"""SQLite persistence. Deliberately small: a few tables with JSON columns, one connection, one lock.
Good for a local MVP; swap for Postgres by reimplementing these functions."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Iterable

from .config import settings

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS personas (
  id INTEGER PRIMARY KEY,
  seed INTEGER NOT NULL,
  skeleton TEXT NOT NULL,      -- sampled attributes (JSON)
  profile TEXT NOT NULL,       -- LLM-written texture (JSON)
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS personas_seed ON personas(seed);

CREATE TABLE IF NOT EXISTS stimuli (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  stimulus_id TEXT NOT NULL,
  config TEXT NOT NULL,
  status TEXT NOT NULL,        -- queued|running|done|failed|stopped
  stage TEXT NOT NULL,
  cost_usd REAL NOT NULL DEFAULT 0,
  tokens TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS run_agents (
  run_id TEXT NOT NULL,
  agent_id INTEGER NOT NULL,   -- 0..N-1 within the run (what the frontend uses)
  persona_id INTEGER NOT NULL,
  persona TEXT NOT NULL,       -- frontend-shaped persona + extras (JSON)
  mood TEXT NOT NULL,
  verdict TEXT,                -- stage-1 verdict (JSON)
  final_score REAL,
  actions TEXT NOT NULL DEFAULT '[]',
  PRIMARY KEY (run_id, agent_id)
);

CREATE TABLE IF NOT EXISTS events (
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  t REAL NOT NULL,
  PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS scorecards (
  run_id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  created_at REAL NOT NULL
);
"""


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(settings.db_path, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.executescript(SCHEMA)
        _add_missing_columns(_conn, "run_agents", {"context": "TEXT"})
    return _conn


def _add_missing_columns(c: sqlite3.Connection, table: str, cols: dict[str, str]) -> None:
    """CREATE TABLE IF NOT EXISTS never alters an existing table, so columns added later are created here."""
    have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
    for name, typ in cols.items():
        if name not in have:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")


def q(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with _lock:
        return conn().execute(sql, tuple(params)).fetchall()


def x(sql: str, params: Iterable[Any] = ()) -> None:
    with _lock:
        conn().execute(sql, tuple(params))


def xmany(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    with _lock:
        conn().executemany(sql, [tuple(r) for r in rows])


def j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def uj(s: str | None, default: Any = None) -> Any:
    return json.loads(s) if s else default


# ---- personas ----
def persona_count() -> int:
    return q("SELECT COUNT(*) c FROM personas")[0]["c"]


def insert_personas(rows: list[tuple[int, dict, dict]]) -> None:
    now = time.time()
    xmany("INSERT INTO personas(seed, skeleton, profile, created_at) VALUES (?,?,?,?)",
          [(seed, j(sk), j(pr), now) for seed, sk, pr in rows])


def update_persona_profile(pid: int, profile: dict) -> None:
    x("UPDATE personas SET profile=? WHERE id=?", (j(profile), pid))


def all_personas() -> list[dict]:
    return [{"id": r["id"], "skeleton": uj(r["skeleton"]), "profile": uj(r["profile"])} for r in q("SELECT * FROM personas")]


# ---- stimuli / runs ----
def save_stimulus(sid: str, data: dict) -> None:
    x("INSERT OR REPLACE INTO stimuli(id, data, created_at) VALUES (?,?,?)", (sid, j(data), time.time()))


def get_stimulus(sid: str) -> dict | None:
    r = q("SELECT data FROM stimuli WHERE id=?", (sid,))
    return uj(r[0]["data"]) if r else None


def create_run(rid: str, stimulus_id: str, config: dict) -> None:
    now = time.time()
    x("INSERT INTO runs(id, stimulus_id, config, status, stage, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
      (rid, stimulus_id, j(config), "queued", "idle", now, now))


def update_run(rid: str, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = [j(v) if isinstance(v, (dict, list)) else v for v in fields.values()]
    x(f"UPDATE runs SET {cols}, updated_at=? WHERE id=?", (*vals, time.time(), rid))


def get_run(rid: str) -> dict | None:
    r = q("SELECT * FROM runs WHERE id=?", (rid,))
    if not r:
        return None
    d = dict(r[0])
    d["config"] = uj(d["config"]); d["tokens"] = uj(d["tokens"], {})
    return d


def list_runs(limit: int = 50) -> list[dict]:
    out = []
    for r in q("SELECT r.*, s.data AS stimulus FROM runs r JOIN stimuli s ON s.id=r.stimulus_id ORDER BY r.created_at DESC LIMIT ?", (limit,)):
        d = dict(r); d["config"] = uj(d["config"]); d["tokens"] = uj(d["tokens"], {}); d["stimulus"] = uj(d["stimulus"])
        out.append(d)
    return out


# ---- run agents ----
def insert_run_agents(rid: str, agents: list[dict]) -> None:
    xmany("INSERT INTO run_agents(run_id, agent_id, persona_id, persona, mood) VALUES (?,?,?,?,?)",
          [(rid, a["id"], a["personaId"], j(a), a["mood"]) for a in agents])


def set_verdict(rid: str, agent_id: int, verdict: dict) -> None:
    x("UPDATE run_agents SET verdict=?, final_score=? WHERE run_id=? AND agent_id=?", (j(verdict), verdict["score"], rid, agent_id))


def set_final_score(rid: str, agent_id: int, score: float) -> None:
    x("UPDATE run_agents SET final_score=? WHERE run_id=? AND agent_id=?", (score, rid, agent_id))


def set_context(rid: str, agent_id: int, context: dict, mood: str, persona: dict) -> None:
    """What the agent knows about the market, plus their mood after the news (also kept in the persona JSON)."""
    x("UPDATE run_agents SET context=?, mood=?, persona=? WHERE run_id=? AND agent_id=?", (j(context), mood, j(persona), rid, agent_id))


def append_action(rid: str, agent_id: int, action: dict) -> None:
    r = q("SELECT actions FROM run_agents WHERE run_id=? AND agent_id=?", (rid, agent_id))
    acts = uj(r[0]["actions"], []) if r else []
    acts.append(action)
    x("UPDATE run_agents SET actions=? WHERE run_id=? AND agent_id=?", (j(acts), rid, agent_id))


def _agent_row(r: sqlite3.Row) -> dict:
    d = uj(r["persona"]); d["verdict"] = uj(r["verdict"]); d["finalScore"] = r["final_score"]; d["actions"] = uj(r["actions"], [])
    d["context"] = uj(r["context"])
    return d


def get_run_agents(rid: str) -> list[dict]:
    return [_agent_row(r) for r in q("SELECT * FROM run_agents WHERE run_id=? ORDER BY agent_id", (rid,))]


def get_run_agent(rid: str, agent_id: int) -> dict | None:
    r = q("SELECT * FROM run_agents WHERE run_id=? AND agent_id=?", (rid, agent_id))
    return _agent_row(r[0]) if r else None


# ---- events ----
def append_event(rid: str, seq: int, ev: dict) -> None:
    x("INSERT INTO events(run_id, seq, kind, payload, t) VALUES (?,?,?,?,?)", (rid, seq, ev["kind"], j(ev), ev.get("t", time.time())))


def events_from(rid: str, seq: int) -> list[dict]:
    return [uj(r["payload"]) | {"seq": r["seq"]} for r in q("SELECT seq, payload FROM events WHERE run_id=? AND seq>=? ORDER BY seq", (rid, seq))]


def max_seq(rid: str) -> int:
    r = q("SELECT MAX(seq) m FROM events WHERE run_id=?", (rid,))
    return r[0]["m"] or 0


# ---- scorecards ----
def save_scorecard(rid: str, data: dict) -> None:
    x("INSERT OR REPLACE INTO scorecards(run_id, data, created_at) VALUES (?,?,?)", (rid, j(data), time.time()))


def get_scorecard(rid: str) -> dict | None:
    r = q("SELECT data FROM scorecards WHERE run_id=?", (rid,))
    return uj(r[0]["data"]) if r else None
