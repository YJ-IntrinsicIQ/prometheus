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

INVESTOR_SECTIONS_VERSION = "m522d_investor_sections_v4"

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
_REGULATORY_FILING = re.compile(r"\b(?:file|submit)\b.{0,120}\b(?:ema|fda|usfda|european medicines|regulator|authority|agency)\b", re.IGNORECASE)
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
    norm = str(hc.get("normalized_commitment", ""))
    if _REGULATORY_FILING.search(norm) or "product" in category:
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
        return f"Per-share compounding observation recorded ({fy}); direction not established"

    period_str = f" ({period.upper()})" if period else ""
    return f"{summary}{period_str}"


def _legacy_build_what_evidence_shows(fact_pack: Dict[str, Any]) -> List[str]:
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


def _legacy_build_what_management_says(fact_pack: Dict[str, Any]) -> List[str]:
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
    for hc in sorted_hc:
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
    return bullets


def _legacy_build_where_management_was_consistent(fact_pack: Dict[str, Any]) -> List[str]:
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


def _legacy_build_management_consistency_map(fact_pack: Dict[str, Any]) -> Dict[str, str]:
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


def _legacy_build_what_is_not_yet_proven(fact_pack: Dict[str, Any]) -> str:
    """Build what_is_not_yet_proven from investor-material unresolved commitments.

    Priority:
    1. Future-facing hard commitments (specific deadlines not yet resolved)
    2. Recent announced projects not yet confirmed delivered
    3. Recurring risk items (from unresolved)
    """
    hard_commitments = fact_pack.get("hard_commitments", [])
    latest_fy = fact_pack.get("latest_fy", 26)

    parts = []

    # Every material unresolved commitment is represented (no truncation)
    sorted_hc = _sort_commitments_by_materiality(hard_commitments, latest_fy)

    for hc in sorted_hc:
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


def _legacy_build_what_to_monitor(fact_pack: Dict[str, Any]) -> List[str]:
    """Build what_to_monitor with internal-label sanitization.

    Each item answers: what specific item? what next milestone? what would resolve uncertainty?

    Rejects: internal labels (Industry_outlook, snake_case names, etc.)
    Requires: named items with specific next observable milestone.
    """
    hard_commitments = fact_pack.get("hard_commitments", [])
    latest_fy = fact_pack.get("latest_fy", 26)
    financial = fact_pack.get("financial_context", {})

    items = []

    # 1. All material hard commitments — no truncation; every unresolved commitment must appear
    # INVARIANT: MATERIAL_UNRESOLVED_HARD_COMMITMENT → MONITORING_COVERAGE
    sorted_hc = _sort_commitments_by_materiality(hard_commitments, latest_fy)
    for hc in sorted_hc:
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
        if len(items) >= len(hard_commitments) + 3:
            break
        sanitized = _sanitize_monitoring_item(str(raw))
        if sanitized and sanitized not in " ".join(items):
            items.append(f"Monitor: {sanitized}")

    # Cap: all hard commitments preserved + up to 3 contextual items
    return items


def validate_consistency_map_vs_monitoring(
    consistency_map: Dict[str, str],
    what_to_monitor: List[str],
) -> List[str]:
    """Return list of contradiction descriptions if map contradicts monitoring items.

    A contradiction: dimension X = CONSISTENT in map, but monitoring says X is INCONSISTENT.
    """
    contradictions = []
    for label, status in consistency_map.items():
        if str(status).split(" — ")[0].strip() == "CONSISTENT":
            for item in what_to_monitor:
                # e.g. "Candor and consistency: currently INCONSISTENT"
                if label.lower() in item.lower() and "INCONSISTENT" in item.upper():
                    contradictions.append(
                        f"Contradiction: '{label}' = CONSISTENT in map but monitoring says INCONSISTENT"
                    )
                    break
    return contradictions




# ═══════════════════════════════════════════════════════════════════════════════
# ENG-MISSION52.2a/2d — evidence-backed section construction (enrichment-driven)
#
# Calibration invariant (M52.2d):  ABSENCE_OF_VERIFIED_OUTCOME != EVIDENCE_OF_NEGATIVE_BEHAVIOR.
# A behaviour classification other than UNABLE_TO_VERIFY needs a complete proof (named dimension,
# specific behaviour, comparison periods, comparable observations, sources, explanation,
# limitations). Observations that fall short are reported as observations, never as verdicts.
# ═══════════════════════════════════════════════════════════════════════════════

_STATUS_SEP = " — "
CLASSIFICATION_STATUSES = ("CONSISTENT", "PARTIALLY_CONSISTENT", "INCONSISTENT", "UNABLE_TO_VERIFY")
_MIN_COMPARISON_PERIODS = 3
_MIN_COMPARABLE_OBSERVATIONS = 3


def render_pct(value: Any) -> str:
    """Typed percentage rendering: 35 -> '35%', 19.64 -> '19.6%'."""
    v = float(value)
    return f"{v:.0f}%" if v == int(v) else f"{v:.1f}%"


def render_pct_exact(value: Any) -> str:
    """Percentage exactly as reported (21.85 stays 21.85%, never rounded)."""
    return f"{float(value):g}%"


def render_cr(value: Any) -> str:
    """Typed INR-crore rendering."""
    return f"₹{float(value):,.0f} cr"


def _fy(period: Any) -> str:
    m = re.search(r"(\d{2,4})", str(period or ""))
    if not m:
        return str(period or "").upper()
    n = int(m.group(1))
    return f"FY{(n % 100 if n > 100 else n):02d}"


def _compress_periods(periods: List[str], universe: List[str]) -> str:
    """'FY20–FY22 and FY24–FY26 (no FY23 record)' from period lists."""
    nums = sorted({int(re.search(r"\d+", p).group()) % 100 for p in periods if re.search(r"\d+", p)})
    uni = sorted({int(re.search(r"\d+", p).group()) % 100 for p in universe if re.search(r"\d+", p)})
    if not nums:
        return ""
    runs, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        runs.append((start, prev)); start = prev = n
    runs.append((start, prev))
    labels = [f"FY{a:02d}" if a == b else f"FY{a:02d}–FY{b:02d}" for a, b in runs]
    txt = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]
    gaps = [f"FY{n:02d}" for n in uni if nums[0] <= n <= nums[-1] and n not in nums]
    return txt + (f" (no {', '.join(gaps)} record)" if gaps else "")


def _enr(fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    return fact_pack.get("enrichment_v5") or {}


def _coverage(fact_pack: Dict[str, Any]) -> str:
    """Bounded-search phrase attached to every absence statement."""
    return (_enr(fact_pack).get("search_coverage") or {}).get("text") or "the tracked evidence streams"


def _ordered_commitment_facts(fact_pack: Dict[str, Any]) -> List[Dict[str, Any]]:
    facts = {c["id"]: c for c in _enr(fact_pack).get("commitments", [])}
    hard = _sort_commitments_by_materiality(fact_pack.get("hard_commitments", []), fact_pack.get("latest_fy", 26))
    return [facts[h["id"]] for h in hard if h.get("id") in facts]


# ── Classification proof contract ────────────────────────────────────────────

def classify_behavior(proof: Dict[str, Any]) -> str:
    """Return a behaviour classification only if the proof is complete; otherwise UNABLE_TO_VERIFY.

    proof keys: dimension, behavior, comparison_periods (list), comparable_observations (int),
    source_refs (list), direction ('consistent'|'contradictory'|'mixed'), explanation, limitations (list).
    Counts of unrelated positive/negative items are never an input.
    """
    needed = ("dimension", "behavior", "explanation", "limitations")
    if any(not proof.get(k) for k in needed):
        return "UNABLE_TO_VERIFY"
    if len(proof.get("comparison_periods") or []) < _MIN_COMPARISON_PERIODS:
        return "UNABLE_TO_VERIFY"
    if int(proof.get("comparable_observations") or 0) < _MIN_COMPARABLE_OBSERVATIONS:
        return "UNABLE_TO_VERIFY"
    if not proof.get("source_refs"):
        return "UNABLE_TO_VERIFY"
    return {"consistent": "CONSISTENT", "mixed": "PARTIALLY_CONSISTENT", "contradictory": "INCONSISTENT"}.get(
        proof.get("direction"), "UNABLE_TO_VERIFY")


def _entry(status: str, observed: str, missing: str, limitations: str, evidence: str = "") -> str:
    parts = [f"{status}{_STATUS_SEP}Observed: {observed}"]
    if evidence:
        parts.append(f"Evidence: {evidence}")
    if missing:
        parts.append(f"Not established: {missing}")
    parts.append(f"Limitations: {limitations}")
    return " ".join(p if p.endswith(('.', '?')) else p + "." for p in parts)


def _map_status(value: str) -> str:
    return str(value).split(_STATUS_SEP)[0].strip()


# ── Tracker scope wording ────────────────────────────────────────────────────

def tracker_scope_text(fact_pack: Dict[str, Any], *, short: bool = False) -> str:
    pc = fact_pack.get("progression_counts", {})
    delivered, total = pc.get("delivered", 0), pc.get("total", 0)
    tr = _enr(fact_pack).get("tracker") or {}
    pop = ", ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in sorted((tr.get("population") or {}).items(), key=lambda kv: -kv[1]))
    base = (f"The management-progression tracker records {delivered} confirmed deliveries among its {total} tracked items"
            + (f" ({pop})" if pop else ""))
    if short:
        return base
    vc = tr.get("verdict_counts") or {}
    rec = (f"; item-level reconciliation against other records: {vc.get('MATCHED_PARTIAL_PROGRESS', 0)} partially matched, "
           f"{vc.get('AMBIGUOUS_MATCH', 0)} ambiguous, {vc.get('NO_MATCH_FOUND', 0)} no match found") if vc else ""
    return base + "; separate records document product approvals, launches and operational activity" + rec


# ── Commitments: three independent facts + reported progress ─────────────────

def _commitment_ref(c: Dict[str, Any]) -> str:
    ann = f"; announced {_fy(c['announcement_period'])}" if c.get("announcement_period") else ""
    pg = f", p.{c['source_page']}" if c.get("source_page") else ""
    conv = " (calendar or financial year not specified in the source)" if c.get("target_period_convention") == "UNSPECIFIED_CALENDAR_OR_FINANCIAL_YEAR" else ""
    return f"[{c['id']} — target: {c['target']}{conv}{ann}{pg}]"


def _progress_text(c: Dict[str, Any], *, brief: bool = False) -> str:
    pr = c.get("progress") or {}
    ser = pr.get("series") or []
    if not ser:
        return ""
    points = "; ".join(f"{render_pct_exact(r['value'])} ({_fy(r['period'])})" for r in ser[-4:] if r["period"])
    if pr.get("basis") == "DERIVED_FROM_DISPOSAL_TABLE":
        what = "share of hazardous waste disposed that was co-processed (derived from the reported disposal tables, tonnes; not a management-stated percentage)"
    else:
        what = "cumulative absolute Scope 1+2 emissions reduction versus the 2020 baseline (management-stated)"
    pages = ", ".join(sorted({f"{_fy(r['period'])} p.{r['page']}" for r in ser[-4:] if r.get("page")}))
    note = ""
    if pr.get("latest_below_prior_report"):
        note = f"; the latest figure is lower than the prior report and the searched sources give no explanation (a restatement or boundary change is not established)"
    tgt = f" against the {render_pct_exact(pr['target_pct'])} target" if pr.get("target_pct") is not None else ""
    ach = "" if brief else "; management's own achievement statement against this target was not found in the searched sources"
    return f"reported {what}: {points}{tgt}{note}{ach} (source: {pages})"


def _mc_three_states(c: Dict[str, Any]) -> str:
    vs = " and ".join(f"{v['date']} ({_fy(v['period'])} annual report p.{v['page']})" for v in c.get("validation_statements", []))
    nl = f" The filing is stated as done by {c['filed_no_later_than']} at the latest ({c['filed_no_later_than_source']} pipeline update)." if c.get("filed_no_later_than") else ""
    return (
        f"FILING: submitted per later disclosures. DEADLINE (H1CY24 target): UNABLE_TO_VERIFY — the filing date is not stated; "
        f"EMA validation, a separate milestone, is dated {vs}; the subject of the second date cannot be resolved from the extracted text "
        f"(original PDF pages not available for confirmation).{nl} APPROVAL: not evidenced in the sources searched ({c.get('_coverage', 'tracked sources')})"
    )


def _commitment_says(c: Dict[str, Any], coverage: str = "") -> str:
    head = f"{c['display_text']} {_commitment_ref(c)}"
    c = {**c, "_coverage": coverage or "tracked sources"}
    if c.get("DELIVERY_STATE") == "FILING_CONFIRMED_BY_SOURCE_TEXT":
        return f"{head}: {_mc_three_states(c)}. The lifecycle tracker still shows {c['tracker_status']}"
    prog = _progress_text(c)
    if prog:
        state = "target period open" if c.get("TARGET_PERIOD_STATE") == "TARGET_PERIOD_OPEN" else "target period has passed under either year convention"
        return f"{head}: {state}; {prog}. The lifecycle tracker still shows {c['tracker_status']}"
    tp = {"TARGET_PERIOD_PASSED": f" — target period has passed; no result was found in the sources searched ({coverage})",
          "TARGET_PERIOD_OPEN": " — target period still open"}.get(c.get("TARGET_PERIOD_STATE"), "")
    return f"{head}: {c['tracker_status']}{tp}"


def build_what_management_says(fact_pack: Dict[str, Any]) -> List[str]:
    facts = _ordered_commitment_facts(fact_pack)
    if not facts:
        return _legacy_build_what_management_says(fact_pack)
    cov = _coverage(fact_pack)
    bullets = [_commitment_says(c, cov) for c in facts]
    enr = _enr(fact_pack)
    strat = (enr.get("behavior") or {}).get("stated_strategy")
    if strat:
        bullets.append(
            f"Stated strategy ('{strat['theme']}') recurs in {len(strat['periods'])} periods "
            f"({_fy(strat['periods'][0])}–{_fy(strat['periods'][-1])}); latest statement "
            f"({_fy(strat['periods'][-1])}): {strat['latest_statement'].rstrip('.')}"
        )
    clean = [x for x in enr.get("named_statements", []) if re.search(r"launch", x["statement"], re.I) and not x.get("transaction_entities")]
    for st in clean[:1]:
        bullets.append(f"{_fy(st['period'])} management statement: {st['statement']} (management-reported; product-level revenue not found in the sources searched)")
    return bullets


# ── Capital allocation and transactions ──────────────────────────────────────

def _transaction_lifecycle(t: Dict[str, Any]) -> str:
    terms = ", ".join(x for x in (t.get("price_per_share"), f"enterprise valuation {t['enterprise_valuation']}" if t.get("enterprise_valuation") else None) if x)
    cond = f"; subject to {t['closing_conditions']}" if t.get("closing_conditions") else ""
    ip = t.get("integration_planning_statement")
    plan = (f"Integration planning: management states that \"{ip['text'].rstrip('.')}\" (FY26 annual report p.{ip['page']}). ") if ip else ""
    return (
        f"{t['counterparty']} (evidence cutoff: FY26 annual report): SIGNED — definitive agreement dated {t['agreement_date']}, after the FY26 year-end"
        f"{': ' + terms if terms else ''}{cond} ({t['reference']}). CLOSING: not completed in the sources searched. {plan}"
        "OPERATIONAL INTEGRATION, FINANCIAL CONSOLIDATION and ATTRIBUTABLE ECONOMIC OUTCOMES: none can be attributed before closing is verified"
    )


def _capital_bullets(fact_pack: Dict[str, Any]) -> List[str]:
    cap = _enr(fact_pack).get("capital") or {}
    uni = cap.get("ledger_periods", [])
    out, parts = [], []
    acqs = cap.get("acquisitions", [])
    if acqs:
        names = "; ".join(
            f"{a['name']} ({_fy(a['periods'][0]) if a.get('periods') else ''}{', ' + a['date'] if a.get('date') else ''})" for a in acqs)
        parts.append(
            f"completed transactions recorded in the capital-allocation ledger: {names} — "
            f"{cap.get('acquisitions_with_attributable_outcome', 0)} of {len(acqs)} named transactions "
            f"have an attributable financial outcome and {cap.get('acquisitions_with_integration_visible', 0)} show visible integration"
            + (f" (plus an unnamed acquisition line item in {_compress_periods(cap['unnamed_acquisition_periods'], uni)})"
               if cap.get("unnamed_acquisition_periods") else ""))
    dp, bp = cap.get("dividend_periods", []), cap.get("buyback_periods", [])
    if dp or bp:
        dist = []
        if dp:
            dist.append(f"dividend line items in {_compress_periods(dp, uni)}")
        if bp:
            dist.append(f"buyback line items in {_compress_periods(bp, uni)}")
        parts.append("shareholder distributions observed: " + "; ".join(dist)
                     + " (cash-flow facts; a missing period may be an extraction gap rather than no payment; amounts not unit-verified; not an assessment of policy or allocation quality)")
    if parts:
        out.append("Capital deployment — " + "; ".join(parts) + ". No capital-weighted conclusion is supportable")
    for t in cap.get("announced_transactions", []):
        out.append(_transaction_lifecycle(t) if t.get("agreement_date") else
                   f"{t['counterparty']}: acquisition announced; recorded status {t['canonical_status'].replace('_', ' ')} — completion and integration not verified")
    return out


def _product_bullet(fact_pack: Dict[str, Any]) -> Optional[str]:
    enr = _enr(fact_pack)
    ms = enr.get("product_milestones", {})
    stmts = [x for x in enr.get("named_statements", []) if re.search(r"launch", x["statement"], re.I) and not x.get("transaction_entities")]
    if not ms and not stmts:
        return None
    parts = []
    for ent, evs in ms.items():
        ev = evs[0]
        when = f" {ev['date_text']}" if ev.get("date_text") else ""
        ref = f"({_fy(ev['period'])} annual report p.{ev['page']})"
        if ev["kind"] == "APPROVED":
            auth = "US FDA" if re.search(r"US\s?FDA", ev["excerpt"]) else "regulatory"
            parts.append(f"{ent}: {auth} approval reported{when} {ref}")
        else:
            parts.append(f"{ent}: {ev.get('phase') or 'clinical-phase'} activity reported{when} {ref}")
    launch = ""
    if stmts:
        ents = " and ".join(stmts[0]["product_entities"])
        launch = (f"; {_fy(stmts[0]['period'])} annual report states the launches of {ents} expanded the innovative-therapies portfolio "
                  f"(management-reported; product-level revenue was not found in the sources searched)")
    names = ", ".join(ms) or ", ".join(stmts[0]["product_entities"])
    return f"Specialty portfolio ({names}): " + "; ".join(parts) + launch


def _followup_bullet(fact_pack: Dict[str, Any]) -> Optional[str]:
    facts = _ordered_commitment_facts(fact_pack)
    if not facts:
        return None
    pieces = []
    for c in facts:
        if c.get("DELIVERY_STATE") == "FILING_CONFIRMED_BY_SOURCE_TEXT":
            pieces.append(f"{c['id']} filing confirmed, deadline adherence unable to verify, approval not evidenced")
        elif (c.get("progress") or {}).get("series"):
            pr = c["progress"]; last = pr["series"][-1]
            lvl = {"REPORTED_AT_OR_ABOVE_TARGET_LEVEL": "at or above the target level", "REPORTED_BELOW_TARGET_LEVEL": "below the target level"}.get(pr["progress_state"], "reported")
            pieces.append(f"{c['id']} {render_pct_exact(last['value'])} reported in {_fy(last['period'])}, {lvl} ({'derived' if pr.get('basis') == 'DERIVED_FROM_DISPOSAL_TABLE' else 'management-stated'})")
        elif c.get("TARGET_PERIOD_STATE") == "TARGET_PERIOD_PASSED":
            pieces.append(f"{c['id']} target passed, no result found in the sources searched")
        else:
            pieces.append(f"{c['id']} target still open")
    return (f"Hard-commitment follow-through ({len(facts)} tracked hard commitments): " + "; ".join(pieces)
            + f". {tracker_scope_text(fact_pack)}")


def _execution_bullet(fact_pack: Dict[str, Any]) -> Optional[str]:
    d = ((_enr(fact_pack).get("behavior") or {}).get("dimensions") or {}).get("execution_discipline")
    if not d or not d.get("positive"):
        return None
    neg = d.get("negative_operational", [])
    per = d.get("periods", [])
    rng = f" across {_fy(per[0])}–{_fy(per[-1])}" if per else ""
    return (
        f"{d['counts']['positive']} project/capacity items are reported operational or partially operational{rng}; most recent: "
        + "; ".join(d["positive"][:3])
        + (". Reported delayed or suspended: " + "; ".join(neg[:2]) if neg else "")
        + ". These are status labels: no comparison with original scope, timeline or budget was found in the sources searched, "
          "so they are not evidence of delivery reliability or of failure"
    )


def _risk_names(beh: Dict[str, Any], key: str = "candor_and_consistency") -> Dict[str, List[str]]:
    return (beh.get("dimensions") or {}).get(key) or (beh.get("dimensions") or {}).get("risk_handling") or {}


def _risk_bullet(fact_pack: Dict[str, Any]) -> Optional[str]:
    d = _risk_names(_enr(fact_pack).get("behavior") or {})
    if not d.get("recurring_risks"):
        return None
    red = d.get("reducing_risks", [])
    return (
        "Recurring or increasing risks disclosed: " + "; ".join(d["recurring_risks"])
        + (f". Risks reported as reducing: {'; '.join(red[:3])}" if red else "")
        + f". No management response or resolution for the recurring items was found in the sources searched ({_coverage(fact_pack)}) — "
          "a disclosure-verification gap, not evidence that no action was taken"
    )


def build_what_evidence_shows(fact_pack: Dict[str, Any]) -> List[str]:
    enr = _enr(fact_pack)
    if not enr or not (enr.get("capital") or enr.get("behavior") or enr.get("commitments")):
        return _legacy_build_what_evidence_shows(fact_pack)
    bullets = [b for b in (
        _product_bullet(fact_pack),
        _followup_bullet(fact_pack),
        *_capital_bullets(fact_pack),
        _execution_bullet(fact_pack),
        _risk_bullet(fact_pack),
    ) if b]
    return bullets or _legacy_build_what_evidence_shows(fact_pack)


# ── Behavioural consistency map (proof-gated) ────────────────────────────────

def build_management_consistency_map(fact_pack: Dict[str, Any]) -> Dict[str, str]:
    enr = _enr(fact_pack)
    beh = (enr.get("behavior") or {}).get("dimensions") or {}
    if not beh:
        return _legacy_build_management_consistency_map(fact_pack)
    cov = _coverage(fact_pack)
    result: Dict[str, str] = {}
    facts = _ordered_commitment_facts(fact_pack)
    cap = enr.get("capital") or {}
    uni = cap.get("ledger_periods", [])

    # Stated strategy — statements compared with statements (no outcome claim)
    strat = (enr.get("behavior") or {}).get("stated_strategy")
    if strat:
        status = classify_behavior({
            "dimension": "Strategic clarity (stated)", "behavior": f"'{strat['theme']}' theme stated",
            "comparison_periods": strat["periods"], "comparable_observations": strat.get("event_count", 0),
            "source_refs": [strat.get("theme_id")] if strat.get("theme_id") else [],
            "direction": "consistent", "explanation": "the same strategic theme recurs without reversal across periods",
            "limitations": ["compares statements only"]})
        result["Strategic clarity (stated)"] = _entry(
            status,
            f"the '{strat['theme']}' theme is stated in {len(strat['periods'])} of {len(enr.get('years_used') or strat['periods'])} periods "
            f"({_fy(strat['periods'][0])}: {strat['first_statement']}; {_fy(strat['periods'][-1])}: {strat['latest_statement']})",
            "", "this compares statements with statements; it says nothing about whether the strategy was executed or succeeded",
            evidence=f"{strat.get('event_count', '?')} statements across {_fy(strat['periods'][0])}–{_fy(strat['periods'][-1])} (commentary theme {strat.get('theme_id', 'n/a')})")

    # Execution — commitments vs observable execution
    d = beh.get("execution_discipline")
    if d:
        obs = []
        for c in facts:
            if c.get("DELIVERY_STATE") == "FILING_CONFIRMED_BY_SOURCE_TEXT":
                obs.append(f"{c['id']} filing submitted, deadline adherence not verifiable")
            elif (c.get("progress") or {}).get("series"):
                last = c["progress"]["series"][-1]
                obs.append(f"{c['id']} reported {render_pct_exact(last['value'])} in {_fy(last['period'])} against {render_pct_exact(c['progress']['target_pct'])}")
            else:
                obs.append(f"{c['id']} no outcome found")
        neg = d.get("negative_operational", [])
        result["Execution discipline"] = _entry(
            "UNABLE_TO_VERIFY",
            ("hard commitments: " + "; ".join(obs) + ". " if obs else "")
            + f"{d['counts']['positive']} project/capacity items reported operational or partially operational (e.g. {'; '.join(d['positive'][:2])})"
            + (f"; reported delayed or suspended: {'; '.join(neg[:2])}" if neg else ""),
            "performance against original scope, timeline or budget for projects, and management's own achievement statements for the commitments",
            f"status labels and single-milestone observations are not comparable delivery records; no failure is inferred from missing confirmation (sources searched: {cov})")

    # Risk handling — exposure -> response -> outcome
    r_ = beh.get("risk_handling")
    if r_:
        red = r_.get("reducing_risks", [])
        result["Risk handling"] = _entry(
            "UNABLE_TO_VERIFY",
            f"risk exposures flagged as recurring, persistent or increasing: {'; '.join(r_['recurring_risks'][:3]) or 'none named'}"
            + (f"; exposures reported as reducing: {'; '.join(red[:2])}" if red else ""),
            "management's response to each exposure and its observed outcome",
            f"a persistent risk can coexist with effective mitigation; no response or outcome was found in the sources searched ({cov})")

    # Candor — contradictions between statements and verified facts
    c_ = beh.get("candor_and_consistency")
    ctr = enr.get("contradictions") or {}
    if c_:
        genuine = ctr.get("genuine") or []
        periods = sorted({p_ for g in genuine for p_ in (g.get("earlier_period"), g.get("later_period")) if p_})
        status = classify_behavior({
            "dimension": "Candor and consistency", "behavior": "management statements later contradicted by verified facts",
            "comparison_periods": periods, "comparable_observations": len(genuine),
            "source_refs": [g.get("signal_id") for g in genuine if g.get("signal_id")],
            "direction": "contradictory", "explanation": "each signal pairs an earlier statement with later verified evidence that contradicts it",
            "limitations": ["limited to the tracker's contradiction signals"]}) if genuine else "UNABLE_TO_VERIFY"
        gap = ("Follow-up disclosure for prior-period risks was not found (a disclosure-verification gap)")
        observed = (f"{ctr.get('total', 0)} tracker signals, of which {ctr.get('types', {}).get('repeated_unresolved', 0)} are of type repeated_unresolved "
                    "(a statement repeated in later periods without a recorded resolution — not a contradiction); "
                    f"{ctr.get('genuine_contradictions', 0)} contradictions between a management statement and a verified fact were found. {gap}")
        if status == "UNABLE_TO_VERIFY":
            result["Candor and consistency"] = _entry(
                status, observed,
                "contradictory statements, unreconciled changes of explanation, or claims later contradicted by verified facts",
                f"missing follow-up is not evidence of concealment or inconsistency (sources searched: {cov})")
        else:
            result["Candor and consistency"] = _entry(
                status, observed, "", "limited to the tracker's contradiction signals",
                evidence=f"{len(genuine)} contradictions across {', '.join(_fy(x) for x in periods)} (signals {', '.join(g['signal_id'] for g in genuine if g.get('signal_id'))})")

    # Adaptability — challenge -> response -> follow-up -> outcome
    a_ = beh.get("adaptability")
    if a_:
        result["Adaptability"] = _entry(
            "UNABLE_TO_VERIFY",
            ("plan changes documented: " + "; ".join(a_["adaptation"][:2])) if a_.get("adaptation") else "no plan-change case documented",
            "a challenge -> management response -> follow-up -> outcome sequence for any case",
            "project, delay and risk items are different kinds of observation and are not combined into a score")

    o_ = beh.get("owner_alignment")
    if o_:
        result["Owner alignment"] = _entry(
            "UNABLE_TO_VERIFY",
            "owner-earnings and per-share observations are computed for each period, with direction unclear in the record",
            "direct evidence of owner-aligned decisions (for example ownership or compensation behaviour)",
            "a computed per-share series is not a behavioural comparison")

    # Distributions — observation, policy consistency and effectiveness are three separate questions
    dp, bp = cap.get("dividend_periods", []), cap.get("buyback_periods", [])
    if dp or bp:
        obs = []
        if dp:
            obs.append(f"dividend line items in {_compress_periods(dp, uni)}")
        if bp:
            obs.append(f"buyback line items in {_compress_periods(bp, uni)}")
        result["Distribution policy consistency"] = _entry(
            "UNABLE_TO_VERIFY", "; ".join(obs),
            "a stated distribution policy to compare against, and confirmation that any gap period is a true non-payment rather than an extraction gap",
            "buybacks need not occur annually; observed distributions are not an assessment of policy or of allocation quality")
    if cap.get("acquisitions"):
        names = ", ".join(a["name"] for a in cap["acquisitions"][:3])
        result["Capital allocation effectiveness"] = _entry(
            "UNABLE_TO_VERIFY",
            f"{len(cap['acquisitions'])} named transactions recorded ({names}); {cap.get('acquisitions_with_attributable_outcome', 0)} have an attributable financial outcome and {cap.get('acquisitions_with_integration_visible', 0)} show visible integration",
            "financial or operating outcomes attributable to the allocations",
            "most allocation amounts are unavailable, so no capital-weighted conclusion is permitted; activity is not skill, and missing attribution is not poor allocation")

    ec = fact_pack.get("evidence_confidence", "")
    if ec:
        result["Evidence confidence"] = (
            f"{str(ec).upper()}{_STATUS_SEP}Source-evidence coverage only: observations are available and extracted across multiple source streams. "
            "This does not verify any outcome and is not a confidence rating of any management-quality judgment above.")
    return result


def build_where_management_was_consistent(fact_pack: Dict[str, Any]) -> List[str]:
    if not _enr(fact_pack):
        return _legacy_build_where_management_was_consistent(fact_pack)
    out = []
    for label, val in build_management_consistency_map(fact_pack).items():
        if _map_status(val) == "CONSISTENT":
            out.append(f"{label}: {val.split(_STATUS_SEP, 1)[1]}")
    return out


# ── Open questions and monitoring ────────────────────────────────────────────

def build_what_is_not_yet_proven(fact_pack: Dict[str, Any]) -> str:
    facts = _ordered_commitment_facts(fact_pack)
    enr = _enr(fact_pack)
    if not facts and not enr:
        return _legacy_build_what_is_not_yet_proven(fact_pack)
    parts = []
    for c in facts:
        txt = f"the commitment \"{c['display_text']}\" ({c['id']}, target {c['target']})"
        if c.get("DELIVERY_STATE") == "FILING_CONFIRMED_BY_SOURCE_TEXT":
            parts.append(
                f"Whether the EMA grants marketing authorisation for {str(c['named_subject']).capitalize()} — a regulatory milestone separate from the "
                f"{c['id']} filing commitment; approval is not evidenced, and whether the filing met its H1CY24 target is unable to verify because the filing date is not stated")
        elif (c.get("progress") or {}).get("series"):
            pr = c["progress"]; last = pr["series"][-1]
            tail = "; the latest figure is below the prior report with no explanation found" if pr.get("latest_below_prior_report") else ""
            parts.append(f"Whether management confirms achievement of {txt}: reported progress is {render_pct_exact(last['value'])} ({_fy(last['period'])}) against {render_pct_exact(pr['target_pct'])}{tail}")
        elif c.get("TARGET_PERIOD_STATE") == "TARGET_PERIOD_PASSED":
            parts.append(f"Whether {txt} was achieved — the target period has passed and no result was found in the sources searched")
        else:
            parts.append(f"Whether {txt} is achieved by the target date")
    for t in (enr.get("capital") or {}).get("announced_transactions", []):
        parts.append(f"Whether the {t['counterparty']} acquisition closes{' (subject to ' + t['closing_conditions'] + ')' if t.get('closing_conditions') else ''} and, if it closes, how integration, consolidation and any economic outcome develop — none can be attributed before closing is verified")
    cap = enr.get("capital") or {}
    launch = [x for x in enr.get("named_statements", []) if re.search(r"launch", x["statement"], re.I) and not x.get("transaction_entities")]
    if launch:
        parts.append(f"Whether the {' and '.join(launch[0]['product_entities'])} launches translate into disclosed revenue or margin contribution — product-level financials were not found in the sources searched")
    if cap.get("acquisitions"):
        parts.append(f"Whether the completed acquisitions ({', '.join(a['name'] for a in cap['acquisitions'])}) produced attributable financial or integration outcomes — none is attributable in the capital-allocation ledger")
    sentences = [p.rstrip(".?") + "." for p in parts]
    for item in fact_pack.get("uncertainty_items", [])[:2]:
        if item and item not in " ".join(sentences):
            sentences.append(str(item).rstrip(".?") + "?")
    return " ".join(sentences) if sentences else _legacy_build_what_is_not_yet_proven(fact_pack)


def _monitor_commitment(c: Dict[str, Any], coverage: str) -> str:
    ref = f"[{c['id']}]"
    if c.get("DELIVERY_STATE") == "FILING_CONFIRMED_BY_SOURCE_TEXT":
        return (
            f"{str(c['named_subject']).capitalize()} EMA marketing-authorisation decision (a separate, forward-looking milestone; the {c['id']} H1CY24 target concerned the filing, "
            f"whose date is unable to verify): approval is not evidenced; monitor company disclosures (annual report, quarterly pipeline updates) for an EMA opinion or decision — "
            "no decision date, outcome or launch timing was found in the sources searched")
    prog = c.get("progress") or {}
    if prog.get("series"):
        last = prog["series"][-1]
        what = ("hazardous-waste co-processing share and management's own achievement statement against the target"
                if prog.get("basis") == "DERIVED_FROM_DISPOSAL_TABLE" else
                "the annual emissions-reduction figure (latest " + render_pct_exact(last['value']) + f" in {_fy(last['period'])} against {render_pct_exact(prog['target_pct'])} by 2030) and an explanation of any change versus the prior report")
        return f"{c['display_text']} {ref}: monitor {what}"
    if c.get("TARGET_PERIOD_STATE") == "TARGET_PERIOD_PASSED":
        return f"{c['display_text']} {ref}: target period has passed — monitor for management disclosure of the achieved result (none found in the sources searched: {coverage})"
    return f"{c['display_text']} {ref}: monitor annual disclosures of progress against the stated target"


def build_what_to_monitor(fact_pack: Dict[str, Any]) -> List[str]:
    enr = _enr(fact_pack)
    facts = _ordered_commitment_facts(fact_pack)
    if not enr or (not facts and fact_pack.get("hard_commitments")):
        return _legacy_build_what_to_monitor(fact_pack)
    cov = _coverage(fact_pack)
    items = [_monitor_commitment(c, cov) for c in facts]
    for t in (enr.get("capital") or {}).get("announced_transactions", []):
        if t.get("agreement_date"):
            items.append(
                f"{t['counterparty']} acquisition (agreement {t['agreement_date']}; {t.get('price_per_share') or 'terms in annual report'}"
                f"{', enterprise valuation ' + t['enterprise_valuation'] if t.get('enterprise_valuation') else ''}): monitor regulatory approvals, closing, funding, "
                "integration planning and — only after closing is verified — consolidation and attributable outcomes")
    launch = [x for x in enr.get("named_statements", []) if re.search(r"launch", x["statement"], re.I) and not x.get("transaction_entities")]
    if launch:
        ents = " and ".join(launch[0]["product_entities"])
        items.append(f"Revenue and margin contribution of the {ents} launches: not found in the sources searched — monitor whether later reports disclose product-level revenue or margin so the launches can be linked to financial outcomes")
    d = _risk_names(enr.get("behavior") or {})
    if d.get("recurring_risks"):
        items.append(f"Recurring risks ({'; '.join(d['recurring_risks'][:3])}): monitor whether later disclosures describe management responses and observed outcomes")
    fs = enr.get("financial_scope") or {}
    financial, npm = fact_pack.get("financial_context", {}), fact_pack.get("npm")
    rev = financial.get("revenue")
    if rev and rev.get("value") is not None and npm is not None:
        items.append(f"Revenue and net profit margin trajectory after {str(rev.get('fiscal_year', '')).upper()} — monitor whether the derived NPM of {render_pct(npm)} (profit attributable to owners of the parent over revenue from operations, consolidated) sustains in subsequent periods")
    if (enr.get("behavior") or {}).get("dimensions", {}).get("candor_and_consistency"):
        items.append("Disclosure verification: monitor whether later reports explicitly update prior-period commitments and risks (no follow-up for the recurring risk items was found in the sources searched)")
    return items


# ── Claim provenance (existing `claims` / `evidence_refs` mechanism) ─────────

def _ref(source: str, period: Any, location: str) -> Dict[str, str]:
    return {"source": source, "period": _fy(period) if period else "n/a", "location": location}


def build_claims(fact_pack: Dict[str, Any], answer: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Traceable records for the material assertions (behaviour classifications, delivery,
    regulatory milestones, financials, transaction status, absence claims)."""
    enr = _enr(fact_pack)
    if not enr:
        return []
    claims: List[Dict[str, Any]] = []
    cov = _coverage(fact_pack)

    def add(ctype, text, refs, status, limits):
        claims.append({"claim_id": f"CL-{len(claims) + 1:03d}", "claim_type": ctype, "claim_text": text,
                       "evidence_refs": refs, "verification_status": status, "limitations": limits})

    for c in enr.get("commitments", []):
        refs = [_ref("management_commitments record " + c["id"], c.get("announcement_period"), f"p.{c.get('source_page')}")]
        add("COMMITMENT", f"{c['id']}: {c['display_text']} (target {c['target']})", refs, "SOURCE_TEXT_VERIFIED",
            ["calendar vs financial year not specified in the source"] if c.get("target_period_convention") != "EXPLICIT" else [])
        if c.get("DELIVERY_STATE") == "FILING_CONFIRMED_BY_SOURCE_TEXT":
            ev = [_ref(f"{e['document'].replace('_', ' ')} chunk {e.get('chunk_id')}", e["period"], f"p.{e.get('page')}") for e in c["followup_events"] if e["kind"] in ("FILED", "VALIDATED")][:5]
            add("REGULATORY_MILESTONE", f"{c['id']} filing step confirmed by later disclosures", ev, "SOURCE_TEXT_VERIFIED",
                ["filing date not stated", "original PDF pages not available; verified against extracted text only"])
            add("REGULATORY_MILESTONE", f"{c['id']} deadline adherence unable to verify; approval not evidenced",
                [_ref("annual report", v["period"], f"p.{v['page']} ({v['date']})") for v in c.get("validation_statements", [])], "UNABLE_TO_VERIFY",
                ["validation dates are a different milestone from the filing date", "the second date's subject is unresolved"])
        pr = c.get("progress") or {}
        if pr.get("series"):
            add("PROGRESS", f"{c['id']}: " + "; ".join(f"{render_pct_exact(r['value'])} ({_fy(r['period'])})" for r in pr["series"][-4:]),
                [_ref(f"annual report chunk {r.get('chunk_id')}", r["period"], f"p.{r.get('page')}") for r in pr["series"][-4:]],
                "DERIVED" if pr.get("basis") == "DERIVED_FROM_DISPOSAL_TABLE" else "SOURCE_TEXT_VERIFIED",
                ["management's own achievement statement not found in the searched sources"]
                + (["share is derived from reported tonnes, not stated by management"] if pr.get("basis") == "DERIVED_FROM_DISPOSAL_TABLE" else []))
        if c.get("TARGET_PERIOD_STATE") == "TARGET_PERIOD_PASSED" and not pr.get("series") and c.get("DELIVERY_STATE") != "FILING_CONFIRMED_BY_SOURCE_TEXT":
            add("ABSENCE", f"{c['id']}: no result found after the target period", [], "NO_EVIDENCE_FOUND_IN_SEARCHED_SOURCES",
                [f"searched: {cov}", "this does not establish that the event did not occur"])
    for ent, evs in (enr.get("product_milestones") or {}).items():
        e = evs[0]
        add("REGULATORY_MILESTONE", f"{ent}: {e['kind'].lower()} reported", [_ref(f"annual report chunk {e.get('chunk_id')}", e["period"], f"p.{e.get('page')}")],
            "SOURCE_TEXT_VERIFIED", ["management-reported text; not independently confirmed with the regulator"])
    fs = enr.get("financial_scope") or {}
    for key, label in (("revenue", "Revenue"), ("pat", "PAT")):
        f = fs.get(key)
        if f:
            add("FINANCIAL", f"{label} {render_cr(f['value'])}: {f['line_item']}; {f['basis']}; year ended {f['period']}; {f['status'].lower()}",
                [_ref("financial truth record", f["fiscal_year"], f"p.{f.get('source_page')} ({f['line_item']})")], "SOURCE_TEXT_VERIFIED", [])
    if fs.get("npm"):
        add("FINANCIAL", f"NPM {render_pct(fact_pack.get('npm'))}: {fs['npm']['formula']}", [_ref("derived from the revenue and PAT records above", "fy26", "computed")], "DERIVED",
            ["a derived ratio, not a company-reported figure"])
    cap = enr.get("capital") or {}
    for a in cap.get("acquisitions", []):
        add("TRANSACTION_STATUS", f"{a['name']}: completed transaction recorded; outcome attribution {str(a.get('outcome_attribution')).lower().replace('_', ' ')}",
            [_ref(f"capital-allocation ledger {a['allocation_id']}", (a.get("periods") or [""])[0], "ledger record")], "SOURCE_TEXT_VERIFIED", ["no financial outcome attributable in the record"])
    for t in cap.get("announced_transactions", []):
        if t.get("agreement_date"):
            add("TRANSACTION_STATUS", f"{t['counterparty']}: definitive agreement dated {t['agreement_date']}; closing not completed in the sources searched",
                [_ref("annual report", "fy26", t["reference"].split(", ")[-1])], "SOURCE_TEXT_VERIFIED",
                ["evidence cutoff is the FY26 annual report", f"searched: {cov}"])
    tr = enr.get("tracker") or {}
    if tr.get("tracked_items"):
        add("SCOPE_STATEMENT", tracker_scope_text(fact_pack), [_ref("management_progression tracker", "fy26", "progression_items")], "SOURCE_TEXT_VERIFIED",
            ["tracker status not changed; item-level reconciliation uses conservative matching"])
    for label, val in (answer.get("management_consistency_map") or {}).items():
        if label == "Evidence confidence":
            continue
        st = _map_status(val)
        strat = (enr.get("behavior") or {}).get("stated_strategy") or {}
        refs = ([_ref(f"commentary theme {strat.get('theme_id')}", strat["periods"][0], "commentary_events (first statement)"),
                 _ref(f"commentary theme {strat.get('theme_id')}", strat["periods"][-1], "commentary_events (latest statement)")]
                if label.startswith("Strategic clarity") and strat else
                [_ref("see the map entry: observations listed there carry their own sources", "", label)])
        add("BEHAVIOR_CLASSIFICATION", f"{label}: {st}", refs,
            "SOURCE_TEXT_VERIFIED" if st != "UNABLE_TO_VERIFY" else "UNABLE_TO_VERIFY",
            ["see 'Not established' and 'Limitations' in the entry"])
    if _risk_names(enr.get("behavior") or {}).get("recurring_risks"):
        add("ABSENCE", "No management response or resolution was found for the recurring risk items", [], "NO_EVIDENCE_FOUND_IN_SEARCHED_SOURCES",
            [f"searched: {cov}", "a disclosure-verification gap, not evidence that no action was taken"])
    return claims


# ── Quality gate ─────────────────────────────────────────────────────────────

def validate_section_quality(answer: Dict[str, Any], fact_pack: Dict[str, Any]) -> List[str]:
    """Deterministic content gates for investor-facing text. Returns violations (empty = PASS)."""
    issues: List[str] = []
    public = {k: v for k, v in answer.items() if not k.startswith("_") and k not in ("deterministic_precision_facts", "claims")}
    flat = " ".join(
        str(v) if not isinstance(v, (list, dict)) else " ".join(map(str, v if isinstance(v, list) else v.values()))
        for v in public.values())
    low = flat.lower()
    for bad in ("assessment=", "compounding confirmed", "industry_outlook", "poor risk management", "failed to deliver",
                "no integration or operating contribution can exist", "management delivered nothing"):
        if bad in low:
            issues.append(f"BLOCKED_PHRASE: {bad}")
    if re.search(r"\b\d+\b[^.]{0,120}\bagainst \d+ (?:negative|delayed|adverse)\b", flat):
        issues.append("ARITHMETIC_CLASSIFICATION_FROM_INCOMPARABLE_COUNTS")
    for unbounded in ("do not document", "no result is disclosed", "not disclosed in the record", "none is disclosed"):
        if unbounded in low:
            issues.append(f"UNBOUNDED_ABSENCE_CLAIM: {unbounded}")
    for item in answer.get("what_to_monitor", []):
        if str(item).startswith("Monitor: "):
            issues.append(f"RAW_MONITORING_FRAGMENT: {item[:60]}")
        if "marketing-authorisation" in str(item) and re.search(r"target:\s*H1CY24", str(item)):
            issues.append("FILING_DEADLINE_ATTACHED_TO_APPROVAL_MILESTONE")
    for c in _enr(fact_pack).get("commitments", []):
        for sec in ("what_management_says", "what_to_monitor"):
            if not any(c["id"] in str(x) for x in answer.get(sec, [])):
                issues.append(f"COMMITMENT_MISSING:{c['id']}:{sec}")
        if c["id"] not in str(answer.get("what_is_not_yet_proven", "")):
            issues.append(f"COMMITMENT_MISSING:{c['id']}:what_is_not_yet_proven")
        if c["display_text"] not in " ".join(map(str, answer.get("what_management_says", []))):
            issues.append(f"UNIT_OR_TEXT_LOSS:{c['id']}")
    total = fact_pack.get("progression_counts", {}).get("total")
    if total:
        for t in re.findall(rf"[^.;]*\b0 (?:confirmed deliveries|of (?:its )?{total})\b[^.;]*", flat):
            if "tracker" not in t.lower():
                issues.append(f"TRACKER_SCOPE_NOT_STATED: {t.strip()[:70]}")
    for label, val in (answer.get("management_consistency_map") or {}).items():
        if label == "Evidence confidence":
            if "does not verify" not in str(val):
                issues.append("EVIDENCE_CONFIDENCE_NOT_SCOPED")
            continue
        status = _map_status(val)
        if status not in CLASSIFICATION_STATUSES:
            issues.append(f"UNKNOWN_STATUS:{label}:{status}")
        if _STATUS_SEP not in str(val) or "Limitations:" not in str(val):
            issues.append(f"LABEL_ONLY_CONSISTENCY_ENTRY:{label}")
        if status != "UNABLE_TO_VERIFY" and "Evidence:" not in str(val):
            issues.append(f"CLASSIFICATION_WITHOUT_EVIDENCE:{label}")
        if status == "UNABLE_TO_VERIFY" and "Not established:" not in str(val):
            issues.append(f"UNVERIFIED_WITHOUT_GAP_STATEMENT:{label}")
    return issues


def build_investor_sections(fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    """Build all investor sections deterministically. No AI calls."""
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
