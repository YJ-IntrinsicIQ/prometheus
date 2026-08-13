from __future__ import annotations

PROJECTS_SCHEMA_VERSION = "projects.v1"
PROJECTS_MANIFEST_SCHEMA_VERSION = "projects_manifest.v1"
PROJECTS_GENERATOR_VERSION = "projects_builder.v1"

PROJECT_TYPES = (
    "facility",
    "capacity_expansion",
    "manufacturing_line",
    "product_development",
    "technology_implementation",
    "regulatory_compliance",
    "environmental_compliance",
    "energy_efficiency",
    "support_infrastructure",
    "maintenance",
    "csr",
    "non_core",
    "core_growth",
    "core_operational",
    "market_expansion",
    "customer_programme",
    "acquisition_integration",
    "infrastructure_upgrade",
    "transformation",
    "other",
)

PROJECT_STATUSES = (
    "announced",
    "planning",
    "funded",
    "under_execution",
    "partially_operational",
    "commissioned",
    "operational",
    "delayed",
    "paused",
    "cancelled",
    "superseded",
    "unable_to_verify",
)

PROJECT_STATUS_ORDER = {
    "announced": 0,
    "planning": 1,
    "funded": 2,
    "under_execution": 3,
    "partially_operational": 4,
    "commissioned": 5,
    "operational": 6,
    "delayed": 3,
    "paused": 3,
    "cancelled": 9,
    "superseded": 8,
    "unable_to_verify": -1,
}

PROJECT_EVENT_TYPES = (
    "project_announced",
    "scope_defined",
    "funding_committed",
    "land_acquired",
    "order_placed",
    "construction_started",
    "equipment_installed",
    "regulatory_approval",
    "trial_production",
    "commissioning",
    "commercial_operations",
    "capacity_ramp",
    "utilization_update",
    "delay_signal",
    "cost_revision",
    "scope_revision",
    "pause",
    "cancellation",
    "economic_impact_update",
    "latest_assessment",
)

ECONOMIC_IMPACT_STATUSES = (
    "not_yet_observable",
    "early_evidence",
    "partially_observed",
    "clearly_observed",
    "negative_outcome",
    "unclear",
)
