"""
ENG-132: Committee Generation Boundary Tests

Two suites:
  1. Adversarial: analyst findings that contain tempting forbidden language must
     be skipped by _has_substantive_constructive_signal / _has_substantive_concern
     so no forbidden text is embedded in the committee skeleton.
  2. Validator strictness: committee output that embeds forbidden phrases must
     be rejected by validate_committee_output (validator NOT weakened).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

import pytest

from intelligence.investor_panel.committee_synthesizer import (
    _detect_doctrine_disagreements,
    _has_substantive_constructive_signal,
)
from intelligence.investor_panel.committee_validator import _validate_normalized_list_text
from intelligence.investor_panel.forbidden_language import (
    has_forbidden_recommendation_language,
    find_forbidden_recommendation_language,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _analyst(
    doctrine_id: str,
    *,
    key_findings: List[str] | None = None,
    red_flags: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "doctrine_id": doctrine_id,
        "company": "test_co",
        "analysis_mode": "llm_reasoning_v1",
        "rating": "mixed",
        "key_findings": key_findings or [f"{doctrine_id} finding"],
        "red_flags": red_flags or [f"{doctrine_id} flag"],
        "open_uncertainties": [],
        "evidence_ids": [f"ev_{doctrine_id}_1"],
        "historical_context_used": False,
        "years_considered": ["fy24"],
        "supporting_pcim_sections": [],
        "evidence_grounding_status": "pass",
        "financial_assessment": {},
        "management_chain_statuses": [],
        "user_facing_brief": None,
    }




# ---------------------------------------------------------------------------
# Suite 1: Adversarial — forbidden-language findings must be skipped
# ---------------------------------------------------------------------------

class TestAdversarialFindingsSkipped:
    """Findings that contain forbidden recommendation/valuation language must
    never be selected as the constructive signal that triggers disagreement
    embedding. The guard at _has_substantive_constructive_signal must skip them.
    """

    def test_buy_action_finding_skipped(self):
        """Finding 'Buy this stock now' must be skipped."""
        found, text = _has_substantive_constructive_signal(["Buy this stock now"])
        assert not found, f"Forbidden 'buy' finding must be skipped; got text={text!r}"

    def test_sell_action_finding_skipped(self):
        """Finding 'Sell before the results' must be skipped."""
        found, text = _has_substantive_constructive_signal(["Sell before the results"])
        assert not found, f"Forbidden 'sell' finding must be skipped; got text={text!r}"

    def test_hold_action_finding_skipped(self):
        """Finding 'Hold for long term' must be skipped."""
        found, text = _has_substantive_constructive_signal(["Hold for long term"])
        assert not found, f"Forbidden 'hold' finding must be skipped; got text={text!r}"

    def test_buy_as_proper_noun_with_action_word_skipped(self):
        """'Buy Indian (IDDM) category' contains standalone 'buy' and must be skipped."""
        finding = (
            "Prioritise procurement of capital items in the Buy Indian (IDDM) category "
            "from domestic sources; execution and financial consequence remain unproven."
        )
        found, text = _has_substantive_constructive_signal([finding])
        assert not found, (
            f"Finding containing 'Buy Indian' (standalone buy) must be skipped; got text={text!r}"
        )

    def test_undervalued_finding_skipped(self):
        """Finding with 'undervalued' must be skipped (forbidden valuation language)."""
        found, text = _has_substantive_constructive_signal(
            ["The stock appears undervalued relative to peers; improving momentum visible."]
        )
        assert not found, (
            f"'undervalued' finding must be skipped even if it contains constructive tokens; got text={text!r}"
        )

    def test_unproven_does_not_match_proven(self):
        """'unproven' must NOT match the constructive signal 'proven' (word-boundary fix)."""
        found, text = _has_substantive_constructive_signal(
            ["execution and financial consequence remain unproven"]
        )
        assert not found, (
            f"'unproven' must not trigger 'proven' signal match (word-boundary bug); got text={text!r}"
        )

    def test_clean_constructive_finding_selected(self):
        """A finding with 'strong' and no forbidden language must be selected normally."""
        finding = "Gross margin is strong at 66% in fy26; comparability is limited."
        found, text = _has_substantive_constructive_signal([finding])
        assert found, f"Clean finding with 'strong' must be selected; found={found}"
        assert text == finding

    def test_forbidden_finding_then_clean_finding_selects_clean(self):
        """When first finding is forbidden but second is clean, second must be selected."""
        forbidden = "Buy this stock; momentum is improving."
        clean = "Margin momentum is improving and improving steadily."
        found, text = _has_substantive_constructive_signal([forbidden, clean])
        assert found, "Second clean finding must be selected"
        assert text == clean, f"Expected clean finding; got {text!r}"

    def test_detect_disagreements_skips_finding_with_buy(self):
        """_detect_doctrine_disagreements must not embed a finding that contains 'buy'."""
        growth = _analyst(
            "fisher",
            key_findings=[
                "Buy Indian (IDDM) category mandate is claim only; outcome unproven.",
                "Operating margin shows strong improvement trend in fy26 filings.",
            ],
        )
        safety = _analyst("graham", red_flags=["execution risk remains unverified"])
        result = _detect_doctrine_disagreements([growth, safety])
        # Whether disagreement is generated or not, NO record should embed the forbidden finding
        for record in result:
            summary = str(record.get("summary") or "")
            assert re.search(r"\bbuy\b", summary, re.IGNORECASE) is None, (
                f"Disagreement summary must not contain 'buy': {summary!r}"
            )

    def test_detect_disagreements_uses_second_finding_when_first_forbidden(self):
        """With forbidden first finding and clean second, disagreement must be generated
        using the clean second finding (not skipped entirely)."""
        growth = _analyst(
            "fisher",
            key_findings=[
                "Buy Indian mandate is CLAIM_ONLY; unproven.",  # forbidden → skip
                "Strong margin trend is visible in fy26.",      # clean → select
            ],
        )
        safety = _analyst("graham", red_flags=["downside risk is material and unverified"])
        result = _detect_doctrine_disagreements([growth, safety])
        assert len(result) >= 1, (
            "Disagreement must be generated when second finding is clean "
            "even if first finding was skipped for forbidden language"
        )


# ---------------------------------------------------------------------------
# Suite 2: Validator strictness — validator layer must NOT be weakened
#
# Tests use _validate_normalized_list_text (the field-level validator check)
# directly. This is the same function called for every list-text field in
# committee output, and it has two sub-checks:
#   (a) find_forbidden_recommendation_language() — complex pattern rules
#   (b) re.search(r"\b(?:buy|sell|hold)\b") — standalone word catch
# ENG-132 did NOT modify committee_validator.py. These tests confirm that.
# ---------------------------------------------------------------------------

class TestValidatorRejectsForbiddenLanguage:
    """Verify the validator has NOT been weakened by ENG-132."""

    def _expect_raise(self, text: str) -> None:
        """Assert _validate_normalized_list_text raises ValueError for text."""
        with pytest.raises(ValueError, match="forbidden"):
            _validate_normalized_list_text("test_field", text)

    def test_buy_standalone_rejected(self):
        """Standalone 'buy' in list text must be rejected by the validator."""
        self._expect_raise("Analysts agree; buy the stock while momentum holds.")

    def test_sell_standalone_rejected(self):
        """Standalone 'sell' must be rejected."""
        self._expect_raise("The committee recommends: sell shares before the next filing.")

    def test_hold_standalone_rejected(self):
        """Standalone 'hold' must be rejected."""
        self._expect_raise("Consensus view is to hold the position.")

    def test_undervalued_rejected(self):
        """'undervalued' must be caught by find_forbidden_recommendation_language."""
        self._expect_raise("The stock appears undervalued relative to sector peers.")

    def test_target_price_rejected(self):
        """'target price' must be caught by find_forbidden_recommendation_language."""
        self._expect_raise("Target price of ₹500 is implied by current FCF yield.")

    def test_investors_should_buy_rejected(self):
        """'investors should buy' must be caught."""
        self._expect_raise("Investors should buy on any correction given the margin profile.")

    def test_clean_analytical_text_passes(self):
        """Clean analytical text must pass the validator unchanged."""
        text = "Evidence strengthens the business-quality thesis on margin durability."
        result = _validate_normalized_list_text("test_field", text)
        assert result == text.strip()

    def test_buy_indian_standalone_rejected(self):
        """'Buy Indian (IDDM) category' contains standalone 'buy' and must be rejected."""
        self._expect_raise(
            "Prioritise procurement in the Buy Indian (IDDM) category from domestic sources."
        )
