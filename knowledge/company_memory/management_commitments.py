from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from intelligence.progression import (
    ProgressionEvent,
    build_confidence,
    build_progression_manifest,
    build_progression_timeline,
    event_deduplication_key,
    validate_progression_payload,
)
from intelligence.progression.manifest import PROGRESSION_CONTRACT_VERSION, PROGRESSION_ENGINE_VERSION

from .company_layer import _normalize_text, _promises_match, _promise_theme_key, _write_json, parse_financial_year
from .guardrails import (
    ELIGIBLE_COMMITMENT_STATEMENTS,
    COMPANY_ACTORS,
    assess_progression_materiality,
    build_semantic_quality,
    classify_actor,
    classify_business_relevance,
    classify_statement_type,
    resolve_period_status,
)


ALLOWED_CATEGORIES = (
    "Product",
    "Capacity",
    "Expansion",
    "Capex",
    "Technology",
    "Partnership",
    "Financial Target",
    "Margin",
    "Growth",
    "Market Entry",
    "Manufacturing",
    "Customer",
    "Acquisition",
    "Other",
)

SCHEMA_VERSION = "management_commitments.v1"
MANIFEST_SCHEMA_VERSION = "management_commitments_manifest.v1"
GENERATOR_VERSION = "management_commitments_builder.v1"

ALLOWED_STATUSES = (
    "Announced",
    "In Progress",
    "Partially Delivered",
    "Delivered",
    "Delayed",
    "Superseded",
    "Abandoned",
    "Unable To Verify",
)

SOURCE_TEXT_FIELDS = ("promise", "commitment", "statement", "value", "text", "summary")
TEXT_CLEANUP_PREFIXES = (
    "we expect ",
    "we expect to ",
    "we plan to ",
    "we plan ",
    "we will ",
    "we aim to ",
    "we aim ",
    "we intend to ",
    "we intend ",
    "the company expects to ",
    "the company expects ",
    "management expects to ",
    "management expects ",
    "the company plans to ",
    "the company plans ",
    "management plans to ",
    "management plans ",
)
TIMEFRAME_PATTERNS = (
    re.compile(r"\bnext year\b", re.IGNORECASE),
    re.compile(r"\bthis year\b", re.IGNORECASE),
    re.compile(r"\bwithin\s+\d+\s+(?:months?|quarters?)\b", re.IGNORECASE),
    re.compile(r"\bover the next\s+\d+\s+(?:months?|quarters?)\b", re.IGNORECASE),
    re.compile(r"\bby\s+fy\d{2,4}\b", re.IGNORECASE),
    re.compile(r"\bin\s+fy\d{2,4}\b", re.IGNORECASE),
    re.compile(r"\bfor fy\d{2,4}\b", re.IGNORECASE),
    re.compile(r"\bby end of fy\d{2,4}\b", re.IGNORECASE),
)
TIMEFRAME_HINT_KEYS = (
    "expected_timeframe",
    "timeframe",
    "target_period",
    "target_date",
    "timeline",
    "period",
    "horizon",
)
FUTURE_MARKERS = (
    "expect",
    "expected",
    "plan",
    "planned",
    "aim",
    "target",
    "intend",
    "will",
    "seek",
    "looking to",
)
PROGRESS_MARKERS = (
    "in progress",
    "underway",
    "ongoing",
    "ramping",
    "ramp up",
    "phase 1",
    "first phase",
    "initial phase",
    "implementation",
    "executing",
    "execution",
    "construction",
    "building",
    "trial",
    "pilot",
    "progress",
)
DELIVERED_MARKERS = (
    "delivered",
    "delivered on",
    "commissioned",
    "operational",
    "launched",
    "completed",
    "implemented",
    "achieved",
    "live",
    "commercial production started",
    "commercial production commenced",
)
PARTIAL_MARKERS = (
    "partial",
    "partially",
    "first tranche",
    "phase 1",
    "initial rollout",
    "limited rollout",
    "some progress",
    "initial capacity",
)
DELAYED_MARKERS = (
    "delayed",
    "delay",
    "slipped",
    "postponed",
    "pushed out",
    "pushed back",
    "rescheduled",
    "deferred",
)
ABANDONED_MARKERS = (
    "abandoned",
    "abandon",
    "not pursuing",
    "no longer pursuing",
    "walked away",
    "cancelled",
    "canceled",
    "dropped",
)
SUPERSEDED_MARKERS = (
    "superseded",
    "replaced",
    "reframed",
    "redirected",
    "shifted focus",
    "new plan",
    "changed plan",
)
CATEGORY_KEYWORDS = {
    "Product": ("product", "launch", "offering", "platform", "feature", "solution", "service"),
    "Capacity": ("capacity", "output", "throughput", "ramp", "expand plant", "expand capacity"),
    "Expansion": ("expand", "expansion", "broaden", "scale", "footprint", "geography", "international"),
    "Capex": ("capex", "capital expenditure", "investment", "cwip", "plant", "facility", "equipment"),
    "Technology": ("technology", "digital", "automation", "system", "cloud", "software", "r&d", "research"),
    "Partnership": ("partner", "partnership", "alliance", "tie up", "tie-up", "channel", "oem", "collaboration"),
    "Financial Target": ("revenue", "ebitda", "pat", "profit", "cash flow", "roe", "roce", "eps", "fcf", "target"),
    "Margin": ("margin", "gross margin", "ebitda margin", "operating margin", "profitability"),
    "Growth": ("growth", "increase sales", "increase revenue", "top line", "market share", "scale revenue"),
    "Market Entry": ("enter", "market entry", "launch in", "country", "region", "export", "overseas"),
    "Manufacturing": ("manufacturing", "production", "commercial production", "commission", "factory", "plant"),
    "Customer": ("customer", "client", "order", "contract", "account", "win", "demand"),
    "Acquisition": ("acquire", "acquisition", "merge", "takeover", "buy", "invest in"),
}
TOPIC_BY_CATEGORY = {
    "Product": "Product launch",
    "Capacity": "Capacity expansion",
    "Expansion": "Business expansion",
    "Capex": "Capital deployment",
    "Technology": "Technology upgrade",
    "Partnership": "Partnership rollout",
    "Financial Target": "Financial target",
    "Margin": "Margin improvement",
    "Growth": "Growth target",
    "Market Entry": "Market entry",
    "Manufacturing": "Commercial production",
    "Customer": "Customer win",
    "Acquisition": "Acquisition",
    "Other": "Management commitment",
}
PRIORITY_BY_CATEGORY = {
    "Financial Target": "high",
    "Margin": "high",
    "Growth": "high",
    "Capacity": "high",
    "Capex": "high",
    "Manufacturing": "high",
    "Market Entry": "high",
    "Acquisition": "high",
    "Technology": "medium",
    "Partnership": "medium",
    "Customer": "medium",
    "Product": "medium",
    "Expansion": "medium",
    "Other": "low",
}


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _year_sort_key(label: str) -> int:
    try:
        return parse_financial_year(label)
    except Exception:
        return -1


def _text_candidates(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        candidates: List[str] = []
        for item in value:
            candidates.extend(_text_candidates(item))
        return candidates
    if isinstance(value, dict):
        candidates: List[str] = []
        for field in SOURCE_TEXT_FIELDS:
            field_value = value.get(field)
            if field_value not in (None, "", [], {}):
                candidates.extend(_text_candidates(field_value))
        return candidates
    return [str(value)]


def _clean_statement(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    lowered = text.lower()
    for prefix in TEXT_CLEANUP_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix):].lstrip(", :-")
            lowered = text.lower()
            break
    return text.strip(" .")


def _strip_timeframe_phrases(value: str) -> str:
    text = value
    for pattern in TIMEFRAME_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" .,:;-")
    return text


def _contains_marker(text: str, marker: str) -> bool:
    normalized_text = _normalize_text(text)
    normalized_marker = _normalize_text(marker)
    if not normalized_marker:
        return False
    pattern = re.escape(normalized_marker).replace(r"\ ", r"\s+")
    return re.search(rf"\b{pattern}\b", normalized_text) is not None


def _extract_timeframe(statement: str, source_item: Dict[str, Any]) -> str:
    for key in TIMEFRAME_HINT_KEYS:
        hint = source_item.get(key)
        if hint not in (None, "", [], {}):
            return " ".join(str(hint).split())
    lowered = statement.lower()
    for pattern in TIMEFRAME_PATTERNS:
        match = pattern.search(lowered)
        if match:
            return match.group(0).strip()
    return "unspecified"


def _classify_category(statement: str, category_hint: Any = None) -> str:
    hint = _clean_label(category_hint)
    if hint in {category.lower() for category in ALLOWED_CATEGORIES}:
        return next(category for category in ALLOWED_CATEGORIES if category.lower() == hint)

    text = _normalize_text(statement)
    scores: Dict[str, int] = {category: 0 for category in ALLOWED_CATEGORIES}
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                scores[category] += 1

    if "commercial production" in text or "commission" in text:
        scores["Manufacturing"] += 2
    if "capacity" in text or "ramp" in text:
        scores["Capacity"] += 2
    if "expand" in text and "capacity" in text:
        scores["Capacity"] += 2
        scores["Expansion"] += 1
    if "margin" in text and ("improve" in text or "protect" in text):
        scores["Margin"] += 2
    if "market" in text and ("enter" in text or "entry" in text):
        scores["Market Entry"] += 2
    if "partner" in text and "customer" in text:
        scores["Partnership"] += 1

    best = max(scores.items(), key=lambda item: (item[1], -ALLOWED_CATEGORIES.index(item[0])))[0]
    if scores[best] == 0:
        return "Other"
    return best


def _clean_label(value: Any) -> str:
    return _normalize_text(value)


def _derive_topic(statement: str, category: str) -> str:
    text = _normalize_text(statement)
    if category == "Manufacturing":
        if "commercial production" in text:
            return "Commercial production"
        if "commission" in text:
            return "Plant commissioning"
        return TOPIC_BY_CATEGORY[category]
    if category == "Capacity":
        if "commercial production" in text:
            return "Commercial production"
        if "ramp" in text:
            return "Capacity ramp"
        return TOPIC_BY_CATEGORY[category]
    if category == "Partnership":
        if "channel" in text:
            return "Channel partnership"
        if "oem" in text:
            return "OEM partnership"
        return TOPIC_BY_CATEGORY[category]
    if category == "Market Entry":
        if "export" in text:
            return "Export market entry"
        return TOPIC_BY_CATEGORY[category]
    if category == "Customer":
        if "contract" in text:
            return "Customer contract"
        if "order" in text:
            return "Customer order"
        return TOPIC_BY_CATEGORY[category]
    if category == "Acquisition":
        if "acquire" in text or "acquisition" in text:
            return "Acquisition"
    if category == "Financial Target":
        if "revenue" in text and "growth" in text:
            return "Revenue growth target"
        if "margin" in text:
            return "Margin target"
    if category == "Growth":
        if "revenue" in text:
            return "Revenue growth"
        if "market share" in text:
            return "Market share growth"
    if category == "Product":
        if "launch" in text:
            return "Product launch"
        if "platform" in text:
            return "Platform rollout"
    if category == "Technology":
        if "security" in text:
            return "Technology security upgrade"
        if "automation" in text:
            return "Automation upgrade"
    if category == "Capex":
        if "plant" in text:
            return "Plant investment"
        if "facility" in text:
            return "Facility investment"
    return TOPIC_BY_CATEGORY.get(category, "Management commitment")


def _normalize_commitment(statement: str, category: str, topic: str) -> str:
    cleaned = _clean_statement(statement)
    lowered = cleaned.lower()
    cleaned = _strip_timeframe_phrases(cleaned)
    stripped = _normalize_text(cleaned)
    if not stripped:
        stripped = _normalize_text(topic)

    future_marked = any(_contains_marker(lowered, marker) for marker in FUTURE_MARKERS)
    if future_marked and stripped == _normalize_text(topic):
        if topic in {"Commercial production", "Capacity expansion"}:
            return f"{topic} expected."
        return f"{topic} planned."

    if future_marked and not stripped.endswith("expected") and not stripped.endswith("planned"):
        if topic and _normalize_text(topic) not in stripped:
            if category in {"Manufacturing", "Capacity", "Capex"}:
                return f"{topic} planned."
            return f"{topic} expected."

    if category == "Financial Target" and "target" not in stripped:
        if "revenue" in lowered and "growth" in lowered:
            return "Revenue growth target."
        if "margin" in lowered:
            return "Margin target."

    if category == "Manufacturing" and "commercial production" in stripped:
        return "Commercial production expected." if future_marked else "Commercial production."

    if category == "Capacity" and "capacity expansion" in stripped:
        return "Capacity expansion planned." if future_marked else "Capacity expansion."

    if category == "Product" and "product launch" in stripped:
        return "Product launch planned." if future_marked else "Product launch."

    sentence = stripped[:1].upper() + stripped[1:]
    if not sentence.endswith("."):
        sentence += "."
    return sentence


def _priority_for(category: str, statement: str) -> str:
    base = PRIORITY_BY_CATEGORY.get(category, "low")
    text = _normalize_text(statement)
    if any(_contains_marker(text, marker) for marker in ("by fy", "next year", "within", "over the next")) and base == "medium":
        return "high"
    return base


def _confidence_for(candidate: Dict[str, Any], group_size: int = 1) -> str:
    score = 0
    if candidate.get("source_artifact") == "company_intelligence.json":
        score += 1
    if candidate.get("page") not in (None, "", []):
        score += 1
    if candidate.get("source_chunk"):
        score += 1
    if candidate.get("expected_timeframe") not in (None, "", "unspecified"):
        score += 1
    if group_size > 1:
        score += 1
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _evidence_status_for_text(statement: str, status_hint: Any = None) -> Tuple[str, str]:
    lowered = _normalize_text(statement)
    hint = _clean_label(status_hint)
    if hint in {"delivered", "completed", "implemented", "commissioned", "operational", "launched", "achieved"}:
        return "Delivered", "delivery_confirmation"
    if hint in {"partially delivered", "partial", "in progress", "ongoing", "underway", "planned"}:
        if hint in {"partial", "partially delivered"}:
            return "Partially Delivered", "progress_update"
        if hint in {"planned"}:
            return "Announced", "announcement"
        return "In Progress", "progress_update"
    if hint in {"delayed", "postponed", "slipped", "deferred"}:
        return "Delayed", "delay_signal"
    if hint in {"abandoned", "cancelled", "canceled", "not pursuing"}:
        return "Abandoned", "abandonment_signal"
    if hint in {"superseded", "replaced", "reframed"}:
        return "Superseded", "superseded"

    if any(_contains_marker(lowered, marker) for marker in DELAYED_MARKERS):
        return "Delayed", "delay_signal"
    if any(_contains_marker(lowered, marker) for marker in ABANDONED_MARKERS):
        return "Abandoned", "abandonment_signal"
    if any(_contains_marker(lowered, marker) for marker in SUPERSEDED_MARKERS):
        return "Superseded", "superseded"
    if any(_contains_marker(lowered, marker) for marker in PARTIAL_MARKERS):
        return "Partially Delivered", "progress_update"
    if any(_contains_marker(lowered, marker) for marker in DELIVERED_MARKERS):
        return "Delivered", "delivery_confirmation"
    if any(_contains_marker(lowered, marker) for marker in PROGRESS_MARKERS):
        return "In Progress", "progress_update"
    return "Announced", "announcement"


def _event_type_for_status(status: str) -> str:
    if status == "Delivered":
        return "delivery_confirmation"
    if status == "Partially Delivered":
        return "progress_update"
    if status == "In Progress":
        return "progress_update"
    if status == "Delayed":
        return "delay_signal"
    if status == "Abandoned":
        return "abandonment_signal"
    if status == "Superseded":
        return "superseded"
    return "announcement"


def _latest_assessment_event(status: str, commitment: Dict[str, Any]) -> Dict[str, Any]:
    latest_period = commitment.get("progression", {}).get("latest_period") or commitment.get("announcement_period")
    latest_statement = commitment.get("delivery_assessment") or commitment.get("investor_implication") or commitment.get("normalized_commitment")
    return {
        "period": latest_period,
        "event_type": "latest_assessment",
        "status": status,
        "statement": latest_statement,
        "source_reference": commitment.get("source_references", [{}])[-1] if commitment.get("source_references") else {},
    }


def _extract_source_item_years(year_record: Dict[str, Any]) -> List[Dict[str, Any]]:
    year = year_record["year"]
    candidates: List[Dict[str, Any]] = []
    sources: List[Tuple[str, Dict[str, Any], Sequence[Dict[str, Any]]]] = []
    seen_year_statements: set[Tuple[str, str]] = set()

    cim = year_record.get("company_intelligence") or {}
    summary = year_record.get("management_summary") or {}

    promise_items = (((cim.get("management") or {}).get("promises") or {}).get("items") or [])
    sources.append(("company_intelligence.json", cim, promise_items))

    summary_sources: List[Dict[str, Any]] = []
    for field_name in ("major_promises", "company_promises", "promises", "commitments", "management_commitments"):
        value = summary.get(field_name)
        if value not in (None, "", [], {}):
            if isinstance(value, list):
                summary_sources.extend(value)
            else:
                summary_sources.append(value)
    if summary_sources:
        sources.append(("management_summary.json", summary, summary_sources))

    for artifact_name, source_payload, source_items in sources:
        for index, item in enumerate(source_items):
            if isinstance(item, str):
                text = item
                item_payload: Dict[str, Any] = {"promise": text}
            elif isinstance(item, dict):
                item_payload = dict(item)
                text = next((candidate for candidate in _text_candidates(item_payload) if candidate), "")
            else:
                text = str(item)
                item_payload = {"promise": text}

            original_statement = " ".join(str(text).split()).strip()
            if not original_statement:
                continue
            year_statement_key = (year, _normalize_text(original_statement))
            if year_statement_key in seen_year_statements:
                continue
            seen_year_statements.add(year_statement_key)
            statement = _clean_statement(original_statement)
            if not statement:
                statement = original_statement

            category_hint = item_payload.get("category") or item_payload.get("topic") or item_payload.get("type")
            status_hint = item_payload.get("status") or item_payload.get("delivery_status")
            timeframe = _extract_timeframe(statement, item_payload)
            category = _classify_category(statement, category_hint)
            topic = _derive_topic(statement, category)
            normalized_commitment = _normalize_commitment(statement, category, topic)
            actor = classify_actor(
                original_statement,
                actor_hint=item_payload.get("actor") or item_payload.get("speaker"),
                source_section="management promises",
            )
            statement_semantics = classify_statement_type(
                original_statement,
                category_hint=category_hint,
                status_hint=status_hint,
            )
            actor_type = actor["actor_type"]
            statement_type = statement_semantics["statement_type"]
            lifecycle_update = any(
                marker in _normalize_text(original_statement)
                for marker in (*DELIVERED_MARKERS, *DELAYED_MARKERS, *ABANDONED_MARKERS, *SUPERSEDED_MARKERS, *PROGRESS_MARKERS)
            )
            normalized_original = _normalize_text(original_statement)
            conservative_expectation = statement_type == "expectation" and (
                bool(re.search(r"\b(?:fy\d{2,4}|20\d{2}|\d+(?:\.\d+)?\s*%|crore|million|billion)\b", normalized_original))
                or any(marker in normalized_original for marker in ("launch", "commission", "commercial production", "next year", "expand", "acquire", "enter the", "complete by", "deliver by"))
            )
            broad_employee_welfare = any(term in normalized_original for term in ("employee wellbeing", "employee well-being", "inclusion and retention", "nurturing future leaders"))
            bounded_signal = bool(re.search(r"\b(?:fy\d{2,4}|20\d{2}|\d+(?:\.\d+)?\s*%|crore|million|billion)\b", normalized_original)) or any(
                marker in normalized_original for marker in ("launch", "commission", "commercial production", "next year", "install", "acquire", "enter the", "complete by", "deliver by", "build ")
            )
            broad_sustainability_pledge = any(term in normalized_original for term in ("sustainable growth", "environmental impact", "sustainability and profitability")) and not bounded_signal
            historical_accomplishment = statement_type == "historical_accomplishment"
            can_initiate_commitment = not broad_employee_welfare and not broad_sustainability_pledge and actor_type in COMPANY_ACTORS and (
                statement_type in ELIGIBLE_COMMITMENT_STATEMENTS or conservative_expectation
            )
            if historical_accomplishment:
                can_initiate_commitment = False
            commitment_eligible = can_initiate_commitment or (actor_type in COMPANY_ACTORS and lifecycle_update)
            relevance = classify_business_relevance(
                original_statement,
                module_name="management_commitments",
                actor_type=actor_type,
                source_kind=artifact_name,
            )
            period_resolution = resolve_period_status(source_year=year, text=original_statement, explicit_year=year)
            materiality = assess_progression_materiality(
                original_statement,
                module_name="management_commitments",
                relevance_status=str(relevance.get("status") or "ambiguous"),
                period_status=str(period_resolution.get("status") or "AMBIGUOUS"),
                status_text=str(status_hint or ""),
            )
            exclusion_reason = ""
            if actor_type not in COMPANY_ACTORS:
                exclusion_reason = f"statement belongs to {actor_type}, not the company"
            elif broad_employee_welfare:
                exclusion_reason = "broad employee-welfare statement is not a bounded investor commitment"
            elif broad_sustainability_pledge:
                exclusion_reason = "broad sustainability pledge lacks a bounded action, target, or timeframe"
            elif historical_accomplishment:
                exclusion_reason = "historical accomplishment belongs in business history, not management commitments"
            elif not can_initiate_commitment and not lifecycle_update:
                exclusion_reason = f"{statement_type} is not an eligible commitment speech act"
            semantic_quality = build_semantic_quality(
                classification="MANAGEMENT_COMMITMENT" if commitment_eligible else statement_type.upper(),
                relevance=relevance,
                period=period_resolution,
                materiality=materiality,
                eligibility="eligible" if commitment_eligible and period_resolution.get("status") == "RESOLVED" else "quarantined",
                exclusion_reason=exclusion_reason,
                evidence_confidence=item_payload.get("confidence") or "medium",
            )
            evidence_status, event_type = _evidence_status_for_text(original_statement, status_hint)
            source_item_id = item_payload.get("id") or item_payload.get("source_item_id") or f"{artifact_name}:{index}"
            source_ref = {
                "period": year,
                "source_artifact": artifact_name,
                "source_item_id": source_item_id,
                "page": item_payload.get("page"),
                "source_chunk": item_payload.get("source_chunk"),
                "confidence": item_payload.get("confidence"),
                "status_hint": status_hint,
            }
            evidence = {
                "period": year,
                "event_type": event_type,
                "status": evidence_status,
                "statement": original_statement,
                "source_reference": source_ref,
            }
            candidates.append(
                {
                    "period": year,
                    "sort_key": _year_sort_key(year),
                    "source_artifact": artifact_name,
                    "source_item_id": source_item_id,
                    "original_statement": original_statement,
                    "normalized_source_statement": _normalize_text(original_statement),
                    "topic": topic,
                    "category": category,
                    "normalized_commitment": normalized_commitment,
                    "expected_timeframe": timeframe,
                    "priority": _priority_for(category, original_statement),
                    "status_hint": status_hint,
                    "confidence": item_payload.get("confidence"),
                    "page": item_payload.get("page"),
                    "source_chunk": item_payload.get("source_chunk"),
                    "source_reference": source_ref,
                    "supporting_evidence": [evidence],
                    "actor_type": actor_type,
                    "actor_classification": actor,
                    "statement_type": statement_type,
                    "statement_classification": statement_semantics,
                    "semantic_quality": semantic_quality,
                    "commitment_role": "announcement" if can_initiate_commitment else "follow_up",
                }
            )

    return candidates


def _group_key(candidate: Dict[str, Any]) -> Tuple[str, str]:
    normalized = _normalize_text(candidate.get("normalized_commitment") or candidate.get("original_statement") or "")
    theme = _promise_theme_key(normalized)
    return candidate.get("category", "Other"), theme or normalized


def _merge_group(base: Dict[str, Any], candidate: Dict[str, Any]) -> None:
    if candidate["period"] not in base["periods_seen"]:
        base["periods_seen"].append(candidate["period"])
    if candidate["normalized_commitment"] and not base.get("normalized_commitment"):
        base["normalized_commitment"] = candidate["normalized_commitment"]
    if candidate["topic"] and not base.get("topic"):
        base["topic"] = candidate["topic"]
    if candidate["expected_timeframe"] and base.get("expected_timeframe") in (None, "", "unspecified"):
        base["expected_timeframe"] = candidate["expected_timeframe"]
    if candidate["priority"] == "high":
        base["priority"] = "high"
    elif candidate["priority"] == "medium" and base.get("priority") == "low":
        base["priority"] = "medium"
    if candidate.get("confidence") == "high":
        base["confidence_votes"].append("high")
    elif candidate.get("confidence") == "medium":
        base["confidence_votes"].append("medium")
    elif candidate.get("confidence") == "low":
        base["confidence_votes"].append("low")
    base["original_statements"].append(candidate["original_statement"])
    base["source_references"].append(candidate["source_reference"])
    base["supporting_evidence"].extend(candidate["supporting_evidence"])
    base["updates"].append(candidate)


def _build_group_from_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "group_key": _group_key(candidate),
        "topic": candidate["topic"],
        "category": candidate["category"],
        "normalized_commitment": candidate["normalized_commitment"],
        "expected_timeframe": candidate["expected_timeframe"],
        "priority": candidate["priority"],
        "announcement_period": candidate["period"],
        "original_statements": [candidate["original_statement"]],
        "source_references": [candidate["source_reference"]],
        "supporting_evidence": list(candidate["supporting_evidence"]),
        "updates": [candidate],
        "periods_seen": [candidate["period"]],
        "confidence_votes": [candidate.get("confidence")] if candidate.get("confidence") else [],
        "actor_type": candidate.get("actor_type"),
        "statement_type": candidate.get("statement_type"),
        "semantic_quality": candidate.get("semantic_quality") or {},
    }


def _determine_status(group: Dict[str, Any]) -> str:
    updates = sorted(group["updates"], key=lambda item: (item["sort_key"], item["period"], item["source_item_id"]))
    if len(updates) <= 1:
        return "Unable To Verify"

    latest_status = "Unable To Verify"
    decisive_seen = False
    for update in updates[1:]:
        status, _ = _evidence_status_for_text(update["original_statement"], update.get("status_hint"))
        if status == "Announced":
            status = "In Progress"
        if status in {"Delivered", "Partially Delivered", "Delayed", "Superseded", "Abandoned", "In Progress"}:
            latest_status = status
            decisive_seen = True
    if not decisive_seen:
        return "Unable To Verify"

    if latest_status == "Delivered":
        return "Delivered"
    if latest_status == "Partially Delivered":
        return "Partially Delivered"
    if latest_status == "Delayed":
        return "Delayed"
    if latest_status == "Superseded":
        return "Superseded"
    if latest_status == "Abandoned":
        return "Abandoned"
    if latest_status == "In Progress":
        return "In Progress"
    return "Unable To Verify"


def _build_delivery_assessment(status: str, group: Dict[str, Any]) -> str:
    announcement = group["announcement_period"]
    latest = max(group["periods_seen"], key=_year_sort_key)
    if status == "Delivered":
        return f"Later evidence by {latest} supports delivery of the original commitment announced in {announcement}."
    if status == "Partially Delivered":
        return f"Later evidence shows partial execution by {latest}, but the original commitment from {announcement} is not fully complete."
    if status == "Delayed":
        return f"Later evidence from {latest} indicates execution slipped after the original {announcement} commitment."
    if status == "Superseded":
        return f"Later evidence indicates the {announcement} commitment was replaced by a different plan."
    if status == "Abandoned":
        return f"Later evidence indicates management stopped pursuing the {announcement} commitment."
    if status == "In Progress":
        return f"Later evidence shows the {announcement} commitment remains underway, but completion is not yet proven."
    return f"No later evidence was found to confirm or overturn the commitment announced in {announcement}."


def _confidence_for_group(group: Dict[str, Any]) -> str:
    votes = group.get("confidence_votes") or []
    if not votes:
        return "low"
    if votes.count("high") >= 2 or (votes.count("high") >= 1 and len(votes) >= 3):
        return "high"
    if votes.count("high") >= 1 or votes.count("medium") >= 2 or len(votes) >= 2:
        return "medium"
    return "low"


def _investor_implication(status: str) -> str:
    mapping = {
        "Delivered": "Execution appears on schedule.",
        "Partially Delivered": "Some execution is visible, but the commitment is not fully complete.",
        "Delayed": "Delay increases uncertainty around the expected outcome.",
        "Superseded": "The original commitment appears to have been replaced by a different plan.",
        "Abandoned": "Management appears to have walked away from the original commitment.",
        "In Progress": "The commitment is in motion, but completion is not yet proven.",
        "Unable To Verify": "There is not enough later evidence to judge execution.",
        "Announced": "The commitment has been announced, but follow-through is still unproven.",
    }
    return mapping.get(status, "There is not enough later evidence to judge execution.")


def _latest_evidence_period(group: Dict[str, Any]) -> str:
    if not group["periods_seen"]:
        return "unknown"
    return max(group["periods_seen"], key=_year_sort_key)


_COMMITMENT_STATUS_ORDER = {
    "Announced": 0,
    "In Progress": 1,
    "Partially Delivered": 2,
    "Delayed": 2,
    "Delivered": 3,
    "Superseded": 3,
    "Abandoned": 3,
    "Unable To Verify": 0,
}

_PROGRESSION_STATUS_TO_EVENT_TYPE = {
    "Announced": "announcement",
    "In Progress": "progress",
    "Partially Delivered": "progress",
    "Delivered": "confirmation",
    "Delayed": "delay",
    "Superseded": "superseded",
    "Abandoned": "abandonment",
    "Unable To Verify": "unresolved",
}


class ManagementCommitmentProgressionAdapter:
    stream_type = "management_commitment"

    def normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(event)
        normalized.setdefault("stream_type", self.stream_type)
        normalized.setdefault("source_references", [])
        normalized.setdefault("metadata", {})
        confidence = normalized.get("confidence") or {}
        if not isinstance(confidence, dict):
            confidence = build_confidence(confidence)
        normalized["confidence"] = build_confidence(
            confidence.get("level"),
            basis=confidence.get("basis"),
            limitations=confidence.get("limitations"),
        )
        normalized["event_type"] = str(normalized.get("event_type") or "update").strip() or "update"
        normalized["sequence"] = int(normalized.get("sequence") or 0)
        return normalized

    def deduplicate_key(self, event: Dict[str, Any]) -> str:
        return event_deduplication_key(event)

    def _rank(self, state: Any) -> int:
        return _COMMITMENT_STATUS_ORDER.get(str(state or "").strip(), 0)

    def validate_transition(self, previous_state: Any, event: Dict[str, Any], next_state: Any) -> Dict[str, Any]:
        if previous_state not in (None, "", "Unknown") and next_state not in (None, "", "Unknown"):
            if self._rank(next_state) < self._rank(previous_state):
                return {
                    "accepted": False,
                    "transition_type": "reversal",
                    "reason": "Backward transition is not allowed for management commitments.",
                    "confidence": build_confidence("medium", basis=["domain validation"], limitations=["backward transition"]),
                }
        transition_type = _PROGRESSION_STATUS_TO_EVENT_TYPE.get(
            str(next_state or event.get("metadata", {}).get("domain_status") or event.get("evidence_status") or "").strip(),
            "update",
        )
        return {
            "accepted": True,
            "transition_type": transition_type,
            "reason": "Transition accepted.",
            "confidence": build_confidence("high", basis=["domain validation"], limitations=[]),
        }

    def derive_current_state(self, events: List[Dict[str, Any]]) -> Any:
        current_state = "Unable To Verify"
        for event in events:
            status = event.get("metadata", {}).get("domain_status") or event.get("evidence_status")
            if status in {"Announced", None, "", "Unknown"}:
                continue
            current_state = str(status)
        return current_state

    def build_investor_implication(self, timeline: Dict[str, Any]) -> Dict[str, Any]:
        current_state = str(timeline.get("current_state") or "Unable To Verify")
        mapping = {
            "Delivered": ("strengthened", "Execution appears on schedule.", "Later evidence supports delivery rather than delay."),
            "Partially Delivered": ("unchanged", "Some execution is visible, but the commitment is not fully complete.", "The evidence supports progress, not full completion."),
            "Delayed": ("weakened", "Delay increases uncertainty around the expected outcome.", "Later evidence indicates slippage or missed timing."),
            "Superseded": ("weakened", "The original commitment appears to have been replaced by a different plan.", "Later evidence points to a change in direction."),
            "Abandoned": ("weakened", "Management appears to have walked away from the original commitment.", "Later evidence shows the effort was dropped."),
            "In Progress": ("unchanged", "The commitment is in motion, but completion is not yet proven.", "Evidence shows movement but not a final outcome."),
            "Unable To Verify": ("unclear", "There is not enough later evidence to judge execution.", "The current evidence set does not support a confident conclusion."),
            "Announced": ("unchanged", "The commitment has been announced, but follow-through is still unproven.", "Only the original announcement is visible."),
        }
        direction, summary, reason = mapping.get(current_state, ("unclear", "The evidence remains incomplete.", "The commitment state is not yet decisive."))
        confidence = build_confidence(
            "medium" if current_state not in {"Unable To Verify", "Announced"} else "low",
            basis=[summary],
            limitations=[reason],
        )
        confidence["direction"] = direction
        confidence["summary"] = summary
        confidence["reason"] = reason
        return confidence


_PROGRESSION_ADAPTER = ManagementCommitmentProgressionAdapter()


def _progression_event_from_evidence(commitment_id: str, evidence: Dict[str, Any], sequence: int, *, is_announcement: bool = False) -> Dict[str, Any]:
    status = str(evidence.get("status") or "Announced")
    event_type = "announcement" if is_announcement else _PROGRESSION_STATUS_TO_EVENT_TYPE.get(status, "update")
    source_reference = dict(evidence.get("source_reference") or {})
    basis = ["management statement"]
    if source_reference.get("source_artifact"):
        basis.append(str(source_reference["source_artifact"]))
    limitations: List[str] = []
    if status in {"Unable To Verify", "Announced"}:
        limitations.append("no later confirmation")
    confidence_level = "medium" if source_reference.get("page") is not None or source_reference.get("source_chunk") else "low"
    return ProgressionEvent(
        event_id=f"{commitment_id}-E{sequence:03d}",
        stream_type=_PROGRESSION_ADAPTER.stream_type,
        subject_id=commitment_id,
        period=str(evidence.get("period") or ""),
        sequence=sequence,
        event_type=event_type,
        title=str(evidence.get("statement") or "").strip()[:120] or event_type.replace("_", " ").title(),
        description=str(evidence.get("statement") or "").strip(),
        evidence_status="direct" if status != "Unable To Verify" else "missing",
        confidence=build_confidence(confidence_level, basis=basis, limitations=limitations),
        source_references=[source_reference] if source_reference else [],
        metadata={
            "domain_status": status,
            "is_announcement": is_announcement,
        },
    ).to_dict()


def _source_registry_for_year_records(year_records: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    considered: List[Dict[str, Any]] = []
    found: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []

    for record in year_records:
        year = record["year"]
        intelligence_dir = Path(record.get("paths", {}).get("intelligence_dir", ""))
        for artifact_name in ("company_intelligence.json", "management_summary.json"):
            path = intelligence_dir / artifact_name
            entry = {
                "period": year,
                "artifact": artifact_name,
                "path": str(path),
            }
            considered.append(entry)
            if path.exists() and record.get("available_artifacts", {}).get(artifact_name):
                found.append(entry)
            else:
                missing.append(entry)

    return {
        "considered": considered,
        "found": found,
        "missing": missing,
    }


def _build_manifest(
    *,
    company: str,
    year_records: Sequence[Dict[str, Any]],
    commitments: Sequence[Dict[str, Any]],
    validation: Dict[str, Any],
    outputs_written: Sequence[str],
) -> Dict[str, Any]:
    source_registry = _source_registry_for_year_records(year_records)
    commitments_with_follow_up = sum(
        1
        for commitment in commitments
        if len((commitment.get("progression") or {}).get("evidence_updates") or []) > 0
    )
    commitments_without_follow_up = len(commitments) - commitments_with_follow_up
    events_processed = sum(len((commitment.get("progression") or {}).get("state_transitions") or []) for commitment in commitments)
    transitions_detected = sum(
        sum(1 for transition in (commitment.get("progression") or {}).get("state_transitions") or [] if transition.get("accepted"))
        for commitment in commitments
    )
    turning_points_detected = sum(len((commitment.get("progression") or {}).get("turning_points") or []) for commitment in commitments)
    unresolved_items = sum(len((commitment.get("progression") or {}).get("unresolved_questions") or []) for commitment in commitments)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "company_slug": company,
        "generated_at": _utc_now(),
        "generator_version": GENERATOR_VERSION,
        "upstream_sources_considered": source_registry["considered"],
        "upstream_sources_found": source_registry["found"],
        "upstream_sources_missing": source_registry["missing"],
        "commitments_detected": len(commitments),
        "commitments_with_follow_up": commitments_with_follow_up,
        "commitments_without_follow_up": commitments_without_follow_up,
        "progression_engine_version": PROGRESSION_ENGINE_VERSION,
        "progression_contract_version": PROGRESSION_CONTRACT_VERSION,
        "progression_engine": build_progression_manifest(
            company_slug=company,
            generated_at=_utc_now(),
            progression_engine_version=PROGRESSION_ENGINE_VERSION,
            progression_contract_version=PROGRESSION_CONTRACT_VERSION,
            events_processed=events_processed,
            transitions_detected=transitions_detected,
            turning_points_detected=turning_points_detected,
            unresolved_items=unresolved_items,
            outputs_written=outputs_written,
            validation_status=validation.get("status", "unknown"),
            limitations=[
                "Commitments are only inferred from explicit management promise language in yearly intelligence artifacts.",
                "Delivery remains Unable To Verify when later evidence does not explicitly confirm, contradict, delay, or abandon the commitment.",
            ],
        ),
        "outputs_written": list(outputs_written),
        "validation_status": validation.get("status", "unknown"),
        "limitations": [
            "Commitments are only inferred from explicit management promise language in yearly intelligence artifacts.",
            "Delivery remains Unable To Verify when later evidence does not explicitly confirm, contradict, delay, or abandon the commitment.",
        ],
    }


def _build_commitment_record(company: str, group: Dict[str, Any], commitment_id: str) -> Dict[str, Any]:
    status = _determine_status(group)
    supporting_evidence = sorted(
        group["supporting_evidence"],
        key=lambda item: (_year_sort_key(item["period"]), item["event_type"], item["statement"]),
    )
    if supporting_evidence:
        announcement_evidence = dict(supporting_evidence[0])
        announcement_evidence["event_type"] = "announcement"
        announcement_evidence["status"] = "Announced"
        supporting_evidence = [announcement_evidence] + supporting_evidence[1:]
    progression_events = [
        _progression_event_from_evidence(commitment_id, evidence, index + 1, is_announcement=(index == 0))
        for index, evidence in enumerate(supporting_evidence)
    ]
    progression_timeline = build_progression_timeline(
        subject_id=commitment_id,
        stream_type=_PROGRESSION_ADAPTER.stream_type,
        events=progression_events,
        adapter=_PROGRESSION_ADAPTER,
        unresolved_questions=[] if status != "Unable To Verify" else ["No later evidence confirmed the commitment."],
        coverage_status="supported" if len(progression_events) > 1 else "partial",
    )
    progression_validation = validate_progression_payload(progression_timeline)
    progression = {
        "announcement": {
            "period": group["announcement_period"],
            "statement": next((item["statement"] for item in supporting_evidence if item["event_type"] == "announcement"), supporting_evidence[0]["statement"]),
            "source_reference": next((item["source_reference"] for item in supporting_evidence if item["event_type"] == "announcement"), supporting_evidence[0]["source_reference"]),
        },
        "evidence_updates": [
            {
                "period": item["period"],
                "event_type": item["event_type"],
                "status": item["status"],
                "statement": item["statement"],
                "source_reference": item["source_reference"],
            }
            for item in supporting_evidence
            if item["event_type"] != "announcement"
        ],
        "latest_status": status,
        "latest_period": _latest_evidence_period(group),
        "current_state": progression_timeline["current_state"],
        "turning_points": progression_timeline["turning_points"],
        "state_transitions": progression_timeline["state_transitions"],
        "unresolved_questions": progression_timeline["unresolved_questions"],
        "confidence": progression_timeline["confidence"],
        "coverage_status": progression_timeline["coverage_status"],
        "investor_implication": progression_timeline["investor_implication"],
    }
    original_statement = group["original_statements"][0]
    if not original_statement:
        original_statement = supporting_evidence[0]["statement"]
    return {
        "id": commitment_id,
        "topic": group["topic"],
        "category": group["category"],
        "announcement_period": group["announcement_period"],
        "original_statement": original_statement,
        "normalized_commitment": group["normalized_commitment"],
        "expected_timeframe": group["expected_timeframe"],
        "priority": group["priority"],
        "status": status,
        "supporting_evidence": supporting_evidence,
        "delivery_assessment": _build_delivery_assessment(status, group),
        "confidence": _confidence_for_group(group),
        "investor_implication": _investor_implication(status),
        "source_references": group["source_references"],
        "progression": progression,
        "progression_validation": progression_validation,
        "actor_type": group.get("actor_type"),
        "statement_type": group.get("statement_type"),
        "semantic_quality": group.get("semantic_quality") or {},
    }


def _has_duplicate_source_statements(candidates: Sequence[Dict[str, Any]]) -> bool:
    seen: set[str] = set()
    duplicate = False
    for candidate in candidates:
        key = candidate["normalized_source_statement"]
        if key in seen:
            duplicate = True
            continue
        seen.add(key)
    return duplicate


def _validate_commitment_record(commitment: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    status = commitment.get("status")
    evidence = commitment.get("supporting_evidence") or []
    announcement_period = commitment.get("announcement_period")
    progression = commitment.get("progression") or {}
    latest_period = progression.get("latest_period") or commitment.get("announcement_period")
    original_statement = str(commitment.get("original_statement") or "").strip()
    normalized_commitment = str(commitment.get("normalized_commitment") or "").strip()
    actor_type = str(commitment.get("actor_type") or "unknown")
    statement_type = str(commitment.get("statement_type") or "unknown")

    if actor_type not in COMPANY_ACTORS:
        issues.append({"code": "external_actor_promoted", "severity": "fail", "commitment_id": commitment.get("id"), "message": f"Actor {actor_type} cannot create a management commitment."})
    if statement_type not in ELIGIBLE_COMMITMENT_STATEMENTS | {"expectation"}:
        issues.append({"code": "invalid_commitment_statement_type", "severity": "fail", "commitment_id": commitment.get("id"), "message": f"Statement type {statement_type} is not commitment-eligible."})
    if (commitment.get("semantic_quality") or {}).get("eligibility") != "eligible":
        issues.append({"code": "ineligible_commitment_promoted", "severity": "fail", "commitment_id": commitment.get("id"), "message": "A quarantined candidate was promoted."})

    if status not in ALLOWED_STATUSES:
        issues.append(
            {
                "code": "invalid_status",
                "severity": "fail",
                "commitment_id": commitment.get("id"),
                "message": f"Status {status!r} is not allowed.",
            }
        )

    if not commitment.get("id"):
        issues.append(
            {
                "code": "missing_commitment_id",
                "severity": "fail",
                "message": "Commitment id is required.",
            }
        )

    if not original_statement:
        issues.append(
            {
                "code": "missing_original_statement",
                "severity": "fail",
                "commitment_id": commitment.get("id"),
                "message": "Original statement is required.",
            }
        )

    if not normalized_commitment:
        issues.append(
            {
                "code": "missing_normalized_commitment",
                "severity": "fail",
                "commitment_id": commitment.get("id"),
                "message": "Normalized commitment is required.",
            }
        )

    if not evidence:
        issues.append(
            {
                "code": "missing_evidence",
                "severity": "fail",
                "commitment_id": commitment.get("id"),
                "message": "Commitment has no supporting evidence.",
            }
        )
        return issues

    announcement_evidence = [item for item in evidence if item.get("event_type") == "announcement"]
    if not announcement_evidence:
        issues.append(
            {
                "code": "missing_announcement",
                "severity": "fail",
                "commitment_id": commitment.get("id"),
                "message": "Commitment is missing an announcement event.",
            }
        )

    for item in evidence[1:]:
        period = str(item.get("period") or "").strip()
        if announcement_period and period and _year_sort_key(period) < _year_sort_key(announcement_period):
            issues.append(
                {
                    "code": "announcement_order_violation",
                    "severity": "fail",
                    "commitment_id": commitment.get("id"),
                    "message": "Later evidence appears to predate the announcement period.",
                    "period": period,
                }
            )
            break

    if status == "Delivered":
        decisive = [
            item
            for item in evidence
            if item.get("event_type") in {"delivery_confirmation", "progress_update"} and str(item.get("period") or "") != str(announcement_period or "")
        ]
        if not decisive:
            issues.append(
                {
                    "code": "unsupported_delivery",
                    "severity": "fail",
                    "commitment_id": commitment.get("id"),
                    "message": "Delivered status is not supported by later confirming evidence.",
                }
            )
        if latest_period and announcement_period and _year_sort_key(latest_period) < _year_sort_key(announcement_period):
            issues.append(
                {
                    "code": "future_ambition_marked_delivered",
                    "severity": "fail",
                    "commitment_id": commitment.get("id"),
                    "message": "Delivered status precedes the announcement period.",
                }
            )

    later_evidence = [item for item in evidence if item.get("event_type") not in {"announcement"}]

    if status == "Partially Delivered":
        if not any(item.get("event_type") == "progress_update" for item in later_evidence):
            issues.append(
                {
                    "code": "missing_partial_execution_evidence",
                    "severity": "fail",
                    "commitment_id": commitment.get("id"),
                    "message": "Partially Delivered status requires explicit partial execution evidence.",
                }
            )

    if status == "Delayed":
        if not any(
            item.get("event_type") == "delay_signal"
            or any(marker in _normalize_text(item.get("statement") or "") for marker in DELAYED_MARKERS)
            for item in later_evidence
        ):
            issues.append(
                {
                    "code": "missing_delay_evidence",
                    "severity": "fail",
                    "commitment_id": commitment.get("id"),
                    "message": "Delayed status requires explicit missed-timeframe or delay evidence.",
                }
            )

    if status == "Abandoned":
        if not any(
            item.get("event_type") == "abandonment_signal"
            or any(marker in _normalize_text(item.get("statement") or "") for marker in ABANDONED_MARKERS)
            for item in later_evidence
        ):
            issues.append(
                {
                    "code": "missing_abandonment_evidence",
                    "severity": "fail",
                    "commitment_id": commitment.get("id"),
                    "message": "Abandoned status requires explicit abandonment evidence.",
                }
            )

    if status in {"Partially Delivered", "Delayed", "Superseded", "Abandoned", "In Progress"} and len(evidence) < 2:
        issues.append(
            {
                "code": "missing_follow_up",
                "severity": "fail",
                "commitment_id": commitment.get("id"),
                "message": f"{status} status requires later evidence beyond the original announcement.",
            }
        )

    if status == "Unable To Verify" and len(evidence) > 1:
        issues.append(
            {
                "code": "overstated_verification",
                "severity": "fail",
                "commitment_id": commitment.get("id"),
                "message": "Unable To Verify should only be used when there is no confirming later evidence.",
            }
        )

    return issues


def validate_management_commitments_payload(
    commitments_payload: Dict[str, Any],
    timeline_payload: Optional[Dict[str, Any]] = None,
    source_candidates: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    commitments = commitments_payload.get("commitments") or []
    issues: List[Dict[str, Any]] = []

    if commitments_payload.get("company") in (None, ""):
        issues.append(
            {
                "code": "missing_company",
                "severity": "fail",
                "message": "Company identifier is required.",
            }
        )

    if not commitments:
        issues.append(
            {
                "code": "missing_commitments",
                "severity": "fail",
                "message": "At least one commitment is required.",
            }
        )

    seen_commitments: set[Tuple[str, str, str]] = set()
    seen_ids: set[str] = set()
    for commitment in commitments:
        issues.extend(_validate_commitment_record(commitment))
        commitment_id = str(commitment.get("id") or "").strip()
        if commitment_id:
            if commitment_id in seen_ids:
                issues.append(
                    {
                        "code": "duplicate_commitment_id",
                        "severity": "fail",
                        "commitment_id": commitment.get("id"),
                        "message": "Duplicate commitment id detected in output payload.",
                    }
                )
            else:
                seen_ids.add(commitment_id)
        key = (
            _clean_label(commitment.get("category")),
            _clean_label(commitment.get("normalized_commitment")),
            _clean_label(commitment.get("announcement_period")),
        )
        if key in seen_commitments:
            issues.append(
                {
                    "code": "duplicate_commitment",
                    "severity": "fail",
                    "commitment_id": commitment.get("id"),
                    "message": "Duplicate commitment detected in output payload.",
                }
            )
        else:
            seen_commitments.add(key)

    if source_candidates is not None and _has_duplicate_source_statements(source_candidates):
        issues.append(
            {
                "code": "identical_commitments_across_years",
                "severity": "fail",
                "message": "Identical commitment wording appears multiple times in source years and should be merged.",
            }
        )

    if timeline_payload is not None:
        timeline_commitment_ids = {item.get("id") for item in timeline_payload.get("timeline", []) or []}
        missing = [commitment.get("id") for commitment in commitments if commitment.get("id") not in timeline_commitment_ids]
        if missing:
            issues.append(
                {
                    "code": "timeline_mismatch",
                    "severity": "fail",
                    "message": "Commitments are missing from the progression timeline.",
                    "missing_commitment_ids": missing,
                }
            )

    status = "pass" if not issues else "fail"
    return {
        "status": status,
        "issue_count": len(issues),
        "issues": issues,
    }


@dataclass
class ManagementCommitmentsBuilder:
    company: str
    companies_root: Path | str = Path("companies")
    output_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.companies_root = Path(self.companies_root)
        self.company_root = self.companies_root / self.company
        self.output_dir = self.company_root / "company_memory" / "management_commitments"

    def _discover_years(self) -> List[Path]:
        if not self.company_root.exists():
            return []
        return sorted(
            [path for path in self.company_root.iterdir() if path.is_dir() and path.name.lower().startswith("fy")],
            key=lambda path: _year_sort_key(path.name),
        )

    def _load_year_record(self, year_dir: Path) -> Dict[str, Any]:
        year = year_dir.name
        intelligence_dir = year_dir / "intelligence"
        cim_path = intelligence_dir / "company_intelligence.json"
        summary_path = intelligence_dir / "management_summary.json"

        cim = _load_json(cim_path)
        summary = _load_json(summary_path)

        available_artifacts = {
            "company_intelligence.json": cim_path.exists(),
            "management_summary.json": summary_path.exists(),
        }

        if cim or summary:
            status = "usable"
            reason = ""
        elif any(available_artifacts.values()):
            status = "partial"
            reason = "No usable management commitment artifacts were readable"
        else:
            status = "missing"
            reason = "No management commitment artifacts found"

        return {
            "year": year,
            "sort_key": _year_sort_key(year),
            "status": status,
            "reason": reason,
            "paths": {
                "year_root": str(year_dir),
                "intelligence_dir": str(intelligence_dir),
            },
            "available_artifacts": available_artifacts,
            "company_intelligence": cim,
            "management_summary": summary,
        }

    def _extract_candidates(self, year_record: Dict[str, Any]) -> List[Dict[str, Any]]:
        return _extract_source_item_years(year_record)

    def _build_groups(self, candidates: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups: List[Dict[str, Any]] = []
        for candidate in sorted(candidates, key=lambda item: (item["sort_key"], item["category"], item["topic"], item["original_statement"])):
            matched_group = None
            for group in groups:
                same_category = group["category"] == candidate["category"]
                same_topic = _normalize_text(candidate["topic"]) == _normalize_text(group["topic"]) or _promise_theme_key(candidate["topic"]) == _promise_theme_key(group["topic"])
                compatible_topic = same_topic or _promises_match(candidate["normalized_commitment"], group["normalized_commitment"]) or _promises_match(
                    candidate["original_statement"], group["original_statements"][0]
                )
                if same_category and compatible_topic:
                    matched_group = group
                    break
            if matched_group is None:
                if candidate.get("commitment_role") == "announcement":
                    groups.append(_build_group_from_candidate(candidate))
            else:
                _merge_group(matched_group, candidate)

        groups.sort(key=lambda group: (_year_sort_key(group["announcement_period"]), group["category"], group["topic"], group["normalized_commitment"]))
        return groups

    def _build_timeline(self, commitments: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        timeline: List[Dict[str, Any]] = []
        for commitment in commitments:
            events: List[Dict[str, Any]] = []
            for evidence in commitment.get("supporting_evidence") or []:
                events.append(
                    {
                        "period": evidence["period"],
                        "event_type": evidence["event_type"],
                        "status": evidence["status"],
                        "statement": evidence["statement"],
                        "source_reference": evidence["source_reference"],
                    }
                )
            events.append(_latest_assessment_event(commitment["status"], commitment))
            timeline.append(
                {
                    "id": commitment["id"],
                    "topic": commitment["topic"],
                    "category": commitment["category"],
                    "announcement_period": commitment["announcement_period"],
                    "latest_status": commitment["status"],
                    "latest_period": commitment["progression"]["latest_period"],
                    "events": events,
                }
            )
        return {
            "company": self.company,
            "timeline": timeline,
        }

    def build(self) -> Dict[str, Path]:
        year_records = [self._load_year_record(year_dir) for year_dir in self._discover_years()]
        candidates: List[Dict[str, Any]] = []
        for year_record in year_records:
            candidates.extend(self._extract_candidates(year_record))

        eligible_candidates = [candidate for candidate in candidates if (candidate.get("semantic_quality") or {}).get("eligibility") == "eligible"]
        quarantined_candidates = [
            {
                "period": candidate.get("period"),
                "source_artifact": candidate.get("source_artifact"),
                "source_item_id": candidate.get("source_item_id"),
                "original_statement": candidate.get("original_statement"),
                "actor_type": candidate.get("actor_type"),
                "statement_type": candidate.get("statement_type"),
                "semantic_quality": candidate.get("semantic_quality"),
            }
            for candidate in candidates
            if (candidate.get("semantic_quality") or {}).get("eligibility") != "eligible"
        ]
        groups = self._build_groups(eligible_candidates)
        commitments = [
            _build_commitment_record(self.company, group, f"MC-{index + 1:04d}")
            for index, group in enumerate(groups)
        ]
        timeline = self._build_timeline(commitments)
        progression_issues: List[Dict[str, Any]] = []
        for commitment in commitments:
            progression_validation = commitment.get("progression_validation") or {}
            for issue in progression_validation.get("issues") or []:
                progression_issues.append(
                    {
                        "code": f"progression_{issue.get('code', 'unknown')}",
                        "severity": issue.get("severity", "fail"),
                        "commitment_id": commitment.get("id"),
                        "message": issue.get("message", "Progression validation failed."),
                    }
                )
        validation = validate_management_commitments_payload(
            {
                "company": self.company,
                "commitments": commitments,
            },
            timeline_payload=timeline,
            source_candidates=eligible_candidates,
        )
        if progression_issues:
            validation["issues"].extend(progression_issues)
            validation["issue_count"] = len(validation["issues"])
            validation["status"] = "fail"

        summary = {
            "schema_version": SCHEMA_VERSION,
            "company": self.company,
            "generated_at": _utc_now(),
            "generator_version": GENERATOR_VERSION,
            "source_years": [record["year"] for record in year_records if record["status"] == "usable"],
            "commitment_count": len(commitments),
            "quarantined_candidate_count": len(quarantined_candidates),
            "quarantined_candidates": quarantined_candidates,
            "status_counts": {
                status: sum(1 for commitment in commitments if commitment["status"] == status)
                for status in ALLOWED_STATUSES
            },
            "category_counts": {
                category: sum(1 for commitment in commitments if commitment["category"] == category)
                for category in ALLOWED_CATEGORIES
            },
            "commitments": commitments,
        }

        files = {
            "management_commitments.json": summary,
            "commitment_timeline.json": timeline,
            "commitment_validation.json": {
                "schema_version": SCHEMA_VERSION,
                "company": self.company,
                "generated_at": _utc_now(),
                **validation,
            },
        }

        manifest = _build_manifest(
            company=self.company,
            year_records=year_records,
            commitments=commitments,
            validation=validation,
            outputs_written=list(files.keys()) + ["management_commitments_manifest.json"],
        )
        files["management_commitments_manifest.json"] = manifest

        written_paths: Dict[str, Path] = {}
        for filename, payload in files.items():
            written_paths[filename] = _write_json(self.output_dir / filename, payload)
        return written_paths


def build_management_commitments(company: str, companies_root: Path | str = Path("companies")) -> Dict[str, Path]:
    return ManagementCommitmentsBuilder(company=company, companies_root=companies_root).build()
