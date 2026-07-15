import json

import pytest

from knowledge.business_blueprint import BusinessBlueprint
from knowledge.business_blueprint.constants import DEFAULT_BLUEPRINT_VERSION
from knowledge.business_interpreter import (
    BusinessInterpretationResult,
    BusinessInterpreter,
    ParserError,
    ValidationError,
    build_prompt,
    parse_interpretation_bundle,
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
    def llm_stub(prompt: str) -> str:
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
                "candidate_dna_signals": [
                    {
                        "name": "Manufacturing",
                        "confidence": 0.81,
                        "supporting_reason": "Physical operations dominate the memory.",
                        "evidence_ids": [],
                    }
                ],
                "reasoning": [{"statement": "The memory emphasizes physical operations and capital deployment."}],
                "classification": {
                    "selected_dnas": [
                        {"name": "Manufacturing", "confidence": 0.81, "reason": "Physical operations dominate the evidence."}
                    ],
                    "rejected_dnas": [],
                    "rationale": ["Manufacturing is supported by physical operations and capital deployment."],
                    "evidence_used": ["Manufactures industrial equipment"],
                    "confidence": 0.81,
                },
            }
        )

    interpreter = BusinessInterpreter(_company_memory(), llm_client=llm_stub)
    result = interpreter.interpret()

    assert isinstance(result, BusinessInterpretationResult)
    assert isinstance(result.blueprint, BusinessBlueprint)
    assert result.blueprint.metadata.company == "acme"
    assert result.blueprint.business_understanding.business_summary == "Manufactures industrial equipment"
    assert [item.name for item in result.blueprint.characteristics] == ["Capital Intensive", "Asset Heavy"]
    assert result.blueprint.candidate_dna_signals[0].name == "Manufacturing"
    assert result.classification["selected_dnas"][0]["name"] == "Manufacturing"


def test_parser_rejects_malformed_json():
    with pytest.raises(ParserError):
        parse_interpretation_payload("{not valid json}")


def test_parser_extracts_blueprint_and_classification_bundle():
    payload = json.dumps(
        {
            "metadata": {"company": "acme", "version": "1.0", "confidence": 0.7},
            "business_understanding": {
                "business_summary": "Makes goods",
                "business_model": "Manufacturing",
                "value_creation": "Creates value",
                "competitive_position": "Competes in niche market",
            },
            "characteristics": [{"name": "Capital Intensive", "confidence": 0.8}],
            "candidate_dna_signals": [
                {
                    "name": "Manufacturing",
                    "confidence": 0.8,
                    "supporting_reason": "Physical operations dominate.",
                    "evidence_ids": [],
                }
            ],
            "reasoning": [{"statement": "Reasoning is present."}],
            "classification": {
                "selected_dnas": [{"name": "Manufacturing", "confidence": 0.8, "reason": "Physical operations dominate."}],
                "rejected_dnas": [{"name": "Enterprise Platform", "reason": "No software-platform evidence."}],
                "rationale": ["Manufacturing fits best."],
                "evidence_used": ["Makes goods"],
                "confidence": 0.8,
            },
        }
    )

    parsed = parse_interpretation_bundle(payload)

    assert parsed.blueprint.metadata.company == "acme"
    assert parsed.classification["selected_dnas"][0]["name"] == "Manufacturing"


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


def test_prompt_matches_blueprint_validator_contract():
    prompt = build_prompt(_company_memory())

    assert f'"version": "{DEFAULT_BLUEPRINT_VERSION}"' in prompt
    assert '"business_summary": ""' in prompt
    assert '"characteristics"' in prompt
    assert '"candidate_dna_signals"' in prompt
    assert "business_characteristics" not in prompt


def test_prompt_uses_compact_company_memory_view():
    prompt = build_prompt(_company_memory())

    assert '"facts": []' in prompt
    assert '"company_id": "acme"' in prompt


def test_prompt_explicitly_marks_business_summary_as_required():
    prompt = build_prompt(_company_memory())

    assert "business_understanding.business_summary" in prompt
    assert "required and must be a concise, non-empty string" in prompt.lower()
    assert "Before finalizing your answer" in prompt


def test_prompt_requires_numeric_confidence_values():
    prompt = build_prompt(_company_memory())

    assert "Every `confidence` value must be a JSON number between 0 and 1." in prompt
    assert "Never write confidence values as words" in prompt
    assert "every `confidence` value is a valid JSON number" in prompt


def test_prompt_discourages_generic_characteristics_and_prefers_specific_ones():
    prompt = build_prompt(_company_memory())

    assert "Avoid vague generic labels such as `Sustainability`, `Innovation`, `Social Responsibility`, or `Human Resources`" in prompt
    assert "`Semiconductor manufacturing`" in prompt
    assert "`Export-led expansion via overseas subsidiaries`" in prompt
    assert "Prefer specific multi-word phrases over abstract single-word labels." in prompt


def test_prompt_includes_classification_context_when_supplied():
    prompt = build_prompt(
        _company_memory(),
        classification_context={
            "allowed_dnas": ["Manufacturing", "Enterprise Platform"],
            "candidate_archetypes": [
                {
                    "dnas": ["Manufacturing"],
                    "definition": "Physical production business.",
                    "positive_signals": ["Plant expansion"],
                    "negative_signals": ["Pure software revenue"],
                }
            ],
        },
    )

    assert "Classification Context" in prompt
    assert '"allowed_dnas"' in prompt
    assert "Do not infer a DNA from generic words alone" in prompt
    assert "authoritative final business dna selection" in prompt.lower()


def test_validator_derives_candidate_dna_signals_from_selected_dnas_when_missing():
    payload = {
        "metadata": {"company": "acme", "version": "1.0", "confidence": 0.7},
        "business_understanding": {
            "business_summary": "Makes goods",
            "business_model": "Manufacturing",
            "value_creation": "Creates value",
            "competitive_position": "Competes in niche market",
        },
        "characteristics": [{"name": "Capital Intensive", "confidence": 0.8}],
        "reasoning": [{"statement": "Reasoning is present."}],
        "classification": {
            "selected_dnas": [{"name": "Manufacturing", "confidence": 0.8, "reason": "Physical operations dominate."}],
            "rejected_dnas": [],
            "rationale": ["Manufacturing fits best."],
            "evidence_used": ["Makes goods"],
            "confidence": 0.8,
        },
    }

    blueprint, classification = validate_blueprint_payload(payload)

    assert classification["selected_dnas"][0]["name"] == "Manufacturing"
    assert blueprint.candidate_dna_signals[0].name == "Manufacturing"
