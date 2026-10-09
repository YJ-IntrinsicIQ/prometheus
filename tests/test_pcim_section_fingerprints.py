"""
M44 — PCIM Section Fingerprinting & Fine-Grained Regeneration Isolation.

Tests:
  PCIM-FP-01  compute_pcim_section_fingerprints returns entry for every candidate section
  PCIM-FP-02  Section digests are stable across repeated calls (5-run stability)
  PCIM-FP-03  Fingerprint schema version bumped to 2
  PCIM-FP-04  compute_company_fingerprints includes pcim:<section> virtual modules
  PCIM-DG-01  management_quality_inputs change → Graham CLEAN (not in doctrine)
  PCIM-DG-02  management_quality_inputs change → Buffett/Fisher/Munger/Lynch DIRTY
  PCIM-DG-03  management_execution_inputs change → Graham CLEAN
  PCIM-DG-04  risk_inputs change → Buffett/Fisher/Lynch CLEAN (not in doctrine)
  PCIM-DG-05  risk_inputs change → Graham/Munger DIRTY
  PCIM-DG-06  financial_truth_inputs change (always_include) → all analysts dirty
  PCIM-M43-01 Regression: management_commitments-only change still dirties Fisher/Munger directly
  PCIM-M43-02 Regression: PCIM rebuild still dirties all analysts via section change
  PCIM-V3-01  Proposed v3 registry structure: no bare 'pcim' entry for any analyst

All tests: 0 AI calls.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Set
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
ACTIVE_REGISTRY_PATH = REPO_ROOT / "governance" / "answer_dependency_registry.json"
PROPOSED_M44_PATH = REPO_ROOT / "governance" / "answer_dependency_registry.proposed_m44.json"
DOCTRINES_DIR = REPO_ROOT / "intelligence" / "investor_panel" / "doctrines"
PRIMARY_CO = "sun_pharma"


def _load_registry(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _plan_with_registry(registry: Dict[str, Any], changed_modules):
    from intelligence.regeneration_planner import plan_regeneration
    with patch("intelligence.regeneration_planner._load_dependency_registry", return_value=registry):
        result = plan_regeneration(PRIMARY_CO, changed_modules=changed_modules)
    return result


def _dirty_units(result: Dict[str, Any]) -> Set[str]:
    return {u["generation_unit"] for u in result["units"] if u["decision"] == "WOULD_REGENERATE"}


def _planned_calls(result: Dict[str, Any]) -> int:
    return result["answer_ai_calls_planned"]


# ---------------------------------------------------------------------------
# PCIM-FP: Fingerprint infrastructure tests
# ---------------------------------------------------------------------------

def test_pcim_fp01_section_fingerprints_cover_all_candidates():
    """Every PCIM_SECTION_FINGERPRINT_CANDIDATE present in sun_pharma PCIM has a digest."""
    from intelligence.evidence_fingerprints import (
        compute_pcim_section_fingerprints,
        PCIM_SECTION_FINGERPRINT_CANDIDATES,
    )
    import json
    pcim = json.loads(
        (REPO_ROOT / "companies" / PRIMARY_CO / "company_memory" / "pcim_v1.json").read_text()
    )
    result = compute_pcim_section_fingerprints(pcim)
    for section in PCIM_SECTION_FINGERPRINT_CANDIDATES:
        if section in pcim:
            key = f"pcim:{section}"
            assert key in result, f"Missing section fingerprint: {key}"
            assert result[key]["digest"].startswith("sha256:"), f"Bad digest for {key}"


def test_pcim_fp02_section_digests_stable_5_runs():
    """Section fingerprints are deterministic across 5 consecutive computations."""
    from intelligence.evidence_fingerprints import compute_pcim_section_fingerprints
    import json
    pcim = json.loads(
        (REPO_ROOT / "companies" / PRIMARY_CO / "company_memory" / "pcim_v1.json").read_text()
    )
    first = compute_pcim_section_fingerprints(pcim)
    for _ in range(4):
        run = compute_pcim_section_fingerprints(pcim)
        assert run == first, "Section fingerprints are not stable"


def test_pcim_fp03_fingerprint_schema_version_is_2():
    """FINGERPRINT_SCHEMA_VERSION must be '2' after M44."""
    from intelligence.evidence_fingerprints import FINGERPRINT_SCHEMA_VERSION
    assert FINGERPRINT_SCHEMA_VERSION == "2", (
        f"Expected schema version '2', got '{FINGERPRINT_SCHEMA_VERSION}'"
    )


def test_pcim_fp04_compute_company_fingerprints_includes_section_virtuals():
    """compute_company_fingerprints includes pcim:section virtual module entries."""
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    fp = compute_company_fingerprints(PRIMARY_CO)
    section_keys = [k for k in fp["modules"] if k.startswith("pcim:")]
    assert len(section_keys) >= 40, (
        f"Expected at least 40 pcim: virtual modules, got {len(section_keys)}"
    )
    assert "pcim" in fp["modules"], "Whole-file pcim digest must still be present"
    assert fp["fingerprint_schema_version"] == "2"


# ---------------------------------------------------------------------------
# PCIM-DG: Dependency granularity tests using proposed v3 registry
# ---------------------------------------------------------------------------

def test_pcim_dg01_management_quality_change_graham_clean():
    """management_quality_inputs PCIM section change → Graham stays CLEAN in v3 registry."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    result = _plan_with_registry(proposed, changed_modules=["pcim:management_quality_inputs"])
    dirty = _dirty_units(result)
    assert "graham_panel" not in dirty, (
        f"Graham should be CLEAN when only management_quality_inputs changes. Dirty: {dirty}"
    )


def test_pcim_dg02_management_quality_change_dirties_4_analysts():
    """management_quality_inputs change → Buffett, Fisher, Munger, Lynch are DIRTY."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    result = _plan_with_registry(proposed, changed_modules=["pcim:management_quality_inputs"])
    dirty = _dirty_units(result)
    for analyst in ["buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]:
        assert analyst in dirty, (
            f"{analyst} should be DIRTY when management_quality_inputs changes. Dirty: {dirty}"
        )


def test_pcim_dg03_management_execution_change_graham_clean():
    """management_execution_inputs PCIM section change → Graham stays CLEAN."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    result = _plan_with_registry(proposed, changed_modules=["pcim:management_execution_inputs"])
    dirty = _dirty_units(result)
    assert "graham_panel" not in dirty, (
        f"Graham should be CLEAN when only management_execution_inputs changes. Dirty: {dirty}"
    )


def test_pcim_dg04_risk_inputs_change_buffett_fisher_lynch_clean():
    """risk_inputs PCIM section change → Buffett, Fisher, Lynch stay CLEAN."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    result = _plan_with_registry(proposed, changed_modules=["pcim:risk_inputs"])
    dirty = _dirty_units(result)
    for analyst in ["buffett_panel", "fisher_panel", "lynch_panel"]:
        assert analyst not in dirty, (
            f"{analyst} should be CLEAN when only risk_inputs changes. Dirty: {dirty}"
        )


def test_pcim_dg05_risk_inputs_change_dirties_graham_munger():
    """risk_inputs PCIM section change → Graham and Munger are DIRTY."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    result = _plan_with_registry(proposed, changed_modules=["pcim:risk_inputs"])
    dirty = _dirty_units(result)
    assert "graham_panel" in dirty, f"Graham should be DIRTY when risk_inputs changes. Dirty: {dirty}"
    assert "munger_panel" in dirty, f"Munger should be DIRTY when risk_inputs changes. Dirty: {dirty}"


def test_pcim_dg06_always_include_change_dirties_all_analysts():
    """financial_truth_inputs change (always_include section) → all 5 analysts dirty."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    result = _plan_with_registry(proposed, changed_modules=["pcim:financial_truth_inputs"])
    dirty = _dirty_units(result)
    for analyst in ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]:
        assert analyst in dirty, (
            f"{analyst} should be DIRTY when financial_truth_inputs changes. Dirty: {dirty}"
        )


# ---------------------------------------------------------------------------
# PCIM-M43: M43 regression tests (propagation chain must still work in v3)
# ---------------------------------------------------------------------------

def test_pcim_m43_01_management_commitments_direct_dep_fisher_munger():
    """M43 regression: management_commitments-only change still dirties Fisher and Munger."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    result = _plan_with_registry(proposed, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    # Fisher and Munger have direct management_commitments dep (kept from v2)
    assert "fisher_panel" in dirty, (
        f"Fisher should be DIRTY on management_commitments change. Dirty: {dirty}"
    )
    assert "munger_panel" in dirty, (
        f"Munger should be DIRTY on management_commitments change. Dirty: {dirty}"
    )


def test_pcim_m43_02_pcim_rebuild_dirties_all_consuming_sections():
    """M43 regression: when all PCIM sections change (full rebuild), all analysts dirty."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    from intelligence.evidence_fingerprints import PCIM_SECTION_FINGERPRINT_CANDIDATES
    all_section_modules = [f"pcim:{s}" for s in PCIM_SECTION_FINGERPRINT_CANDIDATES]
    result = _plan_with_registry(proposed, changed_modules=all_section_modules)
    dirty = _dirty_units(result)
    for analyst in ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]:
        assert analyst in dirty, (
            f"{analyst} should be DIRTY when all PCIM sections change. Dirty: {dirty}"
        )


# ---------------------------------------------------------------------------
# PCIM-V3: Registry structure tests
# ---------------------------------------------------------------------------

def test_pcim_v3_01_no_bare_pcim_in_analyst_upstreams():
    """v3 registry: no analyst has bare 'pcim' (whole-file) in upstream_modules."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    analyst_units = ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]
    for unit in analyst_units:
        upstreams = proposed["generation_units"][unit]["upstream_modules"]
        assert "pcim" not in upstreams, (
            f"{unit} still has bare 'pcim' in v3 upstream_modules: {upstreams}"
        )
        pcim_sections = [m for m in upstreams if m.startswith("pcim:")]
        assert len(pcim_sections) >= 16, (
            f"{unit} has fewer than 16 pcim: entries (need at least always_include): {len(pcim_sections)}"
        )


def test_pcim_v3_02_always_include_sections_in_every_analyst():
    """Every always_include section appears in every analyst's v3 upstream_modules."""
    from intelligence.evidence_fingerprints import PCIM_ALWAYS_INCLUDE_SECTIONS
    proposed = _load_registry(PROPOSED_M44_PATH)
    for unit in ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]:
        upstreams = set(proposed["generation_units"][unit]["upstream_modules"])
        for section in PCIM_ALWAYS_INCLUDE_SECTIONS:
            key = f"pcim:{section}"
            assert key in upstreams, (
                f"{unit} is missing always_include section {key} from v3 upstream"
            )


def test_pcim_v3_03_dependency_contract_version_is_3():
    """v3 registry must have dependency_contract_version == '3'."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    assert proposed.get("dependency_contract_version") == "3", (
        f"Expected '3', got '{proposed.get('dependency_contract_version')}'"
    )


def test_pcim_v3_04_committee_synthesis_unchanged():
    """committee_synthesis upstream_modules are unchanged between v2 and v3."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    proposed = _load_registry(PROPOSED_M44_PATH)
    assert (
        active["generation_units"]["committee_synthesis"]["upstream_modules"] ==
        proposed["generation_units"]["committee_synthesis"]["upstream_modules"]
    )


def test_pcim_v3_05_management_synthesis_unchanged():
    """how_good_is_management_synthesis upstream_modules are unchanged between v2 and v3."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    proposed = _load_registry(PROPOSED_M44_PATH)
    assert (
        active["generation_units"]["how_good_is_management_synthesis"]["upstream_modules"] ==
        proposed["generation_units"]["how_good_is_management_synthesis"]["upstream_modules"]
    )


def test_pcim_v3_06_4_company_stable_baseline_zero_calls():
    """With all 4 companies at stable evidence, v3 registry produces 0 planned AI calls."""
    from intelligence.regeneration_planner import plan_regeneration
    proposed = _load_registry(PROPOSED_M44_PATH)
    companies = ["sun_pharma", "tanla", "datapatterns", "ujjivan"]
    for company in companies:
        with patch("intelligence.regeneration_planner._load_dependency_registry", return_value=proposed):
            result = plan_regeneration(company)
        calls = result["answer_ai_calls_planned"]
        assert calls == 0, (
            f"{company}: expected 0 AI calls with stable evidence under v3, got {calls}"
        )


def test_pcim_v3_07_economic_attribution_change_graham_clean():
    """economic_attribution_inputs change → Graham CLEAN (not in Graham doctrine)."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    result = _plan_with_registry(proposed, changed_modules=["pcim:economic_attribution_inputs"])
    dirty = _dirty_units(result)
    assert "graham_panel" not in dirty, (
        f"Graham should be CLEAN when economic_attribution_inputs changes. Dirty: {dirty}"
    )


def test_pcim_v3_08_business_understanding_change_isolates_graham_munger():
    """business_understanding change → Graham and Munger CLEAN (not in their doctrines)."""
    proposed = _load_registry(PROPOSED_M44_PATH)
    result = _plan_with_registry(proposed, changed_modules=["pcim:business_understanding"])
    dirty = _dirty_units(result)
    assert "graham_panel" not in dirty, f"Graham should be CLEAN. Dirty: {dirty}"
    assert "munger_panel" not in dirty, f"Munger should be CLEAN. Dirty: {dirty}"
    # Buffett, Fisher, Lynch should be dirty
    for analyst in ["buffett_panel", "fisher_panel", "lynch_panel"]:
        assert analyst in dirty, f"{analyst} should be DIRTY. Dirty: {dirty}"
