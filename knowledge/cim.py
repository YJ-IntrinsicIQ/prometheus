import json
from copy import deepcopy
from datetime import datetime

from core.context_paths import intelligence_path

from .cim_schema import create_empty_cim
from .constants import (
    ITEMS,
    STATISTICS,
    OBSERVATIONS,
)

CIM_FILE = "company_intelligence.json"


# ============================================================
# Utilities
# ============================================================

def utc_now():

    return (
        datetime.utcnow()
        .isoformat(timespec="seconds")
        + "Z"
    )


def _parts(path):

    return path.split(".")


# ============================================================
# Lifecycle
# ============================================================

def initialize_cim():

    return create_empty_cim()


def load_cim():

    path = intelligence_path(CIM_FILE)

    if not path.exists():
        return initialize_cim()

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def save_cim(cim):

    cim["metadata"]["updated_at"] = utc_now()

    path = intelligence_path(CIM_FILE)

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            cim,
            f,
            indent=2,
            ensure_ascii=False,
        )

    return path


# ============================================================
# Navigation
# ============================================================

def get_section(
    cim,
    section,
):

    node = cim

    for part in _parts(section):
        node = node[part]

    return node


def update_section(
    cim,
    section,
    value,
):

    node = cim

    parts = _parts(section)

    for part in parts[:-1]:
        node = node[part]

    node[parts[-1]] = value

    return cim


# ============================================================
# Entity Helpers
# ============================================================

def create_entity(
    entity,
):
    """
    Ensure every entity has the
    canonical structure.
    """

    result = deepcopy(entity)

    result.setdefault(
        "observations",
        []
    )

    result.setdefault(
        "metadata",
        {}
    )

    result.setdefault(
        "relationships",
        []
    )

    result.setdefault(
        "confidence",
        "medium"
    )

    return result


def append_entity(
    cim,
    section,
    entity,
):

    bucket = get_section(
        cim,
        section,
    )

    entity = create_entity(
        entity
    )

    bucket[ITEMS].append(
        entity
    )

    return entity


def find_entity(
    cim,
    section,
    entity_id,
):

    bucket = get_section(
        cim,
        section,
    )

    for entity in bucket[ITEMS]:

        if entity.get("id") == entity_id:
            return entity

    return None


def find_entity_by(
    cim,
    section,
    field,
    value,
):

    bucket = get_section(
        cim,
        section,
    )

    for entity in bucket[ITEMS]:

        if entity.get(field) == value:
            return entity

    return None


def upsert_entity(
    cim,
    section,
    entity,
):

    bucket = get_section(
        cim,
        section,
    )

    entity = create_entity(
        entity
    )

    entity_id = entity.get("id")

    if entity_id is None:

        bucket[ITEMS].append(
            entity
        )

        return entity

    for index, existing in enumerate(bucket[ITEMS]):

        if existing["id"] == entity_id:

            merged = deepcopy(existing)

            for key, value in entity.items():

                if key == OBSERVATIONS:
                    continue

                merged[key] = value

            merged[OBSERVATIONS].extend(
                entity.get(
                    OBSERVATIONS,
                    []
                )
            )

            bucket[ITEMS][index] = merged

            return merged

    bucket[ITEMS].append(
        entity
    )

    return entity


# ============================================================
# Observation Helpers
# ============================================================

def add_observation(
    cim,
    section,
    entity_id,
    observation,
):

    entity = find_entity(
        cim,
        section,
        entity_id,
    )

    if entity is None:

        raise ValueError(
            f"Entity not found: {entity_id}"
        )

    entity[OBSERVATIONS].append(
        observation
    )

    return observation


def add_evidence(
    cim,
    section,
    entity_id,
    observation_id,
    evidence,
):

    entity = find_entity(
        cim,
        section,
        entity_id,
    )

    if entity is None:

        raise ValueError(
            f"Entity not found: {entity_id}"
        )

    for observation in entity[OBSERVATIONS]:

        if observation["id"] == observation_id:

            observation.setdefault(
                "evidence",
                []
            )

            observation["evidence"].append(
                evidence
            )

            return evidence

    raise ValueError(
        f"Observation not found: {observation_id}"
    )


# ============================================================
# Statistics
# ============================================================

def update_statistics(
    cim,
):

    sections = [

        "operations.projects",

        "operations.capacity",

        "operations.initiatives",

        "management.promises",

        "financial.capital_allocation",

        "risk.identified",
    ]

    for section in sections:

        bucket = get_section(
            cim,
            section,
        )

        bucket[STATISTICS] = {

            "count":
                len(
                    bucket[ITEMS]
                ),

            "high_confidence":
                sum(
                    1
                    for x in bucket[ITEMS]
                    if x.get("confidence")
                    == "high"
                ),

            "medium_confidence":
                sum(
                    1
                    for x in bucket[ITEMS]
                    if x.get("confidence")
                    == "medium"
                ),

            "low_confidence":
                sum(
                    1
                    for x in bucket[ITEMS]
                    if x.get("confidence")
                    == "low"
                ),
        }

    return cim


# ============================================================
# Ledger
# ============================================================

def log_update(
    cim,
    module,
    updated_sections,
):

    cim.setdefault(
        "ledger",
        []
    )

    cim["ledger"].append(

        {

            "module": module,

            "updated_sections":
                updated_sections,

            "timestamp":
                utc_now(),
        }
    )

    return cim