"""
ENG-140 Regression Tests — Management Progression Evidence Chain

Verifies that every progression item carries resolvable exec_states and
source_items fields, that _status_to_current maps "operational" to "delivered",
and that ACTION_COMPLETED items have non-empty evidence references.

15 tests required by the ENG-140 closure gate.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from knowledge.management_progression.producer import (
    _status_to_current,
    _exec_states_for_item,
    _source_items_for_item,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item(item_id: str, current_status: str, events: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    return {
        "item_id": item_id,
        "current_status": current_status,
        "events": events or [],
    }


def _event(event_id: str, role: str, evidence: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    return {"event_id": event_id, "role": role, "evidence": evidence or []}


def _eref(evidence_id: str, source_artifact: str, source_item_id: str, source_period: str, excerpt: str) -> Dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "source_artifact": source_artifact,
        "source_item_id": source_item_id,
        "source_period": source_period,
        "excerpt": excerpt,
    }


def _meo_record(
    initiative_id: str,
    execution_state: str,
    evidence_ids: List[str],
    eligible: bool = True,
    outcome_state: str = "OUTCOME_NOT_DISCLOSED",
) -> Dict[str, Any]:
    return {
        "initiative_id": initiative_id,
        "execution_state": execution_state,
        "execution_evidence_ids": evidence_ids,
        "action_actor": "management",
        "management_execution_eligible": eligible,
        "outcome_state": outcome_state,
    }


# ---------------------------------------------------------------------------
# T01-T04 — _status_to_current mapping
# ---------------------------------------------------------------------------

def test_status_to_current_operational_is_delivered():
    """ENG-140 T01: 'operational' maps to 'delivered', not 'unresolved'."""
    assert _status_to_current("operational") == "delivered"


def test_status_to_current_operational_case_insensitive():
    """ENG-140 T02: 'Operational' (mixed case) also maps to 'delivered'."""
    assert _status_to_current("Operational") == "delivered"


def test_status_to_current_completed_still_delivered():
    """ENG-140 T03: 'completed' (pre-existing token) still maps to 'delivered'."""
    assert _status_to_current("completed") == "delivered"


def test_status_to_current_announced_is_unresolved():
    """ENG-140 T04: 'announced' has no delivered/in_progress signal → 'unresolved'."""
    assert _status_to_current("announced") == "unresolved"


# ---------------------------------------------------------------------------
# T05-T08 — _exec_states_for_item
# ---------------------------------------------------------------------------

def test_exec_states_empty_when_no_meo_record():
    """ENG-140 T05: Missing MEO record returns empty exec_states list."""
    assert _exec_states_for_item({}) == []


def test_exec_states_contains_execution_state():
    """ENG-140 T06: exec_states carries the execution_state from MEO record."""
    rec = _meo_record("MP-001", "ACTION_COMPLETED", ["ev_001"])
    result = _exec_states_for_item(rec)
    assert len(result) == 1
    assert result[0]["execution_state"] == "ACTION_COMPLETED"


def test_exec_states_carries_evidence_ids():
    """ENG-140 T07: exec_states preserves execution_evidence_ids."""
    rec = _meo_record("MP-001", "ACTION_COMPLETED", ["ev_001", "ev_002"])
    result = _exec_states_for_item(rec)
    assert result[0]["evidence_ids"] == ["ev_001", "ev_002"]


def test_exec_states_carries_eligibility():
    """ENG-140 T08: exec_states preserves management_execution_eligible flag."""
    rec = _meo_record("MP-001", "ANNOUNCED", [], eligible=False)
    result = _exec_states_for_item(rec)
    assert result[0]["management_execution_eligible"] is False


# ---------------------------------------------------------------------------
# T09-T12 — _source_items_for_item
# ---------------------------------------------------------------------------

def test_source_items_empty_when_no_events():
    """ENG-140 T09: Item with no events returns empty source_items."""
    item = _item("MP-001", "announced")
    assert _source_items_for_item(item) == []


def test_source_items_populated_from_evidence():
    """ENG-140 T10: source_items extracted from events[].evidence[]."""
    eref = _eref("ev_001", "projects_registry.json", "PJ-001", "fy23", "Some passage text")
    item = _item("MP-001", "delivered", [_event("EVT-1", "completion", [eref])])
    result = _source_items_for_item(item)
    assert len(result) == 1
    assert result[0]["evidence_id"] == "ev_001"
    assert result[0]["source_artifact"] == "projects_registry.json"
    assert result[0]["passage"] == "Some passage text"


def test_source_items_deduplication():
    """ENG-140 T11: Duplicate evidence_id across events is deduplicated."""
    eref = _eref("ev_001", "projects_registry.json", "PJ-001", "fy23", "passage")
    item = _item("MP-001", "delivered", [
        _event("EVT-1", "statement", [eref]),
        _event("EVT-2", "confirmation", [eref]),
    ])
    result = _source_items_for_item(item)
    assert len(result) == 1


def test_source_items_carries_event_role():
    """ENG-140 T12: source_items preserves the event's role."""
    eref = _eref("ev_002", "clean_projects.json", "PJ-002", "fy22", "text")
    item = _item("MP-002", "delivered", [_event("EVT-1", "completion", [eref])])
    result = _source_items_for_item(item)
    assert result[0]["event_role"] == "completion"


# ---------------------------------------------------------------------------
# T13-T15 — Integration: build() populates both fields for Sun Pharma
# ---------------------------------------------------------------------------

def test_all_items_have_exec_states_populated():
    """ENG-140 T13: Every progression item must have exec_states after build()."""
    pytest.importorskip("companies")  # skip gracefully if data not available
    from pathlib import Path
    if not Path("companies/sun_pharma").exists():
        pytest.skip("sun_pharma data not available")
    from knowledge.management_progression.producer import build_management_progression
    payload = build_management_progression("sun_pharma")
    items = payload["progression_items"]
    empty = [i["item_id"] for i in items if not i.get("exec_states")]
    assert empty == [], f"Items missing exec_states: {empty}"


def test_all_items_have_source_items_populated():
    """ENG-140 T14: Every progression item must have source_items after build()."""
    from pathlib import Path
    if not Path("companies/sun_pharma").exists():
        pytest.skip("sun_pharma data not available")
    from knowledge.management_progression.producer import build_management_progression
    payload = build_management_progression("sun_pharma")
    items = payload["progression_items"]
    empty = [i["item_id"] for i in items if not i.get("source_items")]
    assert empty == [], f"Items missing source_items: {empty}"


def test_action_completed_items_have_evidence_ids():
    """ENG-140 T15: ACTION_COMPLETED items must carry at least one evidence_id in exec_states."""
    from pathlib import Path
    if not Path("companies/sun_pharma").exists():
        pytest.skip("sun_pharma data not available")
    from knowledge.management_progression.producer import build_management_progression
    payload = build_management_progression("sun_pharma")
    items = payload["progression_items"]
    violations = []
    for item in items:
        es = item.get("exec_states", [])
        if not es:
            continue
        if es[0].get("execution_state") == "ACTION_COMPLETED":
            if not es[0].get("evidence_ids"):
                violations.append(item["item_id"])
    assert violations == [], f"ACTION_COMPLETED items with no evidence_ids: {violations}"
