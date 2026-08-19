from knowledge.financials.schema import MonetaryValue
from knowledge.financials.units import build_monetary_value, canonicalize_unit, convert_to_crore


def test_lakh_to_crore_conversion():
    value = build_monetary_value(value_original=1020, unit_original="lakhs", source_year="fy25")

    assert value.value_crore == 10.2
    assert value.unit_original == "lakhs"


def test_million_inr_to_crore_conversion():
    value = build_monetary_value(value_original=10, unit_original="million INR", source_year="fy25")

    assert value.value_crore == 1.0


def test_thousand_to_crore_conversion():
    value = build_monetary_value(value_original=236044642, unit_original="thousands", source_year="fy25")

    assert value.value_crore == 23604.4642


def test_crore_remains_crore():
    assert convert_to_crore(12.5, "crore") == 12.5
    assert canonicalize_unit("cr") == "cr"


def test_negative_values_are_supported():
    value = build_monetary_value(value_original=-250, unit_original="lakhs", source_year="fy25")

    assert value.value_crore == -2.5


def test_missing_values_are_marked():
    value = build_monetary_value(value_original=None, unit_original="crore", source_year="fy25")

    assert isinstance(value, MonetaryValue)
    assert value.value_crore is None
    assert "missing_value" in value.notes
