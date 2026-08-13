from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from intelligence.progression import build_confidence, build_progression_timeline, event_deduplication_key

from .contracts import ALLOCATION_CURRENT_STATUSES


_STATUS_ORDER = {
    "unable_to_verify": -1,
    "announced": 0,
    "in_progress": 1,
    "partially_deployed": 2,
    "deployed": 3,
    "delayed": 4,
    "superseded": 5,
    "abandoned": 6,
}


def _normalize_text(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _status_from_text(text: str) -> str:
    normalized = _normalize_text(text)
    if any(term in normalized for term in ("abandoned", "abandon", "cancelled", "canceled", "dropped")):
        return "abandoned"
    if any(term in normalized for term in ("superseded", "replaced", "shifted", "reframed")):
        return "superseded"
    if any(term in normalized for term in ("delayed", "delay", "slipped", "postponed", "deferred", "behind schedule")):
        return "delayed"
    if any(term in normalized for term in ("commissioned", "operational", "executed", "deployed", "completed", "paid", "repaid", "issued")):
        return "deployed"
    if any(term in normalized for term in ("progress", "ongoing", "in progress", "underway", "ramping", "partial", "partially")):
        return "partially_deployed"
    if any(term in normalized for term in ("planned", "expected", "expect", "announce", "announced", "intend", "target", "will")):
        return "announced"
    return "unable_to_verify"


def _event_type_from_status(status: str, index: int) -> str:
    if status == "delayed":
        return "delay_signal"
    if status == "abandoned":
        return "abandonment"
    if status == "superseded":
        return "superseded"
    if status == "deployed":
        return "confirmation" if index > 0 else "announcement"
    if status == "partially_deployed":
        return "progress"
    if index == 0:
        return "announcement"
    return "latest_assessment"


def build_capital_allocation_event(candidate: Dict[str, Any], sequence: int) -> Dict[str, Any]:
    title = candidate.get("allocation_name") or candidate.get("normalized_name") or "Capital allocation update"
    status_text = " ".join(
        part
        for part in (
            candidate.get("current_status"),
            candidate.get("outcome_status"),
            candidate.get("stated_rationale"),
            candidate.get("inferred_business_purpose"),
            candidate.get("ledger_investor_interpretation"),
        )
        if part
    )
    derived_status = candidate.get("current_status") or _status_from_text(status_text)
    event_type = candidate.get("event_type") or _event_type_from_status(derived_status, sequence - 1)
    description = candidate.get("event_summary") or candidate.get("stated_rationale") or candidate.get("inferred_business_purpose") or title
    if candidate.get("ledger_investor_interpretation"):
        description = f"{description}. {candidate['ledger_investor_interpretation']}"
    return {
        "event_id": f"{candidate['allocation_id']}-E{sequence:03d}",
        "stream_type": "capital_allocation_outcomes",
        "subject_id": candidate["allocation_id"],
        "period": candidate["source_year"],
        "sequence": sequence,
        "event_type": event_type,
        "title": title,
        "description": description,
        "evidence_status": candidate.get("evidence_status") or "supported",
        "confidence": candidate.get("confidence") or build_confidence("medium", basis=["capital allocation source record"], limitations=[]),
        "source_references": [candidate["source_reference"]],
        "metadata": {
            "allocation_category": candidate.get("allocation_category"),
            "normalized_name": candidate.get("normalized_name"),
            "funding_source": candidate.get("funding_source"),
            "amount": candidate.get("amount"),
            "amount_basis": candidate.get("amount_basis"),
            "current_status": derived_status,
            "outcome_status": candidate.get("outcome_status") or "not_yet_observable",
            "stated_rationale": candidate.get("stated_rationale"),
            "inferred_business_purpose": candidate.get("inferred_business_purpose"),
            "what_changed": candidate.get("what_changed"),
            "why_it_changed": candidate.get("why_it_changed"),
            "conviction_impact": candidate.get("conviction_impact"),
            "investor_implication": candidate.get("investor_implication"),
            "ledger_event_type": candidate.get("ledger_event_type"),
            "source_item_id": candidate.get("source_item_id"),
            "source_page": candidate.get("source_page"),
        },
    }


class CapitalAllocationOutcomesProgressionAdapter:
    stream_type = "capital_allocation_outcomes"

    def normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(event)
        normalized["stream_type"] = self.stream_type
        normalized["subject_id"] = str(normalized.get("subject_id") or "").strip()
        normalized["period"] = str(normalized.get("period") or "").strip().lower()
        normalized["sequence"] = int(normalized.get("sequence") or 0)
        normalized["event_type"] = str(normalized.get("event_type") or "latest_assessment").strip()
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
        accepted = bool(next_state)
        reason = ""
        event_type = str(event.get("event_type") or "latest_assessment")
        if not accepted:
            reason = "No derived allocation state was produced."
        elif previous_state == next_state and event_type in {"latest_assessment", "progress"}:
            accepted = False
            reason = "This update did not change the derived state."
        return {
            "accepted": accepted,
            "transition_type": event_type,
            "reason": reason,
            "confidence": build_confidence("high" if accepted else "medium", basis=["deterministic capital allocation progression"], limitations=[reason] if reason else []),
        }

    def derive_current_state(self, events: List[Dict[str, Any]]) -> Any:
        if not events:
            return "unable_to_verify"
        latest = events[-1]
        state = str((latest.get("metadata") or {}).get("current_status") or "unable_to_verify")
        if state not in ALLOCATION_CURRENT_STATUSES:
            state = _status_from_text(" ".join([latest.get("title") or "", latest.get("description") or ""]))
        return state

    def build_investor_implication(self, timeline: Dict[str, Any]) -> Dict[str, Any]:
        current_state = str(timeline.get("current_state") or "unable_to_verify")
        events = timeline.get("events") or []
        turning_points = timeline.get("turning_points") or []
        latest_metadata = (events[-1].get("metadata") or {}) if events else {}
        outcome_status = str(latest_metadata.get("outcome_status") or "not_yet_observable")
        if current_state in {"delayed", "abandoned", "superseded"} or outcome_status == "negative_outcome":
            conviction = "weakened"
            summary = "The allocation is not translating into a clean payoff yet, so conviction should soften."
        elif current_state == "deployed" and outcome_status in {"clearly_observed", "partially_observed", "early_evidence"}:
            conviction = "strengthened"
            summary = "The allocation has moved into visible execution and some downstream evidence is emerging."
        elif current_state in {"partially_deployed", "in_progress"}:
            conviction = "unchanged"
            summary = "The allocation is still in motion, but later evidence is not yet decisive."
        elif current_state == "announced":
            conviction = "unchanged"
            summary = "The allocation is visible, but the later result is still too early to judge."
        else:
            conviction = "unclear"
            summary = "There is not enough later evidence to judge this allocation confidently."
        why = "The latest evidence update changed the view on execution, use, or payoff."
        if turning_points:
            why = f"The latest turning point is {turning_points[-1].get('change_type') or 'a progression update'}."
        return {
            "what_changed": summary,
            "why_it_changed": why,
            "conviction_impact": conviction,
            "current_state": current_state,
            "latest_evidence": [str(event.get("title") or event.get("description") or "") for event in events[-3:]],
            "unresolved_items": list(timeline.get("unresolved_questions") or []),
        }


def build_timeline(allocation: Dict[str, Any], events: Sequence[Dict[str, Any]], unresolved_questions: Sequence[str] | None = None) -> Dict[str, Any]:
    adapter = CapitalAllocationOutcomesProgressionAdapter()
    payload = build_progression_timeline(
        allocation["allocation_id"],
        "capital_allocation_outcomes",
        list(events),
        adapter,
        unresolved_questions=list(unresolved_questions or []),
        coverage_status=allocation.get("evidence_status") or "supported",
    )
    payload["allocation_id"] = allocation["allocation_id"]
    payload["allocation_name"] = allocation.get("allocation_name")
    payload["allocation_category"] = allocation.get("allocation_category")
    payload["normalized_name"] = allocation.get("normalized_name")
    payload["deployment_periods"] = list(allocation.get("deployment_periods") or [])
    payload["source_references"] = list(allocation.get("source_references") or [])
    payload["current_status"] = allocation.get("current_status")
    payload["outcome_status"] = allocation.get("outcome_status")
    return payload

