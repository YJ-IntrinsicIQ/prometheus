import json
from pathlib import Path

from knowledge.company_year_eligibility import (
    build_company_year_eligibility_manifest,
    eligible_company_years,
)
from knowledge.financials.financial_memory_truth import build_financial_memory_manifest


def _write_json(path: Path, payload=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload if payload is not None else {"status": "pass"}), encoding="utf-8")


def _write_company_year(root: Path, year: str) -> None:
    _write_json(root / year / "intelligence" / "company_intelligence.json", {"company": "acme", "year": year})
    _write_json(root / year / "intelligence" / "business_classification.json", {"company": "acme", "year": year})


def _write_financial_year(root: Path, year: str) -> None:
    financials = root / year / "financials"
    _write_json(financials / "normalized_fundamentals.json", {"preferred_basis": "consolidated"})
    _write_json(financials / "financial_validation_report.json", {"status": "warning"})
    _write_json(financials / "financial_reconciliation_report.json", {"status": "warning"})
    _write_json(financials / "financial_ratios.json", {"status": "warning", "ratios": {}})
    _write_json(financials / "financial_growth.json", {"status": "warning", "growth": {}})
    _write_json(financials / "financial_quality_summary.json", {"status": "warning"})
    _write_json(financials / "corporate_actions.json", {"status": "pass", "actions": []})
    _write_json(financials / "shareholding_pattern.json", {"status": "pass", "items": []})


def test_canonical_year_eligibility_classifies_partial_financial_year(tmp_path):
    company_root = tmp_path / "companies" / "acme"
    _write_company_year(company_root, "fy24")
    _write_financial_year(company_root, "fy24")
    _write_financial_year(company_root, "fy23")

    manifest = build_company_year_eligibility_manifest(company="acme", company_root=company_root)

    assert manifest["eligible_years"] == ["fy24"]
    assert manifest["partial_years"] == ["fy23"]
    assert manifest["years"]["fy23"]["status"] == "PARTIAL"
    assert "intelligence/company_intelligence.json" in manifest["years"]["fy23"]["missing_required_artifacts"]
    assert eligible_company_years(company="acme", company_root=company_root) == ["fy24"]


def test_financial_memory_manifest_cannot_admit_partial_year_as_company_memory_year(tmp_path):
    company_root = tmp_path / "companies" / "acme"
    _write_company_year(company_root, "fy24")
    _write_financial_year(company_root, "fy24")
    _write_financial_year(company_root, "fy23")

    manifest = build_financial_memory_manifest(company="acme", company_root=company_root)

    assert manifest["years_scanned"] == ["fy23", "fy24"]
    assert manifest["excluded_company_years"]["fy23"]["status"] == "PARTIAL"
    assert "fy23" not in manifest["years_with_partial_financials"]
    assert "fy23" not in manifest["years_with_financial_truth_registry"]


def test_real_ujjivan_fy23_is_partial_and_excluded_from_eligible_scope():
    company_root = Path("companies") / "ujjivan"
    manifest = build_company_year_eligibility_manifest(company="ujjivan", company_root=company_root)

    assert manifest["years"]["fy23"]["status"] == "PARTIAL"
    assert "financials/normalized_fundamentals.json" in manifest["years"]["fy23"]["available_artifacts"]
    assert "intelligence/company_intelligence.json" in manifest["years"]["fy23"]["missing_required_artifacts"]
    assert "fy23" not in manifest["eligible_years"]
