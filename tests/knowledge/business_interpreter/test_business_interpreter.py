import json

import pytest

from knowledge.business_blueprint import BusinessBlueprint
from knowledge.business_interpreter import (
    BusinessInterpreter,
    ParserError,
    ValidationError,
    build_prompt,
    parse_interpretation_payload,
    validate_blueprint_payload,
)
from knowledge.company_memory import CompanyMemory, Entity


def _company_memory() -> CompanyMemory:
    memory = CompanyMemory(company_id="acme")
    entity = Entity(id="entity-1", name="Acme Manufacturing", entity_type="company")
    memory.entities[entity.name] = entity
    return memory


def test_interpreter_builds_blueprint_from_company_memory():
    def fake_llm(prompt: str) -> str:
        return json.dumps(
            {
                "metadata": {
                    "company": "acme",
                    "version": "1.0",
                    "confidence": 0.84,
                },
                "business_understanding": {
                    "business_summary": "Manufactures industrial equipment",
                    "business_model": "B2B manufacturing",
                    "value_creation": "Builds durable equipment for customers",
                    "competitive_position": "Serves niche industrial markets",
                },
                "characteristics": [
                    {"name": "Capital Intensive", "confidence": 0.8},
                    {"name": "Asset Heavy", "confidence": 0.7},
                ],
                "reasoning": [{"statement": "The memory emphasizes physical operations and capital deployment."}],
            }
        )

    interpreter = BusinessInterpreter(_company_memory(), llm_client=fake_llm)
    blueprint = interpreter.interpret()

    assert isinstance(blueprint, BusinessBlueprint)
    assert blueprint.metadata.company == "acme"
    assert blueprint.business_understanding.business_summary == "Manufactures industrial equipment"
    assert [item.name for item in blueprint.characteristics] == ["Capital Intensive", "Asset Heavy"]


def test_parser_rejects_malformed_json():
    with pytest.raises(ParserError):
        parse_interpretation_payload("{not valid json}")


def test_validator_rejects_duplicate_characteristics():
    payload = {
        "metadata": {"company": "acme", "version": "1.0", "confidence": 0.7},
        "business_understanding": {
            "business_summary": "Makes goods",
            "business_model": "Subscription",
            "value_creation": "Creates value",
            "competitive_position": "Competes in niche market",
        },
        "characteristics": [
            {"name": "Capital Intensive", "confidence": 0.8},
            {"name": "capital intensive", "confidence": 0.8},
        ],
        "reasoning": [{"statement": "Reasoning is present."}],
    }

    with pytest.raises(ValidationError):
        validate_blueprint_payload(payload)


def test_prompt_contains_only_company_memory_guidance():
    prompt = build_prompt(_company_memory())

    assert "Company Memory" in prompt
    assert "never invent facts" in prompt.lower()
    assert "return valid json only" in prompt.lower()
