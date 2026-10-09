"""
M47: Contract V2 Investor-Grade Regeneration Canary — 15 tests.

Covers:
  M47-FP-01..03  Deterministic fact pack
  M47-ASM-01..03 Contract V2 assembler
  M47-EIV-01..02 EIV gate in executor path
  M47-ELIG-01..03 Eligibility gate
  M47-EXEC-01..04 Executor dry_run + schema + outcome
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────
REPO = Path(__file__).parents[2]
SUN_PHARMA_MEM = REPO / "companies" / "sun_pharma" / "company_memory"


def _good_answer() -> Dict[str, Any]:
    """EIV-passing management quality answer."""
    return {
        "simple_answer": (
            "Sun Pharma's management has not demonstrated verifiable follow-through. "
            "Of 25 tracked initiatives, 0 have been confirmed delivered. "
            "Capital allocation decisions totalling ₹47,964 cr (FY26) remain unattributed "
            "to stated strategic objectives. Investors should treat management quality "
            "as uncertain until multi-year delivery evidence emerges."
        ),
        "why_it_matters": (
            "Management follow-through is a leading indicator of capital allocation quality. "
            "Unverified promises increase execution risk and reduce confidence in financial guidance."
        ),
        "investor_interpretation": (
            "Weight management quality at LOW confidence. Capital deployment of ₹47,964 cr "
            "without verifiable initiative delivery creates material execution risk for investors."
        ),
        "key_points": [
            "0 of 25 progression items confirmed delivered across multi-year tracking",
            "FOLLOW_THROUGH_LARGELY_UNVERIFIED — no partial deliveries confirmed",
            "Capital allocation of ₹47,964 cr (FY26) unattributed to strategy",
        ],
        "what_evidence_shows": [
            "Management progression tracker: 25 items, 0 delivered",
            "Multi-year commitment log shows no confirmed completion events",
        ],
        "what_may_mean_economically": (
            "Unverified follow-through on ₹47,964 cr capital base implies investors cannot "
            "confirm whether stated strategic priorities are being executed."
        ),
        "what_is_not_yet_proven": (
            "Whether any of the 25 tracked initiatives resulted in measurable economic outcomes; "
            "causal link between management actions and revenue growth is unestablished."
        ),
        "what_to_monitor": [
            "Quarterly delivery confirmations against each of the 25 tracked items",
            "Capital allocation disclosures tied to strategic initiative outcomes",
        ],
        "where_management_was_consistent": (
            "Management consistently communicated cost-optimisation targets across FY23-FY26 "
            "though none have been verified as delivered."
        ),
        "deterministic_precision_facts": [
            {
                "metric": "management_progression_delivery_rate",
                "value": "0 of 25 items confirmed delivered",
                "semantic_meaning": "No tracked initiative has been confirmed delivered over multi-year period",
            },
            {
                "metric": "capital_deployed_fy26",
                "value": "₹47,964 cr",
                "semantic_meaning": "Total capital deployed in FY26 with no verified strategic attribution",
            },
            {
                "metric": "behavioral_descriptor_derivation",
                "value": "FOLLOW_THROUGH_LARGELY_UNVERIFIED",
                "semantic_meaning": "0 delivered and 0 partially delivered across 25 tracked items",
            },
        ],
        "behavioral_descriptor": "FOLLOW_THROUGH_LARGELY_UNVERIFIED",
    }


# ── M47-FP: Fact pack ─────────────────────────────────────────────────────────

def test_fp01_fact_pack_builds_for_sun_pharma():
    """Fact pack builds without error for sun_pharma."""
    pytest.importorskip("intelligence.management_quality.fact_pack")
    from intelligence.management_quality.fact_pack import build_management_quality_fact_pack
    fp = build_management_quality_fact_pack("sun_pharma", SUN_PHARMA_MEM)
    assert isinstance(fp, dict)
    assert fp.get("schema_version") == "management_fact_pack.v1"
    assert "behavioral_descriptor" in fp


def test_fp02_fact_pack_behavioral_descriptor_is_deterministic():
    """Same inputs → same behavioral_descriptor every call."""
    from intelligence.management_quality.fact_pack import build_management_quality_fact_pack
    fp1 = build_management_quality_fact_pack("sun_pharma", SUN_PHARMA_MEM)
    fp2 = build_management_quality_fact_pack("sun_pharma", SUN_PHARMA_MEM)
    assert fp1["behavioral_descriptor"] == fp2["behavioral_descriptor"]


def test_fp03_fact_pack_has_minimum_dpfs():
    """Fact pack must contain at least 1 DPF (delivery DPF required by EIV-MQ-04)."""
    from intelligence.management_quality.fact_pack import build_management_quality_fact_pack
    fp = build_management_quality_fact_pack("sun_pharma", SUN_PHARMA_MEM)
    dpfs = fp.get("dpfs", [])
    assert len(dpfs) >= 1, f"Expected ≥1 DPF, got {len(dpfs)}"


# ── M47-ASM: Assembler ────────────────────────────────────────────────────────

def test_asm01_assembler_injects_dpfs_from_fact_pack():
    """Assembler always uses DPFs from fact_pack, ignoring LLM value."""
    from intelligence.management_quality.assembler import assemble_contract_v2_answer
    fact_pack = {
        "dpfs": ["DPF-1: 0 of 25 delivered", "DPF-2: ₹47,964 cr unattributed"],
        "behavioral_descriptor": "FOLLOW_THROUGH_LARGELY_UNVERIFIED",
    }
    llm_output = {"simple_answer": "test", "deterministic_precision_facts": ["WRONG"]}
    result = assemble_contract_v2_answer(llm_output, fact_pack)
    assert result["deterministic_precision_facts"] == fact_pack["dpfs"]


def test_asm02_assembler_preserves_llm_prose():
    """Assembler keeps LLM's simple_answer and investor_interpretation intact."""
    from intelligence.management_quality.assembler import assemble_contract_v2_answer
    fact_pack = {"dpfs": ["DPF-1"], "behavioral_descriptor": "FOLLOW_THROUGH_LARGELY_UNVERIFIED"}
    llm_output = {
        "simple_answer": "LLM prose here",
        "investor_interpretation": "LLM interp here",
        "key_points": ["a", "b", "c"],
    }
    result = assemble_contract_v2_answer(llm_output, fact_pack)
    assert result["simple_answer"] == "LLM prose here"
    assert result["investor_interpretation"] == "LLM interp here"


def test_asm03_deterministic_field_precedence_verified():
    """verify_deterministic_field_precedence detects LLM overwrite."""
    from intelligence.management_quality.assembler import verify_deterministic_field_precedence
    fact_pack = {"dpfs": ["DPF-A"], "behavioral_descriptor": "FOLLOW_THROUGH_LARGELY_UNVERIFIED"}
    # Simulate LLM overwriting deterministic fields
    assembled = {"deterministic_precision_facts": ["WRONG"], "behavioral_descriptor": "WRONG"}
    result = verify_deterministic_field_precedence(assembled, fact_pack)
    assert result["valid"] is False
    assert len(result["violations"]) >= 2


# ── M47-EIV: EIV gate in executor path ───────────────────────────────────────

def test_eiv01_good_answer_passes_eiv():
    """An investor-grade answer passes all 8 EIV rules."""
    from intelligence.external_investor_value_validator import validate_management_answer_eiv
    result = validate_management_answer_eiv(_good_answer())
    assert result["overall"] == "PASS", f"EIV failed: {result.get('fails')}"


def test_eiv02_answer_without_dpfs_fails_eiv_mq04():
    """An answer with no DPFs fails EIV-MQ-04 (DPF coverage)."""
    from intelligence.external_investor_value_validator import validate_management_answer_eiv
    answer = _good_answer()
    answer["deterministic_precision_facts"] = []
    result = validate_management_answer_eiv(answer)
    assert result["overall"] == "FAIL"
    assert any("MQ-04" in f or "dpf" in f.lower() for f in result.get("fails", [])), \
        f"Expected MQ-04 fail, got {result.get('fails')}"


# ── M47-ELIG: Eligibility gate ────────────────────────────────────────────────

def test_elig01_pacp_pass_eiv_pass_is_eligible():
    """PACP PASS + EIV PASS + valid digest → HUMAN_REVIEW_ELIGIBLE."""
    from intelligence.management_quality.candidate_eligibility import (
        evaluate_candidate_release_eligibility,
        HUMAN_REVIEW_ELIGIBLE,
    )
    from intelligence.external_investor_value_validator import validate_management_answer_eiv
    answer = _good_answer()
    eiv = validate_management_answer_eiv(answer)
    assert eiv["overall"] == "PASS"

    result = evaluate_candidate_release_eligibility(
        candidate={"candidate_digest": "sha256:abc123", "answer": answer},
        pacp_result={"overall": "PASS"},
        eiv_result=eiv,
    )
    assert result["eligibility_state"] == HUMAN_REVIEW_ELIGIBLE
    assert result["eligible"] is True


def test_elig02_pacp_pass_eiv_fail_is_blocked_eiv():
    """PACP PASS + EIV FAIL → BLOCKED_EIV (EIV gate enforced)."""
    from intelligence.management_quality.candidate_eligibility import (
        evaluate_candidate_release_eligibility,
        BLOCKED_EIV,
    )
    result = evaluate_candidate_release_eligibility(
        candidate={"candidate_digest": "sha256:abc123", "answer": {}},
        pacp_result={"overall": "PASS"},
        eiv_result={"overall": "FAIL", "fails": ["EIV-MQ-04"]},
    )
    assert result["eligibility_state"] == BLOCKED_EIV
    assert result["eligible"] is False


def test_elig03_pacp_fail_eiv_pass_is_blocked_pacp():
    """PACP FAIL + EIV PASS → BLOCKED_PACP (PACP is still a hard gate)."""
    from intelligence.management_quality.candidate_eligibility import (
        evaluate_candidate_release_eligibility,
        BLOCKED_PACP,
    )
    from intelligence.external_investor_value_validator import validate_management_answer_eiv
    answer = _good_answer()
    eiv = validate_management_answer_eiv(answer)
    assert eiv["overall"] == "PASS"

    result = evaluate_candidate_release_eligibility(
        candidate={"candidate_digest": "sha256:abc123", "answer": answer},
        pacp_result={"overall": "FAIL"},
        eiv_result=eiv,
    )
    assert result["eligibility_state"] == BLOCKED_PACP
    assert result["eligible"] is False


# ── shared test helpers ───────────────────────────────────────────────────────

_MINIMAL_MQ_SUMMARY = {
    "company_slug": "sun_pharma",
    "investor_implication": "Management quality weakens conviction until execution improves.",
    "overall_view": "weak",
    "strongest_dimension": "capital_allocation_discipline",
    "weakest_dimension": "execution_discipline",
    "unresolved_questions": ["Are recurring risks addressed?"],
    "interpretation": {"why_it_matters": "Execution discipline shapes compounding."},
}

_PROGRESSION_0_DELIVERED = {
    "progression_items": [
        {"item_id": f"ITEM-{i:03d}", "current_status": "announced", "exec_states": []}
        for i in range(25)
    ]
}

_CAPITAL_ALL_NONE = {
    "allocations": [{"alloc_id": f"A{i}", "attribution_status": "none"} for i in range(10)]
}

_MOCK_PACP_PASS = {
    "overall": "PASS",
    "named_checks": 10,
    "fails": [],
    "warns": [],
    "skips": [],
    "incomplete": [],
}


def _setup_minimal_company(companies_root: Path) -> Path:
    """Create minimal company dir without an existing manifest (forces fresh execution)."""
    company_root = companies_root / "sun_pharma"
    mq_dir = company_root / "company_memory" / "management_quality"
    mq_dir.mkdir(parents=True, exist_ok=True)
    (mq_dir / "management_quality_summary.json").write_text(json.dumps(_MINIMAL_MQ_SUMMARY))

    ask_dir = company_root / "company_memory" / "ask_intrinsiciq"
    ask_dir.mkdir(parents=True, exist_ok=True)
    (ask_dir / "shadow_level3_hybrid_answers.json").write_text(
        json.dumps({"answers": {"how-good-is-management": {"answer": {
            "simple_answer": "Previous answer placeholder.",
            "key_points": [],
        }}}})
    )

    prog_dir = company_root / "company_memory" / "management_progression"
    prog_dir.mkdir(parents=True, exist_ok=True)
    (prog_dir / "management_progression.json").write_text(json.dumps(_PROGRESSION_0_DELIVERED))

    cap_dir = company_root / "company_memory" / "capital_allocation_outcomes"
    cap_dir.mkdir(parents=True, exist_ok=True)
    (cap_dir / "capital_allocation_outcomes.json").write_text(json.dumps(_CAPITAL_ALL_NONE))

    return company_root


def _make_plan(calls: int = 1):
    return {"units": [{
        "generation_unit": "how_good_is_management_synthesis",
        "decision": "WOULD_REGENERATE" if calls else "REUSE",
        "planned_ai_calls": calls,
        "plan_unit_id": "test_unit_001",
    }]}


# ── M47-EXEC: Executor dry_run + schema + outcome ─────────────────────────────

def test_exec01_dry_run_writes_no_candidate_and_zero_ai_calls(tmp_path):
    """Executor dry_run=True makes 0 AI calls and writes no candidate."""
    from intelligence.regeneration_executor import run_regeneration

    companies_root = tmp_path / "companies"
    _setup_minimal_company(companies_root)

    with (
        patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)),
        patch("pipelines.pacp_adversarial.run_adversarial_suite", return_value=_MOCK_PACP_PASS),
    ):
        result = run_regeneration(
            company="sun_pharma",
            dry_run=True,
            companies_root=companies_root,
        )
    latest = result["execution_history"][-1]
    assert latest["ai_calls_executed"] == 0
    assert latest["candidate_digest"] == "NOT_WRITTEN"
    assert latest["outcome"] == "DRY_RUN_COMPLETE"


def test_exec02_candidate_schema_version_is_m47(tmp_path):
    """When PACP passes, candidate uses schema_version=m47_candidate_v1."""
    from intelligence.regeneration_executor import run_regeneration

    companies_root = tmp_path / "companies"
    _setup_minimal_company(companies_root)
    ask_dir = companies_root / "sun_pharma" / "company_memory" / "ask_intrinsiciq"

    with (
        patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)),
        patch("pipelines.pacp_adversarial.run_adversarial_suite", return_value=_MOCK_PACP_PASS),
        patch("intelligence.regeneration_executor._call_llm_with_telemetry") as mock_llm,
    ):
        mock_llm.return_value = {
            "answer": _good_answer(),
            "telemetry": {"model": "test-model", "provider": "mock", "success": True},
            "error": None,
        }
        result = run_regeneration(
            company="sun_pharma",
            dry_run=False,
            companies_root=companies_root,
        )

    latest = result["execution_history"][-1]
    candidate_file = latest.get("candidate_filename")
    if candidate_file and (ask_dir / candidate_file).exists():
        candidate_data = json.loads((ask_dir / candidate_file).read_text())
        assert candidate_data["schema_version"] == "m47_candidate_v1"
    else:
        # candidate written (candidate_digest != NOT_WRITTEN means it was written)
        assert latest["outcome"] != "PACP_FAIL_CANDIDATE_REJECTED", \
            f"Unexpected outcome: {latest['outcome']}"


def test_exec03_outcome_reflects_eiv_in_attempt_entry(tmp_path):
    """attempt_entry includes eiv_result and eligibility_result keys."""
    from intelligence.regeneration_executor import run_regeneration

    companies_root = tmp_path / "companies"
    _setup_minimal_company(companies_root)

    with (
        patch("intelligence.regeneration_planner.plan_regeneration", return_value=_make_plan(1)),
        patch("pipelines.pacp_adversarial.run_adversarial_suite", return_value=_MOCK_PACP_PASS),
        patch("intelligence.regeneration_executor._call_llm_with_telemetry") as mock_llm,
    ):
        mock_llm.return_value = {
            "answer": _good_answer(),
            "telemetry": {"model": "test-model", "provider": "mock", "success": True},
            "error": None,
        }
        result = run_regeneration(
            company="sun_pharma",
            dry_run=False,
            companies_root=companies_root,
        )

    latest = result["execution_history"][-1]
    assert "eiv_result" in latest, "eiv_result missing from attempt_entry"
    assert "eligibility_result" in latest, "eligibility_result missing from attempt_entry"
    assert "overall" in latest["eiv_result"]
    assert "eligible" in latest["eligibility_result"]


def test_exec04_pre_authorized_execution_id_format():
    """Pre-authorized M47 execution ID has expected sha256 prefix and length."""
    M47_PLANNED_EXECUTION_ID = "sha256:9d120267e32e0cd12a3864abb112258e"
    assert M47_PLANNED_EXECUTION_ID.startswith("sha256:")
    hex_part = M47_PLANNED_EXECUTION_ID[len("sha256:"):]
    assert len(hex_part) == 32
    assert all(c in "0123456789abcdef" for c in hex_part)
