from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from intelligence.investor_panel.committee_brief_renderer import validate_committee_brief_source
from intelligence.investor_panel.doctrine_registry import load_doctrine_registry
from knowledge.company_memory.company_layer import parse_financial_year

from .financial_audit import build_financial_audit_report, build_financial_memory_audit_report


REQUIRED_PCIM_FINANCIAL_SECTIONS = [
    "financial_fundamentals_inputs",
    "financial_trend_inputs",
    "cash_conversion_inputs",
    "return_on_capital_inputs",
    "balance_sheet_strength_inputs",
    "per_share_inputs",
    "corporate_action_inputs",
    "ownership_inputs",
    "financial_driver_inputs",
]

REQUIRED_PCIM_MANIFEST_FIELDS = [
    "financial_artifacts_used",
    "financial_years_covered",
    "financial_status",
    "financial_warnings",
]

REQUIRED_RATIO_FIELDS = [
    "opm",
    "npm",
    "roe",
    "roce",
    "debt_to_equity",
    "cfo_to_pat",
    "fcf_to_pat",
    "book_value_per_share",
]

FINANCIAL_PANEL_SECTIONS = {
    "financial_fundamentals_inputs",
    "financial_trend_inputs",
    "cash_conversion_inputs",
    "return_on_capital_inputs",
    "balance_sheet_strength_inputs",
    "per_share_inputs",
    "corporate_action_inputs",
    "ownership_inputs",
    "financial_driver_inputs",
}

CORE_TRACE_FIELDS = [
    "revenue",
    "pat",
    "net_worth",
    "total_debt",
    "cash_and_equivalents",
]


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _append_unique(items: List[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sorted_years(years: Iterable[str]) -> List[str]:
    unique = []
    for year in years:
        year_text = str(year or "").strip()
        if year_text and year_text not in unique:
            unique.append(year_text)
    return sorted(unique, key=parse_financial_year)


def _discover_company_years(company_root: Path) -> List[str]:
    years = []
    if not company_root.exists():
        return years
    for child in company_root.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        try:
            parse_financial_year(name)
        except ValueError:
            continue
        years.append(name)
    return _sorted_years(years)


def _value_entry(normalized: Dict[str, Any], section: str, field: str) -> Dict[str, Any]:
    return ((normalized.get(section) or {}).get(field) or {}) if isinstance(normalized, dict) else {}


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


def _score_from_findings(*, critical_failures: Sequence[str], warnings: Sequence[str], missing_data: Sequence[str]) -> int:
    score = 100
    score -= min(len(critical_failures), 3) * 20
    score -= min(len(warnings), 10) * 4
    score -= min(len(missing_data), 10) * 3
    score = max(0, score)
    if critical_failures:
        score = min(score, 59)
    return score


def _status_from_score(*, score: int, critical_failures: Sequence[str], warnings: Sequence[str], missing_data: Sequence[str]) -> str:
    if critical_failures or score < 60:
        return "fail"
    if warnings or missing_data or score < 90:
        return "warning"
    return "pass"


def _collect_next_actions(
    *,
    critical_failures: Sequence[str],
    warnings: Sequence[str],
    missing_data: Sequence[str],
) -> List[str]:
    actions: List[str] = []
    combined = [*critical_failures, *warnings, *missing_data]
    joined = "\n".join(combined).lower()
    if "validation" in joined or "pbt" in joined or "period inconsistency" in joined:
        _append_unique(actions, "Tighten financial extraction and normalization until financial validation passes cleanly.")
    if "₹ crore" in joined or "value_crore" in joined:
        _append_unique(actions, "Fix monetary normalization so all core financial values preserve original units and normalize to INR crore.")
    if "traceability" in joined or "source" in joined:
        _append_unique(actions, "Restore source artifact and source page traceability for core financial numbers before trusting downstream analysis.")
    if "cfo" in joined or "fcf" in joined:
        _append_unique(actions, "Improve cash flow extraction and mapping so cash-conversion analysis is usable for investor review.")
    if "shareholding" in joined:
        _append_unique(actions, "Improve shareholding extraction so ownership and pledge analysis are not missing.")
    if "share count" in joined or "book value" in joined or "dilution" in joined:
        _append_unique(actions, "Tighten share-data and corporate-action capture so per-share analysis is reliable.")
    if "basis" in joined or "standalone/consolidated" in joined:
        _append_unique(actions, "Resolve standalone versus consolidated basis ambiguity across normalized fundamentals and trend artifacts.")
    if "pcim" in joined or "manifest" in joined:
        _append_unique(actions, "Rebuild CIM and PCIM after financial_memory completes so panel-facing financial manifest coverage is current.")
    if "committee" in joined:
        _append_unique(actions, "Regenerate committee synthesis and committee brief artifacts after financial inputs are current.")
    if not actions:
        _append_unique(actions, "Address the listed missing data and warnings before treating the fundamentals engine as fully trusted.")
    return actions


def build_fundamentals_acceptance_report(
    *,
    company: str,
    year: str | None = None,
    companies_root: Path | str = Path("companies"),
) -> Dict[str, Any]:
    companies_root = Path(companies_root)
    company_root = companies_root / company
    selected_years = [year] if year else _discover_company_years(company_root)

    critical_failures: List[str] = []
    warnings: List[str] = []
    missing_data: List[str] = []
    checks: List[Dict[str, Any]] = []
    year_summaries: List[Dict[str, Any]] = []

    if not company_root.exists():
        _append_unique(critical_failures, f"Company directory not found: {company_root}")

    if year and year not in _discover_company_years(company_root):
        _append_unique(critical_failures, f"Requested financial year not found: {year}")
    elif not selected_years:
        _append_unique(critical_failures, "No financial years were found for the requested company.")

    for selected_year in selected_years:
        financials_dir = company_root / selected_year / "financials"
        year_report = build_financial_audit_report(
            company=company,
            year=selected_year,
            financials_dir=financials_dir,
        )
        year_summaries.append(
            {
                "year": selected_year,
                "audit_status": year_report.status,
                "warnings": list(year_report.warnings),
                "hard_failures": list(year_report.hard_failures),
            }
        )
        for failure in year_report.hard_failures:
            _append_unique(critical_failures, f"{selected_year}: {failure}")
        for warning in year_report.warnings:
            _append_unique(warnings, f"{selected_year}: {warning}")

        normalized_path = financials_dir / "normalized_fundamentals.json"
        ratios_path = financials_dir / "financial_ratios.json"
        growth_path = financials_dir / "financial_growth.json"
        validation_path = financials_dir / "financial_validation_report.json"
        corporate_actions_path = financials_dir / "corporate_actions.json"
        shareholding_path = financials_dir / "shareholding_pattern.json"

        normalized = _load_json(normalized_path) if normalized_path.exists() else {}
        ratios = _load_json(ratios_path) if ratios_path.exists() else {}
        growth = _load_json(growth_path) if growth_path.exists() else {}
        validation = _load_json(validation_path) if validation_path.exists() else {}
        corporate_actions = _load_json(corporate_actions_path) if corporate_actions_path.exists() else {}
        shareholding = _load_json(shareholding_path) if shareholding_path.exists() else {}

        revenue = _value_entry(normalized, "profit_and_loss", "revenue")
        pat = _value_entry(normalized, "profit_and_loss", "pat")
        cfo = _value_entry(normalized, "cash_flow", "cfo")
        debt = _value_entry(normalized, "balance_sheet", "total_debt")
        cash = _value_entry(normalized, "balance_sheet", "cash_and_equivalents")
        net_worth = _value_entry(normalized, "balance_sheet", "net_worth")
        book_value = ((ratios.get("ratios") or {}).get("book_value_per_share") or {})
        share_count = _value_entry(normalized, "share_data", "shares_outstanding")

        if revenue.get("value_crore") is None:
            _append_unique(critical_failures, f"{selected_year}: revenue missing")
        if pat.get("value_crore") is None:
            _append_unique(critical_failures, f"{selected_year}: PAT missing")
        if cfo.get("value_crore") is None:
            _append_unique(missing_data, f"{selected_year}: CFO missing")
        if ((ratios.get("ratios") or {}).get("fcf") or {}).get("value") is None:
            _append_unique(missing_data, f"{selected_year}: FCF missing")
        if debt.get("value_crore") is None:
            _append_unique(missing_data, f"{selected_year}: debt missing")
        if cash.get("value_crore") is None:
            _append_unique(missing_data, f"{selected_year}: cash missing")
        if net_worth.get("value_crore") is None:
            _append_unique(missing_data, f"{selected_year}: net worth missing")
        if book_value.get("value") is None:
            _append_unique(missing_data, f"{selected_year}: book value per share missing")
        if not share_count.get("value_original"):
            _append_unique(missing_data, f"{selected_year}: share count missing")

        for field_name in CORE_TRACE_FIELDS:
            section = "profit_and_loss" if field_name in {"revenue", "pat"} else "balance_sheet"
            entry = _value_entry(normalized, section, field_name)
            if entry.get("value_crore") is None:
                continue
            if not entry.get("source_artifact") or entry.get("source_page") is None:
                _append_unique(
                    critical_failures,
                    f"{selected_year}: source traceability missing for {field_name}",
                )

        ratio_block = ratios.get("ratios") or {}
        for ratio_name in REQUIRED_RATIO_FIELDS:
            if not isinstance(ratio_block.get(ratio_name), dict) or ratio_block[ratio_name].get("value") is None:
                label = ratio_name.upper() if ratio_name in {"opm", "npm", "roe", "roce"} else ratio_name.replace("_", " ")
                _append_unique(warnings, f"{selected_year}: ratio missing or unusable: {label}")

        if validation.get("status") == "fail":
            _append_unique(critical_failures, f"{selected_year}: financial validation failed")
        if validation.get("status") != "fail" and not ratios_path.exists():
            _append_unique(critical_failures, f"{selected_year}: ratios missing despite valid fundamentals")

        growth_metrics = growth.get("growth_metrics") or {}
        has_yoy = False
        has_cagr = False
        for value in growth_metrics.values():
            items = value if isinstance(value, list) else [value]
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("growth_percent") is not None:
                    has_yoy = True
                if item.get("cagr_percent") is not None:
                    has_cagr = True
        if not has_yoy:
            _append_unique(warnings, f"{selected_year}: YoY growth not available")
        if len(selected_years) > 1 and not has_cagr:
            _append_unique(warnings, f"{selected_year}: CAGR not available despite multi-year selection")

        if corporate_actions.get("per_share_comparability_warnings"):
            for item in corporate_actions["per_share_comparability_warnings"]:
                _append_unique(warnings, f"{selected_year}: {item}")
        if shareholding.get("status") == "warning" or not (shareholding.get("items") or []):
            _append_unique(missing_data, f"{selected_year}: shareholding pattern missing or incomplete")

    company_memory_audit = build_financial_memory_audit_report(company=company, company_root=company_root)
    for failure in company_memory_audit.hard_failures:
        _append_unique(critical_failures, failure)
    for warning in company_memory_audit.warnings:
        _append_unique(warnings, warning)

    company_memory_dir = company_root / "company_memory"
    cim_path = company_memory_dir / "cim_v1.json"
    pcim_path = company_memory_dir / "pcim_v1.json"
    committee_synthesis_path = company_memory_dir / "investor_panel" / "committee_synthesis.json"
    committee_brief_path = company_memory_dir / "investor_panel" / "committee_brief.md"

    cim_payload = _load_json(cim_path) if cim_path.exists() else {}
    pcim_payload = _load_json(pcim_path) if pcim_path.exists() else {}

    financial_intelligence = cim_payload.get("financial_intelligence")
    if not isinstance(financial_intelligence, dict):
        _append_unique(critical_failures, "CIM missing financial_intelligence")
    else:
        checks.append(
            {
                "check_name": "cim_financial_intelligence",
                "status": "pass",
                "details": "CIM includes financial_intelligence",
            }
        )

    manifest = pcim_payload.get("pcim_source_manifest")
    if not isinstance(manifest, dict):
        _append_unique(critical_failures, "PCIM financial manifest missing after integration")
    else:
        missing_manifest_fields = [field for field in REQUIRED_PCIM_MANIFEST_FIELDS if field not in manifest]
        if missing_manifest_fields:
            _append_unique(
                critical_failures,
                "PCIM financial manifest missing required fields: " + ", ".join(missing_manifest_fields),
            )
        if manifest.get("financial_status") == "fail":
            _append_unique(critical_failures, "PCIM financial manifest status is fail")
        for item in manifest.get("financial_warnings", []) if isinstance(manifest.get("financial_warnings"), list) else []:
            _append_unique(warnings, f"PCIM: {item}")

    for section in REQUIRED_PCIM_FINANCIAL_SECTIONS:
        if not isinstance(pcim_payload.get(section), dict):
            _append_unique(critical_failures, f"PCIM missing compact financial section: {section}")
    if any(_contains_source_chunk(pcim_payload.get(section)) for section in REQUIRED_PCIM_FINANCIAL_SECTIONS if section in pcim_payload):
        _append_unique(critical_failures, "PCIM financial sections must not contain source_chunk")

    doctrine_issues = []
    for doctrine in load_doctrine_registry():
        required_sections = set(doctrine.get("evidence_required_from_pcim", []))
        if not (required_sections & FINANCIAL_PANEL_SECTIONS):
            doctrine_issues.append(doctrine.get("doctrine_id", "<unknown>"))
    if doctrine_issues:
        _append_unique(
            critical_failures,
            "Investor panel doctrine coverage missing financial sections for: " + ", ".join(sorted(doctrine_issues)),
        )

    if committee_synthesis_path.exists():
        try:
            validate_committee_brief_source(_load_json(committee_synthesis_path))
            if committee_brief_path.exists():
                brief_text = committee_brief_path.read_text(encoding="utf-8")
                if "## Financial View" not in brief_text:
                    _append_unique(warnings, "committee_brief.md is missing the Financial View section")
            else:
                _append_unique(warnings, "committee_brief.md has not been rendered yet")
        except Exception as exc:  # noqa: BLE001
            _append_unique(warnings, f"Committee brief source is not render-ready: {exc}")
    else:
        _append_unique(warnings, "committee_synthesis.json missing; committee brief Financial View was not verified")

    checks.extend(
        [
            {
                "check_name": "financial_memory_audit",
                "status": company_memory_audit.status,
                "details": f"financial_memory audit status={company_memory_audit.status}",
            },
            {
                "check_name": "years_assessed",
                "status": "pass" if selected_years else "fail",
                "details": ", ".join(selected_years) if selected_years else "No financial years selected",
            },
        ]
    )

    score = _score_from_findings(
        critical_failures=critical_failures,
        warnings=warnings,
        missing_data=missing_data,
    )
    status = _status_from_score(
        score=score,
        critical_failures=critical_failures,
        warnings=warnings,
        missing_data=missing_data,
    )
    ready_for_panel = status != "fail" and score >= 75 and not any(
        "pcim" in item.lower() or "manifest" in item.lower() for item in critical_failures
    )

    report = {
        "company": company,
        "year": year,
        "years_assessed": selected_years,
        "generated_at": utc_now(),
        "status": status,
        "fundamentals_readiness_score": score,
        "ready_for_panel": ready_for_panel,
        "ready_for_valuation": False,
        "critical_failures": critical_failures,
        "warnings": warnings,
        "missing_data": missing_data,
        "recommended_next_actions": _collect_next_actions(
            critical_failures=critical_failures,
            warnings=warnings,
            missing_data=missing_data,
        ),
        "year_audits": year_summaries,
        "financial_memory_audit": {
            "status": company_memory_audit.status,
            "warnings": list(company_memory_audit.warnings),
            "hard_failures": list(company_memory_audit.hard_failures),
        },
        "checks": checks,
    }
    return report


def render_fundamentals_acceptance_markdown(report: Dict[str, Any]) -> str:
    lines = [
        f"# Fundamentals Acceptance Report — {str(report.get('company') or '').title()}",
        "",
        f"**Status:** {report.get('status', 'unknown')}",
        f"**Readiness Score:** {report.get('fundamentals_readiness_score', 0)}",
        f"**Ready for Panel:** {'Yes' if report.get('ready_for_panel') else 'No'}",
        "**Ready for Valuation:** No",
        "",
        f"**Years Assessed:** {', '.join(report.get('years_assessed', []) or ['none'])}",
        "",
        "## Critical Failures",
    ]
    critical = report.get("critical_failures", []) or []
    if critical:
        lines.extend([f"- {item}" for item in critical])
    else:
        lines.append("- None.")

    lines.extend(["", "## Warnings"])
    warnings = report.get("warnings", []) or []
    if warnings:
        lines.extend([f"- {item}" for item in warnings])
    else:
        lines.append("- None.")

    lines.extend(["", "## Missing Data"])
    missing = report.get("missing_data", []) or []
    if missing:
        lines.extend([f"- {item}" for item in missing])
    else:
        lines.append("- None.")

    lines.extend(["", "## Recommended Next Actions"])
    actions = report.get("recommended_next_actions", []) or []
    if actions:
        lines.extend([f"- {item}" for item in actions])
    else:
        lines.append("- None.")

    lines.extend(["", "## Year Audit Summary"])
    for item in report.get("year_audits", []) or []:
        lines.extend(
            [
                "",
                f"### {item.get('year', 'unknown')}",
                f"- Audit status: {item.get('audit_status', 'unknown')}",
                f"- Hard failures: {len(item.get('hard_failures', []) or [])}",
                f"- Warnings: {len(item.get('warnings', []) or [])}",
            ]
        )

    lines.extend(["", "## Financial Memory Audit"])
    memory_audit = report.get("financial_memory_audit") or {}
    lines.extend(
        [
            f"- Status: {memory_audit.get('status', 'unknown')}",
            f"- Hard failures: {len(memory_audit.get('hard_failures', []) or [])}",
            f"- Warnings: {len(memory_audit.get('warnings', []) or [])}",
            "",
        ]
    )
    return "\n".join(lines)


def run_fundamentals_acceptance(
    *,
    company: str,
    year: str | None = None,
    companies_root: Path | str = Path("companies"),
    output_md: bool = False,
) -> Dict[str, Path]:
    companies_root = Path(companies_root)
    report = build_fundamentals_acceptance_report(
        company=company,
        year=year,
        companies_root=companies_root,
    )
    audit_dir = companies_root / company / "audit"
    outputs = {
        "fundamentals_acceptance_report.json": _write_json(
            audit_dir / "fundamentals_acceptance_report.json",
            report,
        )
    }
    if output_md:
        outputs["fundamentals_acceptance_report.md"] = _write_text(
            audit_dir / "fundamentals_acceptance_report.md",
            render_fundamentals_acceptance_markdown(report),
        )
    return outputs
