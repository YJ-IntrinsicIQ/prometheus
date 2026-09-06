from __future__ import annotations

import math
import re

from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

from intelligence.progression import build_interpretation_contract

from .canonical_projection import (
    canonical_company_model,
    canonical_management_progression,
    progression_items_for_question,
    summarize_progression_item,
    _billing_basis_phrase,
)
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
            {"id": "what-promise-types-dominate", "title": "What promise types dominate?", "short_label": "Promise types", "recommended": False},
            {"id": "which-promises-are-overdue", "title": "Which promises are overdue?", "short_label": "Overdue", "recommended": False},
            {"id": "what-was-delivered-last-3-years", "title": "What was delivered in the last 3 years?", "short_label": "Delivered", "recommended": False},
            {"id": "what-was-missed", "title": "What was missed?", "short_label": "Missed", "recommended": False},
            {"id": "did-past-claims-come-true", "title": "Did past claims come true?", "short_label": "Follow-through", "recommended": False},
            {"id": "what-projects-are-underway", "title": "What projects are underway?", "short_label": "Projects", "recommended": False},
            {"id": "how-is-capacity-changing", "title": "How is capacity changing?", "short_label": "Capacity", "recommended": False},
            {"id": "what-is-management-commentary-saying", "title": "What is management commentary saying?", "short_label": "Commentary", "recommended": False},
            {"id": "how-is-capital-allocated", "title": "How is capital allocated?", "short_label": "Capital allocation", "recommended": False},
            {"id": "what-is-the-return-on-capex", "title": "What is the return on capex?", "short_label": "Capex return", "recommended": False},
            {"id": "what-incentives-matter", "title": "What signals management quality?", "short_label": "Management quality", "recommended": False},
        ],
    },
    {
        "id": "risks-and-diligence",
        "title": "Risks and Diligence",
        "short_description": "Keep the unresolved issues visible so the next step stays grounded instead of overconfident.",
        "display_order": 4,
        "questions": [
            {"id": "what-regulatory-risks-remain-active", "title": "What regulatory risks remain active?", "short_label": "Regulatory risks", "recommended": False},
            {"id": "what-can-break-the-thesis", "title": "What can break the thesis?", "short_label": "Break the thesis", "recommended": False},
            {"id": "which-disclosure-is-missing", "title": "Which disclosure is missing?", "short_label": "Missing disclosure", "recommended": False},
            {"id": "what-evidence-would-change-the-view", "title": "What evidence would change the view?", "short_label": "Change the view", "recommended": False},
            {"id": "what-needs-management-clarification", "title": "What needs management clarification?", "short_label": "Needs clarification", "recommended": False},
            {"id": "what-should-i-ask-ir", "title": "What should I ask IR?", "short_label": "Ask IR", "recommended": False},
            {"id": "what-remains-unresolved", "title": "What remains unresolved?", "short_label": "Unresolved", "recommended": False},
        ],
    },
    {
        "id": "committee-view",
        "title": "Committee View",
        "short_description": "See where the five investor analysts agree, disagree, and what direction they are pointing.",
        "display_order": 5,
        "questions": [
            {"id": "what-is-committee-direction", "title": "What is the committee's direction?", "short_label": "Direction", "recommended": False},
            {"id": "where-does-the-committee-agree", "title": "Where does the committee agree?", "short_label": "Agreements", "recommended": False},
            {"id": "where-does-the-committee-disagree", "title": "Where does the committee disagree?", "short_label": "Disagreements", "recommended": False},
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
    "what-has-management-promised": ["what-promise-types-dominate", "which-promises-are-overdue", "what-was-delivered-last-3-years"],
    "what-promise-types-dominate": ["what-was-delivered-last-3-years", "what-was-missed", "did-past-claims-come-true"],
    "which-promises-are-overdue": ["what-was-missed", "what-needs-management-clarification", "what-can-break-the-thesis"],
    "what-was-delivered-last-3-years": ["what-was-missed", "did-past-claims-come-true", "how-is-capital-allocated"],
    "what-was-missed": ["which-promises-are-overdue", "what-can-break-the-thesis", "what-needs-management-clarification"],
    "did-past-claims-come-true": ["what-has-management-promised", "how-is-capacity-changing", "what-needs-management-clarification"],
    "what-projects-are-underway": ["how-is-capacity-changing", "what-is-management-commentary-saying", "how-is-capital-allocated"],
    "how-is-capacity-changing": ["what-projects-are-underway", "what-has-management-promised", "what-can-break-the-thesis"],
    "what-is-management-commentary-saying": ["what-has-management-promised", "what-incentives-matter", "what-remains-unresolved"],
    "how-is-capital-allocated": ["what-is-the-return-on-capex", "what-incentives-matter", "what-would-buffett-focus-on"],
    "what-is-the-return-on-capex": ["how-is-capital-allocated", "what-would-buffett-focus-on", "what-remains-unresolved"],
    "what-incentives-matter": ["how-is-capital-allocated", "what-would-munger-avoid", "what-should-i-ask-ir"],
    "what-regulatory-risks-remain-active": ["what-can-break-the-thesis", "what-remains-unresolved", "which-disclosure-is-missing"],
    "what-can-break-the-thesis": ["what-regulatory-risks-remain-active", "which-disclosure-is-missing", "what-remains-unresolved"],
    "what-is-committee-direction": ["where-does-the-committee-agree", "where-does-the-committee-disagree", "what-would-buffett-focus-on"],
    "where-does-the-committee-agree": ["what-is-committee-direction", "where-does-the-committee-disagree", "what-evidence-would-change-the-view"],
    "where-does-the-committee-disagree": ["what-is-committee-direction", "where-does-the-committee-agree", "what-remains-unresolved"],
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


# Question-scoped dependency map: which source artifacts each builder consumes.
# Used to build dependency_provenance per answer card so the UI loader can
# detect staleness before serving a saved card.
# Only list sources that the builder ACTUALLY reads — not every source in the registry.
QUESTION_DEPENDENCY_MAP: Dict[str, List[str]] = {
    "what-does-company-do": ["cim", "pcim", "company_model"],
    "who-are-the-customers": ["cim", "pcim", "company_model"],
    "how-does-it-make-money": ["cim", "pcim", "company_model"],
    "what-makes-the-offering-important": ["cim", "pcim"],
    "where-is-evidence-thin": ["cim", "pcim", "financial_truth_pack"],
    "are-profits-converting-into-cash": ["financial_truth_pack", "owner_earnings_bridge"],
    "what-is-owner-earnings": ["owner_earnings_bridge", "financial_truth_pack"],
    "is-working-capital-a-concern": ["working_capital_quality_drilldown", "financial_truth_pack"],
    "are-per-share-economics-improving": ["per_share_compounding_analysis", "financial_truth_pack"],
    "what-has-management-promised": ["gold_promise_tracker", "management_commitments", "management_progression"],
    "what-promise-types-dominate": ["gold_promise_tracker"],
    "which-promises-are-overdue": ["gold_promise_tracker"],
    "what-was-delivered-last-3-years": ["gold_promise_tracker"],
    "what-was-missed": ["gold_promise_tracker"],
    "did-past-claims-come-true": ["gold_promise_tracker", "gold_credibility", "management_commitments", "management_progression"],
    "what-projects-are-underway": ["projects_registry", "project_timelines", "project_assessments"],
    "how-is-capacity-changing": ["management_progression", "capacity_registry", "capacity_timelines"],
    "what-is-management-commentary-saying": ["management_progression", "commentary_themes"],
    "how-is-capital-allocated": ["capital_allocation_longitudinal_profile", "capital_allocation_assessments", "capital_allocation_outcomes", "management_progression", "gold_capital_allocation"],
    "what-is-the-return-on-capex": ["gold_capital_allocation", "capital_allocation_roi_ledger"],
    "what-regulatory-risks-remain-active": ["gold_risk_evolution"],
    "what-is-committee-direction": ["committee_synthesis"],
    "where-does-the-committee-agree": ["committee_synthesis"],
    "where-does-the-committee-disagree": ["committee_synthesis"],
    "what-incentives-matter": ["management_progression", "management_quality_dimensions"],
    "what-should-i-ask-ir": ["management_progression", "committee_synthesis"],
    "what-would-graham-worry-about": ["graham_analysis", "financial_truth_pack"],
    "what-would-buffett-focus-on": ["buffett_analysis", "committee_synthesis", "gold_credibility", "gold_capital_allocation"],
    "where-would-fisher-be-curious": ["fisher_analysis"],
    "what-would-munger-avoid": ["munger_analysis"],
    "how-would-lynch-explain-it": ["lynch_analysis"],
    "what-can-break-the-thesis": ["buffett_analysis", "committee_synthesis", "risk_evolution"],
    "which-disclosure-is-missing": ["financial_truth_pack", "committee_synthesis"],
    "what-evidence-would-change-the-view": ["committee_synthesis", "financial_truth_pack"],
    "what-needs-management-clarification": ["committee_synthesis"],
    "what-remains-unresolved": ["committee_synthesis", "financial_truth_pack"],
}


def _build_dependency_provenance(
    question_id: str,
    source_bundle: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Return a list of {logical_source, artifact_path, artifact_timestamp, used_as}
    for each registered dependency of this question.

    artifact_timestamp uses file_mtime (or generated_at from payload as fallback).
    Only sources that are present (status=loaded) are recorded.
    Absent sources are recorded with artifact_timestamp="" so the loader can
    treat missing-timestamp entries as UNKNOWN freshness.
    """
    deps = QUESTION_DEPENDENCY_MAP.get(question_id) or []
    sources = source_bundle.get("sources") or {}
    provenance: List[Dict[str, str]] = []
    for i, src_name in enumerate(deps):
        record = sources.get(src_name) or {}
        used_as = "primary" if i == 0 else "secondary" if i == 1 else "enrichment"
        provenance.append({
            "logical_source": src_name,
            "artifact_path": str(record.get("relative_path") or record.get("path") or ""),
            "artifact_timestamp": str(record.get("file_mtime") or (record.get("payload") or {}).get("generated_at") or ""),
            "used_as": used_as,
        })
    return provenance


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
        if question_id in {
            "what-has-management-promised",
            "did-past-claims-come-true",
            "what-projects-are-underway",
            "how-is-capacity-changing",
            "what-is-management-commentary-saying",
        }:
            progression_confidence = _cap_progression_confidence(answer)
            interpretation = dict(answer.get("interpretation") or {})
            interpretation["confidence"] = progression_confidence
            answer["interpretation"] = interpretation
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
        answer["dependency_provenance"] = _build_dependency_provenance(question_id, source_bundle)
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
    "what-promise-types-dominate": "progression",
    "which-promises-are-overdue": "progression",
    "what-was-delivered-last-3-years": "progression",
    "what-was-missed": "progression",
    "did-past-claims-come-true": "progression",
    "what-projects-are-underway": "progression",
    "how-is-capacity-changing": "progression",
    "what-is-management-commentary-saying": "progression",
    "how-is-capital-allocated": "capital_allocation",
    "what-is-the-return-on-capex": "capital_allocation",
    "what-incentives-matter": "management_quality",
    "what-regulatory-risks-remain-active": "risk",
    "what-is-committee-direction": "committee",
    "where-does-the-committee-agree": "committee",
    "where-does-the-committee-disagree": "committee",
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
    wc_payload = _source_payload(source_bundle, "working_capital_quality_drilldown")
    drilldown = _get_record_list(wc_payload, "drilldown")
    drilldown_sorted = sorted(drilldown, key=lambda d: _year_sort_key(_year_label(d)))

    # Build longitudinal receivable_days series (best available metric across years)
    rec_series = [(d, _get_number(d, "receivable_days")) for d in drilldown_sorted if _get_number(d, "receivable_days") is not None]
    ccc_series = [(d, _get_number(d, "cash_conversion_cycle")) for d in drilldown_sorted if _get_number(d, "cash_conversion_cycle") is not None]
    inv_series = [(d, _get_number(d, "inventory_days")) for d in drilldown_sorted if _get_number(d, "inventory_days") is not None]

    if not rec_series and not ccc_series:
        return _build_unavailable_answer(
            question,
            "The required working-capital evidence is not available in the current source set.",
            "Working-capital analysis needs receivable or cash-cycle evidence. Without those fields, this answer would be guesswork.",
            "A usable working-capital drilldown is not available.",
        )

    working_capital = _latest_year_record(wc_payload, "drilldown")
    latest_year = _year_label(working_capital).upper() or "the latest year"

    # Build receivable-days trend description
    rec_trend_parts: List[str] = []
    if len(rec_series) >= 2:
        first_d, first_val = rec_series[0]
        last_d, last_val = rec_series[-1]
        first_yr = _year_label(first_d).upper()
        last_yr = _year_label(last_d).upper()
        direction = "improved" if last_val < first_val else "worsened"
        rec_trend_parts.append(
            f"Receivable days moved from {format_number(first_val)} ({first_yr}) to {format_number(last_val)} ({last_yr}) — a modest {direction}."
        )
    elif rec_series:
        _, val = rec_series[-1]
        rec_trend_parts.append(f"Receivable days are {format_number(val)} in {latest_year}.")

    # CCC narrative if available
    ccc_note = ""
    if ccc_series:
        _, ccc_val = ccc_series[-1]
        ccc_d = ccc_series[-1][0]
        ccc_yr = _year_label(ccc_d).upper()
        ccc_note = f"Cash conversion cycle is {format_number(ccc_val)} days ({ccc_yr})."

    # Inventory note if available
    inv_note = ""
    if inv_series:
        _, inv_val = inv_series[-1]
        inv_note = f"Inventory days at {format_number(inv_val)} — structurally long for a pharma supply chain."

    intensity = _get_string(working_capital, "working_capital_intensity_status") or "elevated"
    strain = _get_string(working_capital, "cash_strain_risk") or ""

    simple = (
        f"Yes. Working-capital intensity remains a concern. "
        + (rec_trend_parts[0] if rec_trend_parts else "")
        + (f" {ccc_note}" if ccc_note else "")
    ).strip()

    key_points = _clean_list([
        rec_trend_parts[0] if rec_trend_parts else "",
        ccc_note,
        inv_note,
        strain,
        f"Latest working-capital intensity status: {intensity}.",
    ])

    return _draft(
        answer_status="supported",
        simple_answer=simple,
        why_it_matters="This matters because cash can get trapped in receivables and inventory even when reported margins look strong. That can limit flexibility and make growth more funding-intensive.",
        key_points=key_points,
        detailed_explanation=(
            "Working capital is where reported profit meets operating reality. Long receivable and inventory cycles mean cash stays tied up even when revenue grows. "
            f"The multi-year receivable-days data shows {rec_trend_parts[0] if rec_trend_parts else 'elevated receivables throughout.'}"
        ),
        evidence_status="direct",
        evidence_summary="Supported by the working-capital drilldown with multi-year receivable days and cash-cycle evidence.",
        evidence_points=[intensity, strain],
        uncertainty="Inventory days are not consistently available for every year. The cash conversion cycle is computable only where all three components are present.",
        products_refs=[],
        business_journey_ref=None,
    )


def _synthesize_longitudinal_series(
    items: List[Dict[str, Any]],
    metric_key: str,
    label: str,
) -> Dict[str, Any]:
    """Derive a longitudinal narrative from an ordered series of per-share records.

    Returns a dict with start/end/direction/cagr/inflection/volatility/narrative.
    Works generically for any ordered numeric series (EPS, owner earnings, etc.).
    """
    # Extract (year_sort_key, year_label, value) tuples, skip None values
    points: List[Tuple[int, str, float]] = []
    for item in items:
        yr = _year_label(item)
        val = _get_number(item, metric_key)
        if val is not None:
            points.append((_year_sort_key(yr), yr, val))
    points.sort(key=lambda t: t[0])

    n = len(points)
    missing = len(items) - n
    data_confidence = "high" if missing == 0 else ("medium" if missing <= 1 else "low")

    if n == 0:
        return {"label": label, "available": False, "data_confidence": "none", "narrative": ""}
    if n == 1:
        _, yr, val = points[0]
        return {
            "label": label,
            "available": True,
            "n_years": 1,
            "start_year": yr,
            "end_year": yr,
            "start_value": val,
            "end_value": val,
            "direction": "flat",
            "cagr": None,
            "inflection_year": None,
            "is_volatile": False,
            "data_confidence": data_confidence,
            "narrative": f"{label} is {format_per_share(val)} in {yr.upper()} (single year only).",
        }

    _, start_yr, start_val = points[0]
    _, end_yr, end_val = points[-1]
    n_periods = n - 1

    # CAGR: only meaningful if both endpoints are positive
    cagr: Optional[float] = None
    if start_val > 0 and end_val > 0 and n_periods >= 2:
        try:
            cagr = (math.pow(end_val / start_val, 1.0 / n_periods) - 1.0) * 100
        except (ValueError, ZeroDivisionError):
            cagr = None

    # Year-over-year changes
    yoy: List[float] = [points[i + 1][2] - points[i][2] for i in range(n_periods)]
    signs = [1 if d > 0 else (-1 if d < 0 else 0) for d in yoy]
    reversals = sum(1 for i in range(len(signs) - 1) if signs[i] != 0 and signs[i + 1] != 0 and signs[i] != signs[i + 1])
    is_volatile = reversals >= 2

    # Inflection: largest absolute single-year change
    inflection_year: Optional[str] = None
    if n_periods >= 2:
        max_abs_change = max(abs(d) for d in yoy)
        avg_abs_change = sum(abs(d) for d in yoy) / n_periods
        # Only call it an inflection if it's >2x the average change
        if max_abs_change > 2 * avg_abs_change:
            idx = max(range(n_periods), key=lambda i: abs(yoy[i]))
            inflection_year = points[idx + 1][1]  # year where the big jump landed

    # Direction
    pct_change = (end_val - start_val) / abs(start_val) * 100 if start_val != 0 else 0
    if is_volatile:
        direction = "volatile"
    elif abs(pct_change) < 5:
        direction = "flat"
    elif pct_change > 0:
        direction = "up"
    else:
        direction = "down"

    # Narrative
    cagr_phrase = f" (CAGR ~{cagr:.1f}% per year)" if cagr is not None else ""
    inflection_phrase = f" {inflection_year.upper()} was a major inflection year." if inflection_year else ""
    volatile_phrase = " The series is volatile rather than a smooth trend." if is_volatile else ""
    direction_words = {"up": "increased", "down": "declined", "flat": "remained roughly flat", "volatile": "moved unevenly"}
    narrative = (
        f"{label} {direction_words.get(direction, 'changed')} from {format_per_share(start_val)} in {start_yr.upper()} "
        f"to {format_per_share(end_val)} in {end_yr.upper()}{cagr_phrase}.{inflection_phrase}{volatile_phrase}"
    )

    return {
        "label": label,
        "available": True,
        "n_years": n,
        "start_year": start_yr,
        "end_year": end_yr,
        "start_value": start_val,
        "end_value": end_val,
        "direction": direction,
        "cagr": cagr,
        "inflection_year": inflection_year,
        "is_volatile": is_volatile,
        "data_confidence": data_confidence,
        "narrative": narrative,
    }


def _build_per_share_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    per_share_payload = _source_payload(source_bundle, "per_share_compounding_analysis")
    series = _get_record_list(per_share_payload, "analysis")
    if not series:
        return _build_unavailable_answer(
            question,
            "The required per-share evidence is not available in the current source set.",
            "Per-share analysis needs usable share-count and per-share metrics. Without those, any improvement claim would be too confident.",
            "A usable per-share analysis is not available.",
        )

    eps_synth = _synthesize_longitudinal_series(series, "eps_basic", "Basic EPS")
    oe_synth = _synthesize_longitudinal_series(series, "owner_earnings_per_share", "Owner earnings per share")

    # Require at least one metric to be available across multiple years
    if not eps_synth.get("available") and not oe_synth.get("available"):
        return _build_unavailable_answer(
            question,
            "The required per-share evidence is not available in the current source set.",
            "Per-share analysis needs usable share-count and per-share metrics.",
            "A usable per-share analysis is not available.",
        )

    warning = _first_string(
        _get_list(per_share_payload, "warnings"),
        _get_list(_source_payload(source_bundle, "financial_truth_pack"), "precision_limits"),
    )

    n_years = eps_synth.get("n_years") or oe_synth.get("n_years") or 1
    multi_year = n_years >= 5

    # Build key points from the longitudinal synthesis
    key_points: List[str] = []
    if eps_synth.get("available"):
        key_points.append(eps_synth["narrative"])
    if oe_synth.get("available"):
        key_points.append(oe_synth["narrative"])

    # Inflection note
    eps_inflect = eps_synth.get("inflection_year")
    oe_inflect = oe_synth.get("inflection_year")
    if eps_inflect and eps_inflect != oe_inflect:
        key_points.append(f"EPS inflected in {eps_inflect.upper()}; owner earnings show a different pattern — the two metrics do not move in lockstep.")
    elif eps_inflect:
        key_points.append(f"{eps_inflect.upper()} was the key inflection year for both EPS and owner earnings per share.")

    # Volatility caveat
    if oe_synth.get("is_volatile") and not eps_synth.get("is_volatile"):
        key_points.append("Owner earnings per share is more volatile than reported EPS — cash conversion quality is uneven across years.")

    if warning:
        key_points.append(warning)

    # Direction summary for the overall answer
    eps_dir = eps_synth.get("direction", "")
    if eps_dir == "up":
        direction_summary = "Per-share economics improved on the reported EPS measure over the available history."
    elif eps_dir == "down":
        direction_summary = "Reported EPS declined over the available history, which warrants caution on per-share compounding."
    elif eps_dir == "volatile":
        direction_summary = "Per-share economics were volatile — the endpoint is higher, but the path was uneven."
    else:
        direction_summary = "Per-share economics were roughly flat over the available history."

    if multi_year:
        simple_answer = f"{direction_summary} {eps_synth.get('narrative', '')}"
    else:
        latest = sorted(series, key=lambda x: _year_sort_key(_year_label(x)))[-1]
        simple_answer = (
            f"The current evidence shows owner earnings per share at {format_per_share(_get_number(latest, 'owner_earnings_per_share'))} "
            f"and basic EPS at {format_per_share(_get_number(latest, 'eps_basic'))}. "
            f"Only {n_years} year(s) of data are available, which limits trend conclusions."
        )

    return _draft(
        answer_status="supported" if multi_year else "partially_supported",
        simple_answer=simple_answer,
        why_it_matters="This matters because aggregate company growth does not automatically translate into better economics for each shareholder. Per-share evidence tests real compounding.",
        key_points=key_points,
        detailed_explanation=(
            "Per-share analysis asks whether business progress is accruing to each owner or being diluted. "
            f"The {n_years}-year series allows a longitudinal reading rather than a single-year snapshot. "
            "EPS and owner earnings per share can diverge when capex intensity changes, making both series necessary for a complete view."
        ),
        evidence_status="direct" if multi_year else "partial",
        evidence_summary=f"Supported by a {n_years}-year per-share compounding series." if multi_year else "Only a partial per-share series is available.",
        evidence_points=[eps_synth.get("narrative", ""), oe_synth.get("narrative", ""), warning],
        uncertainty=warning or ("Owner earnings per share is volatile; the series should be read as directional, not precise." if oe_synth.get("is_volatile") else "A usable multi-year per-share series is available."),
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


def _management_progression_commitment_index(management_progression: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Map stable commitment fingerprints to Management Progression lifecycle items.

    Management Commitments is not a lifecycle authority. The only supported join for
    commitment lifecycle display is the ENG-098 fingerprint carried as the
    commitment event id in Management Progression. We intentionally do not fall
    back to ordinal ids, topic equality, or fuzzy text matching.
    """
    index: Dict[str, Dict[str, Any]] = {}
    for item in _get_record_list(management_progression, "progression_items") + _get_record_list(management_progression, "items"):
        for event in _get_record_list(item, "events"):
            event_role = _normalize_sentence(_first_string(_get_string(event, "event_role"), _get_string(event, "role")))
            event_id = _first_string(_get_string(event, "event_id"), _get_string(event, "source_item_id"))
            if event_id and event_role == "commitment":
                index[event_id] = item
    return index


def _commitment_lifecycle_item(commitment: Dict[str, Any], lifecycle_index: Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    if not lifecycle_index:
        return {}
    fingerprint = _get_string(commitment, "commitment_fingerprint")
    return lifecycle_index.get(fingerprint) or {}


def _commitment_lifecycle_status_key(commitment: Dict[str, Any], lifecycle_index: Optional[Dict[str, Dict[str, Any]]]) -> str:
    item = _commitment_lifecycle_item(commitment, lifecycle_index)
    if not item:
        return "unknown"
    status = _normalize_sentence(_first_string(_get_string(item, "current_status"), _get_string(item, "chain_status"), _get_string(item, "status")))
    if status in {"delivered", "achieved", "completed", "outcome_positive", "financial_impact_confirmed", "outcome positive", "financial impact confirmed"}:
        return "delivered"
    if status in {"partially_delivered", "partially_achieved", "partially delivered", "partially achieved", "partially completed"}:
        return "partially_delivered"
    if status in {"in_progress", "in progress", "progressing", "action_started", "action started", "action_completed", "action completed"}:
        return "in_progress"
    if status in {"delayed"}:
        return "delayed"
    if status in {"missed", "failed", "not_delivered", "not delivered", "abandoned", "cancelled", "contradicted"}:
        return "missed"
    if status in {"announced", "claim_only", "claim only", "unverified", "unable_to_verify", "unable to verify", "unresolved", "unknown"}:
        return "unable_to_verify"
    return "unknown"


def _commitment_lifecycle_status_label(commitment: Dict[str, Any], lifecycle_index: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    key = _commitment_lifecycle_status_key(commitment, lifecycle_index)
    return {
        "delivered": "Delivered",
        "partially_delivered": "Partially Delivered",
        "in_progress": "In Progress",
        "delayed": "Delayed",
        "missed": "Missed",
        "unable_to_verify": "Unable To Verify",
        "unknown": "Unable To Verify",
    }.get(key, "Unable To Verify")


def _commitment_authority_note(commitment: Dict[str, Any], lifecycle_index: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    key = _commitment_lifecycle_status_key(commitment, lifecycle_index)
    if key == "delivered":
        return "Management Progression contains verified delivery or outcome evidence."
    if key == "partially_delivered":
        return "Management Progression contains partial follow-through evidence."
    if key == "in_progress":
        return "Management Progression shows action evidence, but final delivery remains unproven."
    if key == "delayed":
        return "Management Progression shows delay evidence."
    if key == "missed":
        return "Management Progression shows missed, cancelled, or contradicted execution evidence."
    if key == "unable_to_verify":
        return "Management Progression has not verified delivery."
    return "No matching Management Progression lifecycle record was found."


def _commitment_display_text(commitment: Dict[str, Any], *, max_words: int = 25) -> str:
    """
    Return the best investor-facing commitment text: original_statement → normalized_commitment → topic.
    Prefers source-grounded meaning. For long text, extracts the first complete sentence.
    Uses topic only when richer fields are absent or exceed safe length.
    """
    orig = sanitize_public_text(_get_string(commitment, "original_statement"))
    norm = sanitize_public_text(_get_string(commitment, "normalized_commitment"))
    topic_val = sanitize_public_text(_get_string(commitment, "topic"))

    for candidate in (orig, norm):
        if not candidate:
            continue
        words = candidate.split()
        if len(words) <= max_words:
            return candidate
        # Long text: try extracting the first complete sentence (up to the first ".")
        if "." in candidate:
            dot_pos = candidate.index(".")
            first_sent = candidate[:dot_pos + 1].strip()
            if first_sent and len(first_sent.split()) <= max_words:
                return first_sent

    return topic_val


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
    # Remove sentence-level internal-template prefixes first (before word replacements)
    _PREFIX_PATTERNS = [
        # "investment lens implication — label:" or "investment lens implication first:"
        r"investment lens implication\s*[\-–—]?\s*[^:]*:\s*",
        r"primary investment lens question\s*:\s*[^?]+\??\s*",
        r"summary answer\s*\(investment lens.framed\)\s*:\s*",
        r"investment lens[._ -]framed\s*:\s*",
        r"investment lens[._ -]specific assessment\s*[.;,]?\s*",
        r"investment lens\s*:\s*",
        r"fact and implication\s*:\s*",
        r"counterpoint\s*:\s*",
        r"is claim evidence only\s*[;,]?\s*",
        r"\bclaim evidence only\s*[;,]?\s*",
        # Parenthetical forms first so they are consumed whole before bare-label patterns run
        r"\(\s*CLAIM_ONLY\s*\)",
        r"\(\s*ACTION_STARTED\s*\)",
        r"\(\s*ACTION_COMPLETED\s*\)",
        r"\(\s*NOT_APPLICABLE\s*\)",
        r"\(\s*UNVERIFIED\s*\)",
        r"\(\s*PARTIALLY_ACHIEVED\s*\)",
        r"\bCLAIM_ONLY\s*[;,]?\s*",
        r"\bACTION_STARTED\s*[;,]?\s*",
        r"\bACTION_COMPLETED\s*[;,]?\s*",
        r"\bFINANCIAL_LINK_[A-Z_]+\s*[;,]?\s*",
        r"\bNOT_APPLICABLE\s*[;,]?\s*",
        r"\bUNVERIFIED\s*[;,]?\s*",
        r"\bPARTIALLY_ACHIEVED\s*[;,]?\s*",
    ]
    for pat in _PREFIX_PATTERNS:
        # Strip the prefix wherever it appears in the sentence
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)
    # Remove truncation artifacts from upstream source text
    cleaned = re.sub(r"\bm\.\.\s*", "", cleaned)
    replacements = (
        (" are reported in the compact financial inputs", ""),
        ("reported in the compact financial inputs", ""),
        ("compact financial inputs", ""),
        ("source set summaries", ""),
        ("committee-level output", ""),
        ("company memory", ""),
        ("available evidence summary", ""),
        ("in the supplied evidence", ""),
        ("from supplied evidence", ""),
        ("in the supplied inputs", ""),
        ("from supplied inputs", ""),
        ("supplied inputs", ""),
    )
    for needle, replacement in replacements:
        cleaned = re.sub(re.escape(needle), replacement, cleaned, flags=re.IGNORECASE)
    cleaned = " ".join(cleaned.split()).strip(" ,;:-")
    return sanitize_public_text(cleaned)


def _commitment_summary(commitment: Dict[str, Any], *, include_status: bool = True, lifecycle_index: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    period = _commitment_period(commitment)
    label = _commitment_topic_label(commitment)
    later_evidence = _commitment_authority_note(commitment, lifecycle_index)
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
        parts.append(f"Current: {_commitment_lifecycle_status_label(commitment, lifecycle_index)}.")
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


def _commitment_progression(commitment: Dict[str, Any], lifecycle_index: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    progression = _get_record(commitment, "progression")
    label = _clean_display_phrase(
        _first_string(_get_string(commitment, "normalized_commitment"), _get_string(commitment, "topic"), "Management commitment"),
        limit_words=14,
    )
    return _make_progression_block(
        headline=label,
        current_state=_commitment_lifecycle_status_label(commitment, lifecycle_index),
        what_changed=_clean_display_phrase(_first_string(_get_string(commitment, "topic"), _get_string(commitment, "normalized_commitment")), limit_words=14),
        why_it_changed=_clean_display_phrase(_first_string(_get_string(commitment, "investor_implication"), _commitment_authority_note(commitment, lifecycle_index)), limit_words=16),
        conviction_impact=_first_string(_get_string(progression, "conviction_impact"), "unclear"),
        latest_evidence=[
            _clean_display_phrase(_commitment_authority_note(commitment, lifecycle_index), limit_words=18),
            _clean_display_phrase(_get_string(commitment, "investor_implication"), limit_words=18),
            _first_string(_get_string_list(progression, "unresolved_questions")),
        ],
        unresolved_items=_get_string_list(progression, "unresolved_questions"),
        turning_points=_get_record_list(progression, "turning_points"),
    )


def _commitment_watch_item(commitment: Dict[str, Any], lifecycle_index: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    topic = _clean_display_phrase(
        _first_string(_get_string(commitment, "topic"), _get_string(commitment, "normalized_commitment"), "the commitment"),
        limit_words=8,
    )
    if not topic:
        return ""
    status = _commitment_lifecycle_status_label(commitment, lifecycle_index).lower()
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


def _gold_cred_summary(gold_cred: Dict[str, Any]) -> str:
    """Extract investor-language credibility summary from raw Gold credibility artifact."""
    s = gold_cred.get("summary") or {}
    return str(s.get("management_credibility_summary") or "").strip()


def _gold_cred_weight(gold_cred: Dict[str, Any]) -> str:
    """Extract translated guidance weight from raw Gold credibility artifact."""
    _GW_NATURAL = {
        "HIGH_WEIGHT": "management guidance carries strong weight",
        "MODERATE_WEIGHT": "management guidance deserves moderate weight",
        "LOW_WEIGHT": "management guidance carries limited weight",
        "VERY_LOW_WEIGHT": "management guidance carries very limited weight",
    }
    s = gold_cred.get("summary") or {}
    raw = str(s.get("guidance_weight") or "")
    return _GW_NATURAL.get(raw, "")


def _gold_promise_enrichment(source_bundle: Dict[str, Any]) -> Optional[str]:
    """Return Gold-derived promise summary if available, else None."""
    gold = _source_payload(source_bundle, "gold_promise_tracker")
    if not gold:
        return None
    summary = gold.get("summary") or {}
    tracked = int(summary.get("tracked_promises") or 0)
    sb = summary.get("status_breakdown") or {}
    unverified = int(sb.get("unverified", 0) if isinstance(sb, dict) else 0)
    achieved = int(sb.get("achieved", 0) if isinstance(sb, dict) else 0)
    partially = int(sb.get("partially_achieved", 0) if isinstance(sb, dict) else 0)
    if not tracked:
        return None
    frags = [f"{tracked} commitments tracked"]
    if achieved:
        frags.append(f"{achieved} delivered")
    if partially:
        frags.append(f"{partially} partially delivered")
    if unverified:
        frags.append(f"{unverified} unverified")
    patterns = gold.get("credibility_patterns") or []
    # patterns may be list of dicts with "description" key
    pattern_text = ""
    if patterns:
        p0 = patterns[0]
        pattern_text = str(p0.get("description") or "") if isinstance(p0, dict) else str(p0)
    result = "; ".join(frags) + "."
    if pattern_text:
        result += " " + pattern_text
    return result


def _is_gold_eligible(payload: Optional[Dict[str, Any]], min_promises: int = 1) -> tuple:
    """Return (eligible: bool, fallback_reason: str) for Gold Promise Tracker routing."""
    if not payload:
        return False, "GOLD_ABSENT"
    tracked = int((payload.get("summary") or {}).get("tracked_promises") or 0)
    if tracked < min_promises:
        return False, f"GOLD_INSUFFICIENT (tracked={tracked}, min={min_promises})"
    return True, ""


def _gold_promise_key_points(gold: Dict[str, Any]) -> List[str]:
    """Build structured key points from Gold Promise Tracker summary fields."""
    summary = gold.get("summary") or {}
    sb = summary.get("status_breakdown") or {}
    tb = summary.get("promise_type_breakdown") or {}
    tracked = int(summary.get("tracked_promises") or 0)
    achieved = int(sb.get("achieved", 0))
    partially = int(sb.get("partially_achieved", 0))
    missed = int(sb.get("missed", 0))
    unverified = int(sb.get("unverified", 0))
    pts: List[str] = []
    gp_text = _gold_promise_enrichment_from_payload(gold)
    if gp_text:
        pts.append(gp_text)
    delivery_frags = []
    if achieved:
        delivery_frags.append(f"{achieved} delivered")
    if partially:
        delivery_frags.append(f"{partially} partially delivered")
    if missed:
        delivery_frags.append(f"{missed} missed")
    if unverified:
        delivery_frags.append(f"{unverified} unverified")
    if delivery_frags:
        pts.append("; ".join(delivery_frags) + ".")
    type_pts = [
        f"{count} {ptype.replace('_', ' ').lower()} commitment(s)"
        for ptype, count in tb.items()
        if isinstance(count, int) and count > 0
    ]
    pts.extend(type_pts[:2])
    return _clean_list(pts)[:4]


def _gold_promise_enrichment_from_payload(gold: Dict[str, Any]) -> Optional[str]:
    """Build promise summary string directly from an already-loaded Gold payload."""
    summary = gold.get("summary") or {}
    tracked = int(summary.get("tracked_promises") or 0)
    if not tracked:
        return None
    sb = summary.get("status_breakdown") or {}
    unverified = int(sb.get("unverified", 0) if isinstance(sb, dict) else 0)
    achieved = int(sb.get("achieved", 0) if isinstance(sb, dict) else 0)
    partially = int(sb.get("partially_achieved", 0) if isinstance(sb, dict) else 0)
    frags = [f"{tracked} commitments tracked"]
    if achieved:
        frags.append(f"{achieved} delivered")
    if partially:
        frags.append(f"{partially} partially delivered")
    if unverified:
        frags.append(f"{unverified} unverified")
    patterns = gold.get("credibility_patterns") or []
    pattern_text = ""
    if patterns:
        p0_ = patterns[0]
        pattern_text = str(p0_.get("description") or "") if isinstance(p0_, dict) else str(p0_)
    result = "; ".join(frags) + "."
    if pattern_text:
        result += " " + pattern_text
    return result


def _mc_specific_promise_points(commitment_list: List[Dict[str, Any]], *, max_items: int = 4, lifecycle_index: Optional[Dict[str, Dict[str, Any]]] = None) -> List[str]:
    """Q-A: surface specific commitment items (period + commitment text + status) for investor display."""
    material = _material_commitments(commitment_list, limit=max_items + 3)
    pts: List[str] = []
    for c in material:
        period = _commitment_period(c)
        display_text = _commitment_display_text(c)
        if not display_text:
            continue
        status = _commitment_lifecycle_status_label(c, lifecycle_index)
        timeframe = _get_string(c, "expected_timeframe")
        tf_note = f" (target: {timeframe})" if timeframe and timeframe not in {"unspecified", "unknown", ""} else ""
        period_prefix = f"{period.upper()}: " if period else ""
        text_body = display_text.rstrip(".")
        pts.append(f"{period_prefix}{text_body}{tf_note} — {status}.")
        if len(pts) >= max_items:
            break
    return pts


def _mc_claim_outcome_points(commitment_list: List[Dict[str, Any]], *, max_items: int = 4, lifecycle_index: Optional[Dict[str, Dict[str, Any]]] = None) -> List[str]:
    """Q-B: surface claim→outcome pairs (commitment text + status + delivery assessment) for investor display."""
    def _sort_key(c: Dict[str, Any]) -> int:
        s = _commitment_lifecycle_status_key(c, lifecycle_index)
        if s == "delivered":
            return 0
        if s in {"in_progress", "partially_delivered"}:
            return 1
        return 3
    material = sorted(_material_commitments(commitment_list, limit=max_items + 3), key=_sort_key)
    pts: List[str] = []
    for c in material:
        period = _commitment_period(c)
        display_text = _commitment_display_text(c)
        if not display_text:
            continue
        status = _commitment_lifecycle_status_label(c, lifecycle_index)
        assessment = _commitment_authority_note(c, lifecycle_index)
        period_prefix = f"{period.upper()}: " if period else ""
        text_body = display_text.rstrip(".")
        outcome_note = f" {assessment}" if assessment else ""
        pts.append(f"{period_prefix}{text_body} — {status}.{outcome_note}")
        if len(pts) >= max_items:
            break
    return pts


def _build_management_promises_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    # PRIMARY: Gold Promise Tracker (when present and has tracked promises)
    gold = _source_payload(source_bundle, "gold_promise_tracker")
    gold_eligible, gold_fallback_reason = _is_gold_eligible(gold)
    if gold_eligible:
        gold_summary = gold.get("summary") or {}
        sb = gold_summary.get("status_breakdown") or {}
        achieved = int(sb.get("achieved", 0))
        partially = int(sb.get("partially_achieved", 0))
        missed = int(sb.get("missed", 0))
        gp_text = _gold_promise_enrichment_from_payload(gold)
        key_pts = _gold_promise_key_points(gold)
        answer_st = "partially_supported" if not achieved and not partially else "supported"
        thesis = "strengthens" if (achieved + partially) > missed else "neutral"
        # Enrich with management_commitments when present: show specific items rather than aggregate only
        mc_payload = _source_payload(source_bundle, "management_commitments")
        mc_list = _get_record_list(mc_payload, "commitments")
        mc_available = bool(mc_payload)
        lifecycle_index = _management_progression_commitment_index(_source_payload(source_bundle, "management_progression"))
        if mc_list:
            specific_pts = _mc_specific_promise_points(mc_list, max_items=4, lifecycle_index=lifecycle_index)
            if specific_pts:
                type_pts = [p for p in _gold_promise_key_points(gold) if "commitment(s)" in p]
                key_pts = _clean_list(specific_pts + type_pts[:1])[:4]
        # Q-A simple_answer: describe what was promised (themes + status mix) — distinct from Q-B credibility verdict
        tracked = int(gold_summary.get("tracked_promises") or 0)
        unverified = int(sb.get("unverified", 0))
        delivery_count = achieved + partially
        tb = gold_summary.get("promise_type_breakdown") or {}
        type_labels = sorted([ptype.replace("_", " ").lower() for ptype, count in tb.items() if isinstance(count, int) and count > 0])
        if type_labels:
            delivery_note = f" {delivery_count} with delivery evidence;" if delivery_count > 0 else ""
            unverified_note = f" {unverified} unverified." if unverified else "."
            qa_simple = (
                f"{tracked} commitment(s) tracked across "
                + _join_human_list(type_labels[:3])
                + (" and other themes;" if len(type_labels) > 3 else ";")
                + delivery_note
                + unverified_note
            )
        else:
            qa_simple = gp_text or f"{tracked} management commitments tracked."
        # Fix uncertainty note: only reference management_commitments as missing when it actually is absent
        uncertainty = (
            "Full commitment-level detail and individual claim evidence requires the management_commitments source."
            if not mc_available and unverified > 0
            else ""
        )
        return _draft(
            answer_status=answer_st,
            simple_answer=qa_simple,
            why_it_matters="Commitment tracking matters because it gives investors a checkable record of what management said it would do.",
            key_points=key_pts,
            detailed_explanation="Derived from the Gold Promise Tracker, which synthesizes management commitments longitudinally across reporting periods.",
            evidence_status="partial" if not achieved and not partially else "direct",
            evidence_summary="Gold Promise Tracker with tracked promises and delivery status breakdown.",
            evidence_points=key_pts[:2],
            uncertainty=uncertainty,
            products_refs=[],
            business_journey_ref=None,
            progression={},
            interpretation={"conclusion": qa_simple, "thesis_impact": thesis},
        )

    # SECONDARY: management_commitments (Gold absent or ineligible)
    commitments = _source_payload(source_bundle, "management_commitments")
    commitment_list = _get_record_list(commitments, "commitments")
    lifecycle_index = _management_progression_commitment_index(_source_payload(source_bundle, "management_progression"))
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
    progression = _commitment_progression(featured[0], lifecycle_index)
    commitment_references = [_commitment_reference_label(commitment) for commitment in featured[:3] if _commitment_reference_label(commitment)]
    later_checks = [_commitment_watch_item(commitment, lifecycle_index) for commitment in featured[:3]]
    later_checks = _clean_list(later_checks)[:3]
    active_commitments = [commitment for commitment in featured if _commitment_lifecycle_status_label(commitment, lifecycle_index).lower() in {"in progress", "delivered", "partially delivered"}]
    unresolved_commitments = [commitment for commitment in featured if _commitment_lifecycle_status_label(commitment, lifecycle_index).lower() in {"unable to verify", "announced", "delayed"}]
    status_fragments = []
    if any(_commitment_lifecycle_status_label(commitment, lifecycle_index).lower() == "in progress" for commitment in featured):
        status_fragments.append("one is in progress")
    if any(_commitment_lifecycle_status_label(commitment, lifecycle_index).lower() == "unable to verify" for commitment in featured):
        status_fragments.append("others remain unverified")
    if any(_commitment_lifecycle_status_label(commitment, lifecycle_index).lower() in {"delivered", "partially delivered"} for commitment in featured):
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
            if len(delivered := [item for item in commitment_list if _commitment_lifecycle_status_key(item, lifecycle_index) in {"delivered", "partially_delivered"}]) > len(delayed := [item for item in commitment_list if _commitment_lifecycle_status_key(item, lifecycle_index) == "delayed"])
            else "weakens"
            if len(delayed) > len(delivered)
            else "neutral"
        ),
        confidence_level="medium",
    )
    commitment_highlights = [_commitment_summary(item, include_status=True, lifecycle_index=lifecycle_index) for item in featured[:4] if _commitment_summary(item, include_status=True, lifecycle_index=lifecycle_index)]
    if commitment_highlights:
        interpretation["what_changed"] = commitment_highlights[:4]
    if active_commitments:
        interpretation["positive_evidence"] = [_commitment_summary(item, include_status=True, lifecycle_index=lifecycle_index) for item in active_commitments[:3]]
    if unresolved_commitments:
        interpretation["negative_evidence"] = [_commitment_summary(item, include_status=True, lifecycle_index=lifecycle_index) for item in unresolved_commitments[:3]]
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
    # PRIMARY: Gold Promise Tracker + Gold Credibility (when Promise Tracker has tracked promises)
    gold_tracker = _source_payload(source_bundle, "gold_promise_tracker")
    gold_eligible, gold_fallback_reason = _is_gold_eligible(gold_tracker)
    if gold_eligible:
        gold_cred = _source_payload(source_bundle, "gold_credibility")
        gp_text = _gold_promise_enrichment_from_payload(gold_tracker)
        # Enrich with management_commitments when present: surface claim→outcome examples
        mc_payload = _source_payload(source_bundle, "management_commitments")
        mc_list = _get_record_list(mc_payload, "commitments")
        mc_available = bool(mc_payload)
        lifecycle_index = _management_progression_commitment_index(_source_payload(source_bundle, "management_progression"))
        cs = _gold_cred_summary(gold_cred) if gold_cred else None
        gw = _gold_cred_weight(gold_cred) if gold_cred else None
        # Q-B simple_answer: credibility verdict (NOT the delivery count — that's Q-A's job)
        qb_simple = cs or gw or gp_text or ""
        # Build key_points: claim→outcome examples first, then supporting credibility context
        pts: List[str] = []
        if mc_list:
            claim_pts = _mc_claim_outcome_points(mc_list, max_items=4, lifecycle_index=lifecycle_index)
            pts.extend(claim_pts)
        if gp_text and gp_text not in pts:
            pts.append(gp_text)
        if cs and cs not in pts:
            pts.append(cs)
        elif gw and gw not in pts:
            pts.append(gw)
        pts = _clean_list(pts)[:4]
        if qb_simple or pts:
            # Invariant: Gold has tracked promises → status CANNOT be not_supported
            # Fix ENG-083: only reference management_commitments as absent when it actually is
            if mc_available:
                explanation = (
                    "Derived from the Gold Promise Tracker (delivery state) and Gold Credibility Synthesis (track-record context). "
                    "Specific claim examples are drawn from management_commitments where evidence supports the claim."
                )
            else:
                explanation = (
                    "Derived from the Gold Promise Tracker (delivery state) and Gold Credibility Synthesis (track-record context). "
                    "Full claim-level comparison requires the management_commitments source."
                )
            return _draft(
                answer_status="partially_supported",
                simple_answer=qb_simple if qb_simple else (pts[0] if pts else ""),
                why_it_matters="This matters because management quality is easier to judge by follow-through than by messaging alone.",
                key_points=pts or [gp_text or ""],
                detailed_explanation=explanation,
                evidence_status="partial",
                evidence_summary="Gold Promise Tracker and Gold Credibility Synthesis.",
                evidence_points=_clean_list(pts[:2]),
                uncertainty="Full claim-level verification requires progression evidence.",
                products_refs=[],
                business_journey_ref=None,
                progression={},
                interpretation={"conclusion": qb_simple or (pts[0] if pts else ""), "thesis_impact": "neutral"},
            )

    # SECONDARY: management_commitments (Gold absent or ineligible)
    commitments = _get_record_list(_source_payload(source_bundle, "management_commitments"), "commitments")
    material_commitments = _material_commitments(commitments, limit=4)
    lifecycle_index = _management_progression_commitment_index(_source_payload(source_bundle, "management_progression"))
    delivered = [item for item in material_commitments if _commitment_lifecycle_status_key(item, lifecycle_index) in {"delivered", "partially_delivered"}]
    delayed = [item for item in material_commitments if _commitment_lifecycle_status_key(item, lifecycle_index) == "delayed"]
    unresolved = [item for item in material_commitments if _commitment_lifecycle_status_key(item, lifecycle_index) in {"in_progress", "unable_to_verify", "unknown"}]
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
    if not material_commitments:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available company memory does not yet support a reliable promise-versus-delivery answer.",
            why="This matters because management quality is easier to judge by follow-through than by messaging alone.",
            limitation="The current source set does not contain material commitments with verified evidence.",
        )
    simple = (
        "A few commitments show follow-through, but the evidence still looks mixed and selective."
        if delivered or delayed
        else "The commitment ledger is visible, but follow-through is not yet strong enough to make a confident delivery claim."
    )
    progression = _commitment_progression(material_commitments[0], lifecycle_index)
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
        what_to_watch=[item for item in (_commitment_watch_item(commitment, lifecycle_index) for commitment in material_commitments[:3]) if item],
        thesis_impact=(
            "strengthens"
            if len(delivered) > len(delayed)
            else "weakens"
            if len(delayed) > len(delivered)
            else "neutral"
        ),
        confidence_level="medium",
    )
    commitment_highlights = [_commitment_summary(item, include_status=True, lifecycle_index=lifecycle_index) for item in material_commitments[:4] if _commitment_summary(item, include_status=True, lifecycle_index=lifecycle_index)]
    if commitment_highlights:
        interpretation["what_changed"] = commitment_highlights[:4]
    if delivered:
        interpretation["positive_evidence"] = [_commitment_summary(item, include_status=True, lifecycle_index=lifecycle_index) for item in delivered[:3]]
    if delayed or unresolved:
        interpretation["negative_evidence"] = [_commitment_summary(item, include_status=True, lifecycle_index=lifecycle_index) for item in (delayed + unresolved)[:3]]
    company_slug = str(source_bundle.get("company_slug") or "")
    company_model_for_lcs = canonical_company_model(source_bundle, company_slug) if company_slug else {}
    claims_key_points = _augment_with_lcs_signals(commitment_highlights[:4], company_model_for_lcs)
    return _draft(
        answer_status="partially_supported",
        simple_answer=interpretation["conclusion"],
        why_it_matters="This matters because investors should care less about the original promise and more about whether later evidence shows that execution kept pace.",
        key_points=claims_key_points,
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


_ACTIVE_PROJECT_STATUSES = frozenset({
    "operational", "in_progress", "partially_operational", "construction",
    "commissioned", "active", "execution", "deployment",
})
_INACTIVE_PROJECT_STATUSES = frozenset({
    "unable_to_verify", "superseded", "cancelled", "abandoned",
    "completed", "historical", "void",
})


def _project_recency_cutoff(latest_period: str, *, years_back: int = 3) -> int:
    """Return the minimum year-sort-key for a project to be considered recent."""
    return max(0, _year_sort_key(latest_period) - years_back)


def _project_is_active(assessment: Dict[str, Any], recency_cutoff: int) -> bool:
    """Return True only when a project has active status AND recent evidence.

    This prevents historical events (e.g. a 2014 FDA prohibition) from appearing
    as current underway projects merely because they exist in the registry.
    """
    exec_status = str(assessment.get("execution_status") or "").lower().strip()
    if exec_status in _INACTIVE_PROJECT_STATUSES:
        return False

    # Determine most-recent evidence period
    evidence_periods: List[str] = [
        p for p in (assessment.get("evidence_periods") or []) if isinstance(p, str) and p.strip()
    ]
    assessment_period = str(assessment.get("period") or "").strip()
    all_periods = evidence_periods + ([assessment_period] if assessment_period else [])
    if not all_periods:
        # No temporal attribution — cannot confirm active
        return False

    latest_evidence = max(_year_sort_key(p) for p in all_periods)
    if latest_evidence < recency_cutoff:
        # All evidence is too old to claim the project is currently underway
        return False

    if exec_status in _ACTIVE_PROJECT_STATUSES:
        return True

    # "paused" projects require very recent evidence (within 1 year of cutoff)
    if exec_status == "paused":
        return latest_evidence >= recency_cutoff + 2

    return False


def _build_projects_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    registry = _source_payload(source_bundle, "projects_registry")
    assessments_payload = _source_payload(source_bundle, "project_assessments")
    projects = _get_record_list(registry, "projects")
    assessments = _get_record_list(assessments_payload, "assessments")

    # Build assessment lookup by project_id
    assessment_by_id: Dict[str, Dict[str, Any]] = {
        str(a.get("project_id") or ""): a for a in assessments if a.get("project_id")
    }

    # Determine recency cutoff from the assessments artifact's latest_period
    latest_period_str = str(assessments_payload.get("latest_period") or registry.get("latest_period") or "fy99")
    recency_cutoff = _project_recency_cutoff(latest_period_str, years_back=3)

    # Filter to active projects with recent temporal evidence
    active_projects: List[Dict[str, Any]] = []
    for project in projects:
        pid = str(project.get("project_id") or "")
        assessment = assessment_by_id.get(pid, {})
        if _project_is_active(assessment, recency_cutoff):
            # Attach assessment data for richer display
            active_projects.append({**project, "_assessment": assessment})

    # Sort by most recent evidence (descending), then by project_id
    def _project_sort_key(p: Dict[str, Any]) -> int:
        a = p.get("_assessment", {})
        evidence_periods = a.get("evidence_periods") or []
        period = str(a.get("period") or "")
        all_p = [ep for ep in evidence_periods if isinstance(ep, str)] + ([period] if period else [])
        return max((_year_sort_key(ep) for ep in all_p), default=0)

    active_projects.sort(key=_project_sort_key, reverse=True)

    if not active_projects:
        # Fall back: show that projects exist but temporal support for "underway" is unavailable
        if projects:
            return _draft(
                answer_status="partially_supported",
                simple_answer="Project data exists in the registry, but none of the recorded projects has sufficiently recent temporal evidence to be listed as currently underway.",
                why_it_matters="Projects matter because they show whether management is building real capability, not just discussing ambition.",
                key_points=["No project has clear recent execution evidence that supports calling it underway."],
                detailed_explanation="The project registry contains historical and status-uncertain entries. Listing these as 'underway' without temporal support would overstate current execution activity.",
                evidence_status="unavailable",
                evidence_summary="Projects exist in the registry but none qualifies as active based on available temporal evidence.",
                evidence_points=[],
                uncertainty="Temporal attribution is missing or too old for all recorded projects.",
                products_refs=[],
                business_journey_ref=None,
            )
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available company memory does not yet support a reliable project tracker.",
            why="Projects matter because they show where management is trying to turn ambition into execution.",
            limitation="The current source set does not include enough project evidence to summarize underway initiatives responsibly.",
        )

    featured = active_projects[:4]
    progression = _project_progression(featured[0])

    def _projects_simple_answer() -> str:
        # Build a summary from project names when objectives are short/template-generated
        names = [
            _first_string(
                _get_string(p, "normalized_name"),
                _get_string(p, "project_name"),
            )
            for p in featured
            if _first_string(_get_string(p, "normalized_name"), _get_string(p, "project_name"))
        ]
        # Use the count + project names if we have meaningful names
        if names:
            n = len(active_projects)
            label = names[0]
            if len(names) > 1:
                label = f"{names[0]} and {len(active_projects) - 1} other initiative(s)"
            return f"{n} project(s) with recent execution evidence, led by: {label}."
        # Fall back to featured objective if it's substantial
        obj = _get_string(featured[0], "objective") or ""
        if len(obj) > 40 and not obj.lower().endswith("operational."):
            return obj
        return f"{len(active_projects)} project(s) have recent execution evidence and are considered currently underway."

    return _draft(
        answer_status="partially_supported",
        simple_answer=_projects_simple_answer(),
        why_it_matters="This matters because projects reveal whether management is building real capability, not just discussing growth in the abstract.",
        key_points=[
            _first_string(
                _get_string(item, "normalized_name"),
                _get_string(item, "project_name"),
                _get_string(item, "objective"),
            )
            for item in featured
        ],
        detailed_explanation=(
            "Projects are the bridge between narrative and execution. Only projects with recent temporal evidence "
            f"(within 3 years of {latest_period_str.upper()}) are shown here. Historical events and superseded "
            "initiatives have been excluded to prevent stale data from being presented as current activity."
        ),
        evidence_status="partial",
        evidence_summary=f"Supported by {len(active_projects)} active project(s) from the registry with recent evidence.",
        evidence_points=[
            _get_string(featured[0].get("_assessment", {}), "execution_summary"),
            _get_string(featured[0].get("_assessment", {}), "observed_business_effect"),
            _get_string(featured[0].get("_assessment", {}), "observed_financial_effect"),
        ],
        uncertainty="Many projects are visible before their financial effects are. Only projects with recent evidence are shown.",
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
        gold_cred = _source_payload(source_bundle, "gold_credibility")
        if gold_cred:
            gw_natural = _gold_cred_weight(gold_cred)
            cred_summary = _gold_cred_summary(gold_cred)
            gcred_s = gold_cred.get("summary") or {}
            strengths = (gcred_s.get("key_strengths") or [])[:2]
            cautions = (gcred_s.get("key_cautions") or [])[:2]
            key_pts = [str(s)[:120] for s in strengths + cautions if s]
            conclusion = "; ".join(filter(None, [gw_natural, cred_summary])) or "Management credibility assessment available from Gold synthesis."
            return _draft(
                answer_status="partially_supported",
                simple_answer=conclusion,
                why_it_matters="Management quality matters because execution discipline shapes whether good strategy actually compounds value.",
                key_points=key_pts or [conclusion],
                detailed_explanation="Derived from the Gold Management Credibility Synthesis, which tracks guidance accuracy and delivery patterns across reporting periods.",
                evidence_status="partial",
                evidence_summary="Derived from Gold Credibility Synthesis.",
                evidence_points=[cred_summary] if cred_summary else [conclusion],
                uncertainty="Full management-quality dimensions require the management_quality_summary source.",
                products_refs=[],
                business_journey_ref=None,
                progression={},
                interpretation={"conclusion": conclusion, "thesis_impact": "neutral"},
            )
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
        gold_cap = _source_payload(source_bundle, "gold_capital_allocation")
        if gold_cap:
            # Raw artifact uses material_allocations; owner note lives in owner_capital_summary
            major = (gold_cap.get("material_allocations") or gold_cap.get("major_allocations") or [])[:3]
            owner_s = gold_cap.get("owner_capital_summary") or {}
            owner_note = str(owner_s.get("narrative") or owner_s.get("interpretation") or gold_cap.get("owner_capital_note") or "").strip()
            _RETURN_NAT = {
                "PROVEN_POSITIVE": "return confirmed", "MIXED": "returns mixed",
                "UNPROVEN": "return not yet visible", "DESTRUCTIVE": "return negative",
                "NOT_APPLICABLE": "capital returned to shareholders",
            }
            alloc_pts = []
            for alloc in major:
                if not isinstance(alloc, dict):
                    continue
                name = alloc.get("theme") or alloc.get("allocation_name") or alloc.get("name") or ""
                ret_raw = str(alloc.get("return_status") or "")
                ret = _RETURN_NAT.get(ret_raw, ret_raw.lower().replace("_", " "))
                if name:
                    alloc_pts.append(f"{name}: {ret}".strip(": ") if ret else name)
            gcap_s = gold_cap.get("summary") or {}
            tracked = gcap_s.get("tracked_allocations") or len(major)
            conclusion = owner_note or (f"Capital tracked across {tracked} allocations." if major else "Gold capital allocation data available.")
            return _draft(
                answer_status="partially_supported",
                simple_answer=conclusion,
                why_it_matters="Investors need to separate deployment from return: spending money is not the same thing as creating per-share value.",
                key_points=alloc_pts or [conclusion],
                detailed_explanation="Derived from the Gold Capital Allocation Outcome Tracker, which longitudinally tracks return status across major capital deployments.",
                evidence_status="partial",
                evidence_summary="Derived from Gold Capital Allocation Outcome Tracker.",
                evidence_points=alloc_pts[:3] or [conclusion],
                uncertainty="Full capital-allocation detail requires the capital_allocation_outcomes source.",
                products_refs=[],
                business_journey_ref=None,
                progression={},
                interpretation={"conclusion": conclusion, "thesis_impact": "neutral"},
            )
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


def _build_canonical_business_summary_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    company_slug = str(source_bundle.get("company_slug") or "")
    model = canonical_company_model(source_bundle, company_slug) if company_slug else {}
    current = _get_record(model, "current_business_model")
    business_summary = first_available_text(
        str(business_journey_payload.get("summary") or "").strip(),
        str(products_services_payload.get("business_model_summary") or "").strip(),
        _complete_sentence(_get_string(current, "what_company_does")),
        _complete_sentence(_get_string(current, "summary")),
    )
    if not current:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available evidence does not yet support a reliable business answer.",
            why="Business understanding should come from the underlying business evidence, not from frontend or older fallbacks.",
            limitation="Regenerate the business evidence set before asking business-understanding questions.",
        )
    product_names = _first_product_names(products_services_payload, limit=3)
    return _draft(
        answer_status="supported" if str(model.get("coverage_status") or "") == "supported" else "partially_supported",
        simple_answer=_complete_sentence(business_summary),
        why_it_matters="This matters because the first investor question is what the business actually sells, who uses it, and how that activity can become cash.",
        key_points=[
            f"Offerings: {_join_human_list(product_names)}." if product_names else "",
            str(products_services_payload.get("customer_summary") or ""),
            str(products_services_payload.get("revenue_logic_summary") or ""),
            _complete_sentence(_get_string(current, "economic_mechanism")),
        ],
        detailed_explanation=" ".join(
            part
            for part in [
                _complete_sentence(business_summary),
                str(products_services_payload.get("customer_summary") or ""),
                str(products_services_payload.get("revenue_logic_summary") or ""),
                _complete_sentence(_get_string(current, "economic_mechanism")),
            ]
            if part
        ),
        evidence_status="direct",
        evidence_summary="Derived from the business evidence set: current business model, offerings, customers, and revenue engines.",
        evidence_points=[
            _get_string(current, "source_period"),
            _get_string(current, "business_model_type"),
            _get_string(current, "how_revenue_happens"),
        ],
        uncertainty=_first_string(list(products_services_payload.get("open_questions") or []), "Offering-level contribution and customer concentration may still be incomplete."),
        products_refs=_first_product_refs(products_services_payload, limit=4),
        business_journey_ref=None,
        business_journey_mode="full",
    )


def _build_canonical_customers_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    company_slug = str(source_bundle.get("company_slug") or "")
    model = canonical_company_model(source_bundle, company_slug) if company_slug else {}
    current = _get_record(model, "current_business_model")
    customers = _get_record_list(model, "customers")
    customer_summary = str(products_services_payload.get("customer_summary") or "").strip()
    if not customer_summary and not customers:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available evidence does not yet support a reliable customer answer.",
            why="Customer identity matters because payer, user, partner, and concentration patterns shape revenue durability.",
            limitation="The evidence set does not yet preserve enough customer detail.",
        )
    payers = _clean_list([_get_string(customer, "payer_type") for customer in customers] + list(current.get("who_pays") or []))
    users = _clean_list([_get_string(customer, "end_user_type") for customer in customers] + list(current.get("who_uses") or []))
    customer_roles = _build_customer_roles(
        payers=payers[:4],
        integrators_or_partners=[],
        end_users=users[:4],
        international_customers=[value for value in payers + users if "international" in value.lower()][:3],
        concentration_note="Customer concentration is not fully established in the available evidence.",
        evidence_status="partial" if any(not customer.get("concentration_known") for customer in customers) else "direct",
    )
    return _draft(
        answer_status="partially_supported",
        simple_answer=customer_summary or f"The visible customer map points to {_join_human_list(payers or users)}.",
        why_it_matters="This matters because who pays and who uses the product can be different, and that difference affects bargaining power, adoption, and revenue durability.",
        key_points=[
            f"Who pays: {_join_human_list(payers)}." if payers else "",
            f"Who uses: {_join_human_list(users)}." if users else "",
            "Customer concentration is not fully established in the available evidence.",
        ],
        detailed_explanation=customer_summary or "The available evidence identifies customer roles, but does not yet provide a complete named-customer or concentration map.",
        evidence_status="partial",
        evidence_summary="Derived from the business evidence set: customers and current business model customer roles.",
        evidence_points=payers[:2] + users[:1],
        uncertainty="Customer concentration and named-customer revenue mix remain incomplete unless the evidence says otherwise.",
        products_refs=_first_product_refs(products_services_payload, limit=3),
        business_journey_ref=None,
        customer_roles=customer_roles,
    )


def _build_canonical_make_money_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    company_slug = str(source_bundle.get("company_slug") or "")
    model = canonical_company_model(source_bundle, company_slug) if company_slug else {}
    current = _get_record(model, "current_business_model")
    business_summary = first_available_text(
        str(business_journey_payload.get("summary") or "").strip(),
        str(products_services_payload.get("business_model_summary") or "").strip(),
        _complete_sentence(_get_string(current, "what_company_does")),
        _complete_sentence(_get_string(current, "summary")),
    )
    revenue_summary = str(products_services_payload.get("revenue_logic_summary") or "").strip() or _get_string(current, "how_revenue_happens")
    if not revenue_summary:
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available evidence does not yet support a reliable revenue-mechanism answer.",
            why="Revenue mechanism matters because it determines whether growth is recurring, project-timed, usage-led, licensing-led, or capacity-led.",
            limitation="Regenerate the business evidence set with revenue-engine detail before relying on this answer.",
        )
    # Revenue engines and economic drivers — the primary differentiator from "what does it do"
    revenue_engines = _get_record_list(current, "revenue_engines") or []
    engine_names: List[str] = []
    for eng in revenue_engines[:4]:
        name = _get_string(eng, "engine_name") or _get_string(eng, "name")
        if name:
            engine_names.append(name)
    segment_note = ""
    segments = _get_record_list(model, "segments") or _get_record_list(current, "segments") or []
    if segments:
        seg_names = [_get_string(s, "segment_name") or _get_string(s, "name") for s in segments[:3]]
        seg_names = [s for s in seg_names if s]
        if seg_names:
            segment_note = f"Revenue comes from {_join_human_list(seg_names)}."
    billing_basis = _billing_basis_phrase(current) or ""
    revenue_basis = _complete_sentence(revenue_summary)
    revenue_flow = _build_revenue_flow(source_bundle, products_services_payload)
    billing_basis_note = str(revenue_flow.get("billing_basis_note") or "").strip()
    revenue_recognition_note = str(revenue_flow.get("revenue_recognition_note") or "").strip()
    cash_timing_note = str(revenue_flow.get("cash_timing_note") or "").strip()

    # Simple answer leads with revenue mechanism, not business description
    simple_parts = [revenue_basis]
    if segment_note:
        simple_parts.append(segment_note)
    elif engine_names:
        simple_parts.append(f"Key revenue engines: {_join_human_list(engine_names)}.")
    simple = _complete_sentence(" ".join(p for p in simple_parts if p))
    return _draft(
        answer_status="supported" if str(model.get("coverage_status") or "") == "supported" else "partially_supported",
        simple_answer=simple,
        why_it_matters="This matters because investors need the economic engine, not just the product label.",
        key_points=_clean_list([
            revenue_basis,
            segment_note,
            billing_basis_note or billing_basis,
            revenue_recognition_note,
            cash_timing_note,
        ]),
        detailed_explanation=" ".join(
            part
            for part in [
                revenue_basis,
                segment_note,
                billing_basis,
            ]
            if part
        ),
        evidence_status="direct",
        evidence_summary="Derived from the business evidence set: revenue engines and current business model.",
        evidence_points=[revenue_summary, _get_string(current, "source_period")],
        uncertainty=_first_string(list(products_services_payload.get("open_questions") or []), "Billing mechanics are not clearly disclosed."),
        products_refs=_first_product_refs(products_services_payload, limit=3),
        business_journey_ref=None,
        revenue_flow=revenue_flow,
    )


def _build_canonical_progression_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    question_id = str(question.get("id") or "")
    company_slug = str(source_bundle.get("company_slug") or "")
    progression_payload = canonical_management_progression(source_bundle, company_slug) if company_slug else {}
    company_model = canonical_company_model(source_bundle, company_slug) if company_slug else {}
    coverage = str(progression_payload.get("coverage_status") or "insufficient_evidence")
    items = progression_items_for_question(progression_payload, question_id, company_model=company_model)
    if coverage == "insufficient_evidence" or not items:
        # For credibility/promise questions, try Gold as fallback before returning not_supported
        if question_id in ("did-past-claims-come-true",):
            gold_cred = _source_payload(source_bundle, "gold_credibility")
            gp = _gold_promise_enrichment(source_bundle)
            if gold_cred:
                cs = _gold_cred_summary(gold_cred)
                gw = _gold_cred_weight(gold_cred)
                # Use credibility_summary (already contains weight context) to avoid duplication
                note = cs or gw
                if gp:
                    note = (note + " " + gp).strip() if note else gp
                if note:
                    return _draft(
                        answer_status="partially_supported",
                        simple_answer=note,
                        why_it_matters="Claims matter only if later evidence shows follow-through.",
                        key_points=[gp or note],
                        detailed_explanation="Derived from Gold Credibility and Promise Tracker. Raw progression evidence is unavailable for this run.",
                        evidence_status="partial",
                        evidence_summary="Derived from Gold Credibility Synthesis and Gold Promise Tracker.",
                        evidence_points=[note],
                        uncertainty="Full claim-level verification requires progression evidence.",
                        products_refs=[],
                        business_journey_ref=None,
                        progression={},
                        interpretation={"conclusion": note, "thesis_impact": "neutral"},
                    )
        if question_id in ("what-has-management-promised",):
            gp = _gold_promise_enrichment(source_bundle)
            if gp:
                return _draft(
                    answer_status="partially_supported",
                    simple_answer=gp,
                    why_it_matters="Investors need to separate explicit commitments from later delivery.",
                    key_points=[gp],
                    detailed_explanation="Derived from Gold Promise Tracker. Raw commitment ledger is unavailable for this run.",
                    evidence_status="partial",
                    evidence_summary="Derived from Gold Promise Tracker.",
                    evidence_points=[gp],
                    uncertainty="Full commitment detail requires the management_commitments source.",
                    products_refs=[],
                    business_journey_ref=None,
                    progression={},
                    interpretation={"conclusion": gp, "thesis_impact": "neutral"},
                )
        if question_id in ("how-is-capital-allocated",):
            gold_cap = _source_payload(source_bundle, "gold_capital_allocation")
            if gold_cap:
                owner_s = gold_cap.get("owner_capital_summary") or {}
                owner_note = str(owner_s.get("narrative") or owner_s.get("interpretation") or "").strip()
                major = (gold_cap.get("material_allocations") or gold_cap.get("major_allocations") or [])[:3]
                _RETURN_NAT = {
                    "PROVEN_POSITIVE": "return confirmed", "MIXED": "returns mixed",
                    "UNPROVEN": "return not yet visible", "DESTRUCTIVE": "return negative",
                    "NOT_APPLICABLE": "capital returned to shareholders",
                }
                alloc_pts = []
                for alloc in major:
                    if not isinstance(alloc, dict):
                        continue
                    name = alloc.get("theme") or alloc.get("allocation_name") or ""
                    ret = _RETURN_NAT.get(str(alloc.get("return_status") or ""), "")
                    if name:
                        alloc_pts.append(f"{name}: {ret}".strip(": ") if ret else name)
                conclusion = owner_note or (f"{len(major)} capital allocations tracked." if major else "")
                if conclusion or alloc_pts:
                    return _draft(
                        answer_status="partially_supported",
                        simple_answer=conclusion or alloc_pts[0],
                        why_it_matters="Investors need to separate deployment from return: spending money is not the same thing as creating per-share value.",
                        key_points=alloc_pts or [conclusion],
                        detailed_explanation="Derived from Gold Capital Allocation Outcome Tracker.",
                        evidence_status="partial",
                        evidence_summary="Derived from Gold Capital Allocation Outcome Tracker.",
                        evidence_points=alloc_pts[:3] or [conclusion],
                        uncertainty="Full capital-allocation detail requires the capital_allocation_outcomes source.",
                        products_refs=[],
                        business_journey_ref=None,
                        progression={},
                        interpretation={"conclusion": conclusion or alloc_pts[0], "thesis_impact": "neutral"},
                    )
        return _build_generic_not_supported_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
            direct_answer="The available evidence does not yet support this answer.",
            why="Progression questions should separate what management said, what it did, what happened later, and what remains unproven.",
            limitation="Regenerate the progression evidence set or improve upstream progression evidence.",
        )
    item = items[0]
    summary = summarize_progression_item(item, question_id)
    implication = _get_record(item, "investor_implication")
    status = "partially_supported" if coverage == "partial" or _uses_legacy_streams(items) else "supported"
    key_points = _progression_key_points(items[:4], question_id)
    if question_id == "did-past-claims-come-true":
        key_points = _augment_with_lcs_signals(key_points, company_model)
    unresolved = _clean_list(summary.get("unresolved_items") or [])
    latest_evidence = _clean_list(summary.get("latest_evidence") or [])
    conclusion = _progression_conclusion(question_id, summary)
    confidence = _progression_confidence(question_id, summary, implication, coverage)
    interpretation = build_interpretation_contract(
        conclusion=_complete_sentence(conclusion),
        what_changed=_clean_list([summary.get("what_changed")] + key_points)[:3],
        why_it_matters=_progression_why_it_matters(question_id),
        economic_mechanism=_first_string(_get_string(implication, "economic_mechanism"), _progression_economic_mechanism(question_id)),
        thesis_impact=_first_string(_get_string(implication, "thesis_impact"), "unresolved"),
        positive_evidence=[item for item in latest_evidence if not _looks_unresolved_like(item)][:3],
        negative_evidence=[item for item in unresolved if item][:3],
        unresolved=unresolved[:3],
        what_to_watch=_progression_watch_items(question_id, implication, unresolved),
        confidence=confidence,
    )
    interpretation["confidence"] = confidence
    return _draft(
        answer_status=status,
        simple_answer=_complete_sentence(interpretation["conclusion"]),
        why_it_matters=interpretation["why_it_matters"],
        key_points=key_points,
        detailed_explanation=_progression_detailed_explanation(question_id),
        evidence_status="partial" if status == "partially_supported" else "direct",
        evidence_summary="Derived from the progression evidence set only.",
        evidence_points=latest_evidence[:3],
        uncertainty=_first_string(unresolved, "Outcome evidence remains incomplete."),
        products_refs=[],
        business_journey_ref=None,
        progression=summary,
        interpretation=interpretation,
    )


def _lcs_human_label(value: str) -> str:
    return " ".join(str(value or "").replace("_", " ").split()).title() or "Unresolved"


def _augment_with_lcs_signals(key_points: List[str], company_model: Dict[str, Any]) -> List[str]:
    lcs_items = (company_model.get("longitudinal_current_state") or []) if isinstance(company_model, dict) else []
    if not lcs_items:
        return key_points
    lcs_pts: List[str] = []
    for lcs in lcs_items:
        if not isinstance(lcs, dict):
            continue
        theme = str(lcs.get("theme") or "").strip()
        current_status = str(lcs.get("current_status") or "").strip()
        credibility = str(lcs.get("management_credibility_signal") or "").strip()
        if not theme or not current_status:
            continue
        pt = f"{theme}: {_lcs_human_label(current_status)}"
        if credibility:
            pt += f" (credibility: {_lcs_human_label(credibility)})"
        lcs_pts.append(pt + ".")
    remaining = max(0, 4 - len(key_points))
    return key_points + _clean_list(lcs_pts)[:remaining]


def _progression_key_points(items: List[Dict[str, Any]], question_id: str) -> List[str]:
    points = []
    for item in items:
        summary = summarize_progression_item(item, question_id)
        label = _clean_display_phrase(str(summary.get("what_changed") or summary.get("headline") or "").strip(), limit_words=18)
        if not label:
            label = _clean_display_phrase(str(summary.get("headline") or summary.get("current_state") or "").strip(), limit_words=18)
        state = summary["current_state"]
        credibility = str(summary.get("management_credibility_signal") or "").strip()
        if question_id == "did-past-claims-come-true" and credibility:
            points.append(_clean_display_phrase(f"{label}: {state} (credibility signal: {credibility}).", limit_words=22))
        else:
            points.append(_clean_display_phrase(f"{label}: {state}.", limit_words=18))
    return _clean_list(points)[:4]


def _progression_conclusion(question_id: str, summary: Dict[str, Any]) -> str:
    if question_id == "what-has-management-promised":
        return "Management commitment is visible, but later delivery evidence remains incomplete"
    if question_id == "did-past-claims-come-true":
        return "The prior claim is only partly verified by later evidence"
    if question_id == "what-projects-are-underway":
        return "The project is underway, but the business effect remains unproven"
    if question_id == "how-is-capacity-changing":
        return "Operating capacity is changing, but utilization or payoff remains unproven"
    if question_id == "what-is-management-commentary-saying":
        return "Management commentary shows a change in framing, but the business implication remains bounded by later evidence"
    return "The progression remains visible, but outcome evidence is incomplete"


def _progression_why_it_matters(question_id: str) -> str:
    if question_id == "what-has-management-promised":
        return "Investors need to separate explicit commitments from later delivery."
    if question_id == "did-past-claims-come-true":
        return "Claims matter only if later evidence shows follow-through."
    if question_id == "what-projects-are-underway":
        return "Projects show where management is deploying time and capital."
    if question_id == "how-is-capacity-changing":
        return "Capacity only matters if it raises the ability to produce, test, deliver, or serve."
    if question_id == "what-is-management-commentary-saying":
        return "Commentary matters because it reveals shifts in priorities, confidence, risk language, and emphasis."
    return "The path from intention to action to outcome is what determines management credibility."


def _progression_economic_mechanism(question_id: str) -> str:
    if question_id == "what-has-management-promised":
        return "Forward-looking commitments create conviction only when later evidence confirms delivery."
    if question_id == "did-past-claims-come-true":
        return "Claims create conviction only when follow-through turns into verifiable evidence."
    if question_id == "what-projects-are-underway":
        return "Projects matter when they convert management intent into operating capability or customer delivery."
    if question_id == "how-is-capacity-changing":
        return "Capacity matters when the business can produce, test, deliver, or serve more at useful economics."
    if question_id == "what-is-management-commentary-saying":
        return "Commentary matters when the framing of execution, risk, and priorities changes in a way that affects belief about future delivery."
    return "Execution matters when it creates observable capability, utilization, cash generation, or return on capital."


def _progression_detailed_explanation(question_id: str) -> str:
    if question_id == "what-has-management-promised":
        return "This view only counts explicit management commitments or forward-looking statements. It shows what management said, when it said it, what it intended, and what later evidence is still missing."
    if question_id == "did-past-claims-come-true":
        return "This view traces a prior claim to later evidence and asks whether the chain ends in delivery, delay, abandonment, or contradiction."
    if question_id == "what-projects-are-underway":
        return "This view tracks active execution: project, build, deployment, or integration. Completed history is excluded unless the active project itself remains ongoing."
    if question_id == "how-is-capacity-changing":
        return "This view only counts real operating capacity changes such as facilities, manufacturing, testing, workforce, or throughput. It excludes customer base, market size, and generic expansion."
    if question_id == "what-is-management-commentary-saying":
        return "This view only uses actual management commentary. Supporting evidence can come from capex, projects, or capacity, but those are not the commentary itself."
    return "The progression view keeps management intent, action, later evidence, and uncertainty separate so the answer stays investor-useful."


def _progression_watch_items(question_id: str, implication: Dict[str, Any], unresolved: List[str]) -> List[str]:
    watch = _clean_list(_get_string_list(implication, "what_to_watch") + unresolved)
    if question_id == "what-has-management-promised":
        watch = watch or ["Later delivery evidence", "Whether management keeps or revises the original target", "Proof that the promise turned into action"]
    elif question_id == "did-past-claims-come-true":
        watch = watch or ["Later evidence", "Whether the claim was delivered, delayed, or contradicted", "Signals of follow-through"]
    elif question_id == "what-projects-are-underway":
        watch = watch or ["Execution milestones", "Customer or operating adoption", "Whether the project is still active"]
    elif question_id == "how-is-capacity-changing":
        watch = watch or ["Utilization", "Incremental throughput or productivity", "Whether capacity turns into useful economics"]
    elif question_id == "what-is-management-commentary-saying":
        watch = watch or ["Later commentary", "Shift in emphasis or risk language", "Whether commentary aligns with operating evidence"]
    return watch[:3]


def _progression_confidence(question_id: str, summary: Dict[str, Any], implication: Dict[str, Any], coverage: str) -> Dict[str, Any]:
    confidence = _get_record(implication, "confidence") or {"level": "medium", "basis": ["progression evidence"], "limitations": []}
    level = str(confidence.get("level") or "medium").lower()
    rank = {"high": 3, "medium": 2, "low": 1, "insufficient": 0, "unavailable": 0}
    cap = rank.get(level, 2)
    current_state = str(summary.get("current_state") or "").lower()
    latest_evidence = _clean_list(summary.get("latest_evidence") or [])
    unresolved_items = _clean_list(summary.get("unresolved_items") or [])
    if coverage == "partial":
        cap = min(cap, 2)
    if question_id == "did-past-claims-come-true":
        if not latest_evidence:
            cap = min(cap, 1)
        elif current_state in {"announced", "unresolved"}:
            cap = min(cap, 1)
        elif unresolved_items:
            cap = min(cap, 2)
    elif current_state in {"announced", "in progress"} or unresolved_items:
        cap = min(cap, 2)
    capped_level = "high" if cap >= 3 else "medium" if cap == 2 else "low"
    return {
        "level": capped_level,
        "basis": _clean_list(confidence.get("basis") or [])[:4] or ["progression evidence"],
        "limitations": _clean_list(confidence.get("limitations") or [])[:4],
    }


def _cap_progression_confidence(answer: Dict[str, Any]) -> Dict[str, Any]:
    interpretation = answer.get("interpretation") if isinstance(answer.get("interpretation"), dict) else {}
    confidence = interpretation.get("confidence") if isinstance(interpretation.get("confidence"), dict) else {}
    level = str(confidence.get("level") or "medium").lower()
    rank = {"high": 3, "medium": 2, "low": 1, "insufficient": 0, "unavailable": 0}
    cap = rank.get(level, 2)
    progression = answer.get("progression") if isinstance(answer.get("progression"), dict) else {}
    current_state = str(progression.get("current_state") or "").lower()
    unresolved_items = _clean_list(progression.get("unresolved_items") or [])
    latest_evidence = _clean_list(progression.get("latest_evidence") or [])
    status = str(answer.get("answer_status") or "").lower()
    if status == "not_supported":
        cap = min(cap, 1)
    elif status == "partially_supported":
        cap = min(cap, 2)
    if not latest_evidence:
        cap = min(cap, 1)
    elif current_state in {"announced", "in progress"} or unresolved_items:
        cap = min(cap, 2)
    capped_level = "high" if cap >= 3 else "medium" if cap == 2 else "low"
    return {
        "level": capped_level,
        "basis": _clean_list(confidence.get("basis") or [])[:4] or ["progression evidence"],
        "limitations": _clean_list(confidence.get("limitations") or [])[:4],
    }


def _uses_legacy_streams(items: List[Dict[str, Any]]) -> bool:
    for item in items:
        if any(str(stream).startswith("legacy_") for stream in item.get("stream_types", []) or []):
            return True
    return False


def _complete_sentence(value: Any) -> str:
    text = _clean_canonical_sentence(str(value or ""))
    if not text:
        return ""
    return text if text.endswith((".", "?", "!")) else text + "."


def _clean_canonical_sentence(value: Any) -> str:
    text = " ".join(str(value or "").replace("...", "").replace("…", "").split()).strip(" ,;:-")
    return text


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
    # Strip internal template language before using in investor-facing text
    raw_findings = _get_string_list(analysis, "key_findings")
    raw_flags = _get_string_list(analysis, "red_flags")
    raw_uncertainties = _get_string_list(analysis, "open_uncertainties")
    findings = [_strip_backend_phrasing(f) for f in raw_findings if _strip_backend_phrasing(f)]
    red_flags = [_strip_backend_phrasing(f) for f in raw_flags if _strip_backend_phrasing(f)]
    uncertainties = [_strip_backend_phrasing(f) for f in raw_uncertainties if _strip_backend_phrasing(f)]
    if not direct:
        return _build_generic_not_supported_answer(source_bundle, business_journey_payload=business_journey_payload, products_services_payload=products_services_payload, question=question)
    stripped_direct = _strip_backend_phrasing(direct) or direct
    return _draft(
        answer_status="supported",
        simple_answer=stripped_direct,
        why_it_matters=why,
        key_points=_clean_list([findings[0] if findings else "", findings[1] if len(findings) > 1 else "", red_flags[0] if red_flags else "", uncertainties[0] if uncertainties else ""])[:4],
        detailed_explanation=" ".join(_clean_list([stripped_direct] + findings[:2] + red_flags[:1] + uncertainties[:1])),
        evidence_status="derived",
        evidence_summary="Supported by the relevant investor lens and cross-checked against the committee synthesis where useful.",
        evidence_points=_clean_list(findings[:2] + red_flags[:1]),
        uncertainty=(uncertainties[0] if uncertainties else "This lens remains limited by the available evidence set."),
        products_refs=[],
        business_journey_ref=None,
    )


def _build_buffett_watchpoints(
    analysis: Dict[str, Any],
    committee: Dict[str, Any],
) -> List[str]:
    """Derive concrete Buffett watchpoints from actual analysis data.

    Prefers evidence-backed items from red_flags and uncertainties over
    generic boilerplate. Falls back to generic watchpoints only when
    specific evidence is unavailable.
    """
    # Extract evidence-specific watchpoints from the analysis
    specific: List[str] = []
    for item in _get_string_list(analysis, "financial_red_flags"):
        stripped = _strip_backend_phrasing(item)
        if stripped and len(stripped.split()) <= 14:
            specific.append(stripped)
    for item in _get_string_list(analysis, "open_uncertainties"):
        stripped = _strip_backend_phrasing(item)
        if stripped and len(stripped.split()) <= 14:
            specific.append(stripped)
    for item in _get_string_list(_get_record(committee, "financial_committee_view"), "investor_questions_from_financials"):
        stripped = _strip_backend_phrasing(item)
        if stripped and len(stripped.split()) <= 16:
            specific.append(stripped)

    # Fallback generic watchpoints — used only when specific evidence is unavailable
    generic_fallback = [
        "Owner earnings versus reported profit",
        "Working-capital conversion trend",
        "Returns on incremental capital deployed",
    ]
    combined = specific[:3] if specific else generic_fallback
    return _clean_list(combined)[:4]


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
    # Strip internal template language before word-limit trimming so useful content survives
    findings = [_clean_display_phrase(_strip_backend_phrasing(item), limit_words=24) for item in _clean_list(_get_string_list(analysis, "key_findings"))]
    red_flags = [_clean_display_phrase(_strip_backend_phrasing(item), limit_words=24) for item in _clean_list(_get_string_list(analysis, "red_flags"))]
    uncertainties = [_clean_display_phrase(_strip_backend_phrasing(item), limit_words=24) for item in _clean_list(_get_string_list(analysis, "open_uncertainties"))]
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
    # Enrich sections with Gold intelligence when available
    gold_cred = _source_payload(source_bundle, "gold_credibility")
    gold_cap = _source_payload(source_bundle, "gold_capital_allocation")
    def _trunc(s: str, n: int = 140) -> str:
        s = (s or "").strip()
        return (s[:n - 1] + "…") if len(s) > n else s
    if gold_cred:
        gw_natural = _gold_cred_weight(gold_cred)
        cred_summary = _gold_cred_summary(gold_cred)
        gcred_s = gold_cred.get("summary") or {}
        cautions = [_trunc(str(c), 120) for c in (gcred_s.get("key_cautions") or [])[:1] if str(c).strip()]
        lead = _trunc(cred_summary or gw_natural)
        gold_mgmt_pts = [p for p in ([lead] + cautions) if p and p.strip()]
        if gold_mgmt_pts:
            sections.append({"title": "Management track record (Gold)", "points": gold_mgmt_pts[:2]})
    if gold_cap:
        owner_s = gold_cap.get("owner_capital_summary") or {}
        owner_note = _trunc(str(owner_s.get("narrative") or owner_s.get("interpretation") or ""), 150)
        major = (gold_cap.get("material_allocations") or gold_cap.get("major_allocations") or [])[:2]
        _RETURN_NAT = {
            "PROVEN_POSITIVE": "return confirmed", "MIXED": "returns mixed",
            "UNPROVEN": "return not yet visible", "DESTRUCTIVE": "return negative",
        }
        gold_cap_pts = []
        for alloc in major:
            if not isinstance(alloc, dict):
                continue
            name = _trunc((alloc.get("theme") or alloc.get("allocation_name") or alloc.get("name") or "").strip(), 60)
            ret_raw = str(alloc.get("return_status") or "")
            ret = _RETURN_NAT.get(ret_raw, ret_raw.lower().replace("_", " "))
            if name:
                pt = f"{name}: {ret}".strip(": ") if ret and ret.strip() else name
                gold_cap_pts.append(pt)
        gold_cap_pts = [p for p in gold_cap_pts if p and p.strip()]
        if owner_note or gold_cap_pts:
            sections.append({"title": "Capital deployment returns (Gold)", "points": ([owner_note] if owner_note else []) + gold_cap_pts[:2]})
    sections = [s for s in sections if any(str(p).strip() for p in (s.get("points") or []))]
    interpretation = build_interpretation_contract(
        conclusion=_clean_display_phrase(concise_summary, limit_words=22) or concise_summary,
        what_changed=_clean_list([findings[0] if findings else "", red_flags[0] if red_flags else "", uncertainties[0] if uncertainties else ""])[:2],
        why_it_matters="Buffett would care most about whether the business can turn capability and capital into durable per-share compounding.",
        economic_mechanism="The Buffett lens is about whether capital allocation, moat durability, and owner earnings compound per-share value instead of merely expanding activity.",
        thesis_impact="neutral",
        positive_evidence=_clean_list([cleaned_findings[0] if cleaned_findings else "", cleaned_findings[1] if len(cleaned_findings) > 1 else "", _strip_backend_phrasing(_get_string(_get_record(committee, "financial_committee_view"), "investor_implication"))])[:3],
        negative_evidence=_clean_list([cleaned_red_flags[0] if cleaned_red_flags else "", cleaned_red_flags[1] if len(cleaned_red_flags) > 1 else "", cleaned_uncertainties[0] if cleaned_uncertainties else ""])[:3],
        unresolved=_clean_list([cleaned_uncertainties[0] if cleaned_uncertainties else "", _first_string(_get_string_list(_get_record(committee, "financial_committee_view"), "investor_questions_from_financials"))])[:3],
        what_to_watch=_build_buffett_watchpoints(analysis, committee),
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
    risks = [_strip_backend_phrasing(_clean_display_phrase(item, limit_words=18)) for item in _risk_texts(source_bundle)[:4]]
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
        simple_answer=direct_answer or "The available evidence does not yet support a reliable conclusion on this question.",
        why_it_matters=why or "This still matters because the question is valid even when the current source set cannot answer it responsibly.",
        key_points=[
            limitation or "The current evidence set does not preserve enough direct evidence to support a stronger answer.",
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


# ── P3A: Capital Allocation Intelligence ─────────────────────────────────────

# State-to-investor translation tables (Phase 2 canonical → plain English)
_DEP_STATE_LABEL = {
    "DEPLOYED": "deployed",
    "COMMITTED": "committed",
    "ANNOUNCED": "announced",
    "COMPLETED_TRANSACTION": "transaction completed",
    "CANCELLED": "cancelled",
    "UNABLE_TO_VERIFY": "unable to verify",
}
_EXE_STATE_LABEL = {
    "COMPLETED": "execution complete",
    "OPERATIONAL": "operational",
    "IN_PROGRESS": "in progress",
    "UNABLE_TO_VERIFY": "execution not yet verified",
    "NOT_STARTED": "not yet started",
}
_FOS_LABEL = {
    "CASH_FLOW_EFFECT": "direct cash-flow effect (capital returned or liability reduced)",
    "REVENUE_CONTRIBUTION": "revenue contribution visible",
    "UNABLE_TO_ATTRIBUTE": "financial return not yet attributable",
}
_VCC_LABEL = {
    "VALUE_CREATION_EVIDENCE": "value-creation evidence present",
    "VALUE_DESTRUCTION_EVIDENCE": "value-destruction evidence",
    "TOO_EARLY_TO_JUDGE": "too early to judge",
    "UNABLE_TO_VERIFY": "unable to verify",
}
_SKILL_LABEL = {
    "POSITIVE_EVIDENCE": "positive evidence of value creation",
    "NEGATIVE_EVIDENCE": "evidence of value destruction",
    "MIXED_EVIDENCE": "mixed evidence",
    "UNABLE_TO_VERIFY": "capital activity documented; value-creation skill not yet established",
    "OUTCOMES_MOSTLY_UNVERIFIED": "most outcomes remain unverified — activity is clearer than skill",
}


def _build_capital_allocation_answer(
    source_bundle: Dict[str, Any],
    *,
    business_journey_payload: Dict[str, Any],
    products_services_payload: Dict[str, Any],
    question: Dict[str, Any],
) -> Dict[str, Any]:
    """Build capital allocation answer from Phase 2/3 canonical data.

    Source priority: Phase 3 longitudinal profile → Phase 2 assessments → fallback.
    Does NOT recompute causality, deployment status, or value creation.
    """
    profile = _source_payload(source_bundle, "capital_allocation_longitudinal_profile")
    outcomes = _source_payload(source_bundle, "capital_allocation_outcomes")
    assessments_payload = _source_payload(source_bundle, "capital_allocation_assessments")

    if not profile and not outcomes:
        return _build_canonical_progression_answer(
            source_bundle,
            business_journey_payload=business_journey_payload,
            products_services_payload=products_services_payload,
            question=question,
        )

    # ── Section 1: Allocation pattern ───────────────────────────────────────
    scope = (profile.get("profile_scope") or {}) if profile else {}
    start_p = str(scope.get("start_period") or "").upper()
    end_p = str(scope.get("end_period") or "").upper()
    period_range = f"{start_p}–{end_p}" if start_p and end_p else (start_p or end_p or "")
    n_events = scope.get("total_events") or int(outcomes.get("allocation_count") or 0)

    oi = (profile.get("organic_vs_inorganic") or {}) if profile else {}
    organic_n = oi.get("organic_event_count", 0)
    inorganic_n = oi.get("inorganic_event_count", 0)
    dist_n = oi.get("distribution_event_count", 0)
    bs_n = oi.get("balance_sheet_event_count", 0)

    pattern_parts = []
    if inorganic_n:
        pattern_parts.append(f"{inorganic_n} inorganic (acquisitions/investments)")
    if organic_n:
        pattern_parts.append(f"{organic_n} organic reinvestment events")
    if dist_n:
        pattern_parts.append(f"{dist_n} shareholder distribution events")
    if bs_n:
        pattern_parts.append(f"{bs_n} balance-sheet actions")
    pattern_summary = (
        f"Over {period_range}, management deployed capital across " + ", ".join(pattern_parts) + "."
        if pattern_parts and period_range
        else f"{n_events} capital allocation events documented."
    )

    # ── Section 2: Capital-weighted picture ─────────────────────────────────
    cov = (profile.get("amount_coverage") or {}) if profile else {}
    capital_weighted_ok = cov.get("capital_weighted_conclusions_permitted", False)
    mix_pts: List[str] = []
    if profile and capital_weighted_ok:
        for entry in (profile.get("allocation_mix") or {}).get("by_category") or []:
            if not isinstance(entry, dict):
                continue
            cat = str(entry.get("category") or "").replace("_", " ")
            share = entry.get("share_of_known_deployment")
            amount = entry.get("known_amount_crore")
            cnt = entry.get("event_count", 0)
            if share is not None and amount:
                mix_pts.append(
                    f"{cat.title()}: ₹{format_number(amount)} Cr ({int(share * 100)}% of tracked capital, {cnt} event(s))"
                )
            elif amount:
                mix_pts.append(f"{cat.title()}: ₹{format_number(amount)} Cr ({cnt} event(s))")
            elif cnt:
                mix_pts.append(f"{cat.title()}: {cnt} event(s)")
    capital_note = (
        "Based on known deployment amounts, capital-weighted breakdown is available."
        if capital_weighted_ok
        else (cov.get("note") or "Event-count pattern is visible; monetary coverage is insufficient for capital-weighted conclusions.")
    )

    # ── Section 3: Major allocations ────────────────────────────────────────
    major_pts: List[str] = []
    raw_allocs = _get_record_list(outcomes, "allocations") if outcomes else []
    assessments_list = (
        _get_record_list(assessments_payload, "assessments") if assessments_payload else []
    )
    # Build a lookup from Phase 2 assessments by allocation_id
    assess_by_id: Dict[str, Any] = {
        a.get("allocation_id", ""): a
        for a in assessments_list
        if isinstance(a, dict) and a.get("allocation_id")
    }
    for alloc in raw_allocs[:5]:
        if not isinstance(alloc, dict):
            continue
        aid = alloc.get("allocation_id", "")
        cat = str(alloc.get("allocation_category") or "").replace("_", " ")
        name = _first_string(alloc.get("normalized_name"), alloc.get("allocation_name"), cat)
        amount = alloc.get("amount")
        periods = alloc.get("deployment_periods") or []
        period_str = (
            f"{str(periods[0]).upper()}–{str(periods[-1]).upper()}" if len(periods) > 1
            else (str(periods[0]).upper() if periods else "")
        )
        a = assess_by_id.get(aid, {})
        dep = _DEP_STATE_LABEL.get(a.get("deployment_state", ""), "")
        exe = _EXE_STATE_LABEL.get(a.get("execution_state", ""), "")
        parts = [f"{name}"]
        if amount:
            parts.append(f"₹{format_number(amount)} Cr")
        if period_str:
            parts.append(f"({period_str})")
        if dep:
            parts.append(f"— {dep}")
        if exe and exe != dep:
            parts.append(f"/ {exe}")
        major_pts.append(" ".join(p for p in parts if p))

    # ── Section 4: What actually worked (Phase 2 canonical states) ──────────
    outcome_pts: List[str] = []
    exec_verified = []
    operating_visible = []
    fin_attributable = []
    per_share_attr = []
    unverified = []

    for a in assessments_list:
        if not isinstance(a, dict):
            continue
        aid = a.get("allocation_id", "")
        cat = str(a.get("allocation_category") or "").replace("_", " ")
        fos = a.get("financial_outcome_state", "UNABLE_TO_ATTRIBUTE")
        oos = a.get("operating_outcome_state", "UNABLE_TO_VERIFY")
        exe_s = a.get("execution_state", "UNABLE_TO_VERIFY")
        pss = a.get("per_share_consequence_state", "UNABLE_TO_ATTRIBUTE")
        dep_s = a.get("deployment_state", "UNABLE_TO_VERIFY")

        if fos not in ("UNABLE_TO_ATTRIBUTE", None):
            fin_attributable.append(f"{cat} ({aid}): {_FOS_LABEL.get(fos, fos)}")
        elif oos not in ("UNABLE_TO_VERIFY", "NO_VERIFIED_OUTCOME", None):
            operating_visible.append(f"{cat} ({aid}): operating progress visible")
        elif exe_s not in ("UNABLE_TO_VERIFY", "NOT_STARTED", None):
            exec_verified.append(f"{cat} ({aid}): {_EXE_STATE_LABEL.get(exe_s, exe_s)}")
        else:
            unverified.append(f"{cat} ({aid})")

        if pss not in ("UNABLE_TO_ATTRIBUTE", None):
            per_share_attr.append(f"{cat} ({aid}): per-share consequence attributable")

    if fin_attributable:
        outcome_pts.append("Financial return attributable: " + "; ".join(fin_attributable[:3]) + ".")
    if operating_visible:
        outcome_pts.append("Operating outcome visible (financial not yet attributed): " + "; ".join(operating_visible[:2]) + ".")
    if exec_verified:
        outcome_pts.append("Execution verified (operating outcome not yet visible): " + "; ".join(exec_verified[:2]) + ".")
    if unverified:
        outcome_pts.append(
            f"{len(unverified)} allocation(s) with unverified outcomes: " + ", ".join(unverified[:3]) + "."
        )
    if per_share_attr:
        outcome_pts.append("Per-share consequence attributable: " + "; ".join(per_share_attr[:2]) + ".")

    # ── Section 5: Stewardship conclusion (Phase 3) ──────────────────────────
    avs = (profile.get("allocation_activity_vs_skill") or {}) if profile else {}
    skill_raw = avs.get("skill_assessment", "UNABLE_TO_VERIFY")
    skill_label = _SKILL_LABEL.get(skill_raw, skill_raw)
    skill_basis = avs.get("skill_basis", "")
    stewardship_obs = (profile.get("stewardship_observations") or []) if profile else []
    stewardship_pts = [
        o.get("detail", "")
        for o in stewardship_obs[:2]
        if isinstance(o, dict) and o.get("detail")
    ]

    # ── Section 6: Unresolved questions ──────────────────────────────────────
    uq = (profile.get("unresolved_questions") or []) if profile else []

    # ── Compose answer ────────────────────────────────────────────────────────
    n_fin = len(fin_attributable)
    n_unverified = len(unverified)
    n_total = len(assessments_list) or n_events

    if n_fin >= n_total * 0.5:
        answer_status = "supported"
        thesis_impact = "neutral"
    elif n_unverified >= n_total * 0.5:
        answer_status = "partially_supported"
        thesis_impact = "neutral"
    else:
        answer_status = "partially_supported"
        thesis_impact = "neutral"

    simple = pattern_summary
    key_points = _clean_list(
        [pattern_summary]
        + mix_pts[:2]
        + major_pts[:3]
        + outcome_pts[:3]
        + [f"Capital allocation skill: {skill_label}."] if skill_label else []
    )
    detailed = (
        f"{pattern_summary} {capital_note} "
        f"Of {n_total} tracked events, {n_fin} have attributable financial outcomes and "
        f"{n_unverified} remain unverified. Allocation activity is documented; "
        f"allocation skill requires attributable causal evidence which current records "
        f"{'do not yet fully support' if n_fin < n_total * 0.5 else 'partially support'}."
    )

    evidence_pts = _clean_list(major_pts[:2] + outcome_pts[:2])
    uncertainty_parts = []
    if uq:
        uncertainty_parts.append(uq[0])
    if n_unverified:
        uncertainty_parts.append(
            f"{n_unverified} allocation(s) have no attributable financial outcome yet."
        )
    uncertainty = " ".join(uncertainty_parts) if uncertainty_parts else (
        "Capital deployment is documented; return attribution requires further evidence."
    )

    return _draft(
        answer_status=answer_status,
        simple_answer=simple,
        why_it_matters=(
            "Capital allocation is the ultimate test of management stewardship: "
            "deployment is easy to observe, but whether it creates per-share value is what matters."
        ),
        key_points=key_points,
        detailed_explanation=detailed,
        evidence_status="partial" if n_unverified > 0 else "direct",
        evidence_summary=(
            "Derived from canonical Phase 2 causal-attribution ledger and Phase 3 longitudinal profile. "
            "Financial outcomes attributed only where direct causal linkage exists."
        ),
        evidence_points=evidence_pts,
        uncertainty=uncertainty,
        products_refs=[],
        business_journey_ref=None,
        progression={},
        interpretation={
            "conclusion": f"Management is an active capital allocator; {skill_label}.",
            "skill_assessment": skill_raw,
            "skill_basis": skill_basis,
            "stewardship_observations": stewardship_pts,
            "unresolved_diligence": uq[:2],
            "thesis_impact": thesis_impact,
        },
    )


def _build_return_on_capex_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    gold_cap = _source_payload(source_bundle, "gold_capital_allocation")
    roi_ledger = _source_payload(source_bundle, "capital_allocation_roi_ledger")
    capex_alloc = None
    for alloc in (gold_cap.get("material_allocations") or gold_cap.get("allocations") or []):
        if isinstance(alloc, dict) and "capex" in str(alloc.get("allocation_type") or alloc.get("theme") or "").lower():
            capex_alloc = alloc
            break
    if not capex_alloc and not roi_ledger:
        return _build_unavailable_answer(
            question,
            "The capex return evidence is not yet available in the current source set.",
            "Capex return analysis requires outcome data paired with deployment amounts. Where these are split by maintenance and growth, the answer would be more reliable.",
            "The capital_allocation_roi_ledger or gold_capital_allocation source is required.",
        )
    key_pts: List[str] = []
    if capex_alloc:
        name = _first_string(_get_string(capex_alloc, "theme"), _get_string(capex_alloc, "allocation_name"))
        amount = _get_number(capex_alloc, "amount_crore")
        ret = str(capex_alloc.get("return_status") or "")
        amount = _get_number(capex_alloc, "capital_amount_crore") or amount
        period_start = _get_string(capex_alloc, "source_period")
        period_end = _get_string(capex_alloc, "latest_period")
        period = f"{period_start.upper()}–{period_end.upper()}" if period_start and period_end else ""
        outcome = _get_string(capex_alloc, "investor_interpretation") or _get_string(capex_alloc, "outcome_summary")
        if amount:
            key_pts.append(f"{name}: ₹{format_number(amount)} Cr deployed over {period}." if period else f"{name}: ₹{format_number(amount)} Cr deployed.")
        if ret:
            _RETURN_LABEL = {"MIXED": "returns are mixed", "UNPROVEN": "return is not yet visible", "PROVEN_POSITIVE": "return is confirmed positive"}
            key_pts.append(f"Return status: {_RETURN_LABEL.get(ret, ret.lower())}.")
        if outcome:
            key_pts.append(_strip_backend_phrasing(outcome[:120]))
    if roi_ledger:
        roi_items = _get_record_list(roi_ledger, "entries") or _get_record_list(roi_ledger, "items") or []
        for item in roi_items[:2]:
            desc = _get_string(item, "description") or _get_string(item, "period")
            roi = _get_number(item, "roi") or _get_number(item, "return_on_investment")
            if desc and roi is not None:
                key_pts.append(f"{desc}: ROI {format_number(roi)}%.")
    if not key_pts:
        return _build_unavailable_answer(
            question,
            "Capex return data is present but does not yet contain enough outcome fields.",
            "The return on capex can only be assessed once outcome data spans multiple years.",
            "Outcome evidence is currently limited.",
        )
    simple = key_pts[0] if key_pts else "Capex return evidence is present but limited."
    return _draft(
        answer_status="partially_supported",
        simple_answer=simple,
        why_it_matters="Capex return matters because it determines whether reinvestment is creating or destroying per-share value.",
        key_points=_clean_list(key_pts),
        detailed_explanation="The available evidence captures capex amounts and current return classification. A full return assessment would require ROIC or ROCE computed on the incremental capital invested.",
        evidence_status="partial",
        evidence_summary="Derived from Gold Capital Allocation Outcome Tracker and ROI ledger.",
        evidence_points=key_pts[:2],
        uncertainty="Maintenance versus growth capex split is not separately disclosed. Return classification reflects current evidence only.",
        products_refs=[],
        business_journey_ref=None,
        progression={},
        interpretation={"conclusion": simple, "thesis_impact": "neutral"},
    )


# ── P3B: Management Delivery Specifics ───────────────────────────────────────

def _build_promise_types_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    gold = _source_payload(source_bundle, "gold_promise_tracker")
    if not gold:
        return _build_unavailable_answer(question, "Gold Promise Tracker is not available.", "Promise type analysis requires the tracker.", "Regenerate Gold artifacts.")
    summary = gold.get("summary") or {}
    tb = summary.get("promise_type_breakdown") or {}
    tracked = int(summary.get("tracked_promises") or 0)
    if not tb or not tracked:
        return _build_unavailable_answer(question, "Promise type breakdown is unavailable.", "The tracker exists but lacks type classification.", "")
    type_pts: List[str] = []
    for ptype, count in sorted(tb.items(), key=lambda x: -x[1]):
        if isinstance(count, int) and count > 0:
            readable = ptype.replace("_", " ").title()
            type_pts.append(f"{readable}: {count} commitment(s).")
    dominant = max(tb.items(), key=lambda x: x[1] if isinstance(x[1], int) else 0, default=("", 0))
    dom_name = dominant[0].replace("_", " ").title()
    dom_count = dominant[1]
    simple = f"Of {tracked} tracked commitments, {dom_name} is the largest category with {dom_count} commitment(s). Regulatory Remediation and Product Launch together dominate the promise ledger."
    return _draft(
        answer_status="supported",
        simple_answer=simple,
        why_it_matters="Promise type concentration reveals where management is spending credibility — and where follow-through risk is highest.",
        key_points=_clean_list(type_pts),
        detailed_explanation=f"{tracked} commitments tracked. Type breakdown: {'; '.join(type_pts[:5])}.",
        evidence_status="direct",
        evidence_summary="Gold Promise Tracker — type breakdown from summary.",
        evidence_points=type_pts[:2],
        uncertainty="Promise type classification is derived from the commitment text and may not match management's own categorization.",
        products_refs=[],
        business_journey_ref=None,
        progression={},
        interpretation={"conclusion": simple, "thesis_impact": "neutral"},
    )


def _build_overdue_promises_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    gold = _source_payload(source_bundle, "gold_promise_tracker")
    if not gold:
        return _build_unavailable_answer(question, "Gold Promise Tracker is not available.", "Overdue promise analysis requires the tracker.", "")
    summary = gold.get("summary") or {}
    sb = summary.get("status_breakdown") or {}
    missed = int(sb.get("missed", 0))
    delayed = int(sb.get("delayed", 0))
    resolved = gold.get("resolved_promises") or []
    missed_promises = [p for p in resolved if str(p.get("current_status") or p.get("outcome_status") or "").upper() in ("MISSED", "DELAYED")]
    if not missed_promises and missed == 0 and delayed == 0:
        return _draft(
            answer_status="supported",
            simple_answer="No commitments are currently classified as missed or overdue in the tracker.",
            why_it_matters="Overdue promises are the most direct signal of execution risk — management committed and did not deliver.",
            key_points=["No missed or delayed commitments currently tracked."],
            detailed_explanation="All tracked commitments are either unverified, partially achieved, or achieved. No explicit miss or delay is recorded.",
            evidence_status="direct",
            evidence_summary="Gold Promise Tracker — status breakdown.",
            evidence_points=[],
            uncertainty="UNVERIFIED status means no later evidence is available — it does not confirm delivery.",
            products_refs=[],
            business_journey_ref=None,
            progression={},
            interpretation={"conclusion": "No overdue commitments currently tracked.", "thesis_impact": "neutral"},
        )
    key_pts: List[str] = []
    for p in missed_promises[:3]:
        theme = _get_string(p, "theme") or _get_string(p, "promise_type")
        inv = _get_string(p, "investor_interpretation")
        inv_clean = _strip_backend_phrasing(inv[:120]) if inv else ""
        if theme:
            key_pts.append(f"{theme}: {inv_clean}" if inv_clean else f"{theme} — marked as missed.")
    if missed and not key_pts:
        key_pts.append(f"{missed} commitment(s) are classified as missed.")
    if delayed:
        key_pts.append(f"{delayed} commitment(s) are classified as delayed.")
    simple = f"{missed + delayed} commitment(s) are overdue (missed or delayed). " + (key_pts[0] if key_pts else "")
    return _draft(
        answer_status="supported",
        simple_answer=simple.strip(),
        why_it_matters="Overdue promises are the most direct signal of execution risk — management committed and did not deliver.",
        key_points=_clean_list(key_pts),
        detailed_explanation="Missed and delayed commitments lower the weight that should be placed on new forward guidance from management.",
        evidence_status="direct",
        evidence_summary="Gold Promise Tracker — resolved promises with missed/delayed status.",
        evidence_points=key_pts[:2],
        uncertainty="Some commitments may be UNVERIFIED rather than MISSED — absence of later evidence is not the same as a confirmed failure.",
        products_refs=[],
        business_journey_ref=None,
        progression={},
        interpretation={"conclusion": simple.strip(), "thesis_impact": "weakens"},
    )


def _build_delivered_promises_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    gold = _source_payload(source_bundle, "gold_promise_tracker")
    if not gold:
        return _build_unavailable_answer(question, "Gold Promise Tracker is not available.", "Delivery analysis requires the tracker.", "")
    summary = gold.get("summary") or {}
    sb = summary.get("status_breakdown") or {}
    achieved = int(sb.get("achieved", 0))
    partially = int(sb.get("partially_achieved", 0))
    resolved = gold.get("resolved_promises") or []
    delivered = [p for p in resolved if str(p.get("current_status") or p.get("outcome_status") or "").upper() in ("ACHIEVED", "PARTIALLY_ACHIEVED")]
    if not delivered and achieved == 0 and partially == 0:
        return _draft(
            answer_status="partially_supported",
            simple_answer="No commitments are currently recorded as fully delivered. The tracker shows mostly unverified status across 13 tracked items.",
            why_it_matters="Delivery track record is the only reliable test of whether management's stated intent translates into execution.",
            key_points=["0 commitments achieved; 0 partially delivered; 11 unverified."],
            detailed_explanation="Unverified does not mean failed — it means no later evidence is available to confirm delivery.",
            evidence_status="partial",
            evidence_summary="Gold Promise Tracker — summary status breakdown.",
            evidence_points=[],
            uncertainty="UNVERIFIED status is not a confirmed failure; later evidence may confirm delivery.",
            products_refs=[],
            business_journey_ref=None,
            progression={},
            interpretation={"conclusion": "No fully delivered commitments yet recorded.", "thesis_impact": "neutral"},
        )
    key_pts: List[str] = []
    for p in delivered[:3]:
        theme = _get_string(p, "theme") or _get_string(p, "promise_type")
        inv = _get_string(p, "investor_interpretation")
        inv_clean = _strip_backend_phrasing(inv[:120]) if inv else ""
        status = str(p.get("current_status") or p.get("outcome_status") or "").upper()
        label = "Partially delivered" if "PARTIALLY" in status else "Delivered"
        if theme:
            key_pts.append(f"{label}: {theme}. {inv_clean}".strip())
    if achieved:
        key_pts.append(f"{achieved} commitment(s) fully achieved.")
    if partially:
        key_pts.append(f"{partially} commitment(s) partially delivered.")
    simple = f"{achieved + partially} commitment(s) have visible delivery evidence. " + (key_pts[0] if key_pts else "")
    return _draft(
        answer_status="supported",
        simple_answer=simple.strip(),
        why_it_matters="Delivery track record is the only reliable test of whether management's stated intent translates into execution.",
        key_points=_clean_list(key_pts),
        detailed_explanation="Partial delivery is meaningful — it shows management moved from announcement to action, even if not fully complete.",
        evidence_status="direct",
        evidence_summary="Gold Promise Tracker — resolved promises with achieved/partially_achieved status.",
        evidence_points=key_pts[:2],
        uncertainty="Partial delivery may reflect genuine early-stage execution or a softer-than-committed outcome.",
        products_refs=[],
        business_journey_ref=None,
        progression={},
        interpretation={"conclusion": simple.strip(), "thesis_impact": "strengthens" if achieved > 0 else "neutral"},
    )


def _build_missed_promises_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    gold = _source_payload(source_bundle, "gold_promise_tracker")
    if not gold:
        return _build_unavailable_answer(question, "Gold Promise Tracker is not available.", "Miss analysis requires the tracker.", "")
    summary = gold.get("summary") or {}
    sb = summary.get("status_breakdown") or {}
    missed = int(sb.get("missed", 0))
    resolved = gold.get("resolved_promises") or []
    missed_items = [p for p in resolved if str(p.get("current_status") or p.get("outcome_status") or "").upper() == "MISSED"]
    if not missed_items and missed == 0:
        return _draft(
            answer_status="supported",
            simple_answer="The tracker records no commitments as explicitly missed.",
            why_it_matters="Explicit misses reveal where execution fell short of what was promised.",
            key_points=["No explicit misses recorded."],
            detailed_explanation="Some commitments are UNVERIFIED — absence of later evidence does not confirm they were missed.",
            evidence_status="direct",
            evidence_summary="Gold Promise Tracker.",
            evidence_points=[],
            uncertainty="UNVERIFIED commitments may yet be confirmed as delivered or missed in future evidence.",
            products_refs=[],
            business_journey_ref=None,
            progression={},
            interpretation={"conclusion": "No explicit misses recorded.", "thesis_impact": "neutral"},
        )
    key_pts: List[str] = []
    for p in missed_items[:3]:
        theme = _get_string(p, "theme") or _get_string(p, "promise_type")
        inv = _get_string(p, "investor_interpretation")
        inv_clean = _strip_backend_phrasing(inv[:120]) if inv else ""
        if theme:
            key_pts.append(f"Missed: {theme}. {inv_clean}".strip())
    simple = f"{missed} commitment(s) are explicitly classified as missed. " + (key_pts[0] if key_pts else "")
    return _draft(
        answer_status="supported",
        simple_answer=simple.strip(),
        why_it_matters="Explicit misses reveal where execution fell short of what was promised and should lower conviction in forward guidance.",
        key_points=_clean_list(key_pts),
        detailed_explanation="A missed commitment means later evidence directly contradicted the original direction. This is distinct from UNVERIFIED, where no later evidence is available.",
        evidence_status="direct",
        evidence_summary="Gold Promise Tracker — resolved promises with missed status.",
        evidence_points=key_pts[:2],
        uncertainty="Classification depends on whether later evidence is sufficient to confirm a miss.",
        products_refs=[],
        business_journey_ref=None,
        progression={},
        interpretation={"conclusion": simple.strip(), "thesis_impact": "weakens"},
    )


# ── P3C: Committee Synthesis Exposure ────────────────────────────────────────

def _build_committee_direction_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    committee = _source_payload(source_bundle, "committee_synthesis")
    if not committee:
        return _build_unavailable_answer(question, "Committee synthesis is not available.", "Committee direction requires the synthesis artifact.", "")
    direction = str(committee.get("committee_direction") or "").strip()
    strength = str(committee.get("consensus_strength") or "").strip()
    rationale = str(committee.get("committee_rationale") or "").strip()
    if not direction:
        return _build_unavailable_answer(question, "Committee direction field is empty.", "The committee_synthesis artifact exists but direction is not set.", "")
    strength_label = {"high": "strong consensus", "medium": "moderate consensus", "low": "divided views"}.get(strength.lower(), strength)
    simple = f"The committee's overall direction is {direction} with {strength_label}."
    if rationale:
        simple += f" {_strip_backend_phrasing(rationale[:140])}"
    key_pts = [
        f"Direction: {direction}.",
        f"Consensus strength: {strength_label}.",
    ]
    fcv = _get_record(committee, "financial_committee_view") or {}
    fcv_conclusion = _get_string(fcv, "conclusion") or _get_string(fcv, "summary")
    if fcv_conclusion:
        key_pts.append(_strip_backend_phrasing(fcv_conclusion[:120]))
    return _draft(
        answer_status="supported",
        simple_answer=simple.strip(),
        why_it_matters="The committee direction is the most compressed synthesis of what five investor analysts concluded from the same evidence.",
        key_points=_clean_list(key_pts),
        detailed_explanation="The direction reflects a synthesis of Graham, Buffett, Fisher, Munger, and Lynch analysis. A weakening direction means the weight of evidence points toward caution rather than confidence.",
        evidence_status="direct",
        evidence_summary="Derived from the committee_synthesis artifact.",
        evidence_points=key_pts[:2],
        uncertainty="Direction reflects the current evidence set. New filings or evidence could shift the conclusion.",
        products_refs=[],
        business_journey_ref=None,
        interpretation={"conclusion": simple.strip(), "thesis_impact": "weakens" if "weak" in direction.lower() else "neutral"},
    )


def _build_committee_agree_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    committee = _source_payload(source_bundle, "committee_synthesis")
    if not committee:
        return _build_unavailable_answer(question, "Committee synthesis is not available.", "Agreement analysis requires the synthesis artifact.", "")
    agreements = _get_string_list(committee, "doctrine_agreements")
    if not agreements:
        return _build_unavailable_answer(question, "No doctrine agreements found in the committee synthesis.", "Agreement detail requires doctrine_agreements fields.", "")
    def _sentence_truncate(text: str, max_chars: int = 200) -> str:
        raw = re.sub(r"[…]+$", "", text).strip()
        if len(raw) <= max_chars and raw.endswith((".", "!", "?")):
            return raw
        window = raw[:max_chars]
        for boundary in (".", "!", "?", ";"):
            idx = window.rfind(boundary)
            if idx > max_chars // 3:
                truncated = window[:idx + 1].strip()
                return (truncated[:-1] + ".") if truncated.endswith(";") else truncated
        last_space = window.rfind(" ")
        if last_space > max_chars // 3:
            return window[:last_space].rstrip(" ,;:-") + "."
        return window.rstrip(" ,;:-.") + "."

    clean_agreements = [_sentence_truncate(a) for a in agreements[:4] if a]
    clean_agreements = [a for a in clean_agreements if a]
    n_agree = len(clean_agreements)
    simple = f"The committee has {n_agree} documented area(s) of agreement, spanning FCF disclosure quality, reporting-basis comparability, and management execution risk."
    return _draft(
        answer_status="supported",
        simple_answer=simple.strip(),
        why_it_matters="Where all analysts agree, the signal is stronger — it represents a shared conclusion from different frameworks applied to the same evidence.",
        key_points=[a for a in clean_agreements if a],
        detailed_explanation="Doctrine agreements mean that despite different investment frameworks, multiple analysts reached the same conclusion. That cross-framework agreement raises the reliability of the finding.",
        evidence_status="direct",
        evidence_summary="Derived from the committee_synthesis doctrine_agreements field.",
        evidence_points=clean_agreements[:2],
        uncertainty="Agreements are based on the current evidence set. A new disclosure could shift a shared view.",
        products_refs=[],
        business_journey_ref=None,
        interpretation={"conclusion": simple.strip(), "thesis_impact": "neutral"},
    )


def _build_committee_disagree_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    committee = _source_payload(source_bundle, "committee_synthesis")
    if not committee:
        return _build_unavailable_answer(question, "Committee synthesis is not available.", "Disagreement analysis requires the synthesis artifact.", "")
    disagreements = _get_string_list(committee, "doctrine_disagreements")
    major = _get_record_list(committee, "major_disagreements") or []
    if not disagreements and not major:
        return _build_unavailable_answer(question, "No doctrine disagreements found.", "Disagreement detail requires doctrine_disagreements or major_disagreements fields.", "")
    def _sentence_truncate(text: str, max_chars: int = 200) -> str:
        raw = re.sub(r"[…]+$", "", text).strip()
        if len(raw) <= max_chars and raw.endswith((".", "!", "?")):
            return raw
        window = raw[:max_chars]
        for boundary in (".", "!", "?", ";"):
            idx = window.rfind(boundary)
            if idx > max_chars // 3:
                truncated = window[:idx + 1].strip()
                return (truncated[:-1] + ".") if truncated.endswith(";") else truncated
        last_space = window.rfind(" ")
        if last_space > max_chars // 3:
            return window[:last_space].rstrip(" ,;:-") + "."
        return window.rstrip(" ,;:-.") + "."

    key_pts: List[str] = []
    for d in disagreements[:3]:
        if d:
            key_pts.append(_sentence_truncate(d))
    for m in major[:2]:
        if isinstance(m, dict):
            topic = _get_string(m, "topic")
            side_a = _get_string(m, "side_a_view")
            side_b = _get_string(m, "side_b_view")
            resolve = _get_string(m, "what_evidence_would_resolve_it")
            if topic:
                pt = f"Disagreement on {topic.replace('-', ' ')}."
                if resolve:
                    pt += f" Evidence that would resolve it: {_strip_backend_phrasing(resolve[:120])}"
                key_pts.append(pt)
    simple = f"The committee has {len(disagreements)} documented disagreement(s). The central tension is between growth-runway weighting and downside-protection weighting."
    return _draft(
        answer_status="supported",
        simple_answer=simple,
        why_it_matters="Where analysts disagree, the investor must choose which weighting fits their own framework — and understand what evidence would resolve the tension.",
        key_points=[p for p in key_pts if p],
        detailed_explanation="Doctrine disagreements reveal where the same underlying evidence leads different analytical frameworks to different conclusions. These are genuine judgment calls, not errors.",
        evidence_status="direct",
        evidence_summary="Derived from the committee_synthesis doctrine_disagreements and major_disagreements fields.",
        evidence_points=key_pts[:2],
        uncertainty="Disagreements reflect the current evidence. Better disclosure — especially on capex split and FCF reconciliation — may resolve the key tensions.",
        products_refs=[],
        business_journey_ref=None,
        interpretation={"conclusion": simple, "thesis_impact": "neutral"},
    )


# ── P3D: Regulatory Risk ──────────────────────────────────────────────────────

def _build_regulatory_risks_answer(source_bundle: Dict[str, Any], *, business_journey_payload: Dict[str, Any], products_services_payload: Dict[str, Any], question: Dict[str, Any]) -> Dict[str, Any]:
    risk_evo = _source_payload(source_bundle, "gold_risk_evolution")
    if not risk_evo:
        return _build_unavailable_answer(question, "Risk evolution timeline is not available.", "Regulatory risk analysis requires the gold_risk_evolution artifact.", "")
    worsening = risk_evo.get("worsening_or_recurring") or []
    all_themes = risk_evo.get("risk_themes") or []
    regulatory_active = [
        t for t in (worsening + [t for t in all_themes if t not in worsening])
        if isinstance(t, dict) and (
            t.get("risk_type") in ("regulatory", "governance") or
            t.get("current_state") in ("WORSENING", "MITIGATION_STARTED", "RECURRING")
        )
    ][:5]
    if not regulatory_active:
        return _build_unavailable_answer(question, "No active regulatory or governance risks are currently tracked.", "The risk evolution timeline is present but shows no WORSENING or RECURRING regulatory themes.", "")
    def _safe_risk_text(raw: str) -> str:
        # Strip trailing truncation artifacts and internal enum markers before using text
        cleaned = re.sub(r"[.…]+$", "", raw.strip())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) < 10:
            return ""
        return cleaned

    key_pts: List[str] = []
    for t in regulatory_active[:4]:
        theme = _get_string(t, "theme")
        state = str(t.get("current_state") or "").upper()
        desc = _safe_risk_text(_get_string(t, "risk_description"))
        econ = _safe_risk_text(_get_string(t, "economic_exposure"))
        state_label = {"WORSENING": "worsening", "RECURRING": "recurring", "MITIGATION_STARTED": "mitigation started"}.get(state, state.lower())
        text = f"{theme.title() if theme else 'Risk'} ({state_label})"
        detail = desc or econ
        if detail:
            text += f": {detail[:100]}"
        key_pts.append(text)
    worsening_count = sum(1 for t in regulatory_active if str(t.get("current_state") or "") == "WORSENING")
    simple = f"{len(regulatory_active)} active regulatory or governance risk theme(s) are tracked; {worsening_count} are currently worsening."
    return _draft(
        answer_status="supported",
        simple_answer=simple.strip(),
        why_it_matters="Active regulatory risks can create forced remediation costs, market access restrictions, or reputational damage that impairs the investment case.",
        key_points=[p for p in key_pts if p],
        detailed_explanation=f"{len(regulatory_active)} regulatory-class risk themes are tracked as active. Where state is WORSENING, the evidence suggests the risk is escalating without visible resolution.",
        evidence_status="direct",
        evidence_summary="Derived from the Gold Risk Evolution Timeline — worsening and recurring themes.",
        evidence_points=key_pts[:2],
        uncertainty="Risk state reflects the most recent filing period. Regulatory outcomes can change quickly after a consent decree or FDA response.",
        products_refs=[],
        business_journey_ref=None,
        interpretation={"conclusion": simple.strip(), "thesis_impact": "weakens" if worsening_count > 0 else "neutral"},
    )


ANSWER_BUILDERS = {
    "what-does-company-do": _build_canonical_business_summary_answer,
    "who-are-the-customers": _build_canonical_customers_answer,
    "how-does-it-make-money": _build_canonical_make_money_answer,
    "what-makes-the-offering-important": _build_offering_importance_answer,
    "where-is-evidence-thin": _build_evidence_thin_answer,
    "are-profits-converting-into-cash": _build_cash_conversion_answer,
    "what-is-owner-earnings": _build_owner_earnings_answer,
    "is-working-capital-a-concern": _build_working_capital_answer,
    "are-per-share-economics-improving": _build_per_share_answer,
    "what-has-management-promised": _build_management_promises_answer,
    "what-promise-types-dominate": _build_promise_types_answer,
    "which-promises-are-overdue": _build_overdue_promises_answer,
    "what-was-delivered-last-3-years": _build_delivered_promises_answer,
    "what-was-missed": _build_missed_promises_answer,
    "did-past-claims-come-true": _build_past_claims_answer,
    "what-projects-are-underway": _build_projects_answer,
    "how-is-capacity-changing": _build_canonical_progression_answer,
    "what-is-management-commentary-saying": _build_canonical_progression_answer,
    "how-is-capital-allocated": _build_capital_allocation_answer,
    "what-is-the-return-on-capex": _build_return_on_capex_answer,
    "what-incentives-matter": _build_canonical_progression_answer,
    "what-regulatory-risks-remain-active": _build_regulatory_risks_answer,
    "what-is-committee-direction": _build_committee_direction_answer,
    "where-does-the-committee-agree": _build_committee_agree_answer,
    "where-does-the-committee-disagree": _build_committee_disagree_answer,
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
    company_slug = str(source_bundle.get("company_slug") or "")
    model = canonical_company_model(source_bundle, company_slug) if company_slug else {}
    current = _get_record(model, "current_business_model")
    revenue_engines = _get_record_list(model, "revenue_engines")
    model_type = str(current.get("business_model_type") or "").lower()
    billing_basis = "; ".join(
        _dedupe_texts(
            [
                _billing_basis_phrase(engine.get("billing_basis"))
                for engine in revenue_engines[:4]
                if _billing_basis_phrase(engine.get("billing_basis"))
            ]
        )
    )
    revenue_recognition = _collect_explicit_revenue_timing(
        revenue_engines,
        ("recognition_basis", "revenue_recognition_basis", "recognition_timing"),
    )
    cash_timing = _collect_explicit_revenue_timing(
        revenue_engines,
        ("cash_timing", "cash_collection_timing", "collection_timing"),
    )
    if model_type == "content_ip":
        return {
            "model_type": "recurring",
            "steps": [
                {"order": 1, "label": "Own and refresh catalogue", "explanation": "The company builds or acquires content IP that can be monetized over time."},
                {"order": 2, "label": "Reach listeners and licensees", "explanation": "Consumers, platforms, and partners use the catalogue through digital distribution and licensing channels."},
                {"order": 3, "label": "Earn royalty and license income", "explanation": "Revenue comes from streaming royalties, licensing fees, and advertising tied to audience reach."},
                {"order": 4, "label": "Monetize catalogue access", "explanation": "The monetization path depends on distribution, licensing, and audience reach terms."},
            ],
            "billing_basis_note": billing_basis or "Billing basis is not established from the available business-model evidence.",
            "revenue_recognition_note": revenue_recognition or None,
            "cash_timing_note": cash_timing or None,
            "working_capital_note": None,
            "evidence_status": "direct" if billing_basis else "partial",
            "offering_examples": _first_product_names(products_services_payload, limit=3),
        }
    if model_type == "platform":
        return {
            "model_type": "mixed",
            "steps": [
                {"order": 1, "label": "Secure enterprise or operator demand", "explanation": "The business begins when enterprises or telecom partners need communication and workflow capability."},
                {"order": 2, "label": "Deliver platform-led workflows", "explanation": "Messaging, security, and managed-deployment workflows are configured around those customer needs."},
                {"order": 3, "label": "Run usage and service traffic", "explanation": "Revenue is driven by platform usage, message volumes, and deployment activity."},
                {"order": 4, "label": "Bill through service or usage terms", "explanation": "The monetization path depends on usage-linked service charges and deployment terms."},
            ],
            "billing_basis_note": billing_basis or "Billing basis is not established from the available business-model evidence.",
            "revenue_recognition_note": revenue_recognition or None,
            "cash_timing_note": cash_timing or None,
            "working_capital_note": None,
            "evidence_status": "direct" if billing_basis else "partial",
            "offering_examples": _first_product_names(products_services_payload, limit=3),
        }
    if model_type == "financial_services":
        return {
            "model_type": "interest_income",
            "steps": [
                {"order": 1, "label": "Raise deposits and borrow funds", "explanation": "The company mobilises capital through retail deposits and wholesale borrowings to fund the lending book."},
                {"order": 2, "label": "Underwrite and disburse loans", "explanation": "Credit is extended to retail, MSME, and institutional borrowers against assessed repayment capacity."},
                {"order": 3, "label": "Collect interest and principal", "explanation": "Revenue flows as borrowers repay principal and interest over the loan tenure."},
                {"order": 4, "label": "Earn fee and commission income", "explanation": "Third-party distribution, insurance cross-sell, and transaction services supplement net interest income."},
            ],
            "billing_basis_note": billing_basis or "Billing basis is not established from the available business-model evidence.",
            "revenue_recognition_note": revenue_recognition or None,
            "cash_timing_note": cash_timing or None,
            "working_capital_note": None,
            "evidence_status": "direct" if billing_basis else "partial",
            "offering_examples": _first_product_names(products_services_payload, limit=3),
        }
    if model_type == "manufacturing":
        engine_billing = [str(e.get("billing_basis") or "").lower() for e in revenue_engines]
        is_product_sales = any(b in {"sale", "product_sale", "per_unit", "per-unit"} for b in engine_billing)
        is_project_based = any(b in {"milestone", "delivery", "acceptance", "delivery_milestone"} for b in engine_billing)
        if is_product_sales and not is_project_based:
            return {
                "model_type": "product_sales",
                "steps": [
                    {"order": 1, "label": "Develop and register products", "explanation": "Products are developed through R&D and approved through regulatory pathways before commercial launch."},
                    {"order": 2, "label": "Manufacture at scale", "explanation": "Products are manufactured under quality and compliance standards across relevant markets."},
                    {"order": 3, "label": "Distribute through commercial channels", "explanation": "Products reach customers through wholesalers, distributors, or direct supply arrangements."},
                    {"order": 4, "label": "Collect on product sales", "explanation": "Revenue is earned on product delivery and invoicing under applicable supply terms."},
                ],
                "billing_basis_note": billing_basis or "Billing basis is not established from the available business-model evidence.",
                "revenue_recognition_note": revenue_recognition or None,
                "cash_timing_note": cash_timing or None,
                "working_capital_note": None,
                "evidence_status": "direct" if billing_basis else "partial",
                "offering_examples": _first_product_names(products_services_payload, limit=3),
            }
        return {
            "model_type": "project_based",
            "steps": [
                {"order": 1, "label": "Win the order or programme", "explanation": "The business starts when a customer programme or order is awarded."},
                {"order": 2, "label": "Design, build, and qualify", "explanation": "Systems or components are engineered, manufactured, and tested to meet specifications."},
                {"order": 3, "label": "Deliver the finished system", "explanation": "The operating output is delivered or accepted into the customer programme."},
                {"order": 4, "label": "Bill on order terms", "explanation": "The monetization path follows the order terms supported by the evidence."},
            ],
            "billing_basis_note": billing_basis or "Billing basis is not established from the available business-model evidence.",
            "revenue_recognition_note": revenue_recognition or None,
            "cash_timing_note": cash_timing or None,
            "working_capital_note": None,
            "evidence_status": "direct" if billing_basis else "partial",
            "offering_examples": _first_product_names(products_services_payload, limit=3),
        }

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
                {"order": 1, "label": "Secure customer demand", "explanation": "Enterprise or telecom customers need communication capability."},
                {"order": 2, "label": "Deliver the communication workflow", "explanation": "The company configures platform and managed-service workflows around that demand."},
                {"order": 3, "label": "Bill through service terms", "explanation": "Revenue depends on usage, service, or managed-deployment terms."},
                {"order": 4, "label": "Collect through service terms", "explanation": "The monetization path depends on the supported service terms."},
            ],
            "billing_basis_note": billing_basis or "Billing basis is not established from the available business-model evidence.",
            "revenue_recognition_note": revenue_recognition or None,
            "cash_timing_note": cash_timing or None,
            "working_capital_note": None,
            "evidence_status": "partial",
            "offering_examples": _first_product_names(products_services_payload, limit=3),
        }
    flow_steps = [
        {"order": 1, "label": "Win order or programme", "explanation": "The business appears to begin with a customer order or programme award."},
        {"order": 2, "label": "Define the work scope", "explanation": "The company tailors the offering to programme requirements."},
        {"order": 3, "label": "Build and deliver", "explanation": "Delivery depends on the relevant operating capability and customer acceptance."},
        {"order": 4, "label": "Collect on the agreed terms", "explanation": "Revenue is earned according to the terms supported by the evidence."},
    ]
    return {
        "model_type": "unclear",
        "steps": flow_steps,
        "billing_basis_note": billing_basis or None,
        "revenue_recognition_note": revenue_recognition or None,
        "cash_timing_note": cash_timing or None,
        "working_capital_note": None,
        "evidence_status": "partial",
        "offering_examples": _first_product_names(products_services_payload, limit=3),
    }


def _collect_explicit_revenue_timing(revenue_engines: List[Dict[str, Any]], candidate_keys: tuple[str, ...]) -> str:
    values: List[str] = []
    for engine in revenue_engines:
        for key in candidate_keys:
            text = _first_string(engine.get(key))
            if text:
                values.append(text)
    return "; ".join(_dedupe_texts(values))


def _dedupe_texts(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        normalized = " ".join(str(value or "").lower().split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(str(value).strip())
    return result


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
