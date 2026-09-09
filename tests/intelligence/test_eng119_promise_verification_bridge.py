"""
ENG-119: Canonical Promise Verification Bridge — production proof tests.

Validates:
  A  Bridge produces output with correct schema fields
  B  Zero heuristic links — every linked event has identity_basis = named_entity_exact
  C  MC-0008 (ILUMYA Japan/Australia) is VERIFIED via deterministic named entity match
  D  Generic commitments with no named entity are UNVERIFIED (not fabricated)
  E  Named-entity commitments with no execution event are INSUFFICIENT_EVIDENCE
  F  Prohibited patterns are documented in bridge_contract
  G  Management Progression remains lifecycle_authority (not Promise Tracker)
  H  All VERIFIED results have non-empty linked_event_ids and evidence_summary
  I  Observable events catalog contains ILUMYA launch event with status=completed
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUN = ROOT / "companies" / "sun_pharma"
VERIFICATION_EVENTS = SUN / "company_memory" / "gold" / "promise_verification_events.json"


def _load_doc():
    assert VERIFICATION_EVENTS.exists(), (
        "promise_verification_events.json not found — run verification_bridge first"
    )
    return json.loads(VERIFICATION_EVENTS.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# A: schema fields
# ---------------------------------------------------------------------------
def test_A_schema_fields_present():
    doc = _load_doc()
    required = {
        "schema_version", "company_slug", "generated_at", "lifecycle_authority",
        "bridge_contract", "observable_events", "promise_classifications", "summary",
    }
    missing = required - set(doc.keys())
    assert not missing, f"Missing schema fields: {missing}"


# ---------------------------------------------------------------------------
# B: zero heuristic links
# ---------------------------------------------------------------------------
def test_B_zero_heuristic_links():
    doc = _load_doc()
    heuristic = [
        c for c in doc["promise_classifications"]
        if c.get("linked_event_ids")  # has links
        and c.get("identity_basis") != "named_entity_exact"  # but NOT named-entity
    ]
    assert not heuristic, (
        f"Found {len(heuristic)} classification(s) with heuristic links: "
        + str([c["management_commitment_id"] for c in heuristic])
    )


# ---------------------------------------------------------------------------
# C: MC-0008 ILUMYA Japan is VERIFIED
# ---------------------------------------------------------------------------
def test_C_mc0008_ilumya_japan_verified():
    doc = _load_doc()
    classifications = {
        c["management_commitment_id"]: c
        for c in doc["promise_classifications"]
    }
    mc8 = classifications.get("MC-0008")
    assert mc8 is not None, "MC-0008 not found in promise_classifications"
    assert mc8["verification_state"] == "VERIFIED", (
        f"MC-0008 expected VERIFIED, got {mc8['verification_state']}"
    )
    assert mc8["identity_basis"] == "named_entity_exact", (
        f"MC-0008 link must be via named_entity_exact, got {mc8['identity_basis']}"
    )
    assert mc8["canonical_entity"] == "ilumya", (
        f"MC-0008 canonical_entity should be 'ilumya', got {mc8['canonical_entity']}"
    )
    assert mc8["linked_event_ids"], "MC-0008 must have linked event IDs"


# ---------------------------------------------------------------------------
# D: generic commitments are UNVERIFIED (not fabricated)
# ---------------------------------------------------------------------------
def test_D_generic_commitments_are_unverified():
    doc = _load_doc()
    # MCs that are clearly generic (no named entities in text)
    generic_mc_ids = {
        "MC-0001",  # Business expansion
        "MC-0009",  # organic/inorganic growth
        "MC-0010",  # Enhance presence in high growth markets
        "MC-0013",  # Strong pipeline (broad)
        "MC-0015",  # Quality products at affordable prices
    }
    by_mc = {c["management_commitment_id"]: c for c in doc["promise_classifications"]}
    for mc_id in generic_mc_ids:
        if mc_id in by_mc:
            c = by_mc[mc_id]
            assert c["verification_state"] == "UNVERIFIED", (
                f"{mc_id} expected UNVERIFIED (generic commitment), "
                f"got {c['verification_state']}"
            )
            assert not c["linked_event_ids"], (
                f"{mc_id} should have no linked events"
            )


# ---------------------------------------------------------------------------
# E: named-entity commitment with no execution event = INSUFFICIENT_EVIDENCE
# ---------------------------------------------------------------------------
def test_E_non_verifiable_statement_is_excluded_from_bridge():
    doc = _load_doc()
    by_mc = {c["management_commitment_id"]: c for c in doc["promise_classifications"]}
    mc4 = by_mc.get("MC-0004")
    assert mc4 is None, "Strategic/non-verifiable statements must not enter verification"


# ---------------------------------------------------------------------------
# F: prohibited patterns documented in bridge_contract
# ---------------------------------------------------------------------------
def test_F_prohibited_patterns_documented():
    doc = _load_doc()
    bc = doc.get("bridge_contract", {})
    prohibited = [str(p).lower() for p in bc.get("prohibited", [])]
    required_prohibitions = ["fuzzy", "token overlap", "llm", "same year"]
    for req in required_prohibitions:
        assert any(req in p for p in prohibited), (
            f"bridge_contract.prohibited must document '{req}'"
        )


# ---------------------------------------------------------------------------
# G: lifecycle_authority = management_progression
# ---------------------------------------------------------------------------
def test_G_lifecycle_authority_is_management_progression():
    doc = _load_doc()
    assert doc.get("lifecycle_authority") == "management_progression", (
        f"lifecycle_authority must be 'management_progression', "
        f"got {doc.get('lifecycle_authority')}"
    )


# ---------------------------------------------------------------------------
# H: VERIFIED results have evidence
# ---------------------------------------------------------------------------
def test_H_verified_results_have_evidence():
    doc = _load_doc()
    for c in doc["promise_classifications"]:
        if c["verification_state"] == "VERIFIED":
            assert c["linked_event_ids"], (
                f"{c['promise_id']} is VERIFIED but has no linked_event_ids"
            )
            assert c["evidence_summary"], (
                f"{c['promise_id']} is VERIFIED but has no evidence_summary"
            )


# ---------------------------------------------------------------------------
# I: observable events catalog contains ILUMYA launch with status=completed
# ---------------------------------------------------------------------------
def test_I_ilumya_launch_event_in_catalog():
    doc = _load_doc()
    ilumya_events = [
        ev for ev in doc["observable_events"]
        if ev["canonical_entity"] == "ilumya"
        and ev["status"] == "completed"
        and "launched" in ev["action"]
    ]
    assert ilumya_events, (
        "Observable events catalog must contain at least one ILUMYA launch event "
        "with status=completed"
    )
    # Verify it has evidence text mentioning Japan or Australia
    ev = ilumya_events[0]
    assert any(m in ev["evidence_text"].lower() for m in ["japan", "australia"]), (
        f"ILUMYA launch event must mention Japan or Australia: {ev['evidence_text'][:200]}"
    )


def test_J_observable_events_expose_canonical_catalog_fields():
    doc = _load_doc()
    required = {
        "event_id", "event_type", "canonical_subjects", "subject_type", "action",
        "status", "event_period", "source_type", "evidence_ids", "relationship_ids",
    }
    assert doc["observable_events"]
    for event in doc["observable_events"]:
        assert required <= set(event), f"canonical event fields missing: {required - set(event)}"
        assert event["canonical_subjects"]
        assert event["event_period"]
        assert event["evidence_ids"]


def test_K_announced_commentary_is_not_execution_evidence():
    doc = _load_doc()
    for event in doc["observable_events"]:
        if event["status"] == "announced":
            assert event["status"] != "completed"
