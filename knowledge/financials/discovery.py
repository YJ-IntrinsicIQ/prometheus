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
    "notes to consolidated financial statements",
    "notes to standalone financial statements",
    "notes forming part of financial statements",
    "property, plant and equipment",
    "capital work in progress",
    "borrowings",
    "revenue from operations",
    "deferred tax",
    "current tax",
    "lease liabilities",
    "investments",
    "research and development expenditure",
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
    if re.search(
        r"\b(?:fy\s?\d{2,4}|20\d{2}-\d{2}|(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+20\d{2}|\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+20\d{2})\b",
        lowered,
    ):
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
        if category in PRIMARY_SECTION_KEYS:
            hits = [hit for hit in hits if lowered.find(hit.lower()) <= 200]
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

    balance_sheet_sections_present = (
        "assets" in lowered
        and (
            "equity and liabilities" in lowered
            or (
                "liabilities" in lowered
                and "equity" in lowered
                and any(
                    token in lowered
                    for token in ("total assets", "non-current assets", "non current assets", "current assets")
                )
            )
        )
    )
    cash_flow_structure_present = (
        any(pattern in lowered for pattern in PRIMARY_PATTERNS["primary_cash_flow_statement"])
        or "cash flow from operating activities" in lowered
        or "cash flows from operating activities" in lowered
        or "net cash flow from operating activities" in lowered
    )
    cash_flow_continuation_signals = _continuation_row_signals("primary_cash_flow_statement", text)
    cash_flow_continuation_present = (
        len([signal for signal in cash_flow_continuation_signals if signal.startswith("continuation:")]) >= 2
        and "numeric_density" in cash_flow_continuation_signals
    )
    if (
        (
            cash_flow_structure_present
            and ("particulars" in lowered or "note" in lowered)
            and "period_columns" in common_signals
        )
        or cash_flow_continuation_present
    ):
        if not any(pattern in lowered for pattern in AUDITOR_PATTERNS + ACCOUNTING_POLICY_PATTERNS):
            candidates.append(
                (
                    "primary_cash_flow_statement",
                    ["structural:operating_cash_flow", *common_signals, *cash_flow_continuation_signals],
                    130,
                )
            )
    balance_sheet_structure = (
        balance_sheet_sections_present
        and not cash_flow_structure_present
        and ("particulars" in lowered or "note" in lowered)
        and "period_columns" in common_signals
        and len(re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", text)) >= 6
    )
    if balance_sheet_structure:
        candidates.append(
            (
                "primary_balance_sheet_statement",
                [
                    "structural:assets_equity_liabilities",
                    *common_signals,
                ],
                130,
            )
        )

    for category in ("share_capital_note", "eps_note", "dividend_note", "shareholding_note", "corporate_action_note"):
        add(category, SPECIFIC_NOTE_PATTERNS[category], 70)

    add("financial_note", GENERIC_NOTE_PATTERNS, 60)

    if not candidates and _contains_any(text, IRRELEVANT_FINANCIAL_HINTS):
        signals = [f"match:{hit}" for hit in _contains_any(text, IRRELEVANT_FINANCIAL_HINTS)]
        candidates.append(("irrelevant_financial_text", signals + common_signals, 10))

    filtered: List[Tuple[str, List[str], int]] = []
    for category, signals, score in candidates:
        has_primary_statement_structure = "structural:assets_equity_liabilities" in signals
        if category == "statement_of_changes_in_equity":
            if "statement of changes in equity" not in lowered and not (
                "other equity" in lowered and any(token in lowered for token in ("balance at", "opening balance", "closing balance"))
            ):
                continue
        if category in PRIMARY_SECTION_KEYS:
            if _is_non_primary_statement_fragment(text):
                continue
            if "analysis of the balance sheet" in lowered or "analysis of the profit and loss statement" in lowered:
                continue
            if (
                any(pattern in lowered for pattern in AUDITOR_PATTERNS + ACCOUNTING_POLICY_PATTERNS)
                and not has_primary_statement_structure
            ):
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


PRIMARY_CONTINUATION_ROW_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "primary_profit_and_loss_statement": (
        "profit before tax",
        "tax expense",
        "total tax expense",
        "profit for the year",
        "profit for the period",
        "profit attributable to owners",
        "profit for the year attributable to owners",
        "non-controlling interests",
        "earnings per equity share",
    ),
    "primary_balance_sheet_statement": (
        "total assets",
        "current assets",
        "non-current assets",
        "non current assets",
        "total equity",
        "equity and liabilities",
        "total liabilities",
        "other equity",
        "current liabilities",
    ),
    "primary_cash_flow_statement": (
        "cash flow from operating activities",
        "net cash generated from operating activities",
        "net cash generated from/(used in) operating activities",
        "net cash generated from / (used in) operating activities",
        "net cash flow from operating activities",
        "net cash flow from / (used in) operating activities",
        "net cash used in investing activities",
        "net cash flow from / (used in) investing activities",
        "net cash flow from investing activities",
        "payments for purchase of property, plant and equipment",
        "cash and cash equivalents at end",
        "cash and cash equivalents at the end",
        "net cash used in financing activities",
        "net cash flow from / (used in) financing activities",
        "net cash flow from financing activities",
        "proceeds from",
        "repayment of",
        "dividend paid",
        "interest paid",
    ),
}

# Structural completeness markers for primary statements
PRIMARY_COMPLETENESS_MARKERS: Dict[str, Tuple[str, ...]] = {
    "primary_profit_and_loss_statement": (
        "profit for the year",
        "profit for the period",
        "profit attributable to owners",
        "earnings per equity share",
    ),
    "primary_balance_sheet_statement": (
        "total assets",
        "total equity",
        "equity and liabilities",
        "total liabilities",
    ),
    "primary_cash_flow_statement": (
        "cash and cash equivalents at end",
        "cash and cash equivalents at the end",
        "net cash generated from operating activities",
        "net cash used in operating activities",
    ),
}

# Markers that indicate a fragment is incomplete (mid-table)
PRIMARY_INCOMPLETE_START_MARKERS: Dict[str, Tuple[str, ...]] = {
    "primary_profit_and_loss_statement": (
        "total income",
        "total expenses",
        "profit before",
        "tax expense",
    ),
    "primary_balance_sheet_statement": (
        "non-current assets",
        "current assets",
        "non current assets",
        "equity",
        "liabilities",
    ),
    "primary_cash_flow_statement": (
        "adjustments for",
        "operating activities",
        "investing activities",
        "financing activities",
    ),
}

# Markers that indicate a fragment is incomplete (end cut off)
PRIMARY_INCOMPLETE_END_MARKERS: Dict[str, Tuple[str, ...]] = {
    "primary_profit_and_loss_statement": (
        "total income",
        "total expenses",
        "profit before",
        "tax expense",
        "profit for the year",
    ),
    "primary_balance_sheet_statement": (
        "current assets",
        "non-current assets",
        "equity",
        "liabilities",
        "total equity",
    ),
    "primary_cash_flow_statement": (
        "adjustments for",
        "operating activities",
        "investing activities",
        "financing activities",
        "cash generated",
    ),
}


NON_PRIMARY_STATEMENT_FRAGMENT_PATTERNS = (
    "form aoc",
    "aoc - 1",
    "aoc-1",
    "statement containing salient features",
    "name of the subsidiary company",
    "date of acquisition of subsidiary",
    "date of acquisition/ incorporation of subsidiary",
    "percentage of shareholding",
    "% of shareholding",
    "business combinations",
    "purchase consideration was allocated",
    "fair value of the acquired assets",
    "total net identifiable assets",
    "research and development expenditure included in the statement of profit and loss",
    "research and development expenditure included in the consolidated statement of profit and loss",
    "research and development expenditure included in the standalone statement of profit and loss",
    "tax reconciliation",
    "reconciliation of tax expense",
)


def _is_non_primary_statement_fragment(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in NON_PRIMARY_STATEMENT_FRAGMENT_PATTERNS)


def _continuation_row_signals(section_name: str, text: str) -> List[str]:
    lowered = text.lower()
    signals = [f"continuation:{pattern}" for pattern in PRIMARY_CONTINUATION_ROW_PATTERNS.get(section_name, ()) if pattern in lowered]
    if section_name == "primary_profit_and_loss_statement" and re.search(r"\([ivxlcdm]+\)\s+profit", lowered):
        signals.append("continuation:roman_profit_row")
    if len(re.findall(r"\b\d[\d,]*(?:\.\d+)?%?\b", text)) >= 4:
        signals.append("numeric_density")
    if re.search(r"\b(?:year ended|as at|march\s+\d{1,2},?\s+20\d{2})\b", lowered):
        signals.append("period_columns")
    return signals


def _assess_fragment_completeness(section_name: str, text: str) -> Dict[str, Any]:
    """Assess whether a primary statement fragment is complete or incomplete."""
    lowered = text.lower()
    markers = PRIMARY_COMPLETENESS_MARKERS.get(section_name, ())
    incomplete_start = PRIMARY_INCOMPLETE_START_MARKERS.get(section_name, ())
    incomplete_end = PRIMARY_INCOMPLETE_END_MARKERS.get(section_name, ())

    # Check for structural completeness markers (found at end of statement)
    completeness_hits = [m for m in markers if m in lowered]

    # Check for incomplete start markers (mid-table beginning)
    start_hits = [m for m in incomplete_start if m in lowered]

    # Check for incomplete end markers (cut off before completion)
    end_hits = [m for m in incomplete_end if m in lowered]

    # Has period columns
    has_periods = bool(re.search(r"\b(?:year ended|as at|march\s+\d{1,2},?\s+20\d{2})\b", lowered))

    # Has numeric density
    numeric_hits = len(re.findall(r"\b\d[\d,]*(?:\.\d+)?%?\b", text))
    has_numeric = numeric_hits >= 4

    is_complete = len(completeness_hits) > 0 and has_periods and has_numeric
    is_incomplete_start = len(start_hits) > 0 and not any(m in lowered for m in completeness_hits[:2])
    is_incomplete_end = len(end_hits) > 0 and not any(m in lowered for m in completeness_hits)

    return {
        "is_complete": is_complete,
        "is_incomplete_start": is_incomplete_start,
        "is_incomplete_end": is_incomplete_end,
        "completeness_signals": completeness_hits,
        "start_signals": start_hits,
        "end_signals": end_hits,
        "has_periods": has_periods,
        "has_numeric": has_numeric,
        "numeric_count": numeric_hits,
    }


def _is_primary_continuation_candidate(section_name: str, text: str) -> bool:
    lowered = text.lower()
    if any(pattern in lowered for pattern in AUDITOR_PATTERNS + ACCOUNTING_POLICY_PATTERNS):
        return False
    if _is_non_primary_statement_fragment(text):
        return False
    signals = _continuation_row_signals(section_name, text)
    row_signals = [signal for signal in signals if signal.startswith("continuation:")]
    return len(row_signals) >= 2 and "numeric_density" in signals


def _get_primary_statement_fragment_spans(
    section_name: str, chunks: List[Dict[str, Any]], anchors: List[Any], positions: Dict[str, int]
) -> List[List[Dict[str, Any]]]:
    """
    Group continuation chunks into ordered fragment spans for each primary statement.
    Returns list of fragment spans (each span is an ordered list of chunks belonging together).
    """
    if not anchors:
        return []

    # Sort anchors by position
    anchor_positions = sorted([(positions[item.chunk_id], item) for item in anchors if item.chunk_id in positions])

    fragment_spans = []

    for anchor_pos, anchor in anchor_positions:
        # Start a new fragment span with the anchor
        span = [anchor]

        # Look forward and backward for continuation chunks
        # Scan forward
        for pos in range(anchor_pos + 1, len(chunks)):
            chunk = chunks[pos]
            chunk_id = str(chunk.get("chunk_id") or "").strip()
            if not chunk_id:
                continue

            # Check if same page or adjacent page
            anchor_page = anchor.page if isinstance(anchor.page, int) else None
            chunk_page = chunk.get("page")
            if isinstance(anchor_page, int) and isinstance(chunk_page, int) and abs(chunk_page - anchor_page) > 2:
                break

            text = _clean_text(chunk.get("text", ""))
            if not text:
                continue

            # Check if this is a continuation of the same primary statement
            if _is_primary_continuation_candidate(section_name, text):
                # Verify it's the same basis or compatible
                basis, _, _ = detect_basis(text=text, signals=_continuation_row_signals(section_name, text))
                anchor_basis = getattr(anchor, "basis", "unknown")
                if basis != "unknown" and anchor_basis != "unknown" and basis != anchor_basis:
                    break  # Different basis - stop assembly

                span.append(DiscoveredSectionItem(
                    section_type=section_name,
                    source_artifact=chunk.get("source_artifact", anchor.source_artifact),
                    page=chunk.get("page"),
                    chunk_id=chunk_id,
                    text_excerpt=_truncate(text),
                    confidence="high",
                    reasoning=f"Detected {section_name.replace('_', ' ')} continuation (fragment assembly) adjacent to chunk {anchor.chunk_id}.",
                    basis=basis if basis != "unknown" else anchor_basis,
                    basis_confidence=getattr(anchor, "basis_confidence", "medium"),
                    signals=["continuation:primary_statement", *_continuation_row_signals(section_name, text)],
                ))
            else:
                # Not a continuation - stop scanning forward
                break

        # Scan backward (for chunks before the anchor that might be part of the same table)
        for pos in range(anchor_pos - 1, -1, -1):
            chunk = chunks[pos]
            chunk_id = str(chunk.get("chunk_id") or "").strip()
            if not chunk_id:
                continue

            # Check if same page or adjacent page
            anchor_page = anchor.page if isinstance(anchor.page, int) else None
            chunk_page = chunk.get("page")
            if isinstance(anchor_page, int) and isinstance(chunk_page, int) and abs(chunk_page - anchor_page) > 2:
                break

            text = _clean_text(chunk.get("text", ""))
            if not text:
                continue

            # Check if this is a continuation of the same primary statement
            if _is_primary_continuation_candidate(section_name, text):
                basis, _, _ = detect_basis(text=text, signals=_continuation_row_signals(section_name, text))
                anchor_basis = getattr(anchor, "basis", "unknown")
                if basis != "unknown" and anchor_basis != "unknown" and basis != anchor_basis:
                    break

                span.insert(0, DiscoveredSectionItem(
                    section_type=section_name,
                    source_artifact=chunk.get("source_artifact", anchor.source_artifact),
                    page=chunk.get("page"),
                    chunk_id=chunk_id,
                    text_excerpt=_truncate(text),
                    confidence="high",
                    reasoning=f"Detected {section_name.replace('_', ' ')} continuation (fragment assembly) adjacent to chunk {anchor.chunk_id}.",
                    basis=basis if basis != "unknown" else anchor_basis,
                    basis_confidence=getattr(anchor, "basis_confidence", "medium"),
                    signals=["continuation:primary_statement", *_continuation_row_signals(section_name, text)],
                ))
            # Also check for structural context chunks (unit headers, period columns, "particulars")
            # that precede the data chunks but don't match continuation patterns
            elif _is_structural_context_chunk(section_name, text):
                basis, _, _ = detect_basis(text=text, signals=_continuation_row_signals(section_name, text))
                anchor_basis = getattr(anchor, "basis", "unknown")
                if basis != "unknown" and anchor_basis != "unknown" and basis != anchor_basis:
                    break

                span.insert(0, DiscoveredSectionItem(
                    section_type=section_name,
                    source_artifact=chunk.get("source_artifact", anchor.source_artifact),
                    page=chunk.get("page"),
                    chunk_id=chunk_id,
                    text_excerpt=_truncate(text),
                    confidence="high",
                    reasoning=f"Detected {section_name.replace('_', ' ')} structural context (unit/period header) adjacent to chunk {anchor.chunk_id}.",
                    basis=basis if basis != "unknown" else anchor_basis,
                    basis_confidence=getattr(anchor, "basis_confidence", "medium"),
                    signals=["structural:context_header", *_continuation_row_signals(section_name, text)],
                ))
            else:
                break

        fragment_spans.append(span)

    return fragment_spans


def _is_primary_continuation_candidate(section_name: str, text: str) -> bool:
    lowered = text.lower()
    if any(pattern in lowered for pattern in AUDITOR_PATTERNS + ACCOUNTING_POLICY_PATTERNS):
        return False
    if _is_non_primary_statement_fragment(text):
        return False
    signals = _continuation_row_signals(section_name, text)
    row_signals = [signal for signal in signals if signal.startswith("continuation:")]
    return len(row_signals) >= 2 and "numeric_density" in signals


def _is_structural_context_chunk(section_name: str, text: str) -> bool:
    """
    Detect structural context chunks that precede primary statement data chunks.
    These are typically unit headers (e.g., 'in Million'), period columns, 'Particulars' headers,
    or statement title lines that don't have numeric density but are essential for parsing.
    """
    lowered = text.lower()

    # Reject auditor/accounting policy content
    if any(pattern in lowered for pattern in AUDITOR_PATTERNS + ACCOUNTING_POLICY_PATTERNS):
        return False
    if _is_non_primary_statement_fragment(text):
        return False

    # Look for structural context signals
    structural_signals = []

    # Unit headers: "in Million", "in `", "in Crore", "in Lakhs", etc.
    if re.search(r"\bin\s+(million|crore|lakh|`|rupees?|rs\.?)\b", lowered):
        structural_signals.append("structural:unit_header")

    # "Particulars" column header
    if "particulars" in lowered:
        structural_signals.append("structural:particulars_header")

    # Period columns: "Year ended March 31, 2025", "As at March 31, 2026"
    if re.search(r"\b(?:year ended|as at)\s+\w+\s+\d{1,2},?\s+20\d{2}", lowered):
        structural_signals.append("structural:period_columns")

    # Statement title in the chunk (e.g., "Consolidated Statement of Cash Flow")
    if section_name == "primary_cash_flow_statement" and "consolidated statement of cash flow" in lowered:
        structural_signals.append("structural:statement_title")
    elif section_name == "primary_balance_sheet_statement" and ("balance sheet" in lowered or "statement of financial position" in lowered):
        structural_signals.append("structural:statement_title")
    elif section_name == "primary_profit_and_loss_statement" and ("profit and loss" in lowered or "statement of profit" in lowered):
        structural_signals.append("structural:statement_title")

    # Must have at least one structural signal
    if len(structural_signals) < 1:
        return False

    # Exclude year numbers (2024, 2025, etc.) from numeric density check
    # These appear in period headers but don't indicate table data density
    text_without_years = re.sub(r"\b20\d{2}\b", "", text)
    numeric_hits = len(re.findall(r"\b\d[\d,]*(?:\.\d+)?%?\b", text_without_years))
    has_numeric_density = numeric_hits >= 4

    return not has_numeric_density


def _ordered_chunk_positions(chunks: List[Dict[str, Any]]) -> Dict[str, int]:
    positions: Dict[str, int] = {}
    for index, chunk in enumerate(chunks):
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        if chunk_id:
            positions[chunk_id] = index
    return positions


# Schedule discovery for banking/NBFC formats (both Balance Sheet and P&L)
# RBI Schedule III format:
# Balance Sheet schedules: 6 (Cash & RBI), 7 (Balances with Banks), 8 (Investments), 9 (Advances), 10 (Fixed Assets), 11 (Other Assets)
# P&L schedules: 13 (Interest Earned), 14 (Other Income), 15 (Interest Expended), 16 (Operating Expenses)

# Balance Sheet schedule patterns (as table headers)
BALANCE_SHEET_SCHEDULE_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "schedule_6_cash_rbi": ("schedule -6", "cash and balances with reserve bank", "cash & balances with reserve bank"),
    "schedule_7_balances_banks": ("schedule -7", "balances with banks and money at call"),
    "schedule_8_investments": ("schedule -8", "investments"),
    "schedule_9_advances": ("schedule -9", "advances (net of provisions)"),
    "schedule_10_fixed_assets": ("schedule -10", "fixed assets", "property plant and equipment"),
    "schedule_11_other_assets": ("schedule -11", "other assets"),
}

# P&L schedule patterns (as table headers)
PANDL_SCHEDULE_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "schedule_13_interest_earned": ("schedule -13", "interest earned", "interest income"),
    "schedule_14_other_income": ("schedule -14", "other income"),
    "schedule_15_interest_expended": ("schedule -15", "interest expended", "interest expense", "interest paid"),
    "schedule_16_operating_expenses": ("schedule -16", "operating expenses", "operating expense"),
}

# Helper to check if text looks like a schedule table header
def _looks_like_schedule_header(text: str) -> bool:
    """Check if text appears to be a schedule table header (not just a mention)."""
    lowered = text.lower()
    return "schedule" in lowered and (
        "as on march" in lowered
        or "as at march" in lowered
        or "for the year ended" in lowered
        or "particulars" in lowered
        or "in 000" in lowered
        or "in `000" in lowered
        or "in '000" in lowered
    )


def _discover_schedule_relationships(
    *,
    result: FinancialDiscoveryResult,
    chunks: List[Dict[str, Any]],
    chunk_path: Path,
    seen: Dict[str, set[str]],
) -> None:
    """
    Discover schedule relationships for banking/NBFC formats.

    For RBI Schedule III format:
    - Balance Sheet references separate schedules (6-11)
    - Profit & Loss references separate schedules (13-16)

    This function detects these schedule references and adds them as discovered sections.
    """
    # Check if primary balance sheet has schedule references
    bs_items = result.sections.get("primary_balance_sheet_statement", [])
    pl_items = result.sections.get("primary_profit_and_loss_statement", [])

    # If we have a primary balance sheet, discover BS schedules
    if bs_items:
        _discover_balance_sheet_schedules(
            result=result, chunks=chunks, chunk_path=chunk_path, seen=seen
        )

    # If we have a primary P&L (or we're likely a banking company without single P&L), discover P&L schedules
    if pl_items:
        _discover_pandl_schedules(
            result=result, chunks=chunks, chunk_path=chunk_path, seen=seen
        )
    else:
        # For banking format, also try to discover P&L schedules even without a single P&L statement
        # Check if this appears to be a banking company (has banking schedule patterns in BS)
        has_banking_schedules = any(
            sched in result.sections for sched in BALANCE_SHEET_SCHEDULE_PATTERNS
        )
        if has_banking_schedules:
            _discover_pandl_schedules(
                result=result, chunks=chunks, chunk_path=chunk_path, seen=seen
            )


def _discover_balance_sheet_schedules(
    *,
    result: FinancialDiscoveryResult,
    chunks: List[Dict[str, Any]],
    chunk_path: Path,
    seen: Dict[str, set[str]],
) -> None:
    """Discover balance sheet schedules (6-11) for banking/NBFC."""
    # Scan all chunks for schedule references
    for chunk in chunks:
        text = _clean_text(chunk.get("text", "")).lower()
        if not text:
            continue

        chunk_id = str(chunk.get("chunk_id", "")).strip()
        page = chunk.get("page")

        # Check for schedule patterns - be restrictive to avoid false positives
        found_schedules = []
        for sched_name, patterns in BALANCE_SHEET_SCHEDULE_PATTERNS.items():
            if any(pattern in text for pattern in patterns):
                if _looks_like_schedule_header(text):
                    found_schedules.append(sched_name)

        if found_schedules:
            for sched in found_schedules:
                section_name = sched
                if section_name not in result.sections:
                    result.sections[section_name] = []

                dedupe_key = chunk_id or f"page:{page}"
                if dedupe_key in seen.get(section_name, set()):
                    continue

                result.sections.setdefault(section_name, []).append(
                    DiscoveredSectionItem(
                        section_type=section_name,
                        source_artifact=chunk_path.name,
                        page=page if isinstance(page, int) else None,
                        chunk_id=chunk_id,
                        text_excerpt=_truncate(text),
                        confidence="high",
                        reasoning=f"Detected banking balance sheet schedule: {sched} linked to primary balance sheet",
                        basis="consolidated",
                        basis_confidence="medium",
                        signals=[f"banking_schedule:{sched}", "linked_to:primary_balance_sheet_statement"],
                    )
                )
                seen.setdefault(section_name, set()).add(dedupe_key)


def _discover_pandl_schedules(
    *,
    result: FinancialDiscoveryResult,
    chunks: List[Dict[str, Any]],
    chunk_path: Path,
    seen: Dict[str, set[str]],
) -> None:
    """Discover P&L schedules (13-16) for banking/NBFC."""
    for chunk in chunks:
        text = _clean_text(chunk.get("text", "")).lower()
        if not text:
            continue

        chunk_id = str(chunk.get("chunk_id", "")).strip()
        page = chunk.get("page")

        # Check for P&L schedule patterns
        found_schedules = []
        for sched_name, patterns in PANDL_SCHEDULE_PATTERNS.items():
            if any(pattern in text for pattern in patterns):
                if _looks_like_schedule_header(text):
                    found_schedules.append(sched_name)

        if found_schedules:
            for sched in found_schedules:
                section_name = sched
                if section_name not in result.sections:
                    result.sections[section_name] = []

                dedupe_key = chunk_id or f"page:{page}"
                if dedupe_key in seen.get(section_name, set()):
                    continue

                result.sections.setdefault(section_name, []).append(
                    DiscoveredSectionItem(
                        section_type=section_name,
                        source_artifact=chunk_path.name,
                        page=page if isinstance(page, int) else None,
                        chunk_id=chunk_id,
                        text_excerpt=_truncate(text),
                        confidence="high",
                        reasoning=f"Detected banking P&L schedule: {sched} for profit and loss assembly",
                        basis="consolidated",
                        basis_confidence="medium",
                        signals=[f"banking_schedule:{sched}", "linked_to:primary_profit_and_loss_statement"],
                    )
                )
                seen.setdefault(section_name, set()).add(dedupe_key)


def _add_primary_statement_continuations(
    *,
    result: FinancialDiscoveryResult,
    chunks: List[Dict[str, Any]],
    chunk_path: Path,
    seen: Dict[str, set[str]],
) -> None:
    positions = _ordered_chunk_positions(chunks)

    for section_name in PRIMARY_SECTION_KEYS:
        anchors = [item for item in result.sections.get(section_name, []) if item.chunk_id in positions]
        if not anchors:
            continue
        anchor_positions = {positions[item.chunk_id]: item for item in anchors}
        for chunk in chunks:
            chunk_id = str(chunk.get("chunk_id") or "").strip()
            if not chunk_id or chunk_id in seen[section_name]:
                continue
            position = positions.get(chunk_id)
            if position is None:
                continue
            nearby = [
                anchor
                for anchor_position, anchor in anchor_positions.items()
                if abs(anchor_position - position) <= 1
                and (
                    not isinstance(anchor.page, int)
                    or not isinstance(chunk.get("page"), int)
                    or abs(int(chunk.get("page")) - anchor.page) <= 1
                )
            ]
            if not nearby:
                continue
            text = _clean_text(chunk.get("text", ""))
            if not text:
                continue

            # Check if this is a continuation candidate (has row data)
            is_continuation = _is_primary_continuation_candidate(section_name, text)
            # Check if this is a structural context chunk (unit headers, period columns, etc.)
            is_structural_context = _is_structural_context_chunk(section_name, text)

            if not is_continuation and not is_structural_context:
                continue

            anchor = sorted(nearby, key=lambda item: abs(positions[item.chunk_id] - position))[0]

            if is_continuation:
                signals = ["continuation:primary_statement", *_continuation_row_signals(section_name, text)]
                reasoning = f"Detected {section_name.replace('_', ' ')} continuation adjacent to primary statement chunk {anchor.chunk_id}."
            else:
                signals = ["structural:context_header", *_continuation_row_signals(section_name, text)]
                reasoning = f"Detected {section_name.replace('_', ' ')} structural context (unit/period header) adjacent to primary statement chunk {anchor.chunk_id}."

            basis, basis_confidence, basis_reasons = detect_basis(text=text, signals=signals)
            if basis == "unknown" and anchor.basis in {"standalone", "consolidated"}:
                basis = anchor.basis
                basis_confidence = anchor.basis_confidence
                basis_reasons = [f"basis inherited from adjacent {section_name} chunk {anchor.chunk_id}"]
            item_signals = list(dict.fromkeys([*signals, *basis_reasons]))
            page = chunk.get("page")
            result.sections[section_name].append(
                DiscoveredSectionItem(
                    section_type=section_name,
                    source_artifact=chunk_path.name,
                    page=page if isinstance(page, int) else None,
                    chunk_id=chunk_id,
                    text_excerpt=_truncate(text),
                    confidence="high",
                    reasoning=reasoning,
                    basis=basis,
                    basis_confidence=basis_confidence,
                    signals=item_signals,
                )
            )
            seen[section_name].add(chunk_id)


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

    _add_primary_statement_continuations(
        result=result,
        chunks=chunks,
        chunk_path=chunk_path,
        seen=seen,
    )

    # Discover schedule relationships for banking/NBFC formats
    _discover_schedule_relationships(
        result=result,
        chunks=chunks,
        chunk_path=chunk_path,
        seen=seen,
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
