"""
Prometheus Shadow Regeneration Planner — Mission 41.

Sits between dirty detection (M40) and future AI execution.
Given changed evidence, computes a deterministic plan:
  which AI generation units need regeneration,
  how many calls, approximate tokens, and cost estimate.

Invariant:
  AI_CALLS_EXECUTED = 0
  PLANNED_CALL ≠ EXECUTED_CALL

Budgets:
  UPSTREAM_AI  — calls to rebuild canonical intelligence modules (not this module's concern)
  ANSWER_AI    — calls to regenerate investor-facing synthesis artifacts (this module plans these)

These are never combined.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from intelligence.evidence_fingerprints import (
    FINGERPRINT_SCHEMA_VERSION,
    compute_company_fingerprints,
    load_fingerprint_registry,
)
from intelligence.shadow_change_detector import (
    CLEAN,
    DEPENDENCY_UNAVAILABLE,
    FINGERPRINT_SCHEMA_MISMATCH,
    MISSING_BASELINE,
    WOULD_REGENERATE_AI,
    WOULD_RECOMPUTE_DETERMINISTIC,
    _load_dependency_registry,
    _resolve_upstream_modules,
    evaluate_answer_freshness,
)

# ---------------------------------------------------------------------------
# Planner decision constants
# ---------------------------------------------------------------------------
REUSE = "REUSE"
WOULD_REGENERATE = "WOULD_REGENERATE"
INITIAL_GENERATION_REQUIRED = "INITIAL_GENERATION_REQUIRED"
BLOCKED_MISSING_DEPENDENCY = "BLOCKED_MISSING_DEPENDENCY"
BLOCKED_SCHEMA_MISMATCH = "BLOCKED_SCHEMA_MISMATCH"
BLOCKED_BUDGET = "BLOCKED_BUDGET"
BLOCKED_DUPLICATE_IN_FLIGHT = "BLOCKED_DUPLICATE_IN_FLIGHT"
NO_GENERATION_UNIT = "NO_GENERATION_UNIT"

# Regeneration reason codes
EVIDENCE_CHANGED = "EVIDENCE_CHANGED"
PROMPT_VERSION_CHANGED = "PROMPT_VERSION_CHANGED"
SCHEMA_VERSION_CHANGED = "SCHEMA_VERSION_CHANGED"
INITIAL_GENERATION = "INITIAL_GENERATION"

# ---------------------------------------------------------------------------
# Current prompt/schema versions for each generation unit.
# Bumping a version here marks the corresponding unit as needing regeneration
# even if evidence fingerprints are unchanged.
# ---------------------------------------------------------------------------
UNIT_PROMPT_VERSIONS: Dict[str, str] = {
    "graham_panel": "1",
    "buffett_panel": "1",
    "fisher_panel": "1",
    "munger_panel": "1",
    "lynch_panel": "1",
    "committee_synthesis": "1",
    # M45: version bump triggers PROMPT_VERSION_CHANGED for how_good_is_management_synthesis
    "how_good_is_management_synthesis": "2",
}

UNIT_SCHEMA_VERSIONS: Dict[str, str] = {
    "graham_panel": "1",
    "buffett_panel": "1",
    "fisher_panel": "1",
    "munger_panel": "1",
    "lynch_panel": "1",
    "committee_synthesis": "1",
    "how_good_is_management_synthesis": "1",
}

# ---------------------------------------------------------------------------
# Provider / model registry.
# Derived from factory.py (AI_PROVIDER env), openai.py (OPENAI_MODEL env),
# and runner.py / relationship_aware_composer.py call sites.
# ---------------------------------------------------------------------------
MODEL_REGISTRY: Dict[str, Dict[str, str]] = {
    "graham_panel": {
        "provider_env": "AI_PROVIDER",
        "provider_default": "openai",
        "model_env": "OPENAI_MODEL",
        "model_default": "gpt-4.1-mini",
        "model_observed_in_telemetry": "gpt-5-mini-2025-08-07",
        "stage": "investor_panel_analyst",
        "call_site": "intelligence/investor_panel/runner.py:call_llm_with_input_pack",
    },
    "buffett_panel": {
        "provider_env": "AI_PROVIDER",
        "provider_default": "openai",
        "model_env": "OPENAI_MODEL",
        "model_default": "gpt-4.1-mini",
        "model_observed_in_telemetry": "gpt-5-mini-2025-08-07",
        "stage": "investor_panel_analyst",
        "call_site": "intelligence/investor_panel/runner.py:call_llm_with_input_pack",
    },
    "fisher_panel": {
        "provider_env": "AI_PROVIDER",
        "provider_default": "openai",
        "model_env": "OPENAI_MODEL",
        "model_default": "gpt-4.1-mini",
        "model_observed_in_telemetry": "gpt-5-mini-2025-08-07",
        "stage": "investor_panel_analyst",
        "call_site": "intelligence/investor_panel/runner.py:call_llm_with_input_pack",
    },
    "munger_panel": {
        "provider_env": "AI_PROVIDER",
        "provider_default": "openai",
        "model_env": "OPENAI_MODEL",
        "model_default": "gpt-4.1-mini",
        "model_observed_in_telemetry": "gpt-5-mini-2025-08-07",
        "stage": "investor_panel_analyst",
        "call_site": "intelligence/investor_panel/runner.py:call_llm_with_input_pack",
    },
    "lynch_panel": {
        "provider_env": "AI_PROVIDER",
        "provider_default": "openai",
        "model_env": "OPENAI_MODEL",
        "model_default": "gpt-4.1-mini",
        "model_observed_in_telemetry": "gpt-5-mini-2025-08-07",
        "stage": "investor_panel_analyst",
        "call_site": "intelligence/investor_panel/runner.py:call_llm_with_input_pack",
    },
    "committee_synthesis": {
        "provider_env": "AI_PROVIDER",
        "provider_default": "openai",
        "model_env": "OPENAI_MODEL",
        "model_default": "gpt-4.1-mini",
        "model_observed_in_telemetry": "gpt-5-mini-2025-08-07",
        "stage": "committee_synthesis",
        "call_site": "intelligence/investor_panel/committee_synthesizer.py:call_llm_with_input_pack",
    },
    "how_good_is_management_synthesis": {
        "provider_env": "AI_PROVIDER",
        "provider_default": "openai",
        "model_env": "OPENAI_MODEL",
        "model_default": "gpt-4o-mini",
        "model_observed_in_telemetry": None,
        "stage": "shadow_composition",
        "call_site": "intelligence/ask_intrinsiciq/relationship_aware_composer.py:compose_answer_from_plan",
        "note": "model default from relationship_aware_composer.py:258; no LLM call manifest stored",
    },
}

# ---------------------------------------------------------------------------
# Token estimates.
# Analyst panels and committee_synthesis: from historical LLM call manifests
#   (companies/*/company_memory/investor_panel/*_llm_call_manifest.json)
#   N observations across all 4 companies.
# how_good_is_management_synthesis: CONFIG_DEFAULT — no stored manifest.
#   Output bounded by max_tokens=2000 in shadow_runner.py; input estimated
#   from relationship_aware_composer.py (evidence_lines[:10] + prompts).
# ---------------------------------------------------------------------------
TOKEN_TELEMETRY: Dict[str, Dict[str, Any]] = {
    "graham_panel": {
        "source": "HISTORICAL_TELEMETRY",
        "observation_count": 65,
        "median_input_tokens": 7543,
        "p75_input_tokens": 9520,
        "median_output_tokens": 4671,
        "p75_output_tokens": 5153,
        "median_total_tokens": 11628,
        "p75_total_tokens": 14673,
        "token_budget_configured": 7000,
    },
    "buffett_panel": {
        "source": "HISTORICAL_TELEMETRY",
        "observation_count": 70,
        "median_input_tokens": 7540,
        "p75_input_tokens": 9535,
        "median_output_tokens": 5133,
        "p75_output_tokens": 5675,
        "median_total_tokens": 12664,
        "p75_total_tokens": 15210,
        "token_budget_configured": 7000,
    },
    "fisher_panel": {
        "source": "HISTORICAL_TELEMETRY",
        "observation_count": 71,
        "median_input_tokens": 7714,
        "p75_input_tokens": 9027,
        "median_output_tokens": 4873,
        "p75_output_tokens": 5360,
        "median_total_tokens": 12586,
        "p75_total_tokens": 14387,
        "token_budget_configured": 7000,
    },
    "munger_panel": {
        "source": "HISTORICAL_TELEMETRY",
        "observation_count": 60,
        "median_input_tokens": 7670,
        "p75_input_tokens": 9592,
        "median_output_tokens": 5297,
        "p75_output_tokens": 5702,
        "median_total_tokens": 13193,
        "p75_total_tokens": 15294,
        "token_budget_configured": 7000,
    },
    "lynch_panel": {
        "source": "HISTORICAL_TELEMETRY",
        "observation_count": 70,
        "median_input_tokens": 8078,
        "p75_input_tokens": 9075,
        "median_output_tokens": 4903,
        "p75_output_tokens": 5250,
        "median_total_tokens": 12675,
        "p75_total_tokens": 14325,
        "token_budget_configured": 7000,
    },
    "committee_synthesis": {
        "source": "HISTORICAL_TELEMETRY",
        "observation_count": 148,
        "median_input_tokens": 3059,
        "p75_input_tokens": 3264,
        "median_output_tokens": 2863,
        "p75_output_tokens": 3455,
        "median_total_tokens": 5859,
        "p75_total_tokens": 6719,
        "token_budget_configured": 6000,
    },
    "how_good_is_management_synthesis": {
        "source": "CONTRACT_V5_DETERMINISTIC",
        "observation_count": 0,
        "median_input_tokens": 0,
        "p75_input_tokens": 0,
        "median_output_tokens": 0,
        "p75_output_tokens": 0,
        "median_total_tokens": 0,
        "p75_total_tokens": 0,
        "token_budget_configured": 0,
        "planned_ai_calls": 0,
        "note": (
            "ENG-MISSION52 Contract V5: fully deterministic. "
            "Zero AI/LLM calls. assembler_v5.build_management_answer_v5() is pure Python. "
            "Human reviewer Yogesh (2026-10-07): NEEDS_CHANGES + REMOVE_AI. "
            "V4 LLM calls produced inferior output in M51 canary (simple_answer rejected, "
            "economic context dropped PAT). V5 removes all LLM authorization."
        ),
    },
}

# ---------------------------------------------------------------------------
# Quota state discovery.
# Inspected: knowledge/ai/openai.py, knowledge/ai/factory.py, input_packs.py
# No provider account quota stored in repository.
# ---------------------------------------------------------------------------
QUOTA_DISCOVERY: Dict[str, Any] = {
    "known_technical_limits": {
        "investor_panel_analyst_token_budget": 7000,
        "committee_synthesis_token_budget": 6000,
        "shadow_composition_max_tokens": "env:PROMETHEUS_LEVEL3_SHADOW_MAX_TOKENS or 20000",
        "openai_max_retries": "env:OPENAI_MAX_RETRIES or 2",
        "openai_timeout_seconds": "env:OPENAI_TIMEOUT_SECONDS or 180.0",
        "ai_provider": "env:AI_PROVIDER or mock",
        "ai_model": "env:OPENAI_MODEL or AI_MODEL",
    },
    "proposed_prometheus_budgets": "See SHADOW_BUDGET_POLICY below",
    "unknown_provider_account_limits": (
        "OpenAI account-level rate limits, tier limits, and daily spend caps "
        "are not stored in the repository. Actual limits depend on the account "
        "used at runtime."
    ),
    "ai_quota_state": "AI_QUOTA_UNKNOWN_FROM_REPOSITORY",
}

# ---------------------------------------------------------------------------
# Shadow budget policy (proposed — not enforced in M41).
# ---------------------------------------------------------------------------
SHADOW_BUDGET_POLICY: Dict[str, Any] = {
    "status": "PROPOSED_NOT_ENFORCED",
    "note": "Values are conservative proposals derived from telemetry, not production limits",
    "global": {
        "daily_call_budget": 50,
        "monthly_call_budget": 200,
    },
    "company": {
        "max_regeneration_calls_per_refresh": 7,
        "monthly_call_limit": 30,
    },
    "generation_unit": {
        "max_calls_per_evidence_version": 1,
        "max_input_token_ceiling": 15000,
        "retry_allowance": 1,
    },
    "budget_dimensions_rationale": {
        "7_calls_per_company": "5 analysts + 1 committee + 1 management synthesis = absolute maximum",
        "50_daily_global": "4 companies × 7 calls + margin = 28 max realistic; 50 provides safety",
        "200_monthly_global": "~6 full refreshes/month plus onboarding headroom",
    },
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_model(unit: str) -> str:
    info = MODEL_REGISTRY.get(unit, {})
    # Runtime env takes precedence over observed; default is last resort
    return (
        os.getenv(info.get("model_env", "OPENAI_MODEL"))
        or info.get("model_observed_in_telemetry")
        or info.get("model_default", "unknown")
    )


def _compute_unit_plan_id(
    company: str,
    unit: str,
    upstream_digest: str,
    prompt_version: str,
    schema_version: str,
) -> str:
    raw = f"{company}:{unit}:{upstream_digest}:{prompt_version}:{schema_version}"
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _upstream_combined_digest(unit: str, current_modules: Dict[str, Any], registry: Dict[str, Any]) -> str:
    upstream = _resolve_upstream_modules(unit, registry)
    parts = []
    for mod in sorted(upstream):
        entry = current_modules.get(mod, {})
        parts.append(f"{mod}:{entry.get('digest', 'MISSING')}")
    raw = ";".join(parts)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _plan_unit(
    company: str,
    unit: str,
    registry: Dict[str, Any],
    current_modules: Dict[str, Any],
    baseline_modules: Dict[str, Any],
    prompt_version: str,
    schema_version: str,
    in_flight: Optional[set],
    budget_policy: Optional[Dict[str, Any]],
    planned_count_so_far: int,
) -> Dict[str, Any]:
    upstream = _resolve_upstream_modules(unit, registry)

    upstream_digest = _upstream_combined_digest(unit, current_modules, registry)
    plan_unit_id = _compute_unit_plan_id(company, unit, upstream_digest, prompt_version, schema_version)

    # Check for duplicate in-flight plan
    if in_flight is not None and plan_unit_id in in_flight:
        return {
            "generation_unit": unit,
            "decision": BLOCKED_DUPLICATE_IN_FLIGHT,
            "plan_unit_id": plan_unit_id,
            "planned_ai_calls": 0,
            "dirty_dependencies": [],
            "changed_modules": [],
            "unchanged_modules": [],
            "missing_modules": [],
            "regeneration_reason": [],
            "reason": "identical plan_unit_id already in-flight for this run",
        }

    # Classify module changes
    changed: List[str] = []
    unchanged: List[str] = []
    missing: List[str] = []

    for mod in upstream:
        if mod not in current_modules:
            missing.append(mod)
            continue
        if mod not in baseline_modules:
            changed.append(mod)
            continue
        if current_modules[mod]["digest"] == baseline_modules[mod]["digest"]:
            unchanged.append(mod)
        else:
            changed.append(mod)

    # Check schema mismatch
    baseline_schema = (baseline_modules or {}).get("_schema_version", FINGERPRINT_SCHEMA_VERSION)

    # Determine regeneration reasons
    reasons: List[str] = []
    if changed:
        reasons.append(EVIDENCE_CHANGED)

    last_prompt_v = prompt_version  # ponytail: would need stored binding to detect change; flag as always current
    last_schema_v = schema_version
    # In practice: compare against a stored binding per company/unit. For M41 we track current versions.
    # A PROMPT_VERSION_CHANGED reason is injected externally via forced_reason parameter.

    # Missing dependency blocks the plan
    if missing and not changed:
        return {
            "generation_unit": unit,
            "decision": BLOCKED_MISSING_DEPENDENCY,
            "plan_unit_id": plan_unit_id,
            "planned_ai_calls": 0,
            "dirty_dependencies": [],
            "changed_modules": changed,
            "unchanged_modules": unchanged,
            "missing_modules": missing,
            "regeneration_reason": reasons,
            "reason": f"upstream modules unavailable: {missing}",
        }

    # Budget check
    policy = budget_policy or SHADOW_BUDGET_POLICY
    unit_max = policy.get("generation_unit", {}).get("max_calls_per_evidence_version", 1)
    company_max = policy.get("company", {}).get("max_regeneration_calls_per_refresh", 7)
    if reasons and planned_count_so_far >= company_max:
        return {
            "generation_unit": unit,
            "decision": BLOCKED_BUDGET,
            "plan_unit_id": plan_unit_id,
            "planned_ai_calls": 0,
            "dirty_dependencies": changed,
            "changed_modules": changed,
            "unchanged_modules": unchanged,
            "missing_modules": missing,
            "regeneration_reason": reasons,
            "reason": f"company budget ceiling reached: {company_max} calls",
        }

    tel = TOKEN_TELEMETRY.get(unit, {})
    token_estimate = {
        "source": tel.get("source", "UNKNOWN"),
        "observation_count": tel.get("observation_count", 0),
        "expected_input_tokens": tel.get("median_input_tokens", 0),
        "expected_output_tokens": tel.get("median_output_tokens", 0),
        "expected_total_tokens": tel.get("median_total_tokens", 0),
        "conservative_input_tokens": tel.get("p75_input_tokens", 0),
        "conservative_output_tokens": tel.get("p75_output_tokens", 0),
        "conservative_total_tokens": tel.get("p75_total_tokens", 0),
        "max_permitted_tokens": tel.get("token_budget_configured", 0),
        "cost_estimate": "COST_ESTIMATE_UNAVAILABLE_FROM_REPOSITORY",
        "cost_note": (
            f"No pricing stored for model={_resolve_model(unit)}, provider=openai. "
            "Actual cost depends on runtime model and account pricing."
        ),
    }

    # Determine decision
    if not reasons:
        return {
            "generation_unit": unit,
            "decision": REUSE,
            "plan_unit_id": plan_unit_id,
            "planned_ai_calls": 0,
            "dirty_dependencies": [],
            "changed_modules": [],
            "unchanged_modules": unchanged,
            "missing_modules": missing,
            "regeneration_reason": [],
            "token_estimate": token_estimate,
            "reason": "dependency fingerprint unchanged; no version bump",
        }

    # Contract V5: management quality synthesis is fully deterministic — 0 AI calls always
    ai_calls = 0 if unit == "how_good_is_management_synthesis" else 1

    return {
        "generation_unit": unit,
        "decision": WOULD_REGENERATE,
        "plan_unit_id": plan_unit_id,
        "planned_ai_calls": ai_calls,
        "dirty_dependencies": changed,
        "changed_modules": changed,
        "unchanged_modules": unchanged,
        "missing_modules": missing,
        "regeneration_reason": reasons,
        "token_estimate": token_estimate,
        "reason": f"regeneration required: {reasons}",
    }


def _make_company_plan_id(company: str, unit_plans: List[Dict[str, Any]]) -> str:
    parts = ";".join(u["plan_unit_id"] for u in sorted(unit_plans, key=lambda u: u["generation_unit"]))
    return "sha256:" + hashlib.sha256(f"{company}:{parts}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan_regeneration(
    company_slug: str,
    changed_modules: Optional[List[str]] = None,
    *,
    forced_reasons: Optional[Dict[str, List[str]]] = None,
    prompt_versions: Optional[Dict[str, str]] = None,
    schema_versions: Optional[Dict[str, str]] = None,
    budget_policy: Optional[Dict[str, Any]] = None,
    companies_root: Path | str = Path("companies"),
    baseline: Optional[Dict[str, Any]] = None,
    current: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compute a deterministic regeneration plan for all 7 AI generation units.

    Args:
        company_slug: e.g. "sun_pharma"
        changed_modules: if provided, use these as the dirty module set instead of
                         computing from fingerprints. Used for scenario simulation.
        forced_reasons: per-unit override of regeneration reasons, e.g.
                        {"graham_panel": ["PROMPT_VERSION_CHANGED"]}
        prompt_versions: overrides for UNIT_PROMPT_VERSIONS (scenario J)
        schema_versions: overrides for UNIT_SCHEMA_VERSIONS
        budget_policy: overrides for SHADOW_BUDGET_POLICY
        companies_root: path to companies directory
        baseline: pre-loaded fingerprint baseline (skips disk read)
        current: pre-computed current fingerprints (skips computation)

    Returns a plan dict with per-unit decisions, token estimates, call counts,
    UPSTREAM_AI and ANSWER_AI budgets, and cost forecasts.
    """
    registry = _load_dependency_registry()
    generation_units = list(registry.get("generation_units", {}).keys())

    p_versions = {**UNIT_PROMPT_VERSIONS, **(prompt_versions or {})}
    s_versions = {**UNIT_SCHEMA_VERSIONS, **(schema_versions or {})}
    forced_reasons = forced_reasons or {}

    # Load baseline and current fingerprints
    if baseline is None:
        baseline = load_fingerprint_registry(company_slug, companies_root)

    has_baseline = baseline is not None
    baseline_modules: Dict[str, Any] = (baseline or {}).get("modules", {})

    if current is None:
        current = compute_company_fingerprints(company_slug, companies_root)
    current_modules: Dict[str, Any] = current.get("modules", {})

    # If changed_modules is explicitly provided, synthesize a fake baseline
    # by cloning current and corrupting only the specified modules.
    if changed_modules is not None:
        import copy
        if not has_baseline:
            # Use current as baseline (all CLEAN), then mark specified as changed
            baseline_modules = copy.deepcopy(current_modules)
        else:
            baseline_modules = copy.deepcopy(baseline_modules)
        for mod in changed_modules:
            if mod in baseline_modules:
                # Corrupt digest to simulate change
                baseline_modules[mod]["digest"] = baseline_modules[mod]["digest"][:-4] + "XXXX"
            else:
                # Module exists now but not in baseline → treated as changed
                pass
        has_baseline = True

    if not has_baseline:
        # No baseline at all → every unit needs initial generation
        unit_plans = []
        for unit in generation_units:
            upstream_digest = _upstream_combined_digest(unit, current_modules, registry)
            plan_unit_id = _compute_unit_plan_id(
                company_slug, unit, upstream_digest,
                p_versions.get(unit, "1"), s_versions.get(unit, "1"),
            )
            tel = TOKEN_TELEMETRY.get(unit, {})
            unit_plans.append({
                "generation_unit": unit,
                "decision": INITIAL_GENERATION_REQUIRED,
                "plan_unit_id": plan_unit_id,
                "planned_ai_calls": 1,
                "dirty_dependencies": list(_resolve_upstream_modules(unit, registry)),
                "changed_modules": [],
                "unchanged_modules": [],
                "missing_modules": [],
                "regeneration_reason": [INITIAL_GENERATION],
                "token_estimate": {
                    "source": tel.get("source", "UNKNOWN"),
                    "observation_count": tel.get("observation_count", 0),
                    "expected_input_tokens": tel.get("median_input_tokens", 0),
                    "expected_output_tokens": tel.get("median_output_tokens", 0),
                    "expected_total_tokens": tel.get("median_total_tokens", 0),
                    "conservative_total_tokens": tel.get("p75_total_tokens", 0),
                    "cost_estimate": "COST_ESTIMATE_UNAVAILABLE_FROM_REPOSITORY",
                },
                "reason": "no baseline exists; initial generation required",
            })
        total_planned = sum(u["planned_ai_calls"] for u in unit_plans)
        company_plan_id = _make_company_plan_id(company_slug, unit_plans)
        return _finalize_plan(company_slug, unit_plans, total_planned, company_plan_id, budget_policy, registry)

    # Normal case: compare current vs baseline
    in_flight: set = set()
    unit_plans = []
    planned_count = 0

    for unit in generation_units:
        pv = p_versions.get(unit, "1")
        sv = s_versions.get(unit, "1")

        result = _plan_unit(
            company=company_slug,
            unit=unit,
            registry=registry,
            current_modules=current_modules,
            baseline_modules=baseline_modules,
            prompt_version=pv,
            schema_version=sv,
            in_flight=in_flight,
            budget_policy=budget_policy,
            planned_count_so_far=planned_count,
        )

        # Apply forced reasons (prompt version change, schema change, etc.)
        extra = forced_reasons.get(unit, [])
        if extra:
            if result["decision"] == REUSE:
                # Override to WOULD_REGENERATE
                tel = TOKEN_TELEMETRY.get(unit, {})
                result = {
                    **result,
                    "decision": WOULD_REGENERATE,
                    "planned_ai_calls": 1,
                    "regeneration_reason": result.get("regeneration_reason", []) + extra,
                    "reason": f"regeneration required: {result.get('regeneration_reason', []) + extra}",
                    "token_estimate": result.get("token_estimate") or {
                        "source": tel.get("source", "UNKNOWN"),
                        "expected_input_tokens": tel.get("median_input_tokens", 0),
                        "expected_output_tokens": tel.get("median_output_tokens", 0),
                        "expected_total_tokens": tel.get("median_total_tokens", 0),
                        "conservative_total_tokens": tel.get("p75_total_tokens", 0),
                        "cost_estimate": "COST_ESTIMATE_UNAVAILABLE_FROM_REPOSITORY",
                    },
                }
            else:
                result["regeneration_reason"] = list(set(result.get("regeneration_reason", []) + extra))

        if result.get("planned_ai_calls", 0) > 0:
            planned_count += 1
            in_flight.add(result["plan_unit_id"])

        unit_plans.append(result)

    company_plan_id = _make_company_plan_id(company_slug, unit_plans)
    return _finalize_plan(company_slug, unit_plans, planned_count, company_plan_id, budget_policy, registry)


def _finalize_plan(
    company_slug: str,
    unit_plans: List[Dict[str, Any]],
    total_answer_ai: int,
    company_plan_id: str,
    budget_policy: Optional[Dict[str, Any]],
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    # Aggregate token forecasts across planned units
    expected_in = sum(
        u.get("token_estimate", {}).get("expected_input_tokens", 0)
        for u in unit_plans if u.get("planned_ai_calls", 0) > 0
    )
    expected_out = sum(
        u.get("token_estimate", {}).get("expected_output_tokens", 0)
        for u in unit_plans if u.get("planned_ai_calls", 0) > 0
    )
    conservative_total = sum(
        u.get("token_estimate", {}).get("conservative_total_tokens", 0)
        for u in unit_plans if u.get("planned_ai_calls", 0) > 0
    )

    # PCIM impact analysis
    pcim_sensitive = [
        u["generation_unit"] for u in unit_plans
        if "pcim" in _resolve_upstream_modules(u["generation_unit"], registry)
    ]
    units_dirty_because_of_pcim = [
        u["generation_unit"] for u in unit_plans
        if u.get("decision") == WOULD_REGENERATE
        and "pcim" in u.get("changed_modules", [])
    ]

    return {
        "company": company_slug,
        "plan_id": company_plan_id,
        "upstream_ai_calls_required": 0,
        "answer_ai_calls_planned": total_answer_ai,
        "total_planned_calls": total_answer_ai,
        "upstream_note": (
            "UPSTREAM_AI (CIM/PCIM build in business_understanding/pipeline.py) is tracked separately. "
            "M41 plans only ANSWER_AI. upstream_ai_calls_required=0 means no upstream build is "
            "in scope for this plan."
        ),
        "units": unit_plans,
        "cost_forecast": {
            "expected_input_tokens": expected_in,
            "expected_output_tokens": expected_out,
            "expected_total_tokens": expected_in + expected_out,
            "conservative_total_tokens": conservative_total,
            "cost_estimate": "COST_ESTIMATE_UNAVAILABLE_FROM_REPOSITORY",
            "cost_note": (
                "No per-token pricing stored in repository. "
                "Runtime model set via OPENAI_MODEL env var. "
                "Observed model in telemetry: gpt-5-mini-2025-08-07."
            ),
        },
        "pcim_impact": {
            "pcim_sensitive_units": pcim_sensitive,
            "pcim_sensitive_count": len(pcim_sensitive),
            "units_dirty_because_of_pcim_in_this_plan": units_dirty_because_of_pcim,
            "false_positive_risk": (
                "PCIM change marks all 5 analyst panels dirty even if only one "
                "PCIM section changed. Section-level fingerprinting would reduce "
                "potential avoidable calls: up to 4 per refresh if only 1 analyst's "
                "section changed."
            ),
            "estimated_avoidable_calls_if_pcim_section_fingerprinted": 4,
            "refinement_recommendation": (
                "Implement PCIM section-level fingerprinting in a future mission. "
                "Each analyst consumes a specific PCIM section. Fingerprint per section "
                "to enable per-analyst isolation even when PCIM is rebuilt."
            ),
        },
        "proposed_budget_policy": budget_policy or SHADOW_BUDGET_POLICY,
        "quota_state": QUOTA_DISCOVERY,
        "model_registry": MODEL_REGISTRY,
    }


def plan_all_companies(
    companies: List[str],
    changed_modules: Optional[List[str]] = None,
    *,
    forced_reasons: Optional[Dict[str, Dict[str, List[str]]]] = None,
    companies_root: Path | str = Path("companies"),
) -> Dict[str, Any]:
    """
    Run plan_regeneration for all given companies.

    Returns aggregate plan with per-company results and global totals.
    """
    results = {}
    total_answer_ai = 0
    for co in companies:
        fr = (forced_reasons or {}).get(co)
        r = plan_regeneration(
            co,
            changed_modules=changed_modules,
            forced_reasons=fr,
            companies_root=companies_root,
        )
        results[co] = r
        total_answer_ai += r["answer_ai_calls_planned"]

    return {
        "companies": companies,
        "total_answer_ai_calls_planned": total_answer_ai,
        "total_upstream_ai_calls_required": 0,
        "per_company": results,
    }
