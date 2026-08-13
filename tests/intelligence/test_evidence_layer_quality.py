import json

from core.company_context import CompanyContext
from knowledge.evidence_layer import build_evidence_layer_summary, build_evidence_quality


def test_evidence_quality_classifies_company_action_vs_macro_context():
    high = build_evidence_quality(
        {
            "value": "The Company commissioned a facility in FY2025 with Rs 80 crore capex.",
            "status": "commissioned",
        },
        module_name="projects",
    )
    low = build_evidence_quality(
        {
            "value": "The global economy remains uncertain and industry outlook is mixed.",
        },
        module_name="commentary",
    )

    assert high["company_specificity"] in {"high", "medium"}
    assert high["actor_type"] in {"company", "management"}
    assert low["source_proximity"] == "macro_context"
    assert "macro_context" in low["warnings"]


def test_evidence_quality_ignores_source_chunk_year_noise_for_promises():
    item = {
        "item_id": "promises_00001",
        "promise": "Expect the percentage of revenues derived outside India to grow as the company continues to expand internationally.",
        "year": "2020",
        "time_reference": "period_specific",
        "source_chunk": (
            "For the year ended March 31, 2020, majority of our revenues were generated in India. "
            "Results of Operations FY 2019-20 FY 2018-19 Growth % INR in Crore."
        ),
        "value": "Expect the percentage of revenues derived outside India to grow.",
    }

    quality = build_evidence_quality(item, module_name="promises")

    assert quality["period_resolution"]["status"] == "RESOLVED"


def test_evidence_layer_summary_aggregates_counts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="syntheticco", year="fy25")
    context.create_directories()

    (context.raw_dir / "project_discovery_results.json").write_text(
        json.dumps([{"chunk": "The Company commissioned a facility.", "page": 8}]),
        encoding="utf-8",
    )
    (context.extracted_dir / "extracted_projects.json").write_text(
        json.dumps(
            [
                {
                    "project_name": "Facility",
                    "description": "The Company commissioned a facility.",
                    "status": "commissioned",
                    "value": "Facility",
                    "evidence_ids": ["ev_projects_p8_00001"],
                    "confidence": "high",
                    "evidence_quality": {
                        "company_specificity": "high",
                        "actionability": "high",
                        "investor_relevance": "high",
                        "source_proximity": "direct_statement",
                        "actor_type": "company",
                        "time_specificity": "period_specific",
                        "numeric_support": False,
                        "confidence": "high",
                        "warnings": [],
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    (context.extracted_dir / "clean_projects.json").write_text(
        (context.extracted_dir / "extracted_projects.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (context.extracted_dir / "extracted_projects_selection_metadata.json").write_text(
        json.dumps({"chunks_selected": 1, "selection_reasons": []}),
        encoding="utf-8",
    )
    (context.extracted_dir / "extracted_projects_llm_call_manifest.json").write_text(
        json.dumps({"entries": [{"estimated_prompt_tokens": 120}]}),
        encoding="utf-8",
    )
    for filename in (
        "promise_discovery_results.json",
        "risk_discovery_results.json",
        "capacity_discovery_results.json",
        "capital_allocation_discovery_results.json",
        "initiative_discovery_results.json",
    ):
        (context.raw_dir / filename).write_text("[]", encoding="utf-8")
    for filename in (
        "extracted_promises.json",
        "extracted_risks.json",
        "extracted_capacity.json",
        "extracted_capital_allocation.json",
        "extracted_initiatives.json",
        "clean_promises.json",
        "clean_risks.json",
        "clean_capacity.json",
        "clean_capital_allocation.json",
        "clean_initiatives.json",
    ):
        (context.extracted_dir / filename).write_text("[]", encoding="utf-8")

    summary = build_evidence_layer_summary(context)

    assert summary["company"] == "syntheticco"
    assert summary["cost_estimate"]["llm_calls"] == 1
    project_module = next(module for module in summary["modules"] if module["module"] == "projects")
    assert project_module["discovered"] == 1
    assert project_module["selected_for_llm"] == 1
    assert project_module["cleaned"] == 1
