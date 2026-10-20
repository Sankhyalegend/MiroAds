"""Summarize the persona library: size, seed range, fallbacks, and the spread of key dimensions.

    uv run python scripts/library_stats.py
"""
from __future__ import annotations

import collections
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db  # noqa: E402

LENS_KEYWORDS = ("warrant", "return", "price", "cost", "spec", "review", "look", "design", "fun", "status", "friend", "health", "feel")


def main() -> None:
    lib = db.all_personas()
    if not lib:
        print("library is empty"); return
    seeds = [p["skeleton"]["seed"] for p in lib]
    real = [p for p in lib if "_error" not in p["profile"]]
    print(f"personas: {len(lib)}  seeds {min(seeds)}-{max(seeds)}  real: {len(real)}  fallbacks: {len(lib) - len(real)}")
    if not real:
        return
    print(f"median backstory words: {statistics.median(len(p['profile']['backstory'].split()) for p in real):.0f}")
    names = collections.Counter(p["profile"]["name"] for p in real)
    print(f"distinct names: {len(names)} / {len(real)}  (most repeated: {names.most_common(3)})")
    n = len(real)
    kw = collections.Counter()
    for p in real:
        t = (p["profile"]["evaluation_lens"] + " " + p["profile"]["overvalues"]).lower()
        for k in LENS_KEYWORDS:
            if k in t:
                kw[k] += 1
    print("lens keywords: " + ", ".join(f"{k} {v / n:.0%}" for k, v in kw.most_common()))
    for dim in ("professionGroup", "gdpTier", "income", "ideology", "motivation", "trust", "temperament"):
        c = collections.Counter(p["skeleton"].get(dim, "?") for p in real)
        print(f"{dim}: " + ", ".join(f"{k} {v / n:.0%}" for k, v in c.most_common()))
    print(f"countries: {len({p['skeleton']['country'] for p in real})}")


if __name__ == "__main__":
    main()
