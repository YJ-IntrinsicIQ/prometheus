from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, List, Optional

from knowledge.business_blueprint import DEFAULT_BLUEPRINT_VERSION

from .base import BaseAIProvider
from .schema import AIResponse


DEFAULT_MOCK_RESPONSE = json.dumps(
    {
        "metadata": {
            "company": "mock-company",
            "version": DEFAULT_BLUEPRINT_VERSION,
            "confidence": 0.5,
        },
        "business_understanding": {
            "business_summary": "Mock business summary for local smoke tests.",
            "business_model": "Mock business model.",
            "value_creation": "Mock value creation.",
            "competitive_position": "Mock competitive position.",
        },
        "characteristics": [
            {
                "name": "Mock Characteristic",
                "confidence": 0.5,
            }
        ],
        "reasoning": [
            {
                "statement": "Default mock response used for deterministic local smoke tests.",
            }
        ],
        "classification": {
            "selected_dnas": [
                {
                    "name": "Consumer",
                    "confidence": 0.5,
                    "reason": "Mock fixture uses a simple brand-style archetype for deterministic local tests.",
                }
            ],
            "rejected_dnas": [],
            "rationale": [
                "Mock fixture returns a deterministic classification payload for smoke tests."
            ],
            "evidence_used": [
                "Mock business summary for local smoke tests."
            ],
            "confidence": 0.5,
        },
    }
)


class MockProvider(BaseAIProvider):
    provider_name = "mock"

    def __init__(
        self,
        responses: Optional[Iterable[str]] = None,
        model: str = "mock-model",
    ):
        self.model = model
        self._responses: List[str] = list(responses or [DEFAULT_MOCK_RESPONSE])
        self._index = 0

    def generate(
        self,
        prompt: str,
        response_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AIResponse:
        start = time.perf_counter()
        text = self._next_response()
        latency_ms = (time.perf_counter() - start) * 1000
        prompt_tokens = count_tokens(prompt)
        completion_tokens = count_tokens(text)
        return AIResponse(
            text=text,
            provider=self.provider_name,
            model=self.model,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    def _next_response(self) -> str:
        if not self._responses:
            return ""
        if self._index >= len(self._responses):
            return self._responses[-1]
        response = self._responses[self._index]
        self._index += 1
        return response


def count_tokens(text: str) -> int:
    return len((text or "").split())
