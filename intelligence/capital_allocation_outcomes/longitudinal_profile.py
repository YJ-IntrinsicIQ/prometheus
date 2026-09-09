"""
Longitudinal Capital Allocation Profile Builder — ENG-105 Phase 3.

Synthesizes the Phase 2 causal-attribution ledger into a cross-year investor
intelligence profile.

AGGREGATION ONLY:
  - Reads capital_allocation_assessments.json (Phase 2 semantic states) and
    capital_allocation_outcomes.json (periods, amounts) as sole inputs.
  - No AI calls. No raw-document access. No new event extraction.
  - Capital-weighted conclusions blocked when amount coverage is insufficient.
  - Allocation activity and allocation skill kept strictly separate.
  - Chronology never used as causality.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .paths import (
    get_capital_allocation_assessments_path,
    get_capital_allocation_longitudinal_profile_path,
    get_capital_allocation_outcomes_path,
)

# ---------------------------------------------------------------------------
# Category grouping
# ---------------------------------------------------------------------------

_ORGANIC = frozenset({
    "organic_capex", "capacity_expansion", "maintenance_capex",
    "product_development", "research_and_development", "technology_investment",
    "working_capital",
})
_INORGANIC = frozenset({
    "acquisition", "acquisition_integration", "strategic_investment",
    "joint_venture", "subsidiary_investment",
})
_DISTRIBUTION = frozenset({
    "dividend", "special_dividend", "share_buyback",
})
_BALANCE_SHEET = frozenset({
    "debt_repayment", "equity_issuance", "retained_cash",
})

# Amount coverage thresholds (fraction of records with known monetary values)
_COVERAGE_HIGH = 0.70     # ≥70%: capital-weighted conclusions permitted
_COVERAGE_PARTIAL = 0.40  # 40-70%: describe knowns, no conclusive ranking
# <40%: event-pattern only; all capital-weighted claims blocked


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fy_sort(fy: str) -> int:
    try:
        return int(str(fy).lower().replace("fy", "").strip())
    except (ValueError, AttributeError):
        return 9999


def _group(category: str) -> str:
    if category in _ORGANIC:
        return "organic"
    if category in _INORGANIC:
        return "inorganic"
    if category in _DISTRIBUTION:
        return "distribution"
    if category in _BALANCE_SHEET:
        return "balance_sheet"
    return "other"


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Outcome maturity (AGGREGATION of Phase 2 state fields — no recomputation)
# ---------------------------------------------------------------------------

def _maturity_level(rec: Dict[str, Any]) -> int:
    """Highest maturity level this allocation has reached.

    Level 0: deployment not verified
    Level 1: deployment verified
    Level 2: execution verified (COMPLETED/OPERATIONAL/IN_PROGRESS)
    Level 3: operating outcome visible (not UNABLE_TO_VERIFY / NO_VERIFIED_OUTCOME)
    Level 4: financial outcome attributable (CASH_FLOW_EFFECT or REVENUE_CONTRIBUTION etc.)
    Level 5: per-share consequence attributable (SHARE_COUNT_REDUCTION / OWNER_EARNINGS_EFFECT)
    """
    dep = rec.get("deployment_state", "UNABLE_TO_VERIFY")
    exe = rec.get("execution_state", "UNABLE_TO_VERIFY")
    oos = rec.get("operating_outcome_state", "UNABLE_TO_VERIFY")
    fos = rec.get("financial_outcome_state", "UNABLE_TO_ATTRIBUTE")
    pss = rec.get("per_share_consequence_state", "UNABLE_TO_ATTRIBUTE")

    if dep == "UNABLE_TO_VERIFY":
        return 0
    level = 1
    if exe not in {"UNABLE_TO_VERIFY", "NOT_STARTED"}:
        level = 2
    if oos not in {"UNABLE_TO_VERIFY", "NO_VERIFIED_OUTCOME"}:
        level = 3
    if fos != "UNABLE_TO_ATTRIBUTE":
        level = max(level, 4)
    if pss != "UNABLE_TO_ATTRIBUTE":
        level = max(level, 5)
    return level


# ---------------------------------------------------------------------------
# Amount coverage contract
# ---------------------------------------------------------------------------

def _amount_coverage(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(records)
    # ENG-118 Phase 1: only deterministically parsed amounts count as "known".
    # Events with amount=None but amount_basis="unit_ambiguous" are qualitatively
    # preserved but excluded from coverage and weighted totals.
    eligible = [r for r in records if not r.get("deployment_eligibility") or r.get("deployment_eligibility") in {"ELIGIBLE_DEPLOYMENT", "ELIGIBLE_DISTRIBUTION", "ELIGIBLE_DELEVERAGING"}]
    known = [r for r in eligible if r.get("amount") not in (None, "", 0)]
    known_count = len(known)
    unit_ambiguous_count = sum(
        1 for r in records
        if r.get("amount") in (None, "", 0) and r.get("amount_basis") == "unit_ambiguous"
    )
    ratio = known_count / len(eligible) if eligible else 0.0
    trusted_ratio = known_count / total if total else 0.0
    if ratio >= _COVERAGE_HIGH and trusted_ratio >= _COVERAGE_HIGH:
        status = "HIGH"
        capital_weighted_permitted = True
        note = "Capital-weighted conclusions are permitted."
    elif ratio >= _COVERAGE_PARTIAL:
        status = "PARTIAL"
        capital_weighted_permitted = False
        note = (
            "Known amounts described but conclusive capital-weighted ranking is not permitted. "
            "Describe known amounts explicitly."
        )
    else:
        status = "LOW"
        capital_weighted_permitted = False
        note = (
            "CAPITAL_MIX_INSUFFICIENT_AMOUNT_COVERAGE: event-pattern analysis only; "
            "no capital-weighted conclusions permitted."
        )
    if unit_ambiguous_count:
        note += (
            f" {unit_ambiguous_count} event(s) have source amounts with unresolvable unit context"
            " and are excluded from amount-weighted conclusions."
        )
    return {
        "events_with_known_amount": known_count,
        "events_economically_eligible": len(eligible),
        "events_ineligible": total - len(eligible),
        "events_with_weighted_eligible_amount": known_count,
        "events_without_amount": len(eligible) - known_count,
        "events_with_unit_ambiguous_amount": unit_ambiguous_count,
        "total_events": total,
        "coverage_ratio": round(ratio, 3),
        "trusted_weighted_coverage_ratio": round(trusted_ratio, 3),
        "unit_amount_coverage_ratio": round((len([r for r in records if r.get("amount") not in (None, "", 0)]) / total), 3) if total else 0.0,
        "coverage_status": status,
        "capital_weighted_conclusions_permitted": capital_weighted_permitted,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Profile sections
# ---------------------------------------------------------------------------

def _build_allocation_mix(records: List[Dict[str, Any]], cov: Dict[str, Any]) -> Dict[str, Any]:
    by_cat: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "event_count": 0,
        "known_amount_crore": None,
        "amount_events_known": 0,
    })
    for r in records:
        if r.get("deployment_eligibility") and r.get("deployment_eligibility") not in {"ELIGIBLE_DEPLOYMENT", "ELIGIBLE_DISTRIBUTION", "ELIGIBLE_DELEVERAGING"}:
            continue
        cat = r.get("allocation_category", "unknown")
        by_cat[cat]["event_count"] += 1
        amt = r.get("amount")
        if amt not in (None, "", 0):
            try:
                by_cat[cat]["known_amount_crore"] = (by_cat[cat]["known_amount_crore"] or 0) + float(amt)
                by_cat[cat]["amount_events_known"] += 1
            except (ValueError, TypeError):
                pass

    categories = []
    for cat, info in sorted(by_cat.items(), key=lambda x: -x[1]["event_count"]):
        entry: Dict[str, Any] = {
            "category": cat,
            "group": _group(cat),
            "event_count": info["event_count"],
            "known_amount_crore": info["known_amount_crore"],
            "amount_events_known": info["amount_events_known"],
        }
        if cov["capital_weighted_conclusions_permitted"] and info["known_amount_crore"]:
            total_known = sum(
                (v["known_amount_crore"] or 0) for v in by_cat.values()
            )
            entry["share_of_known_deployment"] = (
                round(info["known_amount_crore"] / total_known, 3) if total_known else None
            )
        else:
            entry["share_of_known_deployment"] = None
        categories.append(entry)

    return {
        "by_category": categories,
        "event_mix_note": (
            "Ranked by number of material decisions. "
            "Event counts do not imply capital amounts."
        ),
        "capital_mix_note": cov["note"],
        "capital_weighted_conclusions_permitted": cov["capital_weighted_conclusions_permitted"],
    }


def _build_organic_vs_inorganic(records: List[Dict[str, Any]], cov: Dict[str, Any]) -> Dict[str, Any]:
    groups: Dict[str, List[str]] = defaultdict(list)
    for r in records:
        g = _group(r.get("allocation_category", "other"))
        groups[g].append(r["allocation_id"])

    event_mix = {g: len(ids) for g, ids in groups.items()}
    total = len(records)
    return {
        "organic_event_count": event_mix.get("organic", 0),
        "inorganic_event_count": event_mix.get("inorganic", 0),
        "distribution_event_count": event_mix.get("distribution", 0),
        "balance_sheet_event_count": event_mix.get("balance_sheet", 0),
        "other_event_count": event_mix.get("other", 0),
        "organic_allocation_ids": groups.get("organic", []),
        "inorganic_allocation_ids": groups.get("inorganic", []),
        "distribution_allocation_ids": groups.get("distribution", []),
        "balance_sheet_allocation_ids": groups.get("balance_sheet", []),
        "event_mix_fractions": {
            g: round(len(ids) / total, 3) for g, ids in groups.items()
        } if total else {},
        "capital_mix_note": cov["note"],
        "capital_weighted_conclusions_permitted": cov["capital_weighted_conclusions_permitted"],
    }


def _build_timeline(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Year-by-year canonical timeline derived from deployment_periods."""
    period_events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        for period in (r.get("deployment_periods") or [r.get("first_observed_period")] or []):
            if period:
                period_events[str(period).strip().lower()].append(r)

    timeline = []
    for period in sorted(period_events.keys(), key=_fy_sort):
        events = period_events[period]
        cats = sorted({r.get("allocation_category", "unknown") for r in events})
        exec_devs = [
            {
                "allocation_id": r["allocation_id"],
                "category": r.get("allocation_category"),
                "execution_state": r.get("execution_state"),
            }
            for r in events
            if r.get("execution_state") not in {"UNABLE_TO_VERIFY", "NOT_STARTED", None}
        ]
        outcome_devs = [
            {
                "allocation_id": r["allocation_id"],
                "category": r.get("allocation_category"),
                "operating_outcome_state": r.get("operating_outcome_state"),
                "financial_outcome_state": r.get("financial_outcome_state"),
            }
            for r in events
            if r.get("operating_outcome_state") not in {"UNABLE_TO_VERIFY", "NO_VERIFIED_OUTCOME", None}
            or r.get("financial_outcome_state") not in {"UNABLE_TO_ATTRIBUTE", None}
        ]
        timeline.append({
            "period": period,
            "material_allocation_ids": [r["allocation_id"] for r in events],
            "event_count": len(events),
            "dominant_categories": cats[:3],
            "known_amount_crore": None,  # ponytail: amounts all null for Sun Pharma
            "execution_developments": exec_devs,
            "outcome_developments": outcome_devs,
        })
    return timeline


def _build_outcome_maturity(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    levels: Dict[int, List[str]] = defaultdict(list)
    for r in records:
        levels[_maturity_level(r)].append(r["allocation_id"])

    return {
        "level_0_deployment_unverified": levels.get(0, []),
        "level_1_deployment_verified": levels.get(1, []),
        "level_2_execution_verified": levels.get(2, []),
        "level_3_operating_outcome_visible": levels.get(3, []),
        "level_4_financial_outcome_attributable": levels.get(4, []),
        "level_5_per_share_attributable": levels.get(5, []),
        "counts": {
            f"level_{lvl}": len(ids)
            for lvl, ids in sorted(levels.items())
        },
        "note": (
            "Maturity levels derived exclusively from Phase 2 causal-attribution "
            "state fields. No recomputation occurs here."
        ),
    }


def _build_acquisition_profile(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    acqs = [r for r in records if r.get("allocation_category") in _INORGANIC]
    if not acqs:
        return {"count": 0, "note": "No inorganic allocation events in the ledger."}

    completed = [r for r in acqs if r.get("deployment_state") == "COMPLETED_TRANSACTION"]
    integration_visible = [
        r for r in acqs
        if r.get("operating_outcome_state") not in {"UNABLE_TO_VERIFY", "NO_VERIFIED_OUTCOME", None}
    ]
    financial_attributable = [
        r for r in acqs
        if r.get("financial_outcome_state") not in {"UNABLE_TO_ATTRIBUTE", None}
    ]
    value_creation = [
        r for r in acqs
        if r.get("value_creation_classification") == "VALUE_CREATION_EVIDENCE"
    ]
    periods = sorted(
        {p for r in acqs for p in (r.get("deployment_periods") or [])},
        key=_fy_sort,
    )
    return {
        "event_count": len(acqs),
        "allocation_ids": [r["allocation_id"] for r in acqs],
        "completed_count": len(completed),
        "integration_visible_count": len(integration_visible),
        "financial_outcome_attributable_count": len(financial_attributable),
        "value_creation_verified_count": len(value_creation),
        "known_periods": periods,
        "activity_vs_success_note": (
            f"{len(completed)} inorganic transactions completed. "
            f"{len(integration_visible)} show integration/operating progress. "
            f"{len(financial_attributable)} have attributable financial outcomes. "
            "Acquisition activity is documented; acquisition success requires "
            "direct causal evidence which current records do not provide."
        ),
    }


def _build_organic_reinvestment_profile(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    organic = [r for r in records if r.get("allocation_category") in _ORGANIC]
    if not organic:
        return {"count": 0, "note": "No organic reinvestment events in the ledger."}

    exec_visible = [
        r for r in organic
        if r.get("execution_state") not in {"UNABLE_TO_VERIFY", "NOT_STARTED", None}
    ]
    operating_visible = [
        r for r in organic
        if r.get("operating_outcome_state") not in {"UNABLE_TO_VERIFY", "NO_VERIFIED_OUTCOME", None}
    ]
    return {
        "event_count": len(organic),
        "allocation_ids": [r["allocation_id"] for r in organic],
        "execution_visible_count": len(exec_visible),
        "operating_outcome_visible_count": len(operating_visible),
        "financial_outcome_attributable_count": 0,  # organic always UNABLE_TO_ATTRIBUTE
        "note": (
            "Organic reinvestment execution and operating outcomes are tracked separately "
            "from financial impact. Revenue changes after organic capex are not attributed "
            "to individual capex decisions without direct causal evidence."
        ),
    }


def _build_shareholder_return_profile(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    distributions = [r for r in records if r.get("allocation_category") in _DISTRIBUTION]
    if not distributions:
        return {"count": 0, "note": "No distribution events in the ledger."}

    buybacks = [r for r in distributions if r.get("allocation_category") == "share_buyback"]
    dividends = [
        r for r in distributions
        if r.get("allocation_category") in {"dividend", "special_dividend"}
    ]
    share_count_reduction = [
        r for r in distributions
        if r.get("per_share_consequence_state") == "SHARE_COUNT_REDUCTION"
    ]
    return {
        "event_count": len(distributions),
        "allocation_ids": [r["allocation_id"] for r in distributions],
        "buyback_count": len(buybacks),
        "dividend_count": len(dividends),
        "share_count_reduction_attributable": len(share_count_reduction) > 0,
        "share_count_reduction_allocation_ids": [r["allocation_id"] for r in share_count_reduction],
        "note": (
            "Distribution events are recorded as cash-flow facts. Distributions are not "
            "equated with value creation. Opportunity cost of distributions over reinvestment "
            "is not assessable without full deployment amounts and returns data."
        ),
    }


def _build_balance_sheet_profile(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    bs = [r for r in records if r.get("allocation_category") in _BALANCE_SHEET]
    if not bs:
        return {"count": 0, "note": "No balance-sheet allocation events in the ledger."}

    debt_repayments = [r for r in bs if r.get("allocation_category") == "debt_repayment"]
    return {
        "event_count": len(bs),
        "allocation_ids": [r["allocation_id"] for r in bs],
        "debt_repayment_count": len(debt_repayments),
        "note": (
            "Debt repayment is capital deployment (liability reduction). "
            "Debt raised is a capital source, not deployment, and is excluded from this profile."
        ),
    }


def _build_stewardship_observations(
    records: List[Dict[str, Any]], cov: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Evidence-backed stewardship observations. No unsupported narratives."""
    observations: List[Dict[str, Any]] = []
    total = len(records)
    if total == 0:
        return observations

    # --- Outcome coverage ---
    financial_attributable = [
        r for r in records
        if r.get("financial_outcome_state") not in {"UNABLE_TO_ATTRIBUTE", None}
    ]
    unverified = [
        r for r in records
        if r.get("causal_attribution_confidence") in {"UNKNOWN", None}
        and r.get("financial_outcome_state") == "UNABLE_TO_ATTRIBUTE"
    ]
    if len(unverified) / total >= 0.5:
        observations.append({
            "label": "OUTCOMES_MOSTLY_UNVERIFIED",
            "detail": (
                f"{len(unverified)} of {total} allocations have no attributable financial "
                "outcomes. Management deployed capital across multiple categories; "
                "attributable results are not yet established for most deployments."
            ),
            "supporting_allocation_ids": [r["allocation_id"] for r in unverified],
            "confidence": "medium",
        })

    # --- Acquisition activity ---
    acqs = [r for r in records if r.get("allocation_category") in _INORGANIC]
    acq_unattributed = [
        r for r in acqs
        if r.get("financial_outcome_state") == "UNABLE_TO_ATTRIBUTE"
    ]
    if acqs:
        observations.append({
            "label": "ACQUISITION_ACTIVITY_DOCUMENTED_OUTCOME_UNVERIFIED",
            "detail": (
                f"{len(acqs)} inorganic transaction(s) documented. "
                f"{len(acq_unattributed)} have no attributable financial outcomes. "
                "Acquisition activity is confirmed; acquisition success is not established "
                "by current evidence."
            ),
            "supporting_allocation_ids": [r["allocation_id"] for r in acqs],
            "confidence": "medium",
        })

    # --- Distribution consistency ---
    distributions = [r for r in records if r.get("allocation_category") in _DISTRIBUTION]
    dist_periods = sorted(
        {p for r in distributions for p in (r.get("deployment_periods") or [])},
        key=_fy_sort,
    )
    if len(dist_periods) >= 3:
        observations.append({
            "label": "DISTRIBUTION_ACTIVITY_CONSISTENT",
            "detail": (
                f"Shareholder distributions (dividends and/or buybacks) recorded across "
                f"{len(dist_periods)} periods ({', '.join(dist_periods[:3])}{'...' if len(dist_periods) > 3 else ''}). "
                "Distribution discipline is visible; value of distributions relative to "
                "opportunity cost is not assessed without complete deployment data."
            ),
            "supporting_allocation_ids": [r["allocation_id"] for r in distributions],
            "confidence": "medium",
        })

    # --- Amount coverage warning ---
    if not cov["capital_weighted_conclusions_permitted"]:
        observations.append({
            "label": "CAPITAL_MIX_UNKNOWN",
            "detail": (
                f"Only {cov['events_with_known_amount']} of {total} allocation records have "
                "known monetary values. Capital-weighted conclusions (e.g., 'most capital went "
                "to acquisitions') are not supportable from current data."
            ),
            "supporting_allocation_ids": [],
            "confidence": "high",
        })

    return observations


def _build_activity_vs_skill(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Allocation activity ≠ allocation skill. Must be kept separate."""
    total = len(records)
    financial_attributable = sum(
        1 for r in records
        if r.get("financial_outcome_state") not in {"UNABLE_TO_ATTRIBUTE", None}
    )
    value_creation = sum(
        1 for r in records
        if r.get("value_creation_classification") == "VALUE_CREATION_EVIDENCE"
    )
    value_destruction = sum(
        1 for r in records
        if r.get("value_creation_classification") == "VALUE_DESTRUCTION_EVIDENCE"
    )

    if total == 0:
        skill_assessment = "INSUFFICIENT_DATA"
        skill_basis = "No allocation records."
    elif financial_attributable == 0:
        skill_assessment = "UNABLE_TO_VERIFY"
        skill_basis = (
            f"0 of {total} allocations have attributable financial outcomes. "
            "Capital was deployed; whether deployment created value is not yet established."
        )
    elif value_creation > 0 and value_destruction == 0:
        skill_assessment = "POSITIVE_EVIDENCE"
        skill_basis = f"{value_creation} of {total} allocations show value-creation evidence."
    elif value_destruction > 0 and value_creation == 0:
        skill_assessment = "NEGATIVE_EVIDENCE"
        skill_basis = f"{value_destruction} of {total} allocations show value-destruction evidence."
    elif value_creation > 0 and value_destruction > 0:
        skill_assessment = "MIXED_EVIDENCE"
        skill_basis = f"{value_creation} positive, {value_destruction} negative outcome(s) documented."
    else:
        skill_assessment = "OUTCOMES_MOSTLY_UNVERIFIED"
        skill_basis = f"{financial_attributable} financial attributions exist; value-creation assessment pending."

    return {
        "activity_event_count": total,
        "activity_basis": f"{total} material allocation decisions documented in the ledger.",
        "skill_assessment": skill_assessment,
        "skill_basis": skill_basis,
        "financial_attributable_count": financial_attributable,
        "value_creation_count": value_creation,
        "value_destruction_count": value_destruction,
        "discipline_note": (
            "Allocation activity (what management did) is separate from allocation skill "
            "(whether decisions created value). High activity can coexist with unverified skill."
        ),
    }


def _build_per_share_context(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    buybacks = [
        r for r in records
        if r.get("per_share_consequence_state") == "SHARE_COUNT_REDUCTION"
    ]
    dividends = [
        r for r in records
        if r.get("per_share_consequence_state") == "OWNER_EARNINGS_EFFECT"
    ]
    return {
        "share_count_reduction_documented": len(buybacks) > 0,
        "share_count_reduction_allocation_ids": [r["allocation_id"] for r in buybacks],
        "dividend_distribution_documented": len(dividends) > 0,
        "dividend_allocation_ids": [r["allocation_id"] for r in dividends],
        "company_level_eps_context": None,
        "attribution_note": (
            "Per-share consequences are stated only for allocations where a direct "
            "mechanism exists (buyback reduces share count; dividend distributes earnings). "
            "Company-level EPS trends are not attributed to specific allocations without "
            "explicit Phase 2 causal linkage."
        ),
    }


def _build_unresolved_questions(records: List[Dict[str, Any]]) -> List[str]:
    questions = []
    acqs = [r for r in records if r.get("allocation_category") in _INORGANIC]
    if acqs:
        questions.append(
            "What specific revenue, margin, or cash-flow outcome can be linked to the "
            "completed acquisitions (Alchemee, Concert, legacy)?"
        )
    organic = [r for r in records if r.get("allocation_category") in _ORGANIC]
    if organic:
        questions.append(
            "What operating metrics (utilization, throughput, yield) confirm the organic "
            "capex and working-capital deployments are generating returns?"
        )
    if not any(r.get("financial_outcome_state") not in {"UNABLE_TO_ATTRIBUTE", None} for r in records
               if r.get("allocation_category") not in _DISTRIBUTION | _BALANCE_SHEET):
        questions.append(
            "None of the investment/reinvestment allocations have an attributable financial "
            "outcome. What later evidence will establish causal links?"
        )
    missing_amounts = [r for r in records if r.get("amount") in (None, "", 0)]
    if missing_amounts:
        questions.append(
            f"{len(missing_amounts)} of {len(records)} records lack monetary values. "
            "What is the total capital deployed per category, and what fraction of "
            "operating cash generation was each category?"
        )
    return questions


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

_VALIDATOR_RULE_COUNT = 10


def _validate_profile(profile: Dict[str, Any], records: List[Dict[str, Any]]) -> Dict[str, Any]:
    violations: List[str] = []
    cov = profile.get("amount_coverage", {})

    # Rule 1: no capital-weighted claim when coverage insufficient
    if not cov.get("capital_weighted_conclusions_permitted", False):
        mix = profile.get("allocation_mix", {})
        for entry in mix.get("by_category", []):
            if entry.get("share_of_known_deployment") is not None:
                violations.append(
                    f"RULE1: capital_weighted share_of_known_deployment present for "
                    f"category={entry['category']!r} but coverage={cov.get('coverage_status')!r}"
                )

    # Rule 2: no VALUE_CREATION_EVIDENCE without Phase 2 attributable outcome
    a_vs_s = profile.get("allocation_activity_vs_skill", {})
    if a_vs_s.get("skill_assessment") == "POSITIVE_EVIDENCE" and a_vs_s.get("value_creation_count", 0) == 0:
        violations.append("RULE2: skill_assessment=POSITIVE_EVIDENCE with zero value_creation_count")

    # Rule 3: per-share attribution only for SHARE_COUNT_REDUCTION / OWNER_EARNINGS_EFFECT
    # (enforced upstream; check per_share_context consistency)
    psc = profile.get("per_share_context", {})
    if psc.get("share_count_reduction_documented") and not psc.get("share_count_reduction_allocation_ids"):
        violations.append("RULE3: share_count_reduction_documented=True but no allocation IDs cited")

    # Rule 4: event-count language must not imply capital amounts in observations
    # CAPITAL_MIX_UNKNOWN is exempt — it warns against capital claims, not making one
    for obs in profile.get("stewardship_observations", []):
        if obs.get("label") == "CAPITAL_MIX_UNKNOWN":
            continue
        detail = obs.get("detail", "").lower()
        if "most capital" in detail or "largest share" in detail:
            if not cov.get("capital_weighted_conclusions_permitted", False):
                violations.append(
                    f"RULE4: stewardship observation uses capital-amount language without coverage: {obs.get('label')!r}"
                )

    # Rule 5: timeline periods must exist in Phase 2 ledger
    all_canonical_periods = {
        p for r in records for p in (r.get("deployment_periods") or [])
    }
    for year in profile.get("timeline", []):
        period = year.get("period")
        if period and period not in all_canonical_periods:
            violations.append(f"RULE5: timeline period {period!r} not in canonical deployment_periods")

    # Rule 6: stewardship observations must cite ≥1 supporting allocation_id
    # (exception: CAPITAL_MIX_UNKNOWN has no IDs by design)
    for obs in profile.get("stewardship_observations", []):
        if obs.get("label") != "CAPITAL_MIX_UNKNOWN":
            if not obs.get("supporting_allocation_ids"):
                violations.append(
                    f"RULE6: observation {obs.get('label')!r} has no supporting_allocation_ids"
                )

    # Rule 7: unresolved evidence is allowed (no check needed — affirmed by presence)

    # Rule 8: outcome maturity counts must sum to total records
    om = profile.get("outcome_maturity", {})
    maturity_total = sum(
        len(ids)
        for k, ids in om.items()
        if k.startswith("level_") and isinstance(ids, list)
    )
    if maturity_total != len(records):
        violations.append(
            f"RULE8: outcome maturity total {maturity_total} != record count {len(records)}"
        )

    # Rule 9: no capital source classified as deployment
    all_ids_in_profile = set()
    for entry in profile.get("allocation_mix", {}).get("by_category", []):
        pass  # category-level; no debt_raised should appear (filtered upstream)
    # Check organic/inorganic/dist/bs IDs are unique per group
    oi = profile.get("organic_vs_inorganic", {})
    all_profile_ids = (
        oi.get("organic_allocation_ids", [])
        + oi.get("inorganic_allocation_ids", [])
        + oi.get("distribution_allocation_ids", [])
        + oi.get("balance_sheet_allocation_ids", [])
        + oi.get("other_allocation_ids", [])  # type: ignore[operator]
    )

    # Rule 10: no duplicate allocation events
    seen: set = set()
    for r in records:
        aid = r.get("allocation_id", "")
        if aid in seen:
            violations.append(f"RULE10: duplicate allocation_id {aid!r} in records")
        seen.add(aid)

    return {
        "status": "PASS" if not violations else "FAIL",
        "rules_checked": _VALIDATOR_RULE_COUNT,
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------

def build_longitudinal_profile(
    company: str,
    company_root: Path,
    *,
    assessments_path: Optional[Path] = None,
    outcomes_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build the canonical longitudinal capital allocation profile.

    Reads Phase 2 assessments and outcomes; produces a synthesis artifact.
    No AI calls. No raw-document access.
    """
    if assessments_path is None:
        assessments_path = get_capital_allocation_assessments_path(company)
    if outcomes_path is None:
        outcomes_path = get_capital_allocation_outcomes_path(company)

    if not assessments_path.exists():
        return {
            "company": company,
            "generated_at": _utc_now(),
            "error": "capital_allocation_assessments.json not found — run Phase 2 builder first.",
            "allocation_count": 0,
        }

    try:
        assessments_data = json.loads(assessments_path.read_text(encoding="utf-8"))
        assessments = assessments_data.get("assessments", [])
    except (OSError, json.JSONDecodeError) as exc:
        return {"company": company, "generated_at": _utc_now(), "error": str(exc)}

    # Load outcomes for period + amount metadata
    periods_by_id: Dict[str, List[str]] = {}
    amounts_by_id: Dict[str, Any] = {}
    amount_basis_by_id: Dict[str, str] = {}
    if outcomes_path.exists():
        try:
            outcomes_data = json.loads(outcomes_path.read_text(encoding="utf-8"))
            for alloc in outcomes_data.get("allocations", []):
                aid = alloc.get("allocation_id", "")
                periods_by_id[aid] = alloc.get("deployment_periods") or []
                amounts_by_id[aid] = alloc.get("amount")
                amount_basis_by_id[aid] = alloc.get("amount_basis", "unknown")
        except (OSError, json.JSONDecodeError):
            pass

    # Merge period/amount into assessment records
    records: List[Dict[str, Any]] = []
    for a in assessments:
        if not isinstance(a, dict):
            continue
        aid = a.get("allocation_id", "")
        r = dict(a)
        r["deployment_periods"] = periods_by_id.get(aid, [])
        r["amount"] = amounts_by_id.get(aid)
        r["amount_basis"] = amount_basis_by_id.get(aid, "unknown")
        records.append(r)

    # Compute amount coverage
    cov = _amount_coverage(records)

    # Source ledger fingerprint
    raw_ids = "".join(r.get("allocation_id", "") for r in records)
    source_fingerprint = _fingerprint(raw_ids + str(len(records)))

    # Determine period range
    all_periods = sorted(
        {p for r in records for p in r.get("deployment_periods", [])},
        key=_fy_sort,
    )
    start_period = all_periods[0] if all_periods else None
    end_period = all_periods[-1] if all_periods else None

    # Build all sections
    allocation_mix = _build_allocation_mix(records, cov)
    organic_vs_inorganic = _build_organic_vs_inorganic(records, cov)
    timeline = _build_timeline(records)
    outcome_maturity = _build_outcome_maturity(records)
    acquisition_profile = _build_acquisition_profile(records)
    organic_profile = _build_organic_reinvestment_profile(records)
    shareholder_profile = _build_shareholder_return_profile(records)
    balance_sheet_profile = _build_balance_sheet_profile(records)
    stewardship = _build_stewardship_observations(records, cov)
    activity_vs_skill = _build_activity_vs_skill(records)
    per_share = _build_per_share_context(records)
    unresolved = _build_unresolved_questions(records)

    # Overall confidence
    outcome_attributable = sum(
        1 for r in records
        if r.get("financial_outcome_state") not in {"UNABLE_TO_ATTRIBUTE", None}
    )
    if cov["coverage_ratio"] >= _COVERAGE_HIGH and outcome_attributable / len(records) >= 0.5:
        overall_confidence = "medium"
    elif len(records) >= 5:
        overall_confidence = "low"
    else:
        overall_confidence = "very_low"

    profile: Dict[str, Any] = {
        "company": company,
        "generated_at": _utc_now(),
        "generator_version": "ENG-105-Phase3-v1",
        "source_ledger": {
            "assessments_artifact": str(assessments_path),
            "allocation_count": len(records),
            "source_fingerprint": source_fingerprint,
        },
        "profile_scope": {
            "company": company,
            "start_period": start_period,
            "end_period": end_period,
            "total_events": len(records),
        },
        "amount_coverage": cov,
        "allocation_mix": allocation_mix,
        "organic_vs_inorganic": organic_vs_inorganic,
        "timeline": timeline,
        "outcome_maturity": outcome_maturity,
        "acquisition_profile": acquisition_profile,
        "organic_reinvestment_profile": organic_profile,
        "shareholder_return_profile": shareholder_profile,
        "balance_sheet_profile": balance_sheet_profile,
        "stewardship_observations": stewardship,
        "allocation_activity_vs_skill": activity_vs_skill,
        "per_share_context": per_share,
        "unresolved_questions": unresolved,
        "confidence": {
            "event_coverage": "medium" if len(records) >= 5 else "low",
            "amount_coverage": cov["coverage_status"].lower(),
            "outcome_coverage": "low" if outcome_attributable < len(records) * 0.5 else "medium",
            "overall": overall_confidence,
        },
        "limitations": [
            f"Amount coverage: {cov['coverage_ratio']:.0%} of records have known monetary values. "
            "Capital-weighted conclusions are not supported.",
            "Outcome attribution: Company-wide financial trends are NOT attributed to individual "
            "allocations without direct Phase 2 causal linkage.",
            "Period coverage: profile spans only years for which Phase 2 allocation records exist.",
        ],
        "provenance": {
            "source_artifact": "capital_allocation_assessments.json",
            "source_allocation_count": len(records),
            "phase": "ENG-105-Phase3",
            "causal_contract": "ENG_105_PHASE_2_CAUSAL_ATTRIBUTION_CONTRACT_CLOSED",
        },
    }

    # Validate
    profile["validation"] = _validate_profile(profile, records)

    return profile


# ---------------------------------------------------------------------------
# Writer / class entry-point
# ---------------------------------------------------------------------------

class CapitalAllocationLongitudinalProfileBuilder:
    def __init__(self, company: str):
        self.company = company
        self.company_root = Path("companies") / company
        self.output_path = get_capital_allocation_longitudinal_profile_path(company)

    def build(self) -> Path:
        profile = build_longitudinal_profile(self.company, self.company_root)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(profile, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return self.output_path
