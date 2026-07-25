from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from .corporate_action_schema import CorporateActionItem, ShareCountSummary


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _parse_numeric(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return None
    negative = raw.startswith("(") or raw.startswith("[") or raw.startswith("-")
    raw = raw.strip("()[]")
    if raw.startswith("-"):
        raw = raw[1:]
    try:
        numeric = float(raw)
    except ValueError:
        return None
    return -numeric if negative else numeric


def _entry(payload: Dict[str, Any], section: str, field: str) -> Dict[str, Any]:
    section_payload = payload.get(section, {})
    return section_payload.get(field, {}) if isinstance(section_payload, dict) else {}


def _current_face_value(normalized_payload: Dict[str, Any]) -> Optional[float]:
    entry = _entry(normalized_payload, "share_data", "face_value")
    return _parse_numeric(entry.get("value_original"))


def _weighted_avg_shares(normalized_payload: Dict[str, Any]) -> Optional[float]:
    return _parse_numeric(_entry(normalized_payload, "share_data", "weighted_avg_shares").get("value_original"))


def _diluted_shares(normalized_payload: Dict[str, Any]) -> Optional[float]:
    return _parse_numeric(_entry(normalized_payload, "share_data", "diluted_shares").get("value_original"))


def _shares_outstanding(normalized_payload: Dict[str, Any]) -> Optional[float]:
    raw = _parse_numeric(_entry(normalized_payload, "share_data", "shares_outstanding").get("value_original"))
    if raw is not None:
        return raw
    face_value = _current_face_value(normalized_payload)
    equity_capital = _entry(normalized_payload, "balance_sheet", "equity_share_capital").get("value_crore")
    if isinstance(equity_capital, (int, float)) and face_value not in (None, 0):
        return (float(equity_capital) * 10_000_000.0) / float(face_value)
    return None


def build_share_count_summary(
    *,
    normalized_payload: Dict[str, Any],
    actions: Iterable[CorporateActionItem],
) -> Tuple[ShareCountSummary, List[str]]:
    warnings: List[str] = []
    face_value = _current_face_value(normalized_payload)
    closing_shares = _shares_outstanding(normalized_payload)
    weighted_avg = _weighted_avg_shares(normalized_payload)
    diluted = _diluted_shares(normalized_payload)

    event_items = [
        {
            "action_type": item.action_type,
            "ratio": item.ratio,
            "shares_before": item.shares_before,
            "shares_after": item.shares_after,
            "impact_on_share_count": item.impact_on_share_count,
            "source_line_item": item.source_line_item,
            "source_page": item.source_page,
            "confidence": item.confidence,
        }
        for item in actions
        if item.impact_on_share_count != "none"
    ]

    opening_shares = None
    for item in actions:
        if item.shares_before is not None:
            opening_shares = item.shares_before
            break
    if opening_shares is None:
        opening_shares = closing_shares

    eps_basic = _parse_numeric(_entry(normalized_payload, "profit_and_loss", "eps_basic").get("value_original"))
    eps_diluted = _parse_numeric(_entry(normalized_payload, "profit_and_loss", "eps_diluted").get("value_original"))
    if eps_basic is not None and weighted_avg is None:
        _append_unique(warnings, "EPS exists but weighted average shares are missing")
    if eps_diluted is not None and diluted is None:
        _append_unique(warnings, "diluted shares missing")

    for item in actions:
        if item.action_type in {"stock_split", "bonus_issue"} and not item.ratio:
            _append_unique(warnings, f"{item.action_type} detected but ratio unclear")
        if item.action_type in {"qip", "preferential_issue"} and item.impact_on_share_count == "unknown":
            _append_unique(warnings, f"{item.action_type} detected but share count impact unclear")
        if item.action_type == "face_value_change":
            _append_unique(warnings, "face value changed")
        if item.impact_on_eps_comparability == "yes":
            _append_unique(
                warnings,
                f"{item.action_type} may affect per-share comparability",
            )

    return (
        ShareCountSummary(
            opening_shares=opening_shares,
            closing_shares=closing_shares,
            weighted_avg_shares=weighted_avg,
            diluted_shares=diluted,
            face_value=face_value,
            share_count_events=event_items,
        ),
        warnings,
    )
