from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .sanitizer import sanitize_public_payload, sanitize_public_text


MAX_JOURNEY_STAGES = 4
MAX_HISTORICAL_STAGES = 3
VAGUE_PHRASES = {
    "measured operating push",
    "continued momentum",
    "strategic evolution",
    "enhanced capabilities",
}


def build_business_journey(source_bundle: Dict[str, Any], *, company_slug: str, generated_at: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    events = extract_candidate_journey_events(source_bundle)
    merged = merge_related_journey_events(events)
    historical_stages, current_state = split_historical_and_current_stages(merged)
    stated_direction = infer_stated_direction(source_bundle)
    legacy_current_direction = _legacy_current_direction(current_state, stated_direction)
    open_questions = build_open_questions(source_bundle, historical_stages, current_state, stated_direction)

    if not merged:
        payload = sanitize_public_payload(
            {
                "schema_version": "ask_intrinsiciq_business_journey.v1",
                "company_slug": company_slug,
                "summary": "The available company memory explains the current business, but does not yet establish a reliable multi-year business journey.",
                "stages": [],
                "historical_stages": [],
                "current_state": None,
                "stated_direction": stated_direction,
                "current_direction": legacy_current_direction,
                "open_questions": open_questions,
                "coverage_status": "partial" if legacy_current_direction else "unavailable",
                "generated_at": generated_at,
            }
        )
        diagnostics = {
            "candidate_events": events,
            "merged_events": [],
            "source_kinds_used": sorted({event.get("source_kind") for event in events if event.get("source_kind")}),
        }
        return payload, diagnostics

    coverage_status = "supported" if len(historical_stages) >= 1 and current_state else "partial"
    summary = build_journey_summary(historical_stages, current_state, stated_direction)
    public_historical = [to_public_stage(event, index + 1) for index, event in enumerate(historical_stages[:MAX_HISTORICAL_STAGES])]
    public_current_state = to_public_state(current_state) if current_state else None
    stages_for_legacy = list(public_historical)
    if public_current_state:
        stages_for_legacy.append(
            {
                "id": public_current_state["id"],
                "period_label": public_current_state["period_label"],
                "title": public_current_state["title"],
                "simple_description": public_current_state["description"],
                "significance": public_current_state["why_it_matters"],
                "evidence_status": public_current_state["evidence_status"],
                "display_order": len(stages_for_legacy) + 1,
            }
        )
    payload = sanitize_public_payload(
        {
            "schema_version": "ask_intrinsiciq_business_journey.v1",
            "company_slug": company_slug,
            "summary": summary,
            "stages": stages_for_legacy[:MAX_JOURNEY_STAGES],
            "historical_stages": public_historical,
            "current_state": public_current_state,
            "stated_direction": stated_direction,
            "current_direction": legacy_current_direction,
            "open_questions": open_questions,
            "coverage_status": coverage_status,
            "generated_at": generated_at,
        }
    )
    diagnostics = {
        "candidate_events": events,
        "merged_events": merged,
        "source_kinds_used": sorted({event.get("source_kind") for event in events if event.get("source_kind")}),
        "quality_issues": validate_business_journey_quality(payload),
    }
    return payload, diagnostics


def extract_candidate_journey_events(source_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources = source_bundle.get("sources") or {}
    events: List[Dict[str, Any]] = []

    pcim = ((sources.get("pcim") or {}).get("payload")) or {}
    business_understanding = pcim.get("business_understanding") or {}
    for item in business_understanding.get("business_model_by_year", []) or []:
        if not isinstance(item, dict):
            continue
        year = str(item.get("year") or "").strip()
        if not year:
            continue
        business_summary = str(item.get("business_summary") or "").strip()
        business_model = str(item.get("business_model") or "").strip()
        value_creation = str(item.get("value_creation") or "").strip()
        if not (business_summary or business_model):
            continue
        title = _infer_stage_title(
            dnas=_year_dnas(business_understanding.get("business_dna_by_year", []), year),
            summary=business_summary,
            model=business_model,
        )
        description = _first_sentence(business_summary or business_model)
        significance = _first_sentence(value_creation) or _significance_from_model(business_model)
        events.append(
            {
                "period": year,
                "event_type": "current_state_snapshot",
                "title": title,
                "description": description,
                "significance": significance,
                "source_kind": "pcim_business_model",
                "confidence": "high",
                "provenance": {"year": year, "source": "pcim.business_understanding.business_model_by_year"},
                "signature": _build_signature(title, description, _year_dnas(business_understanding.get("business_dna_by_year", []), year)),
            }
        )

    strategy_timeline = ((sources.get("multi_year_strategy_timeline") or {}).get("payload")) or {}
    for item in strategy_timeline.get("strategy_shifts", []) or []:
        if not isinstance(item, dict):
            continue
        added = [str(value) for value in item.get("added_themes", []) if str(value).strip()]
        removed = [str(value) for value in item.get("removed_themes", []) if str(value).strip()]
        if not added and not removed:
            continue
        from_year = str(item.get("from_year") or "").strip()
        to_year = str(item.get("to_year") or "").strip()
        title, description, significance = _describe_strategy_shift(added, removed)
        if not title:
            continue
        events.append(
            {
                "period": to_year or from_year,
                "event_type": "strategic_direction",
                "title": title,
                "description": description,
                "significance": significance,
                "source_kind": "multi_year_strategy",
                "confidence": "medium",
                "provenance": {"from_year": from_year, "to_year": to_year, "source": "multi_year.strategy_timeline"},
                "signature": _build_signature(title, description, added + removed),
            }
        )

    dna_evolution = ((sources.get("multi_year_business_dna_evolution") or {}).get("payload")) or {}
    for item in dna_evolution.get("changes_detected", []) or []:
        if not isinstance(item, dict):
            continue
        statuses = item.get("status_changes", []) or []
        new_or_removed: List[str] = []
        for status in statuses:
            if not isinstance(status, dict):
                continue
            dna = str(status.get("dna") or "").strip()
            change = str(status.get("status") or "").strip()
            if not dna or not change or change not in {"newly_detected", "not_detected_this_year", "continued"}:
                continue
            if change == "continued":
                continue
            new_or_removed.append(f"{dna}:{change}")
        if not new_or_removed:
            continue
        title, description, significance = _describe_dna_change(new_or_removed)
        events.append(
            {
                "period": str(item.get("to_year") or item.get("from_year") or "").strip(),
                "event_type": "business_model_transition",
                "title": title,
                "description": description,
                "significance": significance,
                "source_kind": "multi_year_business_dna",
                "confidence": "medium",
                "provenance": {"source": "multi_year.business_dna_evolution", "changes": new_or_removed},
                "signature": _build_signature(title, description, new_or_removed),
            }
        )

    return sorted(events, key=lambda event: (_year_sort_key(event.get("period")), event.get("title", "")))


def merge_related_journey_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for event in events:
        if not merged:
            merged.append(_copy_event(event))
            continue
        previous = merged[-1]
        if str(previous.get("period_end") or "") == str(event.get("period") or ""):
            should_absorb = (
                (
                    previous.get("event_type") == "current_state_snapshot"
                    and event.get("event_type") in {"strategic_direction", "business_model_transition"}
                )
                or (
                    event.get("event_type") == "current_state_snapshot"
                    and previous.get("event_type") in {"strategic_direction", "business_model_transition"}
                )
            )
            if should_absorb:
                primary_title = previous.get("title")
                secondary_title = event.get("title")
                primary_description = previous.get("description")
                secondary_description = event.get("description")
                primary_significance = previous.get("significance")
                secondary_significance = event.get("significance")
                if event.get("event_type") == "current_state_snapshot":
                    primary_title = event.get("title")
                    secondary_title = previous.get("title")
                    primary_description = event.get("description")
                    secondary_description = previous.get("description")
                    primary_significance = event.get("significance")
                    secondary_significance = previous.get("significance")
                    previous["event_type"] = "current_state_snapshot"
                previous["title"] = _prefer_title(primary_title, secondary_title)
                previous["description"] = _prefer_richer_text(primary_description, secondary_description)
                previous["significance"] = _prefer_richer_text(primary_significance, secondary_significance)
                previous["signature"] = _build_signature(
                    str(previous.get("title") or ""),
                    str(previous.get("description") or ""),
                    [str(previous.get("signature") or ""), str(event.get("signature") or "")],
                )
                previous.setdefault("provenance_items", []).append(event.get("provenance"))
                previous.setdefault("source_kinds", []).append(event.get("source_kind"))
                continue
        if previous.get("signature") == event.get("signature"):
            previous["period_end"] = event.get("period")
            previous["description"] = previous.get("description") or event.get("description")
            previous["significance"] = previous.get("significance") or event.get("significance")
            previous.setdefault("provenance_items", []).append(event.get("provenance"))
            previous.setdefault("source_kinds", []).append(event.get("source_kind"))
            continue
        merged.append(_copy_event(event))

    merged = _compact_repeated_phases(merged)
    compacted: List[Dict[str, Any]] = []
    for event in merged:
        if len(compacted) >= MAX_JOURNEY_STAGES:
            break
        compacted.append(event)
    return _finalize_period_labels(compacted)


def classify_journey_evidence(event: Dict[str, Any]) -> str:
    source_kinds = set(event.get("source_kinds") or [])
    if event.get("source_kind"):
        source_kinds.add(str(event.get("source_kind")))
    if {"pcim_business_model", "multi_year_strategy", "multi_year_business_dna"} & source_kinds and len(source_kinds) >= 2:
        return "direct"
    if "pcim_business_model" in source_kinds and len(source_kinds) == 1:
        return "partial"
    if source_kinds:
        return "derived"
    return "missing"


def to_public_stage(event: Dict[str, Any], display_order: int) -> Dict[str, Any]:
    period_label = _build_period_label(event)
    return {
        "id": _slugify(f"{period_label}-{event.get('title') or 'stage'}"),
        "period_label": period_label,
        "title": sanitize_public_text(str(event.get("title") or "Business phase")),
        "simple_description": sanitize_public_text(str(event.get("description") or "")),
        "significance": sanitize_public_text(str(event.get("significance") or "")),
        "evidence_status": classify_journey_evidence(event),
        "display_order": display_order,
    }


def infer_stated_direction(source_bundle: Dict[str, Any]) -> Optional[Dict[str, str]]:
    sources = source_bundle.get("sources") or {}
    pcim = ((sources.get("pcim") or {}).get("payload")) or {}
    growth = pcim.get("growth_quality_inputs") or {}
    projects = growth.get("projects_by_year") or []
    latest_projects = _latest_year_items(projects)
    expansion_items = []
    for item in latest_projects:
        value = str(item.get("value") or "").strip()
        status = jsonish(item.get("evidence_references"), "status")
        if not value:
            continue
        lowered = value.lower()
        if any(token in lowered for token in ("expansion", "facility", "testing", "hangar", "integration", "technology")):
            expansion_items.append((value, status))
    if expansion_items:
        return {
            "title": "Further capacity and testing expansion",
            "description": sanitize_public_text("Management has stated an intention to keep expanding manufacturing and testing capability."),
            "evidence_status": "partial",
        }

    latest_view = ((pcim.get("business_understanding") or {}).get("latest_business_view")) or {}
    business_model = latest_view.get("business_model") or {}
    model_text = str(business_model.get("business_model") or "").strip().lower()
    if "expand" in model_text or "working capital" in model_text or "technology infrastructure" in model_text:
        return {
            "title": "Continued operating-capacity investment",
            "description": sanitize_public_text("Available evidence suggests the company is still investing to deepen its operating capacity."),
            "evidence_status": "derived",
        }
    return None


def build_open_questions(
    source_bundle: Dict[str, Any],
    historical_stages: List[Dict[str, Any]],
    current_state: Optional[Dict[str, Any]],
    stated_direction: Optional[Dict[str, str]],
) -> List[str]:
    questions: List[str] = []
    years = _available_years(source_bundle)
    if len(years) <= 1:
        questions.append("How much of the current business model is new versus long-standing?")
    if stated_direction and "expand" in str(stated_direction.get("description") or "").lower():
        questions.append("Has the added capacity become economically meaningful yet?")
    if historical_stages and any("export" in str(stage.get("title") or "").lower() for stage in historical_stages):
        questions.append("How much of revenue now comes from export or non-domestic programmes?")
    if current_state and "system" in str(current_state.get("title") or "").lower():
        questions.append("Which current offering families matter most to delivery and customer dependence?")
    if len(questions) < 2:
        questions.append("Which part of the business change is most clearly supported by multi-year evidence?")
    if len(questions) < 2:
        questions.append("What still needs clearer disclosure to confirm the business transition?")
    return [sanitize_public_text(question) for question in questions[:4]]


def build_journey_summary(
    historical_stages: List[Dict[str, Any]],
    current_state: Optional[Dict[str, Any]] = None,
    stated_direction: Optional[Dict[str, str]] = None,
    current_direction: Optional[str] = None,
) -> str:
    if current_direction and not stated_direction:
        stated_direction = {
            "title": "Current direction",
            "description": current_direction,
            "evidence_status": "partial",
        }
    if historical_stages and current_state is None and "period_label" not in historical_stages[0]:
        if len(historical_stages) > 1:
            current_state = historical_stages[-1]
            historical_stages = historical_stages[:-1]
        else:
            current_state = historical_stages[0]
            historical_stages = []
    if not historical_stages and current_state:
        return sanitize_public_text(
            f"The available evidence mainly supports the current business state: {str(current_state.get('title') or '').lower()}."
        )
    if not historical_stages:
        return "A reliable business-journey summary is not yet available."
    start = str(historical_stages[0].get("title") or "the earlier business").lower()
    current = str((current_state or {}).get("title") or historical_stages[-1].get("title") or "the current business").lower()
    if _normalize_token(start) == _normalize_token(current):
        sentence = f"The business appears to have deepened within the same broad operating model while adding more visible delivery and capacity evidence."
    else:
        sentence = f"The business appears to have evolved from {start} toward {current}."
    if stated_direction:
        sentence += f" Management is also pointing toward {str(stated_direction.get('title') or '').lower()}, but that remains a stated direction rather than a completed outcome."
    return sanitize_public_text(sentence)


def split_historical_and_current_stages(events: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if not events:
        return [], None
    trimmed = list(events[:MAX_JOURNEY_STAGES])
    if len(trimmed) == 1:
        return [], trimmed[0]
    historical = trimmed[:-1][:MAX_HISTORICAL_STAGES]
    current_state = trimmed[-1]
    return historical, current_state


def to_public_state(event: Dict[str, Any]) -> Dict[str, Any]:
    period_label = _build_period_label(event)
    return {
        "id": _slugify(f"{period_label}-{event.get('title') or 'current-state'}"),
        "period_label": period_label,
        "title": sanitize_public_text(str(event.get("title") or "Current business state")),
        "description": sanitize_public_text(str(event.get("description") or "")),
        "why_it_matters": sanitize_public_text(str(event.get("significance") or "")),
        "evidence_status": classify_journey_evidence(event),
    }


def _legacy_current_direction(current_state: Optional[Dict[str, Any]], stated_direction: Optional[Dict[str, str]]) -> Optional[str]:
    if stated_direction:
        return str(stated_direction.get("description") or "").strip() or None
    if current_state:
        return sanitize_public_text(f"The current business state appears to be {str(current_state.get('title') or '').lower()}.")
    return None


def validate_business_journey_quality(journey: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    stages = list(journey.get("historical_stages") or journey.get("stages") or [])
    titles = [_normalize_token(str(stage.get("title") or "")) for stage in stages]
    if len(set(titles)) != len([title for title in titles if title]):
        issues.append("duplicate phases")
    for stage in stages:
        text = " ".join(
            [
                str(stage.get("title") or ""),
                str(stage.get("simple_description") or stage.get("description") or ""),
                str(stage.get("significance") or stage.get("why_it_matters") or ""),
            ]
        )
        lowered = text.lower()
        if any(phrase in lowered for phrase in VAGUE_PHRASES):
            issues.append("vague phrases")
        if _looks_broken_sentence(text):
            issues.append("broken sentences")
    stated_direction = journey.get("stated_direction") or {}
    if isinstance(stated_direction, dict):
        description = str(stated_direction.get("description") or "").lower()
        if any(token in description for token in ("has become", "is now", "already achieved")):
            issues.append("future ambition phrased as achieved fact")
    return sorted(set(issues))


def _looks_broken_sentence(text: str) -> bool:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return False
    return any(
        marker in cleaned
        for marker in (
            " This matters because",
            " from an integrated Chennai",
            "returning cash to",
        )
    )


def _year_dnas(items: List[Dict[str, Any]], year: str) -> List[str]:
    for item in items:
        if str(item.get("year") or "").strip() != year:
            continue
        values = []
        for dna in item.get("business_dnas", []) or []:
            if isinstance(dna, dict):
                value = str(dna.get("value") or "").strip()
            else:
                value = str(dna).strip()
            if value:
                values.append(value)
        return values
    return []


def _infer_stage_title(*, dnas: List[str], summary: str, model: str) -> str:
    lowered = f"{summary} {model}".lower()
    if any(token in lowered for token in ("cpaas", "messaging platform", "communications platform", "enterprise communications", "cloud communications", "marketing automation")):
        return "Enterprise communications platform"
    if "export" in lowered:
        return "Export-capable defence electronics maker"
    if any(token in lowered for token in ("satellite", "radar", "electronic warfare", "defence", "aerospace")):
        return "Broader defence and space systems delivery"
    if any(
        token in lowered
        for token in (
            "deploying significant capital",
            "funded in part by qip",
            "funded in part by ipo",
            "unutilised proceeds",
            "land/building acquisition",
            "building upgrades",
            "emi-emc",
            "technology infrastructure",
        )
    ):
        return "Capacity expansion phase"
    if any(token in lowered for token in ("testing facility", "integration hangar", "facility")):
        return "Integrated manufacturing buildout"
    if "manufactur" in lowered:
        return "Defence electronics manufacturer"
    if any(token in lowered for token in ("transition phase", "operating focus", "business model")):
        sentence = _first_sentence(summary or model)
        if sentence:
            trimmed = sentence.rstrip(".")
            return trimmed[:72].strip()
    if dnas:
        return f"{dnas[0]}-led business"
    return "Operating business model"


def _significance_from_model(model: str) -> str:
    lowered = model.lower()
    if "equity" in lowered or "capex" in lowered:
        return "This phase shows how the company funded and scaled its operating base."
    if "export" in lowered:
        return "This phase suggests the company was broadening beyond a purely domestic customer set."
    return "This phase helps explain how the current business was built."


def _describe_strategy_shift(added: List[str], removed: List[str]) -> Tuple[str, str, str]:
    joined = " ".join(added).lower()
    if any(item in joined for item in ("plant_construction", "land_facility_expansion", "manufacturing_capacity_expansion")):
        return (
            "Capacity expansion phase",
            "The company shifted attention toward adding facility or manufacturing capacity.",
            "This matters because physical expansion can change delivery capability and the scale of future programmes.",
        )
    if "geographic_expansion" in joined:
        return (
            "Broader market reach",
            "The company began emphasizing a wider market reach.",
            "This matters because customer reach can change where growth comes from.",
        )
    return ("", "", "")


def _describe_dna_change(changes: List[str]) -> Tuple[str, str, str]:
    lowered = " ".join(changes).lower()
    if "export:newly_detected" in lowered:
        return (
            "Export capability became visible",
            "Multi-year evidence started to show export activity as a clearer part of the business mix.",
            "This matters because it suggests the company may be reaching beyond its earlier domestic base.",
        )
    if "ip library:not_detected_this_year" in lowered:
        return (
            "Business mix became more operating-led",
            "The later evidence leaned more toward operating execution than earlier intellectual-property signals.",
            "This matters because it changes how the business should be understood day to day.",
        )
    return ("", "", "")


def _build_signature(title: str, description: str, tags: List[str]) -> str:
    normalized = " ".join(sorted({_normalize_token(title), _normalize_token(description), *[_normalize_token(tag) for tag in tags]}))
    return normalized.strip()


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _copy_event(event: Dict[str, Any]) -> Dict[str, Any]:
    copied = dict(event)
    copied["period_start"] = event.get("period")
    copied["period_end"] = event.get("period")
    copied["source_kinds"] = [event.get("source_kind")] if event.get("source_kind") else []
    copied["provenance_items"] = [event.get("provenance")] if event.get("provenance") else []
    return copied


def _compact_repeated_phases(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    compacted: List[Dict[str, Any]] = []
    for event in events:
        title_key = _normalize_token(str(event.get("title") or ""))
        existing = next(
            (
                item
                for item in compacted
                if _normalize_token(str(item.get("title") or "")) == title_key
                and _descriptions_are_similar(
                    str(item.get("description") or ""),
                    str(event.get("description") or ""),
                )
            ),
            None,
        )
        if existing is None:
            compacted.append(event)
            continue
        existing["period_start"] = existing.get("period_start") or event.get("period_start") or event.get("period")
        existing["period_end"] = event.get("period_end") or event.get("period") or existing.get("period_end")
        existing["description"] = _prefer_richer_text(existing.get("description"), event.get("description"))
        existing["significance"] = _prefer_richer_text(existing.get("significance"), event.get("significance"))
        existing["signature"] = _build_signature(
            str(existing.get("title") or ""),
            str(existing.get("description") or ""),
            [str(existing.get("signature") or ""), str(event.get("signature") or "")],
        )
        existing.setdefault("provenance_items", []).extend(event.get("provenance_items") or [])
        existing.setdefault("source_kinds", []).extend(event.get("source_kinds") or [])
    return compacted


def _descriptions_are_similar(left: str, right: str) -> bool:
    left_tokens = {token for token in _normalize_token(left).split() if token}
    right_tokens = {token for token in _normalize_token(right).split() if token}
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens)
    return overlap >= max(3, min(len(left_tokens), len(right_tokens)) // 2)


def _finalize_period_labels(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for event in events:
        event["period_start"] = event.get("period_start") or event.get("period")
        event["period_end"] = event.get("period_end") or event.get("period")
    return sorted(events, key=lambda item: _year_sort_key(item.get("period_start")))


def _build_period_label(event: Dict[str, Any]) -> str:
    start = str(event.get("period_start") or "").strip()
    end = str(event.get("period_end") or "").strip()
    if start and end and start != end:
        return f"{start.upper()}–{end.upper()}"
    if start:
        return start.upper()
    return "Current phase"


def _first_sentence(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace(" This matters because", ". This matters because")
    cleaned = re.sub(r"\b(Chennai|IPO|QIP)\s+The company shifted\b", r"\1. The company shifted", cleaned)
    cleaned = re.sub(r"\breturning cash to\b", "returning cash to shareholders where supported", cleaned)
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    sentence = parts[0].strip()
    sentence = re.split(r"\bThis matters because\b", sentence)[0].strip()
    if len(sentence) <= 220:
        return _trim_dangling_fragment(sentence)
    trimmed = sentence[:220]
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0]
    return _trim_dangling_fragment(trimmed.strip())


def _trim_dangling_fragment(text: str) -> str:
    cleaned = str(text or "").strip(" ,;:-")
    cleaned = re.sub(r"\bfrom an integrated Chennai\b", "", cleaned, flags=re.IGNORECASE).strip(" ,;:-")
    cleaned = re.sub(r"\btesting and systems\b$", "testing systems", cleaned, flags=re.IGNORECASE).strip(" ,;:-")
    cleaned = re.sub(r"\band returning cash\b$", "", cleaned, flags=re.IGNORECASE).strip(" ,;:-")
    cleaned = re.sub(r"\b(and|or|to|with|from)$", "", cleaned).strip(" ,;:-")
    return cleaned


def _available_years(source_bundle: Dict[str, Any]) -> List[str]:
    index = ((source_bundle.get("sources") or {}).get("company_memory_index") or {}).get("payload") or {}
    years = index.get("usable_years") or index.get("ordered_years") or index.get("discovered_years") or []
    return [str(year) for year in years if str(year).strip()]


def _latest_year_items(items_by_year: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items_by_year:
        return []
    ordered = sorted(
        [item for item in items_by_year if isinstance(item, dict)],
        key=lambda item: _year_sort_key(item.get("year")),
    )
    latest = ordered[-1]
    return [item for item in latest.get("items", []) if isinstance(item, dict)]


def _year_sort_key(value: Any) -> int:
    text = str(value or "").lower().replace("fy", "").strip()
    try:
        return int(text)
    except ValueError:
        return 0


def _slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-") or "stage"


def jsonish(value: Any, key: str) -> str:
    if isinstance(value, dict):
        return str(value.get(key) or "").strip()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and str(item.get(key) or "").strip():
                return str(item.get(key) or "").strip()
    return ""


def _merge_text(primary: Any, secondary: Any) -> str:
    primary_text = str(primary or "").strip()
    secondary_text = str(secondary or "").strip()
    if not primary_text:
        return secondary_text
    if not secondary_text or secondary_text in primary_text:
        return primary_text
    return f"{primary_text} {secondary_text}".strip()


def _prefer_richer_text(primary: Any, secondary: Any) -> str:
    primary_text = _first_sentence(str(primary or ""))
    secondary_text = _first_sentence(str(secondary or ""))
    if not primary_text:
        return secondary_text
    if not secondary_text:
        return primary_text
    if len(secondary_text) > len(primary_text) and secondary_text not in primary_text:
        return secondary_text
    return primary_text


def _prefer_title(primary: Any, secondary: Any) -> str:
    primary_text = str(primary or "").strip()
    secondary_text = str(secondary or "").strip()
    if not primary_text:
        return secondary_text
    if not secondary_text:
        return primary_text
    if _title_priority(secondary_text) > _title_priority(primary_text):
        return secondary_text
    return primary_text


def _title_priority(value: str) -> int:
    lowered = str(value or "").lower()
    if "enterprise communications platform" in lowered:
        return 6
    if "broader defence and space systems delivery" in lowered:
        return 6
    if "export" in lowered:
        return 5
    if any(token in lowered for token in ("integrated", "manufacturer", "manufacturing")):
        return 4
    if any(token in lowered for token in ("capacity", "expansion", "market reach")):
        return 2
    return 1
