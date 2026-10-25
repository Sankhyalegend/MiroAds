"""Turn skeletons into people: one cheap LLM call per persona writes backstory, pet peeves, voice,
past products and an evaluation lens. Deterministic fake texture is used without a key."""
from __future__ import annotations

import asyncio
import collections
import random

from .. import db
from ..llm import Meter, llm
from .frame import FRAME_VERSION, SETTLEMENT_PHRASE, sample_skeleton

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "backstory": {"type": "string", "description": "90-130 words, first person, one specific recent life event, concrete details. Hard limit 140 words."},
        "pet_peeves": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
        "overvalues": {"type": "string", "description": "A short phrase, 10 words or less"},
        "ignores": {"type": "string", "description": "A short phrase, 10 words or less"},
        "voice": {"type": "string", "description": "How this person writes online, in 15 words or less"},
        "past_products": {
            "type": "array", "minItems": 2, "maxItems": 2,
            "items": {"type": "object", "properties": {"name": {"type": "string"}, "verdict": {"type": "string", "description": "15 words or less"}},
                      "required": ["name", "verdict"], "additionalProperties": False},
        },
        "evaluation_lens": {"type": "string", "description": "One sentence of 20 words or less: what they look for first when judging a product, ad, offer or business idea"},
    },
    "required": ["name", "backstory", "pet_peeves", "overvalues", "ignores", "voice", "past_products", "evaluation_lens"],
    "additionalProperties": False,
}

SYSTEM = (
    "You write realistic, specific, non-stereotyped personas for market research panels. "
    "Given structured attributes, invent a believable individual consistent with them. Avoid clichés, avoid naming real companies' employees, "
    "vary sentence rhythm, and never mention that this is a persona. Give an ordinary, believable full name for someone of that gender and age "
    "in that country, the kind found in a real phone book: vary region, community and generation rather than reaching for the single most common "
    "or stereotypical name, and do not invent double-barrelled or mixed-culture surnames unless the person's background calls for one.\n"
    "Important for realism: most people are NOT careful, sceptical, spec-reading buyers. Let the attributes decide. A person whose motivation is looks, status, fun, "
    "convenience or novelty should have an evaluation lens, pet peeves and past-product verdicts that reflect THAT (e.g. 'I buy what makes my desk look good', "
    "'I hate ugly packaging', 'bought it because a friend had one'), not warranty or return-policy talk. Only personas whose trust posture, heuristic or motivation "
    "point to proof, price or reliability should care about specs, terms, warranties or total cost. Give enthusiasts real enthusiasm.\n"
    "Make the backstory fit the life stage, household, place and spare money: a parent of young kids in a small town has different days, worries "
    "and budgets than a single renter in a capital. Let their values and brand habits show in the past-product verdicts. Output JSON only."
)
NAME_LETTERS = "ABCDEFGHIJKLMNOPRSTVYZ"

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


def tidy(prof: dict) -> dict:
    """Names sometimes come back with stray spaces."""
    prof["name"] = " ".join(str(prof.get("name", "")).split())
    return prof


def profile_prompt(sk: dict, avoid: list[str] | None = None) -> str:
    """The attributes as the persona writer reads them. The name letters spread names out when thousands are written at once
    (batch requests can't see each other's names); duplicates left over are renamed by dedupe_names."""
    letters = ", ".join(random.Random(sk["seed"] * 31 + 7).sample(NAME_LETTERS, 3))
    lines = [
        f"Job: {sk['profession']} ({sk['professionGroup']}){', now retired' if sk['lifeStage'] == 'Retired' else ''}",
        f"Age: {sk['ageBand']}; gender: {sk['gender']}; education: {sk['education']}",
        f"Lives {SETTLEMENT_PHRASE[sk['settlement']]} in {sk['country']} ({sk['gdpTier']}-income country, currency {sk['currency']})",
        f"Life stage: {sk['lifeStage']}; household of {sk['household']}",
        f"Household income: {sk['income']} for their country; money left each month after essentials: about {sk['spareMoney']}; spending style: {sk['economic']}",
        f"Politics: {sk['ideology']}; {sk['institutions']}; {sk['bigTech']}",
        f"Tech adoption: {sk['tech']}; role when buying: {sk['role']}; trust: {sk['trust']}; decides by: {sk['heuristic']}; brands: {sk['brandLoyalty']}",
        f"Information diet: {sk['diet']}; ads: {sk['adReceptivity']}{', uses an ad blocker' if sk['adBlocker'] else ''}; meets ads mostly on: {', '.join(sk['adPlaces'])}",
        f"Cares about: {sk['values'][0]} and {sk['values'][1]}; what moves them most: {sk['motivation']}",
        f"Temperament: {sk['temperament']}; reacts to new things: {sk['responseStyle']}",
        f"Personality (0-1): {sk['traits']}",
        f"Name: real-sounding for {sk['country']}, this gender and age; if one fits naturally, a first name starting with {letters}",
    ]
    if avoid:
        lines.append(f"These names are already overused in this panel, do NOT use them or close variants: {', '.join(avoid)}")
    return "Attributes:\n" + "\n".join(f"- {line}" for line in lines) + "\nWrite this person."


async def generate_batch(seeds: list[int], meter: Meter, progress=None, avoid_names: dict[str, list[str]] | None = None) -> int:
    """Generate and store personas for the given seeds. Returns count stored.
    `avoid_names` maps country -> names already overused there, so the model picks something else."""
    L = llm()
    rows: list[tuple[int, dict, dict]] = []
    lock = asyncio.Lock()
    done = 0

    async def one(seed: int):
        nonlocal done
        sk = sample_skeleton(seed)
        user = profile_prompt(sk, (avoid_names or {}).get(sk["country"], [])[:40])
        try:
            prof = tidy(await L.json(role="crowd", system=SYSTEM, user=user, schema=PROFILE_SCHEMA, meter=meter, fake=lambda: fake_profile(sk), max_tokens=1200))
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


def overused_names(min_count: int = 2, version: int = FRAME_VERSION) -> dict[str, list[str]]:
    """country -> names that already appear at least `min_count` times there, most frequent first."""
    by_country: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for p in db.all_personas(version):
        if "_error" not in p["profile"]:
            by_country[p["skeleton"]["country"]][p["profile"]["name"]] += 1
    return {c: [n for n, k in cnt.most_common() if k >= min_count] for c, cnt in by_country.items()}


NAME_SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}
NAME_SYSTEM = ("You give realistic full names to research-panel participants. Culturally plausible for the country, matching gender and age, "
               "and deliberately uncommon enough not to collide with names already in use. Output JSON only.")


async def dedupe_names(meter: Meter, progress=None, version: int = FRAME_VERSION) -> int:
    """Rename every persona of this library version whose name is already taken (keeping the lowest id). One tiny call each.
    Returns renamed count."""
    L = llm()
    lib = sorted((p for p in db.all_personas(version) if "_error" not in p["profile"]), key=lambda p: p["id"])
    taken: dict[str, set[str]] = collections.defaultdict(set)
    seen: set[str] = set()
    dupes = []
    for p in lib:
        nm = p["profile"]["name"].strip()
        taken[p["skeleton"]["country"]].add(nm)
        if nm.lower() in seen:
            dupes.append(p)
        seen.add(nm.lower())
    lock = asyncio.Lock()
    renamed = 0

    async def one(p: dict):
        nonlocal renamed
        sk = p["skeleton"]
        used = sorted(taken[sk["country"]])
        user = (f"Country: {sk['country']}. Gender: {sk['gender']}. Age band: {sk['ageBand']}. Profession: {sk['profession']}.\n"
                f"Already used in this country, do not reuse any of these or close variants: {', '.join(used[-150:])}\nGive one new full name.")
        try:
            out = await L.json(role="crowd", system=NAME_SYSTEM, user=user, schema=NAME_SCHEMA, meter=meter, fake=lambda: {"name": f"{sk['nameHint']} {p['id']}"}, max_tokens=60)
        except Exception:
            return
        new = out.get("name", "").strip()
        async with lock:
            if not new or new.lower() in seen:
                return
            seen.add(new.lower()); taken[sk["country"]].add(new)
            old = p["profile"]["name"]
            prof = dict(p["profile"]); prof["name"] = new
            # Backstories are first person and rarely name the speaker, but keep them consistent if they do.
            if old and old in prof.get("backstory", ""):
                prof["backstory"] = prof["backstory"].replace(old, new)
            db.update_persona_profile(p["id"], prof)
            renamed += 1
            if progress and renamed % 100 == 0:
                progress(renamed, len(dupes), meter.cost_usd)

    await asyncio.gather(*(one(p) for p in dupes))
    return renamed
