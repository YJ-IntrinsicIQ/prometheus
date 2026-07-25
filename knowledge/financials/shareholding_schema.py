from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


ALLOWED_SHAREHOLDING_STATUS = {"pass", "warning", "fail"}
ALLOWED_SHAREHOLDING_CONFIDENCE = {"high", "medium", "low", "missing"}

SHAREHOLDING_CATEGORIES = [
    "promoter_holding_percent",
    "pledged_promoter_holding_percent",
    "fii_holding_percent",
    "dii_holding_percent",
    "mutual_fund_holding_percent",
    "insurance_holding_percent",
    "public_holding_percent",
    "body_corporates_percent",
    "retail_holding_percent",
    "others_percent",
    "institutional_holding_percent",
    "non_institutional_holding_percent",
    "total_shareholders",
]


@dataclass
class ShareholdingItem:
    holder_category: str
    period: str
    holding_percent: Optional[float] = None
    shares_held: Optional[float] = None
    change_percent: Optional[float] = None
    source_line_item: str = ""
    source_page: Optional[int] = None
    source_artifact: str = ""
    confidence: str = "missing"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "holder_category": self.holder_category,
            "period": self.period,
            "holding_percent": self.holding_percent,
            "shares_held": self.shares_held,
            "change_percent": self.change_percent,
            "source_line_item": self.source_line_item,
            "source_page": self.source_page,
            "source_artifact": self.source_artifact,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }


@dataclass
class OwnershipSummary:
    promoter_control: str = ""
    institutional_interest: str = ""
    pledge_risk: str = ""
    public_float: str = ""
    notable_changes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "promoter_control": self.promoter_control,
            "institutional_interest": self.institutional_interest,
            "pledge_risk": self.pledge_risk,
            "public_float": self.public_float,
            "notable_changes": list(self.notable_changes),
        }


@dataclass
class ShareholdingReport:
    company: str
    year: str
    generated_at: str
    status: str
    items: List[ShareholdingItem] = field(default_factory=list)
    ownership_summary: OwnershipSummary = field(default_factory=OwnershipSummary)
    searched_sections: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "ownership_summary": self.ownership_summary.to_dict(),
            "searched_sections": list(self.searched_sections),
            "rejection_reasons": list(self.rejection_reasons),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


def validate_shareholding_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["shareholding payload must be an object"]

    for key in ("company", "year", "generated_at", "status", "items", "ownership_summary", "searched_sections", "rejection_reasons"):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")

    status = payload.get("status")
    if status is not None and status not in ALLOWED_SHAREHOLDING_STATUS:
        errors.append(f"invalid status: {status}")

    items = payload.get("items")
    if items is not None and not isinstance(items, list):
        errors.append("items must be a list")
        items = []
    for index, item in enumerate(items or []):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be an object")
            continue
        for key in (
            "holder_category",
            "period",
            "source_line_item",
            "source_artifact",
            "confidence",
            "warnings",
        ):
            if key not in item:
                errors.append(f"items[{index}] missing required field: {key}")
        holder_category = item.get("holder_category")
        if holder_category not in SHAREHOLDING_CATEGORIES:
            errors.append(f"items[{index}].holder_category invalid: {holder_category}")
        if item.get("confidence") not in ALLOWED_SHAREHOLDING_CONFIDENCE:
            errors.append(f"items[{index}].confidence invalid: {item.get('confidence')}")
        if "warnings" in item and not isinstance(item.get("warnings"), list):
            errors.append(f"items[{index}].warnings must be a list")

    ownership_summary = payload.get("ownership_summary")
    if ownership_summary is not None:
        if not isinstance(ownership_summary, dict):
            errors.append("ownership_summary must be an object")
        else:
            for key in (
                "promoter_control",
                "institutional_interest",
                "pledge_risk",
                "public_float",
                "notable_changes",
            ):
                if key not in ownership_summary:
                    errors.append(f"ownership_summary missing required field: {key}")
            if "notable_changes" in ownership_summary and not isinstance(
                ownership_summary.get("notable_changes"), list
            ):
                errors.append("ownership_summary.notable_changes must be a list")

    for key in ("searched_sections", "rejection_reasons", "warnings", "limitations"):
        if key in payload and not isinstance(payload.get(key), list):
            errors.append(f"{key} must be a list")

    return errors
