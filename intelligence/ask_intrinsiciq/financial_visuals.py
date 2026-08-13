from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .sanitizer import sanitize_public_payload


VISUAL_IDS = [
    "revenue_trend",
    "pat_trend",
    "cfo_vs_pat",
    "owner_earnings_bridge",
    "working_capital_days",
    "cash_conversion_cycle",
    "per_share_economics",
    "capital_allocation_summary",
]


def build_financial_visual_summaries(
    source_bundle: Dict[str, Any],
    *,
    company_slug: str,
    generated_at: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    visuals: List[Dict[str, Any]] = []
    diagnostics = {"candidate_ids": list(VISUAL_IDS), "generated_ids": [], "skipped_ids": []}
    for builder in (
        build_revenue_trend,
        build_pat_trend,
        build_cfo_vs_pat,
        build_owner_earnings_bridge,
        build_working_capital_days,
        build_cash_conversion_cycle,
        build_per_share_economics,
        build_capital_allocation_summary,
    ):
        visual = builder(source_bundle, generated_at=generated_at)
        if visual is None:
            diagnostics["skipped_ids"].append(builder.__name__.replace("build_", ""))
            continue
        visuals.append(sanitize_public_payload(visual))
        diagnostics["generated_ids"].append(str(visual.get("id") or ""))
    payload = sanitize_public_payload(
        {
            "schema_version": "ask_intrinsiciq_financial_visual_summaries.v1",
            "company_slug": company_slug,
            "visuals": visuals,
            "coverage_summary": {
                "available": sum(1 for visual in visuals if str(visual.get("evidence_status") or "") in {"direct", "derived"}),
                "partial": sum(1 for visual in visuals if str(visual.get("evidence_status") or "") == "partial"),
                "unavailable": max(0, len(VISUAL_IDS) - len(visuals)),
            },
            "generated_at": generated_at,
        }
    )
    return payload, diagnostics


def build_revenue_trend(source_bundle: Dict[str, Any], *, generated_at: str) -> Optional[Dict[str, Any]]:
    points = _metric_points_from_truth(source_bundle, "revenue", status="reported")
    if len(points) < 2:
        return None
    return _visual(
        visual_id="revenue_trend",
        title="Revenue trend",
        subtitle="Revenue across reported periods with usable evidence.",
        visual_type="line",
        unit="INR crore",
        series=[_series("Revenue", points)],
        interpretation="Revenue direction is visible, but it should be read alongside cash conversion rather than on its own.",
        precision_note=_trend_precision_note(points, None),
        evidence_status="direct",
        recommended_display="compact",
        generated_at=generated_at,
    )


def build_pat_trend(source_bundle: Dict[str, Any], *, generated_at: str) -> Optional[Dict[str, Any]]:
    points = _bridge_metric_points(source_bundle, "reported_pat", status="reported")
    if len(points) < 2:
        return None
    return _visual(
        visual_id="pat_trend",
        title="Profit after tax trend",
        subtitle="Reported profit across periods with usable evidence.",
        visual_type="line",
        unit="INR crore",
        series=[_series("Profit after tax", points)],
        interpretation="Profit movement is visible, but it becomes more useful when paired with cash and working-capital evidence.",
        precision_note=_trend_precision_note(points, None),
        evidence_status="direct",
        recommended_display="compact",
        generated_at=generated_at,
    )


def build_cfo_vs_pat(source_bundle: Dict[str, Any], *, generated_at: str) -> Optional[Dict[str, Any]]:
    pat_points = _bridge_metric_points(source_bundle, "reported_pat", status="reported")
    cfo_points = _bridge_metric_points(source_bundle, "cfo", status="reported")
    shared_periods = [point["period"] for point in pat_points if any(other["period"] == point["period"] for other in cfo_points)]
    pat_points = [point for point in pat_points if point["period"] in shared_periods]
    cfo_points = [point for point in cfo_points if point["period"] in shared_periods]
    if not pat_points or not cfo_points:
        return None
    interpretation = "Cash generation can be compared directly with reported profit for the same periods."
    if len(shared_periods) == 1:
        interpretation = "This is a one-period comparison, so it shows current conversion rather than a durable trend."
    return _visual(
        visual_id="cfo_vs_pat",
        title="Cash flow versus profit",
        subtitle="Reported operating cash flow and profit for matching periods.",
        visual_type="comparison",
        unit="INR crore",
        series=[_series("Operating cash flow", cfo_points), _series("Profit after tax", pat_points)],
        interpretation=interpretation,
        precision_note=_first_nonempty(
            _first_string_list(_source_payload(source_bundle, "owner_earnings_bridge").get("warnings")),
            "Only matching reported periods are shown.",
        ),
        evidence_status="direct",
        recommended_display="compact",
        generated_at=generated_at,
    )


def build_owner_earnings_bridge(source_bundle: Dict[str, Any], *, generated_at: str) -> Optional[Dict[str, Any]]:
    record = _latest_year_record(_source_payload(source_bundle, "owner_earnings_bridge"), "bridges")
    cfo = _get_number(record, "cfo")
    capex = _get_number(record, "total_identified_capex")
    owner = _get_number(record, "owner_earnings_estimate")
    year = _year_label(record)
    if year is None or cfo is None or owner is None:
        return None
    points = [
        _point(year, cfo, "reported", unit="INR crore", semantic_label="Operating cash flow"),
        _point(
            year,
            abs(capex) if capex is not None else None,
            "derived" if capex is not None else "missing",
            unit="INR crore",
            semantic_label="Identified capex",
        ),
        _point(year, owner, "derived", unit="INR crore", semantic_label="Owner-oriented cash estimate"),
    ]
    if points[1]["value"] is None:
        points = [points[0], points[2]]
    return _visual(
        visual_id="owner_earnings_bridge",
        title="Owner-oriented cash bridge",
        subtitle="Current operating cash flow, identified capex, and owner-oriented cash estimate.",
        visual_type="bridge",
        unit="INR crore",
        series=[
            {
                "label": "Current bridge",
                "points": points,
            }
        ],
        interpretation="Current owner-oriented cash is positive, but the estimate remains precision-limited because capex detail is incomplete.",
        precision_note=_first_nonempty(
            _first_string_list(_get_list(record, "owner_earnings_warnings")),
            _first_string_list(_source_payload(source_bundle, "financial_truth_pack").get("precision_limits")),
        ),
        evidence_status="derived",
        recommended_display="expanded",
        generated_at=generated_at,
    )


def build_working_capital_days(source_bundle: Dict[str, Any], *, generated_at: str) -> Optional[Dict[str, Any]]:
    receivable_points = _working_capital_points(source_bundle, "receivable_days")
    inventory_points = _working_capital_points(source_bundle, "inventory_days")
    payable_points = _working_capital_points(source_bundle, "payable_days")
    if not receivable_points and not inventory_points and not payable_points:
        return None
    return _visual(
        visual_id="working_capital_days",
        title="Working-capital days",
        subtitle="Receivable, inventory, and payable days for periods with usable evidence.",
        visual_type="ratio",
        unit="days",
        series=[
            _series("Receivable days", receivable_points),
            _series("Inventory days", inventory_points),
            _series("Payable days", payable_points),
        ],
        interpretation="Receivables and inventory appear to keep cash tied up for long periods relative to payable support.",
        precision_note=_trend_precision_note(receivable_points or inventory_points or payable_points, _first_string_list(_source_payload(source_bundle, "working_capital_quality_drilldown").get("limitations"))),
        evidence_status="direct",
        recommended_display="expanded",
        generated_at=generated_at,
    )


def build_cash_conversion_cycle(source_bundle: Dict[str, Any], *, generated_at: str) -> Optional[Dict[str, Any]]:
    cycle_points = _working_capital_points(source_bundle, "cash_conversion_cycle")
    if not cycle_points:
        return None
    latest = cycle_points[-1]
    interpretation = "A long cash conversion cycle means cash stays tied up inside operations for longer before it returns."
    if latest.get("value") is not None and float(latest["value"]) <= 0:
        interpretation = "A short or negative cash conversion cycle can ease cash pressure, but that conclusion still needs business context."
    return _visual(
        visual_id="cash_conversion_cycle",
        title="Cash conversion cycle",
        subtitle="The time cash appears to stay tied up in operations.",
        visual_type="status" if len(cycle_points) == 1 else "line",
        unit="days",
        series=[_series("Cash conversion cycle", cycle_points)],
        interpretation=interpretation,
        precision_note=_trend_precision_note(cycle_points, None),
        evidence_status="direct",
        recommended_display="compact",
        generated_at=generated_at,
    )


def build_per_share_economics(source_bundle: Dict[str, Any], *, generated_at: str) -> Optional[Dict[str, Any]]:
    eps_points = _per_share_points(source_bundle, "eps_basic")
    owner_points = _per_share_points(source_bundle, "owner_earnings_per_share", derived=True)
    book_points = _per_share_points(source_bundle, "book_value_per_share")
    series = [series for series in [_series("Basic EPS", eps_points), _series("Owner-oriented cash per share", owner_points), _series("Book value per share", book_points)] if series["points"]]
    if not series:
        return None
    warning = _first_nonempty(
        _per_share_warning(source_bundle),
        _trend_precision_note(eps_points or owner_points or book_points, None),
    )
    return _visual(
        visual_id="per_share_economics",
        title="Per-share economics",
        subtitle="Current per-share metrics where share-count evidence is usable.",
        visual_type="comparison",
        unit="INR/share",
        series=series,
        interpretation="Per-share metrics are visible, but multi-year improvement should stay cautious when weighted-average share data is incomplete.",
        precision_note=warning,
        evidence_status="partial" if warning else "direct",
        recommended_display="compact",
        generated_at=generated_at,
    )


def build_capital_allocation_summary(source_bundle: Dict[str, Any], *, generated_at: str) -> Optional[Dict[str, Any]]:
    entries = _record_list(_source_payload(source_bundle, "capital_allocation_roi_ledger"), "entries")
    periods = _sorted_periods_from_records(entries)
    if not periods:
        return None
    capex_points = _capital_points(entries, "capex_deployed")
    dividends_points = _capital_points(entries, "dividends")
    debt_points = _capital_points(entries, "debt_repayment")
    if not capex_points and not dividends_points and not debt_points:
        return None
    return _visual(
        visual_id="capital_allocation_summary",
        title="Capital allocation summary",
        subtitle="Visible uses of capital from the current source set.",
        visual_type="bar",
        unit="INR crore",
        series=[
            _series("Capex deployed", capex_points),
            _series("Dividends", dividends_points),
            _series("Debt repayment", debt_points),
        ],
        interpretation="Capital use is visible more clearly than the eventual return on that capital.",
        precision_note=_first_nonempty(
            _first_string_list(_source_payload(source_bundle, "capital_allocation_roi_ledger").get("limitations")),
            _first_string_list(_source_payload(source_bundle, "capital_allocation_roi_ledger").get("warnings")),
        ),
        evidence_status="partial",
        recommended_display="compact",
        generated_at=generated_at,
    )


def _metric_points_from_truth(source_bundle: Dict[str, Any], metric_id: str, *, status: str) -> List[Dict[str, Any]]:
    truth = _source_payload(source_bundle, "financial_truth_pack")
    metrics = []
    for bucket in ("usable_current_metrics", "usable_derived_metrics"):
        metrics.extend(_get_list(truth, bucket))
    points: List[Dict[str, Any]] = []
    for metric in metrics:
        if str(metric.get("metric_id") or metric.get("canonical_metric") or "") != metric_id:
            continue
        year = _normalize_period(metric.get("fiscal_year"))
        value = _get_number(metric, "value")
        if value is None:
            value = _get_number(metric, "value_crore")
        if year is None or value is None:
            continue
        points.append(_point(year, value, status, unit="INR crore"))
    return _sort_points(points)


def _bridge_metric_points(source_bundle: Dict[str, Any], key: str, *, status: str) -> List[Dict[str, Any]]:
    records = _record_list(_source_payload(source_bundle, "owner_earnings_bridge"), "bridges")
    points: List[Dict[str, Any]] = []
    for record in records:
        value = _get_number(record, key)
        year = _normalize_period(record.get("fiscal_year"))
        if year is None or value is None:
            continue
        points.append(_point(year, value, status, unit="INR crore"))
    return _sort_points(points)


def _working_capital_points(source_bundle: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    records = _record_list(_source_payload(source_bundle, "working_capital_quality_drilldown"), "drilldown")
    points: List[Dict[str, Any]] = []
    for record in records:
        year = _normalize_period(record.get("fiscal_year"))
        value = _get_number(record, key)
        if year is None or value is None:
            continue
        points.append(_point(year, value, "reported", unit="days"))
    return _sort_points(points)


def _per_share_points(source_bundle: Dict[str, Any], key: str, *, derived: bool = False) -> List[Dict[str, Any]]:
    records = _record_list(_source_payload(source_bundle, "per_share_compounding_analysis"), "analysis")
    points: List[Dict[str, Any]] = []
    for record in records:
        year = _normalize_period(record.get("fiscal_year"))
        value = _get_number(record, key)
        if year is None or value is None:
            continue
        points.append(_point(year, value, "derived" if derived else "reported", unit="INR/share"))
    return _sort_points(points)


def _capital_points(entries: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    points: List[Dict[str, Any]] = []
    for record in entries:
        year = _normalize_period(record.get("fiscal_year"))
        value = _get_number(record, key)
        if year is None or value is None:
            continue
        points.append(_point(year, abs(value), "partial", unit="INR crore"))
    return _sort_points(points)


def _series(label: str, points: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"label": label, "points": _limit_points(points)}


def _visual(
    *,
    visual_id: str,
    title: str,
    subtitle: str,
    visual_type: str,
    unit: str,
    series: List[Dict[str, Any]],
    interpretation: str,
    precision_note: Optional[str],
    evidence_status: str,
    recommended_display: str,
    generated_at: str,
) -> Dict[str, Any]:
    return {
        "id": visual_id,
        "title": title,
        "subtitle": subtitle,
        "visual_type": visual_type,
        "unit": unit,
        "series": [item for item in series if item.get("points")][:3],
        "interpretation": interpretation,
        "precision_note": precision_note,
        "evidence_status": evidence_status,
        "recommended_display": recommended_display,
        "generated_at": generated_at,
    }


def _point(period: str, value: Optional[float], status: str, *, unit: str, semantic_label: Optional[str] = None) -> Dict[str, Any]:
    return {
        "period": period.upper(),
        "value": value,
        "display_value": _format_value(value, unit=unit),
        "semantic_label": semantic_label,
        "status": status if value is not None else "missing",
    }


def _format_value(value: Optional[float], *, unit: str) -> Optional[str]:
    if value is None:
        return None
    if unit == "INR crore":
        return f"₹{value:,.2f} crore"
    if unit == "INR/share":
        return f"₹{value:,.2f}/share"
    if unit == "days":
        return f"{value:,.1f} days"
    return f"{value}"


def _trend_precision_note(points: List[Dict[str, Any]], extra_note: Optional[str]) -> Optional[str]:
    if extra_note:
        return extra_note
    if len(points) <= 1:
        return "Only one usable period is available, so this should be read as current-state evidence rather than a trend."
    return None


def _latest_year_record(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    records = _record_list(payload, key)
    if not records:
        return {}
    return sorted(records, key=lambda item: _period_sort_key(item.get("fiscal_year")), reverse=True)[0]


def _sorted_periods_from_records(records: List[Dict[str, Any]]) -> List[str]:
    periods = {_normalize_period(record.get("fiscal_year")) for record in records}
    return [period for period in sorted(periods, key=_period_sort_key) if period]


def _sort_points(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(points, key=lambda item: _period_sort_key(item.get("period")))


def _limit_points(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return points[-8:]


def _source_payload(source_bundle: Dict[str, Any], key: str) -> Dict[str, Any]:
    return ((source_bundle.get("sources") or {}).get(key) or {}).get("payload") or {}


def _get_list(payload: Dict[str, Any], key: str) -> List[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _record_list(payload: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    return [item for item in _get_list(payload, key) if isinstance(item, dict)]


def _get_number(payload: Dict[str, Any], key: str) -> Optional[float]:
    value = payload.get(key)
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_period(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if not text:
        return None
    return text


def _period_sort_key(value: Any) -> int:
    text = str(value or "").strip().lower().replace("fy", "")
    digits = "".join(ch for ch in text if ch.isdigit())
    try:
        return int(digits)
    except ValueError:
        return 0


def _year_label(payload: Dict[str, Any]) -> Optional[str]:
    period = _normalize_period(payload.get("fiscal_year"))
    return period.upper() if period else None


def _first_string_list(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_nonempty(*values: Any) -> Optional[str]:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _get_list_record_values(payload: Dict[str, Any], key: str) -> List[str]:
    return [str(value).strip() for value in _get_list(payload, key) if str(value).strip()]


def _per_share_warning(source_bundle: Dict[str, Any]) -> Optional[str]:
    analysis = _source_payload(source_bundle, "per_share_compounding_analysis")
    warning = _first_string_list(analysis.get("warnings"))
    if warning:
        return warning
    for record in _record_list(analysis, "analysis"):
        text = str(record.get("fcf_per_share_warning") or "").strip()
        if text:
            return text
    return None
