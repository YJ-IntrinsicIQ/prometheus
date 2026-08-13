from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .contracts import PROJECT_TYPES


VAGUE_PHRASES = (
    "continue to grow",
    "continue growing",
    "focused on innovation",
    "focus on innovation",
    "strengthen our position",
    "improve our position",
    "build a stronger company",
    "next phase of growth",
    "future growth",
    "growth story",
    "strategic growth",
    "business expansion",
)

CAPACITY_KEYWORDS = ("capacity", "output", "throughput", "ramp", "utilization", "plant", "facility", "hangar", "line")
FACILITY_KEYWORDS = ("facility", "plant", "hangar", "clean room", "lab", "laboratory", "workshop")
PRODUCT_KEYWORDS = ("product", "launch", "platform", "offering", "solution", "module")
TECH_KEYWORDS = ("technology", "software", "automation", "system", "implementation", "digital", "cyber", "it ", "r&d")
COMPLIANCE_KEYWORDS = ("iso", "14001", "45001", "compliance", "environmental", "ehs", "safety", "regulatory", "permit", "certification")
ENERGY_KEYWORDS = ("solar", "renewable", "rooftop", "energy efficiency", "energy-saving", "power saving")
INFRASTRUCTURE_KEYWORDS = ("infrastructure", "utilities", "support infrastructure", "supporting infrastructure")
MARKET_KEYWORDS = ("export", "market entry", "geography", "overseas", "international")
CUSTOMER_KEYWORDS = ("customer", "programme", "program", "order", "contract", "win")
ACQUISITION_KEYWORDS = ("acquisition", "acquire", "merger", "takeover", "buyout")
TRANSFORMATION_KEYWORDS = ("transformation", "maturity", "process excellence", "organization", "organisation")
CSR_KEYWORDS = ("csr", "community", "school", "classroom", "pond", "stormwater", "welfare")


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _compact_lower(value: Any) -> str:
    return _normalize_text(value).lower()


def _has_any(text: str, keywords: Sequence[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def is_vague_project_text(*texts: Any) -> bool:
    normalized = " ".join(_compact_lower(text) for text in texts if text not in (None, "", [], {}))
    return any(phrase in normalized for phrase in VAGUE_PHRASES)


def classify_project_type(source_kind: str, name: str, description: str, location: str, status: str) -> str:
    normalized = " ".join([_compact_lower(name), _compact_lower(description), _compact_lower(location), _compact_lower(status), source_kind])
    if _has_any(normalized, ACQUISITION_KEYWORDS):
        return "acquisition_integration"
    if _has_any(normalized, CSR_KEYWORDS):
        return "csr" if any(term in normalized for term in ("csr", "community", "welfare")) else "non_core"
    if _has_any(normalized, COMPLIANCE_KEYWORDS):
        if _has_any(normalized, ("environmental", "ehs", "safety", "iso 14001", "iso 45001")):
            return "environmental_compliance"
        return "regulatory_compliance"
    if _has_any(normalized, ENERGY_KEYWORDS):
        return "energy_efficiency"
    if _has_any(normalized, INFRASTRUCTURE_KEYWORDS):
        return "support_infrastructure"
    if _has_any(normalized, CUSTOMER_KEYWORDS):
        return "customer_programme"
    if _has_any(normalized, FACILITY_KEYWORDS):
        if _has_any(normalized, ("expand", "expansion", "additional", "upgrading", "upgrade", "scaling", "scale")):
            return "capacity_expansion"
        return "facility"
    if _has_any(normalized, CAPACITY_KEYWORDS):
        return "capacity_expansion"
    if _has_any(normalized, TECH_KEYWORDS):
        return "technology_implementation"
    if _has_any(normalized, MARKET_KEYWORDS):
        return "market_expansion"
    if _has_any(normalized, TRANSFORMATION_KEYWORDS):
        return "transformation"
    if _has_any(normalized, PRODUCT_KEYWORDS):
        return "product_development"
    return "other"


def normalize_project_name(name: str, description: str, project_type: str) -> str:
    candidate = _normalize_text(name)
    candidate = re.sub(r"\s+", " ", candidate)
    candidate = candidate.strip(" .:-")
    if not candidate:
        candidate = _normalize_text(description)
    if not candidate:
        candidate = "Management project"
    if project_type == "capacity_expansion" and "expansion" not in candidate.lower():
        candidate = f"{candidate} expansion"
    return candidate


def build_objective(name: str, description: str, project_type: str, *, source_kind: str = "") -> str:
    text = _normalize_text(description) or _normalize_text(name)
    if not text:
        return "Execution objective not stated."
    if project_type == "facility":
        return text if "facility" in text.lower() else f"Build or upgrade the facility described as {text}."
    if project_type == "capacity_expansion":
        return text if "capacity" in text.lower() else f"Expand execution capacity for {text}."
    if project_type == "manufacturing_line":
        return text if "line" in text.lower() else f"Install or improve a manufacturing line for {text}."
    if project_type == "product_development":
        return text if "product" in text.lower() else f"Develop the product or platform described as {text}."
    if project_type == "technology_implementation":
        return text if any(term in text.lower() for term in ("system", "software", "automation", "technology", "iso")) else f"Implement the technology or process change described as {text}."
    if project_type == "market_expansion":
        return text if "market" in text.lower() or "export" in text.lower() else f"Enter or expand into the market described as {text}."
    if project_type == "customer_programme":
        return text if "customer" in text.lower() or "order" in text.lower() else f"Execute the customer programme described as {text}."
    if project_type == "acquisition_integration":
        return text if "integration" in text.lower() else f"Integrate the acquired asset or business described as {text}."
    if project_type == "infrastructure_upgrade":
        return text if "upgrade" in text.lower() else f"Upgrade supporting infrastructure for {text}."
    if project_type == "transformation":
        return text if "transformation" in text.lower() else f"Deliver the operating transformation described as {text}."
    return text


def build_business_rationale(name: str, description: str, project_type: str, location: str, expected_output: str) -> str:
    pieces = []
    if project_type in {"facility", "capacity_expansion", "manufacturing_line"}:
        pieces.append("Support execution capacity and delivery readiness")
    elif project_type == "product_development":
        pieces.append("Extend the product set or system capability")
    elif project_type == "technology_implementation":
        pieces.append("Improve operating capability, control, or speed")
    elif project_type == "market_expansion":
        pieces.append("Reach new customers or geographies")
    elif project_type == "customer_programme":
        pieces.append("Serve a specific customer or programme")
    elif project_type == "acquisition_integration":
        pieces.append("Integrate a purchased asset or business")
    else:
        pieces.append("Advance execution on a bounded business objective")

    if location:
        pieces.append(f"at {location}")
    if expected_output:
        pieces.append(f"to deliver {expected_output}")
    return " ".join(pieces).strip().rstrip(".")


def build_expected_output_or_capacity(item: Dict[str, Any], project_type: str) -> str:
    for field in ("expected_output_or_capacity", "target_capacity", "current_capacity", "description"):
        value = _normalize_text(item.get(field))
        if value:
            return value
    if project_type == "capacity_expansion":
        return "Expanded capacity"
    if project_type == "facility":
        return "A bounded facility or plant capability"
    return ""


def build_expected_timeframe(item: Dict[str, Any], announcement_period: str) -> str:
    for field in ("expected_timeframe", "timeline", "target_period", "target_date", "period", "year"):
        value = _normalize_text(item.get(field))
        if value:
            return value
    return announcement_period


def build_expected_cost(item: Dict[str, Any]) -> str:
    for field in ("expected_cost", "amount", "capital_commitment", "cost"):
        value = _normalize_text(item.get(field))
        if value:
            return value
    return ""


def normalize_location(item: Dict[str, Any]) -> str:
    for field in ("location", "site", "plant_location", "address"):
        value = _normalize_text(item.get(field))
        if value:
            return value
    return ""


def build_economic_relevance(project_type: str, expected_output: str, location: str) -> str:
    if project_type in {"facility", "capacity_expansion", "manufacturing_line"}:
        base = "It can improve supply capacity and delivery flexibility"
    elif project_type == "technology_implementation":
        base = "It can improve operating discipline and execution quality"
    elif project_type == "product_development":
        base = "It can widen the product or programme opportunity set"
    elif project_type == "market_expansion":
        base = "It can extend the company into a new market or geography"
    elif project_type == "customer_programme":
        base = "It can support a specific customer relationship or order flow"
    elif project_type == "acquisition_integration":
        base = "It can affect integration quality and realised synergies"
    else:
        base = "It can affect execution quality and business mix"
    if expected_output:
        base = f"{base}; the intended output is {expected_output}"
    if location:
        base = f"{base} at {location}"
    return base.rstrip(".")


def count_signals(item: Dict[str, Any], name: str, description: str, location: str) -> int:
    signals = 0
    if name and len(name.split()) >= 2:
        signals += 1
    if description and len(description.split()) >= 6:
        signals += 1
    if location:
        signals += 1
    if item.get("timeline") or item.get("expected_timeframe") or item.get("year"):
        signals += 1
    if item.get("amount") or item.get("expected_cost") or item.get("capital_commitment"):
        signals += 1
    if item.get("target_capacity") or item.get("current_capacity") or _has_any(_compact_lower(description), ("capacity", "commission", "production", "install", "build", "upgrade", "implement", "launch")):
        signals += 1
    return signals


def is_bounded_project_candidate(item: Dict[str, Any], *, source_kind: str) -> bool:
    name = _normalize_text(item.get("project_name") or item.get("capacity_type") or item.get("value"))
    description = _normalize_text(item.get("description") or item.get("benefit") or item.get("status"))
    location = normalize_location(item)
    if not name:
        return False
    text = _compact_lower(" ".join((name, description, location, _normalize_text(item.get("status")))))
    if _has_any(text, ("school", "classroom", "student capacity", "csr", "community infrastructure", "pond", "stormwater")):
        return False
    if _has_any(text, ("human capital", "training program", "talent program", "intangible assets under development")):
        return False
    bounded_action = _has_any(text, ("setting up", "construction", "install", "commission", "acquisition", "expansion", "upgrade", "implementation", "development project", "funded", "capex"))
    product_like = _has_any(text, ("tester", "checkout", "test system", "flight control computer", "radar unit"))
    if "radar" in text and _has_any(text, ("unit", "commissioned", "customer", "contract")):
        return False
    if re.search(r"\bate\b", text) and not _has_any(text, ("facility", "installation", "setting up", "capex")):
        product_like = True
    if _has_any(text, ("isro-approved manufacturing facility", "manufacturing facility at", "existing manufacturing facility")) and not bounded_action:
        return False
    if _compact_lower(name) == "augmented design & development facility" and not bounded_action:
        return False
    if _compact_lower(name) in {"new facility creation", "infrastructure scaling", "completion of new infrastructure; addition to plant & machinery and computers"}:
        return False
    if product_like and not bounded_action and not item.get("amount") and not location:
        return False
    if is_vague_project_text(name, description, location):
        if not location and not item.get("timeline") and not item.get("expected_timeframe"):
            return False
    score = count_signals(item, name, description, location)
    if source_kind == "capacity" and score < 2:
        return False
    return score >= 2


def project_similarity(left: Dict[str, Any], right: Dict[str, Any]) -> int:
    score = 0
    if left.get("project_type") == right.get("project_type"):
        score += 2
    facility_family = {"facility", "capacity_expansion", "manufacturing_line", "infrastructure_upgrade"}
    if left.get("project_type") in facility_family and right.get("project_type") in facility_family:
        score += 2
    if _compact_lower(left.get("normalized_name")) == _compact_lower(right.get("normalized_name")):
        score += 3
    left_tokens = set(_compact_lower(left.get("normalized_name")).split())
    right_tokens = set(_compact_lower(right.get("normalized_name")).split())
    if left_tokens and right_tokens:
        overlap = len(left_tokens & right_tokens)
        if overlap >= 3:
            score += 2
        elif overlap >= 2:
            score += 1
    if {"land", "acquisition"}.issubset(left_tokens) and {"land", "acquisition"}.issubset(right_tokens):
        score += 3
    if _compact_lower(left.get("location")) and _compact_lower(left.get("location")) == _compact_lower(right.get("location")):
        score += 1
    if _compact_lower(left.get("objective")) and _compact_lower(left.get("objective")) == _compact_lower(right.get("objective")):
        score += 2
    left_commitments = set(left.get("related_commitment_ids") or [])
    right_commitments = set(right.get("related_commitment_ids") or [])
    if left_commitments and right_commitments and left_commitments & right_commitments:
        score += 2
    return score
