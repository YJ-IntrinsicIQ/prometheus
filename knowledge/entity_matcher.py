"""
Generic entity matching for the Prometheus Canonical Intelligence
Model (PCIM).

This module determines whether an extracted entity already exists
inside the Company Intelligence Model.

Version 1:
- Deterministic text normalization
- SequenceMatcher similarity
- Generic (driven entirely by ENTITY_CONFIG)

Future versions may replace the similarity engine with embeddings
without changing the public API.
"""

import re
from difflib import SequenceMatcher

from .constants import ENTITY_CONFIG


DEFAULT_THRESHOLD = 0.85


# ============================================================
# Stop Words
# ============================================================

STOP_WORDS = {
    "the",
    "and",
    "for",
    "of",
    "to",
    "at",
    "in",
    "on",
    "by",
    "new",
    "company",
    "project",
    "facility",
    "plant",
    "unit",
    "phase",
}


# ============================================================
# Name Helpers
# ============================================================

def get_name_field(entity_type):

    if entity_type not in ENTITY_CONFIG:

        raise ValueError(
            f"Unknown entity type: {entity_type}"
        )

    return ENTITY_CONFIG[entity_type]["name_field"]


def get_entity_name(entity_type, entity):

    field = get_name_field(entity_type)

    if field is None:
        return ""

    return str(
        entity.get(field, "")
    )


# ============================================================
# Normalization
# ============================================================

def normalize(text):

    if not text:
        return ""

    text = text.lower()

    text = re.sub(
        r"[^\w\s]",
        " ",
        text,
    )

    words = [

        word

        for word in text.split()

        if word not in STOP_WORDS

    ]

    words.sort()

    return " ".join(words)


# ============================================================
# Similarity
# ============================================================

def similarity(text1, text2):

    text1 = normalize(text1)
    text2 = normalize(text2)

    if not text1 or not text2:
        return 0.0

    return SequenceMatcher(
        None,
        text1,
        text2,
    ).ratio()


# ============================================================
# Matching
# ============================================================

def is_same_entity(
    entity_type,
    entity1,
    entity2,
    threshold=DEFAULT_THRESHOLD,
):

    score = similarity(

        get_entity_name(
            entity_type,
            entity1,
        ),

        get_entity_name(
            entity_type,
            entity2,
        ),
    )

    return score >= threshold


def find_matching_entity(
    entity_type,
    entities,
    candidate,
    threshold=DEFAULT_THRESHOLD,
):
    """
    Returns the matching entity or None.
    """

    candidate_name = get_entity_name(
        entity_type,
        candidate,
    )

    best_entity = None
    best_score = 0.0

    for entity in entities:

        score = similarity(

            get_entity_name(
                entity_type,
                entity,
            ),

            candidate_name,
        )

        if score > best_score:

            best_score = score
            best_entity = entity

    if best_score >= threshold:
        return best_entity

    return None


# ============================================================
# Merge
# ============================================================

def merge_entities(existing, candidate):
    """
    Existing values win unless missing.

    Observations are handled by the CIM,
    not by the matcher.
    """

    merged = existing.copy()

    for key, value in candidate.items():

        if key == "observations":
            continue

        if value in (
            None,
            "",
            [],
            {},
        ):
            continue

        if key not in merged:

            merged[key] = value
            continue

        if merged[key] in (
            None,
            "",
            [],
            {},
        ):

            merged[key] = value

    return merged


# ============================================================
# Upsert
# ============================================================

def upsert_entity(
    entity_type,
    entities,
    candidate,
    threshold=DEFAULT_THRESHOLD,
):
    """
    Finds an existing entity.

    If found:
        Merge.

    Otherwise:
        Insert.

    Returns:

        entity,
        created(bool)
    """

    existing = find_matching_entity(
        entity_type,
        entities,
        candidate,
        threshold,
    )

    if existing is None:

        entities.append(candidate)

        return candidate, True

    merged = merge_entities(
        existing,
        candidate,
    )

    index = entities.index(existing)

    entities[index] = merged

    return merged, False