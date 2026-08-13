from __future__ import annotations

from collections import Counter
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

THESIS_IMPACT_VALUES = {"strengthens", "weakens", "neutral", "unresolved"}


def _clean_text(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def _clean_list(values: Any, limit: int = 3) -> List[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    items: List[str] = []
    for value in values:
        if isinstance(value, dict):
            text = _clean_text(
                value.get("summary")
                or value.get("conclusion")
                or value.get("what_changed")
                or value.get("description")
                or value.get("why_it_matters")
                or value.get("event")
                or value.get("question")
                or value.get("risk")
                or value.get("headline")
            )
        else:
            text = _clean_text(value)
        if text:
            items.append(text)
    deduped: List[str] = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _period_rank(value: Any) -> Tuple[int, int, str]:
    text = str(value or "").strip().lower()
    if not text:
        return (0, 0, "")
    match = re.search(r"(fy)?(\d{2,4})", text)
    if not match:
        return (1, 0, text)
    digits = match.group(2)
    year = int(digits)
    if year < 100:
        year += 2000 if year < 80 else 1900
    return (2, year, text)


def _confidence_rank(value: Any) -> int:
    text = str(value or "").strip().lower()
    if isinstance(value, dict):
        text = str(value.get("level") or "").strip().lower()
    return {"high": 3, "medium": 2, "low": 1, "unavailable": 0, "insufficient": 0}.get(text, 1 if text else 0)


def _materiality_rank(item: Dict[str, Any]) -> int:
    raw = item.get("materiality") or item.get("relevance") or item.get("importance") or item.get("priority")
    if isinstance(raw, dict):
        raw = raw.get("level") or raw.get("status") or raw.get("value")
    text = str(raw or "").strip().lower()
    if text in {"high", "material", "critical", "severe", "strong"}:
        return 3
    if text in {"medium", "moderate", "meaningful"}:
        return 2
    if text in {"low", "minor"}:
        return 1
    return 1 if text else 0


def _thesis_relevance_rank(item: Dict[str, Any], thesis_focus: Sequence[str]) -> int:
    if not thesis_focus:
        return 0
    haystack = " ".join(
        _clean_text(item.get(key), 180)
        for key in (
            "summary",
            "title",
            "description",
            "event",
            "conclusion",
            "why_it_matters",
            "economic_mechanism",
            "investor_implication",
            "mechanism",
            "risk_mechanism",
            "allocation_name",
            "project_name",
            "capacity_name",
            "risk_name",
            "theme_name",
        )
    ).lower()
    score = 0
    for term in thesis_focus:
        token = str(term or "").strip().lower()
        if token and token in haystack:
            score += 1
    return min(score, 3)


def _persistence_rank(item: Dict[str, Any], counts: Counter[str]) -> int:
    identity = _clean_text(item.get("summary") or item.get("title") or item.get("event") or item.get("conclusion"), 220).lower()
    if not identity:
        return 0
    count = counts.get(identity, 1)
    return min(count, 3) - 1 if count > 1 else 0


def _evidence_text(item: Dict[str, Any]) -> str:
    return _clean_text(
        item.get("summary")
        or item.get("conclusion")
        or item.get("what_changed")
        or item.get("description")
        or item.get("event")
        or item.get("why_it_matters")
        or item.get("title")
        or item.get("risk")
        or item.get("question")
    )


def rank_material_evidence(
    items: Sequence[Dict[str, Any]],
    *,
    limit: int = 3,
    latest_period: str = "",
    thesis_focus: Sequence[str] = (),
) -> List[Dict[str, Any]]:
    if not items:
        return []
    counts = Counter(
        _clean_text(item.get("summary") or item.get("title") or item.get("event") or item.get("conclusion"), 220).lower()
        for item in items
        if isinstance(item, dict)
    )
    latest_key = _period_rank(latest_period)

    def _score(item: Dict[str, Any]) -> Tuple[int, int, int, int, int, str]:
        return (
            _materiality_rank(item),
            _thesis_relevance_rank(item, thesis_focus),
            _persistence_rank(item, counts),
            _period_rank(item.get("period") or item.get("latest_period"))[1] - latest_key[1],
            _confidence_rank(item.get("confidence")),
            _evidence_text(item),
        )

    ranked = sorted((item for item in items if isinstance(item, dict)), key=_score, reverse=True)
    return ranked[:limit]


def build_interpretation_contract(
    *,
    conclusion: Any,
    what_changed: Iterable[Any],
    why_it_matters: Any,
    economic_mechanism: Any,
    thesis_impact: str,
    positive_evidence: Iterable[Any],
    negative_evidence: Iterable[Any],
    unresolved: Iterable[Any],
    what_to_watch: Iterable[Any],
    confidence: Any,
) -> Dict[str, Any]:
    impact = str(thesis_impact or "unresolved").strip().lower()
    if impact not in THESIS_IMPACT_VALUES:
        impact = "unresolved"
    return {
        "conclusion": _clean_text(conclusion, 260),
        "what_changed": _clean_list(list(what_changed), limit=3),
        "why_it_matters": _clean_text(why_it_matters, 260),
        "economic_mechanism": _clean_text(economic_mechanism, 260),
        "thesis_impact": impact,
        "positive_evidence": _clean_list(list(positive_evidence), limit=3),
        "negative_evidence": _clean_list(list(negative_evidence), limit=3),
        "unresolved": _clean_list(list(unresolved), limit=3),
        "what_to_watch": _clean_list(list(what_to_watch), limit=3),
        "confidence": confidence if isinstance(confidence, dict) else {"level": _clean_text(confidence, 40) or "medium", "basis": [], "limitations": []},
    }
