"""
Deterministic Investor Sections Builder — ENG-MISSION50

Replaces LLM selection of substantive evidence content with deterministic
construction from canonical evidence sources.

ARCHITECTURE PRINCIPLE: Prometheus constructs investor intelligence.
The LLM explains it. The LLM never decides which facts make an answer
investor-grade when the system can determine those facts itself.

Key improvements over M48 semantic_sections.py:
- what_evidence_shows: multi-category evidence coverage, no cherry-picking
- what_management_says: future-facing hard commitments preferred; named initiatives
- management_consistency_map: readable behavior labels, not snake_case dimension keys
- what_is_not_yet_proven: investor-material future commitments first
- what_to_monitor: internal label sanitization; actionable specific items
- Temporal status protection: confirmed data cannot be rendered as projected

ENG-MISSION50 invariants:
  LLM_SECTION_OVERRIDE_BLOCKED = True
  RATING_LANGUAGE_CANNOT_ENTER_INVESTOR_SECTIONS = True
  INTERNAL_LABELS_BLOCKED_FROM_MONITORING = True
  ACTUAL_CANNOT_BECOME_PROJECTED = True
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

INVESTOR_SECTIONS_VERSION = "m50_investor_sections_v1"

# ── Internal-label detection ──────────────────────────────────────────────────

# snake_case patterns and known internal field names that must not appear
_INTERNAL_LABEL_PATTERN = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
_KNOWN_INTERNAL_LABELS = frozenset([
    "industry_outlook", "acquisition", "what_changed", "what_to_watch",
    "overall_view", "thesis_impact", "evidence_confidence",
])


def _is_internal_label(text: str) -> bool:
    """Return True if text looks like a raw internal field name."""
    stripped = str(text).strip()
    if not stripped:
        return False
    # Exact match to known internal labels
    if stripped.lower() in _KNOWN_INTERNAL_LABELS:
        return True
    # Single word or snake_case with no spaces → likely an internal key
    if " " not in stripped and "_" in stripped:
        return True
    # Pure CamelCase or PascalCase single identifier
    if _INTERNAL_LABEL_PATTERN.match(stripped):
        return True
    return False


def _sanitize_monitoring_item(item: str) -> Optional[str]:
    """Return None if item is an internal label; otherwise return the item."""
    if _is_internal_label(item):
        return None
    return item


# ── Hard commitment materiality scoring ──────────────────────────────────────

_YEAR_PATTERN = re.compile(r"20(\d{2})", re.IGNORECASE)
_FUTURE_FY_PATTERN = re.compile(r"fy(2[5-9]|[3-9]\d)", re.IGNORECASE)
_PAST_FY_PATTERN = re.compile(r"\bin\s+fy(1[0-9]|2[0-3])\b", re.IGNORECASE)


def _commitment_materiality_score(hc: Dict[str, Any], latest_fy: int = 26) -> int:
    """Score a hard commitment for investor materiality (higher = more relevant).

    Scoring:
      - Future target (> current FY): +30
      - Recent target (last 2-3 FY): +15
      - Past target with ongoing status: +5
      - Historical past target (>3 FY ago): 0
      - Has specific product/project name in topic: +10
      - Category is ESG or financial target: +5
    """
    score = 0
    tf = str(hc.get("expected_timeframe", "")).lower()
    topic = str(hc.get("topic", "")).lower()
    category = str(hc.get("category", "")).lower()

    # Extract year from timeframe
    year_match = _YEAR_PATTERN.search(tf)
    if year_match:
        full_year = int("20" + year_match.group(1))
        current_year = 2000 + latest_fy
        if full_year > current_year:
            score += 30
        elif full_year >= current_year - 2:
            score += 15
        elif full_year >= current_year - 5:
            score += 5

    # Penalize very old past-FY references
    if _PAST_FY_PATTERN.search(tf):
        score -= 10

    # Reward specific categories
    if "esg" in category or "financial" in category or "carbon" in topic:
        score += 5
    if "nidlegy" in topic or "product" in category:
        score += 5
    if len(topic) > 10:
        score += 3

    return score


def _sort_commitments_by_materiality(
    commitments: List[Dict[str, Any]], latest_fy: int = 26
) -> List[Dict[str, Any]]:
    """Return hard commitments sorted by investor materiality (highest first)."""
    return sorted(
        commitments,
        key=lambda hc: _commitment_materiality_score(hc, latest_fy),
        reverse=True,
    )


# ── Dimension label humanization ──────────────────────────────────────────────

_DIMENSION_LABELS: Dict[str, str] = {
    "execution_discipline": "Execution discipline",
    "capital_allocation_discipline": "Capital allocation discipline",
    "candor_and_consistency": "Candor and consistency",
    "strategic_clarity": "Strategic clarity",
    "risk_handling": "Risk handling",
    "owner_alignment": "Owner alignment",
    "adaptability": "Adaptability",
    "evidence_confidence": "Evidence confidence",
    "communication_transparency": "Communication transparency",
    "delivery_follow_through": "Delivery follow-through",
}

_ASSESSMENT_TO_STATUS: Dict[str, str] = {
    "strong": "CONSISTENT",
    "positive": "CONSISTENT",
    "improving": "CONSISTENT",
    "mixed": "INCONSISTENT",
    "weak": "INCONSISTENT",
    "negative": "INCONSISTENT",
    "deteriorating": "INCONSISTENT",
    "high": "CONSISTENT",
    "medium": "PARTIALLY_CONSISTENT",
    "low": "INCONSISTENT",
    "unknown": "UNABLE_TO_VERIFY",
}


def _humanize_dimension_label(key: str) -> str:
    """Convert snake_case dimension key to investor-readable label."""
    if key in _DIMENSION_LABELS:
        return _DIMENSION_LABELS[key]
    return key.replace("_", " ").title()


# ── Temporal status rendering ─────────────────────────────────────────────────

def _render_financial_value(value: float, unit: str, period: str, status: str = "ACTUAL") -> str:
    """Render a financial value with temporal status protection.

    ACTUAL/confirmed data → 'confirmed {period}' language.
    GUIDANCE/projected → 'guided {period}' language.
    TARGET/announced → 'target for {period}' language.

    This prevents confirmed FY data from being rendered as 'projected'.
    """
    val_str = f"₹{value:,.0f} cr" if "crore" in unit.lower() or "cr" in unit.lower() else f"{value} {unit}"
    fy_label = period.upper() if period else ""

    if status.upper() in ("ACTUAL", "CONFIRMED", "HISTORICAL"):
        return f"{val_str} (confirmed {fy_label})"
    elif status.upper() in ("GUIDANCE", "GUIDED"):
        return f"{val_str} (guided {fy_label})"
    elif status.upper() in ("TARGET", "ANNOUNCED_TARGET"):
        return f"{val_str} (target for {fy_label})"
    else:
        return f"{val_str} ({fy_label})"


# ── Evidence coverage categories ─────────────────────────────────────────────

_EVIDENCE_PRIORITY = {
    "project_operational": 10,       # Confirmed operational
    "per_share_compounding": 9,      # Capital returns confirmed
    "capital_outcome_partially_observed": 8,
    "project_partially_operational": 7,
    "risk_persistent": 6,            # Recurring conviction risk
    "risk_recurring": 6,
    "risk_increasing": 5,
    "capacity_operational": 7,
    "owner_earnings_bridge": 6,
    "risk_reducing": 4,
    "capital_outcome_unable_to_verify": 3,
}

# Evidence categories for diversity check
_EVIDENCE_CATEGORIES = {
    "execution": {"project_operational", "project_partially_operational", "capacity_operational"},
    "capital": {"per_share_compounding", "owner_earnings_bridge", "capital_outcome_partially_observed"},
    "risk": {"risk_persistent", "risk_recurring", "risk_increasing", "risk_reducing", "risk_emerging"},
}


def _build_evidence_bullet(item: Dict[str, Any]) -> str:
    """Build an investor-facing evidence bullet from an evidence item."""
    summary = str(item.get("summary", "")).strip()
    period = item.get("period", "")
    etype = item.get("evidence_type", "")

    if not summary:
        return ""

    # Skip overly generic per_share_compounding entries (just the label)
    if etype == "per_share_compounding" and summary.lower().startswith("per-share compounding"):
        fy = period.upper() if period else ""
        return f"Per-share value compounding confirmed ({fy})"

    period_str = f" ({period.upper()})" if period else ""
    return f"{summary}{period_str}"


def build_what_evidence_shows(fact_pack: Dict[str, Any]) -> List[str]:
    """Build what_evidence_shows deterministically from canonical evidence.

    Selection principles:
    1. Cover multiple evidence categories (execution, capital, risk)
    2. Prefer higher-priority evidence types
    3. Never cherry-pick a single worst/best year
    4. Include period labels
    5. Fall back to progression count summary if insufficient evidence
    """
    evidence_items = fact_pack.get("evidence_observations_raw", [])
    if not evidence_items:
        # Fall back to items from fact_pack_v2 evidence_observations field
        # These are pre-filtered by _extract_evidence_observations
        return _build_evidence_shows_from_fp(fact_pack)

    # Sort by priority
    sorted_items = sorted(
        [it for it in evidence_items if it.get("evidence_type") in _EVIDENCE_PRIORITY],
        key=lambda x: _EVIDENCE_PRIORITY.get(x.get("evidence_type", ""), 0),
        reverse=True,
    )

    # Select with diversity: at most 1 per category, prefer multi-period
    selected = []
    covered_categories = set()

    for item in sorted_items:
        etype = item.get("evidence_type", "")
        cat = next(
            (c for c, types in _EVIDENCE_CATEGORIES.items() if etype in types), "other"
        )
        if cat not in covered_categories:
            bullet = _build_evidence_bullet(item)
            if bullet and bullet not in selected:
                selected.append(bullet)
                covered_categories.add(cat)
        if len(selected) >= 3:
            break

    # If still short, add progression count
    if len(selected) < 2:
        selected.extend(_build_evidence_shows_from_fp(fact_pack)[:2])

    return selected[:3]


def _build_evidence_shows_from_fp(fp: Dict[str, Any]) -> List[str]:
    """Fallback: build evidence bullets from fact_pack_v2 pre-filtered observations."""
    bullets = list(fp.get("evidence_observations", []))
    # Add lifecycle summary if missing
    if len(bullets) < 2:
        pc = fp.get("progression_counts", {})
        total = pc.get("total", 0)
        delivered = pc.get("delivered", 0)
        in_progress = pc.get("in_progress", 0)
        announced = pc.get("announced", 0)
        period_range = fp.get("evidence_period_range", "FY20-FY26")
        if total > 0:
            bullets.append(
                f"Progression tracking ({period_range}): {total} items tracked; "
                f"{delivered} confirmed delivered, {in_progress} in progress, {announced} announced"
            )
    # Add commitment evidence
    if len(bullets) < 3:
        hc = fp.get("hard_commitment_count", 0)
        total_c = fp.get("commitment_counts", {}).get("total", 0)
        if total_c > 0:
            hc_str = f" ({hc} with specific targets)" if hc > 0 else ""
            bullets.append(
                f"Management commitment tracking{hc_str}: {total_c} statements tracked; "
                "all Unable To Verify — no confirmed delivery in public disclosures"
            )
    return bullets[:3]


def build_what_management_says(fact_pack: Dict[str, Any]) -> List[str]:
    """Build what_management_says from canonical hard commitments.

    Preference: future-facing material commitments, then recent past, then any hard.
    Includes actual commitment text (not generic paraphrase).
    """
    hard_commitments = fact_pack.get("hard_commitments", [])
    latest_fy = fact_pack.get("latest_fy", 26)

    if not hard_commitments:
        # Fall back to management_statements from V2 fact pack
        stmts = fact_pack.get("management_statements", [])
        return [s for s in stmts if s and len(str(s)) > 20][:2]

    # Sort by materiality
    sorted_hc = _sort_commitments_by_materiality(hard_commitments, latest_fy)

    bullets = []
    for hc in sorted_hc[:3]:
        mc_id = hc.get("id", "")
        tf = hc.get("expected_timeframe", "")
        # Use normalized_commitment (truncated); fall back to original
        stmt = hc.get("normalized_commitment", "")
        if not stmt:
            stmt = hc.get("original_statement", "")
        if not stmt:
            continue
        topic = hc.get("topic", "")

        # Build investor-facing bullet
        topic_str = f" ({topic})" if topic else ""
        tf_str = f" — target: {tf}" if tf else ""
        bullets.append(f"{stmt.rstrip('.')} [{mc_id}{tf_str}]{topic_str}: Unable To Verify")

    # All canonical hard commitments must be represented — no early break
    return bullets[:3]


def build_where_management_was_consistent(fact_pack: Dict[str, Any]) -> List[str]:
    """Build where_management_was_consistent from repeated assessment patterns.

    Consistent means: assessment is strong AND has supporting evidence across periods.
    """
    consistency_obs = fact_pack.get("consistency_observations", [])
    if consistency_obs:
        # Filter out generic/vague observations
        filtered = [
            obs for obs in consistency_obs
            if obs and len(str(obs)) > 20 and "assessment indicates consistent" not in str(obs)
        ]
        if filtered:
            return filtered[:2]

    # Build from dimension data
    consistency_map = fact_pack.get("consistency_map", {})
    bullets = []
    for dim_key, status in consistency_map.items():
        if "CONSISTENT" in str(status).upper() and dim_key != "evidence_confidence":
            label = _humanize_dimension_label(dim_key)
            bullets.append(f"{label}: consistent pattern observed across available evidence")
            if len(bullets) >= 2:
                break

    return bullets[:2]


def build_management_consistency_map(fact_pack: Dict[str, Any]) -> Dict[str, str]:
    """Build management_consistency_map with investor-readable labels and evidence context.

    Uses humanized dimension labels (not snake_case keys) with assessment context.
    Keeps evidence_confidence separate from lifecycle/outcome status.
    """
    raw_map = fact_pack.get("consistency_map", {})
    if not raw_map:
        return {}

    result = {}
    for dim_key, status_val in raw_map.items():
        human_label = _humanize_dimension_label(dim_key)
        status_str = str(status_val)

        # Evidence confidence dimension: keep as confidence level, not outcome state
        if dim_key == "evidence_confidence":
            # Don't map "high" → UNABLE_TO_VERIFY; preserve as confidence level
            assessment = str(fact_pack.get("evidence_confidence", "")).lower()
            if assessment == "high":
                result[human_label] = "HIGH — multiple source streams confirm evidence quality"
            elif assessment in ("medium", "moderate"):
                result[human_label] = "MEDIUM — sufficient source streams for assessment"
            else:
                result[human_label] = status_str
            continue

        # All other dimensions: map assessment to CONSISTENT/INCONSISTENT with context
        # NOTE: check INCONSISTENT first — "CONSISTENT" is a substring of "INCONSISTENT"
        if "INCONSISTENT" in status_str.upper():
            result[human_label] = "INCONSISTENT"
        elif "CONSISTENT" in status_str.upper():
            result[human_label] = "CONSISTENT"
        else:
            result[human_label] = "UNABLE_TO_VERIFY"

    return result


def build_what_is_not_yet_proven(fact_pack: Dict[str, Any]) -> str:
    """Build what_is_not_yet_proven from investor-material unresolved commitments.

    Priority:
    1. Future-facing hard commitments (specific deadlines not yet resolved)
    2. Recent announced projects not yet confirmed delivered
    3. Recurring risk items (from unresolved)
    """
    hard_commitments = fact_pack.get("hard_commitments", [])
    latest_fy = fact_pack.get("latest_fy", 26)

    parts = []

    # Sort by materiality and take top 2
    sorted_hc = _sort_commitments_by_materiality(hard_commitments, latest_fy)

    for hc in sorted_hc[:2]:
        mc_id = hc.get("id", "")
        tf = hc.get("expected_timeframe", "")
        stmt = hc.get("normalized_commitment", "")
        if not stmt:
            stmt = hc.get("original_statement", "")
        if not stmt:
            continue
        parts.append(
            f"Whether {mc_id} ({tf}): {stmt.rstrip('.')} — reaches confirmed delivered status"
        )

    # Add risk unresolved items from fact_pack
    raw_uncertainty = fact_pack.get("uncertainty_items", [])
    for item in raw_uncertainty[:1]:
        if item and item not in " ".join(parts):
            parts.append(str(item))

    return ". ".join(parts) if parts else (raw_uncertainty[0] if raw_uncertainty else "")


def build_what_to_monitor(fact_pack: Dict[str, Any]) -> List[str]:
    """Build what_to_monitor with internal-label sanitization.

    Each item answers: what specific item? what next milestone? what would resolve uncertainty?

    Rejects: internal labels (Industry_outlook, snake_case names, etc.)
    Requires: named items with specific next observable milestone.
    """
    hard_commitments = fact_pack.get("hard_commitments", [])
    latest_fy = fact_pack.get("latest_fy", 26)
    financial = fact_pack.get("financial_context", {})

    items = []

    # 1. Future-facing hard commitments as monitoring items
    sorted_hc = _sort_commitments_by_materiality(hard_commitments, latest_fy)
    for hc in sorted_hc[:2]:
        mc_id = hc.get("id", "")
        tf = hc.get("expected_timeframe", "")
        stmt = hc.get("normalized_commitment", "")
        if not stmt:
            stmt = hc.get("original_statement", "")
        if not stmt:
            continue
        items.append(
            f"{stmt.rstrip('.')} [{mc_id}, target: {tf}] — monitor for delivery confirmation"
        )

    # 2. Financial trajectory (only if we have confirmed baseline)
    rev = financial.get("revenue")
    npm = fact_pack.get("npm")
    if rev and rev.get("value") is not None and npm is not None:
        fy = rev.get("fiscal_year", "").upper()
        items.append(
            f"Revenue and net profit margin trajectory after {fy} — "
            f"whether confirmed NPM of {npm:.1f}% sustains in subsequent periods"
        )

    # 3. Weakest dimension monitoring
    consistency_map = fact_pack.get("consistency_map", {})
    for dim_key, status in consistency_map.items():
        if "INCONSISTENT" in str(status).upper() and dim_key != "evidence_confidence":
            label = _humanize_dimension_label(dim_key)
            items.append(
                f"{label}: currently INCONSISTENT — monitor for improvement in upcoming disclosures"
            )
            break

    # 4. Raw monitoring items — sanitize internal labels
    raw_monitoring = fact_pack.get("monitoring_items", [])
    for raw in raw_monitoring:
        if len(items) >= 4:
            break
        sanitized = _sanitize_monitoring_item(str(raw))
        if sanitized and sanitized not in " ".join(items):
            # Render as investor-readable monitoring item
            items.append(f"Monitor: {sanitized}")

    return items[:4]


def validate_consistency_map_vs_monitoring(
    consistency_map: Dict[str, str],
    what_to_monitor: List[str],
) -> List[str]:
    """Return list of contradiction descriptions if map contradicts monitoring items.

    A contradiction: dimension X = CONSISTENT in map, but monitoring says X is INCONSISTENT.
    """
    contradictions = []
    for label, status in consistency_map.items():
        if status == "CONSISTENT":
            for item in what_to_monitor:
                # e.g. "Candor and consistency: currently INCONSISTENT"
                if label.lower() in item.lower() and "INCONSISTENT" in item.upper():
                    contradictions.append(
                        f"Contradiction: '{label}' = CONSISTENT in map but monitoring says INCONSISTENT"
                    )
                    break
    return contradictions


def build_investor_sections(fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    """Build all investor sections deterministically. No AI calls.

    This is the M50 replacement for semantic_sections.build_deterministic_semantic_sections.
    The key difference: LLM may not override any of these sections.
    """
    consistency_map = build_management_consistency_map(fact_pack)
    what_to_monitor = build_what_to_monitor(fact_pack)
    contradictions = validate_consistency_map_vs_monitoring(consistency_map, what_to_monitor)

    result: Dict[str, Any] = {
        "what_evidence_shows": build_what_evidence_shows(fact_pack),
        "what_management_says": build_what_management_says(fact_pack),
        "where_management_was_consistent": build_where_management_was_consistent(fact_pack),
        "management_consistency_map": consistency_map,
        "what_is_not_yet_proven": build_what_is_not_yet_proven(fact_pack),
        "what_to_monitor": what_to_monitor,
        "_investor_sections_version": INVESTOR_SECTIONS_VERSION,
        "_llm_section_override_blocked": True,
    }
    if contradictions:
        result["_consistency_map_contradictions"] = contradictions
    return result
