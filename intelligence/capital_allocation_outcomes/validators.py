from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Set

from knowledge.company_memory import parse_financial_year

from .contracts import ALLOCATION_CATEGORIES, ALLOCATION_CURRENT_STATUSES, ALLOCATION_OUTCOME_STATUSES


FORBIDDEN_PUBLIC_TERMS = (
    "source_chunk",
    "raw_text",
    "full_text",
    "llm",
    "prompt",
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


def _is_chronological(periods: Sequence[str]) -> bool:
    def key(value: str) -> tuple[int, str]:
        lowered = str(value or "").strip().lower()
        try:
            return (parse_financial_year(lowered), lowered)
        except Exception:
            return (10_000, lowered)

    return list(periods) == sorted(periods, key=key)


def _validate_confidence(value: Any) -> bool:
    return isinstance(value, dict) and all(key in value for key in ("level", "basis", "limitations"))


def validate_capital_allocation_outcomes_payload(
    outcomes_payload: Dict[str, Any],
    *,
    timelines_payload: Dict[str, Any] | None = None,
    assessments_payload: Dict[str, Any] | None = None,
    commitment_ids: Iterable[str] | None = None,
    project_ids: Iterable[str] | None = None,
    capacity_ids: Iterable[str] | None = None,
    risk_ids: Iterable[str] | None = None,
    upstream_material_evidence_count: int = 0,
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    allocations = outcomes_payload.get("allocations") or []
    timelines = (timelines_payload or {}).get("timelines") or []
    assessments = (assessments_payload or {}).get("assessments") or []

    if upstream_material_evidence_count > 0 and not allocations:
        issues.append({"code": "material_evidence_zero_output", "severity": "fail", "message": f"{upstream_material_evidence_count} material allocation candidates produced an empty output."})

    commitment_id_set = {str(item).strip() for item in (commitment_ids or []) if str(item).strip()}
    project_id_set = {str(item).strip() for item in (project_ids or []) if str(item).strip()}
    capacity_id_set = {str(item).strip() for item in (capacity_ids or []) if str(item).strip()}
    risk_id_set = {str(item).strip() for item in (risk_ids or []) if str(item).strip()}

    timeline_map = {str(item.get("allocation_id") or ""): item for item in timelines if str(item.get("allocation_id") or "").strip()}
    assessment_map = {str(item.get("allocation_id") or ""): item for item in assessments if str(item.get("allocation_id") or "").strip()}

    seen_ids: Set[str] = set()
    seen_signatures: Set[tuple[str, str, str]] = set()

    for allocation in allocations:
        allocation_id = str(allocation.get("allocation_id") or "").strip()
        allocation_name = str(allocation.get("allocation_name") or "").strip()
        allocation_category = str(allocation.get("allocation_category") or "").strip()
        normalized_name = str(allocation.get("normalized_name") or "").strip()
        status = str(allocation.get("current_status") or "").strip()
        outcome_status = str(allocation.get("outcome_status") or "").strip()
        deployment_periods = [str(period or "").strip() for period in (allocation.get("deployment_periods") or []) if str(period or "").strip()]

        if not allocation_id:
            issues.append({"code": "missing_allocation_id", "severity": "fail", "message": "Allocation id is required."})
        elif allocation_id in seen_ids:
            issues.append({"code": "duplicate_allocation_id", "severity": "fail", "allocation_id": allocation_id, "message": "Duplicate allocation id detected."})
        else:
            seen_ids.add(allocation_id)

        signature = (allocation_category, normalized_name, allocation.get("first_observed_period") or "")
        if signature in seen_signatures:
            issues.append({"code": "duplicate_allocation_signature", "severity": "fail", "allocation_id": allocation_id, "message": "Duplicate allocation family detected."})
        else:
            seen_signatures.add(signature)

        if not allocation_name:
            issues.append({"code": "missing_allocation_name", "severity": "fail", "allocation_id": allocation_id, "message": "Allocation name is required."})
        if allocation_category not in ALLOCATION_CATEGORIES:
            issues.append({"code": "invalid_allocation_category", "severity": "fail", "allocation_id": allocation_id, "message": "Allocation category is invalid."})
        if status not in ALLOCATION_CURRENT_STATUSES:
            issues.append({"code": "invalid_current_status", "severity": "fail", "allocation_id": allocation_id, "message": "Current status is invalid."})
        if outcome_status not in ALLOCATION_OUTCOME_STATUSES:
            issues.append({"code": "invalid_outcome_status", "severity": "fail", "allocation_id": allocation_id, "message": "Outcome status is invalid."})
        if not deployment_periods:
            issues.append({"code": "missing_deployment_periods", "severity": "fail", "allocation_id": allocation_id, "message": "Deployment periods are required."})
        elif not _is_chronological(deployment_periods):
            issues.append({"code": "chronology_violation", "severity": "fail", "allocation_id": allocation_id, "message": "Deployment periods are not chronological."})

        if not allocation.get("source_references"):
            issues.append({"code": "missing_source_references", "severity": "fail", "allocation_id": allocation_id, "message": "Source references must be preserved."})

        if not _validate_confidence(allocation.get("confidence")):
            issues.append({"code": "invalid_confidence", "severity": "fail", "allocation_id": allocation_id, "message": "Confidence must include level, basis, and limitations."})

        if allocation.get("linked_commitment_ids"):
            missing = [item for item in allocation.get("linked_commitment_ids") or [] if item not in commitment_id_set]
            if missing:
                issues.append({"code": "invalid_commitment_reference", "severity": "fail", "allocation_id": allocation_id, "missing_commitment_ids": missing, "message": "Linked commitment ids must exist."})
        if allocation.get("linked_project_ids"):
            missing = [item for item in allocation.get("linked_project_ids") or [] if item not in project_id_set]
            if missing:
                issues.append({"code": "invalid_project_reference", "severity": "fail", "allocation_id": allocation_id, "missing_project_ids": missing, "message": "Linked project ids must exist."})
        if allocation.get("linked_capacity_ids"):
            missing = [item for item in allocation.get("linked_capacity_ids") or [] if item not in capacity_id_set]
            if missing:
                issues.append({"code": "invalid_capacity_reference", "severity": "fail", "allocation_id": allocation_id, "missing_capacity_ids": missing, "message": "Linked capacity ids must exist."})
        if allocation.get("linked_risk_ids"):
            missing = [item for item in allocation.get("linked_risk_ids") or [] if item not in risk_id_set]
            if missing:
                issues.append({"code": "invalid_risk_reference", "severity": "fail", "allocation_id": allocation_id, "missing_risk_ids": missing, "message": "Linked risk ids must exist."})

        if outcome_status in {"clearly_observed", "negative_outcome"} and not allocation.get("return_evidence"):
            issues.append({"code": "unsupported_outcome", "severity": "fail", "allocation_id": allocation_id, "message": "Outcome status requires explicit supporting evidence."})

        timeline = timeline_map.get(allocation_id)
        if timeline is None:
            issues.append({"code": "missing_timeline", "severity": "fail", "allocation_id": allocation_id, "message": "Allocation timeline is missing."})
        else:
            events = timeline.get("events") or []
            periods = [str(event.get("period") or "").strip() for event in events if str(event.get("period") or "").strip()]
            if events and not _is_chronological(periods):
                issues.append({"code": "chronology_violation", "severity": "fail", "allocation_id": allocation_id, "message": "Allocation timeline is not chronological."})
            if events and len({str(event.get("event_id") or "") for event in events if event.get("event_id")}) != len([event for event in events if event.get("event_id")]):
                issues.append({"code": "duplicate_event_id", "severity": "fail", "allocation_id": allocation_id, "message": "Duplicate event id detected in timeline."})
            if status in {"delayed", "abandoned", "superseded"} and not any(str(event.get("event_type") or "") in {"delay_signal", "abandonment", "superseded"} for event in events):
                issues.append({"code": "unsupported_status_transition", "severity": "fail", "allocation_id": allocation_id, "message": "Negative status requires explicit later evidence."})

        assessment = assessment_map.get(allocation_id)
        if assessment is None:
            issues.append({"code": "missing_assessment", "severity": "fail", "allocation_id": allocation_id, "message": "Allocation assessment is missing."})
        elif not _validate_confidence(assessment.get("confidence")):
            issues.append({"code": "invalid_assessment_confidence", "severity": "fail", "allocation_id": allocation_id, "message": "Assessment confidence must include level, basis, and limitations."})

        if _scan_forbidden_terms(allocation):
            issues.append({"code": "public_term_leak", "severity": "fail", "allocation_id": allocation_id, "message": "Internal pipeline terminology leaked into public allocation fields."})

    status = "pass" if not issues else "fail"
    return {
        "status": status,
        "issue_count": len(issues),
        "issues": issues,
    }
