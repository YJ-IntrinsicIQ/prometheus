import json

from core.company_context import CompanyContext
from knowledge.cim_builder import build_company_intelligence
from pipelines.pipeline_context import set_context


def test_cim_builder_uses_classification_as_official_dna_source(tmp_path, monkeypatch):
    context = CompanyContext(company="sample_manufacturing_co", year="fy25")
    monkeypatch.chdir(tmp_path)
    context.create_directories()
    set_context(context)

    (context.intelligence_dir / "business_blueprint.json").write_text(
        json.dumps(
            {
                "metadata": {"company": "Sample", "version": "1.0", "confidence": 0.7},
                "business_understanding": {
                    "business_summary": "Builds physical products.",
                    "business_model": "Production-led business.",
                    "value_creation": "Creates value through production assets.",
                    "competitive_position": "Competes through execution.",
                },
                "characteristics": [{"name": "Asset-heavy production", "confidence": 0.8}],
                "candidate_dna_signals": [
                    {
                        "name": "Manufacturing",
                        "confidence": 0.82,
                        "supporting_reason": "Production assets and operating model support manufacturing.",
                        "evidence_ids": [],
                    }
                ],
                "dnas": [],
                "reasoning": [{"statement": "Reasoning present."}],
            }
        ),
        encoding="utf-8",
    )
    (context.intelligence_dir / "business_classification.json").write_text(
        json.dumps(
            {
                "business_dnas": ["Manufacturing"],
                "question_modules": ["capital_allocation"],
                "report_template": "manufacturing_v1",
                "rationale": ["Production evidence dominates the business description."],
                "evidence_used": ["Builds physical products."],
                "confidence": 0.81,
                "rejected_dnas": [],
            }
        ),
        encoding="utf-8",
    )

    cim = build_company_intelligence()
    manifest = cim["business"]["identity_manifest"]

    assert cim["business"]["dna"]["business_dnas"] == ["Manufacturing"]
    assert manifest["official_dna_source"] == "business_classification.json"
    assert manifest["official_business_dnas"] == ["Manufacturing"]
    assert manifest["conflict_status"] in {"pass", "warning"}


def test_cim_builder_preserves_capital_allocation_taxonomy_fields(tmp_path, monkeypatch):
    context = CompanyContext(company="sample_capital_co", year="fy25")
    monkeypatch.chdir(tmp_path)
    context.create_directories()
    set_context(context)

    (context.intelligence_dir / "business_blueprint.json").write_text(
        json.dumps(
            {
                "metadata": {"company": "Sample", "version": "1.0", "confidence": 0.7},
                "business_understanding": {
                    "business_summary": "Builds products.",
                    "business_model": "Asset-backed business.",
                    "value_creation": "Deploys capital into production capacity.",
                    "competitive_position": "Competes through execution.",
                },
                "characteristics": [{"name": "Asset-heavy production", "confidence": 0.8}],
                "candidate_dna_signals": [],
                "dnas": [],
                "reasoning": [{"statement": "Reasoning present."}],
            }
        ),
        encoding="utf-8",
    )
    (context.intelligence_dir / "business_classification.json").write_text(
        json.dumps(
            {
                "business_dnas": ["Manufacturing"],
                "question_modules": ["capital_allocation"],
                "report_template": "manufacturing_v1",
                "rationale": ["Capital deployment is a core signal."],
            }
        ),
        encoding="utf-8",
    )
    (context.extracted_dir / "clean_capital_allocation.json").write_text(
        json.dumps(
            [
                {
                    "action": "Funds temporarily invested in debt mutual funds",
                    "category": "liquidity management investment",
                    "amount": "25",
                    "canonical_category": "mutual_fund_investment",
                    "capital_allocation_group": "treasury_actions",
                    "cash_flow_effect": "cash_reallocation",
                    "balance_sheet_effect": "cash_reallocation",
                    "is_true_capital_deployment": False,
                    "is_shareholder_return": False,
                    "is_financing_action": False,
                    "is_corporate_action": False,
                    "is_related_party": False,
                    "currency": None,
                    "reasoning": "Matched treasury investment keywords.",
                    "confidence": "high",
                    "page": 12,
                }
            ]
        ),
        encoding="utf-8",
    )

    cim = build_company_intelligence()
    item = cim["financial"]["capital_allocation"]["items"][0]

    assert item["canonical_category"] == "mutual_fund_investment"
    assert item["capital_allocation_group"] == "treasury_actions"
    assert item["cash_flow_effect"] == "cash_reallocation"
    assert item["is_true_capital_deployment"] is False
