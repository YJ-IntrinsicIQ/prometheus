from __future__ import annotations

import re

from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

from intelligence.progression import build_interpretation_contract

from .sanitizer import contains_forbidden_public_term, sanitize_public_payload, sanitize_public_text
from .uncertainty_mapper import build_uncertainty_note_for_answer


QUESTION_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "understand-the-business",
        "title": "Understand the Business",
        "short_description": "Start with the plain-language business model and the people it serves before moving into execution and judgment.",
        "display_order": 1,
        "questions": [
            {"id": "what-does-company-do", "title": "What does the company do?", "short_label": "What does it do?", "recommended": True},
            {"id": "who-are-the-customers", "title": "Who are the customers?", "short_label": "Customers", "recommended": False},
            {"id": "how-does-it-make-money", "title": "How does it make money?", "short_label": "Makes money", "recommended": False},
        ],
    },
    {
        "id": "financials",
        "title": "Financials",
        "short_description": "Keep the financial reading compact, careful, and investor-readable rather than dashboard-heavy.",
        "display_order": 2,
        "questions": [
            {"id": "are-profits-converting-into-cash", "title": "Is profit converting into cash?", "short_label": "Profit to cash", "recommended": False},
            {"id": "what-is-owner-earnings", "title": "What is owner earnings?", "short_label": "Owner earnings", "recommended": False},
            {"id": "is-working-capital-a-concern", "title": "Is working capital a concern?", "short_label": "Working capital", "recommended": False},
            {"id": "are-per-share-economics-improving", "title": "Are per-share economics improving?", "short_label": "Per-share trend", "recommended": False},
        ],
    },
    {
        "id": "management",
        "title": "Management & Progression",
        "short_description": "Look at commitments, projects, capacity, commentary, capital allocation, and management quality over time.",
        "display_order": 3,
        "questions": [
            {"id": "what-has-management-promised", "title": "What has management promised?", "short_label": "Promises", "recommended": False},
            {"id": "did-past-claims-come-true", "title": "Did past claims come true?", "short_label": "Follow-through", "recommended": False},
            {"id": "what-projects-are-underway", "title": "What projects are underway?", "short_label": "Projects", "recommended": False},
            {"id": "how-is-capacity-changing", "title": "How is capacity changing?", "short_label": "Capacity", "recommended": False},
            {"id": "what-is-management-commentary-saying", "title": "What is management commentary saying?", "short_label": "Commentary", "recommended": False},
            {"id": "how-is-capital-allocated", "title": "How is capital allocated?", "short_label": "Capital allocation", "recommended": False},
            {"id": "what-incentives-matter", "title": "What signals management quality?", "short_label": "Management quality", "recommended": False},
        ],
    },
    {
        "id": "risks-and-diligence",
        "title": "Risks and Diligence",
        "short_description": "Keep the unresolved issues visible so the next step stays grounded instead of overconfident.",
        "display_order": 4,
        "questions": [
            {"id": "what-can-break-the-thesis", "title": "What can break the thesis?", "short_label": "Break the thesis", "recommended": False},
            {"id": "which-disclosure-is-missing", "title": "Which disclosure is missing?", "short_label": "Missing disclosure", "recommended": False},
            {"id": "what-evidence-would-change-the-view", "title": "What evidence would change the view?", "short_label": "Change the view", "recommended": False},
            {"id": "what-needs-management-clarification", "title": "What needs management clarification?", "short_label": "Needs clarification", "recommended": False},
            {"id": "what-should-i-ask-ir", "title": "What should I ask IR?", "short_label": "Ask IR", "recommended": False},
            {"id": "what-remains-unresolved", "title": "What remains unresolved?", "short_label": "Unresolved", "recommended": False},
        ],
    },
    {
        "id": "investor-panel",
        "title": "Investor Panel",
        "short_description": "Use investor-style lenses as curated prompts, not as a dashboard or permanent switcher.",
        "display_order": 5,
        "questions": [
            {"id": "what-would-graham-worry-about", "title": "What would Graham worry about?", "short_label": "Graham", "recommended": False},
            {"id": "what-would-buffett-focus-on", "title": "What would Buffett focus on?", "short_label": "Buffett", "recommended": True},
            {"id": "where-would-fisher-be-curious", "title": "Where would Fisher be curious?", "short_label": "Fisher", "recommended": False},
            {"id": "what-would-munger-avoid", "title": "What would Munger avoid?", "short_label": "Munger", "recommended": False},
            {"id": "how-would-lynch-explain-it", "title": "How would Lynch explain it?", "short_label": "Lynch", "recommended": False},
        ],
    },
]


NEXT_QUESTION_MAP = {
    "what-does-company-do": ["who-are-the-customers", "how-does-it-make-money", "what-has-management-promised"],
    "who-are-the-customers": ["how-does-it-make-money", "are-profits-converting-into-cash", "what-projects-are-underway"],
    "how-does-it-make-money": ["are-profits-converting-into-cash", "what-is-owner-earnings", "what-is-management-commentary-saying"],
    "are-profits-converting-into-cash": ["what-is-owner-earnings", "is-working-capital-a-concern", "how-is-capital-allocated"],
    "what-is-owner-earnings": ["is-working-capital-a-concern", "are-per-share-economics-improving", "what-incentives-matter"],
    "is-working-capital-a-concern": ["are-per-share-economics-improving", "what-can-break-the-thesis", "what-remains-unresolved"],
    "are-per-share-economics-improving": ["what-is-owner-earnings", "what-evidence-would-change-the-view", "what-would-buffett-focus-on"],
    "what-has-management-promised": ["did-past-claims-come-true", "what-projects-are-underway", "what-is-management-commentary-saying"],
    "did-past-claims-come-true": ["what-has-management-promised", "how-is-capacity-changing", "what-needs-management-clarification"],
    "what-projects-are-underway": ["how-is-capacity-changing", "what-is-management-commentary-saying", "how-is-capital-allocated"],
    "how-is-capacity-changing": ["what-projects-are-underway", "what-has-management-promised", "what-can-break-the-thesis"],
    "what-is-management-commentary-saying": ["what-has-management-promised", "what-incentives-matter", "what-remains-unresolved"],
    "how-is-capital-allocated": ["what-incentives-matter", "what-would-buffett-focus-on", "what-remains-unresolved"],
    "what-incentives-matter": ["how-is-capital-allocated", "what-would-munger-avoid", "what-should-i-ask-ir"],
    "what-can-break-the-thesis": ["which-disclosure-is-missing", "what-remains-unresolved", "what-needs-management-clarification"],
    "which-disclosure-is-missing": ["what-evidence-would-change-the-view", "what-should-i-ask-ir", "what-remains-unresolved"],
    "what-evidence-would-change-the-view": ["which-disclosure-is-missing", "what-needs-management-clarification", "what-remains-unresolved"],
    "what-needs-management-clarification": ["what-should-i-ask-ir", "which-disclosure-is-missing", "what-remains-unresolved"],
    "what-should-i-ask-ir": ["what-needs-management-clarification", "which-disclosure-is-missing", "what-remains-unresolved"],
    "what-remains-unresolved": ["what-evidence-would-change-the-view", "what-can-break-the-thesis", "what-should-i-ask-ir"],
    "what-would-graham-worry-about": ["is-working-capital-a-concern", "what-can-break-the-thesis", "what-should-i-ask-ir"],
    "what-would-buffett-focus-on": ["what-is-owner-earnings", "how-is-capital-allocated", "what-incentives-matter"],
    "where-would-fisher-be-curious": ["what-has-management-promised", "what-projects-are-underway", "what-is-management-commentary-saying"],
    "what-would-munger-avoid": ["what-incentives-matter", "which-disclosure-is-missing", "what-needs-management-clarification"],
    "how-would-lynch-explain-it": ["what-does-company-do", "are-profits-converting-into-cash", "what-can-break-the-thesis"],
}


QUESTION_INDEX = {
    question["id"]: {
        **question,
        "category_id": category["id"],
        "category_title": category["title"],
        "answer_card_id": f"answer-{question['id']}",
    }
    for category in QUESTION_CATALOG
    for question in category["questions"]
}


BusinessJourneyMode = Literal["none", "summary", "full"]


class AnswerContextPolicy(TypedDict):
    include_business_journey: bool
    business_journey_mode: BusinessJourneyMode
    include_products_services: bool
    allowed_financial_visual_ids: List[str]
    include_uncertainty: bool


def get_context_policy_for_question(question_id: str) -> AnswerContextPolicy:
    visual_mapping = {
        "are-profits-converting-into-cash": ["cfo_vs_pat", "cash_conversion_cycle", "working_capital_days"],
        "what-is-owner-earnings": ["owner_earnings_bridge", "cfo_vs_pat"],
        "is-working-capital-a-concern": ["working_capital_days", "cash_conversion_cycle"],
        "are-per-share-economics-improving": ["per_share_economics"],
        "how-is-capital-allocated": ["capital_allocation_summary"],
        "what-would-graham-worry-about": ["working_capital_days", "cash_conversion_cycle"],
        "what-would-buffett-focus-on": ["owner_earnings_bridge", "capital_allocation_summary"],
        "what-can-break-the-thesis": ["working_capital_days", "cash_conversion_cycle"],
        "which-disclosure-is-missing": ["owner_earnings_bridge", "per_share_economics"],
        "what-needs-management-clarification": ["capital_allocation_summary", "owner_earnings_bridge"],
        "what-remains-unresolved": ["owner_earnings_bridge", "working_capital_days"],
    }
    return {
        "include_business_journey": question_id == "what-does-company-do",
        "business_journey_mode": "full" if question_id == "what-does-company-do" else "none",
        "include_products_services": question_id in {
            "what-does-company-do",
            "who-are-the-customers",
            "how-does-it-make-money",
        },
        "allowed_financial_visual_ids": list(visual_mapping.get(question_id, [])),
        "include_uncertainty": True,
    }


def build_answer_cards(
    source_bundle: Dict[str, Any],
    *,
    business_journey_payload: Dict[str, Any],
    products_services_payload: Dict[str, Any],
    financial_visual_summaries_payload: Optional[Dict[str, Any]] = None,
    uncertainty_map_payload: Optional[Dict[str, Any]] = None,
    company_slug: str,
    generated_at: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    answers = []
    diagnostics = {
        "built_questions": [],
        "missing_upstream_sources": [],
        "repetition_issues": {},
        "contradiction_issues": {},
    }
    available_visual_ids = {
        str(item.get("id") or "")
        for item in (financial_visual_summaries_payload or {}).get("visuals", []) or []
        if str(item.get("id") or "").strip()
    }
    investor_financial_modules = {
        "owner_earnings_bridge": _source_payload(source_bundle, "owner_earnings_bridge"),
        "working_capital_quality_drilldown": _source_payload(source_bundle, "working_capital_quality_drilldown"),
        "capital_allocation_roi_ledger": _source_payload(source_bundle, "capital_allocation_roi_ledger"),
        "per_share_compounding_analysis": _source_payload(source_bundle, "per_share_compounding_analysis"),
    }
    financial_truth_pack = _source_payload(source_bundle, "financial_truth_pack")
    for question_id in QUESTION_INDEX:
        context_policy = get_context_policy_for_question(question_id)
        answer = build_answer_for_question(
            question_id,
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            generated_at=generated_at,
        )
        answer["financial_visual_refs"] = [
            visual_id
            for visual_id in context_policy["allowed_financial_visual_ids"]
            if visual_id in available_visual_ids
        ]
        answer["uncertainty_note"] = build_uncertainty_note_for_answer(
            question_id=question_id,
            answer_status=str(answer.get("answer_status") or ""),
            fallback_message=str((answer.get("uncertainty_note") or {}).get("message") or ""),
            uncertainty_map_payload=uncertainty_map_payload,
        )
        answer = finalize_answer_against_reconciled_truth(
            answer,
            financial_truth_pack,
            investor_financial_modules,
            uncertainty_map_payload or {},
        )
        repetition_issues = detect_public_answer_repetition(answer)
        contradiction_issues = detect_answer_truth_contradictions(
            answer,
            financial_truth_pack,
            investor_financial_modules,
        )
        if repetition_issues:
            diagnostics["repetition_issues"][question_id] = repetition_issues
        if contradiction_issues:
            diagnostics["contradiction_issues"][question_id] = contradiction_issues
        answers.append(answer)
        diagnostics["built_questions"].append(question_id)
    payload = sanitize_public_payload(
        {
            "schema_version": "ask_intrinsiciq_answer_cards.v1",
            "company_slug": company_slug,
            "answers": answers,
            "coverage_summary": _build_coverage_summary(answers),
            "generated_at": generated_at,
        }
    )
    return payload, diagnostics


def build_question_catalog_view(answer_cards_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    status_by_question = {
        str(answer.get("question_id") or ""): str(answer.get("answer_status") or "unavailable")
        for answer in answer_cards_payload.get("answers", []) or []
    }
    categories = []
    for category in QUESTION_CATALOG:
        questions = []
        for question in category["questions"]:
            questions.append(
                {
                    "id": question["id"],
                    "categoryId": category["id"],
                    "title": question["title"],
                    "shortLabel": question["short_label"],
                    "recommended": bool(question["recommended"]),
                    "availabilityStatus": status_by_question.get(question["id"], "unavailable"),
                    "answerCardId": f"answer-{question['id']}",
                }
            )
        categories.append(
            {
                "id": category["id"],
                "title": category["title"],
                "shortDescription": category["short_description"],
                "displayOrder": category["display_order"],
                "questions": questions,
            }
        )
    return categories


QUESTION_TYPE_BY_ID = {
    "what-does-company-do": "factual",
    "who-are-the-customers": "factual",
    "how-does-it-make-money": "factual",
    "what-makes-the-offering-important": "factual",
    "where-is-evidence-thin": "diligence",
    "are-profits-converting-into-cash": "financial",
    "what-is-owner-earnings": "financial",
    "is-working-capital-a-concern": "financial",
    "are-per-share-economics-improving": "financial",
    "which-financial-assumption-matters-most": "financial",
    "what-has-management-promised": "progression",
    "did-past-claims-come-true": "progression",
    "what-projects-are-underway": "progression",
    "how-is-capacity-changing": "progression",
    "what-is-management-commentary-saying": "progression",
    "how-is-capital-allocated": "capital_allocation",
    "what-incentives-matter": "management_quality",
    "what-should-i-ask-ir": "diligence",
    "what-would-graham-worry-about": "investor_lens",
    "what-would-buffett-focus-on": "investor_lens",
    "where-would-fisher-be-curious": "investor_lens",
    "what-would-munger-avoid": "investor_lens",
    "how-would-lynch-explain-it": "investor_lens",
    "what-can-break-the-thesis": "risk",
    "which-disclosure-is-missing": "diligence",
    "what-evidence-would-change-the-view": "diligence",
    "what-needs-management-clarification": "diligence",
    "what-remains-unresolved": "diligence",
    "what-are-key-risks": "risk",
}


def get_question_type_for_question(question_id: str) -> str:
    return QUESTION_TYPE_BY_ID.get(question_id, "factual")


def build_answer_for_question(
    question_id: str,
    source_bundle: Dict[str, Any],
    *,
    business_journey_payload: Dict[str, Any],
    products_services_payload: Dict[str, Any],
    generated_at: str,
) -> Dict[str, Any]:
    question = QUESTION_INDEX[question_id]
    builder = ANSWER_BUILDERS.get(question_id, _build_generic_not_supported_answer)
    draft = builder(
        source_bundle,
        business_journey_payload=business_journey_payload,
        products_services_payload=products_services_payload,
        question=question,
    )
    answer = {
        "id": question["answer_card_id"],
        "question_id": question_id,
        "category_id": question["category_id"],
        "title": question["title"],
        "simple_answer": draft["simple_answer"],
        "why_it_matters": draft["why_it_matters"],
        "key_points": draft["key_points"][:4],
        "detailed_explanation": draft["detailed_explanation"],
        "products_and_services_refs": draft["products_and_services_refs"],
        "business_journey_ref": draft["business_journey_ref"],
        "business_journey_mode": draft["business_journey_mode"],
        "financial_visual_refs": [],
        "progression": draft.get("progression"),
        "evidence_summary": draft["evidence_summary"],
        "uncertainty_note": draft["uncertainty_note"],
        "next_questions": _build_next_questions(question_id),
        "answer_status": draft["answer_status"],
        "customer_roles": draft.get("customer_roles"),
        "revenue_flow": draft.get("revenue_flow"),
        "structured_sections": draft.get("structured_sections") or [],
        "question_type": get_question_type_for_question(question_id),
        "generated_at": generated_at,
    }
    return sanitize_public_payload(answer)


def _build_business_summary_answer(
    source_bundle: Dict[str, Any],
    *,
    business_journey_payload: Dict[str, Any],
    products_services_payload: Dict[str, Any],
    question: Dict[str, Any],
) -> Dict[str, Any]:
    summary = str(products_services_payload.get("summary") or "").strip()
    business_model_summary = str(products_services_payload.get("business_model_summary") or "").strip()
    customer_summary = str(products_services_payload.get("customer_summary") or "").strip()
    revenue_logic_summary = str(products_services_payload.get("revenue_logic_summary") or "").strip()
    journey_summary = str(business_journey_payload.get("summary") or "").strip()
    status = "supported" if summary and business_model_summary else "partially_supported" if summary or business_model_summary else "not_supported"
    if status == "not_supported":
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
        )
    product_names = _first_product_names(products_services_payload, limit=3)
    customer_overview = customer_summary or "The customer mix is only partly visible in the available evidence."
    revenue_overview = revenue_logic_summary or "Revenue appears tied to programme delivery rather than recurring subscription-style billing."
    return _draft(
        answer_status=status,
        simple_answer=first_available_text(
            business_model_summary,
            summary,
            "The available company memory supports only a limited plain-language business summary.",
        ),
        why_it_matters="This matters because a good first read should explain what the company actually sells before moving into financial judgment or investor-style interpretation.",
        key_points=[
            customer_overview,
            f"Visible offerings include {_join_human_list(product_names)}." if product_names else "",
            revenue_overview,
            journey_summary,
        ],
        detailed_explanation=" ".join(
            part
            for part in [
                summary if summary and summary != business_model_summary else "",
                customer_overview,
                revenue_overview,
                journey_summary,
            ]
            if part
        ),
        evidence_status="direct" if status == "supported" else "partial",
        evidence_summary=first_available_text(
            "Supported by business, offering, and company-history evidence already present in company memory.",
            summary,
        )
        or "Supported by current business evidence.",
        evidence_points=[
            business_model_summary,
            customer_summary,
            revenue_logic_summary,
        ],
        uncertainty="Customer concentration, programme mix, and offering-level revenue contribution are still only partly visible in the current evidence.",
        products_refs=_first_product_refs(products_services_payload, limit=4),
        business_journey_ref=None,
        business_journey_mode="full",
    )


def _build_customers_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    customer_summary = str(products_services_payload.get("customer_summary") or "").strip()
    customer_types = _unique_product_customer_types(products_services_payload)
    paying_customers = _customer_roles_from_types(customer_types, role="paying")
    integrating_customers = _customer_roles_from_types(customer_types, role="integrating")
    using_customers = _customer_roles_from_types(customer_types, role="using")
    international_customers = [label for label in customer_types if "international" in label.lower()]
    customer_roles = _build_customer_roles(
        payers=paying_customers,
        integrators_or_partners=integrating_customers,
        end_users=using_customers,
        international_customers=international_customers,
        concentration_note="Customer concentration and repeat-order mix are not clearly disclosed in the available evidence.",
        evidence_status="partial",
    )
    if not customer_summary and not customer_types:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available company memory does not yet support a reliable customer map for this question.",
            why="Customer identity matters because concentration, procurement cycles, and repeat-order behavior can shape both growth quality and risk.",
            limitation="Customer names, concentration, and repeat-order share are not clearly disclosed in the available evidence.",
        )
    type_summary = _join_human_list(customer_types) if customer_types else "institutional customers"
    simple_parts = []
    if paying_customers:
        simple_parts.append(f"The available evidence points to {_join_human_list(paying_customers)} as the main paying customers.")
    if integrating_customers:
        simple_parts.append(f"Programme delivery also appears to involve {_join_human_list(integrating_customers)} as integrators or platform partners.")
    if using_customers:
        simple_parts.append(f"The visible end users appear to include {_join_human_list(using_customers)}.")
    return _draft(
        answer_status="partially_supported",
        simple_answer=first_available_text(
            " ".join(simple_parts),
            customer_summary,
            f"The available evidence points mainly to {type_summary}, but it does not provide a clean customer-by-customer breakdown.",
        )
        or "The available evidence points to institutional customers, but the exact mix is not fully disclosed.",
        why_it_matters="This matters because customer quality is shaped by who buys, how concentrated demand is, and whether revenue depends on a small number of long-cycle programs.",
        key_points=[
            f"Who pays: {_join_human_list(paying_customers)}." if paying_customers else "Who pays is not clearly distinguished in the available evidence.",
            f"Who integrates: {_join_human_list(integrating_customers)}." if integrating_customers else "Integration or partner roles are not clearly separated.",
            f"Who uses: {_join_human_list(using_customers)}." if using_customers else "End-user roles are not clearly separated.",
            "Customer concentration is still not clearly disclosed.",
        ],
        detailed_explanation=" ".join(
            part
            for part in [
                customer_summary,
                str(products_services_payload.get("revenue_logic_summary") or ""),
                "The source set is stronger on customer roles and customer type than on named-customer concentration or repeat-order mix.",
            ]
            if part
        ),
        evidence_status="partial",
        evidence_summary="Partially supported because customer type is visible, but customer concentration and named-customer detail are not.",
        evidence_points=[
            f"Visible customer types: {type_summary}." if customer_types else "",
            customer_summary,
        ],
        uncertainty="Customer concentration and repeat-order visibility remain limited.",
        products_refs=_first_product_refs(products_services_payload, limit=3),
        business_journey_ref=None,
        customer_roles=customer_roles,
    )


def _build_make_money_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    business_model_summary = str(products_services_payload.get("business_model_summary") or "").strip()
    revenue_logic_summary = str(products_services_payload.get("revenue_logic_summary") or "").strip()
    if not business_model_summary and not revenue_logic_summary:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available company memory does not yet describe the revenue model clearly enough to answer this confidently.",
            why="How the company makes money shapes margin durability, working-capital needs, and how understandable the business really is.",
            limitation="Pricing, contract structure, and billing mechanics are not described in enough detail in the available evidence.",
        )
    customer_summary = str(products_services_payload.get("customer_summary") or "").strip()
    cash_cycle_text = _working_capital_implication(source_bundle)
    revenue_flow = _build_revenue_flow(source_bundle, products_services_payload)
    return _draft(
        answer_status="partially_supported" if revenue_logic_summary else "supported",
        simple_answer=first_available_text(
            revenue_logic_summary,
            business_model_summary,
            "The company appears to earn through specialised product and project delivery.",
        ),
        why_it_matters="This matters because revenue quality depends not only on what is sold, but also on whether delivery is recurring, project-based, milestone-driven, or tied to capital deployment ahead of billing.",
        key_points=[
            "Revenue appears mainly project-based rather than recurring." if revenue_logic_summary else "",
            "The visible flow is order or programme, design and build, testing or qualification, then billing and collection." if revenue_logic_summary else "",
            cash_cycle_text,
            customer_summary,
        ],
        detailed_explanation=" ".join(
            part
            for part in [
                business_model_summary,
                customer_summary,
                cash_cycle_text,
                "That means revenue timing can depend on milestone acceptance, programme schedules, and how quickly customers pay after delivery."
                if revenue_logic_summary
                else "",
            ]
            if part
        ),
        evidence_status="partial" if revenue_logic_summary else "direct",
        evidence_summary="Supported by the current business-model and revenue-logic evidence, though pricing detail and customer concentration remain thin.",
        evidence_points=[revenue_logic_summary, cash_cycle_text],
        uncertainty="The available material does not fully spell out pricing mechanics, milestone mix, or customer concentration.",
        products_refs=_first_product_refs(products_services_payload, limit=3),
        business_journey_ref=None,
        revenue_flow=revenue_flow,
    )


def _build_offering_importance_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    value_creation = _latest_business_model_field(source_bundle, "value_creation")
    important_items = _first_product_names(products_services_payload, limit=3)
    if not value_creation and not important_items:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
        )
    return _draft(
        answer_status="partially_supported",
        simple_answer="The offering appears important because it sits inside specialized customer workflows where qualification, reliability, and integration depth matter more than broad commodity scale.",
        why_it_matters="This matters because some businesses are important not because they are mass-market, but because they solve high-stakes customer problems where reliability and qualification matter more than volume alone.",
        key_points=[
            f"Visible offerings include {', '.join(important_items)}." if important_items else "",
            value_creation,
            str(products_services_payload.get("business_model_summary") or ""),
        ],
        detailed_explanation=" ".join(
            part
            for part in [
                "The current evidence suggests the offering matters because it supports specialized programs where technical qualification, delivery reliability, and integration capability are important.",
                value_creation,
                str(products_services_payload.get("business_model_summary") or ""),
                str(products_services_payload.get("customer_summary") or ""),
            ]
            if part
        ),
        evidence_status="partial",
        evidence_summary="Partially supported because strategic importance is visible more clearly than quantified product-level economics.",
        evidence_points=[value_creation, str(products_services_payload.get("business_model_summary") or "")],
        uncertainty="The evidence supports strategic relevance more clearly than it supports offering-level pricing power or revenue dependence.",
        products_refs=_first_product_refs(products_services_payload, limit=4),
        business_journey_ref=None,
    )


def _build_evidence_thin_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    truth = _source_payload(source_bundle, "financial_truth_pack")
    committee = _source_payload(source_bundle, "committee_synthesis")
    thin_points = _clean_list(
        list(products_services_payload.get("open_questions", []) or [])
        + _get_string_list(truth, "precision_limits")
        + _get_string_list(_get_record(committee, "financial_committee_view"), "missing_financial_data")
    )[:4]
    if not thin_points:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    return _draft(
        answer_status="supported",
        simple_answer="The thinnest evidence is around owner-economics precision, customer concentration detail, and the drivers of working-capital intensity.",
        why_it_matters="This matters because those gaps can change how durable the business and its cash generation really are, even when the broad story sounds understandable.",
        key_points=thin_points,
        detailed_explanation="The current source set is stronger on broad business framing than on decision-grade precision in owner economics, customer concentration, and working-capital explanation.",
        evidence_status="direct",
        evidence_summary="Supported by visible evidence gaps already recorded in the current company-memory and financial limitation surfaces.",
        evidence_points=thin_points[:3],
        uncertainty="These gaps are visible in the evidence itself, not inferred from missing UI content.",
        products_refs=[],
        business_journey_ref=None,
    )


def _build_cash_conversion_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    bridge = _latest_year_record(_source_payload(source_bundle, "owner_earnings_bridge"), "bridges")
    working_capital = _latest_year_record(_source_payload(source_bundle, "working_capital_quality_drilldown"), "drilldown")
    per_share = _latest_year_record(_source_payload(source_bundle, "per_share_compounding_analysis"), "analysis")
    pat = _get_number(bridge, "reported_pat")
    cfo = _get_number(bridge, "cfo")
    owner = _get_number(bridge, "owner_earnings_estimate")
    if pat is None and cfo is None and owner is None:
        return _build_unavailable_answer(
            question,
            "The required cash-conversion evidence is not available in the current source set.",
            "Cash-conversion analysis needs current profit, cash-flow, and working-capital evidence. Without those, this answer would overreach.",
            "The current source set does not include a usable current-year profit-to-cash bridge.",
        )
    current_year = _year_label(bridge) or _year_label(working_capital) or "the latest reported year"
    return _draft(
        answer_status="supported" if pat is not None and cfo is not None else "partially_supported",
        simple_answer=(
            f"In {current_year.upper()}, reported profit is {format_crore(pat)}, operating cash flow is {format_crore(cfo)}, "
            f"and a conservative owner-earnings estimate of {format_crore(owner)} is available. "
            f"Cash conversion still looks stretched because receivable days are {format_number(_get_number(working_capital, 'receivable_days'))}, "
            f"inventory days are {format_number(_get_number(working_capital, 'inventory_days'))}, and the cash conversion cycle is {format_number(_get_number(working_capital, 'cash_conversion_cycle'))} days."
        ),
        why_it_matters="This matters because accounting profit can look healthy while cash remains trapped in receivables, inventory, or project timing. Investors care about both the profit and the path from profit to cash.",
        key_points=[
            f"Reported profit is {format_crore(pat)} and operating cash flow is {format_crore(cfo)}.",
            f"A conservative owner-earnings estimate of {format_crore(owner)} is available after identified capex.",
            f"Receivable days are {format_number(_get_number(working_capital, 'receivable_days'))}, inventory days are {format_number(_get_number(working_capital, 'inventory_days'))}, and payable days are {format_number(_get_number(working_capital, 'payable_days'))}.",
            f"Owner earnings per share is {format_per_share(_get_number(per_share, 'owner_earnings_per_share'))}.",
        ],
        detailed_explanation="Profit and cash are related but not identical. Operating cash flow shows what cash actually came in from operations, while owner earnings try to adjust profit for reinvestment needs. The current evidence shows positive cash generation, but it also shows very heavy working-capital demands that can delay conversion from reported profit into readily usable cash.",
        evidence_status="direct",
        evidence_summary="Supported by current financial truth, owner-earnings, and working-capital evidence.",
        evidence_points=[
            _first_string(_get_list(bridge, "owner_earnings_warnings"), _get_list(bridge, "warnings")),
            _get_string(working_capital, "cash_strain_risk"),
        ],
        uncertainty=_first_string(_get_list(bridge, "owner_earnings_warnings"), _get_list(_source_payload(source_bundle, "financial_truth_pack"), "precision_limits"))
        or "Maintenance versus growth capex is not fully disclosed, so owner-earnings precision remains limited.",
        products_refs=[],
        business_journey_ref=None,
    )


def _build_owner_earnings_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    bridge = _latest_year_record(_source_payload(source_bundle, "owner_earnings_bridge"), "bridges")
    owner = _get_number(bridge, "owner_earnings_estimate")
    if owner is None:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available company memory does not yet support a reliable owner-earnings answer.",
            why="Owner earnings matter because they try to translate accounting performance into owner-oriented cash generation after reinvestment needs.",
            limitation="A usable owner-earnings bridge is not available from the current evidence set.",
        )
    current_year = _year_label(bridge) or "the latest reported year"
    return _draft(
        answer_status="supported",
        simple_answer=f"Owner earnings are a conservative way to think about what cash the business may produce after the reinvestment needed to keep it operating. In {current_year.upper()}, the available evidence supports an owner-earnings estimate of {format_crore(owner)}.",
        why_it_matters="This matters because reported profit can overstate what is really available to owners if the business needs significant ongoing reinvestment or if cash conversion is weaker than profit suggests.",
        key_points=[
            f"The current owner-earnings estimate is {format_crore(owner)}.",
            "The bridge is intentionally conservative and should not be treated as an exact free-cash-flow number.",
            _first_string(_get_list(bridge, "owner_earnings_warnings"), _get_list(_source_payload(source_bundle, "financial_truth_pack"), "precision_limits")),
        ],
        detailed_explanation="Owner earnings start with cash generation and then ask how much reinvestment is really needed to sustain the business. That makes the concept useful for investor reading, but the estimate is only as good as the capex detail behind it. The current evidence provides a usable estimate, while still preserving an important limitation around maintenance versus growth capex.",
        evidence_status="direct",
        evidence_summary="Supported by the owner-earnings bridge and the current financial truth summary.",
        evidence_points=[
            _first_string(_get_list(bridge, "owner_earnings_warnings"), _get_list(bridge, "warnings")),
        ],
        uncertainty=_first_string(_get_list(bridge, "owner_earnings_warnings"), _get_list(_source_payload(source_bundle, "financial_truth_pack"), "precision_limits"))
        or "Maintenance versus growth capex is not split cleanly, so the estimate should be treated as conservative rather than exact.",
        products_refs=[],
        business_journey_ref=None,
    )


def _build_working_capital_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    working_capital = _latest_year_record(_source_payload(source_bundle, "working_capital_quality_drilldown"), "drilldown")
    if _get_number(working_capital, "cash_conversion_cycle") is None:
        return _build_unavailable_answer(
            question,
            "The required working-capital evidence is not available in the current source set.",
            "Working-capital analysis needs receivable, inventory, payable, and cash-cycle evidence. Without those fields, this answer would be guesswork.",
            "A usable working-capital drilldown is not available.",
        )
    return _draft(
        answer_status="supported",
        simple_answer=(
            f"Yes. Working-capital intensity looks severe, with receivable days at {format_number(_get_number(working_capital, 'receivable_days'))}, "
            f"inventory days at {format_number(_get_number(working_capital, 'inventory_days'))}, payable days at {format_number(_get_number(working_capital, 'payable_days'))}, "
            f"and a cash conversion cycle of {format_number(_get_number(working_capital, 'cash_conversion_cycle'))} days."
        ),
        why_it_matters="This matters because cash can get trapped in receivables and inventory even when reported margins look strong. That can limit flexibility and make growth more funding-intensive.",
        key_points=[
            f"Receivables are {format_crore(_get_number(working_capital, 'receivables'))}.",
            f"Inventory is {format_crore(_get_number(working_capital, 'inventory'))}.",
            f"Payables are {format_crore(_get_number(working_capital, 'payables'))}.",
            _get_string(working_capital, "cash_strain_risk"),
        ],
        detailed_explanation="Working capital is where reported profit meets operating reality. When receivables or inventory stay high for long periods, cash remains tied up even if revenue and margins look healthy. The current evidence shows a long cash cycle, which means the business may need more patience, more capital, or both before reported performance becomes available as cash.",
        evidence_status="direct",
        evidence_summary="Supported by the working-capital drilldown and current-year financial truth evidence.",
        evidence_points=[
            _get_string(working_capital, "working_capital_intensity_status"),
            _get_string(working_capital, "cash_strain_risk"),
        ],
        uncertainty="The evidence shows the scale of working-capital intensity more clearly than it explains whether it comes from normal billing patterns, production timing, or collection pressure.",
        products_refs=[],
        business_journey_ref=None,
    )


def _build_per_share_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    per_share = _latest_year_record(_source_payload(source_bundle, "per_share_compounding_analysis"), "analysis")
    if _get_number(per_share, "owner_earnings_per_share") is None and _get_number(per_share, "book_value_per_share") is None:
        return _build_unavailable_answer(
            question,
            "The required per-share evidence is not available in the current source set.",
            "Per-share analysis needs usable share-count and per-share metrics. Without those, any improvement claim would be too confident.",
            "A usable per-share analysis is not available.",
        )
    warning = _first_string(_get_list(_source_payload(source_bundle, "per_share_compounding_analysis"), "warnings"), _get_list(_source_payload(source_bundle, "financial_truth_pack"), "precision_limits"))
    return _draft(
        answer_status="partially_supported",
        simple_answer=f"The current evidence shows owner earnings per share at {format_per_share(_get_number(per_share, 'owner_earnings_per_share'))} and book value per share at {format_per_share(_get_number(per_share, 'book_value_per_share'))}, but it does not yet support a clean multi-year improvement claim.",
        why_it_matters="This matters because aggregate company growth does not automatically translate into better economics for each shareholder. Per-share evidence is what helps test real compounding.",
        key_points=[
            f"Owner earnings per share are {format_per_share(_get_number(per_share, 'owner_earnings_per_share'))}.",
            f"Book value per share is {format_per_share(_get_number(per_share, 'book_value_per_share'))}.",
            f"Basic EPS is {format_per_share(_get_number(per_share, 'eps_basic'))}.",
            warning,
        ],
        detailed_explanation="Per-share analysis asks whether business progress is being spread across too many shares or is actually accruing to each owner. The current evidence gives a current-year snapshot, but it does not provide enough clean multi-year comparability to support a stronger improvement narrative.",
        evidence_status="partial",
        evidence_summary="Partially supported because current per-share metrics are visible, but multi-year comparability is still limited.",
        evidence_points=[warning],
        uncertainty=warning or "A clean multi-year per-share trend is not yet well supported.",
        products_refs=[],
        business_journey_ref=None,
    )


def _build_financial_assumption_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    committee = _source_payload(source_bundle, "committee_synthesis")
    truth = _source_payload(source_bundle, "financial_truth_pack")
    question_text = _first_string(
        _get_string_list(_get_record(committee, "financial_committee_view"), "investor_questions_from_financials"),
        _get_string_list(truth, "investor_relevant_questions"),
    )
    if not question_text:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    return _draft(
        answer_status="supported",
        simple_answer="The most important financial assumption is how much of current capex is maintenance versus growth.",
        why_it_matters="This matters because that single judgment changes how much of current cash generation looks truly distributable versus how much is needed just to sustain the business.",
        key_points=[
            question_text,
            _first_string(_get_string_list(truth, "precision_limits")),
            "A different maintenance-capex assumption can materially change how conservative the owner-earnings view should be.",
        ],
        detailed_explanation="The current evidence supports a useful owner-earnings view, but the capex split is still the key swing factor. If a large share of capex is maintenance, then less cash is genuinely free to owners. If more of it is growth, current earning power may be stronger than the conservative reading suggests.",
        evidence_status="direct",
        evidence_summary="Supported by committee follow-up questions and financial precision limits already present in the source set.",
        evidence_points=[question_text],
        uncertainty="Without a maintenance-versus-growth split, owner-oriented cash interpretation remains approximate.",
        products_refs=[],
        business_journey_ref=None,
    )


def _normalize_progression_impact(value: Any, fallback: str = "unclear") -> str:
    text = str(value or "").strip().lower()
    if text in {"strengthened", "weakened", "unchanged", "unclear"}:
        return text
    return fallback


def _normalize_turning_points(turning_points: List[Dict[str, Any]], *, default_impact: str = "unclear") -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for point in turning_points:
        normalized.append(
            {
                "period": _first_string(_get_string(point, "period"), _get_string(point, "latest_period")),
                "label": _first_string(_get_string(point, "label"), _get_string(point, "change_type"), _get_string(point, "title"), _get_string(point, "description")),
                "description": _first_string(_get_string(point, "description"), _get_string(point, "summary")),
                "why_it_matters": _first_string(_get_string(point, "why_it_matters"), _get_string(point, "why_it_matters_text")) or "This changes how investors should think about execution progress.",
                "impact": _normalize_progression_impact(_first_string(_get_string(point, "impact"), _get_string(point, "conviction_impact"), _get_string(point, "direction")), fallback=default_impact),
            }
        )
    return [point for point in normalized if point["label"] or point["description"]]


def _make_progression_block(
    *,
    headline: str,
    current_state: str,
    what_changed: str,
    why_it_changed: str,
    conviction_impact: str,
    latest_evidence: List[str],
    unresolved_items: List[str],
    turning_points: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "headline": sanitize_public_text(headline),
        "current_state": sanitize_public_text(current_state),
        "what_changed": sanitize_public_text(what_changed),
        "why_it_changed": sanitize_public_text(why_it_changed),
        "conviction_impact": _normalize_progression_impact(conviction_impact),
        "latest_evidence": _clean_list(latest_evidence)[:4],
        "unresolved_items": _clean_list(unresolved_items)[:4],
        "turning_points": _normalize_turning_points(turning_points)[:4],
    }


def _make_interpretation_from_progression(
    *,
    progression: Dict[str, Any],
    conclusion: str,
    economic_mechanism: str,
    thesis_impact: str,
    confidence_level: str = "medium",
    positive_evidence: Optional[List[Any]] = None,
    negative_evidence: Optional[List[Any]] = None,
    unresolved: Optional[List[Any]] = None,
    what_to_watch: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    turning_points = _normalize_turning_points(_get_record_list(progression, "turning_points"))
    return build_interpretation_contract(
        conclusion=conclusion,
        what_changed=[item for item in _clean_list([_get_string(progression, "what_changed")])[:3]] or [conclusion],
        why_it_matters=_get_string(progression, "why_it_changed") or _get_string(progression, "headline"),
        economic_mechanism=economic_mechanism,
        thesis_impact=thesis_impact,
        positive_evidence=positive_evidence or _get_string_list(progression, "latest_evidence"),
        negative_evidence=negative_evidence or _get_string_list(progression, "unresolved_items"),
        unresolved=unresolved or _get_string_list(progression, "unresolved_items"),
        what_to_watch=what_to_watch
        or [
            point["description"] or point["label"]
            for point in turning_points[:3]
            if point.get("description") or point.get("label")
        ],
        confidence={"level": confidence_level, "basis": [], "limitations": []},
    )


def _commitment_period(commitment: Dict[str, Any]) -> str:
    refs = _get_record_list(commitment, "source_references")
    for ref in refs:
        period = _first_string(_get_string(ref, "period"), _get_string(ref, "source_year"))
        if period:
            return period
    return _first_string(_get_string(commitment, "expected_timeframe"))


def _commitment_priority_rank(commitment: Dict[str, Any]) -> int:
    priority = _get_string(commitment, "priority").lower()
    score = {"high": 3, "medium": 2, "low": 1}.get(priority, 1)
    text = " ".join(
        _get_string(commitment, key)
        for key in ("topic", "normalized_commitment", "delivery_assessment", "investor_implication")
    ).lower()
    if any(token in text for token in ("capacity", "facility", "commission", "commissioning", "target", "margin", "revenue", "product", "customer", "export", "capex")):
        score += 2
    if any(token in text for token in ("continue to focus", "strategy", "philosophy", "operational discipline", "process excellence")):
        score -= 2
    return max(score, 0)


def _commitment_status_label(commitment: Dict[str, Any]) -> str:
    status = _get_string(commitment, "status")
    if not status:
        return "Unable To Verify"
    lowered = status.lower()
    if lowered in {"unable to verify", "unable_to_verify"}:
        return "Unable To Verify"
    if lowered in {"in progress", "in_progress"}:
        return "In Progress"
    if lowered in {"partially delivered", "partially_delivered"}:
        return "Partially Delivered"
    if lowered in {"delivered"}:
        return "Delivered"
    return status[:1].upper() + status[1:]


def _clean_display_phrase(text: str, *, limit_words: int = 12) -> str:
    cleaned = sanitize_public_text(text)
    if not cleaned:
        return ""
    words = cleaned.split()
    if len(words) <= limit_words:
        return cleaned
    if cleaned.endswith((".", "?", "!")):
        return cleaned
    return ""


def _strip_backend_phrasing(text: str) -> str:
    cleaned = sanitize_public_text(text)
    if not cleaned:
        return ""
    replacements = (
        (" are reported in the compact financial inputs", ""),
        ("reported in the compact financial inputs", ""),
        ("compact financial inputs", ""),
        ("source set summaries", ""),
        ("committee-level output", ""),
        ("company memory", ""),
        ("available evidence summary", ""),
    )
    for needle, replacement in replacements:
        cleaned = re.sub(re.escape(needle), replacement, cleaned, flags=re.IGNORECASE)
    cleaned = " ".join(cleaned.split()).strip(" ,;:-")
    return sanitize_public_text(cleaned)


def _commitment_summary(commitment: Dict[str, Any], *, include_status: bool = True) -> str:
    period = _commitment_period(commitment)
    label = _commitment_topic_label(commitment)
    later_evidence = first_available_text(
        _get_string(commitment, "delivery_assessment"),
        _get_string(commitment, "investor_implication"),
        "Later evidence remains limited.",
    )
    later_evidence = _clean_display_phrase(later_evidence, limit_words=18)
    significance = first_available_text(
        _get_string(commitment, "investor_implication"),
        later_evidence,
    )
    significance = _clean_display_phrase(significance, limit_words=18)
    parts = []
    if period:
        parts.append(f"{period.upper()} — {label}")
    else:
        parts.append(label)
    if include_status:
        parts.append(f"Current: {_commitment_status_label(commitment)}.")
    parts.append(f"Later evidence: {later_evidence}.")
    parts.append(f"Investor significance: {significance}.")
    return " ".join(part.strip() for part in parts if part.strip())


def _commitment_topic_label(commitment: Dict[str, Any]) -> str:
    label = _first_string(_get_string(commitment, "topic"), _get_string(commitment, "normalized_commitment"), "Management commitment")
    return _clean_display_phrase(label, limit_words=8)


def _commitment_reference_label(commitment: Dict[str, Any]) -> str:
    period = _commitment_period(commitment)
    label = _commitment_topic_label(commitment)
    if period and label:
        return f"{period.upper()} {label}"
    return label


def _material_commitments(commitments: List[Dict[str, Any]], *, limit: int = 4) -> List[Dict[str, Any]]:
    ranked = sorted(
        (item for item in commitments if isinstance(item, dict)),
        key=lambda item: (
            _commitment_priority_rank(item),
            -(_year_sort_key(_commitment_period(item)) or 0),
            _get_string(item, "topic"),
            _get_string(item, "normalized_commitment"),
        ),
        reverse=True,
    )
    material: List[Dict[str, Any]] = []
    seen_topics = set()
    for item in ranked:
        topic_key = _normalize_sentence(_first_string(_get_string(item, "topic"), _get_string(item, "normalized_commitment")))
        if not topic_key or topic_key in seen_topics:
            continue
        seen_topics.add(topic_key)
        material.append(item)
        if len(material) >= limit:
            break
    return material


def _commitment_progression(commitment: Dict[str, Any]) -> Dict[str, Any]:
    progression = _get_record(commitment, "progression")
    label = _clean_display_phrase(
        _first_string(_get_string(commitment, "normalized_commitment"), _get_string(commitment, "topic"), "Management commitment"),
        limit_words=14,
    )
    return _make_progression_block(
        headline=label,
        current_state=_first_string(_get_string(commitment, "status"), _get_string(progression, "current_state"), _get_string(progression, "latest_status"), "Unable To Verify"),
        what_changed=_clean_display_phrase(_first_string(_get_string(commitment, "topic"), _get_string(commitment, "normalized_commitment"), _get_string(commitment, "delivery_assessment")), limit_words=14),
        why_it_changed=_clean_display_phrase(_first_string(_get_string(commitment, "investor_implication"), _get_string(commitment, "delivery_assessment"), "Later evidence changed the confidence level."), limit_words=16),
        conviction_impact=_first_string(_get_string(progression, "conviction_impact"), _get_string(commitment, "delivery_assessment"), "unclear"),
        latest_evidence=[
            _clean_display_phrase(_get_string(commitment, "delivery_assessment"), limit_words=18),
            _clean_display_phrase(_get_string(commitment, "investor_implication"), limit_words=18),
            _first_string(_get_string_list(progression, "unresolved_questions")),
        ],
        unresolved_items=_get_string_list(progression, "unresolved_questions"),
        turning_points=_get_record_list(progression, "turning_points"),
    )


def _commitment_watch_item(commitment: Dict[str, Any]) -> str:
    topic = _clean_display_phrase(
        _first_string(_get_string(commitment, "topic"), _get_string(commitment, "normalized_commitment"), "the commitment"),
        limit_words=8,
    )
    if not topic:
        return ""
    status = _commitment_status_label(commitment).lower()
    topic_text = topic.lower()
    if status in {"in progress", "delayed"}:
        return f"Completion evidence for {topic_text}"
    if status == "unable to verify":
        return f"Later evidence confirming or overturning {topic_text}"
    return f"Follow-through evidence for {topic_text}"


def _project_progression(project: Dict[str, Any]) -> Dict[str, Any]:
    progression = _get_record(project, "progression")
    summary = _get_record(project, "progression_summary")
    assessment = _get_record(project, "assessment")
    return _make_progression_block(
        headline=_first_string(_get_string(project, "project_name"), _get_string(project, "normalized_name"), "Project"),
        current_state=_first_string(_get_string(project, "current_status"), _get_string(summary, "current_state"), _get_string(assessment, "execution_status"), "Unable To Verify"),
        what_changed=_first_string(_get_string(summary, "what_changed"), _get_string(assessment, "execution_summary")),
        why_it_changed=_first_string(_get_string(summary, "why_it_changed"), _get_string(project, "investor_implication")),
        conviction_impact=_first_string(_get_string(summary, "conviction_impact"), _get_string(project, "investor_implication"), "unclear"),
        latest_evidence=[
            _get_string(assessment, "execution_summary"),
            _get_string(assessment, "observed_business_effect"),
            _get_string(assessment, "observed_financial_effect"),
        ],
        unresolved_items=_get_string_list(assessment, "unresolved_questions") or _get_string_list(project, "unresolved_questions"),
        turning_points=_get_record_list(progression, "turning_points"),
    )


def _capacity_progression(capacity: Dict[str, Any]) -> Dict[str, Any]:
    summary = _get_record(capacity, "progression_summary")
    assessment = _get_record(capacity, "capacity_assessment")
    turning_points = _get_record_list(_get_record(capacity, "progression"), "turning_points")
    return _make_progression_block(
        headline=_first_string(_get_string(capacity, "capacity_name"), _get_string(capacity, "normalized_name"), "Capacity item"),
        current_state=_first_string(_get_string(capacity, "current_status"), _get_string(assessment, "execution_status"), _get_string(assessment, "utilization_status"), "Unable To Verify"),
        what_changed=_first_string(_get_string(summary, "what_changed"), _get_string(assessment, "observed_business_effect")),
        why_it_changed=_first_string(_get_string(summary, "why_it_changed"), _get_string(capacity, "investor_implication")),
        conviction_impact=_first_string(_get_string(summary, "conviction_impact"), _get_string(capacity, "investor_implication"), "unclear"),
        latest_evidence=[
            _get_string(assessment, "observed_business_effect"),
            _get_string(assessment, "observed_financial_effect"),
            _get_string(capacity, "investor_implication"),
        ],
        unresolved_items=_get_string_list(assessment, "unresolved_questions") or _get_string_list(capacity, "unresolved_questions"),
        turning_points=turning_points,
    )


def _commentary_progression(theme: Dict[str, Any]) -> Dict[str, Any]:
    summary = _get_record(theme, "progression_summary")
    events = _get_record_list(theme, "commentary_events")
    return _make_progression_block(
        headline=_first_string(_get_string(theme, "theme_name"), _get_string(theme, "normalized_theme"), "Management commentary"),
        current_state=_first_string(_get_string(theme, "current_position"), _get_string(summary, "current_state"), "Unable To Verify"),
        what_changed=_first_string(_get_string(summary, "what_changed"), _get_string(theme, "current_emphasis")),
        why_it_changed=_first_string(_get_string(summary, "why_it_changed"), _get_string(theme, "investor_implication")),
        conviction_impact=_first_string(_get_string(theme, "conviction_impact"), "unclear"),
        latest_evidence=_get_string_list(summary, "latest_evidence") or [_get_string(theme, "current_emphasis"), _get_string(theme, "investor_implication")],
        unresolved_items=_get_string_list(summary, "unresolved_items") or _get_string_list(theme, "unresolved_questions"),
        turning_points=events,
    )


def _management_quality_progression(summary: Dict[str, Any]) -> Dict[str, Any]:
    turning_points = _get_record_list(summary, "major_turning_points")
    return _make_progression_block(
        headline="Management quality",
        current_state=_first_string(_get_string(summary, "overall_view"), _get_string(summary, "overall_direction"), "Unable To Verify"),
        what_changed=_first_string(_get_string_list(summary, "what_strengthened_conviction"), _get_string_list(summary, "what_weakened_conviction")),
        why_it_changed=_first_string(_get_string(summary, "investor_implication"), "The evidence base changed the quality assessment."),
        conviction_impact=_first_string(_get_string(summary, "overall_direction"), "unclear"),
        latest_evidence=[
            _get_string(summary, "strongest_dimension"),
            _get_string(summary, "weakest_dimension"),
            _get_string(summary, "investor_implication"),
        ],
        unresolved_items=_get_string_list(summary, "unresolved_questions") or _get_string_list(summary, "what_remains_unproven"),
        turning_points=turning_points,
    )


def _management_quality_signal_points(summary: Dict[str, Any], *, mode: str) -> List[str]:
    signals: List[str] = []
    for point in _get_record_list(summary, "major_turning_points"):
        direction = _normalize_sentence(_get_string(point, "direction"))
        if mode == "positive" and direction not in {"improving", "strengthening", "strengthened"}:
            continue
        if mode == "negative" and direction not in {"deteriorating", "weakened", "weakening", "mixed"}:
            continue
        period = _first_string(_get_string(point, "period"), _get_string(point, "latest_period"))
        dimension = _first_string(_get_string(point, "dimension"), _get_string(point, "label"), "management quality").replace("_", " ")
        summary_text = _clean_display_phrase(
            _first_string(_get_string(point, "summary"), _get_string(point, "why_it_matters"), _get_string(point, "description")),
            limit_words=18,
        )
        if not summary_text:
            continue
        if mode == "positive":
            signal = f"{period.upper()} {dimension} improved through {summary_text}" if period else f"{dimension} improved through {summary_text}"
        else:
            if direction == "mixed":
                signal = f"{period.upper()} {dimension} remained mixed around {summary_text}" if period else f"{dimension} remained mixed around {summary_text}"
            else:
                signal = f"{period.upper()} {dimension} deteriorated through {summary_text}" if period else f"{dimension} deteriorated through {summary_text}"
        signal = _clean_display_phrase(signal, limit_words=20)
        if signal:
            signals.append(signal)
    return _dedupe_similar_lines(signals)[:3]


def _capital_allocation_progression(source_bundle: Dict[str, Any]) -> Dict[str, Any]:
    outcomes = _source_payload(source_bundle, "capital_allocation_outcomes")
    allocations = _get_record_list(outcomes, "allocations")
    if allocations:
        allocation = allocations[-1]
        progression = _get_record(allocation, "progression_summary")
        return _make_progression_block(
            headline=_first_string(_get_string(allocation, "allocation_name"), _get_string(allocation, "normalized_name"), "Capital allocation"),
            current_state=_first_string(_get_string(allocation, "current_status"), _get_string(allocation, "outcome_status"), "Unable To Verify"),
            what_changed=_first_string(_get_string(allocation, "stated_rationale"), _get_string(progression, "what_changed"), _get_string(allocation, "allocation_name")),
            why_it_changed=_first_string(_get_string(allocation, "investor_implication"), _get_string(progression, "why_it_changed"), _get_string(allocation, "balance_sheet_outcome")),
            conviction_impact=_first_string(_get_string(progression, "conviction_impact"), _get_string(allocation, "outcome_status"), "unclear"),
            latest_evidence=[
                _get_string(allocation, "stated_rationale"),
                _get_string(allocation, "balance_sheet_outcome"),
                _get_string(allocation, "financial_evidence"),
                _get_string(allocation, "per_share_outcome"),
            ],
            unresolved_items=_get_string_list(allocation, "unresolved_questions"),
            turning_points=_get_record_list(allocation, "turning_points"),
        )
    ledger = _source_payload(source_bundle, "capital_allocation_roi_ledger")
    entries = _get_record_list(ledger, "entries")
    entry = entries[-1] if entries else {}
    return _make_progression_block(
        headline=_first_string(_get_string(entry, "capital_use"), "Capital allocation"),
        current_state=_first_string(_get_string(entry, "roi_measurability_status"), "Unable To Verify"),
        what_changed=_first_string(_get_string(entry, "capital_use"), _get_string(entry, "purpose")),
        why_it_changed=_first_string(_get_string(entry, "investor_interpretation"), "The use of capital became more visible."),
        conviction_impact="unclear",
        latest_evidence=[_get_string(entry, "investor_interpretation"), _get_string(entry, "roi_measurability_status")],
        unresolved_items=[_get_string(entry, "roi_measurability_status")],
        turning_points=[],
    )


def _risk_progression(source_bundle: Dict[str, Any]) -> Dict[str, Any]:
    evolution = _source_payload(source_bundle, "risk_evolution")
    risks = _get_record_list(evolution, "risks")
    risk = risks[-1] if risks else {}
    severity = _first_string(_get_string(risk, "latest_severity"), "unclear")
    mentions = _get_record_list(risk, "source_mentions")
    return _make_progression_block(
        headline=_first_string(_get_string(risk, "normalized_risk"), "Key risk"),
        current_state=severity,
        what_changed=_first_string(
            _get_string(risk, "what_changed"),
            _get_string(risk, "progression_summary"),
            _get_string(risk, "normalized_risk"),
            _first_string([_get_string(mention, "value") for mention in mentions]),
        ),
        why_it_changed=_first_string(
            _get_string(risk, "why_it_changed"),
            _get_string(risk, "investor_implication"),
            _first_string([_first_string([_get_string(mention, "short_excerpt"), _get_string(mention, "value"), _get_string(mention, "source_artifact")]) for mention in mentions]),
            _get_string(risk, "confidence"),
        ),
        conviction_impact="weakened" if severity in {"high", "severe"} else "unclear",
        latest_evidence=[
            _get_string(risk, "investor_implication"),
            _get_string(risk, "progression_summary"),
            _first_string([_first_string([_get_string(mention, "short_excerpt"), _get_string(mention, "value")]) for mention in mentions]),
            _first_string(_get_string_list(risk, "related_evidence_ids")),
        ],
        unresolved_items=[_first_string([_get_string(mention, "short_excerpt"), _get_string(mention, "value")]) for mention in mentions],
        turning_points=[],
    )


def _build_management_promises_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    commitments = _source_payload(source_bundle, "management_commitments")
    commitment_list = _get_record_list(commitments, "commitments")
    if not commitment_list:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available company memory does not yet document management commitments clearly enough to summarize them responsibly.",
            why="Commitment tracking matters because it gives investors a checkable record of what management said it would do.",
            limitation="The current source set does not preserve a clean commitment ledger.",
    )
    featured = _material_commitments(commitment_list, limit=4)
    progression = _commitment_progression(featured[0])
    commitment_references = [_commitment_reference_label(commitment) for commitment in featured[:3] if _commitment_reference_label(commitment)]
    later_checks = [_commitment_watch_item(commitment) for commitment in featured[:3]]
    later_checks = _clean_list(later_checks)[:3]
    active_commitments = [commitment for commitment in featured if _commitment_status_label(commitment).lower() in {"in progress", "delivered", "partially delivered"}]
    unresolved_commitments = [commitment for commitment in featured if _commitment_status_label(commitment).lower() in {"unable to verify", "announced", "delayed"}]
    status_fragments = []
    if any(_commitment_status_label(commitment).lower() == "in progress" for commitment in featured):
        status_fragments.append("one is in progress")
    if any(_commitment_status_label(commitment).lower() == "unable to verify" for commitment in featured):
        status_fragments.append("others remain unverified")
    if any(_commitment_status_label(commitment).lower() in {"delivered", "partially delivered"} for commitment in featured):
        status_fragments.append("some follow-through is visible")
    interpretation = _make_interpretation_from_progression(
        progression=progression,
        conclusion=(
            f"Management has promised {_join_human_list(commitment_references)}"
            + (f"; {', '.join(status_fragments)}." if status_fragments else ".")
            if commitment_references
            else "Management promises are visible, but credibility still depends on later execution."
        ),
        economic_mechanism="Promises matter because credibility compounds when later evidence shows management can turn stated intent into actual delivery.",
        what_to_watch=later_checks,
        thesis_impact=(
            "strengthens"
            if len(delivered := [item for item in commitment_list if str(item.get("status") or "").lower() in {"delivered", "partially delivered", "partially_delivered"}]) > len(delayed := [item for item in commitment_list if str(item.get("status") or "").lower() == "delayed"])
            else "weakens"
            if len(delayed) > len(delivered)
            else "neutral"
        ),
        confidence_level="medium",
    )
    commitment_highlights = [_commitment_summary(item, include_status=True) for item in featured[:4] if _commitment_summary(item, include_status=True)]
    if commitment_highlights:
        interpretation["what_changed"] = commitment_highlights[:4]
    if active_commitments:
        interpretation["positive_evidence"] = [_commitment_summary(item, include_status=True) for item in active_commitments[:3]]
    if unresolved_commitments:
        interpretation["negative_evidence"] = [_commitment_summary(item, include_status=True) for item in unresolved_commitments[:3]]
    return _draft(
        answer_status="supported" if len(featured) > 1 else "partially_supported",
        simple_answer=interpretation["conclusion"],
        why_it_matters="This matters because a commitment only becomes useful to investors when later evidence can show whether execution kept pace with the promise.",
        key_points=commitment_highlights[:4],
        detailed_explanation="The commitment ledger separates what management said from what later evidence shows. That is the core of progression thinking: a promise is not the same thing as delivery, and investors should not treat them as interchangeable.",
        evidence_status="partial",
        evidence_summary="Supported by the new commitment ledger and its linked follow-through evidence.",
        evidence_points=commitment_highlights[:3],
        uncertainty=_first_string(_get_string(featured[0], "expected_timeframe"), "Some commitments still lack a clean delivery window."),
        products_refs=[],
        business_journey_ref=None,
        progression=progression,
        interpretation=interpretation,
    )


def _build_past_claims_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    commitments = _get_record_list(_source_payload(source_bundle, "management_commitments"), "commitments")
    material_commitments = _material_commitments(commitments, limit=4)
    delivered = [item for item in material_commitments if str(item.get("status") or "").lower() in {"delivered", "partially delivered", "partially_delivered"}]
    delayed = [item for item in material_commitments if str(item.get("status") or "").lower() == "delayed"]
    unresolved = [item for item in material_commitments if str(item.get("status") or "").lower() in {"in progress", "unable to verify", "announced"}]
    if not commitments:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available company memory does not yet support a reliable promise-versus-delivery answer.",
            why="This matters because management quality is easier to judge by follow-through than by messaging alone.",
            limitation="The current source set does not provide a clean time-linked promise-and-outcome comparison.",
        )
    simple = (
        "A few commitments show follow-through, but the evidence still looks mixed and selective."
        if delivered or delayed
        else "The commitment ledger is visible, but follow-through is not yet strong enough to make a confident delivery claim."
    )
    progression = _commitment_progression(material_commitments[0])
    delivered_refs = [_commitment_reference_label(item) for item in delivered[:2] if _commitment_reference_label(item)]
    open_refs = [_commitment_reference_label(item) for item in unresolved[:2] if _commitment_reference_label(item)]
    delayed_refs = [_commitment_reference_label(item) for item in delayed[:2] if _commitment_reference_label(item)]
    conclusion_parts = []
    if delivered_refs and open_refs:
        conclusion_parts.append(f"Follow-through is mixed: {_join_human_list(delivered_refs)} shows progress while {_join_human_list(open_refs)} remains unresolved.")
    elif delivered_refs:
        conclusion_parts.append(f"Several commitments show follow-through, but the remaining record is still thin.")
    elif delayed_refs:
        conclusion_parts.append(f"Follow-through is still mixed because {_join_human_list(delayed_refs)} has slipped.")
    else:
        conclusion_parts.append("The commitment ledger is visible, but follow-through is not yet strong enough to make a confident delivery claim.")
    interpretation = _make_interpretation_from_progression(
        progression=progression,
        conclusion=" ".join(conclusion_parts),
        economic_mechanism="Past claims matter because management credibility rises only when later evidence keeps matching the original promise.",
        what_to_watch=[item for item in (_commitment_watch_item(commitment) for commitment in material_commitments[:3]) if item],
        thesis_impact=(
            "strengthens"
            if len(delivered) > len(delayed)
            else "weakens"
            if len(delayed) > len(delivered)
            else "neutral"
        ),
        confidence_level="medium",
    )
    commitment_highlights = [_commitment_summary(item, include_status=True) for item in material_commitments[:4] if _commitment_summary(item, include_status=True)]
    if commitment_highlights:
        interpretation["what_changed"] = commitment_highlights[:4]
    if delivered:
        interpretation["positive_evidence"] = [_commitment_summary(item, include_status=True) for item in delivered[:3]]
    if delayed or unresolved:
        interpretation["negative_evidence"] = [_commitment_summary(item, include_status=True) for item in (delayed + unresolved)[:3]]
    return _draft(
        answer_status="partially_supported",
        simple_answer=interpretation["conclusion"],
        why_it_matters="This matters because investors should care less about the original promise and more about whether later evidence shows that execution kept pace.",
        key_points=commitment_highlights[:4],
        detailed_explanation=simple + " The right comparison is not quote versus quote; it is promise versus later evidence. Where the evidence shows delivery, conviction can rise. Where the evidence shows delay or no follow-through, conviction should fall or stay cautious.",
        evidence_status="partial" if delivered or delayed else "missing",
        evidence_summary="Supported by the commitment ledger and its time-linked follow-through evidence.",
        evidence_points=commitment_highlights[:3],
        uncertainty="A few commitments still lack later evidence, so some remain unable to verify.",
        products_refs=[],
        business_journey_ref=None,
        progression=progression,
        interpretation=interpretation,
    )


def _build_projects_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    registry = _source_payload(source_bundle, "projects_registry")
    projects = _get_record_list(registry, "projects")
    if not projects:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available company memory does not yet support a reliable project tracker.",
            why="Projects matter because they show where management is trying to turn ambition into execution.",
            limitation="The current source set does not include enough project evidence to summarize underway initiatives responsibly.",
        )
    featured = projects[:4]
    progression = _project_progression(featured[0])
    return _draft(
        answer_status="partially_supported",
        simple_answer=first_available_text(
            _get_string(featured[0], "objective"),
            _get_string(featured[0], "business_rationale"),
            "The company is pursuing several visible projects, but the economic payoff is still unevenly proven.",
        ),
        why_it_matters="This matters because projects reveal whether management is building real capability, not just discussing growth in the abstract.",
        key_points=[
            _first_string(_get_string(item, "objective"), _get_string(item, "normalized_name"), _get_string(item, "project_name")) for item in featured
        ],
        detailed_explanation="Projects are the bridge between narrative and execution. The best use of this view is to see whether a project moved from announcement to construction, from construction to commissioning, and finally from commissioning to observable business impact.",
        evidence_status="partial",
        evidence_summary="Supported by the project registry and its assessment layer.",
        evidence_points=[
            _get_string(featured[0], "execution_summary"),
            _get_string(featured[0], "observed_business_effect"),
            _get_string(featured[0], "observed_financial_effect"),
        ],
        uncertainty="Many projects are visible before their financial effects are.",
        products_refs=[],
        business_journey_ref=None,
        progression=progression,
    )


def _build_capacity_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    registry = _source_payload(source_bundle, "capacity_registry")
    capacity_items = _get_record_list(registry, "capacity_items")
    if not capacity_items:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available company memory does not yet support a reliable capacity tracker.",
            why="Capacity matters because investors want to know whether new assets are actually changing what the company can do.",
            limitation="The current source set does not include enough capacity evidence to summarize utilization responsibly.",
        )
    featured = capacity_items[:4]
    progression = _capacity_progression(featured[0])
    current_status = first_available_text(
        _get_string(featured[0], "current_status"),
        _get_string(featured[0], "utilization_measure"),
        "Capacity is being added, but utilisation and economic payoff are still only partly visible.",
    )
    investor_conclusion = first_available_text(
        _get_string(featured[0], "investor_implication"),
        "Capacity is being added, but utilisation and economic payoff remain unproven.",
    )
    what_changed = _clean_list([
        _get_string(featured[0], "capacity_name"),
        _get_string(featured[0], "capacity_type"),
        _get_string(featured[0], "investor_implication"),
    ])[:3]
    unresolved = _clean_list(
        _get_string_list(featured[0], "unresolved_questions") + [current_status]
    )[:3]
    interpretation = build_interpretation_contract(
        conclusion=investor_conclusion,
        what_changed=what_changed or [current_status],
        why_it_matters="Installed capacity only matters if it gets used enough to improve delivery capability or spread fixed costs.",
        economic_mechanism="New assets create value only when they become usable, utilized, and economically relevant.",
        thesis_impact="neutral",
        positive_evidence=_clean_list([
            _get_string(featured[0], "current_status"),
            _get_string(featured[0], "utilization_measure"),
            _get_string(featured[0], "observed_business_effect"),
        ])[:3],
        negative_evidence=unresolved,
        unresolved=unresolved,
        what_to_watch=_clean_list([
            _get_string(featured[0], "utilization_measure"),
            _get_string(featured[0], "observed_business_effect"),
            _get_string(featured[0], "observed_financial_effect"),
        ])[:3],
        confidence={"level": "medium", "basis": ["Supported by the capacity registry and utilization assessment layer."], "limitations": ["The available evidence does not clearly show forward demand or order-book support."]},
    )
    return _draft(
        answer_status="partially_supported",
        simple_answer=interpretation["conclusion"],
        why_it_matters=interpretation["why_it_matters"],
        key_points=[
            _first_string(_get_string(item, "capacity_name"), _get_string(item, "normalized_name"), _get_string(item, "capacity_type")) for item in featured
        ],
        detailed_explanation="A capacity answer should show whether the asset moved from planned to installed, from installed to commissioned, and from commissioned to meaningfully utilized. It should not pretend that every new asset automatically created economic value.",
        evidence_status="partial",
        evidence_summary="Supported by the capacity registry and utilization assessment layer.",
        evidence_points=[
            _get_string(featured[0], "current_status"),
            _get_string(featured[0], "utilization_measure"),
            _get_string(featured[0], "investor_implication"),
        ],
        uncertainty="Utilization and downstream financial effect are still thinly disclosed.",
        products_refs=[],
        business_journey_ref=None,
        progression=progression,
        interpretation=interpretation,
    )


def _build_commentary_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    themes = _source_payload(source_bundle, "commentary_themes")
    commentary_themes = _get_record_list(themes, "themes")
    if not commentary_themes:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available company memory does not yet support a reliable commentary progression answer.",
            why="Commentary matters because management language often changes before the underlying operating effect is obvious.",
            limitation="The current source set does not include enough commentary evidence to trace evolving emphasis responsibly.",
        )
    featured = commentary_themes[:4]
    progression = _commentary_progression(featured[0])
    current_emphasis = first_available_text(
        _get_string(featured[0], "current_emphasis"),
        _get_string(featured[0], "investor_implication"),
        "Management commentary shows what management is emphasizing right now, but the operating payoff is still only partly visible.",
    )
    investor_conclusion = first_available_text(
        _get_string(featured[0], "investor_implication"),
        "Management is emphasizing technology upgrades, but the business payoff is still unproven.",
    )
    unresolved = _clean_list(
        _get_string_list(featured[0], "unresolved_questions") + [current_emphasis]
    )[:3]
    interpretation = build_interpretation_contract(
        conclusion=investor_conclusion,
        what_changed=_clean_list([
            _get_string(featured[0], "theme_name"),
            _get_string(featured[0], "current_emphasis"),
            _get_string(featured[0], "investor_implication"),
        ])[:3],
        why_it_matters="Changing commentary can reveal where management is leaning before the numbers fully catch up.",
        economic_mechanism="Commentary matters when a change in emphasis anticipates a change in execution, capital deployment, or operating capability.",
        thesis_impact="neutral",
        positive_evidence=_clean_list([
            _get_string(featured[0], "what_changed"),
            _get_string(featured[0], "why_it_changed"),
            _get_string(featured[0], "investor_implication"),
        ])[:3],
        negative_evidence=unresolved,
        unresolved=unresolved,
        what_to_watch=_clean_list([
            _get_string(featured[0], "what_changed"),
            _get_string(featured[0], "why_it_changed"),
            _get_string(featured[0], "investor_implication"),
        ])[:3],
        confidence={"level": "medium", "basis": ["Supported by the commentary theme registry and its progression summary."], "limitations": ["Some commentary themes are newly introduced and still lack long follow-through."]},
    )
    return _draft(
        answer_status="partially_supported",
        simple_answer=interpretation["conclusion"],
        why_it_matters=interpretation["why_it_matters"],
        key_points=[
            _first_string(_get_string(item, "theme_name"), _get_string(item, "normalized_theme"), _get_string(item, "current_emphasis")) for item in featured
        ],
        detailed_explanation="Commentary is most useful when read as a progression stream: what changed, why it changed, and whether the change should alter conviction.",
        evidence_status="partial",
        evidence_summary="Supported by the commentary theme registry and its progression summary.",
        evidence_points=[
            _get_string(featured[0], "what_changed"),
            _get_string(featured[0], "why_it_changed"),
            _get_string(featured[0], "investor_implication"),
        ],
        uncertainty="Some commentary themes are newly introduced and still lack long follow-through.",
        products_refs=[],
        business_journey_ref=None,
        progression=progression,
        interpretation=interpretation,
    )


def _build_management_quality_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    summary = _source_payload(source_bundle, "management_quality_summary")
    if not summary:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available company memory does not yet support a reliable management-quality assessment.",
            why="Management quality matters because execution discipline shapes whether good strategy actually compounds value.",
            limitation="The current source set does not yet include a strong enough management-quality summary.",
        )
    progression = _management_quality_progression(summary)
    strongest = _get_string(summary, "strongest_dimension")
    weakest = _get_string(summary, "weakest_dimension")
    turning_points = _get_record_list(summary, "major_turning_points")
    return _draft(
        answer_status="supported",
        simple_answer=first_available_text(
            _get_string(summary, "investor_implication"),
            _get_string(summary, "overall_view"),
            "Management quality looks like a real strength, but it is still best read through execution evidence rather than slogans.",
        ),
        why_it_matters="This matters because management quality is not a vibe; it is the pattern of execution, discipline, and how convincingly the evidence changes over time.",
        key_points=[
            f"Strongest dimension: {strongest}." if strongest else "",
            f"Weakest dimension: {weakest}." if weakest else "",
            _first_string(_get_string(summary, "overall_direction"), _get_string(summary, "overall_view")),
            _first_string(_get_string_list(summary, "what_strengthened_conviction"), _get_string_list(summary, "what_weakened_conviction")),
        ],
        detailed_explanation="The management-quality view should stay anchored to turning points, not generic praise. The most useful question is whether execution evidence is broadening, whether weaknesses are narrowing, and whether the remaining gaps are material enough to keep conviction guarded.",
        evidence_status="supported",
        evidence_summary="Supported by the dedicated management-quality summary and its turning points.",
        evidence_points=[
            _get_string(summary, "overall_view"),
            _get_string(summary, "overall_direction"),
            _get_string(summary, "investor_implication"),
        ],
        uncertainty=_first_string(_get_string_list(summary, "unresolved_questions"), _get_string_list(summary, "what_remains_unproven"), "Some dimensions remain unproven."),
        products_refs=[],
        business_journey_ref=None,
        progression=progression,
    )


def _build_capital_allocation_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    outcomes = _source_payload(source_bundle, "capital_allocation_outcomes")
    allocations = _get_record_list(outcomes, "allocations")
    if allocations:
        allocation = allocations[-1]
        progression = _capital_allocation_progression(source_bundle)
        deployment = first_available_text(
            _get_string(allocation, "allocation_name"),
            _get_string(allocation, "normalized_name"),
            _get_string(allocation, "allocation_category"),
            "Capital deployment",
        )
        outcome = first_available_text(
            _get_string(allocation, "balance_sheet_outcome"),
            _get_string(allocation, "investor_implication"),
            _get_string(allocation, "balance_sheet_outcome"),
            "The return trail is still only partly visible.",
        ).rstrip(" .")
        per_share = first_available_text(
            _get_string(allocation, "per_share_outcome"),
            "Per-share effects remain indirect and are not yet cleanly attributable.",
        ).rstrip(" .")
        unresolved = _clean_list(
            _get_string_list(allocation, "unresolved_questions") + [per_share]
        )[:3]
        interpretation = build_interpretation_contract(
            conclusion=f"Capital was deployed into {deployment.lower()}, but the return trail is still only partly visible.",
            what_changed=_clean_list([deployment, _get_string(allocation, "stated_rationale"), outcome])[:3],
            why_it_matters="Investors need to separate deployment from return: spending money is not the same thing as creating per-share value.",
            economic_mechanism="Capital allocation matters only when the deployed cash improves capacity, margins, or shareholder economics enough to beat the opportunity cost.",
            thesis_impact="neutral",
            positive_evidence=_clean_list([
                f"Deployment: {deployment}.",
                f"Observed outcome: {outcome}.",
                _get_string(allocation, "investor_implication"),
            ])[:3],
            negative_evidence=unresolved,
            unresolved=unresolved,
            what_to_watch=_clean_list([
                "Utilization of the new capacity",
                "Incremental margins or cash-flow evidence",
                "Per-share earnings or cash outcome from the deployment",
            ])[:3],
            confidence={"level": "medium", "basis": ["Supported by the capital-allocation outcome ledger and its progression summary."], "limitations": ["Owner earnings are estimated, but maintenance and growth capex are not separated."]},
        )
        return _draft(
            answer_status="supported" if _get_string(allocation, "outcome_status") else "partially_supported",
            simple_answer=interpretation["conclusion"],
            why_it_matters=interpretation["why_it_matters"],
            key_points=[
                f"Deployment: {deployment}.",
                f"Outcome: {outcome}.",
                f"Per-share effect: {per_share}.",
                f"Unresolved: {_first_string(_get_string_list(allocation, 'unresolved_questions'))}.",
            ],
            detailed_explanation="The useful capital-allocation question is not only where money went, but what changed afterward: did the business get stronger, did returns become visible, and did per-share economics improve in a way investors can trust?",
            evidence_status="partial",
            evidence_summary="Supported by the capital-allocation outcome ledger and its progression summary.",
            evidence_points=[
                _get_string(allocation, "operating_outcome"),
                _get_string(allocation, "financial_outcome"),
                _get_string(allocation, "per_share_outcome"),
            ],
            uncertainty="Some allocations still do not yet have a clean return trail.",
            products_refs=[],
            business_journey_ref=None,
            progression=progression,
            interpretation=interpretation,
        )
    ledger = _source_payload(source_bundle, "capital_allocation_roi_ledger")
    entries = _get_record_list(ledger, "entries")
    if not entries:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    first_entry = entries[-1]
    progression = _capital_allocation_progression(source_bundle)
    deployment = first_available_text(
        _get_string(first_entry, "capital_use"),
        _get_string(first_entry, "purpose"),
        _get_string(first_entry, "investor_interpretation"),
        "Capital deployment",
    )
    outcome = first_available_text(
        _get_string(first_entry, "balance_sheet_outcome"),
        _get_string(first_entry, "investor_interpretation"),
        "The return trail is still only partly visible.",
    ).rstrip(" .")
    per_share = first_available_text(
        _get_string(first_entry, "per_share_outcome"),
        "Per-share effects remain indirect and are not yet cleanly attributable.",
    ).rstrip(" .")
    unresolved = _clean_list(
        _get_string_list(first_entry, "unresolved_questions") + [per_share]
    )[:3]
    interpretation = build_interpretation_contract(
        conclusion=f"Capital was deployed into {deployment.lower()}, but the return trail is still only partly visible.",
        what_changed=_clean_list([deployment, _get_string(first_entry, "capital_use"), outcome])[:3],
        why_it_matters="Investors need to separate deployment from return: spending money is not the same thing as creating per-share value.",
        economic_mechanism="Capital allocation matters only when the deployed cash improves capacity, margins, or shareholder economics enough to beat the opportunity cost.",
        thesis_impact="neutral",
        positive_evidence=_clean_list([
            f"Deployment: {deployment}.",
            f"Observed outcome: {outcome}.",
            _get_string(first_entry, "investor_interpretation"),
        ])[:3],
        negative_evidence=unresolved,
        unresolved=unresolved,
        what_to_watch=_clean_list([
            "Utilization of the new capacity",
            "Incremental margins or cash-flow evidence",
            "Per-share earnings or cash outcome from the deployment",
        ])[:3],
        confidence={"level": "medium", "basis": ["Supported by the capital-allocation ROI ledger and current financial truth evidence."], "limitations": ["Maintenance versus growth capex is not cleanly separated."]},
    )
    return _draft(
        answer_status="partially_supported",
        simple_answer=interpretation["conclusion"],
        why_it_matters=interpretation["why_it_matters"],
        key_points=[
            f"Deployment: {deployment}.",
            f"Outcome: {outcome}.",
            f"Per-share effect: {per_share}.",
            f"Unresolved: {_first_string(_get_string_list(first_entry, 'unresolved_questions'))}.",
        ],
        detailed_explanation="The current evidence is stronger on where capital seems to be going than on the eventual return on that capital. That supports a useful directional answer on allocation priorities, while still keeping the ROI question open.",
        evidence_status="partial",
        evidence_summary="Partially supported because capital uses are visible, but later return-on-capital evidence is still incomplete.",
        evidence_points=[
            _get_string(first_entry, "investor_interpretation"),
            _first_string(_get_string_list(_get_record(_source_payload(source_bundle, "committee_synthesis"), "financial_committee_view"), "investor_questions_from_financials")),
        ],
        uncertainty="The use of capital is clearer than the eventual return on that capital.",
        products_refs=[],
        business_journey_ref=None,
        progression=progression,
        interpretation=interpretation,
    )


def _build_incentives_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    summary = _source_payload(source_bundle, "management_quality_summary")
    if summary:
        progression = _management_quality_progression(summary)
        positive_signals = _management_quality_signal_points(summary, mode="positive")
        negative_signals = _management_quality_signal_points(summary, mode="negative")
        unresolved_signals = _dedupe_similar_lines(
            _clean_list(_get_string_list(summary, "unresolved_questions") or _get_string_list(summary, "what_remains_unproven"))
        )[:3]
        key_points = _dedupe_similar_lines(positive_signals + negative_signals + unresolved_signals)[:4]
        return _draft(
            answer_status="supported",
            simple_answer=first_available_text(
                _get_string(summary, "investor_implication"),
                "The incentive picture should be read through execution discipline, not just shareholding structure.",
            ),
            why_it_matters="This matters because even a good business can compound poorly if the people allocating capital are not well aligned with outside shareholders.",
            key_points=key_points or [
                _get_string(summary, "strongest_dimension"),
                _get_string(summary, "weakest_dimension"),
                _get_string(summary, "overall_view"),
                _get_string(summary, "investor_implication"),
            ],
            detailed_explanation="This question is now anchored in the management-quality summary rather than a generic governance remark. The point is to show what in the evidence strengthens or weakens conviction about execution discipline, alignment, and transparency.",
            evidence_status="supported",
            evidence_summary="Supported by the dedicated management-quality summary.",
            evidence_points=(positive_signals[:2] + negative_signals[:1] + unresolved_signals[:1])[:3] or [
                _get_string(summary, "overall_view"),
                _get_string(summary, "investor_implication"),
            ],
            uncertainty=_first_string(_get_string_list(summary, "unresolved_questions"), _get_string_list(summary, "what_remains_unproven"), "Some management-quality dimensions remain unproven."),
            products_refs=[],
            business_journey_ref=None,
            progression=progression,
            interpretation=_make_interpretation_from_progression(
                progression=progression,
                conclusion=_first_string(_get_string(summary, "investor_implication"), "Management quality matters because execution and capital discipline shape per-share outcomes."),
                economic_mechanism="Management quality matters because execution, capital allocation, candor, and risk handling determine whether the company converts plans into durable per-share value.",
                thesis_impact=(
                    "strengthens"
                    if positive_signals and len(positive_signals) > len(negative_signals)
                    else "weakens"
                    if negative_signals
                    else "neutral"
                ),
                confidence_level=_first_string(_get_string(summary, "evidence_confidence"), "medium"),
                positive_evidence=positive_signals,
                negative_evidence=negative_signals,
                unresolved=unresolved_signals,
                what_to_watch=(negative_signals[:2] + unresolved_signals[:1] + positive_signals[:1])[:3],
            ),
        )
    analysis = _source_payload(source_bundle, "munger_analysis")
    signals = _clean_list(
        _get_string_list(analysis, "key_findings")[:2] + _get_string_list(analysis, "red_flags")[:2]
    )[:4]
    if not signals:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    return _draft(
        answer_status="partially_supported",
        simple_answer="The main incentive questions here are around capital-raising discipline, related-party exposure, and how transparent management is about the use of shareholder capital.",
        why_it_matters="This matters because even a good business can compound poorly if the people allocating capital are not well aligned with outside shareholders.",
        key_points=signals,
        detailed_explanation="The current evidence highlights the areas where incentives deserve monitoring more clearly than it delivers a final governance verdict. That is still useful, because investor-grade diligence often starts with the right monitoring questions before it reaches a definitive conclusion.",
        evidence_status="partial",
        evidence_summary="Partially supported because the current evidence highlights incentive questions more clearly than it resolves them.",
        evidence_points=signals[:3],
        uncertainty="The source set identifies incentive questions more clearly than it answers them.",
        products_refs=[],
        business_journey_ref=None,
        progression=None,
    )


def _build_ask_ir_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    committee = _source_payload(source_bundle, "committee_synthesis")
    questions = _clean_list(
        _question_texts(_get_record_list(committee, "investigation_questions"))
        + _get_string_list(_get_record(committee, "financial_committee_view"), "investor_questions_from_financials")
    )[:4]
    if not questions:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    return _draft(
        answer_status="supported",
        simple_answer="The best IR questions are the ones that clarify capex split, working-capital drivers, share-count comparability, and the basis of reported financials.",
        why_it_matters="This matters because these questions target the exact evidence gaps that currently limit confidence.",
        key_points=questions,
        detailed_explanation="A good IR question is specific enough to resolve a real limitation, not broad enough to invite generic reassurance. The current evidence already shows which unknowns matter most, so the best follow-up questions are the ones that turn those uncertainty points into direct management clarification requests.",
        evidence_status="direct",
        evidence_summary="Supported by committee follow-up questions already present in the current source set.",
        evidence_points=questions[:3],
        uncertainty="The current evidence is strong enough to suggest the questions, but not always to answer them.",
        products_refs=[],
        business_journey_ref=None,
        progression=None,
    )


def _build_lens_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any], lens_key: str, why: str) -> Dict[str, Any]:
    analysis = _source_payload(source_bundle, lens_key)
    committee = _source_payload(source_bundle, "committee_synthesis")
    if not analysis:
        return _build_unavailable_answer(
            question,
            "The required investor-lens evidence is not available in the current source set.",
            "This answer depends on the saved investor-lens analysis for this doctrine. Without it, the right response is to leave the lens unavailable rather than invent it.",
            "The investor-lens analysis for this question is missing.",
        )
    assessment = _get_record(analysis, "assessment")
    direct = _first_string(list(str(value) for value in assessment.values() if isinstance(value, str)), [_get_string(_get_record(committee, "overall_committee_view"), "summary")])
    findings = _get_string_list(analysis, "key_findings")
    red_flags = _get_string_list(analysis, "red_flags")
    uncertainties = _get_string_list(analysis, "open_uncertainties")
    if not direct:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    return _draft(
        answer_status="supported",
        simple_answer=direct,
        why_it_matters=why,
        key_points=_clean_list([findings[0] if findings else "", findings[1] if len(findings) > 1 else "", red_flags[0] if red_flags else "", uncertainties[0] if uncertainties else ""])[:4],
        detailed_explanation=" ".join(_clean_list([direct] + findings[:2] + red_flags[:1] + uncertainties[:1])),
        evidence_status="derived",
        evidence_summary="Supported by the relevant investor lens and cross-checked against the committee synthesis where useful.",
        evidence_points=_clean_list(findings[:2] + red_flags[:1]),
        uncertainty=(uncertainties[0] if uncertainties else "This lens remains limited by the available evidence set."),
        products_refs=[],
        business_journey_ref=None,
    )


def _build_buffett_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    analysis = _source_payload(source_bundle, "buffett_analysis")
    committee = _source_payload(source_bundle, "committee_synthesis")
    if not analysis:
        return _build_unavailable_answer(
            question,
            "The required Buffett-style evidence is not available in the current source set.",
            "This answer depends on the saved Buffett-style analysis. Without it, the answer should stay unavailable rather than inferred.",
            "The Buffett-style analysis is missing.",
        )
    findings = [_clean_display_phrase(item, limit_words=18) for item in _clean_list(_get_string_list(analysis, "key_findings"))]
    red_flags = [_clean_display_phrase(item, limit_words=18) for item in _clean_list(_get_string_list(analysis, "red_flags"))]
    uncertainties = [_clean_display_phrase(item, limit_words=18) for item in _clean_list(_get_string_list(analysis, "open_uncertainties"))]
    assessment = _get_record(analysis, "assessment")
    concise_summary = _first_string(
        _get_string(assessment, "overall_view"),
        "Buffett would like the specialised business and capability buildout, but he would stay cautious until owner earnings, working-capital conversion, and capital-allocation returns are cleaner.",
    )
    if not concise_summary:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    cleaned_findings = [_strip_backend_phrasing(item) for item in findings if _strip_backend_phrasing(item)]
    cleaned_red_flags = [_strip_backend_phrasing(item) for item in red_flags if _strip_backend_phrasing(item)]
    cleaned_uncertainties = [_strip_backend_phrasing(item) for item in uncertainties if _strip_backend_phrasing(item)]
    if not concise_summary:
        concise_summary = "Buffett would focus on whether the business can compound owner earnings and per-share value."
    sections = [
        {
            "title": "What he may like",
            "points": _clean_list([cleaned_findings[0] if cleaned_findings else "", cleaned_findings[1] if len(cleaned_findings) > 1 else ""])[:2],
        },
        {
            "title": "What he would question",
            "points": _clean_list([cleaned_red_flags[0] if cleaned_red_flags else "", cleaned_red_flags[1] if len(cleaned_red_flags) > 1 else ""])[:2],
        },
        {
            "title": "What remains unproven",
            "points": _clean_list([cleaned_uncertainties[0] if cleaned_uncertainties else "", _first_string(_get_string_list(_get_record(committee, "financial_committee_view"), "investor_questions_from_financials"))])[:2],
        },
    ]
    sections = [section for section in sections if section["points"]]
    interpretation = build_interpretation_contract(
        conclusion=_clean_display_phrase(concise_summary, limit_words=22) or concise_summary,
        what_changed=_clean_list([findings[0] if findings else "", red_flags[0] if red_flags else "", uncertainties[0] if uncertainties else ""])[:2],
        why_it_matters="Buffett would care most about whether the business can turn capability and capital into durable per-share compounding.",
        economic_mechanism="The Buffett lens is about whether capital allocation, moat durability, and owner earnings compound per-share value instead of merely expanding activity.",
        thesis_impact="neutral",
        positive_evidence=_clean_list([cleaned_findings[0] if cleaned_findings else "", cleaned_findings[1] if len(cleaned_findings) > 1 else "", _strip_backend_phrasing(_get_string(_get_record(committee, "financial_committee_view"), "investor_implication"))])[:3],
        negative_evidence=_clean_list([cleaned_red_flags[0] if cleaned_red_flags else "", cleaned_red_flags[1] if len(cleaned_red_flags) > 1 else "", cleaned_uncertainties[0] if cleaned_uncertainties else ""])[:3],
        unresolved=_clean_list([cleaned_uncertainties[0] if cleaned_uncertainties else "", _first_string(_get_string_list(_get_record(committee, "financial_committee_view"), "investor_questions_from_financials"))])[:3],
        what_to_watch=_clean_list([
            "Owner earnings versus reported profit",
            "Working-capital conversion",
            "Returns on incremental capital",
            "Per-share cash generation",
        ])[:3],
        confidence={"level": "high", "basis": ["Supported by the Buffett-style investor lens and cross-checked against committee-level financial follow-up where useful."], "limitations": ["Owner earnings are estimated, but maintenance and growth capex are not separated."]},
    )
    return _draft(
        answer_status="supported",
        simple_answer=interpretation["conclusion"],
        why_it_matters=interpretation["why_it_matters"],
        key_points=_clean_list([
            cleaned_findings[0] if cleaned_findings else "",
            cleaned_red_flags[0] if cleaned_red_flags else "",
            cleaned_uncertainties[0] if cleaned_uncertainties else "",
        ])[:3],
        detailed_explanation="Buffett would focus less on narrative momentum and more on whether the business can repeatedly convert capability into owner earnings and per-share compounding.",
        evidence_status="derived",
        evidence_summary="Supported by the Buffett-style investor lens and cross-checked against committee-level financial follow-up where useful.",
        evidence_points=_clean_list(cleaned_findings[:2] + cleaned_red_flags[:1])[:3],
        uncertainty=cleaned_uncertainties[0] if cleaned_uncertainties else "This answer remains limited by owner-economics precision and capital-allocation follow-through.",
        products_refs=[],
        business_journey_ref=None,
        structured_sections=sections,
        interpretation=interpretation,
    )


def _build_break_thesis_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    risks = [_clean_display_phrase(item, limit_words=18) for item in _risk_texts(source_bundle)[:4]]
    if not risks:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    risks = [item for item in risks if _normalize_sentence(item) != _normalize_sentence("this remains a central caution.")]
    progression = _risk_progression(source_bundle)
    watch_items = _clean_list(risks[:3])
    interpretation = build_interpretation_contract(
        conclusion="The thesis would be pressured most by severe working-capital strain, customer concentration, weak cash conversion, or capital deployment that does not earn back attractive returns.",
        what_changed=watch_items,
        why_it_matters="Break points matter because they identify the few things that would actually damage the business case rather than ordinary volatility.",
        economic_mechanism="A thesis breaks when cash gets trapped, demand becomes too concentrated, or capital spending fails to create durable economic return.",
        thesis_impact="weakens",
        positive_evidence=watch_items,
        negative_evidence=_clean_list([
            _get_string(progression, "current_state"),
            _first_string(_get_string_list(progression, "unresolved_items")),
        ])[:2],
        unresolved=_clean_list([
            _get_string(progression, "current_state"),
            _first_string(_get_string_list(progression, "unresolved_items")),
        ])[:2],
        what_to_watch=_clean_list([
            "Receivable days",
            "Inventory days",
            "Cash conversion cycle",
            "CFO/PAT conversion",
            "Customer concentration and collection commentary",
            "Capital efficiency on future deployments",
        ])[:3],
        confidence={"level": "high", "basis": ["Supported by committee and investor-panel risk outputs, with timeline-aware risk progression now preserved."], "limitations": [_first_string(_get_string_list(_source_payload(source_bundle, "working_capital_quality_drilldown"), "cash_strain_risk"))]},
    )
    return _draft(
        answer_status="supported",
        simple_answer=interpretation["conclusion"],
        why_it_matters=interpretation["why_it_matters"],
        key_points=risks,
        detailed_explanation="The current evidence is strongest on risk flags rather than full scenario analysis. Even so, it clearly points to working-capital stress, dependence on a narrow customer set, and uncertainty around capital efficiency as the main ways the business case could deteriorate.",
        evidence_status="derived",
        evidence_summary="Supported by committee and investor-panel risk outputs, with timeline-aware risk progression now preserved.",
        evidence_points=risks[:3],
        uncertainty="Some risks are directional because the source set is stronger on flags than on quantified downside scenarios.",
        products_refs=[],
        business_journey_ref=None,
        progression=progression,
        interpretation=interpretation,
    )


def _build_missing_disclosure_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    committee = _source_payload(source_bundle, "committee_synthesis")
    truth = _source_payload(source_bundle, "financial_truth_pack")
    missing = _clean_list(
        _get_string_list(_get_record(committee, "financial_committee_view"), "missing_financial_data")
        + _get_string_list(truth, "precision_limits")
    )[:4]
    if not missing:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    return _draft(
        answer_status="supported",
        simple_answer="The most important missing disclosures are the maintenance-versus-growth capex split, clean share-count comparability, and a clearer basis for financial comparison.",
        why_it_matters="This matters because these gaps limit how confidently profit, owner earnings, and per-share progress can be interpreted.",
        key_points=missing,
        detailed_explanation="Missing disclosure matters most when it changes judgment, not when it merely leaves trivia unanswered. Here, the most important gaps affect owner-earnings precision, per-share comparability, and the consistency of current financial interpretation.",
        evidence_status="direct",
        evidence_summary="Supported by financial limitation fields and committee follow-up gaps already present in the source set.",
        evidence_points=missing[:3],
        uncertainty="These are the clearest documented disclosure gaps in the current evidence set.",
        products_refs=[],
        business_journey_ref=None,
    )


def _build_change_view_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    committee = _source_payload(source_bundle, "committee_synthesis")
    questions = _question_texts(_get_record_list(committee, "investigation_questions"))[:4]
    if not questions:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    return _draft(
        answer_status="partially_supported",
        simple_answer="The view would change most if the company provided cleaner evidence on capex split, working-capital drivers, share-count comparability, and reporting basis.",
        why_it_matters="This matters because better evidence should change conviction only when it resolves a genuinely important unknown.",
        key_points=questions,
        detailed_explanation="The current evidence is already enough to identify the pressure points. What would change the view is not more narrative, but clearer evidence on the specific issues that currently prevent a stronger conclusion.",
        evidence_status="partial",
        evidence_summary="Partially supported because the source set identifies the key evidence gaps clearly, even if it cannot yet resolve them.",
        evidence_points=questions[:3],
        uncertainty="The current evidence identifies the decision points more clearly than it resolves them.",
        products_refs=[],
        business_journey_ref=None,
    )


def _build_needs_clarification_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    committee = _source_payload(source_bundle, "committee_synthesis")
    questions = _clean_list(
        _question_texts(_get_record_list(committee, "investigation_questions"))
        + _get_string_list(_get_record(committee, "financial_committee_view"), "investor_questions_from_financials")
    )[:4]
    if not questions:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    return _draft(
        answer_status="supported",
        simple_answer="Management most needs to clarify capex classification, working-capital drivers, share-count comparability, and how to interpret the reported basis consistently.",
        why_it_matters="This matters because these are the points where missing context can change whether current numbers look strong or only superficially strong.",
        key_points=questions,
        detailed_explanation="Clarification questions should target the few issues that most affect interpretation. The current source set makes those issues visible: capex classification, working-capital explanation, share-count comparability, and reporting-basis consistency.",
        evidence_status="direct",
        evidence_summary="Supported by committee follow-up questions and financial limitation signals already present in the source set.",
        evidence_points=questions[:3],
        uncertainty="This answer identifies follow-up areas, not management intent.",
        products_refs=[],
        business_journey_ref=None,
    )


def _build_unresolved_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    committee = _source_payload(source_bundle, "committee_synthesis")
    buffett = _source_payload(source_bundle, "buffett_analysis")
    unresolved = _clean_list(
        _unknown_texts(_get_record_list(committee, "critical_unknowns"))
        + _get_string_list(buffett, "open_uncertainties")
    )[:4]
    if not unresolved:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    return _draft(
        answer_status="supported",
        simple_answer="What remains unresolved is mostly about owner-economics precision, customer concentration, share-count comparability, and why working capital is so demanding.",
        why_it_matters="This matters because early conviction is most dangerous when the unresolved questions are hidden rather than named directly.",
        key_points=unresolved,
        detailed_explanation="The current evidence does not fail because it says nothing. It fails because a few high-value questions remain open. Those open questions cluster around owner-economics precision, the real drivers of cash conversion, and how confidently current shareholder-level economics can be compared over time.",
        evidence_status="derived",
        evidence_summary="Supported by committee unknowns and investor-panel uncertainties.",
        evidence_points=unresolved[:3],
        uncertainty="These unresolved points come directly from the current evidence set.",
        products_refs=[],
        business_journey_ref=None,
    )


def _build_generic_not_supported_answer(
    source_bundle: Dict[str, Any],
    *,
    business_journey_payload: Dict[str, Any],
    products_services_payload: Dict[str, Any],
    question: Dict[str, Any],
    direct_answer: Optional[str] = None,
    why: Optional[str] = None,
    limitation: Optional[str] = None,
) -> Dict[str, Any]:
    return _draft(
        answer_status="not_supported",
        simple_answer=direct_answer or "The available company memory does not yet support a reliable conclusion on this question.",
        why_it_matters=why or "This still matters because the question is valid even when the current source set cannot answer it responsibly.",
        key_points=[
            limitation or "The current source set does not preserve enough direct evidence to support a stronger answer.",
            "A more confident answer would require clearer, better-linked source evidence.",
        ],
        detailed_explanation="The right response here is to stay conservative. The available evidence is not strong enough to support a reliable answer without filling the gap through inference.",
        evidence_status="missing",
        evidence_summary="Not supported by available evidence.",
        evidence_points=["The response is intentionally conservative rather than inferred beyond the evidence."],
        uncertainty=limitation or "A stronger answer would require additional source evidence.",
        products_refs=[],
        business_journey_ref=None,
    )


def _build_unavailable_answer(question: Dict[str, Any], direct_answer: str, why: str, limitation: str) -> Dict[str, Any]:
    return _draft(
        answer_status="unavailable",
        simple_answer=direct_answer,
        why_it_matters=why,
        key_points=[limitation],
        detailed_explanation="The upstream source needed for this answer is absent, so the answer remains unavailable rather than guessed.",
        evidence_status="missing",
        evidence_summary="The required upstream evidence is unavailable.",
        evidence_points=[limitation],
        uncertainty=limitation,
        products_refs=[],
        business_journey_ref=None,
    )


ANSWER_BUILDERS = {
    "what-does-company-do": _build_business_summary_answer,
    "who-are-the-customers": _build_customers_answer,
    "how-does-it-make-money": _build_make_money_answer,
    "what-makes-the-offering-important": _build_offering_importance_answer,
    "where-is-evidence-thin": _build_evidence_thin_answer,
    "are-profits-converting-into-cash": _build_cash_conversion_answer,
    "what-is-owner-earnings": _build_owner_earnings_answer,
    "is-working-capital-a-concern": _build_working_capital_answer,
    "are-per-share-economics-improving": _build_per_share_answer,
    "what-has-management-promised": _build_management_promises_answer,
    "did-past-claims-come-true": _build_past_claims_answer,
    "what-projects-are-underway": _build_projects_answer,
    "how-is-capacity-changing": _build_capacity_answer,
    "what-is-management-commentary-saying": _build_commentary_answer,
    "how-is-capital-allocated": _build_capital_allocation_answer,
    "what-incentives-matter": _build_incentives_answer,
    "what-should-i-ask-ir": _build_ask_ir_answer,
    "what-would-graham-worry-about": lambda *args, **kwargs: _build_lens_answer(*args, lens_key="graham_analysis", why="This lens matters because it stresses downside protection, financial resilience, and whether weak cash conversion can undermine a seemingly strong business.", **kwargs),
    "what-would-buffett-focus-on": _build_buffett_answer,
    "where-would-fisher-be-curious": lambda *args, **kwargs: _build_lens_answer(*args, lens_key="fisher_analysis", why="This lens matters because strong growth deserves confidence only when execution, innovation, and funding quality are real.", **kwargs),
    "what-would-munger-avoid": lambda *args, **kwargs: _build_lens_answer(*args, lens_key="munger_analysis", why="This lens matters because governance, incentives, and avoidable complexity can damage even a good business.", **kwargs),
    "how-would-lynch-explain-it": lambda *args, **kwargs: _build_lens_answer(*args, lens_key="lynch_analysis", why="This lens matters because the business story should stay simple and understandable when checked against the numbers.", **kwargs),
    "what-can-break-the-thesis": _build_break_thesis_answer,
    "which-disclosure-is-missing": _build_missing_disclosure_answer,
    "what-evidence-would-change-the-view": _build_change_view_answer,
    "what-needs-management-clarification": _build_needs_clarification_answer,
    "what-remains-unresolved": _build_unresolved_answer,
}


def _draft(
    *,
    answer_status: str,
    simple_answer: str,
    why_it_matters: str,
    key_points: List[str],
    detailed_explanation: str,
    evidence_status: str,
    evidence_summary: str,
    evidence_points: List[str],
    uncertainty: str,
    products_refs: List[str],
    business_journey_ref: Optional[str],
    business_journey_mode: BusinessJourneyMode = "none",
    customer_roles: Optional[Dict[str, Any]] = None,
    revenue_flow: Optional[Dict[str, Any]] = None,
    structured_sections: Optional[List[Dict[str, Any]]] = None,
    progression: Optional[Dict[str, Any]] = None,
    interpretation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "answer_status": answer_status,
        "simple_answer": sanitize_public_text(simple_answer),
        "why_it_matters": sanitize_public_text(why_it_matters),
        "key_points": _clean_list(key_points)[:4],
        "detailed_explanation": sanitize_public_text(detailed_explanation),
        "products_and_services_refs": list(products_refs),
        "business_journey_ref": business_journey_ref,
        "business_journey_mode": business_journey_mode,
        "customer_roles": customer_roles,
        "revenue_flow": revenue_flow,
        "structured_sections": structured_sections or [],
        "progression": progression,
        "interpretation": interpretation,
        "evidence_summary": {
            "status": evidence_status,
            "summary": sanitize_public_text(evidence_summary),
            "supporting_points": _clean_list(evidence_points)[:3],
        },
        "uncertainty_note": {
            "title": "Uncertainty note",
            "message": sanitize_public_text(uncertainty),
        },
    }


def _build_coverage_summary(answers: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {
        "total_questions": len(QUESTION_INDEX),
        "supported": 0,
        "partially_supported": 0,
        "not_supported": 0,
        "unavailable": 0,
    }
    for answer in answers:
        status = str(answer.get("answer_status") or "")
        if status in summary:
            summary[status] += 1
    return summary


def _build_next_questions(question_id: str) -> List[Dict[str, str]]:
    next_ids = NEXT_QUESTION_MAP[question_id]
    return [
        {
            "question_id": next_id,
            "title": QUESTION_INDEX[next_id]["title"],
            "category_id": QUESTION_INDEX[next_id]["category_id"],
        }
        for next_id in next_ids
    ]


def _source_payload(source_bundle: Dict[str, Any], source_name: str) -> Dict[str, Any]:
    source = ((source_bundle.get("sources") or {}).get(source_name) or {})
    payload = source.get("payload")
    return payload if isinstance(payload, dict) else {}


def _get_record(value: Dict[str, Any], key: str) -> Dict[str, Any]:
    nested = value.get(key)
    return nested if isinstance(nested, dict) else {}


def _get_record_list(value: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    nested = value.get(key)
    if not isinstance(nested, list):
        return []
    return [item for item in nested if isinstance(item, dict)]


def _get_string(value: Dict[str, Any], key: str) -> str:
    nested = value.get(key)
    return str(nested).strip() if isinstance(nested, str) and str(nested).strip() else ""


def _get_string_list(value: Dict[str, Any], key: str) -> List[str]:
    nested = value.get(key)
    if not isinstance(nested, list):
        return []
    return [str(item).strip() for item in nested if isinstance(item, str) and str(item).strip()]


def _get_list(value: Dict[str, Any], key: str) -> List[Any]:
    nested = value.get(key)
    return nested if isinstance(nested, list) else []


def _get_number(value: Dict[str, Any], key: str) -> Optional[float]:
    nested = value.get(key)
    if isinstance(nested, (int, float)):
        return float(nested)
    return None


def _latest_year_record(source_payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    items = _get_record_list(source_payload, key)
    if not items:
        return {}
    ordered = sorted(items, key=lambda item: _year_sort_key(_year_label(item)))
    return ordered[-1]


def _year_label(value: Dict[str, Any]) -> str:
    for key in ("fiscal_year", "year", "fy", "fiscalYear"):
        raw = value.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def _year_sort_key(value: str) -> int:
    text = str(value or "").lower().replace("fy", "").strip()
    try:
        return int(text)
    except ValueError:
        return 0


def _first_string(*values: Any) -> str:
    flattened: List[str] = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(str(item).strip() for item in value if isinstance(item, str))
        elif isinstance(value, str):
            flattened.append(value.strip())
    for item in flattened:
        if item:
            return item
    return ""


def first_available_text(*values: str) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _clean_list(values: List[Any]) -> List[str]:
    cleaned = []
    seen = set()
    boilerplate = {
        "no material evidence limitation was identified for this answer",
    }
    for value in values:
        text = sanitize_public_text(str(value or "").strip())
        normalized = _normalize_sentence(text)
        if (
            not text
            or normalized in seen
            or normalized in boilerplate
            or contains_forbidden_public_term(text)
        ):
            continue
        seen.add(normalized)
        cleaned.append(text)
    return cleaned


def _first_product_refs(products_services_payload: Dict[str, Any], *, limit: int) -> List[str]:
    refs = []
    for group in products_services_payload.get("groups", []) or []:
        for item in group.get("items", []) or []:
            item_id = str(item.get("id") or "").strip()
            if item_id:
                refs.append(item_id)
    return refs[:limit]


def _first_product_names(products_services_payload: Dict[str, Any], *, limit: int) -> List[str]:
    names = []
    for group in products_services_payload.get("groups", []) or []:
        for item in group.get("items", []) or []:
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
    return names[:limit]


def _unique_product_customer_types(products_services_payload: Dict[str, Any]) -> List[str]:
    seen = []
    for group in products_services_payload.get("groups", []) or []:
        for item in group.get("items", []) or []:
            customer_type = str(item.get("customer_type") or "").strip()
            if customer_type and customer_type not in seen and "not clearly established" not in customer_type.lower():
                seen.append(customer_type)
    return seen


def _latest_journey_stage_id(business_journey_payload: Dict[str, Any]) -> Optional[str]:
    stages = business_journey_payload.get("stages", []) or []
    if not stages:
        return None
    return str(stages[-1].get("id") or "") or None


def _latest_business_model_field(source_bundle: Dict[str, Any], field: str) -> str:
    pcim = _source_payload(source_bundle, "pcim")
    latest = _get_record(_get_record(_get_record(pcim, "business_understanding"), "latest_business_view"), "business_model")
    value = _get_string(latest, field)
    if value:
        return value
    yearly = _get_record_list(_get_record(pcim, "business_understanding"), "business_model_by_year")
    ordered = sorted(yearly, key=lambda item: _year_sort_key(_get_string(item, "year")))
    if ordered:
        return _get_string(ordered[-1], field)
    return ""


def _risk_texts(source_bundle: Dict[str, Any]) -> List[str]:
    committee = _source_payload(source_bundle, "committee_synthesis")
    risks = []
    for item in _get_record_list(committee, "most_important_risks"):
        risks.extend(_clean_list([_get_string(item, "risk"), _get_string(item, "why_it_matters")]))
    for lens_key in ("buffett_analysis", "graham_analysis", "munger_analysis"):
        risks.extend(_get_string_list(_source_payload(source_bundle, lens_key), "red_flags"))
    return _clean_list(risks)


def _unknown_texts(items: List[Dict[str, Any]]) -> List[str]:
    values = []
    for item in items:
        values.extend(_clean_list([_get_string(item, "unknown"), _get_string(item, "why_it_matters")]))
    return values


def _question_texts(items: List[Dict[str, Any]]) -> List[str]:
    values = []
    for item in items:
        values.extend(_clean_list([_get_string(item, "question")]))
    return values


def finalize_answer_against_reconciled_truth(
    answer_card: Dict[str, Any],
    financial_truth_pack: Dict[str, Any],
    investor_financial_modules: Dict[str, Any],
    uncertainty_map: Dict[str, Any],
) -> Dict[str, Any]:
    truth = _build_reconciled_truth_snapshot(financial_truth_pack, investor_financial_modules)
    contradiction_rewrite = _precision_limited_truth_sentence(truth)

    simple_answer = _rewrite_stale_missing_claims(str(answer_card.get("simple_answer") or ""), truth, contradiction_rewrite)
    detailed_explanation = _rewrite_stale_missing_claims(str(answer_card.get("detailed_explanation") or ""), truth, contradiction_rewrite)
    why_it_matters = _rewrite_stale_missing_claims(str(answer_card.get("why_it_matters") or ""), truth, contradiction_rewrite)
    key_points = [
        _rewrite_stale_missing_claims(str(point or ""), truth, contradiction_rewrite)
        for point in (answer_card.get("key_points") or [])
    ]
    evidence_summary = dict(answer_card.get("evidence_summary") or {})
    evidence_summary["summary"] = _rewrite_stale_missing_claims(
        str(evidence_summary.get("summary") or ""),
        truth,
        contradiction_rewrite,
    )
    evidence_summary["supporting_points"] = [
        _rewrite_stale_missing_claims(str(point or ""), truth, contradiction_rewrite)
        for point in (evidence_summary.get("supporting_points") or [])
    ]
    uncertainty_note = dict(answer_card.get("uncertainty_note") or {})
    uncertainty_note["message"] = _rewrite_stale_missing_claims(
        str(uncertainty_note.get("message") or ""),
        truth,
        contradiction_rewrite,
    )

    interpretation = dict(answer_card.get("interpretation") or {})
    if not interpretation:
        progression = answer_card.get("progression") if isinstance(answer_card.get("progression"), dict) else {}
        interpretation = build_interpretation_contract(
            conclusion=str(answer_card.get("simple_answer") or ""),
            what_changed=_clean_list([str((progression or {}).get("what_changed") or "")] + list(answer_card.get("key_points") or []))[:3],
            why_it_matters=str(answer_card.get("why_it_matters") or ""),
            economic_mechanism=str((answer_card.get("detailed_explanation") or answer_card.get("why_it_matters") or ""))[:260],
            thesis_impact=(
                "strengthens"
                if str((progression or {}).get("conviction_impact") or "").lower() in {"strengthened", "strengthens"}
                else "weakens"
                if str((progression or {}).get("conviction_impact") or "").lower() in {"weakened", "weakens"}
                else "neutral"
                if str(answer_card.get("answer_status") or "").lower() in {"supported", "partially_supported"}
                else "unresolved"
            ),
            positive_evidence=_clean_list(evidence_summary.get("supporting_points") or [])[:3],
            negative_evidence=_clean_list([str(uncertainty_note.get("message") or "")])[:3],
            unresolved=_clean_list([str(uncertainty_note.get("message") or "")] + list((progression or {}).get("unresolved_items") or []))[:3],
            what_to_watch=_clean_list([str(item.get("description") or item.get("label") or "") for item in ((progression or {}).get("turning_points") or []) if isinstance(item, dict)])[:3],
            confidence={
                "level": "high" if str(answer_card.get("answer_status") or "").lower() == "supported" else "medium" if str(answer_card.get("answer_status") or "").lower() == "partially_supported" else "low",
                "basis": _clean_list([str(evidence_summary.get("status") or ""), str(evidence_summary.get("summary") or "")])[:2],
                "limitations": _clean_list([str(uncertainty_note.get("message") or "")])[:2],
            },
        )

    finalized = dict(answer_card)
    finalized["simple_answer"] = sanitize_public_text(_normalize_public_prose(simple_answer))
    finalized["why_it_matters"] = sanitize_public_text(_normalize_public_prose(why_it_matters))
    finalized["detailed_explanation"] = sanitize_public_text(_normalize_public_prose(detailed_explanation))
    finalized["key_points"] = [
        _clean_display_phrase(point, limit_words=16)
        for point in _dedupe_similar_lines(_clean_list(key_points))[:4]
        if _clean_display_phrase(point, limit_words=16)
    ]
    evidence_summary["supporting_points"] = _dedupe_similar_lines(_clean_list(evidence_summary["supporting_points"]))[:3]
    finalized["evidence_summary"] = evidence_summary
    finalized["uncertainty_note"] = uncertainty_note
    finalized["interpretation"] = interpretation
    finalized["structured_sections"] = _finalize_structured_sections(
        finalized.get("structured_sections"),
        truth,
        contradiction_rewrite,
    )
    interpretation = dict(finalized.get("interpretation") or {})
    def _trim_public_items(values: Any, *, limit: int = 3, word_limit: int = 16) -> List[str]:
        return [
            _clean_display_phrase(item, limit_words=word_limit)
            for item in _clean_list(list(values or []))
            if _clean_display_phrase(item, limit_words=word_limit)
        ][:limit]

    for field in ("what_changed", "positive_evidence", "negative_evidence", "unresolved", "what_to_watch"):
        value = interpretation.get(field)
        if isinstance(value, list):
            interpretation[field] = _trim_public_items(value, limit=3, word_limit=16)

    positive_items = list(interpretation.get("positive_evidence") or [])
    negative_items = list(interpretation.get("negative_evidence") or [])
    unresolved_items = list(interpretation.get("unresolved") or [])

    filtered_positive: List[str] = []
    for item in positive_items:
        if _looks_unresolved_like(item) or _looks_negative_like(item):
            unresolved_items.append(item)
            continue
        if _looks_positive_like(item) or not _looks_negative_like(item):
            filtered_positive.append(item)

    filtered_negative: List[str] = []
    for item in negative_items:
        if _looks_positive_like(item):
            unresolved_items.append(item)
            continue
        filtered_negative.append(item)

    interpretation["positive_evidence"] = _dedupe_similar_lines(_clean_list(filtered_positive))[:3]
    interpretation["negative_evidence"] = _dedupe_similar_lines(_clean_list(filtered_negative))[:3]
    interpretation["unresolved"] = _dedupe_similar_lines(_clean_list(unresolved_items))[:3]

    qid = str(finalized.get("question_id") or "")
    watch_items = list(interpretation.get("what_to_watch") or [])
    generic_watch = {
        "completion",
        "follow through",
        "follow-through",
        "execution",
        "later evidence",
    }
    if qid in {"what-has-management-promised", "did-past-claims-come-true"}:
        topic = _clean_display_phrase(
            _get_string(finalized.get("progression") or {}, "headline")
            or _get_string(finalized.get("progression") or {}, "what_changed")
            or _first_string(list(finalized.get("key_points") or [])),
            limit_words=8,
        )
        if not watch_items or all(_normalize_sentence(item) in generic_watch for item in watch_items):
            watch_items = [f"Completion evidence for {topic.lower()}"] if topic else []
    elif qid == "how-is-capital-allocated" and not watch_items:
        watch_items = _clean_list(
            [
                "Utilization of the new capacity",
                "Incremental margins or cash-flow evidence",
                "Per-share earnings or cash outcome from the deployment",
            ]
        )[:3]
    elif qid == "what-can-break-the-thesis" and not watch_items:
        watch_items = _clean_list(
            [
                "Receivable days",
                "Inventory days",
                "Cash conversion cycle",
                "CFO/PAT conversion",
                "Customer concentration and collection commentary",
                "Capital efficiency on future deployments",
            ]
        )[:3]
        interpretation["positive_evidence"] = []
        cleaned_unresolved = [
            item
            for item in _clean_list(list(interpretation.get("unresolved") or []))
            if _normalize_sentence(item) != _normalize_sentence("this remains a central caution.")
        ]
        if cleaned_unresolved:
            interpretation["unresolved"] = cleaned_unresolved[:3]
        cleaned_changed = [
            item
            for item in _clean_list(list(interpretation.get("what_changed") or []))
            if _normalize_sentence(item) != _normalize_sentence("this remains a central caution.")
        ]
        if cleaned_changed:
            interpretation["what_changed"] = cleaned_changed[:3]
        cleaned_key_points = [
            item
            for item in _clean_list(list(finalized.get("key_points") or []))
            if _normalize_sentence(item) != _normalize_sentence("this remains a central caution.")
        ]
        if cleaned_key_points:
            finalized["key_points"] = cleaned_key_points[:4]
        if not _clean_display_phrase(str(interpretation.get("economic_mechanism") or ""), limit_words=24):
            mechanism = _clean_display_phrase(
                str(finalized.get("detailed_explanation") or finalized.get("why_it_matters") or ""),
                limit_words=24,
            )
            if mechanism:
                interpretation["economic_mechanism"] = mechanism
    elif qid == "what-would-buffett-focus-on" and not watch_items:
        watch_items = _clean_list(
            [
                "Owner earnings versus reported profit",
                "Working-capital conversion",
                "Returns on incremental capital",
                "Per-share cash generation",
            ]
        )[:3]

    if watch_items:
        interpretation["what_to_watch"] = watch_items
    else:
        interpretation.pop("what_to_watch", None)
    finalized["interpretation"] = interpretation

    if str(finalized.get("question_id") or "") == "how-is-capital-allocated":
        def _capital_clean(values: Any) -> List[str]:
            cleaned: List[str] = []
            for item in _clean_list(list(values or [])):
                lowered = item.lower()
                if "net_worth" in lowered or "total_assets" in lowered:
                    continue
                cleaned.append(item)
            return cleaned

        for field in ("positive_evidence", "negative_evidence", "unresolved", "what_to_watch", "what_changed"):
            value = interpretation.get(field)
            if isinstance(value, list):
                cleaned = _capital_clean(value)
                if field == "positive_evidence" and not cleaned:
                    progression = finalized.get("progression") if isinstance(finalized.get("progression"), dict) else {}
                    cleaned = _capital_clean((progression or {}).get("latest_evidence") or [])
                if cleaned:
                    interpretation[field] = cleaned[:3]
        finalized["interpretation"] = interpretation

    if str(finalized.get("question_id") or "") == "what-would-buffett-focus-on":
        for field in ("simple_answer", "why_it_matters", "detailed_explanation"):
            value = finalized.get(field)
            if isinstance(value, str):
                cleaned = _strip_backend_phrasing(value)
                if cleaned:
                    finalized[field] = cleaned

        evidence_summary = dict(finalized.get("evidence_summary") or {})
        if isinstance(evidence_summary.get("summary"), str):
            cleaned_summary = _strip_backend_phrasing(evidence_summary["summary"])
            if cleaned_summary:
                evidence_summary["summary"] = cleaned_summary
        if isinstance(evidence_summary.get("supporting_points"), list):
            cleaned_points = []
            for item in evidence_summary["supporting_points"]:
                cleaned_item = _strip_backend_phrasing(str(item or ""))
                if cleaned_item:
                    cleaned_points.append(cleaned_item)
            if cleaned_points:
                evidence_summary["supporting_points"] = cleaned_points[:3]
        finalized["evidence_summary"] = evidence_summary

        interpretation = dict(finalized.get("interpretation") or {})
        for field in ("conclusion", "what_changed", "positive_evidence", "negative_evidence", "unresolved", "what_to_watch", "why_it_matters", "economic_mechanism"):
            value = interpretation.get(field)
            if isinstance(value, str):
                cleaned = _strip_backend_phrasing(value)
                if cleaned:
                    interpretation[field] = cleaned
            elif isinstance(value, list):
                cleaned_list = [_strip_backend_phrasing(str(item or "")) for item in value]
                cleaned_list = [item for item in cleaned_list if item]
                if cleaned_list:
                    interpretation[field] = cleaned_list[:3]
        if isinstance(finalized.get("structured_sections"), list):
            cleaned_sections = []
            for section in finalized["structured_sections"]:
                if not isinstance(section, dict):
                    continue
                title = _strip_backend_phrasing(str(section.get("title") or ""))
                points = [_strip_backend_phrasing(str(point or "")) for point in (section.get("points") or [])]
                points = [point for point in points if point]
                if title and points:
                    cleaned_sections.append({**section, "title": title, "points": points[:2]})
            if cleaned_sections:
                finalized["structured_sections"] = cleaned_sections[:3]
        finalized["interpretation"] = interpretation

    if str(finalized.get("question_id") or "") in {"what-has-management-promised", "did-past-claims-come-true"}:
        progression = finalized.get("progression") if isinstance(finalized.get("progression"), dict) else {}
        commitment_points = _clean_list(list(finalized.get("key_points") or []))
        if commitment_points:
            interpretation["what_changed"] = commitment_points[:3]
        unresolved_points = _clean_list(_get_string_list(progression, "unresolved_items"))
        if str(finalized.get("question_id") or "") == "what-has-management-promised":
            interpretation["negative_evidence"] = []
        elif unresolved_points:
            interpretation["negative_evidence"] = unresolved_points[:3]
        else:
            interpretation["negative_evidence"] = []
        if unresolved_points:
            interpretation["unresolved"] = unresolved_points[:3]
        finalized["interpretation"] = interpretation

    if str(finalized.get("question_id") or "") in {"how-is-capital-allocated", "what-incentives-matter"}:
        cleaned_positive: List[str] = []
        for item in list(interpretation.get("positive_evidence") or []):
            if _looks_unresolved_like(item) or _looks_negative_like(item):
                unresolved_items.append(item)
                continue
            cleaned_positive.append(item)
        interpretation["positive_evidence"] = _dedupe_similar_lines(_clean_list(cleaned_positive))[:3]
        interpretation["unresolved"] = _dedupe_similar_lines(_clean_list(unresolved_items))[:3]
        finalized["interpretation"] = interpretation

    if truth["has_current_cash_metrics"]:
        finalized["uncertainty_note"]["message"] = _prefer_real_limitation_over_missing_claim(
            str(finalized["uncertainty_note"].get("message") or ""),
            contradiction_rewrite,
        )

    finalized = _reduce_public_answer_repetition(finalized)
    return sanitize_public_payload(finalized)


def detect_public_answer_repetition(answer_card: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    simple = _normalized_sentence_set(str(answer_card.get("simple_answer") or ""))
    why = _normalized_sentence_set(str(answer_card.get("why_it_matters") or ""))
    detail = _normalized_sentence_set(str(answer_card.get("detailed_explanation") or ""))
    key_points = [_normalize_sentence(point) for point in (answer_card.get("key_points") or []) if str(point or "").strip()]
    evidence_summary = _normalized_sentence_set(str((answer_card.get("evidence_summary") or {}).get("summary") or ""))
    uncertainty = _normalized_sentence_set(str((answer_card.get("uncertainty_note") or {}).get("message") or ""))

    if simple & set(key_points):
        issues.append("simple_answer repeats key_points")
    if simple & why:
        issues.append("why_it_matters repeats simple_answer")
    if evidence_summary & set(key_points):
        issues.append("evidence_summary repeats key_points")
    if uncertainty & simple:
        issues.append("uncertainty_note repeats simple_answer")
    if detail & simple and len(detail) <= len(simple):
        issues.append("detailed_explanation does not add meaning beyond simple_answer")
    return issues


def detect_answer_truth_contradictions(
    answer_card: Dict[str, Any],
    financial_truth_pack: Dict[str, Any],
    investor_financial_modules: Dict[str, Any],
) -> List[str]:
    issues: List[str] = []
    truth = _build_reconciled_truth_snapshot(financial_truth_pack, investor_financial_modules)
    joined_text = " ".join(
        [
            str(answer_card.get("simple_answer") or ""),
            str(answer_card.get("detailed_explanation") or ""),
            str((answer_card.get("evidence_summary") or {}).get("summary") or ""),
            " ".join(str(point or "") for point in (answer_card.get("key_points") or [])),
            " ".join(str(point or "") for point in ((answer_card.get("evidence_summary") or {}).get("supporting_points") or [])),
            str((answer_card.get("uncertainty_note") or {}).get("message") or ""),
        ]
    ).lower()
    if truth["has_current_cash_metrics"] and _contains_stale_missing_financial_claim(joined_text):
        issues.append("answer contains stale missing-financial claim despite reconciled current values")
    if truth["has_owner_earnings"] and "owner-earnings cannot be reliably assessed" in joined_text:
        issues.append("answer denies owner-earnings visibility despite reconciled owner-earnings estimate")
    return issues


def _build_reconciled_truth_snapshot(
    financial_truth_pack: Dict[str, Any],
    investor_financial_modules: Dict[str, Any],
) -> Dict[str, bool]:
    latest_bridge = _latest_year_record(investor_financial_modules.get("owner_earnings_bridge") or {}, "bridges")
    latest_per_share = _latest_year_record(investor_financial_modules.get("per_share_compounding_analysis") or {}, "analysis")
    latest_truth = _latest_truth_metrics(financial_truth_pack)
    has_cfo = latest_truth.get("cfo") is not None or _get_number(latest_bridge, "cfo") is not None
    has_capex = _get_number(latest_bridge, "total_identified_capex") is not None
    has_fcf = latest_truth.get("fcf") is not None or _get_number(latest_bridge, "conservative_fcf_after_total_capex") is not None
    has_owner_earnings = _get_number(latest_bridge, "owner_earnings_estimate") is not None
    has_weighted_shares = latest_truth.get("eps_basic") is not None or _get_number(latest_per_share, "eps_basic") is not None
    return {
        "has_cfo": has_cfo,
        "has_capex": has_capex,
        "has_fcf": has_fcf,
        "has_owner_earnings": has_owner_earnings,
        "has_weighted_shares": has_weighted_shares,
        "has_current_cash_metrics": any([has_cfo, has_capex, has_fcf, has_owner_earnings]),
    }


def _latest_truth_metrics(financial_truth_pack: Dict[str, Any]) -> Dict[str, Optional[float]]:
    current_metrics = [
        metric
        for metric in (financial_truth_pack.get("usable_current_metrics") or [])
        if isinstance(metric, dict)
    ]
    latest_year = ""
    for metric in current_metrics:
        year = str(metric.get("fiscal_year") or "").strip()
        if _year_sort_key(year) >= _year_sort_key(latest_year):
            latest_year = year
    snapshot: Dict[str, Optional[float]] = {}
    for metric in current_metrics:
        year = str(metric.get("fiscal_year") or "").strip()
        if latest_year and year != latest_year:
            continue
        metric_id = str(metric.get("metric_id") or metric.get("canonical_metric") or "").strip()
        value = metric.get("value")
        if not isinstance(value, (int, float)):
            value = metric.get("value_crore")
        snapshot[metric_id] = float(value) if isinstance(value, (int, float)) else None
    return snapshot


def _precision_limited_truth_sentence(truth: Dict[str, bool]) -> str:
    if truth["has_owner_earnings"] and truth["has_cfo"] and truth["has_capex"]:
        return "The available evidence includes current cash flow, identified capex, and an owner-earnings estimate, but precision is still limited by the missing maintenance-versus-growth capex split and incomplete history."
    if truth["has_cfo"] or truth["has_capex"] or truth["has_fcf"]:
        return "The available evidence includes current cash-flow inputs, but the main limitation is precision, comparability, and incomplete multi-year history rather than total absence."
    return "The main limitation is precision and comparability, not broad missing-data language."


def _rewrite_stale_missing_claims(text: str, truth: Dict[str, bool], replacement: str) -> str:
    cleaned = _normalize_public_prose(text)
    if not cleaned:
        return cleaned
    if truth["has_current_cash_metrics"] and _contains_stale_missing_financial_claim(cleaned.lower()):
        replacements = [
            (
                r"however, material financial data \(CFO, capex, FCF and certain per-share comparability inputs\) are missing, limiting any owner-earnings or cash-conversion conclusions\.",
                f"however, {replacement.lower()}",
            ),
            (
                r"Key cash-flow inputs are unavailable in the available evidence \(CFO, capex, and therefore free cash flow\), preventing FCF-based assessment\.",
                replacement,
            ),
            (
                r"Owner-earnings readiness:.*?(?:\.|$)",
                replacement,
            ),
            (
                r"Owner-earnings bridge cannot be built because CFO or capex evidence is absent\.",
                replacement,
            ),
        ]
        updated = cleaned
        for pattern, substitute in replacements:
            updated = re.sub(pattern, substitute, updated, flags=re.IGNORECASE)
        if updated != cleaned:
            cleaned = updated
        else:
            cleaned = replacement if len(cleaned.split()) < 28 else f"{cleaned} {replacement}"
    if truth["has_owner_earnings"]:
        cleaned = re.sub(
            r"Owner-earnings readiness:.*?(?:\.|$)",
            replacement,
            cleaned,
            flags=re.IGNORECASE,
        )
    cleaned = cleaned.replace("supplied facts", "available evidence")
    cleaned = cleaned.replace("material financial data inputs", "financial detail")
    cleaned = cleaned.replace("investment-style interpretation", "investor reading")
    return cleaned.strip()


def _prefer_real_limitation_over_missing_claim(text: str, replacement: str) -> str:
    if _contains_stale_missing_financial_claim(text.lower()):
        return replacement
    return text


def _contains_stale_missing_financial_claim(text: str) -> bool:
    stale_patterns = [
        "cfo, capex, fcf",
        "cfo and capex evidence are absent",
        "key cash-flow inputs are unavailable",
        "owner-earnings bridge cannot be built because cfo or capex evidence is absent",
        "owner-earnings cannot be reliably assessed",
        "material financial data",
    ]
    return any(pattern in text for pattern in stale_patterns)


def _reduce_public_answer_repetition(answer_card: Dict[str, Any]) -> Dict[str, Any]:
    reduced = dict(answer_card)
    simple = _normalize_sentence(str(reduced.get("simple_answer") or ""))
    why = str(reduced.get("why_it_matters") or "").strip()
    if _normalize_sentence(why) == simple:
        reduced["why_it_matters"] = "This matters because cash quality, customer mix, or business durability can look very different once the evidence is unpacked."
    key_points = []
    seen = set(simple and [simple] or [])
    for point in reduced.get("key_points", []) or []:
        normalized = _normalize_sentence(str(point or ""))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        key_points.append(point)
    reduced["key_points"] = key_points[:4]
    evidence_summary = dict(reduced.get("evidence_summary") or {})
    evidence_summary_text = _normalize_sentence(str(evidence_summary.get("summary") or ""))
    if evidence_summary_text and evidence_summary_text in seen:
        evidence_summary["summary"] = "The available evidence supports this answer, but some details remain incomplete."
    reduced["evidence_summary"] = evidence_summary
    uncertainty_message = str((reduced.get("uncertainty_note") or {}).get("message") or "")
    if _normalize_sentence(uncertainty_message) in seen:
        reduced.setdefault("uncertainty_note", {})["message"] = "The main limitation is precision or missing detail, not the core direction of the answer."
    return reduced


def _normalized_sentence_set(text: str) -> set[str]:
    return {_normalize_sentence(sentence) for sentence in re.split(r"(?<=[.!?])\s+", text) if _normalize_sentence(sentence)}


def _normalize_sentence(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _looks_unresolved_like(text: str) -> bool:
    normalized = _normalize_sentence(text)
    if not normalized:
        return False
    patterns = (
        "not yet",
        "not proven",
        "not separated",
        "not disclosed",
        "unable",
        "unclear",
        "incomplete",
        "limited",
        "missing",
        "still",
        "unproven",
        "cannot",
        "does not yet",
        "no later evidence",
        "not enough later evidence",
        "no evidence",
        "in progress",
        "central caution",
        "remains underway",
    )
    return any(pattern in normalized for pattern in patterns)


def _looks_positive_like(text: str) -> bool:
    normalized = _normalize_sentence(text)
    if not normalized:
        return False
    positive_markers = (
        "improved",
        "strengthens",
        "supports",
        "visible",
        "delivered",
        "commissioned",
        "utilized",
        "expanded",
        "higher",
        "better",
        "proved",
        "compounding",
        "converted",
        "disclosed",
        "evidence shows",
    )
    return any(pattern in normalized for pattern in positive_markers)


def _looks_negative_like(text: str) -> bool:
    normalized = _normalize_sentence(text)
    if not normalized:
        return False
    negative_markers = (
        "mixed",
        "weakened",
        "weaker",
        "weak cash conversion",
        "cash strain risk",
        "operational cash strain risk",
        "working capital risk",
        "strain risk",
        "caution",
        "fragile",
        "pressure",
        "delay",
        "delayed",
        "headwind",
        "downside",
        "not cleanly attributable",
        "indirect",
    )
    return any(pattern in normalized for pattern in negative_markers)


def _dedupe_similar_lines(values: List[str]) -> List[str]:
    cleaned: List[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_sentence(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(value)
    return cleaned


def _normalize_public_prose(text: str) -> str:
    collapsed = " ".join(str(text or "").split()).strip()
    collapsed = collapsed.replace(" ;", ";").replace(" ,", ",")
    return collapsed


def _customer_roles_from_types(customer_types: List[str], *, role: str) -> List[str]:
    labels: List[str] = []
    for customer_type in customer_types:
        for fragment in _split_customer_type_fragments(customer_type):
            lowered = fragment.lower()
            if role == "paying" and any(token in lowered for token in ("government", "manufacturer", "customer", "agency")):
                labels.append(fragment)
            if role == "integrating" and any(token in lowered for token in ("integrator", "manufacturer", "oem", "partner")):
                labels.append(fragment)
            if role == "using" and any(token in lowered for token in ("government", "agency", "operator", "user", "institution")) and not any(
                token in lowered for token in ("integrator", "manufacturer", "oem", "partner")
            ):
                labels.append(fragment)
    return _dedupe_similar_lines(labels)


def _split_customer_type_fragments(customer_type: str) -> List[str]:
    text = sanitize_public_text(customer_type).strip(" ,;")
    if not text:
        return []
    pieces = re.split(r",|/|\band\b", text, flags=re.IGNORECASE)
    normalized: List[str] = []
    for piece in pieces:
        fragment = sanitize_public_text(piece).strip(" ,;")
        if not fragment:
            continue
        lowered = fragment.lower()
        if lowered == "original equipment manufacturer":
            normalized.append("original equipment manufacturers")
        elif lowered == "government agency":
            normalized.append("government agencies")
        elif lowered == "defence integrator":
            normalized.append("defence integrators")
        else:
            normalized.append(fragment)
    return _dedupe_similar_lines(normalized)


def _build_customer_roles(
    *,
    payers: List[str],
    integrators_or_partners: List[str],
    end_users: List[str],
    international_customers: List[str],
    concentration_note: str,
    evidence_status: str,
) -> Dict[str, Any]:
    if not payers:
        payers = ["Role separation is unclear in the available evidence."]
    if not integrators_or_partners:
        integrators_or_partners = ["Integrator or partner roles are not clearly separated in the available evidence."]
    if not end_users:
        end_users = ["End-user roles are not clearly separated in the available evidence."]
    return {
        "payers": _dedupe_similar_lines(payers),
        "integrators_or_partners": _dedupe_similar_lines(integrators_or_partners),
        "end_users": _dedupe_similar_lines(end_users),
        "international_customers": _dedupe_similar_lines(international_customers),
        "concentration_note": sanitize_public_text(concentration_note),
        "evidence_status": evidence_status,
    }


def _build_revenue_flow(source_bundle: Dict[str, Any], products_services_payload: Dict[str, Any]) -> Dict[str, Any]:
    revenue_text = " ".join(
        [
            str(products_services_payload.get("business_model_summary") or ""),
            str(products_services_payload.get("revenue_logic_summary") or ""),
            " ".join(_first_product_names(products_services_payload, limit=5)),
        ]
    ).lower()
    if any(token in revenue_text for token in ("cpaas", "saas", "platform", "messaging", "marketing automation", "cloud communications")):
        return {
            "model_type": "mixed",
            "steps": [
                {"order": 1, "label": "Win enterprise or operator relationship", "explanation": "The business appears to begin with enterprise customers or telecom partners adopting a communication platform or service."},
                {"order": 2, "label": "Configure communication workflows", "explanation": "The company then appears to configure messaging, security, engagement, or automation workflows for customer use cases."},
                {"order": 3, "label": "Operate platform traffic", "explanation": "Revenue depends on platform usage, managed deployments, or communication volumes."},
                {"order": 4, "label": "Bill for services", "explanation": "Billing appears tied to platform services, customer agreements, or usage-linked communication activity."},
                {"order": 5, "label": "Collect and reinvest", "explanation": "Cash quality still depends on customer collections, platform investment needs, and working-capital discipline."},
            ],
            "cash_timing_note": "Cash timing depends on customer collections and service-commercial terms, not on physical programme acceptance milestones.",
            "working_capital_note": _working_capital_implication(source_bundle),
            "evidence_status": "partial",
            "offering_examples": _first_product_names(products_services_payload, limit=3),
        }
    flow_steps = [
        {"order": 1, "label": "Win programme or order", "explanation": "The business appears to begin with a customer order or programme award."},
        {"order": 2, "label": "Define system scope", "explanation": "The company then appears to tailor the subsystem, product, or integrated system to programme requirements."},
        {"order": 3, "label": "Build and qualify", "explanation": "Delivery appears to depend on in-house manufacturing, testing, or qualification work before customer acceptance."},
        {"order": 4, "label": "Integrate and deliver", "explanation": "Systems or subsystems are then integrated into the wider customer programme or platform."},
        {"order": 5, "label": "Bill against milestones", "explanation": "Billing appears linked to delivery, acceptance, or project milestones rather than simple recurring subscription timing."},
        {"order": 6, "label": "Collect cash later", "explanation": "Cash conversion can lag delivery because collections depend on programme timing and working-capital intensity."},
    ]
    return {
        "model_type": "project_based",
        "steps": flow_steps,
        "cash_timing_note": "Cash timing appears tied to delivery or acceptance milestones rather than smooth recurring billing.",
        "working_capital_note": _working_capital_implication(source_bundle),
        "evidence_status": "partial",
        "offering_examples": _first_product_names(products_services_payload, limit=3),
    }


def _finalize_structured_sections(
    sections: Any,
    truth: Dict[str, bool],
    contradiction_rewrite: str,
) -> List[Dict[str, Any]]:
    if not isinstance(sections, list):
        return []
    finalized_sections: List[Dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = sanitize_public_text(str(section.get("title") or "").strip())
        raw_points = section.get("points")
        if not isinstance(raw_points, list):
            raw_points = []
        points = [
            _rewrite_stale_missing_claims(str(point or ""), truth, contradiction_rewrite)
            for point in raw_points
        ]
        cleaned_points = _dedupe_similar_lines(_clean_list(points))[:3]
        if not title or not cleaned_points:
            continue
        finalized_sections.append({"title": title, "points": cleaned_points})
    return finalized_sections


def _working_capital_implication(source_bundle: Dict[str, Any]) -> str:
    working_capital = _latest_year_record(_source_payload(source_bundle, "working_capital_quality_drilldown"), "drilldown")
    cycle = _get_number(working_capital, "cash_conversion_cycle")
    if cycle is None:
        return "The available evidence does not yet show the full cash-conversion cycle."
    return f"Working capital is important because cash appears to stay tied up for about {format_number(cycle)} days before it returns."


def _join_human_list(values: List[str]) -> str:
    cleaned = [value for value in values if str(value or "").strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def format_crore(value: Optional[float]) -> str:
    return f"₹{value:.2f} crore" if isinstance(value, (int, float)) else "not yet visible"


def format_number(value: Optional[float]) -> str:
    return f"{value:.1f}" if isinstance(value, (int, float)) else "not yet visible"


def format_per_share(value: Optional[float]) -> str:
    return f"₹{value:.2f} per share" if isinstance(value, (int, float)) else "not yet visible"
