from __future__ import annotations

import json
from typing import Any, Dict


def _prune_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _prune_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_prune_none(item) for item in value]
    return value


def progression_payload_to_dict(payload: Any) -> Any:
    if hasattr(payload, "to_dict"):
        return payload.to_dict()
    if isinstance(payload, dict):
        return _prune_none(payload)
    if isinstance(payload, list):
        return [_prune_none(item) for item in payload]
    return payload


def stable_progression_json(payload: Dict[str, Any]) -> str:
    return json.dumps(progressive_payload := progression_payload_to_dict(payload), indent=2, ensure_ascii=False, sort_keys=True)

