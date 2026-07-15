from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from knowledge.business_blueprint import BusinessBlueprint

from .validator import ValidationError, validate_blueprint_payload


class ParserError(ValueError):
    pass


@dataclass
class InterpretationPayload:
    blueprint: BusinessBlueprint
    classification: Optional[Dict[str, Any]] = None


def parse_interpretation_bundle(payload: str) -> InterpretationPayload:
    try:
        parsed = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ParserError("Malformed JSON") from exc

    if not isinstance(parsed, dict):
        raise ParserError("Expected a JSON object")

    try:
        blueprint, classification = validate_blueprint_payload(parsed)
        return InterpretationPayload(
            blueprint=blueprint,
            classification=classification,
        )
    except ValidationError as exc:
        raise ParserError(str(exc)) from exc


def parse_interpretation_payload(payload: str) -> BusinessBlueprint:
    return parse_interpretation_bundle(payload).blueprint
