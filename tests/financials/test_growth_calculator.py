from __future__ import annotations

import json
from pathlib import Path

from knowledge.financials.growth_calculator import calculate_financial_growth, write_financial_growth


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


def _normalized_payload(
    year: str,
    *,
    basis: str = "consolidated",
    revenue=500.0,
    ebitda=150.0,
    ebit=130.0,
    pat=100.0,
    eps_basic=10.0,
    eps_diluted=9.5,
    book_value=40.0,
    net_worth=400.0,
    reserves=320.0,
    debt=100.0,
    cfo=110.0,
    capex=-25.0,
    receivables=50.0,
    inventories=60.0,
    payables=30.0,
):
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
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "preferred_basis": basis,
        "basis_confidence": "high",
        "basis_manifest": {
            "preferred_basis": basis,
            "basis_options_available": [basis],
            "selected_basis_reason": "synthetic test payload",
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
        "basis_views": {},
        "unmapped_rows": [],
        "warnings": [],
        "limitations": [],
    }

    payload["profit_and_loss"]["revenue"] = _entry("revenue", value_crore=revenue, value_original=f"{revenue:.2f}", basis=basis)
    payload["profit_and_loss"]["other_income"] = _entry("other_income", value_crore=20.0, value_original="20.00", basis=basis)
    payload["profit_and_loss"]["total_income"] = _entry("total_income", value_crore=revenue + 20.0, value_original=f"{revenue + 20.0:.2f}", basis=basis)
    payload["profit_and_loss"]["cost_of_materials"] = _entry("cost_of_materials", value_crore=200.0, value_original="200.00", basis=basis)
    payload["profit_and_loss"]["ebitda"] = _entry("ebitda", value_crore=ebitda, value_original=f"{ebitda:.2f}", basis=basis)
    payload["profit_and_loss"]["ebit"] = _entry("ebit", value_crore=ebit, value_original=f"{ebit:.2f}", basis=basis)
    payload["profit_and_loss"]["pat"] = _entry("pat", value_crore=pat, value_original=f"{pat:.2f}", basis=basis)
    payload["profit_and_loss"]["eps_basic"] = _entry("eps_basic", value_crore=None, value_original=f"{eps_basic:.2f}", unit_original="inr", basis=basis)
    payload["profit_and_loss"]["eps_diluted"] = _entry("eps_diluted", value_crore=None, value_original=f"{eps_diluted:.2f}", unit_original="inr", basis=basis)

    payload["balance_sheet"]["net_worth"] = _entry("net_worth", value_crore=net_worth, value_original=f"{net_worth:.2f}", basis=basis)
    payload["balance_sheet"]["reserves"] = _entry("reserves", value_crore=reserves, value_original=f"{reserves:.2f}", basis=basis)
    payload["balance_sheet"]["total_debt"] = _entry("total_debt", value_crore=debt, value_original=f"{debt:.2f}", basis=basis)
    payload["balance_sheet"]["receivables"] = _entry("receivables", value_crore=receivables, value_original=f"{receivables:.2f}", basis=basis)
    payload["balance_sheet"]["inventories"] = _entry("inventories", value_crore=inventories, value_original=f"{inventories:.2f}", basis=basis)
    payload["balance_sheet"]["payables"] = _entry("payables", value_crore=payables, value_original=f"{payables:.2f}", basis=basis)

    payload["cash_flow"]["cfo"] = _entry("cfo", value_crore=cfo, value_original=f"{cfo:.2f}", basis=basis)
    payload["cash_flow"]["capex"] = _entry("capex", value_crore=capex, value_original=f"{capex:.2f}", basis=basis)
    payload["cash_flow"]["fcf"] = _entry("fcf", value_crore=cfo + capex, value_original=f"{cfo + capex:.2f}", basis=basis)

    payload["share_data"]["book_value_per_share"] = _entry(
        "book_value_per_share", value_crore=None, value_original=f"{book_value:.2f}", unit_original="inr", basis=basis
    )
    return payload


def _ratio_payload(year: str, *, gross_margin=50.0, ebitda_margin=30.0, ebit_margin=26.0, opm=26.0, npm=20.0):
    def _ratio(name, value):
        return {
            "ratio_name": name,
            "value": value,
            "unit": "%",
            "formula": "synthetic",
            "inputs_used": [],
            "basis": "consolidated",
            "confidence": "high",
            "warnings": [],
            "source_artifacts": ["normalized_source.json"],
        }

    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "pass",
        "basis_used": "consolidated",
        "warnings": [],
        "limitations": [],
        "ratios": {
            "gross_margin": _ratio("gross_margin", gross_margin),
            "ebitda_margin": _ratio("ebitda_margin", ebitda_margin),
            "ebit_margin": _ratio("ebit_margin", ebit_margin),
            "opm": _ratio("opm", opm),
            "npm": _ratio("npm", npm),
        },
    }


def _reconciliation_payload(year: str, status="pass", *, overrides=None):
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
            "revenue",
            "ebitda",
            "ebit",
            "pat",
            "eps_basic",
            "eps_diluted",
            "net_worth",
            "total_assets",
            "total_debt",
            "receivables",
            "inventories",
            "payables",
            "cfo",
            "capex",
            "shares_outstanding",
            "weighted_avg_shares",
            "diluted_shares",
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
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": status,
        "checks": checks,
        "hard_failures": hard_failures,
        "warnings": [],
        "limitations": [],
    }


def _write_year(tmp_path: Path, year: str, normalized_payload: dict, ratio_payload: dict | None = None, reconciliation_payload: dict | None = None):
    year_dir = tmp_path / "companies" / "acme" / year / "financials"
    _write_json(year_dir / "normalized_fundamentals.json", normalized_payload)
    _write_json(
        year_dir / "financial_reconciliation_report.json",
        reconciliation_payload if reconciliation_payload is not None else _reconciliation_payload(year),
    )
    if ratio_payload is not None:
        _write_json(year_dir / "financial_ratios.json", ratio_payload)
    return year_dir


def test_revenue_yoy_growth(tmp_path):
    _write_year(tmp_path, "fy24", _normalized_payload("fy24", revenue=400.0), _ratio_payload("fy24"))
    current_dir = _write_year(tmp_path, "fy25", _normalized_payload("fy25", revenue=500.0), _ratio_payload("fy25"))

    report = calculate_financial_growth(
        company="acme",
        year="fy25",
        normalized_path=current_dir / "normalized_fundamentals.json",
        reconciliation_path=current_dir / "financial_reconciliation_report.json",
        ratios_path=current_dir / "financial_ratios.json",
    )
    assert report.growth_metrics["revenue"].absolute_change == 100.0
    assert report.growth_metrics["revenue"].growth_percent == 25.0


def test_pat_yoy_growth(tmp_path):
    _write_year(tmp_path, "fy24", _normalized_payload("fy24", pat=80.0), _ratio_payload("fy24"))
    current_dir = _write_year(tmp_path, "fy25", _normalized_payload("fy25", pat=100.0), _ratio_payload("fy25"))

    report = calculate_financial_growth(
        company="acme",
        year="fy25",
        normalized_path=current_dir / "normalized_fundamentals.json",
        reconciliation_path=current_dir / "financial_reconciliation_report.json",
        ratios_path=current_dir / "financial_ratios.json",
    )
    assert report.growth_metrics["pat"].growth_percent == 25.0


def test_eps_and_book_value_growth(tmp_path):
    _write_year(tmp_path, "fy24", _normalized_payload("fy24", eps_basic=8.0, book_value=32.0), _ratio_payload("fy24"))
    current_dir = _write_year(tmp_path, "fy25", _normalized_payload("fy25", eps_basic=10.0, book_value=40.0), _ratio_payload("fy25"))

    report = calculate_financial_growth(
        company="acme",
        year="fy25",
        normalized_path=current_dir / "normalized_fundamentals.json",
        reconciliation_path=current_dir / "financial_reconciliation_report.json",
        ratios_path=current_dir / "financial_ratios.json",
    )
    assert report.growth_metrics["eps_basic"].growth_percent == 25.0
    assert report.growth_metrics["book_value_per_share"].growth_percent == 25.0


def test_payables_growth(tmp_path):
    _write_year(tmp_path, "fy24", _normalized_payload("fy24", payables=24.0), _ratio_payload("fy24"))
    current_dir = _write_year(tmp_path, "fy25", _normalized_payload("fy25", payables=30.0), _ratio_payload("fy25"))

    report = calculate_financial_growth(
        company="acme",
        year="fy25",
        normalized_path=current_dir / "normalized_fundamentals.json",
        reconciliation_path=current_dir / "financial_reconciliation_report.json",
        ratios_path=current_dir / "financial_ratios.json",
    )

    assert report.growth_metrics["payables"].absolute_change == 6.0
    assert report.growth_metrics["payables"].growth_percent == 25.0


def test_margin_expansion(tmp_path):
    _write_year(tmp_path, "fy24", _normalized_payload("fy24"), _ratio_payload("fy24", npm=18.0))
    current_dir = _write_year(tmp_path, "fy25", _normalized_payload("fy25"), _ratio_payload("fy25", npm=20.0))

    report = calculate_financial_growth(
        company="acme",
        year="fy25",
        normalized_path=current_dir / "normalized_fundamentals.json",
        reconciliation_path=current_dir / "financial_reconciliation_report.json",
        ratios_path=current_dir / "financial_ratios.json",
    )
    assert report.margin_changes["npm"].absolute_change == 2.0


def test_cagr_calculation(tmp_path):
    _write_year(tmp_path, "fy23", _normalized_payload("fy23", revenue=320.0), _ratio_payload("fy23"))
    _write_year(tmp_path, "fy24", _normalized_payload("fy24", revenue=400.0), _ratio_payload("fy24"))
    current_dir = _write_year(tmp_path, "fy25", _normalized_payload("fy25", revenue=500.0), _ratio_payload("fy25"))

    report = calculate_financial_growth(
        company="acme",
        year="fy25",
        normalized_path=current_dir / "normalized_fundamentals.json",
        reconciliation_path=current_dir / "financial_reconciliation_report.json",
        ratios_path=current_dir / "financial_ratios.json",
    )
    assert round(report.growth_metrics["revenue"].cagr_percent, 4) == 25.0


def test_zero_base_handling(tmp_path):
    _write_year(tmp_path, "fy24", _normalized_payload("fy24", revenue=0.0), _ratio_payload("fy24"))
    current_dir = _write_year(tmp_path, "fy25", _normalized_payload("fy25", revenue=500.0), _ratio_payload("fy25"))

    report = calculate_financial_growth(
        company="acme",
        year="fy25",
        normalized_path=current_dir / "normalized_fundamentals.json",
        reconciliation_path=current_dir / "financial_reconciliation_report.json",
        ratios_path=current_dir / "financial_ratios.json",
    )
    assert report.growth_metrics["revenue"].growth_percent is None
    assert "base value zero" in report.growth_metrics["revenue"].warnings


def test_missing_previous_year_warning(tmp_path):
    current_dir = _write_year(tmp_path, "fy25", _normalized_payload("fy25"), _ratio_payload("fy25"))

    report = calculate_financial_growth(
        company="acme",
        year="fy25",
        normalized_path=current_dir / "normalized_fundamentals.json",
        reconciliation_path=current_dir / "financial_reconciliation_report.json",
        ratios_path=current_dir / "financial_ratios.json",
    )
    assert "previous-year data missing" in report.growth_metrics["revenue"].warnings


def test_basis_mismatch_warning(tmp_path):
    _write_year(tmp_path, "fy24", _normalized_payload("fy24", basis="standalone"), _ratio_payload("fy24"))
    current_dir = _write_year(tmp_path, "fy25", _normalized_payload("fy25", basis="consolidated"), _ratio_payload("fy25"))

    report = calculate_financial_growth(
        company="acme",
        year="fy25",
        normalized_path=current_dir / "normalized_fundamentals.json",
        reconciliation_path=current_dir / "financial_reconciliation_report.json",
        ratios_path=current_dir / "financial_ratios.json",
    )
    assert "basis mismatch across years" in report.growth_metrics["revenue"].warnings


def test_growth_report_carries_basis_context(tmp_path):
    _write_year(tmp_path, "fy24", _normalized_payload("fy24"), _ratio_payload("fy24"))
    current_payload = _normalized_payload("fy25")
    current_payload["basis_confidence"] = "medium"
    current_payload["basis_manifest"]["basis_warnings"] = [
        "profit_and_loss.revenue fell back to unknown basis because preferred consolidated evidence was unavailable"
    ]
    current_dir = _write_year(tmp_path, "fy25", current_payload, _ratio_payload("fy25"))

    report = calculate_financial_growth(
        company="acme",
        year="fy25",
        normalized_path=current_dir / "normalized_fundamentals.json",
        reconciliation_path=current_dir / "financial_reconciliation_report.json",
        ratios_path=current_dir / "financial_ratios.json",
    )

    assert report.basis_used == "consolidated"
    assert report.basis_confidence == "medium"
    assert report.basis_warnings == current_payload["basis_manifest"]["basis_warnings"]


def test_write_financial_growth(tmp_path):
    _write_year(tmp_path, "fy24", _normalized_payload("fy24"), _ratio_payload("fy24"))
    current_dir = _write_year(tmp_path, "fy25", _normalized_payload("fy25"), _ratio_payload("fy25"))
    output_path = current_dir / "financial_growth.json"

    report = write_financial_growth(
        company="acme",
        year="fy25",
        normalized_path=current_dir / "normalized_fundamentals.json",
        reconciliation_path=current_dir / "financial_reconciliation_report.json",
        ratios_path=current_dir / "financial_ratios.json",
        output_path=output_path,
    )
    assert output_path.exists()
    written = json.loads(output_path.read_text())
    assert written["company"] == report.company


def test_growth_blocked_when_reconciliation_has_hard_failures(tmp_path):
    current_dir = _write_year(
        tmp_path,
        "fy25",
        _normalized_payload("fy25"),
        _ratio_payload("fy25"),
        _reconciliation_payload(
            "fy25",
            "fail",
            overrides={"revenue": {"status": "fail", "hard_failure": True, "reason": "revenue reconciliation failed"}},
        ),
    )

    try:
        calculate_financial_growth(
            company="acme",
            year="fy25",
            normalized_path=current_dir / "normalized_fundamentals.json",
            reconciliation_path=current_dir / "financial_reconciliation_report.json",
            ratios_path=current_dir / "financial_ratios.json",
        )
    except RuntimeError as exc:
        assert "revenue reconciliation failed" in str(exc)
    else:
        raise AssertionError("Expected reconciliation hard failure to block growth calculation")


def test_no_company_specific_behavior():
    text = Path("knowledge/financials/growth_calculator.py").read_text(encoding="utf-8").lower()
    assert "datapatterns" not in text
    assert "polymatech" not in text
    assert "tanla" not in text
    assert "tips" not in text
