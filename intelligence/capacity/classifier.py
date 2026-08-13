from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence


VAGUE_PHRASES = (
    "we are scaling",
    "we expect strong growth",
    "we expect to grow",
    "we will continue to grow",
    "continue to grow",
    "focus on innovation",
    "strengthen our position",
    "grow for the future",
    "investing for the future",
    "building for growth",
)

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")

CAPACITY_TYPE_KEYWORDS = {
    "testing": ("testing facility", "test facility", "emi-emc", "test lab", "lab", "laboratory", "qa"),
    "assembly": ("assembly", "assemble", "assembly line"),
    "production_line": ("production line", "line", "manufacturing line", "commercial production", "factory line"),
    "workforce": ("workforce", "headcount", "recruitment", "hiring", "upskilling", "training", "engineer recruitment", "resource optimization", "manpower"),
    "manufacturing": ("manufacturing", "production", "factory", "plant", "satellite systems", "machining"),
    "infrastructure": ("facility", "infrastructure", "building", "classroom", "renovation", "site", "warehouse", "office", "land", "utilities"),
    "logistics": ("logistics", "distribution", "warehouse", "storage", "depot", "supply chain"),
    "digital": ("digital", "software", "automation", "it ", "it/", "data centre", "data center", "cloud", "platform", "system", "erp"),
    "service_delivery": ("service delivery", "delivery centre", "delivery center", "service centre", "service center", "support centre", "support center", "call centre", "call center"),
    "geographic": ("geographic", "market entry", "expand into", "export", "overseas", "international", "region", "country"),
}

VAGUE_CAPACITY_TERMS = (
    "scale up",
    "scaling",
    "grow the business",
    "grow capacity",
    "strong growth",
    "future growth",
    "invest for future",
)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _compact_lower(value: Any) -> str:
    return _normalize_text(value).lower()


def _tokens(value: Any) -> List[str]:
    return [
        token
        for token in _NORMALIZE_RE.sub(" ", _compact_lower(value)).split()
        if token
    ]


def _token_overlap(left: Sequence[str], right: Sequence[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / max(len(left_set), len(right_set))


def _has_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def sanitize_public_text(value: Any) -> str:
    text = _normalize_text(value)
    return text.replace("pipeline", "program").replace("Pipeline", "Program")


def normalize_location(item: Dict[str, Any]) -> str:
    for field in ("location", "site", "plant_location", "address", "geography"):
        value = _normalize_text(item.get(field))
        if value:
            return sanitize_public_text(value)
    return ""


def is_vague_capacity_text(*texts: Any) -> bool:
    normalized = " ".join(_compact_lower(text) for text in texts if text not in (None, "", [], {}))
    return any(phrase in normalized for phrase in VAGUE_PHRASES) or any(term in normalized for term in VAGUE_CAPACITY_TERMS)


def classify_capacity_type(name: str, description: str, location: str, status: str, source_kind: str) -> str:
    normalized = " ".join([_compact_lower(name), _compact_lower(description), _compact_lower(location), _compact_lower(status), source_kind])
    for capacity_type, keywords in CAPACITY_TYPE_KEYWORDS.items():
        if _has_any(normalized, keywords):
            return capacity_type
    if any(term in normalized for term in ("capacity", "throughput", "utilization", "utilisation", "expand", "expansion", "ramp", "output")):
        return "manufacturing"
    return "other"


def classify_capacity_family(name: str, description: str, location: str, status: str, source_kind: str, capacity_type: str) -> str:
    normalized = " ".join([_compact_lower(name), _compact_lower(description), _compact_lower(location), _compact_lower(status), source_kind, _compact_lower(capacity_type)])
    if _has_any(normalized, CAPACITY_TYPE_KEYWORDS["workforce"]):
        return "workforce"
    if _has_any(normalized, CAPACITY_TYPE_KEYWORDS["digital"]):
        return "digital"
    if _has_any(normalized, CAPACITY_TYPE_KEYWORDS["service_delivery"]):
        return "service_delivery"
    if _has_any(normalized, CAPACITY_TYPE_KEYWORDS["geographic"]):
        return "geographic"
    if _has_any(normalized, CAPACITY_TYPE_KEYWORDS["testing"]):
        return "physical_testing"
    if _has_any(normalized, CAPACITY_TYPE_KEYWORDS["assembly"]) or _has_any(normalized, CAPACITY_TYPE_KEYWORDS["production_line"]) or _has_any(normalized, CAPACITY_TYPE_KEYWORDS["manufacturing"]) or _has_any(normalized, CAPACITY_TYPE_KEYWORDS["infrastructure"]) or _has_any(normalized, CAPACITY_TYPE_KEYWORDS["logistics"]):
        return "physical"
    return "other"


def build_capacity_name(name: str, description: str, capacity_type: str) -> str:
    candidate = sanitize_public_text(name or description or "Capacity")
    candidate = candidate.strip(" .:-")
    if not candidate:
        candidate = "Capacity"
    if capacity_type == "production_line" and "line" not in candidate.lower():
        candidate = f"{candidate} line"
    return candidate


def build_purpose(name: str, description: str, capacity_type: str, location: str, expected_output: str) -> str:
    text = sanitize_public_text(description or name)
    if not text:
        if capacity_type in {"manufacturing", "production_line"}:
            text = "Expand productive output"
        elif capacity_type == "testing":
            text = "Support testing capability"
        elif capacity_type == "workforce":
            text = "Increase available operating capability"
        else:
            text = "Support a bounded productive capability"
    if location and location.lower() not in text.lower():
        text = f"{text} at {location}"
    if expected_output and expected_output.lower() not in text.lower():
        text = f"{text}; expected output: {expected_output}"
    return text.rstrip(".")


def build_capacity_economic_relevance(capacity_type: str, purpose: str, location: str) -> str:
    if capacity_type in {"manufacturing", "production_line", "assembly"}:
        base = "It can improve supply capacity and operating flexibility"
    elif capacity_type == "testing":
        base = "It can improve quality control and validation throughput"
    elif capacity_type == "workforce":
        base = "It can increase execution capacity through more capability"
    elif capacity_type == "digital":
        base = "It can improve operating speed, control, or decision quality"
    elif capacity_type == "logistics":
        base = "It can improve delivery, storage, or distribution capability"
    elif capacity_type == "geographic":
        base = "It can extend the company into a new market or geography"
    else:
        base = "It can affect execution capacity and business mix"
    if purpose:
        base = f"{base}; purpose: {purpose}"
    if location:
        base = f"{base} at {location}"
    return base.rstrip(".")


def build_unit(item: Dict[str, Any], planned_capacity: str, installed_capacity: str, operational_capacity: str, utilized_capacity: str, capital_deployed: str) -> str:
    text = " ".join(
        [
            _compact_lower(item.get("current_capacity")),
            _compact_lower(item.get("target_capacity")),
            _compact_lower(planned_capacity),
            _compact_lower(installed_capacity),
            _compact_lower(operational_capacity),
            _compact_lower(utilized_capacity),
            _compact_lower(capital_deployed),
        ]
    )
    if "crore" in text or "lakh" in text or "rs." in text or "inr" in text or "rupee" in text:
        return "INR crore"
    if "%" in text or "percent" in text or "percentage" in text:
        return "%"
    for unit in ("mw", "mwh", "units/day", "units", "tonnes", "tons", "seats", "beds", "classrooms", "machines", "sq ft", "sq m"):
        if unit in text:
            return unit
    return ""


def capacity_similarity(left: Dict[str, Any], right: Dict[str, Any]) -> int:
    score = 0
    left_name = _compact_lower(left.get("normalized_name") or left.get("capacity_name"))
    right_name = _compact_lower(right.get("normalized_name") or right.get("capacity_name"))
    left_tokens = _tokens(left_name)
    right_tokens = _tokens(right_name)
    overlap = _token_overlap(left_tokens, right_tokens)
    if left_name and right_name:
        if left_name == right_name or left_name in right_name or right_name in left_name:
            score += 4
        elif overlap >= 0.75:
            score += 3
        elif overlap >= 0.5:
            score += 2

    if _compact_lower(left.get("capacity_type")) == _compact_lower(right.get("capacity_type")):
        score += 2

    left_location = _compact_lower(left.get("location"))
    right_location = _compact_lower(right.get("location"))
    if left_location and right_location:
        if left_location == right_location or left_location in right_location or right_location in left_location:
            score += 2
        elif _token_overlap(_tokens(left_location), _tokens(right_location)) >= 0.6:
            score += 1

    left_projects = set(left.get("linked_project_ids") or [])
    right_projects = set(right.get("linked_project_ids") or [])
    if left_projects & right_projects:
        score += 3

    left_commitments = set(left.get("linked_commitment_ids") or [])
    right_commitments = set(right.get("linked_commitment_ids") or [])
    if left_commitments & right_commitments:
        score += 2

    if _compact_lower(left.get("announcement_period")) == _compact_lower(right.get("announcement_period")):
        score += 1

    left_purpose = _compact_lower(left.get("purpose"))
    right_purpose = _compact_lower(right.get("purpose"))
    if left_purpose and right_purpose:
        if left_purpose in right_purpose or right_purpose in left_purpose:
            score += 1
        elif _token_overlap(_tokens(left_purpose), _tokens(right_purpose)) >= 0.6:
            score += 1

    return score


def has_bounded_capacity_signals(item: Dict[str, Any], *, source_kind: str) -> bool:
    name = _normalize_text(item.get("capacity_type") or item.get("value") or item.get("project_name"))
    description = _normalize_text(item.get("status") or item.get("timeline") or item.get("description") or item.get("benefit"))
    location = normalize_location(item)
    status_text = _normalize_text(item.get("status"))
    if not name:
        return False
    text = " ".join([name, description, location, status_text]).lower()
    if _has_any(text, ("school", "classroom", "student capacity", "csr", "community", "pond", "stormwater")):
        return False
    if _has_any(text, ("process excellence", "resource optimization", "targeted upskilling", "training program", "ability to scale", "scalable capacity")) and not any(
        item.get(field) for field in ("target_capacity", "current_capacity", "installed_capacity", "operational_capacity", "amount")
    ):
        return False
    productive_signal = _has_any(text, ("capacity", "manufacturing", "production", "testing", "integration", "assembly", "service delivery", "ems line", "facility", "plant", "equipment", "throughput", "headcount"))
    execution_signal = _has_any(text, ("new", "expand", "expansion", "install", "commission", "operational", "operating", "production", "planned", "funded", "construction", "upgrade", "delayed"))
    quantified_signal = any(item.get(field) for field in ("target_capacity", "current_capacity", "installed_capacity", "operational_capacity", "amount"))
    abstract_or_aspirational = _has_any(text, (
        "capacity utilization increase to support", "capture complete value chain",
        "design and systems integration capacity", "deeper collaborations",
    ))
    observable_execution = _has_any(text, ("new facility", "expansion", "installed", "commissioned", "under construction", "funded", "acquisition", "upgrade"))
    if abstract_or_aspirational and not quantified_signal and not observable_execution:
        return False
    if not productive_signal or not (execution_signal or quantified_signal):
        return False
    if is_vague_capacity_text(name, description, location) and not _has_any(
        text,
        (
            "facility",
            "plant",
            "capacity",
            "production",
            "testing",
            "commission",
            "install",
            "utiliz",
            "build",
            "expansion",
            "capex",
            "workforce",
        ),
    ):
        return False
    if _has_any(text, ("capital expenditure", "capex")) and not _has_any(
        text,
        (
            "facility",
            "plant",
            "capacity",
            "throughput",
            "production",
            "testing",
            "manufacturing",
            "commission",
            "install",
            "utiliz",
            "build",
            "expansion",
            "workforce",
            "warehouse",
            "logistics",
            "infrastructure",
        ),
    ):
        return False

    signals = 0
    if len(name.split()) >= 2:
        signals += 1
    if len(description.split()) >= 4:
        signals += 1
    if location:
        signals += 1
    if any(item.get(field) not in (None, "", [], {}) for field in ("current_capacity", "target_capacity", "timeline", "amount", "currency")):
        signals += 1
    if _has_any(text, ("capacity", "throughput", "utilization", "utilisation", "commission", "install", "construction", "funded", "operational", "planned", "ongoing", "implemented", "output", "ramp")):
        signals += 1
    if source_kind == "capacity":
        signals += 1
    return signals >= 2
