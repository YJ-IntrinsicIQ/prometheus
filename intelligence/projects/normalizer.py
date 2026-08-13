from __future__ import annotations

from typing import Any, Dict, List

from intelligence.progression import build_confidence

from knowledge.company_memory.guardrails import (
    assess_progression_materiality,
    build_semantic_quality,
    classify_business_relevance,
    resolve_period_status,
    semantic_validation,
)

from .classifier import (
    build_business_rationale,
    build_economic_relevance,
    build_expected_cost,
    build_expected_output_or_capacity,
    build_expected_timeframe,
    build_objective,
    classify_project_type,
    is_bounded_project_candidate,
    normalize_location,
    normalize_project_name,
)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _sanitize_public_text(value: str) -> str:
    text = _normalize_text(value)
    text = text.replace("Pipeline", "Program")
    text = text.replace("pipeline", "program")
    return text


def _year_label(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith("fy"):
        return lowered
    if lowered.isdigit() and len(lowered) == 4:
        return f"fy{lowered[-2:]}"
    return text


def _source_reference(year_record: Dict[str, Any], item: Dict[str, Any], source_kind: str) -> Dict[str, Any]:
    return {
        "period": _year_label(year_record.get("year")),
        "source_artifact": year_record.get("source_artifact", source_kind),
        "source_item_id": item.get("item_id") or item.get("source_item_id") or item.get("id") or item.get("value"),
        "page": item.get("page"),
        "source_kind": source_kind,
        "status": item.get("status"),
        "confidence": item.get("confidence"),
        "evidence_ids": list(item.get("evidence_ids") or []),
    }


def normalize_candidate(year_record: Dict[str, Any], item: Dict[str, Any], *, source_kind: str) -> Dict[str, Any] | None:
    if not is_bounded_project_candidate(item, source_kind=source_kind):
        return None

    name = _normalize_text(item.get("project_name") or item.get("capacity_type") or item.get("value"))
    description = _normalize_text(item.get("description") or item.get("benefit") or item.get("status"))
    location = normalize_location(item)
    status = _normalize_text(item.get("status"))
    project_type = classify_project_type(source_kind, name, description, location, status)
    normalized_name = _sanitize_public_text(normalize_project_name(name, description, project_type))
    objective = _sanitize_public_text(build_objective(name, description, project_type, source_kind=source_kind))
    expected_output_or_capacity = build_expected_output_or_capacity(item, project_type)
    expected_timeframe = build_expected_timeframe(item, _year_label(year_record.get("year")))
    expected_cost = build_expected_cost(item)
    full_text = " ".join(part for part in (name, description, location, status, expected_output_or_capacity, expected_timeframe) if part)
    relevance = classify_business_relevance(full_text, module_name="projects", actor_type=str(item.get("actor") or ""), source_kind=source_kind)
    period_resolution = resolve_period_status(
        source_year=year_record.get("year"),
        text=full_text,
        explicit_year=item.get("year") or year_record.get("year"),
    )
    progression_materiality = assess_progression_materiality(
        full_text,
        module_name="projects",
        relevance_status=str(relevance.get("status") or "ambiguous"),
        period_status=str(period_resolution.get("status") or "AMBIGUOUS"),
        evidence_quality=item.get("evidence_quality") if isinstance(item.get("evidence_quality"), dict) else None,
        status_text=status,
    )
    semantic_flags = semantic_validation(
        module_name="projects",
        relevance=relevance,
        period=period_resolution,
        materiality=progression_materiality,
    )
    if semantic_flags["errors"] or not progression_materiality.get("should_promote"):
        return None
    semantic_quality = build_semantic_quality(
        classification="GROWTH_PROJECT",
        relevance=relevance,
        period=period_resolution,
        materiality=progression_materiality,
        evidence_confidence=item.get("confidence") or "medium",
    )

    basis = []
    for field in ("project_name", "description", "status", "location", "timeline", "target_capacity", "current_capacity"):
        value = _normalize_text(item.get(field))
        if value:
            basis.append(f"{field}: {value}")
    limitations = []
    for field in ("uncertainty_reason",):
        value = _normalize_text(item.get(field))
        if value:
            limitations.append(value)

    confidence = build_confidence(
        item.get("confidence") or item.get("evidence_quality", {}).get("confidence") or "medium",
        basis=basis[:4],
        limitations=limitations,
    )

    return {
        "source_kind": source_kind,
        "source_year": _year_label(year_record.get("year")),
        "project_name": _sanitize_public_text(name),
        "normalized_name": normalized_name,
        "project_type": project_type,
        "objective": objective,
        "business_rationale": _sanitize_public_text(build_business_rationale(name, description, project_type, location, expected_output_or_capacity)),
        "announcement_period": _year_label(item.get("year") or year_record.get("year")),
        "expected_timeframe": expected_timeframe,
        "expected_output_or_capacity": _sanitize_public_text(expected_output_or_capacity),
        "expected_cost": expected_cost,
        "location": _sanitize_public_text(location),
        "status_text": status,
        "source_item_id": item.get("item_id") or item.get("source_item_id") or item.get("id") or item.get("value"),
        "source_reference": _source_reference(year_record, item, source_kind),
        "related_commitment_ids": [],
        "confidence": confidence,
        "evidence_status": "supported",
        "source_item": item,
        "economic_relevance": _sanitize_public_text(build_economic_relevance(project_type, expected_output_or_capacity, location)),
        "semantic_relevance": relevance,
        "period_resolution": period_resolution,
        "progression_materiality": progression_materiality,
        "semantic_validation": semantic_flags,
        "semantic_quality": semantic_quality,
    }
