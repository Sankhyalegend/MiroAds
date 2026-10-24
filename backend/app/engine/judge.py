"""Stage 4: numbers from code, words from the model. Produces the frontend Scorecard plus research extras."""
from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from ..llm import Meter, llm
from .banks import DIMENSIONS
from .market import market_summary
from .stimulus import stimulus_block

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "description": "6-10 words, decisive"},
        "summary": {"type": "string", "description": "3-5 sentences for the founder. Lead with the answer. Cite numbers given."},
        "dimension_notes": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "score": {"type": "number", "minimum": 0, "maximum": 10}, "note": {"type": "string"}}, "required": ["name", "score", "note"], "additionalProperties": False}},
        "what_is_missing": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 6},
        "variants": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "object", "properties": {"label": {"type": "string"}, "change": {"type": "string"}, "predicted_delta": {"type": "number"}}, "required": ["label", "change", "predicted_delta"], "additionalProperties": False}},
        "market_position": {"type": "string", "description": "2-3 sentences: how this stacks up against what is already on the market (from the market scan): price position, what would make people switch, which alternative it most has to beat. If no market scan was available, say so in one sentence."},
        "methodology_note": {"type": "string", "description": "2 sentences on what this simulation can and cannot tell the reader"},
        "limitations": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4},
        "confidence_note": {"type": "string"},
    },
    "required": ["verdict", "summary", "dimension_notes", "what_is_missing", "variants", "market_position", "methodology_note", "limitations", "confidence_note"],
    "additionalProperties": False,
}

SYSTEM_TEMPLATE = """You are the lead author of a market-research report built from a simulated crowd of AI personas. You are honest about what a simulation is: a structured pre-test that surfaces objections and segment differences, not a forecast. Every statistic you state must come from the numbers provided. Dimension scores: you assign them, 0-10, using the crowd data and expert findings; keep them consistent with the mean and the objections. Variants: concrete rewrites of the stimulus a founder could ship tomorrow, each with your predicted score change. Write plainly.

{stimulus}

Respond with JSON only."""


# ---------- deterministic statistics ----------
def _ward_groups(texts: list[str], max_groups: int) -> tuple[list[list[int]], np.ndarray | None]:
    """Ward linkage on normalised TF-IDF gives balanced groups where average linkage chained 91 of 100 live takeaways,
    and about half of each run's objections, into one. Short texts that share few words with any other still end up
    together in one loose group, often the largest. Returns groups of indices into texts plus the vectors, or one group
    per text and None when there are too few texts or too little shared vocabulary to cluster."""
    if len(texts) >= 6:
        try:
            X = normalize(TfidfVectorizer(ngram_range=(1, 2), min_df=2, stop_words="english", sublinear_tf=True).fit_transform(texts)).toarray()
            k = min(max_groups, max(2, int(math.sqrt(len(texts)) / 1.5)))
            labels = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(X).tolist()
        except ValueError:  # too little shared vocabulary to cluster
            pass
        else:
            groups: dict[int, list[int]] = defaultdict(list)
            for i, lab in enumerate(labels):
                groups[lab].append(i)
            return list(groups.values()), X
    return [[i] for i in range(len(texts))], None


def _medoid(members: list[int], X: np.ndarray | None) -> int:
    """The member closest to the group's centroid: its most typical text, not the shortest one."""
    return members[int(np.argmax(X[members] @ X[members].mean(axis=0)))] if X is not None else members[0]


def _cluster_objections(items: list[tuple[str, float, str]], max_clusters: int = 8) -> list[dict]:
    """items: (objection_text, influence, quote_attribution). Groups objections the way _themes groups takeaways; each
    cluster is labelled with its most central objection, or with the exact text a majority of its members gave."""
    items = [it for it in items if it[0] and it[0].strip().lower() not in ("none", "n/a", "")]
    texts = [t for t, _, _ in items]
    groups, X = _ward_groups(texts, max_clusters)
    if X is None:  # not clustered: objections repeated verbatim still count together
        groups = [[i for i, t in enumerate(texts) if t == u] for u in dict.fromkeys(texts)]
    out = []
    for members in groups:
        same, c = Counter(texts[i] for i in members).most_common(1)[0]
        rep = max((i for i in members if texts[i] == same), key=lambda i: items[i][1]) if c > len(members) / 2 else _medoid(members, X)
        infl = sum(items[i][1] for i in members)
        quotes = sorted(((items[i][1], items[i][2], items[i][0]) for i in members), reverse=True)[:3]
        out.append({"text": texts[rep], "agent": items[rep][2], "count": len(members), "influence": round(infl, 1), "quotes": [{"agent": q[1], "text": q[2]} for q in quotes]})
    out.sort(key=lambda o: -(o["count"] * (1 + o["influence"])))
    return out[:6]


INTENTS = ("Would buy/use", "Maybe", "Would not")


def _themes(items: list[tuple[str, float, str]], max_themes: int = 6) -> list[dict]:
    """items: (text, influence, attribution). Groups longer free-text answers (exit-interview takeaways, fixes) with
    _ward_groups; each theme is labelled with its most central answer (medoid)."""
    items = [it for it in items if it[0] and it[0].strip()]
    if not items:
        return []
    texts = [t for t, _, _ in items]
    groups, X = _ward_groups(texts, max_themes)
    out = []
    for members in groups:
        rep = _medoid(members, X)
        top = sorted(members, key=lambda i: -items[i][1])[:3]
        out.append({"text": texts[rep], "agent": items[rep][2], "count": len(members), "quotes": [{"agent": items[i][2], "text": texts[i]} for i in top]})
    out.sort(key=lambda o: -o["count"])
    return out[:max_themes]


def _alt_key(name: str) -> str:
    """'My existing desk lamp' and 'my current desk lamp' count as the same alternative."""
    k = re.sub(r"\b(my|the|a|an|existing|current|old|own|usual|already)\b", " ", name.lower())
    return re.sub(r"\s+", " ", k).strip(" .")


def _stated_intents(agents: list[dict], verdicts: dict[int, dict], final: dict[int, float], interviews: dict[int, dict]) -> tuple[list[str], str]:
    """Per agent: what they said in the exit interview, else what they said first, else the score cut-off."""
    out: list[str] = []
    src: Counter = Counter()
    for a in agents:
        iv, v = interviews.get(a["id"]), verdicts.get(a["id"]) or {}
        if iv:
            out.append(iv["intent"]); src["exit interviews"] += 1
        elif v.get("intent") in INTENTS:
            out.append(v["intent"]); src["first impressions"] += 1
        else:
            s = final.get(a["id"], v.get("score", 5.0))
            out.append("Would buy/use" if s >= 6.5 else "Maybe" if s >= 4 else "Would not"); src["score cut-offs"] += 1
    top = src.most_common(1)[0][0] if src else "score cut-offs"
    return out, top if src[top] == len(agents) else ", ".join(f"{k} ({v})" for k, v in src.most_common())


def _pct(c: int, n: int) -> int:
    return round(c / n * 100) if n else 0


def _interview_stats(agents: list[dict], interviews: dict[int, dict]) -> dict | None:
    rows = [(a, interviews[a["id"]]) for a in agents if a["id"] in interviews]
    if not rows:
        return None
    n = len(rows)
    rec = [iv["recommend"] for _, iv in rows]
    prom, det = sum(1 for r in rec if r >= 9), sum(1 for r in rec if r <= 6)
    ch = Counter(iv["changedMind"] for _, iv in rows)
    vs = Counter(iv["vsAlternatives"] for _, iv in rows)
    alts: dict[str, list] = {}
    for _, iv in rows:
        name = re.sub(r"\s+", " ", iv.get("alternativeNamed", "")).strip().rstrip(".")
        if name and _alt_key(name) not in ("nothing", "none", "n/a", "no", "nothing really", "not sure", ""):
            alts.setdefault(_alt_key(name), [name, 0])[1] += 1
    who = lambda a: f"{a['name']}, {a['profession']}, {a['region']}"
    themes = _themes([(iv["takeaway"], a["influence"], who(a)) for a, iv in rows])
    fixes = _themes([(iv["oneFix"], a["influence"], who(a)) for a, iv in rows
                     if iv["intent"] != "Would buy/use" and iv.get("oneFix", "").strip().lower().rstrip(".") not in ("nothing", "none", "")], max_themes=5)
    quotes = []
    for intent in INTENTS:
        for a, iv in sorted((r for r in rows if r[1]["intent"] == intent), key=lambda r: -r[0]["influence"])[:3]:
            quotes.append({"agent": who(a), "intent": intent, "text": iv["quote"]})
    return {
        "n": n, "nps": round((prom - det) / n * 100), "promoters": _pct(prom, n), "passives": _pct(n - prom - det, n), "detractors": _pct(det, n),
        "changedMind": {"no": _pct(ch["No"], n), "positive": _pct(ch["More positive"], n), "negative": _pct(ch["More negative"], n)},
        "vsAlternatives": {"better": _pct(vs["Better"], n), "same": _pct(vs["About the same"], n), "worse": _pct(vs["Worse"], n), "unknown": _pct(vs["Don't know any"], n)},
        "alternatives": [{"name": d, "count": c} for d, c in sorted(alts.values(), key=lambda x: -x[1])[:6]],
        "themes": themes,
        "fixes": [{"text": f["text"], "count": f["count"]} for f in fixes],
        "quotes": quotes,
    }


def interview_summary(stats: dict) -> str:
    """Exit-interview results as text for the research team and the report author."""
    iv = stats.get("interviews")
    if not iv:
        return "EXIT INTERVIEWS: none (the run stopped before them)."
    alts = ", ".join(f"{a['name']} ({a['count']})" for a in iv["alternatives"]) or "none named"
    themes = "\n".join(f"  {t['count']}x {t['text']}" for t in iv["themes"][:5])
    fixes = "; ".join(f"{f['text']} ({f['count']})" for f in iv["fixes"]) or "none"
    return (f"EXIT INTERVIEWS (n={iv['n']}, asked after the discussion; the intent split is what they said here): NPS {iv['nps']} "
            f"(promoters {iv['promoters']}%, detractors {iv['detractors']}%). Changed mind since first impression: more positive {iv['changedMind']['positive']}%, "
            f"more negative {iv['changedMind']['negative']}%. Versus what they use or know: better {iv['vsAlternatives']['better']}%, same {iv['vsAlternatives']['same']}%, "
            f"worse {iv['vsAlternatives']['worse']}%, know none {iv['vsAlternatives']['unknown']}%. Alternatives they'd choose instead: {alts}.\n"
            f"What they concluded (clustered):\n{themes}\nWhat would win the non-buyers over: {fixes}")


def compute_stats(agents: list[dict], verdicts: dict[int, dict], final: dict[int, float], mind_changes: int, posts: list[dict], interviews: dict[int, dict] | None = None) -> dict:
    n = len(agents)
    interviews = interviews or {}
    fs = np.array([final.get(a["id"], verdicts.get(a["id"], {}).get("score", 5.0)) for a in agents], dtype=float)
    init = np.array([verdicts.get(a["id"], {}).get("score", 5.0) for a in agents], dtype=float)
    mean, sd = float(fs.mean()), float(fs.std())
    # Intent is what people said, not a score cut-off: in live runs at most ~1% said they'd buy while scores >= 6.5 implied 11-17%.
    stated, intent_source = _stated_intents(agents, verdicts, final, interviews)
    buy, no = stated.count("Would buy/use"), stated.count("Would not")
    intent = {"buy": _pct(buy, n), "maybe": _pct(n - buy - no, n), "no": _pct(no, n)}
    buys = {a["id"]: x == "Would buy/use" for a, x in zip(agents, stated)}

    def seg(group: str, key):
        m: dict[str, list[tuple[float, bool]]] = defaultdict(list)
        for a, s in zip(agents, fs):
            m[str(key(a))].append((float(s), buys[a["id"]]))
        return [{"segment": k, "group": group, "score": round(float(np.mean([s for s, _ in v])), 1), "n": len(v), "intent": _pct(sum(b for _, b in v), len(v))} for k, v in m.items()]
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

    top_posts = sorted(posts, key=lambda p: -(p.get("replies", 0) * 2 + p.get("reposts", 0) * 1.5 + p.get("likes", 0) * 0.5 + p.get("exposures", 0) * 0.05))[:20]
    agents_by_id = {a["id"]: a for a in agents}
    top_posts_out = [{"id": p["id"], "author": agents_by_id[p["agent_id"]]["name"], "profession": agents_by_id[p["agent_id"]]["profession"], "region": agents_by_id[p["agent_id"]]["region"],
                      "score": p["score"], "text": p["text"], "replies": p.get("replies", 0), "reposts": p.get("reposts", 0), "likes": p.get("likes", 0), "round": p["round"]} for p in top_posts]

    agreement = round(max(0.0, 1 - sd / 3.2) * 100)
    return {
        "n": n, "mean": mean, "sd": sd, "intent": intent, "intent_source": intent_source, "interviews": _interview_stats(agents, interviews),
        "shift": float(fs.mean() - init.mean()), "mind_changes": mind_changes,
        "segments": segments, "objections": objections, "missing": missing, "top_objection": objections[0]["text"] if objections else "none",
        "best_segment": best, "worst_segment": worst, "agreement": agreement,
        "diversity": {"reactionSimilarityMedian": round(sim_median, 3), "distinctObjections": distinct_obj, "segmentSpread": round(best[1] - worst[1], 2),
                      "verdict": "parroting" if sim_median > 0.6 else "healthy" if distinct_obj >= max(8, n // 20) else "narrow"},
        "top_posts": top_posts_out,
    }


def fake_judge(stats: dict, stype: str, rng: random.Random, market: dict | None = None) -> dict:
    m = stats["mean"]
    comps = (market or {}).get("competitors", [])
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
        "market_position": (f"It enters a market where {comps[0]['name']} ({comps[0]['price']}) is the default and {comps[-1]['name']} ({comps[-1]['price']}) is the cheap way out; "
                            f"at a crowd mean of {m:.1f} it has not yet shown why people should switch." if comps else "No market scan was available for this run."),
        "methodology_note": "A simulated crowd of AI personas is a structured pre-test: good at surfacing objections and segment differences, not a demand forecast. Treat deltas as directional.",
        "limitations": ["Personas share one underlying model; real crowds are noisier.", f"Per-segment n is small ({stats['n'] // 10} per profession group).", "No real purchase behaviour was observed."],
        "confidence_note": f"Agreement {stats['agreement']}% on n={stats['n']}.",
    }


async def run_judge(stimulus: dict, stats: dict, experts: list[dict], composition: dict, meter: Meter, state: dict, cost_usd: float, market: dict | None = None) -> dict:
    L = llm()
    system = SYSTEM_TEMPLATE.format(stimulus=stimulus_block(stimulus))
    stype = stimulus["type"]
    dims = ", ".join(f"{d} (weight {w})" for d, w in DIMENSIONS[stype])
    seg = "\n".join(f"  {s['group']}/{s['segment']}: {s['score']:.1f} (n={s['n']}, {s['intent']}% intent)" for s in stats["segments"][:40])
    obj = "\n".join(f"  {o['count']}x (influence {o['influence']:.1f}): {o['text']} — e.g. {o['quotes'][0]['agent'] if o['quotes'] else ''}" for o in stats["objections"])
    exp = "\n".join(f"  [{e['name']}] {e['headline']}\n" + "\n".join(f"     - ({f['type']}) {f['title']}: {f['detail']}" for f in e.get("findings", [])) for e in experts)
    posts = "\n".join(f"  - {p['author']} ({p['profession']}): \"{p['text']}\" [{p['replies']} replies/{p['reposts']} reposts/{p.get('likes', 0)} likes]" for p in stats["top_posts"][:12])
    user = (f"DIMENSIONS TO SCORE: {dims}\n\nCROWD RESULTS (n={stats['n']}): mean {stats['mean']:.2f}, sd {stats['sd']:.2f}, intent buy/maybe/no {stats['intent']['buy']}/{stats['intent']['maybe']}/{stats['intent']['no']}% (stated, from {stats['intent_source']}), "
            f"shift during discussion {stats['shift']:+.2f}, mind changes {stats['mind_changes']}, agreement {stats['agreement']}%.\n"
            f"Diversity check: median reaction similarity {stats['diversity']['reactionSimilarityMedian']}, distinct objections {stats['diversity']['distinctObjections']}, segment spread {stats['diversity']['segmentSpread']} ({stats['diversity']['verdict']}).\n"
            f"SEGMENTS:\n{seg}\nOBJECTIONS (clustered):\n{obj}\nMISSING (most cited): {', '.join(stats['missing'])}\nMOST DISCUSSED POSTS:\n{posts}\n\nRESEARCH TEAM FINDINGS:\n{exp}\n\n"
            f"SAMPLE COMPOSITION: {composition}\n\n{market_summary(market)}\n\n{interview_summary(stats)}\n\nWrite the report fields. JSON only.")
    rng = random.Random(state["seed"] + 99)
    try:
        out = await L.json(role="analyst", system=system, user=user, schema=JUDGE_SCHEMA, meter=meter, fake=lambda: fake_judge(stats, stype, rng, market), max_tokens=8000, effort="medium")
    except Exception as e:
        out = fake_judge(stats, stype, rng, market) | {"_error": str(e)[:160]}

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
        "marketPosition": out.get("market_position", ""),
        "dimensions": dim_scores, "segments": stats["segments"], "objections": stats["objections"], "missing": out["what_is_missing"],
        "missingKpis": kpis[:8], "variants": [{"label": v["label"], "change": v["change"], "predictedDelta": round(float(v["predicted_delta"]), 1)} for v in out["variants"]],
        "polarization": round(stats["sd"], 2), "shift": round(stats["shift"], 2),
        "confidence": {"sample": n, "agreement": stats["agreement"], "label": label, "note": out["confidence_note"] + f" Diversity: {stats['diversity']['verdict']}."},
        "intentSplit": stats["intent"], "intentSource": stats["intent_source"], "interviews": stats["interviews"],
        "research": {
            "methodology": out["methodology_note"], "limitations": out["limitations"], "team": experts, "otherFindings": others[:12],
            "composition": composition, "diversity": stats["diversity"], "topPosts": stats["top_posts"][:10], "mindChanges": stats["mind_changes"],
            "costUsd": round(cost_usd, 3),
        },
    }
