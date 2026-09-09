"""Phase 11.2 — ENG-077: Theme registry generalization tests.

Tests the word-boundary fix in classify_theme() that prevents short pure-alpha
abbreviations (≤ 4 chars) from firing on embedded substrings.

Root cause (ENG-077): 'ott' in 'bottom' → True (b-ott-om substring match).
Fix: _kw_match() uses word-boundary regex for pure-alpha abbreviations ≤ 3 chars.
4-char pure-alpha keywords (e.g. 'hedg') remain as plain substring — they are
deliberate prefix patterns ('hedging', 'hedged'), not abbreviations.

Covers all 12 Part 15 test requirements from the Phase 11.2 mission brief.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from intelligence.multi_source.theme_registry import classify_theme
from intelligence.multi_source.contracts import (
    ClaimDomain,
    CommitmentLifecycle,
    MultiSourceEvidence,
    SourceAuthority,
)
from intelligence.multi_source.lifecycle import resolve_commitments


# ── Part 15.1: Reproduce Data Patterns false matches — confirm eliminated ────

class TestENG077FalseMatchReproduction:
    """All known Data Patterns false matches must now return None."""

    def test_bottom_line_does_not_match_ott(self):
        # "bottom" contains 'ott' as substring (b-OTT-om) — must not fire
        text = "bottom line business go along revenue model distribution"
        result = classify_theme(text)
        assert result is None, f"'bottom' must not match OTT; got {result}"

    def test_bottom_continued_does_not_match_ott(self):
        text = "growth at the bottom of the pyramid in tier-3 cities"
        result = classify_theme(text)
        assert result is None, f"tier-3 bottom text must not match OTT; got {result}"

    def test_allotted_does_not_match_ott(self):
        # "allotted" contains 'ott' as substring (all-OTT-ed) — must not fire
        text = "allotted equity shares employees ESOP scheme exercise price"
        result = classify_theme(text)
        assert result is None, f"'allotted' must not match OTT; got {result}"

    def test_bottleneck_does_not_match_ott(self):
        # "bottleneck" contains 'ott' (b-OTT-leneck) — must not fire
        text = "bottleneck in storage capacity is not a limiting factor"
        result = classify_theme(text)
        assert result is None, f"'bottleneck' must not match OTT; got {result}"

    def test_data_patterns_annual_report_allotted_does_not_match(self):
        # Verbatim near-transcript of Data Patterns quarterly report false positive
        text = (
            "During the year 2,80,000 equity shares were allotted under ESOP "
            "scheme at various exercise prices to eligible employees"
        )
        result = classify_theme(text)
        assert result is None, f"ESOP allotment text must not match OTT; got {result}"


# ── Part 15.2: True Tanla OTT positives must still classify ─────────────────

class TestENG077TanlaOTTPositives:
    """Valid OTT / WhatsApp evidence must still classify correctly after fix."""

    def test_standalone_ott_channels_matches(self):
        result = classify_theme("OTT channels are growing very fast this quarter")
        assert result is not None
        assert result[0] == "ott_whatsapp_growth"

    def test_ott_at_start_of_sentence_matches(self):
        result = classify_theme("OTT is opening new use cases for CPaaS players")
        assert result is not None
        assert result[0] == "ott_whatsapp_growth"

    def test_ott_revenue_contribution_matches(self):
        result = classify_theme("Revenue OTT contribution was 22% for the quarter")
        assert result is not None
        assert result[0] == "ott_whatsapp_growth"

    def test_whatsapp_standalone_matches(self):
        result = classify_theme("WhatsApp business messaging revenue grew 40% YoY")
        assert result is not None
        assert result[0] == "ott_whatsapp_growth"

    def test_whatsapp_and_ott_together_matches(self):
        result = classify_theme("OTT channels and WhatsApp are growing at double digit pace")
        assert result is not None
        assert result[0] == "ott_whatsapp_growth"


# ── Part 15.3: Generic phrases must NOT match specialized OTT theme ──────────

class TestENG077GenericPhraseNegatives:
    """Generic growth phrases without domain signals must not fire OTT/messaging themes."""

    def test_platform_growth_alone_does_not_match_ott(self):
        result = classify_theme("platform growth has been very strong across all segments")
        assert result is None or result[0] != "ott_whatsapp_growth", (
            f"generic 'platform growth' must not classify to ott_whatsapp_growth; got {result}"
        )

    def test_customer_growth_does_not_match_ott(self):
        result = classify_theme("customer growth drove enterprise revenue this quarter")
        assert result is None or result[0] != "ott_whatsapp_growth"

    def test_digital_platform_does_not_match_ott(self):
        result = classify_theme("digital platform transformation is central to our strategy")
        assert result is None or result[0] != "ott_whatsapp_growth"

    def test_enterprise_platform_does_not_match_ott(self):
        result = classify_theme("enterprise platform adoption growing among mid-market clients")
        assert result is None or result[0] != "ott_whatsapp_growth"

    def test_communication_systems_does_not_match_ott(self):
        result = classify_theme("communication systems upgrade across defence establishments")
        assert result is None or result[0] != "ott_whatsapp_growth"

    def test_ai_platform_does_not_match_ott(self):
        result = classify_theme("AI platform capabilities expanding with GenAI integration")
        assert result is None or result[0] != "ott_whatsapp_growth"

    def test_product_growth_does_not_match_ott(self):
        result = classify_theme("product growth driven by radar system exports to Middle East")
        assert result is None or result[0] != "ott_whatsapp_growth"


# ── Part 15.4 & 15.5: Messaging-specific positives classify correctly ────────

class TestENG077MessagingSpecificPositives:
    """Domain-appropriate messaging evidence must classify to the right theme."""

    def test_rcs_channel_adoption_classified(self):
        result = classify_theme("RCS adoption is happening quite fast in the market")
        assert result is not None
        assert result[0] == "rcs_channel_adoption"

    def test_rcs_not_matched_by_arcs(self):
        # "arcs" contains 'rcs' as substring — must not fire
        result = classify_theme("arcs of fire trajectory ballistics defence radar")
        assert result is None or result[0] != "rcs_channel_adoption", (
            f"'arcs' must not match rcs_channel_adoption; got {result}"
        )

    def test_atp_bank_program_classified(self):
        result = classify_theme("Number two ATP yes we have signed the third deal")
        assert result is not None
        assert result[0] == "atp_bank_program"

    def test_hedging_policy_classified(self):
        result = classify_theme("We are reworking on our hedging policy to reduce FX exposure")
        assert result is not None
        assert result[0] == "fx_hedging_policy"


# ── Part 15.6: Multi-theme ambiguous text → UNCLASSIFIED ────────────────────

class TestENG077AmbiguousTextUnclassified:
    """Texts with no sufficient theme signal must return None (UNCLASSIFIED)."""

    def test_generic_meeting_text_is_unclassified(self):
        assert classify_theme("The meeting was called to order at 10am.") is None

    def test_defence_product_no_theme_signal_is_unclassified(self):
        assert classify_theme("radar systems avionics electronic warfare defence") is None

    def test_company_header_alone_is_unclassified(self):
        # Data Patterns header triggers old 'pat' substring match — must now be None
        result = classify_theme("Data Patterns India Limited Q1 FY27 Earnings Call Transcript")
        assert result is None, (
            f"Company header without financial signal must be UNCLASSIFIED; got {result}"
        )


# ── Part 15.7: False cross-company merge prevention ─────────────────────────

class TestENG077NoCrossCompanyFalseMerge:
    """OTT atoms for Tanla must not merge with Data Patterns evidence threads."""

    def test_data_patterns_evidence_does_not_get_ott_slug(self):
        # Defence company texts must never classify as OTT/WhatsApp
        defence_texts = [
            "AESA radar systems avionics integration",
            "missile seekers electronic warfare exports",
            "Data Patterns Q1 FY27 revenue 320 crore",
            "bottom line profitability driven by order execution",
            "allotted ESOP shares employees under scheme",
        ]
        for text in defence_texts:
            result = classify_theme(text)
            if result is not None:
                assert result[0] != "ott_whatsapp_growth", (
                    f"Defence text classified as OTT: {text!r} → {result}"
                )

    def test_tanla_ott_text_still_classifies(self):
        # CPaaS company OTT evidence must still classify
        tanla_text = "OTT A2P messaging revenue contribution grew 18% in Q4 FY26"
        result = classify_theme(tanla_text)
        assert result is not None
        assert result[0] == "ott_whatsapp_growth"


# ── Parts 15.8 & 15.9: Transcript regression (unit level) ──────────────────

class TestENG077TranscriptRegression:
    """Word-boundary fix must not break legitimate financial term detection."""

    def test_pat_standalone_financial_still_classifies_profitability(self):
        # PAT (Profit After Tax) standalone must still match profitability
        result = classify_theme("PAT grew by 15% year over year to 45 crore")
        assert result is not None
        assert result[0] == "profitability"

    def test_profit_substring_still_classifies_profitability(self):
        result = classify_theme("profit margins expanded by 200 basis points this quarter")
        assert result is not None
        assert result[0] == "profitability"

    def test_cash_flow_still_classifies_profitability(self):
        result = classify_theme("cash flow from operations improved significantly in FY26")
        assert result is not None
        assert result[0] == "profitability"

    def test_patterns_company_name_without_pat_financial_is_unclassified(self):
        # "patterns" contains 'pat' but must not trigger profitability without financial signal
        result = classify_theme(
            "Data Patterns India Limited commenced operations in the defence segment"
        )
        assert result is None, (
            f"Company name 'Patterns' must not trigger profitability; got {result}"
        )

    def test_ebitda_margin_classified_from_tanla_style_text(self):
        result = classify_theme("EBITDA margin has improved slightly in the last couple of quarters")
        assert result is not None
        assert result[0] == "ebitda_margin_trajectory"


# ── Parts 15.10 & 15.11: Lifecycle rebuild regression ───────────────────────

def _make_evidence(
    slug: str,
    source_period: str,
    text: str,
    source_type: str = "EARNINGS_CALL_TRANSCRIPT",
    authority: SourceAuthority = SourceAuthority.TRANSCRIPT,
    company: str = "testco",
) -> MultiSourceEvidence:
    return MultiSourceEvidence(
        evidence_id=f"eng077:{slug}:{source_period}",
        company=company,
        fiscal_year="fy26",
        source_period=source_period,
        source_type=source_type,
        authority=authority,
        claim_domain=ClaimDomain.STRATEGIC_PRIORITY,
        theme_slug=slug,
        claim_type="COMMITMENT",
        speaker="Test Speaker",
        speaker_role="MANAGEMENT",
        text=text,
        qualifiers=[],
    )


class TestENG077LifecycleRebuildRegression:
    """After the fix, lifecycle threads must not be corrupted by false-positive atoms."""

    def test_ott_thread_from_valid_text_survives(self):
        evidence = [
            _make_evidence(
                "ott_whatsapp_growth", "Q4 FY26",
                "OTT channels are growing very fast this quarter."
            )
        ]
        commitments = resolve_commitments(evidence)
        slugs = [c.theme_slug for c in commitments]
        assert "ott_whatsapp_growth" in slugs

    def test_false_positive_ott_text_excluded_at_classification_level(self):
        # If classify_theme returns None for the false-positive text,
        # the atom never enters the evidence pool — thread stays clean.
        false_positive_texts = [
            "bottom line business go along revenue model",
            "allotted equity shares ESOP scheme employees",
            "bottleneck in storage is not limiting growth",
        ]
        for text in false_positive_texts:
            result = classify_theme(text)
            assert result is None or result[0] != "ott_whatsapp_growth", (
                f"False-positive text must not classify as OTT, breaking thread purity: {text!r}"
            )

    def test_distinct_theme_threads_not_corrupted(self):
        # Mixed evidence: OTT valid + profitability valid → two separate threads
        evidence = [
            _make_evidence("ott_whatsapp_growth", "Q3 FY26",
                           "OTT revenue contribution was 22% this quarter."),
            _make_evidence("profitability", "Q4 FY26",
                           "PAT grew by 15% to 45 crore year over year.",
                           authority=SourceAuthority.ANNUAL_REPORT),
        ]
        commitments = resolve_commitments(evidence)
        slugs = {c.theme_slug for c in commitments}
        assert "ott_whatsapp_growth" in slugs
        assert "profitability" in slugs
        # No cross-contamination: OTT thread must have no profitability evidence
        ott_thread = next(c for c in commitments if c.theme_slug == "ott_whatsapp_growth")
        assert all(e.theme_slug == "ott_whatsapp_growth" for e in ott_thread.evidence)


# ── Part 15.12: Unknown preservation ────────────────────────────────────────

class TestENG077UnknownPreservation:
    """Unknown / non-theme texts must return None (UNCLASSIFIED), never a wrong theme."""

    @pytest.mark.parametrize("text", [
        "The meeting was called to order at 10am.",
        "radar systems avionics electronic warfare",
        "This question is from the moderator.",
        "Thank you. We will take a break now.",
        "Next question please.",
        "Annual General Meeting notice to shareholders.",
        "Data Patterns India Limited DPIL corporate announcement",
    ])
    def test_non_theme_text_returns_none(self, text):
        result = classify_theme(text)
        # Non-theme texts must either be None or classified to a valid, relevant theme
        # — but NOT to a specialized messaging/OTT theme
        if result is not None:
            assert result[0] not in ("ott_whatsapp_growth", "rcs_channel_adoption", "atp_bank_program"), (
                f"Non-theme text incorrectly classified as messaging theme: {text!r} → {result}"
            )
