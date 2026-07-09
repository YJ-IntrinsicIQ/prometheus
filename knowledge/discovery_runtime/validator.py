from __future__ import annotations

from typing import Any, Dict, List

from knowledge.module_extractor.schema import ModuleExtractionResult
from knowledge.question_engine.schema import DiscoveryPlan, QuestionModule


class ValidationError(ValueError):
    pass


def validate_discovery_result(payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValidationError("payload must be an object")

    business_classification = payload.get("business_classification")
    executed_modules = payload.get("executed_modules")
    module_results = payload.get("module_results")
    statistics = payload.get("statistics")

    if not isinstance(business_classification, dict):
        raise ValidationError("business_classification must be an object")
    if not isinstance(executed_modules, list):
        raise ValidationError("executed_modules must be a list")
    if len(executed_modules) != len(set(executed_modules)):
        raise ValidationError("executed_modules must be unique")
    if not isinstance(module_results, list):
        raise ValidationError("module_results must be a list")
    if not isinstance(statistics, dict):
        raise ValidationError("statistics must be an object")

    for module_id in executed_modules:
        if not isinstance(module_id, str) or not module_id.strip():
            raise ValidationError("executed_modules must contain non-empty strings")

    for index, result in enumerate(module_results):
        if not isinstance(result, dict):
            raise ValidationError(f"module_results[{index}] must be an object")
        if not result.get("module_id"):
            raise ValidationError(f"module_results[{index}].module_id is required")

    if not isinstance(statistics.get("modules_executed"), int):
        raise ValidationError("statistics.modules_executed must be an integer")
