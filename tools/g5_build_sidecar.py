#!/usr/bin/env python3
"""M63 / G5 — claim ledger for the Story / Panel / Explorer projections (sandbox only; reads a clean-inventory run, writes one JSON per company under --root).

Each ledger entry binds the exact rendered clause to the evidence-supported state (pipelines/g5_provenance.judge). The file is written to
<root>/companies/<key>/company_memory/ask_intrinsiciq/g5_absence_provenance.json inside the SANDBOX root; the protected repository folder is never written.
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
from pipelines import g4_investor_answers as g4  # noqa: E402
from pipelines import g5_provenance as G  # noqa: E402
from pipelines import m59_question_batch as m59  # noqa: E402


def entry(L, u: dict, sys_ok: bool, sys_basis: str) -> dict | None:
    cls, rule, clause = u["class"], u["rule"], u["clause"]
    base = {"claim": clause, "anchor": u.get("anchor") or clause}
    if cls == G.UI_OR_SYSTEM and rule == "system-limitation":
        return {**base, "kind": "system_limitation", "topic": "system", "state": None, "verification": "VERIFIED" if sys_ok else "UNRESOLVED", "basis": sys_basis, "locator": "", "evidence_group": f"system|market_data", "review": None}
    if cls == G.UI_OR_SYSTEM and rule == "system-coverage":
        ok, why = G.coverage_check(L, clause)
        return {**base, "kind": "system_coverage", "topic": "coverage", "state": None, "verification": "VERIFIED" if ok else "UNRESOLVED", "basis": why, "locator": "", "evidence_group": f"system|coverage|{L.key}", "review": None}
    if cls not in G.GENUINE:
        return None
    j = G.judge(L, clause, cls, u.get("context", ""))
    if j["status"] in ("VERIFIED_NOT_EXTRACTED", "VERIFIED_NOT_APPLICABLE"):
        v = "VERIFIED"
    elif j["status"] == "UNRESOLVED_NOT_DISCLOSED_CANDIDATE":
        v = "PENDING_HUMAN_CONFIRMATION"
    elif j["status"] in ("CONTRADICTED", "WRONG_NOT_APPLICABLE_CLAIM"):
        v = "CONTRADICTED"
    else:
        v = "UNRESOLVED"
    fb = j.get("fallback")
    return {**base, "kind": "absence", "topic": j["topic"] or "other", "state": j["state"], "verification": v, "basis": j["basis"], "locator": j.get("locator", ""), "evidence_group": j.get("evidence_group", ""),
            "review": j.get("review"), "reasons": j.get("reasons", []), "record_verified": j.get("record_verified", False), "fallback": fb,
            "record_statement_ok": j.get("record_statement_ok", False), "replacement": None if (u.get("anchor") and u["anchor"] != clause) else j.get("rewrite"), "sentence": u.get("context") or clause, "supplement": j.get("supplement") or None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True, help="clean-inventory JSON (tools/g5_clean_inventory.py)")
    ap.add_argument("--ledger-root", required=True, help="evidence root used to resolve (read-only)")
    ap.add_argument("--sandbox-root", required=True, help="sandbox root to write the ledgers into")
    ap.add_argument("--scope", default="S2_candidate_story_panel_explorer")
    ap.add_argument("--surfaces", default="", help="rendered-surface dump (pass 1): positive event claims are checked on every rendered string")
    a = ap.parse_args()
    inv = json.loads(Path(a.inventory).read_text())
    sys_ok, sys_basis = inv["system_limitation"]["verified"], inv["system_limitation"]["basis"]
    by: dict[str, dict] = {}
    for k in m59.COMPANIES:
        L = g4.Ledger(k, Path(a.ledger_root))
        for u in inv["units"]:
            if u["scope"] == a.scope and u["company"] == k:
                e = entry(L, u, sys_ok, sys_basis)
                if e:
                    by.setdefault(k, {})[(e["claim"], e["anchor"])] = e
        if a.surfaces:
            from pipelines import g5_verify as V
            for sf in json.loads(Path(a.surfaces).read_text()).get(k, []):
                if sf["name"].startswith("question:"):
                    continue
                for it in sf["items"]:
                    for ev in V.verify_events(L, it["text"]):
                        if ev["status"] != "SUPPORTED_EVENT":
                            by.setdefault(k, {})[(ev["phrase"], "event")] = {"claim": ev["phrase"], "anchor": ev["phrase"], "kind": "event_claim", "topic": "event", "state": None, "verification": "UNRESOLVED", "basis": ev["status"],
                                                                         "locator": "", "evidence_group": f"event|{k}|{ev['entity']}", "review": None, "reasons": [ev["status"]], "record_verified": False, "fallback": None,
                                                                         "record_statement_ok": False, "replacement": ev["replacement"], "sentence": ev["phrase"], "supplement": None}
        entries = list(by.get(k, {}).values())
        d = Path(a.sandbox_root) / "companies" / k / "company_memory" / "ask_intrinsiciq"
        assert d.is_dir() and not d.is_symlink(), f"sandbox folder must be a real directory, not the protected link: {d}"
        (d / "g5_absence_provenance.json").write_text(json.dumps({"company": k, "scope": a.scope, "entries": entries}, ensure_ascii=False, indent=1))
        print(k, len(entries))


if __name__ == "__main__":
    main()
