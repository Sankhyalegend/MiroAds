"""Check crowd sampling against the full library: speed, composition, quotas, seed reproducibility. No API calls.

    uv run python scripts/check_sampling.py [crowd_size]
"""
from __future__ import annotations

import collections
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db  # noqa: E402
from app.personas.sampler import is_contrarian, is_outsider, sample_crowd  # noqa: E402


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    t = time.time(); lib = db.all_personas(); load = time.time() - t
    by_id = {p["id"]: p for p in lib}
    audiences = {
        "developers": "Remote software developers 25-40, students, productivity enthusiasts",
        "general": "",
        "budget India": "budget-conscious shoppers in India",
    }
    print(f"library {len(lib)} loaded in {load:.2f}s")
    for label, aud in audiences.items():
        t = time.time(); crowd = sample_crowd(lib, n, aud, seed=42); dt = time.time() - t
        groups = collections.Counter(a["professionGroup"] for a in crowd)
        countries = collections.Counter(a["region"] for a in crowd)
        contr = sum(1 for a in crowd if is_contrarian(by_id[a["personaId"]]["skeleton"]))
        outs = sum(1 for a in crowd if is_outsider(by_id[a["personaId"]]["skeleton"], aud))
        burned = sum(1 for a in crowd if a["extra"]["trust"] == "Burned before")
        names = len({a["name"] for a in crowd})
        print(f"\n[{label}] sampled {len(crowd)} in {dt:.2f}s  distinct names {names}  contrarians {contr / len(crowd):.0%}  "
              f"outsiders {outs / len(crowd):.0%}  burned-before {burned / len(crowd):.0%}  countries {len(countries)}")
        print("  groups: " + ", ".join(f"{k} {v}" for k, v in groups.most_common()))
        print("  top countries: " + ", ".join(f"{k} {v}" for k, v in countries.most_common(6)))
    a = [x["personaId"] for x in sample_crowd(lib, n, audiences["developers"], seed=42)]
    b = [x["personaId"] for x in sample_crowd(lib, n, audiences["developers"], seed=42)]
    c = [x["personaId"] for x in sample_crowd(lib, n, audiences["developers"], seed=43)]
    print(f"\nsame seed reproduces crowd: {a == b}   different seed overlap: {len(set(a) & set(c)) / n:.0%}")


if __name__ == "__main__":
    main()
