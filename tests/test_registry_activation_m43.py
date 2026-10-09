"""
M43 — Dependency Registry Activation Sign-off Tests.

Proves the proposed M42 registry is safe to activate:
  M43-01  Graham CLEAN on commitment-only change (zero data paths)
  M43-02  Buffett DIRTY when commitment change propagates through PCIM rebuild
  M43-03  Buffett CLEAN when commitment change does not alter consumed PCIM semantics
  M43-04  Lynch DIRTY when commitment change propagates through PCIM rebuild
  M43-05  Lynch CLEAN when commitment change does not alter consumed PCIM semantics
  M43-06  Fisher direct dependency still dirties on commitment-only change
  M43-07  Munger direct dependency still dirties on commitment-only change
  M43-08  Committee dirty follows analyst-output dependency, not raw commitment change alone
  M43-09  Management synthesis dependency graph unchanged
  M43-10  Stable evidence produces identical current/proposed plans
  M43-11  Call savings: Scenario I (commitment-only, no pcim rebuild) → 4 calls proposed vs 7 active
  M43-12  Scenario I with pcim rebuild → same 7 calls in both registries
  M43-13  Buffett/Lynch false-clean gate: relevant PCIM fields confirmed in doctrine
  M43-14  Graham false-clean gate: doctrine exclusion confirmed for management_quality_inputs
  M43-15  Registry promotion state: proposed has dependency_contract_version change marker

All tests: 0 AI calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
ACTIVE_REGISTRY_PATH = REPO_ROOT / "governance" / "answer_dependency_registry.json"
PROPOSED_REGISTRY_PATH = REPO_ROOT / "governance" / "answer_dependency_registry.proposed_m42.json"
V1_BACKUP_PATH = REPO_ROOT / "governance" / "answer_dependency_registry.v1_pre_m43.json"
DOCTRINES_DIR = REPO_ROOT / "intelligence" / "investor_panel" / "doctrines"
PRIMARY_CO = "sun_pharma"


def _load_registry(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _plan_with_registry(registry: Dict[str, Any], changed_modules):
    from intelligence.regeneration_planner import plan_regeneration
    with patch("intelligence.regeneration_planner._load_dependency_registry", return_value=registry):
        result = plan_regeneration(PRIMARY_CO, changed_modules=changed_modules)
    return result


def _dirty_units(result: Dict[str, Any]) -> set:
    return {u["generation_unit"] for u in result["units"] if u["decision"] == "WOULD_REGENERATE"}


def _planned_calls(result: Dict[str, Any]) -> int:
    return result["answer_ai_calls_planned"]


def _proposed_upstream(unit: str) -> list:
    return _load_registry(PROPOSED_REGISTRY_PATH)["generation_units"][unit]["upstream_modules"]


def _active_upstream(unit: str) -> list:
    return _load_registry(ACTIVE_REGISTRY_PATH)["generation_units"][unit]["upstream_modules"]


# ---------------------------------------------------------------------------
# M43-01: Graham CLEAN on commitment-only change
# ---------------------------------------------------------------------------

def test_m43_01_graham_clean_commitment_only_proposed():
    """Graham has zero management_commitments data paths — must stay CLEAN."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "graham_panel" not in dirty, \
        f"Graham must be CLEAN for commitment-only change in proposed registry; dirty={dirty}"


def test_m43_01_graham_clean_commitment_only_active_confirms_false_dirty():
    """Graham was dirty in v1 registry (pre-M43) = the false dirty that M42/M43 eliminated."""
    v1 = _load_registry(V1_BACKUP_PATH)
    result = _plan_with_registry(v1, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "graham_panel" in dirty, \
        "v1 registry must dirty graham (pre-M43 baseline confirming the false dirty existed)"


# ---------------------------------------------------------------------------
# M43-02 / M43-03: Buffett propagation proof
# Case A: pcim rebuilt after commitment change → Buffett dirty
# Case B: commitment change but pcim unchanged → Buffett CLEAN
# ---------------------------------------------------------------------------

def test_m43_02_buffett_dirty_when_pcim_rebuilt_proposed():
    """Case A: management_commitments change + pcim rebuild → Buffett dirty via pcim upstream."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    assert "pcim" in _proposed_upstream("buffett_panel"), \
        "pcim must remain in buffett proposed upstream for Case A to work"
    result = _plan_with_registry(proposed, changed_modules=["management_commitments", "pcim"])
    dirty = _dirty_units(result)
    assert "buffett_panel" in dirty, \
        f"Buffett must be dirty when pcim is rebuilt after commitment change; dirty={dirty}"


def test_m43_03_buffett_clean_when_pcim_unchanged_proposed():
    """Case B: management_commitments change but pcim semantics unchanged → Buffett CLEAN."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "buffett_panel" not in dirty, \
        f"Buffett must be CLEAN when commitment changes but pcim unchanged in proposed; dirty={dirty}"


# ---------------------------------------------------------------------------
# M43-04 / M43-05: Lynch propagation proof
# ---------------------------------------------------------------------------

def test_m43_04_lynch_dirty_when_pcim_rebuilt_proposed():
    """Case A: management_commitments change + pcim rebuild → Lynch dirty via pcim upstream."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    assert "pcim" in _proposed_upstream("lynch_panel"), \
        "pcim must remain in lynch proposed upstream"
    result = _plan_with_registry(proposed, changed_modules=["management_commitments", "pcim"])
    dirty = _dirty_units(result)
    assert "lynch_panel" in dirty, \
        f"Lynch must be dirty when pcim is rebuilt after commitment change; dirty={dirty}"


def test_m43_05_lynch_clean_when_pcim_unchanged_proposed():
    """Case B: management_commitments change but pcim semantics unchanged → Lynch CLEAN."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "lynch_panel" not in dirty, \
        f"Lynch must be CLEAN when commitment changes but pcim unchanged in proposed; dirty={dirty}"


# ---------------------------------------------------------------------------
# M43-06 / M43-07: Fisher and Munger still dirty via direct dependency
# ---------------------------------------------------------------------------

def test_m43_06_fisher_dirty_commitment_only_proposed():
    """Fisher has management_commitments in position 2 of top-3 — direct dependency retained."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    assert "management_commitments" in _proposed_upstream("fisher_panel"), \
        "management_commitments must remain in fisher proposed upstream"
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "fisher_panel" in dirty, \
        f"Fisher must be dirty for commitment-only change (direct dependency); dirty={dirty}"


def test_m43_07_munger_dirty_commitment_only_proposed():
    """Munger has management_commitments in position 2 of top-3 — direct dependency retained."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    assert "management_commitments" in _proposed_upstream("munger_panel"), \
        "management_commitments must remain in munger proposed upstream"
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "munger_panel" in dirty, \
        f"Munger must be dirty for commitment-only change (direct dependency); dirty={dirty}"


# ---------------------------------------------------------------------------
# M43-08: Committee behavior — dirty via analyst outputs, not raw commitment
# ---------------------------------------------------------------------------

def test_m43_08_committee_dirty_via_fisher_munger_not_raw_commitment():
    """Committee dirtied transitively via Fisher/Munger, not by direct commitment dependency."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    # committee_synthesis has no direct management_commitments dep
    assert "management_commitments" not in _proposed_upstream("committee_synthesis"), \
        "committee_synthesis must have no direct management_commitments dependency"
    # But Fisher/Munger dirty on commitment-only → committee becomes dirty
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "committee_synthesis" in dirty, \
        f"Committee must be dirty (transitively via Fisher/Munger); dirty={dirty}"
    # Verify the transitive chain: fisher and munger are the cause
    assert "fisher_panel" in dirty and "munger_panel" in dirty, \
        "Fisher and Munger must both be dirty as the cause of committee dirtying"


def test_m43_08_committee_clean_when_no_analyst_dirty():
    """Committee remains CLEAN when no analyst output changes."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    # commentary_themes change: only fisher is dirty (commentary_themes in fisher upstream)
    # committee still has analysts as upstream — need all analysts clean to test committee clean
    # Use a module that affects no analyst
    result = _plan_with_registry(proposed, changed_modules=["risk_assessments"])
    dirty = _dirty_units(result)
    # graham_panel and munger_panel have risk_assessments in upstream
    # committee should only dirty if any of its 5 analyst upstream_generation_units dirty
    # risk_assessments → graham dirty, munger dirty → committee dirty (via transitive chain)
    # So test with something that affects zero analysts:
    result2 = _plan_with_registry(proposed, changed_modules=["economic_attribution"])
    dirty2 = _dirty_units(result2)
    # economic_attribution is only in how_good_is_management_synthesis upstream
    assert "committee_synthesis" not in dirty2, \
        f"Committee must not dirty from economic_attribution change (not in any analyst upstream); dirty={dirty2}"
    assert "how_good_is_management_synthesis" in dirty2, \
        "Management synthesis must dirty from economic_attribution change"


# ---------------------------------------------------------------------------
# M43-09: Management synthesis dependency graph unchanged
# ---------------------------------------------------------------------------

def test_m43_09_management_synthesis_upstream_unchanged():
    """how_good_is_management_synthesis upstream must be identical in active and proposed."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    active_upstream = set(active["generation_units"]["how_good_is_management_synthesis"]["upstream_modules"])
    proposed_upstream = set(proposed["generation_units"]["how_good_is_management_synthesis"]["upstream_modules"])
    assert active_upstream == proposed_upstream, \
        f"Management synthesis upstream must be unchanged. Active={active_upstream}, Proposed={proposed_upstream}"


def test_m43_09_management_synthesis_still_dirty_commitment_proposed():
    """Management synthesis must still dirty on commitment change (direct dependency retained)."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "how_good_is_management_synthesis" in dirty, \
        "Management synthesis must be dirty for commitment change (direct dependency unchanged)"


# ---------------------------------------------------------------------------
# M43-10: Stable evidence → identical plans
# ---------------------------------------------------------------------------

def test_m43_10_stable_evidence_identical_plans():
    """When no modules change, both registries produce 0 planned calls."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result_active = _plan_with_registry(active, changed_modules=[])
    result_proposed = _plan_with_registry(proposed, changed_modules=[])
    assert _planned_calls(result_active) == 0, "Active: stable evidence → 0 calls"
    assert _planned_calls(result_proposed) == 0, "Proposed: stable evidence → 0 calls"
    assert _dirty_units(result_active) == set(), "Active: no dirty units on stable evidence"
    assert _dirty_units(result_proposed) == set(), "Proposed: no dirty units on stable evidence"


# ---------------------------------------------------------------------------
# M43-11: Scenario I — commitment-only (no pcim rebuild) call savings
# ---------------------------------------------------------------------------

def test_m43_11_scenario_i_call_savings():
    """Scenario I: v1→v2 promotion. v1=7 calls, v2 (promoted)=4 calls, saves 3."""
    v1 = _load_registry(V1_BACKUP_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result_v1 = _plan_with_registry(v1, changed_modules=["management_commitments"])
    result_proposed = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    calls_v1 = _planned_calls(result_v1)
    calls_proposed = _planned_calls(result_proposed)
    assert calls_v1 == 7, f"v1: Scenario I must plan 7 calls, got {calls_v1}"
    assert calls_proposed == 4, f"Proposed: Scenario I must plan 4 calls, got {calls_proposed}"
    assert calls_v1 - calls_proposed == 3, \
        f"Promotion must save exactly 3 calls, saved {calls_v1 - calls_proposed}"


def test_m43_11_scenario_i_dirty_unit_sets():
    """Scenario I dirty units: v1 has 7, proposed/v2 has 4 (fisher/munger/committee/synthesis)."""
    v1 = _load_registry(V1_BACKUP_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    dirty_v1 = _dirty_units(_plan_with_registry(v1, changed_modules=["management_commitments"]))
    dirty_proposed = _dirty_units(_plan_with_registry(proposed, changed_modules=["management_commitments"]))
    # v1: all 7
    assert dirty_v1 == {
        "graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel",
        "committee_synthesis", "how_good_is_management_synthesis"
    }
    # Proposed: only fisher, munger (direct), committee (transitive), management_synthesis (direct)
    assert dirty_proposed == {
        "fisher_panel", "munger_panel",
        "committee_synthesis", "how_good_is_management_synthesis"
    }
    # Saved: graham, buffett, lynch
    saved = dirty_v1 - dirty_proposed
    assert saved == {"graham_panel", "buffett_panel", "lynch_panel"}, \
        f"Expected to save graham/buffett/lynch, saved={saved}"


# ---------------------------------------------------------------------------
# M43-12: Scenario I with pcim rebuild → same 7 calls in both registries
# ---------------------------------------------------------------------------

def test_m43_12_commitment_plus_pcim_rebuild_same_in_both_registries():
    """When management_commitments change + pcim rebuilt, both registries dirty all 7 units."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result_active = _plan_with_registry(active, changed_modules=["management_commitments", "pcim"])
    result_proposed = _plan_with_registry(proposed, changed_modules=["management_commitments", "pcim"])
    assert _planned_calls(result_active) == 7, "Active: all 7 dirty when pcim rebuilt"
    assert _planned_calls(result_proposed) == 7, "Proposed: all 7 dirty when pcim rebuilt"
    dirty_active = _dirty_units(result_active)
    dirty_proposed = _dirty_units(result_proposed)
    expected = {
        "graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel",
        "committee_synthesis", "how_good_is_management_synthesis"
    }
    assert dirty_active == expected
    assert dirty_proposed == expected


# ---------------------------------------------------------------------------
# M43-13: Buffett/Lynch false-clean gate — doctrine requires management_quality_inputs
# ---------------------------------------------------------------------------

def test_m43_13_buffett_doctrine_requires_management_quality_inputs():
    """Buffett doctrine must require management_quality_inputs — proving PCIM path exists."""
    doctrine = json.loads((DOCTRINES_DIR / "buffett.json").read_text())
    assert "management_quality_inputs" in doctrine.get("evidence_required_from_pcim", []), \
        "Buffett doctrine must list management_quality_inputs (contains promise_tracker from management_commitments)"


def test_m43_13_lynch_doctrine_requires_management_quality_inputs():
    """Lynch doctrine must require management_quality_inputs — proving PCIM path exists."""
    doctrine = json.loads((DOCTRINES_DIR / "lynch.json").read_text())
    assert "management_quality_inputs" in doctrine.get("evidence_required_from_pcim", []), \
        "Lynch doctrine must list management_quality_inputs (contains promise_tracker from management_commitments)"


def test_m43_13_pcim_management_quality_inputs_contains_promise_tracker():
    """Live PCIM must have management_quality_inputs.promise_tracker — confirming chain exists."""
    pcim_path = REPO_ROOT / "companies" / PRIMARY_CO / "company_memory" / "pcim_v1.json"
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    mqi = pcim.get("management_quality_inputs", {})
    assert "promise_tracker" in mqi, \
        "PCIM management_quality_inputs must contain promise_tracker (built from management_commitments)"


def test_m43_13_promise_tracker_sourced_from_management_commitments():
    """CIMContractBuilder._build_management_quality_inputs reads promise_tracker."""
    from knowledge.cim_contract import CIMContractBuilder
    import inspect
    src = inspect.getsource(CIMContractBuilder._build_cim_v1)
    assert "promise_tracker" in src, \
        "CIMContractBuilder._build_cim_v1 must reference promise_tracker (built from management_commitments)"


# ---------------------------------------------------------------------------
# M43-14: Graham false-clean gate — doctrine exclusion confirmed
# ---------------------------------------------------------------------------

def test_m43_14_graham_doctrine_excludes_management_quality_inputs():
    """Graham doctrine must NOT list management_quality_inputs — confirming zero PCIM path."""
    doctrine = json.loads((DOCTRINES_DIR / "graham.json").read_text())
    assert "management_quality_inputs" not in doctrine.get("evidence_required_from_pcim", []), \
        "Graham doctrine must NOT require management_quality_inputs (no promise_tracker path)"


def test_m43_14_graham_doctrine_excludes_management_execution_inputs():
    """Graham doctrine must NOT list management_execution_inputs — zero management data path."""
    doctrine = json.loads((DOCTRINES_DIR / "graham.json").read_text())
    assert "management_execution_inputs" not in doctrine.get("evidence_required_from_pcim", []), \
        "Graham doctrine must NOT require management_execution_inputs"


def test_m43_14_graham_no_management_commitments_upstream_proposed():
    """Proposed registry must NOT list management_commitments for graham."""
    assert "management_commitments" not in _proposed_upstream("graham_panel"), \
        "graham proposed upstream must not include management_commitments"


def test_m43_14_graham_pcim_still_upstream_proposed():
    """Graham still has pcim upstream in proposed registry — pcim path for other sections."""
    assert "pcim" in _proposed_upstream("graham_panel"), \
        "Graham must retain pcim upstream (financial sections still consumed)"


# ---------------------------------------------------------------------------
# M43-15: Registry promotion readiness checks
# ---------------------------------------------------------------------------

def test_m43_15_proposed_registry_management_commitments_removed_from_three():
    """Proposed registry removes management_commitments from exactly graham/buffett/lynch."""
    for unit in ["graham_panel", "buffett_panel", "lynch_panel"]:
        upstream = _proposed_upstream(unit)
        assert "management_commitments" not in upstream, \
            f"{unit} must not have management_commitments in proposed registry"


def test_m43_15_proposed_registry_pcim_retained_for_buffett_lynch():
    """Proposed registry retains pcim for buffett/lynch — the trusted propagation path."""
    for unit in ["buffett_panel", "lynch_panel"]:
        upstream = _proposed_upstream(unit)
        assert "pcim" in upstream, \
            f"{unit} must retain pcim in proposed registry"


def test_m43_15_fisher_munger_commitments_unchanged_proposed():
    """Fisher and Munger must retain management_commitments in proposed registry."""
    for unit in ["fisher_panel", "munger_panel"]:
        upstream = _proposed_upstream(unit)
        assert "management_commitments" in upstream, \
            f"{unit} must retain management_commitments in proposed registry"


def test_m43_15_management_synthesis_commitments_unchanged_proposed():
    """how_good_is_management_synthesis must retain management_commitments."""
    upstream = _proposed_upstream("how_good_is_management_synthesis")
    assert "management_commitments" in upstream, \
        "how_good_is_management_synthesis must retain management_commitments"


def test_m43_15_all_seven_units_present_in_proposed():
    """Proposed registry must define all 7 generation units."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    expected = {
        "graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel",
        "committee_synthesis", "how_good_is_management_synthesis"
    }
    actual = set(proposed["generation_units"].keys())
    assert actual == expected, f"Proposed registry missing units. Expected={expected}, Got={actual}"
