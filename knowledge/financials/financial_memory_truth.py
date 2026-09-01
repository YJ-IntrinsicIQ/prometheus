from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from knowledge.company_memory import parse_financial_year
from knowledge.company_year_eligibility import build_company_year_eligibility_manifest


TRUTH_PRIORITY_FILES = (
    "financial_fact_registry.json",
    "financial_truth_reconciliation_report.json",
    "financial_basis_resolution.json",
    "financial_artifact_quarantine_report.json",
    "financial_ratios.json",
    "financial_growth.json",
    "normalized_fundamentals.json",
)

COMPANY_MEMORY_TRUTH_FILES = (
    "financial_memory_manifest.json",
    "financial_trends.json",
    "financial_quality_summary.json",
    "financial_driver_attribution.json",
)

YEAR_LEVEL_TRUTH_FILES = (
    "financial_fact_registry.json",
    "financial_truth_reconciliation_report.json",
    "financial_basis_resolution.json",
    "financial_artifact_quarantine_report.json",
    "financial_ratios.json",
    "financial_growth.json",
    "normalized_fundamentals.json",
    "corporate_actions.json",
    "shareholding_pattern.json",
)

MODULE_DIRNAME = "investor_financial_modules"
MODULE_FILENAMES = {
    "owner_earnings_bridge": "owner_earnings_bridge.json",
    "capital_allocation_roi_ledger": "capital_allocation_roi_ledger.json",
    "working_capital_quality_drilldown": "working_capital_quality_drilldown.json",
    "order_revenue_cash_conversion_tracker": "order_revenue_cash_conversion_tracker.json",
    "per_share_compounding_analysis": "per_share_compounding_analysis.json",
    "investor_financial_modules_manifest": "investor_financial_modules_manifest.json",
}

WARNING_BLOCK_RULES = {
    "free cash flow missing": ("fcf",),
    "fcf missing": ("fcf",),
    "capex missing": ("capex",),
    "payables missing": ("payables", "payable_days"),
    "payable days missing": ("payables", "payable_days"),
    "cfo/pat missing": ("cfo_to_pat", "cfo", "pat"),
    "roe unavailable": ("roe",),
    "roce unavailable": ("roce",),
    "share count missing": ("closing_shares", "shares_outstanding", "weighted_avg_shares", "diluted_shares"),
    "weighted average shares missing": ("weighted_avg_shares",),
    "diluted shares missing": ("weighted_average_diluted_shares", "diluted_shares"),
    "ownership data missing": ("promoter_holding", "public_holding", "mutual_fund_holding", "fii_holding", "dii_holding"),
    "basis unknown": (),
}

WARNING_REWRITES = {
    "free cash flow missing": "Free cash flow is available only through derived financial evidence.",
    "fcf missing": "Free cash flow is available only through derived financial evidence.",
    "capex missing": "Capex is available but requires careful interpretation from investing cash-flow evidence.",
    "payables missing": "Trade payables are partially available and should be interpreted with note-level caution.",
    "payable days missing": "Payable-days analysis is available but remains sensitive to note-level payables support.",
    "cfo/pat missing": "Cash-conversion analysis is available but may remain partially derived.",
    "roe unavailable": "Return-on-equity evidence is available but should be interpreted with basis caution.",
    "roce unavailable": "Return-on-capital evidence is available but should be interpreted with basis caution.",
    "share count missing": "Share-count evidence is available, but per-share comparability may still need caution.",
    "weighted average shares missing": "Weighted-average share-count evidence is partially available; per-share comparisons remain limited.",
    "diluted shares missing": "Diluted-share evidence is partially available; dilution conclusions remain limited.",
    "ownership data missing": "Ownership evidence is partially available but may not cover every investor category.",
    "basis unknown": "Financial basis is available but may still require cross-year comparability caution.",
}

ANALYTICAL_METRIC_GROUPS = {
    "revenue_and_income": ("revenue", "other_income", "total_income", "ebitda", "ebit", "pat"),
    "profitability": ("ebitda", "ebit", "pat", "pbt"),
    "margins": ("gross_margin", "ebitda_margin", "ebit_margin", "opm", "npm"),
    "return_on_capital": ("roe", "roce", "roa"),
    "cash_conversion": ("cfo", "capex", "fcf", "cfo_to_pat", "fcf_to_pat", "fcf_margin"),
    "working_capital": (
        "receivables",
        "inventory",
        "payables",
        "receivable_days",
        "inventory_days",
        "payable_days",
        "cash_conversion_cycle",
    ),
    "balance_sheet_strength": ("total_assets", "net_worth", "reserves", "cash_and_equivalents"),
    "debt_and_liquidity": ("total_debt", "net_debt", "debt_to_equity", "net_debt_to_equity", "interest_coverage"),
    "per_share": (
        "eps_basic",
        "eps_diluted",
        "book_value_per_share",
        "dividend_per_share",
        "payout_ratio",
        "closing_shares",
        "weighted_avg_shares",
        "weighted_average_diluted_shares",
    ),
    "capital_allocation": ("capex", "fcf", "dividends_paid"),
    "ownership": (
        "promoter_holding",
        "pledged_promoter_holding",
        "fii_holding",
        "dii_holding",
        "mutual_fund_holding",
        "public_holding",
    ),
}

PER_SHARE_DERIVED_NUMERATOR_FACTS = {
    "fcf_per_share": ("fcf",),
    "cfo_per_share": ("cfo",),
    "revenue_per_share": ("revenue",),
}

DIRECT_PER_SHARE_METRICS = {"eps_basic", "eps_diluted", "dividend_per_share", "book_value_per_share"}


def _load_optional_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _append_unique(items: List[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _sort_years(years: Iterable[str]) -> List[str]:
    return sorted({str(year) for year in years if str(year).strip()}, key=parse_financial_year)


def _fact_sort_key(fact: Dict[str, Any]) -> Tuple[int, int, int, int]:
    availability = str(fact.get("availability_status") or "")
    confidence = str(fact.get("confidence") or "")
    reconciliation = str(fact.get("reconciliation_status") or "")
    return (
        1 if bool(fact.get("usable_downstream")) else 0,
        1 if availability == "present_direct" else 0,
        1 if availability == "present_derived" else 0,
        1 if confidence == "high" and reconciliation == "pass" else 0,
    )


def _gather_facts(registry: Optional[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    if not isinstance(registry, dict):
        return grouped
    for field in (
        "available_facts",
        "derived_facts",
        "partial_facts",
        "missing_facts",
        "precise_missing_facts",
        "unreliable_facts",
        "invalid_facts",
        "quarantined_facts",
    ):
        for item in registry.get(field, []) if isinstance(registry.get(field), list) else []:
            if not isinstance(item, dict):
                continue
            grouped.setdefault(str(item.get("metric_id") or ""), []).append(item)
    for metric_id, items in grouped.items():
        grouped[metric_id] = sorted(items, key=_fact_sort_key, reverse=True)
    return grouped


def _iter_metric_names(items: Iterable[Any]) -> List[str]:
    names: List[str] = []
    for item in items:
        if isinstance(item, dict):
            for key in ("metric_id", "canonical_metric", "metric_name", "metric"):
                value = str(item.get(key) or "").strip()
                if value:
                    _append_unique(names, value)
        else:
            _append_unique(names, str(item))
    return names


def _metric_present(metric_names: Iterable[str], aliases: Iterable[str]) -> bool:
    lowered = {
        str(item or "").strip().lower().replace("-", "_").replace(" ", "_")
        for item in metric_names
        if str(item or "").strip()
    }
    for alias in aliases:
        token = str(alias or "").strip().lower().replace("-", "_").replace(" ", "_")
        if token and token in lowered:
            return True
    return False


def _normalize_warning_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _warning_block_match(warning: str, metric_names: Iterable[str]) -> Optional[str]:
    normalized = _normalize_warning_text(warning)
    for trigger, aliases in WARNING_BLOCK_RULES.items():
        if trigger in normalized:
            if not aliases or _metric_present(metric_names, aliases):
                return trigger
    return None


def _rewrite_warning_text(warning: str, trigger: Optional[str]) -> str:
    if not trigger:
        return str(warning or "").strip()
    return WARNING_REWRITES.get(trigger, str(warning or "").strip())


def _load_company_memory_artifacts(company_root: Path) -> Dict[str, Optional[Dict[str, Any]]]:
    financial_root = company_root / "company_memory" / "financials"
    artifacts: Dict[str, Optional[Dict[str, Any]]] = {}
    for filename in COMPANY_MEMORY_TRUTH_FILES:
        artifacts[filename] = _load_optional_json(financial_root / filename)
    modules_root = financial_root / MODULE_DIRNAME
    for key, filename in MODULE_FILENAMES.items():
        artifacts[filename] = _load_optional_json(modules_root / filename)
    return artifacts


def _source_status(*, company_root: Path, years: List[str]) -> Tuple[List[str], List[str], List[str]]:
    checked: List[str] = []
    used: List[str] = []
    missing: List[str] = []
    company_memory_root = company_root / "company_memory" / "financials"
    modules_root = company_memory_root / MODULE_DIRNAME
    for filename in COMPANY_MEMORY_TRUTH_FILES:
        rel = f"company_memory/financials/{filename}"
        checked.append(rel)
        (used if (company_memory_root / filename).exists() else missing).append(rel)
    for filename in MODULE_FILENAMES.values():
        rel = f"company_memory/financials/{MODULE_DIRNAME}/{filename}"
        checked.append(rel)
        (used if (modules_root / filename).exists() else missing).append(rel)
    for year in years:
        financial_root = company_root / year / "financials"
        for filename in YEAR_LEVEL_TRUTH_FILES:
            rel = f"{year}/financials/{filename}"
            checked.append(rel)
            (used if (financial_root / filename).exists() else missing).append(rel)
    return checked, used, missing


def _compact_metric_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "metric_id": str(item.get("metric_id") or item.get("canonical_metric") or item.get("metric_name") or item.get("metric") or "").strip(),
        "canonical_metric": str(item.get("canonical_metric") or item.get("metric_id") or item.get("metric") or "").strip(),
        "metric_name": str(item.get("metric_name") or item.get("metric_id") or item.get("metric") or "").strip(),
        "fiscal_year": str(item.get("fiscal_year") or item.get("year") or item.get("period") or "").strip(),
        "basis": str(item.get("basis") or "unknown").strip() or "unknown",
        "value": item.get("value"),
        "value_crore": item.get("value_crore"),
        "value_per_share": item.get("value_per_share"),
        "raw_number": item.get("raw_number"),
        "unit": str(item.get("unit") or "").strip(),
        "numerator_metric": str(item.get("numerator_metric") or "").strip(),
        "numerator_value": item.get("numerator_value"),
        "numerator_unit": str(item.get("numerator_unit") or "").strip(),
        "denominator_metric": str(item.get("denominator_metric") or "").strip(),
        "denominator_value": item.get("denominator_value"),
        "denominator_unit": str(item.get("denominator_unit") or "").strip(),
        "calculation_formula": str(item.get("calculation_formula") or "").strip(),
        "share_count_basis": str(item.get("share_count_basis") or "").strip(),
        "confidence": str(item.get("confidence") or "").strip(),
        "availability_status": str(item.get("availability_status") or "").strip(),
        "source_artifact": str(item.get("source_artifact") or "").strip(),
        "notes": list(item.get("notes", [])) if isinstance(item.get("notes"), list) else [],
        "warnings": list(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else [],
    }


def _coerce_metric_entry(value: Any, *, metric_id: str, fiscal_year: str, source_artifact: str, notes: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    entry = {
        "metric_id": metric_id,
        "canonical_metric": metric_id,
        "metric_name": metric_id.replace("_", " "),
        "fiscal_year": fiscal_year,
        "basis": str(value.get("basis") or value.get("basis_used") or "unknown"),
        "source_artifact": source_artifact,
        "confidence": str(value.get("confidence") or "medium"),
        "availability_status": "present_direct",
        "notes": list(notes or []),
        "warnings": list(value.get("warnings", [])) if isinstance(value.get("warnings"), list) else [],
    }
    for key in ("value", "value_crore", "value_per_share", "raw_number", "holding_percent", "amount_crore"):
        if isinstance(value.get(key), (int, float)):
            if key == "holding_percent":
                entry["value"] = value.get(key)
            elif key == "amount_crore":
                entry["value_crore"] = value.get(key)
                entry["value"] = value.get(key)
            else:
                entry[key] = value.get(key)
                if key in {"value_crore", "value_per_share", "raw_number"} and "value" not in entry:
                    entry["value"] = value.get(key)
    if not any(isinstance(entry.get(key), (int, float)) for key in ("value", "value_crore", "value_per_share", "raw_number")):
        return None
    return entry


def _normalize_metric_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _first_numeric(*values: Any) -> Optional[float]:
    for value in values:
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _fact_has_numeric_value(fact: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(fact, dict):
        return False
    return any(
        isinstance(fact.get(key), (int, float))
        for key in ("value", "value_crore", "value_per_share", "raw_number", "value_shares", "crore_shares", "amount_crore")
    )


def _bundle_fact_lookup(bundle: Dict[str, Any], *metric_ids: str) -> Optional[Dict[str, Any]]:
    fact_map = bundle.get("fact_map") or {}
    candidates: List[Dict[str, Any]] = []
    for metric_id in metric_ids:
        items = fact_map.get(metric_id) or fact_map.get(_normalize_metric_token(metric_id)) or []
        if items:
            first = items[0]
            if isinstance(first, dict):
                candidates.append(first)
    for fact in candidates:
        if bool(fact.get("usable_downstream")) and _fact_has_numeric_value(fact):
            return fact
    for fact in candidates:
        if _fact_has_numeric_value(fact):
            return fact
    return candidates[0] if candidates else None


def _fact_crore_value(fact: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(fact, dict):
        return None
    explicit = _first_numeric(fact.get("value_crore"), fact.get("amount_crore"))
    if explicit is not None:
        return explicit
    unit = str(fact.get("unit") or "").strip().lower()
    if "crore" in unit:
        return _first_numeric(fact.get("value"))
    return None


def _fact_share_count(fact: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(fact, dict):
        return None
    return _first_numeric(fact.get("raw_number"), fact.get("value_shares"))


def validate_per_share_metric_units(metric: Dict[str, Any]) -> Dict[str, Any]:
    warnings: List[str] = []
    failures: List[str] = []
    if not isinstance(metric, dict):
        return {"status": "fail", "warnings": warnings, "failures": ["metric must be an object"]}
    unit = str(metric.get("unit") or "").strip()
    formula = str(metric.get("calculation_formula") or "").strip()
    metric_id = str(metric.get("metric_id") or "").strip()
    value_per_share = _first_numeric(metric.get("value_per_share"), metric.get("value"))
    numerator_value = _first_numeric(metric.get("numerator_value"))
    numerator_unit = str(metric.get("numerator_unit") or "").strip()
    denominator_value = _first_numeric(metric.get("denominator_value"))
    denominator_unit = str(metric.get("denominator_unit") or "").strip()
    if metric_id in DIRECT_PER_SHARE_METRICS:
        if not unit:
            failures.append("direct per-share metric has no unit metadata")
        if not formula:
            failures.append("direct per-share metric has no calculation metadata")
    elif metric_id.endswith("_per_share"):
        if not unit:
            failures.append("derived per-share metric has no unit metadata")
        if not formula:
            failures.append("derived per-share metric has no calculation metadata")
    if numerator_unit == "INR crore" and denominator_unit == "shares":
        if (
            value_per_share is not None
            and numerator_value is not None
            and denominator_value is not None
            and numerator_value > 0
            and denominator_value > 0
            and value_per_share < 0.01
        ):
            failures.append("likely crore-to-share conversion bug detected")
        if value_per_share is not None and "e-" in format(value_per_share, "g").lower():
            failures.append("scientific-notation per-share value suggests missed crore conversion")
    share_count_basis = str(metric.get("share_count_basis") or "").strip()
    if (
        share_count_basis == "closing_shares"
        and value_per_share is not None
        and denominator_value is not None
    ):
        warnings.append("Weighted-average shares unavailable; calculated using closing shares.")
    status = "fail" if failures else "warning" if warnings else "pass"
    return {"status": status, "warnings": warnings, "failures": failures}


def _build_direct_per_share_entry(
    metric_id: str,
    *,
    fiscal_year: str,
    value_per_share: Optional[float],
    source_artifact: str,
    warnings: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    if value_per_share is None:
        return None
    return {
        "metric_id": metric_id,
        "canonical_metric": metric_id,
        "metric_name": metric_id.replace("_", " "),
        "fiscal_year": fiscal_year,
        "basis": "unknown",
        "value": value_per_share,
        "value_per_share": value_per_share,
        "unit": "INR/share",
        "source_unit": "INR/share",
        "numerator_metric": metric_id,
        "numerator_value": value_per_share,
        "numerator_unit": "INR/share",
        "denominator_metric": "",
        "denominator_value": None,
        "denominator_unit": "",
        "calculation_formula": "reported_directly",
        "share_count_basis": "reported_directly",
        "source_artifact": source_artifact,
        "confidence": "medium",
        "availability_status": "present_direct",
        "notes": ["Hydrated from per-share compounding analysis."],
        "warnings": list(warnings or []),
    }


def _build_derived_per_share_entry(
    metric_id: str,
    *,
    fiscal_year: str,
    numerator_metric: str,
    numerator_value_crore: float,
    denominator_metric: str,
    denominator_value: float,
    source_artifact: str,
    warning: str = "",
) -> Dict[str, Any]:
    value_per_share = numerator_value_crore * 10_000_000.0 / denominator_value
    warnings = [warning] if warning else []
    return {
        "metric_id": metric_id,
        "canonical_metric": metric_id,
        "metric_name": metric_id.replace("_", " "),
        "fiscal_year": fiscal_year,
        "basis": "unknown",
        "value": value_per_share,
        "value_per_share": value_per_share,
        "unit": "INR/share",
        "numerator_metric": numerator_metric,
        "numerator_value": numerator_value_crore,
        "numerator_unit": "INR crore",
        "denominator_metric": denominator_metric,
        "denominator_value": denominator_value,
        "denominator_unit": "shares",
        "calculation_formula": f"value_crore * 10000000 / {denominator_metric}",
        "share_count_basis": denominator_metric,
        "source_artifact": source_artifact,
        "confidence": "medium" if denominator_metric == "closing_shares" else "high",
        "availability_status": "present_derived",
        "notes": ["Hydrated from per-share compounding analysis."],
        "warnings": warnings,
    }


def _build_missing_per_share_entry(
    metric_id: str,
    *,
    fiscal_year: str,
    numerator_metric: str,
    numerator_value: Optional[float],
    numerator_unit: str,
    denominator_metric: str,
    denominator_value: Optional[float],
    denominator_unit: str,
    calculation_formula: str,
    source_artifact: str,
    note: str,
) -> Dict[str, Any]:
    missing_inputs: List[str] = []
    if numerator_metric and numerator_value is None:
        missing_inputs.append(numerator_metric)
    if denominator_metric and denominator_value in (None, 0):
        missing_inputs.append(denominator_metric)
    return {
        "metric_id": metric_id,
        "canonical_metric": metric_id,
        "metric_name": metric_id.replace("_", " "),
        "fiscal_year": fiscal_year,
        "basis": "unknown",
        "value": None,
        "value_per_share": None,
        "unit": "INR/share",
        "numerator_metric": numerator_metric,
        "numerator_value": numerator_value,
        "numerator_unit": numerator_unit,
        "denominator_metric": denominator_metric,
        "denominator_value": denominator_value,
        "denominator_unit": denominator_unit,
        "calculation_formula": calculation_formula,
        "share_count_basis": denominator_metric,
        "availability_status": "missing",
        "missing_inputs": missing_inputs,
        "source_artifact": source_artifact,
        "confidence": "missing",
        "notes": [note],
        "warnings": [],
    }


def resolve_share_count_for_per_share_metric(
    *,
    year: str,
    bundle: Dict[str, Any],
    analysis: Dict[str, Any],
    prefer_diluted: bool = False,
) -> Dict[str, Any]:
    weighted_fact = _bundle_fact_lookup(bundle, "weighted_avg_shares", "weighted_average_basic_shares")
    diluted_fact = _bundle_fact_lookup(bundle, "weighted_average_diluted_shares", "diluted_shares")
    closing_fact = _bundle_fact_lookup(bundle, "closing_shares")

    weighted_value = _first_numeric(_fact_share_count(weighted_fact), analysis.get("weighted_average_basic_shares"))
    diluted_value = _first_numeric(_fact_share_count(diluted_fact), analysis.get("weighted_average_diluted_shares"))
    closing_value = _first_numeric(_fact_share_count(closing_fact), analysis.get("closing_shares"))

    if prefer_diluted and diluted_value not in (None, 0):
        return {
            "denominator_value": diluted_value,
            "denominator_metric": "weighted_average_diluted_shares",
            "denominator_unit": "shares",
            "share_count_basis": "weighted_average_diluted_shares",
            "warnings": [],
        }
    if weighted_value not in (None, 0):
        return {
            "denominator_value": weighted_value,
            "denominator_metric": "weighted_average_basic_shares",
            "denominator_unit": "shares",
            "share_count_basis": "weighted_average_basic_shares",
            "warnings": [],
        }
    if not prefer_diluted and diluted_value not in (None, 0):
        return {
            "denominator_value": diluted_value,
            "denominator_metric": "weighted_average_diluted_shares",
            "denominator_unit": "shares",
            "share_count_basis": "weighted_average_diluted_shares",
            "warnings": [],
        }
    if closing_value not in (None, 0):
        return {
            "denominator_value": closing_value,
            "denominator_metric": "closing_shares",
            "denominator_unit": "shares",
            "share_count_basis": "closing_shares",
            "warnings": ["Weighted-average shares unavailable; calculated using closing shares."],
        }
    return {
        "denominator_value": None,
        "denominator_metric": "closing_shares",
        "denominator_unit": "shares",
        "share_count_basis": "closing_shares",
        "warnings": [],
    }


def _owner_bridge_by_year(artifacts: Dict[str, Optional[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    owner_bridge = artifacts.get(MODULE_FILENAMES["owner_earnings_bridge"]) or {}
    return {
        str(item.get("fiscal_year") or "").strip(): item
        for item in owner_bridge.get("bridges", []) or []
        if isinstance(item, dict) and str(item.get("fiscal_year") or "").strip()
    }


def _hydrate_module_metrics(company_root: Path) -> Dict[str, List[Dict[str, Any]]]:
    artifacts = _load_company_memory_artifacts(company_root)
    owner_bridge = artifacts.get(MODULE_FILENAMES["owner_earnings_bridge"]) or {}
    capital_ledger = artifacts.get(MODULE_FILENAMES["capital_allocation_roi_ledger"]) or {}
    working_capital = artifacts.get(MODULE_FILENAMES["working_capital_quality_drilldown"]) or {}
    order_conversion = artifacts.get(MODULE_FILENAMES["order_revenue_cash_conversion_tracker"]) or {}
    per_share = artifacts.get(MODULE_FILENAMES["per_share_compounding_analysis"]) or {}

    usable_current: List[Dict[str, Any]] = []
    usable_derived: List[Dict[str, Any]] = []
    partial: List[Dict[str, Any]] = []
    precise_missing: List[Dict[str, Any]] = []
    unreliable_metrics: List[Dict[str, Any]] = []
    invalid_metrics: List[Dict[str, Any]] = []
    precision_limits: List[str] = []
    questions: List[str] = []
    source_provenance: List[str] = []
    unit_validation_warnings: List[str] = []
    unit_validation_failures: List[str] = []
    recomputed_metrics: List[Dict[str, Any]] = []
    owner_bridge_lookup = _owner_bridge_by_year(artifacts)
    bundles = load_financial_truth_by_year(company_root=company_root)

    for payload_name, artifact in (
        (MODULE_FILENAMES["owner_earnings_bridge"], owner_bridge),
        (MODULE_FILENAMES["capital_allocation_roi_ledger"], capital_ledger),
        (MODULE_FILENAMES["working_capital_quality_drilldown"], working_capital),
        (MODULE_FILENAMES["order_revenue_cash_conversion_tracker"], order_conversion),
        (MODULE_FILENAMES["per_share_compounding_analysis"], per_share),
    ):
        if artifact:
            _append_unique(source_provenance, payload_name)

    for bridge in owner_bridge.get("bridges", []) if isinstance(owner_bridge.get("bridges"), list) else []:
        if not isinstance(bridge, dict):
            continue
        fiscal_year = str(bridge.get("fiscal_year") or "").strip()
        for metric_id, field, note in (
            ("owner_earnings_estimate", "owner_earnings_estimate", "Derived from owner earnings bridge."),
            ("fcf", "conservative_fcf_after_total_capex", "Derived from owner earnings bridge."),
            ("fcf_after_ppe_cwip_capex", "fcf_after_ppe_cwip_capex", "Derived after identified capex."),
        ):
            entry = _coerce_metric_entry(
                {"value_crore": bridge.get(field), "basis": bridge.get("basis"), "confidence": bridge.get("owner_earnings_precision_status")},
                metric_id=metric_id,
                fiscal_year=fiscal_year,
                source_artifact=MODULE_FILENAMES["owner_earnings_bridge"],
                notes=[note],
            )
            if entry:
                usable_derived.append(entry)
        for warning in bridge.get("owner_earnings_warnings", []) if isinstance(bridge.get("owner_earnings_warnings"), list) else []:
            _append_unique(precision_limits, warning)
        status = str(bridge.get("owner_earnings_precision_status") or "").strip().lower()
        if status and status not in {"high", "pass", "usable"}:
            _append_unique(precision_limits, f"{fiscal_year}: owner-earnings precision is {status}.")

    for drill in working_capital.get("drilldown", []) if isinstance(working_capital.get("drilldown"), list) else []:
        if not isinstance(drill, dict):
            continue
        fiscal_year = str(drill.get("fiscal_year") or "").strip()
        for metric_id in ("receivables", "inventory", "payables", "receivable_days", "inventory_days", "payable_days", "cash_conversion_cycle"):
            entry = _coerce_metric_entry(
                {"value": drill.get(metric_id), "basis": drill.get("basis"), "confidence": drill.get("confidence")},
                metric_id=metric_id,
                fiscal_year=fiscal_year,
                source_artifact=MODULE_FILENAMES["working_capital_quality_drilldown"],
                notes=["Hydrated from working-capital quality drilldown."],
            )
            if entry:
                usable_current.append(entry)
        for field in ("quality_questions",):
            for question in drill.get(field, []) if isinstance(drill.get(field), list) else []:
                _append_unique(questions, str(question))
        if str(drill.get("working_capital_intensity_status") or "").strip():
            _append_unique(precision_limits, f"{fiscal_year}: working-capital intensity is {drill.get('working_capital_intensity_status')}.")

    for tracker in order_conversion.get("tracker", []) if isinstance(order_conversion.get("tracker"), list) else []:
        if not isinstance(tracker, dict):
            continue
        fiscal_year = str(tracker.get("fiscal_year") or "").strip()
        for metric_id in ("revenue", "receivables", "inventory", "cfo", "fcf"):
            entry = _coerce_metric_entry(
                {"value_crore": tracker.get(metric_id), "basis": tracker.get("basis"), "confidence": tracker.get("confidence")},
                metric_id=metric_id,
                fiscal_year=fiscal_year,
                source_artifact=MODULE_FILENAMES["order_revenue_cash_conversion_tracker"],
                notes=["Hydrated from order-to-cash tracker."],
            )
            if entry:
                usable_current.append(entry if metric_id != "fcf" else dict(entry, availability_status="present_derived"))
        for question in tracker.get("cash_conversion_questions", []) if isinstance(tracker.get("cash_conversion_questions"), list) else []:
            _append_unique(questions, str(question))
        if str(tracker.get("revenue_to_cash_visibility") or "").strip():
            _append_unique(precision_limits, f"{fiscal_year}: revenue-to-cash visibility is {tracker.get('revenue_to_cash_visibility')}.")

    for analysis in per_share.get("analysis", []) if isinstance(per_share.get("analysis"), list) else []:
        if not isinstance(analysis, dict):
            continue
        fiscal_year = str(analysis.get("fiscal_year") or "").strip()
        metadata_map = analysis.get("per_share_metric_metadata") if isinstance(analysis.get("per_share_metric_metadata"), dict) else {}
        bundle = bundles.get(fiscal_year) or {}

        for metric_id in ("closing_shares", "weighted_average_basic_shares", "weighted_average_diluted_shares"):
            entry = _coerce_metric_entry(
                {"raw_number": analysis.get(metric_id), "basis": analysis.get("basis"), "confidence": analysis.get("confidence")},
                metric_id=metric_id,
                fiscal_year=fiscal_year,
                source_artifact=MODULE_FILENAMES["per_share_compounding_analysis"],
                notes=["Hydrated from per-share compounding analysis."],
            )
            if entry:
                usable_current.append(entry)

        for metric_id in ("eps_basic", "eps_diluted", "book_value_per_share", "dividend_per_share"):
            direct_meta = metadata_map.get(metric_id) if isinstance(metadata_map.get(metric_id), dict) else {}
            direct_entry = _build_direct_per_share_entry(
                metric_id,
                fiscal_year=fiscal_year,
                value_per_share=_first_numeric(direct_meta.get("value_per_share"), analysis.get(metric_id)),
                source_artifact=MODULE_FILENAMES["per_share_compounding_analysis"],
                warnings=list(direct_meta.get("warnings", [])) if isinstance(direct_meta.get("warnings"), list) else [],
            )
            if direct_entry:
                usable_current.append(direct_entry)

        for metric_id in ("fcf_per_share", "owner_earnings_per_share", "cfo_per_share", "revenue_per_share"):
            metric_meta = metadata_map.get(metric_id) if isinstance(metadata_map.get(metric_id), dict) else {}
            share_resolution = resolve_share_count_for_per_share_metric(
                year=fiscal_year,
                bundle=bundle,
                analysis=analysis,
                prefer_diluted=False,
            )
            entry: Optional[Dict[str, Any]] = None
            value_per_share: Optional[float] = None
            numerator_metric = ""
            numerator_value: Optional[float] = None
            numerator_unit = ""
            metadata_denominator_metric = ""
            metadata_denominator_value: Optional[float] = None
            metadata_denominator_unit = ""
            calculation_formula = ""
            if metric_meta:
                value_per_share = _first_numeric(metric_meta.get("value_per_share"), metric_meta.get("value"))
                numerator_metric = str(metric_meta.get("numerator_metric") or "")
                numerator_value = _first_numeric(metric_meta.get("numerator_value"))
                numerator_unit = str(metric_meta.get("numerator_unit") or "")
                metadata_denominator_metric = str(metric_meta.get("denominator_metric") or "")
                metadata_denominator_value = _first_numeric(metric_meta.get("denominator_value"))
                metadata_denominator_unit = str(metric_meta.get("denominator_unit") or "")
                calculation_formula = str(metric_meta.get("calculation_formula") or "")
                entry = {
                    "metric_id": metric_id,
                    "canonical_metric": metric_id,
                    "metric_name": metric_id.replace("_", " "),
                    "fiscal_year": fiscal_year,
                    "basis": str(metric_meta.get("basis") or analysis.get("basis") or "unknown"),
                    "value": value_per_share,
                    "value_per_share": value_per_share,
                    "unit": str(metric_meta.get("unit") or ""),
                    "numerator_metric": numerator_metric,
                    "numerator_value": numerator_value,
                    "numerator_unit": numerator_unit,
                    "denominator_metric": metadata_denominator_metric,
                    "denominator_value": metadata_denominator_value,
                    "denominator_unit": metadata_denominator_unit,
                    "calculation_formula": calculation_formula,
                    "share_count_basis": str(metric_meta.get("share_count_basis") or ""),
                    "source_artifact": MODULE_FILENAMES["per_share_compounding_analysis"],
                    "confidence": str(metric_meta.get("confidence") or analysis.get("confidence") or "medium"),
                    "availability_status": "present_derived",
                    "notes": ["Hydrated from per-share compounding analysis."],
                    "warnings": list(metric_meta.get("warnings", [])) if isinstance(metric_meta.get("warnings"), list) else [],
                }
            else:
                raw_value = _first_numeric(analysis.get(metric_id))
                if raw_value is not None:
                    value_per_share = raw_value
                    entry = {
                        "metric_id": metric_id,
                        "canonical_metric": metric_id,
                        "metric_name": metric_id.replace("_", " "),
                        "fiscal_year": fiscal_year,
                        "basis": str(analysis.get("basis") or "unknown"),
                        "value": raw_value,
                        "value_per_share": raw_value,
                        "unit": "",
                        "numerator_metric": "",
                        "numerator_value": None,
                        "numerator_unit": "",
                        "denominator_metric": "",
                        "denominator_value": None,
                        "denominator_unit": "",
                        "calculation_formula": "",
                        "share_count_basis": "",
                        "source_artifact": MODULE_FILENAMES["per_share_compounding_analysis"],
                        "confidence": str(analysis.get("confidence") or "medium"),
                        "availability_status": "present_derived",
                        "notes": ["Hydrated from per-share compounding analysis."],
                        "warnings": [],
                    }

            if metric_id == "owner_earnings_per_share":
                if not numerator_metric:
                    numerator_metric = "owner_earnings_estimate"
                if numerator_value is None:
                    numerator_value = _first_numeric((owner_bridge_lookup.get(fiscal_year) or {}).get("owner_earnings_estimate"))
                if not numerator_unit and numerator_value is not None:
                    numerator_unit = "INR crore"
            else:
                derived_metric_ids = PER_SHARE_DERIVED_NUMERATOR_FACTS.get(metric_id, ())
                if not numerator_metric:
                    numerator_metric = derived_metric_ids[0] if derived_metric_ids else ""
                if numerator_value is None and derived_metric_ids:
                    numerator_fact = _bundle_fact_lookup(bundle, *derived_metric_ids)
                    numerator_value = _fact_crore_value(numerator_fact)
                if not numerator_unit and numerator_value is not None:
                    numerator_unit = "INR crore"

            effective_denominator_metric = metadata_denominator_metric or str(share_resolution.get("denominator_metric") or "")
            effective_denominator_value = (
                metadata_denominator_value
                if metadata_denominator_value not in (None, 0)
                else share_resolution.get("denominator_value")
            )
            effective_denominator_unit = metadata_denominator_unit or str(share_resolution.get("denominator_unit") or "shares")
            effective_share_count_basis = str(metric_meta.get("share_count_basis") or share_resolution.get("share_count_basis") or "")
            share_warnings = list(share_resolution.get("warnings", [])) if isinstance(share_resolution.get("warnings"), list) else []
            effective_formula = calculation_formula or f"value_crore * 10000000 / {effective_denominator_metric or 'shares'}"

            if entry is None and numerator_value is not None and effective_denominator_value not in (None, 0):
                entry = _build_derived_per_share_entry(
                    metric_id,
                    fiscal_year=fiscal_year,
                    numerator_metric=numerator_metric,
                    numerator_value_crore=numerator_value,
                    denominator_metric=effective_denominator_metric,
                    denominator_value=effective_denominator_value,
                    source_artifact=MODULE_FILENAMES["per_share_compounding_analysis"],
                    warning=share_warnings[0] if share_warnings and effective_denominator_metric == "closing_shares" else "",
                )
                recomputed_metrics.append({"metric_id": metric_id, "fiscal_year": fiscal_year, "reason": "recomputed_from_available_numerator_and_shares"})

            if entry is None or _first_numeric(entry.get("value_per_share"), entry.get("value")) is None:
                missing_entry = _build_missing_per_share_entry(
                    metric_id,
                    fiscal_year=fiscal_year,
                    numerator_metric=numerator_metric,
                    numerator_value=numerator_value,
                    numerator_unit=numerator_unit or "INR crore",
                    denominator_metric=effective_denominator_metric or denominator_metric,
                    denominator_value=effective_denominator_value,
                    denominator_unit=effective_denominator_unit or "shares",
                    calculation_formula=effective_formula,
                    source_artifact=MODULE_FILENAMES["per_share_compounding_analysis"],
                    note=f"{metric_id.replace('_', '/')} could not be calculated because {numerator_metric or 'numerator'} and/or share-count inputs are unavailable.",
                )
                if numerator_value is not None or effective_denominator_value not in (None, 0):
                    missing_entry["availability_status"] = "partial"
                    missing_entry["confidence"] = "low"
                    partial.append(missing_entry)
                else:
                    precise_missing.append(missing_entry)
                continue

            validation = validate_per_share_metric_units(entry)
            unit_validation_warnings.extend(
                [f"{fiscal_year}:{metric_id}: {warning}" for warning in validation["warnings"]]
            )
            if validation["status"] == "fail":
                if metric_id == "owner_earnings_per_share":
                    numerator_value = _first_numeric((owner_bridge_lookup.get(fiscal_year) or {}).get("owner_earnings_estimate"))
                    numerator_metric = "owner_earnings_estimate"
                else:
                    numerator_fact = _bundle_fact_lookup(bundle, *PER_SHARE_DERIVED_NUMERATOR_FACTS.get(metric_id, ()))
                    numerator_value = _fact_crore_value(numerator_fact)
                    numerator_metric = (PER_SHARE_DERIVED_NUMERATOR_FACTS.get(metric_id) or ("",))[0]
                if numerator_value is not None and effective_denominator_value not in (None, 0):
                    entry = _build_derived_per_share_entry(
                        metric_id,
                        fiscal_year=fiscal_year,
                        numerator_metric=numerator_metric,
                        numerator_value_crore=numerator_value,
                        denominator_metric=effective_denominator_metric,
                        denominator_value=effective_denominator_value,
                        source_artifact=MODULE_FILENAMES["per_share_compounding_analysis"],
                        warning=share_warnings[0] if share_warnings and effective_denominator_metric == "closing_shares" else "",
                    )
                    recomputed_metrics.append({"metric_id": metric_id, "fiscal_year": fiscal_year, "reason": "recomputed_after_unit_validation_failure"})
                    validation = validate_per_share_metric_units(entry)
                    unit_validation_warnings.extend(
                        [f"{fiscal_year}:{metric_id}: {warning}" for warning in validation["warnings"]]
                    )
                else:
                    entry["availability_status"] = "unreliable"
                    entry["warnings"] = list(entry.get("warnings", [])) + list(validation["failures"])
                    unreliable_metrics.append(entry)
                    unit_validation_failures.extend(
                        [f"{fiscal_year}:{metric_id}: {failure}" for failure in validation["failures"]]
                    )
                    continue

            entry["share_count_basis"] = effective_share_count_basis or str(entry.get("share_count_basis") or "")

            if metric_id == "owner_earnings_per_share":
                usable_derived.append(entry)
            else:
                usable_current.append(entry)
        if str(analysis.get("dilution_status") or "").strip():
            _append_unique(precision_limits, f"{fiscal_year}: dilution status is {analysis.get('dilution_status')}.")

    for entry in capital_ledger.get("entries", []) if isinstance(capital_ledger.get("entries"), list) else []:
        if not isinstance(entry, dict):
            continue
        fiscal_year = str(entry.get("fiscal_year") or entry.get("year") or "").strip()
        for metric_id in ("capital_raised", "retained_earnings", "capex_deployed", "working_capital_deployed", "debt_repayment", "dividends", "buybacks", "unutilised_issue_proceeds"):
            metric = _coerce_metric_entry(
                {"value_crore": entry.get(metric_id), "basis": entry.get("basis"), "confidence": entry.get("reliability")},
                metric_id=metric_id,
                fiscal_year=fiscal_year,
                source_artifact=MODULE_FILENAMES["capital_allocation_roi_ledger"],
                notes=["Hydrated from capital-allocation ROI ledger."],
            )
            if metric:
                usable_current.append(metric)
        for question in entry.get("follow_up_questions", []) if isinstance(entry.get("follow_up_questions"), list) else []:
            _append_unique(questions, str(question))
        if str(entry.get("roi_measurability_status") or "").strip():
            _append_unique(precision_limits, f"{fiscal_year}: ROI measurability is {entry.get('roi_measurability_status')}.")

    return {
        "usable_current_metrics": usable_current,
        "usable_derived_metrics": usable_derived,
        "partial_metrics": partial,
        "precise_missing_metrics": precise_missing,
        "unreliable_metrics": unreliable_metrics,
        "invalid_metrics": invalid_metrics,
        "precision_limits": precision_limits,
        "investor_relevant_questions": questions,
        "source_provenance": source_provenance,
        "unit_validation_warnings": unit_validation_warnings,
        "unit_validation_failures": unit_validation_failures,
        "recomputed_metrics": recomputed_metrics,
    }


def _fallback_fact_map(bundle: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    normalized = bundle.get("normalized") or {}
    ratios = bundle.get("ratios") or {}
    fallback: Dict[str, Dict[str, Any]] = {}

    def add(metric_id: str, item: Dict[str, Any], *, unit: str, source_statement: str, derived: bool = False) -> None:
        if not isinstance(item, dict):
            return
        value = item.get("value_crore")
        if not isinstance(value, (int, float)):
            value = item.get("value")
        if not isinstance(value, (int, float)) and isinstance(item.get("value_per_share"), (int, float)):
            value = item.get("value_per_share")
        if not isinstance(value, (int, float)) and isinstance(item.get("raw_number"), (int, float)):
            value = item.get("raw_number")
        availability = "present_derived" if derived and isinstance(value, (int, float)) else ("present_direct" if isinstance(value, (int, float)) else "missing")
        fallback[metric_id] = {
            "metric_id": metric_id,
            "metric_name": metric_id.replace("_", " "),
            "fiscal_year": str(bundle.get("year") or ""),
            "period": str(item.get("period") or bundle.get("year") or ""),
            "value": float(value) if isinstance(value, (int, float)) else None,
            "unit": unit,
            "basis": str(item.get("basis") or normalized.get("preferred_basis") or ratios.get("basis_used") or "unknown"),
            "source_statement": source_statement,
            "source_artifact": str(item.get("source_artifact") or ("financial_ratios.json" if derived else "normalized_fundamentals.json")),
            "source_line_item": str(item.get("source_line_item") or metric_id),
            "source_page": item.get("source_page"),
            "confidence": str(item.get("confidence") or ("medium" if availability != "missing" else "missing")),
            "availability_status": availability,
            "derived": derived,
            "formula": str(item.get("formula") or ""),
            "inputs_used": list(item.get("inputs_used", [])) if isinstance(item.get("inputs_used"), list) else [],
            "warnings": list(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else [],
            "reconciliation_status": "unknown",
            "usable_downstream": availability in {"present_direct", "present_derived"},
            "notes": ["Fallback fact used because financial_fact_registry.json is missing."],
        }

    for section_name, fields in (
        ("profit_and_loss", ("revenue", "ebitda", "ebit", "pat", "pbt", "other_income", "total_income")),
        ("balance_sheet", ("total_assets", "net_worth", "reserves", "cash_and_equivalents", "total_debt", "receivables", "inventories", "payables")),
        ("cash_flow", ("cfo", "capex", "dividends_paid")),
        ("share_data", ("shares_outstanding", "weighted_avg_shares", "diluted_shares", "eps_basic", "eps_diluted", "book_value_per_share")),
    ):
        section = normalized.get(section_name) if isinstance(normalized.get(section_name), dict) else {}
        for field in fields:
            item = section.get(field)
            metric_id = {
                "inventories": "inventory",
                "shares_outstanding": "closing_shares",
                "diluted_shares": "weighted_average_diluted_shares",
            }.get(field, field)
            add(metric_id, item, unit="₹ crore", source_statement=section_name)

    ratio_map = ratios.get("ratios") if isinstance(ratios.get("ratios"), dict) else {}
    for metric_id in (
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
        "dividend_per_share",
        "payout_ratio",
    ):
        add(metric_id, ratio_map.get(metric_id), unit=str((ratio_map.get(metric_id) or {}).get("unit") or ""), source_statement="financial_ratios", derived=True)
    return fallback


def _eligible_years_for_company_memory(company_root: Path) -> List[str]:
    if not company_root.exists():
        return []
    manifest = build_company_year_eligibility_manifest(company=company_root.name, company_root=company_root)
    return _sort_years(manifest.get("eligible_years", []))


def load_financial_truth_by_year(*, company_root: Path, years: Optional[Sequence[str]] = None) -> Dict[str, Dict[str, Any]]:
    if years is None:
        years = _eligible_years_for_company_memory(company_root)
    years = _sort_years(years)
    bundles: Dict[str, Dict[str, Any]] = {}
    for year in years:
        financial_root = company_root / year / "financials"
        bundle = {
            "year": year,
            "financial_root": financial_root,
            "registry": _load_optional_json(financial_root / "financial_fact_registry.json"),
            "reconciliation": _load_optional_json(financial_root / "financial_truth_reconciliation_report.json"),
            "basis_resolution": _load_optional_json(financial_root / "financial_basis_resolution.json"),
            "quarantine": _load_optional_json(financial_root / "financial_artifact_quarantine_report.json"),
            "ratios": _load_optional_json(financial_root / "financial_ratios.json"),
            "growth": _load_optional_json(financial_root / "financial_growth.json"),
            "normalized": _load_optional_json(financial_root / "normalized_fundamentals.json"),
            "shareholding": _load_optional_json(financial_root / "shareholding_pattern.json"),
        }
        bundle["fact_map"] = _gather_facts(bundle["registry"]) if bundle["registry"] else {}
        if not bundle["fact_map"]:
            bundle["fact_map"] = {metric_id: [fact] for metric_id, fact in _fallback_fact_map(bundle).items()}
        bundles[year] = bundle
    return bundles


def build_financial_memory_manifest(*, company: str, company_root: Path) -> Dict[str, Any]:
    eligibility = build_company_year_eligibility_manifest(company=company, company_root=company_root)
    eligible_years = _sort_years(eligibility.get("eligible_years", []))
    years_scanned = _sort_years((eligibility.get("years") or {}).keys())
    bundles = load_financial_truth_by_year(company_root=company_root, years=eligible_years)
    years_with_registry: List[str] = []
    years_with_partial: List[str] = []
    years_missing: List[str] = []
    source_artifacts_used_by_year: Dict[str, List[str]] = {}
    source_artifacts_missing_by_year: Dict[str, List[str]] = {}
    quarantined_domains_by_year: Dict[str, List[str]] = {}
    unreliable_metrics_by_year: Dict[str, List[str]] = {}
    warnings: List[str] = []
    limitations: List[str] = []
    excluded_company_years: Dict[str, Dict[str, Any]] = {}

    for year, item in (eligibility.get("years") or {}).items():
        if year in eligible_years:
            continue
        excluded_company_years[year] = {
            "status": item.get("status"),
            "reason": item.get("reason"),
            "missing_required_artifacts": list(item.get("missing_required_artifacts", [])),
            "available_artifacts": list(item.get("available_artifacts", [])),
        }

    for year, bundle in bundles.items():
        if bundle.get("registry"):
            years_with_registry.append(year)
        elif any(bundle.get(name) for name in ("normalized", "ratios", "growth")):
            years_with_partial.append(year)
        else:
            years_missing.append(year)

        used: List[str] = []
        missing: List[str] = []
        for filename in TRUTH_PRIORITY_FILES:
            path = bundle["financial_root"] / filename
            if path.exists():
                used.append(filename)
            else:
                missing.append(filename)
        source_artifacts_used_by_year[year] = used
        source_artifacts_missing_by_year[year] = missing

        reconciliation = bundle.get("reconciliation") or {}
        unreliable_metrics_by_year[year] = sorted(set(
            [str(item) for item in reconciliation.get("unreliable_metrics", []) if str(item).strip()]
            + [str(item) for item in reconciliation.get("invalid_metrics", []) if str(item).strip()]
        ))

        quarantine = bundle.get("quarantine") or {}
        domains: List[str] = []
        for artifact in quarantine.get("quarantined_artifacts", []) if isinstance(quarantine.get("quarantined_artifacts"), list) else []:
            if isinstance(artifact, dict):
                _append_unique(domains, str(artifact.get("artifact_name") or artifact.get("name") or "unknown_artifact"))
        quarantined_domains_by_year[year] = domains
        if not bundle.get("registry") and year not in years_missing:
            _append_unique(warnings, f"{year}: financial_fact_registry.json missing; company-memory falls back to partial yearly artifacts.")

    status = "pass"
    if years_missing and not years_with_registry and not years_with_partial:
        status = "invalid"
    elif years_missing:
        status = "partial"
    elif any(unreliable_metrics_by_year.values()) or any(quarantined_domains_by_year.values()) or years_with_partial:
        status = "warning"

    if len(years_with_registry) <= 1 and years_with_registry:
        _append_unique(limitations, "Only one year has a financial truth registry, so multi-year comparability is limited.")
    if not years_with_registry:
        _append_unique(limitations, "No year has a financial truth registry yet; company-memory is using partial yearly financial artifacts.")
    if excluded_company_years:
        _append_unique(
            limitations,
            "Some fiscal-year folders were excluded by canonical company-year eligibility: "
            + ", ".join(_sort_years(excluded_company_years.keys())),
        )

    readiness = {
        "usable_registry_years": years_with_registry,
        "partial_years": years_with_partial,
        "missing_years": years_missing,
        "ready_for_trends": bool(years_with_registry or years_with_partial),
        "ready_for_multi_year_comparisons": len(years_with_registry) >= 2,
    }
    return {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years_scanned": years_scanned,
        "years_with_financial_truth_registry": years_with_registry,
        "years_with_partial_financials": years_with_partial,
        "years_missing_financials": years_missing,
        "company_year_eligibility": eligibility,
        "excluded_company_years": excluded_company_years,
        "source_artifacts_used_by_year": source_artifacts_used_by_year,
        "source_artifacts_missing_by_year": source_artifacts_missing_by_year,
        "quarantined_domains_by_year": quarantined_domains_by_year,
        "unreliable_metrics_by_year": unreliable_metrics_by_year,
        "financial_memory_status": status,
        "downstream_readiness": readiness,
        "warnings": warnings,
        "limitations": limitations,
    }


def build_financial_truth_pack(*, company: str, company_root: Path) -> Dict[str, Any]:
    bundles = load_financial_truth_by_year(company_root=company_root)
    years = _sort_years(bundles.keys())
    memory_artifacts = _load_company_memory_artifacts(company_root)
    module_hydration = _hydrate_module_metrics(company_root)
    usable_current_metrics: List[Dict[str, Any]] = []
    usable_derived_metrics: List[Dict[str, Any]] = []
    partial_metrics: List[Dict[str, Any]] = []
    precise_missing_metrics: List[Dict[str, Any]] = []
    unreliable_metrics: List[Dict[str, Any]] = []
    invalid_metrics: List[Dict[str, Any]] = []
    allowed_warnings: List[str] = []
    blocked_warnings: List[Dict[str, Any]] = []
    rewritten_warnings: List[str] = []
    questions: List[str] = []
    trend_durability_limits: List[str] = []
    precision_limits: List[str] = []
    derived_not_explicitly_reported: List[Dict[str, Any]] = []
    source_provenance: List[str] = []
    unit_validation_warnings: List[str] = []
    unit_validation_failures: List[str] = []
    recomputed_metrics: List[Dict[str, Any]] = []

    for year in years:
        bundle = bundles[year]
        registry = bundle.get("registry") or {}
        for field_name, target in (
            ("available_facts", usable_current_metrics),
            ("derived_facts", usable_derived_metrics),
            ("partial_facts", partial_metrics),
            ("precise_missing_facts", precise_missing_metrics),
            ("unreliable_facts", unreliable_metrics),
            ("invalid_facts", invalid_metrics),
        ):
            for item in registry.get(field_name, []) if isinstance(registry.get(field_name), list) else []:
                if isinstance(item, dict):
                    target.append(item)
                    if field_name == "derived_facts":
                        derived_not_explicitly_reported.append(_compact_metric_summary(item))
        reconciliation = bundle.get("reconciliation") or {}
        for warning in reconciliation.get("warnings", []) if isinstance(reconciliation.get("warnings"), list) else []:
            _append_unique(allowed_warnings, str(warning))
        for normalization in reconciliation.get("warning_normalizations", []) if isinstance(reconciliation.get("warning_normalizations"), list) else []:
            if isinstance(normalization, dict):
                blocked_warnings.append(dict(normalization))
                _append_unique(rewritten_warnings, str(normalization.get("normalized_warning") or ""))
        for item in registry.get("precise_missing_facts", []) if isinstance(registry.get("precise_missing_facts"), list) else []:
            if isinstance(item, dict):
                _append_unique(questions, f"{year}: {item.get('notes', ['Missing financial detail requires follow-up.'])[0] if isinstance(item.get('notes'), list) and item.get('notes') else item.get('metric_name')}")
        basis_resolution = bundle.get("basis_resolution") or {}
        for warning in basis_resolution.get("warnings", []) if isinstance(basis_resolution.get("warnings"), list) else []:
            _append_unique(trend_durability_limits, str(warning))
        quarantine = bundle.get("quarantine") or {}
        for warning in quarantine.get("warnings", []) if isinstance(quarantine.get("warnings"), list) else []:
            _append_unique(precision_limits, str(warning))
        for artifact_name in YEAR_LEVEL_TRUTH_FILES:
            if (bundle["financial_root"] / artifact_name).exists():
                _append_unique(source_provenance, f"{year}/financials/{artifact_name}")

    usable_current_metrics.extend(module_hydration["usable_current_metrics"])
    usable_derived_metrics.extend(module_hydration["usable_derived_metrics"])
    partial_metrics.extend(module_hydration["partial_metrics"])
    precise_missing_metrics.extend(module_hydration.get("precise_missing_metrics", []))
    unreliable_metrics.extend(module_hydration.get("unreliable_metrics", []))
    invalid_metrics.extend(module_hydration.get("invalid_metrics", []))
    for item in module_hydration["usable_derived_metrics"]:
        derived_not_explicitly_reported.append(_compact_metric_summary(item))
    for question in module_hydration["investor_relevant_questions"]:
        _append_unique(questions, question)
    for limit in module_hydration["precision_limits"]:
        _append_unique(precision_limits, limit)
    for provenance in module_hydration["source_provenance"]:
        _append_unique(source_provenance, provenance)
    for warning in module_hydration.get("unit_validation_warnings", []):
        _append_unique(unit_validation_warnings, warning)
    for failure in module_hydration.get("unit_validation_failures", []):
        _append_unique(unit_validation_failures, failure)
    for item in module_hydration.get("recomputed_metrics", []):
        if item not in recomputed_metrics:
            recomputed_metrics.append(item)

    truth_metric_names = (
        _iter_metric_names(usable_current_metrics)
        + _iter_metric_names(usable_derived_metrics)
        + _iter_metric_names(partial_metrics)
        + _iter_metric_names(unreliable_metrics)
        + _iter_metric_names(invalid_metrics)
    )
    filtered_allowed: List[str] = []
    for warning in allowed_warnings:
        trigger = _warning_block_match(warning, truth_metric_names)
        if trigger:
            blocked_warnings.append(
                {
                    "original_warning": str(warning),
                    "normalized_warning": _rewrite_warning_text(str(warning), trigger),
                    "reason": "hydrated_financial_truth_available",
                }
            )
            _append_unique(rewritten_warnings, _rewrite_warning_text(str(warning), trigger))
        else:
            _append_unique(filtered_allowed, str(warning))
    allowed_warnings = filtered_allowed

    checked, used, missing = _source_status(company_root=company_root, years=years)
    manifest = memory_artifacts.get("financial_memory_manifest.json") or {}
    investor_modules_manifest = memory_artifacts.get(MODULE_FILENAMES["investor_financial_modules_manifest"]) or {}
    usable_domains = list(investor_modules_manifest.get("usable_domains", [])) if isinstance(investor_modules_manifest.get("usable_domains"), list) else []
    limited_domains = list(investor_modules_manifest.get("limited_domains", [])) if isinstance(investor_modules_manifest.get("limited_domains"), list) else []
    blocked_domains = list(investor_modules_manifest.get("blocked_domains", [])) if isinstance(investor_modules_manifest.get("blocked_domains"), list) else []

    module_files_present = any(
        (company_root / "company_memory" / "financials" / MODULE_DIRNAME / filename).exists()
        for filename in MODULE_FILENAMES.values()
        if filename != MODULE_FILENAMES["investor_financial_modules_manifest"]
    )
    hydrated_sections_present = any(
        (
            usable_current_metrics,
            usable_derived_metrics,
            derived_not_explicitly_reported,
            precision_limits,
            questions,
        )
    )
    panel_status = "pass"
    panel_reason = "Hydrated financial truth is available for investor-panel use."
    if module_files_present and not hydrated_sections_present:
        panel_status = "invalid"
        panel_reason = "Investor financial modules exist, but financial truth hydration produced no usable downstream sections."
        _append_unique(blocked_domains, "all_financial_domains")
    elif not years:
        panel_status = "missing"
        panel_reason = "No yearly financial truth artifacts were discovered."
    elif not usable_current_metrics and not usable_derived_metrics and not partial_metrics:
        panel_status = "partial"
        panel_reason = "Financial truth is available only through missing, unreliable, or quarantined signals."
    elif limited_domains or allowed_warnings:
        panel_status = "warning"
        panel_reason = "Financial truth is usable, but some downstream domains still carry limitations."

    precise_missing_metric_names = {str(item.get("metric_id") or item.get("canonical_metric") or "").strip().lower() for item in precise_missing_metrics if isinstance(item, dict)}
    for collection in (usable_current_metrics, usable_derived_metrics, partial_metrics, unreliable_metrics, invalid_metrics):
        for item in collection:
            metric_name = str(item.get("metric_id") or item.get("canonical_metric") or "").strip().lower()
            if metric_name and metric_name in precise_missing_metric_names:
                precise_missing_metric_names.discard(metric_name)
    precise_missing_metrics = [
        item for item in precise_missing_metrics
        if str(item.get("metric_id") or item.get("canonical_metric") or "").strip().lower() in precise_missing_metric_names
    ]

    return {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years_covered": years,
        "source_files_checked": checked,
        "source_files_used": used,
        "source_files_missing": missing,
        "usable_current_metrics": usable_current_metrics,
        "usable_derived_metrics": usable_derived_metrics,
        "partial_metrics": partial_metrics,
        "precise_missing_metrics": precise_missing_metrics,
        "unreliable_metrics": unreliable_metrics,
        "invalid_or_quarantined_metrics": invalid_metrics,
        "derived_not_explicitly_reported": derived_not_explicitly_reported,
        "trend_durability_limits": trend_durability_limits,
        "precision_limits": precision_limits,
        "financial_warnings_allowed_downstream": allowed_warnings,
        "financial_warnings_blocked_downstream": blocked_warnings,
        "financial_warnings_rewritten": rewritten_warnings,
        "investor_relevant_questions": questions,
        "financial_panel_status": panel_status,
        "financial_panel_status_reason": panel_reason,
        "financial_panel_usable_domains": usable_domains,
        "financial_panel_limited_domains": limited_domains,
        "financial_panel_blocked_domains": blocked_domains,
        "source_provenance": source_provenance,
        "unit_validation_warnings": unit_validation_warnings,
        "unit_validation_failures": unit_validation_failures,
        "recomputed_metrics": recomputed_metrics,
    }
