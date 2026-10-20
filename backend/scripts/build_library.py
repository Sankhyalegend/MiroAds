"""Build (or extend) the persona library.

    uv run python scripts/build_library.py --n 10000 --seed 1
    uv run python scripts/build_library.py --n 500 --budget 1.0     # small test

Seeds are deterministic: seed k always yields the same skeleton, so the library can be rebuilt or extended safely.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import Meter  # noqa: E402
from app.personas.generate import dedupe_names, generate_batch, overused_names  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--budget", type=float, default=6.0, help="USD cap for this build")
    ap.add_argument("--chunk", type=int, default=200)
    ap.add_argument("--redo-fallbacks", action="store_true", help="delete personas whose LLM call failed (template texture) and regenerate them")
    ap.add_argument("--dedupe-names", action="store_true", help="after generating, rename personas whose name is already taken (tiny call each)")
    a = ap.parse_args()

    if a.redo_fallbacks:
        bad = [r["id"] for r in db.q("SELECT id, profile FROM personas") if '"_error"' in r["profile"]]
        for i in range(0, len(bad), 500):
            db.x(f"DELETE FROM personas WHERE id IN ({','.join('?' * len(bad[i:i + 500]))})", bad[i:i + 500])
        print(f"removed {len(bad)} fallback personas")

    existing = {r["seed"] for r in db.q("SELECT seed FROM personas")}
    seeds = [s for s in range(a.seed, a.seed + a.n) if s not in existing]
    print(f"provider={settings.effective_provider} model={settings.model_for('crowd')} existing={len(existing)} to_generate={len(seeds)}")
    meter = Meter(budget_usd=a.budget)
    t0 = time.time()
    total = 0
    for i in range(0, len(seeds), a.chunk):
        if meter.cost_usd >= a.budget:
            print(f"budget ${a.budget:.2f} reached; stopping before chunk {i // a.chunk + 1}. Re-run to continue.")
            break
        chunk = seeds[i:i + a.chunk]
        avoid = overused_names()  # refreshed per chunk so later chunks steer away from earlier repeats
        n = await generate_batch(chunk, meter, avoid_names=avoid)
        total += n
        print(f"stored {total}/{len(seeds)}  library {db.persona_count()}  cost ${meter.cost_usd:.3f}  {time.time() - t0:.0f}s", flush=True)
    if a.dedupe_names:
        renamed = await dedupe_names(meter)
        print(f"renamed {renamed} duplicate names  cost ${meter.cost_usd:.3f}", flush=True)
    print(f"done: library now has {db.persona_count()} personas. cost ${meter.cost_usd:.3f}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
