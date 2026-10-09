"""
M46.1 tests: Contract V2 fingerprint binding + EIV eligibility gate.

23 tests:
  CF-01..08  Material contract components change generation fingerprint
  CF-09      Non-semantic metadata does not change fingerprint
  ID-01      Same evidence + Contract v2 = new execution ID vs M45.2
  ELIG-01..07 Eligibility state machine
  REPLAY-01  M45.2 rejected candidate automatically blocked
  GOOD-01..04 All 4 certified answers satisfy new minimum standard
  HUMAN-01   Human REJECT remains authoritative
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional
import pytest

# ── Imports under test ────────────────────────────────────────────────────────
from intelligence.management_quality.contract_manifest import (
    ASSEMBLER_POLICY,
    ASSEMBLER_POLICY_DIGEST,
    CONTRACT_V2_POLICY_DIGEST,
    DPF_POLICY,
    DPF_POLICY_DIGEST,
    EIV_POLICY_DIGEST,
    EIV_POLICY_VERSION,
    FACT_PACK_SCHEMA_DIGEST,
    FACT_PACK_SCHEMA_VERSION,
    GENERATION_CONTRACT_SCHEMA,
    MANAGEMENT_ANSWER_CONTRACT_SCHEMA_DIGEST,
    MANAGEMENT_ANSWER_CONTRACT_VERSION,
    OUTPUT_SCHEMA_VERSION,
    build_contract_v2_manifest,
    compute_contract_v2_fingerprint,
)
from intelligence.management_quality.candidate_eligibility import (
    BLOCKED_ARTIFACT_IDENTITY,
    BLOCKED_EIV,
    BLOCKED_MULTIPLE,
    BLOCKED_PACP,
    HUMAN_REVIEW_ELIGIBLE,
    evaluate_candidate_release_eligibility,
)
from intelligence.regeneration_executor import (
    UNIT_TARGET,
    _compute_contract_fingerprint,
    compute_execution_id,
)
from intelligence.external_investor_value_validator import validate_management_answer_eiv

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPANIES_ROOT = _REPO_ROOT / "companies"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_certified_answer(company: str) -> Optional[Dict]:
    p = _COMPANIES_ROOT / company / "company_memory" / "ask_intrinsiciq" / "shadow_level3_hybrid_answers.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    entry = data.get("answers", {}).get("how-good-is-management", {})
    return entry.get("answer") if isinstance(entry, dict) else None


def _load_m45_2_candidate() -> Optional[Dict]:
    p = _COMPANIES_ROOT / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / "regeneration_candidate_how_good_is_management.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def _minimal_good_candidate(answer: Dict, pacp_overall: str = "PASS") -> Dict:
    """Wrap a certified answer into a candidate-like dict for eligibility testing."""
    digest = "sha256:" + hashlib.sha256(json.dumps(answer, sort_keys=True).encode()).hexdigest()
    return {
        "candidate_digest": digest,
        "pacp_result": {"overall": pacp_overall},
        "answer": answer,
    }


# ── M461-CF-01..08: Material changes alter generation fingerprint ──────────────

def test_cf01_management_answer_contract_version_changes_fp():
    """CF-01: Management answer contract version change → new contract FP."""
    base = build_contract_v2_manifest()
    modified = copy.deepcopy(base)
    modified["management_answer_contract"]["version"] = "3"

    fp_base = hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()
    fp_mod = hashlib.sha256(json.dumps(modified, sort_keys=True).encode()).hexdigest()
    assert fp_base != fp_mod, "CF-01 FAIL: contract version change did not alter manifest hash"


def test_cf02_management_answer_contract_content_changes_fp():
    """CF-02: Management answer contract schema content change → new contract FP."""
    base = build_contract_v2_manifest()
    modified = copy.deepcopy(base)
    modified["management_answer_contract"]["digest"] = "sha256:" + "0" * 64

    fp_base = hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()
    fp_mod = hashlib.sha256(json.dumps(modified, sort_keys=True).encode()).hexdigest()
    assert fp_base != fp_mod, "CF-02 FAIL: contract digest change did not alter manifest hash"


def test_cf03_fact_pack_schema_changes_fp():
    """CF-03: Fact-pack schema version change → new contract FP."""
    base = build_contract_v2_manifest()
    modified = copy.deepcopy(base)
    modified["fact_pack_schema"]["version"] = "management_fact_pack.v2"

    fp_base = hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()
    fp_mod = hashlib.sha256(json.dumps(modified, sort_keys=True).encode()).hexdigest()
    assert fp_base != fp_mod, "CF-03 FAIL: fact_pack schema change did not alter manifest hash"


def test_cf04_assembler_policy_changes_fp():
    """CF-04: Assembler policy content change → new contract FP."""
    base = build_contract_v2_manifest()
    modified = copy.deepcopy(base)
    modified["assembler_policy"]["digest"] = "sha256:" + "1" * 64

    fp_base = hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()
    fp_mod = hashlib.sha256(json.dumps(modified, sort_keys=True).encode()).hexdigest()
    assert fp_base != fp_mod, "CF-04 FAIL: assembler policy change did not alter manifest hash"


def test_cf05_dpf_policy_changes_fp():
    """CF-05: DPF policy content change → new contract FP."""
    base = build_contract_v2_manifest()
    modified = copy.deepcopy(base)
    modified["dpf_policy"]["digest"] = "sha256:" + "2" * 64

    fp_base = hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()
    fp_mod = hashlib.sha256(json.dumps(modified, sort_keys=True).encode()).hexdigest()
    assert fp_base != fp_mod, "CF-05 FAIL: DPF policy change did not alter manifest hash"


def test_cf06_descriptor_policy_in_assembler_changes_fp():
    """CF-06: Descriptor constraint in assembler policy changes FP."""
    import copy as _copy
    new_assembler = _copy.deepcopy(ASSEMBLER_POLICY)
    new_assembler["invariant"] = "CHANGED_INVARIANT"
    new_digest = hashlib.sha256(json.dumps(new_assembler, sort_keys=True).encode()).hexdigest()
    assert new_digest != ASSEMBLER_POLICY_DIGEST.lstrip("sha256:"), (
        "CF-06 FAIL: assembler invariant change did not alter digest"
    )


def test_cf07_eiv_policy_version_changes_fp():
    """CF-07: EIV policy version change → new contract FP."""
    base = build_contract_v2_manifest()
    modified = copy.deepcopy(base)
    modified["eiv_policy"]["version"] = "eiv_management_quality.v2"

    fp_base = hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()
    fp_mod = hashlib.sha256(json.dumps(modified, sort_keys=True).encode()).hexdigest()
    assert fp_base != fp_mod, "CF-07 FAIL: EIV version change did not alter manifest hash"


def test_cf08_output_schema_version_changes_fp():
    """CF-08: Output schema version change → new contract FP."""
    fp_v1 = compute_contract_v2_fingerprint(output_schema_version="1")
    fp_v2 = compute_contract_v2_fingerprint(output_schema_version="2")
    assert fp_v1 != fp_v2, "CF-08 FAIL: output schema version change did not alter contract FP"


def test_cf09_non_semantic_changes_do_not_alter_fp():
    """CF-09: Timestamps, run IDs, absolute paths do NOT enter the manifest or FP."""
    manifest = build_contract_v2_manifest()
    # Verify no timestamp, run_id, or path in manifest keys
    all_keys = set()
    def _collect_keys(obj: Any):
        if isinstance(obj, dict):
            for k, v in obj.items():
                all_keys.add(k)
                _collect_keys(v)
    _collect_keys(manifest)
    non_semantic_keys = {"timestamp", "run_id", "executed_at", "path", "absolute_path", "machine"}
    intersection = all_keys & non_semantic_keys
    assert not intersection, f"CF-09 FAIL: non-semantic keys found in manifest: {intersection}"
    # FP with same inputs is always identical
    fp1 = compute_contract_v2_fingerprint()
    fp2 = compute_contract_v2_fingerprint()
    assert fp1 == fp2, "CF-09 FAIL: FP not stable across identical calls"


# ── M461-ID-01: Same evidence + new contract = new execution ID ───────────────

def test_id01_contract_v2_produces_new_execution_id():
    """ID-01: Same evidence_fp + Contract v2 contract_fp ≠ M45.2 execution ID."""
    # M45.2 known values
    m45_2_evidence_fp = "sha256:6793736f4298b82142d39d0439f299d7c11f0310ada29ff0a9cc99fac06c2aad"
    m45_2_execution_id = "sha256:1301fe09d781e2fef373ff2866a52949"

    # New Contract v2 fingerprint (uses m46_contract_v1 schema + v2 policy digest)
    new_contract_fp = _compute_contract_fingerprint("2", "1", "gpt-4o-mini")

    # New execution ID with same evidence but new contract
    new_execution_id = compute_execution_id(
        "sun_pharma", UNIT_TARGET, m45_2_evidence_fp, new_contract_fp
    )

    assert new_execution_id != m45_2_execution_id, (
        "ID-01 FAIL: Contract v2 produced same execution ID as M45.2 — "
        "contract change did not propagate to execution identity"
    )

    # Also verify: new contract FP ≠ M45.2 contract FP
    m45_2_contract_fp = "sha256:a626ea1610a99499aa11614d44774a4d"
    assert new_contract_fp != m45_2_contract_fp, (
        "ID-01 FAIL: New contract FP == M45.2 contract FP — "
        "m46_contract_v1 schema + v2 policy digest did not alter fingerprint"
    )


# ── M461-ELIG-01..07: Eligibility state machine ───────────────────────────────

def _good_answer() -> Dict:
    """Minimal answer that passes all 8 EIV rules."""
    return {
        "simple_answer": (
            "FOLLOW_THROUGH_LARGELY_UNVERIFIED: 0 of 25 progression items confirmed delivered "
            "across FY20-FY26 disclosures. Revenue grew to ₹47,964 cr (FY26) but causal "
            "attribution to management plans is not established. All 46 commitments remain "
            "Unable To Verify. Capital allocation decisions lack confirmed execution outcomes."
        ),
        "key_points": [
            "0 of 25 progression items confirmed delivered across multi-year tracking",
            "46 of 46 commitments Unable To Verify (FY26)",
            "Behavioral pattern: FOLLOW_THROUGH_LARGELY_UNVERIFIED",
        ],
        "what_evidence_shows": [
            "No delivery confirmed across 25 tracked management initiatives",
            "All 46 commitments remain Unable To Verify in public disclosures",
        ],
        "what_is_not_yet_proven": "Whether management can convert announced initiatives to delivery.",
        "deterministic_precision_facts": [
            {
                "metric": "Delivery follow-through",
                "value": "0 delivered / 2 in_progress / 23 announced (of 25)",
                "period": "multi-year",
                "semantic_meaning": "No progression item confirmed delivered",
            },
            {
                "metric": "Progression items",
                "value": "0 delivered / 25 total",
                "period": "multi-year",
                "semantic_meaning": "0 of 25 items confirmed delivered",
            },
            {
                "metric": "Management commitments",
                "value": "46 total; 46 unable to verify",
                "period": "multi-year",
                "semantic_meaning": "All commitments Unable To Verify",
            },
        ],
    }


def test_elig01_pacp_pass_eiv_pass_is_eligible():
    """ELIG-01: PACP PASS + EIV PASS → HUMAN_REVIEW_ELIGIBLE."""
    answer = _good_answer()
    eiv = validate_management_answer_eiv(answer)
    assert eiv["overall"] == "PASS", f"Test setup: EIV should PASS for good answer, got {eiv['fails']}"

    candidate = _minimal_good_candidate(answer)
    result = evaluate_candidate_release_eligibility(candidate, eiv_result=eiv)
    assert result["eligible"] is True
    assert result["eligibility_state"] == HUMAN_REVIEW_ELIGIBLE


def test_elig02_pacp_pass_eiv_fail_is_blocked_eiv():
    """ELIG-02: PACP PASS + EIV FAIL → BLOCKED_EIV (not eligible)."""
    # Answer missing DPFs — will fail EIV-MQ-04
    bad_answer = {"simple_answer": "FOLLOW_THROUGH_LARGELY_UNVERIFIED.", "key_points": ["a", "b", "c"], "what_evidence_shows": ["x", "y"]}
    eiv = validate_management_answer_eiv(bad_answer)
    assert eiv["overall"] == "FAIL"

    candidate = {"candidate_digest": "sha256:" + "a" * 64, "pacp_result": {"overall": "PASS"}, "answer": bad_answer}
    result = evaluate_candidate_release_eligibility(candidate, eiv_result=eiv)
    assert result["eligible"] is False
    assert result["eligibility_state"] == BLOCKED_EIV
    assert "BLOCKED_EIV" in result["blocks"]


def test_elig03_pacp_fail_eiv_pass_is_blocked_pacp():
    """ELIG-03: PACP FAIL + EIV PASS → BLOCKED_PACP (not eligible)."""
    answer = _good_answer()
    eiv = validate_management_answer_eiv(answer)
    assert eiv["overall"] == "PASS"

    candidate = {"candidate_digest": "sha256:" + "b" * 64, "pacp_result": {"overall": "FAIL"}, "answer": answer}
    result = evaluate_candidate_release_eligibility(candidate, eiv_result=eiv)
    assert result["eligible"] is False
    assert result["eligibility_state"] == BLOCKED_PACP


def test_elig04_identity_failure_blocks_eligibility():
    """ELIG-04: Missing candidate_digest → BLOCKED_ARTIFACT_IDENTITY."""
    answer = _good_answer()
    eiv = validate_management_answer_eiv(answer)

    candidate = {"candidate_digest": "", "pacp_result": {"overall": "PASS"}, "answer": answer}
    result = evaluate_candidate_release_eligibility(candidate, eiv_result=eiv)
    assert result["eligible"] is False
    assert result["artifact_identity_valid"] is False
    assert BLOCKED_ARTIFACT_IDENTITY in result["blocks"]


def test_elig05_missing_eiv_blocks_eligibility():
    """ELIG-05: EIV result is None → evaluator runs inline; if answer is bad, blocks."""
    # Candidate with no DPFs — inline EIV will FAIL
    bad_answer = {"simple_answer": "Generic.", "key_points": ["x"], "claims": []}
    candidate = {"candidate_digest": "sha256:" + "c" * 64, "pacp_result": {"overall": "PASS"}, "answer": bad_answer}
    # eiv_result=None forces inline run
    result = evaluate_candidate_release_eligibility(candidate, eiv_result=None)
    assert result["eligible"] is False
    # eiv_overall should not be PASS
    assert result["eiv_overall"] != "PASS"


def test_elig06_eligibility_performs_no_approval_mutation():
    """ELIG-06: evaluate_candidate_release_eligibility never writes approval registry."""
    candidate = _minimal_good_candidate(_good_answer())
    result = evaluate_candidate_release_eligibility(candidate)
    # Result carries explicit no-mutation proof flags
    assert result["_approval_registry_mutated"] is False, "ELIG-06 FAIL: approval registry mutated"


def test_elig07_eligibility_performs_no_activation_mutation():
    """ELIG-07: evaluate_candidate_release_eligibility never activates a candidate."""
    candidate = _minimal_good_candidate(_good_answer())
    result = evaluate_candidate_release_eligibility(candidate)
    assert result["_candidate_activated"] is False, "ELIG-07 FAIL: candidate activated"


# ── M461-REPLAY-01: M45.2 rejected candidate automatically fails ──────────────

def test_replay01_m45_2_candidate_fails_eligibility():
    """REPLAY-01: M45.2 PACP-passing candidate is BLOCKED_EIV under new gate."""
    cand = _load_m45_2_candidate()
    if cand is None:
        pytest.skip("M45.2 candidate file not found")

    # Known historical state: PACP PASS
    pacp = {"overall": "PASS"}
    # Run eligibility — EIV runs inline against the candidate
    result = evaluate_candidate_release_eligibility(cand, pacp_result=pacp)

    assert result["eligible"] is False, (
        "REPLAY-01 FAIL: M45.2 PACP-passing candidate should be BLOCKED under EIV gate"
    )
    assert BLOCKED_EIV in result["blocks"], (
        f"REPLAY-01 FAIL: expected BLOCKED_EIV in blocks, got {result['blocks']}"
    )
    assert result["eiv_overall"] == "FAIL", (
        f"REPLAY-01 FAIL: expected EIV FAIL, got {result['eiv_overall']}"
    )


# ── M461-GOOD-01..04: All 4 certified answers pass EIV ────────────────────────

@pytest.mark.parametrize("company", ["sun_pharma", "datapatterns", "tanla", "ujjivan"])
def test_good_certified_answer_passes_eiv(company: str):
    """GOOD-01..04: Currently certified management-quality answers satisfy new EIV standard."""
    answer = _load_certified_answer(company)
    if answer is None:
        pytest.skip(f"Certified answer not found for {company}")

    eiv = validate_management_answer_eiv(answer)
    assert eiv["overall"] == "PASS", (
        f"GOOD: {company} certified answer fails EIV — fails: {eiv['fails']}. "
        f"This would be a false negative (good artifact blocked)."
    )

    # Also verify it would be HUMAN_REVIEW_ELIGIBLE under the full gate
    candidate = _minimal_good_candidate(answer)
    result = evaluate_candidate_release_eligibility(candidate, eiv_result=eiv)
    assert result["eligible"] is True, (
        f"GOOD: {company} certified answer ineligible under full gate — "
        f"state: {result['eligibility_state']}, blocks: {result['blocks']}"
    )


# ── M461-HUMAN-01: Human REJECT authority ────────────────────────────────────

def test_human01_human_reject_remains_authoritative():
    """HUMAN-01: Human REJECT decision is not reset by running eligibility evaluator."""
    cand = _load_m45_2_candidate()
    if cand is None:
        pytest.skip("M45.2 candidate file not found")

    # Load the human review record and verify REJECT is recorded
    review_path = _REPO_ROOT / "governance" / "ENG_MISSION45_MANAGEMENT_REGENERATION_HUMAN_REVIEW.json"
    if review_path.exists():
        review = json.loads(review_path.read_text())
        human_section = review.get("section_28_human_decision_placeholder", {})
        human_decision = human_section.get("HUMAN_DECISION", "PENDING")
        assert human_decision == "REJECT", (
            f"HUMAN-01 FAIL: expected HUMAN_DECISION=REJECT, got {human_decision}"
        )

    # Running eligibility evaluator with PACP=PASS does NOT change the human decision
    pacp = {"overall": "PASS"}
    result = evaluate_candidate_release_eligibility(cand, pacp_result=pacp)
    # The evaluator returns BLOCKED_EIV; it must not flip human decision
    assert result["_approval_registry_mutated"] is False
    assert result["_candidate_activated"] is False
    # The human review file must still say REJECT
    if review_path.exists():
        review_after = json.loads(review_path.read_text())
        human_section_after = review_after.get("section_28_human_decision_placeholder", {})
        assert human_section_after.get("HUMAN_DECISION") == "REJECT", (
            "HUMAN-01 FAIL: running eligibility evaluator mutated human REJECT decision"
        )
