import json
import sys
from pathlib import Path
from collections import Counter
import re

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.context_paths import extraction_path, intelligence_path  # noqa: E402
from knowledge.cim import load_cim  # noqa: E402

INPUT_FILE = "company_intelligence.json"
OUTPUT_FILE = "management_summary.json"

SECTION_MAP = {
    "projects": "operations.projects",
    "promises": "management.promises",
    "capital_allocation": "financial.capital_allocation",
    "initiatives": "operations.initiatives",
    "risks": "risk.identified",
}

COMMENTARY_GROUP_KEYS = (
    "company_management_actions",
    "company_promises",
    "company_capabilities",
    "company_results",
    "risk_responses",
    "external_context",
    "accounting_disclosures",
    "governance_disclosures",
    "uncertain_items",
)

ARCHETYPE_DNA_IP_PLATFORM = {
    "IP Library",
    "Platform Monetization",
}

ARCHETYPE_DNA_SOFTWARE_PLATFORM = {
    "Enterprise Platform",
    "Compliance Infrastructure",
}

DIMENSION_PATTERNS = {
    "core_product": [
        ["product"],
        ["platform"],
        ["solution"],
        ["service"],
        ["offering"],
        ["channel"],
    ],
    "monetization_channel": [
        ["licensing"],
        ["license"],
        ["rights"],
        ["royalty"],
        ["streaming"],
        ["subscription"],
        ["distribution"],
        ["revenue", "share"],
        ["advertising"],
        ["audience"],
        ["content", "library"],
        ["catalogue"],
        ["catalog"],
    ],
    "platform_scale": [
        ["throughput"],
        ["volume"],
        ["scale"],
        ["capacity"],
        ["customer", "base"],
        ["deployment"],
        ["usage"],
        ["messages"],
    ],
    "customer_embeddedness": [
        ["customer", "retention"],
        ["workflow"],
        ["integration"],
        ["embedded"],
        ["adoption"],
        ["enterprise"],
        ["repeat", "usage"],
        ["customer", "success"],
    ],
    "compliance_trust": [
        ["compliance"],
        ["regulatory"],
        ["trust"],
        ["cybersecurity"],
        ["cyber", "resilience"],
        ["security", "assurance"],
        ["anti", "fraud"],
        ["anti", "spam"],
        ["anti", "phishing"],
        ["privacy"],
        ["security"],
        ["abuse", "prevention"],
        ["secure", "coding"],
        ["threat", "detection"],
        ["incident", "response"],
        ["vulnerability", "scanning"],
        ["penetration", "testing"],
        ["threat", "intelligence"],
        ["access", "control"],
        ["audit", "trail"],
        ["devsecops"],
        ["ssdlc"],
    ],
    "partner_distribution": [
        ["partnership"],
        ["partner"],
        ["operator"],
        ["telco"],
        ["ecosystem"],
        ["channel"],
        ["regional", "expansion"],
        ["market", "entry"],
        ["international"],
        ["export"],
    ],
    "capacity_expansion": [
        ["plant"],
        ["facility"],
        ["capacity"],
        ["expansion"],
        ["commissioning"],
        ["manufacturing"],
        ["wafer"],
        ["substrate"],
        ["fab"],
        ["production"],
    ],
    "capital_deployment": [
        ["capex"],
        ["capital", "allocation"],
        ["buyback"],
        ["dividend"],
        ["acquisition"],
        ["debt"],
        ["equity"],
        ["funding"],
        ["investment"],
    ],
    "product_differentiation": [
        ["patent"],
        ["innovation"],
        ["differentiation"],
        ["quality"],
        ["performance"],
        ["research"],
        ["r", "d"],
        ["design"],
    ],
    "operational_reliability": [
        ["automation"],
        ["observability"],
        ["active", "active"],
        ["reliability"],
        ["uptime"],
        ["resilience"],
        ["process", "improvement"],
        ["efficiency"],
        ["monitoring"],
        ["deployment"],
        ["ci", "cd"],
        ["continuous", "monitoring"],
        ["cloud", "security"],
        ["infrastructure"],
        ["patch", "management"],
        ["configuration", "validation"],
    ],
    "csr": [
        ["community"],
        ["school"],
        ["livelihood"],
        ["social"],
        ["csr"],
        ["education"],
        ["hunger"],
        ["rural", "development"],
        ["human", "rights"],
        ["inclusive", "workplace"],
    ],
    "hr": [
        ["compensation"],
        ["rewards"],
        ["employee", "engagement"],
        ["diversity"],
        ["inclusion"],
        ["leadership"],
        ["culture"],
        ["talent"],
        ["human", "resources"],
        ["onboarding"],
        ["induction"],
        ["buddy"],
        ["new", "hire"],
        ["employee"],
        ["employees"],
        ["training"],
        ["participation"],
        ["training", "calendar"],
        ["learning", "journey"],
        ["annual", "leave"],
        ["notice", "period"],
        ["pay", "framework"],
        ["wage", "benchmark"],
        ["work", "life", "balance"],
    ],
    "facilities": [
        ["commuting"],
        ["bus"],
        ["buses"],
        ["water"],
        ["landscaping"],
        ["biodiversity"],
        ["office"],
        ["paper", "reduction"],
        ["waste"],
        ["plastic"],
        ["garbage"],
        ["resource", "efficiency"],
        ["e", "waste"],
        ["renewable", "energy"],
    ],
    "admin": [
        ["reporting"],
        ["governance"],
        ["policy"],
        ["committee"],
        ["statutory"],
        ["documentation"],
        ["compliance", "filing"],
        ["esg", "council"],
        ["brsr"],
        ["net", "zero"],
        ["carbon", "neutrality"],
        ["decarbonisation", "roadmap"],
        ["sustainability", "roadmap"],
    ],
    "governance_boilerplate": [
        ["code", "of", "conduct"],
        ["board"],
        ["oversight"],
        ["governance", "framework"],
        ["internal", "control"],
    ],
}

ARCHETYPE_DIMENSION_WEIGHTS = {
    "ip_platform": {
        "core_product": 2,
        "monetization_channel": 4,
        "partner_distribution": 2,
        "product_differentiation": 1,
        "csr": -3,
        "hr": -3,
        "facilities": -3,
        "admin": -2,
        "governance_boilerplate": -2,
    },
    "software_platform": {
        "core_product": 2,
        "platform_scale": 4,
        "customer_embeddedness": 3,
        "compliance_trust": 4,
        "partner_distribution": 3,
        "product_differentiation": 2,
        "operational_reliability": 3,
        "csr": -3,
        "hr": -2,
        "facilities": -3,
        "admin": -2,
        "governance_boilerplate": -2,
    },
    "manufacturing": {
        "capacity_expansion": 4,
        "capital_deployment": 3,
        "product_differentiation": 2,
        "partner_distribution": 2,
        "operational_reliability": 2,
        "csr": -2,
        "hr": -2,
        "facilities": -2,
        "admin": -2,
        "governance_boilerplate": -2,
    },
}

PROMOTION_SCORE_THRESHOLDS = {
    "software_platform": {
        "project": 20,
        "initiative": 15,
        "promise": 10,
        "focus_area": 15,
    },
    "ip_platform": {
        "project": 1,
        "initiative": 1,
        "promise": 1,
        "focus_area": 1,
    },
    "manufacturing": {
        "project": 1,
        "initiative": 1,
        "promise": 1,
        "focus_area": 1,
    },
}


# ==========================================================
# Helpers
# ==========================================================

def _get_section_items(cim, section_path):

    node = cim

    for part in section_path.split("."):

        if not isinstance(node, dict):
            return []

        node = node.get(part, {})

    if isinstance(node, dict):
        return node.get("items", [])

    return []


def load_profile():

    cim = load_cim()

    profile = {}

    for key, section_path in SECTION_MAP.items():

        profile[key] = _get_section_items(
            cim,
            section_path,
        )

    profile["commentary"] = load_clean_commentary()

    return profile


def load_clean_commentary():
    commentary_path = extraction_path("clean_commentary.json")
    if not commentary_path.exists():
        return {key: [] for key in COMMENTARY_GROUP_KEYS}
    with open(commentary_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        return {key: [] for key in COMMENTARY_GROUP_KEYS}
    normalized = {key: list(payload.get(key, []) or []) for key in COMMENTARY_GROUP_KEYS}
    if "validation" in payload:
        normalized["validation"] = payload["validation"]
    return normalized


def load_business_context():

    classification_path = intelligence_path("business_classification.json")

    if not classification_path.exists():
        return {}

    with open(
        classification_path,
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)


def first_non_empty(item, fields):

    for field in fields:

        value = item.get(field)

        if value:
            return value

    return ""


def _normalize_text(value):

    normalized = re.sub(
        r"[^a-z0-9]+",
        " ",
        str(value or "").lower(),
    )

    return " ".join(
        normalized.split()
    )


def _matches_group(text, group):

    normalized_text = _normalize_text(text)
    tokens = set(
        normalized_text.split()
    )

    normalized_group = [
        _normalize_text(term)
        for term in group
        if _normalize_text(term)
    ]

    if not normalized_group:
        return False

    return all(
        term in normalized_text
        if " " in term
        else term in tokens
        for term in normalized_group
    )

def _dimension_hits(text):
    hits = Counter()
    for dimension, groups in DIMENSION_PATTERNS.items():
        for group in groups:
            if _matches_group(text, group):
                hits[dimension] += 1
    return hits


def _resolve_archetype_profiles(business_dnas):
    profiles = []
    if ARCHETYPE_DNA_IP_PLATFORM.intersection(business_dnas):
        profiles.append("ip_platform")
    if ARCHETYPE_DNA_SOFTWARE_PLATFORM.intersection(business_dnas):
        profiles.append("software_platform")
    if {"Manufacturing", "Semiconductor"}.intersection(business_dnas):
        profiles.append("manufacturing")
    return profiles


def _promotion_threshold(business_dnas, item_type):
    profiles = _resolve_archetype_profiles(business_dnas)
    thresholds = [
        PROMOTION_SCORE_THRESHOLDS.get(profile, {}).get(item_type, 1)
        for profile in profiles
    ]
    if not thresholds:
        return 1
    return max(thresholds)


def _structural_materiality_boost(item, item_type, dimensions):
    score = 0
    if item_type == "project":
        if dimensions["capacity_expansion"] or dimensions["core_product"] or dimensions["platform_scale"]:
            score += 2
    if item_type == "capital_allocation" and dimensions["capital_deployment"]:
        score += 3
    if item_type == "initiative" and (
        dimensions["core_product"]
        or dimensions["platform_scale"]
        or dimensions["monetization_channel"]
        or dimensions["compliance_trust"]
    ):
        score += 1
    return score


def _promise_materiality_adjustment(primary_dimensions, context_dimensions, business_dnas):
    profiles = _resolve_archetype_profiles(business_dnas)
    score = 0

    if "software_platform" in profiles:
        primary_business_signal = (
            primary_dimensions["core_product"]
            + primary_dimensions["platform_scale"]
            + primary_dimensions["customer_embeddedness"]
            + primary_dimensions["compliance_trust"]
            + primary_dimensions["operational_reliability"]
        )
        context_business_signal = (
            context_dimensions["compliance_trust"]
            + context_dimensions["operational_reliability"]
        )
        primary_noise_signal = (
            primary_dimensions["hr"]
            + primary_dimensions["csr"]
            + primary_dimensions["facilities"]
            + primary_dimensions["admin"]
            + primary_dimensions["governance_boilerplate"]
        )
        if primary_business_signal:
            score += primary_business_signal * 3
        if context_business_signal:
            score += context_business_signal
        if primary_noise_signal and not primary_business_signal:
            score -= primary_noise_signal * 5
        elif primary_noise_signal:
            score -= primary_noise_signal * 2
        if primary_noise_signal > primary_business_signal:
            score -= (primary_noise_signal - primary_business_signal) * 4

    return score


def _generic_penalties(item, item_type, normalized_text):
    score = 0
    project_name = _normalize_text(item.get("project_name"))
    description = _normalize_text(item.get("description"))

    if item_type == "project":
        if re.fullmatch(r"project \d+", project_name):
            score -= 5
        if "cwip" in description or "capital work in progress" in description:
            score -= 4
        if "intangible assets under development" in description:
            score -= 4
        if "under development" in description and not (
            "platform" in description
            or "product" in description
            or "facility" in description
            or "capacity" in description
        ):
            score -= 2

    if "generic" in normalized_text and "compliance" in normalized_text:
        score -= 1

    return score


def _score_item_for_context(item, text, business_dnas, item_type):
    normalized_text = _normalize_text(text)
    dimensions = _dimension_hits(normalized_text)
    profiles = _resolve_archetype_profiles(business_dnas)
    score = 0

    for profile in profiles:
        for dimension, weight in ARCHETYPE_DIMENSION_WEIGHTS.get(profile, {}).items():
            score += dimensions.get(dimension, 0) * weight

    score += _structural_materiality_boost(item, item_type, dimensions)
    score += _generic_penalties(item, item_type, normalized_text)

    return score, dimensions


def _score_promise_item(item, text, business_dnas):
    primary_text = " ".join(
        [
            text,
            str(item.get("category", "")),
            str(item.get("timeline", "")),
        ]
    )
    context_text = " ".join(
        [
            str(item.get("benefit", "")),
            str(item.get("description", "")),
            str(item.get("source_chunk", "")),
        ]
    )

    primary_score, primary_dimensions = _score_item_for_context(
        item,
        primary_text,
        business_dnas,
        "promise",
    )
    context_score, context_dimensions = _score_item_for_context(
        item,
        context_text,
        business_dnas,
        "promise",
    )

    score = primary_score + (context_score * 0.35)
    score += _promise_materiality_adjustment(
        primary_dimensions,
        context_dimensions,
        business_dnas,
    )

    return score, primary_dimensions


# ==========================================================
# Schema Mapping
# ==========================================================

from core.schemas import (
    PROJECT_NAME_FIELDS,
    PROMISE_FIELDS,
    INITIATIVE_FIELDS,
    CAPITAL_ACTION_FIELDS
)


CONTEXT_TYPE_COMPANY_ACTION = "company_action"
CONTEXT_TYPE_COMPANY_PROMISE = "company_promise"
CONTEXT_TYPE_COMPANY_CAPABILITY = "company_capability"
CONTEXT_TYPE_COMPANY_RESULT = "company_result"
CONTEXT_TYPE_COMPANY_RISK_RESPONSE = "company_risk_response"
CONTEXT_TYPE_EXTERNAL_CONTEXT = "external_context"
CONTEXT_TYPE_EXTERNAL_TAILWIND = "external_tailwind"
CONTEXT_TYPE_EXTERNAL_HEADWIND = "external_headwind"
CONTEXT_TYPE_ACCOUNTING_DISCLOSURE = "accounting_disclosure"
CONTEXT_TYPE_GOVERNANCE_DISCLOSURE = "governance_disclosure"
CONTEXT_TYPE_UNCERTAIN = "uncertain"

EXTERNAL_CONTEXT_TERMS = (
    "government",
    "policy",
    "budget",
    "fdi",
    "incentive",
    "regulation",
    "regulatory",
    "sector growth",
    "industry growth",
    "market demand",
    "macro",
    "macroeconomic",
    "gdp",
    "inflation",
    "interest rate",
    "industry licensing",
    "national target",
    "fiscal support",
    "public spending",
)

EXTERNAL_TAILWIND_TERMS = (
    "benefit from",
    "tailwind",
    "supportive",
    "favorable",
    "strong demand",
    "incentive",
    "policy support",
)

EXTERNAL_HEADWIND_TERMS = (
    "headwind",
    "slowdown",
    "pressure",
    "tightening",
    "volatility",
    "uncertainty",
    "adverse",
)

COMPANY_ACTION_TERMS = (
    "commissioned",
    "launched",
    "expanded",
    "installed",
    "implemented",
    "established",
    "built",
    "invested",
    "deployed",
    "opened",
    "introduced",
    "developed",
    "upgraded",
)

PROMISE_TERMS = (
    "plans to",
    "aims to",
    "will",
    "target",
    "intends to",
    "expects to",
    "exploring",
    "roadmap",
    "commit",
)

RESULT_TERMS = (
    "achieved",
    "improved",
    "grew",
    "reached",
    "delivered",
    "completed",
    "commissioned",
    "order inflow",
    "shipment",
    "exported",
)

CAPABILITY_TERMS = (
    "capability",
    "certified",
    "certification",
    "facility",
    "platform",
    "system",
    "process",
    "workforce",
    "team",
    "infrastructure",
)

RISK_RESPONSE_TERMS = (
    "mitigate",
    "hedge",
    "monitor",
    "control",
    "reduce risk",
    "response plan",
    "risk management",
    "business continuity",
    "resilience",
)

ACCOUNTING_DISCLOSURE_TERMS = (
    "depreciation",
    "useful life",
    "impairment",
    "fair value",
    "actuarial",
    "accounting policy",
    "significant accounting policies",
    "accounting estimate",
)

GOVERNANCE_DISCLOSURE_TERMS = (
    "board",
    "audit committee",
    "committee",
    "section 177",
    "section 185",
    "section 186",
    "shareholder approval",
    "code of conduct",
    "internal controls",
    "compliance with provisions",
)


# ==========================================================
# Summary Builders
# ==========================================================

def summarize_projects(profile):

    projects = []

    for item in profile.get(
        "projects",
        []
    ):

        project = first_non_empty(
            item,
            PROJECT_NAME_FIELDS
        )

        if project:
            projects.append(project)

    return projects


def summarize_promises(profile):

    promises = []

    for item in profile.get(
        "promises",
        []
    ):

        promise = first_non_empty(
            item,
            PROMISE_FIELDS
        )

        if promise:
            promises.append(promise)

    return promises


def summarize_initiatives(profile):

    initiatives = []

    for item in profile.get(
        "initiatives",
        []
    ):

        initiative = first_non_empty(
            item,
            INITIATIVE_FIELDS
        )

        if initiative:
            initiatives.append(initiative)

    return initiatives


def summarize_capital(profile):

    actions = []

    for item in profile.get(
        "capital_allocation",
        []
    ):

        action = first_non_empty(
            item,
            CAPITAL_ACTION_FIELDS
        )

        if action:
            actions.append(action)

    return actions


def extract_focus_areas(profile):
    return []


def _rank_items(
    items,
    fields,
    business_dnas,
    item_type,
):

    ranked = []

    for item in items:
        text = first_non_empty(item, fields)
        if not text:
            continue

        combined_text = " ".join(
            [
                text,
                str(item.get("category", "")),
                str(item.get("benefit", "")),
                str(item.get("description", "")),
                str(item.get("source_chunk", "")),
            ]
        )

        if item_type == "promise":
            score, _ = _score_promise_item(
                item,
                text,
                business_dnas,
            )
        else:
            score, _ = _score_item_for_context(
                item,
                combined_text,
                business_dnas,
                item_type,
            )

        ranked.append(
            (score, text, combined_text)
        )

    ranked.sort(
        key=lambda value: (
            value[0],
            value[1],
        ),
        reverse=True,
    )

    if ARCHETYPE_DNA_IP_PLATFORM.intersection(business_dnas):
        minimum_score = _promotion_threshold(business_dnas, item_type)
        positive_ranked = [
            text
            for score, text, _ in ranked
            if score >= minimum_score
        ]
        if positive_ranked:
            return _dedupe_ranked_texts(positive_ranked)
        if item_type == "project":
            return []

    if ARCHETYPE_DNA_SOFTWARE_PLATFORM.intersection(business_dnas):
        minimum_score = _promotion_threshold(business_dnas, item_type)
        positive_ranked = [
            text
            for score, text, _ in ranked
            if score >= minimum_score
        ]
        if positive_ranked:
            return _dedupe_ranked_texts(positive_ranked)
        if item_type == "project":
            return []

    return _dedupe_ranked_texts([
        text
        for _, text, _ in ranked
    ])


def _group_management_context(profile):
    grouped = {key: [] for key in COMMENTARY_GROUP_KEYS}

    commentary_groups = profile.get("commentary")
    if isinstance(commentary_groups, dict):
        for key in COMMENTARY_GROUP_KEYS:
            for item in commentary_groups.get(key, []) or []:
                if isinstance(item, dict) and item.get("value"):
                    grouped[key].append(dict(item))

    source_map = {
        "project": (profile.get("projects", []), PROJECT_NAME_FIELDS),
        "promise": (profile.get("promises", []), PROMISE_FIELDS),
        "initiative": (profile.get("initiatives", []), INITIATIVE_FIELDS),
        "capital_allocation": (profile.get("capital_allocation", []), CAPITAL_ACTION_FIELDS),
    }

    for item_type, (items, fields) in source_map.items():
        for item in items:
            value = first_non_empty(item, fields)
            if not value:
                continue
            classified = _classify_management_item(item, item_type, value)
            context_type = classified["context_type"]
            if context_type == CONTEXT_TYPE_COMPANY_ACTION:
                grouped["company_management_actions"].append(classified)
            elif context_type == CONTEXT_TYPE_COMPANY_PROMISE:
                grouped["company_promises"].append(classified)
            elif context_type == CONTEXT_TYPE_COMPANY_CAPABILITY:
                grouped["company_capabilities"].append(classified)
            elif context_type == CONTEXT_TYPE_COMPANY_RESULT:
                grouped["company_results"].append(classified)
            elif context_type == CONTEXT_TYPE_COMPANY_RISK_RESPONSE:
                grouped["risk_responses"].append(classified)
            elif context_type in {
                CONTEXT_TYPE_EXTERNAL_CONTEXT,
                CONTEXT_TYPE_EXTERNAL_TAILWIND,
                CONTEXT_TYPE_EXTERNAL_HEADWIND,
            }:
                grouped["external_context"].append(classified)
            elif context_type == CONTEXT_TYPE_ACCOUNTING_DISCLOSURE:
                grouped["accounting_disclosures"].append(classified)
            elif context_type == CONTEXT_TYPE_GOVERNANCE_DISCLOSURE:
                grouped["governance_disclosures"].append(classified)
            else:
                grouped["uncertain_items"].append(classified)

            shadow = _external_shadow_item(classified)
            if shadow is not None:
                grouped["external_context"].append(shadow)

    for key in COMMENTARY_GROUP_KEYS:
        grouped[key] = _dedupe_grouped_items(grouped[key])

    return grouped


def _dedupe_grouped_items(items):
    deduped = []
    seen = set()
    for item in items:
        key = (
            item.get("context_type"),
            _canonical_text_key(item.get("value")),
            _canonical_text_key(item.get("category")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _filter_items_by_values(items, fields, allowed_values):
    allowed = {_canonical_text_key(value) for value in allowed_values}
    if not allowed:
        return []
    filtered = []
    for item in items:
        text = first_non_empty(item, fields)
        if text and _canonical_text_key(text) in allowed:
            filtered.append(item)
    return filtered


def _extract_ranked_focus_areas(
    initiatives,
    business_dnas,
):

    category_scores = Counter()

    for item in initiatives:
        category = item.get("category", "")
        if not category:
            continue

        combined_text = " ".join(
            [
                category,
                str(item.get("initiative", "")),
                str(item.get("benefit", "")),
                str(item.get("source_chunk", "")),
            ]
        )

        score, _ = _score_item_for_context(
            item,
            combined_text,
            business_dnas,
            "initiative",
        )

        category_scores[category] += score if score != 0 else 1

    ranked = sorted(
        category_scores.items(),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )

    if ARCHETYPE_DNA_IP_PLATFORM.intersection(business_dnas) or ARCHETYPE_DNA_SOFTWARE_PLATFORM.intersection(business_dnas):
        minimum_score = _promotion_threshold(business_dnas, "focus_area")
        ranked = [
            item
            for item in ranked
            if item[1] >= minimum_score
        ]

    return _dedupe_ranked_texts([
        category
        for category, _ in ranked
    ])


def _commentary_focus_areas(grouped_context):
    categories = []
    for section in (
        "company_management_actions",
        "company_promises",
        "company_capabilities",
        "company_results",
        "risk_responses",
    ):
        for item in grouped_context.get(section, []):
            category = item.get("category")
            if category:
                categories.append(category)
    return _dedupe_ranked_texts(categories)


def _canonical_text_key(text):
    normalized = _normalize_text(text)
    tokens = [
        token
        for token in normalized.split()
        if token not in {"the", "and", "for", "with", "of", "to", "in", "a", "an"}
    ]
    return " ".join(tokens)


def _is_alias_of_longer(short_text, long_text):
    short_key = _canonical_text_key(short_text)
    long_key = _canonical_text_key(long_text)
    if not short_key or not long_key or short_key == long_key:
        return False
    short_tokens = short_key.split()
    long_tokens = long_key.split()
    if len(short_tokens) >= len(long_tokens):
        return False
    if short_key in long_key:
        return True
    return all(token in long_tokens for token in short_tokens) and len(short_tokens) <= 3


def _dedupe_ranked_texts(values):
    deduped = []
    for value in values:
        if not value:
            continue
        if any(_canonical_text_key(value) == _canonical_text_key(existing) for existing in deduped):
            continue
        if any(_is_alias_of_longer(value, existing) for existing in deduped):
            continue
        deduped = [
            existing
            for existing in deduped
            if not _is_alias_of_longer(existing, value)
        ]
        deduped.append(value)
    return deduped


def _contains_any(text, terms):
    return any(term in text for term in terms)


def _extract_evidence_ids(item):
    existing = list(item.get("evidence_ids", []) or [])
    if existing:
        return list(dict.fromkeys(existing))
    evidence_ids = []
    for observation in item.get("observations", []) or []:
        for evidence in observation.get("evidence", []) or []:
            evidence_id = evidence.get("id")
            if evidence_id:
                evidence_ids.append(evidence_id)
    return list(dict.fromkeys(evidence_ids))


def _item_confidence(item):
    return str(item.get("confidence") or "").lower() or "unknown"


def _summary_item(
    item,
    *,
    value,
    item_type,
    context_type,
    agency,
    reasoning,
    should_feed_management_consistency,
    should_feed_company_strategy,
    should_feed_external_context,
):
    return {
        "value": value,
        "item_type": item_type,
        "category": item.get("category"),
        "context_type": context_type,
        "agency": agency,
        "should_feed_management_consistency": should_feed_management_consistency,
        "should_feed_company_strategy": should_feed_company_strategy,
        "should_feed_external_context": should_feed_external_context,
        "reasoning": reasoning,
        "evidence_ids": _extract_evidence_ids(item),
        "confidence": _item_confidence(item),
        "source_item_id": item.get("id"),
        "status": item.get("status"),
        "actor": item.get("actor"),
        "time_reference": item.get("time_reference"),
        "amount": item.get("amount"),
        "currency": item.get("currency"),
        "evidence_quality": item.get("evidence_quality"),
        "uncertainty_reason": item.get("uncertainty_reason"),
    }


def _classify_management_item(item, item_type, value):
    normalized = _normalize_text(
        " ".join(
            [
                str(value or ""),
                str(item.get("category", "")),
                str(item.get("benefit", "")),
                str(item.get("description", "")),
                str(item.get("purpose", "")),
                str(item.get("timeline", "")),
                str(item.get("source_chunk", "")),
            ]
        )
    )

    has_external = _contains_any(normalized, EXTERNAL_CONTEXT_TERMS)
    has_tailwind = _contains_any(normalized, EXTERNAL_TAILWIND_TERMS)
    has_headwind = _contains_any(normalized, EXTERNAL_HEADWIND_TERMS)
    has_action = _contains_any(normalized, COMPANY_ACTION_TERMS)
    has_promise = item_type == "promise" or _contains_any(normalized, PROMISE_TERMS)
    has_result = _contains_any(normalized, RESULT_TERMS)
    has_capability = _contains_any(normalized, CAPABILITY_TERMS)
    has_risk_response = _contains_any(normalized, RISK_RESPONSE_TERMS)
    has_accounting = _contains_any(normalized, ACCOUNTING_DISCLOSURE_TERMS)
    has_governance = _contains_any(normalized, GOVERNANCE_DISCLOSURE_TERMS)

    if has_accounting:
        return _summary_item(
            item,
            value=value,
            item_type=item_type,
            context_type=CONTEXT_TYPE_ACCOUNTING_DISCLOSURE,
            agency="company_controlled",
            reasoning="Detected accounting-policy or disclosure language rather than management execution.",
            should_feed_management_consistency=False,
            should_feed_company_strategy=False,
            should_feed_external_context=False,
        )

    if has_governance and not _contains_any(
        normalized,
        ("commissioned", "launched", "expanded", "implemented", "built", "deployed", "invested"),
    ):
        return _summary_item(
            item,
            value=value,
            item_type=item_type,
            context_type=CONTEXT_TYPE_GOVERNANCE_DISCLOSURE,
            agency="company_controlled",
            reasoning="Detected governance or compliance disclosure without a clear execution theme.",
            should_feed_management_consistency=False,
            should_feed_company_strategy=False,
            should_feed_external_context=False,
        )

    if has_external and not (has_action or has_promise or has_capability or has_risk_response):
        context_type = CONTEXT_TYPE_EXTERNAL_CONTEXT
        if has_tailwind:
            context_type = CONTEXT_TYPE_EXTERNAL_TAILWIND
        elif has_headwind:
            context_type = CONTEXT_TYPE_EXTERNAL_HEADWIND
        return _summary_item(
            item,
            value=value,
            item_type=item_type,
            context_type=context_type,
            agency="external_not_controlled",
            reasoning="Detected macro, policy, regulatory, or industry backdrop without a company-controlled action.",
            should_feed_management_consistency=False,
            should_feed_company_strategy=False,
            should_feed_external_context=True,
        )

    if has_external and has_result and not _contains_any(normalized, ("company", "management")):
        return _summary_item(
            item,
            value=value,
            item_type=item_type,
            context_type=CONTEXT_TYPE_EXTERNAL_CONTEXT,
            agency="external_not_controlled",
            reasoning="Detected macro or policy outcome language without a company actor.",
            should_feed_management_consistency=False,
            should_feed_company_strategy=False,
            should_feed_external_context=True,
        )

    if has_promise:
        return _summary_item(
            item,
            value=value,
            item_type=item_type,
            context_type=CONTEXT_TYPE_COMPANY_PROMISE,
            agency="management_committed" if not has_external else "mixed",
            reasoning="Detected forward-looking management commitment or stated intent.",
            should_feed_management_consistency=True,
            should_feed_company_strategy=True,
            should_feed_external_context=has_external,
        )

    if has_risk_response:
        return _summary_item(
            item,
            value=value,
            item_type=item_type,
            context_type=CONTEXT_TYPE_COMPANY_RISK_RESPONSE,
            agency="company_controlled" if not has_external else "mixed",
            reasoning="Detected company-controlled mitigation, monitoring, or resilience action.",
            should_feed_management_consistency=True,
            should_feed_company_strategy=True,
            should_feed_external_context=has_external,
        )

    if has_result:
        return _summary_item(
            item,
            value=value,
            item_type=item_type,
            context_type=CONTEXT_TYPE_COMPANY_RESULT,
            agency="company_controlled" if not has_external else "mixed",
            reasoning="Detected delivered outcome, achieved result, or completed company milestone.",
            should_feed_management_consistency=True,
            should_feed_company_strategy=True,
            should_feed_external_context=has_external,
        )

    if has_action or item_type in {"project", "capital_allocation"}:
        return _summary_item(
            item,
            value=value,
            item_type=item_type,
            context_type=CONTEXT_TYPE_COMPANY_ACTION,
            agency="company_controlled" if not has_external else "mixed",
            reasoning="Detected company-controlled action, buildout, deployment, or capital decision.",
            should_feed_management_consistency=True,
            should_feed_company_strategy=True,
            should_feed_external_context=has_external,
        )

    if has_capability or item_type == "initiative":
        return _summary_item(
            item,
            value=value,
            item_type=item_type,
            context_type=CONTEXT_TYPE_COMPANY_CAPABILITY,
            agency="company_controlled" if not has_external else "mixed",
            reasoning="Detected company capability, process, facility, or operating-system attribute.",
            should_feed_management_consistency=True,
            should_feed_company_strategy=True,
            should_feed_external_context=has_external,
        )

    return _summary_item(
        item,
        value=value,
        item_type=item_type,
        context_type=CONTEXT_TYPE_UNCERTAIN,
        agency="uncertain",
        reasoning="Could not determine whether the item is company-controlled action or external backdrop.",
        should_feed_management_consistency=False,
        should_feed_company_strategy=False,
        should_feed_external_context=False,
    )


def _external_shadow_item(classified_item):
    if not classified_item.get("should_feed_external_context"):
        return None
    if classified_item.get("context_type") in {
        CONTEXT_TYPE_EXTERNAL_CONTEXT,
        CONTEXT_TYPE_EXTERNAL_TAILWIND,
        CONTEXT_TYPE_EXTERNAL_HEADWIND,
    }:
        return None
    context_type = CONTEXT_TYPE_EXTERNAL_CONTEXT
    reasoning = "Preserved external backdrop separately from the primary company-controlled item because the text mixes company action with outside context."
    normalized = _normalize_text(classified_item.get("value"))
    if _contains_any(normalized, EXTERNAL_TAILWIND_TERMS):
        context_type = CONTEXT_TYPE_EXTERNAL_TAILWIND
    elif _contains_any(normalized, EXTERNAL_HEADWIND_TERMS):
        context_type = CONTEXT_TYPE_EXTERNAL_HEADWIND
    shadow = dict(classified_item)
    shadow["context_type"] = context_type
    shadow["agency"] = "mixed"
    shadow["should_feed_management_consistency"] = False
    shadow["should_feed_company_strategy"] = False
    shadow["should_feed_external_context"] = True
    shadow["reasoning"] = reasoning
    return shadow


def _validate_grouped_summary(summary):
    errors = []
    warnings = []
    grouped_sections = (
        "company_management_actions",
        "company_promises",
        "company_capabilities",
        "company_results",
        "risk_responses",
        "external_context",
        "accounting_disclosures",
        "governance_disclosures",
        "uncertain_items",
    )

    for section in grouped_sections:
        for item in summary.get(section, []):
            value = item.get("value") or "unknown item"
            if not item.get("context_type"):
                errors.append(f"{value}: missing context_type")
            if not item.get("agency"):
                errors.append(f"{value}: missing agency")
            if item.get("context_type", "").startswith("external_") and item.get("should_feed_management_consistency"):
                if item.get("agency") != "mixed" or "mixed" not in str(item.get("reasoning", "")).lower():
                    errors.append(f"{value}: external context cannot feed management consistency without explicit mixed-agency reason")
            if item.get("context_type") == CONTEXT_TYPE_ACCOUNTING_DISCLOSURE and item.get("should_feed_company_strategy"):
                errors.append(f"{value}: accounting disclosure cannot feed company strategy")
            if item.get("source_chunk"):
                errors.append(f"{value}: source_chunk must not appear in management_summary grouped output")
            if item.get("context_type") == CONTEXT_TYPE_UNCERTAIN:
                warnings.append(f"{value}: context_type uncertain")
            if item.get("agency") == "uncertain":
                warnings.append(f"{value}: agency uncertain")
            if str(item.get("confidence") or "").lower() in {"", "low"}:
                warnings.append(f"{value}: low confidence")
            if item.get("value") and "budget allocation" in _normalize_text(item.get("value")) and item.get("agency") == "uncertain":
                warnings.append(f"{value}: vague budget allocation label without company actor")

    summary["routing_validation"] = {
        "status": "pass" if not errors else "fail",
        "errors": list(dict.fromkeys(errors)),
        "warnings": list(dict.fromkeys(warnings)),
    }
    if errors:
        raise ValueError("Management summary context validation failed: " + "; ".join(summary["routing_validation"]["errors"]))

    return summary


# ==========================================================
# Main Summary
# ==========================================================

def build_summary(profile, business_context=None):

    business_context = business_context or {}
    business_dnas = set(
        business_context.get("business_dnas", [])
    )
    grouped_context = _group_management_context(profile)

    company_project_items = _filter_items_by_values(
        profile.get("projects", []),
        PROJECT_NAME_FIELDS,
        [item["value"] for item in grouped_context["company_management_actions"] + grouped_context["company_results"]],
    )
    company_promise_items = _filter_items_by_values(
        profile.get("promises", []),
        PROMISE_FIELDS,
        [item["value"] for item in grouped_context["company_promises"]],
    )
    company_initiative_items = _filter_items_by_values(
        profile.get("initiatives", []),
        INITIATIVE_FIELDS,
        [
            item["value"]
            for item in grouped_context["company_management_actions"]
            + grouped_context["company_capabilities"]
            + grouped_context["company_results"]
            + grouped_context["risk_responses"]
        ],
    )
    company_capital_items = _filter_items_by_values(
        profile.get("capital_allocation", []),
        CAPITAL_ACTION_FIELDS,
        [item["value"] for item in grouped_context["company_management_actions"] + grouped_context["company_results"]],
    )

    projects = _rank_items(
        company_project_items,
        PROJECT_NAME_FIELDS,
        business_dnas,
        "project",
    )

    promises = _rank_items(
        company_promise_items,
        PROMISE_FIELDS,
        business_dnas,
        "promise",
    )

    initiatives = _rank_items(
        company_initiative_items,
        INITIATIVE_FIELDS,
        business_dnas,
        "initiative",
    )

    capital_actions = _rank_items(
        company_capital_items,
        CAPITAL_ACTION_FIELDS,
        business_dnas,
        "capital_allocation",
    )

    focus_areas = _extract_ranked_focus_areas(
        company_initiative_items,
        business_dnas,
    )
    focus_areas = _dedupe_ranked_texts(
        focus_areas + _commentary_focus_areas(grouped_context)
    )

    summary = {

        "management_focus_areas":
            focus_areas,

        "major_projects":
            projects,

        "major_promises":
            promises,

        "key_initiatives":
            initiatives,

        "capital_allocation_actions":
            capital_actions,

        "statistics": {

            "project_count":
                len(projects),

            "promise_count":
                len(promises),

            "initiative_count":
                len(initiatives),

            "capital_action_count":
                len(capital_actions)
        }
    }

    summary.update(grouped_context)

    return _validate_grouped_summary(summary)


def print_summary(summary):

    print("\n" + "=" * 60)
    print("MANAGEMENT SUMMARY")
    print("=" * 60)

    print("\nFocus Areas:")

    for area in summary[
        "management_focus_areas"
    ]:

        print(f"- {area}")

    stats = summary["statistics"]

    print("\nStatistics:")
    print(
        f"Projects: {stats['project_count']}"
    )
    print(
        f"Promises: {stats['promise_count']}"
    )
    print(
        f"Initiatives: {stats['initiative_count']}"
    )
    print(
        f"Capital Actions: {stats['capital_action_count']}"
    )


def main():

    profile = load_profile()
    business_context = load_business_context()

    summary = build_summary(
        profile,
        business_context=business_context,
    )

    with open(
        intelligence_path(OUTPUT_FILE),
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            summary,
            f,
            indent=2,
            ensure_ascii=False
        )

    print_summary(
        summary
    )

    print(
        f"\nSaved: {intelligence_path(OUTPUT_FILE)}"
    )


if __name__ == "__main__":
    main()
