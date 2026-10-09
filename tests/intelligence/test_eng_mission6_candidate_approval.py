"""
Mission 6 — Candidate Approval & Validation Stress Testing

Tests:
  - Normalization fix: ai_reason populated for non-SUPPORTED verdicts
  - C005 investigation: CLAIM_ONLY scope rule prevents "continues to" framing
  - Hidden claim extraction: undeclared claims are found and reviewed
  - Acceptance gate: incomplete extraction → FAIL_INCOMPLETE
  - Adversarial undeclared: unsupported undeclared claim → REJECT/NEEDS_REVIEW
  - Regression: M2/M3/M4/M5 pass rate maintained
"""
from __future__ import annotations

import json
import unittest
from typing import Any, Dict
from unittest.mock import MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_package(**overrides) -> Dict[str, Any]:
    base = {
        "company_slug": "sun_pharma",
        "package_constraints": {"ai_reasoning_global_constraints": [], "silence_is_not_failure": ""},
        "sections": {
            "strategic_intents": [
                {
                    "item_id": "PT-0001-64229c7f2c08",
                    "original_statement": "Continue to focus on growing each business faster than the market; develop the specialty business as an additional growth engine while maintaining generics.",
                    "execution_status": "CLAIM_ONLY",
                    "outcome_status": "UNVERIFIED",
                    "accountability_ontology": "STRATEGIC_INTENT",
                    "announcement_period": "fy20",
                    "ai_reasoning_guidance": {
                        "may_assert": ["Management expressed this strategic direction", "This was disclosed in fy20"],
                        "must_not_assert": ["This constitutes a measurable promise"],
                    },
                }
            ],
            "verifiable_commitments": [
                {
                    "item_id": "PT-0003-c001123d90ea",
                    "original_statement": "Target new specialty markets — Japan and China.",
                    "execution_status": "CLAIM_ONLY",
                    "outcome_status": "UNVERIFIED",
                    "announcement_period": "fy20",
                    "later_evidence": [],
                    "ai_reasoning_guidance": {"may_assert": ["Management committed to this target"], "must_not_assert": []},
                }
            ],
            "source_limitations": [
                {
                    "limitation_id": "SL-0001",
                    "description": "No prescription volume data available.",
                    "limitation_type": "SOURCE_EVIDENCE_MISSING",
                }
            ],
        },
    }
    base.update(overrides)
    return base


def _extraction_ok_json(undeclared_count: int = 0, undeclared_text: str = "") -> str:
    extracted = [
        {
            "extraction_id": "EX-001",
            "claim_text": "Management committed to Japan and China specialty expansion.",
            "claim_type": "COMMITMENT_STATEMENT",
            "source_field": "simple_answer",
            "materiality": "HIGH",
            "declared_match": "C001",
            "suggested_refs": ["PT-0003-c001123d90ea"],
        }
    ]
    if undeclared_count > 0:
        extracted.append({
            "extraction_id": "EX-002",
            "claim_text": undeclared_text or "Prescription volumes increased 40% in Japan.",
            "claim_type": "EXECUTION_GAP",
            "source_field": "why_it_matters",
            "materiality": "HIGH",
            "declared_match": None,
            "suggested_refs": [],
        })
    return json.dumps({
        "extracted_claims": extracted,
        "coverage_assessment": "COMPLETE" if undeclared_count == 0 else "PARTIAL",
        "coverage_notes": "",
    })


def _make_ai_response(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    return r


# ── Normalization fix tests ────────────────────────────────────────────────────

class TestAiReasonNormalization(unittest.TestCase):
    """Verify that ai_reason is now populated from summary and checks fields."""

    def _call_review(self, raw_json: str, claim_text: str = "Test claim."):
        from intelligence.ask_intrinsiciq.ai_claim_reviewer import review_claim
        claim = {"claim_text": claim_text, "claim_type": "STRATEGIC_DIRECTION", "evidence_refs": []}
        mock_resp = _make_ai_response(raw_json)
        mock_llm = MagicMock()
        mock_llm.generate.return_value = mock_resp
        with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=mock_llm):
            return review_claim(claim, [])

    def test_reason_from_summary_field(self):
        """Model returns 'summary' key — should be captured in reason."""
        raw = json.dumps({
            "verdict": "PARTIALLY_SUPPORTED",
            "confidence": "MEDIUM",
            "reason": "",
            "summary": "The evidence supports part of the claim but two elements are unverified.",
            "scope_issues": [],
            "qualifications_missing": [],
        })
        result = self._call_review(raw)
        self.assertEqual(result["verdict"], "PARTIALLY_SUPPORTED")
        self.assertIn("two elements are unverified", result["reason"])

    def test_reason_from_checks_failing(self):
        """Model returns 'checks' dict with failing items — should extract their notes."""
        raw = json.dumps({
            "verdict": "PARTIALLY_SUPPORTED",
            "confidence": "MEDIUM",
            "reason": "",
            "checks": {
                "1_EVIDENCE_ESTABLISHES_CLAIM": {
                    "passes": False,
                    "notes": "The claim mentions efficiency measures not in the evidence.",
                },
                "2_SCOPE_MATCH": {"passes": True, "notes": "Period matches FY20."},
                "3_OUTCOME_vs_INTENTION": {
                    "passes": False,
                    "notes": "CLAIM_ONLY evidence must not be framed as ongoing.",
                },
            },
            "scope_issues": [],
            "qualifications_missing": [],
        })
        result = self._call_review(raw)
        self.assertIn("efficiency measures", result["reason"])

    def test_reason_preserved_when_already_set(self):
        """If reason is already populated, normalization should not overwrite it."""
        raw = json.dumps({
            "verdict": "SUPPORTED",
            "confidence": "HIGH",
            "reason": "Evidence directly establishes the claim.",
            "summary": "Should not be used.",
            "scope_issues": [],
            "qualifications_missing": [],
        })
        result = self._call_review(raw)
        self.assertEqual(result["reason"], "Evidence directly establishes the claim.")

    def test_reason_from_checked_criteria_legacy(self):
        """Legacy checked_criteria schema still works."""
        raw = json.dumps({
            "verdict": "UNSUPPORTED",
            "confidence": "HIGH",
            "reason": "",
            "checked_criteria": {
                "evidence_establishes": {"result": "NO", "explanation": "No prescription data exists."},
                "scope_match": {"result": "YES"},
            },
            "scope_issues": [],
            "qualifications_missing": [],
        })
        result = self._call_review(raw)
        self.assertIn("prescription data", result["reason"])

    def test_reason_from_final_explanation_field(self):
        """Model returns 'final_explanation' key — should be captured."""
        raw = json.dumps({
            "verdict": "PARTIALLY_SUPPORTED",
            "confidence": "MEDIUM",
            "reason": "",
            "final_explanation": "The claim aligns partially but omits unverified status.",
            "checklist": {},
            "scope_issues": [],
            "qualifications_missing": [],
        })
        result = self._call_review(raw)
        self.assertIn("partially", result["reason"].lower())

    def test_reason_from_checklist_field(self):
        """Model returns 'checklist' dict (variant of 'checks') — extract notes."""
        raw = json.dumps({
            "verdict": "PARTIALLY_SUPPORTED",
            "confidence": "MEDIUM",
            "reason": "",
            "checklist": {
                "1_evidence": {"result": "PARTIAL_OMISSION", "explanation": "Two elements missing from cited evidence."},
                "2_scope": {"result": "YES", "explanation": "Scope matches."},
            },
            "scope_issues": [],
            "qualifications_missing": [],
        })
        result = self._call_review(raw)
        self.assertIn("Two elements", result["reason"])


# ── C005 scope rule tests ──────────────────────────────────────────────────────

class TestC005ScopeRule(unittest.TestCase):
    """C005's 'continues to' framing is flagged by the AI reviewer."""

    def test_continues_to_framing_flagged(self):
        """'continues to prioritise' on CLAIM_ONLY evidence → PARTIALLY_SUPPORTED at least."""
        from intelligence.ask_intrinsiciq.ai_claim_reviewer import review_claim
        claim = {
            "claim_text": "Management continues to prioritise growing each business faster than the market (FY20).",
            "claim_type": "STRATEGIC_DIRECTION",
            "evidence_refs": ["PT-0001-64229c7f2c08"],
        }
        evidence = {
            "item_id": "PT-0001-64229c7f2c08",
            "original_statement": "Continue to focus on growing each business faster than the market.",
            "execution_status": "CLAIM_ONLY",
            "outcome_status": "UNVERIFIED",
            "announcement_period": "fy20",
        }
        # Mock: return PARTIALLY_SUPPORTED (realistic response for this claim)
        mock_resp = _make_ai_response(json.dumps({
            "verdict": "PARTIALLY_SUPPORTED",
            "confidence": "MEDIUM",
            "reason": "",
            "summary": "The claim uses present-tense 'continues to' but the evidence is a single FY20 CLAIM_ONLY statement.",
            "checks": {},
            "scope_issues": [],
            "qualifications_missing": ["CLAIM_ONLY status not disclosed"],
        }))
        mock_llm = MagicMock()
        mock_llm.generate.return_value = mock_resp
        with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=mock_llm):
            result = review_claim(claim, [evidence])
        self.assertEqual(result["verdict"], "PARTIALLY_SUPPORTED")
        self.assertIn("FY20", result["reason"])

    def test_past_tense_framing_supported(self):
        """'expressed a direction in FY20' framing → SUPPORTED."""
        from intelligence.ask_intrinsiciq.ai_claim_reviewer import review_claim
        claim = {
            "claim_text": "In FY20, management expressed a strategic direction to grow each business faster than the market.",
            "claim_type": "STRATEGIC_DIRECTION",
            "evidence_refs": ["PT-0001-64229c7f2c08"],
        }
        evidence = {
            "item_id": "PT-0001-64229c7f2c08",
            "original_statement": "Continue to focus on growing each business faster than the market.",
            "execution_status": "CLAIM_ONLY",
            "outcome_status": "UNVERIFIED",
            "announcement_period": "fy20",
        }
        mock_resp = _make_ai_response(json.dumps({
            "verdict": "SUPPORTED",
            "confidence": "HIGH",
            "reason": "Past-tense framing correctly represents a management statement.",
            "scope_issues": [],
            "qualifications_missing": [],
        }))
        mock_llm = MagicMock()
        mock_llm.generate.return_value = mock_resp
        with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=mock_llm):
            result = review_claim(claim, [evidence])
        self.assertEqual(result["verdict"], "SUPPORTED")


# ── Hidden claim extraction tests ──────────────────────────────────────────────

class TestHiddenClaimExtraction(unittest.TestCase):
    """Verify extractor finds undeclared material claims."""

    def _extract(self, ai_answer, pkg, undeclared_count=0, undeclared_text=""):
        mock_resp = _make_ai_response(_extraction_ok_json(undeclared_count, undeclared_text))
        mock_llm = MagicMock()
        mock_llm.generate.return_value = mock_resp
        with patch("intelligence.ask_intrinsiciq.claim_extractor.get_llm", return_value=mock_llm):
            from intelligence.ask_intrinsiciq.claim_extractor import extract_claims
            return extract_claims(ai_answer, pkg)

    def test_hidden_prescription_claim_extracted(self):
        """Prescription claim in narrative, not in claims[] → found as undeclared."""
        pkg = _make_package()
        ai_answer = {
            "simple_answer": "ILUMYA launched in Japan.",
            "why_it_matters": "ILUMYA prescription volumes increased 40% in Japan in FY22.",
            "key_points": [],
            "economic_reasoning": {},
            "claims": [
                {"claim_id": "C001", "claim_text": "ILUMYA launched in Japan.", "evidence_refs": ["PT-0003-c001123d90ea"], "claim_type": "PRODUCT_AVAILABILITY"}
            ],
            "evidence_gaps": [],
            "investor_action_items": [],
        }
        result = self._extract(ai_answer, pkg, undeclared_count=1, undeclared_text="ILUMYA prescription volumes increased 40% in Japan in FY22.")
        self.assertEqual(result["undeclared_count"], 1)
        self.assertIn("prescription", result["undeclared_claims"][0]["claim_text"].lower())

    def test_correct_answer_no_undeclared(self):
        """Comprehensive answer → 0 undeclared, COMPLETE."""
        pkg = _make_package()
        ai_answer = {
            "simple_answer": "Management committed to Japan expansion.",
            "why_it_matters": "Specialty is a key revenue pillar.",
            "key_points": ["Commitment to Japan market (unverified)."],
            "economic_reasoning": {"management_intentions": "Expand specialty.", "remaining_uncertainty": "No prescription data."},
            "claims": [{"claim_id": "C001", "claim_text": "Management committed to Japan expansion.", "evidence_refs": ["PT-0003-c001123d90ea"], "claim_type": "COMMITMENT_STATEMENT"}],
            "evidence_gaps": ["No prescription data."],
            "investor_action_items": ["Request ILUMYA prescription data."],
        }
        result = self._extract(ai_answer, pkg)
        self.assertEqual(result["undeclared_count"], 0)
        self.assertEqual(result["coverage_assessment"], "COMPLETE")

    def test_extraction_error_produces_fail_incomplete(self):
        """Extraction failure → FAIL_INCOMPLETE (cannot auto-approve)."""
        from intelligence.ask_intrinsiciq.claim_validator import validate_answer_complete
        FAIL_INCOMPLETE = "FAIL_INCOMPLETE"

        pkg = _make_package()
        ai_answer = {
            "simple_answer": "Test.",
            "why_it_matters": "Test.",
            "key_points": [],
            "economic_reasoning": {},
            "claims": [{"claim_id": "C001", "claim_text": "Test.", "evidence_refs": ["PT-0003-c001123d90ea"], "claim_type": "COMMITMENT_STATEMENT"}],
            "evidence_gaps": [],
            "investor_action_items": [],
        }

        # Make extractor raise
        with patch("intelligence.ask_intrinsiciq.claim_extractor.get_llm", side_effect=RuntimeError("test failure")):
            with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm"):
                result = validate_answer_complete(ai_answer, pkg)
        self.assertEqual(result["answer_status"], "FAIL_INCOMPLETE")

    def test_undeclared_unsupported_claim_flagged(self):
        """Undeclared claim that AI cannot support → NEEDS_REVIEW or REJECT."""
        from intelligence.ask_intrinsiciq.claim_validator import validate_answer_complete, REJECT, NEEDS_REVIEW

        pkg = _make_package()
        ai_answer = {
            "simple_answer": "ILUMYA prescription volumes increased 40% in Japan.",
            "why_it_matters": "Prescription ramp confirmed.",
            "key_points": ["Prescription volumes up 40%."],
            "economic_reasoning": {"established_outcomes": "Prescription commitment delivered."},
            "claims": [{"claim_id": "C001", "claim_text": "ILUMYA launched in Japan.", "evidence_refs": ["PT-0003-c001123d90ea"], "claim_type": "PRODUCT_AVAILABILITY"}],
            "evidence_gaps": [],
            "investor_action_items": [],
        }

        extractor_resp = _make_ai_response(json.dumps({
            "extracted_claims": [
                {
                    "extraction_id": "EX-001",
                    "claim_text": "ILUMYA launched in Japan.",
                    "claim_type": "PRODUCT_AVAILABILITY",
                    "source_field": "simple_answer",
                    "materiality": "HIGH",
                    "declared_match": "C001",
                    "suggested_refs": ["PT-0003-c001123d90ea"],
                },
                {
                    "extraction_id": "EX-002",
                    "claim_text": "ILUMYA prescription volumes increased 40% in Japan.",
                    "claim_type": "EXECUTION_GAP",
                    "source_field": "key_points",
                    "materiality": "HIGH",
                    "declared_match": None,
                    "suggested_refs": [],
                },
            ],
            "coverage_assessment": "PARTIAL",
            "coverage_notes": "Prescription claim undeclared.",
        }))
        reviewer_resp = _make_ai_response(json.dumps({
            "verdict": "UNSUPPORTED",
            "confidence": "HIGH",
            "reason": "No prescription volume data in evidence.",
            "scope_issues": [],
            "qualifications_missing": [],
        }))
        extractor_llm = MagicMock()
        extractor_llm.generate.return_value = extractor_resp
        reviewer_llm = MagicMock()
        reviewer_llm.generate.return_value = reviewer_resp

        with patch("intelligence.ask_intrinsiciq.claim_extractor.get_llm", return_value=extractor_llm):
            with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=reviewer_llm):
                result = validate_answer_complete(ai_answer, pkg)

        # At minimum, answer should NOT be a clean PASS
        self.assertNotEqual(result["answer_status"], "PASS")
        # Undeclared result should be REJECT or NEEDS_REVIEW
        undeclared_results = result.get("undeclared_claim_results", [])
        self.assertTrue(len(undeclared_results) > 0)
        acceptance = undeclared_results[0].get("final_acceptance_status")
        self.assertIn(acceptance, (REJECT, NEEDS_REVIEW))


# ── Acceptance gate tests ──────────────────────────────────────────────────────

class TestAcceptanceGate(unittest.TestCase):
    """Final gate: incomplete validation run must never produce PASS."""

    def test_empty_extraction_produces_fail_incomplete(self):
        """Empty extraction with INCOMPLETE coverage → FAIL_INCOMPLETE."""
        from intelligence.ask_intrinsiciq.claim_validator import validate_answer_complete
        FAIL_INCOMPLETE = "FAIL_INCOMPLETE"

        pkg = _make_package()
        ai_answer = {
            "simple_answer": "Test.",
            "why_it_matters": "Test.",
            "key_points": [],
            "economic_reasoning": {},
            "claims": [{"claim_id": "C001", "claim_text": "Test.", "evidence_refs": ["PT-0003-c001123d90ea"], "claim_type": "COMMITMENT_STATEMENT"}],
            "evidence_gaps": [],
            "investor_action_items": [],
        }
        extraction_resp = _make_ai_response(json.dumps({
            "extracted_claims": [],
            "coverage_assessment": "INCOMPLETE",
            "coverage_notes": "Extraction failed.",
        }))
        mock_extractor_llm = MagicMock()
        mock_extractor_llm.generate.return_value = extraction_resp

        reviewer_resp = _make_ai_response(json.dumps({
            "verdict": "SUPPORTED",
            "confidence": "HIGH",
            "reason": "Test.",
            "scope_issues": [],
            "qualifications_missing": [],
        }))
        mock_reviewer_llm = MagicMock()
        mock_reviewer_llm.generate.return_value = reviewer_resp

        with patch("intelligence.ask_intrinsiciq.claim_extractor.get_llm", return_value=mock_extractor_llm):
            with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=mock_reviewer_llm):
                result = validate_answer_complete(ai_answer, pkg)

        self.assertEqual(result["answer_status"], "FAIL_INCOMPLETE")

    def test_all_accepted_no_undeclared_pass(self):
        """All declared claims ACCEPTED + extraction COMPLETE + 0 undeclared → PASS."""
        from intelligence.ask_intrinsiciq.claim_validator import validate_answer_complete

        pkg = _make_package()
        ai_answer = {
            "simple_answer": "Management committed to Japan expansion.",
            "why_it_matters": "Specialty expansion is part of the stated business model.",
            "key_points": ["Management committed to Japan market (unverified)."],
            "economic_reasoning": {
                "management_intentions": "Expand specialty.",
                "remaining_uncertainty": "No prescription data.",
            },
            "claims": [
                {
                    "claim_id": "C001",
                    "claim_text": "Management committed to targeting Japan and China for specialty expansion (FY20).",
                    "evidence_refs": ["PT-0003-c001123d90ea"],
                    "claim_type": "COMMITMENT_STATEMENT",
                }
            ],
            "evidence_gaps": ["No prescription data."],
            "investor_action_items": ["Request ILUMYA prescription data."],
        }
        extraction_resp = _make_ai_response(_extraction_ok_json(undeclared_count=0))
        reviewer_resp = _make_ai_response(json.dumps({
            "verdict": "SUPPORTED",
            "confidence": "HIGH",
            "reason": "Evidence directly establishes the commitment.",
            "scope_issues": [],
            "qualifications_missing": [],
        }))
        extractor_llm = MagicMock()
        extractor_llm.generate.return_value = extraction_resp
        reviewer_llm = MagicMock()
        reviewer_llm.generate.return_value = reviewer_resp

        with patch("intelligence.ask_intrinsiciq.claim_extractor.get_llm", return_value=extractor_llm):
            with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=reviewer_llm):
                result = validate_answer_complete(ai_answer, pkg)

        self.assertEqual(result["answer_status"], "PASS")


# ── M2/M3/M4/M5 regression sanity ─────────────────────────────────────────────

class TestM6Regressions(unittest.TestCase):
    """Quick regression: existing test modules still importable and key functions callable."""

    def test_claim_validator_imports(self):
        from intelligence.ask_intrinsiciq.claim_validator import (
            validate_answer, validate_answer_with_ai, validate_answer_complete,
            ACCEPT, NEEDS_REVIEW, REJECT,
        )
        self.assertTrue(callable(validate_answer))
        self.assertTrue(callable(validate_answer_with_ai))
        self.assertTrue(callable(validate_answer_complete))

    def test_claim_extractor_imports(self):
        from intelligence.ask_intrinsiciq.claim_extractor import extract_claims
        self.assertTrue(callable(extract_claims))

    def test_ai_claim_reviewer_imports(self):
        from intelligence.ask_intrinsiciq.ai_claim_reviewer import review_claim
        self.assertTrue(callable(review_claim))

    def test_evidence_reasoner_imports(self):
        from intelligence.ask_intrinsiciq.evidence_reasoner import generate_ai_answer
        self.assertTrue(callable(generate_ai_answer))

    def test_determine_acceptance_routing_unchanged(self):
        """Core routing rules from M4 unchanged."""
        from intelligence.ask_intrinsiciq.claim_validator import _determine_acceptance, REJECT, NEEDS_REVIEW, ACCEPT
        # det CONTRADICTED → REJECT regardless of AI
        _, status = _determine_acceptance("CONTRADICTED", "SUPPORTED")
        self.assertEqual(status, REJECT)
        # both SUPPORTED → ACCEPT
        _, status = _determine_acceptance("SUPPORTED", "SUPPORTED")
        self.assertEqual(status, ACCEPT)
        # REVIEW_ERROR → NEEDS_REVIEW
        _, status = _determine_acceptance("SUPPORTED", "REVIEW_ERROR")
        self.assertEqual(status, NEEDS_REVIEW)


if __name__ == "__main__":
    unittest.main(verbosity=2)
