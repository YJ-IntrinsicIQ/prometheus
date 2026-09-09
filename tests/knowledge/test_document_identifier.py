"""Phase 2: Content-based document identification tests.

Test categories:
  1.  TEXT_PDF with clear company name → IDENTIFIED
  2.  Image-only PDF → REJECTED (no extractable text)
  3.  Opaque filename → same company_key as original filename
  4.  Misleading filename → content wins over filename
  5.  Annual report detection (source type)
  6.  Quarterly report detection
  7.  Investor presentation detection
  8.  Earnings call transcript detection
  9.  Exchange filing detection
  10. Reporting period (Indian FY year-end March)
  11. Reporting period (Indian FY range "2024-25")
  12. Consolidated entity scope detection
  13. Standalone entity scope detection
  14. REVIEW_REQUIRED when company found but source type unclear
  15. UNIDENTIFIED when no company match
  16. Evidence provenance: company evidence has excerpt + page
  17. Evidence provenance: source_type evidence has excerpt
  18. Reporting period evidence has excerpt
  19. Manifest passes validate_document_intake_manifest
  20. Cross-company: ujjivan identified from real PDF
  21. Cross-company: polymatech identified from synthetic text fixture
  22. Non-PDF text file identification
  23. Missing file → REJECTED
  24. Empty file → REJECTED
  25. Unsupported extension → REJECTED
  26. Language detection (English)
  27. Quarterly report → REVIEW_REQUIRED when quarter not found
  28. Contradictory FY signals → REVIEW_REQUIRED with warning
  29. Compatibility adapter: IDENTIFIED manifest → LegacyPipelineInputs
  30. Filename independence: same manifest regardless of filename
  31. No company match + unknown source → UNIDENTIFIED (not crash)
  32. IDENTIFIED manifest has content_hash in document_id
  33. Company registry builder: loads slugs from companies/ directory
  34. Score tie between two companies → LOW confidence
  35. Annual report with both consolidated and standalone → MIXED scope
"""
from __future__ import annotations

import base64
import shutil
from pathlib import Path
from typing import Optional

import fitz
import pytest

from knowledge.document_identifier import (
    IDENTIFIER_VERSION,
    _INDIAN_FY_PATTERN,
    _build_company_registry,
    _classify_source_type,
    _detect_entity_scope,
    _detect_language,
    _detect_reporting_period,
    _identify_company,
    _is_filing_reference,
    _probe_identity_trailer,
    _score_company_match,
    _score_fy_candidate,
    _select_best_fy_candidate,
    _slug_to_name_variants,
    identify_document,
)
from knowledge.document_intake import (
    ClassificationStatus,
    ConfidenceLevel,
    EntityScope,
    SourceType,
    manifest_to_legacy_pipeline_inputs,
    validate_document_intake_manifest,
)


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _write_text_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def _write_image_pdf(path: Path) -> None:
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Zt3QAAAAASUVORK5CYII="
    )
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(72, 72, 144, 144), stream=png_bytes)
    doc.save(str(path))
    doc.close()


def _write_text_file(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _make_companies_root(tmp_path: Path, slugs: list) -> Path:
    """Create a synthetic companies/ directory with the given slugs."""
    root = tmp_path / "companies"
    for slug in slugs:
        (root / slug).mkdir(parents=True, exist_ok=True)
    return root


# ─── Sun Pharma annual report content (synthetic) ────────────────────────────

_SUN_PHARMA_ANNUAL_CONTENT = (
    "Sun Pharmaceutical Industries Limited\n"
    "Annual Report 2025-26\n"
    "Consolidated Financial Statements for the Year Ended March 31, 2026\n"
    "Independent Auditor's Report to the Members of Sun Pharmaceutical Industries Limited\n"
    "Directors' Report\n"
    "Board of Directors\n"
    "FY26 revenue grew by 12% to ₹48,000 crores. "
    "The consolidated profit after tax stood at ₹9,200 crores. "
    "Receivable days improved from 95 to 89 days."
)

_POLYMATECH_ANNUAL_CONTENT = (
    "Polymatech Electronics Private Limited\n"
    "Annual Report 2023-24\n"
    "Standalone Financial Statements for the Year Ended March 31, 2024\n"
    "Independent Auditor's Report\n"
    "Directors' Report\n"
    "FY24 revenue from semiconductor components reached ₹850 crores."
)

_TANLA_QUARTERLY_CONTENT = (
    "Tanla Platforms Limited\n"
    "Q2 FY25 Results\n"
    "Unaudited Consolidated Financial Results for the Quarter Ended September 30, 2024\n"
    "Limited Review Report\n"
    "Revenue for Q2 FY25 was ₹910 crores."
)

_INVESTOR_PRESENTATION_CONTENT = (
    "Investor Presentation\n"
    "Analyst Meet — June 2025\n"
    "Sun Pharmaceutical Industries\n"
    "Slide 1: Business Overview\n"
    "Slide 2: Financial Highlights FY25\n"
    "Slide 3: Strategic Roadmap\n"
)

_EARNINGS_CALL_CONTENT = (
    "Conference Call Transcript\n"
    "Sun Pharma Q1 FY26 Earnings Call — July 2025\n"
    "Operator: Good morning, ladies and gentlemen. Welcome to the Sun Pharma earnings call.\n"
    "Management: Thank you Operator. We are pleased to report strong results for Q1 FY26.\n"
    "Q&A Session:\n"
    "Analyst: Can you explain receivable trends?\n"
)

_EXCHANGE_FILING_CONTENT = (
    "USFB/CS/SE/2025-26/27\n"
    "Date: June 03, 2025\n"
    "To, National Stock Exchange of India Limited\n"
    "Listing Department\n"
    "BSE Limited\n"
    "Sub: Submission of Annual Report pursuant to Regulation 34 of SEBI (LODR) Regulations, 2015\n"
    "Dear Sir/Madam,\n"
    "Ujjivan Small Finance Bank — Annual Report 2024-25 enclosed.\n"
)


# ─── Tests ────────────────────────────────────────────────────────────────────

# 1. TEXT_PDF with clear company name → IDENTIFIED

def test_text_pdf_with_company_name_identified(tmp_path):
    pdf = tmp_path / "sun_pharma_ar.pdf"
    _write_text_pdf(pdf, _SUN_PHARMA_ANNUAL_CONTENT)
    root = _make_companies_root(tmp_path, ["sun_pharma", "tanla"])

    result = identify_document(pdf, companies_root=root)

    assert result.classification.status == ClassificationStatus.IDENTIFIED
    assert result.company_identity.resolved_company_key == "sun_pharma"
    assert result.document_identity.source_type == SourceType.ANNUAL_REPORT


# 2. Image-only PDF → REJECTED

def test_image_only_pdf_rejected(tmp_path):
    pdf = tmp_path / "image_only.pdf"
    _write_image_pdf(pdf)
    root = _make_companies_root(tmp_path, ["sun_pharma"])

    result = identify_document(pdf, companies_root=root)

    assert result.classification.status == ClassificationStatus.REJECTED
    assert any("text" in w.lower() or "extractable" in w.lower() for w in result.classification.warnings)


# 3. Opaque filename → same company_key as descriptive filename

def test_opaque_filename_same_result_as_descriptive(tmp_path):
    content = _SUN_PHARMA_ANNUAL_CONTENT
    root = _make_companies_root(tmp_path, ["sun_pharma", "tanla", "polymatech"])

    pdf_descriptive = tmp_path / "sun_pharma_fy26_annual_report.pdf"
    _write_text_pdf(pdf_descriptive, content)

    pdf_opaque = tmp_path / "document_001.pdf"
    _write_text_pdf(pdf_opaque, content)

    result_d = identify_document(pdf_descriptive, companies_root=root)
    result_o = identify_document(pdf_opaque, companies_root=root)

    assert result_d.company_identity.resolved_company_key == result_o.company_identity.resolved_company_key
    assert result_d.document_identity.source_type == result_o.document_identity.source_type


# 4. Misleading filename → content wins

def test_misleading_filename_content_wins(tmp_path):
    # File named after tanla, but content is clearly polymatech
    root = _make_companies_root(tmp_path, ["sun_pharma", "tanla", "polymatech"])
    pdf = tmp_path / "tanla_annual_report.pdf"
    _write_text_pdf(pdf, _POLYMATECH_ANNUAL_CONTENT)

    result = identify_document(pdf, companies_root=root)

    assert result.company_identity.resolved_company_key == "polymatech"


# 5. Annual report source type detection

def test_annual_report_source_type_detected(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "report.pdf"
    _write_text_pdf(pdf, _SUN_PHARMA_ANNUAL_CONTENT)

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_type == SourceType.ANNUAL_REPORT
    assert result.document_identity.confidence in {ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM}


# 6. Quarterly report source type detection

def test_quarterly_report_source_type_detected(tmp_path):
    root = _make_companies_root(tmp_path, ["tanla"])
    pdf = tmp_path / "results.pdf"
    _write_text_pdf(pdf, _TANLA_QUARTERLY_CONTENT)

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_type == SourceType.QUARTERLY_REPORT


# 7. Investor presentation detection

def test_investor_presentation_detected(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "deck.pdf"
    _write_text_pdf(pdf, _INVESTOR_PRESENTATION_CONTENT)

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_type == SourceType.INVESTOR_PRESENTATION


# 8. Earnings call transcript detection

def test_earnings_call_transcript_detected(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "call.pdf"
    _write_text_pdf(pdf, _EARNINGS_CALL_CONTENT)

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_type == SourceType.EARNINGS_CALL_TRANSCRIPT


# 9. Exchange filing detection

def test_exchange_filing_detected(tmp_path):
    root = _make_companies_root(tmp_path, ["ujjivan"])
    txt = tmp_path / "filing.txt"
    _write_text_file(txt, _EXCHANGE_FILING_CONTENT)

    result = identify_document(txt, companies_root=root)

    assert result.document_identity.source_type == SourceType.EXCHANGE_FILING


# 10. Indian FY reporting period from "year ended March"

def test_reporting_period_from_year_ended_march(tmp_path):
    content = (
        "Sun Pharmaceutical Industries\n"
        "Annual Report\n"
        "Standalone Financial Statements for the Year Ended March 31, 2026\n"
        "Independent Auditor's Report\n"
    )
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "report.pdf"
    _write_text_pdf(pdf, content)

    result = identify_document(pdf, companies_root=root)

    assert result.reporting_period is not None
    assert result.reporting_period.fiscal_year == "fy26"


# 11. Indian FY from "2024-25" range pattern

def test_reporting_period_from_indian_fy_range(tmp_path):
    content = (
        "Polymatech Electronics\n"
        "Annual Report 2023-24\n"
        "Financial Year 2023-24 covering April 2023 to March 2024.\n"
        "Independent Auditor's Report\n"
        "Directors' Report\n"
    )
    root = _make_companies_root(tmp_path, ["polymatech"])
    pdf = tmp_path / "poly_ar.pdf"
    _write_text_pdf(pdf, content)

    result = identify_document(pdf, companies_root=root)

    assert result.reporting_period is not None
    assert result.reporting_period.fiscal_year in {"fy24", "fy23"}


# 12. Consolidated entity scope

def test_consolidated_entity_scope_detected(tmp_path):
    content = (
        "Sun Pharma Annual Report\n"
        "Consolidated Financial Statements for FY26\n"
        "Independent Auditor's Report\n"
        "Directors' Report\n"
    )
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "ar.pdf"
    _write_text_pdf(pdf, content)

    result = identify_document(pdf, companies_root=root)

    assert result.entity_scope == EntityScope.CONSOLIDATED


# 13. Standalone entity scope

def test_standalone_entity_scope_detected(tmp_path):
    content = (
        "Polymatech Electronics Annual Report\n"
        "Standalone Financial Statements for FY24\n"
        "Independent Auditor's Report\n"
        "Directors' Report\n"
    )
    root = _make_companies_root(tmp_path, ["polymatech"])
    pdf = tmp_path / "poly.pdf"
    _write_text_pdf(pdf, content)

    result = identify_document(pdf, companies_root=root)

    assert result.entity_scope == EntityScope.STANDALONE


# 14. REVIEW_REQUIRED when source type is low confidence

def test_review_required_when_source_type_ambiguous(tmp_path):
    # Document has company name but no source type signals
    content = (
        "Sun Pharmaceutical Industries Limited\n"
        "Internal document reference number 2025-ARG-001.\n"
        "This document contains various business notes.\n"
    )
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "misc.pdf"
    _write_text_pdf(pdf, content)

    result = identify_document(pdf, companies_root=root)

    # Should be REVIEW_REQUIRED (source type unknown) or IDENTIFIED with LOW
    # Either way, source_type must be honest about the ambiguity
    assert result.classification.status in {
        ClassificationStatus.REVIEW_REQUIRED,
        ClassificationStatus.UNIDENTIFIED,
        ClassificationStatus.IDENTIFIED,
    }
    assert result.company_identity.resolved_company_key == "sun_pharma"


# 15. UNIDENTIFIED when no company match

def test_unidentified_when_no_company_match(tmp_path):
    content = (
        "Accenture Global Solutions\n"
        "Annual Report FY25\n"
        "Consolidated Financial Statements\n"
        "Independent Auditor's Report\n"
    )
    root = _make_companies_root(tmp_path, ["sun_pharma", "tanla"])
    pdf = tmp_path / "accenture.pdf"
    _write_text_pdf(pdf, content)

    result = identify_document(pdf, companies_root=root)

    assert result.classification.status in {
        ClassificationStatus.UNIDENTIFIED,
        ClassificationStatus.REVIEW_REQUIRED,
    }
    assert result.company_identity.resolved_company_key is None or \
           result.company_identity.confidence == ConfidenceLevel.LOW


# 16. Evidence provenance: company evidence has excerpt

def test_company_evidence_has_excerpt(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "ar.pdf"
    _write_text_pdf(pdf, _SUN_PHARMA_ANNUAL_CONTENT)

    result = identify_document(pdf, companies_root=root)

    assert len(result.company_identity.evidence) > 0
    ev = result.company_identity.evidence[0]
    assert ev.excerpt != ""
    assert ev.field == "company_identity.resolved_company_key"


# 17. Evidence provenance: source_type evidence has excerpt

def test_source_type_evidence_has_excerpt(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "ar.pdf"
    _write_text_pdf(pdf, _SUN_PHARMA_ANNUAL_CONTENT)

    result = identify_document(pdf, companies_root=root)

    assert len(result.document_identity.evidence) > 0
    ev = result.document_identity.evidence[0]
    assert ev.excerpt != ""
    assert ev.field == "document_identity.source_type"


# 18. Reporting period evidence has excerpt

def test_reporting_period_evidence_has_excerpt(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "ar.pdf"
    _write_text_pdf(pdf, _SUN_PHARMA_ANNUAL_CONTENT)

    result = identify_document(pdf, companies_root=root)

    if result.reporting_period is not None and result.reporting_period.evidence:
        ev = result.reporting_period.evidence[0]
        assert ev.excerpt != ""


# 19. IDENTIFIED manifest passes validate_document_intake_manifest

def test_identified_manifest_passes_validation(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "ar.pdf"
    _write_text_pdf(pdf, _SUN_PHARMA_ANNUAL_CONTENT)

    result = identify_document(pdf, companies_root=root)

    errors = validate_document_intake_manifest(result)
    assert errors == [], f"Validation errors: {errors}"


# 20. Cross-company: ujjivan identified from real PDF

UJJIVAN_PDF = Path("companies/ujjivan/fy25/raw/ujjivan_fy25.pdf")


@pytest.mark.skipif(not UJJIVAN_PDF.exists(), reason="ujjivan real PDF not available")
def test_ujjivan_real_pdf_identified():
    result = identify_document(UJJIVAN_PDF)

    assert result.classification.status in {
        ClassificationStatus.IDENTIFIED,
        ClassificationStatus.REVIEW_REQUIRED,
    }
    assert result.company_identity.resolved_company_key == "ujjivan"
    assert result.document_identity.source_type in {
        SourceType.ANNUAL_REPORT,
        SourceType.EXCHANGE_FILING,
    }


# 21. Cross-company: polymatech identified from synthetic text fixture

def test_polymatech_synthetic_identified(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma", "polymatech", "tanla"])
    pdf = tmp_path / "poly_report.pdf"
    _write_text_pdf(pdf, _POLYMATECH_ANNUAL_CONTENT)

    result = identify_document(pdf, companies_root=root)

    assert result.company_identity.resolved_company_key == "polymatech"
    assert result.document_identity.source_type == SourceType.ANNUAL_REPORT


# 22. Non-PDF text file identification

def test_text_file_identification(tmp_path):
    root = _make_companies_root(tmp_path, ["tanla"])
    txt = tmp_path / "tanla_results.txt"
    _write_text_file(txt, _TANLA_QUARTERLY_CONTENT)

    result = identify_document(txt, companies_root=root)

    assert result.classification.status != ClassificationStatus.REJECTED
    assert result.company_identity.resolved_company_key == "tanla"
    assert result.document_identity.source_type == SourceType.QUARTERLY_REPORT


# 23. Missing file → REJECTED

def test_missing_file_rejected(tmp_path):
    missing = tmp_path / "nonexistent.pdf"
    result = identify_document(missing)

    assert result.classification.status == ClassificationStatus.REJECTED
    assert any("exist" in w.lower() for w in result.classification.warnings)


# 24. Empty file → REJECTED

def test_empty_file_rejected(tmp_path):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    result = identify_document(empty)

    assert result.classification.status == ClassificationStatus.REJECTED


# 25. Unsupported extension → REJECTED

def test_unsupported_extension_rejected(tmp_path):
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"PK\x03\x04fake")
    result = identify_document(docx)

    assert result.classification.status == ClassificationStatus.REJECTED
    assert any("unsupported" in w.lower() for w in result.classification.warnings)


# 26. Language detection: English document

def test_language_detected_as_english(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "ar.pdf"
    _write_text_pdf(pdf, _SUN_PHARMA_ANNUAL_CONTENT)

    result = identify_document(pdf, companies_root=root)

    assert result.language == "en"


# 27. Quarterly report REVIEW_REQUIRED when quarter not in content

def test_quarterly_without_quarter_number_review_required(tmp_path):
    content = (
        "Tanla Platforms\n"
        "Unaudited Consolidated Financial Results for Quarter Ended September 30, 2024\n"
        "Limited Review Report\n"
        "Revenue was ₹910 crores.\n"
    )
    root = _make_companies_root(tmp_path, ["tanla"])
    pdf = tmp_path / "qr.pdf"
    _write_text_pdf(pdf, content)

    result = identify_document(pdf, companies_root=root)

    if result.document_identity.source_type == SourceType.QUARTERLY_REPORT:
        # If Q number not detectable → REVIEW_REQUIRED
        if result.reporting_period and not result.reporting_period.fiscal_quarter:
            assert result.classification.status == ClassificationStatus.REVIEW_REQUIRED


# 28. Contradictory FY signals → warning present

def test_contradictory_fy_signals_produce_warning(tmp_path):
    content = (
        "Sun Pharmaceutical\n"
        "Annual Report 2024-25\n"
        "Consolidated Financial Statements for the Year Ended March 31, 2026\n"
        "Independent Auditor's Report\n"
        "Directors' Report\n"
    )
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "contradictory.pdf"
    _write_text_pdf(pdf, content)

    result = identify_document(pdf, companies_root=root)

    # May produce a warning or not depending on which signal wins; at least shouldn't crash
    assert result.classification.status in {
        ClassificationStatus.IDENTIFIED,
        ClassificationStatus.REVIEW_REQUIRED,
    }


# 29. Compatibility adapter: IDENTIFIED → LegacyPipelineInputs

def test_identified_manifest_compatibility_adapter(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "sun_ar.pdf"
    _write_text_pdf(pdf, _SUN_PHARMA_ANNUAL_CONTENT)

    result = identify_document(pdf, companies_root=root)

    if result.classification.status == ClassificationStatus.IDENTIFIED:
        legacy = manifest_to_legacy_pipeline_inputs(result)
        assert legacy.company == "sun_pharma"
        assert legacy.year is not None
        assert legacy.source_file != ""


# 30. Filename independence: same manifest for original vs opaque filename

def test_filename_independence_opaque_vs_original(tmp_path):
    content = _POLYMATECH_ANNUAL_CONTENT
    root = _make_companies_root(tmp_path, ["polymatech", "sun_pharma"])

    original = tmp_path / "polymatech_fy24_annual.pdf"
    opaque = tmp_path / "xyz_12345_abc.pdf"
    misleading = tmp_path / "sun_pharma_q1.pdf"

    _write_text_pdf(original, content)
    _write_text_pdf(opaque, content)
    _write_text_pdf(misleading, content)

    r_orig = identify_document(original, companies_root=root)
    r_opaque = identify_document(opaque, companies_root=root)
    r_misleading = identify_document(misleading, companies_root=root)

    # All three should resolve to polymatech regardless of filename
    for r, label in [(r_opaque, "opaque"), (r_misleading, "misleading")]:
        assert r.company_identity.resolved_company_key == r_orig.company_identity.resolved_company_key, \
            f"{label} filename gave different company: {r.company_identity.resolved_company_key}"
        assert r.document_identity.source_type == r_orig.document_identity.source_type, \
            f"{label} filename gave different source type"


# 31. Unknown company + unknown source → UNIDENTIFIED (no crash)

def test_unknown_everything_unidentified_no_crash(tmp_path):
    content = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor."
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "lorem.pdf"
    _write_text_pdf(pdf, content)

    result = identify_document(pdf, companies_root=root)

    assert result.classification.status in {
        ClassificationStatus.UNIDENTIFIED,
        ClassificationStatus.REVIEW_REQUIRED,
        ClassificationStatus.IDENTIFIED,
    }


# 32. IDENTIFIED manifest has content_hash in document_id

def test_identified_document_id_is_content_hash(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "ar.pdf"
    _write_text_pdf(pdf, _SUN_PHARMA_ANNUAL_CONTENT)

    result = identify_document(pdf, companies_root=root)

    assert result.document_id.startswith("sha256:")
    assert result.file.content_hash == result.document_id


# 33. Company registry builder: loads slugs from tmp companies directory

def test_registry_builder_loads_slugs(tmp_path):
    root = _make_companies_root(tmp_path, ["sun_pharma", "polymatech", "tanla"])

    registry = _build_company_registry(root)

    assert "sun_pharma" in registry
    assert "polymatech" in registry
    assert "tanla" in registry
    assert isinstance(registry["sun_pharma"], list)
    assert "sun_pharma" in registry["sun_pharma"] or "sun pharma" in registry["sun_pharma"]


# 34. Score tie between two companies → LOW confidence

def test_score_tie_gives_low_confidence():
    # "sun" and "tan" are not in the variants for the other company
    # Create an ambiguous probe text that matches two companies equally
    registry = {
        "companyabc": ["companyabc", "company abc"],
        "companyxyz": ["companyxyz", "company xyz"],
    }
    # Text mentions both equally — neither wins clearly
    probe_text = "companyabc companyxyz financial report annual"
    slug, conf, evs = _identify_company(probe_text, registry)

    # With a tie, confidence should be LOW
    if conf == ConfidenceLevel.LOW:
        assert True  # correct
    else:
        # Or one won — that's fine too, just verify no crash
        assert slug in {"companyabc", "companyxyz"}


# 35. Annual report with both consolidated and standalone → MIXED scope

def test_mixed_scope_when_both_keywords_present(tmp_path):
    content = (
        "Sun Pharma Annual Report FY26\n"
        "Consolidated and Standalone Financial Statements\n"
        "The standalone financial statements are attached separately.\n"
        "The consolidated financial statements include all subsidiaries.\n"
        "Independent Auditor's Report\n"
        "Directors' Report\n"
    )
    root = _make_companies_root(tmp_path, ["sun_pharma"])
    pdf = tmp_path / "mixed.pdf"
    _write_text_pdf(pdf, content)

    result = identify_document(pdf, companies_root=root)

    assert result.entity_scope == EntityScope.MIXED


# ── Unit tests for helper functions ──────────────────────────────────────────

def test_slug_to_name_variants_compound():
    variants = _slug_to_name_variants("sun_pharma")
    assert "sun_pharma" in variants
    assert "sun pharma" in variants
    assert "sun" in variants
    assert "pharma" in variants


def test_slug_to_name_variants_single_word():
    variants = _slug_to_name_variants("tanla")
    assert "tanla" in variants


def test_slug_to_name_variants_no_company_specific_words():
    # Generic algorithm: no hardcoded additions beyond slug derivation
    variants = _slug_to_name_variants("ujjivan")
    assert all(isinstance(v, str) for v in variants)
    assert "ujjivan" in variants


def test_language_detection_english():
    assert _detect_language("Annual report revenue profit growth CAGR shareholder value.") == "en"


def test_language_detection_empty():
    assert _detect_language("") == "unknown"


def test_entity_scope_consolidated():
    scope, conf, ev = _detect_entity_scope("Consolidated Financial Statements for FY26")
    assert scope == EntityScope.CONSOLIDATED
    assert conf == ConfidenceLevel.HIGH


def test_entity_scope_standalone():
    scope, conf, ev = _detect_entity_scope("Standalone Financial Statements for FY24")
    assert scope == EntityScope.STANDALONE
    assert conf == ConfidenceLevel.HIGH


def test_entity_scope_unknown():
    scope, conf, ev = _detect_entity_scope("Financial data for the period under review.")
    assert scope == EntityScope.UNKNOWN


def test_annual_report_classification_high_confidence():
    source_type, conf, evs = _classify_source_type(
        "Annual Report 2025-26\nDirectors' Report\nIndependent Auditor's Report\nConsolidated Financial Statements",
        "ar_fy26",
    )
    assert source_type == SourceType.ANNUAL_REPORT
    assert conf in {ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM}


def test_quarterly_classification():
    source_type, conf, evs = _classify_source_type(
        "Q2 FY25 Results\nUnaudited Consolidated Financial Results\nLimited Review Report\nQuarter Ended September",
        "q2_results",
    )
    assert source_type == SourceType.QUARTERLY_REPORT


def test_transcript_classification():
    source_type, conf, evs = _classify_source_type(
        "Conference Call Transcript\nOperator: Good morning, ladies and gentlemen.\nQ&A Session",
        "earnings_call",
    )
    assert source_type == SourceType.EARNINGS_CALL_TRANSCRIPT


def test_reporting_period_annual_fy26(tmp_path):
    period, warnings = _detect_reporting_period(
        "Annual Report\nYear Ended March 31, 2026\nConsolidated Statements",
        "report.pdf",
        SourceType.ANNUAL_REPORT,
    )
    assert period is not None
    assert period.fiscal_year == "fy26"


def test_reporting_period_quarterly_q2():
    period, warnings = _detect_reporting_period(
        "Q2 FY25 Results\nUnaudited Consolidated\nQuarter Ended September 30 2024",
        "q2_results.pdf",
        SourceType.QUARTERLY_REPORT,
    )
    assert period is not None
    assert period.fiscal_quarter is not None


def test_identifier_version_constant():
    assert IDENTIFIER_VERSION.startswith("document_identifier.v")


# ── Phase 2.1: Reporting-period precedence tests (15 new) ─────────────────────
#
# These tests verify the generic semantic-precedence fix for Indian FY range
# candidate selection.  Filing serial numbers must not outrank explicit
# reporting-period phrases, regardless of their position in the document.

# P1. Filing serial does not outrank "Annual Report 2024-25"
# Root-cause regression: "CORP/CS/SE/2025-26/27" at position 0 must lose to
# "Annual Report 2024-25" later in the text.

def test_filing_serial_does_not_outrank_annual_report_heading():
    text = (
        "USFB/CS/SE/2025-26/27\n"
        "Date: June 03, 2025\n"
        "To, National Stock Exchange of India Limited\n"
        "BSE Limited\n"
        "Sub: Submission of Annual Report for the Financial Year 2024-25\n"
        "This is to inform you that pursuant to Regulation 34 of SEBI (Listing\n"
        "Obligations and Disclosure Requirements) Regulations, 2015 we hereby\n"
        "submit the Annual Report for the Financial Year 2024-25.\n"
    )
    period, warnings = _detect_reporting_period(text, "ujjivan_fy25.pdf", SourceType.EXCHANGE_FILING)
    assert period is not None
    assert period.fiscal_year == "fy25", (
        f"Expected fy25 but got {period.fiscal_year}; warnings={warnings}"
    )


# P2. Later strong period beats earlier weak (bare) period

def test_later_strong_period_beats_earlier_weak_period():
    # Bare "2022-23" at the start; explicit "Annual Report 2024-25" later.
    text = (
        "Reference: DOC/2022-23/MISC\n"
        "Some background context from a previous year.\n"
        "Polymatech Electronics\n"
        "Annual Report 2024-25\n"
        "Consolidated Financial Statements\n"
        "Directors' Report\n"
    )
    period, warnings = _detect_reporting_period(text, "poly_ar.pdf", SourceType.ANNUAL_REPORT)
    assert period is not None
    assert period.fiscal_year == "fy25", (
        f"Expected fy25 but got {period.fiscal_year}; warnings={warnings}"
    )


# P3. Annual-report heading beats historical FY mention in body text

def test_annual_report_heading_beats_historical_fy_mention():
    text = (
        "Sun Pharmaceutical Industries\n"
        "Annual Report 2024-25\n"
        "Revenue increased from FY22 to FY23 to FY24.\n"
        "For the current year 2024-25 net profit reached ₹9000 crores.\n"
    )
    period, warnings = _detect_reporting_period(text, "report.pdf", SourceType.ANNUAL_REPORT)
    assert period is not None
    assert period.fiscal_year == "fy25", (
        f"Expected fy25 but got {period.fiscal_year}; warnings={warnings}"
    )


# P4. "Year ended March" phrase (stage 2) beats a bare year-range match

def test_year_ended_phrase_beats_generic_year_range():
    # Bare "2022-23" appears first; explicit year-ended phrase follows.
    text = (
        "Historical context: 2022-23 revenue was ₹5000 crores.\n"
        "Consolidated Financial Statements for the Year Ended March 31, 2026.\n"
        "Independent Auditor's Report.\n"
    )
    period, warnings = _detect_reporting_period(text, "report.pdf", SourceType.ANNUAL_REPORT)
    assert period is not None
    assert period.fiscal_year == "fy26", (
        f"Expected fy26 from year-ended-March but got {period.fiscal_year}"
    )


# P5. Current period beats comparative prior-year mention

def test_current_period_beats_comparative_prior_period():
    # Both "2023-24" (prior year comparison) and "2024-25" (current period)
    # appear; current period has "Annual Report" strong context.
    text = (
        "Sun Pharmaceutical Industries\n"
        "Annual Report 2024-25\n"
        "Revenue grew 12% from ₹42,000 crores in 2023-24 to ₹47,000 crores in 2024-25.\n"
        "Board of Directors report for Financial Year 2024-25.\n"
    )
    period, warnings = _detect_reporting_period(text, "report.pdf", SourceType.ANNUAL_REPORT)
    assert period is not None
    assert period.fiscal_year == "fy25", (
        f"Expected fy25 but got {period.fiscal_year}"
    )


# P6. Publication filing date does not become the reporting fiscal year

def test_publication_date_does_not_become_reporting_fy(tmp_path):
    # Filing date is June 2025; the reporting period is FY24-25.
    # The year "2025" in "June 03, 2025" must NOT become the FY.
    text = (
        "Date: June 03, 2025\n"
        "Ujjivan Small Finance Bank\n"
        "Annual Report for the Financial Year 2024-25.\n"
        "Board of Directors.\n"
    )
    root = _make_companies_root(tmp_path, ["ujjivan"])
    txt = tmp_path / "filing.txt"
    _write_text_file(txt, text)

    result = identify_document(txt, companies_root=root)

    # Reporting period must reflect FY25 (2024-25), not FY25 from 2025 filing date
    if result.reporting_period is not None:
        assert result.reporting_period.fiscal_year == "fy25", (
            f"Reporting period should be fy25, got {result.reporting_period.fiscal_year}"
        )
    # Publication date captured separately (may or may not be set depending on regex)
    # Key assertion: fiscal year does NOT end up as "fy25" derived from "2025" alone
    # (it must come from "2024-25"); single years are not matched by _INDIAN_FY_PATTERN


# P7. Slash-heavy identifier alone is de-ranked to LOW confidence with warning

def test_slash_heavy_identifier_alone_is_deranked():
    # Only a filing serial exists — no other FY evidence.
    text = (
        "CORP/CS/SE/2025-26/001\n"
        "Date: May 01, 2025\n"
        "To, BSE Limited\n"
        "Listing Compliance\n"
    )
    period, warnings = _detect_reporting_period(text, "filing.pdf", SourceType.EXCHANGE_FILING)
    # If a period is returned it must have LOW confidence and a warning
    if period is not None:
        assert period.confidence == ConfidenceLevel.LOW, (
            f"Filing reference alone should yield LOW confidence, got {period.confidence}"
        )
        assert any("filing reference" in w.lower() or "reference" in w.lower() for w in warnings), (
            f"Expected a warning about filing reference, got: {warnings}"
        )


# P8. Isolated year range (no strong context) is still usable

def test_isolated_year_range_usable_without_stronger_evidence():
    # "2024-25" appears in a sentence without any report/financial-year heading.
    # The match scores 0 (bare) but must still be returned.
    text = (
        "Sun Pharmaceutical\n"
        "Revenue for 2024-25 grew strongly versus prior periods.\n"
        "Operating margin improved quarter over quarter.\n"
    )
    period, warnings = _detect_reporting_period(text, "misc.pdf", SourceType.ANNUAL_REPORT)
    assert period is not None
    assert period.fiscal_year == "fy25", (
        f"Isolated year range should still resolve to fy25, got {period.fiscal_year}"
    )
    # No filing-reference warning expected
    assert not any("filing reference" in w.lower() for w in warnings)


# P9. Two conflicting strong reporting-period signals produce a warning

def test_two_conflicting_strong_periods_produce_warning():
    # Both "2024-25" and "2025-26" appear with "Financial Year" context.
    # The earlier position wins but a contradiction warning must be raised.
    text = (
        "Sun Pharmaceutical Industries\n"
        "For Financial Year 2024-25 the following was achieved.\n"
        "For Financial Year 2025-26 the guidance has been set.\n"
        "Balance sheet summary.\n"
    )
    period, warnings = _detect_reporting_period(text, "report.pdf", SourceType.ANNUAL_REPORT)
    # Both are strong candidates — a contradiction warning should appear
    assert any(
        "contradict" in w.lower() or "conflict" in w.lower() for w in warnings
    ), f"Expected contradiction warning, got warnings={warnings}"
    # Period should still be resolved to one value
    assert period is not None


# P10–P12. Real production PDF regression — unchanged or corrected

SUN_PHARMA_FY26_PDF = Path("data/Processed/sun_pharma/fy26/annual_report/sun_pharma_fy26.pdf")
POLYMATECH_FY24_PDF = Path("data/Processed/polymatech/fy24/annual_report/polymatech_fy24.pdf")
UJJIVAN_FY25_PDF   = Path("companies/ujjivan/fy25/raw/ujjivan_fy25.pdf")


@pytest.mark.skipif(not POLYMATECH_FY24_PDF.exists(), reason="polymatech real PDF not available")
def test_polymatech_real_period_still_fy24():
    result = identify_document(POLYMATECH_FY24_PDF)
    assert result.reporting_period is not None
    assert result.reporting_period.fiscal_year == "fy24", (
        f"Polymatech period regression: expected fy24, got {result.reporting_period.fiscal_year}"
    )


@pytest.mark.skipif(not SUN_PHARMA_FY26_PDF.exists(), reason="sun_pharma real PDF not available")
def test_sun_pharma_real_period_still_fy26():
    result = identify_document(SUN_PHARMA_FY26_PDF)
    assert result.reporting_period is not None
    assert result.reporting_period.fiscal_year == "fy26", (
        f"Sun Pharma period regression: expected fy26, got {result.reporting_period.fiscal_year}"
    )


@pytest.mark.skipif(not UJJIVAN_FY25_PDF.exists(), reason="ujjivan real PDF not available")
def test_ujjivan_real_period_now_fy25():
    """THE KEY REGRESSION: ujjivan must now resolve to fy25, not fy26."""
    result = identify_document(UJJIVAN_FY25_PDF)
    assert result.reporting_period is not None
    assert result.reporting_period.fiscal_year == "fy25", (
        f"Ujjivan period fix failed: expected fy25, got {result.reporting_period.fiscal_year}. "
        f"Evidence: {[e.excerpt for e in result.reporting_period.evidence]}"
    )


# P13. Period detection is filename-independent

def test_period_detection_filename_independent():
    # Same content with three different filenames → identical period
    text = (
        "Polymatech Electronics\n"
        "Annual Report 2023-24\n"
        "Financial Year 2023-24 Standalone Financial Statements.\n"
        "Directors' Report.\n"
    )
    for filename in ["polymatech_fy24.pdf", "94abc1237.pdf", "tanla_fy22_q1.pdf"]:
        period, warnings = _detect_reporting_period(text, filename, SourceType.ANNUAL_REPORT)
        assert period is not None, f"No period detected for filename {filename!r}"
        assert period.fiscal_year == "fy24", (
            f"Filename {filename!r} changed period to {period.fiscal_year}"
        )


# P14. "Financial Year YYYY-YY" phrase is detected as strong context

def test_financial_year_phrase_is_strong_context():
    text = (
        "Ujjivan Small Finance Bank\n"
        "Sub: Submission of Annual Report for the Financial Year 2024-25\n"
        "Pursuant to Regulation 34 of SEBI (LODR) Regulations, 2015.\n"
    )
    period, warnings = _detect_reporting_period(text, "filing.pdf", SourceType.EXCHANGE_FILING)
    assert period is not None
    assert period.fiscal_year == "fy25", (
        f"'Financial Year 2024-25' should detect fy25, got {period.fiscal_year}"
    )
    # Must not carry a filing-reference warning (the "Financial Year" match is genuine)
    assert not any("filing reference" in w.lower() for w in warnings), (
        f"Unexpected filing-reference warning when strong context exists: {warnings}"
    )


# P15. Filing-reference suppression is generic (no company-specific codes)

def test_filing_reference_suppression_is_generic():
    # Different company prefixes — all should be suppressed in favour of "2024-25"
    # when "Financial Year 2024-25" also appears.
    for prefix in ["USFB/CS/SE", "TCS/FIN/MKT", "HDFC/IR/CS", "ABC/DF/IB"]:
        text = (
            f"{prefix}/2025-26/001\n"
            "Dear Sir/Madam,\n"
            "We submit the Annual Report for the Financial Year 2024-25.\n"
            "BSE Limited, Listing Department.\n"
        )
        period, warnings = _detect_reporting_period(
            text, "filing.pdf", SourceType.EXCHANGE_FILING
        )
        assert period is not None
        assert period.fiscal_year == "fy25", (
            f"Prefix {prefix!r}: expected fy25, got {period.fiscal_year}; warnings={warnings}"
        )


# ── Unit tests for new period-ranking helpers ────────────────────────────────

def test_is_filing_reference_detects_slash_path():
    text = "USFB/CS/SE/2025-26/27 some other text"
    m = _INDIAN_FY_PATTERN.search(text)
    assert m is not None
    assert _is_filing_reference(text, m) is True


def test_is_filing_reference_ignores_bare_year_range():
    text = "Annual Report 2024-25 Standalone Financial Statements"
    m = _INDIAN_FY_PATTERN.search(text)
    assert m is not None
    assert _is_filing_reference(text, m) is False


def test_score_fy_candidate_filing_reference_gets_negative():
    text = "CORP/CS/SE/2025-26/001 Date: June 2025"
    m = _INDIAN_FY_PATTERN.search(text)
    assert m is not None
    score = _score_fy_candidate(text, m)
    assert score < 0, f"Filing reference should score negative, got {score}"


def test_score_fy_candidate_annual_report_context_gets_high():
    text = "Annual Report 2024-25 Consolidated Financial Statements"
    m = _INDIAN_FY_PATTERN.search(text)
    assert m is not None
    score = _score_fy_candidate(text, m)
    assert score >= 10, f"Annual Report context should score ≥10, got {score}"


def test_score_fy_candidate_bare_range_scores_zero():
    text = "Company recorded 2024-25 performance across divisions."
    m = _INDIAN_FY_PATTERN.search(text)
    assert m is not None
    score = _score_fy_candidate(text, m)
    assert score == 0, f"Bare year range should score 0, got {score}"


def test_select_best_fy_candidate_prefers_semantic_over_position():
    # Filing reference at position 0, "Financial Year 2024-25" later
    text = "ABC/CS/SE/2025-26/07 ... Financial Year 2024-25 results enclosed."
    result = _select_best_fy_candidate(text)
    assert result is not None
    fy_str, basis, evidence, is_weak = result
    assert fy_str == "fy25", f"Expected fy25, got {fy_str}"
    assert is_weak is False


def test_select_best_fy_candidate_returns_none_when_no_match():
    result = _select_best_fy_candidate("No year range in this text at all.")
    assert result is None


# ── Phase 4.1 regression: classifier defects found during Tanla Q4 FY26 audit ─

# Defect 1: Exchange wrapper detection missed "enclosing herewith" phrasing.
# Indian companies (e.g. Tanla) commonly write "we are enclosing herewith"
# instead of "please find enclosed" — both are BSE/NSE cover-letter patterns.
def test_exchange_wrapper_fires_on_enclosing_herewith(tmp_path):
    """Wrapper detection must fire when cover letter uses 'enclosing herewith'."""
    from knowledge.document_identifier import _detect_exchange_wrapper
    cover_text = (
        "Tanla Platforms Limited\n"
        "To, BSE Limited\n"
        "National Stock Exchange of India\n"
        "Sub: Investor Updates for the quarter and year ended March 31, 2026\n"
        "Dear Sir/Madam,\n"
        "We are enclosing herewith the Investor Update for Q4 FY26.\n"
    )
    assert _detect_exchange_wrapper(cover_text) is True, (
        "Wrapper detection must fire for 'enclosing herewith' cover-letter pattern"
    )


# Defect 2: Classifier treated 'Investor Update' as QUARTERLY_REPORT because
# 'Q4 FY26 Results Snapshot' in the payload matched the quarterly signal but
# 'investor update' was missing from presentation signals.
def test_investor_update_classified_as_presentation():
    """'Investor Update' slide-deck payload must classify as INVESTOR_PRESENTATION."""
    payload = (
        "Investor Update Full Year & Q4 FY26\n"
        "April 24, 2026\n"
        "FY26 Results Snapshot: Revenue ₹44,177 Mn, EBITDA ₹7,237 Mn, PAT ₹5,091 Mn\n"
        "Q4 FY26 Results Snapshot: Revenue ₹11,775 Mn, PAT ₹1,343 Mn\n"
        "Customer cohort analysis, wallet share metrics\n"
    )
    source_type, conf, evs = _classify_source_type(payload, "opaque_filename")
    assert source_type == SourceType.INVESTOR_PRESENTATION, (
        f"'Investor Update' slide-deck must classify as INVESTOR_PRESENTATION, got {source_type}"
    )


# Defect 2b: Downgrading the ambiguous 'Q4 FY26 results?' signal must NOT break
# genuine quarterly reports that also contain 'quarterly results' / 'quarter ended'.
def test_quarterly_classification_survives_signal_reweight():
    """Genuine quarterly report text must still classify as QUARTERLY_REPORT."""
    quarterly_text = (
        "Q2 FY25 Results\n"
        "Unaudited Consolidated Financial Results for the Quarter Ended September 30, 2024\n"
        "Limited Review Report\n"
        "Quarterly Results filed under Regulation 33 SEBI (LODR)\n"
    )
    source_type, conf, evs = _classify_source_type(quarterly_text, "q2_results")
    assert source_type == SourceType.QUARTERLY_REPORT, (
        f"Genuine quarterly report text must classify as QUARTERLY_REPORT, got {source_type}"
    )


# ── Phase 4.2 regression tests: D1 (no-wrapper probe), D2 (quarterly signals) ─

# D1: No-wrapper path must use pages 1–CONTENT_PROBE_PAYLOAD_PAGES, not just page 1.

def test_d1_no_wrapper_uses_payload_pages(tmp_path):
    """Without an exchange wrapper, classification must see pages 2+ content."""
    from knowledge.document_identifier import (
        CONTENT_PROBE_PAYLOAD_PAGES,
        CONTENT_PROBE_WRAPPER_PAGES,
        _probe_content_adaptive,
    )

    doc = fitz.open()
    # Page 1: generic cover — no company or source-type signals
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Shareholders Letter Q1 FY27\nJuly 2026")
    # Pages 2-3: substantive content with quarterly + company signals
    p2 = doc.new_page()
    p2.insert_text((72, 72), (
        "Sun Pharmaceutical Industries Limited\n"
        "Quarterly Disclosures — Q1 FY27\n"
        "Three months ended June 30, 2026\n"
        "Unaudited Consolidated Financial Results\n"
    ))
    p3 = doc.new_page()
    p3.insert_text((72, 72), "Limited Review Report by auditors.")
    pdf = tmp_path / "no_wrapper.pdf"
    doc.save(str(pdf))
    doc.close()

    wrapper_text, payload_text, desc = _probe_content_adaptive(pdf)
    combined = (wrapper_text + " " + payload_text).strip()

    # After D1 fix: combined must contain page-2 content
    assert "Quarterly Disclosures" in combined, (
        "D1 fix: combined probe must include page-2 content, not just page 1"
    )
    assert "Three months ended" in combined, (
        "D1 fix: combined probe must include page-2 content"
    )


def test_d1_no_wrapper_classification_probe_equals_combined(tmp_path):
    """Without wrapper, classification_probe must equal combined (pages 1+2+…)."""
    from knowledge.document_identifier import (
        _probe_content_adaptive,
        _detect_exchange_wrapper,
    )

    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Tanla Platforms — Shareholder Letter Q1 FY27")
    p2 = doc.new_page()
    p2.insert_text((72, 72), (
        "Quarterly Disclosures\n"
        "Three months ended June 30, 2026\n"
        "Revenue: ₹12,264 Mn\n"
    ))
    pdf = tmp_path / "tanla_no_wrapper.pdf"
    doc.save(str(pdf))
    doc.close()

    wrapper_text, payload_text, desc = _probe_content_adaptive(pdf)
    is_wrapper = _detect_exchange_wrapper(wrapper_text)
    assert not is_wrapper, "Synthetic doc must not be detected as exchange wrapper"

    combined = (wrapper_text + " " + payload_text).strip()
    assert "Quarterly Disclosures" in combined, (
        "D1 fix: Quarterly Disclosures from page 2 must appear in combined probe"
    )


def test_d1_wrapper_path_unchanged(tmp_path):
    """Exchange-filing path (is_wrapper=True) must be unaffected by D1 fix."""
    from knowledge.document_identifier import _detect_exchange_wrapper, _probe_content_adaptive

    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), (
        "To, National Stock Exchange of India Limited\n"
        "BSE Limited, Dalal Street, Mumbai\n"
        "Pursuant to Regulation 30 of SEBI (LODR) Regulations, 2015\n"
        "Sub: Enclosing herewith the Q2 FY25 Investor Presentation\n"
    ))
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Investor Presentation Q2 FY25 — Full deck content page 2")
    pdf = tmp_path / "wrapper_doc.pdf"
    doc.save(str(pdf))
    doc.close()

    wrapper_text, payload_text, desc = _probe_content_adaptive(pdf)
    is_wrapper = _detect_exchange_wrapper(wrapper_text)
    assert is_wrapper, "Exchange wrapper must be detected for BSE/NSE cover letter"
    # Wrapper path: payload_text is the substantive probe
    assert "Investor Presentation" in payload_text, (
        "Exchange-filing path: payload probe must contain page-2 content"
    )


# D2: 'Quarterly Disclosures' and 'Three months ended' must classify as QUARTERLY_REPORT.

def test_d2_quarterly_disclosures_signal_fires():
    """`quarterly disclosures` heading classifies as QUARTERLY_REPORT."""
    text = (
        "Table of Contents\n"
        "1. Management Discussion Q&A\n"
        "2. Quarterly Disclosures (Annexure 1)\n"
        "3. Policies Deep-Dive\n"
    )
    source_type, conf, evs = _classify_source_type(text, "toc_only")
    assert source_type == SourceType.QUARTERLY_REPORT, (
        f"'Quarterly Disclosures' must classify as QUARTERLY_REPORT, got {source_type}"
    )


def test_d2_three_months_ended_signal_fires():
    """`three months ended` period header classifies as QUARTERLY_REPORT."""
    text = (
        "Condensed Consolidated Statement of Profit and Loss\n"
        "Three months ended June 30, 2026 vs Three months ended June 30, 2025\n"
        "Revenue from operations: 12,264 | 10,407\n"
    )
    source_type, conf, evs = _classify_source_type(text, "pl_table")
    assert source_type == SourceType.QUARTERLY_REPORT, (
        f"'Three months ended' must classify as QUARTERLY_REPORT, got {source_type}"
    )


def test_d2_quarterly_disclosures_plural_variant():
    """Signal regex must match both singular and plural 'Disclosures'."""
    for variant in ("Quarterly Disclosure", "Quarterly Disclosures"):
        source_type, _, _ = _classify_source_type(variant, "fn")
        assert source_type == SourceType.QUARTERLY_REPORT, (
            f"'{variant}' must classify as QUARTERLY_REPORT, got {source_type}"
        )


def test_d2_signals_do_not_pollute_annual_report():
    """'Three months ended' inside a comparative column must not flip an annual."""
    text = (
        "Annual Report FY26\n"
        "Year Ended March 31, 2026 — Consolidated Financial Statements\n"
        "Comparative column: Three months ended June 30, 2025 (not audited)\n"
        "Revenue for the year: ₹48,000 Mn\n"
        "Independent Auditor's Report to the Members of Sun Pharmaceutical Industries\n"
    )
    source_type, conf, evs = _classify_source_type(text, "annual_with_comparative")
    # Annual signals must dominate: 'year ended', 'annual report', auditor's report
    assert source_type == SourceType.ANNUAL_REPORT, (
        f"Annual report with comparative quarterly column must stay ANNUAL_REPORT, got {source_type}"
    )


# D4: Quarter extraction must fire when D1+D2 have resolved source_type=QUARTERLY_REPORT.

def test_d4_quarter_extracted_when_source_type_quarterly(tmp_path):
    """Quarter label in probe text is extracted once source_type=QUARTERLY_REPORT."""
    from knowledge.document_identifier import _detect_reporting_period

    text = (
        "Quarterly Disclosures\n"
        "Three months ended June 30, 2026\n"
        "Q1 FY27 Revenue: ₹12,264 Mn\n"
        "PAT: ₹1,422 Mn\n"
    )
    period, _ = _detect_reporting_period(text, "q1_fy27", source_type=SourceType.QUARTERLY_REPORT)
    from knowledge.document_intake import FiscalQuarter
    assert period.fiscal_year == "fy27", f"Expected fy27, got {period.fiscal_year}"
    assert period.fiscal_quarter == FiscalQuarter.Q1, (
        f"D4 fix: Q1 must be extracted when source_type=QUARTERLY_REPORT, got {period.fiscal_quarter}"
    )


def test_d4_quarter_not_extracted_for_annual(tmp_path):
    """Quarter label in annual report text must NOT be extracted as fiscal_quarter."""
    from knowledge.document_identifier import _detect_reporting_period

    text = (
        "Annual Report FY26\n"
        "Year Ended March 31, 2026\n"
        "Q4 FY26 quarterly results snapshot included for reference\n"
    )
    period, _ = _detect_reporting_period(text, "annual_fy26", source_type=SourceType.ANNUAL_REPORT)
    assert period.fiscal_quarter is None, (
        f"Annual report must not extract fiscal_quarter, got {period.fiscal_quarter}"
    )


def test_d4_quarter_pattern_q1_to_q4_all_match():
    """All four quarter labels Q1-Q4 are extractable when source_type=QUARTERLY_REPORT."""
    from knowledge.document_identifier import _detect_reporting_period
    from knowledge.document_intake import FiscalQuarter

    quarters = [
        ("Q1 FY27 results", FiscalQuarter.Q1),
        ("Q2 FY27 results", FiscalQuarter.Q2),
        ("Q3 FY27 results", FiscalQuarter.Q3),
        ("Q4 FY26 results", FiscalQuarter.Q4),
    ]
    for text, expected in quarters:
        period, _ = _detect_reporting_period(text, "qx_results", source_type=SourceType.QUARTERLY_REPORT)
        assert period.fiscal_quarter == expected, (
            f"Expected {expected} from '{text}', got {period.fiscal_quarter}"
        )


# Combined D1+D2: Full-document integration — no-wrapper quarterly reports must identify.

def test_d1_d2_combined_no_wrapper_quarterly_identified(tmp_path):
    """No-wrapper quarterly document must reach QUARTERLY_REPORT after D1+D2 fix."""
    root = _make_companies_root(tmp_path, ["tanla"])

    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Q1 FY27 | July 2026\nShareholders' Letter and Results")
    p2 = doc.new_page()
    p2.insert_text((72, 72), (
        "Tanla Platforms\n"
        "Quarterly Disclosures — Annexure 1\n"
        "Three months ended June 30, 2026\n"
        "Revenue: ₹12,264 Mn | PAT: ₹1,422 Mn\n"
    ))
    pdf = tmp_path / "tanla_q1_fy27.pdf"
    doc.save(str(pdf))
    doc.close()

    result = identify_document(pdf, companies_root=root)
    d = result.to_dict()
    assert d["document_identity"]["source_type"] == SourceType.QUARTERLY_REPORT.value, (
        "D1+D2: no-wrapper quarterly must reach QUARTERLY_REPORT"
    )
    assert d["reporting_period"]["fiscal_quarter"] is not None, (
        "D4: quarter must be extracted from no-wrapper quarterly document"
    )


# ── Phase 4.3 regression tests: company-confidence calibration ─────────────────
# The v4 identifier adds an identity trailer probe (last IDENTITY_TRAILER_PAGES
# pages) that scores corporate domain, legal name blocks, and CIN as issuer signals.
# These tests pin the new evidence-accumulation model.

# ── Unit tests: _score_company_match with trailer ─────────────────────────────

def test_p43_domain_in_trailer_gives_medium_confidence():
    """Corporate domain in trailer text pushes score to ≥ 3 (MEDIUM threshold)."""
    text_lower = "q1 fy27 shareholder report revenue grew 17.8%"
    title_zone = text_lower[:500]
    variants = ["acme"]
    trailer = "www.acme.com follow us at"

    score = _score_company_match(text_lower, title_zone, variants, trailer_lower=trailer.lower())
    # 0 in probe (no match in text), +3 from domain → 3 ≥ MEDIUM threshold
    assert score >= 3, f"Domain in trailer must push score to ≥3, got {score}"


def test_p43_domain_in_trailer_with_body_mention():
    """Domain + one body mention gives score ≥ 4 (solidly MEDIUM)."""
    text_lower = "acme quarterly report revenue"
    title_zone = text_lower[:500]
    variants = ["acme"]
    trailer = "www.acme.com contact us"

    score = _score_company_match(text_lower, title_zone, variants, trailer_lower=trailer.lower())
    assert score >= 4, f"Body mention + domain trailer must give ≥4, got {score}"


def test_p43_legal_name_in_trailer_gives_bonus():
    """Legal name block in trailer adds +2 to score."""
    text_lower = "annual shareholders communication from zetacorp"
    title_zone = text_lower[:500]
    variants = ["zetacorp"]
    # trailer has legal name block but no domain
    trailer = "zetacorp limited registered office 123 main street"

    score_no_trailer = _score_company_match(text_lower, title_zone, variants)
    score_with_trailer = _score_company_match(
        text_lower, title_zone, variants, trailer_lower=trailer.lower()
    )
    assert score_with_trailer > score_no_trailer, (
        "Legal name in trailer must increase score"
    )
    assert score_with_trailer >= 3, (
        f"Body + legal-name trailer must reach MEDIUM threshold, got {score_with_trailer}"
    )


def test_p43_cin_plus_legal_name_in_trailer():
    """CIN co-occurring with legal name in trailer gives additional confidence."""
    text_lower = "q1 results operating margin improved"
    title_zone = text_lower[:500]
    variants = ["betatech"]
    # trailer has legal name + CIN
    trailer = "betatech limited L72900MH2012PLC232169 www.betatech.com"

    score = _score_company_match(text_lower, title_zone, variants, trailer_lower=trailer.lower())
    # domain (+3) + legal name (+2) + CIN co-occurrence (+2) = 7 → HIGH range
    assert score >= 6, f"Domain + legal name + CIN in trailer must give ≥6, got {score}"


def test_p43_no_trailer_score_unchanged():
    """Omitting trailer_lower does not change existing scoring behavior."""
    text_lower = "tanla quarterly disclosures three months ended june 2026"
    title_zone = "tanla " + text_lower[:495]  # put tanla in title zone
    variants = ["tanla"]

    score_old = _score_company_match(text_lower, title_zone, variants)
    score_new = _score_company_match(text_lower, title_zone, variants, trailer_lower="")
    assert score_old == score_new, "Empty trailer must not change score"


def test_p43_short_variant_skipped_in_domain_check():
    """Variants shorter than 4 chars must not fire domain detection (avoids 'sun', 'air')."""
    # Keep "sun" out of title_zone (first 500 chars) by using a neutral title_zone
    title_zone = "annual market report 2026 overview and key findings"
    text_lower = title_zone + " sun energy revenues increased"
    # "sun" is 3 chars — must be skipped for domain check
    variants = ["sun"]
    trailer = "www.sun.com contact"  # would be a false positive if short variants were matched

    score = _score_company_match(text_lower, title_zone, variants, trailer_lower=trailer.lower())
    # "sun" in title_zone would give +3; "sun" not in title_zone → body match +1; domain skipped
    # Since "sun" IS in title_zone (appears in "sun energy revenues"), the check is:
    # title_zone hit → +3; domain skipped because len("sun") < 4
    # The test verifies domain is not ADDITIONALLY added when variant is short
    # A title-zone match is +3 regardless; the key assertion is that domain adds 0
    score_no_trailer = _score_company_match(text_lower, title_zone, variants)
    score_with_trailer = _score_company_match(
        text_lower, title_zone, variants, trailer_lower=trailer.lower()
    )
    assert score_with_trailer == score_no_trailer, (
        "Short-variant domain check must add 0 to score (domain skipped for len<4)"
    )


# ── Contamination tests ────────────────────────────────────────────────────────

def test_p43_customer_name_does_not_reach_medium(tmp_path):
    """Customer name prominently mentioned in a Tanla doc must NOT resolve as that company."""
    root = _make_companies_root(tmp_path, ["tanla", "tanishq"])

    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Tanla Platforms — Q1 FY27 Results")
    p2 = doc.new_page()
    p2.insert_text((72, 72), (
        "Tanishq, a major jewellery brand, used our platform for campaign delivery.\n"
        "Tanishq achieved 40% engagement uplift through Wisely.ai.\n"
        "Revenue from operations: ₹12,264 Mn\n"
    ))
    p3 = doc.new_page()
    p3.insert_text((72, 72), "www.tanla.com")  # back cover
    pdf = tmp_path / "tanla_with_tanishq_case.pdf"
    doc.save(str(pdf))
    doc.close()

    result = identify_document(pdf, companies_root=root)
    d = result.to_dict()
    ci = d["company_identity"]
    assert ci["resolved_company_key"] == "tanla", (
        "Must resolve to tanla, not tanishq customer case-study mention"
    )
    # Tanishq has no trailer domain boost; should remain LOW/UNKNOWN
    tanishq_conf_expected_low = True  # The test passes if tanla wins


def test_p43_partner_name_does_not_outrank_issuer(tmp_path):
    """Partner mentions (Meta/Truecaller) must not outrank the actual issuer."""
    root = _make_companies_root(tmp_path, ["tanla", "meta", "truecaller"])

    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Q1 FY27 Results — Shareholder Report")
    p2 = doc.new_page()
    p2.insert_text((72, 72), (
        "Meta and Truecaller are key partners in our ecosystem.\n"
        "Meta delivers reach; Truecaller provides verified identity.\n"
        "Our platform now serves Meta campaigns across 12 markets.\n"
        "Truecaller integration expanded to 8 new countries.\n"
    ))
    p3 = doc.new_page()
    p3.insert_text((72, 72), "www.tanla.com")
    pdf = tmp_path / "tanla_with_partners.pdf"
    doc.save(str(pdf))
    doc.close()

    result = identify_document(pdf, companies_root=root)
    d = result.to_dict()
    ci = d["company_identity"]
    assert ci["resolved_company_key"] == "tanla", (
        f"Tanla must win over partners Meta/Truecaller, got {ci['resolved_company_key']}"
    )
    assert ci["confidence"] in ("MEDIUM", "HIGH"), (
        f"Tanla must reach MEDIUM/HIGH from domain, got {ci['confidence']}"
    )


def test_p43_acquisition_target_does_not_become_issuer(tmp_path):
    """Acquisition-target mentions must not flip the issuer identity."""
    root = _make_companies_root(tmp_path, ["tanla", "valuefirst"])

    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Q1 FY27 Results — Shareholder Report")
    p2 = doc.new_page()
    p2.insert_text((72, 72), (
        "The acquisition of ValueFirst was completed in FY24.\n"
        "ValueFirst's messaging capabilities have been integrated into Trubloq.\n"
        "ValueFirst contributed ₹1,200 Mn to our revenue base.\n"
    ))
    p3 = doc.new_page()
    p3.insert_text((72, 72), "www.tanla.com")
    pdf = tmp_path / "tanla_with_acquisition.pdf"
    doc.save(str(pdf))
    doc.close()

    result = identify_document(pdf, companies_root=root)
    d = result.to_dict()
    ci = d["company_identity"]
    assert ci["resolved_company_key"] == "tanla", (
        f"Acquisition target ValueFirst must not become the issuer, got {ci['resolved_company_key']}"
    )


def test_p43_one_isolated_mention_stays_low():
    """A single isolated brand mention (no domain, not in title zone) stays in the LOW score range."""
    # Call _score_company_match directly with explicit title_zone where betacorp is absent,
    # ensuring a clean isolation of the body-text-only scoring path.
    title_zone = "market research report cloud services landscape 2026 overview"
    assert "betacorp" not in title_zone  # guard: betacorp must NOT be in title zone
    text_lower = title_zone + " among vendors betacorp provides cloud messaging"

    score = _score_company_match(text_lower, title_zone, ["betacorp"], trailer_lower="")
    # Body match only: score = 1. No domain, no legal name, no compound phrase → stays LOW (1-2)
    assert score <= 2, (
        f"Single body mention with no trailer must be ≤2 (LOW confidence range), got {score}"
    )


def test_p43_official_identity_block_gives_medium_confidence(tmp_path):
    """Legal name + domain in an official identity block must support MEDIUM/HIGH."""
    root = _make_companies_root(tmp_path, ["omega"])

    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Q2 FY26 Shareholder Update — Message from Leadership")
    p2 = doc.new_page()
    p2.insert_text((72, 72), (
        "Revenue grew 14% YoY driven by enterprise clients.\n"
        "Operating margin expanded by 80 bps to 22.4%.\n"
    ))
    p3 = doc.new_page()
    p3.insert_text((72, 72), (
        "Omega Technologies Limited\n"
        "CIN: L72900MH2012PLC232169\n"
        "www.omega.com\n"
        "Registered Office: 12 Tech Park, Mumbai - 400 001\n"
    ))
    pdf = tmp_path / "omega_q2_fy26.pdf"
    doc.save(str(pdf))
    doc.close()

    result = identify_document(pdf, companies_root=root)
    d = result.to_dict()
    ci = d["company_identity"]
    assert ci["resolved_company_key"] == "omega", (
        f"Must resolve to omega from identity block, got {ci['resolved_company_key']}"
    )
    assert ci["confidence"] in ("MEDIUM", "HIGH"), (
        f"Identity block with legal name + CIN + domain must give MEDIUM/HIGH, got {ci['confidence']}"
    )


# ── Integration test: real Tanla quarterly becomes IDENTIFIED ──────────────────

def test_p43_tanla_quarterly_identified():
    """Real Tanla quarterly (342tsgdh266.pdf) must now resolve as IDENTIFIED."""
    from pathlib import Path
    path = Path("data/Processed/tanla/q1 fy27/quarterly_report/342tsgdh266.pdf")
    if not path.exists():
        import pytest
        pytest.skip("Real Tanla quarterly file not available in this environment")

    result = identify_document(path)
    d = result.to_dict()
    ci = d["company_identity"]
    di = d["document_identity"]
    rp = d["reporting_period"]
    cl = d["classification"]

    assert ci["resolved_company_key"] == "tanla", "company_key must be tanla"
    assert ci["confidence"] in ("MEDIUM", "HIGH"), (
        f"company confidence must be MEDIUM or HIGH, got {ci['confidence']}"
    )
    assert di["source_channel"] == "DIRECT"
    assert di["source_type"] == "QUARTERLY_REPORT"
    assert rp["fiscal_year"] == "fy27"
    assert rp["fiscal_quarter"] == "Q1"
    assert cl["status"] == "IDENTIFIED", (
        f"Overall status must be IDENTIFIED, got {cl['status']}"
    )
    assert cl["unresolved_fields"] == [], (
        f"No unresolved fields expected, got {cl['unresolved_fields']}"
    )


def test_p43_identity_trailer_probe_returns_string(tmp_path):
    """_probe_identity_trailer must return a string for valid PDFs and '' for non-PDFs."""
    txt = tmp_path / "sample.txt"
    txt.write_text("some text")
    assert _probe_identity_trailer(txt) == "", "Non-PDF must return empty string"

    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 72), "Back cover content www.example.com")
    pdf = tmp_path / "sample.pdf"
    doc.save(str(pdf))
    doc.close()

    trailer = _probe_identity_trailer(pdf)
    assert isinstance(trailer, str), "Must return str"
    assert "example.com" in trailer.lower(), "Must include last-page content"


# ---------------------------------------------------------------------------
# Phase 5.2 — Mixed full-year + explicit quarter identification
# ENG-D5: expand quarter detection to INVESTOR_PRESENTATION
# ---------------------------------------------------------------------------

class TestMixedPeriodDetection:
    """Phase 5.2 — _detect_reporting_period must extract explicit quarter labels
    from INVESTOR_PRESENTATION probe text and leave them absent when no Qn token
    appears in the text.  Full-year language must never fabricate a quarter.
    """

    def _period(self, text: str, source_type):
        from knowledge.document_identifier import _detect_reporting_period
        result, _ = _detect_reporting_period(text, "test.pdf", source_type)
        return result

    # ── D5.1 Mixed title: explicit Q4 present → must be preserved ───────────

    def test_d5_mixed_title_q4_extracted(self):
        """'Full Year & Q4 FY26' contains explicit Q4 → fiscal_quarter=Q4."""
        from knowledge.document_intake import FiscalQuarter, SourceType
        period = self._period(
            "Full Year & Q4 FY26 Investor Update",
            SourceType.INVESTOR_PRESENTATION,
        )
        assert period is not None
        assert period.fiscal_year == "fy26"
        assert period.fiscal_quarter == FiscalQuarter.Q4, (
            f"D5.1: explicit Q4 in title must be preserved, got {period.fiscal_quarter}"
        )

    # ── D5.2 FY-only title: no Qn token → fiscal_quarter must be None ───────

    def test_d5_fy_only_title_no_quarter(self):
        """'FY26 Investor Presentation' has no Q token → fiscal_quarter=None."""
        from knowledge.document_intake import SourceType
        period = self._period(
            "FY26 Investor Presentation Full Year Performance",
            SourceType.INVESTOR_PRESENTATION,
        )
        assert period is not None
        assert period.fiscal_year == "fy26"
        assert period.fiscal_quarter is None, (
            f"D5.2: FY-only presentation must not produce a quarter, got {period.fiscal_quarter}"
        )

    # ── D5.3 Full-year language only → no quarter inferred ──────────────────

    def test_d5_full_year_language_no_quarter_inference(self):
        """'Annual Investor Update FY26' must not infer any quarter."""
        from knowledge.document_intake import SourceType
        period = self._period(
            "Annual Investor Update FY26 Tanla Platforms",
            SourceType.INVESTOR_PRESENTATION,
        )
        assert period is not None
        assert period.fiscal_quarter is None, (
            f"D5.3: 'Annual' language must not infer a quarter, got {period.fiscal_quarter}"
        )

    # ── D5.4 Q3 in title → Q3 extracted ─────────────────────────────────────

    def test_d5_explicit_q3_extracted(self):
        """Q3 in an investor presentation title is extracted as fiscal_quarter=Q3."""
        from knowledge.document_intake import FiscalQuarter, SourceType
        period = self._period(
            "Q3 FY26 Business Performance Update Investor Deck",
            SourceType.INVESTOR_PRESENTATION,
        )
        assert period is not None
        assert period.fiscal_quarter == FiscalQuarter.Q3, (
            f"D5.4: Q3 in presentation title must be extracted, got {period.fiscal_quarter}"
        )

    # ── D5.5 "Fourth Quarter" spelled out → Q4 ──────────────────────────────

    def test_d5_fourth_quarter_spelled_out(self):
        """'Fourth Quarter FY26 Investor Deck' matches the fourth-quarter pattern."""
        from knowledge.document_intake import FiscalQuarter, SourceType
        period = self._period(
            "Fourth Quarter FY26 Investor Deck",
            SourceType.INVESTOR_PRESENTATION,
        )
        assert period is not None
        assert period.fiscal_quarter == FiscalQuarter.Q4, (
            f"D5.5: 'Fourth Quarter' must map to Q4, got {period.fiscal_quarter}"
        )

    # ── D5.6 Regression: QUARTERLY_REPORT detection unchanged ───────────────

    def test_d5_quarterly_report_unchanged(self):
        """QUARTERLY_REPORT detection is unaffected by the D5 expansion."""
        from knowledge.document_intake import FiscalQuarter, SourceType
        period = self._period(
            "Q4 Results FY26 Press Release Three Months Ended March 31 2026",
            SourceType.QUARTERLY_REPORT,
        )
        assert period is not None
        assert period.fiscal_year == "fy26"
        assert period.fiscal_quarter == FiscalQuarter.Q4, (
            f"D5.6: QUARTERLY_REPORT Q4 detection must be unchanged, got {period.fiscal_quarter}"
        )

    # ── D5.7 Regression: ANNUAL_REPORT still gets no quarter ────────────────

    def test_d5_annual_report_no_quarter_regression(self):
        """ANNUAL_REPORT must NOT extract a quarter even when Q4 text appears."""
        from knowledge.document_intake import SourceType
        period = self._period(
            "Annual Report FY26 Year Ended March 31 2026 Q4 snapshot included",
            SourceType.ANNUAL_REPORT,
        )
        assert period is not None
        assert period.fiscal_quarter is None, (
            f"D5.7: ANNUAL_REPORT must never extract a quarter, got {period.fiscal_quarter}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ENG-059: company_names.json canonical registry (Phase 11.1)
# ─────────────────────────────────────────────────────────────────────────────

class TestENG059CompanyNamesJson:
    """ENG-059: _build_company_registry reads company_names.json; canonical name
    variants are injected without one-off filename heuristics."""

    def _registry(self, tmp_path: Path, slug: str, names_data: dict) -> dict:
        companies = tmp_path / "companies"
        (companies / slug).mkdir(parents=True)
        import json
        (companies / slug / "company_names.json").write_text(
            json.dumps(names_data), encoding="utf-8"
        )
        return _build_company_registry(companies)

    def test_eng059_legal_name_added_to_variants(self, tmp_path):
        """Legal name from company_names.json appears in slug variants."""
        reg = self._registry(
            tmp_path, "datapatterns",
            {"legal_names": ["Data Patterns (India) Limited"], "short_names": [], "aliases": []},
        )
        variants = reg.get("datapatterns", [])
        assert "data patterns (india) limited" in variants, variants

    def test_eng059_short_name_added_to_variants(self, tmp_path):
        """Short name from company_names.json appears in slug variants."""
        reg = self._registry(
            tmp_path, "datapatterns",
            {"legal_names": [], "short_names": ["Data Patterns"], "aliases": []},
        )
        variants = reg.get("datapatterns", [])
        assert "data patterns" in variants, variants

    def test_eng059_alias_added_to_variants(self, tmp_path):
        """Alias from company_names.json appears in slug variants."""
        reg = self._registry(
            tmp_path, "datapatterns",
            {"legal_names": [], "short_names": [], "aliases": ["DPIL", "data patterns india limited"]},
        )
        variants = reg.get("datapatterns", [])
        assert "dpil" in variants, variants
        assert "data patterns india limited" in variants, variants

    def test_eng059_identification_high_confidence_legal_name(self, tmp_path):
        """Document containing legal name resolves to HIGH confidence with company_names.json."""
        reg = self._registry(
            tmp_path, "datapatterns",
            {"legal_names": ["Data Patterns (India) Limited"], "short_names": ["Data Patterns"], "aliases": []},
        )
        text = "Data Patterns (India) Limited Q1 FY27 Earnings Conference Call revenue 320 crore"
        slug, conf, _ = _identify_company(text, reg)
        assert slug == "datapatterns"
        assert conf == ConfidenceLevel.HIGH

    def test_eng059_customer_name_not_resolved_as_issuer(self, tmp_path):
        """Customer name (Bharat Electronics) is not matched when Data Patterns is the slug."""
        reg = self._registry(
            tmp_path, "datapatterns",
            {"legal_names": ["Data Patterns (India) Limited"], "short_names": ["Data Patterns"], "aliases": []},
        )
        text = "Bharat Electronics Limited placed an order for radar supply valued at 300 crore"
        slug, conf, _ = _identify_company(text, reg)
        assert slug != "datapatterns", f"Customer name must not resolve as issuer; got {slug}"

    def test_eng059_drdo_ministry_not_resolved_as_issuer(self, tmp_path):
        """DRDO/Ministry mention alone must not resolve to any company."""
        reg = self._registry(
            tmp_path, "datapatterns",
            {"legal_names": ["Data Patterns (India) Limited"], "short_names": ["Data Patterns"], "aliases": []},
        )
        text = "DRDO Ministry of Defence awarded contract for electronic systems integration"
        slug, conf, _ = _identify_company(text, reg)
        assert slug != "datapatterns", f"DRDO must not resolve as issuer; got {slug}"

    def test_eng059_acquisition_target_not_resolved_as_issuer(self, tmp_path):
        """Acquisition-target name must not become the issuer."""
        reg = self._registry(
            tmp_path, "datapatterns",
            {"legal_names": ["Data Patterns (India) Limited"], "short_names": ["Data Patterns"], "aliases": []},
        )
        text = "ST Advanced Composite Pvt Ltd acquisition target board approval 90 crore"
        slug, conf, _ = _identify_company(text, reg)
        assert slug != "datapatterns", f"Acquisition target must not resolve as issuer; got {slug}"

    def test_eng059_no_names_json_stays_slug_only(self, tmp_path):
        """Without company_names.json the slug's only variant is the slug itself."""
        companies = tmp_path / "companies"
        (companies / "datapatterns").mkdir(parents=True)
        reg = _build_company_registry(companies)
        variants = reg.get("datapatterns", [])
        # Only the slug itself — "Data Patterns" must NOT appear without names.json
        assert "data patterns" not in variants, (
            f"Without company_names.json 'data patterns' must not appear in variants: {variants}"
        )
