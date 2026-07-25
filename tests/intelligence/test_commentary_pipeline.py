import json

from pipelines import run_company_pipeline
from processors.commentary_cleaner import CommentaryCleaner
from synthesis import management_summary_generator as generator


def test_commentary_is_registered_in_canonical_pipeline_lists():
    assert "commentary_discovery_results.json" in run_company_pipeline.DISCOVERY_OUTPUT_FILES
    assert "extracted_commentary.json" in run_company_pipeline.EXTRACTION_OUTPUT_FILES
    assert "clean_commentary.json" in run_company_pipeline.CLEANING_OUTPUT_FILES

    discovery_labels = [label for label, _ in run_company_pipeline.get_discovery_steps()]
    extraction_labels = [label for label, _ in run_company_pipeline.get_extraction_steps()]
    cleaning_labels = [label for label, _ in run_company_pipeline.get_cleaning_steps()]

    assert "Commentary Discovery" in discovery_labels
    assert "Commentary Extractor" in extraction_labels
    assert "Commentary Cleaner" in cleaning_labels


def test_commentary_cleaner_groups_company_and_external_items(tmp_path, monkeypatch):
    input_path = tmp_path / "extracted_commentary.json"
    output_path = tmp_path / "clean_commentary.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "theme": "Operations",
                    "commentary": "The Company commissioned a new facility in FY2025.",
                    "sentiment": "positive",
                    "source_chunk": "raw chunk",
                    "page": 11,
                },
                {
                    "theme": "Strategy",
                    "commentary": "Management plans to expand into new markets next year.",
                    "sentiment": "positive",
                    "source_chunk": "raw chunk",
                    "page": 12,
                },
                {
                    "theme": "Policy",
                    "commentary": "Government increased sector budget allocation for the industry.",
                    "sentiment": "positive",
                    "source_chunk": "raw chunk",
                    "page": 13,
                },
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("processors.commentary_cleaner.extraction_path", lambda _: input_path if _.startswith("extracted") else output_path)
    cleaner = CommentaryCleaner("extracted_commentary.json", "clean_commentary.json", module_name="commentary")
    grouped = cleaner.run()

    company_controlled = grouped["company_management_actions"] + grouped["company_results"]
    assert company_controlled[0]["context_type"] in {"company_action", "company_result"}
    assert grouped["company_promises"][0]["context_type"] == "company_promise"
    assert grouped["external_context"][0]["context_type"] in {"external_context", "external_tailwind"}
    assert "source_chunk" not in json.dumps(grouped)


def test_management_summary_uses_grouped_commentary_without_mixing_external_context():
    profile = {
        "projects": [],
        "promises": [],
        "initiatives": [],
        "capital_allocation": [],
        "commentary": {
            "company_management_actions": [
                {
                    "value": "The Company commissioned a new facility",
                    "category": "Facility Commissioning",
                    "context_type": "company_action",
                    "agency": "company_controlled",
                    "should_feed_management_consistency": True,
                    "should_feed_company_strategy": True,
                    "should_feed_external_context": False,
                    "reasoning": "Company-controlled action.",
                    "evidence_ids": ["ev_commentary_1"],
                    "confidence": "high",
                }
            ],
            "company_promises": [],
            "company_capabilities": [],
            "company_results": [],
            "risk_responses": [],
            "external_context": [
                {
                    "value": "Government increased sector budget allocation",
                    "category": "Policy backdrop",
                    "context_type": "external_tailwind",
                    "agency": "external_not_controlled",
                    "should_feed_management_consistency": False,
                    "should_feed_company_strategy": False,
                    "should_feed_external_context": True,
                    "reasoning": "External backdrop.",
                    "evidence_ids": ["ev_commentary_2"],
                    "confidence": "medium",
                }
            ],
            "accounting_disclosures": [],
            "governance_disclosures": [],
            "uncertain_items": [],
        },
    }

    summary = generator.build_summary(profile, business_context={"business_dnas": ["Manufacturing"]})

    assert "Facility Commissioning" in summary["management_focus_areas"]
    assert summary["company_management_actions"][0]["value"] == "The Company commissioned a new facility"
    assert summary["external_context"][0]["should_feed_management_consistency"] is False
