from __future__ import annotations

from typing import Any, Dict, List


ALLOWED_PCIM_VALIDATION_STATUS = {"pass", "warning", "fail"}


def _require_fields(payload: Dict[str, Any], fields: List[str], label: str) -> List[str]:
    errors: List[str] = []
    for field in fields:
        if field not in payload:
            errors.append(f"{label} missing required field: {field}")
    return errors


def validate_financial_pcim_validation_payload(payload: Dict[str, Any]) -> List[str]:
    if not isinstance(payload, dict):
        return ["financial pcim validation payload must be an object"]
    errors = _require_fields(
        payload,
        ["company", "year", "generated_at", "status", "checks", "hard_failures", "warnings", "limitations"],
        "financial pcim validation payload",
    )
    status = payload.get("status")
    if status not in ALLOWED_PCIM_VALIDATION_STATUS:
        errors.append("financial pcim validation status must be pass|warning|fail")
    for field in ("checks", "hard_failures", "warnings", "limitations"):
        if field in payload and not isinstance(payload.get(field), list):
            errors.append(f"financial pcim validation field must be a list: {field}")
    return errors


def validate_financial_quality_scorecard_payload(payload: Dict[str, Any]) -> List[str]:
    if not isinstance(payload, dict):
        return ["financial quality scorecard payload must be an object"]
    errors = _require_fields(
        payload,
        [
            "company",
            "generated_at",
            "status",
            "overall_score",
            "dimensions",
            "hard_failures",
            "warnings",
            "recommended_next_fixes",
            "years",
        ],
        "financial quality scorecard payload",
    )
    status = payload.get("status")
    if status not in ALLOWED_PCIM_VALIDATION_STATUS:
        errors.append("financial quality scorecard status must be pass|warning|fail")
    if "overall_score" in payload and not isinstance(payload.get("overall_score"), int):
        errors.append("financial quality scorecard overall_score must be an integer")
    if "dimensions" in payload and not isinstance(payload.get("dimensions"), dict):
        errors.append("financial quality scorecard dimensions must be an object")
    if "years" in payload and not isinstance(payload.get("years"), dict):
        errors.append("financial quality scorecard years must be an object")
    for field in ("hard_failures", "warnings", "recommended_next_fixes"):
        if field in payload and not isinstance(payload.get(field), list):
            errors.append(f"financial quality scorecard field must be a list: {field}")
    return errors
