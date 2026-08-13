from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .basis import detect_basis
from .discovery_schema import FINANCIAL_DISCOVERY_SECTIONS, FinancialDiscoveryResult
from .line_item_mapper import map_line_item
from .extraction_schema import (
    FINANCIAL_EXTRACTION_TABLES,
    ExtractedFinancialRow,
    ExtractedValue,
    FinancialExtractionResult,
    validate_financial_extraction_payload,
)
from .units import canonicalize_unit, convert_to_crore


SECTION_KEY_ROW_HINTS: Dict[str, Tuple[str, ...]] = {
    "profit_and_loss": ("revenue", "profit before tax", "profit for the year"),
    "balance_sheet": ("total assets", "equity share capital", "total liabilities"),
    "cash_flow": ("net profit before tax", "net cash generated", "net cash used"),
}

PRIMARY_HEADING_HINTS: Dict[str, Tuple[str, ...]] = {
    "profit_and_loss": ("statement of profit and loss", "profit and loss"),
    "balance_sheet": ("balance sheet", "statement of financial position"),
    "cash_flow": ("cash flow statement", "statement of cash flows"),
}

STOP_PHRASES = (
    "the accompanying notes are an integral part",
    "for deloitte",
    "for and on behalf",
    "basis for opinion",
    "significant accounting policies",
    "material accounting policy information",
)

PERCENT_LABEL_HINTS = ("holding", "shareholding", "pledged", "public", "promoter", "fii", "dii", "mutual fund")
NUMBER_TOKEN_RE = re.compile(r"^[\(\[]?-?(?:\d[\d,]*)(?:\.\d+)?[\)\]]?%?$")
NOTE_TOKEN_RE = re.compile(r"^\d{1,3}[a-z]?(?:\([^)]+\))?$", re.IGNORECASE)
DATE_PERIOD_RE = re.compile(
    r"(?:as at|for the year ended|year ended)\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
    re.IGNORECASE,
)
FY_PERIOD_RE = re.compile(r"\bFY\s?(\d{2,4})\b", re.IGNORECASE)
UNIT_WORD_RE = re.compile(r"\b(units?|shares?)\b", re.IGNORECASE)
MONTH_ONLY_RE = re.compile(r"^(january|february|march|april|may|june|july|august|september|october|november|december)$", re.IGNORECASE)

ROUTED_NOTE_TABLES = {
    "share_capital": ("equity share capital", "share capital", "authorised share capital", "issued subscribed"),
    "eps": ("earnings per share", "eps", "basic earnings per share", "diluted earnings per share", "nominal value of equity shares"),
    "dividend": ("dividend", "dividend per share", "final dividend", "interim dividend"),
    "shareholding_pattern": ("shareholding pattern", "distribution of shareholding", "promoters", "public shareholding"),
    "corporate_actions": ("qip", "qualified institutional placement", "buyback", "bonus issue", "rights issue", "preferential issue", "split", "sub-division"),
    "revenue": ("revenue from operations", "contract with customers", "other income", "total income"),
    "tax": ("tax", "deferred tax", "current tax", "tax expense"),
    "borrowings": ("borrowings", "loan", "debt", "financial liabilities"),
    "fixed_assets": ("property, plant and equipment", "capital work in progress", "cwip", "fixed assets"),
    "investment_schedule": ("investments", "mutual fund", "investment schedule", "current investments", "non-current investments"),
    "lease_note": ("lease", "right of use", "lease liabilities"),
}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_chunks(path: Path) -> List[Dict[str, Any]]:
    payload = _load_json(path)
    if isinstance(payload, dict):
        chunks = payload.get("chunks")
        if isinstance(chunks, list):
            return [item for item in chunks if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError(f"Unsupported clean_chunks payload shape: {path}")


def _parse_discovery(path: Path) -> FinancialDiscoveryResult:
    return FinancialDiscoveryResult.from_dict(_load_json(path))


def _basis_from_candidate(*, text: str, item: Any) -> str:
    basis_signals = list(getattr(item, "signals", []) or [])
    item_basis = str(getattr(item, "basis", "") or "")
    if item_basis in {"standalone", "consolidated"}:
        return item_basis
    basis, _, _ = detect_basis(
        text=" ".join(
            part
            for part in (
                str(getattr(item, "text_excerpt", "") or ""),
                text,
            )
            if part
        ),
        signals=basis_signals,
    )
    return basis


def _unit_hint(text: str, table_type: str) -> str:
    lowered = text.lower()
    if "per share" in lowered or table_type == "eps":
        return "INR per share" if any(token in lowered for token in ("rs", "₹", "inr")) else "per share"
    if "number of shares" in lowered or "weighted average" in lowered or "nominal value per share" in lowered:
        return "shares"
    if "units" in lowered:
        return "units"
    explicit_unit_patterns = (
        r"all figures are in ([a-z₹.\s]+?)(?: unless| specifically| otherwise|\))",
        r"all amounts are in ([a-z₹.\s]+?)(?: unless| specifically| otherwise|\))",
        r"\(rs\.?\s+in\s+([a-z.\s]+?)\)",
    )
    for pattern in explicit_unit_patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if not match:
            continue
        explicit_text = match.group(1)
        for candidate in ("crores", "crore", "cr", "lakhs", "lacs", "lakh", "million", "mn", "billion", "inr", "₹", "rupees"):
            if candidate in explicit_text:
                return candidate
    for candidate in ("crores", "crore", "cr", "lakhs", "lacs", "lakh", "million", "mn", "billion", "inr", "₹", "rupees"):
        if candidate in lowered:
            return candidate
    if "%" in text or (table_type == "shareholding_pattern" and any(hint in lowered for hint in PERCENT_LABEL_HINTS)):
        return "%"
    return ""


def _currency_hint(text: str) -> str:
    lowered = text.lower()
    if "inr" in lowered or "₹" in text or "rupees" in lowered or "rs." in lowered or "rs " in lowered:
        return "INR"
    return ""


def _table_score(text: str, table_type: str, source_section_type: str) -> int:
    lowered = text.lower()
    score = 0
    if "particulars" in lowered:
        score += 3
    if len(re.findall(r"\b\d[\d,]*(?:\.\d+)?%?\b", text)) >= 6:
        score += 3
    for hint in PRIMARY_HEADING_HINTS.get(table_type, ()):
        if hint in lowered:
            score += 4
    for phrases in ROUTED_NOTE_TABLES.values():
        if any(phrase in lowered for phrase in phrases):
            score += 1
    if source_section_type.startswith("primary_"):
        score += 3
    if source_section_type.endswith("_note"):
        score += 2
    if "auditor" in lowered or "opinion" in lowered or "policy" in lowered:
        score -= 3
    if any(stop in lowered for stop in STOP_PHRASES):
        score -= 2
    return score


def _looks_like_table_candidate(text: str, source_section_type: str) -> bool:
    lowered = text.lower()
    numeric_hits = len(re.findall(r"\b\d[\d,]*(?:\.\d+)?%?\b", text))
    has_table_header = "particulars" in lowered or "notes no" in lowered or "category" in lowered
    if source_section_type in {"accounting_policy", "auditor_report", "irrelevant_financial_text"}:
        return False
    if source_section_type in {"management_discussion_financial_summary"}:
        return has_table_header and numeric_hits >= 4
    return numeric_hits >= 4 and (has_table_header or source_section_type.startswith("primary_") or source_section_type.endswith("_note"))


def _trim_table_text(text: str, table_type: str) -> str:
    cleaned = _clean_text(text)
    lowered = cleaned.lower()
    starts = []
    if "particulars" in lowered:
        starts.append(lowered.index("particulars"))
    for hint in PRIMARY_HEADING_HINTS.get(table_type, ()):
        if hint in lowered:
            starts.append(lowered.index(hint))
    if starts:
        cleaned = cleaned[min(starts):]
        lowered = cleaned.lower()
    stop_positions = [lowered.find(stop) for stop in STOP_PHRASES if stop in lowered]
    if stop_positions:
        cleaned = cleaned[: min(stop_positions)].strip()
    return cleaned


def _strip_column_headers(text: str) -> str:
    cleaned = text
    cleaned = re.sub(
        r"^.*?\bparticulars\b(?:\s+notes?\s+no)?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(
        r"^(?:\s*(?:numbers?|amount))(?:\s+(?:numbers?|amount))*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    while True:
        updated = re.sub(
            r"^(?:\s*(?:As at|For the year ended)\s+[A-Za-z]+\s+\d{1,2},?\s+\d{4})+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        if updated == cleaned:
            break
        cleaned = updated
    cleaned = re.sub(
        r"^(?:\s*FY\s?\d{2,4})+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(r"^Category(?:\s+.*?)+", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _extract_periods(text: str) -> List[str]:
    periods: List[str] = []
    for match in DATE_PERIOD_RE.finditer(text):
        label = _clean_text(match.group(1))
        if label and label not in periods:
            periods.append(label)
    for match in FY_PERIOD_RE.finditer(text):
        label = f"FY{match.group(1)}"
        if label not in periods:
            periods.append(label)
    return periods


def _is_number_token(token: str) -> bool:
    return bool(NUMBER_TOKEN_RE.match(token))


def _parse_numeric_token(token: str) -> Optional[float]:
    raw = token.strip()
    if not raw:
        return None
    negative = raw.startswith("(") or raw.startswith("[") or raw.startswith("-")
    cleaned = raw.strip("()[]")
    cleaned = cleaned.replace(",", "").replace("%", "")
    if cleaned.startswith("-"):
        cleaned = cleaned[1:]
        negative = True
    if cleaned in {"", "-"}:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if negative else value


def _row_values_look_table_like(values: Sequence[str]) -> bool:
    return any("." in value or "," in value or "%" in value for value in values)


def _is_paragraph_like_label(label: str) -> bool:
    lowered = label.lower().strip()
    words = lowered.split()
    if len(words) > 14:
        return True
    if lowered.endswith("."):
        return True
    if any(phrase in lowered for phrase in ("the company", "the board", "in accordance with", "during the year", "independent auditor")):
        return True
    return False


def _should_skip_label(label: str, table_type: str) -> bool:
    lowered = label.lower().strip()
    if not lowered:
        return True
    if lowered in {"particulars", "notes no", "assets", "liabilities", "expenses", "category"}:
        return True
    if len(lowered) <= 1:
        return True
    if MONTH_ONLY_RE.match(lowered) and table_type != "statement_of_changes_in_equity":
        return True
    if table_type == "cash_flow" and lowered in {"a.", "b.", "c."}:
        return True
    if _is_paragraph_like_label(label):
        return True
    return False


def _normalize_label(label: str) -> str:
    cleaned = _clean_text(label)
    cleaned = re.sub(
        r"^.*?\b(?:particulars|category)\b(?:\s+notes?\s+no)?(?:\s+(?:fy\s?\d{2,4}|as at\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}|for the year ended\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}))*\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" :;-")


def _expected_value_count(tokens: Sequence[str], periods: Sequence[str]) -> int:
    if periods:
        return max(1, min(4, len(periods)))
    numeric_count = sum(1 for token in tokens if _is_number_token(token))
    if numeric_count >= 6:
        return 2
    return 1


def _split_rows(table_text: str, table_type: str) -> Tuple[List[Tuple[str, List[str]]], List[str], List[str]]:
    tokens = _strip_column_headers(table_text).split()
    if not tokens:
        return [], ["table appears empty after normalization"], []

    expected_values = _expected_value_count(tokens, _extract_periods(table_text))
    rows: List[Tuple[str, List[str]]] = []
    warnings: List[str] = []
    rejected_labels: List[str] = []
    label_tokens: List[str] = []
    index = 0

    while index < len(tokens):
        token = tokens[index]
        if NOTE_TOKEN_RE.match(token) and index + 1 < len(tokens) and _is_number_token(tokens[index + 1]):
            label = _normalize_label(" ".join(label_tokens))
            label_tokens = []
            if _should_skip_label(label, table_type):
                if label:
                    rejected_labels.append(label)
                index += 1
                continue
            values: List[str] = []
            index += 1
            while index < len(tokens) and _is_number_token(tokens[index]) and len(values) < max(expected_values, 4):
                values.append(tokens[index])
                index += 1
            if len(values) >= expected_values and _row_values_look_table_like(values):
                rows.append((label, values))
            else:
                rejected_labels.append(label)
                warnings.append(f"table appears truncated near line item: {label}")
            continue

        if _is_number_token(token):
            if not label_tokens:
                index += 1
                continue
            label = _normalize_label(" ".join(label_tokens))
            label_tokens = []
            if _should_skip_label(label, table_type):
                if label:
                    rejected_labels.append(label)
                index += 1
                while index < len(tokens) and _is_number_token(tokens[index]):
                    index += 1
                continue
            values = [token]
            index += 1
            while index < len(tokens) and _is_number_token(tokens[index]) and len(values) < max(expected_values, 4):
                values.append(tokens[index])
                index += 1
            if len(values) >= expected_values and _row_values_look_table_like(values):
                rows.append((label, values))
            else:
                rejected_labels.append(label)
            continue

        label_tokens.append(token)
        index += 1

    if table_type == "balance_sheet":
        rows = _label_balance_sheet_boundary_totals(rows)

    if not rows:
        warnings.append("no extractable table rows detected from candidate")
    return rows, warnings, rejected_labels


def _label_balance_sheet_boundary_totals(
    rows: Sequence[Tuple[str, List[str]]],
) -> List[Tuple[str, List[str]]]:
    """Restore an assets label only when a generic total sits at a hard section boundary.

    PDF text extraction can collapse ``TOTAL ASSETS`` into ``TOTAL`` while attaching
    ``EQUITY AND LIABILITIES`` to the following share-capital row.  The adjacency
    requirement keeps ordinary subtotals untouched and preserves the reported value.
    """
    labeled = list(rows)
    for index, (label, values) in enumerate(labeled[:-1]):
        normalized = _clean_text(label).lower()
        next_label = _clean_text(labeled[index + 1][0]).lower()
        if normalized in {"total", "total."} and "equity and liabilities" in next_label:
            labeled[index] = ("Total Assets", values)
    return labeled


def _confidence_for_rows(row_count: int, basis: str, score: int, is_primary_statement: bool) -> str:
    if is_primary_statement and row_count >= 5 and score >= 7 and basis != "unknown":
        return "high"
    if row_count >= 3 and score >= 4:
        return "medium"
    return "low"


def _period_labels(table_text: str, value_count: int) -> List[str]:
    periods = _extract_periods(table_text)
    if len(periods) >= value_count:
        return periods[:value_count]
    fallback = periods[:]
    while len(fallback) < value_count:
        fallback.append("PERIOD_COLUMN_UNRESOLVED")
    return fallback


def _share_capital_column_plan(table_text: str, value_count: int) -> Optional[List[Tuple[str, str, str]]]:
    lowered = table_text.lower()
    if value_count < 2 or value_count % 2 != 0:
        return None
    if "numbers" not in lowered or "amount" not in lowered:
        return None
    periods = _extract_periods(table_text)
    group_count = value_count // 2
    if len(periods) < group_count:
        periods = periods[:]
        while len(periods) < group_count:
            periods.append(f"value_group_{len(periods) + 1}")
    plan: List[Tuple[str, str, str]] = []
    for period in periods[:group_count]:
        plan.append((period, "share_count", "shares"))
        plan.append((period, "monetary", ""))
    return plan


def _infer_note_table_type(text: str) -> Optional[str]:
    lowered = text.lower()
    for table_type, phrases in ROUTED_NOTE_TABLES.items():
        if any(phrase in lowered for phrase in phrases):
            return table_type
    return None


def _route_candidate(source_section_type: str, text: str) -> Optional[Tuple[str, str, bool]]:
    if source_section_type == "primary_profit_and_loss_statement":
        return ("profit_and_loss", "profit_and_loss", True)
    if source_section_type == "primary_balance_sheet_statement":
        return ("balance_sheet", "balance_sheet", True)
    if source_section_type == "primary_cash_flow_statement":
        return ("cash_flow", "cash_flow", True)
    if source_section_type == "statement_of_changes_in_equity":
        return ("statement_of_changes_in_equity", "statement_of_changes_in_equity", False)
    if source_section_type == "management_discussion_financial_summary":
        lowered = text.lower()
        if "profit and loss" in lowered:
            return ("profit_and_loss", "management_discussion_financial_summary", False)
        if "balance sheet" in lowered:
            return ("balance_sheet", "management_discussion_financial_summary", False)
        if "cash flow" in lowered:
            return ("cash_flow", "management_discussion_financial_summary", False)
        return ("management_discussion_financial_summary", "management_discussion_financial_summary", False)
    if source_section_type in {"share_capital_note", "eps_note", "dividend_note", "shareholding_note", "corporate_action_note", "financial_note"}:
        inferred = _infer_note_table_type(text)
        if inferred:
            return (inferred, source_section_type, False)
        if source_section_type == "share_capital_note":
            return ("share_capital", source_section_type, False)
        if source_section_type == "eps_note":
            return ("eps", source_section_type, False)
        if source_section_type == "dividend_note":
            return ("dividend", source_section_type, False)
        if source_section_type == "shareholding_note":
            return ("shareholding_pattern", source_section_type, False)
        if source_section_type == "corporate_action_note":
            return ("corporate_actions", source_section_type, False)
    return None


def _detect_value_type(*, table_type: str, line_item_raw: str, raw_value: str, unit_hint: str) -> str:
    lowered_label = line_item_raw.lower()
    lowered_unit = unit_hint.lower()
    if raw_value.strip().endswith("%") or lowered_unit == "%" or any(hint in lowered_label for hint in PERCENT_LABEL_HINTS):
        return "percentage"
    if "per share" in lowered_label or "nominal value" in lowered_label or table_type == "eps":
        return "per_share"
    if "number of shares" in lowered_label or "weighted average" in lowered_label or lowered_unit == "shares":
        return "share_count"
    if "units" in lowered_label or lowered_unit == "units":
        return "unit_count"
    if re.search(r"\bratio[s]?\b", lowered_label):
        return "ratio"
    if lowered_unit in {"crores", "crore", "cr", "lakhs", "lacs", "lakh", "million", "mn", "billion", "inr", "₹", "rupees"}:
        return "monetary"
    return "unknown"


def _convert_value(raw_token: str, unit_hint: str, value_type: str) -> Optional[float]:
    numeric = _parse_numeric_token(raw_token)
    if numeric is None or value_type != "monetary" or not unit_hint:
        return None
    try:
        canonical_unit = canonicalize_unit(unit_hint)
        return convert_to_crore(numeric, canonical_unit)
    except ValueError:
        return None


def _build_row_objects(
    *,
    destination_table_type: str,
    source_section_type: str,
    statement_type: str,
    source_artifact: str,
    page: Optional[int],
    chunk_id: str,
    source_text: str,
    table_text: str,
    row_pairs: Sequence[Tuple[str, List[str]]],
    basis: str,
    score: int,
    warnings: Sequence[str],
    is_primary_statement: bool,
) -> List[ExtractedFinancialRow]:
    rows: List[ExtractedFinancialRow] = []
    unit_hint = _unit_hint(source_text, destination_table_type)
    currency_hint = _currency_hint(source_text)
    shared_periods = _period_labels(table_text, max((len(values) for _, values in row_pairs), default=1))
    table_confidence = _confidence_for_rows(len(row_pairs), basis, score, is_primary_statement)
    table_rejection_risk: List[str] = []
    if basis == "unknown":
        table_rejection_risk.append("basis unclear")
    if not unit_hint:
        table_rejection_risk.append("unit unclear")
    if score < 5:
        table_rejection_risk.append("weak table context")
    for label, raw_values in row_pairs:
        column_plan = (
            _share_capital_column_plan(table_text, len(raw_values))
            if destination_table_type == "share_capital" and source_section_type == "share_capital_note"
            else None
        )
        periods = [period for period, _, _ in column_plan] if column_plan else shared_periods[: len(raw_values)]
        values: List[ExtractedValue] = []
        for index, raw_value in enumerate(raw_values):
            per_value_unit_hint = unit_hint
            if column_plan and index < len(column_plan):
                _, value_type, plan_unit_hint = column_plan[index]
                if plan_unit_hint:
                    per_value_unit_hint = plan_unit_hint
            else:
                value_type = _detect_value_type(
                    table_type=destination_table_type,
                    line_item_raw=label,
                    raw_value=raw_value,
                    unit_hint=unit_hint,
                )
                if value_type == "percentage":
                    per_value_unit_hint = "%"
            values.append(
                ExtractedValue(
                    period=periods[index] if index < len(periods) else f"value_{index + 1}",
                    value_raw=raw_value,
                    unit_hint=per_value_unit_hint,
                    currency_hint=currency_hint,
                    value_crore=_convert_value(raw_value, per_value_unit_hint, value_type),
                    value_type=value_type,
                    raw_number=_parse_numeric_token(raw_value),
                )
            )
        row_warnings = list(warnings)
        if basis == "unknown":
            row_warnings.append("basis unclear")
        if not unit_hint:
            row_warnings.append("unit unclear")
        rows.append(
            ExtractedFinancialRow(
                statement_type=statement_type,
                table_type=destination_table_type,
                basis=basis,
                line_item_raw=label,
                values=values,
                source_artifact=source_artifact,
                page=page,
                chunk_id=chunk_id,
                confidence=table_confidence,
                source_section_type=source_section_type,
                table_confidence=table_confidence,
                table_rejection_risk=table_rejection_risk,
                is_primary_statement=is_primary_statement,
                warnings=row_warnings,
            )
        )
    return rows


def _dedupe_rows(rows: Iterable[ExtractedFinancialRow]) -> List[ExtractedFinancialRow]:
    deduped: List[ExtractedFinancialRow] = []
    seen = set()
    for row in rows:
        key = (
            row.table_type,
            row.basis,
            row.page,
            row.line_item_raw.lower(),
            tuple((value.period, value.value_raw) for value in row.values),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _missing_key_row_warning(table_type: str, rows: Sequence[ExtractedFinancialRow]) -> Optional[str]:
    expected = SECTION_KEY_ROW_HINTS.get(table_type)
    if not expected:
        return None
    labels = " ".join(row.line_item_raw.lower() for row in rows)
    for hint in expected:
        if hint not in labels:
            return f"{table_type} key rows appear incomplete"
    return None


def _canonical_fields_from_rows(rows: Sequence[ExtractedFinancialRow]) -> List[str]:
    fields: List[str] = []
    for row in rows:
        for match in map_line_item(table_type=row.table_type, line_item_raw=row.line_item_raw):
            field_name = f"{match.canonical_section}.{match.canonical_field}"
            if field_name not in fields:
                fields.append(field_name)
    return fields


def _candidate_report(
    *,
    section_name: str,
    discovery_items: Sequence[Any],
    extracted_rows: Sequence[ExtractedFinancialRow],
    required_fields: Sequence[str],
) -> Dict[str, Any]:
    page_numbers = sorted({item.page for item in discovery_items if isinstance(item.page, int)})
    candidate_rows = [
        row
        for row in extracted_rows
        if row.source_section_type == section_name and (not page_numbers or row.page in page_numbers)
    ]
    basis = "unknown"
    if candidate_rows:
        basis_counts: Dict[str, int] = {}
        for row in candidate_rows:
            basis_counts[row.basis] = basis_counts.get(row.basis, 0) + 1
        basis = max(basis_counts, key=basis_counts.get)
    positive_signals = []
    for item in discovery_items:
        for signal in getattr(item, "signals", [])[:3]:
            if signal not in positive_signals:
                positive_signals.append(signal)
    if candidate_rows:
        positive_signals.append(f"rows:{len(candidate_rows)}")
    matched_fields = set(_canonical_fields_from_rows(candidate_rows))
    missing_fields = [field for field in required_fields if field not in matched_fields]
    score = len(candidate_rows) * 10 + len(page_numbers) * 3 + len(matched_fields) * 5
    if basis != "unknown":
        score += 5
    selected = bool(candidate_rows) and not missing_fields
    rejection_reason = None
    negative_signals = []
    if not candidate_rows:
        rejection_reason = "no extracted rows linked to this candidate"
        negative_signals.append("no rows")
    elif missing_fields:
        rejection_reason = f"missing required fields: {', '.join(sorted(missing_fields))}"
        negative_signals.extend([f"missing:{field}" for field in missing_fields])
    return {
        "candidate_id": section_name,
        "pages": page_numbers,
        "title": section_name.replace("_", " ").title(),
        "section_type": section_name,
        "basis": basis,
        "score": score,
        "positive_signals": positive_signals,
        "negative_signals": negative_signals,
        "selected": selected,
        "rejection_reason": rejection_reason,
        "matched_fields": sorted(matched_fields),
        "row_count": len(candidate_rows),
    }


def build_financial_extraction_readiness(discovery: FinancialDiscoveryResult, result: FinancialExtractionResult) -> Dict[str, Any]:
    primary_requirements = {
        "primary_profit_and_loss_statement": ["profit_and_loss.revenue", "profit_and_loss.pat"],
        "primary_balance_sheet_statement": ["balance_sheet.total_assets", "balance_sheet.net_worth", "balance_sheet.equity_share_capital"],
        "primary_cash_flow_statement": ["cash_flow.cfo"],
    }
    primary_tables = {
        "primary_profit_and_loss_statement": "profit_and_loss",
        "primary_balance_sheet_statement": "balance_sheet",
        "primary_cash_flow_statement": "cash_flow",
    }

    statements_discovered = {
        section: len(discovery.sections.get(section, [])) > 0
        for section in primary_requirements
    }
    statements_extracted = {
        table_type: len(result.tables.get(table_type, []))
        for table_type in primary_tables.values()
    }

    candidate_reports = [
        _candidate_report(
            section_name=section_name,
            discovery_items=discovery.sections.get(section_name, []),
            extracted_rows=result.tables.get(primary_tables[section_name], []),
            required_fields=required_fields,
        )
        for section_name, required_fields in primary_requirements.items()
    ]

    missing_required_metrics: List[str] = []
    blocking_reasons: List[str] = []
    for section_name, required_fields in primary_requirements.items():
        if not statements_discovered[section_name]:
            continue
        report = next(item for item in candidate_reports if item["section_type"] == section_name)
        if not report["selected"]:
            blocking_reasons.append(f"{section_name}: {report['rejection_reason']}")
            continue
        matched = set(report["matched_fields"])
        if section_name == "primary_balance_sheet_statement":
            if not any(field in matched for field in required_fields):
                missing_required_metrics.append("balance_sheet.total_assets")
                blocking_reasons.append("primary_balance_sheet_statement: total assets missing")
            if not any(field in matched for field in ("balance_sheet.net_worth", "balance_sheet.equity_share_capital")):
                missing_required_metrics.append("balance_sheet.net_worth_or_equity_share_capital")
                blocking_reasons.append("primary_balance_sheet_statement: equity / net worth missing")
        else:
            for required_field in required_fields:
                if required_field not in matched:
                    missing_required_metrics.append(required_field)
                    blocking_reasons.append(f"{section_name}: {required_field} missing")

    status = "READY"
    if blocking_reasons:
        status = "BLOCKED"
    elif any(not report["selected"] for report in candidate_reports if report["row_count"] > 0):
        status = "PARTIAL"
    elif any(count == 0 for count in statements_extracted.values() if count > 0):
        status = "PARTIAL"

    basis_status = {
        "profit_and_loss": next((row.basis for row in result.tables.get("profit_and_loss", []) if row.basis in {"standalone", "consolidated"}), "unknown"),
        "balance_sheet": next((row.basis for row in result.tables.get("balance_sheet", []) if row.basis in {"standalone", "consolidated"}), "unknown"),
        "cash_flow": next((row.basis for row in result.tables.get("cash_flow", []) if row.basis in {"standalone", "consolidated"}), "unknown"),
    }

    candidate_confidence = {
        report["section_type"]: (
            "high" if report["selected"] and report["score"] >= 25 else "medium" if report["row_count"] > 0 else "low"
        )
        for report in candidate_reports
    }

    return {
        "company": result.company,
        "year": result.year,
        "generated_at": result.generated_at,
        "status": status,
        "reason_code": "FINANCIAL_EXTRACTION_NOT_READY" if status == "BLOCKED" else "",
        "statements_discovered": statements_discovered,
        "statements_extracted": statements_extracted,
        "row_counts": {
            table_type: len(result.tables.get(table_type, []))
            for table_type in FINANCIAL_EXTRACTION_TABLES
        },
        "candidate_confidence": candidate_confidence,
        "candidate_reports": candidate_reports,
        "basis_status": basis_status,
        "missing_required_metrics": sorted(set(missing_required_metrics)),
        "blocking_reasons": blocking_reasons,
    }


def _rejection_record(
    *,
    item: Any,
    reason: str,
    examples: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    return {
        "chunk_id": item.chunk_id,
        "source_page": item.page,
        "source_artifact": item.source_artifact,
        "section_type": item.section_type,
        "reason": reason,
        "examples_of_rejected_line_items": list(examples or []),
        "text_excerpt": item.text_excerpt,
    }


def extract_financial_tables(
    *,
    company: str,
    year: str,
    chunk_path: Path,
    discovery_path: Path,
) -> FinancialExtractionResult:
    chunks = _load_chunks(chunk_path)
    if not chunks:
        raise RuntimeError(f"financial_extraction requires non-empty chunks: {chunk_path}")
    discovery = _parse_discovery(discovery_path)
    by_chunk_id = {str(chunk.get("chunk_id", "")): chunk for chunk in chunks}

    result = FinancialExtractionResult(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        source_documents=list(discovery.source_documents),
        limitations=[
            "Financial extraction captures raw numeric rows from discovered table candidates only; it does not yet map line items into the canonical fundamentals schema or calculate ratios.",
            "Rows rejected as policy text, auditor text, weak table candidates, or ambiguous numeric content are written to financial_extraction_rejections.json for review.",
        ],
    )

    if not isinstance(discovery.sections, dict) or not any(
        discovery.sections.get(name) for name in FINANCIAL_DISCOVERY_SECTIONS
    ):
        raise RuntimeError(f"financial_extraction requires a valid discovery artifact: {discovery_path}")

    extracted_by_table: Dict[str, List[ExtractedFinancialRow]] = {name: [] for name in FINANCIAL_EXTRACTION_TABLES}

    for section_name in FINANCIAL_DISCOVERY_SECTIONS:
        candidates = discovery.sections.get(section_name, [])
        successful_candidates = 0
        per_section_tables: Dict[str, List[ExtractedFinancialRow]] = {}

        for item in candidates:
            chunk = by_chunk_id.get(item.chunk_id)
            if not chunk:
                result.rejections.append(_rejection_record(item=item, reason="chunk missing from clean chunks"))
                continue
            text = _clean_text(chunk.get("text", ""))
            if not text:
                result.rejections.append(_rejection_record(item=item, reason="empty chunk text"))
                continue

            route = _route_candidate(section_name, text)
            if route is None:
                result.rejections.append(_rejection_record(item=item, reason="section type intentionally excluded from extraction"))
                continue

            destination_table_type, statement_type, is_primary_statement = route
            score = _table_score(text, destination_table_type, section_name)
            if score < 3:
                result.rejections.append(_rejection_record(item=item, reason="weak table context score"))
                continue
            if not _looks_like_table_candidate(text, section_name):
                result.rejections.append(_rejection_record(item=item, reason="candidate does not look table-like"))
                continue

            table_text = _trim_table_text(text, destination_table_type)
            row_pairs, row_warnings, rejected_labels = _split_rows(table_text, destination_table_type)
            if not row_pairs:
                result.rejections.append(
                    _rejection_record(
                        item=item,
                        reason="no extractable table rows detected from candidate",
                        examples=rejected_labels[:10],
                    )
                )
                continue

            successful_candidates += 1
            built_rows = _build_row_objects(
                destination_table_type=destination_table_type,
                source_section_type=section_name,
                statement_type=statement_type,
                source_artifact=item.source_artifact,
                page=item.page,
                chunk_id=item.chunk_id,
                source_text=text,
                table_text=table_text,
                row_pairs=row_pairs,
                basis=_basis_from_candidate(text=text, item=item),
                score=score,
                warnings=row_warnings,
                is_primary_statement=is_primary_statement,
            )
            per_section_tables.setdefault(destination_table_type, []).extend(built_rows)
            if rejected_labels:
                result.rejections.append(
                    _rejection_record(
                        item=item,
                        reason="some rows rejected during table boundary detection",
                        examples=rejected_labels[:10],
                    )
                )

        for table_type, rows in per_section_tables.items():
            extracted_by_table[table_type].extend(rows)
            deduped = _dedupe_rows(extracted_by_table[table_type])
            extracted_by_table[table_type] = deduped
            if successful_candidates > 1 and table_type in {"profit_and_loss", "balance_sheet", "cash_flow", "share_capital", "eps", "dividend", "corporate_actions"}:
                warning = f"duplicate table candidates found for {table_type}"
                if warning not in result.warnings:
                    result.warnings.append(warning)

        if candidates and not per_section_tables and section_name not in {"auditor_report", "accounting_policy", "irrelevant_financial_text"}:
            result.warnings.append(f"no extractable financial rows found for {section_name}")

    result.tables = extracted_by_table

    for table_type, rows in result.tables.items():
        warning = _missing_key_row_warning(table_type, rows)
        if warning:
            result.warnings.append(warning)

    if not result.tables["cash_flow"]:
        result.warnings.append("cash flow missing")

    if sum(len(rows) for rows in result.tables.values()) <= 0:
        raise RuntimeError(
            f"financial_extraction found no extractable financial rows for {company} {year}"
        )

    errors = validate_financial_extraction_payload(result.to_dict())
    if errors:
        raise ValueError("; ".join(errors))
    return result


def _rejections_payload(result: FinancialExtractionResult) -> Dict[str, Any]:
    return {
        "company": result.company,
        "year": result.year,
        "generated_at": result.generated_at,
        "rejections": list(result.rejections),
    }


def write_financial_extraction(
    *,
    company: str,
    year: str,
    chunk_path: Path,
    discovery_path: Path,
    output_path: Path,
) -> FinancialExtractionResult:
    result = extract_financial_tables(
        company=company,
        year=year,
        chunk_path=chunk_path,
        discovery_path=discovery_path,
    )
    discovery = _parse_discovery(discovery_path)
    readiness = build_financial_extraction_readiness(discovery, result)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    rejections_path = output_path.parent / "financial_extraction_rejections.json"
    rejections_path.write_text(
        json.dumps(_rejections_payload(result), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    readiness_path = output_path.parent / "financial_extraction_readiness.json"
    readiness_path.write_text(json.dumps(readiness, indent=2, ensure_ascii=False), encoding="utf-8")
    if readiness.get("status") == "BLOCKED":
        raise RuntimeError(
            f"FINANCIAL_EXTRACTION_NOT_READY: {', '.join(readiness.get('blocking_reasons') or ['insufficient coverage'])}"
        )
    return result
