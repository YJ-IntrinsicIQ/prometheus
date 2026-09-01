"""Regression tests for the Strategy Evolution Timeline Gold layer."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from intelligence.strategy_evolution.builder import (
    build_strategy_evolution_timeline,
    write_strategy_evolution_timeline,
    _build_themes_from_legacy_strategy,
)
from intelligence.strategy_evolution.classifier import (
    classify_mp_event_type,
    classify_bme_event_type,
    classify_shift_event,
    classify_theme_category,
    is_generic_theme,
    normalize_theme_name,
)
from intelligence.strategy_evolution.resolver import (
    detect_patterns,
    detect_repetition,
    resolve_capital_backing,
    resolve_theme_current_status,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _mp_item(
    theme: str,
    periods: List[str],
    event_types: List[str] | None = None,
    action: str = "",
) -> Dict[str, Any]:
    """Build a minimal management_progression legacy_strategy item."""
    events = []
    for i, p in enumerate(periods):
        raw_type = (event_types or ["strategic_change"])[min(i, len(event_types or []) - 1)] if event_types else "strategic_change"
        events.append({
            "event_id": f"PJ-{i:04d}",
            "role": "action",
            "event_type": raw_type,
            "source_period": p,
            "event_period": p,
            "action_taken": action or theme,
            "operational_outcome": "",
            "financial_or_business_outcome": "",
            "evidence": [{"evidence_id": f"ev_{p}_{theme[:8].lower().replace(' ', '_')}_{i:03d}"}],
        })
    return {
        "item_id": f"MP-{hash(theme) % 9999:04d}-{theme[:10].lower().replace(' ', '_')}",
        "theme": theme,
        "linked_company_model_ids": [],
        "stream_types": ["legacy_strategy"],
        "current_status": "in_progress",
        "management_credibility_signal": "IN_PROGRESS",
        "events": events,
        "investor_implication": {"conclusion": ""},
        "unresolved": [],
        "synthesis_chain": [],
    }


def _minimal_sources(tmp_path: Path, legacy_items: List[Dict]) -> None:
    """Write minimal source artifacts for a synthetic company."""
    mem = tmp_path / "company_memory"

    mp_dir = mem / "management_progression"
    mp_dir.mkdir(parents=True)
    (mp_dir / "management_progression.json").write_text(
        json.dumps({"progression_items": legacy_items}), encoding="utf-8"
    )

    multi_dir = mem / "multi_year"
    multi_dir.mkdir(parents=True)
    (multi_dir / "strategy_timeline.json").write_text(
        json.dumps({
            "timeline": [],
            "theme_mentions_by_year": {},
            "strategy_continuity": [],
            "strategy_shifts": [],
        }), encoding="utf-8"
    )
    (multi_dir / "promise_tracker.json").write_text(json.dumps({}), encoding="utf-8")

    cm_dir = mem / "company_model"
    cm_dir.mkdir(parents=True)
    (cm_dir / "company_model.json").write_text(
        json.dumps({"business_model_evolution": []}), encoding="utf-8"
    )

    bj_dir = mem / "ask_intrinsiciq"
    bj_dir.mkdir(parents=True)
    (bj_dir / "business_journey.json").write_text(
        json.dumps({"historical_stages": [], "current_direction": "", "current_state": {}}),
        encoding="utf-8"
    )


# ── T1: persistent theme across 4+ periods → persistent_core_focus pattern ───

def test_persistent_theme_generates_core_focus_pattern(tmp_path):
    items = [_mp_item("Specialty pharma", ["fy20", "fy21", "fy22", "fy23", "fy24", "fy25"])]
    _minimal_sources(tmp_path / "acme", items)
    result = build_strategy_evolution_timeline("acme", companies_root=tmp_path)

    pattern_ids = [p["pattern_id"] for p in result["strategy_patterns"]]
    assert "persistent_core_focus" in pattern_ids


# ── T2: repetition ≠ new introduction (same theme → REINFORCED) ──────────────

def test_repeated_mention_classified_as_reinforced_not_introduced():
    item = _mp_item("Digital lending", ["fy22", "fy23", "fy24"])
    first_period = "fy22"
    events = item["events"]

    # First event: INTRODUCED
    first_type = classify_mp_event_type(events[0], first_period)
    assert first_type == "INTRODUCED"

    # Subsequent events on same theme: REINFORCED
    second_type = classify_mp_event_type(events[1], first_period)
    third_type = classify_mp_event_type(events[2], first_period)
    assert second_type == "REINFORCED"
    assert third_type == "REINFORCED"


# ── T3: silence ≠ abandonment (NOT_RECONFIRMED, not DEPRIORITIZED) ────────────

def test_silent_theme_is_not_reconfirmed_not_abandoned():
    # Theme active in fy22, fy23 — silent in fy25, fy26
    theme_periods = ["fy22", "fy23"]
    events = [{"event_type": "INTRODUCED", "period": "fy22"}]
    status = resolve_theme_current_status(theme_periods, "fy26", events)
    # Silence ≠ abandonment: must be NOT_RECONFIRMED (or DEPRIORITIZED only with explicit signal)
    assert status == "NOT_RECONFIRMED"
    assert status != "DEPRIORITIZED"


# ── T4: explicit deprioritization → DEPRIORITIZED ────────────────────────────

def test_explicit_deprioritization_event_yields_deprioritized_status():
    theme_periods = ["fy22", "fy23"]
    events = [
        {"event_type": "INTRODUCED", "period": "fy22"},
        {"event_type": "DEPRIORITIZED", "period": "fy24"},
    ]
    status = resolve_theme_current_status(theme_periods, "fy26", events)
    assert status == "DEPRIORITIZED"


# ── T5: generic themes excluded ──────────────────────────────────────────────

def test_generic_themes_are_excluded_from_gold_output(tmp_path):
    generic_items = [
        _mp_item("governance_compliance", ["fy22", "fy23"]),
        _mp_item("human_capital", ["fy22"]),
        _mp_item("csr", ["fy23"]),
    ]
    _minimal_sources(tmp_path / "acme", generic_items)
    result = build_strategy_evolution_timeline("acme", companies_root=tmp_path)
    # All generic themes should be excluded
    assert result["strategy_themes"] == []


# ── T6: strategy without execution → pattern flagged ─────────────────────────

def test_strategy_without_execution_triggers_pattern(tmp_path):
    # Two themes: multi-period but no execution events, no capital backing
    items = [
        _mp_item("AI integration", ["fy24", "fy25"]),
        _mp_item("Geographic expansion", ["fy24", "fy25"]),
    ]
    _minimal_sources(tmp_path / "acme", items)
    result = build_strategy_evolution_timeline("acme", companies_root=tmp_path)
    pattern_ids = [p["pattern_id"] for p in result["strategy_patterns"]]
    assert "strategy_without_execution" in pattern_ids


# ── T7: capital backing resolved via Gold #2 cross-link ──────────────────────

def test_capital_backed_strategy_detected_via_gold2_crosslink(tmp_path):
    items = [_mp_item("Acquisition and integration", ["fy24"])]
    _minimal_sources(tmp_path / "acme", items)

    # Write a Gold #2 artifact
    gold_dir = tmp_path / "acme" / "company_memory" / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)
    (gold_dir / "capital_allocation_outcome_tracker.json").write_text(
        json.dumps({
            "material_allocations": [
                {
                    "allocation_type": "ACQUISITION",
                    "allocation_name": "ValueFirst acquisition",
                    "capital_amount_crore": 340.0,
                    "return_status": "UNPROVEN",
                }
            ]
        }), encoding="utf-8"
    )

    result = build_strategy_evolution_timeline("acme", companies_root=tmp_path)
    themes = result["strategy_themes"]
    assert themes
    assert themes[0]["capital_backed"] is True

    pattern_ids = [p["pattern_id"] for p in result["strategy_patterns"]]
    assert "capital_backed_strategy" in pattern_ids


# ── T8: single-period theme does not trigger persistent_core_focus ────────────

def test_single_period_theme_does_not_trigger_persistent_focus_pattern(tmp_path):
    items = [_mp_item("Semaglutide launch", ["fy26"])]
    _minimal_sources(tmp_path / "acme", items)
    result = build_strategy_evolution_timeline("acme", companies_root=tmp_path)
    pattern_ids = [p["pattern_id"] for p in result["strategy_patterns"]]
    assert "persistent_core_focus" not in pattern_ids


# ── T9: business_model_evolution pivot → PIVOTED event ───────────────────────

def test_bme_pivot_language_classified_as_pivoted():
    bme = {
        "from_period": "fy24",
        "to_period": "fy25",
        "what_changed": "Management shifted from organic product launches to M&A-led growth.",
        "why_it_changed": "Organic pipeline maturity.",
        "evidence": [],
    }
    event_type = classify_bme_event_type(bme, {"organic growth"})
    assert event_type == "PIVOTED"


# ── T10: business_model_evolution acceleration → ACCELERATED ─────────────────

def test_bme_accelerate_language_classified_as_accelerated():
    bme = {
        "from_period": "fy23",
        "to_period": "fy24",
        "what_changed": "Platform deployment accelerated across all enterprise verticals.",
        "why_it_changed": "Customer demand and regulatory tailwind.",
        "evidence": [],
    }
    event_type = classify_bme_event_type(bme, set())
    assert event_type == "ACCELERATED"


# ── T11: no hardcoding — builder works for synthetic company ─────────────────

def test_builder_works_for_synthetic_company_without_hardcoded_names(tmp_path):
    items = [
        _mp_item("Platform differentiation", ["fy22", "fy23", "fy24", "fy25"]),
        _mp_item("International market entry", ["fy24"]),
    ]
    _minimal_sources(tmp_path / "synthetic_corp", items)
    result = build_strategy_evolution_timeline("synthetic_corp", companies_root=tmp_path)

    assert result["company_slug"] == "synthetic_corp"
    assert result["schema_version"] == "strategy_evolution_gold.v1"
    assert len(result["strategy_themes"]) >= 1

    artifact_text = json.dumps(result)
    for hardcoded in ("sun_pharma", "ujjivan", "tanla", "pharma", "banking", "telecom"):
        assert hardcoded not in artifact_text.lower(), f"Hardcoded term '{hardcoded}' found"


# ── T12: evidence IDs preserved through to output ────────────────────────────

def test_evidence_ids_preserved_in_theme_output(tmp_path):
    items = [_mp_item("Specialty pharma", ["fy22"])]
    _minimal_sources(tmp_path / "acme", items)
    result = build_strategy_evolution_timeline("acme", companies_root=tmp_path)
    themes = result["strategy_themes"]
    assert themes
    # Evidence IDs should be non-empty
    all_ev_ids = themes[0].get("evidence_ids") or []
    assert len(all_ev_ids) >= 1


# ── T13: no strategy quality score in output ──────────────────────────────────

def test_no_strategy_quality_score_in_output(tmp_path):
    items = [_mp_item("Specialty pharma", ["fy22", "fy23", "fy24"])]
    _minimal_sources(tmp_path / "acme", items)
    result = build_strategy_evolution_timeline("acme", companies_root=tmp_path)
    artifact_text = json.dumps(result)
    for banned_key in ("quality_score", "strategy_score", "management_score", "overall_score"):
        assert banned_key not in artifact_text, f"Score field '{banned_key}' found in output"


# ── T14: frequent_priority_turnover triggers with 3+ short-lived themes ──────

def test_frequent_priority_turnover_triggers_with_multiple_short_lived_themes(tmp_path):
    # 3 themes each active for only 1 period
    items = [
        _mp_item("Blockchain integration", ["fy22"]),
        _mp_item("Web3 strategy", ["fy23"]),
        _mp_item("Metaverse expansion", ["fy24"]),
    ]
    _minimal_sources(tmp_path / "acme", items)
    result = build_strategy_evolution_timeline("acme", companies_root=tmp_path)
    pattern_ids = [p["pattern_id"] for p in result["strategy_patterns"]]
    assert "frequent_priority_turnover" in pattern_ids


# ── T15: write produces correct file at expected path ────────────────────────

def test_write_produces_file_at_correct_path(tmp_path):
    items = [_mp_item("Specialty pharma", ["fy22", "fy23"])]
    _minimal_sources(tmp_path / "acme", items)
    out_path = write_strategy_evolution_timeline("acme", companies_root=tmp_path)

    expected = tmp_path / "acme" / "company_memory" / "gold" / "strategy_evolution_timeline.json"
    assert out_path == expected
    assert out_path.exists()

    data = json.loads(out_path.read_text())
    assert data["schema_version"] == "strategy_evolution_gold.v1"
    assert data["company_slug"] == "acme"
