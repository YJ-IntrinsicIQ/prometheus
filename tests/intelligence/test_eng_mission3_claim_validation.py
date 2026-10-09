"""
Mission 3 adversarial tests: independent claim validation audit.

Covers the confirmed validator defect classes discovered in Mission 3:
  D1. Narrative fields (why_it_matters, key_points, economic_reasoning) were
      not validated — value-hierarchy inferences could slip through.
  D2. Citation existence ≠ content match — period-attribution mismatches
      produce a warning (not a hard fail) because deterministic text-content
      matching cannot reliably distinguish paraphrase from misattribution.
  D3. must_not_assert semantic check: requires ALL key tokens to match so
      shared subject nouns don't produce false positives; limitation is that
      stem-level paraphrases are missed.

Also covers regression cases for the negation/conditional guard introduced
to handle legitimate uses of prescription-adjacent language in narrative fields.
"""
from __future__ import annotations

import pytest

from intelligence.ask_intrinsiciq.claim_validator import (
    validate_answer,
    validate_claim,
    validate_narrative_fields,
    _build_evidence_index,
    _build_must_not_assert_index,
    _check_forbidden_patterns,
)


# ── Shared fixtures ────────────────────────────────────────────────────────────

def _pkg():
    """Minimal evidence package for validation tests."""
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
                    "item_id": "PT-FY20",
                    "evidence_type": "VERIFIABLE_COMMITMENT",
                    "original_statement": "Targeting new markets like Japan for specialty products.",
                    "announcement_period": "fy20",
                    "execution_status": "CLAIM_ONLY",
                    "outcome_status": "UNVERIFIED",
                    "ai_reasoning_guidance": {
                        "may_assert": ["Management made this commitment in fy20"],
                        "must_not_assert": [
                            "prescriptions increased",
                            "commitment was fulfilled",
                            "ramp-up was successful",
                        ],
                    },
                },
                {
                    "item_id": "PT-FY21",
                    "evidence_type": "VERIFIABLE_COMMITMENT",
                    "original_statement": "Ramp-up ILUMYA prescriptions in Japan and Australia.",
                    "announcement_period": "fy21",
                    "execution_status": "CLAIM_ONLY",
                    "outcome_status": "UNVERIFIED",
                    "ai_reasoning_guidance": {
                        "may_assert": ["Management made this commitment in fy21"],
                        "must_not_assert": [
                            "prescriptions increased",
                            "commitment was fulfilled",
                        ],
                    },
                },
            ],
            "observable_execution_evidence": [
                {
                    "item_id": "OE-001",
                    "evidence_type": "PRODUCT_AVAILABILITY",
                    "excerpt": "Launched Ilumya/Ilumetri (multiple markets)",
                    "semantic_classification": {
                        "is_product_availability": True,
                        "is_prescription_ramp_verification": False,
                        "is_revenue_attribution": False,
                    },
                    "ai_reasoning_guidance": {
                        "may_assert": ["ILUMYA was launched in multiple markets"],
                        "must_not_assert": ["prescriptions ramped", "ramp succeeded"],
                    },
                }
            ],
            "business_model_context": [
                {
                    "item_id": "BC-001",
                    "evidence_type": "BUSINESS_MODEL_CONTEXT",
                    "field": "how_revenue_happens",
                    "content": "Sales of branded, generic, and specialty pharmaceutical products.",
                },
            ],
            "adverse_evidence": [
                {
                    "item_id": "AE-001",
                    "evidence_type": "ADVERSE_EVIDENCE",
                    "description": "0 of 2 verifiable commitments have later evidence.",
                }
            ],
            "strategic_intents": [],
            "source_limitations": [
                {
                    "limitation_id": "SL-001",
                    "type": "SOURCE_EVIDENCE_MISSING",
                    "description": "No prescription volume data is present in canonical sources.",
                }
            ],
        },
    }


def _ei(pkg):
    return _build_evidence_index(pkg)


def _mni(pkg):
    return _build_must_not_assert_index(pkg)


# ── D1: Narrative field validation ─────────────────────────────────────────────

def test_higher_value_specialty_in_why_it_matters_fails():
    """D1: 'higher-value specialty' is an unsupported value-hierarchy inference."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": "These moves expand geographic reach for higher-value specialty products.",
        "simple_answer": "",
        "key_points": [],
        "economic_reasoning": {},
        "claims": [],
    }
    issues = validate_narrative_fields(ai_answer, pkg)
    assert any("value hierarchy" in i["violation"].lower() for i in issues), \
        f"Expected value-hierarchy violation, got: {issues}"


def test_higher_value_specialty_in_claims_is_caught():
    """D1: Value-hierarchy phrase in a claim triggers CONTRADICTED."""
    pkg = _pkg()
    claim = {
        "claim_id": "C001",
        "claim_text": "These commitments expand access to higher-value specialty products.",
        "evidence_refs": ["PT-FY20"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    result = validate_claim(claim, _ei(pkg), _mni(pkg), [])
    assert result["verdict"] == "CONTRADICTED", \
        f"Expected CONTRADICTED for value-hierarchy phrase, got {result['verdict']}"


def test_failed_commitment_in_key_points_fails():
    """D1: Forbidden phrase in key_points is caught by narrative validation."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": "",
        "simple_answer": "",
        "key_points": ["Management commitment failed to deliver on the Japan target."],
        "economic_reasoning": {},
        "claims": [],
    }
    issues = validate_narrative_fields(ai_answer, pkg)
    assert any("UNVERIFIED" in i["violation"] or "FAILED" in i["violation"].upper()
               for i in issues), f"Expected failed-commitment violation, got: {issues}"


def test_clean_narrative_passes():
    """D1: Clean narrative produces no issues."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": "These commitments align with the stated revenue model.",
        "simple_answer": "Management made two commitments, both UNVERIFIED.",
        "key_points": ["FY20: Target Japan for specialty products (management statement)."],
        "economic_reasoning": {
            "remaining_uncertainty": "No evidence confirms prescription volumes in Japan."
        },
        "claims": [],
    }
    issues = validate_narrative_fields(ai_answer, pkg)
    assert issues == [], f"Expected no narrative issues, got: {issues}"


# ── Negation/conditional guard for narrative fields ──────────────────────────

def test_negated_prescription_growth_in_narrative_passes():
    """Guard: 'does not establish prescription growth' is a correct negation."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": "",
        "simple_answer": "",
        "key_points": [],
        "economic_reasoning": {
            "established_outcomes": (
                "PCIM shows product availability but does not establish "
                "prescription growth or revenue attribution."
            )
        },
        "claims": [],
    }
    issues = validate_narrative_fields(ai_answer, pkg)
    # Negated context should not fire — only the value-hierarchy check has no guard
    assert not any("prescription" in i["violation"].lower() for i in issues), \
        f"False positive on negated prescription context: {issues}"


def test_conditional_prescription_ramp_in_narrative_passes():
    """Guard: 'would require prescription growth' is a conditional description."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": (
            "If executed, securing prescription growth for ILUMYA in Japan "
            "would extend specialty market access."
        ),
        "simple_answer": "",
        "key_points": [],
        "economic_reasoning": {},
        "claims": [],
    }
    issues = validate_narrative_fields(ai_answer, pkg)
    assert not any("prescription" in i["violation"].lower() for i in issues), \
        f"False positive on conditional prescription context: {issues}"


# ── D2: Period attribution warnings ────────────────────────────────────────────

def test_correct_period_produces_no_warning():
    """D2: Period in claim matches evidence item — no period warning."""
    pkg = _pkg()
    claim = {
        "claim_id": "C001",
        "claim_text": "Management committed in FY20 to targeting Japan for specialty products.",
        "evidence_refs": ["PT-FY20"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    result = validate_claim(claim, _ei(pkg), _mni(pkg), [])
    period_warnings = [w for w in result["warnings"] if "Period mismatch" in w]
    assert period_warnings == [], f"Unexpected period warning: {period_warnings}"


def test_wrong_period_produces_warning():
    """D2: Claiming FY21 for a FY20 commitment produces a period-mismatch warning."""
    pkg = _pkg()
    claim = {
        "claim_id": "C001",
        "claim_text": "Management committed in FY21 to targeting Japan for specialty products.",
        "evidence_refs": ["PT-FY20"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    result = validate_claim(claim, _ei(pkg), _mni(pkg), [])
    period_warnings = [w for w in result["warnings"] if "Period mismatch" in w]
    assert period_warnings, "Expected period-mismatch warning for FY21 vs fy20 item"
    # Warning → PARTIALLY_SUPPORTED (has supporting evidence so not UNSUPPORTED)
    assert result["verdict"] == "PARTIALLY_SUPPORTED", \
        f"Expected PARTIALLY_SUPPORTED for period mismatch, got {result['verdict']}"


# ── D3: must_not_assert all-token matching ─────────────────────────────────────

def test_subject_noun_alone_does_not_fire_must_not_assert():
    """D3: 'prescriptions' alone in claim should not fire 'prescriptions increased'."""
    pkg = _pkg()
    claim = {
        "claim_id": "C001",
        "claim_text": "Management committed to ramping up ILUMYA prescriptions (FY21).",
        "evidence_refs": ["PT-FY21"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    result = validate_claim(claim, _ei(pkg), _mni(pkg), [])
    assert result["verdict"] == "SUPPORTED", \
        f"Expected SUPPORTED (subject noun alone), got {result['verdict']}"


def test_both_tokens_present_fires_must_not_assert():
    """D3: 'prescriptions increased' with both tokens present fires a violation."""
    pkg = _pkg()
    claim = {
        "claim_id": "C001",
        "claim_text": "ILUMYA prescriptions increased in Japan after the commitment.",
        "evidence_refs": ["PT-FY21"],
        "claim_type": "COMMITMENT_STATEMENT",
    }
    result = validate_claim(claim, _ei(pkg), _mni(pkg), [])
    assert result["verdict"] == "CONTRADICTED", \
        f"Expected CONTRADICTED, got {result['verdict']}"


# ── source_limitations indexing ────────────────────────────────────────────────

def test_source_limitation_ref_resolves():
    """Fix: SL-* items (limitation_id) are now indexed alongside item_id items."""
    pkg = _pkg()
    ei = _ei(pkg)
    assert "SL-001" in ei, "SL-001 should be in evidence index via limitation_id"


def test_claim_citing_source_limitation_is_supported():
    """Fix: A claim citing SL-001 is SUPPORTED (ref resolves)."""
    pkg = _pkg()
    claim = {
        "claim_id": "C013",
        "claim_text": "No prescription volume data for ILUMYA in Japan is present in canonical sources.",
        "evidence_refs": ["SL-001"],
        "claim_type": "UNCERTAINTY",
    }
    result = validate_claim(claim, _ei(pkg), _mni(pkg), [])
    assert result["verdict"] == "SUPPORTED", \
        f"Expected SUPPORTED for SL-001 ref, got {result['verdict']}"


# ── Full answer PASS / FAIL routing ───────────────────────────────────────────

def test_answer_with_narrative_violation_fails():
    """Full answer: a claim-clean answer with a narrative violation → FAIL_NARRATIVE."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": "This expands access to higher-value specialty products.",
        "simple_answer": "Management made two commitments.",
        "key_points": [],
        "economic_reasoning": {},
        "claims": [
            {
                "claim_id": "C001",
                "claim_text": "Management committed to Japan market entry in FY20.",
                "evidence_refs": ["PT-FY20"],
                "claim_type": "COMMITMENT_STATEMENT",
            }
        ],
    }
    report = validate_answer(ai_answer, pkg)
    assert report["answer_status"] == "FAIL_NARRATIVE"
    assert report["narrative_issues_count"] >= 1


def test_fully_clean_answer_passes():
    """Full answer: clean claims and clean narrative → PASS."""
    pkg = _pkg()
    ai_answer = {
        "why_it_matters": "These commitments align with the company's stated specialty revenue model.",
        "simple_answer": "Management made two tracked commitments, both UNVERIFIED.",
        "key_points": ["FY20: Target Japan for specialty products (management statement)."],
        "economic_reasoning": {
            "established_outcomes": "No verified outcomes. PCIM shows product availability, not prescription volumes."
        },
        "claims": [
            {
                "claim_id": "C001",
                "claim_text": "Management committed in FY20 to targeting Japan for specialty products.",
                "evidence_refs": ["PT-FY20"],
                "claim_type": "COMMITMENT_STATEMENT",
            },
            {
                "claim_id": "C002",
                "claim_text": "ILUMYA was launched in multiple markets per PCIM synthesis.",
                "evidence_refs": ["OE-001"],
                "claim_type": "PRODUCT_AVAILABILITY",
            },
        ],
    }
    report = validate_answer(ai_answer, pkg)
    assert report["answer_status"] == "PASS", \
        f"Expected PASS, got {report['answer_status']}; issues: {report['all_issues']}; narrative: {report['narrative_issues']}"
