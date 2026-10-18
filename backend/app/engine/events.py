"""Per-run event stream: persisted with a sequence number, fanned out to live WebSocket subscribers.
Event payloads match the frontend's SimEvent union exactly."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from .. import db


class RunBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._seq: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def seq(self, run_id: str) -> int:
        if run_id not in self._seq:
            self._seq[run_id] = db.max_seq(run_id)
        return self._seq[run_id]

    async def emit(self, run_id: str, ev: dict) -> dict:
        ev.setdefault("t", time.time() * 1000)
        async with self._lock:
            s = self.seq(run_id) + 1
            self._seq[run_id] = s
        ev["seq"] = s
        db.append_event(run_id, s, ev)
        for qd in list(self._subs.get(run_id, ())):
            try:
                qd.put_nowait(ev)
            except asyncio.QueueFull:
                pass
        return ev

    def subscribe(self, run_id: str) -> asyncio.Queue:
        qd: asyncio.Queue = asyncio.Queue(maxsize=50_000)
        self._subs[run_id].add(qd)
        return qd

    def unsubscribe(self, run_id: str, qd: asyncio.Queue) -> None:
        self._subs[run_id].discard(qd)


bus = RunBus()
