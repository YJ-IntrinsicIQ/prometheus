"""Global processing registry for Prometheus document intake.

Single canonical registry — one JSON file, lookup by SHA-256.

Three identities kept explicitly separate
-----------------------------------------
1. Content identity   SHA-256 of the raw file bytes (never changes).
2. Semantic identity  What Prometheus believes this document IS: company,
                      source_type, fiscal_year, quarter, entity_scope.
                      Captured as a deterministic ``semantic_fingerprint``.
3. Processing compat  Whether existing output is reusable under the CURRENT
                      processor name + version + schema/output version.

Reuse is only safe when ALL three match.  If the classifier later changes its
mind about a document's identity (same SHA, different fingerprint), the
previous output becomes STALE and must be reprocessed.

Processing decisions
--------------------
PROCESS_NEW         SHA not in registry — process for the first time.
REUSE_EXISTING      Identical SHA, fingerprint, processor/schema versions,
                    SUCCESS status, and artifacts present.
REPROCESS_STALE     SHA known, but fingerprint changed, versions changed,
                    or required artifacts are missing.
RETRY_FAILED        Previous attempt recorded as FAILED.
BLOCK_REVIEW_REQUIRED  Document requires operator review; never auto-process.

File movement contract
----------------------
The registry is authoritative.  Filesystem location reflects workflow state.
A document in PROCESSED may be reprocessed in-place — it does NOT need to
return to Inbox for technical reprocessing (Inbox = operator-supplied work).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.inbox_paths import (
    REGISTRY_FILE,
    UNPERIODIZED_BUCKET,
    processed_dir,
    safe_archive_path,
)


# ---------------------------------------------------------------------------
# Processor / schema versions
# (Increment these when a processor's output format changes incompatibly.)
# ---------------------------------------------------------------------------

PROCESSOR_VERSIONS: Dict[str, str] = {
    "AnnualReportProcessor": "1.0",
    "QuarterlyReportProcessor": "1.0",
    "InvestorPresentationProcessor": "1.0",
    "EarningsCallTranscriptProcessor": "1.0",
    "EarningsReleaseProcessor": "1.0",
    "ExchangeDisclosureProcessor": "1.0",
    "BOOTSTRAPPED": "1.0",
}

SCHEMA_VERSIONS: Dict[str, str] = {
    "AnnualReportProcessor": "1.0",
    "QuarterlyReportProcessor": "1.0",
    "InvestorPresentationProcessor": "1.0",
    "EarningsCallTranscriptProcessor": "1.0",
    "EarningsReleaseProcessor": "1.0",
    "ExchangeDisclosureProcessor": "1.0",
    "BOOTSTRAPPED": "1.0",
}

# Identifier (classifier) version — bump when classify logic changes
IDENTIFIER_VERSION: str = "document_identifier.v4"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProcessingDecision(str, Enum):
    PROCESS_NEW = "PROCESS_NEW"
    REUSE_EXISTING = "REUSE_EXISTING"
    REPROCESS_STALE = "REPROCESS_STALE"
    RETRY_FAILED = "RETRY_FAILED"
    BLOCK_REVIEW_REQUIRED = "BLOCK_REVIEW_REQUIRED"


class WorkflowState(str, Enum):
    INBOX = "INBOX"
    PROCESSED = "PROCESSED"
    REVIEW = "REVIEW"
    FAILED = "FAILED"
    BOOTSTRAPPED = "BOOTSTRAPPED"    # migrated from pre-registry era


class ProcessingStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    STALE = "STALE"
    PENDING = "PENDING"
    BOOTSTRAPPED = "BOOTSTRAPPED"


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class ProcessingAttempt:
    attempted_at: str
    status: str         # ProcessingStatus value
    processor_name: str
    processor_version: str
    error: Optional[str] = None


@dataclass
class DocumentIntakeRecord:
    """Canonical registry record for one unique document (keyed by SHA-256)."""

    document_hash: str                  # full sha256:...
    observed_filenames: List[str]       # all filenames ever seen for this hash
    current_path: Optional[str]         # current filesystem location
    workflow_state: str                 # WorkflowState value

    # Semantic identity
    company: Optional[str]
    source_type: Optional[str]
    source_channel: Optional[str]
    fiscal_year: Optional[str]
    quarter: Optional[str]
    entity_scope: Optional[str]

    # Identity provenance
    identifier_version: str
    semantic_fingerprint: str           # deterministic hash of semantic fields

    # Processing provenance
    processor_name: Optional[str]
    processor_version: Optional[str]
    schema_version: Optional[str]
    processing_status: str              # ProcessingStatus value
    processed_at: Optional[str]

    # Output provenance
    artifact_paths: List[str]
    evidence_count: int
    warnings: List[str]
    errors: List[str]

    # Attempt history (oldest first)
    attempt_history: List[dict]

    # Registry metadata
    registered_at: str
    last_updated_at: str


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------

def semantic_fingerprint(
    company: Optional[str],
    source_type: Optional[str],
    fiscal_year: Optional[str],
    quarter: Optional[str],
    entity_scope: Optional[str],
) -> str:
    """Deterministic 16-hex fingerprint of the key identity fields.

    If the classifier later reinterprets any of these fields for the same
    SHA-256, the fingerprint changes and existing output becomes STALE.
    """
    parts = [
        (company or "").lower().strip(),
        (source_type or "").upper().strip(),
        (fiscal_year or "").lower().strip(),
        (quarter or "").lower().strip(),
        (entity_scope or "").lower().strip(),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def fingerprint_from_manifest(manifest: Any) -> str:
    """Extract semantic fingerprint from a DocumentIntakeManifest."""
    company = getattr(getattr(manifest, "company_identity", None), "resolved_company_key", None)
    st_obj = getattr(getattr(manifest, "document_identity", None), "source_type", None)
    source_type = st_obj.value if st_obj else None
    rp = getattr(manifest, "reporting_period", None)
    fiscal_year = getattr(rp, "fiscal_year", None) if rp else None
    fq_obj = getattr(rp, "fiscal_quarter", None) if rp else None
    quarter = fq_obj.value if fq_obj else None
    es_obj = getattr(manifest, "entity_scope", None)
    entity_scope = es_obj.value if es_obj else None
    return semantic_fingerprint(company, source_type, fiscal_year, quarter, entity_scope)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class DocumentIntakeRegistry:
    """Persistent global processing registry backed by a single JSON file.

    All lookups are by full SHA-256 (``sha256:...``).  The registry is
    loaded fresh on each operation to remain safe under concurrent use from
    separate processes (no in-process caching that could go stale).
    """

    def __init__(self, registry_file: Optional[Path] = None) -> None:
        self._path = Path(registry_file) if registry_file else REGISTRY_FILE

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> Dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, records: Dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(records, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        tmp.replace(self._path)   # atomic rename

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, document_hash: str) -> Optional[dict]:
        """Return the registry record for *document_hash*, or None."""
        return self._load().get(document_hash)

    def get_all(self) -> Dict[str, dict]:
        return self._load()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def register_new(
        self,
        document_hash: str,
        filename: str,
        manifest: Any,
        initial_path: str,
        workflow_state: WorkflowState = WorkflowState.INBOX,
    ) -> dict:
        """Create a new registry record for a previously-unseen document."""
        records = self._load()
        now = self._now()

        company = getattr(getattr(manifest, "company_identity", None), "resolved_company_key", None)
        st_obj = getattr(getattr(manifest, "document_identity", None), "source_type", None)
        source_type = st_obj.value if st_obj else None
        sc_obj = getattr(getattr(manifest, "document_identity", None), "source_channel", None)
        source_channel = sc_obj.value if sc_obj else None
        rp = getattr(manifest, "reporting_period", None)
        fiscal_year = getattr(rp, "fiscal_year", None) if rp else None
        fq_obj = getattr(rp, "fiscal_quarter", None) if rp else None
        quarter = fq_obj.value if fq_obj else None
        es_obj = getattr(manifest, "entity_scope", None)
        entity_scope = es_obj.value if es_obj else None

        fp = semantic_fingerprint(company, source_type, fiscal_year, quarter, entity_scope)

        record = {
            "document_hash": document_hash,
            "observed_filenames": [filename],
            "current_path": initial_path,
            "workflow_state": workflow_state.value,
            "company": company,
            "source_type": source_type,
            "source_channel": source_channel,
            "fiscal_year": fiscal_year,
            "quarter": quarter,
            "entity_scope": entity_scope,
            "identifier_version": IDENTIFIER_VERSION,
            "semantic_fingerprint": fp,
            "processor_name": None,
            "processor_version": None,
            "schema_version": None,
            "processing_status": ProcessingStatus.PENDING.value,
            "processed_at": None,
            "artifact_paths": [],
            "evidence_count": 0,
            "warnings": [],
            "errors": [],
            "attempt_history": [],
            "registered_at": now,
            "last_updated_at": now,
        }
        records[document_hash] = record
        self._save(records)
        return record

    def add_filename_alias(self, document_hash: str, filename: str) -> None:
        """Record an additional filename observed for an existing hash."""
        records = self._load()
        if document_hash not in records:
            return
        r = records[document_hash]
        if filename not in r["observed_filenames"]:
            r["observed_filenames"].append(filename)
        r["last_updated_at"] = self._now()
        self._save(records)

    def record_success(
        self,
        document_hash: str,
        processor_name: str,
        artifact_paths: List[str],
        evidence_count: int,
        new_path: str,
        warnings: Optional[List[str]] = None,
    ) -> None:
        """Mark a document as successfully processed and update its archive path."""
        records = self._load()
        r = records[document_hash]
        now = self._now()
        attempt = ProcessingAttempt(
            attempted_at=now,
            status=ProcessingStatus.SUCCESS.value,
            processor_name=processor_name,
            processor_version=PROCESSOR_VERSIONS.get(processor_name, "1.0"),
            error=None,
        )
        r["processing_status"] = ProcessingStatus.SUCCESS.value
        r["processor_name"] = processor_name
        r["processor_version"] = PROCESSOR_VERSIONS.get(processor_name, "1.0")
        r["schema_version"] = SCHEMA_VERSIONS.get(processor_name, "1.0")
        r["processed_at"] = now
        r["artifact_paths"] = list(artifact_paths)
        r["evidence_count"] = evidence_count
        r["warnings"] = list(warnings or [])
        r["errors"] = []
        r["workflow_state"] = WorkflowState.PROCESSED.value
        r["current_path"] = new_path
        r["attempt_history"].append(asdict(attempt))
        r["last_updated_at"] = now
        self._save(records)

    def record_failure(
        self,
        document_hash: str,
        processor_name: str,
        error: str,
        new_path: str,
    ) -> None:
        """Mark a document as failed and move it to the FAILED workflow state."""
        records = self._load()
        r = records[document_hash]
        now = self._now()
        attempt = ProcessingAttempt(
            attempted_at=now,
            status=ProcessingStatus.FAILED.value,
            processor_name=processor_name,
            processor_version=PROCESSOR_VERSIONS.get(processor_name, "1.0"),
            error=error,
        )
        r["processing_status"] = ProcessingStatus.FAILED.value
        r["workflow_state"] = WorkflowState.FAILED.value
        r["current_path"] = new_path
        r["errors"].append(error)
        r["attempt_history"].append(asdict(attempt))
        r["last_updated_at"] = now
        self._save(records)

    def record_review_required(
        self,
        document_hash: str,
        unresolved_fields: List[str],
        new_path: str,
    ) -> None:
        """Mark a document as requiring operator review."""
        records = self._load()
        r = records[document_hash]
        now = self._now()
        r["processing_status"] = ProcessingStatus.REVIEW_REQUIRED.value
        r["workflow_state"] = WorkflowState.REVIEW.value
        r["current_path"] = new_path
        r["warnings"].extend(unresolved_fields)
        r["last_updated_at"] = now
        self._save(records)

    def mark_stale(self, document_hash: str) -> None:
        """Explicitly mark existing output as stale (e.g. after processor upgrade)."""
        records = self._load()
        if document_hash not in records:
            return
        r = records[document_hash]
        r["processing_status"] = ProcessingStatus.STALE.value
        r["last_updated_at"] = self._now()
        self._save(records)

    def bootstrap(
        self,
        document_hash: str,
        filename: str,
        company: str,
        source_type: str,
        fiscal_year: Optional[str],
        quarter: Optional[str],
        processor_name: str,
        artifact_paths: List[str],
        archived_path: str,
        source_channel: str = "DIRECT",
        entity_scope: Optional[str] = None,
    ) -> dict:
        """Bootstrap a pre-registry document (migrated from old data/annual_reports).

        Only used during one-time migration.  Marks workflow_state=BOOTSTRAPPED
        and processing_status=BOOTSTRAPPED so the reuse checker can trust it
        but callers can distinguish bootstrapped from freshly-processed records.
        """
        records = self._load()
        now = self._now()
        fp = semantic_fingerprint(company, source_type, fiscal_year, quarter, entity_scope)
        attempt = asdict(ProcessingAttempt(
            attempted_at=now,
            status=ProcessingStatus.BOOTSTRAPPED.value,
            processor_name=processor_name,
            processor_version=PROCESSOR_VERSIONS.get(processor_name, "1.0"),
            error=None,
        ))
        record = {
            "document_hash": document_hash,
            "observed_filenames": [filename],
            "current_path": archived_path,
            "workflow_state": WorkflowState.BOOTSTRAPPED.value,
            "company": company,
            "source_type": source_type,
            "source_channel": source_channel,
            "fiscal_year": fiscal_year,
            "quarter": quarter,
            "entity_scope": entity_scope,
            "identifier_version": IDENTIFIER_VERSION,
            "semantic_fingerprint": fp,
            "processor_name": processor_name,
            "processor_version": PROCESSOR_VERSIONS.get(processor_name, "1.0"),
            "schema_version": SCHEMA_VERSIONS.get(processor_name, "1.0"),
            "processing_status": ProcessingStatus.BOOTSTRAPPED.value,
            "processed_at": now,
            "artifact_paths": list(artifact_paths),
            "evidence_count": 0,
            "warnings": [],
            "errors": [],
            "attempt_history": [attempt],
            "registered_at": now,
            "last_updated_at": now,
        }
        records[document_hash] = record
        self._save(records)
        return record


# ---------------------------------------------------------------------------
# Processing decision
# ---------------------------------------------------------------------------

def _artifacts_present(artifact_paths: List[str]) -> bool:
    """Lightweight check: all recorded artifact paths still exist."""
    if not artifact_paths:
        return False
    return all(Path(p).exists() for p in artifact_paths)


def _versions_compatible(record: dict, processor_name: str) -> bool:
    """Return True when record's processor/schema versions match current."""
    current_pv = PROCESSOR_VERSIONS.get(processor_name, "1.0")
    current_sv = SCHEMA_VERSIONS.get(processor_name, "1.0")
    return (
        record.get("processor_version") == current_pv
        and record.get("schema_version") == current_sv
    )


def decide_processing_action(
    document_hash: str,
    manifest: Any,
    processor_name: Optional[str],
    registry: DocumentIntakeRegistry,
    force: bool = False,
) -> ProcessingDecision:
    """Return the canonical processing decision for a document.

    Args:
        document_hash:  Full ``sha256:...`` hash of the file.
        manifest:       Resolved ``DocumentIntakeManifest`` (may be None for
                        REVIEW_REQUIRED decisions before manifests are valid).
        processor_name: Name of the processor that would handle this doc, or
                        None for REVIEW_REQUIRED documents.
        registry:       The live registry instance.
        force:          If True, always returns REPROCESS_STALE even when
                        REUSE_EXISTING would otherwise apply.

    Returns:
        One of the five ``ProcessingDecision`` values.
    """
    record = registry.get(document_hash)

    if record is None:
        return ProcessingDecision.PROCESS_NEW

    if force:
        return ProcessingDecision.REPROCESS_STALE

    status = record.get("processing_status")
    workflow = record.get("workflow_state")

    if status == ProcessingStatus.REVIEW_REQUIRED.value:
        return ProcessingDecision.BLOCK_REVIEW_REQUIRED

    if workflow == WorkflowState.REVIEW.value:
        return ProcessingDecision.BLOCK_REVIEW_REQUIRED

    if status == ProcessingStatus.FAILED.value:
        return ProcessingDecision.RETRY_FAILED

    # For reuse: check fingerprint, versions, artifacts
    if status in (ProcessingStatus.SUCCESS.value, ProcessingStatus.BOOTSTRAPPED.value):
        if manifest is not None:
            current_fp = fingerprint_from_manifest(manifest)
            stored_fp = record.get("semantic_fingerprint", "")
            if current_fp != stored_fp:
                return ProcessingDecision.REPROCESS_STALE

        pname = processor_name or record.get("processor_name") or ""
        if not _versions_compatible(record, pname):
            return ProcessingDecision.REPROCESS_STALE

        art_paths = record.get("artifact_paths", [])
        if not _artifacts_present(art_paths):
            return ProcessingDecision.REPROCESS_STALE

        return ProcessingDecision.REUSE_EXISTING

    if status == ProcessingStatus.STALE.value:
        return ProcessingDecision.REPROCESS_STALE

    # PENDING or unknown
    return ProcessingDecision.PROCESS_NEW
