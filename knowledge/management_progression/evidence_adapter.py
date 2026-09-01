from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


DEDICATED_SOURCES = {
    "company_model": "company_memory/company_model/company_model.json",
    "management_commitments": "company_memory/management_commitments/management_commitments.json",
    "projects_registry": "company_memory/projects/projects_registry.json",
    "project_timelines": "company_memory/projects/project_timelines.json",
    "capacity_registry": "company_memory/capacity/capacity_registry.json",
    "capacity_timelines": "company_memory/capacity/capacity_timelines.json",
    "commentary_themes": "company_memory/management_commentary/commentary_themes.json",
    "capital_allocation_outcomes": "company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json",
    "risk_registry": "company_memory/risks/risk_registry.json",
    # Financial time series — used by the synthesis layer to link management actions
    # to observable metric movements. Loaded read-only; never written back.
    "financial_trends": "company_memory/financials/financial_trends.json",
}

LEGACY_SOURCES = {
    "promise_tracker": "company_memory/multi_year/promise_tracker.json",
    "strategy_timeline": "company_memory/multi_year/strategy_timeline.json",
    "capital_allocation_timeline": "company_memory/multi_year/capital_allocation_timeline.json",
    "risk_evolution": "company_memory/multi_year/risk_evolution.json",
    "management_consistency": "company_memory/multi_year/management_consistency.json",
}


@dataclass
class ManagementProgressionSources:
    company_slug: str
    company_root: Path
    sources: Dict[str, Dict[str, Any]]
    source_files_found: List[str]
    source_files_missing: List[str]
    legacy_adapter_used: bool
    legacy_adapter_sources: List[str]
    warnings: List[str]


def load_management_progression_sources(company_slug: str, *, companies_root: Path | str = Path("companies")) -> ManagementProgressionSources:
    company_root = Path(companies_root) / company_slug
    sources: Dict[str, Dict[str, Any]] = {}
    found: List[str] = []
    missing: List[str] = []
    warnings: List[str] = []
    legacy_used: List[str] = []

    for source_name, relative_path in {**DEDICATED_SOURCES, **LEGACY_SOURCES}.items():
        path = company_root / relative_path
        record: Dict[str, Any] = {
            "relative_path": relative_path,
            "path": str(path),
            "status": "missing",
            "payload": None,
            "error": "",
            "legacy": source_name in LEGACY_SOURCES,
        }
        if not path.exists():
            missing.append(relative_path)
            sources[source_name] = record
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            record["status"] = "invalid"
            record["error"] = str(exc)
            missing.append(relative_path)
            sources[source_name] = record
            continue
        if not isinstance(payload, dict):
            record["status"] = "unsupported"
            missing.append(relative_path)
            sources[source_name] = record
            continue
        artifact_company = artifact_company_slug(payload)
        if artifact_company and artifact_company != company_slug:
            record["status"] = "company_mismatch"
            record["error"] = (
                "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION: "
                f"requested_company={company_slug}; artifact_company={artifact_company}; artifact_path={path}"
            )
            missing.append(relative_path)
            warnings.append(record["error"])
            sources[source_name] = record
            continue
        record["status"] = "loaded"
        record["payload"] = payload
        found.append(relative_path)
        if source_name in LEGACY_SOURCES:
            legacy_used.append(relative_path)
        sources[source_name] = record

    return ManagementProgressionSources(
        company_slug=company_slug,
        company_root=company_root,
        sources=sources,
        source_files_found=found,
        source_files_missing=missing,
        legacy_adapter_used=bool(legacy_used),
        legacy_adapter_sources=sorted(set(legacy_used)),
        warnings=warnings,
    )


def artifact_company_slug(payload: Dict[str, Any]) -> str:
    candidates = [
        payload.get("company_slug"),
        payload.get("company"),
        payload.get("source_company"),
        (payload.get("company_identity") or {}).get("company_slug") if isinstance(payload.get("company_identity"), dict) else None,
        (payload.get("source_manifest") or {}).get("company_slug") if isinstance(payload.get("source_manifest"), dict) else None,
    ]
    for candidate in candidates:
        value = str(candidate or "").strip().lower()
        if re.fullmatch(r"[a-z0-9_-]+", value or ""):
            return value
    return ""


def loaded_payload(sources: ManagementProgressionSources, source_name: str) -> Dict[str, Any]:
    record = sources.sources.get(source_name) or {}
    payload = record.get("payload")
    return payload if record.get("status") == "loaded" and isinstance(payload, dict) else {}

