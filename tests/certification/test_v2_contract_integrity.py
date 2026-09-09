"""
Prometheus INVESTOR_CERTIFICATION_V2.0 — Contract Integrity & Evaluator Calibration Tests

Rules:
- ALL fixtures are SYNTHETIC. No production company data is loaded or accessed.
- Tests verify: (1) contract schema validity, (2) evaluator correctness, (3) calibration stability.
- Anti-gaming: synthetic fixtures deliberately probe edge cases that a naive rubric would misdecide.

Closure gate contribution: This file must pass before CERTIFICATION_V2_CONTRACT_FROZEN is declared.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = ROOT / "governance" / "certification" / "investor_certification_v2.json"

# Import evaluator functions from harness
import sys
sys.path.insert(0, str(ROOT))
from pipelines.run_investor_acceptance import (
    _detect_critical_failures_v2,
    _determine_verdict_v2,
    _compute_grade_v2,
    CERTIFICATION_CONTRACT_VERSION,
    DOMAIN_MAP,
    ALL_QUESTIONS,
    HARD_FLOOR_CHECKS,
)


# ─── Contract loading ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    assert CONTRACT_PATH.exists(), f"Contract file not found: {CONTRACT_PATH}"
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


# ─── C1: Schema validation ─────────────────────────────────────────────────────

class TestContractSchema:
    def test_contract_file_exists(self) -> None:
        """C1a: Contract file exists at canonical path."""
        assert CONTRACT_PATH.exists()

    def test_contract_is_valid_json(self) -> None:
        """C1b: Contract file is valid JSON."""
        data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_contract_has_required_top_level_fields(self, contract: dict[str, Any]) -> None:
        """C1c: All required top-level fields are present."""
        required = [
            "certification_id", "frozen_at", "status", "product_claim",
            "question_count", "questions", "domains", "verdict_taxonomy",
            "critical_failure_taxonomy", "numeric_scoring", "investor_grade_gate",
            "grade_taxonomy", "evaluator", "evidence_boundary",
            "answer_generation_path", "provenance_requirements",
            "persistence_contract", "versioning_rules",
        ]
        for field in required:
            assert field in contract, f"Missing required field: {field!r}"

    def test_contract_status_is_frozen(self, contract: dict[str, Any]) -> None:
        """C1d: Contract status must be FROZEN."""
        assert contract["status"] == "FROZEN", f"Expected FROZEN, got {contract['status']!r}"

    def test_contract_id_matches_module_constant(self, contract: dict[str, Any]) -> None:
        """C1e: Contract certification_id matches CERTIFICATION_CONTRACT_VERSION in harness."""
        assert contract["certification_id"] == CERTIFICATION_CONTRACT_VERSION

    def test_question_count_matches_list_length(self, contract: dict[str, Any]) -> None:
        """C1f: question_count == len(questions)."""
        assert contract["question_count"] == len(contract["questions"])

    def test_question_count_is_25(self, contract: dict[str, Any]) -> None:
        """C1g: Exactly 25 questions (deliberate design decision)."""
        assert contract["question_count"] == 25
        assert len(contract["questions"]) == 25

    def test_question_ids_are_unique(self, contract: dict[str, Any]) -> None:
        """C1h: No duplicate question IDs."""
        ids = [q["question_id"] for q in contract["questions"]]
        assert len(ids) == len(set(ids)), f"Duplicate question IDs: {[i for i in ids if ids.count(i) > 1]}"

    def test_every_question_has_required_fields(self, contract: dict[str, Any]) -> None:
        """C1i: Every question has question_id, wording, domain, capability_tested."""
        required = ["question_id", "wording", "domain", "capability_tested"]
        for q in contract["questions"]:
            for field in required:
                assert field in q, f"Question {q.get('question_id')!r} missing field {field!r}"

    def test_all_question_domains_valid(self, contract: dict[str, Any]) -> None:
        """C1j: Every question domain is a key in the domains block."""
        valid_domains = set(contract["domains"].keys())
        for q in contract["questions"]:
            assert q["domain"] in valid_domains, (
                f"Question {q['question_id']!r} has unknown domain {q['domain']!r}"
            )

    def test_domain_question_ids_reference_real_questions(self, contract: dict[str, Any]) -> None:
        """C1k: Every question_id in domains block exists in the questions list."""
        all_ids = {q["question_id"] for q in contract["questions"]}
        for domain, info in contract["domains"].items():
            for qid in info.get("question_ids", []):
                assert qid in all_ids, f"Domain {domain!r} references non-existent question {qid!r}"

    def test_all_25_questions_covered_by_domains(self, contract: dict[str, Any]) -> None:
        """C1l: All 25 questions appear in exactly one domain."""
        all_ids = {q["question_id"] for q in contract["questions"]}
        covered: set[str] = set()
        for domain, info in contract["domains"].items():
            for qid in info.get("question_ids", []):
                assert qid not in covered, f"{qid!r} appears in multiple domains"
                covered.add(qid)
        assert covered == all_ids, f"Questions not in any domain: {all_ids - covered}"

    def test_numeric_scoring_is_disabled(self, contract: dict[str, Any]) -> None:
        """C1m: NUMERIC_SCORING_ENABLED=NO (explicit design decision)."""
        assert contract["numeric_scoring"]["enabled"] is False

    def test_grade_taxonomy_is_enabled(self, contract: dict[str, Any]) -> None:
        """C1n: GRADE_TAXONOMY_ENABLED=YES (explicit design decision)."""
        assert contract["grade_taxonomy"]["enabled"] is True

    def test_grade_taxonomy_has_all_grades(self, contract: dict[str, Any]) -> None:
        """C1o: Grade taxonomy defines CERTIFIED, NEAR_CERTIFICATION, DEVELOPING, UNSAFE."""
        grades = set(contract["grade_taxonomy"]["grades"].keys())
        assert grades == {"CERTIFIED", "NEAR_CERTIFICATION", "DEVELOPING", "UNSAFE"}

    def test_verdict_taxonomy_has_three_tiers(self, contract: dict[str, Any]) -> None:
        """C1p: Verdict taxonomy defines exactly ACCEPTED, PARTIAL, REJECTED."""
        verdicts = set(contract["verdict_taxonomy"].keys())
        assert verdicts == {"ACCEPTED", "PARTIAL", "REJECTED"}

    def test_hard_floor_checks_are_listed(self, contract: dict[str, Any]) -> None:
        """C1q: hard_floor_checks field is present and non-empty."""
        hf = contract.get("hard_floor_checks", [])
        assert len(hf) >= 2
        assert "evidence_backed" in hf
        assert "internally_consistent" in hf

    def test_critical_failure_auto_detectable_count(self, contract: dict[str, Any]) -> None:
        """C1r: At least CF-A001 through CF-A004 are defined as auto-detectable."""
        auto = contract["critical_failure_taxonomy"]["auto_detectable"]
        assert "CF-A001" in auto
        assert "CF-A002" in auto
        assert "CF-A003" in auto
        assert "CF-A004" in auto

    def test_critical_failure_manual_count(self, contract: dict[str, Any]) -> None:
        """C1s: At least CF-M001 through CF-M007 are defined as manual-audit."""
        manual = contract["critical_failure_taxonomy"]["manual_audit_required"]
        for i in range(1, 8):
            key = f"CF-M{i:03d}"
            assert key in manual, f"{key} missing from manual_audit_required"

    def test_contract_version_matches_all_questions_in_harness(self, contract: dict[str, Any]) -> None:
        """C1t: Every contract question_id exists in harness ALL_QUESTIONS."""
        contract_ids = {q["question_id"] for q in contract["questions"]}
        harness_ids = set(ALL_QUESTIONS)
        assert contract_ids == harness_ids, (
            f"Contract/harness mismatch:\n"
            f"  In contract, not harness: {contract_ids - harness_ids}\n"
            f"  In harness, not contract: {harness_ids - contract_ids}"
        )

    def test_domain_map_matches_contract_domains(self, contract: dict[str, Any]) -> None:
        """C1u: Harness DOMAIN_MAP domains match contract domains block."""
        contract_domains = set(contract["domains"].keys())
        harness_domains = set(DOMAIN_MAP.keys())
        assert contract_domains == harness_domains, (
            f"Domain mismatch:\n"
            f"  Contract only: {contract_domains - harness_domains}\n"
            f"  Harness only: {harness_domains - contract_domains}"
        )

    def test_essential_domain_floors_defined(self, contract: dict[str, Any]) -> None:
        """C1v: financial_intelligence and management_accountability have essential_floor=true."""
        domains = contract["domains"]
        assert domains["financial_intelligence"]["essential_floor"] is True
        assert domains["management_accountability"]["essential_floor"] is True

    def test_investor_grade_gate_thresholds(self, contract: dict[str, Any]) -> None:
        """C1w: Investor-grade gate specifies min_accepted_count=15, max_rejected_count=2."""
        conds = contract["investor_grade_gate"]["conditions"]
        assert conds["min_accepted_count"] == 15
        assert conds["max_rejected_count"] == 2
        assert conds["critical_failures_must_be_zero"] is True


# ─── C2: Evaluator contract integrity ─────────────────────────────────────────

class TestHardFloorChecks:
    def test_hard_floor_checks_match_contract(self) -> None:
        """C2a: Harness HARD_FLOOR_CHECKS matches contract hard_floor_checks."""
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        assert HARD_FLOOR_CHECKS == set(contract["hard_floor_checks"])


# ─── C3: Synthetic calibration fixtures ───────────────────────────────────────
# ALL fixtures below are fully synthetic. No production company data involved.

def _all_pass_checks(extras: dict[str, Any] | None = None) -> dict[str, Any]:
    """Returns semantic checks dict where all applicable checks PASS."""
    base = {
        "specific":              {"result": "PASS", "detail": "contains FY24 metric"},
        "longitudinal":          {"result": "PASS", "detail": "3 fiscal years referenced"},
        "evidence_backed":       {"result": "PASS", "detail": "direct evidence; sources: [financial_truth_pack]"},
        "internally_consistent": {"result": "PASS", "detail": "no contradiction"},
        "economically_relevant": {"result": "PASS", "detail": "revenue reference present"},
        "uncertainty_aware":     {"result": "PASS", "detail": "full support; no note required"},
        "non_generic":           {"result": "PASS", "detail": "2 company-specific points"},
        "decision_useful":       {"result": "PASS", "detail": "watchpoint present"},
    }
    if extras:
        base.update(extras)
    return base


def _synthetic_answer(
    answer_status: str = "supported",
    evidence_status: str = "direct",
    key_points: list[str] | None = None,
    simple_answer: str = "Revenue grew 22% in FY24 to ₹1,200 crore.",
    uncertainty_note: dict | None = None,
) -> dict[str, Any]:
    return {
        "answer_status": answer_status,
        "evidence_summary": {"status": evidence_status},
        "key_points": key_points or ["FY24 revenue ₹1,200 crore.", "FY23 revenue ₹980 crore."],
        "simple_answer": simple_answer,
        "detailed_explanation": "",
        "uncertainty_note": uncertainty_note or {},
    }


class TestVerdictCalibration:
    """Calibration tests: verify _determine_verdict_v2 produces correct verdict for known inputs."""

    def test_all_pass_yields_accepted(self) -> None:
        """C3a: All checks PASS → ACCEPTED."""
        checks = _all_pass_checks()
        verdict, rationale = _determine_verdict_v2(checks, [])
        assert verdict == "ACCEPTED", f"Expected ACCEPTED, got {verdict}: {rationale}"

    def test_na_checks_excluded_still_accepted(self) -> None:
        """C3b: N/A checks are excluded from evaluation; all remaining PASS → ACCEPTED."""
        checks = _all_pass_checks({"longitudinal": {"result": "N/A", "detail": "no series"}})
        verdict, _ = _determine_verdict_v2(checks, [])
        assert verdict == "ACCEPTED"

    def test_soft_floor_fail_yields_partial(self) -> None:
        """C3c: Hard floors PASS + one soft-floor FAIL → PARTIAL (not REJECTED)."""
        checks = _all_pass_checks({"specific": {"result": "FAIL", "detail": "no metric"}})
        verdict, rationale = _determine_verdict_v2(checks, [])
        assert verdict == "PARTIAL", f"Expected PARTIAL, got {verdict}: {rationale}"
        assert "specific" in rationale

    def test_multiple_soft_floor_fails_yields_partial(self) -> None:
        """C3d: Multiple soft-floor FAILs → PARTIAL."""
        checks = _all_pass_checks({
            "specific":           {"result": "FAIL", "detail": "no metric"},
            "non_generic":        {"result": "FAIL", "detail": "boilerplate"},
            "decision_useful":    {"result": "FAIL", "detail": "no watchpoint"},
        })
        verdict, _ = _determine_verdict_v2(checks, [])
        assert verdict == "PARTIAL"

    def test_evidence_backed_fail_yields_rejected(self) -> None:
        """C3e: evidence_backed FAIL (hard floor) → REJECTED even if all other checks PASS."""
        checks = _all_pass_checks({"evidence_backed": {"result": "FAIL", "detail": "evidence missing"}})
        verdict, rationale = _determine_verdict_v2(checks, [])
        assert verdict == "REJECTED", f"Expected REJECTED, got {verdict}: {rationale}"
        assert "evidence_backed" in rationale

    def test_internally_consistent_fail_yields_rejected(self) -> None:
        """C3f: internally_consistent FAIL (hard floor) → REJECTED."""
        checks = _all_pass_checks({"internally_consistent": {"result": "FAIL", "detail": "contradiction"}})
        verdict, rationale = _determine_verdict_v2(checks, [])
        assert verdict == "REJECTED"
        assert "internally_consistent" in rationale

    def test_critical_failure_overrides_all_pass_to_rejected(self) -> None:
        """C3g: Critical failure present → REJECTED even if all semantic checks PASS."""
        checks = _all_pass_checks()
        verdict, rationale = _determine_verdict_v2(checks, ["CF-A001"])
        assert verdict == "REJECTED", f"Expected REJECTED due to CF-A001, got {verdict}"
        assert "CF-A001" in rationale

    def test_critical_failure_with_partial_checks_yields_rejected(self) -> None:
        """C3h: Critical failure present → REJECTED regardless of check mix."""
        checks = _all_pass_checks({"specific": {"result": "FAIL", "detail": "no metric"}})
        verdict, _ = _determine_verdict_v2(checks, ["CF-A004"])
        assert verdict == "REJECTED"

    def test_unknown_check_result_treated_as_applicable(self) -> None:
        """C3i: A check result that is not PASS and not N/A counts as FAIL → PARTIAL."""
        checks = _all_pass_checks({"specific": {"result": "UNKNOWN", "detail": "indeterminate"}})
        verdict, _ = _determine_verdict_v2(checks, [])
        # UNKNOWN is not PASS and not N/A → treated as failing soft-floor check → PARTIAL
        assert verdict == "PARTIAL"

    def test_hard_floor_fail_beats_critical_failure_order(self) -> None:
        """C3j: Both CF and hard-floor fail → REJECTED (CF detected first)."""
        checks = _all_pass_checks({
            "evidence_backed": {"result": "FAIL", "detail": "missing"},
            "internally_consistent": {"result": "FAIL", "detail": "contradiction"},
        })
        verdict, rationale = _determine_verdict_v2(checks, ["CF-A001"])
        assert verdict == "REJECTED"
        assert "CF-A001" in rationale  # CF detected first, so mentioned first

    def test_empty_checks_with_no_cfs_yields_accepted(self) -> None:
        """C3k: Empty checks dict with no CFs → ACCEPTED (vacuous: no failures)."""
        verdict, _ = _determine_verdict_v2({}, [])
        assert verdict == "ACCEPTED"


# ─── C4: Critical failure detection calibration ───────────────────────────────

class TestCriticalFailureDetection:

    def test_cf_a001_detected_on_internally_consistent_fail(self) -> None:
        """C4a: CF-A001 detected when internally_consistent check fails."""
        answer = _synthetic_answer()
        checks = {"internally_consistent": {"result": "FAIL", "detail": "contradiction"}}
        cfs = _detect_critical_failures_v2("what-has-management-promised", answer, [], checks)
        assert "CF-A001" in cfs

    def test_cf_a001_not_detected_when_internally_consistent_passes(self) -> None:
        """C4b: CF-A001 NOT detected when internally_consistent PASS."""
        answer = _synthetic_answer()
        checks = {"internally_consistent": {"result": "PASS", "detail": "ok"}}
        cfs = _detect_critical_failures_v2("what-has-management-promised", answer, [], checks)
        assert "CF-A001" not in cfs

    def test_cf_a003_detected_on_pre_2020_project(self) -> None:
        """C4c: CF-A003 detected when what-projects-are-underway has pre-2020 year in key_points."""
        answer = _synthetic_answer(
            key_points=["2014 plant suspension: regulatory action by USFDA at Toansa."]
        )
        cfs = _detect_critical_failures_v2("what-projects-are-underway", answer, [], {})
        assert "CF-A003" in cfs

    def test_cf_a003_not_detected_on_recent_project(self) -> None:
        """C4d: CF-A003 NOT detected when project year is 2022+."""
        answer = _synthetic_answer(
            key_points=["New manufacturing plant commissioned in FY2022 at Halol."]
        )
        cfs = _detect_critical_failures_v2("what-projects-are-underway", answer, [], {})
        assert "CF-A003" not in cfs

    def test_cf_a003_not_triggered_on_wrong_question(self) -> None:
        """C4e: CF-A003 NOT detected on a non-project question even with old year."""
        answer = _synthetic_answer(key_points=["FY2014 revenue was ₹700 crore."])
        cfs = _detect_critical_failures_v2("are-per-share-economics-improving", answer, [], {})
        assert "CF-A003" not in cfs

    def test_cf_a004_detected_on_template_language_with_bad_rendering(self) -> None:
        """C4f: CF-A004 detected when BAD_RENDERING defect + template pattern in key_points."""
        answer = _synthetic_answer(
            key_points=["investment lens implication: regenerate the progression"]
        )
        cfs = _detect_critical_failures_v2(
            "what-would-buffett-focus-on", answer, ["BAD_RENDERING"], {}
        )
        assert "CF-A004" in cfs

    def test_cf_a004_not_detected_without_bad_rendering(self) -> None:
        """C4g: CF-A004 NOT detected if BAD_RENDERING defect is absent (even if template text present)."""
        answer = _synthetic_answer(
            key_points=["investment lens implication: regenerate the progression"]
        )
        cfs = _detect_critical_failures_v2(
            "what-would-buffett-focus-on", answer, [], {}  # no BAD_RENDERING
        )
        assert "CF-A004" not in cfs

    def test_cf_a002_detected_with_stale_and_bad_evidence_link(self) -> None:
        """C4h: CF-A002 detected when both STALE_ARTIFACT and BAD_EVIDENCE_LINK present."""
        answer = _synthetic_answer()
        cfs = _detect_critical_failures_v2(
            "did-past-claims-come-true", answer,
            ["STALE_ARTIFACT", "BAD_EVIDENCE_LINK"], {}
        )
        assert "CF-A002" in cfs

    def test_cf_a002_not_detected_with_only_stale(self) -> None:
        """C4i: CF-A002 NOT detected when STALE_ARTIFACT present but BAD_EVIDENCE_LINK absent."""
        answer = _synthetic_answer()
        cfs = _detect_critical_failures_v2(
            "did-past-claims-come-true", answer, ["STALE_ARTIFACT"], {}
        )
        assert "CF-A002" not in cfs

    def test_multiple_cfs_can_co_occur(self) -> None:
        """C4j: Multiple CFs can be detected simultaneously."""
        answer = _synthetic_answer(
            key_points=["2014 plant: USFDA action at Toansa.", "investment lens implication: regenerate"]
        )
        cfs = _detect_critical_failures_v2(
            "what-projects-are-underway", answer,
            ["STALE_ARTIFACT", "BAD_EVIDENCE_LINK", "BAD_RENDERING"],
            {"internally_consistent": {"result": "FAIL", "detail": "contradiction"}},
        )
        assert "CF-A001" in cfs
        assert "CF-A002" in cfs
        assert "CF-A003" in cfs
        assert "CF-A004" in cfs

    def test_no_cfs_on_clean_answer(self) -> None:
        """C4k: No CFs detected on a clean answer with no defects."""
        answer = _synthetic_answer()
        checks = _all_pass_checks()
        cfs = _detect_critical_failures_v2("what-does-company-do", answer, [], checks)
        assert cfs == []


# ─── C5: Grade taxonomy calibration ───────────────────────────────────────────

class TestGradeCalibration:

    def _domain_accepted(self, fi: int = 1, ma: int = 1) -> dict[str, int]:
        return {
            "financial_intelligence": fi,
            "management_accountability": ma,
            "business_understanding": 0,
            "operational_intelligence": 0,
            "risk_and_diligence": 0,
            "investor_judgment": 0,
        }

    def test_certified_on_gate_pass(self) -> None:
        """C5a: 20 ACCEPTED / 0 REJECTED / 5 PARTIAL / 0 CF + domain floors → CERTIFIED."""
        result = _compute_grade_v2(20, 0, 5, 25, 0, self._domain_accepted())
        assert result["grade"] == "CERTIFIED"
        assert result["investor_grade_pass"] is True

    def test_certified_boundary_exactly_60_pct(self) -> None:
        """C5b: Exactly 15/25 ACCEPTED, 0 REJECTED, 0 CF, domain floors met → CERTIFIED."""
        result = _compute_grade_v2(15, 0, 10, 25, 0, self._domain_accepted())
        assert result["grade"] == "CERTIFIED"

    def test_not_certified_on_14_accepted(self) -> None:
        """C5c: 14/25 ACCEPTED falls below 60% threshold → NOT CERTIFIED."""
        result = _compute_grade_v2(14, 0, 11, 25, 0, self._domain_accepted())
        assert result["grade"] != "CERTIFIED"
        assert result["investor_grade_pass"] is False

    def test_not_certified_on_3_rejected(self) -> None:
        """C5d: 15 ACCEPTED but 3 REJECTED → fails rejected ≤2 condition → NOT CERTIFIED."""
        result = _compute_grade_v2(15, 3, 7, 25, 0, self._domain_accepted())
        assert result["grade"] != "CERTIFIED"

    def test_not_certified_on_missing_fi_floor(self) -> None:
        """C5e: All counts pass but financial_intelligence floor = 0 → NOT CERTIFIED."""
        result = _compute_grade_v2(20, 0, 5, 25, 0, self._domain_accepted(fi=0, ma=1))
        assert result["grade"] != "CERTIFIED"
        assert result["investor_grade_pass"] is False

    def test_not_certified_on_missing_ma_floor(self) -> None:
        """C5f: All counts pass but management_accountability floor = 0 → NOT CERTIFIED."""
        result = _compute_grade_v2(20, 0, 5, 25, 0, self._domain_accepted(fi=1, ma=0))
        assert result["grade"] != "CERTIFIED"
        assert result["investor_grade_pass"] is False

    def test_unsafe_on_any_critical_failure(self) -> None:
        """C5g: Any critical failure → UNSAFE, investor_grade_pass=False."""
        result = _compute_grade_v2(20, 0, 5, 25, 1, self._domain_accepted())
        assert result["grade"] == "UNSAFE"
        assert result["investor_grade_pass"] is False

    def test_unsafe_on_fewer_than_8_accepted(self) -> None:
        """C5h: Fewer than 8 ACCEPTED → UNSAFE regardless of other conditions."""
        result = _compute_grade_v2(7, 0, 18, 25, 0, self._domain_accepted())
        assert result["grade"] == "UNSAFE"

    def test_near_certification_on_4_of_5_conditions(self) -> None:
        """C5i: 0 CFs, 4/5 gate conditions met → NEAR_CERTIFICATION."""
        # Missing financial_intelligence floor but otherwise strong: 16/25, 1 rejected
        result = _compute_grade_v2(16, 1, 8, 25, 0, self._domain_accepted(fi=0, ma=1))
        assert result["grade"] == "NEAR_CERTIFICATION"
        assert result["investor_grade_pass"] is False

    def test_developing_on_3_or_fewer_conditions(self) -> None:
        """C5j: 0 CFs, 3/5 gate conditions met → DEVELOPING."""
        # 12 accepted (below 15, below 60%), 3 rejected (above 2), both floors missing
        result = _compute_grade_v2(12, 3, 10, 25, 0, self._domain_accepted(fi=0, ma=0))
        assert result["grade"] == "DEVELOPING"

    def test_developing_on_partial_heavy_result(self) -> None:
        """C5k: Mostly PARTIAL answers with low ACCEPTED → DEVELOPING."""
        result = _compute_grade_v2(10, 0, 15, 25, 0, self._domain_accepted(fi=1, ma=1))
        assert result["grade"] in ("DEVELOPING", "NEAR_CERTIFICATION")

    def test_grade_result_always_has_investor_grade_pass(self) -> None:
        """C5l: _compute_grade_v2 always returns investor_grade_pass bool."""
        for accepted in [0, 8, 14, 15, 20, 25]:
            result = _compute_grade_v2(accepted, 0, 25 - accepted, 25, 0, self._domain_accepted())
            assert isinstance(result["investor_grade_pass"], bool)


# ─── C6: Anti-gaming calibration ──────────────────────────────────────────────

class TestAntiGamingCalibration:
    """Verify the evaluator resists known gaming patterns."""

    def test_unknown_everywhere_yields_partial(self) -> None:
        """C6a: If system returns non-N/A non-PASS results for all soft-floor checks → PARTIAL."""
        checks = {
            "specific":              {"result": "FAIL", "detail": "no metric"},
            "longitudinal":          {"result": "FAIL", "detail": "no years"},
            "evidence_backed":       {"result": "PASS", "detail": "ok"},
            "internally_consistent": {"result": "PASS", "detail": "ok"},
            "economically_relevant": {"result": "FAIL", "detail": "no econ"},
            "uncertainty_aware":     {"result": "PASS", "detail": "ok"},
            "non_generic":           {"result": "FAIL", "detail": "boilerplate"},
            "decision_useful":       {"result": "FAIL", "detail": "no watchpoint"},
        }
        verdict, _ = _determine_verdict_v2(checks, [])
        assert verdict == "PARTIAL"

    def test_boilerplate_fails_soft_floor(self) -> None:
        """C6b: Generic boilerplate answer fails non_generic soft-floor → PARTIAL."""
        checks = _all_pass_checks({
            "non_generic": {"result": "FAIL", "detail": "all key_points are generic pharmaceutical boilerplate"},
        })
        verdict, _ = _determine_verdict_v2(checks, [])
        assert verdict == "PARTIAL"

    def test_causality_without_evidence_triggers_internally_consistent_concern(self) -> None:
        """C6c: Causality trap: supported status but missing evidence → REJECTED via hard floor."""
        # Simulates: answer says 'supported' but evidence_status='missing' → CF-A001
        answer = _synthetic_answer(answer_status="supported", evidence_status="missing")
        checks_with_contradiction = _all_pass_checks({
            "internally_consistent": {"result": "FAIL", "detail": "answer_status=supported contradicts evidence_status=missing"},
            "evidence_backed": {"result": "FAIL", "detail": "evidence_summary.status=missing"},
        })
        cfs = _detect_critical_failures_v2("how-does-it-make-money", answer, [], checks_with_contradiction)
        assert "CF-A001" in cfs
        verdict, _ = _determine_verdict_v2(checks_with_contradiction, cfs)
        assert verdict == "REJECTED"

    def test_correct_uncertainty_preservation_does_not_fail(self) -> None:
        """C6d: An answer that honestly says 'insufficient evidence' can still be ACCEPTED."""
        # When disclosure limitation is correct, uncertainty_aware should PASS
        # hard floors: evidence_backed can be N/A if not applicable (or PASS if partial evidence)
        checks = {
            "specific":              {"result": "PASS", "detail": "company-specific context present"},
            "longitudinal":          {"result": "N/A", "detail": "not applicable"},
            "evidence_backed":       {"result": "PASS", "detail": "partial evidence; source accessed"},
            "internally_consistent": {"result": "PASS", "detail": "no contradiction"},
            "economically_relevant": {"result": "PASS", "detail": "economic context present"},
            "uncertainty_aware":     {"result": "PASS", "detail": "uncertainty_note set for partial evidence"},
            "non_generic":           {"result": "PASS", "detail": "company-specific points"},
            "decision_useful":       {"result": "PASS", "detail": "monitoring direction provided"},
        }
        verdict, _ = _determine_verdict_v2(checks, [])
        assert verdict == "ACCEPTED"

    def test_lifecycle_trap_pre2020_project_is_rejected(self) -> None:
        """C6e: Lifecycle trap: pre-2020 project served as current → CF-A003 → REJECTED."""
        answer = _synthetic_answer(
            key_points=["2016 plant shutdown ordered by USFDA for GMP violations."]
        )
        checks = _all_pass_checks()
        cfs = _detect_critical_failures_v2("what-projects-are-underway", answer, [], checks)
        assert "CF-A003" in cfs
        verdict, _ = _determine_verdict_v2(checks, cfs)
        assert verdict == "REJECTED"


# ─── C7: Contract hash integrity ─────────────────────────────────────────────

def compute_contract_hash(contract: dict[str, Any]) -> str:
    """
    Compute SHA-256 over the canonical contract JSON with contract_sha256 set to empty string.
    This is the reference implementation for the immutable freeze.
    """
    contract_copy = dict(contract)
    contract_copy["contract_sha256"] = ""
    canonical = json.dumps(contract_copy, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TestContractHash:
    def test_contract_sha256_field_exists(self, contract: dict[str, Any]) -> None:
        """C7a: contract_sha256 field must be present."""
        assert "contract_sha256" in contract

    def test_contract_sha256_is_not_placeholder_after_freeze(self, contract: dict[str, Any]) -> None:
        """C7b: contract_sha256 must be a 64-char hex string (not the placeholder)."""
        sha = contract["contract_sha256"]
        if sha == "TO_BE_COMPUTED":
            pytest.skip("Contract SHA not yet computed — run post_freeze_hash step")
        assert len(sha) == 64, f"SHA-256 must be 64 hex chars, got {len(sha)}: {sha!r}"
        assert all(c in "0123456789abcdef" for c in sha), f"Not a hex string: {sha!r}"

    def test_contract_hash_is_reproducible(self, contract: dict[str, Any]) -> None:
        """C7c: Hash computation is deterministic — same contract always produces same hash."""
        h1 = compute_contract_hash(contract)
        h2 = compute_contract_hash(contract)
        assert h1 == h2

    def test_contract_hash_changes_on_content_change(self, contract: dict[str, Any]) -> None:
        """C7d: Mutating any field produces a different hash (immutability guarantee)."""
        original_hash = compute_contract_hash(contract)
        mutated = dict(contract)
        mutated["question_count"] = 999
        mutated_hash = compute_contract_hash(mutated)
        assert original_hash != mutated_hash

    def test_stored_hash_matches_computed_hash(self, contract: dict[str, Any]) -> None:
        """C7e: If contract_sha256 is set, it must match recomputed hash."""
        sha = contract.get("contract_sha256", "")
        if sha in ("TO_BE_COMPUTED", "", None):
            pytest.skip("Contract SHA not yet computed")
        computed = compute_contract_hash(contract)
        assert computed == sha, (
            f"Contract hash mismatch — contract was modified after freeze!\n"
            f"  Stored:   {sha}\n"
            f"  Computed: {computed}"
        )
