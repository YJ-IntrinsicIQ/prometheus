from knowledge.economic_engines import build_economic_engines
from knowledge.financials.extractor import _segment_reporting_slice
from intelligence.investor_panel.runner import _compact_business_economics_section


def _row(label, year, value, *, basis="consolidated", value_type="monetary", unit="million"):
    return {
        "line_item_raw": label, "basis": basis, "source_artifact": "raw_financial_tables.json",
        "page": 10, "chunk_id": f"chunk-{label}",
        "values": [{"period": f"March 31, {year}", "value_raw": str(value),
                    "value_crore": value / 10, "value_type": value_type, "unit_hint": unit}],
    }


def test_builds_deterministic_mix_and_preserves_unknown_profitability():
    payload = build_economic_engines(
        company="example_co", years=["fy25"],
        yearly_payloads={"fy25": {"raw_financial_tables": {"tables": {"segment_reporting": [
            _row("Domestic", 2025, 600), _row("International", 2025, 400),
        ]}}}},
    )
    engines = {item["engine_id"]: item for item in payload["engines"]}
    assert engines["domestic"]["history"][0]["revenue_share"] == 0.6
    assert engines["international"]["history"][0]["profitability_status"] == "NOT_DISCLOSED"
    assert engines["domestic"]["history"][0]["cash_conversion_linkage"] == "CONSOLIDATED_ONLY"


def test_basis_period_and_non_monetary_rows_do_not_enter_engine_truth():
    rows = [_row("Wrong basis", 2025, 100, basis="standalone"), _row("Wrong period", 2024, 100),
            _row("Narrative ratio", 2025, 10, value_type="percentage", unit="%")]
    payload = build_economic_engines(company="example_co", years=["fy25"], yearly_payloads={
        "fy25": {"raw_financial_tables": {"tables": {"segment_reporting": rows}}}})
    assert payload["engines"] == []
    assert payload["coverage_status"] == "NOT_AVAILABLE"


def test_multi_year_growth_and_mix_shift_are_not_causal_claims():
    yearly = {
        "fy24": {"raw_financial_tables": {"tables": {"segment_reporting": [_row("Engine A", 2024, 500), _row("Engine B", 2024, 500)]}}},
        "fy25": {"raw_financial_tables": {"tables": {"segment_reporting": [_row("Engine A", 2025, 700), _row("Engine B", 2025, 300)]}}},
    }
    payload = build_economic_engines(company="example_co", years=["fy24", "fy25"], yearly_payloads=yearly)
    engine = next(item for item in payload["engines"] if item["engine_id"] == "engine_a")
    assert engine["history"][1]["growth_rate"] == 0.4
    # With only 2 years of data, growth_momentum (= trajectory) is INSUFFICIENT_HISTORY.
    # Mix shift is captured in mix_trajectory: Engine A went from 50% to 70% share → GAINING_SHARE.
    assert engine["trajectory"] == "INSUFFICIENT_HISTORY"
    assert engine["mix_trajectory"] == "GAINING_SHARE"
    assert engine["history"][1]["growth_drivers"] == []


def test_changed_label_is_not_fuzzily_merged_without_alias_authority():
    yearly = {
        "fy24": {"raw_financial_tables": {"tables": {"segment_reporting": [_row("North America", 2024, 100), _row("Other", 2024, 50)]}}},
        "fy25": {"raw_financial_tables": {"tables": {"segment_reporting": [_row("US Market", 2025, 120), _row("Other", 2025, 55)]}}},
    }
    payload = build_economic_engines(company="example_co", years=yearly, yearly_payloads=yearly)
    assert {item["engine_id"] for item in payload["engines"]} == {"north_america", "us_market", "other"}


def test_mixed_eps_and_segment_note_isolated_before_asset_geography():
    text = (
        "NOTE: 51 EARNINGS PER SHARE Basic EPS 10.0 9.0 "
        "NOTE: 52 SEGMENT REPORTING Revenue by geography ₹ in Million "
        "India 600 500 International 400 300 "
        "Non-current assets by geography India 90 80"
    )
    segment = _segment_reporting_slice(text)
    assert "SEGMENT REPORTING" in segment
    assert "EARNINGS PER SHARE" not in segment
    assert "Non-current assets" not in segment


def test_panel_compaction_preserves_engine_economics_and_unknowns():
    economic = build_economic_engines(
        company="example_co", years=["fy25"],
        yearly_payloads={"fy25": {"raw_financial_tables": {"tables": {"segment_reporting": [
            _row("Domestic", 2025, 600), _row("International", 2025, 400),
        ]}}}},
    )
    compact = _compact_business_economics_section({"economic_engines": economic})
    engines = compact["economic_engines"]["engines"]
    assert engines[0]["history"][0]["revenue_share"] in {0.4, 0.6}
    assert "engine profitability" in engines[0]["unknowns"]
