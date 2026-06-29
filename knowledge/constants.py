"""
Canonical constants for the Prometheus Canonical Intelligence Model (PCIM).

This file is the SINGLE source of truth for:

- Entity types
- PCIM locations
- Primary name fields
- ID prefixes
"""

# ============================================================
# Entity Types
# ============================================================

ENTITY_PROJECT = "project"
ENTITY_PROMISE = "promise"
ENTITY_RISK = "risk"
ENTITY_CAPACITY = "capacity"
ENTITY_INITIATIVE = "initiative"
ENTITY_CAPITAL = "capital_allocation"

ENTITY_PRODUCT = "product"
ENTITY_DOCUMENT = "document"

ENTITY_RELATIONSHIP = "relationship"
ENTITY_OBSERVATION = "observation"
ENTITY_EVIDENCE = "evidence"


# ============================================================
# PCIM Paths
# ============================================================

PROJECTS = "operations.projects"

PROMISES = "management.promises"

RISKS = "risk.identified"

CAPACITY = "operations.capacity"

INITIATIVES = "operations.initiatives"

CAPITAL_ALLOCATION = "financial.capital_allocation"

DOCUMENTS = "documents"

RELATIONSHIPS = "relationships"

EVIDENCE = "evidence"


# ============================================================
# Bucket Keys
# ============================================================

ITEMS = "items"

SUMMARY = "summary"

STATISTICS = "statistics"

OBSERVATIONS = "observations"


# ============================================================
# Confidence
# ============================================================

CONFIDENCE_HIGH = "high"

CONFIDENCE_MEDIUM = "medium"

CONFIDENCE_LOW = "low"


# ============================================================
# Entity Configuration
# ============================================================

ENTITY_CONFIG = {

    ENTITY_PROJECT: {

        "section": PROJECTS,

        "name_field": "project_name",

        "id_prefix": "PROJ",
    },

    ENTITY_PROMISE: {

        "section": PROMISES,

        "name_field": "promise",

        "id_prefix": "PROM",
    },

    ENTITY_RISK: {

        "section": RISKS,

        "name_field": "risk",

        "id_prefix": "RISK",
    },

    ENTITY_CAPACITY: {

        "section": CAPACITY,

        "name_field": "capacity_type",

        "id_prefix": "CAP",
    },

    ENTITY_INITIATIVE: {

        "section": INITIATIVES,

        "name_field": "initiative",

        "id_prefix": "INIT",
    },

    ENTITY_CAPITAL: {

        "section": CAPITAL_ALLOCATION,

        "name_field": "action",

        "id_prefix": "CAPALLOC",
    },

    ENTITY_PRODUCT: {

        "section": None,

        "name_field": "product_name",

        "id_prefix": "PROD",
    },

    ENTITY_DOCUMENT: {

        "section": DOCUMENTS,

        "name_field": "filename",

        "id_prefix": "DOC",
    },

    ENTITY_RELATIONSHIP: {

        "section": RELATIONSHIPS,

        "name_field": "name",

        "id_prefix": "REL",
    },

    ENTITY_OBSERVATION: {

        "section": None,

        "name_field": None,

        "id_prefix": "OBS",
    },

    ENTITY_EVIDENCE: {

        "section": EVIDENCE,

        "name_field": None,

        "id_prefix": "EVID",
    },
}