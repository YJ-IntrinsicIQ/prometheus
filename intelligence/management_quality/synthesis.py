from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from intelligence.progression import build_interpretation_contract, rank_material_evidence

from .contracts import MANAGEMENT_QUALITY_ASSESSMENTS
from .dimensions import (
    best_assessment,
    best_direction,
    confidence_from_coverage,
    normalize_assessment,
    normalize_confidence_level,
)


def _pick_top_items(items: Sequence[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
    return list(items[:limit])


def _compact_item(evidence: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "summary": evidence.get("summary"),
        "dimension": evidence.get("dimensions", [None])[0],
        "period": evidence.get("period"),
        "evidence_ids": [evidence.get("evidence_id")],
        "confidence": evidence.get("confidence"),
        "source_stream": evidence.get("source_stream"),
        "source_item_id": evidence.get("source_item_id"),
    }
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def _group_by_dimension(evidence_items: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in evidence_items:
        for dimension in item.get("dimensions") or []:
            grouped[str(dimension)].append(item)
    return grouped


def _score_items(items: Sequence[Dict[str, Any]]) -> Tuple[int, int, int, int]:
    positive = negative = neutral = mixed = 0
    for item in items:
        weight = {"high": 3, "medium": 2, "low": 1, "insufficient": 0}.get(str(item.get("confidence") or "").lower(), 1)
        polarity = str(item.get("polarity") or "neutral").lower()
        if polarity == "positive":
            positive += weight
        elif polarity == "negative":
            negative += weight
        elif polarity == "mixed":
            mixed += weight
        else:
            neutral += weight
    return positive, negative, neutral, mixed


def _assessment_from_scores(positive: int, negative: int, neutral: int, mixed: int, item_count: int) -> str:
    if item_count == 0:
        return "insufficient_evidence"
    if positive == 0 and negative == 0 and mixed == 0:
        return "insufficient_evidence" if neutral <= 1 else "mixed"
    if negative >= positive + 3:
        return "weak"
    if positive >= negative + 4 and item_count >= 3:
        return "strong"
    if positive >= negative + 2 and item_count >= 2:
        return "reasonably_strong"
    if positive and negative:
        return "mixed"
    if mixed >= 2:
        return "mixed"
    if negative and not positive:
        return "weak"
    if positive:
        return "reasonably_strong" if item_count >= 2 else "mixed"
    return "mixed"


def _direction_from_items(items: Sequence[Dict[str, Any]]) -> str:
    directions = [str(item.get("direction") or "").lower() for item in items if str(item.get("direction") or "").strip()]
    if not directions:
        return "unclear"
    return best_direction(directions)


def _confidence_for_dimension(items: Sequence[Dict[str, Any]], *, dimension: str, source_stream_counts: Dict[str, int]) -> Dict[str, Any]:
    basis = []
    limitations = []
    if items:
        basis.append(f"{len(items)} linked evidence items")
    streams = sorted({str(item.get("source_stream") or "") for item in items if item.get("source_stream")})
    if streams:
        basis.append(f"streams: {', '.join(streams)}")
    if dimension == "evidence_confidence":
        if source_stream_counts.get("financial_truth"):
            basis.append("financial truth pack available")
        if source_stream_counts.get("investor_panel"):
            basis.append("investor panel evidence available")
    if len(streams) < 2:
        limitations.append("Evidence is concentrated in a narrow set of sources.")
    if not items:
        limitations.append("No direct evidence was linked.")
    if dimension == "owner_alignment" and not (source_stream_counts.get("owner_earnings") or source_stream_counts.get("per_share_compounding")):
        limitations.append("Per-share economics evidence is thin.")
    if dimension == "capital_allocation_discipline" and not source_stream_counts.get("capital_allocation_outcomes"):
        limitations.append("Capital-allocation outcomes evidence is missing.")
    if dimension == "capital_allocation_discipline" and not (
        source_stream_counts.get("owner_earnings")
        or source_stream_counts.get("per_share_compounding")
        or source_stream_counts.get("projects")
        or source_stream_counts.get("capacity")
    ):
        limitations.append("Capital-allocation discipline is capped until deployment is corroborated by later economics or execution evidence.")
    if dimension == "owner_alignment" and not (source_stream_counts.get("owner_earnings") or source_stream_counts.get("per_share_compounding")):
        limitations.append("Owner alignment is capped until per-share economics evidence appears.")
    if dimension == "risk_handling" and not source_stream_counts.get("risks"):
        limitations.append("Risk-evolution evidence is missing.")
    if dimension == "candor_and_consistency" and not source_stream_counts.get("management_commentary"):
        limitations.append("Management commentary evidence is thin.")
    level = "high" if len(streams) >= 3 and len(items) >= 5 else "medium" if len(items) >= 2 else "low" if items else "insufficient"
    if dimension == "capital_allocation_discipline" and level == "high" and not (
        source_stream_counts.get("owner_earnings") and source_stream_counts.get("per_share_compounding")
    ):
        level = "medium"
    if dimension == "owner_alignment" and level in {"high", "medium"} and not (
        source_stream_counts.get("owner_earnings") and source_stream_counts.get("per_share_compounding")
    ):
        level = "low"
    return {"level": level, "basis": basis, "limitations": limitations}


def _evidence_confidence_level(source_stream_counts: Dict[str, int], evidence_items: Sequence[Dict[str, Any]]) -> str:
    critical_present = all(source_stream_counts.get(stream) for stream in ("management_commitments", "risks", "management_commentary", "capital_allocation_outcomes"))
    if critical_present and len({item.get("source_stream") for item in evidence_items if item.get("source_stream")}) >= 5 and len(evidence_items) >= 10:
        return "high"
    if len(evidence_items) >= 5 and len({item.get("source_stream") for item in evidence_items if item.get("source_stream")}) >= 3:
        return "medium"
    if evidence_items:
        return "low"
    return "insufficient"


def _dimension_lists(items: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    positive = [item for item in items if str(item.get("polarity") or "").lower() == "positive"]
    negative = [item for item in items if str(item.get("polarity") or "").lower() == "negative"]
    neutral = [item for item in items if str(item.get("polarity") or "").lower() in {"neutral", "mixed"}]

    def _pack(source: Sequence[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
        return [_compact_item(item) for item in _pick_top_items(source, limit)]

    return {
        "supporting_evidence": _pack(positive + neutral, 4),
        "conflicting_evidence": _pack(negative, 4),
        "what_strengthened": _pack(positive, 3),
        "what_weakened": _pack(negative, 3),
        "what_remains_unproven": _pack(neutral, 3),
    }


def _economic_mechanism_for_dimension(dimension: str) -> str:
    mapping = {
        "execution_discipline": "Execution discipline determines whether promises, projects, and capacity actually turn into operating capability.",
        "capital_allocation_discipline": "Capital allocation determines whether deployment becomes durable returns and better per-share economics.",
        "candor_and_consistency": "Candor matters because investors can only trust management's narrative if later evidence keeps matching it.",
        "strategic_clarity": "Strategic clarity matters because a coherent direction is easier to execute and easier to monitor for drift.",
        "risk_handling": "Risk handling matters because unmanaged downside can erase the value created by otherwise good execution.",
        "owner_alignment": "Owner alignment matters because shareholder value compounds only when capital decisions improve per-share economics.",
        "adaptability": "Adaptability matters because evidence should change the plan when the original path stops working.",
        "evidence_confidence": "Evidence confidence matters because weak evidence should not be promoted into a strong judgment.",
    }
    return mapping.get(dimension, "The evidence matters because it changes how investors should read the long-term trajectory.")


def evaluate_dimensions(
    *,
    evidence_items: Sequence[Dict[str, Any]],
    source_stream_counts: Dict[str, int],
    latest_period: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    grouped = _group_by_dimension(evidence_items)
    records: List[Dict[str, Any]] = []
    dimension_assessments: Dict[str, str] = {}
    dimension_directions: Dict[str, str] = {}
    evidence_confidence_level = _evidence_confidence_level(source_stream_counts, evidence_items)

    for dimension in (
        "execution_discipline",
        "capital_allocation_discipline",
        "candor_and_consistency",
        "strategic_clarity",
        "risk_handling",
        "owner_alignment",
        "adaptability",
        "evidence_confidence",
    ):
        items = list(grouped.get(dimension, []))
        required_stream_groups = {
            "execution_discipline": (("management_commitments",), ("projects", "capacity")),
            "capital_allocation_discipline": (("capital_allocation_outcomes",),),
            "candor_and_consistency": (("management_commentary",),),
            "strategic_clarity": (("management_commentary", "management_commitments"),),
            "risk_handling": (("risks",),),
            "owner_alignment": (("owner_earnings", "per_share_compounding"),),
            "adaptability": (("management_commentary",), ("projects", "capacity", "risks")),
        }
        required_groups = required_stream_groups.get(dimension, ())
        missing_required = [group for group in required_groups if not any(source_stream_counts.get(stream) for stream in group)]
        positive, negative, neutral, mixed = _score_items(items)
        if dimension == "evidence_confidence":
            assessment = evidence_confidence_level
            direction = "improving" if evidence_confidence_level == "high" and len(evidence_items) >= 8 else "stable" if evidence_confidence_level in {"medium", "high"} else "unclear"
        else:
            assessment = _assessment_from_scores(positive, negative, neutral, mixed, len(items))
            direction = _direction_from_items(items)
            if missing_required or len(items) < 2:
                assessment = "insufficient_evidence"
                direction = "unclear"
        dimension_assessments[dimension] = assessment
        dimension_directions[dimension] = direction
        packs = _dimension_lists(items)
        confidence = _confidence_for_dimension(items, dimension=dimension, source_stream_counts=source_stream_counts)
        latest_items = [item for item in items if str(item.get("period") or "").strip() == latest_period]
        record = {
            "dimension": dimension,
            "assessment": assessment,
            "direction": direction,
            "what_strengthened": packs["what_strengthened"],
            "what_weakened": packs["what_weakened"],
            "what_remains_unproven": packs["what_remains_unproven"],
            "supporting_evidence": packs["supporting_evidence"],
            "conflicting_evidence": packs["conflicting_evidence"],
            "confidence": confidence,
            "investor_implication": _investor_implication(dimension, assessment, direction, items),
            "latest_period": latest_period,
            "evidence_ids": [item.get("evidence_id") for item in items if item.get("evidence_id")],
            "source_streams": sorted({str(item.get("source_stream") or "") for item in items if item.get("source_stream")}),
            "eligible_evidence_count": len(items),
            "material_evidence_count": sum(1 for item in items if str(item.get("relevance") or "").lower() in {"high", "medium"}),
            "period_coverage": sorted({str(item.get("period") or "") for item in items if item.get("period")}),
            "source_stream_coverage": sorted({str(item.get("source_stream") or "") for item in items if item.get("source_stream")}),
            "conflicting_evidence_count": len(packs["conflicting_evidence"]),
            "excluded_evidence_count": 0,
            "missing_critical_stream_groups": [list(group) for group in missing_required],
            "evidence_confidence": confidence,
        }
        if dimension == "evidence_confidence":
            record["assessment"] = assessment
        record["interpretation"] = build_interpretation_contract(
            conclusion=f"{dimension.replace('_', ' ').title()} is {assessment.replace('_', ' ')}.",
            what_changed=[
                item.get("summary")
                for item in _pick_top_items(packs["what_strengthened"] + packs["what_weakened"], limit=3)
                if isinstance(item, dict) and item.get("summary")
            ],
            why_it_matters=_investor_implication(dimension, assessment, direction, items),
            economic_mechanism=_economic_mechanism_for_dimension(dimension),
            thesis_impact=(
                "strengthens"
                if assessment in {"strong", "reasonably_strong"}
                else "weakens"
                if assessment == "weak"
                else "neutral"
                if assessment in {"mixed", "insufficient_evidence"}
                else "unresolved"
            ),
            positive_evidence=[item.get("summary") for item in packs["what_strengthened"] if item.get("summary")],
            negative_evidence=[item.get("summary") for item in packs["what_weakened"] if item.get("summary")],
            unresolved=[item.get("summary") for item in packs["what_remains_unproven"] if item.get("summary")],
            what_to_watch=[
                f"{dimension.replace('_', ' ')} evidence in {latest_period}" if latest_period else f"More evidence for {dimension.replace('_', ' ')}",
                _investor_implication(dimension, assessment, direction, items),
            ],
            confidence=confidence,
        )
        records.append(record)
    return records, {"dimension_assessments": dimension_assessments, "dimension_directions": dimension_directions, "evidence_confidence_level": evidence_confidence_level}


def _investor_implication(dimension: str, assessment: str, direction: str, items: Sequence[Dict[str, Any]]) -> str:
    if assessment == "insufficient_evidence":
        return "The evidence is too thin to change conviction with confidence."
    if dimension == "execution_discipline":
        if assessment in {"strong", "reasonably_strong"}:
            return "Execution appears dependable enough to support conviction."
        if assessment == "weak":
            return "Execution gaps should temper conviction."
        return "Execution is visible, but the pattern is still mixed."
    if dimension == "capital_allocation_discipline":
        if assessment in {"strong", "reasonably_strong"}:
            return "Capital appears to be deployed with reasonable discipline."
        if assessment == "weak":
            return "Capital deployment is not yet proving its worth."
        return "Capital allocation remains mixed and must be watched over time."
    if dimension == "candor_and_consistency":
        if assessment in {"strong", "reasonably_strong"}:
            return "Management explanations appear broadly aligned with later evidence."
        if assessment == "weak":
            return "The narrative has become harder to trust as a guide to evidence."
        return "Management candor is visible, but consistency is not yet settled."
    if dimension == "strategic_clarity":
        if assessment in {"strong", "reasonably_strong"}:
            return "Management direction looks coherent enough to follow."
        if assessment == "weak":
            return "Strategic drift should reduce confidence in the roadmap."
        return "Strategy is visible, but the pattern is still incomplete."
    if dimension == "risk_handling":
        if assessment in {"strong", "reasonably_strong"}:
            return "Risks appear to be surfaced and managed with some discipline."
        if assessment == "weak":
            return "Unresolved risks should keep conviction lower."
        return "Risk handling remains visible, but not yet decisive."
    if dimension == "owner_alignment":
        if assessment in {"strong", "reasonably_strong"}:
            return "Management actions appear to support per-share economics."
        if assessment == "weak":
            return "Per-share economics are not yet being protected clearly enough."
        return "Owner alignment is partly visible but not fully proven."
    if dimension == "adaptability":
        if assessment in {"strong", "reasonably_strong"}:
            return "Management appears able to adjust when evidence changes."
        if assessment == "weak":
            return "The pattern suggests poor adaptation to new facts."
        return "Adaptability is visible but not fully settled."
    if dimension == "evidence_confidence":
        if assessment == "high":
            return "The synthesis is backed by broad and direct evidence."
        if assessment == "medium":
            return "The synthesis is usable, but some areas still need stronger evidence."
        if assessment == "low":
            return "The synthesis should be read cautiously because evidence is thin."
        return "The evidence base is too small to support strong judgment."
    return "The evidence remains mixed."


def build_turning_points(evidence_items: Sequence[Dict[str, Any]], *, limit: int = 10) -> List[Dict[str, Any]]:
    candidates = [
        item
        for item in evidence_items
        if (
            (item.get("turning_point") or str(item.get("evidence_type") or "").endswith(("delivered", "commissioned", "operational", "delayed", "negative_outcome")))
            and (item.get("progression_materiality") or {}).get("should_promote", True)
        )
    ]
    ranked_candidates = rank_material_evidence(candidates, limit=len(candidates))
    unique: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in ranked_candidates:
        key = (str(item.get("source_stream") or ""), str(item.get("source_item_id") or ""), str(item.get("period") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(
            {
                "summary": item.get("summary"),
                "dimension": (item.get("dimensions") or [None])[0],
                "period": item.get("period"),
                "evidence_ids": [item.get("evidence_id")],
                "confidence": item.get("confidence"),
                "source_stream": item.get("source_stream"),
                "source_item_id": item.get("source_item_id"),
                "direction": item.get("direction"),
                "relevance": item.get("relevance"),
            }
        )
        if len(unique) >= limit:
            break
    return unique


def build_conviction_lists(
    dimension_records: Sequence[Dict[str, Any]],
    evidence_items: Sequence[Dict[str, Any]],
    *,
    limit: int = 5,
) -> Dict[str, List[Dict[str, Any]]]:
    positive = [item for item in evidence_items if str(item.get("polarity") or "").lower() == "positive"]
    negative = [item for item in evidence_items if str(item.get("polarity") or "").lower() == "negative"]
    neutral = [item for item in evidence_items if str(item.get("polarity") or "").lower() in {"neutral", "mixed"}]

    def _pack(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        packed = []
        for item in rank_material_evidence(list(items), limit=limit * 2 if items else limit):
            summary = str(item.get("summary") or "")
            if summary in seen:
                continue
            seen.add(summary)
            packed.append(
                {
                    "summary": item.get("summary"),
                    "dimension": (item.get("dimensions") or [None])[0],
                    "period": item.get("period"),
                    "evidence_ids": [item.get("evidence_id")],
                    "confidence": item.get("confidence"),
                    "source_stream": item.get("source_stream"),
                    "source_item_id": item.get("source_item_id"),
                }
            )
            if len(packed) >= limit:
                break
        return packed

    return {
        "what_strengthened_conviction": _pack(positive),
        "what_weakened_conviction": _pack(negative),
        "what_remains_unproven": _pack(neutral),
    }
