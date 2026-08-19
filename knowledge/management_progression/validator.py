from __future__ import annotations

import re
from typing import Any, Dict, List

from .contract import (
    COVERAGE_STATUSES,
    CURRENT_STATUSES,
    EVENT_ROLES,
    EVENT_TYPES,
    SCHEMA_VERSION,
    THESIS_IMPACTS,
    VERIFICATION_STATUSES,
)


GENERIC_BAD = (
    "management focused on expansion and growth",
    "focused on growth and operational efficiency",
    "strategic initiatives",
)


def validate_management_progression(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    company_slug = str(payload.get("company_slug") or "").strip()
    if not company_slug:
        errors.append("company_slug is required")
    if payload.get("coverage_status") not in COVERAGE_STATUSES:
        errors.append("coverage_status is invalid")
    manifest = payload.get("source_manifest") or {}
    if str(manifest.get("company_slug") or company_slug) != company_slug:
        errors.append("source_manifest.company_slug must match company_slug")
    for mismatch in manifest.get("company_mismatch_errors", []) or []:
        errors.append(str(mismatch))

    items = payload.get("progression_items")
    if not isinstance(items, list):
        errors.append("progression_items must be a list")
        items = []
    if payload.get("coverage_status") == "supported" and not items:
        errors.append("supported progression requires progression_items")

    seen_events = set()
    for item_index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"progression_items[{item_index}] must be an object")
            continue
        _validate_item(item, item_index, errors, warnings)
        for event in item.get("events", []) or []:
            marker = _event_marker(event)
            if marker in seen_events:
                errors.append(f"duplicate event detected: {event.get('event_id') or marker}")
            seen_events.add(marker)
            _validate_event(event, item_index, errors, warnings)
    status = "fail" if errors else "warning" if warnings else "pass"
    return {
        "schema_version": "management_progression_validation.v1",
        "company_slug": company_slug,
        "status": status,
        "errors": errors,
        "warnings": warnings,
    }


def _validate_item(item: Dict[str, Any], index: int, errors: List[str], warnings: List[str]) -> None:
    for key in ("item_id", "theme", "current_status"):
        if not str(item.get(key) or "").strip():
            errors.append(f"progression_items[{index}].{key} is required")
    if item.get("current_status") not in CURRENT_STATUSES:
        errors.append(f"progression_items[{index}].current_status is invalid")
    if not isinstance(item.get("events"), list) or not item.get("events"):
        errors.append(f"progression_items[{index}].events must be non-empty")
    implication = item.get("investor_implication") or {}
    for key in ("conclusion", "economic_mechanism", "thesis_impact", "confidence", "what_to_watch"):
        if key not in implication:
            errors.append(f"progression_items[{index}].investor_implication.{key} is required")
    if implication.get("thesis_impact") not in THESIS_IMPACTS:
        errors.append(f"progression_items[{index}].investor_implication.thesis_impact is invalid")
    text = f"{item.get('theme') or ''} {implication.get('conclusion') or ''} {implication.get('economic_mechanism') or ''}".lower()
    if any(phrase in text for phrase in GENERIC_BAD):
        errors.append(f"progression_items[{index}] lacks specificity")
    if len(set(re.findall(r"[a-z0-9]{5,}", text))) < 4:
        warnings.append(f"progression_items[{index}] has thin specificity")


def _validate_event(event: Dict[str, Any], item_index: int, errors: List[str], warnings: List[str]) -> None:
    if event.get("role") not in EVENT_ROLES:
        errors.append(f"progression_items[{item_index}].events.role is invalid")
    if event.get("event_type") not in EVENT_TYPES:
        errors.append(f"progression_items[{item_index}].events.event_type is invalid")
    if event.get("verification_status") not in VERIFICATION_STATUSES:
        errors.append(f"progression_items[{item_index}].events.verification_status is invalid")
    if not event.get("source_period"):
        errors.append(f"progression_items[{item_index}].events.source_period is required")
    if event.get("role") in {"statement", "commitment"} and event.get("verification_status") == "verified":
        errors.append("management statement/commitment cannot be verified outcome by itself")
    if event.get("role") in {"outcome", "completion"} and not (event.get("operational_outcome") or event.get("financial_or_business_outcome")):
        errors.append("outcome/completion event requires outcome text")
    if not event.get("evidence"):
        warnings.append(f"event {event.get('event_id') or ''} has no evidence references")


def _event_marker(event: Dict[str, Any]) -> str:
    return "|".join(
        [
            str(event.get("role") or ""),
            str(event.get("event_type") or ""),
            str(event.get("source_period") or ""),
            str(event.get("event_period") or ""),
            " ".join(str(event.get("statement_text") or event.get("action_taken") or event.get("operational_outcome") or "").lower().split())[:180],
        ]
    )

