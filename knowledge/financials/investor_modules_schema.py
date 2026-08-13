from __future__ import annotations

from typing import Any, Dict, List


MODULE_STATUS = {"pass", "warning", "partial", "invalid", "skipped"}
OWNER_EARNINGS_PRECISION = {"precise", "estimate_available", "partial", "unavailable"}
ROI_MEASURABILITY = {"measurable", "partially_measurable", "not_yet_measurable", "unreliable"}
WORKING_CAPITAL_STATUS = {"healthy", "watch", "stretched", "severe", "insufficient_data"}
CONVERSION_STATUS = {"strong", "watch", "stretched", "insufficient_data"}
DILUTION_STATUS = {
    "no_material_dilution_detected",
    "dilution_warning",
    "comparability_partial",
    "insufficient_data",
    "unreliable",
}


def _require_list(payload: Dict[str, Any], key: str, errors: List[str]) -> None:
    if key in payload and not isinstance(payload.get(key), list):
        errors.append(f"{key} must be a list")


def _require_dict(payload: Dict[str, Any], key: str, errors: List[str]) -> None:
    if key in payload and not isinstance(payload.get(key), dict):
        errors.append(f"{key} must be an object")


def validate_owner_earnings_bridge_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["owner earnings bridge payload must be an object"]
    for key in ("company", "generated_at", "years_covered", "bridges", "warnings", "limitations"):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    for key in ("years_covered", "bridges", "warnings", "limitations"):
        _require_list(payload, key, errors)
    for index, item in enumerate(payload.get("bridges", [])):
        if not isinstance(item, dict):
            errors.append(f"bridges[{index}] must be an object")
            continue
        status = item.get("owner_earnings_precision_status")
        if status and status not in OWNER_EARNINGS_PRECISION:
            errors.append(f"bridges[{index}].owner_earnings_precision_status invalid: {status}")
    return errors


def validate_capital_allocation_roi_ledger_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["capital allocation roi ledger payload must be an object"]
    for key in ("company", "generated_at", "years_covered", "entries", "warnings", "limitations"):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    for key in ("years_covered", "entries", "warnings", "limitations"):
        _require_list(payload, key, errors)
    for index, item in enumerate(payload.get("entries", [])):
        if not isinstance(item, dict):
            errors.append(f"entries[{index}] must be an object")
            continue
        status = item.get("roi_measurability_status")
        if status and status not in ROI_MEASURABILITY:
            errors.append(f"entries[{index}].roi_measurability_status invalid: {status}")
    return errors


def validate_working_capital_quality_drilldown_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["working capital quality drilldown payload must be an object"]
    for key in ("company", "generated_at", "years_covered", "drilldown", "warnings", "limitations"):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    for key in ("years_covered", "drilldown", "warnings", "limitations"):
        _require_list(payload, key, errors)
    for index, item in enumerate(payload.get("drilldown", [])):
        if not isinstance(item, dict):
            errors.append(f"drilldown[{index}] must be an object")
            continue
        status = item.get("working_capital_intensity_status")
        if status and status not in WORKING_CAPITAL_STATUS:
            errors.append(f"drilldown[{index}].working_capital_intensity_status invalid: {status}")
    return errors


def validate_order_revenue_cash_conversion_tracker_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["order revenue cash conversion tracker payload must be an object"]
    for key in ("company", "generated_at", "years_covered", "tracker", "warnings", "limitations"):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    for key in ("years_covered", "tracker", "warnings", "limitations"):
        _require_list(payload, key, errors)
    for index, item in enumerate(payload.get("tracker", [])):
        if not isinstance(item, dict):
            errors.append(f"tracker[{index}] must be an object")
            continue
        status = item.get("conversion_status")
        if status and status not in CONVERSION_STATUS:
            errors.append(f"tracker[{index}].conversion_status invalid: {status}")
    return errors


def validate_per_share_compounding_analysis_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["per share compounding analysis payload must be an object"]
    for key in ("company", "generated_at", "years_covered", "analysis", "warnings", "limitations"):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    for key in ("years_covered", "analysis", "warnings", "limitations"):
        _require_list(payload, key, errors)
    for index, item in enumerate(payload.get("analysis", [])):
        if not isinstance(item, dict):
            errors.append(f"analysis[{index}] must be an object")
            continue
        status = item.get("dilution_status")
        if status and status not in DILUTION_STATUS:
            errors.append(f"analysis[{index}].dilution_status invalid: {status}")
    return errors


def validate_investor_financial_modules_manifest_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["investor financial modules manifest payload must be an object"]
    for key in (
        "company",
        "generated_at",
        "modules_run",
        "module_statuses",
        "source_truth_pack_used",
        "usable_domains",
        "limited_domains",
        "blocked_domains",
        "warnings",
        "limitations",
        "recommended_next_investor_questions",
        "investor_financial_intelligence_pack",
    ):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    for key in (
        "modules_run",
        "usable_domains",
        "limited_domains",
        "blocked_domains",
        "warnings",
        "limitations",
        "recommended_next_investor_questions",
    ):
        _require_list(payload, key, errors)
    for key in ("module_statuses", "source_truth_pack_used", "investor_financial_intelligence_pack"):
        _require_dict(payload, key, errors)
    statuses = payload.get("module_statuses") or {}
    if isinstance(statuses, dict):
        for name, status in statuses.items():
            if status not in MODULE_STATUS:
                errors.append(f"module_statuses.{name} invalid: {status}")
    return errors
