from __future__ import annotations

import json

from knowledge.business_blueprint import BusinessBlueprint

from .validator import ValidationError, validate_blueprint_payload


class ParserError(ValueError):
    pass


def parse_interpretation_payload(payload: str) -> BusinessBlueprint:
    try:
        parsed = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ParserError("Malformed JSON") from exc

    if not isinstance(parsed, dict):
        raise ParserError("Expected a JSON object")

    try:
        return validate_blueprint_payload(parsed)
    except ValidationError as exc:
        raise ParserError(str(exc)) from exc
