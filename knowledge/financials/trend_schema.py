from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


ALLOWED_TREND_BASIS = {"standalone", "consolidated", "mixed", "unknown"}
ALLOWED_TREND_CONFIDENCE = {"high", "medium", "low", "missing"}


@dataclass
class TrendPoint:
    year: str
    value: Optional[float]
    basis: str
    source_artifact: str
    confidence: str
    metric_name: str = ""
    availability_status: str = "missing"
    source_statement: str = ""
    derived: bool = False
    formula: str = ""
    usable_downstream: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "year": self.year,
            "value": self.value,
            "basis": self.basis,
            "source_artifact": self.source_artifact,
            "confidence": self.confidence,
            "metric_name": self.metric_name,
            "availability_status": self.availability_status,
            "source_statement": self.source_statement,
            "derived": self.derived,
            "formula": self.formula,
            "usable_downstream": self.usable_downstream,
            "warnings": list(self.warnings),
        }


@dataclass
class TrendSeries:
    metric: str
    unit: str
    series: List[TrendPoint] = field(default_factory=list)
    comparability_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "unit": self.unit,
            "series": [point.to_dict() for point in self.series],
            "comparability_warnings": list(self.comparability_warnings),
        }


@dataclass
class GrowthSummaryPoint:
    year: str
    growth_percent: Optional[float]
    cagr_percent: Optional[float]
    absolute_change: Optional[float]
    basis: str
    source_artifact: str
    confidence: str
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "year": self.year,
            "growth_percent": self.growth_percent,
            "cagr_percent": self.cagr_percent,
            "absolute_change": self.absolute_change,
            "basis": self.basis,
            "source_artifact": self.source_artifact,
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }


@dataclass
class FinancialTrendReport:
    company: str
    generated_at: str
    years_covered: List[str]
    basis: str
    basis_policy: Dict[str, Any] = field(default_factory=dict)
    trend_groups: Dict[str, Dict[str, TrendSeries]] = field(default_factory=dict)
    metric_trends: Dict[str, TrendSeries] = field(default_factory=dict)
    metric_series: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    ratio_series: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    growth_summary: Dict[str, List[GrowthSummaryPoint]] = field(default_factory=dict)
    margin_trends: Dict[str, TrendSeries] = field(default_factory=dict)
    return_trends: Dict[str, TrendSeries] = field(default_factory=dict)
    cash_conversion_trends: Dict[str, TrendSeries] = field(default_factory=dict)
    balance_sheet_trends: Dict[str, TrendSeries] = field(default_factory=dict)
    per_share_trends: Dict[str, TrendSeries] = field(default_factory=dict)
    ownership_trends: Dict[str, TrendSeries] = field(default_factory=dict)
    corporate_actions_timeline: List[Dict[str, Any]] = field(default_factory=list)
    unreliable_metrics: List[Dict[str, Any]] = field(default_factory=list)
    invalid_or_quarantined_metrics: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "generated_at": self.generated_at,
            "years_covered": list(self.years_covered),
            "basis": self.basis,
            "basis_policy": dict(self.basis_policy),
            "trend_groups": {
                group: {key: value.to_dict() for key, value in metrics.items()}
                for group, metrics in self.trend_groups.items()
            },
            "metric_trends": {key: value.to_dict() for key, value in self.metric_trends.items()},
            "metric_series": {
                key: list(value)
                for key, value in self.metric_series.items()
            },
            "ratio_series": {
                key: list(value)
                for key, value in self.ratio_series.items()
            },
            "growth_summary": {
                key: [point.to_dict() for point in value]
                for key, value in self.growth_summary.items()
            },
            "margin_trends": {key: value.to_dict() for key, value in self.margin_trends.items()},
            "return_trends": {key: value.to_dict() for key, value in self.return_trends.items()},
            "cash_conversion_trends": {
                key: value.to_dict() for key, value in self.cash_conversion_trends.items()
            },
            "balance_sheet_trends": {
                key: value.to_dict() for key, value in self.balance_sheet_trends.items()
            },
            "per_share_trends": {key: value.to_dict() for key, value in self.per_share_trends.items()},
            "ownership_trends": {key: value.to_dict() for key, value in self.ownership_trends.items()},
            "corporate_actions_timeline": list(self.corporate_actions_timeline),
            "unreliable_metrics": list(self.unreliable_metrics),
            "invalid_or_quarantined_metrics": list(self.invalid_or_quarantined_metrics),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


def _validate_series_container(name: str, payload: Any, errors: List[str]) -> None:
    if not isinstance(payload, dict):
        errors.append(f"{name} must be an object")
        return
    for metric, item in payload.items():
        if not isinstance(item, dict):
            errors.append(f"{name}.{metric} must be an object")
            continue
        for key in ("metric", "unit", "series", "comparability_warnings"):
            if key not in item:
                errors.append(f"{name}.{metric} missing required field: {key}")
        if "series" in item and not isinstance(item.get("series"), list):
            errors.append(f"{name}.{metric}.series must be a list")
            continue
        for index, point in enumerate(item.get("series", [])):
            if not isinstance(point, dict):
                errors.append(f"{name}.{metric}.series[{index}] must be an object")
                continue
            for point_key in (
                "year",
                "value",
                "basis",
                "source_artifact",
                "confidence",
                "metric_name",
                "availability_status",
                "source_statement",
                "derived",
                "formula",
                "usable_downstream",
                "warnings",
            ):
                if point_key not in point:
                    errors.append(f"{name}.{metric}.series[{index}] missing required field: {point_key}")
            if point.get("basis") not in ALLOWED_TREND_BASIS:
                errors.append(f"{name}.{metric}.series[{index}].basis invalid: {point.get('basis')}")
            if point.get("confidence") not in ALLOWED_TREND_CONFIDENCE:
                errors.append(f"{name}.{metric}.series[{index}].confidence invalid: {point.get('confidence')}")
            if "derived" in point and not isinstance(point.get("derived"), bool):
                errors.append(f"{name}.{metric}.series[{index}].derived must be boolean")
            if "usable_downstream" in point and not isinstance(point.get("usable_downstream"), bool):
                errors.append(f"{name}.{metric}.series[{index}].usable_downstream must be boolean")
            if "warnings" in point and not isinstance(point.get("warnings"), list):
                errors.append(f"{name}.{metric}.series[{index}].warnings must be a list")
        if "comparability_warnings" in item and not isinstance(item.get("comparability_warnings"), list):
            errors.append(f"{name}.{metric}.comparability_warnings must be a list")


def validate_financial_trend_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial trend payload must be an object"]
    for key in (
        "company",
        "generated_at",
        "years_covered",
        "basis",
        "basis_policy",
        "trend_groups",
        "metric_trends",
        "metric_series",
        "ratio_series",
        "growth_summary",
        "margin_trends",
        "return_trends",
        "cash_conversion_trends",
        "balance_sheet_trends",
        "per_share_trends",
        "ownership_trends",
        "corporate_actions_timeline",
        "unreliable_metrics",
        "invalid_or_quarantined_metrics",
        "warnings",
        "limitations",
    ):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    if payload.get("basis") is not None and payload.get("basis") not in ALLOWED_TREND_BASIS:
        errors.append(f"basis must be one of {sorted(ALLOWED_TREND_BASIS)}")
    for key in ("years_covered", "corporate_actions_timeline", "warnings", "limitations"):
        if key in payload and not isinstance(payload.get(key), list):
            errors.append(f"{key} must be a list")
    if "basis_policy" in payload and not isinstance(payload.get("basis_policy"), dict):
        errors.append("basis_policy must be an object")
    if "trend_groups" in payload:
        if not isinstance(payload.get("trend_groups"), dict):
            errors.append("trend_groups must be an object")
        else:
            for group_name, metrics in payload.get("trend_groups", {}).items():
                _validate_series_container(f"trend_groups.{group_name}", metrics, errors)
    if "metric_series" in payload and not isinstance(payload.get("metric_series"), dict):
        errors.append("metric_series must be an object")
    if "ratio_series" in payload and not isinstance(payload.get("ratio_series"), dict):
        errors.append("ratio_series must be an object")

    for name in (
        "metric_trends",
        "margin_trends",
        "return_trends",
        "cash_conversion_trends",
        "balance_sheet_trends",
        "per_share_trends",
        "ownership_trends",
    ):
        if name in payload:
            _validate_series_container(name, payload.get(name), errors)

    for field in ("unreliable_metrics", "invalid_or_quarantined_metrics"):
        if field in payload and not isinstance(payload.get(field), list):
            errors.append(f"{field} must be a list")

    growth_summary = payload.get("growth_summary")
    if growth_summary is not None:
        if not isinstance(growth_summary, dict):
            errors.append("growth_summary must be an object")
        else:
            for metric, items in growth_summary.items():
                if not isinstance(items, list):
                    errors.append(f"growth_summary.{metric} must be a list")
                    continue
                for index, point in enumerate(items):
                    if not isinstance(point, dict):
                        errors.append(f"growth_summary.{metric}[{index}] must be an object")
                        continue
                    for point_key in (
                        "year",
                        "growth_percent",
                        "cagr_percent",
                        "absolute_change",
                        "basis",
                        "source_artifact",
                        "confidence",
                        "warnings",
                    ):
                        if point_key not in point:
                            errors.append(f"growth_summary.{metric}[{index}] missing required field: {point_key}")
                    if point.get("basis") not in ALLOWED_TREND_BASIS:
                        errors.append(f"growth_summary.{metric}[{index}].basis invalid: {point.get('basis')}")
                    if point.get("confidence") not in ALLOWED_TREND_CONFIDENCE:
                        errors.append(
                            f"growth_summary.{metric}[{index}].confidence invalid: {point.get('confidence')}"
                        )
                    if "warnings" in point and not isinstance(point.get("warnings"), list):
                        errors.append(f"growth_summary.{metric}[{index}].warnings must be a list")

    return errors
