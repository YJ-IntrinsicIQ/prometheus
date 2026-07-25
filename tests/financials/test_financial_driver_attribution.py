from __future__ import annotations

import json
from pathlib import Path

from knowledge.financials.driver_attribution import (
    build_financial_driver_attribution,
    write_financial_driver_attribution,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _series(points):
    return [
        {
            "year": year,
            "value": value,
            "basis": "consolidated",
            "source_artifact": "financial_ratios.json",
            "confidence": "high",
            "warnings": [],
        }
        for year, value in points
    ]


def _growth_points(points):
    return [
        {
            "year": year,
            "growth_percent": growth_percent,
            "cagr_percent": growth_percent,
            "absolute_change": absolute_change,
            "basis": "consolidated",
            "source_artifact": "financial_growth.json",
            "confidence": "high",
            "warnings": [],
        }
        for year, growth_percent, absolute_change in points
    ]


def _trends_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy24", "fy25"],
        "basis": "consolidated",
        "metric_trends": {
            "revenue": {"metric": "revenue", "unit": "₹ crore", "series": _series([("fy24", 100.0), ("fy25", 125.0)]), "comparability_warnings": []},
            "pat": {"metric": "pat", "unit": "₹ crore", "series": _series([("fy24", 10.0), ("fy25", 11.0)]), "comparability_warnings": []},
        },
        "growth_summary": {
            "revenue": _growth_points([("fy25", 25.0, 25.0)]),
            "pat": _growth_points([("fy25", 20.0, 2.0)]),
            "eps_basic": _growth_points([("fy25", 2.0, 0.1)]),
            "book_value_per_share": _growth_points([("fy25", 8.0, 1.0)]),
        },
        "margin_trends": {
            "opm": {"metric": "opm", "unit": "%", "series": _series([("fy24", 18.0), ("fy25", 15.0)]), "comparability_warnings": []},
        },
        "return_trends": {
            "roe": {"metric": "roe", "unit": "%", "series": _series([("fy24", 15.0), ("fy25", 10.0)]), "comparability_warnings": []},
            "roce": {"metric": "roce", "unit": "%", "series": _series([("fy24", 20.0), ("fy25", 16.0)]), "comparability_warnings": []},
        },
        "cash_conversion_trends": {
            "cfo_to_pat": {"metric": "cfo_to_pat", "unit": "%", "series": _series([("fy24", 105.0), ("fy25", 65.0)]), "comparability_warnings": []},
            "fcf": {"metric": "fcf", "unit": "₹ crore", "series": _series([("fy24", 5.0), ("fy25", -4.0)]), "comparability_warnings": []},
            "receivables": {"metric": "receivables", "unit": "₹ crore", "series": _series([("fy24", 20.0), ("fy25", 50.0)]), "comparability_warnings": []},
            "inventory": {"metric": "inventory", "unit": "₹ crore", "series": _series([("fy24", 8.0), ("fy25", 12.0)]), "comparability_warnings": []},
            "receivable_days": {"metric": "receivable_days", "unit": "days", "series": _series([("fy24", 45.0), ("fy25", 60.0)]), "comparability_warnings": []},
        },
        "balance_sheet_trends": {
            "total_debt": {"metric": "total_debt", "unit": "₹ crore", "series": _series([("fy24", 15.0), ("fy25", 30.0)]), "comparability_warnings": []},
        },
        "per_share_trends": {
            "share_count": {"metric": "share_count", "unit": "shares", "series": _series([("fy24", 100.0), ("fy25", 130.0)]), "comparability_warnings": []},
        },
        "ownership_trends": {},
        "corporate_actions_timeline": [
            {"action_type": "qip", "year": "fy25", "source_artifact": "financial_trends.json", "confidence": "high", "evidence_ids": ["ev_qip_1"]},
            {"action_type": "stock_split", "year": "fy25", "source_artifact": "financial_trends.json", "confidence": "high", "evidence_ids": ["ev_split_1"]},
        ],
        "warnings": [],
        "limitations": [],
    }


def _quality_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy24", "fy25"],
        "status": "warning",
        "overall_financial_quality": "mixed",
        "growth_quality": {"status": "mixed", "summary": "", "signals": [], "warnings": [], "metrics": {}},
        "margin_quality": {"status": "weak", "summary": "", "signals": [], "warnings": [], "metrics": {}},
        "return_on_capital_quality": {"status": "weak", "summary": "", "signals": [], "warnings": [], "metrics": {}},
        "cash_conversion_quality": {"status": "weak", "summary": "", "signals": [], "warnings": [], "metrics": {}},
        "balance_sheet_strength": {"status": "mixed", "summary": "", "signals": [], "warnings": [], "metrics": {}},
        "working_capital_quality": {"status": "weak", "summary": "", "signals": [], "warnings": [], "metrics": {}},
        "dilution_and_corporate_action_quality": {"status": "weak", "summary": "", "signals": [], "warnings": [], "metrics": {}},
        "ownership_quality": {"status": "insufficient_data", "summary": "", "signals": [], "warnings": [], "metrics": {}},
        "red_flags": ["Receivables are growing faster than revenue.", "Per-share growth is lagging absolute profit growth."],
        "positive_signals": [],
        "missing_data": [],
        "warnings": ["receivables growth is outpacing revenue growth"],
        "limitations": [],
    }


def _strategy_payload():
    return {
        "company": "acme",
        "timeline": [
            {
                "year": "fy25",
                "management_focus": [{"value": "Large order execution ramp", "source_artifact": "management_summary.json", "evidence_ids": ["ev_exec_1"]}],
                "major_projects": [],
                "major_initiatives": [],
                "external_context": [],
                "strategic_themes": [],
                "evidence_ids": [],
            }
        ],
    }


def _capital_allocation_payload():
    return {
        "company": "acme",
        "timeline": [
            {
                "year": "fy25",
                "capex": [{"value": "Plant expansion program", "source_artifact": "company_intelligence.json", "evidence_ids": ["ev_capex_1"], "confidence": "high"}],
                "cwip": [],
                "acquisitions": [],
                "equity_issuance": [{"value": "QIP issuance", "source_artifact": "company_intelligence.json", "evidence_ids": ["ev_qip_ca_1"], "confidence": "high"}],
                "debt_borrowings": [{"value": "Project debt drawdown", "source_artifact": "company_intelligence.json", "evidence_ids": ["ev_debt_1"], "confidence": "high"}],
                "debt_repayments": [],
                "buybacks": [],
                "share_splits": [{"value": "stock_split", "source_artifact": "company_intelligence.json", "evidence_ids": ["ev_split_ca_1"], "confidence": "high"}],
                "dividends": [],
            }
        ],
    }


def _risk_payload():
    return {
        "company": "acme",
        "risks": [
            {
                "risk_id": "risk_customer_collection",
                "normalized_risk": "customer_collection_risk",
                "first_seen_year": "fy25",
                "related_evidence_ids": ["ev_risk_1"],
            }
        ],
    }


def _promise_payload():
    return {
        "company": "acme",
        "promises": [
            {
                "normalized_promise": "execute new order book",
                "first_seen_year": "fy25",
                "related_evidence_ids": ["ev_promise_1"],
                "source_mentions": [{"source_year": "fy25"}],
            }
        ],
    }


def _management_consistency_payload():
    return {
        "company": "acme",
        "consistency_observations": [
            {
                "theme": "capex_program",
                "years_active": ["fy24", "fy25"],
                "evidence_ids": ["ev_consistency_1"],
                "consistency_status": "consistent",
                "explanation": "Capex focus persisted.",
            }
        ],
    }


def _write_required_inputs(root: Path):
    company_root = root / "companies" / "acme"
    financial_root = company_root / "company_memory" / "financials"
    multi_year_root = company_root / "company_memory" / "multi_year"
    _write_json(financial_root / "financial_trends.json", _trends_payload())
    _write_json(financial_root / "financial_quality_summary.json", _quality_payload())
    _write_json(multi_year_root / "strategy_timeline.json", _strategy_payload())
    _write_json(multi_year_root / "capital_allocation_timeline.json", _capital_allocation_payload())
    _write_json(multi_year_root / "promise_tracker.json", _promise_payload())
    _write_json(multi_year_root / "risk_evolution.json", _risk_payload())
    _write_json(multi_year_root / "management_consistency.json", _management_consistency_payload())
    return company_root


def _find(report, metric):
    for item in report.attributions:
        if item.metric == metric:
            return item
    raise AssertionError(f"missing attribution for {metric}")


def test_qip_is_linked_to_roe_and_share_count_without_overclaiming(tmp_path: Path):
    company_root = _write_required_inputs(tmp_path)

    report = build_financial_driver_attribution(company="acme", company_root=company_root)

    roe_item = _find(report, "roe")
    share_count_item = _find(report, "share_count")
    assert roe_item.driver_type == "equity_raise"
    assert roe_item.causality_status == "possible"
    assert share_count_item.driver_type == "equity_raise"
    assert share_count_item.causality_status == "supported"


def test_capex_is_linked_to_roce_pressure_and_fcf_deterioration(tmp_path: Path):
    company_root = _write_required_inputs(tmp_path)

    report = build_financial_driver_attribution(company="acme", company_root=company_root)

    roce_item = _find(report, "roce")
    fcf_item = _find(report, "fcf")
    assert roce_item.driver_type in {"capex", "equity_raise", "debt"}
    assert "Possible driver" in roce_item.possible_driver
    assert fcf_item.driver_type == "capex"


def test_receivables_growth_is_linked_to_cash_conversion_warning(tmp_path: Path):
    company_root = _write_required_inputs(tmp_path)

    report = build_financial_driver_attribution(company="acme", company_root=company_root)

    receivables_item = _find(report, "receivables")
    cfo_pat_item = _find(report, "cfo_to_pat")
    assert receivables_item.driver_type == "working_capital"
    assert "cash conversion concern" in " ".join(receivables_item.warnings)
    assert cfo_pat_item.driver_type in {"working_capital", "risk", "order_execution"}


def test_split_is_linked_to_eps_comparability_warning(tmp_path: Path):
    company_root = _write_required_inputs(tmp_path)

    report = build_financial_driver_attribution(company="acme", company_root=company_root)

    eps_item = _find(report, "eps_basic")
    comparability_item = _find(report, "eps_comparability")
    assert eps_item.driver_type in {"equity_raise", "corporate_action"}
    assert comparability_item.causality_status == "supported"
    assert comparability_item.driver_type == "corporate_action"


def test_no_causation_is_overclaimed_for_receivables_or_revenue(tmp_path: Path):
    company_root = _write_required_inputs(tmp_path)

    report = build_financial_driver_attribution(company="acme", company_root=company_root)

    revenue_item = _find(report, "revenue")
    receivables_item = _find(report, "receivables")
    assert revenue_item.causality_status in {"possible", "weak"}
    assert receivables_item.causality_status in {"possible", "weak"}
    assert "Possible driver" in revenue_item.possible_driver or "requires verification" in revenue_item.possible_driver


def test_write_financial_driver_attribution_persists_output(tmp_path: Path):
    company_root = _write_required_inputs(tmp_path)
    output_path = company_root / "company_memory" / "financials" / "financial_driver_attribution.json"

    report = write_financial_driver_attribution(
        company="acme",
        company_root=company_root,
        output_path=output_path,
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert output_path.exists()
    assert saved["company"] == "acme"
    assert len(saved["attributions"]) == len(report.attributions)
