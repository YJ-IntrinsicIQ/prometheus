"""Phase 7 — EarningsReleaseProcessor tests."""

from __future__ import annotations

from pathlib import Path


def _make_manifest(
    *,
    source_type_val: str = "EARNINGS_RELEASE",
    status_val: str = "IDENTIFIED",
    company: str = "demo",
    fiscal_year: str = "fy27",
    fiscal_quarter_val: str | None = "Q1",
    content_hash: str = "sha256:releaseabcdef1234",
    source_channel_val: str = "EXCHANGE_FILING",
):
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

    type_map = {
        "EARNINGS_RELEASE": SourceType.EARNINGS_RELEASE,
        "QUARTERLY_REPORT": SourceType.QUARTERLY_REPORT,
        "INVESTOR_PRESENTATION": SourceType.INVESTOR_PRESENTATION,
        "EARNINGS_CALL_TRANSCRIPT": SourceType.EARNINGS_CALL_TRANSCRIPT,
        "ANNUAL_REPORT": SourceType.ANNUAL_REPORT,
    }
    status_map = {
        "IDENTIFIED": ClassificationStatus.IDENTIFIED,
        "REVIEW_REQUIRED": ClassificationStatus.REVIEW_REQUIRED,
    }
    channel_map = {
        "EXCHANGE_FILING": SourceChannel.EXCHANGE_FILING,
        "DIRECT": SourceChannel.DIRECT,
    }
    quarter_map = {
        "Q1": FiscalQuarter.Q1,
        "Q2": FiscalQuarter.Q2,
        "Q3": FiscalQuarter.Q3,
        "Q4": FiscalQuarter.Q4,
    }

    return DocumentIntakeManifest(
        document_id=content_hash,
        file=FileIdentity(
            original_filename="opaque.pdf",
            content_hash=content_hash,
            mime_type="application/pdf",
            size_bytes=100,
            storage_path="/tmp/opaque.pdf",
        ),
        company_identity=CompanyIdentity(
            resolved_company_key=company,
            confidence=ConfidenceLevel.HIGH,
        ),
        document_identity=DocumentIdentity(
            source_type=type_map[source_type_val],
            source_channel=channel_map[source_channel_val],
            confidence=ConfidenceLevel.HIGH,
        ),
        reporting_period=ReportingPeriod(
            fiscal_year=fiscal_year,
            fiscal_quarter=quarter_map[fiscal_quarter_val] if fiscal_quarter_val else None,
            confidence=ConfidenceLevel.HIGH,
        ),
        document_dates=DocumentDates(publication_date="July 14, 2026"),
        entity_scope=EntityScope.UNKNOWN,
        language="en",
        classification=ClassificationState(status=status_map[status_val]),
        provenance=IntakeProvenance(
            ingestion_timestamp="2026-09-02T00:00:00Z",
            classifier_version="test",
            detection_method=DetectionMethod.MANUAL_COMPATIBILITY_ADAPTER,
        ),
    )


class TestEarningsReleaseClassification:
    def _classify(self, text: str):
        from knowledge.document_identifier import _classify_source_type
        return _classify_source_type(text, "opaque")[0]

    def test_earnings_release_classifies_as_release(self):
        from knowledge.document_intake import SourceType
        text = """Press Release
        Demo Limited reports Q1FY27 results.
        Q1 Revenue of INR 2,940 crore, up 11.5% YoY.
        “We expect profitable growth,” said Jane Doe, CEO, Demo Limited.
        """
        assert self._classify(text) == SourceType.EARNINGS_RELEASE

    def test_quarterly_report_not_release(self):
        from knowledge.document_intake import SourceType
        text = "Unaudited consolidated financial results for the quarter ended June 30, 2026. Limited Review Report."
        assert self._classify(text) == SourceType.QUARTERLY_REPORT

    def test_investor_presentation_not_release(self):
        from knowledge.document_intake import SourceType
        text = "Investor Presentation Q1 FY27 Results Slide 1 Business overview"
        assert self._classify(text) == SourceType.INVESTOR_PRESENTATION

    def test_transcript_not_release(self):
        from knowledge.document_intake import SourceType
        text = "Q1 FY27 Earnings Conference Call Transcript\nModerator: Welcome.\nQuestion-and-Answer Session"
        assert self._classify(text) == SourceType.EARNINGS_CALL_TRANSCRIPT

    def test_results_alone_is_insufficient(self):
        from knowledge.document_intake import SourceType
        text = "Results overview with business commentary."
        assert self._classify(text) != SourceType.EARNINGS_RELEASE


class TestEarningsReleaseSemantics:
    def test_reported_financial_result_keeps_authority_unit_period(self):
        from knowledge.document_processor import EarningsReleaseProcessor
        facts = EarningsReleaseProcessor._extract_financial_facts(
            page_texts=[(2, "Revenue at INR 29,401 million; growth of 2.9% QoQ and 11.5% YoY")],
            company="demo",
            fiscal_year="fy27",
            source_period="Q1 FY27",
            context_quarter=1,
            document_hash="sha256:abc",
        )
        assert facts[0]["metric"] == "revenue"
        assert facts[0]["value_raw"] == "29,401"
        assert facts[0]["raw_unit"] == "INR"
        assert facts[0]["raw_scale"] == "million"
        assert facts[0]["period_role"] == "CURRENT_QUARTER"
        assert facts[0]["authority"] == "COMPANY_REPORTED_RELEASE"

    def test_guidance_quote_is_management_claim_not_reported_result(self):
        from knowledge.document_processor import EarningsReleaseProcessor
        claims = EarningsReleaseProcessor._extract_management_quote_claims(
            page_texts=[(2, "“We expect growth to accelerate in FY27. We are targeting 20% EBITDA margin by Q4 FY27,” said Jane Doe, CEO, Demo Limited.")],
            company="demo",
            fiscal_year="fy27",
            source_period="Q1 FY27",
            document_hash="sha256:abc",
        )
        assert {claim["claim_type"] for claim in claims} >= {"EXPECTATION", "TARGET"}
        assert claims[-1]["target_period"].lower() == "q4 fy27"
        assert all(claim["authority"] == "MANAGEMENT_CLAIM" for claim in claims)

    def test_promotional_claim_not_objective_financial_fact(self):
        from knowledge.document_processor import EarningsReleaseProcessor
        facts = EarningsReleaseProcessor._extract_financial_facts(
            page_texts=[(2, "Our breakthrough industry-leading platform has strong momentum.")],
            company="demo",
            fiscal_year="fy27",
            source_period="Q1 FY27",
            context_quarter=1,
            document_hash="sha256:abc",
        )
        assert facts == []

    def test_source_period_distinct_from_target_period(self):
        from knowledge.document_processor import EarningsReleaseProcessor
        claims = EarningsReleaseProcessor._extract_management_quote_claims(
            page_texts=[(2, "“Our aspiration is achieving 13-15% CAGR over the next five years,” said Jane Doe, CEO, Demo Limited.")],
            company="demo",
            fiscal_year="fy27",
            source_period="Q1 FY27",
            document_hash="sha256:abc",
        )
        assert claims[0]["source_period"] == "Q1 FY27"
        assert claims[0]["target_period"] == "next five years"

    def test_processor_writes_document_scoped_common_evidence(self, tmp_path, monkeypatch):
        from knowledge.document_processor import EarningsReleaseProcessor
        source = tmp_path / "opaque.txt"
        source.write_text(
            "Press Release\n"
            "Mumbai, July 14, 2026: Demo Limited announced results for the first quarter ended June 30, 2026.\n"
            "Revenue at INR 29,401 million.\n"
            "“We expect revenue growth to accelerate in FY27 as client demand improves across our core markets,” said Jane Doe, CEO, Demo Limited.\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        result = EarningsReleaseProcessor().process(_make_manifest(), source)
        assert result.status == "SUCCESS"
        assert result.financial_fact_count >= 1
        assert result.management_claim_count >= 1
        assert result.common_evidence_count >= 2
        assert Path(result.common_evidence_path).exists()


class TestEarningsReleaseRouting:
    def test_router_available(self):
        from knowledge.document_intake import SourceType
        from knowledge.document_router import ProcessorState, RouteStatus, SourceRouter
        decision = SourceRouter().route(_make_manifest(source_type_val="EARNINGS_RELEASE"))
        assert decision.status == RouteStatus.ROUTABLE
        assert decision.processor == ProcessorState.AVAILABLE
        assert decision.route == "earnings_release"

    def test_processor_registered(self):
        from knowledge.document_processor import EarningsReleaseProcessor, _find_processor
        proc = _find_processor(_make_manifest())
        assert isinstance(proc, EarningsReleaseProcessor)

    def test_review_required_cannot_execute(self, tmp_path):
        from knowledge.document_processor import process_document
        source = tmp_path / "release.txt"
        source.write_text("Press Release\nUnknown Company reports Q1FY27 results.\n", encoding="utf-8")
        result = process_document(source, execute=True)
        assert result.status.value in {"REVIEW_REQUIRED", "UNSUPPORTED"}
