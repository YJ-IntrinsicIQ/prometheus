"""
Shadow runner for Mission 16 — runs the Level-3 pipeline silently beside production.

Architecture:
  Production path: reads pre-built answer_cards.json (unchanged, unaffected)
  Shadow path:     runs Level-3 pipeline → logs result for comparison
                   NEVER writes to production files

Feature flags (env vars):
  PROMETHEUS_LEVEL3_SHADOW_ENABLED      default: false
  PROMETHEUS_LEVEL3_SHADOW_COMPANIES    default: sun_pharma,tanla
  PROMETHEUS_LEVEL3_SHADOW_SAMPLE_RATE  default: 1.0 (for precomputed mode; not used at runtime)
  PROMETHEUS_LEVEL3_SHADOW_MAX_CALLS    default: 5  per execution
  PROMETHEUS_LEVEL3_SHADOW_MAX_TOKENS   default: 20000 per execution
  PROMETHEUS_LEVEL3_SHADOW_MAX_COST_USD default: 0.02 per execution
  PROMETHEUS_LEVEL3_SHADOW_LOG_DIR      default: .shadow_logs/

Shadow scope: questions whose domain maps to the M15 claim/relationship validation framework.
Out-of-scope questions receive status SHADOW_SCOPE_NOT_YET_COVERED.

Production answer is NEVER modified or affected by this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]


# ── Feature-flag config ───────────────────────────────────────────────────────

@dataclass
class ShadowConfig:
    enabled: bool
    companies: List[str]
    sample_rate: float
    max_calls: int
    max_tokens: int
    max_cost_usd: float
    log_dir: Path

    @classmethod
    def from_env(cls) -> "ShadowConfig":
        enabled = os.getenv("PROMETHEUS_LEVEL3_SHADOW_ENABLED", "false").lower() in ("1", "true", "yes")
        companies_str = os.getenv("PROMETHEUS_LEVEL3_SHADOW_COMPANIES", "sun_pharma,tanla")
        companies = [c.strip() for c in companies_str.split(",") if c.strip()]
        sample_rate = float(os.getenv("PROMETHEUS_LEVEL3_SHADOW_SAMPLE_RATE", "1.0"))
        max_calls = int(os.getenv("PROMETHEUS_LEVEL3_SHADOW_MAX_CALLS", "5"))
        max_tokens = int(os.getenv("PROMETHEUS_LEVEL3_SHADOW_MAX_TOKENS", "20000"))
        max_cost_usd = float(os.getenv("PROMETHEUS_LEVEL3_SHADOW_MAX_COST_USD", "0.02"))
        log_dir = Path(os.getenv("PROMETHEUS_LEVEL3_SHADOW_LOG_DIR", str(REPO / ".shadow_logs")))
        return cls(
            enabled=enabled,
            companies=companies,
            sample_rate=sample_rate,
            max_calls=max_calls,
            max_tokens=max_tokens,
            max_cost_usd=max_cost_usd,
            log_dir=log_dir,
        )


# ── Question scope mapping ────────────────────────────────────────────────────

# Maps question_id → domain question for the Level-3 pipeline.
# Only questions within M15's claim/relationship validation scope are mapped.
_SHADOW_QUESTION_MAP: Dict[str, str] = {
    "how-is-capital-allocated": (
        "How is capital allocated and how do those choices connect to execution and business outcomes?"
    ),
    "did-execution-lead-to-outcomes": (
        "Did management's execution of strategic initiatives lead to observable business outcomes?"
    ),
    "which-investments-created-value": (
        "Which investments have created value and how does capital allocation connect to returns?"
    ),
    "what-has-management-promised": (
        "What has management committed to deliver and how does that connect to operational execution?"
    ),
    "what-is-the-return-on-capex": (
        "What is the return on capital expenditure and how does execution connect to financial outcomes?"
    ),
    "what-was-delivered-last-3-years": (
        "What execution milestones were delivered and how do they connect to observable business outcomes?"
    ),
    "what-is-management-commentary-saying": (
        "What is management commentary revealing about strategic direction, capital allocation, and execution?"
    ),
    "what-can-break-the-thesis": (
        "What risks exist in the execution and capital allocation path and how do they connect to business outcomes?"
    ),
    "what-projects-are-underway": (
        "What capital allocation and execution projects are underway and how do they connect to outcomes?"
    ),
    "did-past-claims-come-true": (
        "Did management's past commitments come true and how does execution connect to delivered outcomes?"
    ),
}

SHADOW_COMPATIBLE_QUESTIONS = set(_SHADOW_QUESTION_MAP.keys())


def get_shadow_domain_question(question_id: str) -> Optional[str]:
    return _SHADOW_QUESTION_MAP.get(question_id)


# ── Shadow result contract ────────────────────────────────────────────────────

SHADOW_STATUS_PASS = "PASS"
SHADOW_STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
SHADOW_STATUS_FAIL = "FAIL"
SHADOW_STATUS_SCOPE_NOT_COVERED = "SHADOW_SCOPE_NOT_YET_COVERED"
SHADOW_STATUS_BUDGET_EXCEEDED = "SHADOW_BUDGET_EXCEEDED"
SHADOW_STATUS_EXECUTION_FAILURE = "SHADOW_EXECUTION_FAILURE"
SHADOW_STATUS_DISABLED = "SHADOW_DISABLED"
SHADOW_STATUS_COMPANY_NOT_IN_SCOPE = "SHADOW_COMPANY_NOT_IN_SCOPE"


@dataclass
class ShadowResult:
    request_id: str
    company: str
    question_id: str
    question_category: str
    domain_question: str
    production_answer_fingerprint: str
    shadow_answer_fingerprint: str

    # Gate results
    claim_gate_status: str = ""
    relationship_gate_status: str = ""
    final_composition_gate: str = ""
    coverage_status: str = ""

    # Counts
    undeclared_claim_count: int = 0
    undeclared_relationship_count: int = 0
    suppressed_relationship_count: int = 0
    needs_review_count: int = 0
    reject_count: int = 0
    review_error_count: int = 0

    # Cost / perf
    latency_ms: float = 0.0
    ai_calls: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0

    # Comparison
    divergence_class: str = ""          # D1-D8
    investor_value: str = ""            # MATERIAL_IMPROVEMENT / MODEST_IMPROVEMENT / EQUIVALENT / WORSE
    divergence_detail: str = ""

    # Status
    shadow_status: str = SHADOW_STATUS_EXECUTION_FAILURE
    failure_reason: str = ""

    # Answers (for logging only)
    production_simple_answer: str = ""
    shadow_simple_answer: str = ""
    shadow_answer: Optional[Dict[str, Any]] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k != "shadow_answer"}
        return d


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── Shadow safety gate ────────────────────────────────────────────────────────

def shadow_safety_gate(
    answer: Dict[str, Any],
    extraction: Dict[str, Any],
    batch_reviews: Dict[str, Any],
    comp_gate: Dict[str, Any],
) -> tuple[str, str]:
    """
    Returns (gate_status, reason).
    A shadow answer is technically valid only if all safety conditions hold.
    """
    issues = []

    if answer.get("_composition_error"):
        issues.append(f"composition_error: {answer['_composition_error'][:80]}")

    if comp_gate.get("gate") != "PASS":
        for issue in comp_gate.get("gate_issues", []):
            issues.append(f"comp_gate: {issue}")

    undeclared = extraction.get("undeclared_claims", [])
    for c in undeclared:
        if c.get("materiality") in ("HIGH", "MEDIUM"):
            issues.append(f"material_undeclared_claim: {c.get('extraction_id')}")

    for cid, review in batch_reviews.items():
        if review.get("verdict") == "CONTRADICTED":
            issues.append(f"CRITICAL_contradicted_claim: {cid}")

    if not issues:
        return SHADOW_STATUS_PASS, ""
    return SHADOW_STATUS_FAIL, "; ".join(issues)


# ── Divergence classification ─────────────────────────────────────────────────

_CAUSAL_PHRASES = re.compile(
    r"\b(caused?|drove?|driven|resulted in|led to|contributed to|directly caused|"
    r"attributed to|responsible for|explains?|accounts? for|produc(?:ed|ing))\b",
    re.IGNORECASE,
)

_HEDGE_PHRASES = re.compile(
    r"\b(may|might|could|appear|appear to|seem|seems|suggest|suggests|"
    r"cannot be established|unclear|uncertain|not establish|evidence does not)\b",
    re.IGNORECASE,
)


def classify_divergence(
    production_card: Dict[str, Any],
    shadow_answer: Dict[str, Any],
    shadow_gate: str,
) -> tuple[str, str, str]:
    """
    Returns (divergence_class, investor_value, detail).
    """
    if shadow_gate in (SHADOW_STATUS_EXECUTION_FAILURE, SHADOW_STATUS_BUDGET_EXCEEDED):
        return "D8", "WORSE", "Shadow execution failure"

    if shadow_gate == SHADOW_STATUS_FAIL:
        detail = shadow_answer.get("_composition_error", "gate_fail")[:100]
        return "D8", "WORSE", f"Shadow gate failure: {detail}"

    prod_sa = str(production_card.get("simple_answer") or "")
    prod_kps = " ".join(production_card.get("key_points") or [])
    prod_prose = (prod_sa + " " + prod_kps).lower()

    shad_sa = str(shadow_answer.get("simple_answer") or "")
    shad_wi = str(shadow_answer.get("why_it_matters") or "")
    shad_inv = str(shadow_answer.get("investor_interpretation") or "")
    shad_kps = " ".join(str(k) for k in (shadow_answer.get("key_points") or []))
    shad_prose = (shad_sa + " " + shad_wi + " " + shad_inv + " " + shad_kps).lower()

    # D4/D5 check: shadow makes strong causal claims without hedge
    causal_in_shadow = _CAUSAL_PHRASES.findall(shad_prose)
    hedge_in_shadow = _HEDGE_PHRASES.findall(shad_prose)
    unhedged_causal = len(causal_in_shadow) > len(hedge_in_shadow) * 2

    if unhedged_causal:
        return "D4", "WORSE", f"Shadow has {len(causal_in_shadow)} causal phrases, only {len(hedge_in_shadow)} hedges"

    # D2: shadow removes unsupported assertion from production
    # Check if production makes strong causal claims shadow doesn't
    causal_in_prod = _CAUSAL_PHRASES.findall(prod_prose)
    hedge_in_prod = _HEDGE_PHRASES.findall(prod_prose)
    prod_causal_unhedged = len(causal_in_prod) > len(hedge_in_prod) * 2
    shad_more_hedged = len(hedge_in_shadow) > len(hedge_in_prod)

    if prod_causal_unhedged and shad_more_hedged:
        return "D2", "MODEST_IMPROVEMENT", "Shadow more cautious on causal claims than production"

    # D6: production has useful content shadow is missing
    prod_words = set(re.findall(r'\b[a-z]+\b', prod_prose.lower()))
    shad_words = set(re.findall(r'\b[a-z]+\b', shad_prose.lower()))
    unique_to_prod = prod_words - shad_words
    # If production has many unique meaningful words, shadow may have missed content
    meaningful_unique_prod = {w for w in unique_to_prod if len(w) > 5}

    if len(meaningful_unique_prod) > 50:
        return "D6", "WORSE", f"{len(meaningful_unique_prod)} meaningful words in production not in shadow"

    # D3: shadow excessively cautious (much shorter, less informative)
    if len(shad_prose) < len(prod_prose) * 0.3:
        return "D3", "WORSE", f"Shadow prose {len(shad_prose)} chars vs production {len(prod_prose)} chars"

    # D1: shadow adds useful evidence-backed insight
    claims = shadow_answer.get("claims") or []
    unique_to_shadow = shad_words - prod_words
    meaningful_unique_shad = {w for w in unique_to_shadow if len(w) > 6}

    if len(claims) >= 7 and len(meaningful_unique_shad) > 30:
        return "D1", "MODEST_IMPROVEMENT", f"Shadow has {len(claims)} validated claims, adds {len(meaningful_unique_shad)} unique terms"

    # D7: equivalent
    return "D7", "EQUIVALENT", "No material divergence detected"


def _assess_investor_value(
    production_card: Dict[str, Any],
    shadow_answer: Dict[str, Any],
    divergence_class: str,
) -> str:
    """Returns MATERIAL_IMPROVEMENT | MODEST_IMPROVEMENT | EQUIVALENT | WORSE."""
    if divergence_class in ("D4", "D5", "D8", "D3", "D6"):
        return "WORSE"
    if divergence_class == "D2":
        return "MODEST_IMPROVEMENT"
    if divergence_class == "D1":
        # Shadow adds validated claims with economic interpretation → material
        claims = shadow_answer.get("claims") or []
        if len(claims) >= 7:
            return "MATERIAL_IMPROVEMENT"
        return "MODEST_IMPROVEMENT"
    return "EQUIVALENT"


# ── Core shadow execution ─────────────────────────────────────────────────────

def run_shadow_for_question(
    company: str,
    company_display_name: str,
    question_id: str,
    question_category: str,
    production_card: Dict[str, Any],
    composition_plan: Dict[str, Any],
    config: ShadowConfig,
    telemetry_ref: Optional[Any] = None,  # TelemetryCollector, imported lazily
) -> ShadowResult:
    """
    Run Level-3 shadow pipeline for one (company, question_id) pair.
    Production card is passed in read-only for comparison only.
    """
    import uuid
    request_id = str(uuid.uuid4())[:8]

    prod_sa = str(production_card.get("simple_answer") or "")
    prod_fp = _fingerprint(prod_sa)
    domain_q = get_shadow_domain_question(question_id)

    result = ShadowResult(
        request_id=request_id,
        company=company,
        question_id=question_id,
        question_category=question_category,
        domain_question=domain_q or "",
        production_answer_fingerprint=prod_fp,
        shadow_answer_fingerprint="",
        production_simple_answer=prod_sa[:200],
    )

    if not domain_q:
        result.shadow_status = SHADOW_STATUS_SCOPE_NOT_COVERED
        result.failure_reason = "Question not within M15 claim/relationship scope"
        return result

    # Import lazily to avoid circular imports at module level
    from intelligence.ask_intrinsiciq.relationship_aware_composer import (
        compose_answer_from_plan,
        assess_composition_gate,
    )
    from intelligence.ask_intrinsiciq.claim_extractor import extract_claims
    from intelligence.ask_intrinsiciq.ai_claim_reviewer import review_claims_batch
    from knowledge.ai.cache import cache_get, cache_put, make_fingerprint
    from knowledge.ai.budget import check_budget, AIBudgetExceededError
    from knowledge.ai.telemetry import TelemetryCollector

    tel = telemetry_ref if telemetry_ref is not None else TelemetryCollector()
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    # Per-question budget (isolated from global telemetry)
    os.environ.setdefault("PROMETHEUS_AI_BUDGET_MODE", "strict")
    max_calls_env = os.environ.get("PROMETHEUS_AI_MAX_CALLS")
    max_tokens_env = os.environ.get("PROMETHEUS_AI_MAX_TOKENS")
    max_cost_env = os.environ.get("PROMETHEUS_AI_MAX_COST_USD")

    # Temporarily set question-level budget
    os.environ["PROMETHEUS_AI_MAX_CALLS"] = str(config.max_calls)
    os.environ["PROMETHEUS_AI_MAX_TOKENS"] = str(config.max_tokens)
    os.environ["PROMETHEUS_AI_MAX_COST_USD"] = str(config.max_cost_usd)

    t_start = time.perf_counter()

    try:
        # Cache key includes question_id so different questions get different answers
        from intelligence.ask_intrinsiciq.relationship_aware_composer import _build_composition_system_prompt, typed_event_lines
        system_prompt = _build_composition_system_prompt(composition_plan, domain_q)
        evidence_lines = []
        all_claims = composition_plan.get("allowed_claims", []) + composition_plan.get("qualified_claims", [])
        for c in all_claims[:10]:
            evidence_lines.append(f"[{c.get('claim_id','?')}] {c.get('claim_text','?')}")
        user_content = (
            f"Company: {company_display_name}\n"
            f"Question: {domain_q}\n\n"
            "Validated claims:\n" + "\n".join(evidence_lines)
            + ("\n\nTyped evidence records:\n" + "\n".join(typed_event_lines(composition_plan.get("typed_evidence"))) if composition_plan.get("typed_evidence") else "")
            + "\n\nGenerate the investor answer as a JSON object following the composition contract."
        )
        fp = make_fingerprint(model, user_content, system_prompt, 0.0, f"m16_shadow_{question_id}_v1")
        cached = cache_get(fp)

        if cached:
            answer = cached["result"]
            tel.record("shadow_composition", model=model, company=company,
                       prompt_tokens=0, completion_tokens=0, cache_hit=True, batch_size=1)
        else:
            check_budget(
                calls_used=tel.total_calls() - tel.cache_hits(),
                tokens_used=tel.total_tokens(),
                cost_usd=tel.estimated_cost_usd(),
            )
            answer = compose_answer_from_plan(composition_plan, domain_q, company_display_name, model=model)
            if not answer.get("_composition_error"):
                cache_put(fp, answer, {"model": model, "stage": "shadow_composition",
                                       "company": company, "question_id": question_id})
            tel.record("shadow_composition", model=model, company=company,
                       prompt_tokens=1800, completion_tokens=400, cache_hit=False, batch_size=1)

        result.shadow_answer = answer
        result.shadow_simple_answer = str(answer.get("simple_answer") or "")[:300]
        result.shadow_answer_fingerprint = _fingerprint(str(answer.get("simple_answer") or ""))

        # Composition gate (deterministic)
        comp_gate = assess_composition_gate(answer, composition_plan)
        result.final_composition_gate = comp_gate.get("gate", "")
        result.suppressed_relationship_count = len(composition_plan.get("suppressed_relationships", []))

        # Claim extraction
        from scratchpad.m15_composition_runner import _adapt_composition_answer_for_extractor, _build_minimal_evidence_package

        adapted = _adapt_composition_answer_for_extractor(answer)
        evidence_pkg = _build_minimal_evidence_package(composition_plan)

        declared_ids = sorted(c["claim_id"] for c in (adapted.get("claims") or []))
        prose_key = (
            adapted.get("simple_answer", "")
            + adapted.get("why_it_matters", "")
            + adapted.get("investor_interpretation", "")
            + "|decl:" + ",".join(declared_ids)
            + f"|q:{question_id}"
        )
        ext_fp = make_fingerprint(model, prose_key, "shadow_extraction_v1", 0.0, "1")
        ext_cached = cache_get(ext_fp)

        if ext_cached:
            extraction = ext_cached["result"]
            tel.record("shadow_extraction", model=model, company=company, cache_hit=True, batch_size=1)
        else:
            check_budget(
                calls_used=tel.total_calls() - tel.cache_hits(),
                tokens_used=tel.total_tokens(),
                cost_usd=tel.estimated_cost_usd(),
            )
            extraction = extract_claims(adapted, evidence_pkg, model=model)
            # Data-derived coverage upgrade (same as m15 runner)
            if (not extraction.get("extraction_error")
                    and extraction.get("undeclared_count", 0) == 0
                    and extraction.get("coverage_assessment") != "COMPLETE"):
                if all(c.get("declared_match") for c in extraction.get("extracted_claims", [])):
                    extraction["coverage_assessment"] = "COMPLETE"
                    extraction["coverage_notes"] = "data-derived: all matched, undeclared=0"
            if not extraction.get("extraction_error"):
                cache_put(ext_fp, extraction, {"model": model, "stage": "shadow_extraction", "company": company})
            tel.record("shadow_extraction", model=model, company=company,
                       prompt_tokens=3000, completion_tokens=1000, cache_hit=False, batch_size=1)

        undeclared = extraction.get("undeclared_claims", [])
        result.undeclared_claim_count = len(undeclared)
        result.coverage_status = extraction.get("coverage_assessment", "INCOMPLETE")

        # Batch review undeclared
        batch_reviews: Dict[str, Any] = {}
        if undeclared:
            claims_for_review = [
                {
                    "claim_id": c.get("extraction_id", f"UC-{i}"),
                    "claim_text": c.get("claim_text", ""),
                    "claim_type": c.get("claim_type", "UNKNOWN"),
                    "evidence_refs": c.get("suggested_refs", []),
                    "evidence_items": [],
                }
                for i, c in enumerate(undeclared)
            ]
            check_budget(
                calls_used=tel.total_calls() - tel.cache_hits(),
                tokens_used=tel.total_tokens(),
                cost_usd=tel.estimated_cost_usd(),
            )
            batch_reviews = review_claims_batch(claims_for_review, model=model, schema_version="shadow_v1")
            tel.record("shadow_batch_review", model=model, company=company,
                       prompt_tokens=800 * len(undeclared), completion_tokens=200 * len(undeclared),
                       cache_hit=False, batch_size=len(undeclared))

        # Count verdict types
        from intelligence.ask_intrinsiciq.ai_claim_reviewer import VERDICT_REVIEW_ERROR
        for cid, rev in batch_reviews.items():
            v = rev.get("verdict", "")
            if v == "NEEDS_REVIEW":
                result.needs_review_count += 1
            elif v in ("CONTRADICTED", "REJECT"):
                result.reject_count += 1
            elif v == VERDICT_REVIEW_ERROR:
                result.review_error_count += 1

        # Shadow safety gate
        gate_status, gate_reason = shadow_safety_gate(answer, extraction, batch_reviews, comp_gate)
        result.claim_gate_status = gate_status
        result.relationship_gate_status = comp_gate.get("gate", "")

        # Divergence classification
        div_class, inv_value, div_detail = classify_divergence(production_card, answer, gate_status)
        result.divergence_class = div_class
        result.investor_value = inv_value
        result.divergence_detail = div_detail

        result.shadow_status = gate_status
        result.failure_reason = gate_reason

    except Exception as exc:
        # Failure isolation: shadow failure NEVER propagates
        exc_name = type(exc).__name__
        result.shadow_status = SHADOW_STATUS_EXECUTION_FAILURE
        result.failure_reason = f"{exc_name}: {str(exc)[:120]}"
        if "AIBudgetExceededError" in exc_name or "budget" in str(exc).lower():
            result.shadow_status = SHADOW_STATUS_BUDGET_EXCEEDED
    finally:
        # Restore original budget env vars
        if max_calls_env is not None:
            os.environ["PROMETHEUS_AI_MAX_CALLS"] = max_calls_env
        if max_tokens_env is not None:
            os.environ["PROMETHEUS_AI_MAX_TOKENS"] = max_tokens_env
        if max_cost_env is not None:
            os.environ["PROMETHEUS_AI_MAX_COST_USD"] = max_cost_env

    result.latency_ms = (time.perf_counter() - t_start) * 1000
    tel_summary = tel.summary()
    result.ai_calls = tel_summary.get("total_calls", 0)
    result.cache_hits = tel_summary.get("cache_hits", 0)
    result.prompt_tokens = tel_summary.get("total_prompt_tokens", 0)
    result.completion_tokens = tel_summary.get("total_completion_tokens", 0)
    result.estimated_cost_usd = tel_summary.get("estimated_cost_usd", 0.0)

    return result


# ── Shadow log writer ─────────────────────────────────────────────────────────

def write_shadow_log(results: List[ShadowResult], config: ShadowConfig, run_label: str = "") -> Path:
    """Write shadow results to log file. Never writes to production paths."""
    config.log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    label = f"_{run_label}" if run_label else ""
    log_path = config.log_dir / f"shadow_run_{timestamp}{label}.json"
    log_data = {
        "run_label": run_label,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_executions": len(results),
        "results": [r.to_dict() for r in results],
        "summary": _build_summary(results),
    }
    log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False))
    return log_path


def _build_summary(results: List[ShadowResult]) -> Dict[str, Any]:
    pass_count = sum(1 for r in results if r.shadow_status == SHADOW_STATUS_PASS)
    needs_review = sum(1 for r in results if r.shadow_status == SHADOW_STATUS_NEEDS_REVIEW)
    fail_count = sum(1 for r in results if r.shadow_status == SHADOW_STATUS_FAIL)
    scope_nc = sum(1 for r in results if r.shadow_status == SHADOW_STATUS_SCOPE_NOT_COVERED)
    exec_fail = sum(1 for r in results if r.shadow_status in (
        SHADOW_STATUS_EXECUTION_FAILURE, SHADOW_STATUS_BUDGET_EXCEEDED))

    active = [r for r in results if r.shadow_status not in (
        SHADOW_STATUS_SCOPE_NOT_COVERED, SHADOW_STATUS_DISABLED)]

    total_calls = sum(r.ai_calls for r in active)
    total_cache = sum(r.cache_hits for r in active)
    total_tokens = sum(r.prompt_tokens + r.completion_tokens for r in active)
    total_cost = sum(r.estimated_cost_usd for r in active)
    latencies = [r.latency_ms for r in active if r.latency_ms > 0]

    div_counts: Dict[str, int] = {}
    for r in active:
        if r.divergence_class:
            div_counts[r.divergence_class] = div_counts.get(r.divergence_class, 0) + 1

    inv_counts: Dict[str, int] = {}
    for r in active:
        if r.investor_value:
            inv_counts[r.investor_value] = inv_counts.get(r.investor_value, 0) + 1

    n = len(active)
    return {
        "total": len(results),
        "pass": pass_count,
        "needs_review": needs_review,
        "fail": fail_count,
        "scope_not_covered": scope_nc,
        "execution_failure": exec_fail,
        "total_undeclared_claims": sum(r.undeclared_claim_count for r in active),
        "total_rejected_claims": sum(r.reject_count for r in active),
        "total_review_errors": sum(r.review_error_count for r in active),
        "critical_d4_d5_count": sum(1 for r in active if r.divergence_class in ("D4", "D5")),
        "ai_calls_total": total_calls,
        "cache_hits_total": total_cache,
        "cache_hit_rate": round(total_cache / total_calls, 3) if total_calls > 0 else 0,
        "avg_calls_per_execution": round(total_calls / n, 2) if n > 0 else 0,
        "avg_tokens_per_execution": round(total_tokens / n, 0) if n > 0 else 0,
        "avg_cost_per_execution": round(total_cost / n, 6) if n > 0 else 0,
        "total_cost_usd": round(total_cost, 6),
        "p50_latency_ms": _percentile(latencies, 50),
        "p95_latency_ms": _percentile(latencies, 95),
        "divergence_counts": div_counts,
        "investor_value_counts": inv_counts,
    }


def _percentile(values: List[float], p: int) -> float:
    if not values:
        return 0.0
    sv = sorted(values)
    idx = max(0, int(len(sv) * p / 100) - 1)
    return round(sv[idx], 1)
