from __future__ import annotations

from typing import List

from .schema import CompanyMemory


def validate_memory(memory: CompanyMemory) -> List[str]:
    errors: List[str] = []

    if not memory.company_id:
        errors.append("company_id is required")

    entity_ids = set()

    for entity_key, entity in memory.entities.items():
        if not entity.id:
            errors.append(f"entity {entity_key} is missing an id")
        elif entity.id in entity_ids:
            errors.append(f"duplicate entity id: {entity.id}")
        else:
            entity_ids.add(entity.id)

        if not entity.current_state:
            errors.append(f"entity {entity.id or entity_key} is missing current state")

        for event_id in entity.events:
            if event_id not in memory.events:
                errors.append(f"event {event_id} referenced by entity {entity.id or entity_key} was not found")

    for event_key, event in memory.events.items():
        if event.entity_id not in entity_ids:
            errors.append(f"event {event_key} references unknown entity {event.entity_id}")

        if not event.evidence_ids:
            errors.append(f"event {event_key} is missing evidence")

        for evidence_id in event.evidence_ids:
            if evidence_id not in memory.evidence:
                errors.append(f"evidence {evidence_id} referenced by event {event_key} was not found")

    for evidence_key, evidence in memory.evidence.items():
        if not evidence.source:
            errors.append(f"evidence {evidence_key} is missing a source")
        if evidence.event_id not in memory.events:
            errors.append(f"evidence {evidence_key} references unknown event {evidence.event_id}")

    return errors
