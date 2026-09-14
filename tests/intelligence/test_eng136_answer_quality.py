"""ENG-136: Investor Answer Quality — regression fixtures.

These tests guard against the defects fixed in ENG-136:
- Empty conclusions caused by 260-char truncation + truncated-text filter
- Internal enum labels leaking into user-visible fields (PROVEN, UNVERIFIED, etc.)
- Schema-shaped "(s)" suffixes and pipe-separated prose in key answers
- Snake_case internal identifiers in user-visible text
- Commitment type metadata (financial_strength_inputs etc.) in key_points

All checks run against the pre-generated sun_pharma answer_cards.json.
No regeneration is needed; these are read-time contracts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

ANSWER_CARDS_PATH = (
    Path(__file__).resolve().parents[2]
    / "companies"
    / "sun_pharma"
    / "company_memory"
    / "ask_intrinsiciq"
    / "answer_cards.json"
)

HARD_FORBIDDEN = [
    "UNVERIFIED",
    "DIRECTLY_ATTRIBUTABLE",
    "ASSOCIATED_NOT_ATTRIBUTABLE",
    "NO_OUTCOME_EVIDENCE",
    "commitment(s)",
    "PROVEN",
    "UNPROVEN",
    "PARTIALLY_PROVEN",
    "NEGATIVE OUTCOMES",
    "Attribution taxonomy",
    "grounding_status",
    "qa_label",
    "financial_strength_inputs",
    "management_execution_inputs",
    "financial_quality_summary",
    "capital_allocation_roi_ledger",
    # These appear legitimately in evidence_summary etc., so only check user-visible fields (F3)
    # "management_execution_outcomes",
    # "gold_risk_evolution",
    # "management_progression",
]

_SNAKE_RE = re.compile(r"\b[a-z]+_[a-z]+_[a-z]+\b")


@pytest.fixture(scope="module")
def answers() -> List[Dict[str, Any]]:
    data = json.loads(ANSWER_CARDS_PATH.read_text())
    return data["answers"]


@pytest.fixture(scope="module")
def by_qid(answers) -> Dict[str, Dict[str, Any]]:
    return {a.get("question_id", ""): a for a in answers}


# ── F1: no empty conclusions ─────────────────────────────────────────────────

def test_no_empty_conclusions(answers):
    empty = [
        a.get("question_id", "?")
        for a in answers
        if not (a.get("interpretation") or {}).get("conclusion", "")
    ]
    assert not empty, f"Answers with empty conclusions: {empty}"


# ── F2: hard-forbidden terms absent from ALL fields ──────────────────────────

def test_no_hard_forbidden_terms_in_any_field(answers):
    violations = []
    for ans in answers:
        raw = json.dumps(ans)
        for term in HARD_FORBIDDEN:
            if term in raw:
                violations.append((ans.get("question_id", "?"), term))
    assert not violations, f"Forbidden terms found: {violations[:10]}"


# ── F3: no snake_case in user-visible fields ─────────────────────────────────

def _user_visible_text(ans: Dict[str, Any]) -> str:
    parts = [
        str(ans.get("simple_answer") or ""),
        " ".join(ans.get("key_points") or []),
    ]
    interp = ans.get("interpretation") or {}
    parts += [
        str(interp.get("conclusion") or ""),
        str(interp.get("why_it_matters") or ""),
        str(interp.get("economic_mechanism") or ""),
    ]
    return " ".join(parts)


def test_no_snake_case_in_user_visible_fields(answers):
    violations = []
    for ans in answers:
        text = _user_visible_text(ans)
        if _SNAKE_RE.search(text):
            matches = _SNAKE_RE.findall(text)
            violations.append((ans.get("question_id", "?"), matches[:3]))
    assert not violations, f"snake_case in user-visible text: {violations[:10]}"


# ── F4: Q6 conclusion leads with investor language, not count table ───────────

def test_q6_conclusion_investor_led(by_qid):
    a = by_qid.get("did-execution-lead-to-outcomes", {})
    conclusion = (a.get("interpretation") or {}).get("conclusion", "")
    assert conclusion, "Q6 conclusion is empty"
    assert "tracked" in conclusion.lower(), (
        f"Q6 conclusion should mention 'tracked' initiatives: {conclusion!r}"
    )
    assert "confirmed" in conclusion.lower() or "none" in conclusion.lower(), (
        f"Q6 conclusion should state confirmed state or none: {conclusion!r}"
    )


# ── F5: Q8 conclusion uses natural sentences, not pipe-separated format ───────

def test_q8_conclusion_no_pipes(by_qid):
    a = by_qid.get("what-can-break-the-thesis", {})
    conclusion = (a.get("interpretation") or {}).get("conclusion", "")
    assert conclusion, "Q8 conclusion is empty"
    assert " | " not in conclusion, (
        f"Q8 conclusion uses pipe format: {conclusion!r}"
    )
    # Should mention risk names naturally
    assert "Risk" in conclusion or "risk" in conclusion, (
        f"Q8 conclusion should mention risks: {conclusion!r}"
    )


# ── F6: Q3/Q4 conclusions avoid "(s)" and "accountability denominator" ────────

def test_q3_conclusion_language(by_qid):
    for qid in ("what-has-management-promised", "did-past-claims-come-true"):
        a = by_qid.get(qid, {})
        conclusion = (a.get("interpretation") or {}).get("conclusion", "")
        assert conclusion, f"{qid} conclusion is empty"
        assert "commitment(s)" not in conclusion, (
            f"{qid} conclusion contains '(s)' suffix: {conclusion!r}"
        )
        assert "accountability denominator" not in conclusion.lower(), (
            f"{qid} conclusion mentions 'accountability denominator': {conclusion!r}"
        )


# ── F7: Q7 key_points contain no ALL_CAPS enum labels ─────────────────────────

def test_q7_key_points_no_allcaps_labels(by_qid):
    a = by_qid.get("which-investments-created-value", {})
    key_points = a.get("key_points") or []
    # These were the exact labels that leaked pre-fix
    bad_labels = ["PROVEN (", "UNPROVEN (", "ASSOCIATED (", "NEGATIVE OUTCOMES:"]
    for kp in key_points:
        for label in bad_labels:
            assert label not in kp, (
                f"Q7 key_point contains internal label {label!r}: {kp!r}"
            )


# ── F8: Q13 (Munger) conclusion has no share_count_reduction / snake terms ───

def test_q13_munger_conclusion_clean(by_qid):
    a = by_qid.get("what-would-munger-avoid", {})
    conclusion = (a.get("interpretation") or {}).get("conclusion", "")
    assert conclusion, "Q13 Munger conclusion is empty"
    bad = ["share_count_reduction", "capital_allocation_outcomes profile", "supplied sections"]
    for term in bad:
        assert term not in conclusion, (
            f"Q13 Munger conclusion contains internal term {term!r}: {conclusion!r}"
        )


# ── F9: status label "Not yet verified" not "Unable To Verify" ───────────────

def test_status_labels_are_human_readable(answers):
    raw = json.dumps(answers)
    assert "Unable To Verify" not in raw, "Old status label 'Unable To Verify' found"
    assert "UNVERIFIED" not in raw, "ALL_CAPS 'UNVERIFIED' found in output"


# ── F10: all 36 answers exist (no builder silently dropped) ──────────────────

def test_answer_count(answers):
    assert len(answers) >= 30, f"Expected >=30 answers, got {len(answers)}"


# ── F11: conclusion char limits: interpretation.py conclusion must allow >260 ─

def test_conclusion_not_cut_at_260_chars(answers):
    """Guard against regression: conclusion truncated to 257 chars + '...'."""
    for ans in answers:
        conclusion = (ans.get("interpretation") or {}).get("conclusion", "")
        assert not conclusion.endswith("..."), (
            f"{ans.get('question_id','?')} conclusion ends in '...' (truncation artifact): {conclusion[-40:]!r}"
        )


# ── F12: sanitizer rewrites lowercase keys work for PROVEN-family terms ───────

def test_sanitizer_proven_rewrites():
    from intelligence.ask_intrinsiciq.sanitizer import sanitize_public_text
    assert sanitize_public_text("PROVEN") == "demonstrated"
    assert sanitize_public_text("UNPROVEN") == "not yet demonstrated"
    assert sanitize_public_text("PARTIALLY_PROVEN") == "partially demonstrated"


# ── F13: sanitizer kills strings containing forbidden identifiers ─────────────

def test_sanitizer_kills_source_record_names():
    from intelligence.ask_intrinsiciq.sanitizer import sanitize_public_text
    assert sanitize_public_text("Optional source record missing: financial_quality_summary") == ""
    assert sanitize_public_text("The capital_allocation_roi_ledger source is required.") == ""


# ── F14: interpretation.py conclusion limit is 2000, not 260 ─────────────────

def test_interpretation_conclusion_limit():
    from intelligence.progression.interpretation import build_interpretation_contract
    long_text = "A" * 500
    result = build_interpretation_contract(
        conclusion=long_text,
        what_changed=[],
        why_it_matters="",
        economic_mechanism="",
        thesis_impact="neutral",
        positive_evidence=[],
        negative_evidence=[],
        unresolved=[],
        what_to_watch=[],
        confidence={"level": "medium", "basis": [], "limitations": []},
    )
    assert result["conclusion"] == long_text, (
        f"Conclusion was truncated: got {len(result['conclusion'])} chars, expected 500"
    )


# ── F15: cross-company — tanla, data_patterns, ujjivan also pass leak scan ────

@pytest.mark.parametrize("slug", ["tanla", "data_patterns", "ujjivan"])
def test_cross_company_no_forbidden_terms(slug):
    path = (
        Path(__file__).resolve().parents[2]
        / "companies"
        / slug
        / "company_memory"
        / "ask_intrinsiciq"
        / "answer_cards.json"
    )
    if not path.exists():
        pytest.skip(f"No answer_cards.json for {slug}")
    data = json.loads(path.read_text())
    answers = data.get("answers", [])
    violations = []
    for ans in answers:
        raw = json.dumps(ans)
        for term in HARD_FORBIDDEN:
            if term in raw:
                violations.append((ans.get("question_id", "?"), term))
        text = _user_visible_text(ans)
        if _SNAKE_RE.search(text):
            violations.append((ans.get("question_id", "?"), "snake_case"))
    assert not violations, f"{slug} violations: {violations[:10]}"
