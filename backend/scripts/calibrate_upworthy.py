"""Accuracy check against real behaviour: headline A/B tests from the Upworthy Research Archive (Matias et al. 2021,
Scientific Data; osf.io/jd64p, CC BY 4.0), where real readers' clicks picked a clear winner.

    uv run python -I scripts/calibrate_upworthy.py --csv data/upworthy/upworthy-archive-exploratory-packages-03.12.2020.csv

Each pair is two headlines tested on the same picture and teaser. Both go to the same crowd from the village (50 people
by default) as an ad first impression, exactly as in a test (stage1.first_impression), and the crowd's click intent
picks a winner. The hit rate is compared with 50% for guessing. Tests from 25 June 2013 to 10 January 2014 are left out,
as the archive's authors advise (randomization problems). Results go to data/calibration-upworthy.json.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import html
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402
from app.engine.judge import stop_pct  # noqa: E402
from app.engine.runner import village  # noqa: E402
from app.engine.stage1 import first_impression, stage1_system  # noqa: E402
from app.llm import BudgetExceeded, Meter  # noqa: E402
from app.personas.sampler import sample_crowd  # noqa: E402

NEEDED = ("clickability_test_id", "created_at", "headline", "eyecatcher_id", "impressions", "clicks")
BAD_FROM, BAD_TO = datetime(2013, 6, 25), datetime(2014, 1, 11)  # the archive's correction: omit these from causal analysis
CLICK_VALUE = {"Yes": 1.0, "Maybe": 0.5, "No": 0.0}


def z_two_proportions(c1: int, n1: int, c2: int, n2: int) -> float:
    p = (c1 + c2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) or 1e-9
    return (c1 / n1 - c2 / n2) / se


def headline_pairs(path: Path, min_impressions: int, min_z: float, min_lift: float) -> list[dict]:
    """Per test: among packages sharing a picture and teaser (so only the headline differs), the best and the worst by
    click rate, kept when the real winner is clear."""
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    missing = [c for c in NEEDED if rows and c not in rows[0]]
    if missing:
        sys.exit(f"{path.name} lacks columns {missing}; has {list(rows[0])[:20]}")
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        try:
            created = datetime.fromisoformat(r["created_at"][:19])
            imp, clk = int(float(r["impressions"])), int(float(r["clicks"]))
        except ValueError:
            continue
        if BAD_FROM <= created < BAD_TO or imp < min_impressions or not r["headline"].strip():
            continue
        groups[(r["clickability_test_id"], r["eyecatcher_id"], r.get("lede", ""))].append(
            {"headline": html.unescape(r["headline"]).strip(), "impressions": imp, "clicks": clk, "ctr": clk / imp})
    pairs = []
    for (test, *_), pk in groups.items():
        uniq = list({p["headline"]: p for p in pk}.values())
        if len(uniq) < 2:
            continue
        hi, lo = max(uniq, key=lambda p: p["ctr"]), min(uniq, key=lambda p: p["ctr"])
        if lo["ctr"] <= 0:
            continue
        z = z_two_proportions(hi["clicks"], hi["impressions"], lo["clicks"], lo["impressions"])
        if z >= min_z and hi["ctr"] / lo["ctr"] - 1 >= min_lift:
            pairs.append({"test": test, "winner": hi, "loser": lo, "z": round(z, 1), "lift": round(hi["ctr"] / lo["ctr"] - 1, 2)})
    return pairs


async def judge_arm(headline: str, crowd: list[dict], seed: int, meter: Meter) -> dict:
    """One headline, shown to the crowd as a story link they come across; returns click intent and stop rate."""
    stim = {"type": "creative", "title": headline, "brief": f"A story link with a picture. Headline: \"{headline}\"", "targetAudience": "general public"}
    system = stage1_system(stim)

    async def one(a: dict) -> dict:
        # Each person's stream depends on the pair and the person only, so both headlines meet them in the same place.
        return await first_impression(a, "creative", system, [], meter, random.Random(f"{seed}:{a['id']}"))
    first = [await one(crowd[0])]  # writes the shared prompt to the cache once
    vs = first + list(await asyncio.gather(*(one(a) for a in crowd[1:])))
    return {"click": sum(CLICK_VALUE.get(v.get("would_click", "No"), 0.0) for v in vs) / len(vs),
            "clickYes": sum(v.get("would_click") == "Yes" for v in vs) / len(vs),
            "stop": sum(stop_pct(v) for v in vs) / len(vs) / 100, "score": sum(v["score"] for v in vs) / len(vs)}


def binomial_p(hits: float, n: int) -> float:
    """One-sided chance of at least this many hits by guessing (ties count half, so hits is rounded down)."""
    k = math.floor(hits)
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--pairs", type=int, default=20)
    ap.add_argument("--crowd", type=int, default=50)
    ap.add_argument("--min-impressions", type=int, default=2000)
    ap.add_argument("--min-z", type=float, default=3.3, help="how clear the real winner must be (3.3 is p < 0.001)")
    ap.add_argument("--min-lift", type=float, default=0.3, help="winner's click rate at least this much higher (0.3 = 30%)")
    ap.add_argument("--budget", type=float, default=1.5)
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    pool = headline_pairs(a.csv, a.min_impressions, a.min_z, a.min_lift)
    pairs = random.Random(a.seed).sample(pool, min(a.pairs, len(pool)))
    print(f"{len(pool)} clear headline pairs in the archive; testing {len(pairs)} on crowds of {a.crowd} "
          f"(provider {settings.effective_provider}, model {settings.model_for('crowd')})", flush=True)
    lib = village()
    meter = Meter(budget_usd=a.budget)
    results, hits = [], 0.0
    for i, p in enumerate(pairs):
        seed = a.seed * 1000 + i
        crowd = sample_crowd(lib, a.crowd, "", seed, load=db.personas_by_ids)
        people = db.personas_by_ids([c["personaId"] for c in crowd])
        for c in crowd:
            c["_sk"], c["_profile"] = people[c["personaId"]]["skeleton"], people[c["personaId"]]["profile"]
        # Separate calls with no memory, so neither headline is seen "second".
        try:
            w, l = await asyncio.gather(judge_arm(p["winner"]["headline"], crowd, seed, meter), judge_arm(p["loser"]["headline"], crowd, seed, meter))
        except BudgetExceeded as e:
            print(f"stopping early: {e}", flush=True)
            break
        hit = 1.0 if w["click"] > l["click"] else 0.5 if w["click"] == l["click"] else 0.0
        hits += hit
        results.append({**p, "crowd": {"winner": w, "loser": l}, "hit": hit})
        print(f"{i + 1:2}. {'HIT ' if hit == 1 else 'tie ' if hit == 0.5 else 'miss'} real lift +{p['lift']:.0%} (z {p['z']}) | crowd click "
              f"{w['click']:.2f} vs {l['click']:.2f} | ${meter.cost_usd:.3f}\n      W: {p['winner']['headline'][:110]}\n      L: {p['loser']['headline'][:110]}", flush=True)
    n = len(results)
    if not n:
        sys.exit("no pairs tested; try lower --min-z or --min-lift")
    lifts = [r["lift"] for r in results]
    crowd_lifts = [r["crowd"]["winner"]["click"] - r["crowd"]["loser"]["click"] for r in results]
    summary = {"pairs": n, "hits": hits, "hitRate": round(hits / n, 3) if n else None, "pGuessing": round(binomial_p(hits, n), 4) if n else None,
               "crowd": a.crowd, "costUsd": round(meter.cost_usd, 3), "model": settings.model_for("crowd"), "csv": a.csv.name,
               "meanCrowdLift": round(sum(crowd_lifts) / n, 3) if n else None, "meanRealLift": round(sum(lifts) / n, 3) if n else None}
    out = settings.db_path.parent / "calibration-upworthy.json"
    out.write_text(json.dumps({"summary": summary, "pairs": results}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nhit rate {hits:g}/{n} = {summary['hitRate']:.0%} (guessing: 50%; chance of doing this well by guessing {summary['pGuessing']:.3f}) "
          f"| cost ${meter.cost_usd:.3f} | saved to {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
