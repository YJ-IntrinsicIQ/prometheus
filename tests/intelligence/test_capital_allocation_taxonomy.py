from knowledge.capital_allocation_taxonomy import (
    normalize_capital_allocation_item,
    validate_capital_allocation_items,
)


def _normalized(action, **overrides):
    item = {"action": action, "category": "", "purpose": "", "amount": None}
    item.update(overrides)
    return normalize_capital_allocation_item(item)


def test_true_capex_classifies_as_true_capital_deployment():
    item = _normalized(
        "New production facility commissioned at cost of 100",
        category="capacity expansion",
        amount="100",
    )

    assert item["capital_allocation_group"] == "true_capital_deployment"
    assert item["canonical_category"] == "capacity_expansion"
    assert item["cash_flow_effect"] == "company_cash_outflow"
    assert item["is_true_capital_deployment"] is True


def test_offer_for_sale_classifies_as_non_company_cashflow():
    item = _normalized(
        "Offer for sale by existing shareholders",
        category="secondary transaction",
    )

    assert item["capital_allocation_group"] == "ownership_transfer_non_company_cashflow"
    assert item["cash_flow_effect"] == "non_company_cashflow"
    assert item["is_true_capital_deployment"] is False


def test_share_split_and_authorized_capital_change_are_not_capex():
    share_split = _normalized(
        "Equity shares split from face value 10 to 5",
        category="share split",
    )
    authorized = _normalized(
        "Authorised share capital increased",
        category="capital structure",
    )

    assert share_split["capital_allocation_group"] == "corporate_actions_non_cash_or_admin"
    assert share_split["cash_flow_effect"] == "non_cash"
    assert authorized["capital_allocation_group"] == "corporate_actions_non_cash_or_admin"
    assert authorized["canonical_category"] == "authorised_capital_change"


def test_debt_repayment_and_treasury_parking_are_separated():
    debt = _normalized(
        "Term loan repaid during the year",
        category="principal repayment",
        amount="50",
    )
    treasury = _normalized(
        "Funds temporarily invested in debt mutual funds",
        category="liquidity management investment",
        amount="25",
    )

    assert debt["capital_allocation_group"] == "financing_actions"
    assert debt["canonical_category"] == "debt_repaid"
    assert debt["cash_flow_effect"] == "company_cash_outflow"
    assert treasury["capital_allocation_group"] == "treasury_actions"
    assert treasury["cash_flow_effect"] == "cash_reallocation"
    assert treasury["is_true_capital_deployment"] is False


def test_accounting_policy_and_related_party_loan_are_not_treated_as_capex():
    accounting = _normalized(
        "Depreciation policy updated",
        category="significant accounting policies",
    )
    related_party = _normalized(
        "Loan given to related party",
        category="related party loan",
        amount="40",
    )

    assert accounting["capital_allocation_group"] == "accounting_or_disclosure_only"
    assert accounting["is_true_capital_deployment"] is False
    assert related_party["capital_allocation_group"] == "related_party_capital_flows"
    assert related_party["is_related_party"] is True


def test_uncertain_items_are_preserved_with_warning():
    item = _normalized("General corporate matter under review")
    validation = validate_capital_allocation_items([item])

    assert item["capital_allocation_group"] == "uncertain"
    assert item["canonical_category"] == "uncertain"
    assert any("uncertain category" in warning for warning in validation["warnings"])


def test_validator_rejects_source_chunk_and_bad_grouping():
    item = _normalized(
        "Accounting policy updated",
        category="significant accounting policies",
    )
    item["source_chunk"] = "raw chunk should not survive cleaning"
    item["capital_allocation_group"] = "true_capital_deployment"
    item["is_true_capital_deployment"] = True

    validation = validate_capital_allocation_items([item])

    assert any("source_chunk" in error for error in validation["errors"])
    assert any("non-deployment item cannot be grouped as true_capital_deployment" in error for error in validation["errors"])
