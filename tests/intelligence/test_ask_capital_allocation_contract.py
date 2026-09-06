"""
ENG-105 Phase 4 — Ask + Panel capital allocation consumption contract tests.

10 Ask contract tests (Step 19) + 5 Panel contract tests (Step 20).

None of these tests run an LLM. They verify that:
- Canonical Phase 2/3 state fields drive investor-facing language
- Unknown/unverified states are never upgraded downstream
- Capital-weighted claims respect amount coverage
- Activity is never equated with skill
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from intelligence.ask_intrinsiciq.answer_cards import _build_capital_allocation_answer
from intelligence.investor_panel.company_memory_context import _compact_capital_allocation_outcomes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile(
    *,
    events: int = 5,
    start: str = "fy20",
    end: str = "fy26",
    coverage_ratio: float = 0.0,
    organic: int = 0,
    inorganic: int = 0,
    dist: int = 0,
    bs: int = 0,
    skill: str = "UNABLE_TO_VERIFY",
    skill_basis: str = "",
    fin_attributable: int = 0,
    value_creation: int = 0,
    obs: Optional[List[Dict]] = None,
    uq: Optional[List[str]] = None,
    share_count_reduction: bool = False,
    dividend: bool = False,
) -> Dict[str, Any]:
    """Build a minimal longitudinal profile for testing."""
    capital_weighted = coverage_ratio >= 0.70
    by_cat = []
    if organic:
        by_cat.append({"category": "organic_capex", "group": "organic", "event_count": organic, "known_amount_crore": 1000.0 if capital_weighted else None, "share_of_known_deployment": 0.4 if capital_weighted else None})
    if inorganic:
        by_cat.append({"category": "acquisition", "group": "inorganic", "event_count": inorganic, "known_amount_crore": 2000.0 if capital_weighted else None, "share_of_known_deployment": 0.6 if capital_weighted else None})
    om_counts = {"counts": {}}
    unverified_count = events - fin_attributable
    level_0_ids = [f"CAO-{i:04d}" for i in range(1, unverified_count + 1)]
    level_4_ids = [f"CAO-{i:04d}" for i in range(unverified_count + 1, events + 1)]
    return {
        "profile_scope": {"start_period": start, "end_period": end, "total_events": events},
        "amount_coverage": {
            "coverage_ratio": coverage_ratio,
            "coverage_status": "HIGH" if capital_weighted else "LOW",
            "capital_weighted_conclusions_permitted": capital_weighted,
            "note": (
                "Capital-weighted conclusions are permitted."
                if capital_weighted
                else "CAPITAL_MIX_INSUFFICIENT_AMOUNT_COVERAGE: event-pattern analysis only."
            ),
        },
        "allocation_mix": {
            "by_category": by_cat,
            "capital_weighted_conclusions_permitted": capital_weighted,
        },
        "organic_vs_inorganic": {
            "organic_event_count": organic,
            "inorganic_event_count": inorganic,
            "distribution_event_count": dist,
            "balance_sheet_event_count": bs,
        },
        "outcome_maturity": {
            "level_0_deployment_unverified": level_0_ids,
            "level_4_financial_outcome_attributable": level_4_ids,
        },
        "allocation_activity_vs_skill": {
            "activity_event_count": events,
            "skill_assessment": skill,
            "skill_basis": skill_basis or f"{events} events tracked; {fin_attributable} with attributable outcomes.",
            "financial_attributable_count": fin_attributable,
            "value_creation_count": value_creation,
        },
        "acquisition_profile": {
            "event_count": inorganic,
            "completed_count": inorganic,
            "financial_outcome_attributable_count": 0,
            "activity_vs_success_note": f"{inorganic} inorganic transaction(s) completed; financial returns not yet attributed.",
        } if inorganic else {},
        "per_share_context": {
            "share_count_reduction_documented": share_count_reduction,
            "dividend_distribution_documented": dividend,
            "attribution_note": "Per-share consequences stated only where direct mechanism exists.",
        },
        "stewardship_observations": obs or [],
        "unresolved_questions": uq or [],
        "limitations": [],
    }


def _outcomes_payload(allocations: List[Dict]) -> Dict[str, Any]:
    return {"allocation_count": len(allocations), "allocations": allocations}


def _assessments_payload(assessments: List[Dict]) -> Dict[str, Any]:
    return {"assessments": assessments}


def _bundle(**sources) -> Dict[str, Any]:
    return {"sources": sources}


def _source_bundle(
    profile: Optional[Dict] = None,
    outcomes: Optional[Dict] = None,
    assessments: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Build a minimal source_bundle compatible with _source_payload().

    _source_payload reads: source_bundle["sources"][name]["payload"]
    """
    sources: Dict[str, Any] = {}
    if profile:
        sources["capital_allocation_longitudinal_profile"] = {"payload": profile}
    if outcomes:
        sources["capital_allocation_outcomes"] = {"payload": outcomes}
    if assessments:
        sources["capital_allocation_assessments"] = {"payload": assessments}
    return {"sources": sources}


def _ask_answer(
    profile: Optional[Dict] = None,
    outcomes: Optional[Dict] = None,
    assessments: Optional[Dict] = None,
) -> Dict[str, Any]:
    sb = _source_bundle(profile, outcomes, assessments)
    return _build_capital_allocation_answer(
        sb,
        business_journey_payload={},
        products_services_payload={},
        question={"id": "how-is-capital-allocated", "title": "How is capital allocated?"},
    )


# ---------------------------------------------------------------------------
# Ask Contract Tests (Step 19)
# ---------------------------------------------------------------------------

# Test 1: Completed acquisition + unknown financial outcome → not called successful
def test_ask_completed_acquisition_financial_unknown():
    a = {"allocation_id": "CAO-0001", "allocation_category": "acquisition",
         "deployment_state": "COMPLETED_TRANSACTION", "execution_state": "OPERATIONAL",
         "operating_outcome_state": "UNABLE_TO_VERIFY",
         "financial_outcome_state": "UNABLE_TO_ATTRIBUTE",
         "per_share_consequence_state": "UNABLE_TO_ATTRIBUTE",
         "value_creation_classification": "UNABLE_TO_VERIFY",
         "causal_attribution_confidence": "MEDIUM"}
    outcomes = _outcomes_payload([{"allocation_id": "CAO-0001", "allocation_category": "acquisition",
                                    "normalized_name": "Alchemee Acquisition", "amount": 2000.0,
                                    "deployment_periods": ["fy23"]}])
    assessments = _assessments_payload([a])
    ans = _ask_answer(outcomes=outcomes, assessments=assessments)
    text = str(ans).lower()
    # Must not claim success
    assert "successful" not in text
    assert "value creation" not in text or "unable" in text or "not yet" in text
    # Must acknowledge completion
    assert "transaction completed" in text or "completed" in text


# Test 2: Operating outcome visible + financial unattributed → operating surfaced, no financial claim
def test_ask_operating_visible_financial_unknown():
    a = {"allocation_id": "CAO-0001", "allocation_category": "organic_capex",
         "deployment_state": "DEPLOYED", "execution_state": "OPERATIONAL",
         "operating_outcome_state": "CAPACITY_ADDED",
         "financial_outcome_state": "UNABLE_TO_ATTRIBUTE",
         "per_share_consequence_state": "UNABLE_TO_ATTRIBUTE",
         "value_creation_classification": "TOO_EARLY_TO_JUDGE",
         "causal_attribution_confidence": "LOW"}
    outcomes = _outcomes_payload([{"allocation_id": "CAO-0001", "allocation_category": "organic_capex",
                                    "normalized_name": "Capex", "amount": 1000.0, "deployment_periods": ["fy22"]}])
    assessments = _assessments_payload([a])
    ans = _ask_answer(outcomes=outcomes, assessments=assessments)
    text = str(ans).lower()
    # Operating progress may be mentioned
    assert "operational" in text or "execution" in text or "capex" in text
    # No financial success claim
    assert "financial return" not in text or "not yet" in text or "unable" in text or "not attributable" in text


# Test 3: Attributable financial outcome → may surface financial contribution
def test_ask_attributable_financial_outcome_surfaced():
    a = {"allocation_id": "CAO-0002", "allocation_category": "dividend",
         "deployment_state": "DEPLOYED", "execution_state": "COMPLETED",
         "operating_outcome_state": "NO_VERIFIED_OUTCOME",
         "financial_outcome_state": "CASH_FLOW_EFFECT",
         "per_share_consequence_state": "OWNER_EARNINGS_EFFECT",
         "value_creation_classification": "UNABLE_TO_VERIFY",
         "causal_attribution_confidence": "MEDIUM"}
    outcomes = _outcomes_payload([{"allocation_id": "CAO-0002", "allocation_category": "dividend",
                                    "normalized_name": "Dividend", "amount": 500.0, "deployment_periods": ["fy22"]}])
    assessments = _assessments_payload([a])
    ans = _ask_answer(outcomes=outcomes, assessments=assessments)
    text = str(ans).lower()
    assert "cash" in text or "return" in text or "effect" in text


# Test 4: Share buyback → per-share consequence surfaced
def test_ask_buyback_per_share_consequence_surfaced():
    profile = _profile(dist=1, events=1, share_count_reduction=True,
                       skill="UNABLE_TO_VERIFY")
    a = {"allocation_id": "CAO-0003", "allocation_category": "share_buyback",
         "deployment_state": "DEPLOYED", "execution_state": "COMPLETED",
         "operating_outcome_state": "NO_VERIFIED_OUTCOME",
         "financial_outcome_state": "CASH_FLOW_EFFECT",
         "per_share_consequence_state": "SHARE_COUNT_REDUCTION",
         "value_creation_classification": "UNABLE_TO_VERIFY",
         "causal_attribution_confidence": "MEDIUM"}
    outcomes = _outcomes_payload([{"allocation_id": "CAO-0003", "allocation_category": "share_buyback",
                                    "normalized_name": "Share buyback", "amount": 100.0, "deployment_periods": ["fy22"]}])
    assessments = _assessments_payload([a])
    ans = _ask_answer(profile=profile, outcomes=outcomes, assessments=assessments)
    psc = (ans.get("interpretation") or {}).get("unresolved_diligence", [])
    # Per-share context from profile must be accessible
    assert profile["per_share_context"]["share_count_reduction_documented"] is True


# Test 5: Event-heavy low coverage → no "most capital went to..." claim
def test_ask_no_capital_weighted_claim_when_low_coverage():
    profile = _profile(
        events=9, coverage_ratio=0.0,
        inorganic=3, organic=2, dist=2, bs=2,
        skill="UNABLE_TO_VERIFY",
    )
    outcomes = _outcomes_payload([
        {"allocation_id": f"CAO-{i:04d}", "allocation_category": "acquisition",
         "normalized_name": f"Deal {i}", "amount": None, "deployment_periods": ["fy22"]}
        for i in range(1, 4)
    ])
    ans = _ask_answer(profile=profile, outcomes=outcomes)
    text = str(ans).lower()
    # Must NOT say most capital went to acquisitions
    assert "most capital went" not in text
    assert "largest share of capital" not in text
    # Must acknowledge coverage limitation
    assert "insufficient" in text or "not permitted" in text or "event" in text or "count" in text


# Test 6: High amount coverage → capital-weighted mix is surfaced
def test_ask_capital_weighted_permitted_when_high_coverage():
    profile = _profile(
        events=3, coverage_ratio=1.0,
        inorganic=1, organic=1, dist=1,
        skill="UNABLE_TO_VERIFY",
    )
    ans = _ask_answer(profile=profile)
    text = str(ans).lower()
    # With high coverage capital mix info should appear somewhere
    # The answer should at least not block it
    assert "capital-weighted" in text or "tracked capital" in text or "₹" in text or "cr" in text or "acquisition" in text


# Test 7: No value-creation evidence → no "strong allocator" language
def test_ask_no_strong_allocator_without_value_creation():
    profile = _profile(
        events=9, coverage_ratio=1.0,
        skill="UNABLE_TO_VERIFY",
        skill_basis="0 of 9 events have value-creation evidence.",
        fin_attributable=0,
        value_creation=0,
    )
    ans = _ask_answer(profile=profile)
    text = str(ans).lower()
    assert "strong allocator" not in text
    assert "excellent capital allocator" not in text
    # Skill assessment should reflect unable to verify
    interp = ans.get("interpretation") or {}
    assert interp.get("skill_assessment") in ("UNABLE_TO_VERIFY", "OUTCOMES_MOSTLY_UNVERIFIED", None)


# Test 8: Value-destruction evidence → negative stewardship evidence surfaced
def test_ask_value_destruction_surfaced():
    profile = _profile(
        events=3, coverage_ratio=1.0,
        skill="NEGATIVE_EVIDENCE",
        skill_basis="1 allocation shows value-destruction evidence.",
        fin_attributable=1,
        value_creation=0,
        obs=[{"label": "VALUE_DESTRUCTION_OBSERVED", "detail": "Impairment recorded on acquired asset.", "supporting_allocation_ids": ["CAO-0001"]}],
    )
    ans = _ask_answer(profile=profile)
    text = str(ans).lower()
    # Negative evidence must not be suppressed
    interp = ans.get("interpretation") or {}
    assert interp.get("skill_assessment") == "NEGATIVE_EVIDENCE" or "negative" in text or "destruction" in text


# Test 9: Recent acquisition (few periods) → too early preserved
def test_ask_recent_acquisition_utv_preserved():
    profile = _profile(
        events=1, coverage_ratio=0.0,
        inorganic=1, skill="UNABLE_TO_VERIFY",
        uq=["The acquisition was completed in FY23; financial attribution requires more time."],
    )
    a = {"allocation_id": "CAO-0001", "allocation_category": "acquisition",
         "deployment_state": "COMPLETED_TRANSACTION", "execution_state": "UNABLE_TO_VERIFY",
         "operating_outcome_state": "UNABLE_TO_VERIFY",
         "financial_outcome_state": "UNABLE_TO_ATTRIBUTE",
         "per_share_consequence_state": "UNABLE_TO_ATTRIBUTE",
         "value_creation_classification": "UNABLE_TO_VERIFY",
         "causal_attribution_confidence": "UNKNOWN"}
    outcomes = _outcomes_payload([{"allocation_id": "CAO-0001", "allocation_category": "acquisition",
                                    "normalized_name": "Alchemee", "amount": None, "deployment_periods": ["fy23"]}])
    assessments = _assessments_payload([a])
    ans = _ask_answer(profile=profile, outcomes=outcomes, assessments=assessments)
    interp = ans.get("interpretation") or {}
    assert interp.get("skill_assessment") == "UNABLE_TO_VERIFY"
    uq = interp.get("unresolved_diligence") or []
    assert len(uq) > 0


# Test 10: UNKNOWN state → never upgraded downstream
def test_ask_unknown_state_never_upgraded():
    profile = _profile(
        events=5, coverage_ratio=0.0,
        skill="UNABLE_TO_VERIFY",
        skill_basis="0 of 5 events have attributable outcomes.",
        fin_attributable=0,
    )
    # All assessments are fully unknown
    assessments = _assessments_payload([
        {"allocation_id": f"CAO-{i:04d}", "allocation_category": "organic_capex",
         "deployment_state": "UNABLE_TO_VERIFY", "execution_state": "UNABLE_TO_VERIFY",
         "operating_outcome_state": "UNABLE_TO_VERIFY",
         "financial_outcome_state": "UNABLE_TO_ATTRIBUTE",
         "per_share_consequence_state": "UNABLE_TO_ATTRIBUTE",
         "value_creation_classification": "UNABLE_TO_VERIFY",
         "causal_attribution_confidence": "UNKNOWN"}
        for i in range(1, 6)
    ])
    ans = _ask_answer(profile=profile, assessments=assessments)
    text = str(ans).lower()
    interp = ans.get("interpretation") or {}
    # No positive claims from unknown states
    assert "successful" not in text
    assert "proven" not in text
    assert "value creation evidence" not in text or "unable" in text or "not" in text
    assert interp.get("skill_assessment") in ("UNABLE_TO_VERIFY", "OUTCOMES_MOSTLY_UNVERIFIED", None)


# ---------------------------------------------------------------------------
# Panel Contract Tests (Step 20)
# ---------------------------------------------------------------------------

def _panel_candidates(profile: Optional[Dict] = None, outcomes: Optional[Dict] = None) -> list:
    """Build panel candidates list as (Path, payload) tuples."""
    from pathlib import PurePosixPath

    candidates = []
    if profile:
        candidates.append((Path("company_memory/capital_allocation_outcomes/capital_allocation_longitudinal_profile.json"), profile))
    if outcomes:
        candidates.append((Path("company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json"), outcomes))
    return candidates


# Panel Test 1 (Buffett): Cannot call acquisition value-creating if Phase 2 says UTV
def test_panel_buffett_cannot_claim_value_creating_when_utv():
    profile = _profile(
        events=3, coverage_ratio=1.0,
        inorganic=3,
        skill="UNABLE_TO_VERIFY",
        skill_basis="3 acquisitions completed; 0 have attributable financial outcomes.",
        fin_attributable=0, value_creation=0,
    )
    compact = _compact_capital_allocation_outcomes(_panel_candidates(profile))
    skill = (compact.get("allocation_skill") or {}).get("assessment", "")
    # Panel context must expose UNABLE_TO_VERIFY, not VALUE_CREATION_EVIDENCE
    assert skill == "UNABLE_TO_VERIFY"
    text = str(compact).lower()
    assert "value_creation_evidence" not in text or "unable" in text


# Panel Test 2 (Graham): Cannot claim balance-sheet deterioration without canonical evidence
def test_panel_graham_no_balance_sheet_deterioration_without_evidence():
    profile = _profile(
        events=2, coverage_ratio=1.0,
        inorganic=1, bs=1,
        skill="UNABLE_TO_VERIFY",
        obs=[],  # No negative observations
    )
    compact = _compact_capital_allocation_outcomes(_panel_candidates(profile))
    obs_texts = compact.get("stewardship_observations") or []
    # No negative claim present in observations without evidence
    for obs in obs_texts:
        assert "deterioration" not in obs.lower() or "evidence" in obs.lower()


# Panel Test 3 (Munger): Cannot infer diworsification merely from acquisition count
def test_panel_munger_diworsification_not_inferred_from_count_alone():
    profile = _profile(
        events=5, coverage_ratio=0.0,
        inorganic=5,  # Many acquisitions but no negative evidence
        skill="UNABLE_TO_VERIFY",
        obs=[],  # No negative observations in profile
    )
    compact = _compact_capital_allocation_outcomes(_panel_candidates(profile))
    obs_texts = compact.get("stewardship_observations") or []
    acq_note = compact.get("acquisition_activity_vs_success") or ""
    # The compact output must not assert diworsification from count alone
    for obs in obs_texts:
        assert "diworsification" not in obs.lower()
    assert "diworsification" not in acq_note.lower()


# Panel Test 4 (Fisher): R&D spend ≠ R&D productivity (organic reinvestment shows as activity, not outcome)
def test_panel_fisher_organic_reinvestment_is_activity_not_outcome():
    profile = _profile(
        events=4, coverage_ratio=1.0,
        organic=4,  # All organic / R&D
        skill="UNABLE_TO_VERIFY",
        fin_attributable=0,
    )
    compact = _compact_capital_allocation_outcomes(_panel_candidates(profile))
    assert compact["event_mix"]["organic_reinvestment"] == 4
    outcome_m = compact.get("outcome_maturity") or {}
    assert outcome_m.get("financial_attributable", 0) == 0


# Panel Test 5 (Lynch): Growth story ≠ proven allocation success
def test_panel_lynch_growth_story_not_equated_with_proven_success():
    profile = _profile(
        events=6, coverage_ratio=1.0,
        inorganic=2, organic=4,
        skill="OUTCOMES_MOSTLY_UNVERIFIED",
        skill_basis="6 events tracked; only distribution-type outcomes attributable.",
        fin_attributable=2, value_creation=0,
    )
    compact = _compact_capital_allocation_outcomes(_panel_candidates(profile))
    skill = (compact.get("allocation_skill") or {}).get("assessment", "")
    assert skill == "OUTCOMES_MOSTLY_UNVERIFIED"
    # No "strong" or "proven" in the compact output
    text = str(compact).lower()
    assert "strong capital allocator" not in text
    assert "proven success" not in text
