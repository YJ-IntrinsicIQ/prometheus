"""Phase 6 — EarningsCallTranscriptProcessor tests.

Production proof: EARNINGS_CALL_TRANSCRIPT_PROCESSOR_CLOSED
The processor is registered only after real-transcript validation proved safe
speaker attribution, Q&A structure, transcript-authority evidence, and routing.

Test groups:
  Part 4  (T01–T07):  Transcript vs non-transcript classification
  Part 6  (T08–T12):  Speaker contract
  Part 7  (T13–T15):  Conservative speaker attribution
  Part 8  (T16–T18):  Section structure (PREPARED_REMARKS / Q_AND_A / OPERATOR)
  Part 9  (T19–T21):  Question vs answer semantics
  Part 10 (T22–T26):  Management claim taxonomy
  Part 11 (T27–T30):  Said ≠ did ≠ outcome
  Part 12 (T31–T34):  Qualifier / uncertainty preservation
  Part 13 (T35–T37):  Analyst assertions not promoted to company facts
  Part 16 (T38–T40):  Source period vs target period
  Part 25 (T41–T44):  Router behaviour (execute=False, execute=True contracts)
  Part 29 (T45–T51):  Transcript vs other source types
  Part 30 (T52–T55):  Cross-source regressions (annual / quarterly / presentation / LTTS)
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Synthetic transcript fixtures
# ---------------------------------------------------------------------------

_BASIC_TRANSCRIPT = """\
Q4 FY26 Earnings Call - Tanla Platforms Limited
April 30, 2026

Participants:
Management:
- Uday Reddy - Chairman and MD
- Srinivas Gunupudi - CFO

Analysts:
- Rahul Jain - Nomura Securities
- Sanjay Jain - IIFL Securities

Operator: Good morning, ladies and gentlemen. Welcome to the Q4 FY26 Earnings Call of Tanla Platforms Limited.

Prepared Remarks

Uday Reddy: Thank you, operator. Good morning. We are pleased to report strong Q4 FY26 results.

Srinivas Gunupudi: Revenue for Q4 FY26 was ₹916 crore, growing 18% year over year.

Question-and-Answer Session

Operator: We will now open the floor for questions. Your next question is from Rahul Jain from Nomura Securities.

Rahul Jain: Good morning. Congratulations on the results. Could you please provide guidance on margins going forward?

Uday Reddy: Thank you, Rahul. We expect margins to improve to 18–20% over the next two quarters. We are targeting cost efficiencies.

Operator: Your next question is from Sanjay Jain from IIFL Securities.

Sanjay Jain: Will you commission the new data centre by Q3 FY27?

Srinivas Gunupudi: We plan to commission the facility by Q3 FY27, subject to regulatory approvals.
"""

_PREPARED_ONLY = """\
Q2 FY27 Earnings Call - Demo Corp

Prepared Remarks

CEO: Good morning. We are pleased with the quarter.
CFO: Revenue came in at ₹500 crore.
"""

_OPERATOR_BRIDGE_TRANSCRIPT = """\
Operator: Your next question is from Ankit from Goldman Sachs.
Ankit: Thank you. Could management confirm capex plans?
CFO: We intend to deploy ₹1,200 crore in capex over the next eighteen months.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manifest(
    *,
    source_type_val: str = "EARNINGS_CALL_TRANSCRIPT",
    status_val: str = "IDENTIFIED",
    company: str = "tanla",
    fiscal_year: str = "fy26",
    fiscal_quarter_val: str | None = "Q4",
    content_hash: str = "sha256:abcdef1234567890",
    source_channel_val: str = "EXCHANGE_FILING",
):
    """Build a minimal DocumentIntakeManifest for transcript tests."""
    from knowledge.document_intake import (
        ClassificationState,
        ClassificationStatus,
        CompanyIdentity,
        ConfidenceLevel,
        DetectionMethod,
        DocumentDates,
        DocumentIdentity,
        DocumentIntakeManifest,
        EntityScope,
        FileIdentity,
        FiscalQuarter,
        IntakeProvenance,
        ReportingPeriod,
        SourceChannel,
        SourceType,
    )

    status_map = {
        "IDENTIFIED": ClassificationStatus.IDENTIFIED,
        "REVIEW_REQUIRED": ClassificationStatus.REVIEW_REQUIRED,
    }
    type_map = {
        "EARNINGS_CALL_TRANSCRIPT": SourceType.EARNINGS_CALL_TRANSCRIPT,
        "INVESTOR_PRESENTATION": SourceType.INVESTOR_PRESENTATION,
        "QUARTERLY_REPORT": SourceType.QUARTERLY_REPORT,
        "ANNUAL_REPORT": SourceType.ANNUAL_REPORT,
        "UNKNOWN": SourceType.UNKNOWN,
    }
    quarter_map = {
        "Q1": FiscalQuarter.Q1, "Q2": FiscalQuarter.Q2,
        "Q3": FiscalQuarter.Q3, "Q4": FiscalQuarter.Q4,
    }

    return DocumentIntakeManifest(
        document_id=content_hash,
        file=FileIdentity(
            original_filename="test_transcript.pdf",
            content_hash=content_hash,
            mime_type="application/pdf",
            size_bytes=100_000,
            storage_path="test_transcript.pdf",
        ),
        company_identity=CompanyIdentity(
            resolved_company_key=company,
            detected_legal_name="",
            detected_display_name="",
            confidence=ConfidenceLevel.HIGH,
            evidence=[],
        ),
        document_identity=DocumentIdentity(
            source_type=type_map[source_type_val],
            source_channel=SourceChannel[source_channel_val],
            document_subtype=source_type_val.lower(),
            confidence=ConfidenceLevel.HIGH,
            evidence=[],
        ),
        reporting_period=ReportingPeriod(
            fiscal_year=fiscal_year,
            fiscal_quarter=quarter_map.get(fiscal_quarter_val) if fiscal_quarter_val else None,
            confidence=ConfidenceLevel.HIGH,
            evidence=[],
        ),
        document_dates=DocumentDates(),
        entity_scope=EntityScope.UNKNOWN,
        language="en",
        classification=ClassificationState(
            overall_confidence=ConfidenceLevel.HIGH,
            status=status_map[status_val],
            unresolved_fields=[],
            warnings=[],
        ),
        provenance=IntakeProvenance(
            ingestion_timestamp="2026-09-02T00:00:00+00:00",
            classifier_version="document_identifier.v4",
            detection_method=DetectionMethod.UNKNOWN,
        ),
    )


# ---------------------------------------------------------------------------
# Part 4 — Transcript vs non-transcript classification (T01–T07)
# ---------------------------------------------------------------------------

class TestTranscriptClassification:
    """Part 29: transcript vs other source types classifier contract."""

    def _classify(self, text: str, filename: str = "unknown.pdf"):
        from knowledge.document_identifier import _classify_source_type
        st, conf, _ = _classify_source_type(text, filename)
        return st

    def test_t01_earnings_call_transcript_label(self):
        """'Earnings Call Transcript' title → EARNINGS_CALL_TRANSCRIPT."""
        from knowledge.document_intake import SourceType
        text = "Q4 FY26 Earnings Call Transcript\nTanla Platforms Limited\nOperator: Good morning."
        assert self._classify(text) == SourceType.EARNINGS_CALL_TRANSCRIPT

    def test_t02_operator_bridge_phrase(self):
        """'Your next question is from' → EARNINGS_CALL_TRANSCRIPT."""
        from knowledge.document_intake import SourceType
        text = "Operator: Your next question is from Rahul from Nomura. Good morning everyone."
        assert self._classify(text) == SourceType.EARNINGS_CALL_TRANSCRIPT

    def test_t03_prepared_remarks_qna(self):
        """'Prepared Remarks' + 'Question-and-Answer Session' → EARNINGS_CALL_TRANSCRIPT."""
        from knowledge.document_intake import SourceType
        text = (
            "Q1 FY27 Earnings Call\n\nPrepared Remarks\n\nCEO: Good morning.\n\n"
            "Question-and-Answer Session\n\nOperator: Your first question is from..."
        )
        assert self._classify(text) == SourceType.EARNINGS_CALL_TRANSCRIPT

    def test_t04_quarterly_report_not_transcript(self):
        """A formal quarterly results document is NOT an earnings-call transcript."""
        from knowledge.document_intake import SourceType
        text = (
            "Quarterly Disclosures Q1 FY27\n"
            "Three months ended June 30, 2026\n"
            "Unaudited Financial Results\n"
            "Limited Review Report\n"
            "Revenue: ₹12,264 Mn\n"
        )
        result = self._classify(text)
        assert result == SourceType.QUARTERLY_REPORT

    def test_t05_investor_presentation_not_transcript(self):
        """An investor presentation slide deck is NOT a transcript."""
        from knowledge.document_intake import SourceType
        text = (
            "Investor Update Q4 FY26\n"
            "Slide 1: Business Overview\n"
            "Slide 2: Financial Highlights\n"
            "Revenue grew 18% YoY\n"
        )
        result = self._classify(text)
        assert result != SourceType.EARNINGS_CALL_TRANSCRIPT

    def test_t06_annual_report_not_transcript(self):
        """An annual report is NOT a transcript even if it has Q&A content."""
        from knowledge.document_intake import SourceType
        text = (
            "Annual Report FY26\n"
            "Management Discussion and Analysis\n"
            "The Board of Directors presents the Annual Report.\n"
            "Financial Year 2025-26\n"
        )
        result = self._classify(text)
        assert result == SourceType.ANNUAL_REPORT

    def test_t07_concall_filename_bonus_does_not_override_content(self):
        """Filename 'concall.pdf' only adds a small bonus; content wins."""
        from knowledge.document_intake import SourceType
        # Annual report content should still win even with a concall filename.
        text = (
            "Annual Report FY26\n"
            "Management Discussion and Analysis\n"
            "Financial Year 2025-26\n"
            "Board of Directors Annual Statutory Report\n"
        )
        result = self._classify(text, filename="tanla_concall")
        # Content should dominate; transcript signals are weak here.
        assert result == SourceType.ANNUAL_REPORT


# ---------------------------------------------------------------------------
# Part 6 — Speaker contract (T08–T12)
# ---------------------------------------------------------------------------

class TestSpeakerContract:
    """Speaker role classification contract."""

    def test_t08_operator_label_gives_operator_role(self):
        from knowledge.document_processor import SpeakerRole, _classify_speaker_role
        role = _classify_speaker_role("Operator", {}, "tanla")
        assert role == SpeakerRole.OPERATOR

    def test_t09_moderator_label_gives_moderator_role(self):
        from knowledge.document_processor import SpeakerRole, _classify_speaker_role
        role = _classify_speaker_role("Moderator", {}, "tanla")
        assert role == SpeakerRole.MODERATOR

    def test_t10_participant_list_management_entry(self):
        from knowledge.document_processor import SpeakerRole, _classify_speaker_role
        registry = {"Uday Reddy": SpeakerRole.MANAGEMENT}
        role = _classify_speaker_role("Uday Reddy", registry, "tanla")
        assert role == SpeakerRole.MANAGEMENT

    def test_t11_analyst_from_firm_classified_analyst(self):
        from knowledge.document_processor import SpeakerRole, _classify_speaker_role
        # Name with securities firm in it.
        role = _classify_speaker_role("Rahul Jain from Nomura Securities", {}, "tanla")
        assert role == SpeakerRole.ANALYST

    def test_t12_cfo_in_participant_registry_is_management(self):
        from knowledge.document_processor import SpeakerRole, _classify_speaker_role
        registry = {"Srinivas Gunupudi": SpeakerRole.MANAGEMENT}
        role = _classify_speaker_role("Srinivas Gunupudi", registry, "tanla")
        assert role == SpeakerRole.MANAGEMENT


# ---------------------------------------------------------------------------
# Part 7 — Conservative speaker attribution (T13–T15)
# ---------------------------------------------------------------------------

class TestConservativeSpeakerAttribution:
    """Missing > guessed: unknown speakers must stay UNKNOWN."""

    def test_t13_unknown_speaker_stays_unknown(self):
        from knowledge.document_processor import SpeakerRole, _classify_speaker_role
        role = _classify_speaker_role("John Smith", {}, "tanla")
        assert role == SpeakerRole.UNKNOWN

    def test_t14_partial_match_still_uses_registry(self):
        from knowledge.document_processor import SpeakerRole, _classify_speaker_role
        # Partial name match — first name only in registry.
        registry = {"Uday": SpeakerRole.MANAGEMENT}
        role = _classify_speaker_role("Uday Reddy", registry, "tanla")
        # 'Uday' is a substring of 'uday reddy' → MANAGEMENT via registry.
        assert role == SpeakerRole.MANAGEMENT

    def test_t15_no_registry_no_heuristic_match_is_unknown(self):
        from knowledge.document_processor import SpeakerRole, _classify_speaker_role
        # Empty registry, no firm suffix, no company key match.
        role = _classify_speaker_role("RandomPerson", {}, "tanla")
        assert role == SpeakerRole.UNKNOWN


# ---------------------------------------------------------------------------
# Part 8 — Section structure (T16–T18)
# ---------------------------------------------------------------------------

class TestSectionStructure:
    """Transcript sections must be correctly identified."""

    def test_t16_prepared_remarks_section_detected(self):
        from knowledge.document_processor import TranscriptSection, _segment_turns
        text = "Prepared Remarks\n\nCEO: Good morning, thank you for joining.\n"
        turns = _segment_turns(text, {}, "demo")
        assert any(t["section"] == TranscriptSection.PREPARED_REMARKS.value for t in turns), (
            "At least one turn must be in PREPARED_REMARKS section"
        )

    def test_t17_qna_section_detected(self):
        from knowledge.document_processor import TranscriptSection, _segment_turns
        text = (
            "Question-and-Answer Session\n\n"
            "Operator: Your next question is from Rahul from Nomura.\n"
            "Rahul: Could you clarify the margin guidance?\n"
            "CEO: We expect margins to reach 20%.\n"
        )
        turns = _segment_turns(text, {"Rahul": __import__("knowledge.document_processor", fromlist=["SpeakerRole"]).SpeakerRole.ANALYST}, "demo")
        qna_turns = [t for t in turns if t["section"] == TranscriptSection.Q_AND_A.value]
        assert len(qna_turns) > 0, "Q&A section turns must be identified"

    def test_t18_operator_turn_is_operator_section(self):
        from knowledge.document_processor import TranscriptSection, SpeakerRole, _segment_turns
        text = "Operator: Your next question is from Sanjay from IIFL.\n"
        turns = _segment_turns(text, {}, "demo")
        assert any(t["section"] == TranscriptSection.OPERATOR_TURN.value for t in turns), (
            "Operator turn must be in OPERATOR_TURN section"
        )


# ---------------------------------------------------------------------------
# Part 9 — Question vs answer semantics (T19–T21)
# ---------------------------------------------------------------------------

class TestQuestionVsAnswer:
    """Analyst questions must be distinguished from management responses."""

    def _turns_from_text(self, text, registry=None):
        from knowledge.document_processor import _segment_turns
        return _segment_turns(text, registry or {}, "demo")

    def test_t19_analyst_question_flagged(self):
        from knowledge.document_processor import SpeakerRole
        registry = {"Rahul Jain": SpeakerRole.ANALYST}
        text = "Rahul Jain: Could you please explain the margin decline?\n"
        turns = self._turns_from_text(text, registry)
        assert any(t["is_question"] for t in turns), (
            "Analyst turn with a question mark must be flagged is_question=True"
        )

    def test_t20_management_answer_not_flagged_as_question(self):
        from knowledge.document_processor import SpeakerRole
        registry = {"CEO": SpeakerRole.MANAGEMENT}
        text = "CEO: We expect margins to improve in the coming quarters.\n"
        turns = self._turns_from_text(text, registry)
        assert not any(t["is_question"] for t in turns), (
            "Management response must never be flagged as a question"
        )

    def test_t21_management_answer_linked_to_prior_question(self):
        from knowledge.document_processor import SpeakerRole
        registry = {
            "Analyst": SpeakerRole.ANALYST,
            "CEO": SpeakerRole.MANAGEMENT,
        }
        text = (
            "Analyst: Will you achieve 20% margin next year?\n"
            "CEO: We expect to reach that level by Q3 FY27.\n"
        )
        turns = self._turns_from_text(text, registry)
        mgmt_turns = [t for t in turns if t["speaker_role"] == SpeakerRole.MANAGEMENT.value]
        assert any(t["question_turn_index"] is not None for t in mgmt_turns), (
            "Management answer must be linked to prior analyst question"
        )


# ---------------------------------------------------------------------------
# Part 10 — Management claim taxonomy (T22–T26)
# ---------------------------------------------------------------------------

class TestManagementClaimTaxonomy:
    """Claim type classification must respect semantic distinctions."""

    def _claim_type(self, text: str):
        from knowledge.document_processor import _classify_claim_type
        return _classify_claim_type(text)

    def test_t22_commitment_classified(self):
        from knowledge.document_processor import ManagementClaimType
        result = self._claim_type("We commit to delivering ₹5,000 crore revenue this year.")
        assert result == ManagementClaimType.COMMITMENT

    def test_t23_target_classified(self):
        from knowledge.document_processor import ManagementClaimType
        result = self._claim_type("We are targeting 20% margin by Q4 FY27.")
        assert result == ManagementClaimType.TARGET

    def test_t24_expectation_classified(self):
        from knowledge.document_processor import ManagementClaimType
        result = self._claim_type("We expect revenue to grow 15% next quarter.")
        assert result == ManagementClaimType.EXPECTATION

    def test_t25_guidance_classified(self):
        from knowledge.document_processor import ManagementClaimType
        result = self._claim_type("Our guidance for FY27 is margin in the range of 18–20%.")
        assert result == ManagementClaimType.GUIDANCE

    def test_t26_risk_acknowledgement_classified(self):
        from knowledge.document_processor import ManagementClaimType
        result = self._claim_type("There is a risk of margin headwinds if commodity prices rise.")
        assert result == ManagementClaimType.RISK_ACKNOWLEDGEMENT


# ---------------------------------------------------------------------------
# Part 11 — Said ≠ did ≠ outcome (T27–T30)
# ---------------------------------------------------------------------------

class TestSaidDidOutcomeDistinction:
    """Speech must never be promoted to operational completion."""

    def test_t27_expectation_not_completion(self):
        from knowledge.document_processor import ManagementClaimType, _classify_claim_type
        text = "We expect Plant X to be commissioned in Q3."
        result = _classify_claim_type(text)
        assert result == ManagementClaimType.EXPECTATION, (
            "'expect to commission' must be EXPECTATION, not a completion fact"
        )

    def test_t28_commissioned_is_factual_not_proven_outcome(self):
        from knowledge.document_processor import ManagementClaimType, _classify_claim_type
        # "We commissioned" = past-tense statement, not independently verified outcome.
        text = "We commissioned Plant X last quarter."
        result = _classify_claim_type(text)
        # No expectation/target/guidance keywords → FACTUAL_STATEMENT (management claim only).
        assert result == ManagementClaimType.FACTUAL_STATEMENT, (
            "Past-tense management statement is a CLAIM, not independently proven outcome"
        )

    def test_t29_may_commission_is_qualified_expectation(self):
        from knowledge.document_processor import ManagementClaimType, _classify_claim_type
        text = "We may commission the plant by end of the year."
        result = _classify_claim_type(text)
        # "may" matches UNCERTAINTY first... but no stronger keyword overrides.
        assert result in (ManagementClaimType.UNCERTAINTY, ManagementClaimType.INTENTION), (
            "'may commission' must preserve uncertainty semantics"
        )

    def test_t30_analyst_question_not_converted_to_commitment(self):
        from knowledge.document_processor import SpeakerRole, _segment_turns, _extract_management_claims
        registry = {"Analyst": SpeakerRole.ANALYST, "CEO": SpeakerRole.MANAGEMENT}
        text = (
            "Analyst: Will you commission the plant by Q3 FY27?\n"
            "CEO: We are looking into it.\n"
        )
        turns = _segment_turns(text, registry, "demo")
        claims = _extract_management_claims(turns, "Q4 FY26")
        # Analyst question must not appear in management claims.
        analyst_sourced = [c for c in claims if c["speaker_role"] == SpeakerRole.ANALYST.value]
        assert len(analyst_sourced) == 0, (
            "Analyst questions must never generate management claim candidates"
        )


# ---------------------------------------------------------------------------
# Part 12 — Qualifier / uncertainty preservation (T31–T34)
# ---------------------------------------------------------------------------

class TestQualifierPreservation:
    """Qualifiers and uncertainty must never be stripped during normalization."""

    def test_t31_expect_qualifier_preserved(self):
        from knowledge.document_processor import _extract_qualifiers
        qualifiers = _extract_qualifiers("We expect margins to improve next quarter.")
        assert "expect" in qualifiers

    def test_t32_may_qualifier_preserved(self):
        from knowledge.document_processor import _extract_qualifiers
        qualifiers = _extract_qualifiers("Revenue may reach ₹5,000 crore subject to market conditions.")
        assert "may" in qualifiers
        assert "subject to" in qualifiers

    def test_t33_target_qualifier_preserved(self):
        from knowledge.document_processor import _extract_qualifiers
        qualifiers = _extract_qualifiers("We are targeting 20% EBITDA margin.")
        assert "target" in qualifiers

    def test_t34_no_qualifier_word_in_plain_statement(self):
        from knowledge.document_processor import _extract_qualifiers
        qualifiers = _extract_qualifiers("Revenue for Q4 was ₹916 crore.")
        assert len(qualifiers) == 0, (
            "Plain factual statements must not generate spurious qualifiers"
        )


# ---------------------------------------------------------------------------
# Part 13 — Analyst assertions not promoted (T35–T37)
# ---------------------------------------------------------------------------

class TestAnalystAssertionsNotPromoted:
    """Analyst assertions must remain question/analyst evidence only."""

    def test_t35_analyst_assertion_not_in_management_claims(self):
        from knowledge.document_processor import SpeakerRole, _segment_turns, _extract_management_claims
        registry = {"Analyst": SpeakerRole.ANALYST}
        text = "Analyst: You lost market share this quarter, correct?\n"
        turns = _segment_turns(text, registry, "demo")
        claims = _extract_management_claims(turns, "Q4 FY26")
        assert len(claims) == 0, (
            "Analyst assertion must never generate a management claim"
        )

    def test_t36_analyst_revenue_statement_not_company_truth(self):
        from knowledge.document_processor import SpeakerRole, _segment_turns, _extract_management_claims
        registry = {"Analyst": SpeakerRole.ANALYST}
        text = "Analyst: Revenue fell 10% this quarter based on our estimates.\n"
        turns = _segment_turns(text, registry, "demo")
        claims = _extract_management_claims(turns, "Q4 FY26")
        assert len(claims) == 0, (
            "Analyst revenue statement must not become a company financial fact"
        )

    def test_t37_operator_boilerplate_not_substantive_evidence(self):
        from knowledge.document_processor import SpeakerRole, _segment_turns, _extract_management_claims
        registry = {}
        text = "Operator: Good morning, ladies and gentlemen. Welcome to the earnings call.\n"
        turns = _segment_turns(text, registry, "demo")
        claims = _extract_management_claims(turns, "Q4 FY26")
        assert len(claims) == 0, (
            "Operator boilerplate must never become substantive evidence"
        )


# ---------------------------------------------------------------------------
# Part 16 — Source period vs target period (T38–T40)
# ---------------------------------------------------------------------------

class TestSourceVsTargetPeriod:
    """Source and target periods must remain distinct."""

    def test_t38_source_period_preserved_in_claim(self):
        from knowledge.document_processor import SpeakerRole, _segment_turns, _extract_management_claims
        registry = {"CFO": SpeakerRole.MANAGEMENT}
        text = "CFO: We plan to commission the facility by Q3 FY27.\n"
        turns = _segment_turns(text, registry, "demo")
        claims = _extract_management_claims(turns, "Q1 FY27")
        assert len(claims) > 0
        assert claims[0]["source_period"] == "Q1 FY27", (
            "Source period must match the document's reporting period"
        )

    def test_t39_target_period_extracted_when_explicit(self):
        from knowledge.document_processor import SpeakerRole, _segment_turns, _extract_management_claims
        registry = {"CEO": SpeakerRole.MANAGEMENT}
        text = "CEO: We expect the project to complete by Q4 FY27.\n"
        turns = _segment_turns(text, registry, "demo")
        claims = _extract_management_claims(turns, "Q1 FY27")
        assert len(claims) > 0
        target = claims[0]["target_period"]
        assert target is not None and "fy27" in target.lower(), (
            "Target period 'Q4 FY27' must be extracted separately from source period"
        )

    def test_t40_source_period_not_overwritten_by_target(self):
        from knowledge.document_processor import SpeakerRole, _segment_turns, _extract_management_claims
        registry = {"CFO": SpeakerRole.MANAGEMENT}
        text = "CFO: Our FY28 capex target is ₹2,000 crore.\n"
        turns = _segment_turns(text, registry, "demo")
        claims = _extract_management_claims(turns, "Q4 FY26")
        assert len(claims) > 0
        assert claims[0]["source_period"] == "Q4 FY26", (
            "Source period must not be overwritten by the target period"
        )


# ---------------------------------------------------------------------------
# Part 25 — Router behaviour (T41–T44)
# ---------------------------------------------------------------------------

class TestRouterBehaviour:
    """Router contract: AVAILABLE after production proof; execute safety."""

    def test_t41_transcript_router_state_available(self):
        """EARNINGS_CALL_TRANSCRIPT must be AVAILABLE after production proof."""
        from knowledge.document_router import ProcessorState, SourceRouter
        from knowledge.document_intake import SourceType
        from knowledge.document_router import _SOURCE_TYPE_PROCESSOR_MAP
        state = _SOURCE_TYPE_PROCESSOR_MAP.get(SourceType.EARNINGS_CALL_TRANSCRIPT)
        assert state == ProcessorState.AVAILABLE

    def test_t42_transcript_in_processor_registry(self):
        """EarningsCallTranscriptProcessor appears in _PROCESSOR_REGISTRY."""
        from knowledge.document_processor import _PROCESSOR_REGISTRY, EarningsCallTranscriptProcessor
        registry_types = [type(p) for p in _PROCESSOR_REGISTRY]
        assert EarningsCallTranscriptProcessor in registry_types

    def test_t43_registered_processor_resolves_for_transcript(self):
        """Registered transcript manifest resolves to the transcript processor."""
        from knowledge.document_processor import _find_processor
        from knowledge.document_processor import EarningsCallTranscriptProcessor
        manifest = _make_manifest()
        proc = _find_processor(manifest)
        assert isinstance(proc, EarningsCallTranscriptProcessor)

    def test_t44_can_process_returns_false_for_non_transcript(self):
        """EarningsCallTranscriptProcessor.can_process() rejects non-transcript manifests."""
        from knowledge.document_processor import EarningsCallTranscriptProcessor
        proc = EarningsCallTranscriptProcessor()
        annual_manifest = _make_manifest(source_type_val="ANNUAL_REPORT")
        assert not proc.can_process(annual_manifest)


# ---------------------------------------------------------------------------
# Part 29 — Transcript vs other source types (T45–T51)
# ---------------------------------------------------------------------------

class TestTranscriptVsOtherSources:
    """Confirm classifier boundaries between transcripts and adjacent types."""

    def _classify(self, text: str, fn: str = "doc.pdf"):
        from knowledge.document_identifier import _classify_source_type
        st, _, _ = _classify_source_type(text, fn)
        return st

    def test_t45_conference_call_transcript_label_wins(self):
        from knowledge.document_intake import SourceType
        text = "Conference Call Transcript Q1 FY27\nOperator: Welcome."
        assert self._classify(text) == SourceType.EARNINGS_CALL_TRANSCRIPT

    def test_t46_management_discussion_and_analysis_not_transcript(self):
        """MDA section in annual report must NOT match transcript signals."""
        from knowledge.document_intake import SourceType
        text = (
            "Management Discussion and Analysis\n"
            "Annual Report FY26\n"
            "Financial Year 2025-26\n"
            "Board of Directors\n"
        )
        result = self._classify(text)
        assert result == SourceType.ANNUAL_REPORT, (
            "MDA section is part of annual report, not a transcript"
        )

    def test_t47_earnings_release_with_quotes_not_transcript(self):
        """Earnings release with quoted management text is not a transcript."""
        from knowledge.document_intake import SourceType
        text = (
            "Earnings Release Q4 FY26\n"
            '"We delivered strong results" — CEO\n'
            "Revenue: ₹916 crore\n"
            "Unaudited Financial Results\n"
        )
        result = self._classify(text)
        assert result != SourceType.EARNINGS_CALL_TRANSCRIPT

    def test_t48_shareholder_report_with_embedded_qa_not_transcript(self):
        """Annual report Q&A section does not make the whole document a transcript."""
        from knowledge.document_intake import SourceType
        text = (
            "Annual Report FY26\n"
            "Year Ended March 31, 2026\n"
            "Management Discussion and Analysis\n"
            "Shareholder Q&A\n"
            "Board of Directors\n"
        )
        result = self._classify(text)
        assert result == SourceType.ANNUAL_REPORT

    def test_t49_pure_operator_bridge_is_strong_transcript_signal(self):
        """'Your next question is from' is a very strong transcript signal."""
        from knowledge.document_intake import SourceType
        text = (
            "Operator: Your next question is from Ankit from Goldman Sachs.\n"
            "Ankit: Thank you. Good morning.\n"
        )
        assert self._classify(text) == SourceType.EARNINGS_CALL_TRANSCRIPT

    def test_t50_concall_keyword_in_text_contributes_to_transcript(self):
        """'concall' term in text contributes to transcript classification."""
        from knowledge.document_intake import SourceType
        text = (
            "Q4 FY26 Concall\n"
            "Prepared Remarks\n"
            "Operator: Good morning, ladies and gentlemen.\n"
        )
        assert self._classify(text) == SourceType.EARNINGS_CALL_TRANSCRIPT

    def test_t51_management_discussion_and_analysis_removed_from_transcript_signals(self):
        """'management discussion and analysis' must NOT add score to transcript."""
        from knowledge.document_identifier import _TRANSCRIPT_SIGNALS
        import re
        signal_texts = [p.pattern for p, _ in _TRANSCRIPT_SIGNALS]
        assert not any("management.discussion" in t.lower() for t in signal_texts), (
            "'management discussion and analysis' must be removed from _TRANSCRIPT_SIGNALS "
            "to prevent false positives on annual reports"
        )


# ---------------------------------------------------------------------------
# Part 30 — Cross-source regressions (T52–T55)
# ---------------------------------------------------------------------------

class TestCrossSourceRegressions:
    """Existing source classifications must be unaffected by Phase 6 changes."""

    def _identify(self, path_str: str):
        from pathlib import Path
        from knowledge.document_identifier import identify_document
        p = Path(path_str)
        if not p.exists():
            pytest.skip(f"Test document not available: {path_str}")
        return identify_document(p)

    def test_t52_tanla_quarterly_still_quarterly(self):
        """342tsgdh266.pdf must remain QUARTERLY_REPORT."""
        from knowledge.document_intake import SourceType
        result = self._identify("data/Processed/tanla/q1 fy27/quarterly_report/342tsgdh266.pdf")
        assert result.document_identity.source_type == SourceType.QUARTERLY_REPORT

    def test_t53_tanla_presentation_still_investor_presentation(self):
        """Tanla 3e52b313 must remain INVESTOR_PRESENTATION."""
        from knowledge.document_intake import SourceType
        result = self._identify("data/Processed/tanla/q4 fy26/investor_presentation/3e52b313-f8d6-4893-b039-88b5b8f070f6.pdf")
        assert result.document_identity.source_type == SourceType.INVESTOR_PRESENTATION

    def test_t54_ltts_release_not_transcript(self):
        """LTTS 6965ca6d must NOT be classified as EARNINGS_CALL_TRANSCRIPT.

        Phase 7 reclassified this document from QUARTERLY_REPORT to EARNINGS_RELEASE
        (press release + investor presentation payload inside an exchange filing wrapper).
        Either classification is acceptable here; what must never happen is that a
        press-release-style document is confused for a conference-call transcript.
        """
        from knowledge.document_intake import SourceType
        result = self._identify("data/Processed/ltts/q1 fy27/earnings_release/6965ca6d-58bd-4c7a-a6ac-901f16d7f058.pdf")
        assert result.document_identity.source_type != SourceType.EARNINGS_CALL_TRANSCRIPT, (
            "LTTS Q1 FY27 press release must NOT be classified as an earnings-call transcript"
        )
        assert result.document_identity.source_type in (
            SourceType.EARNINGS_RELEASE, SourceType.QUARTERLY_REPORT
        ), (
            f"LTTS 6965ca6d should be EARNINGS_RELEASE or QUARTERLY_REPORT, "
            f"got {result.document_identity.source_type}"
        )

    def test_t55_ujjivan_annual_still_annual(self):
        """Ujjivan annual report must remain ANNUAL_REPORT."""
        from knowledge.document_intake import SourceType
        result = self._identify("companies/ujjivan/fy25/raw/ujjivan_fy25.pdf")
        assert result.document_identity.source_type == SourceType.ANNUAL_REPORT


# ---------------------------------------------------------------------------
# Additional: EarningsCallTranscriptResult contract
# ---------------------------------------------------------------------------

class TestResultContract:
    """Result dataclass must carry all required fields."""

    def test_result_fields_present(self):
        from knowledge.document_processor import EarningsCallTranscriptResult
        r = EarningsCallTranscriptResult(
            company="tanla",
            fiscal_year="fy26",
            context_quarter=4,
            call_date="April 30, 2026",
            source_file="/path/to/file.pdf",
            storage_path="companies/tanla/fy26/earnings_calls/abcdef12/",
        )
        assert r.company == "tanla"
        assert r.context_quarter == 4
        assert r.call_date == "April 30, 2026"
        assert r.status == "SUCCESS"
        assert r.evidence_count == 0

    def test_result_with_none_quarter(self):
        from knowledge.document_processor import EarningsCallTranscriptResult
        r = EarningsCallTranscriptResult(
            company="tanla",
            fiscal_year="fy26",
            context_quarter=None,
            call_date=None,
            source_file="/path/to/file.pdf",
            storage_path="companies/tanla/fy26/earnings_calls/abcdef12/",
        )
        assert r.context_quarter is None

    def test_to_dict_serializable(self):
        import json
        from knowledge.document_processor import EarningsCallTranscriptResult
        r = EarningsCallTranscriptResult(
            company="demo",
            fiscal_year="fy27",
            context_quarter=2,
            call_date="October 15, 2026",
            source_file="/path/doc.pdf",
            storage_path="companies/demo/fy27/earnings_calls/hash123/",
        )
        d = r.to_dict()
        assert json.dumps(d)  # must be JSON-serializable
        assert d["context_quarter"] == 2


# ---------------------------------------------------------------------------
# Additional: participant-list parsing
# ---------------------------------------------------------------------------

class TestParticipantListParsing:
    """_parse_participant_list must correctly classify management vs analyst."""

    def test_management_extracted_from_participant_list(self):
        from knowledge.document_processor import SpeakerRole, _parse_participant_list
        text = """\
Management:
- Uday Reddy - Chairman and MD
- Srinivas Gunupudi - CFO

Analysts:
- Rahul Jain - Nomura Securities
"""
        registry = _parse_participant_list(text)
        assert any("Uday" in k for k in registry), "Management name must appear in registry"
        assert any(v == SpeakerRole.MANAGEMENT for v in registry.values())

    def test_analyst_extracted_from_participant_list(self):
        from knowledge.document_processor import SpeakerRole, _parse_participant_list
        text = """\
Management:
- CEO

Analysts:
- Rahul Jain - Nomura Securities
"""
        registry = _parse_participant_list(text)
        assert any(v == SpeakerRole.ANALYST for v in registry.values())

    def test_real_pdf_style_standalone_bullet_lines(self):
        """Bullets on their own lines must apply to the following name line."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list
        text = """\
Management
▪
Uday Kumar Reddy - Founder, Chairman & Chief Executive Officer
▪
Anubhav Batra, Chief Financial Officer
Participants that asked the
questions
▪
Keshav Garg- Counter Cyclical PMS
▪
Amit Chandra - HDFC Securities
Moderator:
Welcome to the earnings call.
"""
        registry = _parse_participant_list(text)
        assert registry["Uday Kumar Reddy"] == SpeakerRole.MANAGEMENT
        assert registry["Anubhav Batra"] == SpeakerRole.MANAGEMENT
        assert registry["Keshav Garg"] == SpeakerRole.ANALYST
        assert registry["Amit Chandra"] == SpeakerRole.ANALYST


class TestRealPdfProductionShapes:
    """Regression tests from the first real transcript production proof."""

    def test_metadata_labels_are_not_speaker_turns(self):
        from knowledge.document_processor import SpeakerRole, _segment_turns
        text = """\
Date: May 1, 2026
Scrip Code: 532790
Symbol: TANLA
Sub: Transcript of the Earnings Call.
Moderator: Welcome to the call.
Ritu Mehta: We will now open the floor for Q&A.
"""
        turns = _segment_turns(text, {"Ritu Mehta": SpeakerRole.MANAGEMENT}, "tanla")
        speakers = [turn["raw_speaker"] for turn in turns]
        assert speakers == ["Moderator", "Ritu Mehta"]

    def test_page_provenance_retained_on_turns_and_claims(self):
        from knowledge.document_processor import SpeakerRole, _segment_turns, _extract_management_claims
        text = """\
Moderator: Welcome.
CEO: We expect revenue to improve by Q4 FY27.
"""
        page_ranges = [(7, 0, len(text))]
        turns = _segment_turns(text, {"CEO": SpeakerRole.MANAGEMENT}, "demo", page_ranges)
        claims = _extract_management_claims(turns, "Q1 FY27")
        assert turns[1]["page"] == 7
        assert claims[0]["page"] == 7
        assert claims[0]["target_period"].lower() == "q4 fy27"

    def test_common_evidence_records_get_stable_claim_ids(self):
        from knowledge.document_processor import EarningsCallTranscriptProcessor
        claims = [{
            "speaker": "CEO",
            "normalized_speaker": "CEO",
            "speaker_role": "MANAGEMENT",
            "section": "Q_AND_A",
            "raw_text": "We expect margins to improve.",
            "claim_type": "EXPECTATION",
            "qualifiers": ["expect"],
            "source_period": "Q4 FY26",
            "target_period": None,
            "turn_index": 2,
            "question_turn_index": 1,
            "page": 5,
        }]
        evidence = EarningsCallTranscriptProcessor._build_common_evidence(
            company="demo",
            fiscal_year="fy26",
            source_period="Q4 FY26",
            document_hash="sha256:abcdef1234567890",
            claims=claims,
        )
        assert claims[0]["claim_id"] == "earnings_call:abcdef1234567890:claim:0000"
        assert evidence["records"][0]["authority"] == "TRANSCRIPT"
        assert evidence["records"][0]["page"] == 5

    def test_call_date_prefers_held_on_date_over_filing_date(self):
        from knowledge.document_processor import EarningsCallTranscriptProcessor
        text = """\
Date: May 1, 2026
Sub: Transcript of the Earnings Call.
The call on audited financial results was held on Monday, April 27, 2026, at 4:30 PM IST.
Tanla Platforms Limited
Q4 FY26 Earnings Conference Call Transcript
April 27, 2026
"""
        assert EarningsCallTranscriptProcessor._detect_call_date(text) == "April 27, 2026"


# ─────────────────────────────────────────────────────────────────────────────
# ENG-076: BSE-style transcript format — participant list parsing (Phase 11.1)
# ─────────────────────────────────────────────────────────────────────────────

_BSE_STYLE_TRANSCRIPT = """\
Data Patterns (India) Limited
Q1 FY27 Earnings Conference Call Transcript

MANAGEMENT: MR. S. RANGARAJAN – CMD

MODERATOR:

Ladies and gentlemen, good day and welcome.

S. Rangarajan: Thank you. Revenue for Q1 FY27 was ₹320 crore.

ANALYST:

Prayasi Patel: Can you discuss order inflows?

S. Rangarajan: We expect order inflows to exceed ₹1,500 crore this fiscal.
"""

_BSE_STYLE_MULTI_MGMT = """\
Data Patterns (India) Limited
Q2 FY27 Earnings Conference Call Transcript

MANAGEMENT: MR. S. RANGARAJAN – CMD

MR. VENKATA SUBRAMANIAN – CFO

MODERATOR:

Welcome to the call.

S. Rangarajan: Revenue was strong.

Venkata Subramanian: EBITDA improved to 28%.

Prayasi Patel: What are the capex plans?

S. Rangarajan: We plan to commission the new facility by Q3 FY28.
"""


class TestENG076BseStyleParticipantList:
    """ENG-076: _parse_participant_list handles BSE-style 'MANAGEMENT: MR. NAME' format
    and bare 'MODERATOR:' section headers without contaminating the registry."""

    def test_eng076_management_compound_line_parsed(self):
        """'MANAGEMENT: MR. S. RANGARAJAN' registers S. Rangarajan as MANAGEMENT."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list
        registry = _parse_participant_list(_BSE_STYLE_TRANSCRIPT)
        assert "S. Rangarajan" in registry or "S. RANGARAJAN" in registry or \
               any("rangarajan" in k.lower() for k in registry), \
               f"S. Rangarajan must be in registry as MANAGEMENT; got {registry}"
        key = next(k for k in registry if "rangarajan" in k.lower())
        assert registry[key] == SpeakerRole.MANAGEMENT

    def test_eng076_bare_moderator_label_terminates_mgmt_section(self):
        """Bare 'MODERATOR:' (no trailing space) resets mode so no contamination."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list
        registry = _parse_participant_list(_BSE_STYLE_TRANSCRIPT)
        # Analyst Prayasi Patel must NOT appear as MANAGEMENT
        for key, role in registry.items():
            assert not ("prayasi" in key.lower() and role == SpeakerRole.MANAGEMENT), \
                f"Analyst 'Prayasi Patel' must not be MANAGEMENT; registry={registry}"

    def test_eng076_analyst_not_in_management_registry(self):
        """Analyst names must not be registered as MANAGEMENT in BSE-style format."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list
        registry = _parse_participant_list(_BSE_STYLE_TRANSCRIPT)
        management_keys = [k for k, v in registry.items() if v == SpeakerRole.MANAGEMENT]
        for key in management_keys:
            assert "prayasi" not in key.lower(), \
                f"'Prayasi Patel' (analyst) must not be MANAGEMENT; got {management_keys}"

    def test_eng076_management_turns_extracted_not_zero(self):
        """Management turns must be recognized (non-zero) after participant list fix."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list, _segment_turns
        registry = _parse_participant_list(_BSE_STYLE_TRANSCRIPT)
        text = '\n'.join(_BSE_STYLE_TRANSCRIPT.splitlines())
        turns = _segment_turns(text, registry, "datapatterns")
        mgmt_turns = [t for t in turns if t.get("speaker_role") == SpeakerRole.MANAGEMENT.value]
        assert len(mgmt_turns) > 0, f"Must have management turns; got 0. Registry={registry}"

    def test_eng076_management_claims_non_zero(self):
        """_extract_management_claims must produce at least one claim from BSE-style transcript."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list, _segment_turns, _extract_management_claims
        text = '\n'.join(_BSE_STYLE_TRANSCRIPT.splitlines())
        registry = _parse_participant_list(text)
        turns = _segment_turns(text, registry, "datapatterns")
        claims = _extract_management_claims(turns, "Q1 FY27")
        assert len(claims) > 0, f"Must produce management claims from BSE-style transcript; got 0"

    def test_eng076_analyst_questions_excluded_from_claims(self):
        """Analyst question turns must not appear as management claims."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list, _segment_turns, _extract_management_claims
        text = '\n'.join(_BSE_STYLE_TRANSCRIPT.splitlines())
        registry = _parse_participant_list(text)
        turns = _segment_turns(text, registry, "datapatterns")
        claims = _extract_management_claims(turns, "Q1 FY27")
        for claim in claims:
            assert claim.get("speaker_role") == SpeakerRole.MANAGEMENT.value, \
                f"Claim from analyst must not appear: {claim}"

    def test_eng076_multi_management_speakers_registered(self):
        """Multiple MANAGEMENT speakers in BSE-style format are all registered."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list
        registry = _parse_participant_list(_BSE_STYLE_MULTI_MGMT)
        mgmt_keys = [k for k, v in registry.items() if v == SpeakerRole.MANAGEMENT]
        has_rangarajan = any("rangarajan" in k.lower() for k in mgmt_keys)
        has_venkata = any("venkata" in k.lower() for k in mgmt_keys)
        assert has_rangarajan, f"S. Rangarajan must be MANAGEMENT; registry={registry}"
        assert has_venkata, f"Venkata Subramanian must be MANAGEMENT; registry={registry}"

    def test_eng076_operator_turns_not_in_claims(self):
        """OPERATOR/MODERATOR turns must be excluded from management claims."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list, _segment_turns, _extract_management_claims
        text = '\n'.join(_BSE_STYLE_TRANSCRIPT.splitlines())
        registry = _parse_participant_list(text)
        turns = _segment_turns(text, registry, "datapatterns")
        claims = _extract_management_claims(turns, "Q1 FY27")
        for claim in claims:
            assert claim.get("speaker_role") != "MODERATOR", \
                f"MODERATOR turn must not produce claims: {claim}"

    def test_eng076_speaker_provenance_preserved(self):
        """Each claim must carry the speaker name that produced it."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list, _segment_turns, _extract_management_claims
        text = '\n'.join(_BSE_STYLE_TRANSCRIPT.splitlines())
        registry = _parse_participant_list(text)
        turns = _segment_turns(text, registry, "datapatterns")
        claims = _extract_management_claims(turns, "Q1 FY27")
        for claim in claims:
            assert claim.get("speaker"), f"Claim must have a speaker: {claim}"
            assert claim.get("normalized_speaker"), f"Claim must have normalized_speaker: {claim}"

    def test_eng076_source_period_preserved_in_claims(self):
        """source_period must be set on all claims."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list, _segment_turns, _extract_management_claims
        text = '\n'.join(_BSE_STYLE_TRANSCRIPT.splitlines())
        registry = _parse_participant_list(text)
        turns = _segment_turns(text, registry, "datapatterns")
        claims = _extract_management_claims(turns, "Q1 FY27")
        assert len(claims) > 0
        for claim in claims:
            assert claim.get("source_period") == "Q1 FY27", \
                f"source_period must be 'Q1 FY27'; got {claim.get('source_period')}"

    def test_eng076_target_period_extracted_when_present(self):
        """Claims with future-period language must populate target_period."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list, _segment_turns, _extract_management_claims
        text = '\n'.join(_BSE_STYLE_MULTI_MGMT.splitlines())
        registry = _parse_participant_list(text)
        turns = _segment_turns(text, registry, "datapatterns")
        claims = _extract_management_claims(turns, "Q2 FY27")
        # "invest ₹200 crore in capex over FY28" — target_period should reference FY28
        target_periods = [c.get("target_period") for c in claims if c.get("target_period")]
        assert len(target_periods) > 0, \
            f"At least one claim must have a target_period; claims={claims}"

    def test_eng076_tanla_standard_format_regression(self):
        """Standard bullet-prefixed transcript format still produces management claims."""
        from knowledge.document_processor import SpeakerRole, _parse_participant_list, _segment_turns, _extract_management_claims
        text = '\n'.join(_BASIC_TRANSCRIPT.splitlines())
        registry = _parse_participant_list(text)
        turns = _segment_turns(text, registry, "tanla")
        claims = _extract_management_claims(turns, "Q4 FY26")
        assert len(claims) > 0, \
            f"Standard transcript format must still produce claims; got 0. Registry={registry}"
        mgmt_speakers = {c["normalized_speaker"] for c in claims}
        assert any("reddy" in s.lower() or "gunupudi" in s.lower() for s in mgmt_speakers), \
            f"Management speakers must be in claims; got {mgmt_speakers}"
