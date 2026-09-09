"""LEGACY MIGRATION UTILITY — completed 2026-09-03, retained for history only.

This one-time script migrated 61 PDFs from the retired data/annual_reports/
directory into the canonical workflow (data/Processed/, data/Review/,
data/Inbox/, data/Failed/). It is NOT part of normal runtime.

The migration is complete:
  • data/annual_reports/ no longer exists.
  • data/.document_registry.json is the authoritative source of truth (59 entries).
  • All runtime code resolves documents via the registry or canonical Processed/ paths.

Do NOT re-run this script on a clean system — it expects data/annual_reports/ to
exist and will do nothing useful if the directory is absent.

If you need to understand past migration decisions, read:
  governance/SESSION_LOG.md  (Phase 10.2 section)
  governance/BACKLOG.md      (ENG-073 Completed)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Ensure repo root is importable
# ---------------------------------------------------------------------------
import os
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    PROCESSOR_VERSIONS,
    semantic_fingerprint,
)
import re
from knowledge.document_intake import compute_content_hash
from knowledge.document_identifier import identify_document
from knowledge.document_intake import (
    ClassificationStatus,
    SourceType,
)


# ---------------------------------------------------------------------------
# Known REVIEW_REQUIRED filenames (confirmed in prior audit)
# ---------------------------------------------------------------------------

KNOWN_REVIEW_FILENAMES = {
    "afr_q4_fy25.pdf",
    "TPL_Reg30_MergerUpdate_Karix_Gamooga-signed.pdf",
    "investor_update_q3fy26.pdf",
    "investor_update_q4fy26.pdf",
    "tpl_earningscall_recording_18102025.pdf",
}

# Annual-report names that map to a confirmed pipeline run (company → years)
# Derived from companies/<company>/<fy>/run_summary.json status="pass"
CONFIRMED_ANNUAL_REPORTS: Dict[str, List[str]] = {
    "tanla":        ["fy20", "fy22", "fy23", "fy24", "fy25", "fy26"],
    "sun_pharma":   ["fy20", "fy21", "fy22", "fy23", "fy24", "fy25", "fy26"],
    "ujjivan":      ["fy21", "fy22", "fy23", "fy24", "fy25"],
    "polymatech":   ["fy22", "fy23", "fy24", "fy25"],
    "datapatterns": ["fy22", "fy23", "fy24", "fy25", "fy26"],
    "tips":         ["fy21", "fy22", "fy23", "fy24", "fy25"],
}


def _filename_annual_report_hint(filename: str) -> tuple:
    """Extract (company, fy) from conventional annual-report filenames.

    Recognises ``<company>_fy<YY>.pdf`` (e.g. ``sun_pharma_fy20.pdf``).
    Returns (None, None) when the filename doesn't match the convention.
    Company must be present in CONFIRMED_ANNUAL_REPORTS.
    """
    stem = Path(filename).stem  # e.g. "sun_pharma_fy20"
    m = re.search(r"_?(fy\d{2,4})$", stem, re.IGNORECASE)
    if not m:
        return None, None
    fy = m.group(1).lower()  # e.g. "fy20"
    # Company is everything before "_fy<YY>"
    company_part = stem[: m.start()].rstrip("_").lower()
    # Match against known companies (longest prefix match)
    if company_part in CONFIRMED_ANNUAL_REPORTS:
        return company_part, fy
    return None, None


def _is_confirmed_annual(company: str, fy: str) -> bool:
    return fy in CONFIRMED_ANNUAL_REPORTS.get(company, [])


def _collect_annual_artifacts(company: str, fy: str) -> List[str]:
    """Return paths of known pipeline outputs for this company+fy."""
    base = Path(__file__).resolve().parent.parent / "companies" / company / fy
    patterns = [
        "run_summary.json",
        "evidence_layer_summary.json",
        "extracted/clean_chunks.json",
        "raw/project_discovery_results.json",
    ]
    found = []
    for pat in patterns:
        p = base / pat
        if p.exists():
            found.append(str(p))
    return found


# ---------------------------------------------------------------------------
# Migration report
# ---------------------------------------------------------------------------

class MigrationReport:
    def __init__(self) -> None:
        self.total = 0
        self.skipped_already_registered = 0
        self.bootstrapped_annual = 0
        self.bootstrapped_other = 0
        self.sent_to_review = 0
        self.sent_to_inbox = 0
        self.duplicate_aliases = 0
        self.errors: List[str] = []
        self.rows: List[dict] = []

    def add(self, row: dict) -> None:
        self.rows.append(row)

    def summary(self) -> str:
        lines = [
            "── Migration Report ────────────────────────────",
            f"  Total PDFs:              {self.total}",
            f"  Already registered:      {self.skipped_already_registered}",
            f"  Bootstrapped (annual):   {self.bootstrapped_annual}",
            f"  Bootstrapped (other):    {self.bootstrapped_other}",
            f"  Duplicate aliases added: {self.duplicate_aliases}",
            f"  Sent to Review/:         {self.sent_to_review}",
            f"  Sent to Inbox/:          {self.sent_to_inbox}",
            f"  Errors:                  {len(self.errors)}",
            "────────────────────────────────────────────────",
        ]
        if self.errors:
            lines.append("  Error details:")
            for e in self.errors:
                lines.append(f"    • {e}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core migration
# ---------------------------------------------------------------------------

def migrate(execute: bool = False) -> MigrationReport:
    ensure_workflow_dirs()
    source_dir = Path(__file__).resolve().parent.parent / "data" / "annual_reports"
    reg = DocumentIntakeRegistry()
    report = MigrationReport()

    pdfs = sorted(source_dir.glob("*.pdf"))
    report.total = len(pdfs)

    seen_hashes: Dict[str, str] = {}   # hash → first filename (for duplicate detection)

    for pdf in pdfs:
        try:
            _migrate_one(pdf, execute=execute, reg=reg, report=report, seen_hashes=seen_hashes)
        except Exception as exc:
            report.errors.append(f"{pdf.name}: {exc}")
            report.add({"file": pdf.name, "category": "ERROR", "error": str(exc)})

    return report


def _migrate_one(
    pdf: Path,
    execute: bool,
    reg: DocumentIntakeRegistry,
    report: MigrationReport,
    seen_hashes: Dict[str, str],
) -> None:
    document_hash = compute_content_hash(pdf)
    short_hash = document_hash.replace("sha256:", "")[:8]

    # ── Already registered? ────────────────────────────────────────────────
    existing = reg.get(document_hash)
    if existing is not None:
        if execute:
            reg.add_filename_alias(document_hash, pdf.name)
        report.skipped_already_registered += 1
        report.add({"file": pdf.name, "category": "ALREADY_REGISTERED", "hash": document_hash})
        return

    # ── Duplicate (same content, different filename)? ──────────────────────
    if document_hash in seen_hashes:
        first_name = seen_hashes[document_hash]
        if execute:
            reg.add_filename_alias(document_hash, pdf.name)
        report.duplicate_aliases += 1
        report.add({
            "file": pdf.name,
            "category": "DUPLICATE_ALIAS",
            "hash": document_hash,
            "primary": first_name,
        })
        return
    seen_hashes[document_hash] = pdf.name

    # ── Known REVIEW_REQUIRED? ─────────────────────────────────────────────
    if pdf.name in KNOWN_REVIEW_FILENAMES:
        _handle_review(pdf, document_hash, short_hash, execute=execute, reg=reg, report=report)
        return

    # ── Filename-based annual-report fast-path (bypasses identifier) ───────
    # Confirmed annual reports are bootstrapped using filename-derived period
    # (company_fy<YY>.pdf) and the known pipeline run, rather than trusting
    # the identifier which can mis-detect fiscal year for older Sun Pharma /
    # early Tanla reports, or fail to resolve the company key for Data Patterns.
    fn_company, fn_fy = _filename_annual_report_hint(pdf.name)
    if fn_company and fn_fy and _is_confirmed_annual(fn_company, fn_fy):
        artifacts = _collect_annual_artifacts(fn_company, fn_fy)
        dest_dir = processed_dir(fn_company, fn_fy, "annual_report")
        dest = safe_archive_path(dest_dir, pdf.name, short_hash)
        if execute:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(pdf), str(dest))
            reg.bootstrap(
                document_hash=document_hash,
                filename=pdf.name,
                company=fn_company,
                source_type="annual_report",
                fiscal_year=fn_fy,
                quarter=None,
                processor_name="AnnualReportProcessor",
                artifact_paths=artifacts,
                archived_path=str(dest),
            )
        report.bootstrapped_annual += 1
        report.add({
            "file": pdf.name,
            "category": "BOOTSTRAPPED_ANNUAL",
            "hash": document_hash,
            "company": fn_company,
            "fy": fn_fy,
            "destination": str(dest),
            "execute": execute,
            "note": "filename-derived period (bypassed identifier)",
        })
        return

    # ── Identify ───────────────────────────────────────────────────────────
    manifest = identify_document(pdf)

    cls_status = getattr(getattr(manifest, "classification", None), "status", None)
    if cls_status in (ClassificationStatus.REVIEW_REQUIRED, ClassificationStatus.REJECTED):
        _handle_review(pdf, document_hash, short_hash, execute=execute, reg=reg, report=report,
                       manifest=manifest)
        return

    if cls_status == ClassificationStatus.UNIDENTIFIED:
        _handle_inbox(pdf, document_hash, short_hash, manifest, execute=execute, reg=reg, report=report)
        return

    # Extract semantic fields
    ci = getattr(manifest, "company_identity", None)
    company = getattr(ci, "resolved_company_key", None)
    di = getattr(manifest, "document_identity", None)
    st_obj = getattr(di, "source_type", None)
    source_type = st_obj.value if st_obj else None
    rp = getattr(manifest, "reporting_period", None)
    fy = getattr(rp, "fiscal_year", None) if rp else None
    fq_obj = getattr(rp, "fiscal_quarter", None) if rp else None
    quarter = fq_obj.value.lower() if fq_obj else None
    es_obj = getattr(manifest, "entity_scope", None)
    entity_scope = es_obj.value if es_obj else None

    if company is None or source_type is None:
        # Cannot classify confidently → Inbox
        _handle_inbox(pdf, document_hash, short_hash, manifest, execute=execute, reg=reg, report=report)
        return

    # ── Other identified documents (new-style processors) ─────────────────
    if fy and quarter:
        period = f"{quarter} {fy}"
    elif fy:
        period = fy
    else:
        period = UNPERIODIZED_BUCKET

    source_type_slug = source_type.lower().replace("_", "_")
    dest_dir = processed_dir(company, period, source_type_slug)
    dest = safe_archive_path(dest_dir, pdf.name, short_hash)

    if execute:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pdf), str(dest))
        processor_name = _infer_processor_name(source_type)
        reg.bootstrap(
            document_hash=document_hash,
            filename=pdf.name,
            company=company,
            source_type=source_type_slug,
            fiscal_year=fy,
            quarter=quarter,
            processor_name=processor_name,
            artifact_paths=[],
            archived_path=str(dest),
            entity_scope=entity_scope,
        )
    report.bootstrapped_other += 1
    report.add({
        "file": pdf.name,
        "category": "BOOTSTRAPPED_OTHER",
        "hash": document_hash,
        "source_type": source_type_slug,
        "company": company,
        "period": period,
        "destination": str(dest),
        "execute": execute,
    })


def _handle_review(
    pdf: Path,
    document_hash: str,
    short_hash: str,
    execute: bool,
    reg: DocumentIntakeRegistry,
    report: MigrationReport,
    manifest=None,
) -> None:
    dest = safe_archive_path(REVIEW, pdf.name, short_hash)
    if execute:
        REVIEW.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pdf), str(dest))
        if reg.get(document_hash):
            reg.record_review_required(
                document_hash=document_hash,
                unresolved_fields=["Bootstrapped into REVIEW during migration"],
                new_path=str(dest),
            )
        else:
            _bootstrap_review(reg, document_hash, pdf.name, manifest, str(dest))
    report.sent_to_review += 1
    report.add({
        "file": pdf.name,
        "category": "REVIEW",
        "hash": document_hash,
        "destination": str(dest),
        "execute": execute,
    })


def _bootstrap_review(reg, document_hash, filename, manifest, archived_path):
    """Bootstrap a REVIEW record for a document with no prior registry entry."""
    from core.document_intake_registry import ProcessingStatus, WorkflowState
    records = reg._load()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    records[document_hash] = {
        "document_hash": document_hash,
        "observed_filenames": [filename],
        "current_path": archived_path,
        "workflow_state": WorkflowState.REVIEW.value,
        "company": None,
        "source_type": None,
        "source_channel": None,
        "fiscal_year": None,
        "quarter": None,
        "entity_scope": None,
        "identifier_version": "document_identifier.v4",
        "semantic_fingerprint": semantic_fingerprint(None, None, None, None, None),
        "processor_name": None,
        "processor_version": None,
        "schema_version": None,
        "processing_status": ProcessingStatus.REVIEW_REQUIRED.value,
        "processed_at": None,
        "artifact_paths": [],
        "evidence_count": 0,
        "warnings": ["Bootstrapped into REVIEW during migration"],
        "errors": [],
        "attempt_history": [],
        "registered_at": now,
        "last_updated_at": now,
    }
    reg._save(records)


def _handle_inbox(pdf, document_hash, short_hash, manifest, execute, reg, report):
    """Move unclassified document to Inbox."""
    dest = safe_archive_path(INBOX, pdf.name, short_hash)
    if execute:
        INBOX.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pdf), str(dest))
        reg.register_new(
            document_hash=document_hash,
            filename=pdf.name,
            manifest=manifest,
            initial_path=str(dest),
            workflow_state=WorkflowState.INBOX,
        )
    report.sent_to_inbox += 1
    report.add({
        "file": pdf.name,
        "category": "INBOX",
        "hash": document_hash,
        "destination": str(dest),
        "execute": execute,
    })


def _infer_processor_name(source_type: str) -> str:
    mapping = {
        "ANNUAL_REPORT":              "AnnualReportProcessor",
        "QUARTERLY_REPORT":           "QuarterlyReportProcessor",
        "INVESTOR_PRESENTATION":      "InvestorPresentationProcessor",
        "EARNINGS_CALL_TRANSCRIPT":   "EarningsCallTranscriptProcessor",
        "EARNINGS_RELEASE":           "EarningsReleaseProcessor",
        "EXCHANGE_DISCLOSURE":        "ExchangeDisclosureProcessor",
    }
    return mapping.get(source_type.upper(), "BOOTSTRAPPED")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate data/annual_reports/ into the canonical Inbox workflow."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually move files and write registry (default: dry run).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON row-level report to stdout.",
    )
    args = parser.parse_args()

    if not args.execute:
        print("[DRY RUN] Pass --execute to move files and write registry.\n")

    report = migrate(execute=args.execute)
    print(report.summary())

    if args.json:
        print(json.dumps({"rows": report.rows}, indent=2))


if __name__ == "__main__":
    _main()
