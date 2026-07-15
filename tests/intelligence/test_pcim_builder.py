import json

from knowledge.cim_contract import CIMContractBuilder


def _write_year_artifacts(base_dir, company, year):
    intelligence_dir = base_dir / "companies" / company / year / "intelligence"
    intelligence_dir.mkdir(parents=True, exist_ok=True)
    (intelligence_dir / "business_classification.json").write_text(
        json.dumps(
            {
                "business_dnas": ["Enterprise Platform"],
                "question_modules": ["technology", "platform_dependency", "platform_economics"],
                "report_template": "software_v1",
                "rationale": ["Platform evidence dominates the business description."],
                "evidence_used": ["API-first platform architecture"],
                "confidence": 0.83,
                "rejected_dnas": [{"name": "Compliance Infrastructure", "reason": "Supportive but not primary."}],
            }
        ),
        encoding="utf-8",
    )
    (intelligence_dir / "business_blueprint.json").write_text(
        json.dumps(
            {
                "metadata": {"company": company, "version": "1.0", "confidence": 0.78},
                "business_understanding": {
                    "business_summary": "Runs an enterprise platform.",
                    "business_model": "Subscription-led software platform.",
                    "value_creation": "Creates value through platform workflows.",
                    "competitive_position": "Competes via platform embeddedness.",
                },
                "characteristics": [{"name": "API-first platform architecture", "confidence": 0.9}],
                "candidate_dna_signals": [
                    {
                        "name": "Enterprise Platform",
                        "confidence": 0.84,
                        "supporting_reason": "Platform workflows and architecture support this candidate.",
                        "evidence_ids": [],
                    }
                ],
                "dnas": [],
                "reasoning": [{"statement": "Reasoning present."}],
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
                        "question_modules": ["technology", "platform_dependency", "platform_economics"],
                        "report_template": "software_v1",
                    },
                    "industry_profile": {
                        "business_summary": "Runs an enterprise platform.",
                        "business_model": "Subscription-led software platform.",
                        "value_creation": "Creates value through platform workflows.",
                        "characteristics": ["API-first platform architecture"],
                    },
                    "competitive_position": {
                        "summary": "Competes via platform embeddedness.",
                        "supporting_modules": ["technology", "platform_dependency", "platform_economics"],
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


def test_pcim_builder_uses_official_classification_dnas_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "sample_platform_co", "fy25")

    written = CIMContractBuilder(company="sample_platform_co").build()
    pcim = json.loads(written["pcim_v1.json"].read_text())

    assert pcim["business_understanding"]["latest_business_view"]["business_dnas"][0]["value"] == "Enterprise Platform"
    assert pcim["business_identity_manifest"]["official_business_dnas"] == ["Enterprise Platform"]
    assert pcim["business_identity_manifest"]["official_dna_source"] == "business_classification.json"
