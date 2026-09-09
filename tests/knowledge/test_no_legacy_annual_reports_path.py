"""Regression guard: no active runtime code may reference data/annual_reports.

This test fails when any Python source file outside the explicitly excluded list
introduces a new reference to the retired ``data/annual_reports`` directory,
preventing accidental re-introduction of legacy fallback paths.

Exclusions (intentional references that must remain):
- pipelines/migrate_annual_reports.py: legacy migration utility (retained for history)
- tests/: test files are audited separately; only runtime source is guarded here
- governance/: documentation, never executed at runtime
- .git/: VCS internals
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Files that are allowed to contain the retired path string
EXCLUSIONS = {
    "pipelines/migrate_annual_reports.py",   # historical migration utility
    "core/inbox_paths.py",                   # module-level docstring explains migration history
    "core/document_intake_registry.py",      # bootstrap() docstring mentions migration origin
    "governance/ATLAS.md",
    "governance/BACKLOG.md",
    "governance/SESSION_LOG.md",
    "governance/PROMETHEUS_INTELLIGENCE_MANIFESTO.md",
    "governance/archive/PIPELINES.md",
}

# Runtime source extensions to check
RUNTIME_EXTENSIONS = {".py"}

# Pattern to detect
PATTERN = re.compile(r"annual_reports")


def _runtime_files():
    """Yield all runtime Python source files, excluding tests and governance."""
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT)
        parts = rel.parts
        # Skip tests, governance, migrations, hidden dirs, __pycache__
        if parts[0] in ("tests", ".git", "__pycache__", "governance"):
            continue
        if any(p.startswith(".") or p == "__pycache__" for p in parts):
            continue
        if str(rel) in EXCLUSIONS:
            continue
        yield path


def test_no_annual_reports_in_runtime_sources():
    """No active runtime Python file may reference data/annual_reports."""
    violations = []
    for path in _runtime_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                rel = str(path.relative_to(REPO_ROOT))
                violations.append(f"{rel}:{lineno}: {line.strip()}")

    assert not violations, (
        "Runtime code contains references to the retired data/annual_reports/ directory.\n"
        "Remove the legacy fallback or add the file to EXCLUSIONS if it is intentional.\n\n"
        + "\n".join(violations)
    )
