"""
ENG-MISSION49: Contract V3 Investor-Grade Regeneration Canary — 18 tests.

Test IDs: M49-01 through M49-18.
No AI calls. All assertions against deterministic outputs and the
already-executed candidate at its shadow location.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

# ── Repo root ─────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parents[2]
COMPANIES = REPO / "companies"
CANDIDATE_PATH = (
    COMPANIES
    / "sun_pharma"
    / "company_memory"
    / "ask_intrinsiciq"
    / "regeneration_candidate_how_good_is_management_041d464fe52e.json"
)
CERTIFIED_PATH = (
    COMPANIES
    / "sun_pharma"
    / "company_memory"
    / "ask_intrinsiciq"
    / "shadow_level3_hybrid_answers.json"
)

EXPECTED_EXECUTION_ID = "sha256:041d464fe52ecec5329eaf728d93a40ed39ca84c4e1ce5670894b6cbfca989aa"
EXPECTED_EVIDENCE_FP = "sha256:6793736f4298b82142d39d0439f299d7c11f0310ada29ff0a9cc99fac06c2aad"
EXPECTED_CONTRACT_V3_FP = "sha256:f79d63a8a0788c1e22ed8acd455e51a8a2d964a5b5ebd1402b757cdc983c438b"
# M50.1 modified fact_pack_v2.py; CONTRACT_V3_POLICY_DIGEST is now a different value
CURRENT_CONTRACT_V3_FP = "sha256:6ee0f4e37f6484ed078df5b2458970c7d09bc40aeb8f4a1297a4c4ba5ed1e435"
CERTIFIED_DIGEST = "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"


@pytest.fixture(scope="module")
def candidate():
    assert CANDIDATE_PATH.exists(), f"Candidate not found: {CANDIDATE_PATH}"
    with open(CANDIDATE_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def answer(candidate):
    return candidate["answer"]


@pytest.fixture(scope="module")
def fact_pack_v2():
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    return build_management_quality_fact_pack_v2(str(COMPANIES / "sun_pharma"))


# M49-01: Execution ID derivation: stored evidence FP + stored contract FP → stored execution ID
def test_m49_01_execution_id_matches_m48_planned():
    """Verify execution ID was correctly derived from evidence FP + contract V3 FP.
    Uses the FPs stored at execution time (not current — evidence FP may drift as data is updated).
    """
    from intelligence.regeneration_executor import compute_execution_id_v3
    recomputed = compute_execution_id_v3(
        "sun_pharma", "how_good_is_management_synthesis",
        EXPECTED_EVIDENCE_FP, EXPECTED_CONTRACT_V3_FP,
    )
    assert recomputed == EXPECTED_EXECUTION_ID, (
        f"Execution ID derivation broken: {recomputed} != {EXPECTED_EXECUTION_ID}"
    )


# M49-02: Candidate execution manifest stores correct evidence FP and execution ID
def test_m49_02_manifest_stores_canonical_execution_fingerprints():
    """The execution manifest must record the evidence FP and execution ID used at M49 time."""
    import json
    manifest_path = (
        COMPANIES / "sun_pharma" / "company_memory" / "ask_intrinsiciq"
        / "regeneration_execution_manifest.json"
    )
    assert manifest_path.exists(), "Execution manifest missing"
    with open(manifest_path) as f:
        m = json.load(f)
    attempt = next(
        (e for e in m.get("execution_history", []) if e.get("attempt") == 7), None
    )
    assert attempt is not None, "Attempt 7 not found in execution manifest"
    assert attempt.get("evidence_dependency_fingerprint") == EXPECTED_EVIDENCE_FP
    assert attempt.get("execution_id") == EXPECTED_EXECUTION_ID
    assert attempt.get("generation_contract_fingerprint") == EXPECTED_CONTRACT_V3_FP


# M49-03: Contract V3 fingerprint is canonical (CURRENT_CONTRACT_V3_FP post-M50.1)
# M49 execution used EXPECTED_CONTRACT_V3_FP; M50.1 changed fact_pack_v2.py → new FP.
def test_m49_03_contract_v3_fingerprint_canonical():
    from intelligence.management_quality.contract_manifest import CONTRACT_V3_POLICY_DIGEST
    assert CONTRACT_V3_POLICY_DIGEST == CURRENT_CONTRACT_V3_FP, (
        f"Contract V3 FP changed from post-M50.1 canonical: {CONTRACT_V3_POLICY_DIGEST}"
    )


# M49-04: Fact Pack V2 has all 5 capabilities pre-generated
def test_m49_04_fact_pack_v2_five_capabilities(fact_pack_v2):
    assert fact_pack_v2.get("evidence_observations"), "evidence_observations missing"
    assert fact_pack_v2.get("management_statements"), "management_statements missing"
    assert fact_pack_v2.get("consistency_observations"), "consistency_observations missing"
    assert fact_pack_v2.get("consistency_map"), "consistency_map missing"
    assert fact_pack_v2.get("npm") is not None, "npm missing"


# M49-05: Fact Pack V2 has hard_commitment_count
def test_m49_05_fact_pack_v2_hard_commitment_count(fact_pack_v2):
    hc = fact_pack_v2.get("hard_commitment_count", 0)
    assert isinstance(hc, int), "hard_commitment_count must be int"
    assert hc >= 1, f"hard_commitment_count must be >= 1, got {hc}"


# M49-06: Fact Pack V2 NPM is populated
def test_m49_06_fact_pack_v2_npm(fact_pack_v2):
    npm = fact_pack_v2.get("npm")
    assert npm is not None, "npm is None"
    assert isinstance(npm, (int, float)), "npm must be numeric"
    assert npm > 0, f"npm must be positive, got {npm}"


# M49-07: Five-capability preflight all_present
def test_m49_07_five_capability_preflight(fact_pack_v2):
    from intelligence.regeneration_executor import _five_capability_preflight
    result = _five_capability_preflight(fact_pack_v2)
    assert result["all_present"], (
        f"5-capability preflight failed: {result['capabilities']}"
    )


# M49-08: Pre-LLM Contract V3 structure skeleton valid (assembler V3 deterministic sections)
def test_m49_08_assembler_v3_deterministic_skeleton(fact_pack_v2):
    from intelligence.management_quality.assembler_v3 import assemble_management_answer_v3
    assembled = assemble_management_answer_v3(fact_pack_v2, llm_prose=None)
    # All deterministic sections must be present without LLM
    assert assembled["what_evidence_shows"], "what_evidence_shows missing without LLM"
    assert assembled["what_management_says"], "what_management_says missing without LLM"
    assert assembled["where_management_was_consistent"], "where_consistent missing without LLM"
    assert assembled["management_consistency_map"], "consistency_map missing without LLM"
    assert assembled["what_is_not_yet_proven"], "uncertainty missing without LLM"
    assert assembled["what_to_monitor"], "monitoring missing without LLM"
    assert assembled.get("_assembler_version") == "m48_assembler_v3"
    assert assembled.get("_deterministic_sections_preserved") is True


# M49-09: PACP PASS on candidate
def test_m49_09_pacp_pass(candidate):
    assert candidate.get("pacp_overall") == "PASS", (
        f"PACP not PASS: {candidate.get('pacp_overall')}"
    )


# M49-10: EIV V2 PASS on candidate
def test_m49_10_eiv_v2_pass(candidate):
    assert candidate.get("eiv_v2_overall") == "PASS", (
        f"EIV V2 not PASS: {candidate.get('eiv_v2_overall')}"
    )


# M49-11: Semantic parity PASS on candidate
def test_m49_11_parity_pass(candidate):
    assert candidate.get("parity_overall") == "PASS", (
        f"Parity not PASS: {candidate.get('parity_overall')}"
    )


# M49-12: Candidate is HUMAN_REVIEW_ELIGIBLE
def test_m49_12_eligibility_human_review(candidate):
    assert candidate.get("eligibility_state") == "HUMAN_REVIEW_ELIGIBLE", (
        f"Not HUMAN_REVIEW_ELIGIBLE: {candidate.get('eligibility_state')}"
    )


# M49-13: Contract V3 validation passes on candidate answer (with corrected required set)
def test_m49_13_contract_v3_validation_passes(answer):
    from intelligence.regeneration_executor import _validate_contract_v3_structure
    result = _validate_contract_v3_structure(answer)
    assert result["valid"], f"Contract V3 validation fails: {result['fails']}"


# M49-14: what_evidence_shows has >= 2 items
def test_m49_14_what_evidence_shows_min_two(answer):
    wes = answer.get("what_evidence_shows", [])
    assert isinstance(wes, list), "what_evidence_shows must be list"
    assert len(wes) >= 2, f"what_evidence_shows has {len(wes)} items, need >= 2"
    assert all(len(str(e)) > 15 for e in wes), "what_evidence_shows items too short"


# M49-15: management_consistency_map has >= 3 entries
def test_m49_15_consistency_map_min_three(answer):
    mcm = answer.get("management_consistency_map", {})
    assert isinstance(mcm, dict), "management_consistency_map must be dict"
    assert len(mcm) >= 3, f"management_consistency_map has {len(mcm)} entries, need >= 3"


# M49-16: deterministic_precision_facts includes NPM DPF
def test_m49_16_dpf_includes_npm(answer):
    dpfs = answer.get("deterministic_precision_facts", [])
    assert len(dpfs) >= 1, "No deterministic_precision_facts"
    all_text = " ".join(
        str(d.get("value", "")) + str(d.get("semantic_meaning", ""))
        for d in dpfs
    )
    assert "NPM" in all_text or "npm" in all_text.lower(), (
        "No DPF contains NPM; Contract V3 requires NPM in DPFs"
    )


# M49-17: Assembler V3 markers present in candidate answer
def test_m49_17_assembler_v3_markers(answer):
    assert answer.get("_assembler_version") == "m48_assembler_v3", (
        f"_assembler_version wrong: {answer.get('_assembler_version')}"
    )
    assert answer.get("_deterministic_sections_preserved") is True


# M49-18: Candidate is in shadow location; certified artifact is byte-identical (not mutated)
def test_m49_18_certified_artifact_not_mutated():
    assert CERTIFIED_PATH.exists(), f"Certified artifact missing: {CERTIFIED_PATH}"
    raw = CERTIFIED_PATH.read_bytes()
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    assert digest == CERTIFIED_DIGEST, (
        f"CERTIFIED ARTIFACT MUTATED: {digest} != {CERTIFIED_DIGEST}"
    )
    # Candidate must be at shadow location (different file)
    assert CANDIDATE_PATH != CERTIFIED_PATH, "Candidate must not overwrite certified"
    assert CANDIDATE_PATH.exists(), f"Candidate missing: {CANDIDATE_PATH}"
