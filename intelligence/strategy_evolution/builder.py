from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from intelligence.strategy_evolution.classifier import (
    classify_bme_event_type,
    classify_mp_event_type,
    classify_shift_event,
    classify_theme_category,
    is_generic_theme,
    normalize_theme_name,
)
from intelligence.strategy_evolution.resolver import (
    detect_patterns,
    detect_repetition,
    resolve_capital_backing,
    resolve_current_state,
    resolve_opening_state,
    resolve_theme_current_status,
)


# ── Source loading ─────────────────────────────────────────────────────────────

def _load_sources(
    company_slug: str,
    companies_root: Path,
) -> Dict[str, Any]:
    mem = companies_root / company_slug / "company_memory"

    def _read(rel: str) -> Any:
        p = mem / rel
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {}

    def _read_list(rel: str, key: str) -> List[Any]:
        data = _read(rel)
        if isinstance(data, dict):
            return data.get(key, []) or []
        return []

    # management_progression → legacy_strategy + commitment items
    mp_all = _read_list("management_progression/management_progression.json", "progression_items")
    legacy_strategy_items = [
        x for x in mp_all
        if "legacy_strategy" in (x.get("stream_types") or [])
    ]
    commitment_items = [
        x for x in mp_all
        if "commitment" in (x.get("stream_types") or [])
    ]

    # strategy_timeline
    strategy_timeline_raw = _read("multi_year/strategy_timeline.json")
    timeline_by_year = {
        entry["year"]: entry
        for entry in (strategy_timeline_raw.get("timeline") or [])
        if isinstance(entry, dict) and entry.get("year")
    }
    theme_mentions_by_year = strategy_timeline_raw.get("theme_mentions_by_year") or {}
    strategy_continuity = strategy_timeline_raw.get("strategy_continuity") or []
    strategy_shifts = strategy_timeline_raw.get("strategy_shifts") or []

    # company_model → business_model_evolution
    company_model = _read("company_model/company_model.json")
    bme_items = company_model.get("business_model_evolution") or []

    # business_journey
    business_journey = _read("ask_intrinsiciq/business_journey.json")
    historical_stages = business_journey.get("historical_stages") or []

    # capital_allocation_outcome_tracker (Gold #2, for cross-linking)
    gold2 = _read("gold/capital_allocation_outcome_tracker.json")
    capital_allocations = gold2.get("material_allocations") or []

    # promise_tracker for cross-reference
    promise_tracker = _read("multi_year/promise_tracker.json")

    # Determine latest data period
    all_years: List[str] = []
    for bme in bme_items:
        if bme.get("to_period"):
            all_years.append(bme["to_period"])
    for item in legacy_strategy_items:
        for ev in (item.get("events") or []):
            if ev.get("source_period"):
                all_years.append(ev["source_period"])
    latest_period = max(all_years, default="fy26")

    return {
        "legacy_strategy_items": legacy_strategy_items,
        "commitment_items": commitment_items,
        "timeline_by_year": timeline_by_year,
        "theme_mentions_by_year": theme_mentions_by_year,
        "strategy_continuity": strategy_continuity,
        "strategy_shifts": strategy_shifts,
        "bme_items": bme_items,
        "historical_stages": historical_stages,
        "business_journey": business_journey,
        "capital_allocations": capital_allocations,
        "promise_tracker": promise_tracker,
        "latest_period": latest_period,
    }


# ── Evidence extraction ───────────────────────────────────────────────────────

def _extract_evidence_ids(item: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for ev_block in (item.get("events") or []):
        for ref in (ev_block.get("evidence") or []):
            eid = ref.get("evidence_id") or ""
            if eid and eid not in ids:
                ids.append(eid)
    return ids


def _extract_source_periods(item: Dict[str, Any]) -> List[str]:
    periods: List[str] = []
    for ev_block in (item.get("events") or []):
        p = ev_block.get("source_period") or ev_block.get("event_period") or ""
        if p and p not in periods:
            periods.append(p)
    return sorted(set(periods))


# ── Theme building from legacy_strategy items ─────────────────────────────────

def _build_themes_from_legacy_strategy(
    legacy_strategy_items: List[Dict[str, Any]],
    capital_allocations: List[Any],
    latest_period: str,
) -> List[Dict[str, Any]]:
    themes: List[Dict[str, Any]] = []
    seen_names: Dict[str, int] = {}  # name → index in themes

    for idx, item in enumerate(legacy_strategy_items):
        raw_theme = (item.get("theme") or "").strip()
        if not raw_theme:
            continue

        theme_name = normalize_theme_name(raw_theme)
        if is_generic_theme(theme_name):
            continue

        periods = _extract_source_periods(item)
        if not periods:
            continue

        first_period = periods[0]
        events: List[Dict[str, Any]] = []

        for ev_block in (item.get("events") or []):
            period = ev_block.get("source_period") or ev_block.get("event_period") or ""
            event_type = classify_mp_event_type(ev_block, first_period)
            action = (ev_block.get("action_taken") or "").strip()
            ev_refs = [r.get("evidence_id", "") for r in (ev_block.get("evidence") or []) if r.get("evidence_id")]

            events.append({
                "event_id": ev_block.get("event_id") or f"SE-{idx:04d}",
                "period": period,
                "event_type": event_type,
                "description": action[:200] if action else theme_name,
                "source_artifact": "management_progression",
                "evidence_ids": ev_refs,
            })

        category = classify_theme_category(theme_name)
        capital_backed = resolve_capital_backing(theme_name, category, capital_allocations)
        current_status = resolve_theme_current_status(periods, latest_period, events)
        has_execution = any(e["event_type"] in ("EXECUTION_STARTED", "OUTCOME_VISIBLE") for e in events)

        # Deduplicate: merge themes with very similar names
        existing_idx = seen_names.get(theme_name.lower())
        if existing_idx is not None:
            existing = themes[existing_idx]
            existing["periods_active"] = sorted(set(existing["periods_active"] + periods))
            existing["events"].extend(events)
            existing["evidence_ids"] = list(set(existing["evidence_ids"] + _extract_evidence_ids(item)))
            existing["capital_backed"] = existing["capital_backed"] or capital_backed
            existing["execution_evidence"] = existing["execution_evidence"] or has_execution
            existing["current_status"] = resolve_theme_current_status(
                existing["periods_active"], latest_period, existing["events"]
            )
        else:
            theme_id = f"ST-{len(themes) + 1:04d}"
            theme_record = {
                "theme_id": theme_id,
                "theme_name": theme_name,
                "theme_category": category,
                "first_period": first_period,
                "last_confirmed_period": periods[-1],
                "periods_active": periods,
                "current_status": current_status,
                "events": events,
                "capital_backed": capital_backed,
                "execution_evidence": has_execution,
                "evidence_ids": _extract_evidence_ids(item),
                "investor_implication": (item.get("investor_implication") or {}).get("conclusion") or "",
            }
            seen_names[theme_name.lower()] = len(themes)
            themes.append(theme_record)

    return themes


# ── Theme augmentation from strategy_shifts ───────────────────────────────────

def _augment_themes_from_shifts(
    themes: List[Dict[str, Any]],
    strategy_shifts: List[Dict[str, Any]],
    latest_period: str,
) -> None:
    """
    Add NOT_RECONFIRMED and DEPRIORITIZED events for themes removed in strategy_shifts.

    Modifies themes in-place.
    """
    theme_names_lower = {t["theme_name"].lower(): t for t in themes}

    for shift in strategy_shifts:
        from_year = shift.get("from_year") or ""
        to_year = shift.get("to_year") or ""

        for removed in (shift.get("removed_themes") or []):
            if is_generic_theme(removed):
                continue
            theme = theme_names_lower.get(removed.lower())
            if theme:
                # Check if last event period matches from_year
                if to_year not in theme["periods_active"]:
                    theme["events"].append({
                        "event_id": f"SE-SHIFT-{from_year}-{removed}",
                        "period": to_year,
                        "event_type": "DEPRIORITIZED",
                        "description": f"Theme '{removed}' absent from management focus after {from_year}.",
                        "source_artifact": "strategy_timeline",
                        "evidence_ids": [],
                    })


# ── Theme augmentation from business_model_evolution ─────────────────────────

def _augment_themes_from_bme(
    themes: List[Dict[str, Any]],
    bme_items: List[Dict[str, Any]],
) -> None:
    """
    Enrich existing themes with PIVOTED/REVERSED/ACCELERATED events from
    business_model_evolution. Modifies themes in-place.
    """
    known_names = {t["theme_name"].lower() for t in themes}
    theme_map = {t["theme_name"].lower(): t for t in themes}

    for bme in bme_items:
        what = (bme.get("what_changed") or "").strip()
        from_p = bme.get("from_period") or ""
        to_p = bme.get("to_period") or ""
        if not what:
            continue

        event_type = classify_bme_event_type(bme, known_names)
        if event_type == "REINFORCED":
            continue  # Skip generic period-on-period reinforcements

        # Try to attach to an existing theme by keyword match
        what_lower = what.lower()
        attached = False
        for name_lower, theme in theme_map.items():
            if any(kw in what_lower for kw in name_lower.split() if len(kw) >= 5):
                theme["events"].append({
                    "event_id": f"SE-BME-{to_p or from_p}",
                    "period": to_p or from_p,
                    "event_type": event_type,
                    "description": what[:200],
                    "source_artifact": "business_model_evolution",
                    "evidence_ids": [],
                })
                attached = True
                break

        # If event is a significant structural change and no theme attached, skip (no new themes from BME)
        _ = attached


# ── Theme building from strategy_timeline (canonical continuity) ──────────────

# Minimum periods for a canonical theme to be included from timeline
_TIMELINE_THEME_MIN_PERIODS = 3

# Human-readable names for canonical theme keys
_CANONICAL_READABLE: Dict[str, str] = {
    "product_innovation": "Product innovation and R&D",
    "capex_program": "Capital expenditure programme",
    "plant_construction": "Manufacturing capacity expansion",
    "manufacturing_capacity_expansion": "Manufacturing capacity expansion",
    "customer_channel": "Market reach and customer channels",
    "capital_allocation": "Capital deployment programme",
    "geographic_expansion": "Geographic expansion",
}


def _build_themes_from_timeline(
    timeline_by_year: Dict[str, Any],
    strategy_continuity: List[Dict[str, Any]],
    capital_allocations: List[Any],
    latest_period: str,
    existing_theme_names: set,
) -> List[Dict[str, Any]]:
    """
    Build strategy themes from strategy_timeline management_focus items.

    Groups focus items by canonical_theme. Only includes themes with 3+ years
    that are not generic and not already represented in legacy_strategy themes.
    """
    # Build map: canonical_theme → {year → [focus_items]}
    theme_year_items: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for year, entry in timeline_by_year.items():
        for focus_item in (entry.get("management_focus") or []):
            canon = focus_item.get("canonical_theme") or "unclassified_theme"
            if is_generic_theme(canon):
                continue
            if canon not in theme_year_items:
                theme_year_items[canon] = {}
            if year not in theme_year_items[canon]:
                theme_year_items[canon][year] = []
            theme_year_items[canon][year].append(focus_item)

    # Get persistence from strategy_continuity
    continuity_map = {c["theme"]: c.get("years_active", []) for c in strategy_continuity}

    themes: List[Dict[str, Any]] = []
    for canon_key, years_map in theme_year_items.items():
        years_active = sorted(years_map.keys())
        if len(years_active) < _TIMELINE_THEME_MIN_PERIODS:
            continue

        # Get readable name: prefer _CANONICAL_READABLE, then best label from focus items
        readable = _CANONICAL_READABLE.get(canon_key)
        if not readable:
            # Find most descriptive value across all years
            all_values = [
                fi.get("value") or ""
                for year_items in years_map.values()
                for fi in year_items
                if fi.get("value")
            ]
            # Pick longest non-generic label
            readable = max(all_values, key=len, default=canon_key.replace("_", " ").title())

        theme_name = normalize_theme_name(readable)
        # Skip if already well-represented by a legacy_strategy theme
        # Require 2+ content words matching to avoid false-positives
        content_words = [kw for kw in theme_name.lower().split() if len(kw) >= 6]
        already_covered = any(
            sum(1 for kw in content_words if kw in existing.lower()) >= 2
            for existing in existing_theme_names
        )
        if already_covered:
            continue

        first_period = years_active[0]
        events: List[Dict[str, Any]] = []
        all_ev_ids: List[str] = []

        for year in years_active:
            ev_type = "INTRODUCED" if year == first_period else "REINFORCED"
            year_focus = years_map[year]
            ev_ids = [eid for fi in year_focus for eid in (fi.get("evidence_ids") or [])]
            all_ev_ids.extend(ev_ids)
            # Use the most descriptive label in this year
            label = max(
                (fi.get("value") or "" for fi in year_focus),
                key=len, default=theme_name,
            )
            events.append({
                "event_id": f"SE-TL-{year}-{canon_key[:12]}",
                "period": year,
                "event_type": ev_type,
                "description": label[:200],
                "source_artifact": "strategy_timeline",
                "evidence_ids": ev_ids,
            })

        category = classify_theme_category(theme_name, canon_key)
        capital_backed = resolve_capital_backing(theme_name, category, capital_allocations)
        current_status = resolve_theme_current_status(years_active, latest_period, events)
        has_execution = capital_backed  # Capital backing implies some execution

        themes.append({
            "theme_id": f"ST-TL-{len(themes) + 1:04d}",
            "theme_name": theme_name,
            "theme_category": category,
            "first_period": first_period,
            "last_confirmed_period": years_active[-1],
            "periods_active": years_active,
            "current_status": current_status,
            "events": events,
            "capital_backed": capital_backed,
            "execution_evidence": has_execution,
            "evidence_ids": list(dict.fromkeys(all_ev_ids)),  # preserve order, deduplicate
            "investor_implication": "",
        })

    return themes


# ── Main builder ─────────────────────────────────────────────────────────────

def build_strategy_evolution_timeline(
    company_slug: str,
    companies_root: Path = Path("."),
) -> Dict[str, Any]:
    sources = _load_sources(company_slug, companies_root)

    themes = _build_themes_from_legacy_strategy(
        sources["legacy_strategy_items"],
        sources["capital_allocations"],
        sources["latest_period"],
    )

    # Add persistent themes from strategy_timeline not covered by legacy_strategy
    existing_names = {t["theme_name"] for t in themes}
    timeline_themes = _build_themes_from_timeline(
        sources["timeline_by_year"],
        sources["strategy_continuity"],
        sources["capital_allocations"],
        sources["latest_period"],
        existing_names,
    )
    themes.extend(timeline_themes)

    # Augment with structural signals
    _augment_themes_from_shifts(themes, sources["strategy_shifts"], sources["latest_period"])
    _augment_themes_from_bme(themes, sources["bme_items"])

    # Sort themes: current priorities first, then by first_period desc
    themes.sort(key=lambda t: (
        0 if t["current_status"] == "CURRENT_PRIORITY" else 1,
        t["first_period"],
    ))

    # Detect cross-theme patterns
    strategy_patterns = detect_patterns(
        themes,
        sources["capital_allocations"],
        sources["latest_period"],
    )

    # Build arc narrative
    opening_state = resolve_opening_state(sources["historical_stages"], sources["bme_items"])
    current_state = resolve_current_state(sources["business_journey"], themes)

    # Cross-references
    cross_refs: Dict[str, str] = {}
    gold2_path = (
        Path(".") / "companies" / company_slug / "company_memory"
        / "gold" / "capital_allocation_outcome_tracker.json"
    )
    if gold2_path.exists():
        cross_refs["capital_allocation_tracker"] = (
            f"companies/{company_slug}/company_memory/gold/capital_allocation_outcome_tracker.json"
        )
    promise_tracker_path = (
        Path(".") / "companies" / company_slug / "company_memory"
        / "multi_year" / "promise_tracker.json"
    )
    if promise_tracker_path.exists():
        cross_refs["management_promise_tracker"] = (
            f"companies/{company_slug}/company_memory/multi_year/promise_tracker.json"
        )

    return {
        "schema_version": "strategy_evolution_gold.v1",
        "company_slug": company_slug,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_coverage": {
            "latest_period": sources["latest_period"],
            "periods_with_data": _all_active_periods(themes),
        },
        "strategy_arc": {
            "opening_state": opening_state,
            "current_state": current_state,
        },
        "strategy_themes": themes,
        "strategy_patterns": strategy_patterns,
        "cross_references": cross_refs,
    }


def _all_active_periods(themes: List[Dict[str, Any]]) -> List[str]:
    periods: set = set()
    for t in themes:
        periods.update(t.get("periods_active") or [])
    return sorted(periods)


def write_strategy_evolution_timeline(
    company_slug: str,
    companies_root: Path = Path("."),
) -> Path:
    result = build_strategy_evolution_timeline(company_slug, companies_root)
    out_dir = companies_root / company_slug / "company_memory" / "gold"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "strategy_evolution_timeline.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path
