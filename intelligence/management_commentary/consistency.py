from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from .theme_mapper import normalize_text


def assess_consistency(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    periods = [str(event.get("period") or "") for event in events if str(event.get("period") or "").strip()]
    sentiments = [str((event.get("metadata") or {}).get("sentiment") or "").lower() for event in events if str((event.get("metadata") or {}).get("sentiment") or "").strip()]
    titles = [normalize_text(event.get("title")) for event in events if normalize_text(event.get("title"))]
    descriptions = [normalize_text(event.get("description")) for event in events if normalize_text(event.get("description"))]
    basis: List[str] = []
    limitations: List[str] = []

    if len(set(periods)) > 1:
        basis.append(f"theme observed across {len(set(periods))} fiscal year(s)")
    if titles:
        basis.append("management used recurring labels")
    if descriptions:
        basis.append("direct commentary available")

    if len(events) <= 1:
        limitations.append("single observation")
        return {"consistency_status": "unclear", "basis": basis, "limitations": limitations}

    if len(set(sentiments)) > 1 and any(sentiments):
        limitations.append("commentary sentiment changed across years")
        return {"consistency_status": "mixed", "basis": basis, "limitations": limitations}

    if len(set(title.lower() for title in titles if title)) > 1:
        basis.append("theme label changed across years")
        return {"consistency_status": "shifting", "basis": basis, "limitations": limitations}

    return {"consistency_status": "consistent", "basis": basis, "limitations": limitations}

