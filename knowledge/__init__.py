"""
Prometheus Canonical Intelligence Model (PCIM)

This package contains the core infrastructure for the
Prometheus Intelligence Layer.
"""

__version__ = "2.0.0"

# ============================================================
# Core API
# ============================================================

from .cim import (
    initialize_cim,
    load_cim,
    save_cim,
    get_section,
    update_section,
    append_entity,
    upsert_entity,
    find_entity,
    add_observation,
    add_evidence,
    update_statistics,
)

# ============================================================
# Schema
# ============================================================

from .cim_schema import (
    create_empty_cim,
)

# ============================================================
# Constants
# ============================================================

from .constants import *

# ============================================================
# IDs
# ============================================================

from .ids import *

# ============================================================
# Evidence
# ============================================================

from .evidence import (
    build_evidence,
    build_observation,
)

__all__ = [

    # Schema
    "create_empty_cim",

    # Core API
    "initialize_cim",
    "load_cim",
    "save_cim",
    "get_section",
    "update_section",
    "append_entity",
    "upsert_entity",
    "find_entity",
    "add_observation",
    "add_evidence",
    "update_statistics",

    # Evidence
    "build_evidence",
    "build_observation",
]