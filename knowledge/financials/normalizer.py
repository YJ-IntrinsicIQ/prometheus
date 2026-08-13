from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .basis import choose_preferred_basis
from .extraction_schema import FinancialExtractionResult
from .line_item_mapper import MappingMatch, map_line_item
from .mapping_registry import CANONICAL_SECTION_FIELDS
from .units import convert_to_crore


BASIS_ORDER = {"consolidated": 3, "standalone": 2, "unknown": 1}
CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1, "missing": 0}
SECTION_ORDER = list(CANONICAL_SECTION_FIELDS.keys())
SOURCE_PRIORITY = {
    "primary_profit_and_loss_statement": 5,
    "primary_balance_sheet_statement": 5,
    "primary_cash_flow_statement": 5,
    "share_capital_note": 4,
    "eps_note": 4,
    "dividend_note": 4,
    "shareholding_note": 4,
    "corporate_action_note": 4,
    "financial_note": 3,
    "statement_of_changes_in_equity": 2,
    "management_discussion_financial_summary": 1,
}

_SHARES_OUTSTANDING_ALLOWED_SECTION_TYPES = {
    "share_capital_note",
    "eps_note",
    "share_capital",
    "eps",
}

_SHARES_OUTSTANDING_ALLOWED_LABEL_TOKENS = (
    "number of shares outstanding",
    "number of equity shares outstanding",
    "number of equity shares",
    "issued equity shares",
    "subscribed equity shares",
    "paid up equity shares",
    "paid-up equity shares",
    "issued subscribed and paid up equity shares",
    "issued subscribed and paid-up equity shares",
    "issued subscribed and fully paid up equity shares",
    "issued subscribed and fully paid-up equity shares",
    "issued subscribed paid up equity shares",
    "issued subscribed paid-up equity shares",
    "subscribed and paid up equity shares",
    "subscribed and paid-up equity shares",
    "subscribed paid up equity shares",
    "subscribed paid-up equity shares",
)

_WEIGHTED_AVG_SHARES_ALLOWED_SECTION_TYPES = {
    "eps_note",
    "eps",
}

_WEIGHTED_AVG_SHARES_ALLOWED_LABEL_TOKENS = (
    "weighted average number of equity shares",
    "weighted average shares outstanding",
    "weighted average number of shares used in eps calculation",
    "weighted average number of shares used for eps",
    "weighted average number of shares",
)

_DILUTED_SHARES_ALLOWED_SECTION_TYPES = {
    "eps_note",
    "eps",
}

_DILUTED_SHARES_ALLOWED_LABEL_TOKENS = (
    "weighted average number of diluted equity shares",
    "diluted weighted average number of equity shares",
    "diluted weighted average shares",
    "number of shares used for diluted eps",
    "number of shares used in diluted eps calculation",
)

_FACE_VALUE_ALLOWED_SECTION_TYPES = {
    "share_capital_note",
    "eps_note",
    "share_capital",
    "eps",
}

_FACE_VALUE_ALLOWED_LABEL_TOKENS = (
    "face value",
    "nominal value",
    "nominal value of equity shares",
    "face value of equity shares",
)

_FACE_VALUE_DISALLOWED_ROW_TOKENS = (
    "authorised",
    "authorized",
    "issued",
    "subscribed",
    "paid up",
    "paid-up",
    "fully paid",
    "opening balance",
    "closing balance",
    "numbers amount",
)


def _empty_entry(field_name: str) -> Dict[str, Any]:
    return {
        "canonical_field": field_name,
        "value_type": "",
        "value_crore": None,
        "value_original": "",
        "unit_original": "",
        "basis": "unknown",
        "period": "",
        "source_line_item": "",
        "source_page": None,
        "source_artifact": "",
        "confidence": "missing",
        "warnings": [],
        "derived": False,
        "formula": "",
        "inputs_used": {},
        "value_per_share": None,
        "value_shares": None,
        "crore_shares": None,
        "raw_number": None,
        "capex_abs_crore": None,
        "sign_convention": "",
        "current": {},
        "comparatives": [],
        "source_value_type": "",
        "source_raw_number": None,
        "statement_type": "",
        "source_section_type": "",
        "table_confidence": "missing",
        "is_primary_statement": False,
    }


def _is_explicit_fcf_source(line_item_raw: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(line_item_raw or "").lower()).strip()
    if normalized in {"fcf", "free cash flow", "free cashflow"}:
        return True
    return "fcf" in normalized.split()


def _capex_sign_convention(value_crore: Optional[float]) -> str:
    if not isinstance(value_crore, (int, float)):
        return ""
    return "cash_flow_signed" if value_crore <= 0 else "positive_outflow"


def _normalize_label(text: str) -> str:
    normalized = str(text or "").lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


_PAYABLES_MSME_TOKENS = (
    "total outstanding dues of micro enterprises and small enterprises",
)

_PAYABLES_OTHER_TOKENS = (
    "total outstanding dues of creditors other than micro enterprises and small enterprises",
)

_PAYABLES_DIRECT_TOKENS = (
    "trade payables",
    "total trade payables",
    "accounts payable",
    "supplier payables",
    "dues to suppliers",
    "creditors for goods services",
    "creditors for goods and services",
)


def _empty_section_map() -> Dict[str, Dict[str, Dict[str, Any]]]:
    return {
        section_name: {field_name: _empty_entry(field_name) for field_name in field_names}
        for section_name, field_names in CANONICAL_SECTION_FIELDS.items()
    }


def _entry_has_value(entry: Dict[str, Any]) -> bool:
    if not isinstance(entry, dict):
        return False
    if isinstance(entry.get("value_crore"), (int, float)):
        return True
    if isinstance(entry.get("value_per_share"), (int, float)):
        return True
    if isinstance(entry.get("value_shares"), (int, float)):
        return True
    return entry.get("value_original") not in (None, "", [])


def _build_preferred_sections(
    *,
    basis_views: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]],
    preferred_basis: str,
) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], List[str], List[Dict[str, Any]]]:
    preferred_sections = _empty_section_map()
    basis_warnings: List[str] = []
    selection_records: List[Dict[str, Any]] = []

    for section_name, field_names in CANONICAL_SECTION_FIELDS.items():
        for field_name in field_names:
            preferred_entry = basis_views.get(preferred_basis, {}).get(section_name, {}).get(field_name, _empty_entry(field_name))
            selected_entry = preferred_entry
            selected_basis = preferred_basis if _entry_has_value(preferred_entry) else ""

            if not _entry_has_value(selected_entry):
                unknown_entry = basis_views.get("unknown", {}).get(section_name, {}).get(field_name, _empty_entry(field_name))
                if _entry_has_value(unknown_entry):
                    selected_entry = unknown_entry
                    selected_basis = "unknown"
                    basis_warnings.append(
                        f"{section_name}.{field_name} fell back to unknown basis because preferred {preferred_basis} evidence was unavailable"
                    )

            if (
                not _entry_has_value(selected_entry)
                and preferred_basis in {"consolidated", "standalone"}
            ):
                alternate_basis = "standalone" if preferred_basis == "consolidated" else "consolidated"
                alternate_entry = basis_views.get(alternate_basis, {}).get(section_name, {}).get(field_name, _empty_entry(field_name))
                if _entry_has_value(alternate_entry):
                    if section_name == "cash_flow":
                        selected_entry = alternate_entry
                        selected_basis = alternate_basis
                        basis_warnings.append(
                            f"{section_name}.{field_name} is available only in {alternate_basis} basis and was promoted into preferred {preferred_basis} view"
                        )
                    else:
                        basis_warnings.append(
                            f"{section_name}.{field_name} is available only in {alternate_basis} basis and was not promoted into preferred {preferred_basis} view"
                        )

            preferred_sections[section_name][field_name] = selected_entry
            available_in = [
                basis
                for basis in ("consolidated", "standalone", "unknown")
                if _entry_has_value(basis_views.get(basis, {}).get(section_name, {}).get(field_name, {}))
            ]
            selection_records.append(
                {
                    "field": f"{section_name}.{field_name}",
                    "selected_basis": selected_basis or "missing",
                    "available_in": available_in,
                }
            )

    deduped_warnings: List[str] = []
    for warning in basis_warnings:
        if warning not in deduped_warnings:
            deduped_warnings.append(warning)
    return preferred_sections, deduped_warnings, selection_records


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_raw_financials(path: Path) -> FinancialExtractionResult:
    return FinancialExtractionResult.from_dict(_load_json(path))


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
    if lowered.startswith("value_") or "period_column_unresolved" in lowered:
        return 0
    score = 1
    if target_year and target_year in lowered:
        score += 5
    if target_year and f"fy{target_year[-2:]}" in lowered:
        score += 5
    if "march 31" in lowered or "31 march" in lowered:
        score += 1
    return score


def _select_value(values: List[Dict[str, Any]], target_year: str) -> Optional[Dict[str, Any]]:
    resolved_values = [
        item
        for item in values
        if _period_match_score(str(item.get("period", "")), target_year) > 0
    ]
    if not resolved_values:
        return None
    ranked = sorted(
        resolved_values,
        key=lambda item: (
            -_period_match_score(str(item.get("period", "")), target_year),
            resolved_values.index(item),
        ),
    )
    return ranked[0]


def _ranked_values(values: List[Dict[str, Any]], target_year: str) -> List[Dict[str, Any]]:
    resolved_values = [
        item
        for item in values
        if _period_match_score(str(item.get("period", "")), target_year) > 0
    ]
    return sorted(
        resolved_values,
        key=lambda item: (
            -_period_match_score(str(item.get("period", "")), target_year),
            resolved_values.index(item),
        ),
    )


def _should_keep_value_crore(section_name: str, field_name: str, unit_original: str) -> bool:
    if section_name in {"shareholding_pattern"}:
        return False
    if section_name == "share_data":
        return field_name not in {
            "face_value",
            "shares_outstanding",
            "weighted_avg_shares",
            "diluted_shares",
            "book_value_per_share",
        }
    if section_name == "profit_and_loss" and field_name in {"eps_basic", "eps_diluted"}:
        return False
    if "%" in unit_original:
        return False
    return True


def _parse_numeric(raw_value: Any) -> Optional[float]:
    raw = str(raw_value or "").strip().replace(",", "")
    if not raw:
        return None
    negative = raw.startswith("(") or raw.startswith("[") or raw.startswith("-")
    raw = raw.strip("()[]")
    if raw.startswith("-"):
        raw = raw[1:]
    raw = raw.rstrip("%")
    try:
        number = float(raw)
    except ValueError:
        return None
    return -number if negative else number


def _clean_unit_for_field(*, field_name: str, selected_value: Dict[str, Any], line_item_raw: str) -> str:
    unit_original = str(selected_value.get("unit_hint") or "").strip()
    lowered_label = str(line_item_raw or "").lower()
    if field_name in {"eps_basic", "eps_diluted", "face_value", "book_value_per_share", "tangible_book_value_per_share"}:
        if "per share" in lowered_label or "face value" in lowered_label or "nominal value" in lowered_label:
            return "INR per share"
        return "INR per share"
    if field_name in {"shares_outstanding", "weighted_avg_shares", "diluted_shares"}:
        return "shares"
    return unit_original


def _normalized_value_type(field_name: str, extracted_value_type: str) -> str:
    if field_name in {"eps_basic", "eps_diluted", "face_value", "book_value_per_share", "tangible_book_value_per_share"}:
        return "per_share"
    if field_name in {"shares_outstanding", "weighted_avg_shares", "diluted_shares"}:
        return "share_count"
    if extracted_value_type:
        return extracted_value_type
    return "monetary"


def _shares_outstanding_source_allowed(row: Dict[str, Any]) -> bool:
    source_section_type = str(row.get("source_section_type", "") or "")
    normalized_line_item = _normalize_label(row.get("line_item_raw", ""))
    if "authorised" in normalized_line_item or "authorized" in normalized_line_item:
        return False
    if source_section_type not in _SHARES_OUTSTANDING_ALLOWED_SECTION_TYPES:
        return False
    return any(token in normalized_line_item for token in _SHARES_OUTSTANDING_ALLOWED_LABEL_TOKENS)


def _weighted_avg_shares_source_allowed(row: Dict[str, Any]) -> bool:
    source_section_type = str(row.get("source_section_type", "") or "")
    normalized_line_item = _normalize_label(row.get("line_item_raw", ""))
    if source_section_type not in _WEIGHTED_AVG_SHARES_ALLOWED_SECTION_TYPES:
        return False
    return any(token in normalized_line_item for token in _WEIGHTED_AVG_SHARES_ALLOWED_LABEL_TOKENS)


def _diluted_shares_source_allowed(row: Dict[str, Any]) -> bool:
    source_section_type = str(row.get("source_section_type", "") or "")
    normalized_line_item = _normalize_label(row.get("line_item_raw", ""))
    if source_section_type not in _DILUTED_SHARES_ALLOWED_SECTION_TYPES:
        return False
    return any(token in normalized_line_item for token in _DILUTED_SHARES_ALLOWED_LABEL_TOKENS)


def _face_value_source_allowed(row: Dict[str, Any]) -> bool:
    source_section_type = str(row.get("source_section_type", "") or "")
    normalized_line_item = _normalize_label(row.get("line_item_raw", ""))
    if source_section_type not in _FACE_VALUE_ALLOWED_SECTION_TYPES:
        return False
    if any(token in normalized_line_item for token in ("fair value", "market value", "nav", "investment value")):
        return False
    if re.search(r"equity shares of r(?:s|e)\s*\d+(?:\.\d+)? each", normalized_line_item):
        return not any(token in normalized_line_item for token in _FACE_VALUE_DISALLOWED_ROW_TOKENS)
    if any(token in normalized_line_item for token in _FACE_VALUE_ALLOWED_LABEL_TOKENS):
        return True
    return False


def _current_and_comparatives(values: List[Dict[str, Any]], target_year: str) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    ranked = _ranked_values(values, target_year)
    if not ranked:
        return None, []
    return ranked[0], ranked[1:]


def _filtered_values_for_field(
    field_name: str,
    values: List[Dict[str, Any]],
    *,
    line_item_raw: str = "",
    table_type: str = "",
) -> List[Dict[str, Any]]:
    if field_name in {"eps_basic", "eps_diluted", "face_value", "book_value_per_share", "tangible_book_value_per_share"}:
        filtered = [item for item in values if str(item.get("value_type", "") or "") == "per_share"]
        return filtered or values
    if field_name in {"shares_outstanding", "weighted_avg_shares", "diluted_shares"}:
        filtered = [item for item in values if str(item.get("value_type", "") or "") == "share_count"]
        if filtered:
            return filtered
        unit_filtered = [item for item in values if str(item.get("unit_hint", "") or "").lower() == "shares"]
        return unit_filtered or filtered
    if field_name in {"promoter_holding", "pledged_promoter_holding", "fii_holding", "dii_holding", "mutual_fund_holding", "public_holding"}:
        filtered = [item for item in values if str(item.get("value_type", "") or "") == "percentage"]
        return filtered or values
    monetary_values = [item for item in values if str(item.get("value_type", "") or "") == "monetary"]
    if monetary_values:
        return monetary_values
    if field_name == "revenue":
        normalized_line_item = _normalize_label(line_item_raw)
        if not any(
            token in normalized_line_item
            for token in ("revenue from operations", "revenue", "income from operations", "total operating revenue")
        ):
            return []
        revenue_like_values = [
            item
            for item in values
            if _parse_numeric(item.get("value_raw")) is not None
            and (
                str(item.get("currency_hint", "") or "").upper() in {"INR", "₹", "RS", "R", "INR."}
                or not str(item.get("unit_hint", "") or "").strip()
                or str(item.get("unit_hint", "") or "").strip().lower() in {"cr", "crore", "crores"}
            )
        ]
        return revenue_like_values or values
    return monetary_values


def _safe_value_crore(
    *,
    section_name: str,
    field_name: str,
    value_raw: str,
    unit_original: str,
    fallback_value_crore: Optional[float],
) -> Optional[float]:
    if not _should_keep_value_crore(section_name, field_name, unit_original):
        return None
    if fallback_value_crore is not None:
        return fallback_value_crore
    if not unit_original:
        return None
    cleaned = str(value_raw or "").strip().replace(",", "")
    negative = cleaned.startswith("(") or cleaned.startswith("[") or cleaned.startswith("-")
    cleaned = cleaned.strip("()[]")
    if cleaned.startswith("-"):
        cleaned = cleaned[1:]
    try:
        numeric = float(cleaned)
    except ValueError:
        return None
    if negative:
        numeric = -numeric
    try:
        return convert_to_crore(numeric, unit_original)
    except ValueError:
        return None


def _build_normalized_entry(
    *,
    section_name: str,
    field_name: str,
    row: Dict[str, Any],
    selected_value: Dict[str, Any],
    match: MappingMatch,
    comparative_values: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    unit_original = _clean_unit_for_field(
        field_name=field_name,
        selected_value=selected_value,
        line_item_raw=str(row.get("line_item_raw", "")),
    )
    numeric_original = _parse_numeric(selected_value.get("value_raw"))
    extracted_value_type = str(selected_value.get("value_type", "") or "")
    normalized_value_type = _normalized_value_type(field_name, extracted_value_type)
    value_crore = _safe_value_crore(
        section_name=section_name,
        field_name=field_name,
        value_raw=str(selected_value.get("value_raw", "")),
        unit_original=unit_original,
        fallback_value_crore=selected_value.get("value_crore"),
    )
    entry = {
        "canonical_field": field_name,
        "value_type": normalized_value_type,
        "value_crore": value_crore,
        "value_original": str(selected_value.get("value_raw", "")),
        "unit_original": unit_original,
        "basis": str(row.get("basis", "unknown")),
        "period": str(selected_value.get("period", "")),
        "source_line_item": str(row.get("line_item_raw", "")),
        "source_page": row.get("page"),
        "source_artifact": str(row.get("source_artifact", "")),
        "confidence": match.confidence,
        "warnings": [str(item) for item in row.get("warnings", [])],
        "derived": False,
        "formula": "",
        "inputs_used": {},
        "value_per_share": numeric_original
        if field_name in {"eps_basic", "eps_diluted", "face_value", "book_value_per_share", "tangible_book_value_per_share"}
        else None,
        "value_shares": numeric_original
        if field_name in {"shares_outstanding", "weighted_avg_shares", "diluted_shares"}
        else None,
        "crore_shares": round(numeric_original / 10_000_000, 6)
        if field_name in {"shares_outstanding", "weighted_avg_shares", "diluted_shares"} and numeric_original is not None
        else None,
        "raw_number": numeric_original
        if field_name in {"shares_outstanding", "weighted_avg_shares", "diluted_shares"}
        else None,
        "capex_abs_crore": abs(value_crore) if field_name == "capex" and isinstance(value_crore, (int, float)) else None,
        "sign_convention": _capex_sign_convention(value_crore) if field_name == "capex" else "",
        "source_section_type": str(row.get("source_section_type", "")),
        "statement_type": str(row.get("statement_type", "")),
        "table_confidence": str(row.get("table_confidence", row.get("confidence", "low"))),
        "is_primary_statement": bool(row.get("is_primary_statement", False)),
        "source_value_type": normalized_value_type,
        "source_raw_number": numeric_original if numeric_original is not None else selected_value.get("raw_number"),
    }
    current_payload = {
        "period": entry["period"],
        "value_type": entry["value_type"],
        "value_original": entry["value_original"],
        "value_crore": entry["value_crore"],
        "source_page": entry["source_page"],
        "source_artifact": entry["source_artifact"],
        "confidence": entry["confidence"],
        "warnings": list(entry["warnings"]),
    }
    if entry["value_per_share"] is not None:
        current_payload["value_per_share"] = entry["value_per_share"]
    if entry["value_shares"] is not None:
        current_payload["value_shares"] = entry["value_shares"]
        current_payload["crore_shares"] = entry["crore_shares"]
        current_payload["raw_number"] = entry["raw_number"]
    if field_name == "capex":
        current_payload["capex_abs_crore"] = entry["capex_abs_crore"]
        current_payload["sign_convention"] = entry["sign_convention"]
    entry["current"] = current_payload
    entry["comparatives"] = []
    for comparative in comparative_values or []:
        comparative_numeric = _parse_numeric(comparative.get("value_raw"))
        comparative_entry = {
            "period": str(comparative.get("period", "")),
            "value_type": normalized_value_type,
            "value_original": str(comparative.get("value_raw", "")),
            "value_crore": _safe_value_crore(
                section_name=section_name,
                field_name=field_name,
                value_raw=str(comparative.get("value_raw", "")),
                unit_original=unit_original,
                fallback_value_crore=comparative.get("value_crore"),
            ),
            "source_page": row.get("page"),
            "source_artifact": str(row.get("source_artifact", "")),
            "confidence": match.confidence,
            "warnings": [str(item) for item in row.get("warnings", [])],
        }
        if field_name in {"eps_basic", "eps_diluted", "face_value", "book_value_per_share", "tangible_book_value_per_share"}:
            comparative_entry["value_per_share"] = comparative_numeric
        if field_name in {"shares_outstanding", "weighted_avg_shares", "diluted_shares"}:
            comparative_entry["value_shares"] = comparative_numeric
            comparative_entry["crore_shares"] = round(comparative_numeric / 10_000_000, 6) if comparative_numeric is not None else None
            comparative_entry["raw_number"] = comparative_numeric
        if field_name == "capex":
            comparative_value_crore = comparative_entry.get("value_crore")
            comparative_entry["capex_abs_crore"] = (
                abs(comparative_value_crore) if isinstance(comparative_value_crore, (int, float)) else None
            )
            comparative_entry["sign_convention"] = _capex_sign_convention(comparative_value_crore)
        entry["comparatives"].append(comparative_entry)
    if not unit_original:
        entry["warnings"].append("unit unclear")
    if entry["current"]:
        entry["current"]["warnings"] = list(entry["warnings"])
    entry["comparatives"] = [
        item for item in entry["comparatives"] if item.get("period") and item.get("value_original") != ""
    ]
    return entry


def _entry_rank(entry: Dict[str, Any], target_year: str) -> Tuple[int, int, int, int, int, int]:
    tax_specificity = 0
    if (
        str(entry.get("canonical_field", "") or "") == "tax"
        and str(entry.get("statement_type", "") or "") == "profit_and_loss"
    ):
        normalized_line_item = _normalize_label(entry.get("source_line_item", ""))
        if any(
            token in normalized_line_item
            for token in (
                "total tax expense",
                "total income tax expense",
                "tax expense recognised",
                "tax expense recognized",
            )
        ):
            tax_specificity = 3
        elif "income tax expense" in normalized_line_item:
            tax_specificity = 2
        elif "current tax" in normalized_line_item:
            tax_specificity = 1
    return (
        1 if entry.get("is_primary_statement") else 0,
        SOURCE_PRIORITY.get(str(entry.get("source_section_type", "")), 0),
        BASIS_ORDER.get(entry.get("basis", "unknown"), 0),
        tax_specificity,
        _period_match_score(str(entry.get("period", "")), target_year),
        CONFIDENCE_ORDER.get(str(entry.get("table_confidence", entry.get("confidence", "low"))), 0),
    )


def _choose_best(entries: Iterable[Dict[str, Any]], target_year: str) -> Dict[str, Any]:
    return max(entries, key=lambda item: _entry_rank(item, target_year))


def _append_if_missing(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _choose_entry_for_period(entries: List[Dict[str, Any]], period: str) -> Optional[Dict[str, Any]]:
    for entry in entries:
        if str(entry.get("period", "")) == str(period):
            return entry
    return None


def _payables_component_kind(source_line_item: str) -> str:
    normalized = _normalize_label(source_line_item)
    if any(token in normalized for token in _PAYABLES_MSME_TOKENS):
        return "msme_trade_payables"
    if any(token in normalized for token in _PAYABLES_OTHER_TOKENS):
        return "other_trade_payables"
    if any(token in normalized for token in _PAYABLES_DIRECT_TOKENS):
        return "direct_trade_payables"
    return ""


def _aggregate_payables_candidates(
    candidates: Dict[Tuple[str, str, str], List[Dict[str, Any]]],
    target_year: str,
) -> None:
    section_name = "balance_sheet"
    field_name = "payables"
    for basis in ("consolidated", "standalone", "unknown"):
        entries = candidates.get((section_name, field_name, basis), [])
        if not entries:
            continue
        msme_entries = [entry for entry in entries if _payables_component_kind(entry.get("source_line_item", "")) == "msme_trade_payables"]
        other_entries = [entry for entry in entries if _payables_component_kind(entry.get("source_line_item", "")) == "other_trade_payables"]
        if not msme_entries or not other_entries:
            continue

        msme_entry = _choose_best(msme_entries, target_year)
        other_entry = _choose_best(other_entries, target_year)
        msme_value = msme_entry.get("value_crore")
        other_value = other_entry.get("value_crore")
        if not isinstance(msme_value, (int, float)) or not isinstance(other_value, (int, float)):
            continue

        aggregated = _empty_entry(field_name)
        aggregated.update(
            {
                "value_type": "monetary",
                "value_crore": round(float(msme_value) + float(other_value), 4),
                "value_original": f"{float(msme_value) + float(other_value):.2f}",
                "unit_original": msme_entry.get("unit_original") or other_entry.get("unit_original") or "crores",
                "basis": basis,
                "period": str(msme_entry.get("period") or other_entry.get("period") or ""),
                "source_line_item": "derived:trade_payables",
                "source_page": msme_entry.get("source_page") or other_entry.get("source_page"),
                "source_artifact": str(msme_entry.get("source_artifact") or other_entry.get("source_artifact") or ""),
                "confidence": "medium",
                "warnings": [],
                "derived": True,
                "formula": "msme_trade_payables + other_trade_payables",
                "inputs_used": {
                    "msme_trade_payables": msme_value,
                    "other_trade_payables": other_value,
                    "component_source_line_items": [
                        msme_entry.get("source_line_item", ""),
                        other_entry.get("source_line_item", ""),
                    ],
                    "component_source_artifacts": [
                        item
                        for item in [msme_entry.get("source_artifact", ""), other_entry.get("source_artifact", "")]
                        if item
                    ],
                    "component_source_pages": [
                        item
                        for item in [msme_entry.get("source_page"), other_entry.get("source_page")]
                        if item is not None
                    ],
                },
                "source_section_type": str(msme_entry.get("source_section_type") or other_entry.get("source_section_type") or ""),
                "statement_type": "balance_sheet",
                "table_confidence": "medium",
                "is_primary_statement": bool(msme_entry.get("is_primary_statement") or other_entry.get("is_primary_statement")),
                "source_value_type": "monetary",
                "source_raw_number": None,
            }
        )
        aggregated["current"] = {
            "period": aggregated["period"],
            "value_type": "monetary",
            "value_original": aggregated["value_original"],
            "value_crore": aggregated["value_crore"],
            "source_page": aggregated["source_page"],
            "source_artifact": aggregated["source_artifact"],
            "confidence": aggregated["confidence"],
            "warnings": [],
        }
        comparatives: List[Dict[str, Any]] = []
        for msme_comparative in msme_entry.get("comparatives", []):
            period = str(msme_comparative.get("period", ""))
            if not period:
                continue
            other_comparative = _choose_entry_for_period(other_entry.get("comparatives", []), period)
            if other_comparative is None:
                continue
            left = msme_comparative.get("value_crore")
            right = other_comparative.get("value_crore")
            if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                continue
            total = round(float(left) + float(right), 4)
            comparatives.append(
                {
                    "period": period,
                    "value_type": "monetary",
                    "value_original": f"{total:.2f}",
                    "value_crore": total,
                    "source_page": msme_comparative.get("source_page") or other_comparative.get("source_page"),
                    "source_artifact": msme_comparative.get("source_artifact") or other_comparative.get("source_artifact"),
                    "confidence": "medium",
                    "warnings": [],
                }
            )
        aggregated["comparatives"] = comparatives
        retained_entries = [
            entry
            for entry in entries
            if _payables_component_kind(entry.get("source_line_item", "")) == "direct_trade_payables"
        ]
        retained_entries.append(aggregated)
        candidates[(section_name, field_name, basis)] = retained_entries


def _derived_entry(
    *,
    field_name: str,
    current_value: float,
    period: str,
    basis: str,
    source_page: Any,
    source_artifact: str,
    formula: str,
    inputs_used: Dict[str, Any],
    comparatives: List[Dict[str, Any]],
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    entry = _empty_entry(field_name)
    entry.update(
        {
            "value_crore": round(current_value, 4),
            "value_original": f"{current_value:.2f}",
            "unit_original": "crores",
            "basis": basis,
            "period": period,
            "source_line_item": f"derived:{field_name}",
            "source_page": source_page,
            "source_artifact": source_artifact,
            "confidence": "medium",
            "warnings": list(warnings or []),
            "derived": True,
            "formula": formula,
            "inputs_used": dict(inputs_used),
        }
    )
    entry["current"] = {
        "period": period,
        "value_original": entry["value_original"],
        "value_crore": entry["value_crore"],
        "source_page": source_page,
        "source_artifact": source_artifact,
        "confidence": "medium",
        "warnings": list(entry["warnings"]),
    }
    entry["comparatives"] = comparatives
    return entry


def _derive_fcf_value(cfo: float, capex: float, *, sign_convention: str = "") -> Tuple[float, List[str]]:
    warnings: List[str] = []
    if sign_convention == "positive_outflow":
        warnings.append("capex treated as positive outflow during FCF derivation")
        return cfo - capex, warnings
    if capex <= 0 or sign_convention == "cash_flow_signed":
        return cfo + capex, warnings
    warnings.append("capex treated as positive outflow during FCF derivation")
    return cfo - capex, warnings


def _build_derived_comparatives(
    *,
    left_entry: Dict[str, Any],
    right_entry: Dict[str, Any],
    operator: str,
) -> List[Dict[str, Any]]:
    comparatives: List[Dict[str, Any]] = []
    for comparative in left_entry.get("comparatives", []):
        period = str(comparative.get("period", ""))
        if not period:
            continue
        right_comparative = _choose_entry_for_period(right_entry.get("comparatives", []), period)
        if right_comparative is None:
            continue
        left_value = comparative.get("value_crore")
        right_value = right_comparative.get("value_crore")
        if not isinstance(left_value, (int, float)) or not isinstance(right_value, (int, float)):
            continue
        value = left_value + right_value if operator == "+" else left_value - right_value
        comparatives.append(
            {
                "period": period,
                "value_original": f"{value:.2f}",
                "value_crore": round(value, 4),
                "source_page": comparative.get("source_page") or right_comparative.get("source_page"),
                "source_artifact": comparative.get("source_artifact") or right_comparative.get("source_artifact"),
                "confidence": "medium",
                "warnings": [],
            }
        )
    return comparatives


def _apply_derived_fallbacks(preferred_sections: Dict[str, Any]) -> None:
    pnl = preferred_sections["profit_and_loss"]
    balance_sheet = preferred_sections["balance_sheet"]
    cash_flow = preferred_sections["cash_flow"]
    pbt_entry = pnl["pbt"]
    finance_entry = pnl["finance_cost"]
    ebit_entry = pnl["ebit"]
    depreciation_entry = pnl["depreciation"]
    ebitda_entry = pnl["ebitda"]
    cfo_entry = cash_flow["cfo"]
    capex_entry = cash_flow["capex"]
    fcf_entry = cash_flow["fcf"]

    net_worth_entry = balance_sheet["net_worth"]
    share_capital_entry = balance_sheet["equity_share_capital"]
    reserves_entry = balance_sheet["reserves"]
    if (
        net_worth_entry.get("value_crore") is None
        and isinstance(share_capital_entry.get("value_crore"), (int, float))
        and isinstance(reserves_entry.get("value_crore"), (int, float))
    ):
        balance_sheet["net_worth"] = _derived_entry(
            field_name="net_worth",
            current_value=float(share_capital_entry["value_crore"]) + float(reserves_entry["value_crore"]),
            period=str(share_capital_entry.get("period") or reserves_entry.get("period") or ""),
            basis=str(share_capital_entry.get("basis") or reserves_entry.get("basis") or "unknown"),
            source_page=share_capital_entry.get("source_page") or reserves_entry.get("source_page"),
            source_artifact=str(share_capital_entry.get("source_artifact") or reserves_entry.get("source_artifact") or ""),
            formula="equity_share_capital + reserves",
            inputs_used={
                "equity_share_capital": share_capital_entry.get("value_crore"),
                "reserves": reserves_entry.get("value_crore"),
            },
            comparatives=_build_derived_comparatives(
                left_entry=share_capital_entry,
                right_entry=reserves_entry,
                operator="+",
            ),
        )

    total_assets_entry = balance_sheet["total_assets"]
    total_liabilities_entry = balance_sheet["total_liabilities"]
    net_worth_entry = balance_sheet["net_worth"]
    if (
        total_liabilities_entry.get("value_crore") is None
        and isinstance(total_assets_entry.get("value_crore"), (int, float))
        and isinstance(net_worth_entry.get("value_crore"), (int, float))
        and float(total_assets_entry["value_crore"]) >= float(net_worth_entry["value_crore"])
    ):
        balance_sheet["total_liabilities"] = _derived_entry(
            field_name="total_liabilities",
            current_value=float(total_assets_entry["value_crore"]) - float(net_worth_entry["value_crore"]),
            period=str(total_assets_entry.get("period") or net_worth_entry.get("period") or ""),
            basis=str(total_assets_entry.get("basis") or net_worth_entry.get("basis") or "unknown"),
            source_page=total_assets_entry.get("source_page") or net_worth_entry.get("source_page"),
            source_artifact=str(total_assets_entry.get("source_artifact") or net_worth_entry.get("source_artifact") or ""),
            formula="total_assets - net_worth",
            inputs_used={
                "total_assets": total_assets_entry.get("value_crore"),
                "net_worth": net_worth_entry.get("value_crore"),
            },
            comparatives=_build_derived_comparatives(
                left_entry=total_assets_entry,
                right_entry=net_worth_entry,
                operator="-",
            ),
            warnings=["total liabilities derived from the balance-sheet equation"],
        )

    if ebit_entry.get("value_crore") is None and isinstance(pbt_entry.get("value_crore"), (int, float)) and isinstance(finance_entry.get("value_crore"), (int, float)):
        current_value = float(pbt_entry["value_crore"]) + float(finance_entry["value_crore"])
        pnl["ebit"] = _derived_entry(
            field_name="ebit",
            current_value=current_value,
            period=str(pbt_entry.get("period") or finance_entry.get("period") or ""),
            basis=str(pbt_entry.get("basis") or finance_entry.get("basis") or "unknown"),
            source_page=pbt_entry.get("source_page") or finance_entry.get("source_page"),
            source_artifact=str(pbt_entry.get("source_artifact") or finance_entry.get("source_artifact") or ""),
            formula="pbt + finance_cost",
            inputs_used={
                "pbt": pbt_entry.get("value_crore"),
                "finance_cost": finance_entry.get("value_crore"),
            },
            comparatives=_build_derived_comparatives(left_entry=pbt_entry, right_entry=finance_entry, operator="+"),
        )
        ebit_entry = pnl["ebit"]

    if ebitda_entry.get("value_crore") is None and isinstance(ebit_entry.get("value_crore"), (int, float)) and isinstance(depreciation_entry.get("value_crore"), (int, float)):
        current_value = float(ebit_entry["value_crore"]) + float(depreciation_entry["value_crore"])
        pnl["ebitda"] = _derived_entry(
            field_name="ebitda",
            current_value=current_value,
            period=str(ebit_entry.get("period") or depreciation_entry.get("period") or ""),
            basis=str(ebit_entry.get("basis") or depreciation_entry.get("basis") or "unknown"),
            source_page=ebit_entry.get("source_page") or depreciation_entry.get("source_page"),
            source_artifact=str(ebit_entry.get("source_artifact") or depreciation_entry.get("source_artifact") or ""),
            formula="ebit + depreciation",
            inputs_used={
                "ebit": ebit_entry.get("value_crore"),
                "depreciation": depreciation_entry.get("value_crore"),
            },
            comparatives=_build_derived_comparatives(left_entry=ebit_entry, right_entry=depreciation_entry, operator="+"),
        )

    if (
        fcf_entry.get("value_crore") is None
        and isinstance(cfo_entry.get("value_crore"), (int, float))
        and isinstance(capex_entry.get("value_crore"), (int, float))
    ):
        current_value, current_warnings = _derive_fcf_value(
            float(cfo_entry["value_crore"]),
            float(capex_entry["value_crore"]),
            sign_convention=str(capex_entry.get("sign_convention", "") or ""),
        )
        comparatives: List[Dict[str, Any]] = []
        for comparative in cfo_entry.get("comparatives", []):
            period = str(comparative.get("period", ""))
            if not period:
                continue
            capex_comparative = _choose_entry_for_period(capex_entry.get("comparatives", []), period)
            if capex_comparative is None:
                continue
            cfo_value = comparative.get("value_crore")
            capex_value = capex_comparative.get("value_crore")
            if not isinstance(cfo_value, (int, float)) or not isinstance(capex_value, (int, float)):
                continue
            capex_sign_convention = str(capex_comparative.get("sign_convention", "") or "")
            value, comparative_warnings = _derive_fcf_value(
                float(cfo_value),
                float(capex_value),
                sign_convention=capex_sign_convention,
            )
            comparatives.append(
                {
                    "period": period,
                    "value_original": f"{value:.2f}",
                    "value_crore": round(value, 4),
                    "source_page": comparative.get("source_page") or capex_comparative.get("source_page"),
                    "source_artifact": comparative.get("source_artifact") or capex_comparative.get("source_artifact"),
                    "confidence": "medium",
                    "warnings": list(comparative_warnings),
                }
            )
        cash_flow["fcf"] = _derived_entry(
            field_name="fcf",
            current_value=current_value,
            period=str(cfo_entry.get("period") or capex_entry.get("period") or ""),
            basis=str(cfo_entry.get("basis") or capex_entry.get("basis") or "unknown"),
            source_page=cfo_entry.get("source_page") or capex_entry.get("source_page"),
            source_artifact=str(cfo_entry.get("source_artifact") or capex_entry.get("source_artifact") or ""),
            formula="cfo + capex (or cfo - capex when capex sign is positive outflow)",
            inputs_used={
                "cfo": cfo_entry.get("value_crore"),
                "capex": capex_entry.get("value_crore"),
                "capex_sign_convention": capex_entry.get("sign_convention"),
            },
            comparatives=comparatives,
            warnings=current_warnings,
        )


def _validate_normalized_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return ["normalized fundamentals payload must be an object"]
    if not payload.get("company"):
        errors.append("company is required")
    if not payload.get("year"):
        errors.append("year is required")
    if not payload.get("generated_at"):
        errors.append("generated_at is required")
    for section_name in SECTION_ORDER:
        section = payload.get(section_name)
        if not isinstance(section, dict):
            errors.append(f"{section_name} must be an object")
            continue
        for field_name in CANONICAL_SECTION_FIELDS[section_name]:
            entry = section.get(field_name)
            if not isinstance(entry, dict):
                errors.append(f"{section_name}.{field_name} must be an object")
                continue
            if entry.get("canonical_field") != field_name:
                errors.append(f"{section_name}.{field_name}.canonical_field must equal {field_name}")
    return errors


def normalize_financial_tables(*, company: str, year: str, raw_tables_path: Path) -> Dict[str, Any]:
    raw = _load_raw_financials(raw_tables_path)
    target_year = _fy_year_from_slug(year) or ""

    basis_views = {
        basis: _empty_section_map() for basis in ("consolidated", "standalone", "unknown")
    }
    candidates: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    unmapped_rows: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for table_type, rows in raw.tables.items():
        for row_obj in rows:
            row = row_obj.to_dict()
            matches = map_line_item(table_type=table_type, line_item_raw=row.get("line_item_raw", ""))
            row_values = row.get("values", [])
            row_selected_value, row_comparative_values = _current_and_comparatives(row_values, target_year)
            if row_selected_value is None:
                unmapped_rows.append(
                    {
                        "table_type": table_type,
                        "basis": row.get("basis", "unknown"),
                        "source_line_item": row.get("line_item_raw", ""),
                        "source_page": row.get("page"),
                        "source_artifact": row.get("source_artifact", ""),
                        "reason": "no_period_value_selected",
                    }
                )
                continue
            if not matches:
                unmapped_rows.append(
                    {
                        "table_type": table_type,
                        "basis": row.get("basis", "unknown"),
                        "source_line_item": row.get("line_item_raw", ""),
                        "source_page": row.get("page"),
                        "source_artifact": row.get("source_artifact", ""),
                        "period": row_selected_value.get("period", ""),
                        "value_original": row_selected_value.get("value_raw", ""),
                        "reason": "unmapped_line_item",
                    }
                )
                continue
            for match in matches:
                filtered_values = _filtered_values_for_field(
                    match.canonical_field,
                    row_values,
                    line_item_raw=row.get("line_item_raw", ""),
                    table_type=table_type,
                )
                selected_value, comparative_values = _current_and_comparatives(filtered_values, target_year)
                if selected_value is None:
                    unmapped_rows.append(
                        {
                            "table_type": table_type,
                            "basis": row.get("basis", "unknown"),
                            "source_line_item": row.get("line_item_raw", ""),
                            "source_page": row.get("page"),
                            "source_artifact": row.get("source_artifact", ""),
                            "reason": f"no_{match.canonical_field}_compatible_values",
                        }
                    )
                    continue
                if match.canonical_section == "cash_flow" and match.canonical_field == "fcf":
                    if not _is_explicit_fcf_source(row.get("line_item_raw", "")):
                        unmapped_rows.append(
                            {
                                "table_type": table_type,
                                "basis": row.get("basis", "unknown"),
                                "source_line_item": row.get("line_item_raw", ""),
                                "source_page": row.get("page"),
                                "source_artifact": row.get("source_artifact", ""),
                                "reason": "fcf_source_not_explicit",
                            }
                        )
                        continue
                    if (
                        selected_value.get("value_crore") is None
                        and _parse_numeric(selected_value.get("value_raw")) is None
                    ):
                        unmapped_rows.append(
                            {
                                "table_type": table_type,
                                "basis": row.get("basis", "unknown"),
                                "source_line_item": row.get("line_item_raw", ""),
                                "source_page": row.get("page"),
                                "source_artifact": row.get("source_artifact", ""),
                                "reason": "fcf_value_not_numeric",
                            }
                        )
                        continue
                if (
                    match.canonical_section == "share_data"
                    and match.canonical_field == "shares_outstanding"
                    and not _shares_outstanding_source_allowed(row)
                ):
                    continue
                if (
                    match.canonical_section == "share_data"
                    and match.canonical_field == "weighted_avg_shares"
                    and not _weighted_avg_shares_source_allowed(row)
                ):
                    continue
                if (
                    match.canonical_section == "share_data"
                    and match.canonical_field == "diluted_shares"
                    and not _diluted_shares_source_allowed(row)
                ):
                    continue
                if (
                    match.canonical_section == "share_data"
                    and match.canonical_field == "face_value"
                    and not _face_value_source_allowed(row)
                ):
                    continue
                entry = _build_normalized_entry(
                    section_name=match.canonical_section,
                    field_name=match.canonical_field,
                    row=row,
                    selected_value=selected_value,
                    match=match,
                    comparative_values=comparative_values,
                )
                basis = entry["basis"]
                candidates.setdefault((match.canonical_section, match.canonical_field, basis), []).append(entry)

    _aggregate_payables_candidates(candidates, target_year)

    for section_name, field_names in CANONICAL_SECTION_FIELDS.items():
        for field_name in field_names:
            for basis in ("consolidated", "standalone", "unknown"):
                field_entries = candidates.get((section_name, field_name, basis), [])
                if not field_entries:
                    continue
                best_entry = _choose_best(field_entries, target_year)
                basis_views[basis][section_name][field_name] = best_entry

    preferred_basis, basis_options_available, selected_basis_reason, basis_confidence = choose_preferred_basis(basis_views)
    preferred_sections, basis_selection_warnings, field_basis_selection = _build_preferred_sections(
        basis_views=basis_views,
        preferred_basis=preferred_basis,
    )

    _apply_derived_fallbacks(preferred_sections)

    basis_manifest = {
        "preferred_basis": preferred_basis,
        "basis_options_available": basis_options_available,
        "selected_basis_reason": selected_basis_reason,
        "basis_confidence": basis_confidence,
        "field_basis_selection": field_basis_selection,
        "basis_warnings": list(basis_selection_warnings),
    }

    payload: Dict[str, Any] = {
        "company": company,
        "year": year,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "preferred_basis": preferred_basis,
        "basis_options_available": basis_options_available,
        "selected_basis_reason": selected_basis_reason,
        "basis_confidence": basis_confidence,
        "basis_manifest": basis_manifest,
        "profit_and_loss": preferred_sections["profit_and_loss"],
        "balance_sheet": preferred_sections["balance_sheet"],
        "cash_flow": preferred_sections["cash_flow"],
        "share_data": preferred_sections["share_data"],
        "corporate_actions": preferred_sections["corporate_actions"],
        "shareholding_pattern": preferred_sections["shareholding_pattern"],
        "basis_views": basis_views,
        "unmapped_rows": unmapped_rows,
        "warnings": warnings,
        "limitations": [
            "Financial normalization maps raw extracted rows into canonical fundamentals without using LLMs or calculating ratios.",
            "Unmapped rows are preserved for review instead of being discarded silently.",
        ],
    }

    for warning in basis_selection_warnings:
        _append_if_missing(payload["warnings"], warning)

    if not payload["profit_and_loss"]["revenue"]["value_original"]:
        raise RuntimeError("normalized fundamentals missing required revenue")
    if not payload["profit_and_loss"]["pat"]["value_original"]:
        raise RuntimeError("normalized fundamentals missing required PAT")

    has_assets = bool(payload["balance_sheet"]["total_assets"]["value_original"])
    has_equity = bool(
        payload["balance_sheet"]["net_worth"]["value_original"]
        or payload["balance_sheet"]["equity_share_capital"]["value_original"]
    )
    has_liabilities = bool(payload["balance_sheet"]["total_liabilities"]["value_original"])
    if not (has_assets and has_equity and has_liabilities):
        raise RuntimeError("normalized fundamentals missing usable balance sheet assets/equity/liabilities data")

    if not payload["cash_flow"]["cfo"]["value_original"]:
        _append_if_missing(payload["warnings"], "CFO missing")
    if not payload["cash_flow"]["capex"]["value_original"]:
        _append_if_missing(payload["warnings"], "capex missing")
    if not payload["balance_sheet"]["total_debt"]["value_original"]:
        _append_if_missing(payload["warnings"], "debt unclear")
    if not payload["profit_and_loss"]["eps_basic"]["value_original"] and not payload["profit_and_loss"]["eps_diluted"]["value_original"]:
        _append_if_missing(payload["warnings"], "EPS missing")
    if not payload["share_data"]["shares_outstanding"]["value_original"] and not payload["share_data"]["weighted_avg_shares"]["value_original"]:
        _append_if_missing(payload["warnings"], "share count missing")
    if payload["preferred_basis"] == "unknown":
        _append_if_missing(payload["warnings"], "standalone/consolidated basis unclear")
    if unmapped_rows:
        _append_if_missing(payload["warnings"], "important rows unmapped")

    errors = _validate_normalized_payload(payload)
    if errors:
        raise ValueError("; ".join(errors))
    return payload


def write_normalized_fundamentals(
    *,
    company: str,
    year: str,
    raw_tables_path: Path,
    output_path: Path,
) -> Dict[str, Any]:
    payload = normalize_financial_tables(company=company, year=year, raw_tables_path=raw_tables_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
