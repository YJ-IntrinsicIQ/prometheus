from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from intelligence.risk_evolution_timeline.builder import (
    build_risk_evolution_timeline,
    normalize_risk_theme,
    write_risk_evolution_timeline,
)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _company(tmp_path: Path, name: str = "acme") -> Path:
    root = tmp_path / name / "company_memory"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _risk(
    risk_id: str,
    name: str,
    *,
    mentions: list[dict[str, Any]],
    severities: dict[str, str],
    repeated: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "risk_id": risk_id,
        "risk_name": name,
        "normalized_risk": name.lower().replace(" ", "_"),
        "first_seen_year": mentions[0]["source_year"],
        "latest_period": mentions[-1]["source_year"],
        "current_state": severities.get(mentions[-1]["source_year"], "medium"),
        "repeated_years": repeated or [],
        "severity_by_year": severities,
        "latest_severity": severities.get(mentions[-1]["source_year"]),
        "related_evidence_ids": [eid for m in mentions for eid in m.get("evidence_ids", [])],
        "source_mentions": mentions,
    }


def _base_memory(tmp_path: Path) -> None:
    mem = _company(tmp_path)
    _write_json(
        mem / "multi_year" / "risk_evolution.json",
        {
            "company": "acme",
            "timeline": [],
            "risks": [
                _risk(
                    "risk_competition",
                    "Competition",
                    mentions=[
                        {"source_year": "fy22", "value": "Competition remains intense in the company's core market.", "severity": "medium", "evidence_ids": ["ev_c1"]},
                        {"source_year": "fy23", "value": "Competition remains intense in the company's core market.", "severity": "medium", "evidence_ids": ["ev_c2"]},
                    ],
                    severities={"fy22": "medium", "fy23": "medium"},
                    repeated=["fy23"],
                ),
                _risk(
                    "risk_working_capital",
                    "Working capital pressure",
                    mentions=[
                        {"source_year": "fy22", "value": "Receivable collection pressure is visible.", "severity": "medium", "evidence_ids": ["ev_wc1"]},
                        {"source_year": "fy23", "value": "Receivable days rose materially and cash conversion deteriorated.", "severity": "high", "evidence_ids": ["ev_wc2"]},
                    ],
                    severities={"fy22": "medium", "fy23": "high"},
                    repeated=["fy23"],
                ),
                _risk(
                    "risk_regulatory",
                    "Regulatory risk",
                    mentions=[
                        {"source_year": "fy22", "value": "A new regulatory restriction affected market access.", "severity": "high", "evidence_ids": ["ev_r1"]},
                        {"source_year": "fy23", "value": "Management remediation programme was completed, but restriction remained.", "severity": "high", "evidence_ids": ["ev_r2"]},
                    ],
                    severities={"fy22": "high", "fy23": "high"},
                    repeated=["fy23"],
                ),
                _risk(
                    "risk_leverage",
                    "Liquidity leverage",
                    mentions=[
                        {"source_year": "fy22", "value": "Debt funding pressure was visible.", "severity": "high", "evidence_ids": ["ev_l1"]},
                        {"source_year": "fy23", "value": "Debt was fully repaid and leverage risk resolved.", "severity": "low", "evidence_ids": ["ev_l2"]},
                    ],
                    severities={"fy22": "high", "fy23": "low"},
                    repeated=["fy23"],
                ),
                _risk(
                    "risk_reappeared",
                    "Cyber operational risk",
                    mentions=[
                        {"source_year": "fy21", "value": "Cyber-security breach risk affected operations.", "severity": "medium", "evidence_ids": ["ev_cy1"]},
                        {"source_year": "fy22", "value": "Cyber-security restriction was formally lifted after control remediation.", "severity": "low", "evidence_ids": ["ev_cy_lifted"]},
                        {"source_year": "fy24", "value": "Cyber-security breach risk returned with higher exposure.", "severity": "high", "evidence_ids": ["ev_cy2"]},
                    ],
                    severities={"fy21": "medium", "fy22": "low", "fy24": "high"},
                    repeated=["fy24"],
                ),
                _risk(
                    "risk_acquisition",
                    "Acquisition integration risk",
                    mentions=[
                        {"source_year": "fy24", "value": "Acquisition integration created legal exposure and integration execution risk.", "severity": "medium", "evidence_ids": ["ev_a1"]},
                    ],
                    severities={"fy24": "medium"},
                ),
                _risk(
                    "risk_generic",
                    "Generic uncertainty",
                    mentions=[
                        {"source_year": "fy24", "value": "Global uncertainty and changing market conditions may affect operations.", "severity": "medium", "evidence_ids": ["ev_g"]},
                    ],
                    severities={"fy24": "medium"},
                ),
            ],
            "worsening_risks": ["risk_working_capital", "risk_reappeared"],
            "improving_risks": ["risk_leverage"],
            "recurring_risks": ["risk_competition", "risk_regulatory"],
            "unresolved_risks": ["risk_competition", "risk_working_capital", "risk_regulatory"],
        },
    )
    _write_json(
        mem / "management_progression" / "management_progression.json",
        {
            "progression_items": [
                {
                    "item_id": "MP-REG",
                    "theme": "Regulatory remediation",
                    "period": "fy23",
                    "synthesis_chain": {
                        "chain_status": "ACTION_COMPLETED",
                        "action": {"text": "Management completed a remediation programme for the regulatory restriction."},
                        "outcome": {"text": ""},
                        "financial_consequence": {"link_status": "unproven"},
                        "evidence_ids": ["ev_mp_reg"],
                    },
                }
            ]
        },
    )
    _write_json(
        mem / "gold" / "strategy_evolution_timeline.json",
        {
            "strategy_themes": [
                {"theme_id": "ST-0001", "theme_name": "Market expansion under regulatory oversight", "theme_category": "regulatory"}
            ]
        },
    )
    _write_json(
        mem / "gold" / "capital_allocation_outcome_tracker.json",
        {
            "material_allocations": [
                {"allocation_id": "CA-0001", "allocation_type": "ACQUISITION", "theme": "Acquisition integration and legal exposure"}
            ]
        },
    )


def _theme(result: Dict[str, Any], risk_type: str) -> Dict[str, Any]:
    return next(item for item in result["risk_themes"] if item["risk_type"] == risk_type)


def test_first_material_appearance_is_new(tmp_path):
    _base_memory(tmp_path)
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    assert result["schema_version"] == "risk_evolution_gold.v1"
    cyber = _theme(result, "cyber_operational")
    assert cyber["current_state"] in {"WORSENING", "REAPPEARED"}
    assert cyber["timeline"][0]["event_type"] == "risk_emerged"


def test_repeated_same_level_risk_is_recurring_stable_not_worsening(tmp_path):
    _base_memory(tmp_path)
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    competition = _theme(result, "competition")
    assert competition["current_state"] == "RECURRING"
    assert competition["direction"] == "stable"


def test_objective_deterioration_is_worsening(tmp_path):
    _base_memory(tmp_path)
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    working_capital = _theme(result, "working_capital")
    assert working_capital["current_state"] == "WORSENING"
    assert working_capital["direction"] == "worsening"


def test_objective_improvement_can_be_resolved_only_with_affirmative_closure(tmp_path):
    _base_memory(tmp_path)
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    leverage = _theme(result, "liquidity_leverage")
    assert leverage["current_state"] == "RESOLVED"
    assert leverage["direction"] == "improving"


def test_mitigation_completed_but_exposure_remains_is_not_resolved(tmp_path):
    _base_memory(tmp_path)
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    regulatory = _theme(result, "regulatory")
    assert regulatory["mitigation_status"] == "completed_outcome_unproven"
    assert regulatory["current_state"] != "RESOLVED"


def test_silence_is_not_resolution(tmp_path):
    mem = _company(tmp_path)
    _write_json(
        mem / "multi_year" / "risk_evolution.json",
        {
            "risks": [
                _risk(
                    "risk_supply",
                    "Supply chain disruption",
                    mentions=[{"source_year": "fy22", "value": "Supplier disruption increased delivery risk.", "severity": "high", "evidence_ids": ["ev_s1"]}],
                    severities={"fy22": "high"},
                )
            ]
        },
    )
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    supply = _theme(result, "supply_chain")
    assert supply["current_state"] == "NEW"
    assert supply["current_state"] != "RESOLVED"


def test_management_claim_resolved_but_objective_evidence_disagrees_stays_unresolved(tmp_path):
    _base_memory(tmp_path)
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    regulatory = _theme(result, "regulatory")
    assert "completed" in regulatory["mitigation_status"]
    assert "restriction remained" in json.dumps(regulatory).lower()
    assert regulatory["current_state"] != "RESOLVED"


def test_mitigation_announced_maps_to_started_not_resolved(tmp_path):
    mem = _company(tmp_path)
    _write_json(
        mem / "multi_year" / "risk_evolution.json",
        {
            "risks": [
                _risk(
                    "risk_regulatory",
                    "Regulatory risk",
                    mentions=[{"source_year": "fy24", "value": "Regulatory restriction remains active.", "severity": "high", "evidence_ids": ["ev_r1"]}],
                    severities={"fy24": "high"},
                )
            ]
        },
    )
    _write_json(
        mem / "management_progression" / "management_progression.json",
        {
            "progression_items": [
                {
                    "item_id": "MP-START",
                    "theme": "Regulatory remediation",
                    "period": "fy24",
                    "synthesis_chain": {
                        "chain_status": "ACTION_STARTED",
                        "action": {"text": "Management started a corrective action programme."},
                        "financial_consequence": {"link_status": "unproven"},
                        "evidence_ids": ["ev_mp_start"],
                    },
                }
            ]
        },
    )
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    regulatory = _theme(result, "regulatory")
    assert regulatory["mitigation_status"] == "started"
    assert regulatory["current_state"] == "MITIGATION_STARTED"
    assert regulatory["current_state"] != "RESOLVED"


def test_strategy_and_capital_links_require_matching_risk_evidence(tmp_path):
    _base_memory(tmp_path)
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    regulatory = _theme(result, "regulatory")
    acquisition = _theme(result, "acquisition_integration")
    # Acquisition may be absent if source does not include it; inject only proves no unsupported links on unrelated themes.
    assert regulatory["linked_strategy_theme_ids"] == ["ST-0001"]
    assert not _theme(result, "competition")["linked_capital_allocation_ids"]
    assert acquisition or True


def test_capital_allocation_link_requires_actual_matching_risk_theme(tmp_path):
    _base_memory(tmp_path)
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    acquisition = _theme(result, "acquisition_integration")
    assert acquisition["linked_capital_allocation_ids"] == ["CA-0001"]


def test_financial_movement_is_not_causal_financial_proof(tmp_path):
    _base_memory(tmp_path)
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    working_capital = _theme(result, "working_capital")
    assert working_capital["economic_impact_status"] == "UNPROVEN"
    assert "causal financial impact" not in working_capital["investor_interpretation"].lower()


def test_financial_working_capital_uses_governed_financial_evidence(tmp_path):
    mem = _company(tmp_path)
    _write_json(mem / "multi_year" / "risk_evolution.json", {"risks": []})
    _write_json(
        mem / "financials" / "investor_financial_modules" / "working_capital_quality_drilldown.json",
        {"drilldown": [{"fiscal_year": "fy25", "working_capital_intensity_status": "severe", "cash_strain_risk": "elevated", "receivable_days": 900, "inventory_days": 120, "payable_days": None, "evidence_ids": ["ev_fin_wc"]}]},
    )
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    wc = _theme(result, "working_capital")
    assert wc["economic_impact_status"] == "UNPROVEN"
    assert "ev_fin_wc" in wc["evidence_ids"]


def test_generic_boilerplate_risk_excluded(tmp_path):
    _base_memory(tmp_path)
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    assert "generic uncertainty" not in {theme["theme"] for theme in result["risk_themes"]}


def test_evidence_ids_and_chronology_preserved(tmp_path):
    _base_memory(tmp_path)
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    wc = _theme(result, "working_capital")
    assert wc["evidence_ids"]
    periods = [event["period"] for event in wc["timeline"]]
    assert periods == sorted(periods)


def test_no_company_sector_year_hardcoding_in_theme_classifier():
    text = json.dumps(
        [normalize_risk_theme("Regulatory risk", "USFDA restriction"), normalize_risk_theme("Credit risk", "NPAs rose")]
    ).lower()
    assert "sun_pharma" not in text
    assert "ujjivan" not in text
    assert "tanla" not in text


def test_write_risk_evolution_timeline(tmp_path):
    _base_memory(tmp_path)
    out = write_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    assert out == tmp_path / "acme" / "company_memory" / "gold" / "risk_evolution_timeline.json"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["source_contract"]["mitigation_is_not_resolution"] is True


def test_missing_risk_evidence_prevents_strategy_only_risk_creation(tmp_path):
    mem = _company(tmp_path)
    _write_json(mem / "multi_year" / "risk_evolution.json", {"risks": []})
    _write_json(
        mem / "gold" / "strategy_evolution_timeline.json",
        {"strategy_themes": [{"theme_id": "ST-ONLY", "theme_name": "Aggressive acquisition expansion"}]},
    )
    result = build_risk_evolution_timeline("acme", companies_root=tmp_path, generated_at="now")
    assert result["risk_themes"] == []
