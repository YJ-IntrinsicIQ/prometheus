from synthesis import management_summary_generator as generator


def test_company_action_and_promise_are_company_controlled():
    profile = {
        "projects": [
            {
                "project_name": "The company commissioned a new facility",
                "category": "capacity expansion",
            }
        ],
        "promises": [
            {
                "promise": "Management plans to expand into new markets",
                "category": "growth plan",
            }
        ],
        "initiatives": [],
        "capital_allocation": [],
    }

    summary = generator.build_summary(profile, business_context={"business_dnas": ["Manufacturing"]})

    company_items = summary["company_management_actions"] + summary["company_results"]
    assert company_items[0]["context_type"] in {"company_action", "company_result"}
    assert company_items[0]["agency"] == "company_controlled"
    assert company_items[0]["should_feed_management_consistency"] is True
    assert summary["company_promises"][0]["context_type"] == "company_promise"
    assert summary["company_promises"][0]["agency"] == "management_committed"


def test_external_policy_and_macro_are_routed_out_of_management_focus():
    profile = {
        "projects": [],
        "promises": [],
        "initiatives": [
            {
                "initiative": "Government increased sector budget allocation",
                "category": "policy backdrop",
            },
            {
                "initiative": "GDP growth improved during the year",
                "category": "macro backdrop",
            },
        ],
        "capital_allocation": [],
    }

    summary = generator.build_summary(profile, business_context={"business_dnas": ["Manufacturing"]})

    assert summary["management_focus_areas"] == []
    assert len(summary["external_context"]) == 2
    assert all(item["agency"] == "external_not_controlled" for item in summary["external_context"])
    assert all(item["should_feed_management_consistency"] is False for item in summary["external_context"])


def test_accounting_and_governance_disclosures_are_not_treated_as_strategy():
    profile = {
        "projects": [],
        "promises": [],
        "initiatives": [
            {
                "initiative": "Depreciation is calculated using useful life estimates",
                "category": "accounting policy",
            },
            {
                "initiative": "Audit committee reviewed internal controls",
                "category": "governance",
            },
        ],
        "capital_allocation": [],
    }

    summary = generator.build_summary(profile, business_context={"business_dnas": ["Enterprise Platform"]})

    assert summary["management_focus_areas"] == []
    assert summary["accounting_disclosures"][0]["context_type"] == "accounting_disclosure"
    assert summary["accounting_disclosures"][0]["should_feed_company_strategy"] is False
    assert summary["governance_disclosures"][0]["context_type"] == "governance_disclosure"
    assert summary["governance_disclosures"][0]["should_feed_management_consistency"] is False


def test_mixed_policy_and_company_action_preserves_company_signal_and_routes_context():
    profile = {
        "projects": [],
        "promises": [],
        "initiatives": [
            {
                "initiative": "Company benefited from favorable policy support and expanded capacity",
                "category": "capacity expansion",
            }
        ],
        "capital_allocation": [],
    }

    summary = generator.build_summary(profile, business_context={"business_dnas": ["Manufacturing"]})

    assert summary["key_initiatives"] == ["Company benefited from favorable policy support and expanded capacity"]
    assert summary["company_management_actions"] or summary["company_capabilities"] or summary["company_results"]
    assert summary["external_context"]
    assert summary["external_context"][0]["agency"] == "mixed"


def test_routing_validation_passes_and_no_grouped_item_leaks_source_chunk():
    profile = {
        "projects": [],
        "promises": [],
        "initiatives": [
            {
                "initiative": "The company commissioned a new facility",
                "category": "capacity expansion",
                "source_chunk": "raw source should not survive grouped summary",
            }
        ],
        "capital_allocation": [],
    }

    summary = generator.build_summary(profile, business_context={"business_dnas": ["Manufacturing"]})

    assert summary["routing_validation"]["status"] == "pass"
    serialized = str(summary["company_management_actions"])
    assert "source_chunk" not in serialized
