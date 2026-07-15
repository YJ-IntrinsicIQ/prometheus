from __future__ import annotations

import json

from .validator import ValidationError, validate_module_extraction_payload


class ParserError(ValueError):
    pass


def parse_module_extraction_payload(payload: str):
    try:
        parsed = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ParserError("Malformed JSON") from exc

    if not isinstance(parsed, dict):
        raise ParserError("Expected a JSON object")

    try:
        return validate_module_extraction_payload(parsed)
    except ValidationError as exc:
        raise ParserError(str(exc)) from exc
