import json
from pathlib import Path

import pytest

from intelligence.capacity import CapacityEvolutionBuilder, validate_capacity_payload


def _write_year_artifacts(
    base_dir: Path,
    company: str,
    year: str,
    *,
    capacity_items=None,
):
    extracted_dir = base_dir / "companies" / company / year / "extracted"
    intelligence_dir = base_dir / "companies" / company / year / "intelligence"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    intelligence_dir.mkdir(parents=True, exist_ok=True)

    (extracted_dir / "clean_capacity.json").write_text(json.dumps(capacity_items or [], ensure_ascii=False), encoding="utf-8")
    (intelligence_dir / "company_intelligence.json").write_text(
        json.dumps({"management": {"promises": {"items": []}}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (intelligence_dir / "business_classification.json").write_text(
        json.dumps({"status": "pass"}, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_projects(base_dir: Path, company: str, projects):
    output_dir = base_dir / "companies" / company / "company_memory" / "projects"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "projects_registry.json").write_text(
        json.dumps({"company": company, "project_count": len(projects), "projects": projects}, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "project_assessments.json").write_text(
        json.dumps({"company": company, "assessments": []}, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_commitments(base_dir: Path, company: str, commitments):
    output_dir = base_dir / "companies" / company / "company_memory" / "management_commitments"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "management_commitments.json").write_text(
        json.dumps({"company": company, "commitment_count": len(commitments), "commitments": commitments}, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_outputs(base_dir: Path, company: str):
    output_dir = base_dir / "companies" / company / "company_memory" / "capacity"
    registry = json.loads((output_dir / "capacity_registry.json").read_text(encoding="utf-8"))
    timelines = json.loads((output_dir / "capacity_timelines.json").read_text(encoding="utf-8"))
    assessments = json.loads((output_dir / "capacity_assessments.json").read_text(encoding="utf-8"))
    validation = json.loads((output_dir / "capacity_validation.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_dir / "capacity_manifest.json").read_text(encoding="utf-8"))
    return registry, timelines, assessments, validation, manifest


def test_explicit_manufacturing_capacity_announcement_creates_item(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "New manufacturing facility",
                "status": "Planned",
                "timeline": "Next year",
                "location": "Chennai",
                "year": "2023",
                "confidence": "high",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, manifest = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_count"] == 1
    assert manifest["capacity_candidates"] == 1
    item = registry["capacity_items"][0]
    assert item["capacity_type"] in {"manufacturing", "infrastructure"}
    assert item["current_status"] in {"planned", "announced"}


def test_vague_scaling_ambition_does_not_create_item(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "We are scaling",
                "status": "We are scaling for growth",
                "year": "2023",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_count"] == 0


def test_non_core_public_infrastructure_capacity_is_quarantined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Pond and stormwater management capacity",
                "status": "Planned",
                "timeline": "Next year",
                "year": "2013",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_count"] == 0


def test_workforce_and_facility_capacity_do_not_merge(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Workforce capacity expansion",
                "status": "Planned",
                "year": "2024",
                "location": "Chennai",
                "description": "Recruit engineers and operators to expand workforce capacity for the new plant.",
            },
            {
                "item_id": "c2",
                "capacity_type": "New manufacturing facility",
                "status": "Planned",
                "year": "2024",
                "location": "Chennai",
                "description": "Build a new manufacturing facility to expand production capacity.",
            },
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_count"] == 2
    assert {item["capacity_family"] for item in registry["capacity_items"]} == {"workforce", "physical"}


def test_related_project_is_linked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "New facility expansion",
                "status": "Planned",
                "location": "Chennai",
                "year": "2023",
            }
        ],
    )
    _write_projects(
        tmp_path,
        "acme",
        [
            {
                "project_id": "PJ-0001",
                "project_name": "Chennai plant expansion",
                "normalized_name": "Chennai plant expansion",
                "location": "Chennai",
                "project_type": "facility",
                "objective": "Expand the Chennai plant",
                "business_rationale": "Support execution capacity",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_items"][0]["linked_project_ids"] == ["PJ-0001"]


def test_related_commitment_is_linked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Capacity expansion",
                "status": "Planned",
                "location": "Chennai",
                "year": "2023",
            }
        ],
    )
    _write_commitments(
        tmp_path,
        "acme",
        [
            {
                "id": "MC-0001",
                "topic": "Capacity expansion",
                "normalized_commitment": "Expand manufacturing capacity",
                "category": "Capacity",
                "delivery_assessment": "In progress",
                "investor_implication": "Execution appears on track.",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_items"][0]["linked_commitment_ids"] == ["MC-0001"]


def test_installation_does_not_equal_commissioning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Testing facility",
                "status": "Installed",
                "location": "Chennai",
                "year": "2024",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_items"][0]["current_status"] == "installed"
    assert registry["capacity_items"][0]["current_status"] != "commissioned"


def test_commissioning_does_not_equal_operations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Testing facility",
                "status": "Commissioned",
                "location": "Chennai",
                "year": "2024",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_items"][0]["current_status"] == "commissioned"
    assert registry["capacity_items"][0]["current_status"] != "operational"


def test_operations_do_not_imply_utilization(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Manufacturing line",
                "status": "Operational",
                "location": "Chennai",
                "year": "2024",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, assessments, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_items"][0]["current_status"] == "operational"
    assert assessments["assessments"][0]["utilization_status"] in {"not_disclosed", "pre_operational", "unclear"}
    assert assessments["latest_period"] == "fy24"
    assert assessments["assessments"][0]["latest_period"] == "fy24"


def test_explicit_utilization_updates_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Manufacturing line",
                "status": "Operating at 80% utilization",
                "location": "Chennai",
                "year": "2024",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, assessments, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert assessments["assessments"][0]["utilization_status"] == "high"
    assert registry["capacity_items"][0]["current_status"] == "materially_utilized"
    assert registry["capacity_items"][0]["utilization_rate"] == pytest.approx(0.8)


def test_missing_denominator_prevents_utilization_rate_calculation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Manufacturing line",
                "status": "Production is improving, but no percentage is disclosed.",
                "location": "Chennai",
                "year": "2024",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, assessments, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_items"][0]["utilization_rate"] is None
    assert assessments["assessments"][0]["utilization_measure"]["denominator"] == ""


def test_capex_without_capacity_evidence_does_not_create_capacity_item(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Capital expenditure",
                "status": "Capex approved",
                "amount": "10",
                "currency": "INR",
                "year": "2024",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_count"] == 0


def test_delayed_ramp_up_becomes_turning_point_candidate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Manufacturing line",
                "status": "Planned",
                "location": "Chennai",
                "year": "2023",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c2",
                "capacity_type": "Manufacturing line",
                "status": "Delayed because equipment delivery slipped",
                "location": "Chennai",
                "year": "2024",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, timelines, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_items"][0]["current_status"] == "delayed"
    assert any(point["change_type"] == "delay_signal" for point in timelines["timelines"][0]["turning_points"])


def test_underutilization_weakens_conviction(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Manufacturing line",
                "status": "Operational but underutilized",
                "location": "Chennai",
                "year": "2024",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, assessments, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_items"][0]["current_status"] == "underutilized"
    assert assessments["assessments"][0]["conviction_impact"] == "weakened"


def test_repeated_annual_mention_is_deduplicated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    item = {
        "item_id": "c1",
        "capacity_type": "New facility",
        "status": "Planned",
        "location": "Chennai",
        "year": "2023",
    }
    _write_year_artifacts(tmp_path, "acme", "fy23", capacity_items=[item])
    _write_year_artifacts(tmp_path, "acme", "fy24", capacity_items=[dict(item, item_id="c2", year="2024")])

    CapacityEvolutionBuilder(company="acme").build()
    registry, timelines, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_count"] == 1
    assert len(timelines["timelines"][0]["events"]) == 2


def test_differently_worded_same_capacity_item_merges(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Chennai plant expansion",
                "status": "Planned",
                "location": "Chennai",
                "year": "2023",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c2",
                "capacity_type": "Plant expansion in Chennai",
                "status": "Under construction",
                "location": "Chennai",
                "year": "2024",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_count"] == 1
    assert registry["capacity_items"][0]["current_status"] in {"under_construction", "planned"}


def test_distinct_expansion_phases_remain_separate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "New facility creation",
                "status": "Planned",
                "location": "Chennai",
                "year": "2024",
            },
            {
                "item_id": "c2",
                "capacity_type": "Setting up an EMI-EMC testing facility",
                "status": "Planned",
                "location": "Bangalore",
                "year": "2024",
            },
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert registry["capacity_count"] == 2


def test_output_growth_after_commissioning_does_not_prove_causality(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Manufacturing line",
                "status": "Commissioned and production increased",
                "location": "Chennai",
                "year": "2024",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    _, _, assessments, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert assessments["assessments"][0]["economic_impact_status"] != "clearly_observed"


def test_invalid_project_reference_fails_validation():
    payload = {
        "company": "acme",
        "capacities": [
            {
                "capacity_id": "CP-0001",
                "capacity_name": "Chennai plant expansion",
                "current_status": "planned",
                "source_references": [{"period": "fy24"}],
                "confidence": {"level": "high", "basis": ["explicit"], "limitations": []},
                "linked_project_ids": ["PJ-9999"],
            }
        ],
    }
    timeline_payload = {
        "timelines": [
            {
                "capacity_id": "CP-0001",
                "events": [
                    {
                        "event_id": "CP-0001-E001",
                        "period": "fy24",
                        "event_type": "capacity_plan_defined",
                        "title": "Chennai plant expansion",
                        "description": "Planned",
                        "source_references": [{"period": "fy24"}],
                        "confidence": {"level": "high", "basis": ["explicit"], "limitations": []},
                    }
                ],
                "current_state": "planned",
                "investor_implication": {},
                "state_transitions": [{"supporting_event_ids": ["CP-0001-E001"], "accepted": True, "current_state": "planned"}],
            }
        ]
    }
    validation = validate_capacity_payload(payload, timelines_payload=timeline_payload, project_ids={"PJ-0001"}, commitment_ids=set())
    assert validation["status"] == "fail"
    assert any(issue["code"] == "invalid_project_reference" for issue in validation["issues"])


def test_invalid_commitment_reference_fails_validation():
    payload = {
        "company": "acme",
        "capacities": [
            {
                "capacity_id": "CP-0001",
                "capacity_name": "Chennai plant expansion",
                "current_status": "planned",
                "source_references": [{"period": "fy24"}],
                "confidence": {"level": "high", "basis": ["explicit"], "limitations": []},
                "linked_commitment_ids": ["MC-9999"],
            }
        ],
    }
    timeline_payload = {
        "timelines": [
            {
                "capacity_id": "CP-0001",
                "events": [
                    {
                        "event_id": "CP-0001-E001",
                        "period": "fy24",
                        "event_type": "capacity_plan_defined",
                        "title": "Chennai plant expansion",
                        "description": "Planned",
                        "source_references": [{"period": "fy24"}],
                        "confidence": {"level": "high", "basis": ["explicit"], "limitations": []},
                    }
                ],
                "current_state": "planned",
                "investor_implication": {},
                "state_transitions": [{"supporting_event_ids": ["CP-0001-E001"], "accepted": True, "current_state": "planned"}],
            }
        ]
    }
    validation = validate_capacity_payload(payload, timelines_payload=timeline_payload, project_ids=set(), commitment_ids={"MC-0001"})
    assert validation["status"] == "fail"
    assert any(issue["code"] == "invalid_commitment_reference" for issue in validation["issues"])


def test_progression_order_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Manufacturing line",
                "status": "Planned",
                "location": "Chennai",
                "year": "2024",
            },
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy25",
        capacity_items=[
            {
                "item_id": "c2",
                "capacity_type": "Manufacturing line",
                "status": "Under construction",
                "location": "Chennai",
                "year": "2025",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    _, timelines, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert [event["period"] for event in timelines["timelines"][0]["events"][:2]] == ["fy24", "fy25"]


def test_confidence_preserves_limitations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "New facility",
                "status": "Planned",
                "year": "2024",
            }
        ],
    )

    CapacityEvolutionBuilder(company="acme").build()
    registry, _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert any("location not disclosed" in limitation for limitation in registry["capacity_items"][0]["confidence"]["limitations"])


def test_no_raw_document_search_occurs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Manufacturing line",
                "status": "Planned",
                "location": "Chennai",
                "year": "2024",
            }
        ],
    )

    read_paths = []
    original_read_text = Path.read_text

    def tracking_read_text(self, *args, **kwargs):
        read_paths.append(str(self))
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracking_read_text)

    CapacityEvolutionBuilder(company="acme").build()

    assert read_paths
    assert not any("/raw/" in path for path in read_paths)


def test_no_llm_call_occurs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        capacity_items=[
            {
                "item_id": "c1",
                "capacity_type": "Manufacturing line",
                "status": "Planned",
                "location": "Chennai",
                "year": "2024",
            }
        ],
    )

    monkeypatch.setattr("knowledge.ai.get_llm", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not be called")))

    CapacityEvolutionBuilder(company="acme").build()
