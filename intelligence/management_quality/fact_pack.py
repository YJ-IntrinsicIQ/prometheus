"""
Deterministic Management Quality Fact Pack — ENG-MISSION46

Builds a company-specific fact pack from canonical evidence modules without
any LLM calls. The fact pack feeds both:
  - the EIV validator (to check answer completeness), and
  - the contract assembler (to inject deterministic facts into LLM-generated answers).

No data is invented; missing evidence is explicitly recorded as UNKNOWN.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

FACT_PACK_SCHEMA_VERSION = "management_fact_pack.v1"


def _load(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _count_progression_lifecycle(items: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for it in items:
        state = str(it.get("current_status") or "unknown").strip().lower()
        counts[state] = counts.get(state, 0) + 1
    return counts


def _latest_financial_metrics(truth_pack: Dict) -> Dict[str, Any]:
    """Extract latest-year revenue and PAT from financial_truth_pack."""
    metrics = truth_pack.get("usable_current_metrics", [])
    if not isinstance(metrics, list):
        return {}

    candidates: Dict[str, List] = {"revenue": [], "pat": []}
    for m in metrics:
        if not isinstance(m, dict) or not m.get("usable_downstream"):
            continue
        mid = str(m.get("metric_id", "")).lower()
        mname = str(m.get("metric_name", "")).lower()
        if "revenue" in mid or "revenue" in mname:
            candidates["revenue"].append(m)
        elif mid == "pat" or "profit after tax" in mname:
            candidates["pat"].append(m)

    result: Dict[str, Any] = {}
    for key, lst in candidates.items():
        if not lst:
            result[key] = None
            continue
        latest = sorted(lst, key=lambda x: x.get("fiscal_year", ""), reverse=True)[0]
        result[key] = {
            "value": latest.get("value"),
            "unit": latest.get("unit", ""),
            "fiscal_year": latest.get("fiscal_year", ""),
        }
    return result


def _build_dpfs(
    progression_counts: Dict[str, int],
    total_items: int,
    commitment_counts: Dict[str, int],
    total_commitments: int,
    financial: Dict[str, Any],
    evidence_confidence: str,
) -> List[Dict[str, Any]]:
    """Build deterministic_precision_facts deterministically from canonical evidence."""
    delivered = progression_counts.get("delivered", 0)
    in_progress = progression_counts.get("in_progress", 0)
    announced = progression_counts.get("announced", 0)
    partial = progression_counts.get("partially_delivered", 0)

    hard = sum(
        commitment_counts.get(k, 0)
        for k in ("hard", "Hard")
        if k in commitment_counts
    )
    # Hard commitments not separately counted → use "Unable To Verify" as proxy for hard
    # The commitment status_counts key names vary; total unable-to-verify
    unable = sum(v for k, v in commitment_counts.items() if "unable" in k.lower() or "verify" in k.lower())

    parts = []
    if partial > 0:
        parts.append(f"{partial} partially_delivered")
    progress_str = f"{delivered} delivered / {in_progress} in_progress"
    if partial:
        progress_str += f" / {partial} partially_delivered"
    progress_str += f" / {announced} announced (of {total_items})"

    dpfs: List[Dict[str, Any]] = [
        {
            "metric": "Delivery follow-through",
            "value": progress_str,
            "period": "multi-year",
            "semantic_meaning": (
                "No progression item confirmed delivered in available disclosures"
                if delivered == 0
                else f"{delivered} item(s) confirmed delivered; {announced + in_progress + partial} remaining unconfirmed"
            ),
        },
        {
            "metric": "Progression items",
            "value": progress_str,
            "period": "multi-year",
            "semantic_meaning": (
                "No item confirmed delivered in public disclosures"
                if delivered == 0
                else f"{delivered} of {total_items} items confirmed delivered"
            ),
        },
        {
            "metric": "Management commitments",
            "value": f"{total_commitments} total; {unable} unable to verify",
            "period": "multi-year",
            "semantic_meaning": (
                "All tracked commitments Unable To Verify"
                if unable == total_commitments
                else f"{unable} of {total_commitments} commitments Unable To Verify"
            ),
        },
    ]

    rev = financial.get("revenue")
    pat = financial.get("pat")
    if rev and rev.get("value") is not None:
        fy = rev.get("fiscal_year", "").upper()
        val = rev["value"]
        unit = rev.get("unit", "")
        val_str = f"₹{val:,.0f} cr" if "crore" in unit.lower() or "cr" in unit.lower() else f"{val} {unit}"
        pat_str = ""
        if pat and pat.get("value") is not None:
            pv = pat["value"]
            pat_str = f"; PAT ₹{pv:,.0f} cr" if "crore" in (pat.get("unit","")).lower() else f"; PAT {pv}"
        dpfs.append({
            "metric": f"Financial scale ({fy})",
            "value": f"Revenue {val_str}{pat_str}",
            "period": fy,
            "semantic_meaning": "Confirmed financial outcomes; causal attribution to management plans not established",
        })

    dpfs.append({
        "metric": "Evidence confidence",
        "value": evidence_confidence.upper() if evidence_confidence else "UNKNOWN",
        "period": "multi-year",
        "semantic_meaning": (
            "Delivery and commitment follow-up observations are supported across multiple source streams"
            if evidence_confidence.lower() in ("high", "medium")
            else "Evidence confidence not established"
        ),
    })
    return dpfs


def build_management_quality_fact_pack(company: str, company_root: Optional[Path] = None) -> Dict[str, Any]:
    """Build deterministic fact pack for a company. No AI calls."""
    if company_root is None:
        company_root = Path("companies") / company / "company_memory"
    else:
        company_root = Path(company_root)

    # 1. Management progression
    mp = _load(company_root / "management_progression" / "management_progression.json") or {}
    progression_items = mp.get("progression_items", []) if isinstance(mp, dict) else []
    progression_counts = _count_progression_lifecycle(progression_items)
    total_progression = len(progression_items)

    # 2. Management commitments
    mc = _load(company_root / "management_commitments" / "management_commitments.json") or {}
    total_commitments = mc.get("commitment_count", 0) if isinstance(mc, dict) else 0
    commitment_status = mc.get("status_counts", {}) if isinstance(mc, dict) else {}
    category_counts = mc.get("category_counts", {}) if isinstance(mc, dict) else {}

    # 3. Management quality summary
    mqs = _load(company_root / "management_quality" / "management_quality_summary.json") or {}
    if not isinstance(mqs, dict):
        mqs = {}

    overall_direction = mqs.get("overall_direction", "UNKNOWN")
    overall_view = mqs.get("overall_view", "UNKNOWN")
    strongest_dimension = mqs.get("strongest_dimension", "UNKNOWN")
    weakest_dimension = mqs.get("weakest_dimension", "UNKNOWN")
    unresolved_questions = mqs.get("unresolved_questions") or mqs.get("interpretation", {}).get("unresolved", [])
    what_to_watch = mqs.get("interpretation", {}).get("what_to_watch", []) if isinstance(mqs.get("interpretation"), dict) else []
    evidence_confidence = mqs.get("evidence_confidence", {})
    if isinstance(evidence_confidence, dict):
        confidence_level = evidence_confidence.get("level", "UNKNOWN")
    else:
        confidence_level = str(evidence_confidence) if evidence_confidence else "UNKNOWN"

    conviction_strengthened = mqs.get("what_strengthened_conviction", [])
    conviction_weakened = mqs.get("what_weakened_conviction", [])
    investor_implication = mqs.get("investor_implication", "")
    major_turning_points = mqs.get("major_turning_points", [])

    # 4. Derive behavioral descriptor from progression counts
    delivered = progression_counts.get("delivered", 0)
    partially = progression_counts.get("partially_delivered", 0)
    if delivered == 0 and partially == 0:
        behavioral_descriptor = "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
    elif delivered >= 10 and delivered / max(total_progression, 1) >= 0.4:
        behavioral_descriptor = "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED"
    elif delivered >= 3 and partially >= 2:
        behavioral_descriptor = "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS"
    elif delivered >= 1 or partially >= 2:
        behavioral_descriptor = "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS"
    else:
        behavioral_descriptor = "FOLLOW_THROUGH_LARGELY_UNVERIFIED"

    # 5. Financial metrics
    ftp = _load(company_root / "financial_truth_pack.json") or {}
    financial = _latest_financial_metrics(ftp) if isinstance(ftp, dict) else {}

    # 6. Build DPFs
    dpfs = _build_dpfs(
        progression_counts, total_progression,
        commitment_status, total_commitments,
        financial, confidence_level,
    )

    return {
        "schema_version": FACT_PACK_SCHEMA_VERSION,
        "company": company,
        "progression_counts": {
            "total": total_progression,
            **progression_counts,
        },
        "commitment_counts": {
            "total": total_commitments,
            "by_status": commitment_status,
            "by_category": category_counts,
        },
        "behavioral_descriptor": behavioral_descriptor,
        "strongest_dimension": strongest_dimension,
        "weakest_dimension": weakest_dimension,
        "overall_direction": overall_direction,
        "investor_implication": investor_implication,
        "conviction_strengthened": conviction_strengthened,
        "conviction_weakened": conviction_weakened,
        "uncertainty_items": unresolved_questions if isinstance(unresolved_questions, list) else [],
        "monitoring_items": what_to_watch if isinstance(what_to_watch, list) else [],
        "major_turning_points": major_turning_points,
        "financial_context": financial,
        "evidence_confidence": confidence_level,
        "dpfs": dpfs,
    }
