from knowledge.ai import AIRequest, AIResponse


def test_ai_request_defaults():
    request = AIRequest(prompt="Summarize this")

    assert request.prompt == "Summarize this"
    assert request.temperature == 0.0
    assert request.max_tokens is None
    assert request.response_schema is None
    assert request.system_prompt is None


def test_ai_response_records_provider_metadata():
    response = AIResponse(
        text="Done",
        provider="mock",
        model="mock-model",
        latency_ms=1.5,
        prompt_tokens=2,
        completion_tokens=1,
        total_tokens=3,
    )

    assert response.text == "Done"
    assert response.provider == "mock"
    assert response.model == "mock-model"
    assert response.latency_ms == 1.5
    assert response.total_tokens == 3
