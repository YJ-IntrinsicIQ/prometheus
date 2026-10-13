"""
Prometheus Shadow Change Detector — Mission 40.

Read-only evaluator: given current evidence and a stored baseline,
determines which answer artifacts WOULD need regeneration.

No AI calls. No queue. No answer mutation. No activation.

Result codes:
  CLEAN                   — dependency fingerprint matches stored baseline
  WOULD_RECOMPUTE_DETERMINISTIC — evidence changed for a deterministic answer
  WOULD_REGENERATE_AI     — evidence changed for an AI generation unit
  MISSING_BASELINE        — no prior fingerprint baseline exists
  DEPENDENCY_UNAVAILABLE  — required module not available on disk
  FINGERPRINT_SCHEMA_MISMATCH — cannot safely compare schema versions
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from intelligence.evidence_fingerprints import (
    FINGERPRINT_SCHEMA_VERSION,
    compute_company_fingerprints,
    load_fingerprint_registry,
)

_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "governance" / "answer_dependency_registry.json"


def _load_dependency_registry() -> Dict[str, Any]:
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


# Result constants
CLEAN = "CLEAN"
WOULD_RECOMPUTE_DETERMINISTIC = "WOULD_RECOMPUTE_DETERMINISTIC"
WOULD_REGENERATE_AI = "WOULD_REGENERATE_AI"
MISSING_BASELINE = "MISSING_BASELINE"
DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
FINGERPRINT_SCHEMA_MISMATCH = "FINGERPRINT_SCHEMA_MISMATCH"


# ENG-MISSION52.2c: versioned generation-contract override layered over the historical M39/M44
# record. Only the override's "contract" block is functional (and is what gets fingerprinted);
# the "governance" block is metadata.
V5_OVERRIDE_KEY = "m52_contract_v5_override"


def get_effective_contract(target: str, registry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The versioned override contract for `target` (question or generation unit), or None."""
    contract = (registry.get(V5_OVERRIDE_KEY) or {}).get("contract")
    if contract and target in (contract.get("generation_unit"), contract.get("question")):
        return contract
    return None


def effective_contract_digest(contract: Dict[str, Any]) -> str:
    import hashlib
    raw = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _resolve_upstream_modules(
    target: str,
    registry: Dict[str, Any],
    *,
    visited: Optional[Set[str]] = None,
) -> List[str]:
    """
    Resolve all upstream MODULE names for a question or generation unit,
    following upstream_generation_units transitively.
    """
    if visited is None:
        visited = set()
    if target in visited:
        return []
    visited.add(target)

    override = get_effective_contract(target, registry)
    if override:
        return list(dict.fromkeys(override["upstream_modules"]))

    questions = registry.get("questions", {})
    generation_units = registry.get("generation_units", {})

    # Try question first
    entry = questions.get(target) or generation_units.get(target)
    if not entry:
        return []

    modules: List[str] = list(entry.get("upstream_modules", []))
    for sub_unit in entry.get("upstream_generation_units", []):
        modules.extend(_resolve_upstream_modules(sub_unit, registry, visited=visited))

    return list(dict.fromkeys(modules))  # deduplicate preserving order


def evaluate_answer_freshness(
    company_slug: str,
    target: str,  # question_id or generation_unit name
    *,
    companies_root: Path | str = Path("companies"),
    baseline: Optional[Dict[str, Any]] = None,
    current: Optional[Dict[str, Any]] = None,  # pre-computed fingerprints for batch use
) -> Dict[str, Any]:
    """
    Evaluate whether the answer for `target` (question or generation unit)
    is still CLEAN given the current evidence state.

    Args:
        company_slug: e.g. "sun_pharma"
        target: question_id (e.g. "what-can-break-the-thesis") or
                generation_unit (e.g. "graham_panel")
        companies_root: path to the companies/ directory
        baseline: optional pre-loaded baseline registry dict

    Returns a dict with:
        result: one of the result constants above
        target: the evaluated target
        company: the company slug
        changed_modules: list of changed module names (if WOULD_*)
        unchanged_modules: list of unchanged module names (if CLEAN)
        missing_modules: list of unavailable modules
        generation_unit: name of the generation unit, if any
        regeneration_mode: DETERMINISTIC | AI_PRECOMPUTED | HYBRID_PRECOMPUTED
    """
    registry = _load_dependency_registry()
    questions = registry.get("questions", {})
    generation_units = registry.get("generation_units", {})

    # Resolve entry
    entry = questions.get(target) or generation_units.get(target)
    if not entry:
        return {
            "result": DEPENDENCY_UNAVAILABLE,
            "target": target,
            "company": company_slug,
            "error": f"Target '{target}' not found in dependency registry",
        }

    # Questions use "generation_mode"; generation units use "type"
    generation_mode = entry.get("generation_mode") or entry.get("type") or "DETERMINISTIC"
    generation_unit = entry.get("generation_unit") or (target if target in generation_units else None)

    # Load baseline
    if baseline is None:
        baseline = load_fingerprint_registry(company_slug, companies_root)

    if baseline is None:
        return {
            "result": MISSING_BASELINE,
            "target": target,
            "company": company_slug,
            "generation_unit": generation_unit,
            "regeneration_mode": generation_mode,
        }

    # Check schema version compatibility
    baseline_schema = baseline.get("fingerprint_schema_version", "0")
    if baseline_schema != FINGERPRINT_SCHEMA_VERSION:
        return {
            "result": FINGERPRINT_SCHEMA_MISMATCH,
            "target": target,
            "company": company_slug,
            "baseline_schema_version": baseline_schema,
            "current_schema_version": FINGERPRINT_SCHEMA_VERSION,
        }

    # Compute current fingerprints (or use pre-computed batch value)
    if current is None:
        current = compute_company_fingerprints(company_slug, companies_root)
    current_modules = current.get("modules", {})
    baseline_modules = baseline.get("modules", {})

    # Resolve all upstream modules (transitive)
    upstream = _resolve_upstream_modules(target, registry)
    if not upstream:
        # Entry exists but has no upstream modules — treat as always CLEAN
        return {
            "result": CLEAN,
            "target": target,
            "company": company_slug,
            "generation_unit": generation_unit,
            "regeneration_mode": generation_mode,
            "changed_modules": [],
            "unchanged_modules": [],
            "missing_modules": [],
            "note": "No upstream modules defined",
        }

    changed: List[str] = []
    unchanged: List[str] = []
    missing: List[str] = []

    for module in upstream:
        if module not in current_modules:
            missing.append(module)
            continue
        if module not in baseline_modules:
            # No baseline for this module → treat as changed
            changed.append(module)
            continue
        if current_modules[module]["digest"] == baseline_modules[module]["digest"]:
            unchanged.append(module)
        else:
            changed.append(module)

    # If any required module is unavailable (not just missing from baseline)
    if missing and not changed:
        return {
            "result": DEPENDENCY_UNAVAILABLE,
            "target": target,
            "company": company_slug,
            "generation_unit": generation_unit,
            "regeneration_mode": generation_mode,
            "missing_modules": missing,
            "unchanged_modules": unchanged,
        }

    if not changed:
        return {
            "result": CLEAN,
            "target": target,
            "company": company_slug,
            "generation_unit": generation_unit,
            "regeneration_mode": generation_mode,
            "changed_modules": [],
            "unchanged_modules": unchanged,
            "missing_modules": missing,
        }

    # Determine appropriate result based on generation mode
    if generation_mode in ("DETERMINISTIC", "NO_AI"):
        result_code = WOULD_RECOMPUTE_DETERMINISTIC
    else:  # AI_PRECOMPUTED, HYBRID_PRECOMPUTED
        result_code = WOULD_REGENERATE_AI

    return {
        "result": result_code,
        "target": target,
        "company": company_slug,
        "generation_unit": generation_unit,
        "regeneration_mode": generation_mode,
        "changed_modules": changed,
        "unchanged_modules": unchanged,
        "missing_modules": missing,
    }


def evaluate_all_questions(
    company_slug: str,
    *,
    companies_root: Path | str = Path("companies"),
    baseline: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate freshness for all registered questions and generation units.

    Returns a summary with per-question results and aggregate counts.
    """
    registry = _load_dependency_registry()

    if baseline is None:
        baseline = load_fingerprint_registry(company_slug, companies_root)

    # Pre-compute current fingerprints once
    current = compute_company_fingerprints(company_slug, companies_root)

    all_targets = list(registry.get("questions", {}).keys())
    # Also evaluate generation units directly
    for unit in registry.get("generation_units", {}):
        if unit not in all_targets:
            all_targets.append(unit)

    results: Dict[str, Any] = {}
    counts: Dict[str, int] = {
        CLEAN: 0,
        WOULD_RECOMPUTE_DETERMINISTIC: 0,
        WOULD_REGENERATE_AI: 0,
        MISSING_BASELINE: 0,
        DEPENDENCY_UNAVAILABLE: 0,
        FINGERPRINT_SCHEMA_MISMATCH: 0,
    }

    for target in all_targets:
        r = evaluate_answer_freshness(
            company_slug,
            target,
            companies_root=companies_root,
            baseline=baseline,
            current=current,
        )
        results[target] = r
        code = r.get("result", "UNKNOWN")
        if code in counts:
            counts[code] += 1

    ai_units_would_regenerate = [
        t for t, r in results.items()
        if r.get("result") == WOULD_REGENERATE_AI
        and t in registry.get("generation_units", {})
    ]

    return {
        "company": company_slug,
        "total_targets": len(all_targets),
        "counts": counts,
        "ai_units_would_regenerate": ai_units_would_regenerate,
        "ai_units_would_regenerate_count": len(ai_units_would_regenerate),
        "results": results,
    }
