from knowledge.business_blueprint import BusinessBlueprint, BusinessCharacteristic, BusinessUnderstanding, Metadata
from knowledge.business_classifier import BusinessClassifier, ClassificationValidationError, Registry, validate_classification


def build_blueprint() -> BusinessBlueprint:
    return BusinessBlueprint(
        metadata=Metadata(company="Acme"),
        business_understanding=BusinessUnderstanding(
            business_summary="Manufactures advanced equipment",
            business_model="B2B manufacturing",
        ),
        characteristics=[
            BusinessCharacteristic(name="Capital Intensive", confidence=0.9),
            BusinessCharacteristic(name="Technology Driven", confidence=0.8),
            BusinessCharacteristic(name="Asset Heavy", confidence=0.85),
        ],
    )


def test_classifier_returns_deterministic_profile():
    classifier = BusinessClassifier()
    classification = classifier.classify(build_blueprint())

    assert classification["business_dnas"] == ["Manufacturing", "Semiconductor"]
    assert classification["question_modules"] == ["Capex", "Supply Chain", "Technology", "Innovation"]
    assert classification["discovery_profile"]["priority_entities"] == ["Plant", "Technology", "Research"]
    assert classification["extraction_profile"]["high_priority_sections"] == [
        "Operations",
        "Capex",
        "Technology",
        "R&D",
        "Intellectual Property",
    ]
    assert classification["report_template"] == "semiconductor_v1"


def test_registry_can_be_extended_with_custom_mappings():
    registry = Registry([
        {
            "characteristics": ["Recurring Revenue"],
            "dnas": ["Subscription"],
            "question_modules": ["Recurring Revenue"],
            "discovery_profile": {"priority_entities": ["Customer"], "priority_events": ["Renewal"]},
            "extraction_profile": {"high_priority_sections": ["Revenue"]},
            "report_template": "software_v1",
        }
    ])

    result = registry.build_profile(["Recurring Revenue"])

    assert result["business_dnas"] == ["Subscription"]
    assert result["question_modules"] == ["Recurring Revenue"]
    assert result["report_template"] == "software_v1"


def test_validator_rejects_duplicate_dnas():
    classification = {
        "business_dnas": ["Manufacturing", "Manufacturing"],
        "question_modules": ["Capex"],
        "discovery_profile": {"priority_entities": [], "priority_events": []},
        "extraction_profile": {"high_priority_sections": []},
        "report_template": "manufacturing_v1",
    }

    try:
        validate_classification(classification)
    except ClassificationValidationError as exc:
        assert "business_dnas" in str(exc)
    else:
        raise AssertionError("Expected validation failure")
