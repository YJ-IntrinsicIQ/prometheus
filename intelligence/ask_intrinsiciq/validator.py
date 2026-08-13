from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Set

from .sanitizer import contains_forbidden_public_term

PROMOTIONAL_TERMS = {
    "world-class",
    "revolutionary",
    "cutting-edge",
    "market-leading",
}

FORBIDDEN_INVESTMENT_TERMS = {
    "buy",
    "sell",
    "hold",
    "target price",
}


def validate_company_research_view(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    required = {
        "schemaVersion",
        "company",
        "coverage",
        "categories",
        "businessJourney",
        "productsAndServices",
        "financialVisuals",
        "generatedAt",
        "sourceState",
    }
    missing = sorted(required - set(payload))
    if missing:
        errors.append(f"missing required top-level fields: {', '.join(missing)}")
        return errors
    company = payload.get("company") or {}
    if not str(company.get("companySlug") or "").strip():
        errors.append("company.companySlug is required")
    if not str(payload.get("schemaVersion") or "").strip():
        errors.append("schemaVersion is required")
    if not str(payload.get("generatedAt") or "").strip():
        errors.append("generatedAt is required")
    errors.extend(_validate_unique_ids(payload))
    errors.extend(_validate_answer_cards(payload))
    errors.extend(_validate_source_state(payload))
    errors.extend(_validate_public_strings(payload))
    errors.extend(_validate_source_freshness(payload))
    try:
        json.dumps(payload, ensure_ascii=False)
    except TypeError as exc:
        errors.append(f"public output is not JSON serializable: {exc}")
    return errors


def build_validation_report(*, generated_at: str, outputs_validated: List[str], errors: List[str], warnings: List[str]) -> Dict[str, Any]:
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "warnings": warnings,
        "checks_run": [
            "required_fields",
            "company_slug_present",
            "schema_version_present",
            "timestamp_present",
            "forbidden_public_terms",
            "unique_ids",
            "answer_card_shape",
            "business_journey_shape",
            "answer_cards_payload_shape",
            "financial_visual_summaries_shape",
            "uncertainty_map_shape",
            "source_freshness_gate",
            "json_serializable",
        ],
        "outputs_validated": outputs_validated,
        "generated_at": generated_at,
    }


def _validate_unique_ids(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    category_ids: Set[str] = set()
    question_ids: Set[str] = set()
    answer_ids: Set[str] = set()
    for category in payload.get("categories", []):
        category_id = str(category.get("id") or "")
        if category_id in category_ids:
            errors.append(f"duplicate category id: {category_id}")
        category_ids.add(category_id)
        for question in category.get("questions", []):
            question_id = str(question.get("id") or "")
            if question_id in question_ids:
                errors.append(f"duplicate question id: {question_id}")
            question_ids.add(question_id)
    for answer in payload.get("answerCards", []) if isinstance(payload.get("answerCards"), list) else []:
        answer_id = str(answer.get("id") or "")
        if answer_id in answer_ids:
            errors.append(f"duplicate answer id: {answer_id}")
        answer_ids.add(answer_id)
    return errors


def _validate_answer_cards(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    visual_ids = {str(item.get("id") or "") for item in payload.get("financialVisuals", [])}
    for answer in payload.get("answerCards", []) if isinstance(payload.get("answerCards"), list) else []:
        key_points = answer.get("keyPoints", [])
        if len(key_points) > 4:
            errors.append(f"answer {answer.get('id')} has more than 4 keyPoints")
        next_questions = answer.get("nextQuestions", [])
        if len(next_questions) != 3:
            errors.append(f"answer {answer.get('id')} must have exactly 3 nextQuestions")
        for ref in answer.get("financialVisualRefs", []):
            if ref not in visual_ids:
                errors.append(f"answer {answer.get('id')} references missing financial visual: {ref}")
    source_state = payload.get("sourceState") or {}
    if not payload.get("categories") and source_state.get("contentStatus") not in {"partial", "incomplete", "unavailable"}:
        errors.append("empty sections are allowed only when sourceState.contentStatus is incomplete or unavailable")
    return errors


def _validate_source_state(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    source_state = payload.get("sourceState") or {}
    uncertainty_summary = source_state.get("uncertaintySummary")
    if uncertainty_summary is None:
        return errors
    required = {
        "importantUnknownsCount",
        "highSeverityCount",
        "mainUncertainty",
        "unresolvedQuestionCount",
    }
    missing = sorted(required - set(uncertainty_summary))
    if missing:
        errors.append(f"sourceState.uncertaintySummary is missing fields: {', '.join(missing)}")
    return errors


def _validate_source_freshness(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    source_state = payload.get("sourceState") or {}
    freshness = source_state.get("sourceFreshness") or {}
    if not freshness:
        return errors
    freshness_status = str(freshness.get("freshnessStatus") or "").lower()
    if freshness_status not in {"fresh", "partial", "unavailable"}:
        errors.append(f"sourceState.sourceFreshness.freshnessStatus is invalid: {freshness_status or 'missing'}")
    if freshness_status == "stale":
        errors.append("sourceState.sourceFreshness indicates stale upstream inputs")
    checked_at = _parse_iso(payload.get("generatedAt"))
    latest_source_generated_at = _parse_iso(freshness.get("latestSourceGeneratedAt"))
    if checked_at and latest_source_generated_at and latest_source_generated_at > checked_at:
        errors.append("sourceState.sourceFreshness.latestSourceGeneratedAt is newer than generatedAt")
    stale_sources = freshness.get("staleSources") or []
    if stale_sources:
        errors.append(f"sourceState.sourceFreshness contains stale sources: {', '.join(str(item) for item in stale_sources)}")
    if source_state.get("contentStatus") == "supported" and freshness_status != "fresh":
        errors.append("supported sourceState content requires fresh upstream inputs")
    return errors


def _validate_public_strings(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    def walk(value: Any, trail: str) -> None:
        if isinstance(value, str) and contains_forbidden_public_term(value):
            errors.append(f"forbidden public term found at {trail}")
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{trail}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{trail}[{index}]")

    walk(payload, "company_research_view")
    return errors


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def validate_business_journey_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    required = {
        "schema_version",
        "company_slug",
        "summary",
        "stages",
        "historical_stages",
        "current_state",
        "stated_direction",
        "current_direction",
        "open_questions",
        "coverage_status",
        "generated_at",
    }
    missing = sorted(required - set(payload))
    if missing:
        return [f"business_journey missing required top-level fields: {', '.join(missing)}"]
    stages = payload.get("stages", []) or []
    historical_stages = payload.get("historical_stages", []) or []
    if len(stages) > 4:
        errors.append("business_journey has more than 4 total stages")
    if len(historical_stages) > 3:
        errors.append("business_journey has more than 3 historical stages")
    ids: Set[str] = set()
    orders: List[int] = []
    previous_period = None
    for stage in stages:
        stage_id = str(stage.get("id") or "")
        if stage_id in ids:
            errors.append(f"duplicate business_journey stage id: {stage_id}")
        ids.add(stage_id)
        period = str(stage.get("period_label") or "").strip()
        if not period:
            errors.append(f"business_journey stage missing period_label: {stage_id}")
        order = int(stage.get("display_order") or 0)
        orders.append(order)
        if previous_period and _period_sort_key(period) < _period_sort_key(previous_period):
            errors.append("business_journey stages are not chronological")
        previous_period = period
        for key in ("title", "simple_description", "significance"):
            value = str(stage.get(key) or "")
            if contains_forbidden_public_term(value):
                errors.append(f"forbidden public term found in business_journey stage {stage_id}.{key}")
    if orders and orders != list(range(1, len(orders) + 1)):
        errors.append("business_journey display_order values must be unique and sequential")
    if not stages and payload.get("coverage_status") not in {"partial", "unavailable"}:
        errors.append("empty business_journey stages require partial or unavailable coverage")
    current_direction = str(payload.get("current_direction") or "")
    if "will become" in current_direction.lower():
        errors.append("business_journey current_direction claims certainty beyond evidence")
    current_state = payload.get("current_state")
    if current_state is not None and not isinstance(current_state, dict):
        errors.append("business_journey current_state must be an object or null")
    stated_direction = payload.get("stated_direction")
    if stated_direction is not None and not isinstance(stated_direction, dict):
        errors.append("business_journey stated_direction must be an object or null")
    if contains_forbidden_public_term(str(payload.get("summary") or "")):
        errors.append("forbidden public term found in business_journey summary")
    try:
        json.dumps(payload, ensure_ascii=False)
    except TypeError as exc:
        errors.append(f"business_journey is not JSON serializable: {exc}")
    return errors


def validate_products_services_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    required = {
        "schema_version",
        "company_slug",
        "summary",
        "groups",
        "business_model_summary",
        "customer_summary",
        "revenue_logic_summary",
        "open_questions",
        "coverage_status",
        "generated_at",
    }
    missing = sorted(required - set(payload))
    if missing:
        return [f"products_services missing required top-level fields: {', '.join(missing)}"]
    groups = payload.get("groups", []) or []
    if len(groups) > 5:
        errors.append("products_services has more than 5 groups")
    group_ids: Set[str] = set()
    item_ids: Set[str] = set()
    normalized_names: Set[str] = set()
    for group in groups:
        group_id = str(group.get("id") or "")
        if group_id in group_ids:
            errors.append(f"duplicate products_services group id: {group_id}")
        group_ids.add(group_id)
        items = group.get("items", []) or []
        if not items:
            errors.append(f"products_services group must not be empty: {group_id}")
        previous_order = 0
        for item in items:
            item_id = str(item.get("id") or "")
            if item_id in item_ids:
                errors.append(f"duplicate products_services item id: {item_id}")
            item_ids.add(item_id)
            name = str(item.get("name") or "").strip()
            explanation = str(item.get("simple_explanation") or "").strip()
            revenue_model = str(item.get("revenue_model") or "").strip()
            if not name:
                errors.append(f"products_services item missing name: {item_id}")
            if not explanation:
                errors.append(f"products_services item missing simple_explanation: {item_id}")
            if not revenue_model:
                errors.append(f"products_services item missing revenue_model: {item_id}")
            normalized = _normalize_name(name)
            if normalized in normalized_names:
                errors.append(f"duplicate normalized offering name: {normalized}")
            normalized_names.add(normalized)
            revenue_status = str(item.get("revenue_contribution_status") or "")
            revenue_value = item.get("revenue_contribution")
            if revenue_status == "unknown" and revenue_value not in {None, ""}:
                errors.append(f"unknown revenue contribution must not carry a value: {item_id}")
            if any(term in explanation.lower() or term in name.lower() for term in PROMOTIONAL_TERMS):
                errors.append(f"promotional wording found in products_services item: {item_id}")
            if contains_forbidden_public_term(name) or contains_forbidden_public_term(explanation):
                errors.append(f"forbidden public term found in products_services item: {item_id}")
            order = int(item.get("display_order") or 0)
            if order <= previous_order:
                errors.append(f"products_services item display_order is not deterministic in group {group_id}")
            previous_order = order
    if not groups and payload.get("coverage_status") not in {"partial", "unavailable"}:
        errors.append("empty products_services groups require partial or unavailable coverage")
    try:
        json.dumps(payload, ensure_ascii=False)
    except TypeError as exc:
        errors.append(f"products_services is not JSON serializable: {exc}")
    return errors


def validate_answer_cards_payload(
    payload: Dict[str, Any],
    *,
    products_services_payload: Dict[str, Any],
    financial_visual_ids: List[str],
) -> List[str]:
    errors: List[str] = []
    required = {
        "schema_version",
        "company_slug",
        "answers",
        "coverage_summary",
        "generated_at",
    }
    missing = sorted(required - set(payload))
    if missing:
        return [f"answer_cards missing required top-level fields: {', '.join(missing)}"]
    answers = payload.get("answers", []) or []
    if not isinstance(answers, list):
        return ["answer_cards.answers must be a list"]
    product_ids = {
        str(item.get("id") or "")
        for group in products_services_payload.get("groups", []) or []
        for item in (group.get("items", []) or [])
        if str(item.get("id") or "").strip()
    }
    question_ids: Set[str] = set()
    answer_ids: Set[str] = set()
    valid_question_ids = set()
    for question_id in _canonical_question_ids():
        valid_question_ids.add(question_id)
    for answer in answers:
        if not isinstance(answer, dict):
            errors.append("answer_cards.answers entries must be objects")
            continue
        answer_id = str(answer.get("id") or "")
        question_id = str(answer.get("question_id") or "")
        if answer_id in answer_ids:
            errors.append(f"duplicate answer card id: {answer_id}")
        answer_ids.add(answer_id)
        if question_id in question_ids:
            errors.append(f"duplicate answer question_id: {question_id}")
        question_ids.add(question_id)
        if question_id not in valid_question_ids:
            errors.append(f"unknown answer question_id: {question_id}")
        if len(answer.get("key_points", []) or []) > 4:
            errors.append(f"answer {answer_id} has more than 4 key_points")
        next_questions = answer.get("next_questions", []) or []
        if len(next_questions) != 3:
            errors.append(f"answer {answer_id} must have exactly 3 next_questions")
        seen_next: Set[str] = set()
        for next_question in next_questions:
            next_id = str((next_question or {}).get("question_id") or "")
            if not next_id:
                errors.append(f"answer {answer_id} next question is missing question_id")
                continue
            if next_id == question_id:
                errors.append(f"answer {answer_id} next question must not self-reference")
            if next_id not in valid_question_ids:
                errors.append(f"answer {answer_id} next question is invalid: {next_id}")
            if next_id in seen_next:
                errors.append(f"answer {answer_id} next question is duplicated: {next_id}")
            seen_next.add(next_id)
        for ref in answer.get("products_and_services_refs", []) or []:
            if ref not in product_ids:
                errors.append(f"answer {answer_id} references unknown product/service item: {ref}")
        for ref in answer.get("financial_visual_refs", []) or []:
            if ref not in financial_visual_ids:
                errors.append(f"answer {answer_id} references unknown financial visual: {ref}")
        status = str(answer.get("answer_status") or "")
        simple_answer = str(answer.get("simple_answer") or "")
        detailed_explanation = str(answer.get("detailed_explanation") or "")
        if status in {"not_supported", "unavailable"} and "available" not in simple_answer.lower() and "not support" not in simple_answer.lower():
            errors.append(f"answer {answer_id} must use cautious language for unsupported/unavailable status")
        if _contains_forbidden_investment_term(simple_answer) or _contains_forbidden_investment_term(detailed_explanation):
            errors.append(f"answer {answer_id} contains forbidden investment language")
        evidence_summary = answer.get("evidence_summary") or {}
        uncertainty_note = answer.get("uncertainty_note") or {}
        if not str(evidence_summary.get("summary") or "").strip():
            errors.append(f"answer {answer_id} is missing evidence_summary.summary")
        if not str(uncertainty_note.get("message") or "").strip():
            errors.append(f"answer {answer_id} is missing uncertainty_note.message")
        interpretation = answer.get("interpretation") or {}
        for point in interpretation.get("positive_evidence", []) or []:
            if _looks_unresolved_like(str(point or "")) or _looks_negative_like(str(point or "")):
                errors.append(f"answer {answer_id} places unresolved or negative evidence in positive_evidence")
                break
        customer_roles = answer.get("customer_roles")
        if customer_roles is not None and not isinstance(customer_roles, dict):
            errors.append(f"answer {answer_id} customer_roles must be an object or null")
        revenue_flow = answer.get("revenue_flow")
        if revenue_flow is not None and not isinstance(revenue_flow, dict):
            errors.append(f"answer {answer_id} revenue_flow must be an object or null")
        errors.extend(validate_question_uncertainty_alignment(answer))
        errors.extend(_validate_public_answer_consistency(answer, answer_id))
        errors.extend(_validate_public_value_strings(answer, f"answer_cards.answers[{answer_id}]"))
    if question_ids != valid_question_ids:
        missing_questions = sorted(valid_question_ids - question_ids)
        extra_questions = sorted(question_ids - valid_question_ids)
        if missing_questions:
            errors.append(f"answer_cards missing questions: {', '.join(missing_questions)}")
        if extra_questions:
            errors.append(f"answer_cards has unexpected questions: {', '.join(extra_questions)}")
    coverage_summary = payload.get("coverage_summary") or {}
    if int(coverage_summary.get("total_questions") or 0) != len(valid_question_ids):
        errors.append("answer_cards coverage_summary.total_questions does not match the canonical catalog")
    try:
        json.dumps(payload, ensure_ascii=False)
    except TypeError as exc:
        errors.append(f"answer_cards is not JSON serializable: {exc}")
    return errors


def validate_question_uncertainty_alignment(answer_card: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    question_id = str(answer_card.get("question_id") or "")
    message = str((answer_card.get("uncertainty_note") or {}).get("message") or "").lower()
    if not question_id or not message:
        return errors
    if question_id == "who-are-the-customers" and "product-level revenue contribution is not disclosed" in message:
        errors.append("customer question uncertainty is not aligned to the strongest customer-specific evidence gap")
    if question_id == "what-does-company-do" and "maintenance and growth capex" in message:
        errors.append("business-summary uncertainty should not be led by a financial precision limitation")
    return errors


def _validate_public_answer_consistency(answer: Dict[str, Any], answer_id: str) -> List[str]:
    errors: List[str] = []
    joined = " ".join(
        [
            str(answer.get("simple_answer") or ""),
            str(answer.get("why_it_matters") or ""),
            str(answer.get("detailed_explanation") or ""),
            " ".join(str(point or "") for point in (answer.get("key_points") or [])),
            str((answer.get("evidence_summary") or {}).get("summary") or ""),
            " ".join(str(point or "") for point in ((answer.get("evidence_summary") or {}).get("supporting_points") or [])),
            str((answer.get("uncertainty_note") or {}).get("message") or ""),
        ]
    ).lower()
    if any(
        phrase in joined
        for phrase in [
            "cfo and capex evidence are absent",
            "key cash-flow inputs are unavailable",
            "owner-earnings cannot be reliably assessed",
            "supplied facts",
        ]
    ):
        errors.append(f"answer {answer_id} contains stale or non-customer-facing wording")
    return errors


def _looks_unresolved_like(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        phrase in lowered
        for phrase in [
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
        ]
    )


def _looks_negative_like(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        phrase in lowered
        for phrase in [
            "mixed",
            "weak",
            "weaken",
            "delay",
            "delayed",
            "caution",
            "fragile",
            "pressure",
            "cash strain risk",
            "operational cash strain risk",
            "working capital risk",
            "strain risk",
            "capped",
            "not cleanly attributable",
            "indirect",
            "downside",
            "headwind",
        ]
    )


def validate_financial_visual_summaries_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    required = {"schema_version", "company_slug", "visuals", "coverage_summary", "generated_at"}
    missing = sorted(required - set(payload))
    if missing:
        return [f"financial_visual_summaries missing required top-level fields: {', '.join(missing)}"]
    visuals = payload.get("visuals", [])
    if not isinstance(visuals, list):
        return ["financial_visual_summaries.visuals must be a list"]
    ids: Set[str] = set()
    valid_visual_types = {"line", "bar", "bridge", "comparison", "timeline", "ratio", "status"}
    valid_point_statuses = {"reported", "derived", "partial", "missing", "unreliable"}
    for visual in visuals:
        if not isinstance(visual, dict):
            errors.append("financial_visual_summaries.visuals entries must be objects")
            continue
        visual_id = str(visual.get("id") or "")
        if not visual_id:
            errors.append("financial visual is missing id")
        elif visual_id in ids:
            errors.append(f"duplicate financial visual id: {visual_id}")
        ids.add(visual_id)
        if str(visual.get("visual_type") or "") not in valid_visual_types:
            errors.append(f"financial visual {visual_id} has invalid visual_type")
        if len(visual.get("series", []) or []) > 3:
            errors.append(f"financial visual {visual_id} has more than 3 series")
        for series in visual.get("series", []) or []:
            points = (series or {}).get("points", []) or []
            if len(points) > 8:
                errors.append(f"financial visual {visual_id} has a series with more than 8 points")
            for point in points:
                status = str((point or {}).get("status") or "")
                if status not in valid_point_statuses:
                    errors.append(f"financial visual {visual_id} has invalid point status: {status}")
                if "value" not in (point or {}):
                    errors.append(f"financial visual {visual_id} point is missing value")
        errors.extend(_validate_public_value_strings(visual, f"financial_visual_summaries.visuals[{visual_id}]"))
    coverage_summary = payload.get("coverage_summary") or {}
    expected_unavailable = max(0, 8 - len(ids))
    if int(coverage_summary.get("unavailable") or 0) != expected_unavailable:
        errors.append("financial_visual_summaries coverage_summary.unavailable does not match the canonical candidate count")
    try:
        json.dumps(payload, ensure_ascii=False)
    except TypeError as exc:
        errors.append(f"financial_visual_summaries is not JSON serializable: {exc}")
    return errors


def validate_uncertainty_map_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    required = {"schema_version", "company_slug", "items", "summary", "coverage_status", "generated_at"}
    missing = sorted(required - set(payload))
    if missing:
        return [f"uncertainty_map missing required top-level fields: {', '.join(missing)}"]
    items = payload.get("items", [])
    if not isinstance(items, list):
        return ["uncertainty_map.items must be a list"]
    ids: Set[str] = set()
    valid_severities = {"low", "medium", "high"}
    valid_statuses = {"missing", "partial", "precision_limited", "unreliable", "contradictory"}
    valid_evidence = {"direct", "derived", "partial", "missing", "unreliable"}
    valid_question_ids = set(_canonical_question_ids())
    previous_order = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append("uncertainty_map.items entries must be objects")
            continue
        item_id = str(item.get("id") or "")
        if not item_id:
            errors.append(f"uncertainty_map item {index} is missing id")
        elif item_id in ids:
            errors.append(f"duplicate uncertainty_map id: {item_id}")
        ids.add(item_id)
        if str(item.get("severity") or "") not in valid_severities:
            errors.append(f"uncertainty_map item {item_id} has invalid severity")
        if str(item.get("status") or "") not in valid_statuses:
            errors.append(f"uncertainty_map item {item_id} has invalid status")
        if str(item.get("evidence_status") or "") not in valid_evidence:
            errors.append(f"uncertainty_map item {item_id} has invalid evidence_status")
        order = int(item.get("display_order") or 0)
        if order <= previous_order:
            errors.append(f"uncertainty_map item {item_id} display_order is not deterministic")
        previous_order = order
        for question_id in item.get("affected_question_ids", []) or []:
            if str(question_id or "") not in valid_question_ids:
                errors.append(f"uncertainty_map item {item_id} references invalid question_id: {question_id}")
        errors.extend(_validate_public_value_strings(item, f"uncertainty_map.items[{item_id or index}]"))
    coverage_status = str(payload.get("coverage_status") or "")
    if not items and coverage_status != "unavailable":
        errors.append("uncertainty_map without items must use coverage_status unavailable")
    if items and coverage_status not in {"supported", "partial"}:
        errors.append("uncertainty_map with items must use supported or partial coverage_status")
    try:
        json.dumps(payload, ensure_ascii=False)
    except TypeError as exc:
        errors.append(f"uncertainty_map is not JSON serializable: {exc}")
    return errors


def _period_sort_key(value: str) -> int:
    text = str(value or "").lower().replace("fy", "").strip()
    if "–" in text:
        text = text.split("–", 1)[0]
    try:
        return int(text)
    except ValueError:
        return 0


def _normalize_name(value: str) -> str:
    text = str(value or "").lower()
    text = " ".join(text.split())
    text = text.replace("/", " ").replace("-", " ")
    text = " ".join(text.split())
    text = text.replace(" ate ", " automated test equipment ")
    text = text.replace(" ew ", " electronic warfare ")
    if text == "ate":
        text = "automated test equipment"
    if text == "ew":
        text = "electronic warfare"
    return " ".join(text.replace("/", " ").replace("-", " ").split())


def _validate_public_value_strings(value: Any, root: str) -> List[str]:
    errors: List[str] = []

    def walk(item: Any, trail: str) -> None:
        if isinstance(item, str) and contains_forbidden_public_term(item):
            errors.append(f"forbidden public term found at {trail}")
        elif isinstance(item, dict):
            for key, nested in item.items():
                walk(nested, f"{trail}.{key}")
        elif isinstance(item, list):
            for index, nested in enumerate(item):
                walk(nested, f"{trail}[{index}]")

    walk(value, root)
    return errors


def _canonical_question_ids() -> List[str]:
    return [
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
    ]


def _contains_forbidden_investment_term(value: str) -> bool:
    lowered = str(value or "").lower()
    advice_patterns = [
        r"\bshould\s+(buy|sell|hold)\b",
        r"\b(buy|sell|hold)\s+(this|the)\b",
        r"\b(buy|sell|hold)\s+(shares|stock|company)\b",
        r"\b(recommend|rating)\s*[:\-]?\s*(buy|sell|hold)\b",
    ]
    return "target price" in lowered or any(re.search(pattern, lowered) for pattern in advice_patterns)
