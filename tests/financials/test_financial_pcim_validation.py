from __future__ import annotations

import json
from pathlib import Path

from knowledge.financials.pcim_validation import (
    build_financial_pcim_validation,
    build_financial_quality_scorecard,
    write_financial_quality_scorecard,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _normalized_entry(value_crore, *, unit_original="crore", value_original=None):
    return {
        "value_crore": value_crore,
        "value_original": str(value_original if value_original is not None else value_crore) if value_crore is not None else "",
        "unit_original": unit_original,
        "basis": "consolidated",
        "source_page": 10,
        "source_artifact": "normalized_fundamentals.json",
        "confidence": "high",
        "warnings": [],
    }


def _seed_financial_year(base: Path, company: str = "acme", year: str = "fy24", *, include_fcf: bool = True, shareholding_status: str = "pass"):
    fin = base / "companies" / company / year / "financials"
    _write_json(
        fin / "normalized_fundamentals.json",
        {
            "company": company,
            "year": year,
            "preferred_basis": "consolidated",
            "profit_and_loss": {
                "revenue": _normalized_entry(100.0),
                "pat": _normalized_entry(12.0),
            },
            "balance_sheet": {
                "net_worth": _normalized_entry(55.0),
                "total_debt": _normalized_entry(8.0),
                "cash_and_equivalents": _normalized_entry(14.0),
                "payables": _normalized_entry(6.0),
            },
            "cash_flow": {
                "cfo": _normalized_entry(16.0),
                "capex": _normalized_entry(4.0),
            },
            "share_data": {
                "shares_outstanding": {
                    "raw_number": 1000000,
                    "value_original": "1000000",
                    "unit_original": "shares",
                    "basis": "consolidated",
                    "source_page": 11,
                    "source_artifact": "normalized_fundamentals.json",
                    "confidence": "medium",
                    "warnings": [],
                }
            },
            "warnings": [],
            "limitations": [],
        },
    )
    _write_json(fin / "financial_validation_report.json", {"company": company, "year": year, "status": "pass", "warnings": [], "hard_failures": []})
    _write_json(fin / "financial_reconciliation_report.json", {"company": company, "year": year, "status": "pass", "warnings": [], "hard_failures": []})
    _write_json(
        fin / "financial_ratios.json",
        {
            "company": company,
            "year": year,
            "status": "pass",
            "ratios": {
                "opm": {"value": 20.0, "unit": "%", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []},
                "npm": {"value": 12.0, "unit": "%", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []},
                "roe": {"value": 18.0, "unit": "%", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []},
                "roce": {"value": 16.0, "unit": "%", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []},
                "debt_to_equity": {"value": 0.15, "unit": "x", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []},
                "cfo_to_pat": {"value": 1.33, "unit": "x", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []},
                "fcf_to_pat": {"value": 1.0 if include_fcf else None, "unit": "x", "basis": "consolidated", "confidence": "high" if include_fcf else "missing", "source_artifacts": ["financial_ratios.json"], "warnings": []},
                "book_value_per_share": {"value": 55.0, "unit": "per share", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []},
                "fcf": {"value": 12.0 if include_fcf else None, "unit": "₹ crore", "basis": "consolidated", "confidence": "medium" if include_fcf else "missing", "source_artifacts": ["financial_ratios.json"], "warnings": ["capex missing"] if not include_fcf else []},
                "receivable_days": {"value": 30.0, "unit": "days", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_ratios.json"], "warnings": []},
                "payable_days": {"value": 18.0, "unit": "days", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_ratios.json"], "warnings": []},
                "cash_conversion_cycle": {"value": 12.0, "unit": "days", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_ratios.json"], "warnings": []},
            },
            "warnings": ["FCF missing"] if not include_fcf else [],
        },
    )
    _write_json(
        fin / "financial_growth.json",
        {
            "company": company,
            "year": year,
            "growth_metrics": {
                "revenue": [{"metric": "revenue", "current_year": year, "growth_percent": 12.0, "absolute_change": 10.0, "basis": "consolidated", "confidence": "medium", "warnings": []}],
                "pat": [{"metric": "pat", "current_year": year, "growth_percent": 14.0, "absolute_change": 1.5, "basis": "consolidated", "confidence": "medium", "warnings": []}],
                "eps_basic": [{"metric": "eps_basic", "current_year": year, "growth_percent": 13.0, "absolute_change": 1.2, "basis": "consolidated", "confidence": "medium", "warnings": []}],
                "book_value_per_share": [{"metric": "book_value_per_share", "current_year": year, "growth_percent": 10.0, "absolute_change": 5.0, "basis": "consolidated", "confidence": "medium", "warnings": []}],
            },
            "warnings": [],
        },
    )
    _write_json(
        fin / "financial_quality_summary.json",
        {
            "company": company,
            "year": year,
            "status": "warning" if not include_fcf else "pass",
            "basis_used": "consolidated",
            "sections": {
                "growth_quality": {"status": "pass", "summary": "Healthy growth.", "signals": ["Revenue and PAT grew."], "warnings": []},
                "cash_conversion_quality": {"status": "warning" if not include_fcf else "pass", "summary": "Cash conversion is usable.", "signals": ["CFO exceeds PAT."], "warnings": ["FCF missing"] if not include_fcf else []},
                "return_on_capital_quality": {"status": "pass", "summary": "Returns remain solid.", "signals": ["ROCE above 15%."], "warnings": []},
                "balance_sheet_strength": {"status": "pass", "summary": "Balance sheet is stable.", "signals": ["Debt remains modest."], "warnings": []},
            },
            "warnings": ["FCF missing"] if not include_fcf else [],
            "limitations": [],
        },
    )
    _write_json(
        fin / "corporate_actions.json",
        {
            "company": company,
            "year": year,
            "status": "warning",
            "actions": [{"action_type": "dividend", "impact_on_share_count": "none", "impact_on_eps_comparability": "no", "warnings": []}],
            "per_share_comparability_warnings": ["No material comparability issue detected."],
            "warnings": [],
        },
    )
    _write_json(
        fin / "shareholding_pattern.json",
        {
            "company": company,
            "year": year,
            "status": shareholding_status,
            "items": [] if shareholding_status != "pass" else [{"holder_category": "promoter_holding_percent", "holding_percent": 51.2, "confidence": "high", "warnings": []}],
            "warnings": ["shareholding pattern missing"] if shareholding_status != "pass" else [],
        },
    )


def _seed_company_memory(base: Path, company: str = "acme", year: str = "fy24", *, include_fcf: bool = True, include_multi_year: bool = True, raw_leak: bool = False):
    company_memory = base / "companies" / company / "company_memory"
    fin_memory = company_memory / "financials"
    _write_json(
        fin_memory / "financial_memory_summary.json",
        {
            "company": company,
            "generated_at": "2026-07-18T00:00:00Z",
            "status": "warning",
            "years_covered": [year],
            "basis_used": "consolidated",
            "summary": {
                "scale_pattern": [f"revenue in {year}: 100.0 ₹ crore"],
                "profitability_pattern": [f"opm in {year}: 20.0 %"],
                "return_pattern": [f"roe in {year}: 18.0 %"],
                "cash_conversion_pattern": [f"cfo in {year}: 16.0 ₹ crore"],
                "balance_sheet_pattern": [f"total_debt in {year}: 8.0 ₹ crore"],
                "working_capital_pattern": [],
                "capital_allocation_pattern": [f"Dividend evidence in: {year}"],
                "ownership_pattern": ["Promoter holding tracked across 1 year(s)."],
            },
            "key_strengths": ["Cash conversion remains healthy."],
            "key_concerns": [],
            "missing_data": ["FCF missing"] if not include_fcf else [],
            "investor_questions": [],
            "warnings": ["FCF missing"] if not include_fcf else [],
            "limitations": [],
        },
    )
    pcim = {
        "company": company,
        "financial_fundamentals_inputs": {
            "by_year": [{"year": year, "basis": "consolidated", "key_metrics": [{"field": "revenue", "value_crore": 100.0, "source_year": year, "source_artifact": "normalized_fundamentals.json", "basis": "consolidated", "confidence": "high", "warnings": []}, {"field": "pat", "value_crore": 12.0, "source_year": year, "source_artifact": "normalized_fundamentals.json", "basis": "consolidated", "confidence": "high", "warnings": []}, {"field": "cfo", "value_crore": 16.0, "source_year": year, "source_artifact": "normalized_fundamentals.json", "basis": "consolidated", "confidence": "high", "warnings": []}, {"field": "capex", "value_crore": 4.0, "source_year": year, "source_artifact": "normalized_fundamentals.json", "basis": "consolidated", "confidence": "high", "warnings": ["FCF missing"] if not include_fcf else []}]}],
            "warnings": ["FCF missing"] if not include_fcf else [],
        },
        "financial_growth_inputs": {"by_year": [{"year": year, "growth_metrics": [{"metric": "revenue", "growth_percent": 12.0, "basis": "consolidated", "confidence": "medium", "source_artifact": "financial_growth.json", "warnings": []}], "warnings": [], "limitations": []}]},
        "profitability_inputs": {"by_year": [{"year": year, "metrics": [{"metric": "opm", "value": 20.0, "unit": "%", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []}], "warnings": [], "limitations": []}]},
        "return_on_capital_inputs": {"status": "pass", "summary": "Returns remain solid.", "signals": ["ROCE remained above 15%."], "warnings": [], "metrics": [{"metric": "roce", "unit": "%", "series": [{"year": year, "value": 16.0, "basis": "consolidated", "source_artifact": "financial_trends.json", "confidence": "high", "warnings": []}], "comparability_warnings": [], "source_artifact": "financial_trends.json"}], "source_artifact": "financial_quality_summary.json"},
        "cash_conversion_inputs": {"status": "warning" if not include_fcf else "pass", "summary": "Cash conversion is usable.", "signals": ["CFO exceeds PAT."], "warnings": ["FCF missing"] if not include_fcf else [], "metrics": [{"metric": "cfo", "unit": "₹ crore", "series": [{"year": year, "value": 16.0, "basis": "consolidated", "source_artifact": "financial_trends.json", "confidence": "high", "warnings": []}], "comparability_warnings": [], "source_artifact": "financial_trends.json"}], "source_artifact": "financial_quality_summary.json"},
        "balance_sheet_strength_inputs": {"status": "pass", "summary": "Balance sheet is stable.", "signals": ["Debt remains modest."], "warnings": [], "metrics": [{"metric": "total_debt", "unit": "₹ crore", "series": [{"year": year, "value": 8.0, "basis": "consolidated", "source_artifact": "financial_trends.json", "confidence": "high", "warnings": []}], "comparability_warnings": [], "source_artifact": "financial_trends.json"}], "source_artifact": "financial_quality_summary.json"},
        "working_capital_inputs": {"by_year": [{"year": year, "metrics": [{"metric": "payable_days", "value": 18.0, "unit": "days", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_ratios.json"], "warnings": []}], "warnings": [], "limitations": []}]},
        "per_share_inputs": {"metrics": [{"metric": "book_value_per_share", "unit": "per share", "series": [{"year": year, "value": 55.0, "basis": "consolidated", "source_artifact": "financial_trends.json", "confidence": "high", "warnings": []}], "comparability_warnings": [], "source_artifact": "financial_trends.json"}], "warnings": [], "source_artifact": "financial_trends.json"},
        "corporate_action_inputs": {"by_year": [{"year": year, "status": "warning", "actions": [{"action_type": "dividend", "source_year": year, "source_artifact": "corporate_actions.json", "impact_on_share_count": "none", "impact_on_eps_comparability": "no", "warnings": []}], "per_share_comparability_warnings": ["No material comparability issue detected."]}], "warnings": [], "source_artifact": "corporate_actions.json"},
        "ownership_inputs": {"by_year": [{"year": year, "status": "pass", "items": [{"holder_category": "promoter_holding_percent", "holding_percent": 51.2, "source_year": year, "source_artifact": "shareholding_pattern.json", "confidence": "high", "warnings": []}], "warnings": []}], "summary_status": "warning", "summary": "Ownership is stable but shallow.", "warnings": [], "source_artifact": "shareholding_pattern.json"},
        "financial_quality_inputs": {"by_year": [{"year": year, "status": "warning" if not include_fcf else "pass", "basis_used": "consolidated", "sections": {}, "red_flags": [], "missing_data": ["FCF missing"] if not include_fcf else [], "investor_questions": [], "warnings": ["FCF missing"] if not include_fcf else [], "limitations": []}], "warnings": ["FCF missing"] if not include_fcf else [], "source_artifact": "financial_quality_summary.json"},
        "financial_driver_inputs": {"status": "warning", "years_covered": [year], "attributions": [], "warnings": [], "limitations": [], "source_artifact": "financial_driver_attribution.json"},
        "financial_source_manifest": {"financial_artifacts_used": ["normalized_fundamentals.json"], "latest_generated_at": "2026-07-18T00:00:00Z", "status": "warning" if not include_fcf else "pass", "warnings": ["FCF missing"] if not include_fcf else [], "limitations": ["FCF missing"] if not include_fcf else []},
        "financial_panel_ready": True,
        "pcim_source_manifest": {"financial_artifacts_used": [{"name": "normalized_fundamentals.json", "loaded": True, "warnings": []}], "financial_years_covered": [year], "financial_status": "warning" if not include_fcf else "pass", "financial_warnings": ["FCF missing"] if not include_fcf else []},
    }
    if include_multi_year:
        pcim["multi_year_financial_inputs"] = {
            "years_covered": [year],
            "basis_used": "consolidated",
            "scale_pattern": [f"revenue in {year}: 100.0 ₹ crore"],
            "profitability_pattern": [f"opm in {year}: 20.0 %"],
            "return_pattern": [f"roe in {year}: 18.0 %"],
            "cash_conversion_pattern": [f"cfo in {year}: 16.0 ₹ crore"],
            "balance_sheet_pattern": [f"total_debt in {year}: 8.0 ₹ crore"],
            "working_capital_pattern": [],
            "capital_allocation_pattern": [f"Dividend evidence in: {year}"],
            "ownership_pattern": ["Promoter holding tracked across 1 year(s)."],
            "key_strengths": ["Cash conversion remains healthy."],
            "key_concerns": [],
            "missing_data": ["FCF missing"] if not include_fcf else [],
            "investor_questions": [],
            "warnings": ["FCF missing"] if not include_fcf else [],
            "limitations": [],
            "source_artifact": "financial_memory_summary.json",
        }
    if raw_leak:
        pcim["financial_fundamentals_inputs"]["source_chunk"] = "raw leaked text"
    _write_json(company_memory / "pcim_v1.json", pcim)


def test_financial_pcim_validation_passes_with_compact_traceable_sections(tmp_path: Path):
    _seed_financial_year(tmp_path)
    _seed_company_memory(tmp_path)

    payload = build_financial_pcim_validation(company="acme", year="fy24", companies_root=tmp_path / "companies")

    assert payload["status"] in {"pass", "warning"}
    assert not payload["hard_failures"]
    assert any(check["check_name"] == "pcim_financial_section_presence" for check in payload["checks"])


def test_financial_pcim_validation_fails_on_raw_leakage_and_invented_fcf(tmp_path: Path):
    _seed_financial_year(tmp_path, include_fcf=False)
    _seed_company_memory(tmp_path, include_fcf=False, raw_leak=True)
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["cash_conversion_inputs"]["metrics"].append(
        {
            "metric": "fcf",
            "unit": "₹ crore",
            "series": [{"year": "fy24", "value": 12.0, "basis": "consolidated", "source_artifact": "financial_trends.json", "confidence": "medium", "warnings": []}],
            "comparability_warnings": [],
            "source_artifact": "financial_trends.json",
        }
    )
    _write_json(pcim_path, pcim)

    payload = build_financial_pcim_validation(company="acme", year="fy24", companies_root=tmp_path / "companies")

    assert payload["status"] == "fail"
    assert any("Raw financial artifact leakage" in item for item in payload["hard_failures"])
    assert any("FCF is available" in item for item in payload["hard_failures"])


def test_financial_pcim_validation_warns_when_missing_limits_are_not_propagated(tmp_path: Path):
    _seed_financial_year(tmp_path, include_fcf=False, shareholding_status="warning")
    _seed_company_memory(tmp_path, include_fcf=False, include_multi_year=False)
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["financial_quality_inputs"]["by_year"][0]["warnings"] = []
    pcim["financial_quality_inputs"]["by_year"][0]["missing_data"] = []
    pcim["financial_source_manifest"]["warnings"] = []
    pcim["pcim_source_manifest"]["financial_warnings"] = []
    _write_json(pcim_path, pcim)

    payload = build_financial_pcim_validation(company="acme", year="fy24", companies_root=tmp_path / "companies")

    assert payload["status"] == "warning"
    assert any("financial limitation" in item.lower() for item in payload["warnings"])
    assert any("multi_year_financial_inputs is missing" in item for item in payload["warnings"])


def test_financial_quality_scorecard_applies_hard_cap_for_raw_leakage(tmp_path: Path):
    _seed_financial_year(tmp_path)
    _seed_company_memory(tmp_path, raw_leak=True)

    scorecard = build_financial_quality_scorecard(company="acme", companies_root=tmp_path / "companies")

    assert scorecard["status"] == "fail"
    assert scorecard["overall_score"] <= 50


def test_financial_quality_scorecard_penalizes_missing_quality_summary_and_writes_markdown(tmp_path: Path):
    _seed_financial_year(tmp_path)
    _seed_company_memory(tmp_path)
    (tmp_path / "companies" / "acme" / "fy24" / "financials" / "financial_quality_summary.json").unlink()

    outputs = write_financial_quality_scorecard(company="acme", companies_root=tmp_path / "companies")
    scorecard = json.loads(outputs["financial_quality_scorecard.json"].read_text(encoding="utf-8"))
    markdown = outputs["financial_quality_scorecard.md"].read_text(encoding="utf-8")

    assert scorecard["dimensions"]["artifact_completeness"]["score"] < 100
    assert "Financial Quality Scorecard" in markdown
    assert "Overall score" in markdown
