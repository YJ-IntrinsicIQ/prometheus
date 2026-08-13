from __future__ import annotations

import json
from pathlib import Path

from knowledge.financials.financial_memory_truth import (
    build_financial_memory_manifest,
    build_financial_truth_pack,
)
from knowledge.financials.memory_builder import build_financial_memory_artifacts


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _registry_payload():
    fact = {
        "metric_id": "fcf",
        "metric_name": "Free cash flow",
        "fiscal_year": "fy24",
        "period": "FY24",
        "value": 12.0,
        "unit": "₹ crore",
        "basis": "consolidated",
        "source_statement": "cash_flow",
        "source_artifact": "financial_ratios.json",
        "source_line_item": "fcf",
        "source_page": 10,
        "confidence": "medium",
        "availability_status": "present_derived",
        "derived": True,
        "formula": "cfo + capex",
        "inputs_used": ["cfo", "capex"],
        "warnings": [],
        "reconciliation_status": "pass",
        "usable_downstream": True,
        "notes": ["FCF derived, not explicitly disclosed."],
    }
    return {
        "company": "acme",
        "year": "fy24",
        "generated_at": "2026-07-25T00:00:00Z",
        "source_artifacts_read": ["financial_ratios.json"],
        "registry_warnings": [],
        "available_facts": [],
        "derived_facts": [fact],
        "partial_facts": [],
        "missing_facts": [],
        "precise_missing_facts": [],
        "unreliable_facts": [],
        "invalid_facts": [],
        "quarantined_facts": [],
        "contradiction_summary": {},
        "downstream_readiness": {
            "financial_truth_status": "warning",
            "usable_metrics": ["fcf"],
            "unreliable_metrics": [],
            "invalid_metrics": [],
            "quarantined_metrics": [],
            "missing_metrics": [],
            "downstream_blockers": [],
            "warnings": [],
        },
    }


def _add_available_fact(
    payload: dict,
    *,
    metric_id: str,
    fiscal_year: str,
    value,
    unit: str,
    source_artifact: str = "normalized_fundamentals.json",
    raw_number=None,
) -> None:
    payload.setdefault("available_facts", []).append(
        {
            "metric_id": metric_id,
            "metric_name": metric_id.replace("_", " "),
            "fiscal_year": fiscal_year,
            "period": fiscal_year.upper(),
            "value": value,
            "raw_number": raw_number,
            "unit": unit,
            "basis": "consolidated",
            "source_statement": "synthetic",
            "source_artifact": source_artifact,
            "source_line_item": metric_id,
            "source_page": 10,
            "confidence": "high",
            "availability_status": "present_direct",
            "derived": False,
            "formula": "",
            "inputs_used": [],
            "warnings": [],
            "reconciliation_status": "pass",
            "usable_downstream": True,
            "notes": [],
        }
    )


def _reconciliation_payload():
    return {
        "company": "acme",
        "year": "fy24",
        "generated_at": "2026-07-25T00:00:00Z",
        "contradictions_found": ["fcf missing warning contradicted by derived fact"],
        "resolved_contradictions": [],
        "unresolved_contradictions": [],
        "false_missing_warnings": ["FCF missing"],
        "unreliable_metrics": [],
        "invalid_metrics": [],
        "usable_metrics": ["fcf"],
        "downstream_blockers": [],
        "warning_normalizations": [
            {
                "original_warning": "FCF missing",
                "normalized_warning": "FCF derived, not explicitly disclosed.",
                "affected_metric": "fcf",
                "reason": "present_derived fact contradicts broad missing warning",
                "evidence_used": ["financial_fact_registry.json"],
                "source_artifact": "financial_quality_summary.json",
                "resolution_status": "normalized_to_derived",
            }
        ],
        "invalid_artifact_findings": [],
        "quarantined_artifacts": [],
        "resolved_false_warnings": [],
        "warnings": [],
    }


def _quarantine_payload():
    return {
        "company": "acme",
        "fiscal_year": "fy24",
        "generated_at": "2026-07-25T00:00:00Z",
        "artifact_status_by_file": {},
        "quarantined_facts": [],
        "quarantined_artifacts": [],
        "usable_artifacts": [],
        "invalid_reason": [],
        "affected_metrics": [],
        "downstream_blockers": [],
        "recommended_reparse_targets": [],
        "warnings": [],
    }


def _minimal_partial_year():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "preferred_basis": "consolidated",
        "profit_and_loss": {
            "revenue": {
                "canonical_field": "revenue",
                "value_crore": 120.0,
                "value_original": "120",
                "unit_original": "crores",
                "basis": "consolidated",
                "period": "FY25",
                "source_line_item": "Revenue",
                "source_page": 10,
                "source_artifact": "normalized_fundamentals.json",
                "confidence": "high",
                "warnings": [],
            }
        },
        "balance_sheet": {},
        "cash_flow": {},
        "share_data": {},
        "warnings": [],
        "limitations": [],
    }


def test_financial_memory_manifest_distinguishes_registry_partial_and_missing_years(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    _write_json(company_root / "fy24" / "financials" / "financial_fact_registry.json", _registry_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(company_root / "fy25" / "financials" / "normalized_fundamentals.json", _minimal_partial_year())
    (company_root / "fy23").mkdir(parents=True, exist_ok=True)

    manifest = build_financial_memory_manifest(company="acme", company_root=company_root)

    assert manifest["years_with_financial_truth_registry"] == ["fy24"]
    assert manifest["years_with_partial_financials"] == ["fy25"]
    assert manifest["years_missing_financials"] == ["fy23"]
    assert manifest["financial_memory_status"] in {"warning", "partial"}


def test_financial_truth_pack_blocks_false_missing_warning_when_registry_has_derived_fcf(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    _write_json(company_root / "fy24" / "financials" / "financial_fact_registry.json", _registry_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    assert truth_pack["usable_derived_metrics"][0]["metric_id"] == "fcf"
    assert truth_pack["financial_warnings_blocked_downstream"][0]["original_warning"] == "FCF missing"
    assert truth_pack["financial_warnings_blocked_downstream"][0]["normalized_warning"] == "FCF derived, not explicitly disclosed."


def test_financial_memory_artifacts_include_manifest_and_truth_pack(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    fin_root = company_root / "company_memory" / "financials"
    _write_json(company_root / "fy24" / "financials" / "financial_fact_registry.json", _registry_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(company_root / "fy24" / "financials" / "normalized_fundamentals.json", _minimal_partial_year())
    _write_json(company_root / "fy24" / "financials" / "financial_validation_report.json", {"status": "pass"})
    _write_json(company_root / "fy24" / "financials" / "financial_reconciliation_report.json", {"status": "pass"})
    _write_json(company_root / "fy24" / "financials" / "financial_quality_summary.json", {"status": "pass"})
    _write_json(fin_root / "financial_trends.json", {
        "company": "acme",
        "generated_at": "2026-07-25T00:00:00Z",
        "years_covered": ["fy24"],
        "basis": "consolidated",
        "basis_policy": {"preferred_basis": "consolidated", "basis_consistency": "consistent", "warnings": []},
        "trend_groups": {},
        "metric_trends": {},
        "metric_series": {},
        "ratio_series": {},
        "growth_summary": {},
        "margin_trends": {},
        "return_trends": {},
        "cash_conversion_trends": {},
        "balance_sheet_trends": {},
        "per_share_trends": {},
        "ownership_trends": {},
        "corporate_actions_timeline": [],
        "unreliable_metrics": [],
        "invalid_or_quarantined_metrics": [],
        "warnings": [],
        "limitations": [],
    })

    payloads = build_financial_memory_artifacts(company="acme", company_root=company_root)

    assert "financial_memory_manifest.json" in payloads
    assert "financial_truth_pack.json" in payloads


def test_financial_truth_pack_hydrates_investor_module_metrics_and_panel_status(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    _write_json(company_root / "fy24" / "financials" / "financial_fact_registry.json", _registry_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "owner_earnings_bridge.json",
        {
            "company": "acme",
            "generated_at": "2026-07-25T00:00:00Z",
            "bridges": [
                {
                    "fiscal_year": "fy24",
                    "owner_earnings_estimate": 9.5,
                    "conservative_fcf_after_total_capex": 12.0,
                    "fcf_after_ppe_cwip_capex": 14.0,
                    "owner_earnings_precision_status": "medium",
                    "owner_earnings_warnings": ["Maintenance versus growth capex is estimated."],
                }
            ],
            "warnings": [],
            "limitations": [],
        },
    )
    _write_json(
        modules_dir / "investor_financial_modules_manifest.json",
        {
            "company": "acme",
            "generated_at": "2026-07-25T00:00:00Z",
            "module_statuses": {"owner_earnings_bridge": "pass"},
            "usable_domains": ["owner_earnings"],
            "limited_domains": [],
            "blocked_domains": [],
            "warnings": [],
            "limitations": [],
            "recommended_next_investor_questions": [],
            "source_truth_pack_used": True,
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    derived_metric_ids = {item["metric_id"] for item in truth_pack["usable_derived_metrics"]}
    assert "owner_earnings_estimate" in derived_metric_ids
    assert truth_pack["financial_panel_status"] in {"pass", "warning"}
    assert "owner_earnings" in truth_pack["financial_panel_usable_domains"]


def test_financial_truth_pack_recomputes_tiny_broken_fcf_per_share_from_crore_and_shares(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    registry = _registry_payload()
    registry["available_facts"].append(
        {
            "metric_id": "closing_shares",
            "metric_name": "closing shares",
            "fiscal_year": "fy24",
            "period": "FY24",
            "value": 50_000_000.0,
            "raw_number": 50_000_000.0,
            "unit": "shares",
            "basis": "consolidated",
            "source_statement": "share_data",
            "source_artifact": "normalized_fundamentals.json",
            "source_line_item": "shares_outstanding",
            "source_page": 10,
            "confidence": "high",
            "availability_status": "present_direct",
            "derived": False,
            "formula": "",
            "inputs_used": [],
            "warnings": [],
            "reconciliation_status": "pass",
            "usable_downstream": True,
            "notes": [],
        }
    )
    _write_json(company_root / "fy24" / "financials" / "financial_fact_registry.json", registry)
    _write_json(company_root / "fy24" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "per_share_compounding_analysis.json",
        {
            "company": "acme",
            "generated_at": "2026-07-26T00:00:00Z",
            "years_covered": ["fy24"],
            "analysis": [
                {
                    "fiscal_year": "fy24",
                    "closing_shares": 50_000_000.0,
                    "weighted_average_basic_shares": None,
                    "weighted_average_diluted_shares": None,
                    "fcf_per_share": 0.000002,
                    "dilution_status": "comparability_partial",
                    "per_share_compounding_status": "usable",
                    "source_provenance": ["financial_fact_registry.json"],
                }
            ],
            "warnings": [],
            "limitations": [],
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    fcf_per_share = next(item for item in truth_pack["usable_current_metrics"] if item["metric_id"] == "fcf_per_share")
    assert fcf_per_share["value_per_share"] == 12.0 * 10_000_000 / 50_000_000.0
    assert fcf_per_share["unit"] == "INR/share"
    assert truth_pack["recomputed_metrics"]
    assert truth_pack["unit_validation_warnings"]


def test_financial_truth_pack_preserves_direct_per_share_metrics_without_crore_conversion(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    _write_json(company_root / "fy24" / "financials" / "financial_fact_registry.json", _registry_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "per_share_compounding_analysis.json",
        {
            "company": "acme",
            "generated_at": "2026-07-26T00:00:00Z",
            "years_covered": ["fy24"],
            "analysis": [
                {
                    "fiscal_year": "fy24",
                    "eps_basic": 30.0,
                    "dividend_per_share": 5.0,
                    "per_share_metric_metadata": {
                        "eps_basic": {
                            "metric_id": "eps_basic",
                            "value_per_share": 30.0,
                            "unit": "INR/share",
                            "calculation_formula": "reported_directly",
                            "source_unit": "INR/share",
                            "warnings": [],
                        },
                        "dividend_per_share": {
                            "metric_id": "dividend_per_share",
                            "value_per_share": 5.0,
                            "unit": "INR/share",
                            "calculation_formula": "reported_directly",
                            "source_unit": "INR/share",
                            "warnings": [],
                        },
                    },
                    "dilution_status": "no_material_dilution_detected",
                    "per_share_compounding_status": "usable",
                    "source_provenance": ["financial_fact_registry.json"],
                }
            ],
            "warnings": [],
            "limitations": [],
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    eps_basic = next(item for item in truth_pack["usable_current_metrics"] if item["metric_id"] == "eps_basic")
    dividend = next(item for item in truth_pack["usable_current_metrics"] if item["metric_id"] == "dividend_per_share")
    assert eps_basic["value_per_share"] == 30.0
    assert eps_basic["calculation_formula"] == "reported_directly"
    assert dividend["value_per_share"] == 5.0
    assert dividend["calculation_formula"] == "reported_directly"


def test_financial_truth_pack_quarantines_unrecoverable_tiny_per_share_bug(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    _write_json(company_root / "fy24" / "financials" / "financial_fact_registry.json", _registry_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "per_share_compounding_analysis.json",
        {
            "company": "acme",
            "generated_at": "2026-07-26T00:00:00Z",
            "years_covered": ["fy24"],
            "analysis": [
                {
                    "fiscal_year": "fy24",
                    "fcf_per_share": 0.000002,
                    "per_share_metric_metadata": {
                        "fcf_per_share": {
                            "metric_id": "fcf_per_share",
                            "value_per_share": 0.000002,
                            "unit": "INR/share",
                            "numerator_metric": "fcf",
                            "numerator_value": None,
                            "numerator_unit": "INR crore",
                            "denominator_metric": "closing_shares",
                            "denominator_value": None,
                            "denominator_unit": "shares",
                            "calculation_formula": "value_crore * 10000000 / shares",
                            "share_count_basis": "closing_shares",
                            "warnings": [],
                        }
                    },
                    "dilution_status": "comparability_partial",
                    "per_share_compounding_status": "usable",
                    "source_provenance": ["financial_fact_registry.json"],
                }
            ],
            "warnings": [],
            "limitations": [],
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    unreliable_ids = {item["metric_id"] for item in truth_pack["unreliable_metrics"]}
    assert "fcf_per_share" in unreliable_ids
    assert truth_pack["unit_validation_failures"]


def test_null_derived_per_share_metric_is_not_marked_usable(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    _write_json(company_root / "fy22" / "financials" / "financial_fact_registry.json", _registry_payload())
    _write_json(company_root / "fy22" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy22" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "per_share_compounding_analysis.json",
        {
            "company": "acme",
            "generated_at": "2026-07-26T00:00:00Z",
            "years_covered": ["fy22"],
            "analysis": [
                {
                    "fiscal_year": "fy22",
                    "fcf_per_share": None,
                    "per_share_metric_metadata": {
                        "fcf_per_share": {
                            "metric_id": "fcf_per_share",
                            "value_per_share": None,
                            "unit": "INR/share",
                            "numerator_metric": "fcf",
                            "numerator_value": None,
                            "numerator_unit": "INR crore",
                            "denominator_metric": "closing_shares",
                            "denominator_value": None,
                            "denominator_unit": "shares",
                            "calculation_formula": "fcf_value_crore * 10000000 / closing_shares",
                            "share_count_basis": "closing_shares",
                            "warnings": [],
                        }
                    },
                    "per_share_compounding_status": "partial",
                    "source_provenance": ["financial_fact_registry.json"],
                }
            ],
            "warnings": [],
            "limitations": [],
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    assert "fcf_per_share" not in {item["metric_id"] for item in truth_pack["usable_current_metrics"]}


def test_missing_fcf_per_share_is_classified_as_precise_missing(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    missing_registry = _registry_payload()
    missing_registry["derived_facts"] = []
    missing_registry["downstream_readiness"]["usable_metrics"] = []
    _write_json(company_root / "fy22" / "financials" / "financial_fact_registry.json", missing_registry)
    _write_json(company_root / "fy22" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy22" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "per_share_compounding_analysis.json",
        {
            "company": "acme",
            "generated_at": "2026-07-26T00:00:00Z",
            "years_covered": ["fy22"],
            "analysis": [{"fiscal_year": "fy22", "fcf_per_share": None}],
            "warnings": [],
            "limitations": [],
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    missing_entry = next(item for item in truth_pack["precise_missing_metrics"] if item["metric_id"] == "fcf_per_share")
    assert missing_entry["availability_status"] == "missing"
    assert "fcf" in missing_entry["missing_inputs"]
    assert "closing_shares" in missing_entry["missing_inputs"]


def test_partial_fcf_per_share_is_classified_as_partial_when_shares_missing(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    _write_json(company_root / "fy22" / "financials" / "financial_fact_registry.json", _registry_payload())
    _write_json(company_root / "fy22" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy22" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "per_share_compounding_analysis.json",
        {
            "company": "acme",
            "generated_at": "2026-07-26T00:00:00Z",
            "years_covered": ["fy22"],
            "analysis": [
                {
                    "fiscal_year": "fy22",
                    "per_share_metric_metadata": {
                        "fcf_per_share": {
                            "metric_id": "fcf_per_share",
                            "value_per_share": None,
                            "unit": "INR/share",
                            "numerator_metric": "fcf",
                            "numerator_value": 12.0,
                            "numerator_unit": "INR crore",
                            "denominator_metric": "closing_shares",
                            "denominator_value": None,
                            "denominator_unit": "shares",
                            "calculation_formula": "fcf_value_crore * 10000000 / closing_shares",
                            "share_count_basis": "closing_shares",
                            "warnings": [],
                        }
                    },
                }
            ],
            "warnings": [],
            "limitations": [],
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    partial_entry = next(item for item in truth_pack["partial_metrics"] if item["metric_id"] == "fcf_per_share")
    assert partial_entry["availability_status"] == "partial"
    assert partial_entry["value_per_share"] is None
    assert "closing_shares" in partial_entry["missing_inputs"]


def test_closing_share_warning_is_only_emitted_for_calculated_per_share_metric(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    registry = _registry_payload()
    registry["available_facts"].append(
        {
            "metric_id": "closing_shares",
            "metric_name": "closing shares",
            "fiscal_year": "fy24",
            "period": "FY24",
            "value": 50_000_000.0,
            "raw_number": 50_000_000.0,
            "unit": "shares",
            "basis": "consolidated",
            "source_statement": "share_data",
            "source_artifact": "normalized_fundamentals.json",
            "source_line_item": "shares_outstanding",
            "source_page": 10,
            "confidence": "high",
            "availability_status": "present_direct",
            "derived": False,
            "formula": "",
            "inputs_used": [],
            "warnings": [],
            "reconciliation_status": "pass",
            "usable_downstream": True,
            "notes": [],
        }
    )
    _write_json(company_root / "fy24" / "financials" / "financial_fact_registry.json", registry)
    _write_json(company_root / "fy24" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "per_share_compounding_analysis.json",
        {
            "company": "acme",
            "generated_at": "2026-07-26T00:00:00Z",
            "years_covered": ["fy24"],
            "analysis": [{"fiscal_year": "fy24", "fcf_per_share": 2.4}],
            "warnings": [],
            "limitations": [],
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    assert any("calculated using closing shares" in warning for warning in truth_pack["unit_validation_warnings"])


def test_missing_per_share_metric_does_not_emit_false_calculated_warning(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    _write_json(company_root / "fy23" / "financials" / "financial_fact_registry.json", _registry_payload())
    _write_json(company_root / "fy23" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy23" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "per_share_compounding_analysis.json",
        {
            "company": "acme",
            "generated_at": "2026-07-26T00:00:00Z",
            "years_covered": ["fy23"],
            "analysis": [{"fiscal_year": "fy23", "fcf_per_share": None}],
            "warnings": [],
            "limitations": [],
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    assert not any(
        "fy23:fcf_per_share: Weighted-average shares unavailable; calculated using closing shares." == warning
        for warning in truth_pack["unit_validation_warnings"]
    )


def test_cfo_per_share_is_calculated_when_cfo_and_closing_shares_exist(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    registry = _registry_payload()
    _add_available_fact(registry, metric_id="cfo", fiscal_year="fy24", value=30.0, unit="₹ crore", source_artifact="financial_ratios.json")
    _add_available_fact(registry, metric_id="closing_shares", fiscal_year="fy24", value=50_000_000.0, raw_number=50_000_000.0, unit="shares")
    _write_json(company_root / "fy24" / "financials" / "financial_fact_registry.json", registry)
    _write_json(company_root / "fy24" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "per_share_compounding_analysis.json",
        {
            "company": "acme",
            "generated_at": "2026-07-26T00:00:00Z",
            "years_covered": ["fy24"],
            "analysis": [{"fiscal_year": "fy24", "closing_shares": 50_000_000.0}],
            "warnings": [],
            "limitations": [],
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    metric = next(item for item in truth_pack["usable_current_metrics"] if item["metric_id"] == "cfo_per_share")
    assert metric["value_per_share"] == 30.0 * 10_000_000 / 50_000_000.0
    assert metric["numerator_metric"] == "cfo"
    assert metric["unit"] == "INR/share"


def test_revenue_per_share_is_calculated_when_revenue_and_closing_shares_exist(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    registry = _registry_payload()
    _add_available_fact(registry, metric_id="revenue", fiscal_year="fy24", value=120.0, unit="₹ crore")
    _add_available_fact(registry, metric_id="closing_shares", fiscal_year="fy24", value=50_000_000.0, raw_number=50_000_000.0, unit="shares")
    _write_json(company_root / "fy24" / "financials" / "financial_fact_registry.json", registry)
    _write_json(company_root / "fy24" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "per_share_compounding_analysis.json",
        {
            "company": "acme",
            "generated_at": "2026-07-26T00:00:00Z",
            "years_covered": ["fy24"],
            "analysis": [{"fiscal_year": "fy24", "closing_shares": 50_000_000.0}],
            "warnings": [],
            "limitations": [],
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    metric = next(item for item in truth_pack["usable_current_metrics"] if item["metric_id"] == "revenue_per_share")
    assert metric["value_per_share"] == 120.0 * 10_000_000 / 50_000_000.0
    assert metric["numerator_metric"] == "revenue"
    assert metric["unit"] == "INR/share"


def test_no_partial_metric_is_emitted_when_cfo_and_shares_exist(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    modules_dir = company_root / "company_memory" / "financials" / "investor_financial_modules"
    registry = _registry_payload()
    _add_available_fact(registry, metric_id="cfo", fiscal_year="fy24", value=30.0, unit="₹ crore", source_artifact="financial_ratios.json")
    _add_available_fact(registry, metric_id="closing_shares", fiscal_year="fy24", value=50_000_000.0, raw_number=50_000_000.0, unit="shares")
    _write_json(company_root / "fy24" / "financials" / "financial_fact_registry.json", registry)
    _write_json(company_root / "fy24" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy24" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(
        modules_dir / "per_share_compounding_analysis.json",
        {
            "company": "acme",
            "generated_at": "2026-07-26T00:00:00Z",
            "years_covered": ["fy24"],
            "analysis": [{"fiscal_year": "fy24", "closing_shares": 50_000_000.0}],
            "warnings": [],
            "limitations": [],
        },
    )

    truth_pack = build_financial_truth_pack(company="acme", company_root=company_root)

    partial_ids = {item["metric_id"] for item in truth_pack["partial_metrics"]}
    assert "cfo_per_share" not in partial_ids
