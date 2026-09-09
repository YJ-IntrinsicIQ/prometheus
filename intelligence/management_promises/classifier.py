from __future__ import annotations

from typing import Any, Dict, List

# ── Materiality ────────────────────────────────────────────────────────────────

_TRIVIAL_KEYWORDS = {
    "gratuity",
    "pension",
    "cancer sanatorium",
    "cancer sanitorium",
    "wadala",
    "flood relief",
    "csr contribution",
    "annual contribution",
    "provident fund",
    "superannuation",
    "remain committed to excellence",
    "continue focusing on customers",
    "remain committed to our values",
    "we will continue to serve",
}

_TRIVIAL_EVENT_TYPES = {
    "hr_initiative",
}

_MATERIAL_STREAM_TYPES = {
    "commitment",
    "capital_allocation",
    "capacity",
    "legacy_strategy",
}

_MATERIAL_KEYWORDS = {
    "revenue",
    "growth",
    "expand",
    "expand internationally",
    "margin",
    "profitability",
    "cost reduction",
    "ebitda",
    "capex",
    "acquisition",
    "merger",
    "market share",
    "product launch",
    "specialty",
    "platform",
    "digital",
    "capacity",
    "manufacturing",
    "regulatory",
    "compliance",
    "fda",
    "r&d",
    "research",
    "pipeline",
    "emission",
    "emissions",
    "sustainability target",
    "borrowing",
    "lending",
    "disburse",
    "disbursement",
    "branch",
    "loan",
    "npa",
    "international",
    "export",
    "capital allocation",
    "invest",
    "investment",
    "return",
    "roe",
    "roic",
    "roa",
    "enterprise value",
    "shareholder",
    "dividend",
    "debt",
    "balance sheet",
    "generics",
    "branded",
    "biosimilar",
    "biologic",
    "specialty pipeline",
    "wisely",
    "data platform",
    "product per customer",
    "ppc",
    "digitisation",
    "digitization",
    "grievance",
    "customer service",
    "collection",
    "insurance",
    "cross-sell",
}


def is_material_promise(item: Dict[str, Any]) -> bool:
    """Return True if the progression item is Gold-worthy based on materiality."""
    theme = (item.get("theme") or "").lower()
    stream_types = set(item.get("stream_types") or [])
    linked_model_ids = item.get("linked_company_model_ids") or []
    events = item.get("events") or []

    # Exclude trivial language regardless of other signals
    if any(kw in theme for kw in _TRIVIAL_KEYWORDS):
        return False

    # Exclude HR-only event types with no business-critical linkage
    event_types = {e.get("event_type") or "" for e in events}
    if event_types <= _TRIVIAL_EVENT_TYPES and not linked_model_ids:
        return False

    # Any linked_company_model_id is a strong materiality signal
    if linked_model_ids:
        return True

    # Material stream types with business-relevant content
    if stream_types & _MATERIAL_STREAM_TYPES:
        if any(kw in theme for kw in _MATERIAL_KEYWORDS):
            return True
        # Check event statements for materiality
        for event in events:
            stmt = (event.get("statement_text") or event.get("action_taken") or "").lower()
            if any(kw in stmt for kw in _MATERIAL_KEYWORDS):
                return True

    # Capacity / capital_allocation streams are almost always material
    if stream_types & {"capital_allocation", "capacity"}:
        return True

    return False


def _commitment_semantic_quality(commitment: Dict[str, Any]) -> Dict[str, Any]:
    value = commitment.get("semantic_quality") or {}
    return value if isinstance(value, dict) else {}


def is_material_commitment_promise(commitment: Dict[str, Any]) -> bool:
    """Return True when a canonical Management Commitment is worth Gold tracking.

    Management Commitments owns the promise universe. This filter only decides
    investor-facing materiality inside that universe; it never admits projects,
    capital-allocation events, risks, or other non-MC progression rows.
    """
    if not isinstance(commitment, dict):
        return False
    fingerprint = str(commitment.get("commitment_fingerprint") or "").strip()
    if not fingerprint:
        return False
    text = " ".join(
        str(commitment.get(key) or "")
        for key in ("topic", "category", "original_statement", "normalized_commitment")
    ).lower()
    if any(kw in text for kw in _TRIVIAL_KEYWORDS):
        return False

    semantic = _commitment_semantic_quality(commitment)
    relevance = str(semantic.get("investor_relevance") or "").lower()
    relevance_outcome = str(semantic.get("relevance_outcome") or "").upper()
    materiality = str(semantic.get("materiality") or commitment.get("priority") or "").lower()
    statement_type = str(commitment.get("statement_type") or "").lower()
    priority = str(commitment.get("priority") or "").lower()

    has_material_keyword = any(kw in text for kw in _MATERIAL_KEYWORDS)
    has_specific_operating_commitment = any(
        kw in text
        for kw in (
            "dashboard", "app", "real-time", "monitoring", "data integrity", "system", "platform",
            "facility", "launch", "market", "customer", "capacity", "pipeline", "r&d", "research",
        )
    )
    if relevance == "excluded":
        return False
    if relevance == "core" or relevance_outcome == "KEEP":
        return True
    if relevance_outcome == "QUARANTINE" and not has_specific_operating_commitment:
        return False
    if materiality in {"high", "medium"} and has_material_keyword:
        return True
    if priority == "high" and has_material_keyword:
        return True
    if statement_type in {"target", "guidance", "planned_action", "future_action", "strategic_priority"} and (has_material_keyword or has_specific_operating_commitment):
        return True
    return False


# ── Promise type classification ────────────────────────────────────────────────

_TYPE_SIGNALS: List[tuple] = [
    # (promise_type, keywords)
    ("REGULATORY_REMEDIATION", ["fda", "usfda", "mhra", "regulatory action", "regulatory compliance", "remediation", "warning letter", "form 483", "consent decree", "drug import ban"]),
    ("CAPACITY", ["capacity", "manufacturing capacity", "facility", "plant", "hangar", "clean room", "throughput", "expansion", "production capacity"]),
    ("DIGITAL_OR_TECH", ["digital", "platform", "data platform", "ai", "machine learning", "blockchain", "technology", "digitisation", "digitization", "tech", "system", "software", "loan origination", "product per customer", "ppc"]),
    ("PRODUCT_LAUNCH", ["product launch", "pipeline", "specialty", "biosimilar", "biologic", "generics", "r&d", "research", "new product", "launch", "wisely", "indica", "ilumya", "cosentyx"]),
    ("GROWTH_TARGET", ["grow faster", "market share", "revenue growth", "international", "expand", "export", "overseas", "global", "geographic"]),
    ("CAPITAL_ALLOCATION", ["acquisition", "merger", "capex", "invest", "capital allocation", "dividend", "buyback", "debt repayment", "no debt", "balance sheet"]),
    ("MARGIN_OR_COST", ["margin", "profitability", "ebitda", "cost reduction", "efficiency", "fixed cost", "interest cost", "rationalising"]),
    ("CUSTOMER_OR_SERVICE", ["customer service", "customer satisfaction", "grievance", "nps", "service standard", "collection", "borrower", "loan disbursement", "cross-sell"]),
    ("SUSTAINABILITY", ["emission", "emissions", "scope 1", "scope 2", "sustainability", "esg", "carbon", "leed", "renewable", "net zero"]),
    ("MARKET_EXPANSION", ["market", "market position", "segment", "geography", "new market", "penetration"]),
]


def classify_promise_type(item: Dict[str, Any]) -> str:
    """Classify the promise into one of the Gold promise types."""
    theme = (item.get("theme") or "").lower()
    events = item.get("events") or []
    event_type = " ".join(e.get("event_type") or "" for e in events).lower()
    full_text = theme + " " + event_type

    # Check all statements
    stmt_text = " ".join(
        (e.get("statement_text") or e.get("action_taken") or "").lower()
        for e in events
    )
    full_text += " " + stmt_text

    for promise_type, keywords in _TYPE_SIGNALS:
        if any(kw in full_text for kw in keywords):
            return promise_type

    return "OTHER"
