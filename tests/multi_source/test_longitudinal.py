"""Phase 9 — Multi-source longitudinal intelligence tests.

Parts 31: Cross-source commitment identity, source authority,
lifecycle state, and six-source regression.
"""
from __future__ import annotations

import pytest
from pathlib import Path

# ── Source-authority contract ───────────────────────────────────────────────

from intelligence.multi_source.contracts import (
    ClaimDomain,
    CommitmentLifecycle,
    SourceAuthority,
    authority_rank,
)


class TestSourceAuthority:
    def test_disclosure_highest_authority_for_factual_events(self):
        rank_disc = authority_rank(SourceAuthority.EXCHANGE_DISCLOSURE, ClaimDomain.FACTUAL_EVENT)
        rank_ar   = authority_rank(SourceAuthority.ANNUAL_REPORT,       ClaimDomain.FACTUAL_EVENT)
        rank_tr   = authority_rank(SourceAuthority.TRANSCRIPT,          ClaimDomain.FACTUAL_EVENT)
        assert rank_disc < rank_ar < rank_tr

    def test_transcript_highest_authority_for_commitments(self):
        rank_tr = authority_rank(SourceAuthority.TRANSCRIPT,          ClaimDomain.COMMITMENT)
        rank_ar = authority_rank(SourceAuthority.ANNUAL_REPORT,       ClaimDomain.COMMITMENT)
        rank_pr = authority_rank(SourceAuthority.INVESTOR_PRESENTATION, ClaimDomain.COMMITMENT)
        assert rank_tr < rank_pr
        assert rank_tr < rank_ar

    def test_annual_report_highest_for_financial_metrics(self):
        rank_ar = authority_rank(SourceAuthority.ANNUAL_REPORT,   ClaimDomain.FINANCIAL_METRIC)
        rank_tr = authority_rank(SourceAuthority.TRANSCRIPT,      ClaimDomain.FINANCIAL_METRIC)
        rank_pr = authority_rank(SourceAuthority.INVESTOR_PRESENTATION, ClaimDomain.FINANCIAL_METRIC)
        assert rank_ar < rank_tr
        assert rank_ar < rank_pr

    def test_unknown_authority_returns_high_rank(self):
        rank = authority_rank(SourceAuthority.UNKNOWN, ClaimDomain.COMMITMENT)
        assert rank == 99


# ── Cross-source commitment identity ────────────────────────────────────────

from intelligence.multi_source.theme_registry import classify_theme


class TestCrossSourceIdentity:
    def test_atp_bank_program_detected(self):
        result = classify_theme("Number two, ATP, yes, we have signed the third deal.")
        assert result is not None
        slug, label, domain = result
        assert slug == "atp_bank_program"

    def test_ebitda_margin_detected(self):
        result = classify_theme("EBITDA margin has improved slightly in the last couple of quarters.")
        assert result is not None
        slug, *_ = result
        assert slug == "ebitda_margin_trajectory"

    def test_wisely_ai_detected(self):
        result = classify_theme("Wisely Ai kind of platforms obviously are growing at a much faster pace.")
        assert result is not None
        slug, *_ = result
        assert slug == "wisely_ai_growth"

    def test_leadership_change_detected_from_disclosure_text(self):
        text = "management change senior management personnel resignation director"
        result = classify_theme(text)
        assert result is not None
        slug, *_ = result
        assert slug == "leadership_change"

    def test_rcs_detected(self):
        result = classify_theme("RCS adoption is happening quite fast in the market.")
        assert result is not None
        assert result[0] == "rcs_channel_adoption"

    def test_unrelated_text_returns_none(self):
        assert classify_theme("The meeting was called to order at 10am.") is None

    def test_fx_hedging_detected(self):
        result = classify_theme("We are reworking on our hedging policy to reduce the exposure.")
        assert result is not None
        assert result[0] == "fx_hedging_policy"

    def test_ott_whatsapp_detected(self):
        result = classify_theme("OTT channels are growing very fast, WhatsApp is growing very fast.")
        assert result is not None
        assert result[0] == "ott_whatsapp_growth"


# ── Lifecycle state machine ──────────────────────────────────────────────────

from intelligence.multi_source.contracts import MultiSourceEvidence
from intelligence.multi_source.lifecycle import resolve_commitments


def _make_evidence(
    slug: str,
    source_period: str,
    source_type: str,
    authority: SourceAuthority,
    claim_domain: ClaimDomain,
    claim_type: str,
    text: str,
    company: str = "testco",
    fiscal_year: str = "fy26",
) -> MultiSourceEvidence:
    return MultiSourceEvidence(
        evidence_id=f"test:{slug}:{source_period}:{source_type}",
        company=company,
        fiscal_year=fiscal_year,
        source_period=source_period,
        source_type=source_type,
        authority=authority,
        claim_domain=claim_domain,
        theme_slug=slug,
        claim_type=claim_type,
        speaker="Test Speaker",
        speaker_role="MANAGEMENT",
        text=text,
        qualifiers=[],
    )


class TestLifecycleMachine:
    def test_single_commitment_atom_is_unproven(self):
        evidence = [
            _make_evidence(
                "platform_launch", "Q3 FY26", "EARNINGS_CALL_TRANSCRIPT",
                SourceAuthority.TRANSCRIPT, ClaimDomain.COMMITMENT,
                "COMMITMENT", "We will launch the new platform next quarter.",
            )
        ]
        commitments = resolve_commitments(evidence)
        assert len(commitments) == 1
        assert commitments[0].lifecycle == CommitmentLifecycle.UNPROVEN

    def test_commitment_with_high_authority_confirmation_is_confirmed(self):
        evidence = [
            _make_evidence(
                "leadership_change", "Q4 FY26", "EARNINGS_CALL_TRANSCRIPT",
                SourceAuthority.TRANSCRIPT, ClaimDomain.COMMITMENT,
                "COMMITMENT", "CEO will resign next quarter.",
            ),
            _make_evidence(
                "leadership_change", "undated", "EXCHANGE_DISCLOSURE",
                SourceAuthority.EXCHANGE_DISCLOSURE, ClaimDomain.FACTUAL_EVENT,
                "MANAGEMENT_CHANGE", "management change senior management personnel resignation.",
            ),
        ]
        commitments = resolve_commitments(evidence)
        assert commitments[0].lifecycle == CommitmentLifecycle.CONFIRMED
        assert commitments[0].confirmed_source == SourceAuthority.EXCHANGE_DISCLOSURE

    def test_commitment_with_low_authority_followup_is_progressing(self):
        evidence = [
            _make_evidence(
                "atp_bank_program", "Q3 FY26", "EARNINGS_CALL_TRANSCRIPT",
                SourceAuthority.TRANSCRIPT, ClaimDomain.COMMITMENT,
                "COMMITMENT", "We plan to sign one more ATP deal by March.",
            ),
            _make_evidence(
                "atp_bank_program", "Q4 FY26", "EARNINGS_CALL_TRANSCRIPT",
                SourceAuthority.TRANSCRIPT, ClaimDomain.COMMITMENT,
                "FACTUAL_STATEMENT", "ATP, yes, we have signed the third deal.",
            ),
        ]
        commitments = resolve_commitments(evidence)
        assert commitments[0].lifecycle == CommitmentLifecycle.PROGRESSING

    def test_multiple_themes_produce_separate_commitments(self):
        evidence = [
            _make_evidence("atp_bank_program", "Q4 FY26", "EARNINGS_CALL_TRANSCRIPT",
                           SourceAuthority.TRANSCRIPT, ClaimDomain.COMMITMENT,
                           "COMMITMENT", "ATP third deal signed.", fiscal_year="fy26"),
            _make_evidence("ebitda_margin_trajectory", "Q4 FY26", "EARNINGS_CALL_TRANSCRIPT",
                           SourceAuthority.TRANSCRIPT, ClaimDomain.COMMITMENT,
                           "COMMITMENT", "EBITDA will improve in coming quarters.", fiscal_year="fy26"),
        ]
        commitments = resolve_commitments(evidence)
        slugs = {c.theme_slug for c in commitments}
        assert "atp_bank_program" in slugs
        assert "ebitda_margin_trajectory" in slugs

    def test_confirmed_commitments_sort_first(self):
        evidence = [
            _make_evidence("atp_bank_program", "Q4 FY26", "EARNINGS_CALL_TRANSCRIPT",
                           SourceAuthority.TRANSCRIPT, ClaimDomain.COMMITMENT,
                           "COMMITMENT", "ATP plan."),
            _make_evidence("leadership_change", "Q4 FY26", "EXCHANGE_DISCLOSURE",
                           SourceAuthority.EXCHANGE_DISCLOSURE, ClaimDomain.FACTUAL_EVENT,
                           "MANAGEMENT_CHANGE", "management change resignation director."),
        ]
        commitments = resolve_commitments(evidence)
        assert commitments[0].lifecycle == CommitmentLifecycle.CONFIRMED


# ── Six-source regression (Part 32) ─────────────────────────────────────────

class TestSixSourceRegression:
    """End-to-end production proof using Tanla real data."""

    @pytest.fixture(scope="class")
    def tanla_report(self):
        from intelligence.multi_source.longitudinal import build
        return build(
            company="tanla",
            companies_root=Path("companies"),
            execute=False,
        )

    def test_all_four_present_source_families(self, tanla_report):
        families = set(tanla_report.source_families_present)
        assert "ANNUAL_REPORT" in families
        assert "EARNINGS_CALL_TRANSCRIPT" in families
        assert "EXCHANGE_DISCLOSURE" in families
        assert "INVESTOR_PRESENTATION" in families

    def test_no_stop_conditions(self, tanla_report):
        assert tanla_report.stop_conditions == []

    def test_at_least_ten_commitment_threads(self, tanla_report):
        assert tanla_report.commitment_count >= 10

    def test_leadership_change_is_confirmed_by_disclosure(self, tanla_report):
        lc = next(
            (c for c in tanla_report.commitments if c.theme_slug == "leadership_change"),
            None,
        )
        assert lc is not None, "leadership_change thread must exist"
        assert lc.lifecycle == CommitmentLifecycle.CONFIRMED
        assert lc.confirmed_source == SourceAuthority.EXCHANGE_DISCLOSURE

    def test_atp_program_appears_as_commitment_thread(self, tanla_report):
        atp = next(
            (c for c in tanla_report.commitments if c.theme_slug == "atp_bank_program"),
            None,
        )
        assert atp is not None, "atp_bank_program commitment thread must exist"

    def test_profitability_thread_has_multi_source_evidence(self, tanla_report):
        prof = next(
            (c for c in tanla_report.commitments if c.theme_slug == "profitability"),
            None,
        )
        assert prof is not None
        source_types = {e.source_type for e in prof.evidence}
        assert len(source_types) >= 2, "profitability must have evidence from ≥ 2 source families"

    def test_manifest_status_closed(self):
        import json
        manifest_path = Path("companies/tanla/longitudinal/longitudinal_manifest.json")
        if not manifest_path.exists():
            pytest.skip("Manifest not yet written — run with execute=True first.")
        manifest = json.load(open(manifest_path))
        assert manifest["status"] == "MULTI_SOURCE_LONGITUDINAL_INTEGRATION_CLOSED"
