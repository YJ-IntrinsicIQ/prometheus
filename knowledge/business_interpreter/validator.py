from __future__ import annotations

from typing import Any, Dict

from knowledge.business_blueprint import BusinessBlueprint


class ValidationError(ValueError):
    pass


def validate_blueprint_payload(payload: Dict[str, Any]) -> BusinessBlueprint:
    if not isinstance(payload, dict):
        raise ValidationError("payload must be an object")

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise ValidationError("metadata is required")
    if not metadata.get("company"):
        raise ValidationError("metadata.company is required")
    if not metadata.get("version"):
        raise ValidationError("metadata.version is required")
    confidence = metadata.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        raise ValidationError("metadata.confidence must be between 0 and 1")

    understanding = payload.get("business_understanding")
    if not isinstance(understanding, dict):
        raise ValidationError("business_understanding is required")
    if not understanding.get("business_summary"):
        raise ValidationError("business_understanding.business_summary is required")
    if not understanding.get("business_model"):
        raise ValidationError("business_understanding.business_model is required")

    characteristics = payload.get("characteristics")
    if not isinstance(characteristics, list) or not characteristics:
        raise ValidationError("characteristics must contain at least one item")
    seen = set()
    for index, characteristic in enumerate(characteristics):
        if not isinstance(characteristic, dict):
            raise ValidationError(f"characteristics[{index}] must be an object")
        name = (characteristic.get("name") or "").strip()
        if not name:
            raise ValidationError(f"characteristics[{index}].name is required")
        c_confidence = characteristic.get("confidence")
        if not isinstance(c_confidence, (int, float)) or not 0 <= float(c_confidence) <= 1:
            raise ValidationError(f"characteristics[{index}].confidence must be between 0 and 1")
        key = name.lower()
        if key in seen:
            raise ValidationError(f"duplicate characteristic: {name}")
        seen.add(key)

    reasoning = payload.get("reasoning")
    if not isinstance(reasoning, list) or not reasoning:
        raise ValidationError("reasoning must contain at least one item")
    for index, item in enumerate(reasoning):
        if isinstance(item, dict):
            statement = (item.get("statement") or "").strip()
        else:
            statement = str(item).strip()
        if not statement:
            raise ValidationError(f"reasoning[{index}].statement is required")

    return BusinessBlueprint.from_dict(payload)
