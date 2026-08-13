from __future__ import annotations

from typing import Any, Dict, Iterable

from .contracts import PROJECTS_GENERATOR_VERSION
from .paths import get_projects_dir


def build_projects_manifest(
    *,
    company_slug: str,
    generated_at: str,
    upstream_sources_considered: Iterable[str],
    upstream_sources_found: Iterable[str],
    upstream_sources_missing: Iterable[str],
    project_candidates: int,
    projects_written: int,
    duplicate_candidates_merged: int,
    timelines_written: int,
    turning_points_detected: int,
    unresolved_projects: int,
    validation_status: str,
    limitations: Iterable[str],
) -> Dict[str, Any]:
    return {
        "schema_version": "projects_manifest.v1",
        "generator_version": PROJECTS_GENERATOR_VERSION,
        "company_slug": company_slug,
        "generated_at": generated_at,
        "output_directory": str(get_projects_dir(company_slug)),
        "upstream_sources_considered": list(upstream_sources_considered),
        "upstream_sources_found": list(upstream_sources_found),
        "upstream_sources_missing": list(upstream_sources_missing),
        "project_candidates": int(project_candidates),
        "projects_written": int(projects_written),
        "duplicate_candidates_merged": int(duplicate_candidates_merged),
        "timelines_written": int(timelines_written),
        "turning_points_detected": int(turning_points_detected),
        "unresolved_projects": int(unresolved_projects),
        "validation_status": validation_status,
        "limitations": list(limitations),
    }

