from knowledge.ai import AIProviderError, AIRateLimitError, AIResponseError, AITimeoutError


def test_ai_exceptions_share_provider_base():
    assert issubclass(AIRateLimitError, AIProviderError)
    assert issubclass(AIResponseError, AIProviderError)
    assert issubclass(AITimeoutError, AIProviderError)
