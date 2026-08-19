"""
Shared temporal event splitter utility for multi-event extraction.

This module provides a generic event-splitting contract that distinguishes:
- Distinct events: separate actions/tranche/amounts/milestones with distinct years
- Context-only: comparisons, targets, statutes, statutory references (e.g., "Income Tax Act, 1961")

The contract returns split items with:
- split_from_item_id: original item_id before splitting
- split_event_index: 1-based index of this event
- split_event_count: total number of split events
- temporal_role: "historical_event" for distinct historical events, "statement_period" for current period
"""

import re
from typing import List, Dict, Any, Optional, Callable


# Regex to find year fragments (e.g., "Plan 2015", "Scheme 2018", "Project 2021", "FY2022", "FY 2022")
_MULTI_EVENT_YEAR_FRAGMENT_RE = re.compile(
    r"(?:^|,|\band\b)\s*([^,]*?(?:(?:19|20)\d{2}|FY\s*\d{2,4}))",
    re.IGNORECASE,
)

# Common leading action prefixes that should be stripped from fragments
_LEADING_ACTION_PREFIX_RE = re.compile(
    r"^(?:instituted/approved|institution/approval of|approved|instituted|institution|approval of)\s+",
    re.IGNORECASE,
)

# Default split hints - can be overridden per module
_DEFAULT_SPLIT_HINTS = (
    "plan",
    "scheme",
    "buyback",
    "dividend",
    "equity issuance",
    "employee stock",
    "stock purchase",
    "rsu",
    "esop",
    "esps",
    "employee stock purchase scheme",
    "preferential",
    "acquisition",
    "loan",
    "investment",
    "project",
    "facility",
    "plant",
    "factory",
    "manufacturing",
    "expansion",
    "construction",
    "capex",
    "capacity",
    "phase",
    "tranche",
    "milestone",
    "stage",
)


# Context-only patterns that should NOT trigger splitting
# These are statutory references, comparisons, or general timeframes
_CONTEXT_ONLY_PATTERNS = (
    r"income\s+tax\s+act",
    r"companies\s+act",
    r"securities\s+contract",
    r"regulation",
    r"statute",
    r"section\s+\d+",
    r"clause\s+\d+",
    r"as\s+per",
    r"pursuant\s+to",
    r"under\s+the",
    r"per\s+the",
    r"compared\s+to",
    r"vs\.?\s*\d{4}",
    r"versus\s+\d{4}",
    r"target\s+\d{4}",
    r"target\s+by\s+\d{4}",
    r"expected\s+by\s+\d{4}",
    r"plan\s+to\s+\d{4}",
    r"until\s+\d{4}",
    r"through\s+\d{4}",
    r"fiscal\s+\d{4}\s*[-–]\s*\d{4}",  # FY23-24 style ranges
    r"fy\d{2}\s*[-–]\s*fy\d{2}",
    r"year\s+ended",
    r"year\s+ending",
    r"period\s+ended",
    r"period\s+ending",
    r"as\s+at\s+\d{1,2}\w*\s+\w+\s+\d{4}",  # "as at March 31, 2024"
)


def is_context_only(text: str) -> bool:
    """
    Check if the text is context-only (statutory references, comparisons, targets)
    rather than distinct historical events.
    """
    text_lower = text.lower()
    for pattern in _CONTEXT_ONLY_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


def extract_year_fragments(action_text: str, split_hints: tuple = _DEFAULT_SPLIT_HINTS) -> List[tuple]:
    """
    Extract fragments from action text that contain years.

    Returns list of (fragment_text, year) tuples.
    """
    if not action_text:
        return []

    # Check if text is context-only (no splitting needed)
    if is_context_only(action_text):
        return []

    # Check if action text has any split hints
    action_lower = action_text.lower()
    if not any(hint in action_lower for hint in split_hints):
        return []

    fragments = _MULTI_EVENT_YEAR_FRAGMENT_RE.findall(action_text)

    # Also check for parenthetical content with years
    if len(fragments) < 2 and "(" in action_text and ")" in action_text:
        inner = action_text.split("(", 1)[1].rsplit(")", 1)[0]
        fragments = [
            fragment.strip()
            for fragment in re.split(r",|\band\b", inner, flags=re.IGNORECASE)
            if re.search(r"\b(?:19|20)\d{2}\b", fragment or "")
        ]

    # Clean fragments
    cleaned_fragments = [
        _LEADING_ACTION_PREFIX_RE.sub("", fragment).strip(" ;.,")
        for fragment in fragments
    ]

    # Parse year from each fragment
    parsed = []
    for fragment in cleaned_fragments:
        years = re.findall(r"\b(?:19|20)\d{2}\b", fragment)
        if years:
            parsed.append((fragment, years[-1]))

    return parsed


def split_compound_action(
    item: Dict[str, Any],
    action_field: str = "action",
    split_hints: tuple = _DEFAULT_SPLIT_HINTS,
    temporal_role: str = "historical_event",
    year_field: str = "year",
) -> List[Dict[str, Any]]:
    """
    Split a compound action item into multiple distinct events.

    Args:
        item: The original item dict
        action_field: The field containing the action text to split
        split_hints: Module-specific hints indicating splittable actions
        temporal_role: Role to assign to split events (default: "historical_event")
        year_field: Field name to set the extracted year to

    Returns:
        List of split items with split metadata, or original item if no split needed
    """
    action = item.get(action_field, "")
    if not action or item.get("item_id") is None:
        return [item]

    # Check if we have split hints in the action
    action_lower = action.lower()
    if not any(hint in action_lower for hint in split_hints):
        return [item]

    # Check if context-only
    if is_context_only(action):
        return [item]

    # Extract fragments with years
    parsed = extract_year_fragments(action, split_hints)

    if len(parsed) < 2:
        return [item]

    # Verify each fragment has a split hint
    if not all(
        any(hint in fragment.lower() for hint in split_hints)
        for fragment, _ in parsed
    ):
        return [item]

    # Create split items
    split_items = []
    original_item_id = item.get("item_id")

    for index, (fragment, year) in enumerate(parsed, start=1):
        split_item = dict(item)
        split_item[action_field] = fragment
        split_item["value"] = fragment
        split_item[year_field] = year
        split_item["split_from_item_id"] = original_item_id
        split_item["split_event_index"] = index
        split_item["split_event_count"] = len(parsed)
        split_item["temporal_role"] = temporal_role
        split_items.append(split_item)

    return split_items


class TemporalEventSplitter:
    """
    Configurable temporal event splitter for different modules.

    Usage:
        splitter = TemporalEventSplitter(
            action_field="action",
            split_hints=("plan", "scheme", "project", "phase"),
            temporal_role="historical_event",
            year_field="year",
        )

        split_items = splitter.split(item)
    """

    def __init__(
        self,
        action_field: str = "action",
        split_hints: tuple = _DEFAULT_SPLIT_HINTS,
        temporal_role: str = "historical_event",
        year_field: str = "year",
        context_only_patterns: tuple = _CONTEXT_ONLY_PATTERNS,
    ):
        self.action_field = action_field
        self.split_hints = split_hints
        self.temporal_role = temporal_role
        self.year_field = year_field
        self.context_only_patterns = context_only_patterns

        # Compile patterns for this instance
        self._multi_event_re = _MULTI_EVENT_YEAR_FRAGMENT_RE
        self._leading_prefix_re = _LEADING_ACTION_PREFIX_RE

    def is_context_only(self, text: str) -> bool:
        """Check if text is context-only (statutory, comparison, target)."""
        text_lower = text.lower()
        for pattern in self.context_only_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False

    def extract_fragments(self, action_text: str) -> List[tuple]:
        """Extract year-bearing fragments from action text."""
        if not action_text:
            return []

        if self.is_context_only(action_text):
            return []

        action_lower = action_text.lower()
        if not any(hint in action_lower for hint in self.split_hints):
            return []

        fragments = self._multi_event_re.findall(action_text)

        if len(fragments) < 2 and "(" in action_text and ")" in action_text:
            inner = action_text.split("(", 1)[1].rsplit(")", 1)[0]
            fragments = [
                fragment.strip()
                for fragment in re.split(r",|\band\b", inner, flags=re.IGNORECASE)
                if re.search(r"\b(?:19|20)\d{2}\b", fragment or "")
            ]

        cleaned_fragments = [
            self._leading_prefix_re.sub("", fragment).strip(" ;.,")
            for fragment in fragments
        ]

        parsed = []
        for fragment in cleaned_fragments:
            years = re.findall(r"\b(?:19|20)\d{2}\b", fragment)
            if not years:
                # Also check for FY format
                fy_match = re.search(r"FY\s*(\d{2,4})", fragment, re.IGNORECASE)
                if fy_match:
                    fy_year = fy_match.group(1)
                    if len(fy_year) == 2:
                        years = ["20" + fy_year]
                    else:
                        years = [fy_year]
            if years:
                parsed.append((fragment, years[-1]))

        return parsed

    def split(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split a compound action item into multiple distinct events."""
        action = item.get(self.action_field, "")
        if not action or item.get("item_id") is None:
            return [item]

        parsed = self.extract_fragments(action)

        if len(parsed) < 2:
            return [item]

        if not all(
            any(hint in fragment.lower() for hint in self.split_hints)
            for fragment, _ in parsed
        ):
            return [item]

        split_items = []
        original_item_id = item.get("item_id")

        for index, (fragment, year) in enumerate(parsed, start=1):
            split_item = dict(item)
            split_item[self.action_field] = fragment
            split_item["value"] = fragment
            split_item[self.year_field] = year
            split_item["split_from_item_id"] = original_item_id
            split_item["split_event_index"] = index
            split_item["split_event_count"] = len(parsed)
            split_item["temporal_role"] = self.temporal_role
            split_items.append(split_item)

        return split_items


# Pre-configured splitters for each module
CAPITAL_ALLOCATION_SPLITTER = TemporalEventSplitter(
    action_field="action",
    split_hints=(
        "plan", "scheme", "buyback", "dividend", "equity issuance",
        "employee stock", "stock purchase", "rsu", "esop", "esps",
        "employee stock purchase scheme", "preferential", "acquisition",
        "loan", "investment"
    ),
    temporal_role="historical_event",
    year_field="year",
)

CAPACITY_SPLITTER = TemporalEventSplitter(
    action_field="capacity_type",
    split_hints=(
        "phase", "tranche", "stage", "expansion", "facility", "plant",
        "capacity", "production", "line", "unit"
    ),
    temporal_role="historical_event",
    year_field="year",
)

PROJECT_SPLITTER = TemporalEventSplitter(
    action_field="project_name",
    split_hints=(
        "phase", "tranche", "stage", "project", "facility", "plant",
        "factory", "manufacturing", "expansion", "construction", "capex"
    ),
    temporal_role="historical_event",
    year_field="year",
)

PROMISE_SPLITTER = TemporalEventSplitter(
    action_field="promise",
    split_hints=(
        "phase", "tranche", "stage", "milestone", "target", "by",
        "commercial production", "commissioning", "launch", "completion"
    ),
    temporal_role="historical_event",
    year_field="year",
)

RISK_SPLITTER = TemporalEventSplitter(
    action_field="risk",
    split_hints=(
        "phase", "tranche", "stage", "period", "fiscal", "fy",
        "demand", "notice", "assessment", "appeal", "litigation"
    ),
    temporal_role="historical_event",
    year_field="year",
)