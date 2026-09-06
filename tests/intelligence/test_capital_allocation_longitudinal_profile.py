"""
ENG-105 Phase 3 — Adversarial tests for the longitudinal capital allocation
profile builder.

15 tests total. All are adversarial: they verify that the builder does NOT
produce capital-weighted conclusions when amounts are missing, does NOT
conflate chronology with causality, and correctly separates allocation activity
from allocation skill.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from intelligence.capital_allocation_outcomes.longitudinal_profile import (
    _amount_coverage,
    _build_acquisition_profile,
    _build_activity_vs_skill,
    _build_allocation_mix,
    _build_organic_vs_inorganic,
    _build_outcome_maturity,
    _build_per_share_context,
    _build_shareholder_return_profile,
    _build_stewardship_observations,
    _build_timeline,
    _maturity_level,
    _validate_profile,
    build_longitudinal_profile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rec(
    *,
    allocation_id: str = "CAO-0001",
    category: str = "organic_capex",
    dep_state: str = "UNABLE_TO_VERIFY",
    exe_state: str = "UNABLE_TO_VERIFY",
    oos: str = "UNABLE_TO_VERIFY",
    fos: str = "UNABLE_TO_ATTRIBUTE",
    pss: str = "UNABLE_TO_ATTRIBUTE",
    vcc: str = "UNABLE_TO_VERIFY",
    cac: str = "UNKNOWN",
    amount: Any = None,
    periods: List[str] | None = None,
    return_evidence: List[Any] | None = None,
) -> Dict[str, Any]:
    return {
        "allocation_id": allocation_id,
        "allocation_category": category,
        "deployment_state": dep_state,
        "execution_state": exe_state,
        "operating_outcome_state": oos,
        "financial_outcome_state": fos,
        "per_share_consequence_state": pss,
        "value_creation_classification": vcc,
        "causal_attribution_confidence": cac,
        "amount": amount,
        "deployment_periods": periods or [],
        "return_evidence": return_evidence or [],
    }


# ---------------------------------------------------------------------------
# Test 1: zero amount coverage blocks capital-weighted conclusions
# ---------------------------------------------------------------------------

def test_zero_amount_coverage_blocks_capital_weighted():
    records = [_rec(allocation_id=f"CAO-{i:04d}", amount=None) for i in range(1, 10)]
    cov = _amount_coverage(records)
    assert cov["capital_weighted_conclusions_permitted"] is False
    assert cov["coverage_status"] == "LOW"
    assert "CAPITAL_MIX_INSUFFICIENT_AMOUNT_COVERAGE" in cov["note"]


# ---------------------------------------------------------------------------
# Test 2: event-count mix must not rank capital when coverage is LOW
# ---------------------------------------------------------------------------

def test_allocation_mix_no_capital_rank_when_low_coverage():
    records = [
        _rec(allocation_id="CAO-0001", category="acquisition", amount=None),
        _rec(allocation_id="CAO-0002", category="organic_capex", amount=None),
        _rec(allocation_id="CAO-0003", category="dividend", amount=None),
    ]
    cov = _amount_coverage(records)
    mix = _build_allocation_mix(records, cov)
    for entry in mix["by_category"]:
        assert entry["share_of_known_deployment"] is None, (
            f"category={entry['category']!r} has a capital share despite low coverage"
        )


# ---------------------------------------------------------------------------
# Test 3: high amount coverage permits capital-weighted conclusions
# ---------------------------------------------------------------------------

def test_high_amount_coverage_permits_capital_weighted():
    records = [
        _rec(allocation_id=f"CAO-{i:04d}", amount=100.0 * i) for i in range(1, 8)
    ]
    cov = _amount_coverage(records)
    assert cov["capital_weighted_conclusions_permitted"] is True
    assert cov["coverage_status"] == "HIGH"


# ---------------------------------------------------------------------------
# Test 4: maturity level 0 when deployment is UNABLE_TO_VERIFY
# ---------------------------------------------------------------------------

def test_maturity_level_0_when_deployment_unverified():
    r = _rec(dep_state="UNABLE_TO_VERIFY")
    assert _maturity_level(r) == 0


# ---------------------------------------------------------------------------
# Test 5: maturity does not exceed 4 without per-share attribution
# ---------------------------------------------------------------------------

def test_maturity_level_4_without_per_share():
    r = _rec(
        dep_state="DEPLOYED",
        exe_state="COMPLETED",
        oos="CAPACITY_ADDED",
        fos="CASH_FLOW_EFFECT",
        pss="UNABLE_TO_ATTRIBUTE",
    )
    assert _maturity_level(r) == 4


# ---------------------------------------------------------------------------
# Test 6: maturity 5 only when per-share is attributable
# ---------------------------------------------------------------------------

def test_maturity_level_5_with_per_share():
    r = _rec(
        dep_state="DEPLOYED",
        exe_state="COMPLETED",
        oos="CAPACITY_ADDED",
        fos="CASH_FLOW_EFFECT",
        pss="SHARE_COUNT_REDUCTION",
    )
    assert _maturity_level(r) == 5


# ---------------------------------------------------------------------------
# Test 7: acquisition activity documented ≠ acquisition success verified
# ---------------------------------------------------------------------------

def test_acquisition_activity_vs_success_separated():
    records = [
        _rec(allocation_id="CAO-0001", category="acquisition",
             dep_state="COMPLETED_TRANSACTION", exe_state="OPERATIONAL",
             fos="UNABLE_TO_ATTRIBUTE"),
    ]
    profile = _build_acquisition_profile(records)
    note = profile["activity_vs_success_note"].lower()
    assert "success" in note or "outcome" in note
    assert profile["financial_outcome_attributable_count"] == 0


# ---------------------------------------------------------------------------
# Test 8: OUTCOMES_MOSTLY_UNVERIFIED observation fires when ≥50% unverified
# ---------------------------------------------------------------------------

def test_stewardship_outcomes_mostly_unverified():
    records = [
        _rec(allocation_id="CAO-0001", fos="UNABLE_TO_ATTRIBUTE", cac="UNKNOWN"),
        _rec(allocation_id="CAO-0002", fos="UNABLE_TO_ATTRIBUTE", cac="UNKNOWN"),
        _rec(allocation_id="CAO-0003", fos="CASH_FLOW_EFFECT", cac="MEDIUM"),
    ]
    cov = _amount_coverage(records)
    obs = _build_stewardship_observations(records, cov)
    labels = [o["label"] for o in obs]
    assert "OUTCOMES_MOSTLY_UNVERIFIED" in labels


# ---------------------------------------------------------------------------
# Test 9: activity vs skill — UNABLE_TO_VERIFY when no attributable outcomes
# ---------------------------------------------------------------------------

def test_activity_vs_skill_unable_to_verify_when_no_outcomes():
    records = [
        _rec(allocation_id="CAO-0001", fos="UNABLE_TO_ATTRIBUTE", vcc="UNABLE_TO_VERIFY"),
        _rec(allocation_id="CAO-0002", fos="UNABLE_TO_ATTRIBUTE", vcc="UNABLE_TO_VERIFY"),
    ]
    avs = _build_activity_vs_skill(records)
    assert avs["skill_assessment"] == "UNABLE_TO_VERIFY"
    assert avs["activity_event_count"] == 2


# ---------------------------------------------------------------------------
# Test 10: distribution records produce SHARE_COUNT_REDUCTION only for buybacks
# ---------------------------------------------------------------------------

def test_per_share_share_count_reduction_only_for_buyback():
    records = [
        _rec(allocation_id="CAO-0001", category="dividend", pss="OWNER_EARNINGS_EFFECT"),
        _rec(allocation_id="CAO-0002", category="share_buyback", pss="SHARE_COUNT_REDUCTION"),
    ]
    psc = _build_per_share_context(records)
    assert psc["share_count_reduction_documented"] is True
    assert "CAO-0002" in psc["share_count_reduction_allocation_ids"]
    assert "CAO-0001" not in psc["share_count_reduction_allocation_ids"]


# ---------------------------------------------------------------------------
# Test 11: timeline uses canonical deployment_periods, not insertion order
# ---------------------------------------------------------------------------

def test_timeline_sorted_by_financial_year():
    records = [
        _rec(allocation_id="CAO-0003", periods=["fy26"]),
        _rec(allocation_id="CAO-0001", periods=["fy20"]),
        _rec(allocation_id="CAO-0002", periods=["fy23"]),
    ]
    timeline = _build_timeline(records)
    periods_in_order = [t["period"] for t in timeline]
    assert periods_in_order == ["fy20", "fy23", "fy26"]


# ---------------------------------------------------------------------------
# Test 12: validator RULE1 fires when capital share present with low coverage
# ---------------------------------------------------------------------------

def test_validator_rule1_fires_when_share_present_with_low_coverage():
    records = [_rec(allocation_id=f"CAO-{i:04d}", amount=None) for i in range(1, 4)]
    cov = _amount_coverage(records)
    assert not cov["capital_weighted_conclusions_permitted"]
    # Manually inject a share to trigger rule
    mix = _build_allocation_mix(records, cov)
    mix["by_category"][0]["share_of_known_deployment"] = 0.5  # forbidden injection
    profile = {
        "amount_coverage": cov,
        "allocation_mix": mix,
        "allocation_activity_vs_skill": {"skill_assessment": "UNABLE_TO_VERIFY", "value_creation_count": 0},
        "per_share_context": {"share_count_reduction_documented": False, "share_count_reduction_allocation_ids": []},
        "stewardship_observations": [],
        "timeline": [],
        "outcome_maturity": {"level_0": ["CAO-0001", "CAO-0002", "CAO-0003"]},
        "organic_vs_inorganic": {},
    }
    val = _validate_profile(profile, records)
    assert val["status"] == "FAIL"
    assert any("RULE1" in v for v in val["violations"])


# ---------------------------------------------------------------------------
# Test 13: validator RULE8 fires when maturity counts mismatch record count
# ---------------------------------------------------------------------------

def test_validator_rule8_fires_on_maturity_count_mismatch():
    records = [_rec(allocation_id="CAO-0001"), _rec(allocation_id="CAO-0002")]
    cov = _amount_coverage(records)
    profile = {
        "amount_coverage": cov,
        "allocation_mix": {"by_category": []},
        "allocation_activity_vs_skill": {"skill_assessment": "UNABLE_TO_VERIFY", "value_creation_count": 0},
        "per_share_context": {"share_count_reduction_documented": False, "share_count_reduction_allocation_ids": []},
        "stewardship_observations": [],
        "timeline": [],
        "outcome_maturity": {
            "level_0_deployment_unverified": ["CAO-0001"],  # only 1, but 2 records
        },
        "organic_vs_inorganic": {},
    }
    val = _validate_profile(profile, records)
    assert val["status"] == "FAIL"
    assert any("RULE8" in v for v in val["violations"])


# ---------------------------------------------------------------------------
# Test 14: build_longitudinal_profile returns error gracefully when no assessments
# ---------------------------------------------------------------------------

def test_build_longitudinal_profile_graceful_missing_assessments(tmp_path):
    company = "test_co"
    result = build_longitudinal_profile(
        company,
        tmp_path,
        assessments_path=tmp_path / "nonexistent.json",
        outcomes_path=tmp_path / "also_nonexistent.json",
    )
    assert "error" in result
    assert result["allocation_count"] == 0


# ---------------------------------------------------------------------------
# Test 15: build_longitudinal_profile with full zero-amount Sun Pharma-like data
# ---------------------------------------------------------------------------

def test_build_longitudinal_profile_sun_pharma_like(tmp_path):
    assessments = [
        {
            "allocation_id": "CAO-0001",
            "allocation_category": "acquisition",
            "deployment_state": "COMPLETED_TRANSACTION",
            "execution_state": "OPERATIONAL",
            "operating_outcome_state": "UNABLE_TO_VERIFY",
            "financial_outcome_state": "UNABLE_TO_ATTRIBUTE",
            "per_share_consequence_state": "UNABLE_TO_ATTRIBUTE",
            "value_creation_classification": "UNABLE_TO_VERIFY",
            "causal_attribution_confidence": "MEDIUM",
            "semantic_state_violations": [],
            "return_evidence": [],
        },
        {
            "allocation_id": "CAO-0002",
            "allocation_category": "dividend",
            "deployment_state": "DEPLOYED",
            "execution_state": "COMPLETED",
            "operating_outcome_state": "NO_VERIFIED_OUTCOME",
            "financial_outcome_state": "CASH_FLOW_EFFECT",
            "per_share_consequence_state": "OWNER_EARNINGS_EFFECT",
            "value_creation_classification": "UNABLE_TO_VERIFY",
            "causal_attribution_confidence": "MEDIUM",
            "semantic_state_violations": [],
            "return_evidence": [],
        },
        {
            "allocation_id": "CAO-0003",
            "allocation_category": "organic_capex",
            "deployment_state": "DEPLOYED",
            "execution_state": "UNABLE_TO_VERIFY",
            "operating_outcome_state": "UNABLE_TO_VERIFY",
            "financial_outcome_state": "UNABLE_TO_ATTRIBUTE",
            "per_share_consequence_state": "UNABLE_TO_ATTRIBUTE",
            "value_creation_classification": "UNABLE_TO_VERIFY",
            "causal_attribution_confidence": "UNKNOWN",
            "semantic_state_violations": [],
            "return_evidence": [],
        },
    ]
    outcomes = [
        {"allocation_id": "CAO-0001", "deployment_periods": ["fy20", "fy21"], "amount": None},
        {"allocation_id": "CAO-0002", "deployment_periods": ["fy20", "fy21", "fy22"], "amount": None},
        {"allocation_id": "CAO-0003", "deployment_periods": ["fy20", "fy21"], "amount": None},
    ]
    a_path = tmp_path / "capital_allocation_assessments.json"
    o_path = tmp_path / "capital_allocation_outcomes.json"
    a_path.write_text(json.dumps({"assessments": assessments}), encoding="utf-8")
    o_path.write_text(json.dumps({"allocations": outcomes}), encoding="utf-8")

    profile = build_longitudinal_profile(
        "test_co", tmp_path, assessments_path=a_path, outcomes_path=o_path
    )

    # Amount coverage: 0%
    assert profile["amount_coverage"]["coverage_ratio"] == 0.0
    assert not profile["amount_coverage"]["capital_weighted_conclusions_permitted"]

    # No share_of_known_deployment on any category
    for entry in profile["allocation_mix"]["by_category"]:
        assert entry["share_of_known_deployment"] is None

    # Activity vs skill: OUTCOMES_MOSTLY_UNVERIFIED (dividend CASH_FLOW_EFFECT counts as
    # financial attribution but no VALUE_CREATION_EVIDENCE → neither UNABLE_TO_VERIFY nor POSITIVE)
    assert profile["allocation_activity_vs_skill"]["skill_assessment"] == "OUTCOMES_MOSTLY_UNVERIFIED"

    # Validation must pass
    assert profile["validation"]["status"] == "PASS", profile["validation"]["violations"]

    # Timeline has fy20, fy21, fy22 in order
    periods_in_order = [t["period"] for t in profile["timeline"]]
    assert periods_in_order == ["fy20", "fy21", "fy22"]
