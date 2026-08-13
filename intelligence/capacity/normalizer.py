from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from intelligence.progression import build_confidence

from knowledge.company_memory.guardrails import (
    assess_progression_materiality,
    build_semantic_quality,
    classify_business_relevance,
    resolve_period_status,
    semantic_validation,
)

from .classifier import (
    build_capacity_economic_relevance,
    build_capacity_name,
    build_purpose,
    build_unit,
    classify_capacity_type,
    classify_capacity_family,
    has_bounded_capacity_signals,
    normalize_location,
    sanitize_public_text,
    _normalize_text,
)


_PERCENT_RE = re.compile(r"(?P<rate>\d+(?:\.\d+)?)\s*%")
_RATIO_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?:out of|/)\s*(?P<den>\d+(?:\.\d+)?)", re.IGNORECASE)
_NUMBER_UNIT_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>crore|lakh|mw|mwh|units?|tonnes?|tons?|seats?|beds?|classrooms?|machines?|sq\.?\s?(?:ft|m)|%|percent|percentage)",
    re.IGNORECASE,
)


def _year_label(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith("fy"):
        return lowered
    if lowered.isdigit() and len(lowered) == 4:
        return f"fy{lowered[-2:]}"
    return lowered


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


def _extract_explicit_rate(*texts: str) -> Tuple[Optional[float], str, str]:
    joined = " ".join(texts)
    ratio_match = _RATIO_RE.search(joined)
    if ratio_match:
        numerator = float(ratio_match.group("num"))
        denominator = float(ratio_match.group("den"))
        if denominator:
            return round(numerator / denominator, 4), ratio_match.group(0), f"{numerator:g}/{denominator:g}"
    percent_match = _PERCENT_RE.search(joined)
    if percent_match:
        return round(float(percent_match.group("rate")) / 100.0, 4), percent_match.group(0), percent_match.group(0)
    return None, "", ""


def _extract_number_unit(text: str) -> Tuple[str, str]:
    match = _NUMBER_UNIT_RE.search(text)
    if not match:
        return "", ""
    unit = match.group("unit").lower().replace("percent", "%").replace("percentage", "%")
    return match.group("value"), unit


def normalize_candidate(year_record: Dict[str, Any], item: Dict[str, Any], *, source_kind: str) -> Dict[str, Any] | None:
    if not has_bounded_capacity_signals(item, source_kind=source_kind):
        return None

    raw_name = _normalize_text(item.get("capacity_type") or item.get("value") or item.get("project_name"))
    description = _normalize_text(item.get("description") or item.get("status") or item.get("timeline") or item.get("benefit"))
    status_text = _normalize_text(item.get("status"))
    location = normalize_location(item)
    capacity_type = classify_capacity_type(raw_name, description, location, status_text, source_kind)
    capacity_name = build_capacity_name(raw_name, description, capacity_type)
    purpose = sanitize_public_text(build_purpose(capacity_name, description, capacity_type, location, _normalize_text(item.get("target_capacity"))))
    expected_timeframe = sanitize_public_text(
        _normalize_text(
            item.get("timeline")
            or item.get("expected_timeframe")
            or item.get("year")
            or year_record.get("year")
        )
    )
    planned_capacity = sanitize_public_text(_normalize_text(item.get("target_capacity") or item.get("current_capacity")))
    installed_capacity = sanitize_public_text(_normalize_text(item.get("installed_capacity") or item.get("current_capacity")))
    operational_capacity = sanitize_public_text(_normalize_text(item.get("operational_capacity") or item.get("current_capacity")))
    utilized_capacity = sanitize_public_text(_normalize_text(item.get("utilized_capacity") or item.get("current_capacity") or item.get("amount")))
    capital_deployed = sanitize_public_text(_normalize_text(item.get("amount") or item.get("capital_deployed")))
    unit = build_unit(item, planned_capacity, installed_capacity, operational_capacity, utilized_capacity, capital_deployed)
    capacity_family = classify_capacity_family(raw_name, description, location, status_text, source_kind, capacity_type)
    explicit_rate, rate_basis, ratio_basis = _extract_explicit_rate(
        planned_capacity,
        installed_capacity,
        operational_capacity,
        utilized_capacity,
        capital_deployed,
        status_text,
        expected_timeframe,
    )
    capital_value, capital_unit = _extract_number_unit(" ".join([capital_deployed, status_text, expected_timeframe]))
    if not capital_deployed and capital_value and capital_unit:
        capital_deployed = sanitize_public_text(f"{capital_value} {capital_unit}")
    full_text = " ".join(part for part in (raw_name, description, status_text, location, planned_capacity, installed_capacity, operational_capacity, utilized_capacity, capital_deployed, expected_timeframe) if part)
    relevance = classify_business_relevance(full_text, module_name="capacity", actor_type=str(item.get("actor") or ""), source_kind=source_kind)
    period_resolution = resolve_period_status(
        source_year=year_record.get("year"),
        text=full_text,
        explicit_year=item.get("year") or year_record.get("year"),
    )
    progression_materiality = assess_progression_materiality(
        full_text,
        module_name="capacity",
        relevance_status=str(relevance.get("status") or "ambiguous"),
        period_status=str(period_resolution.get("status") or "AMBIGUOUS"),
        evidence_quality=item.get("evidence_quality") if isinstance(item.get("evidence_quality"), dict) else None,
        status_text=status_text,
    )
    semantic_flags = semantic_validation(
        module_name="capacity",
        relevance=relevance,
        period=period_resolution,
        materiality=progression_materiality,
    )
    if semantic_flags["errors"] or not progression_materiality.get("should_promote"):
        return None
    semantic_quality = build_semantic_quality(
        classification="CAPACITY",
        relevance=relevance,
        period=period_resolution,
        materiality=progression_materiality,
        evidence_confidence=item.get("confidence") or "medium",
    )

    basis = []
    for field in ("capacity_type", "status", "timeline", "target_capacity", "current_capacity", "amount", "location"):
        value = _normalize_text(item.get(field))
        if value:
            basis.append(f"{field}: {value}")
    limitations = []
    for field in ("uncertainty_reason",):
        value = _normalize_text(item.get(field))
        if value:
            limitations.append(value)
    if not location:
        limitations.append("location not disclosed")

    utilization_numerator = ""
    utilization_denominator = ""
    utilization_unit = unit
    if explicit_rate is not None and ratio_basis:
        if "/" in ratio_basis:
            utilization_numerator, utilization_denominator = ratio_basis.split("/", 1)
        elif rate_basis.endswith("%"):
            utilization_numerator = rate_basis.rstrip("%")
            utilization_denominator = "100"
            utilization_unit = "%"

    return {
        "source_kind": source_kind,
        "source_year": _year_label(year_record.get("year")),
        "sort_key": year_record.get("sort_key", 10_000),
        "capacity_name": capacity_name,
        "normalized_name": sanitize_public_text(capacity_name.lower()),
        "capacity_type": capacity_type,
        "capacity_family": capacity_family,
        "location": location,
        "purpose": purpose,
        "planned_capacity": planned_capacity,
        "installed_capacity": installed_capacity,
        "operational_capacity": operational_capacity,
        "utilized_capacity": utilized_capacity,
        "utilization_rate": explicit_rate,
        "unit": unit,
        "expected_timeframe": expected_timeframe,
        "capital_deployed": capital_deployed,
        "announcement_period": _year_label(item.get("year") or year_record.get("year")),
        "current_status_hint": status_text,
        "current_status": "unable_to_verify",
        "latest_period": _year_label(year_record.get("year")),
        "linked_project_ids": [],
        "linked_commitment_ids": [],
        "progression_summary": {},
        "economic_relevance": purpose,
        "investor_implication": "",
        "confidence": build_confidence(
            item.get("confidence") or item.get("evidence_quality", {}).get("confidence") or "medium",
            basis=basis[:5],
            limitations=limitations,
        ),
        "evidence_status": "supported" if len(basis) >= 3 else "partial",
        "source_reference": _source_reference(year_record, item, source_kind),
        "source_item_id": item.get("item_id") or item.get("source_item_id") or item.get("id") or item.get("value"),
        "utilization_measure": {
            "numerator": utilization_numerator,
            "denominator": utilization_denominator,
            "unit": utilization_unit,
        },
        "source_item": item,
        "utilization_basis": rate_basis or ratio_basis,
        "capital_value": capital_value,
        "capital_unit": capital_unit,
        "original_status_text": status_text,
        "expected_output": _normalize_text(item.get("target_capacity") or item.get("current_capacity")),
        "currency": _normalize_text(item.get("currency")),
        "semantic_relevance": relevance,
        "period_resolution": period_resolution,
        "progression_materiality": progression_materiality,
        "semantic_validation": semantic_flags,
        "semantic_quality": semantic_quality,
    }
