from __future__ import annotations

import base64
from pathlib import Path

import fitz

from knowledge.document_intake import build_document_intake_report, inspect_pdf_document, read_document_text


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
