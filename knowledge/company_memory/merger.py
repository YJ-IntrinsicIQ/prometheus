from __future__ import annotations

from typing import Optional

from .schema import CompanyMemory, Entity, Event, Evidence
from .updater import update_current_state
from .ids import make_entity_id, make_event_id, make_evidence_id


def merge_memory(existing_memory: Optional[CompanyMemory], new_document: dict) -> CompanyMemory:
    if existing_memory is None:
        memory = CompanyMemory(company_id=new_document.get("company_id", ""))
    else:
        memory = existing_memory

    company_id = memory.company_id or new_document.get("company_id", "")
    memory.company_id = company_id

    for entity_payload in new_document.get("entities", []):
        entity_name = entity_payload.get("name") or ""
        entity_id = make_entity_id(company_id, entity_name)
        entity = None

        for existing_entity in memory.entities.values():
            if existing_entity.id == entity_id:
                entity = existing_entity
                break

        if entity is None:
            entity = Entity(
                id=entity_id,
                name=entity_name,
                entity_type=entity_payload.get("entity_type", "entity"),
                metadata=entity_payload.get("metadata", {}),
            )
            memory.entities[entity_name] = entity

        for event_payload in entity_payload.get("events", []):
            event_type = event_payload.get("event_type", "unknown")
            event_id = make_event_id(company_id, entity.id, event_type)
            event = memory.events.get(event_id)

            if event is None:
                event = Event(
                    id=event_id,
                    entity_id=entity.id,
                    event_type=event_type,
                    summary=event_payload.get("summary", ""),
                    occurred_at=event_payload.get("occurred_at"),
                    metadata=event_payload.get("metadata", {}),
                )
                memory.events[event_id] = event
                entity.events.append(event_id)

            for evidence_payload in event_payload.get("evidence", []):
                source = evidence_payload.get("source", "")
                source_type = evidence_payload.get("source_type", "unknown")
                evidence_id = make_evidence_id(company_id, source, source_type)
                evidence = memory.evidence.get(evidence_id)

                if evidence is None:
                    evidence = Evidence(
                        id=evidence_id,
                        event_id=event.id,
                        source=source,
                        source_type=source_type,
                        content=evidence_payload.get("content"),
                        metadata=evidence_payload.get("metadata", {}),
                    )
                    memory.evidence[evidence_id] = evidence

                if evidence.id not in event.evidence_ids:
                    event.evidence_ids.append(evidence.id)

        update_current_state(memory, entity.id)

    memory.updated_at = memory.updated_at
    return memory
