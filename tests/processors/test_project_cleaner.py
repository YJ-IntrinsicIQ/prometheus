import json
from pathlib import Path
from core.company_context import CompanyContext
from knowledge.evidence_layer import finalize_cleaned_item, validate_cleaned_item
from pipelines.pipeline_context import set_context
from processors.project_cleaner import ProjectCleaner


ROOT = Path(__file__).resolve().parents[2]


def _cleaner():
    return ProjectCleaner(
        "extracted_projects.json",
        "clean_projects.json",
        module_name="projects",
    )


def test_project_cleaner_accepts_historical_progression_years_inside_current_disclosures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="datapatterns", year="fy23")
    context.create_directories()
    set_context(context)

    try:
        source = ROOT / "companies" / "datapatterns" / "fy23" / "extracted" / "extracted_projects.json"
        items = json.loads(source.read_text(encoding="utf-8"))
        bundle = next(item for item in items if item.get("item_id") == "projects_00002")
        (context.extracted_dir / "extracted_projects.json").write_text(
            json.dumps([bundle], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = _cleaner().run()

        assert len(cleaned) == 1
        assert cleaned[0]["source_year"] == "fy23"
        assert cleaned[0]["year"] == "2013"
        assert cleaned[0]["evidence_quality"]["period_resolution"]["status"] == "RESOLVED"
    finally:
        set_context(None)


def test_blank_project_status_becomes_explicit_unknown_without_inventing_progress():
    source = {
        "project_name": "Large Systems Integration Hangar",
        "description": "Large Systems Integration Hangar as part of the manufacturing facility.",
        "status": "",
        "year": "fy25",
        "page": 35,
    }

    cleaned = _cleaner().clean_item(source)

    assert cleaned["status"] == "UNKNOWN"
    assert cleaned["uncertainty_reason"] == "Project status was not explicit in the source disclosure."
    assert source["status"] == ""

    finalized = finalize_cleaned_item(cleaned, module_name="projects", item_index=1)
    validation = validate_cleaned_item(finalized, module_name="projects")
    assert validation["errors"] == []


def test_explicit_project_status_is_preserved():
    source = {
        "project_name": "New production building",
        "description": "The company commissioned the new production building.",
        "status": "commissioned",
    }

    cleaned = _cleaner().clean_item(source)

    assert cleaned["status"] == "commissioned"
    assert "uncertainty_reason" not in cleaned
