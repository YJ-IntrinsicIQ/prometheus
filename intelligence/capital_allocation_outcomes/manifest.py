from __future__ import annotations

from typing import Any, Dict, Iterable

from .contracts import ALLOCATION_OUTCOMES_GENERATOR_VERSION
from .paths import get_capital_allocation_outcomes_dir


def build_capital_allocation_manifest(
    *,
    company_slug: str,
    generated_at: str,
    upstream_sources_considered: Iterable[str],
    upstream_sources_found: Iterable[str],
    upstream_sources_missing: Iterable[str],
    allocation_candidates: int,
    allocations_written: int,
    duplicate_candidates_merged: int,
    timelines_written: int,
    assessments_written: int,
    validation_status: str,
    limitations: Iterable[str],
) -> Dict[str, Any]:
    return {
        "schema_version": "capital_allocation_outcomes_manifest.v1",
        "generator_version": ALLOCATION_OUTCOMES_GENERATOR_VERSION,
        "company_slug": company_slug,
        "generated_at": generated_at,
        "output_directory": str(get_capital_allocation_outcomes_dir(company_slug)),
        "upstream_sources_considered": list(upstream_sources_considered),
        "upstream_sources_found": list(upstream_sources_found),
        "upstream_sources_missing": list(upstream_sources_missing),
        "allocation_candidates": int(allocation_candidates),
        "allocations_written": int(allocations_written),
        "duplicate_candidates_merged": int(duplicate_candidates_merged),
        "timelines_written": int(timelines_written),
        "assessments_written": int(assessments_written),
        "validation_status": validation_status,
        "limitations": list(limitations),
    }

