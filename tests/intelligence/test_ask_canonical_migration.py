from __future__ import annotations

from intelligence.ask_intrinsiciq.answer_cards import build_answer_cards
from intelligence.ask_intrinsiciq.canonical_projection import (
    build_business_journey_from_company_model,
    build_products_services_from_company_model,
)
from intelligence.ask_intrinsiciq.loader import load_company_memory_sources


GENERATED_AT = "2026-08-13T00:00:00Z"


def _source_bundle(company: str, *, company_model: dict | None = None, management_progression: dict | None = None, legacy_sources: dict | None = None) -> dict:
    sources = {
        "company_model": {"status": "loaded" if company_model else "missing", "payload": company_model},
        "management_progression": {"status": "loaded" if management_progression else "missing", "payload": management_progression},
    }
    for key, payload in (legacy_sources or {}).items():
        sources[key] = {"status": "loaded", "payload": payload}
    return {
        "company_slug": company,
        "sources": sources,
        "source_files_found": [],
        "source_files_missing": [],
    }


def _company_model(company: str = "acme") -> dict:
    return {
        "schema_version": "company_model.v1",
        "company_slug": company,
        "coverage_status": "supported",
        "company_identity": {"name": company},
        "current_business_model": {
            "summary": "Acme sells usage-linked workflow software to hospitals.",
            "what_company_does": "Acme sells usage-linked workflow software to hospitals.",
            "business_model_type": "software_platform",
            "what_it_sells": ["Hospital workflow software"],
            "who_pays": ["hospitals"],
            "who_uses": ["clinicians"],
            "how_revenue_happens": "Usage-linked software fees from hospital customers.",
            "economic_mechanism": "The business improves hospital workflow throughput and earns as usage expands.",
            "source_period": "fy26",
            "confidence": {"level": "high", "basis": ["test"], "limitations": []},
        },
        "offerings": [
            {
                "offering_id": "hospital_workflow_software",
                "name": "Hospital workflow software",
                "category": "platform",
                "description": "Software that helps hospitals manage clinical workflows.",
                "customer_problem_solved": "Helps hospitals coordinate clinical workflows.",
                "revenue_role": "primary",
                "source_period": "fy26",
                "confidence": {"level": "high", "basis": ["test"], "limitations": []},
            }
        ],
        "customers": [
            {
                "customer_segment_id": "hospitals",
                "payer_type": "hospitals",
                "end_user_type": "clinicians",
                "concentration_known": False,
            }
        ],
        "revenue_engines": [{"engine_id": "usage", "mechanism": "Usage-linked software fees from hospital customers."}],
        "business_model_evolution": [],
        "uncertainties": [{"question": "How concentrated is hospital revenue?"}],
    }


def _management_progression(company: str = "acme", *, coverage: str = "supported") -> dict:
    return {
        "schema_version": "management_progression.v1",
        "company_slug": company,
        "coverage_status": coverage,
        "progression_items": []
        if coverage == "insufficient_evidence"
        else [
            {
                "item_id": "MP-1",
                "theme": "Hospital workflow platform rollout",
                "linked_company_model_ids": ["hospital_workflow_software"],
                "stream_types": ["project"],
                "current_status": "in_progress",
                "events": [
                    {
                        "event_id": "EV-1",
                        "role": "action",
                        "event_type": "project_execution",
                        "source_period": "fy26",
                        "event_period": "fy26",
                        "target_period": "",
                        "resolved_period": "",
                        "actor": "management",
                        "statement_text": "",
                        "action_taken": "Management began rolling out hospital workflow software.",
                        "operational_outcome": "",
                        "financial_or_business_outcome": "",
                        "verification_status": "partially_verified",
                        "confidence": {"level": "medium", "basis": ["test"], "limitations": []},
                        "evidence": [{"source_artifact": "management_progression.json", "source_period": "fy26"}],
                    }
                ],
                "investor_implication": {
                    "conclusion": "The rollout is visible, but utilization and returns remain unproven.",
                    "economic_mechanism": "The rollout matters only if it creates adoption, usage, and cash generation.",
                    "thesis_impact": "unresolved",
                    "confidence": {"level": "medium", "basis": ["test"], "limitations": []},
                    "what_to_watch": ["Hospital utilization."],
                },
                "unresolved": [{"question": "Does utilization follow the rollout?"}],
            }
        ],
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


def test_business_questions_use_company_model_without_pcim():
    cards = _answer_cards(_source_bundle("acme", company_model=_company_model(), management_progression=_management_progression()))
    by_question = {answer["question_id"]: answer for answer in cards["answers"]}

    assert by_question["what-does-company-do"]["answer_status"] == "supported"
    assert "workflow software" in by_question["what-does-company-do"]["simple_answer"].lower()
    assert "current business model" in by_question["what-does-company-do"]["evidence_summary"]["summary"].lower()


def test_progression_questions_use_management_progression():
    cards = _answer_cards(_source_bundle("acme", company_model=_company_model(), management_progression=_management_progression()))
    answer = next(answer for answer in cards["answers"] if answer["question_id"] == "what-projects-are-underway")

    assert answer["answer_status"] == "supported"
    assert "business effect remains unproven" in answer["simple_answer"].lower()
    assert "..." not in answer["simple_answer"]
    assert answer["interpretation"]["confidence"]["level"] == "medium"
    assert "Derived from the progression evidence set only" in answer["evidence_summary"]["summary"]


def test_progression_views_remain_distinct_on_shared_bundle():
    progression = _management_progression()
    base_event = progression["progression_items"][0]["events"][0]
    progression["progression_items"] = [
        {
            **progression["progression_items"][0],
            "item_id": "MP-PROMISE",
            "theme": "Hospital workflow software rollout",
            "stream_types": ["commitment"],
            "current_status": "announced",
            "events": [
                {
                    **base_event,
                    "event_id": "EV-PROMISE",
                    "role": "commitment",
                    "event_type": "product_launch",
                    "statement_text": "Management committed to roll out hospital workflow software.",
                    "action_taken": "",
                    "operational_outcome": "",
                    "financial_or_business_outcome": "",
                    "verification_status": "unresolved",
                }
            ],
        },
        {
            **progression["progression_items"][0],
            "item_id": "MP-HR",
            "theme": "Employee learning and development programme",
            "stream_types": ["commitment"],
            "current_status": "announced",
            "events": [
                {
                    **base_event,
                    "event_id": "EV-HR",
                    "role": "commitment",
                    "event_type": "strategic_change",
                    "statement_text": "Management committed to employee learning and development programmes.",
                    "action_taken": "",
                    "operational_outcome": "",
                    "financial_or_business_outcome": "",
                    "verification_status": "unresolved",
                }
            ],
        },
        {
            **progression["progression_items"][0],
            "item_id": "MP-PROJECT",
            "theme": "Hospital workflow software rollout",
            "stream_types": ["project"],
            "current_status": "in_progress",
            "events": [
                {
                    **base_event,
                    "event_id": "EV-PROJECT",
                    "role": "action",
                    "event_type": "project_execution",
                    "statement_text": "",
                    "action_taken": "Hospital workflow software rollout",
                    "operational_outcome": "Customer adoption remains unproven.",
                    "financial_or_business_outcome": "",
                    "verification_status": "partially_verified",
                }
            ],
        },
        {
            **progression["progression_items"][0],
            "item_id": "MP-CAPACITY",
            "theme": "Manufacturing capacity doubling",
            "stream_types": ["capacity"],
            "current_status": "in_progress",
            "events": [
                {
                    **base_event,
                    "event_id": "EV-CAPACITY",
                    "role": "action",
                    "event_type": "capacity_expansion",
                    "statement_text": "",
                    "action_taken": "Floor area and manufacturing capacity (doubling)",
                    "operational_outcome": "Capacity is still ramping.",
                    "financial_or_business_outcome": "",
                    "verification_status": "partially_verified",
                }
            ],
        },
        {
            **progression["progression_items"][0],
            "item_id": "MP-COMMENTARY",
            "theme": "Management commentary on utilization",
            "stream_types": ["commentary"],
            "current_status": "announced",
            "events": [
                {
                    **base_event,
                    "event_id": "EV-COMMENTARY",
                    "role": "statement",
                    "event_type": "commentary_change",
                    "statement_text": "Management shifted from expansion language toward utilization and execution quality.",
                    "action_taken": "",
                    "operational_outcome": "",
                    "financial_or_business_outcome": "",
                    "verification_status": "unresolved",
                }
            ],
        },
    ]

    cards = _answer_cards(_source_bundle("acme", company_model=_company_model(), management_progression=progression))
    by_question = {answer["question_id"]: answer for answer in cards["answers"]}

    assert by_question["what-has-management-promised"]["answer_status"] == "supported"
    assert "management commitment" in by_question["what-has-management-promised"]["simple_answer"].lower()
    assert "employee learning" not in by_question["what-has-management-promised"]["simple_answer"].lower()
    assert by_question["what-has-management-promised"]["interpretation"]["confidence"]["level"] == "medium"
    assert by_question["what-projects-are-underway"]["answer_status"] == "supported"
    assert "business effect remains unproven" in by_question["what-projects-are-underway"]["simple_answer"].lower()
    assert by_question["how-is-capacity-changing"]["answer_status"] == "supported"
    assert "customer base" not in by_question["how-is-capacity-changing"]["simple_answer"].lower()
    assert "operating capacity" in by_question["how-is-capacity-changing"]["simple_answer"].lower()
    assert by_question["what-is-management-commentary-saying"]["answer_status"] == "supported"
    assert "management commentary shows" in by_question["what-is-management-commentary-saying"]["simple_answer"].lower()
    assert "project" not in by_question["what-is-management-commentary-saying"]["simple_answer"].lower()


def test_claim_question_requires_later_evidence():
    progression = _management_progression()
    progression["progression_items"] = [
        {
            **progression["progression_items"][0],
            "item_id": "MP-CLAIM",
            "theme": "Hospital workflow software promise",
            "stream_types": ["commitment"],
            "current_status": "announced",
            "events": [
                {
                    **progression["progression_items"][0]["events"][0],
                    "event_id": "EV-CLAIM",
                    "role": "commitment",
                    "event_type": "product_launch",
                    "statement_text": "Management committed to roll out hospital workflow software.",
                    "action_taken": "",
                    "operational_outcome": "",
                    "financial_or_business_outcome": "",
                    "verification_status": "unresolved",
                }
            ],
        }
    ]

    cards = _answer_cards(_source_bundle("acme", company_model=_company_model(), management_progression=progression))
    answer = next(answer for answer in cards["answers"] if answer["question_id"] == "did-past-claims-come-true")

    assert answer["answer_status"] == "not_supported"
    assert "does not yet support" in answer["simple_answer"].lower()


def test_promise_question_preserves_valid_management_commitment():
    progression = _management_progression()
    progression["progression_items"] = [
        {
            **progression["progression_items"][0],
            "item_id": "MP-COMMITMENT",
            "theme": "Hospital workflow software utilization target",
            "stream_types": ["commitment"],
            "current_status": "announced",
            "events": [
                {
                    **progression["progression_items"][0]["events"][0],
                    "event_id": "EV-COMMITMENT",
                    "role": "commitment",
                    "event_type": "product_launch",
                    "statement_text": "Management committed to expand hospital workflow software utilization.",
                    "action_taken": "",
                    "operational_outcome": "",
                    "financial_or_business_outcome": "",
                    "verification_status": "unresolved",
                }
            ],
        }
    ]

    cards = _answer_cards(_source_bundle("acme", company_model=_company_model(), management_progression=progression))
    answer = next(answer for answer in cards["answers"] if answer["question_id"] == "what-has-management-promised")

    assert answer["answer_status"] == "supported"
    assert "workflow software utilization" in str(answer).lower()


def test_progression_questions_do_not_promote_legacy_strategy_buckets_as_promises_or_commentary():
    progression = _management_progression()
    progression["progression_items"] = [
        {
            **progression["progression_items"][0],
            "item_id": "MP-LEGACY",
            "theme": "UI Test Automation / Gen AI",
            "stream_types": ["legacy_strategy"],
            "current_status": "in_progress",
            "events": [
                {
                    **progression["progression_items"][0]["events"][0],
                    "event_id": "EV-LEGACY",
                    "role": "action",
                    "event_type": "strategic_change",
                    "statement_text": "",
                    "action_taken": "UI Test Automation / Gen AI",
                    "verification_status": "partially_verified",
                }
            ],
        }
    ]

    cards = _answer_cards(_source_bundle("acme", company_model=_company_model(), management_progression=progression))
    by_question = {answer["question_id"]: answer for answer in cards["answers"]}

    assert by_question["what-has-management-promised"]["answer_status"] == "not_supported"
    assert by_question["what-is-management-commentary-saying"]["answer_status"] == "not_supported"
    assert "ui test automation" not in str(by_question["what-has-management-promised"]).lower()
    assert "ui test automation" not in str(by_question["what-is-management-commentary-saying"]).lower()


def test_business_summary_prioritizes_core_operating_model_over_financing_context():
    bundle = load_company_memory_sources("tanla")
    journey, _ = build_business_journey_from_company_model(bundle, company_slug="tanla", generated_at=GENERATED_AT)
    products, _ = build_products_services_from_company_model(bundle, business_journey_payload=journey, company_slug="tanla", generated_at=GENERATED_AT)
    cards, _ = build_answer_cards(bundle, business_journey_payload=journey, products_services_payload=products, company_slug="tanla", generated_at=GENERATED_AT)
    answer = next(answer for answer in cards["answers"] if answer["question_id"] == "what-does-company-do")
    text = " ".join([journey["summary"], products["summary"], answer["simple_answer"]]).lower()

    assert "enterprise messaging" in text
    assert "qip" not in text
    assert "esop" not in text
    assert "related-party" not in text
    assert "bank financing" not in text


def test_revenue_logic_is_causal_and_business_type_specific():
    tanla_bundle = load_company_memory_sources("tanla")
    tanla_journey, _ = build_business_journey_from_company_model(tanla_bundle, company_slug="tanla", generated_at=GENERATED_AT)
    tanla_products, _ = build_products_services_from_company_model(tanla_bundle, business_journey_payload=tanla_journey, company_slug="tanla", generated_at=GENERATED_AT)
    tanla_cards, _ = build_answer_cards(tanla_bundle, business_journey_payload=tanla_journey, products_services_payload=tanla_products, company_slug="tanla", generated_at=GENERATED_AT)
    tanla_revenue = next(answer for answer in tanla_cards["answers"] if answer["question_id"] == "how-does-it-make-money")

    tips_bundle = load_company_memory_sources("tips")
    tips_journey, _ = build_business_journey_from_company_model(tips_bundle, company_slug="tips", generated_at=GENERATED_AT)
    tips_products, _ = build_products_services_from_company_model(tips_bundle, business_journey_payload=tips_journey, company_slug="tips", generated_at=GENERATED_AT)
    tips_cards, _ = build_answer_cards(tips_bundle, business_journey_payload=tips_journey, products_services_payload=tips_products, company_slug="tips", generated_at=GENERATED_AT)
    tips_revenue = next(answer for answer in tips_cards["answers"] if answer["question_id"] == "how-does-it-make-money")

    datapatterns_bundle = load_company_memory_sources("datapatterns")
    data_journey, _ = build_business_journey_from_company_model(datapatterns_bundle, company_slug="datapatterns", generated_at=GENERATED_AT)
    data_products, _ = build_products_services_from_company_model(datapatterns_bundle, business_journey_payload=data_journey, company_slug="datapatterns", generated_at=GENERATED_AT)
    data_cards, _ = build_answer_cards(datapatterns_bundle, business_journey_payload=data_journey, products_services_payload=data_products, company_slug="datapatterns", generated_at=GENERATED_AT)
    data_revenue = next(answer for answer in data_cards["answers"] if answer["question_id"] == "how-does-it-make-money")

    assert tanla_revenue["revenue_flow"]["model_type"] == "mixed"
    assert "usage-linked service revenue" in tanla_products["revenue_logic_summary"].lower()
    assert "usage-linked service charges" not in tanla_products["revenue_logic_summary"].lower()
    assert tanla_revenue["revenue_flow"]["billing_basis_note"] == "usage-linked service charges"
    assert not tanla_revenue["revenue_flow"].get("cash_timing_note")
    assert "catalogue ownership" in tips_products["revenue_logic_summary"].lower()
    assert "streaming royalties" in tips_products["revenue_logic_summary"].lower()
    assert "milestone" not in tips_products["revenue_logic_summary"].lower()
    assert "royalty-based terms" in tips_revenue["revenue_flow"]["billing_basis_note"].lower()
    assert not tips_revenue["revenue_flow"].get("cash_timing_note")
    assert data_revenue["revenue_flow"]["model_type"] == "project_based"
    assert "delivery" in data_products["revenue_logic_summary"].lower()
    assert "recognized on" not in data_products["revenue_logic_summary"].lower()
    assert "delivery or acceptance terms" in data_revenue["revenue_flow"]["billing_basis_note"].lower()
    assert not data_revenue["revenue_flow"].get("cash_timing_note")


def test_insufficient_progression_does_not_fall_back_to_legacy_sources():
    bundle = _source_bundle(
        "acme",
        company_model=_company_model(),
        management_progression=_management_progression(coverage="insufficient_evidence"),
        legacy_sources={"management_commitments": {"commitments": [{"normalized_commitment": "Legacy promise should not appear"}]}},
    )
    cards = _answer_cards(bundle)
    answer = next(answer for answer in cards["answers"] if answer["question_id"] == "what-has-management-promised")

    assert answer["answer_status"] == "not_supported"
    assert "legacy promise should not appear" not in str(answer).lower()
    assert "The available evidence does not yet support this answer." in answer["simple_answer"]


def test_missing_company_model_is_safe_unavailable():
    journey, _ = build_business_journey_from_company_model(_source_bundle("acme"), company_slug="acme", generated_at=GENERATED_AT)
    products, _ = build_products_services_from_company_model(_source_bundle("acme"), business_journey_payload=journey, company_slug="acme", generated_at=GENERATED_AT)

    assert journey["coverage_status"] == "unavailable"
    assert products["coverage_status"] == "unavailable"


def test_cross_company_company_model_is_rejected():
    bundle = _source_bundle("acme", company_model=_company_model("other"), management_progression=_management_progression())

    try:
        build_business_journey_from_company_model(bundle, company_slug="acme", generated_at=GENERATED_AT)
    except ValueError as exc:
        assert "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION" in str(exc)
    else:
        raise AssertionError("expected cross-company Company Model rejection")
