import json

from core.company_context import CompanyContext
from knowledge.cim_builder import build_company_intelligence
from pipelines.pipeline_context import set_context


def test_build_company_intelligence_populates_business_section_from_upstream_artifacts(
    tmp_path,
    monkeypatch,
):
    context = CompanyContext(company="polymatech", year="fy25")
    monkeypatch.chdir(tmp_path)
    context.create_directories()
    set_context(context)

    (context.intelligence_dir / "business_blueprint.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "company": "Polymatech",
                    "version": "1.0",
                    "confidence": 0.7,
                },
                "business_understanding": {
                    "business_summary": "Builds semiconductor manufacturing capacity.",
                    "business_model": "Manufacturing-led growth with R&D support.",
                    "value_creation": "Creates value through capacity expansion and technology adoption.",
                    "competitive_position": "Competes through manufacturing scale-up and technology adoption.",
                },
                "characteristics": [
                    {"name": "Capital-intensive manufacturing buildout", "confidence": 0.9},
                    {"name": "Technology absorption and R&D expansion", "confidence": 0.8},
                ],
                "reasoning": [],
            }
        ),
        encoding="utf-8",
    )
    (context.intelligence_dir / "business_classification.json").write_text(
        json.dumps(
            {
                "business_dnas": ["Manufacturing", "Semiconductor"],
                "question_modules": ["Capex", "Technology"],
                "report_template": "semiconductor_v1",
            }
        ),
        encoding="utf-8",
    )
    (context.intelligence_dir / "discovery_runtime.json").write_text(
        json.dumps(
            {
                "executed_modules": ["capital_allocation", "technology"],
            }
        ),
        encoding="utf-8",
    )

    cim = build_company_intelligence()

    assert cim["business"]["dna"] == {
        "business_dnas": ["Manufacturing", "Semiconductor"],
        "question_modules": ["capital_allocation", "technology"],
        "report_template": "semiconductor_v1",
    }
    assert cim["business"]["industry_profile"] == {
        "business_summary": "Builds semiconductor manufacturing capacity.",
        "business_model": "Manufacturing-led growth with R&D support.",
        "value_creation": "Creates value through capacity expansion and technology adoption.",
        "characteristics": [
            "Capital-intensive manufacturing buildout",
            "Technology absorption and R&D expansion",
        ],
        "blueprint_version": "1.0",
        "confidence": 0.7,
    }
    assert cim["business"]["competitive_position"] == {
        "summary": "Competes through manufacturing scale-up and technology adoption.",
        "supporting_modules": ["capital_allocation", "technology"],
    }
    assert cim["management"]["promises"]["items"] == []
    assert cim["financial"]["capital_allocation"]["items"] == []


def test_build_company_intelligence_expands_stale_platform_question_modules_from_dnas(
    tmp_path,
    monkeypatch,
):
    context = CompanyContext(company="tanla", year="fy25")
    monkeypatch.chdir(tmp_path)
    context.create_directories()
    set_context(context)

    (context.intelligence_dir / "business_blueprint.json").write_text(
        json.dumps(
            {
                "metadata": {"company": "Tanla", "version": "1.0", "confidence": 0.85},
                "business_understanding": {
                    "business_summary": "Enterprise messaging and compliance platform.",
                    "business_model": "API-first platform with operator and enterprise integrations.",
                    "value_creation": "Creates value through platform scale, trust controls, and partner deployments.",
                    "competitive_position": "Differentiates through throughput, compliance, and platform integrations.",
                },
                "characteristics": [
                    {"name": "API-first platform architecture", "confidence": 0.9},
                    {"name": "Embedded compliance and anti-fraud controls", "confidence": 0.88},
                ],
                "reasoning": [],
            }
        ),
        encoding="utf-8",
    )
    (context.intelligence_dir / "business_classification.json").write_text(
        json.dumps(
            {
                "business_dnas": ["Compliance Infrastructure", "Enterprise Platform"],
                "question_modules": ["technology", "platform_dependency"],
                "report_template": "software_v1",
            }
        ),
        encoding="utf-8",
    )
    (context.intelligence_dir / "discovery_runtime.json").write_text(
        json.dumps(
            {
                "executed_modules": ["technology", "platform_dependency"],
            }
        ),
        encoding="utf-8",
    )

    cim = build_company_intelligence()

    assert cim["business"]["dna"]["question_modules"] == [
        "technology",
        "platform_dependency",
        "platform_economics",
        "compliance_infrastructure",
    ]
    assert cim["business"]["competitive_position"]["supporting_modules"] == [
        "technology",
        "platform_dependency",
        "platform_economics",
        "compliance_infrastructure",
    ]
