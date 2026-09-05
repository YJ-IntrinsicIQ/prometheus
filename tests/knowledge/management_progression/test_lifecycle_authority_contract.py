"""
Lifecycle authority contract tests.

Invariants:
  1. MC (management_commitments) is NOT a lifecycle authority.
     Its top-level `status` is always "Unable To Verify".
  2. MP (management_progression) is the sole lifecycle authority.
     It derives status from event roles (action/milestone/completion/outcome)
     sourced from projects, capacity, commentary — NOT from MC's status field.
  3. Gold derives lifecycle from MP event roles, not from MC.
  4. No path exists where MC status directly promotes Gold or Ask to Delivered/In Progress.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from knowledge.company_memory.management_commitments import (
    _build_commitment_record,
    _commitment_fingerprint,
    _build_group_from_candidate,
)
from knowledge.management_progression.producer import ManagementProgressionProducer
from intelligence.management_promises.resolver import (
    resolve_execution_status,
    resolve_outcome_status,
    resolve_current_status,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _candidate(statement: str, period: str, event_type: str = "announcement", status: str = "Announced") -> Dict[str, Any]:
    return {
        "period": period,
        "original_statement": statement,
        "normalized_commitment": statement.lower().strip("."),
        "normalized_source_statement": statement.lower().strip("."),
        "topic": "Product launch",
        "category": "Product",
        "priority": "medium",
        "expected_timeframe": None,
        "sort_key": period,
        "source_item_id": f"item_{period}",
        "source_artifact": "company_intelligence.json",
        "source_reference": {"source_artifact": "company_intelligence.json", "period": period},
        "supporting_evidence": [{"period": period, "event_type": event_type, "status": status,
                                  "statement": statement, "source_reference": {"source_artifact": "company_intelligence.json", "period": period}}],
        "commitment_role": "announcement",
        "confidence": "medium",
        "actor_type": "company",
        "statement_type": "commitment",
        "semantic_quality": {"eligibility": "eligible"},
        "status_hint": None,
    }


def _follow_up_candidate(statement: str, period: str, event_type: str = "progress_update", status: str = "In Progress") -> Dict[str, Any]:
    c = _candidate(statement, period, event_type, status)
    c["commitment_role"] = "follow_up"
    return c


def _group_with_follow_up(announcement: str, follow_up: str, ann_period: str = "fy20", fu_period: str = "fy22") -> Dict[str, Any]:
    ann = _candidate(announcement, ann_period)
    group = _build_group_from_candidate(ann)
    fu = _follow_up_candidate(follow_up, fu_period)
    group["updates"].append(fu)
    group["supporting_evidence"].extend(fu["supporting_evidence"])
    group["periods_seen"].append(fu_period)
    return group


# ── Test 1: MC status is always "Unable To Verify" ───────────────────────────

def test_mc_status_always_unable_to_verify_with_no_follow_up():
    group = _build_group_from_candidate(_candidate("Evaluate Nafamostat for COVID-19 treatment", "fy20"))
    record = _build_commitment_record("sun_pharma", group, "MC-0001")
    assert record["status"] == "Unable To Verify", "MC must not claim lifecycle truth"


def test_mc_status_always_unable_to_verify_with_progress_follow_up():
    """Even when candidate evidence contains a progress_update, MC must output UTV."""
    group = _group_with_follow_up(
        "Build pipeline of branded generics",
        "R&D expenditure totalling Rs 193 billion indicating continued investment",
    )
    record = _build_commitment_record("sun_pharma", group, "MC-0013")
    assert record["status"] == "Unable To Verify", (
        "MC must not promote 'In Progress' from candidate follow-up evidence"
    )


def test_mc_status_always_unable_to_verify_with_delivery_keyword():
    """Even when follow-up text contains 'operational' or 'launched', MC must output UTV."""
    group = _group_with_follow_up(
        "Platform rollout for enterprise clients",
        "Use of AI platforms has driven measurable operational improvements and launched across all key accounts",
    )
    record = _build_commitment_record("tanla", group, "MC-0012")
    assert record["status"] == "Unable To Verify", (
        "MC must not promote 'Delivered' from text-pattern matching on 'operational'"
    )


def test_mc_lifecycle_authority_field():
    group = _build_group_from_candidate(_candidate("Expand specialty business in Japan", "fy21"))
    record = _build_commitment_record("sun_pharma", group, "MC-0006")
    assert record.get("lifecycle_authority") == "management_progression"


def test_mc_commitment_fingerprint_is_stable():
    group = _build_group_from_candidate(_candidate("Ramp-up ILUMYA prescriptions in Japan", "fy22"))
    r1 = _build_commitment_record("sun_pharma", group, "MC-0001")
    r2 = _build_commitment_record("sun_pharma", group, "MC-0099")  # different ordinal
    assert r1["commitment_fingerprint"] == r2["commitment_fingerprint"], (
        "Fingerprint must be stable regardless of ordinal MC-XXXX id"
    )


def test_mc_fingerprint_differs_by_company():
    group = _build_group_from_candidate(_candidate("Expand capacity", "fy21"))
    r_sun = _build_commitment_record("sun_pharma", group, "MC-0001")
    r_tanla = _build_commitment_record("tanla", group, "MC-0001")
    assert r_sun["commitment_fingerprint"] != r_tanla["commitment_fingerprint"]


def test_mc_fingerprint_differs_by_period():
    g1 = _build_group_from_candidate(_candidate("Expand capacity", "fy21"))
    g2 = _build_group_from_candidate(_candidate("Expand capacity", "fy22"))
    r1 = _build_commitment_record("sun_pharma", g1, "MC-0001")
    r2 = _build_commitment_record("sun_pharma", g2, "MC-0001")
    assert r1["commitment_fingerprint"] != r2["commitment_fingerprint"]


# ── Test 2: MP cannot derive "delivered" from commitment-only input ───────────

def test_mp_commitment_only_event_yields_announced():
    """MP must not classify a commitment as delivered/in_progress from MC-only events."""
    from knowledge.management_progression.producer import _derive_current_status
    events = [{"role": "commitment", "verification_status": "unresolved"}]
    assert _derive_current_status(events) == "announced"


def test_mp_commitment_only_event_with_partially_verified_still_announced():
    """Even if commitment event has partially_verified, MP must return announced (no action events)."""
    from knowledge.management_progression.producer import _derive_current_status
    events = [{"role": "commitment", "verification_status": "partially_verified"}]
    assert _derive_current_status(events) == "announced"


def test_mp_requires_action_role_for_in_progress():
    from knowledge.management_progression.producer import _derive_current_status
    events = [
        {"role": "commitment", "verification_status": "unresolved"},
        {"role": "action", "verification_status": "partially_verified"},
    ]
    assert _derive_current_status(events) == "in_progress"


def test_mp_requires_completion_role_for_delivered():
    from knowledge.management_progression.producer import _derive_current_status
    events = [
        {"role": "commitment", "verification_status": "unresolved"},
        {"role": "completion", "verification_status": "verified"},
    ]
    assert _derive_current_status(events) == "delivered"


# ── Test 3: Gold cannot contradict MP ────────────────────────────────────────

def test_gold_claim_only_when_mp_announced():
    """If MP has only commitment events (announced), Gold execution status must be CLAIM_ONLY."""
    mp_item = {
        "events": [{"role": "commitment", "verification_status": "unresolved",
                    "statement_text": "Evaluate Nafamostat for COVID-19", "source_period": "fy20"}],
        "current_status": "announced",
        "management_credibility_signal": "UNABLE_TO_VERIFY",
    }
    exec_status = resolve_execution_status(mp_item)
    assert exec_status == "CLAIM_ONLY", "Gold must not claim action when MP has no action events"


def test_gold_cannot_deliver_when_mp_announced():
    """Gold outcome_status must be UNVERIFIED when MP is announced (no completion/outcome)."""
    mp_item = {
        "events": [{"role": "commitment", "verification_status": "unresolved",
                    "statement_text": "Build platform rollout", "source_period": "fy21"}],
        "current_status": "announced",
        "management_credibility_signal": "UNABLE_TO_VERIFY",
    }
    exec_status = resolve_execution_status(mp_item)
    outcome_status = resolve_outcome_status(mp_item, execution_status=exec_status,
                                            financial_link_status="INSUFFICIENT_EVIDENCE")
    assert outcome_status == "UNVERIFIED", "Gold must not claim ACHIEVED when MP is announced"


def test_gold_current_status_unverified_when_mp_announced():
    mp_item = {
        "events": [{"role": "commitment", "verification_status": "unresolved",
                    "statement_text": "Grow specialty business", "source_period": "fy20"}],
        "current_status": "announced",
        "management_credibility_signal": "UNABLE_TO_VERIFY",
    }
    exec_status = resolve_execution_status(mp_item)
    outcome_status = resolve_outcome_status(mp_item, execution_status=exec_status,
                                            financial_link_status="INSUFFICIENT_EVIDENCE")
    current = resolve_current_status(mp_item, outcome_status, exec_status)
    assert current == "UNVERIFIED"


# ── Test 4: MC-0004 specific (Nafamostat COVID) ───────────────────────────────

def test_mc0004_nafamostat_is_unable_to_verify():
    """MC-0004 canonical: announcement only, no confirmed follow-up → UTV."""
    group = _build_group_from_candidate(
        _candidate("Evaluate potential of Nafamostat Mesilate and AQCH for COVID-19 treatment", "fy20")
    )
    record = _build_commitment_record("sun_pharma", group, "MC-0004")
    assert record["status"] == "Unable To Verify"
    assert len(record["supporting_evidence"]) == 1  # announcement only


# ── Test 5: MC-0013 specific (Build pipeline) ─────────────────────────────────

def test_mc0013_pipeline_with_rd_follow_up_is_still_utv():
    """MC-0013: R&D expenditure follow-ups are candidate evidence, not lifecycle proof."""
    group = _group_with_follow_up(
        "Build a strong pipeline of branded generics, pure generics and specialty products",
        "Cumulative R&D expenditure to date is Rs 193+ billion; R&D spend of approximately 7.6% in FY21",
        ann_period="fy21",
        fu_period="fy21",
    )
    record = _build_commitment_record("sun_pharma", group, "MC-0013")
    assert record["status"] == "Unable To Verify", "R&D expenditure fact must not promote 'In Progress'"


# ── Test 6: Topic equality cannot establish delivery ─────────────────────────

def test_same_topic_cannot_yield_delivered():
    """Two items sharing only topic='Platform rollout' cannot result in Delivered MC status."""
    group = _group_with_follow_up(
        "Platform rollout for enterprise clients",
        "Owning infrastructure core is structural advantage: once platforms are built, marginal cost is near zero",
        ann_period="fy24",
        fu_period="fy26",
    )
    record = _build_commitment_record("tanla", group, "MC-0012")
    # Regardless of whether items merged (same topic), MC never asserts Delivered
    assert record["status"] == "Unable To Verify"
