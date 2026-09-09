"""Canonical source router for Prometheus document intake.

Converts a DocumentIntakeManifest into a RoutingDecision without touching
any downstream processor or intelligence pipeline.

Routing rules:
  REJECTED manifest   → RouteStatus.REJECTED     (no processor invoked)
  UNIDENTIFIED        → RouteStatus.UNSUPPORTED   (identity not resolved)
  REVIEW_REQUIRED     → RouteStatus.REVIEW_REQUIRED (operator must intervene)
  IDENTIFIED + processor available   → RouteStatus.ROUTABLE
  IDENTIFIED + processor unavailable → RouteStatus.UNSUPPORTED

Source-type processor map (Phase 5):
  ANNUAL_REPORT           → AVAILABLE   (via legacy compatibility adapter)
  QUARTERLY_REPORT        → AVAILABLE   (QuarterlyReportProcessor; direct production proof passed)
  INVESTOR_PRESENTATION   → AVAILABLE   (InvestorPresentationProcessor; direct production proof passed)
  EARNINGS_CALL_TRANSCRIPT → AVAILABLE   (EarningsCallTranscriptProcessor; direct production proof passed)
  EARNINGS_RELEASE        → AVAILABLE   (EarningsReleaseProcessor; direct production proof passed)
  EXCHANGE_DISCLOSURE     → AVAILABLE   (ExchangeDisclosureProcessor; Phase 8.1 production proof passed)
  all others              → NOT_IMPLEMENTED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from knowledge.document_intake import (
    ClassificationStatus,
    DocumentIntakeManifest,
    SourceChannel,
    SourceType,
)


# ---------------------------------------------------------------------------
# Canonical enums
# ---------------------------------------------------------------------------

class RouteStatus(str, Enum):
    """Top-level routing outcome."""
    ROUTABLE = "ROUTABLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    REJECTED = "REJECTED"


class ProcessorState(str, Enum):
    """Whether a processor for this source family exists in the current build."""
    AVAILABLE = "AVAILABLE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    UNAVAILABLE = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Source-type routing table
# ---------------------------------------------------------------------------

_SOURCE_TYPE_PROCESSOR_MAP: dict[SourceType, ProcessorState] = {
    SourceType.ANNUAL_REPORT: ProcessorState.AVAILABLE,
    SourceType.QUARTERLY_REPORT: ProcessorState.AVAILABLE,
    SourceType.INVESTOR_PRESENTATION: ProcessorState.AVAILABLE,
    SourceType.EARNINGS_CALL_TRANSCRIPT: ProcessorState.AVAILABLE,
    SourceType.EARNINGS_RELEASE: ProcessorState.AVAILABLE,
    SourceType.EXCHANGE_DISCLOSURE: ProcessorState.AVAILABLE,
    SourceType.EXCHANGE_FILING: ProcessorState.NOT_IMPLEMENTED,
    SourceType.OTHER: ProcessorState.NOT_IMPLEMENTED,
    SourceType.UNKNOWN: ProcessorState.NOT_IMPLEMENTED,
}

_SOURCE_TYPE_ROUTE_LABEL: dict[SourceType, str] = {
    SourceType.ANNUAL_REPORT: "annual_report",
    SourceType.QUARTERLY_REPORT: "quarterly_report",
    SourceType.INVESTOR_PRESENTATION: "investor_presentation",
    SourceType.EARNINGS_CALL_TRANSCRIPT: "earnings_call_transcript",
    SourceType.EARNINGS_RELEASE: "earnings_release",
    SourceType.EXCHANGE_DISCLOSURE: "exchange_disclosure",
    SourceType.EXCHANGE_FILING: "exchange_filing",
    SourceType.OTHER: "other",
    SourceType.UNKNOWN: "unknown",
}


# ---------------------------------------------------------------------------
# Routing decision contract
# ---------------------------------------------------------------------------

@dataclass
class RoutingDecision:
    """Canonical result of routing a DocumentIntakeManifest.

    Fields:
        manifest:          The input manifest (unchanged).
        status:            Top-level routing outcome.
        route:             Source-family label (e.g. "annual_report").
        processor:         Whether a processor exists for this source family.
        destination:       Intended canonical storage path, computed only after
                           company+year are resolved.  None when unresolvable.
        reason:            Human-readable explanation of the routing outcome.
        warnings:          Non-fatal notes (e.g. weak confidence, unresolved scope).
        unresolved_fields: Populated for REVIEW_REQUIRED — fields the operator
                           must confirm before auto-routing can proceed.
        content_hash:      Carried from manifest for idempotency consumers.
        document_id:       Carried from manifest for idempotency consumers.
    """
    manifest: DocumentIntakeManifest
    status: RouteStatus
    route: str
    processor: ProcessorState
    destination: Optional[str]
    reason: str
    warnings: List[str] = field(default_factory=list)
    unresolved_fields: List[str] = field(default_factory=list)
    content_hash: str = ""
    document_id: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "route": self.route,
            "processor": self.processor.value,
            "destination": self.destination,
            "reason": self.reason,
            "warnings": list(self.warnings),
            "unresolved_fields": list(self.unresolved_fields),
            "content_hash": self.content_hash,
            "document_id": self.document_id,
        }


# ---------------------------------------------------------------------------
# Destination derivation
# ---------------------------------------------------------------------------

def _derive_destination(manifest: DocumentIntakeManifest) -> Optional[str]:
    """Compute the intended canonical storage path from a resolved manifest.

    Annual:    companies/<company>/<fy>/raw/<filename>
    Quarterly: companies/<company>/<fy>/quarters/<q>/<filename>

    Returns None when company, year, or (for quarterly) quarter are
    unresolved — identity must precede destination.
    """
    company = manifest.company_identity.resolved_company_key
    reporting = manifest.reporting_period
    fiscal_year = reporting.fiscal_year if reporting else None
    filename = manifest.file.original_filename or ""

    if not company or not fiscal_year or not filename:
        return None

    source_type = manifest.document_identity.source_type
    if source_type == SourceType.QUARTERLY_REPORT:
        fiscal_quarter = reporting.fiscal_quarter if reporting else None
        if fiscal_quarter:
            q_label = fiscal_quarter.value  # "Q1" … "Q4"
            return str(
                Path("companies") / company / fiscal_year / "quarters" / q_label / filename
            )
        # Quarter not resolved — cannot compute quarterly destination.
        return None

    if source_type == SourceType.INVESTOR_PRESENTATION:
        # Document-scoped path prevents collision when multiple presentations exist.
        hash_short = manifest.file.content_hash.replace("sha256:", "")[:16]
        return str(
            Path("companies") / company / fiscal_year / "presentations" / hash_short / filename
        )

    return str(Path("companies") / company / fiscal_year / "raw" / filename)


# ---------------------------------------------------------------------------
# Source router
# ---------------------------------------------------------------------------

class SourceRouter:
    """Converts a DocumentIntakeManifest into a canonical RoutingDecision.

    The router is stateless and has no side effects.  It does not invoke any
    processor, move any file, or touch downstream intelligence systems.
    """

    def route(self, manifest: DocumentIntakeManifest) -> RoutingDecision:
        """Return the canonical RoutingDecision for *manifest*."""
        status = manifest.classification.status
        warnings: List[str] = list(manifest.classification.warnings)

        # ── REJECTED ────────────────────────────────────────────────────────
        if status == ClassificationStatus.REJECTED:
            return RoutingDecision(
                manifest=manifest,
                status=RouteStatus.REJECTED,
                route="rejected",
                processor=ProcessorState.UNAVAILABLE,
                destination=None,
                reason=(
                    "Document was rejected during identification "
                    "(corrupt, empty, or unreadable file)."
                ),
                warnings=warnings,
                unresolved_fields=list(manifest.classification.unresolved_fields),
                content_hash=manifest.file.content_hash,
                document_id=manifest.document_id,
            )

        # ── UNIDENTIFIED ─────────────────────────────────────────────────────
        if status == ClassificationStatus.UNIDENTIFIED:
            return RoutingDecision(
                manifest=manifest,
                status=RouteStatus.UNSUPPORTED,
                route="unresolved",
                processor=ProcessorState.UNAVAILABLE,
                destination=None,
                reason=(
                    "Document company could not be resolved from content. "
                    "Cannot route without a confirmed company identity."
                ),
                warnings=warnings,
                unresolved_fields=list(manifest.classification.unresolved_fields),
                content_hash=manifest.file.content_hash,
                document_id=manifest.document_id,
            )

        # ── REVIEW_REQUIRED ──────────────────────────────────────────────────
        if status == ClassificationStatus.REVIEW_REQUIRED:
            source_type = manifest.document_identity.source_type
            route_label = _SOURCE_TYPE_ROUTE_LABEL.get(source_type, "unknown")
            # Expose what the operator needs to see — do not guess or auto-select.
            return RoutingDecision(
                manifest=manifest,
                status=RouteStatus.REVIEW_REQUIRED,
                route=route_label,
                processor=ProcessorState.UNAVAILABLE,
                destination=None,
                reason=(
                    "Document identity has unresolved or conflicting signals. "
                    "Operator review is required before this document can be "
                    "automatically routed."
                ),
                warnings=warnings,
                unresolved_fields=list(manifest.classification.unresolved_fields),
                content_hash=manifest.file.content_hash,
                document_id=manifest.document_id,
            )

        # ── IDENTIFIED ───────────────────────────────────────────────────────
        # Identification success != processing support.  Determine source family
        # and look up the processor state separately.
        source_type = manifest.document_identity.source_type
        route_label = _SOURCE_TYPE_ROUTE_LABEL.get(source_type, "unknown")
        processor_state = _SOURCE_TYPE_PROCESSOR_MAP.get(
            source_type, ProcessorState.NOT_IMPLEMENTED
        )

        # Destination is computed AFTER identity is confirmed.
        destination = _derive_destination(manifest)

        if processor_state == ProcessorState.AVAILABLE:
            return RoutingDecision(
                manifest=manifest,
                status=RouteStatus.ROUTABLE,
                route=route_label,
                processor=processor_state,
                destination=destination,
                reason=(
                    f"Document identified as {source_type.value}. "
                    "Processor is available."
                ),
                warnings=warnings,
                unresolved_fields=list(manifest.classification.unresolved_fields),
                content_hash=manifest.file.content_hash,
                document_id=manifest.document_id,
            )

        # Recognized but no processor yet — NOT an identification failure.
        return RoutingDecision(
            manifest=manifest,
            status=RouteStatus.UNSUPPORTED,
            route=route_label,
            processor=processor_state,
            destination=destination,
            reason=(
                f"Document identified as {source_type.value}. "
                "No processor is implemented for this source family in the "
                "current build. Do not fall back to annual-report pipeline."
            ),
            warnings=warnings,
            unresolved_fields=list(manifest.classification.unresolved_fields),
            content_hash=manifest.file.content_hash,
            document_id=manifest.document_id,
        )
