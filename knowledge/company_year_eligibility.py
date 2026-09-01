from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from knowledge.company_memory import parse_financial_year


ELIGIBLE = "ELIGIBLE"
PARTIAL = "PARTIAL"
INELIGIBLE = "INELIGIBLE"

REQUIRED_COMPANY_YEAR_ARTIFACTS = (
    "intelligence/company_intelligence.json",
    "intelligence/business_classification.json",
)

FINANCIAL_YEAR_ARTIFACTS = (
    "financials/normalized_fundamentals.json",
    "financials/financial_validation_report.json",
    "financials/financial_reconciliation_report.json",
    "financials/financial_ratios.json",
    "financials/financial_growth.json",
    "financials/financial_quality_summary.json",
    "financials/corporate_actions.json",
    "financials/shareholding_pattern.json",
    "financials/financial_fact_registry.json",
)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _sort_years(years: Iterable[str]) -> List[str]:
    return sorted({str(year) for year in years if str(year).strip()}, key=parse_financial_year)


@dataclass(frozen=True)
class CompanyYearEligibility:
    company: str
    year: str
    status: str
    available_artifacts: tuple[str, ...]
    missing_required_artifacts: tuple[str, ...]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "year": self.year,
            "status": self.status,
            "available_artifacts": list(self.available_artifacts),
            "missing_required_artifacts": list(self.missing_required_artifacts),
            "reason": self.reason,
        }


def build_company_year_eligibility_manifest(*, company: str, company_root: Path) -> Dict[str, Any]:
    years = _sort_years(
        child.name
        for child in company_root.iterdir()
        if company_root.exists() and child.is_dir() and child.name.lower().startswith("fy")
    )
    entries: Dict[str, CompanyYearEligibility] = {}
    for year in years:
        year_root = company_root / year
        available: List[str] = []
        for rel_path in (*REQUIRED_COMPANY_YEAR_ARTIFACTS, *FINANCIAL_YEAR_ARTIFACTS):
            if _load_json(year_root / rel_path):
                available.append(rel_path)
        missing_required = [
            rel_path
            for rel_path in REQUIRED_COMPANY_YEAR_ARTIFACTS
            if rel_path not in available
        ]
        if not missing_required:
            status = ELIGIBLE
            reason = "required company-year intelligence artifacts are present"
        elif available:
            status = PARTIAL
            reason = "some year-level artifacts exist but required company-year intelligence artifacts are missing"
        else:
            status = INELIGIBLE
            reason = "no usable company-year artifacts found"
        entries[year] = CompanyYearEligibility(
            company=company,
            year=year,
            status=status,
            available_artifacts=tuple(available),
            missing_required_artifacts=tuple(missing_required),
            reason=reason,
        )

    return {
        "company": company,
        "years": {year: entry.to_dict() for year, entry in entries.items()},
        "eligible_years": [year for year, entry in entries.items() if entry.status == ELIGIBLE],
        "partial_years": [year for year, entry in entries.items() if entry.status == PARTIAL],
        "ineligible_years": [year for year, entry in entries.items() if entry.status == INELIGIBLE],
    }


def eligible_company_years(*, company: str, company_root: Path) -> List[str]:
    manifest = build_company_year_eligibility_manifest(company=company, company_root=company_root)
    return list(manifest["eligible_years"])


def year_eligibility_status(*, company: str, company_root: Path, year: str) -> Dict[str, Any]:
    manifest = build_company_year_eligibility_manifest(company=company, company_root=company_root)
    return dict((manifest.get("years") or {}).get(year, {
        "company": company,
        "year": year,
        "status": INELIGIBLE,
        "available_artifacts": [],
        "missing_required_artifacts": list(REQUIRED_COMPANY_YEAR_ARTIFACTS),
        "reason": "year folder not discovered by canonical eligibility resolver",
    }))
