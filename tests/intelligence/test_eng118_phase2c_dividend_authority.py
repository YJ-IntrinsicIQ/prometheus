from intelligence.capital_allocation_outcomes.builder import _parse_amount_to_crore


def test_explicit_cash_total_beats_per_share():
    assert _parse_amount_to_crore("₹2 per equity share; cash outflow of ₹26 crore") == 26.0


def test_per_share_only_has_no_total():
    assert _parse_amount_to_crore("Dividend of ₹2 per equity share") is None


def test_unlabelled_multiple_values_remain_ambiguous():
    assert _parse_amount_to_crore("2; 26") is None

