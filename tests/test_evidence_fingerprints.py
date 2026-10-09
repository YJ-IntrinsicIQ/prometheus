"""
M40 Evidence Fingerprint & Dependency Registry Tests.

Tests:
  FP-01  Identical canonical content → same digest
  FP-02  Semantic field change → different digest
  FP-03  Timestamp-only change → same digest
  FP-04  Record-order change → same digest (stable semantic sort)
  DEP-01 Unrelated module change does not dirty answer
  DEP-02 Required module change dirties answer
  DEP-03 Deterministic answer never requests AI regeneration
  DEP-04 Shared generation unit dirties all dependent UI questions without AI duplication
  DEP-05 Dependency schema change is detected
  UI-01  User request cannot cause AI invocation (architecture check)
  LEGACY-01 Eliminable capital-allocation AI path classified deterministic
  LEGACY-02 Eliminable management-promises AI path classified deterministic
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.evidence_fingerprints import (
    NON_SEMANTIC_FIELDS,
    compute_digest,
    compute_module_fingerprint,
    normalize_for_hashing,
)
from intelligence.shadow_change_detector import (
    CLEAN,
    FINGERPRINT_SCHEMA_MISMATCH,
    MISSING_BASELINE,
    WOULD_REGENERATE_AI,
    WOULD_RECOMPUTE_DETERMINISTIC,
    evaluate_answer_freshness,
    evaluate_all_questions,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
COMPANIES_ROOT = Path(__file__).resolve().parent.parent / "companies"
PRIMARY_COMPANY = "sun_pharma"


def _load_baseline(company: str = PRIMARY_COMPANY) -> dict:
    path = COMPANIES_ROOT / company / "company_memory" / "ask_intrinsiciq" / "evidence_fingerprint_registry.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _dirty_baseline(baseline: dict, modules: list[str]) -> dict:
    """Return a copy of baseline with digests corrupted for specified modules."""
    b = copy.deepcopy(baseline)
    for mod in modules:
        if mod in b["modules"]:
            b["modules"][mod]["digest"] = b["modules"][mod]["digest"][:-4] + "XXXX"
    return b


# Pre-load so tests run fast (one disk read per session)
@pytest.fixture(scope="module")
def baseline_sp():
    return _load_baseline(PRIMARY_COMPANY)


# ---------------------------------------------------------------------------
# FP-01: Identical canonical content → same digest
# ---------------------------------------------------------------------------
def test_fp01_identical_content_same_digest():
    payload = {"field_a": "value", "numbers": [1, 2, 3], "nested": {"x": 1}}
    d1 = compute_digest(payload)
    d2 = compute_digest(payload)
    assert d1 == d2, "Same content must always produce same digest"
    assert d1.startswith("sha256:")


# ---------------------------------------------------------------------------
# FP-02: Semantic field change → different digest
# ---------------------------------------------------------------------------
def test_fp02_semantic_change_different_digest():
    base = {"record_id": "R001", "attribution": "DIRECTLY_ATTRIBUTABLE", "amount": 100}
    changed = {**base, "attribution": "NO_OUTCOME_EVIDENCE"}
    assert compute_digest(base) != compute_digest(changed), (
        "Changing a semantic field must produce a different digest"
    )


def test_fp02_financial_value_change_different_digest():
    base = {"year": "FY24", "revenue_cr": 5000, "attribution": "DIRECTLY_ATTRIBUTABLE"}
    changed = {**base, "revenue_cr": 5500}
    assert compute_digest(base) != compute_digest(changed)


def test_fp02_status_field_change_different_digest():
    base = {"record_id": "MP-001", "current_status": "delivered", "lifecycle": "operational"}
    changed = {**base, "current_status": "overdue"}
    assert compute_digest(base) != compute_digest(changed)


# ---------------------------------------------------------------------------
# FP-03: Timestamp-only change → same digest
# ---------------------------------------------------------------------------
def test_fp03_generated_at_excluded():
    payload1 = {"company": "sun_pharma", "generated_at": "2026-09-01T00:00:00Z", "data": "evidence"}
    payload2 = {"company": "sun_pharma", "generated_at": "2026-10-05T12:00:00Z", "data": "evidence"}
    assert compute_digest(payload1) == compute_digest(payload2), (
        "generated_at must not affect digest"
    )


def test_fp03_all_non_semantic_excluded():
    """No non-semantic field alone should change the digest."""
    base = {"company": "sun_pharma", "record_id": "R001", "value": 42}
    for excluded_field in NON_SEMANTIC_FIELDS:
        with_field = {**base, excluded_field: "some_runtime_value"}
        assert compute_digest(base) == compute_digest(with_field), (
            f"Non-semantic field '{excluded_field}' must not affect digest"
        )


# ---------------------------------------------------------------------------
# FP-04: Record-order change → same digest (stable semantic sort for list-of-dicts)
# ---------------------------------------------------------------------------
def test_fp04_record_order_independent_by_stable_key():
    records_a = [
        {"record_id": "R001", "value": "alpha"},
        {"record_id": "R002", "value": "beta"},
        {"record_id": "R003", "value": "gamma"},
    ]
    records_b = [
        {"record_id": "R003", "value": "gamma"},
        {"record_id": "R001", "value": "alpha"},
        {"record_id": "R002", "value": "beta"},
    ]
    payload_a = {"records": records_a}
    payload_b = {"records": records_b}
    assert compute_digest(payload_a) == compute_digest(payload_b), (
        "List-of-dicts with stable record_id key must produce same digest regardless of order"
    )


def test_fp04_semantic_field_change_still_different():
    records_a = [{"record_id": "R001", "value": "alpha"}]
    records_b = [{"record_id": "R001", "value": "CHANGED"}]
    assert compute_digest({"records": records_a}) != compute_digest({"records": records_b})


# ---------------------------------------------------------------------------
# DEP-01: Unrelated module change does not dirty answer
# ---------------------------------------------------------------------------
def test_dep01_risk_change_does_not_dirty_management_promises(baseline_sp):
    dirty = _dirty_baseline(baseline_sp, ["risk_assessments", "risk_registry", "risk_evolution"])
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_COMPANY)
    r = evaluate_answer_freshness(PRIMARY_COMPANY, "what-has-management-promised",
                                   baseline=dirty, current=current)
    assert r["result"] == CLEAN, (
        "Risk module change must not dirty management promises"
    )


def test_dep01_financial_change_does_not_dirty_risk_question(baseline_sp):
    dirty = _dirty_baseline(baseline_sp, ["owner_earnings_bridge", "financial_truth_pack"])
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_COMPANY)
    r = evaluate_answer_freshness(PRIMARY_COMPANY, "what-can-break-the-thesis",
                                   baseline=dirty, current=current)
    assert r["result"] == CLEAN


# ---------------------------------------------------------------------------
# DEP-02: Required module change dirties answer
# ---------------------------------------------------------------------------
def test_dep02_risk_change_dirties_risk_question(baseline_sp):
    dirty = _dirty_baseline(baseline_sp, ["risk_assessments"])
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_COMPANY)
    r = evaluate_answer_freshness(PRIMARY_COMPANY, "what-can-break-the-thesis",
                                   baseline=dirty, current=current)
    assert r["result"] == WOULD_RECOMPUTE_DETERMINISTIC
    assert "risk_assessments" in r["changed_modules"]


def test_dep02_management_change_dirties_delivery_question(baseline_sp):
    dirty = _dirty_baseline(baseline_sp, ["management_progression"])
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_COMPANY)
    r = evaluate_answer_freshness(PRIMARY_COMPANY, "what-was-delivered-last-3-years",
                                   baseline=dirty, current=current)
    assert r["result"] == WOULD_RECOMPUTE_DETERMINISTIC


# ---------------------------------------------------------------------------
# DEP-03: Deterministic answer never requests AI regeneration
# ---------------------------------------------------------------------------
DETERMINISTIC_QUESTIONS = [
    "what-does-company-do",
    "who-are-the-customers",
    "how-does-it-make-money",
    "are-profits-converting-into-cash",
    "what-is-owner-earnings",
    "is-working-capital-a-concern",
    "are-per-share-economics-improving",
    "what-has-management-promised",
    "what-promise-types-dominate",
    "which-promises-are-overdue",
    "what-was-delivered-last-3-years",
    "what-was-missed",
    "did-past-claims-come-true",
    "did-execution-lead-to-outcomes",
    "what-projects-are-underway",
    "how-is-capacity-changing",
    "what-is-management-commentary-saying",
    "how-is-capital-allocated",
    "which-investments-created-value",
    "what-is-the-return-on-capex",
    "what-incentives-matter",
    "what-regulatory-risks-remain-active",
    "what-can-break-the-thesis",
    "which-disclosure-is-missing",
    "what-should-i-ask-ir",
]


@pytest.mark.parametrize("question_id", DETERMINISTIC_QUESTIONS)
def test_dep03_deterministic_question_never_requests_ai(question_id, baseline_sp):
    """When evidence for a deterministic question changes, result must be
    WOULD_RECOMPUTE_DETERMINISTIC, never WOULD_REGENERATE_AI."""
    # Dirty all modules to force a dirty result
    all_modules = list(baseline_sp["modules"].keys())
    dirty = _dirty_baseline(baseline_sp, all_modules)
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_COMPANY)
    r = evaluate_answer_freshness(PRIMARY_COMPANY, question_id, baseline=dirty, current=current)
    assert r["result"] != WOULD_REGENERATE_AI, (
        f"Deterministic question '{question_id}' must never produce WOULD_REGENERATE_AI"
    )


# ---------------------------------------------------------------------------
# DEP-04: Shared generation unit dirties all dependent questions without AI duplication
# ---------------------------------------------------------------------------
def test_dep04_committee_synthesis_change_dirties_all_committee_questions(baseline_sp):
    dirty = _dirty_baseline(baseline_sp, ["committee_synthesis"])
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_COMPANY)
    committee_questions = [
        "what-is-committee-direction",
        "where-does-the-committee-agree",
        "where-does-the-committee-disagree",
        "what-evidence-would-change-the-view",
        "what-needs-management-clarification",
        "what-remains-unresolved",
    ]
    for q in committee_questions:
        r = evaluate_answer_freshness(PRIMARY_COMPANY, q, baseline=dirty, current=current)
        assert r["result"] == WOULD_REGENERATE_AI, (
            f"'{q}' must be dirty when committee_synthesis changes"
        )
        assert r.get("generation_unit") == "committee_synthesis", (
            f"'{q}' must route to committee_synthesis generation unit, not duplicate"
        )


def test_dep04_committee_synthesis_is_single_unit_not_per_question(baseline_sp):
    """All 6 committee-dependent questions share ONE generation unit (no duplication)."""
    dirty = _dirty_baseline(baseline_sp, ["committee_synthesis"])
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_COMPANY)
    committee_questions = [
        "what-is-committee-direction",
        "where-does-the-committee-agree",
        "where-does-the-committee-disagree",
        "what-evidence-would-change-the-view",
        "what-needs-management-clarification",
        "what-remains-unresolved",
    ]
    units = set()
    for q in committee_questions:
        r = evaluate_answer_freshness(PRIMARY_COMPANY, q, baseline=dirty, current=current)
        units.add(r.get("generation_unit"))
    assert units == {"committee_synthesis"}, (
        "All 6 committee questions must point to ONE generation unit"
    )


# ---------------------------------------------------------------------------
# DEP-05: Dependency schema change is detected
# ---------------------------------------------------------------------------
def test_dep05_schema_version_mismatch_detected(baseline_sp):
    old_schema_baseline = copy.deepcopy(baseline_sp)
    old_schema_baseline["fingerprint_schema_version"] = "0"
    r = evaluate_answer_freshness(
        PRIMARY_COMPANY, "what-can-break-the-thesis",
        baseline=old_schema_baseline,
    )
    assert r["result"] == FINGERPRINT_SCHEMA_MISMATCH, (
        "Mismatched fingerprint schema version must be detected"
    )


# ---------------------------------------------------------------------------
# UI-01: User request cannot cause AI invocation (architecture check)
# ---------------------------------------------------------------------------
def test_ui01_no_llm_import_in_request_path():
    """
    The user request path (load-answer-card.ts) reads from pre-built JSON files.
    Verify that shadow_runner and relationship_aware_composer are NOT imported
    by the production answer serving module (answer_cards.py).
    """
    import importlib.util
    answer_cards_path = (
        Path(__file__).resolve().parent.parent
        / "intelligence" / "ask_intrinsiciq" / "answer_cards.py"
    )
    source = answer_cards_path.read_text(encoding="utf-8")
    # These modules contain LLM call sites and must not be imported by the
    # deterministic answer card builder
    ai_imports = ["relationship_aware_composer", "shadow_runner", "call_llm_with_input_pack"]
    for imp in ai_imports:
        assert imp not in source, (
            f"answer_cards.py must not import '{imp}' — UI path must stay AI-free"
        )


def test_ui01_shadow_answers_served_from_file():
    """
    The canary answer serving reads from shadow_level3_hybrid_answers.json (pre-built file).
    Verify the path reference exists in load-answer-card.ts.
    """
    ts_path = (
        Path(__file__).resolve().parent.parent
        / "apps" / "ask-intrinsiciq" / "src" / "lib" / "ask-intrinsiciq" / "load-answer-card.ts"
    )
    source = ts_path.read_text(encoding="utf-8")
    assert "shadowLevel3HybridAnswers" in source, (
        "load-answer-card.ts must reference paths.shadowLevel3HybridAnswers (pre-built file serving via path abstraction)"
    )
    # Must NOT contain a direct LLM/AI invocation
    ai_call_patterns = ["openai.chat", "anthropic.messages", "completions.create", "call_llm"]
    for pattern in ai_call_patterns:
        assert pattern not in source, (
            f"load-answer-card.ts must not contain '{pattern}' — UI path must stay AI-free"
        )


# ---------------------------------------------------------------------------
# LEGACY-01: Eliminable capital-allocation AI path classified deterministic
# ---------------------------------------------------------------------------
def test_legacy01_capital_allocation_shadow_classified_eliminable():
    registry_path = (
        Path(__file__).resolve().parent.parent
        / "governance" / "answer_dependency_registry.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    eliminable = registry.get("eliminable_ai_paths", {})
    assert "how_is_capital_allocated_shadow" in eliminable, (
        "Capital allocation shadow must be registered as eliminable AI path"
    )
    assert eliminable["how_is_capital_allocated_shadow"]["ai_regeneration_required"] is False, (
        "Capital allocation shadow: ai_regeneration_required must be False"
    )
    assert eliminable["how_is_capital_allocated_shadow"]["target_generation_mode"] == "DETERMINISTIC"


def test_legacy01_capital_allocation_question_is_deterministic(baseline_sp):
    """The QUESTION_INDEX question 'how-is-capital-allocated' is CLASS_A deterministic."""
    dirty = _dirty_baseline(baseline_sp, ["capital_allocation_outcomes", "economic_attribution"])
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_COMPANY)
    r = evaluate_answer_freshness(PRIMARY_COMPANY, "how-is-capital-allocated",
                                   baseline=dirty, current=current)
    assert r["result"] == WOULD_RECOMPUTE_DETERMINISTIC, (
        "how-is-capital-allocated must be WOULD_RECOMPUTE_DETERMINISTIC (not AI) when evidence changes"
    )


# ---------------------------------------------------------------------------
# LEGACY-02: Eliminable management-promises AI path classified deterministic
# ---------------------------------------------------------------------------
def test_legacy02_management_promises_shadow_classified_eliminable():
    registry_path = (
        Path(__file__).resolve().parent.parent
        / "governance" / "answer_dependency_registry.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    eliminable = registry.get("eliminable_ai_paths", {})
    assert "what_has_management_promised_shadow_sp_dp" in eliminable, (
        "Management promises shadow (sp/dp) must be registered as eliminable AI path"
    )
    assert eliminable["what_has_management_promised_shadow_sp_dp"]["ai_regeneration_required"] is False
    assert eliminable["what_has_management_promised_shadow_sp_dp"]["target_generation_mode"] == "DETERMINISTIC"


def test_legacy02_management_promises_question_is_deterministic(baseline_sp):
    """The QUESTION_INDEX question 'what-has-management-promised' is CLASS_A deterministic."""
    dirty = _dirty_baseline(baseline_sp, ["management_commitments"])
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_COMPANY)
    r = evaluate_answer_freshness(PRIMARY_COMPANY, "what-has-management-promised",
                                   baseline=dirty, current=current)
    assert r["result"] == WOULD_RECOMPUTE_DETERMINISTIC


# ---------------------------------------------------------------------------
# Scenario G: Identical evidence rebuilt — byte-different metadata → same digest
# ---------------------------------------------------------------------------
def test_scenario_g_metadata_only_rebuild_stays_clean(baseline_sp):
    """
    Simulate a builder rerun that changes only metadata (timestamps, generator_version).
    The semantic evidence is unchanged → digest must be identical → answer stays CLEAN.
    """
    from intelligence.evidence_fingerprints import compute_company_fingerprints
    current = compute_company_fingerprints(PRIMARY_COMPANY)
    # The baseline was computed from the same files as current → all CLEAN
    r = evaluate_answer_freshness(PRIMARY_COMPANY, "what-can-break-the-thesis",
                                   baseline=baseline_sp, current=current)
    assert r["result"] == CLEAN, (
        "After metadata-only rebuild (same semantic content), answer must remain CLEAN"
    )
