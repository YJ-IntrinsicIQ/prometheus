"""
Management Answer Assembler V5 — ENG-MISSION52

Contract V5 invariant: FULLY_DETERMINISTIC — zero AI calls.

V4 authorized LLM for simple_answer (with descriptor gate) and
what_may_mean_economically (with temporal check). In practice:
- LLM simple_answer was rejected (paraphrased descriptor)
- LLM economic context was accepted but dropped PAT and was vaguer

V5 removes all LLM authorization. Both surfaces are deterministic.
The deterministic economic renderer already preserves PAT explicitly.

V5 changes from V4:
  - NO LLM provider calls for any field
  - generation_mode = DETERMINISTIC
  - execution_id excludes model/provider/prompt (no AI in identity)
  - Internal consistency validator runs and surfaces contradictions
  - MC-0031 omission fixed (investor_sections.py, all hard commitments represented)
  - Consistency map bug fixed (INCONSISTENT checked before CONSISTENT)
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from intelligence.management_quality.investor_sections import (
    build_investor_sections,
    validate_consistency_map_vs_monitoring,
)
from intelligence.management_quality.rating_quarantine import scan_answer_for_rating_violations

ASSEMBLER_VERSION = "m52_assembler_v5"
GENERATION_MODE = "DETERMINISTIC"
LLM_SECTION_OVERRIDE_BLOCKED = True
ZERO_AI_CALLS_INVARIANT = True


def compute_execution_id_v5(
    company: str,
    unit: str,
    evidence_fp: str,
    contract_v5_fp: str,
) -> str:
    """V5 execution identity: no model/provider/prompt — fully deterministic inputs only."""
    payload = json.dumps({
        "company": company,
        "unit": unit,
        "evidence_fp": evidence_fp,
        "contract_v5_fp": contract_v5_fp,
        "generation_mode": GENERATION_MODE,
        "assembler_version": ASSEMBLER_VERSION,
    }, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def build_management_answer_v5(fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble a fully deterministic management quality answer. Zero AI calls.

    All 8 output fields are constructed from canonical evidence:
      1. simple_answer — deterministic template
      2. key_points — deterministic
      3. what_evidence_shows — deterministic from evidence observations
      4. what_management_says — deterministic, all canonical hard commitments
      5. where_management_was_consistent — deterministic
      6. management_consistency_map — deterministic (INCONSISTENT bug fixed)
      7. what_may_mean_economically — deterministic, preserves PAT
      8. what_is_not_yet_proven — deterministic
      9. what_to_monitor — deterministic

    Internal consistency validator runs and surfaces any map/monitoring contradictions.
    """
    det = build_investor_sections(fact_pack)

    simple_answer = _build_deterministic_simple_answer(fact_pack)
    key_points = _build_deterministic_key_points(fact_pack)
    what_may_mean_economically = _build_deterministic_economic_context(fact_pack)

    consistency_map = det["management_consistency_map"]
    what_to_monitor = det["what_to_monitor"]
    contradictions = validate_consistency_map_vs_monitoring(consistency_map, what_to_monitor)

    answer: Dict[str, Any] = {
        "simple_answer": simple_answer,
        "key_points": key_points,
        "what_evidence_shows": det["what_evidence_shows"],
        "what_management_says": det["what_management_says"],
        "where_management_was_consistent": det["where_management_was_consistent"],
        "management_consistency_map": consistency_map,
        "what_may_mean_economically": what_may_mean_economically,
        "what_is_not_yet_proven": det["what_is_not_yet_proven"],
        "what_to_monitor": what_to_monitor,
        "behavioral_descriptor": fact_pack.get("behavioral_descriptor", ""),
        "deterministic_precision_facts": fact_pack.get("dpfs", []),
        "claims": [],
        "_assembler_version": ASSEMBLER_VERSION,
        "_generation_mode": GENERATION_MODE,
        "_deterministic_sections_preserved": True,
        "_llm_section_override_blocked": LLM_SECTION_OVERRIDE_BLOCKED,
        "_zero_ai_calls": ZERO_AI_CALLS_INVARIANT,
    }

    if contradictions:
        answer["_consistency_map_contradictions"] = contradictions

    violations = scan_answer_for_rating_violations(answer)
    if violations:
        answer["_rating_violations"] = violations

    return answer


def _build_deterministic_simple_answer(fp: Dict[str, Any]) -> str:
    """Deterministic simple_answer. Temporal protection: confirmed data labeled confirmed."""
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
        fin_str = f" Revenue ₹{val:,.0f} cr (confirmed {fy});"
        if npm is not None:
            fin_str += f" NPM {npm:.1f}%;"

    return (
        f"Management delivery pattern is {descriptor}: {delivered} of {total} tracked progression items "
        f"confirmed delivered in public disclosures. {total_commits} management commitments{hard_str} — "
        f"all Unable To Verify.{fin_str} Conviction should remain selective until delivery evidence emerges."
    )


def _build_deterministic_economic_context(fp: Dict[str, Any]) -> str:
    """Deterministic what_may_mean_economically. Preserves PAT explicitly."""
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

    # PAT is always included when available — this was the V4 LLM defect (dropped PAT)
    pat_str = f"; PAT ₹{pv:,.0f} cr" if pv is not None else ""
    npm_str = f"; NPM {npm:.1f}%" if npm is not None else ""

    return (
        f"Financial scale is confirmed: Revenue ₹{rv:,.0f} cr{pat_str}{npm_str} (confirmed {fy}). "
        f"However, causal attribution to specific management initiatives is not established — "
        f"financial outcomes cannot independently confirm management quality until delivery evidence emerges."
    )


def _build_deterministic_key_points(fp: Dict[str, Any]) -> List[str]:
    """Deterministic key_points. No rating language."""
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
        f"Delivery follow-through: {descriptor} — {delivered} of {total} tracked items confirmed delivered; "
        f"{in_progress} in progress, {announced} announced ({period_range})",
        f"Management commitments: {total_commits} total{f'; {hc} hard (specific-timeframe)' if hc else ''}; "
        f"all Unable To Verify across tracked base",
    ]

    fin = fp.get("financial_context", {})
    rev = fin.get("revenue")
    if rev and rev.get("value") is not None:
        fy = rev.get("fiscal_year", "").upper()
        rv = rev["value"]
        npm_str = f"; NPM {npm:.1f}%" if npm is not None else ""
        points.append(
            f"Financial scale confirmed ({fy}): Revenue ₹{rv:,.0f} cr{npm_str}; "
            f"causal attribution to management plans not established"
        )

    ec = fp.get("evidence_confidence", "")
    if ec:
        points.append(
            f"Evidence confidence: {ec.upper()} — longitudinal evidence across available source streams"
        )

    return points
