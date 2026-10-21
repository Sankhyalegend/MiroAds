"""Count objection themes by keyword across runs, independent of the report's clustering, to check cluster labels.

    uv run python scripts/objection_themes.py run_A [run_B ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db  # noqa: E402

THEMES = {
    "price / value": r"\$|price|pric|cost|expensive|money|afford|worth|cheap|₹|€|£|budget",
    "app / setup / account": r"\bapp\b|setup|set up|account|install|sync|pair|bluetooth|wifi|wi-fi|connect|subscription|cloud",
    "proof / reviews / durability": r"proof|evidence|review|test|lasts?|durab|reliab|track record|year|long[- ]term|spec|lumen|kelvin",
    "who makes it / trust": r"who (makes|made|is behind)|brand|company|maker|unknown|heard of|trust",
    "unclear / what it does": r"unclear|what (it|does)|don'?t (get|understand)|confus|tagline|vague|mood|vibe",
    "not for me / no need": r"not for me|don'?t need|no need|already have|problem i|my life|irrelevant",
    "warranty / returns": r"warrant|return|refund|guarantee",
}


def main() -> None:
    rids = sys.argv[1:]
    print(f"{'theme (share of stage-1 objections)':<40}" + "".join(f"{r:>18}" for r in rids))
    data = {}
    for r in rids:
        objs = [a["verdict"]["objection"] for a in db.get_run_agents(r) if a.get("verdict")]
        data[r] = objs
    for name, pat in THEMES.items():
        rx = re.compile(pat, re.I)
        print(f"{name:<40}" + "".join(f"{sum(1 for o in data[r] if rx.search(o)) / max(1, len(data[r])):>18.0%}" for r in rids))
    for r in rids:
        sc = db.get_scorecard(r) or {}
        print(f"\n{r} report clusters (label / size), vs how many members actually share the label's theme:")
        for o in sc.get("objections", [])[:3]:
            lab = o["text"]
            hit = [t for t, pat in THEMES.items() if re.search(pat, lab, re.I)]
            print(f"   {o['count']:>3}x  {lab}   [theme: {', '.join(hit) or 'none'}]")


if __name__ == "__main__":
    main()
