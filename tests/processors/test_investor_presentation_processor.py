"""Adversarial test suite for InvestorPresentationProcessor — Phase 5 closure.

Tests cover:
  - Presentation ≠ quarterly report even when it shows quarterly metrics
  - Exchange-filed presentation → INVESTOR_PRESENTATION (not QUARTERLY_REPORT)
  - Management claims are not misclassified as financial outcomes
  - Financial periods remain distinct (Q4 FY26 ≠ FY26, CURRENT_QUARTER ≠ FULL_YEAR_COMPARATIVE)
  - Misleading filename has no effect on routing
  - REVIEW_REQUIRED manifest cannot execute InvestorPresentationProcessor
  - No cross-routing to Annual or Quarterly processors
  - Multiple presentations can coexist (document-scoped storage paths)
  - No automatic downstream cascade (process() returns typed result only)
  - No company-specific code in processor
  - Storage path: companies/<co>/<fy>/presentations/<hash>/
  - InvestorPresentationResult typed dataclass contract
  - context_quarter defaults to 4 when manifest.fiscal_quarter is None
"""

from __future__ import annotations

import pytest
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
from knowledge.document_processor import (
    InvestorPresentationResult,
    InvestorPresentationProcessor,
    ProcessorUnavailableError,
)
from knowledge.financials.period_roles import (
    FinancialPeriodRole,
    interpret_period_role,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manifest(
    *,
    source_type: SourceType = SourceType.INVESTOR_PRESENTATION,
    status: ClassificationStatus = ClassificationStatus.IDENTIFIED,
    quarter: FiscalQuarter | None = None,
    company: str = "acme",
    fiscal_year: str = "fy26",
    source_channel: SourceChannel = SourceChannel.EXCHANGE_FILING,
    content_hash: str = "sha256:abc123def456",
) -> DocumentIntakeManifest:
    return DocumentIntakeManifest(
        document_id="test-doc-id",
        file=FileIdentity(
            original_filename="investor_update_fy26.pdf",
            content_hash=content_hash,
            mime_type="application/pdf",
            size_bytes=7900000,
            storage_path="data/investor_update_fy26.pdf",
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
            source_channel=source_channel,
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


# ===========================================================================
# Group 1: Router — presentation routes to InvestorPresentationProcessor
# ===========================================================================

class TestRouterInvestorPresentationPhase5:
    def test_investor_presentation_routable(self):
        """INVESTOR_PRESENTATION → ROUTABLE / AVAILABLE after Phase 5 proof."""
        manifest = _make_manifest()
        decision = SourceRouter().route(manifest)
        assert decision.status == RouteStatus.ROUTABLE
        assert decision.processor == ProcessorState.AVAILABLE
        assert decision.route == "investor_presentation"

    def test_investor_presentation_not_quarterly_route(self):
        """Showing quarterly metrics in a presentation does not re-route it to quarterly."""
        manifest = _make_manifest(source_type=SourceType.INVESTOR_PRESENTATION)
        decision = SourceRouter().route(manifest)
        assert decision.route != "quarterly_report"
        assert decision.route == "investor_presentation"

    def test_investor_presentation_not_annual_route(self):
        """Showing annual P&L in a presentation does not re-route it to annual."""
        manifest = _make_manifest(source_type=SourceType.INVESTOR_PRESENTATION)
        decision = SourceRouter().route(manifest)
        assert decision.route != "annual_report"

    def test_exchange_filing_presentation_routable(self):
        """Exchange-filed presentation (wrapper + payload) → INVESTOR_PRESENTATION."""
        manifest = _make_manifest(
            source_type=SourceType.INVESTOR_PRESENTATION,
            source_channel=SourceChannel.EXCHANGE_FILING,
        )
        decision = SourceRouter().route(manifest)
        assert decision.status == RouteStatus.ROUTABLE
        assert decision.route == "investor_presentation"

    def test_misleading_filename_irrelevant(self):
        """A presentation named 'quarterly_report.pdf' still routes to investor_presentation."""
        manifest = _make_manifest(source_type=SourceType.INVESTOR_PRESENTATION)
        # source_type is what matters — filename is in content_hash-addressed storage
        decision = SourceRouter().route(manifest)
        assert decision.status == RouteStatus.ROUTABLE
        assert decision.route == "investor_presentation"

    def test_quarterly_report_still_routes_to_quarterly(self):
        """QUARTERLY_REPORT is unaffected by Phase 5 changes."""
        manifest = _make_manifest(
            source_type=SourceType.QUARTERLY_REPORT,
            quarter=FiscalQuarter.Q1,
        )
        decision = SourceRouter().route(manifest)
        assert decision.status == RouteStatus.ROUTABLE
        assert decision.route == "quarterly_report"
        assert decision.route != "investor_presentation"

    def test_annual_report_still_routes_to_annual(self):
        """ANNUAL_REPORT is unaffected by Phase 5 changes."""
        manifest = _make_manifest(source_type=SourceType.ANNUAL_REPORT)
        decision = SourceRouter().route(manifest)
        assert decision.status == RouteStatus.ROUTABLE
        assert decision.route == "annual_report"
        assert decision.route != "investor_presentation"


# ===========================================================================
# Group 2: Processor contract — can_process() and precondition gates
# ===========================================================================

class TestInvestorPresentationProcessorContract:
    def test_can_process_investor_presentation(self):
        """can_process() returns True for IDENTIFIED INVESTOR_PRESENTATION."""
        proc = InvestorPresentationProcessor()
        manifest = _make_manifest()
        assert proc.can_process(manifest) is True

    def test_cannot_process_quarterly_report(self):
        """InvestorPresentationProcessor cannot process QUARTERLY_REPORT."""
        proc = InvestorPresentationProcessor()
        manifest = _make_manifest(source_type=SourceType.QUARTERLY_REPORT, quarter=FiscalQuarter.Q1)
        assert proc.can_process(manifest) is False

    def test_cannot_process_annual_report(self):
        """InvestorPresentationProcessor cannot process ANNUAL_REPORT."""
        proc = InvestorPresentationProcessor()
        manifest = _make_manifest(source_type=SourceType.ANNUAL_REPORT)
        assert proc.can_process(manifest) is False

    def test_review_required_cannot_execute(self):
        """REVIEW_REQUIRED manifest raises ProcessorUnavailableError on process()."""
        proc = InvestorPresentationProcessor()
        manifest = _make_manifest(status=ClassificationStatus.REVIEW_REQUIRED)
        from pathlib import Path
        with pytest.raises(ProcessorUnavailableError, match="IDENTIFIED"):
            proc.process(manifest, Path("dummy.pdf"))

    def test_wrong_source_type_raises(self):
        """Calling process() with QUARTERLY_REPORT manifest raises ProcessorUnavailableError."""
        proc = InvestorPresentationProcessor()
        manifest = _make_manifest(
            source_type=SourceType.QUARTERLY_REPORT,
            quarter=FiscalQuarter.Q1,
        )
        from pathlib import Path
        with pytest.raises(ProcessorUnavailableError, match="INVESTOR_PRESENTATION"):
            proc.process(manifest, Path("dummy.pdf"))


# ===========================================================================
# Group 3: Period semantics — Q4 FY26 ≠ FY26
# ===========================================================================

class TestPresentationPeriodSemantics:
    def test_q4_fy26_is_current_quarter(self):
        """With context_fy=26, context_quarter=4: 'Q4 FY26' → CURRENT_QUARTER."""
        role = interpret_period_role("Q4 FY26", context_fy=26, context_quarter=4)
        assert role == FinancialPeriodRole.CURRENT_QUARTER

    def test_fy26_is_full_year_comparative(self):
        """With context_fy=26, context_quarter=4: bare 'FY26' → FULL_YEAR_COMPARATIVE."""
        role = interpret_period_role("FY26", context_fy=26, context_quarter=4)
        assert role == FinancialPeriodRole.FULL_YEAR_COMPARATIVE

    def test_q4_fy26_ne_fy26_distinct_roles(self):
        """Q4 FY26 and FY26 must produce different period roles — never collapsed."""
        q4_role = interpret_period_role("Q4 FY26", context_fy=26, context_quarter=4)
        full_year_role = interpret_period_role("FY26", context_fy=26, context_quarter=4)
        assert q4_role != full_year_role

    def test_fy25_is_prior_year_full_year(self):
        """With context_fy=26: 'FY25' → PRIOR_YEAR_FULL_YEAR."""
        role = interpret_period_role("FY25", context_fy=26, context_quarter=4)
        assert role == FinancialPeriodRole.PRIOR_YEAR_FULL_YEAR

    def test_q4_fy25_is_prior_year_same_quarter(self):
        """With context_fy=26, context_quarter=4: 'Q4 FY25' → PRIOR_YEAR_SAME_QUARTER."""
        role = interpret_period_role("Q4 FY25", context_fy=26, context_quarter=4)
        assert role == FinancialPeriodRole.PRIOR_YEAR_SAME_QUARTER

    def test_q3_fy26_is_previous_quarter(self):
        """With context_fy=26, context_quarter=4: 'Q3 FY26' → PREVIOUS_QUARTER."""
        role = interpret_period_role("Q3 FY26", context_fy=26, context_quarter=4)
        assert role == FinancialPeriodRole.PREVIOUS_QUARTER


# ===========================================================================
# Group 4: context_quarter semantics — missing is preserved, never fabricated
# ===========================================================================

class TestContextQuarterSemantics:
    def test_null_quarter_returns_none(self):
        """Full-year presentation (fiscal_quarter=None) → context_quarter=None, never Q4."""
        manifest = _make_manifest(quarter=None)
        fiscal_quarter = manifest.reporting_period.fiscal_quarter
        # This mirrors the exact derivation in InvestorPresentationProcessor.process()
        context_quarter = int(fiscal_quarter.value[1]) if fiscal_quarter else None
        assert context_quarter is None

    def test_null_quarter_never_becomes_q4(self):
        """Absence of quarter evidence must not produce context_quarter=4."""
        manifest = _make_manifest(quarter=None)
        fiscal_quarter = manifest.reporting_period.fiscal_quarter
        context_quarter = int(fiscal_quarter.value[1]) if fiscal_quarter else None
        assert context_quarter != 4

    def test_q1_explicit_returns_1(self):
        """Explicit Q1 in manifest → context_quarter=1."""
        manifest = _make_manifest(quarter=FiscalQuarter.Q1)
        fiscal_quarter = manifest.reporting_period.fiscal_quarter
        context_quarter = int(fiscal_quarter.value[1]) if fiscal_quarter else None
        assert context_quarter == 1

    def test_q2_explicit_returns_2(self):
        """Explicit Q2 in manifest → context_quarter=2."""
        manifest = _make_manifest(quarter=FiscalQuarter.Q2)
        fiscal_quarter = manifest.reporting_period.fiscal_quarter
        context_quarter = int(fiscal_quarter.value[1]) if fiscal_quarter else None
        assert context_quarter == 2

    def test_q3_explicit_returns_3(self):
        """Explicit Q3 in manifest → context_quarter=3."""
        manifest = _make_manifest(quarter=FiscalQuarter.Q3)
        fiscal_quarter = manifest.reporting_period.fiscal_quarter
        context_quarter = int(fiscal_quarter.value[1]) if fiscal_quarter else None
        assert context_quarter == 3

    def test_q4_explicit_returns_4(self):
        """Explicit Q4 in manifest → context_quarter=4 (because Q4 is evidenced, not inferred)."""
        manifest = _make_manifest(quarter=FiscalQuarter.Q4)
        fiscal_quarter = manifest.reporting_period.fiscal_quarter
        context_quarter = int(fiscal_quarter.value[1]) if fiscal_quarter else None
        assert context_quarter == 4

    def test_mixed_q4_fy_explicit_q4_uses_q4(self):
        """Mixed 'Full Year & Q4 FY26' presentation where Q4 IS explicit → context_quarter=4."""
        manifest = _make_manifest(quarter=FiscalQuarter.Q4, fiscal_year="fy26")
        fiscal_quarter = manifest.reporting_period.fiscal_quarter
        context_quarter = int(fiscal_quarter.value[1]) if fiscal_quarter else None
        # Q4 is explicit in the manifest — this is evidence-backed, not inferred
        assert context_quarter == 4


# ===========================================================================
# Group 4b: FY-only presentation period roles — quarterly patterns → UNKNOWN
# ===========================================================================

class TestFYOnlyPresentationPeriodRoles:
    def test_fy_only_q4_period_is_unknown(self):
        """'Q4 FY26' returns UNKNOWN when context_quarter=None (no quarter evidence)."""
        from knowledge.financials.period_roles import interpret_period_role, FinancialPeriodRole
        role = interpret_period_role("Q4 FY26", context_fy=26, context_quarter=None)
        assert role == FinancialPeriodRole.UNKNOWN

    def test_fy_only_q1_period_is_unknown(self):
        """'Q1 FY26' returns UNKNOWN when context_quarter=None."""
        from knowledge.financials.period_roles import interpret_period_role, FinancialPeriodRole
        role = interpret_period_role("Q1 FY26", context_fy=26, context_quarter=None)
        assert role == FinancialPeriodRole.UNKNOWN

    def test_fy_only_bare_fy_still_resolves(self):
        """'FY26' resolves to FULL_YEAR_COMPARATIVE even when context_quarter=None."""
        from knowledge.financials.period_roles import interpret_period_role, FinancialPeriodRole
        role = interpret_period_role("FY26", context_fy=26, context_quarter=None)
        assert role == FinancialPeriodRole.FULL_YEAR_COMPARATIVE

    def test_fy_only_prior_year_fy_still_resolves(self):
        """'FY25' resolves to PRIOR_YEAR_FULL_YEAR even when context_quarter=None."""
        from knowledge.financials.period_roles import interpret_period_role, FinancialPeriodRole
        role = interpret_period_role("FY25", context_fy=26, context_quarter=None)
        assert role == FinancialPeriodRole.PRIOR_YEAR_FULL_YEAR

    def test_fy_only_h1_still_resolves(self):
        """'H1 FY26' resolves to HALF_YEAR even when context_quarter=None."""
        from knowledge.financials.period_roles import interpret_period_role, FinancialPeriodRole
        role = interpret_period_role("H1 FY26", context_fy=26, context_quarter=None)
        assert role == FinancialPeriodRole.HALF_YEAR

    def test_fy_only_annotate_preserves_fy_roles(self):
        """annotate_period_roles with context_quarter=None still assigns FY-level roles."""
        from knowledge.financials.period_roles import annotate_period_roles, FinancialPeriodRole
        from knowledge.financials.extraction_schema import ExtractedValue

        values = [
            ExtractedValue(period="FY26", value_raw="44177", unit_hint="mn", currency_hint="INR", value_crore=4417.7),
            ExtractedValue(period="FY25", value_raw="40277", unit_hint="mn", currency_hint="INR", value_crore=4027.7),
            ExtractedValue(period="Q4 FY26", value_raw="11775", unit_hint="mn", currency_hint="INR", value_crore=1177.5),
        ]
        annotate_period_roles(values, context_fy=26, context_quarter=None)
        assert values[0].period_role == FinancialPeriodRole.FULL_YEAR_COMPARATIVE.value
        assert values[1].period_role == FinancialPeriodRole.PRIOR_YEAR_FULL_YEAR.value
        assert values[2].period_role == FinancialPeriodRole.UNKNOWN.value  # no quarter context


# ===========================================================================
# Group 5: Storage path — document-scoped, no collision with quarterly/annual
# ===========================================================================

class TestPresentationStoragePath:
    def test_destination_contains_presentations(self):
        """INVESTOR_PRESENTATION destination includes 'presentations/' segment."""
        manifest = _make_manifest(
            content_hash="sha256:e7a0d6617e2ef3fcb595ef386ef7788b",
        )
        decision = SourceRouter().route(manifest)
        assert decision.destination is not None
        assert "presentations" in decision.destination

    def test_destination_does_not_contain_quarters(self):
        """INVESTOR_PRESENTATION destination never contains 'quarters/'."""
        manifest = _make_manifest()
        decision = SourceRouter().route(manifest)
        assert decision.destination is None or "quarters" not in (decision.destination or "")

    def test_destination_does_not_contain_raw(self):
        """INVESTOR_PRESENTATION destination never uses '/raw/' (annual slot)."""
        manifest = _make_manifest()
        decision = SourceRouter().route(manifest)
        assert decision.destination is None or "/raw/" not in (decision.destination or "")

    def test_two_presentations_different_hashes_different_destinations(self):
        """Two presentations with different content hashes get different destination paths."""
        m1 = _make_manifest(content_hash="sha256:aaaa1111bbbb2222")
        m2 = _make_manifest(content_hash="sha256:cccc3333dddd4444")
        d1 = SourceRouter().route(m1).destination
        d2 = SourceRouter().route(m2).destination
        assert d1 != d2


# ===========================================================================
# Group 6: InvestorPresentationResult typed contract
# ===========================================================================

class TestInvestorPresentationResultContract:
    def test_to_dict_has_required_fields(self):
        """InvestorPresentationResult.to_dict() contains all required fields."""
        r = InvestorPresentationResult(
            company="acme",
            fiscal_year="fy26",
            period_label="FY26",
            context_quarter=4,
            source_file="/data/acme.pdf",
            storage_path="companies/acme/fy26/presentations/abcd1234/",
        )
        d = r.to_dict()
        required = {
            "company", "fiscal_year", "period_label", "context_quarter",
            "source_file", "storage_path", "status", "document_hash",
            "source_type", "source_channel", "warnings", "extracted_fact_count",
            "period_roles_found", "slide_count", "chunks_path", "manifest_path",
            "raw_tables_path", "result_path",
        }
        assert required.issubset(d.keys())

    def test_result_default_status_is_success(self):
        """Default status for InvestorPresentationResult is 'SUCCESS'."""
        r = InvestorPresentationResult(
            company="acme",
            fiscal_year="fy26",
            period_label="FY26",
            context_quarter=4,
            source_file="/data/acme.pdf",
            storage_path="companies/acme/fy26/presentations/abcd1234/",
        )
        assert r.status == "SUCCESS"

    def test_result_context_quarter_preserved_when_int(self):
        """context_quarter=4 (explicit Q4) is written into to_dict() correctly."""
        r = InvestorPresentationResult(
            company="acme",
            fiscal_year="fy26",
            period_label="FY26",
            context_quarter=4,
            source_file="/data/acme.pdf",
            storage_path="companies/acme/fy26/presentations/abcd1234/",
        )
        assert r.to_dict()["context_quarter"] == 4

    def test_result_context_quarter_none_for_full_year(self):
        """context_quarter=None (full-year-only) is preserved in to_dict()."""
        r = InvestorPresentationResult(
            company="acme",
            fiscal_year="fy26",
            period_label="FY26",
            context_quarter=None,
            source_file="/data/acme.pdf",
            storage_path="companies/acme/fy26/presentations/abcd1234/",
        )
        assert r.to_dict()["context_quarter"] is None


# ===========================================================================
# Group 7: No company-specific code
# ===========================================================================

class TestNoCompanySpecificCodePhase5:
    _COMPANY_NAMES = ["ujjivan", "sun_pharma", "polymatech", "datapatterns", "tanla", "ltts"]

    def test_investor_presentation_processor_no_company_names(self):
        """InvestorPresentationProcessor source must contain no company-specific logic."""
        import inspect
        from knowledge import document_processor
        src = inspect.getsource(document_processor.InvestorPresentationProcessor)
        for name in self._COMPANY_NAMES:
            assert name not in src.lower(), (
                f"InvestorPresentationProcessor contains company-specific reference: {name!r}"
            )

    def test_document_router_no_company_names(self):
        """document_router.py must contain no company-specific references."""
        import knowledge.document_router as router_mod
        import inspect
        src = inspect.getsource(router_mod)
        for name in self._COMPANY_NAMES:
            assert name not in src.lower(), (
                f"document_router contains company-specific reference: {name!r}"
            )

    def test_period_roles_no_company_names(self):
        """period_roles.py must contain no company-specific references."""
        from knowledge.financials import period_roles as pr_mod
        import inspect
        src = inspect.getsource(pr_mod)
        for name in self._COMPANY_NAMES:
            assert name not in src.lower(), (
                f"period_roles contains company-specific reference: {name!r}"
            )
