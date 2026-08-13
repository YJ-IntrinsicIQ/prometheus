from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .enums import CONFIDENCE_LEVELS


_LEVEL_ORDER = {"high": 3, "medium": 2, "low": 1, "unavailable": 0}


def _normalize_level(level: Any) -> str:
    candidate = str(level or "unavailable").strip().lower()
    return candidate if candidate in _LEVEL_ORDER else "unavailable"


def build_confidence(level: Any = "unavailable", basis: Iterable[Any] | None = None, limitations: Iterable[Any] | None = None) -> Dict[str, Any]:
    return {
        "level": _normalize_level(level),
        "basis": [str(item) for item in (basis or []) if str(item).strip()],
        "limitations": [str(item) for item in (limitations or []) if str(item).strip()],
    }


def aggregate_confidence(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    basis: List[str] = []
    limitations: List[str] = []
    strongest = "unavailable"

    for item in items:
        confidence = item.get("confidence") or {}
        level = _normalize_level(confidence.get("level"))
        if _LEVEL_ORDER[level] > _LEVEL_ORDER[strongest]:
            strongest = level
        for label in confidence.get("basis") or []:
            label_text = str(label).strip()
            if label_text and label_text not in basis:
                basis.append(label_text)
        for label in confidence.get("limitations") or []:
            label_text = str(label).strip()
            if label_text and label_text not in limitations:
                limitations.append(label_text)

    return build_confidence(strongest, basis=basis, limitations=limitations)

