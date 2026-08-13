from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence

from knowledge.company_memory import parse_financial_year


_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")

THEME_CATEGORY_KEYWORDS = {
    "strategy": ("strategy", "strategic", "corporate ambition", "business direction"),
    "growth": ("growth", "future outlook", "industry outlook", "market outlook", "opportunity"),
    "margins": ("margin", "profitability", "operating leverage", "gross margin", "ebitda margin"),
    "customers": ("customer", "client", "order", "contract", "demand"),
    "demand": ("demand", "bookings", "book order", "pipeline", "visibility"),
    "projects": ("project", "initiative", "programme", "program", "facility", "plant", "launch"),
    "capacity": ("capacity", "utilization", "utilisation", "throughput", "production line"),
    "products": ("product", "offering", "solution", "platform"),
    "technology": ("technology", "innovation", "r&d", "research", "digital", "software"),
    "capital_allocation": ("capital allocation", "capex", "dividend", "debt", "working capital", "investment"),
    "working_capital": ("working capital", "receivable", "inventory", "payable", "cash conversion"),
    "cash_flow": ("cash flow", "fcf", "free cash flow", "cfo", "cash generation"),
    "risk": ("risk", "mitigation", "uncertainty", "challenge", "headwind", "weakness"),
    "competition": ("competitive", "competition", "positioning", "advantage", "peer"),
    "geography": ("geography", "geographic", "export", "overseas", "international", "market entry"),
    "acquisitions": ("acquisition", "acquire", "merger", "integration", "takeover"),
    "execution": ("execution", "delivery", "implementation", "miss", "delay", "timing", "operational"),
    "governance": ("governance", "compliance", "audit", "board", "policy", "hr", "human resources"),
}


def normalize_text(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "")).strip()


def sanitize_public_text(value: Any) -> str:
    text = normalize_text(value)
    return text.replace("Pipeline", "Program").replace("pipeline", "program")


def slugify(value: Any) -> str:
    text = sanitize_public_text(value).lower()
    return _NORMALIZE_RE.sub("_", text).strip("_")


def title_case_label(value: Any) -> str:
    text = sanitize_public_text(value)
    if not text:
        return ""
    return " ".join(piece.capitalize() for piece in text.split())


def extract_year_label(value: Any) -> str:
    text = normalize_text(value).lower()
    if not text:
        return ""
    if text.startswith("fy"):
        return text
    if text.isdigit() and len(text) == 4:
        return f"fy{text[-2:]}"
    return text


def select_commentary_text(item: Dict[str, Any]) -> str:
    for field in ("commentary", "value", "statement", "summary", "description"):
        text = sanitize_public_text(item.get(field))
        if text:
            return text
    return ""


def derive_theme_category(theme_label: Any, commentary_text: str = "", fallback_category: Any = "") -> str:
    text = " ".join(
        [
            sanitize_public_text(theme_label).lower(),
            sanitize_public_text(commentary_text).lower(),
            sanitize_public_text(fallback_category).lower(),
        ]
    )
    for category, keywords in THEME_CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "other"


def build_theme_name(item: Dict[str, Any]) -> str:
    raw = item.get("theme") or item.get("category") or item.get("value") or item.get("commentary")
    text = title_case_label(raw)
    if text:
        return text
    return "Management Commentary"


def build_source_reference(year_record: Dict[str, Any], item: Dict[str, Any], source_kind: str) -> Dict[str, Any]:
    return {
        "period": extract_year_label(year_record.get("year")),
        "source_artifact": year_record.get("source_artifact", source_kind),
        "source_item_id": item.get("item_id") or item.get("source_item_id") or item.get("id") or item.get("value"),
        "page": item.get("page"),
        "source_kind": source_kind,
        "status": item.get("status"),
        "confidence": item.get("confidence"),
        "evidence_ids": list(item.get("evidence_ids") or []),
    }


def token_set(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        text = normalize_text(value).lower()
        text = _NORMALIZE_RE.sub(" ", text)
        tokens.update(token for token in text.split() if token)
    return tokens


def compact_text(value: Any, *, max_words: int = 20) -> str:
    words = sanitize_public_text(value).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(",;:")

