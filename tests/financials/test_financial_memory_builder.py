"""
Regression tests for financial_memory_builder consistency fixes.

Contract: If a metric is present (non-null, usable_downstream=True) in the canonical
financial_trends source, the summary must not simultaneously report it as missing.
Stale lower-priority artifacts (financial_ratios.json, financial_quality_summary.json,
corporate_actions.json) cannot override a canonical present fact.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from knowledge.financials.memory_builder import (
    _MISSING_CLAIM_CHECKS,
    _build_trends_presence,
    _reconcile_canonical_presence,
    build_capital_allocation_financial_timeline,
    build_financial_memory_summary,
)


# ---------------------------------------------------------------------------
# Minimal stub builders
# ---------------------------------------------------------------------------

def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _trend_series(metric_name: str, points: List[Dict]) -> Dict:
    return {metric_name: {"series": points, "unit": "₹ crore"}}



def _minimal_trends_payload(
    *,
    fcf_by_year: Dict[str, Any] = None,
    capex_by_year: Dict[str, Any] = None,
    weighted_avg_shares_by_year: Dict[str, Any] = None,
    diluted_shares_by_year: Dict[str, Any] = None,
    warnings: List[str] = None,
    revenue_by_year: Dict[str, Any] = None,
) -> Dict:
    def _make_series(by_year: Dict[str, Any]) -> List[Dict]:
        return [
            {
                "year": yr,
                "value": val,
                "basis": "consolidated",
                "source_artifact": "normalized_fundamentals.json",
                "confidence": "medium",
                "availability_status": "present_direct" if val is not None else "missing",
                "derived": False,
                "usable_downstream": val is not None,
                "warnings": [],
            }
            for yr, val in (by_year or {}).items()
        ]

    return {
        "company": "testco",
        "years_covered": [],
        "basis": "consolidated",
        "basis_policy": {"preferred_basis": "consolidated", "basis_consistency": "consistent", "warnings": []},
        "warnings": warnings or [],
        "limitations": [],
        "cash_conversion_trends": {
            "fcf": {"series": _make_series(fcf_by_year or {})},
            "capex": {"series": _make_series(capex_by_year or {})},
            "cfo": {"series": []},
            "cfo_to_pat": {"series": []},
            "fcf_to_pat": {"series": []},
            "fcf_margin": {"series": []},
            "receivables": {"series": []},
            "inventory": {"series": []},
            "payables": {"series": []},
            "receivable_days": {"series": []},
            "inventory_days": {"series": []},
            "payable_days": {"series": []},
            "cash_conversion_cycle": {"series": []},
        },
        "metric_trends": {
            "revenue": {"series": _make_series(revenue_by_year or {"fy24": 100.0})},
            "ebitda": {"series": []},
            "ebit": {"series": []},
            "pat": {"series": []},
            "total_assets": {"series": []},
            "net_worth": {"series": []},
            "book_value_per_share": {"series": []},
        },
        "margin_trends": {k: {"series": []} for k in ("gross_margin", "ebitda_margin", "ebit_margin", "opm", "npm")},
        "return_trends": {k: {"series": []} for k in ("roe", "roce", "roa")},
        "balance_sheet_trends": {k: {"series": []} for k in ("total_debt", "net_debt", "debt_to_equity", "net_debt_to_equity", "cash_and_equivalents", "reserves")},
        "per_share_trends": {
            "eps_basic": {"series": []},
            "eps_diluted": {"series": []},
            "book_value_per_share": {"series": []},
            "dividend_per_share": {"series": []},
            "payout_ratio": {"series": []},
            "closing_shares": {"series": []},
            "share_count": {"series": []},
            "weighted_avg_shares": {"series": _make_series(weighted_avg_shares_by_year or {})},
            "weighted_average_diluted_shares": {"series": _make_series(diluted_shares_by_year or {})},
        },
        "ownership_trends": {k: {"series": []} for k in ("promoter_holding", "pledged_promoter_holding", "fii_holding", "dii_holding", "mutual_fund_holding", "public_holding")},
    }


def _minimal_year_index(years: List[str]) -> Dict:
    return {
        "company": "testco",
        "generated_at": "2026-01-01T00:00:00Z",
        "years_discovered": years,
        "years_used": years,
        "years_skipped": [],
        "year_status": {},
        "company_year_eligibility": {"eligible_years": years, "partial_years": [], "ineligible_years": []},
        "warnings": [],
        "limitations": [],
    }


def _minimal_quality_evolution(*, missing_data_patterns: List[str] = None) -> Dict:
    return {
        "company": "testco",
        "generated_at": "2026-01-01T00:00:00Z",
        "years_covered": [],
        "evolution": {},
        "recurring_strengths": [],
        "recurring_concerns": [],
        "improving_signals": [],
        "deteriorating_signals": [],
        "missing_data_patterns": missing_data_patterns or [],
        "warnings": [],
        "limitations": [],
    }


def _minimal_capital_timeline(*, limitations: List[str] = None) -> Dict:
    return {
        "company": "testco",
        "generated_at": "2026-01-01T00:00:00Z",
        "years_covered": [],
        "timeline": [],
        "dividend_pattern": {"years": []},
        "capex_pattern": {"years": []},
        "fcf_pattern": {"years": []},
        "dilution_or_share_issue_pattern": {"years": []},
        "debt_pattern": {"years": []},
        "warnings": [],
        "limitations": limitations or [],
    }


def _minimal_ownership() -> Dict:
    return {
        "company": "testco",
        "generated_at": "2026-01-01T00:00:00Z",
        "years_covered": [],
        "promoter_holding": [],
        "pledge": [],
        "fii": [],
        "dii": [],
        "mutual_funds": [],
        "public": [],
        "institutional_signal": {"years_with_data": [], "note": ""},
        "warnings": [],
        "limitations": [],
    }


def _call_summary(
    *,
    fcf_by_year: Dict[str, Any] = None,
    capex_by_year: Dict[str, Any] = None,
    weighted_avg_shares_by_year: Dict[str, Any] = None,
    diluted_shares_by_year: Dict[str, Any] = None,
    trend_warnings: List[str] = None,
    quality_missing_patterns: List[str] = None,
    capital_limitations: List[str] = None,
    years: List[str] = None,
) -> Dict:
    trends = _minimal_trends_payload(
        fcf_by_year=fcf_by_year,
        capex_by_year=capex_by_year,
        weighted_avg_shares_by_year=weighted_avg_shares_by_year,
        diluted_shares_by_year=diluted_shares_by_year,
        warnings=trend_warnings,
    )
    return build_financial_memory_summary(
        company="testco",
        trends_payload=trends,
        quality_evolution_payload=_minimal_quality_evolution(missing_data_patterns=quality_missing_patterns),
        capital_timeline_payload=_minimal_capital_timeline(limitations=capital_limitations),
        ownership_payload=_minimal_ownership(),
        year_index_payload=_minimal_year_index(years or ["fy24"]),
    )


# ---------------------------------------------------------------------------
# Regression test 1: FCF present in trends → no "FCF missing" in summary
# ---------------------------------------------------------------------------

def test_fcf_present_in_trends_not_reported_as_missing():
    """If FCF is present and usable in financial_trends, 'FCF missing' must not appear
    in missing_data, warnings, or limitations — even when capital_timeline_payload or
    quality_evolution emits a stale missing claim."""
    result = _call_summary(
        fcf_by_year={"fy24": 5012.77},
        capital_limitations=["fy24: FCF missing"],  # stale capital timeline claim
        quality_missing_patterns=["fy24: FCF missing"],  # stale quality evolution claim
    )
    all_missing = result["missing_data"] + result["warnings"] + result["limitations"]
    fcf_missing_claims = [item for item in all_missing if "fcf missing" in item.lower()]
    assert not fcf_missing_claims, (
        f"FCF is present in trends but summary still reports FCF missing: {fcf_missing_claims}"
    )


# ---------------------------------------------------------------------------
# Regression test 2: capex present in trends → no capex-missing warning
# ---------------------------------------------------------------------------

def test_capex_present_in_trends_not_reported_as_missing():
    """If capex is present and usable in financial_trends, 'capex missing' must not
    appear in the summary output."""
    result = _call_summary(
        capex_by_year={"fy24": -1542.0},
        capital_limitations=["fy24: capex missing"],  # stale claim
    )
    all_output = result["missing_data"] + result["warnings"] + result["limitations"]
    capex_claims = [item for item in all_output if "capex missing" in item.lower()]
    assert not capex_claims, (
        f"capex is present in trends but summary still reports it missing: {capex_claims}"
    )


# ---------------------------------------------------------------------------
# Regression test 3: weighted_avg_shares present → no missing warning
# ---------------------------------------------------------------------------

def test_weighted_avg_shares_present_not_reported_as_missing():
    """If weighted_avg_shares is present in financial_trends, stale 'EPS exists but
    weighted average shares are missing' warnings must be suppressed."""
    result = _call_summary(
        weighted_avg_shares_by_year={"fy23": 2399334970.0, "fy24": 2399334970.0},
        # Stale per-year quality_summary warnings
        quality_missing_patterns=[
            "fy23: EPS exists but weighted average shares are missing",
            "fy24: EPS exists but weighted average shares are missing",
        ],
        # Stale financial_trends.json warnings from old corporate_actions
        trend_warnings=[
            "fy23: EPS exists but weighted average shares are missing",
            "fy24: EPS exists but weighted average shares are missing",
        ],
    )
    all_output = result["missing_data"] + result["warnings"] + result["limitations"]
    stale = [item for item in all_output if "weighted average shares are missing" in item.lower()
             or "eps exists but weighted average shares" in item.lower()]
    assert not stale, (
        f"weighted_avg_shares is present in trends but summary still says: {stale}"
    )


# ---------------------------------------------------------------------------
# Regression test 4: genuinely missing metric still reported
# ---------------------------------------------------------------------------

def test_genuinely_missing_metric_still_reported():
    """Diluted shares are genuinely absent (None) in trends — the warning must remain.
    Only claims contradicted by canonical presence are removed."""
    result = _call_summary(
        # diluted_shares has null values → genuinely missing
        diluted_shares_by_year={"fy23": None, "fy24": None},
        quality_missing_patterns=[
            "fy23: diluted shares missing",
            "fy24: diluted shares missing",
        ],
    )
    all_missing = result["missing_data"]
    diluted_claims = [item for item in all_missing if "diluted shares missing" in item.lower()]
    assert diluted_claims, (
        "diluted shares are genuinely missing in trends but the warning was suppressed"
    )


# ---------------------------------------------------------------------------
# Regression test 5: stale lower-priority artifact cannot override canonical present fact
# ---------------------------------------------------------------------------

def test_stale_artifact_cannot_override_canonical_present_fact():
    """A stale warning claiming FCF missing must be ignored when the canonical
    financial_trends source shows FCF present for that year."""
    # FCF present in trends for fy23
    result = _call_summary(
        fcf_by_year={"fy23": 2873.75, "fy24": 9933.17},
        # Stale financial_ratios.json → capital_timeline reports FCF missing for fy23
        capital_limitations=["fy23: FCF missing"],
    )
    all_output = result["missing_data"] + result["warnings"] + result["limitations"]
    assert not any("fy23: fcf missing" in item.lower() for item in all_output), (
        "Stale capital_timeline claim 'fy23: FCF missing' must not override canonical trend fact"
    )
    # FCF not reported as missing for fy24 either
    assert not any("fy24: fcf missing" in item.lower() for item in all_output)


# ---------------------------------------------------------------------------
# Regression test 6: no company/year hardcoding in memory_builder
# ---------------------------------------------------------------------------

def test_no_company_or_year_hardcoding_in_memory_builder():
    """The memory_builder module must not reference any specific company name or fiscal year."""
    import re
    company_names = ["sun_pharma", "ujjivan", "tanla", "datapatterns", "polymatech"]
    text = Path("knowledge/financials/memory_builder.py").read_text(encoding="utf-8").lower()
    for name in company_names:
        assert name not in text, f"memory_builder.py must not hardcode company name '{name}'"
    # Year comparisons as == "fyNN" literals should not appear
    assert not re.search(r'==\s*["\']fy\d{2}["\']', text), (
        "memory_builder.py must not hardcode year comparisons like == 'fy22'"
    )


# ---------------------------------------------------------------------------
# Regression test 7: FCF derivation from normalized in capital_timeline
# ---------------------------------------------------------------------------

def _write_year_financials(company_root: Path, year: str, *, cfo: float, capex: float, ratio_fcf=None) -> None:
    fin = company_root / year / "financials"
    intel = company_root / year / "intelligence"
    for d in (fin, intel):
        d.mkdir(parents=True, exist_ok=True)

    # Normalized fundamentals with cfo and capex
    nf = {
        "company": "testco",
        "year": year,
        "preferred_basis": "consolidated",
        "cash_flow": {
            "cfo": {"canonical_field": "cfo", "value_crore": cfo, "basis": "consolidated"},
            "capex": {"canonical_field": "capex", "value_crore": capex, "basis": "consolidated"},
        },
        "profit_and_loss": {},
        "balance_sheet": {},
        "share_data": {},
    }
    _write_json(fin / "normalized_fundamentals.json", nf)

    # Financial ratios: FCF is None (simulates ratio_calculator failure)
    ratios = {
        "company": "testco",
        "year": year,
        "ratios": {
            "fcf": {"ratio_name": "fcf", "value": ratio_fcf, "unit": "₹ crore"},
        },
    }
    _write_json(fin / "financial_ratios.json", ratios)

    # Stub other required files
    for stub_name in ("financial_validation_report.json", "financial_reconciliation_report.json",
                      "financial_quality_summary.json", "corporate_actions.json", "shareholding_pattern.json",
                      "financial_growth.json"):
        _write_json(fin / stub_name, {"company": "testco", "year": year, "status": "pass"})

    # Intelligence stubs (required for eligibility)
    for name in ("company_intelligence.json", "business_classification.json"):
        _write_json(intel / name, {"company": "testco", "year": year})


def test_capital_timeline_derives_fcf_from_normalized_when_ratio_is_missing(tmp_path):
    """When financial_ratios.json has FCF=None but normalized_fundamentals has cfo+capex,
    build_capital_allocation_financial_timeline must derive FCF and NOT emit 'FCF missing'."""
    company_root = tmp_path / "companies" / "testco"
    _write_year_financials(company_root, "fy23", cfo=4959.33, capex=-2085.58, ratio_fcf=None)

    timeline = build_capital_allocation_financial_timeline(
        company="testco", company_root=company_root, years_used=["fy23"]
    )
    assert "fy23" in timeline["fcf_pattern"]["years"], (
        "fy23 FCF derived from normalized (cfo+capex) must be in fcf_pattern years"
    )
    assert not any("fy23: fcf missing" in lim.lower() for lim in timeline["limitations"]), (
        "'fy23: FCF missing' must not appear in limitations when cfo+capex are available"
    )
    # Verify derived value matches expected (4959.33 + (-2085.58) = 2873.75)
    fy23_entry = next((e for e in timeline["timeline"] if e["year"] == "fy23"), None)
    assert fy23_entry is not None
    assert abs(fy23_entry["fcf"]["value"] - 2873.75) < 0.01, (
        f"Derived FCF must equal cfo+capex=2873.75, got {fy23_entry['fcf']['value']}"
    )
    assert fy23_entry["fcf"]["source_artifact"] == "normalized_fundamentals.json"


def test_capital_timeline_preserves_ratio_fcf_when_present(tmp_path):
    """When financial_ratios.json already has a non-null FCF, it should be used as-is."""
    company_root = tmp_path / "companies" / "testco"
    _write_year_financials(company_root, "fy24", cfo=12134.98, capex=-2201.81, ratio_fcf=9933.17)

    timeline = build_capital_allocation_financial_timeline(
        company="testco", company_root=company_root, years_used=["fy24"]
    )
    assert "fy24" in timeline["fcf_pattern"]["years"]
    fy24_entry = next(e for e in timeline["timeline"] if e["year"] == "fy24")
    assert fy24_entry["fcf"]["value"] == 9933.17
    assert fy24_entry["fcf"]["source_artifact"] == "financial_ratios.json"
