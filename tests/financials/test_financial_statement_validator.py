import json
from pathlib import Path

import pytest

from knowledge.financials.statement_validator import (
    validate_normalized_fundamentals,
    write_financial_validation_report,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _entry(
    field,
    *,
    value_crore=None,
    value_original="",
    unit_original="crores",
    basis="consolidated",
    period="March 31, 2025",
    page=1,
    artifact="normalized_source.json",
    confidence="high",
    warnings=None,
):
    return {
        "canonical_field": field,
        "value_crore": value_crore,
        "value_original": value_original,
        "unit_original": unit_original,
        "basis": basis,
        "period": period,
        "source_line_item": field.replace("_", " ").title(),
        "source_page": page,
        "source_artifact": artifact,
        "confidence": confidence,
        "warnings": list(warnings or []),
        "comparatives": [],
    }


def _empty_section(fields):
    return {field: _entry(field, unit_original="", basis="unknown", artifact="", confidence="missing") for field in fields}


def _payload():
    profit_and_loss_fields = [
        "revenue", "other_income", "total_income", "cost_of_materials", "employee_cost", "other_expenses",
        "ebitda", "depreciation", "ebit", "finance_cost", "pbt", "tax", "pat", "eps_basic", "eps_diluted",
    ]
    balance_sheet_fields = [
        "equity_share_capital", "reserves", "net_worth", "total_debt", "short_term_debt", "long_term_debt",
        "cash_and_equivalents", "investments", "inventories", "receivables", "payables", "fixed_assets",
        "cwip", "total_assets", "total_liabilities",
    ]
    cash_flow_fields = ["cfo", "cfi", "cff", "capex", "fcf", "dividends_paid", "interest_paid", "tax_paid"]
    share_data_fields = ["face_value", "shares_outstanding", "weighted_avg_shares", "diluted_shares", "book_value_per_share"]
    corporate_action_fields = ["dividend", "split", "bonus", "buyback", "rights_issue", "qip", "preferential_issue"]
    shareholding_fields = [
        "promoter_holding", "pledged_promoter_holding", "fii_holding", "dii_holding", "mutual_fund_holding", "public_holding"
    ]

    payload = {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-16T00:00:00Z",
        "preferred_basis": "consolidated",
        "profit_and_loss": _empty_section(profit_and_loss_fields),
        "balance_sheet": _empty_section(balance_sheet_fields),
        "cash_flow": _empty_section(cash_flow_fields),
        "share_data": _empty_section(share_data_fields),
        "corporate_actions": _empty_section(corporate_action_fields),
        "shareholding_pattern": _empty_section(shareholding_fields),
        "basis_views": {
            "consolidated": {
                "profit_and_loss": _empty_section(profit_and_loss_fields),
                "balance_sheet": _empty_section(balance_sheet_fields),
                "cash_flow": _empty_section(cash_flow_fields),
                "share_data": _empty_section(share_data_fields),
                "corporate_actions": _empty_section(corporate_action_fields),
                "shareholding_pattern": _empty_section(shareholding_fields),
            },
            "standalone": {
                "profit_and_loss": _empty_section(profit_and_loss_fields),
                "balance_sheet": _empty_section(balance_sheet_fields),
                "cash_flow": _empty_section(cash_flow_fields),
                "share_data": _empty_section(share_data_fields),
                "corporate_actions": _empty_section(corporate_action_fields),
                "shareholding_pattern": _empty_section(shareholding_fields),
            },
            "unknown": {
                "profit_and_loss": _empty_section(profit_and_loss_fields),
                "balance_sheet": _empty_section(balance_sheet_fields),
                "cash_flow": _empty_section(cash_flow_fields),
                "share_data": _empty_section(share_data_fields),
                "corporate_actions": _empty_section(corporate_action_fields),
                "shareholding_pattern": _empty_section(shareholding_fields),
            },
        },
        "unmapped_rows": [],
        "warnings": [],
        "limitations": [],
    }

    payload["profit_and_loss"]["revenue"] = _entry("revenue", value_crore=500.0, value_original="500.00")
    payload["profit_and_loss"]["other_income"] = _entry("other_income", value_crore=20.0, value_original="20.00")
    payload["profit_and_loss"]["total_income"] = _entry("total_income", value_crore=520.0, value_original="520.00")
    payload["profit_and_loss"]["ebit"] = _entry("ebit", value_crore=150.0, value_original="150.00")
    payload["profit_and_loss"]["finance_cost"] = _entry("finance_cost", value_crore=10.0, value_original="10.00")
    payload["profit_and_loss"]["pbt"] = _entry("pbt", value_crore=140.0, value_original="140.00")
    payload["profit_and_loss"]["tax"] = _entry("tax", value_crore=20.0, value_original="20.00")
    payload["profit_and_loss"]["pat"] = _entry("pat", value_crore=120.0, value_original="120.00")
    payload["profit_and_loss"]["depreciation"] = _entry("depreciation", value_crore=15.0, value_original="15.00")
    payload["profit_and_loss"]["eps_basic"] = _entry("eps_basic", value_crore=None, value_original="12.00", unit_original="inr")

    payload["balance_sheet"]["equity_share_capital"] = _entry("equity_share_capital", value_crore=50.0, value_original="50.00")
    payload["balance_sheet"]["reserves"] = _entry("reserves", value_crore=350.0, value_original="350.00")
    payload["balance_sheet"]["net_worth"] = _entry("net_worth", value_crore=400.0, value_original="400.00")
    payload["balance_sheet"]["total_debt"] = _entry("total_debt", value_crore=100.0, value_original="100.00")
    payload["balance_sheet"]["cash_and_equivalents"] = _entry("cash_and_equivalents", value_crore=70.0, value_original="70.00")
    payload["balance_sheet"]["total_assets"] = _entry("total_assets", value_crore=500.0, value_original="500.00")
    payload["balance_sheet"]["total_liabilities"] = _entry("total_liabilities", value_crore=100.0, value_original="100.00")

    payload["cash_flow"]["cfo"] = _entry("cfo", value_crore=80.0, value_original="80.00")
    payload["cash_flow"]["capex"] = _entry("capex", value_crore=-30.0, value_original="(30.00)")
    payload["cash_flow"]["cfi"] = _entry("cfi", value_crore=-40.0, value_original="(40.00)")
    payload["cash_flow"]["cff"] = _entry("cff", value_crore=-10.0, value_original="(10.00)")
    payload["cash_flow"]["tax_paid"] = _entry("tax_paid", value_crore=-18.0, value_original="(18.00)")

    payload["share_data"]["shares_outstanding"] = _entry(
        "shares_outstanding", value_crore=None, value_original="1000000", unit_original="shares"
    )
    payload["share_data"]["book_value_per_share"] = _entry(
        "book_value_per_share", value_crore=None, value_original="40.00", unit_original="inr"
    )

    return payload


def test_valid_fundamentals_pass(tmp_path):
    path = tmp_path / "normalized_fundamentals.json"
    _write_json(path, _payload())

    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path)

    assert report.status == "pass"
    assert report.hard_failures == []


def test_missing_revenue_fails(tmp_path):
    path = tmp_path / "normalized_fundamentals.json"
    payload = _payload()
    payload["profit_and_loss"]["revenue"]["value_original"] = ""
    payload["profit_and_loss"]["revenue"]["value_crore"] = None
    _write_json(path, payload)

    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path)
    assert report.status == "fail"
    assert "revenue missing" in report.hard_failures


def test_missing_pat_fails(tmp_path):
    path = tmp_path / "normalized_fundamentals.json"
    payload = _payload()
    payload["profit_and_loss"]["pat"]["value_original"] = ""
    payload["profit_and_loss"]["pat"]["value_crore"] = None
    _write_json(path, payload)

    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path)
    assert report.status == "fail"
    assert "PAT missing" in report.hard_failures


def test_balance_sheet_mismatch_warning_or_fail(tmp_path):
    path = tmp_path / "normalized_fundamentals.json"
    payload = _payload()
    payload["balance_sheet"]["total_assets"]["value_crore"] = 800.0
    payload["balance_sheet"]["total_assets"]["value_original"] = "800.00"
    _write_json(path, payload)

    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path)
    assert report.status == "fail"
    assert any("balance_sheet_equation" in failure for failure in report.hard_failures)


def test_missing_cfo_warning(tmp_path):
    path = tmp_path / "normalized_fundamentals.json"
    payload = _payload()
    payload["cash_flow"]["cfo"]["value_original"] = ""
    payload["cash_flow"]["cfo"]["value_crore"] = None
    _write_json(path, payload)

    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path)
    assert report.status == "warning"
    assert "CFO missing" in report.warnings


def test_unit_missing_warning(tmp_path):
    path = tmp_path / "normalized_fundamentals.json"
    payload = _payload()
    payload["profit_and_loss"]["revenue"]["unit_original"] = ""
    _write_json(path, payload)

    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path)
    assert report.status == "warning"
    assert "unit_original missing for profit_and_loss.revenue" in report.warnings


def test_suspicious_negative_debt_warning(tmp_path):
    path = tmp_path / "normalized_fundamentals.json"
    payload = _payload()
    payload["balance_sheet"]["total_debt"]["value_crore"] = -5.0
    payload["balance_sheet"]["total_debt"]["value_original"] = "(5.00)"
    _write_json(path, payload)

    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path)
    assert "debt is negative" in report.suspicious_values


def test_consolidated_standalone_basis_handling(tmp_path):
    path = tmp_path / "normalized_fundamentals.json"
    payload = _payload()
    payload["balance_sheet"]["net_worth"]["basis"] = "standalone"
    _write_json(path, payload)

    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path)
    assert report.basis_checked == "mixed"


def test_unknown_plus_single_explicit_basis_is_unresolved_not_mixed(tmp_path):
    path = tmp_path / "normalized_fundamentals.json"
    payload = _payload()
    for section_name in ("profit_and_loss", "balance_sheet", "cash_flow", "share_data", "corporate_actions", "shareholding_pattern"):
        for entry in payload.get(section_name, {}).values():
            if isinstance(entry, dict):
                entry["basis"] = "unknown"
    payload["balance_sheet"]["net_worth"]["basis"] = "standalone"
    _write_json(path, payload)

    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path)
    assert report.basis_checked == "unknown"


def test_validator_flags_suspicious_ebit_source(tmp_path):
    path = tmp_path / "normalized_fundamentals.json"
    payload = _payload()
    payload["profit_and_loss"]["ebit"]["source_line_item"] = "Surplus in statement of profit and loss Opening balance"
    _write_json(path, payload)

    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path)
    assert "profit_and_loss.ebit mapped from suspicious source_line_item" in report.warnings


def test_validator_flags_value_crore_for_per_share_field(tmp_path):
    path = tmp_path / "normalized_fundamentals.json"
    payload = _payload()
    payload["profit_and_loss"]["eps_basic"]["value_crore"] = 12.0
    _write_json(path, payload)

    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path)
    assert "profit_and_loss.eps_basic should not carry value_crore" in report.warnings


def test_write_financial_validation_report(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    output_path = tmp_path / "financial_validation_report.json"
    _write_json(normalized_path, _payload())

    report = write_financial_validation_report(
        company="acme",
        year="fy25",
        normalized_path=normalized_path,
        output_path=output_path,
    )

    assert output_path.exists()
    written = json.loads(output_path.read_text())
    assert written["status"] == report.status


def test_no_company_specific_behavior():
    text = Path("knowledge/financials/statement_validator.py").read_text(encoding="utf-8").lower()
    assert "datapatterns" not in text
    assert "polymatech" not in text
    assert "tanla" not in text
    assert "tips" not in text
