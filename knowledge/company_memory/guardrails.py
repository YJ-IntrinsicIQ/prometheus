from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Sequence


INVESTOR_RELEVANCE_VALUES = ("core", "supporting", "low", "excluded", "unknown")
ELIGIBILITY_VALUES = ("eligible", "quarantined", "excluded", "unresolved")
PERIOD_BASIS_VALUES = ("source_period", "event_period", "historical_reference", "derived_period", "unresolved")
SEMANTIC_STATUS_VALUES = ("pass", "warning", "fail")

COMPANY_ACTORS = {"company_management", "company_board", "company"}
EXTERNAL_ACTORS = {"government", "regulator", "customer", "supplier", "industry", "market", "analyst", "third_party"}
ELIGIBLE_COMMITMENT_STATEMENTS = {"explicit_commitment", "target", "guidance", "strategic_priority", "planned_action"}


FY_YEAR_RE = re.compile(r"\bfy(?P<year>\d{2,4})\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(?P<year>(?:19|20)\d{2})\b")

HISTORICAL_CUES = (
    "since ",
    "legacy",
    "historical",
    "previously",
    "earlier",
    "ongoing since",
    "in operation since",
    "production since",
    "built in",
    "developed in",
    "launched in",
    "delivered in",
)

NON_CORE_TERMS = (
    "school",
    "classroom",
    "student",
    "education",
    "educational",
    "campus",
    "teacher",
    "library",
    "pond",
    "stormwater",
    "drainage",
    "sewage",
    "community",
    "csr",
    "charity",
    "welfare",
    "hospital",
    "clinic",
    "temple",
    "religious",
    "road",
    "bridge",
)

BUSINESS_TERMS = (
    "project",
    "capacity",
    "facility",
    "plant",
    "manufacturing",
    "capex",
    "capex",
    "investment",
    "expansion",
    "technology",
    "partnership",
    "customer",
    "product",
    "initiative",
    "acquisition",
    "margin",
    "revenue",
    "cash",
    "working capital",
    "receivable",
    "inventory",
    "payable",
    "order",
    "contract",
    "export",
    "production",
    "commissioned",
    "operational",
    "delivery",
)

RISK_TERMS = (
    "risk",
    "compliance",
    "regulatory",
    "security",
    "privacy",
    "breach",
    "fraud",
    "credit",
    "receivable",
    "default",
    "litigation",
    "liquidity",
    "operational",
    "execution",
    "platform",
    "process",
    "supplier",
    "customer",
    "trust",
    "reputation",
    "disclosure",
    "labeling",
    "counterparty",
    "downtime",
)

COMMENTARY_TERMS = (
    "strategy",
    "strategic",
    "growth",
    "execution",
    "candor",
    "consistency",
    "risk",
    "capital allocation",
    "management",
    "priority",
)


def classify_actor(text: str, *, actor_hint: Any = "", source_section: Any = "") -> Dict[str, Any]:
    """Classify who owns a statement; provenance beats lexical promise language."""
    normalized = _compact_lower(text)
    hint = _compact_lower(actor_hint)
    section = _compact_lower(source_section)
    basis: List[str] = []
    actor = "unknown"
    aliases = {
        "management": "company_management",
        "company management": "company_management",
        "board": "company_board",
        "the company": "company",
        "company": "company",
        "government": "government",
        "ministry": "government",
        "mod": "government",
        "regulator": "regulator",
        "industry": "industry",
        "market": "market",
        "customer": "customer",
        "supplier": "supplier",
        "analyst": "analyst",
    }
    strong_government_context = any(term in normalized for term in ("government of india", "indian government", "ministry of defence", "defence budget", "union budget", "the country intends", "national target", "annual defence production"))
    strong_market_context = any(term in normalized for term in ("industry is expected", "industry is projected", "industry is anticipated", "sector is expected", "sector is projected", "sector anticipates", "market is expected", "market is projected"))
    if strong_government_context:
        actor = "government"
        basis.append("government or national-sector ownership is explicit in the statement")
    elif strong_market_context:
        actor = "industry" if "industry" in normalized or "sector" in normalized else "market"
        basis.append("external industry or market ownership is explicit")
    elif hint in aliases:
        actor = aliases[hint]
        basis.append(f"explicit actor hint: {hint}")
    elif hint in COMPANY_ACTORS | EXTERNAL_ACTORS:
        actor = hint
        basis.append(f"canonical actor hint: {hint}")
    elif any(term in normalized for term in ("we will", "we plan", "we aim", "we intend", "our strategy", "the company will", "the company plans", "management expects", "management plans")):
        actor = "company_management"
        basis.append("first-party management language")
    elif "management" in section or "chairman" in section or "md&a" in section:
        actor = "company_management"
        basis.append("management-origin source section")
    return {"actor_type": actor, "basis": basis, "confidence": "high" if basis else "low"}


def classify_statement_type(text: str, *, category_hint: Any = "", status_hint: Any = "") -> Dict[str, Any]:
    normalized = _compact_lower(text)
    hint = _compact_lower(category_hint)
    basis: List[str] = []
    statement_type = "unknown"
    if any(term in normalized for term in ("csr", "community", "school", "classroom", "charitable")):
        statement_type = "CSR_activity"
        basis.append("social or community activity")
    elif any(term in normalized for term in ("government target", "government aims", "defence production of", "annual defence production", "country intends", "ministry of defence")):
        statement_type = "external_target" if any(term in normalized for term in ("target", "aim", "production of")) else "policy_statement"
        basis.append("government or policy objective")
    elif any(term in normalized for term in ("developed in ", "launched in ", "delivered in ", "successful launch", "substantial investments", "invested heavily", "built in ", "introduced in ")):
        statement_type = "historical_accomplishment"
        basis.append("historical accomplishment rather than a forward commitment")
    elif any(term in normalized for term in ("industry is projected", "industry is expected", "industry is anticipated", "sector is projected", "sector anticipated", "cagr", "market is projected")):
        statement_type = "forecast"
        basis.append("industry or market forecast")
    elif any(term in normalized for term in ("possess", "possesses", "has in-house", "existing facility", "existing capability", "is an ", "is a ")) and not any(term in normalized for term in ("will", "plan", "target", "intend", "aim")):
        statement_type = "existing_capability" if any(term in normalized for term in ("capability", "facility", "in-house", "manufacturing")) else "descriptive_fact"
        basis.append("present-tense description without future action")
    elif any(term in normalized for term in ("during the year", "delivered", "completed", "achieved", "increased", "stood at", "attracted")) and not any(term in normalized for term in ("will", "plan", "target", "intend", "aim")):
        statement_type = "historical_fact"
        basis.append("completed or historical observation")
    elif any(term in normalized for term in ("we commit", "the company commits", "committed to")):
        statement_type = "explicit_commitment"
        basis.append("explicit commitment language")
    elif "guidance" in normalized or re.search(r"\btarget(?:s|ed|ing)?\s+(?:of|to|for|revenue|profit|margin|capacity|growth|large contracts|market share)", normalized):
        statement_type = "guidance" if "guidance" in normalized else "target"
        basis.append("explicit target or guidance")
    elif re.search(r"\b(?:we|the company|management)\s+(?:will|plan(?:s)?(?: to)?|intend(?:s)? to)\b", normalized) or re.search(r"^(?:setting up|acquire|expand)\b", normalized):
        statement_type = "planned_action"
        basis.append("specific future company action")
    elif any(term in normalized for term in ("continue to focus", "our priority", "strategic priority", "our strategy", "focus on")):
        statement_type = "strategic_priority"
        basis.append("continuing strategic priority")
    elif any(term in normalized for term in ("expect", "anticipate")):
        statement_type = "expectation"
        basis.append("expectation without firm commitment")
    elif any(term in normalized for term in ("aspire", "seek to", "aim to")):
        statement_type = "aspiration"
        basis.append("aspirational language")
    elif hint in {"csr", "community", "education"}:
        statement_type = "CSR_activity"
        basis.append("source category identifies non-core activity")
    return {"statement_type": statement_type, "basis": basis, "confidence": "high" if basis else "low"}


def build_semantic_quality(
    *,
    classification: str,
    relevance: Dict[str, Any],
    period: Dict[str, Any],
    materiality: Dict[str, Any],
    eligibility: str | None = None,
    exclusion_reason: str = "",
    evidence_confidence: Any = "medium",
) -> Dict[str, Any]:
    relevance_status = str(relevance.get("status") or "unknown").lower()
    investor_relevance = {
        "core": "core", "supporting": "supporting", "contextual": "low",
        "out_of_scope": "excluded", "ambiguous": "unknown",
    }.get(relevance_status, "unknown")
    period_status = str(period.get("status") or "").upper()
    period_basis = "source_period" if period_status == "RESOLVED" else "historical_reference" if period_status == "HISTORICAL_CONTEXT" else "unresolved"
    resolved_eligibility = eligibility or ("eligible" if materiality.get("should_promote") and investor_relevance in {"core", "supporting"} else "quarantined")
    semantic_status = "pass" if resolved_eligibility == "eligible" else "warning" if resolved_eligibility in {"quarantined", "unresolved"} else "fail"
    return {
        "investor_relevance": investor_relevance,
        "classification": classification or "UNKNOWN",
        "exclusion_reason": exclusion_reason or ("; ".join(relevance.get("limitations") or []) if resolved_eligibility != "eligible" else ""),
        "materiality": materiality.get("level") or "unclear",
        "materiality_basis": list(materiality.get("basis") or []),
        "period_basis": period_basis,
        "eligibility": resolved_eligibility,
        "evidence_confidence": evidence_confidence,
        "semantic_status": semantic_status,
    }


def validate_lineage(*, artifact_generated_at: Any, dependencies: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Fail when a synthesized artifact predates a dependency it claims to consume."""
    def _parse(value: Any) -> datetime | None:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    artifact_time = _parse(artifact_generated_at)
    issues: List[Dict[str, Any]] = []
    for dependency in dependencies:
        dependency_time = _parse(dependency.get("generated_at"))
        if dependency_time is None:
            issues.append({"code": "unresolved_dependency_lineage", "severity": "warning", "dependency": dependency.get("name")})
        elif artifact_time is None or artifact_time < dependency_time:
            issues.append({"code": "stale_dependency", "severity": "fail", "dependency": dependency.get("name"), "dependency_generated_at": dependency.get("generated_at")})
    return {"status": "fail" if any(item["severity"] == "fail" for item in issues) else "warning" if issues else "pass", "issues": issues}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _compact_lower(value: Any) -> str:
    return _normalize_text(value).lower()


def _strip_contextual_example_clauses(text: str) -> str:
    return re.sub(r"\((?:e\.g\.|for example|such as)[^)]*\)", " ", text, flags=re.IGNORECASE)


def _extract_year_mentions(text: str) -> List[int]:
    mentions: List[int] = []
    for match in FY_YEAR_RE.finditer(text):
        raw = match.group("year")
        if len(raw) == 4:
            mentions.append(int(raw))
        elif len(raw) == 2 and raw.isdigit():
            mentions.append(2000 + int(raw))
    for match in YEAR_RE.finditer(text):
        mentions.append(int(match.group("year")))
    return sorted(set(mentions))


def _source_year_value(source_year: Any) -> int | None:
    text = _normalize_text(source_year)
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("fy") and lowered[2:].isdigit():
        year = int(lowered[2:])
        return 2000 + year if year < 100 else year
    if lowered.isdigit():
        value = int(lowered)
        if len(lowered) == 4:
            return value
        if len(lowered) == 2:
            return 2000 + value
    return None


def normalize_period_label(value: Any) -> str:
    text = _normalize_text(value).lower()
    if not text:
        return ""
    if text.startswith("fy") and text[2:].isdigit():
        digits = text[2:]
        return f"fy{digits[-2:]}"
    if text.isdigit() and len(text) == 4:
        return f"fy{text[-2:]}"
    if text.isdigit() and len(text) == 2:
        return f"fy{text}"
    return text


def classify_business_relevance(
    text: str,
    *,
    module_name: str,
    actor_type: str = "",
    source_kind: str = "",
) -> Dict[str, Any]:
    normalized = _compact_lower(text)
    actor = _compact_lower(actor_type)
    source = _compact_lower(source_kind)
    basis: List[str] = []
    limitations: List[str] = []
    score = 0

    if not normalized:
        return {
            "status": "ambiguous",
            "score": 0,
            "basis": ["empty text"],
            "limitations": ["no text to classify"],
            "quarantine": True,
        }

    if actor in {"government", "industry", "auditor"}:
        score -= 3
        basis.append(f"external actor: {actor}")

    if any(term in normalized for term in NON_CORE_TERMS):
        score -= 3
        basis.append("non-core public-interest or civic terms detected")

    if any(term in normalized for term in BUSINESS_TERMS):
        score += 2
        basis.append("business-operations terms detected")

    if module_name == "risks" and any(term in normalized for term in RISK_TERMS):
        score += 1
        basis.append("risk-disclosure terms detected")

    if any(term in normalized for term in COMMENTARY_TERMS) and module_name == "commentary":
        score += 1
        basis.append("management-commentary terms detected")

    if module_name in {"projects", "capacity_expansions", "capacity", "management_commitments", "capital_allocations"} and any(
        term in normalized for term in ("capex", "capacity", "facility", "plant", "manufacturing", "expansion", "project")
    ):
        score += 1
        basis.append("stream-specific business term matched")

    if module_name == "initiatives" and any(
        term in normalized
        for term in ("partnership", "platform", "product", "launch", "deployment", "customer", "solution", "ecosystem")
    ):
        score += 3
        basis.append("initiative business term matched")

    if module_name == "commentary" and any(term in normalized for term in ("strategy", "growth", "execution", "priority", "risk")):
        score += 1
        basis.append("commentary is tied to strategy or execution")

    if source == "company_intelligence" and actor == "management":
        score += 1
        basis.append("management source")

    if any(term in normalized for term in ("macro", "industry outlook", "global economy", "policy", "regulatory")) and module_name not in {"commentary", "risks"}:
        score -= 2
        limitations.append("macro or policy context should not drive core intelligence")

    if score >= 3:
        status = "core"
    elif score >= 1:
        status = "supporting"
    elif score == 0 and module_name == "commentary":
        status = "contextual"
    elif score == 0:
        status = "ambiguous"
    else:
        status = "out_of_scope"

    quarantine = status in {"out_of_scope", "ambiguous"} or (module_name != "commentary" and status == "contextual")
    if quarantine and not limitations:
        limitations.append("item does not look like core investor intelligence")
    return {
        "status": status,
        "score": score,
        "basis": basis,
        "limitations": limitations,
        "quarantine": quarantine,
    }


def resolve_period_status(
    *,
    source_year: Any,
    text: str = "",
    explicit_year: Any = "",
    module_name: str = "",
    target_period: Any = "",
    temporal_role: Any = "",
) -> Dict[str, Any]:
    source_value = _source_year_value(source_year)
    if source_value is None:
        return {
            "status": "INVALID",
            "resolved_period": normalize_period_label(source_year),
            "basis": ["source year is not parseable"],
            "limitations": ["unable to anchor chronology"],
        }

    normalized_text = _strip_contextual_example_clauses(_compact_lower(text))
    years = _extract_year_mentions(normalized_text)
    if explicit_year not in (None, ""):
        explicit_text = _normalize_text(explicit_year)
        if explicit_text.lower().startswith("fy") or explicit_text.isdigit():
            years.extend(_extract_year_mentions(explicit_text))
        elif explicit_text.isdigit() and len(explicit_text) == 4:
            years.append(int(explicit_text))
    target_value = _source_year_value(target_period)

    years = sorted(set(years))
    resolved_period = normalize_period_label(source_year)
    basis: List[str] = [f"source period {resolved_period}"]
    limitations: List[str] = []

    if not years:
        if any(cue in normalized_text for cue in HISTORICAL_CUES):
            return {
                "status": "HISTORICAL_CONTEXT",
                "resolved_period": resolved_period,
                "basis": basis + ["historical wording without a specific year"],
                "limitations": ["historical context should not be promoted as a new progression candidate"],
            }
        return {
            "status": "RESOLVED",
            "resolved_period": resolved_period,
            "basis": basis + ["no conflicting explicit year"],
            "limitations": [],
        }

    if (
        len(years) == 2
        and source_value in years
        and target_value is not None
        and target_value in years
        and target_value != source_value
    ):
        role_label = "target period" if target_value > source_value else "event period"
        return {
            "status": "RESOLVED",
            "resolved_period": resolved_period,
            "basis": basis + [f"source period {source_value} and {role_label} {target_value} are both explicitly supported"],
            "limitations": [],
        }

    if (
        module_name == "capacity_expansions"
        and str(temporal_role or "").strip().lower() == "current_target"
        and source_value is not None
        and target_value is not None
        and len(years) == 2
        and source_value not in years
        and source_value + 1 in years
        and source_value + 2 == target_value
        and target_value in years
    ):
        return {
            "status": "RESOLVED",
            "resolved_period": resolved_period,
            "basis": basis + [f"capacity current-state {source_value + 1} and target period {target_value} are explicitly separated in structured fields"],
            "limitations": [],
        }

    if len(years) > 1:
        if module_name == "capital_allocations" and source_value is not None:
            if source_value in years and all(source_value - 2 <= year <= source_value for year in years):
                return {
                    "status": "RESOLVED",
                    "resolved_period": resolved_period,
                    "basis": basis + [f"capital-allocation disclosure spanning {min(years)}-{max(years)} anchored to source year {source_value}"],
                    "limitations": [],
                }
            if (
                len(years) == 2
                and all(source_value - 2 <= year <= source_value - 1 for year in years)
                and any(term in normalized_text for term in ("dividend", "buyback", "paid", "deployed", "distributed", "returned"))
            ):
                return {
                    "status": "RESOLVED",
                    "resolved_period": resolved_period,
                    "basis": basis + [f"capital-allocation disclosure spanning historical years {min(years)}-{max(years)} with explicit payout or deployment language"],
                    "limitations": [],
                }
        failure_class = "SOURCE_PERIOD_VS_TARGET_PERIOD_CONFLICT" if source_value in years and target_value is not None and target_value in years and target_value != source_value else "PERIOD_RESOLUTION_UNSUPPORTED"
        return {
            "status": "AMBIGUOUS",
            "resolved_period": resolved_period,
            "basis": basis + [f"multiple years mentioned: {', '.join(str(year) for year in years)}"],
            "limitations": ["conflicting chronology"],
            "failure_class": failure_class,
        }

    explicit_value = years[0]
    gap = abs(explicit_value - source_value)
    if gap <= 1:
        return {
            "status": "RESOLVED",
            "resolved_period": resolved_period,
            "basis": basis + [f"explicit year {explicit_value} is within the adjacent analysis window of source year {source_value}"],
            "limitations": [],
        }
    if explicit_value > source_value and module_name in {"projects", "promises", "capacity_expansions", "management_commitments"}:
        return {
            "status": "RESOLVED",
            "resolved_period": resolved_period,
            "basis": basis + [f"future-dated explicit year {explicit_value} is valid for forward-looking {module_name.replace('_', ' ')} evidence"],
            "limitations": [],
        }
    if explicit_value < source_value:
        return {
            "status": "HISTORICAL_CONTEXT",
            "resolved_period": resolved_period,
            "basis": basis + [f"explicit year {explicit_value} predates source year {source_value}"],
            "limitations": ["historical context should remain evidence, not a new announcement"],
        }
    return {
        "status": "OUTSIDE_ANALYSIS_WINDOW",
        "resolved_period": resolved_period,
        "basis": basis + [f"explicit year {explicit_value} is after source year {source_value}"],
        "limitations": ["future-dated item should not be promoted into the current window"],
    }


def assess_progression_materiality(
    text: str,
    *,
    module_name: str,
    relevance_status: str,
    period_status: str,
    evidence_quality: Dict[str, Any] | None = None,
    status_text: str = "",
) -> Dict[str, Any]:
    normalized = _compact_lower(text)
    status_norm = _compact_lower(status_text)
    score = 0
    basis: List[str] = []
    limitations: List[str] = []

    if relevance_status in {"core", "supporting"}:
        score += 2 if relevance_status == "core" else 1
        basis.append(f"relevance classified as {relevance_status}")
    else:
        score -= 3
        limitations.append(f"relevance classified as {relevance_status}")

    if period_status == "RESOLVED":
        score += 1
        basis.append("period is resolved")
    elif period_status == "HISTORICAL_CONTEXT":
        score -= 2
        limitations.append("historical context should not drive a progression turn")
    else:
        score -= 3
        limitations.append(f"period status is {period_status.lower()}")

    if evidence_quality:
        if evidence_quality.get("company_specificity") == "high":
            score += 2
            basis.append("company-specific evidence")
        elif evidence_quality.get("company_specificity") == "medium":
            score += 1
        else:
            limitations.append("company specificity is weak")

        if evidence_quality.get("actionability") == "high":
            score += 1
            basis.append("actionable evidence")

        if evidence_quality.get("investor_relevance") == "high":
            score += 1
            basis.append("investor-relevant evidence")
        elif evidence_quality.get("investor_relevance") == "low":
            score -= 1
            limitations.append("investor relevance is low")

        if evidence_quality.get("numeric_support"):
            score += 1
            basis.append("numeric support present")

    if any(term in normalized for term in NON_CORE_TERMS):
        score -= 4
        limitations.append("non-core civic or public-interest wording")

    if any(term in normalized for term in BUSINESS_TERMS):
        score += 1
        basis.append("business-operations wording")

    if any(term in normalized for term in ("commissioned", "operational", "delayed", "abandoned", "superseded", "confirmed", "delivered")):
        score += 2
        basis.append("explicit execution transition")

    if module_name == "commentary" and any(term in normalized for term in COMMENTARY_TERMS):
        score += 1
        basis.append("commentary change is strategically meaningful")

    if status_norm and status_norm not in {"", "planned", "announced", "informational"}:
        score += 1
        basis.append("status text adds progression signal")

    if score >= 7:
        level = "high"
    elif score >= 4:
        level = "medium"
    elif score >= 1:
        level = "low"
    else:
        level = "unclear"

    should_promote = (
        period_status == "RESOLVED"
        and relevance_status in {"core", "supporting"}
        and (level in {"high", "medium"} or module_name == "commentary")
    )
    return {
        "level": level,
        "score": score,
        "basis": basis,
        "limitations": limitations,
        "should_promote": should_promote,
    }


def semantic_validation(
    *,
    module_name: str,
    relevance: Dict[str, Any],
    period: Dict[str, Any],
    materiality: Dict[str, Any] | None = None,
) -> Dict[str, List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    relevance_status = str(relevance.get("status") or "").lower()
    period_status = str(period.get("status") or "").upper()
    materiality_level = str((materiality or {}).get("level") or "").lower()

    if relevance.get("quarantine"):
        errors.append(f"business relevance classified as {relevance_status or 'unknown'}")
    elif relevance_status == "contextual" and module_name != "commentary":
        errors.append("contextual item is not eligible for a core intelligence stream")

    if period_status in {"INVALID", "AMBIGUOUS", "OUTSIDE_ANALYSIS_WINDOW"}:
        errors.append(f"period status is {period_status.lower()}")
    elif period_status == "historical_context" and module_name in {"projects", "capacity", "management_commitments"}:
        errors.append("historical context should not become a new progression candidate")

    if materiality and materiality_level in {"low", "unclear"}:
        warnings.append(f"candidate materiality is {materiality_level}")

    return {
        "errors": errors,
        "warnings": warnings,
    }
