"""Stage 4: numbers from code, words from the model. Produces the frontend Scorecard plus research extras."""
from __future__ import annotations

import math
import random
import re
from collections import defaultdict

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

from ..llm import Meter, llm
from .banks import DIMENSIONS
from .stimulus import stimulus_block

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "description": "6-10 words, decisive"},
        "summary": {"type": "string", "description": "3-5 sentences for the founder. Lead with the answer. Cite numbers given."},
        "dimension_notes": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "score": {"type": "number", "minimum": 0, "maximum": 10}, "note": {"type": "string"}}, "required": ["name", "score", "note"], "additionalProperties": False}},
        "what_is_missing": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 6},
        "variants": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {"label": {"type": "string"}, "change": {"type": "string"}, "predicted_delta": {"type": "number"}}, "required": ["label", "change", "predicted_delta"], "additionalProperties": False}},
        "methodology_note": {"type": "string", "description": "2 sentences on what this simulation can and cannot tell the reader"},
        "limitations": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4},
        "confidence_note": {"type": "string"},
    },
    "required": ["verdict", "summary", "dimension_notes", "what_is_missing", "variants", "methodology_note", "limitations", "confidence_note"],
    "additionalProperties": False,
}

SYSTEM_TEMPLATE = """You are the lead author of a market-research report built from a simulated crowd of AI personas. You are honest about what a simulation is: a structured pre-test that surfaces objections and segment differences, not a forecast. Every statistic you state must come from the numbers provided. Dimension scores: you assign them, 0-10, using the crowd data and expert findings; keep them consistent with the mean and the objections. Variants: concrete rewrites of the stimulus a founder could ship tomorrow, each with your predicted score change. Write plainly.

{stimulus}

Respond with JSON only."""


# ---------- deterministic statistics ----------
def _cluster_objections(items: list[tuple[str, float, str]], max_clusters: int = 8) -> list[dict]:
    """items: (objection_text, influence, quote_attribution). Groups near-duplicate objections."""
    texts = [t for t, _, _ in items if t and t.strip().lower() not in ("none", "n/a", "")]
    if not texts:
        return []
    idx = [i for i, (t, _, _) in enumerate(items) if t and t.strip().lower() not in ("none", "n/a", "")]
    if len(texts) < 4:
        labels = list(range(len(texts)))
    else:
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english").fit_transform(texts)
        n_clusters = min(max_clusters, max(2, int(math.sqrt(len(texts)) / 1.5)))
        try:
            labels = AgglomerativeClustering(n_clusters=n_clusters, metric="cosine", linkage="average").fit_predict(vec.toarray()).tolist()
        except Exception:
            labels = list(range(len(texts)))
    groups: dict[int, list[int]] = defaultdict(list)
    for j, lab in enumerate(labels):
        groups[lab].append(idx[j])
    out = []
    for lab, members in groups.items():
        # representative = most common exact text, else shortest
        texts_m = [items[i][0] for i in members]
        rep = max(set(texts_m), key=lambda t: (texts_m.count(t), -len(t)))
        infl = sum(items[i][1] for i in members)
        quotes = sorted(((items[i][1], items[i][2], items[i][0]) for i in members), reverse=True)[:3]
        out.append({"text": rep, "count": len(members), "influence": round(infl, 1), "quotes": [{"agent": q[1], "text": q[2]} for q in quotes]})
    out.sort(key=lambda o: -(o["count"] * (1 + o["influence"])))
    return out[:6]


def compute_stats(agents: list[dict], verdicts: dict[int, dict], final: dict[int, float], mind_changes: int, posts: list[dict]) -> dict:
    n = len(agents)
    fs = np.array([final.get(a["id"], verdicts.get(a["id"], {}).get("score", 5.0)) for a in agents], dtype=float)
    init = np.array([verdicts.get(a["id"], {}).get("score", 5.0) for a in agents], dtype=float)
    mean, sd = float(fs.mean()), float(fs.std())
    buy = int((fs >= 6.5).sum()); no = int((fs < 4).sum())
    intent = {"buy": round(buy / n * 100), "maybe": round((n - buy - no) / n * 100), "no": round(no / n * 100)}

    def seg(group: str, key):
        m: dict[str, list[float]] = defaultdict(list)
        for a, s in zip(agents, fs):
            m[str(key(a))].append(float(s))
        return [{"segment": k, "group": group, "score": round(float(np.mean(v)), 1), "n": len(v), "intent": round(sum(1 for s in v if s >= 6.5) / len(v) * 100)} for k, v in m.items()]
    segments = []
    for group, key in [("Profession", lambda a: a["professionGroup"]), ("Ideology", lambda a: a["ideology"]), ("Income", lambda a: a["income"]), ("Age", lambda a: a["ageBand"]),
                       ("Tech adoption", lambda a: a["tech"]), ("Role", lambda a: a["role"]), ("Country GDP tier", lambda a: a["extra"]["gdpTier"]), ("Trust posture", lambda a: a["extra"]["trust"]),
                       ("Decision heuristic", lambda a: a["extra"]["heuristic"]), ("Temperament", lambda a: a["extra"]["temperament"]), ("Mood today", lambda a: a["mood"])]:
        segments += sorted(seg(group, key), key=lambda s: -s["score"])
    prof = [s for s in segments if s["group"] == "Profession"]
    best = (prof[0]["segment"], prof[0]["score"]) if prof else ("", 0.0)
    worst = (prof[-1]["segment"], prof[-1]["score"]) if prof else ("", 0.0)

    items = []
    for a in agents:
        v = verdicts.get(a["id"])
        if not v or final.get(a["id"], v["score"]) >= 6.5:
            continue
        items.append((v.get("objection", ""), a["influence"], f"{a['name']}, {a['profession']}, {a['region']}"))
    objections = _cluster_objections(items)

    miss = defaultdict(int)
    for a in agents:
        v = verdicts.get(a["id"])
        if v and v.get("missing"):
            miss[v["missing"].strip().rstrip(".").lower()] += 1
    missing = [k for k, _ in sorted(miss.items(), key=lambda kv: -kv[1])[:6]]

    # Diversity diagnostics: did the crowd actually disagree in distinct ways?
    reactions = [verdicts[a["id"]].get("reaction", "") for a in agents if a["id"] in verdicts]
    sim_median = 0.0
    if len(reactions) >= 10:
        try:
            X = TfidfVectorizer(stop_words="english").fit_transform(reactions)
            sample = X[np.random.RandomState(0).choice(X.shape[0], min(200, X.shape[0]), replace=False)]
            S = (sample @ sample.T).toarray()
            iu = np.triu_indices_from(S, k=1)
            sim_median = float(np.median(S[iu])) if iu[0].size else 0.0
        except Exception:
            sim_median = 0.0
    distinct_obj = len({re.sub(r"\W+", " ", (verdicts[a["id"]].get("objection", "") or "")).strip().lower() for a in agents if a["id"] in verdicts})

    top_posts = sorted(posts, key=lambda p: -(p.get("replies", 0) * 2 + p.get("reposts", 0) * 1.5 + p.get("exposures", 0) * 0.05))[:20]
    agents_by_id = {a["id"]: a for a in agents}
    top_posts_out = [{"id": p["id"], "author": agents_by_id[p["agent_id"]]["name"], "profession": agents_by_id[p["agent_id"]]["profession"], "region": agents_by_id[p["agent_id"]]["region"],
                      "score": p["score"], "text": p["text"], "replies": p.get("replies", 0), "reposts": p.get("reposts", 0), "round": p["round"]} for p in top_posts]

    agreement = round(max(0.0, 1 - sd / 3.2) * 100)
    return {
        "n": n, "mean": mean, "sd": sd, "intent": intent, "shift": float(fs.mean() - init.mean()), "mind_changes": mind_changes,
        "segments": segments, "objections": objections, "missing": missing, "top_objection": objections[0]["text"] if objections else "none",
        "best_segment": best, "worst_segment": worst, "agreement": agreement,
        "diversity": {"reactionSimilarityMedian": round(sim_median, 3), "distinctObjections": distinct_obj, "segmentSpread": round(best[1] - worst[1], 2),
                      "verdict": "parroting" if sim_median > 0.6 else "healthy" if distinct_obj >= max(8, n // 20) else "narrow"},
        "top_posts": top_posts_out,
    }


def fake_judge(stats: dict, stype: str, rng: random.Random) -> dict:
    m = stats["mean"]
    dims = [{"name": d, "score": round(max(1, min(9.8, m + (rng.random() - .5) * 2.2)), 1), "note": "From crowd mean and objection mix."} for d, _ in DIMENSIONS[stype]]
    return {
        "verdict": "Strong: ship it, fix the gaps" if m >= 7 else "Promising but not there yet" if m >= 5.5 else "Weak: rework before spending on it" if m >= 4 else "Do not proceed as is",
        "summary": f"{stats['n']} simulated people scored this {m:.1f}/10 on average; {stats['intent']['buy']}% would buy or back it and {stats['intent']['no']}% would not. "
                   f"The dominant objection was \"{stats['top_objection']}\". Opinion moved {stats['shift']:+.2f} during discussion with {stats['mind_changes']} mind changes. "
                   f"The gap between {stats['best_segment'][0]} ({stats['best_segment'][1]:.1f}) and {stats['worst_segment'][0]} ({stats['worst_segment'][1]:.1f}) says who this is really for.",
        "dimension_notes": dims,
        "what_is_missing": stats["missing"][:5] or ["a price", "proof", "a clear audience"],
        "variants": [{"label": f"Address the top objection directly: {stats['top_objection']}", "change": "Removes the most frequent blocker", "predicted_delta": 0.8},
                     {"label": "Lead with one measurable claim", "change": "Credibility", "predicted_delta": 0.5},
                     {"label": f"Speak to {stats['worst_segment'][0]} explicitly or drop them from targeting", "change": "Segment fit", "predicted_delta": 0.3}],
        "methodology_note": "A simulated crowd of AI personas is a structured pre-test: good at surfacing objections and segment differences, not a demand forecast. Treat deltas as directional.",
        "limitations": ["Personas share one underlying model; real crowds are noisier.", f"Per-segment n is small ({stats['n'] // 10} per profession group).", "No real purchase behaviour was observed."],
        "confidence_note": f"Agreement {stats['agreement']}% on n={stats['n']}.",
    }


async def run_judge(stimulus: dict, stats: dict, experts: list[dict], composition: dict, meter: Meter, state: dict, cost_usd: float) -> dict:
    L = llm()
    system = SYSTEM_TEMPLATE.format(stimulus=stimulus_block(stimulus))
    stype = stimulus["type"]
    dims = ", ".join(f"{d} (weight {w})" for d, w in DIMENSIONS[stype])
    seg = "\n".join(f"  {s['group']}/{s['segment']}: {s['score']:.1f} (n={s['n']}, {s['intent']}% intent)" for s in stats["segments"][:40])
    obj = "\n".join(f"  {o['count']}x (influence {o['influence']:.1f}): {o['text']} — e.g. {o['quotes'][0]['agent'] if o['quotes'] else ''}" for o in stats["objections"])
    exp = "\n".join(f"  [{e['name']}] {e['headline']}\n" + "\n".join(f"     - ({f['type']}) {f['title']}: {f['detail']}" for f in e.get("findings", [])) for e in experts)
    posts = "\n".join(f"  - {p['author']} ({p['profession']}): \"{p['text']}\" [{p['replies']}r/{p['reposts']}rp]" for p in stats["top_posts"][:12])
    user = (f"DIMENSIONS TO SCORE: {dims}\n\nCROWD RESULTS (n={stats['n']}): mean {stats['mean']:.2f}, sd {stats['sd']:.2f}, intent buy/maybe/no {stats['intent']['buy']}/{stats['intent']['maybe']}/{stats['intent']['no']}%, "
            f"shift during discussion {stats['shift']:+.2f}, mind changes {stats['mind_changes']}, agreement {stats['agreement']}%.\n"
            f"Diversity check: median reaction similarity {stats['diversity']['reactionSimilarityMedian']}, distinct objections {stats['diversity']['distinctObjections']}, segment spread {stats['diversity']['segmentSpread']} ({stats['diversity']['verdict']}).\n"
            f"SEGMENTS:\n{seg}\nOBJECTIONS (clustered):\n{obj}\nMISSING (most cited): {', '.join(stats['missing'])}\nMOST DISCUSSED POSTS:\n{posts}\n\nRESEARCH TEAM FINDINGS:\n{exp}\n\n"
            f"SAMPLE COMPOSITION: {composition}\n\nWrite the report fields. JSON only.")
    rng = random.Random(state["seed"] + 99)
    try:
        out = await L.json(role="analyst", system=system, user=user, schema=JUDGE_SCHEMA, meter=meter, fake=lambda: fake_judge(stats, stype, rng), max_tokens=8000, effort="medium")
    except Exception as e:
        out = fake_judge(stats, stype, rng) | {"_error": str(e)[:160]}

    weights = dict(DIMENSIONS[stype])
    dim_scores = [{"name": d["name"], "score": float(d["score"]), "weight": weights.get(d["name"], 0.1), "note": d["note"]} for d in out["dimension_notes"] if d["name"] in weights]
    for d, w in DIMENSIONS[stype]:
        if not any(x["name"] == d for x in dim_scores):
            dim_scores.append({"name": d, "score": round(stats["mean"], 1), "weight": w, "note": "Not scored separately."})
    analyst_score = round(sum(d["score"] * d["weight"] for d in dim_scores) / max(1e-6, sum(d["weight"] for d in dim_scores)), 1)
    # The headline is anchored to what the crowd actually said. The analyst's dimension view can move it by at most
    # one point either way, so the report can never contradict its own data.
    crowd_mean = round(stats["mean"], 1)
    overall = round(crowd_mean + max(-1.0, min(1.0, (analyst_score - crowd_mean) * 0.5)), 1)
    n = stats["n"]
    label = "High" if n >= 800 and stats["agreement"] >= 45 else "Medium" if n >= 250 else "Low"
    kpis: list[dict] = []
    seen_kpi: set[str] = set()
    for e in experts:
        for f in e.get("findings", []):
            if f["type"] != "missing_kpi":
                continue
            key = re.sub(r"\W+", " ", f["title"]).strip().lower()
            if key in seen_kpi:
                continue
            seen_kpi.add(key)
            kpis.append({"kpi": f["title"], "why": f["detail"], "target": f["target"], "by": e["name"]})
    others = [{"type": f["type"], "title": f["title"], "detail": f["detail"], "by": e["name"]} for e in experts for f in e.get("findings", []) if f["type"] != "missing_kpi"]

    return {
        "overall": overall, "crowdMean": crowd_mean, "analystScore": analyst_score, "verdict": out["verdict"], "summary": out["summary"],
        "dimensions": dim_scores, "segments": stats["segments"], "objections": stats["objections"], "missing": out["what_is_missing"],
        "missingKpis": kpis[:8], "variants": [{"label": v["label"], "change": v["change"], "predictedDelta": round(float(v["predicted_delta"]), 1)} for v in out["variants"]],
        "polarization": round(stats["sd"], 2), "shift": round(stats["shift"], 2),
        "confidence": {"sample": n, "agreement": stats["agreement"], "label": label, "note": out["confidence_note"] + f" Diversity: {stats['diversity']['verdict']}."},
        "intentSplit": stats["intent"],
        "research": {
            "methodology": out["methodology_note"], "limitations": out["limitations"], "team": experts, "otherFindings": others[:12],
            "composition": composition, "diversity": stats["diversity"], "topPosts": stats["top_posts"][:10], "mindChanges": stats["mind_changes"],
            "costUsd": round(cost_usd, 3),
        },
    }
