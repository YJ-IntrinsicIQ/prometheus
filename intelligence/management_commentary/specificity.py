from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .theme_mapper import normalize_text


def _has_numeric_signal(text: str) -> bool:
    return any(ch.isdigit() for ch in text) or "%" in text or "₹" in text or "rs." in text.lower() or "crore" in text.lower()


def assess_specificity(item: Dict[str, Any], commentary_text: str, *, repeated_years: int = 1, related_links: int = 0) -> Dict[str, Any]:
    text = normalize_text(commentary_text)
    basis: List[str] = []
    limitations: List[str] = []
    score = 0

    if text:
        basis.append("direct management statement")
        score += 1
        if len(text.split()) >= 8:
            score += 1
        if len(text.split()) >= 18:
            score += 1
    if item.get("page") is not None:
        basis.append("page reference available")
        score += 1
    if item.get("time_reference") or item.get("year"):
        basis.append("time-specific disclosure")
        score += 1
    if _has_numeric_signal(text):
        basis.append("numeric or quantitative language present")
        score += 1
    if repeated_years > 1:
        basis.append("theme repeated across years")
        score += 1
    if related_links:
        basis.append("linked to related company-memory evidence")
        score += 1

    if not text:
        limitations.append("no commentary text available")
    if len(text.split()) < 8 if text else True:
        limitations.append("commentary remains brief")
    if not item.get("page"):
        limitations.append("page reference missing")
    if not _has_numeric_signal(text):
        limitations.append("no quantitative detail disclosed")

    if score >= 5:
        level = "high"
    elif score >= 3:
        level = "medium"
    else:
        level = "low"
    return {"level": level, "basis": basis, "limitations": limitations}

