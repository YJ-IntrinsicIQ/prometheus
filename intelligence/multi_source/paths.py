"""Phase 9 — File discovery across all 6 processor output families."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, List, Tuple


def _iter_period_dirs(company_root: Path, channel: str) -> Iterator[Tuple[str, Path]]:
    """Yield (period_label, artifact_dir) for a given sub-channel."""
    for period_dir in sorted(company_root.iterdir()):
        if not period_dir.is_dir():
            continue
        channel_dir = period_dir / channel
        if not channel_dir.is_dir():
            continue
        for artifact_dir in sorted(channel_dir.iterdir()):
            if artifact_dir.is_dir():
                yield period_dir.name, artifact_dir


def _undated_dir(company_root: Path, channel: str) -> Iterator[Tuple[str, Path]]:
    undated = company_root / "undated" / channel
    if undated.is_dir():
        for artifact_dir in sorted(undated.iterdir()):
            if artifact_dir.is_dir():
                yield "undated", artifact_dir


# ---------------------------------------------------------------------------
# Processor output discovery
# ---------------------------------------------------------------------------

def earnings_call_dirs(company_root: Path) -> List[Tuple[str, Path]]:
    return list(_iter_period_dirs(company_root, "earnings_calls"))


def presentation_dirs(company_root: Path) -> List[Tuple[str, Path]]:
    return list(_iter_period_dirs(company_root, "presentations"))


def earnings_release_dirs(company_root: Path) -> List[Tuple[str, Path]]:
    return list(_iter_period_dirs(company_root, "earnings_releases"))


def exchange_disclosure_dirs(company_root: Path) -> List[Tuple[str, Path]]:
    result = list(_iter_period_dirs(company_root, "exchange_disclosures"))
    result += list(_undated_dir(company_root, "exchange_disclosures"))
    return result


def quarterly_report_dirs(company_root: Path) -> List[Tuple[str, Path]]:
    """Yield (period_label, quarter_dir) for quarterly report outputs.

    Quarterly outputs live at fy*/quarters/Q*/ (no hash sub-directory).
    """
    results = []
    for period_dir in sorted(company_root.iterdir()):
        if not period_dir.is_dir():
            continue
        quarters_dir = period_dir / "quarters"
        if not quarters_dir.is_dir():
            continue
        for q_dir in sorted(quarters_dir.iterdir()):
            if q_dir.is_dir():
                label = f"{q_dir.name.lower()} {period_dir.name}"  # e.g. "q1 fy26"
                results.append((label, q_dir))
    return results


def annual_intelligence_dirs(company_root: Path) -> List[Tuple[str, Path]]:
    """Yield (period, intelligence_dir) for annual report intelligence."""
    results = []
    for period_dir in sorted(company_root.iterdir()):
        if not period_dir.is_dir():
            continue
        intel_dir = period_dir / "intelligence"
        if intel_dir.is_dir():
            results.append((period_dir.name, intel_dir))
    return results


def safe_json_load(path: Path):
    import json
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None
