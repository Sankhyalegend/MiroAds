"""Market scan: what is already on the market, what each agent has plausibly come across, and how the news they
saw shifts their mood. One web-search research call plus one extraction call per run; everything per agent is code."""
from __future__ import annotations

import copy
import random
import re
from collections import Counter

from .. import db
from ..llm import Meter, llm
from .banks import FAKE_MARKET
from .stimulus import stimulus_block

MARKET_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "description": "The market this belongs to, a few words"},
        "summary": {"type": "string", "description": "2-3 sentences: what is already out there and how crowded it is"},
        "price_range": {"type": "string", "description": "Typical prices in the category, e.g. '$25-60, premium $150+'"},
        "competitors": {
            "type": "array", "minItems": 2, "maxItems": 8, "description": "Closest alternatives, most popular first, including the cheap or DIY way",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}, "maker": {"type": "string"}, "price": {"type": "string", "description": "As found, with currency; 'unknown' if not found"},
                    "pitch": {"type": "string", "description": "One line"}, "liked_for": {"type": "string"}, "complaints": {"type": "string"},
                    "url": {"type": "string", "description": "A source URL from the research, or empty"},
                },
                "required": ["name", "maker", "price", "pitch", "liked_for", "complaints", "url"], "additionalProperties": False,
            },
        },
        "news": {
            "type": "array", "maxItems": 6, "description": "Recent news about the category or competitors; empty if none was found",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"}, "source": {"type": "string"}, "date": {"type": "string"}, "gist": {"type": "string", "description": "One line"},
                    "url": {"type": "string"}, "tone": {"type": "string", "enum": ["positive", "neutral", "negative"], "description": "Good or bad news for a new product in this category"},
                },
                "required": ["headline", "source", "date", "gist", "url", "tone"], "additionalProperties": False,
            },
        },
        "buyer_complaints": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "substitutes": {"type": "array", "items": {"type": "string"}, "maxItems": 4, "description": "Non-obvious alternatives: DIY, cheaper hacks, doing nothing"},
    },
    "required": ["category", "summary", "price_range", "competitors", "news", "buyer_complaints", "substitutes"],
    "additionalProperties": False,
}

RESEARCH_SYSTEM = ("You are a market researcher preparing background for a consumer research panel. Use web search to find what already "
                   "exists. Report facts you found, with prices and dates; never invent products, prices or news. Plain prose, no marketing language.")

EXTRACT_SYSTEM = ("You turn market research notes into structured data. Use only what the notes say; keep names, prices and dates as written; "
                  "use a URL only if it appears in the sources list. Respond with JSON only.")


def _research_prompt(stimulus: dict, countries: list[str]) -> str:
    return (f"{stimulus_block(stimulus)}\n"
            f"Competitors the maker already knows about: {stimulus.get('competitors') or 'none given'}.\n"
            f"The panel mostly lives in: {', '.join(countries)}.\n\n"
            "Using web search, find:\n"
            "1. The 4-8 closest existing products, services or substitutes a buyer would compare this with, most popular first. Include the cheap or DIY "
            "way people solve the same need. For each: name, maker, typical price (local prices for the countries above where you find them), "
            "a one-line pitch, what buyers like, what buyers complain about, and a source URL.\n"
            "2. Up to 6 news items from the last 12 months about this category or these competitors (launches, price changes, recalls, trends, studies): "
            "headline, source, date, one-line gist, URL, and whether it is good, neutral or bad news for a new product here.\n"
            "3. The typical price range and the most common buyer complaints in the category.")


def _fake_research(stimulus: dict) -> dict:
    return {"text": "Simulated market research (offline provider).", "sources": [], "searches": 0}


def _camel(brief: dict, sources: list[dict]) -> dict:
    """Schema output (snake_case) -> the frontend MarketBrief shape."""
    return {
        "category": brief["category"], "summary": brief["summary"], "priceRange": brief["price_range"],
        "competitors": [{"name": c["name"], "maker": c["maker"], "price": c["price"], "pitch": c["pitch"], "likedFor": c["liked_for"],
                         "complaints": c["complaints"], "url": c["url"]} for c in brief["competitors"][:8]],
        "news": [dict(n) for n in brief["news"][:6]],
        "buyerComplaints": brief["buyer_complaints"][:5], "substitutes": brief["substitutes"][:4],
        "sources": sources[:20],
    }


async def run_market_scan(stimulus: dict, crowd: list[dict], meter: Meter) -> dict:
    """Returns the `market` event body: {"status": ok|simulated|unavailable, "reason"?, "brief"?}. Never raises."""
    L = llm()
    countries = [c for c, _ in Counter(a["region"] for a in crowd).most_common(5)]
    fake = FAKE_MARKET[stimulus["type"]]
    try:
        research = await L.research(role="market", system=RESEARCH_SYSTEM, user=_research_prompt(stimulus, countries), meter=meter, fake=lambda: _fake_research(stimulus))
        if L.provider == "fake":
            return {"status": "simulated", "brief": _camel(copy.deepcopy(fake), [])}
        if not research["text"]:
            return {"status": "unavailable", "reason": "web search returned nothing usable"}
        src = "\n".join(f"- {s['title']}: {s['url']}" for s in research["sources"][:30]) or "(none)"
        user = f"RESEARCH NOTES:\n{research['text']}\n\nSOURCES:\n{src}\n\nExtract the market data. JSON only."
        brief = await L.json(role="analyst", system=EXTRACT_SYSTEM, user=user, schema=MARKET_SCHEMA, meter=meter, fake=lambda: copy.deepcopy(fake), max_tokens=6000, effort="low")
        if not brief.get("competitors"):
            return {"status": "unavailable", "reason": "no comparable products found"}
        return {"status": "ok", "brief": _camel(brief, research["sources"]), "searches": research["searches"]}
    except Exception as e:  # web search disabled for the org, refusal, budget, network: run on without market context
        return {"status": "unavailable", "reason": f"{type(e).__name__}: {str(e)[:200]}"}


# ---------- what each agent knows (deterministic, no LLM) ----------
_EXTRA_BY_TECH = {"Innovator": 3, "Early adopter": 2, "Early majority": 1, "Late majority": 0, "Laggard": 0}
_NEWS_DIETS = {"Newspapers & podcasts", "Trade press", "LinkedIn"}
_REVIEW_DIETS = {"YouTube reviews", "Reddit"}


def _price_value(price: str) -> float:
    m = re.search(r"\d[\d,.]*", price or "")
    try:
        return float(m.group(0).replace(",", "")) if m else float("inf")
    except ValueError:
        return float("inf")


def market_slice(agent: dict, brief: dict, rng: random.Random) -> dict:
    """What this person has come across, given their tech adoption, information diet, role and spending style."""
    sk = agent["_sk"]
    comps, news = brief.get("competitors", []), brief.get("news", [])
    diet, tech = sk["diet"], sk["tech"]
    base = comps[: 1 if tech in ("Late majority", "Laggard") else 2]  # everyone has heard of the best-known option or two
    rest = comps[len(base):]
    extra = rng.sample(rest, min(_EXTRA_BY_TECH[tech], len(rest)))
    known = base + extra
    knows: list[str] = [f"{c['name']} ({c['maker']}, around {c['price']}): {c['pitch']}" for c in known]
    if known and diet in _REVIEW_DIETS:
        c = rng.choice(known)
        knows.append(f"On {diet} people like {c['name']} for {c['likedFor']}, but complain: {c['complaints']}")
    elif known and diet == "TikTok/Instagram":
        knows.append(f"{comps[0]['name']} keeps showing up on your TikTok/Instagram feed")
    elif known and diet == "Word of mouth":
        c = rng.choice(known)
        knows.append(f"A friend has {c['name']}: likes {c['likedFor']}, grumbles about {c['complaints']}")

    n_news = (2 if tech in ("Innovator", "Early adopter") else 1) if diet in _NEWS_DIETS else (1 if tech in ("Innovator", "Early adopter") or rng.random() < 0.2 else 0)
    seen = rng.sample(news, min(n_news, len(news)))
    owns = None
    if sk["role"] in ("Buyer", "User") and rng.random() < 0.3:
        options = known or comps
        if options:
            by_price = sorted(options, key=lambda c: _price_value(c["price"]))
            c = by_price[0] if sk["economic"] == "Frugal" else by_price[-1] if sk["economic"] == "Premium" else options[0]
            owns = f"{c['name']} ({c['price']})"
        elif brief.get("substitutes"):
            owns = rng.choice(brief["substitutes"])
    return {"knows": knows, "owns": owns, "newsSeen": [f"\"{n['headline']}\" ({n['source']}, {n['date']}): {n['gist']}" for n in seen], "_news": seen}


def news_mood(agent: dict, seen_news: list[dict], rng: random.Random) -> tuple[str, str] | None:
    """Bad news makes anxious or cynical people wary, hype puts contrarians off, good news lifts optimists. Others keep their mood."""
    if not seen_news:
        return None
    sk = agent["_sk"]
    temp, tr = sk["temperament"], sk["traits"]
    tone = sum({"positive": 1, "negative": -1}.get(n.get("tone", ""), 0) for n in seen_news)
    if tone == 0:
        return None
    lead = next(n for n in seen_news if n.get("tone") == ("negative" if tone < 0 else "positive"))
    reason = f"you just read \"{lead['headline']}\" ({lead['source']})"
    if tone < 0 and (temp in ("Anxious", "Cynical") or tr["neuroticism"] >= 0.6) and rng.random() < 0.7:
        return "wary", reason
    if tone > 0 and temp == "Contrarian" and rng.random() < 0.7:
        return "wary", reason + " and the hype puts you off"
    if tone > 0 and (temp in ("Optimistic", "Enthusiastic") or tr["openness"] >= 0.65) and rng.random() < 0.7:
        return "excited", reason
    return None


def apply_market(run_id: str, crowd: list[dict], brief: dict | None, seed: int) -> dict:
    """Gives every agent their slice of the market and any news-driven mood shift; persists both. Returns shift counts."""
    shifts: Counter = Counter()
    if not brief:
        return {}
    rng = random.Random(seed * 13 + 3)
    for a in crowd:
        sl = market_slice(a, brief, random.Random(rng.random()))
        ctx = {k: v for k, v in sl.items() if not k.startswith("_")}
        shift = news_mood(a, sl["_news"], random.Random(rng.random()))
        if shift:
            ctx["moodBefore"], ctx["moodReason"] = a["mood"], shift[1]
            a["mood"], a["_mood_reason"] = shift[0], shift[1]
            shifts[shift[0]] += 1
        a["_market"] = ctx
        db.set_context(run_id, a["id"], ctx, a["mood"], {k: v for k, v in a.items() if not k.startswith("_")})
    return {"wary": shifts["wary"], "excited": shifts["excited"]}


def market_summary(brief: dict | None) -> str:
    """The full brief as text for the research team and the report author."""
    if not brief:
        return "MARKET SCAN: none available for this run."
    comps = "\n".join(f"  - {c['name']} ({c['maker']}, {c['price']}): {c['pitch']}; liked for {c['likedFor']}; complaints: {c['complaints']}" for c in brief["competitors"])
    news = "\n".join(f"  - [{n['tone']}] {n['headline']} ({n['source']}, {n['date']}): {n['gist']}" for n in brief["news"]) or "  (none found)"
    return (f"MARKET SCAN ({brief['category']}): {brief['summary']} Price range: {brief['priceRange']}.\nAlternatives:\n{comps}\nRecent news:\n{news}\n"
            f"Category complaints: {', '.join(brief['buyerComplaints']) or 'none found'}. Substitutes: {', '.join(brief['substitutes']) or 'none found'}.\n"
            "Each panelist only knew part of this, depending on their feeds; about 30% of buyers and users already own an alternative.")


def market_block(agent: dict) -> str:
    """The agent's market knowledge as prompt text, placed after the persona card. Empty when there was no scan."""
    ctx = agent.get("_market")
    if not ctx:
        return ""
    lines = [f"- {k}" for k in ctx["knows"]] + [f"- You read: {n}" for n in ctx["newsSeen"]]
    if ctx.get("owns"):
        lines.append(f"- You currently use: {ctx['owns']}")
    body = "\n".join(lines) if lines else "- You don't know any similar products."
    return ("\n\nWHAT YOU ALREADY KNOW ABOUT THIS MARKET (from your own life and feeds; this is all you know, don't invent more):\n"
            f"{body}\nCompare with these only if that's natural for you.")
