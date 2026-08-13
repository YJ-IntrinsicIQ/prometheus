import json
from pathlib import Path

from intelligence.management_commentary import ManagementCommentaryBuilder, validate_commentary_payload


def _write_year_artifacts(
    base_dir: Path,
    company: str,
    year: str,
    *,
    management_actions=None,
    company_results=None,
):
    intelligence_dir = base_dir / "companies" / company / year / "intelligence"
    intelligence_dir.mkdir(parents=True, exist_ok=True)

    (intelligence_dir / "management_summary.json").write_text(
        json.dumps(
            {
                "company_management_actions": management_actions or [],
                "company_results": company_results or [],
                "risk_responses": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (intelligence_dir / "company_intelligence.json").write_text(
        json.dumps({"management": {"summary": {}, "focus": {}, "credibility": {}}}, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_outputs(base_dir: Path, company: str):
    output_dir = base_dir / "companies" / company / "company_memory" / "management_commentary"
    themes = json.loads((output_dir / "commentary_themes.json").read_text(encoding="utf-8"))
    timelines = json.loads((output_dir / "commentary_timelines.json").read_text(encoding="utf-8"))
    assessments = json.loads((output_dir / "commentary_assessments.json").read_text(encoding="utf-8"))
    validation = json.loads((output_dir / "commentary_validation.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_dir / "commentary_manifest.json").read_text(encoding="utf-8"))
    return themes, timelines, assessments, validation, manifest


def test_commentary_builder_tracks_progression_and_validation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        management_actions=[
            {
                "item_id": "m1",
                "theme": "Strategy",
                "category": "Strategy",
                "commentary": "We expect commercial production next year.",
                "status": "planned",
                "sentiment": "positive",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        management_actions=[
            {
                "item_id": "m2",
                "theme": "Strategy",
                "category": "Strategy",
                "commentary": "We no longer expect commercial production next year.",
                "status": "revised",
                "sentiment": "mixed",
            }
        ],
    )

    ManagementCommentaryBuilder(company="acme").build()
    themes, timelines, assessments, validation, manifest = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert themes["commentary_count"] == 1
    assert manifest["theme_count"] == 1
    assert manifest["timeline_count"] == 1
    assert themes["commentary_themes"][0]["current_position"] == "contradicted"
    assert assessments["assessments"][0]["current_position"] == "contradicted"
    assert timelines["timelines"][0]["current_state"] == "contradicted"
    assert [event["period"] for event in timelines["timelines"][0]["events"]] == ["fy23", "fy24"]
    assert "execution" in " ".join(themes["commentary_themes"][0]["unresolved_questions"]).lower() or isinstance(
        themes["commentary_themes"][0]["unresolved_questions"], list
    )


def test_external_context_is_not_promoted_into_commentary_themes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        management_actions=[
            {
                "item_id": "m1",
                "theme": "Government policy",
                "category": "Other",
                "commentary": "The ministry announced a new scheme for schools and public works.",
                "status": "informational",
                "sentiment": "neutral",
                "actor": "government",
            }
        ],
    )

    ManagementCommentaryBuilder(company="acme").build()
    themes, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert themes["commentary_count"] == 0


def test_commentary_records_carry_semantic_quality_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        management_actions=[
            {
                "item_id": "m1",
                "theme": "Execution",
                "category": "Execution",
                "commentary": "We expect execution to improve with the new plant.",
                "status": "revised",
                "sentiment": "positive",
            }
        ],
    )

    ManagementCommentaryBuilder(company="acme").build()
    themes, timelines, assessments, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    theme = themes["commentary_themes"][0]
    timeline = timelines["timelines"][0]
    assessment = assessments["assessments"][0]
    assert theme["semantic_quality"]["semantic_status"] == "pass"
    assert timeline["semantic_quality"]["semantic_status"] == "pass"
    assert assessment["semantic_quality"]["semantic_status"] == "pass"


def test_validator_rejects_duplicate_ids_and_chronology_violations():
    payload = {
        "themes": [
            {
                "theme_id": "CM-0001",
                "theme_name": "Strategy",
                "theme_category": "strategy",
                "current_position": "stable_priority",
                "source_references": [{"period": "fy23", "artifact": "management_summary.json"}],
                "confidence": {"level": "medium", "basis": ["synthetic"], "limitations": []},
            },
            {
                "theme_id": "CM-0001",
                "theme_name": "Strategy",
                "theme_category": "strategy",
                "current_position": "stable_priority",
                "source_references": [{"period": "fy24", "artifact": "management_summary.json"}],
                "confidence": {"level": "medium", "basis": ["synthetic"], "limitations": []},
            },
        ]
    }
    timelines = {
        "timelines": [
            {
                "theme_id": "CM-0001",
                "events": [
                    {"period": "fy24", "event_type": "commentary_update", "title": "Strategy", "description": "Late"},
                    {"period": "fy23", "event_type": "commentary_update", "title": "Strategy", "description": "Early"},
                ],
            }
        ]
    }
    assessments = {
        "assessments": [
            {
                "theme_id": "CM-0001",
                "consistency_assessment": {},
                "specificity_assessment": {},
                "evidence_alignment": {},
                "confidence": {"level": "medium", "basis": [], "limitations": []},
            }
        ]
    }

    validation = validate_commentary_payload(payload, timelines_payload=timelines, assessments_payload=assessments)

    assert validation["status"] == "fail"
    assert any(issue["code"] == "duplicate_theme_id" for issue in validation["issues"])
    assert any(issue["code"] == "chronology_violation" for issue in validation["issues"])
