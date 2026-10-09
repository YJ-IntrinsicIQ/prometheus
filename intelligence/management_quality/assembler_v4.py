"""
Management Answer Assembler V4 — ENG-MISSION50

Key change from V3: LLM CANNOT override any deterministic investor section.

V3 assembler preferred LLM content for structured sections if it was
"substantive" (>= 2 entries, > 15 chars). This allowed M49's LLM to
replace investor-grade deterministic content with generic prose.

V4 invariant: LLM_SECTION_OVERRIDE_BLOCKED = True
  - All structured sections are deterministic
  - LLM provides only: simple_answer narrative text
  - what_may_mean_economically: LLM may provide if it passes temporal check

CONTRACT V4 INVARIANT: PROMETHEUS_CONSTRUCTS_INVESTOR_INTELLIGENCE
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from intelligence.management_quality.investor_sections import build_investor_sections
from intelligence.management_quality.rating_quarantine import (
    contains_rating_language,
    scan_answer_for_rating_violations,
)

ASSEMBLER_VERSION = "m50_assembler_v4"
LLM_SECTION_OVERRIDE_BLOCKED = True

# Temporal status protection: flag descriptions that use "projected" for confirmed data
_PROJECTED_PATTERN = re.compile(r"\bprojected\s+(?:revenue|earnings|profit|pat|sales)\b", re.IGNORECASE)
_CONFIRMED_VALUE_PATTERN = re.compile(r"₹[\d,]+\s*cr", re.IGNORECASE)


def _temporal_check_passes(text: str, is_confirmed: bool) -> bool:
    """Return False if confirmed financial data is called 'projected'."""
    if not is_confirmed:
        return True
    if _PROJECTED_PATTERN.search(text) and _CONFIRMED_VALUE_PATTERN.search(text):
        return False
    return True


def assemble_management_answer_v4(
    fact_pack_v2: Dict[str, Any],
    llm_prose: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble a management quality answer. All structured sections are deterministic.

    LLM prose is accepted only for:
      - simple_answer: used if it contains the behavioral descriptor AND no rating language
      - what_may_mean_economically: used if substantive AND passes temporal check

    Everything else is always deterministic.

    Args:
        fact_pack_v2: Output of build_management_quality_fact_pack_v2().
        llm_prose: Optional dict with LLM-generated fields.

    Returns:
        Complete answer dict where LLM_SECTION_OVERRIDE_BLOCKED = True.
    """
    det = build_investor_sections(fact_pack_v2)
    llm = llm_prose or {}

    fin = fact_pack_v2.get("financial_context", {})
    has_confirmed_fy = fin.get("revenue", {}).get("value") is not None

    # 1. simple_answer: LLM allowed IFF it has behavioral descriptor + no rating language + temporal check
    descriptor = fact_pack_v2.get("behavioral_descriptor", "")
    llm_simple = str(llm.get("simple_answer") or "")
    if (
        descriptor
        and descriptor in llm_simple
        and not contains_rating_language(llm_simple)
        and _temporal_check_passes(llm_simple, has_confirmed_fy)
    ):
        simple_answer = llm_simple
    else:
        simple_answer = _build_deterministic_simple_answer(fact_pack_v2)

    # 2-7. Structured sections: ALWAYS deterministic (LLM cannot override)
    what_evidence_shows = det["what_evidence_shows"]
    what_management_says = det["what_management_says"]
    where_consistent = det["where_management_was_consistent"]
    consistency_map = det["management_consistency_map"]
    what_is_not_yet_proven = det["what_is_not_yet_proven"]
    what_to_monitor = det["what_to_monitor"]

    # 8. what_may_mean_economically: LLM allowed if substantive + temporal check passes
    llm_wmme = str(llm.get("what_may_mean_economically") or "")
    if (
        len(llm_wmme.strip()) > 30
        and not contains_rating_language(llm_wmme)
        and _temporal_check_passes(llm_wmme, has_confirmed_fy)
    ):
        what_may_mean_economically = llm_wmme
    else:
        what_may_mean_economically = _build_deterministic_economic_context(fact_pack_v2)

    # 9. key_points: always deterministic
    key_points = _build_deterministic_key_points(fact_pack_v2)

    # 10. Deterministic fields
    behavioral_descriptor = fact_pack_v2.get("behavioral_descriptor", "")
    dpfs = fact_pack_v2.get("dpfs", [])
    claims = []  # LLM claims not accepted in V4

    answer = {
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
        "_llm_section_override_blocked": LLM_SECTION_OVERRIDE_BLOCKED,
    }

    # Rating language safety check (non-blocking — produces metadata)
    violations = scan_answer_for_rating_violations(answer)
    if violations:
        answer["_rating_violations"] = violations

    return answer


def _build_deterministic_simple_answer(fp: Dict[str, Any]) -> str:
    """Deterministic simple_answer. Confirms financial data is actual, not projected."""
    descriptor = fp.get("behavioral_descriptor", "UNKNOWN")
    pc = fp.get("progression_counts", {})
    delivered = pc.get("delivered", 0)
    total = pc.get("total", 0)
    cc = fp.get("commitment_counts", {})
    total_commits = cc.get("total", 0)
    hc = fp.get("hard_commitment_count", 0)
    npm = fp.get("npm")

    hard_str = f"; {hc} hard commitments" if hc > 0 else ""
    fin = fp.get("financial_context", {})
    rev = fin.get("revenue")
    fin_str = ""
    if rev and rev.get("value") is not None:
        fy = rev.get("fiscal_year", "").upper()
        val = rev["value"]
        # TEMPORAL PROTECTION: use "confirmed" not "projected"
        fin_str = f" Revenue ₹{val:,.0f} cr (confirmed {fy});"
        if npm is not None:
            fin_str += f" NPM {npm:.1f}%;"

    return (
        f"Management delivery pattern is {descriptor}: {delivered} of {total} tracked progression items "
        f"confirmed delivered in public disclosures. {total_commits} management commitments{hard_str} — "
        f"all Unable To Verify.{fin_str} Conviction should remain selective until delivery evidence emerges."
    )


def _build_deterministic_economic_context(fp: Dict[str, Any]) -> str:
    """Deterministic what_may_mean_economically. Never calls confirmed data 'projected'."""
    fin = fp.get("financial_context", {})
    npm = fp.get("npm")
    rev = fin.get("revenue")
    pat = fin.get("pat")

    if not rev or rev.get("value") is None:
        return (
            "Economic interpretation requires confirmed delivery evidence before management actions "
            "can be attributed to financial outcomes. Causal attribution is not established."
        )

    fy = rev.get("fiscal_year", "").upper()
    rv = rev["value"]
    pv = pat["value"] if pat and pat.get("value") is not None else None

    # TEMPORAL PROTECTION: confirmed data explicitly labeled as confirmed
    pat_str = f"; PAT ₹{pv:,.0f} cr" if pv is not None else ""
    npm_str = f"; NPM {npm:.1f}%" if npm is not None else ""

    return (
        f"Financial scale is confirmed: Revenue ₹{rv:,.0f} cr{pat_str}{npm_str} (confirmed {fy}). "
        f"However, causal attribution to specific management initiatives is not established — "
        f"financial outcomes cannot independently confirm management quality until delivery evidence emerges."
    )


def _build_deterministic_key_points(fp: Dict[str, Any]) -> List[str]:
    """Deterministic key_points skeleton. Omits management quality rating language."""
    descriptor = fp.get("behavioral_descriptor", "UNKNOWN")
    pc = fp.get("progression_counts", {})
    total = pc.get("total", 0)
    delivered = pc.get("delivered", 0)
    in_progress = pc.get("in_progress", 0)
    announced = pc.get("announced", 0)
    cc = fp.get("commitment_counts", {})
    total_commits = cc.get("total", 0)
    hc = fp.get("hard_commitment_count", 0)
    npm = fp.get("npm")

    period_range = fp.get("evidence_period_range", "multi-year")

    points = [
        f"Delivery follow-through: {descriptor} — {delivered} of {total} tracked items confirmed delivered; {in_progress} in progress, {announced} announced ({period_range})",
        f"Management commitments: {total_commits} total{f'; {hc} hard (specific-timeframe)' if hc else ''}; all Unable To Verify across tracked base",
    ]

    fin = fp.get("financial_context", {})
    rev = fin.get("revenue")
    if rev and rev.get("value") is not None:
        fy = rev.get("fiscal_year", "").upper()
        rv = rev["value"]
        npm_str = f"; NPM {npm:.1f}%" if npm is not None else ""
        points.append(
            f"Financial scale confirmed ({fy}): Revenue ₹{rv:,.0f} cr{npm_str}; causal attribution to management plans not established"
        )

    ec = fp.get("evidence_confidence", "")
    if ec:
        points.append(f"Evidence confidence: {ec.upper()} — longitudinal evidence across available source streams")

    return points
