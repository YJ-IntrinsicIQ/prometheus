"""Unit tests for the canonical relationship reviewer (Mission 14)."""
from __future__ import annotations

import pytest
from intelligence.ask_intrinsiciq.relationship_reviewer import (
    apply_acceptance_contract,
    ACCEPT,
    NEEDS_REVIEW,
    REJECT,
    ReviewerResult,
)


def _result(
    verdict="SUPPORTED",
    recommended="SUPPORTED",
    chrono_relation="BEFORE",
    chrono_valid=True,
    semantic_alignment=True,
    linkage=True,
    issues=None,
    retro=False,
    mw=False,
    reason="test",
):
    return ReviewerResult(
        verdict=verdict,
        recommended_confidence=recommended,
        chronology_relation=chrono_relation,
        chronology_valid=chrono_valid,
        semantic_alignment=semantic_alignment,
        linkage_established=linkage,
        causal_issues=issues or [],
        retrospective_bias=retro,
        measurement_window_issue=mw,
        alternative_explanations=None,
        qualification_required=None,
        reason=reason,
    )


# ── CONFIRMED ─────────────────────────────────────────────────────────────────

def test_confirmed_accept():
    r = _result(verdict="SUPPORTED", issues=[], linkage=True, retro=False, mw=False)
    status, _ = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "CONFIRMED", r)
    assert status == ACCEPT


def test_confirmed_reject_unsupported():
    r = _result(verdict="UNSUPPORTED", issues=["no linkage"])
    status, code = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "CONFIRMED", r)
    assert status == REJECT


def test_confirmed_reject_causal_issues():
    r = _result(verdict="SUPPORTED", issues=["management_retrospective_attribution"])
    status, _ = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "CONFIRMED", r)
    assert status in (REJECT, NEEDS_REVIEW)


# ── SUPPORTED — general ───────────────────────────────────────────────────────

def test_supported_accept_general():
    r = _result(verdict="PARTIALLY_SUPPORTED", issues=[], retro=False, mw=False)
    status, _ = apply_acceptance_contract("EXECUTION_TO_OPERATING_OUTCOME", "SUPPORTED", r)
    assert status == ACCEPT


def test_supported_reject_hard_overstatement():
    r = _result(verdict="PARTIALLY_SUPPORTED", issues=["correlation as causality"])
    status, code = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "SUPPORTED", r)
    assert status in (NEEDS_REVIEW, REJECT)
    assert "overstatement" in code or "partial" in code


def test_supported_reject_retrospective():
    r = _result(verdict="PARTIALLY_SUPPORTED", issues=[], retro=True)
    status, _ = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "SUPPORTED", r)
    assert status in (NEEDS_REVIEW, REJECT)


# ── SUPPORTED — STRATEGY_TO_EXECUTION ────────────────────────────────────────

def test_s2e_accept_with_semantic_alignment():
    """Valid strategy-to-execution with alignment: should ACCEPT."""
    r = _result(verdict="SUPPORTED", semantic_alignment=True, issues=[], retro=False, mw=False)
    status, code = apply_acceptance_contract("STRATEGY_TO_EXECUTION", "SUPPORTED", r)
    assert status == ACCEPT
    assert "s2e" in code


def test_s2e_reject_no_semantic_alignment():
    """Debt raising doesn't semantically align with technology strategy."""
    r = _result(verdict="PARTIALLY_SUPPORTED", semantic_alignment=False, issues=[])
    status, code = apply_acceptance_contract("STRATEGY_TO_EXECUTION", "SUPPORTED", r)
    assert status in (NEEDS_REVIEW, REJECT)
    assert "no_semantic_alignment" in code


def test_s2e_does_not_fall_through_to_general():
    """S2E with semantic_alignment=False must not slip through to general SUPPORTED accept."""
    r = _result(verdict="PARTIALLY_SUPPORTED", semantic_alignment=False, issues=[], retro=False, mw=False)
    status, _ = apply_acceptance_contract("STRATEGY_TO_EXECUTION", "SUPPORTED", r)
    assert status != ACCEPT


# ── SUPPORTED — CAPITAL_TO_EXECUTION ─────────────────────────────────────────

def test_c2e_overlapping_chrono_accepts():
    """Same-year capital + execution project: OVERLAPPING should be valid."""
    r = _result(verdict="PARTIALLY_SUPPORTED", chrono_relation="OVERLAPPING", chrono_valid=True, issues=[])
    status, _ = apply_acceptance_contract("CAPITAL_TO_EXECUTION", "SUPPORTED", r)
    assert status == ACCEPT


def test_c2e_revenue_target_blocked():
    """Capital → revenue growth in same year (financial target) should not ACCEPT."""
    r = _result(
        verdict="PARTIALLY_SUPPORTED",
        chrono_relation="OVERLAPPING",
        chrono_valid=True,
        issues=["correlation_as_causation: co-occurrence of capex and revenue growth"],
    )
    status, code = apply_acceptance_contract("CAPITAL_TO_EXECUTION", "SUPPORTED", r)
    assert status in (NEEDS_REVIEW, REJECT)


# ── PLAUSIBLE ─────────────────────────────────────────────────────────────────

def test_plausible_accept_with_frame():
    """PLAUSIBLE with interpretation frame and valid verdict: should ACCEPT."""
    r = _result(verdict="PARTIALLY_SUPPORTED", reason="r&d may have contributed to growth — cannot confirm")
    status, _ = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "PLAUSIBLE", r)
    assert status == ACCEPT


def test_plausible_accept_no_measurement_window_block():
    """Measurement window should NOT block PLAUSIBLE with interpretation frame."""
    r = _result(verdict="PARTIALLY_SUPPORTED", mw=True, reason="plausibly consistent with revenue trend")
    status, _ = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "PLAUSIBLE", r)
    assert status == ACCEPT


def test_plausible_reject_unsupported():
    """PLAUSIBLE with UNSUPPORTED verdict: NEEDS_REVIEW (evidence support mandatory for ACCEPT)."""
    r = _result(verdict="UNSUPPORTED", reason="no connection found")
    status, _ = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "PLAUSIBLE", r)
    assert status in (NEEDS_REVIEW, REJECT)  # never ACCEPT


def test_plausible_p1_supported_plausible_accept():
    """P1: PLAUSIBLE + PARTIALLY_SUPPORTED + interpretation frame → ACCEPT."""
    r = _result(verdict="PARTIALLY_SUPPORTED", reason="capacity expansion may have contributed to margin improvement")
    status, _ = apply_acceptance_contract("EXECUTION_TO_OPERATING_OUTCOME", "PLAUSIBLE", r)
    assert status == ACCEPT


def test_plausible_p2_unsupported_with_frame_needs_review():
    """P2: PLAUSIBLE + UNSUPPORTED + has_frame → still NEEDS_REVIEW (frame alone insufficient)."""
    r = _result(verdict="UNSUPPORTED", reason="may have contributed, though no direct evidence found")
    status, _ = apply_acceptance_contract("EXECUTION_TO_OPERATING_OUTCOME", "PLAUSIBLE", r)
    assert status in (NEEDS_REVIEW, REJECT)  # never ACCEPT


def test_plausible_needs_review_missing_frame():
    """PLAUSIBLE with valid verdict but no interpretation frame: NEEDS_REVIEW."""
    r = _result(verdict="PARTIALLY_SUPPORTED", reason="capex occurred and revenue grew")
    status, code = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "PLAUSIBLE", r)
    assert status in (NEEDS_REVIEW, REJECT)


# ── CONTEXT_ONLY ──────────────────────────────────────────────────────────────

def test_context_only_chrono_not_required():
    """CONTEXT_ONLY PLAUSIBLE where source postdates target: should still ACCEPT."""
    # chronology_valid is set True by the reviewer for CONTEXT_ONLY regardless
    r = _result(verdict="SUPPORTED", chrono_relation="AFTER", chrono_valid=True, reason="contextualises the security investment direction")
    status, _ = apply_acceptance_contract("CONTEXT_ONLY", "PLAUSIBLE", r)
    assert status == ACCEPT


# ── UNKNOWN ───────────────────────────────────────────────────────────────────

def test_unknown_preserved():
    """UNKNOWN relationship with UNSUPPORTED verdict: still ACCEPT."""
    r = _result(verdict="UNSUPPORTED")
    status, _ = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "UNKNOWN", r)
    assert status == ACCEPT


def test_unknown_escalated_if_contradicted():
    """UNKNOWN relationship that is CONTRADICTED: NEEDS_REVIEW."""
    r = _result(verdict="CONTRADICTED")
    status, _ = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "UNKNOWN", r)
    assert status == NEEDS_REVIEW


# ── REVIEW_ERROR ──────────────────────────────────────────────────────────────

def test_review_error_routes_to_needs_review():
    r = _result(verdict="REVIEW_ERROR")
    status, code = apply_acceptance_contract("OPERATING_TO_FINANCIAL_OUTCOME", "SUPPORTED", r)
    assert status == NEEDS_REVIEW
    assert "error" in code
