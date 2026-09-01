from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple


# ── Theme current status ───────────────────────────────────────────────────────

_NOT_RECONFIRMED_GAP = 2  # periods of silence before marking NOT_RECONFIRMED

ALL_PERIODS = [
    "fy14", "fy15", "fy16", "fy17", "fy18", "fy19", "fy20",
    "fy21", "fy22", "fy23", "fy24", "fy25", "fy26", "fy27",
]


def _period_index(period: str) -> int:
    try:
        return ALL_PERIODS.index(period)
    except ValueError:
        return -1


def resolve_theme_current_status(
    theme_periods: List[str],
    latest_data_period: str,
    events: List[Dict[str, Any]],
) -> str:
    """
    Determine whether a theme is still a current priority, not reconfirmed,
    or explicitly deprioritized.

    Silence ≠ abandonment: use NOT_RECONFIRMED not DEPRIORITIZED unless
    an explicit deprioritization event is present.
    """
    if not theme_periods:
        return "NOT_RECONFIRMED"

    latest_theme_idx = max(_period_index(p) for p in theme_periods)
    latest_data_idx = _period_index(latest_data_period)

    # Check for explicit deprioritization event
    deprioritized_types = {"DEPRIORITIZED", "REVERSED"}
    has_deprioritized = any(e.get("event_type") in deprioritized_types for e in events)
    if has_deprioritized:
        return "DEPRIORITIZED"

    # Current priority: theme appears in latest or near-latest period
    if latest_data_idx >= 0:
        gap = latest_data_idx - latest_theme_idx
        if gap <= 1:
            return "CURRENT_PRIORITY"
        if gap <= _NOT_RECONFIRMED_GAP:
            return "NOT_RECONFIRMED"
        return "NOT_RECONFIRMED"

    return "NOT_RECONFIRMED"


# ── Repetition detection ───────────────────────────────────────────────────────

def detect_repetition(theme_periods: List[str]) -> bool:
    """
    Return True if the same theme appears in multiple periods without a gap
    suggesting it was forgotten and rediscovered.

    Repetition (REINFORCED) ≠ new introduction: a theme mentioned 3 years
    running is a persistent priority, not three separate introductions.
    """
    return len(set(theme_periods)) >= 2


# ── Pattern detection ──────────────────────────────────────────────────────────

_PERSISTENT_CORE_FOCUS_MIN_PERIODS = 4
_FREQUENT_TURNOVER_MAX_PERSISTENCE = 2
_FREQUENT_TURNOVER_MIN_THEMES = 3


def detect_patterns(
    themes: List[Dict[str, Any]],
    capital_allocations: List[Dict[str, Any]],
    latest_period: str,
) -> List[Dict[str, Any]]:
    """
    Detect investor-relevant strategy patterns across all tracked themes.

    Pattern IDs:
    - persistent_core_focus
    - strategy_broadening
    - strategy_narrowing
    - strategy_acceleration
    - capital_backed_strategy
    - strategy_without_execution
    - frequent_priority_turnover
    - repeated_strategy_reversal
    """
    patterns: List[Dict[str, Any]] = []

    if not themes:
        return patterns

    # ── persistent_core_focus ────────────────────────────────────────────────
    persistent = [
        t for t in themes
        if len(t.get("periods_active", [])) >= _PERSISTENT_CORE_FOCUS_MIN_PERIODS
        and t.get("current_status") in ("CURRENT_PRIORITY", "NOT_RECONFIRMED")
    ]
    if persistent:
        patterns.append({
            "pattern_id": "persistent_core_focus",
            "description": (
                "One or more strategy themes have been present across 4+ consecutive reporting periods, "
                "indicating a durable management priority rather than a one-off announcement."
            ),
            "themes": [t["theme_name"] for t in persistent],
            "investor_note": (
                "Persistent themes carry higher execution credibility. "
                "Track whether capital deployment matches the stated durability."
            ),
        })

    # ── strategy_broadening ──────────────────────────────────────────────────
    introduced_themes = [t for t in themes if _has_event_type(t, "INTRODUCED")]
    expanded_themes = [t for t in themes if _has_event_type(t, "EXPANDED")]
    broadening_themes = introduced_themes + expanded_themes
    # Only flag broadening if there are already established persistent themes
    if broadening_themes and persistent:
        patterns.append({
            "pattern_id": "strategy_broadening",
            "description": (
                "New strategy themes were introduced or existing themes expanded "
                "alongside an established persistent focus."
            ),
            "themes": [t["theme_name"] for t in broadening_themes[:4]],
            "investor_note": (
                "Broadening adds optionality but also execution risk. "
                "Track whether new themes receive capital backing before treating as commitments."
            ),
        })

    # ── strategy_narrowing ───────────────────────────────────────────────────
    narrowed_themes = [t for t in themes if _has_event_type(t, "NARROWED")]
    deprioritized_themes = [
        t for t in themes
        if t.get("current_status") == "DEPRIORITIZED"
        and len(t.get("periods_active", [])) >= 2
    ]
    if narrowed_themes or deprioritized_themes:
        all_narrowed = narrowed_themes + deprioritized_themes
        patterns.append({
            "pattern_id": "strategy_narrowing",
            "description": (
                "Management explicitly narrowed the strategy scope or deprioritized previously active themes."
            ),
            "themes": [t["theme_name"] for t in all_narrowed[:4]],
            "investor_note": (
                "Narrowing can signal discipline or retreat. "
                "Context — whether operational or capital constraints drove it — matters."
            ),
        })

    # ── strategy_acceleration ────────────────────────────────────────────────
    accelerated_themes = [t for t in themes if _has_event_type(t, "ACCELERATED")]
    if accelerated_themes:
        patterns.append({
            "pattern_id": "strategy_acceleration",
            "description": "Management signalled an explicit speed-up on one or more existing strategy themes.",
            "themes": [t["theme_name"] for t in accelerated_themes],
            "investor_note": (
                "Acceleration without capital backing is rhetoric. "
                "Verify whether capex or acquisition activity matches the stated acceleration."
            ),
        })

    # ── capital_backed_strategy ──────────────────────────────────────────────
    capital_backed = [t for t in themes if t.get("capital_backed") is True]
    if capital_backed:
        patterns.append({
            "pattern_id": "capital_backed_strategy",
            "description": (
                "Strategy themes for which capital deployment evidence exists (from Gold #2 — "
                "Capital Allocation Outcome Tracker)."
            ),
            "themes": [t["theme_name"] for t in capital_backed],
            "investor_note": (
                "Capital-backed themes carry stronger commitment signals than stated priorities alone. "
                "Track return evidence relative to deployment size."
            ),
        })

    # ── strategy_without_execution ───────────────────────────────────────────
    without_execution = [
        t for t in themes
        if not t.get("capital_backed")
        and not _has_event_type(t, "EXECUTION_STARTED")
        and len(t.get("periods_active", [])) >= 2
        and t.get("current_status") in ("CURRENT_PRIORITY", "NOT_RECONFIRMED")
    ]
    if without_execution:
        patterns.append({
            "pattern_id": "strategy_without_execution",
            "description": (
                "Strategy themes mentioned across multiple periods with no execution evidence "
                "(no capital deployment, no project action, no launched initiative)."
            ),
            "themes": [t["theme_name"] for t in without_execution[:4]],
            "investor_note": (
                "Repeated statements without execution are a credibility risk. "
                "Treat these as aspirational rather than committed priorities."
            ),
        })

    # ── frequent_priority_turnover ───────────────────────────────────────────
    short_lived = [
        t for t in themes
        if len(t.get("periods_active", [])) <= _FREQUENT_TURNOVER_MAX_PERSISTENCE
    ]
    if len(short_lived) >= _FREQUENT_TURNOVER_MIN_THEMES:
        patterns.append({
            "pattern_id": "frequent_priority_turnover",
            "description": (
                "Multiple strategy themes appeared for only 1-2 periods before disappearing, "
                "suggesting management attention rotates frequently."
            ),
            "themes": [t["theme_name"] for t in short_lived[:4]],
            "investor_note": (
                "High priority turnover makes execution difficult to assess. "
                "Focus analysis on persistent, capital-backed themes."
            ),
        })

    # ── repeated_strategy_reversal ───────────────────────────────────────────
    reversed_themes = [t for t in themes if _has_event_type(t, "REVERSED")]
    pivoted_themes = [t for t in themes if _has_event_type(t, "PIVOTED")]
    reversals = reversed_themes + pivoted_themes
    if len(reversals) >= 2:
        patterns.append({
            "pattern_id": "repeated_strategy_reversal",
            "description": "Two or more strategy themes show explicit pivot or reversal events.",
            "themes": [t["theme_name"] for t in reversals[:4]],
            "investor_note": (
                "Multiple reversals may indicate adaptive management or strategic instability. "
                "Assess whether pivots were capital-destroying or value-neutral."
            ),
        })

    return patterns


def _has_event_type(theme: Dict[str, Any], event_type: str) -> bool:
    return any(e.get("event_type") == event_type for e in theme.get("events", []))


# ── Capital backing cross-link ─────────────────────────────────────────────────

def resolve_capital_backing(
    theme_name: str,
    theme_category: str,
    capital_allocations: List[Dict[str, Any]],
) -> bool:
    """
    Return True if any capital allocation record matches this strategy theme.
    Cross-links Gold #2 (capital allocation tracker) with Gold #3 (strategy evolution).
    """
    if not capital_allocations:
        return False

    theme_lower = theme_name.lower()
    category_lower = theme_category.lower()

    _CATEGORY_TO_ALLOC_TYPES: Dict[str, Set[str]] = {
        "capacity_investment": {"ORGANIC_CAPEX", "CAPACITY_EXPANSION"},
        "acquisition_integration": {"ACQUISITION"},
        "digital_transformation": {"DIGITAL_OR_TECH_INVESTMENT"},
        "supply_chain_vertical_integration": {"ORGANIC_CAPEX", "CAPACITY_EXPANSION"},
        "product_innovation": {"R_AND_D", "NEW_MARKET_OR_PRODUCT"},
        "market_expansion": {"NEW_MARKET_OR_PRODUCT", "ACQUISITION"},
        "platform_differentiation": {"DIGITAL_OR_TECH_INVESTMENT", "R_AND_D"},
        "capital_return_strategy": {"DIVIDEND", "BUYBACK", "DEBT_REPAYMENT"},
        "financial_inclusion": {"ORGANIC_CAPEX", "NEW_MARKET_OR_PRODUCT"},
    }

    matching_types = _CATEGORY_TO_ALLOC_TYPES.get(category_lower, set())

    for alloc in capital_allocations:
        alloc_type = alloc.get("allocation_type") or ""
        alloc_name = (alloc.get("allocation_name") or "").lower()
        if alloc_type in matching_types:
            return True
        # Also check if theme keywords appear in allocation name
        for kw in theme_lower.split():
            if len(kw) >= 5 and kw in alloc_name:
                return True

    return False


# ── Opening / current state narrative ─────────────────────────────────────────

def resolve_opening_state(
    historical_stages: List[Dict[str, Any]],
    bme_items: List[Dict[str, Any]],
) -> str:
    """Build a 1-2 sentence summary of the company's strategic starting point."""
    if historical_stages:
        first_stage = min(historical_stages, key=lambda s: s.get("display_order", 99))
        desc = first_stage.get("simple_description") or first_stage.get("title") or ""
        period = first_stage.get("period_label") or ""
        if desc:
            return f"{desc.strip()}" + (f" ({period})" if period else "")
    if bme_items:
        first_bme = bme_items[0]
        what = first_bme.get("what_changed") or ""
        period = first_bme.get("from_period") or ""
        if what:
            return f"Strategy as of {period}: {what.strip()}"
    return ""


def resolve_current_state(
    business_journey: Dict[str, Any],
    themes: List[Dict[str, Any]],
) -> str:
    """Build current strategic state summary from business_journey."""
    current_direction = (business_journey.get("current_direction") or "").strip()
    current_state_raw = business_journey.get("current_state") or {}
    if isinstance(current_state_raw, dict):
        summary = current_state_raw.get("summary") or current_state_raw.get("description") or ""
    else:
        summary = str(current_state_raw)
    text = current_direction or summary
    if text:
        return text.strip()
    # Fallback: describe current priority themes
    current_themes = [t["theme_name"] for t in themes if t.get("current_status") == "CURRENT_PRIORITY"]
    if current_themes:
        return "Current strategic priorities: " + ", ".join(current_themes[:4]) + "."
    return ""
