"""
ENG-MISSION52.1 — Historical Contract Identity Audit + Contract V5 Exact-Artifact Human Review
Part A (M521-01..06): Contract identity audit — V4 historical FP, M51 execution ID reproducibility
Part B (M521-07..23): V5 vs M37.8 exact artifact review, regression inventory

0 AI calls. All tests are read-only / computation-only.
"""

import hashlib
import json
import os
import pytest

# ── constants established in M52 ──────────────────────────────────────────────

V5_EXECUTION_ID     = "sha256:559650df434ce99dcdee2c51cbcaf8a374941f4c70b85474d4de90ccfc1fc067"
V5_CANDIDATE_DIGEST = "sha256:7aeadee0f3824a60d91ebe7d90f0a0c230a9bde877d8722bf95cafcc57251876"
V5_CONTRACT_FP      = "sha256:edabf693eb72d391b2ff7a71a38c7a7b2a363f818e438d360046d5feb19023d0"
V5_EVIDENCE_FP      = "sha256:dc623eac6e2350742314f7f4ad44c817e8fe9bb2b4a717e6a864e1da206605a2"

M51_EXECUTION_ID    = "sha256:444fc5f4166d1e5b39e30a58a8469ff2553106ca5f21d777cd1598ea32ae8909"
M51_CANDIDATE_DIGEST = "sha256:5c86d936a296cae6bfd5c88e002ca71ab411a7851f533fea0cd81be3e2faf135"
M51_EVIDENCE_FP     = "sha256:6793736f4298b82142d39d0439f299d7c11f0310ada29ff0a9cc99fac06c2aad"
M51_V4_HISTORICAL_FP = "sha256:46dbdbe96e05fd0c233851ad3ad474fc2dd386f5c0d4955e00dd6fb490291ee7"
M52_V4_CURRENT_FP   = "sha256:cf7747884dd41339701bfb182d8b9fef64a53dd1f5fffe8f0e1cdcf2626111a5"

M37_8_DIGEST        = "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load(path):
    with open(os.path.join(REPO_ROOT, path)) as f:
        return json.load(f)


def _sha256_file(path):
    with open(os.path.join(REPO_ROOT, path), "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


def _sha256_json(data):
    return "sha256:" + hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _compute_execution_id_v3(company, unit, evidence_fp, contract_fp, schema_version="1"):
    raw = json.dumps({
        "company": company,
        "unit": unit,
        "evidence_dependency_fingerprint": evidence_fp,
        "generation_contract_fingerprint": contract_fp,
        "output_schema_version": schema_version,
    }, sort_keys=True)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _compute_execution_id_v5(company, unit, evidence_fp, contract_v5_fp):
    payload = json.dumps({
        "company": company,
        "unit": unit,
        "evidence_fp": evidence_fp,
        "contract_v5_fp": contract_v5_fp,
        "generation_mode": "DETERMINISTIC",
        "assembler_version": "m52_assembler_v5",
    }, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


# ── PART A: Contract Identity Audit (M521-01..06) ─────────────────────────────

def test_m521_01_frozen_v4_manifest_historical_fp_preserved():
    """M521-01: frozen V4 manifest contains the authoritative M51-era V4 FP."""
    frozen = _load("governance/contracts/management_quality_contract_v4_m51_frozen.json")
    assert frozen["historical_contract_v4_fingerprint"] == M51_V4_HISTORICAL_FP, (
        "Historical V4 FP must be preserved verbatim"
    )


def test_m521_02_v4_fp_drifted_after_m52():
    """M521-02: current V4 FP is DIFFERENT from M51-era FP — drift documented."""
    frozen = _load("governance/contracts/management_quality_contract_v4_m51_frozen.json")
    historical = frozen["historical_contract_v4_fingerprint"]
    current    = frozen["current_contract_v4_fingerprint"]
    assert historical != current, "V4 FP must show drift after M52 investor_sections.py fix"
    assert current == M52_V4_CURRENT_FP
    assert frozen["fingerprint_drift"] == "DIFFERENT_DUE_TO_POST_M51_CODE_CHANGE"


def test_m521_03_m51_execution_id_reproducible():
    """M521-03: M51 execution ID is exactly reproducible via compute_execution_id_v3."""
    reproduced = _compute_execution_id_v3(
        "sun_pharma",
        "how_good_is_management_synthesis",
        M51_EVIDENCE_FP,
        M51_V4_HISTORICAL_FP,
    )
    assert reproduced == M51_EXECUTION_ID, (
        f"M51 execution ID must be reproducible; got {reproduced}"
    )


def test_m521_04_v5_execution_id_reproducible():
    """M521-04: V5 execution ID is exactly reproducible via compute_execution_id_v5."""
    reproduced = _compute_execution_id_v5(
        "sun_pharma",
        "how_good_is_management_synthesis",
        V5_EVIDENCE_FP,
        V5_CONTRACT_FP,
    )
    assert reproduced == V5_EXECUTION_ID, (
        f"V5 execution ID must be reproducible; got {reproduced}"
    )


def test_m521_05_investor_sections_changed_since_m51():
    """M521-05: investor_sections.py changed_since_m51=True — M52 fixes documented."""
    frozen = _load("governance/contracts/management_quality_contract_v4_m51_frozen.json")
    inv = frozen["component_digests"]["investor_sections"]
    assert inv["changed_since_m51"] is True
    assert inv["m51_era_digest"] == "NOT_RECOVERABLE_FROM_GIT"


def test_m521_06_v4_fp_reproducibility_partial():
    """M521-06: V4 FP reproducibility is PARTIAL — not fully recomputable from source."""
    frozen = _load("governance/contracts/management_quality_contract_v4_m51_frozen.json")
    verdict = frozen["reproducibility_verdict"]
    assert verdict["M51_HISTORICAL_EXECUTION_ID_REPRODUCIBLE"] is True
    assert verdict["M51_V4_HISTORICAL_FINGERPRINT_REPRODUCIBLE"] == "PARTIAL"


# ── PART B: V5 Exact-Artifact Review (M521-07..23) ────────────────────────────

@pytest.fixture(scope="module")
def v5_candidate():
    return _load(
        "companies/sun_pharma/company_memory/ask_intrinsiciq/"
        "regeneration_candidate_how_good_is_management_559650df434c_v5.json"
    )


@pytest.fixture(scope="module")
def m37_8():
    return _load(
        "companies/sun_pharma/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"
    )


def test_m521_07_v5_candidate_digest_verified(v5_candidate):
    """M521-07: V5 candidate stored candidate_digest field equals governance constant."""
    stored = v5_candidate.get("candidate_digest")
    assert stored == V5_CANDIDATE_DIGEST, (
        f"V5 candidate stored digest mismatch: {stored}"
    )


def test_m521_08_v5_execution_id_in_candidate(v5_candidate):
    """M521-08: V5 candidate execution_id field matches governance constant."""
    exec_id = v5_candidate.get("execution_id") or v5_candidate.get("answer", {}).get("execution_id")
    assert exec_id == V5_EXECUTION_ID


def test_m521_09_m37_8_digest_byte_identical():
    """M521-09: M37.8 certified artifact is byte-identical — not mutated by M52."""
    path = os.path.join(
        REPO_ROOT,
        "companies/sun_pharma/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json",
    )
    with open(path, "rb") as f:
        actual = "sha256:" + hashlib.sha256(f.read()).hexdigest()
    assert actual == M37_8_DIGEST, f"M37.8 byte-identity violated: {actual}"


def test_m521_10_rc1_fix_candor_inconsistent(v5_candidate):
    """M521-10: RC-1 fix — Candor classified as INCONSISTENT (was incorrectly CONSISTENT before fix)."""
    answer = v5_candidate.get("answer", v5_candidate)
    cmap = answer.get("how-good-is-management", answer).get("management_consistency_map", {})
    candor_val = None
    for k, v in cmap.items():
        if "andor" in k or "disclosure" in k.lower() or "transparency" in k.lower():
            candor_val = v
            break
    if candor_val is None:
        # Try direct key lookup
        for k in ["Candor", "candor", "Risk transparency", "Disclosure quality"]:
            if k in cmap:
                candor_val = cmap[k]
                break
    assert candor_val is not None, f"Candor/disclosure key not found in consistency map: {list(cmap.keys())}"
    assert "INCONSISTENT" in str(candor_val).upper() and "UNABLE" not in str(candor_val).upper(), (
        f"RC-1 fix: Candor must be INCONSISTENT, got {candor_val}"
    )


def test_m521_11_rc1_fix_risk_inconsistent(v5_candidate):
    """M521-11: RC-1 fix — Risk classified as INCONSISTENT."""
    answer = v5_candidate.get("answer", v5_candidate)
    cmap = answer.get("how-good-is-management", answer).get("management_consistency_map", {})
    risk_val = None
    for k in ["Risk handling", "Risk transparency", "Risk", "risk", "Hard commitment follow-through"]:
        if k in cmap:
            risk_val = cmap[k]
            break
    assert risk_val is not None, f"Risk key not found in consistency map: {list(cmap.keys())}"
    assert "INCONSISTENT" in str(risk_val).upper(), (
        f"RC-1 fix: Risk must be INCONSISTENT, got {risk_val}"
    )


def test_m521_12_rc2_fix_mc0031_in_what_management_says(v5_candidate):
    """M521-12: RC-2 fix — MC-0031 present in what_management_says (was dropped by early break)."""
    answer = v5_candidate.get("answer", v5_candidate)
    mgmt = answer.get("how-good-is-management", answer)
    wms = mgmt.get("what_management_says", [])
    text = json.dumps(wms)
    assert "MC-0031" in text or "nidlegy" in text.lower() or "ema" in text.lower(), (
        "RC-2 fix: MC-0031 (Nidlegy EMA filing) must appear in what_management_says"
    )


def test_m521_13_three_canonical_commitments_in_what_management_says(v5_candidate):
    """M521-13: All 3 canonical commitments present in what_management_says."""
    answer = v5_candidate.get("answer", v5_candidate)
    mgmt = answer.get("how-good-is-management", answer)
    wms = json.dumps(mgmt.get("what_management_says", []))
    # MC-0039 (By 2030 specialty), MC-0029 (By 2025 US), MC-0031 (H1CY24 Nidlegy)
    for mc in ["MC-0039", "MC-0029", "MC-0031"]:
        assert mc in wms, f"Canonical commitment {mc} missing from what_management_says"


def test_m521_14_pat_in_economic_interpretation(v5_candidate):
    """M521-14: PAT ₹11,479 cr preserved in what_may_mean_economically (vs LLM which dropped it)."""
    answer = v5_candidate.get("answer", v5_candidate)
    mgmt = answer.get("how-good-is-management", answer)
    econ = json.dumps(mgmt.get("what_may_mean_economically", ""))
    assert "11,479" in econ or "11479" in econ, (
        "PAT ₹11,479 cr must be present in economic interpretation"
    )


def test_m521_15_machine_recommendation_needs_changes():
    """M521-15: M52.1 machine recommendation is NEEDS_CHANGES (MC-0031 absent from what_to_monitor)."""
    review = _load("governance/ENG_MISSION52_1_V5_EXACT_ARTIFACT_AND_CONTRACT_IDENTITY_REVIEW.json")
    rec = review.get("machine_recommendation") or review.get("part_b", {}).get("machine_recommendation")
    assert rec == "NEEDS_CHANGES", f"Machine recommendation must be NEEDS_CHANGES, got {rec}"


def test_m521_16_mc0031_absent_from_what_to_monitor(v5_candidate):
    """M521-16: MC-0031 is absent from what_to_monitor — MEDIUM regression vs M37.8."""
    answer = v5_candidate.get("answer", v5_candidate)
    mgmt = answer.get("how-good-is-management", answer)
    wtm = json.dumps(mgmt.get("what_to_monitor", []))
    # MC-0031 = Nidlegy EMA filing, H1CY24 — must NOT be in what_to_monitor
    assert "MC-0031" not in wtm and "nidlegy" not in wtm.lower(), (
        "MC-0031 (Nidlegy EMA) should be ABSENT from what_to_monitor in V5 — this is the documented MEDIUM regression"
    )


def test_m521_17_zero_high_regressions_vs_m37_8():
    """M521-17: V5 has 0 HIGH regressions vs M37.8."""
    review = _load("governance/ENG_MISSION52_1_V5_EXACT_ARTIFACT_AND_CONTRACT_IDENTITY_REVIEW.json")
    part_b = review.get("part_b", review)
    high_count = part_b.get("high_regression_count", 0)
    assert high_count == 0, f"Expected 0 HIGH regressions, got {high_count}"


def test_m521_18_two_medium_regressions_vs_m37_8():
    """M521-18: V5 has exactly 2 MEDIUM regressions vs M37.8."""
    review = _load("governance/ENG_MISSION52_1_V5_EXACT_ARTIFACT_AND_CONTRACT_IDENTITY_REVIEW.json")
    part_b = review.get("part_b", review)
    med_count = part_b.get("medium_regression_count", 0)
    assert med_count == 2, f"Expected 2 MEDIUM regressions, got {med_count}"


def test_m521_19_v5_evidence_freshness_current():
    """M521-19: V5 evidence freshness is CURRENT at time of review."""
    review = _load("governance/ENG_MISSION52_1_V5_EXACT_ARTIFACT_AND_CONTRACT_IDENTITY_REVIEW.json")
    freshness = review.get("evidence_freshness") or review.get("part_a", {}).get("evidence_freshness")
    assert freshness == "CURRENT", f"Evidence freshness must be CURRENT, got {freshness}"


def test_m521_20_comparative_verdict():
    """M521-20: V5 vs M37.8 comparative verdict is V5_MODESTLY_BETTER_THAN_M37_8."""
    review = _load("governance/ENG_MISSION52_1_V5_EXACT_ARTIFACT_AND_CONTRACT_IDENTITY_REVIEW.json")
    part_b = review.get("part_b", review)
    verdict = part_b.get("comparative_verdict")
    assert verdict == "V5_MODESTLY_BETTER_THAN_M37_8", (
        f"Comparative verdict must be V5_MODESTLY_BETTER_THAN_M37_8, got {verdict}"
    )


def test_m521_21_v5_investor_value_adequate():
    """M521-21: V5 candidate investor value classification = ADEQUATE_INVESTOR_VALUE."""
    review = _load("governance/ENG_MISSION52_1_V5_EXACT_ARTIFACT_AND_CONTRACT_IDENTITY_REVIEW.json")
    part_b = review.get("part_b", review)
    val = part_b.get("v5_investor_value")
    assert val == "ADEQUATE_INVESTOR_VALUE", f"V5 investor value must be ADEQUATE, got {val}"


def test_m521_22_m37_8_investor_value_adequate():
    """M521-22: M37.8 investor value classification = ADEQUATE_INVESTOR_VALUE."""
    review = _load("governance/ENG_MISSION52_1_V5_EXACT_ARTIFACT_AND_CONTRACT_IDENTITY_REVIEW.json")
    part_b = review.get("part_b", review)
    val = part_b.get("m37_8_investor_value")
    assert val == "ADEQUATE_INVESTOR_VALUE", f"M37.8 investor value must be ADEQUATE, got {val}"


def test_m521_23_ai_calls_zero():
    """M521-23: M52.1 review executed 0 AI calls."""
    review = _load("governance/ENG_MISSION52_1_V5_EXACT_ARTIFACT_AND_CONTRACT_IDENTITY_REVIEW.json")
    ai_calls = review.get("ai_calls", -1)
    assert ai_calls == 0, f"M52.1 must have 0 AI calls, got {ai_calls}"
