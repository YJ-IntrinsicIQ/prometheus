from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


ALLOWED_ACTION_TYPES = {
    "dividend",
    "final_dividend",
    "interim_dividend",
    "bonus_issue",
    "stock_split",
    "buyback",
    "rights_issue",
    "qip",
    "preferential_issue",
    "warrants",
    "esop_dilution",
    "merger",
    "demerger",
    "face_value_change",
    "share_capital_change",
    "weighted_avg_shares",
    "diluted_shares",
}

ALLOWED_SHARE_COUNT_IMPACT = {"increase", "decrease", "none", "unknown"}
ALLOWED_EPS_COMPARABILITY = {"yes", "no", "unknown"}
ALLOWED_CORPORATE_ACTION_CONFIDENCE = {"high", "medium", "low", "missing"}
ALLOWED_CORPORATE_ACTION_STATUS = {"pass", "warning", "fail"}


@dataclass
class CorporateActionItem:
    action_type: str
    year: str
    announcement_date: Optional[str] = None
    effective_date: Optional[str] = None
    action_subtype: str = ""
    ratio: str = ""
    amount_crore: Optional[float] = None
    amount_raised_crore: Optional[float] = None
    amount_utilised_crore: Optional[float] = None
    per_share_amount: Optional[float] = None
    issue_price: Optional[float] = None
    face_value: Optional[float] = None
    face_value_before: Optional[float] = None
    face_value_after: Optional[float] = None
    shares_issued: Optional[float] = None
    shares_before: Optional[float] = None
    shares_after: Optional[float] = None
    source_column_context: str = ""
    value_type_used: str = ""
    rejection_reason: str = ""
    impact_on_share_count: str = "unknown"
    impact_on_eps_comparability: str = "unknown"
    source_line_item: str = ""
    source_page: Optional[int] = None
    source_artifact: str = ""
    confidence: str = "missing"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "year": self.year,
            "announcement_date": self.announcement_date,
            "effective_date": self.effective_date,
            "action_subtype": self.action_subtype,
            "ratio": self.ratio,
            "amount_crore": self.amount_crore,
            "amount_raised_crore": self.amount_raised_crore,
            "amount_utilised_crore": self.amount_utilised_crore,
            "per_share_amount": self.per_share_amount,
            "issue_price": self.issue_price,
            "face_value": self.face_value,
            "face_value_before": self.face_value_before,
            "face_value_after": self.face_value_after,
            "shares_issued": self.shares_issued,
            "shares_before": self.shares_before,
            "shares_after": self.shares_after,
            "source_column_context": self.source_column_context,
            "value_type_used": self.value_type_used,
            "rejection_reason": self.rejection_reason,
            "impact_on_share_count": self.impact_on_share_count,
            "impact_on_eps_comparability": self.impact_on_eps_comparability,
            "source_line_item": self.source_line_item,
            "source_page": self.source_page,
            "source_artifact": self.source_artifact,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }


@dataclass
class ShareCountSummary:
    opening_shares: Optional[float] = None
    closing_shares: Optional[float] = None
    weighted_avg_shares: Optional[float] = None
    diluted_shares: Optional[float] = None
    face_value: Optional[float] = None
    share_count_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opening_shares": self.opening_shares,
            "closing_shares": self.closing_shares,
            "weighted_avg_shares": self.weighted_avg_shares,
            "diluted_shares": self.diluted_shares,
            "face_value": self.face_value,
            "share_count_events": list(self.share_count_events),
        }


@dataclass
class CorporateActionsReport:
    company: str
    year: str
    generated_at: str
    status: str
    actions: List[CorporateActionItem] = field(default_factory=list)
    share_count_summary: ShareCountSummary = field(default_factory=ShareCountSummary)
    rejection_reasons: List[str] = field(default_factory=list)
    per_share_comparability_warnings: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "status": self.status,
            "actions": [item.to_dict() for item in self.actions],
            "share_count_summary": self.share_count_summary.to_dict(),
            "rejection_reasons": list(self.rejection_reasons),
            "per_share_comparability_warnings": list(self.per_share_comparability_warnings),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


def validate_corporate_actions_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["corporate actions payload must be an object"]
    for key in ("company", "year", "generated_at", "status", "actions", "share_count_summary", "rejection_reasons"):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")

    status = payload.get("status")
    if status is not None and status not in ALLOWED_CORPORATE_ACTION_STATUS:
        errors.append(f"invalid status: {status}")

    actions = payload.get("actions")
    if actions is not None and not isinstance(actions, list):
        errors.append("actions must be a list")
        actions = []
    for index, item in enumerate(actions or []):
        if not isinstance(item, dict):
            errors.append(f"actions[{index}] must be an object")
            continue
        for key in (
            "action_type",
            "year",
            "ratio",
            "impact_on_share_count",
            "impact_on_eps_comparability",
            "source_line_item",
            "source_artifact",
            "confidence",
            "warnings",
        ):
            if key not in item:
                errors.append(f"actions[{index}] missing required field: {key}")
        if item.get("action_type") not in ALLOWED_ACTION_TYPES:
            errors.append(f"actions[{index}].action_type invalid: {item.get('action_type')}")
        if item.get("impact_on_share_count") not in ALLOWED_SHARE_COUNT_IMPACT:
            errors.append(
                f"actions[{index}].impact_on_share_count invalid: {item.get('impact_on_share_count')}"
            )
        if item.get("impact_on_eps_comparability") not in ALLOWED_EPS_COMPARABILITY:
            errors.append(
                f"actions[{index}].impact_on_eps_comparability invalid: {item.get('impact_on_eps_comparability')}"
            )
        if item.get("confidence") not in ALLOWED_CORPORATE_ACTION_CONFIDENCE:
            errors.append(f"actions[{index}].confidence invalid: {item.get('confidence')}")
        if "warnings" in item and not isinstance(item.get("warnings"), list):
            errors.append(f"actions[{index}].warnings must be a list")
        for optional_numeric in (
            "amount_crore",
            "amount_raised_crore",
            "amount_utilised_crore",
            "per_share_amount",
            "issue_price",
            "face_value",
            "face_value_before",
            "face_value_after",
            "shares_issued",
            "shares_before",
            "shares_after",
        ):
            if optional_numeric in item and item.get(optional_numeric) is not None and not isinstance(
                item.get(optional_numeric), (int, float)
            ):
                errors.append(f"actions[{index}].{optional_numeric} must be numeric or null")

    summary = payload.get("share_count_summary")
    if summary is not None:
        if not isinstance(summary, dict):
            errors.append("share_count_summary must be an object")
        else:
            for key in (
                "opening_shares",
                "closing_shares",
                "weighted_avg_shares",
                "diluted_shares",
                "face_value",
                "share_count_events",
            ):
                if key not in summary:
                    errors.append(f"share_count_summary missing required field: {key}")
            if "share_count_events" in summary and not isinstance(summary.get("share_count_events"), list):
                errors.append("share_count_summary.share_count_events must be a list")

    for key in ("rejection_reasons", "per_share_comparability_warnings", "warnings", "limitations"):
        if key in payload and not isinstance(payload.get(key), list):
            errors.append(f"{key} must be a list")

    return errors
