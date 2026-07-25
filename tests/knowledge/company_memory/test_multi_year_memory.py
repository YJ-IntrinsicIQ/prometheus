import json
from pathlib import Path

from knowledge.company_memory.multi_year import MultiYearCompanyMemoryBuilder
from knowledge.company_memory.taxonomy import TaxonomyLoader
from pipelines import run_company_pipeline


def _write_year_artifacts(
    base_dir: Path,
    company: str,
    year: str,
    *,
    complete: bool = True,
    promise: str = "",
    dnas=None,
    rationale=None,
    capital_items=None,
    initiatives=None,
    risk_items=None,
):
    intelligence_dir = base_dir / "companies" / company / year / "intelligence"
    intelligence_dir.mkdir(parents=True, exist_ok=True)

    if dnas is None:
        dnas = ["Enterprise Platform"]
    if rationale is None:
        rationale = [f"{year} rationale"]
    if capital_items is None:
        capital_items = [
            {
                "id": f"CAP-{year}",
                "action": f"{year} Capital Action",
                "category": "capex",
                "page": 13,
                "source_chunk": f"{year} capital source",
            }
        ]
    if initiatives is None:
        initiatives = [
            {
                "id": f"INIT-{year}",
                "initiative": f"{year} Initiative",
                "category": "Platform Operations",
                "status": "Implemented",
                "benefit": "Improves reliability",
                "page": 12,
                "source_chunk": f"{year} initiative source",
            }
        ]
    if risk_items is None:
        risk_items = [
            {
                "id": f"RISK-{year}",
                "risk": "Customer concentration risk",
                "category": "Customer concentration risk",
                "severity": "medium",
                "page": 14,
                "source_chunk": f"{year} risk source",
            }
        ]

    (intelligence_dir / "business_classification.json").write_text(
        json.dumps(
            {
                "business_dnas": dnas,
                "question_modules": ["technology"],
                "report_template": "generic_v1",
                "rationale": rationale,
            }
        ),
        encoding="utf-8",
    )

    if not complete:
        return

    (intelligence_dir / "management_summary.json").write_text(
        json.dumps(
            {
                "management_focus_areas": [item["category"] for item in initiatives if item.get("category")],
                "major_projects": [f"{year} Platform Upgrade"],
                "major_promises": [promise],
                "key_initiatives": [item["initiative"] for item in initiatives],
                "capital_allocation_actions": [item["action"] for item in capital_items],
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
                        "business_dnas": dnas,
                        "question_modules": ["technology"],
                        "report_template": "generic_v1",
                    },
                    "industry_profile": {
                        "business_summary": f"{company} operates the {year} Alpha Platform in India and UAE with Google partner channels.",
                        "business_model": "Platform-led model",
                        "value_creation": "Secure platform delivery",
                        "characteristics": [
                            "Alpha Platform deployment",
                            "Regional expansion in India and UAE",
                        ],
                    },
                    "competitive_position": {"summary": "Strong position", "supporting_modules": ["technology"]},
                },
                "management": {
                    "promises": {
                        "items": [
                            {
                                "id": f"PROM-{year}",
                                "promise": promise,
                                "category": "strategic objective",
                                "status": "UNKNOWN",
                                "page": 10,
                                "source_chunk": f"{year} promise source",
                            }
                        ]
                    }
                },
                "operations": {
                    "projects": {
                        "items": [
                            {
                                "id": f"PROJ-{year}",
                                "project_name": f"{year} Platform Upgrade",
                                "category": "platform",
                                "page": 11,
                                "source_chunk": f"{year} project source",
                            }
                        ]
                    },
                    "initiatives": {
                        "items": initiatives
                    },
                },
                "financial": {
                    "capital_allocation": {
                        "items": capital_items,
                    }
                },
                "risk": {
                    "identified": {
                        "items": risk_items
                    }
                },
                "relationships": {"entities": [], "graph": {}},
                "evidence": {"sources": [], "citations": []},
            }
        ),
        encoding="utf-8",
    )


def test_multi_year_memory_sorts_years_and_handles_missing_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "acme", "fy25", promise="Scale secure API platform", dnas=["Enterprise Platform", "Compliance Infrastructure"])
    _write_year_artifacts(tmp_path, "acme", "fy22", promise="Launch secure API platform", dnas=["Enterprise Platform"])
    _write_year_artifacts(tmp_path, "acme", "fy24", complete=False)

    output_dir = tmp_path / "companies" / "acme" / "company_memory" / "multi_year"
    written = MultiYearCompanyMemoryBuilder(company="acme").build()

    assert output_dir.exists()
    assert set(written) == {
        "company_year_index.json",
        "business_dna_evolution.json",
        "strategy_timeline.json",
        "promise_tracker.json",
        "risk_evolution.json",
        "capital_allocation_timeline.json",
        "management_consistency.json",
        "taxonomy_review_candidates.json",
        "multi_year_index.json",
    }

    company_year_index = json.loads((output_dir / "company_year_index.json").read_text())
    strategy = json.loads((output_dir / "strategy_timeline.json").read_text())
    multi_year_index = json.loads((output_dir / "multi_year_index.json").read_text())

    assert company_year_index["years_detected"] == ["fy22", "fy24", "fy25"]
    assert company_year_index["available_years"] == ["fy22", "fy25"]
    assert company_year_index["missing_artifacts_by_year"]["fy24"] == ["company_intelligence.json", "management_summary.json"]
    assert [item["year"] for item in strategy["timeline"]] == ["fy22", "fy25"]
    assert multi_year_index["years_covered"] == ["fy22", "fy25"]
    assert "fy24: company_intelligence.json missing or unreadable" in multi_year_index["limitations"]
    assert any("Only two usable years" in item for item in multi_year_index["limitations"])


def test_multi_year_memory_is_idempotent_and_preserves_provenance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    capital_items = [
        {
            "id": "CAP-fy24",
            "action": "Related party loan to affiliate",
            "category": "related party loan",
            "amount": "100",
            "counterparty": "Acme Affiliate",
            "relationship": "Subsidiary",
            "repayment_terms": "3 years",
            "approval_oversight_detail": "Board approved",
            "page": 22,
            "source_chunk": "Related party loan to affiliate on board-approved terms.",
        }
    ]
    risk_items = [
        {
            "id": "RISK-fy24",
            "risk": "Liquidity risk from borrowings",
            "category": "Liquidity risk",
            "severity": "medium",
            "page": 14,
            "source_chunk": "Borrowings 1000.00 created liquidity pressure in fy24.",
        }
    ]
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        promise="Scale secure API platform",
        dnas=["Enterprise Platform"],
        capital_items=capital_items,
        risk_items=risk_items,
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy25",
        promise="Scale secure API platform",
        dnas=["Enterprise Platform", "Compliance Infrastructure"],
        capital_items=capital_items,
        risk_items=[
            {
                "id": "RISK-fy25",
                "risk": "Liquidity risk from higher borrowings",
                "category": "Liquidity risk",
                "severity": "high",
                "page": 14,
                "source_chunk": "Borrowings 2000.00 increased liquidity stress in fy25.",
            }
        ],
    )

    builder = MultiYearCompanyMemoryBuilder(company="acme")
    builder.build()
    output_dir = tmp_path / "companies" / "acme" / "company_memory" / "multi_year"
    first_pass = {path.name: path.read_text() for path in sorted(output_dir.glob("*.json"))}

    builder.build()
    second_pass = {path.name: path.read_text() for path in sorted(output_dir.glob("*.json"))}

    assert first_pass == second_pass

    strategy = json.loads((output_dir / "strategy_timeline.json").read_text())
    promise_tracker = json.loads((output_dir / "promise_tracker.json").read_text())
    risk_evolution = json.loads((output_dir / "risk_evolution.json").read_text())
    capital_timeline = json.loads((output_dir / "capital_allocation_timeline.json").read_text())

    focus_item = strategy["timeline"][0]["management_focus"][0]
    assert focus_item["source_year"] == "fy24"
    assert focus_item["source_artifact"] == "management_summary.json"
    assert focus_item["source_item_id"] == "INIT-fy24"
    assert focus_item["evidence_ids"]

    promise = promise_tracker["promises"][0]
    assert promise["first_seen_year"] == "fy24"
    assert promise["repeated_years"] == ["fy25"]
    assert promise["related_evidence_ids"]

    risk = risk_evolution["risks"][0]
    assert risk["severity_by_year"] == {"fy24": "medium", "fy25": "high"}
    assert risk_evolution["worsening_risks"] == [risk["risk_id"]]

    capital_entry = capital_timeline["timeline"][0]["related_party_transactions"][0]
    assert capital_entry["amount"] == "100"
    assert capital_entry["counterparty"] == "Acme Affiliate"
    assert capital_entry["relationship"] == "Subsidiary"
    assert capital_entry["repayment_terms"] == "3 years"
    assert capital_entry["approval_oversight_detail"] == "Board approved"
    assert capital_entry["evidence_ids"]


def test_risk_grouping_stays_item_specific_for_shared_financial_note(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    shared_chunk = (
        "Financial risk note covers credit risk, liquidity risk, market risk - interest rate risk, "
        "and foreign currency risk. Borrowings 5337.21 remain exposed to refinancing pressure."
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        promise="Scale",
        risk_items=[
            {"id": "R1", "risk": "Credit risk", "category": "Credit risk", "severity": "medium", "page": 10, "source_chunk": shared_chunk},
            {"id": "R2", "risk": "Liquidity risk from refinancing pressure", "category": "Liquidity risk", "severity": "medium", "page": 10, "source_chunk": shared_chunk},
            {"id": "R3", "risk": "Market risk - interest rate risk", "category": "Market risk - Interest rate risk", "severity": "medium", "page": 10, "source_chunk": shared_chunk},
            {"id": "R4", "risk": "Foreign currency risk from export receivables", "category": "Foreign exchange exposure", "severity": "medium", "page": 10, "source_chunk": shared_chunk},
            {"id": "R5", "risk": "Deficiencies in internal controls", "category": "Internal control / Operational risk", "severity": "medium", "page": 11, "source_chunk": "Internal control weakness."},
            {"id": "R6", "risk": "Related-party transactions / conflict of interest", "category": "Related party / Governance risk", "severity": "medium", "page": 11, "source_chunk": "Related party concern."},
            {"id": "R7", "risk": "Insufficient formal risk identification and mitigation processes", "category": "Risk management / Governance risk", "severity": "medium", "page": 11, "source_chunk": "Risk governance weakness."},
        ],
    )

    MultiYearCompanyMemoryBuilder(company="acme").build()
    risk_data = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "risk_evolution.json").read_text())
    by_risk = {item["normalized_risk"]: item for item in risk_data["risks"]}

    assert by_risk["credit_risk"]["source_mentions"][0]["value"] == "Credit risk"
    assert by_risk["liquidity_risk"]["source_mentions"][0]["value"] == "Liquidity risk from refinancing pressure"
    assert by_risk["interest_rate_risk"]["source_mentions"][0]["value"] == "Market risk - interest rate risk"
    assert by_risk["foreign_exchange_risk"]["source_mentions"][0]["value"] == "Foreign currency risk from export receivables"
    assert by_risk["internal_control_risk"]["source_mentions"][0]["value"] == "Deficiencies in internal controls"
    assert by_risk["related_party_risk"]["source_mentions"][0]["value"] == "Related-party transactions / conflict of interest"
    governance_key = "governance_risk" if "governance_risk" in by_risk else "risk_management_weakness"
    assert by_risk[governance_key]["source_mentions"][0]["value"] == "Insufficient formal risk identification and mitigation processes"
    assert by_risk["credit_risk"]["related_evidence_ids"] == ["ev_fy24_company_intelligence_r1"]
    assert by_risk["liquidity_risk"]["related_evidence_ids"] == ["ev_fy24_company_intelligence_r2"]
    assert by_risk["interest_rate_risk"]["related_evidence_ids"] == ["ev_fy24_company_intelligence_r3"]
    assert by_risk["foreign_exchange_risk"]["related_evidence_ids"] == ["ev_fy24_company_intelligence_r4"]


def test_major_projects_contribute_to_strategy_themes_and_are_compacted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_chunk = "Large manufacturing facility project with semi-conductors and LED lights expansion. " * 20
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        promise="Scale",
        dnas=["Manufacturing", "Semiconductor"],
        initiatives=[{"id": "I24", "initiative": "Legacy quality", "category": "Quality improvement", "status": "ongoing", "page": 5, "source_chunk": "quality"}],
    )
    intelligence_dir = tmp_path / "companies" / "acme" / "fy25" / "intelligence"
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy25",
        promise="Scale",
        dnas=["Manufacturing", "Semiconductor"],
        initiatives=[],
    )
    summary = json.loads((intelligence_dir / "management_summary.json").read_text())
    summary["major_projects"] = [
        "Manufacturing facility under Atal Industrial Infrastructure Development Scheme",
        "Manufacturing facility for semi-conductors and LED Lights (Atal Industrial Infrastructure Development Scheme)",
    ]
    (intelligence_dir / "management_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    company_intelligence = json.loads((intelligence_dir / "company_intelligence.json").read_text())
    company_intelligence["operations"]["projects"]["items"] = [
        {
            "id": "P1",
            "project_name": "Manufacturing facility under Atal Industrial Infrastructure Development Scheme",
            "category": "manufacturing facility",
            "status": "Planned",
            "page": 12,
            "source_chunk": project_chunk,
        },
        {
            "id": "P2",
            "project_name": "Manufacturing facility for semi-conductors and LED Lights (Atal Industrial Infrastructure Development Scheme)",
            "category": "semi-conductors and LED lights",
            "status": "Planned",
            "page": 13,
            "source_chunk": project_chunk,
        },
    ]
    (intelligence_dir / "company_intelligence.json").write_text(json.dumps(company_intelligence), encoding="utf-8")

    MultiYearCompanyMemoryBuilder(company="acme").build()
    strategy = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "strategy_timeline.json").read_text())
    consistency = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "management_consistency.json").read_text())
    fy25 = next(item for item in strategy["timeline"] if item["year"] == "fy25")

    project_themes = {item["canonical_theme"] for item in fy25["major_projects"]}
    assert "plant_construction" in project_themes or "manufacturing_capacity_expansion" in project_themes
    assert "electronics_manufacturing" in project_themes or "semiconductor_manufacturing" in project_themes or "semiconductor_components" in project_themes
    assert any(theme in fy25["strategic_themes"] for theme in project_themes)
    assert "source_chunk" not in json.dumps(fy25["major_projects"])
    assert len(fy25["major_projects"][0]["evidence_references"][0]["short_excerpt"]) <= 300
    assert "plant_construction" in consistency["changed_focus_areas"] or "manufacturing_capacity_expansion" in consistency["changed_focus_areas"]


def test_multi_year_memory_capital_taxonomy_classifies_share_split_treasury_and_cwip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    capital_items = [
        {
            "id": "CAP-1",
            "action": "Share subdivision (sub-division of equity shares)",
            "category": "Share subdivision / Equity split",
            "page": 10,
            "source_chunk": "Share subdivision approved.",
        },
        {
            "id": "CAP-2",
            "action": "Investment",
            "category": "Debt mutual fund schemes",
            "page": 11,
            "source_chunk": "Invests in debt mutual fund schemes for liquidity management.",
        },
        {
            "id": "CAP-3",
            "action": "Capital expenditure recorded as Capital Work-in-Progress",
            "category": "Capex spending (Capital Work-in-Progress)",
            "amount": "20,187.56",
            "page": 12,
            "source_chunk": "Capital Work in Progress 20187.56",
        },
    ]
    _write_year_artifacts(tmp_path, "acme", "fy25", promise="Scale", capital_items=capital_items)

    MultiYearCompanyMemoryBuilder(company="acme").build()
    data = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "capital_allocation_timeline.json").read_text())
    row = data["timeline"][0]

    assert row["share_splits"][0]["category"] == "share_split"
    assert row["share_splits"][0]["value"].startswith("Share subdivision")
    assert row["treasury_investments"][0]["category"] == "mutual_fund_investment"
    assert row["cwip"][0]["category"] == "cwip"
    assert row["true_capital_deployment"][0]["category"] == "cwip"
    assert row["corporate_actions_non_cash_or_admin"][0]["category"] == "share_split"
    assert row["debt_borrowings"] == []


def test_multi_year_memory_dna_absence_is_not_disappearance_on_single_missing_year(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "acme", "fy24", promise="Scale", dnas=["Manufacturing", "Export"])
    _write_year_artifacts(tmp_path, "acme", "fy25", promise="Scale", dnas=["Manufacturing"], rationale=[])

    MultiYearCompanyMemoryBuilder(company="acme").build()
    data = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "business_dna_evolution.json").read_text())

    fy25 = next(item for item in data["timeline"] if item["year"] == "fy25")
    export_status = next(item for item in fy25["dna_statuses"] if item["dna"] == "Export")

    assert export_status["status"] == "not_detected_this_year"
    assert data["disappearing_themes"] == []
    assert data["missing_rationale"] == ["fy25"]


def test_multi_year_memory_merges_theme_variants_into_canonical_buckets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        promise="Scale",
        initiatives=[
            {
                "id": "INIT-24A",
                "initiative": "Lower power usage",
                "category": "Energy & Sustainability",
                "status": "executing",
                "page": 10,
                "source_chunk": "Energy and sustainability initiative.",
            },
            {
                "id": "INIT-24B",
                "initiative": "Community support",
                "category": "Corporate Social Responsibility",
                "status": "ongoing",
                "page": 11,
                "source_chunk": "Corporate social responsibility program.",
            },
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy25",
        promise="Scale",
        initiatives=[
            {
                "id": "INIT-25A",
                "initiative": "Power optimization",
                "category": "Energy & Resource Efficiency",
                "status": "implemented",
                "page": 10,
                "source_chunk": "Resource efficiency initiative.",
            },
            {
                "id": "INIT-25B",
                "initiative": "Community giving",
                "category": "Corporate Social Responsibility (CSR)",
                "status": "implemented",
                "page": 11,
                "source_chunk": "CSR program.",
            },
        ],
    )

    MultiYearCompanyMemoryBuilder(company="acme").build()
    strategy = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "strategy_timeline.json").read_text())
    consistency = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "management_consistency.json").read_text())

    focus_24 = strategy["timeline"][0]["management_focus"]
    focus_25 = strategy["timeline"][1]["management_focus"]
    assert {item["canonical_theme"] for item in focus_24} == {"csr", "energy_efficiency"}
    assert {item["canonical_theme"] for item in focus_25} == {"csr", "energy_efficiency"}
    assert consistency["theme_mentions_by_year"]["csr"] == ["fy24", "fy25"]
    assert consistency["theme_mentions_by_year"]["energy_efficiency"] == ["fy24", "fy25"]
    assert "Corporate Social Responsibility (CSR)" in consistency["raw_labels_by_canonical_theme"]["csr"]


def test_multi_year_memory_dedupes_risks_and_removes_full_source_chunk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    duplicated_chunk = "Credit risk from receivables and cash equivalents. " * 20
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy25",
        promise="Scale",
        risk_items=[
            {
                "id": "RISK-1",
                "risk": "Credit risk from receivables",
                "category": "Credit risk",
                "severity": "not specified",
                "page": 20,
                "source_chunk": duplicated_chunk,
            },
            {
                "id": "RISK-2",
                "risk": "Credit risk",
                "category": "credit risk",
                "severity": "not specified",
                "page": 20,
                "source_chunk": duplicated_chunk,
            },
        ],
    )

    MultiYearCompanyMemoryBuilder(company="acme").build()
    risk_data = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "risk_evolution.json").read_text())

    assert len(risk_data["timeline"][0]["risks"]) == 1
    risk = risk_data["timeline"][0]["risks"][0]
    assert risk["canonical_risk"] == "credit_risk"
    assert len(risk["evidence_ids"]) == 2
    assert "source_chunk" not in json.dumps(risk)
    assert len(risk["evidence_references"][0]["short_excerpt"]) <= 300


def test_unknown_labels_are_written_to_taxonomy_review_candidates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy25",
        promise="Scale",
        initiatives=[
            {
                "id": "INIT-UNK",
                "initiative": "Odd initiative",
                "category": "Moonshot adjacency weaving",
                "status": "planned",
                "page": 10,
                "source_chunk": "Moonshot adjacency weaving initiative.",
            }
        ],
    )

    MultiYearCompanyMemoryBuilder(company="acme").build()
    strategy = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "strategy_timeline.json").read_text())
    review = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "taxonomy_review_candidates.json").read_text())

    item = strategy["timeline"][0]["management_focus"][0]
    assert item["canonical_theme"] == "unclassified_theme"
    assert item["needs_taxonomy_review"] is True
    assert review["review_candidates"][0]["raw_label"] == "Moonshot adjacency weaving"
    assert review["review_candidates"][0]["normalized_slug"] == "moonshot_adjacency_weaving"
    assert "loaded_archetypes" in review


def test_multi_year_memory_borrowings_increase_worsens_liquidity_risk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        promise="Scale",
        risk_items=[
            {
                "id": "RISK-24",
                "risk": "Liquidity risk from short-term borrowings",
                "category": "Liquidity risk",
                "severity": "medium",
                "page": 12,
                "source_chunk": "Borrowings 2114.79 in fy24.",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy25",
        promise="Scale",
        risk_items=[
            {
                "id": "RISK-25",
                "risk": "Liquidity risk from refinancing pressure",
                "category": "Liquidity risk",
                "severity": "medium",
                "page": 12,
                "source_chunk": "Borrowings 5337.21 in fy25.",
            }
        ],
    )

    MultiYearCompanyMemoryBuilder(company="acme").build()
    risk_data = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "risk_evolution.json").read_text())

    liquidity = next(item for item in risk_data["risks"] if item["normalized_risk"] == "liquidity_risk")
    assert liquidity["numeric_signals_by_year"] == {"fy24": 2114.79, "fy25": 5337.21}
    assert liquidity["risk_id"] in risk_data["worsening_risks"]


def test_registry_curates_universal_theme_matches():
    loader = TaxonomyLoader(
        company="acme",
        business_dnas=["Manufacturing", "Semiconductor", "Export"],
        company_root=Path("companies/acme"),
    )

    assert loader.normalize_theme("Corporate Social Responsibility (CSR)")["canonical_theme"] == "csr"
    assert loader.normalize_theme("Energy conservation and efficiency measures")["canonical_theme"] == "energy_efficiency"
    assert loader.normalize_theme("Utilization of waste material")["canonical_theme"] == "resource_efficiency"
    assert loader.normalize_theme("Improving product quality through improved processes")["canonical_theme"] == "quality_improvement"
    assert loader.normalize_theme("Investing in the United States and other low country-risk regions")["canonical_theme"] == "geographic_expansion"
    assert loader.normalize_theme("Conversion from Private Limited to Public Limited Company")["canonical_theme"] == "governance_compliance"


def test_registry_curates_manufacturing_and_electronics_theme_matches():
    loader = TaxonomyLoader(
        company="acme",
        business_dnas=["Manufacturing", "Semiconductor"],
        company_root=Path("companies/acme"),
    )

    assert loader.normalize_theme("Polymatech has begun the next phase of construction")["canonical_theme"] in {
        "plant_construction",
        "capacity_expansion",
    }
    assert loader.normalize_theme("Production of LED products")["canonical_theme"] in {
        "electronics_manufacturing",
        "product_manufacturing",
    }
    assert loader.normalize_theme("Materials manufacturing for energy-efficient devices")["canonical_theme"] == "electronics_manufacturing"
    assert loader.normalize_theme("Sapphire wafers for integrated circuits")["canonical_theme"] == "semiconductor_manufacturing"


def test_registry_curates_risk_matches_and_priority():
    loader = TaxonomyLoader(
        company="acme",
        business_dnas=["Manufacturing"],
        company_root=Path("companies/acme"),
    )

    assert loader.normalize_risk("Deficiencies in internal controls", "Internal control / Operational risk") == "internal_control_risk"
    assert loader.normalize_risk("Related-party transactions", "Related party / Governance risk") == "related_party_risk"
    assert loader.normalize_risk("Non-compliance with SEBI listing rules", "Compliance risk") == "regulatory_risk"
    assert loader.normalize_risk("FEMA non-compliance", "Compliance risk") == "regulatory_risk"
    assert loader.normalize_risk("Forward contract volatility", "Derivative risk") == "derivative_hedging_risk"


def test_borrowings_numeric_signal_does_not_leak_into_unrelated_risks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy25",
        promise="Scale",
        risk_items=[
            {
                "id": "RISK-LIQ",
                "risk": "Liquidity risk from short-term borrowings",
                "category": "Liquidity risk",
                "severity": "medium",
                "page": 12,
                "source_chunk": "Borrowings 5337.21 in fy25.",
            },
            {
                "id": "RISK-FX",
                "risk": "Foreign exchange exposure from exports",
                "category": "Foreign exchange risk",
                "severity": "medium",
                "page": 13,
                "source_chunk": "Borrowings 5337.21 in fy25.",
            },
            {
                "id": "RISK-MKT",
                "risk": "Market risk from fair-value movements",
                "category": "Market risk",
                "severity": "medium",
                "page": 14,
                "source_chunk": "Borrowings 5337.21 in fy25.",
            },
        ],
    )

    MultiYearCompanyMemoryBuilder(company="acme").build()
    risk_data = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "risk_evolution.json").read_text())

    liquidity = next(item for item in risk_data["risks"] if item["normalized_risk"] == "liquidity_risk")
    fx = next(item for item in risk_data["risks"] if item["normalized_risk"] == "foreign_exchange_risk")
    market = next(item for item in risk_data["risks"] if item["normalized_risk"] == "market_risk")

    assert liquidity["numeric_signals_by_year"] == {"fy25": 5337.21}
    assert fx["numeric_signals_by_year"] == {}
    assert market["numeric_signals_by_year"] == {}


def test_multi_year_memory_stage_makes_no_llm_call(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "acme", "fy25", promise="Scale secure API platform")

    monkeypatch.setattr(
        run_company_pipeline,
        "get_llm",
        lambda: (_ for _ in ()).throw(AssertionError("multi-year memory should not call the LLM")),
    )

    written = run_company_pipeline.run_multi_year_memory_stage(company="acme")

    assert "company_year_index.json" in written
    assert (tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "management_consistency.json").exists()


def test_semiconductor_terms_are_not_hardcoded_in_multi_year_and_live_in_taxonomy_pack():
    multi_year_text = Path("knowledge/company_memory/multi_year.py").read_text(encoding="utf-8").lower()
    semiconductor_pack = Path("knowledge/archetypes/semiconductor_components/themes.json").read_text(encoding="utf-8").lower()

    for term in ("wafer", "chip", "substrate", "htcc", "ltcc"):
        assert term not in multi_year_text
        assert term in semiconductor_pack


def test_taxonomy_loader_uses_semiconductor_domain_pack_for_polymatech_style_dnas():
    loader = TaxonomyLoader(
        company="acme",
        business_dnas=["Manufacturing", "Semiconductor"],
        company_root=Path("companies/acme"),
    )

    result = loader.normalize_theme("Wafer line packaging expansion")

    assert result["canonical_theme"] == "semiconductor_manufacturing"
    assert "semiconductor_components" in loader.get_loaded_pack_ids()


def test_tips_like_media_ip_labels_do_not_require_multi_year_code_changes():
    loader = TaxonomyLoader(
        company="tips",
        business_dnas=["IP Library", "Platform Monetization"],
        company_root=Path("companies/tips"),
    )

    result = loader.normalize_theme("Rights monetization and digital distribution")

    assert result["canonical_theme"] in {"library_economics", "audience_distribution"}
