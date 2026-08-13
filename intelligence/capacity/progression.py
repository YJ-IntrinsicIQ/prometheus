from __future__ import annotations

from typing import Any, Dict, List, Sequence

from intelligence.progression import build_confidence, build_progression_timeline, event_deduplication_key

from .classifier import _compact_lower, _normalize_text
from .contracts import CAPACITY_STATUS_ORDER


FINANCIAL_DEPLOYMENT_HINTS = (
    "funds",
    "funded",
    "funding",
    "proceeds",
    "ipo objects",
    "qip objects",
    "allocated",
    "allocation",
    "unutilised",
    "unutilized",
)

CAPACITY_OPERATING_HINTS = (
    "operating at",
    "running at",
    "output",
    "throughput",
    "occupancy",
    "capacity use",
    "at capacity",
    "production",
    "commercial operations",
    "commercial production",
)


def _status_from_text(status_text: str, utilization_status: str | None = None) -> str:
    text = _normalize_text(status_text).lower()
    if any(term in text for term in FINANCIAL_DEPLOYMENT_HINTS) and not any(term in text for term in CAPACITY_OPERATING_HINTS):
        return "funded"
    if any(term in text for term in ("cancelled", "canceled", "abandoned", "dropped", "shutdown")):
        return "cancelled"
    if any(term in text for term in ("superseded", "replaced", "shifted focus", "reframed")):
        return "superseded"
    if any(term in text for term in ("paused", "on hold", "halted", "suspended")):
        return "paused"
    if any(term in text for term in ("delayed", "delay", "slipped", "postponed", "deferred", "behind schedule")):
        return "delayed"
    if utilization_status in {"fully_utilized", "high"} or any(term in text for term in ("fully utilized", "fully utilised", "at full capacity", "operating at", "running at", "high utilization", "high utilisation")):
        return "materially_utilized"
    if utilization_status == "moderate" or any(term in text for term in ("partially utilized", "partially utilised", "some utilization", "some utilisation", "partial use")):
        return "partially_utilized"
    if utilization_status == "low" or any(term in text for term in ("underutilized", "underutilised", "idle", "unused", "weak utilization", "weak utilisation")):
        return "underutilized"
    if utilization_status == "ramping" or any(term in text for term in ("ramping", "ramp up", "ramp-up", "trial", "pilot", "initial use", "warm up")):
        return "ramping"
    if any(term in text for term in ("operational", "in operation", "commercial operations", "commercial production", "live", "active", "operations started")):
        return "operational"
    if any(term in text for term in ("commissioned", "commissioning", "handed over", "ready for operation")):
        return "commissioned"
    if any(term in text for term in ("installed", "installation", "installed equipment", "set up", "equipment installed", "built", "completed")):
        return "installed"
    if any(term in text for term in ("construction", "under construction", "ongoing", "in progress", "executing", "implementation", "under execution")):
        return "under_construction"
    if any(term in text for term in ("funded", "funding", "allocated", "approved", "budget", "po", "purchase order", "committed")):
        return "funded"
    if any(term in text for term in ("planned", "expected", "expect", "intend", "proposal", "announced", "next year")):
        return "planned" if any(term in text for term in ("planned", "proposal")) else "announced"
    return "unable_to_verify"


def _event_type_from_status(status: str, status_text: str, utilization_status: str | None = None) -> str:
    text = _normalize_text(status_text).lower()
    if status == "cancelled":
        return "cancellation"
    if status == "delayed":
        return "delay_signal"
    if status == "paused":
        return "delay_signal"
    if status == "superseded":
        return "latest_assessment"
    if status in {"materially_utilized", "partially_utilized", "underutilized"}:
        return "utilization_update"
    if utilization_status in {"ramping"} or status == "ramping":
        return "ramp_up_update"
    if status == "operational":
        return "operations_started"
    if status == "commissioned":
        return "commissioning"
    if status == "installed":
        return "equipment_installed"
    if status == "under_construction":
        return "construction_started"
    if status == "funded":
        return "funding_committed"
    if status == "planned":
        return "capacity_plan_defined"
    if any(term in text for term in ("output", "throughput", "production", "utilized", "utilised", "occupancy")):
        return "output_update"
    return "capacity_announced"


def build_capacity_event(candidate: Dict[str, Any], sequence: int) -> Dict[str, Any]:
    status_text = candidate.get("original_status_text") or ""
    utilization_status = candidate.get("utilization_status_hint") or candidate.get("utilization_status")
    derived_status = _status_from_text(status_text, utilization_status)
    event_type = _event_type_from_status(derived_status, status_text, utilization_status)
    title = candidate.get("capacity_name") or candidate.get("normalized_name") or "Capacity update"
    description = candidate.get("purpose") or candidate.get("economic_relevance") or title
    if derived_status in {"materially_utilized", "partially_utilized", "underutilized"}:
        description = f"{description}. Later evidence suggests utilization has become explicit."
    elif derived_status in {"operational", "commissioned", "installed", "under_construction", "funded"}:
        description = f"{description}. Later evidence indicates the capacity moved further along its execution path."
    elif derived_status in {"delayed", "paused", "cancelled", "superseded"}:
        description = f"{description}. Later evidence indicates a setback or change in path."
    return {
        "event_id": f"{candidate['capacity_id']}-E{sequence:03d}",
        "stream_type": "capacity",
        "subject_id": candidate["capacity_id"],
        "period": candidate["source_year"],
        "sequence": sequence,
        "event_type": event_type,
        "title": title,
        "description": description,
        "evidence_status": candidate.get("evidence_status") or "supported",
        "confidence": candidate.get("confidence") or build_confidence("medium", basis=["capacity source record"], limitations=[]),
        "source_references": [candidate["source_reference"]],
        "metadata": {
            "capacity_type": candidate.get("capacity_type"),
            "status_text": status_text,
            "derived_status": derived_status,
            "utilization_status": utilization_status,
            "location": candidate.get("location"),
            "announcement_period": candidate.get("announcement_period"),
            "unit": candidate.get("unit"),
        },
    }


class CapacityProgressionAdapter:
    stream_type = "capacity"

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
        return CAPACITY_STATUS_ORDER.get(str(state or "unable_to_verify"), -1)

    def validate_transition(self, previous_state: Any, event: Dict[str, Any], next_state: Any) -> Dict[str, Any]:
        event_state = str((event.get("metadata") or {}).get("derived_status") or next_state or previous_state or "unable_to_verify")
        previous_rank = self._rank(previous_state)
        next_rank = self._rank(event_state)
        event_type = str(event.get("event_type") or "")
        accepted = True
        reason = ""
        if event_state == "unable_to_verify" and previous_state not in (None, "", "unable_to_verify"):
            accepted = False
            reason = "No new evidence was strong enough to change the current capacity state."
        elif previous_state in {"delayed", "paused"} and next_rank < previous_rank:
            accepted = True
            reason = "Capacity recovered after a delay or pause."
        elif next_rank < previous_rank and event_state not in {"delayed", "paused"}:
            accepted = False
            reason = "Capacity state moved backwards without evidence of recovery."
        elif event_type == "latest_assessment" and previous_state == next_state:
            accepted = False
            reason = "Latest assessment did not add new capacity evidence."
        return {
            "accepted": accepted,
            "transition_type": event_type,
            "reason": reason,
            "confidence": build_confidence(
                "high" if accepted else "medium",
                basis=["deterministic capacity progression"],
                limitations=[reason] if reason else [],
            ),
        }

    def derive_current_state(self, events: List[Dict[str, Any]]) -> Any:
        if not events:
            return "unable_to_verify"
        state = "unable_to_verify"
        for event in events:
            candidate = str((event.get("metadata") or {}).get("derived_status") or "unable_to_verify")
            if self._rank(candidate) >= self._rank(state):
                state = candidate
        return state

    def build_investor_implication(self, timeline: Dict[str, Any]) -> Dict[str, Any]:
        current_state = str(timeline.get("current_state") or "unable_to_verify")
        turning_points = timeline.get("turning_points") or []
        events = timeline.get("events") or []
        if current_state in {"cancelled", "superseded"}:
            conviction = "weakened"
            summary = "The capacity path no longer appears to be on its original track."
        elif current_state in {"delayed", "paused"}:
            conviction = "weakened"
            summary = "The capacity still exists in plan, but execution risk has increased."
        elif current_state in {"underutilized"}:
            conviction = "weakened"
            summary = "The capacity exists, but weak use lowers conviction."
        elif current_state in {"materially_utilized"}:
            conviction = "strengthened"
            summary = "The capacity now appears to be translating into meaningful use."
        elif current_state in {"partially_utilized", "ramping"}:
            conviction = "unchanged"
            summary = "The capacity is moving into use, but the evidence is still incomplete."
        elif current_state in {"commissioned", "operational", "installed", "under_construction", "funded", "planned", "announced"}:
            conviction = "unchanged"
            summary = "The capacity is progressing, but economic use is still not fully visible."
        else:
            conviction = "unclear"
            summary = "There is not enough later evidence to judge the capacity confidently."
        why = "What changed is the latest execution or utilization evidence, or the lack of it."
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


def build_timeline(capacity: Dict[str, Any], events: Sequence[Dict[str, Any]], unresolved_questions: Sequence[str] | None = None) -> Dict[str, Any]:
    adapter = CapacityProgressionAdapter()
    payload = build_progression_timeline(
        capacity["capacity_id"],
        "capacity",
        list(events),
        adapter,
        unresolved_questions=list(unresolved_questions or []),
        coverage_status=capacity.get("evidence_status") or "supported",
    )
    payload["capacity_id"] = capacity["capacity_id"]
    payload["capacity_name"] = capacity.get("capacity_name")
    payload["normalized_name"] = capacity.get("normalized_name")
    payload["capacity_type"] = capacity.get("capacity_type")
    payload["location"] = capacity.get("location")
    payload["announcement_period"] = capacity.get("announcement_period")
    payload["linked_project_ids"] = list(capacity.get("linked_project_ids") or [])
    payload["linked_commitment_ids"] = list(capacity.get("linked_commitment_ids") or [])
    return payload
