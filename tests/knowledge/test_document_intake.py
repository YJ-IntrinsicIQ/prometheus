from __future__ import annotations

import base64
from pathlib import Path

import fitz
import pytest

from knowledge.document_intake import (
    ClassificationState,
    ClassificationStatus,
    CompanyIdentity,
    ConfidenceLevel,
    DocumentDates,
    DocumentIdentity,
    DocumentIntakeManifest,
    DocumentManifestResolutionError,
    EntityScope,
    FileIdentity,
    FiscalQuarter,
    IdentityEvidence,
    ReportingPeriod,
    SourceType,
    build_document_intake_report,
    build_legacy_annual_report_manifest,
    inspect_pdf_document,
    manifest_to_legacy_pipeline_inputs,
    read_document_text,
    validate_document_intake_manifest,
)
from knowledge.document_ownership import assess_source_period_ownership, infer_document_reporting_period


def _write_text_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def _write_image_pdf(path: Path) -> None:
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Zt3QAAAAASUVORK5CYII="
    )
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(72, 72, 144, 144), stream=png_bytes)
    doc.save(path)
    doc.close()


def test_inspect_pdf_document_classifies_text_pdf(tmp_path):
    pdf_path = tmp_path / "text.pdf"
    _write_text_pdf(pdf_path, "Annual report revenue and profit")

    intake = inspect_pdf_document(pdf_path)

    assert intake.classification == "TEXT_PDF"
    assert intake.status == "supported"
    assert intake.text_page_count == 1
    assert intake.ocr_required is False
    assert read_document_text(pdf_path) == "Annual report revenue and profit"


def test_inspect_pdf_document_classifies_image_only_pdf(tmp_path):
    pdf_path = tmp_path / "image_only.pdf"
    _write_image_pdf(pdf_path)

    intake = inspect_pdf_document(pdf_path)

    assert intake.classification == "IMAGE_ONLY_PDF"
    assert intake.status == "blocked"
    assert intake.page_count == 1
    assert intake.image_page_count == 1
    assert intake.ocr_required is True
    assert read_document_text(pdf_path) == ""


def test_ocr_dependencies_available_flag_is_boolean():
    from knowledge.document_intake import _ocr_dependencies_available

    result = _ocr_dependencies_available()
    assert isinstance(result, bool)


def test_image_only_pdf_reports_ocr_capability_state(tmp_path):
    """IMAGE_ONLY_PDF must report ocr_available state and ocr_required=True."""
    pdf_path = tmp_path / "image_only.pdf"
    _write_image_pdf(pdf_path)

    intake = inspect_pdf_document(pdf_path)

    assert intake.classification == "IMAGE_ONLY_PDF"
    assert intake.ocr_required is True
    # ocr_available reflects real environment capability
    from knowledge.document_intake import _ocr_dependencies_available
    assert intake.ocr_available == _ocr_dependencies_available()


def test_image_only_pdf_with_ocr_disabled_still_rejects(tmp_path):
    """When allow_ocr=False, image-only PDFs must not yield text (rejected path)."""
    pdf_path = tmp_path / "image_only.pdf"
    _write_image_pdf(pdf_path)

    text = read_document_text(pdf_path, allow_ocr=False)
    assert text == ""


def test_image_only_pdf_with_ocr_enabled_returns_text_or_empty(tmp_path):
    """When OCR deps are available, extract text from image-only PDF.
    If OCR deps are absent, still returns empty string (graceful)."""
    from knowledge.document_intake import _ocr_dependencies_available

    pdf_path = tmp_path / "image_only.pdf"
    _write_image_pdf(pdf_path)

    text = read_document_text(pdf_path, allow_ocr=True)
    if _ocr_dependencies_available():
        # Should produce some extractable text from the rendered image
        assert isinstance(text, str)
    else:
        assert text == ""


def test_build_document_intake_report_tracks_files(tmp_path):
    text_pdf = tmp_path / "text.pdf"
    image_pdf = tmp_path / "image.pdf"
    plain_text = tmp_path / "notes.txt"
    _write_text_pdf(text_pdf, "Management commentary")
    _write_image_pdf(image_pdf)
    plain_text.write_text("clean text notes", encoding="utf-8")

    report = build_document_intake_report([text_pdf, image_pdf, plain_text])

    assert report["status"] == "blocked"
    assert len(report["documents"]) == 3
    classifications = {item["classification"] for item in report["documents"]}
    assert "TEXT_PDF" in classifications
    assert "IMAGE_ONLY_PDF" in classifications
    assert any(item["classification"] == "TEXT_DOCUMENT" for item in report["documents"])


def test_document_ownership_infers_report_period_from_heading():
    check = infer_document_reporting_period(
        "Shaping the world of Digital Interactions Integrated Annual Report FY24",
        filename="tanla_fy23.pdf",
    )

    assert check["reporting_period"] == "fy24"


def test_source_period_ownership_flags_cross_year_report_text():
    check = assess_source_period_ownership(
        source_year="fy23",
        source_text="13 #TanlaIntegratedReport24 We announced the launch of MaaP and expect go live in FY25.",
    )

    assert check["status"] == "fail"
    assert check["expected_source_period"] == "fy23"
    assert check["inferred_reporting_period"] == "fy24"
    assert check["failure_class"] == "SOURCE_PERIOD_VS_TARGET_PERIOD_CONFLICT"


def _manifest(
    *,
    source_type: SourceType = SourceType.ANNUAL_REPORT,
    company_key: str | None = "sun_pharma",
    fiscal_year: str | None = "fy26",
    fiscal_quarter: FiscalQuarter | None = None,
    status: ClassificationStatus = ClassificationStatus.IDENTIFIED,
    original_filename: str = "8f2a7c91.pdf",
    storage_path: str = "incoming/8f2a7c91.pdf",
) -> DocumentIntakeManifest:
    evidence = [
        IdentityEvidence(
            field="company_identity.resolved_company_key",
            excerpt="Sun Pharmaceutical Industries Limited",
            confidence=ConfidenceLevel.HIGH,
            page=1,
            chunk_id="CHK-000001",
        )
    ]
    return DocumentIntakeManifest(
        document_id="sha256:abc123",
        file=FileIdentity(
            original_filename=original_filename,
            content_hash="sha256:abc123",
            mime_type="application/pdf",
            size_bytes=12345,
            storage_path=storage_path,
        ),
        company_identity=CompanyIdentity(
            resolved_company_key=company_key,
            detected_legal_name="Sun Pharmaceutical Industries Limited" if company_key else "",
            detected_display_name="Sun Pharma" if company_key else "",
            confidence=ConfidenceLevel.HIGH if company_key else ConfidenceLevel.UNKNOWN,
            evidence=evidence if company_key else [],
        ),
        document_identity=DocumentIdentity(
            source_type=source_type,
            document_subtype=source_type.value.lower(),
            confidence=ConfidenceLevel.HIGH if source_type != SourceType.UNKNOWN else ConfidenceLevel.UNKNOWN,
            evidence=[
                IdentityEvidence(
                    field="document_identity.source_type",
                    excerpt="Annual Report 2025-26",
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
        ),
        reporting_period=ReportingPeriod(
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter,
            period_start="2025-04-01" if fiscal_year else None,
            period_end="2026-03-31" if fiscal_year else None,
            confidence=ConfidenceLevel.HIGH if fiscal_year else ConfidenceLevel.UNKNOWN,
            evidence=[
                IdentityEvidence(
                    field="reporting_period.fiscal_year",
                    excerpt="Annual Report 2025-26",
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
        )
        if fiscal_year or fiscal_quarter
        else None,
        document_dates=DocumentDates(
            document_date="2026-05-20",
            publication_date="2026-06-15",
            filing_date="2026-06-16",
            event_date="2026-05-19",
        ),
        entity_scope=EntityScope.CONSOLIDATED,
        language="en",
        classification=ClassificationState(
            overall_confidence=ConfidenceLevel.HIGH if status == ClassificationStatus.IDENTIFIED else ConfidenceLevel.LOW,
            status=status,
            unresolved_fields=[] if status == ClassificationStatus.IDENTIFIED else ["company_identity.resolved_company_key"],
            warnings=[],
        ),
    )


def test_manifest_represents_annual_report_with_opaque_filename():
    manifest = _manifest(original_filename="8f2a7c91.pdf")

    assert validate_document_intake_manifest(manifest) == []
    assert manifest.document_identity.source_type == SourceType.ANNUAL_REPORT
    assert manifest.file.original_filename == "8f2a7c91.pdf"
    assert manifest.company_identity.resolved_company_key == "sun_pharma"


def test_manifest_represents_quarterly_report_with_fiscal_quarter():
    manifest = _manifest(source_type=SourceType.QUARTERLY_REPORT, fiscal_year="fy27", fiscal_quarter=FiscalQuarter.Q2)

    assert validate_document_intake_manifest(manifest) == []
    assert manifest.reporting_period.fiscal_quarter == FiscalQuarter.Q2


def test_manifest_requires_year_when_quarter_exists():
    manifest = _manifest(source_type=SourceType.QUARTERLY_REPORT, fiscal_year=None, fiscal_quarter=FiscalQuarter.Q1)

    assert "reporting_period.fiscal_year is required when fiscal_quarter is present" in validate_document_intake_manifest(manifest)


def test_manifest_represents_investor_presentation():
    manifest = _manifest(source_type=SourceType.INVESTOR_PRESENTATION, fiscal_year="fy26")

    assert validate_document_intake_manifest(manifest) == []


def test_manifest_represents_earnings_call_transcript():
    manifest = _manifest(source_type=SourceType.EARNINGS_CALL_TRANSCRIPT, fiscal_year="fy26", fiscal_quarter=FiscalQuarter.Q4)

    assert validate_document_intake_manifest(manifest) == []


def test_manifest_represents_exchange_filing_without_reporting_period():
    manifest = _manifest(source_type=SourceType.EXCHANGE_FILING, fiscal_year=None)

    assert validate_document_intake_manifest(manifest) == []
    assert manifest.reporting_period is None


def test_company_identity_can_be_unresolved():
    manifest = _manifest(company_key=None, fiscal_year=None, status=ClassificationStatus.UNIDENTIFIED)

    assert validate_document_intake_manifest(manifest) == []
    assert manifest.company_identity.resolved_company_key is None
    assert manifest.company_identity.confidence == ConfidenceLevel.UNKNOWN


def test_source_type_can_be_unknown_when_not_identified():
    manifest = _manifest(source_type=SourceType.UNKNOWN, company_key=None, fiscal_year=None, status=ClassificationStatus.UNIDENTIFIED)

    assert validate_document_intake_manifest(manifest) == []


def test_entity_scope_can_be_unknown():
    manifest = _manifest()
    manifest.entity_scope = EntityScope.UNKNOWN

    assert validate_document_intake_manifest(manifest) == []


def test_reporting_period_dates_are_distinct_from_publication_dates():
    manifest = _manifest(source_type=SourceType.QUARTERLY_REPORT, fiscal_year="fy27", fiscal_quarter=FiscalQuarter.Q2)

    payload = manifest.to_dict()
    assert payload["reporting_period"]["period_end"] == "2026-03-31"
    assert payload["document_dates"]["publication_date"] == "2026-06-15"
    assert payload["reporting_period"]["period_end"] != payload["document_dates"]["publication_date"]


def test_event_date_and_filing_date_are_distinct_fields():
    manifest = _manifest(source_type=SourceType.EXCHANGE_FILING, fiscal_year=None)

    assert manifest.to_dict()["document_dates"]["event_date"] == "2026-05-19"
    assert manifest.to_dict()["document_dates"]["filing_date"] == "2026-06-16"


def test_internal_company_key_remains_distinct_from_public_slug_or_filename():
    manifest = _manifest(original_filename="sun-pharma-fy26.pdf", storage_path="incoming/sun-pharma-fy26.pdf")

    legacy = manifest_to_legacy_pipeline_inputs(manifest)

    assert legacy.company == "sun_pharma"
    assert "sun-pharma" in legacy.source_file


def test_filename_does_not_determine_canonical_identity():
    manifest = _manifest(original_filename="8f2a7c91.pdf", storage_path="incoming/8f2a7c91.pdf")

    assert manifest.company_identity.resolved_company_key == "sun_pharma"
    assert "8f2a7c91" not in manifest.company_identity.resolved_company_key


def test_content_hash_and_field_level_confidence_retained():
    manifest = _manifest()
    payload = manifest.to_dict()

    assert payload["file"]["content_hash"] == "sha256:abc123"
    assert payload["company_identity"]["confidence"] == "HIGH"
    assert payload["reporting_period"]["confidence"] == "HIGH"


def test_identity_evidence_roundtrip_retained():
    manifest = _manifest()

    decoded = DocumentIntakeManifest.from_dict(manifest.to_dict())

    assert decoded.company_identity.evidence[0].excerpt == "Sun Pharmaceutical Industries Limited"
    assert decoded.company_identity.evidence[0].page == 1


def test_unresolved_fields_recorded_for_review_required_state():
    manifest = _manifest(company_key=None, fiscal_year=None, status=ClassificationStatus.REVIEW_REQUIRED)

    assert "company_identity.resolved_company_key" in manifest.classification.unresolved_fields
    assert validate_document_intake_manifest(manifest) == []


def test_identified_manifest_rejects_unknown_company_or_source_type():
    manifest = _manifest(company_key=None, fiscal_year="fy26", status=ClassificationStatus.IDENTIFIED)

    errors = validate_document_intake_manifest(manifest)

    assert "company_identity.resolved_company_key is required when status is IDENTIFIED" in errors
    assert "company_identity.confidence cannot be UNKNOWN when status is IDENTIFIED" in errors


def test_identified_unknown_source_type_is_invalid():
    manifest = _manifest(source_type=SourceType.UNKNOWN, fiscal_year="fy26", status=ClassificationStatus.IDENTIFIED)

    errors = validate_document_intake_manifest(manifest)

    assert "document_identity.source_type cannot be UNKNOWN when status is IDENTIFIED" in errors


def test_identified_periodic_report_requires_fiscal_year():
    manifest = _manifest(source_type=SourceType.ANNUAL_REPORT, fiscal_year=None, status=ClassificationStatus.IDENTIFIED)

    assert "reporting_period.fiscal_year is required for identified periodic reports" in validate_document_intake_manifest(manifest)


def test_reporting_period_start_after_end_rejected():
    manifest = _manifest()
    manifest.reporting_period.period_start = "2026-03-31"
    manifest.reporting_period.period_end = "2025-04-01"

    assert "reporting_period.period_start cannot be after period_end" in validate_document_intake_manifest(manifest)


def test_serialization_deserialization_roundtrip():
    manifest = _manifest(source_type=SourceType.INVESTOR_PRESENTATION, fiscal_year="fy26")

    decoded = DocumentIntakeManifest.from_dict(manifest.to_dict())

    assert decoded.to_dict() == manifest.to_dict()


def test_current_annual_report_metadata_adapts_to_legacy_pipeline_inputs(tmp_path):
    annual_report = tmp_path / "8f2a7c91.pdf"
    annual_report.write_bytes(b"%PDF-1.4 synthetic annual report")

    manifest = build_legacy_annual_report_manifest(
        company_key="sun_pharma",
        fiscal_year="fy26",
        source_file=annual_report,
        detected_legal_name="Sun Pharmaceutical Industries Limited",
    )
    legacy = manifest_to_legacy_pipeline_inputs(manifest)

    assert validate_document_intake_manifest(manifest) == []
    assert legacy.company == "sun_pharma"
    assert legacy.year == "fy26"
    assert legacy.source_file == str(annual_report)


def test_legacy_adapter_refuses_unidentified_or_non_annual_documents():
    unidentified = _manifest(company_key=None, fiscal_year=None, status=ClassificationStatus.UNIDENTIFIED)
    presentation = _manifest(source_type=SourceType.INVESTOR_PRESENTATION, fiscal_year="fy26")

    with pytest.raises(DocumentManifestResolutionError, match="not resolved enough"):
        manifest_to_legacy_pipeline_inputs(unidentified)
    with pytest.raises(DocumentManifestResolutionError, match="annual reports only"):
        manifest_to_legacy_pipeline_inputs(presentation)


def test_event_driven_document_does_not_force_fiscal_year():
    manifest = _manifest(source_type=SourceType.EXCHANGE_FILING, fiscal_year=None)

    assert validate_document_intake_manifest(manifest) == []
    assert manifest.reporting_period is None
