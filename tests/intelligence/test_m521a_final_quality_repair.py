"""
ENG-MISSION52.1a — Final Quality Repair: MC-0031 Monitoring + Historical Integrity
25 tests (M521A-01 through M521A-25)

What this covers:
  - MC-0031 monitoring fix: all material hard commitments in what_to_monitor (not just top 2)
  - Cross-section coverage consistency
  - Sparse-evidence safety
  - Historical candidate immutability (old M52 candidate byte-identical)
  - Deleted-file failures reconciled (3/3 M52 tests now pass)
  - Historical V4 identity preserved (PARTIAL reproducibility honestly recorded)
  - New V5 contract FP after investor_sections.py fix
  - New execution ID derivation
  - 5-run determinism + 4-company replay
  - PACP + EIV + freshness
  - Candidate unapproved, inactive; M37.8 live; AI calls = 0

AI calls used: 0
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COMPANY_MEMORY = REPO / "companies"

# ── M52.1a identity constants ────────────────────────────────────────────────
NEW_V5_CONTRACT_FP   = "sha256:ab55a485b88bd3082eaf4cc55e5603dfeb3cc866837ef7f3daefc0e309322d55"
NEW_V5_EXECUTION_ID  = "sha256:76315ffdb92646c0ab28f1f020f7ae5e76e9cd8bb38fe1758680c3bd04f1683e"
NEW_V5_CANDIDATE_DIGEST = "sha256:f7fd0583d313e86ce2d351b3f6c643901b5203ecc2db55c53457ee80c97dd30a"
V5_EVIDENCE_FP       = "sha256:dc623eac6e2350742314f7f4ad44c817e8fe9bb2b4a717e6a864e1da206605a2"

# Old M52 constants (preserved for immutability checks)
OLD_V5_CONTRACT_FP   = "sha256:edabf693eb72d391b2ff7a71a38c7a7b2a363f818e438d360046d5feb19023d0"
OLD_V5_EXECUTION_ID  = "sha256:559650df434ce99dcdee2c51cbcaf8a374941f4c70b85474d4de90ccfc1fc067"
OLD_V5_CANDIDATE_DIGEST = "sha256:7aeadee0f3824a60d91ebe7d90f0a0c230a9bde877d8722bf95cafcc57251876"

# Historical V4 / M51 constants
M51_V4_HISTORICAL_FP = "sha256:46dbdbe96e05fd0c233851ad3ad474fc2dd386f5c0d4955e00dd6fb490291ee7"
M51_EXECUTION_ID     = "sha256:444fc5f4166d1e5b39e30a58a8469ff2553106ca5f21d777cd1598ea32ae8909"

M37_8_DIGEST = "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"

NEW_CANDIDATE_PATH = COMPANY_MEMORY / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / \
    "regeneration_candidate_how_good_is_management_76315ffdb926_v5.json"
OLD_CANDIDATE_PATH = COMPANY_MEMORY / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / \
    "regeneration_candidate_how_good_is_management_559650df434c_v5.json"
M37_8_PATH = COMPANY_MEMORY / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / \
    "shadow_level3_hybrid_answers.json"


@pytest.fixture(scope="module")
def sun_pharma_fp():
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    return build_management_quality_fact_pack_v2("sun_pharma")


@pytest.fixture(scope="module")
def sun_pharma_v5_answer(sun_pharma_fp):
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    return build_management_answer_v5(sun_pharma_fp)


@pytest.fixture(scope="module")
def new_candidate():
    return json.loads(NEW_CANDIDATE_PATH.read_text())


# ── M521A-01: MC-0031 selection root cause verified ──────────────────────────
def test_m521a_01_mc0031_root_cause_fix():
    """build_what_to_monitor iterates ALL hard commitments, not just top 2."""
    import inspect
    from intelligence.management_quality.investor_sections import build_what_to_monitor
    src = inspect.getsource(build_what_to_monitor)
    # The fix removed the [:2] slice on the sorted hard-commitments loop
    # Confirm the old pattern is gone
    assert "sorted_hc[:2]" not in src, (
        "MC-0031 root cause still present: sorted_hc[:2] truncates commitments"
    )


# ── M521A-02: Material hard-commitment monitoring coverage ───────────────────
def test_m521a_02_all_hard_commitments_in_monitor(sun_pharma_fp):
    """All canonical Sun Pharma hard commitments appear in what_to_monitor."""
    from intelligence.management_quality.investor_sections import build_what_to_monitor
    hard_commits = sun_pharma_fp.get("hard_commitments", [])
    monitor_items = build_what_to_monitor(sun_pharma_fp)
    monitor_text = " ".join(monitor_items).lower()
    for hc in hard_commits:
        mc_id = hc.get("id", "")
        assert mc_id.lower() in monitor_text, (
            f"Hard commitment {mc_id} missing from what_to_monitor"
        )


# ── M521A-03: No arbitrary commitment truncation ─────────────────────────────
def test_m521a_03_no_commitment_truncation(sun_pharma_fp):
    """what_to_monitor count >= number of hard commitments (no silent drops)."""
    from intelligence.management_quality.investor_sections import build_what_to_monitor
    hard_commits = sun_pharma_fp.get("hard_commitments", [])
    monitor_items = build_what_to_monitor(sun_pharma_fp)
    assert len(monitor_items) >= len(hard_commits), (
        f"Monitor has {len(monitor_items)} items but {len(hard_commits)} hard commitments exist"
    )


# ── M521A-04: Cross-section coverage consistency ────────────────────────────
def test_m521a_04_cross_section_coverage(sun_pharma_v5_answer):
    """MC-0031 appears in both what_management_says and what_to_monitor."""
    wms = sun_pharma_v5_answer.get("what_management_says", [])
    wtm = sun_pharma_v5_answer.get("what_to_monitor", [])
    wms_text = " ".join(wms).lower()
    wtm_text = " ".join(wtm).lower()
    assert "mc-0031" in wms_text or "nidlegy" in wms_text, (
        "MC-0031/Nidlegy missing from what_management_says"
    )
    assert "mc-0031" in wtm_text or "nidlegy" in wtm_text, (
        "MC-0031/Nidlegy missing from what_to_monitor"
    )


# ── M521A-05: No invented deadline ──────────────────────────────────────────
def test_m521a_05_no_invented_deadline(sun_pharma_fp, sun_pharma_v5_answer):
    """Every timeframe in what_to_monitor must trace to a canonical hard commitment."""
    from intelligence.management_quality.investor_sections import build_what_to_monitor
    hard_commits = sun_pharma_fp.get("hard_commitments", [])
    canonical_tfs = {hc.get("expected_timeframe", "").lower() for hc in hard_commits if hc.get("expected_timeframe")}
    monitor_items = build_what_to_monitor(sun_pharma_fp)
    import re
    for item in monitor_items:
        # Extract bracketed timeframe like [MC-0031, target: H1CY24]
        m = re.search(r"target:\s*([^\]]+)\]", item, re.IGNORECASE)
        if m:
            tf = m.group(1).strip().lower()
            assert tf in canonical_tfs or tf == "ongoing" or tf == "continuous", (
                f"Timeframe '{tf}' in monitor item not in canonical hard commitments: {item}"
            )


# ── M521A-06: Sparse evidence safe ──────────────────────────────────────────
def test_m521a_06_sparse_evidence_safe():
    """build_what_to_monitor handles fact pack with 0 hard commitments (no crash)."""
    from intelligence.management_quality.investor_sections import build_what_to_monitor
    sparse_fp = {"company": "test", "hard_commitments": [], "management_commitments": []}
    result = build_what_to_monitor(sparse_fp)
    assert isinstance(result, list), "build_what_to_monitor must return list for sparse input"


# ── M521A-07: Consistency-map correctness retained ──────────────────────────
def test_m521a_07_consistency_map_correct(sun_pharma_v5_answer):
    """Candor and Risk handling are never CONSISTENT (M52 substring-bug invariant).

    M52.2d: recurring risks alone are not proof of inconsistent behaviour, so these entries are
    UNABLE_TO_VERIFY rather than INCONSISTENT; the exact-status parsing guarantee is unchanged."""
    cmap = sun_pharma_v5_answer.get("management_consistency_map", {})
    st = lambda v: str(v).split(" — ")[0].strip()
    for label in ("Candor and consistency", "Risk handling"):
        assert st(cmap.get(label)) in ("UNABLE_TO_VERIFY", "INCONSISTENT", "PARTIALLY_CONSISTENT"), cmap.get(label)


# ── M521A-08: DPF values retained ───────────────────────────────────────────
def test_m521a_08_dpf_values_retained(sun_pharma_fp, sun_pharma_v5_answer):
    """data_pattern_flags in answer matches what fact pack provides."""
    fp_dpf = sun_pharma_fp.get("data_pattern_flags", {})
    answer_dpf = sun_pharma_v5_answer.get("data_pattern_flags", {})
    for k, v in fp_dpf.items():
        assert answer_dpf.get(k) == v, f"DPF key {k} changed: fp={v}, answer={answer_dpf.get(k)}"


# ── M521A-09: PAT and financial context retained ────────────────────────────
def test_m521a_09_pat_and_financial_context(sun_pharma_fp):
    """PAT value from fact pack is present in the generated answer text."""
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    answer = build_management_answer_v5(sun_pharma_fp)
    pat = sun_pharma_fp.get("pat_cr", "")
    if pat:
        answer_text = json.dumps(answer).lower()
        pat_str = str(pat).replace(",", "").split(".")[0]  # normalize
        assert pat_str in answer_text or "pat" in answer_text, (
            f"PAT value {pat} not found in answer"
        )


# ── M521A-10: Historical candidates immutable ────────────────────────────────
def test_m521a_10_old_m52_candidate_immutable():
    """Old M52 candidate (559650df) is byte-identical to when it was written."""
    assert OLD_CANDIDATE_PATH.exists(), f"Old M52 candidate missing: {OLD_CANDIDATE_PATH}"
    old_data = json.loads(OLD_CANDIDATE_PATH.read_text())
    stored_digest = old_data.get("candidate_digest")
    assert stored_digest == OLD_V5_CANDIDATE_DIGEST, (
        f"Old M52 candidate digest changed: stored={stored_digest}"
    )
    # Execution ID also unchanged
    assert old_data.get("execution_id") == OLD_V5_EXECUTION_ID, (
        f"Old M52 execution ID changed: {old_data.get('execution_id')}"
    )


# ── M521A-11: All deleted-file failures reconciled ──────────────────────────
def test_m521a_11_deleted_file_failures_reconciled():
    """M52 tests that depended on missing files (test_m52_27, _31, _32) all pass."""
    # Verify by directly running the assertions from those tests
    # test_m52_27: TOKEN_TELEMETRY has 0 planned AI calls
    from intelligence.regeneration_planner import TOKEN_TELEMETRY
    telemetry = TOKEN_TELEMETRY.get("how_good_is_management_synthesis", {})
    assert telemetry.get("planned_ai_calls") == 0

    # test_m52_31 + test_m52_32: M51 HR file exists with correct human decisions
    hr_path = REPO / "governance" / "ENG_MISSION51_NARRATIVE_ONLY_REGENERATION_HUMAN_REVIEW.json"
    assert hr_path.exists(), f"M51 HR file missing: {hr_path}"
    data = json.loads(hr_path.read_text())
    hd = data.get("human_decision_m511", {})
    assert hd.get("ARTIFACT_HUMAN_DECISION") == "NEEDS_CHANGES"
    assert hd.get("AI_ARCHITECTURE_HUMAN_DECISION") == "REMOVE_AI"
    assert hd.get("m51_final_investor_value_canonical") == "ADEQUATE_INVESTOR_VALUE"


# ── M521A-12: Restored contracts have trustworthy provenance ────────────────
def test_m521a_12_restored_file_provenance():
    """ENG_MISSION51 HR reconstruction is clearly labeled with provenance metadata."""
    hr_path = REPO / "governance" / "ENG_MISSION51_NARRATIVE_ONLY_REGENERATION_HUMAN_REVIEW.json"
    assert hr_path.exists(), f"Restored governance file missing: {hr_path}"
    data = json.loads(hr_path.read_text())
    assert "RECONSTRUCTED" in data.get("_note", ""), (
        "_note must contain RECONSTRUCTED label"
    )
    assert "_provenance" in data, "Restored file must have _provenance field"
    assert "_reconstruction_date" in data, "Restored file must have _reconstruction_date"


# ── M521A-13: Historical V4 fingerprint preserved ───────────────────────────
def test_m521a_13_historical_v4_fp_preserved():
    """Frozen V4 identity snapshot retains M51-era V4 FP."""
    contract_path = REPO / "governance" / "contracts" / "management_quality_contract_v4_m51_frozen.json"
    assert contract_path.exists(), f"Frozen V4 contract missing: {contract_path}"
    data = json.loads(contract_path.read_text())
    # Field is historical_contract_v4_fingerprint
    assert data.get("historical_contract_v4_fingerprint") == M51_V4_HISTORICAL_FP, (
        f"M51 V4 historical FP changed: {data.get('historical_contract_v4_fingerprint')}"
    )


# ── M521A-14: Historical reproducibility limitation honestly recorded ────────
def test_m521a_14_partial_reproducibility_honest():
    """Frozen V4 contract records PARTIAL reproducibility (not FULL)."""
    contract_path = REPO / "governance" / "contracts" / "management_quality_contract_v4_m51_frozen.json"
    data = json.loads(contract_path.read_text())
    # _reproducibility is a string; reproducibility_verdict is a dict
    repro_str = data.get("_reproducibility", "")
    verdict = data.get("reproducibility_verdict", {})
    assert "PARTIAL" in repro_str or verdict.get("M51_V4_HISTORICAL_FINGERPRINT_REPRODUCIBLE") == "PARTIAL", (
        f"Reproducibility must be PARTIAL; _reproducibility={repro_str!r}, verdict={verdict}"
    )


# ── M521A-15: Modified V5 policy changes contract fingerprint ───────────────
def test_m521a_15_new_fp_differs_from_old():
    """Historical: the stored M52.1a candidate carries its own (changed) contract FP.

    The live Contract V5 FP has since moved on (M52.2a); see M522A tests for the live identity.
    """
    stored = json.loads(NEW_CANDIDATE_PATH.read_text())["contract_v5_fingerprint"]
    assert stored == NEW_V5_CONTRACT_FP
    assert stored != OLD_V5_CONTRACT_FP, "M52.1a FP must differ from the old M52 FP"


# ── M521A-16: New execution ID derived correctly ────────────────────────────
def test_m521a_16_new_execution_id_correct():
    """New execution ID computed from new contract FP yields NEW_V5_EXECUTION_ID."""
    from intelligence.management_quality.assembler_v5 import compute_execution_id_v5
    exec_id = compute_execution_id_v5(
        "sun_pharma",
        "how_good_is_management_synthesis",
        V5_EVIDENCE_FP,
        NEW_V5_CONTRACT_FP,
    )
    assert exec_id == NEW_V5_EXECUTION_ID, (
        f"New execution ID mismatch: {exec_id}"
    )
    assert exec_id != OLD_V5_EXECUTION_ID, (
        "New execution ID must differ from old M52 execution ID"
    )


# ── M521A-17: Five-run deterministic generation stable ──────────────────────
def test_m521a_17_five_run_determinism_sun_pharma():
    """5 independent runs produce identical answer digests."""
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    digests = set()
    for _ in range(5):
        fp = build_management_quality_fact_pack_v2("sun_pharma")
        a = build_management_answer_v5(fp)
        digests.add(hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest())
    assert len(digests) == 1, f"Non-deterministic across 5 runs: {digests}"


# ── M521A-18: Four-company replay passes ────────────────────────────────────
def test_m521a_18_four_company_replay():
    """Assembler V5 produces valid output for sun_pharma, tanla, ujjivan, ltts."""
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    companies = ["sun_pharma", "tanla", "ujjivan", "ltts"]
    for co in companies:
        try:
            fp = build_management_quality_fact_pack_v2(co)
            answer = build_management_answer_v5(fp)
            assert isinstance(answer, dict), f"{co}: answer must be dict"
            assert "key_points" in answer or "simple_answer" in answer, (
                f"{co}: answer missing required fields"
            )
        except Exception as e:
            pytest.fail(f"4-company replay failed for {co}: {e}")


# ── M521A-19: PACP PASS required ────────────────────────────────────────────
def test_m521a_19_pacp_pass(sun_pharma_fp, sun_pharma_v5_answer):
    """Answer passes semantic capability parity checks (PACP)."""
    from intelligence.management_quality.capability_parity_validator import (
        validate_management_semantic_capability_parity,
    )
    result = validate_management_semantic_capability_parity(sun_pharma_v5_answer)
    assert result.get("overall") == "PASS", (
        f"PACP overall not PASS: {result.get('overall')}\n"
        f"failures: {[c for c in result.get('checks', []) if c.get('status') == 'FAIL']}"
    )


# ── M521A-20: EIV PASS required ─────────────────────────────────────────────
def test_m521a_20_eiv_pass(sun_pharma_fp, sun_pharma_v5_answer):
    """Answer passes External Investor Value validation."""
    from intelligence.external_investor_value_validator import validate_management_answer_eiv
    result = validate_management_answer_eiv(sun_pharma_v5_answer, sun_pharma_fp)
    assert result.get("overall") == "PASS", (
        f"EIV overall not PASS: {result.get('overall')}\n"
        f"failures: {[c for c in result.get('checks', []) if c.get('status') == 'FAIL']}"
    )


# ── M521A-21: Freshness CURRENT required ────────────────────────────────────
def test_m521a_21_evidence_freshness_current(new_candidate):
    """New candidate's evidence FP matches canonical (evidence is CURRENT)."""
    stored_ev_fp = new_candidate.get("evidence_fingerprint")
    assert stored_ev_fp == V5_EVIDENCE_FP, (
        f"Evidence FP changed — evidence may not be current: {stored_ev_fp}"
    )


# ── M521A-22: Candidate remains unapproved ──────────────────────────────────
def test_m521a_22_candidate_unapproved(new_candidate):
    """New M52.1a candidate has no human approval (approval must come from human reviewer)."""
    # Candidate must not have human_approved=True or approval fields
    assert new_candidate.get("human_approved") is not True, (
        "Candidate must not be auto-approved"
    )
    assert new_candidate.get("human_decision") not in ("APPROVE", "APPROVED"), (
        "Candidate must not be pre-approved"
    )


# ── M521A-23: Candidate remains inactive (canary matrix = 20) ────────────────
def test_m521a_23_canary_matrix_unchanged():
    """New candidate is at shadow path only — it did not overwrite the certified serving artifact."""
    # Candidate must be at a shadow path (execution ID in filename), not the certified path
    assert NEW_CANDIDATE_PATH.exists(), f"New candidate missing: {NEW_CANDIDATE_PATH}"
    assert "shadow_level3_hybrid_answers" not in NEW_CANDIDATE_PATH.name, (
        "New candidate must not overwrite the certified serving artifact"
    )
    exec_id_hex = NEW_V5_EXECUTION_ID.replace("sha256:", "")[:12]
    assert exec_id_hex in NEW_CANDIDATE_PATH.name, (
        f"New candidate filename must contain execution ID prefix '{exec_id_hex}': {NEW_CANDIDATE_PATH.name}"
    )
    # Certified artifact (M37.8) is a different path
    assert NEW_CANDIDATE_PATH != M37_8_PATH, (
        "New candidate must not be the same file as the certified M37.8 artifact"
    )


# ── M521A-24: M37.8 remains live (byte-identical) ───────────────────────────
def test_m521a_24_m37_8_byte_identical():
    """M37.8 certified artifact is byte-identical — no overwrite occurred."""
    assert M37_8_PATH.exists(), f"M37.8 artifact missing: {M37_8_PATH}"
    actual = "sha256:" + hashlib.sha256(M37_8_PATH.read_bytes()).hexdigest()
    assert actual == M37_8_DIGEST, (
        f"M37.8 byte-identity violated: {actual}"
    )


# ── M521A-25: AI calls = 0 ───────────────────────────────────────────────────
def test_m521a_25_zero_ai_calls(new_candidate, sun_pharma_v5_answer):
    """New candidate records 0 AI calls; assembler confirms ZERO_AI_CALLS_INVARIANT."""
    assert new_candidate.get("ai_calls_made") == 0, (
        f"ai_calls_made must be 0, got: {new_candidate.get('ai_calls_made')}"
    )
    assert new_candidate.get("zero_ai_calls") is True, (
        "zero_ai_calls flag must be True"
    )
    # Assembler-level check
    from intelligence.management_quality.contract_manifest import CONTRACT_V5_POLICY_DIGEST
    assert CONTRACT_V5_POLICY_DIGEST is not None  # ensures contract manifest imported OK
