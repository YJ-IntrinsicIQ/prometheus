"""
M50.1 Closure Verification — 24 tests (M501-01 through M501-24)

Covers:
- Hard commitment forensics (canonical M50.1 policy)
- Cross-company section quality replay (4 companies)
- M49 defect matrix structural impossibility (D1, D2)
- Rejected-candidate replays: M49, M47, M45.2 all FAIL EIV V2
- M37.8 trusted artifact PASS
- Contract V4 fingerprint stability
- M50.1 verifiable-content year-exclusion fix
"""
import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from intelligence.management_quality.fact_pack_v2 import (
    build_management_quality_fact_pack_v2,
    _is_hard_commitment,
)
from intelligence.management_quality.investor_sections import (
    build_investor_sections,
    _is_internal_label,
)
from intelligence.management_quality.assembler_v4 import (
    assemble_management_answer_v4,
    LLM_SECTION_OVERRIDE_BLOCKED,
    _temporal_check_passes,
)
from intelligence.management_quality.rating_quarantine import (
    scan_answer_for_rating_violations,
)
from intelligence.management_quality.contract_manifest import (
    CONTRACT_V4_POLICY_DIGEST,
    compute_contract_v4_fingerprint,
)
from intelligence.external_investor_value_validator_v2 import (
    validate_management_answer_eiv_v2,
)

COMPANY_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "companies", "sun_pharma", "company_memory", "ask_intrinsiciq",
)
SHADOW_ARTIFACT = os.path.join(COMPANY_DIR, "shadow_level3_hybrid_answers.json")
M49_CANDIDATE = os.path.join(COMPANY_DIR, "regeneration_candidate_how_good_is_management_041d464fe52e.json")
M47_CANDIDATE = os.path.join(COMPANY_DIR, "regeneration_candidate_how_good_is_management_9d120267e32e.json")
M45_CANDIDATE = os.path.join(COMPANY_DIR, "regeneration_candidate_how_good_is_management.json")


# ── Hard commitment forensics ─────────────────────────────────────────────────

def test_m501_01_mc0029_is_hard():
    """MC-0029: co-process 30% hazardous waste by 2025 → HARD (quantified + specific date)."""
    item = {
        "commitment_id": "MC-0029",
        "expected_timeframe": "By 2025",
        "normalized_commitment": "Co process 30 of hazardous waste.",
    }
    assert _is_hard_commitment(item) is True


def test_m501_02_mc0039_is_hard():
    """MC-0039: 35% Scope 1+2 carbon reduction by 2030 → HARD."""
    item = {
        "commitment_id": "MC-0039",
        "expected_timeframe": "By 2030",
        "normalized_commitment": (
            "Achieve a 35 reduction in absolute scope 1 and scope 2 carbon emissions "
            "compared to the baseline year of 2020."
        ),
    }
    assert _is_hard_commitment(item) is True


def test_m501_03_mc0031_is_hard():
    """MC-0031: file Nidlegy with EMA by H1CY24 → HARD (regulatory filing + specific date)."""
    item = {
        "commitment_id": "MC-0031",
        "expected_timeframe": "H1CY24",
        "normalized_commitment": (
            "File nidlegy with the european medicines agency for locally developed biosimilar."
        ),
    }
    assert _is_hard_commitment(item) is True


def test_m501_04_mc0012_not_hard():
    """MC-0012: 'build a strong pipeline' → NOT HARD (aspirational, unmeasurable)."""
    item = {
        "commitment_id": "MC-0012",
        "expected_timeframe": "in fy21",
        "normalized_commitment": "Build a strong pipeline in generic products to enter the us market.",
    }
    assert _is_hard_commitment(item) is False


def test_m501_05_mc0023_not_hard():
    """MC-0023: 'company is increasing focus' → NOT HARD (aspirational/retrospective observation)."""
    item = {
        "commitment_id": "MC-0023",
        "expected_timeframe": "in fy18",
        "normalized_commitment": "The company is increasing focus on expanding taro operations.",
    }
    assert _is_hard_commitment(item) is False


def test_m501_06_sun_pharma_canonical_count_3():
    """Sun Pharma canonical hard commitment count = 3 (M50.1 policy)."""
    fp = build_management_quality_fact_pack_v2("sun_pharma")
    hard = fp.get("hard_commitments", [])
    assert len(hard) == 3, f"Expected 3, got {len(hard)}: {[h.get('expected_timeframe') for h in hard]}"


def test_m501_07_data_patterns_canonical_count_0():
    """Data Patterns hard commitment count = 0."""
    fp = build_management_quality_fact_pack_v2("data_patterns")
    assert fp.get("hard_commitment_count", -1) == 0


def test_m501_08_tanla_canonical_count_0():
    """Tanla hard commitment count = 0 (MC-0019 year-as-target false positive fixed)."""
    fp = build_management_quality_fact_pack_v2("tanla")
    assert fp.get("hard_commitment_count", -1) == 0


def test_m501_09_ujjivan_canonical_count_0():
    """Ujjivan hard commitment count = 0."""
    fp = build_management_quality_fact_pack_v2("ujjivan")
    assert fp.get("hard_commitment_count", -1) == 0


# ── Cross-company section quality ────────────────────────────────────────────

def test_m501_10_sun_pharma_sections_llm_blocked():
    """Sun Pharma investor sections: _llm_section_override_blocked = True."""
    fp = build_management_quality_fact_pack_v2("sun_pharma")
    sections = build_investor_sections(fp)
    assert sections.get("_llm_section_override_blocked") is True


def test_m501_11_sun_pharma_no_internal_label_leaks():
    """Sun Pharma sections: what_to_monitor contains no raw internal field names."""
    fp = build_management_quality_fact_pack_v2("sun_pharma")
    sections = build_investor_sections(fp)
    for item in sections.get("what_to_monitor", []):
        assert not _is_internal_label(str(item)), f"Internal label leak: {item}"


def test_m501_12_sun_pharma_no_rating_violations():
    """Sun Pharma sections: no rating language violations in investor-facing fields."""
    fp = build_management_quality_fact_pack_v2("sun_pharma")
    sections = build_investor_sections(fp)
    answer = {
        "what_evidence_shows": sections.get("what_evidence_shows", []),
        "what_management_says": sections.get("what_management_says", []),
        "what_to_monitor": sections.get("what_to_monitor", []),
    }
    violations = scan_answer_for_rating_violations(answer)
    assert violations == [], f"Rating violations: {violations}"


def test_m501_13_data_patterns_sparse_safety():
    """Data Patterns (sparse evidence): sections empty without crash, LLM block still set."""
    fp = build_management_quality_fact_pack_v2("data_patterns")
    sections = build_investor_sections(fp)
    assert sections.get("_llm_section_override_blocked") is True
    assert sections.get("what_evidence_shows", []) == []
    assert sections.get("what_management_says", []) == []
    assert sections.get("what_to_monitor", []) == []


def test_m501_14_tanla_sections_have_evidence():
    """Tanla sections: what_evidence_shows has >= 1 item (non-sparse company)."""
    fp = build_management_quality_fact_pack_v2("tanla")
    sections = build_investor_sections(fp)
    assert len(sections.get("what_evidence_shows", [])) >= 1


def test_m501_15_ujjivan_sections_llm_blocked():
    """Ujjivan investor sections: _llm_section_override_blocked = True."""
    fp = build_management_quality_fact_pack_v2("ujjivan")
    sections = build_investor_sections(fp)
    assert sections.get("_llm_section_override_blocked") is True


# ── Rejected candidate replays ───────────────────────────────────────────────

def test_m501_16_m49_candidate_fails_eiv_mq18():
    """M49 rejected candidate → EIV V2 FAIL with EIV-MQ-18 HIGH (Industry_outlook label leak)."""
    with open(M49_CANDIDATE) as f:
        candidate = json.load(f)
    answer = candidate.get("answer", candidate)
    result = validate_management_answer_eiv_v2(answer)
    assert result["overall"] == "FAIL"
    assert "EIV-MQ-18" in result["fails"], f"Expected EIV-MQ-18 in fails: {result['fails']}"
    assert "EIV-MQ-18" in result.get("high_severity_fails", [])


def test_m501_17_m49_candidate_fails_eiv_mq19():
    """M49 rejected candidate → EIV V2 FAIL with EIV-MQ-19 HIGH (temporal mismatch)."""
    with open(M49_CANDIDATE) as f:
        candidate = json.load(f)
    answer = candidate.get("answer", candidate)
    result = validate_management_answer_eiv_v2(answer)
    assert result["overall"] == "FAIL"
    assert "EIV-MQ-19" in result["fails"], f"Expected EIV-MQ-19 in fails: {result['fails']}"
    assert "EIV-MQ-19" in result.get("high_severity_fails", [])


def test_m501_18_m47_candidate_fails_structural_regression():
    """M47 rejected candidate → EIV V2 FAIL with structural regression (EIV-MQ-09 HIGH)."""
    with open(M47_CANDIDATE) as f:
        candidate = json.load(f)
    answer = candidate.get("answer", candidate)
    result = validate_management_answer_eiv_v2(answer)
    assert result["overall"] == "FAIL"
    assert "EIV-MQ-09" in result.get("high_severity_fails", []), (
        f"Expected structural regression EIV-MQ-09: {result['fails']}"
    )


def test_m501_19_m45_2_candidate_fails_structural_regression():
    """M45.2 rejected candidate → EIV V2 FAIL with structural regression (EIV-MQ-09 HIGH)."""
    with open(M45_CANDIDATE) as f:
        candidate = json.load(f)
    answer = candidate.get("answer", candidate)
    result = validate_management_answer_eiv_v2(answer)
    assert result["overall"] == "FAIL"
    assert "EIV-MQ-09" in result.get("high_severity_fails", []), (
        f"Expected structural regression EIV-MQ-09: {result['fails']}"
    )


def test_m501_20_m37_8_trusted_artifact_passes():
    """M37.8 trusted artifact → EIV V2 PASS (reference standard preserved)."""
    with open(SHADOW_ARTIFACT) as f:
        artifact = json.load(f)
    answers = artifact.get("answers", artifact)
    mq_answer = answers.get("how-good-is-management", {}).get("answer", {})
    result = validate_management_answer_eiv_v2(mq_answer)
    assert result["overall"] == "PASS", f"M37.8 should PASS EIV V2: {result['fails']}"


# ── M49 defect matrix structural impossibility ───────────────────────────────

def test_m501_21_defect_d1_industry_outlook_structurally_impossible():
    """D1 (Industry_outlook): assembler_v4 always uses deterministic sections — raw internal labels
    cannot appear in what_to_monitor produced by investor_sections."""
    fp = build_management_quality_fact_pack_v2("sun_pharma")
    fake_llm = {
        "simple_answer": "Sun Pharma has strong management.",
        "what_to_monitor": ["Industry_outlook", "Some other metric"],
    }
    answer = assemble_management_answer_v4(fp, llm_prose=fake_llm)
    for item in answer.get("what_to_monitor", []):
        assert "Industry_outlook" not in str(item), (
            f"D1 defect reproduced in assembler_v4 — structural invariant broken: {item}"
        )


def test_m501_22_defect_d2_temporal_mismatch_structurally_impossible():
    """D2 (confirmed data called projected): assembler_v4 temporal gate blocks the LLM text
    when confirmed financial data (revenue) is present but LLM says 'projected'."""
    fp = build_management_quality_fact_pack_v2("sun_pharma")
    # Patch confirmed revenue into fp
    fp_patched = dict(fp)
    fp_patched["financial_context"] = {"revenue": {"value": 50102, "fy": "FY26", "status": "ACTUAL"}}
    fake_llm = {
        "simple_answer": "Management driving projected revenue of ₹50,102 cr for FY26.",
        "what_may_mean_economically": "Projected revenue ₹50,102 cr suggests strong growth.",
    }
    answer = assemble_management_answer_v4(fp_patched, llm_prose=fake_llm)
    # simple_answer must not use the LLM text since temporal check fails
    assert "projected" not in answer.get("simple_answer", "").lower() or \
           answer.get("simple_answer", "") != fake_llm["simple_answer"], (
        "D2 defect reproduced: confirmed data rendered as projected"
    )
    # wmme must be deterministic (not from LLM with temporal error)
    wmme = answer.get("what_may_mean_economically", "")
    assert "Projected revenue ₹50,102 cr suggests" not in wmme, (
        "D2 defect reproduced in what_may_mean_economically"
    )


# ── Contract V4 fingerprint stability ────────────────────────────────────────

def test_m501_23_contract_v4_fingerprint_stable_after_m501():
    """Contract V4 fingerprint is stable (same value) across 3 re-computations after M50.1."""
    fp1 = compute_contract_v4_fingerprint()
    fp2 = compute_contract_v4_fingerprint()
    fp3 = compute_contract_v4_fingerprint()
    assert fp1 == fp2 == fp3, "Contract V4 fingerprint not deterministic"
    assert fp1 == CONTRACT_V4_POLICY_DIGEST, (
        f"Stored fingerprint stale: stored={CONTRACT_V4_POLICY_DIGEST}, computed={fp1}"
    )


def test_m501_24_year_as_target_exclusion():
    """M50.1 fix: 4-digit year in content text must NOT be treated as a verifiable target number."""
    # MC-0019 tanla pattern: "achieve...by 2025" — 2025 is a deadline year, not a target
    item_year_as_target = {
        "commitment_id": "TEST-YEAR",
        "expected_timeframe": "by 2025",
        "normalized_commitment": (
            "Enhance employee experience and achieve an improvement in employee "
            "satisfaction score by 2025"
        ),
    }
    assert _is_hard_commitment(item_year_as_target) is False, (
        "Year 2025 in commitment text must NOT be treated as verifiable target number"
    )

    # MC-0039 pattern: "achieve a 35 reduction" — 35 is a real target (2-digit)
    item_real_target = {
        "commitment_id": "TEST-REAL",
        "expected_timeframe": "By 2030",
        "normalized_commitment": (
            "Achieve a 35 reduction in absolute scope 1 and scope 2 carbon emissions."
        ),
    }
    assert _is_hard_commitment(item_real_target) is True, (
        "Two-digit target number should still qualify as verifiable content"
    )
