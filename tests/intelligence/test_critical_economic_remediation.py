"""Critical SSOT remediation F17-F21: an amount is one period's flow, or it is typed as the stock / cumulative / proposed figure it is. Event identity =
company + event + economic role + amount basis + period + lifecycle + evidence."""
import re

from intelligence.capital_allocation_outcomes.builder import (
    _amount_role, _candidate_from_item, _dividend_lifecycle, _explicit_fiscal_year, _group_similarity, _build_allocation_group, _map_allocation_category,
)
from knowledge.capital_allocation_taxonomy import apply_label_verdict
from knowledge.company_memory.guardrails import extract_issue_dates


def cand(item, year="fy26", group="financing_actions", ledger=None):
    return _candidate_from_item(year, item, group, ledger or {})


QIP_GCP = {"source_item_id": "c8", "action": "Allocation of QIP proceeds for general corporate purposes", "category": "General corporate purposes", "purpose": "General corporate purposes",
           "amount": "Rs. 104.52 Crores", "canonical_category": "qualified_institutional_placement", "capital_allocation_group": "financing_actions"}
QIP_LAND = {"source_item_id": "c7", "action": "Allocation of QIP proceeds for land acquisition", "category": "Land acquisition", "purpose": "Funding acquisition of land (including building)",
            "amount": "Rs. 7.75 Crores", "canonical_category": "qualified_institutional_placement", "capital_allocation_group": "financing_actions"}
QIP_ISSUE = {"source_item_id": "c1", "action": "Equity issuance (Qualified Institutional Placement) — proceeds raised", "category": "Equity issuance (QIP)", "amount": "Rs.487.74 crores",
             "purpose": "Proceeds raised under QIP to be utilized as per objects of the issue; utilized up to March 31, 2026: Rs.450.09 crores", "canonical_category": "qualified_institutional_placement",
             "capital_allocation_group": "financing_actions"}


def test_f17_qip_use_of_proceeds_is_a_cumulative_utilisation_not_new_equity_proceeds_or_a_flow():
    c = cand(QIP_GCP)
    assert c["allocation_category"] == "other" and c["amount"] is None and c["amount_basis"] == "cumulative_utilisation_not_a_period_flow"
    assert c["non_flow_amount"]["role"] == "cumulative_utilisation" and c["non_flow_amount"]["value"] == 104.52 and c["use_of_issue_proceeds"] is True


def test_f17_the_issue_itself_stays_an_equity_issuance_with_its_own_size():
    c = cand(QIP_ISSUE)
    assert c["allocation_category"] == "equity_issuance" and c["amount"] == 487.74 and c["non_flow_amount"] is None


def test_f18_a_land_purchase_funded_by_issue_proceeds_is_asset_spending_not_a_business_acquisition_and_not_annual_capex():
    c = cand(QIP_LAND, group="true_capital_deployment")
    assert c["allocation_category"] == "organic_capex" and c["amount"] is None
    assert c["non_flow_amount"]["role"] == "cumulative_utilisation"


def test_f18_use_of_proceeds_never_merges_into_the_annual_flow_record():
    annual = cand({"source_item_id": "capex_fy26", "amount": 72.06, "value": "Capital expenditure", "canonical_category": "capex", "reasoning": "x"}, group="true_capital_deployment")
    land = cand(QIP_LAND, group="true_capital_deployment")
    assert _group_similarity(_build_allocation_group(annual), land) == 0


TANLA_LOAN = {"source_item_id": "c1", "action": "Unsecured loan availed from related party (Karix Mobile Private Limited)", "category": "Debt raised",
              "purpose": "Loan availed during FY 2023-24 from Karix Mobile Private Limited; interest rate 9.75% p.a.", "amount": "INR 13,219.14 lakhs", "canonical_category": "related_party_loan_received",
              "capital_allocation_group": "related_party_capital_flows"}


def test_f19_a_loan_figure_reported_in_a_later_year_is_a_closing_balance_in_its_actual_period():
    assert _amount_role(TANLA_LOAN, "fy26") == ("closing_balance", "fy24")
    c = cand(TANLA_LOAN, group="related_party_capital_flows")
    assert c["amount"] is None and c["non_flow_amount"]["role"] == "closing_balance" and c["named_period"] == "fy24"


def test_f19_a_loan_figure_in_the_year_it_was_availed_remains_a_flow():
    item = {**TANLA_LOAN, "purpose": "Loan availed during FY 2025-26 from a bank"}
    assert _amount_role(item, "fy26")[0] == "period_flow"


def test_f21_a_proposed_dividend_is_not_paid_and_takes_no_paid_amount_from_the_ledger():
    proposed = {"source_item_id": "c23", "action": "Declare final dividend (subject to shareholder approval); payment to be made on or before August 29, 2024", "category": "Dividend",
                "purpose": "Payment of final dividend for the financial year 2023-24", "canonical_category": "dividend_paid", "capital_allocation_group": "shareholder_returns"}
    assert _dividend_lifecycle(proposed) == "proposed"
    c = cand(proposed, year="fy24", group="shareholder_returns", ledger={"dividends": 25.19, "purpose": "x"})
    assert c["amount"] is None and c["lifecycle"] == "proposed"


def test_f21_a_recommended_dividend_never_carries_the_paid_amount_and_stays_announced():
    rec = {"source_item_id": "c19", "action": "Recommended final dividend", "category": "Dividend", "amount": "INR 36.39 Cr; Rs. 6.50 per equity share",
           "purpose": "Final dividend for FY 2023-24, to be paid on or before August 29, 2024 (subject to shareholder approval)", "canonical_category": "dividend_declared",
           "capital_allocation_group": "shareholder_returns"}
    c = cand(rec, year="fy24", group="shareholder_returns", ledger={"dividends": 25.19})
    assert c["amount"] is None and c["lifecycle"] == "proposed" and c["amount_stated"].startswith("INR 36.39")


def test_f21_paid_and_proposed_dividends_are_distinct_events_that_never_merge():
    paid = {"source_item_id": "c18", "action": "Paid final dividend", "category": "Dividend", "purpose": "Final dividend for FY 2022-23 (approved by shareholders at AGM on August 09, 2023)",
            "canonical_category": "dividend_paid", "capital_allocation_group": "shareholder_returns"}
    rec = {"source_item_id": "c19", "action": "Recommended final dividend", "category": "Dividend", "amount": "INR 36.39 Cr", "purpose": "Final dividend for FY 2023-24 (subject to shareholder approval)",
           "canonical_category": "dividend_declared", "capital_allocation_group": "shareholder_returns"}
    p, r = cand(paid, "fy24", "shareholder_returns"), cand(rec, "fy24", "shareholder_returns")
    assert p["lifecycle"] == "paid" and r["lifecycle"] == "proposed"
    assert _group_similarity(_build_allocation_group(p), r) == 0


def test_f17_the_filing_states_the_issue_date_in_the_sentence_after_the_instrument():
    chunks = [{"page": 182, "text": "NOTE 39 : Issue of shares During the financial year 2022-23, the Company allotted Equity shares through Qualified Institutional Placement (QIP) process. "
                                    "These equity shares were allotted on March 13, 2023 and will rank pari-passu."}]
    found = extract_issue_dates(chunks)
    assert found["qip"]["date"] == "2023-03-13" and found["qip"]["period"] == "fy23"


def test_an_ipo_sentence_does_not_lend_its_date_to_a_qip():
    chunks = [{"page": 3, "text": "The Company raised funds through QIP. The equity shares of the Company were listed on December 22, 2021 pursuant to the initial public offer."}]
    found = extract_issue_dates(chunks)
    assert found.get("qip", {}).get("date") != "2021-12-22"


def test_f20_stored_labels_the_items_own_wording_does_not_support_are_replaced_everywhere():
    borrow = {"action": "Proceeds from borrowings", "category": "Debt raised", "purpose": "Proceeds from borrowings (financing inflow)", "canonical_category": "debt_repaid",
              "capital_allocation_group": "financing_actions", "cash_flow_effect": "company_cash_outflow", "balance_sheet_effect": "liability_reduction",
              "reasoning": "Matched taxonomy keyword 'repayment of borrowings' to debt_repaid."}
    r = apply_label_verdict(borrow)
    assert (r["canonical_category"], r["cash_flow_effect"], r["balance_sheet_effect"]) == ("debt_raised", "company_cash_inflow", "liability_increase")
    sanction = {"action": "Debt raised (term loan sanctioned)", "category": "Debt raised", "purpose": "Not stated", "canonical_category": "actuarial_assumption",
                "reasoning": "Matched taxonomy keyword 'actuarial assumption' to actuarial_assumption."}
    assert apply_label_verdict(sanction)["canonical_category"] != "actuarial_assumption"


def test_f20_the_company_layer_applies_the_verdict_before_any_consumer_reads_the_timeline():
    from knowledge.company_memory.company_layer import _capital_items
    cim = {"financial": {"capital_allocation": {"items": [{"id": "CAPALLOC_00001", "action": "Dividend paid", "category": "Dividend", "purpose": "Distribution of profit to shareholders",
                                                          "canonical_category": "actuarial_assumption", "capital_allocation_group": "accounting_or_disclosure_only",
                                                          "reasoning": "Matched taxonomy keyword 'actuarial assumption' to actuarial_assumption."}]}}}
    items = _capital_items(cim, {}, "fy22")
    assert items[0]["canonical_category"] != "actuarial_assumption" and items[0]["classification_status"] in {"reclassified_from_own_text", "quarantined_unsupported"}


# event identity -----------------------------------------------------------------------------------------------------------------------------------------------------
def _c(action, category, **extra):
    base = {"source_item_id": action[:12], "action": action, "purpose": action, "category": category, "canonical_category": extra.pop("canonical_category", "qualified_institutional_placement"), "capital_allocation_group": "financing_actions"}
    return cand({**base, **extra}, year=extra.get("year", "fy26"), group="financing_actions")


def test_a_paid_dividend_never_merges_with_a_proposed_one_but_an_unstated_one_may_be_the_paid_one():
    from intelligence.capital_allocation_outcomes.builder import _same_event_kind
    mk = lambda action, purpose="x": cand({"source_item_id": action, "action": action, "category": "Dividend", "purpose": purpose, "canonical_category": "dividend_paid", "capital_allocation_group": "shareholder_returns"}, "fy25", "shareholder_returns")
    paid, proposed, payout = mk("Dividend paid"), mk("Recommended final dividend", "subject to shareholder approval"), mk("Dividend payout")
    assert not _same_event_kind(paid, proposed) and not _same_event_kind(payout, proposed) and _same_event_kind(paid, payout)


def test_uses_of_different_issues_or_different_objects_never_merge_but_wordings_of_one_object_do():
    from intelligence.capital_allocation_outcomes.builder import _same_event_kind
    qip_land = _c("Allocation of QIP proceeds for land acquisition", "Land acquisition", amount="Rs. 7.75 Crores")
    qip_land2 = _c("Funding acquisition of land (including building) (QIP proceeds)", "Land acquisition", amount="Rs. 7.75 Crores")
    qip_emi = _c("Allocation of QIP proceeds for EMI-EMC testing facility capex", "Capex spending", amount="Rs. 15.23 Crores")
    ipo_up = _c("Use of IPO proceeds — Upgradation and expansion of existing facility", "Capex spending", amount="Rs. 51.33 Crores")
    ipo_up2 = _c("Upgradation and expansion of existing facilities (IPO proceeds)", "Capex spending", amount="Rs. 51.33 Crores")
    qip_up = _c("Allocation of QIP proceeds for upgradation and expansion of existing facility", "Capex spending", amount="Rs. 9 Crores")
    assert _same_event_kind(qip_land, qip_land2) and _same_event_kind(ipo_up, ipo_up2)
    assert not _same_event_kind(qip_land, qip_emi) and not _same_event_kind(ipo_up, qip_up) and not _same_event_kind(qip_land, ipo_up)


def test_a_closing_balance_never_merges_with_a_period_flow_of_the_same_loan():
    from intelligence.capital_allocation_outcomes.builder import _same_event_kind
    balance = cand(TANLA_LOAN, "fy26", "related_party_capital_flows")
    flow = cand({**TANLA_LOAN, "source_item_id": "x", "purpose": "Loan availed during FY 2025-26 from a bank", "action": "Term loan availed from a bank"}, "fy26", "financing_actions")
    assert balance["non_flow_amount"] and not flow["non_flow_amount"] and not _same_event_kind(balance, flow)


def test_a_loan_amount_with_no_statement_that_it_was_raised_this_year_is_not_a_flow():
    item = {"source_item_id": "u", "action": "Availing unsecured loan from related party", "category": "Debt raised (non-current borrowing)", "purpose": "Unsecured loan from a subsidiary; repayable on demand",
            "amount": "13,219.14 INR Lakhs", "canonical_category": "related_party_loan_received", "capital_allocation_group": "related_party_capital_flows"}
    assert _amount_role(item, "fy26")[0] == "closing_balance"
    assert _amount_role({**item, "purpose": "Unsecured loan availed during the year from a subsidiary"}, "fy26")[0] == "period_flow"


def test_an_id_keeps_its_historical_name_when_longer_wording_is_merged_into_it():
    from intelligence.projects.builder import _keep_historical_identity
    prior = {"capacity_items": [{"capacity_id": "CP-0001", "capacity_name": "Floor area and manufacturing capacity (doubling)", "normalized_name": "floor area and manufacturing capacity (doubling)"}]}
    group = {"capacity_name": "Satellite systems manufacturing capacity (space and full satellites)", "normalized_name": "satellite systems manufacturing capacity (space and full satellites)"}
    _keep_historical_identity([group], ["CP-0001"], prior, registry_key="capacity_items", id_key="capacity_id", name_key="capacity_name")
    assert group["capacity_name"] == "Floor area and manufacturing capacity (doubling)" and group["name_aliases"] == ["Satellite systems manufacturing capacity (space and full satellites)"]
    fresh = {"capacity_name": "New thing", "normalized_name": "new thing"}
    _keep_historical_identity([fresh], ["CP-0009"], prior, registry_key="capacity_items", id_key="capacity_id", name_key="capacity_name")
    assert fresh["capacity_name"] == "New thing" and "name_aliases" not in fresh


def test_a_dividend_to_minority_holders_never_merges_with_the_dividend_to_shareholders():
    from intelligence.capital_allocation_outcomes.builder import _same_event_kind
    mk = lambda action: cand({"source_item_id": action, "action": action, "purpose": action, "category": "Dividend", "canonical_category": "dividend_paid", "capital_allocation_group": "shareholder_returns"}, "fy20", "shareholder_returns")
    assert not _same_event_kind(mk("Dividend payment to non-controlling interests"), mk("Dividend paid to shareholders"))
    assert _same_event_kind(mk("Dividend paid to shareholders"), mk("Dividend paid"))
