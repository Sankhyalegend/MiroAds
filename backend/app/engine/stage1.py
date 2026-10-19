"""Stage 1: every agent forms a first impression alone. Structured verdict per agent."""
from __future__ import annotations

import asyncio
import random

from .. import db
from ..llm import Meter, llm
from ..personas.frame import persona_card
from .banks import MISSING, OBJECTIONS, PRAISE
from .events import bus
from .stimulus import stimulus_block

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "description": "0-10 using the anchors in the instructions; use the whole range and decimals (e.g. 6.5)"},
        "intent": {"type": "string", "enum": ["Would buy/use", "Maybe", "Would not"]},
        "reaction": {"type": "string", "description": "Your honest gut reaction in your own voice, 1-2 sentences, as you'd say it to a friend. Emotion allowed."},
        "objection": {"type": "string", "description": "Your single strongest objection in 12 words or fewer, or 'None' if you don't really have one"},
        "missing": {"type": "string", "description": "What would make this better FOR YOU, 10 words or fewer. Can be 'Nothing' or a feeling, not only facts."},
        "price_reaction": {"type": "string", "description": "If a price is shown: how it lands given your income and country, one sentence. If no price is shown, say so and whether that bothers you."},
        "reasoning": {"type": "string", "description": "2-3 sentences: why you scored it this way, referencing your situation and taste"},
        "confidence": {"type": "number", "description": "0-1, how sure you are of your own reaction"},
    },
    "required": ["score", "intent", "reaction", "objection", "missing", "price_reaction", "reasoning", "confidence"],
    "additionalProperties": False,
}

# What the question actually is, per stimulus type. This is the difference between judging an ad and auditing a contract.
FRAMING = {
    "creative": (
        "You are seeing an ADVERTISEMENT (a poster, banner or creative). Judge it as an ad, the way you'd react scrolling past it or seeing it on a wall: "
        "Did it catch you? Do you get what it is? Does it make you curious or want it? Would you remember it, click, or mention it to someone? "
        "Nobody expects warranty terms, spec sheets or return policies on a poster; raise them only if that is genuinely your first reaction to ads.\n"
        "Score anchors: 1-2 ignored or annoyed; 3-4 noticed, not for me; 5-6 curious, would look it up or click; 7-8 want it, would seriously consider buying; 9-10 love it, would share it."
    ),
    "website": (
        "You are visiting a WEBSITE / landing page. Judge it as a visitor: do you understand what this is within seconds, do you trust it, can you find what you need, would you sign up, try or buy?\n"
        "Score anchors: 1-2 bounce immediately; 3-4 read a bit, leave; 5-6 interested, would browse or bookmark; 7-8 would sign up or trial; 9-10 would buy or recommend today."
    ),
    "offer": (
        "You are shown a COMMERCIAL OFFER (price, discount, terms). Judge whether you'd take it: is it worth it for you, do you trust it, does the urgency help or annoy you?\n"
        "Score anchors: 1-2 no, feels like a trick or irrelevant; 3-4 not worth it for me; 5-6 tempting, would think about it; 7-8 would probably take it; 9-10 would take it right now and tell others."
    ),
    "idea": (
        "You are hearing a BUSINESS IDEA pitched in a few sentences. Judge it from your seat: would you use it, pay for it, back it, or recommend it; is the problem real for you; does it sound credible?\n"
        "Score anchors: 1-2 no, flawed or irrelevant; 3-4 meh, wouldn't use; 5-6 interesting, would try if free; 7-8 would pay or back it; 9-10 wish it existed, would evangelize."
    ),
}

SYSTEM_TEMPLATE = """You are role-playing one specific real person in a consumer research panel. Stay fully in character: their income, country, job, politics, personality, what moves them, trust posture, mood and past experiences all shape what you notice and how you judge.
Rules: judge only what is in front of you; do not invent features; react the way this person actually would, including being bored, excited, confused, charmed or unimpressed; use their writing voice; be specific, never generic. Real panels produce a wide spread of scores because people differ in taste, not only in information; be honest about yours. Not everyone needs proof to like something.

{framing}

{stimulus}

Respond with JSON only."""


def fake_verdict(agent: dict, stype: str, rng: random.Random) -> dict:
    """Deterministic stand-in with the same biases the LLM is expected to show."""
    ex = agent["extra"]
    ps = {"Low": .9, "Lower-middle": .75, "Middle": .55, "Upper-middle": .35, "High": .2}[agent["income"]]
    ps = (ps + {"Frugal": .9, "Value-seeking": .55, "Premium": .2}[agent["economic"]]) / 2
    ps = min(1.0, ps + (1 - ex["purchasingPower"]) * 0.35)
    tech = {"Innovator": .9, "Early adopter": .75, "Early majority": .55, "Late majority": .4, "Laggard": .25}[agent["tech"]]
    a = 0.6 + (tech - .5) * .45 + (agent["traits"]["openness"] - .5) * .25 - (ps - .4) * .3
    if ex["trust"] in ("Sceptical of marketing", "Burned before"):
        a -= 0.08
    if ex["temperament"] == "Contrarian":
        a -= 0.12
    if agent["mood"] in ("irritable", "tired", "rushed"):
        a -= 0.05
    if agent["mood"] in ("curious", "upbeat"):
        a += 0.04
    if stype == "idea" and (agent["professionGroup"] == "Finance" or agent["role"] in ("Investor", "Gatekeeper")):
        a -= 0.1
    if stype == "creative" and agent["professionGroup"] == "Design":
        a -= 0.08
    a += (rng.random() - .5) * .36
    score = round(max(0.3, min(9.7, a * 10)), 1)
    obj = OBJECTIONS[stype]
    objection = obj[1] if ps > .65 and rng.random() < .5 else (obj[-1] if agent["tech"] == "Laggard" and rng.random() < .4 else rng.choice(obj))
    pos = score >= 6.5
    return {
        "score": score,
        "intent": "Would buy/use" if score >= 6.5 else "Maybe" if score >= 4 else "Would not",
        "reaction": (rng.choice(PRAISE[stype]) if pos else objection) + ".",
        "objection": "None" if pos and rng.random() < .5 else objection,
        "missing": rng.choice(MISSING[stype]),
        "price_reaction": f"At my income in {ex['country']} this feels {'steep' if ps > .6 else 'reasonable' if ps > .35 else 'cheap'}.",
        "reasoning": f"As a {agent['profession'].lower()} who is {ex['trust'].lower()}, I focus on {ex['overvalues']} and ignore {ex['ignores']}.",
        "confidence": round(0.5 + rng.random() * 0.45, 2),
    }


async def run_stage1(run_id: str, stimulus: dict, agents: list[dict], meter: Meter, state: dict) -> dict[int, dict]:
    """Returns {agent_id: verdict}. Emits 'impression' events as they complete."""
    L = llm()
    system = SYSTEM_TEMPLATE.format(framing=FRAMING[stimulus["type"]], stimulus=stimulus_block(stimulus))
    verdicts: dict[int, dict] = {}
    rng = random.Random(state["seed"] * 31)
    stype = stimulus["type"]

    async def one(agent: dict):
        if state.get("stopped"):
            return
        card = persona_card(agent["_sk"], agent["_profile"], agent["mood"])
        user = f"{card}\n\nYou see the stimulus above for the first time. Give your first impression as JSON."
        local_rng = random.Random(rng.random())
        try:
            v = await L.json(role="crowd", system=system, user=user, schema=VERDICT_SCHEMA, meter=meter, fake=lambda: fake_verdict(agent, stype, local_rng), max_tokens=900)
        except Exception as e:
            if type(e).__name__ == "BudgetExceeded":
                state["stopped"] = True; state["stop_reason"] = str(e); return
            v = fake_verdict(agent, stype, local_rng) | {"_error": str(e)[:160]}
        v["score"] = float(max(0, min(10, v.get("score", 5))))
        verdicts[agent["id"]] = v
        db.set_verdict(run_id, agent["id"], v)
        await bus.emit(run_id, {"kind": "impression", "agentId": agent["id"], "score": round(v["score"], 1)})

    await asyncio.gather(*(one(a) for a in agents))
    return verdicts
