import json
from pathlib import Path

import pytest
import intelligence.investor_panel.runner as runner_module
from intelligence.investor_panel.briefs import LENS_CONFIG
from intelligence.investor_panel.doctrine_registry import InvestorDoctrineRegistry
from intelligence.investor_panel.runner import (
    _build_compact_prompt,
    _validate_llm_panel_output,
)


def _write_pcim(base_dir: Path, company: str, *, missing_sections=None) -> Path:
    missing_sections = set(missing_sections or [])
    company_memory_dir = base_dir / "companies" / company / "company_memory"
    company_memory_dir.mkdir(parents=True, exist_ok=True)
    pcim = {
        "contract_version": "1.0",
        "company": company,
        "available_years": ["fy25"],
        "business_understanding": {
            "latest_business_view": {
                "year": "fy25",
                "business_model": {"business_summary": "Synthetic business", "evidence_ids": ["ev_bu_1"]},
            }
        },
        "management_quality_inputs": {
            "management_focus_by_year": [{"year": "fy25", "items": [{"value": "Execution focus", "evidence_ids": ["ev_mgmt_1"]}]}],
            "promises_by_year": [{"year": "fy25", "items": [{"value": "Deliver growth", "evidence_ids": ["ev_prom_1"]}]}],
        },
        "growth_quality_inputs": {
            "projects_by_year": [{"year": "fy25", "items": [{"value": "Scale platform", "evidence_ids": ["ev_proj_1"]}]}],
            "initiatives_by_year": [{"year": "fy25", "items": [{"value": "Improve automation", "evidence_ids": ["ev_init_1"]}]}],
            "financial_growth_summary": {
                "quality_status": "pass",
                "summary": "Growth remains healthy.",
                "signals": ["Revenue and EPS improved."],
                "by_year": [{"year": "fy25", "growth_metrics": [{"metric": "revenue", "growth_percent": 15.0}, {"metric": "eps_basic", "growth_percent": 12.0}]}],
                "source_artifact": "financial_quality_summary.json",
            },
        },
        "financial_fundamentals_inputs": {
            "by_year": [{"year": "fy25", "key_metrics": [
                {"field": "revenue", "value_crore": 120.0, "source_year": "fy25", "source_artifact": "normalized_fundamentals.json", "evidence_ids": ["ev_fin_1"]},
                {"field": "net_worth", "value_crore": 80.0, "source_year": "fy25", "source_artifact": "normalized_fundamentals.json", "evidence_ids": ["ev_fin_1"]},
                {"field": "total_debt", "value_crore": 12.0, "source_year": "fy25", "source_artifact": "normalized_fundamentals.json", "evidence_ids": ["ev_fin_1"]},
            ]}],
            "warnings": [],
        },
        "financial_trend_inputs": {
            "years_covered": ["fy24", "fy25"],
            "basis": "consolidated",
            "metric_trends": [
                {"metric": "revenue", "series": [{"year": "fy25", "value": 120.0, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
                {"metric": "pat", "series": [{"year": "fy25", "value": 18.0, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
            ],
            "warnings": [],
            "limitations": [],
            "source_artifact": "financial_trends.json",
        },
        "financial_growth_inputs": {
            "by_year": [
                {
                    "year": "fy25",
                    "growth_metrics": [
                        {"metric": "revenue", "value": 15.0, "unit": "%", "period": "fy25", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_growth.json"], "warnings": [], "limitations": [], "evidence_ids": ["ev_fin_1"]},
                        {"metric": "eps_basic", "value": 12.0, "unit": "%", "period": "fy25", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_growth.json"], "warnings": [], "limitations": [], "evidence_ids": ["ev_fin_1"]},
                    ],
                    "warnings": [],
                    "limitations": [],
                }
            ],
            "warnings": [],
            "limitations": [],
            "source_artifact": "financial_growth.json",
        },
        "profitability_inputs": {
            "by_year": [
                {
                    "year": "fy25",
                    "metrics": [
                        {"metric": "opm", "value": 21.0, "unit": "%", "period": "fy25", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": [], "limitations": [], "evidence_ids": ["ev_fin_1"]},
                        {"metric": "npm", "value": 15.0, "unit": "%", "period": "fy25", "basis": "consolidated", "confidence": "high", "source_artifacts": ["financial_ratios.json"], "warnings": [], "limitations": [], "evidence_ids": ["ev_fin_1"]},
                    ],
                    "warnings": [],
                    "limitations": [],
                }
            ],
            "warnings": [],
            "source_artifact": "financial_ratios.json",
        },
        "cash_conversion_inputs": {
            "status": "pass",
            "summary": "Cash conversion is healthy.",
            "signals": ["CFO exceeds PAT."],
            "warnings": [],
            "metrics": [
                {"metric": "cfo", "series": [{"year": "fy25", "value": 22.0, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
                {"metric": "capex", "series": [{"year": "fy25", "value": -7.0, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
                {"metric": "fcf", "series": [{"year": "fy25", "value": 15.0, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
            ],
            "source_artifact": "financial_quality_summary.json",
        },
        "return_on_capital_inputs": {
            "status": "pass",
            "summary": "Returns remain solid.",
            "signals": ["ROCE remains strong."],
            "warnings": [],
            "metrics": [
                {"metric": "roe", "series": [{"year": "fy25", "value": 19.0, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
                {"metric": "roce", "series": [{"year": "fy25", "value": 17.0, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
            ],
            "source_artifact": "financial_quality_summary.json",
        },
        "balance_sheet_strength_inputs": {
            "status": "pass",
            "summary": "Leverage remains modest.",
            "signals": ["Debt to equity remains controlled."],
            "warnings": [],
            "metrics": [
                {"metric": "debt_to_equity", "series": [{"year": "fy25", "value": 0.15, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
                {"metric": "total_debt", "series": [{"year": "fy25", "value": 12.0, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
            ],
            "source_artifact": "financial_quality_summary.json",
        },
        "working_capital_inputs": {
            "metrics": [
                {"metric": "receivable_days", "series": [{"year": "fy25", "value": 34.0, "source_artifact": "financial_ratios.json", "evidence_ids": ["ev_fin_1"]}]},
                {"metric": "payable_days", "series": [{"year": "fy25", "value": 28.0, "source_artifact": "financial_ratios.json", "evidence_ids": ["ev_fin_1"]}]},
                {"metric": "cash_conversion_cycle", "series": [{"year": "fy25", "value": 18.0, "source_artifact": "financial_ratios.json", "evidence_ids": ["ev_fin_1"]}]},
            ],
            "by_year": [
                {
                    "year": "fy25",
                    "metrics": [
                        {"metric": "receivable_days", "value": 34.0, "unit": "days", "period": "fy25", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_ratios.json"], "warnings": [], "limitations": [], "evidence_ids": ["ev_fin_1"]},
                        {"metric": "payable_days", "value": 28.0, "unit": "days", "period": "fy25", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_ratios.json"], "warnings": [], "limitations": [], "evidence_ids": ["ev_fin_1"]},
                        {"metric": "cash_conversion_cycle", "value": 18.0, "unit": "days", "period": "fy25", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_ratios.json"], "warnings": [], "limitations": [], "evidence_ids": ["ev_fin_1"]},
                    ],
                    "warnings": [],
                    "limitations": [],
                }
            ],
            "warnings": [],
            "source_artifact": "financial_ratios.json",
        },
        "per_share_inputs": {
            "metrics": [
                {"metric": "eps_basic", "series": [{"year": "fy25", "value": 12.0, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
                {"metric": "book_value_per_share", "series": [{"year": "fy25", "value": 55.0, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
                {"metric": "shares_outstanding", "series": [{"year": "fy25", "value": 1.6, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
                {"metric": "weighted_avg_shares", "series": [{"year": "fy25", "value": 1.4, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
                {"metric": "diluted_shares", "series": [{"year": "fy25", "value": 1.45, "source_artifact": "financial_trends.json", "evidence_ids": ["ev_fin_1"]}]},
            ],
            "warnings": [],
            "source_artifact": "financial_trends.json",
        },
        "corporate_action_inputs": {
            "by_year": [{"year": "fy25", "actions": [{"action_type": "qip", "impact_on_share_count": "increase", "impact_on_eps_comparability": "yes"}], "per_share_comparability_warnings": ["QIP affects comparability."]}],
            "warnings": ["QIP affects comparability."],
            "source_artifact": "corporate_actions.json",
        },
        "ownership_inputs": {
            "by_year": [{"year": "fy25", "items": [{"holder_category": "promoter_holding_percent", "holding_percent": 52.0, "source_artifact": "shareholding_pattern.json"}], "warnings": []}],
            "summary_status": "warning",
            "summary": "Ownership is stable.",
            "warnings": [],
            "source_artifact": "shareholding_pattern.json",
        },
        "financial_driver_inputs": {
            "status": "warning",
            "years_covered": ["fy24", "fy25"],
            "attributions": [{"metric": "revenue", "movement": "improved", "possible_driver": "Customer additions", "source_artifacts": ["financial_driver_attribution.json"], "evidence_ids": ["ev_fd_1"]}],
            "warnings": [],
            "limitations": [],
            "source_artifact": "financial_driver_attribution.json",
        },
        "financial_truth_inputs": {
            "usable_current_metrics": [
                {"metric_id": "receivables", "value": 14.0, "basis": "consolidated", "confidence": "medium"},
                {"metric_id": "inventory", "value": 11.0, "basis": "consolidated", "confidence": "medium"},
                {"metric_id": "payables", "value": 9.0, "basis": "consolidated", "confidence": "medium"},
                {"metric_id": "shares_outstanding", "value": 1.6, "basis": "consolidated", "confidence": "medium"},
            ],
            "usable_derived_metrics": [
                {"metric_id": "owner_earnings_estimate", "value": 13.0, "basis": "consolidated", "confidence": "medium"},
                {"metric_id": "conservative_fcf_after_total_capex", "value": 12.0, "basis": "consolidated", "confidence": "medium"},
                {"metric_id": "total_identified_capex", "value": 7.0, "basis": "consolidated", "confidence": "medium"},
                {"metric_id": "capex_deployed", "value": 7.0, "basis": "consolidated", "confidence": "medium"},
            ],
            "source_artifact": "financial_truth_pack.json",
        },
        "owner_earnings_readiness_inputs": {
            "bridges": [
                {
                    "fiscal_year": "fy25",
                    "total_identified_capex": 7.0,
                    "conservative_fcf_after_total_capex": 12.0,
                    "owner_earnings_estimate": 13.0,
                    "owner_earnings_precision_status": "estimate_available",
                }
            ],
            "source_artifact": "owner_earnings_bridge.json",
        },
        "working_capital_quality_inputs": {
            "drilldown": [
                {
                    "metric_id": "receivables",
                    "value": 14.0,
                    "basis": "consolidated",
                    "confidence": "medium",
                },
                {
                    "metric_id": "inventory",
                    "value": 11.0,
                    "basis": "consolidated",
                    "confidence": "medium",
                },
                {
                    "metric_id": "payables",
                    "value": 9.0,
                    "basis": "consolidated",
                    "confidence": "medium",
                },
            ],
            "source_artifact": "working_capital_quality_drilldown.json",
        },
        "capital_allocation_financial_inputs": {
            "entries": [
                {"metric_id": "capex_deployed", "value": 7.0, "basis": "consolidated", "confidence": "medium"},
            ],
            "source_artifact": "capital_allocation_roi_ledger.json",
        },
        "per_share_compounding_inputs": {
            "analysis": [
                {"metric_id": "closing_shares", "value": 1.6, "basis": "consolidated", "confidence": "medium"},
            ],
            "source_artifact": "per_share_compounding_analysis.json",
        },
        "multi_year_financial_inputs": {
            "years_covered": ["fy24", "fy25"],
            "basis_used": "consolidated",
            "scale_pattern": ["revenue in fy25: 120.0 ₹ crore"],
            "profitability_pattern": ["opm in fy25: 21.0 %"],
            "return_pattern": ["roce in fy25: 17.0 %"],
            "cash_conversion_pattern": ["cfo in fy25: 22.0 ₹ crore"],
            "balance_sheet_pattern": ["total_debt in fy25: 12.0 ₹ crore"],
            "working_capital_pattern": ["cash_conversion_cycle in fy25: 18.0 days"],
            "capital_allocation_pattern": ["Capex evidence in: fy25"],
            "ownership_pattern": ["Promoter holding tracked across 1 year(s)."],
            "key_strengths": ["Cash conversion remains healthy."],
            "key_concerns": [],
            "missing_data": [],
            "investor_questions": [],
            "warnings": [],
            "limitations": ["Two-year history is provisional."],
            "source_artifact": "financial_memory_summary.json",
        },
        "financial_quality_inputs": {
            "by_year": [
                {
                    "year": "fy25",
                    "status": "warning",
                    "basis_used": "consolidated",
                    "sections": {
                        "dividend_quality": {
                            "period": "fy25",
                            "section": "dividend_quality",
                            "assessment": "pass",
                            "confidence": "medium",
                            "source_artifacts": ["financial_quality_summary.json"],
                            "warnings": [],
                            "limitations": [],
                            "highlights": ["Dividend remains covered by cash generation."],
                            "evidence_metrics": {"fcf_to_pat": 1.0},
                            "summary": "Dividend quality remains acceptable.",
                        }
                    },
                    "red_flags": [],
                    "missing_data": [],
                    "investor_questions": [],
                    "warnings": ["Only one year available."],
                    "limitations": [],
                }
            ],
            "warnings": ["Only one year available."],
            "source_artifact": "financial_quality_summary.json",
        },
        "risk_inputs": {"risk_by_year": [{"year": "fy25", "items": [{"value": "Customer concentration", "evidence_ids": ["ev_risk_1"]}]}]},
        "capital_allocation_inputs": {"capital_allocation_by_year": [{"year": "fy25", "items": [{"value": "Reinvest in growth", "evidence_ids": ["ev_cap_1"]}]}]},
        "governance_and_incentive_inputs": {"related_party_and_control_items_by_year": [{"year": "fy25", "items": [{"value": "Related-party advance", "evidence_ids": ["ev_gov_1"]}]}]},
        "moat_inputs": {"business_model_by_year": [{"year": "fy25", "business_summary": "Durable platform", "evidence_ids": ["ev_moat_1"]}]},
        "growth_execution_inputs": {"growth_claims_by_year": [{"year": "fy25", "items": [{"value": "Added customers", "evidence_ids": ["ev_growth_1"]}]}]},
        "simplicity_and_story_inputs": {"focus_by_year": [{"year": "fy25", "items": [{"value": "Simple story", "evidence_ids": ["ev_story_1"]}]}]},
        "multi_year_inputs": {"years_covered": ["fy24", "fy25"], "limitations": ["Two-year history is provisional."]},
        "evidence_map": {
            "financial_fundamentals_inputs": ["ev_fin_1"],
            "financial_trend_inputs": ["ev_fin_1"],
            "financial_growth_inputs": ["ev_fin_1"],
            "profitability_inputs": ["ev_fin_1"],
            "cash_conversion_inputs": ["ev_fin_1"],
            "return_on_capital_inputs": ["ev_fin_1"],
            "balance_sheet_strength_inputs": ["ev_fin_1"],
            "working_capital_inputs": ["ev_fin_1"],
            "per_share_inputs": ["ev_fin_1"],
            "corporate_action_inputs": ["ev_fin_1"],
            "ownership_inputs": ["ev_fin_1"],
            "financial_quality_inputs": ["ev_fin_1"],
            "financial_driver_inputs": ["ev_fd_1"],
            "multi_year_financial_inputs": ["ev_fd_1"],
            "risk_inputs": ["ev_risk_1"],
            "capital_allocation_inputs": ["ev_cap_1"],
            "governance_and_incentive_inputs": ["ev_gov_1"],
            "management_quality_inputs": ["ev_mgmt_1", "ev_prom_1"],
            "growth_quality_inputs": ["ev_proj_1", "ev_init_1"],
            "growth_execution_inputs": ["ev_growth_1"],
            "business_understanding": ["ev_bu_1"],
            "moat_inputs": ["ev_moat_1"],
            "simplicity_and_story_inputs": ["ev_story_1"],
            "multi_year_inputs": ["ev_fd_1"],
            "uncertainty_missing_data": [],
        },
        "uncertainty_missing_data": {"incomplete_years": [], "missing_sections": [], "missing_items": []},
    }

    for section in missing_sections:
        pcim[section] = {}
        pcim["uncertainty_missing_data"]["missing_sections"].append(
            {"year": "fy25", "section": section, "reason": "Missing for test"}
        )
        pcim["evidence_map"][section] = []

    path = company_memory_dir / "pcim_v1.json"
    path.write_text(json.dumps(pcim), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("analyst", "expected_sections"),
    [
        ("graham", ['"balance_sheet_strength_inputs"', '"cash_conversion_inputs"', '"financial_fundamentals_inputs"']),
        ("buffett", ['"return_on_capital_inputs"', '"cash_conversion_inputs"', '"per_share_inputs"']),
        ("fisher", ['"financial_growth_inputs"', '"profitability_inputs"', '"financial_driver_inputs"']),
        ("munger", ['"cash_conversion_inputs"', '"corporate_action_inputs"', '"balance_sheet_strength_inputs"']),
        ("lynch", ['"financial_growth_inputs"', '"per_share_inputs"', '"growth_quality_inputs"']),
    ],
)
def test_analyst_prompt_includes_expected_financial_sections(tmp_path, analyst, expected_sections):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get(analyst)

    prompt, _compact_pcim, _stats, _limits_used, _input_compacted, _budget_report = _build_compact_prompt(
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim=pcim,
        sections=list(doctrine["evidence_required_from_pcim"]),
    )

    for section in expected_sections:
        assert section in prompt
    assert '"source_chunk"' not in prompt


def test_unknown_financial_metric_is_omitted_to_diagnostics(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(dict.fromkeys(list(doctrine["evidence_required_from_pcim"]) + ["financial_trend_inputs"]))
    payload_text = json.dumps(
        {
            "assessment": {
                "business_quality_assessment": "Business quality appears strong.",
                "moat_assessment": "Moat evidence is credible.",
                "capital_allocation_assessment": "Capital allocation is disciplined.",
                "management_rationality_assessment": "Management looks rational.",
            },
            "rating": "mixed",
            "key_findings": [{"finding": "Returns are healthy.", "evidence_ids": ["ev_fin_1"]}],
            "red_flags": [{"flag": "Comparability remains a watch item.", "severity": "medium", "evidence_ids": ["ev_fin_1"]}],
            "open_uncertainties": [{"uncertainty": "Coverage is still partial.", "evidence_ids": []}],
            "financial_metrics_used": ["invented_ratio"],
            "financial_red_flags": ["Comparability remains a watch item."],
            "financial_positive_signals": ["ROCE remains healthy."],
            "financial_missing_data": [],
            "financial_interpretation_limits": ["No new ratios were calculated."],
            "financial_assessment": {
                "financials_used": True,
                "basis_used": "consolidated",
                "key_financial_strengths": ["ROCE remains healthy."],
                "key_financial_concerns": ["Comparability remains a watch item."],
                "financial_red_flags": ["Comparability remains a watch item."],
                "missing_financial_data": [],
                "financial_interpretation_limits": ["No new ratios were calculated."],
            },
            "financial_sections_consumed": [
                "financial_fundamentals_inputs",
                "cash_conversion_inputs",
                "return_on_capital_inputs",
                "per_share_inputs",
            ],
            "financial_warnings_carried_forward": [],
            "evidence_ids": ["ev_fin_1"],
            "historical_context_used": True,
            "years_considered": ["fy24", "fy25"],
            "supporting_pcim_sections": consumed_sections,
            "reasoning_limits": ["PCIM only."],
                "user_facing_brief": {
                    "title": "Buffett School of Thought: Business Quality & Capital Allocation",
                    "lens": "This lens focuses on business quality, capital allocation discipline, and the durability of the underlying economics.",
                    "what_looks_good": ["Good economics."],
                    "what_needs_caution": ["Still partial."],
                    "what_is_missing": ["Coverage is incomplete."],
                "bottom_line": "Useful but incomplete.",
            },
        }
    )

    payload = _validate_llm_panel_output(
        payload_text,
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert payload["financial_metrics_used"] == []
    assert payload["unsupported_financial_metric_references"][0]["original_metric_label"] == "invented_ratio"
    assert payload["unsupported_financial_metric_references"][0]["repair_status"] == "omitted"
    assert any("unsupported metric reference omitted" in item.lower() for item in payload["schema_warnings"])


@pytest.mark.parametrize(
    ("raw_metric", "expected_metric"),
    [
        ("owner-earnings estimate (derived)", "owner_earnings_estimate"),
        ("identified capex (total)", "total_identified_capex"),
        ("capex deployed (capital allocation ledger)", "capex_deployed"),
        ("closing shares", "shares_outstanding"),
        ("receivables (value)", "receivables"),
        ("inventory (value)", "inventory"),
        ("payables (value)", "payables"),
        ("payable days", "payable_days"),
        ("receivable days", "receivable_days"),
        ("cash conversion cycle", "cash_conversion_cycle"),
        ("conservative fcf", "conservative_fcf_after_total_capex"),
    ],
)
def test_financial_metric_aliases_normalize_to_truth_pack_metrics(tmp_path, raw_metric, expected_metric):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(
        dict.fromkeys(
            list(doctrine["evidence_required_from_pcim"])
            + [
                "financial_trend_inputs",
                "financial_truth_inputs",
                "owner_earnings_readiness_inputs",
                "working_capital_inputs",
                "working_capital_quality_inputs",
                "capital_allocation_financial_inputs",
                "per_share_compounding_inputs",
            ]
        )
    )
    payload_text = _valid_buffett_payload(consumed_sections, financial_metrics_used=[raw_metric])

    payload = _validate_llm_panel_output(
        payload_text,
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert payload["financial_metrics_used"][0]["metric"] == expected_metric
    assert payload["financial_metrics_used"][0]["original_metric_label"] == raw_metric
    assert payload["financial_metrics_used"][0]["canonical_metric_id"].startswith(expected_metric)
    assert payload["financial_metric_normalizations_applied"][0]["canonical_metric_name"] == expected_metric


def test_missing_financial_sections_flow_into_dry_run_missing_data(tmp_path):
    pcim_path = _write_pcim(
        tmp_path,
        "finpanel",
        missing_sections=["cash_conversion_inputs", "return_on_capital_inputs"],
    )
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")

    from intelligence.investor_panel.runner import _deterministic_panel_output

    payload = _deterministic_panel_output(
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim=pcim,
    )

    assert any("cash_conversion_inputs" in item for item in payload["financial_missing_data"])
    assert any("return_on_capital_inputs" in item for item in payload["financial_missing_data"])


def _valid_buffett_payload(
    consumed_sections,
    *,
    missing_data=None,
    interpretation_limits=None,
    carried_warnings=None,
    financial_metrics_used=None,
):
    missing_data = missing_data or []
    interpretation_limits = interpretation_limits or ["No new ratios were calculated."]
    carried_warnings = carried_warnings or []
    return json.dumps(
        {
            "assessment": {
                "business_quality_assessment": "Business quality appears strong.",
                "moat_assessment": "Moat evidence is credible.",
                "capital_allocation_assessment": "Capital allocation is disciplined.",
                "management_rationality_assessment": "Management looks rational.",
            },
            "rating": "mixed",
            "key_findings": [{"finding": "Returns are healthy.", "evidence_ids": ["ev_fin_1"]}],
            "red_flags": [{"flag": "Comparability remains a watch item.", "severity": "medium", "evidence_ids": ["ev_fin_1"]}],
            "open_uncertainties": [{"uncertainty": "Coverage is still partial.", "evidence_ids": []}],
            "financial_metrics_used": financial_metrics_used or ["roe", "roce", "cfo", "capex", "fcf", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
            "financial_red_flags": ["Comparability remains a watch item."],
            "financial_positive_signals": ["ROCE remains healthy."],
            "financial_missing_data": missing_data,
            "financial_interpretation_limits": interpretation_limits,
            "financial_assessment": {
                "financials_used": True,
                "basis_used": "consolidated",
                "key_financial_strengths": ["ROCE remains healthy."],
                "key_financial_concerns": ["Comparability remains a watch item."],
                "financial_red_flags": ["Comparability remains a watch item."],
                "missing_financial_data": missing_data,
                "financial_interpretation_limits": interpretation_limits,
                "financial_warnings_carried_forward": carried_warnings,
            },
            "financial_sections_consumed": [
                "financial_fundamentals_inputs",
                "cash_conversion_inputs",
                "return_on_capital_inputs",
                "per_share_inputs",
            ],
            "financial_warnings_carried_forward": carried_warnings,
            "evidence_ids": ["ev_fin_1"],
            "historical_context_used": True,
            "years_considered": ["fy24", "fy25"],
            "supporting_pcim_sections": consumed_sections,
            "reasoning_limits": ["PCIM only."],
            "user_facing_brief": {
                "title": "Buffett School of Thought: Business Quality & Capital Allocation",
                "lens": "This lens focuses on business quality, capital allocation discipline, and the durability of the underlying economics.",
                "what_looks_good": ["Good economics."],
                "what_needs_caution": ["Still partial."],
                "what_is_missing": ["Coverage is incomplete."],
                "bottom_line": "Useful but incomplete.",
            },
        }
    )


def test_raw_assessment_string_is_repaired_before_validation(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])
    payload = json.loads(_valid_buffett_payload(consumed_sections))
    payload["assessment"] = "Business quality appears solid, but evidence remains incomplete."

    parsed = _validate_llm_panel_output(
        json.dumps(payload),
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert isinstance(parsed["assessment"], dict)
    assert parsed["assessment"]["business_quality_assessment"] == payload["assessment"]
    assert any(
        "assessment was returned as string and normalized" in item
        for item in parsed["schema_warnings"]
    )


def test_raw_assessment_list_is_repaired_before_validation(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])
    payload = json.loads(_valid_buffett_payload(consumed_sections))
    payload["assessment"] = [
        "Business quality appears solid.",
        "Capital allocation still needs more evidence.",
    ]

    parsed = _validate_llm_panel_output(
        json.dumps(payload),
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert isinstance(parsed["assessment"], dict)
    assert "Business quality appears solid." in parsed["assessment"]["business_quality_assessment"]
    assert any(
        "assessment was returned as list and normalized" in item
        for item in parsed["schema_warnings"]
    )


def test_missing_assessment_uses_skeleton_defaults(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])
    payload = json.loads(_valid_buffett_payload(consumed_sections))
    payload.pop("assessment", None)

    parsed = _validate_llm_panel_output(
        json.dumps(payload),
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert isinstance(parsed["assessment"], dict)
    assert parsed["assessment"]["business_quality_assessment"]
    assert any(
        "assessment was missing; deterministic skeleton defaults were retained." in item
        for item in parsed["schema_warnings"]
    )


def test_unknown_top_level_fields_go_to_diagnostics_not_clean_payload(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])
    payload = json.loads(_valid_buffett_payload(consumed_sections))
    payload["mystery_field"] = {"debug": "keep out of clean artifact"}

    parsed = _validate_llm_panel_output(
        json.dumps(payload),
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert "mystery_field" not in parsed
    assert any(
        "Unknown top-level fields were removed to diagnostics" in item
        for item in parsed["schema_warnings"]
    )


def test_validate_wrapper_repairs_before_strict_validation(monkeypatch, tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])
    payload = json.loads(_valid_buffett_payload(consumed_sections))
    payload["assessment"] = "Raw draft assessment"
    call_order = []

    def fake_repair(parsed, **kwargs):
        call_order.append(("repair", type(parsed.get("assessment")).__name__))
        repaired = dict(parsed)
        repaired["assessment"] = {
            "business_quality_assessment": "Repaired assessment",
            "moat_assessment": "Repaired moat",
            "capital_allocation_assessment": "Repaired capital allocation",
            "management_rationality_assessment": "Repaired rationality",
        }
        repaired["schema_warnings"] = ["repair happened first"]
        return repaired, ["repair happened first"]

    def fake_validate(parsed, **kwargs):
        call_order.append(("validate", type(parsed.get("assessment")).__name__))
        assert isinstance(parsed["assessment"], dict)
        return parsed

    monkeypatch.setattr(runner_module, "_repair_llm_panel_output_draft", fake_repair)
    monkeypatch.setattr(runner_module, "_validate_repaired_llm_panel_output", fake_validate)

    result = _validate_llm_panel_output(
        json.dumps(payload),
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert call_order == [("repair", "str"), ("validate", "dict")]
    assert result["assessment"]["business_quality_assessment"] == "Repaired assessment"


def test_equivalent_per_share_limitation_satisfies_warning_carry_forward(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["per_share_inputs"]["metrics"] = [
        metric for metric in pcim["per_share_inputs"]["metrics"]
        if metric["metric"] not in {"weighted_avg_shares", "diluted_shares"}
    ]
    pcim["financial_fundamentals_inputs"]["warnings"] = ["weighted average shares missing", "diluted shares missing"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(
        dict.fromkeys(list(doctrine["evidence_required_from_pcim"]) + ["financial_trend_inputs"])
    )

    payload = _valid_buffett_payload(
        consumed_sections,
        missing_data=["weighted average shares missing", "diluted shares missing"],
        interpretation_limits=[
            "Per-share analysis is limited because weighted average share count is missing.",
            "Per-share analysis is limited because diluted share count is missing.",
        ],
        carried_warnings=["weighted average shares missing", "diluted shares missing"],
        financial_metrics_used=["roe", "roce", "cfo", "capex", "fcf", "eps_basic", "book_value_per_share"],
    )

    parsed = _validate_llm_panel_output(
        payload,
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )
    assert "weighted average shares missing" in parsed["financial_assessment"]["missing_financial_data"]
    assert parsed["evidence_grounding_status"] in {"pass", "warning"}


def test_validator_auto_carries_major_share_warning(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["per_share_inputs"]["metrics"] = [
        metric for metric in pcim["per_share_inputs"]["metrics"]
        if metric["metric"] not in {"weighted_avg_shares", "diluted_shares"}
    ]
    pcim["financial_fundamentals_inputs"]["warnings"] = ["weighted average shares missing", "diluted shares missing"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])

    payload = _valid_buffett_payload(
        consumed_sections,
        missing_data=[],
        interpretation_limits=["No new ratios were calculated."],
        carried_warnings=[],
        financial_metrics_used=["roe", "roce", "cfo", "capex", "fcf", "eps_basic", "book_value_per_share"],
    )

    parsed = _validate_llm_panel_output(
        payload,
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert any(
        "weighted average shares are missing" in item.lower()
        for item in parsed["financial_warnings_carried_forward"]
    )
    assert any(
        "diluted shares are missing" in item.lower()
        for item in parsed["financial_assessment"]["financial_warnings_carried_forward"]
    )
    assert any(
        "financial warning auto-carried from PCIM: weighted_avg_shares_missing" in item
        for item in parsed["schema_warnings"]
    )
    assert parsed["evidence_grounding_status"] == "warning"


def test_missing_fcf_warning_accepts_equivalent_wording(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["cash_conversion_inputs"]["metrics"] = [
        metric for metric in pcim["cash_conversion_inputs"]["metrics"]
        if metric["metric"] != "fcf"
    ]
    pcim["cash_conversion_inputs"]["warnings"] = ["free cash flow missing"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])

    payload = _valid_buffett_payload(
        consumed_sections,
        missing_data=["free cash flow unavailable"],
        interpretation_limits=["Owner earnings cannot be assessed without free cash flow evidence."],
        carried_warnings=["free cash flow missing"],
        financial_metrics_used=["roe", "roce", "cfo", "capex", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
    )

    parsed = _validate_llm_panel_output(
        payload,
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )
    assert "free cash flow unavailable" in " ".join(parsed["financial_missing_data"]).lower()


def test_missing_capex_warning_accepts_equivalent_wording(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["cash_conversion_inputs"]["metrics"] = [
        metric for metric in pcim["cash_conversion_inputs"]["metrics"]
        if metric["metric"] != "capex"
    ]
    pcim["cash_conversion_inputs"]["warnings"] = ["capex missing"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])

    payload = _valid_buffett_payload(
        consumed_sections,
        missing_data=["capital expenditure not available"],
        interpretation_limits=["Free cash flow cannot be assessed cleanly because capex is unavailable."],
        carried_warnings=["capex missing"],
        financial_metrics_used=["roe", "roce", "cfo", "fcf", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
    )

    parsed = _validate_llm_panel_output(
        payload,
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )
    assert "capital expenditure not available" in " ".join(parsed["financial_missing_data"]).lower()


def test_missing_payables_warning_accepts_equivalent_wording(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["working_capital_inputs"]["metrics"] = [
        metric for metric in pcim["working_capital_inputs"]["metrics"]
        if metric["metric"] not in {"payable_days", "cash_conversion_cycle"}
    ]
    pcim["working_capital_inputs"]["by_year"][0]["metrics"] = [
        metric for metric in pcim["working_capital_inputs"]["by_year"][0]["metrics"]
        if metric["metric"] not in {"payable_days", "cash_conversion_cycle"}
    ]
    pcim["working_capital_inputs"]["warnings"] = ["payable days missing"]
    pcim["financial_truth_inputs"]["usable_current_metrics"] = [
        item for item in pcim["financial_truth_inputs"]["usable_current_metrics"]
        if item.get("metric_id") != "payables"
    ]
    pcim["working_capital_quality_inputs"]["drilldown"] = [
        item for item in pcim["working_capital_quality_inputs"]["drilldown"]
        if item.get("metric_id") != "payables"
    ]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(dict.fromkeys(list(doctrine["evidence_required_from_pcim"]) + ["working_capital_inputs"]))

    payload = _valid_buffett_payload(
        consumed_sections,
        missing_data=["payables missing"],
        interpretation_limits=["Cash conversion cycle unavailable."],
        carried_warnings=["payable days missing"],
    )

    parsed = _validate_llm_panel_output(
        payload,
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )
    assert "payables missing" in " ".join(parsed["financial_missing_data"]).lower()


def test_basis_unknown_warning_accepts_equivalent_wording(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["financial_trend_inputs"]["basis"] = "unknown"
    pcim["financial_trend_inputs"]["warnings"] = ["standalone/consolidated basis unclear"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])

    payload = _valid_buffett_payload(
        consumed_sections,
        missing_data=[],
        interpretation_limits=["Basis uncertainty remains because the standalone/consolidated basis is unclear."],
        carried_warnings=["standalone/consolidated basis unclear"],
    )

    parsed = _validate_llm_panel_output(
        payload,
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )
    assert parsed["financial_assessment"]["basis_used"] == "consolidated"


def test_buffett_cannot_claim_owner_earnings_when_fcf_missing(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["cash_conversion_inputs"]["metrics"] = [
        metric for metric in pcim["cash_conversion_inputs"]["metrics"]
        if metric["metric"] != "fcf"
    ]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])
    payload = json.loads(_valid_buffett_payload(consumed_sections))
    payload["key_findings"][0]["finding"] = "Owner earnings remain strong."
    payload["financial_positive_signals"] = ["Owner earnings remain strong."]
    payload["financial_assessment"]["key_financial_strengths"] = ["Owner earnings remain strong."]
    payload["financial_missing_data"] = []
    payload["financial_interpretation_limits"] = ["No new ratios were calculated."]
    payload["financial_assessment"]["missing_financial_data"] = []
    payload["financial_assessment"]["financial_interpretation_limits"] = ["No new ratios were calculated."]
    payload["financial_warnings_carried_forward"] = []
    payload["financial_assessment"]["financial_warnings_carried_forward"] = []
    payload["financial_metrics_used"] = ["roe", "roce", "cfo", "capex", "eps_basic", "book_value_per_share", "weighted_avg_shares"]

    with pytest.raises(ValueError, match="owner earnings cannot be assessed"):
        _validate_llm_panel_output(
            json.dumps(payload),
            doctrine=doctrine,
            company="finpanel",
            pcim_path=pcim_path,
            pcim_version="1.0",
            pcim=pcim,
            consumed_sections=consumed_sections,
            allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
        )


def test_fcf_missing_is_auto_carried_and_adds_buffett_owner_earnings_limit(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["cash_conversion_inputs"]["metrics"] = [
        metric for metric in pcim["cash_conversion_inputs"]["metrics"]
        if metric["metric"] != "fcf"
    ]
    pcim["cash_conversion_inputs"]["warnings"] = ["free cash flow missing"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(dict.fromkeys(list(doctrine["evidence_required_from_pcim"]) + ["financial_trend_inputs"]))

    payload = _valid_buffett_payload(
        consumed_sections,
        missing_data=[],
        interpretation_limits=["No new ratios were calculated."],
        carried_warnings=[],
        financial_metrics_used=["roe", "roce", "cfo", "capex", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
    )

    parsed = _validate_llm_panel_output(
        payload,
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert any("free cash flow is missing" in item.lower() for item in parsed["financial_warnings_carried_forward"])
    assert any(
        "owner earnings cannot be assessed because free cash flow/capex data is missing or incomplete." in item.lower()
        for item in parsed["financial_interpretation_limits"]
    )
    assert any("financial warning auto-carried from PCIM: fcf_missing" in item for item in parsed["schema_warnings"])
    assert parsed["evidence_grounding_status"] == "warning"


def test_capex_missing_is_auto_carried(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["cash_conversion_inputs"]["metrics"] = [
        metric for metric in pcim["cash_conversion_inputs"]["metrics"]
        if metric["metric"] != "capex"
    ]
    pcim["cash_conversion_inputs"]["warnings"] = ["capex missing"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])

    parsed = _validate_llm_panel_output(
        _valid_buffett_payload(
            consumed_sections,
            missing_data=[],
            interpretation_limits=["No new ratios were calculated."],
            carried_warnings=[],
            financial_metrics_used=["roe", "roce", "cfo", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
        ),
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert any("capex is missing or incomplete" in item.lower() for item in parsed["financial_warnings_carried_forward"])
    assert any("financial warning auto-carried from PCIM: capex_missing" in item for item in parsed["schema_warnings"])


def test_payables_missing_is_auto_carried(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["working_capital_inputs"]["metrics"] = [
        metric for metric in pcim["working_capital_inputs"]["metrics"]
        if metric["metric"] not in {"payable_days", "cash_conversion_cycle"}
    ]
    pcim["working_capital_inputs"]["by_year"][0]["metrics"] = [
        metric for metric in pcim["working_capital_inputs"]["by_year"][0]["metrics"]
        if metric["metric"] not in {"payable_days", "cash_conversion_cycle"}
    ]
    pcim["working_capital_inputs"]["warnings"] = ["payables missing"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(dict.fromkeys(list(doctrine["evidence_required_from_pcim"]) + ["working_capital_inputs"]))

    parsed = _validate_llm_panel_output(
        _valid_buffett_payload(
            consumed_sections,
            missing_data=[],
            interpretation_limits=["No new ratios were calculated."],
            carried_warnings=[],
        ),
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert any("payables or payable-days evidence is missing" in item.lower() for item in parsed["financial_warnings_carried_forward"])
    assert any("financial warning auto-carried from PCIM: payables_missing" in item for item in parsed["schema_warnings"])


def test_basis_unknown_is_auto_carried(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["financial_trend_inputs"]["basis"] = "unknown"
    pcim["financial_trend_inputs"]["warnings"] = ["standalone/consolidated basis unclear"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(
        dict.fromkeys(list(doctrine["evidence_required_from_pcim"]) + ["financial_trend_inputs"])
    )

    parsed = _validate_llm_panel_output(
        _valid_buffett_payload(
            consumed_sections,
            missing_data=[],
            interpretation_limits=["No new ratios were calculated."],
            carried_warnings=[],
        ),
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert any("standalone/consolidated basis is unclear" in item.lower() for item in parsed["financial_warnings_carried_forward"])
    assert any("financial warning auto-carried from PCIM: basis_unknown" in item for item in parsed["schema_warnings"])


def test_validator_fails_if_analyst_claims_positive_fcf_while_fcf_missing(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["cash_conversion_inputs"]["metrics"] = [
        metric for metric in pcim["cash_conversion_inputs"]["metrics"]
        if metric["metric"] != "fcf"
    ]
    pcim["cash_conversion_inputs"]["warnings"] = ["free cash flow missing"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])
    payload = json.loads(
        _valid_buffett_payload(
            consumed_sections,
            missing_data=[],
            interpretation_limits=["No new ratios were calculated."],
            carried_warnings=[],
            financial_metrics_used=["roe", "roce", "cfo", "capex", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
        )
    )
    payload["financial_positive_signals"] = ["Strong FCF supports dividends."]

    with pytest.raises(ValueError, match="free cash flow missing"):
        _validate_llm_panel_output(
            json.dumps(payload),
            doctrine=doctrine,
            company="finpanel",
            pcim_path=pcim_path,
            pcim_version="1.0",
            pcim=pcim,
            consumed_sections=consumed_sections,
            allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
        )


@pytest.mark.parametrize("analyst", ["graham", "buffett", "fisher", "munger", "lynch"])
def test_all_analysts_auto_carry_fcf_missing(tmp_path, analyst):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["cash_conversion_inputs"]["metrics"] = [
        metric for metric in pcim["cash_conversion_inputs"]["metrics"]
        if metric["metric"] != "fcf"
    ]
    pcim["cash_conversion_inputs"]["warnings"] = ["free cash flow missing"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get(analyst)
    consumed_sections = list(doctrine["evidence_required_from_pcim"])

    metrics_by_analyst = {
        "graham": ["net_worth", "total_debt", "cfo", "capex", "book_value_per_share", "weighted_avg_shares"],
        "buffett": ["roe", "roce", "cfo", "capex", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
        "fisher": ["revenue", "eps_basic"],
        "munger": ["cfo", "capex", "debt_to_equity"],
        "lynch": ["revenue", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
    }
    assessment_fields = {
        "graham": {
            "financial_strength_assessment": "Financial posture looks reasonable but incomplete.",
            "integrity_assessment": "No clear integrity break is visible in the supplied PCIM.",
            "downside_protection_assessment": "Risk evidence suggests caution around concentration.",
            "key_red_flags": "Customer concentration and partial financial evidence limit confidence.",
        },
        "buffett": {
            "business_quality_assessment": "Business quality appears strong.",
            "moat_assessment": "Moat evidence is credible.",
            "capital_allocation_assessment": "Capital allocation is disciplined.",
            "management_rationality_assessment": "Management looks rational.",
        },
        "fisher": {
            "management_quality_assessment": "Management shows execution focus.",
            "growth_runway_assessment": "Growth runway appears credible.",
            "innovation_and_product_strength": "Innovation evidence is useful.",
            "execution_evidence": "Execution signals are real.",
        },
        "munger": {
            "incentive_alignment_assessment": "Incentives look directionally acceptable.",
            "governance_sanity_assessment": "Governance looks broadly sane.",
            "avoidable_risk_assessment": "Avoidable risk still needs monitoring.",
            "complexity_and_stupidity_checks": "Complexity remains manageable.",
        },
        "lynch": {
            "business_simplicity_assessment": "The business story is understandable.",
            "story_vs_evidence_assessment": "The story is broadly supported.",
            "growth_category_assessment": "Growth appears practical.",
            "hype_and_mismatch_checks": "No major hype mismatch dominates the current view.",
        },
    }
    payload = json.dumps(
        {
            "assessment": assessment_fields[analyst],
            "rating": "mixed",
            "key_findings": [{"finding": "The doctrine-specific evidence is directionally supportive.", "evidence_ids": ["ev_fin_1"]}],
            "red_flags": [{"flag": "Evidence is not complete enough for maximum confidence.", "severity": "medium", "evidence_ids": ["ev_fin_1"]}],
            "open_uncertainties": [{"uncertainty": "Coverage is still partial.", "evidence_ids": []}],
            "financial_metrics_used": metrics_by_analyst[analyst],
            "financial_red_flags": ["Comparability remains a watch item."],
            "financial_positive_signals": ["Directionally useful financial evidence is available."],
            "financial_missing_data": [],
            "financial_interpretation_limits": ["No new ratios were calculated."],
            "financial_assessment": {
                "financials_used": True,
                "basis_used": "consolidated",
                "key_financial_strengths": ["Directionally useful financial evidence is available."],
                "key_financial_concerns": ["Comparability remains a watch item."],
                "financial_red_flags": ["Comparability remains a watch item."],
                "missing_financial_data": [],
                "financial_interpretation_limits": ["No new ratios were calculated."],
                "financial_warnings_carried_forward": [],
            },
            "financial_sections_consumed": list(
                dict.fromkeys(
                    section
                    for section in consumed_sections
                    if "financial" in section
                    or section in {
                        "cash_conversion_inputs",
                        "per_share_inputs",
                        "balance_sheet_strength_inputs",
                        "return_on_capital_inputs",
                        "corporate_action_inputs",
                    }
                )
            ),
            "financial_warnings_carried_forward": [],
            "evidence_ids": ["ev_fin_1"],
            "historical_context_used": True,
            "years_considered": ["fy24", "fy25"],
            "supporting_pcim_sections": consumed_sections,
            "reasoning_limits": ["PCIM only."],
            "user_facing_brief": {
                "title": LENS_CONFIG[analyst]["title"],
                "lens": LENS_CONFIG[analyst]["lens_text"],
                "what_looks_good": ["Some evidence-backed strengths exist."],
                "what_needs_caution": ["Material gaps remain."],
                "what_is_missing": ["Some financial context is missing."],
                "bottom_line": "Useful but incomplete.",
            },
        }
    )

    parsed = _validate_llm_panel_output(
        payload,
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )

    assert any(
        "free cash flow is missing; fcf-based conclusions cannot be assessed." in item.lower()
        for item in parsed["financial_warnings_carried_forward"]
    )
    assert any(
        "free cash flow is missing, so owner earnings, fcf margin, and fcf-supported dividend sustainability cannot be assessed."
        in item.lower()
        for item in parsed["financial_interpretation_limits"]
    )
    if analyst == "graham":
        assert any(
            "margin-of-safety judgment is limited because free cash flow is unavailable." in item.lower()
            for item in parsed["financial_interpretation_limits"]
        )
    if analyst == "buffett":
        assert any(
            "owner earnings cannot be assessed because free cash flow/capex data is missing or incomplete."
            in item.lower()
            for item in parsed["financial_interpretation_limits"]
        )


def test_imprecise_pcim_share_warning_becomes_warning_not_failure(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["per_share_inputs"]["metrics"] = [
        metric for metric in pcim["per_share_inputs"]["metrics"]
        if metric["metric"] not in {"weighted_avg_shares", "diluted_shares"}
    ]
    pcim["financial_fundamentals_inputs"]["warnings"] = ["share count missing"]
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])

    payload = _valid_buffett_payload(
        consumed_sections,
        missing_data=["weighted average shares missing"],
        interpretation_limits=["Per-share analysis is limited because weighted average share count is missing."],
        carried_warnings=["weighted average shares missing"],
        financial_metrics_used=["roe", "roce", "cfo", "capex", "fcf", "eps_basic", "book_value_per_share"],
    )

    parsed = _validate_llm_panel_output(
        payload,
        doctrine=doctrine,
        company="finpanel",
        pcim_path=pcim_path,
        pcim_version="1.0",
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
    )
    assert parsed["evidence_grounding_status"] == "warning"
    assert any("imprecise" in item.lower() for item in parsed["evidence_grounding_warnings"])


def test_blocked_false_warning_is_rejected_when_truth_pack_has_metric(tmp_path):
    pcim_path = _write_pcim(tmp_path, "finpanel")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["financial_warning_policy"] = {
        "financial_warnings_blocked_downstream": ["free cash flow missing"],
    }
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")
    consumed_sections = list(doctrine["evidence_required_from_pcim"])

    payload = _valid_buffett_payload(
        consumed_sections,
        missing_data=[],
        interpretation_limits=["No new ratios were calculated."],
        carried_warnings=["free cash flow missing"],
        financial_metrics_used=["roe", "roce", "cfo", "capex", "fcf", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
    )

    with pytest.raises(ValueError, match="blocked financial warnings"):
        _validate_llm_panel_output(
            payload,
            doctrine=doctrine,
            company="finpanel",
            pcim_path=pcim_path,
            pcim_version="1.0",
            pcim=pcim,
            consumed_sections=consumed_sections,
            allowed_evidence_ids=["ev_fin_1", "ev_fd_1"],
        )
