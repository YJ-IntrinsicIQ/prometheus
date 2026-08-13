from __future__ import annotations

MANAGEMENT_QUALITY_SCHEMA_VERSION = "management_quality.v1"
MANAGEMENT_QUALITY_MANIFEST_SCHEMA_VERSION = "management_quality_manifest.v1"
MANAGEMENT_QUALITY_GENERATOR_VERSION = "management_quality_builder.v1"

MANAGEMENT_QUALITY_DIMENSIONS = (
    "execution_discipline",
    "capital_allocation_discipline",
    "candor_and_consistency",
    "strategic_clarity",
    "risk_handling",
    "owner_alignment",
    "adaptability",
    "evidence_confidence",
)

MANAGEMENT_QUALITY_ASSESSMENTS = (
    "strong",
    "reasonably_strong",
    "mixed",
    "weak",
    "insufficient_evidence",
)

EVIDENCE_CONFIDENCE_LEVELS = (
    "high",
    "medium",
    "low",
    "insufficient",
)

DIRECTION_VALUES = (
    "improving",
    "stable",
    "deteriorating",
    "mixed",
    "unclear",
)

SOURCE_STREAMS = (
    "management_commitments",
    "projects",
    "capacity",
    "risks",
    "management_commentary",
    "capital_allocation_outcomes",
    "financial_truth",
    "owner_earnings",
    "per_share_compounding",
    "investor_panel",
)

SUMMARY_CONVICTION_FIELDS = (
    "what_strengthened_conviction",
    "what_weakened_conviction",
    "what_remains_unproven",
)

