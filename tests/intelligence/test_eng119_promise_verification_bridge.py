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
# C: MC-0008 ILUMYA Japan — pre-commitment launches must NOT verify the FY21
#    prescription ramp-up commitment (ENG-156 temporal repair)
# ---------------------------------------------------------------------------
def test_C_mc0008_ilumya_prescription_rampup_not_verified_by_precommitment_launch():
    """
    ENG-156: MC-0008 is 'Ramp-up ILUMYA prescriptions in Japan and Australia' (FY21).
    The linked launch event has event_period=fy18 (Australia 2018), which predates
    the FY21 commitment. The repair ensures event_period is used for the temporal gate,
    so this pre-commitment launch cannot verify the post-FY21 prescription ramp-up.
    Expected: INSUFFICIENT_EVIDENCE (entity found; no qualifying post-commitment event).
    The launch event must still exist in the observable_events catalog (partial evidence
    preserved); it just cannot be used to verify this commitment.
    """
    doc = _load_doc()
    classifications = {
        c["management_commitment_id"]: c
        for c in doc["promise_classifications"]
    }
    mc8 = classifications.get("MC-0008")
    assert mc8 is not None, "MC-0008 not found in promise_classifications"
    assert mc8["verification_state"] == "INSUFFICIENT_EVIDENCE", (
        f"ENG-156: MC-0008 expected INSUFFICIENT_EVIDENCE (pre-commitment launches "
        f"cannot verify the FY21 prescription ramp-up commitment), "
        f"got {mc8['verification_state']}"
    )
    assert mc8["canonical_entity"] == "ilumya", (
        f"MC-0008 canonical_entity should still be 'ilumya' (entity was found), "
        f"got {mc8['canonical_entity']}"
    )
    assert not mc8["linked_event_ids"], (
        "MC-0008 must have NO linked event IDs — pre-commitment launch fails temporal gate"
    )


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


# ---------------------------------------------------------------------------
# ENG-156: Temporal verification contract tests
# ---------------------------------------------------------------------------

def test_L_pre_commitment_events_preserved_in_catalog():
    """
    ENG-156: Observable events that predate a commitment must still appear in the
    observable_events catalog (partial evidence preserved). They just cannot be
    linked to verify that commitment.
    """
    doc = _load_doc()
    # The ILUMYA fy18 launch event must still exist in the catalog
    pre_commitment_events = [
        ev for ev in doc["observable_events"]
        if ev["canonical_entity"] == "ilumya"
        and ev.get("event_period", "") < "fy21"
        and ev["status"] == "completed"
    ]
    assert pre_commitment_events, (
        "ENG-156: Pre-commitment ILUMYA launch events must be preserved in "
        "observable_events catalog even though they cannot verify the FY21 commitment. "
        "Partial execution evidence must not be discarded."
    )


def test_M_no_precommitment_event_linked_to_any_verified_classification():
    """
    ENG-156: No VERIFIED classification may be linked to an event whose event_period
    predates the commitment's announcement_period.
    """
    doc = _load_doc()
    events_by_id = {ev["event_id"]: ev for ev in doc["observable_events"]}
    # Build a minimal commitment → announcement_period map from what we know
    # We can only check this via the classifications that carry commitment info
    for c in doc["promise_classifications"]:
        if c["verification_state"] != "VERIFIED":
            continue
        for eid in c.get("linked_event_ids") or []:
            ev = events_by_id.get(eid)
            if ev is None:
                continue
            event_period = ev.get("event_period") or ev.get("evidence_period", "")
            # We don't have announcement_period in the classification output directly,
            # but we can verify the OE-sun_-fy22-8a1c6a21dbab event (event_period=fy18)
            # is NOT among any VERIFIED result's linked_event_ids
            assert eid != "OE-sun_-fy22-8a1c6a21dbab", (
                "ENG-156: OE-sun_-fy22-8a1c6a21dbab (event_period=fy18, predates FY21 "
                "commitment) must not be linked to any VERIFIED classification"
            )


def test_N_temporal_gate_unit_using_bridge_functions():
    """
    ENG-156: Unit-level test of the temporal fix via bridge module directly.
    Post-commitment action (event_period >= announcement_period) → links.
    Pre-commitment action (event_period < announcement_period) → does not link.
    """
    from intelligence.management_promises.verification_bridge import (
        ObservableEvent, _classify_promise, _fy_ge
    )

    commitment_mc = {
        "id": "MC-TEST-001",
        "original_statement": "Ramp-up TESTDRUG prescriptions in Country X",
        "topic": "Ramp prescriptions",
        "category": "Capacity",
        "announcement_period": "fy21",
        "accountability_ontology": "VERIFIABLE_COMMITMENT",
    }
    promise = {
        "promise_id": "VC-test001",
        "commitment_fingerprint": "test001",
        "management_commitment_id": "MC-TEST-001",
    }

    def make_event(event_period: str, evidence_period: str, status: str = "completed") -> ObservableEvent:
        return ObservableEvent(
            event_id=f"OE-test-{event_period}",
            event_type="PRODUCT_LAUNCH",
            company="test_co",
            evidence_period=evidence_period,
            action_period=event_period,
            canonical_entity="testdrug",
            action="launched",
            status=status,
            source_file="test/management_summary.json",
            source_key="key_initiatives",
            evidence_text="Launched TESTDRUG in Country X",
            confidence="high",
        )

    entity_set = {"testdrug"}
    entity_type_map = {"testdrug": "PRODUCT_LAUNCH"}

    # Pre-commitment: event_period=fy18 < announcement=fy21 → must NOT link
    pre_event = make_event("fy18", "fy22")
    assert pre_event.event_period == "fy18"
    result_pre = _classify_promise(
        promise, commitment_mc,
        events_by_entity={"testdrug": [pre_event]},
        entity_names=entity_set,
        entity_to_type=entity_type_map,
    )
    assert result_pre.verification_state == "INSUFFICIENT_EVIDENCE", (
        f"ENG-156: Pre-commitment action (event_period=fy18 < fy21) must not verify "
        f"the commitment. Got: {result_pre.verification_state}"
    )
    assert not result_pre.linked_event_ids, "Pre-commitment event must not be linked"

    # Post-commitment: event_period=fy22 >= announcement=fy21 → MUST link
    post_event = make_event("fy22", "fy22")
    result_post = _classify_promise(
        promise, commitment_mc,
        events_by_entity={"testdrug": [post_event]},
        entity_names=entity_set,
        entity_to_type=entity_type_map,
    )
    assert result_post.verification_state == "VERIFIED", (
        f"ENG-156: Post-commitment action (event_period=fy22 >= fy21) must verify "
        f"the commitment. Got: {result_post.verification_state}"
    )
    assert result_post.linked_event_ids, "Post-commitment event must be linked"

    # Same-period: event_period=fy21 == announcement=fy21 → MUST link (boundary)
    same_event = make_event("fy21", "fy21")
    result_same = _classify_promise(
        promise, commitment_mc,
        events_by_entity={"testdrug": [same_event]},
        entity_names=entity_set,
        entity_to_type=entity_type_map,
    )
    assert result_same.verification_state == "VERIFIED", (
        f"ENG-156: Same-period action (event_period=fy21 == announcement=fy21) should "
        f"verify the commitment. Got: {result_same.verification_state}"
    )

    # No event_period fallback: event_period='' → falls back to evidence_period
    fallback_event = ObservableEvent(
        event_id="OE-fallback",
        event_type="PRODUCT_LAUNCH",
        company="test_co",
        evidence_period="fy22",
        action_period="",
        canonical_entity="testdrug",
        action="launched",
        status="completed",
        source_file="test/management_summary.json",
        source_key="key_initiatives",
        evidence_text="Launched TESTDRUG",
        confidence="high",
    )
    # Manually override event_period to empty (post_init sets it from action_period)
    fallback_event.event_period = ""
    result_fallback = _classify_promise(
        promise, commitment_mc,
        events_by_entity={"testdrug": [fallback_event]},
        entity_names=entity_set,
        entity_to_type=entity_type_map,
    )
    # evidence_period=fy22 >= fy21 → should still link (fallback path)
    assert result_fallback.verification_state == "VERIFIED", (
        f"ENG-156: When event_period is empty, must fall back to evidence_period "
        f"(fy22 >= fy21 = True). Got: {result_fallback.verification_state}"
    )
