import json

from knowledge.cim_contract import CIMContractBuilder
from knowledge.company_memory.pcim_multi_year_builder import audit_saved_pcim_manifest


def _write_year_artifacts(base_dir, company, year):
    intelligence_dir = base_dir / "companies" / company / year / "intelligence"
    intelligence_dir.mkdir(parents=True, exist_ok=True)
    (intelligence_dir / "business_classification.json").write_text(
        json.dumps(
            {
                "business_dnas": ["Enterprise Platform"],
                "question_modules": ["technology", "platform_dependency", "platform_economics"],
                "report_template": "software_v1",
                "rationale": ["Platform evidence dominates the business description."],
                "evidence_used": ["API-first platform architecture"],
                "confidence": 0.83,
                "rejected_dnas": [{"name": "Compliance Infrastructure", "reason": "Supportive but not primary."}],
            }
        ),
        encoding="utf-8",
    )
    (intelligence_dir / "business_blueprint.json").write_text(
        json.dumps(
            {
                "metadata": {"company": company, "version": "1.0", "confidence": 0.78},
                "business_understanding": {
                    "business_summary": "Runs an enterprise platform.",
                    "business_model": "Subscription-led software platform.",
                    "value_creation": "Creates value through platform workflows.",
                    "competitive_position": "Competes via platform embeddedness.",
                },
                "characteristics": [{"name": "API-first platform architecture", "confidence": 0.9}],
                "candidate_dna_signals": [
                    {
                        "name": "Enterprise Platform",
                        "confidence": 0.84,
                        "supporting_reason": "Platform workflows and architecture support this candidate.",
                        "evidence_ids": [],
                    }
                ],
                "dnas": [],
                "reasoning": [{"statement": "Reasoning present."}],
            }
        ),
        encoding="utf-8",
    )
    (intelligence_dir / "management_summary.json").write_text(
        json.dumps(
            {
                "management_focus_areas": [f"{year} Focus"],
                "major_projects": [f"{year} Project"],
                "major_promises": [f"{year} Promise"],
                "key_initiatives": [f"{year} Initiative"],
                "capital_allocation_actions": [f"{year} Capital"],
                "statistics": {},
            }
        ),
        encoding="utf-8",
    )
    (intelligence_dir / "company_intelligence.json").write_text(
        json.dumps(
            {
                "metadata": {"company": company, "year": year},
                "business": {
                    "dna": {
                        "business_dnas": ["Enterprise Platform"],
                        "question_modules": ["technology", "platform_dependency", "platform_economics"],
                        "report_template": "software_v1",
                    },
                    "industry_profile": {
                        "business_summary": "Runs an enterprise platform.",
                        "business_model": "Subscription-led software platform.",
                        "value_creation": "Creates value through platform workflows.",
                        "characteristics": ["API-first platform architecture"],
                    },
                    "competitive_position": {
                        "summary": "Competes via platform embeddedness.",
                        "supporting_modules": ["technology", "platform_dependency", "platform_economics"],
                    },
                },
                "management": {"promises": {"items": []}},
                "operations": {"projects": {"items": []}, "initiatives": {"items": []}},
                "financial": {"capital_allocation": {"items": []}},
                "risk": {"identified": {"items": []}},
                "relationships": {"entities": [], "graph": {}},
                "evidence": {"sources": [], "citations": []},
            }
        ),
        encoding="utf-8",
    )


def test_pcim_builder_uses_official_classification_dnas_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "sample_platform_co", "fy25")

    written = CIMContractBuilder(company="sample_platform_co").build()
    pcim = json.loads(written["pcim_v1.json"].read_text())

    assert pcim["business_understanding"]["latest_business_view"]["business_dnas"][0]["value"] == "Enterprise Platform"
    assert pcim["business_identity_manifest"]["official_business_dnas"] == ["Enterprise Platform"]
    assert pcim["business_identity_manifest"]["official_dna_source"] == "business_classification.json"


def test_pcim_freshness_audit_detects_new_multi_year_source_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "sample_platform_co", "fy25")

    first = json.loads(CIMContractBuilder(company="sample_platform_co").build()["pcim_v1.json"].read_text())

    multi_year_dir = tmp_path / "companies" / "sample_platform_co" / "company_memory" / "multi_year"
    multi_year_dir.mkdir(parents=True, exist_ok=True)
    (multi_year_dir / "company_year_index.json").write_text(
        json.dumps({"available_years": ["fy24", "fy25"], "years_detected": ["fy24", "fy25"]}),
        encoding="utf-8",
    )
    (multi_year_dir / "multi_year_index.json").write_text(
        json.dumps({"years_covered": ["fy24", "fy25"], "limitations": []}),
        encoding="utf-8",
    )

    freshness = audit_saved_pcim_manifest(
        tmp_path / "companies" / "sample_platform_co",
        first["pcim_source_manifest"],
        saved_multi_year_inputs=first["multi_year_inputs"],
        expected_years=first.get("available_years", []),
    )

    assert freshness["status"] == "fail"
    assert any("years_available is stale" in item for item in freshness["failures"])


def test_pcim_capital_allocation_inputs_keep_treasury_and_corporate_actions_out_of_true_deployment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "sample_platform_co", "fy25")

    intelligence_path = tmp_path / "companies" / "sample_platform_co" / "fy25" / "intelligence" / "company_intelligence.json"
    payload = json.loads(intelligence_path.read_text())
    payload["financial"]["capital_allocation"]["items"] = [
        {
            "id": "CAP-1",
            "action": "Funds temporarily invested in debt mutual funds",
            "category": "liquidity management investment",
            "canonical_category": "mutual_fund_investment",
            "capital_allocation_group": "treasury_actions",
            "cash_flow_effect": "cash_reallocation",
            "balance_sheet_effect": "cash_reallocation",
            "is_true_capital_deployment": False,
            "is_shareholder_return": False,
            "is_financing_action": False,
            "is_corporate_action": False,
            "is_related_party": False,
            "confidence": "high",
            "page": 12,
        },
        {
            "id": "CAP-2",
            "action": "Share split approved",
            "category": "equity split",
            "canonical_category": "share_split",
            "capital_allocation_group": "corporate_actions_non_cash_or_admin",
            "cash_flow_effect": "non_cash",
            "balance_sheet_effect": "equity_restructure",
            "is_true_capital_deployment": False,
            "is_shareholder_return": False,
            "is_financing_action": False,
            "is_corporate_action": True,
            "is_related_party": False,
            "confidence": "medium",
            "page": 13,
        },
        {
            "id": "CAP-3",
            "action": "New production facility commissioned",
            "category": "capacity expansion",
            "canonical_category": "capacity_expansion",
            "capital_allocation_group": "true_capital_deployment",
            "cash_flow_effect": "company_cash_outflow",
            "balance_sheet_effect": "asset_increase",
            "is_true_capital_deployment": True,
            "is_shareholder_return": False,
            "is_financing_action": False,
            "is_corporate_action": False,
            "is_related_party": False,
            "confidence": "high",
            "page": 14,
        },
    ]
    intelligence_path.write_text(json.dumps(payload), encoding="utf-8")

    written = CIMContractBuilder(company="sample_platform_co").build()
    pcim = json.loads(written["pcim_v1.json"].read_text())
    inputs = pcim["capital_allocation_inputs"]

    assert [item["canonical_category"] for item in inputs["true_capital_deployment_by_year"][0]["items"]] == [
        "capacity_expansion"
    ]
    assert [item["canonical_category"] for item in inputs["treasury_actions_by_year"][0]["items"]] == [
        "mutual_fund_investment"
    ]
    assert [item["canonical_category"] for item in inputs["corporate_actions_by_year"][0]["items"]] == [
        "share_split"
    ]


def test_pcim_management_quality_excludes_external_context_and_business_context_preserves_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(tmp_path, "sample_platform_co", "fy25")

    intelligence_path = tmp_path / "companies" / "sample_platform_co" / "fy25" / "intelligence" / "management_summary.json"
    summary = json.loads(intelligence_path.read_text())
    summary["external_context"] = [
        {
            "value": "Government increased sector budget allocation",
            "context_type": "external_tailwind",
            "agency": "external_not_controlled",
            "should_feed_management_consistency": False,
            "should_feed_company_strategy": False,
            "should_feed_external_context": True,
            "reasoning": "Policy backdrop rather than management action.",
            "evidence_ids": [],
            "confidence": "medium",
            "source_item_id": "INIT-EXT-fy25",
            "category": "policy backdrop",
        }
    ]
    summary["company_management_actions"] = [
        {
            "value": "The company launched an API-led platform capability",
            "context_type": "company_action",
            "agency": "company_controlled",
            "should_feed_management_consistency": True,
            "should_feed_company_strategy": True,
            "should_feed_external_context": False,
            "reasoning": "Company-controlled action.",
            "evidence_ids": ["ev_fy25_management_summary_json_init_00001"],
            "confidence": "high",
            "source_item_id": "INIT-API-fy25",
            "category": "Platform Launch",
        }
    ]
    intelligence_path.write_text(json.dumps(summary), encoding="utf-8")

    written = CIMContractBuilder(company="sample_platform_co").build()
    pcim = json.loads(written["pcim_v1.json"].read_text())

    assert pcim["management_quality_inputs"]["management_focus_by_year"][0]["items"][0]["value"] == "fy25 Focus"
    assert pcim["management_quality_inputs"]["management_grouped_by_year"][0]["company_management_actions"][0]["category"] == "Platform Launch"
    assert pcim["business_context"]["external_context_by_year"][0]["items"][0]["context_type"] == "external_tailwind"
    assert all(
        item.get("context_type") != "external_tailwind"
        for bucket in pcim["management_quality_inputs"]["management_focus_by_year"]
        for item in bucket.get("items", [])
    )
