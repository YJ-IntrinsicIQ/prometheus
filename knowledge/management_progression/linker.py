from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List


GENERIC_LINK_WORDS = {
    "growth",
    "expansion",
    "capacity",
    "platform",
    "efficiency",
    "business",
    "bounded",
    "control",
    "deliver",
    "delivery",
    "direction",
    "execution",
    "focus",
    "improve",
    "operating",
    "operational",
    "objective",
    "readiness",
    "project",
    "product",
    "development",
    "support",
}


def link_company_model_ids(text: str, company_model: Dict[str, Any]) -> List[str]:
    linked: List[str] = []
    normalized_text = _normalize(text)
    if not normalized_text:
        return []
    for item in company_model.get("offerings", []) or []:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("offering_id") or "").strip()
        candidates = [item.get("name"), item.get("description"), item.get("customer_problem_solved")]
        if identifier and _has_specific_overlap(normalized_text, candidates):
            linked.append(identifier)
    for item in company_model.get("revenue_engines", []) or []:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("engine_id") or "").strip()
        candidates = [item.get("description"), item.get("billing_basis")]
        if identifier and _has_specific_overlap(normalized_text, candidates):
            linked.append(identifier)
    return list(dict.fromkeys(linked))


def theme_key(text: str) -> str:
    words = [
        word
        for word in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(word) >= 4 and word not in GENERIC_LINK_WORDS
    ]
    return "_".join(words[:6]) or "unclassified_progression"


def duplicate_key(event: Dict[str, Any]) -> str:
    basis = "|".join(
        [
            str(event.get("role") or ""),
            str(event.get("event_type") or ""),
            str(event.get("source_period") or ""),
            str(event.get("event_period") or ""),
            _normalize(
                event.get("statement_text")
                or event.get("action_taken")
                or event.get("operational_outcome")
                or event.get("financial_or_business_outcome")
            )[:180],
            ",".join(sorted(_evidence_ids(event))),
        ]
    )
    return basis


def _evidence_ids(event: Dict[str, Any]) -> List[str]:
    ids = []
    for ref in event.get("evidence", []) or []:
        if isinstance(ref, dict) and ref.get("evidence_id"):
            ids.append(str(ref.get("evidence_id")))
    return ids


def _has_specific_overlap(text: str, candidates: Iterable[Any]) -> bool:
    text_words = set(_specific_words(text))
    if not text_words:
        return False
    for candidate in candidates:
        candidate_words = set(_specific_words(str(candidate or "")))
        if len(text_words & candidate_words) >= 2:
            return True
    return False


def _specific_words(text: str) -> List[str]:
    return [
        word
        for word in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(word) >= 5 and word not in GENERIC_LINK_WORDS
    ]


def _normalize(text: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))
