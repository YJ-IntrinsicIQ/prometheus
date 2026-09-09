from knowledge.capital_allocation_taxonomy import normalize_capital_allocation_item


def item(action, category="", amount="100 crore"):
    return normalize_capital_allocation_item({"action": action, "category": category, "amount": amount})


def test_balance_stock_is_not_deployment():
    x = item("Aggregate unquoted investments balance", "investments")
    assert x["economic_role"] == "BALANCE_SHEET_STOCK"
    assert x["deployment_eligibility"] == "INELIGIBLE_BALANCE_STOCK"


def test_sources_and_sanctions_are_not_deployment():
    assert item("Equity issuance proceeds received", "equity issue")["deployment_eligibility"] == "INELIGIBLE_CAPITAL_SOURCE"
    assert item("Bank facility sanctioned", "facility")["deployment_eligibility"] == "INELIGIBLE_ANNOUNCED_NOT_DEPLOYED"


def test_disposal_is_not_acquisition_deployment():
    x = item("Sale of subsidiary and disposal proceeds received", "disposal")
    assert x["deployment_eligibility"] == "INELIGIBLE_DISPOSAL_PROCEEDS"


def test_uses_remain_eligible_and_unknown_stays_qualitative():
    assert item("Capital expenditure paid for new production facility", "capex")["deployment_eligibility"] == "ELIGIBLE_DEPLOYMENT"
    assert item("Term loan repayment", "debt repayment")["deployment_eligibility"] == "ELIGIBLE_DELEVERAGING"
    assert item("Narrative investment reference", "other")["deployment_eligibility"] == "ELIGIBILITY_AMBIGUOUS"


def test_distribution_is_distinct_from_reinvestment():
    x = item("Dividend paid to shareholders", "dividend")
    assert x["economic_role"] == "DISTRIBUTION_DIVIDEND"
    assert x["deployment_eligibility"] == "ELIGIBLE_DISTRIBUTION"


def test_same_amount_does_not_imply_same_flow():
    a = item("Sale consideration received", "disposal")
    b = item("Loan repayment", "debt repayment")
    assert a["economic_flow_relation"] == "DISTINCT_FLOW"
    assert b["economic_flow_relation"] == "DISTINCT_FLOW"

