"""ENG-134: Management execution four-tier propagation tests.

12 fixture tests verifying the full propagation chain:
  MP.management_execution_outcomes → PCIM.management_execution_inputs → Committee → ASK

No external LLM calls. Tests use Sun Pharma production artifacts as fixtures.
Trusted baseline: SUN_PHARMA_POST_ENG133_STRICT_TRUSTED_BASELINE = 72/100.
"""
from __future__ import annotations

import json
from pathlib import Path


COMPANY_ROOT = Path(__file__).resolve().parents[2] / "companies" / "sun_pharma" / "company_memory"
MP_PATH = COMPANY_ROOT / "management_progression" / "management_progression.json"
PCIM_PATH = COMPANY_ROOT / "pcim_v1.json"
COMMITTEE_PATH = COMPANY_ROOT / "investor_panel" / "committee_synthesis.json"
ASK_PATH = COMPANY_ROOT / "ask_intrinsiciq" / "answer_cards.json"


def _mp():
    return json.loads(MP_PATH.read_text())

def _pcim():
    return json.loads(PCIM_PATH.read_text())

def _committee():
    return json.loads(COMMITTEE_PATH.read_text())

def _ask():
    return json.loads(ASK_PATH.read_text())


# ── 1. MP source counts ─────────────────────────────────────────────────────

def test_mp_eligible_count():
    cov = _mp()["management_execution_outcomes"]["coverage"]
    assert cov["management_execution_eligible"] == 22

def test_mp_visible_action_count():
    cov = _mp()["management_execution_outcomes"]["coverage"]
    assert cov["action_observed"] == 4

def test_mp_completed_count():
    cov = _mp()["management_execution_outcomes"]["coverage"]
    assert cov["execution_completed_or_operational"] == 2

def test_mp_observed_outcomes_zero():
    cov = _mp()["management_execution_outcomes"]["coverage"]
    assert cov["operating_outcome_observed"] == 0

def test_mp_attributable_zero():
    cov = _mp()["management_execution_outcomes"]["coverage"]
    assert cov["economic_consequence_attributable"] == 0

def test_mp_excluded_count():
    cov = _mp()["management_execution_outcomes"]["coverage"]
    assert cov["external_actor_events_excluded"] == 3


# ── 2. PCIM propagation ─────────────────────────────────────────────────────

def test_pcim_management_execution_inputs_present():
    mei = _pcim()["management_execution_inputs"]
    assert mei["available"] is True

def test_pcim_counts_match_mp():
    cov = _mp()["management_execution_outcomes"]["coverage"]
    mei = _pcim()["management_execution_inputs"]
    assert mei["eligible_records"] == cov["management_execution_eligible"]
    assert mei["visible_action"] == cov["action_observed"]
    assert mei["completed_or_operational"] == cov["execution_completed_or_operational"]
    assert mei["observed_outcomes"] == cov["operating_outcome_observed"]

def test_pcim_derived_counts():
    mei = _pcim()["management_execution_inputs"]
    assert mei["no_visible_action"] == mei["eligible_records"] - mei["visible_action"]  # 18
    assert mei["outcome_unproven"] == mei["completed_or_operational"] - mei["observed_outcomes"]  # 2

def test_pcim_semantic_contracts_present():
    mei = _pcim()["management_execution_inputs"]
    contracts = mei.get("semantic_contracts", [])
    assert any("NO_VISIBLE_ACTION_IN_EVIDENCE" in c for c in contracts)
    assert any("evidence gap" in c.lower() for c in contracts)


# ── 3. Committee accountability ─────────────────────────────────────────────

def test_committee_management_judgment_cites_execution_gap():
    mj = _committee()["management_judgment"]
    assess = mj.get("assessment", "")
    assert "22" in assess
    assert "4 of 22" in assess or "4" in assess

def test_committee_unresolved_issue_evidence_gap_framing():
    mj = _committee()["management_judgment"]
    unresolved = mj.get("unresolved_issue", "")
    # Must frame 18/22 as evidence gap, not non-execution
    assert "evidence gap" in unresolved.lower() or "not confirmed non-execution" in unresolved.lower()
    assert "18" in unresolved


# ── 4. ASK card propagation ─────────────────────────────────────────────────

def test_ask_execution_outcome_card_cites_four_tier_counts():
    cards = _ask()["answers"]
    card = next((c for c in cards if c.get("question_id") == "did-execution-lead-to-outcomes"), None)
    assert card is not None, "Card 'did-execution-lead-to-outcomes' not found"
    ans = card.get("simple_answer", "")
    assert "4 of 22" in ans
    assert "0 have an observed outcome" in ans or "0 have an" in ans
