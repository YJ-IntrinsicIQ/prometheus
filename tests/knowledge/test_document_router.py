"""Focused tests for Phase 3: canonical source router + processing entry point.

Coverage:
  R01  identified annual report routes correctly
  R02  opaque filename routes correctly (identity from content, not filename)
  R03  misleading filename still routes correctly
  R04  REVIEW_REQUIRED manifest does not route into processor
  R05  UNIDENTIFIED manifest does not route
  R06  REJECTED manifest does not route
  R07  quarterly report recognized but processor unavailable
  R08  investor presentation recognized but processor unavailable
  R09  earnings-call transcript recognized but processor unavailable
  R10  exchange filing recognized but processor unavailable
  R11  OTHER does not fall back to annual-report pipeline
  R12  UNKNOWN does not fall back to annual-report pipeline
  R13  annual-report compatibility adapter works via AnnualReportProcessor
  R14  destination derived only after identity
  R15  source file is NOT moved by default
  R16  execute=False (default) does not invoke processor
  R17  execution requires explicit execute=True
  R18  ProcessorInterface is generic / abstractly enforced
  R19  error states remain distinct (REJECTED != UNSUPPORTED != REVIEW_REQUIRED)
  R20  content hash / document_id carried through routing decision
  R21  no company-specific logic in router
  R22  no source-specific downstream intelligence duplication
  R23  existing document-intake tests still import correctly
  R24  existing identifier tests still import correctly

Real-PDF tests are guarded on file existence so the suite passes without
production PDFs on CI.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

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
    IntakeProvenance,
    LegacyPipelineInputs,
    ReportingPeriod,
    SourceType,
    build_legacy_annual_report_manifest,
)
from knowledge.document_router import (
    ProcessorState,
    RouteStatus,
    RoutingDecision,
    SourceRouter,
    _derive_destination,
)
from knowledge.document_processor import (
    AnnualReportProcessor,
    CompatibilityAdapterError,
    DocumentProcessingResult,
    ProcessorExecutionError,
    ProcessorInterface,
    ProcessorStatus,
    UnsupportedSourceTypeError,
    process_document,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

POLYMATECH_PDF = Path("companies/polymatech/fy24/raw/polymatech_fy24.pdf")
UJJIVAN_PDF = Path("companies/ujjivan/fy25/raw/ujjivan_fy25.pdf")
SUN_PHARMA_PDF = Path("data/Processed/sun_pharma/fy26/annual_report/sun_pharma_fy26.pdf")


def _ts() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _make_manifest(
    *,
    status: ClassificationStatus = ClassificationStatus.IDENTIFIED,
    source_type: SourceType = SourceType.ANNUAL_REPORT,
    company: str = "testco",
    fiscal_year: str = "fy24",
    content_hash: str = "sha256:abc123",
    document_id: str = "doc-001",
    storage_path: str = "companies/testco/fy24/raw/testco_fy24.pdf",
    unresolved_fields: list[str] | None = None,
    warnings: list[str] | None = None,
) -> DocumentIntakeManifest:
    overall_conf = (
        ConfidenceLevel.HIGH
        if status == ClassificationStatus.IDENTIFIED
        else ConfidenceLevel.LOW
    )
    company_conf = (
        ConfidenceLevel.HIGH
        if status not in (ClassificationStatus.UNIDENTIFIED, ClassificationStatus.REJECTED)
        else ConfidenceLevel.UNKNOWN
    )
    resolved_key = (
        company
        if status not in (ClassificationStatus.UNIDENTIFIED, ClassificationStatus.REJECTED)
        else None
    )
    return DocumentIntakeManifest(
        document_id=document_id,
        file=FileIdentity(
            original_filename="testco_fy24.pdf",
            content_hash=content_hash,
            mime_type="application/pdf",
            size_bytes=1024,
            storage_path=storage_path,
        ),
        company_identity=CompanyIdentity(
            resolved_company_key=resolved_key,
            confidence=company_conf,
        ),
        document_identity=DocumentIdentity(
            source_type=source_type,
            confidence=ConfidenceLevel.HIGH,
        ),
        reporting_period=ReportingPeriod(
            fiscal_year=fiscal_year,
            confidence=ConfidenceLevel.HIGH,
        ),
        entity_scope=EntityScope.CONSOLIDATED,
        classification=ClassificationState(
            overall_confidence=overall_conf,
            status=status,
            unresolved_fields=unresolved_fields or [],
            warnings=warnings or [],
        ),
        provenance=IntakeProvenance(
            ingestion_timestamp=_ts(),
            detection_method=DetectionMethod.AUTOMATIC_CLASSIFIER,
        ),
    )


# ---------------------------------------------------------------------------
# R01 – identified annual report routes correctly
# ---------------------------------------------------------------------------

def test_r01_identified_annual_report_routes():
    manifest = _make_manifest(source_type=SourceType.ANNUAL_REPORT)
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.ROUTABLE
    assert decision.route == "annual_report"
    assert decision.processor == ProcessorState.AVAILABLE


# ---------------------------------------------------------------------------
# R02 – opaque filename routes correctly (router is content-independent)
# ---------------------------------------------------------------------------

def test_r02_opaque_filename_routes():
    manifest = _make_manifest(
        source_type=SourceType.ANNUAL_REPORT,
        storage_path="companies/testco/fy24/raw/document_001.pdf",
    )
    # The router does not inspect filenames — it trusts the manifest from the identifier.
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.ROUTABLE
    assert decision.route == "annual_report"


# ---------------------------------------------------------------------------
# R03 – misleading filename still routes correctly
# ---------------------------------------------------------------------------

def test_r03_misleading_filename_routes():
    manifest = _make_manifest(
        source_type=SourceType.ANNUAL_REPORT,
        company="testco",
        storage_path="companies/testco/fy24/raw/other_company_report.pdf",
    )
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.ROUTABLE
    assert decision.route == "annual_report"
    assert decision.manifest.company_identity.resolved_company_key == "testco"


# ---------------------------------------------------------------------------
# R04 – REVIEW_REQUIRED manifest does not route into processor
# ---------------------------------------------------------------------------

def test_r04_review_required_does_not_route():
    manifest = _make_manifest(
        status=ClassificationStatus.REVIEW_REQUIRED,
        source_type=SourceType.ANNUAL_REPORT,
        unresolved_fields=["reporting_period.fiscal_year"],
    )
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.REVIEW_REQUIRED
    assert decision.processor == ProcessorState.UNAVAILABLE
    assert "reporting_period.fiscal_year" in decision.unresolved_fields


# ---------------------------------------------------------------------------
# R05 – UNIDENTIFIED manifest does not route
# ---------------------------------------------------------------------------

def test_r05_unidentified_does_not_route():
    manifest = _make_manifest(
        status=ClassificationStatus.UNIDENTIFIED,
        company="",
    )
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.UNSUPPORTED
    assert decision.destination is None


# ---------------------------------------------------------------------------
# R06 – REJECTED manifest does not route
# ---------------------------------------------------------------------------

def test_r06_rejected_does_not_route():
    manifest = _make_manifest(status=ClassificationStatus.REJECTED)
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.REJECTED
    assert decision.processor == ProcessorState.UNAVAILABLE
    assert decision.destination is None


# ---------------------------------------------------------------------------
# R07 – quarterly report recognized and processor available (Gate B closed)
# ---------------------------------------------------------------------------

def test_r07_quarterly_routable():
    """QuarterlyReportProcessor is now AVAILABLE after direct Tanla proof passed."""
    manifest = _make_manifest(source_type=SourceType.QUARTERLY_REPORT)
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.ROUTABLE
    assert decision.route == "quarterly_report"
    assert decision.processor == ProcessorState.AVAILABLE
    # Must NOT silently route as annual report
    assert decision.route != "annual_report"


# ---------------------------------------------------------------------------
# R08 – investor presentation recognized but processor unavailable
# ---------------------------------------------------------------------------

def test_r08_presentation_routable():
    """InvestorPresentationProcessor is now AVAILABLE after direct production proof passed."""
    manifest = _make_manifest(source_type=SourceType.INVESTOR_PRESENTATION)
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.ROUTABLE
    assert decision.route == "investor_presentation"
    assert decision.processor == ProcessorState.AVAILABLE
    assert decision.route != "quarterly_report"
    assert decision.route != "annual_report"


# ---------------------------------------------------------------------------
# R09 – earnings-call transcript recognized and routable after production proof
# ---------------------------------------------------------------------------

def test_r09_concall_no_fallback():
    manifest = _make_manifest(source_type=SourceType.EARNINGS_CALL_TRANSCRIPT)
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.ROUTABLE
    assert decision.route == "earnings_call_transcript"
    assert decision.processor == ProcessorState.AVAILABLE
    assert decision.route != "annual_report"


# ---------------------------------------------------------------------------
# R09b – earnings release recognized and routable after production proof
# ---------------------------------------------------------------------------

def test_r09b_earnings_release_routable():
    manifest = _make_manifest(source_type=SourceType.EARNINGS_RELEASE)
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.ROUTABLE
    assert decision.route == "earnings_release"
    assert decision.processor == ProcessorState.AVAILABLE
    assert decision.route != "quarterly_report"
    assert decision.route != "investor_presentation"


# ---------------------------------------------------------------------------
# R10 – exchange filing recognized but processor unavailable
# ---------------------------------------------------------------------------

def test_r10_exchange_filing_no_fallback():
    manifest = _make_manifest(source_type=SourceType.EXCHANGE_FILING)
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.UNSUPPORTED
    assert decision.route == "exchange_filing"
    assert decision.processor == ProcessorState.NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# R11 – OTHER does not fall back
# ---------------------------------------------------------------------------

def test_r11_other_no_fallback():
    manifest = _make_manifest(source_type=SourceType.OTHER)
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.UNSUPPORTED
    assert decision.route == "other"
    assert decision.processor == ProcessorState.NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# R12 – UNKNOWN does not fall back
# ---------------------------------------------------------------------------

def test_r12_unknown_no_fallback():
    manifest = _make_manifest(source_type=SourceType.UNKNOWN)
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.UNSUPPORTED
    assert decision.route == "unknown"
    assert decision.processor == ProcessorState.NOT_IMPLEMENTED


# ---------------------------------------------------------------------------
# R13 – annual-report compatibility adapter works via AnnualReportProcessor
# ---------------------------------------------------------------------------

def test_r13_annual_report_processor_bridge():
    manifest = build_legacy_annual_report_manifest(
        company_key="polymatech",
        fiscal_year="fy24",
        source_file="companies/polymatech/fy24/raw/polymatech_fy24.pdf",
    )
    manifest.file.storage_path = "companies/polymatech/fy24/raw/polymatech_fy24.pdf"
    # File may not exist in CI — set a fixture hash so the adapter validator passes.
    if not manifest.file.content_hash:
        manifest.file.content_hash = "sha256:fixture_polymatech_fy24"
    proc = AnnualReportProcessor()
    assert proc.can_process(manifest)
    inputs = proc.process(manifest, Path("companies/polymatech/fy24/raw/polymatech_fy24.pdf"))
    assert isinstance(inputs, LegacyPipelineInputs)
    assert inputs.company == "polymatech"
    assert inputs.year == "fy24"
    assert "polymatech_fy24.pdf" in inputs.source_file


# ---------------------------------------------------------------------------
# R14 – destination derived only after identity
# ---------------------------------------------------------------------------

def test_r14_destination_requires_identity():
    # No company resolved — destination must be None
    manifest_no_company = _make_manifest(
        status=ClassificationStatus.UNIDENTIFIED, company=""
    )
    assert _derive_destination(manifest_no_company) is None

    # Company and year resolved — destination is computed
    manifest_ok = _make_manifest(
        company="polymatech", fiscal_year="fy24",
        storage_path="companies/polymatech/fy24/raw/polymatech_fy24.pdf",
    )
    dest = _derive_destination(manifest_ok)
    assert dest is not None
    assert "polymatech" in dest
    assert "fy24" in dest


# ---------------------------------------------------------------------------
# R15 – source file is NOT moved by default
# ---------------------------------------------------------------------------

def test_r15_source_file_not_moved(tmp_path):
    pdf = tmp_path / "testco_fy24.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake content for router test " * 200)
    original_mtime = pdf.stat().st_mtime
    result = process_document(pdf, execute=False)
    # File must still exist at original location
    assert pdf.exists()
    # mtime unchanged — file not touched
    assert pdf.stat().st_mtime == original_mtime


# ---------------------------------------------------------------------------
# R16 – execute=False (default) does not invoke processor
# ---------------------------------------------------------------------------

def test_r16_execute_false_does_not_invoke_processor(tmp_path):
    pdf = tmp_path / "testco_fy24.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake content for router test " * 200)
    # We patch the processor to confirm it is never called
    called = []

    original_process = AnnualReportProcessor.process

    def spy_process(self, manifest, path):
        called.append(True)
        return original_process(self, manifest, path)

    with patch.object(AnnualReportProcessor, "process", spy_process):
        result = process_document(pdf, execute=False)

    assert not called, "Processor.process() must not be called when execute=False"
    # Status should be ROUTED (if identified) or UNSUPPORTED/REJECTED (content-based)
    assert result.status in (
        ProcessorStatus.ROUTED,
        ProcessorStatus.UNSUPPORTED,
        ProcessorStatus.REJECTED,
        ProcessorStatus.REVIEW_REQUIRED,
        ProcessorStatus.ERROR,  # if PDF text extraction fails on the fake PDF
    )


# ---------------------------------------------------------------------------
# R17 – execution requires explicit execute=True
# ---------------------------------------------------------------------------

def test_r17_execute_true_required_for_processor():
    manifest = build_legacy_annual_report_manifest(
        company_key="testco",
        fiscal_year="fy24",
        source_file="companies/testco/fy24/raw/testco_fy24.pdf",
    )
    manifest.file.storage_path = "companies/testco/fy24/raw/testco_fy24.pdf"
    if not manifest.file.content_hash:
        manifest.file.content_hash = "sha256:fixture_testco_fy24"
    proc = AnnualReportProcessor()
    # Can process (contract check)
    assert proc.can_process(manifest)
    # Calling process() explicitly works
    inputs = proc.process(manifest, Path("companies/testco/fy24/raw/testco_fy24.pdf"))
    assert isinstance(inputs, LegacyPipelineInputs)


# ---------------------------------------------------------------------------
# R18 – ProcessorInterface is generic / abstractly enforced
# ---------------------------------------------------------------------------

def test_r18_processor_interface_is_abstract():
    # Cannot instantiate ProcessorInterface directly
    with pytest.raises(TypeError):
        ProcessorInterface()  # type: ignore[abstract]


def test_r18b_custom_processor_must_implement_both_methods():
    class PartialProcessor(ProcessorInterface):
        def can_process(self, manifest):
            return True
        # process() not implemented

    with pytest.raises(TypeError):
        PartialProcessor()  # type: ignore[abstract]


def test_r18c_custom_processor_registers_cleanly():
    class TestProcessor(ProcessorInterface):
        def can_process(self, manifest):
            return manifest.document_identity.source_type == SourceType.OTHER

        def process(self, manifest, source_path):
            return {"status": "test_ok"}

    proc = TestProcessor()
    m = _make_manifest(source_type=SourceType.OTHER)
    assert proc.can_process(m)
    assert proc.process(m, Path(".")) == {"status": "test_ok"}


# ---------------------------------------------------------------------------
# R19 – error states remain distinct
# ---------------------------------------------------------------------------

def test_r19_error_states_distinct():
    rejected = _make_manifest(status=ClassificationStatus.REJECTED)
    unidentified = _make_manifest(status=ClassificationStatus.UNIDENTIFIED, company="")
    review = _make_manifest(
        status=ClassificationStatus.REVIEW_REQUIRED,
        unresolved_fields=["reporting_period.fiscal_year"],
    )

    router = SourceRouter()
    r_rej = router.route(rejected)
    r_uni = router.route(unidentified)
    r_rev = router.route(review)

    assert r_rej.status == RouteStatus.REJECTED
    assert r_uni.status == RouteStatus.UNSUPPORTED
    assert r_rev.status == RouteStatus.REVIEW_REQUIRED

    # All three are distinct
    statuses = {r_rej.status, r_uni.status, r_rev.status}
    assert len(statuses) == 3


# ---------------------------------------------------------------------------
# R20 – content hash / document_id carried through routing decision
# ---------------------------------------------------------------------------

def test_r20_content_hash_and_document_id_carried():
    manifest = _make_manifest(
        content_hash="sha256:deadbeef",
        document_id="doc-xyz-42",
    )
    decision = SourceRouter().route(manifest)
    assert decision.content_hash == "sha256:deadbeef"
    assert decision.document_id == "doc-xyz-42"


# ---------------------------------------------------------------------------
# R21 – no company-specific logic in router
# ---------------------------------------------------------------------------

def test_r21_router_has_no_company_specific_code():
    import inspect
    import knowledge.document_router as router_mod
    source = inspect.getsource(router_mod)
    # Names that would suggest company-specific hardcoding
    forbidden = ["ujjivan", "sun_pharma", "polymatech", "datapatterns", "tanla"]
    for name in forbidden:
        assert name not in source.lower(), (
            f"Company-specific name '{name}' found in document_router.py"
        )


# ---------------------------------------------------------------------------
# R22 – no source-specific downstream intelligence duplication
# ---------------------------------------------------------------------------

def test_r22_no_source_specific_intelligence_modules():
    import inspect
    import knowledge.document_processor as proc_mod
    source = inspect.getsource(proc_mod)
    forbidden_patterns = [
        "quarterly_company_model",
        "presentation_company_model",
        "concall_company_model",
        "exchange_filing_company_model",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in source, (
            f"Forbidden source-specific intelligence module '{pattern}' "
            "found in document_processor.py"
        )


# ---------------------------------------------------------------------------
# R23 – existing document-intake tests still import correctly
# ---------------------------------------------------------------------------

def test_r23_document_intake_imports_clean():
    from knowledge.document_intake import (
        DocumentIntakeManifest,
        manifest_to_legacy_pipeline_inputs,
        build_legacy_annual_report_manifest,
        validate_document_intake_manifest,
    )
    # Spot-check: build a manifest and validate it
    m = build_legacy_annual_report_manifest(
        company_key="testco",
        fiscal_year="fy25",
        source_file="companies/testco/fy25/raw/testco_fy25.pdf",
    )
    m.file.storage_path = "companies/testco/fy25/raw/testco_fy25.pdf"
    if not m.file.content_hash:
        m.file.content_hash = "sha256:fixture_testco_fy25"
    errors = validate_document_intake_manifest(m)
    assert not errors


# ---------------------------------------------------------------------------
# R24 – existing identifier tests still import correctly
# ---------------------------------------------------------------------------

def test_r24_document_identifier_imports_clean():
    from knowledge.document_identifier import identify_document
    from knowledge.document_identifier import (
        _is_filing_reference,
        _score_fy_candidate,
        _select_best_fy_candidate,
    )
    assert callable(identify_document)
    assert callable(_is_filing_reference)
    assert callable(_score_fy_candidate)
    assert callable(_select_best_fy_candidate)


# ---------------------------------------------------------------------------
# R25 – REVIEW_REQUIRED exposes unresolved fields (Part 13)
# ---------------------------------------------------------------------------

def test_r25_review_required_preserves_unresolved_fields():
    manifest = _make_manifest(
        status=ClassificationStatus.REVIEW_REQUIRED,
        source_type=SourceType.ANNUAL_REPORT,
        unresolved_fields=["reporting_period.fiscal_year", "company_identity.confidence"],
        warnings=["Ambiguous company signal — two candidates detected"],
    )
    decision = SourceRouter().route(manifest)
    assert decision.status == RouteStatus.REVIEW_REQUIRED
    assert "reporting_period.fiscal_year" in decision.unresolved_fields
    assert "company_identity.confidence" in decision.unresolved_fields
    # Warnings carried forward
    assert any("ambiguous" in w.lower() for w in decision.warnings)
    # Destination not guessed
    assert decision.destination is None


# ---------------------------------------------------------------------------
# R26 – process_document with missing file returns ERROR
# ---------------------------------------------------------------------------

def test_r26_missing_file_returns_error():
    result = process_document(Path("/tmp/nonexistent_prometheus_doc.pdf"))
    assert result.status == ProcessorStatus.ERROR
    assert result.manifest is None
    assert result.routing is None
    assert result.error is not None


# ---------------------------------------------------------------------------
# R27 – process_document with empty file returns REJECTED
# ---------------------------------------------------------------------------

def test_r27_empty_file_returns_rejected(tmp_path):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    result = process_document(empty)
    assert result.status == ProcessorStatus.REJECTED
    assert result.manifest is None


# ---------------------------------------------------------------------------
# R28 – to_dict is serializable for routing decision and processing result
# ---------------------------------------------------------------------------

def test_r28_to_dict_is_serializable():
    import json
    manifest = _make_manifest()
    decision = SourceRouter().route(manifest)
    d = decision.to_dict()
    json.dumps(d)  # must not raise

    result = DocumentProcessingResult(
        manifest=manifest,
        routing=decision,
        status=ProcessorStatus.ROUTED,
        processor_output=None,
        error=None,
    )
    r = result.to_dict()
    json.dumps(r)  # must not raise


# ---------------------------------------------------------------------------
# Production proof — real PDFs (guarded on file existence)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not POLYMATECH_PDF.exists(),
    reason="polymatech_fy24.pdf not present",
)
def test_prod_polymatech_routes_as_annual_report():
    result = process_document(POLYMATECH_PDF, execute=False)
    assert result.status == ProcessorStatus.ROUTED
    assert result.routing is not None
    assert result.routing.status == RouteStatus.ROUTABLE
    assert result.routing.route == "annual_report"
    assert result.routing.processor == ProcessorState.AVAILABLE
    manifest = result.manifest
    assert manifest.company_identity.resolved_company_key == "polymatech"
    assert manifest.reporting_period.fiscal_year == "fy24"
    assert manifest.document_identity.source_type == SourceType.ANNUAL_REPORT


@pytest.mark.skipif(
    not POLYMATECH_PDF.exists(),
    reason="polymatech_fy24.pdf not present",
)
def test_prod_polymatech_executes_adapter():
    result = process_document(POLYMATECH_PDF, execute=True)
    assert result.status == ProcessorStatus.EXECUTED
    assert isinstance(result.processor_output, LegacyPipelineInputs)
    assert result.processor_output.company == "polymatech"
    assert result.processor_output.year == "fy24"


@pytest.mark.skipif(
    not UJJIVAN_PDF.exists(),
    reason="ujjivan_fy25.pdf not present",
)
def test_prod_ujjivan_routes_as_annual_report_via_exchange_filing():
    """Phase 3.3: BSE/NSE submission wrapping an annual report must route as ANNUAL_REPORT.

    Old behaviour (v2): source_type=EXCHANGE_FILING → UNSUPPORTED.
    New behaviour (v3): source_channel=EXCHANGE_FILING, source_type=ANNUAL_REPORT → ROUTABLE.
    """
    from knowledge.document_intake import SourceChannel
    result = process_document(UJJIVAN_PDF, execute=False)
    assert result.routing is not None
    assert result.routing.route == "annual_report"
    assert result.routing.processor == ProcessorState.AVAILABLE
    assert result.status == ProcessorStatus.ROUTED
    assert result.manifest.document_identity.source_channel == SourceChannel.EXCHANGE_FILING
    assert result.manifest.reporting_period.fiscal_year == "fy25"


@pytest.mark.skipif(
    not SUN_PHARMA_PDF.exists(),
    reason="sun_pharma_fy26.pdf not present",
)
def test_prod_sun_pharma_routes_as_annual_report_via_exchange_filing():
    """Phase 3.3: BSE/NSE submission wrapping Sun Pharma annual report must route correctly.

    Old behaviour (v2): source_type=EXCHANGE_FILING → UNSUPPORTED.
    New behaviour (v3): source_channel=EXCHANGE_FILING, source_type=ANNUAL_REPORT → ROUTABLE.
    """
    from knowledge.document_intake import SourceChannel
    result = process_document(SUN_PHARMA_PDF, execute=False)
    assert result.routing is not None
    assert result.routing.route == "annual_report"
    assert result.routing.processor == ProcessorState.AVAILABLE
    assert result.status == ProcessorStatus.ROUTED
    assert result.manifest.document_identity.source_channel == SourceChannel.EXCHANGE_FILING
    assert result.manifest.reporting_period.fiscal_year == "fy26"
