import json
from pathlib import Path

from core.company_context import CompanyContext
from knowledge.artifact_audit import run_company_artifact_audit


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


def _base_year_context(tmp_path: Path, company: str = "cleanco", year: str = "fy25") -> CompanyContext:
    context = CompanyContext(company=company, year=year)
    context.create_directories()
    return context


def _seed_clean_year(tmp_path: Path, company: str = "cleanco", year: str = "fy25") -> CompanyContext:
    context = _base_year_context(tmp_path, company=company, year=year)
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

    _write_json(
        context.extracted_dir / "extracted_projects.json",
        [{
            "project_name": "Plant expansion",
            "description": "The company commissioned a plant expansion.",
            "status": "commissioned",
            "value": "Plant expansion",
            "year": year,
            "page": 5,
            "evidence_ids": ["ev_proj_1"],
            "confidence": "high",
            "evidence_quality": _quality(),
        }],
    )
    _write_json(
        context.extracted_dir / "extracted_promises.json",
        [{
            "promise": "Expand exports",
            "category": "Growth",
            "status": "ongoing",
            "value": "Expand exports",
            "year": year,
            "page": 6,
            "evidence_ids": ["ev_prom_1"],
            "confidence": "high",
            "evidence_quality": _quality(),
        }],
    )
    _write_json(
        context.extracted_dir / "extracted_risks.json",
        [{
            "risk": "Liquidity pressure",
            "category": "Liquidity risk",
            "severity": "medium",
            "value": "Liquidity pressure",
            "year": year,
            "page": 7,
            "evidence_ids": ["ev_risk_1"],
            "confidence": "high",
            "evidence_quality": _quality(),
        }],
    )
    _write_json(
        context.extracted_dir / "extracted_capacity.json",
        [{
            "capacity_type": "Wafer line",
            "status": "commissioned",
            "value": "Wafer line",
            "year": year,
            "page": 8,
            "evidence_ids": ["ev_cap_1"],
            "confidence": "high",
            "evidence_quality": _quality(),
        }],
    )
    _write_json(
        context.extracted_dir / "extracted_capital_allocation.json",
        [{
            "action": "Capacity expansion capex",
            "category": "Capex",
            "value": "Capacity expansion capex",
            "amount": "Rs 100 crore",
            "year": year,
            "page": 9,
            "evidence_ids": ["ev_ca_1"],
            "confidence": "high",
            "evidence_quality": _quality(),
        }],
    )
    _write_json(
        context.extracted_dir / "extracted_initiatives.json",
        [{
            "initiative": "Automation initiative",
            "category": "Efficiency",
            "status": "ongoing",
            "value": "Automation initiative",
            "year": year,
            "page": 10,
            "evidence_ids": ["ev_init_1"],
            "confidence": "high",
            "evidence_quality": _quality(),
        }],
    )
    _write_json(
        context.extracted_dir / "extracted_commentary.json",
        [{"commentary": "The company expanded exports.", "value": "Expanded exports"}],
    )

    clean_payloads = {
        "clean_projects.json": json.loads((context.extracted_dir / "extracted_projects.json").read_text(encoding="utf-8")),
        "clean_promises.json": json.loads((context.extracted_dir / "extracted_promises.json").read_text(encoding="utf-8")),
        "clean_risks.json": json.loads((context.extracted_dir / "extracted_risks.json").read_text(encoding="utf-8")),
        "clean_capacity.json": json.loads((context.extracted_dir / "extracted_capacity.json").read_text(encoding="utf-8")),
        "clean_initiatives.json": json.loads((context.extracted_dir / "extracted_initiatives.json").read_text(encoding="utf-8")),
        "clean_capital_allocation.json": [{
            "action": "Capacity expansion capex",
            "category": "Capex",
            "value": "Capacity expansion capex",
            "amount": "Rs 100 crore",
            "year": year,
            "page": 9,
            "evidence_ids": ["ev_ca_1"],
            "confidence": "high",
            "evidence_quality": _quality(),
            "canonical_category": "capacity_expansion",
            "capital_allocation_group": "true_capital_deployment",
            "cash_flow_effect": "company_cash_outflow",
            "is_true_capital_deployment": True,
            "reasoning": "Matched capacity expansion keywords.",
        }],
    }
    for filename, payload in clean_payloads.items():
        _write_json(context.extracted_dir / filename, payload)

    _write_json(
        context.extracted_dir / "clean_commentary.json",
        {
            "company_management_actions": [
                {
                    "value": "Management commissioned a new wafer line.",
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
                "business_summary": "A semiconductor manufacturing business with export exposure.",
                "business_model": "Manufactures semiconductor materials.",
                "value_creation": "Capacity and export execution.",
                "competitive_position": "Specialized manufacturing capability.",
            },
            "characteristics": [{"name": "Semiconductor manufacturing", "confidence": 0.9}],
            "candidate_dna_signals": [
                {"name": "Manufacturing", "confidence": 0.9, "supporting_reason": "Owns and runs manufacturing assets.", "evidence_ids": ["ev_proj_1"]},
                {"name": "Semiconductor", "confidence": 0.9, "supporting_reason": "Operates semiconductor-oriented capacity.", "evidence_ids": ["ev_cap_1"]},
            ],
            "dnas": [
                {"name": "Manufacturing", "confidence": 0.9},
                {"name": "Semiconductor", "confidence": 0.9},
            ],
            "dnas_status": "deprecated_not_authoritative",
            "dnas_source": "business_classification",
            "reasoning": [{"statement": "Classification is mirrored only for compatibility."}],
        },
    )
    _write_json(
        context.intelligence_dir / "business_classification.json",
        {
            "business_dnas": ["Manufacturing", "Semiconductor"],
            "question_modules": ["capital_allocation", "technology"],
            "rationale": ["Company operates semiconductor manufacturing capacity."],
            "evidence_used": ["ev_proj_1", "ev_cap_1"],
            "rejected_dnas": [],
            "confidence": 0.9,
        },
    )
    _write_json(
        context.intelligence_dir / "company_intelligence.json",
        {
            "business": {"dna": {"business_dnas": ["Manufacturing", "Semiconductor"]}},
            "management": {"summary": {"external_context": [], "management_quality_inputs": []}},
        },
    )
    _write_json(
        context.intelligence_dir / "management_summary.json",
        {
            "routing_validation": {"status": "pass", "errors": [], "warnings": []},
            "management_consistency": {"consistency_observations": []},
        },
    )
    _write_json(context.intelligence_dir / "module_results.json", {"module_results": [{"module": "technology"}]})
    _write_json(context.intelligence_dir / "discovery_runtime.json", {"statistics": {"retrieved_chunks": 3}})
    _write_json(context.intelligence_dir / "business_understanding_llm_call_manifest.json", {"entries": [{"estimated_prompt_tokens": 400}]})
    _write_json(context.intelligence_dir / "business_intelligence_llm_call_manifest.json", {"entries": [{"estimated_prompt_tokens": 500}]})
    return context


def test_clean_company_audit_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_clean_year(tmp_path, year="fy24")
    _seed_clean_year(tmp_path, year="fy25")

    outputs = run_company_artifact_audit("cleanco")
    payload = json.loads(outputs["company_artifact_audit.json"].read_text(encoding="utf-8"))

    assert payload["status"] == "pass"
    assert payload["years_detected"] == ["fy24", "fy25"]
    assert outputs["company_artifact_audit.md"].exists()


def test_stale_pcim_is_detected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_clean_year(tmp_path, company="staleco", year="fy24")
    _seed_clean_year(tmp_path, company="staleco", year="fy25")

    company_memory = tmp_path / "companies" / "staleco" / "company_memory"
    multi_year_dir = company_memory / "multi_year"
    multi_year_dir.mkdir(parents=True, exist_ok=True)
    _write_json(multi_year_dir / "company_year_index.json", {"available_years": ["fy24", "fy25"], "years_detected": ["fy24", "fy25"]})
    _write_json(multi_year_dir / "multi_year_index.json", {"years_covered": ["fy24"], "limitations": ["fy25 not yet covered"]})
    _write_json(
        company_memory / "pcim_v1.json",
        {
            "company": "staleco",
            "pcim_source_manifest": {
                "status": "warning",
                "source_files": [],
                "years_available": ["fy24"],
                "years_covered_in_multi_year_inputs": ["fy24"],
                "missing_years": [],
                "stale_source_warnings": [],
            },
            "multi_year_inputs": {"years_covered": ["fy24"]},
        },
    )

    outputs = run_company_artifact_audit("staleco")
    payload = json.loads(outputs["company_artifact_audit.json"].read_text(encoding="utf-8"))

    assert payload["status"] == "fail"
    assert any(check["check_name"] == "pcim_freshness" and check["status"] == "fail" for check in payload["checks"])


def test_business_identity_conflict_fails_audit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _seed_clean_year(tmp_path, company="conflictco")
    blueprint = json.loads((context.intelligence_dir / "business_blueprint.json").read_text(encoding="utf-8"))
    blueprint["dnas_status"] = "manual_authoritative"
    blueprint["dnas"] = [{"name": "Enterprise Platform", "confidence": 0.9}]
    _write_json(context.intelligence_dir / "business_blueprint.json", blueprint)

    outputs = run_company_artifact_audit("conflictco")
    payload = json.loads(outputs["company_artifact_audit.json"].read_text(encoding="utf-8"))

    assert payload["status"] == "fail"
    assert any("Business identity contract status" in check["message"] for check in payload["checks"])


def test_capital_allocation_violation_fails_audit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _seed_clean_year(tmp_path, company="capviolco")
    _write_json(
        context.extracted_dir / "clean_capital_allocation.json",
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

    outputs = run_company_artifact_audit("capviolco")
    payload = json.loads(outputs["company_artifact_audit.json"].read_text(encoding="utf-8"))

    assert payload["status"] == "fail"
    assert any(check["check_name"] == "capital_allocation_taxonomy" and check["status"] == "fail" for check in payload["checks"])


def test_panel_qa_failure_fails_audit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_clean_year(tmp_path, company="panelco")
    company_memory = tmp_path / "companies" / "panelco" / "company_memory"
    _write_json(company_memory / "pcim_v1.json", {"company": "panelco", "pcim_source_manifest": {"status": "pass", "source_files": [], "stale_source_warnings": []}})
    panel_dir = company_memory / "investor_panel"
    panel_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        panel_dir / "committee_synthesis.json",
        {
            "company": "panelco",
            "overall_committee_view": {"summary": "Summary", "confidence": "medium", "dominant_tension": "Tension"},
            "areas_of_agreement": [],
            "areas_of_disagreement": [],
            "strongest_positive_signals": [],
            "most_important_risks": [],
            "critical_unknowns": [],
            "investigation_questions": [],
            "evidence_ids": [],
            "evidence_quality_notes": [],
            "synthesis_limits": [],
            "analysts_considered": [],
            "missing_analysts": [],
            "excluded_analysts": [],
            "years_considered": ["fy25"],
            "analysis_mode": "committee_synthesis_v1",
            "generated_at": "2026-07-15T00:00:00Z",
            "evidence_grounding_status": "pass",
            "evidence_id_normalization": {"applied": True, "replacements": [], "unresolved_ids": []},
        },
    )
    (panel_dir / "committee_brief.md").write_text("bad brief", encoding="utf-8")
    _write_json(panel_dir / "committee_brief_qa.json", {"status": "fail", "warnings": [], "failures": ["required_sections"]})

    outputs = run_company_artifact_audit("panelco")
    payload = json.loads(outputs["company_artifact_audit.json"].read_text(encoding="utf-8"))

    assert payload["status"] == "fail"
    assert any("committee brief QA failed" in check["message"] for check in payload["checks"])
