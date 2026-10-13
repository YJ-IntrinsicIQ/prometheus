"""
M46.1: Contract V2 manifest and generation fingerprint binding.
M48: Contract V3 manifest added alongside V2 (V2 manifest preserved for backward compatibility).

Owns the canonical, deterministic representation of all material semantics
introduced by M46 that affect what a valid management answer must contain
and what gates it must pass before human review.

All digests are computed from artifact content, not file paths or timestamps.
No AI calls. Import-time only computation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

# ── Resolve repo root from this file's location ───────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]

GENERATION_UNIT = "how_good_is_management_synthesis"
GENERATION_CONTRACT_SCHEMA = "m46_contract_v1"

# Policy versions introduced in M46
MANAGEMENT_ANSWER_CONTRACT_VERSION = "2"
FACT_PACK_SCHEMA_VERSION = "management_fact_pack.v1"
EIV_POLICY_VERSION = "eiv_management_quality.v1"
ASSEMBLER_POLICY_VERSION = "m46_assembler_v1"
DPF_POLICY_VERSION = "m46_dpf_v1"
OUTPUT_SCHEMA_VERSION = "1"


def _file_digest(path: Path) -> str:
    """SHA-256 of file contents. Returns 'MISSING' if file absent."""
    if not path.exists():
        return "MISSING"
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _policy_digest(policy: Dict) -> str:
    """Deterministic hash of a policy dict."""
    return "sha256:" + hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()


# ── Artifact content digests (computed once at import time) ───────────────────
MANAGEMENT_ANSWER_CONTRACT_SCHEMA_DIGEST = _file_digest(
    _REPO_ROOT / "schemas" / "management_quality_answer_contract_v2.json"
)
FACT_PACK_SCHEMA_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "management_quality" / "fact_pack.py"
)
EIV_POLICY_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "external_investor_value_validator.py"
)

# ── Assembler policy: LLM/deterministic boundary ─────────────────────────────
ASSEMBLER_POLICY: Dict[str, Any] = {
    "version": ASSEMBLER_POLICY_VERSION,
    "deterministic_fields": [
        "progression_lifecycle_counts",
        "commitment_counts",
        "behavioral_descriptor",
        "deterministic_precision_facts",
        "what_is_not_yet_proven",
        "what_to_monitor",
    ],
    "llm_fields": [
        "simple_answer",
        "what_evidence_shows",
        "what_may_mean_economically",
        "key_points_narrative",
    ],
    "invariant": "LLM_CANNOT_OVERWRITE_DETERMINISTIC_FIELDS",
    "fallback": "If LLM omits deterministic fields, assembler preserves them from fact_pack",
}

# ── DPF policy: what a valid DPF must contain ─────────────────────────────────
DPF_POLICY: Dict[str, Any] = {
    "version": DPF_POLICY_VERSION,
    "min_dpfs": 3,
    "required_dpf_types": ["delivery_follow_through"],
    "required_fields_per_dpf": ["metric", "value", "semantic_meaning"],
    "source": "canonical_management_progression_evidence",
}

ASSEMBLER_POLICY_DIGEST = _policy_digest(ASSEMBLER_POLICY)
DPF_POLICY_DIGEST = _policy_digest(DPF_POLICY)


def build_contract_v2_manifest(
    generation_unit: str = GENERATION_UNIT,
    output_schema_version: str = OUTPUT_SCHEMA_VERSION,
) -> Dict[str, Any]:
    """Canonical, normalized Contract V2 manifest.

    Covers all material semantics introduced in M46 that affect answer
    structure and release eligibility. Does NOT include timestamps,
    absolute paths, run IDs, or developer machine paths.
    """
    return {
        "generation_unit": generation_unit,
        "generation_contract_schema": GENERATION_CONTRACT_SCHEMA,
        "management_answer_contract": {
            "version": MANAGEMENT_ANSWER_CONTRACT_VERSION,
            "digest": MANAGEMENT_ANSWER_CONTRACT_SCHEMA_DIGEST,
        },
        "fact_pack_schema": {
            "version": FACT_PACK_SCHEMA_VERSION,
            "digest": FACT_PACK_SCHEMA_DIGEST,
        },
        "assembler_policy": {
            "version": ASSEMBLER_POLICY_VERSION,
            "digest": ASSEMBLER_POLICY_DIGEST,
        },
        "dpf_policy": {
            "version": DPF_POLICY_VERSION,
            "digest": DPF_POLICY_DIGEST,
        },
        "eiv_policy": {
            "version": EIV_POLICY_VERSION,
            "digest": EIV_POLICY_DIGEST,
        },
        "output_schema_version": output_schema_version,
    }


def compute_contract_v2_fingerprint(
    generation_unit: str = GENERATION_UNIT,
    output_schema_version: str = OUTPUT_SCHEMA_VERSION,
) -> str:
    """Deterministic fingerprint of the full Contract V2 manifest."""
    manifest = build_contract_v2_manifest(generation_unit, output_schema_version)
    raw = json.dumps(manifest, sort_keys=True)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


# Module-level singleton — imported by regeneration_executor
CONTRACT_V2_POLICY_DIGEST: str = compute_contract_v2_fingerprint()

# ── Contract V3 additions (ENG-MISSION48) ─────────────────────────────────────
MANAGEMENT_ANSWER_CONTRACT_VERSION_V3 = "3"
FACT_PACK_SCHEMA_VERSION_V2 = "management_fact_pack.v2"
EIV_POLICY_VERSION_V2 = "eiv_management_quality.v2"
ASSEMBLER_POLICY_VERSION_V3 = "m48_assembler_v3"
CAPABILITY_REGISTRY_VERSION = "management_capability_registry.v1"
PARITY_VALIDATOR_VERSION = "management_parity_validator.v1"

MANAGEMENT_ANSWER_CONTRACT_V3_SCHEMA_DIGEST = _file_digest(
    _REPO_ROOT / "schemas" / "management_quality_answer_contract_v3.json"
)
FACT_PACK_V2_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "management_quality" / "fact_pack_v2.py"
)
EIV_V2_POLICY_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "external_investor_value_validator_v2.py"
)
ASSEMBLER_V3_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "management_quality" / "assembler_v3.py"
)
CAPABILITY_REGISTRY_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "management_quality" / "capability_registry.py"
)
PARITY_VALIDATOR_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "management_quality" / "capability_parity_validator.py"
)

ASSEMBLER_POLICY_V3: Dict[str, Any] = {
    "version": ASSEMBLER_POLICY_VERSION_V3,
    "deterministic_fields": [
        "progression_lifecycle_counts",
        "commitment_counts_with_hard_breakdown",
        "behavioral_descriptor",
        "deterministic_precision_facts_with_npm",
        "what_evidence_shows",
        "what_management_says",
        "where_management_was_consistent",
        "management_consistency_map",
        "what_is_not_yet_proven",
        "what_to_monitor",
        "key_points",
    ],
    "llm_may_enrich_but_not_overwrite": [
        "simple_answer",
        "what_evidence_shows",
        "what_management_says",
        "where_management_was_consistent",
        "what_may_mean_economically",
    ],
    "invariant": "MODEL_COMPRESSION_CANNOT_REMOVE_DETERMINISTIC_SEMANTICS",
    "upgrade_from_v2": (
        "V2 had what_evidence_shows/what_management_says/where_management_was_consistent/"
        "management_consistency_map/what_may_mean_economically in LLM-only territory. "
        "V3 pre-populates deterministic skeletons so LLM compression cannot remove them."
    ),
}

ASSEMBLER_POLICY_V3_DIGEST = _policy_digest(ASSEMBLER_POLICY_V3)


def build_contract_v3_manifest(
    generation_unit: str = GENERATION_UNIT,
    output_schema_version: str = OUTPUT_SCHEMA_VERSION,
) -> Dict[str, Any]:
    """Canonical Contract V3 manifest (ENG-MISSION48)."""
    return {
        "generation_unit": generation_unit,
        "generation_contract_schema": "m48_contract_v3",
        "management_answer_contract": {
            "version": MANAGEMENT_ANSWER_CONTRACT_VERSION_V3,
            "digest": MANAGEMENT_ANSWER_CONTRACT_V3_SCHEMA_DIGEST,
        },
        "fact_pack_schema": {
            "version": FACT_PACK_SCHEMA_VERSION_V2,
            "digest": FACT_PACK_V2_DIGEST,
        },
        "assembler_policy": {
            "version": ASSEMBLER_POLICY_VERSION_V3,
            "digest": ASSEMBLER_POLICY_V3_DIGEST,
        },
        "eiv_policy": {
            "version": EIV_POLICY_VERSION_V2,
            "digest": EIV_V2_POLICY_DIGEST,
        },
        "capability_registry": {
            "version": CAPABILITY_REGISTRY_VERSION,
            "digest": CAPABILITY_REGISTRY_DIGEST,
        },
        "parity_validator": {
            "version": PARITY_VALIDATOR_VERSION,
            "digest": PARITY_VALIDATOR_DIGEST,
        },
        "output_schema_version": output_schema_version,
    }


def compute_contract_v3_fingerprint(
    generation_unit: str = GENERATION_UNIT,
    output_schema_version: str = OUTPUT_SCHEMA_VERSION,
) -> str:
    """Deterministic fingerprint of the full Contract V3 manifest."""
    manifest = build_contract_v3_manifest(generation_unit, output_schema_version)
    raw = json.dumps(manifest, sort_keys=True)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


CONTRACT_V3_POLICY_DIGEST: str = compute_contract_v3_fingerprint()


# ── Contract V4 additions (ENG-MISSION50) ─────────────────────────────────────
MANAGEMENT_ANSWER_CONTRACT_VERSION_V4 = "4"
ASSEMBLER_POLICY_VERSION_V4 = "m50_assembler_v4"

ASSEMBLER_V4_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "management_quality" / "assembler_v4.py"
)
INVESTOR_SECTIONS_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "management_quality" / "investor_sections.py"
)
RATING_QUARANTINE_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "management_quality" / "rating_quarantine.py"
)

ASSEMBLER_POLICY_V4: Dict[str, Any] = {
    "version": ASSEMBLER_POLICY_VERSION_V4,
    "deterministic_fields": [
        "progression_lifecycle_counts",
        "commitment_counts_with_hard_breakdown",
        "behavioral_descriptor",
        "deterministic_precision_facts_with_npm",
        "what_evidence_shows",
        "what_management_says",
        "where_management_was_consistent",
        "management_consistency_map",
        "what_is_not_yet_proven",
        "what_to_monitor",
        "key_points",
        "simple_answer",
    ],
    "llm_may_enrich_but_not_overwrite": [
        "simple_answer",          # only if it contains behavioral_descriptor AND no rating language
        "what_may_mean_economically",  # only if substantive AND temporal check passes
    ],
    "llm_section_override_blocked": True,
    "invariant": "PROMETHEUS_CONSTRUCTS_INVESTOR_INTELLIGENCE",
    "upgrade_from_v3": (
        "V3 had llm_may_enrich_but_not_overwrite policy for what_evidence_shows, "
        "what_management_says, where_management_was_consistent — but assembler_v3 "
        "PREFERRED LLM content if 'substantive' (>= 2 entries). "
        "V4 changes: all structured sections are always deterministic; "
        "LLM cannot override any structured section regardless of content quality."
    ),
}

ASSEMBLER_POLICY_V4_DIGEST = _policy_digest(ASSEMBLER_POLICY_V4)


def build_contract_v4_manifest(
    generation_unit: str = GENERATION_UNIT,
    output_schema_version: str = OUTPUT_SCHEMA_VERSION,
) -> Dict[str, Any]:
    """Canonical Contract V4 manifest (ENG-MISSION50)."""
    return {
        "generation_unit": generation_unit,
        "generation_contract_schema": "m50_contract_v4",
        "management_answer_contract": {
            "version": MANAGEMENT_ANSWER_CONTRACT_VERSION_V4,
            "digest": MANAGEMENT_ANSWER_CONTRACT_V3_SCHEMA_DIGEST,  # schema unchanged; policy changed
        },
        "fact_pack_schema": {
            "version": FACT_PACK_SCHEMA_VERSION_V2,
            "digest": FACT_PACK_V2_DIGEST,
        },
        "assembler_policy": {
            "version": ASSEMBLER_POLICY_VERSION_V4,
            "digest": ASSEMBLER_POLICY_V4_DIGEST,
        },
        "assembler_artifact": {
            "version": ASSEMBLER_POLICY_VERSION_V4,
            "digest": ASSEMBLER_V4_DIGEST,
        },
        "investor_sections_artifact": {
            "version": "m50_investor_sections_v1",
            "digest": INVESTOR_SECTIONS_DIGEST,
        },
        "rating_quarantine_artifact": {
            "version": "m50_rating_quarantine_v1",
            "digest": RATING_QUARANTINE_DIGEST,
        },
        "eiv_policy": {
            "version": EIV_POLICY_VERSION_V2,
            "digest": EIV_V2_POLICY_DIGEST,
        },
        "capability_registry": {
            "version": CAPABILITY_REGISTRY_VERSION,
            "digest": CAPABILITY_REGISTRY_DIGEST,
        },
        "parity_validator": {
            "version": PARITY_VALIDATOR_VERSION,
            "digest": PARITY_VALIDATOR_DIGEST,
        },
        "output_schema_version": output_schema_version,
    }


def compute_contract_v4_fingerprint(
    generation_unit: str = GENERATION_UNIT,
    output_schema_version: str = OUTPUT_SCHEMA_VERSION,
) -> str:
    """Deterministic fingerprint of the full Contract V4 manifest."""
    manifest = build_contract_v4_manifest(generation_unit, output_schema_version)
    raw = json.dumps(manifest, sort_keys=True)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


CONTRACT_V4_POLICY_DIGEST: str = compute_contract_v4_fingerprint()


# ── Contract V5 additions (ENG-MISSION52) ─────────────────────────────────────
MANAGEMENT_ANSWER_CONTRACT_VERSION_V5 = "5"
ASSEMBLER_POLICY_VERSION_V5 = "m52_assembler_v5"

ASSEMBLER_V5_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "management_quality" / "assembler_v5.py"
)
# investor_sections.py digest changes with the V5 fixes (consistency map + MC-0031)
INVESTOR_SECTIONS_V5_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "management_quality" / "investor_sections.py"
)

# ENG-MISSION52.2a: source-backed enrichment of the V2 fact pack (kept separate so the frozen
# V3/V4 fact_pack_v2.py digest — part of their historical identities — is not disturbed)
FACT_PACK_ENRICHMENT_V5_DIGEST = _file_digest(
    _REPO_ROOT / "intelligence" / "management_quality" / "fact_pack_enrichment_v5.py"
)

def _dependency_contract_v5_digest() -> str:
    """Digest of the effective V5 dependency/generation contract from the dependency registry
    (ENG-MISSION52.2c). It decides what 'fresh' means for V5, so it is part of V5 identity."""
    try:
        from intelligence.shadow_change_detector import effective_contract_digest, get_effective_contract
        registry = json.loads((_REPO_ROOT / "governance" / "answer_dependency_registry.json").read_text(encoding="utf-8"))
        contract = get_effective_contract("how_good_is_management_synthesis", registry)
        return effective_contract_digest(contract) if contract else "ABSENT_HISTORICAL_V3"
    except Exception:
        return "UNAVAILABLE"


DEPENDENCY_CONTRACT_V5_DIGEST = _dependency_contract_v5_digest()

ASSEMBLER_POLICY_V5: Dict[str, Any] = {
    "version": ASSEMBLER_POLICY_VERSION_V5,
    "deterministic_fields": [
        "progression_lifecycle_counts",
        "commitment_counts_with_hard_breakdown",
        "behavioral_descriptor",
        "deterministic_precision_facts_with_npm",
        "what_evidence_shows",
        "what_management_says",
        "where_management_was_consistent",
        "management_consistency_map",
        "what_may_mean_economically",
        "what_is_not_yet_proven",
        "what_to_monitor",
        "key_points",
        "simple_answer",
    ],
    "llm_may_enrich_but_not_overwrite": [],
    "llm_section_override_blocked": True,
    "zero_ai_calls_invariant": True,
    "generation_mode": "DETERMINISTIC",
    "invariant": "FULLY_DETERMINISTIC_ZERO_AI_CALLS",
    "upgrade_from_v4": (
        "V4 authorized LLM for simple_answer (descriptor gate) and what_may_mean_economically (temporal gate). "
        "In M51 canary: LLM simple_answer rejected; LLM economic context accepted but dropped PAT. "
        "Human reviewer (Yogesh, 2026-10-07) decision: NEEDS_CHANGES + REMOVE_AI. "
        "V5 removes all LLM authorization. Fixes: (1) consistency map INCONSISTENT-before-CONSISTENT check; "
        "(2) all canonical hard commitments represented in what_management_says; "
        "(3) deterministic economic renderer always preserves PAT. "
        "M52.2a: (4) commitment follow-through keeps delivery, deadline adherence and regulatory outcome separate; "
        "(5) consistency entries carry behavioural evidence, period and uncertainty; "
        "(6) capital-allocation and named-product context from canonical ledgers; "
        "(7) typed unit-preserving commitment text; (8) no truncation of material commitments; "
        "(9) section-quality gate blocks raw fields and unsupported 'compounding confirmed'. "
        "M52.2d: (10) behaviour classifications need a complete proof, absence of verified outcome is never evidence of negative behaviour; "
        "(11) tracker scope stated; (12) filing/deadline/approval independent; (13) absence claims bounded by searched sources; (14) claim provenance populated."
    ),
}

ASSEMBLER_POLICY_V5_DIGEST = _policy_digest(ASSEMBLER_POLICY_V5)


def build_contract_v5_manifest(
    generation_unit: str = GENERATION_UNIT,
    output_schema_version: str = OUTPUT_SCHEMA_VERSION,
) -> Dict[str, Any]:
    """Canonical Contract V5 manifest (ENG-MISSION52) — fully deterministic, zero AI calls."""
    return {
        "generation_unit": generation_unit,
        "generation_contract_schema": "m52_contract_v5",
        "management_answer_contract": {
            "version": MANAGEMENT_ANSWER_CONTRACT_VERSION_V5,
            "digest": MANAGEMENT_ANSWER_CONTRACT_V3_SCHEMA_DIGEST,  # schema unchanged; policy changed
        },
        "fact_pack_schema": {
            "version": FACT_PACK_SCHEMA_VERSION_V2,
            "digest": FACT_PACK_V2_DIGEST,
        },
        "assembler_policy": {
            "version": ASSEMBLER_POLICY_VERSION_V5,
            "digest": ASSEMBLER_POLICY_V5_DIGEST,
        },
        "assembler_artifact": {
            "version": ASSEMBLER_POLICY_VERSION_V5,
            "digest": ASSEMBLER_V5_DIGEST,
        },
        "investor_sections_artifact": {
            "version": "m522d_investor_sections_v4",
            "digest": INVESTOR_SECTIONS_V5_DIGEST,
        },
        "fact_pack_enrichment_artifact": {
            "version": "m522d_enrichment_v2",
            "digest": FACT_PACK_ENRICHMENT_V5_DIGEST,
        },
        "dependency_contract": {
            "version": "m52_contract_v5_override.v1",
            "digest": DEPENDENCY_CONTRACT_V5_DIGEST,
        },
        "rating_quarantine_artifact": {
            "version": "m50_rating_quarantine_v1",
            "digest": RATING_QUARANTINE_DIGEST,
        },
        "eiv_policy": {
            "version": EIV_POLICY_VERSION_V2,
            "digest": EIV_V2_POLICY_DIGEST,
        },
        "capability_registry": {
            "version": CAPABILITY_REGISTRY_VERSION,
            "digest": CAPABILITY_REGISTRY_DIGEST,
        },
        "parity_validator": {
            "version": PARITY_VALIDATOR_VERSION,
            "digest": PARITY_VALIDATOR_DIGEST,
        },
        "generation_mode": "DETERMINISTIC",
        "zero_ai_calls": True,
        "output_schema_version": output_schema_version,
    }


def compute_contract_v5_fingerprint(
    generation_unit: str = GENERATION_UNIT,
    output_schema_version: str = OUTPUT_SCHEMA_VERSION,
) -> str:
    """Deterministic fingerprint of the full Contract V5 manifest."""
    manifest = build_contract_v5_manifest(generation_unit, output_schema_version)
    raw = json.dumps(manifest, sort_keys=True)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


CONTRACT_V5_POLICY_DIGEST: str = compute_contract_v5_fingerprint()


def build_structural_skeleton(fact_pack: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deterministic structural skeleton from a fact pack.

    Populates all deterministic fields from canonical evidence.
    LLM narrative fields are left as None — they are NOT required
    for structural contract parity; only the deterministic fields are.

    Satisfies M46.1 Section 16: LLM must not be required for contract
    completeness. The deterministic sections are fully populated here.
    """
    return {
        # Deterministic — populated without LLM
        "behavioral_descriptor": fact_pack.get("behavioral_descriptor"),
        "deterministic_precision_facts": fact_pack.get("dpfs", []),
        "what_is_not_yet_proven": fact_pack.get("uncertainty_items", []),
        "what_to_monitor": fact_pack.get("monitoring_items", []),
        "key_points": [
            f"Progression: {fact_pack['progression_counts'].get('total', 0)} items tracked; "
            f"{fact_pack['progression_counts'].get('delivered', 0)} confirmed delivered",
            f"Behavioral pattern: {fact_pack.get('behavioral_descriptor', 'UNKNOWN')}",
            f"Evidence confidence: {fact_pack.get('evidence_confidence', 'UNKNOWN')}",
        ],
        # LLM narrative fields — None until AI generation fills them
        "simple_answer": None,
        "what_evidence_shows": None,
        "what_may_mean_economically": None,
    }
