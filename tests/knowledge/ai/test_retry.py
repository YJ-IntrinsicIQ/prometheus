from __future__ import annotations

from knowledge.ai import AIResponseError
from knowledge.ai.retry import is_retryable_empty_response_error


def test_retry_helper_identifies_empty_response_errors():
    assert is_retryable_empty_response_error(AIResponseError("OpenAI response did not include message content"))
    assert is_retryable_empty_response_error(AIResponseError("empty structured response from model"))
    assert not is_retryable_empty_response_error(AIResponseError("bad json"))
    assert not is_retryable_empty_response_error(ValueError("openai response did not include message content"))
