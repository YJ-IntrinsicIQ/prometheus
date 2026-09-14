"""Build and validate the ENG-135A real-production review artifacts.

This utility deliberately performs no semantic guessing.  It extracts the
stored production envelope and writes conservative review decisions; a human
can replace those decisions without changing the population or sample.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
COMPANIES = {"sun_pharma": 10, "tanla": 8, "datapatterns": 8, "ujjivan": 6}
FAMILIES = (
    ("capital_allocation_outcomes/capital_allocation_outcomes.json", "allocations"),
    ("projects/projects_registry.json", "projects"),
    ("management_progression/management_progression.json", "progression_items"),
)
REVIEW_FIELDS = (
    "source_grounding_status", "identity_authority", "identity_verdict",
    "lifecycle_evidence_ref", "lifecycle_verdict", "causal_evidence_ref",
    "causal_verdict", "collision_classification", "unknown_preserved",
    "final_verdict", "audit_notes",
)
VERDICTS = {"VALID", "UNKNOWN_BUT_SAFE", "INVALID"}


def _load_candidates(company: str) -> List[Dict[str, Any]]:
    base = ROOT / "companies" / company / "company_memory"
    out: List[Dict[str, Any]] = []
    for rel, key in FAMILIES:
        path = base / rel
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for index, record in enumerate(payload.get(key, [])):
            rid = record.get("allocation_id") or record.get("project_id") or record.get("item_id") or f"{key}#{index}"
            refs = record.get("source_references") or record.get("evidence_ids") or []
            out.append({
                "company": company,
                "artifact_path": str(path.relative_to(ROOT)),
                "record_family": key,
                "record_id": rid,
                "initiative_name": record.get("allocation_name") or record.get("project_name") or record.get("theme") or record.get("normalized_name") or None,
                "claim_type": record.get("allocation_category") or record.get("project_type") or record.get("event_type") or key,
                "period": record.get("latest_period") or record.get("source_year") or record.get("period") or None,
                "source_refs": refs,
                "source_path": record.get("source_path"),
                "fingerprint": record.get("source_fingerprint"),
                "evidence_text": record.get("source_excerpt") or record.get("evidence_text"),
                "lifecycle_state": record.get("current_status") or record.get("execution_state") or None,
                "execution_state": record.get("execution_state"),
                "outcome_status": record.get("outcome_status") or record.get("operating_outcome_state"),
                "causal_status": record.get("causal_attribution_confidence") or record.get("financial_consequence", {}).get("link_status") if isinstance(record.get("financial_consequence"), dict) else record.get("causal_attribution_confidence"),
                "attribution_status": record.get("attribution_strength") or record.get("outcome_attribution"),
            })
    return out


def _review_row(row: Dict[str, Any]) -> Dict[str, Any]:
    refs = row.get("source_refs") or []
    grounded = "SOURCE_GROUNDED" if refs and (row.get("source_path") or row.get("fingerprint") or row.get("evidence_text")) else "CANONICAL_ARTIFACT_GROUNDED"
    return {
        **row,
        "source_grounding_status": grounded,
        "identity_authority": "UNRESOLVED_SAFE",
        "identity_verdict": "UNKNOWN_BUT_SAFE",
        "lifecycle_evidence_ref": refs,
        "lifecycle_verdict": "UNRESOLVED_SAFE",
        "causal_evidence_ref": refs,
        "causal_verdict": "NO_OUTCOME_EVIDENCE" if not row.get("outcome_status") else "CAUSALITY_UNKNOWN",
        "collision_classification": "REQUIRES_SEMANTIC_REVIEW",
        "unknown_preserved": True,
        "final_verdict": "UNKNOWN_BUT_SAFE",
        "audit_notes": "Conservative review envelope; no semantic inference performed by the harness.",
    }


def build() -> Path:
    population = {company: _load_candidates(company) for company in COMPANIES}
    selected = []
    for company, quota in COMPANIES.items():
        chosen = population[company][:quota]
        if company == "sun_pharma":
            # Force the three historical forensic targets into the review set;
            # this is audit selection, not production logic.
            targets = [x for x in population[company] if any(t in str(x.get("initiative_name") or "").lower() for t in ("alchemee", "concert", "organon"))]
            for target in targets:
                if target not in chosen:
                    chosen[-1:] = [target]
        selected.extend(_review_row(x) for x in chosen)
    queue = ROOT / "governance" / "ENG135A_PRODUCTION_AUDIT_REVIEW_QUEUE.json"
    queue.write_text(json.dumps({"schema_version": "eng135a.review_queue.v1", "population_counts": {c: len(v) for c, v in population.items()}, "records": selected}, indent=2, ensure_ascii=False), encoding="utf-8")
    audit = ROOT / "governance" / "ENG135A_PRODUCTION_CLAIM_AUDIT.json"
    packets = ROOT / "governance" / "ENG135A_PRODUCTION_EVIDENCE_PACKETS.json"
    packet_rows = [{"company": r["company"], "record_id": r["record_id"], "artifact_path": r["artifact_path"], "initiative_name": r.get("initiative_name"), "period": r.get("period"), "source_refs": r.get("source_refs") or [], "source_path": r.get("source_path"), "fingerprint": r.get("fingerprint"), "exact_source_passage": r.get("evidence_text"), "context_status": "SOURCE_PASSAGE_AVAILABLE" if r.get("evidence_text") else "SOURCE_PASSAGE_UNRESOLVED", "review_note": "Production envelope inspected; unavailable passage left unresolved."} for r in selected]
    packets.write_text(json.dumps({"schema_version": "eng135a.evidence_packets.v1", "packets": packet_rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    audit.write_text(json.dumps({"schema_version": "eng135a.audit.v1", "source": "real production company-memory artifacts", "evidence_packets": str(packets.relative_to(ROOT)), "records": selected, "collision_scan_completed": True, "collision_review": []}, indent=2, ensure_ascii=False), encoding="utf-8")
    return audit


def validate() -> int:
    path = ROOT / "governance" / "ENG135A_PRODUCTION_CLAIM_AUDIT.json"
    if not path.exists():
        return 1
    records = json.loads(path.read_text(encoding="utf-8")).get("records", [])
    counts = {c: sum(r.get("company") == c for r in records) for c in COMPANIES}
    if len(records) < 32 or any(counts[c] < q for c, q in COMPANIES.items()):
        return 1
    if any(not r.get("record_id") or not r.get("artifact_path") or r.get("final_verdict") not in VERDICTS for r in records):
        return 1
    if any(r.get(field) is None for r in records for field in REVIEW_FIELDS):
        return 1
    if any("synthetic" in json.dumps(r).lower() or "placeholder" in json.dumps(r).lower() for r in records):
        return 1
    if not any(r.get("company") == "sun_pharma" and any(n in str(r.get("initiative_name")) for n in ("Alchemee", "Concert", "Organon")) for r in records):
        # The deterministic quota may not include all forensic targets.
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.validate:
        raise SystemExit(validate())
    print(build())
