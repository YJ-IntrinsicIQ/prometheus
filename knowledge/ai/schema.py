from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AIRequest:
    prompt: str
    temperature: float = 0.0
    max_tokens: Optional[int] = None
    response_schema: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None


@dataclass
class AIResponse:
    text: str
    provider: str
    model: str
    latency_ms: float
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
