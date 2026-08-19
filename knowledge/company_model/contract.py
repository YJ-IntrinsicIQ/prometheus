from __future__ import annotations

from typing import Any, Dict, List


SCHEMA_VERSION = "company_model.v1"

COVERAGE_STATUSES = {"supported", "partial", "insufficient_evidence"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
BUSINESS_MODEL_TYPES = {"platform", "manufacturing", "content_ip", "services", "hybrid", "other"}
OFFERING_CATEGORIES = {
    "product",
    "platform",
    "service",
    "content_ip",
    "manufacturing_capability",
    "other",
}
REVENUE_BILLING_BASES = {
    "subscription",
    "usage",
    "license",
    "sale",
    "milestone",
    "royalty",
    "ad_revenue",
    "service_fee",
    "unknown",
}


def evidence_ref(
    *,
    source_artifact: str,
    source_period: str = "",
    evidence_id: str = "",
    field_path: str = "",
    excerpt: str = "",
) -> Dict[str, Any]:
    return {
        "source_artifact": source_artifact,
        "source_period": source_period,
        "evidence_id": evidence_id,
        "field_path": field_path,
        "excerpt": excerpt,
    }


def confidence(level: str, *, basis: List[str] | None = None, limitations: List[str] | None = None) -> Dict[str, Any]:
    normalized = level if level in CONFIDENCE_LEVELS else "low"
    return {
        "level": normalized,
        "basis": list(basis or []),
        "limitations": list(limitations or []),
    }

