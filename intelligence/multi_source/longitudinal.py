"""Phase 9 — Top-level longitudinal builder.

Entry point: build(company, companies_root, output_dir)

Produces companies/<company>/longitudinal/longitudinal_report.json
and writes a manifest for downstream consumers (CIM, Panel, Ask layer).
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from intelligence.multi_source.aggregator import aggregate
from intelligence.multi_source.contracts import LongitudinalReport
from intelligence.multi_source.lifecycle import resolve_commitments


# ---------------------------------------------------------------------------
# Stop conditions (Part 30 — pre-production safety gates)
# ---------------------------------------------------------------------------

_MIN_SOURCE_FAMILIES = 2          # need at least 2 different source families
_MIN_TOTAL_EVIDENCE  = 5          # need at least 5 evidence atoms
_MIN_COMMITMENTS     = 1          # need at least 1 commitment thread


def _check_stop_conditions(report: LongitudinalReport) -> list[str]:
    stops = []
    n_families = len(report.source_families_present)
    n_evidence = sum(len(c.evidence) for c in report.commitments)
    n_commitments = report.commitment_count

    if n_families < _MIN_SOURCE_FAMILIES:
        stops.append(
            f"PARTIAL_COMMON_EVIDENCE_INSUFFICIENT: only {n_families} source "
            f"famil{'y' if n_families == 1 else 'ies'} present (need ≥ {_MIN_SOURCE_FAMILIES})."
        )
    if n_evidence < _MIN_TOTAL_EVIDENCE:
        stops.append(
            f"PARTIAL_LONGITUDINAL_IDENTITY_UNSAFE: only {n_evidence} evidence "
            f"atoms (need ≥ {_MIN_TOTAL_EVIDENCE})."
        )
    if n_commitments < _MIN_COMMITMENTS:
        stops.append(
            f"PARTIAL_PRODUCTION_COVERAGE_INSUFFICIENT: {n_commitments} commitment "
            f"thread(s) resolved (need ≥ {_MIN_COMMITMENTS})."
        )
    return stops


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build(
    company: str,
    companies_root: Path,
    output_dir: Optional[Path] = None,
    execute: bool = True,
) -> LongitudinalReport:
    """Aggregate all processor outputs and produce the longitudinal report.

    Args:
        company:        Slug (e.g. "tanla").
        companies_root: Root of the companies/ directory.
        output_dir:     Where to write output (default: companies/<company>/longitudinal/).
        execute:        If False, build the report but do not write files.

    Returns:
        LongitudinalReport dataclass.
    """
    company_root = companies_root / company
    if not company_root.is_dir():
        raise FileNotFoundError(f"Company directory not found: {company_root}")

    # Aggregate all evidence
    evidence = aggregate(company, company_root)

    # Resolve lifecycle
    commitments = resolve_commitments(evidence)

    # Tally metadata
    source_periods = sorted({e.source_period for e in evidence if e.source_period})
    source_families = sorted({e.source_type for e in evidence})
    lifecycle_counts = Counter(c.lifecycle.value for c in commitments)

    report = LongitudinalReport(
        company=company,
        generated_at=datetime.utcnow().isoformat() + "Z",
        source_periods=source_periods,
        source_families_present=source_families,
        commitment_count=len(commitments),
        lifecycle_counts=dict(lifecycle_counts),
        commitments=commitments,
    )

    # Check stop conditions
    report.stop_conditions = _check_stop_conditions(report)

    # Write output
    if execute:
        out_dir = output_dir or (company_root / "longitudinal")
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_report(report, out_dir)

    return report


def _write_report(report: LongitudinalReport, out_dir: Path) -> None:
    report_path = out_dir / "longitudinal_report.json"
    with open(report_path, "w") as fh:
        json.dump(report.to_dict(), fh, indent=2, ensure_ascii=False)

    manifest = {
        "schema_version": "9.0",
        "company": report.company,
        "generated_at": report.generated_at,
        "report_path": str(report_path),
        "commitment_count": report.commitment_count,
        "lifecycle_counts": report.lifecycle_counts,
        "source_families_present": report.source_families_present,
        "stop_conditions": report.stop_conditions,
        "status": "MULTI_SOURCE_LONGITUDINAL_INTEGRATION_CLOSED" if not report.stop_conditions else "PARTIAL",
    }
    with open(out_dir / "longitudinal_manifest.json", "w") as fh:
        json.dump(manifest, fh, indent=2)
