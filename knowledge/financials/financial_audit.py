from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .attribution_schema import validate_financial_driver_attribution_payload
from .audit_schema import (
    FinancialAuditCheck,
    FinancialAuditReport,
    validate_financial_audit_payload,
)
from .corporate_action_schema import validate_corporate_actions_payload
from .discovery_schema import validate_financial_discovery_payload
from .extraction_schema import validate_financial_extraction_payload
from .growth_schema import validate_financial_growth_payload
from .quality_schema import validate_financial_quality_payload
from .reconciliation_schema import validate_financial_reconciliation_payload
from .ratio_schema import validate_financial_ratio_report_payload
from .shareholding_schema import validate_shareholding_payload
from .memory_schema import (
    validate_capital_allocation_financial_timeline_payload,
    validate_financial_memory_summary_payload,
    validate_financial_quality_evolution_payload,
    validate_financial_year_index_payload,
    validate_ownership_evolution_payload,
)
from .trend_schema import validate_financial_trend_payload
from .validation_schema import validate_financial_validation_report_payload


YEAR_REQUIRED_ARTIFACTS = [
    "financial_discovery.json",
    "raw_financial_tables.json",
    "normalized_fundamentals.json",
    "financial_validation_report.json",
    "financial_reconciliation_report.json",
    "financial_ratios.json",
    "financial_growth.json",
    "corporate_actions.json",
    "shareholding_pattern.json",
]

COMPANY_MEMORY_REQUIRED_ARTIFACTS = [
    "financial_year_index.json",
    "financial_trends.json",
    "financial_quality_evolution.json",
    "capital_allocation_financial_timeline.json",
    "ownership_evolution.json",
    "financial_memory_summary.json",
    "financial_quality_summary.json",
    "financial_driver_attribution.json",
]


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _parse_generated_at(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _append_unique(items: List[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


FORBIDDEN_RECOMMENDATION_PATTERNS = (
    re.compile(r"\bbuy\b", re.IGNORECASE),
    re.compile(r"\bsell\b", re.IGNORECASE),
    re.compile(r"\bhold\b", re.IGNORECASE),
)


def _contains_forbidden_recommendation_language(text: str) -> bool:
    return any(pattern.search(text) for pattern in FORBIDDEN_RECOMMENDATION_PATTERNS)


def _roundtrip_dict(value: Any) -> Dict[str, Any]:
    if is_dataclass(value):
        if hasattr(value, "to_dict"):
            return value.to_dict()
        return asdict(value)
    if isinstance(value, dict):
        return json.loads(json.dumps(value, ensure_ascii=False))
    raise TypeError("expected dataclass or dict payload")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _contains_source_chunk(value: Any) -> bool:
    return '"source_chunk"' in json.dumps(value, ensure_ascii=False)


def _safe_status(failures: Sequence[str], warnings: Sequence[str]) -> str:
    if failures:
        return "fail"
    if warnings:
        return "warning"
    return "pass"


def _check(
    checks: List[FinancialAuditCheck],
    *,
    name: str,
    status: str,
    details: str,
) -> None:
    checks.append(FinancialAuditCheck(check_name=name, status=status, details=details))


def _artifact_contracts() -> Dict[str, Callable[[Dict[str, Any]], List[str]]]:
    return {
        "financial_discovery.json": validate_financial_discovery_payload,
        "raw_financial_tables.json": validate_financial_extraction_payload,
        "financial_validation_report.json": validate_financial_validation_report_payload,
        "financial_reconciliation_report.json": validate_financial_reconciliation_payload,
        "financial_ratios.json": validate_financial_ratio_report_payload,
        "financial_growth.json": validate_financial_growth_payload,
        "corporate_actions.json": validate_corporate_actions_payload,
        "shareholding_pattern.json": validate_shareholding_payload,
        "financial_trends.json": validate_financial_trend_payload,
        "financial_year_index.json": validate_financial_year_index_payload,
        "financial_quality_evolution.json": validate_financial_quality_evolution_payload,
        "capital_allocation_financial_timeline.json": validate_capital_allocation_financial_timeline_payload,
        "ownership_evolution.json": validate_ownership_evolution_payload,
        "financial_memory_summary.json": validate_financial_memory_summary_payload,
        "financial_quality_summary.json": validate_financial_quality_payload,
        "financial_driver_attribution.json": validate_financial_driver_attribution_payload,
    }


def _record_artifact_presence(
    *,
    artifact_dir: Path,
    required_artifacts: Sequence[str],
    checks: List[FinancialAuditCheck],
    failures: List[str],
    present_artifacts: List[str],
    missing_artifacts: List[str],
) -> None:
    for filename in required_artifacts:
        path = artifact_dir / filename
        if path.exists():
            present_artifacts.append(filename)
        else:
            missing_artifacts.append(filename)
            _append_unique(failures, f"Missing required artifact: {filename}")
    _check(
        checks,
        name="required_artifacts",
        status="fail" if missing_artifacts else "pass",
        details=(
            "All required financial artifacts are present."
            if not missing_artifacts
            else "Missing artifacts: " + ", ".join(missing_artifacts)
        ),
    )


def _validate_artifact_shapes(
    *,
    artifact_dir: Path,
    filenames: Sequence[str],
    checks: List[FinancialAuditCheck],
    failures: List[str],
    warnings: List[str],
) -> Dict[str, Dict[str, Any]]:
    payloads: Dict[str, Dict[str, Any]] = {}
    validators = _artifact_contracts()
    for filename in filenames:
        path = artifact_dir / filename
        if not path.exists():
            continue
        try:
            payload = _load_json(path)
        except json.JSONDecodeError as exc:
            _append_unique(failures, f"Malformed JSON in {filename}: {exc}")
            _check(
                checks,
                name=f"json:{filename}",
                status="fail",
                details=f"{filename} contains malformed JSON.",
            )
            continue
        payloads[filename] = payload
        validator = validators.get(filename)
        if validator is None:
            _check(
                checks,
                name=f"contract:{filename}",
                status="pass",
                details=f"No strict validator registered for {filename}; JSON loaded successfully.",
            )
            continue
        errors = validator(payload)
        if errors:
            for error in errors:
                _append_unique(failures, f"{filename}: {error}")
            _check(
                checks,
                name=f"contract:{filename}",
                status="fail",
                details=f"{filename} failed contract validation.",
            )
        else:
            _check(
                checks,
                name=f"contract:{filename}",
                status="pass",
                details=f"{filename} passed contract validation.",
            )
    if not payloads and filenames:
        _append_unique(warnings, "No financial artifacts were available to validate.")
    return payloads


def _check_stale_saved_audit(
    *,
    artifact_dir: Path,
    payloads: Dict[str, Dict[str, Any]],
    checks: List[FinancialAuditCheck],
    warnings: List[str],
) -> None:
    audit_path = artifact_dir / "financial_audit_report.json"
    if not audit_path.exists():
        _check(
            checks,
            name="saved_audit_freshness",
            status="pass",
            details="No existing financial_audit_report.json was present before this audit run.",
        )
        return
    try:
        audit_payload = _load_json(audit_path)
    except json.JSONDecodeError:
        _append_unique(warnings, "Existing financial_audit_report.json is malformed; freshness could not be verified.")
        _check(
            checks,
            name="saved_audit_freshness",
            status="warning",
            details="Existing financial_audit_report.json is malformed.",
        )
        return
    audit_generated_at = _parse_generated_at(audit_payload.get("generated_at"))
    if audit_generated_at is None:
        _append_unique(warnings, "Existing financial_audit_report.json has no valid generated_at timestamp.")
        _check(
            checks,
            name="saved_audit_freshness",
            status="warning",
            details="Existing financial_audit_report.json has no valid generated_at timestamp.",
        )
        return
    dependency_files = (
        "financial_reconciliation_report.json",
        "financial_ratios.json",
        "financial_growth.json",
        "corporate_actions.json",
    )
    stale_against: List[str] = []
    for filename in dependency_files:
        payload = payloads.get(filename)
        if not isinstance(payload, dict):
            continue
        dependency_generated_at = _parse_generated_at(payload.get("generated_at"))
        if dependency_generated_at and dependency_generated_at > audit_generated_at:
            stale_against.append(filename)
    if stale_against:
        _append_unique(
            warnings,
            "Existing financial_audit_report.json is stale relative to: " + ", ".join(stale_against),
        )
        _check(
            checks,
            name="saved_audit_freshness",
            status="warning",
            details="Existing financial_audit_report.json is older than: " + ", ".join(stale_against),
        )
        return
    _check(
        checks,
        name="saved_audit_freshness",
        status="pass",
        details="Existing financial_audit_report.json is at least as recent as key dependent artifacts.",
    )


def _normalized_entries(normalized_payload: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    entries: List[Tuple[str, Dict[str, Any]]] = []
    for section_name in ("profit_and_loss", "balance_sheet", "cash_flow", "share_data"):
        section = normalized_payload.get(section_name)
        if not isinstance(section, dict):
            continue
        for field_name, entry in section.items():
            if isinstance(entry, dict):
                entries.append((f"{section_name}.{field_name}", entry))
    return entries


def _normalized_value_missing_crore(path: str, entry: Dict[str, Any]) -> bool:
    raw_value = entry.get("value_original")
    if raw_value in (None, "", []):
        return False
    field_name = str(entry.get("canonical_field") or path.split(".")[-1])
    non_monetary_fields = {
        "shares_outstanding",
        "weighted_avg_shares",
        "diluted_shares",
        "face_value",
        "book_value_per_share",
        "tangible_book_value_per_share",
        "eps_basic",
        "eps_diluted",
    }
    if field_name in non_monetary_fields:
        return False
    return entry.get("value_crore") is None


def _fcf_integrity_issue(entry: Dict[str, Any]) -> str | None:
    raw_value = entry.get("value_original")
    if raw_value in (None, "", []) and entry.get("value_crore") is None:
        return None
    if entry.get("derived") is True:
        if entry.get("value_crore") is None:
            return None
        if not entry.get("formula") or not isinstance(entry.get("inputs_used"), dict) or not entry.get("inputs_used"):
            return "Derived FCF is missing formula or inputs_used."
        return None
    line_item = str(entry.get("source_line_item", "") or "").lower()
    if "free cash flow" not in line_item and "free cashflow" not in line_item and "fcf" not in line_item.split():
        return "FCF is populated from an unrelated source line."
    if entry.get("value_crore") is None:
        return "FCF is populated but not normalized to ₹ crore."
    return None


def _traceability_missing(entry: Dict[str, Any]) -> bool:
    return not entry.get("source_artifact") or entry.get("source_page") is None


def _check_year_fundamentals(
    *,
    company: str,
    year: str,
    payloads: Dict[str, Dict[str, Any]],
    checks: List[FinancialAuditCheck],
    failures: List[str],
    warnings: List[str],
) -> None:
    normalized = payloads.get("normalized_fundamentals.json") or {}
    validation = payloads.get("financial_validation_report.json") or {}
    reconciliation = payloads.get("financial_reconciliation_report.json") or {}
    ratios = payloads.get("financial_ratios.json") or {}
    growth = payloads.get("financial_growth.json") or {}
    corporate_actions = payloads.get("corporate_actions.json") or {}
    shareholding = payloads.get("shareholding_pattern.json") or {}

    revenue = ((normalized.get("profit_and_loss") or {}).get("revenue") or {})
    pat = ((normalized.get("profit_and_loss") or {}).get("pat") or {})
    cfo = ((normalized.get("cash_flow") or {}).get("cfo") or {})
    share_count = ((normalized.get("share_data") or {}).get("shares_outstanding") or {})

    for field_name, entry in (("revenue", revenue), ("pat", pat)):
        if entry.get("value_crore") is None:
            _append_unique(failures, f"{field_name.upper()} missing from normalized fundamentals.")
    _check(
        checks,
        name="required_core_metrics",
        status="fail" if any("missing from normalized fundamentals" in item for item in failures) else "pass",
        details="Revenue and PAT are present in normalized fundamentals." if not any(
            token in " ".join(failures) for token in ("REVENUE missing", "PAT missing")
        ) else "Revenue and/or PAT are missing from normalized fundamentals.",
    )

    missing_crore_paths = [
        path
        for path, entry in _normalized_entries(normalized)
        if _normalized_value_missing_crore(path, entry)
    ]
    if missing_crore_paths:
        _append_unique(
            failures,
            "Values not normalized to ₹ crore: " + ", ".join(sorted(missing_crore_paths)),
        )
    _check(
        checks,
        name="crore_normalization",
        status="fail" if missing_crore_paths else "pass",
        details=(
            "All populated monetary normalized fundamentals preserve value_crore."
            if not missing_crore_paths
            else "Missing value_crore for: " + ", ".join(sorted(missing_crore_paths))
        ),
    )

    fcf_entry = ((normalized.get("cash_flow") or {}).get("fcf") or {})
    fcf_issue = _fcf_integrity_issue(fcf_entry)
    if fcf_issue:
        _append_unique(failures, fcf_issue)
    _check(
        checks,
        name="fcf_integrity",
        status="fail" if fcf_issue else "pass",
        details=fcf_issue or "FCF is either cleanly derived, explicitly sourced, or intentionally absent.",
    )

    traceability_gaps = [
        path
        for path, entry in _normalized_entries(normalized)
        if entry.get("value_crore") is not None and _traceability_missing(entry)
    ]
    if traceability_gaps:
        _append_unique(
            failures,
            "Financial claims lack source traceability: " + ", ".join(sorted(traceability_gaps)),
        )
    _check(
        checks,
        name="source_traceability",
        status="fail" if traceability_gaps else "pass",
        details=(
            "Normalized financial claims preserve source artifact and page traceability."
            if not traceability_gaps
            else "Missing traceability for: " + ", ".join(sorted(traceability_gaps))
        ),
    )

    validation_status = str(validation.get("status") or "")
    if validation_status == "fail":
        _append_unique(failures, "financial_validation_report.json status is fail.")
    _check(
        checks,
        name="validation_gate",
        status="fail" if validation_status == "fail" else "pass",
        details=f"Validation status is {validation_status or 'missing'}.",
    )

    reconciliation_status = str(reconciliation.get("status") or "")
    if reconciliation_status not in {"pass", "warning"}:
        _append_unique(failures, f"financial_reconciliation_report.json status is {reconciliation_status or 'missing'}.")
    _check(
        checks,
        name="reconciliation_gate",
        status="fail" if reconciliation_status not in {"pass", "warning"} else "pass",
        details=f"Reconciliation status is {reconciliation_status or 'missing'}.",
    )

    ratio_items = ratios.get("ratios") if isinstance(ratios.get("ratios"), dict) else {}
    if reconciliation_status in {"pass", "warning"} and not ratio_items:
        _append_unique(failures, "Ratios missing after valid fundamentals.")
    _check(
        checks,
        name="ratio_artifact",
        status="fail" if reconciliation_status in {"pass", "warning"} and not ratio_items else "pass",
        details=(
            "Financial ratios are present."
            if ratio_items
            else "Financial ratios are missing or empty."
        ),
    )

    ratio_formula_gaps = []
    for ratio_name, item in ratio_items.items():
        if not isinstance(item, dict) or item.get("value") is None:
            continue
        if (
            not item.get("formula")
            or not isinstance(item.get("inputs_used"), list)
            or not isinstance(item.get("source_artifacts"), list)
        ):
            ratio_formula_gaps.append(ratio_name)
    if ratio_formula_gaps:
        _append_unique(
            failures,
            "Ratios lack formula/input/source provenance: " + ", ".join(sorted(ratio_formula_gaps)),
        )
    _check(
        checks,
        name="ratio_provenance",
        status="fail" if ratio_formula_gaps else "pass",
        details=(
            "Calculated ratios preserve formula, inputs_used, and source_artifacts metadata."
            if not ratio_formula_gaps
            else "Missing ratio provenance for: " + ", ".join(sorted(ratio_formula_gaps))
        ),
    )

    basis_values = {
        str(normalized.get("preferred_basis") or "").strip(),
        str(validation.get("basis_checked") or "").strip(),
        str(ratios.get("basis_used") or "").strip(),
        str(growth.get("basis_used") or "").strip(),
    } - {""}
    ratio_basis_warnings = [str(item) for item in ratios.get("basis_warnings", []) if str(item).strip()]
    growth_basis_warnings = [str(item) for item in growth.get("basis_warnings", []) if str(item).strip()]
    normalized_basis_warnings = [
        str(item)
        for item in ((normalized.get("basis_manifest") or {}).get("basis_warnings", []))
        if str(item).strip()
    ]
    explicit_basis_warning_present = bool(
        ratio_basis_warnings or growth_basis_warnings or normalized_basis_warnings
    )

    if str(validation.get("basis_checked") or "").strip() == "mixed" and not explicit_basis_warning_present:
        _append_unique(
            failures,
            "Material basis mixing detected without explicit basis warning in downstream financial artifacts.",
        )
        basis_status = "fail"
    elif len(basis_values) > 1 or {"mixed", "unknown"} & basis_values or explicit_basis_warning_present:
        _append_unique(
            warnings,
            "Basis mismatch across financial artifacts: " + ", ".join(sorted(basis_values)),
        )
        for warning in normalized_basis_warnings + ratio_basis_warnings + growth_basis_warnings:
            _append_unique(warnings, warning)
        basis_status = "warning"
    else:
        basis_status = "pass"
    _check(
        checks,
        name="basis_consistency",
        status=basis_status,
        details=" | ".join(sorted(basis_values)) if basis_values else "No basis information recorded.",
    )

    if cfo.get("value_crore") is None:
        _append_unique(warnings, "CFO missing from normalized fundamentals.")
    if (((growth.get("growth_metrics") or {}).get("fcf")) is None) and (
        ((ratios.get("ratios") or {}).get("fcf") or {}).get("value") is None
    ):
        _append_unique(warnings, "FCF missing from growth/ratio artifacts.")
    if ((ratios.get("ratios") or {}).get("roce") or {}).get("value") is None:
        _append_unique(warnings, "ROCE missing from financial ratios.")
    if share_count.get("value_original") in (None, "") and share_count.get("value_crore") is None:
        _append_unique(warnings, "Share count missing from normalized fundamentals.")
    if not (shareholding.get("items") or []):
        _append_unique(warnings, "Shareholding pattern missing or empty.")
    if (corporate_actions.get("per_share_comparability_warnings") or []):
        _append_unique(warnings, "Corporate action comparability issues present.")

    _check(
        checks,
        name="warning_signals",
        status="warning" if warnings else "pass",
        details="Warnings: " + "; ".join(warnings) if warnings else "No financial warning signals detected.",
    )


def _check_company_memory(
    *,
    company_root: Path,
    payloads: Dict[str, Dict[str, Any]],
    checks: List[FinancialAuditCheck],
    failures: List[str],
    warnings: List[str],
) -> None:
    trends = payloads.get("financial_trends.json") or {}
    year_index = payloads.get("financial_year_index.json") or {}
    quality_evolution = payloads.get("financial_quality_evolution.json") or {}
    capital_timeline = payloads.get("capital_allocation_financial_timeline.json") or {}
    ownership = payloads.get("ownership_evolution.json") or {}
    memory_summary = payloads.get("financial_memory_summary.json") or {}
    quality = payloads.get("financial_quality_summary.json") or {}
    attribution = payloads.get("financial_driver_attribution.json") or {}

    if any(
        _contains_source_chunk(item)
        for item in (year_index, trends, quality_evolution, capital_timeline, ownership, memory_summary, quality, attribution)
    ):
        _append_unique(failures, "source_chunk leaked into company-level financial memory artifacts.")
        source_chunk_status = "fail"
    else:
        source_chunk_status = "pass"
    _check(
        checks,
        name="source_chunk_hygiene",
        status=source_chunk_status,
        details=(
            "Company-level financial memory artifacts do not contain source_chunk."
            if source_chunk_status == "pass"
            else "source_chunk leaked into company-level financial memory artifacts."
        ),
    )

    years_covered = list(trends.get("years_covered", [])) if isinstance(trends.get("years_covered"), list) else []
    if len(years_covered) <= 1:
        _append_unique(warnings, "Only one financial year available.")
    basis = str(trends.get("basis") or "")
    if basis in {"mixed", "unknown"}:
        _append_unique(warnings, f"Company-level financial basis is {basis}.")
    _check(
        checks,
        name="financial_memory_basis",
        status="warning" if basis in {"mixed", "unknown"} else "pass",
        details=f"Financial memory basis: {basis or 'missing'}.",
    )

    summary_status = str(memory_summary.get("status") or "")
    if summary_status == "fail":
        _append_unique(failures, "financial_memory_summary.json status is fail.")
    forbidden_text = json.dumps(memory_summary, ensure_ascii=False)
    contains_forbidden_language = _contains_forbidden_recommendation_language(forbidden_text)
    if '"source_chunk"' in forbidden_text or contains_forbidden_language:
        _append_unique(failures, "financial_memory_summary.json contains forbidden source-chunk or recommendation language.")
    _check(
        checks,
        name="financial_memory_summary_contract",
        status="fail" if summary_status == "fail" or '"source_chunk"' in forbidden_text or contains_forbidden_language else "pass",
        details="financial_memory_summary.json is compact and investor-safe." if summary_status != "fail" else "financial_memory_summary.json status is fail.",
    )

    pcim_path = company_root / "company_memory" / "pcim_v1.json"
    if not pcim_path.exists():
        _append_unique(warnings, "PCIM missing; financial manifest check deferred until pcim stage runs.")
        _check(
            checks,
            name="pcim_financial_manifest",
            status="warning",
            details="pcim_v1.json is not present yet.",
        )
        return

    try:
        pcim = _load_json(pcim_path)
    except json.JSONDecodeError as exc:
        _append_unique(failures, f"Malformed JSON in pcim_v1.json: {exc}")
        _check(
            checks,
            name="pcim_financial_manifest",
            status="fail",
            details="pcim_v1.json contains malformed JSON.",
        )
        return

    manifest = pcim.get("pcim_source_manifest") or {}
    if not manifest:
        _append_unique(failures, "pcim_source_manifest missing from pcim_v1.json.")
        _check(
            checks,
            name="pcim_financial_manifest",
            status="fail",
            details="pcim_source_manifest missing from pcim_v1.json.",
        )
        return

    required_keys = {
        "financial_artifacts_used",
        "financial_years_covered",
        "financial_status",
        "financial_warnings",
    }
    missing_keys = sorted(required_keys - set(manifest))
    if missing_keys:
        _append_unique(
            failures,
            "pcim_source_manifest missing required financial fields: " + ", ".join(missing_keys),
        )
    financial_sections = {
        "financial_fundamentals_inputs": pcim.get("financial_fundamentals_inputs"),
        "financial_trend_inputs": pcim.get("financial_trend_inputs"),
        "cash_conversion_inputs": pcim.get("cash_conversion_inputs"),
        "return_on_capital_inputs": pcim.get("return_on_capital_inputs"),
        "balance_sheet_strength_inputs": pcim.get("balance_sheet_strength_inputs"),
        "per_share_inputs": pcim.get("per_share_inputs"),
        "corporate_action_inputs": pcim.get("corporate_action_inputs"),
        "ownership_inputs": pcim.get("ownership_inputs"),
        "financial_driver_inputs": pcim.get("financial_driver_inputs"),
    }
    if _contains_source_chunk(financial_sections):
        _append_unique(failures, "source_chunk leaked into financial PCIM sections.")
    status = "fail" if missing_keys or _contains_source_chunk(financial_sections) else "pass"
    _check(
        checks,
        name="pcim_financial_manifest",
        status=status,
        details=(
            "PCIM financial manifest and compact financial sections are present."
            if status == "pass"
            else "PCIM financial manifest or financial section hygiene failed."
        ),
    )


def build_financial_audit_report(
    *,
    company: str,
    year: str,
    financials_dir: Path,
) -> FinancialAuditReport:
    checks: List[FinancialAuditCheck] = []
    failures: List[str] = []
    warnings: List[str] = []
    present_artifacts: List[str] = []
    missing_artifacts: List[str] = []

    _record_artifact_presence(
        artifact_dir=financials_dir,
        required_artifacts=YEAR_REQUIRED_ARTIFACTS,
        checks=checks,
        failures=failures,
        present_artifacts=present_artifacts,
        missing_artifacts=missing_artifacts,
    )
    payloads = _validate_artifact_shapes(
        artifact_dir=financials_dir,
        filenames=YEAR_REQUIRED_ARTIFACTS,
        checks=checks,
        failures=failures,
        warnings=warnings,
    )
    _check_stale_saved_audit(
        artifact_dir=financials_dir,
        payloads=payloads,
        checks=checks,
        warnings=warnings,
    )
    _check_year_fundamentals(
        company=company,
        year=year,
        payloads=payloads,
        checks=checks,
        failures=failures,
        warnings=warnings,
    )

    report = FinancialAuditReport(
        company=company,
        year=year,
        scope="year",
        generated_at=utc_now(),
        status=_safe_status(failures, warnings),
        hard_failures=failures,
        warnings=warnings,
        checks=checks,
        required_artifacts=list(YEAR_REQUIRED_ARTIFACTS),
        present_artifacts=present_artifacts,
        missing_artifacts=missing_artifacts,
        limitations=[],
    )
    errors = validate_financial_audit_payload(report.to_dict())
    if errors:
        raise RuntimeError("financial audit report validation failed: " + "; ".join(errors))
    return report


def write_financial_audit_report(
    *,
    company: str,
    year: str,
    financials_dir: Path,
    output_path: Path,
) -> FinancialAuditReport:
    report = build_financial_audit_report(
        company=company,
        year=year,
        financials_dir=financials_dir,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def build_financial_memory_audit_report(
    *,
    company: str,
    company_root: Path,
) -> FinancialAuditReport:
    financials_dir = company_root / "company_memory" / "financials"
    checks: List[FinancialAuditCheck] = []
    failures: List[str] = []
    warnings: List[str] = []
    present_artifacts: List[str] = []
    missing_artifacts: List[str] = []

    _record_artifact_presence(
        artifact_dir=financials_dir,
        required_artifacts=COMPANY_MEMORY_REQUIRED_ARTIFACTS,
        checks=checks,
        failures=failures,
        present_artifacts=present_artifacts,
        missing_artifacts=missing_artifacts,
    )
    payloads = _validate_artifact_shapes(
        artifact_dir=financials_dir,
        filenames=COMPANY_MEMORY_REQUIRED_ARTIFACTS,
        checks=checks,
        failures=failures,
        warnings=warnings,
    )
    _check_company_memory(
        company_root=company_root,
        payloads=payloads,
        checks=checks,
        failures=failures,
        warnings=warnings,
    )

    report = FinancialAuditReport(
        company=company,
        year=None,
        scope="company_memory",
        generated_at=utc_now(),
        status=_safe_status(failures, warnings),
        hard_failures=failures,
        warnings=warnings,
        checks=checks,
        required_artifacts=list(COMPANY_MEMORY_REQUIRED_ARTIFACTS),
        present_artifacts=present_artifacts,
        missing_artifacts=missing_artifacts,
        limitations=[],
    )
    errors = validate_financial_audit_payload(report.to_dict())
    if errors:
        raise RuntimeError("financial memory audit report validation failed: " + "; ".join(errors))
    return report


def write_financial_memory_audit_report(
    *,
    company: str,
    company_root: Path,
    output_path: Path,
) -> FinancialAuditReport:
    report = build_financial_memory_audit_report(
        company=company,
        company_root=company_root,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report
