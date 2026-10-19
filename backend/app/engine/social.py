"""Stage 2: social rounds. Each round a slice of the crowd sees a ranked feed and acts once:
post, reply, repost, or nothing, updating their own score. Emits the same events the frontend mock emits."""
from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass, field

from .. import db
from ..llm import Meter, llm
from ..personas.frame import persona_card
from .events import bus
from .stimulus import stimulus_block

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["post", "reply", "repost", "nothing"]},
        "target_post_id": {"type": "integer", "description": "Required for reply/repost: the id of the feed post you respond to; 0 otherwise"},
        "text": {"type": "string", "description": "What you write (post or reply), in your voice, 1-2 sentences, under 40 words, like a real social post: casual, can be emotional, funny, or a question. No numbered lists unless that is truly your voice. Empty for repost/nothing."},
        "new_score": {"type": "number", "description": "Your 0-10 score after reading the feed. Keep it if nothing moved you; move it, sometimes by a lot, if someone you relate to showed you something you missed, or if the pile-on made you push back."},
        "why": {"type": "string", "description": "One sentence on why you acted this way and whether your score moved"},
    },
    "required": ["action", "target_post_id", "text", "new_score", "why"],
    "additionalProperties": False,
}

SYSTEM_TEMPLATE = """You are role-playing one specific real person browsing a social feed where people discuss a new thing. Stay fully in character and write like a real person on social media: short, in your own voice, sometimes emotional, funny, tangential or blunt. People mostly scroll; they reply when something hits a nerve or delights them, repost what they strongly agree with, and post when they have something new to add (a different angle, a personal story, a joke, a question). Don't repeat what the thread already said; add something, repost it, or stay quiet. If you agree with a post and have nothing new to add, repost it rather than writing a "same here" reply. Disagreement is normal; so is enthusiasm. Opinions move when someone you relate to shows you something you missed, and sometimes people double down when a thread piles on.

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
        popularity = 1 + 0.15 * p.replies + 0.1 * p.reposts
        return recency * infl * sim * echo * popularity * (0.7 + rng.random() * 0.6)
    ranked = sorted(posts[-250:], key=w, reverse=True)
    return [p for p in ranked if p.agent_id != agent["id"]][:k]


def fake_action(agent: dict, feed: list[Post], my_score: float, rng: random.Random) -> dict:
    roll = rng.random()
    ex = agent["extra"]
    pull = 0.0
    if feed:
        # drift toward influential, similar voices
        for p in feed[:4]:
            pull += (p.score - my_score) * 0.08 * (0.5 + agent["traits"]["agreeableness"]) * (1 - agent["traits"]["conscientiousness"] * 0.3)
    new_score = round(max(0, min(10, my_score + pull + (rng.random() - 0.5) * 0.3)), 1)
    if feed and roll < 0.42:
        t = feed[0] if rng.random() < 0.6 else rng.choice(feed)
        agree = abs(t.score - my_score) < 2.5
        text = (f"Same. {t.text.split('.')[0]}." if agree else f"Not buying that. {'For what it costs' if ex['heuristic'] == 'Price-first' else 'Where is the evidence'}?") if my_score < 6.5 else (f"Agree, {t.text.split('.')[0].lower()}." if agree else "Different experience here, it worked for me.")
        return {"action": "reply", "target_post_id": t.id, "text": text, "new_score": new_score, "why": "something in the feed hit a nerve"}
    if feed and roll < 0.56:
        t = feed[0] if rng.random() < 0.7 else rng.choice(feed)
        return {"action": "repost", "target_post_id": t.id, "text": "", "new_score": new_score, "why": "strongly agree"}
    if roll < 0.78:
        tone = "Would try it." if my_score >= 6.5 else "On the fence." if my_score >= 4 else "Pass."
        return {"action": "post", "target_post_id": 0, "text": f"{tone} {ex['lens']}", "new_score": new_score, "why": "had something to add"}
    return {"action": "nothing", "target_post_id": 0, "text": "", "new_score": new_score, "why": "just scrolling"}


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
        active = [agents_by_id[i] for i in active_ids]

        async def act(agent: dict):
            if state.get("stopped"):
                return
            feed = rank_feed(agent, ss.posts, agents_by_id, k=8, rng=random.Random(rng.random()), scores=scores)
            my = scores.get(agent["id"], 5.0)
            v = verdicts.get(agent["id"], {})
            feed_txt = "\n".join(
                f"[post {p.id}] {agents_by_id[p.agent_id]['name']} ({agents_by_id[p.agent_id]['profession']}, {agents_by_id[p.agent_id]['region']}): \"{p.text}\""
                + (f" (reply to post {p.reply_to})" if p.reply_to else "") + (f" · {p.replies} replies, {p.reposts} reposts" if p.replies or p.reposts else "")
                for p in feed) or "(feed is empty)"
            user = (f"{persona_card(agent['_sk'], agent['_profile'], agent['mood'])}\n\n"
                    f"Your first impression earlier: score {my:.1f}/10. You said: \"{v.get('reaction', '')}\" Your objection: {v.get('objection', '')}.\n\n"
                    f"Round {r} of the discussion. Your feed right now:\n{feed_txt}\n\nDecide what you do (or don't). JSON only.")
            local = random.Random(rng.random())
            try:
                out = await L.json(role="crowd", system=system, user=user, schema=ACTION_SCHEMA, meter=meter, fake=lambda: fake_action(agent, feed, my, local), max_tokens=500)
            except Exception as e:
                if type(e).__name__ == "BudgetExceeded":
                    state["stopped"] = True; state["stop_reason"] = str(e); return
                out = fake_action(agent, feed, my, local)
            # exposures: everything in the feed was seen
            for p in feed:
                p.exposures += 1
                await bus.emit(run_id, {"kind": "exposure", "agentId": agent["id"], "fromAgentId": p.agent_id, "round": r})
            new_score = float(max(0, min(10, out.get("new_score", my))))
            action = out.get("action", "nothing")
            target = next((p for p in feed if p.id == out.get("target_post_id")), None) if action in ("reply", "repost") else None
            if action in ("reply", "repost") and target is None and feed:
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
            else:
                action = "nothing"
            db.append_action(run_id, agent["id"], {"round": r, "action": action, "text": out.get("text", ""), "target": target.id if target else None, "score": new_score, "why": out.get("why", "")})
            if abs(new_score - my) >= 0.5:
                caused_by = target.agent_id if target else (feed[0].agent_id if feed else agent["id"])
                await bus.emit(run_id, {"kind": "mind_change", "agentId": agent["id"], "from": round(my, 1), "to": round(new_score, 1), "causedBy": caused_by, "round": r})
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
