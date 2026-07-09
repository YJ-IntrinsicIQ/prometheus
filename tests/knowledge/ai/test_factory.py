import json

import pytest

from knowledge.ai import AIProviderError, GroqProvider, MockProvider, OpenAIProvider, get_llm
from knowledge.business_interpreter import validate_blueprint_payload


def test_factory_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    provider = get_llm()

    assert isinstance(provider, MockProvider)
    payload = json.loads(provider.generate(prompt="hello").text)
    assert validate_blueprint_payload(payload)


def test_factory_returns_mock_from_configuration(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AI_MODEL", "unit-test-model")
    monkeypatch.setenv("AI_MOCK_RESPONSE", "configured")

    provider = get_llm()

    assert isinstance(provider, MockProvider)
    assert provider.model == "unit-test-model"
    assert provider.generate(prompt="hello").text == "configured"


def test_factory_uses_default_valid_mock_response_when_unconfigured(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.delenv("AI_MOCK_RESPONSE", raising=False)

    provider = get_llm()

    payload = json.loads(provider.generate(prompt="hello").text)
    assert validate_blueprint_payload(payload)


def test_factory_returns_groq_from_configuration(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-test")

    provider = get_llm()

    assert isinstance(provider, GroqProvider)
    assert provider.model == "llama-test"


def test_factory_returns_openai_from_configuration(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    provider = get_llm()

    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-test"


def test_factory_rejects_unknown_provider():
    with pytest.raises(AIProviderError):
        get_llm(provider="unknown")
