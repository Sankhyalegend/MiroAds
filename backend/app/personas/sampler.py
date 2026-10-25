"""Draw a crowd for one run from the library: stratified, audience-weighted, with forced edges, drawn from the people
tested least so far, reproducible by seed. Also assigns each agent a mood for today."""
from __future__ import annotations

import heapq
import random
import re
from collections import defaultdict
from functools import lru_cache
from typing import Callable

from .frame import COUNTRIES, INCOME, IDEOLOGY, MOODS, PROFESSION_GROUPS, to_frontend_persona

AUDIENCE_KEYWORDS = {
    "developer": ("Engineering",), "engineer": ("Engineering",), "software": ("Engineering",), "designer": ("Design",),
    "marketer": ("Marketing",), "marketing": ("Marketing",), "founder": ("Executives",), "executive": ("Executives",), "ceo": ("Executives",),
    "student": ("Students",), "students": ("Students",), "nurse": ("Healthcare",), "doctor": ("Healthcare",), "teacher": ("Education",),
    "finance": ("Finance",), "procurement": ("Finance",), "retail": ("Retail & Service",), "small business": ("Executives", "Retail & Service"),
    "operations": ("Operations",), "productivity": ("Executives", "Marketing", "Engineering"),
}

# Words in an audience description that point at countries. Matched as whole words; the short codes only in
# capitals, so "people like us" or "business" never target a country.
_CODES = {"US": ("United States",), "U.S.": ("United States",), "USA": ("United States",), "UK": ("United Kingdom",),
          "EU": ("Germany", "Poland"), "UAE": ("UAE",)}
_ALIASES = {
    "america": ("United States",), "american": ("United States",), "americans": ("United States",),
    "britain": ("United Kingdom",), "british": ("United Kingdom",), "england": ("United Kingdom",),
    "europe": ("United Kingdom", "Germany", "Poland"), "european": ("United Kingdom", "Germany", "Poland"), "europeans": ("United Kingdom", "Germany", "Poland"),
    "indian": ("India",), "indians": ("India",), "german": ("Germany",), "germans": ("Germany",), "brazilian": ("Brazil",), "brazilians": ("Brazil",),
    "nigerian": ("Nigeria",), "nigerians": ("Nigeria",), "japanese": ("Japan",), "korean": ("South Korea",), "koreans": ("South Korea",),
    "korea": ("South Korea",), "chinese": ("China",), "mexican": ("Mexico",), "mexicans": ("Mexico",), "canadian": ("Canada",), "canadians": ("Canada",),
    "australian": ("Australia",), "australians": ("Australia",), "singaporean": ("Singapore",), "singaporeans": ("Singapore",),
    "filipino": ("Philippines",), "filipinos": ("Philippines",), "vietnamese": ("Vietnam",), "indonesian": ("Indonesia",), "indonesians": ("Indonesia",),
    "turkish": ("Turkey",), "egyptian": ("Egypt",), "egyptians": ("Egypt",), "kenyan": ("Kenya",), "kenyans": ("Kenya",), "pakistani": ("Pakistan",),
    "pakistanis": ("Pakistan",), "bangladeshi": ("Bangladesh",), "polish": ("Poland",), "emirati": ("UAE",), "dubai": ("UAE",),
    "latin america": ("Brazil", "Mexico"), "latam": ("Brazil", "Mexico"), "africa": ("South Africa", "Nigeria", "Kenya", "Egypt"),
    "african": ("South Africa", "Nigeria", "Kenya", "Egypt"), "southeast asia": ("Singapore", "Indonesia", "Philippines", "Vietnam"),
    "south asia": ("India", "Pakistan", "Bangladesh"), "middle east": ("UAE", "Egypt", "Turkey"),
} | {c.lower(): (c,) for c, *_ in COUNTRIES}


@lru_cache(maxsize=64)
def audience_countries(audience: str) -> frozenset[str]:
    """Countries an audience description names, e.g. 'US students' -> {'United States'}."""
    found: set[str] = set()
    for code, cs in _CODES.items():
        if re.search(rf"(?<![A-Za-z]){re.escape(code)}(?![A-Za-z])", audience):
            found.update(cs)
    low = audience.lower()
    for word, cs in _ALIASES.items():
        if re.search(rf"\b{re.escape(word)}\b", low):
            found.update(cs)
    return frozenset(found)


def _audience_weight(sk: dict, audience: str) -> float:
    a = audience.lower()
    w = 1.0
    for kw, groups in AUDIENCE_KEYWORDS.items():
        if kw in a and sk["professionGroup"] in groups:
            w *= 3.0
    m = re.findall(r"(\d{2})\s*[-–to]+\s*(\d{2})", a)
    if m:
        lo, hi = int(m[0][0]), int(m[0][1])
        band_lo = int(sk["ageBand"].split("-")[0].rstrip("+"))
        if lo - 5 <= band_lo <= hi:
            w *= 2.0
    if "budget" in a or "cheap" in a or "frugal" in a:
        w *= 2.0 if sk["economic"] == "Frugal" else 1.0
    if "premium" in a or "luxury" in a or "enterprise" in a:
        w *= 2.0 if sk["economic"] == "Premium" else 1.0
    if sk["country"] in audience_countries(audience):
        w *= 2.5
    return w


CONTRARIAN_FLOOR = 0.15
OUTSIDER_FLOOR = 0.05


def is_contrarian(sk: dict) -> bool:
    # Temperament only. Trust posture ("Burned before") and low agreeableness are separate dimensions the crowd
    # already samples; folding them in made ~46% of every crowd "contrarian" and skewed results sceptical.
    return sk["temperament"] == "Contrarian"


def is_outsider(sk: dict, audience: str) -> bool:
    return sk["tech"] in ("Laggard", "Late majority") and _audience_weight(sk, audience) <= 1.0


def least_used(library: list[dict], use_counts: dict[int, int], n: int) -> list[dict]:
    """People who have been in the fewest tests. Everyone new comes first; once fewer than 3n new people are left,
    those tested once join them, and so on, so the village cycles and nobody repeats until it is used up.
    The 3n margin leaves the sampler room for its floors and audience weighting."""
    by_uses: dict[int, list[dict]] = defaultdict(list)
    for p in library:
        by_uses[use_counts.get(p["id"], 0)].append(p)
    pool: list[dict] = []
    for k in sorted(by_uses):
        pool += by_uses[k]
        if len(pool) >= 3 * n:
            break
    return pool


def sample_crowd(library: list[dict], n: int, audience: str, seed: int,
                 use_counts: dict[int, int] | None = None, load: Callable[[list[int]], dict[int, dict]] | None = None) -> list[dict]:
    """Returns frontend-shaped personas with agent ids 0..n-1. With `use_counts` (persona id -> tests so far) the crowd comes from
    the least-tested people. `library` may hold only sampling attributes; `load` then fetches the full people drawn."""
    rng = random.Random(seed)
    if not library:
        return []
    n = min(n, len(library))
    uses = use_counts or {}
    if uses:
        library = least_used(library, uses, n)
    fewest = min(uses.get(p["id"], 0) for p in library)
    # Audience weight depends on four attributes only, so it is computed once per combination, not once per person.
    aud_w: dict[tuple, float] = {}
    weight: dict[int, float] = {}
    for p in library:
        sk = p["skeleton"]
        key = (sk["professionGroup"], sk["ageBand"], sk["economic"], sk["country"])
        if key not in aud_w:
            aud_w[key] = _audience_weight(sk, audience)
        # People tested more often than the rest of the pool are picked only when the floors need them.
        weight[p["id"]] = aud_w[key] * (0.1 if uses.get(p["id"], 0) > fewest else 1.0)
    chosen: list[dict] = []
    used: set[int] = set()

    def take(pool: list[dict], k: int):
        pool = [p for p in pool if p["id"] not in used]
        if not pool or k <= 0:
            return
        # Weighted sampling without replacement (Efraimidis-Spirakis): one pass, fast on a 40,000-person village.
        for p in heapq.nlargest(k, pool, key=lambda p: rng.random() ** (1.0 / weight[p["id"]])):
            used.add(p["id"]); chosen.append(p)

    # 1. Minimum coverage: every profession group, income band and ideology gets a floor.
    by_group = defaultdict(list); by_income = defaultdict(list); by_ideo = defaultdict(list)
    for p in library:
        by_group[p["skeleton"]["professionGroup"]].append(p); by_income[p["skeleton"]["income"]].append(p); by_ideo[p["skeleton"]["ideology"]].append(p)
    floor_g = max(3, int(n * 0.05))
    for g in PROFESSION_GROUPS:
        have = sum(1 for p in chosen if p["skeleton"]["professionGroup"] == g)
        take(by_group[g], floor_g - have)
    for inc in INCOME:
        have = sum(1 for p in chosen if p["skeleton"]["income"] == inc)
        take(by_income[inc], max(2, int(n * 0.04)) - have)
    for ideo in IDEOLOGY:
        have = sum(1 for p in chosen if p["skeleton"]["ideology"] == ideo)
        take(by_ideo[ideo], max(2, int(n * 0.06)) - have)
    # 2. Fill the rest audience-weighted.
    take(library, n - len(chosen))
    chosen = chosen[:n]

    # 3. Edge floors: guarantee at least 15% contrarians and 5% outsiders. These are floors, not extra draws:
    # if the natural sample already has enough, nothing changes. Swaps take from the most over-represented
    # profession group so the coverage floors from step 1 still hold.
    def enforce_floor(pred, floor: float) -> None:
        need = round(n * floor) - sum(1 for p in chosen if pred(p["skeleton"]))
        if need <= 0:
            return
        pool = [p for p in library if p["id"] not in used and pred(p["skeleton"])]
        rng.shuffle(pool)
        pool.sort(key=lambda p: uses.get(p["id"], 0))  # least-tested first, random within each
        for newp in pool[:need]:
            counts = defaultdict(int)
            for p in chosen:
                counts[p["skeleton"]["professionGroup"]] += 1
            victims = [i for i, p in enumerate(chosen)
                       if not is_contrarian(p["skeleton"]) and not is_outsider(p["skeleton"], audience)
                       and counts[p["skeleton"]["professionGroup"]] > floor_g]
            if not victims:
                return
            vi = max(victims, key=lambda i: (counts[chosen[i]["skeleton"]["professionGroup"]], rng.random()))
            used.discard(chosen[vi]["id"]); used.add(newp["id"]); chosen[vi] = newp

    enforce_floor(is_contrarian, CONTRARIAN_FLOOR)
    enforce_floor(lambda sk: is_outsider(sk, audience), OUTSIDER_FLOOR)
    rng.shuffle(chosen)

    full = load([p["id"] for p in chosen]) if load else {p["id"]: p for p in chosen}
    out = []
    for i, p in enumerate(chosen):
        mood = rng.choice(MOODS)
        f = full[p["id"]]
        out.append(to_frontend_persona(i, p["id"], f["skeleton"], f["profile"], mood))
    return out


def composition(personas: list[dict]) -> dict:
    """Sample composition summary for the methodology section."""
    def count(key, sub=None):
        d: dict[str, int] = defaultdict(int)
        for p in personas:
            v = p[key] if sub is None else p[sub][key]
            d[str(v)] += 1
        return dict(sorted(d.items(), key=lambda kv: -kv[1]))
    out = {
        "n": len(personas),
        "professionGroup": count("professionGroup"), "income": count("income"), "ideology": count("ideology"),
        "ageBand": count("ageBand"), "tech": count("tech"), "role": count("role"), "country": count("region"),
        "gdpTier": count("gdpTier", "extra"), "trust": count("trust", "extra"), "temperament": count("temperament", "extra"),
        "mood": count("mood"),
    }
    if personas and "lifeStage" in personas[0]["extra"]:  # version 2 people
        out |= {k: count(k, "extra") for k in ("lifeStage", "settlement", "adReceptivity")}
    return out
