from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .growth_schema import (
    GROWTH_METRIC_FIELDS,
    MARGIN_TREND_FIELDS,
    FinancialGrowthReport,
    GrowthItem,
    validate_financial_growth_payload,
)
from .reconciler import reconciliation_blocks_stage


_MONETARY_METRIC_MAP: Dict[str, Tuple[str, str]] = {
    "revenue": ("profit_and_loss", "revenue"),
    "ebitda": ("profit_and_loss", "ebitda"),
    "ebit": ("profit_and_loss", "ebit"),
    "pat": ("profit_and_loss", "pat"),
    "net_worth": ("balance_sheet", "net_worth"),
    "reserves": ("balance_sheet", "reserves"),
    "total_debt": ("balance_sheet", "total_debt"),
    "cfo": ("cash_flow", "cfo"),
    "capex": ("cash_flow", "capex"),
    "receivables": ("balance_sheet", "receivables"),
    "inventory": ("balance_sheet", "inventories"),
    "payables": ("balance_sheet", "payables"),
}

_PER_SHARE_MAP: Dict[str, Tuple[str, str]] = {
    "eps_basic": ("profit_and_loss", "eps_basic"),
    "eps_diluted": ("profit_and_loss", "eps_diluted"),
    "book_value_per_share": ("share_data", "book_value_per_share"),
}

CRITICAL_RECONCILIATION_FIELDS = {
    "revenue",
    "pat",
    "total_assets",
    "eps_basic",
    "eps_diluted",
    "shares_outstanding",
    "weighted_avg_shares",
    "diluted_shares",
}

METRIC_RECON_FIELDS: Dict[str, Tuple[str, ...]] = {
    "revenue": ("revenue",),
    "ebitda": ("ebitda",),
    "ebit": ("ebit",),
    "pat": ("pat",),
    "eps_basic": ("eps_basic",),
    "eps_diluted": ("eps_diluted",),
    "book_value_per_share": ("net_worth", "shares_outstanding"),
    "net_worth": ("net_worth",),
    "reserves": ("reserves",),
    "total_debt": ("total_debt",),
    "cfo": ("cfo",),
    "fcf": ("cfo", "capex"),
    "capex": ("capex",),
    "receivables": ("receivables",),
    "inventory": ("inventories",),
    "payables": ("payables",),
    "gross_margin": ("revenue", "cost_of_materials"),
    "ebitda_margin": ("revenue", "ebitda"),
    "ebit_margin": ("revenue", "ebit"),
    "opm": ("revenue", "ebit"),
    "npm": ("revenue", "pat"),
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path | None) -> Optional[Dict[str, Any]]:
    if path is None or not path.exists():
        return None
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else None


def _entry(payload: Dict[str, Any], section: str, field: str) -> Dict[str, Any]:
    value = payload.get(section, {})
    return value.get(field, {}) if isinstance(value, dict) else {}


def _value_crore(entry_payload: Dict[str, Any]) -> Optional[float]:
    value = entry_payload.get("value_crore")
    return float(value) if isinstance(value, (int, float)) else None


def _value_original_numeric(entry_payload: Dict[str, Any]) -> Optional[float]:
    raw = str(entry_payload.get("value_original", "")).strip().replace(",", "")
    if not raw:
        return None
    negative = raw.startswith("(") or raw.startswith("[") or raw.startswith("-")
    raw = raw.strip("()[]")
    if raw.startswith("-"):
        raw = raw[1:]
    try:
        value = float(raw)
    except ValueError:
        return None
    return -value if negative else value


def _comparative_numeric(entry_payload: Dict[str, Any], *, prefer_original_numeric: bool = False) -> Optional[float]:
    comparatives = entry_payload.get("comparatives", [])
    if not isinstance(comparatives, list) or not comparatives:
        return None
    comparative = comparatives[0]
    if not isinstance(comparative, dict):
        return None
    value = comparative.get("value_crore")
    if isinstance(value, (int, float)) and not prefer_original_numeric:
        return float(value)
    if prefer_original_numeric:
        if isinstance(comparative.get("value_per_share"), (int, float)):
            return float(comparative["value_per_share"])
        if isinstance(comparative.get("value_shares"), (int, float)):
            return float(comparative["value_shares"])
        raw = str(comparative.get("value_original", "")).strip().replace(",", "")
        if not raw:
            return None
        negative = raw.startswith("(") or raw.startswith("[") or raw.startswith("-")
        raw = raw.strip("()[]")
        if raw.startswith("-"):
            raw = raw[1:]
        try:
            value = float(raw)
        except ValueError:
            return None
        return -value if negative else value
    return None


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _round(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 4)


def _parse_year_label(value: str) -> Optional[int]:
    match = re.search(r"(\d{2,4})$", str(value).strip().lower())
    if not match:
        return None
    return int(match.group(1))


def _sort_year_labels(labels: Iterable[str]) -> List[str]:
    return sorted(labels, key=lambda item: (_parse_year_label(item) is None, _parse_year_label(item) or 0, item))


def _artifact_for_year(company_root: Path, year: str, filename: str) -> Path:
    return company_root / year / "financials" / filename


def _collect_available_years(company_root: Path, current_year: str) -> List[str]:
    candidates = {current_year} if current_year else set()
    if company_root.exists():
        for child in company_root.iterdir():
            if child.is_dir() and child.name.lower().startswith("fy"):
                candidates.add(child.name)
    return _sort_year_labels(candidates)


def _year_lookup(company_root: Path, current_year: str) -> Dict[int, str]:
    lookup: Dict[int, str] = {}
    for year in _collect_available_years(company_root, current_year):
        parsed = _parse_year_label(year)
        if parsed is not None:
            lookup[parsed] = year
    return lookup


def _normalized_payload_for_year(company_root: Path, year: str) -> Optional[Dict[str, Any]]:
    return _load_optional_json(_artifact_for_year(company_root, year, "normalized_fundamentals.json"))


def _ratios_payload_for_year(company_root: Path, year: str) -> Optional[Dict[str, Any]]:
    return _load_optional_json(_artifact_for_year(company_root, year, "financial_ratios.json"))


def _reconciliation_payload_for_year(company_root: Path, year: str) -> Optional[Dict[str, Any]]:
    return _load_optional_json(_artifact_for_year(company_root, year, "financial_reconciliation_report.json"))


def _determine_company_root(normalized_path: Path, company: str, year: str) -> Path:
    if (
        normalized_path.parent.name == "financials"
        and normalized_path.parent.parent.name == year
        and normalized_path.parent.parent.parent.name == company
    ):
        return normalized_path.parent.parent.parent
    return normalized_path.parent.parent.parent if len(normalized_path.parents) >= 3 else normalized_path.parent


def _basis_from_payload(payload: Dict[str, Any]) -> str:
    return str(payload.get("preferred_basis", "unknown") or "unknown")


def _basis_confidence_from_payload(payload: Dict[str, Any]) -> str:
    return str(payload.get("basis_confidence", "low") or "low")


def _basis_warnings_from_payload(payload: Dict[str, Any]) -> List[str]:
    manifest = payload.get("basis_manifest") or {}
    warnings = manifest.get("basis_warnings", []) if isinstance(manifest, dict) else []
    results = [str(item) for item in warnings if str(item).strip()]
    basis = _basis_from_payload(payload)
    if basis == "unknown":
        _append_unique(results, "preferred basis is unknown")
    return results


def _metric_basis(payload: Dict[str, Any], metric: str) -> str:
    if metric in _MONETARY_METRIC_MAP:
        section, field = _MONETARY_METRIC_MAP[metric]
        return str(_entry(payload, section, field).get("basis", _basis_from_payload(payload)) or _basis_from_payload(payload))
    if metric in _PER_SHARE_MAP:
        section, field = _PER_SHARE_MAP[metric]
        return str(_entry(payload, section, field).get("basis", _basis_from_payload(payload)) or _basis_from_payload(payload))
    return _basis_from_payload(payload)


def _fcf_from_payload(payload: Dict[str, Any]) -> Optional[float]:
    current = _value_crore(_entry(payload, "cash_flow", "fcf"))
    if current is not None:
        return current
    cfo = _value_crore(_entry(payload, "cash_flow", "cfo"))
    capex = _value_crore(_entry(payload, "cash_flow", "capex"))
    if cfo is None or capex is None:
        return None
    return cfo + capex if capex <= 0 else cfo - capex


def _fcf_from_comparatives(payload: Dict[str, Any]) -> Optional[float]:
    cfo = _comparative_numeric(_entry(payload, "cash_flow", "cfo"))
    capex = _comparative_numeric(_entry(payload, "cash_flow", "capex"))
    if cfo is None or capex is None:
        return None
    return cfo + capex if capex <= 0 else cfo - capex


def _metric_value(payload: Dict[str, Any], metric: str) -> Optional[float]:
    if metric == "fcf":
        return _fcf_from_payload(payload)
    if metric == "cost_of_materials":
        return _value_crore(_entry(payload, "profit_and_loss", "cost_of_materials"))
    if metric in _MONETARY_METRIC_MAP:
        section, field = _MONETARY_METRIC_MAP[metric]
        return _value_crore(_entry(payload, section, field))
    if metric in _PER_SHARE_MAP:
        section, field = _PER_SHARE_MAP[metric]
        return _value_original_numeric(_entry(payload, section, field))
    return None


def _metric_previous_value_from_comparatives(payload: Dict[str, Any], metric: str) -> Optional[float]:
    if metric == "fcf":
        return _fcf_from_comparatives(payload)
    if metric in _MONETARY_METRIC_MAP:
        section, field = _MONETARY_METRIC_MAP[metric]
        return _comparative_numeric(_entry(payload, section, field))
    if metric in _PER_SHARE_MAP:
        section, field = _PER_SHARE_MAP[metric]
        return _comparative_numeric(_entry(payload, section, field), prefer_original_numeric=True)
    return None


def _share_action_warning(payload: Dict[str, Any]) -> Optional[str]:
    actions = payload.get("corporate_actions", {})
    if not isinstance(actions, dict):
        return None
    flagged = []
    for field in ("split", "bonus", "qip", "rights_issue", "preferential_issue"):
        entry_payload = actions.get(field, {})
        occurred = entry_payload.get("occurred") if isinstance(entry_payload, dict) else None
        if occurred is True:
            flagged.append(field)
    if not flagged:
        return None
    return (
        "share count affected by corporate actions "
        f"({', '.join(flagged)}) but corporate action adjustment is not yet available"
    )


def _safe_growth(current: Optional[float], previous: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    if current is None or previous is None:
        return None, "previous-year data missing"
    if previous == 0:
        return None, "base value zero"
    return ((current - previous) / abs(previous)) * 100.0, None


def _safe_cagr(current: Optional[float], base: Optional[float], periods: int) -> Tuple[Optional[float], Optional[str]]:
    if current is None or base is None:
        return None, f"{periods}-year base data missing"
    if base == 0:
        return None, f"{periods}-year base value zero"
    if base < 0 or current < 0:
        return None, f"{periods}-year CAGR is not meaningful for negative values"
    return (((current / base) ** (1.0 / periods)) - 1.0) * 100.0, None


def _confidence(warnings: Sequence[str], *, basis_mismatch: bool = False, derived: bool = False) -> str:
    if any("missing" in warning or "zero" in warning or "blocked" in warning for warning in warnings):
        return "low"
    if basis_mismatch or derived or warnings:
        return "medium"
    return "high"


def _build_growth_item(
    *,
    metric: str,
    current_year: str,
    previous_year: str,
    current_value: Optional[float],
    previous_value: Optional[float],
    unit: str,
    basis: str,
    growth_percent: Optional[float],
    growth_warning: Optional[str],
    cagr_value: Optional[float],
    cagr_warning: Optional[str],
    extra_warnings: Sequence[str] = (),
    basis_mismatch: bool = False,
    derived: bool = False,
) -> GrowthItem:
    warnings = [warning for warning in [growth_warning, cagr_warning, *extra_warnings] if warning]
    absolute_change = None
    if current_value is not None and previous_value is not None:
        absolute_change = current_value - previous_value
    return GrowthItem(
        metric=metric,
        current_year=current_year,
        previous_year=previous_year,
        current_value=_round(current_value),
        previous_value=_round(previous_value),
        absolute_change=_round(absolute_change),
        growth_percent=_round(growth_percent),
        cagr_percent=_round(cagr_value),
        unit=unit,
        basis=basis,
        confidence=_confidence(warnings, basis_mismatch=basis_mismatch, derived=derived),
        warnings=warnings,
    )


def _find_year_by_offset(company_root: Path, current_year: str, offset: int) -> Optional[str]:
    current_numeric = _parse_year_label(current_year)
    if current_numeric is None:
        return None
    return _year_lookup(company_root, current_year).get(current_numeric - offset)


def _metric_reconciled(report: Optional[Dict[str, Any]], metric: str) -> Optional[str]:
    if report is None:
        return "financial reconciliation report missing"
    checks = report.get("checks", {})
    if not isinstance(checks, dict):
        return "financial reconciliation checks missing"
    for field_name in METRIC_RECON_FIELDS.get(metric, ()):
        item = checks.get(field_name)
        if not isinstance(item, dict):
            return f"missing reconciliation check for {field_name}"
        if item.get("status") == "fail":
            return f"{field_name} reconciliation failed"
    return None


def _extract_previous_label(current_payload: Dict[str, Any], metric: str) -> str:
    current_entry = None
    if metric in _MONETARY_METRIC_MAP:
        current_entry = _entry(current_payload, *_MONETARY_METRIC_MAP[metric])
    elif metric in _PER_SHARE_MAP:
        current_entry = _entry(current_payload, *_PER_SHARE_MAP[metric])
    comparatives = current_entry.get("comparatives", []) if isinstance(current_entry, dict) else []
    if comparatives and isinstance(comparatives[0], dict):
        return str(comparatives[0].get("period", "")) or "comparative_period"
    return ""


def _cagr_for_metric(company_root: Path, current_year: str, metric: str) -> Tuple[Optional[float], Optional[str]]:
    current_payload = _normalized_payload_for_year(company_root, current_year)
    if current_payload is None:
        return None, None
    if _metric_reconciled(_reconciliation_payload_for_year(company_root, current_year), metric):
        return None, "current-year reconciliation blocks CAGR"
    current_value = _metric_value(current_payload, metric)
    for periods in (5, 3, 2):
        base_year = _find_year_by_offset(company_root, current_year, periods)
        if base_year is None:
            continue
        base_payload = _normalized_payload_for_year(company_root, base_year)
        base_reconciliation = _reconciliation_payload_for_year(company_root, base_year)
        if base_payload is None or _metric_reconciled(base_reconciliation, metric):
            continue
        base_value = _metric_value(base_payload, metric)
        cagr, issue = _safe_cagr(current_value, base_value, periods)
        if cagr is not None:
            return cagr, None
        if issue:
            return None, issue
    return None, None


def _current_and_previous(
    company_root: Path,
    current_year: str,
    metric: str,
) -> Tuple[Optional[float], Optional[float], str, str, List[str], bool]:
    warnings: List[str] = []
    current_payload = _normalized_payload_for_year(company_root, current_year)
    current_reconciliation = _reconciliation_payload_for_year(company_root, current_year)
    if current_payload is None:
        return None, None, "", "unknown", ["current-year normalized fundamentals missing"], False

    current_block = _metric_reconciled(current_reconciliation, metric)
    current_value = _metric_value(current_payload, metric) if current_block is None else None
    if current_block is not None:
        _append_unique(warnings, current_block)

    previous_year = ""
    previous_value: Optional[float] = None
    previous_basis = "unknown"

    comparative_value = _metric_previous_value_from_comparatives(current_payload, metric)
    comparative_label = _extract_previous_label(current_payload, metric)
    if comparative_value is not None:
        previous_value = comparative_value
        previous_year = comparative_label or "comparative_period"
        previous_basis = _metric_basis(current_payload, metric)
    else:
        previous_year = _find_year_by_offset(company_root, current_year, 1) or ""
        if not previous_year:
            _append_unique(warnings, "previous-year data missing")
        else:
            previous_payload = _normalized_payload_for_year(company_root, previous_year)
            previous_reconciliation = _reconciliation_payload_for_year(company_root, previous_year)
            if previous_payload is None:
                _append_unique(warnings, "previous-year data missing")
            else:
                _append_unique(warnings, "normalized comparatives missing; fell back to previous-year normalized artifact")
                previous_block = _metric_reconciled(previous_reconciliation, metric)
                if previous_block is not None:
                    _append_unique(warnings, previous_block)
                else:
                    previous_value = _metric_value(previous_payload, metric)
                    previous_basis = _metric_basis(previous_payload, metric)
                    if previous_value is None:
                        _append_unique(warnings, "previous-year data missing")

    current_basis = _metric_basis(current_payload, metric)
    basis_mismatch = bool(previous_year) and previous_basis != "unknown" and current_basis != previous_basis
    if basis_mismatch:
        _append_unique(warnings, "basis mismatch across years")

    return current_value, previous_value, previous_year, current_basis, warnings, basis_mismatch


def _margin_value_from_payload(
    normalized_payload: Dict[str, Any],
    ratios_payload: Optional[Dict[str, Any]],
    metric: str,
) -> Tuple[Optional[float], bool]:
    if isinstance(ratios_payload, dict):
        ratios = ratios_payload.get("ratios", {})
        if isinstance(ratios, dict):
            ratio_entry = ratios.get(metric, {})
            if isinstance(ratio_entry, dict) and isinstance(ratio_entry.get("value"), (int, float)):
                return float(ratio_entry["value"]), False

    revenue = _metric_value(normalized_payload, "revenue")
    if revenue in (None, 0):
        return None, True
    if metric == "gross_margin":
        cost = _metric_value(normalized_payload, "cost_of_materials")
        if cost is None:
            return None, True
        return ((revenue - cost) / revenue) * 100.0, True
    numerator_metric = {
        "ebitda_margin": "ebitda",
        "ebit_margin": "ebit",
        "opm": "ebit",
        "npm": "pat",
    }.get(metric)
    numerator = _metric_value(normalized_payload, numerator_metric or "")
    if numerator is None:
        return None, True
    return (numerator / revenue) * 100.0, True


def calculate_financial_growth(
    *,
    company: str,
    year: str,
    normalized_path: Path,
    reconciliation_path: Path,
    ratios_path: Path | None = None,
) -> FinancialGrowthReport:
    if not normalized_path.exists():
        raise RuntimeError("financial_growth requires normalized_fundamentals.json")
    if not reconciliation_path.exists():
        raise RuntimeError("financial_growth requires financial_reconciliation_report.json")

    normalized_payload = _load_json(normalized_path)
    if not isinstance(normalized_payload, dict):
        raise RuntimeError("financial_growth requires normalized_fundamentals.json to contain an object")
    reconciliation_payload = _load_json(reconciliation_path)
    blocking_failures = reconciliation_blocks_stage(
        reconciliation_payload,
        required_fields=sorted(CRITICAL_RECONCILIATION_FIELDS),
    )
    if blocking_failures:
        raise RuntimeError(
            "financial_growth requires reconciled normalized fundamentals; blocking reconciliation failures: "
            + "; ".join(blocking_failures)
        )

    company_root = _determine_company_root(normalized_path, company, year)
    years_available = _collect_available_years(company_root, year)
    current_ratios_payload = _load_optional_json(ratios_path)

    top_warnings: List[str] = []
    limitations: List[str] = []
    growth_metrics: Dict[str, GrowthItem] = {}
    margin_changes: Dict[str, GrowthItem] = {}

    for metric in GROWTH_METRIC_FIELDS:
        current_value, previous_value, previous_year, basis, metric_warnings, basis_mismatch = _current_and_previous(
            company_root,
            year,
            metric,
        )
        growth_percent, growth_warning = _safe_growth(current_value, previous_value)
        cagr_percent, cagr_warning = _cagr_for_metric(company_root, year, metric)
        extra_warnings = list(metric_warnings)

        if metric in {"eps_basic", "eps_diluted", "book_value_per_share"}:
            share_warning = _share_action_warning(normalized_payload)
            if share_warning:
                _append_unique(extra_warnings, share_warning)

        item = _build_growth_item(
            metric=metric,
            current_year=year,
            previous_year=previous_year,
            current_value=current_value,
            previous_value=previous_value,
            unit="per share" if metric in {"eps_basic", "eps_diluted", "book_value_per_share"} else "₹ crore",
            basis=basis,
            growth_percent=growth_percent,
            growth_warning=growth_warning,
            cagr_value=cagr_percent,
            cagr_warning=cagr_warning,
            extra_warnings=extra_warnings,
            basis_mismatch=basis_mismatch,
            derived=(metric == "fcf"),
        )
        growth_metrics[metric] = item
        for warning in item.warnings:
            _append_unique(top_warnings, f"{metric}: {warning}")

    if current_ratios_payload is None:
        _append_unique(
            limitations,
            "financial_ratios.json missing or unreadable; margin expansion is derived directly from reconciled normalized fundamentals where possible",
        )

    for metric in MARGIN_TREND_FIELDS:
        previous_year = _find_year_by_offset(company_root, year, 1) or ""
        previous_payload = _normalized_payload_for_year(company_root, previous_year) if previous_year else None
        previous_reconciliation = _reconciliation_payload_for_year(company_root, previous_year) if previous_year else None
        previous_ratios = _ratios_payload_for_year(company_root, previous_year) if previous_year else None

        current_margin, current_derived = _margin_value_from_payload(normalized_payload, current_ratios_payload, metric)
        previous_margin: Optional[float] = None
        previous_derived = False
        extra_warnings: List[str] = []
        basis = _basis_from_payload(normalized_payload)
        basis_mismatch = False

        current_block = _metric_reconciled(reconciliation_payload, metric)
        if current_block is not None:
            current_margin = None
            _append_unique(extra_warnings, current_block)

        if previous_payload is None:
            _append_unique(extra_warnings, "previous-year data missing")
        else:
            previous_block = _metric_reconciled(previous_reconciliation, metric)
            if previous_block is not None:
                _append_unique(extra_warnings, previous_block)
            else:
                previous_margin, previous_derived = _margin_value_from_payload(previous_payload, previous_ratios, metric)
            previous_basis = _basis_from_payload(previous_payload)
            basis_mismatch = previous_basis != "unknown" and basis != previous_basis
            if basis_mismatch:
                _append_unique(extra_warnings, "basis mismatch across years")
            if previous_margin is None and previous_block is None:
                _append_unique(extra_warnings, "previous-year data missing")

        if current_derived or previous_derived:
            _append_unique(extra_warnings, "margin expansion derived from normalized fundamentals because ratio history was unavailable")

        growth_percent, growth_warning = _safe_growth(current_margin, previous_margin)
        item = _build_growth_item(
            metric=metric,
            current_year=year,
            previous_year=previous_year,
            current_value=current_margin,
            previous_value=previous_margin,
            unit="%",
            basis=basis,
            growth_percent=growth_percent,
            growth_warning=growth_warning,
            cagr_value=None,
            cagr_warning=None,
            extra_warnings=extra_warnings,
            basis_mismatch=basis_mismatch,
            derived=current_derived or previous_derived,
        )
        margin_changes[metric] = item
        for warning in item.warnings:
            _append_unique(top_warnings, f"{metric}: {warning}")

    report = FinancialGrowthReport(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status="warning" if top_warnings or limitations else "pass",
        basis_used=_basis_from_payload(normalized_payload),
        basis_confidence=_basis_confidence_from_payload(normalized_payload),
        years_available=years_available,
        growth_metrics=growth_metrics,
        margin_changes=margin_changes,
        basis_warnings=_basis_warnings_from_payload(normalized_payload),
        warnings=top_warnings,
        limitations=limitations,
    )
    errors = validate_financial_growth_payload(report.to_dict())
    if errors:
        raise ValueError("Invalid financial growth payload: " + "; ".join(errors))
    return report


def write_financial_growth(
    *,
    company: str,
    year: str,
    normalized_path: Path,
    reconciliation_path: Path,
    output_path: Path,
    ratios_path: Path | None = None,
) -> FinancialGrowthReport:
    report = calculate_financial_growth(
        company=company,
        year=year,
        normalized_path=normalized_path,
        reconciliation_path=reconciliation_path,
        ratios_path=ratios_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report
