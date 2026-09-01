from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from knowledge.company_memory import parse_financial_year
from knowledge.company_year_eligibility import build_company_year_eligibility_manifest

from .memory_schema import (
    validate_capital_allocation_financial_timeline_payload,
    validate_financial_memory_manifest_payload,
    validate_financial_memory_summary_payload,
    validate_financial_truth_pack_payload,
    validate_financial_quality_evolution_payload,
    validate_financial_year_index_payload,
    validate_ownership_evolution_payload,
)
from .financial_memory_truth import build_financial_memory_manifest, build_financial_truth_pack


YEAR_LEVEL_REQUIRED = (
    "normalized_fundamentals.json",
    "financial_validation_report.json",
    "financial_reconciliation_report.json",
    "financial_ratios.json",
    "financial_growth.json",
    "financial_quality_summary.json",
    "corporate_actions.json",
    "shareholding_pattern.json",
)


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
    unique = {str(year) for year in years if str(year).strip()}
    return sorted(unique, key=parse_financial_year)


_MISSING_CLAIM_CHECKS: List[Tuple[Tuple[str, ...], str]] = [
    # (text patterns in lowercased missing-data string, metric key in trends containers)
    (("eps exists but weighted average shares", "weighted average shares are missing"), "weighted_avg_shares"),
    (("fcf missing",), "fcf"),
    (("capex missing",), "capex"),
]


def _build_trends_presence(trends_payload: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Return {metric_name: {year, ...}} for metrics with non-null, usable_downstream=True points."""
    presence: Dict[str, Set[str]] = {}
    for container in trends_payload.values():
        if not isinstance(container, dict):
            continue
        for metric_name, metric in container.items():
            if not isinstance(metric, dict):
                continue
            for point in (metric.get("series") or []):
                if isinstance(point, dict) and point.get("value") is not None:
                    if point.get("usable_downstream", True):
                        presence.setdefault(metric_name, set()).add(str(point.get("year", "")))
    return presence


def _reconcile_canonical_presence(items: List[str], presence: Dict[str, Set[str]]) -> List[str]:
    """Remove missing-data / warning strings contradicted by the canonical trends presence map.

    A claim is contradicted when:
    - it matches a known "metric X is missing" pattern, AND
    - the canonical trends show that metric as present (non-null, usable_downstream) for the
      year named in the claim prefix (e.g. "fy23:") — or for at least one year if no prefix.

    Genuine missing items (metric absent in trends) are preserved.
    """
    result = []
    for item in items:
        lowered = item.lower()
        year: Optional[str] = None
        if ":" in lowered:
            prefix = lowered.split(":")[0].strip()
            if prefix.startswith("fy"):
                year = prefix
        keep = True
        for patterns, metric_key in _MISSING_CLAIM_CHECKS:
            if any(p in lowered for p in patterns):
                present_years = presence.get(metric_key, set())
                if year and year in present_years:
                    keep = False
                    break
                elif not year and present_years:
                    keep = False
                    break
        if keep:
            result.append(item)
    return result


def _detect_years(company_root: Path) -> List[str]:
    years: List[str] = []
    for child in company_root.iterdir() if company_root.exists() else []:
        if child.is_dir() and child.name.lower().startswith("fy"):
            years.append(child.name)
    return _sort_years(years)


def _company_year_eligibility(company: str, company_root: Path) -> Dict[str, Any]:
    return build_company_year_eligibility_manifest(company=company, company_root=company_root)


def _safe_status(payload: Optional[Dict[str, Any]]) -> str:
    if not isinstance(payload, dict):
        return "fail"
    status = str(payload.get("status") or "").strip().lower()
    return status if status in {"pass", "warning", "fail"} else "warning"


def _basis_used(normalized_payload: Optional[Dict[str, Any]]) -> str:
    if not isinstance(normalized_payload, dict):
        return "unknown"
    return str(normalized_payload.get("preferred_basis") or "unknown")


def _year_payloads(company_root: Path, year: str) -> Dict[str, Optional[Dict[str, Any]]]:
    financial_dir = company_root / year / "financials"
    return {
        name: _load_optional_json(financial_dir / name)
        for name in YEAR_LEVEL_REQUIRED
    }


def _year_available(payloads: Dict[str, Optional[Dict[str, Any]]]) -> bool:
    return any(isinstance(payloads.get(name), dict) for name in YEAR_LEVEL_REQUIRED)


def _year_is_usable(payloads: Dict[str, Optional[Dict[str, Any]]]) -> bool:
    if not _year_available(payloads):
        return False
    for key in (
        "financial_validation_report.json",
        "financial_reconciliation_report.json",
        "financial_quality_summary.json",
    ):
        if _safe_status(payloads.get(key)) == "fail":
            return False
    return True


def build_financial_year_index(*, company: str, company_root: Path) -> Dict[str, Any]:
    years_discovered = _detect_years(company_root)
    eligibility = _company_year_eligibility(company, company_root)
    eligible_years = set(eligibility.get("eligible_years", []))
    eligibility_by_year = eligibility.get("years", {}) if isinstance(eligibility.get("years"), dict) else {}
    years_used: List[str] = []
    years_skipped: List[str] = []
    year_status: Dict[str, Any] = {}
    warnings: List[str] = []
    limitations: List[str] = []

    for year in years_discovered:
        payloads = _year_payloads(company_root, year)
        validation_status = _safe_status(payloads.get("financial_validation_report.json"))
        reconciliation_status = _safe_status(payloads.get("financial_reconciliation_report.json"))
        quality_status = _safe_status(payloads.get("financial_quality_summary.json"))
        basis_used = _basis_used(payloads.get("normalized_fundamentals.json"))
        entry_warnings: List[str] = []
        entry_limitations: List[str] = []
        year_eligibility = eligibility_by_year.get(year, {})
        eligibility_status = str(year_eligibility.get("status") or "INELIGIBLE")
        for filename in YEAR_LEVEL_REQUIRED:
            if payloads.get(filename) is None:
                _append_unique(entry_warnings, f"missing {filename}")
        if basis_used == "unknown":
            _append_unique(entry_warnings, "preferred basis unknown")
        if validation_status == "fail":
            _append_unique(entry_limitations, "financial validation failed")
        if reconciliation_status == "fail":
            _append_unique(entry_limitations, "financial reconciliation failed")
        if quality_status == "fail":
            _append_unique(entry_limitations, "financial quality failed")
        if eligibility_status != "ELIGIBLE":
            _append_unique(
                entry_limitations,
                "excluded from company-memory financial synthesis because canonical company-year status is "
                + eligibility_status,
            )
        usable = _year_is_usable(payloads)
        if usable and year in eligible_years:
            years_used.append(year)
        else:
            years_skipped.append(year)
        year_status[year] = {
            "company_year_status": eligibility_status,
            "missing_required_company_year_artifacts": list(year_eligibility.get("missing_required_artifacts", [])),
            "financials_available": _year_available(payloads),
            "validation_status": validation_status,
            "reconciliation_status": reconciliation_status,
            "quality_status": quality_status,
            "basis_used": basis_used,
            "warnings": entry_warnings,
            "limitations": entry_limitations,
        }
    if not years_discovered:
        _append_unique(warnings, "No fiscal-year folders discovered.")
    if len(years_used) <= 1 and years_used:
        _append_unique(warnings, "Only one usable financial year available.")
    if not years_used:
        _append_unique(limitations, "No usable financial years available.")
    payload = {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years_discovered": years_discovered,
        "years_used": years_used,
        "years_skipped": years_skipped,
        "year_status": year_status,
        "company_year_eligibility": eligibility,
        "warnings": warnings,
        "limitations": limitations,
    }
    errors = validate_financial_year_index_payload(payload)
    if errors:
        raise ValueError("Invalid financial year index payload: " + "; ".join(errors))
    return payload


def _collect_points(series: Dict[str, Any]) -> List[Dict[str, Any]]:
    points = series.get("series", []) if isinstance(series, dict) else []
    return [point for point in points if isinstance(point, dict)]


def _latest_numeric_point(points: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for point in reversed(points):
        if isinstance(point.get("value"), (int, float)):
            return point
    return None


def _pattern_line(metric: str, points: Sequence[Dict[str, Any]], unit: str) -> Optional[str]:
    latest = _latest_numeric_point(points)
    if latest is None:
        return None
    year = str(latest.get("year") or "")
    value = latest.get("value")
    suffix = unit or ""
    return f"{metric} in {year}: {value}{(' ' + suffix) if suffix else ''}".strip()


def build_financial_quality_evolution(*, company: str, company_root: Path, years_used: Sequence[str]) -> Dict[str, Any]:
    years = list(years_used)
    evolution: Dict[str, Dict[str, Any]] = {
        "growth_quality": {},
        "margin_quality": {},
        "return_on_capital_quality": {},
        "cash_conversion_quality": {},
        "balance_sheet_strength": {},
        "working_capital_pressure": {},
        "per_share_quality": {},
        "dividend_quality": {},
    }
    recurring_strengths: List[str] = []
    recurring_concerns: List[str] = []
    improving_signals: List[str] = []
    deteriorating_signals: List[str] = []
    missing_data_patterns: List[str] = []
    warnings: List[str] = []
    limitations: List[str] = []

    def section_payload(year: str) -> Dict[str, Any]:
        payload = _load_optional_json(company_root / year / "financials" / "financial_quality_summary.json") or {}
        sections = payload.get("sections")
        if isinstance(sections, dict):
            return sections
        return payload

    quality_map = {
        "growth_quality": "growth_quality",
        "margin_quality": "margin_quality",
        "return_on_capital_quality": "return_on_capital_quality",
        "cash_conversion_quality": "cash_conversion_quality",
        "balance_sheet_strength": "balance_sheet_strength",
        "working_capital_pressure": "working_capital_pressure",
        "per_share_quality": "per_share_quality",
        "dividend_quality": "dividend_quality",
    }

    for key, source_key in quality_map.items():
        by_year: List[Dict[str, Any]] = []
        statuses: List[str] = []
        summaries: List[str] = []
        for year in years:
            section = section_payload(year).get(source_key) or {}
            if not isinstance(section, dict):
                continue
            assessment = str(section.get("assessment") or section.get("status") or "insufficient_data")
            statuses.append(assessment)
            if assessment in {"strong", "adequate"}:
                _append_unique(recurring_strengths, f"{key} shows positive evidence in {year}.")
            if assessment in {"weak"}:
                _append_unique(recurring_concerns, f"{key} shows weak evidence in {year}.")
            for item in section.get("warnings", []) if isinstance(section.get("warnings"), list) else []:
                lowered = str(item).lower()
                if any(token in lowered for token in ("missing", "unavailable", "no usable")):
                    _append_unique(missing_data_patterns, f"{year}: {item}")
            summary = str(section.get("summary") or "").strip()
            if summary:
                summaries.append(summary)
            by_year.append(
                {
                    "year": year,
                    "assessment": assessment,
                    "confidence": section.get("confidence") or "missing",
                    "summary": summary,
                    "highlights": list(section.get("highlights", []) or section.get("signals", [])),
                    "warnings": list(section.get("warnings", [])) if isinstance(section.get("warnings"), list) else [],
                }
            )
        evolution[key] = {"by_year": by_year, "latest_assessment": statuses[-1] if statuses else "insufficient_data"}
        if len(statuses) >= 2:
            if statuses[-1] in {"strong", "adequate"} and statuses[0] in {"mixed", "weak", "insufficient_data"}:
                _append_unique(improving_signals, f"{key} improved by the latest year.")
            if statuses[-1] == "weak" and statuses[0] in {"strong", "adequate", "mixed"}:
                _append_unique(deteriorating_signals, f"{key} weakened by the latest year.")
        if not by_year:
            _append_unique(warnings, f"{key} evolution missing.")

    payload = {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years_covered": years,
        "evolution": evolution,
        "recurring_strengths": recurring_strengths,
        "recurring_concerns": recurring_concerns,
        "improving_signals": improving_signals,
        "deteriorating_signals": deteriorating_signals,
        "missing_data_patterns": missing_data_patterns,
        "warnings": warnings,
        "limitations": limitations,
    }
    errors = validate_financial_quality_evolution_payload(payload)
    if errors:
        raise ValueError("Invalid financial quality evolution payload: " + "; ".join(errors))
    return payload


def build_capital_allocation_financial_timeline(*, company: str, company_root: Path, years_used: Sequence[str]) -> Dict[str, Any]:
    years = list(years_used)
    timeline: List[Dict[str, Any]] = []
    warnings: List[str] = []
    limitations: List[str] = []
    dividend_pattern = {"years": [], "warnings": []}
    capex_pattern = {"years": [], "warnings": []}
    fcf_pattern = {"years": [], "warnings": []}
    dilution_pattern = {"years": [], "warnings": []}
    debt_pattern = {"years": [], "warnings": []}

    for year in years:
        ratios = _load_optional_json(company_root / year / "financials" / "financial_ratios.json") or {}
        actions = _load_optional_json(company_root / year / "financials" / "corporate_actions.json") or {}
        normalized = _load_optional_json(company_root / year / "financials" / "normalized_fundamentals.json") or {}
        ratio_map = ratios.get("ratios") or {}
        debt_entry = ((normalized.get("balance_sheet") or {}).get("total_debt") or {})
        capex_entry = ((normalized.get("cash_flow") or {}).get("capex") or {})
        cfo_entry = ((normalized.get("cash_flow") or {}).get("cfo") or {})
        # Prefer ratio-computed FCF; fall back to deriving from normalized cfo+capex
        # using the same formula as the trend_builder (capex is cash-flow-signed).
        ratio_fcf = (ratio_map.get("fcf") or {}).get("value")
        fcf_value = ratio_fcf
        if fcf_value is None:
            cfo_val = cfo_entry.get("value_crore")
            capex_val = capex_entry.get("value_crore")
            if cfo_val is not None and capex_val is not None:
                fcf_value = round(cfo_val + capex_val, 2)
        fcf_source = "normalized_fundamentals.json" if (ratio_fcf is None and fcf_value is not None) else "financial_ratios.json"
        timeline.append(
            {
                "year": year,
                "dividend_actions": [
                    item for item in (actions.get("actions") or [])
                    if isinstance(item, dict) and "dividend" in str(item.get("action_type") or "").lower()
                ],
                "capex": {
                    "value": capex_entry.get("value_crore"),
                    "source_artifact": capex_entry.get("source_artifact") or "normalized_fundamentals.json",
                },
                "fcf": {
                    "value": fcf_value,
                    "source_artifact": fcf_source,
                },
                "debt": {
                    "value": debt_entry.get("value_crore"),
                    "source_artifact": debt_entry.get("source_artifact") or "normalized_fundamentals.json",
                },
                "share_issue_actions": [
                    item for item in (actions.get("actions") or [])
                    if isinstance(item, dict) and str(item.get("impact_on_share_count") or "") in {"increase", "unknown"}
                ],
            }
        )
        if timeline[-1]["dividend_actions"]:
            dividend_pattern["years"].append(year)
        if capex_entry.get("value_crore") is not None:
            capex_pattern["years"].append(year)
        else:
            _append_unique(limitations, f"{year}: capex missing")
        if fcf_value is not None:
            fcf_pattern["years"].append(year)
        else:
            _append_unique(limitations, f"{year}: FCF missing")
        if debt_entry.get("value_crore") is not None:
            debt_pattern["years"].append(year)
        if any(isinstance(item, dict) and item.get("action_type") in {"qip", "rights_issue", "preferential_issue", "buyback", "bonus_issue", "stock_split"} for item in (actions.get("actions") or [])):
            dilution_pattern["years"].append(year)
    if not any(item.get("capex", {}).get("value") is not None for item in timeline):
        _append_unique(warnings, "Capex missing across usable years.")
    if not any(item.get("fcf", {}).get("value") is not None for item in timeline):
        _append_unique(warnings, "FCF missing across usable years.")
    payload = {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years_covered": years,
        "timeline": timeline,
        "dividend_pattern": dividend_pattern,
        "capex_pattern": capex_pattern,
        "fcf_pattern": fcf_pattern,
        "dilution_or_share_issue_pattern": dilution_pattern,
        "debt_pattern": debt_pattern,
        "warnings": warnings,
        "limitations": limitations,
    }
    errors = validate_capital_allocation_financial_timeline_payload(payload)
    if errors:
        raise ValueError("Invalid capital allocation financial timeline payload: " + "; ".join(errors))
    return payload


def build_ownership_evolution(*, company: str, company_root: Path, years_used: Sequence[str]) -> Dict[str, Any]:
    years = list(years_used)
    category_map = {
        "promoter_holding": "promoter_holding_percent",
        "pledge": "pledged_promoter_holding_percent",
        "fii": "fii_holding_percent",
        "dii": "dii_holding_percent",
        "mutual_funds": "mutual_fund_holding_percent",
        "public": "public_holding_percent",
    }
    payload_lists = {key: [] for key in category_map}
    warnings: List[str] = []
    limitations: List[str] = []

    for year in years:
        shareholding = _load_optional_json(company_root / year / "financials" / "shareholding_pattern.json") or {}
        items = shareholding.get("items", []) if isinstance(shareholding.get("items"), list) else []
        if not items:
            _append_unique(warnings, f"{year}: shareholding missing")
            continue
        for target_key, holder_category in category_map.items():
            match = next((item for item in items if isinstance(item, dict) and item.get("holder_category") == holder_category), None)
            if match is None:
                continue
            payload_lists[target_key].append(
                {
                    "year": year,
                    "value": match.get("holding_percent"),
                    "source_artifact": "shareholding_pattern.json",
                    "confidence": match.get("confidence") or "missing",
                    "warnings": list(match.get("warnings", [])) if isinstance(match.get("warnings"), list) else [],
                }
            )
    institutional_signal = {
        "years_with_data": [
            item["year"]
            for item in payload_lists["fii"] + payload_lists["dii"] + payload_lists["mutual_funds"]
        ],
        "note": "Institutional ownership is a signal, not proof of quality.",
    }
    if not any(payload_lists.values()):
        _append_unique(warnings, "Shareholding pattern missing across usable years.")
    payload = {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years_covered": years,
        "promoter_holding": payload_lists["promoter_holding"],
        "pledge": payload_lists["pledge"],
        "fii": payload_lists["fii"],
        "dii": payload_lists["dii"],
        "mutual_funds": payload_lists["mutual_funds"],
        "public": payload_lists["public"],
        "institutional_signal": institutional_signal,
        "warnings": warnings,
        "limitations": limitations,
    }
    errors = validate_ownership_evolution_payload(payload)
    if errors:
        raise ValueError("Invalid ownership evolution payload: " + "; ".join(errors))
    return payload


def _trend_series_lines(trends: Dict[str, Any], container: str, metrics: Sequence[str]) -> List[str]:
    lines: List[str] = []
    section = trends.get(container) or {}
    if not isinstance(section, dict):
        return lines
    for metric in metrics:
        item = section.get(metric) or {}
        if not isinstance(item, dict):
            continue
        line = _pattern_line(metric, _collect_points(item), str(item.get("unit") or ""))
        if line:
            lines.append(line)
    return lines


def build_financial_memory_summary(
    *,
    company: str,
    trends_payload: Dict[str, Any],
    quality_evolution_payload: Dict[str, Any],
    capital_timeline_payload: Dict[str, Any],
    ownership_payload: Dict[str, Any],
    year_index_payload: Dict[str, Any],
) -> Dict[str, Any]:
    warnings: List[str] = list(year_index_payload.get("warnings", []))
    limitations: List[str] = list(year_index_payload.get("limitations", []))
    warnings.extend([item for item in trends_payload.get("warnings", []) if item not in warnings])
    limitations.extend([item for item in trends_payload.get("limitations", []) if item not in limitations])
    warnings.extend([item for item in quality_evolution_payload.get("warnings", []) if item not in warnings])
    limitations.extend([item for item in quality_evolution_payload.get("limitations", []) if item not in limitations])
    warnings.extend([item for item in capital_timeline_payload.get("warnings", []) if item not in warnings])
    limitations.extend([item for item in capital_timeline_payload.get("limitations", []) if item not in limitations])
    warnings.extend([item for item in ownership_payload.get("warnings", []) if item not in warnings])
    limitations.extend([item for item in ownership_payload.get("limitations", []) if item not in limitations])

    key_strengths = list(quality_evolution_payload.get("recurring_strengths", []))[:8]
    key_concerns = list(quality_evolution_payload.get("recurring_concerns", []))[:8]
    missing_data = list(quality_evolution_payload.get("missing_data_patterns", []))
    missing_data.extend([item for item in limitations if item not in missing_data])

    # Reconcile warnings, limitations, and missing_data against the canonical trend presence.
    # Per the invariant: if a metric is present (non-null, usable_downstream=True) in the
    # canonical financial_trends source, the summary must not simultaneously report it missing.
    # Stale lower-priority artifacts (financial_ratios.json, financial_quality_summary.json,
    # corporate_actions.json) may carry "missing" claims that contradict the canonical fact.
    canonical_presence = _build_trends_presence(trends_payload)
    warnings = _reconcile_canonical_presence(warnings, canonical_presence)
    limitations = _reconcile_canonical_presence(limitations, canonical_presence)
    missing_data = _reconcile_canonical_presence(missing_data, canonical_presence)

    summary = {
        "scale_pattern": _trend_series_lines(trends_payload, "metric_trends", ("revenue", "ebitda", "ebit", "pat", "net_worth", "total_assets")),
        "profitability_pattern": _trend_series_lines(trends_payload, "margin_trends", ("opm", "ebitda_margin", "npm")),
        "return_pattern": _trend_series_lines(trends_payload, "return_trends", ("roe", "roce", "roa")),
        "cash_conversion_pattern": _trend_series_lines(trends_payload, "cash_conversion_trends", ("cfo", "fcf", "cfo_to_pat", "fcf_to_pat")),
        "balance_sheet_pattern": _trend_series_lines(trends_payload, "balance_sheet_trends", ("total_debt", "net_debt", "cash_and_equivalents", "reserves")),
        "working_capital_pattern": _trend_series_lines(trends_payload, "cash_conversion_trends", ("receivable_days", "inventory_days", "payable_days", "cash_conversion_cycle")),
        "per_share_pattern": _trend_series_lines(trends_payload, "per_share_trends", ("eps_basic", "eps_diluted", "book_value_per_share", "share_count")),
        "capital_allocation_pattern": [
            f"Dividend evidence in: {', '.join(capital_timeline_payload.get('dividend_pattern', {}).get('years', []))}" if capital_timeline_payload.get("dividend_pattern", {}).get("years") else "",
            f"Capex evidence in: {', '.join(capital_timeline_payload.get('capex_pattern', {}).get('years', []))}" if capital_timeline_payload.get("capex_pattern", {}).get("years") else "",
            f"Share-issue/dilution-related actions in: {', '.join(capital_timeline_payload.get('dilution_or_share_issue_pattern', {}).get('years', []))}" if capital_timeline_payload.get("dilution_or_share_issue_pattern", {}).get("years") else "",
        ],
        "ownership_pattern": [
            f"Promoter holding tracked across {len(ownership_payload.get('promoter_holding', []))} year(s)." if ownership_payload.get("promoter_holding") else "",
            f"FII/DII/MF ownership tracked across {len(ownership_payload.get('fii', [])) + len(ownership_payload.get('dii', [])) + len(ownership_payload.get('mutual_funds', []))} observations." if any(ownership_payload.get(key) for key in ("fii", "dii", "mutual_funds")) else "",
        ],
    }
    for key, items in summary.items():
        summary[key] = [item for item in items if item]

    status = "pass"
    if not year_index_payload.get("years_used"):
        status = "fail"
    elif warnings or limitations:
        status = "warning"

    investor_questions = list(quality_evolution_payload.get("deteriorating_signals", []))
    if any("capex missing" in item.lower() for item in missing_data):
        _append_unique(investor_questions, "Why is capex evidence missing across usable years?")
    if any("fcf missing" in item.lower() for item in missing_data):
        _append_unique(investor_questions, "Is free cash flow unavailable because capex is missing or because operating cash generation is weak?")
    if any("shareholding" in item.lower() for item in missing_data + warnings):
        _append_unique(investor_questions, "What does the missing ownership evidence hide about promoter control or institutional interest?")

    payload = {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "years_covered": list(trends_payload.get("years_covered", [])),
        "basis_used": str((trends_payload.get("basis_policy") or {}).get("preferred_basis") or trends_payload.get("basis") or "unknown"),
        "summary": summary,
        "key_strengths": key_strengths,
        "key_concerns": key_concerns,
        "missing_data": missing_data,
        "investor_questions": investor_questions[:10],
        "warnings": warnings,
        "limitations": limitations,
        "source_manifest": {
            "years_discovered": list(year_index_payload.get("years_discovered", [])),
            "years_used": list(year_index_payload.get("years_used", [])),
            "years_skipped": list(year_index_payload.get("years_skipped", [])),
            "basis_policy": trends_payload.get("basis_policy") or {
                "preferred_basis": trends_payload.get("basis") or "unknown",
                "basis_consistency": "unknown",
                "warnings": [],
            },
            "financial_artifacts_used": [
                "financial_year_index.json",
                "financial_trends.json",
                "financial_quality_evolution.json",
                "capital_allocation_financial_timeline.json",
                "ownership_evolution.json",
            ],
        },
    }
    errors = validate_financial_memory_summary_payload(payload)
    if errors:
        raise ValueError("Invalid financial memory summary payload: " + "; ".join(errors))
    return payload


def build_financial_memory_artifacts(*, company: str, company_root: Path) -> Dict[str, Dict[str, Any]]:
    year_index = build_financial_year_index(company=company, company_root=company_root)
    years_used = list(year_index.get("years_used", []))
    if not years_used:
        raise RuntimeError(f"financial_memory requires at least one usable financial year for {company}")

    company_fin_root = company_root / "company_memory" / "financials"
    trends_payload = _load_optional_json(company_fin_root / "financial_trends.json") or {}
    if not trends_payload:
        raise RuntimeError("financial_memory requires financial_trends.json")
    quality_evolution = build_financial_quality_evolution(company=company, company_root=company_root, years_used=years_used)
    capital_timeline = build_capital_allocation_financial_timeline(company=company, company_root=company_root, years_used=years_used)
    ownership = build_ownership_evolution(company=company, company_root=company_root, years_used=years_used)
    summary = build_financial_memory_summary(
        company=company,
        trends_payload=trends_payload,
        quality_evolution_payload=quality_evolution,
        capital_timeline_payload=capital_timeline,
        ownership_payload=ownership,
        year_index_payload=year_index,
    )
    manifest = build_financial_memory_manifest(company=company, company_root=company_root)
    truth_pack = build_financial_truth_pack(company=company, company_root=company_root)
    manifest_errors = validate_financial_memory_manifest_payload(manifest)
    if manifest_errors:
        raise ValueError("Invalid financial memory manifest payload: " + "; ".join(manifest_errors))
    truth_pack_errors = validate_financial_truth_pack_payload(truth_pack)
    if truth_pack_errors:
        raise ValueError("Invalid financial truth pack payload: " + "; ".join(truth_pack_errors))
    return {
        "financial_year_index.json": year_index,
        "financial_memory_manifest.json": manifest,
        "financial_truth_pack.json": truth_pack,
        "financial_quality_evolution.json": quality_evolution,
        "capital_allocation_financial_timeline.json": capital_timeline,
        "ownership_evolution.json": ownership,
        "financial_memory_summary.json": summary,
    }


def write_financial_memory_artifacts(*, company: str, company_root: Path, output_dir: Path) -> Dict[str, Path]:
    payloads = build_financial_memory_artifacts(company=company, company_root=company_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}
    for filename, payload in payloads.items():
        path = output_dir / filename
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        written[filename] = path
    return written
