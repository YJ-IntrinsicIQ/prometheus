from knowledge.financials.line_item_mapper import map_line_item, normalize_label


def test_revenue_mapping():
    matches = map_line_item(table_type="profit_and_loss", line_item_raw="Revenue from operations")
    assert matches
    assert matches[0].canonical_section == "profit_and_loss"
    assert matches[0].canonical_field == "revenue"


def test_pat_mapping():
    matches = map_line_item(table_type="profit_and_loss", line_item_raw="Profit for the year")
    assert matches[0].canonical_field == "pat"


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


def test_balance_sheet_header_row_does_not_override_equity_line():
    matches = map_line_item(
        table_type="balance_sheet",
        line_item_raw="Equity and Liabilities Equity Share capital",
    )
    fields = {match.canonical_field for match in matches}
    assert "equity_share_capital" in fields
    assert "net_worth" not in fields
    assert "total_liabilities" not in fields


def test_subtotals_do_not_map_to_full_balance_sheet_totals():
    asset_matches = map_line_item(table_type="balance_sheet", line_item_raw="Total Non-current Assets")
    liability_matches = map_line_item(table_type="balance_sheet", line_item_raw="Total non current liabilities")
    assert "total_assets" not in {match.canonical_field for match in asset_matches}
    assert "total_liabilities" not in {match.canonical_field for match in liability_matches}


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
