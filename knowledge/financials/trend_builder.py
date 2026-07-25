from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .trend_schema import (
    FinancialTrendReport,
    GrowthSummaryPoint,
    TrendPoint,
    TrendSeries,
    validate_financial_trend_payload,
)


_SCALE_METRICS = {
    "revenue": ("normalized", "profit_and_loss", "revenue", "₹ crore", "value_crore"),
    "ebitda": ("normalized", "profit_and_loss", "ebitda", "₹ crore", "value_crore"),
    "ebit": ("normalized", "profit_and_loss", "ebit", "₹ crore", "value_crore"),
    "pat": ("normalized", "profit_and_loss", "pat", "₹ crore", "value_crore"),
    "total_assets": ("normalized", "balance_sheet", "total_assets", "₹ crore", "value_crore"),
    "net_worth": ("normalized", "balance_sheet", "net_worth", "₹ crore", "value_crore"),
    "book_value_per_share": ("ratio", "book_value_per_share", "", "per share", "value"),
}

_MARGIN_METRICS = {
    "opm": ("ratio", "opm", "", "%", "value"),
    "ebitda_margin": ("ratio", "ebitda_margin", "", "%", "value"),
    "npm": ("ratio", "npm", "", "%", "value"),
}

_RETURN_METRICS = {
    "roe": ("ratio", "roe", "", "%", "value"),
    "roce": ("ratio", "roce", "", "%", "value"),
    "roa": ("ratio", "roa", "", "%", "value"),
}

_BALANCE_METRICS = {
    "total_debt": ("normalized", "balance_sheet", "total_debt", "₹ crore", "value_crore"),
    "net_debt": ("ratio", "net_debt", "", "₹ crore", "value"),
    "debt_to_equity": ("ratio", "debt_to_equity", "", "%", "value"),
    "cash_and_equivalents": ("normalized", "balance_sheet", "cash_and_equivalents", "₹ crore", "value_crore"),
    "reserves": ("normalized", "balance_sheet", "reserves", "₹ crore", "value_crore"),
}

_CASH_CONVERSION_METRICS = {
    "cfo": ("normalized", "cash_flow", "cfo", "₹ crore", "value_crore"),
    "fcf": ("ratio", "fcf", "", "₹ crore", "value"),
    "cfo_to_pat": ("ratio", "cfo_to_pat", "", "%", "value"),
    "fcf_to_pat": ("ratio", "fcf_to_pat", "", "%", "value"),
    "capex": ("normalized", "cash_flow", "capex", "₹ crore", "value_crore"),
}

_WORKING_CAPITAL_METRICS = {
    "receivables": ("normalized", "balance_sheet", "receivables", "₹ crore", "value_crore"),
    "inventory": ("normalized", "balance_sheet", "inventories", "₹ crore", "value_crore"),
    "payables": ("normalized", "balance_sheet", "payables", "₹ crore", "value_crore"),
    "receivable_days": ("ratio", "receivable_days", "", "days", "value"),
    "inventory_days": ("ratio", "inventory_days", "", "days", "value"),
    "payable_days": ("ratio", "payable_days", "", "days", "value"),
    "cash_conversion_cycle": ("ratio", "cash_conversion_cycle", "", "days", "value"),
}

_PER_SHARE_METRICS = {
    "eps_basic": ("ratio", "eps_basic", "", "per share", "value"),
    "eps_diluted": ("ratio", "eps_diluted", "", "per share", "value"),
    "book_value_per_share": ("ratio", "book_value_per_share", "", "per share", "value"),
    "dividend_per_share": ("ratio", "dividend_per_share", "", "per share", "value"),
    "payout_ratio": ("ratio", "payout_ratio", "", "%", "value"),
    "share_count": ("normalized", "share_data", "shares_outstanding", "shares", "value_original"),
}

_OWNERSHIP_METRICS = {
    "promoter_holding": ("promoter_holding_percent", "%"),
    "pledged_promoter_holding": ("pledged_promoter_holding_percent", "%"),
    "fii_holding": ("fii_holding_percent", "%"),
    "dii_holding": ("dii_holding_percent", "%"),
    "mutual_fund_holding": ("mutual_fund_holding_percent", "%"),
    "public_holding": ("public_holding_percent", "%"),
}

_ACTION_ORDER = {
    "dividend": 1,
    "final_dividend": 2,
    "interim_dividend": 3,
    "bonus_issue": 4,
    "stock_split": 5,
    "qip": 6,
    "buyback": 7,
    "rights_issue": 8,
    "preferential_issue": 9,
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else None


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _parse_numeric(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return None
    negative = raw.startswith("(") or raw.startswith("[") or raw.startswith("-")
    raw = raw.strip("()[]")
    if raw.startswith("-"):
        raw = raw[1:]
    raw = raw.rstrip("%")
    try:
        numeric = float(raw)
    except ValueError:
        return None
    return -numeric if negative else numeric


def _parse_year_label(value: str) -> Optional[int]:
    raw = str(value or "").strip().lower()
    if raw.startswith("fy") and raw[2:].isdigit():
        digits = raw[2:]
        if len(digits) == 2:
            return 2000 + int(digits)
        if len(digits) == 4:
            return int(digits)
    return None


def _sort_years(labels: Iterable[str]) -> List[str]:
    return sorted(labels, key=lambda item: (_parse_year_label(item) is None, _parse_year_label(item) or 0, item))


def _entry(payload: Dict[str, Any], section: str, field: str) -> Dict[str, Any]:
    section_payload = payload.get(section, {})
    return section_payload.get(field, {}) if isinstance(section_payload, dict) else {}


def _basis_from_normalized(payload: Optional[Dict[str, Any]]) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    return str(payload.get("preferred_basis", "unknown") or "unknown")


def _basis_from_ratio(payload: Optional[Dict[str, Any]]) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    return str(payload.get("basis_used", "unknown") or "unknown")


def _basis_from_growth(payload: Optional[Dict[str, Any]]) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    return str(payload.get("basis_used", "unknown") or "unknown")


def _point_confidence(value: Optional[float], warnings: Sequence[str]) -> str:
    if value is None:
        return "missing"
    if any("missing" in warning.lower() or "unavailable" in warning.lower() for warning in warnings):
        return "low"
    if warnings:
        return "medium"
    return "high"


def _round(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 4)


def _extract_metric_from_normalized(
    payload: Optional[Dict[str, Any]],
    section: str,
    field: str,
    value_mode: str,
) -> Tuple[Optional[float], str, List[str]]:
    if not isinstance(payload, dict):
        return None, "unknown", ["normalized fundamentals missing"]
    entry = _entry(payload, section, field)
    warnings = [str(item) for item in entry.get("warnings", [])] if isinstance(entry.get("warnings"), list) else []
    basis = str(entry.get("basis", _basis_from_normalized(payload)) or _basis_from_normalized(payload))
    if value_mode == "value_crore":
        value = entry.get("value_crore")
        return (float(value) if isinstance(value, (int, float)) else None, basis, warnings)
    value = _parse_numeric(entry.get("value_original"))
    return value, basis, warnings


def _extract_metric_from_ratio(
    payload: Optional[Dict[str, Any]],
    ratio_name: str,
) -> Tuple[Optional[float], str, List[str]]:
    if not isinstance(payload, dict):
        return None, "unknown", ["financial ratios missing"]
    ratios = payload.get("ratios", {})
    item = ratios.get(ratio_name, {}) if isinstance(ratios, dict) else {}
    warnings = [str(item) for item in item.get("warnings", [])] if isinstance(item.get("warnings"), list) else []
    value = item.get("value")
    basis = str(item.get("basis", _basis_from_ratio(payload)) or _basis_from_ratio(payload))
    return (float(value) if isinstance(value, (int, float)) else None, basis, warnings)


def _extract_metric_series(
    years: Sequence[str],
    yearly_payloads: Dict[str, Dict[str, Optional[Dict[str, Any]]]],
    spec: Tuple[str, str, str, str, str],
) -> List[TrendPoint]:
    source_kind, field1, field2, _unit, value_mode = spec
    points: List[TrendPoint] = []
    for year in years:
        payloads = yearly_payloads[year]
        if source_kind == "normalized":
            value, basis, warnings = _extract_metric_from_normalized(payloads.get("normalized"), field1, field2, value_mode)
            artifact = "normalized_fundamentals.json"
        else:
            value, basis, warnings = _extract_metric_from_ratio(payloads.get("ratios"), field1)
            artifact = "financial_ratios.json"
        if value is None and source_kind == "ratio" and payloads.get("ratios") is None:
            continue
        if value is None and source_kind == "normalized" and payloads.get("normalized") is None:
            continue
        points.append(
            TrendPoint(
                year=year,
                value=_round(value),
                basis=basis,
                source_artifact=artifact,
                confidence=_point_confidence(value, warnings),
                warnings=warnings,
            )
        )
    return points


def _extract_ownership_series(
    years: Sequence[str],
    yearly_payloads: Dict[str, Dict[str, Optional[Dict[str, Any]]]],
    holder_category: str,
) -> List[TrendPoint]:
    points: List[TrendPoint] = []
    for year in years:
        payload = yearly_payloads[year].get("shareholding")
        if not isinstance(payload, dict):
            continue
        items = payload.get("items", [])
        if not isinstance(items, list):
            continue
        match = next((item for item in items if isinstance(item, dict) and item.get("holder_category") == holder_category), None)
        if match is None:
            continue
        warnings = [str(item) for item in match.get("warnings", [])] if isinstance(match.get("warnings"), list) else []
        points.append(
            TrendPoint(
                year=year,
                value=_round(_parse_numeric(match.get("holding_percent"))),
                basis="unknown",
                source_artifact="shareholding_pattern.json",
                confidence=str(match.get("confidence", "missing") or "missing"),
                warnings=warnings,
            )
        )
    return points


def _series_warnings(points: Sequence[TrendPoint]) -> List[str]:
    warnings: List[str] = []
    basis_values = {point.basis for point in points if point.basis and point.basis != "unknown"}
    if len(basis_values) > 1:
        _append_unique(warnings, "basis mismatch across years")
    return warnings


def _build_trend_container(
    metric_specs: Dict[str, Tuple[str, str, str, str, str]],
    years: Sequence[str],
    yearly_payloads: Dict[str, Dict[str, Optional[Dict[str, Any]]]],
) -> Dict[str, TrendSeries]:
    result: Dict[str, TrendSeries] = {}
    for metric, spec in metric_specs.items():
        unit = spec[3]
        points = _extract_metric_series(years, yearly_payloads, spec)
        result[metric] = TrendSeries(
            metric=metric,
            unit=unit,
            series=points,
            comparability_warnings=_series_warnings(points),
        )
    return result


def _build_ownership_container(
    years: Sequence[str],
    yearly_payloads: Dict[str, Dict[str, Optional[Dict[str, Any]]]],
) -> Dict[str, TrendSeries]:
    result: Dict[str, TrendSeries] = {}
    for metric, (holder_category, unit) in _OWNERSHIP_METRICS.items():
        points = _extract_ownership_series(years, yearly_payloads, holder_category)
        result[metric] = TrendSeries(
            metric=metric,
            unit=unit,
            series=points,
            comparability_warnings=[],
        )
    return result


def _build_growth_summary(
    years: Sequence[str],
    yearly_payloads: Dict[str, Dict[str, Optional[Dict[str, Any]]]],
) -> Dict[str, List[GrowthSummaryPoint]]:
    result: Dict[str, List[GrowthSummaryPoint]] = {}
    for year in years:
        payload = yearly_payloads[year].get("growth")
        if not isinstance(payload, dict):
            continue
        growth_metrics = payload.get("growth_metrics", {})
        if not isinstance(growth_metrics, dict):
            continue
        for metric, item in growth_metrics.items():
            if not isinstance(item, dict):
                continue
            result.setdefault(metric, []).append(
                GrowthSummaryPoint(
                    year=year,
                    growth_percent=_round(item.get("growth_percent") if isinstance(item.get("growth_percent"), (int, float)) else None),
                    cagr_percent=_round(item.get("cagr_percent") if isinstance(item.get("cagr_percent"), (int, float)) else None),
                    absolute_change=_round(item.get("absolute_change") if isinstance(item.get("absolute_change"), (int, float)) else None),
                    basis=str(item.get("basis", _basis_from_growth(payload)) or _basis_from_growth(payload)),
                    source_artifact="financial_growth.json",
                    confidence=str(item.get("confidence", "missing") or "missing"),
                    warnings=[str(w) for w in item.get("warnings", [])] if isinstance(item.get("warnings"), list) else [],
                )
            )
    for metric in result:
        result[metric] = sorted(result[metric], key=lambda point: (_parse_year_label(point.year) is None, _parse_year_label(point.year) or 0, point.year))
    return result


def _build_corporate_actions_timeline(
    years: Sequence[str],
    yearly_payloads: Dict[str, Dict[str, Optional[Dict[str, Any]]]],
) -> List[Dict[str, Any]]:
    timeline: List[Dict[str, Any]] = []
    for year in years:
        payload = yearly_payloads[year].get("corporate_actions")
        if not isinstance(payload, dict):
            continue
        actions = payload.get("actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            timeline.append(
                {
                    "year": year,
                    "action_type": action.get("action_type", ""),
                    "ratio": action.get("ratio", ""),
                    "amount_crore": action.get("amount_crore"),
                    "per_share_amount": action.get("per_share_amount"),
                    "impact_on_share_count": action.get("impact_on_share_count", "unknown"),
                    "impact_on_eps_comparability": action.get("impact_on_eps_comparability", "unknown"),
                    "source_line_item": action.get("source_line_item", ""),
                    "source_artifact": action.get("source_artifact", ""),
                    "confidence": action.get("confidence", "missing"),
                    "warnings": action.get("warnings", []),
                }
            )
    return sorted(
        timeline,
        key=lambda item: (
            _parse_year_label(item.get("year", "")) is None,
            _parse_year_label(item.get("year", "")) or 0,
            _ACTION_ORDER.get(str(item.get("action_type", "")), 99),
            str(item.get("action_type", "")),
        ),
    )


def _determine_basis(yearly_payloads: Dict[str, Dict[str, Optional[Dict[str, Any]]]], years: Sequence[str]) -> str:
    normalized_bases = {
        _basis_from_normalized(yearly_payloads[year].get("normalized"))
        for year in years
        if yearly_payloads[year].get("normalized") is not None
    }
    normalized_bases.discard("unknown")
    if not normalized_bases:
        return "unknown"
    if len(normalized_bases) == 1:
        return next(iter(normalized_bases))
    return "mixed"


def _collect_years(company_root: Path) -> List[str]:
    years: List[str] = []
    for child in company_root.iterdir() if company_root.exists() else []:
        if not child.is_dir() or not child.name.lower().startswith("fy"):
            continue
        financials_dir = child / "financials"
        if not (financials_dir / "normalized_fundamentals.json").exists():
            continue
        validation = _load_optional_json(financials_dir / "financial_validation_report.json") or {}
        reconciliation = _load_optional_json(financials_dir / "financial_reconciliation_report.json") or {}
        quality = _load_optional_json(financials_dir / "financial_quality_summary.json") or {}
        statuses = {
            str(validation.get("status") or "").strip().lower(),
            str(reconciliation.get("status") or "").strip().lower(),
            str(quality.get("status") or "").strip().lower(),
        }
        if "fail" in statuses:
            continue
        years.append(child.name)
    return _sort_years(years)


def _year_payloads(company_root: Path, years: Sequence[str]) -> Dict[str, Dict[str, Optional[Dict[str, Any]]]]:
    payloads: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {}
    for year in years:
        financials_dir = company_root / year / "financials"
        payloads[year] = {
            "normalized": _load_optional_json(financials_dir / "normalized_fundamentals.json"),
            "ratios": _load_optional_json(financials_dir / "financial_ratios.json"),
            "growth": _load_optional_json(financials_dir / "financial_growth.json"),
            "corporate_actions": _load_optional_json(financials_dir / "corporate_actions.json"),
            "shareholding": _load_optional_json(financials_dir / "shareholding_pattern.json"),
        }
    return payloads


def _alias_points(series: TrendSeries) -> List[Dict[str, Any]]:
    return [
        {
            "year": point.year,
            "value": point.value,
            "unit": series.unit,
            "basis": point.basis,
            "confidence": point.confidence,
            "source_artifacts": [point.source_artifact],
            "warnings": list(point.warnings),
        }
        for point in series.series
    ]


def _apply_comparability_warnings(
    per_share_trends: Dict[str, TrendSeries],
    timeline: Sequence[Dict[str, Any]],
    yearly_payloads: Dict[str, Dict[str, Optional[Dict[str, Any]]]],
    warnings: List[str],
) -> None:
    flagged_years = set()
    for year, payloads in yearly_payloads.items():
        corporate_actions = payloads.get("corporate_actions")
        if not isinstance(corporate_actions, dict):
            continue
        for warning in corporate_actions.get("per_share_comparability_warnings", []):
            if isinstance(warning, str):
                flagged_years.add((year, warning))
    for action in timeline:
        if action.get("impact_on_eps_comparability") == "yes":
            _append_unique(
                warnings,
                f"corporate actions affect per-share comparability in {action.get('year')}: {action.get('action_type')}",
            )
            for metric in ("eps_basic", "eps_diluted", "book_value_per_share", "dividend_per_share", "payout_ratio", "share_count"):
                _append_unique(
                    per_share_trends[metric].comparability_warnings,
                    f"{action.get('year')} {action.get('action_type')} may affect comparability",
                )
    for year, warning in flagged_years:
        _append_unique(warnings, f"{year}: {warning}")


def build_financial_trends(*, company: str, company_root: Path) -> FinancialTrendReport:
    years = _collect_years(company_root)
    if not years:
        raise RuntimeError(f"financial_trends requires at least one valid financial year for {company}")

    payloads = _year_payloads(company_root, years)
    metric_trends = _build_trend_container(_SCALE_METRICS, years, payloads)
    margin_trends = _build_trend_container(_MARGIN_METRICS, years, payloads)
    return_trends = _build_trend_container(_RETURN_METRICS, years, payloads)
    balance_sheet_trends = _build_trend_container(_BALANCE_METRICS, years, payloads)
    cash_conversion_trends = _build_trend_container(_CASH_CONVERSION_METRICS, years, payloads)
    working_capital_trends = _build_trend_container(_WORKING_CAPITAL_METRICS, years, payloads)
    per_share_trends = _build_trend_container(_PER_SHARE_METRICS, years, payloads)
    ownership_trends = _build_ownership_container(years, payloads)
    growth_summary = _build_growth_summary(years, payloads)
    corporate_actions_timeline = _build_corporate_actions_timeline(years, payloads)

    warnings: List[str] = []
    limitations: List[str] = []

    revenue_points = metric_trends["revenue"].series
    pat_points = metric_trends["pat"].series
    if not revenue_points and not pat_points:
        raise RuntimeError("financial_trends could not build revenue or PAT trend")

    if len(years) == 1:
        _append_unique(warnings, "only one financial year available")

    basis = _determine_basis(payloads, years)
    if basis == "mixed":
        _append_unique(warnings, "basis mismatch across years")

    if not cash_conversion_trends["cfo"].series:
        _append_unique(warnings, "missing CFO")
    if not cash_conversion_trends["fcf"].series:
        _append_unique(warnings, "missing FCF")

    if not return_trends["roe"].series or all(point.value is None for point in return_trends["roe"].series):
        _append_unique(warnings, "ROE unavailable")
    if not return_trends["roce"].series or all(point.value is None for point in return_trends["roce"].series):
        _append_unique(warnings, "ROCE unavailable")

    if all(not series.series for series in ownership_trends.values()):
        _append_unique(warnings, "shareholding data missing")

    for year in years:
        shareholding_payload = payloads[year].get("shareholding")
        if isinstance(shareholding_payload, dict):
            for warning in shareholding_payload.get("warnings", []):
                if isinstance(warning, str) and "shareholding" in warning.lower():
                    _append_unique(warnings, f"{year}: {warning}")
        normalized_payload = payloads[year].get("normalized")
        if isinstance(normalized_payload, dict):
            year_basis = _basis_from_normalized(normalized_payload)
            if year_basis == "unknown":
                _append_unique(limitations, f"{year}: preferred basis unknown")

    cash_conversion_trends.update(working_capital_trends)
    _apply_comparability_warnings(per_share_trends, corporate_actions_timeline, payloads, warnings)

    report = FinancialTrendReport(
        company=company,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        years_covered=years,
        basis=basis,
        basis_policy={
            "preferred_basis": basis,
            "basis_consistency": "mixed" if basis == "mixed" else ("unknown" if basis == "unknown" else "consistent"),
            "warnings": ["basis mismatch across years"] if basis == "mixed" else [],
        },
        metric_trends=metric_trends,
        metric_series={
            key: _alias_points(value)
            for key, value in {
                **metric_trends,
                "net_debt": balance_sheet_trends["net_debt"],
                "cfo": cash_conversion_trends["cfo"],
                "capex": cash_conversion_trends["capex"],
                "fcf": cash_conversion_trends["fcf"],
                "receivables": cash_conversion_trends["receivables"],
                "inventory": cash_conversion_trends["inventory"],
                "payables": cash_conversion_trends["payables"],
                "eps_basic": per_share_trends["eps_basic"],
                "eps_diluted": per_share_trends["eps_diluted"],
            }.items()
        },
        ratio_series={
            key: _alias_points(value)
            for key, value in {
                **margin_trends,
                **return_trends,
                "debt_to_equity": balance_sheet_trends["debt_to_equity"],
                "cfo_to_pat": cash_conversion_trends["cfo_to_pat"],
                "fcf_to_pat": cash_conversion_trends["fcf_to_pat"],
                "receivable_days": cash_conversion_trends["receivable_days"],
                "inventory_days": cash_conversion_trends["inventory_days"],
                "payable_days": cash_conversion_trends["payable_days"],
                "cash_conversion_cycle": cash_conversion_trends["cash_conversion_cycle"],
                **(
                    {"net_debt_to_equity": balance_sheet_trends["net_debt_to_equity"]}
                    if "net_debt_to_equity" in balance_sheet_trends
                    else {}
                ),
            }.items()
        },
        growth_summary=growth_summary,
        margin_trends=margin_trends,
        return_trends=return_trends,
        cash_conversion_trends=cash_conversion_trends,
        balance_sheet_trends=balance_sheet_trends,
        per_share_trends=per_share_trends,
        ownership_trends=ownership_trends,
        corporate_actions_timeline=corporate_actions_timeline,
        warnings=warnings,
        limitations=limitations,
    )

    validation_errors = validate_financial_trend_payload(report.to_dict())
    if validation_errors:
        raise ValueError("Invalid financial trend payload: " + "; ".join(validation_errors))
    return report


def write_financial_trends(*, company: str, company_root: Path, output_path: Path) -> FinancialTrendReport:
    report = build_financial_trends(company=company, company_root=company_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report
