"""
Anthropic Claude provider for the AI abstraction layer.

Supports the same BaseAIProvider interface used by the executor.
JSON-structured output is requested via system-prompt instruction + schema hint.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from .base import BaseAIProvider
from .exceptions import AIProviderError, AIResponseError
from .schema import AIResponse


def resolve_anthropic_model(default: str = "claude-haiku-4-5-20251001") -> str:
    return os.getenv("ANTHROPIC_MODEL") or os.getenv("AI_MODEL") or default


class AnthropicProvider(BaseAIProvider):
    provider_name = "anthropic"

    def __init__(self, model: Optional[str] = None):
        try:
            import anthropic as _anthropic
            self._client = _anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        except ImportError as exc:
            raise AIProviderError("anthropic SDK not installed") from exc
        # Ignore non-Anthropic model names (e.g. "gpt-4o-mini" from OPENAI_MODEL env)
        if model and not model.startswith("claude"):
            model = None
        self.model = model or resolve_anthropic_model()

    def generate(
        self,
        prompt: str,
        response_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AIResponse:
        system_parts = []
        if system_prompt:
            system_parts.append(system_prompt)
        if response_schema:
            schema_str = json.dumps(response_schema, indent=2)
            system_parts.append(
                f"You MUST respond with valid JSON only — no markdown, no preamble, no explanation.\n"
                f"The JSON must conform exactly to this schema:\n{schema_str}"
            )
        else:
            system_parts.append("Respond with valid JSON only — no markdown, no preamble.")

        system = "\n\n".join(system_parts)

        t0 = time.monotonic()
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens or 2000,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise AIResponseError(f"Anthropic API error: {exc}") from exc

        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        raw_text = resp.content[0].text if resp.content else ""

        # Strip markdown fences if present
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        text = text.strip()

        usage = getattr(resp, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        total_tokens = (input_tokens or 0) + (output_tokens or 0) if input_tokens is not None else None

        return AIResponse(
            text=text,
            provider="anthropic",
            model=self.model,
            latency_ms=latency_ms,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=total_tokens,
        )
