"""
M46 — Management Regeneration Contract Parity Tests

MQC-01..12: Management quality contract / fact-pack / assembler invariants
EIV-01..07: External Investor Value gate rules

Security constraints:
- 0 AI calls
- No artifact mutation
- No approval/activation
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from intelligence.external_investor_value_validator import validate_management_answer_eiv
from intelligence.management_quality.fact_pack import build_management_quality_fact_pack

REPO = Path(__file__).parent.parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_certified(company: str) -> Dict[str, Any]:
    path = REPO / "companies" / company / "company_memory" / "ask_intrinsiciq" / "shadow_level3_hybrid_answers.json"
    return json.loads(path.read_text("utf-8"))["answers"]["how-good-is-management"]


def _load_m45_2_candidate() -> Dict[str, Any]:
    path = REPO / "companies" / "sun_pharma" / "company_memory" / "ask_intrinsiciq" / "regeneration_candidate_how_good_is_management.json"
    return json.loads(path.read_text("utf-8"))


def _stripped(answer_dict: Dict, remove_fields: list) -> Dict:
    result = copy.deepcopy(answer_dict)
    for f in remove_fields:
        result.pop(f, None)
    return result


# ---------------------------------------------------------------------------
# MQC Tests — Management Quality Contract
# ---------------------------------------------------------------------------


class TestMQCFactPack:
    """MQC-07..11: Deterministic fact pack invariants"""

    def test_mqc_07_lifecycle_counts_preserved(self):
        """MQC-07: Fact pack preserves all lifecycle state counts from management_progression."""
        fp = build_management_quality_fact_pack(
            "sun_pharma",
            REPO / "companies" / "sun_pharma" / "company_memory",
        )
        counts = fp["progression_counts"]
        assert counts["total"] == 25
        assert counts.get("announced", 0) == 23
        assert counts.get("in_progress", 0) == 2
        assert counts.get("delivered", 0) == 0

    def test_mqc_07_datapatterns_lifecycle_counts(self):
        """MQC-07: Data Patterns fact pack preserves its delivered/partial/in_progress counts."""
        fp = build_management_quality_fact_pack(
            "datapatterns",
            REPO / "companies" / "datapatterns" / "company_memory",
        )
        counts = fp["progression_counts"]
        assert counts.get("delivered", 0) == 3
        assert counts.get("partially_delivered", 0) == 4
        assert counts["total"] > 0

    def test_mqc_08_dpfs_built_deterministically(self):
        """MQC-08: DPFs are built from fact pack data, not invented."""
        fp = build_management_quality_fact_pack(
            "sun_pharma",
            REPO / "companies" / "sun_pharma" / "company_memory",
        )
        dpfs = fp["dpfs"]
        assert len(dpfs) >= 3
        metrics = [d["metric"] for d in dpfs]
        assert any("delivery" in m.lower() for m in metrics), "Delivery follow-through DPF required"
        assert all(d.get("value") and d.get("semantic_meaning") for d in dpfs)

    def test_mqc_08_dpfs_contain_delivery_counts(self):
        """MQC-08: Delivery DPF value reflects canonical progression counts."""
        fp = build_management_quality_fact_pack(
            "sun_pharma",
            REPO / "companies" / "sun_pharma" / "company_memory",
        )
        delivery_dpf = next(d for d in fp["dpfs"] if "delivery" in d["metric"].lower())
        assert "0" in delivery_dpf["value"], "0 delivered should appear in DPF value"
        assert "25" in delivery_dpf["value"], "25 total should appear in DPF value"

    def test_mqc_09_llm_cannot_overwrite_counts(self):
        """MQC-09: Deterministic counts come from fact_pack, not LLM output."""
        fp = build_management_quality_fact_pack(
            "sun_pharma",
            REPO / "companies" / "sun_pharma" / "company_memory",
        )
        # Fact pack counts are independent of any answer text
        assert fp["progression_counts"]["total"] == 25
        assert fp["commitment_counts"]["total"] == 46
        assert fp["behavioral_descriptor"] == "FOLLOW_THROUGH_LARGELY_UNVERIFIED"

    def test_mqc_10_dpfs_independent_of_llm(self):
        """MQC-10: DPFs are derived from canonical evidence, not from any answer text."""
        fp = build_management_quality_fact_pack(
            "sun_pharma",
            REPO / "companies" / "sun_pharma" / "company_memory",
        )
        # DPF for delivery mentions the exact canonical counts
        commit_dpf = next(d for d in fp["dpfs"] if "commitment" in d["metric"].lower())
        assert "46" in commit_dpf["value"]

    def test_mqc_11_unknown_states_preserved(self):
        """MQC-11: Fact pack preserves UNKNOWN/Unable To Verify states."""
        fp = build_management_quality_fact_pack(
            "sun_pharma",
            REPO / "companies" / "sun_pharma" / "company_memory",
        )
        commit_dpf = next(d for d in fp["dpfs"] if "commitment" in d["metric"].lower())
        assert "unable" in commit_dpf["semantic_meaning"].lower() or "verify" in commit_dpf["semantic_meaning"].lower(), \
            "Unable To Verify state must be preserved in DPF"

    def test_mqc_12_financial_no_management_quality_claim(self):
        """MQC-12: Financial metrics in fact pack carry no management quality judgment."""
        fp = build_management_quality_fact_pack(
            "sun_pharma",
            REPO / "companies" / "sun_pharma" / "company_memory",
        )
        fin = fp["financial_context"]
        # Financial data is pure metrics, not management judgments
        for k, v in fin.items():
            if isinstance(v, dict):
                assert "management" not in str(v.get("semantic_meaning", "")).lower(), \
                    "Financial context must not contain management quality conclusions"


class TestMQCCurrentArtifact:
    """MQC-01..06: Contract invariants against certified answers"""

    def test_mqc_01_sun_pharma_passes_semantic_contract(self):
        """MQC-01: Current M37.8 Sun Pharma answer passes semantic contract."""
        certified = _load_certified("sun_pharma")
        result = validate_management_answer_eiv(certified)
        assert result["overall"] == "PASS", f"Sun Pharma EIV FAIL: {result['fails']}"

    def test_mqc_02_rejected_m45_2_fails_semantic_contract(self):
        """MQC-02: Rejected M45.2 candidate fails semantic contract."""
        candidate = _load_m45_2_candidate()
        result = validate_management_answer_eiv(candidate)
        assert result["overall"] == "FAIL", "M45.2 candidate should fail EIV"

    def test_mqc_03_missing_dpf_fails(self):
        """MQC-03: Answer without DPFs fails EIV-MQ-04."""
        certified = _load_certified("sun_pharma")
        no_dpf = copy.deepcopy(certified)
        no_dpf["answer"].pop("deterministic_precision_facts", None)
        result = validate_management_answer_eiv(no_dpf)
        assert result["overall"] == "FAIL"
        assert "EIV-MQ-04" in result["fails"]

    def test_mqc_04_missing_delivery_counts_fails(self):
        """MQC-04: Answer without factual counts in simple_answer + key_points + DPFs fails."""
        candidate = _load_m45_2_candidate()
        result = validate_management_answer_eiv(candidate)
        assert result["overall"] == "FAIL"
        # M45.2 should fail MQ-01 (no counts) or MQ-04 (no DPFs) or MQ-07 (missing fields)
        assert len(result["fails"]) > 0

    def test_mqc_05_missing_uncertainty_fails(self):
        """MQC-05: Answer without uncertainty coverage fails EIV-MQ-03."""
        certified = _load_certified("sun_pharma")
        no_uncertainty = copy.deepcopy(certified)
        no_uncertainty["answer"].pop("what_is_not_yet_proven", None)
        no_uncertainty["answer"]["evidence_gaps"] = []
        result = validate_management_answer_eiv(no_uncertainty)
        assert result["overall"] == "FAIL"
        assert "EIV-MQ-03" in result["fails"]

    def test_mqc_06_empty_placeholder_sections_fail(self):
        """MQC-06: Empty placeholder sections do not constitute investor value."""
        empty_answer = {
            "answer": {
                "simple_answer": "Management quality assessment for this company.",
                "key_points": [],
                "what_evidence_shows": [],
                "what_is_not_yet_proven": "",
                "deterministic_precision_facts": [],
                "what_to_monitor": [],
                "claims": [],
                "relationships": [],
            }
        }
        result = validate_management_answer_eiv(empty_answer)
        assert result["overall"] == "FAIL"


# ---------------------------------------------------------------------------
# EIV Tests
# ---------------------------------------------------------------------------


class TestEIVGate:
    """EIV-01..07: External Investor Value gate rule tests"""

    def test_eiv_01_current_certified_sun_pharma_passes(self):
        """EIV-01: Current certified Sun Pharma answer passes EIV."""
        result = validate_management_answer_eiv(_load_certified("sun_pharma"))
        assert result["overall"] == "PASS", f"EIV fails: {result['fails']}"

    def test_eiv_02_m45_2_rejected_fails(self):
        """EIV-02: M45.2 rejected candidate fails EIV (the regression M45.4 identified)."""
        result = validate_management_answer_eiv(_load_m45_2_candidate())
        assert result["overall"] == "FAIL"

    def test_eiv_03_generic_prose_fails(self):
        """EIV-03: Generic prose candidate without evidence fails."""
        generic = {
            "answer": {
                "simple_answer": (
                    "Management has shown a stable trajectory and demonstrates reasonable "
                    "alignment with shareholder interests through capital allocation discipline."
                ),
                "key_points": [
                    "Management trajectory is stable.",
                    "Capital allocation discipline is the strongest dimension.",
                    "Execution is the weakest area.",
                ],
                "what_evidence_shows": [],
                "what_is_not_yet_proven": "",
                "deterministic_precision_facts": [],
                "what_to_monitor": [],
                "claims": [],
                "relationships": [],
            }
        }
        result = validate_management_answer_eiv(generic)
        assert result["overall"] == "FAIL"

    def test_eiv_04_evidence_rich_and_safe_passes(self):
        """EIV-04: Evidence-rich, safe candidate passes EIV."""
        good = {
            "answer": {
                "simple_answer": (
                    "Sun Pharma's management delivery pattern is FOLLOW_THROUGH_LARGELY_UNVERIFIED: "
                    "0 of 25 tracked progression items confirmed delivered; 46 commitments tracked, "
                    "4 hard commitments, all Unable To Verify."
                ),
                "key_points": [
                    "0 of 25 tracked items confirmed delivered in available disclosures.",
                    "46 commitments tracked; 4 hard commitments; 0 confirmed delivered.",
                    "Capital allocation discipline is the strongest dimension.",
                    "Execution discipline has the most evidence gaps.",
                    "Evidence confidence: HIGH across 5+ source streams.",
                ],
                "what_evidence_shows": [
                    "Revenue ₹58,462 cr; PAT ₹11,479 cr (NPM 19.6%) in FY26.",
                    "0 of 25 progression items confirmed delivered; 2 in_progress; 23 announced.",
                    "Supply chain, FX, and IP risks are recurring without systematic resolution.",
                ],
                "what_is_not_yet_proven": (
                    "Whether any hard commitment reaches delivered status. "
                    "Whether recurring risks (supply chain, FX, IP) are addressed with quantified mitigation."
                ),
                "what_to_monitor": [
                    "Nidlegy EMA filing (H1CY24 target) — confirmed or delayed.",
                    "Risk resolution: supply chain, FX, IP.",
                ],
                "deterministic_precision_facts": [
                    {"metric": "Delivery follow-through", "value": "0 delivered / 2 in_progress / 23 announced (of 25)", "period": "FY20-FY26", "semantic_meaning": "No item confirmed delivered"},
                    {"metric": "Progression items", "value": "0 delivered / 2 in_progress / 23 announced (of 25)", "period": "FY20-FY26", "semantic_meaning": "No item confirmed"},
                    {"metric": "Management commitments", "value": "46 total; 46 unable to verify", "period": "FY20-FY26", "semantic_meaning": "All commitments Unable To Verify"},
                    {"metric": "Financial scale (FY26)", "value": "Revenue ₹58,462 cr; PAT ₹11,479 cr", "period": "FY26", "semantic_meaning": "Confirmed outcomes; attribution not established"},
                    {"metric": "Evidence confidence", "value": "HIGH", "period": "FY20-FY26", "semantic_meaning": "Supported by 5+ source streams"},
                ],
                "claims": [],
                "relationships": [],
            }
        }
        result = validate_management_answer_eiv(good)
        assert result["overall"] == "PASS", f"EIV fails: {result['fails']}"

    def test_eiv_05_missing_monitoring_fails(self):
        """EIV-05: Answer without monitoring value detected."""
        certified = _load_certified("sun_pharma")
        no_monitor = copy.deepcopy(certified)
        no_monitor["answer"].pop("what_to_monitor", None)
        no_monitor["answer"].pop("what_is_not_yet_proven", None)
        no_monitor["answer"]["evidence_gaps"] = []
        result = validate_management_answer_eiv(no_monitor)
        assert result["overall"] == "FAIL"
        assert "EIV-MQ-06" in result["fails"]

    def test_eiv_06_pacp_pass_eiv_fail_remains_blocked(self):
        """EIV-06: PACP PASS + EIV FAIL means candidate blocked from human review.

        This is an architectural invariant test: the M45.2 candidate had PACP PASS
        but EIV FAIL and was correctly rejected. We verify EIV FAIL detection.
        """
        candidate = _load_m45_2_candidate()
        # PACP result is recorded as PASS in the candidate metadata
        pacp_overall = candidate.get("pacp_overall", "")
        assert pacp_overall == "PASS", "M45.2 candidate should have PACP PASS"
        # EIV should fail
        eiv_result = validate_management_answer_eiv(candidate)
        assert eiv_result["overall"] == "FAIL", "M45.2 PACP PASS candidate must fail EIV"
        # This combination = BLOCKED
        combined_eligible = (pacp_overall == "PASS") and (eiv_result["overall"] == "PASS")
        assert not combined_eligible, "PACP PASS + EIV FAIL must not be eligible for human review"

    def test_eiv_07_pacp_pass_eiv_pass_eligible(self):
        """EIV-07: PACP PASS + EIV PASS = HUMAN_REVIEW_ELIGIBLE."""
        certified = _load_certified("sun_pharma")
        eiv_result = validate_management_answer_eiv(certified)
        pacp_overall = "PASS"  # M37.8 artifact passed all PACP checks
        combined_eligible = (pacp_overall == "PASS") and (eiv_result["overall"] == "PASS")
        assert combined_eligible, f"PACP PASS + EIV PASS should be eligible. EIV: {eiv_result['fails']}"


class TestEIVCrossCompany:
    """All 4 certified companies pass EIV"""

    @pytest.mark.parametrize("company", ["sun_pharma", "datapatterns", "tanla", "ujjivan"])
    def test_eiv_certified_answer_passes(self, company: str):
        """EIV-01 extended: All 4 M37.8-certified answers pass EIV."""
        certified = _load_certified(company)
        result = validate_management_answer_eiv(certified)
        assert result["overall"] == "PASS", f"{company} EIV fails: {result['fails']}"


class TestEIVGoldenFixtures:
    """Golden fixture tests for EIV regression detection"""

    def test_missing_dpf_candidate_caught(self):
        """Golden BAD: Missing DPF candidate fails EIV-MQ-04."""
        candidate = _load_m45_2_candidate()
        # M45.2 has no DPFs
        result = validate_management_answer_eiv(candidate)
        assert "EIV-MQ-04" in result["fails"]

    def test_missing_evidence_shows_caught(self):
        """Golden BAD: Missing what_evidence_shows fails EIV-MQ-02."""
        good_base = copy.deepcopy(_load_certified("sun_pharma"))
        good_base["answer"].pop("what_evidence_shows", None)
        # Remove claims too
        good_base["answer"]["claims"] = []
        result = validate_management_answer_eiv(good_base)
        assert result["overall"] == "FAIL"
        assert "EIV-MQ-02" in result["fails"]

    def test_missing_uncertainty_caught(self):
        """Golden BAD: Missing uncertainty fields fails EIV-MQ-03."""
        good_base = copy.deepcopy(_load_certified("sun_pharma"))
        good_base["answer"].pop("what_is_not_yet_proven", None)
        good_base["answer"]["evidence_gaps"] = []
        result = validate_management_answer_eiv(good_base)
        assert "EIV-MQ-03" in result["fails"]

    def test_missing_counts_in_simple_answer_caught(self):
        """Golden BAD: simple_answer without counts + no DPFs fails EIV."""
        no_counts = {
            "answer": {
                "simple_answer": "Management quality weakens conviction until execution and capital discipline improve.",
                "key_points": ["Trajectory is stable.", "Capital allocation is strongest.", "Execution is weakest."],
                "what_evidence_shows": [],
                "what_is_not_yet_proven": "",
                "deterministic_precision_facts": [],
                "what_to_monitor": [],
                "claims": [],
                "relationships": [],
            }
        }
        result = validate_management_answer_eiv(no_counts)
        assert result["overall"] == "FAIL"

    def test_financial_inference_overreach_not_false_positive(self):
        """Golden: Financial metrics alone with attribution caveat don't cause failure."""
        # The current certified answer mentions financial metrics with attribution caveats
        # This should NOT be caught by EIV as a violation
        certified = _load_certified("sun_pharma")
        result = validate_management_answer_eiv(certified)
        assert result["overall"] == "PASS"


class TestM46Acceptance:
    """M46 acceptance criteria checks"""

    def test_m45_2_rejected_candidate_caught_by_eiv(self):
        """M45_2_REJECTED_CANDIDATE_CAUGHT_BY_EIV = true"""
        result = validate_management_answer_eiv(_load_m45_2_candidate())
        assert result["overall"] == "FAIL"

    def test_current_trusted_artifact_passes_eiv(self):
        """Current M37.8 Sun Pharma certified answer passes EIV."""
        result = validate_management_answer_eiv(_load_certified("sun_pharma"))
        assert result["overall"] == "PASS"

    def test_all_four_companies_pass_eiv(self):
        """All 4 current certified answers pass EIV."""
        for co in ["sun_pharma", "datapatterns", "tanla", "ujjivan"]:
            result = validate_management_answer_eiv(_load_certified(co))
            assert result["overall"] == "PASS", f"{co}: EIV FAIL — {result['fails']}"

    def test_fact_pack_sun_pharma_schema(self):
        """Fact pack schema version present and company recorded."""
        fp = build_management_quality_fact_pack(
            "sun_pharma",
            REPO / "companies" / "sun_pharma" / "company_memory",
        )
        assert fp["schema_version"] == "management_fact_pack.v1"
        assert fp["company"] == "sun_pharma"
        assert fp["behavioral_descriptor"] == "FOLLOW_THROUGH_LARGELY_UNVERIFIED"

    def test_fact_pack_all_companies_build(self):
        """Deterministic fact pack builds for all 4 companies."""
        for co in ["sun_pharma", "datapatterns", "tanla", "ujjivan"]:
            fp = build_management_quality_fact_pack(
                co,
                REPO / "companies" / co / "company_memory",
            )
            assert fp["progression_counts"]["total"] > 0
            assert fp["commitment_counts"]["total"] > 0
            assert fp["behavioral_descriptor"]
            assert len(fp["dpfs"]) >= 3
