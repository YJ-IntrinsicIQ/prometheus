"""Risk Evolution manifest generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .contracts import (
    RISK_GENERATOR_VERSION,
    RISK_MANIFEST_SCHEMA_VERSION,
)


def _utc_now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_risk_manifest(
    company_slug: str,
    risks: List[Dict[str, Any]],
    timelines: List[Dict[str, Any]],
    assessments: List[Dict[str, Any]],
    validation_report: Dict[str, Any],
    upstream_sources: Dict[str, Any],
    merge_log: List[tuple],
) -> Dict[str, Any]:
    """
    Build the risk evolution manifest.
    
    Records what was considered, what was produced, and key metrics.
    """
    
    # Count statuses
    status_counts = {}
    for risk in risks:
        status = risk.get("current_status", "unable_to_verify")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Count materiality levels
    materiality_counts = {"high": 0, "medium": 0, "low": 0, "unclear": 0}
    for risk in risks:
        level = risk.get("materiality", {}).get("level", "unclear")
        if level in materiality_counts:
            materiality_counts[level] += 1
    
    # Count commitment/project/capacity links
    commitment_links = sum(len(r.get("related_commitment_ids", [])) for r in risks)
    project_links = sum(len(r.get("related_project_ids", [])) for r in risks)
    capacity_links = sum(len(r.get("related_capacity_ids", [])) for r in risks)
    
    # Identify turning points
    turning_points = []
    for timeline in timelines:
        tp_list = timeline.get("turning_points", [])
        turning_points.extend(tp_list)
    
    # Identify unresolved risks
    unresolved_risks = [r for r in risks if r.get("current_status") in ["unable_to_verify", "contradictory"]]
    
    # Count high materiality
    high_materiality_risks = [r for r in risks if r.get("materiality", {}).get("level") == "high"]
    
    # Build upstream status
    upstream_sources_found = []
    upstream_sources_missing = []
    
    for source_name, source_info in upstream_sources.items():
        if source_info.get("found"):
            upstream_sources_found.append(source_name)
        else:
            upstream_sources_missing.append(source_name)
    
    return {
        "schema_version": RISK_MANIFEST_SCHEMA_VERSION,
        "generator_version": RISK_GENERATOR_VERSION,
        "company_slug": company_slug,
        "generated_at": _utc_now(),
        "upstream_sources_considered": list(upstream_sources.keys()),
        "upstream_sources_found": upstream_sources_found,
        "upstream_sources_missing": upstream_sources_missing,
        "risk_candidates": {
            "identified": len(risks),
            "after_deduplication": len(risks),
            "duplicate_candidates_merged": len(merge_log),
        },
        "risks_written": len(risks),
        "risks_by_status": status_counts,
        "risks_by_materiality": materiality_counts,
        "high_materiality_risks": len(high_materiality_risks),
        "emerging_risks": status_counts.get("emerging", 0),
        "increasing_risks": status_counts.get("increasing", 0),
        "persistent_risks": status_counts.get("persistent", 0),
        "reducing_risks": status_counts.get("reducing", 0),
        "mitigated_risks": status_counts.get("mitigated", 0),
        "resolved_risks": status_counts.get("resolved", 0),
        "unable_to_verify_risks": status_counts.get("unable_to_verify", 0),
        "commitment_links": commitment_links,
        "project_links": project_links,
        "capacity_links": capacity_links,
        "financial_metric_links": sum(len(r.get("related_financial_metrics", [])) for r in risks),
        "timelines_written": len(timelines),
        "turning_points_detected": len(turning_points),
        "unresolved_risks": len(unresolved_risks),
        "validation_status": validation_report.get("status", "unknown"),
        "validation_errors": validation_report.get("error_count", 0),
        "validation_warnings": validation_report.get("warning_count", 0),
        "limitations": [
            "Risks are identified only from existing company memory artifacts (yearly intelligence, financial data, management commitments, projects, capacity)",
            "Generic risk-factor boilerplate is excluded in favor of company-specific evidence",
            "Absence of mention in later years is not treated as resolution without explicit evidence",
            "Mitigation requires observable evidence; management reassurance alone is insufficient",
            "Risk severity (impact * likelihood) is not calculated; instead materiality assesses business-area importance and evidence quality",
            "Some risks may remain unable-to-verify due to gaps in upstream source coverage",
        ],
    }
