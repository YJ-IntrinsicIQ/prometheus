from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .sanitizer import sanitize_public_payload, sanitize_public_text


QUESTION_IDS = {
    "what-does-company-do",
    "who-are-the-customers",
    "how-does-it-make-money",
    "are-profits-converting-into-cash",
    "what-is-owner-earnings",
    "is-working-capital-a-concern",
    "are-per-share-economics-improving",
    "what-has-management-promised",
    "did-past-claims-come-true",
    "what-projects-are-underway",
    "how-is-capacity-changing",
    "what-is-management-commentary-saying",
    "how-is-capital-allocated",
    "what-incentives-matter",
    "what-should-i-ask-ir",
    "what-would-graham-worry-about",
    "what-would-buffett-focus-on",
    "where-would-fisher-be-curious",
    "what-would-munger-avoid",
    "how-would-lynch-explain-it",
    "what-can-break-the-thesis",
    "which-disclosure-is-missing",
    "what-evidence-would-change-the-view",
    "what-needs-management-clarification",
    "what-remains-unresolved",
}

QUESTION_UNCERTAINTY_PRIORITY: Dict[str, List[str]] = {
    "what-does-company-do": ["offering_coverage", "unclear_business_evolution", "weak_segment_disclosure", "forward_demand_visibility"],
    "who-are-the-customers": ["customer_concentration", "major_customer_revenue_share", "programme_exposure", "repeat_order_mix", "customer_dependency"],
    "how-does-it-make-money": ["product_revenue_mix", "milestone_billing_detail", "service_software_mix", "collection_timing"],
    "are-profits-converting-into-cash": ["working_capital_drivers", "reporting_basis", "capex_split"],
    "what-is-owner-earnings": ["capex_split", "reporting_basis"],
    "is-working-capital-a-concern": ["working_capital_drivers", "reporting_basis"],
    "are-per-share-economics-improving": ["share_count_comparability", "reporting_basis"],
    "what-has-management-promised": ["management_promise_tracking"],
    "did-past-claims-come-true": ["management_promise_tracking"],
    "how-is-capital-allocated": ["capex_split", "capacity_payoff"],
    "what-incentives-matter": ["management_promise_tracking"],
    "what-should-i-ask-ir": ["capex_split", "working_capital_drivers", "share_count_comparability"],
    "what-would-graham-worry-about": ["working_capital_drivers", "share_count_comparability", "product_revenue_mix"],
    "what-would-buffett-focus-on": ["capex_split", "product_revenue_mix", "working_capital_drivers", "share_count_comparability"],
    "where-would-fisher-be-curious": ["forward_demand_visibility", "capacity_payoff", "capability_contract_linkage"],
    "what-would-munger-avoid": ["management_promise_tracking", "product_revenue_mix"],
    "how-would-lynch-explain-it": ["product_revenue_mix", "working_capital_drivers"],
    "what-can-break-the-thesis": ["working_capital_drivers", "forward_demand_visibility", "product_revenue_mix"],
    "which-disclosure-is-missing": ["capex_split", "share_count_comparability", "reporting_basis", "product_revenue_mix"],
    "what-evidence-would-change-the-view": ["capex_split", "working_capital_drivers", "reporting_basis", "capacity_payoff"],
    "what-needs-management-clarification": ["capex_split", "working_capital_drivers", "reporting_basis", "management_promise_tracking"],
    "what-remains-unresolved": ["capex_split", "working_capital_drivers", "share_count_comparability", "product_revenue_mix"],
    "what-projects-are-underway": ["capacity_payoff", "forward_demand_visibility", "management_promise_tracking"],
    "how-is-capacity-changing": ["capacity_payoff", "forward_demand_visibility", "product_revenue_mix"],
    "what-is-management-commentary-saying": ["management_promise_tracking", "forward_demand_visibility", "capacity_payoff"],
}


UNCERTAINTY_THEME_REGISTRY: Dict[str, Dict[str, Any]] = {
    "capex_split": {
        "title": "Maintenance and growth capex are not separated",
        "simple_explanation": "Owner earnings are estimated, but maintenance and growth capex are not separated.",
        "why_it_matters": "This affects how much current cash generation looks truly owner-available rather than tied to ongoing reinvestment.",
        "affected_topics": ["Owner earnings", "Capital allocation", "Cash generation"],
        "affected_question_ids": [
            "what-is-owner-earnings",
            "how-is-capital-allocated",
            "what-incentives-matter",
            "which-disclosure-is-missing",
            "what-evidence-would-change-the-view",
            "what-needs-management-clarification",
            "what-remains-unresolved",
            "what-would-buffett-focus-on",
        ],
        "severity": "high",
        "status": "precision_limited",
        "evidence_status": "direct",
        "suggested_investor_question": "How much of current capex is maintenance rather than expansion?",
        "display_priority": 1,
    },
    "share_count_comparability": {
        "title": "Per-share comparability is incomplete",
        "simple_explanation": "Weighted-average or diluted share counts are incomplete, so per-share comparisons are less exact.",
        "why_it_matters": "This limits how confidently per-share economics can be compared across periods.",
        "affected_topics": ["Per-share economics", "Share-count comparability"],
        "affected_question_ids": [
            "are-per-share-economics-improving",
            "which-disclosure-is-missing",
            "what-evidence-would-change-the-view",
            "what-remains-unresolved",
            "what-would-buffett-focus-on",
            "what-would-graham-worry-about",
        ],
        "severity": "medium",
        "status": "precision_limited",
        "evidence_status": "direct",
        "suggested_investor_question": "What weighted-average and diluted share counts are needed to assess per-share performance cleanly?",
        "display_priority": 2,
    },
    "reporting_basis": {
        "title": "Financial reporting basis is not fully clear",
        "simple_explanation": "The reporting basis is not fully clear, which limits period-to-period comparability.",
        "why_it_matters": "If the basis changes or stays unclear, the same numbers can mean different things across years.",
        "affected_topics": ["Financial comparability", "Reported basis"],
        "affected_question_ids": [
            "are-profits-converting-into-cash",
            "are-per-share-economics-improving",
            "which-disclosure-is-missing",
            "what-evidence-would-change-the-view",
            "what-needs-management-clarification",
            "what-remains-unresolved",
        ],
        "severity": "medium",
        "status": "partial",
        "evidence_status": "derived",
        "suggested_investor_question": "Is the financial basis standalone or consolidated, and does it remain consistent across years?",
        "display_priority": 3,
    },
    "working_capital_drivers": {
        "title": "Working-capital pressure is visible, but the driver is not fully explained",
        "simple_explanation": "Receivables and inventory appear heavy, but the evidence does not yet show how much comes from billing cycles, production timing, or collection pressure.",
        "why_it_matters": "This can materially change how durable current cash conversion really is.",
        "affected_topics": ["Working capital", "Cash conversion", "Collections"],
        "affected_question_ids": [
            "are-profits-converting-into-cash",
            "is-working-capital-a-concern",
            "what-can-break-the-thesis",
            "what-evidence-would-change-the-view",
            "what-needs-management-clarification",
            "what-remains-unresolved",
            "what-would-graham-worry-about",
        ],
        "severity": "high",
        "status": "partial",
        "evidence_status": "direct",
        "suggested_investor_question": "What percentage of receivables is overdue beyond 180 days, and how much of current inventory reflects normal project timing?",
        "display_priority": 4,
    },
    "forward_demand_visibility": {
        "title": "Forward demand visibility is limited",
        "simple_explanation": "The available evidence does not clearly show forward demand or order-book support.",
        "why_it_matters": "Without clearer demand visibility, it is harder to judge whether current growth and capacity expansion are durable.",
        "affected_topics": ["Demand visibility", "Growth durability"],
        "affected_question_ids": [
            "what-does-company-do",
            "who-are-the-customers",
            "what-projects-are-underway",
            "how-is-capacity-changing",
            "what-can-break-the-thesis",
            "what-remains-unresolved",
            "where-would-fisher-be-curious",
        ],
        "severity": "medium",
        "status": "missing",
        "evidence_status": "partial",
        "suggested_investor_question": "What evidence is available on forward demand if order-book disclosure is absent?",
        "display_priority": 5,
    },
    "product_revenue_mix": {
        "title": "Product-level revenue contribution is not disclosed",
        "simple_explanation": "Product-level revenue contribution is not disclosed.",
        "why_it_matters": "Without that split, it is harder to judge which offerings truly drive economics and customer dependence.",
        "affected_topics": ["Revenue mix", "Product economics", "Customer exposure"],
        "affected_question_ids": [
            "what-does-company-do",
            "who-are-the-customers",
            "how-does-it-make-money",
            "what-projects-are-underway",
            "how-is-capacity-changing",
        ],
        "severity": "medium",
        "status": "missing",
        "evidence_status": "partial",
        "suggested_investor_question": "Which products contribute most of revenue and profit?",
        "display_priority": 6,
    },
    "customer_concentration": {
        "title": "Customer concentration is not clearly disclosed",
        "simple_explanation": "The available evidence does not clearly show how concentrated revenue is across major customers or programmes.",
        "why_it_matters": "Without concentration detail, it is harder to judge how dependent the business may be on a small number of relationships.",
        "affected_topics": ["Customer concentration", "Revenue dependency"],
        "affected_question_ids": ["who-are-the-customers", "what-can-break-the-thesis", "what-remains-unresolved"],
        "severity": "high",
        "status": "missing",
        "evidence_status": "partial",
        "suggested_investor_question": "How much revenue comes from the largest customers or programmes?",
        "display_priority": 6,
    },
    "major_customer_revenue_share": {
        "title": "Revenue share by major customer is not disclosed",
        "simple_explanation": "The available evidence does not separate revenue share by major customer.",
        "why_it_matters": "That limits how clearly customer importance and dependency can be assessed.",
        "affected_topics": ["Customer economics", "Revenue dependency"],
        "affected_question_ids": ["who-are-the-customers"],
        "severity": "medium",
        "status": "missing",
        "evidence_status": "partial",
        "suggested_investor_question": "What percentage of revenue comes from the top customers?",
        "display_priority": 7,
    },
    "programme_exposure": {
        "title": "Programme exposure is only partly visible",
        "simple_explanation": "The available evidence shows institutional programmes, but does not clearly separate exposure by major programme.",
        "why_it_matters": "Programme concentration can affect revenue timing, execution risk, and customer dependence.",
        "affected_topics": ["Programme exposure", "Execution dependency"],
        "affected_question_ids": ["who-are-the-customers", "what-can-break-the-thesis"],
        "severity": "medium",
        "status": "partial",
        "evidence_status": "partial",
        "suggested_investor_question": "How exposed is revenue to a small number of large programmes?",
        "display_priority": 8,
    },
    "repeat_order_mix": {
        "title": "Repeat-order mix is not clearly disclosed",
        "simple_explanation": "The available evidence does not show how much business comes from repeat orders versus new programme wins.",
        "why_it_matters": "Repeat-order visibility can change how durable customer relationships really are.",
        "affected_topics": ["Repeat-order visibility", "Customer durability"],
        "affected_question_ids": ["who-are-the-customers"],
        "severity": "medium",
        "status": "missing",
        "evidence_status": "partial",
        "suggested_investor_question": "How much revenue comes from repeat customers or repeat programme orders?",
        "display_priority": 9,
    },
    "customer_dependency": {
        "title": "Customer dependency is not fully visible",
        "simple_explanation": "The available evidence does not yet show how dependent the business is on any one customer relationship.",
        "why_it_matters": "This matters because even a technically strong business can be fragile if too much depends on a few buyers.",
        "affected_topics": ["Customer dependency"],
        "affected_question_ids": ["who-are-the-customers", "what-can-break-the-thesis"],
        "severity": "medium",
        "status": "partial",
        "evidence_status": "partial",
        "suggested_investor_question": "What customer relationships matter most to revenue durability?",
        "display_priority": 10,
    },
    "offering_coverage": {
        "title": "Offering coverage is still incomplete",
        "simple_explanation": "The available evidence shows key offering families, but it does not yet provide a fully complete offering map.",
        "why_it_matters": "Incomplete offering coverage can blur what the business really sells and which families matter most.",
        "affected_topics": ["Offering coverage", "Business framing"],
        "affected_question_ids": ["what-does-company-do"],
        "severity": "medium",
        "status": "partial",
        "evidence_status": "partial",
        "suggested_investor_question": "Which offering families drive most of the business today?",
        "display_priority": 11,
    },
    "unclear_business_evolution": {
        "title": "Business evolution is only partly clear",
        "simple_explanation": "The available history shows broad business phases, but the evolution is not yet fully clean or complete.",
        "why_it_matters": "That makes it harder to see exactly how the operating model changed over time.",
        "affected_topics": ["Business evolution"],
        "affected_question_ids": ["what-does-company-do"],
        "severity": "medium",
        "status": "partial",
        "evidence_status": "partial",
        "suggested_investor_question": "Which business changes are most clearly supported by the multi-year evidence?",
        "display_priority": 12,
    },
    "weak_segment_disclosure": {
        "title": "Segment disclosure is limited",
        "simple_explanation": "The available evidence does not provide a clean segment-style breakdown of the business.",
        "why_it_matters": "That limits how easily the business can be separated into its main economic buckets.",
        "affected_topics": ["Segment disclosure"],
        "affected_question_ids": ["what-does-company-do"],
        "severity": "low",
        "status": "partial",
        "evidence_status": "partial",
        "suggested_investor_question": "Which operating buckets best explain the business today?",
        "display_priority": 13,
    },
    "milestone_billing_detail": {
        "title": "Milestone billing detail is limited",
        "simple_explanation": "The available evidence suggests milestone-style billing, but it does not describe that timing in detail.",
        "why_it_matters": "Billing detail helps explain how revenue timing and cash timing can diverge.",
        "affected_topics": ["Billing mechanics", "Revenue timing"],
        "affected_question_ids": ["how-does-it-make-money"],
        "severity": "medium",
        "status": "partial",
        "evidence_status": "partial",
        "suggested_investor_question": "How much billing depends on customer acceptance or milestone completion?",
        "display_priority": 14,
    },
    "collection_timing": {
        "title": "Collection timing is not fully explained",
        "simple_explanation": "The available evidence shows slow cash conversion, but it does not fully explain collection timing by contract type.",
        "why_it_matters": "Collection timing shapes how quickly reported revenue becomes usable cash.",
        "affected_topics": ["Collections", "Cash timing"],
        "affected_question_ids": ["how-does-it-make-money", "are-profits-converting-into-cash"],
        "severity": "medium",
        "status": "partial",
        "evidence_status": "direct",
        "suggested_investor_question": "How long after delivery or acceptance does cash usually get collected?",
        "display_priority": 15,
    },
    "service_software_mix": {
        "title": "Software and service revenue mix is still unclear",
        "simple_explanation": "The available evidence does not clearly separate software, tool-based, and service revenue.",
        "why_it_matters": "That mix can change how recurring, scalable, and cash-efficient the business really is.",
        "affected_topics": ["Revenue mix", "Business model"],
        "affected_question_ids": [
            "how-does-it-make-money",
            "what-projects-are-underway",
            "how-is-capacity-changing",
        ],
        "severity": "medium",
        "status": "partial",
        "evidence_status": "partial",
        "suggested_investor_question": "How much revenue comes from software, tools, and service contracts respectively?",
        "display_priority": 7,
    },
    "capability_contract_linkage": {
        "title": "Capability-to-contract linkage is still thin",
        "simple_explanation": "The evidence lists capabilities, but it does not clearly show which ones drive the largest contract wins.",
        "why_it_matters": "That gap limits confidence about what really makes the offering important to customers.",
        "affected_topics": ["Offering importance", "Contract wins"],
        "affected_question_ids": [
            "what-projects-are-underway",
            "how-is-capacity-changing",
            "where-would-fisher-be-curious",
        ],
        "severity": "low",
        "status": "partial",
        "evidence_status": "partial",
        "suggested_investor_question": "Which capabilities directly help the company win its larger contracts?",
        "display_priority": 8,
    },
    "capacity_payoff": {
        "title": "Capacity expansion payoff is not yet clear",
        "simple_explanation": "The available history does not yet show whether added capacity has become economically meaningful.",
        "why_it_matters": "Capacity spending matters less than whether it later improves revenue quality, margins, or cash generation.",
        "affected_topics": ["Capacity expansion", "Growth payoff"],
        "affected_question_ids": [
            "what-does-company-do",
            "what-projects-are-underway",
            "what-evidence-would-change-the-view",
            "what-remains-unresolved",
            "where-would-fisher-be-curious",
        ],
        "severity": "medium",
        "status": "partial",
        "evidence_status": "partial",
        "suggested_investor_question": "Has the added capacity improved revenue, margins, or cash generation yet?",
        "display_priority": 9,
    },
    "export_mix": {
        "title": "Export mix is still unclear",
        "simple_explanation": "The available history does not clearly show how much revenue comes from export or non-domestic programmes.",
        "why_it_matters": "Geographic mix can affect growth runway, customer concentration, and programme risk.",
        "affected_topics": ["Revenue mix", "Geographic exposure"],
        "affected_question_ids": [
            "who-are-the-customers",
            "what-remains-unresolved",
        ],
        "severity": "low",
        "status": "missing",
        "evidence_status": "partial",
        "suggested_investor_question": "How much of revenue comes from export or non-domestic programmes?",
        "display_priority": 10,
    },
    "management_promise_tracking": {
        "title": "A clean promise-versus-delivery record is not available",
        "simple_explanation": "The available evidence does not preserve a clean promise-versus-delivery record for management.",
        "why_it_matters": "That limits how directly management credibility can be judged from follow-through rather than narrative.",
        "affected_topics": ["Management credibility", "Execution follow-through"],
        "affected_question_ids": [
            "what-has-management-promised",
            "did-past-claims-come-true",
            "what-incentives-matter",
            "what-should-i-ask-ir",
        ],
        "severity": "high",
        "status": "missing",
        "evidence_status": "missing",
        "suggested_investor_question": "Which management commitments from prior years can now be checked directly against actual outcomes?",
        "display_priority": 11,
    },
    "contradictory_financial_interpretation": {
        "title": "Upstream financial interpretations are not fully aligned",
        "simple_explanation": "Different upstream financial readings are not fully aligned on this issue yet.",
        "why_it_matters": "When two active interpretations disagree, the prudent next step is to resolve the gap before leaning too hard on one conclusion.",
        "affected_topics": ["Financial interpretation"],
        "affected_question_ids": [
            "what-incentives-matter",
            "what-evidence-would-change-the-view",
            "what-remains-unresolved",
        ],
        "severity": "high",
        "status": "contradictory",
        "evidence_status": "derived",
        "suggested_investor_question": "Which specific assumption or data point is causing the conflicting financial interpretation?",
        "display_priority": 12,
    },
}


def build_uncertainty_map(
    source_bundle: Dict[str, Any],
    *,
    business_journey_payload: Dict[str, Any],
    products_services_payload: Dict[str, Any],
    company_slug: str,
    generated_at: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    candidates = collect_uncertainty_candidates(
        source_bundle,
        business_journey_payload=business_journey_payload,
        products_services_payload=products_services_payload,
    )
    items = deduplicate_uncertainties(candidates)
    summary = _build_summary(items)
    coverage_status = "supported" if items else "unavailable"
    payload = sanitize_public_payload(
        {
            "schema_version": "ask_intrinsiciq_uncertainty_map.v1",
            "company_slug": company_slug,
            "items": items,
            "summary": summary,
            "coverage_status": coverage_status,
            "generated_at": generated_at,
        }
    )
    diagnostics = {
        "candidate_count": len(candidates),
        "item_count": len(items),
        "theme_keys": [str(item.get("_theme_key") or "") for item in candidates],
    }
    return payload, diagnostics


def collect_uncertainty_candidates(
    source_bundle: Dict[str, Any],
    *,
    business_journey_payload: Dict[str, Any],
    products_services_payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    truth = _source_payload(source_bundle, "financial_truth_pack")
    committee = _source_payload(source_bundle, "committee_synthesis")
    cim = _source_payload(source_bundle, "cim")

    for text in _get_string_list(truth, "precision_limits"):
        candidate = _candidate_from_text(text, evidence_status="direct")
        if candidate:
            candidates.append(candidate)
    for text in _get_string_list(_get_record(committee, "financial_committee_view"), "missing_financial_data"):
        candidate = _candidate_from_text(text, evidence_status="derived")
        if candidate:
            candidates.append(candidate)
    for text in _get_string_list(_get_record(committee, "financial_committee_view"), "unreliable_financial_data"):
        candidate = _candidate_from_text(text, evidence_status="unreliable")
        if candidate:
            candidate["status"] = "unreliable"
            candidates.append(candidate)
    for item in _get_record_list(committee, "critical_unknowns"):
        candidate = _candidate_from_text(_get_string(item, "unknown"), evidence_status="derived")
        if candidate:
            why = _get_string(item, "why_it_matters")
            if why:
                candidate["why_override"] = why
            candidates.append(candidate)
    for text in _get_string_list(truth, "investor_relevant_questions"):
        candidate = _candidate_from_question(text)
        if candidate:
            candidates.append(candidate)
    for text in business_journey_payload.get("open_questions", []) or []:
        candidate = _candidate_from_question(str(text or ""))
        if candidate:
            candidates.append(candidate)
    for text in products_services_payload.get("open_questions", []) or []:
        candidate = _candidate_from_question(str(text or ""))
        if candidate:
            candidates.append(candidate)
    if str(products_services_payload.get("customer_summary") or "").strip():
        candidates.extend(
            [
                {"_theme_key": "customer_concentration", "evidence_status": "partial"},
                {"_theme_key": "major_customer_revenue_share", "evidence_status": "partial"},
                {"_theme_key": "programme_exposure", "evidence_status": "partial"},
                {"_theme_key": "repeat_order_mix", "evidence_status": "partial"},
                {"_theme_key": "customer_dependency", "evidence_status": "partial"},
            ]
        )
    if str(products_services_payload.get("business_model_summary") or "").strip():
        candidates.extend(
            [
                {"_theme_key": "offering_coverage", "evidence_status": "partial"},
                {"_theme_key": "weak_segment_disclosure", "evidence_status": "partial"},
                {"_theme_key": "milestone_billing_detail", "evidence_status": "partial"},
                {"_theme_key": "collection_timing", "evidence_status": "direct"},
            ]
        )
    if business_journey_payload.get("historical_stages") or business_journey_payload.get("stages"):
        candidates.append({"_theme_key": "unclear_business_evolution", "evidence_status": "partial"})

    promise_items = []
    for yearly in _get_list(cim, "promises"):
        if isinstance(yearly, dict):
            promise_items.extend(_get_list(yearly, "items"))
    if not promise_items:
        candidates.append({"_theme_key": "management_promise_tracking", "evidence_status": "missing"})

    disagreements = _get_record(committee, "financial_committee_view").get("financial_disagreements")
    if isinstance(disagreements, list) and disagreements:
        candidates.append({"_theme_key": "contradictory_financial_interpretation", "evidence_status": "derived"})

    for metric in _get_list(truth, "partial_metrics"):
        candidate = _candidate_from_metric(metric, default_status="partial", evidence_status="partial")
        if candidate:
            candidates.append(candidate)
    for metric in _get_list(truth, "unreliable_metrics"):
        candidate = _candidate_from_metric(metric, default_status="unreliable", evidence_status="unreliable")
        if candidate:
            candidates.append(candidate)
    for metric in _get_list(truth, "invalid_or_quarantined_metrics"):
        candidate = _candidate_from_metric(metric, default_status="unreliable", evidence_status="unreliable")
        if candidate:
            candidates.append(candidate)

    investigation_questions = _get_record_list(committee, "investigation_questions")
    for candidate in candidates:
        key = str(candidate.get("_theme_key") or "")
        question = _find_matching_investor_question(key, investigation_questions)
        if question:
            candidate["suggested_question_override"] = question
    return candidates


def normalize_uncertainty(candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    key = str(candidate.get("_theme_key") or "")
    template = UNCERTAINTY_THEME_REGISTRY.get(key)
    if not template:
        return None
    item = {
        "id": f"uncertainty-{key}",
        "theme_key": key,
        "title": template["title"],
        "simple_explanation": candidate.get("simple_explanation_override") or template["simple_explanation"],
        "why_it_matters": candidate.get("why_override") or template["why_it_matters"],
        "affected_topics": list(template["affected_topics"]),
        "affected_question_ids": list(template["affected_question_ids"]),
        "severity": candidate.get("severity") or assign_uncertainty_severity(candidate),
        "status": candidate.get("status") or template["status"],
        "suggested_investor_question": candidate.get("suggested_question_override") or template["suggested_investor_question"],
        "evidence_status": candidate.get("evidence_status") or template["evidence_status"],
        "display_order": int(template["display_priority"]),
    }
    return sanitize_public_payload(item)


def deduplicate_uncertainties(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        key = str(candidate.get("_theme_key") or "")
        if key not in UNCERTAINTY_THEME_REGISTRY:
            continue
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(candidate)
            continue
        existing["evidence_status"] = _stronger_evidence_status(existing.get("evidence_status"), candidate.get("evidence_status"))
        existing["severity"] = _stronger_severity(existing.get("severity"), candidate.get("severity"))
        if not existing.get("suggested_question_override") and candidate.get("suggested_question_override"):
            existing["suggested_question_override"] = candidate["suggested_question_override"]
        if candidate.get("why_override") and len(str(candidate["why_override"])) > len(str(existing.get("why_override") or "")):
            existing["why_override"] = candidate["why_override"]
        existing_status = str(existing.get("status") or "")
        candidate_status = str(candidate.get("status") or "")
        if _status_rank(candidate_status) > _status_rank(existing_status):
            existing["status"] = candidate_status
    items = []
    for key in sorted(merged, key=lambda item: int(UNCERTAINTY_THEME_REGISTRY[item]["display_priority"])):
        normalized = normalize_uncertainty(merged[key])
        if normalized:
            items.append(normalized)
    for index, item in enumerate(items, start=1):
        item["display_order"] = index
    return items


def assign_uncertainty_severity(candidate: Dict[str, Any]) -> str:
    key = str(candidate.get("_theme_key") or "")
    template = UNCERTAINTY_THEME_REGISTRY.get(key) or {}
    return str(candidate.get("severity") or template.get("severity") or "medium")


def map_uncertainty_to_questions(item: Dict[str, Any], question_catalog: List[str]) -> List[str]:
    valid = set(question_catalog)
    return [question_id for question_id in item.get("affected_question_ids", []) or [] if question_id in valid]


def summarize_uncertainty_for_view(payload: Dict[str, Any]) -> Dict[str, Any]:
    items = payload.get("items", []) or []
    important_unknowns_count = len(items)
    high_severity_count = sum(1 for item in items if str(item.get("severity") or "") == "high")
    main_uncertainty = str(items[0].get("simple_explanation") or "") if items else ""
    unresolved_question_count = len(
        {
            str(item.get("suggested_investor_question") or "").strip()
            for item in items
            if str(item.get("suggested_investor_question") or "").strip()
        }
    )
    return {
        "importantUnknownsCount": important_unknowns_count,
        "highSeverityCount": high_severity_count,
        "mainUncertainty": main_uncertainty,
        "unresolvedQuestionCount": unresolved_question_count,
    }


def build_uncertainty_note_for_answer(
    *,
    question_id: str,
    answer_status: str,
    fallback_message: str,
    uncertainty_map_payload: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    items = (uncertainty_map_payload or {}).get("items", []) or []
    relevant = [item for item in items if question_id in (item.get("affected_question_ids") or [])]
    if relevant:
        ranked = rank_uncertainties_for_question(question_id, relevant)
        message = str(ranked[0].get("simple_explanation") or "").strip()
    else:
        message = str(fallback_message or "").strip()
        if not message and answer_status in {"supported"}:
            message = "The answer is supported, but a narrower limitation was not isolated."
        elif not message:
            message = "The current evidence still leaves open questions."
    return {
        "title": "Uncertainty note",
        "message": sanitize_public_text(message),
    }


def rank_uncertainties_for_question(question_id: str, candidate_uncertainties: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    priority_order = QUESTION_UNCERTAINTY_PRIORITY.get(question_id, [])
    priority_index = {theme: index for index, theme in enumerate(priority_order)}
    return sorted(
        candidate_uncertainties,
        key=lambda item: (
            priority_index.get(str(item.get("theme_key") or item.get("_theme_key") or ""), 999),
            -_severity_rank(item.get("severity")),
            int(item.get("display_order") or 999),
        ),
    )


def _build_summary(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "No material uncertainty could be mapped from the available evidence."
    top = items[:3]
    themes = [str(item.get("title") or "").strip().lower() for item in top if str(item.get("title") or "").strip()]
    if not themes:
        return "The current evidence still contains important unresolved questions."
    return sanitize_public_text(
        "The main open questions are "
        + ", ".join(themes[:-1] + [f"and {themes[-1]}"] if len(themes) > 1 else themes)
        + "."
    )


def _candidate_from_metric(metric: Any, *, default_status: str, evidence_status: str) -> Optional[Dict[str, Any]]:
    if not isinstance(metric, dict):
        return None
    metric_id = str(metric.get("metric_id") or metric.get("canonical_metric") or "").lower()
    if "owner_earnings" in metric_id or "fcf" in metric_id or "capex" in metric_id:
        return {"_theme_key": "capex_split", "status": default_status, "evidence_status": evidence_status}
    if "share" in metric_id or "eps" in metric_id or "per_share" in metric_id:
        return {"_theme_key": "share_count_comparability", "status": default_status, "evidence_status": evidence_status}
    if "receivable" in metric_id or "inventory" in metric_id or "cash_conversion" in metric_id:
        return {"_theme_key": "working_capital_drivers", "status": default_status, "evidence_status": evidence_status}
    return None


def _candidate_from_text(text: str, *, evidence_status: str) -> Optional[Dict[str, Any]]:
    lowered = str(text or "").lower()
    if not lowered.strip():
        return None
    if _contains_any(lowered, ["maintenance", "growth capex", "owner-earnings precision", "owner earnings precision", "derived fcf", "capex split"]):
        return {"_theme_key": "capex_split", "evidence_status": evidence_status}
    if _contains_any(lowered, ["weighted-average", "diluted share", "share-count", "share count"]):
        return {"_theme_key": "share_count_comparability", "evidence_status": evidence_status}
    if _contains_any(lowered, ["basis remains unclear", "reporting basis", "standalone versus consolidated", "standalone or consolidated"]):
        return {"_theme_key": "reporting_basis", "evidence_status": evidence_status}
    if _contains_any(lowered, ["receivable days", "inventory days", "working-capital", "working capital", "collection cadence", "collectability pressure"]):
        return {"_theme_key": "working_capital_drivers", "evidence_status": evidence_status}
    if _contains_any(lowered, ["forward demand", "order-book", "order book"]):
        return {"_theme_key": "forward_demand_visibility", "evidence_status": evidence_status}
    if _contains_any(lowered, ["product-level revenue", "offerings contribute the most revenue"]):
        return {"_theme_key": "product_revenue_mix", "evidence_status": evidence_status}
    if _contains_any(lowered, ["customer concentration", "top customer", "major customer"]):
        return {"_theme_key": "customer_concentration", "evidence_status": evidence_status}
    if _contains_any(lowered, ["repeat order", "repeat-order"]):
        return {"_theme_key": "repeat_order_mix", "evidence_status": evidence_status}
    if _contains_any(lowered, ["programme exposure", "program exposure"]):
        return {"_theme_key": "programme_exposure", "evidence_status": evidence_status}
    return None


def _candidate_from_question(text: str) -> Optional[Dict[str, Any]]:
    lowered = str(text or "").lower().strip()
    if not lowered:
        return None
    if _contains_any(lowered, ["receivable", "inventory", "collection", "working capital"]):
        return {"_theme_key": "working_capital_drivers", "evidence_status": "partial"}
    if _contains_any(lowered, ["forward demand", "order-book", "order book"]):
        return {"_theme_key": "forward_demand_visibility", "evidence_status": "partial"}
    if _contains_any(lowered, ["maintenance capex", "growth capex", "maintenance versus growth"]):
        return {"_theme_key": "capex_split", "evidence_status": "direct"}
    if _contains_any(lowered, ["weighted-average", "diluted share", "share counts"]):
        return {"_theme_key": "share_count_comparability", "evidence_status": "direct"}
    if _contains_any(lowered, ["standalone", "consolidated", "basis"]):
        return {"_theme_key": "reporting_basis", "evidence_status": "derived"}
    if _contains_any(lowered, ["which offerings contribute the most revenue", "products contribute most of revenue"]):
        return {"_theme_key": "product_revenue_mix", "evidence_status": "partial"}
    if _contains_any(lowered, ["largest customers", "major customers", "top customers"]):
        return {"_theme_key": "major_customer_revenue_share", "evidence_status": "partial"}
    if _contains_any(lowered, ["software", "tool-based", "service revenues"]):
        return {"_theme_key": "service_software_mix", "evidence_status": "partial"}
    if _contains_any(lowered, ["milestone", "acceptance"]):
        return {"_theme_key": "milestone_billing_detail", "evidence_status": "partial"}
    if _contains_any(lowered, ["collection", "cash collected", "cash collection"]):
        return {"_theme_key": "collection_timing", "evidence_status": "direct"}
    if _contains_any(lowered, ["which capabilities directly help", "win larger contracts"]):
        return {"_theme_key": "capability_contract_linkage", "evidence_status": "partial"}
    if _contains_any(lowered, ["added capacity", "capacity become economically meaningful"]):
        return {"_theme_key": "capacity_payoff", "evidence_status": "partial"}
    if _contains_any(lowered, ["export", "non-domestic"]):
        return {"_theme_key": "export_mix", "evidence_status": "partial"}
    return None


def _find_matching_investor_question(theme_key: str, investigation_questions: List[Dict[str, Any]]) -> str:
    for item in investigation_questions:
        question = _get_string(item, "question")
        candidate = _candidate_from_question(question) or _candidate_from_text(question, evidence_status="derived")
        if candidate and str(candidate.get("_theme_key") or "") == theme_key:
            return question
    return ""


def _severity_rank(value: Any) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(str(value or ""), 0)


def _stronger_severity(first: Any, second: Any) -> str:
    if _severity_rank(first) == 0 and _severity_rank(second) == 0:
        return ""
    return str(first if _severity_rank(first) >= _severity_rank(second) else second)


def _status_rank(value: str) -> int:
    return {
        "partial": 1,
        "missing": 2,
        "precision_limited": 3,
        "unreliable": 4,
        "contradictory": 5,
    }.get(str(value or ""), 0)


def _stronger_evidence_status(first: Any, second: Any) -> str:
    ranking = {"missing": 0, "partial": 1, "derived": 2, "direct": 3, "unreliable": 4}
    first_text = str(first or "")
    second_text = str(second or "")
    return first_text if ranking.get(first_text, -1) >= ranking.get(second_text, -1) else second_text


def _source_payload(source_bundle: Dict[str, Any], key: str) -> Dict[str, Any]:
    return ((source_bundle.get("sources") or {}).get(key) or {}).get("payload") or {}


def _get_record(value: Dict[str, Any], key: str) -> Dict[str, Any]:
    nested = value.get(key)
    return nested if isinstance(nested, dict) else {}


def _get_list(value: Dict[str, Any], key: str) -> List[Any]:
    nested = value.get(key)
    return nested if isinstance(nested, list) else []


def _get_record_list(value: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    return [item for item in _get_list(value, key) if isinstance(item, dict)]


def _get_string(value: Dict[str, Any], key: str) -> str:
    nested = value.get(key)
    return str(nested).strip() if isinstance(nested, str) and str(nested).strip() else ""


def _get_string_list(value: Dict[str, Any], key: str) -> List[str]:
    return [str(item).strip() for item in _get_list(value, key) if isinstance(item, str) and str(item).strip()]


def _contains_any(text: str, patterns: List[str]) -> bool:
    lowered = str(text or "").lower()
    return any(pattern in lowered for pattern in patterns)
