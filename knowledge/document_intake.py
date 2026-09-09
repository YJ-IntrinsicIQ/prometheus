from __future__ import annotations

import hashlib
import importlib.util
import shutil
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import fitz

try:
    import pytesseract
    from PIL import Image
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

from knowledge.document_ownership import infer_document_reporting_period


PDF_CLASSIFICATIONS = {
    "TEXT_PDF",
    "IMAGE_ONLY_PDF",
    "MIXED_PDF",
    "CORRUPT_PDF",
    "ENCRYPTED_PDF",
    "UNSUPPORTED_PDF",
}


class SourceType(str, Enum):
    ANNUAL_REPORT = "ANNUAL_REPORT"
    QUARTERLY_REPORT = "QUARTERLY_REPORT"
    INVESTOR_PRESENTATION = "INVESTOR_PRESENTATION"
    EARNINGS_CALL_TRANSCRIPT = "EARNINGS_CALL_TRANSCRIPT"
    EARNINGS_RELEASE = "EARNINGS_RELEASE"
    EXCHANGE_FILING = "EXCHANGE_FILING"
    EXCHANGE_DISCLOSURE = "EXCHANGE_DISCLOSURE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class SourceChannel(str, Enum):
    """How the document was distributed — the delivery envelope, not the payload.

    DIRECT           — downloaded directly from company website or sent directly
    EXCHANGE_FILING  — submitted to BSE / NSE / other exchange (Regulation 34/30 wrapper)
    REGULATORY_PORTAL — filed via MCA, SEBI portal, or other regulator
    UNKNOWN          — channel could not be determined from available evidence
    """
    DIRECT = "DIRECT"
    EXCHANGE_FILING = "EXCHANGE_FILING"
    REGULATORY_PORTAL = "REGULATORY_PORTAL"
    UNKNOWN = "UNKNOWN"


class FiscalQuarter(str, Enum):
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"


class EntityScope(str, Enum):
    STANDALONE = "standalone"
    CONSOLIDATED = "consolidated"
    MIXED = "mixed"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ClassificationStatus(str, Enum):
    IDENTIFIED = "IDENTIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNIDENTIFIED = "UNIDENTIFIED"
    REJECTED = "REJECTED"


class DetectionMethod(str, Enum):
    MANUAL_COMPATIBILITY_ADAPTER = "manual_compatibility_adapter"
    AUTOMATIC_CLASSIFIER = "automatic_classifier"
    OPERATOR_REVIEW = "operator_review"
    UNKNOWN = "unknown"


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _date_to_iso(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


@dataclass
class IdentityEvidence:
    field: str
    excerpt: str
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    source_artifact: str = ""
    page: Optional[int] = None
    chunk_id: str = ""
    evidence_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "excerpt": self.excerpt,
            "confidence": _enum_value(self.confidence),
            "source_artifact": self.source_artifact,
            "page": self.page,
            "chunk_id": self.chunk_id,
            "evidence_id": self.evidence_id,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "IdentityEvidence":
        return cls(
            field=str(payload.get("field") or ""),
            excerpt=str(payload.get("excerpt") or ""),
            confidence=ConfidenceLevel(str(payload.get("confidence") or ConfidenceLevel.UNKNOWN.value)),
            source_artifact=str(payload.get("source_artifact") or ""),
            page=payload.get("page"),
            chunk_id=str(payload.get("chunk_id") or ""),
            evidence_id=str(payload.get("evidence_id") or ""),
        )


@dataclass
class FileIdentity:
    original_filename: str
    content_hash: str
    mime_type: str
    size_bytes: int
    storage_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_filename": self.original_filename,
            "content_hash": self.content_hash,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "storage_path": self.storage_path,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FileIdentity":
        return cls(
            original_filename=str(payload.get("original_filename") or ""),
            content_hash=str(payload.get("content_hash") or ""),
            mime_type=str(payload.get("mime_type") or ""),
            size_bytes=int(payload.get("size_bytes") or 0),
            storage_path=str(payload.get("storage_path") or ""),
        )


@dataclass
class CompanyIdentity:
    resolved_company_key: Optional[str] = None
    detected_legal_name: str = ""
    detected_display_name: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    evidence: List[IdentityEvidence] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolved_company_key": self.resolved_company_key,
            "detected_legal_name": self.detected_legal_name,
            "detected_display_name": self.detected_display_name,
            "confidence": _enum_value(self.confidence),
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CompanyIdentity":
        return cls(
            resolved_company_key=payload.get("resolved_company_key"),
            detected_legal_name=str(payload.get("detected_legal_name") or ""),
            detected_display_name=str(payload.get("detected_display_name") or ""),
            confidence=ConfidenceLevel(str(payload.get("confidence") or ConfidenceLevel.UNKNOWN.value)),
            evidence=[IdentityEvidence.from_dict(item) for item in payload.get("evidence", []) if isinstance(item, dict)],
        )


@dataclass
class DocumentIdentity:
    source_type: SourceType = SourceType.UNKNOWN
    source_channel: SourceChannel = SourceChannel.UNKNOWN
    document_subtype: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    evidence: List[IdentityEvidence] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_type": _enum_value(self.source_type),
            "source_channel": _enum_value(self.source_channel),
            "document_subtype": self.document_subtype,
            "confidence": _enum_value(self.confidence),
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DocumentIdentity":
        raw_channel = payload.get("source_channel") or SourceChannel.UNKNOWN.value
        try:
            channel = SourceChannel(str(raw_channel))
        except ValueError:
            channel = SourceChannel.UNKNOWN
        return cls(
            source_type=SourceType(str(payload.get("source_type") or SourceType.UNKNOWN.value)),
            source_channel=channel,
            document_subtype=str(payload.get("document_subtype") or ""),
            confidence=ConfidenceLevel(str(payload.get("confidence") or ConfidenceLevel.UNKNOWN.value)),
            evidence=[IdentityEvidence.from_dict(item) for item in payload.get("evidence", []) if isinstance(item, dict)],
        )


@dataclass
class ReportingPeriod:
    fiscal_year: Optional[str] = None
    fiscal_quarter: Optional[FiscalQuarter] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    evidence: List[IdentityEvidence] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fiscal_year": self.fiscal_year,
            "fiscal_quarter": _enum_value(self.fiscal_quarter) if self.fiscal_quarter else None,
            "period_start": _date_to_iso(self.period_start),
            "period_end": _date_to_iso(self.period_end),
            "confidence": _enum_value(self.confidence),
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ReportingPeriod":
        raw_quarter = payload.get("fiscal_quarter")
        return cls(
            fiscal_year=payload.get("fiscal_year"),
            fiscal_quarter=FiscalQuarter(str(raw_quarter)) if raw_quarter else None,
            period_start=payload.get("period_start"),
            period_end=payload.get("period_end"),
            confidence=ConfidenceLevel(str(payload.get("confidence") or ConfidenceLevel.UNKNOWN.value)),
            evidence=[IdentityEvidence.from_dict(item) for item in payload.get("evidence", []) if isinstance(item, dict)],
        )


@dataclass
class DocumentDates:
    document_date: Optional[str] = None
    publication_date: Optional[str] = None
    filing_date: Optional[str] = None
    event_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_date": _date_to_iso(self.document_date),
            "publication_date": _date_to_iso(self.publication_date),
            "filing_date": _date_to_iso(self.filing_date),
            "event_date": _date_to_iso(self.event_date),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DocumentDates":
        return cls(
            document_date=payload.get("document_date"),
            publication_date=payload.get("publication_date"),
            filing_date=payload.get("filing_date"),
            event_date=payload.get("event_date"),
        )


@dataclass
class ClassificationState:
    overall_confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    status: ClassificationStatus = ClassificationStatus.UNIDENTIFIED
    unresolved_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_confidence": _enum_value(self.overall_confidence),
            "status": _enum_value(self.status),
            "unresolved_fields": list(self.unresolved_fields),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ClassificationState":
        return cls(
            overall_confidence=ConfidenceLevel(str(payload.get("overall_confidence") or ConfidenceLevel.UNKNOWN.value)),
            status=ClassificationStatus(str(payload.get("status") or ClassificationStatus.UNIDENTIFIED.value)),
            unresolved_fields=[str(item) for item in payload.get("unresolved_fields", [])],
            warnings=[str(item) for item in payload.get("warnings", [])],
        )


@dataclass
class IntakeProvenance:
    ingestion_timestamp: str
    classifier_version: str = "document_intake_manifest.v1"
    detection_method: DetectionMethod = DetectionMethod.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ingestion_timestamp": self.ingestion_timestamp,
            "classifier_version": self.classifier_version,
            "detection_method": _enum_value(self.detection_method),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "IntakeProvenance":
        return cls(
            ingestion_timestamp=str(payload.get("ingestion_timestamp") or ""),
            classifier_version=str(payload.get("classifier_version") or "document_intake_manifest.v1"),
            detection_method=DetectionMethod(str(payload.get("detection_method") or DetectionMethod.UNKNOWN.value)),
        )


@dataclass
class DocumentIntakeManifest:
    document_id: str
    file: FileIdentity
    company_identity: CompanyIdentity = field(default_factory=CompanyIdentity)
    document_identity: DocumentIdentity = field(default_factory=DocumentIdentity)
    reporting_period: Optional[ReportingPeriod] = None
    document_dates: DocumentDates = field(default_factory=DocumentDates)
    entity_scope: EntityScope = EntityScope.UNKNOWN
    language: str = "unknown"
    classification: ClassificationState = field(default_factory=ClassificationState)
    provenance: IntakeProvenance = field(
        default_factory=lambda: IntakeProvenance(
            ingestion_timestamp=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "file": self.file.to_dict(),
            "company_identity": self.company_identity.to_dict(),
            "document_identity": self.document_identity.to_dict(),
            "reporting_period": self.reporting_period.to_dict() if self.reporting_period else None,
            "document_dates": self.document_dates.to_dict(),
            "entity_scope": _enum_value(self.entity_scope),
            "language": self.language,
            "classification": self.classification.to_dict(),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DocumentIntakeManifest":
        reporting_period = payload.get("reporting_period")
        return cls(
            document_id=str(payload.get("document_id") or ""),
            file=FileIdentity.from_dict(payload.get("file") or {}),
            company_identity=CompanyIdentity.from_dict(payload.get("company_identity") or {}),
            document_identity=DocumentIdentity.from_dict(payload.get("document_identity") or {}),
            reporting_period=ReportingPeriod.from_dict(reporting_period) if isinstance(reporting_period, dict) else None,
            document_dates=DocumentDates.from_dict(payload.get("document_dates") or {}),
            entity_scope=EntityScope(str(payload.get("entity_scope") or EntityScope.UNKNOWN.value)),
            language=str(payload.get("language") or "unknown"),
            classification=ClassificationState.from_dict(payload.get("classification") or {}),
            provenance=IntakeProvenance.from_dict(payload.get("provenance") or {}),
        )


@dataclass(frozen=True)
class LegacyPipelineInputs:
    company: str
    year: str
    source_file: str


class DocumentManifestResolutionError(ValueError):
    pass


def compute_content_hash(path: Path, *, algorithm: str = "sha256") -> str:
    path = Path(path)
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{algorithm}:{digest.hexdigest()}"


def validate_document_intake_manifest(manifest: DocumentIntakeManifest | Dict[str, Any]) -> List[str]:
    if isinstance(manifest, dict):
        try:
            manifest = DocumentIntakeManifest.from_dict(manifest)
        except (TypeError, ValueError) as exc:
            return [f"manifest cannot be decoded: {exc}"]

    errors: List[str] = []
    if not manifest.document_id:
        errors.append("document_id is required")
    if not manifest.file.original_filename:
        errors.append("file.original_filename is required")
    if not manifest.file.content_hash:
        errors.append("file.content_hash is required")
    if not manifest.file.mime_type:
        errors.append("file.mime_type is required")
    if manifest.file.size_bytes < 0:
        errors.append("file.size_bytes cannot be negative")
    if manifest.reporting_period and manifest.reporting_period.fiscal_quarter and not manifest.reporting_period.fiscal_year:
        errors.append("reporting_period.fiscal_year is required when fiscal_quarter is present")
    if manifest.reporting_period and manifest.reporting_period.period_start and manifest.reporting_period.period_end:
        if manifest.reporting_period.period_start > manifest.reporting_period.period_end:
            errors.append("reporting_period.period_start cannot be after period_end")

    identified = manifest.classification.status == ClassificationStatus.IDENTIFIED
    if identified:
        if manifest.classification.overall_confidence == ConfidenceLevel.UNKNOWN:
            errors.append("classification.overall_confidence cannot be UNKNOWN when status is IDENTIFIED")
        if not manifest.company_identity.resolved_company_key:
            errors.append("company_identity.resolved_company_key is required when status is IDENTIFIED")
        if manifest.company_identity.confidence == ConfidenceLevel.UNKNOWN:
            errors.append("company_identity.confidence cannot be UNKNOWN when status is IDENTIFIED")
        if manifest.document_identity.source_type == SourceType.UNKNOWN:
            errors.append("document_identity.source_type cannot be UNKNOWN when status is IDENTIFIED")
        if manifest.document_identity.confidence == ConfidenceLevel.UNKNOWN:
            errors.append("document_identity.confidence cannot be UNKNOWN when status is IDENTIFIED")
        if manifest.document_identity.source_type in {SourceType.ANNUAL_REPORT, SourceType.QUARTERLY_REPORT}:
            if not manifest.reporting_period or not manifest.reporting_period.fiscal_year:
                errors.append("reporting_period.fiscal_year is required for identified periodic reports")
        if manifest.document_identity.source_type == SourceType.QUARTERLY_REPORT:
            if not manifest.reporting_period or not manifest.reporting_period.fiscal_quarter:
                errors.append("reporting_period.fiscal_quarter is required for identified quarterly reports")
    return errors


def build_legacy_annual_report_manifest(
    *,
    company_key: str,
    fiscal_year: str,
    source_file: Path | str,
    detected_legal_name: str = "",
    detected_display_name: str = "",
    document_date: str | None = None,
    publication_date: str | None = None,
    filing_date: str | None = None,
    ingestion_timestamp: str | None = None,
) -> DocumentIntakeManifest:
    path = Path(source_file)
    content_hash = compute_content_hash(path) if path.exists() else ""
    return DocumentIntakeManifest(
        document_id=content_hash or f"legacy-annual-report:{company_key}:{fiscal_year}:{path.name}",
        file=FileIdentity(
            original_filename=path.name,
            content_hash=content_hash,
            mime_type="application/pdf" if path.suffix.lower() == ".pdf" else "text/plain",
            size_bytes=path.stat().st_size if path.exists() else 0,
            storage_path=str(path),
        ),
        company_identity=CompanyIdentity(
            resolved_company_key=company_key,
            detected_legal_name=detected_legal_name,
            detected_display_name=detected_display_name,
            confidence=ConfidenceLevel.HIGH,
            evidence=[
                IdentityEvidence(
                    field="company_identity.resolved_company_key",
                    excerpt="Provided by existing manual pipeline invocation.",
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
        ),
        document_identity=DocumentIdentity(
            source_type=SourceType.ANNUAL_REPORT,
            document_subtype="annual_report",
            confidence=ConfidenceLevel.HIGH,
            evidence=[
                IdentityEvidence(
                    field="document_identity.source_type",
                    excerpt="Provided by existing annual-report pipeline invocation.",
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
        ),
        reporting_period=ReportingPeriod(
            fiscal_year=fiscal_year,
            confidence=ConfidenceLevel.HIGH,
            evidence=[
                IdentityEvidence(
                    field="reporting_period.fiscal_year",
                    excerpt="Provided by existing manual pipeline invocation.",
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
        ),
        document_dates=DocumentDates(
            document_date=document_date,
            publication_date=publication_date,
            filing_date=filing_date,
        ),
        entity_scope=EntityScope.UNKNOWN,
        language="unknown",
        classification=ClassificationState(
            overall_confidence=ConfidenceLevel.HIGH,
            status=ClassificationStatus.IDENTIFIED,
            unresolved_fields=["entity_scope", "language"],
        ),
        provenance=IntakeProvenance(
            ingestion_timestamp=ingestion_timestamp
            or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            detection_method=DetectionMethod.MANUAL_COMPATIBILITY_ADAPTER,
        ),
    )


def manifest_to_legacy_pipeline_inputs(manifest: DocumentIntakeManifest | Dict[str, Any]) -> LegacyPipelineInputs:
    if isinstance(manifest, dict):
        manifest = DocumentIntakeManifest.from_dict(manifest)
    errors = validate_document_intake_manifest(manifest)
    if errors:
        raise DocumentManifestResolutionError("; ".join(errors))
    if manifest.classification.status != ClassificationStatus.IDENTIFIED:
        raise DocumentManifestResolutionError("document identity is not resolved enough for automatic pipeline routing")
    if manifest.document_identity.source_type != SourceType.ANNUAL_REPORT:
        raise DocumentManifestResolutionError("legacy company/year pipeline currently accepts annual reports only")
    company = manifest.company_identity.resolved_company_key
    year = manifest.reporting_period.fiscal_year if manifest.reporting_period else None
    source_file = manifest.file.storage_path
    if not company or not year or not source_file:
        raise DocumentManifestResolutionError("company, fiscal year, and source file are required for legacy pipeline routing")
    return LegacyPipelineInputs(company=company, year=year, source_file=source_file)


def _clean_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _ocr_dependencies_available() -> bool:
    return bool(
        PYTESSERACT_AVAILABLE
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


def _run_ocr_on_pdf(path: Path) -> str:
    """Run OCR on an image-only or mixed PDF using tesseract."""
    if not PYTESSERACT_AVAILABLE or not shutil.which("tesseract"):
        return ""

    doc = fitz.open(path)
    try:
        ocr_texts = []
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            # Render page to image at 300 DPI for good OCR quality
            pix = page.get_pixmap(dpi=300)
            img_data = pix.tobytes("png")
            from io import BytesIO
            img = Image.open(BytesIO(img_data))
            # Run tesseract OCR
            text = pytesseract.image_to_string(img)
            if text.strip():
                ocr_texts.append(_clean_text(text))
        return "\n".join(ocr_texts).strip()
    except Exception:
        # On any OCR failure, return empty string to let the pipeline handle gracefully
        return ""
    finally:
        doc.close()


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
        # Run actual OCR when dependencies are available
        return _run_ocr_on_pdf(path)

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
            record["reporting_period_check"] = infer_document_reporting_period(text, filename=path.name)
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
                    "reporting_period_check": infer_document_reporting_period(text, filename=path.name),
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
