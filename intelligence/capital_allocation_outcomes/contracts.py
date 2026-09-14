from __future__ import annotations

ALLOCATION_OUTCOMES_SCHEMA_VERSION = "capital_allocation_outcomes.v1"
ALLOCATION_OUTCOMES_MANIFEST_SCHEMA_VERSION = "capital_allocation_outcomes_manifest.v1"
ALLOCATION_OUTCOMES_GENERATOR_VERSION = "capital_allocation_outcomes_builder.v1"

ALLOCATION_CATEGORIES = (
    "organic_capex",
    "capacity_expansion",
    "maintenance_capex",
    "acquisition",
    "acquisition_integration",
    "product_development",
    "research_and_development",
    "technology_investment",
    "working_capital",
    "debt_repayment",
    "debt_funded_investment",
    "dividend",
    "special_dividend",
    "share_buyback",
    "equity_issuance",
    "retained_cash",
    "strategic_investment",
    "joint_venture",
    "subsidiary_investment",
    "restructuring",
    "other",
    "unknown",
)

ALLOCATION_CURRENT_STATUSES = (
    "announced",
    "in_progress",
    "partially_deployed",
    "deployed",
    "delayed",
    "superseded",
    "abandoned",
    "unable_to_verify",
)

ALLOCATION_OUTCOME_STATUSES = (
    "not_yet_observable",
    "early_evidence",
    "partially_observed",
    "clearly_observed",
    "negative_outcome",
    "unclear",
    "unable_to_verify",
)

ALLOCATION_EVENT_TYPES = (
    "announcement",
    "progress",
    "confirmation",
    "delay_signal",
    "superseded",
    "abandonment",
    "latest_assessment",
)

ALLOCATION_FUNDING_SOURCES = (
    "operating_cash_flow",
    "retained_cash",
    "equity_issuance",
    "debt",
    "cash_reserves",
    "mixed",
    "unknown",
)

# ENG-122: Five-tier outcome attribution taxonomy.
# These classify EVIDENCE QUALITY for economic value attribution — not causal inference.
# HEURISTIC_CAUSAL_ATTRIBUTION_PATHS = 0: no token-overlap or temporal-sequence inference.
OUTCOME_ATTRIBUTION_LEVELS = (
    "DIRECTLY_ATTRIBUTABLE",       # Source explicitly states this allocation produced a specific economic outcome,
                                   # OR the transaction itself IS the economic event (distributions, debt repayment).
    "STRONGLY_SUPPORTED",          # Multiple convergent evidence items confirm execution + explicit outcome signal.
    "ASSOCIATED_NOT_ATTRIBUTABLE", # Deployment and execution confirmed; outcome association visible but causal
                                   # link to this specific allocation is not explicit in evidence.
    "NO_OUTCOME_EVIDENCE",         # Deployment observed; no downstream execution or outcome evidence available.
    "NEGATIVE_OUTCOME",            # Explicit evidence of delay, abandonment, or value destruction.
)

