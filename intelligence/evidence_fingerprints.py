"""
Prometheus Evidence Fingerprint Infrastructure — Mission 40/44.

Computes SHA-256 digests over canonical module content,
excluding non-semantic fields (timestamps, generator metadata).

INVARIANT: SAME SEMANTIC EVIDENCE → SAME DIGEST
           NEW DOCUMENT ≠ ANSWER MUST REGENERATE

Fingerprint schema version 2 (M44): adds per-section PCIM digests as
pcim:<section_name> virtual module entries alongside the whole-file pcim digest.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

FINGERPRINT_SCHEMA_VERSION = "2"

# ---------------------------------------------------------------------------
# PCIM section fingerprinting (M44)
# Sections consumed by at least one analyst via evidence_required_from_pcim
# OR injected via _selected_pcim_view always_include set in runner.py.
# Excludes: evidence_map (derived), uncertainty_missing_data (derived),
#           metadata (generated_at, company, contract_version, available_years,
#           source_cim), and manifests (pcim_source_manifest,
#           financial_source_manifest, business_identity_manifest).
# ---------------------------------------------------------------------------

# Mirror of the always_include set in runner.py:_selected_pcim_view
PCIM_ALWAYS_INCLUDE_SECTIONS: Set[str] = {
    "financial_truth_inputs",
    "financial_snapshot_inputs",
    "owner_earnings_readiness_inputs",
    "working_capital_quality_inputs",
    "capital_allocation_financial_inputs",
    "per_share_compounding_inputs",
    "unreliable_financial_inputs",
    "invalid_or_quarantined_financial_inputs",
    "precise_missing_financial_inputs",
    "financial_warning_policy",
    "financial_panel_status",
    "financial_panel_usable_domains",
    "financial_panel_limited_domains",
    "financial_panel_blocked_domains",
    "investor_financial_questions",
    "multi_year_financial_inputs",
}

# All PCIM sections that are independently fingerprinted.
# Includes always_include sections plus all sections from any analyst doctrine's
# evidence_required_from_pcim (excluding derived sections).
PCIM_SECTION_FINGERPRINT_CANDIDATES: Set[str] = PCIM_ALWAYS_INCLUDE_SECTIONS | {
    # Graham doctrine
    "financial_strength_inputs",
    "financial_fundamentals_inputs",
    "cash_conversion_inputs",
    "balance_sheet_strength_inputs",
    "working_capital_inputs",
    "financial_quality_inputs",
    "per_share_inputs",
    "financial_driver_inputs",
    "governance_and_incentive_inputs",
    "risk_inputs",
    "business_economics_inputs",
    "capital_allocation_inputs",
    "multi_year_inputs",
    # Buffett/Fisher/Munger/Lynch doctrine additions
    "business_understanding",
    "moat_inputs",
    "financial_growth_inputs",
    "profitability_inputs",
    "return_on_capital_inputs",
    "management_quality_inputs",
    "management_execution_inputs",
    "economic_attribution_inputs",
    "growth_execution_inputs",
    "growth_quality_inputs",
    "corporate_action_inputs",
    "ownership_inputs",
    "simplicity_and_story_inputs",
    "story_vs_numbers_inputs",
}

# ---------------------------------------------------------------------------
# Non-semantic field exclusion list
# Fields that carry no semantic evidence — excluded from digests.
# Rule: if unsure whether a field is semantic, preserve it.
# ---------------------------------------------------------------------------
NON_SEMANTIC_FIELDS: Set[str] = {
    # Generation timestamps — same evidence rebuilt at different times
    "generated_at",
    "updated_at",
    "created_at",
    "generation_timestamp",
    "last_modified",
    # Pipeline execution metadata
    "generator_version",
    "run_id",
    "execution_id",
    "pipeline_run_id",
    "ingestion_timestamp",
    # File-system / caching metadata
    "cache_key",
    "file_mtime",
    "artifact_path",
    "source_path",
    # Sidecar manifests (separate artifacts, not evidence content)
    "source_manifest",
    "manifest",
    # Internal diagnostic identifiers
    "pipeline_metadata",
}

# Stable semantic sort keys — tried in order to sort unordered record collections.
_STABLE_SORT_KEYS: List[str] = [
    "record_id",
    "commitment_id",
    "promise_id",
    "risk_id",
    "project_id",
    "capacity_id",
    "case_id",
    "id",
    "slug",
    "mp_id",
    "cao_id",
    "rg_id",
]

# ---------------------------------------------------------------------------
# Module → canonical source artifact path (relative to company root).
# Derived from intelligence/ask_intrinsiciq/loader.SOURCE_REGISTRY.
# Only modules that carry semantic evidence for answer generation.
# ---------------------------------------------------------------------------
MODULE_SOURCE_MAP: Dict[str, str] = {
    "cim": "company_memory/cim_v1.json",
    "pcim": "company_memory/pcim_v1.json",
    "company_model": "company_memory/company_model/company_model.json",
    "management_progression": "company_memory/management_progression/management_progression.json",
    "management_commitments": "company_memory/management_commitments/management_commitments.json",
    "financial_truth_pack": "company_memory/financials/financial_truth_pack.json",
    "financial_trends": "company_memory/financials/financial_trends.json",
    "owner_earnings_bridge": "company_memory/financials/investor_financial_modules/owner_earnings_bridge.json",
    "working_capital_quality_drilldown": "company_memory/financials/investor_financial_modules/working_capital_quality_drilldown.json",
    "capital_allocation_roi_ledger": "company_memory/financials/investor_financial_modules/capital_allocation_roi_ledger.json",
    "per_share_compounding_analysis": "company_memory/financials/investor_financial_modules/per_share_compounding_analysis.json",
    "ownership_evolution": "company_memory/financials/ownership_evolution.json",
    "projects_registry": "company_memory/projects/projects_registry.json",
    "project_assessments": "company_memory/projects/project_assessments.json",
    "capacity_registry": "company_memory/capacity/capacity_registry.json",
    "capacity_assessments": "company_memory/capacity/capacity_assessments.json",
    "risk_assessments": "company_memory/risks/risk_assessments.json",
    "risk_registry": "company_memory/risks/risk_registry.json",
    "risk_evolution": "company_memory/multi_year/risk_evolution.json",
    "commentary_themes": "company_memory/management_commentary/commentary_themes.json",
    "commentary_assessments": "company_memory/management_commentary/commentary_assessments.json",
    "capital_allocation_outcomes": "company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json",
    "capital_allocation_assessments": "company_memory/capital_allocation_outcomes/capital_allocation_assessments.json",
    "capital_allocation_longitudinal_profile": "company_memory/capital_allocation_outcomes/capital_allocation_longitudinal_profile.json",
    "economic_attribution": "company_memory/economic_attribution/economic_attribution_intelligence.json",
    "management_quality_summary": "company_memory/management_quality/management_quality_summary.json",
    "management_quality_dimensions": "company_memory/management_quality/management_quality_dimensions.json",
    "gold_promise_tracker": "company_memory/gold/management_promise_tracker.json",
    "gold_capital_allocation": "company_memory/gold/capital_allocation_outcome_tracker.json",
    "gold_risk_evolution": "company_memory/gold/risk_evolution_timeline.json",
    "gold_credibility": "company_memory/gold/management_credibility_synthesis.json",
    # Pre-built AI artifacts — fingerprinted to detect content drift
    "committee_synthesis": "company_memory/investor_panel/committee_synthesis.json",
    "graham_analysis": "company_memory/investor_panel/graham_analysis.json",
    "buffett_analysis": "company_memory/investor_panel/buffett_analysis.json",
    "fisher_analysis": "company_memory/investor_panel/fisher_analysis.json",
    "munger_analysis": "company_memory/investor_panel/munger_analysis.json",
    "lynch_analysis": "company_memory/investor_panel/lynch_analysis.json",
}


def _stable_sort_key(item: Any) -> str:
    """Return a stable string key for sorting a list item."""
    if not isinstance(item, dict):
        return json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    for key in _STABLE_SORT_KEYS:
        if key in item:
            return str(item[key])
    # Fallback: use the entire normalized dict as key (deterministic but expensive)
    return json.dumps({k: item[k] for k in sorted(item) if k not in NON_SEMANTIC_FIELDS},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def normalize_for_hashing(obj: Any) -> Any:
    """
    Recursively normalize an object for deterministic hashing.

    Rules:
    - Remove non-semantic fields from dicts.
    - Sort dict keys alphabetically.
    - Sort list-of-dict collections by stable semantic key.
    - Primitive values are kept as-is.
    """
    if isinstance(obj, dict):
        result = {}
        for k in sorted(obj.keys()):
            if k in NON_SEMANTIC_FIELDS:
                continue
            result[k] = normalize_for_hashing(obj[k])
        return result
    elif isinstance(obj, list):
        normalized = [normalize_for_hashing(item) for item in obj]
        # Sort list-of-dict collections by stable semantic key.
        # Only sort if all items are dicts — mixed lists or ordered primitives
        # are preserved as-is.
        if normalized and all(isinstance(item, dict) for item in normalized):
            try:
                normalized = sorted(normalized, key=_stable_sort_key)
            except (TypeError, ValueError):
                pass  # Preserve order if sorting fails
        return normalized
    else:
        return obj


def _canonical_json(obj: Any) -> bytes:
    """Serialize normalized object to canonical JSON bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def compute_digest(payload: Any) -> str:
    """Return sha256:<hex> digest of the semantic content of payload."""
    normalized = normalize_for_hashing(payload)
    return "sha256:" + hashlib.sha256(_canonical_json(normalized)).hexdigest()


def _record_count(payload: Any, module_name: str) -> Optional[int]:
    """Heuristic: extract record count from well-known collection fields."""
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return None
    # Try integer count fields first
    for key in ("commitment_count", "project_count", "allocation_count",
                "capacity_count", "commentary_count", "attribution_count"):
        if isinstance(payload.get(key), int):
            return payload[key]
    # Then try list fields
    for key in ("progression_items", "assessments", "allocations", "cases",
                "projects", "capacity_items", "themes", "commentary_themes",
                "dimensions", "items", "quarantined_candidates"):
        val = payload.get(key)
        if isinstance(val, list):
            return len(val)
    return None


def compute_module_fingerprint(payload: Any, module_name: str) -> Dict[str, Any]:
    """
    Compute a fingerprint record for one loaded module payload.

    Returns a dict with: module, fingerprint_schema_version, digest, record_count.
    """
    return {
        "module": module_name,
        "fingerprint_schema_version": FINGERPRINT_SCHEMA_VERSION,
        "digest": compute_digest(payload),
        "record_count": _record_count(payload, module_name),
    }


def compute_pcim_section_fingerprints(pcim_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Compute per-section fingerprints for a loaded PCIM artifact.

    Returns a dict mapping "pcim:<section_name>" → fingerprint record
    for each section in PCIM_SECTION_FINGERPRINT_CANDIDATES that exists in pcim_data.
    Sections absent from the PCIM are silently skipped.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for section in PCIM_SECTION_FINGERPRINT_CANDIDATES:
        if section not in pcim_data:
            continue
        virtual_name = f"pcim:{section}"
        result[virtual_name] = {
            "module": virtual_name,
            "fingerprint_schema_version": FINGERPRINT_SCHEMA_VERSION,
            "digest": compute_digest(pcim_data[section]),
            "source_section": section,
        }
    return result


def compute_company_fingerprints(
    company_slug: str,
    companies_root: Path | str = Path("companies"),
) -> Dict[str, Any]:
    """
    Compute fingerprints for all available canonical modules of a company.

    Returns a registry dict suitable for writing to
    companies/<company>/company_memory/ask_intrinsiciq/evidence_fingerprint_registry.json
    """
    company_root = Path(companies_root) / company_slug
    modules: Dict[str, Any] = {}
    available: List[str] = []
    missing: List[str] = []
    errors: Dict[str, str] = {}

    for module_name, relative_path in MODULE_SOURCE_MAP.items():
        artifact_path = company_root / relative_path
        if not artifact_path.exists():
            missing.append(module_name)
            continue
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            fp = compute_module_fingerprint(payload, module_name)
            fp["source_artifact"] = relative_path
            modules[module_name] = fp
            available.append(module_name)
            # M44: add per-section virtual modules for pcim
            if module_name == "pcim":
                section_fps = compute_pcim_section_fingerprints(payload)
                for vname, sfp in section_fps.items():
                    sfp["source_artifact"] = relative_path
                    modules[vname] = sfp
        except Exception as exc:
            errors[module_name] = str(exc)
            missing.append(module_name)

    result: Dict[str, Any] = {
        "company": company_slug,
        "fingerprint_schema_version": FINGERPRINT_SCHEMA_VERSION,
        "modules": modules,
    }
    if errors:
        result["errors"] = errors
    return result


def load_fingerprint_registry(
    company_slug: str,
    companies_root: Path | str = Path("companies"),
) -> Optional[Dict[str, Any]]:
    """Load the stored fingerprint registry for a company, or None if missing."""
    path = (
        Path(companies_root)
        / company_slug
        / "company_memory"
        / "ask_intrinsiciq"
        / "evidence_fingerprint_registry.json"
    )
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def compare_fingerprints(
    current: Dict[str, Any],
    baseline: Dict[str, Any],
) -> Dict[str, str]:
    """
    Compare current module fingerprints to a stored baseline.

    Returns dict: module_name → "CLEAN" | "CHANGED" | "MISSING_BASELINE" | "MISSING_CURRENT"
    """
    baseline_modules = (baseline or {}).get("modules", {})
    current_modules = (current or {}).get("modules", {})
    all_modules = set(baseline_modules) | set(current_modules)
    result: Dict[str, str] = {}
    for module in sorted(all_modules):
        if module not in baseline_modules:
            result[module] = "MISSING_BASELINE"
        elif module not in current_modules:
            result[module] = "MISSING_CURRENT"
        elif current_modules[module]["digest"] == baseline_modules[module]["digest"]:
            result[module] = "CLEAN"
        else:
            result[module] = "CHANGED"
    return result
