import json

from knowledge.ai import AIResponse, MockProvider
from knowledge.business_blueprint import BusinessBlueprint
from knowledge.business_interpreter import validate_blueprint_payload


def test_mock_provider_returns_predefined_responses():
    provider = MockProvider(responses=["first", "second"])

    first = provider.generate(prompt="hello world")
    second = provider.generate(prompt="again")
    third = provider.generate(prompt="repeat")

    assert isinstance(first, AIResponse)
    assert first.text == "first"
    assert second.text == "second"
    assert third.text == "second"
    assert first.provider == "mock"
    assert first.model == "mock-model"
    assert first.prompt_tokens == 2
    assert first.completion_tokens == 1
    assert first.total_tokens == 3


def test_mock_provider_returns_valid_json_by_default():
    provider = MockProvider()

    response = provider.generate(prompt="hello world")
    payload = json.loads(response.text)

    assert validate_blueprint_payload(payload)
    assert payload["metadata"]["version"] == BusinessBlueprint.from_dict(payload).metadata.version
    assert payload["characteristics"]
