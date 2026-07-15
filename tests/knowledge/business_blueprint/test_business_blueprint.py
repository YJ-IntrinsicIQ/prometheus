from knowledge.business_blueprint import (
    BusinessBlueprint,
    CandidateDNASignal,
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
        candidate_dna_signals=[
            CandidateDNASignal(
                name="Manufacturing",
                confidence=0.82,
                supporting_reason="Operating model and production language support a manufacturing candidate.",
            )
        ],
        dnas=[BusinessDNA(name="Technology-first", confidence=0.9)],
        dnas_source="business_classification",
        reasoning=["The company focuses on disciplined execution"],
    )

    errors = validate_blueprint(blueprint)

    assert errors == []


def test_blueprint_payload_rejects_duplicate_dna_when_present():
    payload = {
        "metadata": {"company": "Acme", "version": "1.0", "confidence": 0.8},
        "business_understanding": {
            "business_summary": "Manufactures advanced materials",
            "business_model": "B2B manufacturing",
            "value_creation": "Creates premium products",
            "competitive_position": "Leads in niche markets",
        },
        "characteristics": [{"name": "Operational excellence", "confidence": 0.8}],
        "candidate_dna_signals": [
            {
                "name": "Manufacturing",
                "confidence": 0.82,
                "supporting_reason": "Plant and operations evidence support manufacturing.",
                "evidence_ids": [],
            }
        ],
        "dnas": [
            {"name": "Technology-first", "confidence": 0.9},
            {"name": "technology-first", "confidence": 0.8},
        ],
        "dnas_source": "business_classification",
        "reasoning": [{"statement": "The company focuses on disciplined execution"}],
    }

    try:
        validate_blueprint_payload(payload)
    except BlueprintValidationError as exc:
        assert "duplicate dna entry" in str(exc)
    else:
        raise AssertionError("Expected duplicate DNA validation error")


def test_blueprint_payload_allows_missing_dnas_when_candidate_signals_exist():
    payload = {
        "metadata": {"company": "Acme", "version": "1.0", "confidence": 0.8},
        "business_understanding": {
            "business_summary": "Manufactures advanced materials",
            "business_model": "B2B manufacturing",
            "value_creation": "Creates premium products",
            "competitive_position": "Leads in niche markets",
        },
        "characteristics": [{"name": "Operational excellence", "confidence": 0.8}],
        "candidate_dna_signals": [
            {
                "name": "Manufacturing",
                "confidence": 0.82,
                "supporting_reason": "Plant and production evidence support manufacturing.",
                "evidence_ids": [],
            }
        ],
        "reasoning": [{"statement": "The company focuses on disciplined execution"}],
    }

    blueprint, errors = validate_blueprint_payload(payload)

    assert errors == []
    assert blueprint.dnas == []
    assert blueprint.candidate_dna_signals[0].name == "Manufacturing"
