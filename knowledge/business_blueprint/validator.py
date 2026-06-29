from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .schema import BusinessBlueprint


class BlueprintValidationError(ValueError):
    pass


def validate_blueprint(blueprint: BusinessBlueprint) -> List[str]:
    errors: List[str] = []

    if not blueprint.metadata.company:
        errors.append("metadata.company is required")
    if not blueprint.metadata.version:
        errors.append("metadata.version is required")
    if not 0 <= blueprint.metadata.confidence <= 1:
        errors.append("metadata.confidence must be between 0 and 1")

    if not blueprint.business_understanding.business_summary:
        errors.append("business_understanding.business_summary is required")
    if not blueprint.business_understanding.business_model:
        errors.append("business_understanding.business_model is required")

    if not blueprint.characteristics:
        errors.append("characteristics must contain at least one item")
    else:
        for index, item in enumerate(blueprint.characteristics):
            if not item.name:
                errors.append(f"characteristics[{index}].name is required")
            if not 0 <= item.confidence <= 1:
                errors.append(f"characteristics[{index}].confidence must be between 0 and 1")

    if not blueprint.dnas:
        errors.append("dnas must contain at least one item")
    else:
        seen = set()
        for index, item in enumerate(blueprint.dnas):
            if not item.name:
                errors.append(f"dnas[{index}].name is required")
            if not 0 <= item.confidence <= 1:
                errors.append(f"dnas[{index}].confidence must be between 0 and 1")
            key = item.name.strip().lower()
            if key in seen:
                errors.append(f"duplicate dna entry: {item.name}")
            seen.add(key)

    for index, item in enumerate(blueprint.reasoning):
        statement = item.statement if hasattr(item, "statement") else str(item)
        if not statement or not str(statement).strip():
            errors.append(f"reasoning[{index}].statement is required")

    return errors


def validate_blueprint_payload(payload: Dict[str, Any]) -> Tuple[BusinessBlueprint, List[str]]:
    blueprint = BusinessBlueprint.from_dict(payload)
    errors = validate_blueprint(blueprint)
    if errors:
        raise BlueprintValidationError("; ".join(errors))
    return blueprint, errors
