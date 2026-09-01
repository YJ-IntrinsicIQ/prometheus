import json
import shutil
from pathlib import Path

import pytest

from knowledge.financials.ratio_calculator import calculate_financial_ratios
from knowledge.financials.reconciler import build_financial_reconciliation_report
from knowledge.financials.normalizer import _face_value_from_excerpt, _select_value, normalize_financial_tables, write_normalized_fundamentals

ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _row(
    table_type,
    line_item_raw,
    values,
    *,
    basis="unknown",
    page=1,
    confidence="medium",
    unit_hint="crore",
    currency_hint="INR",
):
    normalized_values = []
    for item in values:
        if len(item) == 3:
            period, value_raw, value_crore = item
            value_type_override = None
            unit_hint_override = None
        elif len(item) == 4:
            period, value_raw, value_crore, value_type_override = item
            unit_hint_override = None
        elif len(item) == 5:
            period, value_raw, value_crore, value_type_override, unit_hint_override = item
        else:
            raise ValueError(f"Unsupported value tuple length: {len(item)}")
        raw_number = None
        cleaned = str(value_raw).strip()
        if cleaned not in {"", "None"}:
            normalized = cleaned.replace(",", "").strip("()[]")
            if normalized.startswith("-"):
                normalized = normalized[1:]
            normalized = normalized.rstrip("%")
            try:
                raw_number = float(normalized)
                if cleaned.startswith("(") or cleaned.startswith("[") or cleaned.startswith("-"):
                    raw_number = -raw_number
            except ValueError:
                raw_number = None
        normalized_values.append(
            {
                "period": period,
                "value_raw": value_raw,
                "unit_hint": unit_hint_override or unit_hint,
                "currency_hint": currency_hint,
                "value_crore": value_crore,
                "value_type": value_type_override or ("per_share" if table_type == "eps" else "share_count" if unit_hint == "shares" else "percentage" if unit_hint == "%" else "monetary"),
                "raw_number": raw_number,
            }
        )
    return {
        "statement_type": table_type,
        "table_type": table_type,
        "basis": basis,
        "line_item_raw": line_item_raw,
        "values": normalized_values,
        "source_artifact": "clean_chunks.json",
        "page": page,
        "chunk_id": f"CHK-{page:03d}",
        "confidence": confidence,
        "source_section_type": (
            "primary_profit_and_loss_statement" if table_type == "profit_and_loss"
            else "primary_balance_sheet_statement" if table_type == "balance_sheet"
            else "primary_cash_flow_statement" if table_type == "cash_flow"
            else table_type
        ) if table_type != "management_discussion_financial_summary" else "management_discussion_financial_summary",
        "table_confidence": confidence,
        "table_rejection_risk": [],
        "is_primary_statement": table_type in {"profit_and_loss", "balance_sheet", "cash_flow"},
        "warnings": [],
    }


def _raw_payload(sections=None):
    tables = {
        "profit_and_loss": [],
        "balance_sheet": [],
        "cash_flow": [],
        "share_capital": [],
        "reserves": [],
        "borrowings": [],
        "fixed_assets": [],
        "revenue": [],
        "tax": [],
        "eps": [],
        "dividend": [],
        "corporate_actions": [],
        "shareholding_pattern": [],
    }
    if sections:
        for key, value in sections.items():
            tables[key] = value
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-16T00:00:00Z",
        "source_documents": ["clean_chunks.json"],
        "tables": tables,
        "warnings": [],
        "limitations": [],
    }


def _minimum_required_sections():
    return {
        "profit_and_loss": [
            _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)]),
            _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)]),
        ],
        "balance_sheet": [
            _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)]),
            _row("balance_sheet", "Total Equity", [("March 31, 2025", "600.00", 600.0)]),
            _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)]),
        ],
    }


def test_revenue_and_pat_mapping(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"].append(_row("profit_and_loss", "Other income", [("March 31, 2025", "25.00", 25.0)]))
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["revenue"]["value_crore"] == 500.0
    assert payload["profit_and_loss"]["pat"]["value_crore"] == 120.0
    assert payload["profit_and_loss"]["other_income"]["value_crore"] == 25.0


def test_balance_sheet_revenue_row_normalizes_to_profit_and_loss_revenue(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)]),
    ]
    sections["balance_sheet"].append(
        _row("balance_sheet", "Revenue", [("March 31, 2025", "500.00", 500.0)])
    )
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["revenue"]["value_crore"] == 500.0
    assert payload["profit_and_loss"]["revenue"]["source_section_type"] == "primary_balance_sheet_statement"
    assert payload["profit_and_loss"]["revenue"]["source_line_item"] == "Revenue"


def test_balance_sheet_capital_total_row_normalizes_to_net_worth(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)]),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)]),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "23604.46", 23604.4642)]),
        _row("balance_sheet", "Details 1. Paid up Capital (`)", [("PERIOD_COLUMN_UNRESOLVED", "19,28,31,42,050", 1928.314205)]),
        _row("balance_sheet", "Paid up Capital", [("March 31, 2025", "1728314205", 172831.4205)]),
        _row("balance_sheet", "RESERVES AND SURPLUS I. Statutory Reserves Closing balance", [("March 31, 2025", "205131", 20.5131)]),
        _row("balance_sheet", "TOTAL (I + II + III+IV+V)", [("March 31, 2025", "8321239", 832.1239)]),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "22772.34", 22772.3403)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["balance_sheet"]["equity_share_capital"]["value_crore"] == 1928.314205
    assert payload["balance_sheet"]["equity_share_capital"]["source_line_item"] == "Details 1. Paid up Capital (`)"
    assert payload["balance_sheet"]["reserves"]["value_crore"] == 832.1239
    assert payload["balance_sheet"]["reserves"]["source_line_item"] == "TOTAL (I + II + III+IV+V)"
    assert payload["balance_sheet"]["net_worth"]["value_crore"] == 2760.4381
    assert payload["balance_sheet"]["net_worth"]["formula"] == "equity_share_capital + reserves"
    assert payload["balance_sheet"]["total_liabilities"]["value_crore"] == 22772.3403


def test_total_equity_and_liabilities_is_not_promoted_to_net_worth(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)]),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)]),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "3009.00", 3009.0)]),
        _row("balance_sheet", "Total Equity and Liabilities", [("March 31, 2025", "3009.00", 3009.0)]),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "1942.00", 1942.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["balance_sheet"]["net_worth"]["source_line_item"] == "Total Equity"
    assert payload["balance_sheet"]["net_worth"]["value_crore"] == 1942.0
    assert payload["balance_sheet"]["total_liabilities"]["derived"] is True
    assert payload["balance_sheet"]["total_liabilities"]["value_crore"] == 1067.0


def test_real_ujjivan_fy23_balance_sheet_prefers_true_total_assets_candidate(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    real_path = ROOT / "companies" / "ujjivan" / "fy23" / "financials" / "raw_financial_tables.json"
    real_discovery_path = ROOT / "companies" / "ujjivan" / "fy23" / "financials" / "financial_discovery.json"
    shutil.copyfile(real_path, path)
    shutil.copyfile(real_discovery_path, tmp_path / "financial_discovery.json")

    payload = normalize_financial_tables(company="ujjivan", year="fy23", raw_tables_path=path)

    assert payload["balance_sheet"]["total_assets"]["source_page"] == 316
    assert payload["balance_sheet"]["total_assets"]["value_crore"] == 23604.4642
    assert payload["balance_sheet"]["net_worth"]["derived"] is True
    assert payload["balance_sheet"]["net_worth"]["source_line_item"] == "derived:net_worth"
    assert payload["balance_sheet"]["net_worth"]["value_crore"] == 3957.8865
    assert payload["balance_sheet"]["net_worth"]["source_page"] == 273
    assert payload["balance_sheet"]["total_liabilities"]["derived"] is True
    assert payload["balance_sheet"]["total_liabilities"]["formula"] == "total_assets - net_worth"
    assert payload["balance_sheet"]["total_liabilities"]["value_crore"] == 19646.5777


def test_real_ujjivan_fy22_balance_sheet_net_worth_scales_from_share_count(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    real_path = ROOT / "companies" / "ujjivan" / "fy22" / "financials" / "raw_financial_tables.json"
    real_discovery_path = ROOT / "companies" / "ujjivan" / "fy22" / "financials" / "financial_discovery.json"
    shutil.copyfile(real_path, path)
    shutil.copyfile(real_discovery_path, tmp_path / "financial_discovery.json")

    payload = normalize_financial_tables(company="ujjivan", year="fy22", raw_tables_path=path)

    assert payload["balance_sheet"]["equity_share_capital"]["value_crore"] == 1928.314205
    assert payload["balance_sheet"]["reserves"]["value_crore"] == 832.1239
    assert payload["balance_sheet"]["net_worth"]["derived"] is True
    assert payload["balance_sheet"]["net_worth"]["value_crore"] == 2760.4381
    assert payload["balance_sheet"]["total_liabilities"]["derived"] is True
    assert payload["balance_sheet"]["total_liabilities"]["value_crore"] == 20844.0261


def test_balance_sheet_pat_label_normalizes_to_pat(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)]),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)]),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "600.00", 600.0)]),
        _row("balance_sheet", "Total profit after taxes", [("March 31, 2025", "8.30", 8.3)]),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["pat"]["value_crore"] == 8.3
    assert payload["profit_and_loss"]["pat"]["source_section_type"] == "primary_balance_sheet_statement"
    assert payload["profit_and_loss"]["pat"]["statement_type"] == "balance_sheet"


def test_balance_sheet_net_profit_row_normalizes_to_pat(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)]),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)]),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "600.00", 600.0)]),
        _row("balance_sheet", "Net Profit (5-6-8-9)", [("March 31, 2025", "8.30", 8.3)]),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["pat"]["value_crore"] == 8.3
    assert payload["profit_and_loss"]["pat"]["source_section_type"] == "primary_balance_sheet_statement"
    assert payload["profit_and_loss"]["pat"]["source_line_item"] == "Net Profit (5-6-8-9)"


def test_generic_net_profit_row_does_not_map_to_pat(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)]),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)]),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)]),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "600.00", 600.0)]),
        _row("balance_sheet", "Mar-20 Mar-21 Mar-22 Net Profit", [("March 31, 2025", "8.30", 8.3)]),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["pat"]["value_crore"] == 120.0
    assert payload["profit_and_loss"]["pat"]["source_line_item"] == "Profit for the year"


def test_balance_sheet_ratio_lookalike_does_not_map_to_pat(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)]),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)]),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "600.00", 600.0)]),
        _row("balance_sheet", "Total profit after taxes", [("March 31, 2025", "8.30", 8.3)]),
        _row("balance_sheet", "Net profit ratio Profit after Tax Revenue from Operations", [("March 31, 2025", "15.0", 15.0)]),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["pat"]["value_crore"] == 8.3
    assert payload["profit_and_loss"]["pat"]["source_line_item"] == "Total profit after taxes"


def test_debt_and_reserves_mapping(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["borrowings"] = [
        _row("borrowings", "Long term borrowings", [("March 31, 2025", "200.00", 200.0)]),
        _row("borrowings", "Short term borrowings", [("March 31, 2025", "50.00", 50.0)]),
    ]
    sections["reserves"] = [
        _row("reserves", "Other Equity", [("March 31, 2025", "350.00", 350.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    assert payload["balance_sheet"]["long_term_debt"]["value_crore"] == 200.0
    assert payload["balance_sheet"]["short_term_debt"]["value_crore"] == 50.0
    assert payload["balance_sheet"]["reserves"]["value_crore"] == 350.0


def test_numeric_date_period_labels_still_select_current_balance_sheet_values(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)], basis="consolidated"),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("31/03/2025", "1000.00", 1000.0), ("31/03/2024", "900.00", 900.0)]),
        _row("balance_sheet", "Total Equity", [("31/03/2025", "600.00", 600.0), ("31/03/2024", "550.00", 550.0)]),
        _row("balance_sheet", "Total Liabilities", [("31/03/2025", "400.00", 400.0), ("31/03/2024", "350.00", 350.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["balance_sheet"]["total_assets"]["value_crore"] == 1000.0
    assert payload["balance_sheet"]["total_assets"]["period"] == "31/03/2025"
    assert payload["balance_sheet"]["net_worth"]["value_crore"] == 600.0
    assert payload["balance_sheet"]["total_liabilities"]["value_crore"] == 400.0


def test_cash_flow_mapping(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["cash_flow"] = [
        _row("cash_flow", "Net cash generated from operating activities", [("March 31, 2025", "140.00", 140.0)]),
        _row("cash_flow", "Purchase of property, plant and equipment", [("March 31, 2025", "(45.00)", -45.0)]),
        _row("cash_flow", "Income taxes paid", [("March 31, 2025", "(20.00)", -20.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    assert payload["cash_flow"]["cfo"]["value_crore"] == 140.0
    assert payload["cash_flow"]["capex"]["value_crore"] == -45.0
    assert payload["cash_flow"]["capex"]["capex_abs_crore"] == 45.0
    assert payload["cash_flow"]["capex"]["sign_convention"] == "cash_flow_signed"
    assert payload["cash_flow"]["tax_paid"]["value_crore"] == -20.0
    assert payload["cash_flow"]["fcf"]["value_crore"] == 95.0
    assert payload["cash_flow"]["fcf"]["derived"] is True
    assert payload["cash_flow"]["fcf"]["inputs_used"]["capex_sign_convention"] == "cash_flow_signed"


def test_wrapped_cash_capex_row_maps_to_capex_and_fcf(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = {
        "profit_and_loss": [
            _row("profit_and_loss", "Revenue from operations", [("March 31, 2023", "500.00", 500.0)], basis="consolidated"),
            _row("profit_and_loss", "Profit for the year", [("March 31, 2023", "120.00", 120.0)], basis="consolidated"),
        ],
        "balance_sheet": [
            _row("balance_sheet", "Total Assets", [("March 31, 2023", "1000.00", 1000.0)], basis="consolidated"),
            _row("balance_sheet", "Total Equity", [("March 31, 2023", "600.00", 600.0)], basis="consolidated"),
            _row("balance_sheet", "Total Liabilities", [("March 31, 2023", "400.00", 400.0)], basis="consolidated"),
        ],
    }
    sections["cash_flow"] = [
        _row("cash_flow", "Net cash generated from operating activities (A)", [("March 31, 2023", "49,593.3", 4959.33)], basis="consolidated", unit_hint="million"),
        _row(
            "cash_flow",
            "B. Cash flow from investing activities Payments for purchase of property, plant and equipment "
            "(including capital work-in- progress, other intangible assets and intangible assets under development)",
            [("March 31, 2023", "(20,855.8)", -2085.58)],
            basis="consolidated",
            unit_hint="million",
        ),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy23", raw_tables_path=path)

    assert payload["cash_flow"]["capex"]["value_crore"] == -2085.58
    assert payload["cash_flow"]["capex"]["sign_convention"] == "cash_flow_signed"
    assert payload["cash_flow"]["fcf"]["value_crore"] == 2873.75
    assert payload["cash_flow"]["fcf"]["formula"] == "cfo + capex (cash-flow-signed capex) or cfo - capex (positive-outflow capex)"


def test_purchase_of_intangible_assets_maps_to_capex(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["cash_flow"] = [
        _row("cash_flow", "Net cash generated from operating activities", [("March 31, 2025", "90.00", 90.0)]),
        _row("cash_flow", "Purchase of intangible assets", [("March 31, 2025", "(41.18)", -41.18)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["cash_flow"]["capex"]["value_crore"] == -41.18
    assert payload["cash_flow"]["capex"]["sign_convention"] == "cash_flow_signed"
    assert payload["cash_flow"]["fcf"]["value_crore"] == 48.82


@pytest.mark.parametrize(
    "line_item_raw",
    [
        "Property, plant and equipment - closing balance",
        "Capital work in progress closing balance",
        "Investment in mutual funds",
        "Payment of lease liabilities",
        "Net cash used in investing activities",
    ],
)
def test_non_capex_rows_do_not_map_to_capex(tmp_path, line_item_raw):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["cash_flow"] = [
        _row("cash_flow", "Net cash generated from operating activities", [("March 31, 2025", "140.00", 140.0)]),
        _row("cash_flow", line_item_raw, [("March 31, 2025", "(45.00)", -45.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["cash_flow"]["capex"]["value_original"] == ""
    assert payload["cash_flow"]["capex"]["value_crore"] is None
    assert payload["cash_flow"]["fcf"]["value_crore"] is None
    assert "capex missing" in payload["warnings"]


def test_generic_cash_flow_heading_is_not_mapped_to_fcf(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["cash_flow"] = [
        _row("cash_flow", "Cash Flow Statement for the year ended March 31, 2025", [("March 31, 2025", "March 31, 2025", None, "monetary")]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["cash_flow"]["fcf"]["value_original"] == ""


def test_explicit_free_cash_flow_row_can_map(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["cash_flow"] = [
        _row("cash_flow", "Free Cash Flow", [("March 31, 2025", "70.00", 70.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["cash_flow"]["fcf"]["value_crore"] == 70.0
    assert payload["cash_flow"]["fcf"]["derived"] is False


def test_fcf_stays_missing_with_warning_when_capex_missing(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["cash_flow"] = [
        _row("cash_flow", "Net cash generated from operating activities", [("March 31, 2025", "140.00", 140.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["cash_flow"]["fcf"]["value_crore"] is None
    assert payload["cash_flow"]["fcf"]["value_original"] == ""
    assert "capex missing" in payload["warnings"]


def test_eps_and_share_data_mapping(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["eps"] = [
        _row("eps", "Basic earnings per share", [("March 31, 2025", "32.45", None)], unit_hint="inr"),
        _row("eps", "Diluted earnings per share", [("March 31, 2025", "31.80", None)], unit_hint="inr"),
        _row("eps", "Weighted average number of equity shares", [("March 31, 2025", "1000000", None)], unit_hint="shares", currency_hint=""),
    ]
    sections["share_capital"] = [
        _row("share_capital", "Nominal value of equity shares", [("March 31, 2025", "2.00", None)], unit_hint="inr"),
        _row("share_capital", "Book value per share", [("March 31, 2025", "120.00", None)], unit_hint="inr"),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    assert payload["profit_and_loss"]["eps_basic"]["value_original"] == "32.45"
    assert payload["profit_and_loss"]["eps_basic"]["value_type"] == "per_share"
    assert payload["profit_and_loss"]["eps_basic"]["source_value_type"] == "per_share"
    assert payload["profit_and_loss"]["eps_basic"]["value_per_share"] == 32.45
    assert payload["profit_and_loss"]["eps_basic"]["value_crore"] is None
    assert payload["profit_and_loss"]["eps_diluted"]["value_type"] == "per_share"
    assert payload["profit_and_loss"]["eps_diluted"]["value_per_share"] == 31.8
    assert payload["share_data"]["weighted_avg_shares"]["value_original"] == "1000000"
    assert payload["share_data"]["weighted_avg_shares"]["value_type"] == "share_count"
    assert payload["share_data"]["weighted_avg_shares"]["source_value_type"] == "share_count"
    assert payload["share_data"]["weighted_avg_shares"]["raw_number"] == 1000000.0
    assert payload["share_data"]["weighted_avg_shares"]["crore_shares"] == 0.1
    assert payload["share_data"]["weighted_avg_shares"]["value_crore"] is None
    assert payload["share_data"]["face_value"]["value_original"] == "2.00"
    assert payload["share_data"]["face_value"]["value_type"] == "per_share"
    assert payload["share_data"]["face_value"]["source_value_type"] == "per_share"
    assert payload["share_data"]["face_value"]["value_per_share"] == 2.0
    assert payload["share_data"]["face_value"]["value_crore"] is None
    assert payload["share_data"]["book_value_per_share"]["value_original"] == "120.00"


def test_eps_denominator_row_does_not_become_reported_eps(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)], basis="consolidated"),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)], basis="consolidated"),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "600.00", 600.0)], basis="consolidated"),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)], basis="consolidated"),
    ]
    sections["eps"] = [
        _row(
            "eps",
            "Weighted average number of shares used in computing basic earnings per share",
            [("March 31, 2025", "2,399,334,970", None, "per_share", "INR per share")],
            basis="consolidated",
            unit_hint="INR per share",
        ),
        _row(
            "eps",
            "Weighted average number of shares used in computing diluted earnings per share",
            [("March 31, 2025", "2,399,335,257", None, "per_share", "INR per share")],
            basis="consolidated",
            unit_hint="INR per share",
        ),
        _row(
            "eps",
            "Basic earnings per share (in `)",
            [("March 31, 2025", "15.7", None)],
            basis="consolidated",
            unit_hint="INR per share",
        ),
        _row(
            "eps",
            "Diluted earnings per share (in `)",
            [("March 31, 2025", "15.6", None)],
            basis="consolidated",
            unit_hint="INR per share",
        ),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["eps_basic"]["value_per_share"] == 15.7
    assert payload["profit_and_loss"]["eps_basic"]["source_line_item"] == "Basic earnings per share (in `)"
    assert payload["profit_and_loss"]["eps_diluted"]["value_per_share"] == 15.6
    assert payload["profit_and_loss"]["eps_diluted"]["source_line_item"] == "Diluted earnings per share (in `)"
    assert payload["share_data"]["weighted_avg_shares"]["value_shares"] == 2399334970.0
    assert payload["share_data"]["weighted_avg_shares"]["value_type"] == "share_count"
    assert payload["share_data"]["weighted_avg_shares"]["source_value_type"] == "share_count"
    assert payload["share_data"]["diluted_shares"]["value_shares"] == 2399335257.0
    assert payload["share_data"]["diluted_shares"]["value_type"] == "share_count"
    assert payload["share_data"]["diluted_shares"]["source_value_type"] == "share_count"


def test_combined_basic_and_diluted_share_denominator_maps_to_both_fields(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["eps"] = [
        _row(
            "eps",
            "Weighted average number of shares used in computing basic and diluted earnings per share",
            [("March 31, 2025", "2,399,334,970", None, "per_share", "INR per share")],
            unit_hint="INR per share",
        ),
        _row("eps", "Basic earnings per share", [("March 31, 2025", "15.7", None)], unit_hint="INR per share"),
        _row("eps", "Diluted earnings per share", [("March 31, 2025", "15.7", None)], unit_hint="INR per share"),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["eps_basic"]["value_per_share"] == 15.7
    assert payload["profit_and_loss"]["eps_diluted"]["value_per_share"] == 15.7
    assert payload["share_data"]["weighted_avg_shares"]["value_shares"] == 2399334970.0
    assert payload["share_data"]["diluted_shares"]["value_shares"] == 2399334970.0


def test_weighted_and_diluted_shares_only_map_from_eps_note_rows(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["share_capital"] = [
        _row("share_capital", "Weighted average number of equity shares", [("March 31, 2025", "1000000", None)], unit_hint="shares", currency_hint=""),
        _row("share_capital", "Diluted weighted average number of equity shares", [("March 31, 2025", "1100000", None)], unit_hint="shares", currency_hint=""),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["share_data"]["weighted_avg_shares"]["value_original"] == ""
    assert payload["share_data"]["diluted_shares"]["value_original"] == ""


def test_mutual_fund_units_do_not_map_to_share_counts(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["share_capital"] = [
        _row("share_capital", "Mutual fund units held", [("March 31, 2025", "1000000", None, "unit_count", "units")], unit_hint="units", currency_hint=""),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["share_data"]["shares_outstanding"]["value_original"] == ""
    assert payload["share_data"]["weighted_avg_shares"]["value_original"] == ""
    assert payload["share_data"]["diluted_shares"]["value_original"] == ""


def test_face_value_maps_from_equity_shares_rs_each_wording(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["share_capital"] = [
        _row("share_capital", "Equity shares of Rs.2 each", [("March 31, 2025", "2.00", None)], unit_hint="inr", currency_hint="INR"),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["share_data"]["face_value"]["value_per_share"] == 2.0


def test_face_value_maps_from_backtick_currency_marker(tmp_path, monkeypatch):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    excerpt = "Schedules forming part of the Balance Sheet (₹ in 000's) Equity shares of ` 10 each"
    monkeypatch.setattr(
        "knowledge.financials.normalizer._load_discovery_excerpt_index",
        lambda _: {"CHK-001": excerpt, "page:1": excerpt},
    )
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "404222163", 40422.2163)]),
        _row(
            "balance_sheet",
            "Issued, Subscribed and Called up Capital",
            [("March 31, 2025", "1958763276", 195876.3276)],
            page=1,
        ),
        _row("balance_sheet", "TOTAL (I + II + III+IV+V+VI)", [("March 31, 2025", "3609.74", 3609.7398)]),
    ]
    sections["balance_sheet"][1]["chunk_id"] = "CHK-001"
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert _face_value_from_excerpt(excerpt) == 10.0
    assert payload["balance_sheet"]["equity_share_capital"]["value_crore"] == 1958.7633
    assert payload["balance_sheet"]["net_worth"]["value_crore"] == 5568.5031
    assert payload["balance_sheet"]["total_liabilities"]["value_crore"] == 34853.7132


def test_face_value_does_not_map_from_fair_value_wording(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["share_capital"] = [
        _row("share_capital", "Fair value of investment", [("March 31, 2025", "2.00", None)], unit_hint="inr", currency_hint="INR"),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["share_data"]["face_value"]["value_original"] == ""


def test_shares_outstanding_populates_from_explicit_equity_share_count(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["share_capital"] = [
        _row("share_capital", "Issued subscribed and paid-up equity shares", [("March 31, 2025", "100000000", None)], unit_hint="shares", currency_hint=""),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    assert payload["share_data"]["shares_outstanding"]["value_original"] == "100000000"
    assert payload["share_data"]["shares_outstanding"]["value_type"] == "share_count"
    assert payload["share_data"]["shares_outstanding"]["raw_number"] == 100000000.0


def test_shares_outstanding_stays_missing_when_source_line_item_is_unrelated(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["share_capital"] = [
        _row("share_capital", "Amount payable to micro and small enterprises", [("March 31, 2025", "100000000", None)], unit_hint="shares", currency_hint=""),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    assert payload["share_data"]["shares_outstanding"]["value_original"] == ""
    assert payload["share_data"]["shares_outstanding"]["value_type"] == ""
    assert payload["share_data"]["shares_outstanding"]["raw_number"] is None


def test_opening_share_count_does_not_map_to_current_shares_outstanding(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["share_capital"] = [
        _row(
            "share_capital",
            "Number of shares outstanding at the beginning of the period",
            [("March 31, 2025", "1699790", None, "share_count", "shares")],
            unit_hint="shares",
            currency_hint="",
        ),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["share_data"]["shares_outstanding"]["value_original"] == ""


def test_percentage_value_does_not_populate_monetary_field(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"].append(
        _row(
            "profit_and_loss",
            "Profit before tax",
            [("March 31, 2025", "25.0%", None, "percentage", "%")],
            unit_hint="%",
        )
    )
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["pbt"]["value_original"] == ""


def test_income_tax_expense_maps_to_tax_not_total_income(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"].append(
        _row(
            "profit_and_loss",
            "VI. Income tax expense/(credit): Current tax",
            [("March 31, 2025", "(20.00)", -20.0)],
        )
    )
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["tax"]["value_crore"] == -20.0
    assert payload["profit_and_loss"]["tax"]["source_line_item"] == "VI. Income tax expense/(credit): Current tax"
    assert payload["profit_and_loss"]["total_income"]["source_line_item"] != "VI. Income tax expense/(credit): Current tax"


def test_total_tax_expense_is_preferred_over_current_tax_component(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"].extend(
        [
            _row(
                "profit_and_loss",
                "X. Tax expense: Current tax",
                [("March 31, 2025", "112.55", 112.55)],
            ),
            _row(
                "profit_and_loss",
                "Total tax Expense (X)",
                [("March 31, 2025", "(260.80)", -260.8)],
            ),
        ]
    )
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["tax"]["value_crore"] == -260.8
    assert payload["profit_and_loss"]["tax"]["source_line_item"] == "Total tax Expense (X)"


def test_pbt_prefers_profit_before_tax_over_working_capital_cash_flow_bridge(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["cash_flow"] = [
        _row(
            "cash_flow",
            "Operating Profit/(Loss) before Working Capital changes",
            [("March 31, 2023", "15,991,439", 1599.1439)],
            page=271,
        ),
        _row(
            "cash_flow",
            "Net Profit/(Loss) before taxation",
            [("March 31, 2023", "14,672,376", 1467.2376)],
            page=271,
        ),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="ujjivan", year="fy23", raw_tables_path=path)

    assert payload["profit_and_loss"]["pbt"]["value_crore"] == 1467.2376
    assert payload["profit_and_loss"]["pbt"]["source_line_item"] == "Net Profit/(Loss) before taxation"


def test_ujjivan_fy23_pat_and_tax_prefer_bridge_consistent_cash_flow_rows(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["cash_flow"] = [
        _row(
            "cash_flow",
            "Operating Profit/(Loss) before Working Capital changes",
            [("March 31, 2023", "15,991,439", 1599.1439)],
            page=271,
        ),
        _row(
            "cash_flow",
            "Net Profit/(Loss) before taxation",
            [("March 31, 2023", "14,672,376", 1467.2376)],
            page=271,
        ),
        _row(
            "cash_flow",
            "A. Cash Flow from Operating Activities Net Profit/(Loss) After taxation",
            [("March 31, 2023", "10,999,217", 1099.9217)],
            page=271,
        ),
        _row(
            "cash_flow",
            "Tax adjustment",
            [("March 31, 2023", "3,673,159", 367.3159)],
            page=271,
        ),
        _row(
            "cash_flow",
            "Direct Taxes paid (net of refunds)",
            [("March 31, 2023", "(2,803,717)", -280.3717)],
            page=271,
        ),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2023", "23604.46", 23604.4642)]),
        _row("balance_sheet", "Details 1. Paid up Capital (`)", [("PERIOD_COLUMN_UNRESOLVED", "19,28,31,42,050", 1928.314205)]),
        _row("balance_sheet", "TOTAL (I + II + III+IV+V)", [("March 31, 2023", "8321239", 832.1239)]),
        _row(
            "balance_sheet",
            "Tax Expenses (including deferred tax)",
            [("March 31, 2023", "(1,357,681)", -135.7681)],
            page=316,
        ),
        _row(
            "balance_sheet",
            "Net Profit (5-6-8-9)",
            [("March 31, 2023", "(4,145,904)", -414.5904)],
            page=316,
        ),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2023", "22772.34", 22772.3403)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="ujjivan", year="fy23", raw_tables_path=path)

    assert payload["profit_and_loss"]["pbt"]["value_crore"] == 1467.2376
    assert payload["profit_and_loss"]["pbt"]["source_line_item"] == "Net Profit/(Loss) before taxation"
    assert payload["profit_and_loss"]["tax"]["value_crore"] == 367.3159
    assert payload["profit_and_loss"]["tax"]["source_line_item"] == "Tax adjustment"
    assert payload["profit_and_loss"]["pat"]["value_crore"] == 1099.9217
    assert payload["profit_and_loss"]["pat"]["source_line_item"] == (
        "A. Cash Flow from Operating Activities Net Profit/(Loss) After taxation"
    )


def test_deferred_tax_component_does_not_populate_total_tax(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"].append(
        _row(
            "profit_and_loss",
            "Deferred Tax",
            [("March 31, 2025", "(0.88)", -0.88)],
        )
    )
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["tax"]["value_original"] == ""


def test_debt_free_company_uses_balance_sheet_equation_without_fabricating_debt(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)]),
        _row("balance_sheet", "Equity Share Capital", [("March 31, 2025", "100.00", 100.0)]),
        _row("balance_sheet", "Other Equity", [("March 31, 2025", "700.00", 700.0)]),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["balance_sheet"]["net_worth"]["value_crore"] == 800.0
    assert payload["balance_sheet"]["total_liabilities"]["value_crore"] == 200.0
    assert payload["balance_sheet"]["total_liabilities"]["derived"] is True
    assert payload["balance_sheet"]["total_liabilities"]["formula"] == "total_assets - net_worth"
    assert payload["balance_sheet"]["total_debt"]["value_original"] == ""


def test_authorised_equity_shares_do_not_map_to_shares_outstanding(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["share_capital"] = [
        _row(
            "share_capital",
            "Authorised Equity shares of Rs.2 each",
            [
                ("March 31, 2025", "78750000", None, "share_count", "shares"),
                ("March 31, 2025", "15.75", 15.75, "monetary", "crore"),
                ("March 31, 2024", "70000000", None, "share_count", "shares"),
                ("March 31, 2024", "14.00", 14.0, "monetary", "crore"),
            ],
            unit_hint="shares",
            currency_hint="",
        ),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    assert payload["share_data"]["shares_outstanding"]["value_original"] == ""
    assert all(
        item.get("value_shares") != 15.75 and item.get("raw_number") != 15.75
        for item in payload["share_data"]["shares_outstanding"].get("comparatives", [])
    )


def test_amount_columns_do_not_enter_share_count_comparatives(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["share_capital"] = [
        _row(
            "share_capital",
            "Issued, subscribed and paid-up equity shares of Rs.2 each",
            [
                ("March 31, 2025", "78750000", None, "share_count", "shares"),
                ("March 31, 2025", "15.75", 15.75, "monetary", "crore"),
                ("March 31, 2024", "70000000", None, "share_count", "shares"),
                ("March 31, 2024", "14.00", 14.0, "monetary", "crore"),
            ],
            unit_hint="shares",
            currency_hint="",
        ),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    shares = payload["share_data"]["shares_outstanding"]
    assert shares["value_original"] == "78750000"
    assert shares["raw_number"] == 78750000.0
    assert shares["comparatives"][0]["value_original"] == "70000000"
    assert shares["comparatives"][0]["raw_number"] == 70000000.0
    assert shares["comparatives"][0]["value_shares"] == 70000000.0
    assert shares["comparatives"][0]["value_crore"] is None


def test_corporate_action_and_shareholding_mapping(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["corporate_actions"] = [
        _row("corporate_actions", "Qualified Institutional Placement", [("March 31, 2025", "300.00", 300.0)]),
    ]
    sections["shareholding_pattern"] = [
        _row("shareholding_pattern", "Promoter holding", [("FY25", "54.2%", None)], unit_hint="%", currency_hint=""),
        _row("shareholding_pattern", "Public holding", [("FY25", "45.8%", None)], unit_hint="%", currency_hint=""),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    assert payload["corporate_actions"]["qip"]["value_original"] == "300.00"
    assert payload["shareholding_pattern"]["promoter_holding"]["value_original"] == "54.2%"
    assert payload["shareholding_pattern"]["promoter_holding"]["value_crore"] is None


def test_consolidated_preferred_over_standalone(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "400.00", 400.0)], basis="standalone"),
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)], basis="consolidated"),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)], basis="consolidated"),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "600.00", 600.0)], basis="consolidated"),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)], basis="consolidated"),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    assert payload["profit_and_loss"]["revenue"]["value_crore"] == 500.0
    assert payload["profit_and_loss"]["revenue"]["basis"] == "consolidated"
    assert payload["preferred_basis"] == "consolidated"
    assert payload["basis_confidence"] in {"medium", "high"}
    assert payload["basis_views"]["standalone"]["profit_and_loss"]["revenue"]["value_crore"] == 400.0


def test_note_total_assets_fills_gap_when_primary_bs_lacks_explicit_row(tmp_path):
    """
    When the primary balance sheet statement has no 'Total Assets' row (e.g. banking
    RBI-Schedule format) but a financial_note carries the correct total, the normalizer
    must use the note value rather than crashing.  The note is the only candidate and
    wins by default — _entry_rank's wrong_scope_penalty keeps it lower than a primary
    BS entry whenever one exists, but here there is no competing candidate.
    """
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)], basis="consolidated"),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Equity",
             [("March 31, 2025", "600.00", 600.0)], basis="consolidated"),
        _row("balance_sheet", "Total Liabilities",
             [("March 31, 2025", "400.00", 400.0)], basis="consolidated"),
        _row("balance_sheet", "Total Assets",
             [("March 31, 2025", "1000.00", 1000.0)], basis="consolidated", page=52),
    ]
    sections["balance_sheet"][0]["source_section_type"] = "primary_balance_sheet_statement"
    sections["balance_sheet"][0]["is_primary_statement"] = True
    sections["balance_sheet"][1]["source_section_type"] = "primary_balance_sheet_statement"
    sections["balance_sheet"][1]["is_primary_statement"] = True
    # Total Assets only in financial_note, not primary BS
    sections["balance_sheet"][2]["source_section_type"] = "financial_note"
    sections["balance_sheet"][2]["is_primary_statement"] = False
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    ta = payload["balance_sheet"]["total_assets"]
    assert ta["value_crore"] == 1000.0
    assert ta["source_section_type"] == "financial_note"


def test_primary_bs_total_assets_beats_financial_note_when_both_present(tmp_path):
    """
    When both primary_balance_sheet_statement and financial_note carry 'Total Assets',
    the primary statement entry must win (higher _entry_rank score).
    """
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)], basis="consolidated"),
    ]
    primary_ta = _row("balance_sheet", "Total Assets",
                      [("March 31, 2025", "2000.00", 2000.0)], basis="consolidated", page=10)
    primary_ta["source_section_type"] = "primary_balance_sheet_statement"
    primary_ta["is_primary_statement"] = True

    note_ta = _row("balance_sheet", "Total Assets",
                   [("March 31, 2025", "999.00", 999.0)], basis="consolidated", page=55)
    note_ta["source_section_type"] = "financial_note"
    note_ta["is_primary_statement"] = False

    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Equity",
             [("March 31, 2025", "1200.00", 1200.0)], basis="consolidated"),
        _row("balance_sheet", "Total Liabilities",
             [("March 31, 2025", "800.00", 800.0)], basis="consolidated"),
        primary_ta,
        note_ta,
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    ta = payload["balance_sheet"]["total_assets"]
    assert ta["value_crore"] == 2000.0
    assert ta["source_section_type"] == "primary_balance_sheet_statement"


def test_cash_flow_from_alternate_basis_is_not_promoted(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)], basis="consolidated"),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)], basis="consolidated"),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "600.00", 600.0)], basis="consolidated"),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)], basis="consolidated"),
    ]
    sections["cash_flow"] = [
        _row(
            "cash_flow",
            "Net cash generated from operating activities",
            [("March 31, 2025", "40.00", 40.0)],
            basis="standalone",
        ),
        _row(
            "cash_flow",
            "Purchase of property, plant and equipment",
            [("March 31, 2025", "(12.00)", -12.0)],
            basis="standalone",
        ),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["preferred_basis"] == "consolidated"
    assert payload["cash_flow"]["cfo"]["value_crore"] is None
    assert payload["basis_views"]["standalone"]["cash_flow"]["cfo"]["value_crore"] == 40.0
    assert any(
        "cash_flow.cfo is available only in standalone basis and was not promoted into preferred consolidated view" in warning
        for warning in payload["warnings"]
    )


def test_primary_unknown_basis_cash_flow_inherits_preferred_basis_when_unconflicted(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)], basis="consolidated"),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)], basis="consolidated"),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "600.00", 600.0)], basis="consolidated"),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)], basis="consolidated"),
    ]
    sections["cash_flow"] = [
        _row(
            "cash_flow",
            "Net Cash Flow generated from Operating Activities (A)",
            [("March 31, 2025", "20,281,998", 2028.1998)],
            basis="unknown",
            unit_hint="thousands",
            page=259,
        ),
        _row(
            "cash_flow",
            "Purchase of Fixed Assets including WIP",
            [("March 31, 2025", "(1,672,079)", -167.2079)],
            basis="unknown",
            unit_hint="thousands",
            page=259,
        ),
    ]
    for row in sections["cash_flow"]:
        row["source_section_type"] = "primary_cash_flow_statement"
        row["is_primary_statement"] = True
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["preferred_basis"] == "consolidated"
    assert payload["cash_flow"]["cfo"]["value_crore"] == 2028.1998
    assert payload["cash_flow"]["cfo"]["basis"] == "consolidated"
    assert payload["cash_flow"]["capex"]["value_crore"] == -167.2079
    assert payload["cash_flow_availability"]["status"] == "EXPLICIT"
    assert payload["cash_flow_availability"]["source_pages"] == [259]
    assert any(
        "cash_flow.cfo inherited preferred consolidated basis from a primary cash-flow statement" in warning
        for warning in payload["warnings"]
    )


def test_unknown_primary_cash_flow_does_not_override_conflicting_explicit_basis(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)], basis="consolidated"),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)], basis="consolidated"),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "600.00", 600.0)], basis="consolidated"),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)], basis="consolidated"),
    ]
    unknown_primary = _row(
        "cash_flow",
        "Net Cash Flow generated from Operating Activities (A)",
        [("March 31, 2025", "140.00", 140.0)],
        basis="unknown",
    )
    unknown_primary["source_section_type"] = "primary_cash_flow_statement"
    unknown_primary["is_primary_statement"] = True
    sections["cash_flow"] = [
        unknown_primary,
        _row(
            "cash_flow",
            "Net cash generated from operating activities",
            [("March 31, 2025", "40.00", 40.0)],
            basis="standalone",
        ),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["preferred_basis"] == "consolidated"
    assert payload["cash_flow"]["cfo"]["value_crore"] is None
    assert payload["basis_views"]["unknown"]["cash_flow"]["cfo"]["value_crore"] == 140.0
    assert payload["basis_views"]["standalone"]["cash_flow"]["cfo"]["value_crore"] == 40.0
    assert any("cash_flow.cfo is available only in standalone basis" in warning for warning in payload["warnings"])


def test_unknown_basis_field_is_not_promoted_into_explicit_preferred_basis(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)], basis="consolidated"),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "1000.00", 1000.0)], basis="consolidated"),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "600.00", 600.0)], basis="consolidated"),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)], basis="consolidated"),
        _row("balance_sheet", "Cash and cash equivalents", [("March 31, 2025", "25.00", 25.0)], basis="unknown"),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["preferred_basis"] == "consolidated"
    assert payload["balance_sheet"]["cash_and_equivalents"]["value_crore"] is None
    assert payload["basis_views"]["unknown"]["balance_sheet"]["cash_and_equivalents"]["value_crore"] == 25.0
    assert not any("fell back to unknown basis" in warning for warning in payload["warnings"])


def test_preferred_basis_does_not_silently_borrow_other_explicit_basis(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "400.00", 400.0)], basis="standalone"),
        _row("profit_and_loss", "Revenue from operations", [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
        _row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)], basis="consolidated"),
    ]
    sections["balance_sheet"] = [
        _row("balance_sheet", "Total Assets", [("March 31, 2025", "900.00", 900.0)], basis="consolidated"),
        _row("balance_sheet", "Total Equity", [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
        _row("balance_sheet", "Total Liabilities", [("March 31, 2025", "400.00", 400.0)], basis="consolidated"),
        _row("balance_sheet", "Trade payables", [("March 31, 2025", "30.00", 30.0)], basis="standalone"),
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["preferred_basis"] == "consolidated"
    assert payload["balance_sheet"]["payables"]["value_crore"] is None
    assert payload["basis_views"]["standalone"]["balance_sheet"]["payables"]["value_crore"] == 30.0
    assert any("balance_sheet.payables is available only in standalone basis" in warning for warning in payload["warnings"])
    assert payload["basis_manifest"]["preferred_basis"] == "consolidated"


def test_trade_payables_maps_to_payables(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["balance_sheet"].append(
        _row("balance_sheet", "Trade payables", [("March 31, 2025", "30.00", 30.0), ("March 31, 2024", "24.00", 24.0)])
    )
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["balance_sheet"]["payables"]["value_crore"] == 30.0
    assert payload["balance_sheet"]["payables"]["source_line_item"] == "Trade payables"
    assert payload["balance_sheet"]["payables"]["comparatives"][0]["value_crore"] == 24.0


def test_liabilities_prefixed_trade_payable_note_does_not_map_to_group_payables(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    note_row = _row(
        "balance_sheet",
        "Liabilities Trade payable",
        [("March 31, 2025", "113.30", 11.33)],
        basis="consolidated",
        page=298,
    )
    note_row["source_section_type"] = "financial_note"
    note_row["is_primary_statement"] = False
    sections["balance_sheet"].append(note_row)
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["balance_sheet"]["payables"]["value_crore"] is None
    assert payload["balance_sheet"]["payables"]["source_line_item"] == ""


def test_clean_trade_payables_wins_over_liabilities_prefixed_note_shape(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["balance_sheet"].append(
        _row("balance_sheet", "Trade payables", [("March 31, 2025", "3000.00", 3000.0)], page=250)
    )
    note_row = _row(
        "balance_sheet",
        "Liabilities Trade payable",
        [("March 31, 2025", "113.30", 11.33)],
        basis="consolidated",
        page=298,
    )
    note_row["source_section_type"] = "financial_note"
    note_row["is_primary_statement"] = False
    sections["balance_sheet"].append(note_row)
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["balance_sheet"]["payables"]["value_crore"] == 3000.0
    assert payload["balance_sheet"]["payables"]["source_line_item"] == "Trade payables"


def test_msme_and_other_creditors_aggregate_to_payables(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["balance_sheet"].extend(
        [
            _row(
                "balance_sheet",
                "Total outstanding dues of micro enterprises and small enterprises",
                [("March 31, 2025", "2.84", 2.84), ("March 31, 2024", "2.76", 2.76)],
            ),
            _row(
                "balance_sheet",
                "Total outstanding dues of creditors other than micro enterprises and small enterprises",
                [("March 31, 2025", "47.27", 47.27), ("March 31, 2024", "41.80", 41.8)],
            ),
        ]
    )
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    payables = payload["balance_sheet"]["payables"]

    assert payables["derived"] is True
    assert payables["formula"] == "msme_trade_payables + other_trade_payables"
    assert payables["source_line_item"] == "derived:trade_payables"
    assert payables["value_crore"] == 50.11
    assert payables["comparatives"][0]["value_crore"] == 44.56
    assert payables["inputs_used"]["msme_trade_payables"] == 2.84
    assert payables["inputs_used"]["other_trade_payables"] == 47.27


@pytest.mark.parametrize(
    "line_item_raw",
    [
        "Total liabilities",
        "Other financial liabilities",
        "Borrowings",
        "Lease liabilities",
        "Provisions",
        "Other current liabilities",
    ],
)
def test_generic_liability_rows_do_not_map_to_payables(tmp_path, line_item_raw):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["balance_sheet"].append(_row("balance_sheet", line_item_raw, [("March 31, 2025", "30.00", 30.0)]))
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["balance_sheet"]["payables"]["value_original"] == ""
    assert payload["balance_sheet"]["payables"]["value_crore"] is None


def test_unmapped_rows_preserved(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"].append(_row("profit_and_loss", "Strange bespoke metric", [("March 31, 2025", "77.00", 77.0)]))
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    assert payload["unmapped_rows"]
    assert payload["warnings"]
    assert "important rows unmapped" in payload["warnings"]


def test_primary_statement_preferred_over_management_summary(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"].append(
        _row(
            "profit_and_loss",
            "Revenue from operations",
            [("March 31, 2025", "500.00", 500.0)],
            confidence="high",
            page=10,
        )
    )
    sections["management_discussion_financial_summary"] = [
        _row(
            "management_discussion_financial_summary",
            "Revenue from operations",
            [("FY25", "300.00", 300.0)],
            confidence="high",
            page=20,
        )
    ]
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)
    assert payload["profit_and_loss"]["revenue"]["value_crore"] == 500.0
    assert payload["profit_and_loss"]["revenue"]["source_section_type"] == "primary_profit_and_loss_statement"


def test_write_normalized_fundamentals(tmp_path):
    raw_path = tmp_path / "raw_financial_tables.json"
    output_path = tmp_path / "normalized_fundamentals.json"
    _write_json(raw_path, _raw_payload(_minimum_required_sections()))

    payload = write_normalized_fundamentals(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        output_path=output_path,
    )

    assert output_path.exists()
    written = json.loads(output_path.read_text())
    assert written["company"] == payload["company"] == "acme"


def test_ratios_proceed_once_eps_and_share_count_value_types_are_normalized(tmp_path):
    raw_path = tmp_path / "raw_financial_tables.json"
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"].extend(
        [
            _row("profit_and_loss", "Other income", [("March 31, 2025", "20.00", 20.0)]),
            _row("profit_and_loss", "EBITDA", [("March 31, 2025", "150.00", 150.0)]),
            _row("profit_and_loss", "EBIT", [("March 31, 2025", "130.00", 130.0)]),
            _row("profit_and_loss", "Finance cost", [("March 31, 2025", "10.00", 10.0)]),
            _row("profit_and_loss", "Profit before tax", [("March 31, 2025", "120.00", 120.0)]),
            _row("profit_and_loss", "Tax expense", [("March 31, 2025", "20.00", 20.0)]),
        ]
    )
    sections["balance_sheet"].extend(
        [
            _row("balance_sheet", "Net worth", [("March 31, 2025", "400.00", 400.0)]),
            _row("balance_sheet", "Total debt", [("March 31, 2025", "100.00", 100.0)]),
            _row("balance_sheet", "Cash and cash equivalents", [("March 31, 2025", "40.00", 40.0)]),
            _row("balance_sheet", "Trade receivables", [("March 31, 2025", "50.00", 50.0)]),
            _row("balance_sheet", "Inventories", [("March 31, 2025", "60.00", 60.0)]),
            _row("balance_sheet", "Trade payables", [("March 31, 2025", "30.00", 30.0)]),
        ]
    )
    sections["cash_flow"] = [
        _row("cash_flow", "Net cash generated from operating activities", [("March 31, 2025", "110.00", 110.0)]),
        _row("cash_flow", "Purchase of property, plant and equipment", [("March 31, 2025", "(25.00)", -25.0)]),
        _row("cash_flow", "Dividend paid", [("March 31, 2025", "(20.00)", -20.0)]),
    ]
    sections["eps"] = [
        _row("eps", "Basic earnings per share", [("March 31, 2025", "10.00", None)], unit_hint="inr"),
        _row("eps", "Diluted earnings per share", [("March 31, 2025", "9.50", None)], unit_hint="inr"),
        _row("eps", "Weighted average number of equity shares", [("March 31, 2025", "100000000", None)], unit_hint="shares", currency_hint=""),
        _row("eps", "Diluted weighted average number of equity shares", [("March 31, 2025", "105000000", None)], unit_hint="shares", currency_hint=""),
    ]
    sections["share_capital"] = [
        _row("share_capital", "Face value per equity share", [("March 31, 2025", "10.00", None)], unit_hint="inr"),
        _row("share_capital", "Number of equity shares", [("March 31, 2025", "100000000", None)], unit_hint="shares", currency_hint=""),
        _row("share_capital", "Book value per share", [("March 31, 2025", "40.00", None)], unit_hint="inr"),
    ]
    _write_json(raw_path, _raw_payload(sections))

    normalized_payload = write_normalized_fundamentals(
        company="acme",
        year="fy25",
        raw_tables_path=raw_path,
        output_path=normalized_path,
    )
    assert normalized_payload["profit_and_loss"]["eps_basic"]["source_value_type"] == "per_share"
    assert normalized_payload["share_data"]["shares_outstanding"]["source_value_type"] == "share_count"

    reconciliation = build_financial_reconciliation_report(
        company="acme",
        year="fy25",
        normalized_path=normalized_path,
    )
    assert reconciliation.status in {"pass", "warning"}
    assert not reconciliation.hard_failures
    reconciliation_path.write_text(json.dumps(reconciliation.to_dict()), encoding="utf-8")

    ratios = calculate_financial_ratios(
        company="acme",
        year="fy25",
        normalized_path=normalized_path,
        reconciliation_path=reconciliation_path,
    )
    assert ratios.ratios["eps_basic"].value == 10.0
    assert ratios.ratios["book_value_per_share"].value is not None


def test_no_company_specific_behavior():
    text = Path("knowledge/financials/normalizer.py").read_text(encoding="utf-8").lower()
    assert "datapatterns" not in text
    assert "polymatech" not in text
    assert "tanla" not in text
    assert "tips" not in text


def test_missing_required_revenue_fails(tmp_path):
    path = tmp_path / "raw_financial_tables.json"
    sections = _minimum_required_sections()
    sections["profit_and_loss"] = [_row("profit_and_loss", "Profit for the year", [("March 31, 2025", "120.00", 120.0)])]
    _write_json(path, _raw_payload(sections))

    with pytest.raises(RuntimeError, match="missing required revenue"):
        normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)


def test_placeholder_period_labels_are_ignored_in_value_selection():
    values = [
        {"period": "value_1", "value_raw": "500.00", "value_crore": 500.0},
        {"period": "PERIOD_COLUMN_UNRESOLVED", "value_raw": "420.00", "value_crore": 420.0},
        {"period": "March 31, 2025", "value_raw": "610.00", "value_crore": 610.0},
    ]

    selected = _select_value(values, "fy25")

    assert selected is not None
    assert selected["period"] == "March 31, 2025"


# ---------------------------------------------------------------------------
# Regression: unknown-basis fallback in _build_preferred_sections
#
# When preferred_basis is "consolidated" (driven by P&L rows) but balance-sheet
# rows carry basis="unknown", the normalizer must still populate balance_sheet
# fields rather than crashing with a RuntimeError.  The fix removed the spurious
# `and preferred_basis == "unknown"` guard that blocked the fallback.
# ---------------------------------------------------------------------------

def _consolidated_pl_unknown_bs_sections(*, revenue=500.0, pat=120.0, total_assets=1000.0, net_worth=600.0):
    """
    Helper: P&L rows are consolidated-basis; balance-sheet rows are unknown-basis.
    This is the exact pattern that triggered the RuntimeError before the fix.
    """
    return {
        "profit_and_loss": [
            _row("profit_and_loss", "Revenue from operations",
                 [("March 31, 2025", str(revenue), revenue)], basis="consolidated"),
            _row("profit_and_loss", "Profit for the year",
                 [("March 31, 2025", str(pat), pat)], basis="consolidated"),
        ],
        "balance_sheet": [
            _row("balance_sheet", "Total Assets",
                 [("March 31, 2025", str(total_assets), total_assets)], basis="unknown"),
            _row("balance_sheet", "Total Equity",
                 [("March 31, 2025", str(net_worth), net_worth)], basis="unknown"),
            _row("balance_sheet", "Total Liabilities",
                 [("March 31, 2025", "400.00", 400.0)], basis="unknown"),
        ],
    }


def test_consolidated_pl_unknown_bs_does_not_crash(tmp_path):
    """Core failing case: P&L=consolidated + BS=unknown must not raise RuntimeError."""
    path = tmp_path / "raw_financial_tables.json"
    _write_json(path, _raw_payload(_consolidated_pl_unknown_bs_sections()))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["revenue"]["value_crore"] == 500.0
    assert payload["balance_sheet"]["total_assets"]["value_crore"] == 1000.0


def test_consolidated_pl_unknown_bs_populates_all_balance_sheet_fields(tmp_path):
    """All balance-sheet canonical fields are present when BS rows are unknown-basis."""
    path = tmp_path / "raw_financial_tables.json"
    _write_json(path, _raw_payload(_consolidated_pl_unknown_bs_sections(
        total_assets=2500.0, net_worth=1500.0
    )))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["balance_sheet"]["total_assets"]["value_crore"] == 2500.0
    assert payload["balance_sheet"]["net_worth"]["value_crore"] == 1500.0


def test_unknown_pl_unknown_bs_still_works(tmp_path):
    """
    Valid nearby variant: when both P&L and BS are unknown-basis the normalizer
    must still populate fields (regression guard — must not become collateral damage).
    """
    path = tmp_path / "raw_financial_tables.json"
    sections = {
        "profit_and_loss": [
            _row("profit_and_loss", "Revenue from operations",
                 [("March 31, 2025", "800.00", 800.0)], basis="unknown"),
            _row("profit_and_loss", "Profit for the year",
                 [("March 31, 2025", "200.00", 200.0)], basis="unknown"),
        ],
        "balance_sheet": [
            _row("balance_sheet", "Total Assets",
                 [("March 31, 2025", "3000.00", 3000.0)], basis="unknown"),
            _row("balance_sheet", "Total Equity",
                 [("March 31, 2025", "1800.00", 1800.0)], basis="unknown"),
            _row("balance_sheet", "Total Liabilities",
                 [("March 31, 2025", "1200.00", 1200.0)], basis="unknown"),
        ],
    }
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["profit_and_loss"]["revenue"]["value_crore"] == 800.0
    assert payload["balance_sheet"]["total_assets"]["value_crore"] == 3000.0


def test_consolidated_pl_standalone_bs_extra_field_not_promoted_via_unknown_fallback(tmp_path):
    """
    Wrong-basis near-neighbor: when consolidated BS is present and an additional
    field exists only in the standalone bucket, it must NOT leak into consolidated
    preferred_sections via the unknown fallback — the fallback only reads the unknown
    bucket, not standalone.
    """
    path = tmp_path / "raw_financial_tables.json"
    sections = {
        "profit_and_loss": [
            _row("profit_and_loss", "Revenue from operations",
                 [("March 31, 2025", "500.00", 500.0)], basis="consolidated"),
            _row("profit_and_loss", "Profit for the year",
                 [("March 31, 2025", "100.00", 100.0)], basis="consolidated"),
        ],
        "balance_sheet": [
            # consolidated core entries — must be used
            _row("balance_sheet", "Total Assets",
                 [("March 31, 2025", "1000.00", 1000.0)], basis="consolidated"),
            _row("balance_sheet", "Total Equity",
                 [("March 31, 2025", "600.00", 600.0)], basis="consolidated"),
            _row("balance_sheet", "Total Liabilities",
                 [("March 31, 2025", "400.00", 400.0)], basis="consolidated"),
            # standalone-only cash entry — must NOT leak into consolidated preferred view
            _row("balance_sheet", "Cash and cash equivalents",
                 [("March 31, 2025", "9999.00", 9999.0)], basis="standalone"),
        ],
    }
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    # Standalone cash entry must not appear in consolidated preferred_sections
    cash = payload["balance_sheet"]["cash_and_equivalents"]
    assert cash.get("value_crore") != 9999.0


def test_preferred_basis_entry_blocks_unknown_fallback(tmp_path):
    """
    When the preferred_basis bucket already has an entry, the unknown fallback
    must NOT override it with the unknown-bucket entry.
    """
    path = tmp_path / "raw_financial_tables.json"
    sections = {
        "profit_and_loss": [
            _row("profit_and_loss", "Revenue from operations",
                 [("March 31, 2025", "700.00", 700.0)], basis="consolidated"),
            _row("profit_and_loss", "Profit for the year",
                 [("March 31, 2025", "150.00", 150.0)], basis="consolidated"),
        ],
        "balance_sheet": [
            # consolidated entry — should win
            _row("balance_sheet", "Total Assets",
                 [("March 31, 2025", "5000.00", 5000.0)], basis="consolidated"),
            _row("balance_sheet", "Total Equity",
                 [("March 31, 2025", "3000.00", 3000.0)], basis="consolidated"),
            _row("balance_sheet", "Total Liabilities",
                 [("March 31, 2025", "2000.00", 2000.0)], basis="consolidated"),
            # unknown entry for same field — must NOT win over consolidated
            _row("balance_sheet", "Total Assets",
                 [("March 31, 2025", "9999.00", 9999.0)], basis="unknown"),
        ],
    }
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    assert payload["balance_sheet"]["total_assets"]["value_crore"] == 5000.0


def test_fallback_entry_records_unknown_basis_in_output(tmp_path):
    """
    Provenance: when the unknown fallback is used, the output entry must record
    basis='unknown' (not the preferred_basis), so investors can audit the source.
    """
    path = tmp_path / "raw_financial_tables.json"
    _write_json(path, _raw_payload(_consolidated_pl_unknown_bs_sections()))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    ta = payload["balance_sheet"]["total_assets"]
    assert ta.get("basis") == "unknown", (
        f"Fallback entry must retain basis='unknown', got {ta.get('basis')!r}"
    )


def test_standalone_pl_unknown_bs_does_not_crash(tmp_path):
    """
    Second company pattern: standalone preferred_basis + unknown BS must also work.
    Validates the fix is not limited to consolidated.
    """
    path = tmp_path / "raw_financial_tables.json"
    sections = {
        "profit_and_loss": [
            _row("profit_and_loss", "Revenue from operations",
                 [("March 31, 2024", "350.00", 350.0)], basis="standalone"),
            _row("profit_and_loss", "Profit for the year",
                 [("March 31, 2024", "70.00", 70.0)], basis="standalone"),
        ],
        "balance_sheet": [
            _row("balance_sheet", "Total Assets",
                 [("March 31, 2024", "1200.00", 1200.0)], basis="unknown"),
            _row("balance_sheet", "Total Equity",
                 [("March 31, 2024", "700.00", 700.0)], basis="unknown"),
            _row("balance_sheet", "Total Liabilities",
                 [("March 31, 2024", "500.00", 500.0)], basis="unknown"),
        ],
    }
    _write_json(path, _raw_payload(sections))

    payload = normalize_financial_tables(company="acme", year="fy24", raw_tables_path=path)

    assert payload["balance_sheet"]["total_assets"]["value_crore"] == 1200.0
    assert payload["profit_and_loss"]["revenue"]["value_crore"] == 350.0


def test_unknown_basis_fallback_basis_warning_emitted(tmp_path):
    """
    When the unknown fallback is triggered, a basis warning must appear in
    payload['warnings'] so the reconciliation report can surface the provenance gap.
    """
    path = tmp_path / "raw_financial_tables.json"
    _write_json(path, _raw_payload(_consolidated_pl_unknown_bs_sections()))

    payload = normalize_financial_tables(company="acme", year="fy25", raw_tables_path=path)

    all_warnings = payload.get("warnings", [])
    assert any(
        "fell back to unknown basis" in str(w) or "basis unclear" in str(w)
        for w in all_warnings
    ), f"Expected a fallback/basis warning in payload warnings, got: {all_warnings}"


def test_no_company_or_sector_hardcoding_in_normalizer():
    """Normalizer must contain no company- or sector-specific string literals."""
    text = (ROOT / "knowledge/financials/normalizer.py").read_text(encoding="utf-8").lower()
    forbidden = {"ujjivan", "sun_pharma", "sunpharma", "cipla", "drreddy", "lupin", "zydus", "hdfc", "icici"}
    for name in forbidden:
        assert name not in text, f"Company name {name!r} found in normalizer.py — remove hardcoding"


def test_sun_pharma_fy23_revenue_unaffected_by_unknown_basis_fix(tmp_path):
    """
    Regression guard: the Sun Pharma FY23 production path must remain intact
    after restoring the unknown-basis fallback.
    """
    import importlib.util, sys

    raw_path = ROOT / "companies/sun_pharma/fy23/financials/raw_financial_tables.json"
    if not raw_path.exists():
        pytest.skip("Sun Pharma FY23 raw tables not present")

    payload = normalize_financial_tables(
        company="sun_pharma", year="fy23", raw_tables_path=raw_path
    )

    revenue = payload["profit_and_loss"]["revenue"]["value_crore"]
    pat = payload["profit_and_loss"]["pat"]["value_crore"]

    assert revenue is not None, "Sun Pharma FY23 revenue must not be None after fix"
    assert pat is not None, "Sun Pharma FY23 PAT must not be None after fix"
    # Values within 1% of expected (43 885.68 crore revenue, 8 473.58 crore PAT)
    assert abs(revenue - 43885.68) / 43885.68 < 0.01, f"Revenue regression: {revenue}"
    assert abs(pat - 8473.58) / 8473.58 < 0.01, f"PAT regression: {pat}"
