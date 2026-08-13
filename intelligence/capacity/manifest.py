from __future__ import annotations

from typing import Any, Dict, Iterable

from intelligence.progression.manifest import PROGRESSION_ENGINE_VERSION

from .contracts import CAPACITY_GENERATOR_VERSION
from .paths import get_capacity_dir


def build_capacity_manifest(
    *,
    company_slug: str,
    generated_at: str,
    upstream_sources_considered: Iterable[str],
    upstream_sources_found: Iterable[str],
    upstream_sources_missing: Iterable[str],
    capacity_candidates: int,
    capacity_items_written: int,
    duplicate_candidates_merged: int,
    project_links: Iterable[str] | Dict[str, Any],
    commitment_links: Iterable[str] | Dict[str, Any],
    timelines_written: int,
    turning_points_detected: int,
    unresolved_items: int,
    validation_status: str,
    limitations: Iterable[str],
) -> Dict[str, Any]:
    return {
        "schema_version": "capacity_manifest.v1",
        "generator_version": CAPACITY_GENERATOR_VERSION,
        "progression_engine_version": PROGRESSION_ENGINE_VERSION,
        "company_slug": company_slug,
        "generated_at": generated_at,
        "output_directory": str(get_capacity_dir(company_slug)),
        "upstream_sources_considered": list(upstream_sources_considered),
        "upstream_sources_found": list(upstream_sources_found),
        "upstream_sources_missing": list(upstream_sources_missing),
        "capacity_candidates": int(capacity_candidates),
        "capacity_items_written": int(capacity_items_written),
        "duplicate_candidates_merged": int(duplicate_candidates_merged),
        "project_links": project_links,
        "commitment_links": commitment_links,
        "timelines_written": int(timelines_written),
        "turning_points_detected": int(turning_points_detected),
        "unresolved_items": int(unresolved_items),
        "validation_status": validation_status,
        "limitations": list(limitations),
    }
