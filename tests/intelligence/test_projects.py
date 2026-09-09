import json
from pathlib import Path

from intelligence.projects import ProjectsBuilder, validate_projects_payload


def _write_year_artifacts(base_dir: Path, company: str, year: str, *, projects=None, capacity=None):
    extracted_dir = base_dir / "companies" / company / year / "extracted"
    intelligence_dir = base_dir / "companies" / company / year / "intelligence"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    intelligence_dir.mkdir(parents=True, exist_ok=True)
    (extracted_dir / "clean_projects.json").write_text(json.dumps(projects or [], ensure_ascii=False), encoding="utf-8")
    (extracted_dir / "clean_capacity.json").write_text(json.dumps(capacity or [], ensure_ascii=False), encoding="utf-8")


def _write_commitments(base_dir: Path, company: str, commitments):
    output_dir = base_dir / "companies" / company / "company_memory" / "management_commitments"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "management_commitments.json").write_text(
        json.dumps(
            {
                "company": company,
                "commitment_count": len(commitments),
                "commitments": commitments,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _load_outputs(base_dir: Path, company: str):
    output_dir = base_dir / "companies" / company / "company_memory" / "projects"
    registry = json.loads((output_dir / "projects_registry.json").read_text(encoding="utf-8"))
    timelines = json.loads((output_dir / "project_timelines.json").read_text(encoding="utf-8"))
    assessments = json.loads((output_dir / "project_assessments.json").read_text(encoding="utf-8"))
    validation = json.loads((output_dir / "projects_validation.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_dir / "projects_manifest.json").read_text(encoding="utf-8"))
    return registry, timelines, assessments, validation, manifest


def test_explicit_facility_announcement_creates_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        projects=[
            {
                "item_id": "p1",
                "project_name": "New manufacturing and integration facility",
                "description": "A new facility to support design, manufacturing, and integration of larger systems.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2023",
                "confidence": "high",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, manifest = _load_outputs(tmp_path, "acme")

    assert validation["status"] in {"pass", "warning"}
    assert manifest["project_candidates"] == 1
    assert registry["project_count"] == 1
    project = registry["projects"][0]
    assert project["project_type"] in {"facility", "capacity_expansion"}
    assert project["current_status"] == "unable_to_verify"
    assert project["assessment"]["latest_period"] == "fy23"
    assert "later delivery evidence" in project["assessment"]["execution_summary"].lower()


def test_vague_growth_ambition_does_not_create_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        projects=[
            {
                "item_id": "p1",
                "project_name": "Continue to grow",
                "description": "We will continue to grow and strengthen our position.",
                "status": "Planned",
                "year": "2023",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] in {"pass", "warning"}
    assert registry["project_count"] == 0


def test_non_core_civic_renovation_is_quarantined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        projects=[
            {
                "item_id": "p1",
                "project_name": "School renovation and classroom addition",
                "description": "Upgrade the school building with a new classroom.",
                "location": "Melakottaiyur",
                "status": "Planned",
                "year": "2023",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] in {"pass", "warning"}
    assert registry["project_count"] == 0


def test_rooftop_solar_and_ehs_projects_use_correct_precedence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p1",
                "project_name": "Rooftop solar power system",
                "description": "Install rooftop solar to lower energy use.",
                "location": "Chennai",
                "status": "Partially operational",
                "year": "2024",
            },
            {
                "item_id": "p2",
                "project_name": "Integrated EHS Management System",
                "description": "ISO 14001 and ISO 45001 certification project.",
                "location": "Chennai",
                "status": "Commissioned",
                "year": "2024",
            },
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] in {"pass", "warning"}
    types = {item["normalized_name"]: item["project_type"] for item in registry["projects"]}
    statuses = {item["normalized_name"]: item["current_status"] for item in registry["projects"]}
    assert types["Rooftop solar power system"] == "energy_efficiency"
    assert statuses["Rooftop solar power system"] == "partially_operational"
    assert types["Integrated EHS Management System"] == "environmental_compliance"


def test_later_construction_update_advances_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        projects=[
            {
                "item_id": "p1",
                "project_name": "Plant expansion in Chennai",
                "description": "Capacity expansion at Chennai plant.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2023",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p2",
                "project_name": "Chennai plant expansion",
                "description": "Construction started for the Chennai plant expansion.",
                "location": "Chennai",
                "status": "Construction started",
                "year": "2024",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, timelines, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["project_count"] == 1
    assert registry["projects"][0]["current_status"] == "under_execution"
    assert [event["period"] for event in timelines["timelines"][0]["events"]] == ["fy23", "fy24"]


def test_commissioning_requires_explicit_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p1",
                "project_name": "New integration facility",
                "description": "The facility was completed last year.",
                "location": "Chennai",
                "status": "Completed",
                "year": "2024",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["projects"][0]["current_status"] != "commissioned"


def test_operational_requires_explicit_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p1",
                "project_name": "New integration facility",
                "description": "The facility was commissioned this year.",
                "location": "Chennai",
                "status": "Commissioned",
                "year": "2024",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["projects"][0]["current_status"] == "commissioned"
    assert registry["projects"][0]["current_status"] != "operational"


def test_commissioning_does_not_equal_economic_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p1",
                "project_name": "New integration facility",
                "description": "The facility was commissioned this year.",
                "location": "Chennai",
                "status": "Commissioned",
                "year": "2024",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    _, _, assessments, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assessment = assessments["assessments"][0]
    assert assessment["economic_impact_status"] != "clearly_observed"
    assert "does not establish a direct link" in assessment["observed_financial_effect"].lower() or "no direct financial effect" in assessment["observed_financial_effect"].lower()


def test_delayed_timeframe_marks_delayed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        projects=[
            {
                "item_id": "p1",
                "project_name": "Chennai plant expansion",
                "description": "Plant expansion in Chennai.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2023",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p2",
                "project_name": "Chennai plant expansion",
                "description": "The project was delayed because equipment delivery slipped.",
                "location": "Chennai",
                "status": "Delayed because equipment delivery slipped.",
                "year": "2024",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, timelines, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["projects"][0]["current_status"] == "delayed"
    assert any(event["event_type"] == "delay_signal" for event in timelines["timelines"][0]["events"])


def test_no_follow_up_becomes_unable_to_verify(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy25",
        projects=[
            {
                "item_id": "p1",
                "project_name": "New facility",
                "description": "We expect to build a facility.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2025",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, manifest = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["projects"][0]["current_status"] == "unable_to_verify"
    assert manifest["unresolved_projects"] == 1


def test_repeated_annual_mention_is_deduplicated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for year in ("fy23", "fy24"):
        _write_year_artifacts(
            tmp_path,
            "acme",
            year,
            projects=[
                {
                    "item_id": f"p-{year}",
                    "project_name": "Chennai plant expansion",
                    "description": "Plant expansion in Chennai.",
                    "location": "Chennai",
                    "status": "Planned",
                    "year": year,
                }
            ],
        )

    ProjectsBuilder(company="acme").build()
    _, timelines, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert len(timelines["timelines"][0]["events"]) == 1


def test_differently_worded_same_project_merges(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        projects=[
            {
                "item_id": "p1",
                "project_name": "New Chennai facility",
                "description": "Design, manufacturing and integration facility expansion in Chennai.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2023",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p2",
                "project_name": "Chennai design and integration block",
                "description": "A facility expansion in Chennai for design and integration.",
                "location": "Chennai",
                "status": "Construction started",
                "year": "2024",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["project_count"] == 1
    assert len(registry["projects"][0]["source_references"]) == 2


def test_distinct_phases_at_same_location_remain_separate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p1",
                "project_name": "Chennai plant expansion",
                "description": "Capacity expansion at Chennai plant.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2024",
            },
            {
                "item_id": "p2",
                "project_name": "Integrated EHS management system",
                "description": "Implementation of ISO 14001 and ISO 45001 across the manufacturing facility and offices.",
                "location": "Chennai",
                "status": "Implemented",
                "year": "2024",
            },
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["project_count"] == 2


def test_cancellation_requires_explicit_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        projects=[
            {
                "item_id": "p1",
                "project_name": "Chennai plant expansion",
                "description": "Capacity expansion at Chennai plant.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2023",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p2",
                "project_name": "Chennai plant expansion",
                "description": "The project was cancelled.",
                "location": "Chennai",
                "status": "Cancelled",
                "year": "2024",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["projects"][0]["current_status"] == "cancelled"


def test_cost_revision_becomes_turning_point_candidate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        projects=[
            {
                "item_id": "p1",
                "project_name": "Chennai plant expansion",
                "description": "Capacity expansion at Chennai plant.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2023",
            },
            {
                "item_id": "p2",
                "project_name": "Chennai plant expansion",
                "description": "The cost was revised upward because of inflation.",
                "location": "Chennai",
                "status": "Cost revision due to inflation.",
                "year": "2024",
            },
        ],
    )

    ProjectsBuilder(company="acme").build()
    _, timelines, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert any(tp["change_type"] == "contradiction" for tp in timelines["timelines"][0]["turning_points"])


def test_commissioning_becomes_turning_point(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        projects=[
            {
                "item_id": "p1",
                "project_name": "Chennai plant expansion",
                "description": "Capacity expansion at Chennai plant.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2023",
            },
            {
                "item_id": "p2",
                "project_name": "Chennai plant expansion",
                "description": "The project was commissioned.",
                "location": "Chennai",
                "status": "Commissioned",
                "year": "2024",
            },
        ],
    )

    ProjectsBuilder(company="acme").build()
    _, timelines, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert any(tp["change_type"] == "completion" for tp in timelines["timelines"][0]["turning_points"])


def test_revenue_growth_after_commissioning_does_not_prove_causality(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        projects=[
            {
                "item_id": "p1",
                "project_name": "Chennai plant expansion",
                "description": "Capacity expansion at Chennai plant.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2023",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p2",
                "project_name": "Chennai plant expansion",
                "description": "Revenue increased after commissioning, but no causal claim is stated.",
                "location": "Chennai",
                "status": "Commissioned",
                "year": "2024",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    _, _, assessments, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assessment = assessments["assessments"][0]
    assert assessment["economic_impact_status"] in {"early_evidence", "partially_observed"}
    assert "does not establish causality" in assessment["observed_financial_effect"].lower()


def test_project_links_to_valid_management_commitment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p1",
                "project_name": "Manufacturing capacity expansion at Chennai facility",
                "description": "A bounded expansion project at the Chennai facility.",
                "location": "Chennai",
                "status": "Construction started",
                "year": "2024",
            }
        ],
    )
    _write_commitments(
        tmp_path,
        "acme",
        [
            {
                "id": "MC-0001",
                "category": "Capacity",
                "topic": "Capacity expansion",
                "normalized_commitment": "Expand manufacturing capacity",
                "announcement_period": "fy23",
                "delivery_assessment": "Execution remains underway.",
                "investor_implication": "The commitment is in motion.",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    # ENG-111A: heuristic candidate links must NOT override related_commitment_ids.
    # "Manufacturing capacity expansion facility" = all generic vocab → zero candidate links.
    assert registry["projects"][0]["related_commitment_ids"] == []
    assert registry["projects"][0]["candidate_commitment_links"] == []


def test_invalid_commitment_reference_fails_validation():
    registry = {
        "projects": [
            {
                "project_id": "PJ-0001",
                "project_name": "Facility expansion",
                "normalized_name": "Facility expansion",
                "project_type": "facility",
                "objective": "Expand the facility",
                "business_rationale": "Support execution capacity",
                "announcement_period": "fy24",
                "expected_timeframe": "fy25",
                "expected_output_or_capacity": "",
                "expected_cost": "",
                "location": "Chennai",
                "related_commitment_ids": ["MC-9999"],
                "current_status": "planning",
                "latest_period": "fy24",
                "progression_summary": {},
                "economic_relevance": "Support execution capacity",
                "investor_implication": {},
                "confidence": {"level": "medium", "basis": ["test"], "limitations": []},
                "evidence_status": "supported",
                "source_references": [{"period": "fy24", "source_artifact": "clean_projects.json", "source_item_id": "p1"}],
                "unresolved_questions": [],
            }
        ]
    }
    timelines = {
        "timelines": [
            {
                "project_id": "PJ-0001",
                "events": [
                    {
                        "event_id": "PJ-0001-E001",
                        "period": "fy24",
                        "event_type": "project_announced",
                        "title": "Facility expansion",
                        "description": "Facility expansion announced.",
                        "source_references": [{"period": "fy24", "source_artifact": "clean_projects.json", "source_item_id": "p1"}],
                        "confidence": {"level": "medium", "basis": ["test"], "limitations": []},
                    }
                ],
                "turning_points": [],
                "current_state": "planning",
                "unresolved_questions": [],
                "investor_implication": {},
                "confidence": {"level": "medium", "basis": ["test"], "limitations": []},
                "latest_period": "fy24",
                "coverage_status": "supported",
            }
        ]
    }
    assessments = {
        "assessments": [
            {
                "project_id": "PJ-0001",
                "project_name": "Facility expansion",
                "execution_status": "planning",
                "execution_summary": "Still planning",
                "economic_impact_status": "not_yet_observable",
                "observed_business_effect": "None",
                "observed_financial_effect": "None",
                "evidence_periods": ["fy24"],
                "confidence": {"level": "medium", "basis": ["test"], "limitations": []},
                "unresolved_questions": [],
                "what_changed": "Nothing",
                "why_it_changed": "Nothing",
                "conviction_impact": "unchanged",
            }
        ]
    }

    validation = validate_projects_payload(registry, timelines_payload=timelines, assessments_payload=assessments, commitment_ids=["MC-0001"])

    assert validation["status"] == "fail"
    assert any(issue["code"] == "invalid_commitment_reference" for issue in validation["issues"])


def test_progression_order_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixture_a = [
        {
            "item_id": "p1",
            "project_name": "Chennai plant expansion",
            "description": "Capacity expansion at Chennai plant.",
            "location": "Chennai",
            "status": "Planned",
            "year": "2023",
        },
        {
            "item_id": "p2",
            "project_name": "Chennai plant expansion",
            "description": "Construction started for the Chennai plant expansion.",
            "location": "Chennai",
            "status": "Construction started",
            "year": "2024",
        },
    ]
    fixture_b = list(reversed(fixture_a))

    _write_year_artifacts(tmp_path, "acme", "fy23", projects=fixture_a)
    _write_year_artifacts(tmp_path, "beta", "fy23", projects=fixture_b)

    ProjectsBuilder(company="acme").build()
    ProjectsBuilder(company="beta").build()
    acme_registry, _, _, _, _ = _load_outputs(tmp_path, "acme")
    beta_registry, _, _, _, _ = _load_outputs(tmp_path, "beta")

    assert acme_registry["projects"][0]["project_name"] == beta_registry["projects"][0]["project_name"]
    assert acme_registry["projects"][0]["progression"]["events"] == beta_registry["projects"][0]["progression"]["events"]


def test_confidence_preserves_evidence_limitations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p1",
                "project_name": "New facility",
                "description": "A bounded facility project.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2024",
                "uncertainty_reason": "weak_time_specificity",
            }
        ],
    )

    ProjectsBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["projects"][0]["confidence"]["limitations"]


def test_no_raw_document_search_occurs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p1",
                "project_name": "New facility",
                "description": "A bounded facility project.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2024",
            }
        ],
    )

    import intelligence.projects.builder as builder_module

    loaded_paths = []
    real_load_json = builder_module._load_json

    def spy(path):
        loaded_paths.append(str(path))
        return real_load_json(path)

    monkeypatch.setattr(builder_module, "_load_json", spy)
    ProjectsBuilder(company="acme").build()

    assert loaded_paths
    assert all("/raw/" not in path for path in loaded_paths)


def test_no_llm_call_occurs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        projects=[
            {
                "item_id": "p1",
                "project_name": "New facility",
                "description": "A bounded facility project.",
                "location": "Chennai",
                "status": "Planned",
                "year": "2024",
            }
        ],
    )

    import knowledge.ai
    import knowledge.ai.input_packs

    def _fail(*args, **kwargs):
        raise AssertionError("LLM call should not happen in Projects Intelligence")

    monkeypatch.setattr(knowledge.ai, "get_llm", _fail)
    monkeypatch.setattr(knowledge.ai.input_packs, "call_llm_with_input_pack", _fail)

    ProjectsBuilder(company="acme").build()
