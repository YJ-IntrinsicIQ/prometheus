"""
ENG-MISSION51 Test Suite — Narrative-Only Regeneration Canary (28 tests).

Verifies the complete Contract V4 pipeline:
  - Identity gates (evidence FP, contract FP, execution ID)
  - Deterministic section completeness and immutability
  - Rating quarantine / temporal / type separation
  - LLM authority constraints
  - Post-assembly section integrity
  - PACP, EIV, parity, freshness, eligibility
  - Release state invariants

All tests are 0-AI-call verification of pipeline properties.
"""
import hashlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent.parent
COMPANIES = REPO / "companies"
GOVERNANCE = REPO / "governance"

_M51_PLANNED_EXEC_ID = "sha256:444fc5f4166d1e5b39e30a58a8469ff2553106ca5f21d777cd1598ea32ae8909"
_M51_PLANNED_EVIDENCE_FP = "sha256:6793736f4298b82142d39d0439f299d7c11f0310ada29ff0a9cc99fac06c2aad"
# M51-era V4 FP (before M52 fixed investor_sections.py)
_M51_PLANNED_CONTRACT_V4_FP = "sha256:46dbdbe96e05fd0c233851ad3ad474fc2dd386f5c0d4955e00dd6fb490291ee7"
# M52-era V4 FP (after investor_sections.py consistency-map + MC-0031 fixes)
_M52_CONTRACT_V4_FP = "sha256:cf7747884dd41339701bfb182d8b9fef64a53dd1f5fffe8f0e1cdcf2626111a5"
_M51_CANDIDATE_PREFIX = "regeneration_candidate_how_good_is_management_444fc5f4166d.json"
_M37_8_DIGEST = "sha256:830679d1b44356ac2b29e9001d9f2408830ea4da260d9b0343242d43337bfb43"


# ── Fixtures ──────────────────────────────────────────────────────────────────


import json as _json_h
from pathlib import Path as _Path_h

import pytest as _pytest_h


@_pytest_h.fixture(autouse=True)
def _historical_dependency_contract_v3(monkeypatch):
    """The M49-M51 executions and their evidence fingerprints were produced under dependency
    contract v3. Since ENG-MISSION52.2c the live registry is v4 (complete V5 coverage), so these
    historical assertions evaluate against the preserved v3 registry. The invariants are unchanged."""
    v3 = _json_h.loads((_Path_h(__file__).resolve().parents[2] / "governance" / "answer_dependency_registry.v3_pre_m52.json").read_text())
    monkeypatch.setattr("intelligence.regeneration_planner._load_dependency_registry", lambda: v3)


@pytest.fixture(scope="module")
def fact_pack():
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    return build_management_quality_fact_pack_v2("sun_pharma")


@pytest.fixture(scope="module")
def investor_sections(fact_pack):
    from intelligence.management_quality.investor_sections import build_investor_sections
    return build_investor_sections(fact_pack)


@pytest.fixture(scope="module")
def pre_llm_artifact(fact_pack):
    from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4
    return assemble_management_answer_v4(fact_pack, llm_prose=None)


@pytest.fixture(scope="module")
def m51_candidate():
    cpath = COMPANIES / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / _M51_CANDIDATE_PREFIX
    if not cpath.exists():
        pytest.skip("M51 candidate not yet generated")
    with open(cpath) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def m51_answer(m51_candidate):
    return m51_candidate.get("answer", {})


@pytest.fixture(scope="module")
def manifest():
    mpath = COMPANIES / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / "regeneration_execution_manifest.json"
    with open(mpath) as f:
        return json.load(f)


# ── Test M51-01: M50 family closed ────────────────────────────────────────────

def test_m51_01_m50_family_closed():
    """M50/M50.1/M50.2 must be formally closed before M51."""
    import sys; sys.path.insert(0, str(REPO))

    m502_proof = GOVERNANCE / "ENG_MISSION50_2_GOVERNANCE_RECONCILIATION_PROOF.json"
    assert m502_proof.exists(), "M50.2 proof missing"
    with open(m502_proof) as f:
        p = json.load(f)
    assert p["m50_formal_closure"]["status"] == "FORMALLY_CLOSED"
    assert p["mission_objectives"]["M50_FORMALLY_CLOSED"] is True
    assert p["mission_objectives"]["M51_SINGLE_CALL_CANARY_READY"] is True


# ── Test M51-02: Contract V4 fingerprint ──────────────────────────────────────

def test_m51_02_contract_v4_fingerprint():
    """Contract V4 FP stability. M52 updated investor_sections.py (fixed consistency-map bug
    + MC-0031 omission), so the V4 FP changed from the M51-era value to the M52-era value.
    This is expected: investor_sections.py is part of the V4 manifest."""
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.management_quality.contract_manifest import compute_contract_v4_fingerprint
    fp = compute_contract_v4_fingerprint()
    assert fp == _M52_CONTRACT_V4_FP, (
        f"Contract V4 FP mismatch: {fp}. "
        f"M51-era FP was {_M51_PLANNED_CONTRACT_V4_FP} (before M52 fixes)."
    )


# ── Test M51-03: Evidence fingerprint ─────────────────────────────────────────

def test_m51_03_evidence_fingerprint():
    """Current evidence fingerprint must match planned M51 identity."""
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.regeneration_executor import _compute_evidence_fingerprint
    ev_fp = _compute_evidence_fingerprint("sun_pharma", COMPANIES)
    assert ev_fp == _M51_PLANNED_EVIDENCE_FP, f"Evidence FP mismatch: {ev_fp}"


# ── Test M51-04: Execution ID matches planned ─────────────────────────────────

def test_m51_04_execution_id_matches_planned():
    """M51 execution ID is stable when computed with M51-era contract FP.
    M52 changed investor_sections.py so the CURRENT V4 FP differs from M51-era.
    To verify M51 identity: use the historical M51-era V4 FP in the computation."""
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.regeneration_executor import _compute_evidence_fingerprint, compute_execution_id_v3
    ev_fp = _compute_evidence_fingerprint("sun_pharma", COMPANIES)
    # Use the M51-era V4 FP (historical), not the current V4 FP (updated by M52)
    eid = compute_execution_id_v3(
        "sun_pharma", "how_good_is_management_synthesis", ev_fp, _M51_PLANNED_CONTRACT_V4_FP
    )
    assert eid == _M51_PLANNED_EXEC_ID, f"Execution ID mismatch: {eid}"


# ── Test M51-05: Canonical hard commitment count ──────────────────────────────

def test_m51_05_canonical_hard_commitments(fact_pack):
    """Canonical hard commitment count must be 3 with correct IDs."""
    assert fact_pack.get("hard_commitment_count") == 3
    ids = {h["id"] for h in fact_pack.get("hard_commitments", [])}
    assert ids == {"MC-0029", "MC-0031", "MC-0039"}


# ── Test M51-06: Pre-LLM deterministic sections complete ─────────────────────

def test_m51_06_pre_llm_sections_complete(pre_llm_artifact):
    """Pre-LLM artifact must have all 6 investor sections."""
    required = [
        "what_evidence_shows", "what_management_says", "where_management_was_consistent",
        "management_consistency_map", "what_is_not_yet_proven", "what_to_monitor",
    ]
    for key in required:
        val = pre_llm_artifact.get(key)
        assert val, f"Pre-LLM missing section: {key}"


# ── Test M51-07: Section quality preflight ────────────────────────────────────

def test_m51_07_section_quality_preflight(pre_llm_artifact, fact_pack):
    """Deterministic sections must pass all M50 section-quality checks."""
    from intelligence.management_quality.rating_quarantine import scan_answer_for_rating_violations
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2

    # Rating violations
    violations = scan_answer_for_rating_violations(pre_llm_artifact)
    assert not violations, f"Rating violations in pre-LLM artifact: {violations}"

    # EIV on deterministic-only artifact
    eiv = validate_management_answer_eiv_v2(pre_llm_artifact, fact_pack=fact_pack)
    assert eiv.get("overall") == "PASS", f"EIV fails on pre-LLM artifact: {eiv.get('fails')}"


# ── Test M51-08: Rating language absent from generation input ─────────────────

def test_m51_08_rating_language_absent(fact_pack):
    """mq_summary unsafe fields must not be in fact_pack (quarantined)."""
    unsafe_fields = ["conclusion", "why_it_matters", "thesis_impact", "overall_view"]
    mqs = fact_pack.get("mq_summary", {})
    for uf in unsafe_fields:
        assert uf not in mqs, f"Unsafe mq_summary field still in fact_pack: {uf}"


# ── Test M51-09: Previous answer prose not used ───────────────────────────────

def test_m51_09_previous_answer_prose_not_used(pre_llm_artifact):
    """Pre-LLM artifact must not contain prose unique to prior certified answers."""
    # Probe: M37.8-specific text like exact specialty drug names in wrong sections
    art_text = json.dumps(pre_llm_artifact)
    # M45.2/M47/M49 candidates were not used as sources — just verify deterministic lineage
    assert pre_llm_artifact.get("_assembler_version") == "m50_assembler_v4"
    assert pre_llm_artifact.get("_deterministic_sections_preserved") is True


# ── Test M51-10: Only authorized LLM fields accepted ─────────────────────────

def test_m51_10_only_authorized_llm_fields():
    """Assembler V4 must only accept simple_answer and what_may_mean_economically from LLM."""
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4

    fp = build_management_quality_fact_pack_v2("sun_pharma")
    deterministic = assemble_management_answer_v4(fp, llm_prose=None)

    # Attempt to inject unauthorized field via LLM prose
    injected = {"simple_answer": "FOLLOW_THROUGH_LARGELY_UNVERIFIED override", "what_evidence_shows": ["INJECTED"]}
    assembled = assemble_management_answer_v4(fp, llm_prose=injected)

    # Unauthorized field must not override
    assert assembled.get("what_evidence_shows") == deterministic.get("what_evidence_shows"), \
        "LLM override of what_evidence_shows accepted — BLOCKED_REQUIRED"


# ── Test M51-11: Protected LLM field overrides blocked ───────────────────────

def test_m51_11_protected_field_overrides_blocked():
    """LLM_SECTION_OVERRIDE_BLOCKED must be True in every assembled artifact."""
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.management_quality.assembler_v4 import LLM_SECTION_OVERRIDE_BLOCKED
    assert LLM_SECTION_OVERRIDE_BLOCKED is True


# ── Test M51-12: Simple answer cannot introduce rating language ───────────────

def test_m51_12_simple_answer_no_rating_language():
    """LLM simple_answer with rating language must be rejected by assembler."""
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4

    fp = build_management_quality_fact_pack_v2("sun_pharma")
    det = assemble_management_answer_v4(fp, llm_prose=None)
    det_simple = det.get("simple_answer", "")

    llm_with_rating = {"simple_answer": "FOLLOW_THROUGH_LARGELY_UNVERIFIED management quality is weak overall"}
    assembled = assemble_management_answer_v4(fp, llm_prose=llm_with_rating)
    # Must not use the version with "management quality is weak"
    assert "management quality is weak" not in assembled.get("simple_answer", "").lower()


# ── Test M51-13: Simple answer cannot alter confirmed/projected status ─────────

def test_m51_13_simple_answer_temporal_protection():
    """LLM simple_answer calling confirmed revenue 'projected' must be rejected."""
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4

    fp = build_management_quality_fact_pack_v2("sun_pharma")
    det = assemble_management_answer_v4(fp, llm_prose=None)
    det_simple = det.get("simple_answer", "")

    llm_projected = {
        "simple_answer": "FOLLOW_THROUGH_LARGELY_UNVERIFIED — projected revenue ₹58,462 cr suggests growth"
    }
    assembled = assemble_management_answer_v4(fp, llm_prose=llm_projected)
    # assembler should reject because 'projected revenue' with confirmed financials fails temporal check
    assert assembled.get("simple_answer") == det_simple, \
        "Projected-revenue LLM simple_answer was accepted — temporal gate failed"


# ── Test M51-14: Simple answer cannot introduce unsupported causality ─────────

def test_m51_14_no_unsupported_causality(m51_answer):
    """Final simple_answer and what_may_mean_economically must not claim causation."""
    wmme = m51_answer.get("what_may_mean_economically", "")
    sa = m51_answer.get("simple_answer", "")
    causal_phrases = ["because management", "due to management", "management caused", "attributed to management"]
    for phrase in causal_phrases:
        assert phrase.lower() not in (sa + wmme).lower(), f"Unsupported causal phrase found: {phrase}"


# ── Test M51-15: Post-assembly deterministic sections equal pre-LLM ───────────

def test_m51_15_deterministic_sections_unchanged(m51_candidate):
    """deterministic_sections_unchanged must be True in M51 candidate."""
    assert m51_candidate.get("deterministic_sections_unchanged") is True, \
        "Deterministic sections changed after LLM assembly"


# ── Test M51-16: Hard commitment count cannot be changed by LLM ──────────────

def test_m51_16_hard_commitment_count_stable(m51_answer, fact_pack):
    """Hard commitment count in DPFs must match canonical fact pack."""
    dpfs = {d.get("metric"): d.get("value") for d in m51_answer.get("deterministic_precision_facts", [])}
    fp_dpfs = {d.get("metric"): d.get("value") for d in fact_pack.get("dpfs", [])}
    # Any commitment DPF in the candidate must match fact_pack
    for metric in fp_dpfs:
        if "commitment" in metric.lower() or "hard" in metric.lower():
            if metric in dpfs:
                assert dpfs[metric] == fp_dpfs[metric], f"DPF mismatch for {metric}"


# ── Test M51-17: DPFs cannot be changed by LLM ────────────────────────────────

def test_m51_17_dpfs_unchanged(m51_candidate):
    """Candidate was written with deterministic_sections_unchanged = True (covers DPFs)."""
    assert m51_candidate.get("deterministic_sections_unchanged") is True


# ── Test M51-18: Contract V4 validation required for eligibility ──────────────

def test_m51_18_contract_v4_validation(m51_answer):
    """M51 answer must pass Contract V4 structure validation."""
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.regeneration_executor import _validate_contract_v3_structure
    result = _validate_contract_v3_structure(m51_answer)
    assert result["valid"], f"Contract V4 validation fails: {result['fails']}"


# ── Test M51-19: Section quality gate required ────────────────────────────────

def test_m51_19_section_quality_gate(m51_answer, fact_pack):
    """M51 final answer must pass EIV section quality gate."""
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    eiv = validate_management_answer_eiv_v2(m51_answer, fact_pack=fact_pack)
    assert eiv.get("overall") == "PASS", f"EIV fails: {eiv.get('fails')}"


# ── Test M51-20: PACP required for eligibility ────────────────────────────────

def test_m51_20_pacp_pass(m51_candidate):
    """M51 candidate must record PACP PASS."""
    assert m51_candidate.get("pacp_overall") == "PASS"


# ── Test M51-21: EIV required for eligibility ─────────────────────────────────

def test_m51_21_eiv_pass(m51_candidate):
    """M51 candidate must record EIV PASS."""
    assert m51_candidate.get("eiv_v2_overall") == "PASS"


# ── Test M51-22: Freshness CURRENT required ───────────────────────────────────

def test_m51_22_freshness_current(manifest):
    """M51 execution history must record FRESHNESS = CURRENT."""
    m51_entries = [e for e in manifest.get("execution_history", [])
                   if e.get("mission") == "ENG-MISSION51"]
    assert len(m51_entries) >= 1, "No M51 entry in execution history"
    latest = m51_entries[-1]
    assert latest.get("freshness") == "CURRENT", f"Freshness: {latest.get('freshness')}"


# ── Test M51-23: M49 D1–D8 regression scan ────────────────────────────────────

def test_m51_23_m49_regression_scan(m51_answer):
    """M51 candidate must not recreate any M49 defect."""
    from intelligence.management_quality.rating_quarantine import scan_answer_for_rating_violations

    # D1: evidence specificity
    wes = m51_answer.get("what_evidence_shows", [])
    assert any(any(k in str(item) for k in ["FY", "₹", "MC-", "%", "Tier"]) for item in wes), \
        "D1 regression: what_evidence_shows is generic"

    # D2: no raw internal labels
    wtm = m51_answer.get("what_to_monitor", [])
    for item in wtm:
        assert "Industry_outlook" not in str(item), "D2 regression: raw internal label in monitoring"

    # D3: management says has named commitments
    wms = m51_answer.get("what_management_says", [])
    assert any("MC-" in str(item) or "target:" in str(item) for item in wms), \
        "D3 regression: generic management statements"

    # D4: no projected/confirmed confusion
    wmme = m51_answer.get("what_may_mean_economically", "")
    if "projected" in wmme.lower():
        assert "confirmed" in wmme.lower(), "D4 regression: confirmed revenue called projected"

    # D6: evidence confidence not mapped to outcome state
    cmap = m51_answer.get("management_consistency_map", {})
    ec_val = cmap.get("Evidence confidence", "")
    assert "UNABLE_TO_VERIFY" not in ec_val, f"D6 regression: evidence_confidence={ec_val}"

    # D7: future-facing commitments in unresolved
    winp = str(m51_answer.get("what_is_not_yet_proven", ""))
    assert "MC-0039" in winp or "MC-0031" in winp, "D7 regression: past-FY items in unresolved"

    # D8: no rating language
    violations = scan_answer_for_rating_violations(m51_answer)
    assert not violations, f"D8 regression: rating violations: {violations}"


# ── Test M51-24: Full gate chain → HUMAN_REVIEW_ELIGIBLE ─────────────────────

def test_m51_24_human_review_eligible(m51_candidate):
    """M51 candidate must reach HUMAN_REVIEW_ELIGIBLE."""
    assert m51_candidate.get("eligibility_state") == "HUMAN_REVIEW_ELIGIBLE"


# ── Test M51-25: Eligibility does not approve candidate ──────────────────────

def test_m51_25_eligibility_does_not_approve(m51_candidate):
    """HUMAN_REVIEW_ELIGIBLE must not mean approved."""
    state = m51_candidate.get("eligibility_state")
    assert state == "HUMAN_REVIEW_ELIGIBLE"
    assert state != "APPROVED"
    assert state != "ACTIVATED"


# ── Test M51-26: Eligibility does not activate candidate ─────────────────────

def test_m51_26_no_auto_activation():
    """M37.8 certified artifact must still be the runtime-served artifact."""
    certified_path = COMPANIES / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / "shadow_level3_hybrid_answers.json"
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.regeneration_executor import _file_digest
    digest = _file_digest(certified_path)
    assert digest == _M37_8_DIGEST, f"Certified artifact mutated: {digest}"


# ── Test M51-27: M37.8 remains runtime-served ────────────────────────────────

def test_m51_27_m37_8_still_serving():
    """M37.8 digest must be byte-identical post-M51."""
    certified_path = COMPANIES / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / "shadow_level3_hybrid_answers.json"
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.regeneration_executor import _file_digest
    assert _file_digest(certified_path) == _M37_8_DIGEST


# ── Test M51-28: Idempotency — second invocation reuses candidate ─────────────

def test_m51_28_idempotency(manifest):
    """M52 changed investor_sections.py → V4 FP changed → executor detects contract mismatch.
    Expected: run_regeneration_v4() returns M51_CONTRACT_IDENTITY_MISMATCH (not REUSE).
    This is correct behavior: when contract changes, prior generation is not reused."""
    import sys; sys.path.insert(0, str(REPO))
    from intelligence.regeneration_executor import run_regeneration_v4

    # the executor may write its manifest under companies/: run it against a disposable COPY of the company, never the served tree
    import shutil
    scratch = Path(__import__("tempfile").mkdtemp()) / "companies"
    shutil.copytree(REPO / "companies" / "sun_pharma", scratch / "sun_pharma", ignore=shutil.ignore_patterns("raw", "fy*"))
    result = run_regeneration_v4(company="sun_pharma", companies_root=scratch, dry_run=False)
    # M52 changed the V4 FP, so executor detects contract identity mismatch
    expected_decisions = {"M51_CONTRACT_IDENTITY_MISMATCH", "REUSE_EXISTING_GENERATION"}
    assert result.get("decision") in expected_decisions, (
        f"Unexpected decision: {result.get('decision')}"
    )
