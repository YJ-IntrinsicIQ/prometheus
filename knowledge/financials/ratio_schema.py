from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


ALLOWED_RATIO_STATUS = {"pass", "warning", "fail"}
ALLOWED_RATIO_CONFIDENCE = {"high", "medium", "low", "missing"}
ALLOWED_RATIO_BASIS = {"standalone", "consolidated", "unknown", "mixed"}


RATIO_FIELDS = (
    "gross_margin",
    "ebitda_margin",
    "ebit_margin",
    "opm",
    "npm",
    "roe",
    "roce",
    "roa",
    "debt_to_equity",
    "net_debt",
    "net_debt_to_equity",
    "interest_coverage",
    "cfo_to_pat",
    "fcf",
    "fcf_to_pat",
    "fcf_margin",
    "receivable_days",
    "inventory_days",
    "payable_days",
    "cash_conversion_cycle",
    "eps_basic",
    "eps_diluted",
    "book_value_per_share",
    "tangible_book_value_per_share",
    "dividend_per_share",
    "payout_ratio",
)


@dataclass
class RatioItem:
    ratio_name: str
    value: Optional[float]
    unit: str
    formula: str
    inputs_used: List[Dict[str, Any]] = field(default_factory=list)
    basis: str = "unknown"
    confidence: str = "missing"
    warnings: List[str] = field(default_factory=list)
    source_artifacts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ratio_name": self.ratio_name,
            "value": self.value,
            "unit": self.unit,
            "formula": self.formula,
            "inputs_used": list(self.inputs_used),
            "basis": self.basis,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "source_artifacts": list(self.source_artifacts),
        }


@dataclass
class FinancialRatioReport:
    company: str
    year: str
    generated_at: str
    status: str
    basis_used: str
    basis_confidence: str = "low"
    basis_warnings: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ratios: Dict[str, RatioItem] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "status": self.status,
            "basis_used": self.basis_used,
            "basis_confidence": self.basis_confidence,
            "basis_warnings": list(self.basis_warnings),
            "warnings": list(self.warnings),
            "ratios": {name: item.to_dict() for name, item in self.ratios.items()},
            "limitations": list(self.limitations),
        }


def validate_financial_ratio_report_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial ratio report must be an object"]
    for key in ("company", "year", "generated_at"):
        if not payload.get(key):
            errors.append(f"{key} is required")
    if payload.get("status") not in ALLOWED_RATIO_STATUS:
        errors.append("status must be pass|warning|fail")
    if payload.get("basis_used") not in ALLOWED_RATIO_BASIS:
        errors.append("basis_used must be standalone|consolidated|unknown|mixed")
    basis_confidence = payload.get("basis_confidence")
    if basis_confidence is not None and basis_confidence not in ALLOWED_RATIO_CONFIDENCE:
        errors.append("basis_confidence must be high|medium|low|missing")
    if "basis_warnings" in payload and not isinstance(payload.get("basis_warnings"), list):
        errors.append("basis_warnings must be a list")
    if not isinstance(payload.get("warnings"), list):
        errors.append("warnings must be a list")
    ratios = payload.get("ratios")
    if not isinstance(ratios, dict):
        errors.append("ratios must be an object")
        return errors
    for field in RATIO_FIELDS:
        item = ratios.get(field)
        if not isinstance(item, dict):
            errors.append(f"ratios.{field} must be an object")
            continue
        if item.get("ratio_name") != field:
            errors.append(f"ratios.{field}.ratio_name must equal {field}")
        if item.get("basis") not in ALLOWED_RATIO_BASIS:
            errors.append(f"ratios.{field}.basis must be standalone|consolidated|unknown|mixed")
        if item.get("confidence") not in ALLOWED_RATIO_CONFIDENCE:
            errors.append(f"ratios.{field}.confidence must be high|medium|low|missing")
        if not isinstance(item.get("inputs_used"), list):
            errors.append(f"ratios.{field}.inputs_used must be a list")
        if not isinstance(item.get("warnings"), list):
            errors.append(f"ratios.{field}.warnings must be a list")
        if not isinstance(item.get("source_artifacts"), list):
            errors.append(f"ratios.{field}.source_artifacts must be a list")
    return errors
