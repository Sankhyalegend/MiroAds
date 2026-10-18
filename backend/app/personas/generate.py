"""Turn skeletons into people: one cheap LLM call per persona writes backstory, pet peeves, voice,
past products and an evaluation lens. Deterministic fake texture is used without a key."""
from __future__ import annotations

import asyncio
import random

from .. import db
from ..llm import Meter, llm
from .frame import sample_skeleton

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "backstory": {"type": "string", "description": "120-170 words, first person, one specific recent life event, concrete details"},
        "pet_peeves": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
        "overvalues": {"type": "string"},
        "ignores": {"type": "string"},
        "voice": {"type": "string", "description": "How this person writes online, in 15 words or less"},
        "past_products": {
            "type": "array", "minItems": 2, "maxItems": 2,
            "items": {"type": "object", "properties": {"name": {"type": "string"}, "verdict": {"type": "string"}}, "required": ["name", "verdict"], "additionalProperties": False},
        },
        "evaluation_lens": {"type": "string", "description": "One sentence: what they look for first when judging a product, ad, offer or business idea"},
    },
    "required": ["name", "backstory", "pet_peeves", "overvalues", "ignores", "voice", "past_products", "evaluation_lens"],
    "additionalProperties": False,
}

SYSTEM = (
    "You write realistic, specific, non-stereotyped personas for market research panels. "
    "Given structured attributes, invent a believable individual consistent with them. Avoid clichés, avoid naming real companies' employees, "
    "vary sentence rhythm, and never mention that this is a persona. Culturally plausible name for the country. Output JSON only."
)

_PEEVES = ["ads that hide the price", "apps that need an account for everything", "fake urgency", "jargon instead of numbers", "subscriptions for things that should be one-off",
           "products that look good and work badly", "influencer reviews", "tiny fonts in terms", "'AI-powered' on everything", "bundles that force extras",
           "slow websites", "cookie walls", "brands that talk like a friend", "unverified health claims", "packaging bigger than the product"]
_OVER = ["warranties", "brand heritage", "reviews count", "battery life", "design", "a good deal", "local availability", "privacy", "resale value", "customer support stories"]
_IGN = ["marketing taglines", "colour options", "award badges", "social proof", "launch discounts", "spec sheets", "sustainability claims", "celebrity endorsements"]
_VOICE = ["Short, blunt, lowercase.", "Long, careful sentences with caveats.", "Emoji and exclamation marks.", "Dry and sarcastic.", "Earnest and detailed, lists things.",
          "Formal, slightly old-fashioned.", "Non-native English, direct, no articles sometimes.", "Asks questions more than states opinions.", "Numbers and comparisons, little emotion."]
_EVENTS = ["just moved cities for work", "had a second child last spring", "was laid off in March and freelancing since", "started a side business selling online",
           "bought a competitor's product last year and regretted it", "paid off a car loan", "went back to study part-time", "took over the family shop",
           "got promoted and now approves team purchases", "moved back in with parents to save money", "renovated a small apartment on a tight budget", "recovered from burnout"]
_PRODUCTS = [("a smart bulb kit", "returned it, pairing kept dropping"), ("a budget monitor light bar", "great value, still using it"), ("a premium noise-cancelling headset", "worth it, but overpaid"),
             ("a meal-kit subscription", "cancelled after the intro price ended"), ("a fitness tracker", "wore it for two months"), ("an e-reader", "best purchase in years"),
             ("a project management tool for the team", "nobody used it after week two"), ("a language learning app", "liked it until the paywall"), ("a standing desk", "good, assembly was awful"),
             ("a 'smart' water bottle", "pointless, gave it away")]


def fake_profile(sk: dict) -> dict:
    rng = random.Random(sk["seed"] * 7919 + 13)
    ev = rng.choice(_EVENTS)
    prods = rng.sample(_PRODUCTS, 2)
    return {
        "name": sk["nameHint"],
        "backstory": (f"I'm a {sk['profession'].lower()} in {sk['country']}. I {ev}. Money is {'tight' if sk['income'] in ('Low', 'Lower-middle') else 'fine but I watch it' if sk['income'] == 'Middle' else 'not my main worry'}, "
                      f"so I {'compare everything twice' if sk['economic'] == 'Frugal' else 'look for the best value' if sk['economic'] == 'Value-seeking' else 'pay for quality when it shows'}. "
                      f"I get most of my recommendations from {sk['diet']} and I'm {sk['trust'].lower()} after a few bad buys. At work I'm the {sk['role'].lower()} when something new comes in."),
        "pet_peeves": rng.sample(_PEEVES, 2),
        "overvalues": rng.choice(_OVER),
        "ignores": rng.choice(_IGN),
        "voice": rng.choice(_VOICE),
        "past_products": [{"name": n, "verdict": v} for n, v in prods],
        "evaluation_lens": {
            "Price-first": "I look at the price before anything else and work backwards.",
            "Brand-first": "I ask who makes it and whether I've heard of them.",
            "Reviews-first": "I go straight to what real users complained about.",
            "Spec-sheet reader": "I want numbers, not adjectives.",
            "Ask a friend": "I think about who I know that would have an opinion.",
            "Impulse": "If it excites me in five seconds I'm in, otherwise never.",
            "Committee decision": "I think about how I'd justify it to the people who sign off.",
        }[sk["heuristic"]],
    }


async def generate_batch(seeds: list[int], meter: Meter, progress=None) -> int:
    """Generate and store personas for the given seeds. Returns count stored."""
    L = llm()
    rows: list[tuple[int, dict, dict]] = []
    lock = asyncio.Lock()
    done = 0

    async def one(seed: int):
        nonlocal done
        sk = sample_skeleton(seed)
        user = "Attributes:\n" + "\n".join(f"- {k}: {v}" for k, v in sk.items() if k not in ("seed", "nameHint", "traits")) + \
               f"\n- personality: {sk['traits']}\n- suggested name (may adapt for culture): {sk['nameHint']}\nWrite this person."
        try:
            prof = await L.json(role="crowd", system=SYSTEM, user=user, schema=PROFILE_SCHEMA, meter=meter, fake=lambda: fake_profile(sk), max_tokens=700)
        except Exception as e:  # keep the library build going; fall back to template texture
            prof = fake_profile(sk) | {"_error": str(e)[:120]}
        async with lock:
            rows.append((seed, sk, prof))
            done += 1
            if progress and done % 50 == 0:
                progress(done, len(seeds), meter.cost_usd)

    await asyncio.gather(*(one(s) for s in seeds))
    rows.sort(key=lambda r: r[0])
    db.insert_personas(rows)
    return len(rows)
