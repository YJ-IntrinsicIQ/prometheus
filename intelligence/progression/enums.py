from __future__ import annotations

STREAM_TYPES = (
    "management_commitment",
    "project",
    "capacity",
    "initiative",
    "risk",
    "management_commentary",
    "capital_allocation",
)

BASE_EVENT_TYPES = (
    "announcement",
    "update",
    "progress",
    "confirmation",
    "delay",
    "contradiction",
    "reversal",
    "completion",
    "abandonment",
    "superseded",
    "current_state",
    "unresolved",
)

EVIDENCE_STATUSES = (
    "direct",
    "derived",
    "partial",
    "conflicting",
    "missing",
    "unreliable",
)

CONFIDENCE_LEVELS = ("high", "medium", "low", "unavailable")

TURNING_POINT_TYPES = (
    "acceleration",
    "delay",
    "contradiction",
    "completion",
    "abandonment",
    "reversal",
    "superseded",
    "evidence_quality_change",
)

