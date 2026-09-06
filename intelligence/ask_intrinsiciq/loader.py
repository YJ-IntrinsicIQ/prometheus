from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


SOURCE_REGISTRY = {
    "cim": "company_memory/cim_v1.json",
    "pcim": "company_memory/pcim_v1.json",
    "company_model": "company_memory/company_model/company_model.json",
    "management_progression": "company_memory/management_progression/management_progression.json",
    "financial_truth_pack": "company_memory/financials/financial_truth_pack.json",
    "financial_trends": "company_memory/financials/financial_trends.json",
    "investor_financial_modules_manifest": "company_memory/financials/investor_financial_modules/investor_financial_modules_manifest.json",
    "owner_earnings_bridge": "company_memory/financials/investor_financial_modules/owner_earnings_bridge.json",
    "working_capital_quality_drilldown": "company_memory/financials/investor_financial_modules/working_capital_quality_drilldown.json",
    "capital_allocation_roi_ledger": "company_memory/financials/investor_financial_modules/capital_allocation_roi_ledger.json",
    "per_share_compounding_analysis": "company_memory/financials/investor_financial_modules/per_share_compounding_analysis.json",
    "committee_synthesis": "company_memory/investor_panel/committee_synthesis.json",
    "graham_analysis": "company_memory/investor_panel/graham_analysis.json",
    "buffett_analysis": "company_memory/investor_panel/buffett_analysis.json",
    "fisher_analysis": "company_memory/investor_panel/fisher_analysis.json",
    "munger_analysis": "company_memory/investor_panel/munger_analysis.json",
    "lynch_analysis": "company_memory/investor_panel/lynch_analysis.json",
    "panel_run_summary": "company_memory/investor_panel/panel_run_summary.json",
    "management_commitments": "company_memory/management_commitments/management_commitments.json",
    "projects_registry": "company_memory/projects/projects_registry.json",
    "project_timelines": "company_memory/projects/project_timelines.json",
    "project_assessments": "company_memory/projects/project_assessments.json",
    "capacity_registry": "company_memory/capacity/capacity_registry.json",
    "capacity_timelines": "company_memory/capacity/capacity_timelines.json",
    "capacity_assessments": "company_memory/capacity/capacity_assessments.json",
    "risk_evolution": "company_memory/multi_year/risk_evolution.json",
    "risk_assessments": "company_memory/risks/risk_assessments.json",
    "risk_timelines": "company_memory/risks/risk_timelines.json",
    "commentary_themes": "company_memory/management_commentary/commentary_themes.json",
    "commentary_assessments": "company_memory/management_commentary/commentary_assessments.json",
    "commentary_timelines": "company_memory/management_commentary/commentary_timelines.json",
    "management_quality_summary": "company_memory/management_quality/management_quality_summary.json",
    "management_quality_dimensions": "company_memory/management_quality/management_quality_dimensions.json",
    "capital_allocation_outcomes": "company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json",
    "capital_allocation_assessments": "company_memory/capital_allocation_outcomes/capital_allocation_assessments.json",
    "capital_allocation_longitudinal_profile": "company_memory/capital_allocation_outcomes/capital_allocation_longitudinal_profile.json",
    "capital_allocation_timelines": "company_memory/capital_allocation_timeline.json",
    "company_memory_index": "company_memory/company_memory_index.json",
    "multi_year_company_year_index": "company_memory/multi_year/company_year_index.json",
    "multi_year_strategy_timeline": "company_memory/multi_year/strategy_timeline.json",
    "multi_year_business_dna_evolution": "company_memory/multi_year/business_dna_evolution.json",
    # Gold intelligence layers
    "gold_promise_tracker": "company_memory/gold/management_promise_tracker.json",
    "gold_capital_allocation": "company_memory/gold/capital_allocation_outcome_tracker.json",
    "gold_strategy_evolution": "company_memory/gold/strategy_evolution_timeline.json",
    "gold_risk_evolution": "company_memory/gold/risk_evolution_timeline.json",
    "gold_credibility": "company_memory/gold/management_credibility_synthesis.json",
}


def _iso_from_timestamp(timestamp: float | None) -> str:
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_company_slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("-", "_")
    if re.fullmatch(r"[a-z0-9_]+", text):
        return text
    return ""


def _artifact_company_slug(payload: Dict[str, Any]) -> str:
    candidates = [
        payload.get("company_slug"),
        payload.get("source_company"),
        (payload.get("metadata") or {}).get("company") if isinstance(payload.get("metadata"), dict) else None,
        (payload.get("company_identity") or {}).get("company_slug") if isinstance(payload.get("company_identity"), dict) else None,
    ]
    for candidate in candidates:
        value = _canonical_company_slug(candidate)
        if value:
            return value
    return _canonical_company_slug(payload.get("company"))


def load_company_memory_sources(company_slug: str) -> Dict[str, Any]:
    company_slug = _canonical_company_slug(company_slug)
    company_root = Path("companies") / company_slug
    sources: Dict[str, Any] = {}
    found: List[str] = []
    missing: List[str] = []

    for source_name, relative_path in SOURCE_REGISTRY.items():
        path = company_root / relative_path
        record: Dict[str, Any] = {
            "path": str(path),
            "relative_path": relative_path,
            "status": "missing",
            "payload": None,
            "error": "",
        }
        if not path.exists():
            missing.append(relative_path)
            sources[source_name] = record
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            record["status"] = "loaded" if isinstance(payload, dict) else "unsupported"
            if isinstance(payload, dict):
                artifact_company = _artifact_company_slug(payload)
                if artifact_company and artifact_company != company_slug:
                    record["status"] = "company_mismatch"
                    record["error"] = (
                        "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION: "
                        f"requested_company={company_slug}; artifact_company={artifact_company}; artifact_path={path}"
                    )
                    record["failure_class"] = "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION"
                    missing.append(relative_path)
                    sources[source_name] = record
                    continue
            record["payload"] = payload
            record["generated_at"] = str(payload.get("generated_at") or "") if isinstance(payload, dict) else ""
            try:
                record["file_mtime"] = _iso_from_timestamp(path.stat().st_mtime)
            except OSError:
                record["file_mtime"] = ""
            if record["status"] == "loaded":
                found.append(relative_path)
            else:
                missing.append(relative_path)
        except (OSError, json.JSONDecodeError) as exc:
            record["status"] = "invalid"
            record["error"] = str(exc)
            missing.append(relative_path)
        sources[source_name] = record

    return {
        "company_slug": company_slug,
        "company_root": str(company_root),
        "sources": sources,
        "source_files_considered": list(SOURCE_REGISTRY.values()),
        "source_files_found": found,
        "source_files_missing": missing,
    }
