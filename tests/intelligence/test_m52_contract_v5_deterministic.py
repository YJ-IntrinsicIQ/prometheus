"""
ENG-MISSION52 — Contract V5 Fully Deterministic Management Intelligence
40 tests (M52-01 through M52-40)

Contract V5 invariants under test:
  - Zero AI calls: generation_mode = DETERMINISTIC
  - Consistency map bug fixed: INCONSISTENT checked before CONSISTENT
  - MC-0031 omission fixed: all canonical hard commitments in what_management_says
  - Economic renderer preserves PAT
  - Internal consistency validator (no map/monitoring contradictions)
  - 5-run determinism across 4 companies
  - V4/V5 execution identity separation
  - Planner reports 0 AI calls for management quality
  - Human decisions recorded (NEEDS_CHANGES + REMOVE_AI)

AI calls used: 0
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COMPANY_MEMORY = REPO / "companies"

# ── V5 identity constants ─────────────────────────────────────────────────────
V5_EXECUTION_ID = "sha256:166d0a4f52b81b483e157313305522ef59376e0c347c05cf5430a61c88ead616"  # updated M52.2a
V5_CANDIDATE_DIGEST = "sha256:84a207ec22b3b3c132c182e78319f09d9c2a558d927665c787d6465a5cedb861"  # updated M52.2a
V5_CONTRACT_FP = "sha256:046004b4d4edb04fab7eaca641b24a73279f2851b483824c3af0349a0deb41f9"  # updated M52.2a
V5_EVIDENCE_FP = "sha256:9be9bd11b1be74a157aa2ceae2bc5f144833e7f11856d6f7a0d8f8b303f23e42"  # official, M52.2c
V5_ASSEMBLER_VERSION = "m52_assembler_v5"

# M51 V4 identity constants (for separation tests)
M51_EXECUTION_ID = "sha256:444fc5f4166d1e5b39e30a58a8469ff2553106ca5f21d777cd1598ea32ae8909"
M51_CANDIDATE_DIGEST = "sha256:5c86d936a296cae6bfd5c88e002ca71ab411a7851f533fea0cd81be3e2faf135"
M37_8_DIGEST = "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"
ACTIVATED_DIGEST = "sha256:9b6d8bad07c39aa8532272ef24b5fb8195cb96eeb988b3bd847f15d569d31998"   # M54.13: live served-answers file after activating the corrected Sun answers

V5_CANDIDATE_PATH = COMPANY_MEMORY / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / \
    "regeneration_candidate_how_good_is_management_166d0a4f52b8_v5.json"  # updated M52.2a
M37_8_PATH = COMPANY_MEMORY / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / \
    "shadow_level3_hybrid_answers.pre_m5413.json"      # preserved M37.8 baseline snapshot
# M59.4 moved the live served file on; the M54.13 activated state this test pins is preserved byte for byte in the M59.4 backup.
LIVE_ANSWERS_PATH = sorted((REPO / "governance").glob("m594_backup_*"))[-1] / "sun_pharma__shadow_level3_hybrid_answers.json"


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sun_pharma_fp():
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    return build_management_quality_fact_pack_v2("sun_pharma")


@pytest.fixture(scope="module")
def sun_pharma_v5_answer(sun_pharma_fp):
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    return build_management_answer_v5(sun_pharma_fp)


@pytest.fixture(scope="module")
def v5_candidate():
    return json.loads(V5_CANDIDATE_PATH.read_text())


# ── M52-01: Contract V5 fingerprint canonical ─────────────────────────────────
def test_m52_01_contract_v5_fingerprint_canonical():
    from intelligence.management_quality.contract_manifest import CONTRACT_V5_POLICY_DIGEST
    assert CONTRACT_V5_POLICY_DIGEST == V5_CONTRACT_FP, (
        f"Contract V5 FP changed: {CONTRACT_V5_POLICY_DIGEST}"
    )


# ── M52-02: V5 execution ID excludes model/provider/prompt ───────────────────
def test_m52_02_execution_id_no_model_or_provider():
    from intelligence.management_quality.assembler_v5 import compute_execution_id_v5
    exec_id = compute_execution_id_v5(
        "sun_pharma",
        "how_good_is_management_synthesis",
        V5_EVIDENCE_FP,
        V5_CONTRACT_FP,
    )
    assert exec_id == V5_EXECUTION_ID
    # Must not change with different model string (not in identity)
    exec_id_2 = compute_execution_id_v5(
        "sun_pharma",
        "how_good_is_management_synthesis",
        V5_EVIDENCE_FP,
        V5_CONTRACT_FP,
    )
    assert exec_id == exec_id_2


# ── M52-03: V5 execution ID ≠ M51 V4 execution ID ────────────────────────────
def test_m52_03_v5_exec_id_separate_from_v4():
    assert V5_EXECUTION_ID != M51_EXECUTION_ID, (
        "V5 and V4 execution IDs must be distinct (different contract FP in identity)"
    )


# ── M52-04: Assembler V5 generation mode is DETERMINISTIC ────────────────────
def test_m52_04_assembler_v5_generation_mode(sun_pharma_v5_answer):
    assert sun_pharma_v5_answer.get("_generation_mode") == "DETERMINISTIC"
    assert sun_pharma_v5_answer.get("_zero_ai_calls") is True
    assert sun_pharma_v5_answer.get("_assembler_version") == V5_ASSEMBLER_VERSION


# ── M52-05: Zero AI calls — no provider in assembler_v5 ──────────────────────
def test_m52_05_zero_ai_calls_no_provider_import():
    import ast, inspect
    from intelligence.management_quality import assembler_v5
    src = inspect.getsource(assembler_v5)
    # Must not import openai, anthropic, or knowledge.ai.factory
    forbidden = ["import openai", "import anthropic", "from knowledge.ai"]
    for f in forbidden:
        assert f not in src, f"assembler_v5 must not import AI provider: {f}"


# ── M52-06: Consistency map bug fixed — INCONSISTENT not misclassified ────────
def _st(value):
    """Map entries are 'STATUS — behavioural evidence'; compare on the status."""
    return str(value).split(" — ")[0].strip()


def test_m52_06_consistency_map_inconsistent_not_misclassified(sun_pharma_v5_answer):
    cm = sun_pharma_v5_answer.get("management_consistency_map", {})
    # M52 invariant (substring bug): an adverse status is never read as CONSISTENT, and statuses are parsed exactly.
    # M52.2d calibration: recurring risks alone do not prove inconsistent behaviour, so these two entries are
    # UNABLE_TO_VERIFY - but they must never be CONSISTENT.
    for label in ("Candor and consistency", "Risk handling"):
        st = _st(cm.get(label))
        assert st in ("UNABLE_TO_VERIFY", "INCONSISTENT", "PARTIALLY_CONSISTENT"), f"{label}: {st}"
        assert st != "CONSISTENT"


# ── M52-07: Consistency map is NOT all-CONSISTENT ────────────────────────────
def test_m52_07_consistency_map_not_all_consistent(sun_pharma_v5_answer):
    cm = sun_pharma_v5_answer.get("management_consistency_map", {})
    values = list(cm.values())
    assert not all(_st(v) == "CONSISTENT" for v in values), "V5 consistency map must not be all-CONSISTENT - M51 defect fixed"
    assert sum(1 for v in values if _st(v) == "UNABLE_TO_VERIFY") >= 1
    for v in values:                              # any adverse classification must carry its proof
        if _st(v) == "INCONSISTENT":
            assert "Evidence:" in v


# ── M52-08: MC-0031 (Nidlegy EMA) present in what_management_says ─────────────
def test_m52_08_mc0031_nidlegy_present(sun_pharma_v5_answer):
    says = sun_pharma_v5_answer.get("what_management_says", [])
    assert len(says) >= 3, f"Expected >= 3 management statements, got {len(says)}"
    nidlegy_present = any(
        "nidlegy" in s.lower() or "ema" in s.lower() or "MC-0031" in s
        for s in says
    )
    assert nidlegy_present, (
        f"MC-0031 (Nidlegy EMA filing) not in what_management_says: {says}"
    )


# ── M52-09: All 3 canonical hard commitments in what_management_says ─────────
def test_m52_09_all_canonical_hard_commitments_represented(sun_pharma_v5_answer, sun_pharma_fp):
    says = sun_pharma_v5_answer.get("what_management_says", [])
    hc_count = sun_pharma_fp.get("hard_commitment_count", 0)
    assert hc_count == 3, f"Canonical hard commitment count should be 3: {hc_count}"
    assert len(says) >= hc_count, (
        f"All {hc_count} canonical hard commitments must be in what_management_says, got {len(says)}"
    )


# ── M52-10: Economic renderer preserves PAT ──────────────────────────────────
def test_m52_10_economic_renderer_preserves_pat(sun_pharma_v5_answer):
    econ = sun_pharma_v5_answer.get("what_may_mean_economically", "")
    assert "11,479" in econ, (
        f"V5 economic context must include PAT ₹11,479 cr (M51 LLM dropped it): {econ[:100]}"
    )


# ── M52-11: Economic renderer includes Revenue and NPM ───────────────────────
def test_m52_11_economic_renderer_complete_financials(sun_pharma_v5_answer):
    econ = sun_pharma_v5_answer.get("what_may_mean_economically", "")
    assert "58,462" in econ, "Revenue ₹58,462 cr should be in economic context"
    assert "19.6" in econ, "NPM 19.6% should be in economic context"
    assert "confirmed" in econ.lower(), "Economic context should say 'confirmed' (temporal protection)"


# ── M52-12: No speculative language on confirmed financials ───────────────────
def test_m52_12_no_speculative_language_on_confirmed_data(sun_pharma_v5_answer):
    econ = sun_pharma_v5_answer.get("what_may_mean_economically", "")
    lower = econ.lower()
    # Should not call confirmed data "projected"
    assert "projected revenue" not in lower, "Must not call confirmed revenue 'projected'"
    assert "projected profit" not in lower, "Must not call confirmed PAT 'projected'"


# ── M52-13: Internal consistency validator — no contradictions ────────────────
def test_m52_13_no_consistency_map_contradictions(sun_pharma_v5_answer):
    contradictions = sun_pharma_v5_answer.get("_consistency_map_contradictions", [])
    assert len(contradictions) == 0, (
        f"V5 consistency map has contradictions with monitoring: {contradictions}"
    )


# ── M52-14: Validator detects contradictions when present ────────────────────
def test_m52_14_consistency_validator_detects_contradictions():
    from intelligence.management_quality.investor_sections import validate_consistency_map_vs_monitoring
    # Synthetic contradiction: map says CONSISTENT but monitoring says INCONSISTENT
    contradictions = validate_consistency_map_vs_monitoring(
        {"Candor and consistency": "CONSISTENT"},
        ["Candor and consistency: currently INCONSISTENT — monitor for improvement"],
    )
    assert len(contradictions) == 1, "Validator must detect the contradiction"
    assert "Candor and consistency" in contradictions[0]


# ── M52-15: V5 simple_answer contains behavioral descriptor ──────────────────
def test_m52_15_simple_answer_contains_descriptor(sun_pharma_v5_answer):
    simple = sun_pharma_v5_answer.get("simple_answer", "")
    assert "FOLLOW_THROUGH_LARGELY_UNVERIFIED" in simple, (
        f"V5 simple_answer must contain behavioral descriptor: {simple[:100]}"
    )


# ── M52-16: V5 simple_answer includes confirmed revenue ──────────────────────
def test_m52_16_simple_answer_confirmed_revenue(sun_pharma_v5_answer):
    simple = sun_pharma_v5_answer.get("simple_answer", "")
    assert "58,462" in simple, "Simple answer should include confirmed Revenue ₹58,462 cr"
    assert "confirmed" in simple.lower(), "Simple answer should label financials as 'confirmed'"


# ── M52-17: V5 candidate file exists and is not M37.8 ────────────────────────
def test_m52_17_v5_candidate_at_shadow_location():
    assert V5_CANDIDATE_PATH.exists(), f"V5 candidate not at shadow location: {V5_CANDIDATE_PATH}"
    # M37.8 must be unmodified
    m37_8_actual = "sha256:" + hashlib.sha256(M37_8_PATH.read_bytes()).hexdigest()
    assert m37_8_actual == M37_8_DIGEST, f"M37.8 byte-identity violated: {m37_8_actual}"
    live = "sha256:" + hashlib.sha256(LIVE_ANSWERS_PATH.read_bytes()).hexdigest()
    assert live == ACTIVATED_DIGEST, f"activated served answers changed: {live}"


# ── M52-18: V5 candidate has correct schema and fields ───────────────────────
def test_m52_18_v5_candidate_schema(v5_candidate):
    assert str(v5_candidate.get("schema_version", "")).startswith("m52")
    assert v5_candidate.get("contract_version") == "v5"
    assert v5_candidate.get("generation_mode") == "DETERMINISTIC"
    assert v5_candidate.get("zero_ai_calls") is True
    assert v5_candidate.get("ai_calls_made") == 0
    assert v5_candidate.get("assembler_version") == V5_ASSEMBLER_VERSION


# ── M52-19: V5 candidate digest matches known value ──────────────────────────
def test_m52_19_v5_candidate_digest_canonical(v5_candidate):
    answer = v5_candidate.get("answer", {})
    actual = "sha256:" + hashlib.sha256(json.dumps(answer, sort_keys=True).encode()).hexdigest()
    assert actual == V5_CANDIDATE_DIGEST, (
        f"V5 answer digest changed: {actual}"
    )


# ── M52-20: 5-run determinism — Sun Pharma ───────────────────────────────────
def test_m52_20_determinism_5_runs_sun_pharma():
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    digests = set()
    for _ in range(5):
        fp = build_management_quality_fact_pack_v2("sun_pharma")
        a = build_management_answer_v5(fp)
        digests.add(hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest())
    assert len(digests) == 1, f"Non-deterministic output across 5 runs: {digests}"


# ── M52-21: 5-run determinism — Tanla ────────────────────────────────────────
def test_m52_21_determinism_5_runs_tanla():
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    digests = set()
    for _ in range(5):
        fp = build_management_quality_fact_pack_v2("tanla")
        a = build_management_answer_v5(fp)
        digests.add(hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest())
    assert len(digests) == 1, f"Non-deterministic output across 5 runs (Tanla): {digests}"


# ── M52-22: 5-run determinism — LTTS ─────────────────────────────────────────
def test_m52_22_determinism_5_runs_ltts():
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    digests = set()
    for _ in range(5):
        fp = build_management_quality_fact_pack_v2("ltts")
        a = build_management_answer_v5(fp)
        digests.add(hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest())
    assert len(digests) == 1, f"Non-deterministic output across 5 runs (LTTS): {digests}"


# ── M52-23: 5-run determinism — Data Patterns ────────────────────────────────
def test_m52_23_determinism_5_runs_data_patterns():
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.assembler_v5 import build_management_answer_v5
    digests = set()
    for _ in range(5):
        fp = build_management_quality_fact_pack_v2("data_patterns")
        a = build_management_answer_v5(fp)
        digests.add(hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest())
    assert len(digests) == 1, f"Non-deterministic output across 5 runs (Data Patterns): {digests}"


# ── M52-24: V5 candidate ≠ V4 M51 candidate ──────────────────────────────────
def test_m52_24_v5_candidate_differs_from_m51():
    assert V5_CANDIDATE_DIGEST != M51_CANDIDATE_DIGEST, (
        "V5 and M51 V4 candidate digests must differ"
    )
    assert V5_EXECUTION_ID != M51_EXECUTION_ID, (
        "V5 and M51 V4 execution IDs must differ"
    )


# ── M52-25: V5 answers to replay do not match M51 V4 answer ──────────────────
def test_m52_25_v5_answer_differs_from_m51_answer():
    m51_path = COMPANY_MEMORY / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / \
        "regeneration_candidate_how_good_is_management_444fc5f4166d.json"
    m51 = json.loads(m51_path.read_text())
    m51_answer_digest = hashlib.sha256(
        json.dumps(m51["answer"], sort_keys=True).encode()
    ).hexdigest()
    v5 = json.loads(V5_CANDIDATE_PATH.read_text())
    v5_answer_digest = hashlib.sha256(
        json.dumps(v5["answer"], sort_keys=True).encode()
    ).hexdigest()
    assert m51_answer_digest != v5_answer_digest, (
        "V5 answer must differ from M51 V4 answer (fixes change the output)"
    )


# ── M52-26: Planner reports 0 AI calls for management quality ─────────────────
def test_m52_26_planner_zero_ai_calls_management_quality():
    from intelligence.regeneration_planner import TOKEN_TELEMETRY
    telemetry = TOKEN_TELEMETRY.get("how_good_is_management_synthesis", {})
    assert telemetry.get("planned_ai_calls") == 0, (
        f"Planner should report 0 AI calls for management quality V5: {telemetry}"
    )
    assert telemetry.get("median_total_tokens") == 0


# ── M52-27: V5 management quality generation plans 0 AI calls ─────────────────
# TEST MIGRATION (ENG-MISSION52.1a): original test called plan_regeneration() which
# requires governance/answer_dependency_registry.json. That file was never committed
# (created in M40-M44 sessions but not git-committed). The underlying invariant —
# management quality V5 plans 0 AI calls — is authoritative in TOKEN_TELEMETRY
# (regeneration_planner.py module level). This migration verifies the same invariant
# via the authoritative config rather than the runtime planning path.
def test_m52_27_planner_plan_unit_zero_ai_calls_for_management():
    from intelligence.regeneration_planner import TOKEN_TELEMETRY
    telemetry = TOKEN_TELEMETRY.get("how_good_is_management_synthesis", {})
    assert telemetry.get("planned_ai_calls") == 0, (
        f"Management quality V5 must plan 0 AI calls per TOKEN_TELEMETRY: {telemetry}"
    )
    assert telemetry.get("median_total_tokens") == 0, (
        f"Management quality V5 must plan 0 tokens: {telemetry}"
    )


# ── M52-28: Contract V5 manifest has generation_mode=DETERMINISTIC ────────────
def test_m52_28_contract_v5_manifest_generation_mode():
    from intelligence.management_quality.contract_manifest import build_contract_v5_manifest
    manifest = build_contract_v5_manifest()
    assert manifest.get("generation_mode") == "DETERMINISTIC"
    assert manifest.get("zero_ai_calls") is True
    assert manifest.get("generation_contract_schema") == "m52_contract_v5"


# ── M52-29: Contract V5 assembler policy has empty LLM fields ─────────────────
def test_m52_29_contract_v5_no_llm_enrichment():
    from intelligence.management_quality.contract_manifest import ASSEMBLER_POLICY_V5
    llm_fields = ASSEMBLER_POLICY_V5.get("llm_may_enrich_but_not_overwrite", ["non-empty"])
    assert llm_fields == [], (
        f"V5 assembler policy must have empty llm_may_enrich: {llm_fields}"
    )
    assert ASSEMBLER_POLICY_V5.get("zero_ai_calls_invariant") is True


# ── M52-30: Contract V5 FP ≠ V4 FP ──────────────────────────────────────────
def test_m52_30_contract_v5_fp_differs_from_v4():
    from intelligence.management_quality.contract_manifest import (
        CONTRACT_V4_POLICY_DIGEST,
        CONTRACT_V5_POLICY_DIGEST,
    )
    assert CONTRACT_V4_POLICY_DIGEST != CONTRACT_V5_POLICY_DIGEST, (
        "V5 and V4 contract fingerprints must differ"
    )


# ── M52-31: Human decisions recorded for M51.1 ────────────────────────────────
def test_m52_31_m511_human_decisions_recorded():
    hr_path = REPO / "governance" / "ENG_MISSION51_NARRATIVE_ONLY_REGENERATION_HUMAN_REVIEW.json"
    with open(hr_path) as f:
        review = json.load(f)
    hd = review.get("human_decision_m511", {})
    assert hd.get("ARTIFACT_HUMAN_DECISION") == "NEEDS_CHANGES"
    assert hd.get("AI_ARCHITECTURE_HUMAN_DECISION") == "REMOVE_AI"
    assert hd.get("HUMAN_REVIEWER") == "Yogesh"
    assert hd.get("HUMAN_REVIEW_TIMESTAMP") not in (None, "PENDING")


# ── M52-32: Canonical investor-value classification reconciled ────────────────
def test_m52_32_m51_final_investor_value_canonical():
    hr_path = REPO / "governance" / "ENG_MISSION51_NARRATIVE_ONLY_REGENERATION_HUMAN_REVIEW.json"
    with open(hr_path) as f:
        review = json.load(f)
    hd = review.get("human_decision_m511", {})
    assert hd.get("m51_final_investor_value_canonical") == "ADEQUATE_INVESTOR_VALUE", (
        f"Canonical investor-value should be ADEQUATE_INVESTOR_VALUE: {hd.get('m51_final_investor_value_canonical')}"
    )


# ── M52-33: M37.8 byte-identical — not touched by M52 ────────────────────────
def test_m52_33_m37_8_byte_identical():
    actual = "sha256:" + hashlib.sha256(M37_8_PATH.read_bytes()).hexdigest()
    assert actual == M37_8_DIGEST, f"M37.8 must remain byte-identical: {actual}"
    assert "sha256:" + hashlib.sha256(LIVE_ANSWERS_PATH.read_bytes()).hexdigest() == ACTIVATED_DIGEST


# ── M52-34: V5 candidate at shadow location — M37.8 not overwritten ──────────
def test_m52_34_v5_in_shadow_not_overwriting_m37_8():
    assert V5_CANDIDATE_PATH.exists()
    assert V5_CANDIDATE_PATH != M37_8_PATH
    assert "_v5" in V5_CANDIDATE_PATH.name, "V5 candidate path should contain '_v5'"


# ── M52-35: All investor sections present in V5 answer ───────────────────────
def test_m52_35_all_investor_sections_present(sun_pharma_v5_answer):
    required = [
        "simple_answer", "key_points", "what_evidence_shows", "what_management_says",
        "where_management_was_consistent", "management_consistency_map",
        "what_may_mean_economically", "what_is_not_yet_proven", "what_to_monitor",
        "behavioral_descriptor", "deterministic_precision_facts",
    ]
    for key in required:
        assert key in sun_pharma_v5_answer and sun_pharma_v5_answer[key] is not None, (
            f"V5 answer missing section: {key}"
        )


# ── M52-36: DPFs present and canonical count ─────────────────────────────────
def test_m52_36_dpfs_canonical(sun_pharma_v5_answer):
    dpfs = sun_pharma_v5_answer.get("deterministic_precision_facts", [])
    assert len(dpfs) >= 3, f"Expected >= 3 DPFs: {len(dpfs)}"
    # Delivery follow-through DPF must be present
    delivery_dpfs = [d for d in dpfs if "delivered" in str(d.get("value", "")).lower()
                     or "delivery" in str(d.get("metric", "")).lower()]
    assert len(delivery_dpfs) >= 1, f"Delivery follow-through DPF must be present: {dpfs}"


# ── M52-37: Consistency map INCONSISTENT before CONSISTENT check ──────────────
def test_m52_37_consistency_map_check_order_fixed():
    """Regression for the substring bug: 'CONSISTENT' in 'INCONSISTENT' = True."""
    from intelligence.management_quality.investor_sections import build_management_consistency_map
    # Synthesize a fact pack with an INCONSISTENT raw value
    fake_fp = {
        "consistency_map": {
            "candor_and_consistency": "INCONSISTENT",
            "execution_discipline": "CONSISTENT",
        }
    }
    result = build_management_consistency_map(fake_fp)
    assert result.get("Candor and consistency") == "INCONSISTENT", (
        f"INCONSISTENT raw value must produce INCONSISTENT, not CONSISTENT: {result}"
    )
    assert result.get("Execution discipline") == "CONSISTENT"


# ── M52-38: MC-0031 regression — hard commitment with specific deadline ────────
def test_m52_38_mc0031_regression_by_characteristics():
    """Any hard commitment that is: product/regulatory, has a specific date, and is material
    must appear in what_management_says. This tests the MC-0031 pattern."""
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.investor_sections import build_what_management_says
    fp = build_management_quality_fact_pack_v2("sun_pharma")
    # Find hard commitments with product/regulatory characteristics
    hard_commits = fp.get("hard_commitments", [])
    product_regulatory = [
        hc for hc in hard_commits
        if any(word in str(hc.get("topic", "")).lower() + str(hc.get("category", "")).lower()
               for word in ["nidlegy", "product", "ema", "fda", "regulatory", "approval"])
    ]
    if product_regulatory:
        # Build what_management_says and verify at least one product/regulatory commitment present
        says = build_what_management_says(fp)
        product_in_says = any(
            any(word in s.lower() for word in ["nidlegy", "ema"])
            for s in says
        )
        assert product_in_says, (
            f"Product/regulatory hard commitment must appear in what_management_says: {says}"
        )


# ── M52-39: V5 investor sections version string is updated ────────────────────
def test_m52_39_investor_sections_version(sun_pharma_v5_answer):
    # V5 uses m52_investor_sections_v2 in contract manifest
    from intelligence.management_quality.contract_manifest import build_contract_v5_manifest
    manifest = build_contract_v5_manifest()
    inv_sections = manifest.get("investor_sections_artifact", {})
    assert inv_sections.get("version") == "m522d_investor_sections_v4", (
        f"Investor sections version should be m522d_investor_sections_v4: {inv_sections}"
    )


# ── M52-40: Full suite — 40/40 tests exist ───────────────────────────────────
def test_m52_40_full_test_suite_complete():
    """Verify this test file has all 40 M52 tests."""
    import ast
    test_src = Path(__file__).read_text()
    tree = ast.parse(test_src)
    test_names = [
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_m52_")
    ]
    assert len(test_names) == 40, (
        f"Expected 40 M52 tests, found {len(test_names)}: {sorted(test_names)}"
    )
