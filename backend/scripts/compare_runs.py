"""Compare two runs side by side: headline numbers, crowd composition, score distribution, segments, objections.

    uv run python scripts/compare_runs.py run_A run_B
"""
from __future__ import annotations

import collections
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db  # noqa: E402


def agents(rid: str) -> list[dict]:
    return [a for a in db.get_run_agents(rid) if a.get("verdict")]


def final(a: dict) -> float:
    return a["finalScore"] if a.get("finalScore") is not None else a["verdict"]["score"]


def share(ag: list[dict], pred) -> str:
    return f"{sum(1 for a in ag if pred(a)) / max(1, len(ag)):.0%}"


def row(label: str, a, b) -> None:
    print(f"  {label:<34}{str(a):>14}{str(b):>14}")


def main() -> None:
    ra, rb = sys.argv[1], sys.argv[2]
    A, B = agents(ra), agents(rb)
    sa, sb = db.get_scorecard(ra) or {}, db.get_scorecard(rb) or {}
    print(f"{'':36}{ra:>14}{rb:>14}")

    print("HEADLINE")
    row("overall score", sa.get("overall"), sb.get("overall"))
    row("crowd mean (final)", round(statistics.mean(map(final, A)), 2), round(statistics.mean(map(final, B)), 2))
    row("first-impression mean", round(statistics.mean(a["verdict"]["score"] for a in A), 2), round(statistics.mean(a["verdict"]["score"] for a in B), 2))
    row("research-team score", sa.get("analystScore"), sb.get("analystScore"))
    row("std-dev (polarization)", sa.get("polarization"), sb.get("polarization"))
    row("shift during discussion", sa.get("shift"), sb.get("shift"))
    ia, ib = sa.get("intentSplit", {}), sb.get("intentSplit", {})
    row("intent buy / maybe / no", f"{ia.get('buy')}/{ia.get('maybe')}/{ia.get('no')}", f"{ib.get('buy')}/{ib.get('maybe')}/{ib.get('no')}")
    row("mind changes", sa.get("research", {}).get("mindChanges"), sb.get("research", {}).get("mindChanges"))
    row("verdict", "", "")
    print(f"    A: {sa.get('verdict')}\n    B: {sb.get('verdict')}")
    row("cost", f"${db.get_run(ra)['cost_usd']:.3f}", f"${db.get_run(rb)['cost_usd']:.3f}")

    print("CROWD COMPOSITION")
    row("contrarian temperament", share(A, lambda a: a["extra"]["temperament"] == "Contrarian"), share(B, lambda a: a["extra"]["temperament"] == "Contrarian"))
    row("burned before", share(A, lambda a: a["extra"]["trust"] == "Burned before"), share(B, lambda a: a["extra"]["trust"] == "Burned before"))
    row("sceptical of marketing", share(A, lambda a: a["extra"]["trust"] == "Sceptical of marketing"), share(B, lambda a: a["extra"]["trust"] == "Sceptical of marketing"))
    row("default-trusting", share(A, lambda a: a["extra"]["trust"] == "Default-trusting"), share(B, lambda a: a["extra"]["trust"] == "Default-trusting"))
    row("cynical or contrarian", share(A, lambda a: a["extra"]["temperament"] in ("Cynical", "Contrarian")), share(B, lambda a: a["extra"]["temperament"] in ("Cynical", "Contrarian")))
    row("engineering", share(A, lambda a: a["professionGroup"] == "Engineering"), share(B, lambda a: a["professionGroup"] == "Engineering"))
    row("distinct names", len({a["name"] for a in A}), len({a["name"] for a in B}))

    print("SCORE DISTRIBUTION (final, whole points)")
    ha = collections.Counter(int(final(a)) for a in A); hb = collections.Counter(int(final(a)) for a in B)
    for k in range(0, 11):
        if ha.get(k) or hb.get(k):
            row(f"{k}", ha.get(k, 0), hb.get(k, 0))

    print("MEAN BY MOTIVATION / TEMPERAMENT / TRUST (first impression)")
    for dim, key in (("motivation", lambda a: a["extra"].get("motivation") or "?"), ("temperament", lambda a: a["extra"]["temperament"]), ("trust", lambda a: a["extra"]["trust"])):
        groups = sorted({key(a) for a in A + B})
        for g in groups:
            va = [a["verdict"]["score"] for a in A if key(a) == g]; vb = [a["verdict"]["score"] for a in B if key(a) == g]
            row(f"{dim}: {g}", f"{statistics.mean(va):.1f} n={len(va)}" if va else "-", f"{statistics.mean(vb):.1f} n={len(vb)}" if vb else "-")

    print("TOP OBJECTIONS")
    for label, sc in (("A", sa), ("B", sb)):
        for o in sc.get("objections", [])[:4]:
            print(f"    {label}: {o['count']:>3}x  {o['text']}")


if __name__ == "__main__":
    main()
