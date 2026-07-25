import json
from pathlib import Path

import pytest

from knowledge.cim_contract import CIMContractBuilder
from pipelines import run_company_pipeline


def _write_year_artifacts(base_dir: Path, company: str, year: str, *, complete: bool = True):
    intelligence_dir = base_dir / "companies" / company / year / "intelligence"
    intelligence_dir.mkdir(parents=True, exist_ok=True)

    classification = {
        "business_dnas": ["Enterprise Platform", "Compliance Infrastructure"],
        "question_modules": ["technology", "platform_dependency"],
        "report_template": "software_v1",
        "confidence": 0.84,
        "rationale": ["Platform and compliance signals are present."],
        "evidence_used": ["API-first platform", "Security controls"],
    }
    blueprint = {
        "metadata": {"version": "1.0", "confidence": 0.83},
        "business_understanding": {
            "business_summary": f"{company} {year} summary",
            "business_model": f"{company} {year} model",
            "value_creation": f"{company} {year} value creation",
            "competitive_position": f"{company} {year} competitive position",
        },
        "characteristics": [
            {"name": f"{year} platform scale", "confidence": 0.9},
            {"name": f"{year} compliance controls", "confidence": 0.88},
        ],
    }

    (intelligence_dir / "business_classification.json").write_text(
        json.dumps(classification),
        encoding="utf-8",
    )
    (intelligence_dir / "business_blueprint.json").write_text(
        json.dumps(blueprint),
        encoding="utf-8",
    )

    if not complete:
        return

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
                        "business_dnas": classification["business_dnas"],
                        "question_modules": classification["question_modules"],
                        "report_template": classification["report_template"],
                    },
                    "industry_profile": {
                        "business_summary": blueprint["business_understanding"]["business_summary"],
                        "business_model": blueprint["business_understanding"]["business_model"],
                        "value_creation": blueprint["business_understanding"]["value_creation"],
                        "characteristics": [item["name"] for item in blueprint["characteristics"]],
                    },
                    "competitive_position": {
                        "summary": blueprint["business_understanding"]["competitive_position"],
                        "supporting_modules": ["technology", "platform_dependency"],
                    },
                },
                "management": {
                    "promises": {
                        "items": [
                            {
                                "id": f"PROM-{year}",
                                "promise": f"{year} Promise",
                                "category": "strategic objective",
                                "page": 21,
                                "source_chunk": f"{year} promise evidence",
                            },
                            {
                                "id": f"PROM-GOV-{year}",
                                "promise": f"{year} Maintain code of conduct and governance discipline",
                                "category": "governance",
                                "page": 26,
                                "source_chunk": f"{year} governance and code of conduct evidence",
                            }
                        ]
                    }
                },
                "operations": {
                    "projects": {
                        "items": [
                            {
                                "id": f"PROJ-{year}",
                                "project_name": f"{year} Project",
                                "category": "platform",
                                "page": 22,
                                "source_chunk": f"{year} project evidence",
                            }
                        ]
                    },
                    "initiatives": {
                        "items": [
                            {
                                "id": f"INIT-{year}",
                                "initiative": f"{year} Initiative",
                                "category": f"{year} Focus",
                                "page": 23,
                                "source_chunk": f"{year} initiative evidence",
                            },
                            {
                                "id": f"INIT-GROWTH-{year}",
                                "initiative": f"{year} Added 400 customers and improved NPS to 65",
                                "category": "growth execution",
                                "page": 27,
                                "source_chunk": f"{year} customer growth, NPS 65 and platform scale evidence",
                            }
                        ]
                    },
                },
                "financial": {
                    "capital_allocation": {
                        "items": [
                            {
                                "id": f"CAP-DIV-{year}",
                                "action": f"{year} Dividend payout",
                                "category": "dividend",
                                "amount": "8000",
                                "page": 24,
                                "source_chunk": f"{year} dividend declared and paid to shareholders",
                            },
                            {
                                "id": f"CAP-RSU-{year}",
                                "action": f"{year} RSU issuance",
                                "category": "equity issuance",
                                "page": 24,
                                "source_chunk": f"{year} RSU and share-based compensation for employees",
                            },
                            {
                                "id": f"CAP-LOAN-{year}",
                                "action": f"{year} Related-party advance",
                                "category": "advance in nature of loan to related party",
                                "amount": "1578.05",
                                "page": 24,
                                "source_chunk": f"{year} related party advance repayable on demand; no default statement; statutory dues dispute",
                            },
                            {
                                "id": f"CAP-{year}",
                                "action": f"{year} Capital",
                                "category": "capex",
                                "page": 24,
                                "source_chunk": f"{year} capital evidence",
                            }
                        ]
                    }
                },
                "risk": {
                    "identified": {
                        "items": [
                            {
                                "id": f"RISK-{year}",
                                "risk": f"{year} Risk",
                                "category": "operational",
                                "severity": "medium",
                                "page": 25,
                                "source_chunk": f"{year} risk evidence",
                            },
                            {
                                "id": f"RISK-CONC-{year}",
                                "risk": f"{year} Customer concentration risk",
                                "category": "revenue concentration",
                                "severity": "high",
                                "page": 28,
                                "source_chunk": f"{year} customer concentration and revenue stability risk",
                            },
                            {
                                "id": f"RISK-GOV-{year}",
                                "risk": f"{year} Risk governance weakness",
                                "category": "governance",
                                "severity": "high",
                                "page": 29,
                                "source_chunk": f"{year} risk governance and procure-to-pay control weakness",
                            }
                        ]
                    }
                },
                "relationships": {"entities": [], "graph": {}},
                "evidence": {"sources": [], "citations": []},
            }
        ),
        encoding="utf-8",
    )


def _write_multi_year_artifacts(base_dir: Path, company: str, years=("fy24", "fy25")):
    multi_year_dir = base_dir / "companies" / company / "company_memory" / "multi_year"
    multi_year_dir.mkdir(parents=True, exist_ok=True)
    first_year, second_year = years

    artifacts = {
        "company_year_index.json": {
            "company": company,
            "years_detected": [first_year, second_year],
            "available_years": [first_year, second_year],
            "missing_artifacts_by_year": {},
        },
        "business_dna_evolution.json": {
            "timeline": [
                {
                    "year": first_year,
                    "business_dnas": ["Export", "Manufacturing"],
                    "dna_statuses": [
                        {"dna": "Export", "status": "newly_detected", "evidence_ids": [f"ev_{first_year}_business_classification_export"]},
                        {"dna": "Manufacturing", "status": "newly_detected", "evidence_ids": [f"ev_{first_year}_business_classification_manufacturing"]},
                    ],
                    "evidence_ids": [
                        f"ev_{first_year}_business_classification_export",
                        f"ev_{first_year}_business_classification_manufacturing",
                    ],
                },
                {
                    "year": second_year,
                    "business_dnas": ["Manufacturing"],
                    "dna_statuses": [
                        {"dna": "Export", "status": "not_detected_this_year", "evidence_ids": []},
                        {"dna": "Manufacturing", "status": "continued", "evidence_ids": [f"ev_{second_year}_business_classification_manufacturing"]},
                    ],
                    "evidence_ids": [f"ev_{second_year}_business_classification_manufacturing"],
                },
            ],
            "changes_detected": [
                {
                    "from_year": first_year,
                    "to_year": second_year,
                    "status_changes": [
                        {"dna": "Export", "from_status": "newly_detected", "to_status": "not_detected_this_year"}
                    ],
                }
            ],
            "stable_themes": ["Manufacturing"],
            "emerging_themes": [],
            "disappearing_themes": [],
            "missing_rationale": [second_year],
        },
        "strategy_timeline.json": {
            "timeline": [
                {
                    "year": first_year,
                    "management_focus": [
                        {
                            "value": "Capacity expansion",
                            "source_year": first_year,
                            "source_artifact": "management_summary.json",
                            "source_item_id": "INIT_0001",
                            "evidence_ids": [f"ev_{first_year}_management_summary_init_0001"],
                            "evidence_references": [{"source_page": 12}],
                            "canonical_theme": "manufacturing_capacity_expansion",
                        }
                    ],
                },
                {
                    "year": second_year,
                    "management_focus": [
                        {
                            "value": "Capacity expansion",
                            "source_year": second_year,
                            "source_artifact": "management_summary.json",
                            "source_item_id": "INIT_0002",
                            "evidence_ids": [f"ev_{second_year}_management_summary_init_0002"],
                            "evidence_references": [{"source_page": 18}],
                            "canonical_theme": "manufacturing_capacity_expansion",
                        }
                    ],
                },
            ],
            "strategy_continuity": [{"theme": "manufacturing_capacity_expansion", "years_active": [first_year, second_year]}],
            "strategy_shifts": [
                {
                    "from_year": first_year,
                    "to_year": second_year,
                    "added_themes": ["energy_efficiency"],
                    "removed_themes": ["geographic_expansion"],
                }
            ],
            "unresolved_strategy_questions": ["Whether export intensity remains durable."],
            "repeated_focus_areas": ["manufacturing_capacity_expansion"],
            "changed_focus_areas": ["energy_efficiency", "geographic_expansion"],
        },
        "promise_tracker.json": {
            "promises": [
                {
                    "promise_id": f"promise_{first_year}_expand_capacity",
                    "normalized_promise": "expand_capacity",
                    "first_seen_year": first_year,
                    "repeated_years": [second_year],
                    "latest_status": "UNKNOWN",
                    "status_by_year": {first_year: "UNKNOWN", second_year: "UNKNOWN"},
                    "related_evidence_ids": [f"ev_{first_year}_company_intelligence_prom_1"],
                    "confidence": 0.9,
                    "source_mentions": [
                        {
                            "value": "Expand capacity over the next year.",
                            "source_year": first_year,
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "PROM_1",
                            "source_page": 14,
                            "evidence_ids": [f"ev_{first_year}_company_intelligence_prom_1"],
                        }
                    ],
                }
            ],
            "fulfilled_promises": [],
            "repeated_unresolved_promises": [],
            "abandoned_or_disappeared_promises": [],
            "unclear_promises": [f"promise_{first_year}_expand_capacity"],
        },
        "risk_evolution.json": {
            "risks": [
                {
                    "risk_id": "risk_credit_risk",
                    "normalized_risk": "credit_risk",
                    "first_seen_year": first_year,
                    "repeated_years": [second_year],
                    "severity_by_year": {first_year: "medium", second_year: "medium"},
                    "latest_severity": "medium",
                    "related_evidence_ids": [f"ev_{first_year}_company_intelligence_risk_1"],
                    "confidence": 0.8,
                    "numeric_signals_by_year": {},
                    "source_mentions": [
                        {
                            "value": "Credit risk remained material.",
                            "source_year": first_year,
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "RISK_1",
                            "source_page": 33,
                            "evidence_ids": [f"ev_{first_year}_company_intelligence_risk_1"],
                            "severity": "medium",
                            "source_chunk": "should not leak",
                        }
                    ],
                }
            ],
            "recurring_risks": ["risk_credit_risk"],
            "new_risks": [],
            "worsening_risks": [],
            "improving_risks": [],
            "unresolved_risks": ["risk_credit_risk"],
            "qa_warnings": [],
        },
        "capital_allocation_timeline.json": {
            "timeline": [
                {
                    "year": first_year,
                    "dividends": [],
                    "buybacks": [],
                    "capex": [],
                    "cwip": [],
                    "acquisitions": [],
                    "share_splits": [
                        {
                            "value": "Share split",
                            "category": "share_split",
                            "source_year": first_year,
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "CAPALLOC_1",
                            "source_page": 21,
                            "evidence_ids": [f"ev_{first_year}_company_intelligence_capalloc_1"],
                        }
                    ],
                    "equity_issuance": [],
                    "treasury_investments": [],
                    "esop_rsu": [],
                    "debt_borrowings": [],
                    "related_party_transactions": [],
                    "loans_and_advances": [],
                    "auditor_observations": [],
                },
                {
                    "year": second_year,
                    "dividends": [],
                    "buybacks": [],
                    "capex": [
                        {
                            "value": "CWIP expansion",
                            "category": "capex",
                            "source_year": second_year,
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "CAPALLOC_2",
                            "source_page": 41,
                            "amount": "20,187.56 (₹ in Lakhs)",
                            "evidence_ids": [f"ev_{second_year}_company_intelligence_capalloc_2"],
                        }
                    ],
                    "cwip": [
                        {
                            "value": "CWIP expansion",
                            "category": "cwip",
                            "source_year": second_year,
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "CAPALLOC_2",
                            "source_page": 41,
                            "amount": "20,187.56 (₹ in Lakhs)",
                            "evidence_ids": [f"ev_{second_year}_company_intelligence_capalloc_2"],
                        }
                    ],
                    "acquisitions": [],
                    "share_splits": [],
                    "equity_issuance": [],
                    "treasury_investments": [],
                    "esop_rsu": [],
                    "debt_borrowings": [],
                    "related_party_transactions": [],
                    "loans_and_advances": [],
                    "auditor_observations": [],
                },
            ],
            "capital_allocation_patterns": [
                {"category": "share_split", "years_active": [first_year]},
                {"category": "capex", "years_active": [second_year]},
            ],
            "recurring_concerns": [],
            "missing_financial_evidence": [],
        },
        "management_consistency.json": {
            "consistency_observations": [
                {
                    "theme": "manufacturing_capacity_expansion",
                    "years_active": [first_year, second_year],
                    "evidence_ids": [f"ev_{first_year}_management_summary_init_0001", f"ev_{second_year}_management_summary_init_0002"],
                    "consistency_status": "consistent",
                    "explanation": "Capacity expansion remained a repeated focus area.",
                }
            ],
            "repeated_focus_areas": ["manufacturing_capacity_expansion"],
            "changed_focus_areas": ["energy_efficiency"],
            "theme_mentions_by_year": {},
            "raw_labels_by_canonical_theme": {},
            "promise_follow_through_summary": {
                "fulfilled_promises": [],
                "repeated_unresolved_promises": [],
                "unclear_promises": [f"promise_{first_year}_expand_capacity"],
            },
            "evidence_gaps": ["Only two usable years are currently available; consistency conclusions remain provisional."],
        },
        "multi_year_index.json": {
            "company": company,
            "generated_at": "2026-07-12T00:00:00Z",
            "artifacts_generated": [
                "business_dna_evolution.json",
                "strategy_timeline.json",
                "promise_tracker.json",
                "risk_evolution.json",
                "capital_allocation_timeline.json",
                "management_consistency.json",
            ],
            "years_covered": [first_year, second_year],
            "limitations": [
                "Only two usable years are available, so trend and discontinuation judgments remain provisional.",
                f"Missing business-classification rationale for: {second_year}.",
            ],
            "source_artifacts": {"yearly_intelligence": {first_year: [], second_year: []}, "company_memory": []},
        },
    }

    for filename, payload in artifacts.items():
        (multi_year_dir / filename).write_text(json.dumps(payload), encoding="utf-8")


def test_cim_contract_generation_and_pcim_derivation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "acme", "fy25")
    _write_year_artifacts(tmp_path, "acme", "fy20")
    _write_year_artifacts(tmp_path, "acme", "fy24", complete=False)

    builder = CIMContractBuilder(company="acme")
    written = builder.build()

    cim = json.loads(written["cim_v1.json"].read_text())
    pcim = json.loads(written["pcim_v1.json"].read_text())

    assert cim["contract_version"] == "1.0"
    assert cim["company"] == "acme"
    assert cim["available_years"] == ["fy20", "fy25"]
    assert [bucket["year"] for bucket in cim["business_dna_by_year"]] == ["fy20", "fy25"]
    assert cim["uncertainty_missing_data"]["incomplete_years"] == [
        {
            "year": "fy24",
            "status": "partial",
            "reason": "company_intelligence.json missing or unreadable",
        }
    ]

    latest = pcim["business_understanding"]["latest_business_view"]
    assert latest["year"] == "fy25"
    assert latest["business_model"]["business_summary"] == "acme fy25 summary"
    assert pcim["source_cim"] == "cim_v1.json"
    assert pcim["financial_strength_inputs"]["capital_allocation_by_year"][0]["year"] == "fy20"
    assert pcim["governance_and_incentive_inputs"]["equity_incentives_by_year"]
    assert pcim["business_economics_inputs"]["customer_and_scale_signals_by_year"]
    assert pcim["growth_execution_inputs"]["growth_claims_by_year"]
    assert pcim["story_vs_numbers_inputs"]["numeric_support_by_year"]
    assert pcim["uncertainty_missing_data"]["missing_items"]


def test_pcim_includes_compact_multi_year_inputs_when_available(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "acme", "fy24")
    _write_year_artifacts(tmp_path, "acme", "fy25")
    _write_multi_year_artifacts(tmp_path, "acme")

    pcim = json.loads(CIMContractBuilder(company="acme").build()["pcim_v1.json"].read_text())
    multi_year = pcim["multi_year_inputs"]
    manifest = pcim["pcim_source_manifest"]

    assert multi_year["years_covered"] == ["fy24", "fy25"]
    assert manifest["years_available"] == ["fy24", "fy25"]
    assert manifest["years_covered_in_multi_year_inputs"] == ["fy24", "fy25"]
    assert manifest["status"] == "pass"
    assert multi_year["business_dna_evolution"]["not_detected_this_year"] == ["Export"]
    assert multi_year["business_dna_evolution"]["possible_discontinuities"][0]["status"] == "not_detected_this_year"
    assert multi_year["recurring_risks"]["recurring_risks"][0]["related_evidence_ids"] == ["ev_fy24_company_intelligence_risk_1"]
    assert multi_year["capital_allocation_pattern"]["capex_or_cwip_activity"][0]["amount"] == "20,187.56 (₹ in Lakhs)"
    assert multi_year["capital_allocation_pattern"]["share_splits"][0]["category"] == "share_split"
    assert multi_year["strategy_evolution"]["possible_strategy_shifts"][0]["note"].startswith("Removed themes indicate")
    assert "source_chunk" not in json.dumps(multi_year)
    assert "ev_fy24_company_intelligence_risk_1" in multi_year["evidence_map"]


def test_pcim_validator_rejects_source_chunk_anywhere_in_pcim(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "acme", "fy24")
    _write_year_artifacts(tmp_path, "acme", "fy25")

    builder = CIMContractBuilder(company="acme")
    pcim = json.loads(builder.build()["pcim_v1.json"].read_text())
    pcim["management_quality_inputs"]["management_focus_by_year"][0]["items"][0]["source_chunk"] = "raw excerpt should never survive"

    with pytest.raises(ValueError, match="PCIM output must not contain source_chunk"):
        builder._validate_pcim_v1(pcim)


def test_pcim_handles_missing_multi_year_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "acme", "fy25")

    pcim = json.loads(CIMContractBuilder(company="acme").build()["pcim_v1.json"].read_text())

    assert pcim["multi_year_inputs"]["available"] is False
    assert pcim["multi_year_inputs"]["years_covered"] == []
    assert "Multi-year memory artifacts not available." in pcim["multi_year_inputs"]["limitations"]
    assert pcim["pcim_source_manifest"]["status"] == "fail"


def test_pcim_enhances_financial_and_governance_inputs_without_inventing_missing_metrics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "acme", "fy25")

    pcim = json.loads(CIMContractBuilder(company="acme").build()["pcim_v1.json"].read_text())

    financial_signals = pcim["financial_strength_inputs"]["dividend_and_distribution_signals_by_year"][0]["items"]
    governance_signals = pcim["governance_and_incentive_inputs"]["related_party_and_control_items_by_year"][0]["items"]
    missing_items = pcim["uncertainty_missing_data"]["missing_items"]

    assert any(item["signal_type"] == "dividend_payout" for item in financial_signals)
    assert any(item["signal_type"] == "related_party_exposure" for item in governance_signals)
    assert any(item["missing_item"] == "free_cash_flow" for item in missing_items)
    assert any(item["missing_item"] == "board_or_committee_references" for item in missing_items)


def test_cim_contract_preserves_provenance_and_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "acme", "fy22")
    _write_year_artifacts(tmp_path, "acme", "fy25")
    _write_multi_year_artifacts(tmp_path, "acme")

    builder = CIMContractBuilder(company="acme")
    builder.build()
    output_dir = tmp_path / "companies" / "acme" / "company_memory"
    first = {
        path.name: path.read_text()
        for path in sorted(output_dir.glob("*v1.json"))
    }

    builder.build()
    second = {
        path.name: path.read_text()
        for path in sorted(output_dir.glob("*v1.json"))
    }
    assert first == second

    cim = json.loads((output_dir / "cim_v1.json").read_text())
    promise_item = cim["promises"][0]["items"][0]
    business_model = cim["business_model"][0]
    evidence_ids = promise_item["evidence_ids"]

    assert promise_item["source_year"] == "fy22"
    assert promise_item["source_artifact"] == "company_intelligence.json"
    assert promise_item["source_item_id"] == "PROM-fy22"
    assert business_model["source_year"] == "fy22"
    assert evidence_ids
    assert cim["evidence_index"][0]["evidence_id"].startswith("ev_")


def test_run_cim_stage_is_deterministic_and_does_not_use_llm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "acme", "fy25")
    monkeypatch.setattr(run_company_pipeline, "get_llm", lambda: (_ for _ in ()).throw(AssertionError("LLM should not be called")))

    written = run_company_pipeline.run_cim_stage(company="acme", context=None)

    assert set(written) == {"cim_v1.json", "pcim_v1.json"}


def test_pcim_includes_all_available_years_for_synthetic_company(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "multiyearco", "fy21")
    _write_year_artifacts(tmp_path, "multiyearco", "fy22")
    _write_year_artifacts(tmp_path, "multiyearco", "fy23")
    _write_multi_year_artifacts(tmp_path, "multiyearco", years=("fy21", "fy23"))
    multi_year_dir = tmp_path / "companies" / "multiyearco" / "company_memory" / "multi_year"
    company_year_index = json.loads((multi_year_dir / "company_year_index.json").read_text())
    company_year_index["years_detected"] = ["fy21", "fy22", "fy23"]
    company_year_index["available_years"] = ["fy21", "fy22", "fy23"]
    (multi_year_dir / "company_year_index.json").write_text(json.dumps(company_year_index), encoding="utf-8")
    multi_year_index = json.loads((multi_year_dir / "multi_year_index.json").read_text())
    multi_year_index["years_covered"] = ["fy21", "fy22", "fy23"]
    (multi_year_dir / "multi_year_index.json").write_text(json.dumps(multi_year_index), encoding="utf-8")

    pcim = json.loads(CIMContractBuilder(company="multiyearco").build()["pcim_v1.json"].read_text())

    assert pcim["pcim_source_manifest"]["years_available"] == ["fy21", "fy22", "fy23"]
    assert pcim["multi_year_inputs"]["years_covered"] == ["fy21", "fy22", "fy23"]
    assert pcim["pcim_source_manifest"]["years_covered_in_multi_year_inputs"] == ["fy21", "fy22", "fy23"]


def test_pcim_rebuild_picks_up_new_year_and_changes_manifest_hash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "sampleco", "fy22")
    _write_multi_year_artifacts(tmp_path, "sampleco", years=("fy22", "fy22"))
    multi_year_dir = tmp_path / "companies" / "sampleco" / "company_memory" / "multi_year"
    company_year_index_path = multi_year_dir / "company_year_index.json"
    company_year_index = json.loads(company_year_index_path.read_text())
    company_year_index["years_detected"] = ["fy22"]
    company_year_index["available_years"] = ["fy22"]
    company_year_index_path.write_text(json.dumps(company_year_index), encoding="utf-8")
    multi_year_index_path = multi_year_dir / "multi_year_index.json"
    multi_year_index = json.loads(multi_year_index_path.read_text())
    multi_year_index["years_covered"] = ["fy22"]
    multi_year_index_path.write_text(json.dumps(multi_year_index), encoding="utf-8")

    first = json.loads(CIMContractBuilder(company="sampleco").build()["pcim_v1.json"].read_text())
    first_hashes = {
        item["name"]: item["content_hash"]
        for item in first["pcim_source_manifest"]["source_files"]
        if item["loaded"]
    }

    _write_year_artifacts(tmp_path, "sampleco", "fy23")
    company_year_index["years_detected"] = ["fy22", "fy23"]
    company_year_index["available_years"] = ["fy22", "fy23"]
    company_year_index_path.write_text(json.dumps(company_year_index), encoding="utf-8")
    multi_year_index["years_covered"] = ["fy22", "fy23"]
    multi_year_index_path.write_text(json.dumps(multi_year_index), encoding="utf-8")

    second = json.loads(CIMContractBuilder(company="sampleco").build()["pcim_v1.json"].read_text())
    second_hashes = {
        item["name"]: item["content_hash"]
        for item in second["pcim_source_manifest"]["source_files"]
        if item["loaded"]
    }

    assert second["multi_year_inputs"]["years_covered"] == ["fy22", "fy23"]
    assert second["pcim_source_manifest"]["years_available"] == ["fy22", "fy23"]
    assert second_hashes["company_year_index.json"] != first_hashes["company_year_index.json"]
    assert second_hashes["multi_year_index.json"] != first_hashes["multi_year_index.json"]


def test_pcim_source_manifest_warns_on_partial_multi_year_coverage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "partialco", "fy21")
    _write_year_artifacts(tmp_path, "partialco", "fy22")
    _write_year_artifacts(tmp_path, "partialco", "fy23")
    _write_multi_year_artifacts(tmp_path, "partialco", years=("fy21", "fy22"))
    multi_year_dir = tmp_path / "companies" / "partialco" / "company_memory" / "multi_year"
    company_year_index = json.loads((multi_year_dir / "company_year_index.json").read_text())
    company_year_index["years_detected"] = ["fy21", "fy22", "fy23"]
    company_year_index["available_years"] = ["fy21", "fy22", "fy23"]
    (multi_year_dir / "company_year_index.json").write_text(json.dumps(company_year_index), encoding="utf-8")
    risk_evolution = json.loads((multi_year_dir / "risk_evolution.json").read_text())
    risk_evolution["risks"][0]["repeated_years"] = ["fy22"]
    risk_evolution["risks"][0]["severity_by_year"] = {"fy22": "medium"}
    risk_evolution["risks"][0]["source_mentions"][0]["source_year"] = "fy22"
    (multi_year_dir / "risk_evolution.json").write_text(json.dumps(risk_evolution), encoding="utf-8")
    multi_year_index = json.loads((multi_year_dir / "multi_year_index.json").read_text())
    multi_year_index["years_covered"] = ["fy21", "fy22"]
    (multi_year_dir / "multi_year_index.json").write_text(json.dumps(multi_year_index), encoding="utf-8")

    pcim = json.loads(CIMContractBuilder(company="partialco").build()["pcim_v1.json"].read_text())

    assert pcim["pcim_source_manifest"]["status"] == "warning"
    assert "fy23" in pcim["pcim_source_manifest"]["missing_years"]
    assert any("cover all available years" in warning for warning in pcim["pcim_source_manifest"]["stale_source_warnings"])
    assert pcim["multi_year_inputs"]["available"] is True
