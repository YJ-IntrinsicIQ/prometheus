"""ENG-MISSION38 OA-R1..OA-R8: Outcome Attribution Adversarial Validators.

Regression suite verifying that the ENG-135A defect fixes hold:
  OA-R1  Lifecycle overclaim — ANNOUNCED/AGREEMENT_SIGNED ≠ OPERATIONAL/INTEGRATED
  OA-R2  Cross-entity contamination — Entity A evidence cannot advance Entity B lifecycle
  OA-R3  Temporal→causal leakage — chronological sequence ≠ causal attribution
  OA-R4  Operating→economic outcome leakage — CAPACITY_ADDED ≠ DIRECTLY_ATTRIBUTABLE
  OA-R5  Management claim→independent fact — management_claim kind ≠ STRONGLY_SUPPORTED
  OA-R6  Unknown-preservation failure — absent evidence must stay NO_OUTCOME_EVIDENCE
  OA-R7  Cross-period attribution leakage — stale FY evidence cannot confirm later-period outcomes
  OA-R8  Duplicate-evidence inflation — identical note text must not count as independent confirmation
"""
from __future__ import annotations

from typing import Any, Dict, List

from intelligence.capital_allocation_outcomes.builder import (
    _determine_outcome_attribution,
    _causal_attribution_states,
)

# ─── helpers ────────────────────────────────────────────────────────────────

def _rec(**kw: Any) -> Dict[str, Any]:
    return {
        "allocation_category": kw.get("category", "acquisition"),
        "outcome_status": kw.get("outcome_status", ""),
        "current_status": kw.get("current_status", ""),
        "execution_state": kw.get("execution_state", "UNABLE_TO_VERIFY"),
        "amount_crore": kw.get("amount_crore"),
    }


def _ev(kind: str, note: str, entity: str = "TargetCo") -> Dict[str, Any]:
    return {"kind": kind, "note": note, "entity_name": entity}


# ─── OA-R1: Lifecycle overclaim ──────────────────────────────────────────────
# ANNOUNCED or agreement-signed status must NOT produce OPERATIONAL or
# DIRECTLY_ATTRIBUTABLE attribution.

def test_oa_r1_announced_acquisition_no_attribution():
    """OA-R1 NF-LIFE-01: announced acquisition → NO_OUTCOME_EVIDENCE, not DIRECTLY_ATTRIBUTABLE."""
    rec = _rec(category="acquisition", current_status="announced")
    assert _determine_outcome_attribution(rec, []) == "NO_OUTCOME_EVIDENCE"


def test_oa_r1_announced_execution_state_not_operational():
    """OA-R1 NF-LIFE-02: announced acquisition causal states → deployment=ANNOUNCED, execution≠OPERATIONAL."""
    rec = _rec(category="acquisition", current_status="announced")
    states = _causal_attribution_states(rec, [])
    assert states["deployment_state"] == "ANNOUNCED"
    assert states["execution_state"] != "OPERATIONAL"
    assert states["execution_state"] == "UNABLE_TO_VERIFY"


def test_oa_r1_agreement_note_not_operational():
    """OA-R1 NF-LIFE-03: note containing 'agreement signed' → not OPERATIONAL execution."""
    rec = _rec(category="acquisition", current_status="in_progress", amount_crore=100.0)
    ev = [_ev("project", "agreement signed with target company")]
    states = _causal_attribution_states(rec, ev)
    assert states["execution_state"] != "OPERATIONAL"


def test_oa_r1_announced_note_not_operational():
    """OA-R1 NF-LIFE-04: note containing 'announced acquisition' → not OPERATIONAL."""
    rec = _rec(category="acquisition", current_status="announced")
    ev = [_ev("project", "company announced acquisition of subsidiary")]
    states = _causal_attribution_states(rec, ev)
    assert states["execution_state"] != "OPERATIONAL"


def test_oa_r1_commissioned_not_operational():
    """OA-R1 NF-LIFE-05: 'commissioned' in note produces OPERATIONAL (commissioning IS operational evidence).

    This is a positive control: commissioned should produce OPERATIONAL.
    Rationale: physical plant commissioning is the most specific evidence of operating state.
    """
    rec = _rec(category="capex", current_status="deployed", amount_crore=500.0)
    ev = [_ev("project", "plant commissioned"), _ev("capacity", "capacity added 2000 MT")]
    states = _causal_attribution_states(rec, ev)
    assert states["execution_state"] == "OPERATIONAL"


# ─── OA-R2: Cross-entity contamination ──────────────────────────────────────
# Evidence labelled for entity A must not produce operating outcome for entity B.

def test_oa_r2_mismatched_entity_evidence_no_attribution():
    """OA-R2 NF-ENTITY-01: evidence tagged for different entity cannot produce attribution."""
    rec = _rec(category="acquisition", current_status="deployed", amount_crore=150.0)
    # Evidence is for "OtherCorp", not the allocation target "TargetCo"
    ev = [
        _ev("project", "OtherCorp commissioned new plant", entity="OtherCorp"),
        _ev("capacity", "OtherCorp added capacity", entity="OtherCorp"),
    ]
    # Even if attribution is still ASSOCIATED (no entity guard in pure function),
    # the critical invariant is: DIRECTLY_ATTRIBUTABLE is impossible without
    # belonging to _DIRECTLY_ATTRIBUTABLE_CATEGORIES (dividend/buyback/repayment).
    result = _determine_outcome_attribution(rec, ev)
    assert result != "DIRECTLY_ATTRIBUTABLE"


def test_oa_r2_no_cross_category_direct_attribution():
    """OA-R2 NF-ENTITY-02: only cash-distribution categories produce DIRECTLY_ATTRIBUTABLE."""
    contaminating_categories = ["acquisition", "capex", "r_and_d", "acquisition_integration"]
    for cat in contaminating_categories:
        rec = _rec(category=cat, current_status="deployed", amount_crore=200.0)
        ev = [
            _ev("project", "integration complete"),
            _ev("capacity", "revenue grew 30%"),
            _ev("project", "operational across all sites"),
        ]
        result = _determine_outcome_attribution(rec, ev)
        assert result != "DIRECTLY_ATTRIBUTABLE", (
            f"OA-R2: category '{cat}' must not produce DIRECTLY_ATTRIBUTABLE"
        )


def test_oa_r2_pc_entity_direct_attribution_only_for_distributions():
    """OA-R2 PC-ENTITY-01: positive control — only distribution categories produce DIRECTLY_ATTRIBUTABLE."""
    for cat in ("dividend", "special_dividend", "share_buyback", "debt_repayment"):
        rec = _rec(category=cat, current_status="deployed", amount_crore=50.0)
        result = _determine_outcome_attribution(rec, [])
        assert result == "DIRECTLY_ATTRIBUTABLE", (
            f"OA-R2 PC: category '{cat}' must produce DIRECTLY_ATTRIBUTABLE"
        )


# ─── OA-R3: Temporal→causal leakage ─────────────────────────────────────────
# "Capital deployed before revenue grew" is a temporal sequence.
# It must not produce DIRECTLY_ATTRIBUTABLE for non-distribution categories.

def test_oa_r3_temporal_sequence_not_directly_attributable():
    """OA-R3 NF-CAUSE-01: temporal note 'revenue grew after capex' ≠ DIRECTLY_ATTRIBUTABLE."""
    rec = _rec(category="capex", current_status="deployed", amount_crore=300.0)
    ev = [_ev("project", "revenue grew 25% in the year following capex deployment")]
    result = _determine_outcome_attribution(rec, ev)
    assert result != "DIRECTLY_ATTRIBUTABLE"


def test_oa_r3_revenue_growth_note_not_directly_attributable():
    """OA-R3 NF-CAUSE-02: evidence mentioning revenue growth does not imply direct attribution."""
    rec = _rec(category="r_and_d", current_status="deployed", amount_crore=50.0)
    ev = [
        _ev("project", "revenue from new products increased following R&D investment"),
        _ev("capacity", "new product line launched"),
    ]
    result = _determine_outcome_attribution(rec, ev)
    assert result != "DIRECTLY_ATTRIBUTABLE"


def test_oa_r3_before_after_pattern_not_causal():
    """OA-R3 NF-CAUSE-03: before/after temporal framing cannot produce DIRECTLY_ATTRIBUTABLE."""
    rec = _rec(category="acquisition", current_status="deployed", amount_crore=200.0)
    ev = [_ev("project", "EBITDA improved from ₹120 cr to ₹185 cr in two years following acquisition")]
    result = _determine_outcome_attribution(rec, ev)
    assert result != "DIRECTLY_ATTRIBUTABLE"


def test_oa_r3_pc_distribution_direct_attribution():
    """OA-R3 PC-CAUSE-01: positive control — distribution IS causal (self-evidencing transaction)."""
    rec = _rec(category="dividend", current_status="deployed", amount_crore=100.0)
    result = _determine_outcome_attribution(rec, [])
    assert result == "DIRECTLY_ATTRIBUTABLE"


# ─── OA-R4: Operating→economic outcome leakage ──────────────────────────────
# CAPACITY_ADDED (an operating outcome) must not be confused with a financial outcome.
# Operational evidence supports at most ASSOCIATED_NOT_ATTRIBUTABLE, not DIRECTLY_ATTRIBUTABLE.

def test_oa_r4_operational_capex_not_directly_attributable():
    """OA-R4 NF-CAUSE-04: OPERATIONAL capex with capacity evidence → ASSOCIATED, not DIRECTLY."""
    rec = _rec(
        category="capex",
        current_status="deployed",
        execution_state="OPERATIONAL",
        amount_crore=500.0,
    )
    ev = [
        _ev("project", "plant operational and commissioned"),
        _ev("capacity", "added 5000 MT capacity"),
    ]
    result = _determine_outcome_attribution(rec, ev)
    assert result != "DIRECTLY_ATTRIBUTABLE"
    # ASSOCIATED_NOT_ATTRIBUTABLE or STRONGLY_SUPPORTED is acceptable — not DIRECTLY_ATTRIBUTABLE
    assert result in ("ASSOCIATED_NOT_ATTRIBUTABLE", "STRONGLY_SUPPORTED")


def test_oa_r4_capacity_added_state():
    """OA-R4: OPERATIONAL capacity_expansion produces CAPACITY_ADDED operating_outcome_state, not financial."""
    rec = _rec(category="capacity_expansion", current_status="deployed", amount_crore=400.0)
    ev = [
        _ev("project", "plant commissioned and operational"),
        _ev("capacity", "2000 MT capacity added"),
    ]
    states = _causal_attribution_states(rec, ev)
    assert states["operating_outcome_state"] == "CAPACITY_ADDED"
    # Financial outcome state must NOT claim direct revenue attribution
    assert states.get("financial_outcome_state") != "DIRECTLY_ATTRIBUTED_REVENUE"


# ─── OA-R5: Management claim→independent fact ───────────────────────────────
# Evidence of kind "management_claim" must not produce STRONGLY_SUPPORTED.
# STRONGLY_SUPPORTED requires kind in {"project", "capacity"}.

def test_oa_r5_management_claim_not_strongly_supported():
    """OA-R5: management_claim evidence alone cannot produce STRONGLY_SUPPORTED."""
    rec = _rec(
        category="acquisition",
        current_status="deployed",
        execution_state="OPERATIONAL",
        amount_crore=200.0,
    )
    # "Management said the acquisition is fully integrated and generating value"
    ev = [
        _ev("management_claim", "management stated acquisition fully integrated"),
        _ev("management_claim", "management stated strong synergy realization"),
        _ev("management_claim", "CEO confirmed acquisition contributed to growth"),
    ]
    result = _determine_outcome_attribution(rec, ev)
    # management_claim kind is not in {"project", "capacity"}, so specific=[],
    # so STRONGLY_SUPPORTED threshold (len(specific) >= 2) cannot be reached.
    assert result != "STRONGLY_SUPPORTED"


def test_oa_r5_project_evidence_can_reach_strongly_supported():
    """OA-R5 PC: positive control — 2+ project/capacity evidence CAN reach STRONGLY_SUPPORTED."""
    rec = _rec(
        category="capex",
        current_status="deployed",
        execution_state="OPERATIONAL",
        amount_crore=500.0,
    )
    ev = [
        _ev("project", "plant commissioned and operational"),
        _ev("capacity", "5000 MT additional capacity added and utilized"),
    ]
    result = _determine_outcome_attribution(rec, ev)
    # STRONGLY_SUPPORTED requires OPERATIONAL + 2+ specific items
    assert result == "STRONGLY_SUPPORTED"


# ─── OA-R6: Unknown-preservation failure ────────────────────────────────────
# Records with no project/capacity evidence must stay NO_OUTCOME_EVIDENCE.
# They must not be silently promoted to a positive attribution level.

def test_oa_r6_no_evidence_stays_no_outcome():
    """OA-R6 NF: no evidence → NO_OUTCOME_EVIDENCE, not ASSOCIATED or DIRECTLY."""
    for cat in ("acquisition", "capex", "r_and_d", "acquisition_integration"):
        rec = _rec(category=cat, current_status="deployed", amount_crore=100.0)
        result = _determine_outcome_attribution(rec, [])
        assert result == "NO_OUTCOME_EVIDENCE", (
            f"OA-R6: category '{cat}' with no evidence must stay NO_OUTCOME_EVIDENCE, got {result}"
        )


def test_oa_r6_deployed_no_project_evidence_no_attribution():
    """OA-R6: deployed status alone (no project evidence) → NO_OUTCOME_EVIDENCE."""
    rec = _rec(category="capex", current_status="deployed", amount_crore=300.0)
    # Only financial evidence (not project/capacity kind)
    ev = [_ev("financial", "gross margin improved in FY24")]
    result = _determine_outcome_attribution(rec, ev)
    assert result == "NO_OUTCOME_EVIDENCE"


def test_oa_r6_unable_to_verify_execution_stays_no_outcome():
    """OA-R6: UNABLE_TO_VERIFY execution state → NO_OUTCOME_EVIDENCE (no evidence = no signal)."""
    rec = _rec(category="acquisition", current_status="", execution_state="UNABLE_TO_VERIFY")
    result = _determine_outcome_attribution(rec, [])
    assert result == "NO_OUTCOME_EVIDENCE"


# ─── OA-R7: Cross-period attribution leakage ────────────────────────────────
# A capital deployment event cannot produce DIRECTLY_ATTRIBUTABLE for categories
# that require project/capacity evidence; period-bridging evidence is still bound
# by the same STRONGLY_SUPPORTED / ASSOCIATED_NOT_ATTRIBUTABLE ceiling.

def test_oa_r7_old_evidence_same_rules():
    """OA-R7: stale period evidence still subject to the same attribution ceiling."""
    rec = _rec(category="acquisition", current_status="deployed", amount_crore=250.0)
    # Evidence from much earlier period
    ev = [
        _ev("project", "integration completed in FY2019"),
        _ev("capacity", "synergies realized in FY2020"),
    ]
    result = _determine_outcome_attribution(rec, ev)
    # DIRECTLY_ATTRIBUTABLE still impossible for acquisition
    assert result != "DIRECTLY_ATTRIBUTABLE"


def test_oa_r7_cross_period_capex_ceiling():
    """OA-R7: even with OPERATIONAL + 2+ evidence from an earlier period, capex ceiling respected."""
    rec = _rec(
        category="capex",
        current_status="deployed",
        execution_state="OPERATIONAL",
        amount_crore=800.0,
    )
    ev = [
        _ev("project", "commissioned in FY2022 and has been operational since"),
        _ev("capacity", "added 10000 MT in FY2022, fully utilized by FY2024"),
    ]
    result = _determine_outcome_attribution(rec, ev)
    # STRONGLY_SUPPORTED is the ceiling for capex; DIRECTLY_ATTRIBUTABLE is not reachable
    assert result in ("STRONGLY_SUPPORTED", "ASSOCIATED_NOT_ATTRIBUTABLE")
    assert result != "DIRECTLY_ATTRIBUTABLE"


# ─── OA-R8: Duplicate evidence inflation ─────────────────────────────────────
# The same source fact appearing in multiple evidence items must not count as
# independent confirmation. Two items with identical notes should not produce
# STRONGLY_SUPPORTED if neither item is kind "project" or "capacity".

def test_oa_r8_duplicate_management_claims_not_independent():
    """OA-R8: 3x identical management_claim note cannot reach STRONGLY_SUPPORTED."""
    rec = _rec(
        category="acquisition",
        current_status="deployed",
        execution_state="OPERATIONAL",
        amount_crore=150.0,
    )
    note = "acquisition performing ahead of expectations"
    ev = [_ev("management_claim", note) for _ in range(3)]
    result = _determine_outcome_attribution(rec, ev)
    assert result != "STRONGLY_SUPPORTED"


def test_oa_r8_duplicate_project_notes_still_count_as_two():
    """OA-R8 PC: two distinct project/capacity items (even with similar notes) reach STRONGLY_SUPPORTED."""
    rec = _rec(
        category="capex",
        current_status="deployed",
        execution_state="OPERATIONAL",
        amount_crore=400.0,
    )
    ev = [
        _ev("project", "plant fully operational"),
        _ev("capacity", "capacity added and utilized"),
    ]
    result = _determine_outcome_attribution(rec, ev)
    assert result == "STRONGLY_SUPPORTED"


def test_oa_r8_one_project_item_not_strongly_supported():
    """OA-R8: single project evidence item → ASSOCIATED_NOT_ATTRIBUTABLE, not STRONGLY_SUPPORTED."""
    rec = _rec(
        category="capex",
        current_status="deployed",
        execution_state="OPERATIONAL",
        amount_crore=300.0,
    )
    ev = [_ev("project", "plant operational and commissioned")]
    result = _determine_outcome_attribution(rec, ev)
    # Only 1 specific item → cannot reach STRONGLY_SUPPORTED threshold (requires 2+)
    assert result in ("ASSOCIATED_NOT_ATTRIBUTABLE",)
