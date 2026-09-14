"""
ENG-122: Capital Allocation Outcome Attribution — regression tests.

Validates the five-tier outcome attribution taxonomy and three-question framework:
  Q1: Did management deploy the capital?        → deployment_state
  Q2: Did the deployment become operational?    → execution_state
  Q3: Did it create economic value?             → outcome_attribution (ENG-122)

HEURISTIC_CAUSAL_ATTRIBUTION_PATHS = 0: no temporal-sequence causality inference.
FALSE_CAUSAL_ATTRIBUTIONS = 0: acquisitions never show DIRECTLY_ATTRIBUTABLE.
COMPANY_SPECIFIC_CAPITAL_OUTCOME_LOGIC = 0: all logic is generic.
"""

from __future__ import annotations

import pytest
from intelligence.capital_allocation_outcomes.builder import (
    _causal_attribution_states,
    _determine_outcome_attribution,
)
from intelligence.capital_allocation_outcomes.contracts import OUTCOME_ATTRIBUTION_LEVELS


# ── A: All five taxonomy values are valid contract members ──────────────────

def test_A_outcome_attribution_taxonomy_complete():
    assert "DIRECTLY_ATTRIBUTABLE" in OUTCOME_ATTRIBUTION_LEVELS
    assert "STRONGLY_SUPPORTED" in OUTCOME_ATTRIBUTION_LEVELS
    assert "ASSOCIATED_NOT_ATTRIBUTABLE" in OUTCOME_ATTRIBUTION_LEVELS
    assert "NO_OUTCOME_EVIDENCE" in OUTCOME_ATTRIBUTION_LEVELS
    assert "NEGATIVE_OUTCOME" in OUTCOME_ATTRIBUTION_LEVELS
    assert len(OUTCOME_ATTRIBUTION_LEVELS) == 5


# ── B: Distributions → DIRECTLY_ATTRIBUTABLE ───────────────────────────────

@pytest.mark.parametrize("category", ["dividend", "special_dividend", "share_buyback", "debt_repayment"])
def test_B_distributions_directly_attributable(category):
    record = {"allocation_category": category, "current_status": "deployed", "outcome_status": "partially_observed", "execution_state": "COMPLETED"}
    oa = _determine_outcome_attribution(record, [])
    assert oa == "DIRECTLY_ATTRIBUTABLE", (
        f"{category} should be DIRECTLY_ATTRIBUTABLE (transaction IS the economic event), got {oa!r}"
    )


# ── C: Acquisition + operational + no evidence → ASSOCIATED_NOT_ATTRIBUTABLE ─

def test_C_acquisition_operational_no_financial_attribution():
    """Acquisition that is operational still cannot attribute financial outcomes."""
    record = {
        "allocation_category": "acquisition",
        "current_status": "deployed",
        "outcome_status": "partially_observed",
        "execution_state": "OPERATIONAL",
    }
    evidence = [{"kind": "project", "note": "operational"}]
    oa = _determine_outcome_attribution(record, evidence)
    # OPERATIONAL + 1 project evidence → ASSOCIATED_NOT_ATTRIBUTABLE (not STRONGLY_SUPPORTED — only 1 evidence item)
    assert oa == "ASSOCIATED_NOT_ATTRIBUTABLE", (
        f"One project evidence item not enough for STRONGLY_SUPPORTED, got {oa!r}"
    )


# ── D: Acquisition + 2 project evidence items → STRONGLY_SUPPORTED ─────────

def test_D_acquisition_multiple_evidence_strongly_supported():
    record = {
        "allocation_category": "acquisition",
        "current_status": "deployed",
        "outcome_status": "partially_observed",
        "execution_state": "OPERATIONAL",
    }
    evidence = [
        {"kind": "project", "note": "operational and integrated"},
        {"kind": "capacity", "note": "commissioning complete"},
    ]
    oa = _determine_outcome_attribution(record, evidence)
    assert oa == "STRONGLY_SUPPORTED", f"Expected STRONGLY_SUPPORTED with 2 specific evidence items, got {oa!r}"


# ── E: Capex with no project/capacity evidence → NO_OUTCOME_EVIDENCE ────────

def test_E_capex_no_evidence_no_outcome():
    record = {
        "allocation_category": "organic_capex",
        "current_status": "deployed",
        "outcome_status": "not_yet_observable",
        "execution_state": "UNABLE_TO_VERIFY",
    }
    oa = _determine_outcome_attribution(record, [])
    assert oa == "NO_OUTCOME_EVIDENCE", f"Expected NO_OUTCOME_EVIDENCE for untraced capex, got {oa!r}"


# ── F: Abandoned allocation → NEGATIVE_OUTCOME ──────────────────────────────

def test_F_abandoned_allocation_negative_outcome():
    record = {
        "allocation_category": "organic_capex",
        "current_status": "abandoned",
        "outcome_status": "negative_outcome",
        "execution_state": "UNABLE_TO_VERIFY",
    }
    oa = _determine_outcome_attribution(record, [])
    assert oa == "NEGATIVE_OUTCOME", f"Expected NEGATIVE_OUTCOME for abandoned allocation, got {oa!r}"


# ── G: Superseded allocation → NEGATIVE_OUTCOME ─────────────────────────────

def test_G_superseded_allocation_negative_outcome():
    record = {
        "allocation_category": "strategic_investment",
        "current_status": "superseded",
        "outcome_status": "not_yet_observable",
        "execution_state": "UNABLE_TO_VERIFY",
    }
    oa = _determine_outcome_attribution(record, [])
    assert oa == "NEGATIVE_OUTCOME", f"Expected NEGATIVE_OUTCOME for superseded allocation, got {oa!r}"


# ── H: outcome_attribution propagates through _causal_attribution_states ─────

def test_H_outcome_attribution_in_causal_states():
    record = {
        "allocation_category": "dividend",
        "current_status": "deployed",
        "outcome_status": "partially_observed",
        "execution_state": "COMPLETED",
    }
    states = _causal_attribution_states(record, [])
    assert "outcome_attribution" in states, "outcome_attribution must be in _causal_attribution_states output"
    assert states["outcome_attribution"] == "DIRECTLY_ATTRIBUTABLE"


# ── I: No temporal-sequence inference — revenue growth ≠ acquisition outcome ─

def test_I_no_temporal_sequence_causality():
    """Revenue trend after acquisition must NOT produce DIRECTLY_ATTRIBUTABLE or STRONGLY_SUPPORTED
    without explicit project/capacity evidence. Temporal association alone = ASSOCIATED_NOT_ATTRIBUTABLE."""
    record = {
        "allocation_category": "acquisition",
        "current_status": "deployed",
        "outcome_status": "partially_observed",  # some 'positive' keywords found
        "execution_state": "OPERATIONAL",         # confirmed operational
        # No project/capacity evidence — only timing
    }
    # Zero specific evidence: execution visible but no project/capacity evidence
    oa = _determine_outcome_attribution(record, [])
    assert oa == "ASSOCIATED_NOT_ATTRIBUTABLE", (
        f"Temporal overlap alone must not produce DIRECTLY_ATTRIBUTABLE or STRONGLY_SUPPORTED, got {oa!r}"
    )


# ── J: Working capital → NO_OUTCOME_EVIDENCE when execution unverified ───────

def test_J_working_capital_no_outcome_evidence():
    record = {
        "allocation_category": "working_capital",
        "current_status": "unable_to_verify",
        "outcome_status": "not_yet_observable",
        "execution_state": "UNABLE_TO_VERIFY",
    }
    oa = _determine_outcome_attribution(record, [])
    assert oa == "NO_OUTCOME_EVIDENCE"


# ── K: Sun Pharma production — 10 allocations, zero violations ───────────────

def test_K_sun_pharma_production_zero_violations():
    """Regression: Sun Pharma rebuild must produce zero semantic_state_violations."""
    import json
    from pathlib import Path
    assessments_path = Path("companies/sun_pharma/company_memory/capital_allocation_outcomes/capital_allocation_assessments.json")
    if not assessments_path.exists():
        pytest.skip("Sun Pharma capital allocation assessments not built yet")
    assessments = json.loads(assessments_path.read_text())
    violations_total = []
    for a in assessments.get("assessments", []):
        v = a.get("semantic_state_violations") or []
        violations_total.extend(v)
    assert violations_total == [], f"Expected zero violations, got: {violations_total}"


# ── L: Sun Pharma — no acquisition shows DIRECTLY_ATTRIBUTABLE ───────────────

def test_L_sun_pharma_no_false_acquisition_attribution():
    """FALSE_CAUSAL_ATTRIBUTIONS = 0: no acquisition is DIRECTLY_ATTRIBUTABLE."""
    import json
    from pathlib import Path
    assessments_path = Path("companies/sun_pharma/company_memory/capital_allocation_outcomes/capital_allocation_assessments.json")
    if not assessments_path.exists():
        pytest.skip("Sun Pharma capital allocation assessments not built yet")
    assessments = json.loads(assessments_path.read_text())
    for a in assessments.get("assessments", []):
        if a.get("allocation_category") in {"acquisition", "acquisition_integration", "strategic_investment"}:
            oa = a.get("outcome_attribution", "")
            assert oa != "DIRECTLY_ATTRIBUTABLE", (
                f"{a['allocation_id']} ({a['allocation_category']}) shows DIRECTLY_ATTRIBUTABLE — "
                f"acquisition financial outcomes are NOT directly attributable without explicit source evidence"
            )


# ── M: Sun Pharma — distributions are DIRECTLY_ATTRIBUTABLE ─────────────────

def test_M_sun_pharma_distributions_directly_attributable():
    """All dividend / buyback / debt-repayment allocations must be DIRECTLY_ATTRIBUTABLE."""
    import json
    from pathlib import Path
    assessments_path = Path("companies/sun_pharma/company_memory/capital_allocation_outcomes/capital_allocation_assessments.json")
    if not assessments_path.exists():
        pytest.skip("Sun Pharma capital allocation assessments not built yet")
    assessments = json.loads(assessments_path.read_text())
    distribution_categories = {"dividend", "special_dividend", "share_buyback", "debt_repayment"}
    for a in assessments.get("assessments", []):
        if a.get("allocation_category") in distribution_categories:
            oa = a.get("outcome_attribution", "")
            assert oa == "DIRECTLY_ATTRIBUTABLE", (
                f"{a['allocation_id']} ({a['allocation_category']}) should be DIRECTLY_ATTRIBUTABLE, got {oa!r}"
            )


# ── N: outcome_attribution field present in all assessments ──────────────────

def test_N_outcome_attribution_field_present_in_all_assessments():
    """Every assessment record must carry an outcome_attribution field."""
    import json
    from pathlib import Path
    assessments_path = Path("companies/sun_pharma/company_memory/capital_allocation_outcomes/capital_allocation_assessments.json")
    if not assessments_path.exists():
        pytest.skip("Sun Pharma capital allocation assessments not built yet")
    assessments = json.loads(assessments_path.read_text())
    for a in assessments.get("assessments", []):
        assert "outcome_attribution" in a, f"outcome_attribution missing from {a.get('allocation_id','?')}"
        assert a["outcome_attribution"] in OUTCOME_ATTRIBUTION_LEVELS, (
            f"{a.get('allocation_id')}: invalid outcome_attribution={a['outcome_attribution']!r}"
        )
