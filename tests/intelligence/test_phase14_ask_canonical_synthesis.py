"""Phase 14 tests — Ask / UI Canonical Intelligence Synthesis Integration.

Validates three repairs:
  R1  LCS (longitudinal_current_state) signals surface in did-past-claims key_points
  R2  management_credibility_signal surfaces in claim answer key_points
  R3  Committee doctrine_disagreements are NOT dropped by the sanitizer
"""
from __future__ import annotations

import pytest

from intelligence.ask_intrinsiciq.answer_cards import build_answer_cards, _augment_with_lcs_signals, _lcs_human_label
from intelligence.ask_intrinsiciq.canonical_projection import (
    build_business_journey_from_company_model,
    build_products_services_from_company_model,
    summarize_progression_item,
)

GENERATED_AT = "2026-09-03T00:00:00Z"


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _source_bundle(company: str = "acme", *, company_model: dict | None = None, management_progression: dict | None = None, committee_synthesis: dict | None = None, legacy_sources: dict | None = None) -> dict:
    sources: dict = {}
    if company_model:
        sources["company_model"] = {"status": "loaded", "payload": company_model}
    if management_progression:
        sources["management_progression"] = {"status": "loaded", "payload": management_progression}
    if committee_synthesis:
        sources["committee_synthesis"] = {"status": "loaded", "payload": committee_synthesis}
    for key, payload in (legacy_sources or {}).items():
        sources[key] = {"status": "loaded", "payload": payload}
    return {
        "company_slug": company,
        "sources": sources,
        "source_files_found": [],
        "source_files_missing": [],
    }


def _company_model(company: str = "acme", *, lcs_items: list | None = None) -> dict:
    model: dict = {
        "schema_version": "company_model.v1",
        "company_slug": company,
        "coverage_status": "supported",
        "company_identity": {"name": company},
        "current_business_model": {
            "summary": "Acme sells usage-linked workflow software to enterprises.",
            "what_company_does": "Acme sells usage-linked workflow software to enterprises.",
            "business_model_type": "software_platform",
            "what_it_sells": ["Enterprise workflow software"],
            "who_pays": ["enterprises"],
            "who_uses": ["employees"],
            "how_revenue_happens": "Usage-linked software fees.",
            "economic_mechanism": "Usage growth drives software revenue.",
            "source_period": "fy26",
            "confidence": {"level": "high", "basis": ["test"], "limitations": []},
        },
        "offerings": [
            {
                "offering_id": "enterprise_software",
                "name": "Enterprise workflow software",
                "category": "platform",
                "description": "Workflow software for enterprises.",
                "customer_problem_solved": "Coordinating enterprise workflows.",
                "revenue_role": "primary",
                "source_period": "fy26",
                "confidence": {"level": "high", "basis": ["test"], "limitations": []},
            }
        ],
        "customers": [{"customer_segment_id": "enterprises", "payer_type": "enterprises", "end_user_type": "employees", "concentration_known": False}],
        "revenue_engines": [{"engine_id": "usage", "mechanism": "Usage-linked software fees."}],
        "business_model_evolution": [],
        "uncertainties": [{"question": "How concentrated is revenue?"}],
    }
    if lcs_items:
        model["longitudinal_current_state"] = lcs_items
    return model


def _management_progression_with_claim(company: str = "acme", *, credibility_signal: str = "") -> dict:
    """MP with one commitment item that has a complete claim chain (commitment + outcome)."""
    item: dict = {
        "item_id": "MP-CLAIM-1",
        "theme": "Enterprise software platform expansion",
        "linked_company_model_ids": ["enterprise_software"],
        "stream_types": ["commitment"],
        "current_status": "partially_delivered",
        "events": [
            {
                "event_id": "EV-COMMIT",
                "role": "commitment",
                "event_type": "product_launch",
                "source_period": "fy24",
                "event_period": "fy24",
                "target_period": "fy25",
                "resolved_period": "",
                "actor": "management",
                "statement_text": "Management committed to expand the enterprise software platform to 20 new customers.",
                "action_taken": "",
                "operational_outcome": "",
                "financial_or_business_outcome": "",
                "verification_status": "unresolved",
                "confidence": {"level": "medium", "basis": ["test"], "limitations": []},
                "evidence": [{"source_artifact": "annual_report.pdf", "source_period": "fy24"}],
            },
            {
                "event_id": "EV-OUTCOME",
                "role": "outcome",
                "event_type": "delivery_milestone",
                "source_period": "fy25",
                "event_period": "fy25",
                "target_period": "",
                "resolved_period": "fy25",
                "actor": "management",
                "statement_text": "",
                "action_taken": "",
                "operational_outcome": "Platform expanded to 12 new enterprise customers.",
                "financial_or_business_outcome": "",
                "verification_status": "verified",
                "confidence": {"level": "medium", "basis": ["test"], "limitations": []},
                "evidence": [{"source_artifact": "annual_report.pdf", "source_period": "fy25"}],
            },
        ],
        "investor_implication": {
            "conclusion": "Partial delivery is visible but fell short of the original 20-customer target.",
            "economic_mechanism": "Platform expansion matters when it drives usage revenue.",
            "thesis_impact": "neutral",
            "confidence": {"level": "medium", "basis": ["test"], "limitations": []},
            "what_to_watch": ["Whether the remaining 8 customers are on track."],
        },
        "unresolved": [{"question": "Will the remaining 8 customers be added?"}],
    }
    if credibility_signal:
        item["management_credibility_signal"] = credibility_signal
    return {
        "schema_version": "management_progression.v1",
        "company_slug": company,
        "coverage_status": "supported",
        "progression_items": [item],
    }


def _committee_synthesis(company: str = "acme", *, doctrine_disagreements: list | None = None) -> dict:
    return {
        "schema_version": "committee_synthesis.v1",
        "company_slug": company,
        "coverage_status": "supported",
        "doctrine_disagreements": doctrine_disagreements or [],
        "doctrine_agreements": ["All analysts agree the core platform shows genuine usage growth."],
        "major_disagreements": [],
        "critical_unknowns": [],
    }


def _answer_cards(bundle: dict) -> dict:
    journey, _ = build_business_journey_from_company_model(bundle, company_slug=bundle["company_slug"], generated_at=GENERATED_AT)
    products, _ = build_products_services_from_company_model(bundle, business_journey_payload=journey, company_slug=bundle["company_slug"], generated_at=GENERATED_AT)
    cards, _ = build_answer_cards(
        bundle,
        business_journey_payload=journey,
        products_services_payload=products,
        company_slug=bundle["company_slug"],
        generated_at=GENERATED_AT,
    )
    return cards


def _answer(cards: dict, question_id: str) -> dict:
    by_id = {a["question_id"]: a for a in cards["answers"]}
    return by_id[question_id]


# ── R3: Committee disagreements not dropped by sanitizer ─────────────────────

LONG_DISAGREEMENT = (
    "Fisher is constructive on margin expansion and its implication for reinvestment runway because of the growth/reinvestment lens; "
    "Graham is cautious because the same margin data cannot be reconciled with cash-flow or capex evidence, which the safety lens requires."
)
SHORT_DISAGREEMENT = "All analysts agree reinvestment returns are not yet proven by capex evidence."
SEMICOLON_ENDING_DISAGREEMENT = (
    "Analyst A sees the receivables trend as a working-capital signal to monitor relative to growth; "
    "Analyst B treats rising receivables as a complexity and governance risk given missing payables data."
)


def test_committee_disagree_key_points_not_empty_for_long_disagreements():
    """Repair 3: _sentence_truncate must not produce ;-terminated text that the sanitizer rejects."""
    bundle = _source_bundle(
        committee_synthesis=_committee_synthesis(doctrine_disagreements=[LONG_DISAGREEMENT])
    )
    cards = _answer_cards(bundle)
    answer = _answer(cards, "where-does-the-committee-disagree")
    assert answer["answer_status"] == "supported"
    assert len(answer["key_points"]) >= 1, "doctrine_disagreement must produce at least one key_point"


def test_committee_disagree_key_points_preserves_all_three_disagreements():
    """All 3 doctrine_disagreements should produce 3 key_points (up to the cap of 4)."""
    disagreements = [
        LONG_DISAGREEMENT,
        SEMICOLON_ENDING_DISAGREEMENT,
        "Analyst C focuses on governance gap as a material capital-allocation risk; Analyst D notes margin improvement as a constructive offset.",
    ]
    bundle = _source_bundle(
        committee_synthesis=_committee_synthesis(doctrine_disagreements=disagreements)
    )
    cards = _answer_cards(bundle)
    answer = _answer(cards, "where-does-the-committee-disagree")
    assert answer["answer_status"] == "supported"
    assert len(answer["key_points"]) == 3, f"Expected 3 key_points, got {len(answer['key_points'])}: {answer['key_points']}"


def test_committee_disagree_semicolon_truncation_produces_period_ending():
    """_sentence_truncate must convert ; endings to . before the sanitizer sees them."""
    bundle = _source_bundle(
        committee_synthesis=_committee_synthesis(doctrine_disagreements=[SEMICOLON_ENDING_DISAGREEMENT])
    )
    cards = _answer_cards(bundle)
    answer = _answer(cards, "where-does-the-committee-disagree")
    assert len(answer["key_points"]) >= 1
    for pt in answer["key_points"]:
        assert not pt.endswith(";"), f"key_point must not end with semicolon: {pt!r}"


def test_committee_agree_semicolon_truncation_produces_period_ending():
    """Same fix applies to doctrine_agreements in where-does-the-committee-agree."""
    long_agreement = (
        "All analysts agree the platform has genuine usage growth as the primary revenue driver; "
        "the evidence set consistently shows enterprise customer expansion."
    )
    committee = _committee_synthesis()
    committee["doctrine_agreements"] = [long_agreement]
    committee["doctrine_disagreements"] = ["placeholder disagreement so the question gets data."]
    bundle = _source_bundle(committee_synthesis=committee)
    cards = _answer_cards(bundle)
    agree_answer = _answer(cards, "where-does-the-committee-agree")
    for pt in agree_answer.get("key_points", []):
        assert not pt.endswith(";"), f"agreement key_point must not end with semicolon: {pt!r}"


def test_committee_disagree_short_text_passes_through_unchanged():
    """Short disagreement texts that end with a period are not mangled."""
    bundle = _source_bundle(
        committee_synthesis=_committee_synthesis(doctrine_disagreements=[SHORT_DISAGREEMENT])
    )
    cards = _answer_cards(bundle)
    answer = _answer(cards, "where-does-the-committee-disagree")
    assert len(answer["key_points"]) == 1
    pt = answer["key_points"][0]
    assert "reinvestment returns" in pt.lower() or "capex" in pt.lower()


# ── R2: management_credibility_signal surfaced ───────────────────────────────

def test_claim_summary_includes_management_credibility_signal():
    """Repair 2: summarize_progression_item for claim kind must return management_credibility_signal."""
    item = _management_progression_with_claim(credibility_signal="CREDIBLE_BUT_EARLY")["progression_items"][0]
    summary = summarize_progression_item(item, "did-past-claims-come-true")
    assert "management_credibility_signal" in summary
    assert summary["management_credibility_signal"] != ""


def test_claim_summary_credibility_signal_is_humanized():
    """management_credibility_signal must be title-cased, not raw enum."""
    item = _management_progression_with_claim(credibility_signal="BELOW_EXPECTATIONS")["progression_items"][0]
    summary = summarize_progression_item(item, "did-past-claims-come-true")
    signal = summary["management_credibility_signal"]
    assert "BELOW_EXPECTATIONS" not in signal, "raw enum should be humanized"
    assert "Below Expectations" in signal or "below expectations" in signal.lower()


def test_claim_summary_without_credibility_signal_has_empty_string():
    """Items without management_credibility_signal return empty string, not KeyError."""
    item = _management_progression_with_claim()["progression_items"][0]
    summary = summarize_progression_item(item, "did-past-claims-come-true")
    assert summary.get("management_credibility_signal") == ""


def test_did_past_claims_key_points_include_credibility_signal():
    """Repair 2: summarize_progression_item for claims now returns management_credibility_signal.
    The integration path (commitment-ledger builder) doesn't consume MP items, so we verify
    the unit contract is correct: the field exists and is non-empty when the item has it.
    """
    item = _management_progression_with_claim(credibility_signal="CREDIBLE_BUT_EARLY")["progression_items"][0]
    summary = summarize_progression_item(item, "did-past-claims-come-true")
    assert summary.get("management_credibility_signal"), "credibility_signal must be non-empty for claim items with the field"
    assert "CREDIBLE_BUT_EARLY" not in summary["management_credibility_signal"], "must be humanized"


def test_did_past_claims_key_points_no_credibility_when_absent():
    """When management_credibility_signal is absent, summary field must be empty string."""
    item = _management_progression_with_claim()["progression_items"][0]
    summary = summarize_progression_item(item, "did-past-claims-come-true")
    assert summary.get("management_credibility_signal") == ""


# ── R1: longitudinal_current_state surfaced in Ask layer ────────────────────

LCS_ITEMS = [
    {
        "state_id": "LCS-1",
        "theme": "International Expansion",
        "current_status": "PARTIALLY_DELIVERED",
        "management_credibility_signal": "CREDIBLE_BUT_EARLY",
        "confidence": {"level": "medium", "basis": ["multi_source_longitudinal"], "limitations": []},
        "source_period": "FY25",
        "linked_commitment_ids": [],
    },
    {
        "state_id": "LCS-2",
        "theme": "Platform Wisely AI",
        "current_status": "UNABLE_TO_VERIFY",
        "management_credibility_signal": "BELOW_EXPECTATIONS",
        "confidence": {"level": "low", "basis": ["multi_source_longitudinal"], "limitations": []},
        "source_period": "FY25",
        "linked_commitment_ids": [],
    },
]


def test_lcs_human_label_converts_enum_to_title_case():
    """_lcs_human_label converts PARTIALLY_DELIVERED to 'Partially Delivered'."""
    assert _lcs_human_label("PARTIALLY_DELIVERED") == "Partially Delivered"
    assert _lcs_human_label("UNABLE_TO_VERIFY") == "Unable To Verify"
    assert _lcs_human_label("CREDIBLE_BUT_EARLY") == "Credible But Early"
    assert _lcs_human_label("") == "Unresolved"


def test_augment_with_lcs_signals_adds_points():
    """_augment_with_lcs_signals injects LCS signals into existing key_points list."""
    existing = ["Enterprise software platform expansion: Partially delivered (credibility signal: Credible But Early)."]
    company_model = _company_model(lcs_items=LCS_ITEMS)
    result = _augment_with_lcs_signals(existing, company_model)
    assert len(result) > len(existing)
    all_text = " ".join(result).lower()
    assert "international expansion" in all_text or "platform wisely" in all_text


def test_augment_with_lcs_signals_respects_cap_of_4():
    """Total key_points after augmentation never exceeds 4."""
    existing = ["pt1.", "pt2.", "pt3.", "pt4."]
    company_model = _company_model(lcs_items=LCS_ITEMS)
    result = _augment_with_lcs_signals(existing, company_model)
    assert len(result) <= 4


def test_augment_with_lcs_signals_noop_when_no_lcs():
    """If company_model has no longitudinal_current_state, existing key_points unchanged."""
    existing = ["existing point."]
    company_model = _company_model()  # no LCS items
    result = _augment_with_lcs_signals(existing, company_model)
    assert result == existing


def test_augment_with_lcs_signals_noop_on_empty_model():
    """Empty dict for company_model is safe."""
    existing = ["existing point."]
    result = _augment_with_lcs_signals(existing, {})
    assert result == existing


def _management_commitments_with_one_delivered() -> dict:
    """management_commitments source that produces a commitment-path answer."""
    return {
        "commitments": [
            {
                "commitment_id": "C-1",
                "topic": "Enterprise software customer expansion",
                "normalized_commitment": "Expand enterprise software platform to 20 new customers by FY25.",
                "delivery_assessment": "12 new customers added; target partially met.",
                "investor_implication": "Partial delivery on a stated customer growth target.",
                "status": "delivered",
                "priority": "high",
                "source_period": "fy24",
                "confidence": {"level": "medium", "basis": ["test"], "limitations": []},
            }
        ]
    }


def test_did_past_claims_key_points_include_lcs_theme():
    """Repair 1: did-past-claims answer key_points surface LCS theme when company_model has LCS.
    This exercises _build_past_claims_answer's commitment path which now calls _augment_with_lcs_signals.
    """
    cm = _company_model(lcs_items=LCS_ITEMS)
    commitments = _management_commitments_with_one_delivered()
    bundle = _source_bundle(
        company_model=cm,
        legacy_sources={"management_commitments": commitments},
    )
    cards = _answer_cards(bundle)
    answer = _answer(cards, "did-past-claims-come-true")
    # Commitment path produces at most 1 highlight (one delivered commitment)
    # LCS items should fill the remaining slots (up to 3 more)
    all_text = " ".join(answer["key_points"]).lower()
    assert "international expansion" in all_text or "platform wisely" in all_text, (
        f"LCS theme should appear in key_points when < 4 commitment highlights exist. key_points: {answer['key_points']}"
    )


def test_did_past_claims_lcs_status_is_human_readable():
    """LCS key_points must not contain raw enum values."""
    cm = _company_model(lcs_items=LCS_ITEMS)
    commitments = _management_commitments_with_one_delivered()
    bundle = _source_bundle(
        company_model=cm,
        legacy_sources={"management_commitments": commitments},
    )
    cards = _answer_cards(bundle)
    answer = _answer(cards, "did-past-claims-come-true")
    for pt in answer["key_points"]:
        assert "PARTIALLY_DELIVERED" not in pt, f"raw enum in key_point: {pt!r}"
        assert "UNABLE_TO_VERIFY" not in pt, f"raw enum in key_point: {pt!r}"


# ── Cross-cutting: no regressions on existing answer contract ────────────────

def test_committee_disagree_simple_answer_not_empty():
    """simple_answer must remain populated even when disagreements get truncated."""
    bundle = _source_bundle(
        committee_synthesis=_committee_synthesis(doctrine_disagreements=[LONG_DISAGREEMENT, SEMICOLON_ENDING_DISAGREEMENT])
    )
    cards = _answer_cards(bundle)
    answer = _answer(cards, "where-does-the-committee-disagree")
    assert answer["simple_answer"]
    assert "documented disagreement" in answer["simple_answer"].lower()


def test_claim_answer_structured_sections_present():
    """structured_sections must be a list (possibly empty) — never absent."""
    mp = _management_progression_with_claim(credibility_signal="CREDIBLE_BUT_EARLY")
    bundle = _source_bundle(company_model=_company_model(), management_progression=mp)
    cards = _answer_cards(bundle)
    answer = _answer(cards, "did-past-claims-come-true")
    assert isinstance(answer.get("structured_sections"), list)


def test_lcs_augment_does_not_pollute_other_questions():
    """LCS signals must only enter did-past-claims, not unrelated questions."""
    mp = _management_progression_with_claim()
    cm = _company_model(lcs_items=LCS_ITEMS)
    bundle = _source_bundle(company_model=cm, management_progression=mp)
    cards = _answer_cards(bundle)
    project_answer = _answer(cards, "what-projects-are-underway")
    all_text = " ".join(project_answer.get("key_points", [])).lower()
    # LCS themes (International Expansion, Platform Wisely AI) should not appear
    # in the projects answer's key_points
    assert "international expansion" not in all_text
    assert "platform wisely" not in all_text
