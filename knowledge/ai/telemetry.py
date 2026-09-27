"""
Lightweight token and cost telemetry for Prometheus AI pipelines.

Usage:
    tel = TelemetryCollector()
    tel.record("claim_review", model="gpt-4o-mini", company="sun_pharma",
               prompt_tokens=800, completion_tokens=300, cache_hit=False, batch_size=1)
    print(tel.summary())

Pricing is configuration-driven via PROMETHEUS_COST_PER_1K_PROMPT_TOKENS and
PROMETHEUS_COST_PER_1K_COMPLETION_TOKENS. Defaults to gpt-4o-mini pricing as
a conservative placeholder.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _cost_per_1k_prompt() -> float:
    return float(os.getenv("PROMETHEUS_COST_PER_1K_PROMPT_TOKENS", "0.000150"))


def _cost_per_1k_completion() -> float:
    return float(os.getenv("PROMETHEUS_COST_PER_1K_COMPLETION_TOKENS", "0.000600"))


@dataclass
class CallRecord:
    stage: str
    model: str
    company: str
    prompt_tokens: int
    completion_tokens: int
    cache_hit: bool
    batch_size: int
    latency_ms: Optional[float]
    estimated_cost_usd: float


@dataclass
class TelemetryCollector:
    _records: List[CallRecord] = field(default_factory=list)

    def record(
        self,
        stage: str,
        *,
        model: str = "",
        company: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_hit: bool = False,
        batch_size: int = 1,
        latency_ms: Optional[float] = None,
    ) -> None:
        cost = 0.0
        if not cache_hit:
            cost = (
                prompt_tokens * _cost_per_1k_prompt() / 1000
                + completion_tokens * _cost_per_1k_completion() / 1000
            )
        self._records.append(CallRecord(
            stage=stage,
            model=model,
            company=company,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_hit=cache_hit,
            batch_size=batch_size,
            latency_ms=latency_ms,
            estimated_cost_usd=cost,
        ))

    def total_calls(self) -> int:
        return len(self._records)

    def cache_hits(self) -> int:
        return sum(1 for r in self._records if r.cache_hit)

    def total_prompt_tokens(self) -> int:
        return sum(r.prompt_tokens for r in self._records if not r.cache_hit)

    def total_completion_tokens(self) -> int:
        return sum(r.completion_tokens for r in self._records if not r.cache_hit)

    def total_tokens(self) -> int:
        return self.total_prompt_tokens() + self.total_completion_tokens()

    def estimated_cost_usd(self) -> float:
        return sum(r.estimated_cost_usd for r in self._records)

    def summary(self) -> Dict:
        by_stage: Dict[str, Dict] = {}
        for r in self._records:
            s = by_stage.setdefault(r.stage, {"calls": 0, "cache_hits": 0, "tokens": 0, "cost_usd": 0.0})
            s["calls"] += 1
            if r.cache_hit:
                s["cache_hits"] += 1
            else:
                s["tokens"] += r.prompt_tokens + r.completion_tokens
                s["cost_usd"] += r.estimated_cost_usd
        return {
            "total_calls": self.total_calls(),
            "cache_hits": self.cache_hits(),
            "total_prompt_tokens": self.total_prompt_tokens(),
            "total_completion_tokens": self.total_completion_tokens(),
            "total_tokens": self.total_tokens(),
            "estimated_cost_usd": round(self.estimated_cost_usd(), 6),
            "by_stage": by_stage,
        }
