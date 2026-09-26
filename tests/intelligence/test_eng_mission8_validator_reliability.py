"""
Mission 8 validator reliability tests.

Tests the three defects fixed in Mission 8:
  HC-006: geography scope check catches unanchored geography in narrative
  HC-009: inconsistent AI response cannot auto-approve; gap reviewer rejects embedded quants
  HC-010/011: source_context prevents false rejections of correctly extracted claims

No live AI calls — all reviewer interactions are stubbed.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock
from typing import Any, Dict, List

from intelligence.ask_intrinsiciq.claim_validator import (
    _determine_acceptance,
    validate_narrative_fields,
    _get_source_field_text,
    _extract_geography_tokens,
    VERDICT_SUPPORTED,
    VERDICT_PARTIALLY,
    VERDICT_UNSUPPORTED,
    VERDICT_CONTRADICTED,
    ACCEPT,
    NEEDS_REVIEW,
    REJECT,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pkg_with_evidence(items: List[Dict]) -> Dict:
    return {"sections": {"verifiable_commitments": items}, "package_constraints": {}}


def _pkg_japan_china() -> Dict:
    """Minimal package whose evidence mentions Japan and China but not Germany/France."""
    return _pkg_with_evidence([
        {
            "item_id": "PT-0001",
            "original_statement": "Management committed to expanding ILUMYA into Japan and China.",
            "announcement_period": "fy20",
        }
    ])


# ── _determine_acceptance — removed promotion ─────────────────────────────────

class TestDetermineAcceptance:
    def test_unsupported_with_no_issues_is_needs_review_not_accept(self):
        """HC-009 root: AI UNSUPPORTED + empty scope_issues must NOT auto-accept."""
        verdict, status = _determine_acceptance(
            VERDICT_SUPPORTED, VERDICT_UNSUPPORTED,
            ai_scope_issues=[], ai_qualifications_missing=[]
        )
        assert status == NEEDS_REVIEW, "Inconsistent AI response must not yield ACCEPT"
        assert verdict == VERDICT_UNSUPPORTED

    def test_unsupported_with_no_issues_is_needs_review_none_args(self):
        verdict, status = _determine_acceptance(
            VERDICT_SUPPORTED, VERDICT_UNSUPPORTED,
            ai_scope_issues=None, ai_qualifications_missing=None
        )
        assert status == NEEDS_REVIEW

    def test_partially_with_scope_issues_is_needs_review(self):
        """HC-006 root: AI PARTIALLY_SUPPORTED with scope_issues must not ACCEPT."""
        verdict, status = _determine_acceptance(
            VERDICT_SUPPORTED, VERDICT_PARTIALLY,
            ai_scope_issues=["Geography Europe not in evidence"],
            ai_qualifications_missing=[]
        )
        assert status == NEEDS_REVIEW
        assert verdict == VERDICT_PARTIALLY

    def test_partially_without_scope_issues_still_accepts(self):
        """No regression: AI PARTIALLY_SUPPORTED with no scope issues still ACCEPT."""
        verdict, status = _determine_acceptance(
            VERDICT_SUPPORTED, VERDICT_PARTIALLY,
            ai_scope_issues=[], ai_qualifications_missing=[]
        )
        assert status == ACCEPT

    def test_both_supported_is_accept(self):
        verdict, status = _determine_acceptance(
            VERDICT_SUPPORTED, VERDICT_SUPPORTED,
        )
        assert status == ACCEPT
        assert verdict == VERDICT_SUPPORTED

    def test_det_unsupported_always_reject(self):
        verdict, status = _determine_acceptance(VERDICT_UNSUPPORTED, VERDICT_SUPPORTED)
        assert status == REJECT

    def test_det_contradicted_always_reject(self):
        verdict, status = _determine_acceptance(VERDICT_CONTRADICTED, VERDICT_SUPPORTED)
        assert status == REJECT

    def test_review_error_is_needs_review(self):
        verdict, status = _determine_acceptance(VERDICT_SUPPORTED, "REVIEW_ERROR")
        assert status == NEEDS_REVIEW

    def test_unsupported_with_actual_scope_issues_stays_needs_review_from_general_path(self):
        """When AI UNSUPPORTED AND has scope_issues → falls through to general NEEDS_REVIEW."""
        verdict, status = _determine_acceptance(
            VERDICT_SUPPORTED, VERDICT_UNSUPPORTED,
            ai_scope_issues=["Germany not in evidence"],
        )
        # Not promoted (the early-exit fires) — ends as NEEDS_REVIEW
        assert status == NEEDS_REVIEW


# ── Geography scope check ─────────────────────────────────────────────────────

class TestGeographyScopeCheck:
    def test_extracts_known_geography_tokens(self):
        tokens = _extract_geography_tokens("Management targeted Germany and France in FY19.")
        assert "germany" in tokens
        assert "france" in tokens

    def test_does_not_extract_generic_text(self):
        tokens = _extract_geography_tokens("Management committed to growth in sales.")
        assert tokens == []

    def test_narrative_flags_unanchored_geography(self):
        """HC-006: Germany/France not in evidence → narrative violation."""
        answer = {
            "simple_answer": "Management targeted Germany and France for ILUMYA in FY19.",
            "why_it_matters": "FY19 commitment to Germany and France.",
            "key_points": ["Germany and France ILUMYA launch FY19."],
            "economic_reasoning": {
                "management_intentions": "Germany and France ILUMYA launch FY19."
            },
        }
        pkg = _pkg_japan_china()
        issues = validate_narrative_fields(answer, pkg)
        geo_issues = [i for i in issues if "geography" in i["violation"].lower()]
        assert len(geo_issues) > 0, "Germany/France should be flagged as unanchored geography"
        texts = " ".join(i["violation"] for i in geo_issues)
        assert "germany" in texts.lower() or "france" in texts.lower()

    def test_narrative_does_not_flag_evidence_anchored_geography(self):
        """Japan is in the evidence — must not produce a false geography violation."""
        answer = {
            "simple_answer": "Management targeted Japan and China for specialty products.",
            "why_it_matters": "Japan and China expansion committed by management.",
            "key_points": [],
            "economic_reasoning": {},
        }
        pkg = _pkg_japan_china()
        issues = validate_narrative_fields(answer, pkg)
        geo_issues = [i for i in issues if "geography" in i["violation"].lower()]
        # japan and china are in evidence corpus — no geography violations
        assert not any("japan" in i["violation"].lower() for i in geo_issues)
        assert not any("china" in i["violation"].lower() for i in geo_issues)

    def test_narrative_clean_answer_produces_no_issues(self):
        """HC-011 style answer with no forbidden patterns and anchored geographies."""
        answer = {
            "simple_answer": "Management committed to geographic expansion. Both commitments remain unverified.",
            "why_it_matters": "The commitments are consistent with the company revenue model.",
            "key_points": ["Management committed to Japan/China specialty expansion (FY20)."],
            "economic_reasoning": {
                "management_intentions": "Target Japan and China for specialty.",
                "remaining_uncertainty": "Both commitments remain UNVERIFIED.",
            },
        }
        pkg = _pkg_japan_china()
        issues = validate_narrative_fields(answer, pkg)
        assert issues == [], f"Clean answer should have no issues, got: {issues}"


# ── Source field text retrieval ───────────────────────────────────────────────

class TestGetSourceFieldText:
    def _answer(self):
        return {
            "simple_answer": "Top-level answer.",
            "why_it_matters": "Why it matters.",
            "key_points": ["Point A", "Point B"],
            "evidence_gaps": ["Gap one", "Gap two"],
            "economic_reasoning": {
                "remaining_uncertainty": "Uncertainty text.",
                "management_intentions": "Intentions text.",
            },
        }

    def test_evidence_gaps_index(self):
        assert _get_source_field_text(self._answer(), "evidence_gaps[1]") == "Gap two"

    def test_key_points_index(self):
        assert _get_source_field_text(self._answer(), "key_points[0]") == "Point A"

    def test_economic_reasoning_field(self):
        assert _get_source_field_text(self._answer(), "economic_reasoning.remaining_uncertainty") == "Uncertainty text."

    def test_top_level_field(self):
        assert _get_source_field_text(self._answer(), "why_it_matters") == "Why it matters."

    def test_missing_field_returns_empty(self):
        assert _get_source_field_text(self._answer(), "nonexistent") == ""

    def test_out_of_bounds_index_returns_empty(self):
        assert _get_source_field_text(self._answer(), "evidence_gaps[99]") == ""


# ── review_claim source_context parameter ────────────────────────────────────

class TestReviewClaimSourceContext:
    """Verify source_context is passed through to the LLM prompt."""

    def _mock_llm_response(self, verdict="SUPPORTED"):
        resp = MagicMock()
        resp.text = json.dumps({
            "verdict": verdict,
            "confidence": "HIGH",
            "reason": "Test reason.",
            "scope_issues": [],
            "qualifications_missing": [],
        })
        return resp

    def test_source_context_included_in_prompt(self):
        from intelligence.ask_intrinsiciq.ai_claim_reviewer import review_claim

        captured_prompt = {}

        def fake_generate(prompt, **kwargs):
            captured_prompt["value"] = prompt
            return self._mock_llm_response()

        mock_llm = MagicMock()
        mock_llm.generate.side_effect = fake_generate

        with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=mock_llm):
            review_claim(
                {"claim_text": "Test claim.", "claim_type": "UNCERTAINTY", "evidence_refs": []},
                [],
                source_context="Both commitments remain UNVERIFIED per package.",
            )

        assert "ORIGINAL SOURCE TEXT" in captured_prompt["value"]
        assert "Both commitments remain UNVERIFIED" in captured_prompt["value"]

    def test_no_source_context_omits_section(self):
        from intelligence.ask_intrinsiciq.ai_claim_reviewer import review_claim

        captured_prompt = {}

        def fake_generate(prompt, **kwargs):
            captured_prompt["value"] = prompt
            return self._mock_llm_response()

        mock_llm = MagicMock()
        mock_llm.generate.side_effect = fake_generate

        with patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.get_llm", return_value=mock_llm):
            review_claim(
                {"claim_text": "Test claim.", "claim_type": "UNCERTAINTY", "evidence_refs": []},
                [],
                source_context=None,
            )

        assert "ORIGINAL SOURCE TEXT" not in captured_prompt["value"]


# ── Undeclared claim inconsistency gate (HC-010/011 false alarm fix) ──────────

class TestUndeclaredClaimInconsistencyGate:
    """
    Undeclared claims with ai=UNSUPPORTED/CONTRADICTED but no scope_issues
    must route to NEEDS_REVIEW, not REJECT (mirrors _determine_acceptance M8 fix).
    """

    def _run_validation(self, ai_verdict: str, scope_issues: list, qualifications: list):
        from intelligence.ask_intrinsiciq.claim_validator import validate_answer_complete

        answer = {
            "simple_answer": "Management committed to geographic expansion. Both commitments remain unverified.",
            "why_it_matters": "The commitments are consistent with the company revenue model.",
            "key_points": ["Management committed to Japan/China specialty expansion (FY20)."],
            "economic_reasoning": {
                "management_intentions": "Target Japan and China for specialty.",
                "remaining_uncertainty": "Both commitments outcome_status=UNVERIFIED.",
            },
            "claims": [
                {
                    "claim_id": "C001",
                    "claim_text": "Management stated it would target new markets like Japan and China for specialty products (FY20).",
                    "claim_type": "COMMITMENT_STATEMENT",
                    "evidence_refs": ["PT-0003-c001123d90ea"],
                }
            ],
            "evidence_gaps": ["Prescription-volume data for ILUMYA in Japan and Australia."],
            "investor_action_items": [],
        }

        mock_extractor_result = {
            "declared_claims": [answer["claims"][0]],
            "undeclared_claims": [
                {
                    "extraction_id": "EX-T01",
                    "claim_text": "Both commitments outcome_status=UNVERIFIED.",
                    "claim_type": "UNCERTAINTY",
                    "suggested_refs": [],
                    "source_field": "",
                }
            ],
            "coverage_assessment": "COMPLETE",
        }

        def fake_extract(*args, **kwargs):
            return mock_extractor_result

        def fake_review(claim, cited_items, model=None, package_context_items=None, source_context=None):
            return {
                "verdict": ai_verdict,
                "confidence": "HIGH",
                "reason": "Test",
                "scope_issues": scope_issues,
                "qualifications_missing": qualifications,
            }

        pkg = {
            "sections": {
                "verifiable_commitments": [
                    {
                        "item_id": "PT-0003-c001123d90ea",
                        "original_statement": "Management committed to expanding ILUMYA into Japan and China.",
                        "announcement_period": "fy20",
                    }
                ]
            },
            "package_constraints": {},
        }

        with patch("intelligence.ask_intrinsiciq.claim_extractor.extract_claims", side_effect=fake_extract), \
             patch("intelligence.ask_intrinsiciq.ai_claim_reviewer.review_claim", side_effect=fake_review):
            return validate_answer_complete(answer, pkg)

    def test_unsupported_no_issues_routes_to_needs_review_not_reject(self):
        """HC-010/011 false alarm: undeclared ai=UNSUPPORTED + no scope_issues → NEEDS_REVIEW."""
        result = self._run_validation("UNSUPPORTED", [], [])
        undecl = {r["claim_id"]: r for r in result["undeclared_claim_results"]}
        assert undecl["EX-T01"]["final_acceptance_status"] == NEEDS_REVIEW, (
            "Undeclared UNSUPPORTED with no issues must not hard-REJECT"
        )

    def test_contradicted_no_issues_routes_to_needs_review_not_reject(self):
        """HC-010 Run 2 false alarm: undeclared ai=CONTRADICTED + no scope_issues → NEEDS_REVIEW."""
        result = self._run_validation("CONTRADICTED", [], [])
        undecl = {r["claim_id"]: r for r in result["undeclared_claim_results"]}
        assert undecl["EX-T01"]["final_acceptance_status"] == NEEDS_REVIEW, (
            "Undeclared CONTRADICTED with no scope_issues must not hard-REJECT"
        )

    def test_unsupported_with_scope_issues_still_rejects(self):
        """Adversarial preservation: undeclared ai=UNSUPPORTED WITH scope_issues → REJECT."""
        result = self._run_validation(
            "UNSUPPORTED", [{"issue": "Fabricated amount", "detail": "₹8,000 crore not in evidence"}], []
        )
        undecl = {r["claim_id"]: r for r in result["undeclared_claim_results"]}
        assert undecl["EX-T01"]["final_acceptance_status"] == REJECT, (
            "Undeclared UNSUPPORTED with scope_issues must still REJECT"
        )

    def test_contradicted_with_scope_issues_still_rejects(self):
        """Adversarial preservation: undeclared ai=CONTRADICTED WITH scope_issues → REJECT."""
        result = self._run_validation(
            "CONTRADICTED",
            [{"issue": "False execution", "detail": "Evidence shows commitment unverified not delivered"}],
            []
        )
        undecl = {r["claim_id"]: r for r in result["undeclared_claim_results"]}
        assert undecl["EX-T01"]["final_acceptance_status"] == REJECT, (
            "Undeclared CONTRADICTED with scope_issues must still REJECT"
        )
