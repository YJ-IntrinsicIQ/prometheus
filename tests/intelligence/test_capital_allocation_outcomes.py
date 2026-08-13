import json
from pathlib import Path

from intelligence.capital_allocation_outcomes import CapitalAllocationOutcomesBuilder, validate_capital_allocation_outcomes_payload


def _mkdirs(base_dir: Path, company: str) -> dict[str, Path]:
    root = base_dir / "companies" / company / "company_memory"
    financial_dir = root / "financials"
    investor_dir = financial_dir / "investor_financial_modules"
    projects_dir = root / "projects"
    capacity_dir = root / "capacity"
    commitments_dir = root / "management_commitments"
    risks_dir = root / "risks"
    for path in (investor_dir, projects_dir, capacity_dir, commitments_dir, risks_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "financial": financial_dir,
        "investor": investor_dir,
        "projects": projects_dir,
        "capacity": capacity_dir,
        "commitments": commitments_dir,
        "risks": risks_dir,
    }


def _write_json(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_capacity_expansion_fixture(base_dir: Path, company: str):
    paths = _mkdirs(base_dir, company)
    financial_dir = paths["financial"]
    investor_dir = paths["investor"]
    capacity_dir = paths["capacity"]
    projects_dir = paths["projects"]
    commitments_dir = paths["commitments"]
    risks_dir = paths["risks"]

    _write_json(
        financial_dir / "capital_allocation_financial_timeline.json",
        {
            "company": company,
            "generated_at": "2026-08-08T00:00:00Z",
            "years_covered": ["fy23", "fy24"],
            "timeline": [
                {
                    "year": "fy23",
                    "true_capital_deployment": [
                        {
                            "value": "Capacity expansion at Chennai plant",
                            "category": "capacity_expansion",
                            "canonical_category": "capacity_expansion",
                            "capital_allocation_group": "true_capital_deployment",
                            "source_year": "fy23",
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "X1",
                            "evidence_ids": ["e1"],
                            "status": "Planned",
                            "confidence": "high",
                            "source_page": 10,
                            "reasoning": "Expand capacity",
                        }
                    ],
                    "shareholder_returns": [],
                    "financing_actions": [],
                    "treasury_actions": [],
                    "related_party_capital_flows": [],
                    "corporate_actions_non_cash_or_admin": [],
                    "ownership_transfer_non_company_cashflow": [],
                    "accounting_or_disclosure_only": [],
                    "uncertain": [],
                },
                {
                    "year": "fy24",
                    "true_capital_deployment": [
                        {
                            "value": "Capacity expansion at Chennai plant",
                            "category": "capacity_expansion",
                            "canonical_category": "capacity_expansion",
                            "capital_allocation_group": "true_capital_deployment",
                            "source_year": "fy24",
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "X2",
                            "evidence_ids": ["e2"],
                            "status": "Commissioned",
                            "confidence": "high",
                            "source_page": 12,
                            "reasoning": "Plant commissioned",
                        }
                    ],
                    "shareholder_returns": [],
                    "financing_actions": [],
                    "treasury_actions": [],
                    "related_party_capital_flows": [],
                    "corporate_actions_non_cash_or_admin": [],
                    "ownership_transfer_non_company_cashflow": [],
                    "accounting_or_disclosure_only": [],
                    "uncertain": [],
                },
            ],
            "dividend_pattern": [],
            "capex_pattern": [],
            "fcf_pattern": [],
            "dilution_or_share_issue_pattern": [],
            "debt_pattern": [],
            "warnings": [],
            "limitations": [],
        },
    )
    _write_json(
        investor_dir / "capital_allocation_roi_ledger.json",
        {
            "company": company,
            "generated_at": "2026-08-08T00:00:00Z",
            "years_covered": ["fy23", "fy24"],
            "entries": [
                {
                    "fiscal_year": "fy23",
                    "capital_raised": None,
                    "retained_earnings": None,
                    "capex_deployed": 12.0,
                    "working_capital_deployed": None,
                    "product_development_or_intangible_investment": None,
                    "debt_repayment": None,
                    "dividends": None,
                    "buybacks": None,
                    "acquisitions": None,
                    "related_party_flows": None,
                    "unutilised_issue_proceeds": None,
                    "capital_allocation_event_type": "operating_reinvestment",
                    "amount": 12.0,
                    "purpose": "Expand capacity",
                    "source": ["financial_memory_summary.json"],
                    "reliability": "usable",
                    "investor_interpretation": "Capital deployed into capacity.",
                    "roi_measurability_status": "partially_measurable",
                    "follow_up_questions": [],
                },
                {
                    "fiscal_year": "fy24",
                    "capital_raised": None,
                    "retained_earnings": None,
                    "capex_deployed": 18.0,
                    "working_capital_deployed": None,
                    "product_development_or_intangible_investment": None,
                    "debt_repayment": None,
                    "dividends": None,
                    "buybacks": None,
                    "acquisitions": None,
                    "related_party_flows": None,
                    "unutilised_issue_proceeds": None,
                    "capital_allocation_event_type": "operating_reinvestment",
                    "amount": 18.0,
                    "purpose": "Expand capacity",
                    "source": ["financial_memory_summary.json"],
                    "reliability": "usable",
                    "investor_interpretation": "Plant commissioned.",
                    "roi_measurability_status": "partially_measurable",
                    "follow_up_questions": [],
                },
            ],
            "warnings": [],
            "limitations": [],
        },
    )
    _write_json(
        financial_dir / "financial_memory_summary.json",
        {
            "company": company,
            "generated_at": "2026-08-08T00:00:00Z",
            "summary": {
                "scale_pattern": ["revenue in fy24: 120 ₹ crore", "revenue in fy23: 100 ₹ crore"],
                "profitability_pattern": ["opm in fy24: 20 %"],
                "return_pattern": ["roce in fy24: 15 %"],
                "cash_conversion_pattern": ["cfo in fy24: 10 ₹ crore"],
                "balance_sheet_pattern": ["net_debt in fy24: -5 ₹ crore"],
                "per_share_pattern": ["eps_basic in fy24: 2.5 ₹/share"],
                "working_capital_pattern": ["cash_conversion_cycle in fy24: 30 days"],
                "capital_allocation_pattern": ["Capacity evidence in: fy23, fy24"],
            },
        },
    )
    _write_json(
        financial_dir / "financial_driver_attribution.json",
        {
            "company": company,
            "generated_at": "2026-08-08T00:00:00Z",
            "years_covered": ["fy23", "fy24"],
            "status": "pass",
            "attributions": [
                {
                    "metric": "revenue",
                    "period": "fy23->fy24",
                    "observed_change": "Revenue improved",
                    "possible_driver": "Capacity expansion",
                    "supporting_event": "Capacity expansion at Chennai plant",
                    "driver_type": "order_execution",
                    "confidence": "medium",
                    "source_artifacts": ["financial_memory_summary.json"],
                    "evidence_ids": ["e1"],
                }
            ],
            "warnings": [],
            "limitations": [],
        },
    )
    _write_json(
        capacity_dir / "capacity_registry.json",
        {
            "company": company,
            "generated_at": "2026-08-08T00:00:00Z",
            "capacity_count": 1,
            "capacity_items": [
                {
                    "capacity_id": "CP-1",
                    "capacity_name": "Chennai plant expansion",
                    "normalized_name": "Chennai plant expansion",
                    "capacity_type": "manufacturing",
                    "purpose": "Expand capacity",
                    "economic_relevance": "Higher throughput",
                    "current_status": "operational",
                    "latest_period": "fy24",
                    "announcement_period": "fy23",
                    "source_references": [{"source_year": "fy23"}],
                }
            ],
        },
    )
    _write_json(capacity_dir / "capacity_timelines.json", {"company": company, "timelines": []})
    _write_json(projects_dir / "projects_registry.json", {"company": company, "project_count": 0, "projects": []})
    _write_json(projects_dir / "project_timelines.json", {"company": company, "timelines": []})
    _write_json(projects_dir / "project_assessments.json", {"company": company, "assessments": []})
    _write_json(commitments_dir / "management_commitments.json", {"company": company, "commitment_count": 0, "commitments": []})
    _write_json(risks_dir / "risk_registry.json", {"company": company, "risk_count": 0, "risks": []})
    _write_json(risks_dir / "risk_timelines.json", {"company": company, "timelines": []})
    _write_json(risks_dir / "risk_assessments.json", {"company": company, "assessments": []})


def _write_dividend_fixture(base_dir: Path, company: str):
    paths = _mkdirs(base_dir, company)
    financial_dir = paths["financial"]
    investor_dir = paths["investor"]

    timeline_years = []
    ledger_entries = []
    for year, source_item_id, amount in (("fy23", "D1", -11.1), ("fy24", "D2", -12.2)):
        timeline_years.append(
            {
                "year": year,
                "true_capital_deployment": [],
                "shareholder_returns": [
                    {
                        "value": "Dividend paid",
                        "category": "dividend_paid",
                        "canonical_category": "dividend_paid",
                        "capital_allocation_group": "shareholder_returns",
                        "source_year": year,
                        "source_artifact": "company_intelligence.json",
                        "source_item_id": source_item_id,
                        "evidence_ids": [f"e{year[-1]}"],
                        "status": "Paid",
                        "confidence": "high",
                        "source_page": 20,
                        "reasoning": "Capital returned to shareholders.",
                        "amount": amount,
                    }
                ],
                "financing_actions": [],
                "treasury_actions": [],
                "related_party_capital_flows": [],
                "corporate_actions_non_cash_or_admin": [],
                "ownership_transfer_non_company_cashflow": [],
                "accounting_or_disclosure_only": [],
                "uncertain": [],
            }
        )
        ledger_entries.append(
            {
                "fiscal_year": year,
                "capital_raised": None,
                "retained_earnings": None,
                "capex_deployed": None,
                "working_capital_deployed": None,
                "product_development_or_intangible_investment": None,
                "debt_repayment": None,
                "dividends": amount,
                "buybacks": None,
                "acquisitions": None,
                "related_party_flows": None,
                "unutilised_issue_proceeds": None,
                "capital_allocation_event_type": "shareholder_return",
                "amount": amount,
                "purpose": "Capital returned to shareholders.",
                "source": ["financial_memory_summary.json"],
                "reliability": "usable",
                "investor_interpretation": "Capital is being returned to shareholders.",
                "roi_measurability_status": "not_yet_measurable",
                "follow_up_questions": [],
            }
        )

    _write_json(
        financial_dir / "capital_allocation_financial_timeline.json",
        {
            "company": company,
            "generated_at": "2026-08-08T00:00:00Z",
            "years_covered": ["fy23", "fy24"],
            "timeline": timeline_years,
            "dividend_pattern": [],
            "capex_pattern": [],
            "fcf_pattern": [],
            "dilution_or_share_issue_pattern": [],
            "debt_pattern": [],
            "warnings": [],
            "limitations": [],
        },
    )
    _write_json(
        investor_dir / "capital_allocation_roi_ledger.json",
        {
            "company": company,
            "generated_at": "2026-08-08T00:00:00Z",
            "years_covered": ["fy23", "fy24"],
            "entries": ledger_entries,
            "warnings": [],
            "limitations": [],
        },
    )
    _write_json(financial_dir / "financial_memory_summary.json", {"company": company, "summary": {"capital_allocation_pattern": []}})
    _write_json(financial_dir / "financial_driver_attribution.json", {"company": company, "attributions": []})
    _write_json(paths["capacity"] / "capacity_registry.json", {"company": company, "capacity_count": 0, "capacity_items": []})
    _write_json(paths["capacity"] / "capacity_timelines.json", {"company": company, "timelines": []})
    _write_json(paths["projects"] / "projects_registry.json", {"company": company, "project_count": 0, "projects": []})
    _write_json(paths["projects"] / "project_timelines.json", {"company": company, "timelines": []})
    _write_json(paths["projects"] / "project_assessments.json", {"company": company, "assessments": []})
    _write_json(paths["commitments"] / "management_commitments.json", {"company": company, "commitment_count": 0, "commitments": []})
    _write_json(paths["risks"] / "risk_registry.json", {"company": company, "risk_count": 0, "risks": []})
    _write_json(paths["risks"] / "risk_timelines.json", {"company": company, "timelines": []})
    _write_json(paths["risks"] / "risk_assessments.json", {"company": company, "assessments": []})


def test_capital_allocation_outcomes_builder_links_and_progresses(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_capacity_expansion_fixture(tmp_path, "acme")

    builder = CapitalAllocationOutcomesBuilder(company="acme")
    written = builder.build()

    output_dir = tmp_path / "companies" / "acme" / "company_memory" / "capital_allocation_outcomes"
    outcomes = json.loads((output_dir / "capital_allocation_outcomes.json").read_text(encoding="utf-8"))
    timelines = json.loads((output_dir / "capital_allocation_timelines.json").read_text(encoding="utf-8"))
    assessments = json.loads((output_dir / "capital_allocation_assessments.json").read_text(encoding="utf-8"))
    validation = json.loads((output_dir / "capital_allocation_validation.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_dir / "capital_allocation_manifest.json").read_text(encoding="utf-8"))

    assert validation["status"] == "pass"
    assert manifest["allocation_candidates"] == 2
    assert outcomes["allocation_count"] == 1
    assert timelines["timeline_count"] == 1
    assert assessments["assessment_count"] == 1
    assert assessments["latest_period"] == "fy24"
    assert assessments["assessments"][0]["latest_period"] == "fy24"
    assert outcomes["allocations"][0]["current_status"] == "deployed"
    assert outcomes["allocations"][0]["outcome_status"] in {"early_evidence", "partially_observed", "clearly_observed"}
    assert outcomes["allocations"][0]["linked_capacity_ids"] == ["CP-1"]
    assert outcomes["allocations"][0]["return_evidence"]
    assert written["capital_allocation_outcomes.json"] == Path("companies") / "acme" / "company_memory" / "capital_allocation_outcomes" / "capital_allocation_outcomes.json"


def test_capital_allocation_outcomes_builder_merges_duplicate_wording(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_dividend_fixture(tmp_path, "acme")

    CapitalAllocationOutcomesBuilder(company="acme").build()
    output_dir = tmp_path / "companies" / "acme" / "company_memory" / "capital_allocation_outcomes"
    outcomes = json.loads((output_dir / "capital_allocation_outcomes.json").read_text(encoding="utf-8"))

    assert outcomes["allocation_count"] == 1
    assert outcomes["allocations"][0]["allocation_category"] == "dividend"
    assert outcomes["allocations"][0]["deployment_periods"] == ["fy23", "fy24"]


def test_capital_allocation_outcomes_validator_catches_unsupported_outcome():
    payload = {
        "company": "acme",
        "generated_at": "2026-08-08T00:00:00Z",
        "years_covered": ["fy23"],
        "allocation_count": 1,
        "allocations": [
            {
                "allocation_id": "CAO-0001",
                "allocation_category": "capacity_expansion",
                "allocation_name": "Capacity expansion",
                "normalized_name": "capacity expansion",
                "first_observed_period": "fy23",
                "deployment_periods": ["fy23"],
                "amount": 10.0,
                "amount_basis": "source_item",
                "funding_source": "operating_cash_flow",
                "linked_project_ids": [],
                "linked_capacity_ids": [],
                "linked_commitment_ids": [],
                "linked_risk_ids": [],
                "linked_acquisition_ids_if_available": [],
                "stated_rationale": "Expand capacity",
                "inferred_business_purpose": "Expand capacity",
                "current_status": "deployed",
                "outcome_status": "clearly_observed",
                "progression_summary": "fy23 -> fy24",
                "operating_outcome": "",
                "financial_outcome": "",
                "per_share_outcome": "",
                "balance_sheet_outcome": "",
                "return_evidence": [],
                "opportunity_cost_notes": "",
                "what_changed": "",
                "why_it_changed": "",
                "conviction_impact": "strengthened",
                "investor_implication": "Execution appears on track.",
                "confidence": {"level": "medium", "basis": ["synthetic"], "limitations": []},
                "evidence_status": "partial",
                "source_references": [{"source_year": "fy23", "source_artifact": "capital_allocation_timeline.json"}],
                "unresolved_questions": [],
            }
        ],
        "warnings": [],
        "limitations": [],
    }
    timelines = {
        "company": "acme",
        "generated_at": "2026-08-08T00:00:00Z",
        "years_covered": ["fy23"],
        "timeline_count": 1,
        "timelines": [
            {
                "allocation_id": "CAO-0001",
                "allocation_name": "Capacity expansion",
                "allocation_category": "capacity_expansion",
                "normalized_name": "capacity expansion",
                "deployment_periods": ["fy23"],
                "source_references": [{"source_year": "fy23", "source_artifact": "capital_allocation_timeline.json"}],
                "events": [
                    {
                        "event_id": "CAO-0001-E001",
                        "stream_type": "capital_allocation_outcomes",
                        "subject_id": "CAO-0001",
                        "period": "fy23",
                        "sequence": 1,
                        "event_type": "announcement",
                        "title": "Capacity expansion",
                        "description": "Expand capacity",
                        "evidence_status": "supported",
                        "confidence": {"level": "medium", "basis": ["synthetic"], "limitations": []},
                        "source_references": [{"source_year": "fy23", "source_artifact": "capital_allocation_timeline.json"}],
                        "metadata": {"current_status": "deployed", "outcome_status": "clearly_observed"},
                    }
                ],
            }
        ],
        "warnings": [],
        "limitations": [],
    }
    assessments = {
        "company": "acme",
        "generated_at": "2026-08-08T00:00:00Z",
        "years_covered": ["fy23"],
        "assessment_count": 1,
        "assessments": [
            {
                "allocation_id": "CAO-0001",
                "allocation_category": "capacity_expansion",
                "allocation_name": "Capacity expansion",
                "current_status": "deployed",
                "outcome_status": "clearly_observed",
                "what_changed": "A new outcome appeared.",
                "why_it_changed": "Later evidence arrived.",
                "conviction_impact": "strengthened",
                "investor_implication": "Execution appears on track.",
                "operating_outcome": "",
                "financial_outcome": "",
                "per_share_outcome": "",
                "balance_sheet_outcome": "",
                "return_evidence": [],
                "unresolved_questions": [],
                "evidence_status": "partial",
                "confidence": {"level": "medium", "basis": ["synthetic"], "limitations": []},
            }
        ],
        "warnings": [],
        "limitations": [],
    }

    validation = validate_capital_allocation_outcomes_payload(payload, timelines_payload=timelines, assessments_payload=assessments)
    assert validation["status"] == "fail"
    assert any(issue["code"] == "unsupported_outcome" for issue in validation["issues"])
