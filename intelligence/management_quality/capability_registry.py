"""
Management Quality Answer Capability Registry — ENG-MISSION48

Canonical definition of required semantic capabilities for a management quality
answer to be considered complete for investor use. Used by capability_parity_validator.
"""
from __future__ import annotations

from typing import Dict, Any

CAPABILITY_REGISTRY_VERSION = "management_capability_registry.v1"

# Each capability: name → {required, description, field_in_answer, min_content, severity_if_missing}
REQUIRED_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "management.lifecycle_counts": {
        "required": True,
        "description": "Progression item counts by lifecycle state (delivered/in_progress/announced)",
        "field_in_answer": "deterministic_precision_facts (delivery DPF)",
        "min_content": "delivery count, in_progress count, announced count, total",
        "evidence_source": "management_progression.json",
        "severity_if_missing": "HIGH",
    },
    "management.hard_commitment_detail": {
        "required": True,
        "description": "Hard commitment count (specific-timeframe commitments) in DPF — not just total+UTV",
        "field_in_answer": "deterministic_precision_facts (commitments DPF)",
        "min_content": "hard commitment count when hard commitments exist in canonical data",
        "evidence_source": "management_commitments.json (items with specific expected_timeframe)",
        "severity_if_missing": "HIGH",
    },
    "management.evidence_observations": {
        "required": True,
        "description": "Observable outcomes and events (what_evidence_shows) — not only synthesis",
        "field_in_answer": "what_evidence_shows",
        "min_content": "2+ bullets referencing specific observable events",
        "evidence_source": "management_quality_evidence.json",
        "severity_if_missing": "HIGH",
    },
    "management.management_statements": {
        "required": True,
        "description": "Management's stated intentions and strategic commitments (what_management_says)",
        "field_in_answer": "what_management_says",
        "min_content": "1+ bullet paraphrasing management stated intentions",
        "evidence_source": "management_quality_evidence.json (commitment types)",
        "severity_if_missing": "HIGH",
    },
    "management.consistency_analysis": {
        "required": True,
        "description": "Structured consistency analysis per dimension (management_consistency_map + where_management_was_consistent)",
        "field_in_answer": "management_consistency_map, where_management_was_consistent",
        "min_content": "3+ dimension entries in map + 1+ consistency bullet",
        "evidence_source": "management_quality_dimensions.json",
        "severity_if_missing": "HIGH",
    },
    "management.economic_context": {
        "required": True,
        "description": "Economic interpretation with specific financial metric (what_may_mean_economically with NPM or margin)",
        "field_in_answer": "what_may_mean_economically",
        "min_content": "non-empty string with at least one specific financial metric",
        "evidence_source": "financial_truth_pack.json (NPM, revenue, PAT)",
        "severity_if_missing": "MEDIUM",
    },
    "management.uncertainty": {
        "required": True,
        "description": "Specific uncertainty map naming named commitments/risks (what_is_not_yet_proven)",
        "field_in_answer": "what_is_not_yet_proven",
        "min_content": "names at least one specific commitment, filing, or risk — not only abstract questions",
        "evidence_source": "management_quality_summary.json unresolved + hard_commitments from fact_pack_v2",
        "severity_if_missing": "HIGH",
    },
    "management.monitoring": {
        "required": True,
        "description": "Specific actionable monitoring items (what_to_monitor) — not bare category labels",
        "field_in_answer": "what_to_monitor",
        "min_content": "3+ items each >25 chars referencing specific metrics/products/filings",
        "evidence_source": "management_quality_summary.json what_to_watch + hard_commitments enrichment",
        "severity_if_missing": "MEDIUM",
    },
    "management.dpfs": {
        "required": True,
        "description": "Deterministic precision facts (>= 3 entries with metric/value/semantic_meaning)",
        "field_in_answer": "deterministic_precision_facts",
        "min_content": "3+ DPF entries; delivery DPF required",
        "evidence_source": "fact_pack_v2.dpfs",
        "severity_if_missing": "HIGH",
    },
    "management.behavioral_descriptor": {
        "required": True,
        "description": "Canonical behavioral descriptor verbatim in simple_answer",
        "field_in_answer": "simple_answer (verbatim text) or behavioral_descriptor field",
        "min_content": "one of the four canonical descriptor strings",
        "evidence_source": "fact_pack: derived from management_progression.json",
        "severity_if_missing": "HIGH",
    },
    "management.evidence_traceability": {
        "required": True,
        "description": "At least one path for investor to trace conclusion back to evidence",
        "field_in_answer": "claims[] with evidence_refs OR what_evidence_shows with named items",
        "min_content": "either 3+ claims with evidence_refs or 2+ what_evidence_shows items",
        "evidence_source": "management_quality_evidence.json",
        "severity_if_missing": "MEDIUM",
    },
}

CANONICAL_DESCRIPTOR_VALUES = {
    "FOLLOW_THROUGH_LARGELY_UNVERIFIED",
    "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS",
    "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS",
    "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED",
}
