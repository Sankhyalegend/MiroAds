"""Stage 2: social rounds. Each round a slice of the crowd opens the app, sees a ranked feed and acts once:
post, reply, repost, like, or nothing, updating their own score. Everyone opens the app at least once over the
rounds. Emits the same events the frontend mock emits."""
from __future__ import annotations

import asyncio
import copy
import math
import random
from dataclasses import dataclass, field

from .. import db
from ..llm import Meter, llm
from ..personas.frame import persona_card
from .events import bus
from .market import market_block
from .stimulus import stimulus_block

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["nothing", "like", "repost", "reply", "post"],
                   "description": "What you do on this visit. On a real feed most visits end in 'nothing' (read and move on) or a 'like'."},
        "target_post_id": {"type": "integer", "description": "Required for like/repost/reply: the id of the feed post you respond to; 0 otherwise"},
        "text": {"type": "string", "description": "Only for reply or post: what you write, in your voice, 1-2 sentences, under 40 words, like a real social post: casual, can be emotional, funny, or a question. No numbered lists unless that is truly your voice. Empty for nothing/like/repost."},
        "new_score": {"type": "number", "description": "Your 0-10 score now. Most people keep their score. Change it only because one specific post in this feed gave you a reason you did not already have, in either direction. A point you already knew, repeated by more people, is not a new reason."},
        "moved_by_post_id": {"type": "integer", "description": "If your score changed, the id of the feed post that changed it. 0 if your score did not change."},
        "why": {"type": "string", "description": "One sentence on why you acted this way and whether your score moved"},
    },
    "required": ["action", "target_post_id", "text", "new_score", "moved_by_post_id", "why"],
    "additionalProperties": False,
}
# A visit on which this person is only scrolling: they can like, repost or move on, but not write.
READ_SCHEMA = copy.deepcopy(ACTION_SCHEMA)
READ_SCHEMA["properties"]["action"] = {"type": "string", "enum": ["nothing", "like", "repost"], "description": "What you do on this visit: move on, like a post, or repost it."}
READ_SCHEMA["properties"]["text"] = {"type": "string", "description": "Always empty on this visit."}

SYSTEM_TEMPLATE = """You are role-playing one specific real person opening a social app where people are discussing a new thing. Stay fully in character and behave the way people really use these apps: most visits end with reading and moving on, or a like. A typical thread gets many likes for every reply, and most readers never write anything. Write only when you have something specific the feed doesn't already have (your own experience, a new angle, a joke, a direct question to someone), or when a post hits a nerve hard enough that you can't resist. Agreeing is a like; agreeing so strongly that you want your own followers to see it is a repost; "same here", "this!" or restating a point already made is never worth a reply. Your posting habit, given with your profile, says how often someone like you writes at all. When you do write, write like a real person on social media: short, in your own voice, sometimes emotional, funny, tangential or blunt. Disagreement is normal; so is enthusiasm.
How opinions actually move: most people finish a thread with the opinion they started with. When someone does change their mind, it is because one specific post gave them a reason they had not considered, and that can push them up (a use case they hadn't pictured, a good experience someone had, a rebuttal of a worry) just as easily as down (a flaw they missed). Seeing the same complaint or the same unanswered question again is not new information and does not make the thing worse than it already seemed to you. Nobody in this feed speaks for the company, so unanswered questions are expected. If the thread has been noise, you can drift back toward your own first impression.

{stimulus}

Respond with JSON only."""


@dataclass
class Post:
    id: int
    agent_id: int
    text: str
    score: float
    round: int
    kind: str  # post|reply
    reply_to: int | None = None
    reposts: int = 0
    replies: int = 0
    likes: int = 0
    exposures: int = 0


@dataclass
class SocialState:
    posts: list[Post] = field(default_factory=list)
    next_id: int = 1


HOUR_CURVE = [0.05, 0.05, 0.05, 0.05, 0.05, 0.1, 0.4, 0.5, 0.7, 0.7, 0.7, 0.8, 1.5, 0.9, 0.7, 0.7, 0.7, 0.8, 1.0, 1.5, 1.5, 1.5, 1.4, 0.6]


def rank_feed(agent: dict, posts: list[Post], agents_by_id: dict[int, dict], k: int, rng: random.Random, scores: dict[int, float]) -> list[Post]:
    """Recency x author influence x segment similarity, with a little echo-chamber weight and noise."""
    if not posts:
        return []
    latest = posts[-1].id
    my = scores.get(agent["id"], 5.0)
    def w(p: Post) -> float:
        if p.agent_id == agent["id"]:
            return 0.0
        author = agents_by_id[p.agent_id]
        recency = math.exp(-(latest - p.id) / 40)
        infl = 0.4 + author["influence"]
        sim = 1.0 + (0.35 if author["professionGroup"] == agent["professionGroup"] else 0) + (0.2 if author["ideology"] == agent["ideology"] else 0) + (0.15 if author["income"] == agent["income"] else 0)
        echo = 1.0 + 0.4 * (1 - min(1, abs(p.score - my) / 5))
        popularity = 1 + 0.15 * p.replies + 0.1 * p.reposts + 0.04 * p.likes
        return recency * infl * sim * echo * popularity * (0.7 + rng.random() * 0.6)
    ranked = sorted(posts[-250:], key=w, reverse=True)
    return [p for p in ranked if p.agent_id != agent["id"]][:k]


def _habit(agent: dict) -> int:
    """0 lurker, 1 occasional replier, 2 regular poster, from activity and extraversion."""
    h = 0.6 * agent["activity"] + 0.4 * agent["traits"]["extraversion"]
    return 0 if h < 0.45 else 1 if h < 0.7 else 2


_HABITS = ("you almost never post or reply online; you read, and now and then you like something.",
           "you reply now and then when something really gets to you, but mostly you read and like.",
           "you post and reply a lot; if you have a take, you share it.")
# Share of visits on which each habit gets to write at all. Asked per call, the model can't keep track of how often
# someone like this writes: in a live run it replied on 97% of visits even when told it rarely posts.
WRITE_CHANCE = (0.1, 0.35, 0.7)


def posting_habit(agent: dict) -> str:
    return _HABITS[_habit(agent)]


def write_chance(agent: dict) -> float:
    return WRITE_CHANCE[_habit(agent)]


def fake_action(agent: dict, feed: list[Post], my_score: float, rng: random.Random, may_write: bool = True) -> dict:
    roll = rng.random()
    ex = agent["extra"]
    pull = 0.0
    if feed:
        # drift toward influential, similar voices
        for p in feed[:4]:
            pull += (p.score - my_score) * 0.08 * (0.5 + agent["traits"]["agreeableness"]) * (1 - agent["traits"]["conscientiousness"] * 0.3)
    new_score = round(max(0, min(10, my_score + pull + (rng.random() - 0.5) * 0.3)), 1)
    writes = 0.75 if may_write else 0.0  # chance this visit produces a reply or post
    if feed and roll < writes * 0.75:
        t = feed[0] if rng.random() < 0.6 else rng.choice(feed)
        agree = abs(t.score - my_score) < 2.5
        text = (f"Same. {t.text.split('.')[0]}." if agree else f"Not buying that. {'For what it costs' if ex['heuristic'] == 'Price-first' else 'Where is the evidence'}?") if my_score < 6.5 else (f"Agree, {t.text.split('.')[0].lower()}." if agree else "Different experience here, it worked for me.")
        return {"action": "reply", "target_post_id": t.id, "text": text, "new_score": new_score, "why": "something in the feed hit a nerve"}
    if roll < writes:
        tone = "Would try it." if my_score >= 6.5 else "On the fence." if my_score >= 4 else "Pass."
        return {"action": "post", "target_post_id": 0, "text": f"{tone} {ex['lens']}", "new_score": new_score, "why": "had something to add"}
    if feed and roll < writes + 0.08:
        t = feed[0] if rng.random() < 0.7 else rng.choice(feed)
        return {"action": "repost", "target_post_id": t.id, "text": "", "new_score": new_score, "why": "strongly agree"}
    if feed and roll < writes + 0.43:
        close = [p for p in feed if abs(p.score - my_score) < 2] or feed
        return {"action": "like", "target_post_id": rng.choice(close).id, "text": "", "new_score": new_score, "why": "agree, nothing to add"}
    return {"action": "nothing", "target_post_id": 0, "text": "", "new_score": new_score, "why": "just scrolling"}


def _fake_with_cause(out: dict, feed: list[Post], my: float) -> dict:
    """Fake provider: attribute any score change to the first feed post, as the schema now requires."""
    out.setdefault("moved_by_post_id", feed[0].id if feed and abs(out["new_score"] - my) >= 0.25 else 0)
    return out


async def run_social(run_id: str, stimulus: dict, agents: list[dict], verdicts: dict[int, dict], meter: Meter, state: dict, rounds: int, rounds_start_hour: int = 9) -> dict[int, float]:
    """Returns final scores. Emits round/post/reply/repost/exposure/mind_change events."""
    L = llm()
    system = SYSTEM_TEMPLATE.format(stimulus=stimulus_block(stimulus))
    rng = random.Random(state["seed"] * 17 + 5)
    agents_by_id = {a["id"]: a for a in agents}
    scores: dict[int, float] = {aid: v["score"] for aid, v in verdicts.items()}
    ss = SocialState()
    stype = stimulus["type"]

    # Seed the feed with the strongest first impressions so round 1 has something to react to.
    seeds = sorted(agents, key=lambda a: -(agents_by_id[a["id"]]["influence"] * (1 + abs(scores.get(a["id"], 5) - 5))))[:max(6, len(agents) // 25)]
    for a in seeds:
        v = verdicts.get(a["id"])
        if not v:
            continue
        p = Post(ss.next_id, a["id"], v["reaction"], scores[a["id"]], 0, "post"); ss.next_id += 1
        ss.posts.append(p)
        await bus.emit(run_id, {"kind": "post", "id": p.id, "agentId": a["id"], "text": p.text, "score": round(p.score, 1), "round": 0})
        db.append_action(run_id, a["id"], {"round": 0, "action": "post", "text": p.text, "score": p.score})

    opened: set[int] = set()  # agents who have opened the app at least once
    for r in range(1, rounds + 1):
        if state.get("stopped"):
            break
        await bus.emit(run_id, {"kind": "round", "round": r, "totalRounds": rounds})
        hour = (rounds_start_hour + r - 1) % 24
        base_share = 0.12 + rng.random() * 0.05
        share = min(0.35, base_share * HOUR_CURVE[hour] * 1.2)
        n_active = max(6, int(len(agents) * share))
        # influence-weighted draw with a long tail of ordinary people
        weights = [0.3 + a["activity"] + a["influence"] * 2 for a in agents]
        active_ids = set()
        while len(active_ids) < min(n_active, len(agents)):
            active_ids.add(rng.choices(range(len(agents)), weights=weights, k=1)[0])
        # Everyone opens the app at least once: spread the people who haven't yet over the remaining rounds.
        waiting = [i for i, a in enumerate(agents) if a["id"] not in opened and i not in active_ids]
        active_ids.update(rng.sample(waiting, min(len(waiting), math.ceil(len(waiting) / (rounds - r + 1)))))
        active = [agents[i] for i in active_ids]
        opened.update(a["id"] for a in active)

        async def act(agent: dict):
            if state.get("stopped"):
                return
            feed = rank_feed(agent, ss.posts, agents_by_id, k=8, rng=random.Random(rng.random()), scores=scores)
            my = scores.get(agent["id"], 5.0)
            v = verdicts.get(agent["id"], {})
            feed_txt = "\n".join(
                f"[post {p.id}] {agents_by_id[p.agent_id]['name']} ({agents_by_id[p.agent_id]['profession']}, {agents_by_id[p.agent_id]['region']}): \"{p.text}\""
                + (f" (reply to post {p.reply_to})" if p.reply_to else "") + (f" · {p.replies} replies, {p.reposts} reposts, {p.likes} likes" if p.replies or p.reposts or p.likes else "")
                for p in feed) or "(feed is empty)"
            first = v.get("score", my)
            # Whether this visit can include writing comes from the person's habit (a dice roll here, on its own random
            # stream so the visits drawn each round don't change). On other visits they can only like, repost or move on.
            may_write = random.Random(f"{state['seed']}:{r}:{agent['id']}").random() < write_chance(agent)
            scrolling = "" if may_write else "This visit you're only scrolling: you won't write anything, but you can like or repost a post, or just move on.\n"
            user = (f"{persona_card(agent['_sk'], agent['_profile'], agent['mood'], agent.get('_mood_reason', ''))}{market_block(agent)}\n"
                    f"Your posting habit: {posting_habit(agent)}\n\n"
                    f"Your first impression, before any discussion: {first:.1f}/10. You said: \"{v.get('reaction', '')}\"\n"
                    f"Your score right now: {my:.1f}/10.\n\n"
                    f"Round {r} of the discussion. Your feed right now:\n{feed_txt}\n\n{scrolling}Decide what you do (or don't). JSON only.")
            local = random.Random(rng.random())
            fake = lambda: _fake_with_cause(fake_action(agent, feed, my, local, may_write), feed, my)
            try:
                out = await L.json(role="crowd", system=system, user=user, schema=ACTION_SCHEMA if may_write else READ_SCHEMA, meter=meter, fake=fake, max_tokens=500)
            except Exception as e:
                if type(e).__name__ == "BudgetExceeded":
                    state["stopped"] = True; state["stop_reason"] = str(e); return
                out = fake()
            # exposures: everything in the feed was seen
            for p in feed:
                p.exposures += 1
                await bus.emit(run_id, {"kind": "exposure", "agentId": agent["id"], "fromAgentId": p.agent_id, "round": r})
            new_score = float(max(0, min(10, out.get("new_score", my))))
            # A score change has to be attributable to a post the agent actually saw. Unattributed drift is reverted
            # and logged, so the social stage measures influence rather than the model's tendency to nudge scores.
            moved_by = next((p for p in feed if p.id == out.get("moved_by_post_id")), None)
            suppressed = None
            if abs(new_score - my) >= 0.25 and moved_by is None:
                suppressed = new_score
                new_score = my
                state["suppressed_moves"] = state.get("suppressed_moves", 0) + 1
            action = out.get("action", "nothing")
            target = next((p for p in feed if p.id == out.get("target_post_id")), None) if action in ("reply", "repost", "like") else None
            if action in ("reply", "repost", "like") and target is None and feed:
                target = feed[0]
            if action == "post" and out.get("text"):
                p = Post(ss.next_id, agent["id"], out["text"].strip(), new_score, r, "post"); ss.next_id += 1
                ss.posts.append(p)
                await bus.emit(run_id, {"kind": "post", "id": p.id, "agentId": agent["id"], "text": p.text, "score": round(new_score, 1), "round": r})
            elif action == "reply" and target and out.get("text"):
                p = Post(ss.next_id, agent["id"], out["text"].strip(), new_score, r, "reply", reply_to=target.id); ss.next_id += 1
                ss.posts.append(p); target.replies += 1
                await bus.emit(run_id, {"kind": "reply", "id": p.id, "agentId": agent["id"], "toAgentId": target.agent_id, "toPostId": target.id, "text": p.text, "score": round(new_score, 1), "round": r})
            elif action == "repost" and target:
                target.reposts += 1
                await bus.emit(run_id, {"kind": "repost", "agentId": agent["id"], "fromAgentId": target.agent_id, "postId": target.id, "round": r})
            elif action == "like" and target:
                target.likes += 1
                await bus.emit(run_id, {"kind": "like", "agentId": agent["id"], "fromAgentId": target.agent_id, "postId": target.id, "round": r})
            else:
                action = "nothing"
            rec = {"round": r, "action": action, "text": out.get("text", "") if action in ("post", "reply") else "", "target": target.id if target else None, "score": new_score, "why": out.get("why", "")}
            if moved_by is not None:
                rec["movedBy"] = moved_by.id
            if suppressed is not None:
                rec["suppressedScore"] = suppressed
            db.append_action(run_id, agent["id"], rec)
            if abs(new_score - my) >= 0.5:
                caused_by = moved_by.agent_id if moved_by else (target.agent_id if target else (feed[0].agent_id if feed else agent["id"]))
                await bus.emit(run_id, {"kind": "mind_change", "agentId": agent["id"], "from": round(my, 1), "to": round(new_score, 1), "causedBy": caused_by,
                                        "postId": moved_by.id if moved_by else None, "round": r})
            if new_score != my:
                scores[agent["id"]] = new_score
                db.set_final_score(run_id, agent["id"], new_score)

        # Stagger starts so the UI animates across the round instead of one burst.
        tasks = []
        for i, a in enumerate(active):
            async def delayed(a=a, i=i):
                await asyncio.sleep(i * (0.9 / max(1, len(active))))
                await act(a)
            tasks.append(delayed())
        await asyncio.gather(*tasks)

    state["posts"] = [p.__dict__ for p in ss.posts]
    return scores
