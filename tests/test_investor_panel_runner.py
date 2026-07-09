import json
from pathlib import Path

import pytest

from intelligence.investor_panel import runner as panel_runner
from intelligence.investor_panel.runner import InvestorPanelRunner
from pipelines import run_company_pipeline


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
                "source_chunk": long_chunk,
                "evidence_ids": [f"ev_risk_{idx}"],
                "evidence_references": [
                    {
                        "page": 50 + idx,
                        "source_chunk": long_chunk,
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
            "governance_and_incentive_inputs",
            "risk_inputs",
            "capital_allocation_inputs",
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
            "capital_allocation_inputs",
            "governance_and_incentive_inputs",
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
            "capital_allocation_inputs",
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
            "growth_execution_inputs",
            "moat_inputs",
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
            "growth_execution_inputs",
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
            "evidence_ids": evidence_ids,
            "supporting_pcim_sections": supporting_pcim_sections,
            "reasoning_limits": [
                "This judgment uses only supplied PCIM sections.",
                "No valuation conclusion is attempted.",
            ],
        }
    )


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
    assert '"business_understanding"' not in prompt
    assert "Allowed supporting_pcim_sections:" in prompt
    assert '"financial_strength_inputs"' in prompt
    assert "Do not treat dividends, related-party advances, or governance ambiguity as automatic condemnation without context" in prompt


def test_compact_prompt_pack_removes_source_chunk_and_preserves_evidence_ids(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_large_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="munger", rating="mixed", evidence_ids=["ev_risk_0", "ev_gov_0"]))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="munger")
    payload = json.loads(written["munger_analysis.json"].read_text())
    prompt = fake_llm.calls[0]["prompt"]

    assert "source_chunk" not in prompt
    assert "short_excerpt" in prompt
    assert "ev_risk_0" in prompt
    assert payload["evidence_ids"] == ["ev_risk_0", "ev_gov_0"]
    assert panel_runner.COMPACTION_REASONING_LIMIT in payload["reasoning_limits"]


def test_large_pcim_prompt_stays_under_budget_and_uses_compact_view(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_large_pcim(tmp_path, "acme")
    fake_llm = FakeLLM(_llm_output(doctrine_id="munger", rating="mixed", evidence_ids=["ev_risk_0", "ev_inc_0"]))
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    runner.run(analyst="munger")

    prompt = fake_llm.calls[0]["prompt"]
    assert len(prompt) <= panel_runner.DEFAULT_MAX_TOTAL_PROMPT_CHARS
    assert "Selected compact PCIM sections:" in prompt


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
    assert "Missing for test" in prompt


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
                "evidence_ids": ["ev_cap_1", "ev_risk_1", "not_allowed"],
                "supporting_pcim_sections": [
                    "financial_strength_inputs",
                    "risk_inputs",
                    "capital_allocation_inputs",
                    "evidence_map",
                    "uncertainty_missing_data",
                ],
                "reasoning_limits": ["PCIM-only judgment."],
            }
        )
    )
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="graham")
    payload = json.loads(written["graham_analysis.json"].read_text())

    assert payload["evidence_ids"] == ["ev_cap_1", "ev_risk_1"]


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
                "evidence_ids": ["ev_inc_1", "ev_risk_1"],
                "supporting_pcim_sections": [
                    "governance_and_incentive_inputs",
                    "risk_inputs",
                    "promise_tracker",
                ],
                "reasoning_limits": ["PCIM-only judgment."],
            }
        )
    )
    monkeypatch.setattr(panel_runner, "get_llm", lambda: fake_llm)

    runner = InvestorPanelRunner(company="acme")
    written = runner.run(analyst="munger")
    payload = json.loads(written["munger_analysis.json"].read_text())

    assert payload["supporting_pcim_sections"] == ["governance_and_incentive_inputs", "risk_inputs"]
    assert any("promise_tracker" in item for item in payload["reasoning_limits"])


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
                "evidence_ids": ["ev_inc_1", "ev_risk_1"],
                "supporting_pcim_sections": ["promise_tracker"],
                "reasoning_limits": ["PCIM-only judgment."],
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
    payload = json.loads(written["munger_analysis.json"].read_text())

    expected_keys = {
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
        "evidence_ids",
        "supporting_pcim_sections",
        "reasoning_limits",
        "generated_at",
    }
    assert set(payload.keys()) == expected_keys


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
