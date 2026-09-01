from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge.financials.financial_audit import (
    build_financial_audit_report,
    build_financial_memory_audit_report,
    write_financial_audit_report,
    write_financial_memory_audit_report,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _discovery_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "source_documents": ["annual_report.pdf"],
        "sections": {
            "primary_profit_and_loss_statement": [
                {
                    "section_type": "primary_profit_and_loss_statement",
                    "source_artifact": "annual_report.pdf",
                    "page": 10,
                    "chunk_id": "chunk-1",
                    "text_excerpt": "Statement of Profit and Loss",
                    "confidence": "high",
                    "reasoning": "Heading matched.",
                    "basis": "consolidated",
                    "basis_confidence": "high",
                    "signals": ["heading"],
                }
            ],
            "primary_balance_sheet_statement": [],
            "primary_cash_flow_statement": [],
            "statement_of_changes_in_equity": [],
            "financial_note": [],
            "accounting_policy": [],
            "auditor_report": [],
            "management_discussion_financial_summary": [],
            "share_capital_note": [],
            "eps_note": [],
            "dividend_note": [],
            "shareholding_note": [],
            "corporate_action_note": [],
            "irrelevant_financial_text": [],
            "schedule_6_cash_rbi": [],
            "schedule_7_balances_banks": [],
            "schedule_8_investments": [],
            "schedule_9_advances": [],
            "schedule_10_fixed_assets": [],
            "schedule_11_other_assets": [],
            "schedule_13_interest_earned": [],
            "schedule_14_other_income": [],
            "schedule_15_interest_expended": [],
            "schedule_16_operating_expenses": [],
        },
        "warnings": [],
        "limitations": [],
    }


def _row(table_type: str, line_item_raw: str, value_raw: str, value_crore: float):
    value_type = "per_share" if table_type == "eps" else "monetary"
    return {
        "statement_type": table_type,
        "table_type": table_type,
        "basis": "consolidated",
        "line_item_raw": line_item_raw,
        "values": [
            {
                "period": "FY25",
                "value_raw": value_raw,
                "unit_hint": "crores",
                "currency_hint": "INR",
                "value_crore": value_crore,
                "value_type": value_type,
                "raw_number": float(value_raw) if value_raw not in {"", None} else None,
            }
        ],
        "source_artifact": "annual_report.pdf",
        "page": 10,
        "chunk_id": f"{table_type}-{line_item_raw}",
        "confidence": "high",
        "source_section_type": "primary_profit_and_loss_statement" if table_type == "profit_and_loss" else "financial_note",
        "table_confidence": "high",
        "table_rejection_risk": [],
        "is_primary_statement": table_type in {"profit_and_loss", "balance_sheet", "cash_flow"},
        "warnings": [],
    }


def _extraction_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "source_documents": ["annual_report.pdf"],
        "tables": {
            "profit_and_loss": [_row("profit_and_loss", "Revenue", "120", 120.0)],
            "balance_sheet": [_row("balance_sheet", "Total assets", "220", 220.0)],
            "cash_flow": [_row("cash_flow", "Cash from operations", "18", 18.0)],
            "statement_of_changes_in_equity": [],
            "share_capital": [],
            "reserves": [],
            "borrowings": [],
            "fixed_assets": [],
            "revenue": [],
            "tax": [],
            "eps": [],
            "dividend": [],
            "corporate_actions": [],
            "shareholding_pattern": [],
            "investment_schedule": [],
            "lease_note": [],
            "management_discussion_financial_summary": [],
        },
        "rejections": [],
        "warnings": [],
        "limitations": [],
    }


def _normalized_entry(field: str, *, value_crore=None, value_original="", unit_original="crores"):
    return {
        "canonical_field": field,
        "value_crore": value_crore,
        "value_original": value_original,
        "unit_original": unit_original,
        "basis": "consolidated",
        "period": "FY25",
        "source_line_item": field,
        "source_page": 10,
        "source_artifact": "annual_report.pdf",
        "confidence": "high",
        "warnings": [],
        "source_section_type": "financial_note",
        "statement_type": "balance_sheet" if field in {"net_worth", "total_debt", "total_assets", "cash_and_equivalents"} else "profit_and_loss",
        "source_value_type": "monetary",
    }


def _normalized_payload(*, cfo_value: float | None = 18.0, share_count_original: str = "1000000"):
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "preferred_basis": "consolidated",
        "basis_confidence": "high",
        "basis_manifest": {
            "preferred_basis": "consolidated",
            "basis_options_available": ["consolidated"],
            "selected_basis_reason": "synthetic test payload",
            "basis_confidence": "high",
            "field_basis_selection": [],
            "basis_warnings": [],
        },
        "profit_and_loss": {
            "revenue": _normalized_entry("revenue", value_crore=120.0, value_original="120"),
            "pat": _normalized_entry("pat", value_crore=14.0, value_original="14"),
        },
        "balance_sheet": {
            "net_worth": _normalized_entry("net_worth", value_crore=80.0, value_original="80"),
            "total_debt": _normalized_entry("total_debt", value_crore=30.0, value_original="30"),
            "total_assets": _normalized_entry("total_assets", value_crore=220.0, value_original="220"),
            "cash_and_equivalents": _normalized_entry("cash_and_equivalents", value_crore=12.0, value_original="12"),
        },
        "cash_flow": {
            "cfo": _normalized_entry(
                "cfo",
                value_crore=cfo_value,
                value_original="" if cfo_value is None else str(cfo_value),
            ),
            "capex": _normalized_entry("capex", value_crore=9.0, value_original="9"),
            "fcf": _normalized_entry("fcf", value_crore=9.0 if cfo_value is not None else None, value_original="9" if cfo_value is not None else ""),
        },
        "share_data": {
            "shares_outstanding": _normalized_entry(
                "shares_outstanding",
                value_crore=None,
                value_original=share_count_original,
                unit_original="shares",
            )
        },
        "shareholding_pattern": {},
        "warnings": [],
        "limitations": [],
        "unmapped_rows": [],
    }


def _ratio_item(name: str, value, unit="%", warnings=None):
    return {
        "ratio_name": name,
        "value": value,
        "unit": unit,
        "formula": f"{name}_formula",
        "inputs_used": [{"name": "input", "value": 1.0, "unit": unit}],
        "basis": "consolidated",
        "confidence": "high" if value is not None else "missing",
        "warnings": list(warnings or []),
        "source_artifacts": ["annual_report.pdf"],
    }


def _ratios_payload(*, roce=15.0, fcf=9.0):
    names = (
        "gross_margin","ebitda_margin","ebit_margin","opm","npm","roe","roce","roa","debt_to_equity","net_debt",
        "net_debt_to_equity","interest_coverage","cfo_to_pat","fcf","fcf_to_pat","fcf_margin","receivable_days",
        "inventory_days","payable_days","cash_conversion_cycle","eps_basic","eps_diluted","book_value_per_share",
        "tangible_book_value_per_share","dividend_per_share","payout_ratio"
    )
    ratios = {name: _ratio_item(name, None, unit="x") for name in names}
    ratios.update(
        {
            "roe": _ratio_item("roe", 12.0),
            "roce": _ratio_item("roce", roce),
            "debt_to_equity": _ratio_item("debt_to_equity", 37.5),
            "cfo_to_pat": _ratio_item("cfo_to_pat", 128.0),
            "fcf": _ratio_item("fcf", fcf, unit="₹ crore"),
            "fcf_to_pat": _ratio_item("fcf_to_pat", 64.0),
            "eps_basic": _ratio_item("eps_basic", 14.0, unit="per share"),
            "book_value_per_share": _ratio_item("book_value_per_share", 80.0, unit="per share"),
        }
    )
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "pass",
        "basis_used": "consolidated",
        "basis_confidence": "high",
        "basis_warnings": [],
        "warnings": [],
        "ratios": ratios,
        "limitations": [],
    }


def _growth_item(metric: str):
    return {
        "metric": metric,
        "current_year": "fy25",
        "previous_year": "fy24",
        "current_value": 1.0,
        "previous_value": 1.0,
        "absolute_change": 1.0,
        "growth_percent": 10.0,
        "cagr_percent": 10.0,
        "unit": "%",
        "basis": "consolidated",
        "confidence": "high",
        "warnings": [],
    }


def _growth_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "pass",
        "basis_used": "consolidated",
        "basis_confidence": "high",
        "years_available": ["fy24", "fy25"],
        "growth_metrics": {
            "revenue": _growth_item("revenue"),
            "pat": _growth_item("pat"),
            "cfo": _growth_item("cfo"),
            "fcf": _growth_item("fcf"),
        },
        "margin_changes": {
            "opm": _growth_item("opm"),
        },
        "basis_warnings": [],
        "warnings": [],
        "limitations": [],
    }


def _validation_payload(status="pass"):
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "status": status,
        "basis_checked": "consolidated",
        "hard_failures": [] if status != "fail" else ["Revenue missing"],
        "warnings": [],
        "checks": [{"check_name": "ready", "status": "pass", "details": "ok"}],
        "missing_fields": [],
        "suspicious_values": [],
        "limitations": [],
    }


def _reconciliation_payload(status="pass"):
    checks = {
        field: {
            "field_name": field,
            "status": "pass",
            "hard_failure": False,
            "reason": "ok",
            "source_line_item": field,
            "source_section_type": "primary_profit_and_loss_statement",
            "statement_type": "profit_and_loss",
            "basis": "consolidated",
            "source_artifacts": ["annual_report.pdf"],
            "warnings": [],
        }
        for field in [
            "revenue",
            "pat",
            "total_assets",
            "eps_basic",
            "eps_diluted",
            "shares_outstanding",
            "weighted_avg_shares",
            "diluted_shares",
        ]
    }
    for field in ("shares_outstanding", "weighted_avg_shares", "diluted_shares"):
        checks[field]["source_section_type"] = "share_capital_note"
        checks[field]["statement_type"] = "share_capital"
        checks[field]["source_value_type"] = "share_count"
    for field in ("eps_basic", "eps_diluted"):
        checks[field]["source_section_type"] = "eps_note"
        checks[field]["source_value_type"] = "per_share"
    hard_failures = [] if status != "fail" else ["Revenue reconciliation failed"]
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "status": status,
        "checks": checks,
        "hard_failures": hard_failures,
        "warnings": [],
        "limitations": [],
    }


def _corporate_actions_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "warning",
        "actions": [],
        "share_count_summary": {
            "opening_shares": 1000000,
            "closing_shares": 1100000,
            "weighted_avg_shares": 1050000,
            "diluted_shares": 1110000,
            "face_value": 10.0,
            "share_count_events": [],
        },
        "rejection_reasons": [],
        "per_share_comparability_warnings": ["QIP may affect comparability"],
        "warnings": [],
        "limitations": [],
    }


def _shareholding_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "pass",
        "items": [
            {
                "holder_category": "promoter_holding_percent",
                "period": "fy25",
                "holding_percent": 52.0,
                "shares_held": None,
                "change_percent": None,
                "source_line_item": "promoter",
                "source_page": 20,
                "source_artifact": "shareholding_pattern.json",
                "confidence": "high",
                "warnings": [],
            }
        ],
        "ownership_summary": {
            "promoter_control": "stable",
            "institutional_interest": "visible",
            "pledge_risk": "low",
            "public_float": "moderate",
            "notable_changes": [],
        },
        "searched_sections": ["shareholding_pattern"],
        "rejection_reasons": [],
        "warnings": [],
        "limitations": [],
    }


def _write_year_artifacts(financials_dir: Path) -> None:
    _write_json(financials_dir / "financial_discovery.json", _discovery_payload())
    _write_json(financials_dir / "raw_financial_tables.json", _extraction_payload())
    _write_json(financials_dir / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financials_dir / "financial_validation_report.json", _validation_payload())
    _write_json(financials_dir / "financial_reconciliation_report.json", _reconciliation_payload())
    _write_json(financials_dir / "financial_ratios.json", _ratios_payload())
    _write_json(financials_dir / "financial_growth.json", _growth_payload())
    _write_json(financials_dir / "corporate_actions.json", _corporate_actions_payload())
    _write_json(financials_dir / "shareholding_pattern.json", _shareholding_payload())


def _trend_series(metric: str, value: float):
    return {
        "metric": metric,
        "unit": "₹ crore",
        "series": [
            {
                "year": "fy25",
                "value": value,
                "basis": "consolidated",
                "source_artifact": "normalized_fundamentals.json",
                "confidence": "high",
                "metric_name": metric,
                "availability_status": "available",
                "source_statement": "profit_and_loss",
                "derived": False,
                "formula": "",
                "usable_downstream": True,
                "warnings": [],
            }
        ],
        "comparability_warnings": [],
    }


def _growth_summary_point():
    return {
        "year": "fy25",
        "growth_percent": 10.0,
        "cagr_percent": 10.0,
        "absolute_change": 5.0,
        "basis": "consolidated",
        "source_artifact": "financial_growth.json",
        "confidence": "high",
        "warnings": [],
    }


def _financial_trends_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy25"],
        "basis": "consolidated",
        "basis_policy": {"preferred_basis": "consolidated", "basis_consistency": "consistent", "warnings": []},
        "trend_groups": {},
        "metric_trends": {"revenue": _trend_series("revenue", 120.0), "pat": _trend_series("pat", 14.0)},
        "metric_series": {
            "revenue": [{"year": "fy25", "value": 120.0, "unit": "₹ crore", "basis": "consolidated", "confidence": "high", "source_artifacts": ["normalized_fundamentals.json"], "warnings": []}],
            "pat": [{"year": "fy25", "value": 14.0, "unit": "₹ crore", "basis": "consolidated", "confidence": "high", "source_artifacts": ["normalized_fundamentals.json"], "warnings": []}],
        },
        "ratio_series": {},
        "growth_summary": {"revenue": [_growth_summary_point()]},
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
    }


def _financial_quality_payload():
    section = {"status": "insufficient_data", "summary": "Limited.", "signals": [], "warnings": [], "metrics": {}}
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy25"],
        "status": "warning",
        "overall_financial_quality": "insufficient_data",
        "current_year_snapshot": {},
        "multi_year_trend_quality": {},
        "growth_quality": section,
        "profitability_quality": section,
        "margin_quality": section,
        "return_on_capital_quality": section,
        "cash_conversion_quality": section,
        "balance_sheet_strength": section,
        "debt_quality": section,
        "working_capital_quality": section,
        "per_share_quality": section,
        "dilution_and_corporate_action_quality": section,
        "ownership_quality": section,
        "capital_allocation_quality": section,
        "red_flags": [],
        "positive_signals": [],
        "missing_data": ["CFO missing"],
        "precise_missing_data": [],
        "unreliable_data": [],
        "invalid_or_quarantined_data": [],
        "warnings": [],
        "limitations": [],
    }


def _financial_attribution_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy25"],
        "status": "warning",
        "attributions": [],
        "attribution_readiness": {"status": "insufficient_data", "reason": "Only one year available."},
        "warnings": ["Only one year available."],
        "limitations": [],
    }


def _financial_year_index_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_discovered": ["fy25"],
        "years_used": ["fy25"],
        "years_skipped": [],
        "year_status": {
            "fy25": {
                "financials_available": True,
                "validation_status": "pass",
                "reconciliation_status": "pass",
                "quality_status": "warning",
                "basis_used": "consolidated",
                "warnings": [],
                "limitations": [],
            }
        },
        "warnings": ["Only one usable financial year available."],
        "limitations": [],
    }


def _financial_quality_evolution_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy25"],
        "evolution": {
            "growth_quality": {"by_year": [{"year": "fy25", "assessment": "insufficient_data", "confidence": "missing", "summary": "Limited.", "highlights": [], "warnings": []}], "latest_assessment": "insufficient_data"},
            "margin_quality": {},
            "return_on_capital_quality": {},
            "cash_conversion_quality": {},
            "balance_sheet_strength": {},
            "working_capital_pressure": {},
            "per_share_quality": {},
            "dividend_quality": {},
        },
        "recurring_strengths": [],
        "recurring_concerns": [],
        "improving_signals": [],
        "deteriorating_signals": [],
        "missing_data_patterns": ["fy25: CFO missing"],
        "warnings": [],
        "limitations": [],
    }


def _capital_allocation_financial_timeline_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy25"],
        "timeline": [],
        "dividend_pattern": {"years": ["fy25"], "warnings": []},
        "capex_pattern": {"years": ["fy25"], "warnings": []},
        "fcf_pattern": {"years": ["fy25"], "warnings": []},
        "dilution_or_share_issue_pattern": {"years": [], "warnings": []},
        "debt_pattern": {"years": ["fy25"], "warnings": []},
        "warnings": [],
        "limitations": [],
    }


def _ownership_evolution_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy25"],
        "promoter_holding": [{"year": "fy25", "value": 52.0, "source_artifact": "shareholding_pattern.json", "confidence": "high", "warnings": []}],
        "pledge": [],
        "fii": [],
        "dii": [],
        "mutual_funds": [],
        "public": [],
        "institutional_signal": {"years_with_data": [], "note": "Institutional ownership is a signal, not proof of quality."},
        "warnings": [],
        "limitations": [],
    }


def _financial_memory_summary_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "warning",
        "years_covered": ["fy25"],
        "basis_used": "consolidated",
        "summary": {
            "scale_pattern": ["revenue in fy25: 120.0 ₹ crore"],
            "profitability_pattern": [],
            "return_pattern": [],
            "cash_conversion_pattern": [],
            "balance_sheet_pattern": [],
            "working_capital_pattern": [],
            "per_share_pattern": [],
            "capital_allocation_pattern": [],
            "ownership_pattern": [],
        },
        "key_strengths": [],
        "key_concerns": [],
        "missing_data": ["fy25: CFO missing"],
        "investor_questions": [],
        "warnings": ["Only one usable financial year available."],
        "limitations": [],
        "source_manifest": {
            "years_discovered": ["fy25"],
            "years_used": ["fy25"],
            "years_skipped": [],
            "basis_policy": {"preferred_basis": "consolidated", "basis_consistency": "consistent", "warnings": []},
            "financial_artifacts_used": ["financial_year_index.json", "financial_trends.json"],
        },
    }


def _write_company_memory_artifacts(company_root: Path) -> None:
    fin_dir = company_root / "company_memory" / "financials"
    _write_json(fin_dir / "financial_year_index.json", _financial_year_index_payload())
    _write_json(fin_dir / "financial_trends.json", _financial_trends_payload())
    _write_json(fin_dir / "financial_quality_evolution.json", _financial_quality_evolution_payload())
    _write_json(fin_dir / "capital_allocation_financial_timeline.json", _capital_allocation_financial_timeline_payload())
    _write_json(fin_dir / "ownership_evolution.json", _ownership_evolution_payload())
    _write_json(fin_dir / "financial_memory_summary.json", _financial_memory_summary_payload())
    _write_json(fin_dir / "financial_quality_summary.json", _financial_quality_payload())
    _write_json(fin_dir / "financial_driver_attribution.json", _financial_attribution_payload())


def test_financial_audit_passes_with_crore_normalization_and_traceability(tmp_path: Path):
    financials_dir = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_year_artifacts(financials_dir)

    report = build_financial_audit_report(
        company="acme",
        year="fy25",
        financials_dir=financials_dir,
    )

    assert report.status == "warning"
    assert not report.hard_failures
    assert any(check.check_name == "crore_normalization" and check.status == "pass" for check in report.checks)
    assert any("ROCE" in warning for warning in report.warnings) is False


def test_financial_audit_fails_when_required_artifact_missing(tmp_path: Path):
    financials_dir = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_year_artifacts(financials_dir)
    (financials_dir / "financial_ratios.json").unlink()

    report = build_financial_audit_report(
        company="acme",
        year="fy25",
        financials_dir=financials_dir,
    )

    assert report.status == "fail"
    assert "Missing required artifact: financial_ratios.json" in report.hard_failures


def test_financial_audit_fails_when_value_crore_missing(tmp_path: Path):
    financials_dir = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_year_artifacts(financials_dir)
    payload = _normalized_payload()
    payload["profit_and_loss"]["revenue"]["value_crore"] = None
    _write_json(financials_dir / "normalized_fundamentals.json", payload)

    report = build_financial_audit_report(
        company="acme",
        year="fy25",
        financials_dir=financials_dir,
    )

    assert report.status == "fail"
    assert any("₹ crore" in failure for failure in report.hard_failures)


def test_financial_audit_warns_on_basis_mismatch_and_missing_cfo(tmp_path: Path):
    financials_dir = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_year_artifacts(financials_dir)
    normalized = _normalized_payload(cfo_value=None)
    _write_json(financials_dir / "normalized_fundamentals.json", normalized)
    validation = _validation_payload()
    validation["basis_checked"] = "unknown"
    _write_json(financials_dir / "financial_validation_report.json", validation)

    report = build_financial_audit_report(
        company="acme",
        year="fy25",
        financials_dir=financials_dir,
    )

    assert report.status == "warning"
    assert any("CFO missing" in warning for warning in report.warnings)
    assert any("Basis mismatch" in warning for warning in report.warnings)


def test_financial_audit_fails_on_silent_material_basis_mixing(tmp_path: Path):
    financials_dir = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_year_artifacts(financials_dir)
    validation = _validation_payload()
    validation["basis_checked"] = "mixed"
    _write_json(financials_dir / "financial_validation_report.json", validation)
    ratios = _ratios_payload()
    ratios["basis_warnings"] = []
    _write_json(financials_dir / "financial_ratios.json", ratios)
    growth = _growth_payload()
    growth["basis_warnings"] = []
    _write_json(financials_dir / "financial_growth.json", growth)
    normalized = _normalized_payload()
    normalized["basis_manifest"]["basis_warnings"] = []
    _write_json(financials_dir / "normalized_fundamentals.json", normalized)

    report = build_financial_audit_report(
        company="acme",
        year="fy25",
        financials_dir=financials_dir,
    )

    assert report.status == "fail"
    assert any("Material basis mixing detected" in failure for failure in report.hard_failures)


def test_financial_audit_warns_when_fcf_is_intentionally_missing(tmp_path: Path):
    financials_dir = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_year_artifacts(financials_dir)
    normalized = _normalized_payload()
    normalized["cash_flow"]["capex"]["value_crore"] = None
    normalized["cash_flow"]["capex"]["value_original"] = ""
    normalized["cash_flow"]["fcf"]["value_crore"] = None
    normalized["cash_flow"]["fcf"]["value_original"] = ""
    _write_json(financials_dir / "normalized_fundamentals.json", normalized)
    ratios = _ratios_payload(fcf=None)
    _write_json(financials_dir / "financial_ratios.json", ratios)
    growth = _growth_payload()
    growth["growth_metrics"]["fcf"] = None
    _write_json(financials_dir / "financial_growth.json", growth)

    report = build_financial_audit_report(
        company="acme",
        year="fy25",
        financials_dir=financials_dir,
    )

    assert not any("Values not normalized to ₹ crore: cash_flow.fcf" in item for item in report.hard_failures)
    assert any("FCF missing" in item for item in report.warnings)


def test_financial_audit_fails_when_fcf_comes_from_unrelated_source(tmp_path: Path):
    financials_dir = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_year_artifacts(financials_dir)
    normalized = _normalized_payload()
    normalized["cash_flow"]["fcf"]["source_line_item"] = "Cash Flow Statement for the year ended March 31, 2025"
    _write_json(financials_dir / "normalized_fundamentals.json", normalized)

    report = build_financial_audit_report(
        company="acme",
        year="fy25",
        financials_dir=financials_dir,
    )

    assert report.status == "fail"
    assert any("FCF is populated from an unrelated source line." in item for item in report.hard_failures)


def test_financial_audit_detects_stale_saved_audit_output(tmp_path: Path):
    financials_dir = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_year_artifacts(financials_dir)
    _write_json(
        financials_dir / "financial_audit_report.json",
        {
            "company": "acme",
            "year": "fy25",
            "scope": "year",
            "generated_at": "2026-07-16T00:00:00Z",
            "status": "pass",
            "hard_failures": [],
            "warnings": [],
            "checks": [],
            "required_artifacts": [],
            "present_artifacts": [],
            "missing_artifacts": [],
            "limitations": [],
        },
    )

    report = build_financial_audit_report(
        company="acme",
        year="fy25",
        financials_dir=financials_dir,
    )

    assert report.status == "warning"
    assert any("stale relative to" in warning for warning in report.warnings)
    assert any(check.check_name == "saved_audit_freshness" and check.status == "warning" for check in report.checks)


def test_financial_memory_audit_checks_pcim_financial_manifest(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    _write_company_memory_artifacts(company_root)
    pcim_payload = {
        "company": "acme",
        "pcim_source_manifest": {
            "financial_artifacts_used": [{"name": "financial_trends.json", "loaded": True, "warnings": []}],
            "financial_years_covered": ["fy25"],
            "financial_status": "warning",
            "financial_warnings": ["Only one financial year available."],
        },
        "financial_fundamentals_inputs": {"by_year": []},
        "financial_trend_inputs": {"years_covered": ["fy25"]},
        "cash_conversion_inputs": {},
        "return_on_capital_inputs": {},
        "balance_sheet_strength_inputs": {},
        "per_share_inputs": {},
        "corporate_action_inputs": {},
        "ownership_inputs": {},
        "financial_driver_inputs": {},
    }
    _write_json(company_root / "company_memory" / "pcim_v1.json", pcim_payload)

    report = build_financial_memory_audit_report(company="acme", company_root=company_root)

    assert report.status == "warning"
    assert any(check.check_name == "pcim_financial_manifest" and check.status == "pass" for check in report.checks)
    assert any("Only one financial year available." in warning for warning in report.warnings)


def test_financial_memory_audit_fails_on_source_chunk_leakage(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    _write_company_memory_artifacts(company_root)
    payload = _financial_trends_payload()
    payload["metric_trends"]["revenue"]["series"][0]["source_chunk"] = "raw excerpt"
    _write_json(company_root / "company_memory" / "financials" / "financial_trends.json", payload)

    report = build_financial_memory_audit_report(company="acme", company_root=company_root)

    assert report.status == "fail"
    assert any("source_chunk" in failure for failure in report.hard_failures)


def test_write_financial_audit_reports_persist_valid_payloads(tmp_path: Path):
    financials_dir = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_year_artifacts(financials_dir)
    company_root = tmp_path / "companies" / "acme"
    _write_company_memory_artifacts(company_root)

    year_output = financials_dir / "financial_audit_report.json"
    company_output = company_root / "company_memory" / "financials" / "financial_memory_audit_report.json"

    year_report = write_financial_audit_report(
        company="acme",
        year="fy25",
        financials_dir=financials_dir,
        output_path=year_output,
    )
    company_report = write_financial_memory_audit_report(
        company="acme",
        company_root=company_root,
        output_path=company_output,
    )

    assert json.loads(year_output.read_text(encoding="utf-8"))["status"] == year_report.status
    assert json.loads(company_output.read_text(encoding="utf-8"))["scope"] == company_report.scope
