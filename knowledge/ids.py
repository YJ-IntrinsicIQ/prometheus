"""
Generic ID generation utilities.

Every entity ID is generated from ENTITY_CONFIG.

No entity-specific logic should exist in this file.
"""

from collections import defaultdict

from .constants import ENTITY_CONFIG


_COUNTERS = defaultdict(int)


# ============================================================
# Counter Utilities
# ============================================================

def reset_counters():
    """
    Reset counters.

    Useful for testing.
    """

    _COUNTERS.clear()


def _next(prefix):

    _COUNTERS[prefix] += 1

    return f"{prefix}_{_COUNTERS[prefix]:05d}"


# ============================================================
# Generic Generator
# ============================================================

def generate_id(entity_type):
    """
    Generate an ID for any entity type.

    Example

        generate_id(ENTITY_PROJECT)

            →

        PROJ_00001
    """

    if entity_type not in ENTITY_CONFIG:

        raise ValueError(
            f"Unknown entity type: {entity_type}"
        )

    prefix = ENTITY_CONFIG[
        entity_type
    ]["id_prefix"]

    return _next(prefix)


# ============================================================
# Company
# ============================================================

def generate_company_id():

    return _next("COMP")

# ============================================================
# Convenience Wrappers
# ============================================================

def generate_document_id():
    return generate_id("document")


def generate_observation_id():
    return generate_id("observation")


def generate_evidence_id():
    return generate_id("evidence")