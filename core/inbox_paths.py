"""Canonical path constants for the Prometheus document Inbox lifecycle.

All code that needs to reference document workflow directories must import
from here.  Do NOT scatter literal path strings like ``data/Inbox`` or
``data/annual_reports`` through the codebase.

Directory semantics
-------------------
INBOX      New documents supplied by the operator.  Everything starts here.
PROCESSED  Successfully processed originals, archived by company/period/type.
REVIEW     Documents Prometheus cannot safely auto-process (REVIEW_REQUIRED).
FAILED     Documents where processing was attempted and failed.

The original source PDF moves only AFTER processing state is known:
  SUCCESS          → PROCESSED / <company> / <period> / <source_type> /
  REVIEW_REQUIRED  → REVIEW /
  FAILED           → FAILED /

Registry truth
--------------
The registry (``core/document_intake_registry.py``) is authoritative.
Filesystem location is workflow state only — never document identity.
Content identity is SHA-256.  Semantic identity is the manifest fingerprint.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Repository root
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Canonical workflow directories
# ---------------------------------------------------------------------------

INBOX: Path = _REPO_ROOT / "data" / "Inbox"
PROCESSED: Path = _REPO_ROOT / "data" / "Processed"
REVIEW: Path = _REPO_ROOT / "data" / "Review"
FAILED: Path = _REPO_ROOT / "data" / "Failed"

# Global processing registry file — hidden file in data/
REGISTRY_FILE: Path = _REPO_ROOT / "data" / ".document_registry.json"

# Canonical bucket for documents with no safely-known fiscal period
UNPERIODIZED_BUCKET: str = "unperiodized"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_workflow_dirs() -> None:
    """Create all workflow directories if they don't exist yet."""
    for d in (INBOX, PROCESSED, REVIEW, FAILED):
        d.mkdir(parents=True, exist_ok=True)


def processed_dir(company: str, period: str, source_type: str) -> Path:
    """Return the canonical Processed sub-directory for a document.

    Args:
        company:     Resolved company key (e.g. ``"tanla"``).
        period:      Fiscal period (e.g. ``"fy26"``, ``"q1 fy26"``) or
                     ``UNPERIODIZED_BUCKET`` when no period is safely known.
        source_type: Source type slug (e.g. ``"annual_report"``).
    """
    return PROCESSED / company / period / source_type


def safe_archive_path(dest_dir: Path, filename: str, content_hash_short: str) -> Path:
    """Return a collision-safe destination path.

    If ``dest_dir / filename`` already exists (different document, same name),
    appends a short content-hash suffix before the extension so we never
    silently overwrite.  Filename has no identity authority.
    """
    candidate = dest_dir / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    return dest_dir / f"{stem}__{content_hash_short}{suffix}"
