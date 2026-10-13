#!/usr/bin/env python3
"""M63 / G5 — remaining human-review queue (read-only). One item per distinct evidence group that the machine could not resolve; every occurrence in the proposed bundle and
the candidate projections is attached to it, so one primary-source decision resolves all of them. Excerpts are UNREVIEWED machine retrievals offered to the reviewer, not evidence."""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from pipelines import g4_investor_answers as g4  # noqa: E402
from pipelines import g5_provenance as G  # noqa: E402

PRIORITY = {"revenue_split": 1, "commitment_followthrough": 4, "capex_split": 2, "segment_margins": 2, "interest_coverage": 3, "roce": 3, "book_value": 3, "market_size": 3, "competitive_position": 3,
            "rd_spend": 3, "management_incentives": 3, "peer_comparison": 3, "contingent": 3, "project_outcomes": 4, "capital_outcomes": 4, "risk_response": 4, "management_depth": 5}
PNAME = {1: "P1 contradicted or potentially contradicted by the filing", 2: "P2 assertion that information is not disclosed", 3: "P3 important financial measure called unavailable",
         4: "P4 management delivery / economic-outcome claim", 5: "P5 lower-impact missing-data label"}


def excerpt(L, pages: list[int], topic: str | None, clause: str, n: int = 260) -> list[dict]:
    p = G.PROFILES.get(topic) if topic else None
    pats = list(p["anchors"]) if p else [w for w in re.findall(r"[a-z]{6,}", clause.lower())][:3]
    out = []
    for c in G._chunks(L):
        if c.get("page") in pages:
            body = " ".join(str(c.get("text", "")).split())
            for pat in pats:
                m = re.search(pat, body, re.I)
                if m:
                    lo = max(0, m.start() - 80)
                    out.append({"page": c["page"], "unreviewed_excerpt": body[lo:lo + n]})
                    break
        if len(out) >= 3:
            break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--json", required=True)
    a = ap.parse_args()
    inv = json.loads(Path(a.inventory).read_text())
    ledgers: dict = {}
    items: dict[str, dict] = {}
    for u in inv["units"]:
        if u["class"] not in G.GENUINE or not u.get("status", "").startswith("UNRESOLVED"):
            continue
        if not (u["scope"].startswith("S5") or u["scope"].startswith("S2")):
            continue
        L = ledgers.setdefault(u["company"], g4.Ledger(u["company"], Path(a.root)))
        topic = u.get("topic")
        rid = G.review_id(u["company"], topic, u["clause"])
        it = items.setdefault(rid, {"review": rid, "company": u["company"], "fy": L.fy, "topic": topic, "claims": {}, "occurrences": {"S5_proposed_bundle_answers": [], "S2_candidate_story_panel_explorer": []}, "status": u["status"]})
        it["claims"][re.sub(r"\d[\d,.]*", "#", u["clause"])[:200]] = u["clause"][:260]
        it["occurrences"][u["scope"]].append(f"{u['surface']} @ {u['location']}")
    out = []
    for rid, it in items.items():
        L = ledgers[it["company"]]
        topic = it["topic"]
        res = G.resolve(L, topic) if topic else None
        pages = (res or {}).get("filing_weak_pages") or []
        if not pages and not topic:
            pages = G.generic_locators(L, next(iter(it["claims"].values())))
        pri = PRIORITY.get(topic, 5 if not topic else 4)
        if res and res["state"] == "NOT_DISCLOSED_CANDIDATE":
            q = f"Does the {L.fy.upper()} annual report carry '{res['label']}' anywhere (tables, notes, MD&A, charts)? The machine searched {res['chunks_searched']} sections with the topic's anchor family and found nothing."
            opts = "CONFIRM NOT_DISCLOSED (reviewer cites the sections read) | FOUND at page X (state becomes NOT_EXTRACTED and the sentence is reworded)"
        elif res and res["state"] == "REVIEW":
            q = f"Do the pages listed carry '{res['label']}' as a figure or disclosure for {L.name}, or only mention the topic?"
            opts = "CARRIED at page X (NOT_EXTRACTED; reword) | MENTION ONLY (NOT_DISCLOSED after full read)"
        else:
            q = "No evidence profile exists for this assertion. Decide what disclosure it concerns and whether the annual report carries it."
            opts = "Assign a topic and decide as above | reclassify the sentence as analytic or explanatory (no state needed)"
        out.append({**it, "claims": list(it["claims"].values()), "priority": pri, "priority_name": PNAME[pri], "question": q, "recommended_decision": opts,
                    "locator_candidates": pages, "machine_basis": (res or {}).get("basis", "no profile"), "unreviewed_excerpts": excerpt(L, pages, topic, next(iter(it["claims"].values()))) if pages else [],
                    "occurrence_counts": {k: len(v) for k, v in it["occurrences"].items()}})
    out.sort(key=lambda x: (x["priority"], x["company"], x["review"]))
    Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(len(out), "review items;", {PNAME[p][:2]: sum(1 for o in out if o["priority"] == p) for p in sorted(PNAME)})


if __name__ == "__main__":
    main()
