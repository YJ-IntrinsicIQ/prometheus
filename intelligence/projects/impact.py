from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence


BUSINESS_EFFECT_TERMS = (
    "utilization",
    "customer win",
    "customer wins",
    "delivery",
    "faster delivery",
    "outsourcing",
    "throughput",
    "capacity",
    "order flow",
    "export",
)

FINANCIAL_EFFECT_TERMS = (
    "revenue",
    "margin",
    "profit",
    "cash flow",
    "working capital",
    "return on capital",
    "cost",
    "impairment",
    "overrun",
)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def assess_project_impact(project: Dict[str, Any], timeline: Dict[str, Any]) -> Dict[str, Any]:
    events = timeline.get("events") or []
    current_state = str(timeline.get("current_state") or project.get("current_status") or "unable_to_verify")
    evidence_periods: List[str] = []
    business_hits: List[str] = []
    financial_hits: List[str] = []
    negative_hits: List[str] = []
    commissioning_only = True

    for event in events:
        haystack = " ".join(
            [
                _normalize_text(event.get("title")),
                _normalize_text(event.get("description")),
                _normalize_text((event.get("metadata") or {}).get("status_text")),
            ]
        ).lower()
        if event.get("event_type") in {"completion", "capacity_ramp", "utilization_update", "economic_impact_update", "confirmation"}:
            commissioning_only = False
            evidence_periods.append(str(event.get("period") or ""))
        if any(term in haystack for term in BUSINESS_EFFECT_TERMS):
            business_hits.append(haystack)
            evidence_periods.append(str(event.get("period") or ""))
        if any(term in haystack for term in FINANCIAL_EFFECT_TERMS):
            financial_hits.append(haystack)
            evidence_periods.append(str(event.get("period") or ""))
        if any(term in haystack for term in ("loss", "impairment", "overrun", "delayed commercialization", "below plan", "weak utilisation", "weak utilization")):
            negative_hits.append(haystack)
            evidence_periods.append(str(event.get("period") or ""))
        if event.get("event_type") in {"confirmation"}:
            evidence_periods.append(str(event.get("period") or ""))

    evidence_periods = [period for period in evidence_periods if period]
    unique_periods = []
    for period in evidence_periods:
        if period not in unique_periods:
            unique_periods.append(period)

    if negative_hits:
        status = "negative_outcome"
        observed_business_effect = "There is negative evidence around delivery or execution."
        observed_financial_effect = "The evidence points to a weaker or adverse economic outcome."
        confidence = "medium" if len(negative_hits) == 1 else "high"
    elif current_state in {"operational", "commissioned"} and (business_hits or financial_hits):
        if financial_hits and business_hits:
            status = "partially_observed"
        elif financial_hits:
            status = "early_evidence"
        else:
            status = "partially_observed"
        observed_business_effect = "There is some post-execution evidence of business use or utilisation."
        if financial_hits:
            observed_financial_effect = "There is some financial evidence after execution, but the available evidence does not establish causality."
        else:
            observed_financial_effect = "No direct financial effect is yet established."
        confidence = "medium"
    elif current_state in {"operational", "commissioned"}:
        status = "early_evidence"
        observed_business_effect = "The project is operating or commissioned, but downstream use is still thin."
        observed_financial_effect = "There is not yet enough evidence to connect the project to a financial effect."
        confidence = "low"
    elif current_state in {"under_execution", "funded", "planning", "announced", "partially_operational"}:
        status = "not_yet_observable"
        observed_business_effect = "The project is still early, so downstream business effect is not yet visible."
        observed_financial_effect = "There is not enough evidence to judge financial effect yet."
        confidence = "low"
    else:
        status = "unclear"
        observed_business_effect = "The available evidence is too thin or conflicting to judge business effect."
        observed_financial_effect = "The available evidence is too thin or conflicting to judge financial effect."
        confidence = "low"

    if financial_hits and "direct link" not in observed_financial_effect.lower():
        observed_financial_effect = f"{observed_financial_effect} The available evidence does not establish a direct link."
    if current_state == "commissioned" and not business_hits and not financial_hits:
        observed_business_effect = "Commissioning is visible, but utilization or financial effect is not yet proven."

    unresolved = []
    if status in {"not_yet_observable", "unclear"}:
        unresolved.append("Later evidence is still too thin to judge execution or economic effect with confidence.")
    if current_state in {"commissioned", "operational"} and not financial_hits:
        unresolved.append("The project has execution evidence, but economic impact remains unproven.")

    return {
        "period": unique_periods[0] if unique_periods else (timeline.get("announcement_period") or project.get("announcement_period") or ""),
        "latest_period": unique_periods[-1] if unique_periods else (timeline.get("latest_period") or project.get("latest_period") or project.get("announcement_period") or ""),
        "execution_status": current_state,
        "execution_summary": _execution_summary(current_state, events),
        "economic_impact_status": status,
        "observed_business_effect": observed_business_effect,
        "observed_financial_effect": observed_financial_effect,
        "evidence_periods": unique_periods,
        "confidence": {
            "level": confidence,
            "basis": ["execution state", "impact keywords" if business_hits or financial_hits else "absence of impact evidence"],
            "limitations": unresolved[:],
        },
        "unresolved_questions": unresolved,
    }


def _execution_summary(current_state: str, events: Sequence[Dict[str, Any]]) -> str:
    if not events:
        return "No project events were available."
    if current_state in {"commissioned", "operational"}:
        return "The project has moved beyond construction into delivery or operation."
    if current_state in {"delayed", "paused"}:
        return "The project is still real, but delivery has slowed or paused."
    if current_state in {"cancelled", "superseded"}:
        return "The project no longer appears to be on its original path."
    if current_state in {"partially_operational"}:
        return "The project has some delivery evidence, but full operation is not yet explicit."
    if current_state in {"under_execution", "funded", "planning", "announced"}:
        return "The project is still moving through execution or planning."
    if events:
        latest = events[-1]
        status_text = _normalize_text((latest.get("metadata") or {}).get("status_text"))
        title = _normalize_text(latest.get("title"))
        description = _normalize_text(latest.get("description"))
        anchor = status_text or title or description or "the announced project"
        return f"The project is visible in the source record, but later delivery evidence for {anchor} remains too thin to confirm execution."
    return "The available evidence does not support a confident execution summary."
