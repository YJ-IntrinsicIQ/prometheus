from __future__ import annotations

import json
from pathlib import Path

from knowledge.financials.fundamentals_acceptance import (
    build_fundamentals_acceptance_report,
    run_fundamentals_acceptance,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _normalized_entry(field: str, year: str, value_crore=None, value_original="", unit_original="crores"):
    return {
        "canonical_field": field,
        "value_crore": value_crore,
        "value_original": value_original,
        "unit_original": unit_original,
        "basis": "consolidated",
        "period": year.upper(),
        "source_line_item": field,
        "source_page": 10,
        "source_artifact": "annual_report.pdf",
        "confidence": "high",
        "warnings": [],
        "source_section_type": "financial_note",
        "statement_type": "balance_sheet" if field in {"net_worth", "total_debt", "total_assets", "cash_and_equivalents"} else "profit_and_loss",
        "source_value_type": "monetary",
    }


def _discovery_payload(year: str):
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "source_documents": ["annual_report.pdf"],
        "sections": {
            "primary_profit_and_loss_statement": [
                {
                    "section_type": "primary_profit_and_loss_statement",
                    "source_artifact": "annual_report.pdf",
                    "page": 10,
                    "chunk_id": f"{year}-pnl",
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
                "period": "FY",
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


def _normalized_payload(year: str, *, revenue=120.0, pat=14.0, cfo=18.0):
    share_count = "1000000" if year == "fy24" else "1100000"
    return {
        "company": "acme",
        "year": year,
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
            "revenue": _normalized_entry("revenue", year, value_crore=revenue, value_original=str(revenue)),
            "pat": _normalized_entry("pat", year, value_crore=pat, value_original=str(pat)),
        },
        "balance_sheet": {
            "net_worth": _normalized_entry("net_worth", year, value_crore=80.0, value_original="80"),
            "total_debt": _normalized_entry("total_debt", year, value_crore=30.0, value_original="30"),
            "total_assets": _normalized_entry("total_assets", year, value_crore=220.0, value_original="220"),
            "cash_and_equivalents": _normalized_entry("cash_and_equivalents", year, value_crore=12.0, value_original="12"),
        },
        "cash_flow": {
            "cfo": _normalized_entry(
                "cfo",
                year,
                value_crore=cfo,
                value_original="" if cfo is None else str(cfo),
            ),
            "capex": _normalized_entry("capex", year, value_crore=9.0, value_original="9"),
        },
        "share_data": {
            "shares_outstanding": _normalized_entry(
                "shares_outstanding",
                year,
                value_crore=None,
                value_original=share_count,
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


def _ratios_payload(year: str):
    names = (
        "gross_margin", "ebitda_margin", "ebit_margin", "opm", "npm", "roe", "roce", "roa", "debt_to_equity",
        "net_debt", "net_debt_to_equity", "interest_coverage", "cfo_to_pat", "fcf", "fcf_to_pat", "fcf_margin",
        "receivable_days", "inventory_days", "payable_days", "cash_conversion_cycle", "eps_basic", "eps_diluted",
        "book_value_per_share", "tangible_book_value_per_share", "dividend_per_share", "payout_ratio"
    )
    ratios = {name: _ratio_item(name, 1.0, unit="x") for name in names}
    ratios.update(
        {
            "opm": _ratio_item("opm", 16.0),
            "npm": _ratio_item("npm", 11.0),
            "roe": _ratio_item("roe", 12.0),
            "roce": _ratio_item("roce", 15.0),
            "debt_to_equity": _ratio_item("debt_to_equity", 0.38, unit="x"),
            "cfo_to_pat": _ratio_item("cfo_to_pat", 1.28, unit="x"),
            "fcf": _ratio_item("fcf", 9.0, unit="₹ crore"),
            "fcf_to_pat": _ratio_item("fcf_to_pat", 0.64, unit="x"),
            "book_value_per_share": _ratio_item("book_value_per_share", 80.0, unit="per share"),
        }
    )
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "pass",
        "basis_used": "consolidated",
        "basis_confidence": "high",
        "basis_warnings": [],
        "warnings": [],
        "ratios": ratios,
        "limitations": [],
    }


def _growth_item(metric: str, current_year: str, previous_year: str):
    return {
        "metric": metric,
        "current_year": current_year,
        "previous_year": previous_year,
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


def _growth_payload(year: str):
    previous = "fy23" if year == "fy24" else "fy24"
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "pass",
        "basis_used": "consolidated",
        "basis_confidence": "high",
        "years_available": [previous, year],
        "growth_metrics": {
            "revenue": _growth_item("revenue", year, previous),
            "pat": _growth_item("pat", year, previous),
            "cfo": _growth_item("cfo", year, previous),
            "fcf": _growth_item("fcf", year, previous),
        },
        "margin_changes": {"opm": _growth_item("opm", year, previous)},
        "basis_warnings": [],
        "warnings": [],
        "limitations": [],
    }


def _validation_payload(year: str, status="pass"):
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": status,
        "basis_checked": "consolidated",
        "hard_failures": [] if status != "fail" else ["validation failed"],
        "warnings": [],
        "checks": [{"check_name": "ready", "status": "pass", "details": "ok"}],
        "missing_fields": [],
        "suspicious_values": [],
        "limitations": [],
    }


def _reconciliation_payload(year: str, status="pass"):
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
    hard_failures = [] if status != "fail" else ["reconciliation failed"]
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": status,
        "checks": checks,
        "hard_failures": hard_failures,
        "warnings": [],
        "limitations": [],
    }


def _corporate_actions_payload(year: str, *, comparability_warnings=None):
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": "pass",
        "actions": [],
        "share_count_summary": {
            "opening_shares": 1000000,
            "closing_shares": 1100000,
            "weighted_avg_shares": 1050000,
            "diluted_shares": 1110000,
            "face_value": 10.0,
            "share_count_events": [],
        },
        "per_share_comparability_warnings": list(comparability_warnings or []),
        "rejection_reasons": [],
        "warnings": [],
        "limitations": [],
    }


def _shareholding_payload(year: str, *, status="pass", items=None):
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-17T00:00:00Z",
        "status": status,
        "items": items if items is not None else [
            {
                "holder_category": "promoter_holding_percent",
                "period": year,
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


def _financial_trends_payload():
    def _trend(metric: str, v24: float, v25: float):
        return {
            "metric": metric,
            "unit": "₹ crore",
            "series": [
                {
                    "year": "fy24",
                    "value": v24,
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
                },
                {
                    "year": "fy25",
                    "value": v25,
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
                },
            ],
            "comparability_warnings": [],
        }

    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy24", "fy25"],
        "basis": "consolidated",
        "basis_policy": {
            "preferred_basis": "consolidated",
            "basis_consistency": "consistent",
            "warnings": [],
        },
        "trend_groups": {},
        "metric_series": {
            "revenue": [
                {"year": "fy24", "value": 110.0, "basis": "consolidated", "source_artifact": "normalized_fundamentals.json", "confidence": "high", "warnings": []},
                {"year": "fy25", "value": 120.0, "basis": "consolidated", "source_artifact": "normalized_fundamentals.json", "confidence": "high", "warnings": []},
            ],
            "pat": [
                {"year": "fy24", "value": 12.0, "basis": "consolidated", "source_artifact": "normalized_fundamentals.json", "confidence": "high", "warnings": []},
                {"year": "fy25", "value": 14.0, "basis": "consolidated", "source_artifact": "normalized_fundamentals.json", "confidence": "high", "warnings": []},
            ],
        },
        "ratio_series": {
            "opm": [
                {"year": "fy24", "value": 16.0, "basis": "consolidated", "source_artifact": "financial_ratios.json", "confidence": "high", "warnings": []},
                {"year": "fy25", "value": 16.0, "basis": "consolidated", "source_artifact": "financial_ratios.json", "confidence": "high", "warnings": []},
            ],
            "roe": [
                {"year": "fy24", "value": 12.0, "basis": "consolidated", "source_artifact": "financial_ratios.json", "confidence": "high", "warnings": []},
                {"year": "fy25", "value": 12.0, "basis": "consolidated", "source_artifact": "financial_ratios.json", "confidence": "high", "warnings": []},
            ],
        },
        "metric_trends": {
            "revenue": _trend("revenue", 110.0, 120.0),
            "pat": _trend("pat", 12.0, 14.0),
        },
        "growth_summary": {
            "revenue": [
                {
                    "year": "fy25",
                    "growth_percent": 9.1,
                    "cagr_percent": 9.1,
                    "absolute_change": 10.0,
                    "basis": "consolidated",
                    "source_artifact": "financial_growth.json",
                    "confidence": "high",
                    "warnings": [],
                }
            ]
        },
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
    section = {
        "status": "strong",
        "summary": "Healthy.",
        "signals": ["stable"],
        "warnings": [],
        "metrics": {},
    }
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy24", "fy25"],
        "status": "pass",
        "overall_financial_quality": "strong",
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
        "positive_signals": ["cash conversion stable"],
        "missing_data": [],
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
        "years_covered": ["fy24", "fy25"],
        "status": "pass",
        "attributions": [],
        "attribution_readiness": {"status": "supported", "reason": "Sufficient data available."},
        "warnings": [],
        "limitations": [],
    }


def _committee_synthesis_payload():
    return {
        "company": "acme",
        "analysis_mode": "committee_synthesis_v1",
        "analysts_considered": ["graham", "buffett"],
        "missing_analysts": [],
        "excluded_analysts": [],
        "years_considered": ["fy24", "fy25"],
        "overall_committee_view": {
            "summary": "The business shows improving fundamentals but still needs careful follow-through tracking.",
            "confidence": "medium",
            "dominant_tension": "Growth is visible, but long-term durability still needs more evidence.",
        },
        "financial_committee_view": {
            "financials_used": True,
            "basis_used": "consolidated",
            "financial_consensus": [
                "Revenue, profit, and cash conversion are usable for investor analysis in the current synthetic fixture."
            ],
            "financial_strengths": ["Revenue and PAT are both present across two years."],
            "financial_concerns": [],
            "financial_disagreements": [],
            "missing_financial_data": [],
            "financial_red_flags": [],
            "financial_interpretation_limits": [],
            "investor_questions_from_financials": [],
        },
        "areas_of_agreement": [
            {"theme": "financial visibility", "analysts": ["graham", "buffett"], "summary": "Core metrics are present.", "evidence_ids": ["ev_1"]},
        ],
        "areas_of_disagreement": [
            {
                "theme": "durability",
                "disagreement_type": "weighting",
                "analysts_positive_or_less_concerned": ["buffett"],
                "analysts_cautious_or_negative": ["graham"],
                "summary": "Some analysts want more history.",
                "why_it_matters": "Durability affects confidence.",
                "evidence_ids": ["ev_1"],
            }
        ],
        "strongest_positive_signals": [
            {"signal": "traceable fundamentals", "supported_by": ["graham"], "summary": "Core numbers are traceable.", "evidence_ids": ["ev_1"]},
        ],
        "most_important_risks": [
            {"risk": "limited history", "raised_by": ["graham"], "summary": "Only two years are available.", "severity": "medium", "evidence_ids": ["ev_1"]},
        ],
        "critical_unknowns": [{"unknown": "long-term durability", "raised_by": ["buffett"], "why_it_matters": "More years would help."}],
        "investigation_questions": [{"question": "Can the company sustain margins?", "reason": "Durability needs more evidence.", "linked_unknown_or_risk": "long-term durability"}],
        "evidence_ids": ["ev_1"],
        "evidence_quality_notes": [],
        "synthesis_limits": ["Only two years are available."],
        "generated_at": "2026-07-17T00:00:00Z",
        "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
    }


def _pcim_payload(*, include_manifest=True):
    payload = {
        "company": "acme",
        "financial_fundamentals_inputs": {"by_year": []},
        "financial_trend_inputs": {"years_covered": ["fy24", "fy25"]},
        "cash_conversion_inputs": {},
        "return_on_capital_inputs": {},
        "balance_sheet_strength_inputs": {},
        "per_share_inputs": {},
        "corporate_action_inputs": {},
        "ownership_inputs": {},
        "financial_driver_inputs": {},
    }
    if include_manifest:
        payload["pcim_source_manifest"] = {
            "financial_artifacts_used": [{"name": "financial_trends.json", "loaded": True, "warnings": []}],
            "financial_years_covered": ["fy24", "fy25"],
            "financial_status": "pass",
            "financial_warnings": [],
        }
    return payload


def _financial_year_index_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_discovered": ["fy24", "fy25"],
        "years_used": ["fy24", "fy25"],
        "years_skipped": [],
        "year_status": {
            "fy24": {
                "financials_available": True,
                "validation_status": "pass",
                "reconciliation_status": "pass",
                "quality_status": "warning",
                "basis_used": "consolidated",
                "warnings": [],
                "limitations": [],
            },
            "fy25": {
                "financials_available": True,
                "validation_status": "pass",
                "reconciliation_status": "pass",
                "quality_status": "warning",
                "basis_used": "consolidated",
                "warnings": [],
                "limitations": [],
            },
        },
        "warnings": [],
        "limitations": [],
    }


def _financial_quality_evolution_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy24", "fy25"],
        "evolution": {
            "growth_quality": {"by_year": [{"year": "fy24", "assessment": "adequate", "confidence": "medium", "summary": "Growth is acceptable.", "highlights": [], "warnings": []}, {"year": "fy25", "assessment": "strong", "confidence": "medium", "summary": "Growth improved.", "highlights": [], "warnings": []}], "latest_assessment": "strong"},
            "margin_quality": {},
            "return_on_capital_quality": {},
            "cash_conversion_quality": {},
            "balance_sheet_strength": {},
            "working_capital_pressure": {},
            "per_share_quality": {},
            "dividend_quality": {},
        },
        "recurring_strengths": ["Growth quality shows positive evidence in fy25."],
        "recurring_concerns": [],
        "improving_signals": ["growth_quality improved by the latest year."],
        "deteriorating_signals": [],
        "missing_data_patterns": [],
        "warnings": [],
        "limitations": [],
    }


def _capital_allocation_financial_timeline_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy24", "fy25"],
        "timeline": [],
        "dividend_pattern": {"years": ["fy24", "fy25"], "warnings": []},
        "capex_pattern": {"years": ["fy24", "fy25"], "warnings": []},
        "fcf_pattern": {"years": ["fy24", "fy25"], "warnings": []},
        "dilution_or_share_issue_pattern": {"years": [], "warnings": []},
        "debt_pattern": {"years": ["fy24", "fy25"], "warnings": []},
        "warnings": [],
        "limitations": [],
    }


def _ownership_evolution_payload():
    return {
        "company": "acme",
        "generated_at": "2026-07-17T00:00:00Z",
        "years_covered": ["fy24", "fy25"],
        "promoter_holding": [{"year": "fy24", "value": 52.0, "source_artifact": "shareholding_pattern.json", "confidence": "high", "warnings": []}],
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
        "status": "pass",
        "years_covered": ["fy24", "fy25"],
        "basis_used": "consolidated",
        "summary": {
            "scale_pattern": ["revenue in fy25: 120.0 ₹ crore"],
            "profitability_pattern": ["opm in fy25: 20.0 %"],
            "return_pattern": ["roe in fy25: 18.0 %"],
            "cash_conversion_pattern": ["cfo in fy25: 15.0 ₹ crore"],
            "balance_sheet_pattern": ["total_debt in fy25: 10.0 ₹ crore"],
            "working_capital_pattern": [],
            "per_share_pattern": ["eps_basic in fy25: 12.0 per share"],
            "capital_allocation_pattern": ["Capex evidence in: fy24, fy25"],
            "ownership_pattern": ["Promoter holding tracked across 1 year(s)."],
        },
        "key_strengths": ["Cash conversion remains healthy."],
        "key_concerns": [],
        "missing_data": [],
        "investor_questions": [],
        "warnings": [],
        "limitations": [],
        "source_manifest": {
            "years_discovered": ["fy24", "fy25"],
            "years_used": ["fy24", "fy25"],
            "years_skipped": [],
            "basis_policy": {"preferred_basis": "consolidated", "basis_consistency": "consistent", "warnings": []},
            "financial_artifacts_used": ["financial_year_index.json", "financial_trends.json"],
        },
    }


def _seed_company(company_root: Path) -> None:
    for year in ("fy24", "fy25"):
        fin_dir = company_root / year / "financials"
        _write_json(fin_dir / "financial_discovery.json", _discovery_payload(year))
        _write_json(fin_dir / "raw_financial_tables.json", _extraction_payload())
        _write_json(fin_dir / "normalized_fundamentals.json", _normalized_payload(year, revenue=110.0 if year == "fy24" else 120.0, pat=12.0 if year == "fy24" else 14.0))
        _write_json(fin_dir / "financial_validation_report.json", _validation_payload(year))
        _write_json(fin_dir / "financial_reconciliation_report.json", _reconciliation_payload(year))
        _write_json(fin_dir / "financial_ratios.json", _ratios_payload(year))
        _write_json(fin_dir / "financial_growth.json", _growth_payload(year))
        _write_json(fin_dir / "corporate_actions.json", _corporate_actions_payload(year))
        _write_json(fin_dir / "shareholding_pattern.json", _shareholding_payload(year))

    company_memory = company_root / "company_memory"
    fin_memory = company_memory / "financials"
    _write_json(fin_memory / "financial_year_index.json", _financial_year_index_payload())
    _write_json(fin_memory / "financial_trends.json", _financial_trends_payload())
    _write_json(fin_memory / "financial_quality_evolution.json", _financial_quality_evolution_payload())
    _write_json(fin_memory / "capital_allocation_financial_timeline.json", _capital_allocation_financial_timeline_payload())
    _write_json(fin_memory / "ownership_evolution.json", _ownership_evolution_payload())
    _write_json(fin_memory / "financial_memory_summary.json", _financial_memory_summary_payload())
    _write_json(fin_memory / "financial_quality_summary.json", _financial_quality_payload())
    _write_json(fin_memory / "financial_driver_attribution.json", _financial_attribution_payload())
    _write_json(company_memory / "cim_v1.json", {"company": "acme", "financial_intelligence": {"fundamentals": []}})
    _write_json(company_memory / "pcim_v1.json", _pcim_payload())
    investor_panel = company_memory / "investor_panel"
    _write_json(investor_panel / "committee_synthesis.json", _committee_synthesis_payload())
    (investor_panel / "committee_brief.md").write_text("# Brief\n\n## Financial View\nPresent.\n", encoding="utf-8")


def test_strong_fundamentals_pass(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    _seed_company(company_root)

    report = build_fundamentals_acceptance_report(company="acme", companies_root=tmp_path / "companies")

    assert report["status"] == "pass"
    assert report["fundamentals_readiness_score"] >= 90
    assert report["ready_for_panel"] is True
    assert report["ready_for_valuation"] is False

    outputs = run_fundamentals_acceptance(
        company="acme",
        companies_root=tmp_path / "companies",
        output_md=True,
    )
    assert outputs["fundamentals_acceptance_report.json"].exists()
    assert outputs["fundamentals_acceptance_report.md"].exists()


def test_missing_revenue_fails(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    _seed_company(company_root)
    payload = _normalized_payload("fy25", revenue=None)
    payload["profit_and_loss"]["revenue"]["value_original"] = ""
    _write_json(company_root / "fy25" / "financials" / "normalized_fundamentals.json", payload)

    report = build_fundamentals_acceptance_report(
        company="acme",
        year="fy25",
        companies_root=tmp_path / "companies",
    )

    assert report["status"] == "fail"
    assert any("revenue missing" in item.lower() for item in report["critical_failures"])


def test_missing_cfo_warns(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    _seed_company(company_root)
    _write_json(company_root / "fy25" / "financials" / "normalized_fundamentals.json", _normalized_payload("fy25", cfo=None))

    report = build_fundamentals_acceptance_report(
        company="acme",
        year="fy25",
        companies_root=tmp_path / "companies",
    )

    assert report["status"] == "warning"
    assert any("cfo missing" in item.lower() for item in report["missing_data"])


def test_missing_shareholding_warns(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    _seed_company(company_root)
    _write_json(
        company_root / "fy25" / "financials" / "shareholding_pattern.json",
        _shareholding_payload("fy25", status="warning", items=[]),
    )

    report = build_fundamentals_acceptance_report(
        company="acme",
        year="fy25",
        companies_root=tmp_path / "companies",
    )

    assert report["status"] == "warning"
    assert any("shareholding pattern missing" in item.lower() for item in report["missing_data"])


def test_missing_pcim_financial_manifest_fails(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    _seed_company(company_root)
    _write_json(company_root / "company_memory" / "pcim_v1.json", _pcim_payload(include_manifest=False))

    report = build_fundamentals_acceptance_report(company="acme", companies_root=tmp_path / "companies")

    assert report["status"] == "fail"
    assert any("pcim financial manifest missing" in item.lower() for item in report["critical_failures"])


def test_valuation_readiness_is_false_even_when_panel_ready(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    _seed_company(company_root)

    report = build_fundamentals_acceptance_report(company="acme", companies_root=tmp_path / "companies")

    assert report["ready_for_panel"] is True
    assert report["ready_for_valuation"] is False
