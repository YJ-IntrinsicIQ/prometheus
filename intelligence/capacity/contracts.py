from __future__ import annotations

CAPACITY_SCHEMA_VERSION = "capacity.v1"
CAPACITY_MANIFEST_SCHEMA_VERSION = "capacity_manifest.v1"
CAPACITY_GENERATOR_VERSION = "capacity_builder.v1"

CAPACITY_TYPES = (
    "manufacturing",
    "testing",
    "assembly",
    "production_line",
    "infrastructure",
    "logistics",
    "digital",
    "service_delivery",
    "workforce",
    "geographic",
    "other",
)

CAPACITY_STATUSES = (
    "announced",
    "planned",
    "funded",
    "under_construction",
    "installed",
    "commissioned",
    "operational",
    "ramping",
    "partially_utilized",
    "materially_utilized",
    "underutilized",
    "delayed",
    "paused",
    "cancelled",
    "superseded",
    "unable_to_verify",
)

CAPACITY_STATUS_ORDER = {
    "unable_to_verify": -1,
    "announced": 0,
    "planned": 1,
    "funded": 2,
    "under_construction": 3,
    "installed": 4,
    "commissioned": 5,
    "operational": 6,
    "ramping": 7,
    "partially_utilized": 8,
    "materially_utilized": 9,
    "underutilized": 10,
    "delayed": 11,
    "paused": 12,
    "cancelled": 13,
    "superseded": 14,
}

CAPACITY_EVENT_TYPES = (
    "capacity_announced",
    "capacity_plan_defined",
    "funding_committed",
    "construction_started",
    "equipment_ordered",
    "equipment_installed",
    "trial_run",
    "commissioning",
    "operations_started",
    "ramp_up_update",
    "utilization_update",
    "output_update",
    "bottleneck_update",
    "delay_signal",
    "cost_revision",
    "expansion_revision",
    "shutdown",
    "cancellation",
    "economic_impact_update",
    "latest_assessment",
)

UTILIZATION_STATUSES = (
    "not_disclosed",
    "pre_operational",
    "ramping",
    "low",
    "moderate",
    "high",
    "fully_utilized",
    "unclear",
)

ECONOMIC_IMPACT_STATUSES = (
    "not_yet_observable",
    "early_evidence",
    "partially_observed",
    "clearly_observed",
    "negative_outcome",
    "unclear",
)
