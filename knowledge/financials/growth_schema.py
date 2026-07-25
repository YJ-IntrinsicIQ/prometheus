from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


ALLOWED_GROWTH_STATUS = {"pass", "warning", "fail"}
ALLOWED_GROWTH_BASIS = {"standalone", "consolidated", "unknown", "mixed"}
ALLOWED_GROWTH_CONFIDENCE = {"high", "medium", "low", "missing"}

GROWTH_METRIC_FIELDS = (
    "revenue",
    "ebitda",
    "ebit",
    "pat",
    "eps_basic",
    "eps_diluted",
    "book_value_per_share",
    "net_worth",
    "reserves",
    "total_debt",
    "cfo",
    "fcf",
    "capex",
    "receivables",
    "inventory",
    "payables",
)

MARGIN_TREND_FIELDS = (
    "gross_margin",
    "ebitda_margin",
    "ebit_margin",
    "opm",
    "npm",
)


@dataclass
class GrowthItem:
    metric: str
    current_year: str
    previous_year: str
    current_value: float | None
    previous_value: float | None
    absolute_change: float | None
    growth_percent: float | None
    cagr_percent: float | None
    unit: str
    basis: str
    confidence: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "current_year": self.current_year,
            "previous_year": self.previous_year,
            "current_value": self.current_value,
            "previous_value": self.previous_value,
            "absolute_change": self.absolute_change,
            "growth_percent": self.growth_percent,
            "cagr_percent": self.cagr_percent,
            "unit": self.unit,
            "basis": self.basis,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }


@dataclass
class FinancialGrowthReport:
    company: str
    year: str
    generated_at: str
    status: str
    basis_used: str
    basis_confidence: str = "low"
    years_available: list[str] = field(default_factory=list)
    growth_metrics: Dict[str, GrowthItem] = field(default_factory=dict)
    margin_changes: Dict[str, GrowthItem] = field(default_factory=dict)
    basis_warnings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "generated_at": self.generated_at,
            "status": self.status,
            "basis_used": self.basis_used,
            "basis_confidence": self.basis_confidence,
            "years_available": list(self.years_available),
            "growth_metrics": {
                key: value.to_dict() if isinstance(value, GrowthItem) else value
                for key, value in self.growth_metrics.items()
            },
            "margin_changes": {
                key: value.to_dict() if isinstance(value, GrowthItem) else value
                for key, value in self.margin_changes.items()
            },
            "basis_warnings": list(self.basis_warnings),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


def validate_financial_growth_payload(payload: Dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("company", "year", "generated_at", "status", "basis_used"):
        if field not in payload:
            errors.append(f"missing required top-level field: {field}")

    status = payload.get("status")
    if status is not None and status not in ALLOWED_GROWTH_STATUS:
        errors.append(f"invalid growth status: {status}")

    basis = payload.get("basis_used")
    if basis is not None and basis not in ALLOWED_GROWTH_BASIS:
        errors.append(f"invalid growth basis: {basis}")
    basis_confidence = payload.get("basis_confidence")
    if basis_confidence is not None and basis_confidence not in ALLOWED_GROWTH_CONFIDENCE:
        errors.append(f"invalid growth basis confidence: {basis_confidence}")

    for container_name, allowed_keys in (
        ("growth_metrics", set(GROWTH_METRIC_FIELDS)),
        ("margin_changes", set(MARGIN_TREND_FIELDS)),
    ):
        container = payload.get(container_name)
        if container is None:
            errors.append(f"missing required top-level field: {container_name}")
            continue
        if not isinstance(container, dict):
            errors.append(f"{container_name} must be an object")
            continue
        for key, item in container.items():
            if key not in allowed_keys:
                errors.append(f"unexpected {container_name} key: {key}")
                continue
            if not isinstance(item, dict):
                errors.append(f"{container_name}.{key} must be an object")
                continue
            for required in (
                "metric",
                "current_year",
                "previous_year",
                "current_value",
                "previous_value",
                "absolute_change",
                "growth_percent",
                "cagr_percent",
                "unit",
                "basis",
                "confidence",
                "warnings",
            ):
                if required not in item:
                    errors.append(f"{container_name}.{key} missing required field: {required}")
            item_basis = item.get("basis")
            if item_basis is not None and item_basis not in ALLOWED_GROWTH_BASIS:
                errors.append(f"{container_name}.{key} has invalid basis: {item_basis}")
            item_confidence = item.get("confidence")
            if item_confidence is not None and item_confidence not in ALLOWED_GROWTH_CONFIDENCE:
                errors.append(f"{container_name}.{key} has invalid confidence: {item_confidence}")
            if "warnings" in item and not isinstance(item.get("warnings"), list):
                errors.append(f"{container_name}.{key}.warnings must be a list")

    for field in ("years_available", "warnings", "limitations", "basis_warnings"):
        if field in payload and not isinstance(payload[field], list):
            errors.append(f"{field} must be a list")

    return errors
