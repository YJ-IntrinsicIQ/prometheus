from __future__ import annotations

from .schema import CompanyMemory, CurrentState
from .ids import utc_now


def update_current_state(memory: CompanyMemory, entity_id: str) -> None:
    entity = None
    for candidate in memory.entities.values():
        if candidate.id == entity_id:
            entity = candidate
            break

    if entity is None:
        return

    event_ids = entity.events
    if not event_ids:
        if entity.current_state is None:
            entity.current_state = CurrentState(status="unknown")
        return

    latest_event_id = event_ids[-1]
    latest_event = memory.events.get(latest_event_id)

    if latest_event is None:
        if entity.current_state is None:
            entity.current_state = CurrentState(status="unknown")
        return

    entity.current_state = CurrentState(
        status=latest_event.event_type,
        last_event_id=latest_event.id,
        updated_at=utc_now(),
        metadata={"summary": latest_event.summary},
    )
