"""Stage 4: numbers from code, words from the model. Produces the frontend Scorecard plus research extras."""
from __future__ import annotations

import asyncio
import logging
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

log = logging.getLogger("judge")

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
    by_label: dict[str, dict] = {}  # groups labelled with the same answer are one theme
    for members in groups:
        rep = _medoid(members, X)
        top = sorted(members, key=lambda i: -items[i][1])[:3]
        t = by_label.setdefault(texts[rep], {"text": texts[rep], "agent": items[rep][2], "count": 0, "quotes": []})
        t["count"] += len(members)
        t["quotes"] = (t["quotes"] + [{"agent": items[i][2], "text": texts[i]} for i in top])[:3]
    return sorted(by_label.values(), key=lambda o: -o["count"])[:max_themes]


def _who(a: dict) -> str:
    return f"{a['name']}, {a['profession']}, {a['region']}"


def _objection_items(agents: list[dict], verdicts: dict[int, dict], final: dict[int, float]) -> list[tuple[str, float, str]]:
    """(objection, influence, attribution) for everyone the stimulus hasn't won over."""
    items = []
    for a in agents:
        v = verdicts.get(a["id"])
        if v and final.get(a["id"], v["score"]) < 6.5 and v.get("objection", "").strip().lower() not in ("none", "n/a", ""):
            items.append((v["objection"], a["influence"], _who(a)))
    return items


def _takeaway_items(agents: list[dict], interviews: dict[int, dict]) -> list[tuple[str, float, str]]:
    return [(interviews[a["id"]]["takeaway"], a["influence"], _who(a)) for a in agents if a["id"] in interviews]


def _fix_items(agents: list[dict], interviews: dict[int, dict]) -> list[tuple[str, float, str]]:
    """What would win over the people who wouldn't buy."""
    return [(iv["oneFix"], a["influence"], _who(a)) for a in agents if (iv := interviews.get(a["id"]))
            and iv["intent"] != "Would buy/use" and iv.get("oneFix", "").strip().lower().rstrip(".") not in ("nothing", "none", "")]


_NO_ALTERNATIVE = ("nothing", "none", "n/a", "no", "nothing really", "not sure", "")


def _alternative_items(agents: list[dict], interviews: dict[int, dict]) -> list[tuple[str, float, str]]:
    """What people would compare it with or choose instead."""
    return [(iv["alternativeNamed"], a["influence"], _who(a)) for a in agents if (iv := interviews.get(a["id"]))
            and _alt_key(iv.get("alternativeNamed", "")) not in _NO_ALTERNATIVE]


THEMES_SCHEMA = {
    "type": "object",
    "properties": {
        "themes": {
            "type": "array", "description": "As many themes as the answers really need (usually 4-7), largest first",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "The theme in plain words, short and specific to this stimulus (e.g. 'Too expensive at $149 for a desk lamp'; for alternatives, the product or habit, e.g. 'BenQ ScreenBar'), not one person's quote"},
                    "representative": {"type": "integer", "description": "Number of the answer that best represents the theme"},
                    "members": {"type": "array", "items": {"type": "integer"}, "description": "Numbers of every answer in this theme"},
                },
                "required": ["label", "representative", "members"], "additionalProperties": False,
            },
        },
    },
    "required": ["themes"],
    "additionalProperties": False,
}

THEMES_SYSTEM = ("You sort short answers from a consumer research panel into themes for the report. Group by what people mean, not the words "
                 "they use: 'too pricey', '$149 is a lot' and 'I can get one for $20' are all about price. Put each answer in exactly one theme, the "
                 "one that matches its main point. Use as many themes as the answers really need (usually 4-7); answers that fit no theme go in a "
                 "theme labelled 'Other'. Respond with JSON only.")

_THEME_KINDS = {
    "objections": "each person's single strongest objection",
    "takeaways": "what each person concluded once the discussion was over",
    "fixes": "the one change that would win each person over",
    "alternatives": "what each person would compare it with or choose instead (put the same product or habit together)",
    "glance": "what each person took in within the first two seconds of seeing it",
}


async def _model_groups(items: list[tuple[str, float, str]], kind: str, stimulus: dict, meter: Meter) -> list[tuple[str, int, list[int]]] | None:
    """[(label, representative, members)] covering every answer once, or None when the model's sort can't be used.
    The model only sorts; counts, influence and quotes are computed here from its assignment."""
    texts = [re.sub(r"\s+", " ", t).strip() for t, _, _ in items]
    if not texts:
        return None
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(texts))
    user = (f"STIMULUS: \"{stimulus.get('title', '')}\" ({stimulus.get('type', '')})\n"
            f"THE ANSWERS ARE {_THEME_KINDS[kind]}:\n{numbered}\n\nSort them into themes. JSON only.")
    out = await llm().json(role="themes", system=THEMES_SYSTEM, user=user, schema=THEMES_SCHEMA, meter=meter, fake=lambda: {"themes": []}, max_tokens=12000, effort="low")
    seen: set[int] = set()
    groups: list[tuple[str, int, list[int]]] = []
    for t in out.get("themes", []):
        members = [i for i in dict.fromkeys(t.get("members", [])) if isinstance(i, int) and 0 <= i < len(texts) and i not in seen]
        if not members:
            continue
        seen.update(members)
        rep = t["representative"] if t.get("representative") in members else members[0]
        label = re.sub(r"^other\s*[:\-–]\s*(?=\S)", "", (t.get("label") or "").strip(), flags=re.I)  # "Other: unclear what it does" is a real theme
        groups.append((label or texts[rep], rep, members))
    missing = [i for i in range(len(texts)) if i not in seen]
    if not groups or len(missing) > 0.2 * len(texts):  # it skipped too much: the word-based groups are safer
        return None
    if missing:
        other = next((g for g in groups if g[0].lower() == "other"), None)
        if other:
            other[2].extend(missing)
        else:
            groups.append(("Other", missing[0], missing))
    return groups


def _grouped(items: list[tuple[str, float, str]], groups: list[tuple[str, int, list[int]]]) -> list[dict]:
    out = []
    for label, rep, members in groups:
        top = [rep] + [i for i in sorted(members, key=lambda i: -items[i][1]) if i != rep][:2]
        out.append({"text": label, "count": len(members), "influence": round(sum(items[i][1] for i in members), 1),
                    "quotes": [{"agent": items[i][2], "text": items[i][0]} for i in top]})
    return out


async def group_by_meaning(stats: dict, agents: list[dict], verdicts: dict[int, dict], final: dict[int, float],
                           interviews: dict[int, dict], stimulus: dict, meter: Meter) -> None:
    """Re-sorts objections, takeaways, fixes and named alternatives into themes with one small model call each. Word
    matching can't group answers this short: on a live run it led with a vague catch-all and showed price (40% of
    objections by keyword) as 14 of 87, and counted "my existing ScreenBar" and "ScreenBar I already own" apart.
    Any list the model can't sort (offline provider, error, skipped answers) keeps its word-based groups."""
    kinds = ["objections"] + (["takeaways", "fixes", "alternatives"] if interviews and stats.get("interviews") else []) + (["glance"] if stats.get("attention") else [])
    stats["grouped_by"] = {k: "word matching" for k in kinds}
    if llm().provider == "fake":
        return
    jobs = {"objections": _objection_items(agents, verdicts, final)}
    if "takeaways" in kinds:
        jobs |= {"takeaways": _takeaway_items(agents, interviews), "fixes": _fix_items(agents, interviews), "alternatives": _alternative_items(agents, interviews)}
    if "glance" in kinds:
        jobs["glance"] = _glance_items(agents, verdicts)
    results = await asyncio.gather(*(_model_groups(items, kind, stimulus, meter) for kind, items in jobs.items()), return_exceptions=True)
    other_last = lambda o: o["text"].lower() == "other"
    for (kind, items), groups in zip(jobs.items(), results):
        if isinstance(groups, BaseException) or not groups:
            log.warning("grouping %s by meaning failed, keeping word matching: %s", kind, groups if isinstance(groups, BaseException) else "unusable sort")
            continue
        stats["grouped_by"][kind] = "model"
        out = _grouped(items, groups)
        if kind == "objections":
            stats["objections"] = sorted(out, key=lambda o: (other_last(o), -(o["count"] * (1 + o["influence"]))))[:6]
            stats["top_objection"] = stats["objections"][0]["text"] if stats["objections"] else "none"
        elif kind == "takeaways":
            stats["interviews"]["themes"] = sorted(out, key=lambda o: (other_last(o), -o["count"]))[:6]
        elif kind == "fixes":
            stats["interviews"]["fixes"] = [{"text": o["text"], "count": o["count"]} for o in sorted(out, key=lambda o: (other_last(o), -o["count"]))[:5]]
        elif kind == "glance":
            stats["attention"]["glance"] = sorted(out, key=lambda o: (other_last(o), -o["count"]))[:5]
        else:
            stats["interviews"]["alternatives"] = [{"name": o["text"], "count": o["count"]} for o in sorted(out, key=lambda o: -o["count"]) if not other_last(o)][:6]


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


def _nice(x: float) -> float:
    return round(x) if x >= 10 else round(x, 2)


def _price_test(ivs: list[dict], price: str | None) -> dict | None:
    """Van Westendorp price sensitivity from the four price answers. The acceptable range runs from where 'too cheap'
    meets 'getting expensive' to where 'bargain' meets 'too expensive'; the optimal price is where 'too cheap' meets
    'too expensive'. Answers out of order (a bargain above too expensive) are left out, as is usual."""
    pts = []
    for iv in ivs:
        p = iv.get("price") or {}
        vals = [p.get(k) for k in ("tooCheap", "bargain", "gettingExpensive", "tooExpensive")]
        if all(isinstance(x, (int, float)) and x > 0 for x in vals) and vals == sorted(vals):
            pts.append(vals)
    if not price or len(pts) < 10:
        return None
    A = np.array(pts, dtype=float)
    grid = np.geomspace(A.min(), A.max(), 400)
    falling = lambda col: (A[:, col][None, :] >= grid[:, None]).mean(axis=1)  # share for whom price p is still this cheap
    rising = lambda col: (A[:, col][None, :] <= grid[:, None]).mean(axis=1)   # share for whom price p is already this dear

    def meet(down: np.ndarray, up: np.ndarray) -> float:
        hit = up >= down
        return float(grid[int(np.argmax(hit))] if hit.any() else grid[-1])
    too_cheap, bargain, expensive, too_dear = falling(0), falling(1), rising(2), rising(3)
    lo, hi = sorted((meet(too_cheap, expensive), meet(bargain, too_dear)))
    out = {"currency": re.sub(r"[\d,.\s]+", "", price) or "", "n": len(pts), "dropped": len(ivs) - len(pts),
           "range": [_nice(lo), _nice(hi)], "optimal": _nice(meet(too_cheap, too_dear)), "indifference": _nice(meet(bargain, expensive))}
    shown = float(m.group(0).replace(",", "")) if (m := re.search(r"\d[\d,]*(?:\.\d+)?", price)) else None
    if shown:
        out |= {"shown": _nice(shown), "tooExpensiveAtShown": _pct(int((A[:, 3] <= shown).sum()), len(pts)),
                "bargainAtShown": _pct(int((A[:, 1] >= shown).sum()), len(pts))}
    return out


def _buying_stats(ivs: list[dict], price: str | None) -> dict:
    """Purchase likelihood, choice share and the price test, from the questions added to the exit interview."""
    lik = [iv["likelihood"] for iv in ivs if "likelihood" in iv]
    if not lik:  # older runs
        return {}
    n = len(lik)
    ch = Counter(iv.get("choice") for iv in ivs if "choice" in iv)
    mean = float(np.mean(lik))
    return {
        "likelihood": {"mean": round(mean, 1), "expectedBuyers": round(mean * 10), "top2": _pct(sum(1 for x in lik if x >= 8), n),
                       "dist": [sum(1 for x in lik if lo <= x <= hi) for lo, hi in ((0, 0), (1, 2), (3, 4), (5, 5), (6, 7), (8, 9), (10, 10))]},
        "choice": {"this": _pct(ch["This one"], n), "alternative": _pct(ch["The alternative I named"], n), "neither": _pct(ch["Neither"], n)},
        "price": _price_test(ivs, price),
    }


def _interview_stats(agents: list[dict], interviews: dict[int, dict], price: str | None = None) -> dict | None:
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
        if name and _alt_key(name) not in _NO_ALTERNATIVE:
            alts.setdefault(_alt_key(name), [name, 0])[1] += 1
    themes = _themes(_takeaway_items(agents, interviews))
    fixes = _themes(_fix_items(agents, interviews), max_themes=5)
    quotes = []
    for intent in INTENTS:
        for a, iv in sorted((r for r in rows if r[1]["intent"] == intent), key=lambda r: -r[0]["influence"])[:3]:
            quotes.append({"agent": _who(a), "intent": intent, "text": iv["quote"]})
    return {
        "n": n, "nps": round((prom - det) / n * 100), "promoters": _pct(prom, n), "passives": _pct(n - prom - det, n), "detractors": _pct(det, n),
        "changedMind": {"no": _pct(ch["No"], n), "positive": _pct(ch["More positive"], n), "negative": _pct(ch["More negative"], n)},
        "vsAlternatives": {"better": _pct(vs["Better"], n), "same": _pct(vs["About the same"], n), "worse": _pct(vs["Worse"], n), "unknown": _pct(vs["Don't know any"], n)},
        "alternatives": [{"name": d, "count": c} for d, c in sorted(alts.values(), key=lambda x: -x[1])[:6]],
        "themes": themes,
        "fixes": [{"text": f["text"], "count": f["count"]} for f in fixes],
        "quotes": quotes,
        **_buying_stats([iv for _, iv in rows], price),
    }


def _glance_items(agents: list[dict], verdicts: dict[int, dict]) -> list[tuple[str, float, str]]:
    """What people took in within two seconds, from those who stopped."""
    return [(v["two_second_takeaway"], a["influence"], _who(a)) for a in agents if (v := verdicts.get(a["id"])) and v.get("noticed")
            and v.get("two_second_takeaway", "").strip().lower().rstrip(".") not in ("nothing", "none", "")]


def _attention_stats(agents: list[dict], verdicts: dict[int, dict]) -> dict | None:
    """Would they have stopped, would they click, by where they met it. None for business ideas and older runs."""
    rows = [(a, v) for a in agents if (v := verdicts.get(a["id"])) and "noticed" in v]
    if not rows:
        return None
    n = len(rows)
    clicks = Counter(v.get("would_click", "No") for _, v in rows)
    by_place: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for _, v in rows:
        b = by_place[v.get("placement", "Unknown")]
        b[0] += 1; b[1] += bool(v["noticed"]); b[2] += v.get("would_click") == "Yes"
    return {
        "n": n, "stopRate": _pct(sum(1 for _, v in rows if v["noticed"]), n),
        "click": {"yes": _pct(clicks["Yes"], n), "maybe": _pct(clicks["Maybe"], n), "no": _pct(clicks["No"], n)},
        "byPlacement": sorted(({"placement": p, "n": c[0], "stopRate": _pct(c[1], c[0]), "clickRate": _pct(c[2], c[0])} for p, c in by_place.items()), key=lambda x: -x["n"]),
        "glance": _themes(_glance_items(agents, verdicts), max_themes=5),
    }


def attention_summary(stats: dict) -> str:
    at = stats.get("attention")
    if not at:
        return ""
    places = "; ".join(f"{p['placement']}: {p['stopRate']}% stop, {p['clickRate']}% click (n={p['n']})" for p in at["byPlacement"][:8])
    glance = "; ".join(f"{g['text']} ({g['count']})" for g in at["glance"][:5]) or "nothing clear"
    return (f"ATTENTION (each person met it where they usually meet ads): {at['stopRate']}% would have stopped scrolling; would click yes {at['click']['yes']}%, "
            f"maybe {at['click']['maybe']}%. By placement: {places}. What those who stopped took in within 2 seconds: {glance}.")


def interview_summary(stats: dict) -> str:
    """Exit-interview results as text for the research team and the report author."""
    iv = stats.get("interviews")
    if not iv:
        return "EXIT INTERVIEWS: none (the run stopped before them)."
    alts = ", ".join(f"{a['name']} ({a['count']})" for a in iv["alternatives"]) or "none named"
    themes = "\n".join(f"  {t['count']}x {t['text']}" for t in iv["themes"][:5])
    fixes = "; ".join(f"{f['text']} ({f['count']})" for f in iv["fixes"]) or "none"
    buying = ""
    if iv.get("likelihood"):
        lk, ch, pr = iv["likelihood"], iv["choice"], iv.get("price")
        buying = (f"\nPurchase likelihood (0-10, labelled): mean {lk['mean']}, so about {lk['expectedBuyers']}% expected to buy as stated (people overstate; "
                  f"real conversion is usually far lower); {lk['top2']}% said 8-10. Choice today: this {ch['this']}%, their alternative {ch['alternative']}%, neither {ch['neither']}%.")
        if pr:
            c = pr["currency"]
            buying += (f" Price test (n={pr['n']}): acceptable range {c}{pr['range'][0]}-{c}{pr['range'][1]}, optimal {c}{pr['optimal']}"
                       + (f"; at the shown {c}{pr['shown']}, {pr['tooExpensiveAtShown']}% call it too expensive and {pr['bargainAtShown']}% a bargain." if "shown" in pr else "."))
    return (f"EXIT INTERVIEWS (n={iv['n']}, asked after the discussion; the intent split is what they said here): NPS {iv['nps']} "
            f"(promoters {iv['promoters']}%, detractors {iv['detractors']}%). Changed mind since first impression: more positive {iv['changedMind']['positive']}%, "
            f"more negative {iv['changedMind']['negative']}%. Versus what they use or know: better {iv['vsAlternatives']['better']}%, same {iv['vsAlternatives']['same']}%, "
            f"worse {iv['vsAlternatives']['worse']}%, know none {iv['vsAlternatives']['unknown']}%. Alternatives they'd choose instead: {alts}.{buying}\n"
            f"What they concluded (grouped):\n{themes}\nWhat would win the non-buyers over: {fixes}")


def compute_stats(agents: list[dict], verdicts: dict[int, dict], final: dict[int, float], mind_changes: int, posts: list[dict],
                  interviews: dict[int, dict] | None = None, price: str | None = None) -> dict:
    """`price` is the price the crowd saw (interview.price_shown), for the price test."""
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
    attention = _attention_stats(agents, verdicts)

    def seg(group: str, key):
        m: dict[str, list[tuple[float, bool, dict]]] = defaultdict(list)
        for a, s in zip(agents, fs):
            m[str(key(a))].append((float(s), buys[a["id"]], verdicts.get(a["id"]) or {}))
        out = []
        for k, v in m.items():
            row = {"segment": k, "group": group, "score": round(float(np.mean([s for s, _, _ in v])), 1), "n": len(v), "intent": _pct(sum(b for _, b, _ in v), len(v))}
            if attention:  # stop rate and click intent per segment
                row |= {"stop": _pct(sum(1 for *_, x in v if x.get("noticed")), len(v)), "click": _pct(sum(1 for *_, x in v if x.get("would_click") == "Yes"), len(v))}
            out.append(row)
        return out
    groups = [("Profession", lambda a: a["professionGroup"]), ("Ideology", lambda a: a["ideology"]), ("Income", lambda a: a["income"]), ("Age", lambda a: a["ageBand"]),
              ("Tech adoption", lambda a: a["tech"]), ("Role", lambda a: a["role"]), ("Country GDP tier", lambda a: a["extra"]["gdpTier"]), ("Trust posture", lambda a: a["extra"]["trust"]),
              ("Decision heuristic", lambda a: a["extra"]["heuristic"]), ("Temperament", lambda a: a["extra"]["temperament"]), ("Mood today", lambda a: a["mood"])]
    if attention:
        groups.append(("Where they saw it", lambda a: (verdicts.get(a["id"]) or {}).get("placement", "Unknown")))
    if agents and "lifeStage" in agents[0]["extra"]:  # people from the current library
        groups += [("Life stage", lambda a: a["extra"]["lifeStage"]), ("Where they live", lambda a: a["extra"]["settlement"]),
                   ("Attitude to ads", lambda a: a["extra"]["adReceptivity"])]
    segments = []
    for group, key in groups:
        segments += sorted(seg(group, key), key=lambda s: -s["score"])
    prof = [s for s in segments if s["group"] == "Profession"]
    best = (prof[0]["segment"], prof[0]["score"]) if prof else ("", 0.0)
    worst = (prof[-1]["segment"], prof[-1]["score"]) if prof else ("", 0.0)

    objections = _cluster_objections(_objection_items(agents, verdicts, final))

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
        "n": n, "mean": mean, "sd": sd, "intent": intent, "intent_source": intent_source, "interviews": _interview_stats(agents, interviews, price), "attention": attention,
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
            f"SAMPLE COMPOSITION: {composition}\n\n{market_summary(market)}\n\n{interview_summary(stats)}\n\n{attention_summary(stats)}\n\nWrite the report fields. JSON only.")
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
        "intentSplit": stats["intent"], "intentSource": stats["intent_source"], "interviews": stats["interviews"], "attention": stats["attention"],
        "research": {
            "methodology": out["methodology_note"], "limitations": out["limitations"], "team": experts, "otherFindings": others[:12],
            "composition": composition, "diversity": stats["diversity"], "topPosts": stats["top_posts"][:10], "mindChanges": stats["mind_changes"],
            "groupedBy": stats.get("grouped_by", {}),
            "costUsd": round(cost_usd, 3),
        },
    }
