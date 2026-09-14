"""Unit tests for ENG-128 economic engine trajectory classification.

Tests: ACCELERATING, DECELERATING, STABLE_GROWTH, VOLATILE, RECOVERING,
INSUFFICIENT_HISTORY, DETERIORATING, and the STABLE_SHARE+DECELERATING combo.
"""
from knowledge.economic_engines import (
    _classify_growth_momentum,
    _classify_mix_trajectory,
    _classify_scale_status,
    _classify_relative_performance,
    _detect_inflection,
    _build_investor_interpretation,
)


def test_decelerating():
    # US-like: growth rates declining over last 3 periods
    rates = [0.133, 0.191, 0.137, 0.071, 0.036]
    assert _classify_growth_momentum(rates) == "DECELERATING"


def test_accelerating():
    # India-like: growth rates rising over last 3 periods
    rates = [0.228, 0.053, 0.087, 0.129, 0.133]
    assert _classify_growth_momentum(rates) == "ACCELERATING"


def test_stable_growth():
    rates = [0.10, 0.11, 0.10, 0.09, 0.10]
    assert _classify_growth_momentum(rates) == "STABLE_GROWTH"


def test_volatile():
    rates = [0.15, 0.05, 0.20, 0.03, 0.18]
    assert _classify_growth_momentum(rates) == "VOLATILE"


def test_recovering():
    rates = [-0.10, -0.05, 0.08, 0.12, 0.15]
    assert _classify_growth_momentum(rates) == "RECOVERING"


def test_deteriorating():
    rates = [0.05, -0.03, -0.08, -0.10, -0.12]
    assert _classify_growth_momentum(rates) == "DETERIORATING"


def test_insufficient_history():
    assert _classify_growth_momentum([0.10, 0.12]) == "INSUFFICIENT_HISTORY"
    assert _classify_growth_momentum([]) == "INSUFFICIENT_HISTORY"
    assert _classify_growth_momentum([None, None, 0.10]) == "INSUFFICIENT_HISTORY"


def test_one_year_spike_not_accelerating():
    # Single spike at end should not trigger ACCELERATING
    rates = [0.10, 0.09, 0.10, 0.08, 0.25]
    result = _classify_growth_momentum(rates)
    # last3 = [0.10, 0.08, 0.25] → 0.08 < 0.10 then 0.25 > 0.08 → no monotone → VOLATILE
    assert result != "ACCELERATING"


def test_stable_share_plus_decelerating_coexist():
    """STABLE_SHARE and DECELERATING must coexist without contradiction."""
    mix_traj = _classify_mix_trajectory(0.313, 0.303)  # US: -1.0pp < 2pp threshold
    momentum = _classify_growth_momentum([0.133, 0.191, 0.137, 0.071, 0.036])
    assert mix_traj == "STABLE_SHARE"
    assert momentum == "DECELERATING"
    # Build interpretation — must not say STABLE for momentum
    interp = _build_investor_interpretation("United States of America", "MAJOR", mix_traj, momentum, "UNDERPERFORMING", None)
    assert "decelerating" in interp["summary"].lower()
    assert "stable" in interp["summary"].lower()  # mix is stable — both concepts coexist


def test_losing_share_but_absolute_growing():
    """LOSING_SHARE + STABLE_GROWTH must coexist (mix and momentum are independent)."""
    mix_traj = _classify_mix_trajectory(0.35, 0.30)  # -5pp → LOSING_SHARE
    # Positive but non-monotone rates: last3 range < 5pp → STABLE_GROWTH
    momentum = _classify_growth_momentum([0.09, 0.08, 0.09, 0.08, 0.09])
    assert mix_traj == "LOSING_SHARE"
    assert momentum == "STABLE_GROWTH"


def test_mix_trajectory_gaining():
    assert _classify_mix_trajectory(0.15, 0.20) == "GAINING_SHARE"


def test_mix_trajectory_losing():
    assert _classify_mix_trajectory(0.25, 0.20) == "LOSING_SHARE"


def test_mix_trajectory_stable():
    assert _classify_mix_trajectory(0.30, 0.31) == "STABLE_SHARE"


def test_scale_status():
    assert _classify_scale_status(0.35) == "MAJOR"
    assert _classify_scale_status(0.20) == "MATERIAL"
    assert _classify_scale_status(0.08) == "SMALL"
    assert _classify_scale_status(0.02) == "MINOR"
    assert _classify_scale_status(None) == "UNKNOWN"


def test_relative_performance():
    assert _classify_relative_performance(0.15, 0.10, [0.08, 0.07]) == "OUTPERFORMING"
    assert _classify_relative_performance(0.05, 0.10, [0.12, 0.11]) == "UNDERPERFORMING"
    assert _classify_relative_performance(0.10, 0.10, [0.09, 0.11]) == "IN_LINE"
    assert _classify_relative_performance(None, 0.10, []) == "UNKNOWN"


def test_inflection_detected():
    # Needs ≥ 6 valid rates; first half ACCELERATING, second half DECELERATING
    rates = [0.05, 0.08, 0.12, 0.15, 0.12, 0.08, 0.04, 0.02]
    result = _detect_inflection(rates)
    assert result is not None
    assert "ACCELERATING" in result or "DECELERATING" in result


def test_inflection_insufficient():
    assert _detect_inflection([0.10, 0.12, 0.08]) is None


def test_investor_interpretation_unique_per_engine():
    """Decelerating and accelerating engines must not share the same summary."""
    i1 = _build_investor_interpretation("Engine A", "MAJOR", "STABLE_SHARE", "DECELERATING", "UNDERPERFORMING", None)
    i2 = _build_investor_interpretation("Engine B", "MATERIAL", "GAINING_SHARE", "ACCELERATING", "OUTPERFORMING", None)
    assert i1["summary"] != i2["summary"]
    assert "decelerating" in i1["summary"].lower()
    assert "accelerating" in i2["summary"].lower()
