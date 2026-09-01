from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from intelligence.management_credibility.builder import (
    build_management_credibility_synthesis,
    execution_vs_economics_conclusion,
    write_management_credibility_synthesis,
)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _company(tmp_path: Path, name: str = "acme") -> Path:
    root = tmp_path / name / "company_memory"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _promise(
    promise_id: str,
    *,
    current_status: str = "UNVERIFIED",
    execution_status: str = "ACTION_STARTED",
    outcome_status: str = "UNVERIFIED",
    financial_link_status: str = "INSUFFICIENT_EVIDENCE",
    theme: str = "Digital platform rollout",
    evidence_ids: list[str] | None = None,
) -> Dict[str, Any]:
    return {
        "promise_id": promise_id,
        "theme": theme,
        "source_period": "fy23",
        "current_status": current_status,
        "execution_status": execution_status,
        "outcome_status": outcome_status,
        "financial_link_status": financial_link_status,
        "later_evidence": [{"period": "fy24", "role": "action", "verification_status": "unresolved"}],
        "evidence_ids": evidence_ids or [f"ev_{promise_id}"],
        "investor_interpretation": f"{theme}: execution evidence and outcome evidence are separated.",
    }


def _base_memory(tmp_path: Path) -> None:
    mem = _company(tmp_path)
    _write_json(
        mem / "gold" / "management_promise_tracker.json",
        {
            "schema_version": "promise_tracker_gold.v1",
            "material_promises": [
                _promise(
                    "p1",
                    current_status="PARTIALLY_ACHIEVED",
                    execution_status="ACTION_COMPLETED",
                    outcome_status="PARTIALLY_ACHIEVED",
                    financial_link_status="PARTIAL",
                    theme="Branch expansion execution",
                ),
                _promise(
                    "p2",
                    current_status="PARTIALLY_ACHIEVED",
                    execution_status="ACTION_COMPLETED",
                    outcome_status="PARTIALLY_ACHIEVED",
                    financial_link_status="PARTIAL",
                    theme="Digital onboarding deployment",
                ),
                _promise("p3", theme="Customer-service upgrade"),
                _promise("p4", theme="Technology modernization"),
                _promise("p5", theme="Product launch roadmap"),
            ],
        },
    )
    _write_json(
        mem / "gold" / "capital_allocation_outcome_tracker.json",
        {
            "schema_version": "capital_allocation_outcome_gold.v1",
            "material_allocations": [
                {
                    "allocation_id": "ca1",
                    "theme": "Organic capex supporting distribution expansion",
                    "allocation_type": "ORGANIC_CAPEX",
                    "source_period": "fy22",
                    "latest_period": "fy25",
                    "deployment_periods": ["fy22", "fy24", "fy25"],
                    "execution_status": "deployed",
                    "return_status": "UNPROVEN",
                    "evidence_level": "EXECUTION_VISIBLE",
                    "evidence_ids": ["ev_ca1"],
                    "investor_interpretation": "Capital was deployed, but incremental returns remain unproven.",
                },
                {
                    "allocation_id": "ca2",
                    "theme": "Technology platform capex",
                    "allocation_type": "ORGANIC_CAPEX",
                    "source_period": "fy24",
                    "latest_period": "fy25",
                    "execution_status": "deployed",
                    "return_status": "MIXED",
                    "evidence_level": "FINANCIAL_OUTCOME_VISIBLE",
                    "evidence_ids": ["ev_ca2"],
                },
            ],
        },
    )
    _write_json(
        mem / "gold" / "strategy_evolution_timeline.json",
        {
            "schema_version": "strategy_evolution_gold.v1",
            "strategy_themes": [
                {
                    "theme_id": "st1",
                    "theme_name": "Distribution expansion",
                    "first_period": "fy21",
                    "last_confirmed_period": "fy25",
                    "periods_active": ["fy21", "fy22", "fy24", "fy25"],
                    "current_status": "CURRENT_PRIORITY",
                    "capital_backed": True,
                    "execution_evidence": True,
                    "evidence_ids": ["ev_st1"],
                },
                {
                    "theme_id": "st2",
                    "theme_name": "Digital process modernization",
                    "first_period": "fy22",
                    "last_confirmed_period": "fy25",
                    "periods_active": ["fy22", "fy23", "fy24", "fy25"],
                    "current_status": "CURRENT_PRIORITY",
                    "capital_backed": True,
                    "execution_evidence": True,
                    "evidence_ids": ["ev_st2"],
                },
            ],
        },
    )
    _write_json(
        mem / "gold" / "risk_evolution_timeline.json",
        {
            "schema_version": "risk_evolution_gold.v1",
            "risk_themes": [
                {
                    "risk_theme_id": "rg1",
                    "theme": "regulatory",
                    "current_state": "MITIGATION_STARTED",
                    "direction": "stable",
                    "mitigation_status": "started",
                    "investor_interpretation": "Management response has started, but effect is not yet proven.",
                    "evidence_ids": ["ev_rg1"],
                },
                {
                    "risk_theme_id": "rg2",
                    "theme": "credit quality",
                    "current_state": "WORSENING",
                    "direction": "worsening",
                    "mitigation_status": "not_evidenced",
                    "investor_interpretation": "Credit quality risk is worsening.",
                    "evidence_ids": ["ev_rg2"],
                },
            ],
        },
    )
    _write_json(
        mem / "management_progression" / "management_progression.json",
        {
            "progression_items": [
                {
                    "item_id": "mp1",
                    "theme": "Commissioned customer research agency",
                    "synthesis_chain": {
                        "chain_status": "ACTION_COMPLETED",
                        "action": {"text": "Management commissioned an external research agency."},
                        "outcome": {"text": ""},
                        "financial_consequence": {"link_status": "not_yet_visible"},
                        "evidence_ids": ["ev_mp1"],
                    },
                },
                {
                    "item_id": "mp2",
                    "theme": "Plant utilization improvement",
                    "synthesis_chain": {
                        "chain_status": "FINANCIAL_IMPACT_CONFIRMED",
                        "action": {"text": "Plant commissioned."},
                        "outcome": {"text": "Utilization rose after commissioning."},
                        "financial_consequence": {"link_status": "confirmed"},
                        "evidence_ids": ["ev_mp2"],
                    },
                },
            ],
            "contradiction_signals": [],
        },
    )


def test_multiple_achieved_promises_create_positive_follow_through_pattern(tmp_path):
    _base_memory(tmp_path)
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    dim = result["dimensions"]["promise_follow_through"]
    assert dim["assessment"] == "constructive_but_incomplete"
    assert dim["supporting_evidence"]


def test_multiple_unverified_promises_are_evidence_limitation_not_failure(tmp_path):
    _base_memory(tmp_path)
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    dim = result["dimensions"]["promise_follow_through"]
    assert "evidence-completeness limitation" in " ".join(dim["uncertainty"])
    assert "automatic proof of management failure" in " ".join(dim["uncertainty"])


def test_repeated_delays_create_execution_caution(tmp_path):
    mem = _company(tmp_path)
    _write_json(
        mem / "gold" / "management_promise_tracker.json",
        {"material_promises": [_promise("p1", current_status="DELAYED"), _promise("p2", current_status="DELAYED")]},
    )
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    assert result["dimensions"]["promise_follow_through"]["assessment"] == "mixed_with_follow_through_cautions"
    assert result["dimensions"]["execution_discipline"]["contrary_evidence"]


def test_completed_actions_without_financial_outcome_create_economic_caution(tmp_path):
    mem = _company(tmp_path)
    _write_json(
        mem / "gold" / "management_promise_tracker.json",
        {
            "material_promises": [
                _promise("p1", current_status="UNVERIFIED", execution_status="ACTION_COMPLETED", financial_link_status="INSUFFICIENT_EVIDENCE"),
                _promise("p2", current_status="UNVERIFIED", execution_status="ACTION_COMPLETED", financial_link_status="INSUFFICIENT_EVIDENCE"),
            ]
        },
    )
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    econ = result["dimensions"]["economic_follow_through"]
    assert econ["assessment"] in {"economic_follow_through_unproven", "limited_economic_evidence"}
    assert any("execution_without_financial_proof" == item["signal"] for item in econ["contrary_evidence"])


def test_strategy_backed_by_capital_is_alignment_not_return_quality(tmp_path):
    _base_memory(tmp_path)
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    capital = result["dimensions"]["capital_allocation_alignment"]
    econ = result["dimensions"]["economic_follow_through"]
    assert capital["assessment"] == "strategy_capital_alignment_visible"
    assert any("return quality is assessed separately" in capital["investor_interpretation"] for _ in [capital])
    assert econ["contrary_evidence"]


def test_capital_backed_strategy_with_poor_returns_keeps_economics_weak(tmp_path):
    mem = _company(tmp_path)
    _write_json(
        mem / "gold" / "strategy_evolution_timeline.json",
        {
            "strategy_themes": [
                {
                    "theme_id": "st1",
                    "theme_name": "Capacity expansion",
                    "periods_active": ["fy22", "fy23", "fy24"],
                    "current_status": "CURRENT_PRIORITY",
                    "capital_backed": True,
                    "execution_evidence": True,
                }
            ]
        },
    )
    _write_json(
        mem / "gold" / "capital_allocation_outcome_tracker.json",
        {
            "material_allocations": [
                {
                    "allocation_id": "ca1",
                    "theme": "Capacity expansion",
                    "return_status": "UNPROVEN",
                    "execution_status": "deployed",
                    "evidence_ids": ["ev_ca1"],
                }
            ]
        },
    )
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    assert result["dimensions"]["capital_allocation_alignment"]["supporting_evidence"]
    assert result["dimensions"]["economic_follow_through"]["assessment"] != "economic_follow_through_partly_visible"


def test_rational_pivot_or_not_reconfirmed_is_not_automatic_credibility_failure(tmp_path):
    mem = _company(tmp_path)
    _write_json(
        mem / "gold" / "strategy_evolution_timeline.json",
        {
            "strategy_themes": [
                {
                    "theme_id": "st1",
                    "theme_name": "Legacy branch expansion",
                    "periods_active": ["fy21"],
                    "current_status": "NOT_RECONFIRMED",
                }
            ]
        },
    )
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    assert "not treated as failed strategies" in " ".join(result["dimensions"]["strategic_consistency"]["uncertainty"])


def test_explicit_contradiction_creates_disclosure_caution(tmp_path):
    mem = _company(tmp_path)
    _write_json(
        mem / "management_progression" / "management_progression.json",
        {
            "progression_items": [],
            "contradiction_signals": [{"item_id": "c1", "text": "Later evidence contradicted the original target.", "evidence_ids": ["ev_c1"]}],
        },
    )
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    assert result["dimensions"]["disclosure_quality"]["assessment"] == "disclosure_consistency_caution"
    assert result["dimensions"]["disclosure_quality"]["contrary_evidence"]


def test_mitigation_completed_but_risk_unresolved_is_mixed(tmp_path):
    mem = _company(tmp_path)
    _write_json(
        mem / "gold" / "risk_evolution_timeline.json",
        {
            "risk_themes": [
                {
                    "risk_theme_id": "rg1",
                    "theme": "customer service",
                    "current_state": "MITIGATION_STARTED",
                    "mitigation_status": "completed_outcome_unproven",
                    "investor_interpretation": "Mitigation completed, resolution unproven.",
                    "evidence_ids": ["ev_rg1"],
                }
            ]
        },
    )
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    assert result["dimensions"]["risk_response"]["assessment"] == "risk_response_started_but_resolution_unproven"
    assert any(p["pattern_id"] == "risk_mitigation_without_resolution" for p in result["credibility_patterns"])


def test_improving_recent_pattern_can_differ_from_historical_pattern(tmp_path):
    _base_memory(tmp_path)
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    assert result["dimensions"]["strategic_consistency"]["assessment"] == "persistent_core_strategy_visible"
    assert result["dimensions"]["risk_response"]["assessment"] in {"risk_response_started_but_resolution_unproven", "risk_response_unresolved"}


def test_disclosure_with_measurable_targets_and_followup_is_stronger(tmp_path):
    mem = _company(tmp_path)
    _write_json(
        mem / "gold" / "management_promise_tracker.json",
        {
            "material_promises": [
                {
                    **_promise("p1"),
                    "measurable_commitment": {"target_description": "Reach 80% utilization", "target_period": "fy25"},
                    "later_evidence": [{"period": "fy25"}, {"period": "fy26"}],
                }
            ]
        },
    )
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    assert result["dimensions"]["disclosure_quality"]["assessment"] == "specificity_or_follow_up_visible"


def test_generic_promotional_language_alone_is_insufficient(tmp_path):
    mem = _company(tmp_path)
    _write_json(
        mem / "management_progression" / "management_progression.json",
        {
            "progression_items": [
                {"item_id": "mp1", "theme": "leading world class robust commitment to excellence", "synthesis_chain": {"chain_status": "CLAIM_ONLY"}}
            ]
        },
    )
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    assert result["dimensions"]["disclosure_quality"]["assessment"] == "disclosure_specificity_limited"


def test_guidance_weight_has_no_numeric_score(tmp_path):
    _base_memory(tmp_path)
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    assert result["summary"]["guidance_weight"] in {"STRONG_WEIGHT", "MODERATE_WEIGHT", "CAUTIOUS_WEIGHT", "INSUFFICIENT_BASIS"}
    text = json.dumps(result).lower()
    assert "credibility_score" not in text
    assert "trust score" not in text
    assert "/100" not in text


def test_unresolved_risk_and_insufficient_promise_verification_prevent_strong_weight(tmp_path):
    mem = _company(tmp_path)
    _write_json(
        mem / "gold" / "management_promise_tracker.json",
        {
            "material_promises": [
                _promise("p1"),
                _promise("p2"),
                _promise("p3"),
            ]
        },
    )
    _write_json(
        mem / "gold" / "strategy_evolution_timeline.json",
        {
            "strategy_themes": [
                {
                    "theme_id": "st1",
                    "theme_name": "Product innovation",
                    "periods_active": ["fy21", "fy22", "fy23"],
                    "current_status": "CURRENT_PRIORITY",
                    "capital_backed": True,
                    "execution_evidence": True,
                },
                {
                    "theme_id": "st2",
                    "theme_name": "Market expansion",
                    "periods_active": ["fy21", "fy22", "fy23"],
                    "current_status": "CURRENT_PRIORITY",
                    "capital_backed": True,
                    "execution_evidence": True,
                },
            ]
        },
    )
    _write_json(
        mem / "gold" / "capital_allocation_outcome_tracker.json",
        {
            "material_allocations": [
                {"allocation_id": "ca1", "theme": "Product innovation", "return_status": "MIXED", "execution_status": "deployed"}
            ]
        },
    )
    _write_json(
        mem / "gold" / "risk_evolution_timeline.json",
        {
            "risk_themes": [
                {"risk_theme_id": "rg1", "theme": "regulatory", "current_state": "WORSENING", "direction": "worsening"}
            ]
        },
    )
    _write_json(
        mem / "management_progression" / "management_progression.json",
        {
            "progression_items": [
                {"item_id": "mp1", "theme": "Platform launched", "synthesis_chain": {"chain_status": "ACTION_COMPLETED"}}
            ]
        },
    )
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    assert result["summary"]["guidance_weight"] != "STRONG_WEIGHT"


def test_evidence_ids_preserved(tmp_path):
    _base_memory(tmp_path)
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    all_ids = json.dumps(result)
    assert "ev_p1" in all_ids
    assert "ev_st1" in all_ids


def test_no_company_sector_year_hardcoding_and_write_contract(tmp_path):
    _base_memory(tmp_path)
    path = write_management_credibility_synthesis("acme", companies_root=tmp_path)
    payload = json.loads(path.read_text())
    assert path == tmp_path / "acme" / "company_memory" / "gold" / "management_credibility_synthesis.json"
    assert payload["schema_version"] == "management_credibility_gold.v1"
    source = Path(__file__).parents[2] / "intelligence" / "management_credibility" / "builder.py"
    text = source.read_text()
    assert 'company_slug == "sun_pharma"' not in text
    assert 'company_slug == "ujjivan"' not in text
    assert 'company_slug == "tanla"' not in text
    assert "if sector ==" not in text


def test_execution_vs_economics_helper_states_distinction(tmp_path):
    _base_memory(tmp_path)
    result = build_management_credibility_synthesis("acme", companies_root=tmp_path, generated_at="now")
    conclusion = execution_vs_economics_conclusion(result["dimensions"])
    assert "economic" in conclusion.lower()
    assert "execution" in conclusion.lower()
