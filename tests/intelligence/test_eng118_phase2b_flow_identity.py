from knowledge.capital_allocation_taxonomy import normalize_capital_allocation_item


def test_explicit_transaction_identity_is_authoritative_same_flow():
    x = normalize_capital_allocation_item({"action": "Acquisition payment", "transaction_id": "TX-1", "amount": "100 crore"})
    assert x["economic_flow_relation"] == "SAME_ECONOMIC_FLOW"
    assert x["economic_flow_authority"] == "EXPLICIT_STRUCTURED_ID"


def test_sale_and_debt_setoff_are_linked_but_distinct():
    x = normalize_capital_allocation_item({"action": "Sale consideration adjusted against loan payable", "category": "debt repayment", "amount": "100 crore"})
    assert x["economic_flow_relation"] == "LINKED_BUT_DISTINCT_FLOW"
    assert x["economic_flow_authority"] == "EXPLICIT_SOURCE_STATEMENT"
    assert x["deployment_eligibility"] == "ELIGIBLE_DELEVERAGING"


def test_equal_amount_without_authority_is_not_same_flow():
    a = normalize_capital_allocation_item({"action": "Asset sold", "amount": "100 crore"})
    b = normalize_capital_allocation_item({"action": "Debt repaid", "amount": "100 crore"})
    assert a["economic_flow_relation"] != "SAME_ECONOMIC_FLOW"
    assert b["economic_flow_relation"] != "SAME_ECONOMIC_FLOW"


def test_per_share_amount_remains_unresolved_without_total():
    x = normalize_capital_allocation_item({"action": "Dividend paid", "amount": "₹2 per share"})
    assert x.get("amount") == "₹2 per share"
    assert x["economic_role"] == "DISTRIBUTION_DIVIDEND"
