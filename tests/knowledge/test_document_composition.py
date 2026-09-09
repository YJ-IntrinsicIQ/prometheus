"""Phase 3.3: Two-axis document composition tests.

Validates the split of source_type (payload) vs source_channel (distribution envelope).

Regression fixtures (C01-C10):
  C01  Direct annual report → DIRECT channel, ANNUAL_REPORT payload
  C02  Exchange-filing annual report → EXCHANGE_FILING channel, ANNUAL_REPORT payload
  C03  Exchange-filing quarterly results → EXCHANGE_FILING channel, QUARTERLY_REPORT payload
  C04  Exchange-filing investor presentation → EXCHANGE_FILING channel, INVESTOR_PRESENTATION payload
  C05  Direct quarterly report → DIRECT channel, QUARTERLY_REPORT payload
  C06  Direct investor presentation → DIRECT channel, INVESTOR_PRESENTATION payload
  C07  Direct transcript → DIRECT channel, EARNINGS_CALL_TRANSCRIPT payload
  C08  No meaningful signals → DIRECT channel, UNKNOWN payload
  C09  LTTS 437-page annual report (real PDF, guarded) → EXCHANGE_FILING, ANNUAL_REPORT, REVIEW_REQUIRED
  C10  LTTS 17-page press release (real PDF, guarded) → EXCHANGE_FILING, status=REVIEW_REQUIRED

Adversarial tests (A01-A13):
  A01  Exchange-filing wrapper filename but DIRECT content → channel from content, not filename
  A02  Exchange-filing wrapper with no recognizable payload → channel=EXCHANGE_FILING, payload=UNKNOWN
  A03  Single-page exchange filing → wrapper detected, no payload pages → graceful fallback
  A04  Company name in document text but not in registry → detected_legal_name preserved, REVIEW_REQUIRED
  A05  No company name anywhere → UNIDENTIFIED (not REVIEW_REQUIRED)
  A06  Regulation 34 deep in document (not first pages) → NOT detected as wrapper
  A07  Strong annual-report signals in first pages → no false-positive wrapper
  A08  Polymatech regression — registered company still routes ROUTABLE
  A09  Router uses payload type (source_type), not source_channel, for routing
  A10  REVIEW_REQUIRED manifest preserves detected_legal_name
  A11  Wrapper threshold not tripped by single signal
  A12  source_channel serialised in to_dict / round-tripped via from_dict
  A13  Backward compat: old manifest dict without source_channel parses cleanly
"""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from knowledge.document_identifier import (
    _detect_exchange_wrapper,
    _extract_legal_company_name,
    identify_document,
)
from knowledge.document_intake import (
    ClassificationStatus,
    CompanyIdentity,
    ConfidenceLevel,
    DocumentIdentity,
    SourceChannel,
    SourceType,
)
from knowledge.document_router import RouteStatus, SourceRouter


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_text_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=10)
    doc.save(str(path))
    doc.close()


def _write_multipage_pdf(path: Path, page_texts: list[str]) -> None:
    """Write a PDF with one text block per page."""
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=9)
    doc.save(str(path))
    doc.close()


def _make_companies_root(tmp_path: Path, slugs: list[str]) -> Path:
    root = tmp_path / "companies"
    for slug in slugs:
        (root / slug).mkdir(parents=True, exist_ok=True)
    return root


# ── Canonical content blocks ──────────────────────────────────────────────────

# BSE/NSE cover-letter that triggers wrapper detection
_WRAPPER_TEXT = (
    "BSE Limited  National Stock Exchange of India Limited NSE India\n"
    "Listing Department  Listing Compliance\n"
    "Sub: Annual Report for Financial Year 2025-26 pursuant to Regulation 34 of "
    "SEBI (LODR) Regulations, 2015\n"
    "Please find enclosed herewith the Annual Report 2025-26 of the Company.\n"
    "Yours faithfully,\nABC Limited  Company Secretary\n"
)

# Cover letter for Regulation 30 (quarterly/press release)
_WRAPPER_REG30_TEXT = (
    "BSE Limited\nNSE India\nListing Department\n"
    "Sub: Quarterly results pursuant to Regulation 30 of SEBI (LODR) Regulations, 2015\n"
    "Please find enclosed herewith Q2 FY26 financial results.\n"
)

# Annual report payload (comes after wrapper on pages 2+)
_AR_PAYLOAD_TEXT = (
    "ABC Limited  Annual Report 2025-26\n"
    "Board of Directors  Directors' Report\n"
    "Standalone Financial Statements for the Year Ended March 31, 2026\n"
    "Independent Auditor's Report\n"
    "FY26 revenue: ₹2,500 crores.  Consolidated Financial Statements.\n"
    "Management Discussion and Analysis\n"
)

# Quarterly results payload
_QR_PAYLOAD_TEXT = (
    "ABC Limited  Q2 FY26 Results\n"
    "Unaudited Consolidated Financial Results for the Quarter Ended September 30, 2025\n"
    "Limited Review Report\n"
    "Revenue for Q2 FY26: ₹620 crores.\n"
)

# Investor presentation payload
_IP_PAYLOAD_TEXT = (
    "Investor Presentation  Analyst Meet — November 2025\n"
    "ABC Limited\n"
    "Slide 1: Business Overview\n"
    "Slide 2: Financial Highlights FY26\n"
    "Slide 3: Strategic Roadmap\n"
    "Earnings Presentation  Slide 4 of 30\n"
)

# Earnings call transcript
_EC_PAYLOAD_TEXT = (
    "Conference Call Transcript  Q2 FY26 Earnings Call\n"
    "Operator: Good morning, ladies and gentlemen.\n"
    "Management: Thank you Operator.\n"
    "Q&A Session\n"
    "Analyst: Can you elaborate on margin guidance?\n"
)

# Direct annual report (no exchange-filing wrapper)
_DIRECT_AR_TEXT = (
    "ABC Limited  Annual Report 2025-26\n"
    "Board of Directors  Directors' Report\n"
    "Standalone Financial Statements for the Year Ended March 31, 2026\n"
    "Independent Auditor's Report\n"
    "FY26 revenue: ₹2,500 crores.\n"
)

# Direct quarterly report
_DIRECT_QR_TEXT = (
    "ABC Limited  Q1 FY26 Quarterly Results\n"
    "Quarterly Results for Quarter Ended June 30, 2025\n"
    "Unaudited Standalone Results  Limited Review\n"
    "Revenue Q1 FY26: ₹580 crores.\n"
)

# Real PDF paths (guarded — CI doesn't require them)
_LTTS_437 = Path("data/Processed/ltts/fy26/annual_report/a5e2aee1-f21a-4812-a614-2851ebb3923b.pdf")
_LTTS_17  = Path("data/Processed/ltts/q1 fy27/earnings_release/6965ca6d-58bd-4c7a-a6ac-901f16d7f058.pdf")


# ---------------------------------------------------------------------------
# C01 – direct annual report → DIRECT channel, ANNUAL_REPORT payload
# ---------------------------------------------------------------------------

def test_c01_direct_annual_report(tmp_path):
    pdf = tmp_path / "direct_ar.pdf"
    _write_text_pdf(pdf, _DIRECT_AR_TEXT)
    root = _make_companies_root(tmp_path, ["abc"])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.DIRECT
    assert result.document_identity.source_type == SourceType.ANNUAL_REPORT


# ---------------------------------------------------------------------------
# C02 – exchange-filing annual report → EXCHANGE_FILING channel, ANNUAL_REPORT payload
# ---------------------------------------------------------------------------

def test_c02_exchange_filing_wraps_annual_report(tmp_path):
    pdf = tmp_path / "exchange_ar.pdf"
    _write_multipage_pdf(pdf, [_WRAPPER_TEXT, _AR_PAYLOAD_TEXT, _AR_PAYLOAD_TEXT])
    root = _make_companies_root(tmp_path, ["abc"])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.EXCHANGE_FILING
    assert result.document_identity.source_type == SourceType.ANNUAL_REPORT


# ---------------------------------------------------------------------------
# C03 – exchange-filing quarterly → EXCHANGE_FILING channel, QUARTERLY_REPORT payload
# ---------------------------------------------------------------------------

def test_c03_exchange_filing_wraps_quarterly(tmp_path):
    pdf = tmp_path / "exchange_qr.pdf"
    _write_multipage_pdf(pdf, [_WRAPPER_REG30_TEXT, _QR_PAYLOAD_TEXT, _QR_PAYLOAD_TEXT])
    root = _make_companies_root(tmp_path, ["abc"])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.EXCHANGE_FILING
    assert result.document_identity.source_type == SourceType.QUARTERLY_REPORT


# ---------------------------------------------------------------------------
# C04 – exchange-filing investor presentation → EXCHANGE_FILING channel, INVESTOR_PRESENTATION
# ---------------------------------------------------------------------------

def test_c04_exchange_filing_wraps_presentation(tmp_path):
    pdf = tmp_path / "exchange_ip.pdf"
    _write_multipage_pdf(pdf, [_WRAPPER_REG30_TEXT, _IP_PAYLOAD_TEXT, _IP_PAYLOAD_TEXT])
    root = _make_companies_root(tmp_path, ["abc"])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.EXCHANGE_FILING
    assert result.document_identity.source_type == SourceType.INVESTOR_PRESENTATION


# ---------------------------------------------------------------------------
# C05 – direct quarterly report → DIRECT channel, QUARTERLY_REPORT payload
# ---------------------------------------------------------------------------

def test_c05_direct_quarterly(tmp_path):
    pdf = tmp_path / "direct_qr.pdf"
    _write_text_pdf(pdf, _DIRECT_QR_TEXT)
    root = _make_companies_root(tmp_path, ["abc"])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.DIRECT
    assert result.document_identity.source_type == SourceType.QUARTERLY_REPORT


# ---------------------------------------------------------------------------
# C06 – direct investor presentation → DIRECT channel, INVESTOR_PRESENTATION
# ---------------------------------------------------------------------------

def test_c06_direct_presentation(tmp_path):
    pdf = tmp_path / "direct_ip.pdf"
    _write_text_pdf(pdf, _IP_PAYLOAD_TEXT)
    root = _make_companies_root(tmp_path, ["abc"])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.DIRECT
    assert result.document_identity.source_type == SourceType.INVESTOR_PRESENTATION


# ---------------------------------------------------------------------------
# C07 – direct transcript → DIRECT channel, EARNINGS_CALL_TRANSCRIPT
# ---------------------------------------------------------------------------

def test_c07_direct_transcript(tmp_path):
    pdf = tmp_path / "direct_ec.pdf"
    _write_text_pdf(pdf, _EC_PAYLOAD_TEXT)
    root = _make_companies_root(tmp_path, ["abc"])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.DIRECT
    assert result.document_identity.source_type == SourceType.EARNINGS_CALL_TRANSCRIPT


# ---------------------------------------------------------------------------
# C08 – no meaningful signals → DIRECT channel, UNKNOWN payload
# ---------------------------------------------------------------------------

def test_c08_no_signals(tmp_path):
    pdf = tmp_path / "no_signals.pdf"
    _write_text_pdf(pdf, "Page 1. Nothing useful here. Lorem ipsum dolor sit amet.")
    root = _make_companies_root(tmp_path, [])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.DIRECT
    assert result.document_identity.source_type == SourceType.UNKNOWN


# ---------------------------------------------------------------------------
# C09 – LTTS 437-page annual report (real PDF, skip if absent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _LTTS_437.exists(), reason="Real LTTS 437-page PDF not available")
def test_c09_ltts_437_page_real_pdf():
    result = identify_document(_LTTS_437)

    assert result.document_identity.source_channel == SourceChannel.EXCHANGE_FILING, (
        f"Expected EXCHANGE_FILING channel, got {result.document_identity.source_channel}"
    )
    assert result.document_identity.source_type == SourceType.ANNUAL_REPORT, (
        f"Expected ANNUAL_REPORT payload, got {result.document_identity.source_type}"
    )
    assert result.classification.status == ClassificationStatus.IDENTIFIED
    assert result.company_identity.detected_legal_name != "", (
        "detected_legal_name should be populated from the exchange filing"
    )
    assert result.company_identity.resolved_company_key == "ltts"


# ---------------------------------------------------------------------------
# C10 – LTTS 17-page press release (real PDF, skip if absent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _LTTS_17.exists(), reason="Real LTTS 17-page PDF not available")
def test_c10_ltts_17_page_real_pdf():
    result = identify_document(_LTTS_17)

    assert result.document_identity.source_channel == SourceChannel.EXCHANGE_FILING, (
        f"Expected EXCHANGE_FILING channel, got {result.document_identity.source_channel}"
    )
    assert result.document_identity.source_type == SourceType.EARNINGS_RELEASE
    assert result.classification.status == ClassificationStatus.IDENTIFIED
    assert result.company_identity.resolved_company_key == "ltts"


# ---------------------------------------------------------------------------
# A01 – Exchange-filing wrapper filename but DIRECT content → channel from content
# ---------------------------------------------------------------------------

def test_a01_filename_does_not_set_channel(tmp_path):
    # Filename says "exchange_filing" but content has no wrapper signals
    pdf = tmp_path / "exchange_filing_bse_nse.pdf"
    _write_text_pdf(pdf, _DIRECT_AR_TEXT)
    root = _make_companies_root(tmp_path, ["abc"])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.DIRECT, (
        "Filename must not determine source_channel; content probe is authoritative"
    )


# ---------------------------------------------------------------------------
# A02 – Exchange-filing wrapper with unrecognizable payload → EXCHANGE_FILING, UNKNOWN
# ---------------------------------------------------------------------------

def test_a02_wrapper_without_recognizable_payload(tmp_path):
    pdf = tmp_path / "no_payload_test.pdf"  # filename must not match any source-type keywords
    _write_multipage_pdf(pdf, [
        _WRAPPER_TEXT,
        "Page 2. No recognizable financial signals here at all.",
        "Page 3. Still nothing useful.",
    ])
    root = _make_companies_root(tmp_path, [])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.EXCHANGE_FILING
    assert result.document_identity.source_type == SourceType.UNKNOWN


# ---------------------------------------------------------------------------
# A03 – Single-page exchange filing → wrapper detected, no payload → graceful
# ---------------------------------------------------------------------------

def test_a03_single_page_exchange_filing(tmp_path):
    pdf = tmp_path / "single_page_wrapper.pdf"
    _write_text_pdf(pdf, _WRAPPER_TEXT)
    root = _make_companies_root(tmp_path, [])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.EXCHANGE_FILING
    # No crash; classification may be UNKNOWN or OTHER for the payload
    assert result.classification.status in {
        ClassificationStatus.UNIDENTIFIED,
        ClassificationStatus.REVIEW_REQUIRED,
    }


# ---------------------------------------------------------------------------
# A04 – Company name in document but not in registry → REVIEW_REQUIRED
# ---------------------------------------------------------------------------

def test_a04_detected_name_not_in_registry_is_review_required(tmp_path):
    content = (
        "L&T Technology Services Limited\n"
        "Annual Report 2025-26\n"
        "Board of Directors  Directors' Report\n"
        "Standalone Financial Statements for the Year Ended March 31, 2026\n"
        "Independent Auditor's Report\n"
        "FY26 revenue: ₹5,000 crores.\n"
    )
    pdf = tmp_path / "ltts_direct_ar.pdf"
    _write_text_pdf(pdf, content)
    # Registry does NOT include ltts
    root = _make_companies_root(tmp_path, ["polymatech"])

    result = identify_document(pdf, companies_root=root)

    assert result.classification.status == ClassificationStatus.REVIEW_REQUIRED, (
        "A company whose name is detected in text but has no registry entry should be REVIEW_REQUIRED"
    )
    assert result.company_identity.resolved_company_key is None
    # Legal name must be preserved
    assert "Technology Services" in result.company_identity.detected_legal_name or \
           "L&T" in result.company_identity.detected_legal_name, (
        f"detected_legal_name should contain company name, got: {result.company_identity.detected_legal_name!r}"
    )


# ---------------------------------------------------------------------------
# A05 – No company name anywhere → UNIDENTIFIED (not REVIEW_REQUIRED)
# ---------------------------------------------------------------------------

def test_a05_no_name_is_unidentified_not_review_required(tmp_path):
    content = (
        "Annual Report 2025-26\n"
        "Board of Directors  Directors' Report\n"
        "Standalone Financial Statements for the Year Ended March 31, 2026\n"
        "Independent Auditor's Report\n"
        "FY26 revenue: ₹2,500 crores.\n"
    )
    pdf = tmp_path / "nameless_ar.pdf"
    _write_text_pdf(pdf, content)
    root = _make_companies_root(tmp_path, [])

    result = identify_document(pdf, companies_root=root)

    assert result.classification.status == ClassificationStatus.UNIDENTIFIED, (
        "When no corporate legal name appears in the document, status should be UNIDENTIFIED"
    )
    assert result.company_identity.detected_legal_name == ""


# ---------------------------------------------------------------------------
# A06 – Regulation 34 only on page 4 (not in wrapper zone) → NOT a wrapper
# ---------------------------------------------------------------------------

def test_a06_regulation34_deep_in_document_not_wrapper(tmp_path):
    # Pages 1-3: pure annual report content
    # Page 4: contains "Regulation 34" as body text, not a cover letter
    ar_page = _DIRECT_AR_TEXT
    reg34_page = (
        "The company has complied with Regulation 34 of SEBI (LODR) requirements "
        "as required under the annual report disclosures. SEBI (LODR) guidelines.\n"
        "This appears on page 4 and should not trigger wrapper detection.\n"
    )
    pdf = tmp_path / "deep_reg34.pdf"
    _write_multipage_pdf(pdf, [ar_page, ar_page, ar_page, reg34_page])
    root = _make_companies_root(tmp_path, ["abc"])

    result = identify_document(pdf, companies_root=root)

    # Wrapper detection only fires on first CONTENT_PROBE_WRAPPER_PAGES pages
    assert result.document_identity.source_channel == SourceChannel.DIRECT, (
        "Regulation 34 appearing on page 4 must not trigger wrapper detection"
    )
    assert result.document_identity.source_type == SourceType.ANNUAL_REPORT


# ---------------------------------------------------------------------------
# A07 – Strong annual-report signals on page 1 → no false-positive wrapper
# ---------------------------------------------------------------------------

def test_a07_annual_report_first_page_not_misclassified_as_wrapper(tmp_path):
    pdf = tmp_path / "strong_ar.pdf"
    _write_text_pdf(pdf, _DIRECT_AR_TEXT)
    root = _make_companies_root(tmp_path, ["abc"])

    result = identify_document(pdf, companies_root=root)

    assert result.document_identity.source_channel == SourceChannel.DIRECT
    assert result.document_identity.source_type == SourceType.ANNUAL_REPORT


# ---------------------------------------------------------------------------
# A08 – Polymatech regression: registered company still routes correctly
# ---------------------------------------------------------------------------

def test_a08_polymatech_regression(tmp_path):
    content = (
        "Polymatech Electronics Private Limited\n"
        "Annual Report 2023-24\n"
        "Standalone Financial Statements for the Year Ended March 31, 2024\n"
        "Independent Auditor's Report\n"
        "Directors' Report  Board of Directors\n"
        "FY24 revenue from semiconductor components reached ₹850 crores.\n"
    )
    pdf = tmp_path / "polymatech_fy24.pdf"
    _write_text_pdf(pdf, content)
    root = _make_companies_root(tmp_path, ["polymatech"])

    result = identify_document(pdf, companies_root=root)

    assert result.classification.status == ClassificationStatus.IDENTIFIED
    assert result.company_identity.resolved_company_key == "polymatech"
    assert result.document_identity.source_type == SourceType.ANNUAL_REPORT
    assert result.document_identity.source_channel == SourceChannel.DIRECT

    decision = SourceRouter().route(result)
    assert decision.status == RouteStatus.ROUTABLE


# ---------------------------------------------------------------------------
# A09 – Router uses payload type (source_type), not source_channel, for routing
# ---------------------------------------------------------------------------

def test_a09_router_uses_payload_type_not_channel(tmp_path):
    content = (
        "Polymatech Electronics Private Limited\n"
        "Annual Report 2023-24\n"
        "Board of Directors  Directors' Report\n"
        "Standalone Financial Statements for the Year Ended March 31, 2024\n"
        "Independent Auditor's Report  FY24 revenue: ₹850 crores.\n"
    )
    pdf = tmp_path / "exchange_polymatech_ar.pdf"
    # Wrap the annual report content in an exchange-filing multi-page PDF
    _write_multipage_pdf(pdf, [_WRAPPER_TEXT, content, content])
    root = _make_companies_root(tmp_path, ["polymatech"])

    result = identify_document(pdf, companies_root=root)

    # Channel is exchange filing but routing is still based on payload type
    assert result.document_identity.source_channel == SourceChannel.EXCHANGE_FILING
    assert result.document_identity.source_type == SourceType.ANNUAL_REPORT

    decision = SourceRouter().route(result)
    assert decision.status == RouteStatus.ROUTABLE, (
        "An ANNUAL_REPORT payload wrapped in an EXCHANGE_FILING channel must still route as ROUTABLE"
    )


# ---------------------------------------------------------------------------
# A10 – REVIEW_REQUIRED manifest preserves detected_legal_name in company_identity
# ---------------------------------------------------------------------------

def test_a10_review_required_preserves_detected_legal_name(tmp_path):
    content = (
        "L&T Technology Services Limited\n"
        "Annual Report 2025-26\n"
        "Board of Directors  Directors' Report\n"
        "Standalone Financial Statements for the Year Ended March 31, 2026\n"
        "Independent Auditor's Report  FY26 revenue: ₹5,000 crores.\n"
    )
    pdf = tmp_path / "ltts_ar.pdf"
    _write_text_pdf(pdf, content)
    root = _make_companies_root(tmp_path, [])

    result = identify_document(pdf, companies_root=root)

    assert result.classification.status == ClassificationStatus.REVIEW_REQUIRED
    assert result.company_identity.resolved_company_key is None
    assert result.company_identity.detected_legal_name != "", (
        "detected_legal_name must be populated for REVIEW_REQUIRED manifests"
    )


# ---------------------------------------------------------------------------
# A11 – Wrapper threshold: single weak signal must not trip wrapper detection
# ---------------------------------------------------------------------------

def test_a11_single_signal_does_not_trip_wrapper():
    # Only "BSE Limited" (score=3) — below threshold of 8
    weak_text = "BSE Limited  Company announces quarterly results for Q2 FY26."
    assert not _detect_exchange_wrapper(weak_text), (
        "A single weak exchange signal must not be enough to declare an exchange-filing wrapper"
    )


def test_a11b_strong_signals_do_trip_wrapper():
    strong_text = (
        "BSE Limited  NSE India  Listing Department\n"
        "Regulation 34 of SEBI (LODR) Regulations, 2015\n"
        "Please find enclosed herewith the Annual Report 2025-26.\n"
    )
    assert _detect_exchange_wrapper(strong_text), (
        "Combination of Regulation 34 + SEBI (LODR) + listing signals must trigger wrapper detection"
    )


# ---------------------------------------------------------------------------
# A12 – source_channel serialised in to_dict / round-tripped via from_dict
# ---------------------------------------------------------------------------

def test_a12_source_channel_round_trip():
    from knowledge.document_intake import DocumentIdentity, SourceChannel, SourceType

    original = DocumentIdentity(
        source_type=SourceType.ANNUAL_REPORT,
        source_channel=SourceChannel.EXCHANGE_FILING,
        document_subtype="annual_report",
        confidence=ConfidenceLevel.HIGH,
    )
    as_dict = original.to_dict()
    assert as_dict["source_channel"] == "EXCHANGE_FILING"

    restored = DocumentIdentity.from_dict(as_dict)
    assert restored.source_channel == SourceChannel.EXCHANGE_FILING
    assert restored.source_type == SourceType.ANNUAL_REPORT


# ---------------------------------------------------------------------------
# A13 – Backward compat: old manifest dict without source_channel parses cleanly
# ---------------------------------------------------------------------------

def test_a13_missing_source_channel_defaults_to_unknown():
    from knowledge.document_intake import DocumentIdentity, SourceChannel, SourceType

    legacy_dict = {
        "source_type": "ANNUAL_REPORT",
        "document_subtype": "annual_report",
        "confidence": "HIGH",
        "evidence": [],
        # No "source_channel" key — simulates a v2 manifest
    }
    result = DocumentIdentity.from_dict(legacy_dict)
    assert result.source_channel == SourceChannel.UNKNOWN, (
        "A manifest serialised without source_channel must default to UNKNOWN without crashing"
    )
    assert result.source_type == SourceType.ANNUAL_REPORT


# ---------------------------------------------------------------------------
# Unit: _extract_legal_company_name
# ---------------------------------------------------------------------------

def test_extract_legal_name_from_title_zone():
    text = (
        "L&T Technology Services Limited\n"
        "Annual Report 2025-26\n"
        "Board of Directors\n"
    )
    name = _extract_legal_company_name(text)
    assert "Technology Services" in name or "L&T" in name


def test_extract_legal_name_private_limited():
    text = "Polymatech Electronics Private Limited\nAnnual Report 2023-24\n"
    name = _extract_legal_company_name(text)
    assert "Polymatech" in name


def test_extract_legal_name_empty_when_absent():
    text = "Annual Report 2025-26. Q1 results. Board meeting."
    name = _extract_legal_company_name(text)
    assert name == ""
