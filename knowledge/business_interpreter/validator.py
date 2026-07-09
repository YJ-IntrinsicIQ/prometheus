from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from knowledge.business_blueprint import BusinessBlueprint


class ValidationError(ValueError):
    pass


def _validate_llm_classification_payload(payload: Any) -> Optional[Dict[str, Any]]:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValidationError("classification must be an object")

    selected = payload.get("selected_dnas", [])
    if not isinstance(selected, list):
        raise ValidationError("classification.selected_dnas must be a list")
    for index, item in enumerate(selected):
        if not isinstance(item, dict):
            raise ValidationError(f"classification.selected_dnas[{index}] must be an object")
        name = (item.get("name") or "").strip()
        if not name:
            raise ValidationError(f"classification.selected_dnas[{index}].name is required")
        confidence = item.get("confidence")
        if confidence is not None and (
            not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1
        ):
            raise ValidationError(
                f"classification.selected_dnas[{index}].confidence must be between 0 and 1"
            )

    rejected = payload.get("rejected_dnas", [])
    if not isinstance(rejected, list):
        raise ValidationError("classification.rejected_dnas must be a list")
    for index, item in enumerate(rejected):
        if not isinstance(item, dict):
            raise ValidationError(f"classification.rejected_dnas[{index}] must be an object")
        name = (item.get("name") or "").strip()
        reason = (item.get("reason") or "").strip()
        if not name:
            raise ValidationError(f"classification.rejected_dnas[{index}].name is required")
        if not reason:
            raise ValidationError(f"classification.rejected_dnas[{index}].reason is required")

    rationale = payload.get("rationale", [])
    if rationale is not None and not isinstance(rationale, list):
        raise ValidationError("classification.rationale must be a list")

    evidence_used = payload.get("evidence_used", [])
    if evidence_used is not None and not isinstance(evidence_used, list):
        raise ValidationError("classification.evidence_used must be a list")

    confidence = payload.get("confidence")
    if confidence is not None and (
        not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1
    ):
        raise ValidationError("classification.confidence must be between 0 and 1")

    return payload


def validate_blueprint_payload(payload: Dict[str, Any]) -> Tuple[BusinessBlueprint, Optional[Dict[str, Any]]]:
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

    classification = _validate_llm_classification_payload(payload.get("classification"))
    return BusinessBlueprint.from_dict(payload), classification
