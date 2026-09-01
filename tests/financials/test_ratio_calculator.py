import json
from pathlib import Path

import pytest

from knowledge.financials.ratio_calculator import calculate_financial_ratios, write_financial_ratios


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
        "sign_convention": "",
    }


def _empty_section(fields):
    return {field: _entry(field, unit_original="", basis="unknown", artifact="", confidence="missing") for field in fields}


def _normalized_payload():
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
        "generated_at": "2026-07-17T00:00:00Z",
        "preferred_basis": "consolidated",
        "basis_confidence": "high",
        "basis_manifest": {
            "preferred_basis": "consolidated",
            "basis_options_available": ["consolidated", "standalone"],
            "selected_basis_reason": "selected consolidated because it is available and reasonably complete",
            "basis_confidence": "high",
            "field_basis_selection": [],
            "basis_warnings": [],
        },
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
    payload["profit_and_loss"]["cost_of_materials"] = _entry("cost_of_materials", value_crore=200.0, value_original="200.00")
    payload["profit_and_loss"]["ebitda"] = _entry("ebitda", value_crore=150.0, value_original="150.00")
    payload["profit_and_loss"]["ebit"] = _entry("ebit", value_crore=130.0, value_original="130.00")
    payload["profit_and_loss"]["finance_cost"] = _entry("finance_cost", value_crore=10.0, value_original="10.00")
    payload["profit_and_loss"]["pbt"] = _entry("pbt", value_crore=120.0, value_original="120.00")
    payload["profit_and_loss"]["tax"] = _entry("tax", value_crore=20.0, value_original="20.00")
    payload["profit_and_loss"]["pat"] = _entry("pat", value_crore=100.0, value_original="100.00")
    payload["profit_and_loss"]["eps_basic"] = _entry("eps_basic", value_crore=None, value_original="10.00", unit_original="inr")
    payload["profit_and_loss"]["eps_diluted"] = _entry("eps_diluted", value_crore=None, value_original="9.50", unit_original="inr")

    payload["balance_sheet"]["net_worth"] = _entry("net_worth", value_crore=400.0, value_original="400.00")
    payload["balance_sheet"]["total_debt"] = _entry("total_debt", value_crore=100.0, value_original="100.00")
    payload["balance_sheet"]["cash_and_equivalents"] = _entry("cash_and_equivalents", value_crore=40.0, value_original="40.00")
    payload["balance_sheet"]["total_assets"] = _entry("total_assets", value_crore=600.0, value_original="600.00")
    payload["balance_sheet"]["receivables"] = _entry("receivables", value_crore=50.0, value_original="50.00")
    payload["balance_sheet"]["inventories"] = _entry("inventories", value_crore=60.0, value_original="60.00")
    payload["balance_sheet"]["payables"] = _entry("payables", value_crore=30.0, value_original="30.00")

    payload["cash_flow"]["cfo"] = _entry("cfo", value_crore=110.0, value_original="110.00")
    payload["cash_flow"]["capex"] = _entry("capex", value_crore=-25.0, value_original="(25.00)")
    payload["cash_flow"]["dividends_paid"] = _entry("dividends_paid", value_crore=-20.0, value_original="(20.00)")

    payload["share_data"]["shares_outstanding"] = _entry(
        "shares_outstanding", value_crore=None, value_original="100000000", unit_original="shares"
    )
    payload["share_data"]["book_value_per_share"] = _entry(
        "book_value_per_share", value_crore=None, value_original="40.00", unit_original="inr"
    )
    return payload


def _validation_payload(status="pass"):
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "status": status,
        "basis_checked": "consolidated",
        "hard_failures": [] if status != "fail" else ["synthetic fail"],
        "warnings": [],
        "checks": [],
        "missing_fields": [],
        "suspicious_values": [],
        "limitations": [],
    }


def _reconciliation_payload(status="pass", *, overrides=None):
    checks = {
        field: {
            "field_name": field,
            "status": "pass",
            "hard_failure": False,
            "reason": "ok",
            "source_line_item": field,
            "source_section_type": "primary_profit_and_loss_statement",
            "statement_type": "profit_and_loss",
            "basis": "consolidated",
            "source_artifacts": ["normalized_source.json"],
            "warnings": [],
        }
        for field in [
            "revenue", "ebitda", "ebit", "finance_cost", "pat", "eps_basic", "eps_diluted",
            "net_worth", "total_assets", "total_debt", "cash_and_equivalents", "receivables",
            "inventories", "payables", "cfo", "capex", "dividends_paid",
            "shares_outstanding", "weighted_avg_shares", "diluted_shares",
        ]
    }
    for field in ("shares_outstanding", "weighted_avg_shares", "diluted_shares"):
        checks[field]["source_section_type"] = "share_capital_note"
        checks[field]["statement_type"] = "share_capital"
    for field in ("eps_basic", "eps_diluted"):
        checks[field]["source_value_type"] = "per_share"
    if overrides:
        for field, values in overrides.items():
            checks[field].update(values)
    hard_failures = [
        f"{field}: {item['reason']}"
        for field, item in checks.items()
        if item.get("hard_failure") and item.get("status") == "fail"
    ]
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "status": status,
        "checks": checks,
        "hard_failures": hard_failures,
        "warnings": [],
        "limitations": [],
    }


def test_margin_calculation(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )
    assert report.ratios["ebitda_margin"].value == 30.0
    assert report.ratios["ebit_margin"].value == 26.0
    assert report.ratios["npm"].value == 20.0


def test_roe_and_roce_calculation(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )
    assert report.ratios["roe"].value == 25.0
    assert round(report.ratios["roce"].value, 4) == 28.2609


def test_debt_equity_and_net_debt_calculation(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )
    assert report.ratios["debt_to_equity"].value == 0.25
    assert report.ratios["net_debt"].value == 60.0
    assert report.ratios["net_debt_to_equity"].value == 0.15


def test_cfo_pat_and_fcf_calculation(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )
    assert report.ratios["cfo_to_pat"].value == 1.1
    assert report.ratios["fcf"].value == 85.0
    assert report.ratios["fcf_to_pat"].value == 0.85
    assert report.ratios["fcf_margin"].value == 17.0


def test_ratio_report_carries_basis_manifest_context(tmp_path):
    normalized = _normalized_payload()
    normalized["basis_confidence"] = "medium"
    normalized["basis_manifest"]["basis_warnings"] = [
        "cash_flow.capex fell back to unknown basis because preferred consolidated evidence was unavailable"
    ]
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    _write_json(normalized_path, normalized)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.basis_used == "consolidated"
    assert report.basis_confidence == "medium"
    assert report.basis_warnings == normalized["basis_manifest"]["basis_warnings"]


def test_fcf_uses_positive_outflow_sign_convention_when_present(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["cash_flow"]["capex"]["value_crore"] = 25.0
    payload["cash_flow"]["capex"]["value_original"] = "25.00"
    payload["cash_flow"]["capex"]["sign_convention"] = "positive_outflow"
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.ratios["fcf"].value == 85.0
    assert "capex treated as positive outflow during FCF calculation" in report.ratios["fcf"].warnings


def test_book_value_per_share_and_eps_passthrough(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )
    assert report.ratios["eps_basic"].value == 10.0
    assert report.ratios["eps_diluted"].value == 9.5
    assert report.ratios["book_value_per_share"].value == 40.0


def test_dividend_per_share_uses_shares_outstanding_only(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"]["value_original"] = ""
    payload["share_data"]["shares_outstanding"]["raw_number"] = None
    payload["share_data"]["diluted_shares"] = _entry(
        "diluted_shares",
        value_crore=None,
        value_original="12100000",
        unit_original="shares",
    )
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload("warning"))

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.ratios["dividend_per_share"].value is None
    assert "share count missing" in report.ratios["dividend_per_share"].warnings


def test_division_by_zero_handling(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["balance_sheet"]["net_worth"]["value_crore"] = 0.0
    payload["balance_sheet"]["net_worth"]["value_original"] = "0.00"
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )
    assert report.ratios["roe"].value is None
    assert "division by zero" in report.ratios["roe"].warnings


def test_missing_input_warnings(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["cash_flow"]["cfo"]["value_original"] = ""
    payload["cash_flow"]["cfo"]["value_crore"] = None
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload("warning"))

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )
    assert report.status == "warning"
    assert "CFO missing" in report.warnings


def test_fcf_stays_null_when_capex_is_missing(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["cash_flow"]["capex"]["value_original"] = ""
    payload["cash_flow"]["capex"]["value_crore"] = None
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload("warning"))

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.status == "warning"
    assert report.ratios["fcf"].value is None
    assert report.ratios["fcf_to_pat"].value is None
    assert report.ratios["fcf_margin"].value is None
    assert "capex missing" in report.warnings


def test_uses_comparatives_for_average_values(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["balance_sheet"]["net_worth"]["comparatives"] = [
        {"period": "March 31, 2024", "value_crore": 300.0, "basis": "consolidated"}
    ]
    payload["balance_sheet"]["total_assets"]["comparatives"] = [
        {"period": "March 31, 2024", "value_crore": 500.0, "basis": "consolidated"}
    ]
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.ratios["roe"].value == 28.5714
    assert not any("closing value" in warning for warning in report.ratios["roe"].warnings)


def test_payable_days_and_cash_conversion_cycle_calculate(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["balance_sheet"]["receivables"]["comparatives"] = [
        {"period": "March 31, 2024", "value_crore": 40.0, "basis": "consolidated"}
    ]
    payload["balance_sheet"]["inventories"]["comparatives"] = [
        {"period": "March 31, 2024", "value_crore": 50.0, "basis": "consolidated"}
    ]
    payload["balance_sheet"]["payables"]["comparatives"] = [
        {"period": "March 31, 2024", "value_crore": 20.0, "basis": "consolidated"}
    ]
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.ratios["payable_days"].value == 45.625
    assert report.ratios["cash_conversion_cycle"].value == 87.6


def test_payable_days_uses_closing_balance_with_precision_warning_when_opening_missing(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["balance_sheet"]["payables"]["comparatives"] = []
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.ratios["payable_days"].value == 54.75
    assert "used closing value because prior-year average was unavailable" in report.ratios["payable_days"].warnings


def test_payable_days_rejects_incompatible_total_expenses_denominator(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["profit_and_loss"]["cost_of_materials"]["source_line_item"] = "Total expenses"
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.ratios["payable_days"].value is None
    assert any("not a compatible purchases or COGS base" in warning for warning in report.ratios["payable_days"].warnings)


def test_payable_days_rejects_wrong_basis_denominator(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["profit_and_loss"]["cost_of_materials"]["basis"] = "standalone"
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.ratios["payable_days"].value is None
    assert "payable_days unavailable: numerator and denominator basis mismatch" in report.ratios["payable_days"].warnings


def test_payable_days_rejects_wrong_period_denominator(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["profit_and_loss"]["cost_of_materials"]["period"] = "March 31, 2024"
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.ratios["payable_days"].value is None
    assert "payable_days unavailable: denominator period does not match fiscal year" in report.ratios["payable_days"].warnings


def test_payable_days_rejects_unit_mismatch(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["profit_and_loss"]["cost_of_materials"]["unit_original"] = "shares"
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.ratios["payable_days"].value is None
    assert any("units are not compatible" in warning for warning in report.ratios["payable_days"].warnings)


def test_payable_days_rejects_stores_spares_denominator_and_absurd_days(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["balance_sheet"]["payables"]["value_crore"] = 3973.66
    payload["balance_sheet"]["payables"]["value_original"] = "3973.66"
    payload["profit_and_loss"]["cost_of_materials"]["value_crore"] = 284.89
    payload["profit_and_loss"]["cost_of_materials"]["value_original"] = "284.89"
    payload["profit_and_loss"]["cost_of_materials"]["source_line_item"] = "Consumption of materials, stores and spare parts"
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.ratios["payable_days"].value is None
    assert any("stores/spares consumption" in warning for warning in report.ratios["payable_days"].warnings)


def test_payable_days_rejects_tiny_denominator_that_would_create_absurd_days(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["balance_sheet"]["payables"]["value_crore"] = 4000.0
    payload["balance_sheet"]["payables"]["value_original"] = "4000.00"
    payload["profit_and_loss"]["cost_of_materials"]["value_crore"] = 300.0
    payload["profit_and_loss"]["cost_of_materials"]["value_original"] = "300.00"
    payload["profit_and_loss"]["cost_of_materials"]["source_line_item"] = "Cost of materials consumed"
    _write_json(normalized_path, payload)
    _write_json(reconciliation_path, _reconciliation_payload())

    report = calculate_financial_ratios(
        company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
    )

    assert report.ratios["payable_days"].value is None
    assert any("implausible working-capital days" in warning for warning in report.ratios["payable_days"].warnings)


def test_ratios_blocked_when_reconciliation_has_hard_failures(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(
        reconciliation_path,
        _reconciliation_payload(
            "fail",
            overrides={"revenue": {"status": "fail", "hard_failure": True, "reason": "revenue reconciliation failed"}},
        ),
    )

    with pytest.raises(RuntimeError, match="revenue reconciliation failed"):
        calculate_financial_ratios(
            company="acme", year="fy25", normalized_path=normalized_path, reconciliation_path=reconciliation_path
        )


def test_write_financial_ratios(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    reconciliation_path = tmp_path / "financial_reconciliation_report.json"
    output_path = tmp_path / "financial_ratios.json"
    _write_json(normalized_path, _normalized_payload())
    _write_json(reconciliation_path, _reconciliation_payload())

    report = write_financial_ratios(
        company="acme",
        year="fy25",
        normalized_path=normalized_path,
        reconciliation_path=reconciliation_path,
        output_path=output_path,
    )
    assert output_path.exists()
    written = json.loads(output_path.read_text())
    assert written["company"] == report.company
    assert isinstance(written["ratios"]["roe"]["inputs_used"], list)
    assert isinstance(written["ratios"]["roe"]["source_artifacts"], list)


def test_no_company_specific_behavior():
    text = Path("knowledge/financials/ratio_calculator.py").read_text(encoding="utf-8").lower()
    assert "datapatterns" not in text
    assert "polymatech" not in text
    assert "sun_pharma" not in text
    assert "tanla" not in text
    assert "tips" not in text
    assert "ujjivan" not in text
