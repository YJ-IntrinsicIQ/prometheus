from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional


CONTRACT_VERSION = "1.0"
ENGINE_TYPES = {"reported_segment", "geography", "product_category", "channel", "other_disclosed_dimension"}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _year_number(year: str) -> Optional[int]:
    match = re.fullmatch(r"fy(\d{2}|\d{4})", str(year or "").lower())
    if not match:
        return None
    number = int(match.group(1))
    return 2000 + number if number < 100 else number


def _is_economic_row(label: str) -> bool:
    lowered = str(label or "").strip().lower()
    if not lowered or len(lowered) > 80:
        return False
    blocked = (
        "year ended", "as at", "total", "non-current", "non current",
        "revenue by", "customer", "segment reporting", "profit", "earnings per share",
    )
    return not any(token in lowered for token in blocked)


def _value_for_year(row: Dict[str, Any], fiscal_year: str) -> Optional[Dict[str, Any]]:
    target = _year_number(fiscal_year)
    if target is None:
        return None
    for value in row.get("values", []):
        period = str(value.get("period") or "")
        if str(target) not in period:
            continue
        if value.get("value_type") != "monetary" or value.get("value_crore") is None:
            continue
        return value
    return None


# ── Trajectory helpers ────────────────────────────────────────────────────────

def _classify_scale_status(revenue_share: Optional[float]) -> str:
    """Classify engine scale by its latest revenue share."""
    if revenue_share is None:
        return "UNKNOWN"
    if revenue_share >= 0.30:
        return "MAJOR"
    if revenue_share >= 0.15:
        return "MATERIAL"
    if revenue_share >= 0.05:
        return "SMALL"
    return "MINOR"


def _classify_growth_momentum(growth_rates: List[float]) -> str:
    """Classify multi-period growth momentum deterministically from YoY growth rate series.

    Requires at least 3 data points. Looks at the last 3 consecutive rates to
    identify sustained directional movement.

    Priority order matters: RECOVERING and DETERIORATING check the full valid
    series; DECELERATING/ACCELERATING/STABLE check only last 3.

    ponytail: last-3-window heuristic; upgrade to linear-regression slope if
    longer series or noisy data becomes a problem.
    """
    valid = [r for r in growth_rates if r is not None]
    if len(valid) < 3:
        return "INSUFFICIENT_HISTORY"

    last3 = valid[-3:]
    a, b, c = last3[0], last3[1], last3[2]

    # Any two consecutive recent periods of absolute revenue decline
    if c < 0 and b < 0:
        return "DETERIORATING"

    # Was in decline in the earlier part, now sustained positive recovery
    # Require that the first half contained negative rates AND last 2 are positive
    mid = len(valid) // 2
    first_half_has_negative = any(r < 0 for r in valid[:mid])
    if first_half_has_negative and b > 0 and c > 0:
        return "RECOVERING"

    # Sustained monotone decline in growth rate (last 3 strictly decreasing)
    if c < b < a:
        return "DECELERATING"
    # Sustained monotone increase in growth rate (last 3 strictly increasing)
    if c > b > a:
        return "ACCELERATING"

    # Stable: all 3 within ±0.05 of each other
    if max(last3) - min(last3) <= 0.05:
        return "STABLE_GROWTH"

    return "VOLATILE"


def _classify_mix_trajectory(
    first_share: Optional[float], last_share: Optional[float], *, threshold: float = 0.02
) -> str:
    """Classify mix trajectory from first-to-last revenue share.

    threshold=0.02 means ±2pp change = STABLE_SHARE.
    """
    if first_share is None or last_share is None:
        return "INSUFFICIENT_HISTORY"
    delta = last_share - first_share
    if abs(delta) < threshold:
        return "STABLE_SHARE"
    if delta >= threshold:
        return "GAINING_SHARE"
    return "LOSING_SHARE"


def _classify_relative_performance(
    engine_cagr: Optional[float],
    company_cagr: Optional[float],
    peer_cagrs: List[float],
    *,
    threshold: float = 0.02,
) -> str:
    """Classify engine performance vs company average and peer engines."""
    if engine_cagr is None or company_cagr is None:
        return "UNKNOWN"
    vs_company = engine_cagr - company_cagr
    if not peer_cagrs:
        if vs_company > threshold:
            return "OUTPERFORMING"
        if vs_company < -threshold:
            return "UNDERPERFORMING"
        return "IN_LINE"
    median_peer = sorted(peer_cagrs)[len(peer_cagrs) // 2]
    vs_peers = engine_cagr - median_peer
    if vs_company > threshold and vs_peers > threshold:
        return "OUTPERFORMING"
    if vs_company < -threshold and vs_peers < -threshold:
        return "UNDERPERFORMING"
    if abs(vs_company) <= threshold:
        return "IN_LINE"
    return "MIXED"


def _detect_inflection(growth_rates: List[float]) -> Optional[str]:
    """Detect momentum-class change with multi-period evidence (≥ 6 data points).

    Requires ≥ 6 valid rates so each half has ≥ 3 for a meaningful classification.
    Returns None when there is insufficient evidence or no clear inflection.
    """
    valid = [r for r in growth_rates if r is not None]
    if len(valid) < 6:
        return None
    mid = len(valid) // 2
    first_class = _classify_growth_momentum(valid[:mid])
    second_class = _classify_growth_momentum(valid[mid:])
    if first_class == second_class:
        return None
    if first_class in ("INSUFFICIENT_HISTORY", "VOLATILE") or second_class in ("INSUFFICIENT_HISTORY", "VOLATILE"):
        return None
    return f"{first_class}_TO_{second_class}"


def _compute_cagr(start_rev: float, end_rev: float, periods: int) -> Optional[float]:
    if periods <= 0 or start_rev <= 0 or end_rev <= 0:
        return None
    return (end_rev / start_rev) ** (1 / periods) - 1


def _build_investor_interpretation(
    engine_name: str,
    scale_status: str,
    mix_trajectory: str,
    growth_momentum: str,
    relative_performance: str,
    inflection: Optional[str],
) -> Dict[str, Any]:
    """Generate engine-specific (non-boilerplate) investor interpretation.

    Each combination of scale × mix × momentum produces different text so that
    no two engines with different trajectories receive identical output.
    """
    # Scale description
    scale_map = {
        "MAJOR": "one of the company's largest revenue contributors",
        "MATERIAL": "a material revenue contributor",
        "SMALL": "a smaller revenue contributor",
        "MINOR": "a minor revenue contributor",
        "UNKNOWN": "a revenue contributor of unconfirmed scale",
    }
    scale_desc = scale_map.get(scale_status, "a revenue contributor")

    # Mix description
    mix_map = {
        "STABLE_SHARE": "its revenue share has remained broadly stable",
        "GAINING_SHARE": "it has been gaining share within the company's revenue mix",
        "LOSING_SHARE": "it has been losing share within the company's revenue mix",
        "VOLATILE_SHARE": "its revenue share has moved with no clear direction",
        "INSUFFICIENT_HISTORY": "insufficient history exists to assess mix movement",
    }
    mix_desc = mix_map.get(mix_trajectory, "its mix movement is unclear")

    # Momentum description
    momentum_map = {
        "ACCELERATING": "growth momentum has been accelerating",
        "DECELERATING": "growth momentum has been decelerating over recent periods",
        "STABLE_GROWTH": "growth has remained relatively stable",
        "VOLATILE": "growth has been volatile with no sustained directional trend",
        "RECOVERING": "growth is recovering after prior weakness",
        "DETERIORATING": "revenue has been contracting",
        "INSUFFICIENT_HISTORY": "insufficient history exists to assess growth momentum",
    }
    momentum_desc = momentum_map.get(growth_momentum, "growth trend is unclear")

    # Relative performance
    rel_map = {
        "OUTPERFORMING": "It is growing faster than the company overall and peer engines.",
        "UNDERPERFORMING": "It is growing slower than the company overall and peer engines.",
        "IN_LINE": "Its growth pace is broadly in line with the company overall.",
        "MIXED": "Its relative performance is mixed versus company and peer engines.",
        "UNKNOWN": "Relative performance versus company and peers cannot be assessed.",
    }
    rel_desc = rel_map.get(relative_performance, "")

    # Inflection note
    inflection_note = ""
    if inflection:
        from_class, _, to_class = inflection.partition("_TO_")
        inflection_note = (
            f" A multi-period momentum shift from {from_class.lower().replace('_', ' ')} "
            f"to {to_class.lower().replace('_', ' ')} is evident."
        )

    summary = (
        f"The {engine_name} engine is {scale_desc}. "
        f"While {mix_desc}, {momentum_desc}.{inflection_note} "
        f"{rel_desc} "
        f"Geography-level profitability and cash economics remain undisclosed."
    ).strip()

    what_to_watch = ["revenue growth rate trend"]
    if mix_trajectory in ("GAINING_SHARE", "LOSING_SHARE"):
        what_to_watch.append("revenue mix shift continuation")
    if growth_momentum == "DECELERATING":
        what_to_watch.append("whether deceleration stabilises or continues")
    if growth_momentum == "ACCELERATING":
        what_to_watch.append("sustainability of acceleration")
    what_to_watch.append("explicit profitability or capital disclosure")

    return {
        "summary": summary,
        "scale_status": scale_status,
        "growth_momentum": growth_momentum,
        "mix_trajectory": mix_trajectory,
        "relative_performance": relative_performance,
        "inflection": inflection,
        "what_matters": "Reported revenue contribution is observable; engine profitability and cash conversion are not disclosed.",
        "what_is_changing": f"momentum={growth_momentum}, mix={mix_trajectory}, scale={scale_status}",
        "what_to_watch": what_to_watch,
        "unknowns": ["engine profitability", "engine cash flow", "engine-specific capital intensity"],
    }


# ── Main builder ──────────────────────────────────────────────────────────────

def build_economic_engines(
    *, company: str, years: Iterable[str], yearly_payloads: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """Build disclosed economic engines without inventing segment economics.

    Identity is exact normalized disclosed label identity.  Renames therefore stay
    unresolved until an evidence-backed alias is supplied; fuzzy matching is never
    authority.  Only monetary rows from the governed segment-reporting table enter
    the model.
    """
    observations: List[Dict[str, Any]] = []
    by_engine: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for year in years:
        raw = yearly_payloads.get(year, {}).get("raw_financial_tables") or {}
        rows = (raw.get("tables") or {}).get("segment_reporting") or []
        selected: List[tuple[Dict[str, Any], Dict[str, Any]]] = []
        for row in rows:
            if row.get("basis") != "consolidated" or not _is_economic_row(row.get("line_item_raw", "")):
                continue
            value = _value_for_year(row, year)
            if value:
                selected.append((row, value))
        # One isolated row cannot establish the disclosed dimension or its mix;
        # retain that year as unavailable instead of presenting a false 100% share.
        unique_selected = {}
        for row, value in selected:
            unique_selected.setdefault(_slug(row.get("line_item_raw", "")), (row, value))
        selected = list(unique_selected.values())
        if len(selected) < 2:
            continue
        total = sum(float(value["value_crore"]) for _, value in selected)
        reported_revenue = (((yearly_payloads.get(year, {}).get("normalized_fundamentals") or {})
                             .get("profit_and_loss") or {}).get("revenue") or {}).get("value_crore")
        reconciliation_delta = None
        reconciliation_status = "NOT_AVAILABLE"
        if reported_revenue:
            reconciliation_delta = round(total - float(reported_revenue), 6)
            reconciliation_status = "RECONCILED" if abs(reconciliation_delta) / abs(float(reported_revenue)) <= 0.02 else "PARTIAL"
        # A same-shaped numeric table can still describe deductions, assets, or
        # another economic scope.  If disclosed components do not reconcile to
        # canonical consolidated revenue, they are not revenue-engine authority.
        if reported_revenue and reconciliation_status != "RECONCILED":
            continue
        for row, value in selected:
            name = str(row["line_item_raw"]).strip()
            engine_id = _slug(name)
            revenue = float(value["value_crore"])
            item = {
                "engine_id": engine_id,
                "engine_name": name,
                "engine_type": "geography",
                "source_dimension": "reported_revenue_by_geography",
                "reporting_period": year,
                "revenue_crore": revenue,
                "revenue_share": round(revenue / total, 6) if total else None,
                "revenue_reconciliation": {
                    "component_total_crore": round(total, 6),
                    "consolidated_revenue_crore": reported_revenue,
                    "delta_crore": reconciliation_delta,
                    "status": reconciliation_status,
                },
                "growth_rate": None,
                "profitability_status": "NOT_DISCLOSED",
                "profitability_metric": None,
                "growth_drivers": [],
                "margin_drivers": [],
                "capital_requirements": [],
                "cash_conversion_linkage": "CONSOLIDATED_ONLY",
                "strategic_role": "UNKNOWN",
                "competitive_evidence": [],
                "evidence_ids": [f"financial:{year}:{row.get('chunk_id')}:{engine_id}"],
                "source_year": year,
                "source_artifact": row.get("source_artifact"),
                "source_item_id": f"{row.get('chunk_id')}:{engine_id}",
                "evidence_references": {
                    "page": row.get("page"), "chunk_id": row.get("chunk_id"),
                    "raw_label": name, "raw_value": value.get("value_raw"),
                },
                "provenance": {
                    "source_artifact": row.get("source_artifact"), "page": row.get("page"),
                    "chunk_id": row.get("chunk_id"), "raw_label": name,
                    "raw_value": value.get("value_raw"), "unit": value.get("unit_hint"),
                    "basis": row.get("basis"), "period": value.get("period"),
                },
                "confidence": "HIGH",
                "unresolved_fields": ["profitability", "engine_cash_flow", "capital_requirements", "growth_driver"],
            }
            observations.append(item)
            by_engine[engine_id].append(item)

    # ── Build per-engine summaries ──────────────────────────────────────────
    engines_raw: List[Dict[str, Any]] = []
    for engine_id, history in sorted(by_engine.items()):
        history.sort(key=lambda item: _year_number(item["reporting_period"]) or 0)
        for previous, current in zip(history, history[1:]):
            if previous["revenue_crore"]:
                current["growth_rate"] = round(current["revenue_crore"] / previous["revenue_crore"] - 1, 6)
        engines_raw.append({"engine_id": engine_id, "history": history})

    # ── Company-level CAGR (for relative performance) ─────────────────────
    # Aggregate total revenue per year across all engines (already reconciled)
    rev_by_year: Dict[str, float] = defaultdict(float)
    for eng in engines_raw:
        for h in eng["history"]:
            rev_by_year[h["reporting_period"]] += h["revenue_crore"]
    sorted_years = sorted(rev_by_year, key=lambda y: _year_number(y) or 0)
    company_cagr: Optional[float] = None
    if len(sorted_years) >= 2:
        company_cagr = _compute_cagr(
            rev_by_year[sorted_years[0]], rev_by_year[sorted_years[-1]], len(sorted_years) - 1
        )

    # ── Per-engine CAGRs (for relative performance) ───────────────────────
    engine_cagrs: Dict[str, Optional[float]] = {}
    for eng in engines_raw:
        h = eng["history"]
        if len(h) >= 2:
            engine_cagrs[eng["engine_id"]] = _compute_cagr(
                h[0]["revenue_crore"], h[-1]["revenue_crore"], len(h) - 1
            )
        else:
            engine_cagrs[eng["engine_id"]] = None

    # ── Assemble final engine objects ─────────────────────────────────────
    engines: List[Dict[str, Any]] = []
    for eng in engines_raw:
        engine_id = eng["engine_id"]
        history = eng["history"]
        first, last = history[0], history[-1]

        growth_rates = [h.get("growth_rate") for h in history]
        mix_series = [h.get("revenue_share") for h in history]

        scale_status = _classify_scale_status(last.get("revenue_share"))
        growth_momentum = _classify_growth_momentum(growth_rates)
        mix_trajectory = _classify_mix_trajectory(
            first.get("revenue_share"), last.get("revenue_share")
        )
        this_cagr = engine_cagrs.get(engine_id)
        peer_cagrs = [v for k, v in engine_cagrs.items() if k != engine_id and v is not None]
        relative_performance = _classify_relative_performance(this_cagr, company_cagr, peer_cagrs)
        inflection = _detect_inflection(growth_rates)

        # Legacy field: keep for backwards-compat consumers that only check trajectory
        legacy_trajectory = growth_momentum  # now reflects growth, not just mix

        investor_interpretation = _build_investor_interpretation(
            engine_name=last["engine_name"],
            scale_status=scale_status,
            mix_trajectory=mix_trajectory,
            growth_momentum=growth_momentum,
            relative_performance=relative_performance,
            inflection=inflection,
        )

        engines.append({
            "engine_id": engine_id,
            "engine_name": last["engine_name"],
            "engine_type": last["engine_type"],
            "identity_status": "CANONICAL_EXACT_LABEL",
            "aliases": [],
            "history": history,
            # ── Trajectory fields ──────────────────────────────────────────
            "scale_status": scale_status,
            "growth_momentum": growth_momentum,
            "mix_trajectory": mix_trajectory,
            "relative_performance": relative_performance,
            "inflection": inflection,
            # Legacy field kept for backwards compat — now reflects growth_momentum
            "trajectory": legacy_trajectory,
            "investor_interpretation": investor_interpretation,
        })

    return {
        "contract_version": CONTRACT_VERSION,
        "company": company,
        "canonical_owner": "CIM_PCIM",
        "engines": engines,
        "observations": observations,
        "source_limitations": [
            "Segment profitability is not inferred from consolidated margins.",
            "Segment cash flow and capital intensity remain unknown unless explicitly disclosed.",
            "Exact-label identity is preserved; renamed dimensions require evidence-backed alias resolution.",
        ],
        "coverage_status": "SUPPORTED" if engines else "NOT_AVAILABLE",
    }
