"""
M45 Controlled AI Regeneration Execution — single-unit executor.

History:
  Attempt 1 (M45.1) — contract_fp sha256:a626ea1610a99499aa11614d44774a4d
    PACP FAIL: check_mq_no_rating_leakage (MQ-R1), check_mq_behavioral_descriptor_present (MQ-R2)
    Cause: overall_view:'weak' seeded rating leakage; descriptor constraint not strong enough
    Candidate: NOT WRITTEN. Certified artifact: PRESERVED.

  Attempt 2 (M45.2) — composition policy corrected; new contract fingerprint
    See execution_history in manifest for full ledger.

SECURITY CONSTRAINTS (never remove or weaken):
- Requires --execute-ai-regeneration flag; exits cleanly without it
- MAX_EXECUTED_AI_CALLS = 1 per run; RETRY_COUNT = 0
- Candidate written per-attempt by execution_id; NEVER overwrites certified artifact
- PACP certification required before candidate is written
- History-preserving: execution_history is append-only; failed attempts never deleted
- No self-approval; no automatic activation; no --mode approve/activate
- Executor MUST NOT be imported or invoked from UI/API serving paths
- Previous certified answer MUST NOT provide semantic content to new generation
- Behavioral descriptor MUST be independently derived from canonical evidence

Idempotency identity:
    sha256({company, unit, evidence_dependency_fingerprint,
            generation_contract_fingerprint, output_schema_version})
Same evidence + same contract → identical ID.  Evidence or contract change → new ID.

Usage:
  python -m intelligence.regeneration_executor --execute-ai-regeneration [--company sun_pharma] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Security constants — do not change without governance review ───────────────
MAX_EXECUTED_AI_CALLS = 1
RETRY_COUNT = 0
MAX_OUTPUT_TOKENS = 2000
OUTPUT_SCHEMA_VERSION = "1"

# ── Target ─────────────────────────────────────────────────────────────────────
UNIT_TARGET = "how_good_is_management_synthesis"
QUESTION_ID = "how-good-is-management"
DOMAIN_QUESTION = (
    "How good is management at executing on strategy, managing capital, "
    "and maintaining credibility with investors?"
)
MANIFEST_FILENAME = "regeneration_execution_manifest.json"
CERTIFIED_ARTIFACT_PATH = "company_memory/ask_intrinsiciq/shadow_level3_hybrid_answers.json"

# Candidate filename uses execution_id_short to avoid overwriting prior attempts
CANDIDATE_FILENAME_TEMPLATE = "regeneration_candidate_how_good_is_management_{eid_short}.json"
# Legacy filename (attempt 1) — kept for reference
CANDIDATE_FILENAME = "regeneration_candidate_how_good_is_management.json"

# Generation contract schema version — bumped M46.1: Contract V2 policy bound into fingerprint
GENERATION_CONTRACT_SCHEMA = "m46_contract_v1"

# M46.1: Import Contract V2 policy digest so it participates in the generation fingerprint.
# This binds management_answer_contract_v2, fact_pack schema, assembler policy,
# DPF policy, and EIV policy into the deterministic contract identity.
try:
    from intelligence.management_quality.contract_manifest import CONTRACT_V2_POLICY_DIGEST as _CONTRACT_V2_POLICY_DIGEST
except Exception:
    _CONTRACT_V2_POLICY_DIGEST = None  # ponytail: import guard — won't happen in production

# ── Composition policy — all material generation-behavior inputs ───────────────
# Hash included in contract fingerprint. ANY change here → new contract fingerprint.
COMPOSITION_POLICY: Dict[str, Any] = {
    "version": "m45_composition_v3",  # M45.3: removed interpretation.conclusion (unsafe claim source)
    # M45.1: was v1 (included overall_view:weak → MQ-R1 leak)
    # M45.2: was v2 (added composition_policy_hash to contract_fp)
    # M45.3: v3 — interpretation.conclusion excluded (contains "management quality is weak" in Sun Pharma data)
    "overall_view_in_plan": False,     # CHANGED M45.2 (was True in attempt 1, caused MQ-R1 leakage)
    "overall_direction_in_plan": True,
    "strongest_dimension_phrasing": "evidence_backed_performance",
    "weakest_dimension_phrasing": "evidence_gaps",
    "descriptor_required_verbatim_in_simple_answer": True,
    "descriptor_source": "canonical_management_progression_evidence",
    "prohibited_language_policy": (
        "NO: management quality is weak/strong/mixed/poor/good/excellent; "
        "NO: management is capable/credible/disciplined/effective/trustworthy; "
        "NO: weak/strong/capable management; NO: numeric/letter grade for management"
    ),
    "descriptor_enforcement_mode": "explicit_mandatory_constraint_in_user_content",
    "no_rating_enforcement_mode": "explicit_prohibition_in_user_content",
    "claim_sources": [
        "investor_implication",
        "overall_direction",
        "strongest_dimension_evidence_backed",
        "weakest_dimension_evidence_gaps",
        "interpretation.why_it_matters",
        # interpretation.conclusion EXCLUDED M45.3: this field can contain prohibited rating language
        # (e.g. Sun Pharma: "Management quality is weak and the trajectory is stable.")
        # UNSAFE_CLAIM_SOURCE = mq_summary.interpretation.conclusion
        "interpretation.economic_mechanism",
        "what_strengthened_conviction_top3",
        "what_weakened_conviction_top3",
        "behavioral_descriptor_canonical_evidence",
    ],
    "generation_contract_schema": GENERATION_CONTRACT_SCHEMA,
}

# Behavioral descriptor vocabulary — M37.1 invariant. Do not extend without governance review.
_BEHAVIORAL_DESCRIPTORS = (
    "FOLLOW_THROUGH_LARGELY_UNVERIFIED",
    "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS",
    "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS",
    "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED",
)

# Rating-leakage patterns banned in composition plan claim texts
_PLAN_RATING_PATTERNS = [
    re.compile(r"\bmanagement quality is (weak|strong|mixed|poor|good|excellent)\b", re.IGNORECASE),
    re.compile(r"\bmanagement is (weak|strong|mixed|poor|good|excellent)\b", re.IGNORECASE),
    re.compile(r"\b(weak|strong|poor|excellent) management\b", re.IGNORECASE),
    re.compile(r"\b(disciplined|capable|competent|credible|effective|reliable|proven)\s+(management|execution)\b", re.IGNORECASE),
    re.compile(r"\bmanagement (execution )?quality is (high|good|strong|established|verified)\b", re.IGNORECASE),
    re.compile(r"overall management quality view is '(weak|strong|mixed|poor|good)'", re.IGNORECASE),
]

REPO = Path(__file__).resolve().parents[1]


# ── Low-level helpers ──────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_str(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:32]


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _file_digest(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# ── Fingerprint / identity ─────────────────────────────────────────────────────

def _compute_composition_policy_hash(policy: Dict[str, Any]) -> str:
    """Deterministic hash of the composition policy.

    Any material change to generation behavior (claim sources, prohibited patterns,
    descriptor enforcement, rating constraints) changes this hash and therefore the
    contract fingerprint.  Do not rely solely on a manually incremented version string.
    """
    raw = json.dumps(policy, sort_keys=True)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


COMPOSITION_POLICY_HASH = _compute_composition_policy_hash(COMPOSITION_POLICY)


def _compute_contract_fingerprint(
    prompt_version: str,
    schema_version: str,
    model: str,
    output_schema_version: str = OUTPUT_SCHEMA_VERSION,
    composition_policy_hash: Optional[str] = None,
    contract_v2_policy_digest: Optional[str] = None,
) -> str:
    """Deterministic fingerprint of the generation contract.

    Covers: prompt_version, unit_schema_version, model_policy, output_schema_version,
            generation_contract_schema, composition_policy_hash, contract_v2_policy_digest.
    composition_policy_hash encodes material generation-behavior policies (M45).
    contract_v2_policy_digest encodes management_answer_contract_v2, fact_pack schema,
        assembler policy, DPF policy, and EIV policy (M46.1).
    Does NOT include: timestamps, run IDs, local paths.
    """
    payload: Dict[str, Any] = {
        "prompt_version": prompt_version,
        "unit_schema_version": schema_version,
        "model_policy": model,
        "output_schema_version": output_schema_version,
        "generation_contract_schema": GENERATION_CONTRACT_SCHEMA,
        "composition_policy_hash": composition_policy_hash or COMPOSITION_POLICY_HASH,
    }
    # M46.1: include Contract V2 policy digest when available
    _cv2 = contract_v2_policy_digest if contract_v2_policy_digest is not None else _CONTRACT_V2_POLICY_DIGEST
    if _cv2:
        payload["contract_v2_policy_digest"] = _cv2
    raw = json.dumps(payload, sort_keys=True)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _compute_evidence_fingerprint(
    company: str,
    companies_root: Path,
) -> str:
    """Upstream evidence fingerprint for UNIT_TARGET."""
    from intelligence.regeneration_planner import (
        _load_dependency_registry,
        _upstream_combined_digest,
    )
    from intelligence.evidence_fingerprints import compute_company_fingerprints

    registry = _load_dependency_registry()
    current = compute_company_fingerprints(company, companies_root)
    current_modules = current.get("modules", {})
    return _upstream_combined_digest(UNIT_TARGET, current_modules, registry)


def compute_execution_id(
    company: str,
    unit: str,
    evidence_fp: str,
    contract_fp: str,
    output_schema_version: str = OUTPUT_SCHEMA_VERSION,
) -> str:
    """Deterministic execution identity.

    Same company + same evidence + same contract → identical ID.
    Evidence or contract change → different ID.
    Timestamps and run metadata do not affect identity.
    """
    raw = json.dumps(
        {
            "company": company,
            "unit": unit,
            "evidence_dependency_fingerprint": evidence_fp,
            "generation_contract_fingerprint": contract_fp,
            "output_schema_version": output_schema_version,
        },
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Behavioral descriptor derivation ──────────────────────────────────────────

def _is_progression_item_delivered(item: Dict[str, Any]) -> bool:
    _delivered_states = frozenset(
        ("DELIVERED", "CONFIRMED_DELIVERED", "COMPLETED", "FULLY_EXECUTED")
    )
    _delivered_statuses = frozenset(
        ("delivered", "confirmed_delivered", "completed", "fully_executed")
    )
    exec_states = item.get("exec_states") or []
    for es in exec_states:
        if es.get("execution_state") in _delivered_states:
            return True
    return item.get("current_status") in _delivered_statuses


def derive_behavioral_descriptor(
    management_progression_data: Dict[str, Any],
    capital_allocation_data: Dict[str, Any],
) -> Optional[str]:
    """Deterministically derive behavioral descriptor from canonical evidence.

    Returns None if evidence insufficient — does not fabricate.
    MUST NOT read or copy from the previous certified answer.
    """
    items = management_progression_data.get("progression_items", []) or []
    n_total = len(items)
    if n_total == 0:
        return None

    n_delivered = sum(1 for item in items if _is_progression_item_delivered(item))

    allocations = (capital_allocation_data.get("allocations") or []) if capital_allocation_data else []
    n_outcomes = len(allocations)
    _unattributed = frozenset(("none", "", "UNABLE_TO_ATTRIBUTE", "NOT_ATTRIBUTED"))
    n_attributed = sum(
        1 for a in allocations
        if (a.get("attribution_status") or "none") not in _unattributed
    )

    delivery_rate = n_delivered / n_total

    if delivery_rate < 0.1:
        return "FOLLOW_THROUGH_LARGELY_UNVERIFIED"
    if delivery_rate < 0.4:
        return "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS"
    if n_outcomes > 0 and n_attributed < n_outcomes * 0.5:
        return "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS"
    return "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED"


def _descriptor_derivation_trace(
    progression_data: Dict[str, Any],
    capital_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Produce a reproducible audit trace of behavioral descriptor derivation."""
    items = progression_data.get("progression_items", []) or []
    n_total = len(items)
    n_delivered = sum(1 for item in items if _is_progression_item_delivered(item))
    n_in_progress = sum(
        1 for item in items
        if item.get("current_status") in ("in_progress", "IN_PROGRESS")
        and not _is_progression_item_delivered(item)
    )
    allocations = (capital_data.get("allocations") or []) if capital_data else []
    _unattributed = frozenset(("none", "", "UNABLE_TO_ATTRIBUTE", "NOT_ATTRIBUTED"))
    n_attributed = sum(
        1 for a in allocations
        if (a.get("attribution_status") or "none") not in _unattributed
    )
    delivery_rate = n_delivered / n_total if n_total > 0 else 0.0
    descriptor = derive_behavioral_descriptor(progression_data, capital_data)
    rule = (
        "delivery_rate < 0.10" if delivery_rate < 0.1 else
        "0.10 <= delivery_rate < 0.40" if delivery_rate < 0.4 else
        f"delivery_rate >= 0.40, n_attributed ({n_attributed}) < 50% of n_outcomes ({len(allocations)})"
        if len(allocations) > 0 and n_attributed < len(allocations) * 0.5 else
        "delivery_rate >= 0.40, sufficient attribution"
    )
    return {
        "total_items": n_total,
        "delivered_count": n_delivered,
        "in_progress_count": n_in_progress,
        "undelivered_count": n_total - n_delivered,
        "delivery_rate": round(delivery_rate, 4),
        "allocation_total": len(allocations),
        "attributed_count": n_attributed,
        "rule_applied": rule,
        "descriptor_result": descriptor,
        "reproducible_without_ai": True,
        "source": "canonical_management_progression_evidence",
    }


# ── Composition plan builder ───────────────────────────────────────────────────

def build_management_quality_composition_plan(
    mq_summary: Dict[str, Any],
    behavioral_descriptor: Optional[str],
) -> Dict[str, Any]:
    """Build a composition plan from management quality summary.

    Fully deterministic — no LLM call.
    behavioral_descriptor: derived from canonical evidence, NOT from certified answer.
    COMPOSITION_POLICY governs what claims are included.
    """
    from intelligence.ask_intrinsiciq.relationship_aware_composer import build_composition_plan

    claims: List[Dict[str, Any]] = []
    cid = [0]

    def _add(text: str, source: str, confidence: str = "CONFIRMED") -> None:
        t = (text or "").strip()
        if not t:
            return
        cid[0] += 1
        claims.append({
            "claim_id": f"MQS-{cid[0]:03d}",
            "claim_text": t,
            "final_acceptance_status": "ACCEPT",
            "evidence_refs": [source],
            "causal_confidence": confidence,
        })

    _add(mq_summary.get("investor_implication", ""), "mq_summary.investor_implication")

    # overall_view excluded (COMPOSITION_POLICY.overall_view_in_plan = False)
    # Reason: 'weak' in claim text seeded MQ-R1 rating leakage in attempt 1.
    if COMPOSITION_POLICY["overall_direction_in_plan"] and mq_summary.get("overall_direction"):
        _add(
            f"Overall management trajectory: {mq_summary['overall_direction']}.",
            "mq_summary.overall_direction",
        )

    if mq_summary.get("strongest_dimension"):
        _add(
            f"The dimension with the most evidence-backed performance: {mq_summary['strongest_dimension']}.",
            "mq_summary.strongest_dimension",
        )
    if mq_summary.get("weakest_dimension"):
        _add(
            f"The dimension with the most evidence gaps: {mq_summary['weakest_dimension']}.",
            "mq_summary.weakest_dimension",
        )

    interp = mq_summary.get("interpretation") or {}
    if isinstance(interp, dict):
        # conclusion excluded — can contain prohibited rating language (see COMPOSITION_POLICY.claim_sources)
        for key in ("why_it_matters", "economic_mechanism"):
            val = interp.get(key, "")
            if val:
                _add(str(val), f"mq_summary.interpretation.{key}", "SUPPORTED")

    for item in (mq_summary.get("what_strengthened_conviction") or [])[:3]:
        if isinstance(item, dict):
            dim, summary = item.get("dimension", ""), item.get("summary", "")
            conf = "SUPPORTED" if item.get("confidence") in ("high", "medium") else "PLAUSIBLE"
            if dim and summary:
                _add(f"Evidence strengthened conviction in {dim}: {summary}.", f"mq_summary.strengthened.{dim}", conf)

    for item in (mq_summary.get("what_weakened_conviction") or [])[:3]:
        if isinstance(item, dict):
            dim, summary = item.get("dimension", ""), item.get("summary", "")
            conf = "SUPPORTED" if item.get("confidence") in ("high", "medium") else "PLAUSIBLE"
            if dim and summary:
                _add(f"Evidence weakened conviction in {dim}: {summary}.", f"mq_summary.weakened.{dim}", conf)

    # Behavioral descriptor: derived from canonical evidence, not from certified answer.
    if behavioral_descriptor:
        _add(
            f"The behavioral delivery descriptor derived from canonical management progression evidence is: "
            f"{behavioral_descriptor}. This descriptor MUST appear verbatim in the simple_answer.",
            "canonical_evidence.behavioral_descriptor",
            "CONFIRMED",
        )

    evidence_gaps = [
        {"gap_description": str(q)}
        for q in (mq_summary.get("unresolved_questions") or [])[:4]
        if q
    ]
    uncertainty_items = []
    for item in (mq_summary.get("what_remains_unproven") or [])[:3]:
        if isinstance(item, dict):
            dim, summary = item.get("dimension", ""), item.get("summary", "")
            text = f"{dim}: {summary}" if dim and summary else (dim or summary)
            if text:
                uncertainty_items.append(text)
        elif item:
            uncertainty_items.append(str(item))

    return build_composition_plan(claims, [], evidence_gaps, uncertainty_items)


# ── Static composition plan audit ─────────────────────────────────────────────

def audit_composition_plan_for_rating_leakage(
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Scan composition plan claim texts for prohibited rating-leakage patterns.

    Called BEFORE the LLM invocation.  Failures raise M452_COMPOSITION_PLAN_RATING_LEAKAGE.
    This prevents deterministic claim text from seeding MQ-R1 violations.
    """
    violations = []
    all_claims = (
        plan.get("allowed_claims", []) + plan.get("qualified_claims", [])
    )
    for claim in all_claims:
        text = claim.get("claim_text", "")
        for pat in _PLAN_RATING_PATTERNS:
            if pat.search(text):
                violations.append({
                    "claim_id": claim.get("claim_id"),
                    "pattern": pat.pattern,
                    "text_excerpt": text[:120],
                })
    return {"clean": len(violations) == 0, "violations": violations}


# ── Anchoring isolation check ──────────────────────────────────────────────────

def verify_no_previous_answer_in_generation_input(
    composition_plan: Dict[str, Any],
    certified_answer: Dict[str, Any],
) -> Dict[str, Any]:
    """Verify that no text from the certified answer entered the composition plan."""
    violations = []
    prev_answer = (
        (certified_answer.get("answers") or {})
        .get("how-good-is-management", {})
        .get("answer", {})
    )
    prev_simple = str(prev_answer.get("simple_answer") or "").strip()
    prev_key_points = [str(kp) for kp in (prev_answer.get("key_points") or [])]

    all_claims = (
        composition_plan.get("allowed_claims", [])
        + composition_plan.get("qualified_claims", [])
        + composition_plan.get("suppressed_claims", [])
    )
    for claim in all_claims:
        text = str(claim.get("claim_text", ""))
        if len(prev_simple) > 40 and prev_simple[:40] in text:
            violations.append(f"claim {claim.get('claim_id')}: contains previous simple_answer prefix")
        for kp in prev_key_points:
            if len(kp) > 30 and kp[:30] in text:
                violations.append(f"claim {claim.get('claim_id')}: contains previous key_point")
        for ref in claim.get("evidence_refs", []):
            if ref == "certified_answer.behavioral_descriptor":
                violations.append(f"claim {claim.get('claim_id')}: anchored to certified_answer.behavioral_descriptor")

    return {"isolated": len(violations) == 0, "violations": violations}


# ── Pre-execution gates ────────────────────────────────────────────────────────

def _verify_plan(plan_result: Dict[str, Any]) -> None:
    """Assert plan shows exactly 1 call for UNIT_TARGET and 0 for all others."""
    all_units = plan_result.get("units", plan_result.get("unit_plans", []))
    unit_map = {u["generation_unit"]: u for u in all_units}
    target = unit_map.get(UNIT_TARGET)
    if not target:
        raise RuntimeError(f"M45_GATE_FAIL: unit '{UNIT_TARGET}' not found in plan")
    if target.get("planned_ai_calls", 0) != 1:
        raise RuntimeError(
            f"M45_GATE_FAIL: M45_PRE_EXECUTION_CALL_PLAN must be 1, "
            f"got {target.get('planned_ai_calls')} (decision={target.get('decision')})"
        )
    for unit, up in unit_map.items():
        if unit != UNIT_TARGET and up.get("planned_ai_calls", 0) > 0:
            raise RuntimeError(
                f"M45_GATE_FAIL: unexpected planned call for unit '{unit}' "
                f"(calls={up['planned_ai_calls']}, decision={up.get('decision')})"
            )


def _find_prior_execution(manifest: Dict[str, Any], execution_id: str) -> Optional[Dict[str, Any]]:
    """Find a prior execution entry with this execution_id in history.  Returns None if not found."""
    for entry in manifest.get("execution_history", []):
        if entry.get("execution_id") == execution_id and entry.get("outcome") is not None:
            return entry
    # Backward-compat: flat manifest (pre-history format)
    if manifest.get("execution_id") == execution_id and manifest.get("outcome") is not None:
        return manifest
    return None


def _check_idempotency(manifest_path: Path, execution_id: str) -> bool:
    """Return True if this execution_id already has a completed outcome in history."""
    manifest = _load_json(manifest_path)
    return _find_prior_execution(manifest, execution_id) is not None


def _compute_plan_digest(plan: Dict[str, Any]) -> str:
    """Deterministic digest of composition plan content.

    Proves same evidence + same contract → same deterministic pre-LLM plan.
    Does NOT replace evidence_fp or contract_fp; is an observational invariant.
    """
    canonical = {
        "allowed_claims": [
            {"id": c.get("claim_id"), "text": c.get("claim_text")}
            for c in plan.get("allowed_claims", [])
        ],
        "qualified_claims": [
            {"id": c.get("claim_id"), "text": c.get("claim_text")}
            for c in plan.get("qualified_claims", [])
        ],
        "evidence_gaps": [g.get("gap_description") for g in plan.get("evidence_gaps", [])],
        "uncertainty_items": plan.get("uncertainty_items", []),
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode()
    ).hexdigest()[:32]


def _find_successful_execution_by_evidence(
    manifest: Dict[str, Any],
    evidence_fp: str,
) -> Optional[Dict[str, Any]]:
    """Find the most recent PACP_PASS execution with matching evidence_fp (any contract schema).

    Used for legacy-contract reuse when a newer contract schema would otherwise
    produce a different execution_id for an already-certified candidate.
    Only considers LIVE_EXECUTION and MIGRATED_FROM_FLAT_MANIFEST records.
    """
    for entry in reversed(manifest.get("execution_history", [])):
        if (
            entry.get("evidence_dependency_fingerprint") == evidence_fp
            and entry.get("outcome") == "PACP_PASS_AWAITING_HUMAN_REVIEW"
            and entry.get("manifest_record_origin") in (
                "LIVE_EXECUTION", "MIGRATED_FROM_FLAT_MANIFEST"
            )
        ):
            return entry
    return None


def _verify_candidate_integrity(
    entry: Dict[str, Any],
    candidate_dir: Path,
) -> Dict[str, Any]:
    """Verify the candidate file referenced by a manifest entry exists and matches its digest.

    Returns {"ok": bool, "candidate_path": str, "digest": str, "reason": str}.
    """
    stored_digest = entry.get("candidate_digest", "")
    # Try candidate_path (repo-relative), then candidate_filename, then legacy filename
    candidate_path: Optional[Path] = None
    for path_key in ("candidate_path", "candidate_filename"):
        val = entry.get(path_key)
        if not val:
            continue
        p = REPO / val if not Path(val).is_absolute() else Path(val)
        if not p.exists():
            p = candidate_dir / Path(val).name
        if p.exists():
            candidate_path = p
            break

    if candidate_path is None:
        legacy = candidate_dir / CANDIDATE_FILENAME
        if legacy.exists():
            candidate_path = legacy

    if candidate_path is None or not candidate_path.exists():
        return {"ok": False, "candidate_path": None, "digest": None,
                "reason": f"candidate file not found for entry {entry.get('execution_id')}"}

    actual_digest = _file_digest(candidate_path)
    if stored_digest and actual_digest != stored_digest:
        return {"ok": False, "candidate_path": str(candidate_path), "digest": actual_digest,
                "reason": f"digest mismatch: stored={stored_digest} actual={actual_digest}"}

    return {"ok": True, "candidate_path": str(candidate_path), "digest": actual_digest,
            "reason": None}


# ── Direct LLM call with telemetry ────────────────────────────────────────────

def _call_llm_with_telemetry(
    composition_plan: Dict[str, Any],
    model: str,
    behavioral_descriptor: Optional[str] = None,
    fact_pack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call the LLM for management synthesis, capturing full telemetry.

    Returns: {"answer": dict, "telemetry": dict, "error": str|None}
    """
    from intelligence.ask_intrinsiciq.relationship_aware_composer import (
        _build_composition_system_prompt,
        _strip_plan_meta,
    )
    from knowledge.ai import get_llm

    system_prompt = _build_composition_system_prompt(composition_plan, DOMAIN_QUESTION)
    evidence_lines = []
    all_claims = (
        composition_plan.get("allowed_claims", [])
        + composition_plan.get("qualified_claims", [])
    )[:10]
    for c in all_claims:
        evs = ", ".join(c.get("evidence_refs", [])[:3])
        evidence_lines.append(
            f"[{c.get('claim_id','?')}] {c.get('claim_text','?')}"
            + (f" (evidence: {evs})" if evs else "")
        )

    # Descriptor verbatim constraint (COMPOSITION_POLICY enforcement)
    _desc_hint = behavioral_descriptor or next(
        (_d for _c in all_claims for _d in _BEHAVIORAL_DESCRIPTORS if _d in _c.get("claim_text", "")),
        None,
    )

    # M47: Include deterministic DPF context in prompt (Contract V2)
    dpf_hint = ""
    if fact_pack and fact_pack.get("dpfs"):
        import json as _json
        dpfs_text = _json.dumps(fact_pack["dpfs"], indent=2)
        prog = fact_pack.get("progression_counts", {})
        dpf_hint = (
            f"\nDETERMINISTIC PRECISION FACTS (already computed from canonical evidence — "
            f"reference these in your what_evidence_shows; they will be injected into "
            f"deterministic_precision_facts automatically):\n{dpfs_text}\n"
            f"Progression counts: {prog.get('total',0)} items total, "
            f"{prog.get('delivered',0)} delivered, "
            f"{prog.get('in_progress',0)} in_progress, "
            f"{prog.get('announced',0)} announced\n"
        )

    user_content = (
        f"Company: Sun Pharma\n"
        f"Question: {DOMAIN_QUESTION}\n\n"
        "Validated claims:\n"
        + "\n".join(evidence_lines)
        + "\n\n"
        + dpf_hint
        + (
            f"MANDATORY CONSTRAINT: The string '{_desc_hint}' MUST appear verbatim in your simple_answer field.\n"
            if _desc_hint else ""
        )
        + "MANDATORY CONSTRAINT: Do NOT use phrases like 'management quality is weak/strong/mixed', "
        "'management is capable/credible/disciplined/effective', 'weak management', 'strong management', "
        "or any numeric/letter grade rating for management quality. "
        "Use factual, evidence-based language about delivery counts, progression states, "
        "attribution status, and commitment evidence only.\n"
        "\nGenerate the investor answer as a JSON object following the composition contract."
        " Include what_evidence_shows (2+ entries) and what_may_mean_economically fields."
    )

    _SCHEMA = {
        "type": "object",
        "required": ["simple_answer", "why_it_matters", "investor_interpretation", "key_points"],
        "properties": {
            "simple_answer": {"type": "string"},
            "why_it_matters": {"type": "string"},
            "investor_interpretation": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "what_evidence_shows": {"type": "array", "items": {"type": "string"}},
            "what_may_mean_economically": {"type": "string"},
            "what_management_says": {"type": "string"},
            "where_management_was_consistent": {"type": "string"},
        },
        "additionalProperties": False,
    }

    telemetry: Dict[str, Any] = {
        "provider": "openai", "model": model,
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
        "latency_ms": None, "success": False, "error": None,
    }
    answer: Dict[str, Any] = {}
    error_msg: Optional[str] = None

    try:
        llm = get_llm(model=model)
        response = llm.generate(
            prompt=user_content,
            response_schema=_SCHEMA,
            max_tokens=MAX_OUTPUT_TOKENS,
            system_prompt=system_prompt,
        )
        telemetry["provider"] = getattr(response, "provider", "openai")
        telemetry["model"] = getattr(response, "model", model)
        telemetry["input_tokens"] = getattr(response, "prompt_tokens", None)
        telemetry["output_tokens"] = getattr(response, "completion_tokens", None)
        telemetry["total_tokens"] = getattr(response, "total_tokens", None)
        telemetry["latency_ms"] = round(getattr(response, "latency_ms", 0.0), 1)
        telemetry["success"] = True
        raw = response.text if hasattr(response, "text") else str(response)
        answer = json.loads(raw.strip())
    except Exception as exc:
        error_msg = str(exc)
        telemetry["error"] = error_msg
        answer = {"_composition_error": error_msg}

    if not answer.get("_composition_error"):
        from intelligence.ask_intrinsiciq.relationship_aware_composer import _strip_plan_meta
        answer["claims"] = [
            _strip_plan_meta(c)
            for c in (
                composition_plan.get("allowed_claims", [])
                + composition_plan.get("qualified_claims", [])
            )
        ]
        answer["relationships"] = [
            _strip_plan_meta(r)
            for r in (
                composition_plan.get("allowed_relationships", [])
                + composition_plan.get("qualified_relationships", [])
                + composition_plan.get("unknown_relationships", [])
                + composition_plan.get("suppressed_relationships", [])
            )
        ]
        answer["evidence_gaps"] = composition_plan.get("evidence_gaps", [])

    return {"answer": answer, "telemetry": telemetry, "error": error_msg}


# ── Semantic diff ──────────────────────────────────────────────────────────────

def _semantic_diff(
    certified_answer: Dict[str, Any],
    candidate_answer: Dict[str, Any],
) -> Dict[str, Any]:
    prev_ans = (
        (certified_answer.get("answers") or {})
        .get("how-good-is-management", {})
        .get("answer", {})
    )
    prev_simple = str(prev_ans.get("simple_answer") or "").strip()
    new_simple = str(candidate_answer.get("simple_answer") or "").strip()
    prev_kps = [str(k) for k in (prev_ans.get("key_points") or [])]
    new_kps = [str(k) for k in (candidate_answer.get("key_points") or [])]

    diff_classes = []
    if prev_simple != new_simple:
        diff_classes.append("STRUCTURAL_PRESENTATION" if prev_simple.lower() != new_simple.lower() else "WORDING_ONLY")

    prev_set, new_set = set(prev_kps), set(new_kps)
    if new_set - prev_set:
        diff_classes.append("CLAIM_ADDED")
    if prev_set - new_set:
        diff_classes.append("CLAIM_REMOVED")

    prev_desc = next((d for d in _BEHAVIORAL_DESCRIPTORS if d in prev_simple), None)
    new_desc = next((d for d in _BEHAVIORAL_DESCRIPTORS if d in new_simple), None)
    if prev_desc != new_desc:
        diff_classes.append("BEHAVIOR_DESCRIPTOR_CHANGE")

    _uncertainty_markers = ("not established", "cannot", "uncertain", "unverified", "unable to verify")
    prev_u = sum(1 for m in _uncertainty_markers if m in prev_simple.lower())
    new_u = sum(1 for m in _uncertainty_markers if m in new_simple.lower())
    if new_u < prev_u:
        diff_classes.append("UNCERTAINTY_CHANGE")

    if not diff_classes:
        diff_classes.append("WORDING_ONLY")

    return {
        "diff_classes": diff_classes,
        "prev_simple_answer_preview": prev_simple[:200],
        "new_simple_answer_preview": new_simple[:200],
        "prev_key_points_count": len(prev_kps),
        "new_key_points_count": len(new_kps),
        "prev_descriptor": prev_desc,
        "new_descriptor": new_desc,
        "potential_regression": "UNCERTAINTY_CHANGE" in diff_classes and new_u < prev_u,
    }


# ── Main execution ─────────────────────────────────────────────────────────────

# Known attempt-1 reconstruction data (manifest was deleted during M45.2 development)
_ATTEMPT_1_RECONSTRUCTION = {
    "attempt": 1,
    "manifest_record_origin": "RECONSTRUCTED_FROM_EXECUTION_EVIDENCE",
    "executed_at": "2026-10-05T00:00:00Z",  # approximate — exact time lost with manifest
    "execution_id": "sha256:1301fe09d781e2fef373ff2866a52949",
    "evidence_dependency_fingerprint": "sha256:6793736f4298b82142d39d0439f299d7c11f0310ada29ff0a9cc99fac06c2aad",
    "generation_contract_fingerprint": "sha256:a626ea1610a99499aa11614d44774a4d",
    "composition_policy_version": "m45_composition_v1",
    "model": "gpt-4o-mini",
    "provider": "openai",
    "prompt_version": "2",
    "dry_run": False,
    "ai_calls_attempted": 1,
    "ai_calls_executed": 1,
    "ai_calls_failed": 0,
    "telemetry": {
        "input_tokens": "UNKNOWN_MANIFEST_DELETED",
        "output_tokens": "UNKNOWN_MANIFEST_DELETED",
        "total_tokens": "UNKNOWN_MANIFEST_DELETED",
        "latency_ms": "UNKNOWN_MANIFEST_DELETED",
        "success": True,
        "error": None,
    },
    "pacp_result": {
        "overall": "FAIL",
        "fails": ["check_mq_no_rating_leakage", "check_mq_behavioral_descriptor_present"],
        "mq_r1_rating_leakage": "FAIL",
        "mq_r2_behavioral_descriptor": "FAIL",
        "warns": [],
        "root_cause": (
            "COMPOSITION_POLICY_V1 passed overall_view:'weak' to LLM, causing MQ-R1 rating leakage. "
            "Descriptor enforcement was insufficient for MQ-R2."
        ),
    },
    "candidate_written": False,
    "candidate_path": None,
    "candidate_digest": "NOT_WRITTEN_PACP_FAIL",
    "outcome": "PACP_FAIL_CANDIDATE_REJECTED",
    "approval": False,
    "activation": False,
    "certified_artifact_mutated": False,
    "reconstruction_evidence": [
        "CLI output showing execution_id and PACP fails",
        "evidence_fp and contract_fp from stdout pre-call checkpoint",
        "PACP fail names: check_mq_no_rating_leakage, check_mq_behavioral_descriptor_present",
        "model=gpt-4o-mini from OPENAI_MODEL env / executor default",
        "manifest was deleted during M45.2 development (before reconstruction mandate)",
    ],
}


def _ensure_attempt1_history(manifest: Dict[str, Any]) -> bool:
    """Ensure attempt-1 reconstruction (PACP_FAIL) is present. Returns True if added.

    Checks both execution_id AND outcome: the same execution_id may appear as both
    a PACP_FAIL (attempt 1) and a PACP_PASS (attempt 2) since M45.1 fixed the composition
    plan without changing the contract fingerprint.
    """
    target_id = _ATTEMPT_1_RECONSTRUCTION["execution_id"]
    target_outcome = _ATTEMPT_1_RECONSTRUCTION["outcome"]
    for entry in manifest.get("execution_history", []):
        if entry.get("execution_id") == target_id and entry.get("outcome") == target_outcome:
            return False
    manifest.setdefault("execution_history", []).insert(0, _ATTEMPT_1_RECONSTRUCTION)
    return True


def run_regeneration(
    company: str = "sun_pharma",
    companies_root: Path = REPO / "companies",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Execute one controlled AI regeneration for UNIT_TARGET.

    History-preserving: appends to execution_history; never overwrites prior attempts.
    Raises on any security gate failure.
    """
    from intelligence.regeneration_planner import (
        plan_regeneration,
        UNIT_PROMPT_VERSIONS,
        UNIT_SCHEMA_VERSIONS,
        PROMPT_VERSION_CHANGED,
    )
    from pipelines.pacp_adversarial import run_adversarial_suite
    import os

    company_root = Path(companies_root) / company
    candidate_dir = company_root / "company_memory" / "ask_intrinsiciq"
    manifest_path = candidate_dir / MANIFEST_FILENAME
    certified_path = company_root / CERTIFIED_ARTIFACT_PATH

    # ── Load or initialize manifest ────────────────────────────────────────────
    raw_manifest = _load_json(manifest_path)
    if "execution_history" not in raw_manifest:
        # M45.3: migrate flat manifest to history-preserving format
        # MUST preserve existing execution entry — never discard a successful execution
        history: List[Dict[str, Any]] = []
        if raw_manifest.get("execution_id") and raw_manifest.get("outcome") is not None:
            migrated = dict(raw_manifest)
            migrated["manifest_record_origin"] = "MIGRATED_FROM_FLAT_MANIFEST"
            migrated["contract_identity_schema"] = "LEGACY_M45_1"  # pre-composition_policy_hash scheme
            migrated["migration_note"] = (
                "Migrated from flat manifest (schema_version m45_manifest_v2). "
                "contract_fp uses pre-composition_policy_hash scheme (LEGACY_M45_1)."
            )
            history = [migrated]
        manifest = {
            "schema_version": "m45_manifest_v3",
            "mission": "ENG-MISSION45",
            "company": company,
            "unit": UNIT_TARGET,
            "question_id": QUESTION_ID,
            "execution_history": history,
        }
    else:
        manifest = raw_manifest

    # Ensure attempt-1 reconstruction (PACP_FAIL) is present — M45.2/M45.3 no-erasure policy
    _ensure_attempt1_history(manifest)

    # ── Generation contract ────────────────────────────────────────────────────
    prompt_version = UNIT_PROMPT_VERSIONS.get(UNIT_TARGET, "1")
    schema_version = UNIT_SCHEMA_VERSIONS.get(UNIT_TARGET, "1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # ── Fingerprints ───────────────────────────────────────────────────────────
    # MUST happen before plan construction — execution_id lookup gates plan build
    evidence_fp = _compute_evidence_fingerprint(company, Path(companies_root))
    contract_fp = _compute_contract_fingerprint(prompt_version, schema_version, model)
    execution_id = compute_execution_id(company, UNIT_TARGET, evidence_fp, contract_fp)
    eid_short = execution_id.replace("sha256:", "")[:12]

    # ── Candidate path uses execution_id to avoid overwriting prior attempts ──
    candidate_filename = CANDIDATE_FILENAME_TEMPLATE.format(eid_short=eid_short)
    candidate_path = candidate_dir / candidate_filename
    assert candidate_path.resolve() != certified_path.resolve(), (
        "SECURITY VIOLATION: candidate path equals certified artifact path"
    )

    # ── Idempotency — MUST happen before plan construction ────────────────────
    # M45.3: check for successful execution (any contract schema) BEFORE building plan
    prior_success = _find_successful_execution_by_evidence(manifest, evidence_fp)
    if prior_success is not None:
        is_exact_contract = prior_success.get("generation_contract_fingerprint") == contract_fp
        if not is_exact_contract:
            # Contract upgraded (M47+): fall through to fresh execution
            print(
                f"[M47] CONTRACT_UPGRADE_DETECTED: prior_contract={prior_success.get('generation_contract_fingerprint')} "
                f"new_contract={contract_fp} — proceeding with fresh execution"
            )
        else:
            # Same contract + same evidence → idempotent reuse
            integrity = _verify_candidate_integrity(prior_success, candidate_dir)
            if not integrity["ok"]:
                return {
                    "decision": "EXISTING_EXECUTION_ARTIFACT_INTEGRITY_FAILURE",
                    "reason": integrity["reason"],
                    "execution_id": prior_success.get("execution_id"),
                    "evidence_fp": evidence_fp,
                    "execution_history": manifest.get("execution_history", []),
                }
            print(
                f"[M45.3] REUSE_EXISTING_GENERATION (EXACT_CONTRACT_MATCH): "
                f"existing_execution_id={prior_success.get('execution_id')} "
                f"candidate_intact=true review_state=AWAITING_HUMAN_REVIEW provider_calls=0"
            )
            return {
                "decision": "REUSE_EXISTING_GENERATION",
                "reuse_type": "EXACT_CONTRACT_MATCH",
                "existing_execution_id": prior_success.get("execution_id"),
                "new_execution_id": execution_id,
                "contract_identity_schema": prior_success.get("contract_identity_schema", "LIVE_EXECUTION"),
                "evidence_fp": evidence_fp,
                "candidate_path": integrity["candidate_path"],
                "candidate_digest": integrity["digest"],
                "pacp_overall": "PASS",
                "review_state": "AWAITING_HUMAN_REVIEW",
                "provider_calls": 0,
                "execution_history": manifest.get("execution_history", []),
            }

    # Check for failed execution with exact execution_id — no automatic retry
    prior_exact = _find_prior_execution(manifest, execution_id)
    if prior_exact is not None and prior_exact.get("outcome") == "PACP_FAIL_CANDIDATE_REJECTED":
        prior_ai_executed = prior_exact.get("ai_calls_executed", 0)
        prior_ai_failed = prior_exact.get("ai_calls_failed", 0)
        if prior_ai_executed == 0 and prior_ai_failed > 0:
            # Prior attempt: AI call failed at API level (no LLM content produced).
            # PACP failure was on an error stub, not on actual LLM output — allow retry.
            print(
                f"[M47] PRIOR_API_FAILURE_RETRY_ALLOWED: execution_id={execution_id} "
                f"ai_calls_executed={prior_ai_executed} ai_calls_failed={prior_ai_failed} "
                f"— API-level failure, no LLM content was evaluated; retry permitted"
            )
        else:
            print(
                f"[M45.3] EXISTING_FAILED_EXECUTION: execution_id={execution_id} "
                f"outcome={prior_exact.get('outcome')} — new contract required to retry"
            )
            return {
                "decision": "EXISTING_FAILED_EXECUTION_REQUIRES_NEW_CONTRACT_OR_EXPLICIT_RETRY_POLICY",
                "execution_id": execution_id,
                "prior_outcome": prior_exact.get("outcome"),
                "execution_history": manifest.get("execution_history", []),
            }

    attempt_number = len(manifest["execution_history"]) + 1

    # ── Regeneration plan ─────────────────────────────────────────────────────
    plan_result = plan_regeneration(
        company_slug=company,
        companies_root=companies_root,
        forced_reasons={UNIT_TARGET: [PROMPT_VERSION_CHANGED]},
        prompt_versions={UNIT_TARGET: prompt_version},
    )
    _verify_plan(plan_result)
    all_units = plan_result.get("units", plan_result.get("unit_plans", []))
    unit_plans = {u["generation_unit"]: u for u in all_units}
    plan_unit_id = unit_plans[UNIT_TARGET].get("plan_unit_id", "unknown")

    # ── Canonical evidence ────────────────────────────────────────────────────
    mq_summary_path = company_root / "company_memory" / "management_quality" / "management_quality_summary.json"
    mq_summary = _load_json(mq_summary_path)
    if not mq_summary:
        raise RuntimeError(f"M45_GATE_FAIL: management_quality_summary not found at {mq_summary_path}")

    progression_path = company_root / "company_memory" / "management_progression" / "management_progression.json"
    capital_path = company_root / "company_memory" / "capital_allocation_outcomes" / "capital_allocation_outcomes.json"
    progression_data = _load_json(progression_path)
    capital_data = _load_json(capital_path)

    # ── Behavioral descriptor — derived independently from canonical evidence ──
    behavioral_descriptor = derive_behavioral_descriptor(progression_data, capital_data)
    derivation_trace = _descriptor_derivation_trace(progression_data, capital_data)

    # ── Composition plan ──────────────────────────────────────────────────────
    composition_plan = build_management_quality_composition_plan(mq_summary, behavioral_descriptor)
    if not composition_plan.get("allowed_claims") and not composition_plan.get("qualified_claims"):
        raise RuntimeError("M45_GATE_FAIL: composition plan has no claims")

    # ── Composition plan digest (M45.3: observational invariant) ─────────────
    plan_digest = _compute_plan_digest(composition_plan)

    # ── Static plan audit (before any tokens are spent) ───────────────────────
    plan_audit = audit_composition_plan_for_rating_leakage(composition_plan)
    if not plan_audit["clean"]:
        raise RuntimeError(
            f"M452_COMPOSITION_PLAN_RATING_LEAKAGE: {plan_audit['violations']}"
        )

    # ── M47: Build deterministic fact pack before AI call ─────────────────────
    try:
        from intelligence.management_quality.fact_pack import build_management_quality_fact_pack
        fact_pack = build_management_quality_fact_pack(company, company_root / "company_memory")
    except Exception as _fp_err:
        print(f"[M47] WARNING: fact_pack build failed: {_fp_err} — proceeding without")
        fact_pack = None

    # ── Previous-answer isolation check ───────────────────────────────────────
    certified_answer_data = _load_json(certified_path)
    isolation_check = verify_no_previous_answer_in_generation_input(composition_plan, certified_answer_data)
    if not isolation_check["isolated"]:
        raise RuntimeError(
            f"M45_PREVIOUS_ANSWER_ANCHORING_DETECTED: {isolation_check['violations']}"
        )

    # ── Evidence invariance check ──────────────────────────────────────────────
    # Only compare against a prior LIVE execution; reconstructed records have uncertain evidence_fp.
    prior_live = next(
        (e for e in reversed(manifest["execution_history"])
         if e.get("manifest_record_origin") == "LIVE_EXECUTION"
         and e.get("evidence_dependency_fingerprint")),
        None,
    )
    if prior_live:
        prior_ev_fp = prior_live["evidence_dependency_fingerprint"]
        if prior_ev_fp != evidence_fp:
            raise RuntimeError(
                f"M45_EVIDENCE_DRIFT_DURING_CANARY: evidence_fp changed since last live execution. "
                f"prior={prior_ev_fp} current={evidence_fp}"
            )

    # ── Certified artifact snapshot (before) ──────────────────────────────────
    certified_digest_before = _file_digest(certified_path)

    # ── Pre-call checkpoint ────────────────────────────────────────────────────
    print(f"[M45.3] PRE-CALL CHECKPOINT:")
    print(f"  MISSION                                = M45.3")
    print(f"  ATTEMPT                                = {attempt_number}")
    print(f"  COMPANY                                = {company}")
    print(f"  GENERATION_UNIT                        = {UNIT_TARGET}")
    print(f"  IDEMPOTENCY_CHECK_ORDER                = fingerprints → execution_id → lookup → plan_build")
    print(f"  COMPOSITION_PLAN_NONDETERMINISM        = false (conclusion excluded)")
    print(f"  PLANNED_CALLS_THIS_ATTEMPT             = 1")
    print(f"  MAX_ALLOWED_CALLS_THIS_ATTEMPT         = {MAX_EXECUTED_AI_CALLS}")
    print(f"  RETRIES                                = {RETRY_COUNT}")
    print(f"  PREVIOUS_ANSWER_USED_AS_GENERATION_INPUT = false (verified)")
    print(f"  DESCRIPTOR_DERIVED_FROM_CANONICAL_EVIDENCE = true")
    print(f"  CURRENT_CERTIFIED_ARTIFACT_PROTECTED   = true")
    print(f"  PACP_BYPASS                            = false")
    print(f"  AUTO_APPROVAL                          = false")
    print(f"  AUTO_ACTIVATION                        = false")
    print(f"  UI_AI_CALL_PATH                        = false")
    print(f"  evidence_fp                            = {evidence_fp}")
    print(f"  contract_fp                            = {contract_fp}")
    print(f"  execution_id                           = {execution_id}")
    print(f"  plan_digest                            = {plan_digest}")
    print(f"  model                                  = {model}")
    print(f"  behavioral_descriptor                  = {behavioral_descriptor}")
    print(f"  composition_policy_hash                = {COMPOSITION_POLICY_HASH}")

    # ── AI call ────────────────────────────────────────────────────────────────
    ai_calls_executed = 0
    ai_calls_failed = 0
    answer: Dict[str, Any] = {}
    telemetry: Dict[str, Any] = {
        "provider": "openai", "model": model,
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
        "latency_ms": None, "success": False, "error": None,
    }

    if dry_run:
        answer = {
            "simple_answer": "[DRY_RUN] No AI call made.",
            "why_it_matters": "",
            "investor_interpretation": "",
            "key_points": ["dry_run=True"],
            "_dry_run": True,
        }
        telemetry["success"] = True
    else:
        result = _call_llm_with_telemetry(composition_plan, model, behavioral_descriptor, fact_pack)
        answer = result["answer"]
        telemetry = result["telemetry"]
        if result["error"] or answer.get("_composition_error"):
            ai_calls_failed = 1
        else:
            ai_calls_executed = 1

    # ── M47: Contract V2 assembly — inject deterministic fields ──────────────
    if not answer.get("_composition_error") and not answer.get("_dry_run") and fact_pack:
        try:
            from intelligence.management_quality.assembler import assemble_contract_v2_answer
            answer = assemble_contract_v2_answer(answer, fact_pack)
        except Exception as _asm_err:
            print(f"[M47] WARNING: assembler failed: {_asm_err} — DPFs may be absent")

    # ── PACP ──────────────────────────────────────────────────────────────────
    pacp_result = run_adversarial_suite(answer=answer, company=company, question_id=QUESTION_ID)
    pacp_overall = pacp_result.get("overall", "INCOMPLETE")

    # ── M47: EIV gate ─────────────────────────────────────────────────────────
    eiv_result: Dict[str, Any] = {}
    eiv_overall = "NOT_RUN"
    try:
        from intelligence.external_investor_value_validator import validate_management_answer_eiv
        eiv_result = validate_management_answer_eiv(answer)
        eiv_overall = eiv_result.get("overall", "FAIL")
    except Exception as _eiv_err:
        print(f"[M47] WARNING: EIV validation failed: {_eiv_err} — treating as FAIL")
        eiv_result = {"overall": "FAIL", "_error": str(_eiv_err)}
        eiv_overall = "FAIL"

    # ── Write candidate (per execution_id, only on PACP PASS/WARN) ───────────
    candidate_digest = "NOT_WRITTEN"
    eligibility_result: Dict[str, Any] = {}
    eligibility_state = "NOT_EVALUATED"
    if pacp_overall in ("PASS", "WARN") and not dry_run:
        # Write preliminary candidate (eligibility evaluated after, uses digest)
        candidate = {
            "schema_version": "m47_candidate_v1",
            "mission": "ENG-MISSION47",
            "attempt": attempt_number,
            "company": company,
            "unit": UNIT_TARGET,
            "question_id": QUESTION_ID,
            "execution_id": execution_id,
            "executed_at": _utc_now(),
            "prompt_version": prompt_version,
            "model": telemetry.get("model", model),
            "pacp_overall": pacp_overall,
            "eiv_overall": eiv_overall,
            "behavioral_descriptor": behavioral_descriptor,
            "composition_policy_version": COMPOSITION_POLICY["version"],
            "answer": answer,
        }
        _write_json(candidate_path, candidate)
        candidate_digest = _file_digest(candidate_path)

        # ── M47: Release eligibility (after write so digest is available) ────
        try:
            from intelligence.management_quality.candidate_eligibility import evaluate_candidate_release_eligibility
            eligibility_result = evaluate_candidate_release_eligibility(
                candidate={**candidate, "candidate_digest": candidate_digest},
                pacp_result=pacp_result,
                eiv_result=eiv_result,
            )
            eligibility_state = eligibility_result.get("eligibility_state", "NOT_EVALUATED")
        except Exception as _elig_err:
            print(f"[M47] WARNING: eligibility evaluation failed: {_elig_err}")
            eligibility_result = {"eligible": False, "eligibility_state": "BLOCKED_MULTIPLE", "_error": str(_elig_err)}
            eligibility_state = "BLOCKED_MULTIPLE"

        # Patch eligibility state into candidate file
        candidate["eligibility_state"] = eligibility_state
        _write_json(candidate_path, candidate)
        candidate_digest = _file_digest(candidate_path)

    # ── Verify certified artifact untouched ───────────────────────────────────
    certified_digest_after = _file_digest(certified_path)
    if certified_digest_before != certified_digest_after:
        raise RuntimeError(
            f"SECURITY VIOLATION: certified artifact mutated. "
            f"before={certified_digest_before} after={certified_digest_after}"
        )

    # ── Semantic diff ──────────────────────────────────────────────────────────
    semantic_diff = _semantic_diff(certified_answer_data, answer)

    # ── Build attempt entry ────────────────────────────────────────────────────
    def _rel(p: Path) -> str:
        return str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p)

    if pacp_overall not in ("PASS", "WARN"):
        outcome = "PACP_FAIL_CANDIDATE_REJECTED"
    elif dry_run:
        outcome = "DRY_RUN_COMPLETE"
    elif eligibility_state == "HUMAN_REVIEW_ELIGIBLE":
        outcome = "PACP_PASS_EIV_PASS_AWAITING_HUMAN_REVIEW"
    elif eligibility_state == "BLOCKED_EIV":
        outcome = "PACP_PASS_EIV_FAIL_BLOCKED"
    else:
        outcome = f"PACP_PASS_BLOCKED_{eligibility_state}"

    attempt_entry: Dict[str, Any] = {
        "attempt": attempt_number,
        "manifest_record_origin": "LIVE_EXECUTION",
        "execution_id": execution_id,
        "executed_at": _utc_now(),
        "prompt_version": prompt_version,
        "schema_version_unit": schema_version,
        "model": telemetry.get("model", model),
        "provider": telemetry.get("provider", "openai"),
        "dry_run": dry_run,
        "plan_unit_id": plan_unit_id,
        "ai_calls_attempted": 0 if dry_run else 1,
        "ai_calls_executed": ai_calls_executed,
        "ai_calls_failed": ai_calls_failed,
        "telemetry": telemetry,
        "evidence_dependency_fingerprint": evidence_fp,
        "generation_contract_fingerprint": contract_fp,
        "composition_policy_version": COMPOSITION_POLICY["version"],
        "composition_policy_hash": COMPOSITION_POLICY_HASH,
        "behavioral_descriptor": behavioral_descriptor,
        "behavioral_descriptor_source": "canonical_management_progression_evidence",
        "behavioral_descriptor_derivation": derivation_trace,
        "previous_answer_isolation": isolation_check,
        "composition_plan_digest": plan_digest,
        "composition_plan_audit": plan_audit,
        "composition_plan_summary": {
            "allowed_claims": len(composition_plan.get("allowed_claims", [])),
            "qualified_claims": len(composition_plan.get("qualified_claims", [])),
            "suppressed_claims": len(composition_plan.get("suppressed_claims", [])),
            "evidence_gaps": len(composition_plan.get("evidence_gaps", [])),
        },
        "pacp_result": {
            "overall": pacp_overall,
            "named_checks": pacp_result.get("named_checks", 0),
            "fails": pacp_result.get("fails", []),
            "warns": pacp_result.get("warns", []),
            "skips": pacp_result.get("skips", []),
            "incomplete": pacp_result.get("incomplete", []),
            "mq_r1_rating_leakage": (
                "PASS" if "check_mq_no_rating_leakage" not in pacp_result.get("fails", []) else "FAIL"
            ),
            "mq_r2_behavioral_descriptor": (
                "PASS" if "check_mq_behavioral_descriptor_present" not in pacp_result.get("fails", []) else "FAIL"
            ),
        },
        "eiv_result": {
            "overall": eiv_overall,
            "fail_count": eiv_result.get("fail_count", 0),
            "fails": eiv_result.get("fails", []),
        },
        "eligibility_result": {
            "eligible": eligibility_result.get("eligible", False),
            "eligibility_state": eligibility_state,
            "blocks": eligibility_result.get("blocks", []),
        },
        "semantic_diff": semantic_diff,
        "certified_artifact_path": _rel(certified_path),
        "certified_artifact_digest_before": certified_digest_before,
        "certified_artifact_digest_after": certified_digest_after,
        "certified_artifact_mutated": certified_digest_before != certified_digest_after,
        "candidate_path": _rel(candidate_path) if pacp_overall in ("PASS", "WARN") and not dry_run else None,
        "candidate_filename": candidate_filename,
        "candidate_digest": candidate_digest,
        "outcome": outcome,
        "approval": False,
        "activation": False,
        "m45_security_constraints": {
            "max_executed_ai_calls": MAX_EXECUTED_AI_CALLS,
            "retry_count": RETRY_COUNT,
            "self_approval": False,
            "automatic_activation": False,
            "approve_mode_invoked": False,
            "activate_mode_invoked": False,
        },
    }

    # ── Append to history (never overwrite) ───────────────────────────────────
    manifest["execution_history"].append(attempt_entry)
    manifest["last_updated"] = _utc_now()
    manifest["total_attempts"] = len(manifest["execution_history"])
    manifest["total_ai_calls_m45_family"] = sum(
        e.get("ai_calls_executed", 0)
        for e in manifest["execution_history"]
        if e.get("manifest_record_origin") != "RECONSTRUCTED_FROM_EXECUTION_EVIDENCE"
    ) + 1  # +1 for reconstructed attempt 1

    _write_json(manifest_path, manifest)
    return manifest


# ── Contract V3 additions (ENG-MISSION49) ─────────────────────────────────────

GENERATION_CONTRACT_SCHEMA_V3 = "m49_contract_v3"

# M48 canonical values — corrected in M49 bookkeeping pass
_M48_PLANNED_EXECUTION_ID = "sha256:041d464fe52ecec5329eaf728d93a40ed39ca84c4e1ce5670894b6cbfca989aa"
_M48_EVIDENCE_FP = "sha256:6793736f4298b82142d39d0439f299d7c11f0310ada29ff0a9cc99fac06c2aad"
_M48_CONTRACT_V3_FP = "sha256:f79d63a8a0788c1e22ed8acd455e51a8a2d964a5b5ebd1402b757cdc983c438b"


def compute_execution_id_v3(
    company: str,
    unit: str,
    evidence_fp: str,
    contract_fp: str,
    output_schema_version: str = OUTPUT_SCHEMA_VERSION,
) -> str:
    """Full SHA-256 execution identity for Contract V3 (ENG-MISSION49).

    Unlike compute_execution_id (M45, truncated 32 chars), this preserves the
    full digest to match the M48 planned execution ID computation.
    """
    raw = json.dumps(
        {
            "company": company,
            "unit": unit,
            "evidence_dependency_fingerprint": evidence_fp,
            "generation_contract_fingerprint": contract_fp,
            "output_schema_version": output_schema_version,
        },
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _validate_contract_v3_structure(answer: Dict[str, Any]) -> Dict[str, Any]:
    """Validate all required Contract V3 sections are present and non-empty."""
    # Contract V3 required fields (M48 spec). why_it_matters / investor_interpretation
    # are V1/V2 LLM-narrative fields not promoted to required by Contract V3.
    REQUIRED = [
        "simple_answer", "key_points",
        "what_evidence_shows", "what_management_says",
        "where_management_was_consistent", "management_consistency_map",
        "what_is_not_yet_proven", "what_to_monitor",
        "what_may_mean_economically", "deterministic_precision_facts",
        "behavioral_descriptor",
    ]
    fails = []
    for field in REQUIRED:
        val = answer.get(field)
        if val is None:
            fails.append(f"{field}: MISSING")
        elif isinstance(val, (list, dict)) and len(val) == 0:
            fails.append(f"{field}: EMPTY")
        elif isinstance(val, str) and not val.strip():
            fails.append(f"{field}: EMPTY_STRING")
    return {"valid": len(fails) == 0, "fails": fails, "required_count": len(REQUIRED)}


def _five_capability_preflight(fact_pack_v2: Dict[str, Any]) -> Dict[str, Any]:
    """Verify 5 previously-missing M47 capabilities are deterministically pre-generated."""
    results = {
        "what_evidence_shows": bool(fact_pack_v2.get("evidence_observations")),
        "what_management_says": bool(fact_pack_v2.get("management_statements")),
        "where_management_was_consistent": bool(fact_pack_v2.get("consistency_observations")),
        "management_consistency_map": bool(fact_pack_v2.get("consistency_map")),
        "what_may_mean_economically": fact_pack_v2.get("npm") is not None,
    }
    all_present = all(results.values())
    return {
        "all_present": all_present,
        "capabilities": results,
        "ALL_FIVE_CAPABILITIES_PREGENERATED_OR_ASSEMBLER_GUARANTEED": all_present,
    }


def _call_llm_v3(
    composition_plan: Dict[str, Any],
    model: str,
    behavioral_descriptor: Optional[str] = None,
    fact_pack_v2: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """V3 LLM call — requests all Contract V3 narrative fields in JSON schema."""
    from intelligence.ask_intrinsiciq.relationship_aware_composer import _build_composition_system_prompt
    from knowledge.ai import get_llm

    system_prompt = _build_composition_system_prompt(composition_plan, DOMAIN_QUESTION)
    all_claims = (
        composition_plan.get("allowed_claims", []) + composition_plan.get("qualified_claims", [])
    )[:10]
    evidence_lines = []
    for c in all_claims:
        evs = ", ".join(c.get("evidence_refs", [])[:3])
        evidence_lines.append(
            f"[{c.get('claim_id','?')}] {c.get('claim_text','?')}"
            + (f" (evidence: {evs})" if evs else "")
        )

    # V3-specific deterministic context for the LLM
    v3_context = ""
    if fact_pack_v2:
        prog = fact_pack_v2.get("progression_counts", {})
        hc_count = fact_pack_v2.get("hard_commitment_count", 0)
        npm = fact_pack_v2.get("npm")
        ev_obs = fact_pack_v2.get("evidence_observations", [])
        mgmt_stmts = fact_pack_v2.get("management_statements", [])
        cons_obs = fact_pack_v2.get("consistency_observations", [])
        dpfs = fact_pack_v2.get("dpfs", [])

        v3_context = (
            f"\nCONTRACT V3 CONTEXT (deterministic values — use in your response):\n"
            f"Progression: {prog.get('total',0)} items, {prog.get('delivered',0)} delivered, "
            f"{prog.get('in_progress',0)} in_progress, {prog.get('announced',0)} announced\n"
            f"Hard commitments with specific deadlines: {hc_count}\n"
        )
        if npm is not None:
            v3_context += f"Net Profit Margin (NPM): {npm}%\n"
        if ev_obs:
            v3_context += "Key evidence observations:\n" + "".join(f"  - {e}\n" for e in ev_obs)
        if mgmt_stmts:
            v3_context += "Management statements:\n" + "".join(f"  - {s}\n" for s in mgmt_stmts)
        if cons_obs:
            v3_context += "Consistency observations:\n" + "".join(f"  - {o}\n" for o in cons_obs)
        if dpfs:
            v3_context += f"\nDETERMINISTIC PRECISION FACTS (injected automatically):\n{json.dumps(dpfs, indent=2)}\n"

    _desc_hint = behavioral_descriptor or next(
        (_d for _c in all_claims for _d in _BEHAVIORAL_DESCRIPTORS if _d in _c.get("claim_text", "")),
        None,
    )

    user_content = (
        f"Company: Sun Pharma\nQuestion: {DOMAIN_QUESTION}\n\n"
        "Validated claims:\n" + "\n".join(evidence_lines)
        + v3_context
        + (
            f"\nMANDATORY CONSTRAINT: The string '{_desc_hint}' MUST appear verbatim in your simple_answer field.\n"
            if _desc_hint else ""
        )
        + "MANDATORY CONSTRAINT: Do NOT use phrases like 'management quality is weak/strong/mixed', "
        "'management is capable/credible/disciplined/effective', or any numeric/letter grade. "
        "Use factual, evidence-based language about delivery counts, progression states, and commitment evidence.\n"
        "\nContract V3 requires these fields in your JSON response:\n"
        "- simple_answer: factual synthesis including the behavioral descriptor verbatim\n"
        "- why_it_matters: investor significance\n"
        "- investor_interpretation: what this means for valuation/outlook\n"
        "- key_points: 3-5 evidence-anchored bullet points\n"
        "- what_evidence_shows: list of 2+ evidence bullets\n"
        "- what_management_says: summary of management statements and commitments\n"
        "- where_management_was_consistent: where actions matched statements\n"
        "- what_may_mean_economically: economic implications referencing NPM/revenue/PAT figures\n"
        "\nNote: what_is_not_yet_proven, what_to_monitor, management_consistency_map, "
        "and deterministic_precision_facts are injected from canonical evidence automatically.\n"
        "\nGenerate the investor answer as a JSON object."
    )

    _SCHEMA_V3 = {
        "type": "object",
        "required": [
            "simple_answer", "why_it_matters", "investor_interpretation", "key_points",
            "what_evidence_shows", "what_management_says",
            "where_management_was_consistent", "what_may_mean_economically",
        ],
        "properties": {
            "simple_answer": {"type": "string"},
            "why_it_matters": {"type": "string"},
            "investor_interpretation": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "what_evidence_shows": {"type": "array", "items": {"type": "string"}},
            "what_management_says": {"type": "string"},
            "where_management_was_consistent": {"type": "string"},
            "what_may_mean_economically": {"type": "string"},
        },
        "additionalProperties": False,
    }

    telemetry: Dict[str, Any] = {
        "provider": "openai", "model": model,
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
        "latency_ms": None, "success": False, "error": None,
    }
    answer_raw: Dict[str, Any] = {}
    error_msg: Optional[str] = None

    try:
        llm = get_llm(model=model)
        response = llm.generate(
            prompt=user_content,
            response_schema=_SCHEMA_V3,
            max_tokens=MAX_OUTPUT_TOKENS,
            system_prompt=system_prompt,
        )
        telemetry["provider"] = getattr(response, "provider", "openai")
        telemetry["model"] = getattr(response, "model", model)
        telemetry["input_tokens"] = getattr(response, "prompt_tokens", None)
        telemetry["output_tokens"] = getattr(response, "completion_tokens", None)
        telemetry["total_tokens"] = getattr(response, "total_tokens", None)
        telemetry["latency_ms"] = round(getattr(response, "latency_ms", 0.0), 1)
        telemetry["success"] = True
        raw_text = response.text if hasattr(response, "text") else str(response)
        answer_raw = json.loads(raw_text.strip())
    except Exception as exc:
        error_msg = str(exc)
        telemetry["error"] = error_msg
        answer_raw = {"_composition_error": error_msg}

    if not answer_raw.get("_composition_error"):
        from intelligence.ask_intrinsiciq.relationship_aware_composer import _strip_plan_meta
        answer_raw["claims"] = [_strip_plan_meta(c) for c in all_claims]
        answer_raw["relationships"] = []
        answer_raw["evidence_gaps"] = composition_plan.get("evidence_gaps", [])

    return {"answer": answer_raw, "telemetry": telemetry, "error": error_msg}


def run_regeneration_v3(
    company: str = "sun_pharma",
    companies_root: Path = REPO / "companies",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Execute one controlled AI regeneration under Contract V3 (ENG-MISSION49).

    Key differences from run_regeneration (V2):
    - Contract fingerprint = CONTRACT_V3_POLICY_DIGEST (full SHA-256, not model-derived)
    - Execution ID uses full SHA-256 (not truncated 32 chars)
    - Builds Fact Pack V2 (not V1)
    - Uses Assembler V3 (not V2)
    - Runs EIV V2 + semantic capability parity validator
    - Writes candidate as m49_candidate_v1

    Security constraints inherited from run_regeneration:
    MAX_EXECUTED_AI_CALLS=1, RETRY_COUNT=0, no self-approval, no activation.
    """
    from intelligence.regeneration_planner import (
        plan_regeneration, UNIT_PROMPT_VERSIONS, UNIT_SCHEMA_VERSIONS, PROMPT_VERSION_CHANGED,
    )
    from pipelines.pacp_adversarial import run_adversarial_suite
    from intelligence.management_quality.contract_manifest import CONTRACT_V3_POLICY_DIGEST
    import os

    company_root = Path(companies_root) / company
    candidate_dir = company_root / "company_memory" / "ask_intrinsiciq"
    manifest_path = candidate_dir / MANIFEST_FILENAME
    certified_path = company_root / CERTIFIED_ARTIFACT_PATH

    # ── Load or initialize manifest ────────────────────────────────────────────
    raw_manifest = _load_json(manifest_path)
    if "execution_history" not in raw_manifest:
        manifest: Dict[str, Any] = {
            "schema_version": "m45_manifest_v3",
            "mission": "ENG-MISSION49",
            "company": company,
            "unit": UNIT_TARGET,
            "question_id": QUESTION_ID,
            "execution_history": [],
        }
    else:
        manifest = raw_manifest
    _ensure_attempt1_history(manifest)

    # ── Contract V3 fingerprint ────────────────────────────────────────────────
    contract_fp = CONTRACT_V3_POLICY_DIGEST  # full SHA-256

    # ── Evidence fingerprint ───────────────────────────────────────────────────
    evidence_fp = _compute_evidence_fingerprint(company, Path(companies_root))

    # ── Execution ID (full SHA-256 — matches M48 planned ID) ─────────────────
    execution_id = compute_execution_id_v3(company, UNIT_TARGET, evidence_fp, contract_fp)
    eid_short = execution_id.replace("sha256:", "")[:12]

    # ── Candidate path ─────────────────────────────────────────────────────────
    candidate_filename = CANDIDATE_FILENAME_TEMPLATE.format(eid_short=eid_short)
    candidate_path = candidate_dir / candidate_filename
    assert candidate_path.resolve() != certified_path.resolve(), (
        "SECURITY VIOLATION: candidate path equals certified artifact path"
    )

    # ── Idempotency ─────────────────────────────────────────────────────────────
    prior_success = _find_successful_execution_by_evidence(manifest, evidence_fp)
    if prior_success is not None:
        is_exact = prior_success.get("generation_contract_fingerprint") == contract_fp
        if is_exact:
            integrity = _verify_candidate_integrity(prior_success, candidate_dir)
            if integrity["ok"]:
                print(
                    f"[M49] REUSE_EXISTING_GENERATION: "
                    f"existing_id={prior_success.get('execution_id')} provider_calls=0"
                )
                return {
                    "decision": "REUSE_EXISTING_GENERATION",
                    "existing_execution_id": prior_success.get("execution_id"),
                    "new_execution_id": execution_id,
                    "evidence_fp": evidence_fp,
                    "contract_fp": contract_fp,
                    "candidate_path": integrity["candidate_path"],
                    "candidate_digest": integrity["digest"],
                    "pacp_overall": "PASS",
                    "review_state": "AWAITING_HUMAN_REVIEW",
                    "provider_calls": 0,
                }

    attempt_number = len(manifest["execution_history"]) + 1
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    prompt_version = UNIT_PROMPT_VERSIONS.get(UNIT_TARGET, "1")
    schema_version = UNIT_SCHEMA_VERSIONS.get(UNIT_TARGET, "1")

    # ── Plan ───────────────────────────────────────────────────────────────────
    plan_result = plan_regeneration(
        company_slug=company, companies_root=companies_root,
        forced_reasons={UNIT_TARGET: [PROMPT_VERSION_CHANGED]},
        prompt_versions={UNIT_TARGET: prompt_version},
    )
    _verify_plan(plan_result)
    all_units = plan_result.get("units", plan_result.get("unit_plans", []))
    unit_plans = {u["generation_unit"]: u for u in all_units}
    plan_unit_id = unit_plans[UNIT_TARGET].get("plan_unit_id", "unknown")

    # ── Canonical evidence ─────────────────────────────────────────────────────
    mq_summary_path = (
        company_root / "company_memory" / "management_quality" / "management_quality_summary.json"
    )
    mq_summary = _load_json(mq_summary_path)
    if not mq_summary:
        raise RuntimeError(f"M49_GATE_FAIL: management_quality_summary not found at {mq_summary_path}")

    progression_path = (
        company_root / "company_memory" / "management_progression" / "management_progression.json"
    )
    capital_path = (
        company_root / "company_memory" / "capital_allocation_outcomes" / "capital_allocation_outcomes.json"
    )
    progression_data = _load_json(progression_path)
    capital_data = _load_json(capital_path)

    # ── Behavioral descriptor ──────────────────────────────────────────────────
    behavioral_descriptor = derive_behavioral_descriptor(progression_data, capital_data)
    derivation_trace = _descriptor_derivation_trace(progression_data, capital_data)

    # ── Fact Pack V2 ───────────────────────────────────────────────────────────
    fact_pack_v2: Optional[Dict[str, Any]] = None
    fact_pack_v2_valid = False
    try:
        from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
        fact_pack_v2 = build_management_quality_fact_pack_v2(company, company_root / "company_memory")
        fact_pack_v2_valid = (
            bool(fact_pack_v2)
            and fact_pack_v2.get("schema_version") == "management_fact_pack.v2"
            and fact_pack_v2.get("progression_counts", {}).get("total", 0) > 0
        )
    except Exception as _fp_err:
        raise RuntimeError(f"M49_FACT_PACK_V2_BUILD_FAILED: {_fp_err}")

    if not fact_pack_v2_valid:
        raise RuntimeError("M49_FACT_PACK_INCONSISTENT: fact_pack_v2 invalid or empty")

    # ── Five-capability preflight ──────────────────────────────────────────────
    capability_preflight = _five_capability_preflight(fact_pack_v2)
    if not capability_preflight["all_present"]:
        raise RuntimeError(
            f"M49_PRE_LLM_CAPABILITY_MISSING: {capability_preflight['capabilities']}"
        )

    # ── Hard commitment granularity ────────────────────────────────────────────
    hard_commitment_count = fact_pack_v2.get("hard_commitment_count", 0)
    hard_commitment_granularity_present = hard_commitment_count > 0
    if not hard_commitment_granularity_present:
        raise RuntimeError("M49_GATE_FAIL: HARD_COMMITMENT_GRANULARITY_PRESENT = false")

    # ── Composition plan + audit ───────────────────────────────────────────────
    composition_plan = build_management_quality_composition_plan(mq_summary, behavioral_descriptor)
    if not composition_plan.get("allowed_claims") and not composition_plan.get("qualified_claims"):
        raise RuntimeError("M49_GATE_FAIL: composition plan has no claims")
    plan_digest = _compute_plan_digest(composition_plan)
    plan_audit = audit_composition_plan_for_rating_leakage(composition_plan)
    if not plan_audit["clean"]:
        raise RuntimeError(
            f"M49_COMPOSITION_PLAN_RATING_LEAKAGE: {plan_audit['violations']}"
        )

    # ── Previous-answer isolation check ───────────────────────────────────────
    certified_answer_data = _load_json(certified_path)
    isolation_check = verify_no_previous_answer_in_generation_input(
        composition_plan, certified_answer_data
    )
    if not isolation_check["isolated"]:
        raise RuntimeError(
            f"M49_PREVIOUS_ANSWER_CONTENT_DETECTED: {isolation_check['violations']}"
        )

    # ── Deterministic skeleton pre-check ──────────────────────────────────────
    from intelligence.management_quality.semantic_sections import build_deterministic_semantic_sections
    deterministic_sections = build_deterministic_semantic_sections(fact_pack_v2)
    skeleton_valid = all(
        deterministic_sections.get(k)
        for k in [
            "what_evidence_shows", "what_management_says", "where_management_was_consistent",
            "management_consistency_map", "what_is_not_yet_proven", "what_to_monitor",
        ]
    )
    if not skeleton_valid:
        missing = [
            k for k in ["what_evidence_shows", "what_management_says", "where_management_was_consistent",
                        "management_consistency_map", "what_is_not_yet_proven", "what_to_monitor"]
            if not deterministic_sections.get(k)
        ]
        raise RuntimeError(f"M49_GATE_FAIL: PRE_LLM_CONTRACT_V3_STRUCTURE = FAIL (missing: {missing})")

    # ── Certified artifact snapshot (before) ──────────────────────────────────
    certified_digest_before = _file_digest(certified_path)

    # ── Identity validation ────────────────────────────────────────────────────
    identity_match = execution_id == _M48_PLANNED_EXECUTION_ID
    evidence_match = evidence_fp == _M48_EVIDENCE_FP
    contract_match = contract_fp == _M48_CONTRACT_V3_FP

    # ── Pre-call checkpoint ────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"MISSION                                    = M49")
    print(f"COMPANY                                    = {company}")
    print(f"GENERATION_UNIT                            = {UNIT_TARGET}")
    print()
    print(f"EVIDENCE_FP                                = {evidence_fp}")
    print(f"CONTRACT_V3_FP                             = {contract_fp}")
    print(f"EXECUTION_ID                               = {execution_id}")
    print(f"EXPECTED_EXECUTION_ID (M48 planned)        = {_M48_PLANNED_EXECUTION_ID}")
    print(f"IDENTITY_MATCH                             = {identity_match}")
    print()
    print(f"FACT_PACK_V2_VALID                         = {fact_pack_v2_valid}")
    print(f"HARD_COMMITMENT_GRANULARITY_PRESENT        = {hard_commitment_granularity_present}")
    print(f"DPF_COUNT                                  = {len(fact_pack_v2.get('dpfs', []))}")
    print()
    for cap, present in capability_preflight["capabilities"].items():
        print(f"CAPABILITY.{cap:<42} = {present}")
    print()
    print(f"UNCERTAINTY_SPECIFIC                       = {bool(fact_pack_v2.get('uncertainty_items_enriched'))}")
    print(f"MONITORING_SPECIFIC                        = {bool(fact_pack_v2.get('monitoring_items_enriched'))}")
    print()
    print(f"PRE_LLM_CONTRACT_V3_STRUCTURE              = {'PASS' if skeleton_valid else 'FAIL'}")
    print(f"PREVIOUS_ANSWER_USED_AS_INPUT              = {not isolation_check['isolated']}")
    print(f"DETERMINISTIC_FIELDS_PROTECTED             = true")
    print()
    print(f"PLANNED_CALLS                              = 1")
    print(f"MAX_ALLOWED_CALLS                          = {MAX_EXECUTED_AI_CALLS}")
    print(f"RETRIES                                    = {RETRY_COUNT}")
    print()
    print(f"PACP_BYPASS                                = false")
    print(f"EIV_V2_BYPASS                              = false")
    print(f"AUTO_APPROVAL                              = false")
    print(f"AUTO_ACTIVATION                            = false")
    print(f"UI_AI_CALL_PATH                            = false")
    print(f"{'='*70}\n")

    if not identity_match:
        return {
            "decision": "M49_EXECUTION_IDENTITY_MISMATCH",
            "computed_id": execution_id,
            "expected_id": _M48_PLANNED_EXECUTION_ID,
            "evidence_fp": evidence_fp,
            "contract_fp": contract_fp,
        }

    # ── AI call ────────────────────────────────────────────────────────────────
    ai_calls_executed = 0
    ai_calls_failed = 0
    answer: Dict[str, Any] = {}
    telemetry: Dict[str, Any] = {
        "provider": "openai", "model": model,
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
        "latency_ms": None, "success": False, "error": None,
    }

    if dry_run:
        answer = {
            "simple_answer": f"[DRY_RUN] {behavioral_descriptor} — deterministic only, no AI call.",
            "why_it_matters": "dry_run=True",
            "investor_interpretation": "dry_run=True",
            "key_points": ["dry_run=True"],
            "what_evidence_shows": ["dry_run"],
            "what_management_says": "dry_run",
            "where_management_was_consistent": "dry_run",
            "what_may_mean_economically": "dry_run",
            "_dry_run": True,
        }
        telemetry["success"] = True
    else:
        result_llm = _call_llm_v3(composition_plan, model, behavioral_descriptor, fact_pack_v2)
        answer = result_llm["answer"]
        telemetry = result_llm["telemetry"]
        if result_llm["error"] or answer.get("_composition_error"):
            ai_calls_failed = 1
        else:
            ai_calls_executed = 1

    # ── Assembler V3 — inject deterministic sections ──────────────────────────
    if not answer.get("_composition_error") and not answer.get("_dry_run"):
        try:
            from intelligence.management_quality.assembler_v3 import assemble_management_answer_v3
            answer = assemble_management_answer_v3(fact_pack_v2, llm_prose=answer)
        except Exception as _asm_err:
            raise RuntimeError(f"M49_ASSEMBLER_V3_FAILED: {_asm_err}")

    # ── Contract V3 structural validation ─────────────────────────────────────
    v3_validation = _validate_contract_v3_structure(answer)

    # ── PACP ──────────────────────────────────────────────────────────────────
    pacp_result = run_adversarial_suite(answer=answer, company=company, question_id=QUESTION_ID)
    pacp_overall = pacp_result.get("overall", "INCOMPLETE")

    # ── EIV V2 gate ───────────────────────────────────────────────────────────
    eiv_v2_result: Dict[str, Any] = {}
    eiv_v2_overall = "NOT_RUN"
    try:
        from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
        eiv_v2_result = validate_management_answer_eiv_v2(answer, fact_pack=fact_pack_v2)
        eiv_v2_overall = eiv_v2_result.get("overall", "FAIL")
    except Exception as _eiv_err:
        print(f"[M49] WARNING: EIV V2 failed: {_eiv_err}")
        eiv_v2_result = {"overall": "FAIL", "_error": str(_eiv_err)}
        eiv_v2_overall = "FAIL"

    # ── Semantic parity validator ──────────────────────────────────────────────
    parity_result: Dict[str, Any] = {}
    parity_overall = "NOT_RUN"
    try:
        from intelligence.management_quality.capability_parity_validator import (
            validate_management_semantic_capability_parity,
        )
        parity_result = validate_management_semantic_capability_parity(answer)
        parity_overall = parity_result.get("overall", "FAIL")
    except Exception as _par_err:
        print(f"[M49] WARNING: parity validator failed: {_par_err}")
        parity_result = {"overall": "FAIL", "_error": str(_par_err)}
        parity_overall = "FAIL"

    # ── Write candidate (per execution_id, only on PACP PASS/WARN) ───────────
    candidate_digest = "NOT_WRITTEN"
    eligibility_result: Dict[str, Any] = {}
    eligibility_state = "NOT_EVALUATED"

    if pacp_overall in ("PASS", "WARN") and not dry_run:
        candidate: Dict[str, Any] = {
            "schema_version": "m49_candidate_v1",
            "mission": "ENG-MISSION49",
            "attempt": attempt_number,
            "company": company,
            "unit": UNIT_TARGET,
            "question_id": QUESTION_ID,
            "execution_id": execution_id,
            "executed_at": _utc_now(),
            "contract_version": "v3",
            "generation_contract_schema": GENERATION_CONTRACT_SCHEMA_V3,
            "prompt_version": prompt_version,
            "model": telemetry.get("model", model),
            "pacp_overall": pacp_overall,
            "eiv_v2_overall": eiv_v2_overall,
            "parity_overall": parity_overall,
            "behavioral_descriptor": behavioral_descriptor,
            "composition_policy_version": COMPOSITION_POLICY["version"],
            "answer": answer,
        }
        _write_json(candidate_path, candidate)
        candidate_digest = _file_digest(candidate_path)

        # ── Release eligibility (M49: must pass PACP + EIV V2 + parity) ─────
        try:
            from intelligence.management_quality.candidate_eligibility import (
                evaluate_candidate_release_eligibility,
            )
            combined_eiv = {
                "overall": eiv_v2_overall,
                "fail_count": eiv_v2_result.get("fail_count", len(eiv_v2_result.get("fails", []))),
                "fails": eiv_v2_result.get("fails", []),
            }
            eligibility_result = evaluate_candidate_release_eligibility(
                candidate={**candidate, "candidate_digest": candidate_digest},
                pacp_result=pacp_result,
                eiv_result=combined_eiv,
            )
            eligibility_state = eligibility_result.get("eligibility_state", "NOT_EVALUATED")
            # Additional M49 gate: parity must pass (WARN allowed for MEDIUM-only)
            if parity_overall == "FAIL" and eligibility_state == "HUMAN_REVIEW_ELIGIBLE":
                eligibility_state = "BLOCKED_SEMANTIC_PARITY"
                eligibility_result["eligible"] = False
                eligibility_result["eligibility_state"] = eligibility_state
                eligibility_result.setdefault("blocks", []).append("SEMANTIC_PARITY_FAIL")
        except Exception as _elig_err:
            print(f"[M49] WARNING: eligibility evaluation failed: {_elig_err}")
            eligibility_result = {
                "eligible": False, "eligibility_state": "BLOCKED_MULTIPLE",
                "_error": str(_elig_err),
            }
            eligibility_state = "BLOCKED_MULTIPLE"

        candidate["eligibility_state"] = eligibility_state
        _write_json(candidate_path, candidate)
        candidate_digest = _file_digest(candidate_path)

    # ── Verify certified artifact untouched ───────────────────────────────────
    certified_digest_after = _file_digest(certified_path)
    if certified_digest_before != certified_digest_after:
        raise RuntimeError(
            f"SECURITY VIOLATION: certified artifact mutated. "
            f"before={certified_digest_before} after={certified_digest_after}"
        )

    # ── Semantic diff ──────────────────────────────────────────────────────────
    semantic_diff = _semantic_diff(certified_answer_data, answer)

    # ── Outcome ───────────────────────────────────────────────────────────────
    if answer.get("_composition_error"):
        outcome = "PROVIDER_CALL_FAILED"
    elif pacp_overall not in ("PASS", "WARN"):
        outcome = "PACP_FAIL_CANDIDATE_REJECTED"
    elif dry_run:
        outcome = "DRY_RUN_COMPLETE"
    elif eligibility_state == "HUMAN_REVIEW_ELIGIBLE":
        outcome = "PACP_PASS_EIV_V2_PASS_PARITY_PASS_AWAITING_HUMAN_REVIEW"
    elif eligibility_state == "BLOCKED_EIV":
        outcome = "PACP_PASS_EIV_V2_FAIL_BLOCKED"
    elif eligibility_state == "BLOCKED_SEMANTIC_PARITY":
        outcome = "PACP_PASS_EIV_V2_PASS_PARITY_FAIL_BLOCKED"
    else:
        outcome = f"PACP_PASS_BLOCKED_{eligibility_state}"

    def _rel(p: Path) -> str:
        return str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p)

    attempt_entry: Dict[str, Any] = {
        "attempt": attempt_number,
        "manifest_record_origin": "LIVE_EXECUTION",
        "execution_id": execution_id,
        "executed_at": _utc_now(),
        "contract_version": "v3",
        "generation_contract_schema": GENERATION_CONTRACT_SCHEMA_V3,
        "prompt_version": prompt_version,
        "schema_version_unit": schema_version,
        "model": telemetry.get("model", model),
        "provider": telemetry.get("provider", "openai"),
        "dry_run": dry_run,
        "plan_unit_id": plan_unit_id,
        "ai_calls_attempted": 0 if dry_run else 1,
        "ai_calls_executed": ai_calls_executed,
        "ai_calls_failed": ai_calls_failed,
        "telemetry": telemetry,
        "evidence_dependency_fingerprint": evidence_fp,
        "generation_contract_fingerprint": contract_fp,
        "m48_planned_execution_id": _M48_PLANNED_EXECUTION_ID,
        "identity_match": identity_match,
        "composition_policy_version": COMPOSITION_POLICY["version"],
        "composition_policy_hash": COMPOSITION_POLICY_HASH,
        "behavioral_descriptor": behavioral_descriptor,
        "behavioral_descriptor_source": "canonical_management_progression_evidence",
        "behavioral_descriptor_derivation": derivation_trace,
        "previous_answer_isolation": isolation_check,
        "composition_plan_digest": plan_digest,
        "composition_plan_audit": plan_audit,
        "fact_pack_v2_valid": fact_pack_v2_valid,
        "hard_commitment_count": hard_commitment_count,
        "hard_commitment_granularity_present": hard_commitment_granularity_present,
        "capability_preflight": capability_preflight,
        "contract_v3_validation": v3_validation,
        "parity_result": {
            "overall": parity_overall,
            "fail_count": parity_result.get("fail_count", 0),
            "high_severity_fails": parity_result.get("high_severity_fails", []),
            "medium_severity_fails": parity_result.get("medium_severity_fails", []),
        },
        "pacp_result": {
            "overall": pacp_overall,
            "named_checks": pacp_result.get("named_checks", 0),
            "fails": pacp_result.get("fails", []),
            "warns": pacp_result.get("warns", []),
        },
        "eiv_v2_result": {
            "overall": eiv_v2_overall,
            "fail_count": eiv_v2_result.get("fail_count", 0),
            "fails": eiv_v2_result.get("fails", []),
            "high_severity_fails": eiv_v2_result.get("high_severity_fails", []),
        },
        "eligibility_result": {
            "eligible": eligibility_result.get("eligible", False),
            "eligibility_state": eligibility_state,
            "blocks": eligibility_result.get("blocks", []),
        },
        "semantic_diff": semantic_diff,
        "certified_artifact_path": _rel(certified_path),
        "certified_artifact_digest_before": certified_digest_before,
        "certified_artifact_digest_after": certified_digest_after,
        "certified_artifact_mutated": certified_digest_before != certified_digest_after,
        "candidate_path": (
            _rel(candidate_path)
            if pacp_overall in ("PASS", "WARN") and not dry_run
            else None
        ),
        "candidate_filename": candidate_filename,
        "candidate_digest": candidate_digest,
        "outcome": outcome,
        "approval": False,
        "activation": False,
        "m49_security_constraints": {
            "max_executed_ai_calls": MAX_EXECUTED_AI_CALLS,
            "retry_count": RETRY_COUNT,
            "self_approval": False,
            "automatic_activation": False,
        },
    }

    # ── Append to history (never overwrite) ───────────────────────────────────
    manifest["execution_history"].append(attempt_entry)
    manifest["last_updated"] = _utc_now()
    manifest["total_attempts"] = len(manifest["execution_history"])
    _write_json(manifest_path, manifest)
    return manifest


# ── M51: Contract V4 Narrative-Only Executor ──────────────────────────────────

_M51_PLANNED_EXECUTION_ID = (
    "sha256:444fc5f4166d1e5b39e30a58a8469ff2553106ca5f21d777cd1598ea32ae8909"
)
_M51_PLANNED_EVIDENCE_FP = (
    "sha256:6793736f4298b82142d39d0439f299d7c11f0310ada29ff0a9cc99fac06c2aad"
)
_M51_PLANNED_CONTRACT_V4_FP = (
    "sha256:46dbdbe96e05fd0c233851ad3ad474fc2dd386f5c0d4955e00dd6fb490291ee7"
)

_SCHEMA_V4_NARRATIVE = {
    "type": "object",
    "required": ["simple_answer", "what_may_mean_economically"],
    "properties": {
        "simple_answer": {"type": "string"},
        "what_may_mean_economically": {"type": "string"},
    },
    "additionalProperties": False,
}


def _call_llm_v4_narrative(
    fact_pack_v2: Dict[str, Any],
    model: str,
) -> Dict[str, Any]:
    """V4 LLM call — requests ONLY simple_answer and what_may_mean_economically.

    All structured investor sections are deterministic. The LLM only narrates
    what Prometheus has already constructed.
    """
    from knowledge.ai import get_llm

    descriptor = fact_pack_v2.get("behavioral_descriptor", "")
    prog = fact_pack_v2.get("progression_counts", {})
    npm = fact_pack_v2.get("npm")
    fin = fact_pack_v2.get("financial_context", {})
    rev = fin.get("revenue", {})
    dpfs = fact_pack_v2.get("dpfs", [])
    hc_count = fact_pack_v2.get("hard_commitment_count", 0)
    hc_list = fact_pack_v2.get("hard_commitments", [])

    fin_line = ""
    if rev.get("value") is not None:
        fin_line = f"Revenue FY{rev.get('fy','?')}: ₹{rev['value']:,.0f} cr (confirmed, not projected)."
    if npm is not None:
        fin_line += f" Net Profit Margin: {npm}%."

    hc_detail = "; ".join(
        f"{h.get('id')} ({h.get('timeframe','?')}): {h.get('normalized_commitment','?')[:60]}"
        for h in hc_list[:3]
    )

    system_prompt = (
        "You are a financial analyst narrating investor intelligence that has already been "
        "constructed deterministically from canonical evidence. Your job is to make the "
        "pre-built intelligence clearer and more readable. You must not add new facts, "
        "invent outcomes, or override any pre-built section. "
        "Avoid all evaluative language about management quality (do not say weak/strong/"
        "poor/excellent/credible/capable/disciplined management). "
        "Do not say 'management quality'. Use factual, evidence-based language."
    )

    user_content = (
        f"Company: Sun Pharma\n"
        f"Question: {DOMAIN_QUESTION}\n\n"
        f"DETERMINISTIC CONTEXT (use these exact values, do not alter):\n"
        f"Behavioral descriptor: {descriptor}\n"
        f"Progression: {prog.get('total',0)} total commitments tracked; "
        f"{prog.get('delivered',0)} delivered, {prog.get('in_progress',0)} in-progress, "
        f"{prog.get('announced',0)} announced.\n"
        f"Hard commitments (specific date + verifiable): {hc_count} — [{hc_detail}]\n"
        f"{fin_line}\n"
        + (f"\nDETERMINISTIC PRECISION FACTS:\n" + json.dumps(dpfs, indent=2) + "\n" if dpfs else "")
        + f"\nINSTRUCTIONS:\n"
        f"1. simple_answer: Write a factual 2-3 sentence synthesis. The exact string "
        f"'{descriptor}' MUST appear verbatim. Include key progression counts and commitment "
        f"count. Do NOT use rating language or evaluative phrases.\n"
        f"2. what_may_mean_economically: Explain what the confirmed financial facts above "
        f"mean for an investor. Reference confirmed NPM and revenue (not projected). "
        f"Do not create causal attribution or upgrade association to causation.\n\n"
        f"NOTE: All structured investor sections (what_evidence_shows, what_management_says, "
        f"management_consistency_map, what_is_not_yet_proven, what_to_monitor) are already "
        f"built deterministically. You are ONLY providing simple_answer and "
        f"what_may_mean_economically as narrative improvements.\n\n"
        f"Return JSON with exactly these two fields: simple_answer, what_may_mean_economically."
    )

    telemetry: Dict[str, Any] = {
        "provider": "openai", "model": model,
        "input_tokens": None, "output_tokens": None, "total_tokens": None,
        "latency_ms": None, "success": False, "error": None,
    }
    answer_raw: Dict[str, Any] = {}
    error_msg: Optional[str] = None

    try:
        llm = get_llm(model=model)
        response = llm.generate(
            prompt=user_content,
            response_schema=_SCHEMA_V4_NARRATIVE,
            max_tokens=MAX_OUTPUT_TOKENS,
            system_prompt=system_prompt,
        )
        telemetry["provider"] = getattr(response, "provider", "openai")
        telemetry["model"] = getattr(response, "model", model)
        telemetry["input_tokens"] = getattr(response, "prompt_tokens", None)
        telemetry["output_tokens"] = getattr(response, "completion_tokens", None)
        telemetry["total_tokens"] = getattr(response, "total_tokens", None)
        telemetry["latency_ms"] = round(getattr(response, "latency_ms", 0.0), 1)
        telemetry["success"] = True
        raw_text = response.text if hasattr(response, "text") else str(response)
        answer_raw = json.loads(raw_text.strip())
    except Exception as exc:
        error_msg = str(exc)
        telemetry["error"] = error_msg
        answer_raw = {"_composition_error": error_msg}

    return {"answer": answer_raw, "telemetry": telemetry, "error": error_msg}


def run_regeneration_v4(
    company: str = "sun_pharma",
    companies_root: str = "companies",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """M51: Contract V4 Narrative-Only Regeneration Canary.

    One authorized provider call. All structured sections deterministic.
    LLM produces only simple_answer and what_may_mean_economically.
    """
    from pathlib import Path
    from intelligence.management_quality.fact_pack_v2 import build_management_quality_fact_pack_v2
    from intelligence.management_quality.investor_sections import build_investor_sections
    from intelligence.management_quality.assembler_v4 import assemble_management_answer_v4, LLM_SECTION_OVERRIDE_BLOCKED
    from intelligence.management_quality.contract_manifest import compute_contract_v4_fingerprint
    from intelligence.management_quality.rating_quarantine import (
        contains_rating_language, scan_answer_for_rating_violations,
    )
    from intelligence.management_quality.candidate_eligibility import evaluate_candidate_release_eligibility
    from intelligence.external_investor_value_validator_v2 import validate_management_answer_eiv_v2
    from intelligence.management_quality.capability_parity_validator import (
        validate_management_semantic_capability_parity,
    )

    company_root = Path(companies_root) / company
    candidate_dir = company_root / "company_memory" / "ask_intrinsiciq"
    manifest_path = candidate_dir / MANIFEST_FILENAME
    certified_path = company_root / "company_memory" / "ask_intrinsiciq" / "shadow_level3_hybrid_answers.json"

    # ── Identity verification ──────────────────────────────────────────────────
    evidence_fp = _compute_evidence_fingerprint(company, Path(companies_root))
    contract_fp = compute_contract_v4_fingerprint()
    execution_id = compute_execution_id_v3(company, UNIT_TARGET, evidence_fp, contract_fp)
    eid_short = execution_id.replace("sha256:", "")[:12]

    if evidence_fp != _M51_PLANNED_EVIDENCE_FP:
        return {"decision": "M51_EVIDENCE_DRIFT_BEFORE_EXECUTION",
                "current_evidence_fp": evidence_fp,
                "planned_evidence_fp": _M51_PLANNED_EVIDENCE_FP}

    if contract_fp != _M51_PLANNED_CONTRACT_V4_FP:
        return {"decision": "M51_CONTRACT_IDENTITY_MISMATCH",
                "current_contract_fp": contract_fp,
                "planned_contract_fp": _M51_PLANNED_CONTRACT_V4_FP}

    if execution_id != _M51_PLANNED_EXECUTION_ID:
        return {"decision": "M51_EXECUTION_IDENTITY_MISMATCH",
                "computed_id": execution_id,
                "expected_id": _M51_PLANNED_EXECUTION_ID}

    # ── Load manifest ──────────────────────────────────────────────────────────
    raw_manifest = _load_json(manifest_path)
    manifest = raw_manifest if "execution_history" in raw_manifest else {
        "schema_version": "m51_manifest_v1",
        "mission": "ENG-MISSION51",
        "company": company,
        "unit": UNIT_TARGET,
        "execution_history": [],
    }

    # ── Idempotency — check for prior successful M51 execution ────────────────
    for entry in manifest.get("execution_history", []):
        if (entry.get("execution_id") == execution_id
                and entry.get("outcome") not in (None, "PROVIDER_CALL_FAILED", "PACP_FAILED_SAFELY")):
            # Verify candidate file still exists and matches
            cpath = candidate_dir / f"regeneration_candidate_how_good_is_management_{eid_short}.json"
            if cpath.exists():
                existing_digest = _file_digest(cpath)
                if existing_digest == entry.get("candidate_digest"):
                    return {
                        "decision": "REUSE_EXISTING_GENERATION",
                        "new_ai_calls": 0,
                        "execution_id": execution_id,
                        "candidate_path": str(cpath),
                        "candidate_digest": existing_digest,
                    }

    # ── Build deterministic fact pack and investor sections ────────────────────
    fp = build_management_quality_fact_pack_v2(company, company_root / "company_memory")
    sections = build_investor_sections(fp)

    # ── Hard commitment gate ────────────────────────────────────────────────────
    hc_count = fp.get("hard_commitment_count", 0)
    hc_ids = [h.get("id") for h in fp.get("hard_commitments", [])]
    if hc_count != 3 or set(hc_ids) != {"MC-0029", "MC-0031", "MC-0039"}:
        return {"decision": "M51_HARD_COMMITMENT_TRUTH_MISMATCH",
                "current_count": hc_count, "current_ids": hc_ids,
                "expected_count": 3, "expected_ids": ["MC-0029", "MC-0031", "MC-0039"]}

    # ── Build pre-LLM artifact (fully deterministic) ───────────────────────────
    pre_llm_artifact = assemble_management_answer_v4(fp, llm_prose=None)
    pre_llm_digest = "sha256:" + hashlib.sha256(
        json.dumps(pre_llm_artifact, sort_keys=True).encode()
    ).hexdigest()

    # ── Rating quarantine on pre-LLM artifact ─────────────────────────────────
    pre_llm_violations = scan_answer_for_rating_violations(pre_llm_artifact)
    if pre_llm_violations:
        return {"decision": "M51_RATING_LANGUAGE_IN_PRE_LLM_ARTIFACT",
                "violations": pre_llm_violations}

    # ── Certified artifact snapshot (before) ──────────────────────────────────
    certified_digest_before = _file_digest(certified_path)

    # ── Model configuration ────────────────────────────────────────────────────
    import os
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    attempt_number = len(manifest["execution_history"]) + 1

    # ── AI call ────────────────────────────────────────────────────────────────
    ai_calls_executed = 0
    ai_calls_failed = 0

    if dry_run:
        llm_raw = {
            "simple_answer": f"[DRY_RUN] {fp.get('behavioral_descriptor')} — narrative only.",
            "what_may_mean_economically": "[DRY_RUN] deterministic only.",
        }
        telemetry: Dict[str, Any] = {
            "provider": "dry_run", "model": model,
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            "latency_ms": 0, "success": True, "error": None,
        }
        llm_error = None
    else:
        llm_result = _call_llm_v4_narrative(fp, model)
        llm_raw = llm_result["answer"]
        telemetry = llm_result["telemetry"]
        llm_error = llm_result["error"]
        if llm_error or llm_raw.get("_composition_error"):
            ai_calls_failed = 1
        else:
            ai_calls_executed = 1

    # ── Validate LLM output scope ──────────────────────────────────────────────
    protected_field_override_attempt = False
    protected_field_override_accepted = False
    if not llm_raw.get("_composition_error"):
        ALLOWED_LLM_FIELDS = {"simple_answer", "what_may_mean_economically"}
        attempted_overrides = [k for k in llm_raw if k not in ALLOWED_LLM_FIELDS and not k.startswith("_")]
        if attempted_overrides:
            protected_field_override_attempt = True
            # Strip — do not accept
            llm_raw = {k: v for k, v in llm_raw.items() if k in ALLOWED_LLM_FIELDS or k.startswith("_")}

    # ── Assemble V4 (deterministic > LLM) ─────────────────────────────────────
    final_artifact = assemble_management_answer_v4(fp, llm_prose=llm_raw)

    # ── Post-assembly: verify deterministic sections unchanged ─────────────────
    deterministic_sections_unchanged = True
    changed_sections = []
    for key in ["what_evidence_shows", "what_management_says", "where_management_was_consistent",
                "management_consistency_map", "what_is_not_yet_proven", "what_to_monitor",
                "behavioral_descriptor", "deterministic_precision_facts"]:
        pre_val = pre_llm_artifact.get(key)
        post_val = final_artifact.get(key)
        if json.dumps(pre_val, sort_keys=True) != json.dumps(post_val, sort_keys=True):
            deterministic_sections_unchanged = False
            changed_sections.append(key)

    # ── PACP ──────────────────────────────────────────────────────────────────
    from pipelines.pacp_adversarial import run_adversarial_suite
    pacp_result = run_adversarial_suite(answer=final_artifact, company=company, question_id=QUESTION_ID)
    pacp_overall = pacp_result.get("overall", "INCOMPLETE")

    # ── EIV V2 ────────────────────────────────────────────────────────────────
    try:
        eiv_v2_result = validate_management_answer_eiv_v2(final_artifact, fact_pack=fp)
        eiv_v2_overall = eiv_v2_result.get("overall", "FAIL")
    except Exception as _eiv_err:
        eiv_v2_result = {"overall": "FAIL", "_error": str(_eiv_err)}
        eiv_v2_overall = "FAIL"

    # ── Semantic parity ────────────────────────────────────────────────────────
    try:
        parity_result = validate_management_semantic_capability_parity(final_artifact)
        parity_overall = parity_result.get("overall", "FAIL")
    except Exception as _par_err:
        parity_result = {"overall": "FAIL", "_error": str(_par_err)}
        parity_overall = "FAIL"

    # ── Write candidate ────────────────────────────────────────────────────────
    candidate_path = candidate_dir / f"regeneration_candidate_how_good_is_management_{eid_short}.json"
    assert candidate_path.resolve() != certified_path.resolve(), \
        "SECURITY VIOLATION: candidate path equals certified artifact path"

    candidate_digest = "NOT_WRITTEN"
    eligibility_state = "NOT_EVALUATED"
    eligibility_result: Dict[str, Any] = {}

    if pacp_overall in ("PASS", "WARN") and not dry_run:
        candidate: Dict[str, Any] = {
            "schema_version": "m51_candidate_v1",
            "mission": "ENG-MISSION51",
            "attempt": attempt_number,
            "company": company,
            "unit": UNIT_TARGET,
            "question_id": QUESTION_ID,
            "execution_id": execution_id,
            "executed_at": _utc_now(),
            "contract_version": "v4",
            "model": telemetry.get("model", model),
            "pacp_overall": pacp_overall,
            "eiv_v2_overall": eiv_v2_overall,
            "parity_overall": parity_overall,
            "behavioral_descriptor": fp.get("behavioral_descriptor", ""),
            "deterministic_sections_unchanged": deterministic_sections_unchanged,
            "pre_llm_artifact_digest": pre_llm_digest,
            "llm_raw": llm_raw,
            "answer": final_artifact,
        }
        _write_json(candidate_path, candidate)
        candidate_digest = _file_digest(candidate_path)

        # ── Eligibility ────────────────────────────────────────────────────────
        try:
            combined_eiv = {
                "overall": eiv_v2_overall,
                "fail_count": eiv_v2_result.get("fail_count", len(eiv_v2_result.get("fails", []))),
                "fails": eiv_v2_result.get("fails", []),
            }
            eligibility_result = evaluate_candidate_release_eligibility(
                candidate={**candidate, "candidate_digest": candidate_digest},
                pacp_result=pacp_result,
                eiv_result=combined_eiv,
            )
            eligibility_state = eligibility_result.get("eligibility_state", "NOT_EVALUATED")
            if parity_overall == "FAIL" and eligibility_state == "HUMAN_REVIEW_ELIGIBLE":
                eligibility_state = "BLOCKED_SEMANTIC_PARITY"
                eligibility_result["eligible"] = False
                eligibility_result["eligibility_state"] = eligibility_state
            if not deterministic_sections_unchanged and eligibility_state == "HUMAN_REVIEW_ELIGIBLE":
                eligibility_state = "BLOCKED_DETERMINISTIC_INTEGRITY"
                eligibility_result["eligible"] = False
                eligibility_result["eligibility_state"] = eligibility_state
        except Exception as _elig_err:
            eligibility_result = {"eligible": False, "eligibility_state": "BLOCKED_MULTIPLE",
                                  "_error": str(_elig_err)}
            eligibility_state = "BLOCKED_MULTIPLE"

        candidate["eligibility_state"] = eligibility_state
        _write_json(candidate_path, candidate)
        candidate_digest = _file_digest(candidate_path)

    # ── Verify certified artifact untouched ───────────────────────────────────
    certified_digest_after = _file_digest(certified_path)
    if certified_digest_before != certified_digest_after:
        raise RuntimeError(
            f"SECURITY VIOLATION: certified artifact mutated. "
            f"before={certified_digest_before} after={certified_digest_after}"
        )

    # ── Freshness ──────────────────────────────────────────────────────────────
    post_evidence_fp = _compute_evidence_fingerprint(company, Path(companies_root))
    freshness = "CURRENT" if post_evidence_fp == evidence_fp else "STALE_DRIFT_DETECTED"

    # ── Outcome ───────────────────────────────────────────────────────────────
    if llm_raw.get("_composition_error"):
        outcome = "PROVIDER_CALL_FAILED"
    elif not deterministic_sections_unchanged:
        outcome = "DETERMINISTIC_INTEGRITY_VIOLATED"
    elif pacp_overall not in ("PASS", "WARN"):
        outcome = "PACP_FAILED_SAFELY"
    elif eiv_v2_overall != "PASS":
        outcome = "BLOCKED_EIV"
    elif parity_overall == "FAIL":
        outcome = "BLOCKED_SEMANTIC_PARITY"
    elif eligibility_state == "HUMAN_REVIEW_ELIGIBLE":
        outcome = "PACP_PASS_EIV_PASS_PARITY_PASS_AWAITING_HUMAN_REVIEW"
    else:
        outcome = f"BLOCKED_{eligibility_state}"

    # ── Append history ─────────────────────────────────────────────────────────
    attempt_entry: Dict[str, Any] = {
        "mission": "ENG-MISSION51",
        "attempt": attempt_number,
        "execution_id": execution_id,
        "evidence_fp": evidence_fp,
        "contract_fp": contract_fp,
        "model": telemetry.get("model", model),
        "executed_at": _utc_now(),
        "ai_calls_executed": ai_calls_executed,
        "ai_calls_failed": ai_calls_failed,
        "outcome": outcome,
        "pacp_overall": pacp_overall,
        "eiv_v2_overall": eiv_v2_overall,
        "parity_overall": parity_overall,
        "eligibility_state": eligibility_state,
        "candidate_digest": candidate_digest,
        "freshness": freshness,
        "deterministic_sections_unchanged": deterministic_sections_unchanged,
        "telemetry": telemetry,
    }
    manifest["execution_history"].append(attempt_entry)
    manifest["last_updated"] = _utc_now()
    manifest["total_attempts"] = len(manifest["execution_history"])
    _write_json(manifest_path, manifest)

    return {
        "decision": outcome,
        "execution_id": execution_id,
        "evidence_fp": evidence_fp,
        "contract_fp": contract_fp,
        "pre_llm_digest": pre_llm_digest,
        "candidate_digest": candidate_digest,
        "candidate_path": str(candidate_path) if candidate_digest != "NOT_WRITTEN" else None,
        "pacp_overall": pacp_overall,
        "eiv_v2_overall": eiv_v2_overall,
        "parity_overall": parity_overall,
        "eligibility_state": eligibility_state,
        "eligibility_result": eligibility_result,
        "freshness": freshness,
        "deterministic_sections_unchanged": deterministic_sections_unchanged,
        "changed_sections": changed_sections,
        "ai_calls_executed": ai_calls_executed,
        "ai_calls_failed": ai_calls_failed,
        "telemetry": telemetry,
        "llm_raw": llm_raw,
        "protected_field_override_attempt": protected_field_override_attempt,
        "certified_digest_before": certified_digest_before,
        "certified_digest_after": certified_digest_after,
        "certified_artifact_unchanged": certified_digest_before == certified_digest_after,
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="M45/M49 Controlled AI Regeneration Executor")
    p.add_argument(
        "--execute-ai-regeneration",
        action="store_true",
        help="Required flag to authorize AI execution.",
    )
    p.add_argument("--company", default="sun_pharma")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--contract-version", default="v2", choices=["v2", "v3"],
                   help="Contract version: v2 (M47) or v3 (M49).")
    return p.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = _parse_args(argv)
    if not args.execute_ai_regeneration:
        print("[M45] --execute-ai-regeneration not set. No AI calls made. Exiting cleanly.")
        return 0

    mission = "M49" if args.contract_version == "v3" else "M45"
    print(f"[{mission}] Starting controlled regeneration: company={args.company} dry_run={args.dry_run} contract={args.contract_version}")

    if args.contract_version == "v3":
        result = run_regeneration_v3(company=args.company, dry_run=args.dry_run)
    else:
        result = run_regeneration(company=args.company, dry_run=args.dry_run)

    decision = result.get("decision")
    if decision in ("REUSE_EXISTING_GENERATION", "EXISTING_EXECUTION_ARTIFACT_INTEGRITY_FAILURE",
                    "EXISTING_FAILED_EXECUTION_REQUIRES_NEW_CONTRACT_OR_EXPLICIT_RETRY_POLICY"):
        print(f"[M45] Done. decision={decision} provider_calls={result.get('provider_calls', 0)}")
        print(f"[M45] execution_id={result.get('existing_execution_id') or result.get('execution_id')}")
        print(f"[M45] outcome={result.get('pacp_overall', result.get('prior_outcome', 'N/A'))}")
        if result.get("candidate_path"):
            print(f"[M45] Candidate: {result['candidate_path']}")
    else:
        latest = result["execution_history"][-1] if result.get("execution_history") else {}
        outcome = latest.get("outcome", "UNKNOWN")
        pacp = latest.get("pacp_result", {}).get("overall", "UNKNOWN")
        attempt = latest.get("attempt", "?")
        print(f"[M45] Done. attempt={attempt} outcome={outcome} pacp={pacp}")
        print(f"[M45] execution_id={latest.get('execution_id')}")
        print(f"[M45] total_ai_calls_m45_family={result.get('total_ai_calls_m45_family')}")
        if latest.get("candidate_path"):
            print(f"[M45] Candidate: {latest['candidate_path']}")
    print(f"[M45] Manifest: companies/{args.company}/company_memory/ask_intrinsiciq/{MANIFEST_FILENAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
