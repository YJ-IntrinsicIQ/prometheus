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


def test_non_promotable_ambiguous_historical_project_is_quarantined_with_diagnostics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="sun_pharma", year="fy20")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "item_id": "projects_00011",
                "project_name": "USFDA regulatory remediation",
                "description": "Facility remediation references inspections in 2012, 2013, and 2017, but the excerpt is truncated before final status.",
                "location": "Multiple facilities",
                "status": "Incomplete information in provided text; final status not fully specified in the provided excerpt.",
                "year": "2012",
                "time_reference": "dated",
                "source_year": "fy20",
                "value": "USFDA regulatory remediation",
                "source_chunk": "In 2012 the facility received inspection observations. A 2013 warning letter followed. In 2017 the regulator referenced subsequent action, but the provided text is truncated before the final status.",
                "actor": "company",
                "page": 42,
            }
        ]
        (context.extracted_dir / "extracted_projects.json").write_text(
            json.dumps(items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = _cleaner().run()

        assert cleaned == []
        output = json.loads((context.extracted_dir / "clean_projects.json").read_text(encoding="utf-8"))
        assert output == []

        rejections = json.loads((context.extracted_dir / "clean_projects_rejections.json").read_text(encoding="utf-8"))
        assert rejections["rejection_count"] == 1
        rejection = rejections["rejections"][0]
        assert rejection["source_item_id"] == "projects_00011"
        assert rejection["failure_class"] == "PERIOD_RESOLUTION_UNSUPPORTED"
        assert rejection["diagnostics"]["period_status"] == "AMBIGUOUS"
        assert rejection["diagnostics"]["should_promote"] is False
        assert rejection["cleaned_period_fields"]["progression_materiality"]["should_promote"] is False
        assert {ref["year"] for ref in rejection["cleaned_period_fields"]["period_resolution"]["temporal_roles"]["references"]} >= {2012, 2013, 2017}
    finally:
        set_context(None)


def test_generic_non_promotable_ambiguous_historical_project_variant_is_quarantined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="acme", year="fy25")
    context.create_directories()
    set_context(context)

    try:
        items = [
            {
                "item_id": "projects_heldout_ambiguous_history",
                "project_name": "Plant regulatory remediation history",
                "description": "Facility remediation references a 2018 inspection, 2020 warning letter and 2022 later update, but the excerpt is truncated before final status.",
                "location": "Main plant",
                "status": "Incomplete information in provided text; final status not fully specified in the provided excerpt.",
                "year": "2018",
                "time_reference": "dated",
                "source_year": "fy25",
                "value": "Plant regulatory remediation history",
                "source_chunk": "In 2018 the facility received inspection observations. A 2020 warning letter followed. In 2022 the regulator referenced subsequent action, but the provided text is truncated before the final status.",
                "actor": "company",
                "page": 42,
            }
        ]
        (context.extracted_dir / "extracted_projects.json").write_text(
            json.dumps(items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cleaned = _cleaner().run()

        assert cleaned == []
        rejections = json.loads((context.extracted_dir / "clean_projects_rejections.json").read_text(encoding="utf-8"))
        assert rejections["rejections"][0]["diagnostics"]["company"] == "acme"
        assert rejections["rejections"][0]["diagnostics"]["failure_class"] == "PERIOD_RESOLUTION_UNSUPPORTED"
    finally:
        set_context(None)


def test_promotable_ambiguous_period_still_hard_fails_at_cleaner_boundary():
    cleaner = _cleaner()
    finalized_item = {
        "item_id": "projects_promotable_ambiguous",
        "evidence_quality": {
            "period_resolution": {"status": "AMBIGUOUS", "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED"},
            "progression_materiality": {"should_promote": True},
        },
    }
    validation = {"errors": ["invalid or unsupported period resolution"], "warnings": []}

    assert cleaner._is_local_rejection(finalized_item=finalized_item, validation=validation) is False


def test_required_fact_without_explicit_non_promotable_materiality_still_hard_fails():
    cleaner = _cleaner()
    finalized_item = {
        "item_id": "projects_required_ambiguous",
        "evidence_quality": {
            "period_resolution": {"status": "AMBIGUOUS", "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED"},
        },
    }
    validation = {"errors": ["invalid or unsupported period resolution"], "warnings": []}

    assert cleaner._is_local_rejection(finalized_item=finalized_item, validation=validation) is False


def test_ambiguous_period_with_other_validation_errors_still_hard_fails():
    cleaner = _cleaner()
    finalized_item = {
        "item_id": "projects_structurally_bad",
        "evidence_quality": {
            "period_resolution": {"status": "AMBIGUOUS", "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED"},
            "progression_materiality": {"should_promote": False},
        },
    }
    validation = {"errors": ["missing value", "invalid or unsupported period resolution"], "warnings": []}

    assert cleaner._is_local_rejection(finalized_item=finalized_item, validation=validation) is False


def test_project_rejection_diagnostics_do_not_change_company_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = CompanyContext(company="acme", year="fy25")
    context.create_directories()
    set_context(context)

    try:
        raw_item = {"item_id": "projects_identity_probe", "year": "2018", "source_year": "fy25"}
        finalized_item = {
            "item_id": "projects_identity_probe",
            "year": "2018",
            "source_year": "fy25",
            "evidence_ids": ["ev_probe"],
            "evidence_quality": {
                "period_resolution": {
                    "status": "AMBIGUOUS",
                    "resolved_period": "fy25",
                    "failure_class": "PERIOD_RESOLUTION_UNSUPPORTED",
                },
                "progression_materiality": {"should_promote": False},
            },
        }
        rejection = _cleaner()._rejection_record(
            raw_item=raw_item,
            finalized_item=finalized_item,
            validation={"errors": ["invalid or unsupported period resolution"], "warnings": []},
            context=context,
        )

        assert rejection["diagnostics"]["company"] == "acme"
        assert rejection["diagnostics"]["year"] == "fy25"
        assert rejection["provenance"]["evidence_ids"] == ["ev_probe"]
    finally:
        set_context(None)
