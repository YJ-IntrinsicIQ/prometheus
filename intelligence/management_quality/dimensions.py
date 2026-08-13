from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence

from .contracts import (
    DIRECTION_VALUES,
    EVIDENCE_CONFIDENCE_LEVELS,
    MANAGEMENT_QUALITY_ASSESSMENTS,
    MANAGEMENT_QUALITY_DIMENSIONS,
)


DIMENSION_SOURCE_STREAMS = {
    "execution_discipline": ("management_commitments", "projects", "capacity"),
    "capital_allocation_discipline": ("capital_allocation_outcomes", "owner_earnings", "per_share_compounding"),
    "candor_and_consistency": ("management_commentary", "management_commitments", "risks"),
    "strategic_clarity": ("management_commentary", "management_commitments", "projects", "capacity"),
    "risk_handling": ("risks", "management_commentary", "management_commitments"),
    "owner_alignment": ("capital_allocation_outcomes", "owner_earnings", "per_share_compounding"),
    "adaptability": ("management_commentary", "management_commitments", "projects", "capacity", "risks"),
    "evidence_confidence": ("management_commitments", "projects", "capacity", "risks", "management_commentary", "capital_allocation_outcomes", "financial_truth", "owner_earnings", "per_share_compounding"),
}

DIMENSION_LABELS = {
    "execution_discipline": "Execution discipline",
    "capital_allocation_discipline": "Capital allocation discipline",
    "candor_and_consistency": "Candor and consistency",
    "strategic_clarity": "Strategic clarity",
    "risk_handling": "Risk handling",
    "owner_alignment": "Owner alignment",
    "adaptability": "Adaptability",
    "evidence_confidence": "Evidence confidence",
}

ASSESSMENT_ORDER = {value: index for index, value in enumerate(("insufficient_evidence", "weak", "mixed", "reasonably_strong", "strong"))}
CONFIDENCE_ORDER = {value: index for index, value in enumerate(("insufficient", "low", "medium", "high"))}
DIRECTION_ORDER = {value: index for index, value in enumerate(("unclear", "deteriorating", "mixed", "stable", "improving"))}


def _cap_confidence(level: str, cap: str) -> str:
    if CONFIDENCE_ORDER.get(level, 0) > CONFIDENCE_ORDER.get(cap, 0):
        return cap
    return level


def ordered_dimensions() -> List[str]:
    return list(MANAGEMENT_QUALITY_DIMENSIONS)


def normalize_assessment(value: str) -> str:
    lowered = str(value or "").strip().lower()
    return lowered if lowered in MANAGEMENT_QUALITY_ASSESSMENTS else "insufficient_evidence"


def normalize_direction(value: str) -> str:
    lowered = str(value or "").strip().lower()
    return lowered if lowered in DIRECTION_VALUES else "unclear"


def normalize_confidence_level(value: str) -> str:
    lowered = str(value or "").strip().lower()
    return lowered if lowered in EVIDENCE_CONFIDENCE_LEVELS else "insufficient"


def best_assessment(values: Sequence[str]) -> str:
    filtered = [normalize_assessment(value) for value in values if str(value or "").strip()]
    if not filtered:
        return "insufficient_evidence"
    return max(filtered, key=lambda value: ASSESSMENT_ORDER[value])


def weakest_assessment(values: Sequence[str]) -> str:
    filtered = [normalize_assessment(value) for value in values if str(value or "").strip()]
    if not filtered:
        return "insufficient_evidence"
    return min(filtered, key=lambda value: ASSESSMENT_ORDER[value])


def best_direction(values: Sequence[str]) -> str:
    filtered = [normalize_direction(value) for value in values if str(value or "").strip()]
    if not filtered:
        return "unclear"
    return max(filtered, key=lambda value: DIRECTION_ORDER[value])


def confidence_from_coverage(source_stream_counts: Dict[str, int], evidence_items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    distinct_streams = len({item.get("source_stream") for item in evidence_items if item.get("source_stream")})
    direct_items = sum(1 for item in evidence_items if item.get("evidence_type") not in {"financial_truth", "investor_panel_reference"})
    limitations: List[str] = []
    basis: List[str] = []

    critical_present = all(source_stream_counts.get(stream) for stream in ("management_commitments", "risks", "management_commentary", "capital_allocation_outcomes"))
    if distinct_streams >= 5 and direct_items >= 8 and critical_present:
        level = "high"
    elif distinct_streams >= 3 and direct_items >= 4:
        level = "medium"
    elif direct_items >= 1:
        level = "low"
    else:
        level = "insufficient"

    if not source_stream_counts.get("management_commitments"):
        limitations.append("No management commitments evidence was available.")
    if not source_stream_counts.get("projects") and not source_stream_counts.get("capacity"):
        limitations.append("Execution evidence is thin or missing.")
    if not source_stream_counts.get("capital_allocation_outcomes"):
        limitations.append("No capital-allocation outcomes evidence was available.")
    if not source_stream_counts.get("owner_earnings") and not source_stream_counts.get("per_share_compounding"):
        limitations.append("Per-share economics evidence is thin or missing.")
    if not source_stream_counts.get("risks"):
        limitations.append("Risk-evolution evidence is thin or missing.")

    if distinct_streams:
        basis.append(f"{distinct_streams} source streams contributed evidence")
    if direct_items:
        basis.append(f"{direct_items} direct evidence items were linked")
    if source_stream_counts.get("management_commentary"):
        basis.append("management commentary evolution was available")

    if level == "high" and (not source_stream_counts.get("projects") or not source_stream_counts.get("capacity")):
        level = "medium"
        limitations.append("Execution evidence is not broad enough for a high-confidence judgment.")
    if level == "high" and not (source_stream_counts.get("owner_earnings") or source_stream_counts.get("per_share_compounding")):
        level = "medium"
        limitations.append("Per-share economics are not corroborated enough for a high-confidence judgment.")

    return {"level": level, "basis": basis, "limitations": limitations}


def aggregate_overall_view(
    *,
    dimension_assessments: Dict[str, str],
    evidence_confidence_level: str,
    dimension_directions: Dict[str, str],
) -> str:
    if not dimension_assessments:
        return "insufficient_evidence"

    values = [normalize_assessment(value) for key, value in dimension_assessments.items() if key != "evidence_confidence"]
    strong_like = sum(1 for value in values if value in {"strong", "reasonably_strong"})
    mixed_like = sum(1 for value in values if value == "mixed")
    weak_like = sum(1 for value in values if value == "weak")
    insufficient_like = sum(1 for value in values if value == "insufficient_evidence")

    if insufficient_like >= 2:
        return "insufficient_evidence" if insufficient_like >= 4 else "mixed"
    if insufficient_like >= 5 and evidence_confidence_level in {"insufficient", "low"}:
        return "insufficient_evidence"
    if weak_like >= 2:
        return "weak"
    if strong_like >= 5 and weak_like == 0 and evidence_confidence_level in {"high", "medium"}:
        return "strong"
    if strong_like >= 3 and weak_like <= 1 and evidence_confidence_level != "insufficient":
        return "reasonably_strong"
    if weak_like and strong_like:
        return "mixed"
    if mixed_like >= 3:
        return "mixed"
    if evidence_confidence_level in {"insufficient", "low"} and strong_like <= 1:
        return "mixed" if mixed_like else "insufficient_evidence"
    if all(value == "insufficient_evidence" for value in values):
        return "insufficient_evidence"
    if weak_like:
        return "weak"
    if dimension_directions and best_direction(list(dimension_directions.values())) == "deteriorating":
        return "mixed"
    return "reasonably_strong" if strong_like >= 2 else "mixed"
