"""Generic processing entry point for Prometheus document intake.

Canonical flow:
    RAW FILE
    → identify_document(path)        [document_identifier.py]
    → DocumentIntakeManifest
    → SourceRouter.route(manifest)   [document_router.py]
    → RoutingDecision
    → ProcessorInterface.process(manifest, path)   [this file]
    → DocumentProcessingResult

Public API:
    process_document(path, *, execute=False) -> DocumentProcessingResult

Safe default: execute=False identifies and routes but does NOT invoke any
downstream intelligence pipeline.  Execution requires explicit intent.

Processor interface (Part 10):
    ProcessorInterface is the abstract base all future source processors must
    implement.  AnnualReportProcessor is the only concrete implementation in
    Phase 3; it bridges into the existing pipeline via the Phase 1 compatibility
    adapter (manifest_to_legacy_pipeline_inputs).

Error taxonomy (Part 15):
    DocumentIntakeError        — file invalid or unreadable
    IdentificationUnresolvedError — UNIDENTIFIED manifest
    ReviewRequiredError        — REVIEW_REQUIRED status
    UnsupportedSourceTypeError — source recognized but no processor
    ProcessorUnavailableError  — processor declared but not ready at runtime
    CompatibilityAdapterError  — legacy adapter conversion failed
    ProcessorExecutionError    — processor.process() raised
"""

from __future__ import annotations

import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

from knowledge.document_identifier import identify_document
from knowledge.document_intake import (
    ClassificationStatus,
    DocumentIntakeManifest,
    DocumentManifestResolutionError,
    LegacyPipelineInputs,
    SourceType,
    manifest_to_legacy_pipeline_inputs,
)
from knowledge.document_router import (
    ProcessorState,
    RouteStatus,
    RoutingDecision,
    SourceRouter,
)


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

class DocumentIntakeError(ValueError):
    """File could not be read or validated before identification."""


class IdentificationUnresolvedError(ValueError):
    """Company or source type could not be resolved from document content."""


class ReviewRequiredError(ValueError):
    """Document identity has unresolved signals; operator review is required."""
    def __init__(self, message: str, unresolved_fields: List[str] | None = None) -> None:
        super().__init__(message)
        self.unresolved_fields: List[str] = unresolved_fields or []


class UnsupportedSourceTypeError(ValueError):
    """Source type is recognized but no processor is implemented for it."""
    def __init__(self, message: str, source_type: str = "") -> None:
        super().__init__(message)
        self.source_type = source_type


class ProcessorUnavailableError(RuntimeError):
    """A processor is declared for this source type but is not available."""


class CompatibilityAdapterError(ValueError):
    """Legacy compatibility adapter (manifest_to_legacy_pipeline_inputs) failed."""


class ProcessorExecutionError(RuntimeError):
    """The processor raised an exception during execution."""


# ---------------------------------------------------------------------------
# Processing result
# ---------------------------------------------------------------------------

class ProcessorStatus(str, Enum):
    """High-level status of the process_document() call."""
    IDENTIFIED_ONLY = "IDENTIFIED_ONLY"   # execute=False, identification done
    ROUTED = "ROUTED"                      # execute=False, routing done
    EXECUTED = "EXECUTED"                  # execute=True, processor ran
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


@dataclass
class DocumentProcessingResult:
    """Structured result returned by process_document().

    Fields:
        manifest:         The DocumentIntakeManifest from identification.
        routing:          The RoutingDecision (None if identification failed).
        status:           High-level processing outcome.
        processor_output: LegacyPipelineInputs (annual report) or None.
        error:            Human-readable error description when status=ERROR.
        warnings:         Non-fatal notes accumulated across all stages.
        elapsed_seconds:  Wall-clock time for the full call.
        processed_at:     ISO-8601 UTC timestamp of completion.
    """
    manifest: Optional[DocumentIntakeManifest]
    routing: Optional[RoutingDecision]
    status: ProcessorStatus
    processor_output: Optional[Any]
    error: Optional[str]
    warnings: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    processed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "routing": self.routing.to_dict() if self.routing else None,
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "processor_output": (
                {
                    "company": self.processor_output.company,
                    "year": self.processor_output.year,
                    "source_file": self.processor_output.source_file,
                }
                if isinstance(self.processor_output, LegacyPipelineInputs)
                else None
            ),
            "error": self.error,
            "warnings": list(self.warnings),
            "elapsed_seconds": self.elapsed_seconds,
            "processed_at": self.processed_at,
        }


# ---------------------------------------------------------------------------
# Processor interface
# ---------------------------------------------------------------------------

class ProcessorInterface(ABC):
    """Abstract base for all source-type processors.

    Every source processor must implement this interface so intake/router
    governance cannot be bypassed.  Do not create five separate ad-hoc CLI
    routes or source-specific parallel intelligence systems.
    """

    @abstractmethod
    def can_process(self, manifest: DocumentIntakeManifest) -> bool:
        """Return True when this processor can handle *manifest*."""

    @abstractmethod
    def process(self, manifest: DocumentIntakeManifest, source_path: Path) -> Any:
        """Execute the processor and return a typed result.

        Raises ProcessorExecutionError on failure.
        """


# ---------------------------------------------------------------------------
# Annual-report processor (Phase 3 — only concrete implementation)
# ---------------------------------------------------------------------------

class AnnualReportProcessor(ProcessorInterface):
    """Bridges an ANNUAL_REPORT manifest into the existing legacy pipeline.

    Uses the Phase 1 compatibility adapter (manifest_to_legacy_pipeline_inputs)
    to convert manifest → LegacyPipelineInputs without rewriting any downstream
    stage.

    This processor does NOT invoke the full intelligence pipeline (discovery,
    extraction, financials, panel, …).  It returns the bridge inputs only.
    Invoking the downstream stages is the caller's explicit responsibility.
    """

    def can_process(self, manifest: DocumentIntakeManifest) -> bool:
        return manifest.document_identity.source_type == SourceType.ANNUAL_REPORT

    def process(
        self, manifest: DocumentIntakeManifest, source_path: Path
    ) -> LegacyPipelineInputs:
        """Return LegacyPipelineInputs via the compatibility adapter.

        Raises:
            CompatibilityAdapterError if the adapter rejects the manifest.
            ProcessorExecutionError on unexpected failures.
        """
        # Ensure the storage_path is set so the adapter can resolve source_file.
        if not manifest.file.storage_path:
            manifest.file.storage_path = str(source_path)

        try:
            return manifest_to_legacy_pipeline_inputs(manifest)
        except DocumentManifestResolutionError as exc:
            raise CompatibilityAdapterError(str(exc)) from exc
        except Exception as exc:
            raise ProcessorExecutionError(
                f"Annual-report processor failed unexpectedly: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Quarterly-report processor (Phase 4 Gate B — full implementation)
#
# Architecture contract:
#   • Storage path:      companies/<company>/<fy>/quarters/<q>/
#   • CompanyContext:    quarter: Optional[str] field — set from manifest
#   • Evidence boundary: quarterly evidence uses the SAME chunking + extraction
#                        schema as annual processing; it does NOT create a
#                        parallel quarterly intelligence universe
#   • Period roles:      ExtractedValue.period_role is annotated by the
#                        period_roles module after extraction
#   • Downstream:        processor is responsible ONLY for document-scoped
#                        ingestion; it does NOT trigger CIM/PCIM/Panel/Committee
#   • Registration:      QuarterlyReportProcessor is added to _PROCESSOR_REGISTRY
#                        and the router set to AVAILABLE only after the direct
#                        production proof passes (Phase 4 Gate B)
# ---------------------------------------------------------------------------

@dataclass
class QuarterlyProcessingResult:
    """Typed result returned by QuarterlyReportProcessor.process().

    Quarter identity uses FY + quarter label (e.g. "fy27", "Q1") rather than a
    calendar quarter so it aligns with the company's own fiscal calendar.

    Fields (Phase 4 Gate B extended):
        company:            Registry-resolved company slug.
        fiscal_year:        Company fiscal year label (e.g. "fy27").
        quarter:            Quarter label within the fiscal year ("Q1"–"Q4").
        period_label:       Human-readable period (e.g. "Q1 FY27").
        source_file:        Absolute path to the source document.
        storage_path:       Canonical path: companies/<co>/<fy>/quarters/<q>/
        status:             "SUCCESS" | "PARTIAL" | "ERROR"
        document_hash:      SHA-256 content hash from the manifest.
        source_type:        SourceType value from manifest.
        source_channel:     SourceChannel value from manifest.
        basis:              Detected entity scope ("consolidated"|"standalone"|"unknown").
        warnings:           Non-fatal notes from the processing run.
        extracted_fact_count: Number of ExtractedValue instances after period annotation.
        period_roles_found: Distinct period role values found in extracted values.
        chunks_path:        Path to written chunks JSON.
        manifest_path:      Path to written manifest JSON.
        raw_tables_path:    Path to written raw financial tables JSON.
        result_path:        Path to written processing result JSON.
    """
    company: str
    fiscal_year: str
    quarter: str
    period_label: str
    source_file: str
    storage_path: str
    # Extended fields (Phase 4 Gate B)
    status: str = "SUCCESS"
    document_hash: str = ""
    source_type: str = ""
    source_channel: str = ""
    basis: str = "unknown"
    warnings: List[str] = field(default_factory=list)
    extracted_fact_count: int = 0
    period_roles_found: List[str] = field(default_factory=list)
    chunks_path: str = ""
    manifest_path: str = ""
    raw_tables_path: str = ""
    result_path: str = ""

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "fiscal_year": self.fiscal_year,
            "quarter": self.quarter,
            "period_label": self.period_label,
            "source_file": self.source_file,
            "storage_path": self.storage_path,
            "status": self.status,
            "document_hash": self.document_hash,
            "source_type": self.source_type,
            "source_channel": self.source_channel,
            "basis": self.basis,
            "warnings": list(self.warnings),
            "extracted_fact_count": self.extracted_fact_count,
            "period_roles_found": list(self.period_roles_found),
            "chunks_path": self.chunks_path,
            "manifest_path": self.manifest_path,
            "raw_tables_path": self.raw_tables_path,
            "result_path": self.result_path,
        }


class QuarterlyReportProcessor(ProcessorInterface):
    """Canonical processor for QUARTERLY_REPORT source type.

    Processing flow:
        manifest + source_path
        → validate (IDENTIFIED + QUARTERLY_REPORT + quarter present)
        → build quarter-aware CompanyContext
        → create quarter storage directory
        → chunk document with smart_chunker (shared infrastructure)
        → discover financial sections (shared infrastructure)
        → extract raw financial tables (shared infrastructure)
        → annotate extracted values with period roles (quarterly-specific)
        → write quarterly_manifest.json, quarterly_chunks.json,
          quarterly_raw_tables.json, quarterly_processing_result.json
        → return QuarterlyProcessingResult

    This processor does NOT:
        - run annual report normalization/ratios/trends
        - invoke CIM/PCIM/Panel/Committee
        - overwrite any existing annual artifact
        - create a parallel quarterly intelligence system

    Common evidence boundary: the same ExtractedFinancialRow/ExtractedValue
    schema as annual processing, stored under companies/<co>/<fy>/quarters/<q>/.
    """

    def can_process(self, manifest: DocumentIntakeManifest) -> bool:
        return (
            manifest.document_identity.source_type == SourceType.QUARTERLY_REPORT
            and manifest.classification.status == ClassificationStatus.IDENTIFIED
        )

    def process(
        self, manifest: DocumentIntakeManifest, source_path: Path
    ) -> QuarterlyProcessingResult:
        """Execute quarterly ingestion and return QuarterlyProcessingResult.

        Raises:
            ProcessorUnavailableError: if manifest is not IDENTIFIED QUARTERLY_REPORT.
            ProcessorExecutionError:   on unexpected failures.
        """
        import json
        import time as _time

        # ── Validate preconditions ───────────────────────────────────────
        if manifest.classification.status != ClassificationStatus.IDENTIFIED:
            raise ProcessorUnavailableError(
                "QuarterlyReportProcessor requires status=IDENTIFIED. "
                f"Got: {manifest.classification.status.value}. "
                "Operator review is required before processing."
            )
        if manifest.document_identity.source_type != SourceType.QUARTERLY_REPORT:
            raise ProcessorUnavailableError(
                "QuarterlyReportProcessor can only process QUARTERLY_REPORT documents. "
                f"Got: {manifest.document_identity.source_type.value}."
            )

        reporting = manifest.reporting_period
        if not reporting or not reporting.fiscal_quarter:
            raise ProcessorUnavailableError(
                "QuarterlyReportProcessor requires a resolved fiscal_quarter in the manifest. "
                "Quarter is missing — cannot route to quarter storage."
            )

        company = manifest.company_identity.resolved_company_key
        fiscal_year = reporting.fiscal_year
        quarter = reporting.fiscal_quarter.value  # "Q1" … "Q4"

        if not company or not fiscal_year:
            raise ProcessorUnavailableError(
                "QuarterlyReportProcessor requires resolved company and fiscal_year. "
                f"company={company!r} fiscal_year={fiscal_year!r}."
            )

        period_label = f"{quarter} {fiscal_year.upper()}"
        storage_root = Path("companies") / company / fiscal_year / "quarters" / quarter
        warnings: List[str] = []

        try:
            # ── Create quarter storage directory ─────────────────────────
            storage_root.mkdir(parents=True, exist_ok=True)

            # ── Detect basis from entity scope ────────────────────────────
            entity_scope = getattr(manifest, "entity_scope", None)
            basis = entity_scope.value if entity_scope else "unknown"
            if basis in ("not_applicable", ""):
                basis = "unknown"

            # ── Step 1: Chunk the document ────────────────────────────────
            chunks_path = storage_root / "quarterly_chunks.json"
            self._run_chunker(source_path, chunks_path, warnings)

            # ── Step 2: Discover financial sections ───────────────────────
            discovery_path = storage_root / "quarterly_discovery.json"
            self._run_discovery(
                company=company,
                fiscal_year=fiscal_year,
                chunks_path=chunks_path,
                discovery_path=discovery_path,
                warnings=warnings,
            )

            # ── Step 3: Extract financial tables ──────────────────────────
            raw_tables_path = storage_root / "quarterly_raw_tables.json"
            extracted_fact_count, period_roles_found = self._run_extraction_and_annotate(
                company=company,
                fiscal_year=fiscal_year,
                quarter=quarter,
                chunks_path=chunks_path,
                discovery_path=discovery_path,
                raw_tables_path=raw_tables_path,
                warnings=warnings,
            )

            # ── Step 4: Write manifest JSON ───────────────────────────────
            manifest_path = storage_root / "quarterly_manifest.json"
            manifest_path.write_text(
                json.dumps(manifest.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )

            # ── Step 5: Build and write processing result ─────────────────
            result = QuarterlyProcessingResult(
                company=company,
                fiscal_year=fiscal_year,
                quarter=quarter,
                period_label=period_label,
                source_file=str(source_path.resolve()),
                storage_path=str(storage_root),
                status="SUCCESS",
                document_hash=manifest.file.content_hash,
                source_type=manifest.document_identity.source_type.value,
                source_channel=manifest.document_identity.source_channel.value,
                basis=basis,
                warnings=warnings,
                extracted_fact_count=extracted_fact_count,
                period_roles_found=sorted(set(period_roles_found)),
                chunks_path=str(chunks_path),
                manifest_path=str(manifest_path),
                raw_tables_path=str(raw_tables_path),
                result_path=str(storage_root / "quarterly_processing_result.json"),
            )
            result_path = storage_root / "quarterly_processing_result.json"
            result.result_path = str(result_path)
            result_path.write_text(
                json.dumps(result.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
            return result

        except (ProcessorUnavailableError, ProcessorExecutionError):
            raise
        except Exception as exc:
            raise ProcessorExecutionError(
                f"QuarterlyReportProcessor failed: {exc}"
            ) from exc

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _run_chunker(
        self, source_path: Path, chunks_path: Path, warnings: List[str]
    ) -> None:
        """Run smart_chunker on the source PDF and write chunks JSON."""
        try:
            from scripts.pdf_reader import extract_pages
            from scripts.smart_chunker import chunk_pages, persist_clean_chunks

            pages = extract_pages(str(source_path))
            persist_clean_chunks(
                chunk_pages(pages),
                company="",          # identity is in the manifest, not the chunks
                year="",
                document_type="quarterly_report",
                output_path=chunks_path,
            )
        except ImportError as exc:
            warnings.append(
                f"smart_chunker/pdf_reader not available ({exc}); chunks written as empty."
            )
            chunks_path.write_text(
                '{"company":"","year":"","document_type":"quarterly_report","chunk_count":0,"chunks":[]}',
                encoding="utf-8",
            )
        except Exception as exc:
            warnings.append(f"Chunking failed ({exc}); chunks written as empty.")
            chunks_path.write_text(
                '{"company":"","year":"","document_type":"quarterly_report","chunk_count":0,"chunks":[]}',
                encoding="utf-8",
            )

    def _run_discovery(
        self,
        *,
        company: str,
        fiscal_year: str,
        chunks_path: Path,
        discovery_path: Path,
        warnings: List[str],
    ) -> None:
        """Run financial discovery and write discovery JSON."""
        import json
        try:
            from knowledge.financials.discovery import discover_financial_sections
            result = discover_financial_sections(
                company=company,
                year=fiscal_year,
                chunk_path=chunks_path,
            )
            discovery_path.write_text(
                json.dumps(result.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            warnings.append(f"Financial discovery failed ({exc}); wrote empty discovery.")
            # Write minimal valid discovery so extraction can detect missing sections.
            discovery_path.write_text(
                '{"sections": {}, "source_documents": [], "generated_at": ""}',
                encoding="utf-8",
            )

    def _run_extraction_and_annotate(
        self,
        *,
        company: str,
        fiscal_year: str,
        quarter: str,
        chunks_path: Path,
        discovery_path: Path,
        raw_tables_path: Path,
        warnings: List[str],
    ) -> tuple[int, List[str]]:
        """Run financial extraction + period role annotation; write raw_tables JSON.

        Returns (extracted_fact_count, period_roles_found).
        """
        import json

        extracted_fact_count = 0
        period_roles_found: List[str] = []

        try:
            from knowledge.financials.extractor import extract_financial_tables
            from knowledge.financials.period_roles import annotate_period_roles, FinancialPeriodRole

            extraction = extract_financial_tables(
                company=company,
                year=fiscal_year,
                chunk_path=chunks_path,
                discovery_path=discovery_path,
            )

            # Derive 2-digit FY and quarter int for the period-role interpreter.
            context_fy = self._parse_fy_int(fiscal_year)
            context_q = int(quarter[1])  # "Q1" → 1, "Q4" → 4

            # Annotate all extracted values with period roles.
            all_values = []
            for table_rows in extraction.tables.values():
                for row in table_rows:
                    all_values.extend(row.values)

            annotate_period_roles(
                all_values,
                context_fy=context_fy,
                context_quarter=context_q,
            )

            for v in all_values:
                extracted_fact_count += 1
                if v.period_role:
                    period_roles_found.append(v.period_role)

            # Write raw tables with period roles.
            raw_tables_path.write_text(
                json.dumps(extraction.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )

        except RuntimeError as exc:
            # extraction raises RuntimeError for empty chunks or invalid discovery.
            warnings.append(f"Financial extraction skipped: {exc}")
            raw_tables_path.write_text(
                '{"tables": {}, "rejections": [], "source_documents": []}',
                encoding="utf-8",
            )
        except Exception as exc:
            warnings.append(f"Financial extraction failed ({exc}); raw tables empty.")
            raw_tables_path.write_text(
                '{"tables": {}, "rejections": [], "source_documents": []}',
                encoding="utf-8",
            )

        return extracted_fact_count, period_roles_found

    @staticmethod
    def _parse_fy_int(fiscal_year: str) -> int:
        """Parse 2-digit FY integer from "fy27" → 27, "FY2027" → 27.

        Returns 0 on parse failure (period role interpretation will return UNKNOWN).
        """
        import re
        m = re.search(r"(\d{2,4})", fiscal_year)
        if not m:
            return 0
        n = int(m.group(1))
        return n % 100 if n > 100 else n


# ---------------------------------------------------------------------------
# Investor presentation processing result
# ---------------------------------------------------------------------------

@dataclass
class InvestorPresentationResult:
    """Typed result returned by InvestorPresentationProcessor.process().

    An investor presentation covers one or more periods (e.g. "Full Year & Q4
    FY26"), so it carries a period_label rather than a single quarter.

    Fields:
        company:              Registry-resolved company slug.
        fiscal_year:          Company fiscal year label (e.g. "fy26").
        period_label:         Human-readable coverage (e.g. "Full Year & Q4 FY26").
        context_quarter:      Quarter used for period-role annotation (1–4), or None
                              when the manifest does not carry explicit quarter evidence.
                              Never fabricated — missing is preserved as None.
        source_file:          Absolute path to the source document.
        storage_path:         Canonical path: companies/<co>/<fy>/presentations/<hash>/
        status:               "SUCCESS" | "PARTIAL_*" | "ERROR"
        document_hash:        SHA-256 content hash from the manifest.
        source_type:          SourceType value from manifest.
        source_channel:       SourceChannel value from manifest.
        warnings:             Non-fatal notes from the processing run.
        extracted_fact_count: Number of ExtractedValue instances after annotation.
        period_roles_found:   Distinct period role values found in extracted values.
        slide_count:          Total page count of the source PDF.
        chunks_path:          Path to written chunks JSON.
        manifest_path:        Path to written manifest JSON.
        raw_tables_path:      Path to written raw financial tables JSON.
        result_path:          Path to written processing result JSON.
    """
    company: str
    fiscal_year: str
    period_label: str
    context_quarter: Optional[int]
    source_file: str
    storage_path: str
    status: str = "SUCCESS"
    document_hash: str = ""
    source_type: str = ""
    source_channel: str = ""
    warnings: List[str] = field(default_factory=list)
    extracted_fact_count: int = 0
    period_roles_found: List[str] = field(default_factory=list)
    slide_count: int = 0
    chunks_path: str = ""
    manifest_path: str = ""
    raw_tables_path: str = ""
    result_path: str = ""

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "fiscal_year": self.fiscal_year,
            "period_label": self.period_label,
            "context_quarter": self.context_quarter,
            "source_file": self.source_file,
            "storage_path": self.storage_path,
            "status": self.status,
            "document_hash": self.document_hash,
            "source_type": self.source_type,
            "source_channel": self.source_channel,
            "warnings": list(self.warnings),
            "extracted_fact_count": self.extracted_fact_count,
            "period_roles_found": list(self.period_roles_found),
            "slide_count": self.slide_count,
            "chunks_path": self.chunks_path,
            "manifest_path": self.manifest_path,
            "raw_tables_path": self.raw_tables_path,
            "result_path": self.result_path,
        }


# ---------------------------------------------------------------------------
# Investor presentation processor
# ---------------------------------------------------------------------------

class InvestorPresentationProcessor(ProcessorInterface):
    """Canonical processor for INVESTOR_PRESENTATION source type.

    An investor presentation is a company-authored slide deck filed with an
    exchange or published directly, covering one or more financial periods.
    It shares the common evidence schema (ExtractedFinancialRow / ExtractedValue)
    so its output flows into the same Prometheus intelligence layer as quarterly
    and annual evidence.

    Key design properties:
    - Storage is document-scoped (presentations/<hash>/) to prevent overwriting
      annual or quarterly artifacts when multiple presentations exist.
    - Period roles are annotated using the explicitly evidenced quarter from the
      manifest.  When fiscal_quarter is None (full-year-only presentations),
      context_quarter stays None — quarterly patterns return UNKNOWN rather than
      being mapped to a fabricated quarter.
    - Management claims in narrative slides are NOT extracted in this version;
      only structured financial table evidence is captured.
    - PARTIAL_* statuses signal bounded incompleteness without failing the run.
    """

    def can_process(self, manifest: DocumentIntakeManifest) -> bool:
        from knowledge.document_intake import SourceType
        return (
            manifest.classification.status == ClassificationStatus.IDENTIFIED
            and manifest.document_identity.source_type == SourceType.INVESTOR_PRESENTATION
        )

    def process(
        self,
        manifest: DocumentIntakeManifest,
        source_path: Path,
    ) -> InvestorPresentationResult:
        """Execute the investor presentation pipeline.

        Raises:
            ProcessorUnavailableError: if manifest is not IDENTIFIED INVESTOR_PRESENTATION.
            ProcessorExecutionError:   on unexpected failures.
        """
        import json
        import time as _time
        from knowledge.document_intake import SourceType

        # ── Validate preconditions ───────────────────────────────────────────
        if manifest.classification.status != ClassificationStatus.IDENTIFIED:
            raise ProcessorUnavailableError(
                "InvestorPresentationProcessor requires status=IDENTIFIED. "
                f"Got: {manifest.classification.status.value}. "
                "Operator review is required before processing."
            )
        if manifest.document_identity.source_type != SourceType.INVESTOR_PRESENTATION:
            raise ProcessorUnavailableError(
                "InvestorPresentationProcessor can only process INVESTOR_PRESENTATION documents. "
                f"Got: {manifest.document_identity.source_type.value}."
            )

        company = manifest.company_identity.resolved_company_key
        reporting = manifest.reporting_period
        fiscal_year = reporting.fiscal_year if reporting else None

        if not company or not fiscal_year:
            raise ProcessorUnavailableError(
                "InvestorPresentationProcessor requires resolved company and fiscal_year. "
                f"company={company!r} fiscal_year={fiscal_year!r}."
            )

        # Investor presentations cover multiple periods; fiscal_quarter may be null.
        # Preserve absence of quarter evidence — never fabricate a quarter.
        fiscal_quarter = reporting.fiscal_quarter if reporting else None
        context_quarter: Optional[int] = (
            int(fiscal_quarter.value[1]) if fiscal_quarter else None
        )

        # Period label from manifest or derive from fiscal year.
        period_label = fiscal_year.upper()
        if fiscal_quarter:
            period_label = f"{fiscal_quarter.value} {fiscal_year.upper()}"

        # Document-scoped storage path prevents collision with quarterly artifacts.
        doc_hash_short = manifest.file.content_hash.replace("sha256:", "")[:16]
        storage_root = (
            Path("companies") / company / fiscal_year / "presentations" / doc_hash_short
        )
        warnings: List[str] = []

        # Slide count from PDF page count (best-effort).
        slide_count = self._get_slide_count(source_path, warnings)

        try:
            # ── Create storage directory ─────────────────────────────────────
            storage_root.mkdir(parents=True, exist_ok=True)

            # ── Step 1: Chunk the document ────────────────────────────────────
            chunks_path = storage_root / "presentation_chunks.json"
            self._run_chunker(source_path, chunks_path, warnings)

            # ── Step 2: Discover financial sections ───────────────────────────
            discovery_path = storage_root / "presentation_discovery.json"
            self._run_discovery(
                company=company,
                fiscal_year=fiscal_year,
                chunks_path=chunks_path,
                discovery_path=discovery_path,
                warnings=warnings,
            )

            # ── Step 3: Extract financial tables + annotate period roles ──────
            raw_tables_path = storage_root / "presentation_raw_tables.json"
            context_fy = self._parse_fy_int(fiscal_year)
            extracted_fact_count, period_roles_found = self._run_extraction_and_annotate(
                company=company,
                fiscal_year=fiscal_year,
                context_fy=context_fy,
                context_quarter=context_quarter,
                chunks_path=chunks_path,
                discovery_path=discovery_path,
                raw_tables_path=raw_tables_path,
                warnings=warnings,
            )

            # ── Step 4: Write manifest JSON ───────────────────────────────────
            manifest_path = storage_root / "presentation_manifest.json"
            manifest_path.write_text(
                json.dumps(manifest.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )

            # ── Step 5: Determine status ──────────────────────────────────────
            status = "SUCCESS"
            if extracted_fact_count == 0:
                status = "PARTIAL_COMMON_EVIDENCE_CONTRACT_REQUIRED"
                warnings.append(
                    "No financial facts extracted. Presentation may use visual-only "
                    "tables not captured by text extraction."
                )
            elif not period_roles_found:
                status = "PARTIAL_COMMON_EVIDENCE_CONTRACT_REQUIRED"
                warnings.append("Financial facts extracted but no period roles could be assigned.")

            # ── Step 6: Build and write processing result ─────────────────────
            result = InvestorPresentationResult(
                company=company,
                fiscal_year=fiscal_year,
                period_label=period_label,
                context_quarter=context_quarter,
                source_file=str(source_path.resolve()),
                storage_path=str(storage_root),
                status=status,
                document_hash=manifest.file.content_hash,
                source_type=manifest.document_identity.source_type.value,
                source_channel=manifest.document_identity.source_channel.value,
                warnings=warnings,
                extracted_fact_count=extracted_fact_count,
                period_roles_found=sorted(set(period_roles_found)),
                slide_count=slide_count,
                chunks_path=str(chunks_path),
                manifest_path=str(manifest_path),
                raw_tables_path=str(raw_tables_path),
            )
            result_path = storage_root / "presentation_result.json"
            result.result_path = str(result_path)
            result_path.write_text(
                json.dumps(result.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
            return result

        except (ProcessorUnavailableError, ProcessorExecutionError):
            raise
        except Exception as exc:
            raise ProcessorExecutionError(
                f"InvestorPresentationProcessor failed: {exc}"
            ) from exc

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _get_slide_count(source_path: Path, warnings: List[str]) -> int:
        try:
            import pymupdf
            doc = pymupdf.open(str(source_path))
            return doc.page_count
        except Exception:
            try:
                import fitz
                doc = fitz.open(str(source_path))
                return doc.page_count
            except Exception as exc:
                warnings.append(f"Could not determine slide count: {exc}")
                return 0

    def _run_chunker(
        self, source_path: Path, chunks_path: Path, warnings: List[str]
    ) -> None:
        try:
            from scripts.pdf_reader import extract_pages
            from scripts.smart_chunker import chunk_pages, persist_clean_chunks

            pages = extract_pages(str(source_path))
            persist_clean_chunks(
                chunk_pages(pages),
                company="",
                year="",
                document_type="investor_presentation",
                output_path=chunks_path,
            )
        except ImportError as exc:
            warnings.append(
                f"smart_chunker/pdf_reader not available ({exc}); chunks written as empty."
            )
            chunks_path.write_text(
                '{"company":"","year":"","document_type":"investor_presentation","chunk_count":0,"chunks":[]}',
                encoding="utf-8",
            )
        except Exception as exc:
            warnings.append(f"Chunking failed ({exc}); chunks written as empty.")
            chunks_path.write_text(
                '{"company":"","year":"","document_type":"investor_presentation","chunk_count":0,"chunks":[]}',
                encoding="utf-8",
            )

    def _run_discovery(
        self,
        *,
        company: str,
        fiscal_year: str,
        chunks_path: Path,
        discovery_path: Path,
        warnings: List[str],
    ) -> None:
        import json
        try:
            from knowledge.financials.discovery import discover_financial_sections
            result = discover_financial_sections(
                company=company,
                year=fiscal_year,
                chunk_path=chunks_path,
            )
            discovery_path.write_text(
                json.dumps(result.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            warnings.append(f"Financial discovery failed ({exc}); wrote empty discovery.")
            discovery_path.write_text(
                '{"sections": {}, "source_documents": [], "generated_at": ""}',
                encoding="utf-8",
            )

    def _run_extraction_and_annotate(
        self,
        *,
        company: str,
        fiscal_year: str,
        context_fy: int,
        context_quarter: Optional[int],
        chunks_path: Path,
        discovery_path: Path,
        raw_tables_path: Path,
        warnings: List[str],
    ) -> tuple[int, List[str]]:
        import json

        extracted_fact_count = 0
        period_roles_found: List[str] = []

        try:
            from knowledge.financials.extractor import extract_financial_tables
            from knowledge.financials.period_roles import annotate_period_roles

            extraction = extract_financial_tables(
                company=company,
                year=fiscal_year,
                chunk_path=chunks_path,
                discovery_path=discovery_path,
            )

            all_values = []
            for table_rows in extraction.tables.values():
                for row in table_rows:
                    all_values.extend(row.values)

            annotate_period_roles(
                all_values,
                context_fy=context_fy,
                context_quarter=context_quarter,
            )

            for v in all_values:
                extracted_fact_count += 1
                if v.period_role:
                    period_roles_found.append(v.period_role)

            raw_tables_path.write_text(
                json.dumps(extraction.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )

        except RuntimeError as exc:
            warnings.append(f"Financial extraction skipped: {exc}")
            raw_tables_path.write_text(
                '{"tables": {}, "rejections": [], "source_documents": []}',
                encoding="utf-8",
            )
        except Exception as exc:
            warnings.append(f"Financial extraction failed ({exc}); raw tables empty.")
            raw_tables_path.write_text(
                '{"tables": {}, "rejections": [], "source_documents": []}',
                encoding="utf-8",
            )

        return extracted_fact_count, period_roles_found

    @staticmethod
    def _parse_fy_int(fiscal_year: str) -> int:
        import re
        m = re.search(r"(\d{2,4})", fiscal_year)
        if not m:
            return 0
        n = int(m.group(1))
        return n % 100 if n > 100 else n


# ---------------------------------------------------------------------------
# Earnings call transcript — speaker / section / claim contracts
# ---------------------------------------------------------------------------

import re as _re
from enum import Enum as _Enum


class SpeakerRole(str, _Enum):
    """Semantic role of a transcript speaker.

    Attribution must fail conservatively: if the speaker cannot be matched to
    a participant list entry or a definitive label (Operator, Moderator),
    assign UNKNOWN.  Never guess from conversational context alone.
    """
    MANAGEMENT = "MANAGEMENT"
    ANALYST = "ANALYST"
    OPERATOR = "OPERATOR"
    MODERATOR = "MODERATOR"
    OTHER_COMPANY = "OTHER_COMPANY"
    UNKNOWN = "UNKNOWN"


class TranscriptSection(str, _Enum):
    """High-level section of an earnings call transcript."""
    INTRO = "INTRO"
    PREPARED_REMARKS = "PREPARED_REMARKS"
    Q_AND_A = "Q_AND_A"
    OPERATOR_TURN = "OPERATOR_TURN"
    UNKNOWN = "UNKNOWN"


class ManagementClaimType(str, _Enum):
    """Semantic type of a management claim in the transcript.

    These are CLAIM semantics only — not outcomes or proven facts.
    'Said' is never 'did' is never 'outcome'.
    """
    FACTUAL_STATEMENT = "FACTUAL_STATEMENT"
    EXPLANATION = "EXPLANATION"
    GUIDANCE = "GUIDANCE"
    TARGET = "TARGET"
    EXPECTATION = "EXPECTATION"
    COMMITMENT = "COMMITMENT"
    INTENTION = "INTENTION"
    STRATEGIC_PRIORITY = "STRATEGIC_PRIORITY"
    RISK_ACKNOWLEDGEMENT = "RISK_ACKNOWLEDGEMENT"
    UNCERTAINTY = "UNCERTAINTY"


# Qualifier words that must be preserved (never stripped during normalization).
_QUALIFIER_WORDS = (
    "expect", "expecting", "target", "hope", "intend", "planning",
    "may", "could", "might", "would", "likely", "probably",
    "approximately", "around", "roughly", "subject to", "depending on",
    "difficult to predict", "no guidance", "aspire", "aim",
    "potentially", "possibly", "if", "assuming",
)

# Regex patterns for claim-type classification.
_RE_COMMITMENT  = _re.compile(r"\b(commit(?:ted|ment)?|pledge|promise|ensure|will\s+complete|will\s+deliver)\b", _re.I)
_RE_EXPECTATION = _re.compile(r"\b(expect(?:ing)?|anticipat(?:e|ed)|looking\s+to|foresee)\b", _re.I)
_RE_TARGET      = _re.compile(r"\b(target(?:ing)?|aim(?:ing)?|goal|objective|aspir(?:e|ing|ation)|strive)\b", _re.I)
_RE_GUIDANCE    = _re.compile(r"\b(guidance|guid(?:e|ed|ing)|forecast(?:ing)?|project(?:ed|ing)?|outlook)\b", _re.I)
_RE_INTENTION   = _re.compile(r"\b(intend|plan(?:ning)?|going\s+to|looking\s+to|set\s+to)\b", _re.I)
_RE_UNCERTAINTY = _re.compile(r"\b(may|could|might|possibly|potentially|depend(?:ing)?|difficult|challenging|uncertain)\b", _re.I)
_RE_RISK        = _re.compile(r"\b(risk|headwind|challenge|concern|volatil(?:e|ity)|adverse|threat)\b", _re.I)
_RE_STRATEGIC   = _re.compile(r"\b(strateg(?:y|ic)|priorit(?:y|ies)|focus|initiative|invest(?:ment|ing))\b", _re.I)

# Speaker-label pattern: "Name:" or "Name - Title:" at start of a paragraph.
_RE_SPEAKER_LABEL = _re.compile(
    r"^([A-Z][A-Za-z0-9 \.\-\']{2,60}):\s+",
    _re.MULTILINE,
)
# Operator / Moderator labels (case-insensitive exact role names).
_RE_OPERATOR_LABEL  = _re.compile(r"^Operator\s*:", _re.IGNORECASE | _re.MULTILINE)
_RE_MODERATOR_LABEL = _re.compile(r"^Moderator\s*:", _re.IGNORECASE | _re.MULTILINE)

# Section boundary markers.
_RE_SECTION_PREPARED  = _re.compile(r"\bprepared\s+remarks\b", _re.IGNORECASE)
_RE_SECTION_QNA       = _re.compile(r"\b(question[\s\-]+and[\s\-]+answer|q\s*&\s*a)\s+session\b", _re.IGNORECASE)
_RE_OPERATOR_BRIDGE   = _re.compile(r"\byour\s+next\s+question\s+(?:is\s+)?(?:comes?\s+)?from\b", _re.IGNORECASE)

# Analyst firm suffixes used to classify analyst speakers without participant list.
_RE_ANALYST_FIRM = _re.compile(
    r"\b(?:securities|research|capital|bank(?:ing)?|brokerage|advisory|"
    r"partners?|asset\s+management|equity|financial\s+services)\b",
    _re.IGNORECASE,
)

# Honorific-prefixed participant name line in a participant list section.
# Matches lines like "MR. S. RANGARAJAN – CHAIRMAN & MD" that appear without
# bullet markers in some transcript formats (e.g. BSE-filed concall PDFs).
# Only applied when inside a known MANAGEMENT or ANALYST section header block.
_RE_PARTICIPANT_HONORIFIC = _re.compile(
    r"^(?:MR\.|MS\.|DR\.|PROF\.|SHRI\b|SH\.\s*|SMT\.|MRS\.|MR\s+|MS\s+)\s*[A-Z]",
    _re.IGNORECASE,
)

# Speaker label terminated at end of line (no trailing text after the colon).
# Complements _RE_SPEAKER_LABEL which requires ":\s+" (colon + content).
# Handles lines like "Moderator:" or "Prayasi Patel:" that appear as speaker
# headings in some transcript PDFs where content follows on the next line.
_RE_BARE_SPEAKER_LABEL = _re.compile(
    r"^([A-Z][A-Za-z0-9 \.\-\']{2,60}):\s*$",
)

_TRANSCRIPT_METADATA_LABELS = {
    "date",
    "to",
    "scrip code",
    "symbol",
    "sub",
    "subject",
}


def _normalize_speaker_name(name: str) -> str:
    """Normalize a transcript speaker label for conservative role lookup."""
    cleaned = _re.sub(r"\s+", " ", str(name or "").strip())
    cleaned = _re.sub(r"\s*[-–—]\s*.+$", "", cleaned).strip()
    return cleaned


def _classify_claim_type(text: str) -> ManagementClaimType:
    """Classify a management statement into a claim type using keyword heuristics.

    Priority: COMMITMENT > TARGET > GUIDANCE > EXPECTATION > INTENTION >
              RISK_ACKNOWLEDGEMENT > STRATEGIC_PRIORITY > UNCERTAINTY >
              EXPLANATION > FACTUAL_STATEMENT.
    """
    if _RE_COMMITMENT.search(text):
        return ManagementClaimType.COMMITMENT
    if _RE_TARGET.search(text):
        return ManagementClaimType.TARGET
    if _RE_GUIDANCE.search(text):
        return ManagementClaimType.GUIDANCE
    if _RE_EXPECTATION.search(text):
        return ManagementClaimType.EXPECTATION
    if _RE_INTENTION.search(text):
        return ManagementClaimType.INTENTION
    if _RE_RISK.search(text):
        return ManagementClaimType.RISK_ACKNOWLEDGEMENT
    if _RE_STRATEGIC.search(text):
        return ManagementClaimType.STRATEGIC_PRIORITY
    if _RE_UNCERTAINTY.search(text):
        return ManagementClaimType.UNCERTAINTY
    # Explanation: sentence containing "because", "due to", "as a result", "since"
    if _re.search(r"\b(because|due\s+to|as\s+a\s+result|since|therefore|driven\s+by)\b", text, _re.I):
        return ManagementClaimType.EXPLANATION
    return ManagementClaimType.FACTUAL_STATEMENT


def _extract_qualifiers(text: str) -> List[str]:
    """Return qualifier words found in text (preserving uncertainty semantics)."""
    found = []
    lower = text.lower()
    for q in _QUALIFIER_WORDS:
        if q in lower:
            found.append(q)
    return found


def _classify_speaker_role(
    name: str,
    participant_registry: dict,
    company_key: str,
) -> SpeakerRole:
    """Classify a speaker label into a SpeakerRole.

    Lookup priority:
    1. Exact match in participant_registry (built from participant list).
    2. 'Operator' or 'Moderator' exact label.
    3. Analyst-firm suffix in the name string.
    4. Company name/key substring in name.
    5. UNKNOWN (conservative fallback).
    """
    normalized_name = _normalize_speaker_name(name)
    name_lower = normalized_name.lower().strip()

    if name_lower == "operator":
        return SpeakerRole.OPERATOR
    if name_lower == "moderator":
        return SpeakerRole.MODERATOR

    # Check participant registry first.
    for reg_name, reg_role in participant_registry.items():
        reg_lower = _normalize_speaker_name(reg_name).lower()
        if not reg_lower:
            continue
        if reg_lower == name_lower:
            return reg_role
        if len(reg_lower) >= 4 and (reg_lower in name_lower or name_lower in reg_lower):
            return reg_role

    # Heuristic: analyst firm suffix in name/label.
    if _RE_ANALYST_FIRM.search(name):
        return SpeakerRole.ANALYST

    # Heuristic: company key in name.
    if company_key and company_key.lower() in name_lower:
        return SpeakerRole.MANAGEMENT

    return SpeakerRole.UNKNOWN


def _parse_participant_list(text: str) -> dict:
    """Extract a speaker → role registry from the participant list section.

    Looks for sections labelled "Management", "Company Speakers", "Analysts",
    "Analysts Participating" etc. and builds a {name_lower: SpeakerRole} dict.
    Conservative: only entries clearly under a Management or Analyst header
    are classified; everything else stays out of the registry.
    """
    def _extract_name(line: str) -> str:
        # Strip leading bullet markers first, then strip trailing role/title suffix.
        stripped = _re.sub(r"^\s*[-–—•·*]\s*", "", line.strip())
        stripped = _re.sub(r"\s*[-–—]\s*.+", "", stripped).strip()
        return _re.sub(r"\s*,\s*(?:chief|cfo|ceo|founder|executive|investor|general|managing|director|president|vice)\b.+", "", stripped, flags=_re.IGNORECASE).strip()

    registry: dict = {}
    mode: Optional[SpeakerRole] = None
    lines = [line.strip() for line in text[:8000].splitlines()]
    pending_bullet = False
    for idx, line in enumerate(lines):
        lower = line.lower()
        next_lower = lines[idx + 1].lower() if idx + 1 < len(lines) else ""

        if lower.rstrip(":") in {"management", "company speakers", "company participants"}:
            mode = SpeakerRole.MANAGEMENT
            continue
        if (
            "participants" in lower
            and ("question" in lower or "question" in next_lower)
        ) or lower.rstrip(":") in {"analysts", "analyst participants", "investors"}:
            mode = SpeakerRole.ANALYST
            continue
        if lower in {"questions", "question"} and mode == SpeakerRole.ANALYST:
            continue
        # Bare "NAME:" line (colon at end, no trailing content) — handles section
        # headers and body-speaker labels that don't use ":\s+" format.
        m_bare = _RE_BARE_SPEAKER_LABEL.match(line)
        if m_bare:
            bare_lower = m_bare.group(1).strip().lower()
            if bare_lower in {"management", "company speakers", "company participants"}:
                mode = SpeakerRole.MANAGEMENT
            elif bare_lower in {"analysts", "analyst participants", "investors"}:
                mode = SpeakerRole.ANALYST
            else:
                # Any real speaker name ("Moderator:", "Prayasi Patel:", etc.)
                # terminates the participant list section.
                mode = None
            continue
        m_label = _RE_SPEAKER_LABEL.match(line)
        if m_label:
            label_lower = m_label.group(1).strip().lower()
            if label_lower in {"management", "company speakers", "company participants"}:
                # The MANAGEMENT: speaker-label may carry the first participant
                # name on the same line: "MANAGEMENT: MR. S. RANGARAJAN – CMD".
                mode = SpeakerRole.MANAGEMENT
                remainder = line[m_label.end():].strip()
                if remainder and _RE_PARTICIPANT_HONORIFIC.match(remainder):
                    pname = _extract_name(remainder)
                    pname = _re.sub(
                        r"^(?:MR\.|MS\.|DR\.|PROF\.|SHRI\b|SH\.\s*|SMT\.|MRS\.|MR\s+|MS\s+)\s*",
                        "", pname, flags=_re.IGNORECASE,
                    ).strip()
                    if len(pname) > 2:
                        registry[_normalize_speaker_name(pname)] = mode
            elif label_lower in {"analysts", "analyst participants", "investors"}:
                mode = SpeakerRole.ANALYST
            else:
                # All other speaker labels (Moderator, real speaker names, etc.)
                # end the participant list block.
                mode = None
            continue
        # Honorific-prefixed participant name without a bullet marker.
        # Fires only inside a known MANAGEMENT / ANALYST section block, so
        # honorific references later in the call body (customer names, DRDO,
        # acquisition-target names) are never captured — the first real
        # speaker label above resets mode to None.
        if mode in (SpeakerRole.MANAGEMENT, SpeakerRole.ANALYST):
            if _RE_PARTICIPANT_HONORIFIC.match(line):
                name = _extract_name(line)
                # Strip leading honorific: "MR. S. RANGARAJAN" → "S. RANGARAJAN"
                name = _re.sub(
                    r"^(?:MR\.|MS\.|DR\.|PROF\.|SHRI\b|SH\.\s*|SMT\.|MRS\.|MR\s+|MS\s+)\s*",
                    "", name, flags=_re.IGNORECASE,
                ).strip()
                if len(name) > 2:
                    registry[_normalize_speaker_name(name)] = mode
                continue
        if line in {"▪", "•", "-", "–", "*"}:
            pending_bullet = True
            continue
        if not line.startswith(("▪", "•", "-", "–", "*")) and not pending_bullet:
            continue

        name = _extract_name(line)
        if len(name) > 2 and mode in (SpeakerRole.MANAGEMENT, SpeakerRole.ANALYST):
            registry[_normalize_speaker_name(name)] = mode
        pending_bullet = False

    return registry


def _page_for_offset(offset: int, page_ranges: Optional[List[tuple[int, int, int]]]) -> Optional[int]:
    if not page_ranges:
        return None
    for page, start, end in page_ranges:
        if start <= offset < end:
            return page
    return page_ranges[-1][0] if page_ranges else None


def _segment_turns(
    text: str,
    participant_registry: dict,
    company_key: str,
    page_ranges: Optional[List[tuple[int, int, int]]] = None,
) -> List[dict]:
    """Segment transcript text into speaker turns.

    Returns a list of turn dicts with keys:
        turn_index, raw_speaker, speaker_role, text, is_question, section.

    Conservative attribution: unknown speakers stay UNKNOWN.
    Analyst questions are only those attributed to ANALYST speakers.
    """
    turns: List[dict] = []
    current_section = TranscriptSection.INTRO

    # Split on speaker labels.
    matches = [
        m for m in _RE_SPEAKER_LABEL.finditer(text)
        if _normalize_speaker_name(m.group(1)).lower() not in _TRANSCRIPT_METADATA_LABELS
    ]
    if not matches:
        return turns

    for i, m in enumerate(matches):
        preamble_start = matches[i - 1].end() if i > 0 else 0
        preamble_text = text[preamble_start:m.start()]
        if _RE_SECTION_PREPARED.search(preamble_text):
            current_section = TranscriptSection.PREPARED_REMARKS
        elif _RE_SECTION_QNA.search(preamble_text):
            current_section = TranscriptSection.Q_AND_A

        raw_speaker = m.group(1).strip()
        normalized_speaker = _normalize_speaker_name(raw_speaker)
        start_of_text = m.end()
        end_of_text = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        turn_text = text[start_of_text:end_of_text].strip()

        # Determine section from turn content.
        if _RE_SECTION_PREPARED.search(turn_text) or _RE_SECTION_PREPARED.search(raw_speaker):
            current_section = TranscriptSection.PREPARED_REMARKS
        elif _RE_SECTION_QNA.search(turn_text) or _RE_OPERATOR_BRIDGE.search(turn_text):
            current_section = TranscriptSection.Q_AND_A

        role = _classify_speaker_role(raw_speaker, participant_registry, company_key)

        if role in (SpeakerRole.OPERATOR, SpeakerRole.MODERATOR):
            section = TranscriptSection.OPERATOR_TURN
        else:
            section = current_section

        # A turn is a question when:
        # - attributed to ANALYST, AND
        # - ends with a question mark OR contains a question pattern
        is_question = (
            role == SpeakerRole.ANALYST
            and bool(_re.search(r"\?", turn_text))
        )

        turns.append({
            "turn_index": i,
            "raw_speaker": raw_speaker,
            "normalized_speaker": normalized_speaker,
            "speaker_role": role.value,
            "section": section.value,
            "page": _page_for_offset(m.start(), page_ranges),
            "text": turn_text,
            "is_question": is_question,
            "question_turn_index": None,  # filled in Q&A linking pass
        })

    # Q&A linking: link each MANAGEMENT turn to the most recent ANALYST question.
    last_question_idx = None
    for t in turns:
        if t["is_question"]:
            last_question_idx = t["turn_index"]
        elif t["speaker_role"] == SpeakerRole.MANAGEMENT.value and last_question_idx is not None:
            t["question_turn_index"] = last_question_idx

    return turns


def _extract_management_claims(turns: List[dict], source_period: str) -> List[dict]:
    """Extract management claim candidates from management turns.

    Returns a list of claim dicts.  Each claim preserves:
      - speaker, role, section, raw_text, claim_type, qualifiers,
        source_period, target_period (None when not inferable), turn_index.

    Analyst turns are never a source of management claims.
    Operator turns are never a source of substantive evidence.
    """
    claims: List[dict] = []
    for turn in turns:
        if turn["speaker_role"] not in (
            SpeakerRole.MANAGEMENT.value,
            SpeakerRole.OTHER_COMPANY.value,
        ):
            continue

        # Split into sentences for finer-grained claim extraction.
        sentences = _re.split(r"(?<=[.!?])\s+", turn["text"])
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 20:
                continue

            claim_type = _classify_claim_type(sent)
            qualifiers = _extract_qualifiers(sent)

            # Attempt to detect target period if different from source period.
            # Pattern: "by Q3 FY27", "in FY28", "next quarter", etc.
            target_period: Optional[str] = None
            tp_match = _re.search(
                r"\b(?:by|in|during|for|before)\s+(q[1-4]\s*fy\d{2,4}|fy\d{2,4}|next\s+quarter|next\s+year)\b",
                sent, _re.IGNORECASE
            )
            if tp_match:
                target_period = tp_match.group(1).strip()

            claims.append({
                "speaker": turn["raw_speaker"],
                "normalized_speaker": turn.get("normalized_speaker"),
                "speaker_role": turn["speaker_role"],
                "section": turn["section"],
                "raw_text": sent,
                "claim_type": claim_type.value,
                "qualifiers": qualifiers,
                "source_period": source_period,
                "target_period": target_period,
                "turn_index": turn["turn_index"],
                "question_turn_index": turn.get("question_turn_index"),
                "page": turn.get("page"),
            })

    return claims


# ---------------------------------------------------------------------------
# Earnings call transcript result
# ---------------------------------------------------------------------------

@dataclass
class EarningsCallTranscriptResult:
    """Typed result returned by EarningsCallTranscriptProcessor.process().

    Fields:
        company:               Registry-resolved company slug.
        fiscal_year:           Company fiscal year label (e.g. "fy26").
        context_quarter:       Quarter number (1–4) when explicitly evidenced,
                               or None for full-year-only calls.  Never fabricated.
        call_date:             ISO date of the call when detectable from content.
        source_file:           Absolute path to the source document.
        storage_path:          Canonical: companies/<co>/<fy>/earnings_calls/<hash>/
        status:                "SUCCESS" | "PARTIAL_*" | "ERROR"
        document_hash:         SHA-256 content hash from the manifest.
        source_type:           SourceType value from manifest.
        source_channel:        SourceChannel value from manifest.
        warnings:              Non-fatal notes from the processing run.
        speaker_count:         Distinct speaker labels found.
        turn_count:            Total speaker turns segmented.
        management_turn_count: Turns attributed to MANAGEMENT speakers.
        analyst_question_count:Turns attributed to ANALYST with is_question=True.
        evidence_count:        Management claim candidates extracted.
        chunks_path:           Path to written chunks JSON.
        manifest_path:         Path to written manifest JSON.
        turns_path:            Path to written transcript turns JSON.
        claims_path:           Path to written management claims JSON.
        result_path:           Path to written processing result JSON.
    """
    company: str
    fiscal_year: str
    context_quarter: Optional[int]
    call_date: Optional[str]
    source_file: str
    storage_path: str
    status: str = "SUCCESS"
    document_hash: str = ""
    source_type: str = ""
    source_channel: str = ""
    warnings: List[str] = field(default_factory=list)
    speaker_count: int = 0
    turn_count: int = 0
    management_turn_count: int = 0
    analyst_question_count: int = 0
    evidence_count: int = 0
    chunks_path: str = ""
    manifest_path: str = ""
    turns_path: str = ""
    claims_path: str = ""
    common_evidence_path: str = ""
    result_path: str = ""

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "fiscal_year": self.fiscal_year,
            "context_quarter": self.context_quarter,
            "call_date": self.call_date,
            "source_file": self.source_file,
            "storage_path": self.storage_path,
            "status": self.status,
            "document_hash": self.document_hash,
            "source_type": self.source_type,
            "source_channel": self.source_channel,
            "warnings": list(self.warnings),
            "speaker_count": self.speaker_count,
            "turn_count": self.turn_count,
            "management_turn_count": self.management_turn_count,
            "analyst_question_count": self.analyst_question_count,
            "evidence_count": self.evidence_count,
            "chunks_path": self.chunks_path,
            "manifest_path": self.manifest_path,
            "turns_path": self.turns_path,
            "claims_path": self.claims_path,
            "common_evidence_path": self.common_evidence_path,
            "result_path": self.result_path,
        }


# ---------------------------------------------------------------------------
# Earnings release result
# ---------------------------------------------------------------------------

@dataclass
class EarningsReleaseResult:
    """Typed result returned by EarningsReleaseProcessor.process()."""

    company: str
    fiscal_year: str
    context_quarter: Optional[int]
    release_date: Optional[str]
    source_file: str
    storage_path: str
    status: str = "SUCCESS"
    document_hash: str = ""
    source_type: str = ""
    source_channel: str = ""
    warnings: List[str] = field(default_factory=list)
    financial_fact_count: int = 0
    management_claim_count: int = 0
    operational_evidence_count: int = 0
    common_evidence_count: int = 0
    chunks_path: str = ""
    manifest_path: str = ""
    financial_facts_path: str = ""
    management_claims_path: str = ""
    operational_evidence_path: str = ""
    common_evidence_path: str = ""
    result_path: str = ""

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "fiscal_year": self.fiscal_year,
            "context_quarter": self.context_quarter,
            "release_date": self.release_date,
            "source_file": self.source_file,
            "storage_path": self.storage_path,
            "status": self.status,
            "document_hash": self.document_hash,
            "source_type": self.source_type,
            "source_channel": self.source_channel,
            "warnings": list(self.warnings),
            "financial_fact_count": self.financial_fact_count,
            "management_claim_count": self.management_claim_count,
            "operational_evidence_count": self.operational_evidence_count,
            "common_evidence_count": self.common_evidence_count,
            "chunks_path": self.chunks_path,
            "manifest_path": self.manifest_path,
            "financial_facts_path": self.financial_facts_path,
            "management_claims_path": self.management_claims_path,
            "operational_evidence_path": self.operational_evidence_path,
            "common_evidence_path": self.common_evidence_path,
            "result_path": self.result_path,
        }


class EarningsReleaseProcessor(ProcessorInterface):
    """Canonical processor for company-issued EARNINGS_RELEASE documents.

    Earnings releases contain company-reported result highlights plus
    management commentary. They are not transcripts, not slide decks, and not
    formal audited financial truth. This processor emits document-scoped common
    evidence with source authority preserved; it does not run downstream
    intelligence stages.
    """

    def can_process(self, manifest: DocumentIntakeManifest) -> bool:
        return (
            manifest.classification.status == ClassificationStatus.IDENTIFIED
            and manifest.document_identity.source_type == SourceType.EARNINGS_RELEASE
        )

    def process(
        self,
        manifest: DocumentIntakeManifest,
        source_path: Path,
    ) -> EarningsReleaseResult:
        import json

        if manifest.classification.status != ClassificationStatus.IDENTIFIED:
            raise ProcessorUnavailableError(
                "EarningsReleaseProcessor requires status=IDENTIFIED. "
                f"Got: {manifest.classification.status.value}."
            )
        if manifest.document_identity.source_type != SourceType.EARNINGS_RELEASE:
            raise ProcessorUnavailableError(
                "EarningsReleaseProcessor can only process EARNINGS_RELEASE. "
                f"Got: {manifest.document_identity.source_type.value}."
            )

        company = manifest.company_identity.resolved_company_key
        reporting = manifest.reporting_period
        fiscal_year = reporting.fiscal_year if reporting else None
        fiscal_quarter = reporting.fiscal_quarter if reporting else None
        if not company or not fiscal_year or not fiscal_quarter:
            raise ProcessorUnavailableError(
                "EarningsReleaseProcessor requires resolved company, fiscal_year, "
                f"and fiscal_quarter. company={company!r} fiscal_year={fiscal_year!r} "
                f"fiscal_quarter={fiscal_quarter!r}."
            )

        context_quarter = int(fiscal_quarter.value[1])
        source_period = f"{fiscal_quarter.value} {fiscal_year.upper()}"
        doc_hash_short = manifest.file.content_hash.replace("sha256:", "")[:16]
        storage_root = (
            Path("companies") / company / fiscal_year / "earnings_releases" / doc_hash_short
        )
        warnings: List[str] = []

        try:
            storage_root.mkdir(parents=True, exist_ok=True)
            full_text, page_ranges = EarningsCallTranscriptProcessor._extract_full_text_with_pages(
                source_path, warnings
            )
            page_texts = self._page_texts_from_ranges(full_text, page_ranges)
            release_date = self._detect_release_date(full_text) or manifest.document_dates.publication_date

            financial_facts = self._extract_financial_facts(
                page_texts=page_texts,
                company=company,
                fiscal_year=fiscal_year,
                source_period=source_period,
                context_quarter=context_quarter,
                document_hash=manifest.file.content_hash,
            )
            management_claims = self._extract_management_quote_claims(
                page_texts=page_texts,
                company=company,
                fiscal_year=fiscal_year,
                source_period=source_period,
                document_hash=manifest.file.content_hash,
            )
            operational_evidence = self._extract_operational_evidence(
                page_texts=page_texts,
                company=company,
                fiscal_year=fiscal_year,
                source_period=source_period,
                document_hash=manifest.file.content_hash,
            )
            common_evidence = self._build_common_evidence(
                company=company,
                fiscal_year=fiscal_year,
                source_period=source_period,
                document_hash=manifest.file.content_hash,
                financial_facts=financial_facts,
                management_claims=management_claims,
                operational_evidence=operational_evidence,
            )

            chunks_path = storage_root / "release_chunks.json"
            chunks_path.write_text(
                json.dumps(
                    {"chunks": [{"page": page, "text": text} for page, text in page_texts]},
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )

            financial_facts_path = storage_root / "reported_financial_facts.json"
            financial_facts_path.write_text(
                json.dumps({"source_period": source_period, "facts": financial_facts}, indent=2, default=str),
                encoding="utf-8",
            )
            management_claims_path = storage_root / "management_claims.json"
            management_claims_path.write_text(
                json.dumps({"source_period": source_period, "claims": management_claims}, indent=2, default=str),
                encoding="utf-8",
            )
            operational_evidence_path = storage_root / "operational_evidence.json"
            operational_evidence_path.write_text(
                json.dumps({"source_period": source_period, "items": operational_evidence}, indent=2, default=str),
                encoding="utf-8",
            )
            common_evidence_path = storage_root / "common_evidence.json"
            common_evidence_path.write_text(
                json.dumps(common_evidence, indent=2, default=str),
                encoding="utf-8",
            )

            manifest_path = storage_root / "release_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "manifest": manifest.to_dict(),
                        "source_period": source_period,
                        "release_date": release_date,
                        "storage_root": str(storage_root),
                    },
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )

            result = EarningsReleaseResult(
                company=company,
                fiscal_year=fiscal_year,
                context_quarter=context_quarter,
                release_date=release_date,
                source_file=str(source_path.resolve()),
                storage_path=str(storage_root),
                document_hash=manifest.file.content_hash,
                source_type=manifest.document_identity.source_type.value,
                source_channel=manifest.document_identity.source_channel.value,
                warnings=warnings,
                financial_fact_count=len(financial_facts),
                management_claim_count=len(management_claims),
                operational_evidence_count=len(operational_evidence),
                common_evidence_count=len(common_evidence["records"]),
                chunks_path=str(chunks_path),
                manifest_path=str(manifest_path),
                financial_facts_path=str(financial_facts_path),
                management_claims_path=str(management_claims_path),
                operational_evidence_path=str(operational_evidence_path),
                common_evidence_path=str(common_evidence_path),
            )
            result_path = storage_root / "release_processing_result.json"
            result.result_path = str(result_path)
            result_path.write_text(
                json.dumps(result.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
            return result

        except (ProcessorUnavailableError, ProcessorExecutionError):
            raise
        except Exception as exc:
            raise ProcessorExecutionError(f"EarningsReleaseProcessor failed: {exc}") from exc

    @staticmethod
    def _page_texts_from_ranges(
        full_text: str,
        page_ranges: List[tuple[int, int, int]],
    ) -> List[tuple[int, str]]:
        return [(page, full_text[start:end].strip()) for page, start, end in page_ranges if full_text[start:end].strip()]

    @staticmethod
    def _detect_release_date(text: str) -> Optional[str]:
        m = _re.search(
            r"\b(?:Mumbai|Bengaluru|New Delhi|Hyderabad|Pune|Chennai),?\s+"
            r"((?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+\d{1,2},?\s+\d{4})\b",
            text[:5000],
            _re.IGNORECASE,
        )
        if m:
            return _re.sub(r"\s+", " ", m.group(1)).strip()
        m = _re.search(
            r"\b((?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+\d{1,2},?\s+\d{4})\b",
            text[:5000],
        )
        return _re.sub(r"\s+", " ", m.group(1)).strip() if m else None

    @staticmethod
    def _metric_from_line(line: str) -> Optional[str]:
        lower = line.lower()
        if "revenue" in lower and "usd" not in lower:
            return "revenue"
        if "usd revenue" in lower:
            return "usd_revenue"
        if "ebit margin" in lower or "ebit margins" in lower:
            if "bps" in lower and not _re.search(r"\bmargin(?:s)?\s+(?:at|to)\b", lower):
                return "ebit_margin_change"
            return "ebit_margin"
        if "net income" in lower or "net profit" in lower or "pat" in lower:
            return "net_profit"
        if "ebit" in lower:
            return "ebit"
        return None

    @staticmethod
    def _extract_release_value(line: str, metric: str) -> Optional[tuple[str, str, str]]:
        """Extract the metric value without mistaking Q1/FY tokens for values."""
        currency_re = _re.compile(
            r"(?P<unit>₹|INR|USD|\$)\s*(?P<value>\(?-?\d[\d,]*(?:\.\d+)?\)?)(?:\s*(?P<scale>crore|million|mn))?",
            _re.IGNORECASE,
        )
        percent_re = _re.compile(r"(?P<value>\(?-?\d[\d,]*(?:\.\d+)?\)?)\s*(?P<scale>%|bps)\b", _re.IGNORECASE)
        if metric in {"revenue", "usd_revenue", "net_profit"}:
            m = currency_re.search(line)
            if m:
                return m.group("value"), m.group("unit") or "", m.group("scale") or ""
            return None
        if metric in {"ebit_margin"}:
            m = _re.search(
                r"\b(?:ebit\s+)?margin(?:s)?(?:\s+improved)?\s+(?:at|to)\s+(?P<value>\(?-?\d[\d,]*(?:\.\d+)?\)?)\s*(?P<scale>%)",
                line,
                _re.IGNORECASE,
            ) or percent_re.search(line)
            if m:
                return m.group("value"), "", m.group("scale") or ""
            return None
        if metric in {"ebit_margin_change"}:
            m = _re.search(r"(?P<value>\(?-?\d[\d,]*(?:\.\d+)?\)?)\s*(?P<scale>bps)\b", line, _re.IGNORECASE)
            if m:
                return m.group("value"), "", m.group("scale") or ""
            return None
        m = currency_re.search(line) or percent_re.search(line)
        if not m:
            return None
        return m.group("value"), m.groupdict().get("unit") or "", m.groupdict().get("scale") or ""

    @staticmethod
    def _extract_financial_facts(
        *,
        page_texts: List[tuple[int, str]],
        company: str,
        fiscal_year: str,
        source_period: str,
        context_quarter: int,
        document_hash: str,
    ) -> List[dict]:
        from knowledge.financials.period_roles import FinancialPeriodRole, interpret_period_role

        facts: List[dict] = []
        context_fy = int(_re.search(r"\d{2,4}", fiscal_year).group(0)) % 100
        for page, text in page_texts:
            for raw_line in text.splitlines():
                line = _re.sub(r"\s+", " ", raw_line).strip(" •\t")
                if len(line) < 8:
                    continue
                metric = EarningsReleaseProcessor._metric_from_line(line)
                if not metric:
                    continue
                extracted_value = EarningsReleaseProcessor._extract_release_value(line, metric)
                if not extracted_value:
                    continue
                value_raw, raw_unit, raw_scale = extracted_value
                period_role = FinancialPeriodRole.CURRENT_QUARTER
                explicit_role = interpret_period_role(
                    line,
                    context_fy=context_fy,
                    context_quarter=context_quarter,
                )
                if explicit_role != FinancialPeriodRole.UNKNOWN:
                    period_role = explicit_role
                fact_id = f"earnings_release:{document_hash.replace('sha256:', '')[:16]}:financial:{len(facts):04d}"
                facts.append({
                    "fact_id": fact_id,
                    "company": company,
                    "fiscal_year": fiscal_year,
                    "source_type": "EARNINGS_RELEASE",
                    "authority": "COMPANY_REPORTED_RELEASE",
                    "evidence_kind": "REPORTED_RESULT",
                    "metric": metric,
                    "value_raw": value_raw,
                    "raw_unit": raw_unit,
                    "raw_scale": raw_scale,
                    "raw_label": line,
                    "basis": "unknown",
                    "source_period": source_period,
                    "period_role": period_role.value,
                    "page": page,
                    "document_hash": document_hash,
                    "reported_vs_derived": "reported",
                })
        return facts

    @staticmethod
    def _extract_management_quote_claims(
        *,
        page_texts: List[tuple[int, str]],
        company: str,
        fiscal_year: str,
        source_period: str,
        document_hash: str,
    ) -> List[dict]:
        claims: List[dict] = []
        quote_re = _re.compile(r"[“\"](.{60,3200}?)[”\"]\s*said\s+([^.\n]{3,180})", _re.IGNORECASE | _re.DOTALL)
        for page, text in page_texts:
            for m in quote_re.finditer(text):
                quote = _re.sub(r"\s+", " ", m.group(1)).strip()
                speaker_block = _re.sub(r"\s+", " ", m.group(2)).strip()
                speaker = speaker_block.split(",")[0].strip()
                for sent in _re.split(r"(?<=[.!?])\s+", quote):
                    sent = sent.strip()
                    if len(sent) < 25:
                        continue
                    target_period = None
                    tp_match = _re.search(
                        r"\b(?:by|in|during|for|before)\s+(q[1-4]\s*fy\d{2,4}|fy\d{2,4}|next\s+quarter|next\s+year)\b",
                        sent,
                        _re.IGNORECASE,
                    )
                    if tp_match:
                        target_period = tp_match.group(1).strip()
                    elif _re.search(r"\bnext\s+five\s+years\b", sent, _re.IGNORECASE):
                        target_period = "next five years"
                    claim_id = f"earnings_release:{document_hash.replace('sha256:', '')[:16]}:claim:{len(claims):04d}"
                    claims.append({
                        "claim_id": claim_id,
                        "company": company,
                        "fiscal_year": fiscal_year,
                        "source_type": "EARNINGS_RELEASE",
                        "authority": "MANAGEMENT_CLAIM",
                        "evidence_kind": "MANAGEMENT_CLAIM",
                        "speaker": speaker,
                        "speaker_title": speaker_block,
                        "claim_type": _classify_claim_type(sent).value,
                        "qualifiers": _extract_qualifiers(sent),
                        "raw_text": sent,
                        "source_period": source_period,
                        "target_period": target_period,
                        "page": page,
                        "document_hash": document_hash,
                    })
        return claims

    @staticmethod
    def _extract_operational_evidence(
        *,
        page_texts: List[tuple[int, str]],
        company: str,
        fiscal_year: str,
        source_period: str,
        document_hash: str,
    ) -> List[dict]:
        patterns = _re.compile(
            r"\b(deal|win|selected|partnered|launched|recognized|patents?|employees?|"
            r"customer|segment|growth|initiative|portfolio|technology|ai)\b",
            _re.IGNORECASE,
        )
        items: List[dict] = []
        for page, text in page_texts:
            for raw_line in text.splitlines():
                line = _re.sub(r"\s+", " ", raw_line).strip(" •\t")
                lower = line.lower()
                if (
                    page == 1
                    or
                    len(line) < 30
                    or not patterns.search(line)
                    or "copyright" in lower
                    or lower.startswith("for ")
                    or "registered office" in lower
                    or "www." in lower
                    or "@" in line
                    or EarningsReleaseProcessor._metric_from_line(line)
                ):
                    continue
                item_id = f"earnings_release:{document_hash.replace('sha256:', '')[:16]}:operational:{len(items):04d}"
                items.append({
                    "evidence_id": item_id,
                    "company": company,
                    "fiscal_year": fiscal_year,
                    "source_type": "EARNINGS_RELEASE",
                    "authority": "COMPANY_REPORTED_RELEASE",
                    "evidence_kind": "OPERATIONAL_HIGHLIGHT",
                    "raw_text": line,
                    "source_period": source_period,
                    "target_period": None,
                    "page": page,
                    "document_hash": document_hash,
                })
                if len(items) >= 80:
                    return items
        return items

    @staticmethod
    def _build_common_evidence(
        *,
        company: str,
        fiscal_year: str,
        source_period: str,
        document_hash: str,
        financial_facts: List[dict],
        management_claims: List[dict],
        operational_evidence: List[dict],
    ) -> dict:
        records = []
        for fact in financial_facts:
            records.append({**fact, "evidence_id": fact["fact_id"]})
        for claim in management_claims:
            records.append({**claim, "evidence_id": claim["claim_id"]})
        records.extend(operational_evidence)
        return {
            "company": company,
            "fiscal_year": fiscal_year,
            "source_period": source_period,
            "source_type": "EARNINGS_RELEASE",
            "authority": "COMPANY_REPORTED_RELEASE",
            "document_hash": document_hash,
            "records": records,
        }


# ---------------------------------------------------------------------------
# Earnings call transcript processor
#
# Registered after direct production proof on a real earnings-call transcript
# (Phase 6.1, 2026-09-02).  See SESSION_LOG.md.
# ---------------------------------------------------------------------------

class EarningsCallTranscriptProcessor(ProcessorInterface):
    """Canonical processor for EARNINGS_CALL_TRANSCRIPT source type.

    An earnings call transcript is a structured record of a conference call
    with distinct speaker turns, participant roles, prepared remarks, and a
    Q&A session.  It differs from all other source types in that evidence
    authority depends on WHO said WHAT and WHERE:

    - MANAGEMENT turns in PREPARED_REMARKS: polished, scripted evidence
    - MANAGEMENT turns in Q_AND_A: reactive, often more revealing
    - ANALYST turns: questions and assertions — never promoted to company facts
    - OPERATOR turns: structural scaffolding — never substantive evidence

    Key design principles:
    - Speaker attribution fails conservatively: UNKNOWN when ambiguous.
    - Analyst questions are never management claims.
    - Qualifiers and uncertainty are preserved, never stripped.
    - 'Said' ≠ 'did' ≠ 'outcome': management speech is always CLAIM semantics.
    - Source period and target period are kept distinct.
    - Financial references carry TRANSCRIPT source authority — they do not
      overwrite formal financial statement truth.
    - Storage is document-scoped (earnings_calls/<hash>/) to allow multiple
      calls per quarter to coexist without collision.
    """

    def can_process(self, manifest: DocumentIntakeManifest) -> bool:
        from knowledge.document_intake import SourceType
        return (
            manifest.classification.status == ClassificationStatus.IDENTIFIED
            and manifest.document_identity.source_type == SourceType.EARNINGS_CALL_TRANSCRIPT
        )

    def process(
        self,
        manifest: DocumentIntakeManifest,
        source_path: Path,
    ) -> EarningsCallTranscriptResult:
        """Execute the transcript processing pipeline.

        Raises:
            ProcessorUnavailableError: if manifest is not IDENTIFIED EARNINGS_CALL_TRANSCRIPT.
            ProcessorExecutionError:   on unexpected failures.
        """
        import json
        import time as _time
        from knowledge.document_intake import SourceType

        # ── Validate preconditions ────────────────────────────────────────────
        if manifest.classification.status != ClassificationStatus.IDENTIFIED:
            raise ProcessorUnavailableError(
                "EarningsCallTranscriptProcessor requires status=IDENTIFIED. "
                f"Got: {manifest.classification.status.value}."
            )
        if manifest.document_identity.source_type != SourceType.EARNINGS_CALL_TRANSCRIPT:
            raise ProcessorUnavailableError(
                "EarningsCallTranscriptProcessor can only process EARNINGS_CALL_TRANSCRIPT. "
                f"Got: {manifest.document_identity.source_type.value}."
            )

        company = manifest.company_identity.resolved_company_key
        reporting = manifest.reporting_period
        fiscal_year = reporting.fiscal_year if reporting else None

        if not company or not fiscal_year:
            raise ProcessorUnavailableError(
                "EarningsCallTranscriptProcessor requires resolved company and fiscal_year. "
                f"company={company!r} fiscal_year={fiscal_year!r}."
            )

        # Preserve explicit quarter evidence; never fabricate.
        fiscal_quarter = reporting.fiscal_quarter if reporting else None
        context_quarter: Optional[int] = (
            int(fiscal_quarter.value[1]) if fiscal_quarter else None
        )

        # Build source period label for claim provenance.
        source_period = fiscal_year.upper()
        if fiscal_quarter:
            source_period = f"{fiscal_quarter.value} {fiscal_year.upper()}"

        # Document-scoped storage — multiple calls per quarter coexist safely.
        doc_hash_short = manifest.file.content_hash.replace("sha256:", "")[:16]
        storage_root = (
            Path("companies") / company / fiscal_year / "earnings_calls" / doc_hash_short
        )
        warnings: List[str] = []

        try:
            storage_root.mkdir(parents=True, exist_ok=True)

            # ── Step 1: Extract full text ──────────────────────────────────────
            full_text, page_ranges = self._extract_full_text_with_pages(source_path, warnings)

            # ── Step 2: Detect call date from content ──────────────────────────
            call_date = self._detect_call_date(full_text)

            # ── Step 3: Build participant registry ─────────────────────────────
            participant_registry = _parse_participant_list(full_text)

            # ── Step 4: Segment into speaker turns ────────────────────────────
            turns = _segment_turns(full_text, participant_registry, company, page_ranges)

            # ── Step 5: Extract management claim candidates ────────────────────
            claims = _extract_management_claims(turns, source_period)

            # ── Step 6: Compute statistics ────────────────────────────────────
            speaker_count = len({t["raw_speaker"] for t in turns})
            turn_count = len(turns)
            management_turn_count = sum(
                1 for t in turns if t["speaker_role"] == SpeakerRole.MANAGEMENT.value
            )
            analyst_question_count = sum(1 for t in turns if t["is_question"])
            evidence_count = len(claims)

            # ── Step 7: Write document-scoped artifacts ────────────────────────
            chunks_path = storage_root / "transcript_chunks.json"
            self._write_chunks(source_path, chunks_path, warnings)

            turns_path = storage_root / "transcript_turns.json"
            turns_path.write_text(
                json.dumps(
                    {"source_period": source_period, "turns": turns},
                    indent=2, default=str,
                ),
                encoding="utf-8",
            )

            common_evidence_path = storage_root / "common_evidence.json"
            common_evidence = self._build_common_evidence(
                company=company,
                fiscal_year=fiscal_year,
                source_period=source_period,
                document_hash=manifest.file.content_hash,
                claims=claims,
            )

            claims_path = storage_root / "management_claims.json"
            claims_path.write_text(
                json.dumps(
                    {
                        "source_period": source_period,
                        "company": company,
                        "fiscal_year": fiscal_year,
                        "authority": "TRANSCRIPT",
                        "claims": claims,
                    },
                    indent=2, default=str,
                ),
                encoding="utf-8",
            )

            common_evidence_path.write_text(
                json.dumps(common_evidence, indent=2, default=str),
                encoding="utf-8",
            )

            manifest_data = {
                "company": company,
                "fiscal_year": fiscal_year,
                "context_quarter": context_quarter,
                "source_period": source_period,
                "call_date": call_date,
                "document_hash": manifest.file.content_hash,
                "source_type": manifest.document_identity.source_type.value,
                "source_channel": manifest.document_identity.source_channel.value,
                "storage_root": str(storage_root),
                "speaker_count": speaker_count,
                "turn_count": turn_count,
                "management_turn_count": management_turn_count,
                "analyst_question_count": analyst_question_count,
                "evidence_count": evidence_count,
                "warnings": warnings,
            }
            manifest_path = storage_root / "transcript_manifest.json"
            manifest_path.write_text(
                json.dumps(manifest_data, indent=2, default=str),
                encoding="utf-8",
            )

            result_obj = EarningsCallTranscriptResult(
                company=company,
                fiscal_year=fiscal_year,
                context_quarter=context_quarter,
                call_date=call_date,
                source_file=str(source_path.resolve()),
                storage_path=str(storage_root),
                status="SUCCESS",
                document_hash=manifest.file.content_hash,
                source_type=manifest.document_identity.source_type.value,
                source_channel=manifest.document_identity.source_channel.value,
                warnings=warnings,
                speaker_count=speaker_count,
                turn_count=turn_count,
                management_turn_count=management_turn_count,
                analyst_question_count=analyst_question_count,
                evidence_count=evidence_count,
                chunks_path=str(chunks_path),
                manifest_path=str(manifest_path),
                turns_path=str(turns_path),
                claims_path=str(claims_path),
                common_evidence_path=str(common_evidence_path),
            )
            result_path = storage_root / "processing_result.json"
            result_path.write_text(
                json.dumps(result_obj.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
            result_obj.result_path = str(result_path)
            return result_obj

        except (ProcessorUnavailableError, ProcessorExecutionError):
            raise
        except Exception as exc:
            raise ProcessorExecutionError(
                f"EarningsCallTranscriptProcessor failed: {exc}"
            ) from exc

    @staticmethod
    def _extract_full_text(source_path: Path, warnings: List[str]) -> str:
        """Extract full text from a PDF or text file."""
        text, _ranges = EarningsCallTranscriptProcessor._extract_full_text_with_pages(
            source_path, warnings
        )
        return text

    @staticmethod
    def _extract_full_text_with_pages(
        source_path: Path,
        warnings: List[str],
    ) -> tuple[str, List[tuple[int, int, int]]]:
        """Extract full text plus page-offset ranges for provenance."""
        suffix = source_path.suffix.lower()
        if suffix in (".txt", ".md"):
            text = source_path.read_text(encoding="utf-8", errors="replace")
            return text, [(1, 0, len(text))]
        try:
            import fitz
            doc = fitz.open(str(source_path))
            pages: List[str] = []
            ranges: List[tuple[int, int, int]] = []
            offset = 0
            for page_index, page in enumerate(doc, start=1):
                page_text = page.get_text()
                start = offset
                pages.append(page_text)
                offset += len(page_text) + 1
                ranges.append((page_index, start, offset))
            doc.close()
            return "\n".join(pages), ranges
        except Exception as exc:
            warnings.append(f"Full text extraction failed: {exc}")
            return "", []

    @staticmethod
    def _build_common_evidence(
        *,
        company: str,
        fiscal_year: str,
        source_period: str,
        document_hash: str,
        claims: List[dict],
    ) -> dict:
        """Build source-scoped common-evidence records from management claims.

        Transcript evidence is intentionally lower-authority claim evidence. It
        can feed later common intelligence, but it does not become audited
        financial truth or completed operational outcome by being parsed here.
        """
        records = []
        for idx, claim in enumerate(claims):
            evidence_id = f"earnings_call:{document_hash.replace('sha256:', '')[:16]}:claim:{idx:04d}"
            claim["claim_id"] = evidence_id
            records.append({
                "evidence_id": evidence_id,
                "company": company,
                "fiscal_year": fiscal_year,
                "source_type": "EARNINGS_CALL_TRANSCRIPT",
                "authority": "TRANSCRIPT",
                "source_period": source_period,
                "target_period": claim.get("target_period"),
                "speaker": claim.get("speaker"),
                "normalized_speaker": claim.get("normalized_speaker"),
                "speaker_role": claim.get("speaker_role"),
                "section": claim.get("section"),
                "turn_index": claim.get("turn_index"),
                "question_turn_index": claim.get("question_turn_index"),
                "page": claim.get("page"),
                "claim_type": claim.get("claim_type"),
                "qualifiers": list(claim.get("qualifiers") or []),
                "text": claim.get("raw_text"),
                "provenance": {
                    "document_hash": document_hash,
                    "source": "earnings_call_transcript_processor",
                },
            })
        return {
            "company": company,
            "fiscal_year": fiscal_year,
            "source_period": source_period,
            "source_type": "EARNINGS_CALL_TRANSCRIPT",
            "authority": "TRANSCRIPT",
            "records": records,
        }

    @staticmethod
    def _detect_call_date(text: str) -> Optional[str]:
        """Detect the earnings-call date, not the exchange filing date."""
        header = text[:5000]
        held_match = _re.search(
            r"\bheld\s+on\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?"
            r",?\s*((?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+\d{1,2},?\s+\d{4})\b",
            header,
            _re.IGNORECASE,
        )
        if held_match:
            return _re.sub(r"\s+", " ", held_match.group(1)).strip()

        title_match = _re.search(
            r"(?:earnings|conference)\s+call\s+transcript\s+"
            r"((?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+\d{1,2},?\s+\d{4})\b",
            header,
            _re.IGNORECASE,
        )
        if title_match:
            return _re.sub(r"\s+", " ", title_match.group(1)).strip()

        m = _re.search(
            r"\b(?:(?:January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})\b",
            header,
        )
        return _re.sub(r"\s+", " ", m.group(0)).strip() if m else None

    @staticmethod
    def _write_chunks(source_path: Path, chunks_path: Path, warnings: List[str]) -> None:
        """Write page-scoped transcript chunks to storage (best-effort)."""
        import json as _json
        try:
            text, page_ranges = EarningsCallTranscriptProcessor._extract_full_text_with_pages(
                source_path, warnings
            )
            chunks = []
            for page, start, end in page_ranges:
                page_text = text[start:end].strip()
                if page_text:
                    chunks.append({"page": page, "text": page_text})
            chunks_path.write_text(
                _json.dumps({"chunks": chunks}, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            warnings.append(f"Chunking skipped: {exc}")
            chunks_path.write_text('{"chunks": []}', encoding="utf-8")


# ---------------------------------------------------------------------------
# Exchange Disclosure enums and processor
# ---------------------------------------------------------------------------

class DisclosureEventType(str, Enum):
    """Conservative taxonomy of material corporate events."""
    ORDER_AWARD = "ORDER_AWARD"
    CONTRACT = "CONTRACT"
    ACQUISITION = "ACQUISITION"
    DIVESTMENT = "DIVESTMENT"
    PROJECT = "PROJECT"
    CAPACITY = "CAPACITY"
    REGULATORY_APPROVAL = "REGULATORY_APPROVAL"
    MANAGEMENT_CHANGE = "MANAGEMENT_CHANGE"
    CAPITAL_RAISE = "CAPITAL_RAISE"
    DEBT = "DEBT"
    CREDIT_RATING = "CREDIT_RATING"
    LITIGATION = "LITIGATION"
    BOARD_DECISION = "BOARD_DECISION"
    CUSTOMER_PARTNERSHIP = "CUSTOMER_PARTNERSHIP"
    OTHER_MATERIAL_EVENT = "OTHER_MATERIAL_EVENT"
    UNKNOWN = "UNKNOWN"


class DisclosureEventStatus(str, Enum):
    """Conservative lifecycle state vocabulary.

    Missing > guessed: if state is not explicit, use UNKNOWN.
    Do not promote PROPOSED to APPROVED merely because a board meeting is mentioned.
    Do not promote COMMISSIONED to OPERATIONAL unless the disclosure says so.
    """
    PROPOSED = "PROPOSED"
    PLANNED = "PLANNED"
    UNDER_CONSIDERATION = "UNDER_CONSIDERATION"
    APPROVED = "APPROVED"
    SIGNED = "SIGNED"
    AWARDED = "AWARDED"
    FUNDED = "FUNDED"
    UNDER_CONSTRUCTION = "UNDER_CONSTRUCTION"
    INSTALLED = "INSTALLED"
    COMMISSIONED = "COMMISSIONED"
    OPERATIONAL = "OPERATIONAL"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    DELAYED = "DELAYED"
    UNKNOWN = "UNKNOWN"


# Regex helpers for event classification.
_RE_DISC_ORDER = _re.compile(
    r"\border\s+(award|win|won|receiv|obtain|secur|bag|bagg)\w*\b"
    r"|\b(receiv|secur|obtain|award|win|won|bag|bagg)\w*\s+(?:\w+\s+){0,4}order\b"
    r"|\border\s+book\b|\bcontract\s+award\b",
    _re.IGNORECASE,
)
_RE_DISC_ACQUISITION = _re.compile(
    r"\bacquisition\b|\bacquir\b|\bmerger\b|\bamalgamation\b|\btakeover\b",
    _re.IGNORECASE,
)
_RE_DISC_DIVESTMENT = _re.compile(
    r"\bdivestment\b|\bdivestiture\b|\bsale\s+of\s+(business|subsidiary|stake)\b",
    _re.IGNORECASE,
)
_RE_DISC_CAPACITY = _re.compile(
    r"\bcommissioned?\b|\bcapacity\s+(addition|expansion|installation)\b|\bplant\s+(expansion|set\s+up)\b",
    _re.IGNORECASE,
)
_RE_DISC_REGULATORY = _re.compile(
    r"\bregulatory\s+approv\w*\b|\bcertification\b|\bfda\s+approv\w*\b"
    r"|\bsebi\s+approv\w*\b|\bnmpa\b|\bpatent\s+grant\b|\bdrdo\s+approv\w*\b",
    _re.IGNORECASE,
)
_RE_DISC_MGMT_CHANGE = _re.compile(
    r"\bappoint(?:ed|ment)?\b|\bresign(?:ed|ation)?\b|\bcessation\b|\bmanaging\s+director\b"
    r"|\b(?:ceo|cfo|coo|cto)\s+(?:appoint|resign)",
    _re.IGNORECASE,
)
_RE_DISC_CAPITAL = _re.compile(
    r"\bfundraising\b|\bright\s+issue\b|\bpreferential\s+allotment\b|\bqip\b|\bncds?\b|\bdebentures?\b",
    _re.IGNORECASE,
)
_RE_DISC_CREDIT = _re.compile(
    r"\bcredit\s+rating\b|\brating\s+(action|change|upgrade|downgrade)\b",
    _re.IGNORECASE,
)
_RE_DISC_LITIGATION = _re.compile(
    r"\blitigation\b|\barbitration\b|\bcourt\s+order\b|\badjudication\b|\bpenalty\b",
    _re.IGNORECASE,
)
_RE_DISC_BOARD = _re.compile(
    r"\boutcome\s+of\s+(the\s+)?board\b|\bboard\s+(meeting|resolution|decision|approved)\b",
    _re.IGNORECASE,
)

# Event status detection patterns — ordered most-specific first.
_DISC_STATUS_PATTERNS: List[Tuple[_re.Pattern, DisclosureEventStatus]] = [
    (_re.compile(r"\bcommissioned\b", _re.IGNORECASE), DisclosureEventStatus.COMMISSIONED),
    (_re.compile(r"\boperational\b|\bcommercially\s+launched\b", _re.IGNORECASE), DisclosureEventStatus.OPERATIONAL),
    (_re.compile(r"\bcompleted\b|\bclosure\b|\bclosed\b", _re.IGNORECASE), DisclosureEventStatus.COMPLETED),
    (_re.compile(r"\bawarded\b|\bconferred\b|\breceived\b.*\border\b", _re.IGNORECASE), DisclosureEventStatus.AWARDED),
    (_re.compile(r"\bagreement\s+(?:executed|signed)\b|\bspa\s+signed\b|\bcontract\s+signed\b|\bsigned\s+between\b|\bsigned\s+and\s+effective\b|\bexecuted\s+(?:and\s+)?signed\b|\bsign(?:ed|ing)\s+(?:of\s+)?(?:the\s+)?(?:agreement|contract|mou|nda|loi|spa)\b", _re.IGNORECASE), DisclosureEventStatus.SIGNED),
    (_re.compile(r"\bapproved?\b|\bapproval\s+received\b|\bregulatory\s+approv\w*\b|\bsanctioned\b|\baccorded\b|\bclearance\s+received\b|\bgranted\b|\bcertified\b|\blicensed\b", _re.IGNORECASE), DisclosureEventStatus.APPROVED),
    (_re.compile(r"\bunder\s+construction\b|\bin\s+progress\b|\bimplementation\b|\bconstruction\s+is\s+\w+\b|\bis\s+underway\b|\bunderway\b", _re.IGNORECASE), DisclosureEventStatus.UNDER_CONSTRUCTION),
    (_re.compile(r"\binstalled\b", _re.IGNORECASE), DisclosureEventStatus.INSTALLED),
    (_re.compile(r"\bfunded\b|\bfinanced\b", _re.IGNORECASE), DisclosureEventStatus.FUNDED),
    (_re.compile(r"\bplanned?\b|\bproposed?\b.*\bboard\b", _re.IGNORECASE), DisclosureEventStatus.PLANNED),
    (_re.compile(r"\bpropos(?:ed|ing|al)\b|\bconsider(?:ing|ation)\b|\bcontemplat\w+\b", _re.IGNORECASE), DisclosureEventStatus.PROPOSED),
    (_re.compile(r"\bcancell?ed\b|\babandoned\b|\bwithdrawn\b", _re.IGNORECASE), DisclosureEventStatus.CANCELLED),
    (_re.compile(r"\bdelayed\b|\bpostponed\b|\bdeferred\b", _re.IGNORECASE), DisclosureEventStatus.DELAYED),
]

# Amount/value extraction.
_RE_DISC_AMOUNT = _re.compile(
    r"(?:₹|rs\.?|inr|usd|\$|eur)\s*(\d[\d,\.]*)\s*(?:crore|cr|lakh|mn|million|billion|bn)?",
    _re.IGNORECASE,
)
_RE_DISC_DATE = _re.compile(
    r"(?:effective\s+from|effective|on|dated?|from|with\s+effect\s+from|w\.?e\.?f\.?)\s+"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{1,2}\s+\w{3,9}\s+\d{2,4}"
    r"|\w{3,9}\s+\d{1,2},?\s+\d{2,4})",  # Month DD, YYYY  e.g. "April 06, 2026"
    _re.IGNORECASE,
)


def _classify_disclosure_event(text: str) -> DisclosureEventType:
    """Classify the primary event type from disclosure text. Conservative: UNKNOWN if ambiguous."""
    if _RE_DISC_ORDER.search(text):
        return DisclosureEventType.ORDER_AWARD
    if _RE_DISC_ACQUISITION.search(text):
        return DisclosureEventType.ACQUISITION
    if _RE_DISC_DIVESTMENT.search(text):
        return DisclosureEventType.DIVESTMENT
    if _RE_DISC_CAPACITY.search(text):
        return DisclosureEventType.CAPACITY
    if _RE_DISC_REGULATORY.search(text):
        return DisclosureEventType.REGULATORY_APPROVAL
    if _RE_DISC_MGMT_CHANGE.search(text):
        return DisclosureEventType.MANAGEMENT_CHANGE
    if _RE_DISC_CAPITAL.search(text):
        return DisclosureEventType.CAPITAL_RAISE
    if _RE_DISC_CREDIT.search(text):
        return DisclosureEventType.CREDIT_RATING
    if _RE_DISC_LITIGATION.search(text):
        return DisclosureEventType.LITIGATION
    if _RE_DISC_BOARD.search(text):
        return DisclosureEventType.BOARD_DECISION
    return DisclosureEventType.UNKNOWN


def _classify_disclosure_status(text: str) -> DisclosureEventStatus:
    """Classify event status conservatively. UNKNOWN when not explicit."""
    for pattern, status in _DISC_STATUS_PATTERNS:
        if pattern.search(text):
            return status
    return DisclosureEventStatus.UNKNOWN


def _extract_disclosure_amount(text: str) -> Optional[str]:
    """Return the first explicit amount string, or None. Never invent values."""
    m = _RE_DISC_AMOUNT.search(text)
    if m:
        return m.group(0).strip()
    return None


def _extract_disclosure_dates(text: str) -> dict:
    """Extract named dates from disclosure text. Returns dict with keys:
    event_date, target_date — both Optional[str].
    source/filing date comes from the manifest, not text parsing.
    """
    dates: dict = {"event_date": None, "target_date": None}
    matches = _RE_DISC_DATE.findall(text)
    if matches:
        dates["event_date"] = matches[0]
        if len(matches) >= 2:
            dates["target_date"] = matches[1]
    return dates


@dataclass
class ExchangeDisclosureResult:
    """Typed result returned by ExchangeDisclosureProcessor.process().

    Operational summary only — no investment analysis or downstream cascade.
    """

    company: str
    fiscal_year: Optional[str]
    source_file: str
    storage_path: str
    document_hash: str = ""
    source_type: str = "EXCHANGE_DISCLOSURE"
    source_channel: str = "EXCHANGE_FILING"
    filing_date: Optional[str] = None
    event_count: int = 0
    event_types: List[str] = field(default_factory=list)
    claim_count: int = 0
    status: str = "SUCCESS"
    warnings: List[str] = field(default_factory=list)
    evidence_path: str = ""
    claims_path: str = ""
    result_path: str = ""

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "fiscal_year": self.fiscal_year,
            "source_file": self.source_file,
            "storage_path": self.storage_path,
            "document_hash": self.document_hash,
            "source_type": self.source_type,
            "source_channel": self.source_channel,
            "filing_date": self.filing_date,
            "event_count": self.event_count,
            "event_types": self.event_types,
            "claim_count": self.claim_count,
            "status": self.status,
            "warnings": self.warnings,
            "evidence_path": self.evidence_path,
            "claims_path": self.claims_path,
            "result_path": self.result_path,
        }


class ExchangeDisclosureProcessor(ProcessorInterface):
    """Processor for EXCHANGE_DISCLOSURE source type.

    Ingests company-issued material corporate event disclosures into common
    evidence while preserving the distinction between:
    - reported/confirmed events (ORDER_AWARD, APPROVED, COMMISSIONED …)
    - management claims about those events
    - proposed/planned events not yet executed

    NOT registered in _PROCESSOR_REGISTRY.
    Registration requires direct production proof on a real disclosure.
    Status: BLOCKED_REAL_EXCHANGE_DISCLOSURE_MISSING (Phase 8, 2026-09-02).

    Core semantic contracts:
    - PROPOSED ≠ APPROVED ≠ COMPLETED (never promote state without evidence).
    - Board approval ≠ commercial completion.
    - Order received ≠ revenue recognized.
    - Plant commissioned ≠ fully operational/utilized.
    - Installed capacity ≠ production output.
    - Regulatory application ≠ regulatory approval.
    - Regulatory approval ≠ commercial launch.
    - Litigation allegation ≠ established liability.
    - Filing date ≠ event date ≠ target date.
    - Vague amounts never numerically invented.
    - Unnamed counterparties remain UNKNOWN.
    - Promotional statements not objective event facts.
    """

    def can_process(self, manifest: DocumentIntakeManifest) -> bool:
        from knowledge.document_intake import SourceType
        return (
            manifest.classification.status == ClassificationStatus.IDENTIFIED
            and manifest.document_identity.source_type == SourceType.EXCHANGE_DISCLOSURE
        )

    def process(
        self,
        manifest: DocumentIntakeManifest,
        source_path: Path,
    ) -> ExchangeDisclosureResult:
        import json as _json
        from knowledge.document_intake import SourceType

        if manifest.classification.status != ClassificationStatus.IDENTIFIED:
            raise ReviewRequiredError(
                "ExchangeDisclosureProcessor requires status=IDENTIFIED. "
                f"Got {manifest.classification.status.value}."
            )
        if manifest.document_identity.source_type != SourceType.EXCHANGE_DISCLOSURE:
            raise UnsupportedSourceTypeError(
                "ExchangeDisclosureProcessor can only process EXCHANGE_DISCLOSURE. "
                f"Got {manifest.document_identity.source_type.value}."
            )

        company = manifest.company_identity.resolved_company_key
        fiscal_year = getattr(manifest.reporting_period, "fiscal_year", None)
        if not company:
            raise ProcessorExecutionError(
                "ExchangeDisclosureProcessor requires a resolved company key."
            )

        warnings_list: List[str] = []
        content_hash = manifest.file.content_hash or ""
        hash_short = content_hash.replace("sha256:", "")[:16]

        # Storage: companies/<company>/<fy>/exchange_disclosures/<hash>/
        # When fiscal_year is not known, use 'undated' as safe fallback.
        fy_segment = fiscal_year or "undated"
        storage_root = (
            Path("companies") / company / fy_segment
            / "exchange_disclosures" / hash_short
        )
        storage_root.mkdir(parents=True, exist_ok=True)

        # Extract full text.
        full_text = self._extract_full_text(source_path, warnings_list)

        # Detect filing date from manifest.
        filing_date: Optional[str] = None
        if manifest.document_dates:
            filing_date = getattr(manifest.document_dates, "publication_date", None)

        # Classify the primary event type from the full text.
        event_type = _classify_disclosure_event(full_text)
        event_status = _classify_disclosure_status(full_text)
        amount = _extract_disclosure_amount(full_text)
        dates = _extract_disclosure_dates(full_text)

        # Extract event evidence records (one per structural paragraph/section).
        event_records = self._extract_event_records(
            full_text, event_type, event_status, amount, dates,
            company, fiscal_year, content_hash, str(source_path),
        )

        # Extract management claims (promotional/forward-looking language).
        management_claims = self._extract_management_claims(
            full_text, company, fiscal_year, content_hash, str(source_path),
        )

        # Write artifacts.
        evidence_path = storage_root / "disclosure_events.json"
        claims_path = storage_root / "management_claims.json"
        manifest_path = storage_root / "disclosure_manifest.json"
        result_path = storage_root / "processing_result.json"

        evidence_path.write_text(
            _json.dumps({
                "authority": "EXCHANGE_DISCLOSURE",
                "company": company,
                "fiscal_year": fiscal_year,
                "filing_date": filing_date,
                "event_type": event_type.value,
                "event_status": event_status.value,
                "source_file": str(source_path),
                "document_hash": content_hash,
                "records": event_records,
            }, indent=2, default=str),
            encoding="utf-8",
        )
        claims_path.write_text(
            _json.dumps({
                "authority": "EXCHANGE_DISCLOSURE",
                "company": company,
                "source_file": str(source_path),
                "claims": management_claims,
            }, indent=2, default=str),
            encoding="utf-8",
        )
        manifest_path.write_text(
            _json.dumps({
                "processor": "ExchangeDisclosureProcessor",
                "version": "1.0",
                "company": company,
                "fiscal_year": fiscal_year,
                "source_file": str(source_path),
                "document_hash": content_hash,
                "filing_date": filing_date,
                "event_type": event_type.value,
                "event_status": event_status.value,
                "event_count": len(event_records),
                "claim_count": len(management_claims),
                "warnings": warnings_list,
            }, indent=2, default=str),
            encoding="utf-8",
        )

        result = ExchangeDisclosureResult(
            company=company,
            fiscal_year=fiscal_year,
            source_file=str(source_path),
            storage_path=str(storage_root) + "/",
            document_hash=content_hash,
            filing_date=filing_date,
            event_count=len(event_records),
            event_types=[event_type.value],
            claim_count=len(management_claims),
            status="SUCCESS",
            warnings=warnings_list,
            evidence_path=str(evidence_path),
            claims_path=str(claims_path),
            result_path=str(result_path),
        )
        result_path.write_text(
            _json.dumps(result.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_full_text(source_path: Path, warnings_list: List[str]) -> str:
        try:
            from knowledge.document_processor import _extract_full_text as _shared_extract
            return _shared_extract(source_path)
        except Exception:
            pass
        try:
            import fitz
            doc = fitz.open(str(source_path))
            pages = [doc.load_page(i).get_text() for i in range(len(doc))]
            doc.close()
            return "\n".join(pages)
        except Exception as exc:
            warnings_list.append(f"Text extraction failed: {exc}")
            return ""

    @staticmethod
    def _extract_event_records(
        text: str,
        event_type: DisclosureEventType,
        event_status: DisclosureEventStatus,
        amount: Optional[str],
        dates: dict,
        company: str,
        fiscal_year: Optional[str],
        doc_hash: str,
        source_file: str,
    ) -> List[dict]:
        """Split disclosure text into paragraph-level event evidence records.

        Each record carries:
        - event_type (conservative, from whole-document classification)
        - event_status (conservative)
        - amount / counterparty if explicitly stated
        - source_date, event_date, target_date — all distinct
        - authority = EXCHANGE_DISCLOSURE (not AUDITED)
        - direct/inferred marker: 'direct' for confirmed facts, 'inferred' for hedged text

        Semantic boundaries enforced:
        - PROPOSED ≠ COMPLETED
        - ORDER_AWARD ≠ REVENUE_RECOGNIZED
        - COMMISSIONED ≠ OPERATIONAL
        """
        records = []
        # Split into paragraphs (blank-line separated).
        paras = [p.strip() for p in _re.split(r"\n{2,}", text) if len(p.strip()) > 40]
        for i, para in enumerate(paras):
            para_status = _classify_disclosure_status(para)
            if para_status == DisclosureEventStatus.UNKNOWN:
                para_status = event_status
            para_amount = _extract_disclosure_amount(para) or amount
            is_direct = not bool(_re.search(
                r"\bexpect\b|\bplan\b|\bintend\b|\bmay\b|\bsubject\s+to\b|\bpending\b",
                para, _re.IGNORECASE,
            ))
            record = {
                "record_id": f"disc_{doc_hash[:8]}_{i:03d}",
                "company": company,
                "fiscal_year": fiscal_year,
                "event_type": event_type.value,
                "event_status": para_status.value,
                "raw_text": para[:1000],
                "amount": para_amount,
                "counterparty": None,  # never inferred; must be explicit
                "location": None,
                "filing_date": None,  # set from manifest at call site
                "event_date": dates.get("event_date"),
                "target_date": dates.get("target_date"),
                "source_file": source_file,
                "source_type": "EXCHANGE_DISCLOSURE",
                "document_hash": doc_hash,
                "authority": "EXCHANGE_DISCLOSURE",
                "direct": is_direct,
                "confidence": "HIGH" if is_direct else "MEDIUM",
            }
            records.append(record)
        return records

    @staticmethod
    def _extract_management_claims(
        text: str,
        company: str,
        fiscal_year: Optional[str],
        doc_hash: str,
        source_file: str,
    ) -> List[dict]:
        """Extract management commentary / promotional sentences as claims.

        These are NOT objective event facts. They carry authority=EXCHANGE_DISCLOSURE
        with claim_type from the existing ManagementClaimType vocabulary.
        """
        claims = []
        sents = _re.split(r"(?<=[.!?])\s+", text)
        for i, sent in enumerate(sents):
            sent = sent.strip()
            if len(sent) < 30:
                continue
            claim_type = _classify_claim_type(sent)
            # Only record sentences with non-trivial claim semantics.
            if claim_type == ManagementClaimType.FACTUAL_STATEMENT:
                continue
            qualifiers = _extract_qualifiers(sent)
            claims.append({
                "claim_id": f"disc_claim_{doc_hash[:8]}_{i:03d}",
                "company": company,
                "fiscal_year": fiscal_year,
                "raw_text": sent[:800],
                "claim_type": claim_type.value,
                "qualifiers": qualifiers,
                "source_file": source_file,
                "source_type": "EXCHANGE_DISCLOSURE",
                "document_hash": doc_hash,
                "authority": "EXCHANGE_DISCLOSURE",
            })
        return claims


# ---------------------------------------------------------------------------
# Processor registry
#
# QuarterlyReportProcessor is registered here after the direct production
# proof passed (Phase 4 Gate B, 2026-09-02).  See SESSION_LOG.md.
# InvestorPresentationProcessor is registered here after the direct production
# proof passed (Phase 5, 2026-09-02).  See SESSION_LOG.md.
# EarningsCallTranscriptProcessor is registered after Phase 6.1 production
# proof on a real earnings-call transcript.  See SESSION_LOG.md.
# EarningsReleaseProcessor is registered after Phase 7 production proof.
# See SESSION_LOG.md for the specific document used.
# ExchangeDisclosureProcessor registered after Phase 8.1 production proof
# (2026-09-03) — dual-CXO resignation SE Intimation.
# Gates A–D passed; 49 adversarial tests passing.  See SESSION_LOG.md.
# ---------------------------------------------------------------------------

_PROCESSOR_REGISTRY: list[ProcessorInterface] = [
    AnnualReportProcessor(),
    QuarterlyReportProcessor(),
    InvestorPresentationProcessor(),
    EarningsCallTranscriptProcessor(),
    EarningsReleaseProcessor(),
    ExchangeDisclosureProcessor(),
]


def _find_processor(manifest: DocumentIntakeManifest) -> Optional[ProcessorInterface]:
    for proc in _PROCESSOR_REGISTRY:
        if proc.can_process(manifest):
            return proc
    return None


# ---------------------------------------------------------------------------
# Generic processing entry point
# ---------------------------------------------------------------------------

def process_document(
    path: Path | str,
    *,
    execute: bool = False,
) -> DocumentProcessingResult:
    """Canonical entry point: identify → route → optionally execute.

    Args:
        path:    Path to the raw document file.
        execute: When False (default), identifies and routes only — safe for
                 bulk ingestion and operator review flows.  When True, invokes
                 the processor for ROUTABLE manifests and returns the bridge
                 inputs.  Execution never starts automatically.

    Returns:
        DocumentProcessingResult with full manifest, routing decision, and
        (when execute=True) processor_output.

    This function catches all anticipated failure modes and returns them in the
    result struct.  Raw stack traces are never the only interface.
    """
    import time
    t0 = time.monotonic()
    path = Path(path)

    def _now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _finish(
        result: DocumentProcessingResult, t0: float
    ) -> DocumentProcessingResult:
        result.elapsed_seconds = round(time.monotonic() - t0, 3)
        result.processed_at = _now()
        return result

    # ── Stage 1: validate path ───────────────────────────────────────────────
    if not path.exists():
        return _finish(
            DocumentProcessingResult(
                manifest=None,
                routing=None,
                status=ProcessorStatus.ERROR,
                processor_output=None,
                error=f"File not found: {path}",
            ),
            t0,
        )

    if path.stat().st_size == 0:
        return _finish(
            DocumentProcessingResult(
                manifest=None,
                routing=None,
                status=ProcessorStatus.REJECTED,
                processor_output=None,
                error=f"Empty file: {path}",
            ),
            t0,
        )

    # ── Stage 2: identify ────────────────────────────────────────────────────
    try:
        manifest = identify_document(path)
    except Exception as exc:
        return _finish(
            DocumentProcessingResult(
                manifest=None,
                routing=None,
                status=ProcessorStatus.ERROR,
                processor_output=None,
                error=f"Identification failed: {exc}",
                warnings=[traceback.format_exc()],
            ),
            t0,
        )

    # ── Stage 3: inspect manifest status ─────────────────────────────────────
    cls_status = manifest.classification.status
    warnings: List[str] = list(manifest.classification.warnings)

    if cls_status == ClassificationStatus.REJECTED:
        return _finish(
            DocumentProcessingResult(
                manifest=manifest,
                routing=None,
                status=ProcessorStatus.REJECTED,
                processor_output=None,
                error="Document rejected during identification (corrupt, empty, or unreadable).",
                warnings=warnings,
            ),
            t0,
        )

    # ── Stage 4: route ───────────────────────────────────────────────────────
    router = SourceRouter()
    try:
        decision = router.route(manifest)
    except Exception as exc:
        return _finish(
            DocumentProcessingResult(
                manifest=manifest,
                routing=None,
                status=ProcessorStatus.ERROR,
                processor_output=None,
                error=f"Router failed unexpectedly: {exc}",
                warnings=warnings + [traceback.format_exc()],
            ),
            t0,
        )

    combined_warnings = warnings + [
        w for w in decision.warnings if w not in warnings
    ]

    # ── Stage 5: map routing outcome to processing status ────────────────────
    if decision.status == RouteStatus.REJECTED:
        return _finish(
            DocumentProcessingResult(
                manifest=manifest,
                routing=decision,
                status=ProcessorStatus.REJECTED,
                processor_output=None,
                error=decision.reason,
                warnings=combined_warnings,
            ),
            t0,
        )

    if decision.status == RouteStatus.REVIEW_REQUIRED:
        return _finish(
            DocumentProcessingResult(
                manifest=manifest,
                routing=decision,
                status=ProcessorStatus.REVIEW_REQUIRED,
                processor_output=None,
                error=decision.reason,
                warnings=combined_warnings,
            ),
            t0,
        )

    if decision.status == RouteStatus.UNSUPPORTED:
        return _finish(
            DocumentProcessingResult(
                manifest=manifest,
                routing=decision,
                status=ProcessorStatus.UNSUPPORTED,
                processor_output=None,
                error=decision.reason,
                warnings=combined_warnings,
            ),
            t0,
        )

    # ── Stage 6: ROUTABLE — execute if requested ─────────────────────────────
    if not execute:
        return _finish(
            DocumentProcessingResult(
                manifest=manifest,
                routing=decision,
                status=ProcessorStatus.ROUTED,
                processor_output=None,
                error=None,
                warnings=combined_warnings,
            ),
            t0,
        )

    # Execution requested — find and invoke the processor.
    processor = _find_processor(manifest)
    if processor is None:
        return _finish(
            DocumentProcessingResult(
                manifest=manifest,
                routing=decision,
                status=ProcessorStatus.UNSUPPORTED,
                processor_output=None,
                error=(
                    f"No processor registered for source type "
                    f"{manifest.document_identity.source_type.value} "
                    "even though routing declared AVAILABLE. "
                    "Registry and routing table are out of sync."
                ),
                warnings=combined_warnings,
            ),
            t0,
        )

    if not processor.can_process(manifest):
        return _finish(
            DocumentProcessingResult(
                manifest=manifest,
                routing=decision,
                status=ProcessorStatus.UNSUPPORTED,
                processor_output=None,
                error=f"Processor {type(processor).__name__} declined this manifest.",
                warnings=combined_warnings,
            ),
            t0,
        )

    try:
        output = processor.process(manifest, path)
    except CompatibilityAdapterError as exc:
        return _finish(
            DocumentProcessingResult(
                manifest=manifest,
                routing=decision,
                status=ProcessorStatus.ERROR,
                processor_output=None,
                error=f"Compatibility adapter failure: {exc}",
                warnings=combined_warnings,
            ),
            t0,
        )
    except ProcessorExecutionError as exc:
        return _finish(
            DocumentProcessingResult(
                manifest=manifest,
                routing=decision,
                status=ProcessorStatus.ERROR,
                processor_output=None,
                error=f"Processor execution failure: {exc}",
                warnings=combined_warnings,
            ),
            t0,
        )
    except Exception as exc:
        return _finish(
            DocumentProcessingResult(
                manifest=manifest,
                routing=decision,
                status=ProcessorStatus.ERROR,
                processor_output=None,
                error=f"Unexpected processor error: {exc}",
                warnings=combined_warnings + [traceback.format_exc()],
            ),
            t0,
        )

    return _finish(
        DocumentProcessingResult(
            manifest=manifest,
            routing=decision,
            status=ProcessorStatus.EXECUTED,
            processor_output=output,
            error=None,
            warnings=combined_warnings,
        ),
        t0,
    )
