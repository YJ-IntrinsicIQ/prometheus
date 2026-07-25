import json

import pytest

from knowledge.cim_contract import CIMContractBuilder


def _write_year_intelligence(base_dir, company, year):
    intelligence_dir = base_dir / "companies" / company / year / "intelligence"
    intelligence_dir.mkdir(parents=True, exist_ok=True)
    (intelligence_dir / "business_classification.json").write_text(
        json.dumps(
            {
                "business_dnas": ["Enterprise Platform"],
                "question_modules": ["technology"],
                "report_template": "software_v1",
            }
        ),
        encoding="utf-8",
    )
    (intelligence_dir / "business_blueprint.json").write_text(
        json.dumps(
            {
                "metadata": {"version": "1.0", "confidence": 0.8},
                "business_understanding": {
                    "business_summary": "Software platform",
                    "business_model": "Recurring enterprise software",
                    "value_creation": "Workflow automation",
                    "competitive_position": "Embedded platform position",
                },
                "characteristics": [{"name": "Enterprise platform", "confidence": 0.9}],
            }
        ),
        encoding="utf-8",
    )
    (intelligence_dir / "management_summary.json").write_text(
        json.dumps(
            {
                "management_focus_areas": [f"{year} Focus"],
                "major_projects": [f"{year} Project"],
                "major_promises": [f"{year} Promise"],
                "key_initiatives": [f"{year} Initiative"],
                "capital_allocation_actions": [f"{year} Capital"],
                "statistics": {},
            }
        ),
        encoding="utf-8",
    )
    (intelligence_dir / "company_intelligence.json").write_text(
        json.dumps(
            {
                "metadata": {"company": company, "year": year},
                "business": {
                    "dna": {
                        "business_dnas": ["Enterprise Platform"],
                        "question_modules": ["technology"],
                        "report_template": "software_v1",
                    },
                    "industry_profile": {
                        "business_summary": "Software platform",
                        "business_model": "Recurring enterprise software",
                        "value_creation": "Workflow automation",
                        "characteristics": ["Enterprise platform"],
                    },
                    "competitive_position": {
                        "summary": "Embedded platform position",
                        "supporting_modules": ["technology"],
                    },
                },
                "management": {"promises": {"items": []}},
                "operations": {"projects": {"items": []}, "initiatives": {"items": []}},
                "financial": {"capital_allocation": {"items": []}},
                "risk": {"identified": {"items": []}},
                "relationships": {"entities": [], "graph": {}},
                "evidence": {"sources": [], "citations": []},
            }
        ),
        encoding="utf-8",
    )


def _write_company_memory_multi_year(base_dir, company, years):
    multi_year_dir = base_dir / "companies" / company / "company_memory" / "multi_year"
    multi_year_dir.mkdir(parents=True, exist_ok=True)
    (multi_year_dir / "company_year_index.json").write_text(
        json.dumps({"company": company, "years_detected": years, "available_years": years}),
        encoding="utf-8",
    )
    (multi_year_dir / "multi_year_index.json").write_text(
        json.dumps({"company": company, "generated_at": "2026-07-17T00:00:00Z", "years_covered": years, "limitations": []}),
        encoding="utf-8",
    )
    for name, payload in {
        "business_dna_evolution.json": {"timeline": [], "changes_detected": []},
        "strategy_timeline.json": {"timeline": [], "strategy_continuity": [], "strategy_shifts": []},
        "promise_tracker.json": {"promises": [], "fulfilled_promises": [], "repeated_unresolved_promises": []},
        "risk_evolution.json": {"risks": [], "recurring_risks": [], "qa_warnings": []},
        "capital_allocation_timeline.json": {"timeline": [], "capital_allocation_patterns": []},
        "management_consistency.json": {"consistency_observations": [], "repeated_focus_areas": [], "changed_focus_areas": []},
    }.items():
        (multi_year_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _write_year_financials(base_dir, company, year):
    financial_dir = base_dir / "companies" / company / year / "financials"
    financial_dir.mkdir(parents=True, exist_ok=True)
    (financial_dir / "normalized_fundamentals.json").write_text(
        json.dumps(
            {
                "company": company,
                "year": year,
                "preferred_basis": "consolidated",
                "profit_and_loss": {
                    "revenue": {
                        "value_crore": 100.0,
                        "value_original": "100.0",
                        "unit_original": "crore",
                        "basis": "consolidated",
                        "source_page": 12,
                        "source_artifact": "raw_financial_tables.json",
                        "confidence": "high",
                        "warnings": [],
                    },
                    "pat": {
                        "value_crore": 12.0,
                        "value_original": "12.0",
                        "unit_original": "crore",
                        "basis": "consolidated",
                        "source_page": 15,
                        "source_artifact": "raw_financial_tables.json",
                        "confidence": "high",
                        "warnings": [],
                    },
                },
                "balance_sheet": {
                    "net_worth": {
                        "value_crore": 55.0,
                        "value_original": "55.0",
                        "unit_original": "crore",
                        "basis": "consolidated",
                        "source_page": 20,
                        "source_artifact": "raw_financial_tables.json",
                        "confidence": "high",
                        "warnings": [],
                    },
                    "total_debt": {
                        "value_crore": 8.0,
                        "value_original": "8.0",
                        "unit_original": "crore",
                        "basis": "consolidated",
                        "source_page": 21,
                        "source_artifact": "raw_financial_tables.json",
                        "confidence": "high",
                        "warnings": [],
                    },
                    "cash_and_equivalents": {
                        "value_crore": 14.0,
                        "value_original": "14.0",
                        "unit_original": "crore",
                        "basis": "consolidated",
                        "source_page": 22,
                        "source_artifact": "raw_financial_tables.json",
                        "confidence": "high",
                        "warnings": [],
                    },
                },
                "cash_flow": {
                    "cfo": {
                        "value_crore": 16.0,
                        "value_original": "16.0",
                        "unit_original": "crore",
                        "basis": "consolidated",
                        "source_page": 24,
                        "source_artifact": "raw_financial_tables.json",
                        "confidence": "high",
                        "warnings": [],
                    },
                    "capex": {
                        "value_crore": 4.0,
                        "value_original": "4.0",
                        "unit_original": "crore",
                        "basis": "consolidated",
                        "source_page": 25,
                        "source_artifact": "raw_financial_tables.json",
                        "confidence": "high",
                        "warnings": [],
                    },
                },
                "share_data": {
                    "shares_outstanding": {
                        "value_original": "10.0",
                        "unit_original": "crore shares",
                        "basis": "consolidated",
                        "source_page": 26,
                        "source_artifact": "raw_financial_tables.json",
                        "confidence": "medium",
                        "warnings": [],
                    }
                },
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )
    (financial_dir / "financial_ratios.json").write_text(
        json.dumps(
            {
                "company": company,
                "year": year,
                "ratios": {
                    "opm": {"value": 20.0, "unit": "%", "basis": "consolidated", "formula": "ebit / revenue", "confidence": "high", "warnings": []},
                    "npm": {"value": 12.0, "unit": "%", "basis": "consolidated", "formula": "pat / revenue", "confidence": "high", "warnings": []},
                    "roe": {"value": 18.0, "unit": "%", "basis": "consolidated", "formula": "pat / equity", "confidence": "high", "warnings": []},
                    "roce": {"value": 16.0, "unit": "%", "basis": "consolidated", "formula": "ebit / capital employed", "confidence": "high", "warnings": []},
                    "roa": {"value": 9.0, "unit": "%", "basis": "consolidated", "formula": "pat / assets", "confidence": "high", "warnings": []},
                    "cfo_to_pat": {"value": 1.33, "unit": "x", "basis": "consolidated", "formula": "cfo / pat", "confidence": "high", "warnings": []},
                    "fcf_to_pat": {"value": 1.0, "unit": "x", "basis": "consolidated", "formula": "fcf / pat", "confidence": "high", "warnings": []},
                    "eps_basic": {"value": 12.0, "unit": "₹", "basis": "consolidated", "formula": "pat / shares", "confidence": "high", "warnings": []},
                    "book_value_per_share": {"value": 55.0, "unit": "₹", "basis": "consolidated", "formula": "net worth / shares", "confidence": "high", "warnings": []},
                    "debt_to_equity": {"value": 0.15, "unit": "x", "basis": "consolidated", "formula": "debt / equity", "confidence": "high", "warnings": []},
                },
            }
        ),
        encoding="utf-8",
    )
    (financial_dir / "financial_growth.json").write_text(
        json.dumps(
            {
                "company": company,
                "year": year,
                "growth_metrics": {
                    "revenue": [{"metric": "revenue", "current_year": year, "growth_percent": 12.0, "absolute_change": 10.0, "basis": "consolidated", "confidence": "medium", "warnings": []}],
                    "pat": [{"metric": "pat", "current_year": year, "growth_percent": 14.0, "absolute_change": 1.5, "basis": "consolidated", "confidence": "medium", "warnings": []}],
                    "eps_basic": [{"metric": "eps_basic", "current_year": year, "growth_percent": 13.0, "absolute_change": 1.2, "basis": "consolidated", "confidence": "medium", "warnings": []}],
                    "book_value_per_share": [{"metric": "book_value_per_share", "current_year": year, "growth_percent": 10.0, "absolute_change": 5.0, "basis": "consolidated", "confidence": "medium", "warnings": []}],
                },
            }
        ),
        encoding="utf-8",
    )
    (financial_dir / "corporate_actions.json").write_text(
        json.dumps(
            {
                "company": company,
                "year": year,
                "status": "warning",
                "actions": [
                    {
                        "action_type": "dividend",
                        "year": year,
                        "ratio": "",
                        "impact_on_share_count": "none",
                        "impact_on_eps_comparability": "no",
                        "warnings": [],
                    }
                ],
                "per_share_comparability_warnings": ["No dilution adjustments required."],
            }
        ),
        encoding="utf-8",
    )
    (financial_dir / "shareholding_pattern.json").write_text(
        json.dumps(
            {
                "company": company,
                "year": year,
                "status": "pass",
                "items": [
                    {
                        "holder_category": "promoter_holding_percent",
                        "holding_percent": 51.2,
                        "confidence": "high",
                        "warnings": [],
                    }
                ],
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )


def _write_company_financials(base_dir, company, years):
    company_financial_dir = base_dir / "companies" / company / "company_memory" / "financials"
    company_financial_dir.mkdir(parents=True, exist_ok=True)
    (company_financial_dir / "financial_year_index.json").write_text(
        json.dumps(
            {
                "company": company,
                "generated_at": "2026-07-17T00:00:00Z",
                "years_discovered": years,
                "years_used": years,
                "years_skipped": [],
                "year_status": {
                    year: {
                        "financials_available": True,
                        "validation_status": "pass",
                        "reconciliation_status": "pass",
                        "quality_status": "warning",
                        "basis_used": "consolidated",
                        "warnings": [],
                        "limitations": [],
                    }
                    for year in years
                },
                "warnings": ["Only one usable financial year available."] if len(years) == 1 else [],
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    (company_financial_dir / "financial_trends.json").write_text(
        json.dumps(
            {
                "company": company,
                "generated_at": "2026-07-17T00:00:00Z",
                "years_covered": years,
                "basis": "consolidated",
                "basis_policy": {"preferred_basis": "consolidated", "basis_consistency": "consistent", "warnings": []},
                "metric_trends": {
                    "revenue": {"unit": "₹ crore", "series": [{"year": years[0], "value": 100.0, "source_artifact": "normalized_fundamentals.json", "confidence": "high"}]},
                    "pat": {"unit": "₹ crore", "series": [{"year": years[0], "value": 12.0, "source_artifact": "normalized_fundamentals.json", "confidence": "high"}]},
                    "net_worth": {"unit": "₹ crore", "series": [{"year": years[0], "value": 55.0, "source_artifact": "normalized_fundamentals.json", "confidence": "high"}]},
                    "total_assets": {"unit": "₹ crore", "series": [{"year": years[0], "value": 80.0, "source_artifact": "normalized_fundamentals.json", "confidence": "high"}]},
                },
                "cash_conversion_trends": {
                    "cfo": {"unit": "₹ crore", "series": [{"year": years[0], "value": 16.0, "source_artifact": "normalized_fundamentals.json", "confidence": "high"}]},
                    "fcf": {"unit": "₹ crore", "series": [{"year": years[0], "value": 12.0, "source_artifact": "financial_ratios.json", "confidence": "medium"}]},
                    "cfo_to_pat": {"unit": "x", "series": [{"year": years[0], "value": 1.33, "source_artifact": "financial_ratios.json", "confidence": "high"}]},
                    "fcf_to_pat": {"unit": "x", "series": [{"year": years[0], "value": 1.0, "source_artifact": "financial_ratios.json", "confidence": "high"}]},
                    "receivable_days": {"unit": "days", "series": [{"year": years[0], "value": 30.0, "source_artifact": "financial_ratios.json", "confidence": "medium"}]},
                    "cash_conversion_cycle": {"unit": "days", "series": [{"year": years[0], "value": 12.0, "source_artifact": "financial_ratios.json", "confidence": "medium"}]},
                },
                "return_trends": {
                    "roe": {"unit": "%", "series": [{"year": years[0], "value": 18.0, "source_artifact": "financial_ratios.json", "confidence": "high"}]},
                    "roce": {"unit": "%", "series": [{"year": years[0], "value": 16.0, "source_artifact": "financial_ratios.json", "confidence": "high"}]},
                    "roa": {"unit": "%", "series": [{"year": years[0], "value": 9.0, "source_artifact": "financial_ratios.json", "confidence": "high"}]},
                },
                "balance_sheet_trends": {
                    "total_debt": {"unit": "₹ crore", "series": [{"year": years[0], "value": 8.0, "source_artifact": "normalized_fundamentals.json", "confidence": "high"}]},
                    "debt_to_equity": {"unit": "x", "series": [{"year": years[0], "value": 0.15, "source_artifact": "financial_ratios.json", "confidence": "high"}]},
                    "cash_and_equivalents": {"unit": "₹ crore", "series": [{"year": years[0], "value": 14.0, "source_artifact": "normalized_fundamentals.json", "confidence": "high"}]},
                    "reserves": {"unit": "₹ crore", "series": [{"year": years[0], "value": 40.0, "source_artifact": "normalized_fundamentals.json", "confidence": "medium"}]},
                },
                "per_share_trends": {
                    "eps_basic": {"unit": "₹", "series": [{"year": years[0], "value": 12.0, "source_artifact": "financial_ratios.json", "confidence": "high"}]},
                    "eps_diluted": {"unit": "₹", "series": [{"year": years[0], "value": 11.5, "source_artifact": "financial_ratios.json", "confidence": "medium"}]},
                    "book_value_per_share": {"unit": "₹", "series": [{"year": years[0], "value": 55.0, "source_artifact": "financial_ratios.json", "confidence": "high"}]},
                    "dividend_per_share": {"unit": "₹", "series": [{"year": years[0], "value": 2.0, "source_artifact": "corporate_actions.json", "confidence": "medium"}]},
                    "share_count": {"unit": "crore shares", "series": [{"year": years[0], "value": 10.0, "source_artifact": "normalized_fundamentals.json", "confidence": "medium"}]},
                },
                "metric_series": {
                    "revenue": [{"year": years[0], "value": 100.0, "unit": "₹ crore", "basis": "consolidated", "confidence": "high", "source_artifacts": ["normalized_fundamentals.json"], "warnings": []}],
                    "pat": [{"year": years[0], "value": 12.0, "unit": "₹ crore", "basis": "consolidated", "confidence": "high", "source_artifacts": ["normalized_fundamentals.json"], "warnings": []}],
                    "net_worth": [{"year": years[0], "value": 55.0, "unit": "₹ crore", "basis": "consolidated", "confidence": "high", "source_artifacts": ["normalized_fundamentals.json"], "warnings": []}],
                    "total_assets": [{"year": years[0], "value": 80.0, "unit": "₹ crore", "basis": "consolidated", "confidence": "high", "source_artifacts": ["normalized_fundamentals.json"], "warnings": []}],
                    "cfo": [{"year": years[0], "value": 16.0, "unit": "₹ crore", "basis": "consolidated", "confidence": "high", "source_artifacts": ["normalized_fundamentals.json"], "warnings": []}],
                    "capex": [{"year": years[0], "value": 4.0, "unit": "₹ crore", "basis": "consolidated", "confidence": "high", "source_artifacts": ["normalized_fundamentals.json"], "warnings": []}],
                    "fcf": [{"year": years[0], "value": 12.0, "unit": "₹ crore", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_ratios.json"], "warnings": []}],
                    "eps_basic": [{"year": years[0], "value": 12.0, "unit": "per share", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []}],
                    "eps_diluted": [{"year": years[0], "value": 11.5, "unit": "per share", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_ratios.json"], "warnings": []}],
                },
                "ratio_series": {
                    "opm": [{"year": years[0], "value": 20.0, "unit": "%", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []}],
                    "npm": [{"year": years[0], "value": 12.0, "unit": "%", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []}],
                    "roe": [{"year": years[0], "value": 18.0, "unit": "%", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []}],
                    "roce": [{"year": years[0], "value": 16.0, "unit": "%", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []}],
                    "debt_to_equity": [{"year": years[0], "value": 0.15, "unit": "x", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []}],
                    "cfo_to_pat": [{"year": years[0], "value": 1.33, "unit": "x", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []}],
                    "fcf_to_pat": [{"year": years[0], "value": 1.0, "unit": "x", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": []}],
                },
                "warnings": [],
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    (company_financial_dir / "financial_quality_evolution.json").write_text(
        json.dumps(
            {
                "company": company,
                "generated_at": "2026-07-17T00:00:00Z",
                "years_covered": years,
                "evolution": {"growth_quality": {"by_year": [{"year": years[0], "assessment": "insufficient_data", "confidence": "missing", "summary": "Limited.", "highlights": [], "warnings": []}], "latest_assessment": "insufficient_data"}},
                "recurring_strengths": [],
                "recurring_concerns": [],
                "improving_signals": [],
                "deteriorating_signals": [],
                "missing_data_patterns": [],
                "warnings": [],
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    (company_financial_dir / "capital_allocation_financial_timeline.json").write_text(
        json.dumps(
            {
                "company": company,
                "generated_at": "2026-07-17T00:00:00Z",
                "years_covered": years,
                "timeline": [],
                "dividend_pattern": {"years": years, "warnings": []},
                "capex_pattern": {"years": years, "warnings": []},
                "fcf_pattern": {"years": years, "warnings": []},
                "dilution_or_share_issue_pattern": {"years": [], "warnings": []},
                "debt_pattern": {"years": years, "warnings": []},
                "warnings": [],
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    (company_financial_dir / "ownership_evolution.json").write_text(
        json.dumps(
            {
                "company": company,
                "generated_at": "2026-07-17T00:00:00Z",
                "years_covered": years,
                "promoter_holding": [{"year": years[0], "value": 51.2, "source_artifact": "shareholding_pattern.json", "confidence": "high", "warnings": []}],
                "pledge": [],
                "fii": [],
                "dii": [],
                "mutual_funds": [],
                "public": [],
                "institutional_signal": {"years_with_data": [], "note": "Institutional ownership is a signal, not proof of quality."},
                "warnings": [],
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    (company_financial_dir / "financial_memory_summary.json").write_text(
        json.dumps(
            {
                "company": company,
                "generated_at": "2026-07-17T00:00:00Z",
                "status": "warning",
                "years_covered": years,
                "basis_used": "consolidated",
                "summary": {
                    "scale_pattern": ["revenue in fy24: 100.0 ₹ crore"],
                    "profitability_pattern": ["opm in fy24: 20.0 %"],
                    "return_pattern": ["roe in fy24: 18.0 %"],
                    "cash_conversion_pattern": ["cfo in fy24: 16.0 ₹ crore"],
                    "balance_sheet_pattern": ["total_debt in fy24: 8.0 ₹ crore"],
                    "working_capital_pattern": [],
                    "per_share_pattern": ["eps_basic in fy24: 12.0 per share"],
                    "capital_allocation_pattern": ["Dividend evidence in: fy24"],
                    "ownership_pattern": ["Promoter holding tracked across 1 year(s)."],
                },
                "key_strengths": ["Cash conversion remains healthy."],
                "key_concerns": [],
                "missing_data": [],
                "investor_questions": [],
                "warnings": [],
                "limitations": [],
                "source_manifest": {
                    "years_discovered": years,
                    "years_used": years,
                    "years_skipped": [],
                    "basis_policy": {"preferred_basis": "consolidated", "basis_consistency": "consistent", "warnings": []},
                    "financial_artifacts_used": ["financial_year_index.json", "financial_trends.json"],
                },
            }
        ),
        encoding="utf-8",
    )
    (company_financial_dir / "financial_quality_summary.json").write_text(
        json.dumps(
            {
                "company": company,
                "generated_at": "2026-07-17T00:00:00Z",
                "years_covered": years,
                "growth_quality": {"status": "pass", "summary": "Growth remains healthy.", "signals": ["Revenue and PAT grew consistently."]},
                "cash_conversion_quality": {"status": "pass", "summary": "Cash conversion is healthy.", "signals": ["CFO exceeds PAT."], "warnings": []},
                "return_on_capital_quality": {"status": "pass", "summary": "Returns remain solid.", "signals": ["ROCE remained above 15%."], "warnings": []},
                "balance_sheet_strength": {"status": "pass", "summary": "Leverage remains modest.", "signals": ["Debt to equity remains low."], "warnings": []},
                "ownership_quality": {"status": "warning", "summary": "Ownership is stable but shallow.", "warnings": ["Only one year available."]},
                "dilution_and_corporate_action_quality": {"warnings": ["No material comparability issue detected."]},
                "missing_data": [],
                "warnings": [],
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    (company_financial_dir / "financial_driver_attribution.json").write_text(
        json.dumps(
            {
                "company": company,
                "generated_at": "2026-07-17T00:00:00Z",
                "years_covered": years,
                "status": "warning",
                "attributions": [
                    {
                        "metric": "revenue",
                        "movement": "improved",
                        "period": years[0],
                        "possible_driver": "Platform expansion",
                        "driver_type": "order_execution",
                        "supporting_event": "New enterprise platform rollout",
                        "confidence": "medium",
                        "causality_status": "possible",
                        "evidence_ids": [],
                        "source_artifacts": ["financial_trends.json"],
                        "warnings": [],
                        "verification_questions": ["Did customer additions drive the improvement?"],
                    }
                ],
                "warnings": ["Attribution remains provisional."],
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )


def _build_company(tmp_path, company="finco", years=("fy24",)):
    for year in years:
        _write_year_intelligence(tmp_path, company, year)
        _write_year_financials(tmp_path, company, year)
    _write_company_memory_multi_year(tmp_path, company, list(years))
    _write_company_financials(tmp_path, company, list(years))
    return json.loads(CIMContractBuilder(company=company).build()["pcim_v1.json"].read_text()), json.loads(
        (tmp_path / "companies" / company / "company_memory" / "cim_v1.json").read_text()
    )


def test_financials_are_integrated_into_cim_and_compact_pcim(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pcim, cim = _build_company(tmp_path)

    assert "financials" in cim
    assert "financial_intelligence" in cim
    assert cim["financial_intelligence"]["fundamentals"][0]["artifact"]["profit_and_loss"]["revenue"]["value_crore"] == 100.0
    assert cim["financials"]["core_fundamentals"]["revenue"]["value"] == 100.0
    assert pcim["financial_fundamentals_inputs"]["by_year"][0]["key_metrics"][0]["source_artifact"] == "normalized_fundamentals.json"
    assert pcim["financial_trend_inputs"]["metric_trends"][0]["series"][0]["year"] == "fy24"
    assert pcim["financial_growth_inputs"]["by_year"][0]["growth_metrics"][0]["metric"] == "revenue"
    assert pcim["profitability_inputs"]["by_year"][0]["metrics"][0]["metric"] in {"gross_margin", "ebitda_margin", "ebit_margin", "opm", "npm"}
    assert pcim["cash_conversion_inputs"]["metrics"][0]["source_artifact"] == "financial_trends.json"
    assert pcim["financial_driver_inputs"]["source_artifact"] == "financial_driver_attribution.json"
    assert pcim["financial_quality_inputs"]["by_year"][0]["status"] in {"pass", "warning"}
    assert pcim["multi_year_financial_inputs"]["basis_used"] == "consolidated"
    assert pcim["multi_year_financial_inputs"]["scale_pattern"]
    assert pcim["financial_panel_ready"] is True
    assert pcim["financial_source_manifest"]["status"] in {"warning", "pass"}
    assert pcim["pcim_source_manifest"]["financial_status"] in {"warning", "pass"}
    assert "financial_artifacts_used" in pcim["pcim_source_manifest"]
    assert "source_chunk" not in json.dumps(pcim["financial_fundamentals_inputs"])


def test_pcim_uses_precise_share_warning_when_shares_outstanding_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pcim, _cim = _build_company(tmp_path)

    manifest_warnings = pcim["pcim_source_manifest"]["financial_warnings"]
    quality_warnings = pcim["financial_quality_inputs"]["warnings"]
    all_warning_text = " | ".join(manifest_warnings + quality_warnings).lower()
    all_limitations = " | ".join(pcim["financial_source_manifest"].get("limitations", [])).lower()

    assert "weighted average shares missing" in all_warning_text
    assert "diluted shares missing" in all_warning_text
    assert "share count missing" not in all_warning_text
    assert "per-share analysis is limited because weighted average share count is missing." in all_limitations


def test_pcim_financial_manifest_warns_when_company_level_financials_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_intelligence(tmp_path, "warnco", "fy24")
    _write_year_financials(tmp_path, "warnco", "fy24")
    _write_company_memory_multi_year(tmp_path, "warnco", ["fy24"])

    pcim = json.loads(CIMContractBuilder(company="warnco").build()["pcim_v1.json"].read_text())

    assert pcim["pcim_source_manifest"]["financial_status"] == "warning"
    assert any("financial_trends.json" in warning for warning in pcim["pcim_source_manifest"]["financial_warnings"])


def test_pcim_financial_manifest_fails_on_year_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_intelligence(tmp_path, "badfinco", "fy24")
    _write_year_financials(tmp_path, "badfinco", "fy24")
    _write_company_memory_multi_year(tmp_path, "badfinco", ["fy24"])
    _write_company_financials(tmp_path, "badfinco", ["fy23"])

    with pytest.raises(ValueError, match="financial years mismatch company years"):
        CIMContractBuilder(company="badfinco").build()
