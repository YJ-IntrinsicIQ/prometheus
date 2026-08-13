from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .contracts import MANAGEMENT_QUALITY_GENERATOR_VERSION
from .paths import get_management_quality_dir


def build_management_quality_manifest(
    *,
    company_slug: str,
    generated_at: str,
    source_files_considered: Iterable[str],
    source_files_found: Iterable[str],
    source_files_missing: Iterable[str],
    dimension_count: int,
    evidence_count: int,
    turning_point_count: int,
    overall_view: str,
    overall_direction: str,
    validation_status: str,
    limitations: Iterable[str],
) -> Dict[str, Any]:
    return {
        "schema_version": "management_quality_manifest.v1",
        "generator_version": MANAGEMENT_QUALITY_GENERATOR_VERSION,
        "company_slug": company_slug,
        "generated_at": generated_at,
        "output_directory": str(get_management_quality_dir(company_slug)),
        "source_files_considered": list(source_files_considered),
        "source_files_found": list(source_files_found),
        "source_files_missing": list(source_files_missing),
        "dimension_count": int(dimension_count),
        "evidence_count": int(evidence_count),
        "turning_point_count": int(turning_point_count),
        "overall_view": overall_view,
        "overall_direction": overall_direction,
        "validation_status": validation_status,
        "limitations": list(limitations),
    }

