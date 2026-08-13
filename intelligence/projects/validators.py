from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Set

from knowledge.company_memory.guardrails import semantic_validation

from .contracts import ECONOMIC_IMPACT_STATUSES, PROJECT_STATUSES


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


def validate_projects_payload(
    registry_payload: Dict[str, Any],
    *,
    timelines_payload: Dict[str, Any] | None = None,
    assessments_payload: Dict[str, Any] | None = None,
    commitment_ids: Iterable[str] | None = None,
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    projects = registry_payload.get("projects") or []
    timelines = (timelines_payload or {}).get("timelines") or []
    assessments = (assessments_payload or {}).get("assessments") or []
    commitment_id_set = {str(item).strip() for item in (commitment_ids or []) if str(item).strip()}

    seen_ids: Set[str] = set()
    seen_names: Set[str] = set()
    timeline_map = {str(item.get("project_id") or ""): item for item in timelines if str(item.get("project_id") or "").strip()}
    assessment_map = {str(item.get("project_id") or ""): item for item in assessments if str(item.get("project_id") or "").strip()}

    for project in projects:
        project_id = str(project.get("project_id") or "").strip()
        if not project_id:
            issues.append({"code": "missing_project_id", "severity": "fail", "message": "Project id is missing."})
        elif project_id in seen_ids:
            issues.append({"code": "duplicate_project_id", "severity": "fail", "project_id": project_id, "message": "Duplicate project id detected."})
        else:
            seen_ids.add(project_id)

        project_name = str(project.get("project_name") or "").strip()
        if not project_name:
            issues.append({"code": "missing_project_name", "severity": "fail", "project_id": project_id, "message": "Project name is required."})
        elif project_name.lower() in seen_names:
            issues.append({"code": "duplicate_project_name", "severity": "fail", "project_id": project_id, "message": "Duplicate project name detected."})
        else:
            seen_names.add(project_name.lower())

        if str(project.get("current_status") or "").strip() not in PROJECT_STATUSES:
            issues.append({"code": "invalid_project_status", "severity": "fail", "project_id": project_id, "message": "Current status is invalid."})
        if not project.get("source_references"):
            issues.append({"code": "missing_source_references", "severity": "fail", "project_id": project_id, "message": "Source references must be preserved."})
        if not isinstance(project.get("confidence"), dict) or "level" not in (project.get("confidence") or {}) or "basis" not in (project.get("confidence") or {}) or "limitations" not in (project.get("confidence") or {}):
            issues.append({"code": "invalid_confidence", "severity": "fail", "project_id": project_id, "message": "Confidence must include level, basis, and limitations."})
        if project.get("related_commitment_ids"):
            missing = [cid for cid in project.get("related_commitment_ids") or [] if cid not in commitment_id_set]
            if missing:
                issues.append({"code": "invalid_commitment_reference", "severity": "fail", "project_id": project_id, "missing_commitment_ids": missing, "message": "Linked commitment ids must exist."})
        semantic = semantic_validation(
            module_name="projects",
            relevance=project.get("semantic_relevance") or {},
            period=project.get("period_resolution") or {},
            materiality=project.get("progression_materiality") or {},
        )
        if semantic["errors"]:
            issues.append({"code": "semantic_validation_failed", "severity": "fail", "project_id": project_id, "message": "; ".join(semantic["errors"])})
        if semantic["warnings"]:
            issues.append({"code": "semantic_validation_warning", "severity": "warning", "project_id": project_id, "message": "; ".join(semantic["warnings"])})

        timeline = timeline_map.get(project_id)
        if timeline is None:
            issues.append({"code": "missing_timeline", "severity": "fail", "project_id": project_id, "message": "Project timeline is missing."})
            continue

        events = timeline.get("events") or []
        if not events:
            issues.append({"code": "missing_events", "severity": "fail", "project_id": project_id, "message": "Timeline must include events."})
            continue

        periods = [str(event.get("period") or "") for event in events]
        if not _is_chronological(periods):
            issues.append({"code": "chronology_violation", "severity": "fail", "project_id": project_id, "message": "Project timeline is not chronological."})

        if len({str(event.get("event_id") or "") for event in events if event.get("event_id")}) != len([event for event in events if event.get("event_id")]):
            issues.append({"code": "duplicate_event_id", "severity": "fail", "project_id": project_id, "message": "Duplicate event id detected in timeline."})

        duplicate_signatures = set()
        for event in events:
            signature = (
                str(event.get("period") or ""),
                str(event.get("event_type") or ""),
                str(event.get("title") or ""),
                str(event.get("description") or ""),
            )
            if signature in duplicate_signatures:
                issues.append({"code": "duplicate_event", "severity": "fail", "project_id": project_id, "message": "Repeated project mention should be deduplicated."})
                break
            duplicate_signatures.add(signature)

        current_status = str(project.get("current_status") or "")
        has_commissioning = any(str(event.get("event_type") or "") == "confirmation" for event in events)
        has_operational = any(str(event.get("event_type") or "") == "completion" for event in events)
        has_delay = any(str(event.get("event_type") or "") == "delay_signal" for event in events)
        has_cancellation = any(str(event.get("event_type") or "") == "abandonment" for event in events)
        if current_status == "commissioned" and not has_commissioning:
            issues.append({"code": "missing_commissioning_evidence", "severity": "fail", "project_id": project_id, "message": "Commissioned projects require explicit commissioning evidence."})
        if current_status == "operational" and not has_operational:
            issues.append({"code": "missing_operating_evidence", "severity": "fail", "project_id": project_id, "message": "Operational projects require explicit operating evidence."})
        if current_status == "delayed" and not has_delay:
            issues.append({"code": "missing_delay_evidence", "severity": "fail", "project_id": project_id, "message": "Delayed projects require explicit delay evidence."})
        if current_status == "cancelled" and not has_cancellation:
            issues.append({"code": "missing_cancellation_evidence", "severity": "fail", "project_id": project_id, "message": "Cancelled projects require explicit cancellation evidence."})

        if assessment_map.get(project_id):
            assessment = assessment_map[project_id]
            if str(assessment.get("economic_impact_status") or "") not in ECONOMIC_IMPACT_STATUSES:
                issues.append({"code": "invalid_economic_impact_status", "severity": "fail", "project_id": project_id, "message": "Economic impact status is invalid."})
            if assessment.get("economic_impact_status") == "clearly_observed" and not any(str(event.get("event_type") or "") in {"commercial_operations", "utilization_update", "economic_impact_update"} for event in events):
                issues.append({"code": "unsupported_causality", "severity": "fail", "project_id": project_id, "message": "Economic impact should not be claimed without explicit downstream evidence."})
            if assessment.get("observed_financial_effect") and any(term in str(assessment.get("observed_financial_effect") or "").lower() for term in ("caused", "proves", "proved", "definitely", "clearly caused")):
                issues.append({"code": "causality_overstate", "severity": "fail", "project_id": project_id, "message": "Investor implication overstates causality."})
            if not isinstance(assessment.get("confidence"), dict) or "level" not in (assessment.get("confidence") or {}) or "basis" not in (assessment.get("confidence") or {}) or "limitations" not in (assessment.get("confidence") or {}):
                issues.append({"code": "invalid_assessment_confidence", "severity": "fail", "project_id": project_id, "message": "Assessment confidence must include level, basis, and limitations."})

        if _scan_forbidden_terms(project):
            issues.append({"code": "public_term_leak", "severity": "fail", "project_id": project_id, "message": "Internal pipeline terminology leaked into public project fields."})

    status = "pass" if not issues else "fail"
    return {
        "status": status,
        "issue_count": len(issues),
        "issues": issues,
    }
