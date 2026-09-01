from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


# ── Event type vocabulary ──────────────────────────────────────────────────────

STRATEGY_EVENT_TYPES = {
    "INTRODUCED",        # theme appears for the first time with intent signal
    "REINFORCED",        # theme repeated without material change
    "EXECUTION_STARTED", # execution action taken (capex, acquisition, launch)
    "EXPANDED",          # scope of existing theme widened
    "NARROWED",          # scope of existing theme reduced
    "ACCELERATED",       # explicit speed-up signal on existing theme
    "DELAYED",           # management signalled delay / slower execution
    "DEPRIORITIZED",     # management reduced emphasis; no reversal statement
    "PIVOTED",           # strategy direction changed within same domain
    "REVERSED",          # prior commitment explicitly reversed or abandoned
    "OUTCOME_VISIBLE",   # result of strategy visible (positive or negative)
    "CURRENT_PRIORITY",  # explicitly flagged as current period priority
    "NOT_RECONFIRMED",   # theme absent from recent periods; no abandonment statement
}


# ── Generic theme filter ───────────────────────────────────────────────────────

# Themes too broad to be investor-relevant strategy signals
_GENERIC_THEME_LABELS: Set[str] = {
    "governance_compliance",
    "human_capital",
    "csr",
    "sustainability",
    "risk_management",
    "energy_efficiency",
    "resource_efficiency",
    "unclassified_theme",
    "cost_efficiency",
    "quality_improvement",
    "supply_chain_stability",
}

# Keyword fragments that indicate generic operational language in free text
_GENERIC_KEYWORDS = {
    "focus on quality",
    "operational excellence",
    "improving processes",
    "business as usual",
    "continuing to invest",
    "ongoing efforts",
    "stakeholder engagement",
    "esg reporting",
    "data governance",
    "routine capex",
}


def is_generic_theme(theme_name: str) -> bool:
    """Return True if this theme is too generic to constitute a strategy signal."""
    normalized = theme_name.lower().strip()
    if normalized in _GENERIC_THEME_LABELS:
        return True
    if any(kw in normalized for kw in _GENERIC_KEYWORDS):
        return True
    return False


def normalize_theme_name(raw: str) -> str:
    """Convert raw management text to a consistent theme label."""
    return " ".join(raw.strip().split())


# ── Management focus → management_focus item classification ──────────────────

# Source event_type strings (from management_progression) → Gold event type
_MP_EVENT_TYPE_MAP = {
    "strategic_change": "INTRODUCED",
    "strategic_commitment": "INTRODUCED",
    "commitment_made": "INTRODUCED",
    "commitment_update": "REINFORCED",
    "commitment_delivered": "OUTCOME_VISIBLE",
    "commitment_missed": "OUTCOME_VISIBLE",
    "project_execution": "EXECUTION_STARTED",
    "project_outcome": "OUTCOME_VISIBLE",
    "capital_allocation": "EXECUTION_STARTED",
    "capacity_expansion": "EXECUTION_STARTED",
}


def classify_mp_event_type(event: Dict[str, Any], theme_first_period: Optional[str]) -> str:
    """
    Map a management_progression event to our Gold event vocabulary.

    If the event period matches the theme's first_period, it is INTRODUCED;
    subsequent events on the same theme default to REINFORCED unless richer
    signals indicate otherwise.
    """
    raw_type = (event.get("event_type") or "").lower()
    period = event.get("source_period") or event.get("event_period") or ""
    action = (event.get("action_taken") or "").lower()
    outcome = (event.get("operational_outcome") or "").lower()

    # Direct map for well-known types
    if raw_type in _MP_EVENT_TYPE_MAP:
        mapped = _MP_EVENT_TYPE_MAP[raw_type]
        # If not first period for INTRODUCED → REINFORCED
        if mapped == "INTRODUCED" and theme_first_period and period != theme_first_period:
            mapped = "REINFORCED"
        return mapped

    # Heuristic: execution signals in action text
    _EXECUTION_SIGNALS = (
        "launched", "acquired", "commissioned", "deployed", "completed",
        "opened", "commenced", "built", "signed"
    )
    if any(s in action for s in _EXECUTION_SIGNALS):
        return "EXECUTION_STARTED"

    # Outcome signals
    _OUTCOME_SIGNALS = (
        "resulted in", "revenue grew", "margin improved", "contribution",
        "ebitda", "roic", "succeeded", "failed", "impaired"
    )
    if any(s in outcome for s in _OUTCOME_SIGNALS):
        return "OUTCOME_VISIBLE"

    # Default: first period → INTRODUCED, else REINFORCED
    if theme_first_period and period == theme_first_period:
        return "INTRODUCED"
    return "REINFORCED"


# ── Strategy theme category ────────────────────────────────────────────────────

# Canonical theme categories used in Gold output
THEME_CATEGORIES = {
    "product_innovation",
    "market_expansion",
    "platform_differentiation",
    "capacity_investment",
    "acquisition_integration",
    "digital_transformation",
    "portfolio_rationalisation",
    "financial_inclusion",
    "regulatory_positioning",
    "supply_chain_vertical_integration",
    "capital_return_strategy",
    "other",
}

# Raw canonical theme names → Gold category
_THEME_CATEGORY_MAP: List[tuple[str, str]] = [
    ("product_innovation", "product_innovation"),
    ("manufacturing_capacity_expansion", "capacity_investment"),
    ("capex_program", "capacity_investment"),
    ("plant_construction", "capacity_investment"),
    ("geographic_expansion", "market_expansion"),
    ("customer_channel", "market_expansion"),
    ("capital_allocation", "capacity_investment"),
    ("innovative medicines", "product_innovation"),
    ("specialty", "product_innovation"),
    ("acquisition", "acquisition_integration"),
    ("digital", "digital_transformation"),
    ("platform", "platform_differentiation"),
    ("financial inclusion", "financial_inclusion"),
    ("api", "supply_chain_vertical_integration"),
    ("backward integration", "supply_chain_vertical_integration"),
    ("buyback", "capital_return_strategy"),
    ("dividend", "capital_return_strategy"),
]


def classify_theme_category(theme_name: str, canonical_key: str = "") -> str:
    """Map a theme name to a Gold category."""
    text = (theme_name + " " + canonical_key).lower()
    for keyword, category in _THEME_CATEGORY_MAP:
        if keyword in text:
            return category
    return "other"


# ── Business model evolution → event classification ──────────────────────────

def classify_bme_event_type(bme_entry: Dict[str, Any], known_themes: Set[str]) -> str:
    """
    Classify a business_model_evolution entry as a strategy event type.

    Checks what_changed text for acceleration, narrowing, pivot, or reversal signals.
    """
    what = (bme_entry.get("what_changed") or "").lower()
    why = (bme_entry.get("why_it_changed") or "").lower()
    combined = what + " " + why

    _PIVOT_SIGNALS = ("pivot", "shift from", "shifted from", "moved away", "transitioned from", "replaced")
    _REVERSAL_SIGNALS = ("reversed", "abandoned", "discontinued", "cancelled", "stopped")
    _ACCELERATE_SIGNALS = ("accelerat", "doubled down", "faster", "more aggressive", "scaled up")
    _NARROW_SIGNALS = ("narrowed", "narrowing", "focused only", "reduced scope", "pruned")
    _EXPAND_SIGNALS = ("expanded", "broadened", "added", "entered", "new market", "new product")

    if any(s in combined for s in _REVERSAL_SIGNALS):
        return "REVERSED"
    if any(s in combined for s in _PIVOT_SIGNALS):
        return "PIVOTED"
    if any(s in combined for s in _ACCELERATE_SIGNALS):
        return "ACCELERATED"
    if any(s in combined for s in _NARROW_SIGNALS):
        return "NARROWED"
    if any(s in combined for s in _EXPAND_SIGNALS):
        return "EXPANDED"
    return "REINFORCED"


# ── Strategy shift → event classification ────────────────────────────────────

def classify_shift_event(
    canonical_theme: str,
    direction: str,  # "added" or "removed"
    from_year: str,
    to_year: str,
    theme_first_period: Optional[str],
) -> str:
    """
    Classify a strategy_shift (theme added/removed across a period transition).
    """
    if direction == "removed":
        return "DEPRIORITIZED"
    # Theme added
    if theme_first_period == from_year or theme_first_period is None:
        return "INTRODUCED"
    # Was seen before → re-expanded / expanded
    return "EXPANDED"
