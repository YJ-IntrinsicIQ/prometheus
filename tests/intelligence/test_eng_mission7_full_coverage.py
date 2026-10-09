"""
Mission 7 tests — Complete Claim Coverage & Candidate Approval.

Covers:
  - EVIDENCE_GAP_STATEMENT extraction from evidence_gaps field
  - Evidence-gap reviewer uses absence-aware system prompt
  - Declared ECONOMIC_INTERPRETATION claim with commitment + BMC refs → ACCEPT
  - Declared UNCERTAINTY claim with SL-*/AE-* refs → ACCEPT
  - Evidence-gap reviewer: package confirms absence → SUPPORTED
  - Evidence-gap reviewer: package contradicts absence claim → UNSUPPORTED
  - Evidence-gap reviewer: overstated scope → PARTIALLY_SUPPORTED
  - Validator: EVIDENCE_GAP_STATEMENT skips "no refs" warning
  - Regression: claim_type enum includes EVIDENCE_GAP_STATEMENT
  - Regression: evidence_gaps present in extraction prompt
  - Regression: prior Mission 6 fixes still in place (Rules 8, 9)
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, ".")

from intelligence.ask_intrinsiciq.claim_extractor import (
    _EXTRACTION_SCHEMA,
    _EXTRACTOR_SYSTEM_PROMPT,
    _build_extraction_prompt,
)
from intelligence.ask_intrinsiciq.claim_validator import (
    ACCEPT,
    NEEDS_REVIEW,
    REJECT,
    _build_evidence_index,
    validate_claim,
)
from intelligence.ask_intrinsiciq.ai_claim_reviewer import (
    _EVIDENCE_GAP_REVIEWER_SYSTEM_PROMPT,
    _REVIEWER_SYSTEM_PROMPT,
    review_claim,
)
from intelligence.ask_intrinsiciq.evidence_reasoner import _SYSTEM_PROMPT


# ── Fixtures ──────────────────────────────────────────────────────────────────

_EVIDENCE_PKG = {
    "sections": {
        "verifiable_commitments": [
            {
                "item_id": "PT-0003",
                "original_statement": "Targeting new markets like Japan and China for our specialty products.",
                "announcement_period": "fy20",
                "execution_status": "CLAIM_ONLY",
                "outcome_status": "UNVERIFIED",
                "later_evidence": [],
                "ai_reasoning_guidance": {"may_assert": [], "must_not_assert": []},
            },
            {
                "item_id": "PT-0004",
                "original_statement": "Ramp-up ILUMYA prescriptions in Japan and Australia.",
                "announcement_period": "fy21",
                "execution_status": "CLAIM_ONLY",
                "outcome_status": "UNVERIFIED",
                "later_evidence": [],
                "ai_reasoning_guidance": {"may_assert": [], "must_not_assert": []},
            },
        ],
        "business_model_context": [
            {
                "item_id": "BC-CM-001",
                "field": "revenue_model",
                "content": "Sales of branded, generic, and specialty pharmaceutical products.",
            },
        ],
        "adverse_evidence": [
            {
                "item_id": "AE-GOLD-001",
                "description": "PT-0004: unresolved_reason=NO_MATCHING_PROGRESSION_RECORD.",
                "evidence_type": "ADVERSE_EVIDENCE",
            },
            {
                "item_id": "AE-GOLD-002",
                "description": "All 30 tracked material promises have outcome_status=UNVERIFIED.",
                "evidence_type": "ADVERSE_EVIDENCE",
            },
        ],
        "source_limitations": [
            {
                "limitation_id": "SL-001",
                "type": "SOURCE_EVIDENCE_MISSING",
                "description": "No prescription volume data for ILUMYA in Japan or Australia is present in any canonical source.",
            },
            {
                "limitation_id": "SL-002",
                "type": "CANONICAL_RELATIONSHIP_MISSING",
                "description": "linked_company_model_ids=[] for PT-0004. No economic linkage can be established.",
            },
        ],
    },
    "package_constraints": {
        "ai_reasoning_global_constraints": [],
        "accountability_metrics": {"material_verifiable_commitments": 2},
    },
}


def _mock_llm_response(text: str):
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.text = text
    mock_llm.generate.return_value = mock_response
    return mock_llm


# ── TestEvidenceGapExtraction ─────────────────────────────────────────────────

class TestEvidenceGapExtraction:
    """evidence_gaps field is now included in extraction, not excluded."""

    def test_evidence_gap_statement_in_schema_enum(self):
        enum_values = (
            _EXTRACTION_SCHEMA["properties"]["extracted_claims"]["items"]
            ["properties"]["claim_type"]["enum"]
        )
        assert "EVIDENCE_GAP_STATEMENT" in enum_values

    def test_extraction_prompt_includes_evidence_gaps(self):
        answer = {
            "simple_answer": "Management committed to X.",
            "evidence_gaps": ["No prescription volume data for ILUMYA in Japan."],
            "claims": [],
        }
        prompt = _build_extraction_prompt(answer, [], [])
        assert "evidence_gaps" in prompt
        assert "No prescription volume data" in prompt

    def test_extraction_system_prompt_explains_absence_type(self):
        assert "EVIDENCE_GAP_STATEMENT" in _EXTRACTOR_SYSTEM_PROMPT
        assert "ABSENT" in _EXTRACTOR_SYSTEM_PROMPT or "absent" in _EXTRACTOR_SYSTEM_PROMPT

    def test_extraction_prompt_absent_no_longer_excluded(self):
        # Prior exclusion comment should be gone
        from intelligence.ask_intrinsiciq import claim_extractor
        import inspect
        src = inspect.getsource(claim_extractor._build_extraction_prompt)
        assert "intentionally excluded" not in src

    def test_extraction_schema_backward_compat(self):
        # All Mission 5/6 types still present
        enum_values = (
            _EXTRACTION_SCHEMA["properties"]["extracted_claims"]["items"]
            ["properties"]["claim_type"]["enum"]
        )
        for t in ["COMMITMENT_STATEMENT", "STRATEGIC_DIRECTION", "PRODUCT_AVAILABILITY",
                  "ECONOMIC_INTERPRETATION", "EXECUTION_GAP", "UNCERTAINTY", "BUSINESS_CONTEXT"]:
            assert t in enum_values, f"Missing claim_type: {t}"


# ── TestEvidenceGapReviewer ───────────────────────────────────────────────────

class TestEvidenceGapReviewer:
    """Evidence-gap reviewer uses absence-aware system prompt."""

    def test_evidence_gap_reviewer_prompt_exists(self):
        assert _EVIDENCE_GAP_REVIEWER_SYSTEM_PROMPT
        assert "ABSENT" in _EVIDENCE_GAP_REVIEWER_SYSTEM_PROMPT or "absent" in _EVIDENCE_GAP_REVIEWER_SYSTEM_PROMPT

    def test_evidence_gap_reviewer_distinct_from_positive_reviewer(self):
        assert _EVIDENCE_GAP_REVIEWER_SYSTEM_PROMPT != _REVIEWER_SYSTEM_PROMPT

    def test_review_claim_uses_gap_prompt_for_evidence_gap_type(self):
        """review_claim uses _EVIDENCE_GAP_REVIEWER_SYSTEM_PROMPT when claim_type=EVIDENCE_GAP_STATEMENT."""
        mock_llm = _mock_llm_response(
            '{"verdict":"SUPPORTED","confidence":"HIGH","reason":"Absence confirmed by SL-001.","scope_issues":[],"qualifications_missing":[]}'
        )
        claim = {
            "claim_id": "C001",
            "claim_text": "No prescription volume data for ILUMYA in Japan is present in canonical sources.",
            "claim_type": "EVIDENCE_GAP_STATEMENT",
            "evidence_refs": ["SL-001"],
        }
        sl_item = _EVIDENCE_PKG["sections"]["source_limitations"][0]
        with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=mock_llm):
            result = review_claim(claim, [sl_item])
        # Verify the evidence-gap system prompt was used (not the positive-claim prompt)
        call_kwargs = mock_llm.generate.call_args[1]
        system_used = call_kwargs.get("system_prompt", "")
        assert "ABSENT" in system_used or "absence" in system_used.lower(), \
            "Expected evidence-gap system prompt"
        assert result["verdict"] == "SUPPORTED"

    def test_review_claim_uses_standard_prompt_for_positive_claim(self):
        mock_llm = _mock_llm_response(
            '{"verdict":"SUPPORTED","confidence":"HIGH","reason":"Supported by PT-0003.","scope_issues":[],"qualifications_missing":[]}'
        )
        claim = {
            "claim_id": "C001",
            "claim_text": "Management stated it was targeting Japan for specialty products.",
            "claim_type": "COMMITMENT_STATEMENT",
            "evidence_refs": ["PT-0003"],
        }
        vc_item = _EVIDENCE_PKG["sections"]["verifiable_commitments"][0]
        with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=mock_llm):
            result = review_claim(claim, [vc_item])
        call_kwargs = mock_llm.generate.call_args[1]
        system_used = call_kwargs.get("system_prompt", "")
        # Should NOT use the gap prompt
        assert "ABSENT" not in system_used or "evaluate whether this claim is genuinely supported" in system_used.lower()

    def test_absence_confirmed_returns_supported(self):
        mock_llm = _mock_llm_response(
            '{"verdict":"SUPPORTED","confidence":"HIGH","reason":"SL-001 explicitly states no prescription volume data.","scope_issues":[],"qualifications_missing":[]}'
        )
        claim = {
            "claim_id": "C-GAP-001",
            "claim_text": "No prescription volume data for ILUMYA in Japan or Australia is present in canonical sources.",
            "claim_type": "EVIDENCE_GAP_STATEMENT",
            "evidence_refs": ["SL-001"],
        }
        with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=mock_llm):
            result = review_claim(claim, [_EVIDENCE_PKG["sections"]["source_limitations"][0]])
        assert result["verdict"] == "SUPPORTED"

    def test_overstated_scope_returns_partially_supported(self):
        mock_llm = _mock_llm_response(
            '{"verdict":"PARTIALLY_SUPPORTED","confidence":"MEDIUM","reason":"Package confirms absence within scope, but claim asserts company has never disclosed this.","scope_issues":["Scope exceeds package bounds"],"qualifications_missing":[]}'
        )
        claim = {
            "claim_id": "C-GAP-002",
            "claim_text": "Sun Pharma has never publicly disclosed prescription volume data for ILUMYA.",
            "claim_type": "EVIDENCE_GAP_STATEMENT",
            "evidence_refs": ["SL-001"],
        }
        with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=mock_llm):
            result = review_claim(claim, [_EVIDENCE_PKG["sections"]["source_limitations"][0]])
        assert result["verdict"] == "PARTIALLY_SUPPORTED"

    def test_contradicted_absence_returns_unsupported(self):
        mock_llm = _mock_llm_response(
            '{"verdict":"UNSUPPORTED","confidence":"HIGH","reason":"The evidence item explicitly provides the data described as absent.","scope_issues":[],"qualifications_missing":[]}'
        )
        claim = {
            "claim_id": "C-GAP-BAD",
            "claim_text": "No information about ILUMYA is present in the package.",
            "claim_type": "EVIDENCE_GAP_STATEMENT",
            "evidence_refs": [],
        }
        fake_item = {
            "item_id": "OE-001",
            "excerpt": "ILUMYA/Ilumetri launched in multiple markets.",
        }
        with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=mock_llm):
            result = review_claim(claim, [fake_item])
        assert result["verdict"] == "UNSUPPORTED"


# ── TestDeclaredCoverageRules ─────────────────────────────────────────────────

class TestDeclaredCoverageRules:
    """Rules 10/11/12: why_it_matters, uncertainty, and gap claims declared in claims[]."""

    def test_rule_10_in_system_prompt(self):
        assert "why_it_matters" in _SYSTEM_PROMPT
        assert "ECONOMIC_INTERPRETATION" in _SYSTEM_PROMPT

    def test_rule_11_in_system_prompt(self):
        assert "remaining_uncertainty" in _SYSTEM_PROMPT
        assert "UNCERTAINTY" in _SYSTEM_PROMPT
        assert "SL-" in _SYSTEM_PROMPT or "SL-*" in _SYSTEM_PROMPT

    def test_rule_12_in_system_prompt(self):
        assert "EVIDENCE_GAP_STATEMENT" in _SYSTEM_PROMPT
        assert "evidence_gaps" in _SYSTEM_PROMPT

    def test_economic_interpretation_declared_with_refs_passes_det(self):
        """ECONOMIC_INTERPRETATION claim with commitment + BMC refs passes deterministic check."""
        evidence_index = _build_evidence_index(_EVIDENCE_PKG)
        claim = {
            "claim_id": "C-EI-001",
            "claim_text": (
                "The management commitments to target Japan/China for specialty products (PT-0003) "
                "and ramp ILUMYA prescriptions in Japan/Australia (PT-0004) align with the company's "
                "revenue model of branded and specialty pharmaceutical sales (BC-CM-001)."
            ),
            "claim_type": "ECONOMIC_INTERPRETATION",
            "evidence_refs": ["PT-0003", "PT-0004", "BC-CM-001"],
        }
        result = validate_claim(claim, evidence_index, {}, [])
        assert result["verdict"] not in ("CONTRADICTED", "UNSUPPORTED"), \
            f"Expected SUPPORTED/PARTIALLY_SUPPORTED, got {result['verdict']}: {result['issues']}"

    def test_uncertainty_claim_declared_with_sl_ae_refs_passes_det(self):
        """UNCERTAINTY claim citing SL-001, AE-GOLD-001, AE-GOLD-002 passes deterministic check."""
        evidence_index = _build_evidence_index(_EVIDENCE_PKG)
        claim = {
            "claim_id": "C-UNC-001",
            "claim_text": (
                "Both FY20 and FY21 commitments have outcome_status=UNVERIFIED (AE-GOLD-002). "
                "No prescription-volume data for ILUMYA in Japan/Australia is present (SL-001). "
                "No progression record links the ILUMYA ramp-up to tracked execution (AE-GOLD-001)."
            ),
            "claim_type": "UNCERTAINTY",
            "evidence_refs": ["SL-001", "AE-GOLD-001", "AE-GOLD-002"],
        }
        result = validate_claim(claim, evidence_index, {}, [])
        assert result["verdict"] not in ("CONTRADICTED", "UNSUPPORTED"), \
            f"Expected SUPPORTED/PARTIALLY_SUPPORTED, got {result['verdict']}: {result['issues']}"

    def test_evidence_gap_claim_no_refs_warning_suppressed(self):
        """EVIDENCE_GAP_STATEMENT without refs should NOT trigger 'no evidence_refs' warning."""
        evidence_index = _build_evidence_index(_EVIDENCE_PKG)
        claim = {
            "claim_id": "C-EG-001",
            "claim_text": "Prescription-volume data for ILUMYA in Japan and Australia is absent.",
            "claim_type": "EVIDENCE_GAP_STATEMENT",
            "evidence_refs": [],
        }
        result = validate_claim(claim, evidence_index, {}, [])
        # Should not warn about missing refs for this type
        assert not any("no evidence_refs" in w.lower() for w in result["warnings"]), \
            f"Unexpected warning: {result['warnings']}"


# ── TestRule9Regression ───────────────────────────────────────────────────────

class TestMission6Regressions:
    """Ensure Mission 6 fixes are still in place."""

    def test_rule_8_in_system_prompt(self):
        assert "traceable to an evidence_ref" in _SYSTEM_PROMPT or "MUST be traceable" in _SYSTEM_PROMPT

    def test_rule_9_in_system_prompt(self):
        assert "past-tense" in _SYSTEM_PROMPT or "past-tense framing" in _SYSTEM_PROMPT

    def test_no_higher_value_specialty_phrase_allowed(self):
        from intelligence.ask_intrinsiciq.claim_validator import _VALUE_HIERARCHY_PHRASES
        assert any("higher-value" in p for p in _VALUE_HIERARCHY_PHRASES), \
            "higher-value specialty should remain in forbidden list"

    def test_answer_schema_has_all_required_fields(self):
        from intelligence.ask_intrinsiciq.evidence_reasoner import ANSWER_SCHEMA
        required = ANSWER_SCHEMA.get("required", [])
        for f in ["simple_answer", "why_it_matters", "key_points", "economic_reasoning",
                  "claims", "evidence_gaps", "investor_action_items"]:
            assert f in required, f"Missing required field in ANSWER_SCHEMA: {f}"

    def test_evidence_gap_stmt_not_in_value_hierarchy_forbidden(self):
        """EVIDENCE_GAP_STATEMENT claims should not be caught by value hierarchy detector."""
        from intelligence.ask_intrinsiciq.claim_validator import _check_forbidden_patterns
        text = "No prescription volume data for ILUMYA in Japan is present in canonical sources."
        issues = _check_forbidden_patterns(text)
        assert not issues, f"Unexpected forbidden pattern in gap statement: {issues}"

    def test_imports_unchanged(self):
        """Existing public API unchanged."""
        from intelligence.ask_intrinsiciq.claim_validator import validate_answer_complete
        from intelligence.ask_intrinsiciq.claim_extractor import extract_claims
        from intelligence.ask_intrinsiciq.ai_claim_reviewer import review_claim
        from intelligence.ask_intrinsiciq.evidence_reasoner import generate_ai_answer
        assert all([validate_answer_complete, extract_claims, review_claim, generate_ai_answer])
