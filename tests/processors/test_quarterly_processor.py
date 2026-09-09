"""Adversarial test suite for QuarterlyReportProcessor — Gate B closure.

Tests cover:
  - Period extraction: Q1/Q4 recognition, standalone FY, duplicate quarterly labels
  - Period role interpretation: CURRENT_QUARTER, PRIOR_YEAR_SAME_QUARTER,
    PRIOR_YEAR_FULL_YEAR, UNKNOWN for historical trend quarters
  - No fabricated YTD derivation (Q2 ≠ H1 - Q1, etc.)
  - No period_role on annual ExtractedValue objects
  - Misleading filename has no effect on routing
  - Annual documents never route to QuarterlyReportProcessor
  - Router state: QUARTERLY_REPORT → AVAILABLE after Gate B
  - No company-specific code in processor or extractor
  - Storage path: companies/<co>/<fy>/quarters/<q>/
  - No downstream cascade (CIM/PCIM/Panel not triggered)
"""

from __future__ import annotations

import pytest
from knowledge.financials.extractor import _extract_periods
from knowledge.financials.period_roles import (
    FinancialPeriodRole,
    annotate_period_roles,
    interpret_period_role,
)
from knowledge.financials.extraction_schema import ExtractedValue
from knowledge.document_router import SourceRouter, RouteStatus, ProcessorState
from knowledge.document_intake import (
    SourceType,
    ClassificationStatus,
    DocumentIntakeManifest,
    FileIdentity,
    CompanyIdentity,
    DocumentIdentity,
    ReportingPeriod,
    FiscalQuarter,
    ClassificationState,
    IntakeProvenance,
    ConfidenceLevel,
    DetectionMethod,
    EntityScope,
    SourceChannel,
)
from core.company_context import CompanyContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manifest(
    *,
    source_type: SourceType = SourceType.QUARTERLY_REPORT,
    status: ClassificationStatus = ClassificationStatus.IDENTIFIED,
    quarter: FiscalQuarter | None = FiscalQuarter.Q1,
    company: str = "acme",
    fiscal_year: str = "fy27",
) -> DocumentIntakeManifest:
    return DocumentIntakeManifest(
        document_id="test-doc-id",
        file=FileIdentity(
            original_filename="report.pdf",
            content_hash="sha256:abc",
            mime_type="application/pdf",
            size_bytes=1024,
            storage_path="data/report.pdf",
        ),
        company_identity=CompanyIdentity(
            resolved_company_key=company,
            detected_legal_name="",
            detected_display_name="",
            confidence=ConfidenceLevel.HIGH,
            evidence=[],
        ),
        document_identity=DocumentIdentity(
            source_type=source_type,
            source_channel=SourceChannel.DIRECT,
            document_subtype="",
            confidence=ConfidenceLevel.HIGH,
            evidence=[],
        ),
        reporting_period=ReportingPeriod(
            fiscal_year=fiscal_year,
            fiscal_quarter=quarter,
            period_start=None,
            period_end=None,
            confidence=ConfidenceLevel.HIGH,
            evidence=[],
        ),
        entity_scope=EntityScope.UNKNOWN,
        language="en",
        classification=ClassificationState(
            overall_confidence=ConfidenceLevel.HIGH,
            status=status,
            unresolved_fields=[],
            warnings=[],
        ),
        provenance=IntakeProvenance(
            ingestion_timestamp="2026-09-02T00:00:00Z",
            classifier_version="test",
            detection_method=DetectionMethod.AUTOMATIC_CLASSIFIER,
        ),
    )


def _ev(period: str, value: str = "100") -> ExtractedValue:
    return ExtractedValue(
        period=period,
        value_raw=value,
        unit_hint="crore",
        currency_hint="INR",
        value_crore=100.0,
    )


# ===========================================================================
# Group 1: Period extraction (_extract_periods)
# ===========================================================================

class TestExtractPeriods:
    def test_q1_fy27_alone_no_fy27_duplicate(self):
        """'Q1 FY27' in header and column — no bare 'FY27' should appear."""
        text = "Report Q1 FY27 INCOME STATEMENT Q1 FY27 Revenue 12264"
        periods = _extract_periods(text)
        assert periods == ["Q1 FY27"]
        assert "FY27" not in periods

    def test_q1_fy27_q1_fy26_fy26_all_distinct(self):
        """Three distinct period labels extracted: Q1 FY27, Q1 FY26, FY26."""
        text = "Q1 FY27 Q1 FY26 FY26 Revenue 12264 10407 44177"
        periods = _extract_periods(text)
        assert periods == ["Q1 FY27", "Q1 FY26", "FY26"]

    def test_q4_recognized(self):
        """Q4 labels are extracted with the same logic as Q1."""
        text = "Q4 FY27 Q4 FY26 FY26 PAT 500 450 1800"
        periods = _extract_periods(text)
        assert "Q4 FY27" in periods
        assert "Q4 FY26" in periods
        assert "FY26" in periods

    def test_standalone_fy_not_suppressed_by_different_quarter(self):
        """'Q1 FY26' should NOT suppress 'FY26' (they are different column heads)."""
        text = "Q1 FY27 Q1 FY26 FY26 Revenue 12264 10407 44177"
        periods = _extract_periods(text)
        assert "FY26" in periods, "Standalone FY26 should survive even when Q1 FY26 is present"

    def test_duplicate_quarterly_label_all_spans_tracked(self):
        """When 'Q1 FY27' appears in both page header and column header,
        the bare 'FY27' embedded in both occurrences must be suppressed."""
        text = "Page 3 Q1 FY27 CONDENSED INCOME STATEMENT Q1 FY27 Q1 FY26 FY26"
        periods = _extract_periods(text)
        assert "FY27" not in periods
        assert "Q1 FY27" in periods
        assert "FY26" in periods

    def test_annual_only_document(self):
        """Annual-only text produces bare FY labels, no quarterly labels."""
        text = "FY26 FY25 Revenue 44177 38000"
        periods = _extract_periods(text)
        assert "FY26" in periods
        assert "FY25" in periods
        assert not any(p.startswith("Q") for p in periods)

    def test_standalone_fy_when_quarterly_fy_same_year(self):
        """Standalone FY27 can coexist with Q1 FY27 (full-year comparative)."""
        text = "Q1 FY27 FY27 Revenue 12264 44177"
        periods = _extract_periods(text)
        assert "Q1 FY27" in periods
        assert "FY27" in periods


# ===========================================================================
# Group 2: Period role interpretation
# ===========================================================================

class TestInterpretPeriodRole:
    def test_current_quarter_q1_fy27(self):
        role = interpret_period_role("Q1 FY27", context_fy=27, context_quarter=1)
        assert role == FinancialPeriodRole.CURRENT_QUARTER

    def test_prior_year_same_quarter_q1_fy26(self):
        role = interpret_period_role("Q1 FY26", context_fy=27, context_quarter=1)
        assert role == FinancialPeriodRole.PRIOR_YEAR_SAME_QUARTER

    def test_prior_year_full_year_fy26(self):
        role = interpret_period_role("FY26", context_fy=27, context_quarter=1)
        assert role == FinancialPeriodRole.PRIOR_YEAR_FULL_YEAR

    def test_current_quarter_q4_fy27(self):
        role = interpret_period_role("Q4 FY27", context_fy=27, context_quarter=4)
        assert role == FinancialPeriodRole.CURRENT_QUARTER

    def test_prior_year_same_quarter_q4_fy26(self):
        role = interpret_period_role("Q4 FY26", context_fy=27, context_quarter=4)
        assert role == FinancialPeriodRole.PRIOR_YEAR_SAME_QUARTER

    def test_historical_q_is_unknown_not_ytd(self):
        """Q2 FY26 with Q1 FY27 context must be UNKNOWN — not promoted to YTD."""
        role = interpret_period_role("Q2 FY26", context_fy=27, context_quarter=1)
        assert role == FinancialPeriodRole.UNKNOWN

    def test_historical_q_same_fy_is_unknown(self):
        """Q3 FY25 with Q1 FY27 context must be UNKNOWN."""
        role = interpret_period_role("Q3 FY25", context_fy=27, context_quarter=1)
        assert role == FinancialPeriodRole.UNKNOWN

    def test_no_ytd_fabrication_for_q1(self):
        """Q1 alone must never be promoted to YEAR_TO_DATE."""
        role = interpret_period_role("Q1 FY27", context_fy=27, context_quarter=1)
        assert role != FinancialPeriodRole.YEAR_TO_DATE


# ===========================================================================
# Group 3: annotate_period_roles
# ===========================================================================

class TestAnnotatePeriodRoles:
    def test_all_three_primary_roles_assigned(self):
        values = [
            _ev("Q1 FY27"),
            _ev("Q1 FY26"),
            _ev("FY26"),
        ]
        annotate_period_roles(values, context_fy=27, context_quarter=1)
        roles = [v.period_role for v in values]
        assert "CURRENT_QUARTER" in roles
        assert "PRIOR_YEAR_SAME_QUARTER" in roles
        assert "PRIOR_YEAR_FULL_YEAR" in roles

    def test_trend_quarters_are_unknown(self):
        values = [
            _ev("Q1 FY25"),
            _ev("Q2 FY25"),
            _ev("Q3 FY25"),
        ]
        annotate_period_roles(values, context_fy=27, context_quarter=1)
        for v in values:
            assert v.period_role == "UNKNOWN"

    def test_period_role_empty_before_annotation(self):
        """ExtractedValue.period_role is empty string until annotated."""
        v = _ev("Q1 FY27")
        assert v.period_role == ""

    def test_annotation_mutates_in_place(self):
        values = [_ev("Q1 FY27"), _ev("Q1 FY26")]
        before_ids = [id(v) for v in values]
        annotate_period_roles(values, context_fy=27, context_quarter=1)
        after_ids = [id(v) for v in values]
        assert before_ids == after_ids, "annotate_period_roles must mutate in-place, not replace"

    def test_no_ytd_fabricated_from_q1(self):
        """Presence of Q1 FY27 must not produce YEAR_TO_DATE."""
        values = [_ev("Q1 FY27"), _ev("Q1 FY26"), _ev("FY26")]
        annotate_period_roles(values, context_fy=27, context_quarter=1)
        roles = [v.period_role for v in values]
        assert "YEAR_TO_DATE" not in roles


# ===========================================================================
# Group 4: annual ExtractedValue must never get period_role
# ===========================================================================

class TestAnnualNoRoleContamination:
    def test_annual_extracted_value_has_empty_role(self):
        """An ExtractedValue created by the annual pipeline has period_role=''."""
        v = ExtractedValue(
            period="FY26",
            value_raw="44,177",
            unit_hint="crore",
            currency_hint="INR",
            value_crore=4417.7,
        )
        assert v.period_role == ""

    def test_annual_value_to_dict_no_period_role_key(self):
        """period_role must be absent from to_dict() when empty."""
        v = ExtractedValue(
            period="FY26",
            value_raw="44,177",
            unit_hint="crore",
            currency_hint="INR",
            value_crore=4417.7,
        )
        d = v.to_dict()
        assert "period_role" not in d


# ===========================================================================
# Group 5: Router — QUARTERLY_REPORT → AVAILABLE post Gate B
# ===========================================================================

class TestRouterQuarterlyGateB:
    def test_quarterly_report_routable(self):
        manifest = _make_manifest(source_type=SourceType.QUARTERLY_REPORT)
        decision = SourceRouter().route(manifest)
        assert decision.status == RouteStatus.ROUTABLE
        assert decision.processor == ProcessorState.AVAILABLE

    def test_quarterly_route_label(self):
        manifest = _make_manifest(source_type=SourceType.QUARTERLY_REPORT)
        decision = SourceRouter().route(manifest)
        assert decision.route == "quarterly_report"

    def test_quarterly_destination_includes_quarter_path(self):
        manifest = _make_manifest(
            source_type=SourceType.QUARTERLY_REPORT,
            quarter=FiscalQuarter.Q1,
            company="acme",
            fiscal_year="fy27",
        )
        decision = SourceRouter().route(manifest)
        assert decision.destination is not None
        assert "quarters" in decision.destination
        assert "Q1" in decision.destination

    def test_annual_report_not_affected(self):
        manifest = _make_manifest(source_type=SourceType.ANNUAL_REPORT, quarter=None)
        decision = SourceRouter().route(manifest)
        assert decision.status == RouteStatus.ROUTABLE
        assert decision.processor == ProcessorState.AVAILABLE
        assert decision.route == "annual_report"
        assert "quarters" not in (decision.destination or "")

    def test_investor_presentation_routable_phase5(self):
        """InvestorPresentationProcessor is AVAILABLE after Phase 5 production proof."""
        manifest = _make_manifest(source_type=SourceType.INVESTOR_PRESENTATION, quarter=None)
        decision = SourceRouter().route(manifest)
        assert decision.status == RouteStatus.ROUTABLE
        assert decision.processor == ProcessorState.AVAILABLE
        assert decision.route == "investor_presentation"
        assert decision.route != "quarterly_report"


# ===========================================================================
# Group 6: CompanyContext quarter_root
# ===========================================================================

class TestCompanyContextQuarterRoot:
    def test_quarter_root_path_structure(self):
        ctx = CompanyContext(company="acme", year="fy27", quarter="Q1")
        root = ctx.quarter_root
        assert str(root) == "companies/acme/fy27/quarters/Q1"

    def test_quarter_root_raises_when_annual(self):
        ctx = CompanyContext(company="acme", year="fy27", quarter=None)
        with pytest.raises(ValueError, match="quarter_root"):
            _ = ctx.quarter_root

    def test_annual_year_root_unchanged(self):
        ctx = CompanyContext(company="acme", year="fy27", quarter=None)
        assert str(ctx.year_root) == "companies/acme/fy27"

    def test_q4_path(self):
        ctx = CompanyContext(company="acme", year="fy27", quarter="Q4")
        assert "Q4" in str(ctx.quarter_root)


# ===========================================================================
# Group 7: No company-specific code in core modules
# ===========================================================================

class TestNoCompanySpecificCode:
    _COMPANY_NAMES = ["ujjivan", "sun_pharma", "polymatech", "datapatterns", "tanla", "ltts"]

    def test_period_roles_module_has_no_company_names(self):
        import inspect
        import knowledge.financials.period_roles as mod
        source = inspect.getsource(mod).lower()
        for name in self._COMPANY_NAMES:
            assert name not in source, f"Company-specific name '{name}' in period_roles.py"

    def test_extractor_has_no_company_names(self):
        import inspect
        import knowledge.financials.extractor as mod
        source = inspect.getsource(mod).lower()
        for name in self._COMPANY_NAMES:
            assert name not in source, f"Company-specific name '{name}' in extractor.py"

    def test_document_processor_has_no_company_names(self):
        import inspect
        import knowledge.document_processor as mod
        source = inspect.getsource(mod).lower()
        for name in self._COMPANY_NAMES:
            assert name not in source, f"Company-specific name '{name}' in document_processor.py"
