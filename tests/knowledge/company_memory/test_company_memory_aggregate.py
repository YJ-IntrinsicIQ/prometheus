import json
from pathlib import Path

from knowledge.company_memory.company_layer import CompanyMemoryAggregateBuilder


def _write_year_artifacts(base_dir: Path, company: str, year: str, *, complete: bool = True, promise: str = "", dnas=None):
    intelligence_dir = base_dir / "companies" / company / year / "intelligence"
    intelligence_dir.mkdir(parents=True, exist_ok=True)

    if dnas is None:
        dnas = ["Enterprise Platform"]

    (intelligence_dir / "business_classification.json").write_text(
        json.dumps(
            {
                "business_dnas": dnas,
                "question_modules": ["technology"],
                "report_template": "generic_v1",
            }
        ),
        encoding="utf-8",
    )

    if not complete:
        return

    (intelligence_dir / "management_summary.json").write_text(
        json.dumps(
            {
                "management_focus_areas": ["Platform Operations"],
                "major_projects": [f"{year} Platform Upgrade"],
                "major_promises": [promise],
                "key_initiatives": [f"{year} Initiative"],
                "capital_allocation_actions": [f"{year} Capital Action"],
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
                        "items": [
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
                    },
                },
                "financial": {
                    "capital_allocation": {
                        "items": [
                            {
                                "id": f"CAP-{year}",
                                "action": f"{year} Capital Action",
                                "category": "capex",
                                "page": 13,
                                "source_chunk": f"{year} capital source",
                            }
                        ]
                    }
                },
                "risk": {
                    "identified": {
                        "items": [
                            {
                                "id": f"RISK-{year}",
                                "risk": f"{year} Delivery Risk",
                                "category": "operational",
                                "severity": "medium",
                                "page": 14,
                                "source_chunk": f"{year} risk source",
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


def test_company_memory_aggregate_sorts_years_and_handles_late_arrival(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "acme", "fy25", promise="Scale secure API platform")
    _write_year_artifacts(tmp_path, "acme", "fy24", promise="Scale secure API platform")
    _write_year_artifacts(tmp_path, "acme", "fy20", promise="Launch secure API platform")
    _write_year_artifacts(tmp_path, "acme", "fy23", complete=False)

    builder = CompanyMemoryAggregateBuilder(company="acme")
    builder.build()

    strategy = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "strategy_timeline.json").read_text())
    index = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "company_memory_index.json").read_text())

    assert [item["year"] for item in strategy["timeline"]] == ["fy20", "fy24", "fy25"]
    assert index["ordered_years"] == ["fy20", "fy23", "fy24", "fy25"]
    assert index["usable_years"] == ["fy20", "fy24", "fy25"]
    assert index["incomplete_years"] == [
        {
            "year": "fy23",
            "status": "partial",
            "reason": "company_intelligence.json missing or unreadable",
        }
    ]

    _write_year_artifacts(tmp_path, "acme", "fy22", promise="Harden secure API platform")
    builder.build()

    strategy = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "strategy_timeline.json").read_text())
    assert [item["year"] for item in strategy["timeline"]] == ["fy20", "fy22", "fy24", "fy25"]


def test_company_memory_aggregate_is_idempotent_and_preserves_provenance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "Maintain secure software delivery controls"
    _write_year_artifacts(tmp_path, "acme", "fy25", promise=promise, dnas=["Compliance Infrastructure", "Enterprise Platform"])
    _write_year_artifacts(tmp_path, "acme", "fy24", promise=promise, dnas=["Compliance Infrastructure"])

    builder = CompanyMemoryAggregateBuilder(company="acme")
    builder.build()
    output_dir = tmp_path / "companies" / "acme" / "company_memory"
    first_pass = {
        path.name: path.read_text()
        for path in sorted(output_dir.glob("*.json"))
    }

    builder.build()
    second_pass = {
        path.name: path.read_text()
        for path in sorted(output_dir.glob("*.json"))
    }

    assert first_pass == second_pass

    company_cim = json.loads((output_dir / "company_cim.json").read_text())
    promise_tracker = json.loads((output_dir / "promise_tracker.json").read_text())
    entity_registry = json.loads((output_dir / "entity_registry.json").read_text())

    first_snapshot = company_cim["yearly_snapshots"][0]
    first_dna = first_snapshot["business_dnas"][0]
    first_promise = first_snapshot["major_promises"][0]

    assert first_snapshot["year"] == "fy24"
    assert first_dna["source_year"] == "fy24"
    assert first_dna["source_artifact"] == "business_classification.json"
    assert first_promise["source_year"] == "fy24"
    assert first_promise["source_artifact"] == "company_intelligence.json"
    assert first_promise["source_item_id"] == "PROM-fy24"
    assert first_promise["evidence_references"]["page"] == 10

    assert len(promise_tracker["promise_groups"]) == 1
    group = promise_tracker["promise_groups"][0]
    assert group["first_seen_year"] == "fy24"
    assert group["latest_seen_year"] == "fy25"
    assert [mention["year"] for mention in group["yearly_mentions"]] == ["fy24", "fy25"]

    names = {(item["entity_type"], item["entity_name"]) for item in entity_registry["entities"]}
    assert ("platform", "Alpha Platform") in names
    assert ("geography", "UAE") in names
