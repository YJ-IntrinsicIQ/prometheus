from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from knowledge.company_memory.company_layer import parse_financial_year

from .pcim_validation_schema import (
    validate_financial_pcim_validation_payload,
    validate_financial_quality_scorecard_payload,
)


EXPECTED_FINANCIAL_PCIM_SECTIONS = [
    "financial_fundamentals_inputs",
    "financial_growth_inputs",
    "profitability_inputs",
    "return_on_capital_inputs",
    "cash_conversion_inputs",
    "balance_sheet_strength_inputs",
    "working_capital_inputs",
    "per_share_inputs",
    "corporate_action_inputs",
    "ownership_inputs",
    "financial_quality_inputs",
]
RAW_LEAKAGE_TOKENS = (
    "source_chunk",
    "raw_financial_tables",
    "line_item_raw",
    "table_type",
    "statement_type",
    "chunk_id",
    "clean_chunks",
)
FORBIDDEN_LANGUAGE_PATTERNS = (
    re.compile(r"\bbuy\b", re.IGNORECASE),
    re.compile(r"\bsell\b", re.IGNORECASE),
    re.compile(r"\bhold\b", re.IGNORECASE),
    re.compile(r"target price", re.IGNORECASE),
    re.compile(r"undervalued", re.IGNORECASE),
    re.compile(r"overvalued", re.IGNORECASE),
    re.compile(r"intrinsic value", re.IGNORECASE),
    re.compile(r"margin of safety", re.IGNORECASE),
    re.compile(r"owner earnings", re.IGNORECASE),
)
SOFT_SECTION_CHAR_LIMIT = 12_000
SOFT_TOTAL_CHAR_LIMIT = 28_000
HARD_TOTAL_TOKEN_LIMIT = 7_000
SOFT_METRIC_COUNT_LIMIT = 40
HARD_METRIC_COUNT_LIMIT = 120
KEY_WARNING_LABELS = {
    "basis_unknown": ("basis unknown", "preferred basis unknown", "basis remains unknown", "basis unclear", "basis uncertainty", "standalone/consolidated basis unclear"),
    "capex_missing": ("capex missing", "capital expenditure missing", "capital expenditure not available", "fcf cannot be calculated due capex missing"),
    "fcf_missing": ("fcf missing", "free cash flow missing", "free cash flow unavailable", "capex missing prevents fcf"),
    "share_count_missing": (
        "share count missing",
        "shares outstanding missing",
        "weighted average shares missing",
        "diluted shares missing",
        "per-share analysis is limited",
        "share-count data incomplete",
    ),
    "payables_missing": ("payables missing", "trade payables missing", "payable days missing", "ccc incomplete", "cash conversion cycle unavailable"),
    "shareholding_missing": ("shareholding missing", "shareholding pattern missing"),
    "reconciliation_warning": ("reconciliation",),
    "audit_warning": ("audit",),
    "corporate_action_comparability": ("comparability", "dilution", "split", "bonus", "qip"),
}
MAJOR_METRICS = {"revenue", "pat", "net_worth", "total_debt", "cash_and_equivalents", "cfo", "opm", "roe", "roce"}
SCORE_DIMENSIONS = (
    "artifact_completeness",
    "reconciliation_quality",
    "ratio_quality",
    "growth_quality",
    "corporate_action_quality",
    "shareholding_quality",
    "pcim_financial_integration",
    "multi_year_financial_memory",
    "panel_financial_readiness",
)


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _append_unique(items: List[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _sorted_years(years: Iterable[str]) -> List[str]:
    values = {str(year).strip() for year in years if str(year).strip()}
    return sorted(values, key=parse_financial_year)


def _discover_company_years(company_root: Path) -> List[str]:
    years: List[str] = []
    if not company_root.exists():
        return years
    for child in company_root.iterdir():
        if not child.is_dir():
            continue
        try:
            parse_financial_year(child.name)
        except ValueError:
            continue
        years.append(child.name)
    return _sorted_years(years)


def _status_from_lists(hard_failures: Sequence[str], warnings: Sequence[str]) -> str:
    if hard_failures:
        return "fail"
    if warnings:
        return "warning"
    return "pass"


def _contains_forbidden_language(text: str) -> bool:
    return any(pattern.search(text) for pattern in FORBIDDEN_LANGUAGE_PATTERNS)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def _section_size(section: Any) -> Tuple[int, int]:
    serialized = json.dumps(section, ensure_ascii=False)
    return len(serialized), _estimate_tokens(serialized)


def _artifact_status(payload: Dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip().lower()
    return status if status in {"pass", "warning", "fail"} else "warning"


def _metric_like_dict(node: Dict[str, Any]) -> bool:
    return any(key in node for key in ("metric", "field", "value", "value_crore", "growth_percent", "holding_percent"))


def _iter_dicts(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _iter_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


def _collect_metric_count(section: Any) -> int:
    return sum(1 for item in _iter_dicts(section) if _metric_like_dict(item))


def _section_text(pcim_payload: Dict[str, Any]) -> str:
    parts: List[str] = []
    for section in EXPECTED_FINANCIAL_PCIM_SECTIONS + ["multi_year_financial_inputs", "financial_source_manifest"]:
        if section in pcim_payload:
            parts.append(json.dumps(pcim_payload.get(section), ensure_ascii=False))
    manifest = pcim_payload.get("pcim_source_manifest") or {}
    if manifest:
        parts.append(json.dumps(manifest, ensure_ascii=False))
    return "\n".join(parts)


def _has_financial_artifacts(year_dir: Path) -> bool:
    names = (
        "normalized_fundamentals.json",
        "financial_ratios.json",
        "financial_growth.json",
        "financial_quality_summary.json",
        "corporate_actions.json",
        "shareholding_pattern.json",
    )
    return any((year_dir / name).exists() for name in names)


def _normalized_metric_lookup(normalized: Dict[str, Any]) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {}
    sections = {
        "profit_and_loss": ("revenue", "pat"),
        "balance_sheet": ("net_worth", "total_debt", "cash_and_equivalents", "payables"),
        "cash_flow": ("cfo", "capex"),
        "share_data": ("shares_outstanding",),
    }
    for section, fields in sections.items():
        payload = normalized.get(section) or {}
        for field in fields:
            entry = payload.get(field) or {}
            value = entry.get("value_crore")
            unit = "₹ crore"
            if value is None:
                for alt_key, alt_unit in (("value_per_share", "per share"), ("raw_number", "count"), ("crore_shares", "crore shares")):
                    if entry.get(alt_key) is not None:
                        value = entry.get(alt_key)
                        unit = alt_unit
                        break
            if value is not None:
                mapping[field] = {"value": value, "unit": unit}
    return mapping


def _ratio_metric_lookup(ratios: Dict[str, Any]) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {}
    for metric, item in (ratios.get("ratios") or {}).items():
        if isinstance(item, dict) and item.get("value") is not None:
            mapping[metric] = {"value": item.get("value"), "unit": item.get("unit") or ""}
    return mapping


def _growth_metric_lookup(growth: Dict[str, Any]) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {}
    for metric, items in (growth.get("growth_metrics") or {}).items():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("growth_percent") is not None:
                mapping[metric] = {"value": item.get("growth_percent"), "unit": "%"}
                break
    return mapping


def _pcim_metric_items(pcim_payload: Dict[str, Any], year: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    for bucket in (pcim_payload.get("financial_fundamentals_inputs") or {}).get("by_year", []) or []:
        if str(bucket.get("year")) != year:
            continue
        for metric in bucket.get("key_metrics", []) or []:
            if isinstance(metric, dict):
                items.append({"metric": metric.get("field"), "value": metric.get("value_crore", metric.get("value_original")), "unit": metric.get("unit_original") or "₹ crore", "payload": metric, "source_type": "normalized"})

    for section_name in ("financial_growth_inputs", "profitability_inputs", "working_capital_inputs"):
        for bucket in (pcim_payload.get(section_name) or {}).get("by_year", []) or []:
            if str(bucket.get("year")) != year:
                continue
            key = "growth_metrics" if section_name == "financial_growth_inputs" else "metrics"
            for metric in bucket.get(key, []) or []:
                if isinstance(metric, dict):
                    items.append({"metric": metric.get("metric"), "value": metric.get("value", metric.get("growth_percent")), "unit": metric.get("unit") or "%", "payload": metric, "source_type": "growth" if section_name == "financial_growth_inputs" else "ratios"})

    for section_name in ("cash_conversion_inputs", "return_on_capital_inputs", "balance_sheet_strength_inputs", "per_share_inputs"):
        for metric in (pcim_payload.get(section_name) or {}).get("metrics", []) or []:
            if not isinstance(metric, dict):
                continue
            series = metric.get("series") or []
            point = next((point for point in series if isinstance(point, dict) and str(point.get("year")) == year), None)
            if point:
                items.append({"metric": metric.get("metric"), "value": point.get("value"), "unit": metric.get("unit") or "", "payload": point, "source_type": "ratios_or_trends"})

    for bucket in (pcim_payload.get("ownership_inputs") or {}).get("by_year", []) or []:
        if str(bucket.get("year")) != year:
            continue
        for item in bucket.get("items", []) or []:
            if isinstance(item, dict):
                items.append({"metric": item.get("holder_category"), "value": item.get("holding_percent"), "unit": "%", "payload": item, "source_type": "ownership"})

    return items


def _traceability_issues(node: Any, *, issues: List[str]) -> None:
    if isinstance(node, dict):
        if _metric_like_dict(node):
            metric_name = node.get("metric") or node.get("field") or node.get("holder_category") or "<unknown>"
            has_value = any(node.get(key) is not None for key in ("value", "value_crore", "growth_percent", "holding_percent"))
            if has_value:
                if not (node.get("source_artifact") or node.get("source_artifacts") or node.get("source_manifest")):
                    _append_unique(issues, f"Missing source artifact traceability for metric-like item: {metric_name}")
                if not node.get("basis") and not node.get("years_covered") and node.get("holding_percent") is None:
                    _append_unique(issues, f"Missing basis for metric-like item: {metric_name}")
                if node.get("confidence") is None and not node.get("years_covered"):
                    _append_unique(issues, f"Missing confidence for metric-like item: {metric_name}")
        for value in node.values():
            _traceability_issues(value, issues=issues)
    elif isinstance(node, list):
        for item in node:
            _traceability_issues(item, issues=issues)


def _warning_expectations(
    *,
    normalized: Dict[str, Any],
    ratios: Dict[str, Any],
    validation: Dict[str, Any],
    reconciliation: Dict[str, Any],
    audit: Dict[str, Any],
    corporate_actions: Dict[str, Any],
    shareholding: Dict[str, Any],
) -> List[str]:
    labels: List[str] = []
    if str(normalized.get("preferred_basis") or "unknown") == "unknown":
        labels.append("basis_unknown")
    if (((normalized.get("cash_flow") or {}).get("capex") or {}).get("value_crore")) is None:
        labels.append("capex_missing")
    if (((ratios.get("ratios") or {}).get("fcf") or {}).get("value")) is None:
        labels.append("fcf_missing")
    if not (((normalized.get("share_data") or {}).get("shares_outstanding") or {}).get("value_original")):
        labels.append("share_count_missing")
    if (((normalized.get("balance_sheet") or {}).get("payables") or {}).get("value_crore") is None):
        labels.append("payables_missing")
    if _artifact_status(shareholding) in {"warning", "fail"} or not (shareholding.get("items") or []):
        labels.append("shareholding_missing")
    if _artifact_status(reconciliation) in {"warning", "fail"}:
        labels.append("reconciliation_warning")
    if audit and (_artifact_status(audit) in {"warning", "fail"} or audit.get("warnings") or audit.get("hard_failures")):
        labels.append("audit_warning")
    if (corporate_actions.get("per_share_comparability_warnings") or []):
        labels.append("corporate_action_comparability")
    return labels


def build_financial_pcim_validation(
    *,
    company: str,
    year: str,
    companies_root: Path | str = Path("companies"),
) -> Dict[str, Any]:
    companies_root = Path(companies_root)
    year_dir = companies_root / company / year / "financials"
    company_memory_dir = companies_root / company / "company_memory"
    audit_dir = companies_root / company / "audit"

    pcim = _load_json(company_memory_dir / "pcim_v1.json")
    normalized = _load_json(year_dir / "normalized_fundamentals.json")
    ratios = _load_json(year_dir / "financial_ratios.json")
    growth = _load_json(year_dir / "financial_growth.json")
    validation = _load_json(year_dir / "financial_validation_report.json")
    reconciliation = _load_json(year_dir / "financial_reconciliation_report.json")
    corporate_actions = _load_json(year_dir / "corporate_actions.json")
    shareholding = _load_json(year_dir / "shareholding_pattern.json")
    quality = _load_json(year_dir / "financial_quality_summary.json")
    memory_summary = _load_json(company_memory_dir / "financials" / "financial_memory_summary.json")
    panel_summary = _load_json(companies_root / company / year / "intelligence" / "investor_panel" / "panel_run_summary.json")
    financial_audit = _load_json(year_dir / "financial_audit_report.json")
    manifest = pcim.get("pcim_source_manifest") or {}

    checks: List[Dict[str, Any]] = []
    hard_failures: List[str] = []
    warnings: List[str] = []
    limitations: List[str] = []

    def record_check(name: str, status: str, details: str) -> None:
        checks.append({"check_name": name, "status": status, "details": details})

    financial_artifacts_exist = _has_financial_artifacts(year_dir)

    missing_sections = [section for section in EXPECTED_FINANCIAL_PCIM_SECTIONS if not isinstance(pcim.get(section), dict)]
    if financial_artifacts_exist and not missing_sections:
        record_check("pcim_financial_section_presence", "pass", "Expected financial PCIM sections are present.")
    elif financial_artifacts_exist and _artifact_status(validation) != "fail" and _artifact_status(reconciliation) != "fail":
        _append_unique(hard_failures, "PCIM financial sections missing despite usable financial artifacts: " + ", ".join(missing_sections))
        record_check("pcim_financial_section_presence", "fail", "Missing sections: " + ", ".join(missing_sections))
    else:
        _append_unique(warnings, "PCIM financial section coverage is incomplete because financial artifacts are missing or failed.")
        record_check("pcim_financial_section_presence", "warning", "Financial artifacts are incomplete or failed; section coverage cannot be fully enforced.")

    has_multi_year_memory = bool(memory_summary)
    if has_multi_year_memory and isinstance(pcim.get("multi_year_financial_inputs"), dict):
        record_check("multi_year_financial_inputs", "pass", "multi_year_financial_inputs is present.")
    elif has_multi_year_memory:
        _append_unique(warnings, "multi_year_financial_inputs is missing even though financial_memory_summary.json exists.")
        record_check("multi_year_financial_inputs", "warning", "financial_memory_summary.json exists but multi_year_financial_inputs is missing.")

    financial_text = _section_text(pcim)
    leakage_hits = [token for token in RAW_LEAKAGE_TOKENS if token in financial_text]
    if leakage_hits:
        _append_unique(hard_failures, "Raw financial artifact leakage detected in PCIM financial sections: " + ", ".join(sorted(set(leakage_hits))))
        record_check("raw_financial_leakage", "fail", "Detected raw-artifact leakage tokens in PCIM financial sections.")
    else:
        record_check("raw_financial_leakage", "pass", "No raw-artifact leakage detected in PCIM financial sections.")

    total_chars = 0
    total_tokens = 0
    compactness_warnings: List[str] = []
    metric_count = 0
    for section_name in EXPECTED_FINANCIAL_PCIM_SECTIONS + ["multi_year_financial_inputs"]:
        if section_name not in pcim:
            continue
        chars, tokens = _section_size(pcim.get(section_name))
        total_chars += chars
        total_tokens += tokens
        metric_count += _collect_metric_count(pcim.get(section_name))
        if chars > SOFT_SECTION_CHAR_LIMIT:
            _append_unique(compactness_warnings, f"{section_name} is larger than the soft compactness limit.")
    if metric_count > SOFT_METRIC_COUNT_LIMIT:
        _append_unique(compactness_warnings, "financial PCIM sections contain many metrics and may be over-dumped.")
    if total_tokens > HARD_TOTAL_TOKEN_LIMIT or metric_count > HARD_METRIC_COUNT_LIMIT:
        _append_unique(hard_failures, f"Financial PCIM sections exceed compactness budget (tokens={total_tokens}, metrics={metric_count}).")
        record_check("compactness", "fail", f"Financial PCIM sections are too large for safe panel use (chars={total_chars}, tokens={total_tokens}, metrics={metric_count}).")
    elif compactness_warnings or total_chars > SOFT_TOTAL_CHAR_LIMIT:
        if total_chars > SOFT_TOTAL_CHAR_LIMIT:
            _append_unique(compactness_warnings, "combined financial PCIM section size exceeds the soft prompt-size target")
        for item in compactness_warnings:
            _append_unique(warnings, item)
        record_check("compactness", "warning", f"Soft compactness warnings present (chars={total_chars}, tokens={total_tokens}, metrics={metric_count}).")
    else:
        record_check("compactness", "pass", f"Financial PCIM sections remain compact enough for panel use (chars={total_chars}, tokens={total_tokens}, metrics={metric_count}).")

    traceability_issues: List[str] = []
    for section_name in EXPECTED_FINANCIAL_PCIM_SECTIONS:
        _traceability_issues(pcim.get(section_name), issues=traceability_issues)
    if traceability_issues:
        for item in traceability_issues:
            target = hard_failures if any(metric in item.lower() for metric in MAJOR_METRICS) else warnings
            _append_unique(target, item)
        record_check("source_traceability", "fail" if any(metric in " ".join(traceability_issues).lower() for metric in MAJOR_METRICS) else "warning", "Some metric-like items are missing basis/confidence/source traceability.")
    else:
        record_check("source_traceability", "pass", "Metric-like financial PCIM items carry basis, confidence, and source references.")

    expected_warning_labels = _warning_expectations(
        normalized=normalized,
        ratios=ratios,
        validation=validation,
        reconciliation=reconciliation,
        audit=financial_audit,
        corporate_actions=corporate_actions,
        shareholding=shareholding,
    )
    lowered_pcim_text = financial_text.lower()
    missing_warning_labels = []
    for label in expected_warning_labels:
        if not any(phrase in lowered_pcim_text for phrase in KEY_WARNING_LABELS.get(label, ())):
            missing_warning_labels.append(label)
    if missing_warning_labels:
        for label in missing_warning_labels:
            _append_unique(warnings, f"PCIM does not clearly carry forward financial limitation: {label}")
        record_check("financial_warning_propagation", "warning", "Some underlying financial limitations are not clearly propagated into PCIM.")
    else:
        record_check("financial_warning_propagation", "pass", "Underlying financial limitations are visible in PCIM.")
    if (_artifact_status(validation) == "fail" or _artifact_status(reconciliation) == "fail") and pcim.get("financial_panel_ready") is True:
        _append_unique(hard_failures, "PCIM marks financial_panel_ready true despite year-level financial validation or reconciliation failure.")

    if _contains_forbidden_language(financial_text):
        _append_unique(hard_failures, "PCIM financial sections contain forbidden valuation or recommendation language.")
        record_check("unsupported_language", "fail", "Forbidden valuation/recommendation language detected in financial PCIM sections.")
    else:
        record_check("unsupported_language", "pass", "No forbidden valuation/recommendation language detected.")

    normalized_lookup = _normalized_metric_lookup(normalized)
    ratio_lookup = _ratio_metric_lookup(ratios)
    growth_lookup = _growth_metric_lookup(growth)
    consistency_failures: List[str] = []
    for item in _pcim_metric_items(pcim, year):
        metric = str(item.get("metric") or "")
        if not metric:
            continue
        source_type = str(item.get("source_type") or "")
        if source_type == "normalized":
            lookup = normalized_lookup
        elif source_type == "growth":
            lookup = growth_lookup
        elif source_type == "ownership":
            lookup = {}
        else:
            lookup = ratio_lookup
        if metric in lookup:
            expected_value = lookup[metric]["value"]
            actual_value = item.get("value")
            if isinstance(expected_value, (int, float)) and isinstance(actual_value, (int, float)):
                if abs(float(expected_value) - float(actual_value)) > 0.01:
                    _append_unique(consistency_failures, f"PCIM value mismatch for {metric}: {actual_value} != {expected_value}")
        elif metric in {"free_cash_flow", "owner_earnings"}:
            _append_unique(consistency_failures, f"Unsupported financial metric claimed in PCIM: {metric}")
    if (((ratios.get("ratios") or {}).get("fcf") or {}).get("value") is None) and "fcf" in {str(item.get("metric")) for item in _pcim_metric_items(pcim, year)}:
        _append_unique(consistency_failures, "PCIM claims FCF is available when financial_ratios.json reports it missing.")
    if consistency_failures:
        for item in consistency_failures:
            _append_unique(hard_failures, item)
        record_check("deterministic_consistency", "fail", "PCIM financial values or claims diverge from deterministic source artifacts.")
    else:
        record_check("deterministic_consistency", "pass", "PCIM financial values remain aligned with deterministic financial artifacts.")

    if panel_summary:
        panel_status = str(panel_summary.get("status") or "")
        detail = f"panel_run_summary status={panel_status or 'unknown'}"
        if panel_status == "fail":
            _append_unique(warnings, "panel_run_summary reports fail; financial panel readiness may still be blocked downstream.")
            record_check("panel_run_summary", "warning", detail)
        else:
            record_check("panel_run_summary", "pass", detail)

    payload = {
        "company": company,
        "year": year,
        "generated_at": utc_now(),
        "status": _status_from_lists(hard_failures, warnings),
        "checks": checks,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "limitations": limitations,
    }
    errors = validate_financial_pcim_validation_payload(payload)
    if errors:
        raise RuntimeError("financial PCIM validation payload failed schema validation: " + "; ".join(errors))
    return payload


def write_financial_pcim_validation(
    *,
    company: str,
    year: str,
    companies_root: Path | str = Path("companies"),
) -> Tuple[Dict[str, Any], Path]:
    companies_root = Path(companies_root)
    payload = build_financial_pcim_validation(company=company, year=year, companies_root=companies_root)
    output_path = companies_root / company / year / "financials" / "financial_pcim_validation.json"
    return payload, _write_json(output_path, payload)


def _dimension(score: int, reasons: Sequence[str]) -> Dict[str, Any]:
    status = "fail" if score < 60 else "warning" if score < 90 or reasons else "pass"
    return {"score": max(0, min(100, int(score))), "status": status, "reasons": list(reasons)}


def _score_artifact_completeness(year_dir: Path) -> Dict[str, Any]:
    required = [
        "normalized_fundamentals.json",
        "financial_validation_report.json",
        "financial_reconciliation_report.json",
        "financial_ratios.json",
        "financial_growth.json",
        "financial_quality_summary.json",
        "corporate_actions.json",
        "shareholding_pattern.json",
    ]
    missing = [name for name in required if not (year_dir / name).exists()]
    score = 100 - (len(missing) * 12)
    reasons = [f"Missing artifact: {name}" for name in missing]
    if "shareholding_pattern.json" in missing:
        score += 4
    return _dimension(score, reasons)


def _score_reconciliation_quality(reconciliation: Dict[str, Any]) -> Dict[str, Any]:
    status = _artifact_status(reconciliation)
    reasons = list(reconciliation.get("hard_failures", []) or []) + list(reconciliation.get("warnings", []) or [])
    if status == "fail":
        return _dimension(40, reasons)
    if status == "warning":
        return _dimension(75, reasons)
    return _dimension(100, [])


def _score_ratio_quality(ratios: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    if not ratios:
        return _dimension(35, ["financial_ratios.json missing"])
    score = 100
    for metric in ("opm", "npm", "roe", "roce", "debt_to_equity", "cfo_to_pat", "fcf_to_pat", "book_value_per_share"):
        item = (ratios.get("ratios") or {}).get(metric) or {}
        if item.get("value") is None:
            score -= 8
            _append_unique(reasons, f"Ratio missing or unusable: {metric}")
        if item and not (item.get("source_artifacts") or item.get("source_artifact")):
            score -= 10
            _append_unique(reasons, f"Ratio traceability missing: {metric}")
    return _dimension(score, reasons)


def _score_growth_quality(growth: Dict[str, Any], years_available: int) -> Dict[str, Any]:
    reasons: List[str] = []
    if not growth:
        return _dimension(35, ["financial_growth.json missing"])
    score = 100
    growth_metrics = growth.get("growth_metrics") or {}
    for metric in ("revenue", "pat", "eps_basic", "book_value_per_share"):
        items = growth_metrics.get(metric) or []
        if not items:
            score -= 8
            _append_unique(reasons, f"Growth metric missing: {metric}")
    if years_available <= 1:
        score -= 10
        _append_unique(reasons, "Only one financial year available.")
    return _dimension(score, reasons)


def _score_corporate_action_quality(corporate_actions: Dict[str, Any], year_dir: Path) -> Dict[str, Any]:
    reasons: List[str] = []
    if not corporate_actions:
        return _dimension(55, ["corporate_actions.json missing"])
    score = 100
    if any(item.get("action_type") == "qip_proceeds_utilization" and item.get("impact_on_share_count") == "increase" for item in corporate_actions.get("actions", []) if isinstance(item, dict)):
        score = min(score, 60)
        _append_unique(reasons, "QIP proceeds utilization incorrectly affects share count.")
    if any(item.get("action_type") == "qip_issue" and item.get("impact_on_share_count") == "increase" and not (item.get("shares_after") or item.get("shares_issued")) for item in corporate_actions.get("actions", []) if isinstance(item, dict)):
        score -= 20
        _append_unique(reasons, "QIP issue marks dilution without reliable share-count support.")
    if (corporate_actions.get("per_share_comparability_warnings") or []):
        score -= 10
        reasons.extend(str(item) for item in corporate_actions.get("per_share_comparability_warnings", []))
    rejection_path = year_dir / "corporate_action_rejections.json"
    if rejection_path.exists():
        score = min(100, score + 5)
    return _dimension(score, reasons)


def _score_shareholding_quality(shareholding: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    if not shareholding:
        return _dimension(70, ["shareholding_pattern.json missing"])
    score = 100
    if _artifact_status(shareholding) in {"warning", "fail"}:
        score -= 20
        reasons.extend(str(item) for item in shareholding.get("warnings", []))
    if not (shareholding.get("items") or []):
        score -= 20
        _append_unique(reasons, "Shareholding items missing.")
    if not any(item.get("holder_category") == "pledged_promoter_holding_percent" for item in shareholding.get("items", []) if isinstance(item, dict)):
        score -= 5
        _append_unique(reasons, "Promoter pledge detail unavailable.")
    return _dimension(score, reasons)


def _score_pcim_integration(validation_payload: Dict[str, Any]) -> Dict[str, Any]:
    reasons = list(validation_payload.get("hard_failures", [])) + list(validation_payload.get("warnings", []))
    score = 100
    if validation_payload.get("status") == "fail":
        score = 40
    elif validation_payload.get("status") == "warning":
        score = 75
    text = "\n".join(reasons).lower()
    if "raw financial artifact leakage" in text or "source_chunk" in text:
        score = min(score, 50)
    if "invent" in text or "mismatch" in text:
        score = min(score, 45)
    return _dimension(score, reasons)


def _score_multi_year_financial_memory(company_financial_dir: Path) -> Dict[str, Any]:
    reasons: List[str] = []
    memory_summary = _load_json(company_financial_dir / "financial_memory_summary.json")
    year_index = _load_json(company_financial_dir / "financial_year_index.json")
    if not memory_summary:
        return _dimension(75, ["financial_memory_summary.json missing"])
    score = 100
    if len(memory_summary.get("years_covered", []) or []) <= 1:
        score -= 15
        _append_unique(reasons, "Only one financial year available in multi-year financial memory.")
    if str(memory_summary.get("basis_used") or "unknown") == "unknown":
        score = min(score, 60)
        _append_unique(reasons, "Multi-year financial basis remains unknown.")
    if _artifact_status(memory_summary) == "fail":
        score = min(score, 50)
        _append_unique(reasons, "financial_memory_summary.json status is fail.")
    reasons.extend(str(item) for item in year_index.get("warnings", []) if isinstance(item, str))
    return _dimension(score, reasons)


def _score_panel_financial_readiness(pcim: Dict[str, Any], panel_summary: Dict[str, Any], validation_payloads: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    reasons: List[str] = []
    score = 100 if pcim.get("financial_panel_ready") is True else 70
    if pcim.get("financial_panel_ready") is not True:
        _append_unique(reasons, "PCIM financial_panel_ready is false.")
    if any(payload.get("status") == "fail" for payload in validation_payloads.values()):
        score = min(score, 60)
        _append_unique(reasons, "At least one year-level financial PCIM validation failed.")
    if panel_summary:
        panel_status = str(panel_summary.get("status") or "")
        if panel_status == "fail":
            score = min(score, 55)
            _append_unique(reasons, "panel_run_summary reports fail.")
    else:
        score -= 10
        _append_unique(reasons, "panel_run_summary.json missing.")
    return _dimension(score, reasons)


def _overall_status(score: int, hard_failures: Sequence[str], warnings: Sequence[str]) -> str:
    if hard_failures or score < 60:
        return "fail"
    if warnings or score < 90:
        return "warning"
    return "pass"


def _recommended_fixes(hard_failures: Sequence[str], warnings: Sequence[str]) -> List[str]:
    actions: List[str] = []
    joined = "\n".join([*hard_failures, *warnings]).lower()
    if "raw financial artifact leakage" in joined or "source_chunk" in joined:
        _append_unique(actions, "Keep PCIM financial sections compact and panel-safe by stripping raw table, chunk, and debug fields before save.")
    if "capex" in joined or "fcf" in joined:
        _append_unique(actions, "Improve capex and cash-flow coverage so FCF-related panel reasoning is based on complete deterministic inputs.")
    if "share count" in joined:
        _append_unique(actions, "Tighten share-data extraction so per-share metrics remain trustworthy.")
    if "shareholding" in joined:
        _append_unique(actions, "Improve ownership extraction so PCIM can carry fuller promoter, pledge, and institutional signals.")
    if "basis" in joined:
        _append_unique(actions, "Resolve standalone versus consolidated basis ambiguity before promoting financial readiness.")
    if "reconciliation" in joined:
        _append_unique(actions, "Fix reconciliation warnings and failures before treating financial PCIM as panel-safe.")
    if "financial_memory" in joined or "multi-year" in joined:
        _append_unique(actions, "Regenerate company-level financial memory and ensure PCIM includes multi_year_financial_inputs.")
    if not actions:
        _append_unique(actions, "Address the listed warnings and hard failures before relying on financial PCIM in investor-panel reasoning.")
    return actions


def build_financial_quality_scorecard(
    *,
    company: str,
    companies_root: Path | str = Path("companies"),
) -> Dict[str, Any]:
    companies_root = Path(companies_root)
    company_root = companies_root / company
    company_financial_dir = company_root / "company_memory" / "financials"
    company_memory_dir = company_root / "company_memory"
    years = _discover_company_years(company_root)
    pcim = _load_json(company_memory_dir / "pcim_v1.json")
    panel_summary = _load_json(company_root / years[-1] / "intelligence" / "investor_panel" / "panel_run_summary.json") if years else {}

    year_validations: Dict[str, Dict[str, Any]] = {}
    year_dimensions: Dict[str, Dict[str, Any]] = {}
    hard_failures: List[str] = []
    warnings: List[str] = []

    for year in years:
        validation_payload = build_financial_pcim_validation(company=company, year=year, companies_root=companies_root)
        year_validations[year] = validation_payload
        year_dir = company_root / year / "financials"
        reconciliation = _load_json(year_dir / "financial_reconciliation_report.json")
        ratios = _load_json(year_dir / "financial_ratios.json")
        growth = _load_json(year_dir / "financial_growth.json")
        corporate_actions = _load_json(year_dir / "corporate_actions.json")
        shareholding = _load_json(year_dir / "shareholding_pattern.json")

        dims = {
            "artifact_completeness": _score_artifact_completeness(year_dir),
            "reconciliation_quality": _score_reconciliation_quality(reconciliation),
            "ratio_quality": _score_ratio_quality(ratios),
            "growth_quality": _score_growth_quality(growth, len(years)),
            "corporate_action_quality": _score_corporate_action_quality(corporate_actions, year_dir),
            "shareholding_quality": _score_shareholding_quality(shareholding),
            "pcim_financial_integration": _score_pcim_integration(validation_payload),
        }
        year_dimensions[year] = dims
        for item in validation_payload.get("hard_failures", []):
            _append_unique(hard_failures, f"{year}: {item}")
        for item in validation_payload.get("warnings", []):
            _append_unique(warnings, f"{year}: {item}")

    multi_year_dimension = _score_multi_year_financial_memory(company_financial_dir)
    panel_dimension = _score_panel_financial_readiness(pcim, panel_summary, year_validations)

    dimensions: Dict[str, Dict[str, Any]] = {}
    for name in SCORE_DIMENSIONS:
        if name == "multi_year_financial_memory":
            dimensions[name] = multi_year_dimension
        elif name == "panel_financial_readiness":
            dimensions[name] = panel_dimension
        else:
            scores = [year_dimensions[year][name]["score"] for year in year_dimensions if name in year_dimensions[year]]
            reasons: List[str] = []
            for year in year_dimensions:
                reasons.extend(f"{year}: {reason}" for reason in year_dimensions[year][name]["reasons"])
            dimensions[name] = _dimension(sum(scores) // len(scores) if scores else 70, reasons)

    overall_score = sum(dimensions[name]["score"] for name in SCORE_DIMENSIONS) // len(SCORE_DIMENSIONS)

    joined_failures = "\n".join(hard_failures).lower()
    if "raw financial artifact leakage" in joined_failures or "source_chunk" in joined_failures:
        overall_score = min(overall_score, 50)
    if "invent" in joined_failures or "mismatch" in joined_failures:
        overall_score = min(overall_score, 45)
    if any("reconciliation" in item.lower() and "fail" in item.lower() for item in hard_failures):
        overall_score = min(overall_score, 60)
    if any("ratio traceability" in item.lower() for item in warnings + hard_failures):
        overall_score = min(overall_score, 65)
    if not (company_root / years[0] / "financials" / "financial_quality_summary.json").exists() if years else True:
        overall_score = min(overall_score, 70)
    if _contains_forbidden_language(json.dumps(pcim, ensure_ascii=False)):
        overall_score = min(overall_score, 40)

    payload = {
        "company": company,
        "generated_at": utc_now(),
        "status": _overall_status(overall_score, hard_failures, warnings),
        "overall_score": int(overall_score),
        "dimensions": dimensions,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "recommended_next_fixes": _recommended_fixes(hard_failures, warnings),
        "years": {
            year: {
                "pcim_validation_status": year_validations[year]["status"],
                "pcim_validation_hard_failures": year_validations[year]["hard_failures"],
                "pcim_validation_warnings": year_validations[year]["warnings"],
                "dimension_scores": year_dimensions[year],
            }
            for year in years
        },
    }
    errors = validate_financial_quality_scorecard_payload(payload)
    if errors:
        raise RuntimeError("financial quality scorecard payload failed schema validation: " + "; ".join(errors))
    return payload


def render_financial_quality_scorecard_markdown(payload: Dict[str, Any]) -> str:
    dimensions = payload.get("dimensions") or {}
    sorted_dimensions = sorted(
        ((name, data) for name, data in dimensions.items() if isinstance(data, dict)),
        key=lambda item: item[1].get("score", 0),
        reverse=True,
    )
    best = sorted_dimensions[:3]
    weakest = list(reversed(sorted_dimensions[-3:])) if sorted_dimensions else []
    lines = [
        "# Financial Quality Scorecard",
        "",
        f"- Overall status: {payload.get('status', 'unknown')}",
        f"- Overall score: {payload.get('overall_score', 0)}",
        "",
        "## Best Dimensions",
    ]
    if best:
        for name, data in best:
            lines.append(f"- {name}: {data.get('score', 0)} ({data.get('status', 'unknown')})")
    else:
        lines.append("- No dimensions were scored.")
    lines.extend(["", "## Weakest Dimensions"])
    if weakest:
        for name, data in weakest:
            lines.append(f"- {name}: {data.get('score', 0)} ({data.get('status', 'unknown')})")
    else:
        lines.append("- No weak dimensions were recorded.")
    lines.extend(["", "## Hard Failures"])
    if payload.get("hard_failures"):
        for item in payload["hard_failures"]:
            lines.append(f"- {item}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Warnings"])
    if payload.get("warnings"):
        for item in payload["warnings"]:
            lines.append(f"- {item}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Recommended Next Fixes"])
    for item in payload.get("recommended_next_fixes", []) or ["No further fixes were suggested."]:
        lines.append(f"- {item}")
    lines.extend(["", "## Year-by-Year Readiness"])
    for year, year_payload in (payload.get("years") or {}).items():
        lines.append(f"- {year}: {year_payload.get('pcim_validation_status', 'unknown')}")
    lines.extend(["", "## Panel Readiness"])
    panel_dimension = (payload.get("dimensions") or {}).get("panel_financial_readiness") or {}
    lines.append(f"- Score: {panel_dimension.get('score', 0)}")
    lines.append(f"- Status: {panel_dimension.get('status', 'unknown')}")
    return "\n".join(lines) + "\n"


def write_financial_quality_scorecard(
    *,
    company: str,
    companies_root: Path | str = Path("companies"),
) -> Dict[str, Path]:
    companies_root = Path(companies_root)
    payload = build_financial_quality_scorecard(company=company, companies_root=companies_root)
    audit_dir = companies_root / company / "audit"
    json_path = _write_json(audit_dir / "financial_quality_scorecard.json", payload)
    md_path = _write_text(audit_dir / "financial_quality_scorecard.md", render_financial_quality_scorecard_markdown(payload))
    return {
        "financial_quality_scorecard.json": json_path,
        "financial_quality_scorecard.md": md_path,
    }
