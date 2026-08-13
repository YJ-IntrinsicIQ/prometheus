import json
from pathlib import Path

import pytest

from core.company_context import CompanyContext
from intelligence.investor_panel.evidence_router import split_clean_and_diagnostics
from intelligence.investor_panel import runner as panel_runner
from intelligence.investor_panel.runner import (
    InvestorPanelRunner,
    finalize_analyst_financial_truth_consistency,
    finalize_analyst_financial_warnings,
    finalize_analyst_validation_status,
)
from pipelines import run_company_pipeline
from pipelines.pipeline_context import set_context


BRIEF_TITLES = {
    "graham": "Graham School of Thought: Downside Protection",
    "buffett": "Buffett School of Thought: Business Quality & Capital Allocation",
    "fisher": "Fisher School of Thought: Growth Quality & Management Ambition",
    "munger": "Munger School of Thought: Incentives, Governance & Avoidable Mistakes",
    "lynch": "Lynch School of Thought: Simple Story, Growth Runway & Hype Check",
}


def _read_saved_outputs(written: dict[str, Path], analyst: str):
    clean = json.loads(written[f"{analyst}_analysis.json"].read_text(encoding="utf-8"))
    diagnostics = json.loads(
        written[f"{analyst}_analysis_diagnostics.json"].read_text(encoding="utf-8")
    )
    return clean, diagnostics


def _write_pcim(base_dir: Path, company: str, missing_sections=None):
    if missing_sections is None:
        missing_sections = []
    company_memory_dir = base_dir / "companies" / company / "company_memory"
    company_memory_dir.mkdir(parents=True, exist_ok=True)

    pcim = {
        "contract_version": "1.0",
        "company": company,
        "available_years": ["fy25"],
        "business_understanding": {
            "latest_business_view": {
                "year": "fy25",
                "business_dnas": [{"value": "Enterprise Platform", "evidence_ids": ["ev_bu_1"]}],
                "business_model": {"business_summary": "Simple platform business", "evidence_ids": ["ev_bu_1"]},
                "management_focus": [{"value": "Platform reliability", "evidence_ids": ["ev_focus_1"]}],
            },
            "business_dna_by_year": [],
            "business_model_by_year": [],
        },
        "financial_strength_inputs": {
            "capital_allocation_by_year": [{"year": "fy25", "items": [{"value": "Disciplined reinvestment", "evidence_ids": ["ev_cap_1"]}]}],
            "working_capital_and_liquidity_signals_by_year": [{"year": "fy25", "items": [{"value": "Cash and receivables support liquidity", "signal_type": "working_capital_signals", "evidence_ids": ["ev_fin_1"]}]}],
            "dividend_and_distribution_signals_by_year": [{"year": "fy25", "items": [{"value": "Dividend declared", "signal_type": "dividend_payout", "evidence_ids": ["ev_div_1"]}]}],
            "uncertainty_notes": [],
        },
        "management_quality_inputs": {
            "management_focus_by_year": [{"year": "fy25", "items": [{"value": "Execution focus", "evidence_ids": ["ev_mgmt_1"]}]}],
            "promise_tracker": [{"normalized_promise_theme": "secure growth", "source_references": [], "yearly_mentions": []}],
            "promises_by_year": [{"year": "fy25", "items": [{"value": "Maintain secure growth", "evidence_ids": ["ev_prom_1"]}]}],
        },
        "growth_quality_inputs": {
            "projects_by_year": [{"year": "fy25", "items": [{"value": "Scale platform", "evidence_ids": ["ev_proj_1"]}]}],
            "initiatives_by_year": [{"year": "fy25", "items": [{"value": "Improve automation", "evidence_ids": ["ev_init_1"]}]}],
            "strategy_timeline": [{"year": "fy25", "business_dnas": []}],
            "financial_growth_summary": {
                "quality_status": "pass",
                "summary": "Growth remains healthy.",
                "signals": ["Revenue and EPS both improved."],
                "by_year": [{"year": "fy25", "growth_metrics": [{"metric": "revenue", "growth_percent": 18.0}, {"metric": "eps_basic", "growth_percent": 14.0}]}],
                "source_artifact": "financial_quality_summary.json",
            },
        },
        "financial_fundamentals_inputs": {
            "basis_used": "consolidated",
            "by_year": [
                {
                    "year": "fy25",
                    "key_metrics": [
                        {"field": "revenue", "value_crore": 120.0, "source_year": "fy25", "source_artifact": "normalized_fundamentals.json"},
                        {"field": "pat", "value_crore": 18.0, "source_year": "fy25", "source_artifact": "normalized_fundamentals.json"},
                        {"field": "net_worth", "value_crore": 70.0, "source_year": "fy25", "source_artifact": "normalized_fundamentals.json"},
                        {"field": "total_debt", "value_crore": 9.0, "source_year": "fy25", "source_artifact": "normalized_fundamentals.json"},
                    ],
                    "warnings": [],
                }
            ],
            "warnings": [],
        },
        "financial_trend_inputs": {
            "years_covered": ["fy24", "fy25"],
            "basis": "consolidated",
            "metric_trends": [
                {"metric": "revenue", "series": [{"year": "fy25", "value": 120.0, "source_artifact": "financial_trends.json"}]},
                {"metric": "pat", "series": [{"year": "fy25", "value": 18.0, "source_artifact": "financial_trends.json"}]},
            ],
            "warnings": [],
            "limitations": [],
            "source_artifact": "financial_trends.json",
        },
        "cash_conversion_inputs": {
            "status": "pass",
            "summary": "Cash conversion is healthy.",
            "signals": ["CFO exceeds PAT."],
            "basis": "consolidated",
            "warnings": [],
            "metrics": [
                {"metric": "cfo", "series": [{"year": "fy25", "value": 22.0, "source_artifact": "financial_trends.json"}]},
                {"metric": "capex", "series": [{"year": "fy25", "value": -7.0, "source_artifact": "financial_trends.json"}]},
                {"metric": "fcf", "series": [{"year": "fy25", "value": 15.0, "source_artifact": "financial_trends.json"}]},
                {"metric": "cfo_to_pat", "series": [{"year": "fy25", "value": 1.22, "source_artifact": "financial_trends.json"}]},
            ],
            "source_artifact": "financial_quality_summary.json",
        },
        "return_on_capital_inputs": {
            "status": "pass",
            "summary": "Returns remain solid.",
            "signals": ["ROCE remains above 15%."],
            "basis": "consolidated",
            "warnings": [],
            "metrics": [
                {"metric": "roe", "series": [{"year": "fy25", "value": 19.0, "source_artifact": "financial_trends.json"}]},
                {"metric": "roce", "series": [{"year": "fy25", "value": 17.0, "source_artifact": "financial_trends.json"}]},
            ],
            "source_artifact": "financial_quality_summary.json",
        },
        "balance_sheet_strength_inputs": {
            "status": "pass",
            "summary": "Leverage remains controlled.",
            "signals": ["Debt to equity remains modest."],
            "basis": "consolidated",
            "warnings": [],
            "metrics": [
                {"metric": "total_debt", "series": [{"year": "fy25", "value": 9.0, "source_artifact": "financial_trends.json"}]},
                {"metric": "debt_to_equity", "series": [{"year": "fy25", "value": 0.13, "source_artifact": "financial_trends.json"}]},
            ],
            "source_artifact": "financial_quality_summary.json",
        },
        "working_capital_inputs": {
            "basis": "consolidated",
            "metrics": [
                {"metric": "payable_days", "series": [{"year": "fy25", "value": 28.0, "source_artifact": "financial_ratios.json"}]},
                {"metric": "cash_conversion_cycle", "series": [{"year": "fy25", "value": 18.0, "source_artifact": "financial_ratios.json"}]},
            ],
            "by_year": [
                {
                    "year": "fy25",
                    "metrics": [
                        {"metric": "payable_days", "value": 28.0, "unit": "days", "period": "fy25", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_ratios.json"]},
                        {"metric": "cash_conversion_cycle", "value": 18.0, "unit": "days", "period": "fy25", "basis": "consolidated", "confidence": "medium", "source_artifacts": ["financial_ratios.json"]},
                    ],
                    "warnings": [],
                    "limitations": [],
                }
            ],
            "warnings": [],
            "source_artifact": "financial_ratios.json",
        },
        "per_share_inputs": {
            "basis": "consolidated",
            "metrics": [
                {"metric": "eps_basic", "series": [{"year": "fy25", "value": 12.0, "source_artifact": "financial_trends.json"}]},
                {"metric": "book_value_per_share", "series": [{"year": "fy25", "value": 55.0, "source_artifact": "financial_trends.json"}]},
                {"metric": "shares_outstanding", "series": [{"year": "fy25", "value": 1.6, "source_artifact": "financial_trends.json"}]},
                {"metric": "weighted_avg_shares", "series": [{"year": "fy25", "value": 1.4, "source_artifact": "financial_trends.json"}]},
                {"metric": "diluted_shares", "series": [{"year": "fy25", "value": 1.45, "source_artifact": "financial_trends.json"}]},
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
            "attributions": [{"metric": "revenue", "movement": "improved", "possible_driver": "Customer additions", "source_artifacts": ["financial_driver_attribution.json"], "evidence_ids": ["ev_fin_driver_1"]}],
            "warnings": [],
            "limitations": [],
            "source_artifact": "financial_driver_attribution.json",
        },
        "moat_inputs": {
            "business_dna_by_year": [{"year": "fy25", "items": [{"value": "Enterprise Platform", "evidence_ids": ["ev_moat_1"]}]}],
            "business_model_by_year": [{"year": "fy25", "business_summary": "Durable platform", "evidence_ids": ["ev_moat_1"]}],
            "entities": [{"entity_name": "Alpha Platform", "mentions": [{"evidence_ids": ["ev_entity_1"]}]}],
        },
        "capital_allocation_inputs": {
            "capital_allocation_by_year": [{"year": "fy25", "items": [{"value": "Reinvest in platform", "evidence_ids": ["ev_cap_1"]}]}],
            "promises_by_year": [{"year": "fy25", "items": [{"value": "Maintain capital discipline", "evidence_ids": ["ev_cap_2"]}]}],
        },
        "risk_inputs": {
            "risk_by_year": [{"year": "fy25", "items": [{"value": "Customer concentration", "evidence_ids": ["ev_risk_1"]}]}],
            "risk_evolution": [{"year": "fy25", "risks": []}],
        },
        "incentive_inputs": {
            "capital_allocation_by_year": [{"year": "fy25", "items": [{"value": "Reinvest rationally", "evidence_ids": ["ev_inc_1"]}]}],
            "promise_tracker": [{"normalized_promise_theme": "owner alignment", "yearly_mentions": []}],
            "uncertainty_notes": [],
        },
        "governance_and_incentive_inputs": {
            "equity_incentives_by_year": [{"year": "fy25", "items": [{"value": "RSU issuance", "signal_type": "equity_incentives", "evidence_ids": ["ev_inc_1"]}]}],
            "related_party_and_control_items_by_year": [{"year": "fy25", "items": [{"value": "Related-party advance", "signal_type": "related_party_exposure", "evidence_ids": ["ev_gov_1"]}]}],
            "risk_governance_flags_by_year": [{"year": "fy25", "items": [{"value": "Risk governance weakness", "signal_type": "governance_risk", "evidence_ids": ["ev_gov_2"]}]}],
            "management_conduct_signals_by_year": [],
            "uncertainty_notes": [],
        },
        "business_economics_inputs": {
            "business_model_by_year": [{"year": "fy25", "business_summary": "Durable platform", "evidence_ids": ["ev_bu_1"]}],
            "customer_and_scale_signals_by_year": [{"year": "fy25", "items": [{"value": "Added customers and scaled platform", "signal_type": "customer_and_scale_signal", "evidence_ids": ["ev_be_1"]}]}],
            "pricing_and_margin_signals_by_year": [],
            "concentration_and_recurrence_signals_by_year": [{"year": "fy25", "items": [{"value": "Customer concentration risk", "signal_type": "concentration_or_recurrence_signal", "evidence_ids": ["ev_risk_1"]}]}],
            "uncertainty_notes": [],
        },
        "growth_execution_inputs": {
            "projects_by_year": [{"year": "fy25", "items": [{"value": "Scale platform", "evidence_ids": ["ev_proj_1"]}]}],
            "initiatives_by_year": [{"year": "fy25", "items": [{"value": "Improve automation", "evidence_ids": ["ev_init_1"]}]}],
            "promises_by_year": [{"year": "fy25", "items": [{"value": "Maintain secure growth", "evidence_ids": ["ev_prom_1"]}]}],
            "growth_claims_by_year": [{"year": "fy25", "items": [{"value": "Added 400 customers", "signal_type": "growth_claim", "evidence_ids": ["ev_growth_1"]}]}],
            "executed_promises_by_year": [],
            "multi_year_trend_markers": [{"year": "fy25", "business_dnas": []}],
            "uncertainty_notes": [],
        },
        "simplicity_and_story_inputs": {
            "latest_business_view": {"year": "fy25", "business_model": {"business_summary": "Understandable business"}},
            "strategy_timeline": [{"year": "fy25"}],
            "focus_by_year": [{"year": "fy25", "items": [{"value": "Simple story", "evidence_ids": ["ev_story_1"]}]}],
        },
        "story_vs_numbers_inputs": {
            "latest_business_view": {"year": "fy25", "business_model": {"business_summary": "Understandable business"}},
            "numeric_support_by_year": [{"year": "fy25", "items": [{"value": "NPS 65 and 400 customers", "signal_type": "numeric_support", "evidence_ids": ["ev_story_2"]}]}],
            "hype_or_unverified_claims_by_year": [{"year": "fy25", "items": [{"value": "Market leader claim", "signal_type": "hype_or_unverified_claim", "evidence_ids": ["ev_story_3"]}]}],
            "evidence_confidence_notes": [],
            "uncertainty_notes": [],
        },
        "multi_year_inputs": {
            "years_covered": ["fy24", "fy25"],
            "business_dna_evolution": {
                "stable_dnas": ["Enterprise Platform"],
                "not_detected_this_year": ["Export"],
                "evidence_ids": ["ev_my_dna_1"],
            },
            "management_consistency": {
                "repeated_focus_areas": ["platform_reliability"],
                "consistency_observations": [
                    {
                        "theme": "platform_reliability",
                        "consistency_status": "consistent",
                        "evidence_ids": ["ev_my_mgmt_1"],
                    }
                ],
                "evidence_gaps": ["Only two usable years are available; conclusions remain provisional."],
            },
            "strategy_evolution": {
                "continued_themes": ["platform_reliability"],
                "possible_strategy_shifts": [
                    {
                        "from_year": "fy24",
                        "to_year": "fy25",
                        "note": "Removed themes indicate they were not detected in later artifacts, not confirmed abandonment.",
                        "evidence_ids": ["ev_my_strategy_1"],
                    }
                ],
                "limitations": [],
            },
            "promise_follow_through": {
                "unclear_promises": [
                    {
                        "promise_id": "promise_1",
                        "normalized_promise": "maintain secure growth",
                        "related_evidence_ids": ["ev_my_promise_1"],
                        "source_mentions": [{"value": "Maintain secure growth", "evidence_ids": ["ev_my_promise_1"]}],
                    }
                ],
                "limitations": ["Promise fulfillment is not explicit in current evidence."],
            },
            "recurring_risks": {
                "recurring_risks": [
                    {
                        "risk_id": "risk_credit_risk",
                        "normalized_risk": "credit_risk",
                        "severity_by_year": {"fy24": "medium", "fy25": "medium"},
                        "related_evidence_ids": ["ev_my_risk_1"],
                        "source_mentions": [{"value": "Credit risk", "evidence_ids": ["ev_my_risk_1"], "source_page": 44}],
                    }
                ],
                "worsening_risks": [],
                "top_risk_observations": [],
            },
            "capital_allocation_pattern": {
                "capex_or_cwip_activity": [
                    {
                        "value": "Reinvested in platform reliability",
                        "category": "capex",
                        "amount": "120.0",
                        "evidence_ids": ["ev_my_cap_1"],
                    }
                ],
                "share_splits": [],
                "treasury_investments": [],
                "debt_borrowing_signals": [],
                "related_party_transactions": [],
                "loans_and_advances": [],
                "missing_financial_evidence": [],
            },
            "evidence_map": {
                "ev_my_dna_1": {"source_year": "fy24", "source_artifact": "business_classification.json", "source_item_id": "Enterprise Platform", "source_page": 12},
                "ev_my_mgmt_1": {"source_year": "fy25", "source_artifact": "management_summary.json", "source_item_id": "INIT_1", "source_page": 22},
                "ev_my_promise_1": {"source_year": "fy25", "source_artifact": "company_intelligence.json", "source_item_id": "PROM_1", "source_page": 28},
                "ev_my_risk_1": {"source_year": "fy25", "source_artifact": "company_intelligence.json", "source_item_id": "RISK_1", "source_page": 44},
                "ev_my_cap_1": {"source_year": "fy25", "source_artifact": "company_intelligence.json", "source_item_id": "CAP_1", "source_page": 31},
            },
            "limitations": ["Only two usable years are available, so historical conclusions remain provisional."],
        },
        "evidence_map": {
            "business_understanding": ["ev_bu_1", "ev_focus_1"],
            "financial_strength_inputs": ["ev_cap_1", "ev_fin_1", "ev_div_1"],
            "management_quality_inputs": ["ev_mgmt_1", "ev_prom_1"],
            "growth_quality_inputs": ["ev_proj_1", "ev_init_1"],
            "moat_inputs": ["ev_moat_1", "ev_entity_1"],
            "capital_allocation_inputs": ["ev_cap_1", "ev_cap_2"],
            "risk_inputs": ["ev_risk_1"],
            "incentive_inputs": ["ev_inc_1"],
            "simplicity_and_story_inputs": ["ev_story_1"],
            "governance_and_incentive_inputs": ["ev_inc_1", "ev_gov_1", "ev_gov_2"],
            "business_economics_inputs": ["ev_be_1", "ev_risk_1"],
            "growth_execution_inputs": ["ev_proj_1", "ev_init_1", "ev_prom_1", "ev_growth_1"],
            "story_vs_numbers_inputs": ["ev_story_2", "ev_story_3"],
            "financial_fundamentals_inputs": ["ev_fin_1"],
            "financial_trend_inputs": ["ev_fin_1"],
            "cash_conversion_inputs": ["ev_fin_1"],
            "return_on_capital_inputs": ["ev_fin_1"],
            "balance_sheet_strength_inputs": ["ev_fin_1"],
            "per_share_inputs": ["ev_fin_1"],
            "corporate_action_inputs": ["ev_fin_1"],
            "ownership_inputs": ["ev_fin_1"],
            "financial_driver_inputs": ["ev_fin_driver_1"],
            "multi_year_inputs": ["ev_my_dna_1", "ev_my_mgmt_1", "ev_my_promise_1", "ev_my_risk_1", "ev_my_cap_1"],
        },
        "uncertainty_missing_data": {"incomplete_years": [], "missing_sections": [], "missing_items": []},
        "source_cim": "cim_v1.json",
    }

    for section in missing_sections:
        pcim[section] = {} if isinstance(pcim.get(section), dict) else []
        if section in pcim["evidence_map"]:
            pcim["evidence_map"][section] = []
        pcim["uncertainty_missing_data"]["missing_sections"].append(
            {"year": "fy25", "section": section, "reason": "Missing for test"}
        )

    (company_memory_dir / "pcim_v1.json").write_text(
        json.dumps(pcim),
        encoding="utf-8",
    )


def _write_large_pcim(base_dir: Path, company: str):
    company_memory_dir = base_dir / "companies" / company / "company_memory"
    company_memory_dir.mkdir(parents=True, exist_ok=True)
    long_chunk = "Very long raw excerpt from the annual report. " * 80
    large_items = []
    for idx in range(40):
        large_items.append(
            {
                "value": f"Risk item {idx}",
                "source_year": "fy25",
                "source_artifact": "management_summary.json",
                "source_item_id": f"RISK_{idx}",
                "category": "Risk",
                "status": "Open",
                "confidence": "low",
                "page": 50 + idx,
                "raw_text": long_chunk,
                "evidence_ids": [f"ev_risk_{idx}"],
                "evidence_references": [
                    {
                        "page": 50 + idx,
                        "content": long_chunk,
                        "source_artifact": "management_summary.json",
                        "evidence_ids": [f"ev_risk_{idx}"],
                    }
                ],
            }
        )

    pcim = {
        "contract_version": "1.0",
        "company": company,
        "risk_inputs": {
            "risk_by_year": [{"year": "fy25", "items": large_items}],
            "risk_evolution": [{"year": "fy25", "risks": large_items}],
        },
        "management_quality_inputs": {
            "promises_by_year": [{"year": "fy25", "items": large_items}],
        },
        "capital_allocation_inputs": {
            "capital_allocation_by_year": [{"year": "fy25", "items": large_items}],
        },
        "incentive_inputs": {"promise_tracker": large_items},
        "governance_and_incentive_inputs": {
            "related_party_and_control_items_by_year": [{"year": "fy25", "items": large_items}],
        },
        "cash_conversion_inputs": {
            "metrics": [
                {"metric": "cfo", "series": [{"year": "fy25", "value": 18.0, "source_artifact": "financial_trends.json"}]},
                {"metric": "capex", "series": [{"year": "fy25", "value": -6.0, "source_artifact": "financial_trends.json"}]},
                {"metric": "fcf", "series": [{"year": "fy25", "value": 12.0, "source_artifact": "financial_trends.json"}]},
            ],
            "warnings": [],
            "source_artifact": "financial_quality_summary.json",
        },
        "balance_sheet_strength_inputs": {
            "metrics": [
                {"metric": "debt_to_equity", "series": [{"year": "fy25", "value": 0.2, "source_artifact": "financial_trends.json"}]},
            ],
            "warnings": [],
            "source_artifact": "financial_quality_summary.json",
        },
        "corporate_action_inputs": {
            "by_year": [{"year": "fy25", "actions": [{"action_type": "qip_issue", "impact_on_share_count": "increase", "impact_on_eps_comparability": "yes"}]}],
            "warnings": ["QIP affects comparability."],
            "source_artifact": "corporate_actions.json",
        },
        "financial_driver_inputs": {
            "attributions": [{"metric": "revenue", "possible_driver": "Platform expansion", "source_artifacts": ["financial_driver_attribution.json"], "evidence_ids": ["ev_fd_1"]}],
            "warnings": [],
            "limitations": [],
            "source_artifact": "financial_driver_attribution.json",
        },
        "business_economics_inputs": {
            "customer_and_scale_signals_by_year": [{"year": "fy25", "items": large_items}],
        },
        "growth_execution_inputs": {
            "growth_claims_by_year": [{"year": "fy25", "items": large_items}],
        },
        "business_understanding": {},
        "growth_quality_inputs": {},
        "moat_inputs": {},
        "financial_strength_inputs": {},
        "simplicity_and_story_inputs": {},
        "story_vs_numbers_inputs": {},
        "evidence_map": {
            "risk_inputs": [f"ev_risk_{idx}" for idx in range(40)],
            "management_quality_inputs": [f"ev_mgmt_{idx}" for idx in range(40)],
            "capital_allocation_inputs": [f"ev_cap_{idx}" for idx in range(40)],
            "incentive_inputs": [f"ev_inc_{idx}" for idx in range(40)],
            "governance_and_incentive_inputs": [f"ev_gov_{idx}" for idx in range(40)],
            "cash_conversion_inputs": ["ev_fd_1"],
            "balance_sheet_strength_inputs": ["ev_fd_1"],
            "corporate_action_inputs": ["ev_fd_1"],
            "financial_driver_inputs": ["ev_fd_1"],
            "business_economics_inputs": [f"ev_be_{idx}" for idx in range(40)],
            "growth_execution_inputs": [f"ev_growth_{idx}" for idx in range(40)],
        },
        "uncertainty_missing_data": {"incomplete_years": [], "missing_sections": [], "missing_items": []},
        "source_cim": "cim_v1.json",
    }
    (company_memory_dir / "pcim_v1.json").write_text(json.dumps(pcim), encoding="utf-8")


class FakeLLM:
    def __init__(self, response_text):
        self.response_text = response_text
        self.calls = []

    def generate(
        self,
        prompt,
        response_schema=None,
        temperature=0.0,
        max_tokens=None,
        system_prompt=None,
    ):
        self.calls.append(
            {
                "prompt": prompt,
                "response_schema": response_schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "system_prompt": system_prompt,
            }
        )
        return type(
            "AIResponse",
            (),
            {
                "text": self.response_text,
                "provider": "mock",
                "model": "mock-panel-model",
            },
        )()


class SequencedFakeLLM:
    def __init__(self, response_texts):
        self.response_texts = list(response_texts)
        self.calls = []

    def generate(
        self,
        prompt,
        response_schema=None,
        temperature=0.0,
        max_tokens=None,
        system_prompt=None,
    ):
        self.calls.append(
            {
                "prompt": prompt,
                "response_schema": response_schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "system_prompt": system_prompt,
            }
        )
        if not self.response_texts:
            raise AssertionError("SequencedFakeLLM ran out of responses")
        response_text = self.response_texts.pop(0)
        return type(
            "AIResponse",
            (),
            {
                "text": response_text,
                "provider": "mock",
                "model": "mock-panel-model",
            },
        )()


class PromptRoutingFakeLLM:
    def __init__(self, response_map):
        self.response_map = dict(response_map)
        self.calls = []

    def generate(
        self,
        prompt,
        response_schema=None,
        temperature=0.0,
        max_tokens=None,
        system_prompt=None,
    ):
        self.calls.append(
            {
                "prompt": prompt,
                "response_schema": response_schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "system_prompt": system_prompt,
            }
        )
        doctrine_id = None
        for candidate in self.response_map:
            if f"Doctrine ID: {candidate}" in prompt:
                doctrine_id = candidate
                break
        if doctrine_id is None:
            raise AssertionError("PromptRoutingFakeLLM could not determine doctrine from prompt")
        return type(
            "AIResponse",
            (),
            {
                "text": self.response_map[doctrine_id],
                "provider": "mock",
                "model": "mock-panel-model",
            },
        )()


def _llm_output(doctrine_id="graham", rating="mixed", evidence_ids=None):
    if evidence_ids is None:
        evidence_ids = ["ev_cap_1", "ev_risk_1"]

    if doctrine_id == "graham":
        assessment = {
            "financial_strength_assessment": "Financial posture looks reasonable but incomplete.",
            "integrity_assessment": "No clear integrity break is visible in the supplied PCIM.",
            "downside_protection_assessment": "Risk evidence suggests caution around concentration.",
            "key_red_flags": "Customer concentration and partial financial evidence limit confidence.",
        }
        supporting_pcim_sections = [
            "financial_strength_inputs",
            "financial_fundamentals_inputs",
            "cash_conversion_inputs",
            "balance_sheet_strength_inputs",
            "per_share_inputs",
            "financial_driver_inputs",
            "governance_and_incentive_inputs",
            "risk_inputs",
            "capital_allocation_inputs",
            "multi_year_inputs",
            "evidence_map",
            "uncertainty_missing_data",
        ]
    elif doctrine_id == "buffett":
        assessment = {
            "business_quality_assessment": "Business quality appears durable from the supplied PCIM.",
            "moat_assessment": "Moat evidence is credible but not fully stress-tested.",
            "capital_allocation_assessment": "Capital allocation looks rational in the available record.",
            "management_rationality_assessment": "Management appears reasonably owner-minded.",
        }
        supporting_pcim_sections = [
            "business_understanding",
            "business_economics_inputs",
            "moat_inputs",
            "financial_fundamentals_inputs",
            "cash_conversion_inputs",
            "return_on_capital_inputs",
            "per_share_inputs",
            "financial_driver_inputs",
            "capital_allocation_inputs",
            "management_quality_inputs",
            "governance_and_incentive_inputs",
            "multi_year_inputs",
            "evidence_map",
            "uncertainty_missing_data",
        ]
    elif doctrine_id == "munger":
        assessment = {
            "incentive_alignment_assessment": "Incentive evidence is directionally positive.",
            "governance_sanity_assessment": "Governance signals appear sane but not exhaustive.",
            "avoidable_risk_assessment": "Some avoidable operational risk remains.",
            "complexity_and_stupidity_checks": "The business is manageable but some complexity remains.",
        }
        supporting_pcim_sections = [
            "governance_and_incentive_inputs",
            "risk_inputs",
            "management_quality_inputs",
            "cash_conversion_inputs",
            "balance_sheet_strength_inputs",
            "corporate_action_inputs",
            "financial_driver_inputs",
            "capital_allocation_inputs",
            "multi_year_inputs",
            "evidence_map",
            "uncertainty_missing_data",
        ]
    elif doctrine_id == "fisher":
        assessment = {
            "management_quality_assessment": "Management shows execution focus.",
            "growth_runway_assessment": "Growth runway appears credible but still concentrated.",
            "innovation_and_product_strength": "Innovation evidence ties to product and platform scale.",
            "execution_evidence": "Execution signals are real and repeated.",
        }
        supporting_pcim_sections = [
            "business_understanding",
            "management_quality_inputs",
            "financial_trend_inputs",
            "financial_driver_inputs",
            "growth_execution_inputs",
            "growth_quality_inputs",
            "moat_inputs",
            "multi_year_inputs",
            "evidence_map",
            "uncertainty_missing_data",
        ]
    else:
        assessment = {
            "business_simplicity_assessment": "The business can be explained simply enough from PCIM.",
            "story_vs_evidence_assessment": "The story is broadly supported by the evidence.",
            "growth_category_assessment": "Growth appears practical rather than hype-led.",
            "hype_and_mismatch_checks": "No major hype mismatch dominates the current view.",
        }
        supporting_pcim_sections = [
            "business_understanding",
            "management_quality_inputs",
            "financial_trend_inputs",
            "growth_quality_inputs",
            "per_share_inputs",
            "corporate_action_inputs",
            "financial_driver_inputs",
            "growth_execution_inputs",
            "simplicity_and_story_inputs",
            "multi_year_inputs",
            "story_vs_numbers_inputs",
            "evidence_map",
            "uncertainty_missing_data",
        ]

    return json.dumps(
        {
            "assessment": assessment,
            "rating": rating,
            "key_findings": [
                {
                    "finding": "The doctrine-specific evidence is directionally supportive.",
                    "evidence_ids": evidence_ids[:1],
                }
            ],
            "red_flags": [
                {
                    "flag": "Evidence is not complete enough for maximum confidence.",
                    "severity": "medium",
                    "evidence_ids": evidence_ids[1:],
                }
            ],
            "open_uncertainties": [
                {
                    "uncertainty": "Missing multi-year evidence limits confidence.",
                    "evidence_ids": [],
                }
            ],
            **_financial_payload(
                doctrine_id,
                metrics={
                    "graham": ["net_worth", "total_debt", "cfo", "capex", "fcf", "book_value_per_share", "weighted_avg_shares"],
                    "buffett": ["revenue", "cfo", "capex", "fcf", "roce", "roe", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
                    "fisher": ["revenue", "eps_basic"],
                    "munger": ["cfo", "capex", "debt_to_equity"],
                    "lynch": ["revenue", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
                }[doctrine_id],
            ),
            "evidence_ids": evidence_ids,
            "historical_context_used": True,
            "years_considered": ["fy24", "fy25"],
            "supporting_pcim_sections": supporting_pcim_sections,
            "reasoning_limits": [
                "This judgment uses only supplied PCIM sections.",
                "No valuation conclusion is attempted.",
            ],
            "user_facing_brief": {
                "title": BRIEF_TITLES[doctrine_id],
                "lens": "This lens focuses on the most decision-useful strengths, cautions, and missing context.",
                "financial_lens": "The financial lens focuses on only the supplied numbers, their limitations, and what they imply without inventing new math.",
                "what_looks_good": [
                    "The business shows some evidence-backed strengths."
                ],
                "what_needs_caution": [
                    "Important risks still need close monitoring."
                ],
                "what_is_missing": [
                    "Some multi-year context is still missing."
                ],
                "bottom_line": "The current picture is useful but still incomplete, so confidence should stay measured.",
            },
        }
    )


def _brief_payload(doctrine_id="graham"):
    return {
        "title": BRIEF_TITLES[doctrine_id],
        "lens": "This lens focuses on the most decision-useful strengths, cautions, and missing context.",
        "financial_lens": "The financial lens focuses on only the supplied numbers, their limitations, and what they imply without inventing new math.",
        "what_looks_good": ["The business shows some evidence-backed strengths."],
        "what_needs_caution": ["Important risks still need close monitoring."],
        "what_is_missing": ["Some multi-year context is still missing."],
        "bottom_line": "The current picture is useful but still incomplete, so confidence should stay measured.",
    }


def _financial_payload(doctrine_id="graham", *, concerns=None, red_flags=None, metrics=None):
    default_metrics = {
        "graham": ["net_worth", "total_debt", "cfo", "capex", "fcf", "book_value_per_share", "weighted_avg_shares"],
        "buffett": ["revenue", "cfo", "capex", "fcf", "roce", "roe", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
        "fisher": ["revenue", "eps_basic"],
        "munger": ["cfo", "capex", "debt_to_equity"],
        "lynch": ["revenue", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
    }
    financial_sections = {
        "graham": ["financial_strength_inputs", "cash_conversion_inputs", "balance_sheet_strength_inputs", "per_share_inputs"],
        "buffett": ["financial_fundamentals_inputs", "cash_conversion_inputs", "return_on_capital_inputs", "per_share_inputs"],
        "fisher": ["financial_trend_inputs", "financial_driver_inputs"],
        "munger": ["cash_conversion_inputs", "balance_sheet_strength_inputs", "corporate_action_inputs", "financial_driver_inputs"],
        "lynch": ["financial_trend_inputs", "per_share_inputs", "corporate_action_inputs"],
    }
    key_strengths = {
        "graham": ["Cash conversion remains better than PAT."],
        "buffett": ["Cash conversion remains better than PAT."],
        "fisher": ["Revenue and EPS both improved in the supplied evidence."],
        "munger": ["Debt discipline remains visible in the supplied evidence."],
        "lynch": ["Per-share growth remains directionally supportive in the supplied evidence."],
    }
    missing_data = {
        "graham": [],
        "buffett": [],
        "fisher": [
            "Free cash flow is unavailable in the supplied financial sections.",
            "Capex is unavailable in the supplied financial sections.",
        ],
        "munger": [],
        "lynch": [
            "Free cash flow is unavailable in the supplied financial sections.",
            "Capex is unavailable in the supplied financial sections.",
        ],
    }
    financial_red_flags = red_flags if red_flags is not None else ["Comparability remains affected by share-count events."]
    key_concerns = concerns if concerns is not None else [
        "Evidence is not complete enough for maximum confidence.",
        "Financial basis still needs to be interpreted conservatively from the supplied sections.",
    ]
    return {
        "financial_metrics_used": metrics if metrics is not None else default_metrics[doctrine_id],
        "financial_red_flags": financial_red_flags,
        "financial_positive_signals": key_strengths[doctrine_id],
        "financial_missing_data": missing_data[doctrine_id],
        "financial_interpretation_limits": [
            "Only supplied PCIM metrics were used; no new ratios were calculated.",
            "Financial basis was interpreted conservatively from the supplied sections.",
        ],
        "financial_assessment": {
            "financials_used": True,
            "basis_used": "consolidated",
            "key_financial_strengths": key_strengths[doctrine_id],
            "key_financial_concerns": key_concerns,
            "financial_red_flags": financial_red_flags,
            "missing_financial_data": missing_data[doctrine_id],
            "financial_interpretation_limits": [
                "Only supplied PCIM metrics were used; no new ratios were calculated.",
                "Financial basis was interpreted conservatively from the supplied sections.",
            ],
        },
        "financial_sections_consumed": financial_sections[doctrine_id],
        "financial_warnings_carried_forward": [],
    }


def test_panel_runner_loads_selected_doctrine_and_generates_llm_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="graham", rating="strong"))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")

    payload = json.loads(written["graham_analysis.json"].read_text())
    assert payload["doctrine_id"] == "graham"
    assert payload["analysis_mode"] == "llm_reasoning_v1"
    assert payload["rating"] == "strong"
    assert payload["user_facing_brief"]["title"] == BRIEF_TITLES["graham"]
    assert fake_llm.calls[0]["response_schema"] == {"type": "object"}
    assert fake_llm.calls[0]["temperature"] == 0.0


def test_panel_runner_passes_only_declared_pcim_sections_into_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="graham"))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    runner.run(analyst="graham")

    prompt = fake_llm.calls[0]["prompt"]
    assert '"financial_strength_inputs"' in prompt
    assert '"governance_and_incentive_inputs"' in prompt
    assert '"risk_inputs"' in prompt
    assert '"capital_allocation_inputs"' in prompt
    assert '"multi_year_inputs"' in prompt
    assert '"business_understanding"' not in prompt
    assert "Allowed supporting_pcim_sections:" in prompt
    assert '"financial_strength_inputs"' in prompt


@pytest.mark.parametrize(
    ("analyst", "expected_sections"),
    [
        ("graham", ['"multi_year_inputs"', '"financial_strength_inputs"']),
        ("buffett", ['"multi_year_inputs"', '"management_quality_inputs"']),
        ("fisher", ['"multi_year_inputs"', '"growth_execution_inputs"']),
        ("munger", ['"multi_year_inputs"', '"governance_and_incentive_inputs"']),
        ("lynch", ['"multi_year_inputs"', '"simplicity_and_story_inputs"']),
    ],
)
def test_declared_analysts_receive_multi_year_inputs_in_prompt(tmp_path, monkeypatch, analyst, expected_sections):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id=analyst))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    runner.run(analyst=analyst)

    prompt = fake_llm.calls[0]["prompt"]
    for section in expected_sections:
        assert section in prompt
    assert '"years_covered"' in prompt
    assert '"limitations"' in prompt
    assert "Do not treat dividends, related-party advances, or governance ambiguity as automatic condemnation without context" in prompt


def test_compact_prompt_pack_removes_source_chunk_and_preserves_evidence_ids(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_large_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="munger", rating="mixed", evidence_ids=["ev_risk_0", "ev_risk_1"]))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="munger")
    payload = json.loads(written["munger_analysis.json"].read_text())
    prompt = fake_llm.calls[0]["prompt"]

    assert "source_chunk" not in prompt
    assert "evidence_references" not in prompt
    assert "ev_risk_0" in prompt
    assert payload["evidence_ids"] == ["ev_risk_0", "ev_risk_1"]
    assert panel_runner.COMPACTION_REASONING_LIMIT in payload["reasoning_limits"]


def test_multi_year_prompt_pack_preserves_evidence_ids_and_has_no_source_chunk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    pcim = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json").read_text())

    prompt, compact_pcim, _stats, _limits, _compacted, _budget_report = panel_runner._build_compact_prompt(
        doctrine=panel_runner.InvestorDoctrineRegistry(Path(panel_runner.__file__).resolve().parent / "doctrines").get("graham"),
        company="acme",
        pcim_path=tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json",
        pcim=pcim,
        sections=["financial_strength_inputs", "risk_inputs", "capital_allocation_inputs", "multi_year_inputs", "evidence_map", "uncertainty_missing_data"],
    )

    assert "source_chunk" not in prompt
    assert "ev_my_risk_1" in prompt
    assert compact_pcim["multi_year_inputs"]["limitations"]


def test_large_pcim_prompt_stays_under_budget_and_uses_compact_view(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_large_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="munger", rating="mixed", evidence_ids=["ev_risk_0", "ev_inc_0"]))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    runner.run(analyst="munger")

    prompt = fake_llm.calls[0]["prompt"]
    manifest = json.loads((tmp_path / "companies" / "acme" / "company_memory" / "investor_panel" / "investor_panel_llm_call_manifest.json").read_text(encoding="utf-8"))
    entry = manifest["entries"][0]

    assert len(prompt) <= panel_runner.DEFAULT_MAX_TOTAL_PROMPT_CHARS
    assert entry["analyst"] == "munger"
    assert entry["truncation_applied"] is True
    assert entry["estimated_prompt_tokens"] <= panel_runner.DEFAULT_TOTAL_PROMPT_BUDGET_TOKENS
    assert entry["prompt_tokens_after"] <= entry["token_budget"]
    assert entry["pack_tokens_after"] <= entry["token_budget"]
    assert entry["pack_tokens_after"] <= panel_runner.DEFAULT_COMPACT_INPUT_PACK_BUDGET_TOKENS
    assert entry["budget_status"] in {"pass", "pass_with_warning"}
    assert entry["raw_largest_sections"]
    assert entry["compacted_largest_sections"]
    assert entry["sections_requested"]
    assert entry["sections_included"]
    assert entry["dropped_items_count"] >= 0
    assert "Selected compact PCIM sections:" in prompt


def test_financial_truth_compaction_prioritizes_latest_fiscal_year():
    payload = {
        "usable_current_metrics": [
            {
                "metric_id": f"revenue:{year}",
                "metric_name": "revenue",
                "fiscal_year": year,
                "value_crore": value,
                "basis": "consolidated",
                "confidence": "high",
            }
            for year, value in (("fy22", 100), ("fy23", 120), ("fy24", 140), ("fy25", 170), ("fy26", 210))
        ]
    }

    compacted = panel_runner.compact_financial_truth_for_analyst(
        payload,
        "buffett",
        token_budget=1000,
    )

    assert [item["period"] for item in compacted["top_usable_metrics"]] == [
        "fy26",
        "fy25",
        "fy24",
        "fy23",
        "fy22",
    ]
    assert compacted["top_usable_metrics"][0]["value"] == 210


def test_metric_value_extraction_uses_latest_series_point():
    value, unit = panel_runner._extract_metric_value(
        {
            "unit": "₹ crore",
            "series": [
                {"year": "fy22", "value": 100},
                {"year": "fy26", "value": 210},
                {"year": "fy24", "value": 140},
            ],
        }
    )

    assert value == 210
    assert unit == "₹ crore"


def test_financial_prompt_compaction_prioritizes_recent_year_buckets():
    prioritized = panel_runner._prioritize_recent_financial_items(
        {
            "by_year": [
                {"year": "fy22", "metrics": [{"period": "fy22", "value": 100}]},
                {"year": "fy26", "metrics": [{"period": "fy26", "value": 210}]},
                {"year": "fy24", "metrics": [{"period": "fy24", "value": 140}]},
            ]
        }
    )

    assert [item["year"] for item in prioritized["by_year"]] == ["fy26", "fy24", "fy22"]


def test_large_financial_truth_inputs_are_compacted_but_not_dropped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["financial_truth_inputs"] = {
        "usable_current_metrics": [
            {
                "metric_id": f"metric_{idx}",
                "metric_name": f"Very long metric name {idx} " * 8,
                "fiscal_year": "fy25",
                "value": idx,
                "basis": "consolidated",
                "confidence": "medium",
                "notes": [("Long note " * 40).strip()],
                "warnings": [("Long warning " * 30).strip()],
            }
            for idx in range(40)
        ],
        "usable_derived_metrics": [
            {
                "metric_id": f"derived_{idx}",
                "metric_name": f"Derived metric {idx} " * 8,
                "fiscal_year": "fy25",
                "value": idx,
                "basis": "consolidated",
                "confidence": "medium",
                "notes": [("Derived note " * 40).strip()],
            }
            for idx in range(20)
        ],
        "financial_warnings_allowed_downstream": [("Allowed warning " * 20).strip() for _ in range(12)],
        "financial_warnings_blocked_downstream": [
            {"original_warning": "free cash flow missing", "normalized_warning": ("Blocked warning " * 20).strip()}
            for _ in range(12)
        ],
        "investor_financial_questions": [("Question " * 25).strip() for _ in range(10)],
        "source_provenance": [("company_memory/financials/source_" + str(i) + ".json") for i in range(20)],
        "financial_panel_status": "warning",
        "financial_panel_status_reason": ("Status reason " * 20).strip(),
    }
    pcim_path.write_text(json.dumps(pcim), encoding="utf-8")

    fake_llm = FakeLLM(_llm_output(doctrine_id="graham", rating="mixed", evidence_ids=["ev_fin_1"]))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)
    runner = InvestorPanelRunner(company="acme")
    runner.run(analyst="graham")

    prompt = fake_llm.calls[0]["prompt"]
    diagnostics = json.loads(
        (tmp_path / "companies" / "acme" / "company_memory" / "investor_panel" / "prompt_budget_diagnostics_graham.json").read_text(encoding="utf-8")
    )

    assert '"financial_truth_inputs"' in prompt
    assert '"top_usable_metrics"' in prompt
    assert diagnostics["compacted_section_tokens"]["financial_truth_inputs"] > 0
    assert diagnostics["compacted_section_tokens"]["financial_truth_inputs"] < diagnostics["raw_section_tokens"]["financial_truth_inputs"]
    assert diagnostics["financial_truth_tokens"] <= panel_runner.DEFAULT_FINANCIAL_TRUTH_PACK_BUDGET_TOKENS


def test_prompt_budget_diagnostics_record_dropped_sections_and_emergency_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INVESTOR_PANEL_MAX_PROMPT_CHARS", "2000")
    _write_large_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="munger", rating="mixed", evidence_ids=["ev_cap_1"]))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    runner.run(analyst="munger")

    diagnostics = json.loads(
        (tmp_path / "companies" / "acme" / "company_memory" / "investor_panel" / "prompt_budget_diagnostics_munger.json").read_text(encoding="utf-8")
    )

    assert diagnostics["sections_requested"]
    assert diagnostics["included_sections"]
    assert diagnostics["excluded_sections"] or diagnostics["sections_dropped_due_budget"]
    assert diagnostics["shrink_passes_applied"] >= 1
    assert "budget_status" in diagnostics
    assert "token_usage_by_budget_class" in diagnostics
    assert diagnostics["compact_input_pack_budget_tokens"] == panel_runner.DEFAULT_COMPACT_INPUT_PACK_BUDGET_TOKENS


def test_prompt_budget_defaults_use_new_token_architecture():
    limits = panel_runner._prompt_compaction_limits()

    assert limits["total_prompt_budget_tokens"] == 9000
    assert limits["hard_max_prompt_tokens"] == 10000
    assert limits["compact_input_pack_budget_tokens"] == 4200
    assert limits["financial_truth_pack_budget_tokens"] == 900
    assert limits["evidence_pack_budget_tokens"] == 500
    assert limits["doctrine_context_budget_tokens"] == 2200


def test_panel_runner_never_accesses_raw_documents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    forbidden_root = tmp_path / "companies" / "acme" / "fy25" / "raw"
    forbidden_root.mkdir(parents=True, exist_ok=True)
    (forbidden_root / "annual_report.txt").write_text("should not be read", encoding="utf-8")
    fake_llm = FakeLLM(_llm_output(doctrine_id="lynch"))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="lynch")
    payload = json.loads(written["lynch_analysis.json"].read_text())

    assert payload["pcim_source"].endswith("pcim_v1.json")
    assert "raw" not in payload["pcim_source"]
    assert "annual_report.txt" not in fake_llm.calls[0]["prompt"]


def test_panel_runner_fails_fast_if_pcim_contains_source_chunk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["source_chunk"] = "raw leaked chunk"
    pcim_path.write_text(json.dumps(pcim), encoding="utf-8")

    runner = InvestorPanelRunner(company="acme")
    with pytest.raises(ValueError, match="PCIM must not contain source_chunk"):
        runner.run(analyst="graham")


def test_missing_pcim_sections_are_reflected_as_uncertainty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme", missing_sections=["risk_inputs", "financial_strength_inputs"])
    fake_llm = FakeLLM(_llm_output(doctrine_id="graham", rating="insufficient_evidence"))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    payload = json.loads(written["graham_analysis.json"].read_text())

    assert payload["rating"] == "insufficient_evidence"
    prompt = fake_llm.calls[0]["prompt"]
    assert "risk_inputs" in prompt
    assert "financial_strength_inputs" in prompt
    assert '"uncertainty_missing_data"' in prompt


def test_prompt_includes_missing_evidence_discipline_for_graham(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="graham", rating="mixed"))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    runner.run(analyst="graham")

    prompt = fake_llm.calls[0]["prompt"]
    assert "Do not treat dividends as a red flag by default" in prompt
    assert "If dividend or distribution evidence lacks cash-flow and leverage context" in prompt


def test_rating_is_taken_from_llm_output_not_section_availability(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="graham", rating="weak"))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    payload = json.loads(written["graham_analysis.json"].read_text())

    assert payload["rating"] == "weak"


@pytest.mark.parametrize(
    ("rating", "expected"),
    [
        ("insufficient evidence", "insufficient_evidence"),
        ("insufficient-evidence", "insufficient_evidence"),
        ("not enough evidence", "insufficient_evidence"),
        ("inconclusive", "insufficient_evidence"),
        ("neutral", "mixed"),
        ("cautious", "mixed"),
        ("positive", "strong"),
        ("negative", "weak"),
    ],
)
def test_rating_variants_are_normalized(tmp_path, monkeypatch, rating, expected):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="graham", rating=rating))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    payload = json.loads(written["graham_analysis.json"].read_text())
    diagnostics = json.loads(written["graham_analysis_diagnostics.json"].read_text())

    assert payload["rating"] == expected
    assert any("rating was normalized" in warning for warning in diagnostics.get("schema_warnings", []))


def test_invalid_rating_still_fails_after_normalization_attempt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="graham", rating="maybe"))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    with pytest.raises(ValueError, match="rating must be one of strong, mixed, weak, insufficient_evidence"):
        runner.run(analyst="graham")


def test_evidence_ids_are_preserved_and_filtered_to_allowed_ids(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(
        json.dumps(
            {
                "assessment": {
                    "financial_strength_assessment": "Adequate evidence.",
                    "integrity_assessment": "No obvious integrity issue.",
                    "downside_protection_assessment": "Concentration remains a risk.",
                    "key_red_flags": "Evidence quality is still limited.",
                },
                "rating": "mixed",
                "key_findings": [{"finding": "Useful evidence exists.", "evidence_ids": ["ev_cap_1", "not_allowed"]}],
                "red_flags": [{"flag": "Concentration risk", "severity": "medium", "evidence_ids": ["ev_risk_1"]}],
                "open_uncertainties": [{"uncertainty": "Multi-year data is limited.", "evidence_ids": ["not_allowed_2"]}],
                **_financial_payload("graham"),
                "evidence_ids": ["ev_cap_1", "ev_risk_1", "not_allowed"],
                "supporting_pcim_sections": [
                    "financial_strength_inputs",
                    "risk_inputs",
                    "capital_allocation_inputs",
                    "evidence_map",
                    "uncertainty_missing_data",
                ],
                "reasoning_limits": ["PCIM-only judgment."],
                "user_facing_brief": _brief_payload("graham"),
            }
        )
    )
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    payload, diagnostics = _read_saved_outputs(written, "graham")

    assert "ev_cap_1" in payload["evidence_ids"]
    assert "ev_risk_1" in payload["evidence_ids"]
    assert diagnostics["evidence_id_normalization"]["applied"] is True
    assert diagnostics["evidence_id_normalization"]["unresolved_ids"] == [
        "not_allowed",
        "not_allowed_2",
    ]
    removed = diagnostics["evidence_id_normalization"]["removed_invalid_ids"]
    assert {"invalid_id": "not_allowed", "path": "$.evidence_ids", "reason": "unknown_evidence_id"} in removed
    assert "not_allowed" not in payload["evidence_ids"]
    assert all(
        "not_allowed" not in (item.get("evidence_ids", []) if isinstance(item, dict) else [])
        for item in payload["key_findings"]
    )
    assert all(
        "not_allowed" not in (item.get("evidence_ids", []) if isinstance(item, dict) else [])
        for item in payload["open_uncertainties"]
    )
    assert payload["evidence_grounding_status"] == "warning"


def test_section_name_evidence_ids_are_removed_before_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(
        json.dumps(
            {
                "assessment": {
                    "financial_strength_assessment": "Adequate evidence.",
                    "integrity_assessment": "No obvious integrity issue.",
                    "downside_protection_assessment": "Concentration remains a risk.",
                    "key_red_flags": "Evidence quality is still limited.",
                },
                "rating": "mixed",
                "key_findings": [{"finding": "Useful evidence exists.", "evidence_ids": ["working_capital_inputs", "ev_cap_1"]}],
                "red_flags": [{"flag": "Concentration risk", "severity": "medium", "evidence_ids": ["risk_inputs", "ev_risk_1"]}],
                "open_uncertainties": [{"uncertainty": "Multi-year data is limited.", "evidence_ids": ["multi_year_inputs"]}],
                **_financial_payload("graham"),
                "evidence_ids": ["working_capital_inputs", "ev_cap_1", "risk_inputs"],
                "supporting_pcim_sections": [
                    "financial_strength_inputs",
                    "risk_inputs",
                    "capital_allocation_inputs",
                    "evidence_map",
                    "uncertainty_missing_data",
                ],
                "reasoning_limits": ["PCIM-only judgment."],
                "user_facing_brief": _brief_payload("graham"),
            }
        )
    )
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    payload, diagnostics = _read_saved_outputs(written, "graham")

    assert "working_capital_inputs" not in payload["evidence_ids"]
    assert "risk_inputs" not in payload["evidence_ids"]
    assert "multi_year_inputs" not in json.dumps(payload["evidence_ids"])
    removed = diagnostics["evidence_id_normalization"]["removed_invalid_ids"]
    assert any(item["invalid_id"] == "working_capital_inputs" for item in removed)
    assert any(
        "section-name references instead of evidence IDs" in item
        for item in diagnostics["schema_warnings"]
    )


def test_buffett_style_section_name_evidence_ids_are_removed_before_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(
        json.dumps(
            {
                "assessment": {
                    "business_quality_assessment": "Adequate evidence.",
                    "moat_assessment": "Some durability evidence exists.",
                    "capital_allocation_assessment": "Capital allocation needs more history.",
                    "management_rationality_assessment": "Management rationality needs more evidence.",
                    "key_red_flags": "Evidence quality is still limited.",
                },
                "rating": "mixed",
                "key_findings": [
                    {
                        "finding": "Governance and financial evidence are relevant.",
                        "evidence_ids": ["governance_and_incentive_inputs", "ev_cap_1"],
                    }
                ],
                "red_flags": [
                    {
                        "flag": "Cash conversion evidence is incomplete.",
                        "severity": "medium",
                        "evidence_ids": ["cash_conversion_inputs", "ev_risk_1"],
                    }
                ],
                "open_uncertainties": [
                    {
                        "uncertainty": "Financial fundamentals remain incomplete.",
                        "evidence_ids": ["financial_fundamentals_inputs", "per_share_inputs"],
                    }
                ],
                **_financial_payload("buffett"),
                "evidence_ids": [
                    "governance_and_incentive_inputs",
                    "financial_fundamentals_inputs",
                    "cash_conversion_inputs",
                    "return_on_capital_inputs",
                    "per_share_inputs",
                    "ev_cap_1",
                    "ev_risk_1",
                ],
                "supporting_pcim_sections": [
                    "business_understanding",
                    "moat_inputs",
                    "capital_allocation_inputs",
                    "governance_and_incentive_inputs",
                    "financial_fundamentals_inputs",
                    "cash_conversion_inputs",
                    "return_on_capital_inputs",
                    "per_share_inputs",
                    "uncertainty_missing_data",
                ],
                "reasoning_limits": ["PCIM-only judgment."],
                "user_facing_brief": {
                    **_brief_payload("buffett"),
                    "evidence_ids": ["governance_and_incentive_inputs"],
                },
            }
        )
    )
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="buffett")
    payload, diagnostics = _read_saved_outputs(written, "buffett")
    serialized_active_ids = json.dumps(
        {
            "top_level": payload["evidence_ids"],
            "key_findings": payload["key_findings"],
            "red_flags": payload["red_flags"],
            "open_uncertainties": payload["open_uncertainties"],
            "user_facing_brief": payload["user_facing_brief"],
        },
        ensure_ascii=False,
    )

    for section_name in (
        "governance_and_incentive_inputs",
        "financial_fundamentals_inputs",
        "cash_conversion_inputs",
        "return_on_capital_inputs",
        "per_share_inputs",
    ):
        assert section_name not in serialized_active_ids
    assert "ev_cap_1" in payload["evidence_ids"]
    assert "ev_risk_1" in payload["evidence_ids"]
    assert payload["evidence_grounding_status"] == "warning"
    removed = diagnostics["evidence_id_normalization"]["removed_invalid_ids"]
    assert any(item["invalid_id"] == "governance_and_incentive_inputs" for item in removed)


def test_alias_evidence_ids_are_normalized_to_canonical_ids(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text())
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["category"] = "Liquidity risk"
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["evidence_ids"] = [
        "ev_fy25_company_intelligence_json_risk_00001"
    ]
    pcim["evidence_map"]["risk_inputs"] = ["ev_fy25_company_intelligence_json_risk_00001"]
    pcim_path.write_text(json.dumps(pcim), encoding="utf-8")

    fake_llm = FakeLLM(
        json.dumps(
            {
                "assessment": {
                    "financial_strength_assessment": "Liquidity risk remains visible.",
                    "integrity_assessment": "No obvious integrity issue.",
                    "downside_protection_assessment": "Downside protection remains mixed.",
                    "key_red_flags": "Liquidity remains the main red flag.",
                },
                "rating": "mixed",
                "key_findings": [
                    {
                        "finding": "Liquidity remains visible.",
                        "evidence_ids": ["ev_fy25_company_intelligence_risk_00001"],
                    }
                ],
                "red_flags": [],
                "open_uncertainties": [],
                **_financial_payload("graham", concerns=["Liquidity remains the main red flag."], red_flags=["Liquidity remains the main red flag."], metrics=["total_debt"]),
                "evidence_ids": ["ev_fy25_company_intelligence_risk_00001"],
                "supporting_pcim_sections": [
                    "financial_strength_inputs",
                    "risk_inputs",
                    "capital_allocation_inputs",
                    "evidence_map",
                    "uncertainty_missing_data",
                ],
                "reasoning_limits": ["PCIM-only judgment."],
                "user_facing_brief": _brief_payload("graham"),
            }
        )
    )
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    payload, diagnostics = _read_saved_outputs(written, "graham")

    assert "ev_fy25_company_intelligence_json_risk_00001" in payload["evidence_ids"]
    assert "ev_fy25_company_intelligence_risk_00001" not in payload["evidence_ids"]
    assert diagnostics["evidence_id_normalization"]["applied"] is True
    assert diagnostics["evidence_id_normalization"]["replacements"] == [
        {
            "original_id": "ev_fy25_company_intelligence_risk_00001",
            "canonical_id": "ev_fy25_company_intelligence_json_risk_00001",
        }
    ]
    assert payload["evidence_grounding_status"] == "pass"
    assert not any(
        warning.get("evidence_id") == "ev_fy25_company_intelligence_capalloc_00002"
        for warning in diagnostics["evidence_grounding_warnings"]
        if isinstance(warning, dict)
    )


def test_noncanonical_capalloc_ids_are_normalized_before_save(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text())
    pcim["capital_allocation_inputs"]["capital_allocation_by_year"][0]["items"][0]["category"] = "capex"
    pcim["capital_allocation_inputs"]["capital_allocation_by_year"][0]["items"][0]["evidence_ids"] = [
        "ev_fy25_company_intelligence_json_capalloc_00002"
    ]
    pcim["evidence_map"]["capital_allocation_inputs"] = ["ev_fy25_company_intelligence_json_capalloc_00002"]
    pcim_path.write_text(json.dumps(pcim), encoding="utf-8")

    fake_llm = FakeLLM(
        json.dumps(
            {
                "assessment": {
                    "financial_strength_assessment": "Capex remains visible through ev_fy25_company_intelligence_capalloc_00002.",
                    "integrity_assessment": "No obvious integrity issue.",
                    "downside_protection_assessment": "Downside protection remains mixed.",
                    "key_red_flags": "Capex intensity remains a watch item.",
                },
                "rating": "mixed",
                "key_findings": [
                    {
                        "finding": "Capex remains visible.",
                        "evidence_ids": ["ev_fy25_company_intelligence_capalloc_00002"],
                    }
                ],
                "red_flags": [],
                "open_uncertainties": [],
                **_financial_payload("graham", concerns=["Capex intensity remains a watch item."], red_flags=["Capex intensity remains a watch item."], metrics=["capex"]),
                "evidence_ids": ["ev_fy25_company_intelligence_capalloc_00002"],
                "supporting_pcim_sections": [
                    "financial_strength_inputs",
                    "risk_inputs",
                    "capital_allocation_inputs",
                    "evidence_map",
                    "uncertainty_missing_data",
                ],
                "reasoning_limits": ["PCIM-only judgment."],
                "user_facing_brief": _brief_payload("graham"),
            }
        )
    )
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    payload, diagnostics = _read_saved_outputs(written, "graham")

    assert "ev_fy25_company_intelligence_json_capalloc_00002" in payload["evidence_ids"]
    assert "ev_fy25_company_intelligence_json_capalloc_00002" not in payload["assessment"]["financial_strength_assessment"]
    assert "supporting evidence" in payload["assessment"]["financial_strength_assessment"].lower()
    assert not any(
        warning.get("evidence_id") == "ev_fy25_company_intelligence_capalloc_00002"
        for warning in diagnostics["evidence_grounding_warnings"]
        if isinstance(warning, dict)
    )


def test_unresolved_ids_are_preserved_and_reported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(
        json.dumps(
            {
                "assessment": {
                    "financial_strength_assessment": "Evidence remains partial.",
                    "integrity_assessment": "No obvious integrity issue.",
                    "downside_protection_assessment": "Downside protection remains mixed.",
                    "key_red_flags": "Evidence quality is still limited.",
                },
                "rating": "mixed",
                "key_findings": [{"finding": "Useful evidence exists.", "evidence_ids": ["ev_missing_alias"]}],
                "red_flags": [],
                "open_uncertainties": [],
                **_financial_payload("graham"),
                "evidence_ids": ["ev_missing_alias"],
                "supporting_pcim_sections": [
                    "financial_strength_inputs",
                    "risk_inputs",
                    "capital_allocation_inputs",
                    "evidence_map",
                    "uncertainty_missing_data",
                ],
                "reasoning_limits": ["PCIM-only judgment."],
                "user_facing_brief": _brief_payload("graham"),
            }
        )
    )
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    payload, diagnostics = _read_saved_outputs(written, "graham")

    assert "ev_missing_alias" not in payload["evidence_ids"]
    assert diagnostics["evidence_id_normalization"]["unresolved_ids"] == ["ev_missing_alias"]
    assert diagnostics["evidence_id_normalization"]["removed_invalid_ids"] == [
        {
            "path": "$.key_findings.evidence_ids",
            "invalid_id": "ev_missing_alias",
            "reason": "unknown_evidence_id",
        },
        {
            "path": "$.evidence_ids",
            "invalid_id": "ev_missing_alias",
            "reason": "unknown_evidence_id",
        },
    ]
    assert payload["evidence_grounding_status"] == "warning"


def test_unresolved_ids_cannot_coexist_with_pass_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(
        json.dumps(
            {
                "assessment": {
                    "business_simplicity_assessment": "The business can be explained simply enough from PCIM.",
                    "story_vs_evidence_assessment": "The story is broadly supported by the evidence.",
                    "growth_category_assessment": "Growth appears practical rather than hype-led.",
                    "hype_and_mismatch_checks": "No major hype mismatch dominates the current view.",
                },
                "rating": "mixed",
                "key_findings": [{"finding": "Useful evidence exists.", "evidence_ids": ["ev_missing_alias"]}],
                "red_flags": [],
                "open_uncertainties": [],
                **_financial_payload("lynch", metrics=["revenue", "eps_basic"]),
                "evidence_ids": ["ev_missing_alias"],
                "historical_context_used": True,
                "years_considered": ["fy24", "fy25"],
                "supporting_pcim_sections": [
                    "business_understanding",
                    "management_quality_inputs",
                    "growth_execution_inputs",
                    "simplicity_and_story_inputs",
                    "multi_year_inputs",
                    "story_vs_numbers_inputs",
                    "evidence_map",
                    "uncertainty_missing_data",
                ],
                "reasoning_limits": ["PCIM-only judgment."],
                "user_facing_brief": _brief_payload("lynch"),
            }
        )
    )
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="lynch")
    payload, diagnostics = _read_saved_outputs(written, "lynch")

    assert diagnostics["evidence_id_normalization"]["unresolved_ids"] == ["ev_missing_alias"]
    assert payload["evidence_grounding_status"] in {"warning", "fail"}


def test_invalid_supporting_sections_are_safely_repaired(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(
        json.dumps(
            {
                "assessment": {
                    "incentive_alignment_assessment": "Incentive evidence is directionally positive.",
                    "governance_sanity_assessment": "Governance signals appear sane but not exhaustive.",
                    "avoidable_risk_assessment": "Some avoidable operational risk remains.",
                    "complexity_and_stupidity_checks": "The business is manageable but some complexity remains.",
                },
                "rating": "mixed",
                "key_findings": [{"finding": "Useful evidence exists.", "evidence_ids": ["ev_inc_1"]}],
                "red_flags": [{"flag": "Some risk remains.", "severity": "medium", "evidence_ids": ["ev_risk_1"]}],
                "open_uncertainties": [{"uncertainty": "Multi-year data is limited.", "evidence_ids": []}],
                **_financial_payload("munger"),
                "evidence_ids": ["ev_inc_1", "ev_risk_1"],
                "supporting_pcim_sections": [
                    "governance_and_incentive_inputs",
                    "risk_inputs",
                    "promise_tracker",
                ],
                "reasoning_limits": ["PCIM-only judgment."],
                "user_facing_brief": _brief_payload("munger"),
            }
        )
    )
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="munger")
    payload = json.loads(written["munger_analysis.json"].read_text())

    assert payload["supporting_pcim_sections"] == ["governance_and_incentive_inputs", "risk_inputs"]
    assert any("promise_tracker" in item for item in payload["reasoning_limits"])


def test_munger_governance_routing_failure_is_repaired_deterministically_before_retry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["value"] = "Foreign exchange market risk"
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["category"] = "Foreign exchange exposure"
    pcim_path.write_text(json.dumps(pcim), encoding="utf-8")

    bad_payload = json.loads(_llm_output(doctrine_id="munger", evidence_ids=["ev_risk_1"]))
    bad_payload["assessment"]["governance_sanity_assessment"] = (
        "Governance quality looks sound because market-risk disclosure is present."
    )
    bad_payload["key_findings"] = [
        {
            "finding": "Governance quality looks sound because market-risk disclosure is present.",
            "evidence_ids": ["ev_risk_1"],
        }
    ]
    bad_payload["evidence_ids"] = ["ev_risk_1"]

    fake_llm = SequencedFakeLLM([json.dumps(bad_payload)])
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    written = InvestorPanelRunner(company="acme").run(analyst="munger")
    saved, diagnostics = _read_saved_outputs(written, "munger")

    assert len(fake_llm.calls) == 1
    assert saved["evidence_grounding_status"] in {"pass", "warning"}
    assert diagnostics["evidence_routing_diagnostics"]["removed_misrouted_evidence"]
    assert "ev_risk_1" not in json.dumps(saved["key_findings"], ensure_ascii=False)
    assert not any(
        "market-risk evidence should not support governance/incentive claim" in str(warning)
        for warning in diagnostics["evidence_grounding_warnings"]
    )


def test_munger_governance_routing_diagnostics_records_converted_limitation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["value"] = "Foreign exchange market risk"
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["category"] = "Foreign exchange exposure"
    pcim_path.write_text(json.dumps(pcim), encoding="utf-8")

    bad_payload = json.loads(_llm_output(doctrine_id="munger", evidence_ids=["ev_risk_1"]))
    bad_payload["assessment"]["governance_sanity_assessment"] = (
        "Governance quality looks sound because market-risk disclosure is present."
    )
    bad_payload["key_findings"] = [
        {
            "finding": "Governance quality looks sound because market-risk disclosure is present.",
            "evidence_ids": ["ev_risk_1"],
        }
    ]
    bad_payload["evidence_ids"] = ["ev_risk_1"]

    pcim["governance_and_incentive_inputs"] = {}
    pcim["ownership_inputs"] = {}
    pcim["capital_allocation_inputs"] = {}
    pcim["management_quality_inputs"] = {}
    pcim["corporate_action_inputs"] = {}
    for section in (
        "governance_and_incentive_inputs",
        "ownership_inputs",
        "capital_allocation_inputs",
        "management_quality_inputs",
        "corporate_action_inputs",
    ):
        pcim["evidence_map"][section] = []
    pcim_path.write_text(json.dumps(pcim), encoding="utf-8")

    fake_llm = SequencedFakeLLM([json.dumps(bad_payload)])
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    written = InvestorPanelRunner(company="acme").run(analyst="munger")
    saved, diagnostics = _read_saved_outputs(written, "munger")

    assert len(fake_llm.calls) == 1
    assert diagnostics["evidence_routing_diagnostics"]["removed_misrouted_evidence"]
    assert "governance" in saved["assessment"]["governance_sanity_assessment"].lower()
    assert "incomplete" in saved["assessment"]["governance_sanity_assessment"].lower()
    assert not any(
        "market-risk evidence should not support governance/incentive claim" in str(warning)
        for warning in diagnostics["evidence_grounding_warnings"]
    )


def test_market_risk_routing_diagnostics_record_accepted_market_risk_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["category"] = "Market risk"
    pcim["risk_inputs"]["risk_by_year"][0]["items"][0]["value"] = (
        "Sensitivity to market-price movements remains visible."
    )
    pcim_path.write_text(json.dumps(pcim), encoding="utf-8")

    payload = json.loads(_llm_output(doctrine_id="graham", evidence_ids=["ev_risk_1"]))
    payload["key_findings"] = [
        {
            "finding": (
                "Risk disclosures explicitly note market risk (FX/interest) exposure in FY22, "
                "highlighting sensitivity to market-price movements."
            ),
            "evidence_ids": ["ev_risk_1"],
        }
    ]
    payload["red_flags"] = []
    payload["evidence_ids"] = ["ev_risk_1"]
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    written = InvestorPanelRunner(company="acme").run(analyst="graham")
    saved, diagnostics = _read_saved_outputs(written, "graham")

    assert saved["evidence_grounding_status"] in {"pass", "warning"}
    accepted = diagnostics["evidence_routing_diagnostics"]["accepted_market_risk_evidence"]
    assert accepted
    assert accepted[0]["claim_type"] == "market_risk"
    assert accepted[0]["evidence_id"] == "ev_risk_1"
    assert accepted[0]["routing_decision"] == "accepted_market_risk_evidence"


def test_supporting_sections_must_not_be_only_undeclared_sections(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(
        json.dumps(
            {
                "assessment": {
                    "incentive_alignment_assessment": "Incentive evidence is directionally positive.",
                    "governance_sanity_assessment": "Governance signals appear sane but not exhaustive.",
                    "avoidable_risk_assessment": "Some avoidable operational risk remains.",
                    "complexity_and_stupidity_checks": "The business is manageable but some complexity remains.",
                },
                "rating": "mixed",
                "key_findings": [{"finding": "Useful evidence exists.", "evidence_ids": ["ev_inc_1"]}],
                "red_flags": [{"flag": "Some risk remains.", "severity": "medium", "evidence_ids": ["ev_risk_1"]}],
                "open_uncertainties": [{"uncertainty": "Multi-year data is limited.", "evidence_ids": []}],
                **_financial_payload("munger"),
                "evidence_ids": ["ev_inc_1", "ev_risk_1"],
                "supporting_pcim_sections": ["promise_tracker"],
                "reasoning_limits": ["PCIM-only judgment."],
                "user_facing_brief": _brief_payload("munger"),
            }
        )
    )
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")

    with pytest.raises(ValueError, match="Invalid supporting_pcim_sections returned: \\['promise_tracker'\\]"):
        runner.run(analyst="munger")


def test_invalid_llm_json_fails_safely(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM("not json")
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")

    with pytest.raises(ValueError, match="Malformed JSON"):
        runner.run(analyst="graham")


def test_user_facing_brief_with_internal_jargon_is_repaired(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="graham"))
    original_assessment = dict(payload["assessment"])
    payload["user_facing_brief"]["bottom_line"] = "This PCIM view looks promising."
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    saved = json.loads(written["graham_analysis.json"].read_text())

    assert "pcim" not in json.dumps(saved["assessment"], ensure_ascii=False).lower()
    assert "PCIM" not in saved["user_facing_brief"]["bottom_line"]
    assert "available evidence" in saved["user_facing_brief"]["bottom_line"].lower()


def test_user_facing_brief_with_evidence_ids_is_repaired(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="graham"))
    payload["user_facing_brief"]["what_looks_good"] = ["Evidence looks strong ev_cap_1"]
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    saved = json.loads(written["graham_analysis.json"].read_text())

    assert "ev_" not in saved["user_facing_brief"]["what_looks_good"][0]
    assert "supporting evidence" in saved["user_facing_brief"]["what_looks_good"][0].lower()


def test_user_facing_brief_shape_is_normalized_before_validation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="buffett"))
    payload["user_facing_brief"]["what_looks_good"] = "The PCIM shows resilient demand."
    payload["user_facing_brief"]["what_needs_caution"] = None
    payload["user_facing_brief"].pop("what_is_missing")
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="buffett")
    saved = json.loads(written["buffett_analysis.json"].read_text())

    assert saved["user_facing_brief"]["what_looks_good"] == ["The available evidence shows resilient demand."]
    assert saved["user_facing_brief"]["what_needs_caution"] == []
    assert saved["user_facing_brief"]["what_is_missing"]


@pytest.mark.parametrize("analyst", ["graham", "buffett", "fisher", "munger", "lynch"])
def test_all_analysts_receive_canonical_brief_titles(tmp_path, monkeypatch, analyst):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id=analyst))
    payload["user_facing_brief"]["title"] = "Wrong title from llm"
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst=analyst)
    saved, diagnostics = _read_saved_outputs(written, analyst)

    assert saved["user_facing_brief"]["title"] == BRIEF_TITLES[analyst]
    assert any(
        item.get("field") == "user_facing_brief.title"
        and item.get("repair_reason") == "canonical_title_enforced"
        for item in diagnostics.get("brief_repair_diagnostics", [])
    )


def test_user_facing_brief_title_mismatch_is_overwritten(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="buffett"))
    payload["user_facing_brief"]["title"] = "Buffett says buy quality"
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="buffett")
    saved, diagnostics = _read_saved_outputs(written, "buffett")

    assert saved["user_facing_brief"]["title"] == BRIEF_TITLES["buffett"]
    assert any(
        item.get("field") == "user_facing_brief.title"
        and item.get("original_value") == "Buffett says buy quality"
        and item.get("repaired_value") == BRIEF_TITLES["buffett"]
        for item in diagnostics.get("brief_repair_diagnostics", [])
    )


def test_missing_user_facing_brief_uses_skeleton_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="graham"))
    payload.pop("user_facing_brief")
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    saved, diagnostics = _read_saved_outputs(written, "graham")

    assert saved["user_facing_brief"]["title"] == BRIEF_TITLES["graham"]
    assert saved["user_facing_brief"]["bottom_line"]
    assert any(
        "user_facing_brief was missing; deterministic skeleton defaults were retained." in item
        for item in diagnostics.get("schema_warnings", [])
    )


def test_user_facing_brief_string_is_finalized_into_canonical_object(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="buffett"))
    payload["user_facing_brief"] = "Strong business quality, but evidence remains incomplete."
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="buffett")
    saved, diagnostics = _read_saved_outputs(written, "buffett")

    assert saved["user_facing_brief"]["title"] == BRIEF_TITLES["buffett"]
    assert saved["user_facing_brief"]["bottom_line"] == "Strong business quality, but evidence remains incomplete."
    assert any(
        "user_facing_brief was returned as string and normalized into bottom_line." in item
        for item in diagnostics.get("schema_warnings", [])
    )


def test_unknown_user_facing_brief_fields_go_to_diagnostics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="buffett"))
    payload["user_facing_brief"]["mystery_field"] = "should not survive"
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="buffett")
    saved, diagnostics = _read_saved_outputs(written, "buffett")

    assert "mystery_field" not in saved["user_facing_brief"]
    assert any(
        "Unknown user_facing_brief fields were removed to diagnostics" in item
        for item in diagnostics.get("schema_warnings", [])
    )


def test_user_facing_brief_lengths_are_normalized_before_validation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="fisher"))
    original_assessment = dict(payload["assessment"])
    payload["user_facing_brief"]["what_looks_good"] = [
        "Growth looks credible. " + ("Additional detail that should be shortened safely " * 25)
    ]
    payload["user_facing_brief"]["bottom_line"] = (
        "Execution is promising but evidence remains partial. "
        + ("More disclosed proof would improve confidence " * 40)
    )
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="fisher")
    saved = json.loads(written["fisher_analysis.json"].read_text())

    assert saved["assessment"] == original_assessment
    assert len(saved["user_facing_brief"]["what_looks_good"][0]) <= 350
    assert len(saved["user_facing_brief"]["bottom_line"]) <= 900


def test_missing_required_brief_key_uses_skeleton_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="graham"))
    payload["user_facing_brief"].pop("bottom_line")
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    saved, diagnostics = _read_saved_outputs(written, "graham")

    assert saved["user_facing_brief"]["bottom_line"]
    assert any(
        "user_facing_brief canonical fields were finalized before validation." in item
        for item in diagnostics.get("schema_warnings", [])
    )


def test_user_facing_brief_validation_happens_after_finalization(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="buffett"))
    payload["user_facing_brief"]["title"] = "Bad title"
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    original_finalize = panel_runner.finalize_user_facing_brief_for_external_reader
    original_validate = panel_runner.validate_user_facing_brief
    calls = []

    def wrapped_finalize(analyst, brief, doctrine=None, diagnostics=None):
        calls.append(("finalize", analyst, isinstance(brief, dict)))
        return original_finalize(analyst, brief, doctrine=doctrine, diagnostics=diagnostics)

    def wrapped_validate(analyst, brief):
        calls.append(("validate", analyst, brief.get("title")))
        return original_validate(analyst, brief)

    monkeypatch.setattr(panel_runner, "finalize_user_facing_brief_for_external_reader", wrapped_finalize)
    monkeypatch.setattr(panel_runner, "validate_user_facing_brief", wrapped_validate)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="buffett")
    saved = json.loads(written["buffett_analysis.json"].read_text(encoding="utf-8"))

    assert saved["user_facing_brief"]["title"] == BRIEF_TITLES["buffett"]
    assert calls[0][0] == "finalize"
    assert calls[1] == ("validate", "buffett", BRIEF_TITLES["buffett"])


def test_collect_user_facing_brief_validation_issues_reports_multiple_terms():
    issues = panel_runner.collect_user_facing_brief_validation_issues(
        "fisher",
        {
            "title": BRIEF_TITLES["fisher"],
            "lens": "Valid investor-facing lens sentence with enough detail to pass the minimum length check.",
            "what_looks_good": ["The PCIM and evidence_ids support the growth story."],
            "what_needs_caution": ["business_understanding suggests a gap."],
            "what_is_missing": [],
            "bottom_line": "artifact and JSON language still leaked here.",
            "financial_lens": "Based on financial_growth_inputs, more proof is needed.",
        },
    )

    forbidden_terms = {item["forbidden_term"] for item in issues}
    assert "PCIM" in forbidden_terms
    assert "evidence_id" in forbidden_terms
    assert "business_understanding" in forbidden_terms
    assert "artifact" in forbidden_terms
    assert "JSON" in forbidden_terms


def test_external_reader_finalizer_rewrites_all_brief_fields():
    diagnostics = {}
    finalized = panel_runner.finalize_user_facing_brief_for_external_reader(
        "fisher",
        {
            "title": "Wrong",
            "lens": "Wrong lens",
            "what_looks_good": ["The PCIM supports execution."],
            "what_needs_caution": ["artifact and evidence_ids are messy."],
            "what_is_missing": ["business_understanding and working_capital_inputs are incomplete."],
            "bottom_line": "JSON output from the LLM references source_artifact fields.",
            "financial_lens": "financial_growth_inputs and per_share_inputs remain incomplete.",
        },
        diagnostics=diagnostics,
    )

    brief_blob = json.dumps(finalized, ensure_ascii=False).lower()
    assert "pcim" not in brief_blob
    assert "artifact" not in brief_blob
    assert ".json" not in brief_blob
    assert "evidence_id" not in brief_blob
    assert "business_understanding" not in brief_blob
    assert "financial_growth_inputs" not in brief_blob
    assert diagnostics["rewritten_fields"]


def test_active_analyst_fields_are_sanitized_for_external_reader():
    payload = {
        "assessment": {"management_rationality_assessment": "This is grounded in business_understanding and working_capital_inputs."},
        "key_findings": ["The PCIM supports execution."],
        "red_flags": ["artifact and JSON labels remain in the raw text."],
        "open_uncertainties": ["uncertainty_missing_data still blocks conviction."],
        "financial_red_flags": ["financial_growth_inputs remain incomplete."],
        "financial_missing_data": ["evidence_id is missing for one claim."],
        "financial_interpretation_limits": ["Prompt-level wording leaked from the LLM."],
        "financial_warnings_carried_forward": ["source_artifact details leaked."],
        "precise_missing_financial_data": [],
        "derived_not_explicitly_reported": [],
        "partial_financial_data": [],
        "unreliable_financial_data": [],
        "invalid_or_quarantined_financial_data": [],
        "trend_durability_limits": [],
        "financial_questions_for_investor": [],
        "reasoning_limits": ["business_understanding was explicitly cited."],
        "key_concerns": [],
        "key_questions": [],
        "evidence_gaps": [],
        "financial_assessment": {
            "key_financial_strengths": ["The PCIM shows resilience."],
            "key_financial_concerns": ["artifact missing."],
            "financial_red_flags": ["working_capital_inputs remain limited."],
            "missing_financial_data": ["source chunk leakage."],
            "financial_interpretation_limits": ["input pack phrasing leaked."],
            "financial_warnings_carried_forward": ["prompt wording leaked."],
        },
        "user_facing_brief": {
            "title": BRIEF_TITLES["graham"],
            "lens": "This lens looks for balance-sheet caution, financial resilience, and whether the downside appears protected when conditions get worse.",
            "what_looks_good": ["The PCIM supports resilience."],
            "what_needs_caution": [],
            "what_is_missing": [],
            "bottom_line": "artifact wording leaked.",
            "financial_lens": "financial_growth_inputs remain incomplete.",
        },
    }

    sanitized = panel_runner._sanitize_active_external_reader_fields(payload, {})
    sanitized_blob = json.dumps(sanitized, ensure_ascii=False).lower()

    for forbidden in ("pcim", "artifact", "json", "business_understanding", "working_capital_inputs", "source_artifact", "input pack", "prompt"):
        assert forbidden not in sanitized_blob


def test_boilerplate_grounding_claim_is_rewritten_to_limitation():
    rewritten = panel_runner.rewrite_text_for_external_reader(
        "Execution evidence is grounded in business_understanding and financial_growth_inputs.",
        field_path="assessment.execution_assessment",
    )

    assert "grounded in" not in rewritten.lower()
    assert "insufficient direct evidence" in rewritten.lower()


def test_user_facing_brief_with_recommendation_language_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="graham"))
    payload["user_facing_brief"]["bottom_line"] = "This looks like a buy."
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")

    with pytest.raises(ValueError, match='Invalid user_facing_brief for analyst graham: field "bottom_line" contains recommendation language'):
        runner.run(analyst="graham")


def test_user_facing_brief_with_too_many_items_is_capped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="graham"))
    payload["user_facing_brief"]["what_looks_good"] = [
        "one", "two", "three", "four", "five", "six",
    ]
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")

    written = runner.run(analyst="graham")
    saved = json.loads(written["graham_analysis.json"].read_text())

    assert len(saved["user_facing_brief"]["what_looks_good"]) == 5
    assert saved["user_facing_brief"]["what_looks_good"] == ["one.", "two.", "three.", "four.", "five."]


def test_dry_run_uses_deterministic_scaffold_and_does_not_overwrite_llm_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="graham", rating="mixed"))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    llm_path = written["graham_analysis.json"]
    llm_payload = json.loads(llm_path.read_text())

    monkeypatch.setenv("INVESTOR_PANEL_DRY_RUN", "1")
    dry_written = runner.run(analyst="graham")
    dry_path = dry_written["graham_analysis_dry_run.json"]
    dry_payload = json.loads(dry_path.read_text())

    assert llm_path.exists()
    assert json.loads(llm_path.read_text()) == llm_payload
    assert dry_payload["analysis_mode"] == "deterministic_scaffold"
    assert dry_path != llm_path


def test_output_schema_is_valid_for_llm_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="munger", rating="mixed", evidence_ids=["ev_inc_1", "ev_risk_1"]))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="munger")
    payload, diagnostics = _read_saved_outputs(written, "munger")

    expected_clean_keys = {
        "doctrine_id",
        "company",
        "pcim_version",
        "pcim_source",
        "analysis_mode",
        "sections_consumed",
        "assessment",
        "rating",
        "key_findings",
        "red_flags",
        "open_uncertainties",
        "financial_metrics_used",
        "financial_red_flags",
        "financial_positive_signals",
        "financial_missing_data",
        "financial_interpretation_limits",
        "financial_assessment",
        "financial_sections_consumed",
        "financial_warnings_carried_forward",
        "evidence_ids",
        "historical_context_used",
        "years_considered",
        "supporting_pcim_sections",
        "status",
        "validation_status",
        "evidence_grounding_status",
        "financial_truth_consistency_status",
        "blocked_stale_financial_warnings",
        "diagnostic_only_financial_warnings",
        "reasoning_limits",
        "user_facing_brief",
        "warnings",
        "generated_at",
    }
    assert set(payload.keys()) == expected_clean_keys
    assert {
        "doctrine_id",
        "company",
        "analysis_mode",
        "generated_at",
        "evidence_id_normalization",
        "evidence_grounding_warnings",
        "schema_warnings",
        "evidence_routing_diagnostics",
    }.issubset(set(diagnostics.keys()))


def test_user_facing_brief_can_render_financial_lens_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="buffett", rating="strong"))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="buffett")
    payload = json.loads(written["buffett_analysis.json"].read_text())

    assert payload["user_facing_brief"]["financial_lens"]


def test_reasoning_limits_string_is_normalized_with_schema_warning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="buffett"))
    payload["reasoning_limits"] = "No valuation was performed."
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    written = InvestorPanelRunner(company="acme").run(analyst="buffett")
    saved, diagnostics = _read_saved_outputs(written, "buffett")

    assert "No valuation was performed." in saved["reasoning_limits"]
    assert any(
        "reasoning_limits was returned as string" in item
        for item in diagnostics["schema_warnings"]
    )


def test_reasoning_limits_null_becomes_empty_list_with_schema_warning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="buffett"))
    payload["reasoning_limits"] = None
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    written = InvestorPanelRunner(company="acme").run(analyst="buffett")
    _saved, diagnostics = _read_saved_outputs(written, "buffett")

    assert any(
        "reasoning_limits was null or missing" in item
        for item in diagnostics["schema_warnings"]
    )


def test_financial_assessment_list_fields_normalize_safely(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="buffett"))
    payload["financial_missing_data"] = "Free cash flow is unavailable in the supplied financial sections."
    payload["financial_interpretation_limits"] = None
    payload["financial_warnings_carried_forward"] = {"message": "Basis remains conservative."}
    payload["financial_assessment"]["key_financial_strengths"] = [{"summary": "Cash conversion remains better than PAT."}]
    payload["financial_assessment"]["key_financial_concerns"] = "Evidence is not complete enough for maximum confidence."
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    written = InvestorPanelRunner(company="acme").run(analyst="buffett")
    saved, diagnostics = _read_saved_outputs(written, "buffett")

    assert saved["financial_missing_data"] == ["Free cash flow is unavailable in the supplied financial sections."]
    assert saved["financial_interpretation_limits"] == []
    assert saved["financial_warnings_carried_forward"] == ["Basis remains conservative."]
    assert saved["financial_assessment"]["key_financial_strengths"] == ["Cash conversion remains better than PAT."]
    assert saved["financial_assessment"]["key_financial_concerns"] == ["Evidence is not complete enough for maximum confidence."]
    assert any(
        "financial_missing_data was returned as string" in item
        for item in diagnostics["schema_warnings"]
    )
    assert any(
        "financial_assessment.key_financial_strengths contained non-string items" in item
        for item in diagnostics["schema_warnings"]
    )


def test_source_chunk_in_normalized_list_field_still_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="buffett"))
    payload["reasoning_limits"] = [{"source_chunk": "forbidden raw text"}]
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    with pytest.raises(ValueError, match="source_chunk is not allowed in analyst output"):
        InvestorPanelRunner(company="acme").run(analyst="buffett")


def test_output_can_legitimately_reference_multi_year_inputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    payload = json.loads(_llm_output(doctrine_id="graham"))
    payload["supporting_pcim_sections"] = ["financial_strength_inputs", "multi_year_inputs", "risk_inputs"]
    fake_llm = FakeLLM(json.dumps(payload))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    saved = json.loads(written["graham_analysis.json"].read_text())

    assert "multi_year_inputs" in saved["supporting_pcim_sections"]
    assert saved["historical_context_used"] is True
    assert saved["years_considered"] == ["fy24", "fy25"]


def test_runner_all_analysts_auto_carry_fcf_missing_consistently(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["cash_conversion_inputs"]["metrics"] = [
        metric for metric in pcim["cash_conversion_inputs"]["metrics"]
        if metric["metric"] != "fcf"
    ]
    pcim["cash_conversion_inputs"]["warnings"] = ["free cash flow missing"]
    pcim_path.write_text(json.dumps(pcim), encoding="utf-8")

    responses = {}
    doctrine_metrics = {
        "graham": ["net_worth", "total_debt", "cfo", "capex", "book_value_per_share", "weighted_avg_shares"],
        "buffett": ["revenue", "cfo", "capex", "roce", "roe", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
        "fisher": ["revenue", "eps_basic"],
        "munger": ["cfo", "capex", "debt_to_equity"],
        "lynch": ["revenue", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
    }
    for doctrine_id in ("graham", "buffett", "fisher", "munger", "lynch"):
        payload = json.loads(_llm_output(doctrine_id=doctrine_id))
        payload["financial_metrics_used"] = doctrine_metrics[doctrine_id]
        payload["financial_missing_data"] = []
        payload["financial_interpretation_limits"] = ["Only supplied PCIM metrics were used; no new ratios were calculated."]
        payload["financial_warnings_carried_forward"] = []
        payload["financial_assessment"]["missing_financial_data"] = []
        payload["financial_assessment"]["financial_interpretation_limits"] = ["Only supplied PCIM metrics were used; no new ratios were calculated."]
        payload["financial_assessment"]["financial_warnings_carried_forward"] = []
        responses[doctrine_id] = json.dumps(payload)

    fake_llm = PromptRoutingFakeLLM(responses)
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    written = InvestorPanelRunner(company="acme").run()

    for doctrine_id in ("graham", "buffett", "fisher", "munger", "lynch"):
        saved = json.loads(written[f"{doctrine_id}_analysis.json"].read_text())
        assert any(
            "free cash flow is missing; fcf-based conclusions cannot be assessed." in item.lower()
            for item in saved["financial_warnings_carried_forward"]
        )
        assert any(
            "free cash flow is missing, so owner earnings, fcf margin, and fcf-supported dividend sustainability cannot be assessed."
            in item.lower()
            for item in saved["financial_interpretation_limits"]
        )
        if doctrine_id == "graham":
            assert any(
                "margin-of-safety judgment is limited because free cash flow is unavailable." in item.lower()
                for item in saved["financial_interpretation_limits"]
            )
        if doctrine_id == "buffett":
            assert any(
                "owner earnings cannot be assessed because free cash flow/capex data is missing or incomplete."
                in item.lower()
                for item in saved["financial_interpretation_limits"]
            )


def test_runner_only_loads_pcim_not_raw_multi_year_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="graham"))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    loaded_paths = []
    original_load_json = panel_runner._load_json

    def tracking_load_json(path):
        loaded_paths.append(str(path))
        return original_load_json(path)

    monkeypatch.setattr(panel_runner, "_load_json", tracking_load_json)

    runner = InvestorPanelRunner(company="acme")
    runner.run(analyst="graham")

    assert any(path.endswith("pcim_v1.json") for path in loaded_paths)
    assert not any("/multi_year/" in path for path in loaded_paths)


def test_prompt_includes_munger_monitoring_guidance_for_related_party_items(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="munger", rating="mixed", evidence_ids=["ev_inc_1", "ev_risk_1"]))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    runner.run(analyst="munger")

    prompt = fake_llm.calls[0]["prompt"]
    assert "monitoring signals first" in prompt
    assert "Do not overstate related-party advances or governance ambiguity" in prompt


def test_main_runs_investor_panel_without_year(monkeypatch):
    calls = []

    monkeypatch.setattr(
        run_company_pipeline,
        "run_investor_panel_stage",
        lambda company, analyst=None, context=None: calls.append(
            ("run_investor_panel_stage", company, analyst, context)
        ),
    )
    monkeypatch.setattr(
        run_company_pipeline.sys,
        "argv",
        ["run_company_pipeline", "tips", "--stage", "investor_panel", "--analyst", "graham"],
    )

    run_company_pipeline.main()

    assert calls == [("run_investor_panel_stage", "tips", "graham", None)]


def test_runner_keeps_company_memory_panel_dir_when_context_is_active(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="acme", year="fy25")
    context.create_directories()
    set_context(context)
    try:
        _write_pcim(tmp_path, "acme")
        fake_llm = FakeLLM(_llm_output(doctrine_id="graham"))
        monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

        written = InvestorPanelRunner(company="acme").run(analyst="graham")

        assert written["graham_analysis.json"].resolve() == (
            tmp_path / "companies" / "acme" / "company_memory" / "investor_panel" / "graham_analysis.json"
        ).resolve()
        assert written["graham_analysis_diagnostics.json"].resolve() == (
            tmp_path
            / "companies"
            / "acme"
            / "company_memory"
            / "investor_panel"
            / "graham_analysis_diagnostics.json"
        ).resolve()
        assert not (
            tmp_path / "companies" / "acme" / "fy25" / "intelligence" / "investor_panel" / "graham_analysis.json"
        ).exists()
    finally:
        set_context(None)


def test_dirty_financial_warning_text_is_sanitized_out_of_clean_payload():
    payload = json.loads(_llm_output(doctrine_id="graham"))
    payload["financial_warnings_carried_forward"] = [
        "Financial artifacts do not cover all company years: fy22, fy23",
        "normalized_fundamentals.json: Artifact missing.",
        "financial_audit_report.json is stale relative to newer outputs",
        "weighted_avg_shares: field has no populated normalized value",
        "standalone/consolidated basis unclear",
        "FCF missing",
    ]
    payload["financial_assessment"]["financial_warnings_carried_forward"] = list(
        payload["financial_warnings_carried_forward"]
    )

    clean, diagnostics = split_clean_and_diagnostics(payload)
    panel_runner.assert_clean_analysis_payload(clean)

    clean_blob = json.dumps(clean, ensure_ascii=False).lower()
    assert "artifact" not in clean_blob
    assert ".json" not in clean_blob
    assert "financial artifacts do not cover all company years" not in clean_blob
    assert "normalized_fundamentals.json" not in clean_blob
    assert "financial_audit_report.json" not in clean_blob
    assert "Financial data does not cover all company years." in clean["financial_warnings_carried_forward"]
    assert "Weighted average shares are missing; per-share interpretation remains limited." in clean["financial_warnings_carried_forward"]
    assert "Standalone/consolidated basis is unclear; financial comparability remains limited." in clean["financial_warnings_carried_forward"]
    assert "Free cash flow is missing; FCF-based conclusions cannot be assessed." in clean["financial_warnings_carried_forward"]
    warning_diagnostics = diagnostics["financial_warning_diagnostics"]
    assert "normalized_fundamentals.json: Artifact missing." in warning_diagnostics["removed_internal_financial_warnings"]
    assert "financial_audit_report.json is stale relative to newer outputs" in warning_diagnostics["removed_internal_financial_warnings"]
    assert "normalized_fundamentals.json: Artifact missing." in warning_diagnostics["raw_financial_warnings_carried_forward"]


def test_clean_string_sanitizer_rewrites_artifact_prose():
    diagnostics = {}
    sanitized = panel_runner.sanitize_clean_string(
        "Assessment relies on provided artifacts and source artifacts.",
        "$.assessment.management_rationality_assessment",
        diagnostics,
    )

    assert sanitized == "Assessment relies on provided materials and source materials."
    assert diagnostics["rewritten_strings"]


def test_clean_assertion_allows_artifact_term_after_sanitizer():
    payload = json.loads(_llm_output(doctrine_id="graham"))
    payload["assessment"]["management_rationality_assessment"] = "The provided artifacts suggest discipline."

    diagnostics = {}
    clean = panel_runner._sanitize_clean_payload(payload, "$", diagnostics)
    panel_runner.assert_clean_analysis_payload(clean)

    assert clean["assessment"]["management_rationality_assessment"] == "The provided materials suggest discipline."


def test_clean_assertion_still_fails_for_source_chunk_string():
    payload = json.loads(_llm_output(doctrine_id="graham"))
    payload["assessment"]["management_rationality_assessment"] = "This references source_chunk directly."

    with pytest.raises(ValueError, match="forbidden internal string"):
        panel_runner.assert_clean_analysis_payload(payload)


def test_write_clean_artifacts_writes_diagnostics_even_on_clean_failure(tmp_path):
    output_dir = tmp_path / "out"
    payload = json.loads(_llm_output(doctrine_id="graham"))
    payload["assessment"]["management_rationality_assessment"] = "This leaks source_chunk in prose."

    with pytest.raises(ValueError, match="clean analyst payload failed validation"):
        panel_runner.write_clean_analyst_artifacts(
            payload=payload,
            output_dir=output_dir,
            doctrine_id="graham",
            analysis_mode="llm_reasoning_v1",
        )

    diagnostics_path = output_dir / "graham_analysis_diagnostics.json"
    failed_candidate_path = output_dir / "graham_analysis_failed_clean_candidate.json"
    assert diagnostics_path.exists()
    assert failed_candidate_path.exists()

    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    assert diagnostics["clean_writer_status"] == "fail"
    assert diagnostics["failed_clean_candidate_path"].endswith("graham_analysis_failed_clean_candidate.json")
    assert diagnostics["remaining_forbidden_strings"]


def test_full_panel_stage_uses_same_global_fcf_warning_carry_forward(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, "acme")
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    pcim["cash_conversion_inputs"]["metrics"] = [
        metric for metric in pcim["cash_conversion_inputs"]["metrics"]
        if metric["metric"] != "fcf"
    ]
    pcim["cash_conversion_inputs"]["warnings"] = ["free cash flow missing"]
    pcim_path.write_text(json.dumps(pcim), encoding="utf-8")

    responses = {}
    doctrine_metrics = {
        "graham": ["net_worth", "total_debt", "cfo", "capex", "book_value_per_share", "weighted_avg_shares"],
        "buffett": ["revenue", "cfo", "capex", "roce", "roe", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
        "fisher": ["revenue", "eps_basic"],
        "munger": ["cfo", "capex", "debt_to_equity"],
        "lynch": ["revenue", "eps_basic", "book_value_per_share", "weighted_avg_shares"],
    }
    for doctrine_id in ("graham", "buffett", "fisher", "munger", "lynch"):
        payload = json.loads(_llm_output(doctrine_id=doctrine_id))
        payload["financial_metrics_used"] = doctrine_metrics[doctrine_id]
        payload["financial_missing_data"] = []
        payload["financial_interpretation_limits"] = ["Only supplied PCIM metrics were used; no new ratios were calculated."]
        payload["financial_warnings_carried_forward"] = []
        payload["financial_assessment"]["missing_financial_data"] = []
        payload["financial_assessment"]["financial_interpretation_limits"] = ["Only supplied PCIM metrics were used; no new ratios were calculated."]
        payload["financial_assessment"]["financial_warnings_carried_forward"] = []
        responses[doctrine_id] = json.dumps(payload)

    fake_llm = PromptRoutingFakeLLM(responses)
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)
    monkeypatch.setattr(
        run_company_pipeline,
        "_assess_pcim_freshness",
        lambda company, payload: {"status": "pass", "warnings": [], "failures": []},
    )

    panel_dir = tmp_path / "companies" / "acme" / "company_memory" / "investor_panel"

    def fake_committee_synthesis(company, context=None, cleanup_only=False):
        panel_dir.mkdir(parents=True, exist_ok=True)
        path = panel_dir / "committee_synthesis.json"
        path.write_text(
            json.dumps(
                {
                    "evidence_id_normalization": {"applied": True, "replacements": [], "unresolved_ids": []},
                    "areas_of_disagreement": [{"disagreement_type": "different_emphasis"}],
                }
            ),
            encoding="utf-8",
        )
        return {"committee_synthesis.json": path}

    def fake_committee_brief(company, context=None, include_evidence_ids=False):
        panel_dir.mkdir(parents=True, exist_ok=True)
        brief = panel_dir / "committee_brief.md"
        brief.write_text("brief", encoding="utf-8")
        qa = panel_dir / "committee_brief_qa.json"
        qa.write_text(json.dumps({"status": "pass", "warnings": [], "failures": []}), encoding="utf-8")
        return {"committee_brief.md": brief, "committee_brief_qa.json": qa}

    def fake_committee_brief_qa(company, context=None, include_evidence_ids=False):
        panel_dir.mkdir(parents=True, exist_ok=True)
        qa = panel_dir / "committee_brief_qa.json"
        qa.write_text(json.dumps({"status": "pass", "warnings": [], "failures": []}), encoding="utf-8")
        return {"committee_brief_qa.json": qa}

    monkeypatch.setattr(run_company_pipeline, "run_committee_synthesis_stage", fake_committee_synthesis)
    monkeypatch.setattr(run_company_pipeline, "run_committee_brief_stage", fake_committee_brief)
    monkeypatch.setattr(run_company_pipeline, "run_committee_brief_qa_stage", fake_committee_brief_qa)
    monkeypatch.setattr(
        run_company_pipeline,
        "_validate_analyst_output",
        lambda company, analyst, context=None: {
            "status": "pass",
            "evidence_grounding_status": "warning",
            "warning_count": 1,
            "output": str(panel_dir / f"{analyst}_analysis.json"),
            "payload": json.loads((panel_dir / f"{analyst}_analysis.json").read_text(encoding="utf-8")),
            "warnings": [],
            "failures": [],
        },
    )

    result = run_company_pipeline.run_panel_stage(company="acme", regenerate_analysts=True)
    summary = json.loads(
        (tmp_path / "companies" / "acme" / "company_memory" / "investor_panel" / "panel_run_summary.json").read_text(
            encoding="utf-8"
        )
    )
    graham = json.loads((panel_dir / "graham_analysis.json").read_text(encoding="utf-8"))

    assert result["panel_run_summary.json"].name == "panel_run_summary.json"
    assert summary["status"] in {"pass", "warning"}
    assert summary["analysts"]["graham"]["status"] in {"pass", "warning"}
    assert any(
        "free cash flow is missing; fcf-based conclusions cannot be assessed." in item.lower()
        for item in graham["financial_warnings_carried_forward"]
    )
    assert any(
        "margin-of-safety judgment is limited because free cash flow is unavailable." in item.lower()
        for item in graham["financial_interpretation_limits"]
    )


def test_main_runs_pcim_stage_without_year(monkeypatch):
    calls = []

    monkeypatch.setattr(
        run_company_pipeline,
        "run_cim_stage",
        lambda company, context=None: calls.append(
            ("run_cim_stage", company, context)
        ),
    )
    monkeypatch.setattr(
        run_company_pipeline.sys,
        "argv",
        ["run_company_pipeline", "tanla", "--stage", "pcim"],
    )

    run_company_pipeline.main()

    assert calls == [("run_cim_stage", "tanla", None)]


def test_finalize_analyst_validation_status_repairs_stale_fail_to_warning():
    analysis = {
        "evidence_grounding_status": "fail",
        "validation_status": "fail",
        "status": "fail",
        "evidence_ids": ["ev_1"],
        "key_findings": [{"finding": "ok", "evidence_ids": ["ev_1"]}],
        "red_flags": [],
        "open_uncertainties": [],
    }
    diagnostics = {
        "clean_writer_status": "pass",
        "evidence_routing_diagnostics": {
            "unresolved_claims": [],
            "replaced_evidence": [{"claim_path": "key_findings[0]"}],
        },
        "evidence_id_normalization": {
            "unresolved_ids": [],
            "removed_invalid_ids": [],
        },
    }

    finalized = finalize_analyst_validation_status(analysis, diagnostics)

    assert finalized["evidence_grounding_status"] == "warning"
    assert diagnostics["post_finalization_status"]["status"] == "warning"


def test_finalize_analyst_validation_status_keeps_fail_for_unresolved_claims():
    analysis = {
        "evidence_grounding_status": "warning",
        "validation_status": "warning",
        "status": "warning",
        "evidence_ids": ["ev_1"],
        "assessment": {"downside_assessment": "Liquidity pressure remains elevated."},
        "key_findings": [{"finding": "ok", "evidence_ids": ["ev_1"]}],
        "red_flags": [],
        "open_uncertainties": [],
    }
    diagnostics = {
        "evidence_routing_diagnostics": {
            "unresolved_claims": [{"claim_path": "assessment.downside", "claim_text": "Liquidity pressure remains elevated."}],
        },
        "evidence_id_normalization": {
            "unresolved_ids": [],
            "removed_invalid_ids": [],
        },
    }

    finalized = finalize_analyst_validation_status(analysis, diagnostics)

    assert finalized["status"] == "fail"
    assert "unresolved factual claims remain after evidence routing repair" in finalized["hard_failures"]


def test_finalize_analyst_validation_status_removed_unresolved_claim_becomes_warning():
    analysis = {
        "evidence_grounding_status": "fail",
        "validation_status": "fail",
        "status": "fail",
        "evidence_ids": ["ev_1"],
        "assessment": {"downside_assessment": "Insufficient direct evidence in the compacted PCIM to make a confident doctrine-specific assessment. Treat this as a limitation, not a company conclusion."},
        "key_findings": [{"finding": "Conservative liquidity interpretation remains limited.", "evidence_ids": ["ev_1"]}],
        "red_flags": [],
        "open_uncertainties": ["Liquidity evidence remains incomplete."],
    }
    diagnostics = {
        "clean_writer_status": "pass",
        "evidence_routing_diagnostics": {
            "unresolved_claims": [{"claim_path": "assessment.downside", "claim_text": "Liquidity pressure remains elevated."}],
            "claims_converted_to_limitations": [{"claim_path": "assessment.downside"}],
        },
        "evidence_id_normalization": {
            "unresolved_ids": ["ev_missing"],
            "removed_invalid_ids": [{"path": "$.key_findings[0].evidence_ids", "invalid_id": "ev_missing", "reason": "unknown_evidence_id"}],
        },
    }

    finalized = finalize_analyst_validation_status(analysis, diagnostics)

    assert finalized["status"] == "warning"
    assert "unresolved factual claims remain after evidence routing repair" not in finalized["hard_failures"]
    assert any("removed from active conclusions" in item for item in finalized["warnings"])


def test_finalize_analyst_validation_status_replaces_boilerplate_assessment():
    analysis = {
        "evidence_grounding_status": "fail",
        "validation_status": "fail",
        "status": "fail",
        "evidence_ids": [],
        "assessment": {
            "downside_assessment": "Downside assessment is grounded in balance_sheet_strength_inputs and is interpreted through the doctrine focus on downside protection."
        },
        "key_findings": [],
        "red_flags": [],
        "open_uncertainties": [],
    }
    diagnostics = {
        "clean_writer_status": "pass",
        "evidence_routing_diagnostics": {
            "unresolved_claims": [{"claim_path": "assessment.downside", "claim_text": "Downside assessment is grounded in balance_sheet_strength_inputs and is interpreted through the doctrine focus on downside protection."}],
        },
        "evidence_id_normalization": {"unresolved_ids": [], "removed_invalid_ids": []},
    }

    finalized = finalize_analyst_validation_status(analysis, diagnostics)

    assert finalized["status"] == "warning"
    assert "Insufficient direct evidence in the compacted PCIM" in finalized["assessment"]["downside_assessment"]
    assert "unresolved factual claims remain after evidence routing repair" not in finalized["hard_failures"]


def test_finalize_analyst_validation_status_normalized_evidence_id_is_not_hard_fail():
    analysis = {
        "evidence_grounding_status": "warning",
        "validation_status": "warning",
        "status": "warning",
        "evidence_ids": ["ev_json_1"],
        "key_findings": [{"finding": "ok", "evidence_ids": ["ev_json_1"]}],
        "red_flags": [],
        "open_uncertainties": [],
    }
    diagnostics = {
        "clean_writer_status": "pass",
        "evidence_routing_diagnostics": {},
        "evidence_id_normalization": {
            "unresolved_ids": [],
            "removed_invalid_ids": [],
            "replacements": [{"original_id": "ev_1", "canonical_id": "ev_json_1"}],
        },
        "evidence_grounding_warnings": [{"issue": "evidence category metadata weak", "path": "key_findings[0]"}],
    }

    finalized = finalize_analyst_validation_status(analysis, diagnostics)

    assert finalized["status"] == "warning"
    assert finalized["hard_failures"] == []


def test_finalize_analyst_financial_warnings_rewrites_stale_missing_warning():
    analysis = {
        "financial_missing_data": ["FCF missing"],
        "financial_interpretation_limits": [],
        "financial_warnings_carried_forward": [],
        "red_flags": [],
        "open_uncertainties": [],
        "financial_red_flags": [],
        "precise_missing_financial_data": [],
        "reasoning_limits": [],
        "user_facing_brief": {
            "what_needs_caution": [],
            "what_is_missing": [],
            "bottom_line": "",
        },
        "financial_assessment": {
            "key_financial_concerns": [],
            "financial_red_flags": [],
            "missing_financial_data": ["FCF missing"],
            "financial_interpretation_limits": [],
            "financial_warnings_carried_forward": [],
        },
    }
    truth_pack = {
        "usable_derived_metrics": ["fcf"],
    }
    diagnostics = {}

    finalized = finalize_analyst_financial_warnings(analysis, truth_pack, diagnostics)

    assert len(finalized["financial_missing_data"]) == 1
    assert "derived fcf / owner-earnings estimate is available" in finalized["financial_missing_data"][0].lower()
    assert "maintenance versus growth capex split" in finalized["financial_missing_data"][0].lower()
    assert diagnostics["financial_warning_resolution"][0]["resolution_status"] == "rewritten"


def test_finalize_analyst_financial_warnings_rewrites_stale_capex_and_payables_warnings():
    analysis = {
        "financial_missing_data": ["Capex missing", "Payables or payable-days evidence is missing"],
        "financial_interpretation_limits": ["cash conversion cycle cannot be assessed cleanly"],
        "financial_warnings_carried_forward": [],
        "red_flags": [],
        "open_uncertainties": [],
        "financial_red_flags": [],
        "precise_missing_financial_data": [],
        "reasoning_limits": [],
        "user_facing_brief": {
            "what_needs_caution": [],
            "what_is_missing": [],
            "bottom_line": "",
        },
        "financial_assessment": {
            "key_financial_concerns": [],
            "financial_red_flags": [],
            "missing_financial_data": ["Capex missing"],
            "financial_interpretation_limits": ["cash conversion cycle cannot be assessed cleanly"],
            "financial_warnings_carried_forward": ["Payables or payable-days evidence is missing"],
        },
    }
    truth_pack = {
        "usable_current_metrics": ["payables", "payable_days"],
        "usable_derived_metrics": ["capex", "cash_conversion_cycle"],
    }
    diagnostics = {}

    finalized = finalize_analyst_financial_warnings(analysis, truth_pack, diagnostics)

    assert any("maintenance versus growth capex split is unavailable" in item.lower() for item in finalized["financial_missing_data"])
    assert any("payables and payable-days are available" in item.lower() for item in finalized["financial_interpretation_limits"])
    assert diagnostics["financial_warning_resolution"]


def test_finalize_analyst_financial_truth_consistency_cleans_active_fields_and_internal_labels():
    analysis = {
        "key_findings": ["Free cash flow is missing; FCF-based conclusions cannot be assessed."],
        "red_flags": ["free cash flow and capex data are not provided"],
        "open_uncertainties": ["Payables or payable-days evidence is missing; cash conversion cycle cannot be assessed cleanly."],
        "financial_red_flags": ["capex data are not provided"],
        "financial_missing_data": ["FCF missing", "Capex missing"],
        "financial_interpretation_limits": ["cash conversion cycle cannot be assessed cleanly"],
        "financial_warnings_carried_forward": ["fcf: derived value used"],
        "user_facing_brief": {
            "what_looks_good": ["fcf: derived value used"],
            "what_needs_caution": ["Free cash flow and capex data are not provided; owner-earnings cannot be assessed."],
            "what_is_missing": ["weighted_avg_shares: field has no populated normalized value"],
            "bottom_line": "Capex is unavailable.",
            "financial_lens": ["critical financial fields include unknown basis entries"],
        },
        "financial_assessment": {
            "key_financial_strengths": ["fcf: fcf is derived from normalized inputs"],
            "key_financial_concerns": ["Capex missing"],
            "financial_red_flags": ["Payables or payable-days evidence is missing"],
            "missing_financial_data": ["FCF missing"],
            "financial_interpretation_limits": ["owner-earnings cannot be assessed"],
            "financial_warnings_carried_forward": ["preferred basis is unknown"],
        },
    }
    truth_pack = {
        "usable_current_metrics": ["payables", "payable_days"],
        "usable_derived_metrics": ["fcf", "owner_earnings_estimate", "capex", "cash_conversion_cycle"],
    }
    diagnostics = {}

    finalized = finalize_analyst_financial_truth_consistency(analysis, truth_pack, diagnostics)

    assert any("derived fcf / owner-earnings estimate is available" in item.lower() for item in finalized["key_findings"])
    assert not any("free cash flow and capex data are not provided" in item.lower() for item in finalized["red_flags"])
    assert any("identified capex is available" in item.lower() for item in finalized["financial_red_flags"])
    assert any("payables and payable-days are available" in item.lower() for item in finalized["open_uncertainties"])
    assert any("weighted-average shares are unavailable" in item.lower() for item in finalized["user_facing_brief"]["what_is_missing"])
    assert any("standalone versus consolidated basis remains unclear" in item.lower() for item in finalized["user_facing_brief"]["financial_lens"])
    assert "fcf: derived value used" in diagnostics["diagnostic_only_financial_warnings"]
    assert finalized["financial_truth_consistency_status"] == "warning"
    assert finalized["blocked_stale_financial_warnings"]
    assert finalized["diagnostic_only_financial_warnings"] == [
        "Internal raw financial warning labels were moved to diagnostics."
    ]


def test_finalize_analyst_financial_truth_consistency_preserves_valid_limitations():
    analysis = {
        "financial_interpretation_limits": [
            "Maintenance versus growth capex split is unavailable.",
            "FY22/FY23 owner-earnings bridge history remains unavailable.",
            "Standalone/consolidated basis is unclear.",
            "Weighted-average shares are missing.",
        ],
        "user_facing_brief": {"what_needs_caution": [], "what_is_missing": [], "bottom_line": "", "financial_lens": []},
        "financial_assessment": {
            "key_financial_strengths": [],
            "key_financial_concerns": [],
            "financial_red_flags": [],
            "missing_financial_data": [],
            "financial_interpretation_limits": [
                "Maintenance versus growth capex split is unavailable.",
                "Weighted-average shares are missing.",
            ],
            "financial_warnings_carried_forward": [],
        },
    }
    diagnostics = {}

    finalized = finalize_analyst_financial_truth_consistency(analysis, {}, diagnostics)

    assert "Maintenance versus growth capex split is unavailable." in finalized["financial_interpretation_limits"]
    assert "FY22/FY23 owner-earnings bridge history remains unavailable." in finalized["financial_interpretation_limits"]
    assert "Standalone/consolidated basis is unclear." in finalized["financial_interpretation_limits"]
    assert "Weighted-average shares are missing." in finalized["financial_interpretation_limits"]


def test_finalize_analyst_validation_status_preserves_fail_without_repair_diagnostics():
    analysis = {
        "evidence_grounding_status": "fail",
        "validation_status": "fail",
        "status": "fail",
        "evidence_ids": [],
        "key_findings": [],
        "red_flags": [],
        "open_uncertainties": [],
    }
    diagnostics = {
        "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
        "evidence_routing_diagnostics": {},
    }

    finalized = finalize_analyst_validation_status(analysis, diagnostics)

    assert finalized["status"] == "fail"
    assert finalized["hard_failures"] == ["evidence_grounding_status=fail"]


def test_finalize_analyst_validation_status_persists_financial_truth_status_fields():
    analysis = {
        "evidence_grounding_status": "warning",
        "validation_status": "warning",
        "status": "warning",
        "financial_truth_consistency_status": "warning",
        "blocked_stale_financial_warnings": ["Stale missing-data warnings were blocked after financial truth reconciliation."],
        "diagnostic_only_financial_warnings": ["Internal raw financial warning labels were moved to diagnostics."],
        "evidence_ids": [],
        "key_findings": [],
        "red_flags": [],
        "open_uncertainties": [],
    }
    diagnostics = {
        "blocked_stale_financial_warnings": ["FCF missing"],
        "diagnostic_only_financial_warnings": ["fcf: derived value used"],
        "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
        "evidence_routing_diagnostics": {},
    }

    finalized = finalize_analyst_validation_status(analysis, diagnostics)

    assert finalized["status"] == "warning"
    assert finalized["validation_status"] == "warning"
    assert finalized["evidence_grounding_status"] == "warning"
    assert finalized["financial_truth_consistency_status"] == "warning"
    assert finalized["blocked_stale_financial_warnings"] == [
        "Stale missing-data warnings were blocked after financial truth reconciliation."
    ]
    assert finalized["diagnostic_only_financial_warnings"] == [
        "Internal raw financial warning labels were moved to diagnostics."
    ]
