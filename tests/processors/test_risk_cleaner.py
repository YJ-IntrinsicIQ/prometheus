import json

from core.company_context import CompanyContext
from pipelines.pipeline_context import set_context
from processors.risk_cleaner import create_cleaner


def test_risk_cleaner_excludes_quarantined_items_without_failing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy20")
    context.create_directories()
    set_context(context)

    try:
        risks = [
            {
                "risk": "Dynamic and stringent regulatory/compliance environment requiring ongoing changes to platforms and processes",
                "category": "Regulatory risk",
                "severity": "medium",
                "year": "2021",
                "page": 12,
                "actor": "management",
                "value": "Dynamic and stringent regulatory/compliance environment requiring ongoing changes to platforms and processes",
            },
            {
                "risk": "Community development/CSR initiatives failing to be adopted successfully by target communities",
                "category": "CSR risk",
                "severity": "low",
                "year": "2021",
                "page": 13,
                "actor": "company",
                "value": "Community development/CSR initiatives failing to be adopted successfully by target communities",
            },
        ]
        (context.extracted_dir / "extracted_risks.json").write_text(json.dumps(risks, indent=2, ensure_ascii=False), encoding="utf-8")

        cleaned = create_cleaner().run()

        assert len(cleaned) == 1
        assert cleaned[0]["risk"] == risks[0]["risk"]
        output = json.loads((context.extracted_dir / "clean_risks.json").read_text(encoding="utf-8"))
        assert len(output) == 1
        assert output[0]["risk"] == risks[0]["risk"]
    finally:
        set_context(None)


def test_risk_cleaner_handles_example_years_inside_current_disclosures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy20")
    context.create_directories()
    set_context(context)

    try:
        risks = [
            {
                "risk": "Dynamic and stringent regulatory/compliance environment (e.g., TCCPR 2018) requiring ongoing changes to platforms and processes",
                "category": "Regulatory risk",
                "severity": "high",
                "page": 12,
                "actor": "management",
                "value": "Dynamic and stringent regulatory/compliance environment (e.g., TCCPR 2018) requiring ongoing changes to platforms and processes",
                "source_chunk": "Management Discussion and Analysis ... TCCPR 2018 ... ongoing changes ...",
            }
        ]
        (context.extracted_dir / "extracted_risks.json").write_text(json.dumps(risks, indent=2, ensure_ascii=False), encoding="utf-8")

        cleaned = create_cleaner().run()

        assert len(cleaned) == 1
        assert cleaned[0]["source_year"] == "fy20"
        assert cleaned[0]["risk"] == risks[0]["risk"]
        output = json.loads((context.extracted_dir / "clean_risks.json").read_text(encoding="utf-8"))
        assert len(output) == 1
        assert output[0]["risk"] == risks[0]["risk"]
    finally:
        set_context(None)
