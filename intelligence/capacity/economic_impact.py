from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .classifier import _compact_lower, _normalize_text


BUSINESS_EFFECT_TERMS = (
    "higher production",
    "reduced outsourcing",
    "shorter lead time",
    "lead time",
    "customer win",
    "customer wins",
    "delivery",
    "throughput",
    "export",
    "order flow",
    "output",
    "utilization",
)

FINANCIAL_EFFECT_TERMS = (
    "revenue",
    "margin",
    "profit",
    "cash flow",
    "return on capital",
    "margin improvement",
    "cost saving",
    "lower cost",
    "impairment",
    "overrun",
)

NEGATIVE_TERMS = (
    "idle",
    "underutilized",
    "underutilised",
    "delay",
    "delayed",
    "slipped",
    "cost overrun",
    "impairment",
    "shutdown",
)


def _related_assessment_text(assessment: Dict[str, Any]) -> str:
    return " ".join(
        [
            _normalize_text(assessment.get("observed_business_effect")),
            _normalize_text(assessment.get("observed_financial_effect")),
            _normalize_text(assessment.get("economic_impact_status")),
        ]
    ).lower()


def assess_capacity_impact(
    capacity: Dict[str, Any],
    timeline: Dict[str, Any],
    utilization: Dict[str, Any],
    related_project_assessments: Iterable[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    events = timeline.get("events") or []
    current_state = str(timeline.get("current_state") or capacity.get("current_status") or "unable_to_verify")
    evidence_periods: List[str] = []
    business_hits: List[str] = []
    financial_hits: List[str] = []
    negative_hits: List[str] = []

    text = " ".join(
        [
            _compact_lower(capacity.get("capacity_name")),
            _compact_lower(capacity.get("purpose")),
            _compact_lower(capacity.get("economic_relevance")),
            _compact_lower(capacity.get("investor_implication")),
            _compact_lower(utilization.get("implied_utilization")),
            _compact_lower(utilization.get("disclosed_output")),
            _compact_lower(utilization.get("disclosed_rate")),
        ]
    )

    for event in events:
        event_text = " ".join(
            [
                _normalize_text(event.get("title")),
                _normalize_text(event.get("description")),
                _normalize_text((event.get("metadata") or {}).get("status_text")),
            ]
        ).lower()
        if event.get("event_type") in {"output_update", "utilization_update", "economic_impact_update", "operations_started"}:
            evidence_periods.append(str(event.get("period") or ""))
        if any(term in event_text for term in BUSINESS_EFFECT_TERMS):
            business_hits.append(event_text)
            evidence_periods.append(str(event.get("period") or ""))
        if any(term in event_text for term in FINANCIAL_EFFECT_TERMS):
            financial_hits.append(event_text)
            evidence_periods.append(str(event.get("period") or ""))
        if any(term in event_text for term in NEGATIVE_TERMS):
            negative_hits.append(event_text)
            evidence_periods.append(str(event.get("period") or ""))

    for assessment in related_project_assessments or []:
        related_text = _related_assessment_text(assessment)
        if not related_text:
            continue
        if str(assessment.get("economic_impact_status") or "") in {"negative_outcome"}:
            negative_hits.append(related_text)
        if any(term in related_text for term in BUSINESS_EFFECT_TERMS):
            business_hits.append(related_text)
        if any(term in related_text for term in FINANCIAL_EFFECT_TERMS):
            financial_hits.append(related_text)
        for period in assessment.get("evidence_periods") or []:
            evidence_periods.append(str(period))

    unique_periods: List[str] = []
    for period in evidence_periods:
        if period and period not in unique_periods:
            unique_periods.append(period)

    if negative_hits:
        status = "negative_outcome"
        observed_business_effect = "The evidence points to weak or adverse execution use."
        observed_financial_effect = "The available evidence points to a weaker or adverse economic outcome."
        confidence = "medium" if len(negative_hits) == 1 else "high"
    elif financial_hits and business_hits:
        status = "clearly_observed" if utilization.get("utilization_status") in {"high", "fully_utilized"} else "partially_observed"
        observed_business_effect = "There is explicit downstream business-use evidence, though causality is still cautious."
        observed_financial_effect = "There is explicit financial evidence, but the contribution of the capacity is not isolated."
        confidence = "medium"
    elif business_hits or financial_hits:
        status = "early_evidence"
        observed_business_effect = "There is some downstream evidence, but it is still thin."
        observed_financial_effect = "There is some financial evidence, but it does not isolate the capacity's contribution."
        confidence = "medium"
    elif current_state in {"operational", "commissioned"} and utilization.get("utilization_status") in {"high", "fully_utilized", "moderate", "low", "ramping"}:
        status = "early_evidence"
        observed_business_effect = "The capacity is in use, but a broader economic effect is not yet isolated."
        observed_financial_effect = "The available evidence does not isolate a financial effect."
        confidence = "low"
    elif current_state in {"operational", "commissioned", "ramping", "partially_utilized", "materially_utilized"}:
        status = "not_yet_observable"
        observed_business_effect = "The capacity is visible, but economic effect is not yet clear."
        observed_financial_effect = "There is not yet enough evidence to judge financial effect."
        confidence = "low"
    else:
        status = "unclear"
        observed_business_effect = "The evidence is still too thin to judge business effect."
        observed_financial_effect = "The evidence is still too thin to judge financial effect."
        confidence = "low"

    unresolved: List[str] = []
    if status in {"not_yet_observable", "unclear"}:
        unresolved.append("Downstream business and financial effects remain thin or unproven.")
    if utilization.get("utilization_status") in {"not_disclosed", "pre_operational", "unclear"}:
        unresolved.append("Operating utilization remains insufficiently disclosed.")

    if financial_hits and "direct link" not in observed_financial_effect.lower():
        observed_financial_effect = f"{observed_financial_effect} The available evidence does not establish a direct link."

    return {
        "execution_status": current_state,
        "utilization_status": utilization.get("utilization_status"),
        "observed_business_effect": observed_business_effect,
        "observed_financial_effect": observed_financial_effect,
        "economic_impact_status": status,
        "evidence_periods": unique_periods,
        "confidence": {
            "level": confidence,
            "basis": ["execution state", "utilization disclosure" if utilization.get("utilization_status") else "downstream evidence"],
            "limitations": unresolved[:],
        },
        "unresolved_questions": unresolved,
    }
