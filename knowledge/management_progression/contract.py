from __future__ import annotations

from typing import Any, Dict, List


SCHEMA_VERSION = "management_progression.v1"

COVERAGE_STATUSES = {"supported", "partial", "insufficient_evidence"}
EVENT_ROLES = {
    "statement",
    "commitment",
    "action",
    "milestone",
    "completion",
    "outcome",
    "reversal",
    "abandonment",
    "historical_context",
}
EVENT_TYPES = {
    "product_launch",
    "capacity_expansion",
    "project_execution",
    "capital_deployment",
    "commentary_change",
    "risk_response",
    "strategic_change",
    "financial_outcome",
    "other",
}
CURRENT_STATUSES = {
    "announced",
    "in_progress",
    "delivered",
    "partially_delivered",
    "failed",
    "reversed",
    "abandoned",
    "unresolved",
    "historical_context",
}
VERIFICATION_STATUSES = {
    "verified",
    "partially_verified",
    "contradicted",
    "unresolved",
    "not_applicable",
}
THESIS_IMPACTS = {"strengthens", "weakens", "neutral", "unresolved"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}


def confidence(level: str, *, basis: List[str] | None = None, limitations: List[str] | None = None) -> Dict[str, Any]:
    return {
        "level": level if level in CONFIDENCE_LEVELS else "low",
        "basis": list(basis or []),
        "limitations": list(limitations or []),
    }


def evidence_ref(
    *,
    source_artifact: str,
    source_period: str = "",
    evidence_id: str = "",
    source_item_id: str = "",
    field_path: str = "",
    excerpt: str = "",
) -> Dict[str, Any]:
    return {
        "source_artifact": source_artifact,
        "source_period": source_period,
        "evidence_id": evidence_id,
        "source_item_id": source_item_id,
        "field_path": field_path,
        "excerpt": excerpt,
    }

