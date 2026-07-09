import pytest
import httpx

from knowledge.ai import AIProviderError, AIRateLimitError, AIResponseError, AITimeoutError, GroqProvider
from knowledge.ai.groq import resolve_groq_model


def test_groq_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_MODEL", "llama-test")

    with pytest.raises(AIProviderError):
        GroqProvider()


def test_groq_provider_construction_from_environment(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-test")

    provider = GroqProvider()

    assert provider.provider_name == "groq"
    assert provider.model == "llama-test"


def test_resolve_groq_model_defaults_to_gpt_oss(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)

    assert resolve_groq_model() == "openai/gpt-oss-120b"


def test_resolve_groq_model_respects_environment(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "grok-model")
    monkeypatch.setenv("AI_MODEL", "fallback-model")

    assert resolve_groq_model() == "grok-model"


def test_groq_payload_supports_json_mode(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    provider = GroqProvider(model="llama-test")

    payload = provider._build_payload(
        prompt="Return JSON",
        response_schema={"type": "object"},
        temperature=0.2,
        max_tokens=100,
        system_prompt="You are precise.",
    )

    assert payload["model"] == "llama-test"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 100
    assert payload["temperature"] == 0.2
    assert payload["messages"][0]["role"] == "system"
    assert "You are precise." in payload["messages"][0]["content"]
    assert "valid JSON object" in payload["messages"][0]["content"]
    assert payload["messages"][1] == {"role": "user", "content": "Return JSON"}


def test_groq_payload_adds_json_system_prompt_when_none_provided(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    provider = GroqProvider(model="llama-test")

    payload = provider._build_payload(
        prompt="Return JSON",
        response_schema={"type": "object"},
        temperature=0.0,
        max_tokens=None,
        system_prompt=None,
    )

    assert payload["messages"][0]["role"] == "system"
    assert "valid JSON object" in payload["messages"][0]["content"]
    assert "numeric fields must be valid JSON numbers" in payload["messages"][0]["content"]
    assert payload["messages"][1] == {"role": "user", "content": "Return JSON"}


def test_groq_generate_maps_timeout(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    provider = GroqProvider(model="llama-test")

    class TimeoutClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def post(self, url, json, headers):
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr("knowledge.ai.groq.httpx.Client", TimeoutClient)

    with pytest.raises(AITimeoutError):
        provider.generate(prompt="hello")


def test_groq_generate_maps_rate_limit(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    provider = GroqProvider(model="llama-test")

    class RateLimitResponse:
        status_code = 429
        text = "rate limited"

        def raise_for_status(self):
            request = httpx.Request("POST", provider.api_url)
            response = httpx.Response(429, request=request, text=self.text)
            raise httpx.HTTPStatusError("rate limited", request=request, response=response)

    class RateLimitClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def post(self, url, json, headers):
            return RateLimitResponse()

    monkeypatch.setattr("knowledge.ai.groq.httpx.Client", RateLimitClient)

    with pytest.raises(AIRateLimitError):
        provider.generate(prompt="hello")


def test_groq_generate_maps_malformed_json(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    provider = GroqProvider(model="llama-test")

    class MalformedJsonResponse:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("bad json")

    class MalformedJsonClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def post(self, url, json, headers):
            return MalformedJsonResponse()

    monkeypatch.setattr("knowledge.ai.groq.httpx.Client", MalformedJsonClient)

    with pytest.raises(AIResponseError):
        provider.generate(prompt="hello")
