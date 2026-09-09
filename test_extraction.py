#!/usr/bin/env python3
"""Standalone test for the financial extraction fix."""

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ============ COPY OF EXTRACTOR FUNCTIONS ============

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
    r"(?:as at|as on|for the year ended|year ended)\s+("
    r"(?:[A-Za-z]+\s+\d{1,2},\s+\d{4})"
    r"|(?:\d{1,2}[/-]\d{1,2}[/-]\d{4})"
    r"|(?:\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})"
    r")",
    re.IGNORECASE,
)
FY_PERIOD_RE = re.compile(r"\bFY\s?(\d{2,4})\b", re.IGNORECASE)
MONTH_ONLY_RE = re.compile(r"^(january|february|march|april|may|june|july|august|september|october|november|december)$", re.IGNORECASE)
UNIT_HINT_CANDIDATES = (
    "crores", "crore", "lakhs", "lacs", "lakh", "millions", "million",
    "mn", "billion", "cr", "inr", "₹", "rupees",
)

def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()

def _trim_table_text(text: str, table_type: str) -> str:
    cleaned = _clean_text(text)
    lowered = cleaned.lower()
    starts = []
    if "particulars" in lowered:
        starts.append(lowered.index("particulars"))
    for hint in PRIMARY_HEADING_HINTS.get(table_type, ()):
        if hint in lowered:
            hint_index = lowered.index(hint)
            if hint_index <= 200:
                starts.append(hint_index)
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
    # Drop a trailing column-header row such as
    # ``Notes  Year ended March 31, 2022  Year ended March 31, 2021`` that
    # survives the "particulars" strip and would otherwise be glued onto the
    # first line-item label, causing the row to look paragraph-like and be rejected.
    # Match "Notes" followed by any text up to a roman-numeral label like (I), (II), etc.
    cleaned = re.sub(
        r"^\s*notes?\s+.*?(?=\([IVX]+\))",
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

def _is_number_token(token: str) -> bool:
    if not NUMBER_TOKEN_RE.match(token):
        return False
    # Exclude simple note-reference integers (e.g., "29", "30", "31") that appear
    # after line-item labels but before actual financial values. These are small
    # positive integers without commas, decimals, or parentheses.
    if token.isdigit() and 1 <= int(token) <= 100 and "." not in token and "," not in token:
        return False
    return True

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

def _row_values_look_table_like(values: Sequence[str]) -> bool:
    return any("." in value or "," in value or "%" in value for value in values)

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
    if table_type == "profit_and_loss" and any(
        token in lowered
        for token in (
            "profit before tax",
            "profit for the year",
            "profit for the period",
            "profit attributable to owners",
            "profit for the year attributable to owners",
            "total tax expense",
            "non-controlling interests",
        )
    ):
        return False
    if len(lowered.split()) > 14:
        return True
    if lowered.endswith("."):
        return True
    if any(phrase in lowered for phrase in ("the company", "the board", "in accordance with", "during the year", "independent auditor")):
        return True
    return False

def _capital_summary_row_is_salvageable(label: str, values: Sequence[str], table_type: str) -> bool:
    if table_type not in {"balance_sheet", "share_capital"}:
        return False
    normalized = _clean_text(label).lower()
    if not any(
        token in normalized
        for token in (
            "paid up capital",
            "paid-up capital",
            "issued, subscribed and called up capital",
            "issued subscribed and called up capital",
        )
    ):
        return False
    return any(_is_number_token(value) for value in values)

def _extract_periods(text: str) -> List[str]:
    periods: List[str] = []
    seen: set[str] = set()
    for match in DATE_PERIOD_RE.finditer(text):
        label = _clean_text(match.group(1))
        if label:
            key = label.lower()
            if key not in seen:
                seen.add(key)
                periods.append(label)
    for match in FY_PERIOD_RE.finditer(text):
        label = f"FY{match.group(1)}"
        key = label.lower()
        if key not in seen:
            seen.add(key)
            periods.append(label)
    return periods

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
            elif _capital_summary_row_is_salvageable(label, values, table_type):
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
            elif _capital_summary_row_is_salvageable(label, values, table_type):
                rows.append((label, values))
            else:
                rejected_labels.append(label)
            continue

        label_tokens.append(token)
        index += 1

    if table_type == "balance_sheet":
        # Simplified version of _label_balance_sheet_boundary_totals
        pass

    if not rows:
        warnings.append("no extractable table rows detected from candidate")
    return rows, warnings, rejected_labels

# ============ TEST ============

def load_chunks(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        chunks = payload.get("chunks")
        if isinstance(chunks, list):
            return [item for item in chunks if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError(f"Unsupported clean_chunks payload shape: {path}")

def load_discovery(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def test_fy22_pnl():
    """Test FY22 P&L extraction."""
    company = "sun_pharma"
    year = "fy22"

    chunk_path = Path(f"companies/{company}/{year}/extracted/clean_chunks.json")
    discovery_path = Path(f"companies/{company}/{year}/financials/financial_discovery.json")

    chunks = load_chunks(chunk_path)
    discovery = load_discovery(discovery_path)

    # Find P&L discovery items
    pnl_items = discovery.get("sections", {}).get("primary_profit_and_loss_statement", [])
    print(f"Found {len(pnl_items)} P&L discovery items")

    all_pnl_rows = []

    for item in pnl_items:
        chunk_id = item.get("chunk_id")
        chunk = next((c for c in chunks if c.get("chunk_id") == chunk_id), None)
        if not chunk:
            print(f"  Chunk {chunk_id} not found")
            continue

        text = _clean_text(chunk.get("text", ""))
        if not text:
            continue

        table_type = "profit_and_loss"
        trimmed = _trim_table_text(text, table_type)
        rows, warnings, rejected = _split_rows(trimmed, table_type)

        if rows:
            print(f"  Chunk {chunk_id} (page {chunk.get('page')}): {len(rows)} rows extracted")
            all_pnl_rows.extend(rows)
        else:
            print(f"  Chunk {chunk_id} (page {chunk.get('page')}): NO ROWS - {warnings}")
            if rejected:
                print(f"    Rejected: {rejected[:5]}")

    print(f"\nTotal P&L rows extracted: {len(all_pnl_rows)}")

    # Check for revenue
    revenue_found = False
    for label, values in all_pnl_rows:
        if "revenue" in label.lower() and "operations" in label.lower():
            print(f"\n✅ REVENUE FOUND: {label} = {values}")
            revenue_found = True

    if not revenue_found:
        print("\n❌ REVENUE NOT FOUND")
        # Show first 30 rows
        for label, values in all_pnl_rows[:30]:
            print(f"  {label}: {values}")

    return revenue_found, all_pnl_rows

if __name__ == "__main__":
    found, rows = test_fy22_pnl()
    if found:
        print("\n🎉 TEST PASSED: Revenue row extracted successfully!")
    else:
        print("\n❌ TEST FAILED: Revenue row not found")