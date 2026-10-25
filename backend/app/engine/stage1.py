"""Stage 1: every agent forms a first impression alone. Structured verdict per agent.
Each person looks at the actual images, and meets ads, sites and offers where they really would (their usual ad places),
so the first questions are whether they'd have stopped at all and what they took in at a glance."""
from __future__ import annotations

import asyncio
import random

from .. import db
from ..llm import Meter, llm
from ..personas.frame import persona_card
from .banks import MISSING, OBJECTIONS, PRAISE
from .events import bus
from .market import market_block
from .stimulus import stimulus_block

# Where someone meets the stimulus, keyed by the ad places in personas/frame.py, plus a friend showing it.
PLACEMENTS = {
    "Instagram or TikTok feed": "as a sponsored post while scrolling your Instagram or TikTok feed",
    "Facebook feed": "as a sponsored post while scrolling Facebook",
    "YouTube ads": "as an ad before a YouTube video you wanted to watch (skippable after 5 seconds)",
    "Reddit promoted posts": "as a promoted post in your Reddit feed",
    "LinkedIn feed": "as a promoted post in your LinkedIn feed during a work break",
    "News websites": "as a banner next to a news article you are reading",
    "Podcasts": "in the show notes of a podcast you listen to",
    "TV and streaming": "in an ad break while streaming a show",
    "Search results": "as a sponsored result at the top of a search for something related",
    "WhatsApp or group chats": "forwarded by someone in a WhatsApp group you're in",
    "Billboards and transit": "on a poster at a bus stop or station on your way somewhere",
    "Trade magazines": "as an ad page in a trade magazine you read for work",
    "In shops": "on a display in a shop you're browsing",
    "Shown by a friend": "when a friend shows it to you on their phone",
}
# People from the first library have no ad places; their information diet stands in.
DIET_PLACE = {"Reddit": "Reddit promoted posts", "YouTube reviews": "YouTube ads", "LinkedIn": "LinkedIn feed", "TikTok/Instagram": "Instagram or TikTok feed",
              "Newspapers & podcasts": "News websites", "Word of mouth": "Shown by a friend", "Trade press": "Trade magazines"}
SITUATION = {
    "creative": "You come across this ad {where}.",
    "website": "You end up on this page after seeing it {where}.",
    "offer": "This offer reaches you {where}.",
}
CLICK = {
    "creative": "Would you tap or click it, or look it up afterwards?",
    "website": "Would you go past this first screen: sign up, start a trial or keep exploring?",
    "offer": "Would you click through to take or check the offer?",
}


def placement(agent: dict, stype: str, rng: random.Random) -> str | None:
    """Where this person meets it in this run. Their main place (from their information diet) counts double; a friend
    showing it on their phone happens one time in ten. Business ideas are pitched, not placed."""
    if stype not in SITUATION:
        return None
    ex = agent["extra"]
    places = list(ex.get("adPlaces") or [DIET_PLACE.get(ex.get("diet", ""), "Instagram or TikTok feed")])
    if stype == "creative":
        places = [p for p in places if p != "Podcasts"]  # a picture needs somewhere to be seen
    if not places or rng.random() < 0.1:
        return "Shown by a friend"
    return rng.choices(places, weights=[2] + [1] * (len(places) - 1))[0]


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


def verdict_schema(stype: str) -> dict:
    """Ads, sites and offers first ask what a real person does in the moment: stop or scroll past, take in a few words, click.
    These come before the score so the gut answer isn't argued into shape by the considered one."""
    if stype not in SITUATION:
        return VERDICT_SCHEMA
    base = VERDICT_SCHEMA["properties"]
    props = {
        "noticed": {"type": "boolean", "description": "Honestly: in that moment, would you have stopped to look at it at all? Most ads get scrolled past."},
        "two_second_takeaway": {"type": "string", "description": "What you took in within the first 2 seconds, 10 words or fewer; 'nothing' if you'd have scrolled past"},
        "score": base["score"], "intent": base["intent"],
        "would_click": {"type": "string", "enum": ["Yes", "Maybe", "No"], "description": CLICK[stype]},
        **{k: v for k, v in base.items() if k not in ("score", "intent")},
    }
    return {**VERDICT_SCHEMA, "properties": props, "required": list(props)}

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
    if agent["mood"] == "wary":
        a -= 0.07
    if agent["mood"] == "excited":
        a += 0.06
    if stype == "idea" and (agent["professionGroup"] == "Finance" or agent["role"] in ("Investor", "Gatekeeper")):
        a -= 0.1
    if stype == "creative" and agent["professionGroup"] == "Design":
        a -= 0.08
    a += (rng.random() - .5) * .36
    score = round(max(0.3, min(9.7, a * 10)), 1)
    obj = OBJECTIONS[stype]
    objection = obj[1] if ps > .65 and rng.random() < .5 else (obj[-1] if agent["tech"] == "Laggard" and rng.random() < .4 else rng.choice(obj))
    pos = score >= 6.5
    attention = {}
    if stype in SITUATION:
        # Most ads are scrolled past; people who like ads, or like this one, stop more often.
        p_stop = 0.25 + 0.04 * (score - 5) + {"Ignores most ads": -0.1, "Sceptical of ads": -0.05, "Enjoys discovering things through ads": 0.15}.get(ex.get("adReceptivity", ""), 0)
        noticed = rng.random() < max(0.05, min(0.9, p_stop))
        attention = {"noticed": noticed, "two_second_takeaway": "a new product, not sure what" if noticed else "nothing",
                     "would_click": "Yes" if noticed and score >= 7 else "Maybe" if noticed and score >= 5 else "No"}
    return {
        **attention,
        "score": score,
        "intent": "Would buy/use" if score >= 6.5 else "Maybe" if score >= 4 else "Would not",
        "reaction": (rng.choice(PRAISE[stype]) if pos else objection) + ".",
        "objection": "None" if pos and rng.random() < .5 else objection,
        "missing": rng.choice(MISSING[stype]),
        "price_reaction": f"At my income in {ex['country']} this feels {'steep' if ps > .6 else 'reasonable' if ps > .35 else 'cheap'}.",
        "reasoning": f"As a {agent['profession'].lower()} who is {ex['trust'].lower()}, I focus on {ex['overvalues']} and ignore {ex['ignores']}.",
        "confidence": round(0.5 + rng.random() * 0.45, 2),
    }


def image_blocks(images: list[dict]) -> list[dict]:
    """The pictures every person looks at, before their own card so the shared part of the message is cached once per run."""
    if not images:
        return []
    blocks: list[dict] = [{"type": "text", "text": "What you see:"}]
    blocks += [{"type": "image", "source": {"type": "base64", "media_type": im["media_type"], "data": im["data"]}} for im in images]
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


async def run_stage1(run_id: str, stimulus: dict, agents: list[dict], meter: Meter, state: dict) -> dict[int, dict]:
    """Returns {agent_id: verdict}. Emits 'impression' events as they complete."""
    L = llm()
    system = SYSTEM_TEMPLATE.format(framing=FRAMING[stimulus["type"]], stimulus=stimulus_block(stimulus))
    verdicts: dict[int, dict] = {}
    rng = random.Random(state["seed"] * 31)
    stype = stimulus["type"]
    schema = verdict_schema(stype)
    seen = image_blocks(stimulus.get("_images") or [])

    async def one(agent: dict):
        if state.get("stopped"):
            return
        local_rng = random.Random(rng.random())
        place = placement(agent, stype, local_rng)
        situation = (f"{SITUATION[stype].format(where=PLACEMENTS[place])} Give it the attention you'd really give it there: first say honestly "
                     f"whether you'd even have stopped, then look at it properly." if place else "You hear this pitch for the first time.")
        card = persona_card(agent["_sk"], agent["_profile"], agent["mood"], agent.get("_mood_reason", ""))
        text = f"{card}{market_block(agent)}\n\n{situation} Give your first impression as JSON."
        try:
            v = await L.json(role="crowd", system=system, user=[*seen, {"type": "text", "text": text}] if seen else text, schema=schema, meter=meter,
                             fake=lambda: fake_verdict(agent, stype, local_rng), max_tokens=900)
        except Exception as e:
            if type(e).__name__ == "BudgetExceeded":
                state["stopped"] = True; state["stop_reason"] = str(e); return
            v = fake_verdict(agent, stype, local_rng) | {"_error": str(e)[:160]}
        v["score"] = float(max(0, min(10, v.get("score", 5))))
        if place:
            v["placement"] = place
        verdicts[agent["id"]] = v
        db.set_verdict(run_id, agent["id"], v)
        await bus.emit(run_id, {"kind": "impression", "agentId": agent["id"], "score": round(v["score"], 1)})

    # One person first, so the shared instructions and images are written to the cache once and everyone after reads them,
    # instead of the first wave of parallel calls each paying to write them.
    if agents:
        await one(agents[0])
    await asyncio.gather(*(one(a) for a in agents[1:]))
    return verdicts
