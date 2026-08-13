from __future__ import annotations

from typing import Any, Dict, Iterable, List

from intelligence.progression import build_progression_manifest

from .contracts import COMMENTARY_MANIFEST_SCHEMA_VERSION, COMMENTARY_GENERATOR_VERSION, COMMENTARY_SCHEMA_VERSION


def build_commentary_manifest(
    *,
    company_slug: str,
    generated_at: str,
    upstream_sources_considered: Iterable[str],
    upstream_sources_found: Iterable[str],
    upstream_sources_missing: Iterable[str],
    theme_count: int,
    timeline_count: int,
    assessment_count: int,
    validation_status: str,
    limitations: List[str],
    position_counts: Dict[str, int],
    theme_category_counts: Dict[str, int],
) -> Dict[str, Any]:
    manifest = build_progression_manifest(
        company_slug=company_slug,
        generated_at=generated_at,
        progression_engine_version="progression_engine.v1",
        progression_contract_version="progression_contract.v1",
        events_processed=theme_count,
        transitions_detected=timeline_count,
        turning_points_detected=assessment_count,
        unresolved_items=len(limitations),
        outputs_written=[
            "commentary_themes.json",
            "commentary_timelines.json",
            "commentary_assessments.json",
            "commentary_validation.json",
            "commentary_manifest.json",
        ],
        validation_status=validation_status,
        limitations=limitations,
    )
    manifest["manifest_schema_version"] = COMMENTARY_MANIFEST_SCHEMA_VERSION
    manifest["generator_version"] = COMMENTARY_GENERATOR_VERSION
    manifest["schema_version"] = COMMENTARY_SCHEMA_VERSION
    manifest["upstream_sources_considered"] = list(upstream_sources_considered)
    manifest["upstream_sources_found"] = list(upstream_sources_found)
    manifest["upstream_sources_missing"] = list(upstream_sources_missing)
    manifest["theme_count"] = int(theme_count)
    manifest["timeline_count"] = int(timeline_count)
    manifest["assessment_count"] = int(assessment_count)
    manifest["position_counts"] = dict(position_counts)
    manifest["theme_category_counts"] = dict(theme_category_counts)
    return manifest
