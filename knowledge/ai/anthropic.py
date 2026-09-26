from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import anthropic as _anthropic_lib
except ImportError:  # pragma: no cover
    _anthropic_lib = None  # type: ignore

from .base import BaseAIProvider
from .exceptions import AIProviderError, AIRateLimitError, AIResponseError, AITimeoutError
from .schema import AIResponse

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

_DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicProvider(BaseAIProvider):
    provider_name = "anthropic"

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, timeout_seconds: float = 180.0):
        if _anthropic_lib is None:
            raise AIProviderError("anthropic package is not installed")
        self.model = model or os.getenv("ANTHROPIC_MODEL") or _DEFAULT_MODEL
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise AIProviderError("ANTHROPIC_API_KEY is required")
        self.timeout_seconds = timeout_seconds
        self.client = _anthropic_lib.Anthropic(api_key=api_key)

    def generate(
        self,
        prompt: str,
        response_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AIResponse:
        # When a JSON schema is requested, append a JSON-only instruction to the system prompt
        sys = system_prompt or ""
        if response_schema is not None:
            json_instruction = "\n\nIMPORTANT: Respond with valid JSON only — no markdown fences, no prose before or after."
            sys = (sys + json_instruction).strip()

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or 8192,
            "messages": [{"role": "user", "content": prompt}],
        }
        if sys:
            kwargs["system"] = sys
        # Anthropic doesn't support temperature=0 natively in all versions; use 0 → 0
        if temperature not in (None, 0, 0.0):
            kwargs["temperature"] = temperature

        start = time.perf_counter()
        try:
            response = self.client.messages.create(**kwargs)
        except Exception as exc:
            msg = str(exc).lower()
            if "rate" in msg or "429" in msg or "overloaded" in msg:
                raise AIRateLimitError("Anthropic rate limit exceeded") from exc
            if "timeout" in msg:
                raise AITimeoutError("Anthropic request timed out") from exc
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc

        latency_ms = (time.perf_counter() - start) * 1000

        try:
            text = response.content[0].text
        except (AttributeError, IndexError, TypeError) as exc:
            raise AIResponseError("Anthropic response did not include text content") from exc

        if not text:
            raise AIResponseError("Anthropic response returned empty text")

        usage = getattr(response, "usage", None)
        return AIResponse(
            text=text,
            provider=self.provider_name,
            model=getattr(response, "model", None) or self.model,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "input_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "output_tokens", None) if usage else None,
            total_tokens=(
                (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0)
                if usage else None
            ),
        )
