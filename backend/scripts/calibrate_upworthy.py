"""Accuracy check against real behaviour: headline A/B tests from the Upworthy Research Archive (Matias et al. 2021,
Scientific Data; osf.io/jd64p, CC BY 4.0), where real readers' clicks picked a clear winner.

    uv run python -I scripts/calibrate_upworthy.py --csv data/upworthy/upworthy-archive-exploratory-packages-03.12.2020.csv

Each pair is two headlines tested on the same picture and teaser. Both go to the same crowd from the village (50 people
by default) and the crowd picks a winner; the hit rate is compared with 50% for guessing. Tests from 25 June 2013 to
10 January 2014 are left out, as the archive's authors advise (randomization problems).

--mode separate (default): each headline is judged on its own as an ad first impression, exactly as in a test
(stage1.first_impression), and click intent decides. Results go to data/calibration-upworthy.json.
--mode head-to-head: each person sees both headlines as story links in their feed (half of them with the real winner
first) and says how likely they'd click each and which one they would; the share of picks decides. Results go to
data/calibration-upworthy-h2h.json. --fresh leaves out pairs tested before, so a new mode isn't judged on old pairs.
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
from app.llm import BudgetExceeded, Meter, llm  # noqa: E402
from app.personas.frame import persona_card  # noqa: E402
from app.personas.sampler import sample_crowd  # noqa: E402

NEEDED = ("clickability_test_id", "created_at", "headline", "eyecatcher_id", "impressions", "clicks")
BAD_FROM, BAD_TO = datetime(2013, 6, 25), datetime(2014, 1, 11)  # the archive's correction: omit these from causal analysis
CLICK_VALUE = {"Yes": 1.0, "Maybe": 0.5, "No": 0.0}
RESULTS = {"separate": "calibration-upworthy.json", "head-to-head": "calibration-upworthy-h2h.json"}
COST_PER_CALL = {"separate": 0.00027, "head-to-head": 0.00015}  # Haiku 5.5, measured on live calls

_CHANCE = "0 = you'd scroll right past it, 5 = 50/50, 10 = you'd definitely click"
H2H_SCHEMA = {
    "type": "object",
    "properties": {
        "first_chance": {"type": "number", "description": f"0-10: how likely you'd click the first story. {_CHANCE}"},
        "second_chance": {"type": "number", "description": f"0-10: how likely you'd click the second story. {_CHANCE}"},
        "pick": {"type": "string", "enum": ["first", "second", "neither"], "description": "The one you'd actually click, if either"},
    },
    "required": ["first_chance", "second_chance", "pick"],
    "additionalProperties": False,
}
H2H_SYSTEM = ("You are role-playing one specific real person scrolling their social feed. Stay fully in character: your country, age, "
              "job, interests, politics, mood and habits decide what catches your eye; don't judge like an editor or a marketer. Two "
              "story links show up near each other (headlines only; the pictures haven't loaded). Most people scroll past most stories, "
              "so low numbers are normal. Say how likely you'd be to click each, then which one you'd actually click, if either. JSON only.")


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


async def judge_arm(headline: str, crowd: list[dict], seed: int, meter: Meter, audience: str) -> dict:
    """One headline, shown to the crowd as a story link they come across; returns click intent and stop rate."""
    stim = {"type": "creative", "title": headline, "brief": f"A story link with a picture. Headline: \"{headline}\"", "targetAudience": audience}
    system = stage1_system(stim)

    async def one(a: dict) -> dict:
        # Each person's stream depends on the pair and the person only, so both headlines meet them in the same place.
        return await first_impression(a, "creative", system, [], meter, random.Random(f"{seed}:{a['id']}"))
    first = [await one(crowd[0])]  # writes the shared prompt to the cache once
    vs = first + list(await asyncio.gather(*(one(a) for a in crowd[1:])))
    return {"click": sum(CLICK_VALUE.get(v.get("would_click", "No"), 0.0) for v in vs) / len(vs),
            "clickYes": sum(v.get("would_click") == "Yes" for v in vs) / len(vs),
            "stop": sum(stop_pct(v) for v in vs) / len(vs) / 100, "score": sum(v["score"] for v in vs) / len(vs)}


async def head_to_head(p: dict, crowd: list[dict], meter: Meter) -> dict:
    """Both headlines in front of each person at once; every other person sees the real winner first, so a preference for
    whichever comes first cancels out. Returns picks and average click chances for the winner and the loser."""
    w, l = p["winner"]["headline"], p["loser"]["headline"]

    async def one(i: int, a: dict) -> dict:
        winner_first = i % 2 == 0
        first, second = (w, l) if winner_first else (l, w)
        user = (f"{persona_card(a['_sk'], a['_profile'], a['mood'])}\n\nTwo stories in your feed:\nFIRST: \"{first}\"\nSECOND: \"{second}\"\n\nJSON only.")
        out = await llm().json(role="crowd", system=H2H_SYSTEM, user=user, schema=H2H_SCHEMA, meter=meter,
                               fake=lambda: {"first_chance": 3, "second_chance": 3, "pick": "neither"}, max_tokens=200)
        fc, sc = (float(max(0, min(10, out.get(k, 0)))) for k in ("first_chance", "second_chance"))
        pick = out.get("pick", "neither")
        chosen = "neither" if pick not in ("first", "second") else ("winner" if (pick == "first") == winner_first else "loser")
        return {"w": fc if winner_first else sc, "l": sc if winner_first else fc, "pick": chosen, "first": pick == "first"}
    vs = await asyncio.gather(*(one(i, a) for i, a in enumerate(crowd)))
    n = len(vs)
    return {"winnerPicks": sum(v["pick"] == "winner" for v in vs), "loserPicks": sum(v["pick"] == "loser" for v in vs),
            "neither": sum(v["pick"] == "neither" for v in vs), "firstPicks": sum(v["first"] for v in vs),
            "winnerChance": round(sum(v["w"] for v in vs) / n, 2), "loserChance": round(sum(v["l"] for v in vs) / n, 2)}


def tested_before(folder: Path) -> set[str]:
    """Test ids of pairs in earlier results files."""
    out: set[str] = set()
    for name in RESULTS.values():
        f = folder / name
        if f.exists():
            out |= {p["test"] for p in json.loads(f.read_text(encoding="utf-8"))["pairs"]}
    return out


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
    ap.add_argument("--dry-run", action="store_true", help="list the pairs and the estimated cost without calling the API")
    # Upworthy's tests ran on its (mostly American) readers, so the crowd leans US the way a test's audience would.
    ap.add_argument("--audience", default="US readers of social news stories")
    ap.add_argument("--mode", choices=list(RESULTS), default="separate")
    ap.add_argument("--fresh", action="store_true", help="leave out pairs tested in earlier results files")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    pool = headline_pairs(a.csv, a.min_impressions, a.min_z, a.min_lift)
    if a.fresh:
        seen = tested_before(settings.db_path.parent)
        pool = [p for p in pool if p["test"] not in seen]
    pairs = random.Random(a.seed).sample(pool, min(a.pairs, len(pool)))
    calls = len(pairs) * a.crowd * (2 if a.mode == "separate" else 1)
    print(f"{len(pool)} clear headline pairs available; testing {len(pairs)} {a.mode} on crowds of {a.crowd} "
          f"(provider {settings.effective_provider}, model {settings.model_for('crowd')}; estimated ${calls * COST_PER_CALL[a.mode]:.2f})", flush=True)
    if a.dry_run:
        for i, p in enumerate(pairs):
            print(f"{i + 1:2}. real lift +{p['lift']:.0%} (z {p['z']}, {p['winner']['impressions']:,} and {p['loser']['impressions']:,} viewers)\n"
                  f"      W: {p['winner']['headline'][:110]}\n      L: {p['loser']['headline'][:110]}")
        return
    lib = village()
    meter = Meter(budget_usd=a.budget)
    results, hits = [], 0.0
    for i, p in enumerate(pairs):
        seed = a.seed * 1000 + i
        crowd = sample_crowd(lib, a.crowd, a.audience, seed, load=db.personas_by_ids)
        people = db.personas_by_ids([c["personaId"] for c in crowd])
        for c in crowd:
            c["_sk"], c["_profile"] = people[c["personaId"]]["skeleton"], people[c["personaId"]]["profile"]
        try:
            if a.mode == "separate":  # separate calls with no memory, so neither headline is seen "second"
                w, l = await asyncio.gather(judge_arm(p["winner"]["headline"], crowd, seed, meter, a.audience), judge_arm(p["loser"]["headline"], crowd, seed, meter, a.audience))
                crowd_says = {"winner": w, "loser": l}
                margin, line = w["click"] - l["click"], f"crowd click {w['click']:.2f} vs {l['click']:.2f}"
            else:
                h = await head_to_head(p, crowd, meter)
                crowd_says = h
                # Picks decide; average click chances break a tie in picks.
                margin = (h["winnerPicks"] - h["loserPicks"]) or (h["winnerChance"] - h["loserChance"])
                line = (f"picks {h['winnerPicks']} vs {h['loserPicks']} ({h['neither']} neither) | chance {h['winnerChance']:.1f} vs {h['loserChance']:.1f}"
                        f" | first picked {h['firstPicks']}")
        except BudgetExceeded as e:
            print(f"stopping early: {e}", flush=True)
            break
        hit = 1.0 if margin > 0 else 0.5 if margin == 0 else 0.0
        hits += hit
        results.append({**p, "crowd": crowd_says, "hit": hit})
        print(f"{i + 1:2}. {'HIT ' if hit == 1 else 'tie ' if hit == 0.5 else 'miss'} real lift +{p['lift']:.0%} (z {p['z']}) | {line} | ${meter.cost_usd:.3f}\n"
              f"      W: {p['winner']['headline'][:110]}\n      L: {p['loser']['headline'][:110]}", flush=True)
    n = len(results)
    if not n:
        sys.exit("no pairs tested; try lower --min-z or --min-lift")
    summary = {"mode": a.mode, "pairs": n, "hits": hits, "hitRate": round(hits / n, 3), "pGuessing": round(binomial_p(hits, n), 4),
               "crowd": a.crowd, "audience": a.audience, "costUsd": round(meter.cost_usd, 3), "model": settings.model_for("crowd"), "csv": a.csv.name}
    if a.mode == "head-to-head":
        picked = sum(r["crowd"]["winnerPicks"] + r["crowd"]["loserPicks"] for r in results)
        summary |= {"winnerShareOfPicks": round(sum(r["crowd"]["winnerPicks"] for r in results) / max(1, picked), 3),
                    "firstShareOfPicks": round(sum(r["crowd"]["firstPicks"] for r in results) / max(1, picked), 3)}
    out = settings.db_path.parent / RESULTS[a.mode]
    out.write_text(json.dumps({"summary": summary, "pairs": results}, indent=1, ensure_ascii=False), encoding="utf-8")
    extra = (f" | real winners got {summary['winnerShareOfPicks']:.0%} of the crowd's picks; the first-shown headline {summary['firstShareOfPicks']:.0%}"
             if a.mode == "head-to-head" else "")
    print(f"\nhit rate {hits:g}/{n} = {summary['hitRate']:.0%} (guessing: 50%; chance of doing this well by guessing {summary['pGuessing']:.3f}){extra} "
          f"| cost ${meter.cost_usd:.3f} | saved to {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
