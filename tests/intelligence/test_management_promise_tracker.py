"""Regression tests for the Management Promise Tracker Gold layer."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from intelligence.management_promises.builder import build_management_promise_tracker
from intelligence.management_promises.classifier import classify_promise_type, is_material_promise
from intelligence.management_promises.resolver import (
    build_investor_interpretation,
    resolve_current_status,
    resolve_execution_status,
    resolve_financial_link_status,
    resolve_outcome_status,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _item(
    *,
    item_id: str = "MP-0001-test",
    theme: str = "Expand manufacturing capacity in India.",
    stream_types: List[str] | None = None,
    current_status: str = "in_progress",
    management_credibility_signal: str = "IN_PROGRESS",
    linked_company_model_ids: List[str] | None = None,
    events: List[Dict[str, Any]] | None = None,
    investor_implication: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "item_id": item_id,
        "theme": theme,
        "stream_types": stream_types or ["commitment"],
        "current_status": current_status,
        "management_credibility_signal": management_credibility_signal,
        "linked_company_model_ids": linked_company_model_ids or ["advanced_manufacturing_capacity"],
        "events": events or [],
        "investor_implication": investor_implication,
    }


def _commitment_event(period: str, statement: str, target_period: str = "") -> Dict[str, Any]:
    return {
        "event_id": f"evt_{period}_commit",
        "role": "commitment",
        "event_type": "capacity_expansion",
        "source_period": period,
        "event_period": period,
        "target_period": target_period,
        "statement_text": statement,
        "action_taken": "",
        "operational_outcome": "",
        "financial_or_business_outcome": "",
        "verification_status": "unresolved",
        "evidence": [],
    }


def _completion_event(period: str, action: str, financial_outcome: str = "") -> Dict[str, Any]:
    return {
        "event_id": f"evt_{period}_complete",
        "role": "completion",
        "event_type": "capacity_expansion",
        "source_period": period,
        "event_period": period,
        "target_period": "",
        "statement_text": "",
        "action_taken": action,
        "operational_outcome": "operational",
        "financial_or_business_outcome": financial_outcome,
        "verification_status": "verified",
        "evidence": [{"evidence_id": f"ev_{period}_001", "source_artifact": "test"}],
    }


def _outcome_event(period: str, financial_outcome: str, verification: str = "verified") -> Dict[str, Any]:
    return {
        "event_id": f"evt_{period}_outcome",
        "role": "outcome",
        "event_type": "capacity_expansion",
        "source_period": period,
        "event_period": period,
        "target_period": "",
        "statement_text": "",
        "action_taken": "",
        "operational_outcome": financial_outcome,
        "financial_or_business_outcome": financial_outcome,
        "verification_status": verification,
        "evidence": [],
    }


def _progression_bundle(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "progression_items": items,
        "management_thesis_chains": [],
        "measurable_commitments": [],
        "contradiction_signals": [],
        "coverage_status": "supported",
    }


# ── T1: numeric target met → ACHIEVED ─────────────────────────────────────────

def test_numeric_promise_with_financial_outcome_maps_to_achieved():
    item = _item(
        current_status="delivered",
        management_credibility_signal="DELIVERED",
        events=[
            _commitment_event("fy22", "Build 3 new manufacturing facilities by FY24.", "fy24"),
            _completion_event("fy24", "3 manufacturing facilities commissioned.", "Revenue grew 15%; capacity utilisation reached 82%."),
        ],
    )
    exec_status = resolve_execution_status(item)
    fin_link = resolve_financial_link_status(item)
    outcome = resolve_outcome_status(item, execution_status=exec_status, financial_link_status=fin_link)
    assert exec_status == "ACTION_COMPLETED"
    assert outcome == "ACHIEVED"


# ── T2: target-period slip → DELAYED ──────────────────────────────────────────

def test_commitment_with_target_period_not_yet_met_maps_to_delayed():
    item = _item(
        current_status="in_progress",
        management_credibility_signal="IN_PROGRESS",
        events=[
            _commitment_event("fy21", "Launch specialty biosimilar by FY23.", "fy23"),
            {
                "event_id": "evt_fy24_action",
                "role": "action",
                "event_type": "product_launch",
                "source_period": "fy24",
                "event_period": "fy24",
                "target_period": "fy23",
                "statement_text": "",
                "action_taken": "Biosimilar trials initiated; commercialisation ongoing.",
                "operational_outcome": "",
                "financial_or_business_outcome": "",
                "verification_status": "partially_verified",
                "evidence": [],
            },
        ],
    )
    exec_status = resolve_execution_status(item)
    fin_link = resolve_financial_link_status(item)
    outcome = resolve_outcome_status(item, execution_status=exec_status, financial_link_status=fin_link)
    current = resolve_current_status(item, outcome, exec_status)
    assert exec_status == "ACTION_STARTED"
    assert current == "DELAYED"


# ── T3: partial delivery → PARTIALLY_ACHIEVED ─────────────────────────────────

def test_partial_delivery_maps_to_partially_achieved():
    item = _item(
        current_status="partially_delivered",
        management_credibility_signal="PARTIALLY_DELIVERED",
        events=[
            _commitment_event("fy22", "Expand to 5 new geographies by FY24.", "fy24"),
            _completion_event("fy24", "Expanded to 3 new geographies; 2 remain."),
        ],
    )
    exec_status = resolve_execution_status(item)
    fin_link = resolve_financial_link_status(item)
    outcome = resolve_outcome_status(item, execution_status=exec_status, financial_link_status=fin_link)
    assert outcome == "PARTIALLY_ACHIEVED"


# ── T4: explicit contradiction → MISSED ───────────────────────────────────────

def test_contradicted_signal_maps_to_missed():
    item = _item(
        current_status="failed",
        management_credibility_signal="CONTRADICTED",
        events=[
            _commitment_event("fy20", "Maintain debt-free balance sheet."),
            {
                "event_id": "evt_fy23_contra",
                "role": "contradiction",
                "event_type": "capital_allocation",
                "source_period": "fy23",
                "event_period": "fy23",
                "target_period": "",
                "statement_text": "Company raised ₹2,000 cr debt in FY23.",
                "action_taken": "Debt raised despite earlier commitment.",
                "operational_outcome": "",
                "financial_or_business_outcome": "Debt now on balance sheet: contradicts earlier statement.",
                "verification_status": "contradicted",
                "evidence": [],
            },
        ],
    )
    exec_status = resolve_execution_status(item)
    fin_link = resolve_financial_link_status(item)
    outcome = resolve_outcome_status(item, execution_status=exec_status, financial_link_status=fin_link)
    assert outcome == "MISSED"


# ── T5: no later evidence → UNVERIFIED (not MISSED) ──────────────────────────

def test_no_later_evidence_resolves_to_unverified_not_missed():
    item = _item(
        current_status="announced",
        management_credibility_signal="UNABLE_TO_VERIFY",
        events=[
            _commitment_event("fy24", "Achieve 35% reduction in Scope 1+2 emissions by FY30.", "fy30"),
        ],
    )
    exec_status = resolve_execution_status(item)
    fin_link = resolve_financial_link_status(item)
    outcome = resolve_outcome_status(item, execution_status=exec_status, financial_link_status=fin_link)
    current = resolve_current_status(item, outcome, exec_status)
    assert outcome == "UNVERIFIED"
    assert current != "MISSED"
    assert current != "ACHIEVED"


# ── T6: strategic reversal is not automatic MISSED ────────────────────────────

def test_strategy_reversal_context_does_not_become_automatic_missed():
    # A company moved from generic to specialty focus — this is a strategy change, not a failure
    item = _item(
        current_status="in_progress",
        management_credibility_signal="IN_PROGRESS",
        events=[
            _commitment_event("fy20", "Continue disciplined identification of future R&D projects for US generics."),
            {
                "event_id": "evt_fy23_action",
                "role": "action",
                "event_type": "strategic_change",
                "source_period": "fy23",
                "event_period": "fy23",
                "target_period": "",
                "statement_text": "",
                "action_taken": "Strategic shift to focus on specialty and branded business; generics R&D rationalised.",
                "operational_outcome": "",
                "financial_or_business_outcome": "",
                "verification_status": "partially_verified",
                "evidence": [],
            },
        ],
    )
    exec_status = resolve_execution_status(item)
    fin_link = resolve_financial_link_status(item)
    outcome = resolve_outcome_status(item, execution_status=exec_status, financial_link_status=fin_link)
    # Strategic reversal via ACTION_STARTED + IN_PROGRESS should not be MISSED
    assert outcome != "MISSED"
    assert exec_status == "ACTION_STARTED"


# ── T7: completion ≠ economic success ─────────────────────────────────────────

def test_action_completed_without_financial_link_is_not_achieved():
    item = _item(
        current_status="delivered",
        management_credibility_signal="DELIVERED",
        events=[
            _commitment_event("fy22", "Commission independent customer-service assessment."),
            _completion_event("fy23", "Independent assessment commissioned and completed.", ""),
        ],
    )
    exec_status = resolve_execution_status(item)
    fin_link = resolve_financial_link_status(item)
    outcome = resolve_outcome_status(item, execution_status=exec_status, financial_link_status=fin_link)
    assert exec_status == "ACTION_COMPLETED"
    assert fin_link == "INSUFFICIENT_EVIDENCE"
    assert outcome == "UNVERIFIED"
    assert outcome != "ACHIEVED"


# ── T8: operating outcome without financial causal proof stays unproven ────────

def test_operating_outcome_without_financial_causation_stays_insufficient():
    item = _item(
        current_status="delivered",
        management_credibility_signal="DELIVERED",
        events=[
            _commitment_event("fy22", "Build data platform to improve Product Per Customer."),
            {
                **_completion_event("fy24", "Data platform launched and operational.", ""),
                "financial_or_business_outcome": "There is not yet enough evidence to connect the project to a financial effect.",
            },
        ],
    )
    fin_link = resolve_financial_link_status(item)
    assert fin_link == "INSUFFICIENT_EVIDENCE"


# ── T9: repeated unverified pattern requires ≥3 promises ──────────────────────

def test_repeated_unverified_pattern_requires_multiple_promises():
    from intelligence.management_promises.builder import _build_credibility_patterns

    # Only 2 unverified — should NOT trigger the pattern
    two_promises = [
        {"current_status": "UNVERIFIED", "execution_status": "CLAIM_ONLY", "financial_link_status": "INSUFFICIENT_EVIDENCE",
         "promise_type": "OTHER", "linked_company_model_ids": []},
        {"current_status": "UNVERIFIED", "execution_status": "CLAIM_ONLY", "financial_link_status": "INSUFFICIENT_EVIDENCE",
         "promise_type": "OTHER", "linked_company_model_ids": []},
    ]
    patterns = _build_credibility_patterns(two_promises)
    pattern_ids = [p["pattern_id"] for p in patterns]
    assert "frequent_unverified_commitments" not in pattern_ids

    # 3+ unverified — should trigger the pattern
    three_promises = two_promises + [
        {"current_status": "UNVERIFIED", "execution_status": "CLAIM_ONLY", "financial_link_status": "INSUFFICIENT_EVIDENCE",
         "promise_type": "OTHER", "linked_company_model_ids": []},
    ]
    patterns = _build_credibility_patterns(three_promises)
    pattern_ids = [p["pattern_id"] for p in patterns]
    assert "frequent_unverified_commitments" in pattern_ids


# ── T10: trivial management language is excluded from Gold ────────────────────

def test_trivial_language_excluded_from_gold():
    trivial_items = [
        _item(theme="Aim to keep annual contributions to the gratuity fund relatively stable.", linked_company_model_ids=[]),
        _item(theme="Continue to pay pensions to employees who had already retired.", linked_company_model_ids=[]),
        _item(theme="We remain committed to excellence in customer service.", linked_company_model_ids=[]),
        _item(theme="Cancer sanatorium institute Wadala Mumbai support ongoing.", linked_company_model_ids=[]),
    ]
    for item in trivial_items:
        assert not is_material_promise(item), f"Trivial item incorrectly passed materiality: {item['theme'][:80]}"


# ── T11: evidence IDs are preserved ──────────────────────────────────────────

def test_evidence_ids_are_preserved_in_promise_records():
    from intelligence.management_promises.resolver import extract_evidence_ids

    item = _item(
        events=[
            {
                **_commitment_event("fy22", "Build facility."),
                "evidence": [
                    {"evidence_id": "ev_fy22_001", "source_artifact": "projects_registry.json"},
                    {"evidence_id": "ev_fy22_002", "source_artifact": "pcim_v1.json"},
                ],
            },
            {
                **_completion_event("fy24", "Facility commissioned."),
                "evidence": [
                    {"evidence_id": "ev_fy24_003", "source_artifact": "projects_registry.json"},
                ],
            },
        ]
    )
    ids = extract_evidence_ids(item)
    assert "ev_fy22_001" in ids
    assert "ev_fy22_002" in ids
    assert "ev_fy24_003" in ids
    assert len(set(ids)) == len(ids)  # no duplicates


# ── T12: chronological integrity — later_evidence is post-commitment ──────────

def test_later_evidence_is_chronologically_ordered_after_commitment():
    from intelligence.management_promises.resolver import extract_later_evidence

    item = _item(
        events=[
            _commitment_event("fy22", "Promise made."),
            _completion_event("fy23", "Action taken post-promise."),
            _completion_event("fy24", "Further completion."),
        ]
    )
    evidence = extract_later_evidence(item)
    periods = [e["period"] for e in evidence]
    assert periods == sorted(periods), "later_evidence should be in chronological order"


# ── T13: no company/sector/year hardcoding ────────────────────────────────────

def test_builder_works_for_synthetic_company_without_hardcoding(tmp_path):
    # Create a minimal management_progression artifact
    mp_dir = tmp_path / "synthetic_co" / "company_memory" / "management_progression"
    mp_dir.mkdir(parents=True)
    progression = {
        "coverage_status": "supported",
        "progression_items": [
            {
                "item_id": "MP-0001-expand_into_new_markets",
                "theme": "Expand into new international markets with revenue growth target.",
                "stream_types": ["commitment"],
                "current_status": "in_progress",
                "management_credibility_signal": "IN_PROGRESS",
                "linked_company_model_ids": ["core_revenue_engine"],
                "events": [
                    _commitment_event("fy23", "We will expand into 3 new international markets by FY25.", "fy25"),
                    {
                        **_commitment_event("fy24", ""),
                        "role": "action",
                        "action_taken": "Entered 2 new markets.",
                        "statement_text": "",
                        "verification_status": "partially_verified",
                    },
                ],
                "investor_implication": None,
            },
        ],
        "management_thesis_chains": [],
        "measurable_commitments": [],
        "contradiction_signals": [],
    }
    (mp_dir / "management_progression.json").write_text(json.dumps(progression), encoding="utf-8")

    result = build_management_promise_tracker("synthetic_co", companies_root=tmp_path)

    assert result["company_slug"] == "synthetic_co"
    assert len(result["material_promises"]) == 1
    p = result["material_promises"][0]
    assert p["promise_type"] in {"GROWTH_TARGET", "MARKET_EXPANSION", "CAPACITY", "OTHER"}
    assert p["current_status"] in {"UNVERIFIED", "DELAYED", "PARTIALLY_ACHIEVED"}
    # No hardcoded company names in the output
    artifact_text = json.dumps(result)
    for hardcoded in ("sun_pharma", "ujjivan", "tanla", "pharma", "banking"):
        assert hardcoded not in artifact_text.lower(), f"Hardcoded term '{hardcoded}' found"
