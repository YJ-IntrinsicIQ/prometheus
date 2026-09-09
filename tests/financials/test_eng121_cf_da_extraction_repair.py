"""
ENG-121: Sun Pharma Cash Flow D&A Extraction Repair — focused tests.

Nine test cases (A-I) verifying:
  A  discovery.py CF continuation patterns include indirect-method operating section
  B  FY26 D&A chunk text passes the new continuation check
  C  FY23 clean_chunks.json contains the D&A row after re-chunking
  D  FY23 raw_financial_tables has a CF D&A row with is_primary_statement=True
  E  FY26 raw_financial_tables has a CF D&A row with is_primary_statement=True
  F  FY23 normalized_fundamentals: depreciation=2529.43 Cr, source=primary_cash_flow_statement
  G  FY26 normalized_fundamentals: depreciation=2937.85 Cr, source=primary_cash_flow_statement
  H  Cross-company regression: Tanla D&A unchanged
  I  Cross-company regression: Data Patterns D&A unchanged
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUN = ROOT / "companies" / "sun_pharma"
DP = ROOT / "companies" / "datapatterns"
TANLA = ROOT / "companies" / "tanla"


# ---------------------------------------------------------------------------
# A: discovery.py CF continuation patterns
# ---------------------------------------------------------------------------

def test_A_cf_continuation_includes_indirect_method_patterns():
    from knowledge.financials.discovery import PRIMARY_CONTINUATION_ROW_PATTERNS

    patterns = PRIMARY_CONTINUATION_ROW_PATTERNS["primary_cash_flow_statement"]
    required = {
        "profit before tax",
        "adjustments for",
        "depreciation and amortisation",
        "operating profit before working capital changes",
        "movements in working capital",
    }
    missing = required - set(patterns)
    assert not missing, f"CF continuation patterns missing: {missing}"


# ---------------------------------------------------------------------------
# B: FY26 D&A chunk text passes continuation check
# ---------------------------------------------------------------------------

def test_B_fy26_da_chunk_passes_continuation_check():
    from knowledge.financials.discovery import (
        PRIMARY_CONTINUATION_ROW_PATTERNS,
        _continuation_row_signals,
        _is_primary_continuation_candidate,
    )

    # Chunk 589 text (page 246, consolidated CF): contains profit before tax + D&A
    chunk_text = (
        "Profit/(loss) before tax 151,188.8 137,521.3 "
        "Adjustments for: Depreciation and amortisation expense 29,378.5 25,753.9 "
        "Finance costs 4,023.4 3,012.1 Interest income (8,103.6) (6,218.5)"
    )
    signals = list(_continuation_row_signals("primary_cash_flow_statement", chunk_text))
    assert len(signals) >= 2, f"Expected ≥2 signals, got {len(signals)}: {signals}"
    assert _is_primary_continuation_candidate("primary_cash_flow_statement", chunk_text), (
        "FY26 D&A chunk should pass continuation check after ENG-121 repair"
    )


# ---------------------------------------------------------------------------
# C: FY23 clean_chunks.json contains D&A row
# ---------------------------------------------------------------------------

def test_C_fy23_chunks_contain_da_row():
    chunk_path = SUN / "fy23" / "extracted" / "clean_chunks.json"
    if not chunk_path.exists():
        pytest.skip("FY23 clean_chunks.json not found")

    with open(chunk_path) as f:
        data = json.load(f)
    chunks = data["chunks"]

    da_chunks = [
        c for c in chunks
        if "depreciation and amortis" in c.get("text", "").lower()
        and "25,294" in c.get("text", "")
    ]
    assert da_chunks, (
        "FY23 clean_chunks.json must contain 'Depreciation and amortisation expense 25,294.3'"
        " after re-chunking with current smart_chunker.py"
    )


# ---------------------------------------------------------------------------
# D: FY23 raw_financial_tables — CF D&A row with is_primary_statement=True
# ---------------------------------------------------------------------------

def test_D_fy23_raw_tables_has_primary_cf_da_row():
    raw_path = SUN / "fy23" / "financials" / "raw_financial_tables.json"
    if not raw_path.exists():
        pytest.skip("FY23 raw_financial_tables.json not found")

    with open(raw_path) as f:
        raw = json.load(f)

    cf_rows = raw.get("tables", {}).get("cash_flow", [])
    da_rows = [
        r for r in cf_rows
        if "depreciation" in r.get("line_item_raw", "").lower()
        and r.get("is_primary_statement") is True
    ]
    assert da_rows, "FY23 raw CF tables must contain a D&A row with is_primary_statement=True"

    # Verify value
    values = da_rows[0].get("values", [])
    fy23_val = next(
        (v["value_crore"] for v in values if "2023" in v.get("period", "")), None
    )
    assert fy23_val is not None, "FY23 D&A row missing March 2023 value"
    assert abs(fy23_val - 2529.43) < 1.0, f"FY23 CF D&A expected ~2529.43 Cr, got {fy23_val}"


# ---------------------------------------------------------------------------
# E: FY26 raw_financial_tables — CF D&A row with is_primary_statement=True
# ---------------------------------------------------------------------------

def test_E_fy26_raw_tables_has_primary_cf_da_row():
    raw_path = SUN / "fy26" / "financials" / "raw_financial_tables.json"
    if not raw_path.exists():
        pytest.skip("FY26 raw_financial_tables.json not found")

    with open(raw_path) as f:
        raw = json.load(f)

    cf_rows = raw.get("tables", {}).get("cash_flow", [])
    da_rows = [
        r for r in cf_rows
        if "depreciation" in r.get("line_item_raw", "").lower()
        and r.get("is_primary_statement") is True
    ]
    assert da_rows, "FY26 raw CF tables must contain a D&A row with is_primary_statement=True"

    values = da_rows[0].get("values", [])
    fy26_val = next(
        (v["value_crore"] for v in values if "2026" in v.get("period", "")), None
    )
    assert fy26_val is not None, "FY26 D&A row missing March 2026 value"
    assert abs(fy26_val - 2937.85) < 1.0, f"FY26 CF D&A expected ~2937.85 Cr, got {fy26_val}"


# ---------------------------------------------------------------------------
# F: FY23 normalized_fundamentals — depreciation from primary CF statement
# ---------------------------------------------------------------------------

def test_F_fy23_normalized_da_from_primary_cf():
    norm_path = SUN / "fy23" / "financials" / "normalized_fundamentals.json"
    if not norm_path.exists():
        pytest.skip("FY23 normalized_fundamentals.json not found")

    with open(norm_path) as f:
        norm = json.load(f)

    da = norm.get("profit_and_loss", {}).get("depreciation", {})
    assert da, "FY23 normalized_fundamentals must contain depreciation"
    assert da["source_section_type"] == "primary_cash_flow_statement", (
        f"FY23 D&A must come from primary_cash_flow_statement, got {da.get('source_section_type')}"
    )
    assert da["is_primary_statement"] is True, "FY23 D&A must have is_primary_statement=True"
    assert abs(da["value_crore"] - 2529.43) < 1.0, (
        f"FY23 D&A expected 2529.43 Cr, got {da['value_crore']}"
    )


# ---------------------------------------------------------------------------
# G: FY26 normalized_fundamentals — depreciation from primary CF statement
# ---------------------------------------------------------------------------

def test_G_fy26_normalized_da_from_primary_cf():
    norm_path = SUN / "fy26" / "financials" / "normalized_fundamentals.json"
    if not norm_path.exists():
        pytest.skip("FY26 normalized_fundamentals.json not found")

    with open(norm_path) as f:
        norm = json.load(f)

    da = norm.get("profit_and_loss", {}).get("depreciation", {})
    assert da, "FY26 normalized_fundamentals must contain depreciation"
    assert da["source_section_type"] == "primary_cash_flow_statement", (
        f"FY26 D&A must come from primary_cash_flow_statement, got {da.get('source_section_type')}"
    )
    assert da["is_primary_statement"] is True, "FY26 D&A must have is_primary_statement=True"
    assert abs(da["value_crore"] - 2937.85) < 1.0, (
        f"FY26 D&A expected 2937.85 Cr, got {da['value_crore']}"
    )


# ---------------------------------------------------------------------------
# H: Cross-company regression — Tanla D&A unchanged
# ---------------------------------------------------------------------------

TANLA_DA_BASELINE = {
    "fy22": 40.8563,
    "fy23": 46.1713,
    "fy24": 85.2685,
    "fy25": 97.7743,
    "fy26": 122.205,
}


@pytest.mark.parametrize("year,expected", TANLA_DA_BASELINE.items())
def test_H_tanla_da_regression(year, expected):
    norm_path = TANLA / year / "financials" / "normalized_fundamentals.json"
    if not norm_path.exists():
        pytest.skip(f"Tanla {year} normalized_fundamentals.json not found")

    with open(norm_path) as f:
        norm = json.load(f)

    da = norm.get("profit_and_loss", {}).get("depreciation", {})
    assert da, f"Tanla {year} missing depreciation metric"
    assert abs(da["value_crore"] - expected) < 0.5, (
        f"Tanla {year} D&A regression: expected ~{expected} Cr, got {da['value_crore']}"
    )


# ---------------------------------------------------------------------------
# I: Cross-company regression — Data Patterns D&A unchanged
# ---------------------------------------------------------------------------

DP_DA_BASELINE = {
    "fy23": 8.45,
    "fy24": 16.13,
    "fy25": 13.92,
}


@pytest.mark.parametrize("year,expected", DP_DA_BASELINE.items())
def test_I_datapatterns_da_regression(year, expected):
    norm_path = DP / year / "financials" / "normalized_fundamentals.json"
    if not norm_path.exists():
        pytest.skip(f"Data Patterns {year} normalized_fundamentals.json not found")

    with open(norm_path) as f:
        norm = json.load(f)

    da = norm.get("profit_and_loss", {}).get("depreciation", {})
    assert da, f"Data Patterns {year} missing depreciation metric"
    assert abs(da["value_crore"] - expected) < 0.5, (
        f"Data Patterns {year} D&A regression: expected ~{expected} Cr, got {da['value_crore']}"
    )
