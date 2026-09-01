"""P3 investor-coverage and depth tests.

Tests cover:
- P3A: Capital allocation intelligence (new builder, bucket-level key points)
- P3B: Management delivery specifics (promise types, overdue, delivered, missed)
- P3C: Committee synthesis exposure (direction, agreements, disagreements)
- P3D: Regulatory risk active themes + working capital longitudinal
- P3E: Make-money revenue mechanism differentiation
- P3F: Rendering leak fixes (break-thesis strip, gate G5 patterns)
- Regression sentinels: P2 gates still green, QUESTION_CATALOG extended

All tests use generic fixtures or live generated output (no company-specific rules in helpers).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from intelligence.ask_intrinsiciq.answer_cards import (
    ANSWER_BUILDERS,
    QUESTION_CATALOG,
    QUESTION_INDEX,
    _strip_backend_phrasing,
    _synthesize_longitudinal_series,
)
from intelligence.ask_intrinsiciq.answer_gates import validate_answer_cards


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _answer(
    question_id: str = "what-would-buffett-focus-on",
    status: str = "supported",
    simple_answer: str = "Generic answer.",
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


# ── P3A: Capital allocation ────────────────────────────────────────────────────

def test_capital_allocation_builder_registered():
    assert "how-is-capital-allocated" in ANSWER_BUILDERS
    assert "what-is-the-return-on-capex" in ANSWER_BUILDERS


def test_capital_allocation_question_in_catalog():
    all_ids = {q["id"] for cat in QUESTION_CATALOG for q in cat["questions"]}
    assert "how-is-capital-allocated" in all_ids
    assert "what-is-the-return-on-capex" in all_ids


def test_capital_allocation_different_from_progression_builder():
    from intelligence.ask_intrinsiciq.answer_cards import _build_capital_allocation_answer, _build_canonical_progression_answer
    assert _build_capital_allocation_answer is not _build_canonical_progression_answer


# ── P3B: Management delivery specifics ────────────────────────────────────────

def test_promise_type_builders_registered():
    for qid in ["what-promise-types-dominate", "which-promises-are-overdue", "what-was-delivered-last-3-years", "what-was-missed"]:
        assert qid in ANSWER_BUILDERS, f"Missing builder: {qid}"


def test_promise_questions_in_catalog():
    all_ids = {q["id"] for cat in QUESTION_CATALOG for q in cat["questions"]}
    for qid in ["what-promise-types-dominate", "which-promises-are-overdue", "what-was-delivered-last-3-years", "what-was-missed"]:
        assert qid in all_ids, f"Missing in catalog: {qid}"


def test_management_delivery_builders_are_distinct():
    from intelligence.ask_intrinsiciq.answer_cards import (
        _build_promise_types_answer,
        _build_overdue_promises_answer,
        _build_delivered_promises_answer,
        _build_missed_promises_answer,
    )
    builders = [_build_promise_types_answer, _build_overdue_promises_answer, _build_delivered_promises_answer, _build_missed_promises_answer]
    assert len(set(id(b) for b in builders)) == 4, "All four delivery builders must be distinct functions"


# ── P3C: Committee synthesis exposure ─────────────────────────────────────────

def test_committee_builders_registered():
    for qid in ["what-is-committee-direction", "where-does-the-committee-agree", "where-does-the-committee-disagree"]:
        assert qid in ANSWER_BUILDERS, f"Missing builder: {qid}"


def test_committee_category_in_catalog():
    categories = {cat["id"] for cat in QUESTION_CATALOG}
    assert "committee-view" in categories, "committee-view category must be in QUESTION_CATALOG"


def test_committee_questions_in_catalog():
    all_ids = {q["id"] for cat in QUESTION_CATALOG for q in cat["questions"]}
    for qid in ["what-is-committee-direction", "where-does-the-committee-agree", "where-does-the-committee-disagree"]:
        assert qid in all_ids, f"Missing in catalog: {qid}"


def test_committee_direction_builder_distinct_from_agree():
    from intelligence.ask_intrinsiciq.answer_cards import _build_committee_direction_answer, _build_committee_agree_answer
    assert _build_committee_direction_answer is not _build_committee_agree_answer


# ── P3D: Regulatory risk + working capital ────────────────────────────────────

def test_regulatory_risks_builder_registered():
    assert "what-regulatory-risks-remain-active" in ANSWER_BUILDERS


def test_regulatory_risks_question_in_catalog():
    all_ids = {q["id"] for cat in QUESTION_CATALOG for q in cat["questions"]}
    assert "what-regulatory-risks-remain-active" in all_ids


def test_working_capital_question_still_registered():
    assert "is-working-capital-a-concern" in ANSWER_BUILDERS


def test_working_capital_not_using_ccc_only():
    # Regression: the builder must not return unavailable when CCC is None but receivable_days exist
    from intelligence.ask_intrinsiciq.answer_cards import _build_working_capital_answer
    sb_mock = {
        "company_slug": "test_co",
        "sources": {
            "working_capital_quality_drilldown": {
                "payload": {
                    "drilldown": [
                        {"fiscal_year": "fy20", "receivable_days": 100.0, "inventory_days": 500.0, "payable_days": 140.0, "cash_conversion_cycle": 460.0, "working_capital_intensity_status": "severe", "cash_strain_risk": "elevated"},
                        {"fiscal_year": "fy24", "receivable_days": 85.0, "inventory_days": None, "payable_days": None, "cash_conversion_cycle": None, "working_capital_intensity_status": "watch", "cash_strain_risk": "watch"},
                        {"fiscal_year": "fy26", "receivable_days": 90.0, "inventory_days": None, "payable_days": None, "cash_conversion_cycle": None, "working_capital_intensity_status": "watch", "cash_strain_risk": "watch"},
                    ]
                },
                "status": "loaded",
            },
            "financial_truth_pack": {"payload": {}, "status": "loaded"},
        },
    }
    result = _build_working_capital_answer(sb_mock, business_journey_payload={}, products_services_payload={}, question={"id": "is-working-capital-a-concern"})
    assert result.get("answer_status") != "unavailable", "Working capital must not degrade to unavailable when receivable_days exist"
    assert "receivable" in str(result.get("simple_answer", "")).lower() or "concern" in str(result.get("simple_answer", "")).lower()


def test_working_capital_longitudinal_trend_detected():
    from intelligence.ask_intrinsiciq.answer_cards import _build_working_capital_answer
    sb_mock = {
        "company_slug": "test_co",
        "sources": {
            "working_capital_quality_drilldown": {
                "payload": {
                    "drilldown": [
                        {"fiscal_year": "fy20", "receivable_days": 120.0, "cash_conversion_cycle": None, "working_capital_intensity_status": "severe", "cash_strain_risk": "elevated"},
                        {"fiscal_year": "fy24", "receivable_days": 80.0, "cash_conversion_cycle": None, "working_capital_intensity_status": "watch", "cash_strain_risk": "watch"},
                    ]
                },
                "status": "loaded",
            },
            "financial_truth_pack": {"payload": {}, "status": "loaded"},
        },
    }
    result = _build_working_capital_answer(sb_mock, business_journey_payload={}, products_services_payload={}, question={"id": "is-working-capital-a-concern"})
    kps = " ".join(result.get("key_points", []))
    # Must mention both years and show the trend
    assert "fy20" in kps.lower() or "FY20" in kps, "Must reference starting year of receivable trend"
    assert "fy24" in kps.lower() or "FY24" in kps, "Must reference ending year of receivable trend"


# ── P3E: Business model differentiation ───────────────────────────────────────

def test_make_money_builder_registered():
    assert "how-does-it-make-money" in ANSWER_BUILDERS


def test_make_money_question_in_catalog():
    all_ids = {q["id"] for cat in QUESTION_CATALOG for q in cat["questions"]}
    assert "how-does-it-make-money" in all_ids
    assert "what-does-company-do" in all_ids


# ── P3F: Rendering leak fixes ─────────────────────────────────────────────────

def test_claim_only_enum_stripped():
    raw = "CLAIM_ONLY; execution remains unproven for this commitment."
    result = _strip_backend_phrasing(raw)
    assert "CLAIM_ONLY" not in result
    assert "execution" in result.lower()


def test_action_started_enum_stripped():
    raw = "ACTION_STARTED, the capex program has begun."
    result = _strip_backend_phrasing(raw)
    assert "ACTION_STARTED" not in result


def test_action_completed_enum_stripped():
    raw = "ACTION_COMPLETED; the facility became operational."
    result = _strip_backend_phrasing(raw)
    assert "ACTION_COMPLETED" not in result


def test_financial_link_enum_stripped():
    raw = "FINANCIAL_LINK_PROVEN, revenue growth confirms the investment thesis."
    result = _strip_backend_phrasing(raw)
    assert "FINANCIAL_LINK" not in result


def test_break_thesis_applies_strip_function():
    # Verify _build_break_thesis_answer uses _strip_backend_phrasing on risk texts
    # by confirming it's referenced in the builder source
    import inspect
    from intelligence.ask_intrinsiciq.answer_cards import _build_break_thesis_answer
    src = inspect.getsource(_build_break_thesis_answer)
    assert "_strip_backend_phrasing" in src, "_build_break_thesis_answer must apply _strip_backend_phrasing to risk texts"


def test_gate_g5_catches_claim_only():
    answer = _answer(
        question_id="what-has-management-promised",
        simple_answer="Management guidance is CLAIM_ONLY; later evidence is pending.",
    )
    result = validate_answer_cards(_payload([answer]))
    g5_failures = [f for f in result["gate_failures"] if f["gate_id"] == "G5"]
    assert g5_failures, "G5 should catch CLAIM_ONLY internal enum"


def test_gate_g5_catches_action_started():
    answer = _answer(
        question_id="how-is-capital-allocated",
        simple_answer="The capex program is ACTION_STARTED per the tracker.",
    )
    result = validate_answer_cards(_payload([answer]))
    g5_failures = [f for f in result["gate_failures"] if f["gate_id"] == "G5"]
    assert g5_failures, "G5 should catch ACTION_STARTED internal enum"


def test_gate_g5_catches_supplied_inputs_phrase():
    answer = _answer(
        question_id="what-is-owner-earnings",
        simple_answer="Owner earnings are derived in the supplied inputs from the bridge.",
    )
    result = validate_answer_cards(_payload([answer]))
    g5_failures = [f for f in result["gate_failures"] if f["gate_id"] == "G5"]
    assert g5_failures, "G5 should catch 'in the supplied inputs' internal phrase"


# ── QUESTION_CATALOG and QUESTION_INDEX consistency ───────────────────────────

def test_question_catalog_extended_to_committee_view():
    categories = {cat["id"]: cat for cat in QUESTION_CATALOG}
    assert "committee-view" in categories
    committee_q_ids = {q["id"] for q in categories["committee-view"]["questions"]}
    assert "what-is-committee-direction" in committee_q_ids
    assert "where-does-the-committee-agree" in committee_q_ids
    assert "where-does-the-committee-disagree" in committee_q_ids


def test_question_index_consistent_with_catalog():
    catalog_ids = {q["id"] for cat in QUESTION_CATALOG for q in cat["questions"]}
    index_ids = set(QUESTION_INDEX.keys())
    assert catalog_ids == index_ids, f"QUESTION_INDEX out of sync. Catalog-only: {catalog_ids - index_ids}, Index-only: {index_ids - catalog_ids}"


def test_all_catalog_questions_have_builders():
    catalog_ids = {q["id"] for cat in QUESTION_CATALOG for q in cat["questions"]}
    missing = [qid for qid in catalog_ids if qid not in ANSWER_BUILDERS]
    assert not missing, f"These catalog questions have no builder: {missing}"


def test_question_count_increased_from_p2():
    # P2 had 25 questions; P3 should have at least 34 (9 new ones added)
    assert len(QUESTION_INDEX) >= 34, f"Expected ≥34 questions after P3, got {len(QUESTION_INDEX)}"


# ── Live generation regression ────────────────────────────────────────────────

def _live_answers() -> Dict[str, Any]:
    """Run the full generation pipeline once and cache for the session."""
    from intelligence.ask_intrinsiciq.generator import generate_ask_intrinsiciq_view
    result = generate_ask_intrinsiciq_view("sun_pharma")
    return {a["question_id"]: a for a in result["answer_cards"].get("answers", [])}


@pytest.fixture(scope="module")
def live_answers():
    return _live_answers()


@pytest.fixture(scope="module")
def live_gate_result(live_answers):
    from intelligence.ask_intrinsiciq.answer_gates import validate_answer_cards
    answers_list = list(live_answers.values())
    return validate_answer_cards({"answers": answers_list})


def test_live_gates_all_pass(live_gate_result):
    assert live_gate_result["passed"], f"Gate failures: {live_gate_result['gate_failures']}"


def test_live_capital_allocation_supported(live_answers):
    a = live_answers.get("how-is-capital-allocated", {})
    assert a.get("answer_status") in ("supported", "partially_supported"), "Capital allocation must be supported"
    simple = a.get("simple_answer", "")
    assert len(simple) > 20, "Capital allocation simple_answer must have real content"


def test_live_promise_types_supported(live_answers):
    a = live_answers.get("what-promise-types-dominate", {})
    assert a.get("answer_status") in ("supported", "partially_supported")
    kps = a.get("key_points", [])
    assert len(kps) >= 2, "Promise types must have at least 2 key points"


def test_live_overdue_promises_supported(live_answers):
    a = live_answers.get("which-promises-are-overdue", {})
    assert a.get("answer_status") in ("supported", "partially_supported")


def test_live_delivered_promises_supported(live_answers):
    a = live_answers.get("what-was-delivered-last-3-years", {})
    assert a.get("answer_status") in ("supported", "partially_supported")


def test_live_missed_promises_supported(live_answers):
    a = live_answers.get("what-was-missed", {})
    assert a.get("answer_status") in ("supported", "partially_supported")


def test_live_committee_direction_supported(live_answers):
    a = live_answers.get("what-is-committee-direction", {})
    assert a.get("answer_status") in ("supported", "partially_supported")
    simple = a.get("simple_answer", "")
    assert "weakening" in simple.lower() or "strengthening" in simple.lower() or "neutral" in simple.lower(), "Must reflect actual committee direction"


def test_live_committee_agree_supported(live_answers):
    a = live_answers.get("where-does-the-committee-agree", {})
    assert a.get("answer_status") in ("supported", "partially_supported")
    kps = a.get("key_points", [])
    assert len(kps) >= 1, "Committee agreement must have at least 1 key point"


def test_live_committee_disagree_supported(live_answers):
    a = live_answers.get("where-does-the-committee-disagree", {})
    assert a.get("answer_status") in ("supported", "partially_supported")


def test_live_regulatory_risks_supported(live_answers):
    a = live_answers.get("what-regulatory-risks-remain-active", {})
    assert a.get("answer_status") in ("supported", "partially_supported")
    simple = a.get("simple_answer", "")
    assert len(simple) > 20, "Regulatory risks must have substantive simple_answer"


def test_live_working_capital_now_supported(live_answers):
    a = live_answers.get("is-working-capital-a-concern", {})
    assert a.get("answer_status") == "supported", "Working capital must be supported, not unavailable"
    simple = a.get("simple_answer", "")
    assert "receivable" in simple.lower() or "working-capital" in simple.lower()


def test_live_make_money_has_revenue_content(live_answers):
    a_biz = live_answers.get("what-does-company-do", {})
    a_rev = live_answers.get("how-does-it-make-money", {})
    simple_biz = a_biz.get("simple_answer", "")
    simple_rev = a_rev.get("simple_answer", "")
    # Revenue answer must have distinct content from business description
    assert simple_rev != simple_biz, "how-does-it-make-money simple_answer must differ from what-does-company-do"


def test_live_capex_return_partially_supported(live_answers):
    a = live_answers.get("what-is-the-return-on-capex", {})
    assert a.get("answer_status") in ("supported", "partially_supported")
    simple = a.get("simple_answer", "")
    assert "capex" in simple.lower() or "₹" in simple or "return" in simple.lower()


def test_live_break_thesis_no_internal_phrases(live_answers):
    a = live_answers.get("what-can-break-the-thesis", {})
    all_text = " ".join([
        a.get("simple_answer", ""),
        *a.get("key_points", []),
        a.get("detailed_explanation", ""),
    ])
    assert "CLAIM_ONLY" not in all_text
    assert "from supplied evidence" not in all_text.lower()
    assert "in the supplied inputs" not in all_text.lower()


def test_live_answer_count_at_least_34(live_answers):
    assert len(live_answers) >= 34, f"Expected ≥34 answers, got {len(live_answers)}"
