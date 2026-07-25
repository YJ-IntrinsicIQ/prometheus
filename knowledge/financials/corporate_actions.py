from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .corporate_action_schema import CorporateActionItem, CorporateActionsReport, validate_corporate_actions_payload
from .share_count_adjuster import build_share_count_summary


_ACTION_KEYWORDS: Sequence[Tuple[str, Sequence[str]]] = (
    ("interim_dividend", ("interim dividend",)),
    ("final_dividend", ("final dividend",)),
    ("dividend", ("dividend",)),
    ("bonus_issue", ("bonus issue", "bonus shares")),
    ("stock_split", ("stock split", "split of equity shares", "sub-division", "subdivision")),
    ("buyback", ("buyback", "buy-back")),
    ("rights_issue", ("rights issue", "rights shares", "rights entitlement")),
    ("qip", ("qip", "qualified institutional placement", "qualified institutions placement")),
    ("preferential_issue", ("preferential issue", "preferential allotment")),
    ("warrants", ("warrant", "warrants")),
    ("esop_dilution", ("esop", "employee stock option")),
    ("merger", ("merger", "amalgamation")),
    ("demerger", ("demerger", "demerged")),
    ("face_value_change", ("face value", "nominal value")),
    ("weighted_avg_shares", ("weighted average shares", "weighted avg shares", "weighted average number of equity shares")),
    ("diluted_shares", ("diluted shares", "diluted weighted average shares", "diluted weighted average number of equity shares")),
    ("share_capital_change", ("issue of shares", "shares issued", "issued share capital", "allotment of shares")),
)

_ALLOWED_TABLES = {"dividend", "corporate_actions", "share_capital", "eps", "cash_flow"}
_INCREASE_ACTIONS = {"bonus_issue", "rights_issue", "qip", "preferential_issue", "warrants", "esop_dilution", "share_capital_change"}
_DECREASE_ACTIONS = {"buyback"}
_EXPLICIT_SHARE_CAPITAL_EVENT_TOKENS = (
    "issue of shares",
    "shares issued",
    "allotment",
    "bonus issue",
    "rights issue",
    "preferential issue",
    "qip",
    "buyback",
    "stock split",
    "sub-division",
)
_DIVIDEND_PER_SHARE_TOKENS = (
    "dividend per share",
    "dividend per equity share",
    "dps",
    "final dividend per share",
    "interim dividend per share",
)
_DIVIDEND_CASH_TOKENS = (
    "dividend paid",
    "final dividend paid",
    "interim dividend paid",
)
_PROCEEDS_UTILIZATION_TOKENS = (
    "out of qip proceeds",
    "out of issue proceeds",
    "utilisation of proceeds",
    "utilization of proceeds",
    "utilisation of qip proceeds",
    "utilization of qip proceeds",
    "objects of issue",
    "objects of the issue",
    "amount utilised",
    "amount utilized",
    "use of proceeds",
    "application of proceeds",
)
_MEGA_TRANSACTION_EXEMPT_ACTIONS = {"merger", "demerger"}
_AMOUNT_ACTIONS = {
    "buyback",
    "rights_issue",
    "qip",
    "preferential_issue",
    "warrants",
    "esop_dilution",
    "merger",
    "demerger",
    "share_capital_change",
}
_SHARE_COUNT_ACTIONS = {
    "qip",
    "preferential_issue",
    "rights_issue",
    "warrants",
    "esop_dilution",
    "weighted_avg_shares",
    "diluted_shares",
    "share_capital_change",
    "buyback",
}


def _rejection_record(
    *,
    row: Dict[str, Any],
    rejected_action_type: str,
    rejection_reason: str,
    raw_value: str = "",
    detected_value_type: str = "",
) -> Dict[str, Any]:
    return {
        "source_line_item": str(row.get("line_item_raw", "") or ""),
        "raw_value": raw_value,
        "detected_value_type": detected_value_type,
        "attempted_action_type": rejected_action_type,
        "rejection_reason": rejection_reason,
        "source_page": row.get("page"),
        "source_artifact": str(row.get("source_artifact", "") or ""),
        "confidence": str(row.get("confidence", "low") or "low"),
    }


def _infer_rejected_action_type(line_item_raw: str) -> str:
    lowered = str(line_item_raw or "").lower()
    for action_type, keywords in _ACTION_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return action_type
    if "authorized share capital" in lowered or "authorised share capital" in lowered:
        return "share_capital_change"
    if "dividend" in lowered:
        return "dividend"
    if "bonus" in lowered:
        return "bonus_issue"
    if "rights" in lowered:
        return "rights_issue"
    if "preferential" in lowered:
        return "preferential_issue"
    if "qip" in lowered:
        return "qip"
    if "face value" in lowered or "nominal value" in lowered:
        return "face_value_change"
    return "unknown"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
    raw = raw.rstrip("%")
    try:
        numeric = float(raw)
    except ValueError:
        return None
    return -numeric if negative else numeric


def _entry(payload: Dict[str, Any], section: str, field: str) -> Dict[str, Any]:
    section_payload = payload.get(section, {})
    return section_payload.get(field, {}) if isinstance(section_payload, dict) else {}


def _fy_year_from_slug(year: str) -> Optional[str]:
    raw = str(year or "").strip().lower()
    if raw.startswith("fy") and raw[2:].isdigit():
        digits = raw[2:]
        if len(digits) == 2:
            return f"20{digits}"
        if len(digits) == 4:
            return digits
    return None


def _period_match_score(period: str, target_year: str) -> int:
    lowered = str(period or "").lower()
    if not lowered:
        return 0
    score = 1
    if target_year and target_year in lowered:
        score += 5
    if target_year and f"fy{target_year[-2:]}" in lowered:
        score += 5
    if "march 31" in lowered or "31 march" in lowered:
        score += 1
    return score


def _select_value(values: Sequence[Dict[str, Any]], target_year: str) -> Optional[Dict[str, Any]]:
    if not values:
        return None
    ranked = sorted(
        values,
        key=lambda item: (-_period_match_score(str(item.get("period", "")), target_year), list(values).index(item)),
    )
    return ranked[0]


def _parse_ratio(text: str) -> str:
    raw = str(text or "")
    for pattern in (
        r"(\d+\s*:\s*\d+)",
        r"(\d+\s*for\s*\d+)",
        r"(\d+\s*to\s*\d+)",
    ):
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _parse_face_value_change(text: str) -> Tuple[Optional[float], Optional[float]]:
    raw = str(text or "")
    for pattern in (
        r"face\s+value.*?(?:from|of)\s*(?:rs\.?|₹)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:to|each\s+to)\s*(?:rs\.?|₹)?\s*([0-9]+(?:\.[0-9]+)?)",
        r"from\s*(?:rs\.?|₹)?\s*([0-9]+(?:\.[0-9]+)?)\s*to\s*(?:rs\.?|₹)?\s*([0-9]+(?:\.[0-9]+)?)",
    ):
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            return _parse_numeric(match.group(1)), _parse_numeric(match.group(2))
    return None, None


def _classify_action(table_type: str, line_item_raw: str) -> Optional[str]:
    lowered = str(line_item_raw or "").lower()
    if table_type not in _ALLOWED_TABLES:
        return None
    for action_type, keywords in _ACTION_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            if action_type == "share_capital_change" and not any(token in lowered for token in _EXPLICIT_SHARE_CAPITAL_EVENT_TOKENS):
                continue
            if action_type == "dividend" and "dividend" not in lowered:
                continue
            return action_type
    return None


def _has_explicit_action_language(action_type: str, line_item_raw: str) -> bool:
    lowered = str(line_item_raw or "").lower()
    explicit_tokens = {
        "bonus_issue": ("bonus issue", "bonus shares"),
        "rights_issue": ("rights issue", "rights shares", "rights entitlement"),
        "preferential_issue": ("preferential issue", "preferential allotment"),
        "qip": ("qip", "qualified institutional placement", "qualified institutions placement"),
        "buyback": ("buyback", "buy-back"),
        "dividend": ("dividend declared", "recommended dividend", "interim dividend", "final dividend", "dividend paid"),
        "final_dividend": ("final dividend",),
        "interim_dividend": ("interim dividend",),
        "stock_split": ("stock split", "split of equity shares", "sub-division", "subdivision"),
        "face_value_change": ("face value", "nominal value"),
        "share_capital_change": _EXPLICIT_SHARE_CAPITAL_EVENT_TOKENS,
    }
    return any(token in lowered for token in explicit_tokens.get(action_type, (action_type.replace("_", " "),)))


def _selected_value_type(selected_value: Optional[Dict[str, Any]], unit_hint: str, line_item_raw: str) -> str:
    if isinstance(selected_value, dict):
        explicit = str(selected_value.get("value_type", "") or "").strip().lower()
        if explicit:
            return explicit
    lowered = str(line_item_raw or "").lower()
    unit_lower = str(unit_hint or "").lower()
    if unit_lower in {"shares", "units"} or "number of shares" in lowered or "weighted average" in lowered:
        return "share_count"
    if "%" in unit_lower or lowered.endswith("%"):
        return "percentage"
    if "per share" in lowered or "dps" in lowered:
        return "per_share"
    return "monetary"


def _source_column_context(selected_value: Optional[Dict[str, Any]], value_type: str) -> str:
    if not isinstance(selected_value, dict):
        return f"value_type={value_type}"
    unit_hint = str(selected_value.get("unit_hint", "") or "").strip()
    period = str(selected_value.get("period", "") or "").strip()
    extracted_value_type = str(selected_value.get("value_type", "") or "").strip()
    parts = [f"value_type={value_type}"]
    if extracted_value_type:
        parts.append(f"extracted_value_type={extracted_value_type}")
    if unit_hint:
        parts.append(f"unit_hint={unit_hint}")
    if period:
        parts.append(f"period={period}")
    return "; ".join(parts)


def _parse_issue_price(text: str) -> Optional[float]:
    raw = str(text or "")
    patterns = (
        r"(?:issue price|price of|priced at|at)\s*(?:rs\.?|₹|inr)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:per share|per equity share)?",
        r"(?:rs\.?|₹|inr)\s*([0-9]+(?:\.[0-9]+)?)\s*per share",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            return _parse_numeric(match.group(1))
    return None


def _is_authorized_share_capital(line_item_raw: str) -> bool:
    lowered = str(line_item_raw or "").lower()
    return "authorised share capital" in lowered or "authorized share capital" in lowered


def _is_objects_of_issue_reference(line_item_raw: str) -> bool:
    lowered = str(line_item_raw or "").lower()
    return any(token in lowered for token in _PROCEEDS_UTILIZATION_TOKENS)


def _action_subtype(action_type: str, line_item_raw: str) -> str:
    if action_type in {"qip", "rights_issue", "preferential_issue"} and _is_objects_of_issue_reference(line_item_raw):
        return f"{action_type}_proceeds_utilization"
    if action_type in {"qip", "rights_issue", "preferential_issue"}:
        return f"{action_type}_issue"
    return action_type


def _financial_scale_reference(normalized_payload: Dict[str, Any]) -> Optional[float]:
    candidates: List[float] = []
    for section_name, field_name in (
        ("profit_and_loss", "revenue"),
        ("balance_sheet", "net_worth"),
        ("balance_sheet", "total_assets"),
    ):
        entry = _entry(normalized_payload, section_name, field_name)
        value = entry.get("value_crore")
        if isinstance(value, (int, float)) and value > 0:
            candidates.append(float(value))
    return max(candidates) if candidates else None


def _sanitize_amount_against_scale(
    *,
    action_type: str,
    amount_crore: Optional[float],
    normalized_payload: Dict[str, Any],
    warnings: List[str],
) -> Tuple[Optional[float], Optional[str]]:
    if amount_crore is None or action_type in _MEGA_TRANSACTION_EXEMPT_ACTIONS:
        return amount_crore, None
    scale = _financial_scale_reference(normalized_payload)
    if not scale:
        return amount_crore, None
    if amount_crore <= scale * 10:
        return amount_crore, None
    reason = (
        f"amount_crore rejected as suspicious relative to financial scale: {amount_crore} crore "
        f"> 10x reference scale {scale} crore"
    )
    _append_unique(warnings, reason)
    return None, reason


def _impact_on_share_count(action_type: str) -> str:
    if action_type in _INCREASE_ACTIONS:
        return "increase"
    if action_type in _DECREASE_ACTIONS:
        return "decrease"
    if action_type in {"dividend", "final_dividend", "interim_dividend", "weighted_avg_shares", "diluted_shares"}:
        return "none"
    if action_type in {"stock_split", "face_value_change", "merger", "demerger"}:
        return "unknown"
    return "unknown"


def _eps_comparability(action_type: str) -> str:
    if action_type in {
        "bonus_issue",
        "stock_split",
        "buyback",
        "rights_issue",
        "qip",
        "preferential_issue",
        "warrants",
        "esop_dilution",
        "face_value_change",
        "share_capital_change",
    }:
        return "yes"
    if action_type in {"dividend", "final_dividend", "interim_dividend"}:
        return "no"
    return "unknown"


def _resolved_share_count_impact(
    *,
    action_type: str,
    action_subtype: str,
    shares_issued: Optional[float],
    shares_after: Optional[float],
    warnings: List[str],
) -> str:
    if action_subtype.endswith("proceeds_utilization"):
        return "none"
    if action_type == "qip":
        if shares_issued is not None or shares_after is not None:
            return "increase"
        _append_unique(warnings, "possible dilution, share count not captured")
        return "unknown"
    return _impact_on_share_count(action_type)


def _resolved_eps_comparability(
    *,
    action_type: str,
    action_subtype: str,
    impact_on_share_count: str,
) -> str:
    if action_subtype.endswith("proceeds_utilization"):
        return "no"
    if action_type == "qip":
        return "yes" if impact_on_share_count == "increase" else "unknown"
    return _eps_comparability(action_type)


def _normalized_field_to_action(field_name: str) -> Optional[str]:
    return {
        "dividend": "dividend",
        "bonus": "bonus_issue",
        "split": "stock_split",
        "buyback": "buyback",
        "rights_issue": "rights_issue",
        "qip": "qip",
        "preferential_issue": "preferential_issue",
        "merger": "merger",
        "demerger": "demerger",
    }.get(field_name)


def _build_from_normalized(
    *,
    normalized_payload: Dict[str, Any],
    year: str,
) -> List[CorporateActionItem]:
    actions: List[CorporateActionItem] = []
    current_face_value = _parse_numeric(_entry(normalized_payload, "share_data", "face_value").get("value_original"))
    for field_name, payload in (normalized_payload.get("corporate_actions") or {}).items():
        if not isinstance(payload, dict):
            continue
        action_type = _normalized_field_to_action(field_name)
        if not action_type:
            continue
        occurred = payload.get("occurred")
        ratio = str(payload.get("ratio", "") or "")
        amount_payload = payload.get("amount", {}) if isinstance(payload.get("amount"), dict) else {}
        amount_crore = amount_payload.get("value_crore") if isinstance(amount_payload.get("value_crore"), (int, float)) else None
        if not occurred and not ratio and amount_crore is None:
            continue
        actions.append(
            CorporateActionItem(
                action_type=action_type,
                year=year,
                action_subtype=_action_subtype(action_type, field_name.replace("_", " ")),
                ratio=ratio,
                amount_crore=float(amount_crore) if isinstance(amount_crore, (int, float)) else None,
                amount_raised_crore=float(amount_crore) if action_type in {"qip", "rights_issue", "preferential_issue"} and isinstance(amount_crore, (int, float)) else None,
                impact_on_share_count=_impact_on_share_count(action_type),
                impact_on_eps_comparability=_eps_comparability(action_type),
                source_line_item=field_name.replace("_", " "),
                source_page=payload.get("source_page"),
                source_artifact=str(payload.get("source_artifact", "")),
                confidence=str(payload.get("confidence", "missing") or "missing"),
                face_value=current_face_value,
                face_value_after=current_face_value if action_type == "face_value_change" else None,
                source_column_context="normalized corporate_actions field",
                value_type_used="monetary" if isinstance(amount_crore, (int, float)) else "",
                warnings=[str(item) for item in payload.get("notes", [])],
            )
        )
    return actions


def _build_from_raw(
    *,
    raw_payload: Optional[Dict[str, Any]],
    normalized_payload: Dict[str, Any],
    year: str,
) -> Tuple[List[CorporateActionItem], List[str], List[Dict[str, Any]]]:
    if not isinstance(raw_payload, dict):
        return [], [], []
    actions: List[CorporateActionItem] = []
    rejection_reasons: List[str] = []
    rejection_items: List[Dict[str, Any]] = []
    target_year = _fy_year_from_slug(year) or ""
    current_face_value = _parse_numeric(_entry(normalized_payload, "share_data", "face_value").get("value_original"))
    weighted_avg = _parse_numeric(_entry(normalized_payload, "share_data", "weighted_avg_shares").get("value_original"))
    diluted = _parse_numeric(_entry(normalized_payload, "share_data", "diluted_shares").get("value_original"))
    shares_outstanding = _parse_numeric(_entry(normalized_payload, "share_data", "shares_outstanding").get("value_original"))

    for table_type, rows in (raw_payload.get("tables") or {}).items():
        if table_type not in _ALLOWED_TABLES or not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            line_item_raw = str(row.get("line_item_raw", "") or "")
            action_type = _classify_action(table_type, line_item_raw)
            if not action_type:
                lowered_line_item = line_item_raw.lower()
                inferred = _infer_rejected_action_type(line_item_raw)
                if inferred != "unknown":
                    reason = "candidate mentions action-like language but does not satisfy explicit classification rules"
                    if "dividend income" in lowered_line_item:
                        reason = "dividend income is not a corporate action"
                        _append_unique(rejection_reasons, f"Rejected dividend reference that does not declare an action: {line_item_raw}")
                        rejection_items.append(_rejection_record(row=row, rejected_action_type=inferred, rejection_reason=reason))
                        continue
                    elif _is_authorized_share_capital(line_item_raw):
                        reason = "authorized share capital is not an issued share-capital action"
                        _append_unique(rejection_reasons, f"Rejected authorized share-capital reference: {line_item_raw}")
                        rejection_items.append(_rejection_record(row=row, rejected_action_type=inferred, rejection_reason=reason))
                        continue
                    elif "fair value" in lowered_line_item:
                        reason = "fair value rows are not face value changes"
                    _append_unique(rejection_reasons, f"Rejected {inferred} candidate: {line_item_raw}")
                    rejection_items.append(_rejection_record(row=row, rejected_action_type=inferred, rejection_reason=reason))
                continue
            if action_type in {"bonus_issue", "rights_issue", "preferential_issue", "qip", "buyback", "stock_split", "face_value_change", "share_capital_change"} and not _has_explicit_action_language(action_type, line_item_raw):
                reason = "explicit action language missing"
                _append_unique(rejection_reasons, f"Rejected {action_type} candidate without explicit action language: {line_item_raw}")
                rejection_items.append(_rejection_record(row=row, rejected_action_type=action_type, rejection_reason=reason))
                continue
            if _is_authorized_share_capital(line_item_raw):
                reason = "authorized share capital is not an issued share-capital action"
                _append_unique(rejection_reasons, f"Rejected authorized share-capital reference: {line_item_raw}")
                rejection_items.append(_rejection_record(row=row, rejected_action_type=action_type, rejection_reason=reason))
                continue
            selected_value = _select_value(row.get("values", []), target_year)
            unit_hint = str(selected_value.get("unit_hint", "") or "") if selected_value else ""
            raw_value = str(selected_value.get("value_raw", "") or "") if selected_value else ""
            numeric_value = _parse_numeric(raw_value) if selected_value else None
            lowered_line_item = line_item_raw.lower()
            value_type = _selected_value_type(selected_value, unit_hint, line_item_raw)
            action_subtype = _action_subtype(action_type, line_item_raw)
            column_context = _source_column_context(selected_value, value_type)

            amount_crore: Optional[float] = None
            amount_raised_crore: Optional[float] = None
            amount_utilised_crore: Optional[float] = None
            per_share_amount: Optional[float] = None
            shares_issued: Optional[float] = None
            warnings = [str(item) for item in row.get("warnings", [])]
            rejection_reason = ""

            if action_type in {"dividend", "final_dividend", "interim_dividend"} and "dividend income" in lowered_line_item:
                reason = "dividend income is not a corporate action"
                _append_unique(rejection_reasons, f"Rejected dividend reference that does not declare an action: {line_item_raw}")
                rejection_items.append(
                    _rejection_record(
                        row=row,
                        rejected_action_type=action_type,
                        rejection_reason=reason,
                        raw_value=raw_value,
                        detected_value_type=value_type,
                    )
                )
                continue

            if selected_value:
                selected_crore = selected_value.get("value_crore")
                is_per_share = any(token in lowered_line_item for token in _DIVIDEND_PER_SHARE_TOKENS)
                is_dividend_cash = any(token in lowered_line_item for token in _DIVIDEND_CASH_TOKENS)
                if action_type in {"dividend", "final_dividend", "interim_dividend"} and is_per_share:
                    per_share_amount = numeric_value
                elif action_type in {"dividend", "final_dividend", "interim_dividend"} and is_dividend_cash:
                    amount_crore = float(selected_crore) if isinstance(selected_crore, (int, float)) else numeric_value
                elif action_type in {"dividend", "final_dividend", "interim_dividend"}:
                    reason = "dividend row is neither explicit dividend cash outflow nor explicit dividend-per-share language"
                    _append_unique(rejection_reasons, f"Rejected ambiguous dividend row: {line_item_raw}")
                    rejection_items.append(
                        _rejection_record(
                            row=row,
                            rejected_action_type=action_type,
                            rejection_reason=reason,
                            raw_value=raw_value,
                            detected_value_type=value_type,
                        )
                    )
                    continue
                elif action_type in _AMOUNT_ACTIONS and value_type == "share_count":
                    amount_crore = None
                    if action_type in _SHARE_COUNT_ACTIONS:
                        shares_issued = numeric_value
                elif action_type == "face_value_change" and "fair value" in lowered_line_item:
                    reason = "fair value rows are not face value changes"
                    _append_unique(rejection_reasons, f"Rejected fair-value row for face value change: {line_item_raw}")
                    rejection_items.append(
                        _rejection_record(
                            row=row,
                            rejected_action_type=action_type,
                            rejection_reason=reason,
                            raw_value=raw_value,
                            detected_value_type=value_type,
                        )
                    )
                    continue
                elif action_type in _AMOUNT_ACTIONS and isinstance(selected_crore, (int, float)):
                    amount_crore = float(selected_crore)
                elif action_type in _AMOUNT_ACTIONS:
                    amount_crore = numeric_value

                if action_type in {"qip", "rights_issue", "preferential_issue"}:
                    if action_subtype.endswith("proceeds_utilization"):
                        amount_utilised_crore = amount_crore
                    else:
                        amount_raised_crore = amount_crore

                if amount_crore is not None:
                    amount_crore, rejection_reason = _sanitize_amount_against_scale(
                        action_type=action_type,
                        amount_crore=amount_crore,
                        normalized_payload=normalized_payload,
                        warnings=warnings,
                    )
                    if amount_raised_crore is not None:
                        amount_raised_crore = amount_crore
                    if amount_utilised_crore is not None:
                        amount_utilised_crore = amount_crore
                    if rejection_reason:
                        rejection_items.append(
                            _rejection_record(
                                row=row,
                                rejected_action_type=action_type,
                                rejection_reason=rejection_reason,
                                raw_value=raw_value,
                                detected_value_type=value_type,
                            )
                        )

            face_before, face_after = _parse_face_value_change(line_item_raw)
            if action_type == "face_value_change" and face_after is None:
                face_after = current_face_value

            shares_before = None
            shares_after = None
            if action_type in _SHARE_COUNT_ACTIONS:
                if value_type == "share_count":
                    shares_after = numeric_value
                    shares_issued = shares_issued if shares_issued is not None else numeric_value
                elif action_type == "weighted_avg_shares":
                    shares_after = weighted_avg
                elif action_type == "diluted_shares":
                    shares_after = diluted
                elif action_type == "share_capital_change":
                    shares_after = shares_outstanding
                elif action_type in {"qip", "preferential_issue", "rights_issue", "warrants", "esop_dilution"}:
                    shares_after = None
                elif action_type in _INCREASE_ACTIONS | _DECREASE_ACTIONS:
                    shares_after = shares_outstanding

            ratio = _parse_ratio(line_item_raw)
            if action_type in {"stock_split", "bonus_issue"} and not ratio:
                _append_unique(warnings, "ratio unclear")
            if action_type == "share_capital_change" and value_type != "share_count" and not any(token in lowered_line_item for token in _EXPLICIT_SHARE_CAPITAL_EVENT_TOKENS):
                reason = "share capital reference is not an explicit issued-share event"
                _append_unique(rejection_reasons, f"Rejected share_capital_change candidate without explicit issued-share event: {line_item_raw}")
                rejection_items.append(
                    _rejection_record(
                        row=row,
                        rejected_action_type=action_type,
                        rejection_reason=reason,
                        raw_value=raw_value,
                        detected_value_type=value_type,
                    )
                )
                continue

            if rejection_reason:
                _append_unique(rejection_reasons, rejection_reason)
                _append_unique(rejection_reasons, f"Rejected {action_type} candidate: {line_item_raw}")
                continue

            impact_on_share_count = _resolved_share_count_impact(
                action_type=action_type,
                action_subtype=action_subtype,
                shares_issued=shares_issued,
                shares_after=shares_after,
                warnings=warnings,
            )
            impact_on_eps_comparability = _resolved_eps_comparability(
                action_type=action_type,
                action_subtype=action_subtype,
                impact_on_share_count=impact_on_share_count,
            )

            actions.append(
                CorporateActionItem(
                    action_type=action_type,
                    year=year,
                    action_subtype=action_subtype,
                    ratio=ratio,
                    amount_crore=amount_crore,
                    amount_raised_crore=amount_raised_crore,
                    amount_utilised_crore=amount_utilised_crore,
                    per_share_amount=per_share_amount,
                    issue_price=_parse_issue_price(line_item_raw),
                    face_value=current_face_value,
                    face_value_before=face_before,
                    face_value_after=face_after,
                    shares_issued=shares_issued,
                    shares_before=shares_before,
                    shares_after=shares_after,
                    source_column_context=column_context,
                    value_type_used=value_type,
                    rejection_reason="",
                    impact_on_share_count=impact_on_share_count,
                    impact_on_eps_comparability=impact_on_eps_comparability,
                    source_line_item=line_item_raw,
                    source_page=row.get("page"),
                    source_artifact=str(row.get("source_artifact", "")),
                    confidence=str(row.get("confidence", "low") or "low"),
                    warnings=warnings,
                )
            )
    return actions, rejection_reasons, rejection_items


def _dedupe_actions(items: Iterable[CorporateActionItem]) -> List[CorporateActionItem]:
    deduped: Dict[Tuple[str, str, Optional[int]], CorporateActionItem] = {}
    for item in items:
        key = (item.action_type, item.source_line_item, item.source_page)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = item
            continue
        if len(item.warnings) < len(existing.warnings):
            deduped[key] = item
    return list(deduped.values())


def extract_corporate_actions(
    *,
    company: str,
    year: str,
    normalized_path: Path,
    raw_tables_path: Optional[Path] = None,
) -> CorporateActionsReport:
    if not normalized_path.exists():
        raise RuntimeError("corporate_actions requires normalized_fundamentals.json")

    normalized_payload = _load_json(normalized_path)
    if not isinstance(normalized_payload, dict):
        raise RuntimeError("corporate_actions requires normalized_fundamentals.json to contain an object")

    raw_payload = _load_json(raw_tables_path) if raw_tables_path is not None and raw_tables_path.exists() else None

    raw_actions, rejection_reasons, rejection_items = _build_from_raw(
        raw_payload=raw_payload,
        normalized_payload=normalized_payload,
        year=year,
    )
    actions = _dedupe_actions(
        [
            *_build_from_normalized(normalized_payload=normalized_payload, year=year),
            *raw_actions,
        ]
    )
    share_count_summary, comparability_warnings = build_share_count_summary(
        normalized_payload=normalized_payload,
        actions=actions,
    )

    warnings: List[str] = []
    limitations: List[str] = []
    if raw_payload is None:
        _append_unique(
            limitations,
            "raw_financial_tables.json missing or unreadable; corporate action extraction relied on normalized fundamentals only",
        )

    for item in actions:
        for warning in item.warnings:
            _append_unique(warnings, f"{item.action_type}: {warning}")

    report = CorporateActionsReport(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status="warning" if warnings or comparability_warnings or limitations else "pass",
        actions=actions,
        share_count_summary=share_count_summary,
        rejection_reasons=rejection_reasons,
        per_share_comparability_warnings=comparability_warnings,
        warnings=warnings,
        limitations=limitations,
    )
    errors = validate_corporate_actions_payload(report.to_dict())
    if errors:
        raise ValueError("Invalid corporate actions payload: " + "; ".join(errors))
    report._rejection_items = rejection_items  # type: ignore[attr-defined]
    return report


def write_corporate_actions(
    *,
    company: str,
    year: str,
    normalized_path: Path,
    output_path: Path,
    raw_tables_path: Optional[Path] = None,
) -> CorporateActionsReport:
    report = extract_corporate_actions(
        company=company,
        year=year,
        normalized_path=normalized_path,
        raw_tables_path=raw_tables_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    rejection_path = output_path.with_name("corporate_action_rejections.json")
    rejection_items = getattr(report, "_rejection_items", [])
    rejection_path.write_text(json.dumps(rejection_items, indent=2), encoding="utf-8")
    return report
