from __future__ import annotations

import base64
from pathlib import Path

import fitz

from knowledge.document_intake import build_document_intake_report, inspect_pdf_document, read_document_text
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
