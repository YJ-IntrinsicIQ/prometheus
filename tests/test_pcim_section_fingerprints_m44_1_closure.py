"""
M44.1 — PCIM Section-Fingerprint v3 Closure Verification.

Tests:
  M44C-01  57/57 PCIM top-level keys accounted for (6 classifications)
  M44C-02  43/43 section fingerprints map to canonical semantic sections
  M44C-03  5-run × 4-company section stability (43 sections × 4 companies × 5 runs)
  M44C-04  Active v3 registry baseline = 0 planned calls (all 4 companies)
  M44C-05  Relevant M43 commitment propagation: Fisher/Munger/Buffett/Lynch dirty, committee dirty
  M44C-06  Irrelevant M43 commitment: Graham/Buffett/Lynch clean, Fisher/Munger dirty via direct dep
  M44C-07  Every consumed pcim section in analyst upstream dirties that analyst
  M44C-08  Non-consumed pcim section (unique to other analysts) does not dirty unrelated analyst
  M44C-09  Missing required pcim section fingerprint → planner cannot find baseline digest
  M44C-10  v2/v3 registry divergence is fully explained (no bare 'pcim' in v3 analysts)
  M44C-11  Full PCIM whole-file digest remains available in fingerprint registry
  M44C-12  Active registry is v3 (dep_contract=3), v2 backup file exists

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
V2_BACKUP_PATH = REPO_ROOT / "governance" / "answer_dependency_registry.v2_pre_m44.json"
DOCTRINES_DIR = REPO_ROOT / "intelligence" / "investor_panel" / "doctrines"
PRIMARY_CO = "sun_pharma"
COMPANIES = ["sun_pharma", "tanla", "datapatterns", "ujjivan"]
ANALYSTS = ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]

# 57 PCIM key → classification
PCIM_KEY_CLASSIFICATIONS: Dict[str, Dict[str, Any]] = {
    # GLOBAL_METADATA — structural envelope fields, carry no semantic evidence content
    "company":                            {"class": "GLOBAL_METADATA",        "fingerprinted": False, "reason": "Company slug identifier, not evidence content"},
    "contract_version":                   {"class": "GLOBAL_METADATA",        "fingerprinted": False, "reason": "Schema contract version string, non-semantic"},
    "available_years":                    {"class": "GLOBAL_METADATA",        "fingerprinted": False, "reason": "Structural year enumeration, not evidence content"},
    "source_cim":                         {"class": "GLOBAL_METADATA",        "fingerprinted": False, "reason": "CIM reference pointer, not substantive evidence"},
    # NON_SEMANTIC_METADATA — pipeline execution artifacts excluded via NON_SEMANTIC_FIELDS
    "generated_at":                       {"class": "NON_SEMANTIC_METADATA",  "fingerprinted": False, "reason": "Generation timestamp — excluded by NON_SEMANTIC_FIELDS"},
    "business_identity_manifest":         {"class": "NON_SEMANTIC_METADATA",  "fingerprinted": False, "reason": "Pipeline artifact manifest, not evidence"},
    "financial_source_manifest":          {"class": "NON_SEMANTIC_METADATA",  "fingerprinted": False, "reason": "Pipeline artifact manifest, not evidence"},
    "pcim_source_manifest":               {"class": "NON_SEMANTIC_METADATA",  "fingerprinted": False, "reason": "Pipeline artifact manifest, not evidence"},
    # DERIVED_AGGREGATE — computed from consumed sections; analyst dirty via contributing section
    "evidence_map":                       {"class": "DERIVED_AGGREGATE",      "fingerprinted": False, "reason": "Computed index over all sections; analyst dirty via section change"},
    "uncertainty_missing_data":           {"class": "DERIVED_AGGREGATE",      "fingerprinted": False, "reason": "Derived missing-data summary; analyst dirty via section change"},
    # COUPLED_WITH_SECTION — boolean derived from financial_panel_status; changes iff status changes
    "financial_panel_ready":              {"class": "COUPLED_WITH_SECTION",   "fingerprinted": False, "reason": "Boolean summary of financial_panel_status; fingerprinting status covers it"},
    # SEMANTIC_SECTION (no analyst consumer) — real semantic content but no analyst reads it via doctrine
    "business_context":                   {"class": "SEMANTIC_SECTION",       "fingerprinted": False, "reason": "No analyst has this in evidence_required_from_pcim or always_include"},
    "financial_trend_inputs":             {"class": "SEMANTIC_SECTION",       "fingerprinted": False, "reason": "No analyst has this in evidence_required_from_pcim or always_include"},
    "incentive_inputs":                   {"class": "SEMANTIC_SECTION",       "fingerprinted": False, "reason": "No analyst has this in evidence_required_from_pcim or always_include; governance_and_incentive_inputs covers incentive semantics"},
    # SEMANTIC_SECTION (fingerprinted) — always_include set (16 sections)
    "financial_truth_inputs":             {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — financial quality gate, consumed by all analysts"},
    "financial_snapshot_inputs":          {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — current-period financial position"},
    "owner_earnings_readiness_inputs":    {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — FCF/owner-earnings quality gate"},
    "working_capital_quality_inputs":     {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — working capital quality gate"},
    "capital_allocation_financial_inputs":{"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — capex and ROIC data"},
    "per_share_compounding_inputs":       {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — per-share trajectory"},
    "unreliable_financial_inputs":        {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — reliability-flagged financials"},
    "invalid_or_quarantined_financial_inputs": {"class": "SEMANTIC_SECTION",  "fingerprinted": True,  "reason": "always_include — quarantined financial data"},
    "precise_missing_financial_inputs":   {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — known missing data map"},
    "financial_warning_policy":           {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — financial panel policy"},
    "financial_panel_status":             {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — panel readiness status"},
    "financial_panel_usable_domains":     {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — available financial domains"},
    "financial_panel_limited_domains":    {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — limited financial domains"},
    "financial_panel_blocked_domains":    {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — blocked financial domains"},
    "investor_financial_questions":       {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — investor financial question set"},
    "multi_year_financial_inputs":        {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "always_include — multi-year financial history"},
    # SEMANTIC_SECTION (fingerprinted) — doctrine-specific sections (27 sections)
    "balance_sheet_strength_inputs":      {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Graham, Buffett, Munger, Lynch doctrine"},
    "business_economics_inputs":          {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "All 5 analyst doctrines"},
    "business_understanding":             {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Buffett, Fisher, Lynch doctrine"},
    "capital_allocation_inputs":          {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Graham, Munger doctrine"},
    "cash_conversion_inputs":             {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Graham, Munger doctrine"},
    "corporate_action_inputs":            {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Munger, Lynch doctrine"},
    "economic_attribution_inputs":        {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Buffett, Fisher, Munger, Lynch doctrine"},
    "financial_driver_inputs":            {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "All 5 analyst doctrines"},
    "financial_fundamentals_inputs":      {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Graham, Buffett doctrine"},
    "financial_growth_inputs":            {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Buffett, Fisher, Lynch doctrine"},
    "financial_quality_inputs":           {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "All 5 analyst doctrines"},
    "financial_strength_inputs":          {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Graham doctrine"},
    "governance_and_incentive_inputs":    {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Graham, Buffett, Munger doctrine"},
    "growth_execution_inputs":            {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Fisher, Lynch doctrine"},
    "growth_quality_inputs":              {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Fisher, Lynch doctrine"},
    "management_execution_inputs":        {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Buffett, Fisher, Munger, Lynch doctrine"},
    "management_quality_inputs":          {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Buffett, Fisher, Munger, Lynch doctrine (includes promise_tracker)"},
    "moat_inputs":                        {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Buffett, Fisher doctrine"},
    "multi_year_inputs":                  {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "All 5 analyst doctrines"},
    "ownership_inputs":                   {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Munger doctrine"},
    "per_share_inputs":                   {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Graham, Buffett, Lynch doctrine"},
    "profitability_inputs":               {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Buffett, Fisher, Lynch doctrine"},
    "return_on_capital_inputs":           {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Buffett doctrine"},
    "risk_inputs":                        {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Graham, Munger doctrine"},
    "simplicity_and_story_inputs":        {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Lynch doctrine"},
    "story_vs_numbers_inputs":            {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Lynch doctrine"},
    "working_capital_inputs":             {"class": "SEMANTIC_SECTION",       "fingerprinted": True,  "reason": "Graham, Fisher, Munger doctrine"},
}


def _load_registry(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _plan_with_registry(registry: Dict[str, Any], changed_modules):
    from intelligence.regeneration_planner import plan_regeneration
    with patch("intelligence.regeneration_planner._load_dependency_registry", return_value=registry):
        result = plan_regeneration(PRIMARY_CO, changed_modules=changed_modules)
    return result


def _dirty_units(result: Dict[str, Any]) -> Set[str]:
    return {u["generation_unit"] for u in result["units"] if u["decision"] == "WOULD_REGENERATE"}


# ---------------------------------------------------------------------------
# M44C-01: 57/57 PCIM keys accounted for
# ---------------------------------------------------------------------------

def test_m44c_01_57_pcim_keys_accounted_for():
    """57/57 PCIM top-level keys have a classification in PCIM_KEY_CLASSIFICATIONS."""
    pcim = json.loads(
        (REPO_ROOT / "companies" / PRIMARY_CO / "company_memory" / "pcim_v1.json").read_text()
    )
    pcim_keys = set(pcim.keys())
    classified_keys = set(PCIM_KEY_CLASSIFICATIONS.keys())
    # All actual PCIM keys must be classified
    unclassified = pcim_keys - classified_keys
    assert not unclassified, f"Unclassified PCIM keys: {sorted(unclassified)}"
    assert len(pcim_keys) == 57, f"Expected 57 top-level PCIM keys, got {len(pcim_keys)}"
    # Count fingerprinted vs not
    fingerprinted = [k for k, v in PCIM_KEY_CLASSIFICATIONS.items() if v["fingerprinted"]]
    assert len(fingerprinted) == 43, f"Expected 43 fingerprinted sections, got {len(fingerprinted)}"
    not_fp = [k for k, v in PCIM_KEY_CLASSIFICATIONS.items() if not v["fingerprinted"]]
    assert len(not_fp) == 14, f"Expected 14 non-fingerprinted keys, got {len(not_fp)}"


# ---------------------------------------------------------------------------
# M44C-02: 43 section fingerprints map to canonical semantic sections
# ---------------------------------------------------------------------------

def test_m44c_02_43_section_fingerprints_are_semantic():
    """Every fingerprinted section is classified SEMANTIC_SECTION with fingerprinted=True."""
    from intelligence.evidence_fingerprints import PCIM_SECTION_FINGERPRINT_CANDIDATES
    assert len(PCIM_SECTION_FINGERPRINT_CANDIDATES) == 43, (
        f"Expected 43 candidates, got {len(PCIM_SECTION_FINGERPRINT_CANDIDATES)}"
    )
    for section in PCIM_SECTION_FINGERPRINT_CANDIDATES:
        assert section in PCIM_KEY_CLASSIFICATIONS, f"Section {section} not in key classifications"
        rec = PCIM_KEY_CLASSIFICATIONS[section]
        assert rec["class"] == "SEMANTIC_SECTION", (
            f"{section} is classified as '{rec['class']}', expected SEMANTIC_SECTION"
        )
        assert rec["fingerprinted"] is True, f"{section} has fingerprinted=False"
    # Verify all SEMANTIC_SECTION+fingerprinted keys are exactly the candidates
    classified_fp = {k for k, v in PCIM_KEY_CLASSIFICATIONS.items()
                     if v["class"] == "SEMANTIC_SECTION" and v["fingerprinted"]}
    assert classified_fp == PCIM_SECTION_FINGERPRINT_CANDIDATES, (
        f"Mismatch: classified={sorted(classified_fp)}, candidates={sorted(PCIM_SECTION_FINGERPRINT_CANDIDATES)}"
    )


# ---------------------------------------------------------------------------
# M44C-03: 5-run × 4-company section stability
# ---------------------------------------------------------------------------

def test_m44c_03_5run_4company_section_stability():
    """Section fingerprints are deterministic: 43 sections × 4 companies × 5 runs."""
    from intelligence.evidence_fingerprints import compute_pcim_section_fingerprints
    for company in COMPANIES:
        pcim = json.loads(
            (REPO_ROOT / "companies" / company / "company_memory" / "pcim_v1.json").read_text()
        )
        first = compute_pcim_section_fingerprints(pcim)
        assert len(first) == 43, f"{company}: expected 43 sections, got {len(first)}"
        for run in range(1, 5):
            run_result = compute_pcim_section_fingerprints(pcim)
            assert run_result == first, (
                f"{company}: section fingerprints non-deterministic on run {run + 1}"
            )


# ---------------------------------------------------------------------------
# M44C-04: Active v3 registry baseline = 0 planned calls
# ---------------------------------------------------------------------------

def test_m44c_04_active_v3_baseline_zero_calls():
    """Active registry v3 produces 0 planned AI calls for all 4 companies with stable evidence."""
    from intelligence.regeneration_planner import plan_regeneration
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    assert active["dependency_contract_version"] == "3", (
        f"Active registry is not v3: {active['dependency_contract_version']}"
    )
    for company in COMPANIES:
        with patch("intelligence.regeneration_planner._load_dependency_registry", return_value=active):
            result = plan_regeneration(company)
        calls = result["answer_ai_calls_planned"]
        assert calls == 0, f"{company}: expected 0 planned calls under v3, got {calls}"


# ---------------------------------------------------------------------------
# M44C-05: Relevant M43 commitment propagation preserved
# ---------------------------------------------------------------------------

def test_m44c_05_relevant_commitment_propagation_preserved():
    """Relevant management_commitments change + management_quality_inputs section change
    dirties Buffett, Fisher, Munger, Lynch, committee. How-good-is-management dirty."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    result = _plan_with_registry(
        active,
        changed_modules=["management_commitments", "pcim:management_quality_inputs"]
    )
    dirty = _dirty_units(result)
    # Fisher/Munger have direct management_commitments dep
    assert "fisher_panel" in dirty, f"Fisher should be dirty. Dirty={dirty}"
    assert "munger_panel" in dirty, f"Munger should be dirty. Dirty={dirty}"
    # Buffett/Lynch dirty via pcim:management_quality_inputs
    assert "buffett_panel" in dirty, f"Buffett should be dirty via pcim:management_quality_inputs. Dirty={dirty}"
    assert "lynch_panel" in dirty, f"Lynch should be dirty via pcim:management_quality_inputs. Dirty={dirty}"
    # Committee dirty transitively via analysts
    assert "committee_synthesis" in dirty, f"committee_synthesis should be dirty. Dirty={dirty}"
    # how_good_is_management dirty via management_commitments direct dep
    assert "how_good_is_management_synthesis" in dirty, (
        f"how_good_is_management_synthesis should be dirty. Dirty={dirty}"
    )


# ---------------------------------------------------------------------------
# M44C-06: Irrelevant commitment (management_commitments only, pcim unchanged)
# ---------------------------------------------------------------------------

def test_m44c_06_irrelevant_commitment_selective():
    """management_commitments change alone (pcim unchanged): Graham/Buffett/Lynch clean.
    Fisher/Munger dirty via direct dep. M43 regression verified."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    result = _plan_with_registry(active, changed_modules=["management_commitments"])
    dirty = _dirty_units(result)
    # Graham has no management_commitments dep
    assert "graham_panel" not in dirty, f"Graham should be CLEAN. Dirty={dirty}"
    # Buffett/Lynch removed management_commitments dep in M43
    assert "buffett_panel" not in dirty, f"Buffett should be CLEAN. Dirty={dirty}"
    assert "lynch_panel" not in dirty, f"Lynch should be CLEAN. Dirty={dirty}"
    # Fisher/Munger retained management_commitments dep (position 2 DOCTRINE_MEMORY_PRIORITIES)
    assert "fisher_panel" in dirty, f"Fisher should be dirty. Dirty={dirty}"
    assert "munger_panel" in dirty, f"Munger should be dirty. Dirty={dirty}"


# ---------------------------------------------------------------------------
# M44C-07: Every consumed pcim section dirties its analyst (no false-clean)
# ---------------------------------------------------------------------------

def test_m44c_07_consumed_section_dirties_analyst():
    """For each analyst, changing all its consumed pcim: sections makes it dirty.
    Uses batch (all sections at once per analyst) for efficiency."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    for unit in ANALYSTS:
        consumed_sections = [
            m for m in active["generation_units"][unit]["upstream_modules"]
            if m.startswith("pcim:")
        ]
        assert consumed_sections, f"{unit} has no pcim: section upstreams"
        result = _plan_with_registry(active, changed_modules=consumed_sections)
        dirty = _dirty_units(result)
        assert unit in dirty, (
            f"FALSE_CLEAN: {unit} not dirty when all its consumed pcim sections change. "
            f"Consumed: {consumed_sections}, dirty: {dirty}"
        )


# ---------------------------------------------------------------------------
# M44C-08: Non-consumed section does not dirty unrelated analyst
# ---------------------------------------------------------------------------

def test_m44c_08_non_consumed_section_does_not_dirty_unrelated():
    """Sections unique to specific analysts do not dirty unrelated analysts.
    Risk_inputs (Graham+Munger only): Buffett/Fisher/Lynch stay clean.
    Management_quality_inputs (Buffett/Fisher/Munger/Lynch): Graham stays clean.
    Business_understanding (Buffett/Fisher/Lynch): Graham/Munger stay clean."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)

    # risk_inputs: Graham+Munger only
    r = _plan_with_registry(active, changed_modules=["pcim:risk_inputs"])
    dirty = _dirty_units(r)
    for unit in ["buffett_panel", "fisher_panel", "lynch_panel"]:
        assert unit not in dirty, f"{unit} should be CLEAN when risk_inputs changes. Dirty={dirty}"

    # management_quality_inputs: Buffett/Fisher/Munger/Lynch, NOT Graham
    r = _plan_with_registry(active, changed_modules=["pcim:management_quality_inputs"])
    dirty = _dirty_units(r)
    assert "graham_panel" not in dirty, (
        f"Graham should be CLEAN when management_quality_inputs changes. Dirty={dirty}"
    )

    # business_understanding: Buffett/Fisher/Lynch, NOT Graham/Munger
    r = _plan_with_registry(active, changed_modules=["pcim:business_understanding"])
    dirty = _dirty_units(r)
    for unit in ["graham_panel", "munger_panel"]:
        assert unit not in dirty, (
            f"{unit} should be CLEAN when business_understanding changes. Dirty={dirty}"
        )


# ---------------------------------------------------------------------------
# M44C-09: Missing required section never resolves CLEAN
# ---------------------------------------------------------------------------

def test_m44c_09_missing_section_in_registry_becomes_missing_baseline():
    """If a required pcim:section entry is absent from the stored baseline (new section
    added to registry without recomputing fingerprints), the planner sees MISSING_BASELINE
    for that module, which causes the unit to be dirty — not clean."""
    from intelligence.evidence_fingerprints import compare_fingerprints, compute_company_fingerprints
    # Build current fingerprints
    current = compute_company_fingerprints(PRIMARY_CO)
    # Build a synthetic 'baseline' that lacks a key always_include section
    baseline = json.loads(
        (REPO_ROOT / "companies" / PRIMARY_CO / "company_memory" / "ask_intrinsiciq"
         / "evidence_fingerprint_registry.json").read_text()
    )
    baseline_missing = copy.deepcopy(baseline)
    # Remove pcim:financial_truth_inputs from baseline to simulate a new section being added
    removed = baseline_missing["modules"].pop("pcim:financial_truth_inputs", None)
    assert removed is not None, "pcim:financial_truth_inputs not in stored baseline"
    comparison = compare_fingerprints(current, baseline_missing)
    # Should be MISSING_BASELINE (in current but not in baseline)
    assert comparison.get("pcim:financial_truth_inputs") == "MISSING_BASELINE", (
        f"Expected MISSING_BASELINE, got {comparison.get('pcim:financial_truth_inputs')}"
    )


# ---------------------------------------------------------------------------
# M44C-10: v2/v3 divergence is fully explained (no bare 'pcim' in v3 analysts)
# ---------------------------------------------------------------------------

def test_m44c_10_v2_v3_divergence_fully_explained():
    """Every analyst unit that changed between v2 and v3 changed because:
    - bare 'pcim' was removed, and
    - pcim:<section> entries were added.
    No other upstream_modules were changed for these units."""
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    v2 = _load_registry(V2_BACKUP_PATH)
    for unit in ANALYSTS:
        v3_upstreams = set(active["generation_units"][unit]["upstream_modules"])
        v2_upstreams = set(v2["generation_units"][unit]["upstream_modules"])
        # v3 must NOT have bare 'pcim'
        assert "pcim" not in v3_upstreams, f"{unit}: bare 'pcim' still in v3"
        # v2 must have bare 'pcim'
        assert "pcim" in v2_upstreams, f"{unit}: v2 should have bare 'pcim'"
        # Non-pcim upstreams must be identical
        v3_non_pcim = {m for m in v3_upstreams if not m.startswith("pcim")}
        v2_non_pcim = {m for m in v2_upstreams if not m.startswith("pcim")}
        assert v3_non_pcim == v2_non_pcim, (
            f"{unit}: non-pcim upstreams diverged between v2 and v3. "
            f"Added: {v3_non_pcim - v2_non_pcim}, Removed: {v2_non_pcim - v3_non_pcim}"
        )


# ---------------------------------------------------------------------------
# M44C-11: Full PCIM whole-file digest remains available
# ---------------------------------------------------------------------------

def test_m44c_11_whole_pcim_digest_available():
    """The whole-file 'pcim' digest remains present in the fingerprint registry
    alongside the per-section pcim:section entries."""
    for company in COMPANIES:
        reg = json.loads(
            (REPO_ROOT / "companies" / company / "company_memory" / "ask_intrinsiciq"
             / "evidence_fingerprint_registry.json").read_text()
        )
        modules = reg["modules"]
        assert "pcim" in modules, f"{company}: whole-file 'pcim' digest missing from registry"
        assert modules["pcim"]["digest"].startswith("sha256:"), (
            f"{company}: 'pcim' digest malformed"
        )
        section_keys = [k for k in modules if k.startswith("pcim:")]
        assert len(section_keys) >= 40, (
            f"{company}: expected ≥40 pcim: section entries, got {len(section_keys)}"
        )


# ---------------------------------------------------------------------------
# M44C-12: Active registry is v3, v2 backup exists
# ---------------------------------------------------------------------------

def test_m44c_12_active_v3_and_v2_backup_exist():
    """Active registry is dependency_contract_version='3'; v2 backup exists with version '2'."""
    assert ACTIVE_REGISTRY_PATH.exists(), "Active registry file missing"
    assert V2_BACKUP_PATH.exists(), "v2 backup file missing"
    active = _load_registry(ACTIVE_REGISTRY_PATH)
    v2 = _load_registry(V2_BACKUP_PATH)
    assert active["dependency_contract_version"] == "3", (
        f"Active registry not v3: {active['dependency_contract_version']}"
    )
    assert v2["dependency_contract_version"] == "2", (
        f"v2 backup not v2: {v2['dependency_contract_version']}"
    )
    # Active has no bare 'pcim' in any analyst
    for unit in ANALYSTS:
        upstreams = active["generation_units"][unit]["upstream_modules"]
        assert "pcim" not in upstreams, f"Active registry: {unit} still has bare 'pcim'"
    # v2 backup has bare 'pcim' in all analysts
    for unit in ANALYSTS:
        upstreams = v2["generation_units"][unit]["upstream_modules"]
        assert "pcim" in upstreams, f"v2 backup: {unit} should have bare 'pcim'"
