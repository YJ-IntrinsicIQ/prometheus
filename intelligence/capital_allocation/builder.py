from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .classifier import (
    classify_allocation_type,
    extract_management_rationale,
    is_material_allocation,
    _parse_amount_crore,
    _CAPITAL_RETURN_TYPES,
)
from .resolver import (
    build_capital_return_interpretation,
    build_investor_interpretation,
    materiality_rank,
    resolve_evidence_level,
    resolve_financial_link_status,
    resolve_return_status,
)

SCHEMA_VERSION = "capital_allocation_gold.v1"

_GOLD_DIR = "gold"
_ARTIFACT_NAME = "capital_allocation_outcome_tracker.json"


# ── I/O helpers ────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _load_list(path: Path, key: str) -> List[Dict[str, Any]]:
    d = _load_json(path)
    result = d.get(key) or []
    if not isinstance(result, list):
        return []
    return result


def _gold_output_path(company_slug: str, companies_root: Path) -> Path:
    return companies_root / company_slug / "company_memory" / _GOLD_DIR / _ARTIFACT_NAME


# ── Source loading ─────────────────────────────────────────────────────────────

def _load_sources(company_slug: str, companies_root: Path) -> Dict[str, Any]:
    """Load all relevant source artifacts for the company."""
    mem = companies_root / company_slug / "company_memory"

    # Primary allocation outcomes
    outcomes_records = _load_list(
        mem / "capital_allocation_outcomes" / "capital_allocation_outcomes.json",
        "allocations",
    )

    # Capital allocation timeline (top-level — contains raw event data)
    timeline_raw = _load_list(mem / "capital_allocation_timeline.json", "timeline")

    # Financial capital allocation timeline
    fin_timeline_entries = _load_list(
        mem / "financials" / "capital_allocation_financial_timeline.json", "timeline"
    )

    # ROI ledger
    roi_ledger = _load_list(
        mem / "financials" / "investor_financial_modules" / "capital_allocation_roi_ledger.json",
        "entries",
    )

    # Owner earnings bridge
    oe_bridge = _load_list(
        mem / "financials" / "investor_financial_modules" / "owner_earnings_bridge.json",
        "bridges",
    )

    # Financial trends (metric_series and ratio_series)
    trends = _load_json(mem / "financials" / "financial_trends.json")
    metric_series = trends.get("metric_series") or {}
    ratio_series = trends.get("ratio_series") or {}

    # Management promise tracker (for cross-linking)
    promise_tracker = _load_json(mem / "gold" / "management_promise_tracker.json")

    # Capacity registry (for capacity-expansion enrichment)
    capacity_items = _load_list(mem / "capacity" / "capacity_registry.json", "capacity_items")

    return {
        "outcomes_records": outcomes_records,
        "timeline_raw": timeline_raw,
        "fin_timeline_entries": fin_timeline_entries,
        "roi_ledger": roi_ledger,
        "oe_bridge": oe_bridge,
        "capex_series": [
            e for e in (metric_series.get("capex") or []) if e.get("value") is not None
        ],
        "fcf_series": [
            e for e in (metric_series.get("fcf") or []) if e.get("value") is not None
        ],
        "revenue_series": [
            e for e in (metric_series.get("revenue") or []) if e.get("value") is not None
        ],
        "pat_series": [
            e for e in (metric_series.get("pat") or []) if e.get("value") is not None
        ],
        "roce_series": [
            e for e in (ratio_series.get("roce") or []) if e.get("value") is not None
        ],
        "roe_series": [
            e for e in (ratio_series.get("roe") or []) if e.get("value") is not None
        ],
        "promise_tracker": promise_tracker,
        "capacity_items": capacity_items,
    }


# ── Categories that represent genuine capital outflows ────────────────────────

# Only these categories are brought in as allocation candidates from the raw timeline.
# Inflows (debt raised, equity issuance), treasury management (HTM securities,
# deposits), and internal accounting (reserve transfers) are excluded.
_INCLUDE_CATEGORIES = {
    "acquisition", "subsidiary acquisition", "subsidiary acquisition/incorporation",
    "subsidiary incorporation/acquisition",
    "buyback", "buyback (tender offer)",
    "capex spending", "capital expenditure",
    "r&d spending", "research and development",
    "dividend",
    "debt repayment", "debt repayment / settlement",
    "investment in associate",
}

# These categories are explicitly inflows or non-outflows — always skip
_EXCLUDE_CATEGORIES = {
    "debt raised", "proceeds from borrowings", "proceeds from issue of shares",
    "equity issuance", "equity issuance (preference shares)",
    "equity (authorised share capital increase)",
    "equity issuance (employee stock-based compensation)",
    "reserve transfer",
    "lending / loan book change",
    "deposits with banks / short-term placements",
    "investment - htm securities", "investment - non-htm securities",
    "perpetual non-cumulative preference shares (additional tier 1)",
    "common equity (tier 1)",
    "asset disposals",
    "financing activities", "investing activities",
    "decrease in borrowings (net)",
}


# ── Raw event → allocation candidate ─────────────────────────────────────────

def _events_to_candidates(timeline_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert raw capital_allocation_timeline events into candidate allocation records.

    Groups events by canonical allocation type (not raw text), so all dividends
    become one DIVIDEND candidate, all buybacks one BUYBACK candidate, etc.
    Only genuine capital outflow categories are included.
    """
    from intelligence.capital_allocation.classifier import classify_allocation_type

    # Group by canonical allocation type
    grouped: Dict[str, Dict[str, Any]] = {}

    for year_entry in timeline_raw:
        year = year_entry.get("year") or ""
        for action in year_entry.get("capital_allocation_actions") or []:
            raw_category = (action.get("category") or "").lower().strip()

            # Skip excluded categories
            if raw_category in _EXCLUDE_CATEGORIES:
                continue

            # Skip if not in the include set (unknown categories are skipped)
            if raw_category and raw_category not in _INCLUDE_CATEGORIES:
                continue

            value = (action.get("value") or "").strip()
            # Build a minimal record to classify
            probe = {
                "allocation_category": raw_category,
                "category": action.get("category") or "",
                "value": value,
                "allocation_name": value,
                "inferred_business_purpose": value,
            }
            alloc_type = classify_allocation_type(probe)

            # Key by canonical type — one candidate per type
            key = alloc_type
            if key not in grouped:
                grouped[key] = {
                    "source_item_id": action.get("source_item_id") or f"{year}_{key}",
                    "allocation_category": raw_category,
                    "allocation_name": value,
                    "value": value,
                    "category": action.get("category") or "",
                    "amount": None,  # do NOT parse string amounts from timeline
                    "deployment_periods": [],
                    "evidence_references": [],
                    "inferred_business_purpose": value,
                    "operating_outcome": "",
                    "financial_outcome": "",
                    "balance_sheet_outcome": "",
                    "causal_confidence": "low",
                    "execution_status": "deployed",
                    "investor_implication": "",
                }
            else:
                # Keep the most descriptive name (longest)
                if len(value) > len(grouped[key]["allocation_name"]):
                    grouped[key]["allocation_name"] = value
                    grouped[key]["value"] = value

            if year not in grouped[key]["deployment_periods"]:
                grouped[key]["deployment_periods"].append(year)
            ev_ref = action.get("evidence_references")
            if ev_ref and isinstance(ev_ref, dict):
                grouped[key]["evidence_references"].append(ev_ref)

    return list(grouped.values())


# ── Deduplication: merge outcomes_records with timeline candidates ─────────────

def _merge_sources(
    outcomes_records: List[Dict[str, Any]],
    timeline_candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Prefer the richer outcomes_records when they exist; supplement with
    timeline_candidates for categories not in outcomes.
    """
    # Index outcomes by normalized type
    outcomes_types = {
        classify_allocation_type(r) for r in outcomes_records
    }

    # Add timeline candidates whose type is NOT already covered by outcomes
    merged = list(outcomes_records)
    for candidate in timeline_candidates:
        alloc_type = classify_allocation_type(candidate)
        if alloc_type not in outcomes_types:
            merged.append(candidate)

    return merged


# ── Period helpers ────────────────────────────────────────────────────────────

def _deployment_periods(record: Dict[str, Any]) -> List[str]:
    periods = record.get("deployment_periods") or []
    if not periods and record.get("first_observed_period"):
        periods = [record["first_observed_period"]]
    return sorted(set(p for p in periods if p))


def _source_period(record: Dict[str, Any]) -> str:
    periods = _deployment_periods(record)
    return periods[0] if periods else ""


def _latest_period(record: Dict[str, Any]) -> str:
    periods = _deployment_periods(record)
    return periods[-1] if periods else ""


# ── Promise tracker cross-links ────────────────────────────────────────────────

def _find_promise_links(
    record: Dict[str, Any],
    alloc_type: str,
    promise_tracker: Dict[str, Any],
) -> List[str]:
    """Return promise IDs from the promise tracker that relate to this allocation."""
    promises = promise_tracker.get("material_promises") or []
    name_lower = (
        record.get("allocation_name") or record.get("value") or ""
    ).lower()

    # Type matching
    type_to_promise_types = {
        "ORGANIC_CAPEX": {"CAPITAL_ALLOCATION", "CAPACITY"},
        "CAPACITY_EXPANSION": {"CAPACITY", "CAPITAL_ALLOCATION"},
        "ACQUISITION": {"CAPITAL_ALLOCATION"},
        "DIGITAL_OR_TECH_INVESTMENT": {"DIGITAL_OR_TECH", "CAPITAL_ALLOCATION"},
        "R_AND_D": {"PRODUCT_LAUNCH", "CAPITAL_ALLOCATION"},
        "DIVIDEND": {"CAPITAL_ALLOCATION"},
        "BUYBACK": {"CAPITAL_ALLOCATION"},
    }
    matching_promise_types = type_to_promise_types.get(alloc_type, set())

    linked = []
    for p in promises:
        if p.get("promise_type") in matching_promise_types:
            # Check for name overlap
            p_theme = (p.get("theme") or "").lower()
            shared_words = set(name_lower.split()) & set(p_theme.split()) - {
                "the", "a", "an", "of", "in", "to", "and", "or", "for", "is", "at",
                "on", "as", "was", "by", "be", "it", "are", "have", "had", "has",
                "from", "with", "this", "that", "these", "those", "we", "our",
            }
            if len(shared_words) >= 1 or (alloc_type in ("ORGANIC_CAPEX", "DIVIDEND") and matching_promise_types):
                pid = p.get("promise_id")
                if pid and pid not in linked:
                    linked.append(pid)

    # Cap at 3 links to avoid spurious connections
    return linked[:3]


# ── Capacity enrichment ────────────────────────────────────────────────────────

def _enrich_with_capacity(
    record: Dict[str, Any],
    alloc_type: str,
    capacity_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Supplement operating_outcome with capacity item data where relevant."""
    if alloc_type not in ("CAPACITY_EXPANSION", "ORGANIC_CAPEX"):
        return {}

    linked_ids = []
    cap_summaries = []
    for cap in capacity_items:
        exec_s = (cap.get("capacity_assessment") or {}).get("execution_status") or ""
        economic = (cap.get("capacity_assessment") or {}).get("economic_impact_status") or ""
        util = (cap.get("capacity_assessment") or {}).get("utilization_status") or ""
        cap_id = cap.get("capacity_id") or ""

        # Only include material capacity items
        sem = (cap.get("semantic_quality") or {})
        if sem.get("investor_relevance") == "core" or sem.get("materiality") == "high":
            linked_ids.append(cap_id)
            cap_summaries.append({
                "capacity_id": cap_id,
                "name": cap.get("capacity_name") or "",
                "execution_status": exec_s,
                "utilization_status": util,
                "economic_impact_status": economic,
            })

    return {
        "linked_capacity_ids": linked_ids[:5],
        "capacity_summaries": cap_summaries[:5],
    }


# ── Financial data helpers ─────────────────────────────────────────────────────

def _build_financial_summary(sources: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact financial summary for the company from available series."""
    capex = sources.get("capex_series") or []
    fcf = sources.get("fcf_series") or []
    revenue = sources.get("revenue_series") or []
    pat = sources.get("pat_series") or []
    roce = sources.get("roce_series") or []

    def _sum_series(series: List[Dict]) -> Optional[float]:
        vals = [abs(e["value"]) for e in series if e.get("value") is not None]
        return sum(vals) if vals else None

    def _latest(series: List[Dict]) -> Optional[Dict]:
        if not series:
            return None
        return max(series, key=lambda e: e.get("year") or "")

    total_capex = _sum_series(capex)
    avg_fcf = None
    fcf_vals = [e["value"] for e in fcf if e.get("value") is not None]
    if fcf_vals:
        avg_fcf = sum(fcf_vals) / len(fcf_vals)

    rev_latest = _latest(revenue)
    rev_first = revenue[0] if revenue else None
    revenue_growth_pct = None
    if rev_latest and rev_first and rev_first.get("value") and rev_latest.get("value"):
        raw_growth = (rev_latest["value"] - rev_first["value"]) / rev_first["value"] * 100
        # Cap at 1000% to avoid misleading numbers from structural breaks (e.g. SFB conversion)
        if raw_growth < 1000:
            revenue_growth_pct = round(raw_growth, 1)

    return {
        "total_capex_crore": total_capex,
        "avg_fcf_crore": round(avg_fcf, 2) if avg_fcf is not None else None,
        "fcf_consistently_positive": all(v > 0 for v in fcf_vals) if fcf_vals else None,
        "revenue_growth_pct": revenue_growth_pct,
        "years_of_data": sorted({e["year"] for series in [capex, fcf, revenue, pat] for e in series}),
        "roce_available": len(roce) > 0,
        "roce_values": [{"year": e["year"], "value": e["value"]} for e in roce],
        "capex_values": [{"year": e["year"], "value": e["value"]} for e in capex],
        "fcf_values": [{"year": e["year"], "value": e["value"]} for e in fcf],
        "fcf_series": fcf_vals,
        "cfo_series": [],  # populated below if available
    }


# ── Core allocation record builder ────────────────────────────────────────────

def _build_allocation_record(
    raw: Dict[str, Any],
    idx: int,
    sources: Dict[str, Any],
    financial_summary: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Build one Gold allocation record from a raw source record."""
    alloc_type = classify_allocation_type(raw)
    if not is_material_allocation(raw, alloc_type):
        return None

    allocation_id = f"CA-{idx:04d}-{alloc_type.lower()}"
    rationale = extract_management_rationale(raw)
    amount_cr = _parse_amount_crore(raw)
    periods = _deployment_periods(raw)

    evidence_level = resolve_evidence_level(raw)
    return_status = resolve_return_status(raw, alloc_type, evidence_level)
    fin_link = resolve_financial_link_status(raw, return_status)

    # Build investor interpretation
    if alloc_type in _CAPITAL_RETURN_TYPES or alloc_type == "BUYBACK":
        interpretation = build_capital_return_interpretation(raw, alloc_type, financial_summary)
    else:
        interpretation = build_investor_interpretation(raw, alloc_type, evidence_level, return_status)

    # Promise cross-links
    promise_tracker = sources.get("promise_tracker") or {}
    promise_links = _find_promise_links(raw, alloc_type, promise_tracker)

    # Capacity enrichment
    capacity_enrich = _enrich_with_capacity(raw, alloc_type, sources.get("capacity_items") or [])

    # Evidence IDs from raw records
    evidence_ids: List[str] = []
    for ref in (raw.get("evidence_references") or []):
        if isinstance(ref, dict):
            ev_id = ref.get("evidence_id") or ref.get("source_item_id") or ""
            if ev_id and ev_id not in evidence_ids:
                evidence_ids.append(ev_id)
        elif isinstance(ref, str) and ref:
            evidence_ids.append(ref)

    # Linked capacity / project IDs from outcomes_records
    linked_capacity_ids = (
        capacity_enrich.get("linked_capacity_ids")
        or raw.get("linked_capacity_ids") or []
    )
    linked_project_ids = raw.get("linked_project_ids") or []

    record: Dict[str, Any] = {
        "allocation_id": allocation_id,
        "source_item_id": raw.get("allocation_id") or raw.get("source_item_id") or "",
        "theme": (raw.get("allocation_name") or raw.get("value") or "").strip()[:200],
        "allocation_type": alloc_type,
        "source_period": _source_period(raw),
        "latest_period": _latest_period(raw),
        "deployment_periods": periods,
        "capital_amount_crore": round(amount_cr, 2) if amount_cr is not None else None,
        "currency": "INR",
        "management_rationale": rationale,
        "evidence_level": evidence_level,
        "execution_status": raw.get("execution_status") or raw.get("deployment_status") or "",
        "operating_outcome": (raw.get("operating_outcome") or raw.get("operating_evidence") or "").strip()[:500],
        "financial_outcome": (raw.get("financial_outcome") or raw.get("financial_evidence") or "").strip()[:500],
        "return_status": return_status,
        "financial_link_status": fin_link,
        "evidence_ids": evidence_ids,
        "linked_capacity_ids": linked_capacity_ids,
        "linked_project_ids": linked_project_ids,
        "linked_management_promise_ids": promise_links,
        "investor_interpretation": interpretation,
    }

    # Optional capacity summaries
    if capacity_enrich.get("capacity_summaries"):
        record["capacity_summaries"] = capacity_enrich["capacity_summaries"]

    return record


# ── Allocation patterns ────────────────────────────────────────────────────────

def _build_allocation_patterns(
    allocations: List[Dict[str, Any]],
    financial_summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Identify patterns only where multiple observations support them."""
    if len(allocations) < 2:
        return []

    type_counts = Counter(a["allocation_type"] for a in allocations)
    return_counts = Counter(a["return_status"] for a in allocations)
    evidence_counts = Counter(a["evidence_level"] for a in allocations)
    total = len(allocations)
    patterns = []

    # Pattern 1: Sustained reinvestment without return evidence
    unproven_reinvestment = [
        a for a in allocations
        if a["return_status"] == "UNPROVEN"
        and a["allocation_type"] not in {"DIVIDEND", "BUYBACK", "DEBT_REPAYMENT"}
    ]
    if len(unproven_reinvestment) >= 2:
        types = Counter(a["allocation_type"] for a in unproven_reinvestment)
        top_types = ", ".join(f"{k} ({v})" for k, v in types.most_common(3))
        patterns.append({
            "pattern_id": "sustained_reinvestment_without_return_evidence",
            "description": (
                f"Management has deployed capital into {len(unproven_reinvestment)} tracked "
                f"reinvestment categories ({top_types}) but return evidence has not been established for any of them. "
                "Execution may be visible, but economic justification remains incomplete."
            ),
            "evidence_count": len(unproven_reinvestment),
            "investor_relevance": "Ask management to quantify what returns on deployed capital look like.",
        })

    # Pattern 2: Positive return signals across multiple allocations
    positive_returns = [
        a for a in allocations
        if a["return_status"] in ("PROVEN_POSITIVE", "EARLY_POSITIVE_SIGNAL")
    ]
    if len(positive_returns) >= 2:
        patterns.append({
            "pattern_id": "multiple_positive_return_signals",
            "description": (
                f"{len(positive_returns)} of {total} tracked allocations show positive return signals. "
                "Management's track record on execution and economic translation appears constructive, "
                "though individual causal links may vary in strength."
            ),
            "evidence_count": len(positive_returns),
            "investor_relevance": "Verify the causal chain for each positive signal before extrapolating.",
        })

    # Pattern 3: Capital return alongside reinvestment — allocation balance
    return_allocations = [a for a in allocations if a["allocation_type"] in {"DIVIDEND", "BUYBACK"}]
    reinvestment_allocations = [
        a for a in allocations
        if a["allocation_type"] not in {"DIVIDEND", "BUYBACK", "DEBT_REPAYMENT"}
    ]
    if return_allocations and reinvestment_allocations:
        total_return_cr = sum(
            a.get("capital_amount_crore") or 0 for a in return_allocations
        )
        total_reinvest_cr = sum(
            a.get("capital_amount_crore") or 0 for a in reinvestment_allocations
        )
        if total_return_cr > 0 and total_reinvest_cr > 0:
            ratio = round(total_reinvest_cr / max(total_return_cr, 1), 1)
            patterns.append({
                "pattern_id": "dual_allocation_reinvestment_and_return",
                "description": (
                    f"Management is simultaneously reinvesting (₹{total_reinvest_cr:,.0f} Cr tracked) "
                    f"and returning capital (₹{total_return_cr:,.0f} Cr tracked). "
                    f"Reinvestment-to-distribution ratio is approximately {ratio}:1. "
                    "Whether reinvestment opportunities justify the balance is not yet fully assessable."
                ),
                "evidence_count": len(return_allocations) + len(reinvestment_allocations),
                "investor_relevance": "Capital allocation balance shapes long-run compounding potential.",
            })

    # Pattern 4: Destructive or weak outcomes
    adverse_outcomes = [
        a for a in allocations
        if a["return_status"] in ("DESTRUCTIVE", "WEAK")
    ]
    if len(adverse_outcomes) >= 1:
        patterns.append({
            "pattern_id": "adverse_capital_outcome_observed",
            "description": (
                f"{len(adverse_outcomes)} allocation(s) show adverse return evidence — "
                "impairment, margin erosion, or loss. "
                "This warrants scrutiny of management's capital decision process."
            ),
            "evidence_count": len(adverse_outcomes),
            "investor_relevance": "Adverse outcomes reduce confidence in future capital decisions.",
        })

    # Pattern 5: High capex without ROCE visibility
    capex_allocations = [
        a for a in allocations
        if a["allocation_type"] in ("ORGANIC_CAPEX", "CAPACITY_EXPANSION")
    ]
    total_capex = financial_summary.get("total_capex_crore")
    if capex_allocations and total_capex and total_capex > 100 and not financial_summary.get("roce_available"):
        patterns.append({
            "pattern_id": "capex_without_roce_visibility",
            "description": (
                f"Cumulative capex of ₹{total_capex:,.0f} Cr has been deployed, "
                "but ROCE/ROIC metrics are not available in the current data. "
                "Return on the asset base cannot be assessed with precision."
            ),
            "evidence_count": len(capex_allocations),
            "investor_relevance": "ROCE/ROIC visibility is necessary to assess whether asset investment is creating value.",
        })

    return patterns


# ── Owner-capital interpretation ───────────────────────────────────────────────

def _build_owner_capital_summary(
    allocations: List[Dict[str, Any]],
    financial_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Buffett-style: what happened to retained capital?
    Distinguishes deployment, execution, operating outcome, financial consequence.
    """
    reinvestment = [
        a for a in allocations
        if a["allocation_type"] not in {"DIVIDEND", "BUYBACK", "DEBT_REPAYMENT"}
    ]
    capital_returns = [
        a for a in allocations
        if a["allocation_type"] in {"DIVIDEND", "BUYBACK"}
    ]

    total_tracked = len(allocations)
    proven_positive = sum(1 for a in allocations if a["return_status"] == "PROVEN_POSITIVE")
    early_positive = sum(1 for a in allocations if a["return_status"] == "EARLY_POSITIVE_SIGNAL")
    unproven = sum(1 for a in allocations if a["return_status"] == "UNPROVEN")
    adverse = sum(1 for a in allocations if a["return_status"] in ("DESTRUCTIVE", "WEAK"))
    not_applicable = sum(1 for a in allocations if a["return_status"] == "NOT_APPLICABLE")

    total_capex = financial_summary.get("total_capex_crore")
    avg_fcf = financial_summary.get("avg_fcf_crore")
    rev_growth = financial_summary.get("revenue_growth_pct")
    fcf_positive = financial_summary.get("fcf_consistently_positive")

    # Build a narrative paragraph
    parts = []
    if total_capex:
        parts.append(f"Total tracked capex over the available period: approximately ₹{total_capex:,.0f} Cr.")
    if avg_fcf:
        sign = "positive" if avg_fcf > 0 else "negative"
        parts.append(f"Average free cash flow: ₹{avg_fcf:,.0f} Cr ({sign}).")
    if rev_growth is not None:
        parts.append(f"Revenue grew approximately {rev_growth}% over the covered period.")
    if not financial_summary.get("roce_available"):
        parts.append("ROCE/ROIC is not computable from available data — maintenance vs growth capex split is not disclosed.")

    if proven_positive:
        parts.append(f"{proven_positive} allocation(s) show proven positive returns.")
    if early_positive:
        parts.append(f"{early_positive} show early positive signals — execution visible, full financial proof pending.")
    if unproven:
        parts.append(f"{unproven} allocation(s) remain unproven — capital deployed but economic consequence not established.")
    if adverse:
        parts.append(f"{adverse} allocation(s) show adverse outcomes.")
    if capital_returns:
        parts.append(
            f"Management also returned capital via dividends or buybacks across {len(capital_returns)} tracked decision(s)."
        )

    return {
        "narrative": " ".join(parts),
        "total_tracked_allocations": total_tracked,
        "reinvestment_count": len(reinvestment),
        "capital_return_count": len(capital_returns),
        "return_status_distribution": {
            "proven_positive": proven_positive,
            "early_positive_signal": early_positive,
            "unproven": unproven,
            "mixed": sum(1 for a in allocations if a["return_status"] == "MIXED"),
            "weak": sum(1 for a in allocations if a["return_status"] == "WEAK"),
            "destructive": adverse,
            "not_applicable": not_applicable,
        },
        "maintenance_growth_split_disclosed": False,  # always false given data; let source override
        "roce_visibility": financial_summary.get("roce_available", False),
    }


# ── Critical follow-up ────────────────────────────────────────────────────────

def _build_critical_followup(allocations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    followup = []
    for a in allocations:
        if a["return_status"] == "UNPROVEN" and a["allocation_type"] not in {"DIVIDEND", "BUYBACK"}:
            followup.append({
                "allocation_id": a["allocation_id"],
                "question": "What measurable return has this capital generated — revenue, margin, ROCE, or FCF?",
                "type": "return_evidence_needed",
                "theme": a["theme"][:100],
            })
        elif a["return_status"] == "EARLY_POSITIVE_SIGNAL":
            followup.append({
                "allocation_id": a["allocation_id"],
                "question": "Has the early positive signal converted into a demonstrable financial return?",
                "type": "return_confirmation_needed",
                "theme": a["theme"][:100],
            })
        elif a["return_status"] in ("DESTRUCTIVE", "WEAK"):
            followup.append({
                "allocation_id": a["allocation_id"],
                "question": "What is management's explanation for the adverse outcome, and has the allocation been written down or exited?",
                "type": "adverse_outcome_investigation",
                "theme": a["theme"][:100],
            })
    return followup[:10]


# ── Main builder ──────────────────────────────────────────────────────────────

def build_capital_allocation_outcome_tracker(
    company_slug: str,
    *,
    companies_root: Path | str = Path("companies"),
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    companies_root = Path(companies_root)
    generated_at = (
        generated_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )

    sources = _load_sources(company_slug, companies_root)

    # Merge source records
    timeline_candidates = _events_to_candidates(sources.get("timeline_raw") or [])
    raw_records = _merge_sources(
        sources.get("outcomes_records") or [],
        timeline_candidates,
    )

    # Build financial summary
    financial_summary = _build_financial_summary(sources)

    # Build allocation records
    allocations: List[Dict[str, Any]] = []
    excluded_count = 0
    for idx, raw in enumerate(raw_records, start=1):
        record = _build_allocation_record(raw, idx, sources, financial_summary)
        if record is None:
            excluded_count += 1
        else:
            allocations.append(record)

    # Sort by materiality rank
    allocations.sort(key=materiality_rank, reverse=True)

    # Partition into outcome buckets
    proven_outcomes = [
        a for a in allocations
        if a["return_status"] in ("PROVEN_POSITIVE", "EARLY_POSITIVE_SIGNAL")
        and a["allocation_type"] not in {"DIVIDEND", "BUYBACK", "DEBT_REPAYMENT"}
    ]
    unproven_allocations = [
        a for a in allocations
        if a["return_status"] == "UNPROVEN"
    ]
    weak_or_destructive = [
        a for a in allocations
        if a["return_status"] in ("DESTRUCTIVE", "WEAK")
    ]
    not_applicable_allocations = [
        a for a in allocations
        if a["return_status"] in ("NOT_APPLICABLE", "MIXED")
    ]

    # Patterns
    patterns = _build_allocation_patterns(allocations, financial_summary)

    # Owner capital summary
    owner_summary = _build_owner_capital_summary(allocations, financial_summary)

    # Critical follow-up
    critical_followup = _build_critical_followup(allocations)

    # Summary
    type_counts = Counter(a["allocation_type"] for a in allocations)
    return_counts = Counter(a["return_status"] for a in allocations)
    evidence_counts = Counter(a["evidence_level"] for a in allocations)

    summary = {
        "company_slug": company_slug,
        "tracked_allocations": len(allocations),
        "excluded_immaterial": excluded_count,
        "allocation_type_breakdown": dict(type_counts),
        "return_status_breakdown": dict(return_counts),
        "evidence_level_breakdown": dict(evidence_counts),
        "patterns_count": len(patterns),
        "financial_summary": financial_summary,
        "causal_attribution_note": (
            "A financial metric observed after an allocation does not prove the allocation caused it. "
            "financial_link_status distinguishes observation from attribution."
        ),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "company_slug": company_slug,
        "generated_at": generated_at,
        "summary": summary,
        "material_allocations": allocations,
        "proven_outcomes": proven_outcomes,
        "unproven_allocations": unproven_allocations,
        "weak_or_destructive_allocations": weak_or_destructive,
        "not_applicable_allocations": not_applicable_allocations,
        "allocation_patterns": patterns,
        "owner_capital_summary": owner_summary,
        "critical_follow_up": critical_followup,
    }


def write_capital_allocation_outcome_tracker(
    company_slug: str,
    *,
    companies_root: Path | str = Path("companies"),
    generated_at: Optional[str] = None,
) -> Path:
    companies_root = Path(companies_root)
    payload = build_capital_allocation_outcome_tracker(
        company_slug, companies_root=companies_root, generated_at=generated_at
    )
    output_path = _gold_output_path(company_slug, companies_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path
