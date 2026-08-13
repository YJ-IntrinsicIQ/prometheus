from __future__ import annotations

from typing import Any, Dict, Iterable, List

PROGRESSION_ENGINE_VERSION = "progression_engine.v1"
PROGRESSION_CONTRACT_VERSION = "progression_contract.v1"


def build_progression_manifest(
    *,
    company_slug: str,
    generated_at: str,
    progression_engine_version: str,
    progression_contract_version: str,
    events_processed: int,
    transitions_detected: int,
    turning_points_detected: int,
    unresolved_items: int,
    outputs_written: Iterable[str],
    validation_status: str,
    limitations: Iterable[str],
) -> Dict[str, Any]:
    return {
        "schema_version": "progression_manifest.v1",
        "company_slug": company_slug,
        "generated_at": generated_at,
        "progression_engine_version": progression_engine_version,
        "progression_contract_version": progression_contract_version,
        "events_processed": int(events_processed),
        "transitions_detected": int(transitions_detected),
        "turning_points_detected": int(turning_points_detected),
        "unresolved_items": int(unresolved_items),
        "outputs_written": list(outputs_written),
        "validation_status": validation_status,
        "limitations": list(limitations),
    }
