"""Diagnose what the social stage did to opinions: was the information environment balanced, and why did people move?

    uv run python scripts/social_diagnostics.py run_A [run_B ...]
"""
from __future__ import annotations

import bisect
import collections
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db  # noqa: E402

# Phrases in an agent's own "why" that point to conformity (moving with the room) vs new information.
CONFORMITY = re.compile(r"\b(nobody|no one|no-one|still no|still hasn|everyone|the thread|the group|the feed keeps|keeps (asking|circling|repeating)|pile|consensus|others (are|keep)|several people|many people|reinforc)", re.I)
NEW_INFO = re.compile(r"\b(point(ed)? out|made me realis|hadn'?t (thought|considered)|didn'?t (think|consider|notice)|good point|fair point|new (angle|info)|convinced|showed me)", re.I)


def mean(xs):
    xs = list(xs)
    return statistics.mean(xs) if xs else float("nan")


def diagnose(rid: str) -> dict:
    evs = db.events_from(rid, 0)
    agents = {a["id"]: a for a in db.get_run_agents(rid) if a.get("verdict")}
    s1 = mean(a["verdict"]["score"] for a in agents.values())
    fin = mean((a["finalScore"] if a["finalScore"] is not None else a["verdict"]["score"]) for a in agents.values())

    posts = [e for e in evs if e["kind"] in ("post", "reply")]
    seed_posts = [e for e in posts if e.get("round") == 0]
    by_author: dict[int, list[tuple[int, float]]] = collections.defaultdict(list)
    post_score = {}
    for e in posts:
        by_author[e["agentId"]].append((e["round"], e["score"]))
        post_score[e["id"]] = e["score"]

    def author_score_at(aid: int, r: int) -> float | None:
        lst = by_author.get(aid)
        if not lst:
            return None
        i = bisect.bisect_right([x[0] for x in lst], r) - 1
        return lst[max(0, i)][1]

    exp_scores = [s for e in evs if e["kind"] == "exposure" for s in [author_score_at(e["fromAgentId"], e["round"])] if s is not None]

    # Replies received per post, by the post's score band.
    replies_to = collections.Counter(e["toPostId"] for e in evs if e["kind"] == "reply")
    band = lambda s: "low (<4)" if s < 4 else "mid (4-6.4)" if s < 6.5 else "high (6.5+)"
    band_posts = collections.defaultdict(list)
    for e in posts:
        band_posts[band(e["score"])].append(replies_to.get(e["id"], 0))

    mcs = [e for e in evs if e["kind"] == "mind_change"]
    toward = 0
    for e in mcs:
        cs = author_score_at(e["causedBy"], e["round"])
        if cs is not None and abs(cs - e["to"]) < abs(cs - e["from"]):
            toward += 1

    # Every acting agent's per-round score change and stated reason.
    deltas = collections.defaultdict(list)
    downs = ups = conf_down = info_down = conf_up = info_up = 0
    supp_down = supp_up = 0
    for a in agents.values():
        prev = a["verdict"]["score"]
        for act in a.get("actions", []):
            if act["round"] == 0:
                continue
            if "suppressedScore" in act:
                supp_down += act["suppressedScore"] < act["score"]; supp_up += act["suppressedScore"] > act["score"]
            d = act["score"] - prev
            deltas[act["round"]].append(d)
            why = act.get("why", "") or ""
            if d <= -0.25:
                downs += 1; conf_down += bool(CONFORMITY.search(why)); info_down += bool(NEW_INFO.search(why))
            elif d >= 0.25:
                ups += 1; conf_up += bool(CONFORMITY.search(why)); info_up += bool(NEW_INFO.search(why))
            prev = act["score"]

    return {
        "stage-1 mean": f"{s1:.2f}", "final mean": f"{fin:.2f}", "shift": f"{fin - s1:+.2f}",
        "seed posts (round 0): n / mean": f"{len(seed_posts)} / {mean(e['score'] for e in seed_posts):.2f}",
        "all posts+replies: mean score": f"{mean(e['score'] for e in posts):.2f}",
        "what people saw (exposure-wtd)": f"{mean(exp_scores):.2f}",
        "saw minus crowd stage-1": f"{mean(exp_scores) - s1:+.2f}",
        **{f"replies per post, {k}": f"{mean(v):.2f} (n={len(v)})" for k, v in sorted(band_posts.items())},
        "mind changes: down / up": f"{sum(1 for e in mcs if e['to'] < e['from'])} / {sum(1 for e in mcs if e['to'] > e['from'])}",
        "mind changes toward the cause": f"{toward / max(1, len(mcs)):.0%}",
        **{f"mean change, round {r}": f"{mean(v):+.2f} (n={len(v)})" for r, v in sorted(deltas.items())},
        "moves down: conformity / new-info reasons": f"{conf_down}/{downs} ({conf_down / max(1, downs):.0%}) / {info_down}/{downs}",
        "moves up: conformity / new-info reasons": f"{conf_up}/{ups} / {info_up}/{ups}",
        "unattributed moves reverted: down / up": f"{supp_down} / {supp_up}",
    }


def main() -> None:
    rids = sys.argv[1:]
    res = [diagnose(r) for r in rids]
    w = max(len(k) for k in res[0])
    print(" " * (w + 2) + "".join(f"{r:>26}" for r in rids))
    for k in res[0]:
        print(f"{k:<{w + 2}}" + "".join(f"{d.get(k, '-'):>26}" for d in res))


if __name__ == "__main__":
    main()
