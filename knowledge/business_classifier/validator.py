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

    question_modules = classification.get("question_modules", [])
    if not isinstance(question_modules, list):
        raise ClassificationValidationError("question_modules must be a list")
    if len(question_modules) != len(set(question_modules)):
        raise ClassificationValidationError("question_modules must be unique")

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
