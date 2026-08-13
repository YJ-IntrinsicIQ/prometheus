from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Set

from knowledge.company_memory.guardrails import semantic_validation

from .contracts import COMMENTARY_POSITIONS, COMMENTARY_THEME_CATEGORIES


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
    def key(value: str) -> tuple:
        lowered = str(value or "").lower()
        if lowered.startswith("fy") and lowered[2:].isdigit():
            return (int(lowered[2:]), lowered)
        if lowered.isdigit():
            return (int(lowered), lowered)
        return (10_000, lowered)

    return list(periods) == sorted(periods, key=key)


def validate_commentary_payload(
    themes_payload: Dict[str, Any],
    *,
    timelines_payload: Dict[str, Any] | None = None,
    assessments_payload: Dict[str, Any] | None = None,
    commitment_ids: Iterable[str] | None = None,
    project_ids: Iterable[str] | None = None,
    capacity_ids: Iterable[str] | None = None,
    risk_ids: Iterable[str] | None = None,
    financial_metrics: Iterable[str] | None = None,
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    themes = themes_payload.get("themes") or []
    timelines = (timelines_payload or {}).get("timelines") or []
    assessments = (assessments_payload or {}).get("assessments") or []
    commitment_id_set = {str(item).strip() for item in (commitment_ids or []) if str(item).strip()}
    project_id_set = {str(item).strip() for item in (project_ids or []) if str(item).strip()}
    capacity_id_set = {str(item).strip() for item in (capacity_ids or []) if str(item).strip()}
    risk_id_set = {str(item).strip() for item in (risk_ids or []) if str(item).strip()}
    financial_metric_set = {str(item).strip() for item in (financial_metrics or []) if str(item).strip()}
    timeline_map = {str(item.get("theme_id") or ""): item for item in timelines if str(item.get("theme_id") or "").strip()}
    assessment_map = {str(item.get("theme_id") or ""): item for item in assessments if str(item.get("theme_id") or "").strip()}

    seen_ids: Set[str] = set()
    seen_names: Set[str] = set()
    for theme in themes:
        theme_id = str(theme.get("theme_id") or "").strip()
        if not theme_id:
            issues.append({"code": "missing_theme_id", "severity": "fail", "message": "Theme id is missing."})
        elif theme_id in seen_ids:
            issues.append({"code": "duplicate_theme_id", "severity": "fail", "theme_id": theme_id, "message": "Duplicate theme id detected."})
        else:
            seen_ids.add(theme_id)

        theme_name = str(theme.get("theme_name") or "").strip()
        if not theme_name:
            issues.append({"code": "missing_theme_name", "severity": "fail", "theme_id": theme_id, "message": "Theme name is required."})
        elif theme_name.lower() in seen_names:
            issues.append({"code": "duplicate_theme_name", "severity": "fail", "theme_id": theme_id, "message": "Duplicate theme name detected."})
        else:
            seen_names.add(theme_name.lower())

        if str(theme.get("theme_category") or "").strip() not in COMMENTARY_THEME_CATEGORIES:
            issues.append({"code": "invalid_theme_category", "severity": "fail", "theme_id": theme_id, "message": "Theme category is invalid."})
        if str(theme.get("current_position") or "").strip() not in COMMENTARY_POSITIONS:
            issues.append({"code": "invalid_theme_position", "severity": "fail", "theme_id": theme_id, "message": "Theme position is invalid."})
        if not theme.get("source_references"):
            issues.append({"code": "missing_source_references", "severity": "fail", "theme_id": theme_id, "message": "Source references must be preserved."})
        if not isinstance(theme.get("confidence"), dict) or "level" not in (theme.get("confidence") or {}) or "basis" not in (theme.get("confidence") or {}) or "limitations" not in (theme.get("confidence") or {}):
            issues.append({"code": "invalid_confidence", "severity": "fail", "theme_id": theme_id, "message": "Confidence must include level, basis, and limitations."})
        if _scan_forbidden_terms(theme):
            issues.append({"code": "public_term_leak", "severity": "fail", "theme_id": theme_id, "message": "Internal pipeline terminology leaked into public commentary fields."})

        if theme.get("related_commitment_ids"):
            missing = [cid for cid in theme.get("related_commitment_ids") or [] if cid not in commitment_id_set]
            if missing:
                issues.append({"code": "invalid_commitment_reference", "severity": "fail", "theme_id": theme_id, "missing_commitment_ids": missing, "message": "Related commitment ids must exist."})
        if theme.get("related_project_ids"):
            missing = [pid for pid in theme.get("related_project_ids") or [] if pid not in project_id_set]
            if missing:
                issues.append({"code": "invalid_project_reference", "severity": "fail", "theme_id": theme_id, "missing_project_ids": missing, "message": "Related project ids must exist."})
        if theme.get("related_capacity_ids"):
            missing = [cid for cid in theme.get("related_capacity_ids") or [] if cid not in capacity_id_set]
            if missing:
                issues.append({"code": "invalid_capacity_reference", "severity": "fail", "theme_id": theme_id, "missing_capacity_ids": missing, "message": "Related capacity ids must exist."})
        if theme.get("related_risk_ids"):
            missing = [rid for rid in theme.get("related_risk_ids") or [] if rid not in risk_id_set]
            if missing:
                issues.append({"code": "invalid_risk_reference", "severity": "fail", "theme_id": theme_id, "missing_risk_ids": missing, "message": "Related risk ids must exist."})
        if theme.get("related_financial_metrics"):
            missing = [metric for metric in theme.get("related_financial_metrics") or [] if metric not in financial_metric_set]
            if missing:
                issues.append({"code": "invalid_financial_metric_reference", "severity": "fail", "theme_id": theme_id, "missing_financial_metrics": missing, "message": "Related financial metrics must exist in company memory."})
        semantic = semantic_validation(
            module_name="commentary",
            relevance=theme.get("semantic_relevance") or {},
            period=theme.get("period_resolution") or {},
            materiality=theme.get("progression_materiality") or {},
        )
        if semantic["errors"]:
            issues.append({"code": "semantic_validation_failed", "severity": "fail", "theme_id": theme_id, "message": "; ".join(semantic["errors"])})
        if semantic["warnings"]:
            issues.append({"code": "semantic_validation_warning", "severity": "warning", "theme_id": theme_id, "message": "; ".join(semantic["warnings"])})

        timeline = timeline_map.get(theme_id)
        if timeline is None:
            issues.append({"code": "missing_timeline", "severity": "fail", "theme_id": theme_id, "message": "Theme timeline is missing."})
            continue

        events = timeline.get("events") or []
        if not events:
            issues.append({"code": "missing_events", "severity": "fail", "theme_id": theme_id, "message": "Theme timeline must include events."})
            continue

        periods = [str(event.get("period") or "") for event in events]
        if not _is_chronological(periods):
            issues.append({"code": "chronology_violation", "severity": "fail", "theme_id": theme_id, "message": "Theme timeline is not chronological."})

        duplicate_signatures = set()
        for event in events:
            signature = (
                str(event.get("period") or ""),
                str(event.get("event_type") or ""),
                str(event.get("title") or ""),
                str(event.get("description") or ""),
            )
            if signature in duplicate_signatures:
                issues.append({"code": "duplicate_event", "severity": "fail", "theme_id": theme_id, "message": "Repeated commentary event should be deduplicated."})
                break
            duplicate_signatures.add(signature)

        assessment = assessment_map.get(theme_id)
        if assessment:
            for key in ("consistency_assessment", "specificity_assessment", "evidence_alignment"):
                if not isinstance(assessment.get(key), dict):
                    issues.append({"code": "invalid_assessment_shape", "severity": "fail", "theme_id": theme_id, "message": f"{key} must be a dict."})
            if not isinstance(assessment.get("confidence"), dict):
                issues.append({"code": "invalid_assessment_confidence", "severity": "fail", "theme_id": theme_id, "message": "Assessment confidence must be a dict."})

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
