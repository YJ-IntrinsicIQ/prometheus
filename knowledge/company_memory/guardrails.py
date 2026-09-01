from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Sequence


INVESTOR_RELEVANCE_VALUES = ("core", "supporting", "low", "excluded", "unknown")
ELIGIBILITY_VALUES = ("eligible", "quarantined", "excluded", "unresolved")

# Four-outcome business relevance contract
BUSINESS_RELEVANCE_OUTCOMES = ("KEEP", "DEMOTE", "QUARANTINE", "HARD_FAIL")
PERIOD_BASIS_VALUES = ("source_period", "event_period", "historical_reference", "derived_period", "unresolved")
SEMANTIC_STATUS_VALUES = ("pass", "warning", "fail")
FORWARD_TARGET_MODULES = {"projects", "promises", "capacity_expansions", "management_commitments", "initiatives"}
TEMPORAL_ROLE_VALUES = (
    "SOURCE_PERIOD",
    "STATEMENT_PERIOD",
    "EVENT_PERIOD",
    "TARGET_PERIOD",
    "MILESTONE_PERIOD",
    "OUTCOME_PERIOD",
    "HISTORICAL_CONTEXT",
    "COMPARATIVE_PERIOD",
    "NON_TEMPORAL_REFERENCE",
    "UNKNOWN",
)

COMPANY_ACTORS = {"company_management", "company_board", "company"}
EXTERNAL_ACTORS = {"government", "regulator", "customer", "supplier", "industry", "market", "analyst", "third_party"}
ELIGIBLE_COMMITMENT_STATEMENTS = {
    "explicit_commitment", "target", "guidance", "strategic_priority", "planned_action", "future_action",
}

# Stable codes for quarantine reason — appear in artifact output so audits can produce distributions.
QUARANTINE_REASON_CODES = frozenset({
    "EXTERNAL_ACTOR",
    "NOT_FUTURE_ORIENTED",
    "NO_ACTIONABLE_INTENT",
    "GENERIC_ASPIRATION",
    "HISTORICAL_FACT",
    "NON_INVESTOR_MATERIAL",
    "AMBIGUOUS_ACTOR",
    "UNCLASSIFIED_STATEMENT",
    "OTHER",
})


FY_YEAR_RE = re.compile(r"\bfy(?P<year>\d{2,4})\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(?P<year>(?:19|20)\d{2})\b")

# ── Statement-type detection patterns (generic, not sector-specific) ──────────

# Gerund openers: present-participle verbs used as strategy-list bullets
# where the company actor is implied from context.
_GERUND_PREFIX_RE = re.compile(
    r"^(?:targeting|building|expanding|evaluating|ramping(?:\s+up)?|increasing|strengthening"
    r"|developing|entering|growing|investing|launching|commerciali[sz]ing"
    r"|accelerating|deploying|scaling|capturing|diversifying|advancing"
    r"|rolling(?:\s+out)?|driving|leveraging|establishing|implementing|creating"
    r"|extending|broadening|deepening|continuing(?:\s+to)?|focusing|focussing"
    r"|consolidating|integrating|transforming|delivering|executing|pursuing"
    r"|stepping(?:\s+up)?|ramping|modernising|modernizing|digitali[sz]ing"
    r"|streamlining|augmenting|deepening|nurturing|commissioning|acquiring"
    r"|upgrading|completing|constructing|operationalizing|operationalising"
    r"|enhancing|maintaining|ensuring|assessing|monitoring|sustaining|fostering"
    r"|migrating|validating|filing|using|reducing|planning)\b",
    re.IGNORECASE,
)

# Imperative / infinitive forms used as strategy bullets
_IMPERATIVE_PREFIX_RE = re.compile(
    r"^(?:enhance|build|expand|enter|develop|continue|increase|accelerate|strengthen"
    r"|optimi[sz]e|scale|capture|deliver|execute|achieve|establish|improve"
    r"|maximi[sz]e|diversify|leverage|unlock|drive|grow|advance|ramp(?:\s+up)?"
    r"|invest|launch|deploy|commerciali[sz]e|consolidate|extend|broaden|deepen"
    r"|maintain|preserve|retain|secure|gain|generate|monetize|monetise|integrate"
    r"|modernise|modernize|digitali[sz]e|streamline|augment|identify|pursue"
    r"|ensure|evaluate|target|use|file|plan|assess|monitor|co-process|co-develop"
    r"|replicate|reduce|divest|migrate|validate|sustain|foster)\b",
    re.IGNORECASE,
)

# Explicit subject-verb future action: "We will / plan to / intend to / continue to / seek to"
_SUBJECT_FUTURE_RE = re.compile(
    r"\b(?:we|the company|management|management team|the board|company)\s+"
    r"(?:will|plan(?:s)?(?: to)?|intend(?:s)? to|continue(?:s)? to|seek(?:s)? to|aim(?:s)? to"
    r"|expect(?:s)? to|propose(?:s)? to|commit(?:s)? to)\b",
    re.IGNORECASE,
)

# Generic aspirational language — future-sounding but no trackable action/object
_GENERIC_ASPIRATION_RE = re.compile(
    r"\b(?:remain(?:ing)? committed to|continue to (?:remain|be)|"
    r"(?:become|be) (?:a|the) (?:global\s+|world\s+)?(?:leader|leading|best)\b|"
    r"pursue (?:excellence|quality|value\b)|"
    r"(?:create|deliver|build|unlock) (?:stakeholder|shareholder) value|"
    r"committed to (?:excellence|quality)\b|"
    r"strive to be|dedicated to being|aspire to be|"
    r"achieve (?:excellence|the highest)|remain at the (?:forefront|vanguard|cutting edge))\b",
    re.IGNORECASE,
)

# Specific business-trackable nouns: presence of these makes a gerund/imperative statement trackable
_TRACKABLE_NOUNS = frozenset({
    "pipeline", "facility", "facilities", "plant", "plants", "platform", "platforms",
    "capacity", "portfolio", "manufacturing", "distribution", "partnership", "partnerships",
    "acquisition", "acquisitions", "contract", "contracts", "r&d", "research",
    "indication", "indications", "technology", "segment", "segments", "geography", "geographies",
    "network", "infrastructure", "capability", "capabilities",
    "product", "products", "channel", "channels", "market", "markets",
    "presence", "footprint", "customer", "customers",
})


def _has_specific_action_object(text: str) -> bool:
    """Return True when a future-action form has a specific enough object to track over time."""
    lower = text.lower()
    # Named proper nouns — two+ consecutive capitalized words signal geography, brand, product
    if re.search(r"(?<![A-Za-z])[A-Z][a-zA-Z]{2,}(?:\s+(?:and\s+)?[A-Z][a-zA-Z]{2,})+", text):
        return True
    # Fiscal-year or calendar-year targets
    if re.search(r"\bfy\d{2,4}\b|\bby\s+(?:fy|\d{4})\b", lower):
        return True
    # Numeric quantities with business units.  Use (?!\w) not \b after the unit
    # symbol because symbols like % are non-word chars — \b never fires after them.
    if re.search(
        r"\b\d+(?:[.,]\d+)?\s*(?:%|x|cr|crore|mn|million|bn|billion|units?|beds?|stores?"
        r"|outlets?|mt|mw|kl|liter|litre|tonne|ton)(?!\w)",
        lower,
    ):
        return True
    # Trackable business nouns
    words = set(re.findall(r"[a-z][a-z0-9&]+", lower))
    return bool(words & _TRACKABLE_NOUNS)


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

# Civic/public-interest terms that indicate non-investor intelligence (beyond core NON_CORE_TERMS)
CIVIC_PUBLIC_INTEREST_TERMS = (
    "consumer feedback",
    "consumer complaint",
    "consumer case",
    "consumer protection",
    "stakeholder litigation",
    "unfair trade practice",
    "public interest",
    "civic",
    "municipal",
    "panchayat",
    "zoning",
    "building permit",
    "environmental clearance",
    "pollution control",
    "waste management",
    "water supply",
    "sanitation",
    "public hearing",
    "labeling regulation",
    "labeling compliance",
    "disclosure regulation",
    "platform disclosure",
    "partner platform visibility",
    "partner platform dependence",
    "visibility on platform",
    "platform dependence",
    "government scheme",
    "social welfare",
    "affordable housing",
    "rural development",
    "livelihood",
    "employment generation",
    "skill development",
    "vocational training",
)

# Module-specific core terms that signal investor relevance
MODULE_CORE_TERMS = {
    "risks": (
        "concentration",
        "dependence",
        "counterparty",
        "regulatory risk",
        "compliance risk",
        "credit risk",
        "liquidity risk",
        "operational risk",
        "execution risk",
        "platform risk",
        "supplier risk",
        "customer risk",
        "reputation risk",
        "disclosure risk",
        "litigation risk",
        "margin risk",
        "revenue risk",
        "cash flow risk",
        "working capital risk",
    ),
    "projects": (
        "capex",
        "capacity",
        "facility",
        "plant",
        "manufacturing",
        "expansion",
        "project",
        "commissioned",
        "operational",
        "production",
        "delivery",
    ),
    "promises": (
        "target",
        "guidance",
        "commitment",
        "milestone",
        "commercial production",
        "commissioning",
        "launch",
    ),
    "capacity_expansions": (
        "capacity",
        "throughput",
        "production",
        "commercial production",
        "line",
        "facility",
        "plant",
        "expansion",
    ),
    "initiatives": (
        "partnership",
        "platform",
        "product",
        "launch",
        "deployment",
        "customer",
        "solution",
        "ecosystem",
    ),
    "commentary": (
        "strategy",
        "growth",
        "execution",
        "capital allocation",
        "priority",
        "risk",
    ),
}

# Hard-fail terms: malformed, contaminated, or fundamentally broken items
HARD_FAIL_TERMS = (
    "audit",
    "auditor",
    "reasonable assurance",
    "financial statement",
    "going concern",
    "table of contents",
    "forward looking statement",
    "corporate governance report",
    "director profile",
    "notice of annual general meeting",
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
    """Classify a management statement into a semantic type.

    Returns a dict with:
      statement_type  — classification (see ELIGIBLE_COMMITMENT_STATEMENTS for eligible types)
      future_orientation — True when the statement describes intended future action
      actionability   — "specific" | "directional" | "generic" | "none"
      basis           — list of evidence strings
      confidence      — "high" | "low"
    """
    normalized = _compact_lower(text)
    hint = _compact_lower(category_hint)
    basis: List[str] = []
    statement_type = "unknown"
    future_orientation = False
    actionability = "none"

    # ── 1. Hard excludes — checked first regardless of future language ──────

    if any(term in normalized for term in ("csr", "community", "school", "classroom", "charitable", "education system", "teacher training", "malnutrition", "child nutrition", "hunger alleviation")):
        statement_type = "CSR_activity"
        basis.append("social or community activity")
    elif hint in {"csr", "community", "education"}:
        statement_type = "CSR_activity"
        basis.append("source category identifies non-core activity")

    # Pension/gratuity/employee-benefit mechanics — non-investor administrative
    elif any(term in normalized for term in ("pension plan", "gratuity fund", "provident fund", "pension to employees", "contribution to the gratuity", "pension fund")):
        statement_type = "non_investor_material"
        basis.append("employee benefit administration")

    # Government / policy statements (not the company's own action)
    elif any(term in normalized for term in ("government target", "government aims", "defence production of", "annual defence production", "country intends", "ministry of defence")) \
            or re.search(r"\bunder (?:the )?[a-z][a-z\s]+ scheme\b", normalized):
        statement_type = "external_statement"
        basis.append("government or policy objective")

    # Historical accomplishments — past tense + accomplishment signals, no forward language
    elif any(term in normalized for term in ("developed in ", "launched in ", "delivered in ", "successful launch", "substantial investments", "invested heavily", "built in ", "introduced in ")):
        statement_type = "historical_accomplishment"
        basis.append("historical accomplishment rather than a forward commitment")

    # Historical facts (past performance) — no future language override
    elif (
        any(term in normalized for term in ("during the year", "stood at", "attracted", "ensured adequate", "donated", "awarded",
                                            "has continued to improve", "has improved", "has grown", "has increased to"))
        and not any(term in normalized for term in ("will", "plan", "target", "intend", "aim", "expect"))
    ):
        statement_type = "historical_fact"
        basis.append("completed or historical observation")

    # Industry/market forecasts — external, not a company commitment
    elif any(term in normalized for term in (
        "industry is projected", "industry is expected", "industry is anticipated",
        "sector is projected", "sector anticipated", "cagr", "market is projected",
        "market is expected", "likely to change", "likely to continue",
        "are expected to grow", "industry forecast",
    )):
        statement_type = "forecast"
        basis.append("industry or market forecast")

    # Present-state capability descriptions without forward language
    elif (
        any(term in normalized for term in ("possess", "possesses", "has in-house", "existing facility", "existing capability"))
        and not any(term in normalized for term in ("will", "plan", "target", "intend", "aim"))
    ):
        statement_type = "existing_capability" if any(term in normalized for term in ("capability", "facility", "in-house", "manufacturing")) else "descriptive_fact"
        basis.append("present-tense description without future action")

    # Generic aspiration — future-sounding language with no trackable object
    elif _GENERIC_ASPIRATION_RE.search(normalized):
        statement_type = "generic_aspiration"
        basis.append("aspirational language without specific trackable action")

    # ── 2. Genuine commitment forms ──────────────────────────────────────────

    # Explicit commitment — strongest signal
    elif any(term in normalized for term in ("we commit", "the company commits", "committed to achieving", "committed to delivering")):
        statement_type = "explicit_commitment"
        future_orientation = True
        actionability = "specific"
        basis.append("explicit commitment language")

    # Guidance / numerical target
    elif "guidance" in normalized or re.search(
        r"\btarget(?:s|ed|ing)?\s+(?:of|to|for|revenue|profit|margin|capacity|growth|large contracts|market share)",
        normalized,
    ):
        statement_type = "guidance" if "guidance" in normalized else "target"
        future_orientation = True
        actionability = "specific"
        basis.append("explicit target or guidance")

    # Subject-explicit future action: "We will / plan to / intend to / continue to / seek to"
    elif _SUBJECT_FUTURE_RE.search(normalized) or re.search(r"^(?:setting up|acquire|expand)\b", normalized):
        statement_type = "planned_action"
        future_orientation = True
        actionability = "specific" if _has_specific_action_object(text) else "directional"
        basis.append("explicit subject-verb future action")

    # Gerund opener — present-participle bullet implying company actor
    elif _GERUND_PREFIX_RE.match(normalized):
        future_orientation = True
        if _has_specific_action_object(text):
            statement_type = "future_action"
            actionability = "specific"
            basis.append("gerund-form future action with specific object")
        else:
            statement_type = "strategic_priority"
            actionability = "directional"
            basis.append("gerund-form strategic direction without specific object")

    # Imperative / infinitive opener — strategy-list form
    elif _IMPERATIVE_PREFIX_RE.match(normalized):
        future_orientation = True
        if _has_specific_action_object(text):
            statement_type = "future_action"
            actionability = "specific"
            basis.append("imperative-form future action with specific object")
        else:
            statement_type = "strategic_priority"
            actionability = "directional"
            basis.append("imperative-form strategic direction without specific object")

    # Attribution frame: "Management [identifies|emphasizes|…] [gerund/commitment]"
    # Strip the attribution prefix and re-classify the embedded action (one level only).
    # Only rescued when the inner text resolves to an eligible commitment type; otherwise
    # the outer result stays unknown so a non-commitment attribution doesn't become eligible.
    elif re.match(
        r"^(?:management|the company|the board)\s+(?:identifies?|emphasizes?|emphasises?|highlights?|states? that|confirms?|indicates?|reaffirms?|notes? that|signals?)\s+",
        normalized,
    ):
        inner = re.sub(
            r"^(?:management|the company|the board)\s+(?:identifies?|emphasizes?|emphasises?|highlights?|states? that|confirms?|indicates?|reaffirms?|notes? that|signals?)\s+",
            "",
            normalized,
        ).strip()
        inner_result = classify_statement_type(inner, category_hint=category_hint, status_hint=status_hint)
        if inner_result["statement_type"] in ELIGIBLE_COMMITMENT_STATEMENTS:
            statement_type = inner_result["statement_type"]
            future_orientation = inner_result["future_orientation"]
            actionability = inner_result["actionability"]
            basis = ["management attribution frame → " + b for b in inner_result["basis"]]
        # If inner is unknown/non-commitment, leave statement_type as "unknown" — do not
        # admit a non-commitment just because it starts with "Management identifies".

    # Noun-phrase intent: "conscious/deliberate/stated effort to [verb]"
    elif re.match(r"^(?:a\s+)?(?:conscious|deliberate|stated|proactive)\s+effort\s+to\b", normalized):
        statement_type = "planned_action"
        future_orientation = True
        actionability = "specific" if _has_specific_action_object(text) else "directional"
        basis.append("noun-phrase commitment form: effort-to-verb")

    # Strategic priority — broad ongoing direction
    elif any(term in normalized for term in ("continue to focus", "our priority", "strategic priority", "our strategy", "focus on", "our approach")):
        statement_type = "strategic_priority"
        future_orientation = True
        actionability = "directional"
        basis.append("continuing strategic priority")

    # Expectation without firm commitment
    elif any(term in normalized for term in ("expect", "anticipate")):
        statement_type = "expectation"
        future_orientation = True
        actionability = "directional"
        basis.append("expectation without firm commitment")

    # Aspiration — weaker forward signal
    elif any(term in normalized for term in ("aspire", "seek to", "aim to")):
        statement_type = "aspiration"
        future_orientation = True
        actionability = "generic"
        basis.append("aspirational language")

    return {
        "statement_type": statement_type,
        "future_orientation": future_orientation,
        "actionability": actionability,
        "basis": basis,
        "confidence": "high" if basis else "low",
    }


def build_semantic_quality(
    *,
    classification: str,
    relevance: Dict[str, Any],
    period: Dict[str, Any],
    materiality: Dict[str, Any],
    eligibility: str | None = None,
    exclusion_reason: str = "",
    evidence_confidence: Any = "medium",
    commitment_eligible: bool = False,
) -> Dict[str, Any]:
    """Build the semantic quality assessment for a candidate.

    commitment_eligible — when True, DEMOTE or QUARANTINE relevance outcomes do
    not veto admission.  Both signal reduced materiality or neutral scoring, not
    "not a real commitment."  HARD_FAIL still excludes regardless: those cases
    have structural defects (empty text, audit boilerplate) that make the item
    unusable.  CSR/external-actor items are already excluded upstream by setting
    commitment_eligible=False before this function is called.
    """
    relevance_status = str(relevance.get("status") or "unknown").lower()
    investor_relevance = {
        "core": "core", "supporting": "supporting", "contextual": "low",
        "out_of_scope": "excluded", "ambiguous": "unknown",
    }.get(relevance_status, "unknown")

    # Four-outcome contract drives eligibility
    outcome = str(relevance.get("outcome") or "").upper()
    if outcome == "KEEP":
        resolved_eligibility = "eligible"
    elif outcome == "DEMOTE":
        # DEMOTE means 'valid but lower materiality'.  For genuine commitments
        # (commitment_eligible=True) lower materiality does not mean quarantine.
        resolved_eligibility = "eligible" if commitment_eligible else "quarantined"
    elif outcome == "QUARANTINE":
        # QUARANTINE can mean "neutral score" (no matching BUSINESS_TERMS) just
        # as often as "civic/CSR content."  For genuine commitments
        # (commitment_eligible=True) a neutral score does not mean quarantine.
        resolved_eligibility = "eligible" if commitment_eligible else "quarantined"
    elif outcome == "HARD_FAIL":
        resolved_eligibility = "excluded"
    else:
        # Fallback to legacy logic
        resolved_eligibility = eligibility or ("eligible" if materiality.get("should_promote") and investor_relevance in {"core", "supporting"} else "quarantined")

    period_status = str(period.get("status") or "").upper()
    period_basis = "source_period" if period_status == "RESOLVED" else "historical_reference" if period_status == "HISTORICAL_CONTEXT" else "unresolved"
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
        "relevance_outcome": outcome,
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


_COMPARATIVE_YEAR_CUES = (
    "from ",
    "compared to",
    "compares",
    "comparison to",
    "versus",
    "vs ",
    "vs.",
    "up from",
    "down from",
    "increase from",
    "decrease from",
    "rose from",
    "fell from",
    "grew from",
    "as of",
    "as on",
    "as at",
    "during ",
    "since ",
    "between ",
    "through ",
    "ongoing",
    "current",
    "shipped",
    "manufactured",
    "commissioned",
    "launched",
    "handed over",
    "completed",
    "scaled",
    "production",
    "manufacturing",
    "progress",
    "in progress",
    "achieved",
    "year on year",
    "year-on-year",
    "y-o-y",
    "yoy",
)
_YEAR_RANGE_RE = re.compile(r"\b(?:19|20)\d{2}\s*[-–]\s*(?:(?:19|20)\d{2}|\d{2})\b")
_NAMED_REFERENCE_BEFORE_YEAR_RE = re.compile(
    r"(?:"
    r"\b(?:act|acts|regulation|regulations|rules|rule|code|standard|standards|scheme|circular|"
    r"guideline|guidelines|notification)\s*,?\s*$"
    r"|\b(?:income tax|banking regulation|companies|sebi|rbi|reserve bank of india|ind as|ias|ifrs)\s+"
    r"(?:act|regulation|regulations|rules|standard|standards|scheme|circular|guidelines?)?\s*,?\s*$"
    r"|\b(?:section|u/s|under section)\s+[a-z0-9()/. -]{0,40}$"
    r"|\bdated\s+(?:[a-z]+\s+)?\d{1,2},?\s*$"
    r")",
    re.IGNORECASE,
)
_NAMED_REFERENCE_AFTER_YEAR_RE = re.compile(
    r"^\s*(?:act|acts|regulation|regulations|rules|rule|code|standard|standards|scheme|circular|guidelines?|notification)\b",
    re.IGNORECASE,
)


def _has_comparative_year_context(text: str) -> bool:
    normalized = _compact_lower(text)
    if not normalized:
        return False
    if re.search(r"\bfrom\b.*\bto\b", normalized):
        return True
    return any(cue in normalized for cue in _COMPARATIVE_YEAR_CUES)


def _has_year_range_context(text: str) -> bool:
    return bool(_YEAR_RANGE_RE.search(_normalize_text(text)))


def _has_target_year_context(text: str) -> bool:
    normalized = _compact_lower(text)
    return any(
        cue in normalized
        for cue in (
            "target",
            "expected",
            "projected",
            "forecast",
            "planned",
            "plan",
            "aim",
            "goal",
            "milestone",
            "by fy",
            "by ",
        )
    )


def _is_non_temporal_year_reference(text: str, match: re.Match[str]) -> bool:
    start, end = match.span()
    left_context = text[max(0, start - 90) : start]
    right_context = text[end : min(len(text), end + 40)]
    if _NAMED_REFERENCE_BEFORE_YEAR_RE.search(left_context):
        return True
    if _NAMED_REFERENCE_AFTER_YEAR_RE.search(right_context):
        return True
    return False


def _extract_year_mentions(text: str) -> List[int]:
    roles = classify_temporal_references(text)
    return sorted(
        {
            int(item["year"])
            for item in roles
            if item["role"] != "NON_TEMPORAL_REFERENCE"
        }
    )


def _year_value_from_match(raw: str) -> int:
    if len(raw) == 4:
        return int(raw)
    return 2000 + int(raw)


def _window(text: str, start: int, end: int, *, width: int = 120) -> str:
    return _normalize_text(text[max(0, start - width) : min(len(text), end + width)])


def _role_from_year_context(
    *,
    text: str,
    match: re.Match[str],
    year: int,
    source_value: int | None,
    target_value: int | None,
    module_name: str,
) -> str:
    snippet = _compact_lower(_window(text, *match.span()))
    if _is_non_temporal_year_reference(text, match):
        return "NON_TEMPORAL_REFERENCE"
    if target_value is not None and year == target_value and target_value != source_value:
        return "TARGET_PERIOD" if target_value > (source_value or target_value) else "EVENT_PERIOD"
    if source_value is not None and year == source_value:
        if any(cue in snippet for cue in ("annual report", "for the year ended", "year ended", "fy ")):
            return "SOURCE_PERIOD"
        return "STATEMENT_PERIOD"
    if source_value is not None and year < source_value:
        if _has_comparative_year_context(snippet) or _has_year_range_context(snippet):
            return "COMPARATIVE_PERIOD"
        if any(cue in snippet for cue in HISTORICAL_CUES):
            return "HISTORICAL_CONTEXT"
        return "HISTORICAL_CONTEXT"
    if _has_target_year_context(snippet):
        return "TARGET_PERIOD"
    if any(cue in snippet for cue in ("completed", "commissioned", "launched", "paid", "deployed", "distributed", "returned", "capitalised", "capitalized")):
        return "EVENT_PERIOD"
    if source_value is not None and year > source_value and (
        module_name in FORWARD_TARGET_MODULES or module_name == "capital_allocations"
    ):
        return "TARGET_PERIOD"
    return "UNKNOWN"


def classify_temporal_references(
    text: str,
    *,
    source_year: Any = "",
    target_period: Any = "",
    module_name: str = "",
) -> List[Dict[str, Any]]:
    """Classify year-like tokens before the resolver decides chronology.

    raw_period remains a backward-compatible source field; downstream chronology
    should consume these semantic roles rather than treating every four-digit
    token as an event year.
    """
    normalized = _normalize_text(text)
    if not normalized:
        return []
    source_value = _source_year_value(source_year)
    target_value = _source_year_value(target_period)
    references: Dict[tuple[int, str], Dict[str, Any]] = {}

    for pattern in (FY_YEAR_RE, YEAR_RE):
        for match in pattern.finditer(normalized):
            raw = match.group("year") if "year" in pattern.groupindex else match.group(0)
            if not raw.isdigit():
                continue
            year = _year_value_from_match(raw)
            role = _role_from_year_context(
                text=normalized,
                match=match,
                year=year,
                source_value=source_value,
                target_value=target_value,
                module_name=module_name,
            )
            key = (year, role)
            if key not in references:
                references[key] = {
                    "year": year,
                    "period": _period_label_from_year(year),
                    "role": role,
                    "text": _window(normalized, *match.span()),
                }
    return sorted(references.values(), key=lambda item: (item["year"], item["role"]))


def temporal_years_from_text(
    text: str,
    *,
    source_year: Any = "",
    target_period: Any = "",
    module_name: str = "",
) -> List[int]:
    return sorted(
        {
            int(item["year"])
            for item in classify_temporal_references(
                text,
                source_year=source_year,
                target_period=target_period,
                module_name=module_name,
            )
            if item["role"] != "NON_TEMPORAL_REFERENCE"
        }
    )


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


def _period_label_from_year(value: int) -> str:
    return f"fy{str(value)[-2:]}"


def _temporal_roles(
    *,
    source_value: int,
    target_value: int | None = None,
    event_value: int | None = None,
    historical_values: Sequence[int] = (),
    references: Sequence[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    return {
        "source_period": _period_label_from_year(source_value),
        "event_period": _period_label_from_year(event_value or source_value),
        "target_period": _period_label_from_year(target_value) if target_value is not None else "",
        "historical_periods": [_period_label_from_year(year) for year in sorted(set(historical_values))],
        "references": list(references),
    }


def classify_business_relevance(
    text: str,
    *,
    module_name: str,
    actor_type: str = "",
    source_kind: str = "",
) -> Dict[str, Any]:
    """
    Four-outcome business relevance contract for investor intelligence:
    - KEEP: Core investor intelligence (material to economics/operations/capital/regulation/customer/continuity)
    - DEMOTE: Valid but secondary (contextual, supporting, low materiality) - keep in evidence layer, don't promote
    - QUARANTINE: Valid content but unsuitable for canonical investor intelligence (civic/CSR/public-interest/generic workforce)
    - HARD_FAIL: Malformed, contaminated, or fundamentally broken (audit boilerplate, empty, structural defects)

    Uses Company Model generically: offerings, customers, revenue engines, dependencies,
    economic drivers, operating model — no hardcoded companies/sectors.
    """
    normalized = _compact_lower(text)
    actor = _compact_lower(actor_type)
    source = _compact_lower(source_kind)
    basis: List[str] = []
    limitations: List[str] = []
    score = 0

    # HARD_FAIL: structural defects that make the item unusable
    if not normalized:
        return {
            "status": "ambiguous",
            "score": 0,
            "basis": ["empty text"],
            "limitations": ["no text to classify"],
            "quarantine": True,
            "outcome": "HARD_FAIL",
            "outcome_basis": ["empty or whitespace-only text"],
        }

    if any(term in normalized for term in HARD_FAIL_TERMS):
        return {
            "status": "out_of_scope",
            "score": -10,
            "basis": ["hard-fail term detected"],
            "limitations": ["audit/boilerplate/contaminated content"],
            "quarantine": True,
            "outcome": "HARD_FAIL",
            "outcome_basis": ["audit or boilerplate terminology indicates contaminated extraction"],
        }

    # External actor penalty
    if actor in {"government", "industry", "auditor"}:
        score -= 3
        basis.append(f"external actor: {actor}")

    # Civic/public-interest terms: strong QUARANTINE signal (beyond NON_CORE_TERMS)
    civic_matches = [term for term in CIVIC_PUBLIC_INTEREST_TERMS if term in normalized]
    if civic_matches:
        score -= 5
        basis.append(f"civic/public-interest terms: {', '.join(civic_matches[:3])}")
        limitations.append("civic or public-interest wording — not core investor intelligence")

    # Non-core terms (existing)
    non_core_matches = [term for term in NON_CORE_TERMS if term in normalized]
    if non_core_matches:
        score -= 3
        basis.append(f"non-core terms: {', '.join(non_core_matches[:3])}")

    # Business operations terms
    if any(term in normalized for term in BUSINESS_TERMS):
        score += 2
        basis.append("business-operations terms detected")

    # Module-specific risk terms
    if module_name == "risks" and any(term in normalized for term in RISK_TERMS):
        score += 1
        basis.append("risk-disclosure terms detected")

    # Module-specific core terms (Company Model: offerings, customers, revenue engines, dependencies, economic drivers, operating model)
    module_core = MODULE_CORE_TERMS.get(module_name, ())
    core_matches = [term for term in module_core if term in normalized]
    if core_matches:
        score += 2
        basis.append(f"module core terms: {', '.join(core_matches[:3])}")

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

    # Macro/policy penalty (except commentary and risks where policy risk is valid)
    if any(term in normalized for term in ("macro", "industry outlook", "global economy", "policy", "regulatory")) and module_name not in {"commentary", "risks"}:
        score -= 2
        limitations.append("macro or policy context should not drive core intelligence")

    # Status classification (existing scale)
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

    # Four-outcome decision
    # HARD_FAIL already handled above
    if status == "out_of_scope" or (civic_matches and status != "core"):
        # Civic/public-interest items that somehow scored >=1 still get QUARANTINED
        outcome = "QUARANTINE"
        quarantine = True
        if not limitations:
            limitations.append("item does not look like core investor intelligence")
    elif status == "ambiguous":
        outcome = "QUARANTINE"
        quarantine = True
        if not limitations:
            limitations.append("ambiguous relevance — cannot confirm investor materiality")
    elif status == "contextual" and module_name != "commentary":
        outcome = "DEMOTE"
        quarantine = True
        limitations.append("contextual item — not eligible for core intelligence stream")
    elif status == "supporting":
        outcome = "DEMOTE"
        quarantine = False
        limitations.append("valid but secondary — keep in evidence layer, do not promote to canonical")
    else:  # core
        outcome = "KEEP"
        quarantine = False

    return {
        "status": status,
        "score": score,
        "basis": basis,
        "limitations": limitations,
        "quarantine": quarantine,
        "outcome": outcome,
        "outcome_basis": [f"four-outcome contract: {outcome}"],
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
    temporal_references = classify_temporal_references(
        normalized_text,
        source_year=source_year,
        target_period=target_period,
        module_name=module_name,
    )
    years = [
        int(item["year"])
        for item in temporal_references
        if item["role"] != "NON_TEMPORAL_REFERENCE"
    ]
    if explicit_year not in (None, ""):
        explicit_text = _normalize_text(explicit_year)
        if explicit_text.lower().startswith("fy") or explicit_text.isdigit():
            explicit_references = classify_temporal_references(
                explicit_text,
                source_year=source_year,
                target_period=target_period,
                module_name=module_name,
            )
            temporal_references.extend(explicit_references)
            years.extend(
                int(item["year"])
                for item in explicit_references
                if item["role"] != "NON_TEMPORAL_REFERENCE"
            )
        elif explicit_text.isdigit() and len(explicit_text) == 4:
            years.append(int(explicit_text))
    target_value = _source_year_value(target_period)

    years = sorted(set(years))
    resolved_period = normalize_period_label(source_year)
    basis: List[str] = [f"source period {resolved_period}"]
    limitations: List[str] = []
    temporal_roles = _temporal_roles(source_value=source_value, references=temporal_references)

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
            "temporal_roles": temporal_roles,
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
            "temporal_roles": _temporal_roles(source_value=source_value, target_value=target_value if target_value > source_value else None, event_value=target_value if target_value <= source_value else None, references=temporal_references),
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
            "temporal_roles": _temporal_roles(source_value=source_value, target_value=target_value, event_value=source_value + 1, references=temporal_references),
        }

    if len(years) > 1:
        target_role_years = sorted(
            {
                int(item["year"])
                for item in temporal_references
                if item["role"] == "TARGET_PERIOD"
                and int(item["year"]) > source_value
                and _has_target_year_context(str(item.get("text") or ""))
            }
        )
        if len(target_role_years) == 1 and all(year <= source_value or year in target_role_years for year in years):
            historical_values = [year for year in years if year < source_value]
            return {
                "status": "RESOLVED",
                "resolved_period": resolved_period,
                "basis": basis
                + [
                    f"target period {target_role_years[0]} is semantically separated from source-period {module_name.replace('_', ' ') or 'evidence'} observation",
                    f"historical reference periods {', '.join(str(year) for year in historical_values)} do not replace source-period anchoring",
                ],
                "limitations": [],
                "temporal_roles": _temporal_roles(source_value=source_value, target_value=target_role_years[0], historical_values=historical_values, references=temporal_references),
            }
        if (
            module_name in FORWARD_TARGET_MODULES
            and target_value is not None
            and target_value > source_value
            and target_value in years
            and all(year < source_value or year == target_value for year in years)
        ):
            historical_values = [year for year in years if year < source_value]
            return {
                "status": "RESOLVED",
                "resolved_period": resolved_period,
                "basis": basis
                + [
                    f"target period {target_value} is explicitly separated from source period {source_value}",
                    f"historical reference periods {', '.join(str(year) for year in historical_values)} do not replace source-period anchoring",
                ],
                "limitations": [],
                "temporal_roles": _temporal_roles(source_value=source_value, target_value=target_value, historical_values=historical_values, references=temporal_references),
            }
        if (
            all(year <= source_value for year in years)
            and (_has_comparative_year_context(normalized_text) or _has_year_range_context(normalized_text))
        ):
            other_years = ", ".join(str(year) for year in years if year != source_value)
            if other_years:
                basis.append(f"comparative or historical years {other_years} are context for source period {resolved_period}")
            return {
                "status": "RESOLVED",
                "resolved_period": resolved_period,
                "basis": basis,
                "limitations": [],
                "temporal_roles": _temporal_roles(source_value=source_value, historical_values=[year for year in years if year < source_value], references=temporal_references),
            }
        if module_name == "capital_allocations" and source_value is not None:
            if source_value in years and all(source_value - 2 <= year <= source_value for year in years):
                return {
                    "status": "RESOLVED",
                    "resolved_period": resolved_period,
                    "basis": basis + [f"capital-allocation disclosure spanning {min(years)}-{max(years)} anchored to source year {source_value}"],
                    "limitations": [],
                    "temporal_roles": _temporal_roles(source_value=source_value, historical_values=[year for year in years if year < source_value], references=temporal_references),
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
                    "temporal_roles": _temporal_roles(source_value=source_value, historical_values=years, references=temporal_references),
                }
        failure_class = "SOURCE_PERIOD_VS_TARGET_PERIOD_CONFLICT" if source_value in years and target_value is not None and target_value in years and target_value != source_value else "PERIOD_RESOLUTION_UNSUPPORTED"
        return {
            "status": "AMBIGUOUS",
            "resolved_period": resolved_period,
            "basis": basis + [f"multiple years mentioned: {', '.join(str(year) for year in years)}"],
            "limitations": ["conflicting chronology"],
            "failure_class": failure_class,
            "temporal_roles": _temporal_roles(source_value=source_value, references=temporal_references),
        }

    explicit_value = years[0]
    gap = abs(explicit_value - source_value)
    if gap <= 1:
        return {
            "status": "RESOLVED",
            "resolved_period": resolved_period,
            "basis": basis + [f"explicit year {explicit_value} is within the adjacent analysis window of source year {source_value}"],
            "limitations": [],
            "temporal_roles": _temporal_roles(source_value=source_value, event_value=explicit_value, references=temporal_references),
        }
    if explicit_value > source_value and module_name in {"projects", "promises", "capacity_expansions", "management_commitments"}:
        return {
            "status": "RESOLVED",
            "resolved_period": resolved_period,
            "basis": basis + [f"future-dated explicit year {explicit_value} is valid for forward-looking {module_name.replace('_', ' ')} evidence"],
            "limitations": [],
            "temporal_roles": _temporal_roles(source_value=source_value, target_value=explicit_value, references=temporal_references),
        }
    if explicit_value > source_value and any(
        item["year"] == explicit_value and item["role"] == "TARGET_PERIOD"
        for item in temporal_references
    ):
        return {
            "status": "RESOLVED",
            "resolved_period": resolved_period,
            "basis": basis + [f"future target period {explicit_value} is separated from source-period {module_name.replace('_', ' ') or 'evidence'} observation"],
            "limitations": [],
            "temporal_roles": _temporal_roles(source_value=source_value, target_value=explicit_value, references=temporal_references),
        }
    if explicit_value < source_value:
        return {
            "status": "HISTORICAL_CONTEXT",
            "resolved_period": resolved_period,
            "basis": basis + [f"explicit year {explicit_value} predates source year {source_value}"],
            "limitations": ["historical context should remain evidence, not a new announcement"],
            "temporal_roles": _temporal_roles(source_value=source_value, historical_values=[explicit_value], references=temporal_references),
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
    relevance_outcome: str = "",
) -> Dict[str, Any]:
    """
    Assess progression materiality respecting the four-outcome contract.
    Items with QUARANTINE or HARD_FAIL outcomes should not be promoted.
    """
    normalized = _compact_lower(text)
    status_norm = _compact_lower(status_text)
    score = 0
    basis: List[str] = []
    limitations: List[str] = []

    # Respect four-outcome contract
    outcome = relevance_outcome.upper() if relevance_outcome else ""
    if outcome in {"QUARANTINE", "HARD_FAIL"}:
        # Quarantined or hard-fail items should not drive progression
        score -= 5
        limitations.append(f"relevance outcome: {outcome} — not eligible for progression promotion")
    elif relevance_status in {"core", "supporting"}:
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
    relevance_outcome = str(relevance.get("outcome") or "").upper()

    # Four-outcome contract drives validation
    if relevance_outcome == "HARD_FAIL":
        errors.append(f"business relevance outcome: {relevance_outcome} — structurally invalid")
    elif relevance_outcome == "QUARANTINE":
        errors.append(f"business relevance outcome: {relevance_outcome} — quarantined from investor intelligence")
    elif relevance_outcome == "DEMOTE":
        warnings.append(f"business relevance outcome: {relevance_outcome} — valid but secondary, not for canonical promotion")
    elif relevance.get("quarantine"):
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
