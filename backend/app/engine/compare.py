"""Two runs side by side: headline numbers, and B minus A with a 95% margin of error. When B was run on the same crowd as
A (sameCrowdAs), each person is compared with themselves, which takes out the person-to-person noise; otherwise the
margin is for two independent crowds and is wider. Builds on the same per-agent records as scripts/compare_runs.py."""
from __future__ import annotations

import math

from .. import db

Z95 = 1.96


def _final(a: dict) -> float:
    return a["finalScore"] if a.get("finalScore") is not None else a["verdict"]["score"]


# Per-person measures: (key, label, unit, value from an agent record or None when it wasn't asked)
MEASURES = [
    ("score", "Score after the discussion", "points", lambda a: _final(a)),
    ("first", "First-impression score", "points", lambda a: a["verdict"]["score"]),
    ("stop", "Would stop scrolling", "%", lambda a: 100.0 * bool(a["verdict"]["noticed"]) if "noticed" in a["verdict"] else None),
    ("click", "Would click", "%", lambda a: 100.0 * (a["verdict"].get("would_click") == "Yes") if "would_click" in a["verdict"] else None),
    ("buy", "Would buy / back (stated)", "%", lambda a: 100.0 * (a["interview"]["intent"] == "Would buy/use") if a.get("interview") else None),
    ("likelihood", "Likelihood to buy (0-10)", "points", lambda a: float(a["interview"]["likelihood"]) if a.get("interview") and "likelihood" in a["interview"] else None),
    ("choice", "Would choose this over the alternative", "%", lambda a: 100.0 * (a["interview"].get("choice") == "This one") if a.get("interview") and "choice" in a["interview"] else None),
    # NPS as each person's contribution: +100 promoter, -100 detractor, 0 passive; the mean is the NPS.
    ("nps", "Net promoter score", "", lambda a: (100.0 if a["interview"]["recommend"] >= 9 else -100.0 if a["interview"]["recommend"] <= 6 else 0.0) if a.get("interview") else None),
]


def _mean_sd(xs: list[float]) -> tuple[float, float]:
    m = sum(xs) / len(xs)
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else 0.0


def _summary(rid: str) -> dict:
    r = db.get_run(rid)
    s = db.get_stimulus(r["stimulus_id"]) or {}
    sc = db.get_scorecard(rid) or {}
    iv = sc.get("interviews") or {}
    return {"id": rid, "title": s.get("title", rid), "type": s.get("type"), "brief": s.get("brief", ""), "status": r["status"], "createdAt": r["created_at"],
            "costUsd": round(r["cost_usd"], 4), "overall": sc.get("overall"), "verdict": sc.get("verdict"), "n": (sc.get("confidence") or {}).get("sample"),
            "objections": [{"text": o["text"], "count": o["count"]} for o in (sc.get("objections") or [])[:4]],
            "price": iv.get("price"), "sameCrowdAs": r["config"].get("sameCrowdAs")}


def compare_runs(ra: str, rb: str) -> dict:
    A = {a["personaId"]: a for a in db.get_run_agents(ra) if a.get("verdict")}
    B = {b["personaId"]: b for b in db.get_run_agents(rb) if b.get("verdict")}
    both = sorted(A.keys() & B.keys())
    paired = len(both) >= 0.9 * max(len(A), len(B), 1)
    rows = []
    for key, label, unit, f in MEASURES:
        if paired:
            pairs = [(x, y) for pid in both if (x := f(A[pid])) is not None and (y := f(B[pid])) is not None]
            if len(pairs) < 2:
                continue
            xa, xb = [p[0] for p in pairs], [p[1] for p in pairs]
            diff, sd = _mean_sd([y - x for x, y in pairs])
            margin = Z95 * sd / math.sqrt(len(pairs))
            n = len(pairs)
        else:
            xa = [v for a in A.values() if (v := f(a)) is not None]
            xb = [v for b in B.values() if (v := f(b)) is not None]
            if len(xa) < 2 or len(xb) < 2:
                continue
            (ma, sa), (mb, sb) = _mean_sd(xa), _mean_sd(xb)
            diff, margin, n = mb - ma, Z95 * math.sqrt(sa ** 2 / len(xa) + sb ** 2 / len(xb)), min(len(xa), len(xb))
        ma, mb = sum(xa) / len(xa), sum(xb) / len(xb)
        rows.append({"key": key, "label": label, "unit": unit, "a": round(ma, 2), "b": round(mb, 2), "diff": round(diff, 2), "margin": round(margin, 2), "n": n,
                     "verdict": "B higher" if diff - margin > 0 else "A higher" if diff + margin < 0 else "no clear difference"})
    return {"a": _summary(ra), "b": _summary(rb), "paired": paired, "people": len(both), "rows": rows}
