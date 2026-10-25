"""Exit interviews: when the discussion is over, every agent is asked what they now conclude. One structured call
per agent on the crowd model. The score is not asked again: it stays the one from the discussion, where every
change had to cite a post. Intent in the report comes from these answers, not from score cut-offs."""
from __future__ import annotations

import asyncio
import random
import re

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

# Purchase probability on a labelled 0-10 scale (Juster): better at predicting what people actually do than intent categories.
LIKELIHOOD = {"type": "number", "description": "0-10: how likely you are to actually buy, sign up for or back it (whichever applies) in the next 3 months. "
                                               "0 = no chance, 1 = very slight, 3 = some chance, 5 = about even, 7 = probably, 9 = almost certain, 10 = certain"}
CHOICE = {"type": "string", "enum": ["This one", "The alternative I named", "Neither"],
          "description": "If you had to choose today between this, the alternative you named, and neither, which would you pick?"}
# Van Westendorp price questions, asked only when a price is shown. Answers in the shown currency so they can be pooled.
PRICE_FIELDS = {
    "price_too_cheap": "At what price would it be so cheap that you'd doubt its quality?",
    "price_bargain": "At what price would it be a bargain, a great buy for the money?",
    "price_getting_expensive": "At what price would it start to feel expensive, though you'd still consider it?",
    "price_too_expensive": "At what price would it be too expensive to consider at all?",
}
PRICE_RE = re.compile(r"(?:[$€£¥₹₦₱]|R\$|MX\$|C\$|A\$|S\$|Rs\.?|USD|EUR|GBP|INR)\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:USD|EUR|GBP|INR|dollars|euros|pounds|rupees)", re.I)


def price_shown(stimulus: dict) -> str | None:
    """The first price in what the crowd read, e.g. "$149", or None."""
    text = " ".join([(stimulus.get("offer") or {}).get("price", "") or "", stimulus.get("brief", "")])
    m = PRICE_RE.search(text)
    return m.group(0).strip() if m else None


def interview_schema(price: str | None) -> dict:
    """Likelihood comes straight after intent and the choice after the alternative it refers to, so the answers stay consistent."""
    props: dict = {}
    for k, v in INTERVIEW_SCHEMA["properties"].items():
        props[k] = v
        if k == "intent":
            props["purchase_likelihood"] = LIKELIHOOD
        elif k == "alternative_named":
            props["choice"] = CHOICE
    if price:
        props |= {k: {"type": "number", "description": f"{q} A number in the same currency as the price shown ({price})."} for k, q in PRICE_FIELDS.items()}
    return {**INTERVIEW_SCHEMA, "properties": props, "required": list(props)}

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


def amount(price: str | None) -> float | None:
    """149.0 from "$149" or "₹1,299"."""
    m = re.search(r"\d[\d,]*(?:\.\d+)?", price or "")
    return float(m.group(0).replace(",", "")) if m else None


def fake_interview(agent: dict, v: dict, score: float, rng: random.Random, price: str | None = None) -> dict:
    """Deterministic stand-in: stated intent is more conservative than the score, as in real panels."""
    first = v.get("score", score)
    ctx = agent.get("_market") or {}
    intent = "Would buy/use" if (score >= 7.5 and rng.random() < 0.55) or (score >= 6.5 and rng.random() < 0.2) else "Maybe" if score >= 4.5 else "Would not"
    known = [k.split(" (")[0] for k in ctx.get("knows", [])]
    alt = (ctx.get("owns") or "").split(" (")[0] or (known[0] if known else "nothing")
    vs = "Don't know any" if alt == "nothing" else "Better" if score >= 7 else "About the same" if score >= 5 else "Worse"
    delta = score - first
    extra: dict = {"purchase_likelihood": round(max(0.0, min(10.0, (score - 3) * 1.2 + (rng.random() - 0.5) * 3))),
                   "choice": "This one" if intent == "Would buy/use" else "The alternative I named" if alt != "nothing" and rng.random() < 0.5 else "Neither"}
    shown = amount(price)
    if shown:
        # Thresholds scale with how much the price weighs on this person and how much they like it.
        f = (0.5 + score / 10) * (0.6 + agent["extra"].get("purchasingPower", 1.0) * 0.6) * (0.8 + rng.random() * 0.4)
        extra |= {"price_too_cheap": round(shown * f * 0.3), "price_bargain": round(shown * f * 0.6),
                  "price_getting_expensive": round(shown * f * 0.95), "price_too_expensive": round(shown * f * 1.3)}
    return {
        **extra,
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
    price = price_shown(stimulus)
    schema = interview_schema(price)
    price_line = f"The price shown is {price}; answer the price questions in that currency, as what you'd really pay given your money.\n" if price else ""
    out: dict[int, dict] = {}

    async def one(agent: dict):
        if state.get("stopped"):
            return
        v = verdicts.get(agent["id"], {})
        now = scores.get(agent["id"], v.get("score", 5.0))
        user = (f"{persona_card(agent['_sk'], agent['_profile'], agent['mood'], agent.get('_mood_reason', ''))}{market_block(agent)}\n\n"
                f"YOUR FIRST IMPRESSION: {v.get('score', now):.1f}/10, \"{v.get('intent', 'Maybe')}\". You said: \"{v.get('reaction', '')}\" Strongest objection: {v.get('objection', 'none')}.\n"
                f"WHAT YOU DID IN THE APP:\n{_activity(actions.get(agent['id'], []), posts_by_id, names)}\n"
                f"YOUR SCORE NOW: {now:.1f}/10.\n{price_line}\nThe discussion is over. Answer the researcher's closing questions. JSON only.")
        local = random.Random(rng.random())
        try:
            iv = await L.json(role="crowd", system=system, user=user, schema=schema, meter=meter, fake=lambda: fake_interview(agent, v, now, local, price), max_tokens=800)
        except Exception as e:
            if type(e).__name__ == "BudgetExceeded":
                state["stopped"] = True; state["stop_reason"] = str(e); return
            iv = fake_interview(agent, v, now, local, price) | {"_error": str(e)[:160]}
        iv["recommend"] = round(max(0.0, min(10.0, float(iv.get("recommend", 5)))))
        if iv.get("intent") not in INTENTS:
            iv["intent"] = "Maybe"
        rec = {"intent": iv["intent"], "takeaway": iv["takeaway"], "changedMind": iv["changed_mind"], "whatChangedIt": iv["what_changed_it"],
               "vsAlternatives": iv["vs_alternatives"], "alternativeNamed": iv["alternative_named"], "recommend": iv["recommend"],
               "oneFix": iv["one_fix"], "quote": iv["quote"],
               "likelihood": round(max(0.0, min(10.0, float(iv.get("purchase_likelihood", 0))))),
               "choice": iv.get("choice") if iv.get("choice") in CHOICE["enum"] else "Neither"}
        if price:
            rec["price"] = {"tooCheap": iv.get("price_too_cheap"), "bargain": iv.get("price_bargain"),
                            "gettingExpensive": iv.get("price_getting_expensive"), "tooExpensive": iv.get("price_too_expensive")}
        out[agent["id"]] = rec
        db.set_interview(run_id, agent["id"], rec)
        await bus.emit(run_id, {"kind": "interview", "agentId": agent["id"], "intent": rec["intent"], "recommend": rec["recommend"],
                                "changedMind": rec["changedMind"], "quote": rec["quote"], "likelihood": rec["likelihood"]})

    await asyncio.gather(*(one(a) for a in agents))
    return out
