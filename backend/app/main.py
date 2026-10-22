"""Crowd Validator API. Run: uv run python -m uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db
from .config import settings
from .engine.events import bus
from .engine.runner import start_run_task, stop_run
from .llm import Meter
from .personas.generate import generate_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
app = FastAPI(title="Crowd Validator", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


class StimulusIn(BaseModel):
    type: str = Field(pattern="^(creative|website|offer|idea)$")
    title: str
    brief: str = ""
    targetAudience: str = ""
    imageUrl: Optional[str] = None
    url: Optional[str] = None
    offer: Optional[dict[str, Any]] = None


class RunIn(BaseModel):
    stimulus_id: str
    crowdSize: int = Field(default=300, ge=20, le=3000)
    rounds: int = Field(default=5, ge=0, le=12)
    seed: int = 42
    budgetUsd: Optional[float] = None


class LibraryBuildIn(BaseModel):
    n: int = Field(default=1000, ge=1, le=20000)
    seed: int = 1
    budgetUsd: float = 6.0


_library_job: dict[str, Any] = {"running": False, "done": 0, "total": 0, "cost": 0.0, "error": None}


@app.get("/health")
def health():
    return {"ok": True, "provider": settings.effective_provider, "crowdModel": settings.model_for("crowd"), "analystModel": settings.model_for("analyst"),
            "devMode": settings.dev_mode, "library": db.persona_count(), "runBudgetUsd": settings.run_budget_usd}


# ---- library ----
@app.get("/library/stats")
def library_stats():
    return {"count": db.persona_count(), "job": _library_job}


@app.post("/library/build")
async def library_build(body: LibraryBuildIn):
    if _library_job["running"]:
        raise HTTPException(409, "a library build is already running")
    existing = {r["seed"] for r in db.q("SELECT seed FROM personas")}
    seeds = [s for s in range(body.seed, body.seed + body.n) if s not in existing]
    _library_job.update(running=True, done=0, total=len(seeds), cost=0.0, error=None)

    async def job():
        meter = Meter(budget_usd=body.budgetUsd)
        try:
            for i in range(0, len(seeds), 200):
                n = await generate_batch(seeds[i:i + 200], meter)
                _library_job["done"] += n; _library_job["cost"] = round(meter.cost_usd, 3)
        except Exception as e:
            _library_job["error"] = str(e)[:300]
        finally:
            _library_job["running"] = False
    asyncio.create_task(job())
    return {"started": True, "toGenerate": len(seeds)}


# ---- stimuli & runs ----
@app.post("/stimuli")
def create_stimulus(body: StimulusIn):
    sid = "stim_" + uuid.uuid4().hex[:10]
    db.save_stimulus(sid, body.model_dump())
    return {"id": sid}


@app.get("/stimuli/{sid}")
def get_stimulus(sid: str):
    s = db.get_stimulus(sid)
    if not s:
        raise HTTPException(404, "stimulus not found")
    return s


@app.post("/runs")
async def create_run(body: RunIn):
    if not db.get_stimulus(body.stimulus_id):
        raise HTTPException(404, "stimulus not found")
    if db.persona_count() == 0:
        raise HTTPException(409, "persona library is empty; build it first (POST /library/build)")
    rid = "run_" + uuid.uuid4().hex[:10]
    cfg = body.model_dump()
    cfg["budgetUsd"] = cfg["budgetUsd"] or settings.run_budget_usd
    db.create_run(rid, body.stimulus_id, cfg)
    start_run_task(rid)
    # Wait briefly for the crowd to be sampled so the client can fetch personas right away.
    for _ in range(100):
        if db.get_run_agents(rid):
            break
        await asyncio.sleep(0.05)
    return run_view(rid)


@app.get("/runs")
def runs_list():
    out = []
    for r in db.list_runs():
        sc = db.get_scorecard(r["id"])
        out.append({"id": r["id"], "status": r["status"], "stage": r["stage"], "costUsd": round(r["cost_usd"], 4), "createdAt": r["created_at"],
                    "stimulus": {k: r["stimulus"].get(k) for k in ("type", "title", "targetAudience")}, "config": r["config"],
                    "overall": sc["overall"] if sc else None, "verdict": sc["verdict"] if sc else None})
    return out


def run_view(rid: str) -> dict:
    r = db.get_run(rid)
    if not r:
        raise HTTPException(404, "run not found")
    agents = db.get_run_agents(rid)
    personas = [{k: v for k, v in a.items() if k not in ("verdict", "finalScore", "actions")} for a in agents]
    return {"id": rid, "status": r["status"], "stage": r["stage"], "costUsd": round(r["cost_usd"], 4), "tokens": r["tokens"], "error": r["error"],
            "config": r["config"], "stimulus": db.get_stimulus(r["stimulus_id"]), "personas": personas, "lastSeq": db.max_seq(rid),
            "hasScorecard": db.get_scorecard(rid) is not None}


@app.get("/runs/{rid}")
def get_run(rid: str):
    return run_view(rid)


@app.post("/runs/{rid}/stop")
def post_stop(rid: str):
    return {"stopped": stop_run(rid)}


@app.get("/runs/{rid}/scorecard")
def get_scorecard(rid: str):
    sc = db.get_scorecard(rid)
    if not sc:
        raise HTTPException(404, "scorecard not ready")
    return sc


@app.get("/runs/{rid}/agents/{aid}")
def get_agent(rid: str, aid: int):
    a = db.get_run_agent(rid, aid)
    if not a:
        raise HTTPException(404, "agent not found")
    return a


@app.get("/runs/{rid}/events")
def get_events(rid: str, from_seq: int = 0):
    return db.events_from(rid, from_seq)


@app.websocket("/runs/{rid}/events")
async def ws_events(ws: WebSocket, rid: str, from_seq: int = 0):
    await ws.accept()
    if not db.get_run(rid):
        await ws.close(code=4004); return
    qd = bus.subscribe(rid)
    try:
        # Replay history first, in batches, then stream live. A client that reconnects passes ?from_seq=lastSeq+1.
        history = db.events_from(rid, from_seq)
        for i in range(0, len(history), 500):
            await ws.send_json({"batch": history[i:i + 500]})
        last = history[-1]["seq"] if history else from_seq - 1
        run = db.get_run(rid)
        if run and run["status"] in ("done", "failed", "stopped") and any(e["kind"] == "done" for e in history):
            await ws.send_json({"batch": [], "eof": True})
            return
        while True:
            ev = await qd.get()
            if ev["seq"] <= last:
                continue
            batch = [ev]
            # drain anything else already queued to cut frame count
            while not qd.empty() and len(batch) < 200:
                batch.append(qd.get_nowait())
            await ws.send_json({"batch": batch})
            if any(e["kind"] == "done" for e in batch):
                await ws.send_json({"batch": [], "eof": True})
                return
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(rid, qd)
