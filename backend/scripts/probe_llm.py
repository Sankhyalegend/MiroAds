"""Pre-flight: prove every API parameter the engine uses is accepted by the live endpoint.
Makes 3 tiny calls (2x crowd model to check caching, 1x analyst model). Prints usage and cost, never the key."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.llm import Meter, llm  # noqa: E402

SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "number", "minimum": 0, "maximum": 10}, "intent": {"type": "string", "enum": ["Would buy/use", "Maybe", "Would not"]}, "reaction": {"type": "string"}},
    "required": ["score", "intent", "reaction"], "additionalProperties": False,
}
SYSTEM = ("You are role-playing a 34-year-old frugal nurse in India reviewing a product for a research panel. Stay in character. Respond with JSON only.\n\n"
          "STIMULUS: a $149 smart desk lamp that changes colour temperature with your calendar. " * 12)  # padded so the prefix is cacheable


async def main() -> None:
    print(f"provider={settings.effective_provider} key_loaded={'yes' if settings.api_key else 'NO'} crowd={settings.model_for('crowd')} analyst={settings.model_for('analyst')} "
          f"dev_mode={settings.dev_mode} budget/run=${settings.run_budget_usd} concurrency={settings.max_concurrency}")
    if settings.effective_provider != "anthropic":
        print("Not using Anthropic: nothing to probe."); return
    L = llm()
    m = Meter(budget_usd=0.05)
    for i in (1, 2):
        t = time.time()
        out = await L.json(role="crowd", system=SYSTEM, user="Give your first impression as JSON.", schema=SCHEMA, meter=m, fake=lambda: {}, max_tokens=200)
        print(f"crowd call {i}: {time.time()-t:.1f}s score={out.get('score')} intent={out.get('intent')!r} reaction={str(out.get('reaction'))[:70]!r}")
        print(f"   tokens so far: {m.tokens}  cost ${m.cost_usd:.5f}")
    cached = m.tokens["cache_read"] > 0
    print(f"prompt caching: {'WORKING (cache_read > 0 on 2nd call)' if cached else 'no cache read seen (prefix may be below the minimum cacheable size for this model; harmless)'}")

    # Analyst role with the real analyst model regardless of dev mode, to validate Sonnet params too.
    settings.dev_mode = False
    t = time.time()
    out = await L.json(role="analyst", system="You are a research analyst. Respond with JSON only.", user="Return {\"score\": 7, \"intent\": \"Maybe\", \"reaction\": \"test\"} exactly.",
                       schema=SCHEMA, meter=m, fake=lambda: {}, max_tokens=120, effort="low")
    print(f"analyst call ({settings.analyst_model}): {time.time()-t:.1f}s -> {out}")
    print(f"TOTAL: {m.calls} calls, tokens {m.tokens}, cost ${m.cost_usd:.5f}")
    print("ALL PARAMETERS ACCEPTED" )


if __name__ == "__main__":
    asyncio.run(main())
