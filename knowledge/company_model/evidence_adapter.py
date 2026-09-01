from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CompanyModelSources:
    company_slug: str
    company_root: Path
    sources: Dict[str, Dict[str, Any]]
    source_files_found: List[str]
    source_files_missing: List[str]
    legacy_adapter_used: bool
    legacy_adapter_sources: List[str]
    warnings: List[str]


GOVERNED_SOURCE_FILES = {
    "pcim": "company_memory/pcim_v1.json",
    "cim": "company_memory/cim_v1.json",
    "company_memory_index": "company_memory/company_memory_index.json",
    "multi_year_business_dna_evolution": "company_memory/multi_year/business_dna_evolution.json",
    "multi_year_strategy_timeline": "company_memory/multi_year/strategy_timeline.json",
}

LEGACY_ADAPTER_SOURCE_NAMES = {
    "pcim",
    "cim",
    "company_memory_index",
    "multi_year_business_dna_evolution",
    "multi_year_strategy_timeline",
}


def load_company_model_sources(company_slug: str, *, companies_root: Path | str = Path("companies")) -> CompanyModelSources:
    company_root = Path(companies_root) / company_slug
    sources: Dict[str, Dict[str, Any]] = {}
    found: List[str] = []
    missing: List[str] = []
    warnings: List[str] = []
    legacy_sources: List[str] = []

    for source_name, relative_path in GOVERNED_SOURCE_FILES.items():
        path = company_root / relative_path
        record: Dict[str, Any] = {
            "relative_path": relative_path,
            "path": str(path),
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
            sources[source_name] = record
            warnings.append(record["error"])
            continue
        record["status"] = "loaded"
        record["payload"] = payload
        found.append(relative_path)
        if source_name in LEGACY_ADAPTER_SOURCE_NAMES:
            legacy_sources.append(relative_path)
        sources[source_name] = record

    for year_dir in sorted(company_root.glob("fy*/intelligence")):
        year = year_dir.parent.name
        for filename in ("business_blueprint.json", "business_classification.json"):
            key = f"{year}_{filename.removesuffix('.json')}"
            relative_path = f"{year}/intelligence/{filename}"
            path = year_dir / filename
            record = {
                "relative_path": relative_path,
                "path": str(path),
                "status": "missing",
                "payload": None,
                "error": "",
                "year": year,
            }
            if not path.exists():
                missing.append(relative_path)
                sources[key] = record
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                record["status"] = "invalid"
                record["error"] = str(exc)
                missing.append(relative_path)
                sources[key] = record
                continue
            if isinstance(payload, dict):
                artifact_company = artifact_company_slug(payload)
                if artifact_company and artifact_company != company_slug:
                    record["status"] = "company_mismatch"
                    record["error"] = (
                        "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION: "
                        f"requested_company={company_slug}; artifact_company={artifact_company}; artifact_path={path}"
                    )
                    missing.append(relative_path)
                    warnings.append(record["error"])
                    sources[key] = record
                    continue
            record["status"] = "loaded" if isinstance(payload, dict) else "unsupported"
            record["payload"] = payload
            found.append(relative_path)
            sources[key] = record

    return CompanyModelSources(
        company_slug=company_slug,
        company_root=company_root,
        sources=sources,
        source_files_found=found,
        source_files_missing=missing,
        legacy_adapter_used=bool(legacy_sources),
        legacy_adapter_sources=sorted(set(legacy_sources)),
        warnings=warnings,
    )


def artifact_company_slug(payload: Dict[str, Any]) -> str:
    candidates = [
        payload.get("company_slug"),
        payload.get("source_company"),
        payload.get("company"),
        (payload.get("metadata") or {}).get("company") if isinstance(payload.get("metadata"), dict) else None,
        (payload.get("company_identity") or {}).get("company_slug") if isinstance(payload.get("company_identity"), dict) else None,
    ]
    for candidate in candidates:
        value = str(candidate or "").strip().lower()
        if value and re.fullmatch(r"[a-z0-9_-]+", value):
            return value
    return ""


def loaded_payload(sources: CompanyModelSources, source_name: str) -> Dict[str, Any]:
    record = sources.sources.get(source_name) or {}
    payload = record.get("payload")
    return payload if isinstance(payload, dict) and record.get("status") == "loaded" else {}


def yearly_payloads(sources: CompanyModelSources, suffix: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for key, record in sources.sources.items():
        if not key.endswith(suffix) or record.get("status") != "loaded":
            continue
        payload = record.get("payload")
        if isinstance(payload, dict):
            results.append({"year": record.get("year") or "", "payload": payload, "relative_path": record.get("relative_path") or ""})
    return sorted(results, key=lambda item: _year_sort_key(item.get("year")))


def _year_sort_key(value: Any) -> int:
    text = str(value or "").lower()
    match = re.search(r"(\d{2,4})", text)
    if not match:
        return -1
    number = int(match.group(1))
    return number % 100 if number >= 100 else number

