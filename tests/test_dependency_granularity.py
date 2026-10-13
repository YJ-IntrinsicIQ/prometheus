"""
M42 — Investor Panel Dependency Granularity Audit Tests.

Tests verify:
  DG-01  Removed management_commitments dependency does not dirty graham when mc changes alone
  DG-02  management_progression still dirties all 5 analysts (correct — all load it directly)
  DG-03  Fisher and Munger still dirty when management_commitments changes (direct top-3 stream)
  DG-04  Committee still dirty when Fisher/Munger are dirty (transitive dependency)
  DG-05  Graham, Buffett, Lynch CLEAN for management_commitments-only change in proposed registry
  DG-06  PCIM section coverage — which analyst doctrines require management_quality_inputs vs not
  DG-07  management synthesis unchanged by panel dependency changes (separate upstream)
  DG-08  Active dependency registry is unchanged from M40 baseline

All tests: 0 AI calls.
"""
from __future__ import annotations

import json
import copy
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ACTIVE_REGISTRY_PATH = REPO_ROOT / "governance" / "answer_dependency_registry.json"
PROPOSED_REGISTRY_PATH = REPO_ROOT / "governance" / "answer_dependency_registry.proposed_m42.json"
V1_BACKUP_PATH = REPO_ROOT / "governance" / "answer_dependency_registry.v1_pre_m43.json"
DOCTRINES_DIR = REPO_ROOT / "intelligence" / "investor_panel" / "doctrines"
PRIMARY_CO = "sun_pharma"

# --- helpers ----------------------------------------------------------------

def _load_registry(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _plan_with_registry(registry: Dict[str, Any], changed_modules):
    """Run plan_regeneration against a custom registry using mock."""
    from intelligence.regeneration_planner import plan_regeneration

    with patch("intelligence.regeneration_planner._load_dependency_registry", return_value=registry):
        result = plan_regeneration(PRIMARY_CO, changed_modules=changed_modules)
    return result


def _dirty_units(result: Dict[str, Any]) -> set:
    return {
        u["generation_unit"]
        for u in result["units"]
        if u["decision"] == "WOULD_REGENERATE"
    }


def _planned_calls(result: Dict[str, Any]) -> int:
    return result["answer_ai_calls_planned"]


def _active_upstream(unit: str) -> list:
    registry = _load_registry(ACTIVE_REGISTRY_PATH)
    return registry["generation_units"][unit]["upstream_modules"]


def _proposed_upstream(unit: str) -> list:
    registry = _load_registry(PROPOSED_REGISTRY_PATH)
    return registry["generation_units"][unit]["upstream_modules"]


# --- DG-01: v1 registry (pre-M43) — management_commitments change dirties graham (baseline) ---
# After M43 promotion, active registry is v2. Use v1 backup for v1 baseline checks.

def test_dg01_active_registry_management_commitments_dirties_graham():
    """Verify v1 registry listed management_commitments for graham (pre-M43 baseline)."""
    v1 = _load_registry(V1_BACKUP_PATH)
    assert "management_commitments" in v1["generation_units"]["graham_panel"]["upstream_modules"], \
        "v1 registry must list management_commitments for graham"


def test_dg01_active_registry_all_analysts_dirty_for_management_commitments():
    """Baseline: with v1 registry, management_commitments change dirties all 5 analysts + committee + synthesis."""
    v1 = _load_registry(V1_BACKUP_PATH)
    result = _plan_with_registry(v1, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    expected = {"graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel",
                "committee_synthesis", "how_good_is_management_synthesis"}
    assert dirty == expected, f"Expected 7 dirty units with v1 registry, got: {dirty}"
    assert _planned_calls(result) == 6  # Contract V5 (ENG-MISSION52): the management unit is deterministic -> 0 AI calls


# --- DG-02: management_progression dirties all 5 analysts (both registries) ---

def test_dg02_management_progression_dirties_all_analysts_active():
    """management_progression change dirties all 5 analysts under active registry."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    result = _plan_with_registry(active, changed_modules=["management_progression"])
    dirty = _dirty_units(result)
    for unit in ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]:
        assert unit in dirty, f"{unit} must be dirty when management_progression changes"
    assert _planned_calls(result) == 6  # Contract V5 (ENG-MISSION52): the management unit is deterministic -> 0 AI calls


def test_dg02_management_progression_dirties_all_analysts_proposed():
    """management_progression change still dirties all 5 analysts under proposed registry — unchanged."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_progression"])
    dirty = _dirty_units(result)
    for unit in ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]:
        assert unit in dirty, f"{unit} must be dirty for management_progression (company_memory_context top-3 for all)"
    assert _planned_calls(result) == 6  # Contract V5 (ENG-MISSION52): the management unit is deterministic -> 0 AI calls


def test_dg02_management_progression_in_all_analyst_upstream_modules():
    """management_progression is declared upstream for all 5 analysts in BOTH registries."""
    for path in (ACTIVE_REGISTRY_PATH, PROPOSED_REGISTRY_PATH):
        reg = _load_registry(path)
        for unit in ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]:
            assert "management_progression" in reg["generation_units"][unit]["upstream_modules"], \
                f"{path.name}: management_progression missing from {unit}"


# --- DG-03: Fisher and Munger still dirty for management_commitments in proposed registry ---

def test_dg03_fisher_munger_still_dirty_in_proposed_registry():
    """Fisher and Munger retain management_commitments in proposed registry (direct top-3 stream)."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    assert "management_commitments" in proposed["generation_units"]["fisher_panel"]["upstream_modules"]
    assert "management_commitments" in proposed["generation_units"]["munger_panel"]["upstream_modules"]


def test_dg03_fisher_munger_dirty_for_management_commitments_proposed():
    """Fisher and Munger remain dirty for management_commitments changes under proposed registry."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "fisher_panel" in dirty, "Fisher must stay dirty — management_commitments in top-3 company_memory_context"
    assert "munger_panel" in dirty, "Munger must stay dirty — management_commitments in top-3 company_memory_context"


def test_dg03_fisher_commitments_top3_justification():
    """Fisher's DOCTRINE_MEMORY_PRIORITIES places management_commitments at position 2 (index 2)."""
    from intelligence.investor_panel.company_memory_context import DOCTRINE_MEMORY_PRIORITIES
    fisher_priorities = DOCTRINE_MEMORY_PRIORITIES["fisher"]
    assert fisher_priorities.index("management commitments") < 3, \
        "management commitments must be in Fisher's top-3 streams"


def test_dg03_munger_commitments_top3_justification():
    """Munger's DOCTRINE_MEMORY_PRIORITIES places management_commitments at position 2 (index 2)."""
    from intelligence.investor_panel.company_memory_context import DOCTRINE_MEMORY_PRIORITIES
    munger_priorities = DOCTRINE_MEMORY_PRIORITIES["munger"]
    assert munger_priorities.index("management commitments") < 3, \
        "management commitments must be in Munger's top-3 streams"


# --- DG-04: Committee still dirty when Fisher/Munger dirty ---

def test_dg04_committee_dirty_via_fisher_munger():
    """Committee synthesis is still dirty when management_commitments changes under proposed registry."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "committee_synthesis" in dirty, \
        "Committee must be dirty transitively via Fisher and Munger"


def test_dg04_committee_not_dirty_when_all_analysts_clean():
    """Committee is clean if no analyst is dirty."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    # No changed modules → all clean
    result = _plan_with_registry(proposed, changed_modules=[])
    dirty = _dirty_units(result)
    assert "committee_synthesis" not in dirty


# --- DG-05: Graham, Buffett, Lynch CLEAN for management_commitments in proposed registry ---

def test_dg05_graham_clean_management_commitments_proposed():
    """Graham stays CLEAN for management_commitments changes under proposed registry — no access path."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "graham_panel" not in dirty, \
        "Graham has NO management_commitments access path — should be CLEAN"


def test_dg05_buffett_clean_management_commitments_proposed():
    """Buffett stays CLEAN for management_commitments changes under proposed registry."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "buffett_panel" not in dirty, \
        "Buffett accesses management_commitments only via pcim; pcim not corrupted here"


def test_dg05_lynch_clean_management_commitments_proposed():
    """Lynch stays CLEAN for management_commitments changes under proposed registry."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "lynch_panel" not in dirty, \
        "Lynch accesses management_commitments only via pcim; pcim not corrupted here"


def test_dg05_proposed_registry_scenario_i_4_calls():
    """Proposed registry reduces Scenario I from 7 to 4 calls."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    assert _planned_calls(result) == 3, \
        f"Proposed registry must plan 3 AI calls for Scenario I (4 dirty units, management deterministic), got {_planned_calls(result)}"


def test_dg05_proposed_saves_3_calls_over_active():
    """Proposed registry saves exactly 3 calls for Scenario I (compared to v1 baseline)."""
    v1 = _load_registry(V1_BACKUP_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result_v1 = _plan_with_registry(v1, changed_modules=["management_commitments"])
    result_proposed = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    assert _planned_calls(result_v1) - _planned_calls(result_proposed) == 3


# --- DG-06: PCIM section coverage audit ---

def test_dg06_graham_doctrine_no_management_quality_inputs():
    """Graham doctrine does NOT require management_quality_inputs (no management_commitments path via PCIM)."""
    path = DOCTRINES_DIR / "graham.json"
    doctrine = json.loads(path.read_text())
    assert "management_quality_inputs" not in doctrine["evidence_required_from_pcim"], \
        "Graham must not require management_quality_inputs PCIM section"


def test_dg06_graham_doctrine_no_management_execution_inputs():
    """Graham doctrine does NOT require management_execution_inputs."""
    path = DOCTRINES_DIR / "graham.json"
    doctrine = json.loads(path.read_text())
    assert "management_execution_inputs" not in doctrine["evidence_required_from_pcim"]


def test_dg06_buffett_doctrine_requires_management_quality_inputs():
    """Buffett doctrine DOES require management_quality_inputs (management_commitments data via pcim)."""
    path = DOCTRINES_DIR / "buffett.json"
    doctrine = json.loads(path.read_text())
    assert "management_quality_inputs" in doctrine["evidence_required_from_pcim"]


def test_dg06_lynch_doctrine_requires_management_quality_inputs():
    """Lynch doctrine DOES require management_quality_inputs (management_commitments data via pcim)."""
    path = DOCTRINES_DIR / "lynch.json"
    doctrine = json.loads(path.read_text())
    assert "management_quality_inputs" in doctrine["evidence_required_from_pcim"]


def test_dg06_graham_not_in_management_commitments_top3():
    """Graham's DOCTRINE_MEMORY_PRIORITIES has management_commitments outside top-3."""
    from intelligence.investor_panel.company_memory_context import DOCTRINE_MEMORY_PRIORITIES
    graham_priorities = DOCTRINE_MEMORY_PRIORITIES["graham"]
    mc_position = graham_priorities.index("management commitments")
    assert mc_position >= 3, \
        f"management commitments must be outside Graham's top-3 (pos {mc_position})"


def test_dg06_buffett_not_in_management_commitments_top3():
    """Buffett's DOCTRINE_MEMORY_PRIORITIES has management_commitments outside top-3."""
    from intelligence.investor_panel.company_memory_context import DOCTRINE_MEMORY_PRIORITIES
    buffett_priorities = DOCTRINE_MEMORY_PRIORITIES["buffett"]
    mc_position = buffett_priorities.index("management commitments")
    assert mc_position >= 3, \
        f"management commitments must be outside Buffett's top-3 (pos {mc_position})"


def test_dg06_lynch_not_in_management_commitments_top3():
    """Lynch's DOCTRINE_MEMORY_PRIORITIES has management_commitments outside top-3."""
    from intelligence.investor_panel.company_memory_context import DOCTRINE_MEMORY_PRIORITIES
    lynch_priorities = DOCTRINE_MEMORY_PRIORITIES["lynch"]
    mc_position = lynch_priorities.index("management commitments")
    assert mc_position >= 3, \
        f"management commitments must be outside Lynch's top-3 (pos {mc_position})"


def test_dg06_management_execution_inputs_sourced_from_management_progression():
    """PCIM management_execution_inputs authority is management_progression.json."""
    from knowledge.cim_contract import CIMContractBuilder
    import inspect
    src = inspect.getsource(CIMContractBuilder._build_management_execution_inputs)
    assert "management_progression" in src, \
        "management_execution_inputs must be built from management_progression"


def test_dg06_management_quality_inputs_contains_promise_tracker():
    """PCIM management_quality_inputs contains promise_tracker (sourced from management_commitments)."""
    pcim_path = REPO_ROOT / "companies" / "datapatterns" / "company_memory" / "pcim_v1.json"
    if not pcim_path.exists():
        pytest.skip("datapatterns pcim not available")
    pcim = json.loads(pcim_path.read_text())
    mqi = pcim.get("management_quality_inputs", {})
    assert "promise_tracker" in mqi, \
        "management_quality_inputs must contain promise_tracker (sourced from management_commitments)"


# --- DG-07: management synthesis unchanged by panel dependency changes ---

def test_dg07_management_synthesis_upstream_unchanged():
    """management synthesis upstream_modules are identical in active and proposed registries."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    active_mgmt = active["generation_units"]["how_good_is_management_synthesis"]["upstream_modules"]
    proposed_mgmt = proposed["generation_units"]["how_good_is_management_synthesis"]["upstream_modules"]
    assert sorted(active_mgmt) == sorted(proposed_mgmt), \
        "management synthesis upstream_modules must be identical — M42 does not change it"


def test_dg07_management_synthesis_still_dirty_management_commitments_proposed():
    """management synthesis is still dirty when management_commitments changes under proposed registry."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    assert "how_good_is_management_synthesis" in dirty, \
        "management synthesis retains direct management_commitments dependency"


def test_dg07_management_synthesis_dirty_count_independent_of_panel_changes():
    """management synthesis call count is 1 for single-module management_quality_summary change (not affected by panel optimization)."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_quality_summary"])
    dirty = _dirty_units(result)
    assert "how_good_is_management_synthesis" in dirty
    # Analyst panels must NOT be dirty (management_quality_summary not in their upstream)
    for unit in ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]:
        assert unit not in dirty, f"{unit} must not be dirty for management_quality_summary change"


# --- DG-08: Active dependency registry is unchanged ---

def test_dg08_active_registry_unchanged():
    """v1 backup preserves the pre-M43 registry state (all analysts had management_commitments)."""
    v1 = _load_registry(V1_BACKUP_PATH)
    # All M40 upstream_modules were present in v1
    assert "management_commitments" in v1["generation_units"]["graham_panel"]["upstream_modules"]
    assert "management_commitments" in v1["generation_units"]["buffett_panel"]["upstream_modules"]
    assert "management_commitments" in v1["generation_units"]["lynch_panel"]["upstream_modules"]
    assert "management_commitments" in v1["generation_units"]["fisher_panel"]["upstream_modules"]
    assert "management_commitments" in v1["generation_units"]["munger_panel"]["upstream_modules"]


def test_dg08_proposed_registry_is_separate_file():
    """Proposed registry is a separate file — active registry path unchanged."""
    assert PROPOSED_REGISTRY_PATH.exists(), "Proposed registry must exist at separate path"
    assert ACTIVE_REGISTRY_PATH != PROPOSED_REGISTRY_PATH, \
        "Active and proposed registries must be separate files"


def test_dg08_proposed_registry_contract_version_unchanged():
    """Proposed registry preserves the v1 dependency_contract_version (proposed was staged before promotion)."""
    v1 = _load_registry(V1_BACKUP_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    assert v1["dependency_contract_version"] == proposed["dependency_contract_version"], \
        "Proposed registry was staged against v1 and has matching contract version"


# --- Additional scenario checks: other scenarios unchanged ---

def test_dg_management_progression_scenario_same_in_both():
    """Scenario C (management_progression) produces 7 calls in both active and proposed."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    r_active = _plan_with_registry(active, changed_modules=["management_progression"])
    r_proposed = _plan_with_registry(proposed, changed_modules=["management_progression"])
    assert _planned_calls(r_active) == 6
    assert _planned_calls(r_proposed) == 6, "management_progression scenario must be unchanged"


def test_dg_pcim_scenario_same_in_both():
    """Scenario F (pcim-only) produces 6 calls in both active and proposed."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    r_active = _plan_with_registry(active, changed_modules=["pcim"])
    r_proposed = _plan_with_registry(proposed, changed_modules=["pcim"])
    # M44 replaced the whole-module 'pcim' dependency with per-section pcim:* modules in the ACTIVE
    # registry, so a bare 'pcim' change no longer dirties it; the M42 proposal still depends on 'pcim'.
    assert _planned_calls(r_active) == 0
    assert _planned_calls(r_proposed) == 6, "PCIM scenario unchanged by management_commitments optimization"
    sections = sorted({m for u in active["generation_units"].values() for m in u["upstream_modules"] if m.startswith("pcim:")})
    assert sections and _planned_calls(_plan_with_registry(active, changed_modules=sections)) == 6


def test_dg_financial_scenario_same_in_both():
    """Scenario B (financial only) produces 4 calls in both active and proposed."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    r_active = _plan_with_registry(active, changed_modules=["financial_truth_pack", "owner_earnings_bridge"])
    r_proposed = _plan_with_registry(proposed, changed_modules=["financial_truth_pack", "owner_earnings_bridge"])
    assert _planned_calls(r_active) == 4
    assert _planned_calls(r_proposed) == 4, "Financial scenario unchanged by management_commitments optimization"


def test_dg_risk_scenario_same_in_both():
    """Scenario E (risk-only) produces 3 calls in both active and proposed."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    r_active = _plan_with_registry(active, changed_modules=["risk_assessments"])
    r_proposed = _plan_with_registry(proposed, changed_modules=["risk_assessments"])
    assert _planned_calls(r_active) == 3
    assert _planned_calls(r_proposed) == 3


# --- False-clean analysis ---

def test_dg_no_false_clean_graham_pcim_path():
    """When pcim is dirty (rebuilt after management_commitments change), Graham is still dirty — pcim in upstream."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    # Simulate: management_commitments changed AND pcim was rebuilt
    result = _plan_with_registry(proposed, changed_modules=["management_commitments", "pcim"])
    dirty = _dirty_units(result)
    assert "graham_panel" in dirty, \
        "Graham must be dirty when pcim is dirty — no false_clean when pcim is rebuilt"
    assert "buffett_panel" in dirty, "Buffett must be dirty when pcim dirty"
    assert "lynch_panel" in dirty, "Lynch must be dirty when pcim dirty"


def test_dg_no_false_clean_all_7_when_pcim_and_mc_both_dirty():
    """All 7 units dirty when both pcim and management_commitments are dirty (full pipeline run)."""
    proposed = _load_registry(PROPOSED_REGISTRY_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments", "pcim"])
    assert _planned_calls(result) == 6, \
        "Full pipeline rebuild must plan 6 AI calls (7 dirty units; management is deterministic) even with proposed registry"
    assert len(_dirty_units(result)) == 7
