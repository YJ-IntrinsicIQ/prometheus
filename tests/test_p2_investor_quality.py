"""P2 investor-surface quality tests.

Tests cover:
- Per-share longitudinal synthesis
- Project temporal integrity
- Buffett language gates
- Pre-save answer gates (G2, G3, G5, G6, G7, G8, G9)
- Management P1 regression sentinels
- P0 routing regression sentinels

All tests use generic (non-company-specific) fixtures.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import pytest

from intelligence.ask_intrinsiciq.answer_cards import (
    _synthesize_longitudinal_series,
    _strip_backend_phrasing,
    _project_is_active,
    _project_recency_cutoff,
    format_per_share,
)
from intelligence.ask_intrinsiciq.answer_gates import validate_answer_cards


# ── Helpers ──────────────────────────────────────────────────────────────────

def _record(fy: str, eps: Optional[float], owner_eps: Optional[float] = None) -> Dict[str, Any]:
    return {"fiscal_year": fy, "eps_basic": eps, "owner_earnings_per_share": owner_eps}


def _assessment(exec_status: str, evidence_periods: List[str], period: str = "") -> Dict[str, Any]:
    return {"execution_status": exec_status, "evidence_periods": evidence_periods, "period": period}


def _answer(
    question_id: str = "what-would-buffett-focus-on",
    status: str = "supported",
    simple_answer: str = "Generic statement.",
    key_points: Optional[List[str]] = None,
    sections: Optional[List[Dict[str, Any]]] = None,
    interpretation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "question_id": question_id,
        "answer_status": status,
        "simple_answer": simple_answer,
        "key_points": key_points or [],
        "structured_sections": sections or [],
        "interpretation": interpretation or {},
        "evidence_points": [],
    }


def _payload(answers: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"answers": answers}


# ── Test 1: 7-year EPS series generates longitudinal synthesis ───────────────

def test_seven_year_eps_generates_longitudinal_synthesis():
    series = [_record(f"fy{y}", 10.0 + y) for y in range(20, 27)]
    result = _synthesize_longitudinal_series(series, "eps_basic", "EPS")
    assert result["available"] is True
    assert result["n_years"] == 7
    assert result["start_year"] == "fy20"
    assert result["end_year"] == "fy26"
    assert result["direction"] == "up"
    assert result["narrative"] != ""
    assert "fy20" in result["narrative"].upper() or "FY20" in result["narrative"]


# ── Test 2: Inflection year is detected ────────────────────────────────────

def test_inflection_year_detected():
    # EPS flat for 4 years, then jumps massively in one year
    series = [
        _record("fy20", 10.0),
        _record("fy21", 10.5),
        _record("fy22", 11.0),
        _record("fy23", 11.5),
        _record("fy24", 35.0),  # Major jump
        _record("fy25", 37.0),
    ]
    result = _synthesize_longitudinal_series(series, "eps_basic", "EPS")
    assert result["inflection_year"] is not None
    assert result["inflection_year"] == "fy24"


# ── Test 3: Volatile series is not called "improving" without caveat ─────────

def test_volatile_series_not_oversimplified():
    series = [
        _record("fy20", 20.0),
        _record("fy21", 5.0),   # sharp drop
        _record("fy22", 25.0),  # sharp recovery
        _record("fy23", 8.0),   # sharp drop again
        _record("fy24", 30.0),  # sharp recovery
        _record("fy25", 10.0),  # drop
    ]
    result = _synthesize_longitudinal_series(series, "eps_basic", "EPS")
    assert result["is_volatile"] is True
    assert result["direction"] == "volatile"
    assert "volatile" in result["narrative"].lower()


# ── Test 4: Missing years handled conservatively ─────────────────────────────

def test_missing_years_handled_conservatively():
    series = [
        _record("fy20", 15.0),
        _record("fy21", None),   # missing
        _record("fy22", 18.0),
        _record("fy23", None),   # missing
        _record("fy24", 22.0),
    ]
    result = _synthesize_longitudinal_series(series, "eps_basic", "EPS")
    assert result["available"] is True
    assert result["data_confidence"] == "low"
    assert result["n_years"] == 3  # only non-None values counted


# ── Test 5: Active project requires temporal support ─────────────────────────

def test_active_project_requires_temporal_support():
    # No evidence periods → cannot confirm active
    assessment = _assessment("operational", evidence_periods=[], period="")
    assert _project_is_active(assessment, recency_cutoff=23) is False


# ── Test 6: Historical project excluded from active list ─────────────────────

def test_historical_project_excluded():
    # Operational but all evidence is fy14 — well before recency cutoff of fy23
    assessment = _assessment("operational", evidence_periods=["fy14"], period="fy14")
    cutoff = _project_recency_cutoff("fy26", years_back=3)  # fy23
    assert _project_is_active(assessment, recency_cutoff=cutoff) is False


# ── Test 7: Old-but-reconfirmed project can remain active ────────────────────

def test_old_but_reconfirmed_project_active():
    # Operational, started in fy19, but has fy25 evidence → recent enough
    assessment = _assessment("operational", evidence_periods=["fy19", "fy25"], period="fy25")
    cutoff = _project_recency_cutoff("fy26", years_back=3)  # fy23
    assert _project_is_active(assessment, recency_cutoff=cutoff) is True


# ── Test 8: Completed project not shown as underway ──────────────────────────

def test_completed_project_not_underway():
    assessment = _assessment("completed", evidence_periods=["fy24", "fy25"], period="fy25")
    cutoff = _project_recency_cutoff("fy26", years_back=3)
    assert _project_is_active(assessment, recency_cutoff=cutoff) is False


# ── Test 9: Blank-year unable_to_verify project excluded ─────────────────────

def test_blank_year_unable_to_verify_excluded():
    assessment = _assessment("unable_to_verify", evidence_periods=[], period="")
    assert _project_is_active(assessment, recency_cutoff=23) is False


# ── Test 10: Unrelated evidence cannot make a superseded project active ───────

def test_superseded_project_excluded_regardless_of_evidence():
    assessment = _assessment("superseded", evidence_periods=["fy25", "fy26"], period="fy26")
    cutoff = _project_recency_cutoff("fy26", years_back=3)
    assert _project_is_active(assessment, recency_cutoff=cutoff) is False


# ── Test 11: Internal template language is stripped ──────────────────────────

def test_template_prefix_stripped():
    raw = "investment lens implication first: A true moat must generate repeatable owner returns."
    result = _strip_backend_phrasing(raw)
    assert "investment lens implication first" not in result.lower()
    assert "moat" in result.lower()


# ── Test 12: Claim evidence only phrase is stripped ──────────────────────────

def test_claim_evidence_only_stripped():
    raw = "Grow each business faster than the market; is claim evidence only; execution remains unproven."
    result = _strip_backend_phrasing(raw)
    assert "claim evidence only" not in result.lower()
    assert "execution" in result.lower()


# ── Test 13: Truncated text marker is stripped ──────────────────────────────

def test_truncated_text_artifact_stripped():
    raw = "Expand capacity in the new m.. is a strategic priority."
    result = _strip_backend_phrasing(raw)
    assert "m.." not in result


# ── Test 14: Internal IDs blocked by G6 gate ─────────────────────────────────

def test_gate_g6_blocks_internal_ids():
    answer = _answer(
        simple_answer="Based on sun_pharma data, the economics are improving.",
        key_points=["Revenue grew 15% per year."],
    )
    result = validate_answer_cards(_payload([answer]))
    g6_failures = [f for f in result["gate_failures"] if f["gate_id"] == "G6"]
    assert g6_failures, "G6 should fail when internal ID like sun_pharma appears"


# ── Test 15: Contradiction between FCF unavailable and FCF value caught ───────

def test_gate_g7_catches_fcf_contradiction():
    answer = _answer(
        simple_answer="FCF cannot be assessed from available data.",
        key_points=["FCF per share is ₹12.50 per share for the latest year."],
    )
    result = validate_answer_cards(_payload([answer]))
    g7_failures = [f for f in result["gate_failures"] if f["gate_id"] == "G7"]
    assert g7_failures, "G7 should catch FCF contradiction"


# ── Test 16: Empty semantic section omitted/degraded by G8 ───────────────────

def test_gate_g8_catches_empty_section():
    answer = _answer(
        sections=[
            {"title": "What he may like", "points": ["Specialised business with scale."]},
            {"title": "Economic Mechanism", "points": []},  # empty
        ],
    )
    result = validate_answer_cards(_payload([answer]))
    g8_failures = [f for f in result["gate_failures"] if f["gate_id"] == "G8"]
    assert g8_failures, "G8 should flag empty section"


# ── Test 17: Decision-usefulness gate works for analytical answers ────────────

def test_gate_g9_requires_concrete_content_in_buffett_answer():
    answer = _answer(
        question_id="what-would-buffett-focus-on",
        simple_answer="Buffett would consider the overall business dynamics and think about long-term value.",
        key_points=["The business has some strengths.", "There are certain concerns."],
    )
    result = validate_answer_cards(_payload([answer]))
    g9_failures = [f for f in result["gate_failures"] if f["gate_id"] == "G9"]
    assert g9_failures, "G9 should flag generic Buffett answer without concrete metrics"


def test_gate_g9_passes_when_concrete_metric_present():
    answer = _answer(
        question_id="what-would-buffett-focus-on",
        simple_answer="Buffett would focus on owner earnings quality and FCF conversion.",
        key_points=["Receivable days at 89 days warrants attention.", "ROE is 14.7% — adequate but not exceptional."],
    )
    result = validate_answer_cards(_payload([answer]))
    g9_failures = [f for f in result["gate_failures"] if f["gate_id"] == "G9"]
    assert not g9_failures, "G9 should pass when concrete metrics like receivable days are present"


# ── Test 18: Management P1 answers unaffected (regression sentinel) ───────────

def test_management_answer_not_blocked_by_gates():
    answer = _answer(
        question_id="what-has-management-promised",
        simple_answer="Management has tracked 13 commitments. 1 partially delivered, 11 unverified.",
        key_points=[
            "Product launch programme — In Progress since FY20 with 39 evidence items.",
            "Business expansion commitment — Unable To Verify with 4 evidence items.",
        ],
    )
    result = validate_answer_cards(_payload([answer]))
    # Management answers should not be blocked by G5/G6/G9 for this content
    blocking = [f for f in result["gate_failures"] if f.get("action") == "BLOCK_CARD"]
    assert not blocking, f"Management P1 answers should not be blocked: {blocking}"


# ── Test 19: P0 routing question is not affected by G9 (factual, not analytical)

def test_gate_g9_does_not_apply_to_factual_questions():
    answer = _answer(
        question_id="what-does-company-do",
        simple_answer="The company manufactures and sells generic and specialty pharmaceutical products.",
        key_points=["Generics: sold globally.", "Specialty: regulated markets."],
    )
    result = validate_answer_cards(_payload([answer]))
    g9_failures = [f for f in result["gate_failures"] if f["gate_id"] == "G9"]
    assert not g9_failures, "G9 must not apply to factual non-analytical questions"


# ── Test 20: G2 fails when answer claims snapshot-only despite multi-year data ─

def test_gate_g2_fails_when_snapshot_claimed_with_multi_year_data():
    answer = _answer(
        question_id="are-per-share-economics-improving",
        simple_answer="The current evidence gives a current-year snapshot only and does not support a multi-year improvement claim.",
        key_points=["EPS in FY20 was ₹15.70 per share.", "EPS in FY26 was ₹47.80 per share."],
    )
    result = validate_answer_cards(_payload([answer]))
    g2_failures = [f for f in result["gate_failures"] if f["gate_id"] == "G2"]
    assert g2_failures, "G2 should fail when snapshot-only is claimed but two years are cited"


# ── Test 21: No company-specific logic in synthesis function ─────────────────

def test_synthesis_function_generic_no_company_terms():
    # Use completely generic, non-pharma series
    series = [
        _record("fy18", 5.0),
        _record("fy19", 6.0),
        _record("fy20", 7.5),
        _record("fy21", 9.0),
        _record("fy22", 11.0),
    ]
    result = _synthesize_longitudinal_series(series, "eps_basic", "Basic EPS")
    assert result["available"] is True
    assert result["direction"] == "up"
    # CAGR should be computed and positive
    assert result["cagr"] is not None
    assert result["cagr"] > 0
    # Verify CAGR is mathematically correct: (11/5)^(1/4) - 1
    expected_cagr = (math.pow(11.0 / 5.0, 1.0 / 4.0) - 1.0) * 100
    assert abs(result["cagr"] - expected_cagr) < 0.01


# ── Test 22: No sector-specific temporal hacks in project filter ─────────────

def test_project_filter_generic_no_sector_terms():
    # Simulate a non-pharma project that is operational with recent evidence
    assessment = _assessment("operational", evidence_periods=["fy24", "fy25"], period="fy25")
    cutoff = _project_recency_cutoff("fy26", years_back=3)
    assert _project_is_active(assessment, recency_cutoff=cutoff) is True

    # Simulate a non-pharma project that is old and has no recent evidence
    old_assessment = _assessment("operational", evidence_periods=["fy18"], period="fy18")
    assert _project_is_active(old_assessment, recency_cutoff=cutoff) is False
