from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge.company_year_eligibility import (
    ELIGIBLE,
    INELIGIBLE,
    PARTIAL,
    build_company_year_eligibility_manifest,
)
from knowledge.financials.trend_builder import build_financial_trends, write_financial_trends


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _normalized_entry(field: str, value_crore=None, value_original="", basis="consolidated"):
    return {
        "canonical_field": field,
        "value_crore": value_crore,
        "value_original": value_original,
        "unit_original": "crores" if value_crore is not None else "",
        "basis": basis,
        "period": "March 31",
        "source_line_item": field,
        "source_page": 1,
        "source_artifact": "normalized_fundamentals.json",
        "confidence": "high",
        "warnings": [],
    }


def _normalized_payload(year: str, *, revenue: float, ebitda: float, ebit: float, pat: float, assets: float, net_worth: float, debt: float, cash: float, reserves: float, cfo: float, capex: float, receivables: float, inventory: float, payables: float, share_count: float = 10000000.0, basis: str = "consolidated"):
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "preferred_basis": basis,
        "profit_and_loss": {
            "revenue": _normalized_entry("revenue", value_crore=revenue, basis=basis),
            "ebitda": _normalized_entry("ebitda", value_crore=ebitda, basis=basis),
            "ebit": _normalized_entry("ebit", value_crore=ebit, basis=basis),
            "pat": _normalized_entry("pat", value_crore=pat, basis=basis),
        },
        "balance_sheet": {
            "total_assets": _normalized_entry("total_assets", value_crore=assets, basis=basis),
            "net_worth": _normalized_entry("net_worth", value_crore=net_worth, basis=basis),
            "total_debt": _normalized_entry("total_debt", value_crore=debt, basis=basis),
            "cash_and_equivalents": _normalized_entry("cash_and_equivalents", value_crore=cash, basis=basis),
            "reserves": _normalized_entry("reserves", value_crore=reserves, basis=basis),
            "receivables": _normalized_entry("receivables", value_crore=receivables, basis=basis),
            "inventories": _normalized_entry("inventories", value_crore=inventory, basis=basis),
            "payables": _normalized_entry("payables", value_crore=payables, basis=basis),
        },
        "cash_flow": {
            "cfo": _normalized_entry("cfo", value_crore=cfo, basis=basis),
            "capex": _normalized_entry("capex", value_crore=capex, basis=basis),
        },
        "share_data": {
            "shares_outstanding": _normalized_entry("shares_outstanding", value_original=str(share_count), basis=basis),
        },
        "shareholding_pattern": {},
        "warnings": [],
        "limitations": [],
    }


def _ratio_item(name: str, value, unit="%", basis="consolidated", warnings=None):
    return {
        "ratio_name": name,
        "value": value,
        "unit": unit,
        "formula": name,
        "inputs_used": {},
        "basis": basis,
        "confidence": "high" if value is not None else "missing",
        "warnings": list(warnings or []),
    }


def _ratio_payload(year: str, *, opm, ebitda_margin, npm, roe, roce, roa, net_debt, debt_to_equity, cfo_to_pat, fcf, fcf_to_pat, receivable_days, inventory_days, payable_days, ccc, eps_basic, eps_diluted, book_value_per_share, dividend_per_share, payout_ratio, basis="consolidated"):
    ratios = {name: _ratio_item(name, None, unit="x", basis=basis) for name in (
        "gross_margin","ebitda_margin","ebit_margin","opm","npm","roe","roce","roa","debt_to_equity","net_debt","net_debt_to_equity","interest_coverage","cfo_to_pat","fcf","fcf_to_pat","fcf_margin","receivable_days","inventory_days","payable_days","cash_conversion_cycle","eps_basic","eps_diluted","book_value_per_share","tangible_book_value_per_share","dividend_per_share","payout_ratio"
    )}
    ratios.update({
        "opm": _ratio_item("opm", opm, "%", basis),
        "ebitda_margin": _ratio_item("ebitda_margin", ebitda_margin, "%", basis),
        "npm": _ratio_item("npm", npm, "%", basis),
        "roe": _ratio_item("roe", roe, "%", basis),
        "roce": _ratio_item("roce", roce, "%", basis),
        "roa": _ratio_item("roa", roa, "%", basis),
        "net_debt": _ratio_item("net_debt", net_debt, "₹ crore", basis),
        "debt_to_equity": _ratio_item("debt_to_equity", debt_to_equity, "%", basis),
        "cfo_to_pat": _ratio_item("cfo_to_pat", cfo_to_pat, "%", basis),
        "fcf": _ratio_item("fcf", fcf, "₹ crore", basis),
        "fcf_to_pat": _ratio_item("fcf_to_pat", fcf_to_pat, "%", basis),
        "receivable_days": _ratio_item("receivable_days", receivable_days, "days", basis),
        "inventory_days": _ratio_item("inventory_days", inventory_days, "days", basis),
        "payable_days": _ratio_item("payable_days", payable_days, "days", basis),
        "cash_conversion_cycle": _ratio_item("cash_conversion_cycle", ccc, "days", basis),
        "eps_basic": _ratio_item("eps_basic", eps_basic, "per share", basis),
        "eps_diluted": _ratio_item("eps_diluted", eps_diluted, "per share", basis),
        "book_value_per_share": _ratio_item("book_value_per_share", book_value_per_share, "per share", basis),
        "dividend_per_share": _ratio_item("dividend_per_share", dividend_per_share, "per share", basis),
        "payout_ratio": _ratio_item("payout_ratio", payout_ratio, "%", basis),
    })
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "pass",
        "basis_used": basis,
        "warnings": [],
        "ratios": ratios,
        "limitations": [],
    }


def _growth_item(metric: str, year: str, growth_percent, cagr_percent, absolute_change, basis="consolidated"):
    return {
        "metric": metric,
        "current_year": year,
        "previous_year": "prev",
        "current_value": 1.0,
        "previous_value": 1.0,
        "absolute_change": absolute_change,
        "growth_percent": growth_percent,
        "cagr_percent": cagr_percent,
        "unit": "%",
        "basis": basis,
        "confidence": "high",
        "warnings": [],
    }


def _growth_payload(year: str, *, revenue_growth, pat_growth, basis="consolidated"):
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "pass",
        "basis_used": basis,
        "years_available": [year],
        "growth_metrics": {
            "revenue": _growth_item("revenue", year, revenue_growth, revenue_growth, 10.0, basis),
            "pat": _growth_item("pat", year, pat_growth, pat_growth, 5.0, basis),
        },
        "margin_changes": {},
        "warnings": [],
        "limitations": [],
    }


def _corporate_actions_payload(year: str, *, action_type=None):
    actions = []
    warnings = []
    comparability = []
    if action_type:
        actions.append({
            "action_type": action_type,
            "year": year,
            "announcement_date": None,
            "effective_date": None,
            "ratio": "1:1" if action_type == "stock_split" else "",
            "amount_crore": None,
            "per_share_amount": None,
            "face_value_before": None,
            "face_value_after": None,
            "shares_before": None,
            "shares_after": None,
            "impact_on_share_count": "increase" if action_type in {"qip", "bonus_issue"} else "unknown",
            "impact_on_eps_comparability": "yes",
            "source_line_item": action_type,
            "source_page": 1,
            "source_artifact": "corporate_actions.json",
            "confidence": "high",
            "warnings": [],
        })
        comparability.append(f"{action_type} may affect per-share comparability")
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "pass",
        "actions": actions,
        "share_count_summary": {
            "opening_shares": 10000000,
            "closing_shares": 12000000,
            "weighted_avg_shares": 11000000,
            "diluted_shares": 12100000,
            "face_value": 10.0,
            "share_count_events": [],
        },
        "per_share_comparability_warnings": comparability,
        "warnings": warnings,
        "limitations": [],
    }


def _shareholding_payload(year: str, *, promoter, pledge, fii, dii, mf, public):
    items = [
        {"holder_category": "promoter_holding_percent", "period": year, "holding_percent": promoter, "shares_held": None, "change_percent": None, "source_line_item": "promoter", "source_page": 1, "source_artifact": "shareholding_pattern.json", "confidence": "high", "warnings": []},
        {"holder_category": "pledged_promoter_holding_percent", "period": year, "holding_percent": pledge, "shares_held": None, "change_percent": None, "source_line_item": "pledge", "source_page": 1, "source_artifact": "shareholding_pattern.json", "confidence": "high", "warnings": []},
        {"holder_category": "fii_holding_percent", "period": year, "holding_percent": fii, "shares_held": None, "change_percent": None, "source_line_item": "fii", "source_page": 1, "source_artifact": "shareholding_pattern.json", "confidence": "high", "warnings": []},
        {"holder_category": "dii_holding_percent", "period": year, "holding_percent": dii, "shares_held": None, "change_percent": None, "source_line_item": "dii", "source_page": 1, "source_artifact": "shareholding_pattern.json", "confidence": "high", "warnings": []},
        {"holder_category": "mutual_fund_holding_percent", "period": year, "holding_percent": mf, "shares_held": None, "change_percent": None, "source_line_item": "mf", "source_page": 1, "source_artifact": "shareholding_pattern.json", "confidence": "high", "warnings": []},
        {"holder_category": "public_holding_percent", "period": year, "holding_percent": public, "shares_held": None, "change_percent": None, "source_line_item": "public", "source_page": 1, "source_artifact": "shareholding_pattern.json", "confidence": "high", "warnings": []},
    ]
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "pass",
        "items": items,
        "ownership_summary": {
            "promoter_control": "",
            "institutional_interest": "",
            "pledge_risk": "",
            "public_float": "",
            "notable_changes": [],
        },
        "warnings": [],
        "limitations": [],
    }


def _write_year(company_root: Path, year: str, normalized, ratios=None, growth=None, actions=None, shareholding=None):
    fin = company_root / year / "financials"
    _write_json(fin / "normalized_fundamentals.json", normalized)
    if ratios is not None:
        _write_json(fin / "financial_ratios.json", ratios)
    if growth is not None:
        _write_json(fin / "financial_growth.json", growth)
    if actions is not None:
        _write_json(fin / "corporate_actions.json", actions)
    if shareholding is not None:
        _write_json(fin / "shareholding_pattern.json", shareholding)
    # Write stub intelligence artifacts so this year is ELIGIBLE (not PARTIAL).
    # The eligibility contract requires company_intelligence.json and
    # business_classification.json to be present and non-empty in
    # {year}/intelligence/. Financial data alone is insufficient.
    intel = company_root / year / "intelligence"
    _write_json(intel / "company_intelligence.json", {"stub": True, "company": str(company_root.name), "year": year})
    _write_json(intel / "business_classification.json", {"stub": True, "company": str(company_root.name), "year": year})


def test_build_financial_trends_multi_year_revenue_pat_and_margin(tmp_path):
    company_root = tmp_path / "companies" / "acme"
    _write_year(
        company_root, "fy24",
        _normalized_payload("fy24", revenue=100, ebitda=20, ebit=15, pat=10, assets=90, net_worth=50, debt=20, cash=5, reserves=30, cfo=12, capex=-6, receivables=14, inventory=9, payables=7),
        _ratio_payload("fy24", opm=15, ebitda_margin=20, npm=10, roe=18, roce=16, roa=11, net_debt=15, debt_to_equity=40, cfo_to_pat=120, fcf=6, fcf_to_pat=60, receivable_days=40, inventory_days=25, payable_days=20, ccc=45, eps_basic=10, eps_diluted=9.5, book_value_per_share=50, dividend_per_share=2, payout_ratio=20),
        _growth_payload("fy24", revenue_growth=10, pat_growth=8),
        _corporate_actions_payload("fy24"),
        _shareholding_payload("fy24", promoter=55, pledge=0, fii=10, dii=8, mf=5, public=45),
    )
    _write_year(
        company_root, "fy25",
        _normalized_payload("fy25", revenue=120, ebitda=27, ebit=21, pat=14, assets=110, net_worth=60, debt=24, cash=8, reserves=38, cfo=18, capex=-8, receivables=15, inventory=10, payables=8),
        _ratio_payload("fy25", opm=17.5, ebitda_margin=22.5, npm=11.7, roe=20, roce=18, roa=12.7, net_debt=16, debt_to_equity=40, cfo_to_pat=128.5, fcf=10, fcf_to_pat=71.4, receivable_days=39, inventory_days=24, payable_days=21, ccc=42, eps_basic=14, eps_diluted=13.2, book_value_per_share=60, dividend_per_share=3, payout_ratio=21.4),
        _growth_payload("fy25", revenue_growth=20, pat_growth=40),
        _corporate_actions_payload("fy25"),
        _shareholding_payload("fy25", promoter=54, pledge=0, fii=11, dii=9, mf=6, public=46),
    )

    report = build_financial_trends(company="acme", company_root=company_root)

    assert report.years_covered == ["fy24", "fy25"]
    assert [point.value for point in report.metric_trends["revenue"].series] == [100.0, 120.0]
    assert [point.value for point in report.metric_trends["pat"].series] == [10.0, 14.0]
    assert [point.value for point in report.margin_trends["opm"].series] == [15.0, 17.5]
    assert [point.value for point in report.return_trends["roe"].series] == [18.0, 20.0]
    assert report.growth_summary["revenue"][-1].growth_percent == 20.0


def test_build_financial_trends_cfo_fcf_debt_and_ownership(tmp_path):
    company_root = tmp_path / "companies" / "acme"
    _write_year(
        company_root, "fy24",
        _normalized_payload("fy24", revenue=100, ebitda=20, ebit=15, pat=10, assets=90, net_worth=50, debt=22, cash=4, reserves=28, cfo=11, capex=-5, receivables=12, inventory=8, payables=6),
        _ratio_payload("fy24", opm=15, ebitda_margin=20, npm=10, roe=18, roce=16, roa=11, net_debt=18, debt_to_equity=44, cfo_to_pat=110, fcf=6, fcf_to_pat=60, receivable_days=42, inventory_days=27, payable_days=19, ccc=50, eps_basic=10, eps_diluted=9.5, book_value_per_share=50, dividend_per_share=2, payout_ratio=20),
        _growth_payload("fy24", revenue_growth=10, pat_growth=8),
        _corporate_actions_payload("fy24"),
        _shareholding_payload("fy24", promoter=55, pledge=1, fii=9, dii=7, mf=4, public=45),
    )
    _write_year(
        company_root, "fy25",
        _normalized_payload("fy25", revenue=120, ebitda=27, ebit=21, pat=14, assets=110, net_worth=60, debt=20, cash=7, reserves=35, cfo=17, capex=-7, receivables=13, inventory=8.5, payables=7),
        _ratio_payload("fy25", opm=17, ebitda_margin=22, npm=11.6, roe=19, roce=17, roa=12, net_debt=13, debt_to_equity=33, cfo_to_pat=121, fcf=10, fcf_to_pat=71, receivable_days=38, inventory_days=24, payable_days=20, ccc=42, eps_basic=14, eps_diluted=13.3, book_value_per_share=60, dividend_per_share=3, payout_ratio=21),
        _growth_payload("fy25", revenue_growth=20, pat_growth=40),
        _corporate_actions_payload("fy25"),
        _shareholding_payload("fy25", promoter=54, pledge=0.5, fii=10, dii=8, mf=5, public=46),
    )

    report = build_financial_trends(company="acme", company_root=company_root)
    assert [point.value for point in report.cash_conversion_trends["cfo"].series] == [11.0, 17.0]
    assert [point.value for point in report.cash_conversion_trends["fcf"].series] == [6.0, 10.0]
    assert [point.value for point in report.balance_sheet_trends["total_debt"].series] == [22.0, 20.0]
    assert [point.value for point in report.ownership_trends["promoter_holding"].series] == [55.0, 54.0]


def test_build_financial_trends_split_and_qip_create_per_share_warnings(tmp_path):
    company_root = tmp_path / "companies" / "acme"
    _write_year(
        company_root, "fy24",
        _normalized_payload("fy24", revenue=100, ebitda=20, ebit=15, pat=10, assets=90, net_worth=50, debt=20, cash=5, reserves=30, cfo=12, capex=-6, receivables=14, inventory=9, payables=7),
        _ratio_payload("fy24", opm=15, ebitda_margin=20, npm=10, roe=18, roce=16, roa=11, net_debt=15, debt_to_equity=40, cfo_to_pat=120, fcf=6, fcf_to_pat=60, receivable_days=40, inventory_days=25, payable_days=20, ccc=45, eps_basic=10, eps_diluted=9.5, book_value_per_share=50, dividend_per_share=2, payout_ratio=20),
        _growth_payload("fy24", revenue_growth=10, pat_growth=8),
        _corporate_actions_payload("fy24", action_type="stock_split"),
        _shareholding_payload("fy24", promoter=55, pledge=0, fii=10, dii=8, mf=5, public=45),
    )
    _write_year(
        company_root, "fy25",
        _normalized_payload("fy25", revenue=120, ebitda=27, ebit=21, pat=14, assets=110, net_worth=60, debt=24, cash=8, reserves=38, cfo=18, capex=-8, receivables=15, inventory=10, payables=8, share_count=12000000),
        _ratio_payload("fy25", opm=17.5, ebitda_margin=22.5, npm=11.7, roe=20, roce=18, roa=12.7, net_debt=16, debt_to_equity=40, cfo_to_pat=128.5, fcf=10, fcf_to_pat=71.4, receivable_days=39, inventory_days=24, payable_days=21, ccc=42, eps_basic=14, eps_diluted=13.2, book_value_per_share=60, dividend_per_share=3, payout_ratio=21.4),
        _growth_payload("fy25", revenue_growth=20, pat_growth=40),
        _corporate_actions_payload("fy25", action_type="qip"),
        _shareholding_payload("fy25", promoter=54, pledge=0, fii=11, dii=9, mf=6, public=46),
    )

    report = build_financial_trends(company="acme", company_root=company_root)
    assert any("stock_split" in warning for warning in report.warnings)
    assert any("qip" in warning for warning in report.warnings)
    assert any("stock_split" in warning for warning in report.per_share_trends["eps_basic"].comparability_warnings)
    assert any("qip" in warning for warning in report.per_share_trends["share_count"].comparability_warnings)


def test_build_financial_trends_warns_on_basis_mismatch_and_single_year(tmp_path):
    company_root = tmp_path / "companies" / "acme"
    _write_year(
        company_root, "fy24",
        _normalized_payload("fy24", revenue=100, ebitda=20, ebit=15, pat=10, assets=90, net_worth=50, debt=20, cash=5, reserves=30, cfo=12, capex=-6, receivables=14, inventory=9, payables=7, basis="standalone"),
        _ratio_payload("fy24", opm=15, ebitda_margin=20, npm=10, roe=18, roce=16, roa=11, net_debt=15, debt_to_equity=40, cfo_to_pat=120, fcf=6, fcf_to_pat=60, receivable_days=40, inventory_days=25, payable_days=20, ccc=45, eps_basic=10, eps_diluted=9.5, book_value_per_share=50, dividend_per_share=2, payout_ratio=20, basis="standalone"),
        _growth_payload("fy24", revenue_growth=10, pat_growth=8, basis="standalone"),
        _corporate_actions_payload("fy24"),
        _shareholding_payload("fy24", promoter=55, pledge=0, fii=10, dii=8, mf=5, public=45),
    )
    _write_year(
        company_root, "fy25",
        _normalized_payload("fy25", revenue=120, ebitda=27, ebit=21, pat=14, assets=110, net_worth=60, debt=24, cash=8, reserves=38, cfo=18, capex=-8, receivables=15, inventory=10, payables=8, basis="consolidated"),
        _ratio_payload("fy25", opm=17.5, ebitda_margin=22.5, npm=11.7, roe=20, roce=18, roa=12.7, net_debt=16, debt_to_equity=40, cfo_to_pat=128.5, fcf=10, fcf_to_pat=71.4, receivable_days=39, inventory_days=24, payable_days=21, ccc=42, eps_basic=14, eps_diluted=13.2, book_value_per_share=60, dividend_per_share=3, payout_ratio=21.4, basis="consolidated"),
        _growth_payload("fy25", revenue_growth=20, pat_growth=40, basis="consolidated"),
        _corporate_actions_payload("fy25"),
        _shareholding_payload("fy25", promoter=54, pledge=0, fii=11, dii=9, mf=6, public=46),
    )

    report = build_financial_trends(company="acme", company_root=company_root)
    assert report.basis == "mixed"
    assert "basis mismatch across years" in report.warnings

    solo_root = tmp_path / "companies" / "solo"
    _write_year(
        solo_root, "fy25",
        _normalized_payload("fy25", revenue=120, ebitda=27, ebit=21, pat=14, assets=110, net_worth=60, debt=24, cash=8, reserves=38, cfo=18, capex=-8, receivables=15, inventory=10, payables=8),
    )
    solo = build_financial_trends(company="solo", company_root=solo_root)
    assert "only one financial year available" in solo.warnings


def test_write_financial_trends_persists_company_level_artifact(tmp_path):
    company_root = tmp_path / "companies" / "acme"
    _write_year(
        company_root, "fy25",
        _normalized_payload("fy25", revenue=120, ebitda=27, ebit=21, pat=14, assets=110, net_worth=60, debt=24, cash=8, reserves=38, cfo=18, capex=-8, receivables=15, inventory=10, payables=8),
    )
    output_path = company_root / "company_memory" / "financials" / "financial_trends.json"

    report = write_financial_trends(company="acme", company_root=company_root, output_path=output_path)
    assert output_path.exists()
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["company"] == "acme"
    assert saved["years_covered"] == report.years_covered


# ---------------------------------------------------------------------------
# Eligibility contract regression tests
# ---------------------------------------------------------------------------

def test_eligible_year_is_included_in_financial_trends(tmp_path):
    """A year with both intelligence artifacts + financial data must appear in trends."""
    company_root = tmp_path / "companies" / "acme"
    _write_year(
        company_root, "fy25",
        _normalized_payload("fy25", revenue=100, ebitda=20, ebit=15, pat=10, assets=90, net_worth=50, debt=20, cash=5, reserves=30, cfo=12, capex=-6, receivables=14, inventory=9, payables=7),
    )
    manifest = build_company_year_eligibility_manifest(company="acme", company_root=company_root)
    assert manifest["eligible_years"] == ["fy25"]
    report = build_financial_trends(company="acme", company_root=company_root)
    assert "fy25" in report.years_covered


def test_incomplete_year_missing_intelligence_artifacts_is_excluded_from_trends(tmp_path):
    """A year that has financial data but no intelligence artifacts must be PARTIAL (not ELIGIBLE)."""
    company_root = tmp_path / "companies" / "acme"
    # Write financial data for fy24 WITHOUT intelligence artifacts
    fin = company_root / "fy24" / "financials"
    _write_json(fin / "normalized_fundamentals.json",
        _normalized_payload("fy24", revenue=80, ebitda=16, ebit=12, pat=8, assets=70, net_worth=40, debt=15, cash=4, reserves=22, cfo=10, capex=-5, receivables=10, inventory=7, payables=5))
    # Write a complete eligible fy25 for revenue/PAT trend to succeed
    _write_year(
        company_root, "fy25",
        _normalized_payload("fy25", revenue=100, ebitda=20, ebit=15, pat=10, assets=90, net_worth=50, debt=20, cash=5, reserves=30, cfo=12, capex=-6, receivables=14, inventory=9, payables=7),
    )
    manifest = build_company_year_eligibility_manifest(company="acme", company_root=company_root)
    assert "fy24" in manifest["partial_years"], "fy24 has financial data but is not ELIGIBLE without intelligence artifacts"
    assert "fy24" not in manifest["eligible_years"]
    report = build_financial_trends(company="acme", company_root=company_root)
    assert "fy24" not in report.years_covered


def test_partial_year_status_is_explicit_in_eligibility_manifest(tmp_path):
    """A year with only financial artifacts must show status=PARTIAL (not INELIGIBLE)."""
    company_root = tmp_path / "companies" / "acme"
    fin = company_root / "fy24" / "financials"
    _write_json(fin / "normalized_fundamentals.json",
        _normalized_payload("fy24", revenue=80, ebitda=16, ebit=12, pat=8, assets=70, net_worth=40, debt=15, cash=4, reserves=22, cfo=10, capex=-5, receivables=10, inventory=7, payables=5))
    manifest = build_company_year_eligibility_manifest(company="acme", company_root=company_root)
    year_entry = manifest["years"]["fy24"]
    assert year_entry["status"] == PARTIAL
    assert len(year_entry["missing_required_artifacts"]) == 2  # both intelligence artifacts missing
    assert "intelligence/company_intelligence.json" in year_entry["missing_required_artifacts"]
    assert "intelligence/business_classification.json" in year_entry["missing_required_artifacts"]


def test_financial_data_alone_cannot_bypass_eligibility(tmp_path):
    """build_financial_trends must not produce a trend series from a PARTIAL year when no ELIGIBLE year exists."""
    company_root = tmp_path / "companies" / "acme"
    fin = company_root / "fy24" / "financials"
    _write_json(fin / "normalized_fundamentals.json",
        _normalized_payload("fy24", revenue=80, ebitda=16, ebit=12, pat=8, assets=70, net_worth=40, debt=15, cash=4, reserves=22, cfo=10, capex=-5, receivables=10, inventory=7, payables=5))
    manifest = build_company_year_eligibility_manifest(company="acme", company_root=company_root)
    assert manifest["eligible_years"] == [], "financial data alone must not produce an eligible year"
    with pytest.raises(RuntimeError, match="financial_trends could not build revenue or PAT trend"):
        build_financial_trends(company="acme", company_root=company_root)


def test_test_fixtures_mirror_production_eligibility_prerequisites(tmp_path):
    """_write_year in tests must satisfy the same eligibility prerequisites as production."""
    company_root = tmp_path / "companies" / "acme"
    _write_year(
        company_root, "fy25",
        _normalized_payload("fy25", revenue=100, ebitda=20, ebit=15, pat=10, assets=90, net_worth=50, debt=20, cash=5, reserves=30, cfo=12, capex=-6, receivables=14, inventory=9, payables=7),
    )
    # Verify exactly what production checks: intelligence artifacts exist and are non-empty
    intel_ci = company_root / "fy25" / "intelligence" / "company_intelligence.json"
    intel_bc = company_root / "fy25" / "intelligence" / "business_classification.json"
    assert intel_ci.exists(), "_write_year must create company_intelligence.json"
    assert intel_bc.exists(), "_write_year must create business_classification.json"
    assert json.loads(intel_ci.read_text()), "company_intelligence.json must be non-empty"
    assert json.loads(intel_bc.read_text()), "business_classification.json must be non-empty"
    manifest = build_company_year_eligibility_manifest(company="acme", company_root=company_root)
    assert "fy25" in manifest["eligible_years"], "_write_year must produce ELIGIBLE years"


def test_sun_pharma_fy22_excluded_when_intelligence_artifacts_absent(tmp_path):
    """Regression: Sun Pharma FY22 was excluded from trends because intelligence artifacts
    were never generated (pipeline failed at cleaning). A year without intelligence artifacts
    must remain PARTIAL/excluded even when financial data exists."""
    company_root = tmp_path / "companies" / "sun_pharma"
    # FY21 + FY23 are eligible (simulate post-fix pipeline success)
    _write_year(
        company_root, "fy21",
        _normalized_payload("fy21", revenue=250, ebitda=55, ebit=48, pat=38, assets=450, net_worth=320, debt=30, cash=20, reserves=280, cfo=45, capex=-20, receivables=40, inventory=35, payables=22),
    )
    _write_year(
        company_root, "fy23",
        _normalized_payload("fy23", revenue=310, ebitda=72, ebit=63, pat=50, assets=520, net_worth=370, debt=25, cash=30, reserves=335, cfo=55, capex=-22, receivables=48, inventory=38, payables=25),
    )
    # FY22: financial data present but intelligence artifacts absent (pipeline failed at cleaning)
    fin22 = company_root / "fy22" / "financials"
    _write_json(fin22 / "normalized_fundamentals.json",
        _normalized_payload("fy22", revenue=280, ebitda=61, ebit=53, pat=43, assets=480, net_worth=340, debt=28, cash=25, reserves=305, cfo=50, capex=-21, receivables=44, inventory=36, payables=23))

    manifest = build_company_year_eligibility_manifest(company="sun_pharma", company_root=company_root)
    assert manifest["years"]["fy22"]["status"] == PARTIAL, "FY22 must be PARTIAL, not ELIGIBLE"
    assert "fy22" not in manifest["eligible_years"]
    report = build_financial_trends(company="sun_pharma", company_root=company_root)
    assert "fy22" not in report.years_covered
    assert "fy21" in report.years_covered
    assert "fy23" in report.years_covered


def test_no_company_or_year_hardcoding_in_eligibility_or_trend_code():
    """No production module should reference a specific company name or year."""
    import re
    company_names = ["sun_pharma", "ujjivan", "tanla", "datapatterns", "polymatech"]
    for module_path in [
        "knowledge/company_year_eligibility.py",
        "knowledge/financials/trend_builder.py",
    ]:
        text = Path(module_path).read_text(encoding="utf-8").lower()
        for name in company_names:
            assert name not in text, (
                f"{module_path} must not hardcode company name '{name}'"
            )
    # Years like "fy22", "fy23" etc. must not appear as literals (they may appear in docstrings / comments,
    # but not in conditional logic — check that no year-keyed dict literal or comparison exists)
    trend_text = Path("knowledge/financials/trend_builder.py").read_text(encoding="utf-8")
    assert not re.search(r'==\s*["\']fy\d{2}["\']', trend_text), (
        "trend_builder.py must not hardcode year comparisons like == 'fy22'"
    )
