"""Regression tests for the Capital Allocation Outcome Tracker Gold layer."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from intelligence.capital_allocation.builder import (
    build_capital_allocation_outcome_tracker,
    _build_allocation_patterns,
    _build_financial_summary,
)
from intelligence.capital_allocation.classifier import (
    classify_allocation_type,
    is_material_allocation,
    _parse_amount_crore,
)
from intelligence.capital_allocation.resolver import (
    build_investor_interpretation,
    resolve_evidence_level,
    resolve_financial_link_status,
    resolve_return_status,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _raw_capex(
    *,
    name: str = "Organic Capex",
    amount: float = 500.0,
    operating_outcome: str = "",
    financial_outcome: str = "",
    causal_confidence: str = "low",
    execution_status: str = "deployed",
    deployment_periods: list | None = None,
) -> Dict[str, Any]:
    return {
        "allocation_category": "organic_capex",
        "allocation_name": name,
        "amount": amount,
        "operating_outcome": operating_outcome,
        "financial_outcome": financial_outcome,
        "causal_confidence": causal_confidence,
        "execution_status": execution_status,
        "deployment_periods": deployment_periods or ["fy22", "fy23"],
        "inferred_business_purpose": "Expand or maintain the asset base.",
        "investor_implication": "",
        "balance_sheet_outcome": "",
    }


def _raw_acquisition(
    *,
    name: str = "Acquisition of TargetCo",
    amount: float = 350.0,
    operating_outcome: str = "",
    financial_outcome: str = "",
    causal_confidence: str = "low",
) -> Dict[str, Any]:
    return {
        "allocation_category": "acquisition",
        "allocation_name": name,
        "category": "Acquisition",
        "value": name,
        "amount": amount,
        "operating_outcome": operating_outcome,
        "financial_outcome": financial_outcome,
        "causal_confidence": causal_confidence,
        "execution_status": "deployed",
        "deployment_periods": ["fy24"],
        "inferred_business_purpose": "Acquire capabilities in enterprise communications.",
        "investor_implication": "",
        "balance_sheet_outcome": "",
        "evidence_references": [{"evidence_id": "ev_fy24_acq_001", "source_artifact": "cap_timeline.json"}],
    }


def _raw_dividend(*, amount: float = 200.0) -> Dict[str, Any]:
    return {
        "allocation_category": "dividend",
        "allocation_name": "Dividend paid to shareholders",
        "amount": amount,
        "operating_outcome": "This is primarily a capital-structure or distribution decision rather than an operating investment.",
        "financial_outcome": "eps_basic grew.",
        "causal_confidence": "low",
        "execution_status": "deployed",
        "deployment_periods": ["fy22", "fy24"],
        "inferred_business_purpose": "Return excess capital to shareholders.",
        "investor_implication": "",
        "balance_sheet_outcome": "",
    }


def _raw_debt_repayment(*, operating_outcome: str = "", financial_outcome: str = "") -> Dict[str, Any]:
    return {
        "allocation_category": "debt_repayment",
        "allocation_name": "Debt repayment",
        "amount": 150.0,
        "operating_outcome": operating_outcome,
        "financial_outcome": financial_outcome,
        "causal_confidence": "medium",
        "execution_status": "deployed",
        "deployment_periods": ["fy23"],
        "inferred_business_purpose": "Reduce financial leverage.",
        "investor_implication": "",
        "balance_sheet_outcome": "",
    }


# ── T1: capex identified but no outcome → UNPROVEN ───────────────────────────

def test_capex_no_outcome_is_unproven():
    raw = _raw_capex(operating_outcome="", financial_outcome="")
    alloc_type = classify_allocation_type(raw)
    evidence_level = resolve_evidence_level(raw)
    return_status = resolve_return_status(raw, alloc_type, evidence_level)
    assert alloc_type == "ORGANIC_CAPEX"
    assert return_status == "UNPROVEN"


# ── T2: capex + commissioning → execution visible, return still UNPROVEN ──────

def test_capex_with_commissioning_evidence_is_still_unproven():
    raw = _raw_capex(
        operating_outcome="Plant commissioned and operational. Capacity is now deployed.",
        financial_outcome="",
    )
    alloc_type = classify_allocation_type(raw)
    evidence_level = resolve_evidence_level(raw)
    return_status = resolve_return_status(raw, alloc_type, evidence_level)
    # Operating evidence should be visible
    assert evidence_level in ("OPERATING_OUTCOME_VISIBLE", "EXECUTION_VISIBLE")
    # But return remains unproven without financial link
    assert return_status == "UNPROVEN"


# ── T3: operating traction without financial proof → EARLY_POSITIVE_SIGNAL ───

def test_operating_traction_without_financial_proof_is_early_positive():
    raw = _raw_capex(
        operating_outcome="Capacity utilisation reached 65%. Platform deployed and operational.",
        financial_outcome="Revenue grew 18% (+450 crore absolute change).",
        causal_confidence="medium",
    )
    alloc_type = classify_allocation_type(raw)
    evidence_level = resolve_evidence_level(raw)
    return_status = resolve_return_status(raw, alloc_type, evidence_level)
    assert evidence_level in ("FINANCIAL_OUTCOME_VISIBLE", "OPERATING_OUTCOME_VISIBLE")
    assert return_status in ("EARLY_POSITIVE_SIGNAL", "MIXED", "UNPROVEN")
    # Specifically: with medium causal confidence and revenue growth signal
    # it should NOT be PROVEN_POSITIVE (that requires high causal + return metrics)
    assert return_status != "PROVEN_POSITIVE"


# ── T4: attributable financial improvement → PROVEN_POSITIVE ─────────────────

def test_attributable_financial_improvement_is_proven_positive():
    raw = _raw_capex(
        operating_outcome="ROIC improved to 14% from 9% over 3 years after commissioning.",
        financial_outcome="Return on capital employed confirmed at 14%. Revenue contribution attributable to new assets.",
        causal_confidence="high",
    )
    alloc_type = classify_allocation_type(raw)
    evidence_level = resolve_evidence_level(raw)
    return_status = resolve_return_status(raw, alloc_type, evidence_level)
    assert evidence_level == "RETURN_EVIDENCE_VISIBLE"
    assert return_status == "PROVEN_POSITIVE"


# ── T5: acquisition completion ≠ acquisition success ─────────────────────────

def test_acquisition_completion_does_not_imply_success():
    raw = _raw_acquisition(
        operating_outcome="Acquisition completed. Integration underway.",
        financial_outcome="",
    )
    alloc_type = classify_allocation_type(raw)
    evidence_level = resolve_evidence_level(raw)
    return_status = resolve_return_status(raw, alloc_type, evidence_level)
    assert alloc_type == "ACQUISITION"
    # Completion is EXECUTION_VISIBLE or OPERATING_OUTCOME_VISIBLE
    assert evidence_level in ("EXECUTION_VISIBLE", "OPERATING_OUTCOME_VISIBLE")
    # Return must remain UNPROVEN without financial consequence evidence
    assert return_status == "UNPROVEN"


# ── T6: acquisition impairment → DESTRUCTIVE ─────────────────────────────────

def test_acquisition_with_impairment_is_destructive():
    raw = _raw_acquisition(
        operating_outcome="Integration completed.",
        financial_outcome="Goodwill impaired; write-off of ₹180 crore recorded in fy25.",
        causal_confidence="high",
    )
    alloc_type = classify_allocation_type(raw)
    evidence_level = resolve_evidence_level(raw)
    return_status = resolve_return_status(raw, alloc_type, evidence_level)
    assert return_status == "DESTRUCTIVE"


# ── T7: debt reduction + lower leverage → positive resilience outcome ─────────

def test_debt_repayment_with_leverage_reduction_is_early_positive():
    raw = _raw_debt_repayment(
        operating_outcome="Leverage fell. Debt reduced from ₹500 Cr to ₹200 Cr. Interest burden improved.",
        financial_outcome="Interest cost reduced by ₹30 Cr annually. Financial resilience improved.",
    )
    alloc_type = classify_allocation_type(raw)
    return_status = resolve_return_status(raw, alloc_type, resolve_evidence_level(raw))
    assert alloc_type == "DEBT_REPAYMENT"
    assert return_status == "EARLY_POSITIVE_SIGNAL"


# ── T8: dividend is NOT forced through capex-return logic ─────────────────────

def test_dividend_uses_capital_return_logic_not_roi():
    raw = _raw_dividend()
    alloc_type = classify_allocation_type(raw)
    evidence_level = resolve_evidence_level(raw)
    return_status = resolve_return_status(raw, alloc_type, evidence_level)
    assert alloc_type == "DIVIDEND"
    # Dividend must not be assessed as UNPROVEN, PROVEN_POSITIVE, or DESTRUCTIVE
    # It is NOT_APPLICABLE to reinvestment return logic
    assert return_status == "NOT_APPLICABLE"


# ── T9: revenue rising after capex does not imply causality ──────────────────

def test_revenue_after_capex_does_not_prove_causality():
    raw = _raw_capex(
        operating_outcome="",
        financial_outcome="Revenue grew 11% over the period.",
        causal_confidence="low",
    )
    alloc_type = classify_allocation_type(raw)
    evidence_level = resolve_evidence_level(raw)
    return_status = resolve_return_status(raw, alloc_type, evidence_level)
    fin_link = resolve_financial_link_status(raw, return_status)
    # Financial outcome IS visible (revenue number)
    assert evidence_level == "FINANCIAL_OUTCOME_VISIBLE"
    # But with low causal confidence, return is not PROVEN_POSITIVE
    assert return_status != "PROVEN_POSITIVE"
    # Financial link with low causal confidence is PARTIAL at best
    assert fin_link in ("PARTIAL", "UNPROVEN")


# ── T10: repeated allocation pattern requires multiple observations ────────────

def test_pattern_requires_multiple_allocations():
    single = [{
        "allocation_type": "ORGANIC_CAPEX",
        "return_status": "UNPROVEN",
        "evidence_level": "EXECUTION_VISIBLE",
        "capital_amount_crore": 200.0,
    }]
    patterns = _build_allocation_patterns(single, {})
    # Only 1 allocation → no pattern can be identified
    assert patterns == []


def test_pattern_triggers_with_multiple_allocations():
    two_unproven = [
        {"allocation_type": "ORGANIC_CAPEX", "return_status": "UNPROVEN",
         "evidence_level": "EXECUTION_VISIBLE", "capital_amount_crore": 200.0},
        {"allocation_type": "ACQUISITION", "return_status": "UNPROVEN",
         "evidence_level": "EXECUTION_VISIBLE", "capital_amount_crore": 350.0},
    ]
    patterns = _build_allocation_patterns(two_unproven, {"total_capex_crore": 200, "roce_available": False})
    pattern_ids = [p["pattern_id"] for p in patterns]
    assert "sustained_reinvestment_without_return_evidence" in pattern_ids


# ── T11: materiality excludes trivial uses ────────────────────────────────────

def test_trivial_allocations_are_excluded():
    trivial_records = [
        # EMD deposit — immaterial keyword
        {"allocation_category": "deposits", "category": "Deposits / Loans (unsecured)",
         "allocation_name": "EMD deposits paid", "value": "EMD deposits paid", "amount": 3.4,
         "inferred_business_purpose": ""},
        # RSU grant
        {"allocation_category": "equity", "category": "Equity issuance (employee stock grant)",
         "allocation_name": "RSU grants", "value": "RSU grants", "amount": "",
         "inferred_business_purpose": ""},
        # Collateral/pledging — not a capital outflow
        {"allocation_category": "other", "category": "Collateral / security for borrowings",
         "allocation_name": "Pledged assets as security", "value": "Pledged assets as security", "amount": 700.0,
         "inferred_business_purpose": ""},
    ]
    for raw in trivial_records:
        alloc_type = classify_allocation_type(raw)
        assert not is_material_allocation(raw, alloc_type), (
            f"Trivial record incorrectly passed materiality: {raw['allocation_name']}"
        )


# ── T12: evidence IDs preserved ──────────────────────────────────────────────

def test_evidence_ids_preserved_in_allocation_record():
    raw = _raw_acquisition(
        operating_outcome="Integration completed.",
        financial_outcome="Revenue contributed ₹120 Cr.",
    )
    alloc_type = classify_allocation_type(raw)
    from intelligence.capital_allocation.builder import _build_allocation_record, _load_sources
    # Build a minimal sources dict
    sources = {"promise_tracker": {}, "capacity_items": []}
    record = _build_allocation_record(raw, 1, sources, {})
    assert record is not None
    assert "ev_fy24_acq_001" in record["evidence_ids"]


# ── T13: chronology preserved ─────────────────────────────────────────────────

def test_deployment_periods_are_chronologically_ordered():
    raw = _raw_capex(deployment_periods=["fy24", "fy21", "fy22"])
    from intelligence.capital_allocation.builder import _deployment_periods
    periods = _deployment_periods(raw)
    assert periods == sorted(periods), "deployment_periods should be chronologically ordered"


# ── T14: no company/sector/year hardcoding ────────────────────────────────────

def test_builder_works_for_synthetic_company_without_hardcoding(tmp_path):
    # Build minimal source artifacts for a synthetic company
    memory = tmp_path / "synthetic_corp" / "company_memory"

    # Minimal capital_allocation_outcomes
    outcomes_dir = memory / "capital_allocation_outcomes"
    outcomes_dir.mkdir(parents=True)
    (outcomes_dir / "capital_allocation_outcomes.json").write_text(
        json.dumps({
            "allocations": [
                {
                    "allocation_id": "CAO-0001",
                    "allocation_category": "organic_capex",
                    "allocation_name": "Capital expenditure programme",
                    "amount": 450.0,
                    "deployment_periods": ["fy22", "fy23"],
                    "operating_outcome": "Facilities commissioned and operational.",
                    "financial_outcome": "Revenue grew 14% over the period.",
                    "causal_confidence": "low",
                    "execution_status": "deployed",
                    "inferred_business_purpose": "Expand manufacturing capacity.",
                    "investor_implication": "",
                    "balance_sheet_outcome": "",
                }
            ]
        }),
        encoding="utf-8",
    )

    # Minimal financials/financial_trends
    fin_dir = memory / "financials"
    fin_dir.mkdir(parents=True)
    (fin_dir / "financial_trends.json").write_text(
        json.dumps({
            "metric_series": {
                "capex": [{"year": "fy22", "value": -200.0}, {"year": "fy23", "value": -250.0}],
                "fcf": [{"year": "fy22", "value": 300.0}, {"year": "fy23", "value": 350.0}],
                "revenue": [{"year": "fy22", "value": 1000.0}, {"year": "fy23", "value": 1140.0}],
                "pat": [],
            },
            "ratio_series": {"roce": []},
        }),
        encoding="utf-8",
    )

    result = build_capital_allocation_outcome_tracker("synthetic_corp", companies_root=tmp_path)
    assert result["company_slug"] == "synthetic_corp"
    assert result["schema_version"] == "capital_allocation_gold.v1"
    assert len(result["material_allocations"]) >= 1

    alloc = result["material_allocations"][0]
    assert alloc["allocation_type"] in {"ORGANIC_CAPEX", "CAPACITY_EXPANSION"}
    assert alloc["return_status"] in {"UNPROVEN", "EARLY_POSITIVE_SIGNAL", "MIXED"}

    # No hardcoded company names in output
    artifact_text = json.dumps(result)
    for hardcoded in ("sun_pharma", "ujjivan", "tanla", "pharma", "banking", "telecom"):
        assert hardcoded not in artifact_text.lower(), f"Hardcoded term '{hardcoded}' found"
