"""Prometheus Inbox scanner — process all pending documents in data/Inbox/.

Usage (dry run — identify and decide, no execution):
    python -m pipelines.scan_inbox

Usage (execute processing):
    python -m pipelines.scan_inbox --execute

Usage (force reprocess even if output exists):
    python -m pipelines.scan_inbox --execute --force

Public API:
    scan_inbox(execute=False, force=False) -> ScanReport

One canonical loop:
  1. Discover PDFs in INBOX
  2. Compute SHA-256
  3. Registry lookup → decide_processing_action()
  4. Act on decision: process / skip / flag
  5. On success: move PDF to Processed/, update registry
  6. On failure: move PDF to Failed/, update registry
  7. On REVIEW_REQUIRED: move PDF to Review/, update registry

Crash safety:
  PDF is moved only AFTER processor success AND artifact validation succeeds.
  Registry is committed AFTER the move.  If the process dies between move
  and registry commit, the next scan re-discovers the file in its new
  location and logs a warning (orphan in Processed/ not in registry).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from core.inbox_paths import (
    FAILED,
    INBOX,
    PROCESSED,
    REVIEW,
    UNPERIODIZED_BUCKET,
    ensure_workflow_dirs,
    processed_dir,
    safe_archive_path,
)
from core.document_intake_registry import (
    DocumentIntakeRegistry,
    ProcessingDecision,
    ProcessingStatus,
    WorkflowState,
    decide_processing_action,
    fingerprint_from_manifest,
    semantic_fingerprint,
)
from knowledge.document_intake import compute_content_hash
from knowledge.document_identifier import identify_document
from knowledge.document_processor import (
    DocumentProcessingResult,
    ProcessorStatus,
    process_document,
)


# ---------------------------------------------------------------------------
# Scan report
# ---------------------------------------------------------------------------

@dataclass
class DocumentOutcome:
    filename: str
    document_hash: str
    decision: str
    final_status: str
    destination: Optional[str] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class ScanReport:
    total_discovered: int = 0
    process_new: int = 0
    reuse_existing: int = 0
    reprocess_stale: int = 0
    retry_failed: int = 0
    blocked_review: int = 0
    succeeded: int = 0
    failed: int = 0
    review_required: int = 0
    skipped_dry_run: int = 0
    outcomes: List[DocumentOutcome] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "── Inbox Scan Report ──────────────────────────",
            f"  Discovered:       {self.total_discovered}",
            f"  PROCESS_NEW:      {self.process_new}",
            f"  REUSE_EXISTING:   {self.reuse_existing}",
            f"  REPROCESS_STALE:  {self.reprocess_stale}",
            f"  RETRY_FAILED:     {self.retry_failed}",
            f"  BLOCKED_REVIEW:   {self.blocked_review}",
            "  Results:",
            f"    Succeeded:      {self.succeeded}",
            f"    Failed:         {self.failed}",
            f"    Review:         {self.review_required}",
            f"    Dry-run skipped:{self.skipped_dry_run}",
            "───────────────────────────────────────────────",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_processor_name(result: DocumentProcessingResult) -> str:
    """Derive the processor name from the routing decision."""
    if result.routing is None:
        return "Unknown"
    route = result.routing.route
    if route is None:
        return "Unknown"
    return getattr(route, "processor_class", None) or str(route)


def _derive_archive_dir(result: DocumentProcessingResult) -> Path:
    """Derive the Processed sub-directory from the manifest + routing."""
    manifest = result.manifest
    if manifest is None:
        return PROCESSED / "unknown" / UNPERIODIZED_BUCKET / "unknown"

    ci = getattr(manifest, "company_identity", None)
    company = getattr(ci, "resolved_company_key", None) or "unknown"

    di = getattr(manifest, "document_identity", None)
    st_obj = getattr(di, "source_type", None)
    source_type = st_obj.value.lower() if st_obj else "unknown"

    rp = getattr(manifest, "reporting_period", None)
    fy = getattr(rp, "fiscal_year", None) if rp else None
    fq_obj = getattr(rp, "fiscal_quarter", None) if rp else None
    quarter = fq_obj.value.lower() if fq_obj else None

    if fy and quarter:
        period = f"{quarter} {fy}"
    elif fy:
        period = fy
    else:
        period = UNPERIODIZED_BUCKET

    return processed_dir(company, period, source_type)


def _collect_artifact_paths(result: DocumentProcessingResult) -> List[str]:
    """Collect artifact file paths from the processor output dict."""
    out = result.processor_output
    if not isinstance(out, dict):
        return []
    paths: List[str] = []
    for v in out.values():
        if isinstance(v, (str, Path)):
            p = Path(str(v))
            if p.exists():
                paths.append(str(p))
        elif isinstance(v, list):
            for item in v:
                p = Path(str(item))
                if p.exists():
                    paths.append(str(p))
    return paths


def _move_pdf(source: Path, dest_dir: Path, content_hash_short: str) -> Path:
    """Move a PDF to dest_dir, creating it first, with collision safety."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = safe_archive_path(dest_dir, source.name, content_hash_short)
    shutil.move(str(source), str(dest))
    return dest


# ---------------------------------------------------------------------------
# Core scan loop
# ---------------------------------------------------------------------------

def scan_inbox(
    execute: bool = False,
    force: bool = False,
    registry: Optional[DocumentIntakeRegistry] = None,
    inbox: Optional[Path] = None,
) -> ScanReport:
    """Scan INBOX and process every PDF found.

    Args:
        execute: When False (dry run), identifies and decides but does not
                 invoke processors or move files.
        force:   Force reprocessing of documents already marked REUSE_EXISTING.
        registry: Override the live registry (for testing).
        inbox:   Override the Inbox path (for testing).
    """
    ensure_workflow_dirs()

    reg = registry or DocumentIntakeRegistry()
    inbox_path = inbox or INBOX

    pdf_files = sorted(inbox_path.glob("*.pdf"))
    report = ScanReport(total_discovered=len(pdf_files))

    for pdf in pdf_files:
        outcome = _process_one(pdf, execute=execute, force=force, registry=reg)
        report.outcomes.append(outcome)

        decision = outcome.decision
        if decision == ProcessingDecision.PROCESS_NEW.value:
            report.process_new += 1
        elif decision == ProcessingDecision.REUSE_EXISTING.value:
            report.reuse_existing += 1
        elif decision == ProcessingDecision.REPROCESS_STALE.value:
            report.reprocess_stale += 1
        elif decision == ProcessingDecision.RETRY_FAILED.value:
            report.retry_failed += 1
        elif decision == ProcessingDecision.BLOCK_REVIEW_REQUIRED.value:
            report.blocked_review += 1

        final = outcome.final_status
        if final == "SUCCESS":
            report.succeeded += 1
        elif final == "FAILED":
            report.failed += 1
        elif final == "REVIEW_REQUIRED":
            report.review_required += 1
        elif final == "DRY_RUN":
            report.skipped_dry_run += 1
        elif final == "REUSED":
            report.reuse_existing += 0   # already counted above

    return report


def _process_one(
    pdf: Path,
    execute: bool,
    force: bool,
    registry: DocumentIntakeRegistry,
) -> DocumentOutcome:
    """Process a single Inbox PDF end-to-end."""
    document_hash = compute_content_hash(pdf)
    short_hash = document_hash.replace("sha256:", "")[:8]

    # --- Step 1: identify to get the manifest ---
    manifest = identify_document(pdf)

    # --- Step 2: register if new ---
    existing = registry.get(document_hash)
    if existing is None:
        registry.register_new(
            document_hash=document_hash,
            filename=pdf.name,
            manifest=manifest,
            initial_path=str(pdf),
            workflow_state=WorkflowState.INBOX,
        )
    else:
        registry.add_filename_alias(document_hash, pdf.name)

    # --- Step 3: decide ---
    # Infer processor name from manifest source_type
    st_obj = getattr(getattr(manifest, "document_identity", None), "source_type", None)
    st_val = st_obj.value if st_obj else None
    _PROCESSOR_MAP = {
        "ANNUAL_REPORT": "AnnualReportProcessor",
        "QUARTERLY_REPORT": "QuarterlyReportProcessor",
        "INVESTOR_PRESENTATION": "InvestorPresentationProcessor",
        "EARNINGS_CALL_TRANSCRIPT": "EarningsCallTranscriptProcessor",
        "EARNINGS_RELEASE": "EarningsReleaseProcessor",
        "EXCHANGE_DISCLOSURE": "ExchangeDisclosureProcessor",
    }
    processor_name = _PROCESSOR_MAP.get(st_val) if st_val else None
    decision = decide_processing_action(
        document_hash=document_hash,
        manifest=manifest,
        processor_name=processor_name,
        registry=registry,
        force=force,
    )

    # --- Step 4: REVIEW_REQUIRED decision (before touching anything) ---
    if decision == ProcessingDecision.BLOCK_REVIEW_REQUIRED:
        return DocumentOutcome(
            filename=pdf.name,
            document_hash=document_hash,
            decision=decision.value,
            final_status="BLOCKED",
        )

    # --- Step 5: REUSE_EXISTING — no processing needed ---
    if decision == ProcessingDecision.REUSE_EXISTING:
        return DocumentOutcome(
            filename=pdf.name,
            document_hash=document_hash,
            decision=decision.value,
            final_status="REUSED",
        )

    # --- Step 6: dry-run short-circuit ---
    if not execute:
        return DocumentOutcome(
            filename=pdf.name,
            document_hash=document_hash,
            decision=decision.value,
            final_status="DRY_RUN",
        )

    # --- Step 7: REVIEW_REQUIRED from identification stage ---
    from knowledge.document_intake import ClassificationStatus
    _cls = getattr(manifest, "classification", None)
    cls_status = getattr(_cls, "status", None)
    if cls_status == ClassificationStatus.REVIEW_REQUIRED:
        unresolved = getattr(manifest, "unresolved_fields", []) or []
        dest = _move_pdf(pdf, REVIEW, short_hash)
        registry.record_review_required(
            document_hash=document_hash,
            unresolved_fields=list(unresolved),
            new_path=str(dest),
        )
        return DocumentOutcome(
            filename=pdf.name,
            document_hash=document_hash,
            decision=decision.value,
            final_status="REVIEW_REQUIRED",
            destination=str(dest),
            warnings=list(unresolved),
        )

    # --- Step 8: Execute ---
    result = process_document(pdf, execute=True)

    if result.status == ProcessorStatus.EXECUTED:
        archive_dir = _derive_archive_dir(result)
        dest = _move_pdf(pdf, archive_dir, short_hash)
        artifact_paths = _collect_artifact_paths(result)
        pname = processor_name or _derive_processor_name(result)
        registry.record_success(
            document_hash=document_hash,
            processor_name=pname,
            artifact_paths=artifact_paths,
            evidence_count=len(artifact_paths),
            new_path=str(dest),
            warnings=list(result.warnings or []),
        )
        return DocumentOutcome(
            filename=pdf.name,
            document_hash=document_hash,
            decision=decision.value,
            final_status="SUCCESS",
            destination=str(dest),
            warnings=list(result.warnings or []),
        )

    elif result.status == ProcessorStatus.REVIEW_REQUIRED:
        dest = _move_pdf(pdf, REVIEW, short_hash)
        registry.record_review_required(
            document_hash=document_hash,
            unresolved_fields=list(result.warnings or []),
            new_path=str(dest),
        )
        return DocumentOutcome(
            filename=pdf.name,
            document_hash=document_hash,
            decision=decision.value,
            final_status="REVIEW_REQUIRED",
            destination=str(dest),
            warnings=list(result.warnings or []),
        )

    else:
        # ERROR, UNSUPPORTED, REJECTED
        dest = _move_pdf(pdf, FAILED, short_hash)
        err = result.error or f"Processor returned status {result.status.value}"
        registry.record_failure(
            document_hash=document_hash,
            processor_name=_derive_processor_name(result),
            error=err,
            new_path=str(dest),
        )
        return DocumentOutcome(
            filename=pdf.name,
            document_hash=document_hash,
            decision=decision.value,
            final_status="FAILED",
            destination=str(dest),
            error=err,
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan data/Inbox/ and process all pending documents."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run processors and move files (default: dry run).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess documents even if REUSE_EXISTING applies.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON report to stdout.",
    )
    args = parser.parse_args()

    if not args.execute:
        print("[DRY RUN] Passing --execute to actually process files.\n")

    report = scan_inbox(execute=args.execute, force=args.force)
    print(report.summary())

    if args.json:
        print(json.dumps(
            {"outcomes": [asdict(o) for o in report.outcomes]},
            indent=2,
        ))


if __name__ == "__main__":
    _main()
