from copy import deepcopy
from datetime import datetime


PIPELINE_VERSION = "2.0.0"


def utc_now():

    return (
        datetime.utcnow()
        .isoformat(timespec="seconds")
        + "Z"
    )


def create_bucket():

    return {

        "items": [],

        "summary": {},

        "statistics": {}
    }


def create_empty_cim():

    return {

        # ====================================================
        # Metadata
        # ====================================================

        "metadata": {

            "company": None,

            "year": None,

            "document_type": "annual_report",

            "pipeline_version": PIPELINE_VERSION,

            "created_at": utc_now(),

            "updated_at": utc_now(),
        },

        # ====================================================
        # Documents
        # ====================================================

        "documents": [],

        # ====================================================
        # Business
        # ====================================================

        "business": {

            "dna": {},

            "industry_profile": {},

            "competitive_position": {}
        },

        # ====================================================
        # Management
        # ====================================================

        "management": {

            "summary": {},

            "focus": {},

            "credibility": {},

            "promises": create_bucket()
        },

        # ====================================================
        # Operations
        # ====================================================

        "operations": {

            "projects": create_bucket(),

            "capacity": create_bucket(),

            "initiatives": create_bucket()
        },

        # ====================================================
        # Financial
        # ====================================================

        "financial": {

            "capital_allocation": create_bucket()
        },

        # ====================================================
        # Risk
        # ====================================================

        "risk": {

            "identified": create_bucket(),

            "monitoring": [],

            "red_flags": []
        },

        # ====================================================
        # Themes
        # ====================================================

        "themes": {

            "active": [],

            "weights": {},

            "confidence": {}
        },

        # ====================================================
        # Relationships
        # ====================================================

        "relationships": {

            "entities": [],

            "graph": {}
        },

        # ====================================================
        # Evidence
        # ====================================================

        "evidence": {

            "sources": [],

            "citations": []
        },

        # ====================================================
        # Intelligence Ledger
        # ====================================================

        "ledger": []
    }


def clone_schema():

    return deepcopy(
        create_empty_cim()
    )