"""Financial period role contract for quarterly document processing.

A financial fact extracted from a quarterly report carries one of these roles
so downstream consumers can distinguish current-quarter results from
prior-period comparatives without collapsing them into a bare fiscal year.

This module owns:
  - FinancialPeriodRole enum (canonical role vocabulary)
  - interpret_period_role()  — deterministic, no-LLM mapping from a raw
    column-header string to a FinancialPeriodRole, given the document's
    reporting context (fiscal year + quarter).

Design rules:
  - No company-specific rules.
  - No LLM calls.
  - No silent derivation: reported facts stay reported facts.
  - UNKNOWN is always the safe fallback; never invent a role.
  - Q1 is never silently promoted to YEAR_TO_DATE in this layer; if the
    source column is "Q1", preserve it as CURRENT_QUARTER.  Only explicit
    "YTD" / "H1" / "9M" / "Six Months" column labels trigger those roles.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Canonical role enum
# ---------------------------------------------------------------------------

class FinancialPeriodRole(str, Enum):
    """Semantic role of a financial column in a periodic report."""

    CURRENT_QUARTER = "CURRENT_QUARTER"
    PREVIOUS_QUARTER = "PREVIOUS_QUARTER"
    PRIOR_YEAR_SAME_QUARTER = "PRIOR_YEAR_SAME_QUARTER"

    YEAR_TO_DATE = "YEAR_TO_DATE"
    PRIOR_YEAR_YTD = "PRIOR_YEAR_YTD"

    HALF_YEAR = "HALF_YEAR"
    PRIOR_YEAR_HALF_YEAR = "PRIOR_YEAR_HALF_YEAR"

    NINE_MONTHS = "NINE_MONTHS"
    PRIOR_YEAR_NINE_MONTHS = "PRIOR_YEAR_NINE_MONTHS"

    PRIOR_YEAR_FULL_YEAR = "PRIOR_YEAR_FULL_YEAR"
    FULL_YEAR_COMPARATIVE = "FULL_YEAR_COMPARATIVE"

    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Months that mark the end of Indian fiscal quarters:
#   Q1 ends June (6), Q2 ends September (9),
#   Q3 ends December (12), Q4 ends March (3).
_QUARTER_END_MONTHS = {6: 1, 9: 2, 12: 3, 3: 4}

_MONTH_ABBR: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}

# Compile once.
_RE_QNFYY = re.compile(
    r"\bq([1-4])\s*[-/]?\s*f\.?y\.?\s*(\d{2,4})\b",
    re.IGNORECASE,
)
_RE_FYY = re.compile(
    r"\bf\.?y\.?\s*(\d{2,4})\b",
    re.IGNORECASE,
)
_RE_HN_FYY = re.compile(
    r"\bh([12])\s*[-/]?\s*f\.?y\.?\s*(\d{2,4})\b",
    re.IGNORECASE,
)
_RE_YTD_FYY = re.compile(
    r"\bytd\s*[-/]?\s*f\.?y\.?\s*(\d{2,4})\b",
    re.IGNORECASE,
)
_RE_9M_FYY = re.compile(
    r"\b(?:9\s*m(?:onths?)?|nine\s+months?)\s*(?:[-/]?\s*f\.?y\.?\s*(\d{2,4}))?\b",
    re.IGNORECASE,
)
_RE_MON_YEAR = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"[\s\-,\.]*(\d{2,4})\b",
    re.IGNORECASE,
)
_RE_YEAR_ENDED = re.compile(
    r"\byear\s+ended\s+(?:march|mar)[\s\-,\.]*(?:\d{1,2}[\s,\.]+)?(\d{4})\b",
    re.IGNORECASE,
)


def _normalize_fy(raw: str) -> int:
    """Convert a raw FY string (2 or 4 digit) to a 2-digit FY integer.

    Examples: "27" → 27, "2027" → 27, "26" → 26, "2026" → 26.
    Returns -1 when the string cannot be parsed.
    """
    try:
        n = int(raw.strip())
    except ValueError:
        return -1
    if n > 100:
        return n % 100
    return n


def _fy_from_month_year(month: int, year_raw: int) -> int:
    """Derive the Indian 2-digit FY from a calendar month + year.

    Indian FY runs April → March.  A date in April–December belongs to
    FY(year+1); a date in January–March belongs to FY(year).

    Example: June 2026 → FY27, March 2026 → FY26, December 2026 → FY27.
    """
    if month >= 4:
        return (year_raw + 1) % 100
    else:
        return year_raw % 100


def _quarter_from_month(month: int) -> int:
    """Map an Indian quarter-end month to a quarter number (1–4).

    Returns 0 when the month is not a quarter-end.
    """
    return _QUARTER_END_MONTHS.get(month, 0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def interpret_period_role(
    period_str: str,
    *,
    context_fy: int,
    context_quarter: Optional[int],
) -> FinancialPeriodRole:
    """Map a raw column-header string to a FinancialPeriodRole.

    Args:
        period_str:      Raw column header from the source document
                         (e.g. "Q1 FY27", "Q1 FY26", "FY26", "H1FY27").
        context_fy:      2-digit fiscal year of the document
                         (e.g. 27 for a Q1 FY27 report).
        context_quarter: Quarter number of the document (1–4), or None for
                         full-year presentations where no quarter was explicitly
                         evidenced.  When None, quarterly patterns (Qn FYyy,
                         quarter-end month-year) return UNKNOWN — the safe
                         fallback.  Annual patterns (bare FYyy, half-year,
                         YTD, 9M) are unaffected and still resolve correctly.

    Returns:
        FinancialPeriodRole enum value.  Never raises; returns UNKNOWN when
        the column header cannot be mapped deterministically.
    """
    if not period_str or not period_str.strip():
        return FinancialPeriodRole.UNKNOWN

    s = period_str.strip()

    # ── 1. "Qn FYyy" pattern ─────────────────────────────────────────────
    m = _RE_QNFYY.search(s)
    if m:
        # No quarter context → cannot assign a quarterly role without fabricating one.
        if context_quarter is None:
            return FinancialPeriodRole.UNKNOWN

        q = int(m.group(1))
        fy = _normalize_fy(m.group(2))
        if fy == -1:
            return FinancialPeriodRole.UNKNOWN

        if fy == context_fy and q == context_quarter:
            return FinancialPeriodRole.CURRENT_QUARTER

        if q == context_quarter:
            if fy == context_fy - 1 or fy == (context_fy - 1) % 100:
                return FinancialPeriodRole.PRIOR_YEAR_SAME_QUARTER
            # Same quarter, different year (e.g. two years back) → UNKNOWN.

        if q == (context_quarter - 1) if context_quarter > 1 else 4:
            if fy == context_fy:
                return FinancialPeriodRole.PREVIOUS_QUARTER

        return FinancialPeriodRole.UNKNOWN

    # ── 2. Half-year "H1/H2 FYyy" ────────────────────────────────────────
    m = _RE_HN_FYY.search(s)
    if m:
        fy = _normalize_fy(m.group(2))
        if fy == context_fy:
            return FinancialPeriodRole.HALF_YEAR
        if fy == context_fy - 1 or fy == (context_fy - 1) % 100:
            return FinancialPeriodRole.PRIOR_YEAR_HALF_YEAR
        return FinancialPeriodRole.UNKNOWN

    # ── 3. YTD "YTD FYyy" ────────────────────────────────────────────────
    m = _RE_YTD_FYY.search(s)
    if m:
        fy = _normalize_fy(m.group(1))
        if fy == context_fy:
            return FinancialPeriodRole.YEAR_TO_DATE
        if fy == context_fy - 1 or fy == (context_fy - 1) % 100:
            return FinancialPeriodRole.PRIOR_YEAR_YTD
        return FinancialPeriodRole.UNKNOWN

    # ── 4. Nine months "9M FYyy" / "Nine Months FYyy" ───────────────────
    m = _RE_9M_FYY.search(s)
    if m:
        raw_fy = m.group(1)
        if raw_fy:
            fy = _normalize_fy(raw_fy)
            if fy == context_fy:
                return FinancialPeriodRole.NINE_MONTHS
            if fy == context_fy - 1 or fy == (context_fy - 1) % 100:
                return FinancialPeriodRole.PRIOR_YEAR_NINE_MONTHS
        # Nine months without explicit FY — assume current year.
        return FinancialPeriodRole.NINE_MONTHS

    # ── 5. "Year Ended March YYYY" ────────────────────────────────────────
    m = _RE_YEAR_ENDED.search(s)
    if m:
        year4 = int(m.group(1))
        fy = year4 % 100
        if fy == context_fy - 1 or fy == (context_fy - 1) % 100:
            return FinancialPeriodRole.PRIOR_YEAR_FULL_YEAR
        if fy == context_fy:
            return FinancialPeriodRole.FULL_YEAR_COMPARATIVE
        return FinancialPeriodRole.UNKNOWN

    # ── 6. Bare "FYyy" (annual, no quarter) ─────────────────────────────
    m = _RE_FYY.search(s)
    if m:
        fy = _normalize_fy(m.group(1))
        if fy == context_fy - 1 or fy == (context_fy - 1) % 100:
            return FinancialPeriodRole.PRIOR_YEAR_FULL_YEAR
        if fy == context_fy:
            return FinancialPeriodRole.FULL_YEAR_COMPARATIVE
        return FinancialPeriodRole.UNKNOWN

    # ── 7. Month-year "Jun-26", "June 2026" ─────────────────────────────
    m = _RE_MON_YEAR.search(s)
    if m:
        month = _MONTH_ABBR.get(m.group(1).lower()[:3], 0)
        if month == 0:
            return FinancialPeriodRole.UNKNOWN
        year_raw = int(m.group(2))
        if year_raw < 100:
            year_raw += 2000  # assume 21st century
        fy = _fy_from_month_year(month, year_raw)
        q = _quarter_from_month(month)

        if q > 0:
            # Quarter-end month — needs explicit quarter context.
            if context_quarter is None:
                return FinancialPeriodRole.UNKNOWN
            if fy == context_fy and q == context_quarter:
                return FinancialPeriodRole.CURRENT_QUARTER
            if q == context_quarter:
                if fy == context_fy - 1 or fy == (context_fy - 1) % 100:
                    return FinancialPeriodRole.PRIOR_YEAR_SAME_QUARTER
        else:
            # Year-end month or non-quarter-end.
            if month == 3:  # March — fiscal year end
                if fy == context_fy - 1 or fy == (context_fy - 1) % 100:
                    return FinancialPeriodRole.PRIOR_YEAR_FULL_YEAR
                if fy == context_fy:
                    return FinancialPeriodRole.FULL_YEAR_COMPARATIVE

        return FinancialPeriodRole.UNKNOWN

    return FinancialPeriodRole.UNKNOWN


def annotate_period_roles(
    values: list,
    *,
    context_fy: int,
    context_quarter: Optional[int],
) -> None:
    """Mutate a list of ExtractedValue objects in-place, setting period_role.

    This is the shared annotation pass that processors apply after financial
    extraction so every fact carries a period role.

    Args:
        values:          List of ExtractedValue objects (must have .period
                         and .period_role attributes).
        context_fy:      2-digit FY of the document.
        context_quarter: Quarter of the document (1–4), or None for full-year
                         presentations where no quarter was explicitly evidenced.
                         Quarterly patterns return UNKNOWN when None; annual
                         patterns (bare FYyy, H1/H2, YTD, 9M) resolve normally.
    """
    for v in values:
        if not getattr(v, "period_role", ""):
            role = interpret_period_role(
                v.period,
                context_fy=context_fy,
                context_quarter=context_quarter,
            )
            v.period_role = role.value
