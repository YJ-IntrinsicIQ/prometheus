"""
Deterministic Semantic Sections Builder — ENG-MISSION48

Assembles the six investor-facing sections that must survive LLM generation
by being pre-populated deterministically from canonical data.

These sections are the difference between M37.8 (HIGH investor value) and
M47 candidate (ADEQUATE — sections absent because LLM never generated them).

CONTRACT V3 INVARIANT: MODEL_COMPRESSION_CANNOT_REMOVE_DETERMINISTIC_SEMANTICS
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_deterministic_semantic_sections(fact_pack_v2: Dict[str, Any]) -> Dict[str, Any]:
    """Build all six sections from a V2 fact pack. No AI calls.

    Returns a dict with keys matching the six required answer sections.
    LLM may enrich these but cannot omit them — assembler_v3 merges
    LLM output over this skeleton.
    """
    return {
        "what_evidence_shows": _build_what_evidence_shows(fact_pack_v2),
        "what_management_says": _build_what_management_says(fact_pack_v2),
        "where_management_was_consistent": _build_where_consistent(fact_pack_v2),
        "management_consistency_map": _build_consistency_map(fact_pack_v2),
        "what_is_not_yet_proven": _build_uncertainty(fact_pack_v2),
        "what_to_monitor": _build_monitoring(fact_pack_v2),
    }


def _build_what_evidence_shows(fp: Dict) -> List[str]:
    """Build what_evidence_shows from evidence_observations + progression counts."""
    bullets: List[str] = []

    # From evidence observations (observable outcomes)
    for obs in fp.get("evidence_observations", []):
        if obs and len(str(obs)) > 15:
            bullets.append(str(obs))

    # If we have fewer than 2 bullets, fall back to progression-derived bullet
    if len(bullets) < 2:
        pc = fp.get("progression_counts", {})
        total = pc.get("total", 0)
        delivered = pc.get("delivered", 0)
        in_progress = pc.get("in_progress", 0)
        announced = pc.get("announced", 0)
        if total > 0:
            bullets.append(
                f"Progression tracking: {total} items tracked across multi-year period; "
                f"{delivered} confirmed delivered, {in_progress} in progress, "
                f"{announced} announced — no confirmed delivery in public disclosures"
            )

    # Add commitment evidence bullet if room
    if len(bullets) < 3:
        hc = fp.get("hard_commitment_count", 0)
        total_commit = fp.get("commitment_counts", {}).get("total", 0)
        if total_commit > 0:
            hc_str = f"{hc} hard commitment(s) with specific targets; " if hc > 0 else ""
            bullets.append(
                f"Management commitments: {total_commit} tracked; {hc_str}all Unable To Verify — "
                f"no confirmed delivery across tracked commitment base"
            )

    return bullets[:3]


def _build_what_management_says(fp: Dict) -> List[str]:
    """Build what_management_says from management_statements."""
    bullets: List[str] = []
    for stmt in fp.get("management_statements", []):
        if stmt and len(str(stmt)) > 20:
            bullets.append(str(stmt))

    # Fallback: use investor_implication and strongest dimension
    if not bullets:
        strongest = fp.get("strongest_dimension", "")
        if strongest:
            bullets.append(
                f"Management has emphasized {strongest} as the primary strategic focus; "
                f"public disclosures reflect ongoing commitment to this dimension"
            )

    if len(bullets) < 2:
        implication = fp.get("investor_implication", "")
        if implication:
            bullets.append(str(implication)[:200])

    return bullets[:2]


def _build_where_consistent(fp: Dict) -> List[str]:
    """Build where_management_was_consistent from consistency_observations."""
    bullets: List[str] = []
    for obs in fp.get("consistency_observations", []):
        if obs and len(str(obs)) > 10:
            bullets.append(str(obs))

    # Fallback from consistency_map
    if not bullets:
        cmap = fp.get("consistency_map", {})
        consistent_dims = [k for k, v in cmap.items() if "CONSISTENT" in str(v).upper()]
        for dim in consistent_dims[:2]:
            bullets.append(f"{dim}: assessment indicates consistent pattern in available disclosures")

    # Fallback from conviction_strengthened
    if not bullets:
        for item in fp.get("conviction_strengthened", [])[:1]:
            bullets.append(f"Conviction strengthened by: {item}")

    return bullets[:2]


def _build_consistency_map(fp: Dict) -> Dict[str, str]:
    """Build management_consistency_map from consistency_map in fact_pack."""
    cmap = fp.get("consistency_map", {})
    if cmap:
        return {str(k): str(v) for k, v in cmap.items()}

    # Fallback: derive from strongest/weakest dimension
    result = {}
    strongest = fp.get("strongest_dimension", "")
    weakest = fp.get("weakest_dimension", "")
    if strongest:
        result[strongest] = "CONSISTENT"
    if weakest:
        result[weakest] = "INCONSISTENT"
    return result


def _build_uncertainty(fp: Dict) -> str:
    """Build what_is_not_yet_proven (enriched) from fact_pack_v2."""
    enriched = fp.get("uncertainty_items_enriched", "")
    if enriched and len(str(enriched).strip()) > 20:
        return str(enriched)

    # Fallback: combine raw uncertainty items with hard commitment names
    items = fp.get("uncertainty_items", [])
    hard = fp.get("hard_commitments", [])
    parts = []
    for hc in hard[:2]:
        mc_id = hc.get("id", "")
        tf = hc.get("expected_timeframe", "")
        norm = hc.get("normalized_commitment", "")[:80]
        if norm:
            parts.append(f"Whether {mc_id} ({tf}): {norm} — reaches confirmed delivered status")
    for raw in items[:1]:
        if raw:
            parts.append(str(raw))
    if parts:
        return ". ".join(parts)

    return (items[0] if items else "") or ""


def _build_monitoring(fp: Dict) -> List[str]:
    """Build what_to_monitor (enriched) from fact_pack_v2."""
    enriched = fp.get("monitoring_items_enriched", [])
    if isinstance(enriched, list) and len(enriched) >= 3:
        return [str(i) for i in enriched[:4]]

    # Fallback: use raw monitoring items + hard commitments
    raw = fp.get("monitoring_items", [])
    hard = fp.get("hard_commitments", [])
    items = []
    for hc in hard[:2]:
        mc_id = hc.get("id", "")
        tf = hc.get("expected_timeframe", "")
        norm = hc.get("normalized_commitment", "")[:80]
        if norm:
            items.append(f"{mc_id} ({tf}) — monitor for confirmed delivery: {norm}")
    for raw_item in raw:
        if len(items) >= 3:
            break
        if str(raw_item) not in " ".join(items):
            items.append(str(raw_item))
    return items[:4]
