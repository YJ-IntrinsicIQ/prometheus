from __future__ import annotations

from dataclasses import dataclass

import json
from pathlib import Path

import pytest

from intelligence.progression import build_confidence, build_progression_timeline, validate_progression_payload
from knowledge.company_memory import ManagementCommitmentsBuilder


@dataclass
class ToyProgressionAdapter:
    stream_type: str = "toy_stream"

    def normalize_event(self, event):
        normalized = dict(event)
        normalized.setdefault("stream_type", self.stream_type)
        normalized.setdefault("source_references", [])
        normalized.setdefault("metadata", {})
        confidence = normalized.get("confidence") or {}
        if not isinstance(confidence, dict):
            confidence = build_confidence(confidence)
        normalized["confidence"] = build_confidence(
            confidence.get("level"),
            basis=confidence.get("basis"),
            limitations=confidence.get("limitations"),
        )
        return normalized

    def deduplicate_key(self, event):
        metadata = tuple(sorted((event.get("metadata") or {}).items()))
        return (
            str(event.get("stream_type") or ""),
            str(event.get("subject_id") or ""),
            str(event.get("period") or ""),
            str(event.get("sequence") or 0),
            str(event.get("event_type") or ""),
            str(event.get("title") or ""),
            str(event.get("description") or ""),
            str(event.get("evidence_status") or ""),
            metadata,
        )

    def validate_transition(self, previous_state, event, next_state):
        order = {"Announced": 0, "In Progress": 1, "Partially Delivered": 2, "Delivered": 3, "Delayed": 2, "Superseded": 3, "Abandoned": 3, "Unable To Verify": 0}
        if previous_state not in (None, "", "Unknown") and next_state not in (None, "", "Unknown"):
            if order.get(str(next_state), 0) < order.get(str(previous_state), 0):
                return {
                    "accepted": False,
                    "transition_type": "reversal",
                    "reason": "Backward transition rejected.",
                    "confidence": build_confidence("medium", basis=["domain validation"], limitations=["backward transition"]),
                }
        return {
            "accepted": True,
            "transition_type": event.get("event_type", "update"),
            "reason": "Accepted.",
            "confidence": build_confidence("high", basis=["domain validation"], limitations=[]),
        }

    def derive_current_state(self, events):
        state = "Unable To Verify"
        for event in events:
            status = event.get("metadata", {}).get("domain_status") or event.get("evidence_status")
            if status in {"Announced", None, "", "Unknown"}:
                continue
            state = str(status)
        return state

    def build_investor_implication(self, timeline):
        current_state = str(timeline.get("current_state") or "Unable To Verify")
        direction = {"Delivered": "strengthened", "Delayed": "weakened", "Superseded": "weakened", "Abandoned": "weakened", "Unable To Verify": "unclear", "Announced": "unchanged"}.get(current_state, "unchanged")
        return {
            "direction": direction,
            "summary": f"Current state is {current_state}.",
            "reason": "Synthetic adapter judgment.",
            "confidence": "medium" if current_state not in {"Unable To Verify", "Announced"} else "low",
        }


def _event(
    event_id,
    period,
    sequence,
    event_type,
    title,
    description,
    *,
    evidence_status="direct",
    domain_status=None,
    confidence_level="medium",
    source_reference_id=None,
):
    return {
        "event_id": event_id,
        "stream_type": "toy_stream",
        "subject_id": "subject-1",
        "period": period,
        "sequence": sequence,
        "event_type": event_type,
        "title": title,
        "description": description,
        "evidence_status": evidence_status,
        "confidence": {
            "level": confidence_level,
            "basis": ["direct evidence"],
            "limitations": [],
        },
        "source_references": [
            {
                "period": period,
                "source_artifact": "synthetic.json",
                "source_item_id": source_reference_id or event_id,
            }
        ],
        "metadata": {
            "domain_status": domain_status or description,
        },
    }


def test_chronological_order_and_same_period_determinism():
    adapter = ToyProgressionAdapter()
    events = [
        _event("e2", "fy24", 2, "update", "Update", "Still in progress", domain_status="In Progress"),
        _event("e1", "fy24", 1, "announcement", "Announcement", "Initial commitment", domain_status="Announced"),
        _event("e3", "fy25", 1, "confirmation", "Confirmation", "Delivered", domain_status="Delivered"),
    ]

    timeline = build_progression_timeline("subject-1", "toy_stream", events, adapter)

    assert [event["event_id"] for event in timeline["events"]] == ["e1", "e2", "e3"]
    assert timeline["current_state"] == "Delivered"
    assert timeline["state_transitions"][-1]["current_state"] == "Delivered"


def test_duplicate_events_merge_and_materially_different_events_remain_separate():
    adapter = ToyProgressionAdapter()
    events = [
        _event("dup-1", "fy24", 1, "update", "Update", "Capacity work continues", domain_status="In Progress"),
        _event("dup-2", "fy24", 1, "update", "Update", "Capacity work continues", domain_status="In Progress"),
        _event("diff-1", "fy24", 2, "update", "Update", "Capacity work continues with a new machine line", domain_status="In Progress"),
    ]

    timeline = build_progression_timeline("subject-1", "toy_stream", events, adapter)

    assert [event["event_id"] for event in timeline["events"]] == ["dup-1", "diff-1"]


def test_state_transition_references_valid_events_and_backward_transition_is_rejected():
    adapter = ToyProgressionAdapter()
    events = [
        _event("e1", "fy23", 1, "announcement", "Announcement", "Initial commitment", domain_status="Announced"),
        _event("e2", "fy24", 1, "confirmation", "Confirmation", "Delivered", domain_status="Delivered"),
    ]

    timeline = build_progression_timeline("subject-1", "toy_stream", events, adapter)

    assert all(transition["supporting_event_ids"] for transition in timeline["state_transitions"])
    rejection = adapter.validate_transition("Delivered", events[0], "In Progress")
    assert rejection["accepted"] is False
    assert rejection["transition_type"] == "reversal"


def test_missing_follow_up_remains_unresolved_and_no_evidence_does_not_mean_no_change():
    adapter = ToyProgressionAdapter()
    timeline = build_progression_timeline(
        "subject-1",
        "toy_stream",
        [
            _event("e1", "fy24", 1, "announcement", "Announcement", "Initial commitment", domain_status="Announced"),
        ],
        adapter,
    )

    assert timeline["current_state"] == "Unable To Verify"
    assert timeline["turning_points"] == []
    assert timeline["coverage_status"] == "partial"


def test_contradiction_reversal_and_completion_become_turning_points():
    adapter = ToyProgressionAdapter()
    timeline = build_progression_timeline(
        "subject-1",
        "toy_stream",
        [
            _event("e1", "fy23", 1, "announcement", "Announcement", "Initial commitment", domain_status="Announced"),
            _event("e2", "fy24", 1, "contradiction", "Contradiction", "Earlier statement no longer holds", domain_status="Delayed"),
            _event("e3", "fy25", 1, "reversal", "Reversal", "Direction changed", domain_status="Superseded"),
            _event("e4", "fy26", 1, "confirmation", "Confirmation", "Delivered", domain_status="Delivered"),
        ],
        adapter,
    )

    assert [point["change_type"] for point in timeline["turning_points"]] == ["contradiction", "reversal", "completion"]


def test_repeated_annual_mentions_are_not_automatic_turning_points():
    adapter = ToyProgressionAdapter()
    timeline = build_progression_timeline(
        "subject-1",
        "toy_stream",
        [
            _event("e1", "fy23", 1, "announcement", "Announcement", "Initial commitment", domain_status="Announced"),
            _event("e2", "fy24", 1, "update", "Annual mention", "Still the same commitment", domain_status="Announced"),
            _event("e3", "fy25", 1, "update", "Annual mention", "Still the same commitment", domain_status="Announced"),
        ],
        adapter,
    )

    assert timeline["turning_points"] == []


def test_confidence_aggregates_basis_and_limitations():
    adapter = ToyProgressionAdapter()
    timeline = build_progression_timeline(
        "subject-1",
        "toy_stream",
        [
            _event("e1", "fy23", 1, "announcement", "Announcement", "Initial commitment", confidence_level="low", domain_status="Announced"),
            _event("e2", "fy24", 1, "confirmation", "Confirmation", "Delivered", confidence_level="high", domain_status="Delivered"),
        ],
        adapter,
    )

    assert timeline["confidence"]["level"] == "high"
    assert "direct evidence" in timeline["confidence"]["basis"]


def test_generic_engine_requires_no_company_specific_assumptions():
    adapter = ToyProgressionAdapter(stream_type="risk")
    timeline = build_progression_timeline(
        "risk-1",
        "risk",
        [
            {
                "event_id": "r1",
                "stream_type": "risk",
                "subject_id": "risk-1",
                "period": "fy24",
                "sequence": 1,
                "event_type": "announcement",
                "title": "Risk identified",
                "description": "A generic risk item",
                "evidence_status": "direct",
                "confidence": {"level": "low", "basis": ["direct evidence"], "limitations": []},
                "source_references": [{"period": "fy24", "source_artifact": "synthetic.json", "source_item_id": "r1"}],
                "metadata": {"domain_status": "Announced"},
            }
        ],
        adapter,
    )

    assert timeline["stream_type"] == "risk"
    assert timeline["subject_id"] == "risk-1"
    assert timeline["current_state"] == "Unable To Verify"


def test_validation_collects_issues_and_distinguishes_unresolved_from_failure():
    timeline = {
        "subject_id": "subject-1",
        "stream_type": "toy_stream",
        "events": [
            {
                "event_id": "e1",
                "stream_type": "toy_stream",
                "subject_id": "subject-1",
                "period": "fy24",
                "sequence": 1,
                "event_type": "announcement",
                "title": "Announcement",
                "description": "Initial commitment",
                "evidence_status": "direct",
                "confidence": {"level": "low", "basis": ["direct evidence"], "limitations": []},
                "source_references": [{"period": "fy24", "source_artifact": "synthetic.json", "source_item_id": "e1"}],
                "metadata": {"domain_status": "Announced"},
            }
        ],
        "state_transitions": [],
        "turning_points": [],
        "current_state": "Unable To Verify",
        "unresolved_questions": ["No follow-up evidence yet."],
        "investor_implication": {"direction": "unclear", "summary": "Current state is unresolved.", "reason": "No follow-up.", "confidence": "low"},
        "confidence": {"level": "low", "basis": ["direct evidence"], "limitations": ["no later confirmation"]},
        "latest_period": "fy24",
        "coverage_status": "partial",
    }

    validation = validate_progression_payload(timeline)

    assert validation["status"] == "pass"
    assert validation["issue_count"] == 0


def test_management_commitments_remains_conservative_and_no_llm_call(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("LLM should not be called for management commitments.")

    monkeypatch.setattr("knowledge.ai.get_llm", _fail_if_called, raising=False)

    company = "acme"
    intelligence_dir = tmp_path / "companies" / company / "fy24" / "intelligence"
    intelligence_dir.mkdir(parents=True, exist_ok=True)
    (intelligence_dir / "company_intelligence.json").write_text(
        json.dumps(
            {
                "management": {
                    "promises": {
                        "items": [
                            {
                                "id": "P1",
                                "promise": "We expect to expand capacity next year.",
                                "category": "Capacity",
                                "page": 1,
                                "source_chunk": "We expect to expand capacity next year.",
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (intelligence_dir / "management_summary.json").write_text(json.dumps({"major_promises": []}), encoding="utf-8")

    written_paths = ManagementCommitmentsBuilder(company=company).build()
    output_dir = tmp_path / "companies" / company / "company_memory" / "management_commitments"
    commitments = json.loads((output_dir / "management_commitments.json").read_text())

    assert set(written_paths) == {
        "management_commitments.json",
        "commitment_timeline.json",
        "commitment_validation.json",
        "management_commitments_manifest.json",
    }
    assert commitments["commitment_count"] == 1
    commitment = commitments["commitments"][0]
    assert commitment["status"] == "Unable To Verify"
    assert commitment["progression"]["latest_status"] == "Unable To Verify"
    assert commitment["progression"]["unresolved_questions"] == ["No later evidence confirmed the commitment."]
