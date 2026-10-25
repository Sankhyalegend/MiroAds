"""Build the village with the Message Batches API: half the price of live calls; a batch usually finishes within an hour.

    uv run python scripts/build_library_batch.py --n 40000 --seed 100001 --dedupe-names

First a small live pilot writes a few people at full price, to check the output and measure the cost per person. Batches then
go one at a time, each measured before the next is sent, and the build stops if the projected total is over --budget.
Running the same command again resumes: batches already submitted are collected (results are kept 29 days; ids are saved
in data/batches.json) and seeds already in the library are skipped. Seeds are deterministic, so a --seed range always yields
the same people. Requests that fail are stored with template texture marked _error; rebuild those live with
build_library.py --redo-fallbacks.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import Anthropic, APIConnectionError, APITimeoutError, InternalServerError  # noqa: E402

from app import db  # noqa: E402
from app.config import PRICING, settings  # noqa: E402
from app.llm import Meter, json_request  # noqa: E402
from app.personas.frame import FRAME_VERSION, sample_skeleton  # noqa: E402
from app.personas.generate import PROFILE_SCHEMA, SYSTEM, dedupe_names, fake_profile, generate_batch, profile_prompt, tidy  # noqa: E402

STATE = settings.db_path.parent / "batches.json"


def load_state() -> list[dict]:
    return json.loads(STATE.read_text()) if STATE.exists() else []


def save_state(batches: list[dict]) -> None:
    STATE.write_text(json.dumps(batches, indent=1))


def request(seed: int) -> dict:
    # Same parameters as live generation (generate_batch), so batch people match live ones.
    return {"custom_id": f"seed-{seed}", "params": json_request(model=settings.model_for("crowd"), role="crowd", system=SYSTEM,
                                                                user=profile_prompt(sample_skeleton(seed)), schema=PROFILE_SCHEMA, max_tokens=1200)}


def wait(client: Anthropic, b: dict) -> None:
    """Polls once a minute. A dropped connection (a first build died on a DNS failure an hour in) is waited out for up to
    30 minutes: the batch keeps running on Anthropic's side either way."""
    t0 = time.time()
    failures = 0
    while True:
        try:
            s = client.messages.batches.retrieve(b["id"])
        except (APIConnectionError, APITimeoutError, InternalServerError) as e:
            failures += 1
            if failures > 30:
                raise
            print(f"  {time.time() - t0:5.0f}s  can't reach the API ({type(e).__name__}); trying again in a minute", flush=True)
            time.sleep(60)
            continue
        failures = 0
        c = s.request_counts
        print(f"  {time.time() - t0:5.0f}s  {s.processing_status}: {c.succeeded} done, {c.errored} errored, {c.processing} to go", flush=True)
        if s.processing_status == "ended":
            return
        time.sleep(60)


def collect(client: Anthropic, b: dict) -> None:
    """Store one ended batch and record what it cost."""
    have = {r["seed"] for r in db.q("SELECT seed FROM personas")}
    model = settings.model_for("crowd")
    meter = Meter(budget_usd=1e9)
    rows: list[tuple[int, dict, dict]] = []
    for r in client.messages.batches.results(b["id"]):
        seed = int(r.custom_id.removeprefix("seed-"))
        if seed in have:
            continue
        sk = sample_skeleton(seed)
        if r.result.type == "succeeded":
            msg = r.result.message
            meter.add(model, msg.usage, price_factor=0.5)
            try:
                prof = tidy(json.loads(next((c.text for c in msg.content if c.type == "text"), "")))
            except json.JSONDecodeError:
                prof = fake_profile(sk) | {"_error": f"unreadable answer ({msg.stop_reason})"}
        else:
            prof = fake_profile(sk) | {"_error": f"batch request {r.result.type}"}
        rows.append((seed, sk, prof))
    rows.sort(key=lambda r: r[0])
    for i in range(0, len(rows), 1000):
        db.insert_personas(rows[i:i + 1000])
    b.update(collected=True, stored=len(rows), failed=sum(1 for r in rows if "_error" in r[2]), cost=round(meter.cost_usd, 4), tokens=meter.tokens)
    print(f"stored {len(rows)} from {b['id']} ({b['failed']} failed, kept with template texture) for ${meter.cost_usd:.3f}; tokens {meter.tokens}", flush=True)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40000)
    ap.add_argument("--seed", type=int, default=100001, help="first seed; the first library used 1-10000")
    ap.add_argument("--batch", type=int, default=10000, help="requests per batch")
    ap.add_argument("--pilot", type=int, default=20, help="people written live first, to check output and measure cost")
    ap.add_argument("--budget", type=float, default=7.5, help="USD cap for this build (pilot + batches), checked before each batch")
    ap.add_argument("--dedupe-names", action="store_true", help="afterwards, rename people whose name is already taken (live, tiny calls)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # names and currencies in the pilot example
    if settings.effective_provider != "anthropic":
        sys.exit("the batch build needs ANTHROPIC_API_KEY; use build_library.py for the fake provider")

    client = Anthropic(api_key=settings.api_key, timeout=900, max_retries=3)
    batches = load_state()
    for b in batches:
        if not b["collected"]:
            print(f"collecting {b['id']} submitted earlier", flush=True)
            wait(client, b); collect(client, b); save_state(batches)
    spent = sum(b.get("cost", 0) for b in batches)
    existing = {r["seed"] for r in db.q("SELECT seed FROM personas")}
    seeds = [s for s in range(a.seed, a.seed + a.n) if s not in existing]
    print(f"model={settings.model_for('crowd')} library v{FRAME_VERSION}={db.persona_count(FRAME_VERSION)} to_generate={len(seeds)} spent so far ${spent:.3f}", flush=True)

    # Cost per person at batch prices: measured on the last batch, else estimated from a live pilot.
    measured = [b for b in batches if b.get("stored")]
    per_person = measured[-1]["cost"] / measured[-1]["stored"] if measured else None
    if per_person is None and a.pilot and seeds:
        pilot, seeds = seeds[:a.pilot], seeds[a.pilot:]
        meter = Meter(budget_usd=1e9)
        await generate_batch(pilot, meter)
        spent += meter.cost_usd
        # The pilot's parallel calls all write the instruction cache; a batch mostly reads it. The first batch's measured
        # cost replaces this estimate before the second batch is sent.
        t, p = meter.tokens, PRICING[settings.model_for("crowd")]
        per_person = (t["in"] * p["in"] + t["out"] * p["out"] + (t["cache_write"] + t["cache_read"]) * p["cache_read"]) / 1e6 / len(pilot) * 0.5
        sample = db.q("SELECT profile FROM personas WHERE seed=?", (pilot[0],))[0]["profile"]
        print(f"pilot: {len(pilot)} people live for ${meter.cost_usd:.4f} ({meter.tokens['in'] // len(pilot)} in / {meter.tokens['out'] // len(pilot)} out tokens each)\n"
              f"example: {sample[:400]}", flush=True)

    while seeds:
        projected = spent + (per_person or 0) * len(seeds)
        print(f"projected total ${projected:.2f} for {len(seeds)} more people at ${per_person or 0:.6f} each (budget ${a.budget:.2f})", flush=True)
        if projected > a.budget:
            sys.exit(f"stopping: projected ${projected:.2f} is over --budget ${a.budget:.2f}. Raise --budget and run again to continue.")
        chunk, seeds = seeds[:a.batch], seeds[a.batch:]
        sent = client.messages.batches.create(requests=[request(s) for s in chunk])
        b = {"id": sent.id, "first": chunk[0], "last": chunk[-1], "n": len(chunk), "collected": False}
        batches.append(b); save_state(batches)
        print(f"submitted {sent.id}: {len(chunk)} people (seeds {chunk[0]}-{chunk[-1]})", flush=True)
        wait(client, b); collect(client, b); save_state(batches)
        spent += b["cost"]
        per_person = b["cost"] / max(1, b["stored"])

    if a.dedupe_names:
        meter = Meter(budget_usd=1e9)
        renamed = await dedupe_names(meter, progress=lambda done, total, cost: print(f"renamed {done}/{total}  ${cost:.3f}", flush=True))
        spent += meter.cost_usd
        print(f"renamed {renamed} repeated names for ${meter.cost_usd:.3f}", flush=True)
    print(f"done: library v{FRAME_VERSION} has {db.persona_count(FRAME_VERSION)} people. this build ${spent:.3f}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
