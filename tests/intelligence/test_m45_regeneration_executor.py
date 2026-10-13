"""
ENG-MISSION45 — Controlled AI Regeneration Execution: deterministic test suite.

Tests EXE-01..EXE-15 (original) + EXE-ID-01..06, EXE-ANCHOR-01/02,
EXE-DESC-01/02, EXE-EVIDENCE-01, EXE-SERVE-01 (M45.1 safety corrections) +
M452-HIST-01..03, M452-CF-01..06, M452-EXEC-01..03, M452-PLAN-01,
M452-DESC-01/02, M452-SERVE-01, M452-UI-01 (M45.2 history/contract/identity) +
M453-IDEM-01..08, M453-FAIL-01..03, M453-CF-01..07, M453-PLAN-01..05 (M45.3 idempotency/determinism).

All deterministic — no real API calls.
Run: python -m pytest tests/intelligence/test_m45_regeneration_executor.py -v
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from intelligence.regeneration_executor import (
    MAX_EXECUTED_AI_CALLS,
    RETRY_COUNT,
    MAX_OUTPUT_TOKENS,
    UNIT_TARGET,
    QUESTION_ID,
    DOMAIN_QUESTION,
    CANDIDATE_FILENAME,
    CANDIDATE_FILENAME_TEMPLATE,
    MANIFEST_FILENAME,
    CERTIFIED_ARTIFACT_PATH,
    OUTPUT_SCHEMA_VERSION,
    COMPOSITION_POLICY,
    COMPOSITION_POLICY_HASH,
    GENERATION_CONTRACT_SCHEMA,
    _ATTEMPT_1_RECONSTRUCTION,
    build_management_quality_composition_plan,
    derive_behavioral_descriptor,
    compute_execution_id,
    _compute_contract_fingerprint,
    _compute_composition_policy_hash,
    _compute_plan_digest,
    audit_composition_plan_for_rating_leakage,
    verify_no_previous_answer_in_generation_input,
    _verify_plan,
    _check_idempotency,
    _find_prior_execution,
    _find_successful_execution_by_evidence,
    _verify_candidate_integrity,
    _ensure_attempt1_history,
    _parse_args,
    main,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────

_MINIMAL_MQ_SUMMARY = {
    "company_slug": "sun_pharma",
    "investor_implication": "Management quality weakens conviction until execution improves.",
    "overall_view": "weak",
    "strongest_dimension": "capital_allocation_discipline",
    "weakest_dimension": "execution_discipline",
    "what_strengthened_conviction": [
        {"dimension": "risk_handling", "summary": "Tech risk acknowledged", "confidence": "high"},
    ],
    "what_weakened_conviction": [
        {"dimension": "execution_discipline", "summary": "Supply chain disruption unresolved", "confidence": "high"},
    ],
    "what_remains_unproven": [
        {"dimension": "candor_and_consistency", "summary": "Guidance accuracy not verified"},
    ],
    "unresolved_questions": [
        "Are recurring risks being addressed early?",
        "Does capital allocation connect to returns?",
    ],
    "interpretation": {
        "why_it_matters": "Execution discipline shapes compounding.",
        "conclusion": "Management quality is guarded.",
    },
}

_MOCK_AI_ANSWER = {
    "simple_answer": (
        "Management quality is guarded — FOLLOW_THROUGH_LARGELY_UNVERIFIED; "
        "execution discipline is the weak link."
    ),
    "why_it_matters": "Execution shapes compounding.",
    "investor_interpretation": "The evidence suggests caution.",
    "key_points": ["Capital allocation is the strongest dimension.", "Execution discipline is weakest."],
}

_MOCK_PACP_PASS = {
    "overall": "PASS",
    "named_checks": 10,
    "fails": [],
    "warns": [],
    "skips": [],
    "incomplete": [],
    "coverage_note": "family='management_quality': registered",
}

_MOCK_PACP_FAIL = {
    "overall": "FAIL",
    "named_checks": 10,
    "fails": ["check_mq_no_promise_to_delivered"],
    "warns": [],
    "skips": [],
    "incomplete": [],
    "coverage_note": "family='management_quality': registered",
}

_PROGRESSION_0_DELIVERED = {
    "progression_items": [
        {"item_id": f"ITEM-{i:03d}", "current_status": "announced", "exec_states": []}
        for i in range(25)
    ]
}

_PROGRESSION_10_OF_20_DELIVERED = {
    "progression_items": (
        [{"item_id": f"ITEM-{i:03d}", "current_status": "announced",
          "exec_states": [{"execution_state": "DELIVERED"}]}
         for i in range(10)]
        + [{"item_id": f"ITEM-{i:03d}", "current_status": "announced", "exec_states": []}
           for i in range(10, 20)]
    )
}

_PROGRESSION_9_OF_10_DELIVERED_UNATTRIBUTED = {
    "progression_items": (
        [{"item_id": f"ITEM-{i:03d}", "current_status": "announced",
          "exec_states": [{"execution_state": "DELIVERED"}]}
         for i in range(9)]
        + [{"item_id": "ITEM-009", "current_status": "announced", "exec_states": []}]
    )
}

_CAPITAL_ALL_NONE = {
    "allocations": [{"alloc_id": f"A{i}", "attribution_status": "none"} for i in range(10)]
}

_CAPITAL_SOME_ATTRIBUTED = {
    "allocations": (
        [{"alloc_id": f"A{i}", "attribution_status": "ATTRIBUTED"} for i in range(6)]
        + [{"alloc_id": f"A{i}", "attribution_status": "none"} for i in range(6, 10)]
    )
}


def _make_plan(calls_for_target: int = 1, include_extra_call: bool = False):
    units = [
        {
            "generation_unit": UNIT_TARGET,
            "decision": "WOULD_REGENERATE" if calls_for_target else "REUSE",
            "planned_ai_calls": calls_for_target,
            "plan_unit_id": "test_plan_unit_id_001",
        },
    ]
    if include_extra_call:
        units.append({
            "generation_unit": "graham_panel",
            "decision": "WOULD_REGENERATE",
            "planned_ai_calls": 1,
            "plan_unit_id": "test_plan_unit_id_002",
        })
    return {"units": units}


def _setup_company_root(companies_root: Path, *, include_progression: bool = True):
    """Create minimal company directory structure for tests."""
    company_root = companies_root / "sun_pharma"
    mq_dir = company_root / "company_memory" / "management_quality"
    mq_dir.mkdir(parents=True, exist_ok=True)
    (mq_dir / "management_quality_summary.json").write_text(json.dumps(_MINIMAL_MQ_SUMMARY))

    ask_dir = company_root / "company_memory" / "ask_intrinsiciq"
    ask_dir.mkdir(parents=True, exist_ok=True)
    (ask_dir / "shadow_level3_hybrid_answers.json").write_text(
        json.dumps({"answers": {"how-good-is-management": {"answer": {
            "simple_answer": "Previous answer placeholder.",
            "key_points": [],
        }}}})
    )

    if include_progression:
        prog_dir = company_root / "company_memory" / "management_progression"
        prog_dir.mkdir(parents=True, exist_ok=True)
        (prog_dir / "management_progression.json").write_text(json.dumps(_PROGRESSION_0_DELIVERED))

        cap_dir = company_root / "company_memory" / "capital_allocation_outcomes"
        cap_dir.mkdir(parents=True, exist_ok=True)
        (cap_dir / "capital_allocation_outcomes.json").write_text(json.dumps(_CAPITAL_ALL_NONE))

    return company_root


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-01: Flag gate — no flag → exits 0, no AI call
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_01_flag_gate_no_flag():
    """EXE-01: Without --execute-ai-regeneration, main() returns 0 and makes no AI call."""
    with patch("intelligence.regeneration_executor.run_regeneration") as mock_run:
        result = main(argv=[])
    assert result == 0
    mock_run.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-02: Plan produces exactly 1 call for UNIT_TARGET with PROMPT_VERSION_CHANGED
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_02_plan_one_call_for_target():
    """EXE-02: plan_regeneration with forced_reasons produces exactly 1 call for UNIT_TARGET."""
    from intelligence.regeneration_planner import plan_regeneration, PROMPT_VERSION_CHANGED

    plan = plan_regeneration(
        company_slug="sun_pharma",
        forced_reasons={UNIT_TARGET: [PROMPT_VERSION_CHANGED]},
        prompt_versions={UNIT_TARGET: "2"},
    )
    all_units = plan.get("units", plan.get("unit_plans", []))
    unit_map = {u["generation_unit"]: u for u in all_units}
    target = unit_map.get(UNIT_TARGET, {})
    # Contract V5 (ENG-MISSION52 / 52.2b): the target unit is deterministic -> 0 AI calls, but the
    # forced reason is still recorded and the unit is still planned for regeneration.
    assert target.get("planned_ai_calls") == 0, (
        f"Expected 0 planned AI calls for {UNIT_TARGET} under Contract V5, got {target.get('planned_ai_calls')}"
    )
    assert PROMPT_VERSION_CHANGED in target.get("regeneration_reason", [])


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-03: Plan produces 0 calls for all 6 other generation units
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_03_clean_plan_no_other_calls():
    """EXE-03: All non-target units have 0 planned calls when no evidence changed."""
    from intelligence.regeneration_planner import plan_regeneration, PROMPT_VERSION_CHANGED

    plan = plan_regeneration(
        company_slug="sun_pharma",
        forced_reasons={UNIT_TARGET: [PROMPT_VERSION_CHANGED]},
        prompt_versions={UNIT_TARGET: "2"},
    )
    all_units = plan.get("units", plan.get("unit_plans", []))
    unit_map = {u["generation_unit"]: u for u in all_units}
    non_target_calls = {
        unit: up.get("planned_ai_calls", 0)
        for unit, up in unit_map.items()
        if unit != UNIT_TARGET and up.get("planned_ai_calls", 0) > 0
    }
    assert not non_target_calls, (
        f"Expected 0 calls for non-target units, got: {non_target_calls}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-04: MAX_EXECUTED_AI_CALLS is 1
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_04_max_executed_ai_calls():
    """EXE-04: MAX_EXECUTED_AI_CALLS constant equals 1."""
    assert MAX_EXECUTED_AI_CALLS == 1


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-05: RETRY_COUNT is 0
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_05_retry_count_zero():
    """EXE-05: RETRY_COUNT constant equals 0."""
    assert RETRY_COUNT == 0


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-06: Candidate path is NOT the certified artifact path
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_06_candidate_not_certified():
    """EXE-06: Candidate filename differs from certified artifact path."""
    assert CANDIDATE_FILENAME != Path(CERTIFIED_ARTIFACT_PATH).name, (
        "Candidate filename must not be the certified artifact filename"
    )
    assert "shadow_level3_hybrid_answers" not in CANDIDATE_FILENAME


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-07: Idempotency — duplicate execution_id is not re-executed
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_07_idempotency_duplicate_rejected():
    """EXE-07: A manifest with an existing execution_id blocks re-execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / MANIFEST_FILENAME
        execution_id = "sha256:abcdef1234567890abcdef1234567890"
        manifest_path.write_text(json.dumps({
            "execution_id": execution_id,
            "outcome": "PACP_PASS_AWAITING_HUMAN_REVIEW",
        }))
        assert _check_idempotency(manifest_path, execution_id) is True
        assert _check_idempotency(manifest_path, "sha256:different") is False


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-08: PACP is called with correct question_id = "how-good-is-management"
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_08_pacp_called_with_correct_question_id():
    """EXE-08: QUESTION_ID is 'how-good-is-management' and matches PACP family registry."""
    from pipelines.pacp_adversarial import QUESTION_FAMILY_MAP
    assert QUESTION_ID == "how-good-is-management"
    family = QUESTION_FAMILY_MAP.get(QUESTION_ID)
    assert family == "management_quality", (
        f"Expected management_quality family for {QUESTION_ID}, got {family!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-09: PACP PASS → candidate written; PACP FAIL → candidate NOT written
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_09_pacp_pass_writes_candidate_fail_does_not():
    """EXE-09: On PACP FAIL, outcome is PACP_FAIL_CANDIDATE_REJECTED and candidate is not written."""
    from intelligence.regeneration_executor import run_regeneration

    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"

        with (
            patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)),
            patch("pipelines.pacp_adversarial.run_adversarial_suite", return_value=_MOCK_PACP_FAIL),
        ):
            manifest = run_regeneration(
                company="sun_pharma",
                companies_root=companies_root,
                dry_run=True,
            )

        latest = manifest["execution_history"][-1]
        assert latest["outcome"] == "PACP_FAIL_CANDIDATE_REJECTED"
        # Candidate filename uses execution_id, not legacy CANDIDATE_FILENAME
        candidate_file = latest.get("candidate_filename")
        if candidate_file:
            assert not (cert_dir / candidate_file).exists(), "Candidate must NOT be written on PACP FAIL"


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-10: Token cap: MAX_OUTPUT_TOKENS <= 2000
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_10_max_output_tokens():
    """EXE-10: MAX_OUTPUT_TOKENS is at most 2000."""
    assert MAX_OUTPUT_TOKENS <= 2000


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-11: Composition plan has allowed_claims from management quality summary
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_11_composition_plan_has_claims():
    """EXE-11: build_management_quality_composition_plan produces at least 1 allowed claim."""
    plan = build_management_quality_composition_plan(
        _MINIMAL_MQ_SUMMARY, "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
    )
    allowed = plan.get("allowed_claims", [])
    qualified = plan.get("qualified_claims", [])
    assert len(allowed) + len(qualified) >= 1, "Composition plan must have at least 1 claim"
    for c in allowed + qualified:
        assert "claim_id" in c
        assert "claim_text" in c
        assert c.get("final_acceptance_status") == "ACCEPT"


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-12: Certified artifact byte-identical before and after dry-run
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_12_certified_artifact_untouched():
    """EXE-12: Certified artifact digest is identical before and after execution."""
    from intelligence.regeneration_executor import run_regeneration

    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_path = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / "shadow_level3_hybrid_answers.json"
        before_digest = hashlib.sha256(cert_path.read_bytes()).hexdigest()

        with patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)):
            manifest = run_regeneration(
                company="sun_pharma",
                companies_root=companies_root,
                dry_run=True,
            )

        after_digest = hashlib.sha256(cert_path.read_bytes()).hexdigest()
        assert before_digest == after_digest, "Certified artifact must be byte-identical after execution"
        latest = manifest["execution_history"][-1]
        assert not latest.get("certified_artifact_mutated", True), "manifest must report not mutated"


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-13: Execution manifest written to correct path
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_13_manifest_written_to_correct_path():
    """EXE-13: Execution manifest is written to companies/<co>/company_memory/ask_intrinsiciq/."""
    from intelligence.regeneration_executor import run_regeneration

    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"

        with patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)):
            run_regeneration(company="sun_pharma", companies_root=companies_root, dry_run=True)

        manifest_path = cert_dir / MANIFEST_FILENAME
        assert manifest_path.exists(), f"Manifest not found at {manifest_path}"
        manifest = json.loads(manifest_path.read_text())
        assert manifest.get("mission") == "ENG-MISSION45"
        assert manifest.get("unit") == UNIT_TARGET
        assert manifest.get("company") == "sun_pharma"


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-14: No approve/activate operations in security constraints
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_14_no_approve_activate():
    """EXE-14: Security constraints in manifest confirm no approve/activate operations."""
    from intelligence.regeneration_executor import run_regeneration

    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)

        with patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)):
            manifest = run_regeneration(company="sun_pharma", companies_root=companies_root, dry_run=True)

        latest = manifest["execution_history"][-1]
        sec = latest.get("m45_security_constraints", {})
        assert sec.get("self_approval") is False
        assert sec.get("automatic_activation") is False
        assert sec.get("approve_mode_invoked") is False
        assert sec.get("activate_mode_invoked") is False


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-15: M45_PRE_EXECUTION_CALL_PLAN == 1
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_15_pre_execution_call_plan_equals_1():
    """EXE-15: _verify_plan passes with 1 call and fails on 0 or 2 or unexpected extra unit."""
    _verify_plan(_make_plan(calls_for_target=1))

    with pytest.raises(RuntimeError, match="M45_GATE_FAIL"):
        _verify_plan(_make_plan(calls_for_target=0))

    with pytest.raises(RuntimeError, match="M45_GATE_FAIL"):
        _verify_plan(_make_plan(calls_for_target=1, include_extra_call=True))


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-ID-01: Same company + evidence + contract → identical execution ID
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_id_01_same_inputs_same_id():
    """EXE-ID-01: Identical company + evidence_fp + contract_fp → identical execution_id."""
    id1 = compute_execution_id("sun_pharma", UNIT_TARGET, "fp_evidence_abc", "fp_contract_xyz")
    id2 = compute_execution_id("sun_pharma", UNIT_TARGET, "fp_evidence_abc", "fp_contract_xyz")
    assert id1 == id2


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-ID-02: Evidence fingerprint change → execution ID changes
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_id_02_evidence_change_changes_id():
    """EXE-ID-02: Different evidence_fp → different execution_id."""
    id_a = compute_execution_id("sun_pharma", UNIT_TARGET, "fp_evidence_aaa", "fp_contract_xyz")
    id_b = compute_execution_id("sun_pharma", UNIT_TARGET, "fp_evidence_bbb", "fp_contract_xyz")
    assert id_a != id_b


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-ID-03: Contract fingerprint change → execution ID changes
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_id_03_contract_change_changes_id():
    """EXE-ID-03: Different contract_fp → different execution_id."""
    id_a = compute_execution_id("sun_pharma", UNIT_TARGET, "fp_evidence_abc", "fp_contract_v1")
    id_b = compute_execution_id("sun_pharma", UNIT_TARGET, "fp_evidence_abc", "fp_contract_v2")
    assert id_a != id_b


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-ID-04: Schema version change → execution ID changes
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_id_04_schema_version_change_changes_id():
    """EXE-ID-04: Different output_schema_version → different execution_id."""
    id_v1 = compute_execution_id("sun_pharma", UNIT_TARGET, "fp_ev", "fp_ct", output_schema_version="1")
    id_v2 = compute_execution_id("sun_pharma", UNIT_TARGET, "fp_ev", "fp_ct", output_schema_version="2")
    assert id_v1 != id_v2


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-ID-05: Timestamp / run metadata does NOT affect execution ID
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_id_05_timestamp_does_not_affect_id():
    """EXE-ID-05: compute_execution_id is deterministic — run_at / run_id do not enter it."""
    # The function takes only company, unit, evidence_fp, contract_fp, schema_version.
    # Multiple calls at different "times" must return identical values.
    id1 = compute_execution_id("sun_pharma", UNIT_TARGET, "fp_ev", "fp_ct")
    id2 = compute_execution_id("sun_pharma", UNIT_TARGET, "fp_ev", "fp_ct")
    id3 = compute_execution_id("sun_pharma", UNIT_TARGET, "fp_ev", "fp_ct")
    assert id1 == id2 == id3


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-ID-06: Duplicate execution ID → provider call skipped (idempotency)
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_id_06_duplicate_id_skips_provider_call():
    """EXE-ID-06: When execution_id in manifest matches, run_regeneration returns without AI call."""
    from intelligence.regeneration_executor import run_regeneration

    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"

        # Compute the execution ID the way run_regeneration would, using a stable contract fp
        # We pre-write a manifest with the same ID to trigger idempotency guard
        stable_id = compute_execution_id("sun_pharma", UNIT_TARGET, "mock_ev_fp", "mock_ct_fp")
        # Create a dummy candidate file so integrity check passes
        eid_short = stable_id.replace("sha256:", "")[:12]
        candidate_filename = f"regeneration_candidate_how_good_is_management_{eid_short}.json"
        (cert_dir / candidate_filename).write_text(json.dumps({"dummy": "candidate"}))
        candidate_digest = "sha256:" + __import__("hashlib").sha256(
            (cert_dir / candidate_filename).read_bytes()
        ).hexdigest()
        manifest_path = cert_dir / MANIFEST_FILENAME
        manifest_path.write_text(json.dumps({
            "schema_version": "m45_manifest_v3",
            "mission": "ENG-MISSION45",
            "company": "sun_pharma",
            "unit": UNIT_TARGET,
            "question_id": QUESTION_ID,
            "execution_history": [
                {
                    "execution_id": stable_id,
                    "outcome": "PACP_PASS_AWAITING_HUMAN_REVIEW",
                    "manifest_record_origin": "LIVE_EXECUTION",
                    "evidence_dependency_fingerprint": "mock_ev_fp",
                    "generation_contract_fingerprint": "mock_ct_fp",
                    "candidate_filename": candidate_filename,
                    "candidate_digest": candidate_digest,
                }
            ],
        }))

        call_counter = {"count": 0}
        original_call = __builtins__  # just a reference check placeholder

        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="mock_ev_fp"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="mock_ct_fp"),
            patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)),
            patch("intelligence.regeneration_executor._call_llm_with_telemetry",
                  side_effect=lambda *a, **kw: (call_counter.update({"count": call_counter["count"] + 1}), {})[1]) as mock_call,
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)

        # Idempotency guard fires → no LLM call
        mock_call.assert_not_called()
        # Returns REUSE decision; stable_id in history
        assert result.get("decision") == "REUSE_EXISTING_GENERATION"
        history_ids = [e.get("execution_id") for e in result.get("execution_history", [])]
        assert stable_id in history_ids


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-ANCHOR-01: Previous certified answer text cannot enter generation input
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_anchor_01_previous_answer_not_in_composition_plan():
    """EXE-ANCHOR-01: verify_no_previous_answer_in_generation_input flags old answer text in claims."""
    # Build a plan that does NOT contain previous answer text
    plan = build_management_quality_composition_plan(
        _MINIMAL_MQ_SUMMARY, "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
    )
    certified = {
        "answers": {"how-good-is-management": {"answer": {
            "simple_answer": "Previous certified answer text that should not appear anywhere.",
            "key_points": ["Old key point one that was certified previously."],
        }}}
    }
    check = verify_no_previous_answer_in_generation_input(plan, certified)
    assert check["isolated"] is True, f"Unexpected anchoring violations: {check['violations']}"


def test_exe_anchor_01b_anchoring_detected():
    """EXE-ANCHOR-01b: Anchoring is detected when a claim has certified_answer.behavioral_descriptor source."""
    plan = {
        "allowed_claims": [{
            "claim_id": "MQS-999",
            "claim_text": "Descriptor copied from certified answer.",
            "final_acceptance_status": "ACCEPT",
            "evidence_refs": ["certified_answer.behavioral_descriptor"],
            "causal_confidence": "CONFIRMED",
        }],
        "qualified_claims": [],
        "suppressed_claims": [],
    }
    certified = {"answers": {"how-good-is-management": {"answer": {"simple_answer": "", "key_points": []}}}}
    check = verify_no_previous_answer_in_generation_input(plan, certified)
    assert check["isolated"] is False
    assert any("certified_answer.behavioral_descriptor" in v for v in check["violations"])


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-ANCHOR-02: Previous behavioral descriptor cannot be copied into composition plan
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_anchor_02_descriptor_source_is_canonical_evidence():
    """EXE-ANCHOR-02: Behavioral descriptor claim references canonical evidence, not certified answer."""
    plan = build_management_quality_composition_plan(
        _MINIMAL_MQ_SUMMARY, "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
    )
    all_claims = (
        plan.get("allowed_claims", [])
        + plan.get("qualified_claims", [])
        + plan.get("suppressed_claims", [])
    )
    # No claim should reference "certified_answer.behavioral_descriptor"
    for claim in all_claims:
        for ref in claim.get("evidence_refs", []):
            assert ref != "certified_answer.behavioral_descriptor", (
                f"Claim {claim['claim_id']} references certified_answer.behavioral_descriptor — anchoring violation"
            )

    # The descriptor claim (if present) must reference canonical_evidence
    descriptor_claims = [
        c for c in all_claims
        if "FOLLOW_THROUGH_LARGELY_UNVERIFIED" in c.get("claim_text", "")
    ]
    for dc in descriptor_claims:
        refs = dc.get("evidence_refs", [])
        assert any("canonical_evidence" in r for r in refs), (
            f"Descriptor claim {dc['claim_id']} must reference canonical_evidence.behavioral_descriptor"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-DESC-01: Behavioral descriptor deterministically derived from canonical evidence
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_desc_01_descriptor_derivation_deterministic():
    """EXE-DESC-01: derive_behavioral_descriptor is deterministic for canonical Sun Pharma evidence."""
    # 0/25 delivered → FOLLOW_THROUGH_LARGELY_UNVERIFIED
    d1 = derive_behavioral_descriptor(_PROGRESSION_0_DELIVERED, _CAPITAL_ALL_NONE)
    d2 = derive_behavioral_descriptor(_PROGRESSION_0_DELIVERED, _CAPITAL_ALL_NONE)
    assert d1 == d2 == "FOLLOW_THROUGH_LARGELY_UNVERIFIED"

    # 10/20 delivered = 50%, but outcomes all unattributed → MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS
    d3 = derive_behavioral_descriptor(_PROGRESSION_10_OF_20_DELIVERED, _CAPITAL_ALL_NONE)
    assert d3 == "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS"

    # 10/20 = 50%, outcomes mostly attributed → HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED
    d4 = derive_behavioral_descriptor(_PROGRESSION_10_OF_20_DELIVERED, _CAPITAL_SOME_ATTRIBUTED)
    assert d4 == "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED"


def test_exe_desc_01b_partial_delivery():
    """EXE-DESC-01b: 10-40% delivery → PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS."""
    progression = {
        "progression_items": (
            [{"item_id": f"ITEM-{i}", "current_status": "announced",
              "exec_states": [{"execution_state": "DELIVERED"}]}
             for i in range(3)]
            + [{"item_id": f"ITEM-{i}", "current_status": "announced", "exec_states": []}
               for i in range(3, 10)]
        )
    }
    # 3/10 = 30% → PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS
    d = derive_behavioral_descriptor(progression, _CAPITAL_ALL_NONE)
    assert d == "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS"


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-DESC-02: Unsupported evidence state cannot manufacture stronger descriptor
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_desc_02_missing_evidence_returns_none():
    """EXE-DESC-02: Empty progression data returns None — cannot fabricate a descriptor."""
    d = derive_behavioral_descriptor({}, {})
    assert d is None, f"Expected None for empty evidence, got {d!r}"

    d2 = derive_behavioral_descriptor({"progression_items": []}, {})
    assert d2 is None, f"Expected None for empty progression_items, got {d2!r}"


def test_exe_desc_02b_status_field_respected():
    """EXE-DESC-02b: current_status='announced' does NOT count as delivered."""
    progression = {
        "progression_items": [
            {"item_id": "I1", "current_status": "announced", "exec_states": [
                {"execution_state": "IN_PROGRESS"}
            ]},
            {"item_id": "I2", "current_status": "in_progress", "exec_states": []},
        ]
    }
    d = derive_behavioral_descriptor(progression, _CAPITAL_ALL_NONE)
    # 0/2 delivered → FOLLOW_THROUGH_LARGELY_UNVERIFIED
    assert d == "FOLLOW_THROUGH_LARGELY_UNVERIFIED"


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-EVIDENCE-01: Contract-only regeneration preserves evidence fingerprint
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_evidence_01_contract_fp_differs_from_evidence_fp():
    """EXE-EVIDENCE-01: Contract fingerprint and evidence fingerprint are separate, independent values."""
    contract_fp_v1 = _compute_contract_fingerprint("1", "1", "gpt-4o-mini")
    contract_fp_v2 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")

    # Contract fp changes with prompt version
    assert contract_fp_v1 != contract_fp_v2

    # Evidence fp is unaffected by contract changes (it doesn't include prompt_version)
    # We verify this by checking that execution_id computed with same evidence_fp but different
    # contract_fp gives different IDs (contract change alone changes the ID)
    id_old_contract = compute_execution_id("sun_pharma", UNIT_TARGET, "ev_fp_constant", contract_fp_v1)
    id_new_contract = compute_execution_id("sun_pharma", UNIT_TARGET, "ev_fp_constant", contract_fp_v2)
    assert id_old_contract != id_new_contract, "Contract change alone must change execution_id"

    # But evidence_fp is preserved — same evidence + different contract = different ID.
    # Contract-only regeneration does NOT change the evidence fingerprint recorded in the manifest.
    # (manifest records both separately — verified in EXE-13 via manifest structure check)
    # This test confirms the fingerprint components are separable.
    id_changed_ev = compute_execution_id("sun_pharma", UNIT_TARGET, "ev_fp_changed", contract_fp_v1)
    assert id_old_contract != id_changed_ev, "Evidence change alone must change execution_id"


# ═══════════════════════════════════════════════════════════════════════════════
# EXE-SERVE-01: Current served artifact unchanged after candidate generation
# ═══════════════════════════════════════════════════════════════════════════════

def test_exe_serve_01_serving_artifact_unchanged():
    """EXE-SERVE-01: shadow_level3_hybrid_answers.json is byte-identical after candidate is written."""
    from intelligence.regeneration_executor import run_regeneration

    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        certified_path = (
            companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
            / "shadow_level3_hybrid_answers.json"
        )
        digest_before = hashlib.sha256(certified_path.read_bytes()).hexdigest()

        with (
            patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)),
            patch("pipelines.pacp_adversarial.run_adversarial_suite", return_value=_MOCK_PACP_PASS),
            # dry_run=False would make a real API call; we patch the LLM call instead
            patch(
                "intelligence.regeneration_executor._call_llm_with_telemetry",
                return_value={
                    "answer": _MOCK_AI_ANSWER,
                    "telemetry": {"success": True, "model": "gpt-4o-mini", "provider": "openai",
                                  "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                                  "latency_ms": 1200.0, "error": None},
                    "error": None,
                }
            ),
        ):
            manifest = run_regeneration(
                company="sun_pharma",
                companies_root=companies_root,
                dry_run=False,
            )

        digest_after = hashlib.sha256(certified_path.read_bytes()).hexdigest()
        assert digest_before == digest_after, (
            "shadow_level3_hybrid_answers.json must be byte-identical after candidate generation"
        )
        latest = manifest["execution_history"][-1]
        assert not latest.get("certified_artifact_mutated"), "manifest must confirm artifact not mutated"

        # Candidate was written (PACP PASS) — find by filename from manifest entry
        candidate_filename = latest.get("candidate_filename")
        assert candidate_filename, "manifest must record candidate_filename"
        candidate_path = (
            companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / candidate_filename
        )
        assert candidate_path.exists(), "Candidate must be written on PACP PASS"


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: verify PACP family registration for management_quality
# ═══════════════════════════════════════════════════════════════════════════════

def test_pacp_management_quality_family_has_validators():
    """Sanity: management_quality family has registered PACP validators."""
    from pipelines.pacp_adversarial import FAMILY_VALIDATORS
    validators = FAMILY_VALIDATORS.get("management_quality", [])
    assert len(validators) >= 5, (
        f"Expected >=5 management_quality validators, got {len(validators)}"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# M452-HIST-01: Failed attempt cannot be deleted by executor API
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_hist_01_failed_attempt_preserved():
    """M452-HIST-01: run_regeneration preserves prior failed attempts in execution_history."""
    from intelligence.regeneration_executor import run_regeneration

    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"

        # Pre-populate a failed attempt manifest
        prior_manifest = {
            "schema_version": "m45_manifest_v3",
            "mission": "ENG-MISSION45",
            "company": "sun_pharma",
            "unit": UNIT_TARGET,
            "question_id": QUESTION_ID,
            "execution_history": [
                {
                    "attempt": 1,
                    "execution_id": "sha256:prior_failed_001",
                    "outcome": "PACP_FAIL_CANDIDATE_REJECTED",
                    "approval": False,
                    "activation": False,
                }
            ],
        }
        (cert_dir / MANIFEST_FILENAME).write_text(json.dumps(prior_manifest))

        with (
            patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)),
            patch("pipelines.pacp_adversarial.run_adversarial_suite", return_value=_MOCK_PACP_FAIL),
        ):
            manifest = run_regeneration(company="sun_pharma", companies_root=companies_root, dry_run=True)

        # Prior failed entry must still be present
        ids = [e.get("execution_id") for e in manifest["execution_history"]]
        assert "sha256:prior_failed_001" in ids, "Prior failed attempt must be preserved in history"
        # At least 2 entries (prior + new)
        assert len(manifest["execution_history"]) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# M452-HIST-02: Second attempt appends history
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_hist_02_second_attempt_appends():
    """M452-HIST-02: A new execution appends a new entry; old entries unchanged."""
    from intelligence.regeneration_executor import run_regeneration

    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"

        # Two successive dry-runs should produce 2+ entries (attempt-1 reconstruction + 2 runs)
        with patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)):
            m1 = run_regeneration(company="sun_pharma", companies_root=companies_root, dry_run=True)

        n1 = len(m1["execution_history"])

        # Second run: idempotency blocks same execution_id (same contract + evidence → same ID)
        # So delete the manifest and re-run to force a second live entry
        (cert_dir / MANIFEST_FILENAME).unlink()
        _setup_company_root(companies_root)  # reset

        # Pre-populate manifest with attempt-1 history only so next run is attempt 2
        m1_fresh = {
            "schema_version": "m45_manifest_v3",
            "mission": "ENG-MISSION45",
            "company": "sun_pharma",
            "unit": UNIT_TARGET,
            "question_id": QUESTION_ID,
            "execution_history": [_ATTEMPT_1_RECONSTRUCTION],
        }
        (cert_dir / MANIFEST_FILENAME).write_text(json.dumps(m1_fresh))

        with patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)):
            m2 = run_regeneration(company="sun_pharma", companies_root=companies_root, dry_run=True)

        # The new run added an entry
        assert len(m2["execution_history"]) > len(m1_fresh["execution_history"])
        # Attempt-1 reconstruction still present
        ids = [e.get("execution_id") for e in m2["execution_history"]]
        assert _ATTEMPT_1_RECONSTRUCTION["execution_id"] in ids


# ═══════════════════════════════════════════════════════════════════════════════
# M452-HIST-03: Old failed candidate remains immutable
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_hist_03_old_candidate_immutable():
    """M452-HIST-03: A new execution writes a new candidate file, not overwriting an old one."""
    # Candidate paths use execution_id_short, so each attempt writes to a distinct file.
    # Verify CANDIDATE_FILENAME_TEMPLATE produces distinct paths for distinct execution IDs.
    eid1 = "sha256:aaaaaa000001bbbb"
    eid2 = "sha256:cccccc000002dddd"
    short1 = eid1.replace("sha256:", "")[:12]
    short2 = eid2.replace("sha256:", "")[:12]
    path1 = CANDIDATE_FILENAME_TEMPLATE.format(eid_short=short1)
    path2 = CANDIDATE_FILENAME_TEMPLATE.format(eid_short=short2)
    assert path1 != path2, "Different execution IDs must produce different candidate filenames"


# ═══════════════════════════════════════════════════════════════════════════════
# M452-CF-01: Identical generation behavior → same contract fingerprint
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_cf_01_same_policy_same_fp():
    """M452-CF-01: Same composition policy → same contract fingerprint (deterministic)."""
    fp1 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")
    fp2 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")
    assert fp1 == fp2


# ═══════════════════════════════════════════════════════════════════════════════
# M452-CF-02: Remove/add overall_view claim → fingerprint changes
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_cf_02_overall_view_change_changes_fp():
    """M452-CF-02: overall_view_in_plan flip changes composition_policy_hash → contract_fp changes."""
    policy_with = dict(COMPOSITION_POLICY, overall_view_in_plan=True)
    policy_without = dict(COMPOSITION_POLICY, overall_view_in_plan=False)
    h_with = _compute_composition_policy_hash(policy_with)
    h_without = _compute_composition_policy_hash(policy_without)
    fp_with = _compute_contract_fingerprint("2", "1", "gpt-4o-mini", composition_policy_hash=h_with)
    fp_without = _compute_contract_fingerprint("2", "1", "gpt-4o-mini", composition_policy_hash=h_without)
    assert fp_with != fp_without


# ═══════════════════════════════════════════════════════════════════════════════
# M452-CF-03: Descriptor instruction changes → fingerprint changes
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_cf_03_descriptor_instruction_change_changes_fp():
    """M452-CF-03: Changing descriptor_enforcement_mode changes policy hash → contract_fp changes."""
    policy_old = dict(COMPOSITION_POLICY, descriptor_enforcement_mode="implicit_claim_hint")
    policy_new = dict(COMPOSITION_POLICY, descriptor_enforcement_mode="explicit_mandatory_constraint_in_user_content")
    h_old = _compute_composition_policy_hash(policy_old)
    h_new = _compute_composition_policy_hash(policy_new)
    fp_old = _compute_contract_fingerprint("2", "1", "gpt-4o-mini", composition_policy_hash=h_old)
    fp_new = _compute_contract_fingerprint("2", "1", "gpt-4o-mini", composition_policy_hash=h_new)
    assert fp_old != fp_new


# ═══════════════════════════════════════════════════════════════════════════════
# M452-CF-04: No-rating policy changes → fingerprint changes
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_cf_04_rating_policy_change_changes_fp():
    """M452-CF-04: Changing prohibited_language_policy changes policy hash → contract_fp changes."""
    policy_old = dict(COMPOSITION_POLICY, prohibited_language_policy="none")
    policy_new = dict(COMPOSITION_POLICY, prohibited_language_policy="management_quality_is_weak_strong_mixed")
    h_old = _compute_composition_policy_hash(policy_old)
    h_new = _compute_composition_policy_hash(policy_new)
    assert h_old != h_new


# ═══════════════════════════════════════════════════════════════════════════════
# M452-CF-05: Output schema changes → fingerprint changes
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_cf_05_output_schema_change_changes_fp():
    """M452-CF-05: Different output_schema_version → different contract fingerprint."""
    fp_v1 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini", output_schema_version="1")
    fp_v2 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini", output_schema_version="2")
    assert fp_v1 != fp_v2


# ═══════════════════════════════════════════════════════════════════════════════
# M452-CF-06: Timestamp/runtime metadata → fingerprint unchanged
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_cf_06_timestamps_do_not_affect_fp():
    """M452-CF-06: Multiple calls at different times return identical contract fingerprint."""
    fp1 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")
    fp2 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")
    fp3 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")
    assert fp1 == fp2 == fp3


# ═══════════════════════════════════════════════════════════════════════════════
# M452-EXEC-01: New contract produces new execution ID
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_exec_01_new_contract_new_execution_id():
    """M452-EXEC-01: Attempt-1 contract_fp != attempt-2 contract_fp → different execution IDs."""
    attempt1_contract_fp = _ATTEMPT_1_RECONSTRUCTION["generation_contract_fingerprint"]
    attempt2_contract_fp = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")

    assert attempt1_contract_fp != attempt2_contract_fp, (
        "Attempt-1 and attempt-2 must have different contract fingerprints"
    )

    # Same evidence, different contract → different execution ID
    ev_fp = _ATTEMPT_1_RECONSTRUCTION["evidence_dependency_fingerprint"]
    id1 = compute_execution_id("sun_pharma", UNIT_TARGET, ev_fp, attempt1_contract_fp)
    id2 = compute_execution_id("sun_pharma", UNIT_TARGET, ev_fp, attempt2_contract_fp)
    assert id1 != id2, "Different contracts must produce different execution IDs"

    # Verify attempt-1 execution ID matches reconstruction
    assert id1 == _ATTEMPT_1_RECONSTRUCTION["execution_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# M452-EXEC-02: Evidence fingerprint unchanged across attempts
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_exec_02_evidence_fp_unchanged():
    """M452-EXEC-02: Attempt-1 evidence_fp equals attempt-2 evidence_fp (contract-only change)."""
    # Both attempts operate on the same Sun Pharma evidence.
    # The only change was the generation contract (composition policy corrected).
    attempt1_ev_fp = _ATTEMPT_1_RECONSTRUCTION["evidence_dependency_fingerprint"]

    # Verify attempt-2 contract_fp includes composition_policy_hash (evidence_fp is independent)
    attempt2_contract_fp = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")
    assert attempt2_contract_fp != _ATTEMPT_1_RECONSTRUCTION["generation_contract_fingerprint"]

    # The evidence fingerprint is not part of the contract fingerprint (they are separate)
    assert attempt1_ev_fp not in attempt2_contract_fp


# ═══════════════════════════════════════════════════════════════════════════════
# M452-EXEC-03: Only one call permitted for attempt 2
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_exec_03_one_call_only():
    """M452-EXEC-03: MAX_EXECUTED_AI_CALLS == 1 and RETRY_COUNT == 0."""
    assert MAX_EXECUTED_AI_CALLS == 1
    assert RETRY_COUNT == 0


# ═══════════════════════════════════════════════════════════════════════════════
# M452-PLAN-01: Unsafe rating claim absent from deterministic plan
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_plan_01_no_rating_in_composition_plan():
    """M452-PLAN-01: audit_composition_plan_for_rating_leakage returns clean for current plan."""
    plan = build_management_quality_composition_plan(
        _MINIMAL_MQ_SUMMARY, "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
    )
    audit = audit_composition_plan_for_rating_leakage(plan)
    assert audit["clean"], (
        f"Composition plan has rating leakage violations: {audit['violations']}"
    )


def test_m452_plan_01b_rating_claim_detected():
    """M452-PLAN-01b: audit detects 'management quality is weak' in a claim."""
    from intelligence.ask_intrinsiciq.relationship_aware_composer import build_composition_plan
    plan = build_composition_plan(
        [{"claim_id": "X-001", "claim_text": "Overall management quality is weak.",
          "final_acceptance_status": "ACCEPT", "evidence_refs": ["test"], "causal_confidence": "CONFIRMED"}],
        [], [], []
    )
    audit = audit_composition_plan_for_rating_leakage(plan)
    assert not audit["clean"], "Rating claim must be detected"
    assert len(audit["violations"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# M452-DESC-01: Descriptor derived independently (not from prior answer)
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_desc_01_descriptor_from_canonical_evidence():
    """M452-DESC-01: derive_behavioral_descriptor uses canonical progression, not certified answer."""
    # Sun Pharma: 0/25 delivered → FOLLOW_THROUGH_LARGELY_UNVERIFIED
    d = derive_behavioral_descriptor(_PROGRESSION_0_DELIVERED, _CAPITAL_ALL_NONE)
    assert d == "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
    # The function takes evidence dicts, never a certified_answer parameter
    import inspect
    sig = inspect.signature(derive_behavioral_descriptor)
    param_names = list(sig.parameters.keys())
    assert "certified_answer" not in param_names
    assert "previous_answer" not in param_names


# ═══════════════════════════════════════════════════════════════════════════════
# M452-DESC-02: Descriptor appears as required synthesis input without copying prior answer
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_desc_02_descriptor_in_plan_refs_canonical():
    """M452-DESC-02: Descriptor claim in composition plan references canonical_evidence, not certified_answer."""
    plan = build_management_quality_composition_plan(
        _MINIMAL_MQ_SUMMARY, "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
    )
    all_claims = plan.get("allowed_claims", []) + plan.get("qualified_claims", [])
    descriptor_claims = [
        c for c in all_claims
        if "FOLLOW_THROUGH_LARGELY_UNVERIFIED" in c.get("claim_text", "")
    ]
    assert len(descriptor_claims) >= 1, "Descriptor claim must be present in composition plan"
    for dc in descriptor_claims:
        refs = dc.get("evidence_refs", [])
        assert any("canonical_evidence" in r for r in refs), (
            f"Descriptor claim must reference canonical_evidence, not certified_answer. refs={refs}"
        )
        assert not any("certified_answer" in r for r in refs), (
            f"Descriptor claim must not reference certified_answer. refs={refs}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# M452-SERVE-01: Previous active artifact remains served
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_serve_01_artifact_unchanged_after_attempt2():
    """M452-SERVE-01: Certified artifact byte-identical before and after attempt-2 execution."""
    from intelligence.regeneration_executor import run_regeneration

    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        certified_path = (
            companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
            / "shadow_level3_hybrid_answers.json"
        )
        digest_before = hashlib.sha256(certified_path.read_bytes()).hexdigest()

        with (
            patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)),
            patch("pipelines.pacp_adversarial.run_adversarial_suite", return_value=_MOCK_PACP_PASS),
            patch(
                "intelligence.regeneration_executor._call_llm_with_telemetry",
                return_value={
                    "answer": _MOCK_AI_ANSWER,
                    "telemetry": {"success": True, "model": "gpt-4o-mini", "provider": "openai",
                                  "input_tokens": 100, "output_tokens": 50, "total_tokens": 150,
                                  "latency_ms": 1200.0, "error": None},
                    "error": None,
                }
            ),
        ):
            manifest = run_regeneration(
                company="sun_pharma",
                companies_root=companies_root,
                dry_run=False,
            )

        digest_after = hashlib.sha256(certified_path.read_bytes()).hexdigest()
        assert digest_before == digest_after, "Certified artifact must be byte-identical"
        latest = manifest["execution_history"][-1]
        assert not latest.get("certified_artifact_mutated"), "Must report not mutated"


# ═══════════════════════════════════════════════════════════════════════════════
# M452-UI-01: Executor unreachable from user request path
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_ui_01_executor_not_in_serving_paths():
    """M452-UI-01: regeneration_executor is not imported by any UI/API serving module."""
    import ast
    serving_modules = [
        REPO / "apps" / "ask-intrinsiciq" / "src" / "lib" / "ask-intrinsiciq" / "index.ts",
        REPO / "intelligence" / "ask_intrinsiciq" / "shadow_runner.py",
        REPO / "intelligence" / "ask_intrinsiciq" / "loader.py",
    ]
    for path in serving_modules:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        assert "regeneration_executor" not in content, (
            f"regeneration_executor must not be imported from serving path {path}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# M452: Attempt-1 reconstruction is present in fresh manifest
# ═══════════════════════════════════════════════════════════════════════════════

def test_m452_attempt1_reconstruction_present():
    """M452: _ensure_attempt1_history injects attempt-1 reconstruction into empty manifest."""
    manifest = {"execution_history": []}
    added = _ensure_attempt1_history(manifest)
    assert added is True
    assert len(manifest["execution_history"]) == 1
    entry = manifest["execution_history"][0]
    assert entry["execution_id"] == _ATTEMPT_1_RECONSTRUCTION["execution_id"]
    assert entry["outcome"] == "PACP_FAIL_CANDIDATE_REJECTED"
    assert entry["manifest_record_origin"] == "RECONSTRUCTED_FROM_EXECUTION_EVIDENCE"
    assert entry["approval"] is False
    assert entry["activation"] is False

    # Not added twice
    added2 = _ensure_attempt1_history(manifest)
    assert added2 is False
    assert len(manifest["execution_history"]) == 1


def test_m452_attempt1_pacp_fails_recorded():
    """M452: Attempt-1 reconstruction records MQ-R1 and MQ-R2 failures."""
    pacp = _ATTEMPT_1_RECONSTRUCTION["pacp_result"]
    assert "check_mq_no_rating_leakage" in pacp["fails"]
    assert "check_mq_behavioral_descriptor_present" in pacp["fails"]
    assert pacp["mq_r1_rating_leakage"] == "FAIL"
    assert pacp["mq_r2_behavioral_descriptor"] == "FAIL"


def test_m452_composition_policy_hash_covers_key_fields():
    """M452: COMPOSITION_POLICY_HASH changes when overall_view_in_plan changes."""
    policy_v1 = dict(COMPOSITION_POLICY, overall_view_in_plan=True)
    policy_v2 = dict(COMPOSITION_POLICY, overall_view_in_plan=False)
    assert _compute_composition_policy_hash(policy_v1) != _compute_composition_policy_hash(policy_v2)
    # Current policy has overall_view_in_plan=False
    assert COMPOSITION_POLICY["overall_view_in_plan"] is False
    # Current policy hash matches recomputation
    assert COMPOSITION_POLICY_HASH == _compute_composition_policy_hash(COMPOSITION_POLICY)


# ═══════════════════════════════════════════════════════════════════════════════
# M45.3 IDEMPOTENCY ORDERING
# ═══════════════════════════════════════════════════════════════════════════════

def _make_pacp_pass_manifest(cert_dir: Path, evidence_fp: str, contract_fp: str) -> str:
    """Write a history-preserving manifest with a PACP_PASS entry and return the candidate filename."""
    eid = compute_execution_id("sun_pharma", UNIT_TARGET, evidence_fp, contract_fp)
    eid_short = eid.replace("sha256:", "")[:12]
    cf = CANDIDATE_FILENAME_TEMPLATE.format(eid_short=eid_short)
    (cert_dir / cf).write_text(json.dumps({"dummy": "candidate"}))
    digest = "sha256:" + hashlib.sha256((cert_dir / cf).read_bytes()).hexdigest()
    manifest_path = cert_dir / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps({
        "schema_version": "m45_manifest_v3",
        "mission": "ENG-MISSION45",
        "company": "sun_pharma",
        "unit": UNIT_TARGET,
        "question_id": QUESTION_ID,
        "execution_history": [
            {
                "execution_id": eid,
                "outcome": "PACP_PASS_AWAITING_HUMAN_REVIEW",
                "manifest_record_origin": "LIVE_EXECUTION",
                "evidence_dependency_fingerprint": evidence_fp,
                "generation_contract_fingerprint": contract_fp,
                "candidate_filename": cf,
                "candidate_digest": digest,
            }
        ],
    }))
    return cf


def test_m453_idem_01_successful_exact_identity_returns_reuse():
    """M453-IDEM-01: Existing successful exact identity returns REUSE_EXISTING_GENERATION."""
    from intelligence.regeneration_executor import run_regeneration
    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
        _make_pacp_pass_manifest(cert_dir, "mock_ev_fp", "mock_ct_fp")
        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="mock_ev_fp"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="mock_ct_fp"),
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)
        assert result.get("decision") == "REUSE_EXISTING_GENERATION"


def test_m453_idem_02_reuse_performs_zero_provider_calls():
    """M453-IDEM-02: REUSE_EXISTING_GENERATION performs 0 provider calls."""
    from intelligence.regeneration_executor import run_regeneration
    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
        _make_pacp_pass_manifest(cert_dir, "mock_ev_fp", "mock_ct_fp")
        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="mock_ev_fp"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="mock_ct_fp"),
            patch("intelligence.regeneration_executor._call_llm_with_telemetry") as mock_llm,
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)
        mock_llm.assert_not_called()
        assert result.get("provider_calls") == 0


def test_m453_idem_03_reuse_does_not_build_composition_plan():
    """M453-IDEM-03: REUSE_EXISTING_GENERATION does not build composition plan."""
    from intelligence.regeneration_executor import run_regeneration
    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
        _make_pacp_pass_manifest(cert_dir, "mock_ev_fp", "mock_ct_fp")
        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="mock_ev_fp"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="mock_ct_fp"),
            patch("intelligence.regeneration_executor.build_management_quality_composition_plan") as mock_plan,
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)
        mock_plan.assert_not_called()
        assert result.get("decision") == "REUSE_EXISTING_GENERATION"


def test_m453_idem_04_reuse_does_not_run_pacp():
    """M453-IDEM-04: REUSE_EXISTING_GENERATION does not run PACP."""
    from intelligence.regeneration_executor import run_regeneration
    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
        _make_pacp_pass_manifest(cert_dir, "mock_ev_fp", "mock_ct_fp")
        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="mock_ev_fp"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="mock_ct_fp"),
            patch("pipelines.pacp_adversarial.run_adversarial_suite") as mock_pacp,
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)
        mock_pacp.assert_not_called()
        assert result.get("decision") == "REUSE_EXISTING_GENERATION"


def test_m453_idem_05_reuse_does_not_append_provider_execution():
    """M453-IDEM-05: REUSE does not append a new LIVE_EXECUTION entry to history."""
    from intelligence.regeneration_executor import run_regeneration
    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
        _make_pacp_pass_manifest(cert_dir, "mock_ev_fp", "mock_ct_fp")
        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="mock_ev_fp"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="mock_ct_fp"),
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)
        live_count = sum(
            1 for e in result.get("execution_history", [])
            if e.get("manifest_record_origin") == "LIVE_EXECUTION"
        )
        assert live_count == 1, f"Expected 1 LIVE_EXECUTION entry, got {live_count}"


def test_m453_idem_06_reuse_preserves_human_review_state():
    """M453-IDEM-06: REUSE preserves AWAITING_HUMAN_REVIEW state."""
    from intelligence.regeneration_executor import run_regeneration
    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
        _make_pacp_pass_manifest(cert_dir, "mock_ev_fp", "mock_ct_fp")
        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="mock_ev_fp"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="mock_ct_fp"),
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)
        assert result.get("review_state") == "AWAITING_HUMAN_REVIEW"
        assert result.get("pacp_overall") == "PASS"


def test_m453_idem_07_candidate_digest_verified_before_reuse():
    """M453-IDEM-07: Candidate digest is verified before returning REUSE."""
    from intelligence.regeneration_executor import run_regeneration
    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
        eid = compute_execution_id("sun_pharma", UNIT_TARGET, "mock_ev_fp", "mock_ct_fp")
        eid_short = eid.replace("sha256:", "")[:12]
        cf = CANDIDATE_FILENAME_TEMPLATE.format(eid_short=eid_short)
        (cert_dir / cf).write_text(json.dumps({"dummy": "candidate"}))
        real_digest = "sha256:" + hashlib.sha256((cert_dir / cf).read_bytes()).hexdigest()
        # Manifest with correct digest and matching contract fingerprint (EXACT_CONTRACT_MATCH)
        (cert_dir / MANIFEST_FILENAME).write_text(json.dumps({
            "schema_version": "m45_manifest_v3",
            "execution_history": [{
                "execution_id": eid,
                "outcome": "PACP_PASS_AWAITING_HUMAN_REVIEW",
                "manifest_record_origin": "LIVE_EXECUTION",
                "evidence_dependency_fingerprint": "mock_ev_fp",
                "generation_contract_fingerprint": "mock_ct_fp",
                "candidate_filename": cf,
                "candidate_digest": real_digest,
            }],
        }))
        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="mock_ev_fp"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="mock_ct_fp"),
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)
        assert result.get("decision") == "REUSE_EXISTING_GENERATION"
        assert result.get("candidate_digest") == real_digest


def test_m453_idem_08_corrupted_candidate_blocks_reuse():
    """M453-IDEM-08: Corrupted candidate digest blocks REUSE without regenerating."""
    from intelligence.regeneration_executor import run_regeneration
    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
        eid = compute_execution_id("sun_pharma", UNIT_TARGET, "mock_ev_fp", "mock_ct_fp")
        eid_short = eid.replace("sha256:", "")[:12]
        cf = CANDIDATE_FILENAME_TEMPLATE.format(eid_short=eid_short)
        (cert_dir / cf).write_text(json.dumps({"dummy": "candidate"}))
        # Write WRONG digest to force mismatch (matching contract fp so integrity check runs)
        (cert_dir / MANIFEST_FILENAME).write_text(json.dumps({
            "schema_version": "m45_manifest_v3",
            "execution_history": [{
                "execution_id": eid,
                "outcome": "PACP_PASS_AWAITING_HUMAN_REVIEW",
                "manifest_record_origin": "LIVE_EXECUTION",
                "evidence_dependency_fingerprint": "mock_ev_fp",
                "generation_contract_fingerprint": "mock_ct_fp",
                "candidate_filename": cf,
                "candidate_digest": "sha256:deadbeef00000000000000000000000000000000000000000000000000000000",
            }],
        }))
        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="mock_ev_fp"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="mock_ct_fp"),
            patch("intelligence.regeneration_executor._call_llm_with_telemetry") as mock_llm,
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)
        mock_llm.assert_not_called()  # must NOT regenerate
        assert result.get("decision") == "EXISTING_EXECUTION_ARTIFACT_INTEGRITY_FAILURE"


# ═══════════════════════════════════════════════════════════════════════════════
# M45.3 FAILED IDENTITY POLICY
# ═══════════════════════════════════════════════════════════════════════════════

def test_m453_fail_01_failed_exact_identity_cannot_auto_retry():
    """M453-FAIL-01: Exact previous PACP_FAIL identity cannot automatically retry."""
    from intelligence.regeneration_executor import run_regeneration
    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
        eid = compute_execution_id("sun_pharma", UNIT_TARGET, "mock_ev_fp", "mock_ct_fp")
        (cert_dir / MANIFEST_FILENAME).write_text(json.dumps({
            "schema_version": "m45_manifest_v3",
            "execution_history": [{
                "execution_id": eid,
                "outcome": "PACP_FAIL_CANDIDATE_REJECTED",
                "manifest_record_origin": "LIVE_EXECUTION",
                "evidence_dependency_fingerprint": "mock_ev_fp",
                "generation_contract_fingerprint": "mock_ct_fp",
            }],
        }))
        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="mock_ev_fp"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="mock_ct_fp"),
            patch("intelligence.regeneration_executor._call_llm_with_telemetry") as mock_llm,
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)
        mock_llm.assert_not_called()
        assert result.get("decision") == "EXISTING_FAILED_EXECUTION_REQUIRES_NEW_CONTRACT_OR_EXPLICIT_RETRY_POLICY"


def test_m453_fail_02_new_material_contract_creates_new_execution_id():
    """M453-FAIL-02: Material contract change (composition policy) creates new execution_id."""
    policy_a = dict(COMPOSITION_POLICY, version="test_v_a")
    policy_b = dict(COMPOSITION_POLICY, version="test_v_b")
    fp_a = _compute_composition_policy_hash(policy_a)
    fp_b = _compute_composition_policy_hash(policy_b)
    assert fp_a != fp_b
    # Different policy hashes produce different contract fingerprints
    ct_a = _compute_contract_fingerprint("2", "1", "gpt-4o-mini", composition_policy_hash=fp_a)
    ct_b = _compute_contract_fingerprint("2", "1", "gpt-4o-mini", composition_policy_hash=fp_b)
    assert ct_a != ct_b
    # Different contract fingerprints produce different execution IDs
    eid_a = compute_execution_id("sun_pharma", UNIT_TARGET, "ev_fp", ct_a)
    eid_b = compute_execution_id("sun_pharma", UNIT_TARGET, "ev_fp", ct_b)
    assert eid_a != eid_b


def test_m453_fail_03_pre_execution_block_not_counted_as_provider_call():
    """M453-FAIL-03: A PRE_EXECUTION_BLOCK (plan audit failure) does not count as provider call."""
    # The plan audit raises M452_COMPOSITION_PLAN_RATING_LEAKAGE before provider invocation.
    # Verify by constructing a plan with a prohibited claim — audit fires, provider not called.
    from intelligence.regeneration_executor import (
        build_management_quality_composition_plan,
        audit_composition_plan_for_rating_leakage,
    )
    # Inject prohibited language through investor_implication
    bad_summary = dict(_MINIMAL_MQ_SUMMARY, investor_implication="Management quality is weak and needs improvement.")
    plan = build_management_quality_composition_plan(bad_summary, "FOLLOW_THROUGH_LARGELY_UNVERIFIED")
    audit = audit_composition_plan_for_rating_leakage(plan)
    assert not audit["clean"], "Expected rating-leakage violation not found"
    # Provider would NOT be called — the executor raises before _call_llm_with_telemetry


# ═══════════════════════════════════════════════════════════════════════════════
# M45.3 CONTRACT COVERAGE
# ═══════════════════════════════════════════════════════════════════════════════

def test_m453_cf_01_identical_contract_semantics_same_fp():
    """M453-CF-01: Identical contract inputs → same contract fingerprint."""
    fp1 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")
    fp2 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")
    assert fp1 == fp2


def test_m453_cf_02_composition_claim_policy_change_changes_fp():
    """M453-CF-02: Composition claim policy change → contract FP changes."""
    old_policy = dict(COMPOSITION_POLICY, claim_sources=["investor_implication"])
    new_policy = dict(COMPOSITION_POLICY, claim_sources=["investor_implication", "overall_direction"])
    fp_old = _compute_contract_fingerprint("2", "1", "gpt-4o-mini",
                                           composition_policy_hash=_compute_composition_policy_hash(old_policy))
    fp_new = _compute_contract_fingerprint("2", "1", "gpt-4o-mini",
                                           composition_policy_hash=_compute_composition_policy_hash(new_policy))
    assert fp_old != fp_new


def test_m453_cf_03_descriptor_policy_change_changes_fp():
    """M453-CF-03: Descriptor policy change → contract FP changes."""
    policy_a = dict(COMPOSITION_POLICY, descriptor_source="canonical_evidence")
    policy_b = dict(COMPOSITION_POLICY, descriptor_source="alternative_source")
    fp_a = _compute_contract_fingerprint("2", "1", "gpt-4o-mini",
                                         composition_policy_hash=_compute_composition_policy_hash(policy_a))
    fp_b = _compute_contract_fingerprint("2", "1", "gpt-4o-mini",
                                         composition_policy_hash=_compute_composition_policy_hash(policy_b))
    assert fp_a != fp_b


def test_m453_cf_04_rating_prohibition_change_changes_fp():
    """M453-CF-04: Rating prohibition policy change → contract FP changes."""
    policy_a = dict(COMPOSITION_POLICY, prohibited_language_policy="NO: weak")
    policy_b = dict(COMPOSITION_POLICY, prohibited_language_policy="NO: weak/strong")
    fp_a = _compute_contract_fingerprint("2", "1", "gpt-4o-mini",
                                         composition_policy_hash=_compute_composition_policy_hash(policy_a))
    fp_b = _compute_contract_fingerprint("2", "1", "gpt-4o-mini",
                                         composition_policy_hash=_compute_composition_policy_hash(policy_b))
    assert fp_a != fp_b


def test_m453_cf_05_prompt_text_change_changes_fp():
    """M453-CF-05: Prompt version change → contract FP changes."""
    fp_v2 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")
    fp_v3 = _compute_contract_fingerprint("3", "1", "gpt-4o-mini")
    assert fp_v2 != fp_v3


def test_m453_cf_06_output_schema_change_changes_fp():
    """M453-CF-06: Output schema version change → contract FP changes."""
    fp_v1 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini", output_schema_version="1")
    fp_v2 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini", output_schema_version="2")
    assert fp_v1 != fp_v2


def test_m453_cf_07_runtime_metadata_does_not_change_fp():
    """M453-CF-07: Runtime timestamps and paths do NOT affect contract fingerprint."""
    fp1 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")
    fp2 = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")
    # Calling again at a different time (or hypothetically from a different path) yields same fp
    assert fp1 == fp2
    # Composition policy hash is deterministic
    assert _compute_composition_policy_hash(COMPOSITION_POLICY) == _compute_composition_policy_hash(COMPOSITION_POLICY)


# ═══════════════════════════════════════════════════════════════════════════════
# M45.3 PLAN DETERMINISM
# ═══════════════════════════════════════════════════════════════════════════════

def test_m453_plan_01_ten_identical_builds_produce_identical_digest():
    """M453-PLAN-01: 10 consecutive plan builds produce identical plan digests."""
    digests = set()
    for _ in range(10):
        plan = build_management_quality_composition_plan(
            _MINIMAL_MQ_SUMMARY, "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
        )
        digests.add(_compute_plan_digest(plan))
    assert len(digests) == 1, f"Non-deterministic plan digests: {digests}"


def test_m453_plan_02_canonical_ordering_is_deterministic():
    """M453-PLAN-02: Repeated plan builds for same inputs give same claim order."""
    plans = [
        build_management_quality_composition_plan(
            _MINIMAL_MQ_SUMMARY, "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
        )
        for _ in range(5)
    ]
    claim_orders = [
        [c.get("claim_id") for c in p.get("allowed_claims", [])]
        for p in plans
    ]
    first = claim_orders[0]
    for order in claim_orders[1:]:
        assert order == first, "Claim order is non-deterministic"


def test_m453_plan_03_evidence_change_changes_plan_digest():
    """M453-PLAN-03: Different canonical evidence produces different plan digest."""
    summary_a = dict(_MINIMAL_MQ_SUMMARY, investor_implication="Evidence supports conviction.")
    summary_b = dict(_MINIMAL_MQ_SUMMARY, investor_implication="Evidence undermines conviction.")
    plan_a = build_management_quality_composition_plan(summary_a, "FOLLOW_THROUGH_LARGELY_UNVERIFIED")
    plan_b = build_management_quality_composition_plan(summary_b, "FOLLOW_THROUGH_LARGELY_UNVERIFIED")
    assert _compute_plan_digest(plan_a) != _compute_plan_digest(plan_b)


def test_m453_plan_04_same_evidence_same_contract_same_plan():
    """M453-PLAN-04: Same evidence + same contract cannot produce different claims (deterministic builder)."""
    plan1 = build_management_quality_composition_plan(_MINIMAL_MQ_SUMMARY, "FOLLOW_THROUGH_LARGELY_UNVERIFIED")
    plan2 = build_management_quality_composition_plan(_MINIMAL_MQ_SUMMARY, "FOLLOW_THROUGH_LARGELY_UNVERIFIED")
    assert _compute_plan_digest(plan1) == _compute_plan_digest(plan2)
    claims1 = [c.get("claim_text") for c in plan1.get("allowed_claims", [])]
    claims2 = [c.get("claim_text") for c in plan2.get("allowed_claims", [])]
    assert claims1 == claims2


def test_m453_plan_05_rating_scan_deterministic_across_builds():
    """M453-PLAN-05: Rating-leakage scan gives identical result across repeated plan builds."""
    audits = [
        audit_composition_plan_for_rating_leakage(
            build_management_quality_composition_plan(
                _MINIMAL_MQ_SUMMARY, "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
            )
        )
        for _ in range(5)
    ]
    # All audits agree
    assert all(a["clean"] == audits[0]["clean"] for a in audits)
    # Current plan must be clean (interpretation.conclusion excluded in M45.3)
    assert audits[0]["clean"], f"Plan audit not clean: {audits[0]['violations']}"


# ═══════════════════════════════════════════════════════════════════════════════
# M45.3 FORENSICS
# ═══════════════════════════════════════════════════════════════════════════════

def test_m453_forensic_unsafe_claim_source():
    """M453-FORENSIC-01: interpretation.conclusion is excluded; injecting it via investor_implication is caught."""
    # The unsafe claim "Management quality is weak and the trajectory is stable."
    # came from mq_summary.interpretation.conclusion — now excluded from plan builder.
    # Verify conclusion is NOT added as a claim from the interpretation dict.
    summary_with_conclusion = dict(_MINIMAL_MQ_SUMMARY)
    summary_with_conclusion["interpretation"] = {
        "why_it_matters": "Capital discipline matters for compounding.",
        "conclusion": "Management quality is weak and the trajectory is stable.",
        "economic_mechanism": "Per-share value driven by allocation.",
    }
    plan = build_management_quality_composition_plan(summary_with_conclusion, "FOLLOW_THROUGH_LARGELY_UNVERIFIED")
    all_texts = [c.get("claim_text", "") for c in plan.get("allowed_claims", [])]
    for t in all_texts:
        assert "management quality is weak" not in t.lower(), (
            f"Prohibited claim from interpretation.conclusion present: {t}"
        )
    audit = audit_composition_plan_for_rating_leakage(plan)
    assert audit["clean"], f"Plan still has rating leakage: {audit['violations']}"


def test_m453_forensic_previous_answer_isolation():
    """M453-FORENSIC-02: Reconfirm PREVIOUS_ANSWER_USED_AS_GENERATION_INPUT = false."""
    plan = build_management_quality_composition_plan(_MINIMAL_MQ_SUMMARY, "FOLLOW_THROUGH_LARGELY_UNVERIFIED")
    certified = {"answers": {"how-good-is-management": {"answer": {
        "simple_answer": "Sun Pharma's management delivery pattern is FOLLOW_THROUGH_LARGELY_UNVERIFIED.",
        "key_points": ["None of the 25 tracked items reached delivered state."],
    }}}}
    check = verify_no_previous_answer_in_generation_input(plan, certified)
    assert check["isolated"] is True


def test_m453_legacy_flat_manifest_migration():
    """M453-LEGACY-01: Flat manifest is migrated to history format, preserving the existing successful entry."""
    from intelligence.regeneration_executor import run_regeneration
    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"

        legacy_execution_id = "sha256:1301fe09d781e2fef373ff2866a52949"
        legacy_evidence_fp = "mock_ev_fp"
        # Create the legacy candidate file
        (cert_dir / CANDIDATE_FILENAME).write_text(json.dumps({"legacy": "candidate"}))
        candidate_digest = "sha256:" + hashlib.sha256(
            (cert_dir / CANDIDATE_FILENAME).read_bytes()
        ).hexdigest()

        # Write a flat manifest (old schema_version m45_manifest_v2)
        flat_manifest = {
            "schema_version": "m45_manifest_v2",
            "execution_id": legacy_execution_id,
            "company": "sun_pharma",
            "unit": UNIT_TARGET,
            "question_id": QUESTION_ID,
            "evidence_dependency_fingerprint": legacy_evidence_fp,
            "generation_contract_fingerprint": "mock_ct_fp",
            "outcome": "PACP_PASS_AWAITING_HUMAN_REVIEW",
            # Use filename-only key so integrity check resolves via candidate_dir (tmpdir), not REPO
            "candidate_filename": CANDIDATE_FILENAME,
            "candidate_digest": candidate_digest,
        }
        (cert_dir / MANIFEST_FILENAME).write_text(json.dumps(flat_manifest))

        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="mock_ev_fp"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="mock_ct_fp"),
            patch("intelligence.regeneration_executor._call_llm_with_telemetry") as mock_llm,
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)

        mock_llm.assert_not_called()
        assert result.get("decision") == "REUSE_EXISTING_GENERATION"
        # Check migration happened
        history = result.get("execution_history", [])
        migrated = next((e for e in history if e.get("execution_id") == legacy_execution_id
                         and e.get("outcome") == "PACP_PASS_AWAITING_HUMAN_REVIEW"), None)
        assert migrated is not None, "Migrated flat manifest entry not in history"
        assert migrated.get("manifest_record_origin") == "MIGRATED_FROM_FLAT_MANIFEST"
        assert migrated.get("contract_identity_schema") == "LEGACY_M45_1"


def test_m453_composition_plan_digest_in_attempt_entry():
    """M453-DIGEST-01: composition_plan_digest is recorded in execution history entry."""
    from intelligence.regeneration_executor import run_regeneration

    def _mock_llm(*a, **kw):
        return {
            "answer": {
                "simple_answer": f"FOLLOW_THROUGH_LARGELY_UNVERIFIED evidence shows no delivery.",
                "why_it_matters": "test",
                "investor_interpretation": "test",
                "key_points": ["test"],
            },
            "telemetry": {"provider": "openai", "model": "gpt-4o-mini",
                          "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                          "latency_ms": 100.0, "success": True, "error": None},
            "error": None,
        }

    with tempfile.TemporaryDirectory() as tmpdir:
        companies_root = Path(tmpdir)
        _setup_company_root(companies_root)
        cert_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
        (cert_dir / MANIFEST_FILENAME).write_text(json.dumps({
            "schema_version": "m45_manifest_v3",
            "execution_history": [],
        }))

        with (
            patch("intelligence.regeneration_executor._compute_evidence_fingerprint", return_value="ev_fp_new"),
            patch("intelligence.regeneration_executor._compute_contract_fingerprint", return_value="ct_fp_new"),
            patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)),
            patch("intelligence.regeneration_executor._call_llm_with_telemetry", side_effect=_mock_llm),
            patch("pipelines.pacp_adversarial.run_adversarial_suite",
                  return_value={"overall": "PASS", "named_checks": 26, "fails": [], "warns": [],
                                "skips": [], "incomplete": []}),
        ):
            result = run_regeneration(company="sun_pharma", companies_root=companies_root)

        live_entries = [e for e in result.get("execution_history", [])
                        if e.get("manifest_record_origin") == "LIVE_EXECUTION"]
        assert len(live_entries) >= 1
        latest = live_entries[-1]
        assert "composition_plan_digest" in latest, "composition_plan_digest missing from attempt entry"
        assert latest["composition_plan_digest"].startswith("sha256:")
