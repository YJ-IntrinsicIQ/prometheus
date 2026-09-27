"""
Execution budget guard for Prometheus AI pipelines.

Reads limits from env vars; raises AIBudgetExceededError on violation.
Never silently skips validation — callers must handle the exception.

Env vars:
    PROMETHEUS_AI_MAX_CALLS     — max total API calls per run (default: unlimited)
    PROMETHEUS_AI_MAX_TOKENS    — max total tokens per run (default: unlimited)
    PROMETHEUS_AI_MAX_COST_USD  — max estimated cost per run (default: unlimited)
    PROMETHEUS_AI_BUDGET_MODE   — 'strict' (default) or 'warn' (log only, never raise)

Override for certification runs:
    PROMETHEUS_AI_BUDGET_OVERRIDE=1  — disables all budget limits
"""
from __future__ import annotations

import os
from typing import Optional


class AIBudgetExceededError(Exception):
    """Raised when a configured pipeline budget is exceeded."""
    def __init__(self, dimension: str, used: float, limit: float) -> None:
        self.dimension = dimension
        self.used = used
        self.limit = limit
        super().__init__(
            f"AI_BUDGET_EXCEEDED: {dimension} used={used:.1f} limit={limit:.1f}. "
            "Stop the run and increase the limit or use PROMETHEUS_AI_BUDGET_OVERRIDE=1."
        )


def _env_float(key: str) -> Optional[float]:
    v = os.getenv(key)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def check_budget(
    calls_used: int = 0,
    tokens_used: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """
    Check current pipeline consumption against configured limits.

    Call this before each AI invocation.
    Raises AIBudgetExceededError on violation (unless budget mode is 'warn').
    """
    if os.getenv("PROMETHEUS_AI_BUDGET_OVERRIDE", "").strip() == "1":
        return

    mode = os.getenv("PROMETHEUS_AI_BUDGET_MODE", "strict").strip().lower()

    def _check(dimension: str, used: float, limit: Optional[float]) -> None:
        if limit is not None and used >= limit:
            err = AIBudgetExceededError(dimension, used, limit)
            if mode == "warn":
                import warnings
                warnings.warn(str(err), stacklevel=3)
            else:
                raise err

    _check("calls", calls_used, _env_float("PROMETHEUS_AI_MAX_CALLS"))
    _check("tokens", tokens_used, _env_float("PROMETHEUS_AI_MAX_TOKENS"))
    _check("cost_usd", cost_usd, _env_float("PROMETHEUS_AI_MAX_COST_USD"))
