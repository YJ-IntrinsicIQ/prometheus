from knowledge.financials.line_item_mapper import map_line_item, normalize_label


def test_revenue_mapping():
    matches = map_line_item(table_type="profit_and_loss", line_item_raw="Revenue from operations")
    assert matches
    assert matches[0].canonical_section == "profit_and_loss"
    assert matches[0].canonical_field == "revenue"


def test_revenue_lookalikes_do_not_map_to_revenue():
    phrases = [
        "Revenue growth %",
        "Energy Intensity per INR Cr Revenue",
        "Revenue concentration",
        "Revenue per employee",
        "Revenue mix",
        "GHG emissions / Revenue from operations INR in Cr) tCO2e / INR in Cr",
    ]

    for phrase in phrases:
        matches = map_line_item(table_type="profit_and_loss", line_item_raw=phrase)
        assert "revenue" not in {match.canonical_field for match in matches}


def test_pat_mapping():
    matches = map_line_item(table_type="profit_and_loss", line_item_raw="Profit for the year")
    assert matches[0].canonical_field == "pat"


def test_pat_mapping_prefers_profit_attributable_to_owners():
    matches = map_line_item(table_type="profit_and_loss", line_item_raw="Profit for the year attributable to owners of the Company")
    assert matches
    assert matches[0].canonical_field == "pat"


def test_pre_nci_profit_rows_do_not_map_to_pat():
    labels = [
        "Profit for the year before non-controlling interests",
        "Profit for the year before share of profit/(loss) of associates and joint venture",
    ]

    for label in labels:
        matches = map_line_item(table_type="profit_and_loss", line_item_raw=label)
        assert "pat" not in {match.canonical_field for match in matches}


def test_pat_mapping_handles_profit_loss_label_variants():
    matches = map_line_item(table_type="profit_and_loss", line_item_raw="VII. Profit(Loss)for the period")
    assert "pat" in {match.canonical_field for match in matches}


def test_pat_mapping_from_balance_sheet_summary_label():
    matches = map_line_item(table_type="balance_sheet", line_item_raw="Total profit after taxes")
    assert "pat" in {match.canonical_field for match in matches}


def test_tax_mapping_from_financial_note():
    matches = map_line_item(table_type="balance_sheet", line_item_raw="Tax Expenses (including deferred tax)")
    assert "tax" in {match.canonical_field for match in matches}


def test_pbt_lookalikes_do_not_map_to_pbt():
    matches = map_line_item(
        table_type="cash_flow",
        line_item_raw="Operating Profit/(Loss) before Working Capital changes",
    )
    assert "pbt" not in {match.canonical_field for match in matches}


def test_pat_lookalikes_do_not_map_to_pat():
    matches = map_line_item(table_type="profit_and_loss", line_item_raw="For the year ended March")
    assert "pat" not in {match.canonical_field for match in matches}


def test_pat_ratio_lookalikes_do_not_map_to_pat():
    matches = map_line_item(table_type="balance_sheet", line_item_raw="Net profit ratio Profit after Tax Revenue from Operations")
    assert "pat" not in {match.canonical_field for match in matches}


def test_debt_mapping():
    matches = map_line_item(table_type="borrowings", line_item_raw="Long term borrowings")
    assert matches[0].canonical_section == "balance_sheet"
    assert matches[0].canonical_field == "long_term_debt"


def test_shareholding_mapping():
    matches = map_line_item(table_type="shareholding_pattern", line_item_raw="Promoter holding")
    assert matches[0].canonical_field == "promoter_holding"


def test_basic_and_diluted_maps_to_both_eps_fields():
    matches = map_line_item(table_type="eps", line_item_raw="Basic and diluted")
    fields = {match.canonical_field for match in matches}
    assert fields == {"eps_basic", "eps_diluted"}


def test_normalize_label_is_generic():
    assert normalize_label("Property, Plant & Equipment") == "property plant and equipment"


def test_balance_sheet_totals_do_not_match_on_weak_overlap():
    matches = map_line_item(table_type="balance_sheet", line_item_raw="Right of use assets")
    fields = {match.canonical_field for match in matches}
    assert "total_assets" not in fields
    assert "fixed_assets" not in fields


def test_real_ujjivan_fy23_asset_lookalikes_do_not_map_to_total_assets():
    phrases = [
        "Segment Assets",
        "vi) Total Risk weighted assets ( RWA )",
        "Average Total Assets",
        "Form AOC-1 Subsidiary Total Assets",
        "Total Assets of subsidiaries",
    ]

    for phrase in phrases:
        matches = map_line_item(table_type="balance_sheet", line_item_raw=phrase)
        assert "total_assets" not in {match.canonical_field for match in matches}


def test_balance_sheet_header_row_does_not_override_equity_line():
    matches = map_line_item(
        table_type="balance_sheet",
        line_item_raw="Equity and Liabilities Equity Share capital",
    )
    fields = {match.canonical_field for match in matches}
    assert "equity_share_capital" in fields
    assert "net_worth" not in fields
    assert "total_liabilities" not in fields


def test_liabilities_prefixed_trade_payable_row_does_not_map_to_group_payables():
    matches = map_line_item(table_type="balance_sheet", line_item_raw="Liabilities Trade payable")
    assert "payables" not in {match.canonical_field for match in matches}


def test_net_worth_rejects_off_balance_sheet_equity_tranche():
    matches = map_line_item(
        table_type="balance_sheet",
        line_item_raw="Balance Sheet* Off Balance Sheet Total Equity Tranche",
    )
    assert "net_worth" not in {match.canonical_field for match in matches}


def test_net_worth_still_maps_for_real_equity_language():
    matches = map_line_item(
        table_type="balance_sheet",
        line_item_raw="Shareholders' Funds",
    )
    assert "net_worth" in {match.canonical_field for match in matches}


def test_total_equity_and_liabilities_maps_to_total_assets():
    # "Total Equity and Liabilities" is an accounting identity = Total Assets
    # It should map to total_assets, NOT net_worth
    matches = map_line_item(
        table_type="balance_sheet",
        line_item_raw="Total Equity and Liabilities",
    )
    fields = {match.canonical_field for match in matches}

    assert "net_worth" not in fields
    assert "total_assets" in fields


def test_bank_reserve_equivalents_map_to_balance_sheet_reserves():
    retained_earnings = map_line_item(table_type="share_capital", line_item_raw="Retained earnings")
    reserve_fund = map_line_item(table_type="share_capital", line_item_raw="Investment Fluctuation Reserve")
    assert ("balance_sheet", "reserves") in {
        (match.canonical_section, match.canonical_field) for match in retained_earnings
    }
    assert ("balance_sheet", "reserves") in {
        (match.canonical_section, match.canonical_field) for match in reserve_fund
    }


def test_paid_up_capital_maps_to_equity_share_capital():
    matches = map_line_item(table_type="share_capital", line_item_raw="Paid up Capital")
    assert "equity_share_capital" in {match.canonical_field for match in matches}


def test_subtotals_do_not_map_to_full_balance_sheet_totals():
    asset_matches = map_line_item(table_type="balance_sheet", line_item_raw="Total Non-current Assets")
    liability_matches = map_line_item(table_type="balance_sheet", line_item_raw="Total non current liabilities")
    assert "total_assets" not in {match.canonical_field for match in asset_matches}
    assert "total_liabilities" not in {match.canonical_field for match in liability_matches}


def test_capex_maps_when_prefixed_by_investing_activity_section_header():
    matches = map_line_item(
        table_type="cash_flow",
        line_item_raw=(
            "B. Cash flow from investing activities Payments for purchase of property, "
            "plant and equipment"
        ),
    )
    assert "capex" in {match.canonical_field for match in matches}
    aggregate_matches = map_line_item(
        table_type="cash_flow",
        line_item_raw="Net cash flow from / (used in) investing activities (B)",
    )
    assert "capex" not in {match.canonical_field for match in aggregate_matches}


def test_authorised_equity_shares_do_not_map_to_shares_outstanding():
    matches = map_line_item(
        table_type="share_capital",
        line_item_raw="Authorised Equity shares of Rs.2 each",
    )
    assert "shares_outstanding" not in {match.canonical_field for match in matches}


def test_issued_subscribed_paid_up_equity_shares_map_to_shares_outstanding():
    matches = map_line_item(
        table_type="share_capital",
        line_item_raw="Issued, subscribed and paid-up equity shares of Rs.2 each",
    )
    assert "shares_outstanding" in {match.canonical_field for match in matches}


def test_fully_paid_up_equity_shares_map_to_shares_outstanding():
    matches = map_line_item(
        table_type="share_capital",
        line_item_raw="Issued, subscribed and fully paid up Equity shares of Rs.2 each",
    )
    assert "shares_outstanding" in {match.canonical_field for match in matches}


def test_weighted_average_shares_map_only_from_eps_note_wording():
    matches = map_line_item(
        table_type="eps",
        line_item_raw="Weighted average number of shares used in EPS calculation",
    )
    assert "weighted_avg_shares" in {match.canonical_field for match in matches}


def test_diluted_shares_map_only_from_eps_note_wording():
    matches = map_line_item(
        table_type="eps",
        line_item_raw="Number of shares used for diluted EPS",
    )
    assert "diluted_shares" in {match.canonical_field for match in matches}


def test_mutual_fund_units_do_not_map_to_share_count_fields():
    matches = map_line_item(
        table_type="share_capital",
        line_item_raw="Units held in mutual fund scheme",
    )
    fields = {match.canonical_field for match in matches}
    assert "shares_outstanding" not in fields
    assert "weighted_avg_shares" not in fields
    assert "diluted_shares" not in fields


def test_face_value_maps_from_equity_share_rs_each_wording():
    matches = map_line_item(
        table_type="share_capital",
        line_item_raw="Equity shares of Rs.2 each",
    )
    assert "face_value" in {match.canonical_field for match in matches}
