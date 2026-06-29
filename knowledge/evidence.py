"""
Evidence & Observation helpers.

Hierarchy

Entity
    └── Observation(s)
            └── Evidence
"""

from datetime import datetime

from .ids import (
    generate_observation_id,
    generate_evidence_id,
)


# ============================================================
# Utilities
# ============================================================

def utc_now():

    return (
        datetime.utcnow()
        .isoformat(timespec="seconds")
        + "Z"
    )


# ============================================================
# Evidence
# ============================================================

def build_evidence(

    document_id=None,

    page=None,

    chunk_id=None,

    confidence="medium",

    document_type="annual_report",

    source_file=None,

    metadata=None,
):
    """
    Creates a canonical evidence object.
    """

    return {

        "id": generate_evidence_id(),

        "document_id": document_id,

        "document_type": document_type,

        "page": page,

        "chunk_id": chunk_id,

        "source_file": source_file,

        "confidence": confidence,

        "captured_at": utc_now(),

        "metadata": metadata or {}
    }


# ============================================================
# Observation
# ============================================================

def build_observation(

    year=None,

    status=None,

    summary=None,

    evidence=None,

    metadata=None,
):
    """
    Observation of an entity at a point in time.

    Example

    FY25

    Project commissioned.

    FY26

    Capacity doubled.
    """

    return {

        "id": generate_observation_id(),

        "year": year,

        "status": status,

        "summary": summary,

        "created_at": utc_now(),

        "evidence": evidence or [],

        "metadata": metadata or {}
    }


# ============================================================
# Helpers
# ============================================================

def append_evidence(
    observation,
    evidence,
):

    observation.setdefault(
        "evidence",
        []
    )

    observation["evidence"].append(
        evidence
    )

    return observation


def merge_observations(
    observations,
    observation,
):
    """
    Merge by observation ID.
    """

    for idx, existing in enumerate(observations):

        if existing["id"] == observation["id"]:

            merged = existing.copy()

            merged.update(observation)

            observations[idx] = merged

            return observations

    observations.append(observation)

    return observations