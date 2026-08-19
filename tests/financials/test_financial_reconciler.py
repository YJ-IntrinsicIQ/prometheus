from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge.financials.reconciler import (
    build_financial_reconciliation_report,
    reconciliation_blocks_stage,
    write_financial_reconciliation_report,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _entry(
    field: str,
    *,
    value_crore=1.0,
    value_original="1.00",
    section_type="primary_profit_and_loss_statement",
    statement_type="profit_and_loss",
    source_value_type="monetary",
):
    return {
        "canonical_field": field,
        "value_crore": value_crore,
        "value_original": value_original,
        "unit_original": "crores",
        "basis": "consolidated",
        "period": "FY25",
        "source_line_item": field.replace("_", " ").title(),
        "source_page": 10,
        "source_artifact": "annual_report.pdf",
        "confidence": "high",
        "warnings": [],
        "source_section_type": section_type,
        "statement_type": statement_type,
        "source_value_type": source_value_type,
    }


def _normalized_payload():
    payload = {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "preferred_basis": "consolidated",
        "basis_manifest": {
            "preferred_basis": "consolidated",
            "basis_options_available": ["consolidated"],
            "selected_basis_reason": "synthetic test payload",
            "basis_confidence": "high",
            "field_basis_selection": [],
            "basis_warnings": [],
        },
        "profit_and_loss": {
            "revenue": _entry("revenue"),
            "ebitda": _entry("ebitda"),
            "ebit": _entry("ebit"),
            "finance_cost": _entry("finance_cost"),
            "pat": _entry("pat"),
            "eps_basic": _entry(
                "eps_basic",
                value_crore=None,
                value_original="10.00",
                section_type="financial_note",
                statement_type="profit_and_loss",
                source_value_type="per_share",
            ),
            "eps_diluted": _entry(
                "eps_diluted",
                value_crore=None,
                value_original="9.50",
                section_type="financial_note",
                statement_type="profit_and_loss",
                source_value_type="per_share",
            ),
        },
        "balance_sheet": {
            "net_worth": _entry("net_worth", section_type="statement_of_changes_in_equity", statement_type="balance_sheet"),
            "total_assets": _entry("total_assets", section_type="primary_balance_sheet_statement", statement_type="balance_sheet"),
            "total_debt": _entry("total_debt", section_type="financial_note", statement_type="balance_sheet"),
            "cash_and_equivalents": _entry("cash_and_equivalents", section_type="primary_balance_sheet_statement", statement_type="balance_sheet"),
            "receivables": _entry("receivables", section_type="financial_note", statement_type="balance_sheet"),
            "inventories": _entry("inventories", section_type="financial_note", statement_type="balance_sheet"),
            "payables": _entry("payables", section_type="financial_note", statement_type="balance_sheet"),
        },
        "cash_flow": {
            "cfo": _entry("cfo", section_type="primary_cash_flow_statement", statement_type="cash_flow"),
            "capex": _entry("capex", section_type="financial_note", statement_type="cash_flow"),
            "fcf": _entry("fcf", section_type="financial_note", statement_type="cash_flow"),
            "dividends_paid": _entry("dividends_paid", section_type="financial_note", statement_type="cash_flow"),
        },
        "share_data": {
            "shares_outstanding": _entry(
                "shares_outstanding",
                value_crore=None,
                value_original="100000000",
                section_type="share_capital_note",
                statement_type="share_capital",
                source_value_type="share_count",
            ),
            "weighted_avg_shares": _entry(
                "weighted_avg_shares",
                value_crore=None,
                value_original="95000000",
                section_type="eps_note",
                statement_type="eps",
                source_value_type="share_count",
            ),
            "diluted_shares": _entry(
                "diluted_shares",
                value_crore=None,
                value_original="98000000",
                section_type="eps_note",
                statement_type="eps",
                source_value_type="share_count",
            ),
        },
    }
    return payload


def test_reconciler_passes_for_related_sources(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["profit_and_loss"]["revenue"]["source_line_item"] = "Revenue from operations"
    payload["profit_and_loss"]["ebitda"]["source_line_item"] = "EBITDA"
    payload["profit_and_loss"]["ebit"]["source_line_item"] = "Profit before finance costs and tax"
    payload["profit_and_loss"]["finance_cost"]["source_line_item"] = "Finance costs"
    payload["profit_and_loss"]["pat"]["source_line_item"] = "Profit for the year"
    payload["balance_sheet"]["net_worth"]["source_line_item"] = "Other Equity"
    payload["balance_sheet"]["total_assets"]["source_line_item"] = "Total Assets"
    payload["balance_sheet"]["total_debt"]["source_line_item"] = "Borrowings"
    payload["balance_sheet"]["cash_and_equivalents"]["source_line_item"] = "Cash and Cash Equivalents"
    payload["balance_sheet"]["receivables"]["source_line_item"] = "Trade Receivables"
    payload["balance_sheet"]["inventories"]["source_line_item"] = "Inventories"
    payload["balance_sheet"]["payables"]["source_line_item"] = "Trade Payables"
    payload["cash_flow"]["cfo"]["source_line_item"] = "Net cash generated from operating activities"
    payload["cash_flow"]["capex"]["source_line_item"] = "Purchase of property, plant and equipment"
    payload["cash_flow"]["fcf"] = {
        **payload["cash_flow"]["fcf"],
        "derived": True,
        "formula": "cfo + capex (or cfo - capex when capex sign is positive outflow)",
        "inputs_used": {"cfo": 1.0, "capex": -1.0},
        "source_line_item": "derived:fcf",
    }
    payload["cash_flow"]["dividends_paid"]["source_line_item"] = "Dividend paid"
    payload["share_data"]["shares_outstanding"].update(
        {
            "source_line_item": "Issued, subscribed and fully paid up Equity shares of Rs.2 each",
            "source_section_type": "share_capital_note",
            "statement_type": "share_data",
            "value_type": "share_count",
            "source_value_type": "share_count",
            "value_shares": 100_000_000.0,
            "raw_number": 100_000_000.0,
            "value_crore": None,
        }
    )
    payload["share_data"]["weighted_avg_shares"]["source_line_item"] = "Weighted average number of equity shares"
    payload["share_data"]["diluted_shares"]["source_line_item"] = "Diluted weighted average number of equity shares"
    payload["profit_and_loss"]["eps_basic"]["source_line_item"] = "Basic earnings per share"
    payload["profit_and_loss"]["eps_diluted"]["source_line_item"] = "Diluted earnings per share"
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.status == "warning"
    assert not report.hard_failures
    assert report.checks["fcf"].status == "warning"


def test_reconciler_accepts_note_based_revenue_and_eps(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["profit_and_loss"]["revenue"].update(
        {
            "source_line_item": "FY 2019-20 Revenue from Operations",
            "source_section_type": "financial_note",
            "statement_type": "revenue",
        }
    )
    payload["profit_and_loss"]["eps_basic"].update(
        {
            "source_line_item": "EPS (Basic) (`)",
            "source_section_type": "financial_note",
            "statement_type": "eps",
            "source_value_type": "per_share",
        }
    )
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["revenue"].status == "pass"
    assert report.checks["eps_basic"].status == "pass"
    assert not any("revenue" in failure for failure in report.hard_failures)
    assert not any("eps_basic" in failure for failure in report.hard_failures)


def test_reconciler_fails_for_disallowed_source_on_critical_field(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["profit_and_loss"]["revenue"]["source_section_type"] = "management_discussion_financial_summary"
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.status == "fail"
    assert any("revenue" in failure for failure in report.hard_failures)


def test_reconciler_fails_for_share_count_value_type_mismatch(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"]["source_value_type"] = "monetary"
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.status == "fail"
    assert any("shares_outstanding" in failure for failure in report.hard_failures)


def test_reconciler_warns_when_shares_outstanding_is_missing(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"]["value_original"] = ""
    payload["share_data"]["shares_outstanding"]["value_crore"] = None
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["shares_outstanding"].status == "warning"
    assert not any("shares_outstanding" in failure for failure in report.hard_failures)


def test_reconciler_passes_for_issued_subscribed_fully_paid_shares_outstanding(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"].update(
        {
            "source_line_item": "Issued, subscribed and fully paid up Equity shares of Rs.2 each",
            "source_section_type": "share_capital_note",
            "statement_type": "share_data",
            "source_value_type": "share_count",
            "value_type": "share_count",
            "value_shares": 55_983_969.0,
            "raw_number": 55_983_969.0,
            "value_crore": None,
            "basis": "unknown",
        }
    )
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["shares_outstanding"].status in {"pass", "warning"}
    assert not any("shares_outstanding" in failure for failure in report.hard_failures)


def test_reconciler_passes_for_paid_up_equity_shares_outstanding(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"].update(
        {
            "source_line_item": "Paid up equity shares",
            "source_section_type": "share_capital_note",
            "statement_type": "share_data",
            "source_value_type": "share_count",
            "value_type": "share_count",
            "value_shares": 100_000_000.0,
            "raw_number": 100_000_000.0,
            "value_crore": None,
        }
    )
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["shares_outstanding"].status == "pass"
    assert not any("shares_outstanding" in failure for failure in report.hard_failures)


def test_reconciler_passes_for_end_of_period_share_count(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"].update(
        {
            "value_original": "51886650",
            "value_type": "share_count",
            "value_shares": 51886650.0,
            "raw_number": 51886650.0,
            "value_crore": None,
            "source_line_item": "Number of shares outstanding at the end of the period",
            "source_section_type": "share_capital_note",
            "statement_type": "share_capital_note",
            "source_value_type": "share_count",
        }
    )
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(
        company="acme", year="fy25", normalized_path=normalized_path
    )

    assert report.checks["shares_outstanding"].status == "pass"
    assert not any("shares_outstanding" in failure for failure in report.hard_failures)


def test_reconciler_passes_for_outstanding_equity_shares(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"].update(
        {
            "source_line_item": "Outstanding equity shares",
            "source_section_type": "notes_to_accounts",
            "statement_type": "notes_to_accounts",
            "source_value_type": "share_count",
            "value_type": "share_count",
            "value_shares": 100_000_000.0,
            "raw_number": 100_000_000.0,
            "value_crore": None,
        }
    )
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["shares_outstanding"].status == "pass"
    assert not any("shares_outstanding" in failure for failure in report.hard_failures)


def test_reconciler_fails_on_silent_critical_basis_mixing(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["cash_flow"]["capex"]["source_line_item"] = "Purchase of property, plant and equipment"
    payload["cash_flow"]["fcf"] = {
        **payload["cash_flow"]["fcf"],
        "derived": True,
        "formula": "cfo + capex (or cfo - capex when capex sign is positive outflow)",
        "inputs_used": {"cfo": 1.0, "capex": -1.0},
        "source_line_item": "derived:fcf",
    }
    payload["balance_sheet"]["total_assets"]["basis"] = "standalone"
    payload["basis_manifest"]["basis_warnings"] = []
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.status == "fail"
    assert any("mix standalone and consolidated basis" in failure for failure in report.hard_failures)


def test_reconciler_warns_when_fcf_is_missing_due_to_missing_capex(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["cash_flow"]["fcf"]["value_original"] = ""
    payload["cash_flow"]["fcf"]["value_crore"] = None
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["fcf"].status == "warning"
    assert not any("fcf" in failure for failure in report.hard_failures)


def test_reconciler_warns_when_capex_is_missing(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["cash_flow"]["capex"]["value_original"] = ""
    payload["cash_flow"]["capex"]["value_crore"] = None
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["capex"].status == "warning"
    assert not any("capex" in failure for failure in report.hard_failures)


def test_reconciler_fails_when_capex_uses_balance_row(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["cash_flow"]["capex"]["source_line_item"] = "Property, plant and equipment - closing balance"
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["capex"].status == "fail"
    assert any("capex" in failure for failure in report.hard_failures)


def test_reconciler_fails_when_fcf_uses_heading_text(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["cash_flow"]["fcf"]["source_line_item"] = "Cash Flow Statement for the year ended March 31, 2025"
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["fcf"].status == "fail"
    assert any("fcf" in failure for failure in report.hard_failures)


def test_reconciler_fails_when_shares_outstanding_comes_from_authorised_share_capital(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"]["source_line_item"] = "Authorised Equity shares of Rs.2 each"
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["shares_outstanding"].status == "fail"
    assert any("shares_outstanding" in failure for failure in report.hard_failures)


def test_reconciler_fails_when_shares_outstanding_is_monetary_not_share_count(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"].update(
        {
            "source_line_item": "Issued, subscribed and fully paid up Equity shares",
            "source_value_type": "monetary",
            "value_type": "monetary",
            "value_crore": 15.75,
            "value_shares": None,
            "raw_number": None,
        }
    )
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["shares_outstanding"].status == "fail"
    assert any("shares_outstanding" in failure for failure in report.hard_failures)


def test_reconciler_fails_when_shares_outstanding_uses_securities_premium_row(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"].update(
        {
            "source_line_item": "Securities premium",
            "source_value_type": "share_count",
            "value_type": "share_count",
            "value_shares": 100_000_000.0,
            "raw_number": 100_000_000.0,
            "value_crore": None,
        }
    )
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["shares_outstanding"].status == "fail"
    assert any("shares_outstanding" in failure for failure in report.hard_failures)


def test_reconciler_fails_when_shares_outstanding_uses_dividend_row(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"].update(
        {
            "source_line_item": "Dividend paid",
            "source_value_type": "share_count",
            "value_type": "share_count",
            "value_shares": 100_000_000.0,
            "raw_number": 100_000_000.0,
            "value_crore": None,
        }
    )
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["shares_outstanding"].status == "fail"
    assert any("shares_outstanding" in failure for failure in report.hard_failures)


def test_reconciler_fails_when_shares_outstanding_uses_qip_proceeds_row(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["share_data"]["shares_outstanding"].update(
        {
            "source_line_item": "QIP proceeds utilisation",
            "source_value_type": "share_count",
            "value_type": "share_count",
            "value_shares": 100_000_000.0,
            "raw_number": 100_000_000.0,
            "value_crore": None,
        }
    )
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["shares_outstanding"].status == "fail"
    assert any("shares_outstanding" in failure for failure in report.hard_failures)


def test_reconciler_passes_for_derived_trade_payables(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["balance_sheet"]["payables"] = {
        **payload["balance_sheet"]["payables"],
        "value_crore": 50.11,
        "value_original": "50.11",
        "derived": True,
        "formula": "msme_trade_payables + other_trade_payables",
        "inputs_used": {
            "msme_trade_payables": 2.84,
            "other_trade_payables": 47.27,
        },
        "source_line_item": "derived:trade_payables",
    }
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["payables"].status == "pass"
    assert not any("payables" in failure for failure in report.hard_failures)


def test_reconciler_fails_when_payables_uses_generic_liabilities(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    payload = _normalized_payload()
    payload["balance_sheet"]["payables"]["source_line_item"] = "Other current liabilities"
    _write_json(normalized_path, payload)

    report = build_financial_reconciliation_report(company="acme", year="fy25", normalized_path=normalized_path)

    assert report.checks["payables"].status == "fail"
    assert not any("payables" in failure for failure in report.hard_failures)


def test_reconciliation_gate_blocks_only_hard_failures():
    payload = {
        "status": "warning",
        "checks": {
            "revenue": {"status": "pass", "hard_failure": False, "reason": "ok"},
            "pat": {"status": "pass", "hard_failure": False, "reason": "ok"},
            "total_assets": {"status": "pass", "hard_failure": False, "reason": "ok"},
        },
    }
    assert reconciliation_blocks_stage(payload, required_fields=["revenue", "pat", "total_assets"]) == []

    payload["checks"]["revenue"] = {"status": "fail", "hard_failure": True, "reason": "revenue reconciliation failed"}
    failures = reconciliation_blocks_stage(payload, required_fields=["revenue", "pat", "total_assets"])
    assert failures == ["revenue: revenue reconciliation failed"]


def test_write_financial_reconciliation_report(tmp_path):
    normalized_path = tmp_path / "normalized_fundamentals.json"
    output_path = tmp_path / "financial_reconciliation_report.json"
    payload = _normalized_payload()
    payload["profit_and_loss"]["revenue"]["source_line_item"] = "Revenue from operations"
    payload["profit_and_loss"]["ebitda"]["source_line_item"] = "EBITDA"
    payload["profit_and_loss"]["ebit"]["source_line_item"] = "Profit before finance costs and tax"
    payload["profit_and_loss"]["finance_cost"]["source_line_item"] = "Finance costs"
    payload["profit_and_loss"]["pat"]["source_line_item"] = "Profit for the year"
    payload["balance_sheet"]["net_worth"]["source_line_item"] = "Other Equity"
    payload["balance_sheet"]["total_assets"]["source_line_item"] = "Total Assets"
    payload["balance_sheet"]["total_debt"]["source_line_item"] = "Borrowings"
    payload["balance_sheet"]["cash_and_equivalents"]["source_line_item"] = "Cash and Cash Equivalents"
    payload["balance_sheet"]["receivables"]["source_line_item"] = "Trade Receivables"
    payload["balance_sheet"]["inventories"]["source_line_item"] = "Inventories"
    payload["balance_sheet"]["payables"]["source_line_item"] = "Trade Payables"
    payload["cash_flow"]["cfo"]["source_line_item"] = "Net cash generated from operating activities"
    payload["cash_flow"]["capex"]["source_line_item"] = "Purchase of property, plant and equipment"
    payload["cash_flow"]["dividends_paid"]["source_line_item"] = "Dividend paid"
    payload["share_data"]["shares_outstanding"].update(
        {
            "source_line_item": "Issued, subscribed and fully paid up Equity shares of Rs.2 each",
            "source_section_type": "share_capital_note",
            "statement_type": "share_data",
            "value_type": "share_count",
            "source_value_type": "share_count",
            "value_shares": 100_000_000.0,
            "raw_number": 100_000_000.0,
            "value_crore": None,
        }
    )
    payload["share_data"]["weighted_avg_shares"]["source_line_item"] = "Weighted average number of equity shares"
    payload["share_data"]["diluted_shares"]["source_line_item"] = "Diluted weighted average number of equity shares"
    payload["profit_and_loss"]["eps_basic"]["source_line_item"] = "Basic earnings per share"
    payload["profit_and_loss"]["eps_diluted"]["source_line_item"] = "Diluted earnings per share"
    _write_json(normalized_path, payload)

    report = write_financial_reconciliation_report(
        company="acme",
        year="fy25",
        normalized_path=normalized_path,
        output_path=output_path,
    )

    assert output_path.exists()
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["company"] == report.company
    assert written["status"] == "warning"


def test_no_company_specific_behavior():
    text = Path("knowledge/financials/reconciler.py").read_text(encoding="utf-8").lower()
    assert "datapatterns" not in text
    assert "polymatech" not in text
    assert "tanla" not in text
    assert "tips" not in text
