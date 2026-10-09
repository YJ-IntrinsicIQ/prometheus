"""
ENG-MISSION50: Deterministic Investor Sections — 24 tests (M50-01 through M50-24)

0 AI calls. All deterministic.

COVERAGE:
  M50-01..04: rating_quarantine
  M50-05..08: investor_sections field structure
  M50-09..12: assembler_v4 LLM override block
  M50-13..16: assembler_v4 temporal protection
  M50-17..19: assembler_v4 rating language gate
  M50-20..22: EIV v2 new quality rules (MQ-17, MQ-18, MQ-19)
  M50-23: contract V4 fingerprint stable
  M50-24: fact_pack_v2 new fields present
"""
import json
import re
from pathlib import Path
from typing import Any, Dict

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_minimal_fp(**overrides) -> Dict[str, Any]:
    """Minimal fact_pack_v2-shaped dict for testing."""
    fp = {
        "behavioral_descriptor": "FOLLOW_THROUGH_LARGELY_UNVERIFIED",
        "progression_counts": {"total": 25, "delivered": 0, "in_progress": 2, "announced": 23},
        "commitment_counts": {"total": 46, "by_status": {"unable_to_verify": 46}},
        "hard_commitment_count": 5,
        "hard_commitments": [
            {"id": "MC-0029", "expected_timeframe": "By 2025", "normalized_commitment": "Carbon neutrality by 2025"},
            {"id": "MC-0031", "expected_timeframe": "H1CY24", "normalized_commitment": "Complete USFDA remediation by H1CY24"},
            {"id": "MC-0039", "expected_timeframe": "By 2030", "normalized_commitment": "25% revenue from specialty by 2030"},
            {"id": "MC-0012", "expected_timeframe": "in fy21", "normalized_commitment": "Capex of 8% revenue in fy21"},
            {"id": "MC-0023", "expected_timeframe": "in fy18", "normalized_commitment": "Taro turnaround in fy18"},
        ],
        "npm": 19.6,
        "financial_context": {
            "revenue": {"value": 50102.34, "unit": "crore", "fiscal_year": "FY26"},
            "pat": {"value": 9820.11, "unit": "crore", "fiscal_year": "FY26"},
        },
        "evidence_confidence": "high",
        "evidence_observations": ["Pharmerging markets expansion confirmed FY21-FY26"],
        "evidence_observations_raw": [
            {"evidence_type": "project_operational", "summary": "Pharmerging markets expansion confirmed", "period": "FY21-FY26"},
            {"evidence_type": "capital_outcome_partially_observed", "summary": "Halol USFDA remediation resolved FY22", "period": "FY22"},
        ],
        "evidence_period_range": "FY20-FY26",
        "latest_fy": 26,
        "management_statements": ["Specialty revenue target not verified by public disclosure"],
        "consistency_observations": ["execution_discipline: strong (3 evidence items)"],
        "consistency_map": {
            "execution_discipline": "strong",
            "candor_and_consistency": "weak",
            "strategic_clarity": "strong",
        },
        "uncertainty_items": ["Whether specialty revenue target is reached"],
        "monitoring_items": ["MC-0029 (By 2025): Carbon neutrality by 2025", "Revenue trajectory after FY26"],
        "dpfs": [
            {"metric": "Delivery follow-through", "value": "0 delivered / 2 in_progress / 23 announced (of 25)", "period": "multi-year", "semantic_meaning": "..."},
            {"metric": "Management commitments", "value": "5 hard; 46 Unable To Verify (of 46)", "period": "multi-year", "semantic_meaning": "..."},
            {"metric": "Financial scale (FY26)", "value": "Revenue ₹50,102 cr; PAT ₹9,820 cr; NPM 19.6%", "period": "FY26", "semantic_meaning": "..."},
            {"metric": "Evidence confidence", "value": "HIGH", "period": "multi-year", "semantic_meaning": "..."},
        ],
    }
    fp.update(overrides)
    return fp


# ── M50-01..04: rating_quarantine ──────────────────────────────────────────────

class TestRatingQuarantine:
    def test_m50_01_contains_rating_language_explicit_weak(self):
        """M50-01: 'management quality is weak' flagged as rating language."""
        from intelligence.management_quality.rating_quarantine import contains_rating_language
        assert contains_rating_language("Management quality is weak and the trajectory is stable.") is True

    def test_m50_02_contains_rating_language_false_for_neutral(self):
        """M50-02: neutral behavioral descriptor text passes quarantine check."""
        from intelligence.management_quality.rating_quarantine import contains_rating_language
        assert contains_rating_language("FOLLOW_THROUGH_LARGELY_UNVERIFIED delivery pattern") is False

    def test_m50_03_sanitize_mq_summary_removes_unsafe_fields(self):
        """M50-03: sanitize_mq_summary_for_generation removes conclusion/why_it_matters/thesis_impact."""
        from intelligence.management_quality.rating_quarantine import sanitize_mq_summary_for_generation, UNSAFE_MQ_SUMMARY_FIELDS
        raw_mqs = {
            "interpretation": {
                "conclusion": "Management quality is weak and the trajectory is stable.",
                "why_it_matters": "Management quality weakens conviction.",
                "thesis_impact": "weakens",
                "overall_view": "weak",
                "what_to_watch": ["Industry_outlook", "acquisition"],
            },
            "other_field": "safe content",
        }
        result = sanitize_mq_summary_for_generation(raw_mqs)
        interp = result["interpretation"]
        for unsafe_field in UNSAFE_MQ_SUMMARY_FIELDS:
            assert "QUARANTINED" in str(interp.get(unsafe_field, "")), f"{unsafe_field} not quarantined"
        # Safe fields preserved
        assert interp["what_to_watch"] == ["Industry_outlook", "acquisition"]
        assert result["other_field"] == "safe content"

    def test_m50_04_scan_answer_for_rating_violations_catches_weak(self):
        """M50-04: scan_answer detects 'management quality is weak' in simple_answer."""
        from intelligence.management_quality.rating_quarantine import scan_answer_for_rating_violations
        answer = {
            "simple_answer": "Management quality is weak. Delivery pattern is unverified.",
            "what_evidence_shows": ["Operational expansion confirmed"],
        }
        violations = scan_answer_for_rating_violations(answer)
        assert len(violations) >= 1
        assert any("simple_answer" in v for v in violations)


# ── M50-05..08: investor_sections field structure ──────────────────────────────

class TestInvestorSections:
    def test_m50_05_build_investor_sections_returns_all_required_fields(self):
        """M50-05: build_investor_sections returns all 6 required structured sections."""
        from intelligence.management_quality.investor_sections import build_investor_sections
        fp = _make_minimal_fp()
        sections = build_investor_sections(fp)
        for field in [
            "what_evidence_shows", "what_management_says", "where_management_was_consistent",
            "management_consistency_map", "what_is_not_yet_proven", "what_to_monitor",
        ]:
            assert field in sections, f"Missing: {field}"
        assert sections["_llm_section_override_blocked"] is True

    def test_m50_06_what_to_monitor_no_internal_labels(self):
        """M50-06: what_to_monitor built by investor_sections contains no internal labels."""
        from intelligence.management_quality.investor_sections import build_investor_sections, _is_internal_label
        fp = _make_minimal_fp()
        # Add internal labels to monitoring_items to test sanitization
        fp["monitoring_items"] = ["Industry_outlook", "acquisition", "MC-0029 (By 2025): Carbon neutrality"]
        sections = build_investor_sections(fp)
        for item in sections["what_to_monitor"]:
            assert not _is_internal_label(item), f"Internal label leaked: {repr(item)}"

    def test_m50_07_management_consistency_map_no_snake_case_keys(self):
        """M50-07: management_consistency_map uses human-readable labels, not snake_case."""
        from intelligence.management_quality.investor_sections import build_investor_sections
        fp = _make_minimal_fp()
        sections = build_investor_sections(fp)
        cmap = sections["management_consistency_map"]
        for key in cmap:
            # Readable labels should have spaces or be title-case or be EVIDENCE_CONFIDENCE_* style
            assert "_" not in key or key.startswith("EVIDENCE"), \
                f"Snake-case key leaked into consistency_map: {repr(key)}"

    def test_m50_08_what_management_says_future_facing_preferred(self):
        """M50-08: future-facing hard commitments (By 2025, By 2030) appear in what_management_says."""
        from intelligence.management_quality.investor_sections import build_investor_sections
        fp = _make_minimal_fp()
        sections = build_investor_sections(fp)
        wms_text = " ".join(str(x) for x in sections["what_management_says"])
        # At least one future commitment should appear
        has_future = any(term in wms_text for term in ["By 2025", "By 2030", "H1CY24", "2025", "2030"])
        assert has_future, f"No future-facing commitment in what_management_says: {wms_text[:200]}"


# ── M50-09..12: assembler_v4 LLM override block ───────────────────────────────

class TestAssemblerV4LLMOverrideBlocked:
    def test_m50_09_llm_section_override_blocked_flag(self):
        """M50-09: assemble_management_answer_v4 sets _llm_section_override_blocked=True."""
        from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4, LLM_SECTION_OVERRIDE_BLOCKED
        assert LLM_SECTION_OVERRIDE_BLOCKED is True
        fp = _make_minimal_fp()
        result = assemble_management_answer_v4(fp)
        assert result["_llm_section_override_blocked"] is True

    def test_m50_10_llm_cannot_override_what_evidence_shows(self):
        """M50-10: LLM what_evidence_shows is ignored; deterministic version used."""
        from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4
        from intelligence.management_quality.investor_sections import build_investor_sections
        fp = _make_minimal_fp()
        det_wes = build_investor_sections(fp)["what_evidence_shows"]
        # LLM provides "better" looking evidence — should still be ignored
        llm_prose = {"what_evidence_shows": ["LLM-generated fake evidence A", "LLM-generated fake evidence B", "LLM-generated fake evidence C"]}
        result = assemble_management_answer_v4(fp, llm_prose)
        assert result["what_evidence_shows"] == det_wes, \
            "LLM overrode what_evidence_shows — V4 invariant violated"

    def test_m50_11_llm_cannot_override_what_management_says(self):
        """M50-11: LLM what_management_says is ignored; deterministic version used."""
        from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4
        from intelligence.management_quality.investor_sections import build_investor_sections
        fp = _make_minimal_fp()
        det_wms = build_investor_sections(fp)["what_management_says"]
        llm_prose = {"what_management_says": ["LLM management summary 1", "LLM management summary 2"]}
        result = assemble_management_answer_v4(fp, llm_prose)
        assert result["what_management_says"] == det_wms, \
            "LLM overrode what_management_says — V4 invariant violated"

    def test_m50_12_llm_cannot_override_consistency_map(self):
        """M50-12: LLM management_consistency_map is ignored; deterministic version used."""
        from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4
        from intelligence.management_quality.investor_sections import build_investor_sections
        fp = _make_minimal_fp()
        det_map = build_investor_sections(fp)["management_consistency_map"]
        llm_prose = {"management_consistency_map": {"execution_discipline": "LLM_SAID_STRONG"}}
        result = assemble_management_answer_v4(fp, llm_prose)
        assert result["management_consistency_map"] == det_map, \
            "LLM overrode management_consistency_map — V4 invariant violated"


# ── M50-13..16: assembler_v4 temporal protection ─────────────────────────────

class TestAssemblerV4TemporalProtection:
    def test_m50_13_deterministic_simple_answer_uses_confirmed_not_projected(self):
        """M50-13: deterministic simple_answer uses 'confirmed' not 'projected' for actual revenue."""
        from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4
        fp = _make_minimal_fp()
        result = assemble_management_answer_v4(fp)
        sa = result["simple_answer"].lower()
        assert "confirmed" in sa or "actual" in sa, \
            f"simple_answer doesn't say confirmed/actual: {result['simple_answer'][:200]}"
        # Must not call confirmed revenue 'projected'
        assert not re.search(r"projected\s+(?:revenue|earnings|profit|pat)", sa), \
            f"simple_answer uses 'projected' for confirmed data: {result['simple_answer'][:200]}"

    def test_m50_14_llm_simple_answer_rejected_if_temporal_mismatch(self):
        """M50-14: LLM simple_answer using 'projected revenue ₹X cr' is rejected."""
        from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4
        from intelligence.management_quality.assembler_v4 import _build_deterministic_simple_answer
        fp = _make_minimal_fp()
        llm_prose = {
            "simple_answer": (
                "FOLLOW_THROUGH_LARGELY_UNVERIFIED delivery pattern. "
                "Projected revenue ₹50,102 cr confirms scale. "
            )
        }
        result = assemble_management_answer_v4(fp, llm_prose)
        det_sa = _build_deterministic_simple_answer(fp)
        assert result["simple_answer"] == det_sa, \
            "LLM simple_answer with 'projected revenue ₹X cr' should be rejected; got: " + result["simple_answer"][:100]

    def test_m50_15_llm_wmme_rejected_if_temporal_mismatch(self):
        """M50-15: LLM what_may_mean_economically with 'projected revenue ₹X cr' is rejected."""
        from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4
        fp = _make_minimal_fp()
        llm_prose = {
            "what_may_mean_economically": "These projected revenue ₹50,102 cr figures suggest scale."
        }
        result = assemble_management_answer_v4(fp, llm_prose)
        # Should fall back to deterministic
        assert "projected revenue" not in result["what_may_mean_economically"].lower() or \
               "confirmed" in result["what_may_mean_economically"].lower(), \
            "what_may_mean_economically uses 'projected revenue' for confirmed data"

    def test_m50_16_deterministic_economic_context_labels_data_confirmed(self):
        """M50-16: deterministic what_may_mean_economically says 'confirmed' not 'projected'."""
        from intelligence.management_quality.assembler_v4 import _build_deterministic_economic_context
        fp = _make_minimal_fp()
        wmme = _build_deterministic_economic_context(fp)
        assert "confirmed" in wmme.lower(), \
            f"deterministic economic context doesn't say 'confirmed': {wmme[:200]}"
        assert "projected" not in wmme.lower() or "not projected" in wmme.lower(), \
            f"deterministic economic context uses 'projected': {wmme[:200]}"


# ── M50-17..19: assembler_v4 rating language gate ─────────────────────────────

class TestAssemblerV4RatingGate:
    def test_m50_17_deterministic_key_points_omit_rating_language(self):
        """M50-17: deterministic key_points omit 'management quality is weak' language."""
        from intelligence.management_quality.assembler_v4 import _build_deterministic_key_points
        from intelligence.management_quality.rating_quarantine import contains_rating_language
        fp = _make_minimal_fp()
        points = _build_deterministic_key_points(fp)
        for point in points:
            assert not contains_rating_language(point), \
                f"Rating language in key_point: {repr(point)}"

    def test_m50_18_llm_simple_answer_rejected_if_rating_language(self):
        """M50-18: LLM simple_answer containing 'management quality is weak' is rejected."""
        from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4
        from intelligence.management_quality.assembler_v4 import _build_deterministic_simple_answer
        fp = _make_minimal_fp()
        llm_prose = {
            "simple_answer": (
                "FOLLOW_THROUGH_LARGELY_UNVERIFIED pattern. "
                "Management quality is weak and trajectory is stable."
            )
        }
        result = assemble_management_answer_v4(fp, llm_prose)
        det_sa = _build_deterministic_simple_answer(fp)
        assert result["simple_answer"] == det_sa, \
            "LLM simple_answer with rating language should be rejected"

    def test_m50_19_full_assembly_no_rating_violations(self):
        """M50-19: assemble_management_answer_v4 output has no rating violations."""
        from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4
        from intelligence.management_quality.rating_quarantine import scan_answer_for_rating_violations
        fp = _make_minimal_fp()
        result = assemble_management_answer_v4(fp)
        violations = scan_answer_for_rating_violations(result)
        assert violations == [], f"Rating violations in assembled answer: {violations}"


# ── M50-20..22: EIV v2 new quality rules ──────────────────────────────────────

class TestEIVV2NewRules:
    def test_m50_20_mq_17_generic_evidence_fails_generic_items(self):
        """M50-20: EIV-MQ-17 fails when all what_evidence_shows items are generic."""
        from intelligence.external_investor_value_validator_v2 import _eiv_mq_17_generic_evidence_detection
        answer = {"what_evidence_shows": [
            "Management demonstrated strong operational improvements.",
            "The company showed execution capabilities.",
        ]}
        result = _eiv_mq_17_generic_evidence_detection(answer)
        assert result["result"] == "FAIL", f"Expected FAIL for generic evidence: {result}"
        assert result["severity"] == "MEDIUM"

    def test_m50_21_mq_18_internal_label_fails_industry_outlook(self):
        """M50-21: EIV-MQ-18 fails when what_to_monitor contains 'Industry_outlook'."""
        from intelligence.external_investor_value_validator_v2 import _eiv_mq_18_internal_label_sanitization
        answer = {"what_to_monitor": [
            "Industry_outlook",
            "acquisition",
            "MC-0029 (By 2025): Carbon neutrality target",
        ]}
        result = _eiv_mq_18_internal_label_sanitization(answer)
        assert result["result"] == "FAIL", f"Expected FAIL for internal labels: {result}"
        assert result["severity"] == "HIGH"
        assert "Industry_outlook" in result["reason"]

    def test_m50_22_mq_19_temporal_fails_projected_confirmed_revenue(self):
        """M50-22: EIV-MQ-19 fails when confirmed revenue is described as projected."""
        from intelligence.external_investor_value_validator_v2 import _eiv_mq_19_temporal_status_accuracy
        answer = {
            "simple_answer": (
                "Projected revenue ₹50,102 cr and PAT ₹9,820 cr suggest strong fundamentals. "
                "FOLLOW_THROUGH_LARGELY_UNVERIFIED pattern."
            )
        }
        result = _eiv_mq_19_temporal_status_accuracy(answer)
        assert result["result"] == "FAIL", f"Expected FAIL for projected confirmed revenue: {result}"
        assert result["severity"] == "HIGH"


# ── M50-23: contract V4 fingerprint stable ────────────────────────────────────

class TestContractV4:
    def test_m50_23_contract_v4_fingerprint_deterministic(self):
        """M50-23: Contract V4 fingerprint is deterministic and non-empty."""
        from intelligence.management_quality.contract_manifest import (
            compute_contract_v4_fingerprint,
            CONTRACT_V4_POLICY_DIGEST,
        )
        fp1 = compute_contract_v4_fingerprint()
        fp2 = compute_contract_v4_fingerprint()
        assert fp1 == fp2, "Contract V4 fingerprint not deterministic"
        assert fp1.startswith("sha256:"), "Contract V4 fingerprint format unexpected"
        assert len(fp1) == 71, f"Unexpected fingerprint length: {len(fp1)}"
        assert fp1 == CONTRACT_V4_POLICY_DIGEST, "MODULE_LEVEL constant differs from computed"


# ── M50-24: fact_pack_v2 new fields ──────────────────────────────────────────

class TestFactPackV2NewFields:
    def test_m50_24_fact_pack_v2_exposes_m50_fields(self):
        """M50-24: build_management_quality_fact_pack_v2 returns evidence_observations_raw, latest_fy, evidence_period_range."""
        from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
        # Use sun_pharma (the canonical test company for this unit)
        fp = build_management_quality_fact_pack_v2("sun_pharma")
        assert "evidence_observations_raw" in fp, "Missing evidence_observations_raw"
        assert isinstance(fp["evidence_observations_raw"], list), "evidence_observations_raw not a list"
        assert "latest_fy" in fp, "Missing latest_fy"
        assert isinstance(fp["latest_fy"], int), f"latest_fy not int: {fp['latest_fy']}"
        assert "evidence_period_range" in fp, "Missing evidence_period_range"
        assert isinstance(fp["evidence_period_range"], str), "evidence_period_range not a str"
