"""ENG-118 Phase 1: Capital Amount Unit Authority & Ambiguous-Amount Containment.

Adversarial tests verifying that:
  - Explicit lakh amounts are correctly converted to crore
  - Explicit crore amounts are preserved
  - Bare numeric strings (no unit) → UNIT_AMBIGUOUS (amount=None)
  - Bare INR strings without unit context → UNIT_AMBIGUOUS (amount=None)
  - Foreign currency strings → unsupported (amount=None)
  - Per-share amounts → ambiguous (amount=None)
  - Semicolon-compound strings → ambiguous (amount=None)
  - Ambiguous events remain in Phase 2 (event count preserved)
  - Ambiguous amounts are excluded from weighted totals
  - Coverage ratio reflects only confirmed amounts
  - capital_weighted_conclusions_permitted cannot be True
    when all amounts are unit_ambiguous

Tests A–L correspond to the 13 adversarial cases in ENG-118 Phase 1 Step 13.
"""
from __future__ import annotations

import pytest

from intelligence.capital_allocation_outcomes.builder import (
    _candidate_amount,
    _amount_basis,
    _parse_amount_to_crore,
)
from intelligence.capital_allocation_outcomes.longitudinal_profile import (
    _amount_coverage,
    _build_allocation_mix,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item(amount=None, amount_crore=None, amount_raised_crore=None, **kw):
    d = {}
    if amount is not None:
        d["amount"] = amount
    if amount_crore is not None:
        d["amount_crore"] = amount_crore
    if amount_raised_crore is not None:
        d["amount_raised_crore"] = amount_raised_crore
    d.update(kw)
    return d


def _ledger(**kw):
    return kw


def _rec(allocation_id, category, amount, amount_basis="source_item", **kw):
    return {
        "allocation_id": allocation_id,
        "allocation_category": category,
        "amount": amount,
        "amount_basis": amount_basis,
        "causal_attribution_confidence": "LOW",
        "outcome_status": "not_yet_observable",
        "value_creation_classification": "TOO_EARLY_TO_JUDGE",
        "financial_outcome_state": "UNABLE_TO_ATTRIBUTE",
        **kw,
    }


# ---------------------------------------------------------------------------
# Unit parser: _parse_amount_to_crore
# ---------------------------------------------------------------------------

class TestParseAmountToCrore:
    """Direct tests of the unit-aware string parser."""

    def test_explicit_lakhs_inr_prefix(self):
        """INR 12,280.86 lakhs → 122.8086 Cr"""
        result = _parse_amount_to_crore("INR 12,280.86 lakhs")
        assert result is not None
        assert abs(result - 122.8086) < 0.001

    def test_explicit_lakhs_suffix(self):
        """25,500.00 INR Lakhs → 255 Cr"""
        result = _parse_amount_to_crore("25,500.00 INR Lakhs")
        assert result is not None
        assert abs(result - 255.0) < 0.001

    def test_explicit_lakhs_with_share_count_suffix(self):
        """INR 1,821.46 lakhs for 3,00,000 shares → 18.2146 Cr"""
        result = _parse_amount_to_crore("INR 1,821.46 lakhs for 3,00,000 shares")
        assert result is not None
        assert abs(result - 18.2146) < 0.001

    def test_explicit_crore_rupee_symbol(self):
        """₹51 Cr → 51 Cr"""
        result = _parse_amount_to_crore("₹51 Cr")
        assert result == pytest.approx(51.0)

    def test_explicit_crore_spelled_out(self):
        """INR 159 Crores → 159 Cr"""
        result = _parse_amount_to_crore("INR 159 Crores")
        assert result == pytest.approx(159.0)

    def test_explicit_crore_with_context(self):
        """₹220 Cr (cash outflow, FY25) → 220 Cr"""
        result = _parse_amount_to_crore("₹220 Cr (cash outflow, FY25)")
        assert result == pytest.approx(220.0)

    def test_bare_inr_no_unit_ambiguous(self):
        """INR 20,000,000 without unit label → UNIT_AMBIGUOUS"""
        result = _parse_amount_to_crore("INR 20,000,000")
        assert result is None, "Raw INR string without unit must not be parsed as crore"

    def test_bare_inr_small_no_unit_ambiguous(self):
        """INR 16,903,800 → UNIT_AMBIGUOUS (no unit label)"""
        result = _parse_amount_to_crore("INR 16,903,800")
        assert result is None

    def test_bare_numeric_no_unit_ambiguous(self):
        """1,835.37 with no unit → UNIT_AMBIGUOUS"""
        result = _parse_amount_to_crore("1,835.37")
        assert result is None, "Bare numeric with no unit must not be treated as crore"

    def test_bare_numeric_parenthesised(self):
        """(25,500.00) → UNIT_AMBIGUOUS"""
        result = _parse_amount_to_crore("(25,500.00)")
        assert result is None

    def test_foreign_currency_usd_excluded(self):
        """USD 25,545,429 → unsupported currency, excluded"""
        result = _parse_amount_to_crore("USD 25,545,429")
        assert result is None, "USD amounts must be excluded from known_amount_crore"

    def test_per_share_amount_ambiguous(self):
        """₹ 2 per equity share → ambiguous (total unknown)"""
        result = _parse_amount_to_crore("₹ 2 per equity share")
        assert result is None

    def test_per_share_in_compound_string(self):
        """₹ 2 per equity share; cash outflow of ₹ 26 crore → ambiguous"""
        result = _parse_amount_to_crore("₹ 2 per equity share; cash outflow of ₹ 26 crore")
        assert result is None, "First number must not be silently taken from multi-value string"

    def test_semicolon_compound_ambiguous(self):
        """Loans given: 8,907.04; balance outstanding: 10,540.19 → ambiguous"""
        result = _parse_amount_to_crore(
            "Loans given during year: 8,907.04; balance outstanding as at March 31, 2024: 10,540.19"
        )
        assert result is None

    def test_outstanding_balance_ambiguous(self):
        """1,835.37; balance outstanding as at March 31, 2024: 1,700.29 → ambiguous"""
        result = _parse_amount_to_crore(
            "1,835.37; balance outstanding as at March 31, 2024: 1,700.29"
        )
        assert result is None

    def test_buyback_compound_semicolon(self):
        """Bought back N shares; price ...; deployed ₹64.98 crore → ambiguous (has ;)"""
        result = _parse_amount_to_crore(
            "Bought back 7,05,677 equity shares; volume weighted average price ₹920.88 per equity share; deployed ₹64.98 crore excluding transaction costs"
        )
        assert result is None

    def test_rupee_symbol_crore_parenthetical(self):
        """₹ 112 crore → 112 Cr"""
        result = _parse_amount_to_crore("₹ 112 crore")
        assert result == pytest.approx(112.0)

    def test_lakh_bracket_format(self):
        """1,578.05 (₹ in Lakhs) → 15.7805 Cr"""
        result = _parse_amount_to_crore("1,578.05 (₹ in Lakhs)")
        assert result is not None
        assert abs(result - 15.7805) < 0.001

    def test_rsu_grant_no_unit(self):
        """4,67,500 RSU granted → UNIT_AMBIGUOUS (share count, not money)"""
        result = _parse_amount_to_crore("4,67,500 RSU granted")
        assert result is None

    def test_aggregate_buyback_with_semicolon(self):
        """Aggregate amount not exceeding ₹65 crore; price not exceeding ₹1,260 per equity share → ambiguous"""
        result = _parse_amount_to_crore(
            "Aggregate amount not exceeding ₹65 crore; price not exceeding ₹1,260 per equity share"
        )
        assert result is None

    def test_numeric_int_trusted_as_crore(self):
        """Numeric int input trusted as crore (financial timeline contract)"""
        result = _parse_amount_to_crore(208)
        assert result == pytest.approx(208.0)

    def test_numeric_float_trusted_as_crore(self):
        """Numeric float trusted as crore"""
        result = _parse_amount_to_crore(51.0)
        assert result == pytest.approx(51.0)

    def test_none_returns_none(self):
        assert _parse_amount_to_crore(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_amount_to_crore("") is None


# ---------------------------------------------------------------------------
# Test A: INR lakhs explicit → correct crore conversion
# ---------------------------------------------------------------------------

class TestA_ExplicitLakhsConversion:
    def test_inr_12280_lakhs_to_crore(self):
        """A: INR 12,280.86 lakhs → 122.8086 Cr"""
        item = _item(amount="INR 12,280.86 lakhs")
        result = _candidate_amount(item, _ledger())
        assert result is not None
        assert abs(result - 122.8086) < 0.001

    def test_inr_13219_lakhs_to_crore(self):
        item = _item(amount="INR 13,219.14 lakhs")
        result = _candidate_amount(item, _ledger())
        assert result is not None
        assert abs(result - 132.1914) < 0.001

    def test_inr_4025_lakhs_to_crore(self):
        item = _item(amount="4,025.00 INR Lakhs")
        result = _candidate_amount(item, _ledger())
        assert result is not None
        assert abs(result - 40.25) < 0.001

    def test_amount_basis_source_item_for_parsed_lakh(self):
        item = _item(amount="INR 12,280.86 lakhs")
        amt = _candidate_amount(item, _ledger())
        basis = _amount_basis(item, _ledger(), amt)
        assert basis == "source_item"


# ---------------------------------------------------------------------------
# Test B: INR 20,000,000 without unit → UNIT_AMBIGUOUS
# ---------------------------------------------------------------------------

class TestB_BareINRNoUnit:
    def test_inr_20m_returns_none(self):
        """B: INR 20,000,000 with no unit label → None"""
        item = _item(amount="INR 20,000,000")
        result = _candidate_amount(item, _ledger())
        assert result is None, "Raw INR amount without unit must be None"

    def test_amount_basis_unit_ambiguous(self):
        """B: amount_basis must be unit_ambiguous when string has no parseable unit"""
        item = _item(amount="INR 20,000,000")
        amt = _candidate_amount(item, _ledger())
        basis = _amount_basis(item, _ledger(), amt)
        assert basis == "unit_ambiguous"

    def test_ledger_not_used_when_string_amount_present(self):
        """B: Ledger fallback suppressed when source item has a string amount (even ambiguous)"""
        item = _item(amount="INR 20,000,000")
        ledger = _ledger(capex_deployed=999.0)  # must NOT be used
        result = _candidate_amount(item, ledger)
        assert result is None, "Ambiguous string amount must suppress ledger fallback"

    def test_inr_16903800_returns_none(self):
        item = _item(amount="INR 16,903,800")
        assert _candidate_amount(item, _ledger()) is None

    def test_inr_4714640_returns_none(self):
        item = _item(amount="INR 4,714,640")
        assert _candidate_amount(item, _ledger()) is None


# ---------------------------------------------------------------------------
# Test D: Explicit crore → preserved
# ---------------------------------------------------------------------------

class TestD_ExplicitCrore:
    def test_rs_51_cr(self):
        """D: ₹51 Cr → 51 Cr"""
        item = _item(amount="₹51 Cr")
        result = _candidate_amount(item, _ledger())
        assert result == pytest.approx(51.0)

    def test_rs_208_cr(self):
        item = _item(amount="₹208 Cr (cash outflow, FY25)")
        result = _candidate_amount(item, _ledger())
        assert result == pytest.approx(208.0)

    def test_inr_159_crores(self):
        item = _item(amount="INR 159 Crores")
        result = _candidate_amount(item, _ledger())
        assert result == pytest.approx(159.0)

    def test_numeric_float_crore(self):
        """H: Numeric typed canonical crore input → preserved"""
        item = _item(amount=208.0)
        result = _candidate_amount(item, _ledger())
        assert result == pytest.approx(208.0)

    def test_amount_crore_field_trusted(self):
        """Schema-canonical amount_crore field → preserved"""
        item = _item(amount_crore=51.0)
        result = _candidate_amount(item, _ledger())
        assert result == pytest.approx(51.0)


# ---------------------------------------------------------------------------
# Test E: Bare numeric string → UNIT_AMBIGUOUS
# ---------------------------------------------------------------------------

class TestE_BareNumericString:
    def test_1835_37_bare(self):
        """E: 1,835.37 with no unit → None"""
        item = _item(amount="1,835.37")
        assert _candidate_amount(item, _ledger()) is None

    def test_parenthesised_numeric(self):
        item = _item(amount="(1,821.46)")
        assert _candidate_amount(item, _ledger()) is None

    def test_bare_numeric_basis_unit_ambiguous(self):
        item = _item(amount="1,835.37")
        amt = _candidate_amount(item, _ledger())
        basis = _amount_basis(item, _ledger(), amt)
        assert basis == "unit_ambiguous"


# ---------------------------------------------------------------------------
# Test F: Foreign currency → excluded
# ---------------------------------------------------------------------------

class TestF_ForeignCurrency:
    def test_usd_amount_excluded(self):
        """F: USD 25,545,429 → None (unsupported currency)"""
        item = _item(amount="USD 25,545,429")
        assert _candidate_amount(item, _ledger()) is None

    def test_usd_indian_comma_format_excluded(self):
        item = _item(amount="USD 18,65,954")
        assert _candidate_amount(item, _ledger()) is None


# ---------------------------------------------------------------------------
# Test G: Per-share compound string → do NOT silently parse
# ---------------------------------------------------------------------------

class TestG_PerShareCompound:
    def test_per_share_compound_returns_none(self):
        """G: ₹2 per share; cash outflow ₹26 crore → None"""
        item = _item(amount="₹ 2 per equity share; cash outflow of ₹ 26 crore")
        result = _candidate_amount(item, _ledger())
        assert result is None, "Must not silently take ₹2 instead of ₹26 Cr"

    def test_per_share_simple_returns_none(self):
        item = _item(amount="INR 6 per share")
        assert _candidate_amount(item, _ledger()) is None


# ---------------------------------------------------------------------------
# Test I: Ambiguous amount event remains in Phase 2 profile event count
# ---------------------------------------------------------------------------

class TestI_AmbiguousEventPreserved:
    def test_ambiguous_event_in_event_count(self):
        """I: Events with unit_ambiguous amounts must remain in total_events"""
        records = [
            _rec("CAO-0001", "organic_capex", 208.0),
            _rec("CAO-0002", "research_and_development", None, amount_basis="unit_ambiguous"),
        ]
        cov = _amount_coverage(records)
        assert cov["total_events"] == 2
        assert cov["events_with_known_amount"] == 1
        assert cov["events_without_amount"] == 1

    def test_ambiguous_count_reported(self):
        """I: events_with_unit_ambiguous_amount reported separately"""
        records = [
            _rec("CAO-0001", "organic_capex", 208.0),
            _rec("CAO-0002", "research_and_development", None, amount_basis="unit_ambiguous"),
            _rec("CAO-0003", "acquisition", None, amount_basis="unknown"),
        ]
        cov = _amount_coverage(records)
        assert cov["events_with_unit_ambiguous_amount"] == 1


# ---------------------------------------------------------------------------
# Test J: Ambiguous amount does not count toward known amount coverage
# ---------------------------------------------------------------------------

class TestJ_AmbiguousExcludedFromCoverage:
    def test_ambiguous_does_not_count_as_known(self):
        """J: unit_ambiguous events must not inflate coverage_ratio"""
        records = [
            _rec("CAO-0001", "organic_capex", None, amount_basis="unit_ambiguous"),
            _rec("CAO-0002", "organic_capex", None, amount_basis="unit_ambiguous"),
        ]
        cov = _amount_coverage(records)
        assert cov["coverage_ratio"] == 0.0
        assert cov["events_with_known_amount"] == 0


# ---------------------------------------------------------------------------
# Test K: Ambiguous amount does not affect category weighted mix
# ---------------------------------------------------------------------------

class TestK_AmbiguousExcludedFromMix:
    def test_ambiguous_not_in_known_amount_crore(self):
        """K: Category known_amount_crore must exclude unit_ambiguous events"""
        records = [
            _rec("CAO-0001", "organic_capex", 208.0),
            _rec("CAO-0002", "organic_capex", None, amount_basis="unit_ambiguous"),
        ]
        cov = _amount_coverage(records)
        mix = _build_allocation_mix(records, cov)
        cat = next(c for c in mix["by_category"] if c["category"] == "organic_capex")
        assert cat["known_amount_crore"] == pytest.approx(208.0)
        assert cat["amount_events_known"] == 1

    def test_share_of_known_deployment_uses_only_confirmed(self):
        records = [
            _rec("CAO-0001", "organic_capex", 100.0),
            _rec("CAO-0002", "acquisition", None, amount_basis="unit_ambiguous"),
        ]
        cov = _amount_coverage(records)
        mix = _build_allocation_mix(records, cov)
        # Only 1/2 events known → coverage = 0.5 → PARTIAL → capital_weighted_permitted = False
        assert not cov["capital_weighted_conclusions_permitted"]


# ---------------------------------------------------------------------------
# Test L: Known amount coverage falls honestly
# ---------------------------------------------------------------------------

class TestL_CoverageFallsHonestly:
    def test_all_ambiguous_coverage_zero(self):
        """L: If all events have unit_ambiguous amounts, coverage must be 0"""
        records = [
            _rec("CAO-0001", "research_and_development", None, amount_basis="unit_ambiguous"),
            _rec("CAO-0002", "research_and_development", None, amount_basis="unit_ambiguous"),
            _rec("CAO-0003", "unknown", None, amount_basis="unit_ambiguous"),
        ]
        cov = _amount_coverage(records)
        assert cov["coverage_ratio"] == 0.0
        assert not cov["capital_weighted_conclusions_permitted"]

    def test_capital_weighted_not_permitted_for_unit_ambiguous_all(self):
        """L: capital_weighted_conclusions_permitted cannot be True when amounts are ambiguous"""
        records = [
            _rec(f"CAO-{i:04d}", "unknown", None, amount_basis="unit_ambiguous")
            for i in range(15)
        ]
        cov = _amount_coverage(records)
        assert not cov["capital_weighted_conclusions_permitted"]


# ---------------------------------------------------------------------------
# Cross-company: no magnitude heuristics, no company hardcoding
# ---------------------------------------------------------------------------

class TestCrossCompany:
    def test_sun_pharma_in_million_excluded(self):
        """Sun Pharma 'In Million' strings must not become crore amounts"""
        result = _parse_amount_to_crore("105,515.7 (In Million)")
        assert result is None, "Amounts in Million must not be silently parsed as crore"

    def test_data_patterns_share_count_excluded(self):
        """Data Patterns share-count strings must not become crore amounts"""
        result = _parse_amount_to_crore("4,097,319 equity shares at Rs.1,220.31")
        assert result is None, "Share counts must not become capital amounts"

    def test_clean_crore_value_passes(self):
        """Any company: explicit crore amount preserved"""
        assert _parse_amount_to_crore("₹500 Crore") == pytest.approx(500.0)
        assert _parse_amount_to_crore("INR 1,000 Cr") == pytest.approx(1000.0)

    def test_explicit_lakh_any_company(self):
        """Any company: explicit lakh amount converted correctly"""
        result = _parse_amount_to_crore("25,000.00 lakhs")
        assert result is not None
        assert abs(result - 250.0) < 0.001

    def test_no_company_specific_threshold(self):
        """No magnitude heuristic: small and large bare numbers both return None"""
        assert _parse_amount_to_crore("42") is None
        assert _parse_amount_to_crore("20000000") is None
        assert _parse_amount_to_crore("200") is None
