"""Orchestrates one run through the four stages with budget control and status updates."""
from __future__ import annotations

import asyncio
import logging
import traceback

from .. import db
from ..config import settings
from ..llm import Meter, llm
from ..personas.frame import FRAME_VERSION
from ..personas.sampler import composition, sample_crowd
from .events import bus
from .experts import run_experts
from .interview import price_shown, run_interviews
from .judge import compute_stats, group_by_meaning, run_judge
from .market import apply_market, run_market_scan
from .social import run_social
from .stage1 import run_stage1
from .stimulus import build_brief

log = logging.getLogger("runner")
_running: dict[str, dict] = {}
_village_cache: dict = {"key": None, "index": []}
MIN_VILLAGE = 1000  # a newer library version takes over once it has at least this many people


def village() -> list[dict]:
    """The people new runs draw from: the current library version once it is built, otherwise every person in the library.
    Holds sampling attributes only; the runner loads the people drawn."""
    version = FRAME_VERSION if db.persona_count(FRAME_VERSION) >= MIN_VILLAGE else None
    key = (version, db.persona_count(version))
    if _village_cache["key"] != key:
        _village_cache.update(key=key, index=db.library_index(version))
    return _village_cache["index"]


def same_crowd(source_id: str) -> tuple[list[dict], dict, dict]:
    """The people of an earlier run, with the moods, market knowledge and market scan they had there, so a new version is
    judged by exactly the same crowd. Returns (crowd, market, mood shifts)."""
    rows = db.get_run_agents(source_id)
    if not rows:
        raise RuntimeError(f"run {source_id} has no crowd to copy")
    people = db.personas_by_ids([r["personaId"] for r in rows])
    crowd = []
    for r in rows:
        a = {k: v for k, v in r.items() if k not in ("verdict", "finalScore", "actions", "context", "interview")}
        a["_sk"], a["_profile"] = people[a["personaId"]]["skeleton"], people[a["personaId"]]["profile"]
        if r.get("context"):
            a["_market"] = r["context"]
            if r["context"].get("moodReason"):
                a["_mood_reason"] = r["context"]["moodReason"]
        crowd.append(a)
    ev = next((e for e in db.events_from(source_id, 0) if e["kind"] == "market"), None) or {}
    market = {k: ev[k] for k in ("status", "brief", "reason", "searches") if k in ev} or {"status": "off"}
    return crowd, market, ev.get("moodShifts", {})


def stop_run(run_id: str) -> bool:
    st = _running.get(run_id)
    if st:
        st["stopped"] = True; st["stop_reason"] = "stopped by user"
        return True
    return False


async def _set_stage(run_id: str, stage: str) -> None:
    db.update_run(run_id, stage=stage, status="running")
    await bus.emit(run_id, {"kind": "stage", "stage": stage})


async def execute_run(run_id: str) -> None:
    run = db.get_run(run_id)
    if not run:
        return
    cfg = run["config"]
    stimulus = db.get_stimulus(run["stimulus_id"]) or {}
    state = {"seed": int(cfg.get("seed", 42)), "stopped": False}
    _running[run_id] = state

    def on_meter(m: Meter) -> None:
        if m.calls % 10 == 0:
            db.update_run(run_id, cost_usd=m.cost_usd, tokens=m.tokens)
    meter = Meter(budget_usd=float(cfg.get("budgetUsd", settings.run_budget_usd)), on_update=on_meter)

    try:
        llm()  # initialise provider early so a bad key fails fast
        # ---- crowd: drawn from the people tested least so far, or for an A/B test the very people of an earlier run ----
        lib = village()
        if not lib:
            raise RuntimeError("Persona library is empty. Run scripts/build_library.py first.")
        same = cfg.get("sameCrowdAs")
        if same:
            crowd, copied_market, copied_shifts = same_crowd(same)
            state["crowd_info"] = {"seed": state["seed"], "village": len(lib), "newPeople": 0, "sameCrowdAs": same}
        else:
            uses = db.persona_use_counts()
            people: dict[int, dict] = {}

            def load(ids: list[int]) -> dict[int, dict]:
                people.update(db.personas_by_ids(ids))
                return people
            crowd = sample_crowd(lib, int(cfg.get("crowdSize", 300)), stimulus.get("targetAudience", ""), state["seed"], use_counts=uses, load=load)
            for a in crowd:
                a["_sk"] = people[a["personaId"]]["skeleton"]; a["_profile"] = people[a["personaId"]]["profile"]
            state["crowd_info"] = {"seed": state["seed"], "village": len(lib), "newPeople": sum(1 for a in crowd if not uses.get(a["personaId"]))}
        db.insert_run_agents(run_id, [{k: v for k, v in a.items() if not k.startswith("_")} for a in crowd])
        db.update_run(run_id, status="running")
        await bus.emit(run_id, {"kind": "crowd_ready", "n": len(crowd)})

        # ---- stage 0: brief ----
        stimulus = await build_brief(stimulus, meter)
        db.save_stimulus(run["stimulus_id"], {k: v for k, v in stimulus.items() if k != "_images"})

        # ---- stage 0b: market scan; each agent gets the slice they'd plausibly know, and news can shift mood ----
        market: dict = {"status": "off"}
        if same:  # the same market knowledge and moods as in the first version's run
            market, shifts = copied_market, copied_shifts
            for a in crowd:
                if a.get("_market"):
                    db.set_context(run_id, a["id"], a["_market"], a["mood"], {k: v for k, v in a.items() if not k.startswith("_")})
        else:
            if cfg.get("marketScan", True):
                await _set_stage(run_id, "market")
                market = await run_market_scan(stimulus, crowd, meter)
            shifts = apply_market(run_id, crowd, market.get("brief"), state["seed"])
        await bus.emit(run_id, {"kind": "market", **market, "moodShifts": shifts})

        # ---- stage 1 ----
        await _set_stage(run_id, "impressions")
        verdicts = await run_stage1(run_id, stimulus, crowd, meter, state)

        # ---- stage 2 ----
        rounds = int(cfg.get("rounds", 5))
        final = {aid: v["score"] for aid, v in verdicts.items()}
        if not state["stopped"] and rounds > 0:
            await _set_stage(run_id, "social")
            final = await run_social(run_id, stimulus, crowd, verdicts, meter, state, rounds)
        posts = state.get("posts", [])
        mind_changes = sum(1 for e in db.events_from(run_id, 0) if e["kind"] == "mind_change")

        # ---- stage 2b: exit interviews, everyone says what they now conclude ----
        interviews: dict[int, dict] = {}
        if not state["stopped"]:
            await _set_stage(run_id, "interviews")
            interviews = await run_interviews(run_id, stimulus, crowd, verdicts, final, posts, meter, state)

        # ---- stats (code) ----
        stats = compute_stats(crowd, verdicts, final, mind_changes, posts, interviews, price_shown(stimulus))
        await group_by_meaning(stats, crowd, verdicts, final, interviews, stimulus, meter)
        comp = composition(crowd)

        # ---- stage 3 ----
        experts = []
        if not state["stopped"]:
            await _set_stage(run_id, "experts")
            experts = await run_experts(run_id, stimulus, stats, stats["top_posts"], meter, state, market.get("brief"))

        # ---- stage 4 ----
        await _set_stage(run_id, "judge")
        scorecard = await run_judge(stimulus, stats, experts, comp, meter, state, meter.cost_usd, market.get("brief"))
        scorecard["research"]["market"] = {"status": market["status"], **({"reason": market["reason"]} if market.get("reason") else {}),
                                           **(market.get("brief") or {}), "moodShifts": shifts}
        if state["stopped"]:
            scorecard["confidence"]["note"] += f" Run ended early: {state.get('stop_reason', 'stopped')}."
        scorecard["research"]["crowd"] = state["crowd_info"]
        scorecard["research"]["costUsd"] = round(meter.cost_usd, 3)
        scorecard["research"]["suppressedMoves"] = state.get("suppressed_moves", 0)
        scorecard["research"]["tokens"] = meter.tokens
        scorecard["research"]["provider"] = llm().provider
        scorecard["research"]["models"] = {"crowd": settings.model_for("crowd"), "analyst": settings.model_for("analyst")}
        db.save_scorecard(run_id, scorecard)
        db.update_run(run_id, status="stopped" if state["stopped"] else "done", stage="done", cost_usd=meter.cost_usd, tokens=meter.tokens)
        await bus.emit(run_id, {"kind": "stage", "stage": "done"})
        await bus.emit(run_id, {"kind": "done", "costUsd": round(meter.cost_usd, 4)})
    except Exception as e:
        log.error("run %s failed: %s\n%s", run_id, e, traceback.format_exc())
        db.update_run(run_id, status="failed", error=str(e)[:500], cost_usd=meter.cost_usd, tokens=meter.tokens)
        await bus.emit(run_id, {"kind": "error", "message": str(e)[:300]})
        await bus.emit(run_id, {"kind": "done", "costUsd": round(meter.cost_usd, 4), "failed": True})
    finally:
        _running.pop(run_id, None)


def start_run_task(run_id: str) -> asyncio.Task:
    return asyncio.create_task(execute_run(run_id))
