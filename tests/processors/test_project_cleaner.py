from knowledge.evidence_layer import finalize_cleaned_item, validate_cleaned_item
from processors.project_cleaner import ProjectCleaner


def _cleaner():
    return ProjectCleaner(
        "extracted_projects.json",
        "clean_projects.json",
        module_name="projects",
    )


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
