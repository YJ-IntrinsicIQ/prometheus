from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


ALLOWED_ATTRIBUTION_STATUS = {"pass", "warning", "fail"}
ALLOWED_ATTRIBUTION_MOVEMENT = {"improved", "declined", "spiked", "compressed", "unknown"}
ALLOWED_ATTRIBUTION_DRIVER_TYPES = {
    "capex",
    "working_capital",
    "debt",
    "equity_raise",
    "corporate_action",
    "margin",
    "order_execution",
    "customer_concentration",
    "risk",
    "unknown",
}
ALLOWED_ATTRIBUTION_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_CAUSALITY_STATUS = {"supported", "possible", "weak", "unknown"}


@dataclass
class FinancialDriverAttributionItem:
    metric: str
    movement: str
    period: str
    observed_change: str
    possible_driver: str
    driver_type: str
    supporting_event: str
    confidence: str
    causality_status: str
    evidence_ids: List[str] = field(default_factory=list)
    source_artifacts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    verification_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "movement": self.movement,
            "period": self.period,
            "observed_change": self.observed_change,
            "possible_driver": self.possible_driver,
            "driver_type": self.driver_type,
            "supporting_event": self.supporting_event,
            "confidence": self.confidence,
            "causality_status": self.causality_status,
            "evidence_ids": list(self.evidence_ids),
            "source_artifacts": list(self.source_artifacts),
            "warnings": list(self.warnings),
            "verification_questions": list(self.verification_questions),
        }


@dataclass
class FinancialDriverAttributionReport:
    company: str
    generated_at: str
    years_covered: List[str]
    status: str
    attribution_readiness: Dict[str, Any] = field(default_factory=dict)
    attributions: List[FinancialDriverAttributionItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "generated_at": self.generated_at,
            "years_covered": list(self.years_covered),
            "status": self.status,
            "attribution_readiness": dict(self.attribution_readiness),
            "attributions": [item.to_dict() for item in self.attributions],
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


def validate_financial_driver_attribution_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial driver attribution payload must be an object"]

    for key in ("company", "generated_at", "years_covered", "status", "attribution_readiness", "attributions", "warnings", "limitations"):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")

    if payload.get("status") is not None and payload.get("status") not in ALLOWED_ATTRIBUTION_STATUS:
        errors.append(f"invalid status: {payload.get('status')}")

    for list_key in ("years_covered", "attributions", "warnings", "limitations"):
        if list_key in payload and not isinstance(payload.get(list_key), list):
            errors.append(f"{list_key} must be a list")
    if "attribution_readiness" in payload and not isinstance(payload.get("attribution_readiness"), dict):
        errors.append("attribution_readiness must be an object")

    for index, item in enumerate(payload.get("attributions", [])):
        if not isinstance(item, dict):
            errors.append(f"attributions[{index}] must be an object")
            continue
        for key in (
            "metric",
            "movement",
            "period",
            "observed_change",
            "possible_driver",
            "driver_type",
            "supporting_event",
            "confidence",
            "causality_status",
            "evidence_ids",
            "source_artifacts",
            "warnings",
            "verification_questions",
        ):
            if key not in item:
                errors.append(f"attributions[{index}] missing required field: {key}")
        if item.get("movement") not in ALLOWED_ATTRIBUTION_MOVEMENT:
            errors.append(f"attributions[{index}].movement invalid: {item.get('movement')}")
        if item.get("driver_type") not in ALLOWED_ATTRIBUTION_DRIVER_TYPES:
            errors.append(f"attributions[{index}].driver_type invalid: {item.get('driver_type')}")
        if item.get("confidence") not in ALLOWED_ATTRIBUTION_CONFIDENCE:
            errors.append(f"attributions[{index}].confidence invalid: {item.get('confidence')}")
        if item.get("causality_status") not in ALLOWED_CAUSALITY_STATUS:
            errors.append(f"attributions[{index}].causality_status invalid: {item.get('causality_status')}")
        for list_key in ("evidence_ids", "source_artifacts", "warnings", "verification_questions"):
            if list_key in item and not isinstance(item.get(list_key), list):
                errors.append(f"attributions[{index}].{list_key} must be a list")

    return errors
