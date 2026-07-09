from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from .schema import AIResponse


class BaseAIProvider(ABC):
    provider_name: str
    model: str

    @abstractmethod
    def generate(
        self,
        prompt: str,
        response_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> AIResponse:
        """
        Generate a completion using the configured provider.

        Provider-specific options must stay inside provider implementations.
        """
