"""Draw a crowd for one run from the library: stratified, audience-weighted, with forced edges,
reproducible by seed. Also assigns each agent a mood for today."""
from __future__ import annotations

import random
import re
from collections import defaultdict

from .frame import INCOME, IDEOLOGY, MOODS, PROFESSION_GROUPS, to_frontend_persona

AUDIENCE_KEYWORDS = {
    "developer": ("Engineering",), "engineer": ("Engineering",), "software": ("Engineering",), "designer": ("Design",),
    "marketer": ("Marketing",), "marketing": ("Marketing",), "founder": ("Executives",), "executive": ("Executives",), "ceo": ("Executives",),
    "student": ("Students",), "students": ("Students",), "nurse": ("Healthcare",), "doctor": ("Healthcare",), "teacher": ("Education",),
    "finance": ("Finance",), "procurement": ("Finance",), "retail": ("Retail & Service",), "small business": ("Executives", "Retail & Service"),
    "operations": ("Operations",), "productivity": ("Executives", "Marketing", "Engineering"),
}


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
    for c in ("india", "us", "uk", "germany", "brazil", "nigeria", "japan", "europe"):
        if c in a and c in sk["country"].lower():
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


def sample_crowd(library: list[dict], n: int, audience: str, seed: int) -> list[dict]:
    """Returns frontend-shaped personas with agent ids 0..n-1."""
    rng = random.Random(seed)
    if not library:
        return []
    n = min(n, len(library))
    chosen: list[dict] = []
    used: set[int] = set()

    def take(pool: list[dict], k: int, weighted: bool = True):
        pool = [p for p in pool if p["id"] not in used]
        if not pool or k <= 0:
            return
        if weighted:
            ws = [_audience_weight(p["skeleton"], audience) for p in pool]
            picks = []
            # weighted sampling without replacement
            idx = list(range(len(pool)))
            for _ in range(min(k, len(pool))):
                tot = sum(ws[i] for i in idx)
                r = rng.random() * tot
                acc = 0.0
                for j, i in enumerate(idx):
                    acc += ws[i]
                    if r <= acc:
                        picks.append(pool[i]); idx.pop(j); break
        else:
            picks = rng.sample(pool, min(k, len(pool)))
        for p in picks:
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

    out = []
    for i, p in enumerate(chosen):
        mood = rng.choice(MOODS)
        out.append(to_frontend_persona(i, p["id"], p["skeleton"], p["profile"], mood))
    return out


def composition(personas: list[dict]) -> dict:
    """Sample composition summary for the methodology section."""
    def count(key, sub=None):
        d: dict[str, int] = defaultdict(int)
        for p in personas:
            v = p[key] if sub is None else p[sub][key]
            d[str(v)] += 1
        return dict(sorted(d.items(), key=lambda kv: -kv[1]))
    return {
        "n": len(personas),
        "professionGroup": count("professionGroup"), "income": count("income"), "ideology": count("ideology"),
        "ageBand": count("ageBand"), "tech": count("tech"), "role": count("role"), "country": count("region"),
        "gdpTier": count("gdpTier", "extra"), "trust": count("trust", "extra"), "temperament": count("temperament", "extra"),
        "mood": count("mood"),
    }
