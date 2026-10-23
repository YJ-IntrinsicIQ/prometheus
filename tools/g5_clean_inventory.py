#!/usr/bin/env python3
"""M63 / G5 — clean provenance inventory (read-only, zero AI calls).

Classifies every clause that carries a negation in four overlapping scopes into six semantic classes (pipelines/g5_provenance.py), keeps the rule that excluded each
non-genuine clause, resolves the genuine ones per evidence group (company, FY, topic, class, scope) once, and writes the corrected denominator, the groups and the review queue.

Scopes (overlap in text; never added):  S1 candidate answers · S2 candidate Story/Panel/Explorer · S3 frozen approved answers · S4 served Story/Panel/Explorer
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
from pipelines import g4_investor_answers as g4  # noqa: E402
from pipelines import g5_provenance as G  # noqa: E402
from pipelines import m59_question_batch as m59  # noqa: E402
from g5_absence_inventory import answer_fields  # noqa: E402

SPLIT = re.compile(r"(?<=[.;])\s+(?=[A-Z“\d])")
LABEL_SOURCES = {"not in the extracted records", "not extracted into the records", "not extracted", "not in the records"}


def surface_entries(surfaces: dict) -> dict:
    """{(company, surface): [entry dict]} rebuilt from the `.g5_absence[i].<field>` items a provenance-aware loader attaches."""
    out: dict = {}
    for company, surfs in surfaces.items():
        for s in surfs:
            ents: dict = {}
            for it in s["items"]:
                m = re.match(r"\.g5_absence\[(\d+)\]\.(\w+)$", it["path"])
                if m:
                    ents.setdefault(int(m.group(1)), {})[m.group(2)] = it["text"]
            out[(company, s["name"])] = list(ents.values())
    return out


def surface_units(surfaces: dict, scope: str):
    """(company, surface, location, claim text, label_line) for every negation-bearing string, with label cells joined to the text they label."""
    for company, surfs in surfaces.items():
        for s in surfs:
            if s["name"].startswith("question:"):
                continue
            by = {i["path"]: i["text"] for i in s["items"]}
            for it in s["items"]:
                p, t = it["path"], it["text"]
                if ".g5_absence[" in p or p.endswith((".id", ".href", ".slug", ".route")) or re.fullmatch(r"[a-z0-9][a-z0-9_\-]*", t):      # provenance items and identifiers are not rendered claims
                    continue
                if t.strip().lower().rstrip(".") in LABEL_SOURCES:
                    m = re.match(r"(.*\.rows\[\d+\])\[1\]$", p)
                    sib = by.get(m.group(1) + "[0]") if m else by.get(p.rsplit(".", 1)[0] + ".text") if p.endswith(".source") else None
                    yield company, s["name"], p, f"{sib}: {t}" if sib else t, (sib or t)
                    continue
                for sent in SPLIT.split(" ".join(t.split())):
                    yield company, s["name"], p, sent, None


def run(args) -> dict:
    registry = json.loads((REPO / "governance" / "approval_registry.json").read_text())["approvals"]
    cos = {k: m59.Co(k, registry) for k in m59.COMPANIES}
    ledgers = {k: g4.Ledger(k, Path(args.root)) for k in m59.COMPANIES}
    sys_ok, sys_basis = G.system_limitation_ok(Path(args.root))
    units: list[dict] = []

    def add(scope, company, surface, location, text, protected, entries=None, label_line=None):
        for clause in ([text] if label_line else G.split_clauses(text)):
            cls, rule = G.classify(clause) if not label_line else ((G.ANALYTIC_UNCERTAINTY, "label-joined-analytic") if G.ANALYTIC_RX.search(label_line) or re.search(r"outcome|integration|execution", label_line, re.I) else (G.EXTRACTION_ABSENCE, "label-joined-to-text"))
            if cls is None:
                continue
            units.append({"anchor": label_line, "scope": scope, "company": company, "surface": surface, "location": location, "clause": clause[:320], "class": cls, "rule": rule, "protected": protected, "context": text,
                          "entries": entries})

    for k in m59.COMPANIES:
        for qid in g4.QUESTION_FOR_AREA.values():
            f = Path(args.cand) / f"{k}__{qid}.candidate.json"
            if f.exists():
                a = json.loads(f.read_text())["answer"]
                for loc, t in answer_fields(a):
                    for sent in SPLIT.split(" ".join(t.split())):
                        add("S1_candidate_answers", k, f"{k}:{qid}", loc, sent, False, a.get("g5_absence") or [])
        for qid in sorted({r.split(":", 1)[1] for r in registry if r.startswith(k + ":")}):
            a = cos[k].approved(qid)
            if a:
                for loc, t in answer_fields(a):
                    for sent in SPLIT.split(" ".join(t.split())):
                        add("S3_frozen_approved_answers", k, f"{k}:{qid}", loc, sent, True, a.get("g5_absence") if "g5_absence" in a else None)
    if getattr(args, "bundle", None):
        for f in sorted((Path(args.bundle) / "answers").glob("*.json")):
            d = json.loads(f.read_text())
            k = d["slot"].split(":", 1)[0]
            for loc, t in answer_fields(d["answer"]):
                for sent in SPLIT.split(" ".join(t.split())):
                    add("S5_proposed_bundle_answers", k, d["slot"], loc, sent, False, (d["answer"].get("g5_absence") or []) + (d["answer"].get("g5_review_pending") or []))
    for scope, path, prot in (("S2_candidate_story_panel_explorer", args.surf_cand, False), ("S4_served_story_panel_explorer", args.surf_served, True)):
        sd = json.loads(Path(path).read_text())
        ents = surface_entries(sd)
        if scope.startswith("S2") and getattr(args, "sandbox_root", ""):          # the ledger is attached as non-enumerable audit data, so link against the ledger files themselves
            for k in m59.COMPANIES:
                lf = Path(args.sandbox_root) / "companies" / k / "company_memory" / "ask_intrinsiciq" / "g5_absence_provenance.json"
                led_entries = json.loads(lf.read_text())["entries"] if lf.exists() else []
                for s_ in sd.get(k, []):
                    ents[(k, s_["name"])] = led_entries
        for company, surf, loc, text, lab in surface_units(sd, scope):
            add(scope, company, surf, loc, text, prot, ents.get((company, surf)) if scope.startswith("S2") else None, lab)

    # resolve per evidence group
    groups: dict[str, dict] = {}
    for u in units:
        if u["class"] in G.GENUINE:
            L = ledgers[u["company"]]
            topic = G.topic_of(u["clause"]) or G.topic_of(u.get("context", ""))
            u["topic"] = topic
            scope_kind = "record" if u["class"] == G.EXTRACTION_ABSENCE else "source"
            if u["class"] == G.INAPPLICABLE_MEASURE:
                u["group"] = G.group_key(u["company"], L.fy, topic or "unprofiled", u["class"], "business-model")
            else:
                u["group"] = G.group_key(u["company"], L.fy, topic or "unprofiled", u["class"], scope_kind)
            if u["group"] not in groups:
                groups[u["group"]] = {"group": u["group"], "company": u["company"], "fy": L.fy, "topic": topic, "class": u["class"], "assertion_scope": scope_kind,
                                      "resolution": G.resolve(L, topic) if topic else {"state": "UNPROFILED", "verified": False, "basis": "no evidence profile exists for this assertion",
                                                                                         "locator": "", "contradicts": False, "uncertainty": "needs a profile or human review"},
                                      "example_claim": u["clause"], "occurrences": 0, "scopes": Counter(), "locators_hint": []}
                if not topic:
                    groups[u["group"]]["locators_hint"] = G.generic_locators(L, u["clause"])
            gr = groups[u["group"]]
            gr["occurrences"] += 1
            gr["scopes"][u["scope"]] += 1
        elif u["class"] == G.UI_OR_SYSTEM and u["rule"] == "system-limitation":
            u["system_verified"], u["system_basis"] = sys_ok, sys_basis

    # per-unit status: the evidence gate decides (pipelines/g5_verify), unit by unit
    for u in units:
        if u["class"] not in G.GENUINE:
            continue
        j = G.judge(ledgers[u["company"]], u["clause"], u["class"], u.get("context", ""))
        u["status"], u["state"], u["reasons"], u["level"] = j["status"], j["state"], j["reasons"], j["level"]
        u["record_verified"] = j.get("record_verified", False)
        u["record_statement_ok"] = j.get("record_statement_ok", False)
        u["rewrite"] = j.get("rewrite")
        entries = u.get("entries")

        def match(e):
            c = u["clause"]
            return (e.get("claim") and (e["claim"] in c or c in e["claim"])) or (e.get("anchor") and e["anchor"] in c)
        u["claim_linked_entry"] = (any(match(e) for e in entries) if entries is not None else None)

    return {"units": units, "groups": list(groups.values()), "system_limitation": {"verified": sys_ok, "basis": sys_basis}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--surf-cand", required=True)
    ap.add_argument("--surf-served", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--bundle", default="")
    ap.add_argument("--sandbox-root", default="")
    a = ap.parse_args()
    res = run(a)
    for gr in res["groups"]:
        gr["scopes"] = dict(gr["scopes"])
    Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    by = defaultdict(Counter)
    for u in res["units"]:
        by[u["scope"]][u["class"]] += 1
    for s, v in sorted(by.items()):
        print(s, dict(v))
    st = defaultdict(Counter)
    for u in res["units"]:
        if "status" in u:
            st[u["scope"]][u["status"]] += 1
    for s, v in sorted(st.items()):
        print(s, dict(v))
    print("groups:", len(res["groups"]), Counter(g["resolution"]["state"] for g in res["groups"]))


if __name__ == "__main__":
    main()
