#!/usr/bin/env python3
"""M63 / G5 — read-only, reproducible claim-level absence inventory. Zero AI calls; writes only the two output paths given.

Scopes (never summed with each other: they overlap in rendered text):
  S1  the 16 scratch candidate answers (every rendered field, incl. key_points / evidence_gaps / precision facts)
  S2  Story / Panel / Explorer rendered from the candidate overlay root  (surfaces other than question views)
  S3  the 91 frozen approved answers (the objects the registry pins)
  S4  Story / Panel / Explorer rendered from the current served data     (surfaces other than question views)

A claim is an *applicable* absence claim only if g4.claim_kind says the sentence asserts that a disclosure is absent from the source or from the records. Analytic unknowns
(a cause or outcome is not established) and method wording are counted, not audited. Each applicable claim is checked against the filing with the independent anchor
review (topic -> anchor patterns); a topic with no anchor family is UNRESOLVED / NOT TESTED, never assumed.

    python3 tools/g5_absence_inventory.py --cand OUT --root ROOT --surf-cand F.json --surf-served F.json --json out.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from pipelines import g4_investor_answers as g  # noqa: E402
from pipelines import m59_question_batch as m59  # noqa: E402

SCREEN = re.compile(r"not in the records|records? (?:do(?:es)? not|don.t) (?:show|say|contain|include|record|carry|hold)|not disclosed|undisclosed|not (?:yet )?(?:available|stated|reported|recorded|extracted|provided)|unavailable|is silent|are silent|do(?:es)? not (?:disclose|state|say|report|provide)|cannot be (?:determined|tested|measured|verified|assessed|built)|\bmissing\b|\blacks?\b|no (?:market data|disclosure)", re.I)  # wide net: its hits that claim_kind did not classify are listed as NOT TESTED, never counted as claims
SPLIT = re.compile(r"(?<=[.;])\s+(?=[A-Z“\d])")
FIELDS = ("simple_answer", "what_may_mean_economically", "what_is_not_yet_proven", "why_it_matters", "investor_interpretation", "what_evidence_shows", "what_to_monitor", "key_points", "evidence_gaps")


def answer_fields(a: dict):
    for f in FIELDS:
        v = a.get(f)
        for i, s in enumerate(v if isinstance(v, list) else [v]):
            if s:
                yield f"{f}[{i}]" if isinstance(v, list) else f, str(s)
    for i, d in enumerate(a.get("deterministic_precision_facts") or []):
        if isinstance(d, dict):
            if d.get("semantic_meaning"):
                yield f"deterministic_precision_facts[{i}].semantic_meaning", str(d["semantic_meaning"])
            v = str(d.get("value") or "")
            if v and not v.startswith("“"):
                yield f"deterministic_precision_facts[{i}].value", v


def review(L, topic: str, sent: str, entries: list[dict] | None) -> dict:
    """Primary-source review for one applicable claim."""
    src_level = bool(g.SRC_ABSENCE.search(sent)) and not g.RECORD_WORDS.search(sent) and not g.ABS_EXTR.search(sent) and not g.ABS_NA.search(sent)
    na = bool(g.ABS_NA.search(sent))
    prov = "none"
    mine = [e for e in (entries or []) if e.get("topic") == topic]
    if mine:
        prov = "; ".join(f"{e['state']} ({e['class']})" for e in mine)
    elif entries is not None:
        prov = "none linked to this claim"
    if na:
        required, status = "NOT_APPLICABLE", ("SUPPORTED" if L.bank and re.search(r"receivable|working capital|inventory|capex|capital expenditure", sent, re.I) else "UNRESOLVED")
        locator = "business-model class (bank vs industrial) — not a filing locator"
    elif topic in g.ANCHORS:
        ev = g.anchor_hits(L, topic)
        found = ev["chunks_matching"] or (topic == "concentration" and g.find_disclosure(L, g.BANK_CONC if L.bank else g.CUSTOMER_CONC))
        locator = f"{ev['chunks_matching']} matching sections, e.g. pp. {', '.join(map(str, ev['example_pages'][:4]))}" if ev["chunks_matching"] else (f"{ev['chunks_searched']} sections searched; no match" if not found else "disclosure found by note parser")
        if found:
            required = "NOT_EXTRACTED"
            status = "CONTRADICTED" if src_level else "SUPPORTED_AS_RECORD_GAP"
        else:
            required, status = "NOT_DISCLOSED", "SUPPORTED_AS_SEARCHED_ABSENCE"
    else:
        required, status, locator = "UNDETERMINED", "UNRESOLVED", "NOT TESTED: no anchor family exists for this topic"
    fix = {"CONTRADICTED": "replace the absence statement with what the filing carries (quote or paraphrase with page) and state NOT_EXTRACTED only for the unrecorded part",
           "SUPPORTED_AS_RECORD_GAP": "attach a NOT_EXTRACTED entry (topic-bound) naming the filing sections that carry it",
           "SUPPORTED_AS_SEARCHED_ABSENCE": "attach a NOT_DISCLOSED entry with the anchor review as provenance",
           "SUPPORTED": "attach a NOT_APPLICABLE entry with the business-model reason",
           "UNRESOLVED": "manual primary-source review needed before any state can be assigned"}[status]
    if entries is not None and mine and status not in ("CONTRADICTED", "UNRESOLVED"):
        fix = "none — claim-linked state present"
    return {"source_level": src_level, "required_state": required, "existing_provenance": prov, "review_locator": locator, "status": status, "correction": fix}


def inventory(args) -> dict:
    registry = json.loads((REPO / "governance" / "approval_registry.json").read_text())["approvals"]
    cos = {k: m59.Co(k, registry) for k in m59.COMPANIES}
    ledgers = {k: g.Ledger(k, Path(args.root)) for k in m59.COMPANIES}
    claims: list[dict] = []
    other = defaultdict(Counter)
    screen: list[dict] = []

    def scan(scope, company, surface, location, text, entries, protected, answer_id=""):
        for sent in SPLIT.split(" ".join(str(text).split())):
            if sent.rstrip().endswith("?"):
                continue
            kind = g.claim_kind(sent)
            if not kind:
                if SCREEN.search(re.sub(r"“[^”]*”", " ", sent)):
                    screen.append({"scope": scope, "company": company, "answer_or_surface": surface, "location": location, "text": sent[:240], "status": "NOT TESTED (screen hit, not classified by claim_kind)", "protected_approval_blocks_correction": protected})
                continue
            if kind != "disclosure_absence":
                other[scope][kind] += 1
                continue
            topic = g.claim_topic(sent)
            r = review(ledgers[company], topic, sent, entries)
            claims.append({"scope": scope, "company": company, "answer_or_surface": surface, "answer_id": answer_id, "location": location, "claim": sent[:300], "applicable": True, "topic": topic,
                           **r, "protected_approval_blocks_correction": protected})

    # S1 / S3 answers
    for k, co in cos.items():
        for qid in g.QUESTION_FOR_AREA.values():
            f = Path(args.cand) / f"{k}__{qid}.candidate.json"
            if f.exists():
                a = json.loads(f.read_text())["answer"]
                for loc, t in answer_fields(a):
                    scan("S1_candidate_answers", k, f"{k}:{qid}", loc, t, a.get("g5_absence") or [], False, f"candidate:{k}:{qid}")
    approved = 0
    for k, co in cos.items():
        for qid in sorted({r.split(":", 1)[1] for r in registry if r.startswith(k + ":")}):
            a = co.approved(qid)
            if not a:
                continue
            approved += 1
            for loc, t in answer_fields(a):
                scan("S3_frozen_approved_answers", k, f"{k}:{qid}", loc, t, None, True, f"approved:{k}:{qid}")
    # S2 / S4 surfaces
    for scope, path in (("S2_candidate_story_panel_explorer", args.surf_cand), ("S4_served_story_panel_explorer", args.surf_served)):
        d = json.loads(Path(path).read_text())
        for k, surfs in d.items():
            for s in surfs:
                if s["name"].startswith("question:"):
                    continue
                for i, line in enumerate(s["text"].split("\n")):
                    scan(scope, k, s["name"], f"line {i}", line, None, scope.startswith("S4"), "")
    return {"approved_answers_scanned": approved, "claims": claims, "screen_hits_not_classified": screen, "non_applicable_counts": {k: dict(v) for k, v in other.items()}}


def esc(t: str) -> str:
    return str(t).replace("|", "\\|").replace("\n", " ")


def markdown(res: dict) -> str:
    cl, scr = res["claims"], res["screen_hits_not_classified"]
    scopes = sorted({c["scope"] for c in cl})
    o = ["# M63 / G5 — Full-scope absence inventory (claim level, read-only)\n",
         "Generated by `tools/g5_absence_inventory.py` (no AI calls, writes only this file and the JSON beside it). **Scopes overlap in rendered text and are never added together.** Only sentences that assert a disclosure is absent from the source or the records are *applicable* claims; analytic unknowns and method wording are counted separately; wide-net screen hits that the claim classifier did not classify are listed as **NOT TESTED**, not counted as claims. Statuses are machine-assigned from the independent anchor review (topic → filing search, independent of the G3 family search); no human primary-source read has been done except where the report says so. `UNRESOLVED` = no anchor family exists for that topic, so the claim is neither supported nor contradicted.\n",
         f"Approved answers scanned: {res['approved_answers_scanned']} (the 91 frozen answers). Protected approval: S3 and S4 content cannot be corrected without a CTO-approved replacement; S1/S2 are scratch.\n",
         "## Summary\n", "| Scope | applicable claims | SUPPORTED (record gap, state needed) | SUPPORTED (searched absence) | CONTRADICTED | UNRESOLVED / NOT TESTED | analytic unknowns (not contractual) | method wording | screen hits NOT TESTED |", "|---|---|---|---|---|---|---|---|---|"]
    for sc in scopes:
        v = Counter(c["status"] for c in cl if c["scope"] == sc)
        n = res["non_applicable_counts"].get(sc, {})
        o.append(f"| {sc} | {sum(v.values())} | {v['SUPPORTED_AS_RECORD_GAP']} | {v['SUPPORTED_AS_SEARCHED_ABSENCE']} | {v['CONTRADICTED']} | {v['UNRESOLVED']} | {n.get('analytic_unknown', 0)} | {n.get('method', 0)} | {sum(1 for x in scr if x['scope'] == sc)} |")
    s1 = [c for c in cl if c["scope"].startswith("S1")]
    o.append(f"\nS1 claims with a claim-linked state: {sum(1 for c in s1 if c['existing_provenance'] not in ('none', 'none linked to this claim'))} of {len(s1)}.\n")
    cols = "| company | answer / surface | location | exact claim | required state | existing provenance | primary-source review (locator) | status | required correction | protected approval blocks correction |\n|---|---|---|---|---|---|---|---|---|---|"
    row = lambda c: f"| {c['company']} | {esc(c['answer_or_surface'])} | {esc(c['location'])} | {esc(c['claim'])} | {c['required_state']} | {esc(c['existing_provenance'])} | {esc(c['review_locator'])} | {c['status']} | {esc(c['correction'])} | {'yes' if c['protected_approval_blocks_correction'] else 'no'} |"
    for sc, title in (("S1_candidate_answers", "S1 — 16 candidate answers (every claim)"), ("S3_frozen_approved_answers", "S3 — 91 frozen approved answers (every applicable claim)")):
        o += [f"\n## {title}\n", cols] + [row(c) for c in cl if c["scope"] == sc]
    for sc, title in (("S2_candidate_story_panel_explorer", "S2 — candidate Story / Panel / Explorer"), ("S4_served_story_panel_explorer", "S4 — served Story / Panel / Explorer")):
        grp: dict = defaultdict(list)
        for c in cl:
            if c["scope"] == sc:
                grp[(c["topic"], c["claim"], c["status"], c["required_state"], c["review_locator"], c["correction"])].append(c)
        o += [f"\n## {title}: distinct claims (identical text grouped; full rows in the JSON)\n", "| claim | topic | occurrences | companies / surfaces | required state | review (locator) | status | required correction | protected approval blocks correction |", "|---|---|---|---|---|---|---|---|---|"]
        for (topic, claim, st, req, loc, fix), rows in sorted(grp.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1])):
            where = ", ".join(sorted({f"{r['company']}:{r['answer_or_surface']}" for r in rows}))
            o.append(f"| {esc(claim)} | {topic} | {len(rows)} | {esc(where[:260])} | {req} | {esc(loc)} | {st} | {esc(fix)} | {'yes' if rows[0]['protected_approval_blocks_correction'] else 'no'} |")
    o += ["\n## Screen hits the claim classifier did not classify (NOT TESTED)\n", "| scope | company | surface | text | status |", "|---|---|---|---|---|"]
    o += [f"| {x['scope']} | {x['company']} | {esc(x['answer_or_surface'])} | {esc(x['text'])} | {x['status']} |" for x in scr if x["scope"].startswith(("S1", "S3"))]
    o.append("\n(S2/S4 screen hits are in the JSON only.)")
    return "\n".join(o) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--surf-cand", required=True)
    ap.add_argument("--surf-served", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--md", default="")
    args = ap.parse_args()
    res = inventory(args)
    Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    if args.md:
        Path(args.md).write_text(markdown(res))
    by = defaultdict(Counter)
    for c in res["claims"]:
        by[c["scope"]][c["status"]] += 1
    print("approved answers scanned:", res["approved_answers_scanned"])
    for s, v in sorted(by.items()):
        print(s, sum(v.values()), dict(v))
    print(res["non_applicable_counts"])
    print("screen hits not classified:", dict(Counter(x["scope"] for x in res["screen_hits_not_classified"])))


if __name__ == "__main__":
    main()
