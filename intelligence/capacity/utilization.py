from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from .classifier import _compact_lower, _normalize_text, _tokens


UTILIZATION_HINTS = (
    "utilized",
    "utilised",
    "utilization",
    "utilisation",
    "occupancy",
    "operating at",
    "running at",
    "output",
    "capacity use",
    "at capacity",
)

RAMP_HINTS = (
    "ramping",
    "ramp up",
    "ramp-up",
    "trial",
    "pilot",
    "initial use",
    "phase 1",
)

UNDERUTILIZED_HINTS = (
    "underutilized",
    "under-utilized",
    "underutilised",
    "idle",
    "unused",
    "low utilization",
    "weak utilization",
    "weak utilisation",
)

FULL_HINTS = (
    "fully utilized",
    "fully utilised",
    "at full capacity",
    "100%",
)

FINANCIAL_DEPLOYMENT_HINTS = (
    "funds",
    "funded",
    "funding",
    "proceeds",
    "ipo objects",
    "qip objects",
    "allocated",
    "allocation",
    "unutilised",
    "unutilized",
)

CAPACITY_OPERATING_HINTS = (
    "operating at",
    "running at",
    "output",
    "throughput",
    "occupancy",
    "capacity use",
    "at capacity",
    "production",
    "commercial operations",
    "commercial production",
)

PERCENT_RE = re.compile(r"(?P<rate>\d+(?:\.\d+)?)\s*%")
RATIO_RE = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?:out of|/)\s*(?P<den>\d+(?:\.\d+)?)", re.IGNORECASE)


def _event_text(event: Dict[str, Any]) -> str:
    metadata = event.get("metadata") or {}
    return " ".join(
        [
            _normalize_text(event.get("title")),
            _normalize_text(event.get("description")),
            _normalize_text(metadata.get("status_text")),
            _normalize_text(metadata.get("utilization_status")),
        ]
    ).lower()


def _status_from_rate(rate: float) -> str:
    if rate >= 0.95:
        return "fully_utilized"
    if rate >= 0.75:
        return "high"
    if rate >= 0.4:
        return "moderate"
    return "low"


def _extract_rate(texts: Iterable[str]) -> Tuple[float | None, str, str]:
    joined = " ".join(texts)
    ratio_match = RATIO_RE.search(joined)
    if ratio_match:
        numerator = float(ratio_match.group("num"))
        denominator = float(ratio_match.group("den"))
        if denominator:
            return round(numerator / denominator, 4), ratio_match.group(0), f"{numerator:g}/{denominator:g}"
    percent_match = PERCENT_RE.search(joined)
    if percent_match:
        return round(float(percent_match.group("rate")) / 100.0, 4), percent_match.group(0), percent_match.group(0)
    return None, "", ""


def _looks_like_financial_deployment(joined: str) -> bool:
    return any(term in joined for term in FINANCIAL_DEPLOYMENT_HINTS) and not any(term in joined for term in CAPACITY_OPERATING_HINTS)


def assess_utilization(capacity: Dict[str, Any], timeline: Dict[str, Any], related_assessments: Iterable[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    events = timeline.get("events") or []
    current_state = str(timeline.get("current_state") or capacity.get("current_status") or "unable_to_verify")
    event_text = " ".join(_event_text(event) for event in events)
    capacity_text = " ".join(
        [
            _compact_lower(capacity.get("capacity_name")),
            _compact_lower(capacity.get("normalized_name")),
            _compact_lower(capacity.get("purpose")),
            _compact_lower(capacity.get("planned_capacity")),
            _compact_lower(capacity.get("installed_capacity")),
            _compact_lower(capacity.get("operational_capacity")),
            _compact_lower(capacity.get("utilized_capacity")),
            _compact_lower(capacity.get("capital_deployed")),
            _compact_lower(capacity.get("expected_timeframe")),
        ]
    )
    joined = " ".join([event_text, capacity_text])
    financial_deployment = _looks_like_financial_deployment(joined)

    rate, rate_basis, ratio_basis = _extract_rate(
        [
            _normalize_text(capacity.get("utilization_rate")),
            _normalize_text(capacity.get("utilized_capacity")),
            _normalize_text(capacity.get("operational_capacity")),
            _normalize_text(capacity.get("capital_deployed")),
            event_text,
            capacity_text,
        ]
    )

    if financial_deployment:
        utilization_status = "pre_operational" if current_state in {"planned", "announced", "funded"} else "not_disclosed"
        implied_utilization = "The evidence shows funds were deployed, but not that operating capacity is in use."
    elif any(term in joined for term in FULL_HINTS):
        utilization_status = "fully_utilized"
        implied_utilization = "The disclosed evidence suggests the capacity is fully used."
    elif any(term in joined for term in UNDERUTILIZED_HINTS):
        utilization_status = "low"
        implied_utilization = "The disclosed evidence suggests the capacity is underused."
    elif rate is not None:
        utilization_status = _status_from_rate(rate)
        implied_utilization = f"The disclosed rate is about {rate:.0%}."
    elif any(term in joined for term in RAMP_HINTS):
        utilization_status = "ramping"
        implied_utilization = "The capacity is moving through ramp-up use."
    elif any(term in joined for term in UTILIZATION_HINTS):
        utilization_status = "unclear" if current_state in {"installed", "commissioned"} else "not_disclosed"
        implied_utilization = "Utilization is mentioned, but the denominator or operating level is not explicit."
    elif current_state in {"installed", "commissioned"}:
        utilization_status = "pre_operational" if current_state == "installed" else "not_disclosed"
        implied_utilization = "The capacity is not yet shown to be in use."
    else:
        utilization_status = "pre_operational"
        implied_utilization = "The capacity is still early or there is no explicit utilization disclosure."

    disclosed_output = _normalize_text(
        capacity.get("utilized_capacity")
        or capacity.get("operational_capacity")
        or capacity.get("installed_capacity")
        or capacity.get("planned_capacity")
    )
    basis = [
        text
        for text in [
            capacity.get("original_status_text"),
            capacity.get("expected_timeframe"),
            capacity.get("capital_deployed"),
            disclosed_output,
            rate_basis,
        ]
        if _normalize_text(text)
    ]
    limitations: List[str] = []
    if not rate_basis and utilization_status in {"not_disclosed", "unclear", "pre_operational"}:
        limitations.append("No explicit numerator, denominator, or operating denominator was disclosed.")
    if not capacity.get("unit") and not ratio_basis:
        limitations.append("Unit is unclear, so a precise utilization rate was not calculated.")

    confidence_level = "high" if rate is not None or utilization_status in {"fully_utilized", "high"} else "medium" if utilization_status in {"moderate", "low", "ramping"} else "low"
    return {
        "utilization_status": utilization_status,
        "disclosed_rate": rate,
        "disclosed_output": disclosed_output,
        "implied_utilization": implied_utilization,
        "evidence_period": timeline.get("latest_period") or capacity.get("latest_period") or capacity.get("announcement_period"),
        "basis": basis,
        "limitations": limitations,
        "confidence": {
            "level": confidence_level,
            "basis": basis[:4],
            "limitations": limitations,
        },
        "numerator": ratio_basis.split("/", 1)[0] if ratio_basis and "/" in ratio_basis else "",
        "denominator": ratio_basis.split("/", 1)[1] if ratio_basis and "/" in ratio_basis else "",
        "unit": capacity.get("unit") or ("%" if rate is not None and "%" in rate_basis else ""),
    }
