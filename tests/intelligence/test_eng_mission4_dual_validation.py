"""
Mission 4 adversarial tests: Reliable Claim-to-Evidence Dual Validation.

Tests cover the 10 adversarial classes specified in Mission 4 Step 6:
  1. Product launch cited as proof of prescription growth
  2. Management intention presented as completed execution
  3. Incorrect fiscal period / geography
  4. Company-wide revenue attributed to one product
  5. Unsupported causal claims (only AI catches)
  6. Incorrect financial amounts / units (only AI catches)
  7. Industry observations cited as company commitments (only AI catches)
  8. Unverified commitments described as failed
  9. Unsupported claims hidden in narrative paragraphs
  10. Correct conditional economic explanations (must pass / ACCEPT)

AI reviewer is mocked for deterministic test behavior; routing logic tests verify
that deterministic rejection cannot be overridden by AI approval.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from intelligence.ask_intrinsiciq.claim_validator import (
    _determine_acceptance,
    validate_claim_with_ai,
    validate_answer_with_ai,
    ACCEPT,
    NEEDS_REVIEW,
    REJECT,
    VERDICT_SUPPORTED,
    VERDICT_PARTIALLY,
    VERDICT_UNSUPPORTED,
    VERDICT_CONTRADICTED,
)


# ── Shared fixture ─────────────────────────────────────────────────────────────

def _pkg():
    return {
        "package_fingerprint": "m4test",
        "company_slug": "test_co",
        "package_constraints": {
            "ai_reasoning_global_constraints": [],
            "silence_is_not_failure": "UNVERIFIED means no evidence — not failure.",
            "accountability_metrics": {},
        },
        "sections": {
            "verifiable_commitments": [
                {
                    "item_id": "PT-FY22",
                    "evidence_type": "VERIFIABLE_COMMITMENT",
                    "original_statement": "Ramp up ILUMYA prescriptions in Japan by FY22.",
                    "announcement_period": "fy22",
                    "execution_status": "CLAIM_ONLY",
                    "outcome_status": "UNVERIFIED",
                    "ai_reasoning_guidance": {
                        "may_assert": ["Management committed to ramp-up in FY22"],
                        "must_not_assert": [
                            "prescriptions increased",
                            "commitment was fulfilled",
                            "ramp-up was successful",
                        ],
                    },
                },
                {
                    "item_id": "PT-FY23",
                    "evidence_type": "VERIFIABLE_COMMITMENT",
                    "original_statement": "Expand to three new markets in FY23.",
                    "announcement_period": "fy23",
                    "execution_status": "CLAIM_ONLY",
                    "outcome_status": "UNVERIFIED",
                    "ai_reasoning_guidance": {
                        "may_assert": ["Management targeted three new markets in FY23"],
                        "must_not_assert": ["commitment was fulfilled", "markets were entered"],
                    },
                },
            ],
            "observable_execution_evidence": [
                {
                    "item_id": "OE-001",
                    "evidence_type": "PRODUCT_AVAILABILITY",
                    "excerpt": "ILUMYA/Ilumetri launched in Japan (FY22)",
                    "semantic_classification": {
                        "is_product_availability": True,
                        "is_prescription_ramp_verification": False,
                        "is_revenue_attribution": False,
                    },
                    "ai_reasoning_guidance": {
                        "may_assert": ["ILUMYA was made available in Japan"],
                        "must_not_assert": ["prescriptions grew", "ramp succeeded"],
                    },
                }
            ],
            "adverse_evidence": [
                {
                    "item_id": "AE-001",
                    "evidence_type": "ADVERSE_EVIDENCE",
                    "description": "No prescription volume data found for Japan market.",
                }
            ],
            "strategic_intents": [],
            "business_model_context": [
                {
                    "item_id": "BC-001",
                    "evidence_type": "BUSINESS_MODEL_CONTEXT",
                    "field": "how_revenue_happens",
                    "content": "Pharmaceutical sales across branded, generic, and specialty segments.",
                },
            ],
            "source_limitations": [
                {
                    "limitation_id": "SL-001",
                    "type": "SOURCE_EVIDENCE_MISSING",
                    "description": "No prescription volume data available for Japan or Australia.",
                }
            ],
        },
    }


def _ai_ok(verdict="SUPPORTED"):
    return {
        "verdict": verdict,
        "confidence": "HIGH",
        "reason": f"Evidence establishes the claim. Verdict: {verdict}.",
        "scope_issues": [],
        "qualifications_missing": [],
    }


def _ai_reject(verdict="UNSUPPORTED", reason="Evidence does not establish the claim."):
    return {
        "verdict": verdict,
        "confidence": "HIGH",
        "reason": reason,
        "scope_issues": [],
        "qualifications_missing": [],
    }


# ── Acceptance routing unit tests ──────────────────────────────────────────────

class TestDetermineAcceptance:
    def test_det_contradicted_is_always_reject(self):
        _, status = _determine_acceptance(VERDICT_CONTRADICTED, VERDICT_SUPPORTED)
        assert status == REJECT

    def test_det_unsupported_is_always_reject(self):
        _, status = _determine_acceptance(VERDICT_UNSUPPORTED, VERDICT_SUPPORTED)
        assert status == REJECT

    def test_ai_approval_cannot_override_det_rejection(self):
        """Core invariant: AI SUPPORTED cannot override deterministic CONTRADICTED."""
        _, status = _determine_acceptance(VERDICT_CONTRADICTED, VERDICT_SUPPORTED)
        assert status == REJECT, "AI approval must not override deterministic rejection"

    def test_both_supported_is_accept(self):
        _, status = _determine_acceptance(VERDICT_SUPPORTED, VERDICT_SUPPORTED)
        assert status == ACCEPT

    def test_det_supported_ai_partially_is_needs_review(self):
        _, status = _determine_acceptance(VERDICT_SUPPORTED, VERDICT_PARTIALLY)
        assert status == NEEDS_REVIEW

    def test_det_supported_ai_unsupported_is_needs_review(self):
        _, status = _determine_acceptance(VERDICT_SUPPORTED, VERDICT_UNSUPPORTED)
        assert status == NEEDS_REVIEW

    def test_det_supported_ai_contradicted_is_needs_review(self):
        _, status = _determine_acceptance(VERDICT_SUPPORTED, VERDICT_CONTRADICTED)
        assert status == NEEDS_REVIEW

    def test_det_partially_ai_supported_is_needs_review(self):
        _, status = _determine_acceptance(VERDICT_PARTIALLY, VERDICT_SUPPORTED)
        assert status == NEEDS_REVIEW

    def test_det_partially_ai_unsupported_is_reject(self):
        _, status = _determine_acceptance(VERDICT_PARTIALLY, VERDICT_UNSUPPORTED)
        assert status == REJECT

    def test_det_partially_ai_contradicted_is_reject(self):
        _, status = _determine_acceptance(VERDICT_PARTIALLY, VERDICT_CONTRADICTED)
        assert status == REJECT

    def test_review_error_is_needs_review(self):
        _, status = _determine_acceptance(VERDICT_SUPPORTED, "REVIEW_ERROR")
        assert status == NEEDS_REVIEW


# ── Class 1: Product launch ≠ prescription growth ─────────────────────────────

def test_c1_product_launch_cited_as_prescription_proof_is_rejected():
    """C1: Claiming prescription growth from launch evidence — det catches forbidden phrase."""
    pkg = _pkg()
    claim = {
        "claim_id": "C1",
        "claim_text": "Following the ILUMYA launch in Japan, prescription volumes grew and the ramp-up was successful.",
        "evidence_refs": ["OE-001"],
        "claim_type": "PRODUCT_AVAILABILITY",
    }
    from intelligence.ask_intrinsiciq.claim_validator import _build_evidence_index, _build_must_not_assert_index, validate_claim
    ei = _build_evidence_index(pkg)
    mni = _build_must_not_assert_index(pkg)
    det = validate_claim(claim, ei, mni, [])
    assert det["verdict"] == VERDICT_CONTRADICTED, \
        f"Det should catch prescription ramp assertion from launch evidence: {det['issues']}"


# ── Class 2: Intention as completed execution ──────────────────────────────────

def test_c2_intention_presented_as_completed_execution_is_rejected():
    """C2: Management commitment presented as fulfilled — det catches forbidden phrase."""
    pkg = _pkg()
    claim = {
        "claim_id": "C2",
        "claim_text": "Management's commitment to ramp up prescriptions was met and commitment was fulfilled.",
        "evidence_refs": ["PT-FY22"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    from intelligence.ask_intrinsiciq.claim_validator import _build_evidence_index, _build_must_not_assert_index, validate_claim
    ei = _build_evidence_index(pkg)
    mni = _build_must_not_assert_index(pkg)
    det = validate_claim(claim, ei, mni, [])
    assert det["verdict"] == VERDICT_CONTRADICTED


# ── Class 3: Incorrect fiscal period ──────────────────────────────────────────

def test_c3_incorrect_fiscal_period_produces_partially_supported():
    """C3: Claiming FY23 for a FY22 commitment — det produces period warning → PARTIALLY."""
    pkg = _pkg()
    claim = {
        "claim_id": "C3",
        "claim_text": "Management committed in FY23 to ramp up ILUMYA prescriptions.",
        "evidence_refs": ["PT-FY22"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    from intelligence.ask_intrinsiciq.claim_validator import _build_evidence_index, _build_must_not_assert_index, validate_claim
    ei = _build_evidence_index(pkg)
    mni = _build_must_not_assert_index(pkg)
    det = validate_claim(claim, ei, mni, [])
    assert det["verdict"] == VERDICT_PARTIALLY, \
        f"Period mismatch should yield PARTIALLY_SUPPORTED, got {det['verdict']}"
    assert any("Period mismatch" in w for w in det["warnings"])


def test_c3_period_mismatch_plus_ai_rejection_yields_reject():
    """C3: det=PARTIALLY + AI catches scope issue → REJECT."""
    pkg = _pkg()
    claim = {
        "claim_id": "C3",
        "claim_text": "Management committed in FY23 to ramp up ILUMYA prescriptions.",
        "evidence_refs": ["PT-FY22"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    with patch(
        "intelligence.ask_intrinsiciq.claim_validator.validate_claim_with_ai.__wrapped__"
        if hasattr(validate_claim_with_ai, "__wrapped__") else
        "intelligence.ask_intrinsiciq.ai_claim_reviewer.review_claim",
        return_value=_ai_reject(verdict=VERDICT_UNSUPPORTED, reason="Period in claim (FY23) does not match evidence period (FY22)."),
    ):
        result = validate_claim_with_ai(
            claim,
            _build_ei(pkg),
            _build_mni(pkg),
            [],
        )
    assert result["final_acceptance_status"] == REJECT


# ── Class 4: Revenue attributed to one product without evidence ────────────────

def test_c4_company_revenue_attributed_to_one_product_is_rejected():
    """C4: Claiming ILUMYA generated revenue — det catches revenue attribution phrase."""
    pkg = _pkg()
    claim = {
        "claim_id": "C4",
        "claim_text": "ILUMYA revenue contributed to specialty segment growth.",
        "evidence_refs": ["OE-001"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    from intelligence.ask_intrinsiciq.claim_validator import _build_evidence_index, _build_must_not_assert_index, validate_claim
    ei = _build_evidence_index(pkg)
    mni = _build_must_not_assert_index(pkg)
    det = validate_claim(claim, ei, mni, [])
    assert det["verdict"] == VERDICT_CONTRADICTED, \
        f"Revenue attribution should be CONTRADICTED: {det['issues']}"


# ── Class 5: Unsupported causal claim (only AI catches) ───────────────────────

def test_c5_unsupported_causal_claim_ai_catches_and_yields_needs_review():
    """C5: Claim makes causal inference that det allows but AI correctly flags."""
    pkg = _pkg()
    claim = {
        "claim_id": "C5",
        "claim_text": "Because management committed to Japan market entry, specialty growth in Asia followed.",
        "evidence_refs": ["PT-FY22", "OE-001"],
        "claim_type": "STRATEGIC_DIRECTION",
    }
    with patch(
        "intelligence.ask_intrinsiciq.ai_claim_reviewer.review_claim",
        return_value=_ai_reject(
            verdict=VERDICT_UNSUPPORTED,
            reason="Causal inference (commitment → growth) is not established by cited evidence.",
        ),
    ):
        result = validate_claim_with_ai(claim, _build_ei(pkg), _build_mni(pkg), [])
    assert result["final_acceptance_status"] == NEEDS_REVIEW
    assert result["ai_verdict"] == VERDICT_UNSUPPORTED


# ── Class 6: Incorrect financial amounts (only AI catches) ────────────────────

def test_c6_incorrect_financial_amounts_ai_flags_and_yields_needs_review():
    """C6: Claim states specific revenue figure not present in any cited evidence."""
    pkg = _pkg()
    claim = {
        "claim_id": "C6",
        "claim_text": "Management's Japan entry generated ₹500 crore in specialty revenue.",
        "evidence_refs": ["OE-001"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    with patch(
        "intelligence.ask_intrinsiciq.ai_claim_reviewer.review_claim",
        return_value=_ai_reject(
            verdict=VERDICT_UNSUPPORTED,
            reason="Specific revenue figure (₹500 crore) is absent from cited evidence items.",
        ),
    ):
        result = validate_claim_with_ai(claim, _build_ei(pkg), _build_mni(pkg), [])
    assert result["final_acceptance_status"] == NEEDS_REVIEW
    assert result["ai_verdict"] == VERDICT_UNSUPPORTED


# ── Class 7: Industry observation as company commitment (only AI catches) ──────

def test_c7_industry_observation_cited_as_company_commitment_ai_flags():
    """C7: General industry trend presented as a commitment by this company."""
    pkg = _pkg()
    # BC-001 is business model context (how revenue happens), not a commitment
    claim = {
        "claim_id": "C7",
        "claim_text": "The company committed to growing specialty revenue as a primary channel.",
        "evidence_refs": ["BC-001"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    with patch(
        "intelligence.ask_intrinsiciq.ai_claim_reviewer.review_claim",
        return_value=_ai_reject(
            verdict=VERDICT_UNSUPPORTED,
            reason="BC-001 describes the business model (how revenue happens), not a management commitment.",
        ),
    ):
        result = validate_claim_with_ai(claim, _build_ei(pkg), _build_mni(pkg), [])
    assert result["final_acceptance_status"] == NEEDS_REVIEW
    assert "BC-001" in " ".join(result.get("ai_scope_issues", []) + [result["ai_reason"]])


# ── Class 8: UNVERIFIED commitment described as FAILED ────────────────────────

def test_c8_unverified_commitment_as_failed_is_rejected():
    """C8: UNVERIFIED commitment described as 'failed to deliver' — det catches it."""
    pkg = _pkg()
    claim = {
        "claim_id": "C8",
        "claim_text": "Management failed to deliver on its FY22 prescription ramp commitment in Japan.",
        "evidence_refs": ["PT-FY22"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    from intelligence.ask_intrinsiciq.claim_validator import _build_evidence_index, _build_must_not_assert_index, validate_claim
    ei = _build_evidence_index(pkg)
    mni = _build_must_not_assert_index(pkg)
    det = validate_claim(claim, ei, mni, [])
    assert det["verdict"] == VERDICT_CONTRADICTED


# ── Class 9: Unsupported claims in narrative paragraphs ───────────────────────

def test_c9_value_hierarchy_in_narrative_fails_validate_answer():
    """C9: Narrative paragraph contains unsupported value-hierarchy inference."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": "This expands geographic reach for higher-value specialty products.",
        "simple_answer": "Management made commitments.",
        "key_points": [],
        "economic_reasoning": {},
        "claims": [],
    }
    from intelligence.ask_intrinsiciq.claim_validator import validate_answer
    report = validate_answer(ai_answer, pkg)
    assert report["answer_status"] == "FAIL_NARRATIVE"
    assert report["narrative_issues_count"] >= 1


def test_c9_unsupported_claim_hidden_in_narrative_economic_reasoning():
    """C9: 'commitment fulfilled' in economic_reasoning fires narrative violation."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": "Specialty expansion matters.",
        "simple_answer": "Management made commitments.",
        "key_points": [],
        "economic_reasoning": {
            "established_outcomes": "The Japan commitment was fulfilled and prescription volumes increased."
        },
        "claims": [],
    }
    from intelligence.ask_intrinsiciq.claim_validator import validate_answer
    report = validate_answer(ai_answer, pkg)
    assert report["answer_status"] == "FAIL_NARRATIVE"


# ── Class 10: Correct conditional economic explanation should ACCEPT ───────────

def test_c10_correct_conditional_explanation_is_accepted():
    """C10: Clean claim with correct qualifications + AI confirms → ACCEPT."""
    pkg = _pkg()
    claim = {
        "claim_id": "C10",
        "claim_text": (
            "Management committed in FY22 to ramping up ILUMYA prescriptions in Japan; "
            "this commitment remains UNVERIFIED — no later evidence confirms outcomes."
        ),
        "evidence_refs": ["PT-FY22"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    with patch(
        "intelligence.ask_intrinsiciq.ai_claim_reviewer.review_claim",
        return_value=_ai_ok("SUPPORTED"),
    ):
        result = validate_claim_with_ai(claim, _build_ei(pkg), _build_mni(pkg), [])
    assert result["final_acceptance_status"] == ACCEPT
    assert result["ai_verdict"] == VERDICT_SUPPORTED
    assert result["deterministic_verdict"] == VERDICT_SUPPORTED


def test_c10_correct_product_availability_claim_is_accepted():
    """C10: Accurate product-availability claim with no over-inference → ACCEPT."""
    pkg = _pkg()
    claim = {
        "claim_id": "C10b",
        "claim_text": "ILUMYA was launched and made available in Japan in FY22 per observable evidence.",
        "evidence_refs": ["OE-001"],
        "claim_type": "PRODUCT_AVAILABILITY",
    }
    with patch(
        "intelligence.ask_intrinsiciq.ai_claim_reviewer.review_claim",
        return_value=_ai_ok("SUPPORTED"),
    ):
        result = validate_claim_with_ai(claim, _build_ei(pkg), _build_mni(pkg), [])
    assert result["final_acceptance_status"] == ACCEPT


# ── Full answer dual-validation pass/fail routing ─────────────────────────────

def test_full_answer_all_accepted_passes():
    """All claims ACCEPT and clean narrative → PASS."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": "These commitments align with the stated specialty revenue model.",
        "simple_answer": "Two commitments, both UNVERIFIED.",
        "key_points": ["FY22: Japan ramp-up committed (unverified)."],
        "economic_reasoning": {
            "remaining_uncertainty": "No prescription volume data available."
        },
        "claims": [
            {
                "claim_id": "C1",
                "claim_text": "Management committed in FY22 to ILUMYA ramp-up in Japan; UNVERIFIED.",
                "evidence_refs": ["PT-FY22"],
                "claim_type": "COMMITMENT_STATEMENT",
            }
        ],
    }
    with patch(
        "intelligence.ask_intrinsiciq.ai_claim_reviewer.review_claim",
        return_value=_ai_ok("SUPPORTED"),
    ):
        report = validate_answer_with_ai(ai_answer, pkg)
    assert report["answer_status"] == "PASS"
    assert report["claims_accepted"] == 1
    assert report["claims_rejected"] == 0
    assert report["claims_needs_review"] == 0


def test_full_answer_with_contradicted_claim_fails():
    """A single CONTRADICTED claim → FAIL_CONTRADICTED regardless of AI."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": "",
        "simple_answer": "",
        "key_points": [],
        "economic_reasoning": {},
        "claims": [
            {
                "claim_id": "C_bad",
                "claim_text": "The prescription ramp-up was successful and commitment was fulfilled.",
                "evidence_refs": ["PT-FY22"],
                "claim_type": "COMMITMENT_STATEMENT",
            }
        ],
    }
    # Even if AI says SUPPORTED, det contradiction wins
    with patch(
        "intelligence.ask_intrinsiciq.ai_claim_reviewer.review_claim",
        return_value=_ai_ok("SUPPORTED"),
    ):
        report = validate_answer_with_ai(ai_answer, pkg)
    assert report["answer_status"] == "FAIL_CONTRADICTED"
    assert report["claims_rejected"] == 1


def test_full_answer_ai_flagged_yields_needs_review():
    """Clean claim (det=SUPPORTED) but AI flags issue → FAIL_NEEDS_REVIEW."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": "",
        "simple_answer": "",
        "key_points": [],
        "economic_reasoning": {},
        "claims": [
            {
                "claim_id": "C_ai_flag",
                "claim_text": "Because management committed to Japan, specialty growth in Asia followed.",
                "evidence_refs": ["PT-FY22"],
                "claim_type": "STRATEGIC_DIRECTION",
            }
        ],
    }
    with patch(
        "intelligence.ask_intrinsiciq.ai_claim_reviewer.review_claim",
        return_value=_ai_reject("UNSUPPORTED", "Causal inference not established."),
    ):
        report = validate_answer_with_ai(ai_answer, pkg)
    assert report["answer_status"] == "FAIL_NEEDS_REVIEW"
    assert report["claims_needs_review"] == 1


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_ei(pkg):
    from intelligence.ask_intrinsiciq.claim_validator import _build_evidence_index
    return _build_evidence_index(pkg)


def _build_mni(pkg):
    from intelligence.ask_intrinsiciq.claim_validator import _build_must_not_assert_index
    return _build_must_not_assert_index(pkg)
