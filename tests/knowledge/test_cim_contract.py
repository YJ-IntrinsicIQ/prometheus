import json
from pathlib import Path

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
