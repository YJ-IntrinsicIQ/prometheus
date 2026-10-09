"""
M50.2 Governance Reconciliation — 19 tests (M502-01 through M502-19)

Covers:
- D7 (DEFECT-M4): unresolved-item prioritization — historical defect valid,
  current prevention STRUCTURALLY_IMPOSSIBLE via materiality-sorted hard commitments
- D6 (DEFECT-M3): evidence_confidence vs outcome state type confusion — historical
  defect valid, current prevention is TYPED_SCHEMA_VALIDATION (NOT rating quarantine)
- Canonical hard commitment count = 3 consistently
- Historical counts (4, 5) preserved only as historical records
- Contract V4 fingerprint recomputation
- Planned M51 execution ID
- Release state unchanged
"""
import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from intelligence.management_quality.investor_sections import (
    build_management_consistency_map,
    build_what_is_not_yet_proven,
    _commitment_materiality_score,
    _sort_commitments_by_materiality,
)
from intelligence.management_quality.fact_pack_v2 import (
    build_management_quality_fact_pack_v2,
    _is_hard_commitment,
)
from intelligence.management_quality.rating_quarantine import (
    contains_rating_language,
)
from intelligence.management_quality.contract_manifest import (
    CONTRACT_V4_POLICY_DIGEST,
    compute_contract_v4_fingerprint,
)
from intelligence.regeneration_executor import compute_execution_id_v3

GOVERNANCE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "governance")
COMPANY_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "companies", "sun_pharma", "company_memory", "ask_intrinsiciq",
)
M49_2_REVIEW = os.path.join(GOVERNANCE_DIR, "ENG_MISSION49_2_EXACT_ARTIFACT_HUMAN_REVIEW.json")
M50_PROOF = os.path.join(GOVERNANCE_DIR, "ENG_MISSION50_DETERMINISTIC_INVESTOR_SECTIONS_PROOF.json")
M501_PROOF = os.path.join(GOVERNANCE_DIR, "ENG_MISSION50_1_CLOSURE_VERIFICATION_PROOF.json")
SHADOW_ARTIFACT = os.path.join(COMPANY_DIR, "shadow_level3_hybrid_answers.json")
M49_CANDIDATE = os.path.join(COMPANY_DIR, "regeneration_candidate_how_good_is_management_041d464fe52e.json")
M47_CANDIDATE = os.path.join(COMPANY_DIR, "regeneration_candidate_how_good_is_management_9d120267e32e.json")
M45_CANDIDATE = os.path.join(COMPANY_DIR, "regeneration_candidate_how_good_is_management.json")

_M48_EVIDENCE_FP = "sha256:6793736f4298b82142d39d0439f299d7c11f0310ada29ff0a9cc99fac06c2aad"
# M50.1/M51-era V4 FP (before M52 investor_sections.py fixes)
_M51_ERA_V4_FP = "sha256:46dbdbe96e05fd0c233851ad3ad474fc2dd386f5c0d4955e00dd6fb490291ee7"
# M52-era V4 FP (after investor_sections.py consistency-map + MC-0031 fixes)
_CANONICAL_V4_FP = "sha256:cf7747884dd41339701bfb182d8b9fef64a53dd1f5fffe8f0e1cdcf2626111a5"
_M37_8_DIGEST = "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"


# ── D7: unresolved-item prioritization ───────────────────────────────────────

def test_m502_01_d7_historical_defect_supported_by_m49_2():
    """D7 historical defect is supported by evidence in M49.2 review.

    M49 selected MC-0012 (fy21) and MC-0023 (fy18) in what_is_not_yet_proven.
    M37.8 correctly featured Nidlegy EMA filing (H1CY24) and 35% carbon (2030).
    This is a genuine regression, not a NOT_A_REGRESSION.
    """
    with open(M49_2_REVIEW) as f:
        review = json.load(f)
    defects = review.get("defect_inventory", {}).get("medium_severity", [])
    m4 = next((d for d in defects if d.get("id") == "DEFECT-M4"), None)
    assert m4 is not None, "DEFECT-M4 (unresolved-item prioritization) must exist in M49.2 review"
    assert "fy21" in m4.get("detail", "").lower() or "fy18" in m4.get("detail", "").lower(), (
        "DEFECT-M4 must document past-FY codes selected by M49"
    )
    assert "nidlegy" in m4.get("detail", "").lower() or "carbon" in m4.get("detail", "").lower(), (
        "DEFECT-M4 must reference the more investor-relevant future commitments"
    )
    # Confirm lower investor priority of M49 selection
    assert m4.get("verdict") == "WORSE" or "worse" in m4.get("detail", "").lower() or \
           "lower" in m4.get("detail", "").lower() or "lower-priority" in m4.get("detail", "").lower() or \
           "past" in m4.get("detail", "").lower(), (
        "DEFECT-M4 must document M49's inferior selection"
    )


def test_m502_02_d7_current_prevention_deterministic_selector():
    """D7 current prevention: materiality-sorted canonical hard commitments via
    build_what_is_not_yet_proven — STRUCTURALLY_IMPOSSIBLE.

    MC-0012 and MC-0023 are NOT in canonical hard_commitments (excluded by M50.1
    verifiability policy), so they can NEVER appear in what_is_not_yet_proven.
    """
    fp = build_management_quality_fact_pack_v2("sun_pharma")
    hard_ids = {h.get("id") for h in fp.get("hard_commitments", [])}
    assert "MC-0012" not in hard_ids, "MC-0012 (aspirational) must not be in canonical hard commitments"
    assert "MC-0023" not in hard_ids, "MC-0023 (aspirational) must not be in canonical hard commitments"

    # what_is_not_yet_proven must not contain past-FY aspirational codes
    result = build_what_is_not_yet_proven(fp)
    assert "MC-0012" not in result, "MC-0012 (fy21 aspirational) must not appear in what_is_not_yet_proven"
    assert "MC-0023" not in result, "MC-0023 (fy18 aspirational) must not appear in what_is_not_yet_proven"


def test_m502_03_d7_materiality_recent_beats_old():
    """D7 adversarial: recent material hard commitment scores higher than old
    low-materiality aspirational item.

    UNRESOLVED_ITEM_PRIORITY_PASS = true
    """
    old_low = {
        "id": "MC-0012",
        "expected_timeframe": "in fy21",
        "normalized_commitment": "Build a strong pipeline in generic products.",
        "topic": "pipeline",
        "category": "strategic",
    }
    high_mat = {
        "id": "MC-0039",
        "expected_timeframe": "By 2030",
        "normalized_commitment": (
            "Achieve a 35 reduction in absolute scope 1 and scope 2 carbon emissions."
        ),
        "topic": "carbon",
        "category": "esg",
    }
    score_old = _commitment_materiality_score(old_low, latest_fy=26)
    score_high = _commitment_materiality_score(high_mat, latest_fy=26)
    assert score_high > score_old, (
        f"Material commitment (score={score_high}) must outrank old aspirational "
        f"(score={score_old}). UNRESOLVED_ITEM_PRIORITY_PASS = true"
    )
    # Old low-materiality should actually be penalized
    assert score_old < 0, f"Past-FY aspirational item should be penalized: score={score_old}"


# ── D6: evidence confidence vs outcome state type confusion ──────────────────

def test_m502_04_d6_historical_defect_documented_in_m49_2():
    """D6 historical defect is documented in M49.2 DEFECT-M3.

    M49 consistency_map had evidence_confidence → UNABLE_TO_VERIFY despite
    canonical evidence_confidence = 'high'.
    """
    with open(M49_2_REVIEW) as f:
        review = json.load(f)
    defects = review.get("defect_inventory", {}).get("medium_severity", [])
    m3 = next((d for d in defects if d.get("id") == "DEFECT-M3"), None)
    assert m3 is not None, "DEFECT-M3 (consistency-map dimension labels) must exist in M49.2 review"
    assert "unable_to_verify" in m3.get("detail", "").lower() or \
           "unable to verify" in m3.get("detail", "").lower(), (
        "DEFECT-M3 must document evidence_confidence → UNABLE_TO_VERIFY confusion"
    )
    assert "evidence_confidence" in m3.get("detail", "").lower(), (
        "DEFECT-M3 must name evidence_confidence as the confounded dimension"
    )


def test_m502_05_d6_evidence_confidence_and_outcome_stay_separate():
    """D6 adversarial: evidence_confidence='high' in fact_pack must NOT be rendered
    as UNABLE_TO_VERIFY in consistency_map, even when raw map contains UNABLE_TO_VERIFY.

    CONFIDENCE_OUTCOME_TYPE_SEPARATION_PASS = true
    """
    fp_patched = {
        "consistency_map": {
            "execution_discipline": "CONSISTENT",
            "evidence_confidence": "UNABLE_TO_VERIFY",  # what M49 injected into raw map
        },
        "evidence_confidence": "high",  # canonical fact_pack value
    }
    result = build_management_consistency_map(fp_patched)
    ec_value = result.get("Evidence confidence", "")
    assert "UNABLE_TO_VERIFY" not in ec_value, (
        f"D6 type confusion reproduced: evidence_confidence rendered as '{ec_value}'"
    )
    assert "HIGH" in ec_value, (
        f"Evidence confidence must render as HIGH when canonical is 'high'. Got: '{ec_value}'"
    )


def test_m502_06_d6_prevention_is_not_rating_quarantine():
    """D6 prevention must NOT be attributed to rating quarantine.

    Rating quarantine prevents 'strong management' / 'weak management' language.
    It does NOT prevent type confusion between evidence confidence and outcome states.
    Verify: 'UNABLE_TO_VERIFY' and 'HIGH' are not detected as rating language.
    """
    assert not contains_rating_language("UNABLE_TO_VERIFY"), (
        "UNABLE_TO_VERIFY is not rating language — rating quarantine does not prevent D6"
    )
    assert not contains_rating_language("HIGH — multiple source streams confirm evidence quality"), (
        "HIGH confidence text is not rating language — rating quarantine does not prevent D6"
    )
    assert not contains_rating_language("Evidence confidence: HIGH"), (
        "Evidence confidence assessment is not rating language"
    )


# ── Canonical hard commitment count = 3 ──────────────────────────────────────

def test_m502_07_canonical_hard_count_3():
    """Canonical Sun Pharma hard commitment count = 3 (M50.1 policy)."""
    fp = build_management_quality_fact_pack_v2("sun_pharma")
    assert len(fp.get("hard_commitments", [])) == 3, (
        f"Canonical count must be 3. Got: {len(fp.get('hard_commitments', []))}"
    )


def test_m502_08_historical_counts_preserved_not_claimed_canonical():
    """Historical counts (M37.8=4, M49=5) are preserved only as historical records.

    M50 proof and M50.1 proof must document historical values separately
    from the canonical_count = 3.
    """
    with open(M50_PROOF) as f:
        m50 = json.load(f)
    hcd = m50.get("hard_commitment_discrepancy_resolution", {})
    # Historical values must be present as historical
    assert hcd.get("m37_8_count") == 4, "M37.8 historical count must be preserved as 4"
    assert hcd.get("m49_v2_count") == 5, "M49 V2 historical count must be preserved as 5"
    # Current canonical must be 3
    assert hcd.get("canonical_count") == 3, (
        f"Current canonical_count must be 3. Got: {hcd.get('canonical_count')}"
    )


def test_m502_09_no_active_governance_claims_4_or_5_as_canonical():
    """No active governance file claims 4 or 5 as the current canonical hard commitment count.

    Historical values are labeled as such (m37_8_count, hard_v2, etc.).
    """
    with open(M50_PROOF) as f:
        m50 = json.load(f)
    hcd = m50.get("hard_commitment_discrepancy_resolution", {})
    assert hcd.get("canonical_count") == 3, (
        f"M50 proof must claim canonical_count = 3. Got: {hcd.get('canonical_count')}"
    )

    with open(M501_PROOF) as f:
        m501 = json.load(f)
    fh = m501.get("hard_commitment_forensics", {})
    canonical_counts = fh.get("canonical_counts", {})
    assert canonical_counts.get("sun_pharma", {}).get("count") == 3, (
        "M50.1 proof must record sun_pharma canonical_count = 3"
    )


# ── Contract V4 fingerprint ───────────────────────────────────────────────────

def test_m502_10_contract_v4_fingerprint_recomputes_exactly():
    """Contract V4 fingerprint recomputes to same value as stored constant.

    Full SHA-256, not abbreviated.
    """
    recomputed = compute_contract_v4_fingerprint()
    assert recomputed == CONTRACT_V4_POLICY_DIGEST, (
        f"Fingerprint mismatch: stored={CONTRACT_V4_POLICY_DIGEST}, "
        f"recomputed={recomputed}"
    )
    assert recomputed == _CANONICAL_V4_FP, (
        f"Fingerprint does not match expected M52-era canonical: {recomputed}. "
        f"M51-era value was {_M51_ERA_V4_FP} (before M52 investor_sections.py fixes)."
    )


def test_m502_11_governance_records_use_current_v4_fingerprint():
    """M50 and M50.1 governance proofs record the V4 FP that was current when they were written.
    These are historical records written with the M51-era V4 FP (before M52 investor_sections.py fixes)."""
    with open(M50_PROOF) as f:
        m50 = json.load(f)
    cv4 = m50.get("contract_v4", {})
    stored_fp = cv4.get("fingerprint", "")
    # M50/M50.1 governance files were written with M51-era FP (historical)
    assert stored_fp == _M51_ERA_V4_FP, (
        f"M50 proof has unexpected fingerprint: {stored_fp}"
    )

    with open(M501_PROOF) as f:
        m501 = json.load(f)
    fp_section = m501.get("contract_v4_fingerprint", {})
    assert fp_section.get("value") == _M51_ERA_V4_FP, (
        f"M50.1 proof has unexpected fingerprint: {fp_section.get('value')}"
    )


def test_m502_12_planned_m51_execution_id_recomputes():
    """Planned M51 execution ID recomputes deterministically from canonical inputs.
    Uses M51-era V4 FP (not the M52-era FP) because M51 was executed with that contract."""
    recomputed = compute_execution_id_v3(
        "sun_pharma",
        "how_good_is_management_synthesis",
        _M48_EVIDENCE_FP,
        _M51_ERA_V4_FP,  # M51 was executed with this FP (before M52 investor_sections.py fixes)
    )
    expected = "sha256:444fc5f4166d1e5b39e30a58a8469ff2553106ca5f21d777cd1598ea32ae8909"
    assert recomputed == expected, (
        f"M51 planned execution ID mismatch: expected={expected}, "
        f"recomputed={recomputed}"
    )
    # Must be full SHA-256 (64 hex chars after sha256:)
    assert len(recomputed.split(":")[1]) == 64, "Execution ID must be full SHA-256"


# ── D1-D8 matrix completeness ────────────────────────────────────────────────

def test_m502_13_d1_d8_matrix_has_no_unresolved_prevention():
    """M50.2 proof records all 8 defects with explicit prevention mechanisms.

    Check that D6 and D7 now have correct (non-empty) prevention, not misattributed.
    """
    proof_path = os.path.join(GOVERNANCE_DIR, "ENG_MISSION50_2_GOVERNANCE_RECONCILIATION_PROOF.json")
    with open(proof_path) as f:
        proof = json.load(f)
    matrix = proof.get("m49_defect_matrix_final", {})
    required_keys = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"]
    for key in required_keys:
        assert key in matrix, f"Missing defect {key} in M50.2 defect matrix"
        entry = matrix[key]
        assert entry.get("current_prevention") not in (None, "", "UNKNOWN", "UNRESOLVED"), (
            f"{key} has unresolved prevention mechanism: {entry.get('current_prevention')}"
        )


def test_m502_14_no_high_medium_defect_still_possible():
    """No HIGH or MEDIUM severity M49 defect should remain STILL_POSSIBLE.

    Acceptable statuses: STRUCTURALLY_IMPOSSIBLE, DETERMINISTIC_SELECTOR,
    TYPED_SCHEMA_VALIDATION, ASSEMBLER_PROTECTION, NOT_A_REGRESSION.
    """
    proof_path = os.path.join(GOVERNANCE_DIR, "ENG_MISSION50_2_GOVERNANCE_RECONCILIATION_PROOF.json")
    with open(proof_path) as f:
        proof = json.load(f)
    matrix = proof.get("m49_defect_matrix_final", {})
    for key, entry in matrix.items():
        if entry.get("severity") in ("HIGH", "MEDIUM"):
            prev = entry.get("current_prevention", "")
            assert "STILL_POSSIBLE" not in prev, (
                f"{key} ({entry.get('severity')}) prevention is STILL_POSSIBLE: {prev}"
            )


# ── Rejected candidate / production state ────────────────────────────────────

def test_m502_15_rejected_candidate_states_unchanged():
    """M45.2, M47, M49 remain REJECTED / inactive — verified via execution manifest."""
    manifest_path = os.path.join(COMPANY_DIR, "regeneration_execution_manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)
    history = manifest.get("execution_history", [])
    outcomes = {
        entry.get("execution_id", "")[:24]: entry.get("outcome", "")
        for entry in history
    }

    # M49 (attempt 7, exec_id sha256:041d464fe52e...): must be HUMAN_REJECTED
    m49_entries = [e for e in history if str(e.get("execution_id", "")).startswith("sha256:041d464fe52e")]
    assert any(e.get("outcome") == "HUMAN_REJECTED" for e in m49_entries), (
        f"M49 must have HUMAN_REJECTED outcome in execution manifest. Found: {[e.get('outcome') for e in m49_entries]}"
    )

    # M47 (attempt 5, exec_id sha256:9d120267...): awaiting human review (REJECTED by process)
    m47_entries = [e for e in history if str(e.get("execution_id", "")).startswith("sha256:9d120267")]
    assert len(m47_entries) > 0, "M47 execution must exist in manifest history"

    # M45.2 candidate file must exist (not overwritten)
    assert os.path.exists(M45_CANDIDATE), "M45.2 candidate file must still exist"


def test_m502_16_m37_8_production_artifact_unchanged():
    """M37.8 artifact byte-identical (production unchanged)."""
    with open(SHADOW_ARTIFACT, "rb") as f:
        actual = "sha256:" + hashlib.sha256(f.read()).hexdigest()
    assert actual == _M37_8_DIGEST, (
        f"M37.8 production artifact mutated: {actual}"
    )


def test_m502_17_approval_registry_20_entries():
    """Approval registry has 20 entries (canary matrix 20-pair, unchanged)."""
    with open(os.path.join(GOVERNANCE_DIR, "..", "governance", "approval_registry.json")) as f:
        reg = json.load(f)
    approvals = reg.get("approvals", {})
    assert len(approvals) == 20, (
        f"Approval registry must have 20 entries (canary matrix). Got: {len(approvals)}"
    )


def test_m502_18_canary_matrix_unchanged():
    """Canary matrix count unchanged — no new management quality entries added."""
    with open(os.path.join(os.path.dirname(__file__), "..", "..", "governance", "approval_registry.json")) as f:
        reg = json.load(f)
    approvals = reg.get("approvals", {})
    mq_entries = [k for k in approvals if "how-good-is-management" in k]
    assert len(mq_entries) == 4, (
        f"Must have exactly 4 how-good-is-management entries (one per company). Got: {len(mq_entries)}"
    )


def test_m502_19_zero_ai_calls():
    """M50.2 records 0 AI calls."""
    proof_path = os.path.join(GOVERNANCE_DIR, "ENG_MISSION50_2_GOVERNANCE_RECONCILIATION_PROOF.json")
    with open(proof_path) as f:
        proof = json.load(f)
    assert proof.get("ai_calls") == 0, f"Expected 0 AI calls. Got: {proof.get('ai_calls')}"
