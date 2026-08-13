import json
from pathlib import Path

from knowledge.company_memory import ManagementCommitmentsBuilder, validate_management_commitments_payload


def _write_year_artifacts(
    base_dir: Path,
    company: str,
    year: str,
    *,
    promise_items=None,
    summary_promises=None,
):
    intelligence_dir = base_dir / "companies" / company / year / "intelligence"
    intelligence_dir.mkdir(parents=True, exist_ok=True)

    if promise_items is None:
        promise_items = []
    if summary_promises is None:
        summary_promises = []

    (intelligence_dir / "company_intelligence.json").write_text(
        json.dumps(
            {
                "management": {
                    "promises": {
                        "items": promise_items,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (intelligence_dir / "management_summary.json").write_text(
        json.dumps(
            {
                "major_promises": summary_promises,
            }
        ),
        encoding="utf-8",
    )


def _load_outputs(base_dir: Path, company: str):
    output_dir = base_dir / "companies" / company / "company_memory" / "management_commitments"
    commitments = json.loads((output_dir / "management_commitments.json").read_text())
    timeline = json.loads((output_dir / "commitment_timeline.json").read_text())
    validation = json.loads((output_dir / "commitment_validation.json").read_text())
    manifest = json.loads((output_dir / "management_commitments_manifest.json").read_text())
    return commitments, timeline, validation, manifest


def test_commitments_capture_delivery_after_later_confirmation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        promise_items=[
            {
                "id": "P1",
                "promise": "We expect commercial production next year.",
                "category": "Manufacturing",
                "page": 10,
                "source_chunk": "Commercial production next year.",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        promise_items=[
            {
                "id": "P2",
                "promise": "Commercial production was commissioned and is now operational.",
                "category": "Manufacturing",
                "page": 14,
                "source_chunk": "Commercial production was commissioned and is now operational.",
            }
        ],
    )

    ManagementCommitmentsBuilder(company="acme").build()
    commitments, timeline, validation, manifest = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    assert commitments["commitment_count"] == 1
    assert manifest["schema_version"] == "management_commitments_manifest.v1"
    assert manifest["commitments_detected"] == 1
    assert manifest["commitments_without_follow_up"] == 0

    commitment = commitments["commitments"][0]
    assert commitment["announcement_period"] == "fy23"
    assert commitment["category"] == "Manufacturing"
    assert commitment["topic"] == "Commercial production"
    assert commitment["status"] == "Delivered"
    assert commitment["normalized_commitment"] == "Commercial production."
    assert commitment["supporting_evidence"][0]["event_type"] == "announcement"
    assert commitment["supporting_evidence"][1]["event_type"] == "delivery_confirmation"
    assert "supports delivery" in commitment["delivery_assessment"]
    assert commitment["investor_implication"] == "Execution appears on schedule."
    assert timeline["timeline"][0]["latest_status"] == "Delivered"
    assert [event["event_type"] for event in timeline["timeline"][0]["events"]] == [
        "announcement",
        "delivery_confirmation",
        "latest_assessment",
    ]


def test_commitments_detect_delay_after_later_contradiction(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        promise_items=[
            {
                "id": "P1",
                "promise": "We will expand capacity in the new plant.",
                "category": "Capacity",
                "page": 8,
                "source_chunk": "Expand capacity in the new plant.",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        promise_items=[
            {
                "id": "P2",
                "promise": "The capacity expansion was delayed because equipment delivery slipped.",
                "category": "Capacity",
                "page": 12,
                "source_chunk": "The capacity expansion was delayed because equipment delivery slipped.",
            }
        ],
    )

    ManagementCommitmentsBuilder(company="acme").build()
    commitments, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    commitment = commitments["commitments"][0]
    assert commitment["status"] == "Delayed"
    assert commitment["investor_implication"] == "Delay increases uncertainty around the expected outcome."
    assert commitment["progression"]["latest_status"] == "Delayed"


def test_commitments_mark_abandoned_after_follow_up(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy22",
        promise_items=[
            {
                "id": "P1",
                "promise": "We plan to enter the European market.",
                "category": "Market Entry",
                "page": 5,
                "source_chunk": "Enter the European market.",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        promise_items=[
            {
                "id": "P2",
                "promise": "We are no longer pursuing the European market entry plan.",
                "category": "Market Entry",
                "page": 11,
                "source_chunk": "No longer pursuing the European market entry plan.",
            }
        ],
    )

    ManagementCommitmentsBuilder(company="acme").build()
    commitments, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    commitment = commitments["commitments"][0]
    assert commitment["status"] == "Abandoned"
    assert "walked away" in commitment["investor_implication"]


def test_commitments_mark_unable_to_verify_without_follow_up(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy25",
        promise_items=[
            {
                "id": "P1",
                "promise": "We expect to launch a new product line.",
                "category": "Product",
                "page": 7,
                "source_chunk": "Launch a new product line.",
            }
        ],
    )

    ManagementCommitmentsBuilder(company="acme").build()
    commitments, _, validation, manifest = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    commitment = commitments["commitments"][0]
    assert commitment["status"] == "Unable To Verify"
    assert commitment["investor_implication"] == "There is not enough later evidence to judge execution."
    assert manifest["commitments_without_follow_up"] == 1
    assert commitment["supporting_evidence"] == [
        {
            "period": "fy25",
            "event_type": "announcement",
            "status": "Announced",
            "statement": "We expect to launch a new product line.",
            "source_reference": {
                "period": "fy25",
                "source_artifact": "company_intelligence.json",
                "source_item_id": "P1",
                "page": 7,
                "source_chunk": "Launch a new product line.",
                "confidence": None,
                "status_hint": None,
            },
        }
    ]


def test_commitments_keep_multiple_updates_in_progression(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy21",
        promise_items=[
            {
                "id": "P1",
                "promise": "We plan to roll out the platform.",
                "category": "Product",
                "page": 2,
                "source_chunk": "Roll out the platform.",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy22",
        promise_items=[
            {
                "id": "P2",
                "promise": "The platform rollout is in progress and early customers are testing it.",
                "category": "Product",
                "page": 6,
                "source_chunk": "The platform rollout is in progress and early customers are testing it.",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        promise_items=[
            {
                "id": "P3",
                "promise": "The platform rollout is now operational and customers are live.",
                "category": "Product",
                "page": 9,
                "source_chunk": "The platform rollout is now operational and customers are live.",
            }
        ],
    )

    ManagementCommitmentsBuilder(company="acme").build()
    commitments, timeline, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "pass"
    commitment = commitments["commitments"][0]
    assert commitment["status"] == "Delivered"
    assert commitment["progression"]["announcement"]["period"] == "fy21"
    assert len(commitment["progression"]["evidence_updates"]) == 2
    assert [event["event_type"] for event in timeline["timeline"][0]["events"]] == [
        "announcement",
        "progress_update",
        "delivery_confirmation",
        "latest_assessment",
    ]


def test_commitments_flag_duplicate_wording_across_years(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy23",
        promise_items=[
            {
                "id": "P1",
                "promise": "We will expand capacity at the plant.",
                "category": "Capacity",
                "page": 4,
                "source_chunk": "Expand capacity at the plant.",
            }
        ],
    )
    _write_year_artifacts(
        tmp_path,
        "acme",
        "fy24",
        promise_items=[
            {
                "id": "P2",
                "promise": "We will expand capacity at the plant.",
                "category": "Capacity",
                "page": 10,
                "source_chunk": "Expand capacity at the plant.",
            }
        ],
    )

    ManagementCommitmentsBuilder(company="acme").build()
    _, _, validation, _ = _load_outputs(tmp_path, "acme")

    assert validation["status"] == "fail"
    assert any(issue["code"] == "identical_commitments_across_years" for issue in validation["issues"])


def test_validation_rejects_unsupported_delivery_and_future_ambition_marked_delivered():
    payload = {
        "company": "acme",
        "commitments": [
            {
                "id": "MC-0001",
                "topic": "Commercial production",
                "category": "Manufacturing",
                "announcement_period": "fy23",
                "original_statement": "We expect commercial production next year.",
                "normalized_commitment": "Commercial production expected.",
                "expected_timeframe": "next year",
                "priority": "high",
                "status": "Delivered",
                "supporting_evidence": [
                    {
                        "period": "fy23",
                        "event_type": "announcement",
                        "status": "Announced",
                        "statement": "We expect commercial production next year.",
                        "source_reference": {
                            "period": "fy23",
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "P1",
                            "page": 10,
                            "source_chunk": "Commercial production next year.",
                            "confidence": None,
                            "status_hint": None,
                        },
                    }
                ],
                "delivery_assessment": "Unsupported",
                "confidence": "medium",
                "investor_implication": "Execution appears on schedule.",
                "source_references": [],
                "progression": {
                    "announcement": {
                        "period": "fy23",
                        "statement": "We expect commercial production next year.",
                        "source_reference": {
                            "period": "fy23",
                            "source_artifact": "company_intelligence.json",
                            "source_item_id": "P1",
                            "page": 10,
                            "source_chunk": "Commercial production next year.",
                            "confidence": None,
                            "status_hint": None,
                        },
                    },
                    "evidence_updates": [],
                    "latest_status": "Delivered",
                    "latest_period": "fy22",
                },
            }
        ],
    }

    validation = validate_management_commitments_payload(payload)

    assert validation["status"] == "fail"
    codes = {issue["code"] for issue in validation["issues"]}
    assert "unsupported_delivery" in codes
    assert "future_ambition_marked_delivered" in codes
