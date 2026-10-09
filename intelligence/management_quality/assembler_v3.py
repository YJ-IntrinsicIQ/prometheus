"""
Management Answer Assembler V3 — ENG-MISSION48

Takes:
  - fact_pack_v2 (canonical deterministic data)
  - deterministic_semantic_sections (six pre-built sections)
  - LLM-generated prose (optional)

Returns a merged answer dict where:
  - Deterministic sections CANNOT be removed by LLM compression
  - LLM prose can enrich but not overwrite canonical sections

CONTRACT V3 INVARIANT: MODEL_COMPRESSION_CANNOT_REMOVE_DETERMINISTIC_SEMANTICS
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from intelligence.management_quality.semantic_sections import build_deterministic_semantic_sections

ASSEMBLER_VERSION = "m48_assembler_v3"


def assemble_management_answer_v3(
    fact_pack_v2: Dict[str, Any],
    llm_prose: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Assemble a complete management quality answer from deterministic data + LLM prose.

    Merge strategy:
      - All deterministic sections are pre-populated from fact_pack_v2.
      - LLM prose may ENRICH deterministic sections (add detail) but cannot REPLACE them.
      - If LLM omits a required section, the deterministic version is preserved.
      - simple_answer from LLM is used IF it contains the behavioral descriptor; otherwise
        a deterministic fallback is generated.

    Args:
        fact_pack_v2: Output of build_management_quality_fact_pack_v2().
        llm_prose: Optional dict with LLM-generated fields (simple_answer, what_may_mean_economically, etc.)

    Returns:
        Complete answer dict ready for PACP + EIV V2 validation.
    """
    det = build_deterministic_semantic_sections(fact_pack_v2)
    llm = llm_prose or {}

    # 1. simple_answer: use LLM if it contains the behavioral descriptor, else build deterministic
    descriptor = fact_pack_v2.get("behavioral_descriptor", "")
    llm_simple = str(llm.get("simple_answer") or "")
    if descriptor and descriptor in llm_simple:
        simple_answer = llm_simple
    elif descriptor:
        simple_answer = _build_fallback_simple_answer(fact_pack_v2)
    else:
        simple_answer = llm_simple or _build_fallback_simple_answer(fact_pack_v2)

    # 2. what_evidence_shows: prefer LLM if substantive (>= 2 entries), else use deterministic
    llm_wes = llm.get("what_evidence_shows")
    if isinstance(llm_wes, list) and len(llm_wes) >= 2 and all(len(str(e)) > 15 for e in llm_wes):
        what_evidence_shows = llm_wes
    else:
        what_evidence_shows = det["what_evidence_shows"]

    # 3. what_management_says: prefer LLM, fallback to deterministic
    llm_wms = llm.get("what_management_says")
    if isinstance(llm_wms, list) and len(llm_wms) >= 1:
        what_management_says = llm_wms
    elif isinstance(llm_wms, str) and len(llm_wms.strip()) > 20:
        what_management_says = [llm_wms]
    else:
        what_management_says = det["what_management_says"]

    # 4. where_management_was_consistent: prefer LLM, fallback to deterministic
    llm_wmwc = llm.get("where_management_was_consistent")
    if isinstance(llm_wmwc, list) and len(llm_wmwc) >= 1:
        where_consistent = llm_wmwc
    elif isinstance(llm_wmwc, str) and len(llm_wmwc.strip()) > 20:
        where_consistent = [llm_wmwc]
    else:
        where_consistent = det["where_management_was_consistent"]

    # 5. management_consistency_map: prefer LLM dict with >= 3 entries, else deterministic
    llm_mcm = llm.get("management_consistency_map")
    if isinstance(llm_mcm, dict) and len(llm_mcm) >= 3:
        consistency_map = llm_mcm
    else:
        consistency_map = det["management_consistency_map"]

    # 6. what_may_mean_economically: prefer LLM if substantive, else build deterministic
    llm_wmme = str(llm.get("what_may_mean_economically") or "")
    if len(llm_wmme.strip()) > 30:
        what_may_mean_economically = llm_wmme
    else:
        what_may_mean_economically = _build_fallback_economic_context(fact_pack_v2)

    # 7. what_is_not_yet_proven: deterministic (enriched) ALWAYS preserved; LLM may not replace
    what_is_not_yet_proven = det["what_is_not_yet_proven"]

    # 8. what_to_monitor: deterministic (enriched) ALWAYS preserved
    what_to_monitor = det["what_to_monitor"]

    # 9. key_points: prefer LLM if >= 3 entries, else build from deterministic
    llm_kp = llm.get("key_points", [])
    if isinstance(llm_kp, list) and len(llm_kp) >= 3:
        key_points = llm_kp
    else:
        key_points = _build_fallback_key_points(fact_pack_v2)

    # 10. behavioral_descriptor: always deterministic
    behavioral_descriptor = fact_pack_v2.get("behavioral_descriptor", "")

    # 11. deterministic_precision_facts: always from fact_pack_v2 V2 DPFs
    dpfs = fact_pack_v2.get("dpfs", [])

    # 12. claims: from LLM if present, else empty
    claims = llm.get("claims", [])

    return {
        "simple_answer": simple_answer,
        "key_points": key_points,
        "what_evidence_shows": what_evidence_shows,
        "what_management_says": what_management_says,
        "where_management_was_consistent": where_consistent,
        "management_consistency_map": consistency_map,
        "what_may_mean_economically": what_may_mean_economically,
        "what_is_not_yet_proven": what_is_not_yet_proven,
        "what_to_monitor": what_to_monitor,
        "behavioral_descriptor": behavioral_descriptor,
        "deterministic_precision_facts": dpfs,
        "claims": claims,
        "_assembler_version": ASSEMBLER_VERSION,
        "_deterministic_sections_preserved": True,
    }


def _build_fallback_simple_answer(fp: Dict[str, Any]) -> str:
    """Deterministic simple_answer when LLM omits the behavioral descriptor."""
    descriptor = fp.get("behavioral_descriptor", "UNKNOWN")
    pc = fp.get("progression_counts", {})
    total = pc.get("total", 0)
    delivered = pc.get("delivered", 0)
    cc = fp.get("commitment_counts", {})
    total_commits = cc.get("total", 0)
    hc = fp.get("hard_commitment_count", 0)
    npm = fp.get("npm")

    hard_str = f"; {hc} hard commitments" if hc > 0 else ""
    npm_str = f" NPM {npm:.1f}%;" if npm is not None else ""
    fin = fp.get("financial_context", {})
    rev = fin.get("revenue")
    rev_str = ""
    if rev and rev.get("value") is not None:
        fy = rev.get("fiscal_year", "").upper()
        val = rev["value"]
        unit = rev.get("unit", "")
        rev_str = f" Revenue ₹{val:,.0f} cr ({fy});{npm_str}" if "cr" in unit.lower() else f" Revenue {val} {unit};{npm_str}"

    return (
        f"Management delivery pattern is {descriptor}: {delivered} of {total} tracked progression items "
        f"confirmed delivered in public disclosures. {total_commits} management commitments{hard_str} — "
        f"all Unable To Verify.{rev_str} Conviction should remain selective until delivery evidence emerges."
    )


def _build_fallback_economic_context(fp: Dict[str, Any]) -> str:
    """Deterministic what_may_mean_economically when LLM omits it."""
    fin = fp.get("financial_context", {})
    npm = fp.get("npm")
    rev = fin.get("revenue")
    pat = fin.get("pat")

    if not rev or rev.get("value") is None:
        return (
            "Economic interpretation requires confirmed delivery evidence before management actions "
            "can be attributed to financial outcomes. Causal attribution not established."
        )

    fy = rev.get("fiscal_year", "").upper()
    rv = rev["value"]
    pv = pat["value"] if pat and pat.get("value") is not None else None
    npm_str = f" (NPM {npm:.1f}%)" if npm is not None else ""

    pat_str = f"; PAT ₹{pv:,.0f} cr" if pv is not None else ""
    return (
        f"Financial scale is confirmed: Revenue ₹{rv:,.0f} cr{pat_str}{npm_str} ({fy}). "
        f"However, causal attribution to specific management initiatives is not established — "
        f"financial outcomes cannot independently confirm management quality until delivery evidence emerges."
    )


def _build_fallback_key_points(fp: Dict[str, Any]) -> List[str]:
    """Deterministic key_points skeleton."""
    descriptor = fp.get("behavioral_descriptor", "UNKNOWN")
    pc = fp.get("progression_counts", {})
    total = pc.get("total", 0)
    delivered = pc.get("delivered", 0)
    in_progress = pc.get("in_progress", 0)
    cc = fp.get("commitment_counts", {})
    total_commits = cc.get("total", 0)
    hc = fp.get("hard_commitment_count", 0)
    strongest = fp.get("strongest_dimension", "")
    npm = fp.get("npm")
    npm_str = f"; NPM {npm:.1f}%" if npm is not None else ""

    points = [
        f"Delivery pattern: {descriptor} — {delivered} of {total} tracked items confirmed delivered; {in_progress} in progress",
        f"Management commitments: {total_commits} total{f'; {hc} hard' if hc else ''}; all Unable To Verify",
    ]
    if strongest:
        points.append(f"Strongest dimension: {strongest}")
    fin = fp.get("financial_context", {})
    rev = fin.get("revenue")
    if rev and rev.get("value") is not None:
        fy = rev.get("fiscal_year", "").upper()
        points.append(f"Financial scale confirmed ({fy}){npm_str}; causal attribution to management not established")
    return points
