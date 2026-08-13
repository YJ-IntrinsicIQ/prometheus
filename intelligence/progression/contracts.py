from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


def _prune_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _prune_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_prune_none(item) for item in value]
    return value


@dataclass
class ProgressionEvent:
    event_id: str
    stream_type: str
    subject_id: str
    period: str
    sequence: int
    event_type: str
    title: str
    description: str
    evidence_status: str
    confidence: Dict[str, Any]
    source_references: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _prune_none(asdict(self))


@dataclass
class ProgressionState:
    subject_id: str
    stream_type: str
    previous_state: Any
    current_state: Any
    transition_type: str
    transition_period: str
    transition_reason: str
    confidence: Dict[str, Any]
    supporting_event_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _prune_none(asdict(self))


@dataclass
class TurningPoint:
    event_id: str
    period: str
    change_type: str
    description: str
    why_it_matters: str
    confidence: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return _prune_none(asdict(self))


@dataclass
class ProgressionSummary:
    what_changed: str
    why_it_changed: str
    conviction_impact: Dict[str, Any]
    current_state: Any
    latest_evidence: List[str]
    unresolved_items: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return _prune_none(asdict(self))


@dataclass
class ProgressionTimeline:
    subject_id: str
    stream_type: str
    events: List[Dict[str, Any]]
    turning_points: List[Dict[str, Any]]
    current_state: Any
    unresolved_questions: List[str]
    investor_implication: Dict[str, Any]
    confidence: Dict[str, Any]
    latest_period: str
    coverage_status: str
    state_transitions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return _prune_none(asdict(self))


@runtime_checkable
class ProgressionAdapter(Protocol):
    stream_type: str

    def normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def deduplicate_key(self, event: Dict[str, Any]) -> str:
        ...

    def validate_transition(self, previous_state: Any, event: Dict[str, Any], next_state: Any) -> Dict[str, Any]:
        ...

    def derive_current_state(self, events: List[Dict[str, Any]]) -> Any:
        ...

    def build_investor_implication(self, timeline: Dict[str, Any]) -> Dict[str, Any]:
        ...
