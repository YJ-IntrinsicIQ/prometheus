"""SSOT critical closure F17 / F18 / F21: distinct issue instruments are distinct events, an asset purchase is capital expenditure in EVERY field, a proposed dividend is not a completed
distribution on any surface, and a QIP's proceeds are named gross / net with the issue expenses beside them."""
from intelligence.capital_allocation_outcomes.builder import (
    _build_allocation_group, _candidate_from_item, _causal_attribution_states, _determine_outcome_attribution, _group_similarity, _issue_instrument, _map_allocation_category,
    _pending_distribution,
)
from knowledge.capital_allocation_taxonomy import resolve_economic_role
from knowledge.company_memory.guardrails import extract_issue_economics
from intelligence.economic_attribution.builder import _build_cao_cases


def cand(item, year="fy26", group="financing_actions"):
    return _candidate_from_item(year, item, group, {})


def item(source_id, action, canonical, group="financing_actions", **kw):
    return {"source_item_id": source_id, "value": action, "action": action, "category": action, "canonical_category": canonical, "capital_allocation_group": group, **kw}


# ---- F17: one record per issue instrument -----------------------------------------------------------------------------------------------------------------------------------------------

def test_a_qip_an_ipo_bonus_shares_and_a_private_placement_are_four_events_that_never_merge():
    qip = cand(item("a", "Equity issuance (Qualified Institutional Placement) — proceeds raised", "qualified_institutional_placement", amount="Rs.487.74 crores"))
    ipo = cand(item("b", "Equity issuance (IPO primary proceeds)", "equity_issuance", amount="INR 281.42 Crore (net)"), year="fy22")
    bonus = cand(item("c", "Issued and allotted bonus equity shares", "equity_issuance"), year="fy24")
    private = cand(item("d", "Equity issuance (Private Placement)", "equity_issuance", amount="INR 60 Cr"), year="fy22")
    assert [_issue_instrument(c) for c in (qip, ipo, bonus, private)] == ["qip", "ipo", "bonus", "private_placement"]
    candidates = [qip, ipo, bonus, private]
    for first in candidates:
        group = _build_allocation_group(first)
        assert all(_group_similarity(group, other) == 0 for other in candidates if other is not first)


def test_a_group_is_judged_against_every_member_not_only_the_first():
    qip, later_qip = cand(item("a", "Equity issuance (QIP)", "qualified_institutional_placement", amount="Rs.487.74 crores")), cand(item("e", "Equity issued through QIP (premium received)", "equity_issuance"), year="fy24")
    group = _build_allocation_group(qip)
    from intelligence.capital_allocation_outcomes.builder import _merge_group
    _merge_group(group, later_qip)
    bonus = cand(item("c", "Issued and allotted bonus equity shares", "equity_issuance"), year="fy25")
    assert _group_similarity(group, bonus) == 0


def test_a_repayment_of_borrowings_is_not_filed_as_an_equity_issuance_whatever_its_purpose_text_says():
    repayment = item("r", "Repayment of borrowings", "debt_repaid", amount="Rs. 60.08 Crore", purpose="Prepayment/repayment of outstanding borrowings (repaid out of IPO & QIP proceeds); equity issuance proceeds")
    assert _map_allocation_category(repayment, {}) == "debt_repayment"
    issue = cand(item("a", "Equity issuance (QIP)", "qualified_institutional_placement", amount="Rs.487.74 crores"))
    assert _group_similarity(_build_allocation_group(issue), cand(repayment)) == 0


def test_the_filing_states_gross_proceeds_through_shares_and_price_and_the_expenses_beside_the_net_total():
    chunks = [{"page": 170, "text": "During the FY 22-23, the Company allotted 40,97,319 Equity shares of Rs. 2/- each at an issue price of Rs. 1,220.31 per equity share through Qualified Institutional Placement"},
              {"page": 182, "text": "The Company has spent INR 12.24 Crores towards the Qualified Institutional Placement process and the same is adjusted in Securities Premium account"}]
    economics = extract_issue_economics(chunks)
    assert economics["shares"] == 4097319 and economics["issue_price"] == 1220.31 and economics["gross_crore"] == 500.0 and economics["issue_expenses_crore"] == 12.24
    assert abs(487.74 + economics["issue_expenses_crore"] - economics["gross_crore"]) < 0.1            # net objects total + expenses = gross: the three reconcile


def test_nothing_is_inferred_when_the_filing_states_no_price_or_expenses():
    assert extract_issue_economics([{"page": 1, "text": "The Company raised funds through a QIP."}]) == {}


def test_bonus_shares_are_a_non_cash_capitalisation_not_a_capital_source():
    role = resolve_economic_role({"action": "Issued and allotted bonus equity shares", "category": "Equity issuance", "canonical_category": "equity_issuance", "capital_allocation_group": "financing_actions"})
    assert role["economic_role"] == "NON_CASH_CAPITALISATION" and role["deployment_eligibility"] != "INELIGIBLE_CAPITAL_SOURCE"


# ---- F18: asset spending is capital expenditure in every field --------------------------------------------------------------------------------------------------------------------------

def test_land_bought_with_issue_proceeds_is_organic_capex_in_category_and_in_economic_role():
    land = item("l", "Allocation of QIP proceeds for land acquisition", "qualified_institutional_placement", purpose="Funding acquisition of land (including building)", amount="Rs. 7.75 Crores")
    category = _map_allocation_category(land, {})
    role = resolve_economic_role({"action": "Funding acquisition of land (including building) (QIP proceeds)", "category": category, "canonical_category": category, "capital_allocation_group": "financing_actions"})
    assert category == "organic_capex" and role["economic_role"] == "DEPLOYMENT_ORGANIC_CAPEX"


def test_organic_capex_never_carries_an_acquisition_role_without_a_source_supported_distinction():
    for text in ("Acquisition of land for the plant", "Purchase of building", "Acquisition of machinery"):
        role = resolve_economic_role({"action": text, "category": "organic_capex", "canonical_category": "organic_capex"})
        assert role["economic_role"] == "DEPLOYMENT_ORGANIC_CAPEX", text


def test_a_real_business_acquisition_keeps_its_acquisition_role():
    role = resolve_economic_role({"action": "Acquisition of 100% stake in Acme Technologies", "category": "acquisition", "canonical_category": "acquisitions"})
    assert role["economic_role"] == "DEPLOYMENT_ACQUISITION"
    assert resolve_economic_role({"action": "Acquisition of land", "category": "acquisition", "canonical_category": "acquisition"})["economic_role"] == "DEPLOYMENT_ACQUISITION"


# ---- F21: a proposed dividend is not a completed distribution ----------------------------------------------------------------------------------------------------------------------------

def record(lifecycle, category="dividend"):
    return {"allocation_category": category, "lifecycle": lifecycle, "current_status": "announced" if lifecycle != "paid" else "deployed", "outcome_status": "no_outcome_evidence", "execution_state": ""}


def test_a_proposed_dividend_has_no_distribution_outcome_on_any_semantic_layer():
    states = _causal_attribution_states(record("proposed"), [])
    assert _pending_distribution(record("proposed")) and _pending_distribution(record(None))
    assert states["execution_state"] == "NOT_STARTED" and states["financial_outcome_state"] == "UNABLE_TO_ATTRIBUTE"
    assert states["per_share_consequence_state"] == "UNABLE_TO_ATTRIBUTE" and states["causal_attribution_confidence"] == "UNKNOWN"
    assert states["outcome_attribution"] == "NO_OUTCOME_EVIDENCE" and _determine_outcome_attribution(record("proposed"), []) == "NO_OUTCOME_EVIDENCE"


def test_a_paid_dividend_is_a_completed_distribution_with_a_direct_outcome():
    states = _causal_attribution_states(record("paid"), [])
    assert states["execution_state"] == "COMPLETED" and states["financial_outcome_state"] == "CASH_FLOW_EFFECT" and states["outcome_attribution"] == "DIRECTLY_ATTRIBUTABLE"
    assert states["per_share_consequence_state"] == "OWNER_EARNINGS_EFFECT"


def test_a_buyback_is_unaffected_by_the_dividend_lifecycle_rule():
    assert _causal_attribution_states(record(None, "share_buyback"), [])["outcome_attribution"] == "DIRECTLY_ATTRIBUTABLE"


def test_economic_attribution_does_not_copy_a_completed_distribution_onto_a_proposal():
    data = {"allocations": [{"allocation_id": "CAO-1", "allocation_category": "dividend", "allocation_name": "Recommended final dividend", "lifecycle": "proposed", "execution_state": "NOT_STARTED",
                             "outcome_attribution": "NO_OUTCOME_EVIDENCE", "deployment_state": "ANNOUNCED", "deployment_periods": ["fy24"]},
                            {"allocation_id": "CAO-2", "allocation_category": "dividend", "allocation_name": "Dividend paid to shareholders", "lifecycle": "paid", "execution_state": "COMPLETED",
                             "outcome_attribution": "DIRECTLY_ATTRIBUTABLE", "deployment_state": "DEPLOYED", "deployment_periods": ["fy24"], "amount": 25.19}]}
    proposed, paid = _build_cao_cases(data, 700.0)
    assert proposed["economic_consequence"] == "unknown" and proposed["financial_consequence"] == "none_disclosed" and proposed["per_share_consequence"] is None
    assert "not evidenced" in proposed["operating_outcome"]
    assert paid["economic_consequence"] == "per_share_owner_value_change" and paid["per_share_consequence"]
