import pytest

from knowledge.business_blueprint import (
    BusinessBlueprint,
    BusinessCharacteristic,
    BusinessUnderstanding,
    CandidateDNASignal,
    Metadata,
)
from knowledge.business_identity import (
    align_blueprint_with_classification,
    build_business_identity_manifest,
    ensure_business_identity_contract,
)


def _blueprint(company="sample_platform_co"):
    return BusinessBlueprint(
        metadata=Metadata(company=company),
        business_understanding=BusinessUnderstanding(
            business_summary="Runs a workflow platform for enterprise customers.",
            business_model="Subscription-led enterprise platform.",
        ),
        characteristics=[
            BusinessCharacteristic(name="API-first platform architecture", confidence=0.9),
        ],
        candidate_dna_signals=[
            CandidateDNASignal(
                name="Enterprise Platform",
                confidence=0.88,
                supporting_reason="Platform architecture and enterprise workflows support this candidate.",
                evidence_ids=[],
            )
        ],
        reasoning=["Reasoning present."],
    )


def test_blueprint_candidates_and_classification_official_source_can_align():
    blueprint = _blueprint()
    classification = {
        "business_dnas": ["Enterprise Platform"],
        "question_modules": ["technology", "platform_dependency", "platform_economics"],
        "report_template": "software_v1",
        "rationale": ["Platform evidence is sustained across the business description."],
        "evidence_used": ["API-first platform architecture"],
        "confidence": 0.84,
        "rejected_dnas": [{"name": "Compliance Infrastructure", "reason": "Evidence is supportive but not primary."}],
    }

    aligned = align_blueprint_with_classification(blueprint, classification)
    manifest = ensure_business_identity_contract(aligned, classification)

    assert aligned.dnas_source == "business_classification"
    assert [item.name for item in aligned.dnas] == ["Enterprise Platform"]
    assert manifest["official_business_dnas"] == ["Enterprise Platform"]
    assert manifest["conflict_status"] == "pass"


def test_empty_blueprint_dnas_does_not_fail_when_classification_is_valid():
    manifest = ensure_business_identity_contract(
        _blueprint(),
        {
            "business_dnas": ["Manufacturing"],
            "question_modules": ["capital_allocation"],
            "report_template": "manufacturing_v1",
            "rationale": ["Operations and production signals dominate."],
            "evidence_used": ["Plant operations"],
            "confidence": 0.7,
            "rejected_dnas": [],
        },
    )

    assert manifest["failures"] == []


def test_conflict_detection_fails_when_blueprint_and_classification_disagree():
    blueprint = _blueprint("sample_conflict_co")
    blueprint.dnas = []
    blueprint.dnas_source = None
    blueprint.dnas = align_blueprint_with_classification(
        blueprint,
        {
            "business_dnas": ["Enterprise Platform"],
            "question_modules": ["technology", "platform_dependency", "platform_economics"],
            "report_template": "software_v1",
            "rationale": ["Platform evidence is sustained across the business description."],
            "evidence_used": ["API-first platform architecture"],
            "confidence": 0.84,
            "rejected_dnas": [],
        },
    ).dnas
    blueprint.dnas_source = "manual"
    blueprint.dnas[0].name = "Manufacturing"

    with pytest.raises(ValueError, match="conflicts with business_classification.business_dnas"):
        ensure_business_identity_contract(
            blueprint,
            {
                "business_dnas": ["Enterprise Platform"],
                "question_modules": ["technology", "platform_dependency", "platform_economics"],
                "report_template": "software_v1",
                "rationale": ["Platform evidence is sustained across the business description."],
                "evidence_used": ["API-first platform architecture"],
                "confidence": 0.84,
                "rejected_dnas": [],
            },
        )


def test_empty_classification_with_rationale_returns_warning_not_silent_pass():
    manifest = build_business_identity_manifest(
        _blueprint("sample_empty_evidence_co"),
        {
            "business_dnas": [],
            "question_modules": [],
            "report_template": "generic_v1",
            "rationale": ["Current evidence does not strongly support an official DNA selection."],
            "evidence_used": ["Mixed general operating language"],
            "confidence": 0.22,
            "rejected_dnas": [{"name": "Manufacturing", "reason": "No sustained production evidence."}],
        },
    )

    assert manifest["conflict_status"] == "warning"
    assert any("No official Business DNAs were selected" in warning for warning in manifest["warnings"])
