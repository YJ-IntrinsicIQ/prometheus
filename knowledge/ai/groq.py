from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import httpx

from .base import BaseAIProvider
from .exceptions import AIRateLimitError, AIResponseError, AITimeoutError, AIProviderError
from .retry import is_retryable_empty_response_error
from .schema import AIResponse

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local configuration helper
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(ROOT / ".env")


def resolve_groq_model(default: str = "openai/gpt-oss-120b") -> str:
    return os.getenv("GROQ_MODEL") or os.getenv("AI_MODEL") or default


def _json_output_system_prompt() -> str:
    return (
        "Return exactly one valid JSON object. "
        "Do not include markdown, comments, prose, or trailing commas. "
        "All numeric fields must be valid JSON numbers, never words or quoted strings."
    )


class GroqProvider(BaseAIProvider):
    provider_name = "groq"
    api_url = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ):
        self.model = model or os.getenv("GROQ_MODEL") or os.getenv("AI_MODEL") or ""
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.timeout_seconds = timeout_seconds

        if not self.model:
            raise AIProviderError("Groq model is required. Set GROQ_MODEL or AI_MODEL.")
        if not self.api_key:
            raise AIProviderError("Groq API key is required. Set GROQ_API_KEY.")

    def generate(
        self,
        prompt: str,
        response_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AIResponse:
        payload = self._build_payload(
            prompt=prompt,
            response_schema=response_schema,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )
        start = time.perf_counter()
        attempts = 2
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                    response = client.post(
                        self.api_url,
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    response.raise_for_status()
                    response_payload = response.json()

                latency_ms = (time.perf_counter() - start) * 1000
                return self._parse_response(response_payload, latency_ms)
            except AIResponseError as exc:
                last_error = exc
                if is_retryable_empty_response_error(exc) and attempt < attempts:
                    continue
                raise
            except httpx.TimeoutException as exc:
                raise AITimeoutError("Groq request timed out") from exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code == 429:
                    raise AIRateLimitError("Groq rate limit exceeded") from exc
                raise AIProviderError(
                    f"Groq request failed with HTTP {status_code}: {exc.response.text}"
                ) from exc
            except json.JSONDecodeError as exc:
                raise AIResponseError("Groq returned malformed JSON") from exc
            except ValueError as exc:
                raise AIResponseError("Groq returned malformed JSON") from exc
            except httpx.RequestError as exc:
                last_error = exc
                raise AIProviderError(f"Groq request failed: {exc}") from exc

        if last_error is not None:
            raise AIProviderError(f"Groq request failed before a response was returned: {last_error}") from last_error
        raise AIProviderError("Groq request failed before a response was returned")

    def _build_payload(
        self,
        prompt: str,
        response_schema: Optional[Dict[str, Any]],
        temperature: float,
        max_tokens: Optional[int],
        system_prompt: Optional[str],
    ) -> Dict[str, Any]:
        messages = []
        effective_system_prompt = system_prompt
        if response_schema is not None:
            json_system_prompt = _json_output_system_prompt()
            effective_system_prompt = (
                f"{system_prompt}\n\n{json_system_prompt}"
                if system_prompt
                else json_system_prompt
            )
        if effective_system_prompt:
            messages.append({"role": "system", "content": effective_system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _parse_response(self, payload: Dict[str, Any], latency_ms: float) -> AIResponse:
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIResponseError("Groq response did not include message content") from exc

        usage = payload.get("usage") or {}
        return AIResponse(
            text=text,
            provider=self.provider_name,
            model=payload.get("model") or self.model,
            latency_ms=latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
