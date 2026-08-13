from __future__ import annotations

from typing import Any, Dict, List

from intelligence.progression import build_confidence, build_progression_timeline, event_deduplication_key

from .contracts import COMMENTARY_POSITION_ORDER
from .theme_mapper import normalize_text, sanitize_public_text


def _derived_position(item: Dict[str, Any], *, repeated_years: int, specificity_level: str, consistency_status: str) -> str:
    text = f"{sanitize_public_text(item.get('commentary') or item.get('value') or item.get('summary') or '')} {sanitize_public_text(item.get('status') or '')}".lower()
    if any(term in text for term in ("contradict", "reverse", "opposite", "no longer", "not")) and repeated_years > 1:
        return "contradicted"
    if any(term in text for term in ("reduce", "reduced", "less", "softer", "soften", "cautious", "moderate", "thinner")):
        return "softened"
    if any(term in text for term in ("revised", "update", "updated", "reframe", "shift", "change in focus")) and repeated_years > 1:
        return "revised"
    if any(term in text for term in ("strengthen", "more specific", "specific", "detailed", "expanded", "deeper", "clearer")):
        return "strengthened"
    if repeated_years <= 1:
        return "newly_introduced"
    if consistency_status == "mixed":
        return "revised"
    if specificity_level == "high":
        return "stable_priority"
    if specificity_level == "medium":
        return "increasing_priority"
    return "stable_priority"


def build_commentary_event(candidate: Dict[str, Any], sequence: int, *, repeated_years: int, consistency_status: str) -> Dict[str, Any]:
    commentary = sanitize_public_text(candidate.get("commentary") or candidate.get("value") or candidate.get("summary") or "")
    title = candidate.get("theme_name") or candidate.get("theme_label") or "Management commentary"
    specificity_level = str((candidate.get("specificity") or {}).get("level") or "low")
    position = _derived_position(candidate, repeated_years=repeated_years, specificity_level=specificity_level, consistency_status=consistency_status)
    event_type = "commentary_update"
    if position == "contradicted":
        event_type = "contradiction"
    elif position in {"revised", "softened"}:
        event_type = "superseded"
    elif position == "strengthened":
        event_type = "confirmation"
    return {
        "event_id": f"{candidate['theme_id']}-E{sequence:03d}",
        "stream_type": "management_commentary",
        "subject_id": candidate["theme_id"],
        "period": candidate["source_year"],
        "sequence": sequence,
        "event_type": event_type,
        "title": title,
        "description": commentary or title,
        "evidence_status": candidate.get("evidence_status") or "supported",
        "confidence": candidate.get("confidence") or build_confidence("medium", basis=["management commentary source record"], limitations=[]),
        "semantic_quality": candidate.get("semantic_quality") or {},
        "source_references": [candidate["source_reference"]],
        "metadata": {
            "theme_name": candidate.get("theme_name"),
            "normalized_theme": candidate.get("normalized_theme"),
            "theme_category": candidate.get("theme_category"),
            "raw_category": candidate.get("raw_category"),
            "raw_theme": candidate.get("raw_theme"),
            "sentiment": candidate.get("sentiment"),
            "status": candidate.get("status"),
            "derived_position": position,
            "specificity_level": specificity_level,
            "latest_emphasis": candidate.get("latest_emphasis") or commentary or title,
            "why_it_matters": candidate.get("why_it_matters") or "Management language can signal shifting priorities, confidence, and follow-through.",
        },
    }


class ManagementCommentaryProgressionAdapter:
    stream_type = "management_commentary"

    def normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(event)
        normalized["stream_type"] = self.stream_type
        normalized["subject_id"] = str(normalized.get("subject_id") or "").strip()
        normalized["period"] = str(normalized.get("period") or "").strip().lower()
        normalized["sequence"] = int(normalized.get("sequence") or 0)
        normalized["event_type"] = str(normalized.get("event_type") or "commentary_update").strip()
        normalized["title"] = str(normalized.get("title") or "").strip()
        normalized["description"] = str(normalized.get("description") or "").strip()
        normalized["evidence_status"] = str(normalized.get("evidence_status") or "supported").strip()
        normalized["confidence"] = normalized.get("confidence") or build_confidence("unavailable", basis=[], limitations=["missing confidence"])
        normalized["source_references"] = list(normalized.get("source_references") or [])
        normalized["metadata"] = dict(normalized.get("metadata") or {})
        return normalized

    def deduplicate_key(self, event: Dict[str, Any]) -> str:
        return event_deduplication_key(event)

    def validate_transition(self, previous_state: Any, event: Dict[str, Any], next_state: Any) -> Dict[str, Any]:
        transition_type = str(event.get("event_type") or "commentary_update")
        accepted = True
        reason = ""
        if not next_state:
            accepted = False
            reason = "No derived commentary position was produced."
        return {
            "accepted": accepted,
            "transition_type": transition_type,
            "reason": reason,
            "confidence": build_confidence("high" if accepted else "medium", basis=["deterministic commentary progression"], limitations=[reason] if reason else []),
        }

    def derive_current_state(self, events: List[Dict[str, Any]]) -> Any:
        if not events:
            return "unable_to_verify"
        for event in reversed(events):
            position = (event.get("metadata") or {}).get("derived_position")
            if position:
                return position
        return "unable_to_verify"

    def build_investor_implication(self, timeline: Dict[str, Any]) -> Dict[str, Any]:
        current_state = str(timeline.get("current_state") or "unable_to_verify")
        turning_points = timeline.get("turning_points") or []
        events = timeline.get("events") or []
        if current_state in {"contradicted"}:
            conviction = "weakened"
            summary = "Later commentary conflicts with earlier framing, so conviction should soften."
        elif current_state in {"dropped_without_follow_up"}:
            conviction = "weakened"
            summary = "The theme stopped getting follow-up, so its importance appears to have faded."
        elif current_state in {"softened", "reduced_priority"}:
            conviction = "weakened"
            summary = "Management appears less forceful or less focused on this theme than before."
        elif current_state in {"strengthened", "increasing_priority"}:
            conviction = "strengthened"
            summary = "Management is emphasizing the theme more clearly or more persistently."
        elif current_state in {"revised"}:
            conviction = "unchanged"
            summary = "Management reframed the theme, so the narrative changed rather than simply intensified."
        elif current_state in {"newly_introduced"}:
            conviction = "unchanged"
            summary = "The theme has newly appeared in management commentary."
        elif current_state in {"stable_priority"}:
            conviction = "unchanged"
            summary = "Management keeps returning to the same theme without a major change in emphasis."
        else:
            conviction = "unclear"
            summary = "There is not enough commentary history to judge the theme confidently."
        why = "The latest commentary updated the language, priority, or specificity around this theme."
        if turning_points:
            why = f"The latest turning point is {turning_points[-1].get('change_type') or 'an evidence update'}."
        return {
            "what_changed": summary,
            "why_it_changed": why,
            "conviction_impact": conviction,
            "current_state": current_state,
            "latest_evidence": [str(event.get("title") or event.get("description") or "") for event in events[-3:]],
            "unresolved_items": list(timeline.get("unresolved_questions") or []),
        }


def build_timeline(theme: Dict[str, Any], events: List[Dict[str, Any]], unresolved_questions: List[str] | None = None) -> Dict[str, Any]:
    adapter = ManagementCommentaryProgressionAdapter()
    payload = build_progression_timeline(
        theme["theme_id"],
        "management_commentary",
        list(events),
        adapter,
        unresolved_questions=list(unresolved_questions or []),
        coverage_status=theme.get("evidence_status") or "supported",
    )
    payload["theme_id"] = theme["theme_id"]
    payload["theme_name"] = theme.get("theme_name")
    payload["normalized_theme"] = theme.get("normalized_theme")
    payload["theme_category"] = theme.get("theme_category")
    payload["source_references"] = list(theme.get("source_references") or [])
    return payload
