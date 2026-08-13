from __future__ import annotations

from typing import Any, Dict, List, Sequence

from intelligence.progression import build_confidence, build_progression_timeline, event_deduplication_key

from .contracts import PROJECT_STATUS_ORDER


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _status_from_text(status_text: str) -> str:
    text = _normalize_text(status_text).lower()
    if any(term in text for term in ("cancelled", "canceled", "abandoned", "dropped")):
        return "cancelled"
    if any(term in text for term in ("superseded", "replaced", "shifted focus")):
        return "superseded"
    if any(term in text for term in ("paused", "on hold", "halted", "suspended")):
        return "paused"
    if any(term in text for term in ("delayed", "delay", "slipped", "postponed", "deferred")):
        return "delayed"
    if any(term in text for term in ("partially operational", "partial", "phased", "phase 1", "first phase", "trial", "testing", "installed", "built", "completed", "implemented", "created")):
        return "partially_operational"
    if any(term in text for term in ("operational", "in operation", "commercial operations", "commercial production", "live", "active")):
        return "operational"
    if any(term in text for term in ("commissioned", "commissioning", "handed over", "ready for operation")):
        return "commissioned"
    if any(term in text for term in ("underway", "ongoing", "in progress", "construction", "building", "executing", "implementation", "ramping")):
        return "under_execution"
    if any(term in text for term in ("funded", "funding", "budget", "approved", "land acquired", "order placed", "purchase order", "regulatory approval")):
        return "funded"
    if any(term in text for term in ("planned", "proposed", "expect", "expected", "intend", "announce", "announced")):
        return "planning" if any(term in text for term in ("plan", "planned", "proposed")) else "announced"
    if text:
        return "under_execution" if any(token in text for token in ("update", "progress")) else "unable_to_verify"
    return "unable_to_verify"


def _milestone_type(status_text: str) -> str:
    text = _normalize_text(status_text).lower()
    if any(term in text for term in ("cancelled", "canceled", "abandoned", "dropped")):
        return "abandonment"
    if any(term in text for term in ("delayed", "delay", "slipped", "postponed", "deferred")):
        return "delay_signal"
    if any(term in text for term in ("paused", "on hold", "halted", "suspended")):
        return "delay_signal"
    if any(term in text for term in ("superseded", "replaced", "shifted focus")):
        return "superseded"
    if any(term in text for term in ("cost revision", "cost overrun", "budget revision", "budget overrun", "price escalation", "scope revision")):
        return "contradiction"
    if any(term in text for term in ("commissioned", "commissioning", "handed over", "commercial production")):
        return "confirmation"
    if any(term in text for term in ("operational", "live", "in operation", "active", "ongoing", "production ongoing", "manufacturing ongoing")):
        return "completion"
    if any(term in text for term in ("trial", "testing", "installed", "built", "completed", "implemented", "created", "progress")):
        return "capacity_ramp"
    if any(term in text for term in ("funded", "budget", "approved", "land acquired", "order placed", "regulatory approval")):
        return "funding_committed"
    if any(term in text for term in ("plan", "planned", "proposed", "announced", "expect", "expected")):
        return "project_announced"
    return "latest_assessment"


def build_project_event(candidate: Dict[str, Any], sequence: int) -> Dict[str, Any]:
    status_text = candidate.get("status_text") or ""
    status = _status_from_text(status_text)
    milestone_type = _milestone_type(status_text)
    title = candidate.get("project_name") or candidate.get("normalized_name") or "Project update"
    description = candidate.get("business_rationale") or candidate.get("objective") or title
    if status in {"commissioned", "operational"}:
        description = f"{description}. Later evidence indicates the project is {status.replace('_', ' ')}."
    elif status == "delayed":
        description = f"{description}. Later evidence indicates a delay."
    elif status == "cancelled":
        description = f"{description}. Later evidence indicates cancellation."
    return {
        "event_id": f"{candidate['project_id']}-E{sequence:03d}",
        "stream_type": "project",
        "subject_id": candidate["project_id"],
        "period": candidate["source_year"],
        "sequence": sequence,
        "event_type": milestone_type,
        "title": title,
        "description": description,
        "evidence_status": candidate.get("evidence_status") or "supported",
        "confidence": candidate.get("confidence") or build_confidence("medium", basis=["project source record"], limitations=[]),
        "source_references": [candidate["source_reference"]],
        "metadata": {
            "project_type": candidate.get("project_type"),
            "status_text": status_text,
            "derived_status": status,
            "milestone_type": milestone_type,
            "location": candidate.get("location"),
            "announcement_period": candidate.get("announcement_period"),
        },
    }


class ProjectsProgressionAdapter:
    stream_type = "project"

    def normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(event)
        normalized["stream_type"] = self.stream_type
        normalized["subject_id"] = str(normalized.get("subject_id") or "").strip()
        normalized["period"] = str(normalized.get("period") or "").strip().lower()
        normalized["sequence"] = int(normalized.get("sequence") or 0)
        normalized["event_type"] = str(normalized.get("event_type") or "latest_assessment").strip()
        normalized["title"] = str(normalized.get("title") or "").strip()
        normalized["description"] = str(normalized.get("description") or "").strip()
        normalized["evidence_status"] = str(normalized.get("evidence_status") or "supported").strip()
        normalized["confidence"] = normalized.get("confidence") or build_confidence("unavailable", basis=[], limitations=["missing confidence"])
        normalized["source_references"] = list(normalized.get("source_references") or [])
        normalized["metadata"] = dict(normalized.get("metadata") or {})
        return normalized

    def deduplicate_key(self, event: Dict[str, Any]) -> str:
        return event_deduplication_key(event)

    def _rank(self, state: Any) -> int:
        return PROJECT_STATUS_ORDER.get(str(state or "unable_to_verify"), -1)

    def validate_transition(self, previous_state: Any, event: Dict[str, Any], next_state: Any) -> Dict[str, Any]:
        event_state = str((event.get("metadata") or {}).get("derived_status") or next_state or previous_state or "unable_to_verify")
        previous_rank = self._rank(previous_state)
        next_rank = self._rank(event_state)
        event_type = str(event.get("event_type") or "")
        accepted = True
        reason = ""
        if event_state == "unable_to_verify" and previous_state not in (None, "unable_to_verify"):
            accepted = False
            reason = "No new evidence was strong enough to change the current project state."
        elif event_state in {"cancelled", "superseded"}:
            accepted = True
        elif event_state == "delayed" and previous_rank < 0:
            accepted = True
        elif next_rank < previous_rank and event_state not in {"delayed", "paused"}:
            accepted = False
            reason = "Project state moved backwards without evidence of reversal."
        elif event_type == "latest_assessment" and previous_state == next_state:
            accepted = False
            reason = "Latest assessment did not add new project evidence."
        return {
            "accepted": accepted,
            "transition_type": event_type,
            "reason": reason,
            "confidence": build_confidence(
                "high" if accepted else "medium",
                basis=["deterministic project progression"],
                limitations=[reason] if reason else [],
            ),
        }

    def derive_current_state(self, events: List[Dict[str, Any]]) -> Any:
        if not events:
            return "unable_to_verify"
        state = "unable_to_verify"
        for event in events:
            metadata = event.get("metadata") or {}
            candidate = str(metadata.get("derived_status") or "unable_to_verify")
            if self._rank(candidate) >= self._rank(state):
                state = candidate
        if len(events) == 1 and state in {"announced", "planning", "funded", "under_execution"}:
            return "unable_to_verify"
        return state

    def build_investor_implication(self, timeline: Dict[str, Any]) -> Dict[str, Any]:
        current_state = str(timeline.get("current_state") or "unable_to_verify")
        turning_points = timeline.get("turning_points") or []
        events = timeline.get("events") or []
        if current_state in {"cancelled", "superseded"}:
            conviction = "weakened"
            summary = "The project no longer appears to be on the original path."
        elif current_state in {"delayed", "paused"}:
            conviction = "weakened"
            summary = "The project is still in motion, but execution risk has increased."
        elif current_state in {"commissioned", "operational"}:
            conviction = "strengthened"
            summary = "The project has moved into a materially stronger execution state."
        elif current_state in {"partially_operational", "under_execution", "funded", "planning", "announced"}:
            conviction = "unchanged"
            summary = "The project is progressing, but the evidence is still short of full delivery."
        else:
            conviction = "unclear"
            summary = "There is not enough later evidence to judge the project confidently."
        why = "What changed is the latest execution evidence or evidence gap."
        if turning_points:
            why = f"The latest turning point is {turning_points[-1].get('change_type') or 'a progression update'}."
        return {
            "what_changed": summary,
            "why_it_changed": why,
            "conviction_impact": conviction,
            "current_state": current_state,
            "latest_evidence": [str(event.get("title") or event.get("description") or "") for event in events[-3:]],
            "unresolved_items": list(timeline.get("unresolved_questions") or []),
        }


def build_timeline(project: Dict[str, Any], events: Sequence[Dict[str, Any]], unresolved_questions: Sequence[str] | None = None) -> Dict[str, Any]:
    adapter = ProjectsProgressionAdapter()
    payload = build_progression_timeline(
        project["project_id"],
        "project",
        list(events),
        adapter,
        unresolved_questions=list(unresolved_questions or []),
        coverage_status=project.get("evidence_status") or "supported",
    )
    payload["project_id"] = project["project_id"]
    payload["project_name"] = project.get("project_name")
    payload["normalized_name"] = project.get("normalized_name")
    payload["project_type"] = project.get("project_type")
    payload["location"] = project.get("location")
    payload["announcement_period"] = project.get("announcement_period")
    payload["related_commitment_ids"] = list(project.get("related_commitment_ids") or [])
    return payload
