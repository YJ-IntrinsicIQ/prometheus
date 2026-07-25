from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .attribution_schema import (
    FinancialDriverAttributionItem,
    FinancialDriverAttributionReport,
    validate_financial_driver_attribution_payload,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else None


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _trend_series(payload: Dict[str, Any], container: str, metric: str) -> List[Dict[str, Any]]:
    section = payload.get(container, {})
    item = section.get(metric, {}) if isinstance(section, dict) else {}
    series = item.get("series", []) if isinstance(item, dict) else []
    return series if isinstance(series, list) else []


def _growth_points(payload: Dict[str, Any], metric: str) -> List[Dict[str, Any]]:
    section = payload.get("growth_summary", {})
    points = section.get(metric, []) if isinstance(section, dict) else []
    return points if isinstance(points, list) else []


def _latest_point(items: Sequence[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
    for item in reversed(items):
        if isinstance(item.get(key), (int, float)):
            return item
    return None


def _first_numeric(items: Sequence[Dict[str, Any]], key: str) -> Optional[float]:
    for item in items:
        if isinstance(item.get(key), (int, float)):
            return float(item[key])
    return None


def _latest_numeric(items: Sequence[Dict[str, Any]], key: str) -> Optional[float]:
    point = _latest_point(items, key)
    if point is None:
        return None
    return float(point[key])


def _delta(items: Sequence[Dict[str, Any]], key: str = "value") -> Optional[float]:
    first = _first_numeric(items, key)
    latest = _latest_numeric(items, key)
    if first is None or latest is None:
        return None
    return latest - first


def _latest_year_from_series(items: Sequence[Dict[str, Any]]) -> str:
    for item in reversed(items):
        year = str(item.get("year", "")).strip()
        if year:
            return year
    return ""


def _latest_growth(items: Sequence[Dict[str, Any]]) -> Tuple[Optional[float], str, Optional[float]]:
    point = _latest_point(items, "growth_percent")
    if point is None:
        return None, "", None
    absolute_change = point.get("absolute_change")
    return (
        float(point["growth_percent"]),
        str(point.get("year", "")),
        float(absolute_change) if isinstance(absolute_change, (int, float)) else None,
    )


def _format_percent(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    return f"{value:+.1f}%"


def _format_crore(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    return f"{value:+.1f} crore"


def _format_period(year: str, years_covered: Sequence[str]) -> str:
    if not year:
        return "unknown"
    if len(years_covered) >= 2 and year == years_covered[-1]:
        return f"{years_covered[-2]}->{year}"
    return year


def _build_event(
    *,
    year: str,
    label: str,
    driver_type: str,
    source_artifact: str,
    evidence_ids: Optional[Iterable[str]] = None,
    confidence: str = "medium",
) -> Dict[str, Any]:
    return {
        "year": year,
        "label": label,
        "driver_type": driver_type,
        "source_artifact": source_artifact,
        "evidence_ids": [str(item) for item in (evidence_ids or []) if str(item).strip()],
        "confidence": confidence,
    }


def _strategy_events(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    events: List[Dict[str, Any]] = []
    for entry in payload.get("timeline", []) if isinstance(payload.get("timeline"), list) else []:
        if not isinstance(entry, dict):
            continue
        year = str(entry.get("year", "")).strip()
        for section_name in ("management_focus", "major_projects", "major_initiatives", "strategic_themes"):
            for item in entry.get(section_name, []) if isinstance(entry.get(section_name), list) else []:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("value") or item.get("candidate_label") or item.get("raw_label") or "").strip()
                if not label:
                    continue
                events.append(
                    _build_event(
                        year=year or str(item.get("source_year", "")).strip(),
                        label=label,
                        driver_type="order_execution",
                        source_artifact=str(item.get("source_artifact") or "strategy_timeline.json"),
                        evidence_ids=item.get("evidence_ids", []),
                        confidence="medium",
                    )
                )
    return events


def _capital_allocation_events(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    events: List[Dict[str, Any]] = []
    field_to_driver = {
        "capex": "capex",
        "cwip": "capex",
        "acquisitions": "capex",
        "equity_issuance": "equity_raise",
        "debt_borrowings": "debt",
        "debt_repayments": "debt",
        "buybacks": "corporate_action",
        "share_splits": "corporate_action",
        "dividends": "corporate_action",
    }
    for entry in payload.get("timeline", []) if isinstance(payload.get("timeline"), list) else []:
        if not isinstance(entry, dict):
            continue
        year = str(entry.get("year", "")).strip()
        for field_name, driver_type in field_to_driver.items():
            for item in entry.get(field_name, []) if isinstance(entry.get(field_name), list) else []:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("value") or item.get("canonical_category") or field_name).strip()
                events.append(
                    _build_event(
                        year=year or str(item.get("source_year", "")).strip(),
                        label=label,
                        driver_type=driver_type,
                        source_artifact=str(item.get("source_artifact") or "capital_allocation_timeline.json"),
                        evidence_ids=item.get("evidence_ids", []),
                        confidence=str(item.get("confidence") or "medium"),
                    )
                )
    return events


def _promise_events(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    events: List[Dict[str, Any]] = []
    aggregated: List[Dict[str, Any]] = []
    for key in ("promises", "fulfilled_promises", "repeated_unresolved_promises", "unclear_promises"):
        if isinstance(payload.get(key), list):
            aggregated.extend([item for item in payload[key] if isinstance(item, dict)])
    for item in aggregated:
        source_mentions = item.get("source_mentions", [])
        year = str(item.get("first_seen_year", "")).strip()
        if isinstance(source_mentions, list) and source_mentions:
            year = str(source_mentions[0].get("source_year", year)).strip()
        label = str(item.get("normalized_promise") or item.get("promise_id") or "").strip()
        if label:
            events.append(
                _build_event(
                    year=year,
                    label=label,
                    driver_type="order_execution",
                    source_artifact="promise_tracker.json",
                    evidence_ids=item.get("related_evidence_ids", []),
                    confidence="low",
                )
            )
    return events


def _risk_events(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    events: List[Dict[str, Any]] = []
    for item in payload.get("risks", []) if isinstance(payload.get("risks"), list) else []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("normalized_risk") or item.get("risk_id") or "").strip()
        if label:
            events.append(
                _build_event(
                    year=str(item.get("first_seen_year", "")).strip(),
                    label=label,
                    driver_type="risk",
                    source_artifact="risk_evolution.json",
                    evidence_ids=item.get("related_evidence_ids", []),
                    confidence="low",
                )
            )
    return events


def _management_consistency_events(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    events: List[Dict[str, Any]] = []
    for item in payload.get("consistency_observations", []) if isinstance(payload.get("consistency_observations"), list) else []:
        if not isinstance(item, dict):
            continue
        years_active = item.get("years_active", [])
        year = str(years_active[-1]).strip() if isinstance(years_active, list) and years_active else ""
        theme = str(item.get("theme") or "").strip()
        if not theme:
            continue
        events.append(
            _build_event(
                year=year,
                label=theme,
                driver_type="capex" if "capex" in theme else "order_execution",
                source_artifact="management_consistency.json",
                evidence_ids=item.get("evidence_ids", []),
                confidence="medium",
            )
        )
    return events


def _corporate_action_events_from_trends(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for item in payload.get("corporate_actions_timeline", []) if isinstance(payload.get("corporate_actions_timeline"), list) else []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("action_type") or item.get("source_line_item") or "corporate_action").strip()
        events.append(
            _build_event(
                year=str(item.get("year", "")).strip(),
                label=label,
                driver_type="corporate_action",
                source_artifact=str(item.get("source_artifact") or "financial_trends.json"),
                evidence_ids=item.get("evidence_ids", []),
                confidence=str(item.get("confidence") or "medium"),
            )
        )
    return events


def _corporate_action_events_from_report(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    events: List[Dict[str, Any]] = []
    for item in payload.get("actions", []) if isinstance(payload.get("actions"), list) else []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("action_type") or item.get("source_line_item") or "corporate_action").strip()
        events.append(
            _build_event(
                year=str(item.get("year", "")).strip(),
                label=label,
                driver_type="equity_raise" if label in {"qip", "preferential_issue", "rights_issue"} else "corporate_action",
                source_artifact=str(item.get("source_artifact") or "corporate_actions.json"),
                evidence_ids=item.get("evidence_ids", []),
                confidence=str(item.get("confidence") or "medium"),
            )
        )
    return events


def _collect_events(company_root: Path, trends: Dict[str, Any]) -> List[Dict[str, Any]]:
    multi_year_root = company_root / "company_memory" / "multi_year"
    events: List[Dict[str, Any]] = []
    events.extend(_strategy_events(_load_optional_json(multi_year_root / "strategy_timeline.json")))
    events.extend(_capital_allocation_events(_load_optional_json(multi_year_root / "capital_allocation_timeline.json")))
    events.extend(_promise_events(_load_optional_json(multi_year_root / "promise_tracker.json")))
    events.extend(_risk_events(_load_optional_json(multi_year_root / "risk_evolution.json")))
    events.extend(_management_consistency_events(_load_optional_json(multi_year_root / "management_consistency.json")))
    events.extend(_corporate_action_events_from_trends(trends))
    events.extend(
        _corporate_action_events_from_report(
            _load_optional_json(company_root / "company_memory" / "financials" / "corporate_actions.json")
        )
    )
    return events


def _find_event(
    events: Sequence[Dict[str, Any]],
    *,
    preferred_types: Sequence[str],
    year: str,
    preferred_labels: Sequence[str] = (),
) -> Optional[Dict[str, Any]]:
    scoped = [event for event in events if event.get("driver_type") in preferred_types]
    if year:
        year_scoped = [event for event in scoped if event.get("year") == year]
        if year_scoped:
            scoped = year_scoped
    if not scoped:
        return None
    label_tokens = [token.lower() for token in preferred_labels if token]
    if label_tokens:
        for event in scoped:
            label = str(event.get("label", "")).lower()
            if any(token in label for token in label_tokens):
                return event
    return scoped[0]


def _event_driver_text(event: Optional[Dict[str, Any]], fallback: str) -> str:
    if not event:
        return fallback
    return f"Possible driver: {event.get('label', fallback)}."


def _build_item(
    *,
    metric: str,
    movement: str,
    period: str,
    observed_change: str,
    possible_driver: str,
    driver_type: str,
    supporting_event: str,
    confidence: str,
    causality_status: str,
    event: Optional[Dict[str, Any]] = None,
    warnings: Optional[Iterable[str]] = None,
    verification_questions: Optional[Iterable[str]] = None,
) -> FinancialDriverAttributionItem:
    evidence_ids = list(event.get("evidence_ids", [])) if event else []
    source_artifacts: List[str] = []
    if event and event.get("source_artifact"):
        _append_unique(source_artifacts, str(event["source_artifact"]))
    item_warnings = [str(item) for item in (warnings or [])]
    if not evidence_ids:
        _append_unique(item_warnings, "supporting evidence is limited")
    return FinancialDriverAttributionItem(
        metric=metric,
        movement=movement,
        period=period,
        observed_change=observed_change,
        possible_driver=possible_driver,
        driver_type=driver_type,
        supporting_event=supporting_event,
        confidence=confidence,
        causality_status=causality_status,
        evidence_ids=evidence_ids,
        source_artifacts=source_artifacts,
        warnings=item_warnings,
        verification_questions=[str(item) for item in (verification_questions or [])],
    )


def build_financial_driver_attribution(*, company: str, company_root: Path) -> FinancialDriverAttributionReport:
    financial_root = company_root / "company_memory" / "financials"
    trends_path = financial_root / "financial_trends.json"
    if not trends_path.exists():
        raise RuntimeError(f"financial_attribution requires financial_trends.json: {trends_path}")

    trends = _load_json(trends_path)
    if not isinstance(trends, dict):
        raise RuntimeError("financial_attribution requires a valid financial_trends.json object")

    quality = _load_optional_json(financial_root / "financial_quality_summary.json")
    events = _collect_events(company_root, trends)
    years_covered = [str(year) for year in trends.get("years_covered", [])] if isinstance(trends.get("years_covered"), list) else []
    latest_year = years_covered[-1] if years_covered else ""

    items: List[FinancialDriverAttributionItem] = []
    warnings: List[str] = []
    limitations: List[str] = [str(item) for item in trends.get("limitations", [])] if isinstance(trends.get("limitations"), list) else []
    if isinstance(quality, dict) and isinstance(quality.get("limitations"), list):
        for item in quality.get("limitations", []):
            _append_unique(limitations, str(item))

    revenue_growth, revenue_year, revenue_abs = _latest_growth(_growth_points(trends, "revenue"))
    if revenue_growth is not None and abs(revenue_growth) >= 5:
        event = _find_event(events, preferred_types=("order_execution", "customer_concentration", "risk"), year=revenue_year or latest_year)
        items.append(
            _build_item(
                metric="revenue",
                movement="improved" if revenue_growth > 0 else "declined",
                period=_format_period(revenue_year or latest_year, years_covered),
                observed_change=f"Revenue growth {_format_percent(revenue_growth)} ({_format_crore(revenue_abs)} absolute change)",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: execution and demand conditions changed, but the exact commercial driver requires verification.",
                ),
                driver_type=str(event.get("driver_type")) if event else "order_execution",
                supporting_event=str(event.get("label", "No proximate management event found.")) if event else "No proximate management event found.",
                confidence="medium" if event else "low",
                causality_status="possible" if event else "weak",
                event=event,
                verification_questions=["Which products, customers, or execution milestones explain the revenue move?"],
            )
        )

    pat_growth, pat_year, pat_abs = _latest_growth(_growth_points(trends, "pat"))
    if pat_growth is not None and abs(pat_growth) >= 5:
        event = _find_event(events, preferred_types=("margin", "order_execution", "risk", "capex"), year=pat_year or latest_year)
        items.append(
            _build_item(
                metric="pat",
                movement="improved" if pat_growth > 0 else "declined",
                period=_format_period(pat_year or latest_year, years_covered),
                observed_change=f"PAT growth {_format_percent(pat_growth)} ({_format_crore(pat_abs)} absolute change)",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: operating execution or cost absorption shifted, but direct causation is not established.",
                ),
                driver_type=str(event.get("driver_type")) if event else "margin",
                supporting_event=str(event.get("label", "No direct business event found.")) if event else "No direct business event found.",
                confidence="medium" if event else "low",
                causality_status="possible" if event else "weak",
                event=event,
                verification_questions=["Did the profit move come from volume, pricing, mix, or one-off cost changes?"],
            )
        )

    opm_series = _trend_series(trends, "margin_trends", "opm")
    opm_change = _delta(opm_series)
    if opm_change is not None and abs(opm_change) >= 1.0:
        event = _find_event(events, preferred_types=("capex", "order_execution", "risk"), year=_latest_year_from_series(opm_series) or latest_year)
        items.append(
            _build_item(
                metric="opm",
                movement="improved" if opm_change > 0 else "compressed",
                period=_format_period(_latest_year_from_series(opm_series) or latest_year, years_covered),
                observed_change=f"Operating margin moved by {_format_percent(opm_change)}",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: execution mix, cost structure, or ramp-up effects changed margins, but the exact source requires verification.",
                ),
                driver_type=str(event.get("driver_type")) if event else "margin",
                supporting_event=str(event.get("label", "No direct margin-side event found.")) if event else "No direct margin-side event found.",
                confidence="medium" if event else "low",
                causality_status="possible" if event else "weak",
                event=event,
                verification_questions=["What mix, pricing, or cost changes explain the margin move?"],
            )
        )

    roce_series = _trend_series(trends, "return_trends", "roce")
    roce_change = _delta(roce_series)
    if roce_change is not None and abs(roce_change) >= 1.0:
        event = _find_event(
            events,
            preferred_types=("capex", "equity_raise", "debt"),
            year=_latest_year_from_series(roce_series) or latest_year,
            preferred_labels=("qip", "equity", "capex", "cwip", "debt"),
        )
        items.append(
            _build_item(
                metric="roce",
                movement="improved" if roce_change > 0 else "declined",
                period=_format_period(_latest_year_from_series(roce_series) or latest_year, years_covered),
                observed_change=f"ROCE moved by {_format_percent(roce_change)}",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: capital employed changed faster than operating return, but the driver needs verification.",
                ),
                driver_type=str(event.get("driver_type")) if event else "unknown",
                supporting_event=str(event.get("label", "No proximate capital event found.")) if event else "No proximate capital event found.",
                confidence="medium" if event else "low",
                causality_status="possible" if event else "weak",
                event=event,
                verification_questions=["Did capex, equity raising, or working-capital build temporarily depress returns?"],
            )
        )

    roe_series = _trend_series(trends, "return_trends", "roe")
    roe_change = _delta(roe_series)
    if roe_change is not None and abs(roe_change) >= 1.0:
        event = _find_event(
            events,
            preferred_types=("equity_raise", "corporate_action", "debt"),
            year=_latest_year_from_series(roe_series) or latest_year,
            preferred_labels=("qip", "equity", "preferential", "rights"),
        )
        items.append(
            _build_item(
                metric="roe",
                movement="improved" if roe_change > 0 else "declined",
                period=_format_period(_latest_year_from_series(roe_series) or latest_year, years_covered),
                observed_change=f"ROE moved by {_format_percent(roe_change)}",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: equity base or profitability changed, but the relationship needs verification.",
                ),
                driver_type=str(event.get("driver_type")) if event else "unknown",
                supporting_event=str(event.get("label", "No proximate equity-side event found.")) if event else "No proximate equity-side event found.",
                confidence="medium" if event else "low",
                causality_status="possible" if event else "weak",
                event=event,
                verification_questions=["Was the ROE move driven by profitability, dilution, or a larger capital base?"],
            )
        )

    debt_series = _trend_series(trends, "balance_sheet_trends", "total_debt")
    debt_change = _delta(debt_series)
    if debt_change is not None and abs(debt_change) >= 1.0:
        debt_year = _latest_year_from_series(debt_series) or latest_year
        event = _find_event(events, preferred_types=("debt", "capex"), year=debt_year, preferred_labels=("debt", "borrowing", "repayment", "capex"))
        items.append(
            _build_item(
                metric="total_debt",
                movement="spiked" if debt_change > 0 else "improved",
                period=_format_period(debt_year, years_covered),
                observed_change=f"Debt changed by {_format_crore(debt_change)}",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: financing activity changed debt levels, but the exact use of proceeds requires verification.",
                ),
                driver_type=str(event.get("driver_type")) if event else "debt",
                supporting_event=str(event.get("label", "No debt-related event found.")) if event else "No debt-related event found.",
                confidence="medium" if event else "low",
                causality_status="possible" if event else "weak",
                event=event,
                verification_questions=["Was the debt movement linked to capex, refinancing, or working-capital funding?"],
            )
        )

    cfo_pat_series = _trend_series(trends, "cash_conversion_trends", "cfo_to_pat")
    cfo_pat_latest = _latest_numeric(cfo_pat_series, "value")
    cfo_pat_change = _delta(cfo_pat_series)
    if (cfo_pat_latest is not None and cfo_pat_latest < 80) or (cfo_pat_change is not None and cfo_pat_change < -10):
        period_year = _latest_year_from_series(cfo_pat_series) or latest_year
        event = _find_event(events, preferred_types=("working_capital", "risk", "order_execution"), year=period_year)
        items.append(
            _build_item(
                metric="cfo_to_pat",
                movement="declined",
                period=_format_period(period_year, years_covered),
                observed_change=f"CFO/PAT is {cfo_pat_latest:.1f}%" if cfo_pat_latest is not None else "CFO/PAT deteriorated",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: working-capital absorption or slower cash realization is likely, but it requires verification.",
                ),
                driver_type=str(event.get("driver_type")) if event else "working_capital",
                supporting_event=str(event.get("label", "No direct working-capital event found.")) if event else "No direct working-capital event found.",
                confidence="medium" if event else "low",
                causality_status="possible" if event else "weak",
                event=event,
                verification_questions=["Did receivables, inventory, or customer terms absorb operating cash flow?"],
            )
        )

    fcf_series = _trend_series(trends, "cash_conversion_trends", "fcf")
    fcf_latest = _latest_numeric(fcf_series, "value")
    fcf_change = _delta(fcf_series)
    if (fcf_latest is not None and fcf_latest < 0) or (fcf_change is not None and fcf_change < -1):
        period_year = _latest_year_from_series(fcf_series) or latest_year
        event = _find_event(events, preferred_types=("capex", "debt"), year=period_year, preferred_labels=("capex", "cwip", "facility"))
        items.append(
            _build_item(
                metric="fcf",
                movement="declined",
                period=_format_period(period_year, years_covered),
                observed_change=f"FCF is {_format_crore(fcf_latest)}" if fcf_latest is not None else "FCF deteriorated",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: capital deployment or weak cash conversion pressured free cash flow, but the exact source requires verification.",
                ),
                driver_type=str(event.get("driver_type")) if event else "capex",
                supporting_event=str(event.get("label", "No proximate capital-deployment event found.")) if event else "No proximate capital-deployment event found.",
                confidence="medium" if event else "low",
                causality_status="possible" if event else "weak",
                event=event,
                verification_questions=["Was free-cash-flow pressure driven by capex, receivables, or both?"],
            )
        )

    receivables_series = _trend_series(trends, "cash_conversion_trends", "receivables")
    revenue_series = _trend_series(trends, "metric_trends", "revenue")
    receivables_change = _delta(receivables_series)
    revenue_change = _delta(revenue_series)
    if receivables_change is not None and revenue_change is not None and receivables_change > revenue_change:
        period_year = _latest_year_from_series(receivables_series) or latest_year
        items.append(
            _build_item(
                metric="receivables",
                movement="spiked",
                period=_format_period(period_year, years_covered),
                observed_change=f"Receivables changed by {_format_crore(receivables_change)} versus revenue {_format_crore(revenue_change)}",
                possible_driver="Possible driver: working-capital pressure is likely related to slower collections or revenue conversion, but that requires verification.",
                driver_type="working_capital",
                supporting_event="Financial trend and quality signals show receivables rising faster than revenue.",
                confidence="medium",
                causality_status="possible",
                warnings=["cash conversion concern accompanies this movement"],
                verification_questions=["Did customer collections slow, or did sales terms become looser?"],
            )
        )

    inventory_series = _trend_series(trends, "cash_conversion_trends", "inventory")
    inventory_change = _delta(inventory_series)
    if inventory_change is not None and inventory_change > 1:
        period_year = _latest_year_from_series(inventory_series) or latest_year
        event = _find_event(events, preferred_types=("capex", "order_execution", "risk"), year=period_year)
        items.append(
            _build_item(
                metric="inventory",
                movement="spiked",
                period=_format_period(period_year, years_covered),
                observed_change=f"Inventory changed by {_format_crore(inventory_change)}",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: production build-up or slower sell-through changed inventory, but this requires verification.",
                ),
                driver_type=str(event.get("driver_type")) if event else "working_capital",
                supporting_event=str(event.get("label", "No direct inventory-side event found.")) if event else "No direct inventory-side event found.",
                confidence="medium" if event else "low",
                causality_status="possible" if event else "weak",
                event=event,
                verification_questions=["Was inventory growth deliberate capacity build-up or slower demand conversion?"],
            )
        )

    eps_growth, eps_year, _ = _latest_growth(_growth_points(trends, "eps_basic"))
    if pat_growth is not None and eps_growth is not None and pat_growth > eps_growth + 10:
        period_year = eps_year or pat_year or latest_year
        event = _find_event(events, preferred_types=("equity_raise", "corporate_action"), year=period_year, preferred_labels=("qip", "preferential", "rights", "split", "bonus"))
        label = str(event.get("label", "")).lower() if event else ""
        items.append(
            _build_item(
                metric="eps_basic",
                movement="compressed",
                period=_format_period(period_year, years_covered),
                observed_change=f"PAT growth {_format_percent(pat_growth)} outpaced EPS growth {_format_percent(eps_growth)}",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: share-count change or per-share comparability distortion is affecting EPS, but the exact mechanism requires verification.",
                ),
                driver_type=str(event.get("driver_type")) if event else "corporate_action",
                supporting_event=str(event.get("label", "No direct per-share comparability event found.")) if event else "No direct per-share comparability event found.",
                confidence="medium" if event else "low",
                causality_status="supported" if label in {"stock_split", "bonus_issue"} else ("possible" if event else "weak"),
                event=event,
                verification_questions=["Did dilution or per-share comparability effects distort EPS versus PAT?"],
            )
        )

    bvps_growth, bvps_year, bvps_abs = _latest_growth(_growth_points(trends, "book_value_per_share"))
    if bvps_growth is not None and abs(bvps_growth) >= 5:
        event = _find_event(events, preferred_types=("equity_raise", "order_execution", "debt"), year=bvps_year or latest_year)
        items.append(
            _build_item(
                metric="book_value_per_share",
                movement="improved" if bvps_growth > 0 else "declined",
                period=_format_period(bvps_year or latest_year, years_covered),
                observed_change=f"Book value per share growth {_format_percent(bvps_growth)} ({_format_crore(bvps_abs)} absolute change)",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: retained earnings or capital-base changes affected book value per share, but the exact source requires verification.",
                ),
                driver_type=str(event.get("driver_type")) if event else "unknown",
                supporting_event=str(event.get("label", "No direct balance-sheet event found.")) if event else "No direct balance-sheet event found.",
                confidence="medium" if event else "low",
                causality_status="possible" if event else "weak",
                event=event,
                verification_questions=["Was book-value change driven by retained earnings, dilution, or asset reconfiguration?"],
            )
        )

    share_count_series = _trend_series(trends, "per_share_trends", "share_count")
    share_count_change = _delta(share_count_series)
    if share_count_change is not None and share_count_change > 0:
        period_year = _latest_year_from_series(share_count_series) or latest_year
        event = _find_event(events, preferred_types=("equity_raise", "corporate_action"), year=period_year, preferred_labels=("qip", "preferential", "rights", "bonus", "split"))
        items.append(
            _build_item(
                metric="share_count",
                movement="spiked",
                period=_format_period(period_year, years_covered),
                observed_change=f"Share count changed by {share_count_change:+.1f}",
                possible_driver=_event_driver_text(
                    event,
                    "Possible driver: dilution or corporate-action comparability effects changed the share base, but the exact mechanism requires verification.",
                ),
                driver_type=str(event.get("driver_type")) if event else "corporate_action",
                supporting_event=str(event.get("label", "No direct share-count event found.")) if event else "No direct share-count event found.",
                confidence="high" if event and event.get("driver_type") == "equity_raise" else ("medium" if event else "low"),
                causality_status="supported" if event and event.get("driver_type") == "equity_raise" else ("possible" if event else "weak"),
                event=event,
                verification_questions=["Which issuance, split, or bonus event explains the larger share base?"],
            )
        )

    direct_comparability_event = _find_event(events, preferred_types=("corporate_action",), year=latest_year, preferred_labels=("stock_split", "bonus_issue"))
    if direct_comparability_event and str(direct_comparability_event.get("label", "")).lower() in {"stock_split", "bonus_issue"}:
        label = str(direct_comparability_event.get("label", "corporate_action"))
        items.append(
            _build_item(
                metric="eps_comparability",
                movement="unknown",
                period=_format_period(latest_year, years_covered),
                observed_change=f"{label} is present and may distort per-share comparisons",
                possible_driver=f"Possible driver: {label} changed per-share comparability directly.",
                driver_type="corporate_action",
                supporting_event=label,
                confidence="high",
                causality_status="supported",
                event=direct_comparability_event,
                verification_questions=["Were historical per-share numbers adjusted consistently after the corporate action?"],
            )
        )

    if not items:
        _append_unique(warnings, "no attribution found")
    elif not any(item.causality_status in {"supported", "possible"} for item in items):
        _append_unique(warnings, "only weak drivers found")
    if any(not item.evidence_ids for item in items):
        _append_unique(warnings, "evidence missing for one or more attribution items")
    if any(item.period == "unknown" for item in items):
        _append_unique(warnings, "event timing unclear for one or more attribution items")

    status = "warning" if warnings or any(item.warnings for item in items) else "pass"
    report = FinancialDriverAttributionReport(
        company=company,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        years_covered=years_covered,
        status=status,
        attributions=items,
        warnings=warnings,
        limitations=limitations,
    )
    validation_errors = validate_financial_driver_attribution_payload(report.to_dict())
    if validation_errors:
        raise ValueError("Invalid financial driver attribution payload: " + "; ".join(validation_errors))
    return report


def write_financial_driver_attribution(*, company: str, company_root: Path, output_path: Path) -> FinancialDriverAttributionReport:
    report = build_financial_driver_attribution(company=company, company_root=company_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report
