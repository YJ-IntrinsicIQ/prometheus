from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Set

from knowledge.company_memory.guardrails import semantic_validation

from .contracts import CAPACITY_STATUSES, ECONOMIC_IMPACT_STATUSES


FORBIDDEN_PUBLIC_TERMS = (
    "source_chunk",
    "raw_text",
    "full_text",
    "llm",
    "prompt",
    "pipeline",
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
    def key(value: str) -> tuple:
        lowered = str(value or "").lower()
        if lowered.startswith("fy") and lowered[2:].isdigit():
            return (int(lowered[2:]), lowered)
        if lowered.isdigit():
            return (int(lowered), lowered)
        return (10_000, lowered)

    return list(periods) == sorted(periods, key=key)


def _contains_utilization_evidence(events: Sequence[Dict[str, Any]]) -> bool:
    return any(str(event.get("event_type") or "") in {"utilization_update", "output_update", "ramp_up_update"} for event in events)


def validate_capacity_payload(
    registry_payload: Dict[str, Any],
    *,
    timelines_payload: Dict[str, Any] | None = None,
    assessments_payload: Dict[str, Any] | None = None,
    project_ids: Iterable[str] | None = None,
    commitment_ids: Iterable[str] | None = None,
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    capacities = registry_payload.get("capacities") or []
    timelines = (timelines_payload or {}).get("timelines") or []
    assessments = (assessments_payload or {}).get("assessments") or []
    project_id_set = {str(item).strip() for item in (project_ids or []) if str(item).strip()}
    commitment_id_set = {str(item).strip() for item in (commitment_ids or []) if str(item).strip()}

    seen_ids: Set[str] = set()
    seen_names: Set[str] = set()
    timeline_map = {str(item.get("capacity_id") or ""): item for item in timelines if str(item.get("capacity_id") or "").strip()}
    assessment_map = {str(item.get("capacity_id") or ""): item for item in assessments if str(item.get("capacity_id") or "").strip()}

    for capacity in capacities:
        capacity_id = str(capacity.get("capacity_id") or "").strip()
        if not capacity_id:
            issues.append({"code": "missing_capacity_id", "severity": "fail", "message": "Capacity id is missing."})
        elif capacity_id in seen_ids:
            issues.append({"code": "duplicate_capacity_id", "severity": "fail", "capacity_id": capacity_id, "message": "Duplicate capacity id detected."})
        else:
            seen_ids.add(capacity_id)

        capacity_name = str(capacity.get("capacity_name") or "").strip()
        if not capacity_name:
            issues.append({"code": "missing_capacity_name", "severity": "fail", "capacity_id": capacity_id, "message": "Capacity name is required."})
        elif capacity_name.lower() in seen_names:
            issues.append({"code": "duplicate_capacity_name", "severity": "fail", "capacity_id": capacity_id, "message": "Duplicate capacity name detected."})
        else:
            seen_names.add(capacity_name.lower())

        if str(capacity.get("current_status") or "").strip() not in CAPACITY_STATUSES:
            issues.append({"code": "invalid_capacity_status", "severity": "fail", "capacity_id": capacity_id, "message": "Current capacity status is invalid."})
        if not capacity.get("source_references"):
            issues.append({"code": "missing_source_references", "severity": "fail", "capacity_id": capacity_id, "message": "Source references must be preserved."})
        if not isinstance(capacity.get("confidence"), dict) or "level" not in (capacity.get("confidence") or {}) or "basis" not in (capacity.get("confidence") or {}) or "limitations" not in (capacity.get("confidence") or {}):
            issues.append({"code": "invalid_confidence", "severity": "fail", "capacity_id": capacity_id, "message": "Confidence must include level, basis, and limitations."})
        if capacity.get("linked_project_ids"):
            missing = [pid for pid in capacity.get("linked_project_ids") or [] if pid not in project_id_set]
            if missing:
                issues.append({"code": "invalid_project_reference", "severity": "fail", "capacity_id": capacity_id, "missing_project_ids": missing, "message": "Linked project ids must exist."})
        if capacity.get("linked_commitment_ids"):
            missing = [cid for cid in capacity.get("linked_commitment_ids") or [] if cid not in commitment_id_set]
            if missing:
                issues.append({"code": "invalid_commitment_reference", "severity": "fail", "capacity_id": capacity_id, "missing_commitment_ids": missing, "message": "Linked commitment ids must exist."})
        if str(capacity.get("current_status") or "") == "materially_utilized" and not capacity.get("utilization_rate") and not capacity.get("utilized_capacity"):
            issues.append({"code": "missing_utilization_evidence", "severity": "fail", "capacity_id": capacity_id, "message": "Utilized capacity requires explicit utilization evidence."})
        if str(capacity.get("current_status") or "") == "commissioned" and capacity.get("utilization_rate"):
            issues.append({"code": "commissioning_is_not_utilization", "severity": "fail", "capacity_id": capacity_id, "message": "Commissioning must not be treated as utilization."})
        if str(capacity.get("current_status") or "") == "operational" and capacity.get("utilization_rate") and not capacity.get("utilization_measure", {}).get("numerator"):
            issues.append({"code": "missing_utilization_measure", "severity": "fail", "capacity_id": capacity_id, "message": "Utilization rate requires numerator, denominator, and unit."})

        timeline = timeline_map.get(capacity_id)
        if timeline is None:
            issues.append({"code": "missing_timeline", "severity": "fail", "capacity_id": capacity_id, "message": "Capacity timeline is missing."})
            continue

        events = timeline.get("events") or []
        if not events:
            issues.append({"code": "missing_events", "severity": "fail", "capacity_id": capacity_id, "message": "Timeline must include events."})
            continue

        periods = [str(event.get("period") or "") for event in events]
        if not _is_chronological(periods):
            issues.append({"code": "chronology_violation", "severity": "fail", "capacity_id": capacity_id, "message": "Capacity timeline is not chronological."})

        if len({str(event.get("event_id") or "") for event in events if event.get("event_id")}) != len([event for event in events if event.get("event_id")]):
            issues.append({"code": "duplicate_event_id", "severity": "fail", "capacity_id": capacity_id, "message": "Duplicate event id detected in timeline."})

        duplicate_signatures = set()
        for event in events:
            signature = (
                str(event.get("period") or ""),
                str(event.get("event_type") or ""),
                str(event.get("title") or ""),
                str(event.get("description") or ""),
            )
            if signature in duplicate_signatures:
                issues.append({"code": "duplicate_event", "severity": "fail", "capacity_id": capacity_id, "message": "Repeated capacity mention should be deduplicated."})
                break
            duplicate_signatures.add(signature)

        current_status = str(capacity.get("current_status") or "")
        has_installation = any(str(event.get("event_type") or "") == "equipment_installed" for event in events)
        has_commissioning = any(str(event.get("event_type") or "") == "commissioning" for event in events)
        has_operations = any(str(event.get("event_type") or "") == "operations_started" for event in events)
        has_utilization = _contains_utilization_evidence(events)
        has_shutdown = any(str(event.get("event_type") or "") == "shutdown" for event in events)
        if current_status == "installed" and not has_installation:
            issues.append({"code": "missing_installation_evidence", "severity": "fail", "capacity_id": capacity_id, "message": "Installed capacity requires explicit installation evidence."})
        if current_status == "commissioned" and not has_commissioning:
            issues.append({"code": "missing_commissioning_evidence", "severity": "fail", "capacity_id": capacity_id, "message": "Commissioned capacity requires explicit commissioning evidence."})
        if current_status == "operational" and not has_operations:
            issues.append({"code": "missing_operating_evidence", "severity": "fail", "capacity_id": capacity_id, "message": "Operational capacity requires explicit operating evidence."})
        if current_status in {"ramping", "partially_utilized", "materially_utilized", "underutilized"} and not has_utilization:
            issues.append({"code": "missing_utilization_evidence", "severity": "fail", "capacity_id": capacity_id, "message": "Utilized capacity requires explicit utilization evidence."})
        if current_status == "cancelled" and not has_shutdown:
            issues.append({"code": "missing_shutdown_evidence", "severity": "fail", "capacity_id": capacity_id, "message": "Cancelled capacity requires explicit shutdown or cancellation evidence."})

        assessment = assessment_map.get(capacity_id)
        if assessment:
            if str(assessment.get("economic_impact_status") or "") not in ECONOMIC_IMPACT_STATUSES:
                issues.append({"code": "invalid_economic_impact_status", "severity": "fail", "capacity_id": capacity_id, "message": "Economic impact status is invalid."})
            if assessment.get("economic_impact_status") == "clearly_observed" and not any(str(event.get("event_type") or "") in {"economic_impact_update", "output_update"} for event in events):
                issues.append({"code": "unsupported_causality", "severity": "fail", "capacity_id": capacity_id, "message": "Economic impact should not be claimed without explicit downstream evidence."})
            if assessment.get("observed_financial_effect") and any(term in str(assessment.get("observed_financial_effect") or "").lower() for term in ("caused", "proves", "proved", "clearly caused", "directly caused")):
                issues.append({"code": "causality_overstate", "severity": "fail", "capacity_id": capacity_id, "message": "Investor implication overstates causality."})
            if not isinstance(assessment.get("confidence"), dict) or "level" not in (assessment.get("confidence") or {}) or "basis" not in (assessment.get("confidence") or {}) or "limitations" not in (assessment.get("confidence") or {}):
                issues.append({"code": "invalid_assessment_confidence", "severity": "fail", "capacity_id": capacity_id, "message": "Assessment confidence must include level, basis, and limitations."})
            if assessment.get("utilization_status") == "fully_utilized" and str(capacity.get("current_status") or "") == "commissioned":
                issues.append({"code": "commissioning_is_not_utilization", "severity": "fail", "capacity_id": capacity_id, "message": "Commissioning must not be treated as utilization."})
            if assessment.get("utilization_status") in {"low", "moderate", "high", "fully_utilized"} and str(capacity.get("current_status") or "") in {"commissioned", "operational"} and not has_utilization:
                issues.append({"code": "missing_utilization_evidence", "severity": "fail", "capacity_id": capacity_id, "message": "Utilization status must be supported by explicit utilization evidence."})
        semantic = semantic_validation(
            module_name="capacity",
            relevance=capacity.get("semantic_relevance") or {},
            period=capacity.get("period_resolution") or {},
            materiality=capacity.get("progression_materiality") or {},
        )
        if semantic["errors"]:
            issues.append({"code": "semantic_validation_failed", "severity": "fail", "capacity_id": capacity_id, "message": "; ".join(semantic["errors"])})
        if semantic["warnings"]:
            issues.append({"code": "semantic_validation_warning", "severity": "warning", "capacity_id": capacity_id, "message": "; ".join(semantic["warnings"])})

        if _scan_forbidden_terms(capacity):
            issues.append({"code": "public_term_leak", "severity": "fail", "capacity_id": capacity_id, "message": "Internal pipeline terminology leaked into public capacity fields."})

    status = "pass"
    if any(issue.get("severity") == "fail" for issue in issues):
        status = "fail"
    elif issues:
        status = "warning"
    return {
        "status": status,
        "issue_count": len(issues),
        "issues": issues,
    }
