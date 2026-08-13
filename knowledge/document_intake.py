from __future__ import annotations

import importlib.util
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import fitz


PDF_CLASSIFICATIONS = {
    "TEXT_PDF",
    "IMAGE_ONLY_PDF",
    "MIXED_PDF",
    "CORRUPT_PDF",
    "ENCRYPTED_PDF",
    "UNSUPPORTED_PDF",
}


def _clean_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _ocr_dependencies_available() -> bool:
    return bool(
        importlib.util.find_spec("pytesseract")
        and importlib.util.find_spec("PIL")
        and shutil.which("tesseract")
    )


@dataclass
class PageIntake:
    page: int
    text_char_count: int
    image_count: int
    has_text: bool
    has_image: bool
    text_sample: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "text_char_count": self.text_char_count,
            "image_count": self.image_count,
            "has_text": self.has_text,
            "has_image": self.has_image,
            "text_sample": self.text_sample,
        }


@dataclass
class PdfIntake:
    path: str
    classification: str
    page_count: int
    text_page_count: int
    image_page_count: int
    text_layer_coverage: float
    native_text_char_count: int
    ocr_available: bool
    ocr_required: bool
    ocr_used: bool
    status: str
    limitations: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    pages: List[PageIntake] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "classification": self.classification,
            "page_count": self.page_count,
            "text_page_count": self.text_page_count,
            "image_page_count": self.image_page_count,
            "text_layer_coverage": self.text_layer_coverage,
            "native_text_char_count": self.native_text_char_count,
            "ocr_available": self.ocr_available,
            "ocr_required": self.ocr_required,
            "ocr_used": self.ocr_used,
            "status": self.status,
            "limitations": list(self.limitations),
            "errors": list(self.errors),
            "pages": [page.to_dict() for page in self.pages],
        }


def _classify_pdf_inspection(*, page_count: int, text_page_count: int, image_page_count: int, native_text_char_count: int, errors: Iterable[str]) -> str:
    if errors:
        if any("encrypted" in error.lower() for error in errors):
            return "ENCRYPTED_PDF"
        if any("corrupt" in error.lower() or "filedataerror" in error.lower() for error in errors):
            return "CORRUPT_PDF"
        return "UNSUPPORTED_PDF"
    if page_count <= 0:
        return "UNSUPPORTED_PDF"
    if text_page_count <= 0:
        return "IMAGE_ONLY_PDF" if image_page_count > 0 else "UNSUPPORTED_PDF"
    coverage = text_page_count / max(page_count, 1)
    if coverage >= 0.8 and native_text_char_count > 0:
        return "TEXT_PDF"
    if coverage <= 0.25 and image_page_count > 0:
        return "IMAGE_ONLY_PDF"
    return "MIXED_PDF"


def inspect_pdf_document(pdf_path: Path) -> PdfIntake:
    pdf_path = Path(pdf_path)
    errors: List[str] = []
    pages: List[PageIntake] = []
    doc = None
    try:
        doc = fitz.open(pdf_path)
        if doc.needs_pass or getattr(doc, "is_encrypted", False):
            return PdfIntake(
                path=str(pdf_path),
                classification="ENCRYPTED_PDF",
                page_count=doc.page_count if doc is not None else 0,
                text_page_count=0,
                image_page_count=0,
                text_layer_coverage=0.0,
                native_text_char_count=0,
                ocr_available=_ocr_dependencies_available(),
                ocr_required=True,
                ocr_used=False,
                status="blocked",
                limitations=["PDF is encrypted and requires a password before text extraction can continue."],
                errors=["encrypted pdf"],
                pages=[],
            )
        native_text_char_count = 0
        text_page_count = 0
        image_page_count = 0
        page_count = doc.page_count
        for page_index in range(page_count):
            page = doc.load_page(page_index)
            text = _clean_text(page.get_text("text"))
            image_count = len(page.get_images(full=True))
            has_text = len(text) >= 20
            has_image = image_count > 0
            if has_text:
                text_page_count += 1
                native_text_char_count += len(text)
            if has_image and not has_text:
                image_page_count += 1
            pages.append(
                PageIntake(
                    page=page_index + 1,
                    text_char_count=len(text),
                    image_count=image_count,
                    has_text=has_text,
                    has_image=has_image,
                    text_sample=text[:180],
                )
            )
        classification = _classify_pdf_inspection(
            page_count=page_count,
            text_page_count=text_page_count,
            image_page_count=image_page_count,
            native_text_char_count=native_text_char_count,
            errors=errors,
        )
        ocr_required = classification in {"IMAGE_ONLY_PDF", "MIXED_PDF"} and text_page_count < page_count
        status = "supported" if classification in {"TEXT_PDF", "MIXED_PDF"} else "blocked"
        limitations = []
        if classification == "IMAGE_ONLY_PDF":
            limitations.append("No machine-readable text layer was found in the PDF.")
        elif classification == "MIXED_PDF":
            limitations.append("The PDF contains a mixed text/image layer and may need OCR on image-heavy pages.")
        return PdfIntake(
            path=str(pdf_path),
            classification=classification,
            page_count=page_count,
            text_page_count=text_page_count,
            image_page_count=image_page_count,
            text_layer_coverage=(text_page_count / page_count) if page_count else 0.0,
            native_text_char_count=native_text_char_count,
            ocr_available=_ocr_dependencies_available(),
            ocr_required=ocr_required,
            ocr_used=False,
            status=status,
            limitations=limitations,
            errors=[],
            pages=pages,
        )
    except fitz.FileDataError as exc:
        errors.append(str(exc) or "corrupt pdf")
    except (RuntimeError, ValueError, OSError) as exc:
        errors.append(str(exc) or "unsupported pdf")
    finally:
        if doc is not None:
            doc.close()

    classification = _classify_pdf_inspection(
        page_count=0,
        text_page_count=0,
        image_page_count=0,
        native_text_char_count=0,
        errors=errors,
    )
    return PdfIntake(
        path=str(pdf_path),
        classification=classification,
        page_count=0,
        text_page_count=0,
        image_page_count=0,
        text_layer_coverage=0.0,
        native_text_char_count=0,
        ocr_available=_ocr_dependencies_available(),
        ocr_required=classification == "IMAGE_ONLY_PDF",
        ocr_used=False,
        status="blocked",
        limitations=["PDF could not be opened safely."],
        errors=errors,
        pages=[],
    )


def read_document_text(path: Path, *, allow_ocr: bool = True) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8").strip()
    if suffix != ".pdf":
        return ""

    intake = inspect_pdf_document(path)
    if intake.native_text_char_count > 0 and intake.classification in {"TEXT_PDF", "MIXED_PDF"}:
        doc = fitz.open(path)
        try:
            return "\n".join(_clean_text(page.get_text("text")) for page in doc).strip()
        finally:
            doc.close()

    if allow_ocr and intake.ocr_available:
        # Minimal canonical OCR architecture: the hook exists, but OCR engines are optional.
        # When OCR dependencies are available in the environment, the caller may extend this
        # branch to render pages and run OCR without changing pipeline behavior.
        return ""

    return ""


def build_document_intake_report(paths: Iterable[Path], *, allow_ocr: bool = True) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    for path in paths:
        path = Path(path)
        if path.suffix.lower() == ".pdf":
            intake = inspect_pdf_document(path)
            text = read_document_text(path, allow_ocr=allow_ocr)
            record = intake.to_dict()
            record["extractable_text_char_count"] = len(_clean_text(text))
            record["has_extractable_text"] = bool(_clean_text(text))
            records.append(record)
        else:
            text = read_document_text(path, allow_ocr=False)
            records.append(
                {
                    "path": str(path),
                    "classification": "TEXT_DOCUMENT",
                    "page_count": 0,
                    "text_page_count": 0,
                    "image_page_count": 0,
                    "text_layer_coverage": 1.0 if text else 0.0,
                    "native_text_char_count": len(_clean_text(text)),
                    "ocr_available": False,
                    "ocr_required": False,
                    "ocr_used": False,
                    "status": "supported" if text else "blocked",
                    "limitations": [],
                    "errors": [],
                    "pages": [],
                    "extractable_text_char_count": len(_clean_text(text)),
                    "has_extractable_text": bool(_clean_text(text)),
                }
            )

    ocr_available = _ocr_dependencies_available()
    ocr_required_paths = [record["path"] for record in records if record.get("ocr_required")]
    text_documents = [record["path"] for record in records if record.get("has_extractable_text")]
    blocked_documents = [record["path"] for record in records if not record.get("has_extractable_text")]

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "supported" if not blocked_documents else "blocked",
        "ocr_available": ocr_available,
        "ocr_required_paths": ocr_required_paths,
        "text_documents": text_documents,
        "blocked_documents": blocked_documents,
        "documents": records,
    }
