from __future__ import annotations

from intelligence.ask_intrinsiciq.answer_cards import QUESTION_CATALOG
from intelligence.ask_intrinsiciq.validator import _canonical_question_ids


def test_ask_validator_question_catalog_uses_canonical_answer_catalog():
    catalog_ids = {q["id"] for cat in QUESTION_CATALOG for q in cat["questions"]}
    validator_ids = set(_canonical_question_ids())

    assert validator_ids == catalog_ids
    assert "what-promise-types-dominate" in validator_ids
    assert "which-promises-are-overdue" in validator_ids
    assert "what-was-delivered-last-3-years" in validator_ids
    assert "what-is-the-return-on-capex" in validator_ids
    assert "where-does-the-committee-disagree" in validator_ids
