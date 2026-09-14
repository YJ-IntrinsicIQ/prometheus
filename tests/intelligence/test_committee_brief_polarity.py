"""
ENG-131A: Generic polarity correctness tests for Committee Brief renderer.
Tests the classification contract: structured conviction_effect governs polarity,
not keyword inference. Worsening evidence must never appear in the positive slot.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from intelligence.investor_panel.committee_brief_renderer import build_canonical_committee_brief_view_v2
from intelligence.investor_panel.committee_brief_qa import CommitteeBriefQAGate


def _make_synthesis(**overrides):
    """Minimal valid v2 committee synthesis fixture."""
    base = {
        "analysis_mode": "committee_synthesis_v2",
        "company": "test_co",
        "company_slug": "test_co",
        "committee_view": "The committee sees a mixed business.",
        "committee_direction": "weakening",
        "consensus_strength": "moderate",
        "committee_summary": "Mixed evidence with worsening risk profile.",
        "latest_period": "fy26",
        "years_considered": ["fy24", "fy25", "fy26"],
        "thesis_strengtheners": [],
        "thesis_weakeners": [],
        "major_turning_points": [],
        "strongest_shared_convictions": [],
        "major_disagreements": [],
        "unresolved_items": [],
        "top_diligence_questions": [],
        "what_would_change_the_view": [],
        "critical_unknowns": [],
        "management_judgment": {},
        "capital_allocation_judgment": {},
        "financial_judgment": {},
        "risk_judgment": {},
        "evidence_confidence": {"level": "medium", "basis": ["test"], "main_limitation": "Evidence incomplete."},
    }
    base.update(overrides)
    return base


def _bottom_line(synthesis):
    view = build_canonical_committee_brief_view_v2(synthesis)
    return view.get("bottom_line", "")


# --- Test 1: improving risk (strengthened) → positive slot ---
def test_improving_risk_in_positive_slot():
    synthesis = _make_synthesis(
        thesis_strengtheners=[{
            "summary": "US revenue engine is recovering and accelerating.",
            "period": "fy26",
            "why_it_matters": "Reversal of prior deceleration — positive signal.",
            "conviction_effect": "strengthened",
            "confidence": "high",
            "supporting_analysts": ["buffett", "fisher"],
        }]
    )
    bottom = _bottom_line(synthesis)
    assert "US revenue engine is recovering" in bottom or "recovering" in bottom.lower(), (
        f"Improving/strengthened item should appear in positive slot. Got: {bottom!r}"
    )


# --- Test 2: worsening risk → must NOT be in positive slot ---
def test_worsening_risk_not_in_positive_slot():
    synthesis = _make_synthesis(
        major_turning_points=[{
            "period": "fy26",
            "summary": "FX risk is classified as worsening.",
            "event": "FX risk is classified as worsening.",
            "before": "stable",
            "after": "increasing",
            "why_it_matters": "Risk has intensified.",
            "conviction_effect": "weakened",
            "confidence": "high",
            "supporting_analysts": ["graham", "munger"],
        }],
        thesis_weakeners=[{
            "summary": "FX risk is classified as worsening.",
            "period": "fy26",
            "why_it_matters": "Risk has intensified.",
            "conviction_effect": "weakened",
            "confidence": "high",
            "supporting_analysts": ["graham", "munger"],
        }]
    )
    bottom = _bottom_line(synthesis)
    # "strongest positive is FX risk is classified as worsening" must NOT appear
    lower = bottom.lower()
    if "strongest positive" in lower:
        positive_start = lower.index("strongest positive")
        positive_clause = lower[positive_start:positive_start + 120]
        assert "worsening" not in positive_clause, (
            f"Worsening risk appeared in 'strongest positive' slot. bottom_line: {bottom!r}"
        )


# --- Test 3: stable/neutral risk → does not appear as positive or negative label ---
def test_stable_risk_not_forced_positive():
    synthesis = _make_synthesis(
        major_turning_points=[{
            "period": "fy26",
            "summary": "Governance risk remains stable with no change.",
            "event": "Governance risk remains stable.",
            "before": "stable",
            "after": "stable",
            "why_it_matters": "No material change observed.",
            "conviction_effect": "",  # no polarity
            "confidence": "medium",
            "supporting_analysts": ["graham"],
        }]
    )
    bottom = _bottom_line(synthesis)
    # Stable item with empty conviction_effect is allowed in what_changed but should not be labeled "strongest positive"
    # unless there are no strengtheners — if it does appear, it shouldn't say "worsening"
    assert "worsening" not in bottom.lower() or "strongest positive" not in bottom.lower() or (
        "strongest positive" in bottom.lower() and "worsening" not in bottom.lower()[bottom.lower().index("strongest positive"):bottom.lower().index("strongest positive") + 120]
    ), f"Stable risk mislabeled. bottom_line: {bottom!r}"


# --- Test 4: unresolved risk → not classified as positive ---
def test_unresolved_risk_not_classified_positive():
    synthesis = _make_synthesis(
        major_turning_points=[{
            "period": "fy26",
            "summary": "Capital allocation returns remain unresolved.",
            "event": "Capital allocation returns remain unresolved.",
            "before": "unknown",
            "after": "unknown",
            "why_it_matters": "Cannot determine if capital is being deployed effectively.",
            "conviction_effect": "weakened",  # unresolved → treated as weakened for polarity
            "confidence": "low",
            "supporting_analysts": ["buffett"],
        }]
    )
    bottom = _bottom_line(synthesis)
    lower = bottom.lower()
    if "strongest positive" in lower:
        positive_start = lower.index("strongest positive")
        positive_clause = lower[positive_start:positive_start + 120]
        assert "unresolved" not in positive_clause, (
            f"Unresolved item appeared in positive slot. bottom_line: {bottom!r}"
        )


# --- Test 5: positive thesis evidence → appears in positive slot (bottom_line or what_strengthened) ---
def test_positive_thesis_evidence_in_positive_slot():
    synthesis = _make_synthesis(
        thesis_strengtheners=[{
            "summary": "Net cash position strengthens balance sheet resilience.",
            "period": "fy26",
            "why_it_matters": "Balance sheet is a positive anchor for the thesis.",
            "conviction_effect": "strengthened",
            "confidence": "high",
            "supporting_analysts": ["graham", "buffett"],
        }]
    )
    view = build_canonical_committee_brief_view_v2(synthesis)
    bottom = view.get("bottom_line", "")
    what_strengthened = view.get("what_strengthened", [])
    # Thesis strengtheners appear either in what_strengthened or, via fallback,
    # in what_changed (when major_turning_points is empty) which populates bottom_line.
    in_strengthened = any("net cash" in str(item.get("conclusion", "")).lower() for item in what_strengthened)
    in_bottom = "net cash" in bottom.lower() or "strengthens balance sheet" in bottom.lower()
    assert in_strengthened or in_bottom, (
        f"Positive thesis evidence should appear in positive slot (what_strengthened or bottom_line). "
        f"what_strengthened={what_strengthened}, bottom_line={bottom!r}"
    )
    # Critical: it must NOT appear in the 'biggest concern' slot
    lower = bottom.lower()
    if "biggest concern" in lower:
        concern_start = lower.index("biggest concern")
        concern_end = lower.find("main unresolved", concern_start)
        if concern_end == -1:
            concern_end = len(lower)
        concern_clause = lower[concern_start:concern_end]
        assert "net cash" not in concern_clause, (
            f"Positive evidence appeared in 'biggest concern' slot: {bottom!r}"
        )


# --- Test 6: weakening thesis evidence → appears in what_weakened, not what_strengthened ---
def test_weakening_thesis_evidence_in_weakened_slot():
    synthesis = _make_synthesis(
        thesis_weakeners=[{
            "summary": "Governance risk is worsening in the longitudinal evidence.",
            "period": "fy26",
            "why_it_matters": "Worsening governance reduces thesis confidence.",
            "conviction_effect": "weakened",
            "confidence": "high",
            "supporting_analysts": ["graham", "munger"],
        }]
    )
    view = build_canonical_committee_brief_view_v2(synthesis)
    what_weakened = view.get("what_weakened", [])
    what_strengthened = view.get("what_strengthened", [])
    assert any("governance" in str(item.get("conclusion", "")).lower() for item in what_weakened), (
        f"Weakening evidence should appear in what_weakened. Got: {what_weakened}"
    )
    strengthened_texts = " ".join(str(item.get("conclusion", "")) for item in what_strengthened).lower()
    assert "governance risk is worsening" not in strengthened_texts, (
        f"Weakening evidence must not appear in what_strengthened. Got: {what_strengthened}"
    )


# --- Test 7: mixed evidence → strengthened not in negative slot, weakened not in positive slot ---
def test_mixed_evidence_split_correctly():
    synthesis = _make_synthesis(
        thesis_strengtheners=[{
            "summary": "India growth engine is accelerating with strong momentum.",
            "period": "fy26",
            "why_it_matters": "Positive engine trajectory.",
            "conviction_effect": "strengthened",
            "confidence": "medium",
            "supporting_analysts": ["fisher", "lynch"],
        }],
        thesis_weakeners=[{
            "summary": "US growth engine is decelerating rapidly.",
            "period": "fy26",
            "why_it_matters": "Major engine losing momentum.",
            "conviction_effect": "weakened",
            "confidence": "high",
            "supporting_analysts": ["buffett", "graham"],
        }],
    )
    view = build_canonical_committee_brief_view_v2(synthesis)
    what_strengthened = view.get("what_strengthened", [])
    what_weakened = view.get("what_weakened", [])
    bottom = view.get("bottom_line", "").lower()
    strengthened_texts = " ".join(str(i.get("conclusion", "")) for i in what_strengthened).lower()
    weakened_texts = " ".join(str(i.get("conclusion", "")) for i in what_weakened).lower()
    # Weakened item must appear in what_weakened
    assert "us growth" in weakened_texts or "decelerating" in weakened_texts, (
        f"US weakener should be in what_weakened. Got: {what_weakened}"
    )
    # Weakened item must NOT appear in the positive slot in bottom_line
    if "strongest positive" in bottom:
        pos_start = bottom.index("strongest positive")
        pos_end = bottom.find("biggest concern", pos_start)
        if pos_end == -1:
            pos_end = pos_start + 150
        pos_clause = bottom[pos_start:pos_end]
        assert "decelerating" not in pos_clause, (
            f"US weakener (decelerating) appeared in 'strongest positive' slot: {bottom!r}"
        )


# --- Test 8: missing conviction_effect field → safe fallback (unknown != positive) ---
def test_missing_conviction_effect_safe_fallback():
    """Items with no conviction_effect field must NOT enter the positive slot.
    Unknown polarity is not positive; fall back to default text instead."""
    synthesis = _make_synthesis(
        major_turning_points=[{
            "period": "fy26",
            "summary": "Working capital pressure has intensified materially.",
            "event": "Working capital pressure has intensified.",
            "before": "moderate",
            "after": "severe",
            "why_it_matters": "Cash conversion cycle stretched further.",
            # conviction_effect intentionally omitted -> unknown polarity
            "confidence": "high",
            "supporting_analysts": ["buffett"],
        }]
    )
    bottom = _bottom_line(synthesis)
    lower = bottom.lower()
    # Item with missing conviction_effect must NOT appear in 'strongest positive' slot.
    if "strongest positive" in lower:
        positive_start = lower.index("strongest positive")
        positive_end = lower.find("biggest concern", positive_start)
        if positive_end == -1:
            positive_end = positive_start + 150
        positive_clause = lower[positive_start:positive_end]
        assert "intensified" not in positive_clause, (
            f"Unknown-polarity item leaked into positive slot: {bottom!r}"
        )


# --- Test 9: negative text inside otherwise positive sentence → structured conviction_effect=strengthened wins ---
def test_negative_text_in_strengthener_does_not_block_positive_slot():
    """A thesis_strengthener can mention a risk word in context — conviction_effect=strengthened means it belongs
    in the positive slot. Keyword-in-text ('risk', 'fx') must not block it."""
    synthesis = _make_synthesis(
        thesis_strengtheners=[{
            "summary": "Despite FX risk disclosure, management has taken hedging action.",
            "period": "fy26",
            "why_it_matters": "Execution has started; risk is being managed.",
            "conviction_effect": "strengthened",
            "confidence": "medium",
            "supporting_analysts": ["munger"],
        }]
    )
    view = build_canonical_committee_brief_view_v2(synthesis)
    # When major_turning_points is empty, thesis_strengtheners become what_changed items (fallback).
    # The strengthener may appear in what_strengthened OR what_changed (via bottom_line positive slot).
    what_strengthened = view.get("what_strengthened", [])
    bottom = view.get("bottom_line", "").lower()
    in_strengthened = any(
        "hedging" in str(item.get("conclusion", "")).lower() or "fx risk" in str(item.get("conclusion", "")).lower()
        for item in what_strengthened
    )
    in_bottom_positive = False
    if "strongest positive" in bottom:
        pos_start = bottom.index("strongest positive")
        pos_end = bottom.find("biggest concern", pos_start)
        if pos_end == -1:
            pos_end = pos_start + 200
        pos_clause = bottom[pos_start:pos_end]
        in_bottom_positive = "hedging" in pos_clause or "fx risk" in pos_clause
    assert in_strengthened or in_bottom_positive, (
        f"Strengthener with negative-word context should appear in positive slot. "
        f"what_strengthened={what_strengthened}, bottom_line={view.get('bottom_line')!r}"
    )


# --- Test 10: positive word inside negative structured state → conviction_effect=weakened wins ---
def test_positive_word_in_weakened_item_does_not_enter_positive_slot():
    """Even if a weakened item contains words like 'strong' or 'positive', conviction_effect=weakened blocks it from the positive slot."""
    synthesis = _make_synthesis(
        major_turning_points=[{
            "period": "fy26",
            "summary": "Strong increase in worsening governance risk classification.",
            "event": "Strong increase in worsening governance risk.",
            "before": "elevated",
            "after": "severe",
            "why_it_matters": "Governance trajectory is strongly negative.",
            "conviction_effect": "weakened",
            "confidence": "high",
            "supporting_analysts": ["graham"],
        }]
    )
    bottom = _bottom_line(synthesis)
    lower = bottom.lower()
    if "strongest positive" in lower:
        positive_start = lower.index("strongest positive")
        positive_clause = lower[positive_start:positive_start + 120]
        assert "worsening governance" not in positive_clause, (
            f"Weakened item with positive word leaked into positive slot. bottom_line: {bottom!r}"
        )


if __name__ == "__main__":
    tests = [
        test_improving_risk_in_positive_slot,
        test_worsening_risk_not_in_positive_slot,
        test_stable_risk_not_forced_positive,
        test_unresolved_risk_not_classified_positive,
        test_positive_thesis_evidence_in_positive_slot,
        test_weakening_thesis_evidence_in_weakened_slot,
        test_mixed_evidence_split_correctly,
        test_missing_conviction_effect_safe_fallback,
        test_negative_text_in_strengthener_does_not_block_positive_slot,
        test_positive_word_in_weakened_item_does_not_enter_positive_slot,
    ]
    passed = 0
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{len(tests)} passed")
    if failed:
        sys.exit(1)
