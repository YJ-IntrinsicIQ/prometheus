from types import SimpleNamespace

import pytest

from knowledge.ai import AIProviderError, AIRateLimitError, AIResponseError, AITimeoutError, OpenAIProvider
from knowledge.ai.openai import (
    resolve_openai_max_retries,
    resolve_openai_model,
    resolve_openai_timeout_seconds,
)


def test_openai_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    with pytest.raises(AIProviderError):
        OpenAIProvider()


def test_openai_provider_construction_from_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    provider = OpenAIProvider()

    assert provider.provider_name == "openai"
    assert provider.model == "gpt-test"
    assert provider.timeout_seconds == 180.0
    assert provider.max_retries == 2


def test_resolve_openai_model_respects_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-primary")
    monkeypatch.setenv("AI_MODEL", "fallback-model")

    assert resolve_openai_model() == "gpt-primary"


def test_resolve_openai_timeout_seconds_respects_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "240")

    assert resolve_openai_timeout_seconds() == 240.0


def test_resolve_openai_timeout_seconds_falls_back_on_invalid_value(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "not-a-number")

    assert resolve_openai_timeout_seconds() == 180.0


def test_resolve_openai_max_retries_respects_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "5")

    assert resolve_openai_max_retries() == 5


def test_openai_payload_supports_json_mode(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAIProvider(model="gpt-test")

    payload = provider._build_payload(
        prompt="Return JSON",
        response_schema={"type": "object"},
        temperature=0.2,
        max_tokens=100,
        system_prompt="You are precise.",
    )

    assert payload["model"] == "gpt-test"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 100
    assert payload["temperature"] == 0.2
    assert payload["messages"][0] == {"role": "system", "content": "You are precise."}
    assert payload["messages"][1] == {"role": "user", "content": "Return JSON"}


def test_openai_generate_happy_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                model=kwargs["model"],
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

    class FakeOpenAI:
        def __init__(self, api_key, timeout, max_retries):
            self.api_key = api_key
            self.timeout = timeout
            self.max_retries = max_retries
            captured["api_key"] = api_key
            captured["timeout"] = timeout
            captured["max_retries"] = max_retries
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("knowledge.ai.openai.OpenAI", FakeOpenAI)

    provider = OpenAIProvider(model="gpt-test")
    response = provider.generate(prompt="hello", response_schema={"type": "object"})

    assert response.provider == "openai"
    assert response.model == "gpt-test"
    assert response.text == '{"ok": true}'
    assert response.prompt_tokens == 10
    assert response.completion_tokens == 5
    assert response.total_tokens == 15
    assert captured == {
        "api_key": "test-key",
        "timeout": 180.0,
        "max_retries": 2,
    }


def test_openai_generate_maps_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeOpenAI:
        def __init__(self, api_key, timeout, max_retries):
            def create(**kwargs):
                raise __import__("knowledge.ai.openai", fromlist=["APITimeoutError"]).APITimeoutError("timeout")

            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setattr("knowledge.ai.openai.OpenAI", FakeOpenAI)
    provider = OpenAIProvider(model="gpt-test")

    with pytest.raises(AITimeoutError):
        provider.generate(prompt="hello")


def test_openai_generate_maps_rate_limit(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeRateLimitError(Exception):
        pass

    class FakeOpenAI:
        def __init__(self, api_key, timeout, max_retries):
            def create(**kwargs):
                raise FakeRateLimitError("rate limited")

            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    monkeypatch.setattr("knowledge.ai.openai.RateLimitError", FakeRateLimitError)
    monkeypatch.setattr("knowledge.ai.openai.OpenAI", FakeOpenAI)
    provider = OpenAIProvider(model="gpt-test")

    with pytest.raises(AIRateLimitError):
        provider.generate(prompt="hello")


def test_openai_parse_rejects_missing_message_content(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeOpenAI:
        def __init__(self, api_key, timeout, max_retries):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: SimpleNamespace(
                        model="gpt-test",
                        choices=[SimpleNamespace(message=SimpleNamespace(content=""))],
                        usage=None,
                    )
                )
            )

    monkeypatch.setattr("knowledge.ai.openai.OpenAI", FakeOpenAI)
    provider = OpenAIProvider(model="gpt-test")

    with pytest.raises(AIResponseError):
        provider.generate(prompt="hello")


def test_openai_provider_uses_env_timeout_and_retries(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "210")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "4")

    provider = OpenAIProvider()

    assert provider.timeout_seconds == 210.0
    assert provider.max_retries == 4
