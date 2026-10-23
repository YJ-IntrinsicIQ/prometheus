"""
ENG-139 Regression Tests — CFO Extraction Correctness

Ensures the normalizer never misclassifies the PBT row (opening line of
indirect-method cash-flow statement) as the net operating cash flow (CFO),
and that the correct net OCF row is selected instead.

12 tests required by the ENG-139 closure gate.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from knowledge.financials.normalizer import normalize_financial_tables, write_normalized_fundamentals

# ---------------------------------------------------------------------------
# Helpers (mirror the pattern in test_financial_normalizer.py)
# ---------------------------------------------------------------------------

_YEAR = "fy26"
_PERIOD = "March 31, 2026"
_PRIOR_PERIOD = "March 31, 2025"


def _raw_value(
    period: str,
    value_raw: str,
    value_crore: Optional[float],
    unit_hint: str = "crore",
) -> Dict[str, Any]:
    return {
        "period": period,
        "value_raw": value_raw,
        "unit_hint": unit_hint,
        "currency_hint": "INR",
        "value_crore": value_crore,
        "value_type": "monetary",
        "raw_number": value_crore,
    }


def _row(
    table_type: str,
    line_item_raw: str,
    values: List[Tuple],
    *,
    basis: str = "consolidated",
    page: int = 246,
    confidence: str = "high",
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    normalized_values = []
    for item in values:
        if len(item) == 3:
            period, raw, crore = item
            unit = "crore"
        elif len(item) == 4:
            period, raw, crore, unit = item
        else:
            raise ValueError(f"Unexpected value tuple length: {len(item)}")
        normalized_values.append(_raw_value(period, raw, crore, unit))

    source_section = {
        "profit_and_loss": "primary_profit_and_loss_statement",
        "balance_sheet": "primary_balance_sheet_statement",
        "cash_flow": "primary_cash_flow_statement",
    }.get(table_type, table_type)

    return {
        "statement_type": table_type,
        "table_type": table_type,
        "basis": basis,
        "line_item_raw": line_item_raw,
        "values": normalized_values,
        "source_artifact": "clean_chunks.json",
        "page": page,
        "chunk_id": f"CHK-{page:06d}",
        "confidence": confidence,
        "source_section_type": source_section,
        "table_confidence": confidence,
        "table_rejection_risk": [],
        "is_primary_statement": table_type in {"profit_and_loss", "balance_sheet", "cash_flow"},
        "warnings": warnings or [],
    }


def _required_sections() -> Dict[str, List]:
    """Minimum rows that satisfy normalizer's revenue/balance-sheet requirements."""
    return {
        "profit_and_loss": [
            _row("profit_and_loss", "Revenue from operations",
                 [(_PERIOD, "58,462.04", 58462.04)]),
            _row("profit_and_loss", "Profit for the year",
                 [(_PERIOD, "11,479.42", 11479.42)]),
        ],
        "balance_sheet": [
            _row("balance_sheet", "Total Assets", [(_PERIOD, "80,000.00", 80000.0)]),
            _row("balance_sheet", "Total Equity", [(_PERIOD, "55,000.00", 55000.0)]),
            _row("balance_sheet", "Total Liabilities", [(_PERIOD, "25,000.00", 25000.0)]),
        ],
    }


def _payload(cash_flow_rows: List[Dict], year: str = _YEAR) -> Dict[str, Any]:
    tables = {
        "profit_and_loss": [], "balance_sheet": [], "cash_flow": [],
        "share_capital": [], "reserves": [], "borrowings": [], "fixed_assets": [],
        "revenue": [], "tax": [], "eps": [], "dividend": [], "corporate_actions": [],
        "shareholding_pattern": [], "investment_schedule": [], "lease_note": [],
        "segment_reporting": [], "statement_of_changes_in_equity": [],
        "management_discussion_financial_summary": [],
    }
    for table_type, rows in _required_sections().items():
        tables[table_type] = rows
    tables["cash_flow"] = cash_flow_rows
    return {
        "company": "test_co",
        "year": year,
        "generated_at": "2026-09-15T00:00:00Z",
        "source_documents": ["annual_report.pdf"],
        "tables": tables,
        "rejections": [],
        "warnings": [],
        "limitations": [],
    }


def _run(cash_flow_rows: List[Dict], tmp_path: Path) -> Dict[str, Any]:
    raw_path = tmp_path / "raw_financial_tables.json"
    raw_path.write_text(json.dumps(_payload(cash_flow_rows)), encoding="utf-8")
    return normalize_financial_tables(company="test_co", year=_YEAR, raw_tables_path=raw_path)


def _cfo(result: Dict[str, Any]) -> Optional[float]:
    return (result.get("cash_flow") or {}).get("cfo", {}).get("value_crore")


# ---------------------------------------------------------------------------
# T01 — PBT row MUST NOT become CFO
# ---------------------------------------------------------------------------

def test_indirect_pbt_row_not_classified_as_cfo(tmp_path):
    """ENG-139 T01: The opening PBT row in an indirect-method OCF section is
    never selected as the canonical CFO."""
    rows = [
        _row("cash_flow", "A. Cash flow from operating activities Profit/(loss) before tax",
             [(_PERIOD, "15,118.88", 15118.88)]),
        _row("cash_flow", "Net cash generated from / (used in) operating activities (A)",
             [(_PERIOD, "12,419.18", 12419.18)]),
    ]
    result = _run(rows, tmp_path)
    cfo = _cfo(result)
    assert cfo is not None, "CFO should be resolved"
    assert abs(cfo - 12419.18) < 0.01, (
        f"CFO must be 12419.18 (net OCF), not 15118.88 (PBT). Got {cfo}"
    )


# ---------------------------------------------------------------------------
# T02 — Net operating cash-flow row IS selected as CFO
# ---------------------------------------------------------------------------

def test_net_operating_cash_flow_row_is_cfo(tmp_path):
    """ENG-139 T02: 'Net cash generated from operating activities (A)' row is
    selected as the canonical CFO."""
    rows = [
        _row("cash_flow", "Net cash generated from operating activities (A)",
             [(_PERIOD, "12,419.18", 12419.18)]),
    ]
    result = _run(rows, tmp_path)
    cfo = _cfo(result)
    assert cfo is not None
    assert abs(cfo - 12419.18) < 0.01


# ---------------------------------------------------------------------------
# T03 — "before tax" qualifier in a cash-flow label blocks CFO classification
# ---------------------------------------------------------------------------

def test_cash_flow_before_tax_label_not_cfo(tmp_path):
    """ENG-139 T03: Any row whose label contains 'before tax' is rejected as
    CFO candidate, even if it appears in the cash_flow table."""
    rows = [
        _row("cash_flow", "Cash generated before tax",
             [(_PERIOD, "16,000.00", 16000.00)]),
        _row("cash_flow", "Net cash from operating activities",
             [(_PERIOD, "12,419.18", 12419.18)]),
    ]
    result = _run(rows, tmp_path)
    cfo = _cfo(result)
    assert cfo is not None
    assert abs(cfo - 12419.18) < 0.01, (
        f"'Cash generated before tax' must not outrank net OCF. Got {cfo}"
    )


# ---------------------------------------------------------------------------
# T04 — "taxes paid" row does not become CFO
# ---------------------------------------------------------------------------

def test_taxes_paid_not_cfo(tmp_path):
    """ENG-139 T04: An 'Income tax paid' adjustment row is not selected as CFO."""
    rows = [
        _row("cash_flow", "Income taxes paid",
             [(_PERIOD, "-2,500.00", -2500.00)]),
        _row("cash_flow", "Net cash generated from / (used in) operating activities (A)",
             [(_PERIOD, "12,419.18", 12419.18)]),
    ]
    result = _run(rows, tmp_path)
    cfo = _cfo(result)
    assert cfo is not None
    assert abs(cfo - 12419.18) < 0.01


# ---------------------------------------------------------------------------
# T05 — Intermediate operating subtotal does not outrank final net row
# ---------------------------------------------------------------------------

def test_operating_subtotal_does_not_outrank_net_ocf(tmp_path):
    """ENG-139 T05: An 'Operating profit before working capital changes'
    subtotal has lower priority than the final net operating cash flow line."""
    rows = [
        _row("cash_flow", "Operating profit before working capital changes",
             [(_PERIOD, "16,000.91", 16000.91)]),
        _row("cash_flow", "Net cash generated from operating activities (A)",
             [(_PERIOD, "12,419.18", 12419.18)]),
    ]
    result = _run(rows, tmp_path)
    cfo = _cfo(result)
    assert cfo is not None
    assert abs(cfo - 12419.18) < 0.01, (
        f"Intermediate subtotal must not win over net OCF. Got {cfo}"
    )


# ---------------------------------------------------------------------------
# T06 — Consolidated-only rows used; standalone ignored when consolidated exists
# ---------------------------------------------------------------------------

def test_consolidated_basis_preferred_over_standalone(tmp_path):
    """ENG-139 T06: When both consolidated and standalone CFO rows exist the
    normalizer picks consolidated."""
    rows = [
        _row("cash_flow", "Net cash from operating activities",
             [(_PERIOD, "5,000.00", 5000.00)], basis="standalone"),
        _row("cash_flow", "Net cash from operating activities",
             [(_PERIOD, "12,419.18", 12419.18)], basis="consolidated"),
    ]
    result = _run(rows, tmp_path)
    cfo = _cfo(result)
    assert cfo is not None
    assert abs(cfo - 12419.18) < 0.01


# ---------------------------------------------------------------------------
# T07 — Prior-year comparative column is not used as current-year CFO
# ---------------------------------------------------------------------------

def test_prior_year_column_not_used_as_current_cfo(tmp_path):
    """ENG-139 T07: When a row has both FY26 and FY25 value columns, only
    the FY26 column is stored as CFO for the fy26 normalization pass."""
    rows = [
        _row("cash_flow", "Net cash generated from operating activities (A)",
             [
                 (_PERIOD, "12,419.18", 12419.18),
                 (_PRIOR_PERIOD, "14,072.09", 14072.09),
             ]),
    ]
    result = _run(rows, tmp_path)
    cfo = _cfo(result)
    assert cfo is not None
    assert abs(cfo - 12419.18) < 0.01, (
        f"Current year value must be FY26 (12419.18), not FY25 (14072.09). Got {cfo}"
    )


# ---------------------------------------------------------------------------
# T08 — Unit round-tripping: crore values preserved as crore
# ---------------------------------------------------------------------------

def test_cfo_unit_preserved_in_crore(tmp_path):
    """ENG-139 T08: A value already in crore is stored without rescaling."""
    rows = [
        _row("cash_flow", "Net cash from operating activities",
             [(_PERIOD, "12,419.18", 12419.18)]),
    ]
    result = _run(rows, tmp_path)
    cfo = _cfo(result)
    assert cfo is not None
    assert 12000 < cfo < 13000, f"CFO crore value out of expected range: {cfo}"


# ---------------------------------------------------------------------------
# T09 — Million-unit PBT row still not selected as CFO
# ---------------------------------------------------------------------------

def test_million_unit_pbt_row_still_not_cfo(tmp_path):
    """ENG-139 T09: A PBT row expressed in millions (pre-converted to crore)
    must still NOT be selected as CFO."""
    # value_crore is pre-computed by extractor (151,188.8 million = 15118.88 crore)
    rows = [
        _row("cash_flow",
             "A. Cash flow from operating activities Profit/(loss) before tax",
             [(_PERIOD, "151,188.8", 15118.88, "million")]),
        _row("cash_flow",
             "Net cash generated from / (used in) operating activities (A)",
             [(_PERIOD, "124,191.8", 12419.18, "million")]),
    ]
    result = _run(rows, tmp_path)
    cfo = _cfo(result)
    assert cfo is not None
    assert abs(cfo - 12419.18) < 0.01, (
        f"Million-unit PBT must not displace net OCF. Got {cfo}"
    )


# ---------------------------------------------------------------------------
# T10 — Duplicate candidates: highest-specificity row wins
# ---------------------------------------------------------------------------

def test_duplicate_candidates_resolved_by_specificity(tmp_path):
    """ENG-139 T10: When two OCF-matching rows compete, the one with
    'net cash generated from operating activities' wins by specificity bonus."""
    rows = [
        _row("cash_flow", "Cash from operations",
             [(_PERIOD, "11,000.00", 11000.00)]),
        _row("cash_flow", "Net cash generated from operating activities (A)",
             [(_PERIOD, "12,419.18", 12419.18)]),
    ]
    result = _run(rows, tmp_path)
    cfo = _cfo(result)
    assert cfo is not None
    assert abs(cfo - 12419.18) < 0.01


# ---------------------------------------------------------------------------
# T11 — Owner Earnings uses the canonical resolved CFO, not PBT
# ---------------------------------------------------------------------------

def test_owner_earnings_uses_canonical_cfo():
    """ENG-139 T11: The Owner Earnings bridge reads the resolved CFO from
    the fact_registry/normalized_fundamentals pipeline, not the raw PBT value."""
    from knowledge.financials.investor_modules import build_investor_financial_modules

    company_root = Path(__file__).resolve().parents[2] / "companies" / "sun_pharma"
    if not company_root.exists():
        pytest.skip("sun_pharma company data not available")

    modules = build_investor_financial_modules(company="sun_pharma", company_root=company_root)
    bridge = modules.get("owner_earnings_bridge.json") or {}
    fy26_entry = next(
        (b for b in bridge.get("bridges", []) if b.get("fiscal_year") == "fy26"),
        None,
    )
    assert fy26_entry is not None, "FY26 entry missing from owner_earnings_bridge"
    cfo = fy26_entry.get("cfo")
    assert cfo is not None
    assert abs(cfo - 12419.18) < 0.01, (
        f"Owner Earnings bridge must use correct CFO (12419.18), got {cfo}"
    )
    oe = fy26_entry.get("owner_earnings_estimate")
    assert oe is not None
    assert abs(oe - 8809.81) < 1.0, (
        f"Owner Earnings must be ~8809.81 (CFO - capex), got {oe}"
    )


# ---------------------------------------------------------------------------
# T12 — Wrong CFO cannot propagate: PBT blocked in normalized_fundamentals
# ---------------------------------------------------------------------------

def test_pbt_sourced_cfo_blocked_before_downstream(tmp_path):
    """ENG-139 T12: Normalizer rejects PBT row as CFO so the wrong value never
    enters normalized_fundamentals.json and cannot propagate downstream."""
    rows = [
        _row("cash_flow",
             "A. Cash flow from operating activities Profit/(loss) before tax",
             [(_PERIOD, "15,118.88", 15118.88)]),
        _row("cash_flow",
             "Net cash generated from / (used in) operating activities (A)",
             [(_PERIOD, "12,419.18", 12419.18)]),
    ]
    raw_path = tmp_path / "raw_financial_tables.json"
    raw_path.write_text(json.dumps(_payload(rows)), encoding="utf-8")
    out_path = tmp_path / "normalized_fundamentals.json"
    write_normalized_fundamentals(
        company="test_co",
        year=_YEAR,
        raw_tables_path=raw_path,
        output_path=out_path,
        output_root=tmp_path,
    )
    normalized = json.loads(out_path.read_text())
    cfo_val = (normalized.get("cash_flow") or {}).get("cfo", {}).get("value_crore")
    assert cfo_val is not None, "CFO must be present in normalized output"
    assert abs(cfo_val - 12419.18) < 0.01, (
        f"PBT (15118.88) must not propagate to normalized_fundamentals. Got {cfo_val}"
    )
