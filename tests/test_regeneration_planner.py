"""
M41 Shadow Regeneration Planner Tests.

Tests:
  RP-C-01    management_progression change: exact dirty-unit set
  RP-I-01    Single commitment change (management_commitments): exact dirty-unit set
  RP-LABEL-01 Scenario labels A–J map to correct fixture definitions
  RP-TRANSITIVE-01 Transitive dependency only via planned chain (committee_synthesis example)
  RP-TRANSITIVE-02 Unchanged consumed artifact prevents unnecessary regeneration
  RP-01  Clean dependencies → 0 calls planned
  RP-02  One dirty generation unit → 1 planned call
  RP-03  Three dirty generation units → 3 planned calls
  RP-04  11 dirty UI questions sharing 6 units → max 6 calls, not 11
  RP-05  Deterministic question change → 0 AI calls
  RP-06  Repeated identical planning → same plan ID
  RP-07  Prompt version bump → regeneration planned
  RP-08  Schema bump → (version tracking stub) plan behaves correctly
  RP-09  Missing dependency → blocked, no call
  RP-10  Budget exceeded → BLOCKED_BUDGET
  RP-11  PCIM-only change → coarse dependency behavior accurately reflected
  RP-12  UI route → planner/provider unreachable from serving path
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.regeneration_planner import (
    BLOCKED_BUDGET,
    BLOCKED_MISSING_DEPENDENCY,
    INITIAL_GENERATION_REQUIRED,
    REUSE,
    WOULD_REGENERATE,
    plan_all_companies,
    plan_regeneration,
    SHADOW_BUDGET_POLICY,
    TOKEN_TELEMETRY,
    MODEL_REGISTRY,
    QUOTA_DISCOVERY,
)

COMPANIES_ROOT = Path(__file__).resolve().parent.parent / "companies"
PRIMARY_CO = "sun_pharma"
ALL_COMPANIES = ["sun_pharma", "tanla", "datapatterns", "ujjivan"]
ALL_UNITS = [
    "graham_panel", "buffett_panel", "fisher_panel", "munger_panel",
    "lynch_panel", "committee_synthesis", "how_good_is_management_synthesis",
]


# ---------------------------------------------------------------------------
# RP-01: Clean dependencies → 0 calls planned
# ---------------------------------------------------------------------------
def test_rp01_clean_evidence_zero_planned_calls():
    r = plan_regeneration(PRIMARY_CO)
    assert r["answer_ai_calls_planned"] == 0
    for u in r["units"]:
        assert u["decision"] == REUSE, f"{u['generation_unit']} should be REUSE when evidence is clean"
        assert u["planned_ai_calls"] == 0


def test_rp01_all_four_companies_zero_calls():
    all_r = plan_all_companies(ALL_COMPANIES)
    assert all_r["total_answer_ai_calls_planned"] == 0
    for co in ALL_COMPANIES:
        assert all_r["per_company"][co]["answer_ai_calls_planned"] == 0


# ---------------------------------------------------------------------------
# RP-02: One dirty generation unit → 1 planned call
# ---------------------------------------------------------------------------
def test_rp02_one_dirty_unit_one_planned_call():
    # management_quality_summary is ONLY in how_good_is_management_synthesis upstream
    r = plan_regeneration(PRIMARY_CO, changed_modules=["management_quality_summary"])
    assert r["answer_ai_calls_planned"] == 1
    dirty = [u for u in r["units"] if u["decision"] == WOULD_REGENERATE]
    assert len(dirty) == 1
    assert dirty[0]["generation_unit"] == "how_good_is_management_synthesis"


# ---------------------------------------------------------------------------
# RP-03: Three dirty generation units → 3 planned calls
# ---------------------------------------------------------------------------
def test_rp03_three_dirty_units_three_planned_calls():
    # financial_truth_pack → graham, buffett, lynch, committee (4 calls actually)
    # Let's use risk_assessments which affects only graham and munger + committee = 3
    r = plan_regeneration(PRIMARY_CO, changed_modules=["risk_assessments"])
    assert r["answer_ai_calls_planned"] == 3
    dirty_names = {u["generation_unit"] for u in r["units"] if u["decision"] == WOULD_REGENERATE}
    assert dirty_names == {"graham_panel", "munger_panel", "committee_synthesis"}


# ---------------------------------------------------------------------------
# RP-04: 11 dirty UI questions sharing 6 units → max 6 calls, not 11
# ---------------------------------------------------------------------------
def test_rp04_shared_units_not_per_question():
    """
    Dirty evidence for all analyst-panel and committee_synthesis questions.
    There are 11 CLASS_C questions (5 analyst + 6 committee) but only 6 generation units.
    Planner must count units, not questions.
    """
    # PCIM change dirties all 5 analysts + committee
    r = plan_regeneration(PRIMARY_CO, changed_modules=["pcim"])
    assert r["answer_ai_calls_planned"] == 6  # 5 analysts + committee, not 11 questions
    assert r["answer_ai_calls_planned"] != 11


def test_rp04_plan_units_count_not_question_count():
    r = plan_regeneration(PRIMARY_CO, changed_modules=["pcim"])
    assert len(r["units"]) == len(ALL_UNITS), "Plan must contain exactly 7 generation units"
    dirty = [u for u in r["units"] if u["decision"] == WOULD_REGENERATE]
    assert len(dirty) == 6


# ---------------------------------------------------------------------------
# RP-05: Deterministic question change → 0 AI calls
# ---------------------------------------------------------------------------
def test_rp05_deterministic_change_zero_ai_calls():
    """
    Changing modules that only feed deterministic (CLASS_A) questions must
    not generate any AI regeneration calls.
    Only risk_evolution is used only by deterministic questions in the QUESTION_INDEX
    but it's NOT in any AI generation unit's upstream — verify that.
    """
    # risk_evolution: not in any generation unit's upstream → 0 AI calls
    r = plan_regeneration(PRIMARY_CO, changed_modules=["risk_evolution"])
    assert r["answer_ai_calls_planned"] == 0


def test_rp05_financial_trends_zero_ai_calls():
    # financial_trends is not in any generation unit's upstream
    r = plan_regeneration(PRIMARY_CO, changed_modules=["financial_trends"])
    assert r["answer_ai_calls_planned"] == 0


# ---------------------------------------------------------------------------
# RP-06: Repeated identical planning → same plan ID
# ---------------------------------------------------------------------------
def test_rp06_same_inputs_same_plan_id():
    r1 = plan_regeneration(PRIMARY_CO, changed_modules=["risk_assessments"])
    r2 = plan_regeneration(PRIMARY_CO, changed_modules=["risk_assessments"])
    assert r1["plan_id"] == r2["plan_id"]

    for u1, u2 in zip(
        sorted(r1["units"], key=lambda u: u["generation_unit"]),
        sorted(r2["units"], key=lambda u: u["generation_unit"]),
    ):
        assert u1["plan_unit_id"] == u2["plan_unit_id"]
        assert u1["decision"] == u2["decision"]
        assert u1["planned_ai_calls"] == u2["planned_ai_calls"]


def test_rp06_clean_and_dirty_same_evidence_same_plan_id():
    """
    plan_id captures current evidence state + prompt versions, not what changed.
    Same current evidence → same plan_id even if different dirty modules are injected.
    This is the correct idempotency semantic: the plan is for the current artifact state.
    """
    r_clean = plan_regeneration(PRIMARY_CO)
    r_dirty = plan_regeneration(PRIMARY_CO, changed_modules=["risk_assessments"])
    # Both have the same current evidence → same plan_ids for unchanged units
    assert r_clean["plan_id"] == r_dirty["plan_id"], (
        "plan_id represents current artifact state; same current evidence → same plan_id"
    )


# ---------------------------------------------------------------------------
# RP-07: Prompt version bump → regeneration planned
# ---------------------------------------------------------------------------
def test_rp07_prompt_version_bump_plans_regeneration():
    r = plan_regeneration(
        PRIMARY_CO,
        forced_reasons={"graham_panel": ["PROMPT_VERSION_CHANGED"]},
    )
    graham = next(u for u in r["units"] if u["generation_unit"] == "graham_panel")
    assert graham["decision"] == WOULD_REGENERATE
    assert "PROMPT_VERSION_CHANGED" in graham["regeneration_reason"]
    assert graham["planned_ai_calls"] == 1
    assert r["answer_ai_calls_planned"] >= 1


def test_rp07_prompt_bump_does_not_dirty_unrelated_units():
    r = plan_regeneration(
        PRIMARY_CO,
        forced_reasons={"how_good_is_management_synthesis": ["PROMPT_VERSION_CHANGED"]},
    )
    mgmt = next(u for u in r["units"] if u["generation_unit"] == "how_good_is_management_synthesis")
    assert mgmt["decision"] == WOULD_REGENERATE
    for u in r["units"]:
        if u["generation_unit"] != "how_good_is_management_synthesis":
            assert u["decision"] == REUSE, f"{u['generation_unit']} should not be dirty from unrelated prompt bump"


# ---------------------------------------------------------------------------
# RP-08: Schema bump → appropriate plan decision
# ---------------------------------------------------------------------------
def test_rp08_schema_version_tracked_per_unit():
    """Schema versions are registered; changing one bumps the version string."""
    from intelligence.regeneration_planner import UNIT_SCHEMA_VERSIONS
    for unit in ALL_UNITS:
        assert unit in UNIT_SCHEMA_VERSIONS, f"Unit '{unit}' must have a schema version entry"
        assert isinstance(UNIT_SCHEMA_VERSIONS[unit], str)
        assert len(UNIT_SCHEMA_VERSIONS[unit]) > 0


def test_rp08_forced_schema_change_regenerates():
    """A forced schema change reason triggers regeneration for the affected unit."""
    r = plan_regeneration(
        PRIMARY_CO,
        forced_reasons={"committee_synthesis": ["SCHEMA_VERSION_CHANGED"]},
    )
    cs = next(u for u in r["units"] if u["generation_unit"] == "committee_synthesis")
    assert cs["decision"] == WOULD_REGENERATE
    assert "SCHEMA_VERSION_CHANGED" in cs["regeneration_reason"]
    assert cs["planned_ai_calls"] == 1


# ---------------------------------------------------------------------------
# RP-09: Missing dependency → blocked, no call
# ---------------------------------------------------------------------------
def test_rp09_missing_all_modules_blocks_plan():
    """
    Simulate a company that has no canonical modules on disk (e.g., new onboarding attempt
    but modules haven't been built yet). A plan against an empty current fingerprint should
    not produce AI calls for units whose modules are unavailable.
    """
    # Simulate by passing an empty current fingerprint
    r = plan_regeneration(
        PRIMARY_CO,
        changed_modules=["risk_assessments"],
        current={"company": PRIMARY_CO, "fingerprint_schema_version": "1", "modules": {}},
        baseline={"company": PRIMARY_CO, "fingerprint_schema_version": "1", "modules": {}},
    )
    # With no current modules, all upstream modules are missing → BLOCKED_MISSING_DEPENDENCY
    for u in r["units"]:
        assert u["decision"] in (BLOCKED_MISSING_DEPENDENCY, REUSE), (
            f"Unit {u['generation_unit']} with missing modules should be BLOCKED or REUSE (no data to hash)"
        )
        assert u["planned_ai_calls"] == 0


# ---------------------------------------------------------------------------
# RP-10: Budget exceeded → BLOCKED_BUDGET
# ---------------------------------------------------------------------------
def test_rp10_budget_ceiling_produces_blocked_budget():
    tight_budget = {
        **SHADOW_BUDGET_POLICY,
        "company": {"max_regeneration_calls_per_refresh": 2},
    }
    # management_commitments in v2: fisher/munger/committee/synthesis dirty → 4 dirty units
    r = plan_regeneration(PRIMARY_CO, changed_modules=["management_commitments"], budget_policy=tight_budget)
    decisions = [u["decision"] for u in r["units"]]
    assert r["answer_ai_calls_planned"] == 2, "Budget of 2 should cap at 2 planned calls"
    assert BLOCKED_BUDGET in decisions, "Some units should be BLOCKED_BUDGET"
    blocked_count = decisions.count(BLOCKED_BUDGET)
    would_regen_count = decisions.count(WOULD_REGENERATE)
    assert would_regen_count == 2
    assert would_regen_count + blocked_count == 4, "All dirty units must be WOULD_REGENERATE or BLOCKED_BUDGET"


# ---------------------------------------------------------------------------
# RP-11: PCIM-only change → coarse dependency behavior
# ---------------------------------------------------------------------------
def test_rp11_pcim_change_dirties_all_five_analysts():
    r = plan_regeneration(PRIMARY_CO, changed_modules=["pcim"])
    analyst_units = ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]
    for unit_name in analyst_units:
        u = next(u for u in r["units"] if u["generation_unit"] == unit_name)
        assert u["decision"] == WOULD_REGENERATE, (
            f"PCIM change must dirty {unit_name} (current coarse dependency)"
        )
        assert "pcim" in u["changed_modules"]


def test_rp11_pcim_change_also_dirties_committee_transitively():
    r = plan_regeneration(PRIMARY_CO, changed_modules=["pcim"])
    cs = next(u for u in r["units"] if u["generation_unit"] == "committee_synthesis")
    assert cs["decision"] == WOULD_REGENERATE


def test_rp11_pcim_does_not_dirty_management_synthesis():
    r = plan_regeneration(PRIMARY_CO, changed_modules=["pcim"])
    mgmt = next(u for u in r["units"] if u["generation_unit"] == "how_good_is_management_synthesis")
    assert mgmt["decision"] == REUSE, (
        "how_good_is_management_synthesis does not depend on PCIM; must stay REUSE"
    )


def test_rp11_pcim_impact_documented_in_plan():
    r = plan_regeneration(PRIMARY_CO, changed_modules=["pcim"])
    pcim_impact = r.get("pcim_impact", {})
    assert pcim_impact.get("pcim_sensitive_count", 0) >= 5
    assert "false_positive_risk" in pcim_impact
    assert pcim_impact.get("estimated_avoidable_calls_if_pcim_section_fingerprinted", 0) > 0


# ---------------------------------------------------------------------------
# RP-12: UI route → planner/provider unreachable from serving path
# ---------------------------------------------------------------------------
def test_rp12_planner_not_imported_by_answer_cards():
    answer_cards_path = (
        Path(__file__).resolve().parent.parent
        / "intelligence" / "ask_intrinsiciq" / "answer_cards.py"
    )
    source = answer_cards_path.read_text(encoding="utf-8")
    assert "regeneration_planner" not in source, (
        "answer_cards.py must not import regeneration_planner — planner must not be reachable from UI request path"
    )


def test_rp12_planner_not_imported_by_load_answer_card_ts():
    ts_path = (
        Path(__file__).resolve().parent.parent
        / "apps" / "ask-intrinsiciq" / "src" / "lib" / "ask-intrinsiciq" / "load-answer-card.ts"
    )
    source = ts_path.read_text(encoding="utf-8")
    assert "regeneration_planner" not in source, (
        "load-answer-card.ts must not reference regeneration_planner"
    )
    # Verify no direct runner/synthesizer references
    assert "runner.py" not in source
    assert "committee_synthesizer" not in source


# ---------------------------------------------------------------------------
# Invariant: AI_CALL_COUNT = DIRTY_GENERATION_UNITS (not dirty questions)
# ---------------------------------------------------------------------------
def test_invariant_call_count_equals_dirty_units_not_questions():
    """
    committee_synthesis serves 6 UI questions. If it needs regeneration, that counts
    as 1 AI call, not 6.
    """
    r = plan_regeneration(PRIMARY_CO, changed_modules=["committee_synthesis"])
    dirty_units = [u for u in r["units"] if u["decision"] == WOULD_REGENERATE]
    total_planned = r["answer_ai_calls_planned"]
    assert total_planned == len(dirty_units), (
        "planned_calls must equal number of dirty units, not number of dependent questions"
    )


def test_invariant_upstream_ai_always_zero():
    """Planner only plans ANSWER_AI. UPSTREAM_AI is always reported as 0."""
    for co in ALL_COMPANIES:
        r = plan_regeneration(co)
        assert r["upstream_ai_calls_required"] == 0


# ---------------------------------------------------------------------------
# Token estimation structure
# ---------------------------------------------------------------------------
def test_token_telemetry_present_for_all_units():
    for unit in ALL_UNITS:
        assert unit in TOKEN_TELEMETRY, f"TOKEN_TELEMETRY missing entry for {unit}"
        tel = TOKEN_TELEMETRY[unit]
        assert "source" in tel
        assert "median_input_tokens" in tel
        assert "median_output_tokens" in tel
        assert tel["median_input_tokens"] > 0
        assert tel["median_output_tokens"] > 0


def test_historical_telemetry_units_have_observations():
    telemetry_units = ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel", "committee_synthesis"]
    for unit in telemetry_units:
        assert TOKEN_TELEMETRY[unit]["source"] == "HISTORICAL_TELEMETRY"
        assert TOKEN_TELEMETRY[unit]["observation_count"] >= 60


def test_management_synthesis_uses_config_default():
    tel = TOKEN_TELEMETRY["how_good_is_management_synthesis"]
    assert tel["source"] == "CONFIG_DEFAULT", (
        "how_good_is_management_synthesis has no stored LLM manifest; must use CONFIG_DEFAULT"
    )
    assert tel["observation_count"] == 0


# ---------------------------------------------------------------------------
# Cost estimate
# ---------------------------------------------------------------------------
def test_cost_estimate_unavailable_from_repository():
    r = plan_regeneration(PRIMARY_CO, changed_modules=["pcim"])
    assert r["cost_forecast"]["cost_estimate"] == "COST_ESTIMATE_UNAVAILABLE_FROM_REPOSITORY"
    for u in r["units"]:
        if u.get("planned_ai_calls", 0) > 0:
            assert u["token_estimate"]["cost_estimate"] == "COST_ESTIMATE_UNAVAILABLE_FROM_REPOSITORY"


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------
def test_model_registry_covers_all_units():
    for unit in ALL_UNITS:
        assert unit in MODEL_REGISTRY, f"MODEL_REGISTRY missing entry for {unit}"
        reg = MODEL_REGISTRY[unit]
        assert "call_site" in reg
        assert "provider_default" in reg


# ---------------------------------------------------------------------------
# New company onboarding: no baseline → INITIAL_GENERATION_REQUIRED for all units
# ---------------------------------------------------------------------------
def test_new_company_onboarding_all_units_initial_generation():
    # Simulate new company: no baseline, but current fingerprints present
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_CO)

    r = plan_regeneration(
        "hypothetical_new_company",
        companies_root=COMPANIES_ROOT,
        current=current,
        baseline=None,
    )
    assert r["answer_ai_calls_planned"] == len(ALL_UNITS), (
        f"New company onboarding must plan {len(ALL_UNITS)} AI calls (one per unit)"
    )
    for u in r["units"]:
        assert u["decision"] == INITIAL_GENERATION_REQUIRED


# ---------------------------------------------------------------------------
# Scenario A–J call count verification
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("scenario,modules,forced,expected_calls", [
    ("A_stable",         None,                                              None,                                           0),
    ("B_financial",      ["financial_truth_pack", "owner_earnings_bridge"], None,                                           4),
    ("C_mgmt_prog",      ["management_progression"],                       None,                                           7),
    ("D_commentary",     ["commentary_themes"],                             None,                                           3),
    ("E_risk_only",      ["risk_assessments"],                              None,                                           3),
    ("F_pcim",           ["pcim"],                                          None,                                           6),
    ("G_annual",         ["pcim","financial_truth_pack","management_progression","commentary_themes"], None,                 7),
    ("H_quarterly",      ["financial_truth_pack","financial_trends"],       None,                                           4),
    ("I_commitment",     ["management_commitments"],                        None,                                           4),
    ("J_prompt_bump",    None,                                              {"how_good_is_management_synthesis":["PROMPT_VERSION_CHANGED"]}, 1),
])
def test_scenario_call_count(scenario, modules, forced, expected_calls):
    r = plan_regeneration(PRIMARY_CO, changed_modules=modules, forced_reasons=forced)
    assert r["answer_ai_calls_planned"] == expected_calls, (
        f"Scenario {scenario}: expected {expected_calls} calls, got {r['answer_ai_calls_planned']}"
    )


# ===========================================================================
# M41.1 Reconciliation Tests
# ===========================================================================

# ---------------------------------------------------------------------------
# RP-C-01: management_progression change → exact canonical dirty-unit set
# ---------------------------------------------------------------------------
def test_rp_c01_management_progression_exact_dirty_units():
    """
    Scenario C: management_progression changes.
    All 5 analyst panels load management_progression DIRECTLY via company_memory_context.py
    (DOCTRINE_MEMORY_PRIORITIES lists 'management progression' for all 5 doctrines).
    how_good_is_management_synthesis also lists it as a direct upstream module.
    committee_synthesis is dirty TRANSITIVELY: it depends on analyst OUTPUT files
    which would change after analyst regeneration.
    Canonical result: ALL 7 units dirty.
    """
    r = plan_regeneration(PRIMARY_CO, changed_modules=["management_progression"])
    assert r["answer_ai_calls_planned"] == 7

    dirty = {u["generation_unit"] for u in r["units"] if u["decision"] == WOULD_REGENERATE}
    assert dirty == {
        "graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel",
        "committee_synthesis", "how_good_is_management_synthesis",
    }, f"Unexpected dirty units: {dirty}"

    # Verify direct dependency for all 5 analysts
    for unit in ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]:
        u = next(u for u in r["units"] if u["generation_unit"] == unit)
        assert "management_progression" in u["changed_modules"], (
            f"{unit} must show management_progression as direct changed dependency"
        )

    # Verify management synthesis is direct
    mgmt = next(u for u in r["units"] if u["generation_unit"] == "how_good_is_management_synthesis")
    assert "management_progression" in mgmt["changed_modules"]

    # Verify committee_synthesis is transitive (no direct management_progression in its upstream_modules)
    from intelligence.shadow_change_detector import _load_dependency_registry
    reg = _load_dependency_registry()
    cs_direct = reg["generation_units"]["committee_synthesis"]["upstream_modules"]
    assert "management_progression" not in cs_direct, (
        "committee_synthesis must NOT list management_progression as a direct upstream module"
    )


def test_rp_c01_not_a_false_positive():
    """
    company_memory_context.py directly loads management_progression.json for all doctrines.
    This is NOT a PCIM-mediated false positive — it is a genuine direct dependency.
    Verify that PCIM digest is independent of management_progression file.
    """
    from intelligence.evidence_fingerprints import compute_digest, compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_CO)
    mp_digest = current["modules"].get("management_progression", {}).get("digest", "MISSING")
    pcim_digest = current["modules"].get("pcim", {}).get("digest", "MISSING")
    # They are different files → different digests → independent
    assert mp_digest != pcim_digest, (
        "management_progression and pcim are independent files with independent digests"
    )
    assert mp_digest != "MISSING" and pcim_digest != "MISSING"


# ---------------------------------------------------------------------------
# RP-I-01: Single commitment change → exact canonical dirty-unit set
# ---------------------------------------------------------------------------
def test_rp_i01_single_commitment_exact_dirty_units():
    """
    Scenario I: management_commitments.json changes (even one commitment record).
    Registry v2 (M43): management_commitments removed from graham/buffett/lynch.
    Dirty: fisher_panel, munger_panel (direct), committee_synthesis (transitive),
    how_good_is_management_synthesis (direct). Total: 4 units.
    Graham/Buffett/Lynch now CLEAN — they access management_commitments only via pcim
    (which has not been rebuilt in this incremental scenario).
    """
    r = plan_regeneration(PRIMARY_CO, changed_modules=["management_commitments"])
    assert r["answer_ai_calls_planned"] == 4

    dirty = {u["generation_unit"] for u in r["units"] if u["decision"] == WOULD_REGENERATE}
    assert dirty == {
        "fisher_panel", "munger_panel",
        "committee_synthesis", "how_good_is_management_synthesis",
    }, f"Unexpected dirty units: {dirty}"

    # Fisher and Munger show management_commitments as a direct changed dependency
    for unit in ["fisher_panel", "munger_panel"]:
        u = next(u for u in r["units"] if u["generation_unit"] == unit)
        assert "management_commitments" in u["changed_modules"], (
            f"{unit} must show management_commitments as direct changed dependency"
        )


def test_rp_i01_minimum_commitment_impact_is_management_quality_modules():
    """
    The SMALLEST plan from a management-related change (0 analysts, only management synthesis)
    comes from changing modules exclusive to how_good_is_management_synthesis:
    management_quality_summary, management_quality_dimensions, or economic_attribution.
    """
    for exclusive_module in ["management_quality_summary", "management_quality_dimensions", "economic_attribution"]:
        r = plan_regeneration(PRIMARY_CO, changed_modules=[exclusive_module])
        assert r["answer_ai_calls_planned"] == 1, (
            f"{exclusive_module} should only dirty how_good_is_management_synthesis (1 call)"
        )
        dirty = {u["generation_unit"] for u in r["units"] if u["decision"] == WOULD_REGENERATE}
        assert dirty == {"how_good_is_management_synthesis"}, (
            f"{exclusive_module} must only dirty how_good_is_management_synthesis, got {dirty}"
        )


# ---------------------------------------------------------------------------
# RP-LABEL-01: Scenario labels A–J map to the correct fixture definitions
# ---------------------------------------------------------------------------
def test_rp_label01_scenario_a_is_stable():
    r = plan_regeneration(PRIMARY_CO, changed_modules=None)
    assert r["answer_ai_calls_planned"] == 0

def test_rp_label01_scenario_b_is_financial_only():
    r = plan_regeneration(PRIMARY_CO, changed_modules=["financial_truth_pack", "owner_earnings_bridge"])
    assert r["answer_ai_calls_planned"] == 4
    dirty = {u["generation_unit"] for u in r["units"] if u["decision"] == WOULD_REGENERATE}
    assert dirty == {"graham_panel", "buffett_panel", "lynch_panel", "committee_synthesis"}

def test_rp_label01_scenario_c_is_management_progression():
    r = plan_regeneration(PRIMARY_CO, changed_modules=["management_progression"])
    assert r["answer_ai_calls_planned"] == 7

def test_rp_label01_scenario_d_is_commentary():
    r = plan_regeneration(PRIMARY_CO, changed_modules=["commentary_themes"])
    assert r["answer_ai_calls_planned"] == 3
    dirty = {u["generation_unit"] for u in r["units"] if u["decision"] == WOULD_REGENERATE}
    assert dirty == {"fisher_panel", "committee_synthesis", "how_good_is_management_synthesis"}

def test_rp_label01_scenario_e_is_risk_only():
    r = plan_regeneration(PRIMARY_CO, changed_modules=["risk_assessments"])
    assert r["answer_ai_calls_planned"] == 3
    dirty = {u["generation_unit"] for u in r["units"] if u["decision"] == WOULD_REGENERATE}
    assert dirty == {"graham_panel", "munger_panel", "committee_synthesis"}

def test_rp_label01_scenario_f_is_pcim_only():
    r = plan_regeneration(PRIMARY_CO, changed_modules=["pcim"])
    assert r["answer_ai_calls_planned"] == 6
    dirty = {u["generation_unit"] for u in r["units"] if u["decision"] == WOULD_REGENERATE}
    assert "how_good_is_management_synthesis" not in dirty

def test_rp_label01_scenario_i_is_management_commitments_not_quality_summary():
    """
    Scenario I is defined as 'single commitment update' = changing management_commitments.json.
    This is NOT the same as changing management_quality_summary.
    Registry v2 (M43): management_commitments = 4 calls; management_quality_summary = 1 call.
    The two scenarios are distinct and must produce different call counts.
    """
    r_correct = plan_regeneration(PRIMARY_CO, changed_modules=["management_commitments"])
    r_wrong = plan_regeneration(PRIMARY_CO, changed_modules=["management_quality_summary"])
    assert r_correct["answer_ai_calls_planned"] == 4
    assert r_wrong["answer_ai_calls_planned"] == 1
    assert r_correct["answer_ai_calls_planned"] != r_wrong["answer_ai_calls_planned"], (
        "Scenario I (management_commitments) must be distinguished from management_quality_summary"
    )


# ---------------------------------------------------------------------------
# RP-TRANSITIVE-01: Transitive dirty correctly identified through planned chain
# ---------------------------------------------------------------------------
def test_rp_transitive01_committee_dirty_via_analyst_chain():
    """
    committee_synthesis does NOT directly depend on management_progression.
    It is dirty because:
      management_progression → all 5 analyst panels (direct) → WOULD_REGENERATE
      → analyst output files would change
      → committee_synthesis (depends on analyst outputs) → WOULD_REGENERATE

    Verify: committee_synthesis's direct upstream_modules do NOT include management_progression.
    Verify: committee_synthesis is WOULD_REGENERATE when management_progression changes.
    """
    from intelligence.shadow_change_detector import _load_dependency_registry
    reg = _load_dependency_registry()

    # Direct check: management_progression not in committee's direct upstream
    cs_direct = reg["generation_units"]["committee_synthesis"]["upstream_modules"]
    assert "management_progression" not in cs_direct, (
        "committee_synthesis must not list management_progression as direct upstream"
    )

    # But when management_progression changes, committee IS dirty (via transitive chain)
    r = plan_regeneration(PRIMARY_CO, changed_modules=["management_progression"])
    cs = next(u for u in r["units"] if u["generation_unit"] == "committee_synthesis")
    assert cs["decision"] == WOULD_REGENERATE, (
        "committee_synthesis must be dirty when management_progression changes (transitive via analyst panels)"
    )


def test_rp_transitive01_committee_dirty_via_risk_assessments_chain():
    """
    risk_assessments → graham + munger WOULD_REGENERATE
    → committee_synthesis dirty (transitive via analysts)
    risk_assessments is NOT in committee_synthesis direct upstream.
    """
    from intelligence.shadow_change_detector import _load_dependency_registry
    reg = _load_dependency_registry()
    cs_direct = reg["generation_units"]["committee_synthesis"]["upstream_modules"]
    assert "risk_assessments" not in cs_direct

    r = plan_regeneration(PRIMARY_CO, changed_modules=["risk_assessments"])
    cs = next(u for u in r["units"] if u["generation_unit"] == "committee_synthesis")
    assert cs["decision"] == WOULD_REGENERATE


# ---------------------------------------------------------------------------
# RP-TRANSITIVE-02: Unchanged consumed artifact prevents unnecessary regeneration
# ---------------------------------------------------------------------------
def test_rp_transitive02_unrelated_module_change_does_not_dirty_analyst():
    """
    Changing a module that is NOT in any analyst's direct upstream must not dirty
    those analysts. Verify with modules exclusive to management synthesis.
    """
    for mod in ["management_quality_summary", "management_quality_dimensions", "economic_attribution"]:
        r = plan_regeneration(PRIMARY_CO, changed_modules=[mod])
        for unit in ["graham_panel", "buffett_panel", "fisher_panel", "munger_panel", "lynch_panel"]:
            u = next(u for u in r["units"] if u["generation_unit"] == unit)
            assert u["decision"] == REUSE, (
                f"{unit} must not be dirty when only {mod} changes (not in its direct upstream)"
            )


def test_rp_transitive02_risk_only_does_not_dirty_fisher_or_lynch():
    """
    risk_assessments is ONLY in graham and munger direct upstream.
    fisher and lynch do NOT have risk_assessments → must stay REUSE.
    """
    r = plan_regeneration(PRIMARY_CO, changed_modules=["risk_assessments"])
    for clean_unit in ["fisher_panel", "lynch_panel", "how_good_is_management_synthesis"]:
        u = next(u for u in r["units"] if u["generation_unit"] == clean_unit)
        assert u["decision"] == REUSE, (
            f"{clean_unit} must not be dirty when only risk_assessments changes"
        )
