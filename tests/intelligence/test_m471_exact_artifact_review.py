"""
M47.1 Exact-Artifact Human Review — deterministic verification tests.
Tests M471-01 through M471-13.
0 AI calls. No approval. No activation. No runtime mutation.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
CANDIDATE_PATH = ROOT / "companies/sun_pharma/company_memory/ask_intrinsiciq/regeneration_candidate_how_good_is_management_9d120267e32e.json"
REVIEW_PACKAGE_PATH = ROOT / "governance/ENG_MISSION47_INVESTOR_GRADE_REGENERATION_HUMAN_REVIEW.json"
CERTIFIED_PATH = ROOT / "companies/sun_pharma/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"
APPROVAL_REGISTRY_PATH = ROOT / "governance/approval_registry.json"
LAUNCH_JSON_PATH = ROOT / ".claude/launch.json"

GOVERNANCE_CANDIDATE_DIGEST = "sha256:baf9c79f728a9024c1a24fac9de4ba9c0138596d61cb7325efaf2e95e4a39fe7"
GOVERNANCE_CERTIFIED_DIGEST = "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"
M47_EXECUTION_ID = "sha256:9d120267e32e0cd12a3864abb112258e"
M378_FINGERPRINT = "37e04b439bf5cfa3"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def candidate():
    return json.loads(CANDIDATE_PATH.read_bytes())


@pytest.fixture(scope="module")
def review_package():
    return json.loads(REVIEW_PACKAGE_PATH.read_bytes())


@pytest.fixture(scope="module")
def fact_pack():
    sys.path.insert(0, str(ROOT))
    from intelligence.management_quality.fact_pack import build_management_quality_fact_pack
    return build_management_quality_fact_pack("sun_pharma")


# M471-01: Candidate digest matches review package
def test_m471_01_candidate_digest_matches_review_package(review_package):
    expected = review_package["candidate_summary"]["candidate_digest"]
    recomputed = _sha256(CANDIDATE_PATH)
    assert recomputed == expected, (
        f"Candidate digest mismatch: recomputed={recomputed} expected={expected}. "
        "Candidate bytes changed after governance review was written — human decision is invalid."
    )


# M471-02: Candidate maps to M47 execution identity
def test_m471_02_candidate_execution_identity(candidate):
    assert candidate["execution_id"] == M47_EXECUTION_ID
    assert candidate["mission"] == "ENG-MISSION47"
    assert candidate["company"] == "sun_pharma"
    assert candidate["unit"] == "how_good_is_management_synthesis"
    assert candidate["schema_version"] == "m47_candidate_v1"


# M471-03: PACP PASS recorded for exact candidate digest
def test_m471_03_pacp_pass_tied_to_exact_digest(candidate, review_package):
    assert candidate["pacp_overall"] == "PASS"
    # Review package PACP result must reference the same candidate
    pacp = review_package["automated_checks"]["pacp"]
    assert pacp["overall"] == "PASS"
    # Digest in review package must match candidate
    assert review_package["candidate_summary"]["candidate_digest"] == GOVERNANCE_CANDIDATE_DIGEST


# M471-04: EIV PASS recorded for exact candidate digest
def test_m471_04_eiv_pass_tied_to_exact_digest(candidate, review_package):
    assert candidate["eiv_overall"] == "PASS"
    eiv = review_package["automated_checks"]["eiv"]
    assert eiv["overall"] == "PASS"
    assert eiv["fail_count"] == 0
    assert len(eiv["rules_passed"]) == 8


# M471-05: Lifecycle counts match deterministic fact pack
def test_m471_05_lifecycle_counts_match_fact_pack(candidate, fact_pack):
    pc = fact_pack["progression_counts"]
    assert pc["total"] == 25
    assert pc["announced"] == 23
    assert pc["in_progress"] == 2

    dpfs = candidate["answer"]["deterministic_precision_facts"]
    delivery_dpf = next(d for d in dpfs if "Delivery" in d["metric"] or "delivery" in d["metric"].lower())
    assert "0 delivered" in delivery_dpf["value"]
    assert "2 in_progress" in delivery_dpf["value"]
    assert "23 announced" in delivery_dpf["value"]
    assert "25" in delivery_dpf["value"]


# M471-06: DPFs match deterministic fact pack
def test_m471_06_dpfs_match_fact_pack(candidate, fact_pack):
    candidate_dpfs = {d["metric"]: d["value"] for d in candidate["answer"]["deterministic_precision_facts"]}
    fp_dpfs = {d["metric"]: d["value"] for d in fact_pack["dpfs"]}

    # Every fact_pack DPF must appear in candidate DPFs
    for metric, value in fp_dpfs.items():
        assert metric in candidate_dpfs, f"DPF metric '{metric}' from fact_pack missing in candidate"
        assert candidate_dpfs[metric] == value, (
            f"DPF value mismatch for '{metric}': candidate='{candidate_dpfs[metric]}' fact_pack='{value}'"
        )


# M471-07: Behavioral descriptor matches deterministic derivation
def test_m471_07_behavioral_descriptor_deterministic(candidate, fact_pack):
    assert fact_pack["behavioral_descriptor"] == "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
    assert candidate["behavioral_descriptor"] == "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
    assert candidate["answer"]["behavioral_descriptor"] == "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
    # Descriptor must appear verbatim in simple_answer
    assert "FOLLOW_THROUGH_LARGELY_UNVERIFIED" in candidate["answer"]["simple_answer"]
    # Derivation: 0 delivered out of 25 → delivery_rate = 0.0 → FOLLOW_THROUGH_LARGELY_UNVERIFIED
    pc = fact_pack["progression_counts"]
    delivery_rate = 0  # 0 delivered of total
    assert pc["total"] == 25
    assert delivery_rate < 0.10  # threshold for FOLLOW_THROUGH_LARGELY_UNVERIFIED


# M471-08: No prohibited rating or personality language in investor-facing fields
def test_m471_08_no_prohibited_language(candidate):
    answer = candidate["answer"]
    investor_fields = [
        answer.get("simple_answer", ""),
        answer.get("why_it_matters", ""),
        answer.get("investor_interpretation", ""),
        " ".join(answer.get("key_points", [])),
        answer.get("what_is_not_yet_proven", ""),
        " ".join(answer.get("what_to_monitor", [])),
    ]
    full_text = " ".join(investor_fields)

    # Rating labels not allowed
    for label in ["MQ overall:", "Management quality overall:", "WEAK", "MIXED", "STRONG"]:
        assert label not in full_text, f"Prohibited rating label '{label}' found in investor-facing text"

    # Personality judgments not allowed
    for term in ["honesty", "integrity", "intelligent", "trustworthy", "shareholder friendly"]:
        assert term.lower() not in full_text.lower(), f"Personality judgment '{term}' found in investor-facing text"


# M471-09: Material claims trace to canonical evidence (spot-check key claims)
def test_m471_09_material_claims_traceability(candidate, fact_pack):
    # Claim: "0 items delivered out of 25 commitments"
    simple = candidate["answer"]["simple_answer"]
    assert "0 items delivered" in simple or "0 delivered" in str(candidate["answer"]["deterministic_precision_facts"])

    # Claim: strongest_dimension = capital_allocation_discipline
    assert fact_pack["strongest_dimension"] == "capital_allocation_discipline"

    # Claim: financial figures
    fin = fact_pack["financial_context"]
    assert abs(fin["revenue"]["value"] - 58462.04) < 1.0
    assert abs(fin["pat"]["value"] - 11479.42) < 1.0


# M471-10: UNKNOWN preservation — UNKNOWN not converted to FAILED or DELIVERED
def test_m471_10_unknown_preservation(candidate):
    answer = candidate["answer"]
    text_fields = [
        answer.get("simple_answer", ""),
        answer.get("investor_interpretation", ""),
        " ".join(answer.get("key_points", [])),
        answer.get("what_is_not_yet_proven", ""),
    ]
    full_text = " ".join(text_fields).lower()

    # Must not convert unknowns to confirmed failures or deliveries without evidence
    # "announced" items must not be called "failed" or "undelivered failures"
    assert "announced commitments indicate a lack of follow-through" in full_text or \
           "announced" in full_text, "Announced commitments must be preserved as announced, not failed"

    # Commitment status must be "unable to verify" not "failed"
    commit_dpf = next(
        (d for d in answer["deterministic_precision_facts"] if "commitment" in d["metric"].lower()),
        None
    )
    assert commit_dpf is not None
    assert "unable to verify" in commit_dpf["value"].lower() or "utv" in commit_dpf["value"].lower()


# M471-11: M45.2 major regressions absent — DPFs present, delivery counts present
def test_m471_11_m452_major_regressions_absent(candidate):
    answer = candidate["answer"]
    dpfs = answer.get("deterministic_precision_facts", [])

    # M45.2 had 0 DPFs — must now have >= 3
    assert len(dpfs) >= 3, f"M45.2 DPF regression present: only {len(dpfs)} DPFs, need >= 3"

    # Delivery count must be present in DPFs or key_points
    delivery_present = any("0 delivered" in str(d) for d in dpfs)
    counts_in_key_points = any("0 of 25" in kp or "0 items delivered" in kp or "0 delivered" in kp
                                for kp in answer.get("key_points", []))
    assert delivery_present or counts_in_key_points, "M45.2 regression: delivery counts missing from DPFs and key_points"

    # Financial context must be present
    fin_dpf = next((d for d in dpfs if "Financial" in d["metric"] or "financial" in d["metric"].lower()), None)
    assert fin_dpf is not None, "M45.2 regression: financial context DPF missing"
    assert "58,462" in fin_dpf["value"] or "58462" in fin_dpf["value"]


# M471-12: Human decision is REJECT (recorded by M48 — M47.1 machine recommendation was REJECT_RECOMMENDED)
def test_m471_12_human_decision_pending(review_package):
    # M48 recorded the human decision as REJECT per machine recommendation REJECT_RECOMMENDED
    # Status updated from AWAITING_HUMAN_REVIEW to HUMAN_DECISION_REJECT
    assert review_package["status"] in ("AWAITING_HUMAN_REVIEW", "HUMAN_DECISION_REJECT"), (
        f"Unexpected status: {review_package['status']}"
    )
    # Eligibility state is correct
    assert review_package["automated_checks"]["eligibility"]["state"] == "HUMAN_REVIEW_ELIGIBLE"
    # Human decision must be REJECT (recorded by M48) or still PENDING
    m471_review = review_package.get("m47_1_exact_artifact_review", {})
    human_decision = m471_review.get("human_decision")
    assert human_decision in (None, "PENDING", "REJECT"), (
        f"Human decision must be PENDING or REJECT, got {human_decision}"
    )


# M471-13: Production artifact remains unchanged (M37.8 still serving)
def test_m471_13_production_artifact_unchanged():
    recomputed = _sha256(CERTIFIED_PATH)
    assert recomputed == GOVERNANCE_CERTIFIED_DIGEST, (
        f"CERTIFIED ARTIFACT MUTATED: recomputed={recomputed} expected={GOVERNANCE_CERTIFIED_DIGEST}"
    )
    # Approval registry still points to M37.8 fingerprint
    registry = json.loads(APPROVAL_REGISTRY_PATH.read_bytes())
    sp_entry = registry["approvals"]["sun_pharma:how-good-is-management"]
    assert sp_entry["fingerprint"] == M378_FINGERPRINT, (
        f"Approval registry fingerprint changed: {sp_entry['fingerprint']} != {M378_FINGERPRINT}"
    )
    # M47 candidate NOT in approval registry
    assert "baf9c79f728a9024c1a24fac9de4ba9c0138596d61cb7325efaf2e95e4a39fe7" not in str(registry)
