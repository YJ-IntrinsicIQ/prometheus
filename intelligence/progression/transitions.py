from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .confidence import aggregate_confidence, build_confidence
from .contracts import ProgressionState


def _transition_type_for_event(event_type: str) -> str:
    mapping = {
        "announcement": "announcement",
        "update": "update",
        "progress": "progress",
        "confirmation": "confirmation",
        "delay": "delay",
        "contradiction": "contradiction",
        "reversal": "reversal",
        "completion": "completion",
        "abandonment": "abandonment",
        "superseded": "superseded",
        "current_state": "current_state",
        "unresolved": "unresolved",
    }
    return mapping.get(str(event_type or "").strip(), "update")


def evaluate_transition(previous_state: Any, event: Dict[str, Any], next_state: Any, adapter) -> Dict[str, Any]:
    validation = adapter.validate_transition(previous_state, event, next_state)
    accepted = bool(validation.get("accepted", False))
    reason = str(validation.get("reason") or "").strip()
    transition_type = str(validation.get("transition_type") or _transition_type_for_event(event.get("event_type")))
    return {
        "accepted": accepted,
        "transition_type": transition_type,
        "transition_reason": reason,
        "previous_state": previous_state,
        "current_state": next_state if accepted else previous_state,
        "event_id": event.get("event_id"),
        "period": event.get("period"),
        "confidence": aggregate_confidence([event, {"confidence": validation.get("confidence") or {}}]),
    }


def build_transition_states(events: List[Dict[str, Any]], adapter) -> List[Dict[str, Any]]:
    transitions: List[Dict[str, Any]] = []
    previous_state = None
    for index, event in enumerate(events):
        next_state = adapter.derive_current_state(events[: index + 1])
        transition = evaluate_transition(previous_state, event, next_state, adapter)
        transition["supporting_event_ids"] = [event.get("event_id")] if event.get("event_id") else []
        transitions.append(transition)
        if transition["accepted"]:
            previous_state = transition["current_state"]
    return transitions
