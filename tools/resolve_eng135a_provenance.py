#!/usr/bin/env python3
"""Mechanically resolve ENG-135A provenance references without semantic review.

Resolution strategy (in priority order):
1. Search company_memory artifacts by source_item_id (existing logic).
2. If the matched item has extraction_item_id, look in fy{year}/extracted/
   extracted_{module}.json for that item_id and retrieve source_chunk.
3. If item has source_item_id + source_year but no extraction_item_id, hop
   through fy{year}/intelligence/company_intelligence.json to get item_id
   then look in fy{year}/extracted/extracted_capital_allocations.json.
4. For non-.json source_artifact (e.g. "capacity", "project"), look directly
   in fy{period}/extracted/extracted_{artifact}.json by item_id.
5. Try all source_refs (not just the first); first EXACT wins, then PARTIAL.
6. Synthetic IDs (capex_fy*, share_issue_*, roi_ledger_*) → LEGACY_UNRECOVERABLE.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {"RESOLVED_EXACT", "RESOLVED_PARTIAL", "UNRESOLVABLE_WITH_REASON"}
REASONS = {
    "SOURCE_ARTIFACT_MISSING", "SOURCE_ITEM_ID_MISSING", "SOURCE_ITEM_NOT_FOUND",
    "SOURCE_ITEM_AMBIGUOUS", "SOURCE_DOCUMENT_MISSING", "PAGE_METADATA_MISSING",
    "PASSAGE_NOT_PERSISTED", "BROKEN_REFERENCE", "LEGACY_PROVENANCE_GAP",
    "UNSUPPORTED_ARTIFACT_TYPE", "LEGACY_UNRECOVERABLE",
}

_SYNTHETIC_ID_RE = re.compile(
    r"^(capex_fy|share_issue_fy|roi_ledger_fy|working_capital_fy|dividends_fy|buybacks_fy|"
    r"debt_repayment_fy|equity_issuance_fy|acquisitions_fy|capex_|share_issue_|roi_ledger_)"
)

# Modules whose extraction files hold source_chunk
_MODULE_EXTRACTION_MAP = {
    "capital_allocation_timeline.json": "capital_allocations",
    "capital_allocation": "capital_allocations",
    "capacity": "capacity",
    "project": "projects",
    "projects": "projects",
    "management_commitments": "promises",
    "management_progression": "promises",
}


def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _paths(company: str, artifact: str) -> List[Path]:
    name = Path(artifact or "").name
    if not name:
        return []
    roots = [
        ROOT / f"companies/{company}/company_memory",
        ROOT / f"companies/{company}/company_memory/multi_year",
    ]
    roots += list((ROOT / f"companies/{company}").glob("*/intelligence"))
    return [p / name for p in roots if (p / name).exists()]


def _fingerprint(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text.strip().lower()).encode()).hexdigest()


def _is_synthetic_id(item_id: str) -> bool:
    return bool(_SYNTHETIC_ID_RE.match(str(item_id or "")))


def _find_in_data(data: Any, item_id: str, source_year: Optional[str] = None) -> List[Dict]:
    matches = []
    for obj in _walk(data):
        if not isinstance(obj, dict):
            continue
        candidate_id = obj.get("source_item_id") or obj.get("item_id") or obj.get("id")
        if candidate_id != item_id:
            continue
        if source_year and obj.get("source_year") and obj.get("source_year") != source_year:
            continue
        matches.append(obj)
    return matches


def _score(obj: Dict) -> int:
    return sum(bool(obj.get(k)) for k in (
        "exact_source_passage", "source_chunk", "source_text", "evidence_text",
        "excerpt", "short_excerpt", "page", "source_page", "evidence_references",
    ))


def _extraction_path(company: str, source_year: str, module: str) -> Optional[Path]:
    """Return path to fy{year}/extracted/extracted_{module}.json if it exists."""
    year = str(source_year or "").strip().lower()
    if not year:
        return None
    candidates = [
        ROOT / f"companies/{company}/{year}/extracted/extracted_{module}.json",
        ROOT / f"companies/{company}/{year}/extracted/clean_{module}.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _lookup_extraction_passage(
    company: str, source_year: str, module: str, item_id: str
) -> Tuple[Optional[str], Optional[int]]:
    """Return (source_chunk, page) from the extraction layer, or (None, None)."""
    path = _extraction_path(company, source_year, module)
    if not path:
        return None, None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None, None
    items = data if isinstance(data, list) else []
    for obj in items:
        if not isinstance(obj, dict):
            continue
        if obj.get("item_id") == item_id or obj.get("id") == item_id:
            chunk = obj.get("source_chunk")
            # capacity/projects use source_chunks (list) instead
            if not chunk:
                chunks = obj.get("source_chunks") or []
                if chunks and isinstance(chunks[0], dict):
                    chunk = chunks[0].get("text")
                elif chunks and isinstance(chunks[0], str):
                    chunk = chunks[0]
            page = obj.get("page") or obj.get("source_page")
            return chunk, page
    return None, None


def _hop_ci_to_extraction(
    company: str, source_item_id: str, source_year: str
) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """Two-hop: timeline source_item_id → company_intelligence item_id → extracted source_chunk.
    Returns (passage, page, extraction_item_id).
    """
    year = str(source_year or "").strip().lower()
    if not year:
        return None, None, None
    ci_path = ROOT / f"companies/{company}/{year}/intelligence/company_intelligence.json"
    if not ci_path.exists():
        return None, None, None
    try:
        ci = json.loads(ci_path.read_text())
    except Exception:
        return None, None, None
    # Find the item by id == source_item_id
    ca_items = ((ci.get("financial") or {}).get("capital_allocation") or {}).get("items") or []
    for obj in ca_items:
        if obj.get("id") == source_item_id:
            ext_id = obj.get("item_id")
            if not ext_id:
                return None, None, None
            chunk, page = _lookup_extraction_passage(
                company, source_year, "capital_allocations", ext_id
            )
            return chunk, page, ext_id
    return None, None, None


def _resolve_one_ref(company: str, ref: Dict) -> Dict:
    """Attempt to resolve a single source_ref. Returns resolution dict."""
    artifact = ref.get("source_artifact") or ""
    item_id = ref.get("source_item_id") or ""
    source_year = ref.get("source_year") or ref.get("period") or ""

    if not item_id:
        return {"status": "UNRESOLVABLE_WITH_REASON", "reason": "SOURCE_ITEM_ID_MISSING",
                "artifact": artifact, "item_id": None, "passage": None, "page": None, "ext_id": None}

    if _is_synthetic_id(item_id):
        return {"status": "UNRESOLVABLE_WITH_REASON", "reason": "LEGACY_UNRECOVERABLE",
                "artifact": artifact, "item_id": item_id, "passage": None, "page": None, "ext_id": None}

    # Check if this is a non-.json artifact (capacity, project, etc.)
    has_extension = artifact.endswith(".json")
    if not has_extension:
        # Direct extraction lookup by source_artifact family name
        module = _MODULE_EXTRACTION_MAP.get(artifact, artifact)
        chunk, page = _lookup_extraction_passage(company, source_year, module, item_id)
        if chunk:
            return {"status": "RESOLVED_EXACT", "reason": None,
                    "artifact": f"fy{source_year}/extracted/extracted_{module}.json",
                    "item_id": item_id, "passage": chunk, "page": page, "ext_id": item_id}
        # Found in extraction but no chunk
        ext_path = _extraction_path(company, source_year, module)
        if ext_path:
            return {"status": "RESOLVED_PARTIAL", "reason": "PASSAGE_NOT_PERSISTED",
                    "artifact": str(ext_path.relative_to(ROOT)),
                    "item_id": item_id, "passage": None, "page": page, "ext_id": item_id}
        return {"status": "UNRESOLVABLE_WITH_REASON", "reason": "SOURCE_ARTIFACT_MISSING",
                "artifact": artifact, "item_id": item_id, "passage": None, "page": None, "ext_id": None}

    # Standard lookup in company_memory paths
    matched_paths = _paths(company, artifact)
    if not matched_paths:
        return {"status": "UNRESOLVABLE_WITH_REASON", "reason": "SOURCE_ARTIFACT_MISSING",
                "artifact": artifact, "item_id": item_id, "passage": None, "page": None, "ext_id": None}

    all_matches = []
    for path in matched_paths:
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        for obj in _find_in_data(data, item_id, source_year or None):
            all_matches.append((path, obj))

    if not all_matches:
        return {"status": "UNRESOLVABLE_WITH_REASON", "reason": "SOURCE_ITEM_NOT_FOUND",
                "artifact": artifact, "item_id": item_id, "passage": None, "page": None, "ext_id": None}

    # Pick best match by score
    best_path, best_obj = max(all_matches, key=lambda po: _score(po[1]))
    page = (
        (best_obj.get("evidence_references") or {}).get("page")
        if isinstance(best_obj.get("evidence_references"), dict)
        else best_obj.get("page") or best_obj.get("source_page") or ref.get("page")
    )

    # Check if it carries extraction_item_id for direct extraction hop
    ext_id = best_obj.get("extraction_item_id")
    if ext_id and source_year:
        module = _MODULE_EXTRACTION_MAP.get(artifact, "capital_allocations")
        chunk, ext_page = _lookup_extraction_passage(company, source_year, module, ext_id)
        if chunk:
            return {"status": "RESOLVED_EXACT", "reason": None,
                    "artifact": str(best_path.relative_to(ROOT)),
                    "item_id": item_id, "passage": chunk, "page": ext_page or page, "ext_id": ext_id}

    # Try two-hop through company_intelligence → extracted
    if source_year and artifact == "capital_allocation_timeline.json":
        chunk, ci_page, ci_ext_id = _hop_ci_to_extraction(company, item_id, source_year)
        if chunk:
            return {"status": "RESOLVED_EXACT", "reason": None,
                    "artifact": str(best_path.relative_to(ROOT)),
                    "item_id": item_id, "passage": chunk,
                    "page": ci_page or page, "ext_id": ci_ext_id}

    # Partial: item found in company_memory but no verbatim passage
    direct_evidence = (
        best_obj.get("exact_source_passage") or best_obj.get("source_text") or
        best_obj.get("evidence_text") or best_obj.get("excerpt")
    )
    if direct_evidence:
        return {"status": "RESOLVED_EXACT" if page else "RESOLVED_PARTIAL",
                "reason": None if page else "PAGE_METADATA_MISSING",
                "artifact": str(best_path.relative_to(ROOT)),
                "item_id": item_id, "passage": direct_evidence, "page": page, "ext_id": None}

    reason = "PASSAGE_NOT_PERSISTED" if not direct_evidence else "PAGE_METADATA_MISSING"
    return {"status": "RESOLVED_PARTIAL", "reason": reason,
            "artifact": str(best_path.relative_to(ROOT)),
            "item_id": item_id, "passage": None, "page": page, "ext_id": None}


def resolve(packet: Dict) -> Dict:
    refs = packet.get("source_refs") or []
    if not refs:
        return _out(packet, "UNRESOLVABLE_WITH_REASON", "SOURCE_ITEM_ID_MISSING", None, None, None)

    best_exact: Optional[Dict] = None
    best_partial: Optional[Dict] = None

    for ref in refs:
        r = _resolve_one_ref(packet["company"], ref)
        if r["status"] == "RESOLVED_EXACT" and best_exact is None:
            best_exact = r
        elif r["status"] == "RESOLVED_PARTIAL" and best_partial is None:
            best_partial = r

    winner = best_exact or best_partial
    if winner:
        detail = {"passage": winner["passage"], "page": winner["page"],
                  "fingerprint": _fingerprint(winner["passage"]) if winner["passage"] else "NOT_AVAILABLE"}
        status = winner["status"]
        reason = winner["reason"]
        artifact = winner["artifact"]
        item_id = winner["item_id"]
        return _out(packet, status, reason, artifact, item_id, detail)

    # All refs failed — return the first failure reason
    first = _resolve_one_ref(packet["company"], refs[0])
    return _out(packet, first["status"], first["reason"], first["artifact"], first["item_id"], None)


def _out(packet, status, reason, artifact, item_id, detail):
    return {
        "company": packet.get("company"),
        "record_id": packet.get("record_id"),
        "source_artifact": (packet.get("source_refs") or [{}])[0].get("source_artifact"),
        "source_item_id": item_id,
        "resolution_status": status,
        "resolved_artifact": artifact,
        "resolved_item_id": item_id,
        "source_document": None,
        "page": (detail or {}).get("page") if detail else None,
        "section": None,
        "passage": (detail or {}).get("passage") if detail else None,
        "fingerprint_status": (detail or {}).get("fingerprint") if detail else "NOT_AVAILABLE",
        "reason_code": reason,
        "resolver_notes": "Mechanical resolution only; no semantic correctness asserted.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()

    packets = json.loads((ROOT / "governance/ENG135A_PRODUCTION_EVIDENCE_PACKETS.json").read_text())["packets"]
    results = [resolve(p) for p in packets]

    out = ROOT / "governance/ENG135A_PROVENANCE_RESOLUTION_RESULTS.json"
    from collections import Counter
    summary = dict(Counter(r["resolution_status"] for r in results))
    reasons = dict(Counter(r["reason_code"] for r in results if r["reason_code"]))
    out.write_text(json.dumps({
        "schema_version": "eng135a.provenance_resolution.v2",
        "summary": {
            "total": len(results),
            "exact": summary.get("RESOLVED_EXACT", 0),
            "partial": summary.get("RESOLVED_PARTIAL", 0),
            "unresolvable": summary.get("UNRESOLVABLE_WITH_REASON", 0),
        },
        "reason_counts": reasons,
        "records": results,
    }, indent=2) + "\n")

    by = {(r["company"], r["record_id"]): r for r in results}
    for p in packets:
        r = by[(p.get("company"), p["record_id"])]
        p.update({
            "provenance_resolution_status": r["resolution_status"],
            "resolved_artifact_path": r["resolved_artifact"],
            "resolved_source_item_id": r["resolved_item_id"],
            "source_document": r["source_document"],
            "resolved_page": r["page"],
            "resolved_section": r["section"],
            "exact_evidence_passage": r["passage"],
            "fingerprint_result": r["fingerprint_status"],
            "provenance_unresolved_reason": r["reason_code"],
        })
    packets_path = ROOT / "governance/ENG135A_PRODUCTION_EVIDENCE_PACKETS.json"
    packets_path.write_text(json.dumps(
        {"schema_version": "eng135a.evidence_packets.v2", "packets": packets}, indent=2
    ) + "\n")

    if args.validate:
        assert len(results) == 32 and all(r["resolution_status"] in STATUSES for r in results)

    print("RESOLVER_RECORDS =", len(results))
    print(summary)
    print(reasons)


if __name__ == "__main__":
    main()
