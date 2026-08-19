import pytest

from knowledge.evidence_layer import finalize_cleaned_item, validate_cleaned_item


def test_cleaned_item_gets_evidence_quality_and_loses_source_chunk():
    item = finalize_cleaned_item(
        {
            "project_name": "New facility",
            "description": "The Company commissioned a new facility in FY2025 for Rs 100 crore.",
            "status": "commissioned",
            "source_chunk": "raw text should not survive",
            "page": 22,
        },
        module_name="projects",
        item_index=1,
    )

    assert "source_chunk" not in item
    assert item["evidence_ids"]
    assert item["evidence_quality"]["company_specificity"] in {"high", "medium"}
    assert item["confidence"] in {"high", "medium", "low"}


def test_validator_fails_on_missing_evidence_ids():
    validation = validate_cleaned_item(
        {
            "value": "Declared dividend",
            "action": "Declared dividend",
            "category": "Dividend",
            "status": "",
            "confidence": "high",
            "evidence_quality": {
                "company_specificity": "high",
                "actionability": "high",
                "investor_relevance": "high",
                "source_proximity": "direct_statement",
                "actor_type": "company",
                "time_specificity": "dated",
                "numeric_support": True,
                "confidence": "high",
                "warnings": [],
            },
            "evidence_ids": [],
        },
        module_name="capital_allocations",
    )

    assert "missing evidence_ids" in validation["errors"]


def test_validator_blocks_uncertain_external_context():
    item = finalize_cleaned_item(
        {
            "risk": "Government policy changes may affect the sector outlook.",
            "category": "Regulatory",
            "severity": "medium",
            "source_year": "fy20",
            "page": 9,
        },
        module_name="risks",
        item_index=2,
    )

    validation = validate_cleaned_item(item, module_name="risks")

    assert "business relevance outcome: QUARANTINE" in validation["errors"]


def test_source_year_metadata_does_not_create_period_conflicts_for_risks():
    item = finalize_cleaned_item(
        {
            "risk": "Dynamic and stringent regulatory/compliance environment requiring ongoing changes to platforms and processes.",
            "category": "Regulatory risk",
            "severity": "High",
            "source_year": "fy20",
            "page": 12,
        },
        module_name="risks",
        item_index=3,
    )

    assert item["evidence_quality"]["period_resolution"]["status"] in {"RESOLVED", "HISTORICAL_CONTEXT"}
