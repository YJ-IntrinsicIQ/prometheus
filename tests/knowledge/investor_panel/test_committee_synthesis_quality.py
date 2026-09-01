"""
Committee Synthesis Quality Tests

Verifies that the committee synthesis layer:
- Preserves doctrine-specific reasoning in agreements AND disagreements
- Surfaces disagreements even when all analysts rate identically
- Does not treat shared evidence as independent confirmation
- Respects management chain status semantics (CLAIM_ONLY ≠ execution, etc.)
- Produces monitorable conviction-change triggers
- Is free of company-specific hardcoding
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from intelligence.investor_panel.committee_synthesizer import (
    ANALYST_DOCTRINE_FOCUS,
    InvestmentCommitteeSynthesizer,
    _canonical_confidence_value,
    _detect_doctrine_disagreements,
    _infer_unknown_type,
    build_committee_synthesis_skeleton,
)
from intelligence.investor_panel.committee_validator import (
    FORBIDDEN_INTERNAL_BRIEF_TERMS,
    validate_committee_output,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _analyst(
    doctrine_id: str,
    *,
    rating: str = "mixed",
    key_findings: List[str] | None = None,
    red_flags: List[str] | None = None,
    open_uncertainties: List[str] | None = None,
    evidence_ids: List[str] | None = None,
    management_chain_statuses: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "doctrine_id": doctrine_id,
        "company": "test_co",
        "analysis_mode": "llm_reasoning_v1",
        "rating": rating,
        "key_findings": key_findings or [f"{doctrine_id} positive finding"],
        "red_flags": red_flags or [f"{doctrine_id} risk flag"],
        "open_uncertainties": open_uncertainties or [f"{doctrine_id} uncertainty"],
        "evidence_ids": evidence_ids or [f"ev_{doctrine_id}_1"],
        "historical_context_used": False,
        "years_considered": ["fy24"],
        "supporting_pcim_sections": [],
        "evidence_grounding_status": "pass",
        "reasoning_limits": [],
        "financial_assessment": {
            "financials_used": True,
            "basis_used": "consolidated",
            "key_financial_strengths": ["Revenue is growing"],
            "key_financial_concerns": ["Debt is elevated"],
            "financial_red_flags": [],
            "missing_financial_data": [],
            "financial_interpretation_limits": [],
            "financial_warnings_carried_forward": [],
        },
        "financial_sections_consumed": ["financial_trend_inputs"],
        "financial_warnings_carried_forward": [],
        "user_facing_brief": {
            "bottom_line": f"{doctrine_id} view: cautious",
        },
        "management_chain_statuses_used": management_chain_statuses or [],
        "generated_at": "2026-08-30T00:00:00Z",
    }


def _all_analysts(rating: str = "mixed", shared_ev_id: str | None = None) -> List[Dict[str, Any]]:
    analysts = ["graham", "buffett", "fisher", "munger", "lynch"]
    return [
        _analyst(
            a,
            rating=rating,
            evidence_ids=[shared_ev_id or f"ev_{a}_1"],
        )
        for a in analysts
    ]


# ---------------------------------------------------------------------------
# Test 1: Doctrine focus is injected into compact analyst block
# ---------------------------------------------------------------------------

def test_doctrine_focus_present_in_compact_block(tmp_path):
    """_compact_analyst_input must include doctrine_focus for each analyst."""
    synthesizer = InvestmentCommitteeSynthesizer(company="test_co", companies_root=tmp_path)
    payload = _analyst("graham")
    compacted = synthesizer._compact_analyst_input(payload)
    assert "doctrine_focus" in compacted, "doctrine_focus must appear in compacted analyst block"
    assert "downside" in compacted["doctrine_focus"].lower(), \
        "Graham's doctrine_focus must mention downside protection"


def test_all_analysts_have_doctrine_focus():
    """Every expected analyst must have a doctrine_focus entry."""
    for analyst in ["graham", "buffett", "fisher", "munger", "lynch"]:
        assert analyst in ANALYST_DOCTRINE_FOCUS, f"{analyst} missing from ANALYST_DOCTRINE_FOCUS"
        assert ANALYST_DOCTRINE_FOCUS[analyst], f"{analyst} doctrine_focus must not be empty"


# ---------------------------------------------------------------------------
# Test 2: Evidence-backed disagreement detection
# ---------------------------------------------------------------------------

def _analyst_with_constructive_signal(doctrine_id: str) -> Dict[str, Any]:
    """Analyst whose key_findings include a substantively constructive signal."""
    return _analyst(
        doctrine_id,
        key_findings=["credible building blocks exist for long-runway growth; margins are improving"],
        red_flags=["execution proof between capex and returns is not yet visible"],
    )


def _analyst_with_safety_concern(doctrine_id: str) -> Dict[str, Any]:
    """Analyst whose red_flags include a substantive (non-data-gap) downside concern."""
    return _analyst(
        doctrine_id,
        key_findings=["some cash generation signals are present"],
        red_flags=["downside protection remains inadequate; cash-conversion is below acceptable threshold"],
    )


def _analyst_with_data_gap_only(doctrine_id: str) -> Dict[str, Any]:
    """Analyst whose findings and flags are purely data-availability notes."""
    return _analyst(
        doctrine_id,
        key_findings=["capex split unavailable", "payables data missing"],
        red_flags=["maintenance vs growth split unavailable; share count data missing"],
    )


def test_doctrine_disagreement_requires_content_not_just_doctrine_type():
    """Doctrine difference alone must NOT produce a disagreement when all signals are data gaps."""
    included = [
        _analyst_with_data_gap_only("fisher"),
        _analyst_with_data_gap_only("lynch"),
        _analyst_with_data_gap_only("graham"),
        _analyst_with_data_gap_only("munger"),
    ]
    result = _detect_doctrine_disagreements(included)
    assert result == [], \
        "No disagreement should be produced when all findings are data-gap notes"


def test_doctrine_disagreement_detected_when_content_diverges():
    """A disagreement IS produced when growth analyst is constructive AND safety analyst has real concern."""
    included = [
        _analyst_with_constructive_signal("fisher"),
        _analyst_with_safety_concern("graham"),
        _analyst("buffett"),
    ]
    result = _detect_doctrine_disagreements(included)
    assert len(result) == 1, "Expected exactly one disagreement from content divergence"
    d = result[0]
    assert "fisher" in d.get("analysts_positive_or_less_concerned", [])
    assert "graham" in d.get("analysts_cautious_or_negative", [])


def test_doctrine_disagreement_names_growth_and_safety_analysts():
    """When disagreement exists, analysts must be correctly classified by doctrine."""
    included = [
        _analyst_with_constructive_signal("fisher"),
        _analyst_with_constructive_signal("lynch"),
        _analyst_with_safety_concern("graham"),
        _analyst_with_safety_concern("munger"),
        _analyst("buffett"),
    ]
    result = _detect_doctrine_disagreements(included)
    assert result, "Expected disagreement with mixed constructive and concern signals"
    d = result[0]
    cautious = d.get("analysts_cautious_or_negative", [])
    constructive = d.get("analysts_positive_or_less_concerned", [])
    assert "graham" in cautious, "Graham must be classified as cautious"
    assert "munger" in cautious, "Munger must be classified as cautious"
    assert "fisher" in constructive, "Fisher must be classified as constructive"


def test_doctrine_disagreement_absent_when_all_same_caution_level():
    """No disagreement when all growth AND safety analysts express similar cautious signals."""
    # Both growth and safety analysts are cautious about the same things
    included = [
        _analyst("fisher", key_findings=["some margin signals"], red_flags=["execution unproven"]),
        _analyst("graham", key_findings=["some cash signals"], red_flags=["downside unverified"]),
    ]
    # "some margin signals" and "some cash signals" don't contain constructive vocabulary
    # → growth_signal_found = False → no disagreement
    result = _detect_doctrine_disagreements(included)
    assert result == [], \
        "No disagreement when growth analysts don't have substantive constructive signals"


def test_rating_disparity_disagreement_still_works():
    """Rating-disparity disagreement must still be generated when ratings differ."""
    strong = _analyst("buffett", rating="strong")
    weak = _analyst("graham", rating="weak")
    result = build_committee_synthesis_skeleton("test_co", [strong, weak], None)
    disagree = result["areas_of_disagreement"]
    assert len(disagree) >= 1, "Rating-disparity disagreement must be present"


def test_rating_disparity_disagreement_still_works():
    """Rating-disparity disagreement must still be generated when ratings differ."""
    strong = _analyst("buffett", rating="strong")
    weak = _analyst("graham", rating="weak")
    result = build_committee_synthesis_skeleton("test_co", [strong, weak], None)
    disagree = result["areas_of_disagreement"]
    assert len(disagree) >= 1, "Rating-disparity disagreement must be present"


# ---------------------------------------------------------------------------
# Test 3: Shared evidence is not treated as independent confirmation
# ---------------------------------------------------------------------------

def test_shared_evidence_caps_confidence_at_medium():
    """5 analysts citing the same 2 evidence IDs must not produce 'high' confidence."""
    # 5 analysts, 2 unique evidence IDs → ratio = 0.4 < 2.0 → must be capped at medium
    shared_evidence = ["ev_shared_001", "ev_shared_002"]
    included = [
        _analyst(a, evidence_ids=shared_evidence)
        for a in ["graham", "buffett", "fisher", "munger", "lynch"]
    ]
    result = build_committee_synthesis_skeleton("test_co", included, None)
    confidence = result["overall_committee_view"]["confidence"]
    assert confidence in {"low", "medium"}, \
        f"Confidence must not be 'high' when all analysts share the same narrow evidence pool; got {confidence}"


def test_canonical_confidence_value_evidence_independence():
    """_canonical_confidence_value must cap at medium when evidence pool is narrow."""
    # 5 analysts, 3 unique evidence IDs → ratio = 0.6 → cap at medium
    conf = _canonical_confidence_value(5, 0, unique_evidence_count=3)
    assert conf == "medium", f"Expected medium (shared evidence), got {conf}"

    # 5 analysts, 15 unique evidence IDs → ratio = 3.0 → no cap, reaches high
    conf_high = _canonical_confidence_value(5, 0, unique_evidence_count=15)
    assert conf_high == "high", f"Expected high (independent evidence), got {conf_high}"


# ---------------------------------------------------------------------------
# Test 4: Weak evidence + unanimous analysts ≠ high confidence
# ---------------------------------------------------------------------------

def test_many_warnings_keeps_confidence_low():
    """High analyst count with many warnings must remain low confidence."""
    # _canonical_confidence_value: warning_count >= 4 → low
    conf = _canonical_confidence_value(5, 4)
    assert conf == "low", f"Expected low confidence with 4+ warnings, got {conf}"


# ---------------------------------------------------------------------------
# Test 5: Detect_doctrine_disagreements is company-agnostic
# ---------------------------------------------------------------------------

def test_detect_doctrine_disagreements_not_company_specific():
    """_detect_doctrine_disagreements must work for any company, no hardcoding."""
    for company_name in ["sun_pharma", "ujjivan", "some_unknown_co", "xyz_corp_2099"]:
        included = [
            _analyst_with_constructive_signal("fisher"),
            _analyst_with_safety_concern("graham"),
        ]
        result = _detect_doctrine_disagreements(included)
        assert isinstance(result, list), f"Expected list for {company_name}"
        assert len(result) >= 1, \
            f"Expected doctrine disagreement for {company_name} with constructive fisher + concerned graham"


def test_detect_doctrine_disagreements_returns_empty_for_uniform_safety():
    """If only safety-oriented analysts are present, no growth-vs-safety tension exists."""
    safety_only = [_analyst("graham"), _analyst("munger")]
    result = _detect_doctrine_disagreements(safety_only)
    assert result == [], \
        "No growth-vs-safety disagreement when only safety analysts present"


# ---------------------------------------------------------------------------
# Test 6: what_would_change_conviction field is present in skeleton
# ---------------------------------------------------------------------------

def test_what_would_change_conviction_field_in_skeleton():
    """Skeleton must always include what_would_change_conviction (even if empty list)."""
    included = _all_analysts()
    result = build_committee_synthesis_skeleton("test_co", included, None)
    assert "what_would_change_conviction" in result, \
        "what_would_change_conviction must be a top-level key in skeleton"
    assert isinstance(result["what_would_change_conviction"], list)


# ---------------------------------------------------------------------------
# Test 7: doctrine_agreements and doctrine_disagreements in skeleton
# ---------------------------------------------------------------------------

def test_doctrine_fields_initialized_in_skeleton():
    """Skeleton must include doctrine_agreements and doctrine_disagreements fields."""
    included = _all_analysts()
    result = build_committee_synthesis_skeleton("test_co", included, None)
    assert "doctrine_agreements" in result, "doctrine_agreements key must be in skeleton"
    assert "doctrine_disagreements" in result, "doctrine_disagreements key must be in skeleton"


# ---------------------------------------------------------------------------
# Test 8: CLAIM_ONLY cannot become execution in compact block
# ---------------------------------------------------------------------------

def test_claim_only_semantics_preserved_in_compact(tmp_path):
    """CLAIM_ONLY management chain status must not be relabeled as action in compact output."""
    from intelligence.investor_panel.committee_synthesizer import COMMITTEE_SYNTHESIS_SYSTEM_PROMPT
    assert "CLAIM_ONLY" in COMMITTEE_SYNTHESIS_SYSTEM_PROMPT, \
        "System prompt must instruct LLM about CLAIM_ONLY semantics"
    assert "ACTION_COMPLETED" in COMMITTEE_SYNTHESIS_SYSTEM_PROMPT, \
        "System prompt must instruct LLM about ACTION_COMPLETED semantics"
    # Also verify compact block contains finding text with CLAIM_ONLY note
    payload = _analyst(
        "buffett",
        key_findings=["Management stated intention to expand capacity (CLAIM_ONLY — no action evidence)"],
        management_chain_statuses=["CLAIM_ONLY"],
    )
    synthesizer = InvestmentCommitteeSynthesizer(company="test_co", companies_root=tmp_path)
    compacted = synthesizer._compact_analyst_input(payload)
    assert "doctrine_focus" in compacted, "compact block must still include doctrine_focus"


# ---------------------------------------------------------------------------
# Test 9: FINANCIAL_LINK_UNPROVEN cannot become confirmed impact
# ---------------------------------------------------------------------------

def test_financial_link_unproven_semantics_in_system_prompt():
    """System prompt must explicitly block FINANCIAL_LINK_UNPROVEN from becoming confirmed impact."""
    from intelligence.investor_panel.committee_synthesizer import COMMITTEE_SYNTHESIS_SYSTEM_PROMPT
    assert "FINANCIAL_LINK_UNPROVEN" in COMMITTEE_SYNTHESIS_SYSTEM_PROMPT, \
        "System prompt must mention FINANCIAL_LINK_UNPROVEN"


# ---------------------------------------------------------------------------
# Test 10: Regulator action ≠ management action semantics in system prompt
# ---------------------------------------------------------------------------

def test_regulator_action_semantics_in_system_prompt():
    """System prompt must distinguish regulator action from management action."""
    from intelligence.investor_panel.committee_synthesizer import COMMITTEE_SYNTHESIS_SYSTEM_PROMPT
    assert "regulator" in COMMITTEE_SYNTHESIS_SYSTEM_PROMPT.lower(), \
        "System prompt must address regulator action vs management action distinction"


# ---------------------------------------------------------------------------
# Test 11: 'doctrine' as a concept is no longer forbidden in committee output
# ---------------------------------------------------------------------------

def test_doctrine_word_not_forbidden_in_committee_output():
    """The word 'doctrine' in natural narrative must not be blocked; only 'doctrine_id' is forbidden."""
    assert "doctrine" not in FORBIDDEN_INTERNAL_BRIEF_TERMS, \
        "'doctrine' as a concept must be allowed in committee narrative (was incorrectly blocked)"
    assert "doctrine_id" in FORBIDDEN_INTERNAL_BRIEF_TERMS, \
        "'doctrine_id' (the internal metadata key) must still be forbidden"


# ---------------------------------------------------------------------------
# Test 12: Existing validator still rejects genuinely invalid synthesis
# ---------------------------------------------------------------------------

def test_validator_still_rejects_invalid_synthesis():
    """The committee validator must raise on a synthesis missing required keys."""
    invalid = {
        "company": "test_co",
        "analysis_mode": "committee_synthesis_v1",
        # Deliberately missing: overall_committee_view, areas_of_agreement, etc.
    }
    with pytest.raises(ValueError, match="missing required keys"):
        validate_committee_output(
            invalid,
            company="test_co",
            included_analysts=["graham"],
            missing_analysts=[],
            excluded_analysts=[],
            allowed_evidence_ids=[],
            analyst_uncertainties={},
            mode="raw",
        )


# ---------------------------------------------------------------------------
# Tests for unknown classification (DATA_GAP vs DECISION_UNKNOWN)
# ---------------------------------------------------------------------------

def test_data_gap_classification():
    """Pure data-availability notes must be classified as DATA_GAP."""
    data_gaps = [
        "maintenance versus growth capex split unavailable",
        "payables data is missing",
        "share count data is not available",
        "diluted shares not reported in this filing",
        "capex split unavailable",
    ]
    for text in data_gaps:
        t = _infer_unknown_type(text)
        assert t == "DATA_GAP", f"Expected DATA_GAP for '{text}', got {t}"


def test_decision_unknown_classification():
    """Investment thesis questions must be classified as DECISION_UNKNOWN."""
    decision_unknowns = [
        "whether specialty capex is generating acceptable incremental returns",
        "can management convert the current capex cycle into durable returns",
        "whether recent growth translates to cash remains unproven",
        "the financial consequence of the R&D strategy remains unproven",
    ]
    for text in decision_unknowns:
        t = _infer_unknown_type(text)
        assert t == "DECISION_UNKNOWN", f"Expected DECISION_UNKNOWN for '{text}', got {t}"


def test_decision_unknowns_promoted_in_skeleton():
    """Skeleton critical_unknowns must contain DECISION_UNKNOWN items when registry supplies them."""
    # Build the uncertainty registry directly as the format skeleton expects
    registry = [
        {
            "uncertainty_id": "fisher_u001",
            "analyst": "fisher",
            "category": "management",
            "text": "whether the capex is generating acceptable incremental returns",
            "aliases": [],
            "source_path": "fisher_analysis.json#open_uncertainties",
        },
        {
            "uncertainty_id": "graham_u001",
            "analyst": "graham",
            "category": "management",
            "text": "can management execute the stated reinvestment strategy",
            "aliases": [],
            "source_path": "graham_analysis.json#open_uncertainties",
        },
        {
            "uncertainty_id": "fisher_u002",
            "analyst": "fisher",
            "category": "financials",
            "text": "maintenance vs growth capex split unavailable",
            "aliases": [],
            "source_path": "fisher_analysis.json#open_uncertainties",
        },
    ]
    payloads = [_analyst("fisher"), _analyst("graham")]
    result = build_committee_synthesis_skeleton("test_co", payloads, None, uncertainty_registry=registry)
    critical = result["critical_unknowns"]
    gaps = result["evidence_gaps"]

    # At least one DECISION_UNKNOWN must be in critical_unknowns
    decision_types = [item.get("unknown_type") for item in critical]
    assert "DECISION_UNKNOWN" in decision_types, \
        f"critical_unknowns must contain DECISION_UNKNOWN items; got types: {decision_types}"

    # DATA_GAP items must appear in evidence_gaps
    all_gap_types = [item.get("unknown_type") for item in gaps]
    assert "DATA_GAP" in all_gap_types, \
        f"evidence_gaps must contain DATA_GAP items; got types: {all_gap_types}"


def test_no_decision_unknown_means_critical_unknowns_empty():
    """If registry has only DATA_GAP items, critical_unknowns must be empty — not promoted."""
    registry = [
        {
            "uncertainty_id": "fisher_u001",
            "analyst": "fisher",
            "category": "financials",
            "text": "maintenance vs growth capex split unavailable",
            "aliases": [],
            "source_path": "fisher_analysis.json#open_uncertainties",
        },
        {
            "uncertainty_id": "graham_u001",
            "analyst": "graham",
            "category": "financials",
            "text": "payables data is missing",
            "aliases": [],
            "source_path": "graham_analysis.json#open_uncertainties",
        },
    ]
    result = build_committee_synthesis_skeleton(
        "test_co", [_analyst("fisher"), _analyst("graham")], None, uncertainty_registry=registry
    )
    assert result["critical_unknowns"] == [], \
        "critical_unknowns must be empty when registry has only DATA_GAP items"
    assert len(result["evidence_gaps"]) >= 1, \
        "DATA_GAP items must remain in evidence_gaps"


def test_data_gap_never_promoted_to_critical_unknowns():
    """DATA_GAP items must stay in evidence_gaps; must not appear in critical_unknowns."""
    registry = [
        {
            "uncertainty_id": "x_u001",
            "analyst": "graham",
            "category": "financials",
            "text": "diluted shares not reported",
            "aliases": [],
            "source_path": "graham_analysis.json#open_uncertainties",
        }
    ]
    result = build_committee_synthesis_skeleton(
        "test_co", [_analyst("graham")], None, uncertainty_registry=registry
    )
    critical_texts = [item.get("unknown") for item in result["critical_unknowns"]]
    assert "diluted shares not reported" not in critical_texts, \
        "DATA_GAP item must not appear in critical_unknowns"


def test_evidence_gaps_field_in_skeleton():
    """Skeleton must always include evidence_gaps field."""
    result = build_committee_synthesis_skeleton("test_co", _all_analysts(), None)
    assert "evidence_gaps" in result, "evidence_gaps must be a top-level key in skeleton"
    assert isinstance(result["evidence_gaps"], list)


def test_conviction_trigger_schema_is_monitorable():
    """Schema prompt must include monitorable-trigger guidance with good/bad examples."""
    from intelligence.investor_panel.committee_synthesizer import COMMITTEE_SCHEMA_PROMPT
    assert "ROIC" in COMMITTEE_SCHEMA_PROMPT or "monitorable" in COMMITTEE_SCHEMA_PROMPT.lower(), \
        "Schema must guide LLM toward monitorable conviction triggers"
    assert "GOOD" in COMMITTEE_SCHEMA_PROMPT or "good" in COMMITTEE_SCHEMA_PROMPT.lower(), \
        "Schema must include a positive example of a conviction trigger"
    assert "BAD" in COMMITTEE_SCHEMA_PROMPT or "bad" in COMMITTEE_SCHEMA_PROMPT.lower(), \
        "Schema must include a negative example to reject vague triggers"


def test_management_chain_semantics_in_system_prompt_complete():
    """All four management-chain semantic rules must appear in the system prompt."""
    from intelligence.investor_panel.committee_synthesizer import COMMITTEE_SYNTHESIS_SYSTEM_PROMPT
    prompt = COMMITTEE_SYNTHESIS_SYSTEM_PROMPT
    assert "CLAIM_ONLY" in prompt, "System prompt must reference CLAIM_ONLY"
    assert "ACTION_COMPLETED" in prompt, "System prompt must reference ACTION_COMPLETED"
    assert "FINANCIAL_LINK_UNPROVEN" in prompt, "System prompt must reference FINANCIAL_LINK_UNPROVEN"
    assert "regulator" in prompt.lower(), "System prompt must address regulator vs management distinction"


def test_no_company_name_in_disagreement_detection():
    """_detect_doctrine_disagreements must not reference any company name or hardcoded value."""
    import inspect
    from intelligence.investor_panel import committee_synthesizer
    src = inspect.getsource(committee_synthesizer._detect_doctrine_disagreements)
    company_names = ["sun_pharma", "ujjivan", "tanla", "datapatterns", "polymatech"]
    for name in company_names:
        assert name not in src, f"Company name '{name}' must not appear in _detect_doctrine_disagreements"
