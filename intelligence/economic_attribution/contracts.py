"""Frozen contracts for economic attribution intelligence (ENG-135).

All constants here are FROZEN — changes require a new schema version.
"""
from __future__ import annotations

SCHEMA_VERSION = "economic_attribution_intelligence.v1"
GENERATOR_VERSION = "economic_attribution_builder.v1"

# ─── Attribution taxonomy (reused from ENG-122 CAO, authoritative) ─────────
ATTRIBUTION_LEVELS = (
    "DIRECTLY_ATTRIBUTABLE",        # Transaction IS the economic event (dividend, buyback, debt repayment)
    "STRONGLY_SUPPORTED",           # Multiple convergent evidence + explicit causal disclosure
    "ASSOCIATED_NOT_ATTRIBUTABLE",  # Deployment confirmed; causality unestablished
    "NO_OUTCOME_EVIDENCE",          # Execution exists; no outcome evidence present
    "NEGATIVE_OUTCOME",             # Evidence demonstrates adverse result defensibly
    "ATTRIBUTION_UNKNOWN",          # Insufficient basis to classify
)

# ─── Operating outcome contract (ENG-135 Step 7, FROZEN) ────────────────────
# What qualifies as operating outcome (must NOT be the execution state itself):
# - Capacity became operational AND utilization changed measurably
# - Product volume/adoption changed measurably
# - Geographic segment contributed identifiable revenue
# - Cost base changed measurably (not just cost-cutting announcement)
# - Working-capital behaviour changed measurably (days ratios)
OPERATING_OUTCOME_TYPES = (
    "capacity_operational_utilization_observed",
    "volume_adoption_observed",
    "geographic_segment_contribution_observed",
    "cost_base_changed_observed",
    "working_capital_behaviour_changed_observed",
    "product_revenue_contribution_observed",
    "none_disclosed",
    "unknown",
)

# ─── Financial consequence contract (ENG-135 Step 8, FROZEN) ────────────────
# Explicitly disclosed, not inferred:
FINANCIAL_CONSEQUENCE_TYPES = (
    "explicit_revenue_contribution",          # Source explicitly states segment/product contribution
    "explicit_margin_contribution",           # Source explicitly states margin effect
    "explicit_cost_savings",                  # Source explicitly states savings amount
    "explicit_cash_flow_change",              # Source explicitly states CFO effect
    "explicit_working_capital_release",       # Source explicitly states WC release
    "explicit_debt_reduction",                # Deterministic from debt schedules
    "explicit_capex_burden",                  # Deterministic from capex schedules
    "explicit_impairment_writeoff",           # Source explicitly states impairment
    "explicit_dilution",                      # Share count change is deterministic
    "explicit_eps_per_share_effect",          # Source explicitly states EPS effect
    "deterministic_transaction_consequence",  # The transaction itself produces a ledger outcome
    "none_disclosed",
    "unknown",
)

# ─── Economic consequence contract (ENG-135 Step 9, FROZEN) ─────────────────
# Must go BEYOND accounting movement:
ECONOMIC_CONSEQUENCE_TYPES = (
    "earning_power_change",          # Business's ability to generate earnings changed
    "cash_generation_change",        # Sustainable CFO trajectory changed
    "incremental_roic_established",  # Returns on incremental capital established
    "balance_sheet_resilience_change",
    "reinvestment_economics_shown",
    "per_share_owner_value_change",  # Equity value per share demonstrably changed
    "none_established",
    "unknown",
)

# ─── Economic materiality (ENG-135 Step 25, FROZEN) ─────────────────────────
# Based on economic EFFECT, not narrative prominence
MATERIALITY_LEVELS = (
    "MATERIAL",    # Effect is ≥2% of consolidated revenue, OR changes EPS ≥5%, OR debt material
    "MODERATE",    # Effect is 0.5–2% of consolidated revenue, or directionally significant
    "MINOR",       # Effect <0.5% of consolidated revenue
    "UNKNOWN",     # Cannot assess without attribution
)

# ─── Chain-stop classification (ENG-135 Step 6, FROZEN) ─────────────────────
CHAIN_STOP_REASONS = (
    "SOURCE_NOT_DISCLOSED",          # Source documents do not disclose outcome
    "OUTCOME_NOT_CAPTURED",          # No operating outcome captured in evidence
    "FINANCIAL_LINK_NOT_CAPTURED",   # Operating outcome exists but financial link not captured
    "ATTRIBUTION_NOT_DEFENSIBLE",    # Financial change exists but attribution cannot be established
    "ALTERNATIVE_EXPLANATIONS_UNRESOLVED",  # Causality ambiguous due to confounders
    "PER_SHARE_LINK_NOT_DEFENSIBLE", # Aggregate outcome exists but per-share effect not defensible
    "CORRECT_UNKNOWN",               # Chain stops correctly — nothing further can be said
    "CORRECT_KNOWN",                 # Chain is fully traceable and documented
)

# ─── Semantic contracts (ENG-135A + ENG-135, FROZEN) ────────────────────────
SEMANTIC_CONTRACTS = [
    "CHRONOLOGY_IS_NOT_CAUSALITY: action followed by financial improvement ≠ causal proof.",
    "ACQUISITION_COMPLETED ≠ integration success; acquisition signed ≠ value creation.",
    "PRODUCT_LAUNCHED ≠ commercial success; revenue growth ≠ product attribution.",
    "EXECUTION_STATE ≠ operating outcome; operating outcome ≠ economic consequence.",
    "MANAGEMENT_ATTRIBUTION ≠ independent proof; company claim requires external corroboration.",
    "ASSOCIATED_NOT_ATTRIBUTABLE: economic change occurred; causality not established.",
    "NO_OUTCOME_EVIDENCE: execution confirmed; outcome evidence absent (not FAILED).",
    "ALTERNATIVE_EXPLANATIONS must be considered before STRONGLY_SUPPORTED or higher.",
    "TEMPORAL_SEQUENCE_ONLY maps to ASSOCIATED_NOT_ATTRIBUTABLE at most.",
]
