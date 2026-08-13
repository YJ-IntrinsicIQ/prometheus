from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from .contracts import DIRECTION_VALUES, EVIDENCE_CONFIDENCE_LEVELS, MANAGEMENT_QUALITY_ASSESSMENTS, MANAGEMENT_QUALITY_DIMENSIONS


FORBIDDEN_PUBLIC_TERMS = (
    "source_chunk",
    "raw_text",
    "full_text",
    "llm",
    "prompt",
    "score",
    "management_score",
)


def _scan_forbidden_terms(value: Any) -> List[str]:
    found: List[str] = []
    if isinstance(value, dict):
        for item in value.values():
            found.extend(_scan_forbidden_terms(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_scan_forbidden_terms(item))
    else:
        text = str(value or "").lower()
        for term in FORBIDDEN_PUBLIC_TERMS:
            if term in text and term not in found:
                found.append(term)
    return found


def _scan_forbidden_keys(value: Any) -> List[str]:
    found: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key or "").strip().lower()
            if lowered in {"score", "management_score", "overall_score"} or lowered.endswith("_score"):
                if lowered not in found:
                    found.append(lowered)
            found.extend(_scan_forbidden_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_scan_forbidden_keys(item))
    return found


def _validate_confidence(value: Any) -> bool:
    return isinstance(value, dict) and all(key in value for key in ("level", "basis", "limitations"))


def validate_management_quality_payload(
    summary_payload: Dict[str, Any],
    *,
    dimensions_payload: Dict[str, Any] | None = None,
    evidence_payload: Dict[str, Any] | None = None,
    lineage_report: Dict[str, Any] | None = None,
    upstream_validation: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []

    dimensions = (dimensions_payload or {}).get("dimensions") or []
    evidence_items = (evidence_payload or {}).get("evidence_items") or []
    dimension_map = {str(item.get("dimension") or ""): item for item in dimensions if str(item.get("dimension") or "").strip()}
    required_dimensions = list(MANAGEMENT_QUALITY_DIMENSIONS)

    for dimension in required_dimensions:
        item = dimension_map.get(dimension)
        if item is None:
            issues.append({"code": "missing_dimension", "severity": "fail", "dimension": dimension, "message": "Required dimension is missing."})
            continue
        assessment = str(item.get("assessment") or "").strip().lower()
        direction = str(item.get("direction") or "").strip().lower()
        if dimension == "evidence_confidence":
            if assessment not in EVIDENCE_CONFIDENCE_LEVELS:
                issues.append({"code": "invalid_evidence_confidence", "severity": "fail", "dimension": dimension, "message": "Evidence confidence level is invalid."})
        elif assessment not in MANAGEMENT_QUALITY_ASSESSMENTS:
            issues.append({"code": "invalid_assessment", "severity": "fail", "dimension": dimension, "message": "Dimension assessment is invalid."})
        if direction not in DIRECTION_VALUES:
            issues.append({"code": "invalid_direction", "severity": "fail", "dimension": dimension, "message": "Dimension direction is invalid."})
        if not item.get("supporting_evidence") and assessment != "insufficient_evidence" and dimension != "evidence_confidence":
            issues.append({"code": "missing_supporting_evidence", "severity": "fail", "dimension": dimension, "message": "Supporting evidence is required unless evidence is insufficient."})
        if not _validate_confidence(item.get("confidence")):
            issues.append({"code": "invalid_confidence", "severity": "fail", "dimension": dimension, "message": "Confidence must include level, basis, and limitations."})
        if item.get("missing_critical_stream_groups") and assessment != "insufficient_evidence":
            issues.append({"code": "missing_critical_stream_not_capped", "severity": "fail", "dimension": dimension, "message": "A missing critical stream must cap the dimension at insufficient evidence."})
        if not item.get("conflicting_evidence") and assessment in {"mixed", "weak"} and dimension != "evidence_confidence":
            issues.append({"code": "missing_conflicting_evidence", "severity": "warning", "dimension": dimension, "message": "Conflicting evidence should remain visible."})

    if str(summary_payload.get("overall_view") or "").strip().lower() not in (*MANAGEMENT_QUALITY_ASSESSMENTS,):
        issues.append({"code": "invalid_overall_view", "severity": "fail", "message": "Overall view is invalid."})
    if str(summary_payload.get("overall_direction") or "").strip().lower() not in DIRECTION_VALUES:
        issues.append({"code": "invalid_overall_direction", "severity": "fail", "message": "Overall direction is invalid."})

    if not summary_payload.get("strongest_dimension") or not summary_payload.get("weakest_dimension"):
        issues.append({"code": "missing_summary_dimensions", "severity": "fail", "message": "Summary must identify strongest and weakest dimensions."})

    if not isinstance(summary_payload.get("evidence_confidence"), dict) or not _validate_confidence(summary_payload.get("evidence_confidence")):
        issues.append({"code": "invalid_summary_evidence_confidence", "severity": "fail", "message": "Summary evidence confidence must include level, basis, and limitations."})

    for field in ("what_strengthened_conviction", "what_weakened_conviction", "what_remains_unproven"):
        items = summary_payload.get(field) or []
        summaries = [str(item.get("summary") or "").strip() for item in items if isinstance(item, dict)]
        if len(summaries) != len(set(summaries)):
            issues.append({"code": f"duplicate_{field}", "severity": "fail", "message": f"Duplicate items detected in {field}."})

    if not any(item.get("source_stream") == "management_commitments" for item in evidence_items):
        issues.append({"code": "missing_commitment_evidence", "severity": "warning", "message": "No management commitments evidence was linked."})
    if not any(item.get("source_stream") in {"projects", "capacity"} for item in evidence_items):
        issues.append({"code": "missing_execution_evidence", "severity": "warning", "message": "Execution evidence is thin or missing."})
    if not any(item.get("source_stream") == "capital_allocation_outcomes" for item in evidence_items):
        issues.append({"code": "missing_capital_allocation_evidence", "severity": "warning", "message": "Capital allocation outcomes evidence is missing."})
    if not any(item.get("source_stream") in {"owner_earnings", "per_share_compounding"} for item in evidence_items):
        issues.append({"code": "missing_owner_alignment_evidence", "severity": "warning", "message": "Owner alignment evidence is thin or missing."})
    if not any(item.get("source_stream") == "risks" for item in evidence_items):
        issues.append({"code": "missing_risk_evidence", "severity": "warning", "message": "Risk-handling evidence is thin or missing."})

    if any(item.get("source_stream") == "investor_panel" for item in evidence_items):
        issues.append({"code": "downstream_dependency", "severity": "fail", "message": "Management Quality cannot consume Investor Panel or Committee evidence."})
    missing_critical = not any(item.get("source_stream") == "risks" for item in evidence_items) or not any(item.get("source_stream") == "capital_allocation_outcomes" for item in evidence_items)
    if missing_critical and str(summary_payload.get("overall_view") or "").lower() == "strong":
        issues.append({"code": "strong_with_missing_critical_streams", "severity": "fail", "message": "Overall management quality cannot be strong while critical streams are missing."})
    if missing_critical and str((summary_payload.get("evidence_confidence") or {}).get("level") or "").lower() == "high":
        issues.append({"code": "high_confidence_with_missing_critical_streams", "severity": "fail", "message": "Overall confidence cannot be high while critical streams are missing."})
    if lineage_report and lineage_report.get("status") == "fail":
        issues.append({"code": "stale_lineage", "severity": "fail", "message": "Management Quality predates one or more upstream dependencies."})
    for stream, status in (upstream_validation or {}).items():
        if status in {"fail", "failed", "missing"}:
            issues.append({"code": "invalid_upstream_stream", "severity": "fail", "stream": stream, "message": f"Upstream stream is not valid: {status}."})
        elif status not in {"pass", "passed"}:
            issues.append({"code": "degraded_upstream_stream", "severity": "warning", "stream": stream, "message": f"Upstream stream requires caution: {status}."})

    if (
        _scan_forbidden_terms(summary_payload)
        or _scan_forbidden_terms(dimensions_payload or {})
        or _scan_forbidden_terms(evidence_payload or {})
        or _scan_forbidden_keys(summary_payload)
        or _scan_forbidden_keys(dimensions_payload or {})
        or _scan_forbidden_keys(evidence_payload or {})
    ):
        issues.append({"code": "public_term_leak", "severity": "fail", "message": "Internal pipeline terminology leaked into public management-quality fields."})

    # deterministic shape check for evidence references
    for item in dimensions:
        for key in ("supporting_evidence", "conflicting_evidence", "what_strengthened", "what_weakened", "what_remains_unproven"):
            values = item.get(key) or []
            for entry in values:
                if not isinstance(entry, dict) or not entry.get("summary"):
                    issues.append({"code": "invalid_evidence_item", "severity": "fail", "dimension": item.get("dimension"), "message": f"{key} entries must be structured and non-empty."})
                    break

    status = "pass"
    if any(issue.get("severity") == "fail" for issue in issues):
        status = "fail"
    elif issues:
        status = "warning"
    return {"status": status, "issue_count": len(issues), "issues": issues}
