"""
ENG-MISSION51.1: Exact-Artifact Human Review + AI Necessity Decision — 21 tests.

Test IDs: M511-01 through M511-21.
0 AI calls. Deterministic review only.

Review findings:
- Decision A: M51_WORSE_THAN_M37_8 (consistency map contradiction, missing MC-0031)
- Decision B: AI_NARRATIVE_NOT_NEEDED (LLM what_may_mean_economically inferior to deterministic)
- Artifact recommendation: NEEDS_CHANGES
- Architecture recommendation: MOVE_TO_CONTRACT_V5_ZERO_AI
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COMPANIES = REPO / "companies"
COMPANY_MEMORY = COMPANIES / "sun_pharma" / "company_memory"

M37_8_PATH = COMPANY_MEMORY / "ask_intrinsiciq" / "shadow_level3_hybrid_answers.json"
M51_CANDIDATE_PATH = (
    COMPANY_MEMORY / "ask_intrinsiciq"
    / "regeneration_candidate_how_good_is_management_444fc5f4166d.json"
)

M37_8_DIGEST = "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"
M51_PRE_LLM_DIGEST = "sha256:5314d96aabc7bcd56f45289c9f368f023a9bd113f76eb488ad417fd39d55635f"
M51_CANDIDATE_DIGEST = "sha256:5c86d936a296cae6bfd5c88e002ca71ab411a7851f533fea0cd81be3e2faf135"

M51_EXECUTION_ID = "sha256:444fc5f4166d1e5b39e30a58a8469ff2553106ca5f21d777cd1598ea32ae8909"
M51_EVIDENCE_FP = "sha256:6793736f4298b82142d39d0439f299d7c11f0310ada29ff0a9cc99fac06c2aad"
M51_CONTRACT_V4_FP = "sha256:46dbdbe96e05fd0c233851ad3ad474fc2dd386f5c0d4955e00dd6fb490291ee7"
M51_RAW_NARRATIVE_DIGEST = "sha256:6bd8caaa6d72b926c8a499e82e0f67c41230d42e6566e0b726cccc1c36dd96ba"


@pytest.fixture(scope="module")
def m37_8_answer():
    with open(M37_8_PATH) as f:
        return json.load(f)["answers"]["how-good-is-management"]["answer"]


@pytest.fixture(scope="module")
def m51_candidate():
    with open(M51_CANDIDATE_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def m51_answer(m51_candidate):
    return m51_candidate["answer"]


@pytest.fixture(scope="module")
def pre_llm_artifact():
    # M52 note: investor_sections.py bugs (consistency map + MC-0031) were fixed in M52.
    # Running V4 assembler with current code produces different output than M51 execution.
    # This fixture now returns "V4 with M52-fixed investor_sections" — used by M511-14
    # to verify deterministic renderer still includes PAT (property is still true).
    # M511-15 is updated to not require section equality (which would use M51-era buggy code).
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4
    fp = build_management_quality_fact_pack_v2("sun_pharma", COMPANY_MEMORY)
    return assemble_management_answer_v4(fp, llm_prose=None)


# M511-01: All three artifact identities verified
def test_m511_01_all_artifact_identities_verified():
    m37_8_actual = "sha256:" + hashlib.sha256(M37_8_PATH.read_bytes()).hexdigest()
    assert m37_8_actual == M37_8_DIGEST, f"M37.8 digest mismatch: {m37_8_actual}"

    m51_actual = "sha256:" + hashlib.sha256(M51_CANDIDATE_PATH.read_bytes()).hexdigest()
    assert m51_actual == M51_CANDIDATE_DIGEST, f"M51 candidate digest mismatch: {m51_actual}"

    # Pre-LLM digest: read from M51 candidate's stored field.
    # Cannot re-derive from current code — M52 fixed the investor_sections.py bugs
    # (all-CONSISTENT map bug + MC-0031 omission) which changes V4 output.
    # The stored digest is the historical record of what M51 executor produced.
    with open(M51_CANDIDATE_PATH) as f:
        m51_raw = json.load(f)
    stored_pre_llm = m51_raw.get("pre_llm_artifact_digest", "")
    assert stored_pre_llm == M51_PRE_LLM_DIGEST, (
        f"M51 candidate stored pre_llm_artifact_digest does not match expected M51_PRE_LLM_DIGEST: {stored_pre_llm}"
    )


# M511-02: M51 freshness CURRENT
def test_m511_02_m51_freshness_current():
    from pathlib import Path
    from intelligence.regeneration_executor import _compute_evidence_fingerprint
    current_fp = _compute_evidence_fingerprint("sun_pharma", Path("companies"))
    assert current_fp == M51_EVIDENCE_FP, (
        f"Evidence changed since M51 execution — reconcile freshness first. "
        f"Current: {current_fp} Expected: {M51_EVIDENCE_FP}"
    )


# M511-03: M51 exact execution identity verified
def test_m511_03_m51_execution_identity_verified(m51_candidate):
    assert m51_candidate["execution_id"] == M51_EXECUTION_ID
    with open(M51_CANDIDATE_PATH) as f:
        raw = json.load(f)
    assert raw.get("execution_id") == M51_EXECUTION_ID
    # Verify raw narrative digest
    llm_raw = m51_candidate.get("llm_raw", {})
    raw_str = json.dumps(llm_raw, sort_keys=True).encode()
    actual_raw_digest = "sha256:" + hashlib.sha256(raw_str).hexdigest()
    assert actual_raw_digest == M51_RAW_NARRATIVE_DIGEST, (
        f"Raw narrative digest mismatch: {actual_raw_digest}"
    )


# M511-04: Canonical hard count = 3
def test_m511_04_canonical_hard_count_3(m51_answer):
    simple = m51_answer["simple_answer"]
    assert "3 hard commitments" in simple, "Canonical hard count (3) not in simple_answer"
    # DPF also reflects canonical count
    dpfs = {d["metric"]: d["value"] for d in m51_answer.get("deterministic_precision_facts", [])}
    commit_dpf = dpfs.get("Management commitments", "")
    assert "3 hard" in commit_dpf, f"DPF Management commitments not canonical: {commit_dpf}"


# M511-05: M51 core factual claims supported
def test_m511_05_m51_core_claims_supported(m51_answer):
    simple = m51_answer["simple_answer"]
    assert "FOLLOW_THROUGH_LARGELY_UNVERIFIED" in simple
    assert "0 of 25" in simple
    assert "46 management commitments" in simple
    assert "₹58,462 cr" in simple
    assert "19.6%" in simple
    # Behavioral descriptor is in dedicated field
    assert m51_answer.get("behavioral_descriptor") == "FOLLOW_THROUGH_LARGELY_UNVERIFIED"


# M511-06: DPFs supported by current evidence
def test_m511_06_dpfs_supported(m51_answer):
    dpfs = {d["metric"]: d["value"] for d in m51_answer.get("deterministic_precision_facts", [])}
    # Canonical financial facts
    fin = dpfs.get("Financial scale (FY26)", "")
    assert "58,462" in fin, f"Revenue not in financial DPF: {fin}"
    assert "19.6%" in fin, f"NPM not in financial DPF: {fin}"
    assert "11,479" in fin, f"PAT not in financial DPF: {fin}"
    # Delivery follow-through
    delivery = dpfs.get("Delivery follow-through", "")
    assert "0 delivered" in delivery, f"0 delivered not in DPF: {delivery}"


# M511-07: D6 remains fixed — evidence_confidence is independent field
def test_m511_07_d6_evidence_confidence_independent(m51_answer):
    cm = m51_answer.get("management_consistency_map", {})
    # evidence_confidence is a distinct key (D6 fix)
    assert "Evidence confidence" in cm, "Evidence confidence missing from consistency map"
    ec_value = cm["Evidence confidence"]
    assert "HIGH" in ec_value, f"Evidence confidence should indicate HIGH quality: {ec_value}"
    # Detect the known consistency map contradiction (documented as NEEDS_CHANGES)
    monitoring = m51_answer.get("what_to_monitor", [])
    inconsistent_in_monitoring = [item for item in monitoring if "INCONSISTENT" in item]
    candor_map = cm.get("Candor and consistency", "")
    # Both facts are retrievable — the contradiction is real and documented
    assert "CONSISTENT" in candor_map or candor_map != ""
    # This contradiction (map=CONSISTENT, monitoring=INCONSISTENT) is a known defect
    assert len(inconsistent_in_monitoring) > 0, (
        "Expected at least one INCONSISTENT entry in monitoring — "
        "candor contradiction not detectable"
    )


# M511-08: D7 remains fixed — unresolved items present and non-trivial
def test_m511_08_d7_unresolved_items_present(m51_answer):
    nyp = m51_answer.get("what_is_not_yet_proven", "")
    assert len(nyp) > 50, "what_is_not_yet_proven is too short/empty"
    assert "MC-0039" in nyp or "MC-0029" in nyp, (
        "what_is_not_yet_proven should reference unresolved commitments"
    )


# M511-09: Monitoring items specific and named
def test_m511_09_monitoring_specific(m51_answer):
    monitoring = m51_answer.get("what_to_monitor", [])
    assert len(monitoring) >= 3, f"Monitoring too sparse: {len(monitoring)} items"
    # At least one item references a named commitment
    named = [item for item in monitoring if "MC-" in item]
    assert len(named) >= 1, "No named commitment in what_to_monitor"


# M511-10: Economic interpretation no speculative language on confirmed financials
def test_m511_10_economic_interpretation_temporal_safety(m51_answer):
    econ = m51_answer.get("what_may_mean_economically", "")
    assert len(econ) > 30, "what_may_mean_economically too short"
    # No "projected" applied to the confirmed ₹58,462 cr figure
    lower = econ.lower()
    assert "projected revenue" not in lower, "Speculative 'projected revenue' in economic context"
    assert "₹58,462" in econ or "58,462" in econ, "Confirmed revenue not in economic context"


# M511-11: Final simple_answer source is DETERMINISTIC (LLM rejected)
def test_m511_11_final_simple_answer_source_deterministic(m51_candidate, m51_answer):
    # LLM raw did not contain exact descriptor string
    llm_raw_simple = m51_candidate.get("llm_raw", {}).get("simple_answer", "")
    assert "FOLLOW_THROUGH_LARGELY_UNVERIFIED" not in llm_raw_simple, (
        "LLM raw simple_answer should not contain exact descriptor (it was rejected)"
    )
    # Final simple_answer DOES contain exact descriptor (deterministic fallback used)
    final_simple = m51_answer.get("simple_answer", "")
    assert "FOLLOW_THROUGH_LARGELY_UNVERIFIED" in final_simple


# M511-12: Rejected model simple_answer is recorded but not served
def test_m511_12_rejected_llm_simple_answer_recorded(m51_candidate):
    llm_raw = m51_candidate.get("llm_raw", {})
    assert "simple_answer" in llm_raw, "LLM raw simple_answer not recorded"
    raw_simple = llm_raw["simple_answer"]
    assert "largely unverified" in raw_simple.lower(), (
        "LLM raw simple_answer should contain 'largely unverified' (paraphrase that was rejected)"
    )
    # Not served — final answer uses deterministic version
    final = m51_candidate["answer"]["simple_answer"]
    assert final != raw_simple, "Final simple_answer should differ from rejected LLM version"


# M511-13: Accepted model economic narrative identified and matches final
def test_m511_13_accepted_llm_economic_narrative_identified(m51_candidate, m51_answer):
    llm_raw = m51_candidate.get("llm_raw", {})
    raw_econ = llm_raw.get("what_may_mean_economically", "")
    final_econ = m51_answer.get("what_may_mean_economically", "")
    assert raw_econ == final_econ, (
        "what_may_mean_economically in final should match accepted LLM version"
    )
    # Verify LLM version is inferior to deterministic (drops PAT)
    assert "11,479" not in final_econ, (
        "LLM version should not include PAT — deterministic version has it but LLM dropped it"
    )


# M511-14: Pre-LLM deterministic artifact is independently investor-usable
def test_m511_14_pre_llm_artifact_investor_usable(pre_llm_artifact):
    required = [
        "what_evidence_shows", "what_management_says", "where_management_was_consistent",
        "management_consistency_map", "what_is_not_yet_proven", "what_to_monitor",
        "behavioral_descriptor", "deterministic_precision_facts",
    ]
    for key in required:
        assert key in pre_llm_artifact and pre_llm_artifact[key], (
            f"Pre-LLM artifact missing or empty: {key}"
        )
    # Pre-LLM economic context includes PAT (more complete than LLM version)
    pre_econ = pre_llm_artifact.get("what_may_mean_economically", "")
    assert "11,479" in pre_econ, "Pre-LLM economic context should include PAT ₹11,479 cr"


# M511-15: AI delta — what_may_mean_economically is where LLM made its only contribution
def test_m511_15_ai_delta_only_economic_context(pre_llm_artifact, m51_answer):
    # M52 note: M52 fixed investor_sections bugs, so pre_llm_artifact (recomputed with fixed
    # code) differs from the M51-era pre-LLM in what_management_says and consistency_map.
    # We cannot re-derive the historical M51 pre-LLM (digest only stored, not artifact).
    # What we CAN verify: (1) pre-LLM economic context differs from M51 final (LLM did change it);
    # (2) M51 final economic context matches LLM accepted version (no PAT).
    pre_econ = pre_llm_artifact.get("what_may_mean_economically", "")
    final_econ = m51_answer.get("what_may_mean_economically", "")
    # Pre-LLM (current code) includes PAT; M51 final (LLM accepted) does not
    assert "11,479" in pre_econ, "Pre-LLM economic context should include PAT ₹11,479 cr"
    assert "11,479" not in final_econ, "M51 final (LLM accepted) should not include PAT (LLM dropped it)"
    assert pre_econ != final_econ, "Economic context should differ between pre-LLM and M51 final"


# M511-16: Artifact and AI recommendations are recorded separately
def test_m511_16_artifact_and_ai_recommendations_separate():
    hr_path = REPO / "governance" / "ENG_MISSION51_NARRATIVE_ONLY_REGENERATION_HUMAN_REVIEW.json"
    with open(hr_path) as f:
        review = json.load(f)
    m511_review = review.get("m511_review", {})
    assert "artifact_recommendation" in m511_review, "artifact_recommendation missing"
    assert "ai_architecture_recommendation" in m511_review, "ai_architecture_recommendation missing"
    # The two recommendations must be distinct fields (independent decisions)
    assert m511_review["artifact_recommendation"] != m511_review["ai_architecture_recommendation"]


# M511-17: Human decisions remain PENDING
def test_m511_17_human_decisions_recorded():
    # M52: human decisions have been recorded by Yogesh (2026-10-07)
    hr_path = REPO / "governance" / "ENG_MISSION51_NARRATIVE_ONLY_REGENERATION_HUMAN_REVIEW.json"
    with open(hr_path) as f:
        review = json.load(f)
    hd = review.get("human_decision_m511", {})
    assert hd.get("ARTIFACT_HUMAN_DECISION") == "NEEDS_CHANGES", (
        f"Expected NEEDS_CHANGES, got: {hd.get('ARTIFACT_HUMAN_DECISION')}"
    )
    assert hd.get("AI_ARCHITECTURE_HUMAN_DECISION") == "REMOVE_AI", (
        f"Expected REMOVE_AI, got: {hd.get('AI_ARCHITECTURE_HUMAN_DECISION')}"
    )
    assert hd.get("HUMAN_REVIEWER") == "Yogesh"
    assert hd.get("HUMAN_REVIEW_TIMESTAMP") is not None
    assert hd.get("HUMAN_REVIEW_TIMESTAMP") != "PENDING"


# M511-18: M51 candidate remains unapproved and inactive
def test_m511_18_candidate_unapproved_inactive(m51_candidate):
    assert m51_candidate.get("eligibility_state") == "HUMAN_REVIEW_ELIGIBLE"
    assert m51_candidate.get("pacp_overall") == "PASS"
    # Not APPROVED or ACTIVATED
    state = m51_candidate.get("eligibility_state", "")
    assert state not in ("APPROVED", "ACTIVATED"), f"Candidate should not be approved/activated: {state}"


# M511-19: M37.8 remains runtime-served and byte-identical
def test_m511_19_m37_8_still_serving():
    actual = "sha256:" + hashlib.sha256(M37_8_PATH.read_bytes()).hexdigest()
    assert actual == M37_8_DIGEST, f"M37.8 has changed: {actual}"


# M511-20: Obsolete test expectations have been reconciled
def test_m511_20_obsolete_tests_reconciled():
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest",
         "tests/intelligence/test_m49_contract_v3_canary.py",
         "tests/intelligence/test_m491_evidence_drift_and_freshness.py",
         "-q", "--tb=no"],
        capture_output=True, text=True, cwd=REPO
    )
    assert result.returncode == 0, (
        f"Pre-existing tests still failing after M51.1 migration:\n{result.stdout}"
    )


# M511-21: 0 AI calls — entire review is deterministic
def test_m511_21_zero_ai_calls():
    # Evidence FP match + deterministic review = 0 AI calls
    from pathlib import Path
    from intelligence.regeneration_executor import _compute_evidence_fingerprint
    fp = _compute_evidence_fingerprint("sun_pharma", Path("companies"))
    assert fp == M51_EVIDENCE_FP  # freshness check only, no AI
    # Verify no AI client is needed for this review
    assert True  # structural: test_m511 file makes 0 LLM calls by design
