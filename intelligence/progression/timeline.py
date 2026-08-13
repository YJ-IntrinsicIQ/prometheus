from __future__ import annotations

from typing import Any, Dict, List, Optional

from .confidence import aggregate_confidence
from .contracts import ProgressionTimeline
from .deduplication import deduplicate_events
from .transitions import build_transition_states


def _sort_key(event: Dict[str, Any]) -> tuple:
    return (
        str(event.get("period") or ""),
        int(event.get("sequence") or 0),
        str(event.get("event_type") or ""),
        str(event.get("event_id") or ""),
    )


def _turning_point_type(event: Dict[str, Any], transition: Dict[str, Any]) -> Optional[str]:
    event_type = str(event.get("event_type") or "").strip()
    if event_type in {"delay", "delay_signal", "contradiction", "reversal", "completion", "abandonment", "superseded"}:
        return event_type
    if event_type == "confirmation":
        return "completion"
    if transition.get("previous_state") != transition.get("current_state") and event_type not in {"announcement", "update"}:
        return "evidence_quality_change"
    return None


def build_progression_timeline(subject_id: str, stream_type: str, events: List[Dict[str, Any]], adapter, *, unresolved_questions: Optional[List[str]] = None, coverage_status: str = "supported") -> Dict[str, Any]:
    normalized = [adapter.normalize_event(dict(event)) for event in events]
    ordered = sorted(deduplicate_events(normalized, key_fn=adapter.deduplicate_key), key=_sort_key)
    transitions = build_transition_states(ordered, adapter)
    effective_coverage_status = coverage_status
    if coverage_status == "supported":
        if not ordered:
            effective_coverage_status = "unavailable"
        elif len(ordered) == 1:
            effective_coverage_status = "partial"

    turning_points: List[Dict[str, Any]] = []
    for event, transition in zip(ordered, transitions):
        turning_point_type = _turning_point_type(event, transition)
        if turning_point_type is None:
            continue
        turning_points.append(
            {
                "event_id": event.get("event_id"),
                "period": event.get("period"),
                "change_type": turning_point_type,
                "description": event.get("title") or event.get("description"),
                "why_it_matters": event.get("metadata", {}).get("why_it_matters")
                or "This may affect investor conviction because it changes the path of the stream.",
                "confidence": event.get("confidence") or aggregate_confidence([event]),
            }
        )

    accepted_transitions = [transition for transition in transitions if transition.get("accepted")]
    current_state = accepted_transitions[-1].get("current_state") if accepted_transitions else adapter.derive_current_state(ordered)
    investor_implication = adapter.build_investor_implication(
        {
            "subject_id": subject_id,
            "stream_type": stream_type,
            "events": ordered,
            "turning_points": turning_points,
            "current_state": current_state,
        }
    )
    confidence = aggregate_confidence(ordered)
    latest_period = ordered[-1]["period"] if ordered else ""

    timeline = ProgressionTimeline(
        subject_id=subject_id,
        stream_type=stream_type,
        events=ordered,
        turning_points=turning_points,
        current_state=current_state,
        unresolved_questions=list(unresolved_questions or []),
        investor_implication=investor_implication,
        confidence=confidence,
        latest_period=latest_period,
        coverage_status=effective_coverage_status,
        state_transitions=transitions,
    )
    return timeline.to_dict()
