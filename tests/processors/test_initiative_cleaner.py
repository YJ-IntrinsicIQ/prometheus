import json

from core.company_context import CompanyContext
from pipelines.pipeline_context import set_context
from processors.initiative_cleaner import InitiativeCleaner


def test_initiative_cleaner_keeps_platform_partnerships(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy22")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "initiative": "Kicked off exclusive partnership with Truecaller",
                "category": "Strategic partnership — Identity/communication",
                "status": "Executed",
                "benefit": "Enhances caller identity and communication capabilities, broadening the platform ecosystem and solution set",
                "year": "2021",
                "page": 21,
                "actor": "company",
                "value": "Kicked off exclusive partnership with Truecaller",
            }
        ]
        (context.extracted_dir / "extracted_initiatives.json").write_text(
            json.dumps(items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = InitiativeCleaner("extracted_initiatives.json", "clean_initiatives.json", module_name="initiatives").run()

        assert len(cleaned) == 1
        assert cleaned[0]["initiative"] == "Kicked off exclusive partnership with Truecaller"
        output = json.loads((context.extracted_dir / "clean_initiatives.json").read_text(encoding="utf-8"))
        assert len(output) == 1
    finally:
        set_context(None)


def test_initiative_cleaner_handles_historical_completion_without_period_conflict(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy20")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "initiative": "Acquired 100% voting interest in Gamooga Softtech Private Limited",
                "category": "Acquisition",
                "status": "Completed (24 October 2019)",
                "year": "2019",
                "page": 116,
                "actor": "company",
                "value": "Acquired 100% voting interest in Gamooga Softtech Private Limited",
            }
        ]
        (context.extracted_dir / "extracted_initiatives.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

        cleaned = InitiativeCleaner("extracted_initiatives.json", "clean_initiatives.json", module_name="initiatives").run()

        assert len(cleaned) == 1
        assert cleaned[0]["initiative"] == items[0]["initiative"]
    finally:
        set_context(None)


def test_initiative_cleaner_handles_future_milestone_without_period_conflict(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="tanla", year="fy23")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "initiative": "Deployment and commercialization of Wisely ATP platform",
                "category": "Digital platform deployment",
                "status": "Deployed and commercialized (FY24)",
                "page": 39,
                "actor": "company",
                "value": "Deployment and commercialization of Wisely ATP platform",
            }
        ]
        (context.extracted_dir / "extracted_initiatives.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

        cleaned = InitiativeCleaner("extracted_initiatives.json", "clean_initiatives.json", module_name="initiatives").run()

        assert len(cleaned) == 1
        assert cleaned[0]["initiative"] == items[0]["initiative"]
    finally:
        set_context(None)
