from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from .base import BaseAIProvider
from .exceptions import AIRateLimitError, AIResponseError, AITimeoutError, AIProviderError
from .retry import is_retryable_empty_response_error
from .schema import AIResponse

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local configuration helper
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(ROOT / ".env")


def resolve_deepseek_model(default: str = "deepseek-v4-flash") -> str:
    return os.getenv("DEEPSEEK_MODEL") or os.getenv("AI_MODEL") or default


def resolve_deepseek_timeout_seconds(default: float = 180.0) -> float:
    raw_value = os.getenv("DEEPSEEK_TIMEOUT_SECONDS")
    if raw_value in (None, ""):
        return default
    try:
        timeout = float(raw_value)
    except ValueError:
        return default
    return timeout if timeout > 0 else default


def resolve_deepseek_max_retries(default: int = 2) -> int:
    raw_value = os.getenv("DEEPSEEK_MAX_RETRIES")
    if raw_value in (None, ""):
        return default
    try:
        retries = int(raw_value)
    except ValueError:
        return default
    return retries if retries >= 0 else default


def _json_output_system_prompt() -> str:
    return (
        "Return exactly one valid JSON object. "
        "Do not include markdown, comments, prose, or trailing commas. "
        "All numeric fields must be valid JSON numbers, never words or quoted strings."
    )


class DeepSeekProvider(BaseAIProvider):
    provider_name = "deepseek"
    api_url = "https://api.deepseek.com/chat/completions"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
    ):
        self.model = model or resolve_deepseek_model("")
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else resolve_deepseek_timeout_seconds()
        )
        self.max_retries = (
            max_retries if max_retries is not None else resolve_deepseek_max_retries()
        )

        if not self.model:
            raise AIProviderError("DeepSeek model is required. Set DEEPSEEK_MODEL or AI_MODEL.")
        if not self.api_key:
            raise AIProviderError("DeepSeek API key is required. Set DEEPSEEK_API_KEY.")

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
        attempts = self.max_retries + 1
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
                last_error = exc
                if attempt >= attempts:
                    raise AITimeoutError("DeepSeek request timed out") from exc

            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code == 429:
                    last_error = exc
                    if attempt >= attempts:
                        raise AIRateLimitError("DeepSeek rate limit exceeded") from exc
                    continue

                raise AIProviderError(
                    f"DeepSeek request failed with HTTP {status_code}: {exc.response.text}"
                ) from exc

            except (json.JSONDecodeError, ValueError) as exc:
                raise AIResponseError("DeepSeek returned malformed JSON") from exc

            except httpx.RequestError as exc:
                last_error = exc
                if attempt >= attempts:
                    raise AIProviderError(f"DeepSeek request failed: {exc}") from exc

        if isinstance(last_error, httpx.TimeoutException):
            raise AITimeoutError("DeepSeek request timed out") from last_error
        if isinstance(last_error, httpx.RequestError):
            raise AIProviderError(f"DeepSeek request failed: {last_error}") from last_error
        if isinstance(last_error, httpx.HTTPStatusError):
            raise AIRateLimitError("DeepSeek rate limit exceeded") from last_error

        raise AIProviderError("DeepSeek request failed before a response was returned")

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
        }

        if temperature not in (None, 0, 0.0):
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        return payload

    def _parse_response(self, payload: Dict[str, Any], latency_ms: float) -> AIResponse:
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIResponseError("DeepSeek response did not include message content") from exc

        if not text:
            raise AIResponseError("DeepSeek response did not include message content")

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
