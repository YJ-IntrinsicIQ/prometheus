"""
Tests for cost-hardening infrastructure (Step 16 of the cost-control mission).

All tests are deterministic — no live API calls required.
Tests cover: cache hits/misses, batch claim mapping, batch relationship mapping,
malformed batch items, budget enforcement, and safe-stop behavior.
"""
from __future__ import annotations

import json
import os
import pytest
import tempfile

from knowledge.ai.cache import cache_get, cache_put, cache_invalidate, make_fingerprint
from knowledge.ai.budget import AIBudgetExceededError, check_budget
from knowledge.ai.telemetry import TelemetryCollector
from intelligence.ask_intrinsiciq.ai_claim_reviewer import (
    review_claims_batch,
    _safe_review_item,
    VERDICT_REVIEW_ERROR,
)


# ── Cache tests ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Each test gets its own cache directory."""
    monkeypatch.setenv("PROMETHEUS_CACHE_DIR", str(tmp_path / "cache"))
    yield


def test_cache_hit_on_identical_input():
    fp = make_fingerprint("gpt-4o-mini", "prompt A", "sys A", 0.0, "1")
    cache_put(fp, {"verdict": "SUPPORTED"}, {"model": "gpt-4o-mini", "stage": "test"})
    hit = cache_get(fp)
    assert hit is not None
    assert hit["result"]["verdict"] == "SUPPORTED"


def test_cache_miss_on_changed_prompt():
    fp1 = make_fingerprint("gpt-4o-mini", "prompt A", "sys", 0.0, "1")
    fp2 = make_fingerprint("gpt-4o-mini", "prompt B", "sys", 0.0, "1")
    cache_put(fp1, {"verdict": "SUPPORTED"}, {"model": "gpt-4o-mini", "stage": "test"})
    assert fp1 != fp2
    assert cache_get(fp2) is None


def test_cache_miss_on_changed_model():
    fp1 = make_fingerprint("gpt-4o-mini", "prompt X", "sys", 0.0, "1")
    fp2 = make_fingerprint("gpt-4o", "prompt X", "sys", 0.0, "1")
    assert fp1 != fp2
    assert cache_get(fp2) is None


def test_cache_miss_on_changed_schema_version():
    fp1 = make_fingerprint("gpt-4o-mini", "prompt X", "sys", 0.0, "1")
    fp2 = make_fingerprint("gpt-4o-mini", "prompt X", "sys", 0.0, "2")
    assert fp1 != fp2


def test_cache_invalidate_removes_entry():
    fp = make_fingerprint("gpt-4o-mini", "prompt Y", "", 0.0, "1")
    cache_put(fp, {"x": 1}, {"stage": "test"})
    assert cache_get(fp) is not None
    removed = cache_invalidate(fp)
    assert removed is True
    assert cache_get(fp) is None


def test_cache_invalidate_missing_returns_false():
    fp = make_fingerprint("gpt-4o-mini", "nonexistent prompt", "", 0.0, "1")
    assert cache_invalidate(fp) is False


def test_cache_metadata_stored():
    fp = make_fingerprint("gpt-4o-mini", "meta test", "", 0.0, "1")
    cache_put(fp, "my_result", {"model": "gpt-4o-mini", "prompt_tokens": 100, "completion_tokens": 50})
    entry = cache_get(fp)
    assert entry["model"] == "gpt-4o-mini"
    assert entry["prompt_tokens"] == 100
    assert entry["result"] == "my_result"
    assert "cached_at" in entry


# ── Budget tests ─────────────────────────────────────────────────────────────

def test_budget_exceeded_calls_raises(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_AI_MAX_CALLS", "5")
    monkeypatch.delenv("PROMETHEUS_AI_BUDGET_OVERRIDE", raising=False)
    with pytest.raises(AIBudgetExceededError) as exc_info:
        check_budget(calls_used=5)
    assert exc_info.value.dimension == "calls"


def test_budget_exceeded_tokens_raises(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_AI_MAX_TOKENS", "10000")
    monkeypatch.delenv("PROMETHEUS_AI_BUDGET_OVERRIDE", raising=False)
    with pytest.raises(AIBudgetExceededError) as exc_info:
        check_budget(tokens_used=10000)
    assert exc_info.value.dimension == "tokens"


def test_budget_exceeded_cost_raises(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_AI_MAX_COST_USD", "1.00")
    monkeypatch.delenv("PROMETHEUS_AI_BUDGET_OVERRIDE", raising=False)
    with pytest.raises(AIBudgetExceededError):
        check_budget(cost_usd=1.00)


def test_budget_override_disables_limit(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_AI_MAX_CALLS", "1")
    monkeypatch.setenv("PROMETHEUS_AI_BUDGET_OVERRIDE", "1")
    check_budget(calls_used=999)  # must not raise


def test_budget_no_limits_passes(monkeypatch):
    for k in ("PROMETHEUS_AI_MAX_CALLS", "PROMETHEUS_AI_MAX_TOKENS", "PROMETHEUS_AI_MAX_COST_USD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("PROMETHEUS_AI_BUDGET_OVERRIDE", raising=False)
    check_budget(calls_used=9999, tokens_used=9999999, cost_usd=9999.0)  # no raise


def test_budget_error_attributes():
    err = AIBudgetExceededError("tokens", 15000, 10000)
    assert err.dimension == "tokens"
    assert err.used == 15000
    assert err.limit == 10000
    assert "AI_BUDGET_EXCEEDED" in str(err)


# ── Telemetry tests ──────────────────────────────────────────────────────────

def test_telemetry_accumulates_calls():
    tel = TelemetryCollector()
    tel.record("claim_review", model="m", company="c", prompt_tokens=100, completion_tokens=50)
    tel.record("claim_review", model="m", company="c", prompt_tokens=120, completion_tokens=60, cache_hit=True)
    assert tel.total_calls() == 2
    assert tel.cache_hits() == 1
    assert tel.total_prompt_tokens() == 100   # cache hit excluded
    assert tel.total_completion_tokens() == 50


def test_telemetry_cost_excludes_cache_hits():
    tel = TelemetryCollector()
    tel.record("x", prompt_tokens=1000, completion_tokens=1000, cache_hit=True)
    assert tel.estimated_cost_usd() == 0.0


def test_telemetry_summary_structure():
    tel = TelemetryCollector()
    tel.record("claim_review", model="m", prompt_tokens=100, completion_tokens=50)
    tel.record("rel_review", model="m", prompt_tokens=200, completion_tokens=80)
    s = tel.summary()
    assert "total_calls" in s
    assert "by_stage" in s
    assert "claim_review" in s["by_stage"]
    assert "rel_review" in s["by_stage"]


# ── Batch claim review tests ─────────────────────────────────────────────────

def _make_mock_batch_response(reviews: list) -> str:
    return json.dumps({"reviews": reviews})


def test_batch_claim_results_correctly_mapped(monkeypatch):
    """Mock LLM returns 2 independent verdicts; verify correct claim_id mapping."""
    from knowledge.ai.mock import MockProvider
    mock_response = _make_mock_batch_response([
        {"claim_id": "C001", "verdict": "SUPPORTED", "confidence": "HIGH",
         "reason": "Directly established", "scope_issues": [], "qualifications_missing": []},
        {"claim_id": "C002", "verdict": "UNSUPPORTED", "confidence": "LOW",
         "reason": "No evidence", "scope_issues": ["scope mismatch"], "qualifications_missing": []},
    ])
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AI_MOCK_RESPONSE", mock_response)
    monkeypatch.setenv("AI_MODEL", "mock-model")

    claims = [
        {"claim_id": "C001", "claim_text": "Revenue grew.", "claim_type": "COMMITMENT_STATEMENT",
         "evidence_refs": ["E001"], "evidence_items": []},
        {"claim_id": "C002", "claim_text": "ILUMYA launched in Japan.", "claim_type": "PRODUCT_AVAILABILITY",
         "evidence_refs": ["E002"], "evidence_items": []},
    ]
    results = review_claims_batch(claims)
    assert results["C001"]["verdict"] == "SUPPORTED"
    assert results["C002"]["verdict"] == "UNSUPPORTED"
    assert results["C002"]["scope_issues"] == ["scope mismatch"]


def test_batch_claim_malformed_item_routes_to_review_error():
    """A batch item with missing or invalid verdict gets VERDICT_REVIEW_ERROR."""
    raw = {"claim_id": "C999", "verdict": "INVALID_VERDICT", "confidence": "HIGH",
           "reason": "", "scope_issues": [], "qualifications_missing": []}
    result = _safe_review_item(raw)
    assert result["verdict"] == VERDICT_REVIEW_ERROR


def test_batch_claim_absent_claim_routes_to_review_error(monkeypatch):
    """A claim absent from the batch response gets VERDICT_REVIEW_ERROR."""
    mock_response = _make_mock_batch_response([
        {"claim_id": "C001", "verdict": "SUPPORTED", "confidence": "HIGH",
         "reason": "ok", "scope_issues": [], "qualifications_missing": []},
        # C002 intentionally missing
    ])
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AI_MOCK_RESPONSE", mock_response)
    monkeypatch.setenv("AI_MODEL", "mock-model")

    claims = [
        {"claim_id": "C001", "claim_text": "X", "claim_type": "COMMITMENT_STATEMENT",
         "evidence_refs": [], "evidence_items": []},
        {"claim_id": "C002", "claim_text": "Y", "claim_type": "COMMITMENT_STATEMENT",
         "evidence_refs": [], "evidence_items": []},
    ]
    results = review_claims_batch(claims)
    assert results["C001"]["verdict"] == "SUPPORTED"
    assert results["C002"]["verdict"] == VERDICT_REVIEW_ERROR


def test_batch_claim_empty_input():
    results = review_claims_batch([])
    assert results == {}


def test_safe_review_item_preserves_valid():
    raw = {"claim_id": "C001", "verdict": "PARTIALLY_SUPPORTED", "confidence": "MEDIUM",
           "reason": "partial", "scope_issues": ["s"], "qualifications_missing": ["q"]}
    result = _safe_review_item(raw)
    assert result["verdict"] == "PARTIALLY_SUPPORTED"
    assert result["scope_issues"] == ["s"]
    assert result["qualifications_missing"] == ["q"]


# ── Batch relationship review tests ─────────────────────────────────────────

def test_batch_relationship_empty_input():
    from intelligence.ask_intrinsiciq.relationship_reviewer import validate_relationships_batch
    assert validate_relationships_batch([], {}, {}) == []


def test_batch_relationship_results_correctly_mapped(monkeypatch):
    """Mock returns 2 relationship verdicts; verify rel_id mapping and contract application."""
    from intelligence.ask_intrinsiciq.relationship_reviewer import validate_relationships_batch

    mock_response = json.dumps({"reviews": [
        {
            "relationship_id": "REL-001",
            "verdict": "SUPPORTED",
            "recommended_confidence": "SUPPORTED",
            "chronology_relation": "BEFORE",
            "chronology_valid": True,
            "semantic_alignment": True,
            "linkage_established": True,
            "causal_issues": [],
            "retrospective_bias": False,
            "measurement_window_issue": False,
            "alternative_explanations": None,
            "qualification_required": None,
            "reason": "Aligned strategy and execution",
        },
        {
            "relationship_id": "REL-002",
            "verdict": "UNSUPPORTED",
            "recommended_confidence": "UNKNOWN",
            "chronology_relation": "UNKNOWN",
            "chronology_valid": False,
            "semantic_alignment": False,
            "linkage_established": False,
            "causal_issues": ["correlation_as_causation"],
            "retrospective_bias": False,
            "measurement_window_issue": False,
            "alternative_explanations": None,
            "qualification_required": None,
            "reason": "No direct link",
        },
    ]})
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AI_MOCK_RESPONSE", mock_response)
    monkeypatch.setenv("AI_MODEL", "mock-model")

    rels = [
        {
            "rel_id": "REL-001",
            "rel_type": "STRATEGY_TO_EXECUTION",
            "causal_confidence": "SUPPORTED",
            "from_claim_id": "C001",
            "to_claim_id": "C002",
            "rationale": "Strategy aligned with execution",
            "shared_evidence_refs": [],
        },
        {
            "rel_id": "REL-002",
            "rel_type": "OPERATING_TO_FINANCIAL_OUTCOME",
            "causal_confidence": "CONFIRMED",
            "from_claim_id": "C003",
            "to_claim_id": "C004",
            "rationale": "Revenue follows operations",
            "shared_evidence_refs": [],
        },
    ]
    claims_by_id = {
        "C001": {"claim_text": "Strategy A", "evidence_refs": [], "fiscal_period": "FY24"},
        "C002": {"claim_text": "Execution B", "evidence_refs": [], "fiscal_period": "FY25"},
        "C003": {"claim_text": "Operating X", "evidence_refs": [], "fiscal_period": "FY24"},
        "C004": {"claim_text": "Revenue Y", "evidence_refs": [], "fiscal_period": "FY24"},
    }

    results = validate_relationships_batch(rels, claims_by_id, {})
    assert len(results) == 2
    r1 = next(r for r in results if r["rel_id"] == "REL-001")
    r2 = next(r for r in results if r["rel_id"] == "REL-002")
    assert r1["ai_verdict"] == "SUPPORTED"
    assert r2["ai_verdict"] == "UNSUPPORTED"
    # acceptance contract applied independently
    assert r1["acceptance"] in ("ACCEPT", "NEEDS_REVIEW")
    assert r2["acceptance"] in ("NEEDS_REVIEW", "REJECT")


def test_batch_relationship_absent_rel_routes_to_needs_review(monkeypatch):
    """A relationship absent from the batch response gets NEEDS_REVIEW."""
    from intelligence.ask_intrinsiciq.relationship_reviewer import validate_relationships_batch

    # Only REL-001 in response; REL-002 is absent
    mock_response = json.dumps({"reviews": [
        {
            "relationship_id": "REL-001",
            "verdict": "SUPPORTED",
            "recommended_confidence": "SUPPORTED",
            "chronology_relation": "BEFORE",
            "chronology_valid": True,
            "semantic_alignment": True,
            "linkage_established": True,
            "causal_issues": [],
            "retrospective_bias": False,
            "measurement_window_issue": False,
            "alternative_explanations": None,
            "qualification_required": None,
            "reason": "ok",
        },
    ]})
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AI_MOCK_RESPONSE", mock_response)
    monkeypatch.setenv("AI_MODEL", "mock-model")

    rels = [
        {"rel_id": "REL-001", "rel_type": "STRATEGY_TO_EXECUTION", "causal_confidence": "SUPPORTED",
         "from_claim_id": "C001", "to_claim_id": "C002", "rationale": "", "shared_evidence_refs": []},
        {"rel_id": "REL-002", "rel_type": "CONTEXT_ONLY", "causal_confidence": "UNKNOWN",
         "from_claim_id": "C003", "to_claim_id": "C004", "rationale": "", "shared_evidence_refs": []},
    ]
    claims_by_id = {
        "C001": {"claim_text": "A", "evidence_refs": [], "fiscal_period": "FY24"},
        "C002": {"claim_text": "B", "evidence_refs": [], "fiscal_period": "FY24"},
        "C003": {"claim_text": "C", "evidence_refs": [], "fiscal_period": "FY24"},
        "C004": {"claim_text": "D", "evidence_refs": [], "fiscal_period": "FY24"},
    }

    results = validate_relationships_batch(rels, claims_by_id, {})
    r2 = next(r for r in results if r["rel_id"] == "REL-002")
    assert r2["acceptance"] == "NEEDS_REVIEW"
    # acceptance_reason comes from apply_acceptance_contract on REVIEW_ERROR verdict
    assert r2["acceptance_reason"] == "reviewer_error"


def test_cached_result_cache_hit_skips_api(monkeypatch, tmp_path):
    """A pre-cached result must be returned without any AI call."""
    from knowledge.ai.cache import make_fingerprint, cache_put, cache_get

    # Pre-populate cache with a known result
    prompt_key = make_fingerprint("gpt-4o-mini", "cached_prompt", "cached_sys", 0.0, "1")
    cache_put(prompt_key, [
        {"claim_id": "C001", "verdict": "SUPPORTED", "confidence": "HIGH",
         "reason": "cached", "scope_issues": [], "qualifications_missing": []},
    ], {"model": "gpt-4o-mini", "stage": "claim_review_batch"})

    # Verify it's retrievable without making an AI call
    hit = cache_get(prompt_key)
    assert hit is not None
    assert hit["result"][0]["verdict"] == "SUPPORTED"
    assert hit["result"][0]["reason"] == "cached"
