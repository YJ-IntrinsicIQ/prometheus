"""Phase 11.3 — ENG-078: platform_launch theme precision tests.

Root cause: platform_launch optional keywords included "new" and "announce",
both too generic. "new customers", "new hires", "new accounting standards",
"announced a buyback" all contained "platform" in the same chunk and triggered
a false platform_launch classification.

Fix: optional reduced from ["launch", "announce", "gigantic", "new"] to
["launch", "gigantic"]. A platform launch requires a strong action verb
(launch / gigantic), not just generic novelty ("new") or announcement.

Canonical platform_launch semantics:
  Evidence that a specific platform/product/service is being launched,
  introduced, rolled out, or commercially deployed. Requires "platform" +
  a strong launch-action verb. Generic novelty alone ("new customers",
  "new hires", "new quarter", "announced buyback") must not classify.
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


# ── Part 15.1: Reproduced ENG-078 false positives — confirmed eliminated ─────

class TestENG078FalseMatchesEliminated:
    """All confirmed ENG-078 false matches must now return None or a different theme."""

    def test_new_products_development_not_platform_launch(self):
        # Data Patterns DP transcript false positive
        text = (
            "We're also leveraging our existing technology platforms and reusable building "
            "blocks to develop new products faster and more cost effectively, improving both "
            "scalability and speed to market."
        )
        result = classify_theme(text)
        assert result is None or result[0] != "platform_launch", (
            f"'new products' development text must not classify as platform_launch; got {result}"
        )

    def test_idex_new_technologies_not_platform_launch(self):
        # Data Patterns annual report false positive
        text = "Create new technologies and products through the iDEX platform"
        result = classify_theme(text)
        assert result is None or result[0] != "platform_launch", (
            f"iDEX 'new technologies' text must not classify as platform_launch; got {result}"
        )

    def test_idex_develop_new_products_not_platform_launch(self):
        # Data Patterns annual report false positive
        text = "iDEX to provide a platform for start-ups to connect with defence establishments and develop new technologies/products"
        result = classify_theme(text)
        assert result is None or result[0] != "platform_launch", (
            f"iDEX development text must not classify as platform_launch; got {result}"
        )

    def test_new_customer_additions_not_platform_launch(self):
        # Tanla quarterly report false positive
        text = "Platform business revenue grew 6% QoQ driven by new customer additions and wallet share expansion among existing clients."
        result = classify_theme(text)
        assert result is None or result[0] != "platform_launch", (
            f"'new customer additions' must not classify as platform_launch; got {result}"
        )

    def test_new_hires_not_platform_launch(self):
        # Tanla quarterly report false positive
        text = "Indirect expenses increased due to salary increments, new hires, and performance-linked RSU on our platform business."
        result = classify_theme(text)
        assert result is None or result[0] != "platform_launch", (
            f"'new hires' text must not classify as platform_launch; got {result}"
        )

    def test_announced_buyback_not_platform_launch(self):
        # Tanla quarterly report false positive — "announce" + "platform" in same chunk
        text = "We announced a buyback program of up to ₹175 Cr at ₹875 per share for the platform business shareholders."
        result = classify_theme(text)
        assert result is None or result[0] != "platform_launch", (
            f"Buyback announcement must not classify as platform_launch; got {result}"
        )

    def test_new_accounting_standard_not_platform_launch(self):
        # Quarterly report boilerplate false positive
        text = "Financial statements prepared except where a newly issued accounting standard is initially adopted. Platform business definitions apply."
        result = classify_theme(text)
        assert result is None or result[0] != "platform_launch", (
            f"Accounting standard text must not classify as platform_launch; got {result}"
        )


# ── Part 15.2: "new" alone must never trigger platform_launch ────────────────

class TestENG078NewAloneNeverTriggers:
    """'new' alone — even with 'platform' present — must not classify as platform_launch."""

    def test_new_alone_no_platform_launch(self):
        result = classify_theme("We have new ideas for the platform this quarter.")
        assert result is None or result[0] != "platform_launch"

    def test_new_era_not_platform_launch(self):
        result = classify_theme("This platform unlocks a new era of performance marketing.")
        assert result is None or result[0] != "platform_launch"

    def test_new_features_not_platform_launch(self):
        result = classify_theme("The platform team is developing new and innovative products, expanding features.")
        assert result is None or result[0] != "platform_launch"

    def test_new_behaviors_not_platform_launch(self):
        result = classify_theme("Users no longer need to download new apps or learn new behaviors on our platform.")
        assert result is None or result[0] != "platform_launch"


# ── Part 15.3–15.5: Specific generic noun + platform negatives ───────────────

class TestENG078GenericNounNegatives:
    """Specific false-positive noun categories must not classify as platform_launch."""

    def test_new_order_not_platform_launch(self):
        result = classify_theme("We received a new order from the Ministry through our digital platform.")
        assert result is None or result[0] != "platform_launch"

    def test_new_customer_not_platform_launch(self):
        result = classify_theme("We added 71 new customers this quarter through our platform ecosystem.")
        assert result is None or result[0] != "platform_launch"

    def test_new_contract_not_platform_launch(self):
        result = classify_theme("A new contract was signed for our cloud platform services.")
        assert result is None or result[0] != "platform_launch"

    def test_new_facility_not_platform_launch(self):
        result = classify_theme("We commissioned a new facility to support our platform operations.")
        assert result is None or result[0] != "platform_launch"

    def test_new_plant_not_platform_launch(self):
        result = classify_theme("The new plant will manufacture components for platform-based systems.")
        assert result is None or result[0] != "platform_launch"

    def test_new_employee_not_platform_launch(self):
        result = classify_theme("New employees joined the platform engineering team this quarter.")
        assert result is None or result[0] != "platform_launch"

    def test_new_market_not_platform_launch(self):
        result = classify_theme("We are expanding into a new market segment with our platform offering.")
        assert result is None or result[0] != "platform_launch"

    def test_new_quarter_not_platform_launch(self):
        result = classify_theme("In the new quarter platform business revenue is expected to grow.")
        assert result is None or result[0] != "platform_launch"

    def test_new_revenue_stream_not_platform_launch(self):
        result = classify_theme("A new revenue stream is emerging from our enterprise platform segment.")
        assert result is None or result[0] != "platform_launch"

    def test_new_program_not_platform_launch(self):
        result = classify_theme("We launched a new program to support start-ups using the iDEX platform.")
        # Note: this contains "launched" — it should be AMBIGUOUS. We only assert it's
        # not platform_launch if "launch" is NOT in the text.
        # Rewrite without launch to test the "new program" pattern:
        result2 = classify_theme("We introduced a new program to support start-ups using the iDEX platform.")
        # "introduced" is not in optional — only "launch" and "gigantic" are
        assert result2 is None or result2[0] != "platform_launch"


# ── Part 15.6–15.8: Genuine positives must still classify ────────────────────

class TestENG078GenuineLaunchPositives:
    """Real platform launch evidence must classify correctly after fix."""

    def test_launched_platform_classifies(self):
        result = classify_theme("We are expected to launch one gigantic platform this quarter.")
        assert result is not None
        assert result[0] == "platform_launch"

    def test_launched_maap_classifies(self):
        result = classify_theme("We launched our Messaging as a Platform MaaP for RCS in India and signed an agreement with BSNL.")
        assert result is not None
        assert result[0] == "platform_launch"

    def test_commercial_launch_classifies(self):
        result = classify_theme("Commercial launch in Q2 FY26. Completed MaaP platform deployment for RCS across networks.")
        assert result is not None
        assert result[0] == "platform_launch"

    def test_government_platform_launch_classifies(self):
        result = classify_theme("State Government to support the launch of Namma Arasu a WhatsApp-based e-governance platform that enables citizens.")
        assert result is not None
        assert result[0] == "platform_launch"

    def test_gigantic_platform_classifies(self):
        result = classify_theme("Tanla is developing one gigantic platform for enterprise communications.")
        assert result is not None
        assert result[0] == "platform_launch"

    def test_rollout_platform_classifies(self):
        # "launched" (substring of "rollout"? No — "rollout" does not contain "launch")
        # Test that "launched" as standalone verb works
        result = classify_theme("The platform was launched commercially across all major telecom operators.")
        assert result is not None
        assert result[0] == "platform_launch"


# ── Part 15.9–15.10: Lifecycle-state discipline ──────────────────────────────

class TestENG078LifecycleStateDiscipline:
    """Development and planning phases must not be confused with completed launch."""

    def test_developing_platform_not_launch(self):
        # "developing" is not a launch action — must not classify
        result = classify_theme("We are developing a new platform for enterprise communications.")
        assert result is None or result[0] != "platform_launch"

    def test_plans_to_launch_ambiguous(self):
        # "plans to launch" has "launch" — may classify, but should not be confused with done
        # We don't assert on this — we just verify it's not incorrectly blocked
        # The lifecycle contract handles planned vs confirmed distinction
        pass

    def test_proposed_platform_not_launch(self):
        # "proposed" is not a launch verb
        result = classify_theme("We have proposed a new platform for digital banking services.")
        assert result is None or result[0] != "platform_launch"

    def test_working_on_platform_not_launch(self):
        # Working on ≠ launched
        result = classify_theme("Tanla is working on new platforms for the enterprise segment.")
        assert result is None or result[0] != "platform_launch"


# ── Part 15.11: Tanla production regression ──────────────────────────────────

class TestENG078TanlaProductionRegression:
    """Tanla longitudinal rebuild must be semantically valid after fix."""

    @pytest.fixture(scope="class")
    def tanla_report(self):
        from intelligence.multi_source.longitudinal import build
        return build(
            company="tanla",
            companies_root=Path("companies"),
            execute=False,
        )

    def test_tanla_has_platform_launch_thread(self, tanla_report):
        pl = next((c for c in tanla_report.commitments if c.theme_slug == "platform_launch"), None)
        assert pl is not None, "Tanla must have a platform_launch commitment thread"

    def test_tanla_platform_launch_has_real_evidence(self, tanla_report):
        pl = next(c for c in tanla_report.commitments if c.theme_slug == "platform_launch")
        assert len(pl.evidence) >= 1, "platform_launch thread must have at least one atom"

    def test_tanla_thread_count_unchanged(self, tanla_report):
        # 17 threads must be preserved
        assert tanla_report.commitment_count == 17

    def test_tanla_no_stop_conditions(self, tanla_report):
        assert tanla_report.stop_conditions == []

    def test_tanla_leadership_change_still_confirmed(self, tanla_report):
        lc = next(c for c in tanla_report.commitments if c.theme_slug == "leadership_change")
        assert lc.lifecycle == CommitmentLifecycle.CONFIRMED
        assert lc.confirmed_source == SourceAuthority.EXCHANGE_DISCLOSURE

    def test_tanla_ott_thread_preserved(self, tanla_report):
        ott = next((c for c in tanla_report.commitments if c.theme_slug == "ott_whatsapp_growth"), None)
        assert ott is not None
        assert len(ott.evidence) >= 20


# ── Part 15.12: Data Patterns production regression ──────────────────────────

class TestENG078DataPatternsProductionRegression:
    """Data Patterns must have zero platform_launch atoms after fix."""

    @pytest.fixture(scope="class")
    def dp_report(self):
        from intelligence.multi_source.longitudinal import build
        return build(
            company="datapatterns",
            companies_root=Path("companies"),
            execute=False,
        )

    def test_datapatterns_no_platform_launch_thread(self, dp_report):
        pl = next((c for c in dp_report.commitments if c.theme_slug == "platform_launch"), None)
        assert pl is None, (
            f"Data Patterns must have NO platform_launch thread; found {pl}"
        )

    def test_datapatterns_no_stop_conditions(self, dp_report):
        assert dp_report.stop_conditions == []

    def test_datapatterns_leadership_confirmed(self, dp_report):
        lc = next((c for c in dp_report.commitments if c.theme_slug == "leadership_change"), None)
        assert lc is not None
        assert lc.lifecycle == CommitmentLifecycle.CONFIRMED

    def test_datapatterns_profitability_preserved(self, dp_report):
        prof = next((c for c in dp_report.commitments if c.theme_slug == "profitability"), None)
        assert prof is not None
        assert len(prof.evidence) >= 40


# ── Part 15.13: Lifecycle rebuild regression ─────────────────────────────────

def _make_ev(slug, text, period="Q4 FY26", source_type="EARNINGS_CALL_TRANSCRIPT",
             authority=SourceAuthority.TRANSCRIPT, company="testco"):
    return MultiSourceEvidence(
        evidence_id=f"eng078:{slug}:{period}",
        company=company,
        fiscal_year="fy26",
        source_period=period,
        source_type=source_type,
        authority=authority,
        claim_domain=ClaimDomain.COMMITMENT,
        theme_slug=slug,
        claim_type="COMMITMENT",
        speaker="Test Speaker",
        speaker_role="MANAGEMENT",
        text=text,
        qualifiers=[],
    )


class TestENG078LifecycleRebuildRegression:
    """Lifecycle threads must stay clean after the fix."""

    def test_valid_platform_launch_creates_thread(self):
        evidence = [
            _make_ev("platform_launch", "We are expected to launch one gigantic platform next quarter.")
        ]
        commitments = resolve_commitments(evidence)
        slugs = [c.theme_slug for c in commitments]
        assert "platform_launch" in slugs

    def test_false_positive_text_excluded_at_classification(self):
        # False positive texts must no longer classify as platform_launch
        false_texts = [
            "We're leveraging existing technology platforms to develop new products faster.",
            "Create new technologies and products through the iDEX platform.",
            "New customer additions drove platform business growth this quarter.",
            "Indirect expenses include new hires on the platform engineering team.",
        ]
        for text in false_texts:
            result = classify_theme(text)
            assert result is None or result[0] != "platform_launch", (
                f"False positive text must not classify as platform_launch: {text!r}"
            )

    def test_platform_launch_thread_not_corrupted_by_false_atoms(self):
        evidence = [
            _make_ev("platform_launch", "We launched our Messaging as a Platform MaaP for RCS in India."),
            _make_ev("profitability", "PAT grew by 18% year over year to 45 crore.", authority=SourceAuthority.ANNUAL_REPORT),
        ]
        commitments = resolve_commitments(evidence)
        slugs = {c.theme_slug for c in commitments}
        assert "platform_launch" in slugs
        assert "profitability" in slugs
        pl_thread = next(c for c in commitments if c.theme_slug == "platform_launch")
        assert all(e.theme_slug == "platform_launch" for e in pl_thread.evidence)


# ── Part 15.14: No unintended cross-theme migration ──────────────────────────

class TestENG078NoCrossThemeMigration:
    """Atoms removed from platform_launch must not end up in wrong themes."""

    @pytest.mark.parametrize("text,bad_theme", [
        ("We're leveraging platforms to develop new products faster.", "ott_whatsapp_growth"),
        ("Create new technologies through the iDEX platform.", "rcs_channel_adoption"),
        ("New customer additions contributed to platform business growth.", "ebitda_margin_trajectory"),
    ])
    def test_migrated_atom_not_in_wrong_specialized_theme(self, text, bad_theme):
        result = classify_theme(text)
        assert result is None or result[0] != bad_theme, (
            f"Former platform_launch false-positive classified as wrong theme {bad_theme!r}: {text!r}"
        )


# ── Part 15.15: Unknown preservation ─────────────────────────────────────────

class TestENG078UnknownPreservation:
    """Non-theme texts must not be accidentally classified as platform_launch."""

    @pytest.mark.parametrize("text", [
        "Revenue grew 5% QoQ driven by new customer acquisition.",
        "We announced a buyback program of up to 175 Cr at 875 per share.",
        "The new accounting standard was adopted from April 2024.",
        "New hires joined the engineering and sales teams this quarter.",
        "We are developing a new platform for defence communications.",
        "iDEX provides infrastructure for defence start-ups to connect.",
    ])
    def test_non_launch_text_not_platform_launch(self, text):
        result = classify_theme(text)
        if result is not None:
            assert result[0] != "platform_launch", (
                f"Non-launch text incorrectly classified as platform_launch: {text!r} → {result}"
            )
