"""Exit interviews: when the discussion is over, every agent is asked what they now conclude. One structured call
per agent on the crowd model. The score is not asked again: it stays the one from the discussion, where every
change had to cite a post. Intent in the report comes from these answers, not from score cut-offs."""
from __future__ import annotations

import asyncio
import random

from .. import db
from ..llm import Meter, llm
from ..personas.frame import persona_card
from .events import bus
from .market import market_block
from .stimulus import stimulus_block

INTENTS = ["Would buy/use", "Maybe", "Would not"]

INTERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS, "description": "What you would actually do now. 'Would buy/use' means you would really spend the money or the time."},
        "takeaway": {"type": "string", "description": "Your conclusion about it now, 2-3 sentences, in your own voice"},
        "changed_mind": {"type": "string", "enum": ["No", "More positive", "More negative"], "description": "Compared with your first impression"},
        "what_changed_it": {"type": "string", "description": "The post, person, competitor or fact that changed your view, or 'nothing'"},
        "vs_alternatives": {"type": "string", "enum": ["Better", "About the same", "Worse", "Don't know any"], "description": "Compared with what you use or know of today"},
        "alternative_named": {"type": "string", "description": "What you'd compare it with or choose instead (a product, a habit, or 'nothing'), a few words"},
        "recommend": {"type": "number", "description": "0-10: how likely you are to recommend it to a friend or colleague"},
        "one_fix": {"type": "string", "description": "The single change that would win you over, or 'nothing'; 12 words or fewer"},
        "quote": {"type": "string", "description": "One line you'd say to a friend about it, in your voice"},
    },
    "required": ["intent", "takeaway", "changed_mind", "what_changed_it", "vs_alternatives", "alternative_named", "recommend", "one_fix", "quote"],
    "additionalProperties": False,
}

SYSTEM_TEMPLATE = """You are role-playing one specific real person who just spent time in a social app where people discussed a new thing, and a researcher is now asking you a few closing questions. Stay fully in character: your income, country, job, personality, mood, what moves you and what you already own all shape your answers, and you answer in your own writing voice.
Be honest about what you would actually do. Most people who feel positive still don't buy; "Maybe" is a normal answer and "Would buy/use" means you would really spend the money or the time. Answer from what you saw and what you already know; don't invent facts.

{stimulus}

Respond with JSON only."""


def _activity(actions: list[dict], posts_by_id: dict[int, dict], names: dict[int, str]) -> str:
    lines = []
    for a in actions:
        if a.get("round", 0) < 1 or a["action"] == "nothing":
            continue
        tgt = posts_by_id.get(a.get("target") or -1)
        about = f" post by {names.get(tgt['agent_id'], 'someone')}: \"{tgt['text'][:120]}\"" if tgt else ""
        said = f" You wrote: \"{a['text']}\"" if a.get("text") else ""
        lines.append(f"- Round {a['round']}: {a['action']}{about}.{said}")
        moved = posts_by_id.get(a.get("movedBy") or -1)
        if moved:
            lines.append(f"  This post changed your score: {names.get(moved['agent_id'], 'someone')}: \"{moved['text'][:160]}\"")
    return "\n".join(lines[-8:]) or "- You scrolled the feed but didn't post, reply, repost or like anything."


def fake_interview(agent: dict, v: dict, score: float, rng: random.Random) -> dict:
    """Deterministic stand-in: stated intent is more conservative than the score, as in real panels."""
    first = v.get("score", score)
    ctx = agent.get("_market") or {}
    intent = "Would buy/use" if (score >= 7.5 and rng.random() < 0.55) or (score >= 6.5 and rng.random() < 0.2) else "Maybe" if score >= 4.5 else "Would not"
    known = [k.split(" (")[0] for k in ctx.get("knows", [])]
    alt = (ctx.get("owns") or "").split(" (")[0] or (known[0] if known else "nothing")
    vs = "Don't know any" if alt == "nothing" else "Better" if score >= 7 else "About the same" if score >= 5 else "Worse"
    delta = score - first
    return {
        "intent": intent,
        "takeaway": f"{'Still' if abs(delta) < 0.5 else 'Now'} {'keen on it' if score >= 6.5 else 'on the fence' if score >= 4 else 'not for me'}. {v.get('reaction', '')}",
        "changed_mind": "No" if abs(delta) < 0.5 else "More positive" if delta > 0 else "More negative",
        "what_changed_it": "nothing" if abs(delta) < 0.5 else "a post in the feed",
        "vs_alternatives": vs, "alternative_named": alt,
        "recommend": round(max(0.0, min(10.0, score + (rng.random() - 0.5) * 2))),
        "one_fix": v.get("missing", "nothing"), "quote": v.get("reaction", ""),
    }


async def run_interviews(run_id: str, stimulus: dict, agents: list[dict], verdicts: dict[int, dict], scores: dict[int, float],
                         posts: list[dict], meter: Meter, state: dict) -> dict[int, dict]:
    """Returns {agent_id: interview}. Emits an 'interview' event per agent."""
    L = llm()
    system = SYSTEM_TEMPLATE.format(stimulus=stimulus_block(stimulus))
    rng = random.Random(state["seed"] * 7 + 11)
    posts_by_id = {p["id"]: p for p in posts}
    names = {a["id"]: a["name"] for a in agents}
    actions = {r["id"]: r["actions"] for r in db.get_run_agents(run_id)}
    out: dict[int, dict] = {}

    async def one(agent: dict):
        if state.get("stopped"):
            return
        v = verdicts.get(agent["id"], {})
        now = scores.get(agent["id"], v.get("score", 5.0))
        user = (f"{persona_card(agent['_sk'], agent['_profile'], agent['mood'], agent.get('_mood_reason', ''))}{market_block(agent)}\n\n"
                f"YOUR FIRST IMPRESSION: {v.get('score', now):.1f}/10, \"{v.get('intent', 'Maybe')}\". You said: \"{v.get('reaction', '')}\" Strongest objection: {v.get('objection', 'none')}.\n"
                f"WHAT YOU DID IN THE APP:\n{_activity(actions.get(agent['id'], []), posts_by_id, names)}\n"
                f"YOUR SCORE NOW: {now:.1f}/10.\n\nThe discussion is over. Answer the researcher's closing questions. JSON only.")
        local = random.Random(rng.random())
        try:
            iv = await L.json(role="crowd", system=system, user=user, schema=INTERVIEW_SCHEMA, meter=meter, fake=lambda: fake_interview(agent, v, now, local), max_tokens=700)
        except Exception as e:
            if type(e).__name__ == "BudgetExceeded":
                state["stopped"] = True; state["stop_reason"] = str(e); return
            iv = fake_interview(agent, v, now, local) | {"_error": str(e)[:160]}
        iv["recommend"] = round(max(0.0, min(10.0, float(iv.get("recommend", 5)))))
        if iv.get("intent") not in INTENTS:
            iv["intent"] = "Maybe"
        rec = {"intent": iv["intent"], "takeaway": iv["takeaway"], "changedMind": iv["changed_mind"], "whatChangedIt": iv["what_changed_it"],
               "vsAlternatives": iv["vs_alternatives"], "alternativeNamed": iv["alternative_named"], "recommend": iv["recommend"],
               "oneFix": iv["one_fix"], "quote": iv["quote"]}
        out[agent["id"]] = rec
        db.set_interview(run_id, agent["id"], rec)
        await bus.emit(run_id, {"kind": "interview", "agentId": agent["id"], "intent": rec["intent"], "recommend": rec["recommend"],
                                "changedMind": rec["changedMind"], "quote": rec["quote"]})

    await asyncio.gather(*(one(a) for a in agents))
    return out
