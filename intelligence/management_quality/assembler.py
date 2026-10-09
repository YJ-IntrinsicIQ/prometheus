"""
M47: Contract V2 assembler — merges deterministic fact pack with LLM synthesis.

Invariant: DETERMINISTIC_FIELD_PRECEDENCE = true
Deterministic fields from the fact pack override any LLM-generated values.
LLM output provides prose synthesis only.

No AI calls.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# Fields that the LLM cannot overwrite — always sourced from canonical fact pack
_DETERMINISTIC_FIELDS = frozenset({
    "deterministic_precision_facts",
    "behavioral_descriptor",
})

# Fields sourced from fact pack when LLM omits them (fail-safe fallback)
_FALLBACK_FIELDS = frozenset({
    "what_is_not_yet_proven",
    "what_to_monitor",
})


def assemble_contract_v2_answer(
    llm_output: Dict[str, Any],
    fact_pack: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge LLM synthesis with deterministic fact pack values.

    Deterministic field precedence:
    - deterministic_precision_facts: ALWAYS from fact_pack.dpfs
    - behavioral_descriptor: ALWAYS from fact_pack.behavioral_descriptor
    - what_is_not_yet_proven: from fact_pack.uncertainty_items if LLM omitted or empty
    - what_to_monitor: from fact_pack.monitoring_items if LLM omitted or empty

    LLM narrative fields (kept from LLM output):
    - simple_answer, why_it_matters, investor_interpretation
    - key_points (LLM version augmented if < 3 entries)
    - what_evidence_shows, what_may_mean_economically
    - what_management_says, where_management_was_consistent

    DETERMINISTIC_FIELD_OVERWRITE_BLOCKED = true
    """
    result = dict(llm_output)

    # ── MANDATORY overrides (always from fact pack) ────────────────────────────
    dpfs = fact_pack.get("dpfs", [])
    result["deterministic_precision_facts"] = dpfs

    descriptor = fact_pack.get("behavioral_descriptor")
    if descriptor:
        result["behavioral_descriptor"] = descriptor

    # ── Fallback: inject from fact pack when LLM omitted ──────────────────────
    uncertainty = fact_pack.get("uncertainty_items", [])
    if uncertainty and not _has_content(result.get("what_is_not_yet_proven")):
        if isinstance(uncertainty, list):
            result["what_is_not_yet_proven"] = "; ".join(str(u) for u in uncertainty[:3])
        else:
            result["what_is_not_yet_proven"] = str(uncertainty)

    monitoring = fact_pack.get("monitoring_items", [])
    if monitoring and not _has_content(result.get("what_to_monitor")):
        result["what_to_monitor"] = monitoring[:5] if isinstance(monitoring, list) else [str(monitoring)]

    # ── Ensure key_points minimum ≥ 3 ─────────────────────────────────────────
    kp = result.get("key_points", [])
    if isinstance(kp, list) and len(kp) < 3:
        prog = fact_pack.get("progression_counts", {})
        total = prog.get("total", 0)
        delivered = prog.get("delivered", 0)
        fallback_kps = [
            f"{delivered} of {total} progression items confirmed delivered (multi-year tracking)",
            f"Behavioral pattern: {descriptor}" if descriptor else "Follow-through unverified",
            f"Evidence confidence: {fact_pack.get('evidence_confidence', 'UNKNOWN')}",
        ]
        while len(kp) < 3 and fallback_kps:
            kp.append(fallback_kps.pop(0))
        result["key_points"] = kp

    return result


def verify_deterministic_field_precedence(
    assembled: Dict[str, Any],
    fact_pack: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Verify that deterministic fields in the assembled answer match the fact pack.

    Returns:
        {"valid": bool, "violations": [...]}
    """
    violations = []

    # DPFs must match fact pack exactly
    assembled_dpfs = assembled.get("deterministic_precision_facts", [])
    expected_dpfs = fact_pack.get("dpfs", [])
    if assembled_dpfs != expected_dpfs:
        violations.append({
            "field": "deterministic_precision_facts",
            "expected_count": len(expected_dpfs),
            "actual_count": len(assembled_dpfs),
        })

    # Behavioral descriptor must match
    assembled_desc = assembled.get("behavioral_descriptor")
    expected_desc = fact_pack.get("behavioral_descriptor")
    if expected_desc and assembled_desc != expected_desc:
        violations.append({
            "field": "behavioral_descriptor",
            "expected": expected_desc,
            "actual": assembled_desc,
        })

    return {"valid": not violations, "violations": violations}


def _has_content(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return len(val.strip()) > 10
    if isinstance(val, (list, dict)):
        return len(val) > 0
    return bool(val)
