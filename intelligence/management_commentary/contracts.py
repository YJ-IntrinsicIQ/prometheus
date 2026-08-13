from __future__ import annotations

COMMENTARY_SCHEMA_VERSION = "management_commentary.v1"
COMMENTARY_MANIFEST_SCHEMA_VERSION = "management_commentary_manifest.v1"
COMMENTARY_GENERATOR_VERSION = "management_commentary_builder.v1"

COMMENTARY_THEME_CATEGORIES = (
    "strategy",
    "growth",
    "margins",
    "customers",
    "demand",
    "projects",
    "capacity",
    "products",
    "technology",
    "capital_allocation",
    "working_capital",
    "cash_flow",
    "risk",
    "competition",
    "geography",
    "acquisitions",
    "execution",
    "governance",
    "other",
)

COMMENTARY_POSITIONS = (
    "observation",
    "increasing_priority",
    "stable_priority",
    "reduced_priority",
    "newly_introduced",
    "revised",
    "softened",
    "strengthened",
    "contradicted",
    "dropped_without_follow_up",
    "unresolved",
    "unable_to_verify",
)

COMMENTARY_POSITION_ORDER = {
    "unable_to_verify": -1,
    "unresolved": 0,
    "observation": 0,
    "newly_introduced": 1,
    "dropped_without_follow_up": 1,
    "stable_priority": 2,
    "reduced_priority": 2,
    "softened": 2,
    "increasing_priority": 3,
    "revised": 3,
    "strengthened": 4,
    "contradicted": 5,
}
