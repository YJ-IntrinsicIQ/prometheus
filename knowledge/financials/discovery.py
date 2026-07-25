from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.document_registry import DocumentRegistry
from .basis import detect_basis

from .discovery_schema import (
    FINANCIAL_DISCOVERY_SECTIONS,
    DiscoveredSectionItem,
    FinancialDiscoveryResult,
    validate_financial_discovery_payload,
)


MAX_EXCERPT_CHARS = 500
PRIMARY_SECTION_KEYS = (
    "primary_profit_and_loss_statement",
    "primary_balance_sheet_statement",
    "primary_cash_flow_statement",
)

PRIMARY_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "primary_profit_and_loss_statement": (
        "statement of profit and loss",
        "profit and loss statement",
        "statement of profit & loss",
    ),
    "primary_balance_sheet_statement": (
        "balance sheet",
        "statement of financial position",
    ),
    "primary_cash_flow_statement": (
        "cash flow statement",
        "statement of cash flows",
    ),
}

SPECIFIC_NOTE_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "statement_of_changes_in_equity": (
        "statement of changes in equity",
        "statement of changes in equity for the year",
        "other equity",
    ),
    "share_capital_note": (
        "equity share capital",
        "share capital",
        "issued subscribed and paid-up share capital",
    ),
    "eps_note": (
        "earnings per share",
        "basic earnings per share",
        "diluted earnings per share",
        "basic and diluted eps",
    ),
    "dividend_note": (
        "dividend per share",
        "interim dividend",
        "final dividend",
        "dividend proposed",
    ),
    "shareholding_note": (
        "shareholding pattern",
        "distribution of shareholding",
        "number of shareholders",
        "promoters",
        "public shareholding",
    ),
    "corporate_action_note": (
        "buyback",
        "bonus issue",
        "stock split",
        "sub-division",
        "rights issue",
        "preferential issue",
        "qualified institutional placement",
        "qip",
        "merger",
        "demerger",
    ),
}

GENERIC_NOTE_PATTERNS = (
    "notes to accounts",
    "notes to the financial statements",
    "notes forming part of financial statements",
    "property, plant and equipment",
    "capital work in progress",
    "borrowings",
    "revenue from operations",
    "deferred tax",
    "current tax",
    "lease liabilities",
    "investments",
)

ACCOUNTING_POLICY_PATTERNS = (
    "significant accounting policies",
    "summary of significant accounting policies",
    "material accounting policy information",
    "recognition and measurement",
    "recognised in the statement of profit and loss",
    "fair value through profit and loss",
)

AUDITOR_PATTERNS = (
    "independent auditor’s report",
    "independent auditor's report",
    "report on the audit of the standalone financial statements",
    "report on the audit of the consolidated financial statements",
    "basis for opinion",
    "our opinion on the financial statements",
    "key audit matters",
)

MANAGEMENT_SUMMARY_PATTERNS = (
    "analysis of the profit and loss statement",
    "analysis of the balance sheet",
    "performance highlights",
    "ratios particulars",
    "net worth stood at",
    "ebitda margin",
    "return on net worth",
)

IRRELEVANT_FINANCIAL_HINTS = (
    "financial section",
    "financial statements",
    "profit and loss",
    "balance sheet",
    "cash flow",
)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _truncate(text: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    cleaned = _clean_text(text)
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 3:
        return cleaned[:limit]
    return cleaned[: limit - 3].rstrip() + "..."


def _load_chunk_payload(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        chunks = payload.get("chunks")
        if isinstance(chunks, list):
            return [item for item in chunks if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError(f"Unsupported clean_chunks payload shape: {path}")


def _source_documents(company: str, year: str, chunk_path: Path) -> List[str]:
    documents: List[str] = []
    registry = DocumentRegistry(company=company, year=year, registry_file=chunk_path.parent.parent / "raw" / "document_registry.json")
    for record in registry.load():
        if not isinstance(record, dict):
            continue
        filename = record.get("filename")
        if filename:
            documents.append(str(filename))
    documents.append(str(chunk_path))
    deduped: List[str] = []
    for item in documents:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _contains_any(text: str, patterns: Iterable[str]) -> List[str]:
    lowered = text.lower()
    return [pattern for pattern in patterns if pattern in lowered]


def _table_like_signals(text: str) -> List[str]:
    lowered = text.lower()
    signals: List[str] = []
    numeric_hits = len(re.findall(r"\b\d[\d,]*(?:\.\d+)?%?\b", text))
    if numeric_hits >= 4:
        signals.append("numeric_density")
    if re.search(r"\b(?:fy\s?\d{2,4}|20\d{2}-\d{2}|march\s+\d{1,2},\s+20\d{2})\b", lowered):
        signals.append("period_columns")
    if re.search(r"\b(?:inr|rs\.?|₹|crores?|cr|lakhs?|lacs|million|mn|billion)\b", lowered):
        signals.append("unit_signal")
    if "particulars" in lowered:
        signals.append("particulars_header")
    return signals


def _statement_scope_signals(text: str) -> List[str]:
    lowered = text.lower()
    signals: List[str] = []
    if "consolidated" in lowered:
        signals.append("consolidated_hint")
    if "standalone" in lowered:
        signals.append("standalone_hint")
    return signals


def _confidence_for_category(category: str, signals: List[str]) -> str:
    heading_hits = [signal for signal in signals if signal.startswith("heading:")]
    table_hits = [signal for signal in signals if signal in {"numeric_density", "period_columns", "unit_signal", "particulars_header"}]
    if category in PRIMARY_SECTION_KEYS and heading_hits and len(table_hits) >= 2:
        return "high"
    if category.endswith("_note") and heading_hits and table_hits:
        return "high"
    if category in {"auditor_report", "accounting_policy", "management_discussion_financial_summary"} and heading_hits:
        return "high"
    if heading_hits or len(signals) >= 3:
        return "medium"
    return "low"


def _reasoning(category: str, signals: List[str]) -> str:
    if signals:
        return f"Detected {category.replace('_', ' ')} because of " + ", ".join(signals) + "."
    return f"Detected weak {category.replace('_', ' ')} signal."


def _category_candidates(text: str) -> List[Tuple[str, List[str], int]]:
    lowered = text.lower()
    common_signals = _table_like_signals(text) + _statement_scope_signals(text)
    candidates: List[Tuple[str, List[str], int]] = []

    def add(category: str, patterns: Iterable[str], base_score: int) -> None:
        hits = _contains_any(text, patterns)
        if not hits:
            return
        signals = [f"heading:{hit}" for hit in hits] + [signal for signal in common_signals if signal not in hits]
        candidates.append((category, signals, base_score + len(hits)))

    add("auditor_report", AUDITOR_PATTERNS, 120)
    add("accounting_policy", ACCOUNTING_POLICY_PATTERNS, 110)
    add("statement_of_changes_in_equity", SPECIFIC_NOTE_PATTERNS["statement_of_changes_in_equity"], 100)
    add("management_discussion_financial_summary", MANAGEMENT_SUMMARY_PATTERNS, 90)

    for category in PRIMARY_SECTION_KEYS:
        add(category, PRIMARY_PATTERNS[category], 80)

    for category in ("share_capital_note", "eps_note", "dividend_note", "shareholding_note", "corporate_action_note"):
        add(category, SPECIFIC_NOTE_PATTERNS[category], 70)

    add("financial_note", GENERIC_NOTE_PATTERNS, 60)

    if not candidates and _contains_any(text, IRRELEVANT_FINANCIAL_HINTS):
        signals = [f"match:{hit}" for hit in _contains_any(text, IRRELEVANT_FINANCIAL_HINTS)]
        candidates.append(("irrelevant_financial_text", signals + common_signals, 10))

    filtered: List[Tuple[str, List[str], int]] = []
    for category, signals, score in candidates:
        if category == "statement_of_changes_in_equity":
            if "statement of changes in equity" not in lowered and not (
                "other equity" in lowered and any(token in lowered for token in ("balance at", "opening balance", "closing balance"))
            ):
                continue
        if category in PRIMARY_SECTION_KEYS:
            if "analysis of the balance sheet" in lowered or "analysis of the profit and loss statement" in lowered:
                continue
            if any(pattern in lowered for pattern in AUDITOR_PATTERNS + ACCOUNTING_POLICY_PATTERNS):
                continue
        if category == "financial_note" and any(pattern in lowered for pattern in AUDITOR_PATTERNS + ACCOUNTING_POLICY_PATTERNS):
            continue
        filtered.append((category, signals, score))
    return filtered


def _best_category(text: str) -> Optional[Tuple[str, List[str]]]:
    candidates = _category_candidates(text)
    if not candidates:
        return None
    category, signals, _score = max(candidates, key=lambda item: item[2])
    return category, signals


def discover_financial_sections(*, company: str, year: str, chunk_path: Path) -> FinancialDiscoveryResult:
    chunks = _load_chunk_payload(chunk_path)
    if not chunks:
        raise RuntimeError(f"financial_discovery requires non-empty chunks: {chunk_path}")

    result = FinancialDiscoveryResult(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        source_documents=_source_documents(company, year, chunk_path),
        limitations=[
            "Discovery identifies likely financial-statement locations only; it does not extract final numbers or calculate ratios.",
            "Narrative accounting-policy, auditor-report, and management-discussion chunks are tagged separately so downstream extraction can reject them for primary statement use.",
        ],
    )
    seen: Dict[str, set[str]] = {section: set() for section in FINANCIAL_DISCOVERY_SECTIONS}

    for chunk in chunks:
        text = _clean_text(chunk.get("text", ""))
        if not text:
            continue
        best = _best_category(text)
        if best is None:
            continue
        category, signals = best
        page = chunk.get("page")
        chunk_id = str(chunk.get("chunk_id", "")).strip()
        dedupe_key = chunk_id or f"page:{page}"
        if dedupe_key in seen[category]:
            continue
        seen[category].add(dedupe_key)
        basis, basis_confidence, basis_reasons = detect_basis(text=text, signals=signals)
        item_signals = list(signals)
        for reason in basis_reasons:
            if reason not in item_signals:
                item_signals.append(reason)
        result.sections[category].append(
            DiscoveredSectionItem(
                section_type=category,
                source_artifact=chunk_path.name,
                page=page if isinstance(page, int) else None,
                chunk_id=chunk_id,
                text_excerpt=_truncate(text),
                confidence=_confidence_for_category(category, signals),
                reasoning=_reasoning(category, signals),
                basis=basis,
                basis_confidence=basis_confidence,
                signals=item_signals,
            )
        )

    discovered_count = sum(len(items) for items in result.sections.values())
    if discovered_count <= 0:
        raise RuntimeError(
            f"financial_discovery found no financial sections for {company} {year} in {chunk_path}"
        )

    if not result.sections["primary_cash_flow_statement"]:
        result.warnings.append("cash flow statement was not discovered")
    if not result.sections["shareholding_note"]:
        result.warnings.append("shareholding pattern was not discovered")

    major_items = [item for section_name in PRIMARY_SECTION_KEYS for item in result.sections[section_name]]
    if major_items and not any(
        "consolidated_hint" in item.signals or "standalone_hint" in item.signals
        for item in major_items
    ):
        result.warnings.append("consolidated/standalone distinction is unclear")

    if any(item.page is None for items in result.sections.values() for item in items):
        result.warnings.append("page numbers missing for one or more discovered sections")

    errors = validate_financial_discovery_payload(result.to_dict())
    if errors:
        raise ValueError("; ".join(errors))
    return result


def write_financial_discovery(*, company: str, year: str, chunk_path: Path, output_path: Path) -> FinancialDiscoveryResult:
    result = discover_financial_sections(company=company, year=year, chunk_path=chunk_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return result
