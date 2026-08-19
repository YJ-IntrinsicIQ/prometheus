from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .sanitizer import sanitize_public_payload, sanitize_public_text


MIGRATED_BUSINESS_QUESTIONS = {
    "what-does-company-do",
    "who-are-the-customers",
    "how-does-it-make-money",
}

MIGRATED_PROGRESSION_QUESTIONS = {
    "what-has-management-promised",
    "did-past-claims-come-true",
    "what-projects-are-underway",
    "how-is-capacity-changing",
    "what-is-management-commentary-saying",
    "how-is-capital-allocated",
    "what-incentives-matter",
}

_PROMISE_QUESTION_IDS = {"what-has-management-promised", "did-past-claims-come-true"}
_PROJECT_QUESTION_ID = "what-projects-are-underway"
_CAPACITY_QUESTION_ID = "how-is-capacity-changing"
_COMMENTARY_QUESTION_ID = "what-is-management-commentary-saying"

_MATERIAL_ANCHOR_WORDS = {
    "acquisition",
    "ai",
    "automation",
    "capex",
    "customer",
    "defence",
    "facility",
    "hangar",
    "hospital",
    "integration",
    "manufacturing",
    "platform",
    "product",
    "programme",
    "radar",
    "satellite",
    "service",
    "software",
    "testing",
    "throughput",
    "workflow",
    "solution",
    "system",
    "telecom",
    "enterprise",
    "workforce",
}
_PROMISE_ANCHOR_WORDS = _MATERIAL_ANCHOR_WORDS | {"commitment", "objective", "target", "intent", "future", "plan"}
_PROJECT_ANCHOR_WORDS = _MATERIAL_ANCHOR_WORDS | {"deployment", "implementation", "launch", "rollout", "build", "integration"}
_PROJECT_ANCHOR_WORDS = _PROJECT_ANCHOR_WORDS | {"software", "workflow", "solution", "system", "hospital", "telecom", "enterprise", "defense", "defence"}
_CAPACITY_PHYSICAL_WORDS = {
    "facility",
    "testing",
    "plant",
    "hangar",
    "integration",
    "clean",
    "room",
    "satellite",
    "radar",
    "infrastructure",
    "floor",
    "area",
    "upgradation",
    "expansion",
    "addition",
}
_CAPACITY_THROUGHPUT_WORDS = {"throughput", "platform", "service", "delivery", "distribution", "deployment", "processing"}
_CAPACITY_WORKFORCE_WORDS = {"workforce", "engineer", "recruitment", "training", "skill", "staff"}
_LOW_VALUE_CAPACITY_WORDS = {"customer base", "market size", "channel count", "revenue growth"}
_COMMENTARY_WORDS = {"commentary", "said", "stated", "according", "management", "focus", "risk", "strategy", "outlook"}

_CORE_BUSINESS_TERMS = {
    "platform",
    "messaging",
    "software",
    "telecom",
    "enterprise",
    "deployment",
    "integration",
    "automation",
    "manufacturing",
    "testing",
    "facility",
    "plant",
    "throughput",
    "service",
    "delivery",
    "product",
    "solution",
    "solutions",
    "radar",
    "satellite",
    "defense",
    "defence",
    "workflow",
    "ai",
    "customer",
}

_PROGRESSION_HR_WORDS = {
    "employee",
    "employees",
    "training",
    "skill",
    "skills",
    "learning",
    "development",
    "capability",
    "capability building",
    "enablement",
    "welfare",
    "talent",
    "vocational",
}

_OUTCOME_ONLY_PHRASES = {
    "positive impact",
    "quality of business outcomes",
    "described as having",
    "characteristics include",
    "business outcomes",
}

_PROGRESSION_SCaffold_PREFIXES = [
    re.compile(r"^advance execution on a bounded business objective(?: at [^,]+)? to deliver\s*", re.I),
    re.compile(r"^improve operating capability, control, or speed(?: at [^,]+)? to deliver\s*", re.I),
    re.compile(r"^support execution capacity and delivery readiness(?: at [^,]+)? to deliver\s*", re.I),
    re.compile(r"^integrate a purchased asset or business(?: at [^,]+)? to deliver\s*", re.I),
    re.compile(r"^extend the product set or system capability(?: at [^,]+)? to deliver\s*", re.I),
]

_GENERIC_PROGRESSION_HEADLINES = {
    "future outlook",
    "industry outlook",
    "capex - physical infrastructure",
    "capital investment in sustainability",
    "capital investment",
    "debt repayment",
    "equity issuance",
    "operational_initiative",
    "strategic objective",
    "future plan",
}

_GENERIC_REVENUE_LABELS = {
    "platform, messaging, managed deployment, or usage-linked service revenue",
}

_BUSINESS_CONTEXT_TAIL_MARKERS = [
    " with recent investments",
    " funded partly via",
    " funded in part by",
    " alongside ",
    " and uses related-party",
    " and uses bank financing",
    " qip",
    " esop",
    " capital raise",
    " related-party financing",
    " bank financing",
]


def build_business_journey_from_company_model(
    source_bundle: Dict[str, Any],
    *,
    company_slug: str,
    generated_at: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    model = canonical_company_model(source_bundle, company_slug)
    if not model:
        payload = _empty_business_journey(company_slug, generated_at)
        return payload, {"derived_from": [], "coverage_gate": "company_model_missing"}

    current_model = _record(model, "current_business_model")
    evolution = _records(model, "business_model_evolution")
    uncertainties = _records(model, "uncertainties")
    coverage = _coverage(model)

    historical = []
    for index, change in enumerate(evolution[:3], start=1):
        title = _first_text(change.get("what_changed"), "Business model change")
        period = _period_label(change.get("from_period"), change.get("to_period"))
        historical.append(
            {
                "id": _slugify(f"{period}-{title}") or f"business-model-change-{index}",
                "period_label": period or str(change.get("to_period") or change.get("from_period") or "historical").upper(),
                "title": sanitize_public_text(_truncate(title, 92)),
                "simple_description": sanitize_public_text(_sentence(_truncate(_first_text(change.get("what_changed"), change.get("evidence_of_change")), 260))),
                "significance": sanitize_public_text(_sentence(_truncate(_first_text(change.get("why_it_changed"), change.get("evidence_of_change")), 260))),
                "evidence_status": _evidence_status(change),
                "display_order": index,
            }
        )

    current_state = None
    if current_model:
        primary_business_summary = _primary_business_summary(current_model)
        current_state = {
            "id": "current-business-model",
            "period_label": str(current_model.get("source_period") or "current").upper(),
            "title": sanitize_public_text(_truncate(_first_text(current_model.get("business_model_type"), "Current business model").replace("_", " ").title(), 80)),
            "description": sanitize_public_text(_sentence(_truncate(primary_business_summary, 300))),
            "why_it_matters": sanitize_public_text(_sentence(_truncate(_first_text(current_model.get("economic_mechanism"), current_model.get("how_revenue_happens")), 280))),
            "evidence_status": _evidence_status(current_model),
            "display_order": len(historical) + 1,
        }

    stages = list(historical)
    if current_state:
        stages.append(
            {
                "id": current_state["id"],
                "period_label": current_state["period_label"],
                "title": current_state["title"],
                "simple_description": current_state["description"],
                "significance": current_state["why_it_matters"],
                "evidence_status": current_state["evidence_status"],
                "display_order": current_state["display_order"],
            }
        )

    payload = sanitize_public_payload(
        {
            "schema_version": "ask_intrinsiciq_business_journey.v1",
            "company_slug": company_slug,
            "summary": sanitize_public_text(_sentence(_primary_business_summary(current_model, fallback="The available evidence does not yet provide a reliable business summary."))),
            "stages": stages[:4],
            "historical_stages": historical,
            "current_state": current_state,
            "stated_direction": None,
            "current_direction": sanitize_public_text(_sentence(_first_text(current_model.get("economic_mechanism"), "The current direction is not yet clear from the available evidence."))),
            "open_questions": _uncertainty_questions(uncertainties),
            "coverage_status": "supported" if coverage == "supported" and current_model else "partial" if current_model else "unavailable",
            "derived_from": ["company_evidence"],
            "generated_at": generated_at,
        }
    )
    return payload, {"derived_from": ["company_evidence"], "coverage_gate": coverage}


def build_products_services_from_company_model(
    source_bundle: Dict[str, Any],
    *,
    business_journey_payload: Dict[str, Any],
    company_slug: str,
    generated_at: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    model = canonical_company_model(source_bundle, company_slug)
    if not model:
        payload = _empty_products_services(company_slug, generated_at)
        return payload, {"derived_from": [], "coverage_gate": "company_model_missing"}

    current_model = _record(model, "current_business_model")
    offerings = _records(model, "offerings")
    customers = _records(model, "customers")
    revenue_engines = _records(model, "revenue_engines")
    uncertainties = _records(model, "uncertainties")

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for index, offering in enumerate(offerings[:8], start=1):
        category = _first_text(offering.get("category"), "offerings").replace("_", " ").title()
        item = {
            "id": str(offering.get("offering_id") or f"offering-{index}"),
            "name": sanitize_public_text(_first_text(offering.get("name"), f"Offering {index}")),
            "group": category,
            "simple_explanation": sanitize_public_text(_sentence(_truncate(_first_text(offering.get("customer_problem_solved"), offering.get("description")), 260))),
            "customer_type": sanitize_public_text(_customer_summary(customers) or _join(current_model.get("who_pays")) or "Customer type is not clearly established."),
            "customer_types": _customer_types(customers, current_model),
            "role_in_business": sanitize_public_text(_first_text(offering.get("revenue_role"), "Offering role is not separately quantified.")),
            "revenue_model": sanitize_public_text(_sentence(_first_text(offering.get("revenue_model"), _revenue_summary(revenue_engines, current_model), "Revenue mechanism is not separately disclosed."))),
            "revenue_contribution_status": "unknown",
            "revenue_contribution": None,
            "evidence_status": _evidence_status(offering),
            "source_periods": [str(offering.get("source_period") or current_model.get("source_period") or "").upper()],
            "display_order": index,
        }
        grouped.setdefault(category, []).append(item)

    groups = []
    for group_index, (title, items) in enumerate(sorted(grouped.items()), start=1):
        groups.append(
            {
                "id": _slugify(title) or f"group-{group_index}",
                "title": title,
                "description": f"Grouped from the company's offering evidence under {title.lower()}.",
                "items": items,
            }
        )

    payload = sanitize_public_payload(
        {
            "schema_version": "ask_intrinsiciq_products_services.v1",
            "company_slug": company_slug,
            "summary": sanitize_public_text(_sentence(_primary_business_summary(current_model, fallback="The available evidence does not yet support a product/service summary."))),
            "groups": groups[:5],
            "business_model_summary": sanitize_public_text(_sentence(_primary_business_summary(current_model))),
            "customer_summary": sanitize_public_text(_sentence(_customer_summary(customers) or _join(current_model.get("who_pays")))),
            "revenue_logic_summary": sanitize_public_text(_sentence(_revenue_summary(revenue_engines, current_model))),
            "open_questions": _uncertainty_questions(uncertainties),
            "coverage_status": "supported" if groups else "partial",
            "derived_from": ["company_evidence"],
            "generated_at": generated_at,
        }
    )
    return payload, {"derived_from": ["company_evidence"], "coverage_gate": _coverage(model)}


def canonical_company_model(source_bundle: Dict[str, Any], company_slug: str) -> Dict[str, Any]:
    payload = _source_payload(source_bundle, "company_model")
    if str(payload.get("schema_version") or "") != "company_model.v1":
        return {}
    if str(payload.get("company_slug") or "") != company_slug:
        raise ValueError(f"CROSS_COMPANY_INTELLIGENCE_CONTAMINATION: requested_company={company_slug}; company_model.company_slug={payload.get('company_slug')}")
    return payload


def canonical_management_progression(source_bundle: Dict[str, Any], company_slug: str) -> Dict[str, Any]:
    payload = _source_payload(source_bundle, "management_progression")
    if str(payload.get("schema_version") or "") != "management_progression.v1":
        return {}
    if str(payload.get("company_slug") or "") != company_slug:
        raise ValueError(
            "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION: "
            f"requested_company={company_slug}; management_progression.company_slug={payload.get('company_slug')}"
        )
    return payload


def progression_items_for_question(progression: Dict[str, Any], question_id: str, *, company_model: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    items = _records(progression, "progression_items")
    if not items or _coverage(progression) == "insufficient_evidence":
        return []
    if question_id == "did-past-claims-come-true":
        selected = [item for item in items if _is_claim_view_item(item, company_model=company_model)]
        return sorted(selected, key=lambda item: _progression_rank(item, question_id, company_model=company_model), reverse=True)
    if question_id in _PROMISE_QUESTION_IDS:
        selected = [item for item in items if _is_promise_view_item(item, company_model=company_model)]
        return sorted(selected, key=lambda item: _progression_rank(item, question_id, company_model=company_model), reverse=True)
    if question_id == _PROJECT_QUESTION_ID:
        selected = [item for item in items if _is_project_view_item(item, company_model=company_model)]
        return sorted(selected, key=lambda item: _progression_rank(item, question_id, company_model=company_model), reverse=True)
    if question_id == _CAPACITY_QUESTION_ID:
        selected = [item for item in items if _is_capacity_view_item(item, company_model=company_model)]
        return sorted(selected, key=lambda item: _progression_rank(item, question_id, company_model=company_model), reverse=True)
    if question_id == _COMMENTARY_QUESTION_ID:
        selected = [item if _is_commentary_view_item(item, company_model=company_model) else None for item in items]
        selected = [item for item in selected if item is not None]
        return sorted(selected, key=lambda item: _progression_rank(item, question_id, company_model=company_model), reverse=True)
    if question_id == "how-is-capital-allocated":
        selected = _filter_progression(items, stream_types={"capital_allocation", "legacy_capital_allocation"}, event_types={"capital_deployment"})
        return sorted(selected, key=lambda item: _progression_rank(item, question_id, company_model=company_model), reverse=True)
    if question_id == "what-incentives-matter":
        return items
    return []


def summarize_progression_item(item: Dict[str, Any], question_id: str = "") -> Dict[str, Any]:
    events = _records(item, "events")
    implication = _record(item, "investor_implication")
    unresolved = _records(item, "unresolved")
    kind = _question_view_kind(question_id)
    event_text = _question_primary_text(item, question_id) or _first_event_text(events, roles={"commitment", "statement", "action", "milestone", "completion", "outcome"})
    current_state = _humanize_label(_first_text(item.get("current_status"), "unresolved"))
    if kind == "promise":
        unresolved_text = "What later evidence confirms or contradicts the commitment remains unproven."
        changed_text = _sentence(_truncate(_question_primary_text(item, question_id) or event_text, 220))
        headline = _sentence(_clean_progression_headline(_best_progression_headline(item.get("theme"), event_text)))
        evidence = _question_later_evidence(item, question_id) or _event_texts(events)[:3]
        turning_points = [
            {
                "period": _first_text(event.get("event_period"), event.get("source_period")),
                "label": _humanize_label(_first_text(event.get("role"), event.get("event_type"))),
                "description": _sentence(_truncate(_event_text(event), 220)),
            }
            for event in events[:3]
        ]
        return {
            "headline": headline,
            "current_state": current_state,
            "what_changed": changed_text,
            "why_it_changed": _first_text(implication.get("economic_mechanism"), "Forward-looking commitments only matter if later evidence confirms delivery."),
            "conviction_impact": _humanize_label(_first_text(implication.get("thesis_impact"), "unresolved")),
            "latest_evidence": [_sentence(_truncate(text, 220)) for text in evidence][:3],
            "unresolved_items": [_first_text(row.get("question"), row.get("why_it_matters")) for row in unresolved][:3] or [unresolved_text],
            "turning_points": turning_points,
        }
    if kind == "claim":
        claim_text = _question_primary_text(item, question_id) or event_text
        later_evidence = _question_later_evidence(item, question_id)
        verdict = _claim_verdict(item)
        return {
            "headline": _sentence(_clean_progression_headline(_best_progression_headline(item.get("theme"), claim_text))),
            "current_state": current_state,
            "what_changed": _sentence(_truncate(claim_text, 220)),
            "why_it_changed": _first_text(implication.get("economic_mechanism"), "Claims matter only if later evidence confirms the original promise."),
            "conviction_impact": _humanize_label(verdict),
            "latest_evidence": [_sentence(_truncate(text, 220)) for text in later_evidence[:3]],
            "unresolved_items": [_first_text(row.get("question"), row.get("why_it_matters")) for row in unresolved][:3] or ["Later evidence remains limited or incomplete."],
            "turning_points": [
                {
                    "period": _first_text(event.get("event_period"), event.get("source_period")),
                    "label": _humanize_label(_first_text(event.get("role"), event.get("event_type"))),
                    "description": _sentence(_truncate(_event_text(event), 220)),
                }
                for event in events[:4]
            ],
        }
    if kind == "project":
        return {
            "headline": _sentence(_clean_progression_headline(_best_progression_headline(item.get("theme"), event_text))),
            "current_state": current_state,
            "what_changed": _sentence(_truncate(event_text, 220)),
            "why_it_changed": _first_text(implication.get("economic_mechanism"), "Projects matter when they convert stated intent into operating capability or customer delivery."),
            "conviction_impact": _humanize_label(_first_text(implication.get("thesis_impact"), "unresolved")),
            "latest_evidence": [_sentence(_truncate(text, 220)) for text in _event_texts(events)[:3]],
            "unresolved_items": [_first_text(row.get("question"), row.get("why_it_matters")) for row in unresolved][:3],
            "turning_points": [
                {
                    "period": _first_text(event.get("event_period"), event.get("source_period")),
                    "label": _humanize_label(_first_text(event.get("role"), event.get("event_type"))),
                    "description": _sentence(_truncate(_event_text(event), 220)),
                }
                for event in events[:4]
            ],
        }
    if kind == "capacity":
        return {
            "headline": _sentence(_clean_progression_headline(_best_progression_headline(item.get("theme"), event_text))),
            "current_state": current_state,
            "what_changed": _sentence(_truncate(_capacity_focus_text(item, events), 220)),
            "why_it_changed": _first_text(implication.get("economic_mechanism"), "Capacity matters only if the business can produce, test, deliver, or serve more at useful economics."),
            "conviction_impact": _humanize_label(_first_text(implication.get("thesis_impact"), "unresolved")),
            "latest_evidence": [_sentence(_truncate(text, 220)) for text in _event_texts(events)[:3]],
            "unresolved_items": [_first_text(row.get("question"), row.get("why_it_matters")) for row in unresolved][:3],
            "turning_points": [
                {
                    "period": _first_text(event.get("event_period"), event.get("source_period")),
                    "label": _humanize_label(_first_text(event.get("role"), event.get("event_type"))),
                    "description": _sentence(_truncate(_event_text(event), 220)),
                }
                for event in events[:4]
            ],
        }
    if kind == "commentary":
        earlier_view = _earliest_commentary_text(events)
        later_view = _latest_commentary_text(events)
        changed = _commentary_change_text(earlier_view, later_view, events)
        stayed = _commentary_stayed_consistent_text(events)
        return {
            "headline": _sentence(_clean_progression_headline(_best_progression_headline(item.get("theme"), later_view or event_text))),
            "current_state": current_state,
            "what_changed": _sentence(_truncate(changed or later_view or event_text, 220)),
            "why_it_changed": _first_text(implication.get("economic_mechanism"), "Commentary matters because it shows how management frames execution, risk, and priorities over time."),
            "conviction_impact": _humanize_label(_first_text(implication.get("thesis_impact"), "unresolved")),
            "latest_evidence": [_sentence(_truncate(text, 220)) for text in _event_texts(events)[:3]],
            "unresolved_items": [_first_text(row.get("question"), row.get("why_it_matters")) for row in unresolved][:3],
            "turning_points": [
                {
                    "period": _first_text(event.get("event_period"), event.get("source_period")),
                    "label": _humanize_label(_first_text(event.get("role"), event.get("event_type"))),
                    "description": _sentence(_truncate(_event_text(event), 220)),
                }
                for event in events[:4]
            ],
            "earlier_view": earlier_view,
            "later_view": later_view,
            "what_stayed_consistent": stayed,
        }
    return {
        "headline": _sentence(_clean_progression_headline(_best_progression_headline(item.get("theme"), event_text))),
        "current_state": current_state,
        "what_changed": _sentence(_truncate(_strip_progression_scaffolding(event_text), 220)),
        "why_it_changed": _first_text(implication.get("economic_mechanism"), "The economic consequence remains unresolved."),
        "conviction_impact": _humanize_label(_first_text(implication.get("thesis_impact"), "unresolved")),
        "latest_evidence": [_sentence(_truncate(_strip_progression_scaffolding(text), 220)) for text in _event_texts(events)[:3]],
        "unresolved_items": [_first_text(row.get("question"), row.get("why_it_matters")) for row in unresolved][:3],
        "turning_points": [
            {
                "period": _first_text(event.get("event_period"), event.get("source_period")),
                "label": _humanize_label(_first_text(event.get("role"), event.get("event_type"))),
                "description": _sentence(_truncate(_strip_progression_scaffolding(_event_text(event)), 220)),
            }
            for event in events[:4]
        ],
    }


def _filter_progression(
    items: List[Dict[str, Any]],
    *,
    stream_types: set[str] | None = None,
    roles: set[str] | None = None,
    event_types: set[str] | None = None,
) -> List[Dict[str, Any]]:
    selected = []
    for item in items:
        item_streams = {str(value) for value in item.get("stream_types", []) or []}
        events = _records(item, "events")
        item_roles = {str(event.get("role") or "") for event in events}
        item_event_types = {str(event.get("event_type") or "") for event in events}
        if stream_types and item_streams & stream_types:
            selected.append(item)
            continue
        if roles and item_roles & roles:
            selected.append(item)
            continue
        if event_types and item_event_types & event_types:
            selected.append(item)
            continue
    return selected


def _progression_rank(item: Dict[str, Any], question_id: str, *, company_model: Dict[str, Any] | None = None) -> Tuple[int, int, int, int]:
    events = _records(item, "events")
    texts = [_strip_progression_scaffolding(_event_text(event)) for event in events]
    specific_count = sum(1 for text in texts if _is_specific_progression_text(text))
    outcome_count = sum(
        1
        for event in events
        if _first_text(event.get("operational_outcome"), event.get("financial_or_business_outcome"))
        and "thin" not in _first_text(event.get("operational_outcome"), event.get("financial_or_business_outcome")).lower()
    )
    promise_count = sum(1 for event in events if _first_text(event.get("statement_text"), event.get("future_intent"), event.get("promise_text"), event.get("project_text"), event.get("commentary_text"), event.get("milestone_text"), event.get("action_taken")))
    event_count = len(events)
    relevance_score = _business_relevance_score(item, question_id=question_id, company_model=company_model)
    if question_id == "did-past-claims-come-true":
        return (relevance_score, _later_evidence_count(item), outcome_count, specific_count)
    if question_id == "what-has-management-promised":
        return (relevance_score, promise_count, specific_count, _material_anchor_count(texts))
    if question_id == _PROJECT_QUESTION_ID:
        return (relevance_score + _project_materiality_score(item), specific_count, event_count, outcome_count)
    if question_id == _CAPACITY_QUESTION_ID:
        return (relevance_score + _capacity_materiality_score(item), specific_count, outcome_count, event_count)
    if question_id == _COMMENTARY_QUESTION_ID:
        return (relevance_score + _commentary_materiality_score(item), len(texts), specific_count, event_count)
    return (relevance_score, specific_count, event_count, outcome_count)


def _empty_business_journey(company_slug: str, generated_at: str) -> Dict[str, Any]:
    return {
        "schema_version": "ask_intrinsiciq_business_journey.v1",
        "company_slug": company_slug,
        "summary": "The available evidence does not yet support a reliable business journey.",
        "stages": [],
        "historical_stages": [],
        "current_state": None,
        "stated_direction": None,
        "current_direction": "Unavailable until the business evidence set is present.",
        "open_questions": ["Regenerate the business evidence set for this company."],
        "coverage_status": "unavailable",
        "derived_from": [],
        "generated_at": generated_at,
    }


def _empty_products_services(company_slug: str, generated_at: str) -> Dict[str, Any]:
    return {
        "schema_version": "ask_intrinsiciq_products_services.v1",
        "company_slug": company_slug,
        "summary": "The available evidence does not yet support a reliable products and services view.",
        "groups": [],
        "business_model_summary": "",
        "customer_summary": "",
        "revenue_logic_summary": "",
        "open_questions": ["Regenerate the business evidence set for this company."],
        "coverage_status": "unavailable",
        "derived_from": [],
        "generated_at": generated_at,
    }


def _source_payload(source_bundle: Dict[str, Any], source_name: str) -> Dict[str, Any]:
    source = ((source_bundle.get("sources") or {}).get(source_name) or {})
    payload = source.get("payload")
    return payload if isinstance(payload, dict) else {}


def _record(value: Dict[str, Any], key: str) -> Dict[str, Any]:
    nested = value.get(key)
    return nested if isinstance(nested, dict) else {}


def _records(value: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    nested = value.get(key)
    return [item for item in nested if isinstance(item, dict)] if isinstance(nested, list) else []


def _coverage(payload: Dict[str, Any]) -> str:
    return str(payload.get("coverage_status") or "insufficient_evidence")


def _evidence_status(item: Dict[str, Any]) -> str:
    level = str((_record(item, "confidence").get("level") or "")).lower()
    if level == "high":
        return "direct"
    if level == "medium":
        return "partial"
    return "missing" if not item.get("evidence") else "partial"


def _customer_summary(customers: List[Dict[str, Any]]) -> str:
    payers = []
    users = []
    for customer in customers:
        payers.append(str(customer.get("payer_type") or "").strip())
        users.append(str(customer.get("end_user_type") or "").strip())
    payers = _dedupe([value for value in payers if value])
    users = _dedupe([value for value in users if value])
    if payers and users:
        return f"Who pays: {_join(payers)}. Who uses: {_join(users)}."
    if payers:
        return f"Who pays: {_join(payers)}."
    return ""


def _customer_types(customers: List[Dict[str, Any]], current_model: Dict[str, Any]) -> List[str]:
    values = []
    for customer in customers:
        values.extend([customer.get("payer_type"), customer.get("end_user_type")])
    values.extend(current_model.get("who_pays") or [])
    values.extend(current_model.get("who_uses") or [])
    return _dedupe([str(value).strip() for value in values if str(value or "").strip()])


def _revenue_summary(revenue_engines: List[Dict[str, Any]], current_model: Dict[str, Any]) -> str:
    current_revenue = str(current_model.get("how_revenue_happens") or "").strip()
    model_type = str(current_model.get("business_model_type") or "").lower()
    revenue_descriptions = _dedupe([_first_text(engine.get("description"), engine.get("mechanism"), engine.get("name")) for engine in revenue_engines[:4]])

    if model_type == "content_ip":
        return "Catalogue ownership and audience reach generate streaming royalties, licensing fees, and advertising revenue."
    if model_type == "platform":
        return "Enterprise and telecom demand turns into messaging, managed deployments, and usage-linked service revenue."
    if model_type == "manufacturing":
        return "Customer orders become engineered systems or components through design, build, test, and delivery."
    if revenue_descriptions:
        return _join(revenue_descriptions) if len(revenue_descriptions) > 1 else revenue_descriptions[0]
    normalized_revenue = " ".join(current_revenue.lower().split()).strip(" .,!?:;")
    if current_revenue and normalized_revenue not in _GENERIC_REVENUE_LABELS:
        return current_revenue
    return _first_text(current_model.get("economic_mechanism"), current_model.get("what_company_does"), current_model.get("summary"))


def _primary_business_summary(current_model: Dict[str, Any], *, fallback: str = "") -> str:
    primary = _primary_business_clause(_first_text(current_model.get("what_company_does"), current_model.get("summary")))
    return primary or fallback


def _primary_business_clause(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip(" ,;:-—")
    if not text:
        return ""
    clauses = [clause.strip(" ,;:-—") for clause in text.split(";") if clause.strip(" ,;:-—")]
    candidate = clauses[0] if clauses else text
    lowered = candidate.lower()
    cut_index = len(candidate)
    for marker in _BUSINESS_CONTEXT_TAIL_MARKERS:
        index = lowered.find(marker)
        if index != -1 and index < cut_index:
            cut_index = index
    candidate = candidate[:cut_index].strip(" ,;:-—")
    return candidate or text


def _billing_basis_phrase(value: Any) -> str:
    text = " ".join(str(value or "").lower().split()).strip(" ,;:-")
    if not text:
        return ""
    if text in {"usage", "usage-linked", "usage_linked"}:
        return "usage-linked service charges"
    if text in {"milestone", "delivery", "delivery_or_acceptance", "acceptance"}:
        return "delivery or acceptance terms"
    if text in {"sale", "sales"}:
        return "product sale terms"
    if text in {"royalty", "royalties"}:
        return "royalty-based terms"
    if text in {"license", "licence", "licensing"}:
        return "license agreement terms"
    if text in {"ad_revenue", "advertising", "ads"}:
        return "advertising-supported terms"
    return text.replace("_", " ")


def _uncertainty_questions(uncertainties: List[Dict[str, Any]]) -> List[str]:
    return [_first_text(item.get("question"), item.get("why_it_matters")) for item in uncertainties[:4] if _first_text(item.get("question"), item.get("why_it_matters"))]


def _first_event_text(events: List[Dict[str, Any]], *, roles: set[str]) -> str:
    for event in events:
        if str(event.get("role") or "") in roles:
            text = _event_text(event)
            if text:
                return text
    return ""


def _question_view_kind(question_id: str) -> str:
    if question_id in _PROMISE_QUESTION_IDS:
        return "promise" if question_id == "what-has-management-promised" else "claim"
    if question_id == _PROJECT_QUESTION_ID:
        return "project"
    if question_id == _CAPACITY_QUESTION_ID:
        return "capacity"
    if question_id == _COMMENTARY_QUESTION_ID:
        return "commentary"
    return "generic"


def _question_primary_text(item: Dict[str, Any], question_id: str) -> str:
    events = _records(item, "events")
    kind = _question_view_kind(question_id)
    if kind in {"promise", "claim"}:
        return _first_event_text(events, roles={"commitment", "statement"})
    if kind == "project":
        return _first_event_text(events, roles={"action", "milestone", "completion", "outcome", "statement"})
    if kind == "capacity":
        return _capacity_focus_text(item, events)
    if kind == "commentary":
        return _first_event_text(events, roles={"statement"}) or _event_text(events[-1]) if events else ""
    return _first_event_text(events, roles={"commitment", "statement", "action", "milestone", "completion", "outcome"})


def _company_model_text(company_model: Dict[str, Any] | None) -> str:
    if not isinstance(company_model, dict):
        return ""
    current = _record(company_model, "current_business_model")
    parts: List[str] = []
    for key in ("summary", "what_company_does", "economic_mechanism", "how_revenue_happens", "business_model_type"):
        parts.append(_first_text(current.get(key)))
    for key in ("what_it_sells", "who_pays", "who_uses"):
        values = current.get(key)
        if isinstance(values, list):
            parts.extend(str(value) for value in values if str(value or "").strip())
    for record in _records(company_model, "offerings"):
        parts.extend(
            _first_text(record.get(key))
            for key in ("name", "description", "customer_problem_solved", "revenue_role", "category")
        )
    for record in _records(company_model, "revenue_engines"):
        parts.extend(_first_text(record.get(key)) for key in ("name", "mechanism", "description"))
    return " ".join(part for part in parts if part)


def _has_any_phrase(text: Any, phrases: set[str]) -> bool:
    lowered = str(text or "").lower()
    return any(phrase in lowered for phrase in phrases)


def _item_progression_text(item: Dict[str, Any], question_id: str = "") -> str:
    events = _records(item, "events")
    parts = [item.get("theme"), _question_primary_text(item, question_id)] if question_id else [item.get("theme")]
    parts.extend(_event_text(event) for event in events)
    return " ".join(part for part in parts if part)


def _business_relevance_score(item: Dict[str, Any], *, question_id: str, company_model: Dict[str, Any] | None = None) -> int:
    text = _item_progression_text(item, question_id).lower()
    if not text:
        return 0
    model_text = _company_model_text(company_model).lower()
    item_tokens = set(re.findall(r"[a-z0-9]+", text))
    model_tokens = set(re.findall(r"[a-z0-9]+", model_text))
    overlap = item_tokens & model_tokens
    score = len(overlap)
    if overlap & _CORE_BUSINESS_TERMS:
        score += 2
    if overlap & {"ai", "platform", "messaging", "telecom", "enterprise", "manufacturing", "testing", "facility", "plant", "deployment", "integration", "workflow"}:
        score += 1
    if _has_any_phrase(text, _PROGRESSION_HR_WORDS) and not (overlap & _CORE_BUSINESS_TERMS):
        score -= 2
    if question_id == _CAPACITY_QUESTION_ID:
        if _has_any_phrase(text, {"vocational", "training", "skill development", "skill building"}) and not _has_any_phrase(
            text,
            {"manufacturing", "testing", "throughput", "production", "service delivery", "deployment", "facility", "plant"},
        ):
            score -= 3
        if _has_any_phrase(text, {"acquisition", "integration"}) and not _has_any_phrase(text, {"facility", "manufacturing", "testing", "throughput", "delivery", "production"}):
            score -= 2
    if question_id == _PROJECT_QUESTION_ID:
        if _has_any_phrase(text, _OUTCOME_ONLY_PHRASES) and not _has_any_phrase(text, {"build", "deploy", "rollout", "install", "commission", "expand", "implement", "develop", "launch", "automation"}):
            score -= 3
    if question_id == _COMMENTARY_QUESTION_ID and not _has_any_phrase(text, _COMMENTARY_WORDS):
        score -= 2
    return score


def _has_active_execution_language(text: Any) -> bool:
    lowered = str(text or "").lower()
    return any(
        phrase in lowered
        for phrase in (
            "build",
            "deploy",
            "rollout",
            "install",
            "commission",
            "expand",
            "implement",
            "develop",
            "launch",
            "automation",
            "integration",
            "acquisition",
            "upgrade",
            "construction",
            "manufacturing",
            "testing",
        )
    )


def _has_operating_capacity_language(text: Any) -> bool:
    lowered = str(text or "").lower()
    if _has_any_phrase(lowered, {"customer base", "market size", "channel count", "revenue growth"}):
        return False
    if _has_any_phrase(lowered, {"vocational training facility", "training facility", "skill development centre", "skill development center"}) and not _has_any_phrase(
        lowered,
        {"manufacturing", "testing", "throughput", "production", "service delivery", "deployment", "facility", "plant"},
    ):
        return False
    return any(word in lowered for word in _CAPACITY_PHYSICAL_WORDS | _CAPACITY_THROUGHPUT_WORDS | _CAPACITY_WORKFORCE_WORDS)


def _claim_has_complete_chain(item: Dict[str, Any]) -> bool:
    events = _records(item, "events")
    if not events:
        return False
    primary = _question_primary_text(item, "did-past-claims-come-true")
    if not primary:
        return False
    later = _question_later_evidence(item, "did-past-claims-come-true")
    if not later:
        return False
    return any(str(event.get("role") or "") in {"commitment", "statement"} for event in events) and any(
        str(event.get("role") or "") in {"action", "milestone", "completion", "outcome"} for event in events
    )


def _question_later_evidence(item: Dict[str, Any], question_id: str) -> List[str]:
    events = _records(item, "events")
    kind = _question_view_kind(question_id)
    later_roles = {"action", "milestone", "completion", "outcome"}
    if kind == "commentary":
        later_roles = {"statement"}
    evidence = []
    for event in events:
        if str(event.get("role") or "") in later_roles:
            text = _event_text(event)
            if text:
                evidence.append(text)
    primary = _question_primary_text(item, question_id)
    if primary:
        evidence = [text for text in evidence if " ".join(text.lower().split()) != " ".join(primary.lower().split())]
    return _dedupe(evidence)


def _claim_verdict(item: Dict[str, Any]) -> str:
    status = str(item.get("current_status") or "").lower()
    if status == "delivered":
        return "DELIVERED"
    if status == "partially_delivered":
        return "PARTIALLY_DELIVERED"
    if status == "in_progress":
        return "IN_PROGRESS"
    if status == "failed":
        return "CONTRADICTED"
    if status == "abandoned":
        return "ABANDONED"
    if status == "reversed":
        return "SUPERSEDED"
    return "UNABLE_TO_VERIFY"


def _is_promise_view_item(item: Dict[str, Any], *, company_model: Dict[str, Any] | None = None) -> bool:
    events = _records(item, "events")
    item_streams = {str(value) for value in item.get("stream_types", []) or []}
    if not ({*item_streams} & {"commitment"} or any(str(event.get("role") or "") == "commitment" for event in events)):
        return False
    text = _item_progression_text(item, "what-has-management-promised")
    if not _has_material_anchor(text, _PROMISE_ANCHOR_WORDS):
        return False
    if _business_relevance_score(item, question_id="what-has-management-promised", company_model=company_model) < 1:
        return False
    if _has_any_phrase(text, _PROGRESSION_HR_WORDS) and not _has_any_phrase(text, _CORE_BUSINESS_TERMS):
        return False
    return True


def _is_claim_view_item(item: Dict[str, Any], *, company_model: Dict[str, Any] | None = None) -> bool:
    events = _records(item, "events")
    item_streams = {str(value) for value in item.get("stream_types", []) or []}
    if not ({*item_streams} & {"commitment"} or any(str(event.get("role") or "") in {"commitment", "statement"} for event in events)):
        return False
    if not _claim_has_complete_chain(item):
        return False
    if _business_relevance_score(item, question_id="did-past-claims-come-true", company_model=company_model) < 1:
        return False
    return True


def _is_project_view_item(item: Dict[str, Any], *, company_model: Dict[str, Any] | None = None) -> bool:
    item_streams = {str(value) for value in item.get("stream_types", []) or []}
    if "project" not in item_streams:
        return False
    text = _item_progression_text(item, _PROJECT_QUESTION_ID)
    if not _has_material_anchor(text, _PROJECT_ANCHOR_WORDS):
        return False
    if not _has_active_execution_language(text):
        return False
    if _has_any_phrase(text, _OUTCOME_ONLY_PHRASES) and not _has_any_phrase(text, {"build", "deploy", "rollout", "install", "commission", "expand", "implement", "develop", "launch", "automation"}):
        return False
    if _business_relevance_score(item, question_id=_PROJECT_QUESTION_ID, company_model=company_model) < 1:
        return False
    return True


def _is_capacity_view_item(item: Dict[str, Any], *, company_model: Dict[str, Any] | None = None) -> bool:
    item_streams = {str(value) for value in item.get("stream_types", []) or []}
    if "commentary" in item_streams:
        return False
    text = _item_progression_text(item, _CAPACITY_QUESTION_ID)
    lowered = text.lower()
    if any(marker in lowered for marker in _LOW_VALUE_CAPACITY_WORDS):
        return False
    if not _has_operating_capacity_language(text):
        return False
    if _has_any_phrase(lowered, {"vocational training facility", "training facility", "skill development centre", "skill development center"}) and not _has_any_phrase(
        lowered,
        {"manufacturing", "testing", "throughput", "production", "service delivery", "deployment", "facility", "plant"},
    ):
        return False
    if _business_relevance_score(item, question_id=_CAPACITY_QUESTION_ID, company_model=company_model) < 1:
        return False
    if "capacity" in item_streams and _has_material_anchor(lowered, _MATERIAL_ANCHOR_WORDS):
        return True
    return True


def _is_commentary_view_item(item: Dict[str, Any], *, company_model: Dict[str, Any] | None = None) -> bool:
    item_streams = {str(value) for value in item.get("stream_types", []) or []}
    if "commentary" not in item_streams:
        return False
    text = _item_progression_text(item, _COMMENTARY_QUESTION_ID)
    if not text or not _has_any_phrase(text, _COMMENTARY_WORDS):
        return False
    if _business_relevance_score(item, question_id=_COMMENTARY_QUESTION_ID, company_model=company_model) < 1:
        return False
    return True


def _capacity_focus_text(item: Dict[str, Any], events: List[Dict[str, Any]]) -> str:
    theme = _first_text(item.get("theme"))
    if theme:
        return theme
    return _first_event_text(events, roles={"action", "milestone", "completion", "outcome"}) or _first_event_text(events, roles={"statement"})


def _earliest_commentary_text(events: List[Dict[str, Any]]) -> str:
    return _first_event_text(events, roles={"statement"}) or _event_text(events[0]) if events else ""


def _latest_commentary_text(events: List[Dict[str, Any]]) -> str:
    if not events:
        return ""
    for event in reversed(events):
        text = _event_text(event)
        if text:
            return text
    return ""


def _commentary_change_text(earlier: str, later: str, events: List[Dict[str, Any]]) -> str:
    if earlier and later and earlier != later:
        return f"Earlier commentary emphasized {earlier}; later commentary emphasized {later}."
    if later:
        return later
    return _first_event_text(events, roles={"statement"})


def _commentary_stayed_consistent_text(events: List[Dict[str, Any]]) -> str:
    texts = _event_texts(events)
    if len(texts) <= 1:
        return ""
    first = texts[0]
    if all(text == first for text in texts[1:]):
        return first
    return _first_text(events[-1].get("statement_text"), events[-1].get("action_taken"))


def _has_material_anchor(text: Any, anchor_words: set[str]) -> bool:
    words = set(re.findall(r"[a-z0-9]+", str(text or "").lower()))
    return bool(words & anchor_words)


def _later_evidence_count(item: Dict[str, Any]) -> int:
    return len(_question_later_evidence(item, "did-past-claims-come-true"))


def _material_anchor_count(texts: List[str]) -> int:
    count = 0
    for text in texts:
        if _has_material_anchor(text, _MATERIAL_ANCHOR_WORDS):
            count += 1
    return count


def _project_materiality_score(item: Dict[str, Any]) -> int:
    text = " ".join(_event_texts(_records(item, "events")) + [_first_text(item.get("theme"))]).lower()
    words = set(re.findall(r"[a-z0-9]+", text))
    score = len(_records(item, "events"))
    score += 4 if words & {"facility", "manufacturing", "testing", "hangar", "plant", "integration", "deployment"} else 0
    score += 3 if words & {"platform", "product", "project", "programme", "programme", "rollout", "implementation", "acquisition"} else 0
    score += 2 if words & {"customer", "defence", "enterprise", "satellite", "radar", "ai"} else 0
    score += len(words & _MATERIAL_ANCHOR_WORDS)
    return score


def _capacity_materiality_score(item: Dict[str, Any]) -> int:
    text = " ".join(_event_texts(_records(item, "events")) + [_first_text(item.get("theme"))]).lower()
    words = set(re.findall(r"[a-z0-9]+", text))
    score = len(_records(item, "events"))
    score += 20 if words & _CAPACITY_PHYSICAL_WORDS else 0
    score += 10 if words & {"manufacturing", "testing"} else 0
    score += 6 if words & _CAPACITY_THROUGHPUT_WORDS else 0
    score += 2 if words & _CAPACITY_WORKFORCE_WORDS else 0
    score -= 5 if any(marker in text for marker in _LOW_VALUE_CAPACITY_WORDS) else 0
    return score


def _commentary_materiality_score(item: Dict[str, Any]) -> int:
    events = _records(item, "events")
    texts = _event_texts(events)
    score = len(events) * 2
    score += _material_anchor_count(texts)
    score += 2 if len(texts) > 1 else 0
    score += 1 if any(word in " ".join(texts).lower() for word in {"risk", "strategy", "focus", "outlook", "utilization", "capacity"}) else 0
    return score


def _event_texts(events: List[Dict[str, Any]]) -> List[str]:
    return _dedupe([_event_text(event) for event in events if _event_text(event)])


def _event_text(event: Dict[str, Any]) -> str:
    return _first_text(
        event.get("statement_text"),
        event.get("action_taken"),
        event.get("future_intent"),
        event.get("promise_text"),
        event.get("project_text"),
        event.get("commentary_text"),
        event.get("milestone_text"),
        event.get("outcome_text"),
        event.get("operational_outcome"),
        event.get("financial_or_business_outcome"),
    )


def _period_label(start: Any, end: Any) -> str:
    start_text = str(start or "").upper()
    end_text = str(end or "").upper()
    if start_text and end_text and start_text != end_text:
        return f"{start_text} → {end_text}"
    return end_text or start_text


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            joined = _join([str(item).strip() for item in value if str(item).strip()])
            if joined:
                return joined
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _join(values: Any) -> str:
    if not isinstance(values, list):
        return str(values or "").strip()
    return "; ".join(_dedupe([str(value).strip() for value in values if str(value).strip()]))


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        normalized = " ".join(value.lower().split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return result


def _truncate(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") + "."


def _sentence(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    text = text.replace("...", "").replace("…", "").strip(" ,;:-")
    return text if text.endswith((".", "?", "!")) else text + "."


def _clean_progression_headline(value: Any) -> str:
    text = _strip_progression_scaffolding(value)
    if len(text) > 110:
        text = text[:110].rsplit(" ", 1)[0].strip(" ,;:-")
    return text or "Management progression"


def _best_progression_headline(theme: Any, event_text: Any) -> str:
    theme_text = _strip_progression_scaffolding(theme)
    event_text = _strip_progression_scaffolding(event_text)
    if not theme_text:
        return event_text
    if _is_generic_progression_headline(theme_text) and event_text:
        return event_text
    if len(theme_text.split()) <= 7 and len(event_text.split()) >= len(theme_text.split()) + 3:
        return event_text
    if len(theme_text) < 24 and len(event_text) > len(theme_text):
        return event_text
    return theme_text or event_text


def _strip_progression_scaffolding(value: Any) -> str:
    text = " ".join(str(value or "").replace("...", "").replace("…", "").split()).strip(" ,;:-")
    for pattern in _PROGRESSION_SCaffold_PREFIXES:
        text = pattern.sub("", text).strip(" ,;:-")
    return text


def _is_specific_progression_text(text: str) -> bool:
    normalized = " ".join(str(text or "").split()).lower().strip(" .,!?:;")
    if not normalized:
        return False
    if normalized in _GENERIC_PROGRESSION_HEADLINES:
        return False
    return len(normalized.split()) >= 4


def _is_generic_progression_headline(text: str) -> bool:
    normalized = " ".join(str(text or "").split()).lower().strip(" .,!?:;")
    if not normalized:
        return True
    return normalized in _GENERIC_PROGRESSION_HEADLINES or len(normalized.split()) <= 3


def _humanize_label(value: Any) -> str:
    text = " ".join(str(value or "").replace("_", " ").split()).strip(" ,;:-")
    return text[:1].upper() + text[1:] if text else "Unresolved"


def _slugify(value: Any) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()))
