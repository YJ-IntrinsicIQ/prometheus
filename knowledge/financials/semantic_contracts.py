"""Metric-meaning contracts for the Financial Fact Registry.

A fact is usable downstream only when its SOURCE LINE can be what its metric says it is. The registry applies these contracts to every fact it keeps (changed or not), so a
line that shares words or a number with a metric - a total beside a residual, a component beside a total, an authorised ceiling beside paid-up capital, an accumulated balance
beside an annual charge, a sentence fragment, a note number - is made `invalid` (quarantined, never usable) with the reason recorded. They are rules about meaning, keyed
on metric and the statement's own wording; no company, year or amount appears here.
"""
from __future__ import annotations

import re
from typing import Callable, List, Optional, Tuple

_NARRATIVE = re.compile(r"\b(?:was|were|has been|have been|furthermore|pursuant|consequent|hereby|thereof|aforesaid)\b")
_SECTION_PREFIX = re.compile(r"\b(?:non[\s-]*current|current)\s+liabilities\b", re.I)
_MSME_COMPONENT = re.compile(r"micro\s+enterprises|\bmsme\b|other\s+than\s+micro", re.I)
_PAR_FROM_LABEL = re.compile(r"shares?\s+of\s+(?:[₹`]|rs\.?|re\.?|inr)\s*([\d.]+)\s*(?:/-)?\s*each", re.I)

# metric -> (fragments that mark a different quantity, reason)
CONTRADICTORY_FRAGMENTS = {
    "other_expenses": (("total expenses", "total expenditure", "total operating", "operating expenses"),
                       "a total of expenses contains the lines beside it; 'other expenses' is the residual heading only"),
    "depreciation": (("to date", "accumulated", "cumulative", "up to", "upto", "provision for depreciation"),
                     "an accumulated depreciation balance is a stock; the metric is the annual charge"),
    "equity_share_capital": (("authorised", "authorized", "furthermore", "revised from", "pending allotment"),
                             "authorised capital is a ceiling; the metric is the paid-up / issued capital"),
    "investments": (("associate", "joint venture", "subsidiar"),
                    "holdings in associates, joint ventures or subsidiaries are one component of investments, not the investments balance"),
    "cost_of_materials": (("stores and spare", "stores spares", "spare parts"),
                          "stores and spares are consumed inside other expenses (a note); the metric is the materials consumed in the cost of sales"),
    "ebit": (("before working capital", "working capital changes", "operating profit before"),
             "an operating-cash-flow subtotal (before working-capital changes) is not earnings before interest and tax"),
}


def _words(label: str) -> str:
    return " ".join(re.findall(r"[a-z()]+", str(label or "").lower()))


def _contradictory_fragment(fact) -> Optional[str]:
    fragments, reason = CONTRADICTORY_FRAGMENTS.get(fact.metric_id, ((), ""))
    label = _words(fact.source_line_item)
    hit = next((f for f in fragments if f in label), None)
    return f"the source line {fact.source_line_item!r} is not this metric (contains {hit!r}): {reason}" if hit else None


def _narrative_label(fact) -> Optional[str]:
    if _NARRATIVE.search(_words(fact.source_line_item)):
        return f"the source {str(fact.source_line_item)[:80]!r} is a sentence fragment of a note, not a statement line"
    return None


def _component_total_debt(fact) -> Optional[str]:
    if fact.metric_id == "total_debt" and not fact.derived and _SECTION_PREFIX.search(str(fact.source_line_item or "")):
        return f"{fact.source_line_item!r} is one section's borrowings (current or non-current), not total borrowings"
    if fact.metric_id == "total_debt" and fact.derived and re.search(r"\b(?:short_term_debt|long_term_debt) only\b", str(fact.formula or "")):
        return f"total debt is incomplete ({fact.formula}): one section's borrowings is not the total"
    return None


def _component_payables(fact) -> Optional[str]:
    if fact.metric_id == "payables" and not fact.derived and _MSME_COMPONENT.search(str(fact.source_line_item or "")):
        return f"{fact.source_line_item!r} is one part of trade payables (micro and small enterprises, or the remainder); the total needs both parts"
    return None


def _bare_gross_block_additions(fact) -> Optional[str]:
    if fact.metric_id == "gross_block_additions" and not fact.derived and re.fullmatch(r"additions?(?:\s+during\s+the\s+(?:year|period))?", _words(fact.source_line_item).replace("()", "").strip()):
        return "a bare 'Additions' row of an asset-class schedule: the cell read is one asset class's column, and the total column / row was not identified"
    return None


_EXPENSE_METRICS = {"finance_cost", "depreciation", "employee_cost", "cost_of_materials", "other_expenses"}


def _negative_expense(fact) -> Optional[str]:
    """An expense line is a positive charge. A negative 'finance cost' is the cash-flow statement's interest PAID (an outflow), a negative 'depreciation' a reversal or an
    accumulated balance: neither is the period's expense."""
    if fact.metric_id in _EXPENSE_METRICS and not fact.derived and isinstance(fact.value, (int, float)) and fact.value < 0:
        return f"{fact.metric_id} is negative ({fact.value}): a signed cash outflow or a reversal, not the period's expense"
    return None


def _par_value_cell(fact) -> Optional[str]:
    if fact.metric_id == "face_value":
        match = _PAR_FROM_LABEL.search(str(fact.source_line_item or ""))
        if match and isinstance(fact.value, (int, float)):
            try:
                stated = float(match.group(1).rstrip("."))
            except ValueError:
                return None
            if abs(float(fact.value) - stated) > 1e-9:
                return f"the cell {fact.value} sits beside 'shares of {stated:g} each': it is a capital amount, not the per-share face value"
    return None


def _maturity_scope(fact) -> Optional[str]:
    """Long-term and short-term borrowings are different maturities: a line printed under CURRENT liabilities (or 'current maturities') is not the long-term figure, a line under
    NON-CURRENT liabilities is not the short-term one."""
    if fact.derived or fact.metric_id not in {"long_term_debt", "short_term_debt"}:
        return None
    label = _words(fact.source_line_item)
    non_current = "non current" in label
    current = (not non_current and "current liabilities" in label) or "current maturities" in label
    if fact.metric_id == "long_term_debt" and current:
        return f"{fact.source_line_item!r} is printed under current liabilities (or is current maturities): it is the short-term maturity, not long-term debt"
    if fact.metric_id == "short_term_debt" and non_current and "current maturities" not in label:
        return f"{fact.source_line_item!r} is printed under non-current liabilities: it is the long-term maturity, not short-term debt"
    return None


def _bare_other_assets(fact) -> Optional[str]:
    label = _words(fact.source_line_item)
    if fact.metric_id == "other_assets" and not fact.derived and ("other assets" not in label or len(label.split()) > 6 or any(t in label for t in ("not included", "above categories", "exposure"))):
        return f"{fact.source_line_item!r} is a sub-line ('Others') of some heading, not the other-assets balance"
    return None


def _bank_cash(fact, *, bank_format: bool) -> Optional[str]:
    if bank_format and fact.metric_id == "cash_and_equivalents" and not fact.derived and fact.source_statement != "cash_flow":
        label = _words(fact.source_line_item)
        if "cash equivalents" not in label:
            return ("bank balance-sheet cash is 'Cash and balances with the Reserve Bank' (a component); cash and cash equivalents are defined by the cash-flow statement, "
                    "which adds bank balances and removes restricted deposits")
    return None


_RULES: Tuple[Callable, ...] = (_contradictory_fragment, _narrative_label, _component_total_debt, _component_payables, _bare_gross_block_additions, _negative_expense, _par_value_cell, _bare_other_assets, _maturity_scope)
_USABLE_STATES = {"present_direct", "present_derived", "partial"}


def semantic_problems(fact, *, bank_format: bool = False) -> List[str]:
    """Reasons the fact's source line cannot be the metric (empty when it can)."""
    if fact.availability_status not in _USABLE_STATES:
        return []
    problems = [message for rule in _RULES if (message := rule(fact))]
    cash = _bank_cash(fact, bank_format=bank_format)
    return problems + ([cash] if cash else [])


def enforce_semantic_contracts(fact, *, bank_format: bool = False) -> None:
    problems = semantic_problems(fact, bank_format=bank_format)
    if not problems:
        return
    fact.availability_status = "invalid"
    fact.confidence = "invalid"
    fact.usable_downstream = False
    fact.reconciliation_status = "fail"
    fact.warnings = list(fact.warnings) + [f"{fact.metric_id}: {problem}" for problem in problems]
