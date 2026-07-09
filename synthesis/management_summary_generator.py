import json
import sys
from pathlib import Path
from collections import Counter
import re

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.context_paths import intelligence_path  # noqa: E402
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

    return profile


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


# ==========================================================
# Main Summary
# ==========================================================

def build_summary(profile, business_context=None):

    business_context = business_context or {}
    business_dnas = set(
        business_context.get("business_dnas", [])
    )

    projects = _rank_items(
        profile.get("projects", []),
        PROJECT_NAME_FIELDS,
        business_dnas,
        "project",
    )

    promises = _rank_items(
        profile.get("promises", []),
        PROMISE_FIELDS,
        business_dnas,
        "promise",
    )

    initiatives = _rank_items(
        profile.get("initiatives", []),
        INITIATIVE_FIELDS,
        business_dnas,
        "initiative",
    )

    capital_actions = _rank_items(
        profile.get("capital_allocation", []),
        CAPITAL_ACTION_FIELDS,
        business_dnas,
        "capital_allocation",
    )

    focus_areas = _extract_ranked_focus_areas(
        profile.get("initiatives", []),
        business_dnas,
    )

    return {

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
