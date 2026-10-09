"""
Deterministic Management Quality Fact Pack V2 — ENG-MISSION48

Extends V1 (management_fact_pack.v1) with:
  - hard_commitment_count: commitments with specific timeframes
  - npm: net profit margin from financial data
  - evidence_observations: from management_quality_evidence.json
  - management_statements: from management_quality_evidence.json
  - consistency_observations: from management_quality_dimensions.json
  - uncertainty_items_enriched: named specific commitments/risks
  - monitoring_items_enriched: specific actionable items
  - dpfs upgraded with hard commitment granularity and NPM

Backward-compatible: still exports build_management_quality_fact_pack (V1).
New entry point: build_management_quality_fact_pack_v2.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from intelligence.management_quality.fact_pack import (
    FACT_PACK_SCHEMA_VERSION as FACT_PACK_SCHEMA_VERSION_V1,
    build_management_quality_fact_pack,
    _load,
    _count_progression_lifecycle,
    _latest_financial_metrics,
)

FACT_PACK_SCHEMA_VERSION = "management_fact_pack.v2"

# Expected_timeframe strings that are NOT specific dates
_GENERIC_TIMEFRAMES = re.compile(
    r"^(unspecified|ongoing|no specific|tbd|n/?a|not specified|not defined|continuous|indefinite)",
    re.IGNORECASE,
)

# Patterns that indicate a specific date/timeframe
_SPECIFIC_DATE_PATTERN = re.compile(
    r"(fy\d{2,4}|H\d\s*CY\d{2,4}|Q\d\s*FY\d{2,4}|by\s+20\d{2}|in\s+20\d{2}|20\d{2})",
    re.IGNORECASE,
)

# M50.1: Verifiable content — quantified target, specific regulatory/milestone action.
# A hard commitment must contain at least one of these.
_HARD_COMMITMENT_VERIFIABLE_CONTENT = re.compile(
    r"\b\d+\s*%|"                                              # percentage target: 30%, 35%
    r"\b\d+\s+reduction\b|"                                    # "35 reduction" (normalized, % stripped)
    r"\b(?:co[\s-]?process|achieve)\b.{0,80}\b\d{1,3}\b|"     # action + non-year number (1-3 digits)
    r"\bfile\b.{0,120}\b(?:ema|fda|usfda|regulator|authority|agency)\b|"  # regulatory filing
    r"\bsubmit\b.{0,120}\b(?:ema|fda|usfda|regulator|authority|agency)\b",
    re.IGNORECASE,
)

# M50.1: Aspirational language — qualitative commitments that do not qualify as hard
# even when paired with a specific timeframe.
# Example: "Build a strong pipeline in fy21" — "strong" is unmeasurable.
# Example: "The company is increasing focus on its global specialty business in fy18" — retrospective observation.
_ASPIRATIONAL_LANGUAGE = re.compile(
    r"^build\s+a\s+(?:strong|robust|excellent|better|larger|bigger)\b|"
    r"^the\s+company\s+is\s+(?:increasing|growing|enhancing|expanding)\s+(?:focus|its)",
    re.IGNORECASE,
)


def _is_hard_commitment(item: Dict) -> bool:
    """Return True if a commitment qualifies as 'hard' under the M50.1 canonical policy.

    CANONICAL HARD COMMITMENT POLICY (ENG-MISSION50.1):
    A commitment is HARD only if ALL of:
    1. expected_timeframe contains a specific date (not unspecified/ongoing/tbd)
    2. normalized_commitment has VERIFIABLE CONTENT: a quantified target (percentage,
       number+unit) OR a specific named milestone action (regulatory filing, etc.)
    3. normalized_commitment is NOT purely aspirational language (qualitative phrases
       like "build a strong pipeline" or retrospective observations like "increasing focus
       on ... in fy18")

    Root cause of M50 discrepancy (V2=5, M37.8=4, canonical=3):
    V2 counted MC-0012 ("build a strong pipeline in fy21") and MC-0023
    ("increasing focus on specialty in fy18") — both fail criteria (2) and (3).
    These are qualitative aspirations and a retrospective observation respectively.
    """
    tf = str(item.get("expected_timeframe") or "").strip()
    if not tf:
        return False
    if _GENERIC_TIMEFRAMES.match(tf):
        return False
    if not _SPECIFIC_DATE_PATTERN.search(tf):
        return False
    norm = str(item.get("normalized_commitment") or "").strip()
    if _ASPIRATIONAL_LANGUAGE.match(norm):
        return False
    if not _HARD_COMMITMENT_VERIFIABLE_CONTENT.search(norm):
        return False
    return True


def _count_hard_commitments(items: List[Dict]) -> tuple[int, List[Dict]]:
    """Hard commitments under canonical M50.1 policy.

    A commitment is hard only if it has a specific timeframe AND verifiable content
    (quantified target or named milestone). Purely aspirational commitments with dates
    are excluded.

    Returns (count, list_of_hard_commitment_items).
    """
    hard = [item for item in items if _is_hard_commitment(item)]
    return len(hard), hard


def _compute_npm(financial: Dict[str, Any]) -> Optional[float]:
    """Compute NPM from revenue and PAT. Returns None if data missing."""
    rev = financial.get("revenue")
    pat = financial.get("pat")
    if not rev or not pat:
        return None
    rv = rev.get("value")
    pv = pat.get("value")
    if rv is None or pv is None or rv == 0:
        return None
    try:
        return round((float(pv) / float(rv)) * 100, 1)
    except (TypeError, ZeroDivisionError):
        return None


def _extract_evidence_observations(evidence_items: List[Dict]) -> List[str]:
    """Build what_evidence_shows skeleton from management_quality_evidence.json items.

    Picks observable outcome types: project_operational, capital_outcome_*, risk events.
    Returns up to 3 bullet strings.
    """
    OBSERVABLE_TYPES = {
        "project_operational",
        "project_partially_operational",
        "capital_outcome_partially_observed",
        "owner_earnings_bridge",
        "per_share_compounding",
        "risk_persistent",
        "risk_recurring",
        "risk_increasing",
        "risk_reducing",
    }
    bullets = []
    seen_summaries: set = set()
    for item in evidence_items:
        etype = item.get("evidence_type", "")
        if etype not in OBSERVABLE_TYPES:
            continue
        summary = str(item.get("summary", "")).strip()
        if not summary or summary in seen_summaries:
            continue
        seen_summaries.add(summary)
        period = item.get("period", "")
        period_str = f" ({period})" if period else ""
        bullets.append(f"{summary}{period_str}")
        if len(bullets) >= 3:
            break
    return bullets


def _extract_management_statements(evidence_items: List[Dict]) -> List[str]:
    """Build what_management_says skeleton from commitment evidence items."""
    STATEMENT_TYPES = {
        "commitment_unable_to_verify",
        "commitment_unknown",
    }
    bullets = []
    seen: set = set()
    for item in evidence_items:
        etype = item.get("evidence_type", "")
        if etype not in STATEMENT_TYPES:
            continue
        summary = str(item.get("summary", "")).strip()
        if not summary or summary in seen:
            continue
        seen.add(summary)
        bullets.append(summary)
        if len(bullets) >= 2:
            break
    return bullets


def _extract_consistency_observations(dimensions_data: Dict) -> tuple[List[str], Dict]:
    """Build where_management_was_consistent and management_consistency_map from dimensions.

    Returns (consistency_bullets, consistency_map_dict).
    """
    dims = dimensions_data.get("dimensions", []) if isinstance(dimensions_data, dict) else []
    consistency_bullets: List[str] = []
    consistency_map: Dict[str, str] = {}

    STATUS_MAP = {
        "strong": "CONSISTENT",
        "positive": "CONSISTENT",
        "mixed": "INCONSISTENT",
        "weak": "INCONSISTENT",
        "negative": "INCONSISTENT",
        "improving": "CONSISTENT",
        "deteriorating": "INCONSISTENT",
    }

    for dim in dims:
        name = dim.get("dimension", dim.get("dimension_name", dim.get("name", "")))
        assessment = str(dim.get("assessment", dim.get("status", ""))).lower()
        if not name:
            continue
        status = STATUS_MAP.get(assessment, "UNABLE_TO_VERIFY")
        consistency_map[name] = status
        if status == "CONSISTENT":
            evidence_count = len(dim.get("supporting_evidence", dim.get("evidence_items", [])))
            ec_str = f" ({evidence_count} evidence items)" if evidence_count else ""
            consistency_bullets.append(f"{name}{ec_str}: assessment={assessment}")

    return consistency_bullets[:3], consistency_map


def _enrich_uncertainty_items(
    raw_items: List[str],
    hard_commitments: List[Dict],
    mqs_data: Dict,
) -> str:
    """Enrich what_is_not_yet_proven with named specific commitments.

    Takes raw mq_summary.unresolved and adds named hard commitment IDs and specific risks.
    """
    parts = []

    # Add hard commitments with specific timeframes
    for hc in hard_commitments[:2]:
        norm = hc.get("normalized_commitment", hc.get("original_statement", ""))[:120]
        tf = hc.get("expected_timeframe", "")
        mc_id = hc.get("id", "")
        if norm:
            parts.append(f"Whether {mc_id} ({tf}): {norm} — reaches confirmed delivered status")

    # Add what_changed items from mq_summary as specific risk context
    what_changed = mqs_data.get("what_changed", []) if isinstance(mqs_data, dict) else []
    for item in what_changed[:1]:
        parts.append(f"Whether recent development ({item}) is addressed with quantified mitigation before it becomes visible")

    # Append raw unresolved if we have room
    for item in raw_items[:1]:
        if item and item not in " ".join(parts):
            parts.append(item)

    return ". ".join(parts) if parts else (raw_items[0] if raw_items else "")


def _enrich_monitoring_items(
    raw_items: List[str],
    hard_commitments: List[Dict],
    financial: Dict[str, Any],
    dimensions_data: Dict,
) -> List[str]:
    """Enrich what_to_monitor with specific actionable items."""
    items = []

    # Hard commitments with deadlines → specific monitors
    for hc in hard_commitments[:2]:
        mc_id = hc.get("id", "")
        norm = hc.get("normalized_commitment", "")[:80]
        tf = hc.get("expected_timeframe", "")
        if norm:
            items.append(f"{mc_id} ({tf}): {norm}")

    # Financial metric progression (specific, not generic)
    rev = financial.get("revenue")
    if rev and rev.get("fiscal_year"):
        items.append(f"Revenue and margin trajectory after {rev['fiscal_year']} — whether NPM sustains above confirmed level")

    # Risk dimensions from consistency_map (weak ones to monitor)
    dims = dimensions_data.get("dimensions", []) if isinstance(dimensions_data, dict) else []
    for dim in dims:
        assessment = str(dim.get("assessment", "")).lower()
        if assessment in ("weak", "mixed", "negative"):
            name = dim.get("dimension_name", dim.get("name", ""))
            if name:
                items.append(f"Dimension {name}: {assessment} assessment — monitor for improvement evidence in next disclosure")
                break

    # Fill remaining from raw items (only the more specific-looking ones)
    for raw in raw_items:
        if len(items) >= 4:
            break
        if raw and raw not in " ".join(items):
            items.append(raw)

    return items[:4]


def _build_dpfs_v2(
    progression_counts: Dict[str, int],
    total_items: int,
    commitment_counts: Dict[str, int],
    total_commitments: int,
    hard_commitment_count: int,
    financial: Dict[str, Any],
    evidence_confidence: str,
    npm: Optional[float],
) -> List[Dict[str, Any]]:
    """Build DPFs V2: adds hard commitment count and NPM to financial DPF."""
    delivered = progression_counts.get("delivered", 0)
    in_progress = progression_counts.get("in_progress", 0)
    announced = progression_counts.get("announced", 0)
    unable = sum(v for k, v in commitment_counts.items() if "unable" in k.lower() or "verify" in k.lower())

    progress_str = f"{delivered} delivered / {in_progress} in_progress / {announced} announced (of {total_items})"

    # V2 upgrade: include hard commitment count in commitment DPF
    if hard_commitment_count > 0:
        commit_value = (
            f"{hard_commitment_count} hard; {unable} Unable To Verify (of {total_commitments})"
        )
        commit_semantic = (
            f"{hard_commitment_count} hard commitments tracked; 0 confirmed delivered; "
            f"all {unable} commitments Unable To Verify"
        )
    else:
        commit_value = f"{total_commitments} total; {unable} unable to verify"
        commit_semantic = (
            "All tracked commitments Unable To Verify"
            if unable == total_commitments
            else f"{unable} of {total_commitments} commitments Unable To Verify"
        )

    dpfs: List[Dict[str, Any]] = [
        {
            "metric": "Delivery follow-through",
            "value": progress_str,
            "period": "multi-year",
            "semantic_meaning": (
                "No progression item confirmed delivered in available disclosures"
                if delivered == 0
                else f"{delivered} item(s) confirmed delivered; {announced + in_progress} remaining unconfirmed"
            ),
        },
        {
            "metric": "Progression items",
            "value": progress_str,
            "period": "multi-year",
            "semantic_meaning": (
                "No item confirmed delivered in public disclosures"
                if delivered == 0
                else f"{delivered} of {total_items} items confirmed delivered"
            ),
        },
        {
            "metric": "Management commitments",
            "value": commit_value,
            "period": "multi-year",
            "semantic_meaning": commit_semantic,
        },
    ]

    rev = financial.get("revenue")
    pat = financial.get("pat")
    if rev and rev.get("value") is not None:
        fy = rev.get("fiscal_year", "").upper()
        val = rev["value"]
        unit = rev.get("unit", "")
        val_str = f"₹{val:,.0f} cr" if "crore" in unit.lower() or "cr" in unit.lower() else f"{val} {unit}"
        pat_str = ""
        if pat and pat.get("value") is not None:
            pv = pat["value"]
            pat_str = f"; PAT ₹{pv:,.0f} cr" if "crore" in (pat.get("unit", "")).lower() else f"; PAT {pv}"
        # V2 upgrade: include NPM
        npm_str = f"; NPM {npm:.1f}%" if npm is not None else ""
        dpfs.append({
            "metric": f"Financial scale ({fy})",
            "value": f"Revenue {val_str}{pat_str}{npm_str}",
            "period": fy,
            "semantic_meaning": f"Confirmed financial outcomes{f'; NPM {npm:.1f}% establishes profitability baseline' if npm else ''}; causal attribution to management plans not established",
        })

    dpfs.append({
        "metric": "Evidence confidence",
        "value": evidence_confidence.upper() if evidence_confidence else "UNKNOWN",
        "period": "multi-year",
        "semantic_meaning": (
            "Delivery and commitment follow-up observations are supported across multiple source streams"
            if evidence_confidence.lower() in ("high", "medium")
            else "Evidence confidence not established"
        ),
    })
    return dpfs


def build_management_quality_fact_pack_v2(
    company: str,
    company_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build V2 fact pack. Superset of V1. No AI calls."""
    if company_root is None:
        company_root = Path("companies") / company / "company_memory"
    else:
        company_root = Path(company_root)

    # Build V1 first (reuse all existing logic)
    v1 = build_management_quality_fact_pack(company, company_root)

    # Additional V2 sources
    # 1. Management commitments (hard commitments)
    mc_path = company_root / "management_commitments" / "management_commitments.json"
    mc_data = _load(mc_path) or {}
    mc_items = mc_data.get("commitments", []) if isinstance(mc_data, dict) else []
    hard_commitment_count, hard_commitments = _count_hard_commitments(mc_items)

    # 2. Financial metrics (for NPM)
    ftp = _load(company_root / "financial_truth_pack.json") or {}
    financial = v1.get("financial_context", {})
    npm = _compute_npm(financial)

    # 3. Management quality evidence
    mq_evidence_path = company_root / "management_quality" / "management_quality_evidence.json"
    mq_evidence_data = _load(mq_evidence_path) or {}
    evidence_items = mq_evidence_data.get("evidence_items", []) if isinstance(mq_evidence_data, dict) else []
    evidence_observations = _extract_evidence_observations(evidence_items)
    management_statements = _extract_management_statements(evidence_items)

    # 4. Management quality dimensions
    mq_dims_path = company_root / "management_quality" / "management_quality_dimensions.json"
    mq_dims_data = _load(mq_dims_path) or {}
    consistency_bullets, consistency_map = _extract_consistency_observations(mq_dims_data)

    # 5. Enriched uncertainty and monitoring items
    mqs_path = company_root / "management_quality" / "management_quality_summary.json"
    mqs_data = _load(mqs_path) or {}
    raw_uncertainty = v1.get("uncertainty_items", [])
    raw_monitoring = v1.get("monitoring_items", [])

    uncertainty_items_enriched = _enrich_uncertainty_items(
        raw_uncertainty, hard_commitments, mqs_data
    )
    monitoring_items_enriched = _enrich_monitoring_items(
        raw_monitoring, hard_commitments, financial, mq_dims_data
    )

    # 6. Rebuild DPFs with V2 enhancements (hard commitment count, NPM)
    dpfs_v2 = _build_dpfs_v2(
        {k: v for k, v in v1["progression_counts"].items() if k != "total"},
        v1["progression_counts"]["total"],
        v1["commitment_counts"].get("by_status", {}),
        v1["commitment_counts"]["total"],
        hard_commitment_count,
        financial,
        v1.get("evidence_confidence", "UNKNOWN"),
        npm,
    )

    # Derive latest_fy from financial context (used for commitment materiality scoring)
    rev_fy = (financial.get("revenue") or {}).get("fiscal_year", "")
    latest_fy = 26  # default
    if rev_fy:
        fy_digits = re.search(r"(\d{2,4})", str(rev_fy))
        if fy_digits:
            raw = int(fy_digits.group(1))
            latest_fy = raw % 100 if raw > 100 else raw

    # Compute evidence period range from evidence items
    periods = [str(e.get("period", "")) for e in evidence_items if e.get("period")]
    fys = sorted({int(re.search(r"\d{2,4}", p).group()) % 100 for p in periods if re.search(r"\d{2,4}", p)})
    evidence_period_range = f"FY{fys[0]:02d}-FY{fys[-1]:02d}" if len(fys) >= 2 else (f"FY{fys[0]:02d}" if fys else "multi-year")

    return {
        **v1,
        "schema_version": FACT_PACK_SCHEMA_VERSION,
        # V2 additions
        "hard_commitment_count": hard_commitment_count,
        "hard_commitments": [
            {
                "id": hc.get("id"),
                "expected_timeframe": hc.get("expected_timeframe"),
                "normalized_commitment": hc.get("normalized_commitment", "")[:120],
            }
            for hc in hard_commitments
        ],
        "npm": npm,
        "evidence_observations": evidence_observations,
        "evidence_observations_raw": evidence_items,
        "evidence_period_range": evidence_period_range,
        "latest_fy": latest_fy,
        "management_statements": management_statements,
        "consistency_observations": consistency_bullets,
        "consistency_map": consistency_map,
        "uncertainty_items_enriched": uncertainty_items_enriched,
        "monitoring_items_enriched": monitoring_items_enriched,
        # Override DPFs with V2 version
        "dpfs": dpfs_v2,
    }
