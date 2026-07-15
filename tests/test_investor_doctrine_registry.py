import json
from pathlib import Path

import pytest

from intelligence.investor_panel import (
    VALID_PCIM_SECTIONS,
    InvestorDoctrineRegistry,
    load_doctrine_registry,
)
from intelligence.investor_panel.doctrine_registry import DoctrineValidationError


DOCTRINES_DIR = Path("intelligence/investor_panel/doctrines")


def test_registry_loads_all_doctrines_deterministically():
    doctrines = load_doctrine_registry(DOCTRINES_DIR)

    assert [doctrine["doctrine_id"] for doctrine in doctrines] == [
        "buffett",
        "fisher",
        "graham",
        "lynch",
        "munger",
    ]


def test_every_doctrine_has_required_fields_and_rules():
    doctrines = load_doctrine_registry(DOCTRINES_DIR)

    for doctrine in doctrines:
        assert doctrine["input_source_policy"] == "pcim_only"
        assert doctrine["primary_focus"]
        assert doctrine["canonical_principles"]
        assert doctrine["canonical_questions"]
        assert doctrine["evidence_required_from_pcim"]
        assert doctrine["evidence_to_ignore_or_downweight"]
        assert doctrine["red_flags"]
        assert doctrine["uncertainty_rules"]
        assert doctrine["output_contract"]


def test_every_doctrine_maps_only_to_valid_pcim_sections():
    doctrines = load_doctrine_registry(DOCTRINES_DIR)

    for doctrine in doctrines:
        invalid = [
            section
            for section in doctrine["evidence_required_from_pcim"]
            if section not in VALID_PCIM_SECTIONS
        ]
        assert invalid == []


def test_every_doctrine_has_output_contract_requirements():
    doctrines = load_doctrine_registry(DOCTRINES_DIR)

    for doctrine in doctrines:
        output_contract = doctrine["output_contract"]
        assert output_contract["summary"]
        assert output_contract["rating_scale"]
        assert output_contract["required_sections"]
        assert output_contract["required_evidence"]
        assert output_contract["uncertainty_reporting"]


def test_doctrines_do_not_instruct_raw_document_access():
    doctrines = load_doctrine_registry(DOCTRINES_DIR)
    forbidden_phrases = ("raw document", "raw documents", "annual report", "filing pdf", "document chunk")

    for doctrine in doctrines:
        serialized = json.dumps(doctrine).lower()
        assert doctrine["input_source_policy"] == "pcim_only"
        assert not any(phrase in serialized for phrase in forbidden_phrases)


def test_registry_rejects_invalid_pcim_section(tmp_path):
    invalid_path = tmp_path / "bad.json"
    invalid_path.write_text(
        json.dumps(
            {
                "doctrine_id": "bad",
                "investor_lens": "Bad Lens",
                "input_source_policy": "pcim_only",
                "primary_focus": ["Focus"],
                "canonical_principles": ["Principle"],
                "canonical_questions": ["Question"],
                "evidence_required_from_pcim": ["raw_documents"],
                "evidence_to_ignore_or_downweight": ["Noise"],
                "red_flags": ["Flag"],
                "uncertainty_rules": ["Rule"],
                "output_contract": {
                    "summary": "Summary",
                    "rating_scale": "strong / weak",
                    "required_sections": ["section"],
                    "required_evidence": ["evidence_ids"],
                    "uncertainty_reporting": "Report uncertainty"
                }
            }
        ),
        encoding="utf-8",
    )

    registry = InvestorDoctrineRegistry(tmp_path)
    with pytest.raises(DoctrineValidationError, match="invalid PCIM sections"):
        registry.load_all()
