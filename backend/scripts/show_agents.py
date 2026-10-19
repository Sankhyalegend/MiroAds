"""Print a few agents' reasoning and actions from a run, chosen to span the score range and segments.

    uv run python scripts/show_agents.py run_xxx [count]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db  # noqa: E402


def main() -> None:
    rid = sys.argv[1]
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    agents = [a for a in db.get_run_agents(rid) if a.get("verdict")]
    if not agents:
        print("no agents with verdicts"); return
    agents.sort(key=lambda a: a["verdict"]["score"])
    # spread across the score range, prefer agents who acted
    picks = []
    for i in range(k):
        idx = round(i * (len(agents) - 1) / max(1, k - 1))
        window = agents[max(0, idx - 10): idx + 10]
        window.sort(key=lambda a: -len(a.get("actions", [])))
        for a in window:
            if a not in picks:
                picks.append(a); break
    for a in picks:
        v = a["verdict"]; ex = a.get("extra", {})
        print("=" * 100)
        print(f"{a['name']} · {a['profession']} · {a['region']} ({ex.get('gdpTier')}-income country, {a['income']} income) · {a['ideology']}, {a['economic']}, {a['tech']} · {ex.get('trust')} · {ex.get('heuristic')} · mood {a.get('mood')}")
        print(f"FIRST IMPRESSION {v['score']:.1f}/10 · {v['intent']} · confidence {v.get('confidence')}")
        print(f"  reaction : {v['reaction']}")
        print(f"  reasoning: {v.get('reasoning')}")
        print(f"  objection: {v['objection']}   | missing: {v['missing']}")
        print(f"  on price : {v.get('price_reaction')}")
        fs = a.get("finalScore")
        if fs is not None and abs(fs - v["score"]) >= 0.05:
            print(f"  FINAL {fs:.1f} (moved {fs - v['score']:+.1f} during discussion)")
        for act in a.get("actions", []):
            line = f"  r{act['round']} {act['action']:<7}"
            if act.get("target"): line += f" -> post {act['target']}"
            if act.get("text"): line += f' : "{act["text"]}"'
            if act.get("why"): line += f"   [{act['why']}]"
            print(line)


if __name__ == "__main__":
    main()
