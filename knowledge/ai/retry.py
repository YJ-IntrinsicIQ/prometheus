from __future__ import annotations

from .exceptions import AIResponseError


EMPTY_RESPONSE_ERROR_MARKERS = (
    "did not include message content",
    "empty response from model",
    "empty structured response",
)


def is_retryable_empty_response_error(error: Exception) -> bool:
    if not isinstance(error, AIResponseError):
        return False
    message = str(error).strip().lower()
    return any(marker in message for marker in EMPTY_RESPONSE_ERROR_MARKERS)
