"""
ENG-MISSION48 Tests: Contract V3, Fact Pack V2, Semantic Sections, Capability Registry,
Capability Parity Validator, Assembler V3, EIV V2

27 tests. 0 AI calls. 0 release mutations.

Test groups:
  V3-01..10: Contract V3 schema + Fact Pack V2 + Assembler V3
  EIV2-01..10: EIV V2 replay (M47, M45.2, all 4 trusted artifacts)
  FP48-01..04: Fact Pack V2 canonical data verification
  PARITY-01..03: Capability parity validator
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parents[2]

# ── Canonical digests (immutable governance anchors) ─────────────────────────
M378_SUNPHARMA_DIGEST = "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"
M47_CANDIDATE_DIGEST = "sha256:baf9c79f728a9024c1a24fac9de4ba9c0138596d61cb7325efaf2e95e4a39fe7"
M452_CANDIDATE_DIGEST = "sha256:79b6f4adf1b46fd705cef919ee51976f02d7ed7ed1a68a2ce54c38963cae798b"

SUNPHARMA_TRUSTED_PATH = ROOT / "companies/sun_pharma/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"
M47_CANDIDATE_PATH = ROOT / "companies/sun_pharma/company_memory/ask_intrinsiciq/regeneration_candidate_how_good_is_management_9d120267e32e.json"
M452_CANDIDATE_PATH = ROOT / "companies/sun_pharma/company_memory/ask_intrinsiciq/regeneration_candidate_how_good_is_management.json"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


# ── Module-scoped fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def fp_v2():
    import sys
    sys.path.insert(0, str(ROOT))
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    return build_management_quality_fact_pack_v2("sun_pharma")


@pytest.fixture(scope="module")
def assembled_answer(fp_v2):
    from intelligence.management_quality.assembler_v3 import assemble_management_answer_v3
    return assemble_management_answer_v3(fp_v2)


@pytest.fixture(scope="module")
def m47_candidate():
    return _load(M47_CANDIDATE_PATH)


@pytest.fixture(scope="module")
def m452_candidate():
    return _load(M452_CANDIDATE_PATH)


@pytest.fixture(scope="module")
def sunpharma_trusted():
    return _load(SUNPHARMA_TRUSTED_PATH)


# ── V3-01: Contract V3 schema exists and has correct version ─────────────────

def test_V3_01_contract_v3_schema_exists():
    schema_path = ROOT / "schemas" / "management_quality_answer_contract_v3.json"
    assert schema_path.exists(), "Contract V3 schema must exist"
    schema = _load(schema_path)
    assert schema["schema_version"] == 3
    assert schema["mission"] == "ENG-MISSION48"


def test_V3_02_contract_v3_promotes_all_five_sections_to_required():
    schema = _load(ROOT / "schemas" / "management_quality_answer_contract_v3.json")
    required_fields = schema.get("required_fields", {})
    v3_required_sections = [
        "what_evidence_shows",
        "what_management_says",
        "where_management_was_consistent",
        "management_consistency_map",
        "what_may_mean_economically",
    ]
    for section in v3_required_sections:
        assert section in required_fields, (
            f"{section} must be REQUIRED in Contract V3 "
            f"(was OPTIONAL in V2 — M47 regression root cause)"
        )
        assert required_fields[section].get("allowed_empty_state") is False, (
            f"{section} must not allow empty state in V3"
        )


def test_V3_03_fact_pack_v2_schema_version():
    from intelligence.management_quality.fact_pack_v2 import FACT_PACK_SCHEMA_VERSION
    assert FACT_PACK_SCHEMA_VERSION == "management_fact_pack.v2"


def test_V3_04_fact_pack_v2_has_hard_commitment_count(fp_v2):
    assert "hard_commitment_count" in fp_v2
    assert isinstance(fp_v2["hard_commitment_count"], int)
    # Sun Pharma has commitments with specific timeframes (MC-0031 H1CY24, MC-0039 By 2030, etc.)
    assert fp_v2["hard_commitment_count"] > 0, (
        "Sun Pharma has known hard commitments (Nidlegy EMA H1CY24, 35% carbon reduction by 2030)"
    )


def test_V3_05_fact_pack_v2_has_npm(fp_v2):
    assert fp_v2.get("npm") is not None
    assert isinstance(fp_v2["npm"], float)
    # Sun Pharma NPM should be approximately 19.6% (PAT/Revenue)
    assert 15.0 <= fp_v2["npm"] <= 25.0, f"NPM {fp_v2['npm']}% outside expected range for Sun Pharma"


def test_V3_06_fact_pack_v2_dpf_includes_hard_commitment_and_npm(fp_v2):
    dpfs = fp_v2.get("dpfs", [])
    # Commitment DPF must show hard count
    commit_dpf = next((d for d in dpfs if "commit" in d["metric"].lower()), None)
    assert commit_dpf is not None, "No commitment DPF in V2 DPFs"
    assert "hard" in commit_dpf["value"].lower(), (
        f"Commitment DPF must include hard count. Got: {commit_dpf['value']}"
    )
    # Financial DPF must include NPM
    fin_dpf = next((d for d in dpfs if "financial" in d["metric"].lower()), None)
    assert fin_dpf is not None, "No financial DPF in V2 DPFs"
    assert "NPM" in fin_dpf["value"], (
        f"Financial DPF must include NPM. Got: {fin_dpf['value']}"
    )


def test_V3_07_assembler_v3_preserves_all_deterministic_sections(assembled_answer):
    required_sections = [
        "what_evidence_shows",
        "what_management_says",
        "where_management_was_consistent",
        "management_consistency_map",
        "what_may_mean_economically",
        "what_is_not_yet_proven",
        "what_to_monitor",
        "behavioral_descriptor",
        "deterministic_precision_facts",
    ]
    for section in required_sections:
        val = assembled_answer.get(section)
        assert val is not None, f"Assembler V3 must preserve {section}"
        if isinstance(val, (list, dict)):
            assert len(val) > 0, f"{section} must not be empty"
        elif isinstance(val, str):
            assert len(val.strip()) > 10, f"{section} must not be trivially short"

    assert assembled_answer.get("_deterministic_sections_preserved") is True
    assert assembled_answer.get("_assembler_version") == "m48_assembler_v3"


def test_V3_08_assembler_v3_contains_behavioral_descriptor_in_simple_answer(assembled_answer):
    descriptor = assembled_answer.get("behavioral_descriptor", "")
    simple = assembled_answer.get("simple_answer", "")
    assert descriptor, "behavioral_descriptor must be set"
    assert descriptor in simple, (
        f"simple_answer must contain behavioral descriptor '{descriptor}'. "
        f"simple_answer starts: {simple[:100]}"
    )


def test_V3_09_capability_registry_defines_required_capabilities():
    from intelligence.management_quality.capability_registry import (
        REQUIRED_CAPABILITIES,
        CAPABILITY_REGISTRY_VERSION,
    )
    assert CAPABILITY_REGISTRY_VERSION == "management_capability_registry.v1"
    required_names = {
        "management.lifecycle_counts",
        "management.hard_commitment_detail",
        "management.evidence_observations",
        "management.management_statements",
        "management.consistency_analysis",
        "management.economic_context",
        "management.uncertainty",
        "management.monitoring",
        "management.dpfs",
        "management.behavioral_descriptor",
        "management.evidence_traceability",
    }
    assert required_names.issubset(set(REQUIRED_CAPABILITIES.keys())), (
        f"Missing capabilities: {required_names - set(REQUIRED_CAPABILITIES.keys())}"
    )


def test_V3_10_assembler_v3_what_evidence_shows_has_two_plus_entries(assembled_answer):
    wes = assembled_answer.get("what_evidence_shows", [])
    assert isinstance(wes, list), "what_evidence_shows must be a list"
    assert len(wes) >= 2, (
        f"what_evidence_shows must have >= 2 entries (Contract V3 requirement). Got: {len(wes)}"
    )


# ── EIV2 tests: EIV V2 replays ────────────────────────────────────────────────

def test_EIV2_01_m47_candidate_fails_eiv_v2_but_passed_eiv_v1(m47_candidate):
    """Core mission proof: M47 passed V1 but must fail V2."""
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    result = validate_management_answer_eiv_v2(m47_candidate)
    assert result["v1_result"]["overall"] == "PASS", "M47 must still pass EIV V1 (no regression)"
    assert result["overall"] == "FAIL", "M47 must FAIL EIV V2 (semantic capability regression detected)"


def test_EIV2_02_m47_candidate_eiv_v2_catches_five_absent_sections(m47_candidate):
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    result = validate_management_answer_eiv_v2(m47_candidate)
    assert "EIV-MQ-09" in result["v2_new_fails"], (
        "EIV-MQ-09 (Trusted Capability Parity) must fail for M47 — all 5 rich sections absent"
    )


def test_EIV2_03_m47_candidate_eiv_v2_catches_granularity_regression(m47_candidate):
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    result = validate_management_answer_eiv_v2(m47_candidate)
    assert "EIV-MQ-10" in result["v2_new_fails"], (
        "EIV-MQ-10 (Factual Granularity) must fail for M47 — '46 total; 46 unable to verify' pattern"
    )


def test_EIV2_04_m47_candidate_eiv_v2_catches_uncertainty_regression(m47_candidate):
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    result = validate_management_answer_eiv_v2(m47_candidate)
    assert "EIV-MQ-12" in result["v2_new_fails"], (
        "EIV-MQ-12 (Uncertainty Parity) must fail for M47 — generic abstract questions vs named specifics"
    )


def test_EIV2_05_m47_candidate_eiv_v2_semantic_regression_gate_fails(m47_candidate):
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    result = validate_management_answer_eiv_v2(m47_candidate)
    assert "EIV-MQ-16" in result["v2_new_fails"], (
        "EIV-MQ-16 (Semantic Regression Gate) must fail for M47 — >= 2 HIGH severity capabilities absent"
    )
    assert len(result["high_severity_fails"]) >= 2, (
        f"M47 must have >= 2 HIGH severity fails to trigger gate. Got: {result['high_severity_fails']}"
    )


def test_EIV2_06_sunpharma_m378_passes_eiv_v2(sunpharma_trusted):
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    ans = sunpharma_trusted["answers"]["how-good-is-management"]
    result = validate_management_answer_eiv_v2(ans)
    assert result["overall"] == "PASS", (
        f"Sun Pharma M37.8 must PASS EIV V2. Fails: {result['fails']}"
    )


def test_EIV2_07_datapatterns_m378_passes_eiv_v2():
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    d = _load(ROOT / "companies/datapatterns/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json")
    ans = d["answers"]["how-good-is-management"]
    result = validate_management_answer_eiv_v2(ans)
    assert result["overall"] == "PASS", f"DataPatterns M37.8 must PASS EIV V2. Fails: {result['fails']}"


def test_EIV2_08_tanla_m378_passes_eiv_v2():
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    d = _load(ROOT / "companies/tanla/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json")
    ans = d["answers"]["how-good-is-management"]
    result = validate_management_answer_eiv_v2(ans)
    assert result["overall"] == "PASS", f"Tanla M37.8 must PASS EIV V2. Fails: {result['fails']}"


def test_EIV2_09_ujjivan_m378_passes_eiv_v2():
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    d = _load(ROOT / "companies/ujjivan/company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json")
    ans = d["answers"]["how-good-is-management"]
    result = validate_management_answer_eiv_v2(ans)
    assert result["overall"] == "PASS", f"Ujjivan M37.8 must PASS EIV V2. Fails: {result['fails']}"


def test_EIV2_10_m452_candidate_fails_eiv_v2():
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    m452 = _load(M452_CANDIDATE_PATH)
    result = validate_management_answer_eiv_v2(m452)
    assert result["overall"] == "FAIL", "M45.2 candidate must FAIL EIV V2"
    # M45.2 also fails V1
    assert result["v1_result"]["overall"] == "FAIL", "M45.2 must also fail EIV V1"


# ── FP48: Fact Pack V2 canonical data verification ────────────────────────────

def test_FP48_01_fact_pack_v2_hard_commitments_are_from_canonical_data(fp_v2):
    hc_list = fp_v2.get("hard_commitments", [])
    assert len(hc_list) > 0
    for hc in hc_list:
        assert "id" in hc and hc["id"].startswith("MC-"), f"Hard commitment must have MC-* ID: {hc}"
        assert "expected_timeframe" in hc, f"Hard commitment must have timeframe: {hc}"
        # Must not be "unspecified" or "ongoing"
        tf = hc["expected_timeframe"].lower()
        assert "unspecified" not in tf and "ongoing" not in tf, (
            f"Hard commitment must have specific timeframe, not: {tf}"
        )


def test_FP48_02_fact_pack_v2_includes_known_hard_commitments(fp_v2):
    """Nidlegy EMA H1CY24 and 35% carbon reduction by 2030 must be in hard commitments."""
    hc_ids = [hc["id"] for hc in fp_v2.get("hard_commitments", [])]
    assert "MC-0031" in hc_ids, "MC-0031 (Nidlegy EMA H1CY24) must be a hard commitment"
    assert "MC-0039" in hc_ids, "MC-0039 (35% carbon reduction by 2030) must be a hard commitment"


def test_FP48_03_fact_pack_v2_npm_matches_canonical_financial_data(fp_v2):
    """NPM must equal PAT/Revenue from canonical financial_truth_pack."""
    npm = fp_v2.get("npm")
    fin = fp_v2.get("financial_context", {})
    rev_val = fin.get("revenue", {}).get("value")
    pat_val = fin.get("pat", {}).get("value")
    if rev_val and pat_val:
        expected_npm = round((float(pat_val) / float(rev_val)) * 100, 1)
        assert abs(npm - expected_npm) < 0.2, (
            f"NPM {npm}% does not match canonical PAT/Revenue = {expected_npm}%"
        )


def test_FP48_04_fact_pack_v2_consistency_map_has_dimensions(fp_v2):
    cmap = fp_v2.get("consistency_map", {})
    assert len(cmap) >= 3, (
        f"consistency_map must have >= 3 dimension entries. Got: {list(cmap.keys())}"
    )
    # All known Sun Pharma dimensions should be present
    assert "execution_discipline" in cmap
    assert "capital_allocation_discipline" in cmap


# ── PARITY tests: Capability Parity Validator ─────────────────────────────────

def test_PARITY_01_m47_candidate_fails_capability_parity(m47_candidate):
    from intelligence.management_quality.capability_parity_validator import (
        validate_management_semantic_capability_parity,
    )
    result = validate_management_semantic_capability_parity(m47_candidate)
    assert result["overall"] == "FAIL", (
        f"M47 candidate must FAIL capability parity. "
        f"High fails: {result['high_severity_fails']}"
    )
    # Must have HIGH severity failures for the 5 absent sections
    assert len(result["high_severity_fails"]) >= 2, (
        f"M47 must have >= 2 HIGH severity capability failures. Got: {result['high_severity_fails']}"
    )


def test_PARITY_02_sunpharma_m378_passes_capability_parity(sunpharma_trusted):
    from intelligence.management_quality.capability_parity_validator import (
        validate_management_semantic_capability_parity,
    )
    ans = sunpharma_trusted["answers"]["how-good-is-management"]
    result = validate_management_semantic_capability_parity(ans)
    assert result["overall"] == "PASS", (
        f"Sun Pharma M37.8 must PASS capability parity. Fails: "
        f"{[r['capability'] + ': ' + r['reason'][:60] for r in result['capability_results'] if r['result'] != 'PASS']}"
    )


def test_PARITY_03_capability_parity_detects_factual_granularity_regression(m47_candidate):
    """Specifically: M47's '46 total; 46 unable to verify' must trigger FACTUAL_GRANULARITY_REGRESSION."""
    from intelligence.management_quality.capability_parity_validator import (
        validate_management_semantic_capability_parity,
    )
    result = validate_management_semantic_capability_parity(m47_candidate)
    cap_results = {r["capability"]: r for r in result["capability_results"]}
    hcd = cap_results.get("management.hard_commitment_detail", {})
    assert hcd.get("result") == "FAIL", "management.hard_commitment_detail must FAIL for M47"
    assert "FACTUAL_GRANULARITY_REGRESSION" in hcd.get("reason", ""), (
        f"Must specifically identify FACTUAL_GRANULARITY_REGRESSION. Got: {hcd.get('reason','')[:120]}"
    )


# ── Governance integrity: certified artifacts unchanged ───────────────────────

def test_EIV2_GOVERNANCE_01_m47_candidate_digest_unchanged():
    assert _sha256(M47_CANDIDATE_PATH) == M47_CANDIDATE_DIGEST, (
        "M47 candidate digest changed — candidate file must not be mutated"
    )


def test_EIV2_GOVERNANCE_02_m378_certified_artifact_unchanged():
    assert _sha256(SUNPHARMA_TRUSTED_PATH) == M378_SUNPHARMA_DIGEST, (
        "M37.8 certified artifact digest changed — certified artifact must never be mutated"
    )


def test_EIV2_GOVERNANCE_03_m47_rejected_candidate_not_in_approval_registry():
    registry_path = ROOT / "governance" / "approval_registry.json"
    registry = _load(registry_path)
    # Approval records live under the 'approvals' key
    approvals = registry.get("approvals", registry) if isinstance(registry.get("approvals"), dict) else registry
    for key, entry in approvals.items():
        if not isinstance(entry, dict):
            continue
        assert entry.get("full_artifact_digest") != M47_CANDIDATE_DIGEST.replace("sha256:", ""), (
            f"M47 candidate (REJECTED) must not appear in approval registry. Found in: {key}"
        )


def test_EIV2_GOVERNANCE_04_m47_human_decision_is_reject():
    review_path = ROOT / "governance" / "ENG_MISSION47_INVESTOR_GRADE_REGENERATION_HUMAN_REVIEW.json"
    review = _load(review_path)
    m471 = review.get("m47_1_exact_artifact_review", {})
    assert m471.get("human_decision") == "REJECT", (
        f"M47 human_decision must be REJECT (recorded by M48). Got: {m471.get('human_decision')}"
    )
    assert review.get("status") == "HUMAN_DECISION_REJECT"


def test_EIV2_GOVERNANCE_05_m47_rejected_candidate_preserved():
    """Rejected candidate file must still exist (never deleted)."""
    assert M47_CANDIDATE_PATH.exists(), (
        "M47 candidate file must be preserved permanently as regression evidence. "
        "Rejected candidates are never deleted."
    )
    assert _sha256(M47_CANDIDATE_PATH) == M47_CANDIDATE_DIGEST
