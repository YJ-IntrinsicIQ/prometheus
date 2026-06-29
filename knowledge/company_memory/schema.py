from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .constants import DEFAULT_ENTITY_TYPE, DEFAULT_EVENT_TYPE, DEFAULT_SOURCE_TYPE, DEFAULT_STATE
from .ids import utc_now


@dataclass
class CurrentState:
    status: str = DEFAULT_STATE
    last_event_id: Optional[str] = None
    updated_at: str = field(default_factory=utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "last_event_id": self.last_event_id,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CurrentState":
        return cls(
            status=payload.get("status", DEFAULT_STATE),
            last_event_id=payload.get("last_event_id"),
            updated_at=payload.get("updated_at", utc_now()),
            metadata=payload.get("metadata", {}),
        )


@dataclass
class Evidence:
    id: str
    event_id: str
    source: str
    source_type: str = DEFAULT_SOURCE_TYPE
    content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "source": self.source,
            "source_type": self.source_type,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Evidence":
        return cls(
            id=payload["id"],
            event_id=payload["event_id"],
            source=payload.get("source", ""),
            source_type=payload.get("source_type", DEFAULT_SOURCE_TYPE),
            content=payload.get("content"),
            metadata=payload.get("metadata", {}),
            created_at=payload.get("created_at", utc_now()),
        )


@dataclass
class Event:
    id: str
    entity_id: str
    event_type: str = DEFAULT_EVENT_TYPE
    summary: str = ""
    occurred_at: Optional[str] = None
    evidence_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "event_type": self.event_type,
            "summary": self.summary,
            "occurred_at": self.occurred_at,
            "evidence_ids": self.evidence_ids,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Event":
        return cls(
            id=payload["id"],
            entity_id=payload["entity_id"],
            event_type=payload.get("event_type", DEFAULT_EVENT_TYPE),
            summary=payload.get("summary", ""),
            occurred_at=payload.get("occurred_at"),
            evidence_ids=payload.get("evidence_ids", []),
            metadata=payload.get("metadata", {}),
            created_at=payload.get("created_at", utc_now()),
        )


@dataclass
class Entity:
    id: str
    name: str
    entity_type: str = DEFAULT_ENTITY_TYPE
    events: List[str] = field(default_factory=list)
    current_state: Optional[CurrentState] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type,
            "events": self.events,
            "current_state": self.current_state.to_dict() if self.current_state else None,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Entity":
        state_payload = payload.get("current_state")
        state = CurrentState.from_dict(state_payload) if state_payload else None
        return cls(
            id=payload["id"],
            name=payload.get("name", ""),
            entity_type=payload.get("entity_type", DEFAULT_ENTITY_TYPE),
            events=payload.get("events", []),
            current_state=state,
            metadata=payload.get("metadata", {}),
            created_at=payload.get("created_at", utc_now()),
        )


@dataclass
class CompanyMemory:
    company_id: str
    entities: Dict[str, Entity] = field(default_factory=dict)
    events: Dict[str, Event] = field(default_factory=dict)
    evidence: Dict[str, Evidence] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company_id": self.company_id,
            "entities": {key: value.to_dict() for key, value in self.entities.items()},
            "events": {key: value.to_dict() for key, value in self.events.items()},
            "evidence": {key: value.to_dict() for key, value in self.evidence.items()},
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CompanyMemory":
        memory = cls(
            company_id=payload.get("company_id", ""),
            metadata=payload.get("metadata", {}),
            created_at=payload.get("created_at", utc_now()),
            updated_at=payload.get("updated_at", utc_now()),
        )
        for key, value in payload.get("entities", {}).items():
            memory.entities[key] = Entity.from_dict(value)
        for key, value in payload.get("events", {}).items():
            memory.events[key] = Event.from_dict(value)
        for key, value in payload.get("evidence", {}).items():
            memory.evidence[key] = Evidence.from_dict(value)
        return memory
