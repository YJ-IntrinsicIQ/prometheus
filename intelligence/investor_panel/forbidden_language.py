from __future__ import annotations

import re
from typing import Dict, List


ALLOWED_CORPORATE_ACTION_PHRASES = [
    "offer-for-sale",
    "offer for sale",
    "sale of shares",
    "share sale",
    "equity sale",
    "stake sale",
    "sales revenue",
    "net sales",
    "cost of sales",
    "defence sales",
    "authorized placement",
    "qualified institutional placement",
    "qip",
    "capital raising",
    "equity issuance",
    "share issuance",
    "divestment proceeds",
]

FORBIDDEN_LANGUAGE_RULES = [
    (
        "target_price_language",
        re.compile(r"\btarget price\b", re.IGNORECASE),
    ),
    (
        "fair_value_language",
        re.compile(r"\bfair value(?:\s+is)?\b", re.IGNORECASE),
    ),
    (
        "valuation_language",
        re.compile(r"\b(?:under|over)valued\b", re.IGNORECASE),
    ),
    (
        "valuation_language",
        re.compile(r"\bmultibagger\b", re.IGNORECASE),
    ),
    (
        "valuation_language",
        re.compile(r"\bcheap\s+(?:stock|shares|valuation|multiple|price)\b", re.IGNORECASE),
    ),
    (
        "valuation_language",
        re.compile(r"\bexpensive\s+(?:stock|shares|valuation|multiple|price)\b", re.IGNORECASE),
    ),
    (
        "recommendation_intent",
        re.compile(
            r"\b(?:buy|sell|hold|accumulate|exit|avoid)\s+(?:this|the)?\s*(?:stock|shares?|position|company|investment)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "recommendation_intent",
        re.compile(
            r"\b(?:recommend|recommended|recommends|recommending|recommendation)\b[\s:,-]*(?:to\s+)?(?:buy|sell|hold|accumulate|exit|avoid|buying|selling)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "recommendation_intent",
        re.compile(
            r"\b(?:investor|investors)\s+should\s+(?:buy|sell|hold|accumulate|exit|avoid)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "recommendation_intent",
        re.compile(
            r"\bshould\s+(?:buy|sell|hold|accumulate|exit|avoid)\s+(?:this|the)?\s*(?:stock|shares?|position|company|investment)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "recommendation_intent",
        re.compile(r"\bwould\s+(?:buy|sell|hold|accumulate|exit|avoid)\b", re.IGNORECASE),
    ),
    (
        "recommendation_intent",
        re.compile(
            r"\b(?:looks like|look[s]? like|is|seems|appears to be)\s+(?:a\s+)?(?:buy|sell|hold)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "recommendation_intent",
        re.compile(r"\bstrong\s+(?:buy|sell)\b", re.IGNORECASE),
    ),
    (
        "recommendation_intent",
        re.compile(r"\binvest now\b", re.IGNORECASE),
    ),
]


def _mask_allowed_phrases(text: str) -> str:
    masked = text
    for phrase in ALLOWED_CORPORATE_ACTION_PHRASES:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        masked = pattern.sub(lambda match: " " * len(match.group(0)), masked)
    return masked


def find_forbidden_recommendation_language(text: str) -> List[Dict[str, object]]:
    original = str(text or "")
    masked = _mask_allowed_phrases(original)
    matches: List[Dict[str, object]] = []
    seen = set()

    for reason, pattern in FORBIDDEN_LANGUAGE_RULES:
        for match in pattern.finditer(masked):
            key = (reason, match.start(), match.end(), match.group(0).lower())
            if key in seen:
                continue
            seen.add(key)
            matches.append(
                {
                    "term": pattern.pattern,
                    "matched_text": original[match.start():match.end()],
                    "reason": reason,
                    "start": match.start(),
                    "end": match.end(),
                }
            )

    return sorted(matches, key=lambda item: (int(item["start"]), int(item["end"])))


def has_forbidden_recommendation_language(text: str) -> bool:
    return bool(find_forbidden_recommendation_language(text))
