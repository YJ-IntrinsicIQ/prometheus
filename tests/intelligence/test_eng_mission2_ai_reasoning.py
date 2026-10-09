"""
Mission 2 adversarial tests: evidence-grounded AI economic reasoning.

Tests validate the claim validator's ability to reject answers that violate
the 15 non-negotiable architectural rules, specifically:
- UNVERIFIED != FAILED (Rule 11)
- Product availability != prescription ramp (semantics from Rule 8)
- No causal attribution from temporal proximity (Rule 5)
- No revenue attribution without canonical evidence (Rule 8)
- No merged verifiable/strategic fulfilment percentage (Rule 9)
"""
from __future__ import annotations

import pytest
from intelligence.ask_intrinsiciq.claim_validator import validate_answer, validate_claim


# ── Minimal evidence package fixture ──────────────────────────────────────────

def _pkg():
    return {
        "package_fingerprint": "test",
        "company_slug": "test_co",
        "package_constraints": {
            "ai_reasoning_global_constraints": [],
            "silence_is_not_failure": "UNVERIFIED means no evidence — not failure.",
            "accountability_metrics": {},
        },
        "sections": {
            "verifiable_commitments": [
                {
                    "item_id": "PT-001",
                    "original_statement": "Ramp-up prescriptions in Japan",
                    "execution_status": "UNVERIFIED",
                    "outcome_status": "UNVERIFIED",
                    "ai_reasoning_guidance": {
                        "may_assert": ["commitment was stated"],
                        "must_not_assert": [
                            "prescriptions increased",
                            "commitment was fulfilled",
                            "ramp-up was successful",
                        ],
                    },
                }
            ],
            "observable_execution_evidence": [
                {
                    "item_id": "OE-001",
                    "excerpt": "ILUMYA launched in Japan",
                    "evidence_type": "PRODUCT_AVAILABILITY",
                    "semantic_classification": {
                        "is_product_availability": True,
                        "is_prescription_ramp_verification": False,
                        "is_revenue_attribution": False,
                    },
                    "ai_reasoning_guidance": {
                        "may_assert": ["product was made available"],
                        "must_not_assert": ["prescriptions grew", "ramp succeeded"],
                    },
                }
            ],
            "adverse_evidence": [],
            "strategic_intents": [],
            "business_model_context": [],
            "source_limitations": [],
        },
    }


def _evidence_index(pkg):
    from intelligence.ask_intrinsiciq.claim_validator import _build_evidence_index
    return _build_evidence_index(pkg)


def _must_not_index(pkg):
    from intelligence.ask_intrinsiciq.claim_validator import _build_must_not_assert_index
    return _build_must_not_assert_index(pkg)


# ── 1. UNVERIFIED != FAILED ────────────────────────────────────────────────────

def test_failed_commitment_phrase_is_contradicted():
    pkg = _pkg()
    claim = {
        "claim_id": "C001",
        "claim_text": "Management did not deliver on its commitment and failed to achieve the ramp-up target.",
        "evidence_refs": ["PT-001"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    result = validate_claim(claim, _evidence_index(pkg), _must_not_index(pkg), [])
    assert result["verdict"] == "CONTRADICTED", f"Expected CONTRADICTED, got {result['verdict']}"


def test_unverified_correctly_stated_is_supported():
    pkg = _pkg()
    claim = {
        "claim_id": "C001",
        "claim_text": "Management committed to ramping up ILUMYA prescriptions; this commitment is unverified — no later evidence confirms or refutes it.",
        "evidence_refs": ["PT-001"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    result = validate_claim(claim, _evidence_index(pkg), _must_not_index(pkg), [])
    assert result["verdict"] == "SUPPORTED", f"Expected SUPPORTED, got {result['verdict']}"


# ── 2. Product availability != prescription ramp ──────────────────────────────

def test_prescription_ramp_asserted_from_launch_is_contradicted():
    pkg = _pkg()
    claim = {
        "claim_id": "C002",
        "claim_text": "Following the product launch, prescription volumes grew steadily as the ramp-up was successful.",
        "evidence_refs": ["OE-001"],
        "claim_type": "PRODUCT_AVAILABILITY",
    }
    result = validate_claim(claim, _evidence_index(pkg), _must_not_index(pkg), [])
    assert result["verdict"] == "CONTRADICTED"


def test_product_availability_only_claim_is_supported():
    pkg = _pkg()
    claim = {
        "claim_id": "C002",
        "claim_text": "The product was made available in Japan, establishing market presence.",
        "evidence_refs": ["OE-001"],
        "claim_type": "PRODUCT_AVAILABILITY",
    }
    result = validate_claim(claim, _evidence_index(pkg), _must_not_index(pkg), [])
    assert result["verdict"] in ("SUPPORTED", "PARTIALLY_SUPPORTED")


# ── 3. Revenue attribution without evidence ───────────────────────────────────

def test_revenue_attribution_phrase_is_contradicted():
    pkg = _pkg()
    claim = {
        "claim_id": "C003",
        "claim_text": "The ILUMYA ramp generated revenue and contributed revenue to the specialty segment.",
        "evidence_refs": ["OE-001"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    result = validate_claim(claim, _evidence_index(pkg), _must_not_index(pkg), [])
    assert result["verdict"] == "CONTRADICTED"


# ── 4. Unresolved refs are unsupported ────────────────────────────────────────

def test_nonexistent_ref_is_unsupported():
    pkg = _pkg()
    claim = {
        "claim_id": "C004",
        "claim_text": "Management stated a target for MENA expansion.",
        "evidence_refs": ["PT-NONEXISTENT"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    result = validate_claim(claim, _evidence_index(pkg), _must_not_index(pkg), [])
    assert result["verdict"] in ("UNSUPPORTED", "CONTRADICTED")
    assert any("Unresolved evidence refs" in i for i in result["issues"])


# ── 5. Full answer with mixed valid/invalid claims ────────────────────────────

def test_validate_answer_fails_on_contradicted_claim():
    pkg = _pkg()
    ai_answer = {
        "claims": [
            {
                "claim_id": "C001",
                "claim_text": "Commitment was met and fulfillment was confirmed.",
                "evidence_refs": ["PT-001"],
                "claim_type": "COMMITMENT_STATEMENT",
            }
        ]
    }
    report = validate_answer(ai_answer, pkg)
    assert report["answer_status"] != "PASS"
    assert report["verdict_summary"]["CONTRADICTED"] >= 1


def test_validate_answer_passes_on_clean_claims():
    pkg = _pkg()
    ai_answer = {
        "claims": [
            {
                "claim_id": "C001",
                "claim_text": "Management stated the commitment; verification status remains open.",
                "evidence_refs": ["PT-001"],
                "claim_type": "COMMITMENT_STATEMENT",
            },
            {
                "claim_id": "C002",
                "claim_text": "The product was made available in Japan per PCIM evidence.",
                "evidence_refs": ["OE-001"],
                "claim_type": "PRODUCT_AVAILABILITY",
            },
        ]
    }
    report = validate_answer(ai_answer, pkg)
    assert report["answer_status"] == "PASS"
    assert report["verdict_summary"]["CONTRADICTED"] == 0
    assert report["verdict_summary"]["UNSUPPORTED"] == 0
