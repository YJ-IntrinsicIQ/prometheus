"""Phase 8 — ExchangeDisclosureProcessor tests.

Production proof: BLOCKED_REAL_EXCHANGE_DISCLOSURE_MISSING.
Processor is implemented and tested synthetically; NOT registered in
_PROCESSOR_REGISTRY until a real exchange-disclosure event file is available.

Closure gate requires:
  - genuine production disclosure(s) exist
  - blind identifier resolves them as EXCHANGE_DISCLOSURE
  - direct process() proof before registration

Test groups:
  ER1 (T01–T06):  Source-type classification (disclosure vs other families)
  ER2 (T07–T11):  Event-type taxonomy (ORDER_AWARD / ACQUISITION / etc.)
  ER3 (T12–T18):  Event-state semantics — the critical closure gate
  ER4 (T19–T22):  Date semantics (filing ≠ event ≠ target)
  ER5 (T23–T26):  Amount/counterparty semantics
  ER6 (T27–T30):  Management claim vs reported event
  ER7 (T31–T33):  Common evidence boundary
  ER8 (T34–T37):  Router / registry state
  ER9 (T38–T43):  Adversarial event-state tests (Parts 25–26 of mission)
  ER10(T44–T47):  Six-source regression matrix
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# ER1 — Source classification (T01–T06)
# ---------------------------------------------------------------------------

class TestDisclosureClassification:

    def _classify(self, text: str, fn: str = "doc.pdf"):
        from knowledge.document_identifier import _classify_source_type
        st, _, _ = _classify_source_type(text, fn)
        return st

    def test_t01_outcome_of_board_meeting_is_disclosure(self):
        from knowledge.document_intake import SourceType
        text = (
            "Outcome of Board Meeting\n"
            "Pursuant to Regulation 30 of SEBI (LODR) Regulations, 2015, "
            "we hereby inform that the Board of Directors approved the acquisition "
            "of ABC Pvt Ltd at a consideration of ₹200 crore."
        )
        assert self._classify(text) == SourceType.EXCHANGE_DISCLOSURE

    def test_t02_order_award_disclosure(self):
        from knowledge.document_intake import SourceType
        text = (
            "Material Event Disclosure\n"
            "The Company has received an order worth ₹500 crore "
            "from a leading infrastructure developer for embedded electronics. "
            "Pursuant to Regulation 30 SEBI LODR."
        )
        assert self._classify(text) == SourceType.EXCHANGE_DISCLOSURE

    def test_t03_annual_report_not_disclosure(self):
        from knowledge.document_intake import SourceType
        text = (
            "Annual Report FY26\n"
            "Management Discussion and Analysis\n"
            "Board of Directors Annual Report\n"
            "Financial Year 2025-26\n"
        )
        assert self._classify(text) == SourceType.ANNUAL_REPORT

    def test_t04_quarterly_report_not_disclosure(self):
        from knowledge.document_intake import SourceType
        text = (
            "Unaudited Financial Results Q1 FY27\n"
            "Quarter Ended June 30, 2026\n"
            "Limited Review Report\n"
            "Revenue: ₹12,264 Mn\n"
        )
        assert self._classify(text) == SourceType.QUARTERLY_REPORT

    def test_t05_earnings_release_not_disclosure(self):
        from knowledge.document_intake import SourceType
        text = (
            "Press Release\n"
            "Q1 FY27 Results\n"
            "Revenue for Q1 FY27 was ₹500 crore, up 15% YoY.\n"
            'CEO: "We delivered a strong quarter."\n'
        )
        result = self._classify(text)
        assert result != SourceType.EXCHANGE_DISCLOSURE

    def test_t06_bse_cover_letter_alone_not_disclosure(self):
        """Exchange filing cover letter alone must NOT force EXCHANGE_DISCLOSURE."""
        from knowledge.document_intake import SourceType
        text = (
            "To\nBSE Limited\nNational Stock Exchange Limited\n"
            "Dear Sir/Madam,\n"
            "Please find enclosed herewith the Annual Report for FY 2025-26.\n"
        )
        result = self._classify(text)
        assert result != SourceType.EXCHANGE_DISCLOSURE


# ---------------------------------------------------------------------------
# ER2 — Event-type taxonomy (T07–T11)
# ---------------------------------------------------------------------------

class TestEventTypeTaxonomy:

    def _event_type(self, text: str):
        from knowledge.document_processor import _classify_disclosure_event
        return _classify_disclosure_event(text)

    def test_t07_order_award_classified(self):
        from knowledge.document_processor import DisclosureEventType
        result = self._event_type("Company received an order worth ₹300 crore from a PSU client.")
        assert result == DisclosureEventType.ORDER_AWARD

    def test_t08_acquisition_classified(self):
        from knowledge.document_processor import DisclosureEventType
        result = self._event_type("Board approved acquisition of XYZ Technology Limited.")
        assert result == DisclosureEventType.ACQUISITION

    def test_t09_management_change_classified(self):
        from knowledge.document_processor import DisclosureEventType
        result = self._event_type("The CFO has resigned effective June 30, 2026.")
        assert result == DisclosureEventType.MANAGEMENT_CHANGE

    def test_t10_capacity_classified(self):
        from knowledge.document_processor import DisclosureEventType
        result = self._event_type("New plant commissioned at Pune facility in March 2026.")
        assert result == DisclosureEventType.CAPACITY

    def test_t11_unknown_not_forced_to_type(self):
        from knowledge.document_processor import DisclosureEventType
        result = self._event_type("The company held its Annual General Meeting yesterday.")
        assert result == DisclosureEventType.UNKNOWN


# ---------------------------------------------------------------------------
# ER3 — Event-state semantics (T12–T18) — closure-critical
# ---------------------------------------------------------------------------

class TestEventStateCritical:
    """Proposed ≠ approved ≠ completed. Missing > guessed."""

    def _status(self, text: str):
        from knowledge.document_processor import _classify_disclosure_status
        return _classify_disclosure_status(text)

    def test_t12_proposed_acquisition_is_proposed(self):
        from knowledge.document_processor import DisclosureEventStatus
        status = self._status("The company is proposing an acquisition of ABC Ltd.")
        assert status == DisclosureEventStatus.PROPOSED, (
            "PROPOSED acquisition must NOT be promoted to APPROVED or COMPLETED"
        )

    def test_t13_board_approved_acquisition_is_approved_not_completed(self):
        from knowledge.document_processor import DisclosureEventStatus
        status = self._status(
            "Board of Directors approved the acquisition of XYZ Ltd "
            "subject to regulatory approvals and shareholder consent."
        )
        assert status == DisclosureEventStatus.APPROVED, (
            "Board approval ≠ acquisition closure; status must be APPROVED not COMPLETED"
        )

    def test_t14_plant_commissioned_is_commissioned_not_operational(self):
        from knowledge.document_processor import DisclosureEventStatus
        status = self._status("The manufacturing plant was commissioned on March 31, 2026.")
        assert status == DisclosureEventStatus.COMMISSIONED, (
            "COMMISSIONED ≠ OPERATIONAL; full utilization not proven by this disclosure alone"
        )

    def test_t15_under_construction_is_not_commissioned(self):
        from knowledge.document_processor import DisclosureEventStatus
        status = self._status("Construction of the new facility is underway.")
        assert status == DisclosureEventStatus.UNDER_CONSTRUCTION

    def test_t16_cancelled_project_is_cancelled(self):
        from knowledge.document_processor import DisclosureEventStatus
        status = self._status("The project has been cancelled due to unfavourable market conditions.")
        assert status == DisclosureEventStatus.CANCELLED

    def test_t17_delayed_project_is_delayed(self):
        from knowledge.document_processor import DisclosureEventStatus
        status = self._status("Execution has been delayed by six months due to supply chain issues.")
        assert status == DisclosureEventStatus.DELAYED

    def test_t18_vague_statement_stays_unknown(self):
        from knowledge.document_processor import DisclosureEventStatus
        status = self._status("The Company continues to evaluate strategic opportunities.")
        assert status == DisclosureEventStatus.UNKNOWN, (
            "Ambiguous strategic language must never infer a concrete event state"
        )


# ---------------------------------------------------------------------------
# ER4 — Date semantics (T19–T22)
# ---------------------------------------------------------------------------

class TestDateSemantics:

    def test_t19_event_date_extracted_separately(self):
        from knowledge.document_processor import _extract_disclosure_dates
        text = "Agreement signed on 15 April 2026 between the parties."
        dates = _extract_disclosure_dates(text)
        assert dates["event_date"] is not None, "Explicit event date must be extracted"

    def test_t20_target_date_extracted_from_second_match(self):
        from knowledge.document_processor import _extract_disclosure_dates
        text = (
            "The agreement was signed on 01/04/2026 "
            "and is expected to be effective from 01/07/2026."
        )
        dates = _extract_disclosure_dates(text)
        assert dates["event_date"] is not None
        assert dates["target_date"] is not None
        assert dates["event_date"] != dates["target_date"], (
            "Event date and target date must be stored separately"
        )

    def test_t21_no_date_in_text_gives_none(self):
        from knowledge.document_processor import _extract_disclosure_dates
        dates = _extract_disclosure_dates("Order received from government agency.")
        assert dates["event_date"] is None, "Missing date must remain None, not fabricated"

    def test_t22_filing_date_comes_from_manifest_not_text(self):
        """The processor design separates filing_date (manifest) from event_date (text)."""
        from knowledge.document_processor import _extract_disclosure_dates
        dates = _extract_disclosure_dates("Company received an order from a PSU.")
        assert "filing_date" not in dates, (
            "Filing date must not be conflated with event date in text extraction"
        )


# ---------------------------------------------------------------------------
# ER5 — Amount / counterparty semantics (T23–T26)
# ---------------------------------------------------------------------------

class TestAmountCounterpartySemantics:

    def test_t23_explicit_amount_extracted(self):
        from knowledge.document_processor import _extract_disclosure_amount
        amount = _extract_disclosure_amount("Order worth ₹500 crore received from ABC Corp.")
        assert amount is not None
        assert "500" in amount

    def test_t24_vague_amount_not_invented(self):
        from knowledge.document_processor import _extract_disclosure_amount
        amount = _extract_disclosure_amount("The company received a large order from a PSU.")
        assert amount is None, (
            "Vague 'large order' must never generate a numeric amount"
        )

    def test_t25_usd_amount_extracted(self):
        from knowledge.document_processor import _extract_disclosure_amount
        amount = _extract_disclosure_amount("Contract valued at USD 25 million with global client.")
        assert amount is not None

    def test_t26_unnamed_counterparty_stays_none(self):
        """Counterparty field stays None when not explicitly named."""
        from knowledge.document_processor import ExchangeDisclosureProcessor, _classify_disclosure_event, _classify_disclosure_status, _extract_disclosure_amount, _extract_disclosure_dates, DisclosureEventType, DisclosureEventStatus
        text = "Company received an order from a leading infrastructure developer."
        event_type = _classify_disclosure_event(text)
        event_status = _classify_disclosure_status(text)
        amount = _extract_disclosure_amount(text)
        dates = _extract_disclosure_dates(text)
        records = ExchangeDisclosureProcessor._extract_event_records(
            text, event_type, event_status, amount, dates,
            "testco", "fy26", "sha256:abc123", "test.pdf",
        )
        for r in records:
            assert r["counterparty"] is None, (
                "Unnamed counterparty 'leading developer' must not be inferred"
            )


# ---------------------------------------------------------------------------
# ER6 — Management claim vs reported event (T27–T30)
# ---------------------------------------------------------------------------

class TestManagementClaimVsEvent:

    def test_t27_factual_event_is_direct(self):
        from knowledge.document_processor import ExchangeDisclosureProcessor, _classify_disclosure_event, _classify_disclosure_status, _extract_disclosure_amount, _extract_disclosure_dates
        text = "The Company received an order worth ₹300 crore from ABC Corp."
        event_type = _classify_disclosure_event(text)
        event_status = _classify_disclosure_status(text)
        records = ExchangeDisclosureProcessor._extract_event_records(
            text, event_type, event_status,
            _extract_disclosure_amount(text), _extract_disclosure_dates(text),
            "testco", "fy27", "sha256:abc", "test.pdf",
        )
        assert any(r["direct"] for r in records), (
            "Factual event sentence must be marked direct=True"
        )

    def test_t28_hedged_sentence_is_not_direct(self):
        from knowledge.document_processor import ExchangeDisclosureProcessor, _classify_disclosure_event, _classify_disclosure_status, _extract_disclosure_amount, _extract_disclosure_dates
        text = "We expect the plant to be commissioned by Q3 FY27, subject to approvals."
        event_type = _classify_disclosure_event(text)
        event_status = _classify_disclosure_status(text)
        records = ExchangeDisclosureProcessor._extract_event_records(
            text, event_type, event_status,
            _extract_disclosure_amount(text), _extract_disclosure_dates(text),
            "testco", "fy27", "sha256:abc", "test.pdf",
        )
        assert any(not r["direct"] for r in records), (
            "Hedged/forward-looking sentence must be marked direct=False"
        )

    def test_t29_promotional_language_becomes_claim_not_event_fact(self):
        from knowledge.document_processor import _classify_claim_type, ManagementClaimType
        text = "We aim to be the market leader in embedded electronics."
        claim_type = _classify_claim_type(text)
        assert claim_type != ManagementClaimType.FACTUAL_STATEMENT, (
            "Promotional/aspiration language must not be classified as objective event fact"
        )

    def test_t30_authority_is_exchange_disclosure_not_audited(self):
        from knowledge.document_processor import ExchangeDisclosureProcessor, _classify_disclosure_event, _classify_disclosure_status, _extract_disclosure_amount, _extract_disclosure_dates
        text = "Order received worth ₹500 crore from infrastructure client."
        event_type = _classify_disclosure_event(text)
        event_status = _classify_disclosure_status(text)
        records = ExchangeDisclosureProcessor._extract_event_records(
            text, event_type, event_status,
            _extract_disclosure_amount(text), _extract_disclosure_dates(text),
            "testco", "fy27", "sha256:abc", "test.pdf",
        )
        for r in records:
            assert r["authority"] == "EXCHANGE_DISCLOSURE", (
                "Disclosure evidence must carry EXCHANGE_DISCLOSURE authority, not AUDITED"
            )


# ---------------------------------------------------------------------------
# ER7 — Common evidence boundary (T31–T33)
# ---------------------------------------------------------------------------

class TestCommonEvidenceBoundary:

    def test_t31_result_dataclass_has_required_fields(self):
        from knowledge.document_processor import ExchangeDisclosureResult
        r = ExchangeDisclosureResult(
            company="testco",
            fiscal_year="fy27",
            source_file="/path/doc.pdf",
            storage_path="companies/testco/fy27/exchange_disclosures/abc123/",
        )
        assert r.company == "testco"
        assert r.status == "SUCCESS"
        assert r.event_count == 0

    def test_t32_result_to_dict_json_serializable(self):
        import json
        from knowledge.document_processor import ExchangeDisclosureResult
        r = ExchangeDisclosureResult(
            company="testco",
            fiscal_year="fy27",
            source_file="/path/doc.pdf",
            storage_path="companies/testco/fy27/exchange_disclosures/abc123/",
            event_count=3,
            event_types=["ORDER_AWARD"],
            claim_count=2,
        )
        d = r.to_dict()
        assert json.dumps(d)
        assert d["event_types"] == ["ORDER_AWARD"]

    def test_t33_fiscal_year_optional_for_event_disclosures(self):
        """ExchangeDisclosureResult must accept fiscal_year=None for event-centric files."""
        from knowledge.document_processor import ExchangeDisclosureResult
        r = ExchangeDisclosureResult(
            company="testco",
            fiscal_year=None,
            source_file="/path/doc.pdf",
            storage_path="companies/testco/undated/exchange_disclosures/abc123/",
        )
        assert r.fiscal_year is None


# ---------------------------------------------------------------------------
# ER8 — Router / registry state (T34–T37)
# ---------------------------------------------------------------------------

class TestRouterRegistryState:

    def test_t34_exchange_disclosure_router_available(self):
        from knowledge.document_router import _SOURCE_TYPE_PROCESSOR_MAP, ProcessorState
        from knowledge.document_intake import SourceType
        state = _SOURCE_TYPE_PROCESSOR_MAP.get(SourceType.EXCHANGE_DISCLOSURE)
        assert state == ProcessorState.AVAILABLE, (
            "ExchangeDisclosureProcessor must be AVAILABLE after Phase 8.1 production proof"
        )

    def test_t35_processor_in_registry(self):
        from knowledge.document_processor import _PROCESSOR_REGISTRY, ExchangeDisclosureProcessor
        registry_types = [type(p) for p in _PROCESSOR_REGISTRY]
        assert ExchangeDisclosureProcessor in registry_types, (
            "ExchangeDisclosureProcessor must be registered after Phase 8.1 production proof"
        )

    def test_t36_can_process_false_for_annual_report(self):
        from knowledge.document_processor import ExchangeDisclosureProcessor
        proc = ExchangeDisclosureProcessor()
        # Build a minimal ANNUAL_REPORT manifest
        manifest = _make_minimal_manifest(source_type_val="ANNUAL_REPORT")
        assert not proc.can_process(manifest)

    def test_t37_can_process_true_for_exchange_disclosure_identified(self):
        from knowledge.document_processor import ExchangeDisclosureProcessor
        proc = ExchangeDisclosureProcessor()
        manifest = _make_minimal_manifest(source_type_val="EXCHANGE_DISCLOSURE")
        assert proc.can_process(manifest)


# ---------------------------------------------------------------------------
# ER9 — Adversarial event-state tests (T38–T43)
# ---------------------------------------------------------------------------

class TestAdversarialEventState:
    """Mission Part 25: 16 adversarial tests. Grouped here by semantic category."""

    def _status(self, text: str):
        from knowledge.document_processor import _classify_disclosure_status
        return _classify_disclosure_status(text)

    def _event(self, text: str):
        from knowledge.document_processor import _classify_disclosure_event
        return _classify_disclosure_event(text)

    def test_t38_proposed_acquisition_ne_completed(self):
        from knowledge.document_processor import DisclosureEventStatus
        status = self._status("Company is proposing acquisition of a digital business.")
        assert status == DisclosureEventStatus.PROPOSED
        assert status != DisclosureEventStatus.COMPLETED

    def test_t39_board_approved_acquisition_ne_closed(self):
        from knowledge.document_processor import DisclosureEventStatus
        status = self._status("Board approved the acquisition subject to regulatory approvals.")
        assert status == DisclosureEventStatus.APPROVED
        assert status != DisclosureEventStatus.COMPLETED

    def test_t40_order_received_ne_revenue_recognized(self):
        """Order receipt does not imply revenue. Event type must be ORDER_AWARD, not financial result."""
        from knowledge.document_processor import DisclosureEventType, _extract_disclosure_amount
        text = "The Company received an order worth ₹300 crore from ABC Corp."
        assert self._event(text) == DisclosureEventType.ORDER_AWARD
        amount = _extract_disclosure_amount(text)
        assert amount is not None
        # The amount is the contract value, NOT revenue; test documents event semantics only.
        # The result record authority = EXCHANGE_DISCLOSURE, not AUDITED or REVENUE.

    def test_t41_plant_commissioned_ne_fully_operational_economics(self):
        from knowledge.document_processor import DisclosureEventStatus
        status = self._status("The plant was commissioned on April 1, 2026.")
        assert status == DisclosureEventStatus.COMMISSIONED
        assert status != DisclosureEventStatus.OPERATIONAL, (
            "COMMISSIONED ≠ OPERATIONAL; utilization economics not established by commissioning"
        )

    def test_t42_installed_capacity_ne_production_output(self):
        from knowledge.document_processor import DisclosureEventStatus
        status = self._status("Capacity of 50,000 MT installed at the Pune facility.")
        assert status == DisclosureEventStatus.INSTALLED
        assert status != DisclosureEventStatus.OPERATIONAL

    def test_t43_regulatory_application_ne_regulatory_approval(self):
        from knowledge.document_processor import DisclosureEventStatus
        approved = self._status("Received regulatory approval from USFDA.")
        applied = self._status("Filed application for regulatory clearance with USFDA.")
        assert approved == DisclosureEventStatus.APPROVED
        assert applied != DisclosureEventStatus.APPROVED, (
            "Regulatory application ≠ regulatory approval"
        )


# ---------------------------------------------------------------------------
# ER10 — Six-source regression matrix (T44–T47)
# ---------------------------------------------------------------------------

class TestSixSourceRegressions:
    """All six source families must remain distinct — no cross-routing."""

    def _identify(self, path_str: str):
        from pathlib import Path
        from knowledge.document_identifier import identify_document
        p = Path(path_str)
        if not p.exists():
            pytest.skip(f"Test document not available: {path_str}")
        return identify_document(p)

    def test_t44_tanla_annual_still_annual(self):
        from knowledge.document_intake import SourceType
        result = self._identify("data/Processed/tanla/fy26/annual_report/tanla_fy26.pdf")
        assert result.document_identity.source_type == SourceType.ANNUAL_REPORT

    def test_t45_tanla_quarterly_still_quarterly(self):
        from knowledge.document_intake import SourceType
        result = self._identify("data/Processed/tanla/q1 fy27/quarterly_report/342tsgdh266.pdf")
        assert result.document_identity.source_type == SourceType.QUARTERLY_REPORT

    def test_t46_tanla_presentation_still_presentation(self):
        from knowledge.document_intake import SourceType
        result = self._identify("data/Processed/tanla/q4 fy26/investor_presentation/3e52b313-f8d6-4893-b039-88b5b8f070f6.pdf")
        assert result.document_identity.source_type == SourceType.INVESTOR_PRESENTATION

    def test_t47_tanla_transcript_still_transcript(self):
        from knowledge.document_intake import SourceType
        result = self._identify("data/Processed/tanla/q4 fy26/earnings_call_transcript/TanlaPlatforms_01052026185354_Q4EarningCallTranscript-SEfinal.pdf")
        assert result.document_identity.source_type == SourceType.EARNINGS_CALL_TRANSCRIPT

    def test_t48_ltts_release_still_release(self):
        from knowledge.document_intake import SourceType
        result = self._identify("data/Processed/ltts/q1 fy27/earnings_release/6965ca6d-58bd-4c7a-a6ac-901f16d7f058.pdf")
        assert result.document_identity.source_type == SourceType.EARNINGS_RELEASE

    def test_t49_ujjivan_annual_still_annual(self):
        from knowledge.document_intake import SourceType
        result = self._identify("companies/ujjivan/fy25/raw/ujjivan_fy25.pdf")
        assert result.document_identity.source_type == SourceType.ANNUAL_REPORT


# ---------------------------------------------------------------------------
# Minimal manifest helper
# ---------------------------------------------------------------------------

def _make_minimal_manifest(
    *,
    source_type_val: str = "EXCHANGE_DISCLOSURE",
    status_val: str = "IDENTIFIED",
    company: str = "testco",
    fiscal_year: str = "fy27",
):
    from knowledge.document_intake import (
        ClassificationState,
        ClassificationStatus,
        CompanyIdentity,
        ConfidenceLevel,
        DocumentIdentity,
        DocumentIntakeManifest,
        FileIdentity,
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
        "EXCHANGE_DISCLOSURE": SourceType.EXCHANGE_DISCLOSURE,
        "ANNUAL_REPORT": SourceType.ANNUAL_REPORT,
        "QUARTERLY_REPORT": SourceType.QUARTERLY_REPORT,
        "EARNINGS_RELEASE": SourceType.EARNINGS_RELEASE,
    }

    return DocumentIntakeManifest(
        document_id="sha256:test1234",
        file=FileIdentity(
            original_filename="test_disclosure.pdf",
            content_hash="sha256:test1234",
            mime_type="application/pdf",
            size_bytes=50_000,
            storage_path="test_disclosure.pdf",
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
            source_channel=SourceChannel.EXCHANGE_FILING,
            document_subtype=source_type_val.lower(),
            confidence=ConfidenceLevel.HIGH,
            evidence=[],
        ),
        reporting_period=ReportingPeriod(
            fiscal_year=fiscal_year,
            fiscal_quarter=None,
            confidence=ConfidenceLevel.HIGH,
            evidence=[],
        ),
        document_dates=None,
        entity_scope=None,
        language="en",
        classification=ClassificationState(
            overall_confidence=ConfidenceLevel.HIGH,
            status=status_map[status_val],
            unresolved_fields=[],
            warnings=[],
        ),
        provenance=IntakeProvenance(
            ingestion_timestamp="2026-09-02T00:00:00+00:00",
        ),
    )
