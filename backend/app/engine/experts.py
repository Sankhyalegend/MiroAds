"""Stage 3: the research team audits the run. Each expert sees the brief, the numbers and the most-discussed posts."""
from __future__ import annotations

import asyncio
import random

from ..llm import Meter, llm
from .banks import KPI_HINTS, RESEARCH_TEAM
from .events import bus
from .stimulus import stimulus_block

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "Your one-sentence read of the result from your lens"},
        "findings": {
            "type": "array", "minItems": 2, "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["missing_kpi", "unmeasurable_claim", "risk", "opportunity", "statistical_caveat", "what_would_be_better"]},
                    "title": {"type": "string"},
                    "detail": {"type": "string", "description": "2-3 sentences grounded in the crowd data provided; cite a number or a quote"},
                    "target": {"type": "string", "description": "For missing_kpi: a definition and a target value. Otherwise empty."},
                },
                "required": ["type", "title", "detail", "target"], "additionalProperties": False,
            },
        },
    },
    "required": ["headline", "findings"],
    "additionalProperties": False,
}

SYSTEM_TEMPLATE = """You are a senior member of a market-research team reviewing a simulated-crowd study. You are rigorous and specific: you cite the numbers and quotes you were given, you separate what the data shows from what you infer, and you never pad. You write for a founder who will act on this tomorrow.

{stimulus}

Respond with JSON only."""


def fake_findings(expert: dict, stats: dict, stype: str, rng: random.Random) -> dict:
    kpis = [k.strip() for k in KPI_HINTS[stype].split(",")]
    k = rng.choice(kpis)
    return {
        "headline": f"{expert['name']}: the crowd mean of {stats['mean']:.1f} with {stats['intent']['buy']}% intent is {'encouraging' if stats['mean'] >= 6 else 'a warning' if stats['mean'] < 4.5 else 'inconclusive'} from my lens.",
        "findings": [
            {"type": "missing_kpi", "title": k.capitalize(), "detail": f"Nothing in the stimulus lets you measure {k}. The top objection ('{stats['top_objection']}') is exactly what this KPI would catch.", "target": f"Define {k}; set a target before launch."},
            {"type": "statistical_caveat" if expert["name"] == "Quantitative analyst" else "risk", "title": "Segment gap", "detail": f"Best segment {stats['best_segment'][0]} at {stats['best_segment'][1]:.1f} vs worst {stats['worst_segment'][0]} at {stats['worst_segment'][1]:.1f}; a {stats['best_segment'][1] - stats['worst_segment'][1]:.1f} point gap on n={stats['n']}.", "target": ""},
        ],
    }


async def run_experts(run_id: str, stimulus: dict, stats: dict, top_posts: list[dict], meter: Meter, state: dict) -> list[dict]:
    L = llm()
    system = SYSTEM_TEMPLATE.format(stimulus=stimulus_block(stimulus))
    rng = random.Random(state["seed"] * 3 + 1)
    posts_txt = "\n".join(f"- {p['author']} ({p['profession']}, {p['region']}, score {p['score']:.1f}): \"{p['text']}\" [{p['replies']} replies, {p['reposts']} reposts]" for p in top_posts[:20])
    seg = "\n".join(f"  {s['group']}/{s['segment']}: {s['score']:.1f} (n={s['n']}, {s['intent']}% intent)" for s in stats["segments"][:28])
    obj = "\n".join(f"  {o['count']}x (influence {o['influence']:.1f}): {o['text']}" for o in stats["objections"][:8])
    data = (f"CROWD RESULTS (n={stats['n']}):\n- Mean score {stats['mean']:.2f}/10, std-dev {stats['sd']:.2f}; intent buy/maybe/no = {stats['intent']['buy']}/{stats['intent']['maybe']}/{stats['intent']['no']}%\n"
            f"- Opinion shift during discussion: {stats['shift']:+.2f}; mind changes: {stats['mind_changes']}\n- Segment scores:\n{seg}\n- Top objections:\n{obj}\n"
            f"- Most cited missing items: {', '.join(stats['missing'][:5])}\n- Most discussed posts:\n{posts_txt}\n"
            f"- KPI families typical for this stimulus type: {KPI_HINTS[stimulus['type']]}")
    results: list[dict] = []

    async def one(expert: dict):
        if state.get("stopped"):
            return
        user = f"Your role: {expert['name']}. Your lens: {expert['lens']}\n\n{data}\n\nGive your headline and 2-4 findings. JSON only."
        local = random.Random(rng.random())
        try:
            out = await L.json(role="analyst", system=system, user=user, schema=FINDINGS_SCHEMA, meter=meter, fake=lambda: fake_findings(expert, stats, stimulus["type"], local), max_tokens=900)
        except Exception as e:
            if type(e).__name__ == "BudgetExceeded":
                state["stopped"] = True; state["stop_reason"] = str(e); return
            out = fake_findings(expert, stats, stimulus["type"], local)
        rec = {"name": expert["name"], "role": expert["name"], "lens": expert["lens"], **out}
        results.append(rec)
        await bus.emit(run_id, {"kind": "expert", "name": expert["name"], "role": expert["name"], "finding": out["headline"]})
        for f in out["findings"][:2]:
            await bus.emit(run_id, {"kind": "expert", "name": expert["name"], "role": f["type"].replace("_", " "), "finding": f"{f['title']}: {f['detail']}"})

    await asyncio.gather(*(one(e) for e in RESEARCH_TEAM))
    order = {e["name"]: i for i, e in enumerate(RESEARCH_TEAM)}
    results.sort(key=lambda r: order.get(r["name"], 99))
    return results
