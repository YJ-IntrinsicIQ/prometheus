from __future__ import annotations

from typing import Any, Dict

from .constants import DEFAULT_DISCOVERY_PROFILE, DEFAULT_EXTRACTION_PROFILE, SUPPORTED_TEMPLATES


class ClassificationValidationError(ValueError):
    pass


def validate_classification(classification: Dict[str, Any]) -> None:
    if not isinstance(classification, dict):
        raise ClassificationValidationError("Classification must be an object")

    business_dnas = classification.get("business_dnas", [])
    if not isinstance(business_dnas, list):
        raise ClassificationValidationError("business_dnas must be a list")
    if len(business_dnas) != len(set(business_dnas)):
        raise ClassificationValidationError("business_dnas must be unique")
    if any(not isinstance(item, str) or not item.strip() for item in business_dnas):
        raise ClassificationValidationError("business_dnas must contain non-empty strings")

    question_modules = classification.get("question_modules", [])
    if not isinstance(question_modules, list):
        raise ClassificationValidationError("question_modules must be a list")
    if len(question_modules) != len(set(question_modules)):
        raise ClassificationValidationError("question_modules must be unique")
    if any(not isinstance(item, str) or not item.strip() for item in question_modules):
        raise ClassificationValidationError("question_modules must contain non-empty strings")

    rationale = classification.get("rationale", [])
    if rationale is None or not isinstance(rationale, list):
        raise ClassificationValidationError("rationale must be a list")

    evidence_used = classification.get("evidence_used", [])
    if evidence_used is None or not isinstance(evidence_used, list):
        raise ClassificationValidationError("evidence_used must be a list")

    rejected_dnas = classification.get("rejected_dnas", [])
    if rejected_dnas is None or not isinstance(rejected_dnas, list):
        raise ClassificationValidationError("rejected_dnas must be a list")
    for index, item in enumerate(rejected_dnas):
        if not isinstance(item, dict):
            raise ClassificationValidationError(f"rejected_dnas[{index}] must be an object")
        if not str(item.get("name") or "").strip():
            raise ClassificationValidationError(f"rejected_dnas[{index}].name is required")
        if not str(item.get("reason") or "").strip():
            raise ClassificationValidationError(f"rejected_dnas[{index}].reason is required")

    confidence = classification.get("confidence")
    if confidence is not None:
        try:
            numeric_confidence = float(confidence)
        except (TypeError, ValueError) as exc:
            raise ClassificationValidationError("confidence must be a number between 0 and 1") from exc
        if not 0 <= numeric_confidence <= 1:
            raise ClassificationValidationError("confidence must be a number between 0 and 1")

    if business_dnas and not rationale:
        raise ClassificationValidationError("selected business_dnas require non-empty rationale")
    if business_dnas and not evidence_used:
        raise ClassificationValidationError("selected business_dnas require non-empty evidence_used")
    if not business_dnas:
        if not rationale:
            raise ClassificationValidationError("empty business_dnas require non-empty rationale")
        if not rejected_dnas:
            raise ClassificationValidationError("empty business_dnas require non-empty rejected_dnas")

    discovery_profile = classification.get("discovery_profile", DEFAULT_DISCOVERY_PROFILE)
    if not isinstance(discovery_profile, dict):
        raise ClassificationValidationError("discovery_profile must be an object")
    if not isinstance(discovery_profile.get("priority_entities", []), list):
        raise ClassificationValidationError("discovery_profile.priority_entities must be a list")
    if not isinstance(discovery_profile.get("priority_events", []), list):
        raise ClassificationValidationError("discovery_profile.priority_events must be a list")

    extraction_profile = classification.get("extraction_profile", DEFAULT_EXTRACTION_PROFILE)
    if not isinstance(extraction_profile, dict):
        raise ClassificationValidationError("extraction_profile must be an object")
    if not isinstance(extraction_profile.get("high_priority_sections", []), list):
        raise ClassificationValidationError("extraction_profile.high_priority_sections must be a list")

    template = classification.get("report_template")
    if template not in SUPPORTED_TEMPLATES:
        raise ClassificationValidationError("report_template is not supported")
