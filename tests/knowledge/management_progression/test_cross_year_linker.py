"""
Tests for the Multi-Year Management Evidence Linker (Mission 5).

Coverage:
  ML-1   Same initiative, different wording → linked (model + ≥4 anchor words)
  ML-2   Different initiatives, only 3 shared anchors → NOT linked (below threshold)
  ML-3   Shared evidence ID → linked even with no model IDs
  ML-4   Transitive chain: A-B and B-C both linked → single chain A-B-C
  ML-5   Chain evolution ordered chronologically (oldest first)
  ML-6   Single-item groups excluded from thesis chains
  ML-7  strongest_chain_status = highest status across all linked items
  ML-8  Measurable % target extracted from commitment event
  ML-9  Measurable branch-count target extracted from commitment event
  ML-10 Delivery status ACHIEVED when later completion event verified
  ML-11 Delivery status UNVERIFIED when no later evidence
  ML-12 Delivery status ABANDONED when later abandonment event present
  ML-13 Contradiction signal: explicit contradiction (verification_status == "contradicted")
  ML-14 Contradiction signal: repeated_unresolved commitment across ≥3 years
  ML-15 No company/year hardcoding (fictional company + fictional years)
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from knowledge.management_progression.linker import (
    _DELIVERY_STATUSES,
    _items_are_linked,
    build_cross_year_links,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ev(
    *,
    role: str = "action",
    source_period: str = "fy22",
    statement_text: str = "",
    action_taken: str = "",
    operational_outcome: str = "",
    verification_status: str = "unresolved",
    evidence: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    return {
        "role": role,
        "event_type": "project_execution",
        "source_period": source_period,
        "event_period": source_period,
        "statement_text": statement_text,
        "action_taken": action_taken,
        "operational_outcome": operational_outcome,
        "verification_status": verification_status,
        "evidence": evidence or [],
    }


def _item(
    item_id: str,
    theme: str,
    *,
    models: List[str] | None = None,
    events: List[Dict[str, Any]] | None = None,
    chain_status: str = "ACTION_STARTED",
) -> Dict[str, Any]:
    return {
        "item_id": item_id,
        "theme": theme,
        "linked_company_model_ids": models or [],
        "events": events or [],
        "synthesis_chain": {"chain_status": chain_status},
    }


def _evref(evidence_id: str) -> Dict[str, Any]:
    return {"evidence_id": evidence_id, "source_artifact": "test.json"}


# ---------------------------------------------------------------------------
# ML-1: Same initiative, different wording → linked (model + ≥4 anchor words)
# ---------------------------------------------------------------------------


def test_ml1_same_initiative_different_wording_linked():
    """
    Two items about the same IPSOS customer-satisfaction assessment programme,
    phrased differently across years. Should be linked via model overlap + ≥4
    shared anchor words.
    """
    items = [
        _item(
            "MP-0001",
            "Commissioned IPSOS to independently assess current levels of customer satisfaction",
            models=["retail_credit_products"],
            events=[_ev(role="action", source_period="fy24")],
        ),
        _item(
            "MP-0009",
            "Independent research agency IPSOS commissioned to assess customer satisfaction levels",
            models=["retail_credit_products"],
            events=[_ev(role="action", source_period="fy23")],
        ),
    ]
    result = build_cross_year_links(items)
    chains = result["management_thesis_chains"]
    assert len(chains) == 1, f"Expected 1 thesis chain, got {len(chains)}"
    linked = set(chains[0]["linked_item_ids"])
    assert linked == {"MP-0001", "MP-0009"}
    assert chains[0]["link_basis"] == "model_and_word_overlap"


# ---------------------------------------------------------------------------
# ML-2: Below threshold (3 shared anchors, not 4) → NOT linked
# ---------------------------------------------------------------------------


def test_ml2_below_threshold_not_linked():
    """
    Two items share a model and exactly 3 specific anchor words ('robust',
    'grievance', 'mechanism') but not 4. Should NOT be linked.
    """
    items = [
        _item(
            "MP-A",
            "Robust grievance mechanism for complaints",  # anchors: robust, grievance, mechanism, complaints
            models=["retail_ops"],
            events=[_ev(source_period="fy22")],
        ),
        _item(
            "MP-B",
            "Robust grievance mechanism for digital users only",  # anchors: robust, grievance, mechanism, digital
            models=["retail_ops"],
            events=[_ev(source_period="fy24")],
        ),
    ]
    # "robust" (6), "grievance" (9), "mechanism" (9) = 3 shared anchors < threshold 4
    # "complaints" vs "digital" not shared
    result = build_cross_year_links(items)
    chains = result["management_thesis_chains"]
    assert len(chains) == 0, "Items below threshold must not be linked"


# ---------------------------------------------------------------------------
# ML-3: Shared evidence ID → linked even without model IDs
# ---------------------------------------------------------------------------


def test_ml3_shared_evidence_id_links_without_models():
    items = [
        _item(
            "MP-X",
            "Toansa API facility USFDA prohibition January 2014",
            models=[],
            events=[_ev(role="action", source_period="fy14", evidence=[_evref("ev_source_001")])],
        ),
        _item(
            "MP-Y",
            "Supply disruption from Toansa plant following regulatory ban",
            models=[],
            events=[_ev(role="outcome", source_period="fy15", evidence=[_evref("ev_source_001")])],
        ),
    ]
    result = build_cross_year_links(items)
    chains = result["management_thesis_chains"]
    assert len(chains) == 1
    assert set(chains[0]["linked_item_ids"]) == {"MP-X", "MP-Y"}
    assert chains[0]["link_basis"] == "shared_evidence"


# ---------------------------------------------------------------------------
# ML-4: Transitive chain A-B and B-C → single chain A-B-C
# ---------------------------------------------------------------------------


def test_ml4_transitive_chain_merges_three_items():
    """
    A and B are linked (shared evidence); B and C are linked (model + word overlap).
    All three should form a single thesis chain.
    """
    ev_shared = _evref("ev_common_001")
    items = [
        _item(
            "MP-A",
            "Established robust grievance redressal mechanism customer complaints",
            models=["banking_ops"],
            events=[_ev(source_period="fy22", evidence=[ev_shared])],
            chain_status="CLAIM_ONLY",
        ),
        _item(
            "MP-B",
            "Grievance redressal mechanism customer complaints tracking portal launched",
            models=["banking_ops"],
            events=[_ev(source_period="fy23", evidence=[ev_shared])],
            chain_status="ACTION_STARTED",
        ),
        _item(
            "MP-C",
            "Established robust grievance redressal mechanism customer complaints resolution portal",
            models=["banking_ops"],
            events=[_ev(source_period="fy24")],
            chain_status="ACTION_COMPLETED",
        ),
    ]
    result = build_cross_year_links(items)
    chains = result["management_thesis_chains"]
    assert len(chains) == 1, f"Expected 1 chain, got {len(chains)}: {[c['linked_item_ids'] for c in chains]}"
    linked = set(chains[0]["linked_item_ids"])
    assert linked == {"MP-A", "MP-B", "MP-C"}


# ---------------------------------------------------------------------------
# ML-5: Chain evolution ordered chronologically (oldest first)
# ---------------------------------------------------------------------------


def test_ml5_chain_evolution_chronological_order():
    """
    Item A has events in fy24; item B has events in fy22.
    chain_evolution should list B before A (chronological, oldest first).
    """
    items = [
        _item(
            "MP-A",
            "Commissioned IPSOS to assess customer satisfaction independently annually",
            models=["retail_credit"],
            events=[_ev(source_period="fy24")],
        ),
        _item(
            "MP-B",
            "Commissioned IPSOS to independently assess customer satisfaction annually",
            models=["retail_credit"],
            events=[_ev(source_period="fy22")],
        ),
    ]
    result = build_cross_year_links(items)
    chains = result["management_thesis_chains"]
    assert len(chains) == 1
    periods = [entry["period"] for entry in chains[0]["chain_evolution"]]
    assert periods[0] == "fy22", f"Expected fy22 first, got: {periods}"
    assert periods[1] == "fy24"


# ---------------------------------------------------------------------------
# ML-6: Single-item groups excluded from thesis chains
# ---------------------------------------------------------------------------


def test_ml6_solo_items_not_included_in_thesis_chains():
    """
    Three items: MP-A and MP-B are linked; MP-C is isolated.
    Thesis chains must contain exactly one chain (A-B). MP-C is excluded.
    """
    items = [
        _item(
            "MP-A",
            "Commissioned IPSOS assess customer satisfaction independently annually",
            models=["retail_credit"],
            events=[_ev(source_period="fy22")],
        ),
        _item(
            "MP-B",
            "Commissioned IPSOS independently assess customer satisfaction annually",
            models=["retail_credit"],
            events=[_ev(source_period="fy23")],
        ),
        _item(
            "MP-C",
            "Capex allocation for new manufacturing plant greenfield brownfield expansion",
            models=["manufacturing"],
            events=[_ev(source_period="fy22")],
        ),
    ]
    result = build_cross_year_links(items)
    chains = result["management_thesis_chains"]
    assert len(chains) == 1
    all_ids = set(chains[0]["linked_item_ids"])
    assert "MP-C" not in all_ids, "Isolated item MP-C must not appear in any thesis chain"


# ---------------------------------------------------------------------------
# ML-7: strongest_chain_status = highest status across linked items
# ---------------------------------------------------------------------------


def test_ml7_strongest_chain_status_reflects_highest_item():
    items = [
        _item(
            "MP-A",
            "Commissioned IPSOS assess customer satisfaction independently annually",
            models=["retail_credit"],
            events=[_ev(source_period="fy22")],
            chain_status="ACTION_COMPLETED",
        ),
        _item(
            "MP-B",
            "Commissioned IPSOS independently assess customer satisfaction annually results",
            models=["retail_credit"],
            events=[_ev(source_period="fy23")],
            chain_status="EARLY_OPERATING_SIGNAL",
        ),
    ]
    result = build_cross_year_links(items)
    chains = result["management_thesis_chains"]
    assert len(chains) == 1
    assert chains[0]["strongest_chain_status"] == "EARLY_OPERATING_SIGNAL"


# ---------------------------------------------------------------------------
# ML-8: Measurable % target extracted from commitment event
# ---------------------------------------------------------------------------


def test_ml8_percentage_target_extracted_from_commitment():
    items = [
        _item(
            "MP-COMMIT",
            "Reduce carbon emissions",
            models=["sustainability"],
            events=[
                _ev(
                    role="commitment",
                    statement_text="Achieve a 35% reduction in absolute Scope 1 and Scope 2 carbon emissions compared to the FY2020 baseline by fy30.",
                    source_period="fy24",
                )
            ],
        )
    ]
    result = build_cross_year_links(items)
    commitments = result["measurable_commitments"]
    assert len(commitments) >= 1, "Expected at least one measurable commitment"
    c = commitments[0]
    assert "35%" in c["extracted_target"].lower() or "35" in c["extracted_target"]
    assert c["source_item_id"] == "MP-COMMIT"
    assert c["source_period"] == "fy24"
    assert c["delivery_status"] in _DELIVERY_STATUSES


# ---------------------------------------------------------------------------
# ML-9: Measurable branch-count target extracted from commitment event
# ---------------------------------------------------------------------------


def test_ml9_branch_count_target_extracted():
    items = [
        _item(
            "MP-BRANCH",
            "Expand branch network",
            models=["retail_distribution"],
            events=[
                _ev(
                    role="commitment",
                    statement_text="Target to open 200 new branches in underserved regions by fy26.",
                    source_period="fy23",
                )
            ],
        )
    ]
    result = build_cross_year_links(items)
    commitments = result["measurable_commitments"]
    assert len(commitments) >= 1
    c = commitments[0]
    assert "200" in c["extracted_target"]


# ---------------------------------------------------------------------------
# ML-10: Delivery status ACHIEVED when later completion event is verified
# ---------------------------------------------------------------------------


def test_ml10_delivery_achieved_when_later_completion_verified():
    items = [
        _item(
            "MP-PROMISE",
            "Target R&D spend commitment measurable annual",
            models=["r_and_d"],
            events=[
                _ev(
                    role="commitment",
                    statement_text="Target R&D spend of 6.1% of sales by fy26.",
                    source_period="fy23",
                    verification_status="unresolved",
                ),
                _ev(
                    role="completion",
                    action_taken="R&D spend reached 6.2% of net sales in FY2026.",
                    source_period="fy26",
                    verification_status="verified",
                ),
            ],
        )
    ]
    result = build_cross_year_links(items)
    commitments = result["measurable_commitments"]
    assert commitments, "Expected a measurable commitment to be extracted"
    assert commitments[0]["delivery_status"] == "ACHIEVED"


# ---------------------------------------------------------------------------
# ML-11: Delivery status UNVERIFIED when no later evidence
# ---------------------------------------------------------------------------


def test_ml11_delivery_unverified_when_no_later_evidence():
    items = [
        _item(
            "MP-UNVERIFIED",
            "Carbon commitment measurable target reduction",
            models=["sustainability"],
            events=[
                _ev(
                    role="commitment",
                    statement_text="Achieve 40% reduction in carbon intensity by fy30.",
                    source_period="fy24",
                    verification_status="unresolved",
                )
            ],
        )
    ]
    result = build_cross_year_links(items)
    commitments = result["measurable_commitments"]
    assert commitments, "Expected a measurable commitment"
    assert commitments[0]["delivery_status"] == "UNVERIFIED"


# ---------------------------------------------------------------------------
# ML-12: Delivery status ABANDONED when later abandonment event present
# ---------------------------------------------------------------------------


def test_ml12_delivery_abandoned_when_abandonment_event():
    items = [
        _item(
            "MP-ABANDONED",
            "Branch expansion target commitment measurable",
            models=["retail_distribution"],
            events=[
                _ev(
                    role="commitment",
                    statement_text="Target 500 new branches by fy27.",
                    source_period="fy23",
                    verification_status="unresolved",
                ),
                _ev(
                    role="abandonment",
                    action_taken="Branch expansion programme discontinued following strategic review.",
                    source_period="fy25",
                    verification_status="verified",
                ),
            ],
        )
    ]
    result = build_cross_year_links(items)
    commitments = result["measurable_commitments"]
    assert commitments, "Expected a measurable commitment"
    assert commitments[0]["delivery_status"] == "ABANDONED"


# ---------------------------------------------------------------------------
# ML-13: Contradiction signal — explicit contradiction via verification_status
# ---------------------------------------------------------------------------


def test_ml13_explicit_contradiction_flagged():
    """
    Item has a commitment in fy22, and a later event in fy25 with
    verification_status == "contradicted". This must generate an explicit_contradiction signal.
    """
    items = [
        _item(
            "MP-CONTRA",
            "Promise to maintain leadership in specialty segment",
            models=["pharma_specialty"],
            events=[
                _ev(
                    role="commitment",
                    statement_text="Management committed to maintain number-one market position in specialty.",
                    source_period="fy22",
                    verification_status="unresolved",
                ),
                _ev(
                    role="statement",
                    statement_text="Specialty market share has declined materially due to competition.",
                    source_period="fy25",
                    verification_status="contradicted",
                ),
            ],
        )
    ]
    result = build_cross_year_links(items)
    signals = result["contradiction_signals"]
    assert len(signals) >= 1
    s = signals[0]
    assert s["signal_type"] == "explicit_contradiction"
    assert s["source_item_id"] == "MP-CONTRA"
    assert s["earlier_period"] == "fy22"
    assert s["later_period"] == "fy25"
    assert s["contradiction_type"] == "claim_contradicted"


# ---------------------------------------------------------------------------
# ML-14: Contradiction signal — repeated_unresolved across ≥3 years
# ---------------------------------------------------------------------------


def test_ml14_repeated_unresolved_commitment_flagged():
    """
    An item has a commitment event in fy20 and another commitment event in fy23
    (gap = 3 years), both still unresolved. This must generate a repeated_unresolved signal.
    """
    items = [
        _item(
            "MP-REPEAT",
            "Promise to expand into new therapeutic areas",
            models=["pharma_pipeline"],
            events=[
                _ev(
                    role="commitment",
                    statement_text="We continue to focus on identifying future R&D projects in new therapeutic areas.",
                    source_period="fy20",
                    verification_status="unresolved",
                ),
                _ev(
                    role="commitment",
                    statement_text="We continue disciplined identification of future R&D projects.",
                    source_period="fy23",
                    verification_status="unresolved",
                ),
            ],
        )
    ]
    result = build_cross_year_links(items)
    signals = result["contradiction_signals"]
    assert len(signals) >= 1
    s = signals[0]
    assert s["signal_type"] == "repeated_unresolved"
    assert s["contradiction_type"] == "commitment_repeated_unresolved"
    assert s["source_item_id"] == "MP-REPEAT"


# ---------------------------------------------------------------------------
# ML-15: No company/year hardcoding (fictional company + years)
# ---------------------------------------------------------------------------


def test_ml15_no_company_year_hardcoding():
    """
    Fictional company 'acme_widgets', fictional years 'fy12' and 'fy14'.
    Two items with shared model + ≥4 anchor words should still form a thesis chain.
    """
    items = [
        _item(
            "MW-0001",
            "Commissioned external agency widget quality assessment inspection process annual",
            models=["widget_production"],
            events=[_ev(source_period="fy12")],
            chain_status="ACTION_COMPLETED",
        ),
        _item(
            "MW-0002",
            "External agency widget quality assessment inspection process commissioned annually",
            models=["widget_production"],
            events=[_ev(source_period="fy14")],
            chain_status="OUTCOME_POSITIVE",
        ),
    ]
    result = build_cross_year_links(items)
    chains = result["management_thesis_chains"]
    assert len(chains) == 1, "Fictional company/year data must link correctly"
    linked = set(chains[0]["linked_item_ids"])
    assert linked == {"MW-0001", "MW-0002"}
    assert chains[0]["strongest_chain_status"] == "OUTCOME_POSITIVE"
    # Chain evolution should have fy12 before fy14
    periods = [e["period"] for e in chains[0]["chain_evolution"]]
    assert periods[0] == "fy12"


# ---------------------------------------------------------------------------
# ML-16: Thesis chain shows state advancement (CLAIM_ONLY → ACTION_STARTED)
# ---------------------------------------------------------------------------


def test_ml16_thesis_chain_shows_state_advancement():
    """
    Two linked items: older one is CLAIM_ONLY, newer one is ACTION_STARTED.
    The chain_evolution must preserve both statuses in chronological order,
    and strongest_chain_status = ACTION_STARTED.
    """
    items = [
        _item(
            "MP-CLAIM",
            "Commissioned IPSOS to independently assess customer satisfaction annually strategy",
            models=["retail_credit"],
            events=[_ev(source_period="fy22")],
            chain_status="CLAIM_ONLY",
        ),
        _item(
            "MP-ACTION",
            "Commissioned IPSOS independently assess customer satisfaction annually programme",
            models=["retail_credit"],
            events=[_ev(source_period="fy24")],
            chain_status="ACTION_STARTED",
        ),
    ]
    result = build_cross_year_links(items)
    chains = result["management_thesis_chains"]
    assert len(chains) == 1
    evolution = chains[0]["chain_evolution"]
    assert evolution[0]["period"] == "fy22"
    assert evolution[0]["chain_status"] == "CLAIM_ONLY"
    assert evolution[1]["period"] == "fy24"
    assert evolution[1]["chain_status"] == "ACTION_STARTED"
    assert chains[0]["strongest_chain_status"] == "ACTION_STARTED"


# ---------------------------------------------------------------------------
# ML-17: Thesis chain with ACTION_STARTED → OUTCOME_POSITIVE shows advancement
# ---------------------------------------------------------------------------


def test_ml17_thesis_chain_action_to_outcome_positive():
    """
    Two linked items: fy23 ACTION_STARTED and fy25 OUTCOME_POSITIVE.
    strongest_chain_status must be OUTCOME_POSITIVE.
    """
    items = [
        _item(
            "MP-ACT",
            "Commissioned IPSOS assess customer satisfaction independently annually results",
            models=["retail_credit"],
            events=[_ev(source_period="fy23")],
            chain_status="ACTION_STARTED",
        ),
        _item(
            "MP-OUT",
            "Commissioned IPSOS independently assess customer satisfaction annually outcomes",
            models=["retail_credit"],
            events=[_ev(source_period="fy25")],
            chain_status="OUTCOME_POSITIVE",
        ),
    ]
    result = build_cross_year_links(items)
    chains = result["management_thesis_chains"]
    assert len(chains) == 1
    assert chains[0]["strongest_chain_status"] == "OUTCOME_POSITIVE"


# ---------------------------------------------------------------------------
# ML-18: Delivery status DELAYED (target period passed, activity still ongoing)
# ---------------------------------------------------------------------------


def test_ml18_delivery_delayed_when_target_period_passed():
    """
    Commitment (fy22, target_period=fy24).
    Later action event exists in fy25 (after fy24) but is NOT a completion.
    Delivery status must be DELAYED (target date passed, still executing).
    """
    items = [
        _item(
            "MP-DELAY",
            "Carbon commitment measurable target reduction emission",
            models=["sustainability"],
            events=[
                _ev(
                    role="commitment",
                    statement_text="Achieve 40% reduction in carbon intensity by fy24.",
                    source_period="fy22",
                    verification_status="unresolved",
                ),
                _ev(
                    role="action",
                    action_taken="Carbon reduction programme still under implementation as of fy25.",
                    source_period="fy25",
                    verification_status="unresolved",
                ),
            ],
        )
    ]
    result = build_cross_year_links(items)
    commitments = result["measurable_commitments"]
    assert commitments, "Expected a measurable commitment"
    assert commitments[0]["delivery_status"] == "DELAYED"


# ---------------------------------------------------------------------------
# ML-19: Delivery status PARTIALLY_ACHIEVED for partially-verified completion
# ---------------------------------------------------------------------------


def test_ml19_delivery_partially_achieved():
    """
    Commitment event in fy22, later completion event with verification_status
    == "partially_verified". Delivery status must be PARTIALLY_ACHIEVED.
    """
    items = [
        _item(
            "MP-PARTIAL",
            "Branch expansion target measurable commitment reduction",
            models=["retail_distribution"],
            events=[
                _ev(
                    role="commitment",
                    statement_text="Target to open 200 new branches by fy25.",
                    source_period="fy22",
                    verification_status="unresolved",
                ),
                _ev(
                    role="completion",
                    action_taken="Opened 120 of the targeted 200 branches; remainder deferred to fy26.",
                    source_period="fy25",
                    verification_status="partially_verified",
                ),
            ],
        )
    ]
    result = build_cross_year_links(items)
    commitments = result["measurable_commitments"]
    assert commitments, "Expected a measurable commitment"
    assert commitments[0]["delivery_status"] == "PARTIALLY_ACHIEVED"


# ---------------------------------------------------------------------------
# ML-20: Target MISSED only with affirmative contradicted evidence
# ---------------------------------------------------------------------------


def test_ml20_missed_requires_affirmative_contradicted_evidence():
    """
    Commitment event in fy22. Later event has verification_status == "contradicted".
    Delivery status must be MISSED (not UNVERIFIED — explicit contradiction present).
    """
    items = [
        _item(
            "MP-MISSED",
            "Target commitment measurable market position specialty",
            models=["pharma_specialty"],
            events=[
                _ev(
                    role="commitment",
                    statement_text="Target 30% revenue growth by fy25.",
                    source_period="fy22",
                    verification_status="unresolved",
                ),
                _ev(
                    role="outcome",
                    action_taken="Revenue declined 10% in fy25 versus the prior year.",
                    source_period="fy25",
                    verification_status="contradicted",
                ),
            ],
        )
    ]
    result = build_cross_year_links(items)
    commitments = result["measurable_commitments"]
    assert commitments, "Expected a measurable commitment"
    assert commitments[0]["delivery_status"] == "MISSED"


def test_ml20b_no_later_evidence_never_missed():
    """
    Commitment with no later events must be UNVERIFIED, never MISSED.
    Silence is not failure.
    """
    items = [
        _item(
            "MP-SILENT",
            "Target commitment measurable market growth segment",
            models=["pharma"],
            events=[
                _ev(
                    role="commitment",
                    statement_text="Target 25% market share growth by fy27.",
                    source_period="fy24",
                    verification_status="unresolved",
                )
            ],
        )
    ]
    result = build_cross_year_links(items)
    commitments = result["measurable_commitments"]
    assert commitments, "Expected a measurable commitment"
    assert commitments[0]["delivery_status"] == "UNVERIFIED", (
        "Absence of later evidence must be UNVERIFIED, not MISSED"
    )


# ---------------------------------------------------------------------------
# ML-21: Evidence IDs preserved through thesis chain
# ---------------------------------------------------------------------------


def test_ml21_evidence_ids_preserved_in_thesis_chain():
    """
    Items with specific evidence IDs must retain those IDs after cross-year linking.
    The thesis chain references item_ids; the items themselves still carry evidence.
    """
    ev_a = _evref("ev_real_doc_001")
    ev_b = _evref("ev_real_doc_002")
    items = [
        _item(
            "MP-EV-A",
            "Commissioned IPSOS assess customer satisfaction independently strategy",
            models=["retail_credit"],
            events=[_ev(source_period="fy22", evidence=[ev_a])],
        ),
        _item(
            "MP-EV-B",
            "Commissioned IPSOS independently assess customer satisfaction annually",
            models=["retail_credit"],
            events=[_ev(source_period="fy24", evidence=[ev_b])],
        ),
    ]
    result = build_cross_year_links(items)
    chains = result["management_thesis_chains"]
    assert len(chains) == 1
    # Both item IDs appear in the chain
    assert "MP-EV-A" in chains[0]["linked_item_ids"]
    assert "MP-EV-B" in chains[0]["linked_item_ids"]
    # The original items (with their evidence IDs) are unchanged
    item_a = next(it for it in items if it["item_id"] == "MP-EV-A")
    item_b = next(it for it in items if it["item_id"] == "MP-EV-B")
    assert item_a["events"][0]["evidence"][0]["evidence_id"] == "ev_real_doc_001"
    assert item_b["events"][0]["evidence"][0]["evidence_id"] == "ev_real_doc_002"


# ---------------------------------------------------------------------------
# ML-22: Consistency-based contradiction signal from management_consistency data
# ---------------------------------------------------------------------------


def test_ml22_consistency_data_generates_repeated_unresolved_signal():
    """
    When consistency_data contains a repeated_unresolved_promise, build_cross_year_links
    must generate a corresponding contradiction signal with source == "management_consistency".
    """
    consistency_data = {
        "promise_follow_through_summary": {
            "fulfilled_promises": [],
            "repeated_unresolved_promises": [
                "promise_fy20_we continue disciplined identifying future r d projects"
            ],
            "unclear_promises": [],
        }
    }
    items = []  # No progression items needed — signal comes from consistency
    result = build_cross_year_links(items, consistency_data=consistency_data)
    signals = result["contradiction_signals"]
    assert len(signals) == 1
    s = signals[0]
    assert s["signal_type"] == "repeated_unresolved"
    assert s["earlier_period"] == "fy20"
    assert "disciplined" in s["earlier_claim"] or "r d projects" in s["earlier_claim"]
    assert s.get("source") == "management_consistency"


# ---------------------------------------------------------------------------
# ML-23: Measurable target from consistency promise with numeric value
# ---------------------------------------------------------------------------


def test_ml23_consistency_measurable_target_extracted():
    """
    A repeated_unresolved_promise containing a numeric target must produce
    a measurable commitment with delivery_status == UNVERIFIED.
    """
    consistency_data = {
        "promise_follow_through_summary": {
            "fulfilled_promises": [],
            "repeated_unresolved_promises": [
                "promise_fy24_achieve 35 reduction absolute scope 1 scope 2 emissions"
            ],
            "unclear_promises": [],
        }
    }
    items = []
    result = build_cross_year_links(items, consistency_data=consistency_data)
    commitments = result["measurable_commitments"]
    assert len(commitments) >= 1, "Numeric promise must yield a measurable commitment"
    c = commitments[0]
    assert "35" in c["extracted_target"]
    assert c["delivery_status"] == "UNVERIFIED"
    assert c.get("source") == "management_consistency"
    assert c["source_period"] == "fy24"
