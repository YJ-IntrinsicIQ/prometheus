from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .shareholding_schema import (
    OwnershipSummary,
    ShareholdingItem,
    ShareholdingReport,
    validate_shareholding_payload,
)


_NORMALIZED_FIELD_TO_CATEGORY = {
    "promoter_holding": "promoter_holding_percent",
    "pledged_promoter_holding": "pledged_promoter_holding_percent",
    "fii_holding": "fii_holding_percent",
    "dii_holding": "dii_holding_percent",
    "mutual_fund_holding": "mutual_fund_holding_percent",
    "public_holding": "public_holding_percent",
    "others": "others_percent",
}

_RAW_CATEGORY_KEYWORDS: Sequence[Tuple[str, Sequence[str]]] = (
    ("pledged_promoter_holding_percent", ("pledged promoter", "promoter pledged")),
    ("promoter_holding_percent", ("promoter and promoter group", "promoter group", "promoters", "promoter holding", "promoter shareholding")),
    ("mutual_fund_holding_percent", ("mutual fund", "mutual funds")),
    ("insurance_holding_percent", ("insurance companies", "insurance")),
    ("fii_holding_percent", ("foreign institutional investor", "foreign portfolio investor", "fii", "fpi", "foreign investors")),
    ("dii_holding_percent", ("domestic institutional investor", "dii", "financial institutions", "banks / financial institutions", "banks and financial institutions")),
    ("body_corporates_percent", ("body corporates", "body corporate", "corporates")),
    ("retail_holding_percent", ("retail", "individual shareholders", "individuals", "resident individuals")),
    ("public_holding_percent", ("public shareholding", "public holding", "public")),
    ("others_percent", ("others", "other investors")),
    ("institutional_holding_percent", ("institutional investors", "institutions", "institutional holding")),
    ("non_institutional_holding_percent", ("non institutional", "non-institutional")),
    ("total_shareholders", ("total shareholders", "number of shareholders", "total holders")),
)

_INSTITUTIONAL_COMPONENTS = (
    "fii_holding_percent",
    "dii_holding_percent",
    "mutual_fund_holding_percent",
    "insurance_holding_percent",
)
_NON_INSTITUTIONAL_COMPONENTS = (
    "body_corporates_percent",
    "retail_holding_percent",
    "others_percent",
)
_SHAREHOLDING_TABLE_MARKERS = (
    "shareholding pattern",
    "category of shareholder",
    "promoter and promoter group",
    "public shareholder",
    "public shareholding",
    "pledged",
)


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


def _best_current_and_previous(
    values: Sequence[Dict[str, Any]],
    target_year: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    ranked = sorted(
        [item for item in values if isinstance(item, dict)],
        key=lambda item: (-_period_match_score(str(item.get("period", "")), target_year), values.index(item)),
    )
    if not ranked:
        return None, None
    current = ranked[0]
    previous = ranked[1] if len(ranked) > 1 else None
    return current, previous


def _classify_raw_category(line_item_raw: str) -> Optional[str]:
    lowered = str(line_item_raw or "").lower()
    for category, keywords in _RAW_CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return None


def _row_looks_like_shareholding_table(line_item_raw: str) -> bool:
    lowered = str(line_item_raw or "").lower()
    return any(token in lowered for token in _SHAREHOLDING_TABLE_MARKERS) or _classify_raw_category(line_item_raw) is not None


def _value_type(current: Optional[Dict[str, Any]], line_item_raw: str) -> str:
    if isinstance(current, dict):
        explicit = str(current.get("value_type", "") or "").strip().lower()
        if explicit:
            return explicit
        unit = str(current.get("unit_hint", "") or "").strip().lower()
        if unit in {"%", "percent", "percentage"}:
            return "percentage"
        if unit in {"shares", "units"}:
            return "share_count"
    lowered = str(line_item_raw or "").lower()
    if "shareholders" in lowered and "total" in lowered:
        return "share_count"
    if "shares held" in lowered or "number of shares" in lowered:
        return "share_count"
    return "percentage"


def _rejection_record(
    *,
    row: Dict[str, Any],
    rejection_reason: str,
) -> Dict[str, Any]:
    return {
        "candidate_text": str(row.get("line_item_raw", "") or ""),
        "source_page": row.get("page"),
        "source_line_item": str(row.get("line_item_raw", "") or ""),
        "rejection_reason": rejection_reason,
        "confidence": str(row.get("confidence", "low") or "low"),
    }


def _make_item(
    *,
    holder_category: str,
    period: str,
    holding_percent: Optional[float],
    shares_held: Optional[float],
    change_percent: Optional[float],
    source_line_item: str,
    source_page: Optional[int],
    source_artifact: str,
    confidence: str,
    warnings: Iterable[str],
) -> ShareholdingItem:
    return ShareholdingItem(
        holder_category=holder_category,
        period=period,
        holding_percent=holding_percent,
        shares_held=shares_held,
        change_percent=change_percent,
        source_line_item=source_line_item,
        source_page=source_page,
        source_artifact=source_artifact,
        confidence=confidence,
        warnings=[str(item) for item in warnings],
    )


def _build_from_normalized(normalized_payload: Dict[str, Any]) -> List[ShareholdingItem]:
    items: List[ShareholdingItem] = []
    for field_name, holder_category in _NORMALIZED_FIELD_TO_CATEGORY.items():
        entry = _entry(normalized_payload, "shareholding_pattern", field_name)
        value = _parse_numeric(entry.get("value_original"))
        period = str(entry.get("period", "") or "")
        if value is None and not period and not entry.get("source_line_item"):
            continue
        warnings = list(entry.get("warnings", [])) if isinstance(entry.get("warnings"), list) else []
        if value is None:
            _append_unique(warnings, "holding percent unavailable")
        items.append(
            _make_item(
                holder_category=holder_category,
                period=period,
                holding_percent=value,
                shares_held=None,
                change_percent=None,
                source_line_item=str(entry.get("source_line_item", "") or field_name),
                source_page=entry.get("source_page"),
                source_artifact=str(entry.get("source_artifact", "") or "normalized_fundamentals.json"),
                confidence=str(entry.get("confidence", "missing") or "missing"),
                warnings=warnings,
            )
        )
    return items


def _build_from_raw(raw_payload: Optional[Dict[str, Any]], year: str) -> Tuple[List[ShareholdingItem], bool, List[str], List[Dict[str, Any]]]:
    if not isinstance(raw_payload, dict):
        return [], False, [], []
    rows = (raw_payload.get("tables") or {}).get("shareholding_pattern")
    if not isinstance(rows, list):
        return [], False, [], []
    target_year = _fy_year_from_slug(year) or ""
    items: List[ShareholdingItem] = []
    saw_section = bool(rows)
    rejection_reasons: List[str] = []
    rejection_items: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        line_item_raw = str(row.get("line_item_raw", "") or "")
        if not _row_looks_like_shareholding_table(line_item_raw):
            _append_unique(rejection_reasons, f"Unclassified shareholding row: {line_item_raw}")
            rejection_items.append(_rejection_record(row=row, rejection_reason="row does not look like an explicit shareholding category"))
            continue
        holder_category = _classify_raw_category(line_item_raw)
        if not holder_category:
            _append_unique(rejection_reasons, f"Unclassified shareholding row: {line_item_raw}")
            rejection_items.append(_rejection_record(row=row, rejection_reason="shareholding category could not be classified"))
            continue
        current, previous = _best_current_and_previous(row.get("values", []), target_year)
        if current is None:
            _append_unique(rejection_reasons, f"Shareholding row missing usable current period: {line_item_raw}")
            rejection_items.append(_rejection_record(row=row, rejection_reason="current period value missing"))
            continue
        current_value = _parse_numeric(current.get("value_raw"))
        previous_value = _parse_numeric(previous.get("value_raw")) if previous else None
        value_type = _value_type(current, line_item_raw)
        change_percent = None
        holding_percent = None
        shares_held = None
        warnings = list(row.get("warnings", [])) if isinstance(row.get("warnings"), list) else []
        if value_type == "percentage":
            holding_percent = current_value
            if current_value is not None and previous_value is not None:
                change_percent = current_value - previous_value
        elif value_type == "share_count":
            shares_held = current_value
        else:
            _append_unique(rejection_reasons, f"Unsupported shareholding value type for row: {line_item_raw}")
            rejection_items.append(_rejection_record(row=row, rejection_reason=f"unsupported shareholding value type: {value_type}"))
            continue
        if holder_category == "pledged_promoter_holding_percent" and value_type != "percentage":
            _append_unique(rejection_reasons, f"Pledge row must be a percentage: {line_item_raw}")
            rejection_items.append(_rejection_record(row=row, rejection_reason="pledge disclosure must be percentage based"))
            continue
        if holding_percent is None and shares_held is None:
            _append_unique(rejection_reasons, f"Shareholding row missing usable normalized value: {line_item_raw}")
            rejection_items.append(_rejection_record(row=row, rejection_reason="row could not be normalized into percent or shares"))
            continue
        if holding_percent is None and holder_category != "total_shareholders":
            _append_unique(warnings, "holding percent unavailable")
        if shares_held is None and value_type == "share_count":
            _append_unique(warnings, "shares held unavailable")
        if holder_category == "total_shareholders":
            shares_held = current_value
            holding_percent = None
        if current_value is not None and previous_value is not None and value_type == "percentage":
            change_percent = current_value - previous_value
        items.append(
            _make_item(
                holder_category=holder_category,
                period=str(current.get("period", "") or ""),
                holding_percent=holding_percent,
                shares_held=shares_held,
                change_percent=change_percent,
                source_line_item=line_item_raw,
                source_page=row.get("page"),
                source_artifact=str(row.get("source_artifact", "") or "raw_financial_tables.json"),
                confidence=str(row.get("confidence", "low") or "low"),
                warnings=warnings,
            )
        )
    return items, saw_section, rejection_reasons, rejection_items


def _pick_better(existing: ShareholdingItem, candidate: ShareholdingItem) -> ShareholdingItem:
    confidence_rank = {"high": 3, "medium": 2, "low": 1, "missing": 0}
    source_rank = {"raw_financial_tables.json": 2, "normalized_fundamentals.json": 1}
    existing_score = (
        existing.holding_percent is not None,
        confidence_rank.get(existing.confidence, 0),
        source_rank.get(existing.source_artifact, 0),
        len(existing.warnings) == 0,
    )
    candidate_score = (
        candidate.holding_percent is not None,
        confidence_rank.get(candidate.confidence, 0),
        source_rank.get(candidate.source_artifact, 0),
        len(candidate.warnings) == 0,
    )
    return candidate if candidate_score > existing_score else existing


def _merge_items(raw_items: List[ShareholdingItem], normalized_items: List[ShareholdingItem]) -> List[ShareholdingItem]:
    merged: Dict[str, ShareholdingItem] = {}
    for item in normalized_items + raw_items:
        existing = merged.get(item.holder_category)
        merged[item.holder_category] = item if existing is None else _pick_better(existing, item)
    return list(merged.values())


def _item_map(items: Iterable[ShareholdingItem]) -> Dict[str, ShareholdingItem]:
    return {item.holder_category: item for item in items}


def _sum_known(items: Dict[str, ShareholdingItem], categories: Sequence[str]) -> Tuple[Optional[float], List[str]]:
    values: List[float] = []
    warnings: List[str] = []
    for category in categories:
        item = items.get(category)
        if item is None or item.holding_percent is None:
            continue
        values.append(item.holding_percent)
        warnings.extend(item.warnings)
    if not values:
        return None, warnings
    return sum(values), warnings


def _derive_aggregate_items(items: List[ShareholdingItem]) -> List[ShareholdingItem]:
    item_map = _item_map(items)
    derived: List[ShareholdingItem] = []

    institutional_total, institutional_warnings = _sum_known(item_map, _INSTITUTIONAL_COMPONENTS)
    if institutional_total is not None and "institutional_holding_percent" not in item_map:
        source_artifacts = sorted(
            {
                item_map[key].source_artifact
                for key in _INSTITUTIONAL_COMPONENTS
                if key in item_map and item_map[key].source_artifact
            }
        )
        derived.append(
            _make_item(
                holder_category="institutional_holding_percent",
                period=next((item_map[key].period for key in _INSTITUTIONAL_COMPONENTS if key in item_map), ""),
                holding_percent=round(institutional_total, 2),
                shares_held=None,
                change_percent=None,
                source_line_item="derived institutional holding",
                source_page=None,
                source_artifact=", ".join(source_artifacts),
                confidence="medium",
                warnings=list(set(institutional_warnings + ["derived from institution subcategories"])),
            )
        )

    non_institutional_total, non_inst_warnings = _sum_known(item_map, _NON_INSTITUTIONAL_COMPONENTS)
    if non_institutional_total is not None and "non_institutional_holding_percent" not in item_map:
        source_artifacts = sorted(
            {
                item_map[key].source_artifact
                for key in _NON_INSTITUTIONAL_COMPONENTS
                if key in item_map and item_map[key].source_artifact
            }
        )
        derived.append(
            _make_item(
                holder_category="non_institutional_holding_percent",
                period=next((item_map[key].period for key in _NON_INSTITUTIONAL_COMPONENTS if key in item_map), ""),
                holding_percent=round(non_institutional_total, 2),
                shares_held=None,
                change_percent=None,
                source_line_item="derived non-institutional holding",
                source_page=None,
                source_artifact=", ".join(source_artifacts),
                confidence="medium",
                warnings=list(set(non_inst_warnings + ["derived from public subcategories"])),
            )
        )
    elif "non_institutional_holding_percent" not in item_map:
        public_item = item_map.get("public_holding_percent")
        institutional_item = item_map.get("institutional_holding_percent") or next(
            (item for item in derived if item.holder_category == "institutional_holding_percent"),
            None,
        )
        if (
            public_item is not None
            and public_item.holding_percent is not None
            and institutional_item is not None
            and institutional_item.holding_percent is not None
        ):
            derived_value = public_item.holding_percent - institutional_item.holding_percent
            derived.append(
                _make_item(
                    holder_category="non_institutional_holding_percent",
                    period=public_item.period,
                    holding_percent=round(derived_value, 2),
                    shares_held=None,
                    change_percent=None,
                    source_line_item="derived public minus institutional holding",
                    source_page=public_item.source_page,
                    source_artifact=public_item.source_artifact,
                    confidence="low",
                    warnings=["derived from public minus institutional holding"],
                )
            )
    return derived


def _build_summary(items: List[ShareholdingItem]) -> OwnershipSummary:
    item_map = _item_map(items)
    promoter = item_map.get("promoter_holding_percent")
    pledge = item_map.get("pledged_promoter_holding_percent")
    institutional = item_map.get("institutional_holding_percent")
    public_float = item_map.get("public_holding_percent")

    promoter_control = (
        f"Promoter holding recorded at {promoter.holding_percent:.2f}%."
        if promoter and promoter.holding_percent is not None
        else "Promoter holding information unavailable."
    )
    institutional_interest = (
        f"Institutional holding recorded at {institutional.holding_percent:.2f}%."
        if institutional and institutional.holding_percent is not None
        else "Institutional holding detail is incomplete."
    )
    if pledge and pledge.holding_percent is not None:
        pledge_risk = (
            f"Promoter pledge recorded at {pledge.holding_percent:.2f}%."
            if pledge.holding_percent > 0
            else "No promoter pledge was recorded."
        )
    else:
        pledge_risk = "Promoter pledge data unavailable."
    public_float_summary = (
        f"Public holding recorded at {public_float.holding_percent:.2f}%."
        if public_float and public_float.holding_percent is not None
        else "Public float detail is incomplete."
    )

    notable_changes: List[str] = []
    for item in items:
        if item.change_percent is None:
            continue
        if abs(item.change_percent) < 0.25:
            continue
        direction = "increased" if item.change_percent > 0 else "decreased"
        notable_changes.append(
            f"{item.holder_category} {direction} by {abs(item.change_percent):.2f} percentage points."
        )

    return OwnershipSummary(
        promoter_control=promoter_control,
        institutional_interest=institutional_interest,
        pledge_risk=pledge_risk,
        public_float=public_float_summary,
        notable_changes=notable_changes,
    )


def extract_shareholding_pattern(
    *,
    company: str,
    year: str,
    raw_tables_path: Path,
    normalized_path: Path,
) -> ShareholdingReport:
    if not normalized_path.exists():
        raise FileNotFoundError(f"normalized fundamentals not found: {normalized_path}")

    normalized_payload = _load_json(normalized_path)
    raw_payload = _load_json(raw_tables_path) if raw_tables_path.exists() else None

    normalized_items = _build_from_normalized(normalized_payload)
    raw_items, saw_raw_shareholding_section, raw_rejection_reasons, rejection_items = _build_from_raw(raw_payload, year)
    items = _merge_items(raw_items, normalized_items)
    items.extend(_derive_aggregate_items(items))
    items = _merge_items(items, [])

    warnings: List[str] = []
    limitations: List[str] = []
    rejection_reasons: List[str] = list(raw_rejection_reasons)
    searched_sections: List[str] = []

    if isinstance(raw_payload, dict):
        tables = raw_payload.get("tables", {})
        if isinstance(tables, dict):
            for section_name, rows in tables.items():
                if isinstance(rows, list) and rows:
                    searched_sections.append(section_name)

    if not raw_tables_path.exists():
        _append_unique(limitations, "raw_financial_tables.json unavailable; shareholding extraction relied on normalized fundamentals only")

    if not saw_raw_shareholding_section and not items:
        _append_unique(warnings, "shareholding pattern missing")
        if searched_sections:
            _append_unique(warnings, "shareholding pattern was searched but no explicit shareholding table was found")

    if saw_raw_shareholding_section and not raw_items:
        _append_unique(rejection_reasons, "shareholding_pattern rows were present but none could be confidently classified")
        _append_unique(warnings, "shareholding table exists but could not be parsed reliably")

    pledged_item = next((item for item in items if item.holder_category == "pledged_promoter_holding_percent"), None)
    if pledged_item is None or pledged_item.holding_percent is None:
        _append_unique(warnings, "promoter pledge data missing")

    if all(item.holder_category not in {"fii_holding_percent", "dii_holding_percent", "mutual_fund_holding_percent", "insurance_holding_percent", "institutional_holding_percent"} for item in items):
        _append_unique(warnings, "institutional split unavailable")

    if any(not item.period for item in items):
        _append_unique(warnings, "period labels unclear")

    total_categories = [
        item.holding_percent
        for item in items
        if item.holder_category
        in {
            "promoter_holding_percent",
            "public_holding_percent",
            "others_percent",
            "institutional_holding_percent",
            "non_institutional_holding_percent",
        }
        and item.holding_percent is not None
    ]
    promoter = next((item.holding_percent for item in items if item.holder_category == "promoter_holding_percent"), None)
    public = next((item.holding_percent for item in items if item.holder_category == "public_holding_percent"), None)
    if promoter is not None and public is not None:
        combined = promoter + public
        if abs(combined - 100.0) > 2.0:
            _append_unique(warnings, "categories do not sum near 100%")
    elif total_categories:
        direct_total = sum(total_categories)
        if direct_total > 102.0 or direct_total < 98.0:
            _append_unique(warnings, "categories do not sum near 100%")

    if any(item.holding_percent is None for item in items):
        _append_unique(limitations, "some ownership rows are present but their percentages could not be normalized")

    status = "pass"
    if warnings or limitations:
        status = "warning"

    report = ShareholdingReport(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status=status,
        items=items,
        ownership_summary=_build_summary(items),
        searched_sections=searched_sections,
        rejection_reasons=rejection_reasons,
        warnings=warnings,
        limitations=limitations,
    )

    validation_errors = validate_shareholding_payload(report.to_dict())
    if validation_errors:
        raise ValueError("Invalid shareholding payload: " + "; ".join(validation_errors))
    report._rejection_items = rejection_items  # type: ignore[attr-defined]
    return report


def write_shareholding_pattern(
    *,
    company: str,
    year: str,
    raw_tables_path: Path,
    normalized_path: Path,
    output_path: Path,
) -> ShareholdingReport:
    report = extract_shareholding_pattern(
        company=company,
        year=year,
        raw_tables_path=raw_tables_path,
        normalized_path=normalized_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    rejection_path = output_path.with_name("shareholding_rejections.json")
    rejection_items = getattr(report, "_rejection_items", [])
    rejection_path.write_text(json.dumps(rejection_items, indent=2), encoding="utf-8")
    return report
