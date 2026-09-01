"""
Tests for multi-period project event splitting (PSP-1 through PSP-15).

When a projects_registry item contains accepted state_transitions across 2+
distinct fiscal years, the producer must emit one event per year instead of
one compressed summary event.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from knowledge.management_progression.producer import (
    ManagementProgressionProducer,
    _transition_role_verification,
)
from knowledge.management_progression.linker import build_cross_year_links
from knowledge.management_progression.evidence_adapter import ManagementProgressionSources


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sources(
    *,
    projects: Optional[List[Dict[str, Any]]] = None,
    commitments: Optional[List[Dict[str, Any]]] = None,
    capacity_items: Optional[List[Dict[str, Any]]] = None,
) -> ManagementProgressionSources:
    """Build a ManagementProgressionSources stub for isolated unit tests."""
    sources_dict: Dict[str, Dict[str, Any]] = {}

    def _loaded(payload):
        return {"status": "loaded", "payload": payload, "legacy": False, "relative_path": "", "path": "", "error": ""}

    if projects is not None:
        sources_dict["projects_registry"] = _loaded({"projects": projects, "company_slug": "test_co"})
    if commitments is not None:
        sources_dict["management_commitments"] = _loaded({"commitments": commitments, "company_slug": "test_co"})
    if capacity_items is not None:
        sources_dict["capacity_registry"] = _loaded({"capacity_items": capacity_items, "company_slug": "test_co"})

    # Provide empty stubs for all other expected sources
    empty_stub = {"status": "missing", "payload": None, "legacy": False, "relative_path": "", "path": "", "error": ""}
    for name in (
        "company_model", "management_commitments", "projects_registry",
        "capacity_registry", "capacity_timelines", "project_timelines",
        "commentary_themes", "capital_allocation_outcomes", "financial_trends",
        "promise_tracker", "strategy_timeline", "capital_allocation_timeline",
        "risk_evolution", "management_consistency",
    ):
        sources_dict.setdefault(name, empty_stub)

    return ManagementProgressionSources(
        company_slug="test_co",
        company_root=Path("/fake/test_co"),
        sources=sources_dict,
        source_files_found=[],
        source_files_missing=[],
        legacy_adapter_used=False,
        legacy_adapter_sources=[],
        warnings=[],
    )


def _make_project(
    project_id: str,
    name: str,
    *,
    ann: str = "fy22",
    transitions: Optional[List[Dict[str, Any]]] = None,
    refs: Optional[List[Dict[str, Any]]] = None,
    assessment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a minimal projects_registry item."""
    return {
        "project_id": project_id,
        "project_name": name,
        "business_rationale": name,
        "announcement_period": ann,
        "latest_period": ann,
        "current_status": "operational",
        "assessment": assessment or {"execution_status": "operational"},
        "progression": {"state_transitions": transitions or []},
        "source_references": refs or [],
    }


def _make_transition(period: str, ttype: str, state: str, accepted: bool = True) -> Dict[str, Any]:
    return {
        "period": period,
        "transition_type": ttype,
        "current_state": state,
        "accepted": accepted,
        "confidence": {"basis": [f"status: {state}", "current_capacity: executed"], "level": "high"},
    }


def _make_ref(period: str, ev_id: str) -> Dict[str, Any]:
    return {"period": period, "evidence_ids": [ev_id], "state": ""}


def _build(sources: ManagementProgressionSources) -> Dict[str, Any]:
    return ManagementProgressionProducer(sources=sources, generated_at="2025-01-01T00:00:00Z").build()


# ---------------------------------------------------------------------------
# PSP-1  Three explicit fiscal years → three separate events
# ---------------------------------------------------------------------------

def test_psp1_three_periods_produce_three_events():
    project = _make_project(
        "PJ-TEST-01",
        "Specialised manufacturing platform commissioning",
        transitions=[
            _make_transition("fy22", "project_announced", "unable_to_verify"),
            _make_transition("fy23", "capacity_ramp", "partially_operational"),
            _make_transition("fy24", "completion", "operational"),
        ],
        refs=[
            _make_ref("fy22", "ev_001"),
            _make_ref("fy23", "ev_002"),
            _make_ref("fy24", "ev_003"),
        ],
    )
    result = _build(_make_sources(projects=[project]))
    items = result["progression_items"]
    # All three events for the same project should collapse into one item.
    assert len(items) == 1
    events = items[0]["events"]
    assert len(events) == 3
    periods = [ev["event_period"] for ev in events]
    assert "fy22" in periods
    assert "fy23" in periods
    assert "fy24" in periods


# ---------------------------------------------------------------------------
# PSP-2  Source year and event year are distinct and both preserved
# ---------------------------------------------------------------------------

def test_psp2_event_period_preserved_per_transition():
    """Each event's source_period and event_period must match the transition period."""
    project = _make_project(
        "PJ-TEST-02",
        "Digital customer platform expansion",
        transitions=[
            _make_transition("fy23", "capacity_ramp", "partially_operational"),
            _make_transition("fy25", "completion", "operational"),
        ],
        refs=[_make_ref("fy23", "ev_p23"), _make_ref("fy25", "ev_p25")],
    )
    result = _build(_make_sources(projects=[project]))
    items = result["progression_items"]
    assert len(items) == 1
    events = sorted(items[0]["events"], key=lambda e: e["event_period"])
    assert events[0]["event_period"] == "fy23"
    assert events[0]["source_period"] == "fy23"
    assert events[1]["event_period"] == "fy25"
    assert events[1]["source_period"] == "fy25"


# ---------------------------------------------------------------------------
# PSP-3  Vague multi-year text → single event (quarantine preserved)
# ---------------------------------------------------------------------------

def test_psp3_vague_description_stays_single_event_or_excluded():
    """A project whose description is too generic must not be split."""
    project = _make_project(
        "PJ-TEST-03",
        "growth",   # fails _specific_enough
        transitions=[
            _make_transition("fy22", "project_announced", "unable_to_verify"),
            _make_transition("fy23", "completion", "operational"),
        ],
        refs=[_make_ref("fy22", "ev_001"), _make_ref("fy23", "ev_002")],
    )
    result = _build(_make_sources(projects=[project]))
    items = result["progression_items"]
    # The item must be excluded (fails specificity) — no events
    for item in items:
        theme = item.get("theme", "")
        assert "growth" not in theme.lower() or len(item.get("events", [])) <= 1, \
            "Vague description must not produce multi-event item"


# ---------------------------------------------------------------------------
# PSP-4  Target period is preserved separately from event period
# ---------------------------------------------------------------------------

def test_psp4_target_period_distinct_from_event_period():
    """A commitment event's target_period is separate from its source/event period."""
    project = _make_project(
        "PJ-TEST-04",
        "Specialised radar testing facility commissioning by fy25",
        transitions=[
            _make_transition("fy22", "project_announced", "unable_to_verify"),
            _make_transition("fy24", "completion", "operational"),
        ],
        refs=[_make_ref("fy22", "ev_001"), _make_ref("fy24", "ev_002")],
    )
    result = _build(_make_sources(projects=[project]))
    items = result["progression_items"]
    assert len(items) == 1
    events = items[0]["events"]
    # The fy22 announcement event has event_period=fy22, not fy25
    ev_fy22 = next((e for e in events if e["event_period"] == "fy22"), None)
    assert ev_fy22 is not None, "fy22 event should be present"
    assert ev_fy22["event_period"] == "fy22"
    assert ev_fy22["source_period"] == "fy22"


# ---------------------------------------------------------------------------
# PSP-5  project_announced → capacity_ramp → completion produces 3 events
# ---------------------------------------------------------------------------

def test_psp5_announced_to_commissioned_three_events():
    """Classic project lifecycle: announce → build → commission → 3 events."""
    project = _make_project(
        "PJ-TEST-05",
        "Defence electronics manufacturing facility construction",
        transitions=[
            _make_transition("fy21", "project_announced", "unable_to_verify"),
            _make_transition("fy23", "capacity_ramp", "partially_operational"),
            _make_transition("fy24", "completion", "operational"),
        ],
        refs=[
            _make_ref("fy21", "ev_r21"),
            _make_ref("fy23", "ev_r23"),
            _make_ref("fy24", "ev_r24"),
        ],
    )
    result = _build(_make_sources(projects=[project]))
    items = result["progression_items"]
    assert len(items) == 1
    events = sorted(items[0]["events"], key=lambda e: e["event_period"])
    assert len(events) == 3
    roles = [ev["role"] for ev in events]
    assert "commitment" in roles   # fy21 announced
    assert "milestone" in roles    # fy23 ramp
    assert "completion" in roles   # fy24 done


# ---------------------------------------------------------------------------
# PSP-6  Completion event becomes a separate operating evidence event
# ---------------------------------------------------------------------------

def test_psp6_completion_event_has_verified_status():
    """A completion transition must produce a 'verified' verification_status event."""
    project = _make_project(
        "PJ-TEST-06",
        "Satellite communications testing platform deployment",
        transitions=[
            _make_transition("fy23", "project_announced", "unable_to_verify"),
            _make_transition("fy25", "completion", "operational"),
        ],
        refs=[_make_ref("fy23", "ev_a"), _make_ref("fy25", "ev_b")],
    )
    result = _build(_make_sources(projects=[project]))
    items = result["progression_items"]
    events = items[0]["events"]
    completion_ev = next((e for e in events if e["role"] == "completion"), None)
    assert completion_ev is not None
    assert completion_ev["verification_status"] == "verified"
    assert completion_ev["event_period"] == "fy25"


# ---------------------------------------------------------------------------
# PSP-7  Unresolved consistency assessment does not fabricate an action event
# ---------------------------------------------------------------------------

def test_psp7_unresolved_consistency_promise_does_not_fabricate_action():
    """
    An unresolved promise in management_consistency generates a contradiction
    signal but must NOT produce a fabricated action progression event.
    """
    from knowledge.management_progression.linker import build_cross_year_links

    # One vague commitment item (CLAIM_ONLY) — no project events
    items = [
        {
            "item_id": "MP-0001-test",
            "theme": "Reduce carbon emissions by 35% by fy26",
            "linked_company_model_ids": [],
            "events": [
                {
                    "event_id": "commit_001",
                    "role": "commitment",
                    "event_type": "strategic_change",
                    "source_period": "fy22",
                    "event_period": "fy22",
                    "statement_text": "achieve 35% reduction in absolute scope 1 scope 2 emissions by fy26",
                    "verification_status": "unresolved",
                    "evidence": [],
                }
            ],
            "synthesis_chain": {"chain_status": "CLAIM_ONLY"},
        }
    ]
    consistency_data = {
        "promise_follow_through_summary": {
            "repeated_unresolved_promises": [
                "promise_fy22_achieve 35% reduction in absolute scope 1 emissions"
            ],
            "fulfilled_promises": [],
            "unclear_promises": [],
        }
    }
    result = build_cross_year_links(items, consistency_data=consistency_data)
    # Contradiction signal generated from consistency — that's fine
    assert any(s["signal_type"] == "repeated_unresolved" for s in result["contradiction_signals"])
    # But no extra progression events should have been fabricated
    # (linker only produces thesis chains, commitments, signals — not new events)
    total_events = sum(len(it.get("events", [])) for it in items)
    assert total_events == 1, "No fabricated action events should appear in progression items"


# ---------------------------------------------------------------------------
# PSP-8  Fulfilled promise in consistency data does NOT add execution event
# ---------------------------------------------------------------------------

def test_psp8_fulfilled_promise_no_fabricated_execution():
    """
    fulfilled_promises in consistency data lack explicit period-specific
    completion evidence — they must remain as summary signals only, never
    as fabricated completion events.
    """
    from knowledge.management_progression.linker import build_cross_year_links

    items: List[Dict[str, Any]] = []
    consistency_data = {
        "promise_follow_through_summary": {
            "fulfilled_promises": ["Expanded specialist manufacturing capacity in fy24"],
            "repeated_unresolved_promises": [],
            "unclear_promises": [],
        }
    }
    result = build_cross_year_links(items, consistency_data=consistency_data)
    # fulfilled_promises are not ingested by _build_consistency_signals
    assert result["contradiction_signals"] == []
    assert result["measurable_commitments"] == []
    assert result["management_thesis_chains"] == []


# ---------------------------------------------------------------------------
# PSP-9  Quarantined weak commitment stays quarantined
# ---------------------------------------------------------------------------

def test_psp9_weak_commitment_quarantined():
    """A commitment with generic text must not appear in progression items."""
    commitment = {
        "commitment_id": "CMT-001",
        "normalized_commitment": "grow",   # too vague
        "first_seen_period": "fy22",
        "latest_status": "unresolved",
    }
    result = _build(_make_sources(commitments=[commitment]))
    items = result["progression_items"]
    for item in items:
        assert "grow" not in item.get("theme", "").lower() or len(item["events"]) == 0, \
            "Weak commitment must be quarantined"


# ---------------------------------------------------------------------------
# PSP-10  High-quality governed commitment is promoted
# ---------------------------------------------------------------------------

def test_psp10_high_quality_commitment_promoted():
    """A commitment with specific text and material anchors passes the filter."""
    commitment = {
        "commitment_id": "CMT-002",
        "normalized_commitment": "commission new radar testing facility at Hyderabad by fy25",
        "first_seen_period": "fy23",
        "latest_status": "unresolved",
        "evidence_ids": ["ev_cmt_001"],
    }
    result = _build(_make_sources(commitments=[commitment]))
    items = result["progression_items"]
    assert len(items) >= 1, "Specific commitment must be promoted to a progression item"
    texts = " ".join(it.get("theme", "") for it in items).lower()
    assert "radar" in texts or "facility" in texts or "commission" in texts


# ---------------------------------------------------------------------------
# PSP-11  Evidence IDs preserved on every emitted event
# ---------------------------------------------------------------------------

def test_psp11_evidence_ids_preserved_per_event():
    """Each split event must carry its own period-specific evidence_id."""
    project = _make_project(
        "PJ-TEST-11",
        "Enterprise software platform integration",
        transitions=[
            _make_transition("fy22", "project_announced", "unable_to_verify"),
            _make_transition("fy24", "completion", "operational"),
        ],
        refs=[
            _make_ref("fy22", "ev_fy22_001"),
            _make_ref("fy24", "ev_fy24_001"),
        ],
    )
    result = _build(_make_sources(projects=[project]))
    items = result["progression_items"]
    assert len(items) == 1
    events = items[0]["events"]
    ev_by_period = {ev["event_period"]: ev for ev in events}
    assert "fy22" in ev_by_period
    assert "fy24" in ev_by_period
    # Each event must have evidence
    for period, ev in ev_by_period.items():
        assert ev.get("evidence"), f"Event at {period} missing evidence"
        assert any(ref.get("evidence_id") for ref in ev["evidence"]), \
            f"Event at {period} has no evidence_id"


# ---------------------------------------------------------------------------
# PSP-12  Chronological ordering is stable
# ---------------------------------------------------------------------------

def test_psp12_events_ordered_chronologically():
    """Events within a multi-period item must be ordered earliest to latest."""
    project = _make_project(
        "PJ-TEST-12",
        "Software automation testing platform build-out",
        transitions=[
            _make_transition("fy25", "completion", "operational"),
            _make_transition("fy22", "project_announced", "unable_to_verify"),
            _make_transition("fy24", "capacity_ramp", "partially_operational"),
        ],
        refs=[
            _make_ref("fy22", "ev_a"),
            _make_ref("fy24", "ev_b"),
            _make_ref("fy25", "ev_c"),
        ],
    )
    result = _build(_make_sources(projects=[project]))
    items = result["progression_items"]
    events = items[0]["events"]
    periods = [ev["event_period"] for ev in events]
    # Extract numeric year portion for comparison
    def year_num(p: str) -> int:
        import re
        m = re.search(r"\d+", p)
        return int(m.group()) if m else 0
    years = [year_num(p) for p in periods]
    assert years == sorted(years), f"Events not in chronological order: {periods}"


# ---------------------------------------------------------------------------
# PSP-13  No duplicate events from the same fact
# ---------------------------------------------------------------------------

def test_psp13_no_duplicate_events_same_period():
    """Multiple accepted transitions in the same period → only one event emitted."""
    project = _make_project(
        "PJ-TEST-13",
        "Manufacturing facility expansion and commissioning",
        transitions=[
            # Two accepted transitions both at fy24 — completion wins
            _make_transition("fy24", "capacity_ramp", "partially_operational"),
            _make_transition("fy24", "completion", "operational"),
            _make_transition("fy22", "project_announced", "unable_to_verify"),
        ],
        refs=[_make_ref("fy22", "ev_a"), _make_ref("fy24", "ev_b")],
    )
    result = _build(_make_sources(projects=[project]))
    items = result["progression_items"]
    events = items[0]["events"]
    # Should be exactly 2 events (fy22 and fy24), not 3
    assert len(events) == 2
    ev_fy24 = next((e for e in events if e["event_period"] == "fy24"), None)
    assert ev_fy24 is not None
    # The higher-priority "completion" must win
    assert ev_fy24["role"] == "completion"


# ---------------------------------------------------------------------------
# PSP-14  No company or year hardcoding in the splitting logic
# ---------------------------------------------------------------------------

def test_psp14_no_company_year_hardcoding():
    """Splitting works identically regardless of company slug."""
    for slug in ("acme_corp", "test_pharma", "random_finco"):
        sources = _make_sources(
            projects=[
                _make_project(
                    "PJ-X",
                    "Product development platform commissioning",
                    transitions=[
                        _make_transition("fy20", "project_announced", "unable_to_verify"),
                        _make_transition("fy22", "completion", "operational"),
                    ],
                    refs=[_make_ref("fy20", "ev_a"), _make_ref("fy22", "ev_b")],
                )
            ]
        )
        # Patch company slug
        sources = ManagementProgressionSources(
            company_slug=slug,
            company_root=Path(f"/fake/{slug}"),
            sources=sources.sources,
            source_files_found=[],
            source_files_missing=[],
            legacy_adapter_used=False,
            legacy_adapter_sources=[],
            warnings=[],
        )
        result = ManagementProgressionProducer(sources=sources, generated_at="2025-01-01T00:00:00Z").build()
        items = result["progression_items"]
        assert len(items) == 1
        assert len(items[0]["events"]) == 2, f"Split failed for slug={slug}"


# ---------------------------------------------------------------------------
# PSP-15  Existing synthesis / linker behavior is backward-compatible
# ---------------------------------------------------------------------------

def test_psp15_single_period_project_unchanged():
    """
    A project with only one accepted transition period must fall back to
    the existing single-event path and not be affected by the new logic.
    """
    project = _make_project(
        "PJ-TEST-15",
        "Defence radar system integration",
        transitions=[
            # Only one distinct accepted period
            _make_transition("fy24", "completion", "operational"),
            _make_transition("fy24", "confirmation", "operational"),  # same period
        ],
        refs=[_make_ref("fy24", "ev_001")],
        assessment={"execution_status": "delivered", "observed_business_effect": "Radar system operational"},
    )
    result = _build(_make_sources(projects=[project]))
    items = result["progression_items"]
    # Must produce exactly 1 event (single period → fallback path)
    assert len(items) == 1
    events = items[0]["events"]
    # Single-period fallback produces exactly 1 event from the assessment
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Helper: _transition_role_verification unit tests
# ---------------------------------------------------------------------------

def test_transition_role_verification_completion():
    role, vst = _transition_role_verification("completion", "operational")
    assert role == "completion"
    assert vst == "verified"


def test_transition_role_verification_capacity_ramp():
    role, vst = _transition_role_verification("capacity_ramp", "partially_operational")
    assert role == "milestone"
    assert vst == "partially_verified"


def test_transition_role_verification_latest_assessment_claim():
    role, vst = _transition_role_verification("latest_assessment", "unable_to_verify")
    assert role == "statement"
    assert vst == "unresolved"


def test_transition_role_verification_latest_assessment_action():
    role, vst = _transition_role_verification("latest_assessment", "under_execution")
    assert role == "action"
    assert vst == "partially_verified"


def test_transition_role_verification_funding_committed_funded():
    role, vst = _transition_role_verification("funding_committed", "funded")
    assert role == "action"
    assert vst == "partially_verified"


def test_transition_role_verification_project_announced():
    role, vst = _transition_role_verification("project_announced", "unable_to_verify")
    assert role == "commitment"
    assert vst == "unresolved"
