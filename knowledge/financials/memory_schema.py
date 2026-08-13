from __future__ import annotations

from typing import Any, Dict, List


ALLOWED_STATUS = {"pass", "warning", "fail"}
ALLOWED_BASIS = {"standalone", "consolidated", "mixed", "unknown"}
ALLOWED_BASIS_CONSISTENCY = {"consistent", "mixed", "unknown"}


def _require_list(payload: Dict[str, Any], key: str, errors: List[str]) -> None:
    if key in payload and not isinstance(payload.get(key), list):
        errors.append(f"{key} must be a list")


def _require_dict(payload: Dict[str, Any], key: str, errors: List[str]) -> None:
    if key in payload and not isinstance(payload.get(key), dict):
        errors.append(f"{key} must be an object")


def validate_financial_year_index_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial year index payload must be an object"]
    for key in (
        "company",
        "generated_at",
        "years_discovered",
        "years_used",
        "years_skipped",
        "year_status",
        "warnings",
        "limitations",
    ):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    for key in ("years_discovered", "years_used", "years_skipped", "warnings", "limitations"):
        _require_list(payload, key, errors)
    _require_dict(payload, "year_status", errors)
    for year, item in (payload.get("year_status") or {}).items():
        if not isinstance(item, dict):
            errors.append(f"year_status.{year} must be an object")
            continue
        for field in (
            "financials_available",
            "validation_status",
            "reconciliation_status",
            "quality_status",
            "basis_used",
            "warnings",
            "limitations",
        ):
            if field not in item:
                errors.append(f"year_status.{year} missing required field: {field}")
        for status_field in ("validation_status", "reconciliation_status", "quality_status"):
            value = item.get(status_field)
            if value and value not in ALLOWED_STATUS:
                errors.append(f"year_status.{year}.{status_field} invalid: {value}")
        basis = item.get("basis_used")
        if basis and basis not in ALLOWED_BASIS:
            errors.append(f"year_status.{year}.basis_used invalid: {basis}")
        if "warnings" in item and not isinstance(item.get("warnings"), list):
            errors.append(f"year_status.{year}.warnings must be a list")
        if "limitations" in item and not isinstance(item.get("limitations"), list):
            errors.append(f"year_status.{year}.limitations must be a list")
    return errors


def validate_financial_quality_evolution_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial quality evolution payload must be an object"]
    for key in (
        "company",
        "generated_at",
        "years_covered",
        "evolution",
        "recurring_strengths",
        "recurring_concerns",
        "improving_signals",
        "deteriorating_signals",
        "missing_data_patterns",
        "warnings",
        "limitations",
    ):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    _require_list(payload, "years_covered", errors)
    _require_dict(payload, "evolution", errors)
    for key in (
        "recurring_strengths",
        "recurring_concerns",
        "improving_signals",
        "deteriorating_signals",
        "missing_data_patterns",
        "warnings",
        "limitations",
    ):
        _require_list(payload, key, errors)
    return errors


def validate_capital_allocation_financial_timeline_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["capital allocation financial timeline payload must be an object"]
    for key in (
        "company",
        "generated_at",
        "years_covered",
        "timeline",
        "dividend_pattern",
        "capex_pattern",
        "fcf_pattern",
        "dilution_or_share_issue_pattern",
        "debt_pattern",
        "warnings",
        "limitations",
    ):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    _require_list(payload, "years_covered", errors)
    _require_list(payload, "timeline", errors)
    for key in (
        "dividend_pattern",
        "capex_pattern",
        "fcf_pattern",
        "dilution_or_share_issue_pattern",
        "debt_pattern",
    ):
        _require_dict(payload, key, errors)
    _require_list(payload, "warnings", errors)
    _require_list(payload, "limitations", errors)
    return errors


def validate_ownership_evolution_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["ownership evolution payload must be an object"]
    for key in (
        "company",
        "generated_at",
        "years_covered",
        "promoter_holding",
        "pledge",
        "fii",
        "dii",
        "mutual_funds",
        "public",
        "institutional_signal",
        "warnings",
        "limitations",
    ):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    for key in ("years_covered", "promoter_holding", "pledge", "fii", "dii", "mutual_funds", "public", "warnings", "limitations"):
        _require_list(payload, key, errors)
    _require_dict(payload, "institutional_signal", errors)
    return errors


def validate_financial_memory_summary_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial memory summary payload must be an object"]
    for key in (
        "company",
        "generated_at",
        "status",
        "years_covered",
        "basis_used",
        "summary",
        "key_strengths",
        "key_concerns",
        "missing_data",
        "investor_questions",
        "warnings",
        "limitations",
        "source_manifest",
    ):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    status = payload.get("status")
    if status is not None and status not in ALLOWED_STATUS:
        errors.append(f"invalid status: {status}")
    basis = payload.get("basis_used")
    if basis is not None and basis not in ALLOWED_BASIS:
        errors.append(f"invalid basis_used: {basis}")
    _require_list(payload, "years_covered", errors)
    _require_dict(payload, "summary", errors)
    _require_dict(payload, "source_manifest", errors)
    for key in ("key_strengths", "key_concerns", "missing_data", "investor_questions", "warnings", "limitations"):
        _require_list(payload, key, errors)
    summary = payload.get("summary") or {}
    if isinstance(summary, dict):
        for key in (
            "scale_pattern",
            "profitability_pattern",
            "return_pattern",
            "cash_conversion_pattern",
            "balance_sheet_pattern",
            "working_capital_pattern",
            "per_share_pattern",
            "capital_allocation_pattern",
            "ownership_pattern",
        ):
            if key not in summary:
                errors.append(f"summary missing required field: {key}")
            elif not isinstance(summary.get(key), list):
                errors.append(f"summary.{key} must be a list")
    source_manifest = payload.get("source_manifest") or {}
    if isinstance(source_manifest, dict):
        basis_policy = source_manifest.get("basis_policy") or {}
        if basis_policy:
            consistency = basis_policy.get("basis_consistency")
            if consistency and consistency not in ALLOWED_BASIS_CONSISTENCY:
                errors.append(f"source_manifest.basis_policy.basis_consistency invalid: {consistency}")
    return errors


def validate_financial_memory_manifest_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial memory manifest payload must be an object"]
    for key in (
        "company",
        "generated_at",
        "years_scanned",
        "years_with_financial_truth_registry",
        "years_with_partial_financials",
        "years_missing_financials",
        "source_artifacts_used_by_year",
        "source_artifacts_missing_by_year",
        "quarantined_domains_by_year",
        "unreliable_metrics_by_year",
        "financial_memory_status",
        "downstream_readiness",
        "warnings",
        "limitations",
    ):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    for key in (
        "years_scanned",
        "years_with_financial_truth_registry",
        "years_with_partial_financials",
        "years_missing_financials",
        "warnings",
        "limitations",
    ):
        _require_list(payload, key, errors)
    for key in (
        "source_artifacts_used_by_year",
        "source_artifacts_missing_by_year",
        "quarantined_domains_by_year",
        "unreliable_metrics_by_year",
        "downstream_readiness",
    ):
        _require_dict(payload, key, errors)
    status = payload.get("financial_memory_status")
    if status and status not in {"pass", "warning", "partial", "invalid"}:
        errors.append(f"financial_memory_status invalid: {status}")
    return errors


def validate_financial_truth_pack_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["financial truth pack payload must be an object"]
    required_list_fields = (
        "company",
        "generated_at",
        "years_covered",
        "source_files_checked",
        "source_files_used",
        "source_files_missing",
        "usable_current_metrics",
        "usable_derived_metrics",
        "partial_metrics",
        "precise_missing_metrics",
        "unreliable_metrics",
        "invalid_or_quarantined_metrics",
        "derived_not_explicitly_reported",
        "trend_durability_limits",
        "precision_limits",
        "financial_warnings_allowed_downstream",
        "financial_warnings_blocked_downstream",
        "financial_warnings_rewritten",
        "investor_relevant_questions",
        "financial_panel_usable_domains",
        "financial_panel_limited_domains",
        "financial_panel_blocked_domains",
        "source_provenance",
        "unit_validation_warnings",
        "unit_validation_failures",
        "recomputed_metrics",
    )
    for key in required_list_fields:
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
        elif key not in {"company", "generated_at"} and not isinstance(payload.get(key), list):
            errors.append(f"{key} must be a list")
    for key in ("financial_panel_status", "financial_panel_status_reason"):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")
    if payload.get("financial_panel_status") not in {"pass", "warning", "partial", "invalid", "missing"}:
        errors.append("financial_panel_status must be pass|warning|partial|invalid|missing")
    return errors
