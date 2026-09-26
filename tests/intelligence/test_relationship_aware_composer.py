"""
Mission 15 composition adversarial tests (C1–C10).

Tests cover the prose-permission system, composition plan categorization,
and gate logic — all deterministic (no AI calls).
"""
from __future__ import annotations

import pytest

from intelligence.ask_intrinsiciq.relationship_aware_composer import (
    ALLOWED,
    QUALIFIED,
    SUPPRESSED,
    get_prose_permission,
    get_confidence_wording,
    build_composition_plan,
    assess_composition_gate,
    _REJECT_PROSE,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _claim(cid: str, text: str, acceptance: str, evidence_refs=None) -> dict:
    return {
        "claim_id": cid,
        "claim_text": text,
        "final_acceptance_status": acceptance,
        "evidence_refs": evidence_refs or [],
    }


def _rel(rid: str, rel_type: str, acceptance: str, conf: str,
         from_id="CF", to_id="CT") -> dict:
    return {
        "rel_id": rid,
        "rel_type": rel_type,
        "acceptance": acceptance,
        "causal_confidence": conf,
        "from_claim_id": from_id,
        "to_claim_id": to_id,
    }


# ── C1: REJECT relationship → SUPPRESSED ──────────────────────────────────────

def test_c1_reject_relationship_suppressed():
    """C1: REJECT relationship must be SUPPRESSED — never asserted as causal fact."""
    perm = get_prose_permission("REJECT", "PLAUSIBLE")
    assert perm == SUPPRESSED, "REJECT must always be SUPPRESSED"


def test_c1_reject_plan_categorization():
    """C1: REJECT relationship ends up in suppressed_relationships in the plan."""
    plan = build_composition_plan(
        claim_results=[_claim("C1", "Revenue grew.", "ACCEPT")],
        rel_results=[_rel("R-REJECT", "OPERATING_TO_FINANCIAL_OUTCOME", "REJECT", "PLAUSIBLE")],
    )
    assert len(plan["suppressed_relationships"]) == 1
    assert plan["suppressed_relationships"][0]["rel_id"] == "R-REJECT"
    assert plan["suppressed_relationships"][0]["suppression_replacement"] == _REJECT_PROSE


# ── C2: NEEDS_REVIEW relationship → QUALIFIED or SUPPRESSED ──────────────────

def test_c2_needs_review_plausible_qualified():
    """C2a: NEEDS_REVIEW + PLAUSIBLE → QUALIFIED (may appear as uncertainty)."""
    perm = get_prose_permission("NEEDS_REVIEW", "PLAUSIBLE")
    assert perm == QUALIFIED


def test_c2_needs_review_supported_suppressed():
    """C2b: NEEDS_REVIEW + SUPPORTED → SUPPRESSED (not safe for qualified prose)."""
    perm = get_prose_permission("NEEDS_REVIEW", "SUPPORTED")
    assert perm == SUPPRESSED


def test_c2_needs_review_plan_categorization():
    """C2: NEEDS_REVIEW + PLAUSIBLE ends in qualified_relationships."""
    plan = build_composition_plan(
        claim_results=[],
        rel_results=[_rel("R-NR", "EXECUTION_TO_OPERATING_OUTCOME", "NEEDS_REVIEW", "PLAUSIBLE")],
    )
    assert len(plan["qualified_relationships"]) == 1
    assert plan["qualified_relationships"][0]["rel_id"] == "R-NR"


# ── C3: UNKNOWN relationship → uncertainty preserved ─────────────────────────

def test_c3_unknown_accept_allowed():
    """C3: ACCEPT + UNKNOWN confidence → ALLOWED (uncertainty language required)."""
    perm = get_prose_permission("ACCEPT", "UNKNOWN")
    assert perm == ALLOWED


def test_c3_unknown_wording():
    """C3: UNKNOWN confidence wording includes uncertainty phrases."""
    wording = get_confidence_wording("UNKNOWN")
    assert any("cannot be established" in w or "uncertain" in w for w in wording)


def test_c3_unknown_rel_in_plan():
    """C3: ACCEPT + UNKNOWN relationship ends in unknown_relationships (separate bucket)."""
    plan = build_composition_plan(
        claim_results=[],
        rel_results=[_rel("R-UNKNOWN", "OPERATING_TO_FINANCIAL_OUTCOME", "ACCEPT", "UNKNOWN")],
    )
    assert len(plan["unknown_relationships"]) == 1
    assert plan["unknown_relationships"][0]["rel_id"] == "R-UNKNOWN"


# ── C4: CONFIRMED relationship → strong causal wording allowed ───────────────

def test_c4_confirmed_accept_allowed():
    """C4: ACCEPT + CONFIRMED → ALLOWED with strong causal wording."""
    perm = get_prose_permission("ACCEPT", "CONFIRMED")
    assert perm == ALLOWED


def test_c4_confirmed_wording_is_causal():
    """C4: CONFIRMED wording includes 'contributed to', 'resulted in'."""
    wording = get_confidence_wording("CONFIRMED")
    assert any("contributed to" in w or "resulted in" in w for w in wording)


def test_c4_confirmed_in_allowed_rels():
    """C4: ACCEPT + CONFIRMED ends in allowed_relationships."""
    plan = build_composition_plan(
        claim_results=[],
        rel_results=[_rel("R-CONFIRMED", "OPERATING_TO_FINANCIAL_OUTCOME", "ACCEPT", "CONFIRMED")],
    )
    assert len(plan["allowed_relationships"]) == 1


# ── C5: PLAUSIBLE relationship → qualified wording only ──────────────────────

def test_c5_plausible_accept_allowed():
    """C5: ACCEPT + PLAUSIBLE → ALLOWED, but only with hedged wording."""
    perm = get_prose_permission("ACCEPT", "PLAUSIBLE")
    assert perm == ALLOWED


def test_c5_plausible_wording_is_hedged():
    """C5: PLAUSIBLE wording must include 'may have contributed' or 'could be'."""
    wording = get_confidence_wording("PLAUSIBLE")
    assert any("may have" in w or "could be" in w for w in wording)


def test_c5_plausible_does_not_include_definitive_causal():
    """C5: PLAUSIBLE wording must not include 'contributed to' (definitive)."""
    wording = get_confidence_wording("PLAUSIBLE")
    assert not any(w.strip() == "contributed to" for w in wording)


# ── C6: Undeclared claim detection ───────────────────────────────────────────

def test_c6_undeclared_claim_gate_context():
    """C6: Gate note explicitly states undeclared claim check requires claim extractor."""
    plan = build_composition_plan(claim_results=[], rel_results=[])
    gate_result = assess_composition_gate({"simple_answer": "Revenue grew."}, plan)
    assert "validate_answer_complete" in gate_result["note"] or "Full gate" in gate_result["note"]


# ── C7: Hidden causal assertion detection ────────────────────────────────────

def test_c7_suppressed_rel_id_in_prose_fails_gate():
    """C7: If prose somehow contains a suppressed rel_id, gate fails."""
    plan = build_composition_plan(
        claim_results=[],
        rel_results=[_rel("REL-004", "OPERATING_TO_FINANCIAL_OUTCOME", "REJECT", "PLAUSIBLE")],
    )
    # Simulate prose that leaked the rel_id (should never happen, but gate should catch it)
    answer = {"simple_answer": "REL-004 is the key driver."}
    result = assess_composition_gate(answer, plan)
    assert "REL-004" in result["suppressed_rel_ids_found_in_prose"]
    assert result["gate"] != "PASS"


# ── C8: Negated causal statement ─────────────────────────────────────────────

def test_c8_negation_not_misclassified():
    """C8: Permission for a REJECT rel is SUPPRESSED regardless of prose wording in rationale."""
    # The reviewer must not 'accept' a rejected relationship because it was framed negatively
    perm = get_prose_permission("REJECT", "PLAUSIBLE")
    assert perm == SUPPRESSED, "REJECT is always SUPPRESSED — no negation exception"


def test_c8_replacement_prose_for_suppressed_rel():
    """C8: Suppressed relationship gets a factual replacement prose."""
    plan = build_composition_plan(
        claim_results=[],
        rel_results=[_rel("R1", "OPERATING_TO_FINANCIAL_OUTCOME", "REJECT", "PLAUSIBLE")],
    )
    assert plan["suppressed_relationships"][0]["suppression_replacement"] == _REJECT_PROSE
    assert "does not establish" in _REJECT_PROSE


# ── C9: Rejected relationship — endpoints may remain, causal link suppressed ─

def test_c9_reject_rel_endpoints_can_accept():
    """C9: ACCEPT claims (endpoints) are in allowed_claims even if their relationship is REJECT."""
    plan = build_composition_plan(
        claim_results=[
            _claim("C-SRC", "Initiative was launched.", "ACCEPT"),
            _claim("C-TGT", "Revenue grew 12%.", "ACCEPT"),
        ],
        rel_results=[
            _rel("R-CAUSAL", "OPERATING_TO_FINANCIAL_OUTCOME", "REJECT", "PLAUSIBLE",
                 from_id="C-SRC", to_id="C-TGT"),
        ],
    )
    # Both endpoint claims are ALLOWED
    allowed_ids = {c["claim_id"] for c in plan["allowed_claims"]}
    assert "C-SRC" in allowed_ids
    assert "C-TGT" in allowed_ids
    # But the causal relationship is SUPPRESSED
    assert len(plan["suppressed_relationships"]) == 1


# ── C10: Correct supported relationship survives composition ──────────────────

def test_c10_supported_accept_relationship_survives():
    """C10: ACCEPT + SUPPORTED relationship ends in allowed_relationships — not suppressed."""
    plan = build_composition_plan(
        claim_results=[_claim("C1", "Capex deployed.", "ACCEPT")],
        rel_results=[_rel("R-OK", "CAPITAL_TO_EXECUTION", "ACCEPT", "SUPPORTED")],
    )
    assert len(plan["allowed_relationships"]) == 1
    assert plan["allowed_relationships"][0]["rel_id"] == "R-OK"
    assert len(plan["suppressed_relationships"]) == 0


def test_c10_accept_claim_in_allowed_claims():
    """C10: ACCEPT claims reach allowed_claims unchanged."""
    plan = build_composition_plan(
        claim_results=[_claim("C-OK", "Margins improved.", "ACCEPT")],
        rel_results=[],
    )
    assert len(plan["allowed_claims"]) == 1
    assert plan["allowed_claims"][0]["claim_id"] == "C-OK"
    assert plan["allowed_claims"][0]["prose_permission"] == ALLOWED


# ── Permission completeness ───────────────────────────────────────────────────

def test_all_acceptance_states_have_permission():
    """Every acceptance state must map to a defined permission."""
    for state in ("ACCEPT", "NEEDS_REVIEW", "REJECT"):
        for conf in ("CONFIRMED", "SUPPORTED", "PLAUSIBLE", "UNKNOWN"):
            perm = get_prose_permission(state, conf)
            assert perm in (ALLOWED, QUALIFIED, SUPPRESSED), (
                f"get_prose_permission({state!r}, {conf!r}) returned unexpected {perm!r}"
            )
