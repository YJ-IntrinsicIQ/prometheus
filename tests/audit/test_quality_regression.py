import json
from pathlib import Path

from core.company_context import CompanyContext
from knowledge.quality_regression import (
    parse_company_selector,
    run_quality_regression,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _quality() -> dict:
    return {
        "company_specificity": "high",
        "actionability": "high",
        "investor_relevance": "high",
        "source_proximity": "direct_statement",
        "actor_type": "company",
        "time_specificity": "period_specific",
        "numeric_support": True,
        "confidence": "high",
        "warnings": [],
    }


def _seed_company(tmp_path: Path, company: str, years: list[str], *, include_company_memory: bool = False) -> None:
    for year in years:
        context = CompanyContext(company=company, year=year)
        context.create_directories()
        (context.raw_dir / "annual_report.pdf").write_text("pdf placeholder", encoding="utf-8")
        for filename in (
            "project_discovery_results.json",
            "promise_discovery_results.json",
            "risk_discovery_results.json",
            "capacity_discovery_results.json",
            "capital_allocation_discovery_results.json",
            "initiative_discovery_results.json",
            "commentary_discovery_results.json",
        ):
            _write_json(context.raw_dir / filename, [{"chunk": "The company executed a concrete action.", "page": 5}])

        base_item = {
            "year": year,
            "page": 5,
            "confidence": "high",
            "evidence_quality": _quality(),
        }
        _write_json(context.extracted_dir / "extracted_projects.json", [{**base_item, "project_name": "Project", "description": "Description", "status": "commissioned", "value": "Project", "evidence_ids": ["ev_proj_1"]}])
        _write_json(context.extracted_dir / "extracted_promises.json", [{**base_item, "promise": "Promise", "category": "Growth", "status": "ongoing", "value": "Promise", "evidence_ids": ["ev_prom_1"]}])
        _write_json(context.extracted_dir / "extracted_risks.json", [{**base_item, "risk": "Liquidity pressure", "category": "Liquidity risk", "severity": "medium", "value": "Liquidity pressure", "evidence_ids": ["ev_risk_1"]}])
        _write_json(context.extracted_dir / "extracted_capacity.json", [{**base_item, "capacity_type": "Wafer line", "status": "commissioned", "value": "Wafer line", "evidence_ids": ["ev_cap_1"]}])
        _write_json(context.extracted_dir / "extracted_initiatives.json", [{**base_item, "initiative": "Automation", "category": "Efficiency", "status": "ongoing", "value": "Automation", "evidence_ids": ["ev_init_1"]}])
        _write_json(context.extracted_dir / "extracted_commentary.json", [{"commentary": "Commentary", "value": "Commentary"}])
        _write_json(
            context.extracted_dir / "extracted_capital_allocation.json",
            [{**base_item, "action": "Capacity expansion capex", "category": "Capex", "value": "Capacity expansion capex", "amount": "Rs 100 crore", "evidence_ids": ["ev_ca_1"]}],
        )

        _write_json(context.extracted_dir / "clean_projects.json", json.loads((context.extracted_dir / "extracted_projects.json").read_text(encoding="utf-8")))
        _write_json(context.extracted_dir / "clean_promises.json", json.loads((context.extracted_dir / "extracted_promises.json").read_text(encoding="utf-8")))
        _write_json(context.extracted_dir / "clean_risks.json", json.loads((context.extracted_dir / "extracted_risks.json").read_text(encoding="utf-8")))
        _write_json(context.extracted_dir / "clean_capacity.json", json.loads((context.extracted_dir / "extracted_capacity.json").read_text(encoding="utf-8")))
        _write_json(context.extracted_dir / "clean_initiatives.json", json.loads((context.extracted_dir / "extracted_initiatives.json").read_text(encoding="utf-8")))
        _write_json(
            context.extracted_dir / "clean_capital_allocation.json",
            [{
                **base_item,
                "action": "Capacity expansion capex",
                "category": "Capex",
                "value": "Capacity expansion capex",
                "amount": "Rs 100 crore",
                "evidence_ids": ["ev_ca_1"],
                "canonical_category": "capacity_expansion",
                "capital_allocation_group": "true_capital_deployment",
                "cash_flow_effect": "company_cash_outflow",
                "is_true_capital_deployment": True,
                "reasoning": "Matched capacity expansion keywords.",
            }],
        )
        _write_json(
            context.extracted_dir / "clean_commentary.json",
            {
                "company_management_actions": [
                    {
                        "value": "Management commissioned a new line.",
                        "context_type": "company_management_action",
                        "agency": "company_controlled",
                        "should_feed_management_consistency": True,
                        "should_feed_external_context": False,
                        "confidence": "high",
                        "reasoning": "Direct company action.",
                    }
                ],
                "company_promises": [],
                "company_capabilities": [],
                "company_results": [],
                "risk_responses": [],
                "external_context": [],
                "accounting_disclosures": [],
                "governance_disclosures": [],
                "uncertain_items": [],
                "validation": {"status": "pass", "errors": [], "warnings": []},
            },
        )
        for filename in (
            "extracted_projects",
            "extracted_promises",
            "extracted_risks",
            "extracted_capacity",
            "extracted_capital_allocation",
            "extracted_initiatives",
            "extracted_commentary",
        ):
            _write_json(context.extracted_dir / f"{filename}_selection_metadata.json", {"chunks_selected": 1, "selection_reasons": []})
            _write_json(context.extracted_dir / f"{filename}_llm_call_manifest.json", {"entries": [{"estimated_prompt_tokens": 300}]})

        _write_json(
            context.intelligence_dir / "business_blueprint.json",
            {
                "metadata": {"company": company, "version": "1.0", "confidence": 0.9},
                "business_understanding": {
                    "business_summary": "A manufacturing business.",
                    "business_model": "Produces goods.",
                    "value_creation": "Operations and distribution.",
                    "competitive_position": "Specialized capability.",
                },
                "characteristics": [{"name": "Manufacturing", "confidence": 0.9}],
                "candidate_dna_signals": [{"name": "Manufacturing", "confidence": 0.9, "supporting_reason": "Owns operations.", "evidence_ids": ["ev_proj_1"]}],
                "dnas": [{"name": "Manufacturing", "confidence": 0.9}],
                "dnas_status": "deprecated_not_authoritative",
                "dnas_source": "business_classification",
                "reasoning": [{"statement": "Classification mirrored for compatibility."}],
            },
        )
        _write_json(
            context.intelligence_dir / "business_classification.json",
            {
                "business_dnas": ["Manufacturing"],
                "question_modules": ["capital_allocation"],
                "rationale": ["Company operates manufacturing assets."],
                "evidence_used": ["ev_proj_1"],
                "rejected_dnas": [],
                "confidence": 0.9,
            },
        )
        _write_json(context.intelligence_dir / "company_intelligence.json", {"business": {"dna": {"business_dnas": ["Manufacturing"]}}, "management": {"summary": {"external_context": [], "management_quality_inputs": []}}})
        _write_json(context.intelligence_dir / "management_summary.json", {"routing_validation": {"status": "pass", "errors": [], "warnings": []}, "management_consistency": {"consistency_observations": []}})
        _write_json(context.intelligence_dir / "module_results.json", {"module_results": [{"module": "capital_allocation"}]})
        _write_json(context.intelligence_dir / "discovery_runtime.json", {"statistics": {"retrieved_chunks": 3}})
        _write_json(context.intelligence_dir / "business_understanding_llm_call_manifest.json", {"entries": [{"estimated_prompt_tokens": 400}]})
        _write_json(context.intelligence_dir / "business_intelligence_llm_call_manifest.json", {"entries": [{"estimated_prompt_tokens": 500}]})

    if include_company_memory:
        company_memory = tmp_path / "companies" / company / "company_memory"
        multi_year_dir = company_memory / "multi_year"
        multi_year_dir.mkdir(parents=True, exist_ok=True)
        _write_json(company_memory / "cim_v1.json", {"business": {"dna": {"business_dnas": ["Manufacturing"]}}})
        _write_json(
            company_memory / "pcim_v1.json",
            {
                "company": company,
                "business_identity_manifest": {"official_business_dnas": ["Manufacturing"]},
                "business_understanding": {"latest_business_view": {"business_dnas": [{"value": "Manufacturing"}]}},
                "management_quality_inputs": {"management_grouped_by_year": []},
                "pcim_source_manifest": {
                    "status": "pass",
                    "source_files": [],
                    "years_available": years,
                    "years_covered_in_multi_year_inputs": years,
                    "missing_years": [],
                    "stale_source_warnings": [],
                },
                "multi_year_inputs": {"years_covered": years},
            },
        )
        _write_json(multi_year_dir / "company_year_index.json", {"available_years": years, "years_detected": years})
        _write_json(multi_year_dir / "multi_year_index.json", {"years_covered": years, "limitations": []})


def test_quality_regression_all_pass_fixture_scores_above_90(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_company(tmp_path, "alpha", ["fy24", "fy25"])

    outputs = run_quality_regression(companies=["alpha"])
    payload = json.loads(outputs["prometheus_quality_scorecard.json"].read_text(encoding="utf-8"))

    assert payload["overall_status"] == "pass"
    assert payload["scores"][0]["overall_score"] > 90


def test_quality_regression_stale_pcim_caps_score(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_company(tmp_path, "beta", ["fy24", "fy25"])
    company_memory = tmp_path / "companies" / "beta" / "company_memory"
    multi_year_dir = company_memory / "multi_year"
    multi_year_dir.mkdir(parents=True, exist_ok=True)
    _write_json(company_memory / "cim_v1.json", {"business": {"dna": {"business_dnas": ["Manufacturing"]}}})
    _write_json(
        company_memory / "pcim_v1.json",
        {
            "company": "beta",
            "business_identity_manifest": {"official_business_dnas": ["Manufacturing"]},
            "business_understanding": {"latest_business_view": {"business_dnas": [{"value": "Manufacturing"}]}},
            "management_quality_inputs": {"management_grouped_by_year": []},
            "pcim_source_manifest": {
                "status": "fail",
                "source_files": [],
                "years_available": ["fy24", "fy25"],
                "years_covered_in_multi_year_inputs": ["fy24"],
                "missing_years": ["fy25"],
                "stale_source_warnings": [],
            },
            "multi_year_inputs": {"years_covered": ["fy24"]},
        },
    )
    _write_json(multi_year_dir / "company_year_index.json", {"available_years": ["fy24", "fy25"], "years_detected": ["fy24", "fy25"]})
    _write_json(multi_year_dir / "multi_year_index.json", {"years_covered": ["fy24"], "limitations": ["fy25 not yet covered"]})

    outputs = run_quality_regression(companies=["beta"])
    scorecard = json.loads(outputs["prometheus_quality_scorecard.json"].read_text(encoding="utf-8"))

    assert scorecard["scores"][0]["status"] == "fail"
    assert scorecard["scores"][0]["overall_score"] <= 65


def test_quality_regression_business_identity_conflict_caps_score(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_company(tmp_path, "gamma", ["fy25"])
    blueprint_path = tmp_path / "companies" / "gamma" / "fy25" / "intelligence" / "business_blueprint.json"
    blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
    blueprint["dnas_status"] = "manual_authoritative"
    blueprint["dnas"] = [{"name": "Enterprise Platform", "confidence": 0.9}]
    _write_json(blueprint_path, blueprint)

    outputs = run_quality_regression(companies=["gamma"])
    scorecard = json.loads(outputs["prometheus_quality_scorecard.json"].read_text(encoding="utf-8"))

    assert scorecard["scores"][0]["status"] == "fail"
    assert scorecard["scores"][0]["overall_score"] <= 60


def test_quality_regression_captures_capital_allocation_violation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_company(tmp_path, "delta", ["fy25"])
    cap_path = tmp_path / "companies" / "delta" / "fy25" / "extracted" / "clean_capital_allocation.json"
    _write_json(
        cap_path,
        [{
            "action": "Share split",
            "category": "Share split",
            "value": "Share split",
            "amount": "",
            "year": "fy25",
            "page": 1,
            "evidence_ids": ["ev_ca_2"],
            "confidence": "high",
            "evidence_quality": _quality(),
            "canonical_category": "share_split",
            "capital_allocation_group": "true_capital_deployment",
            "cash_flow_effect": "non_cash",
            "is_true_capital_deployment": False,
            "reasoning": "Incorrectly treated as deployment.",
        }],
    )

    outputs = run_quality_regression(companies=["delta"])
    scorecard = json.loads(outputs["prometheus_quality_scorecard.json"].read_text(encoding="utf-8"))

    assert scorecard["scores"][0]["dimension_scores"]["capital_allocation_taxonomy"] < 100


def test_quality_regression_missing_panel_lowers_only_panel_dimension_when_requested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_company(tmp_path, "epsilon", ["fy25"])

    outputs = run_quality_regression(companies=["epsilon"], include_panel=True)
    scorecard = json.loads(outputs["prometheus_quality_scorecard.json"].read_text(encoding="utf-8"))

    assert scorecard["scores"][0]["status"] != "fail"
    assert scorecard["scores"][0]["dimension_scores"]["panel_readiness"] <= 70


def test_quality_regression_source_chunk_leakage_fails_and_caps_score(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_company(tmp_path, "zeta", ["fy25"])
    company_memory = tmp_path / "companies" / "zeta" / "company_memory"
    multi_year_dir = company_memory / "multi_year"
    multi_year_dir.mkdir(parents=True, exist_ok=True)
    pcim_path = company_memory / "pcim_v1.json"
    _write_json(company_memory / "cim_v1.json", {"business": {"dna": {"business_dnas": ["Manufacturing"]}}})
    _write_json(
        pcim_path,
        {
            "company": "zeta",
            "business_identity_manifest": {"official_business_dnas": ["Manufacturing"]},
            "business_understanding": {"latest_business_view": {"business_dnas": [{"value": "Manufacturing"}]}},
            "management_quality_inputs": {"management_grouped_by_year": []},
            "pcim_source_manifest": {
                "status": "pass",
                "source_files": [],
                "years_available": ["fy25"],
                "years_covered_in_multi_year_inputs": ["fy25"],
                "missing_years": [],
                "stale_source_warnings": [],
            },
            "multi_year_inputs": {"years_covered": ["fy25"], "source_chunk": "raw leak"},
        },
    )
    _write_json(multi_year_dir / "company_year_index.json", {"available_years": ["fy25"], "years_detected": ["fy25"]})
    _write_json(multi_year_dir / "multi_year_index.json", {"years_covered": ["fy25"], "limitations": []})

    outputs = run_quality_regression(companies=["zeta"])
    scorecard = json.loads(outputs["prometheus_quality_scorecard.json"].read_text(encoding="utf-8"))

    assert scorecard["scores"][0]["status"] == "fail"
    assert scorecard["scores"][0]["overall_score"] <= 60


def test_quality_regression_trend_comparison_detects_worsening(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_company(tmp_path, "theta", ["fy25"])
    reports_dir = tmp_path / "reports" / "quality"
    reports_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        reports_dir / "prometheus_quality_scorecard.json",
        {
            "scores": [
                {
                    "company": "theta",
                    "overall_score": 95,
                    "status": "pass",
                    "critical_failures": [],
                    "warnings": [],
                }
            ]
        },
    )
    blueprint_path = tmp_path / "companies" / "theta" / "fy25" / "intelligence" / "business_blueprint.json"
    blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
    blueprint["dnas_status"] = "manual_authoritative"
    blueprint["dnas"] = [{"name": "Enterprise Platform", "confidence": 0.9}]
    _write_json(blueprint_path, blueprint)

    outputs = run_quality_regression(companies=["theta"])
    scorecard = json.loads(outputs["prometheus_quality_scorecard.json"].read_text(encoding="utf-8"))

    assert "theta" in scorecard["trend_comparison"]["companies_worsened"]
    assert (reports_dir / "prometheus_quality_scorecard.previous.json").exists()


def test_quality_regression_works_for_arbitrary_company_names(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_company(tmp_path, "orbitworks", ["fy23", "fy24"])
    _seed_company(tmp_path, "northstar_holdings", ["fy22"])

    outputs = run_quality_regression(companies=parse_company_selector("all"))
    scorecard = json.loads(outputs["prometheus_quality_scorecard.json"].read_text(encoding="utf-8"))

    assert set(scorecard["companies_evaluated"]) == {"orbitworks", "northstar_holdings"}
