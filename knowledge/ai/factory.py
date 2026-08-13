from __future__ import annotations

import os
from typing import Iterable, Optional

from .base import BaseAIProvider
from .exceptions import AIProviderError
from .groq import GroqProvider
from .mock import MockProvider
from .openai import OpenAIProvider
from .deepseek import DeepSeekProvider


def get_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    mock_responses: Optional[Iterable[str]] = None,
) -> BaseAIProvider:
    selected_provider = (provider or os.getenv("AI_PROVIDER") or "mock").strip().lower()

    if selected_provider == "groq":
        return GroqProvider(model=model)
    if selected_provider == "openai":
        return OpenAIProvider(model=model)
    if selected_provider == "deepseek":
        return DeepSeekProvider()
    if selected_provider == "mock":
        configured_response = os.getenv("AI_MOCK_RESPONSE")
        responses = mock_responses
        if responses is None and configured_response is not None:
            responses = [configured_response]
        return MockProvider(responses=responses, model=model or os.getenv("AI_MODEL") or "mock-model")

    raise AIProviderError(f"Unsupported AI provider: {selected_provider}")
