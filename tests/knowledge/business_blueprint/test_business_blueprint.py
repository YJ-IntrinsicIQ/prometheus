from knowledge.business_blueprint import (
    BusinessBlueprint,
    BusinessCharacteristic,
    BusinessDNA,
    BusinessUnderstanding,
    Metadata,
    BlueprintValidationError,
    validate_blueprint,
    validate_blueprint_payload,
)


def test_blueprint_validates_successfully():
    blueprint = BusinessBlueprint(
        metadata=Metadata(company="Acme"),
        business_understanding=BusinessUnderstanding(
            business_summary="Manufactures advanced materials",
            business_model="B2B manufacturing",
        ),
        characteristics=[BusinessCharacteristic(name="Operational excellence", confidence=0.8)],
        dnas=[BusinessDNA(name="Technology-first", confidence=0.9)],
        reasoning=["The company focuses on disciplined execution"],
    )

    errors = validate_blueprint(blueprint)

    assert errors == []


def test_blueprint_payload_rejects_duplicate_dna():
    payload = {
        "metadata": {"company": "Acme", "version": "1.0", "confidence": 0.8},
        "business_understanding": {
            "business_summary": "Manufactures advanced materials",
            "business_model": "B2B manufacturing",
            "value_creation": "Creates premium products",
            "competitive_position": "Leads in niche markets",
        },
        "characteristics": [{"name": "Operational excellence", "confidence": 0.8}],
        "dnas": [
            {"name": "Technology-first", "confidence": 0.9},
            {"name": "technology-first", "confidence": 0.8},
        ],
        "reasoning": [{"statement": "The company focuses on disciplined execution"}],
    }

    try:
        validate_blueprint_payload(payload)
    except BlueprintValidationError as exc:
        assert "duplicate dna entry" in str(exc)
    else:
        raise AssertionError("Expected duplicate DNA validation error")
