from __future__ import annotations

from typing import Any, Dict, List, Set

def _is_valid_period(period: Any) -> bool:
    return isinstance(period, str) and bool(period.strip())


def _has_circular_reference(node: Any, seen: Set[int]) -> bool:
    node_id = id(node)
    if node_id in seen:
        return True
    if isinstance(node, dict):
        seen.add(node_id)
        for value in node.values():
            if _has_circular_reference(value, seen):
                return True
        seen.remove(node_id)
    elif isinstance(node, list):
        seen.add(node_id)
        for value in node:
            if _has_circular_reference(value, seen):
                return True
        seen.remove(node_id)
    return False


def _event_sort_key(event: Dict[str, Any]) -> tuple:
    return (
        str(event.get("period") or ""),
        int(event.get("sequence") or 0),
        str(event.get("event_type") or ""),
        str(event.get("event_id") or ""),
    )


def _event_signature(event: Dict[str, Any]) -> tuple:
    metadata = tuple(sorted((event.get("metadata") or {}).items()))
    return (
        str(event.get("subject_id") or ""),
        str(event.get("stream_type") or ""),
        str(event.get("period") or ""),
        str(event.get("event_type") or ""),
        str(event.get("title") or ""),
        str(event.get("description") or ""),
        str(event.get("evidence_status") or ""),
        metadata,
    )


def validate_progression_payload(timeline_payload: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    events = timeline_payload.get("events") or []
    state_transitions = timeline_payload.get("state_transitions") or []
    turning_points = timeline_payload.get("turning_points") or []
    current_state = timeline_payload.get("current_state")
    event_ids: Set[str] = set()
    event_signatures: Set[tuple] = set()

    if _has_circular_reference(timeline_payload, set()):
        issues.append({"code": "circular_reference", "severity": "fail", "message": "Progression payload contains a circular reference."})

    for index, event in enumerate(events):
        event_id = str(event.get("event_id") or "").strip()
        if not event_id:
            issues.append({"code": "missing_event_id", "severity": "fail", "message": f"Event at index {index} is missing an event_id."})
        elif event_id in event_ids:
            issues.append({"code": "duplicate_event_id", "severity": "fail", "event_id": event_id, "message": "Duplicate event_id detected."})
        else:
            event_ids.add(event_id)

        signature = _event_signature(event)
        if signature in event_signatures:
            issues.append({"code": "duplicate_event", "severity": "fail", "event_id": event_id, "message": "Duplicate event detected."})
        else:
            event_signatures.add(signature)

        if not _is_valid_period(event.get("period")):
            issues.append({"code": "invalid_period", "severity": "fail", "event_id": event_id, "message": "Event period is invalid."})
        if not isinstance(event.get("sequence"), int):
            issues.append({"code": "invalid_sequence", "severity": "fail", "event_id": event_id, "message": "Event sequence must be an integer."})
        if not event.get("source_references"):
            issues.append({"code": "missing_source_references", "severity": "fail", "event_id": event_id, "message": "Event source references must be preserved."})
        confidence = event.get("confidence") or {}
        if "level" not in confidence or "basis" not in confidence or "limitations" not in confidence:
            issues.append({"code": "invalid_confidence", "severity": "fail", "event_id": event_id, "message": "Confidence must include level, basis, and limitations."})

    if events:
        ordered_ids = [str(event.get("event_id") or "") for event in events]
        sorted_ids = [str(event.get("event_id") or "") for event in sorted(events, key=_event_sort_key)]
        if ordered_ids != sorted_ids:
            issues.append({"code": "chronology_violation", "severity": "fail", "message": "Events must be chronologically ordered and deterministic."})

    turning_ids = {turning.get("event_id") for turning in turning_points}
    missing_turning = [turning.get("event_id") for turning in turning_points if turning.get("event_id") not in event_ids]
    if missing_turning:
        issues.append({"code": "invalid_turning_point_reference", "severity": "fail", "missing_event_ids": missing_turning, "message": "Turning points must reference existing events."})

    for index, transition in enumerate(state_transitions):
        supporting_event_ids = transition.get("supporting_event_ids") or []
        if not supporting_event_ids:
            issues.append({"code": "invalid_state_transition", "severity": "fail", "message": f"Transition {index} is missing supporting_event_ids."})
        for event_id in supporting_event_ids:
            if event_id not in event_ids:
                issues.append({"code": "invalid_state_transition", "severity": "fail", "event_id": event_id, "message": "State transitions must reference valid events."})

    if current_state is None:
        issues.append({"code": "missing_current_state", "severity": "fail", "message": "Current state is required."})
    elif state_transitions:
        accepted_transitions = [transition for transition in state_transitions if transition.get("accepted")]
        if accepted_transitions and accepted_transitions[-1].get("current_state") != current_state:
            issues.append({"code": "current_state_mismatch", "severity": "fail", "message": "Current state must match the final accepted transition."})

    unresolved = timeline_payload.get("unresolved_questions") or []
    if unresolved and not isinstance(unresolved, list):
        issues.append({"code": "invalid_unresolved_items", "severity": "fail", "message": "Unresolved questions must be a list."})

    if timeline_payload.get("investor_implication") is not None and not isinstance(timeline_payload.get("investor_implication"), dict):
        issues.append({"code": "invalid_investor_implication", "severity": "fail", "message": "Investor implication must be a dict container."})

    return {
        "status": "pass" if not issues else "fail",
        "issue_count": len(issues),
        "issues": issues,
    }
