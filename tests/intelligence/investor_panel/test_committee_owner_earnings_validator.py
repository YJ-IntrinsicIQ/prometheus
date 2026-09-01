"""
Regression tests for the committee validator owner-earnings limitation fix.

Root cause: when truth_detected=False (no financial_truth_pack.json), validate_committee_output
built owner_earnings_support={}.  Any owner-earnings limitation language in the committee view
then raised ValueError even though the text was a genuine data-quality statement.

Fix location: intelligence/investor_panel/committee_validator.py — validate_committee_output
now falls back to _owner_earnings_support_registry(included_analyst_payloads) when
truth_detected=False.  Limitation references backed by analyst discussion pass; positive
claims without analyst support still fail.

Test strategy: T1-T8 target _validate_financial_committee_view (the exact function that
raises); T9/T10 exercise the validate_committee_output integration path with a real payload.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from intelligence.investor_panel.committee_validator import (
    _owner_earnings_support_registry,
    _validate_financial_committee_view,
    classify_owner_earnings_reference,
    validate_committee_output,
)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_LIMITATION_TEXT = (
    "Derived FCF / owner-earnings estimate is available for the current usable year, "
    "but precision is limited by maintenance-versus-growth capex split and incomplete "
    "multi-year bridge history."
)
_POSITIVE_TEXT = "Owner earnings are strong and confirm the investment thesis."

_FCF_MISSING_SUPPORT = {
    "owner_earnings_limitation_supported": True,
    "owner_earnings_positive_claim_supported": False,
    "fcf_missing": True,
    "capex_missing": True,
    "payables_missing": False,
    "basis_unknown": False,
    "owner_earnings_status": "missing",
}

_EMPTY_SUPPORT: Dict[str, Any] = {}  # truth_detected=False, no analysts


def _minimal_fcv(*, missing_financial_data: List[str] | None = None) -> Dict[str, Any]:
    """Minimal financial_committee_view dict for targeted validator tests."""
    return {
        "financial_consensus": [],
        "financial_strengths": [],
        "financial_concerns": [],
        "financial_red_flags": [],
        "derived_not_explicitly_reported": [],
        "unreliable_financial_data": [],
        "invalid_or_quarantined_financial_data": [],
        "financials_used": False,
        "basis_used": "unknown",
        "missing_financial_data": missing_financial_data or [],
        "precise_missing_financial_data": [],
        "precision_limited_financial_data": [],
        "trend_durability_limits": [],
        "financial_interpretation_limits": [],
        "financial_disagreements": [],
        "investor_questions_from_financials": [],
        "investor_implications": "",
    }


def _validate_fcv(fcv: Dict[str, Any], support: Dict[str, Any]) -> Dict[str, Any]:
    # Allow fcf/capex terms so the limitation text (which references FCF and capex)
    # passes the strict-financial-terms check; owner_earnings is always exempt in that check.
    warnings: List[str] = []
    return _validate_financial_committee_view(
        fcv,
        allowed_terms={"fcf", "capex", "free cash flow"},
        owner_earnings_support=support,
        expected_financials_used=False,
        expected_basis_used="unknown",
        schema_warnings=warnings,
    )


# ---------------------------------------------------------------------------
# T1: valid owner-earnings limitation passes when analyst text supports it
# ---------------------------------------------------------------------------
def test_limitation_passes_when_analyst_text_supports():
    fcv = _minimal_fcv(missing_financial_data=[_LIMITATION_TEXT])
    result = _validate_fcv(fcv, _FCF_MISSING_SUPPORT)
    missing = result.get("missing_financial_data") or []
    assert any("owner" in m.lower() or "precision" in m.lower() for m in missing)


# ---------------------------------------------------------------------------
# T2: structured limitation form passes (limitation_supported=True via any path)
# ---------------------------------------------------------------------------
def test_structured_limitation_support_passes():
    text = "Owner earnings cannot be assessed: free cash flow is not disclosed."
    assert classify_owner_earnings_reference(text, path="test", financial_context={}) == "limitation"
    fcv = _minimal_fcv(missing_financial_data=[text])
    result = _validate_fcv(fcv, _FCF_MISSING_SUPPORT)
    missing = result.get("missing_financial_data") or []
    assert any("owner" in m.lower() for m in missing)


# ---------------------------------------------------------------------------
# T3: malformed input still fails (contract integrity)
# ---------------------------------------------------------------------------
def test_none_financial_committee_view_raises():
    with pytest.raises((ValueError, TypeError)):
        _validate_financial_committee_view(
            None,
            allowed_terms=set(),
            owner_earnings_support=_FCF_MISSING_SUPPORT,
            expected_financials_used=False,
            expected_basis_used="unknown",
            schema_warnings=[],
        )


# ---------------------------------------------------------------------------
# T4: limitation text is preserved in the validated output (not stripped)
# ---------------------------------------------------------------------------
def test_limitation_text_preserved_verbatim():
    fcv = _minimal_fcv(missing_financial_data=[_LIMITATION_TEXT])
    result = _validate_fcv(fcv, _FCF_MISSING_SUPPORT)
    combined = " ".join(result.get("missing_financial_data") or []).lower()
    assert "precision is limited" in combined


# ---------------------------------------------------------------------------
# T5: limitation not converted into economic negative or positive conclusion
# ---------------------------------------------------------------------------
def test_limitation_not_converted_to_economic_conclusion():
    fcv = _minimal_fcv(missing_financial_data=[_LIMITATION_TEXT])
    result = _validate_fcv(fcv, _FCF_MISSING_SUPPORT)
    combined = " ".join(result.get("missing_financial_data") or []).lower()
    for phrase in ("poor owner earnings", "strong owner earnings", "weak owner earnings"):
        assert phrase not in combined, f"Injected economic conclusion: {phrase!r}"


# ---------------------------------------------------------------------------
# T6: when no owner-earnings text at all, empty support dict does not fail
# ---------------------------------------------------------------------------
def test_no_owner_earnings_text_does_not_fail_with_empty_support():
    fcv = _minimal_fcv(missing_financial_data=["Capex evidence is incomplete."])
    result = _validate_fcv(fcv, _EMPTY_SUPPORT)
    assert result is not None


# ---------------------------------------------------------------------------
# T7: genuine positive claim without analyst support still raises
# ---------------------------------------------------------------------------
def test_positive_claim_without_support_raises():
    fcv = _minimal_fcv()
    fcv["financial_concerns"] = [_POSITIVE_TEXT]
    with pytest.raises(ValueError):
        _validate_fcv(fcv, _EMPTY_SUPPORT)


# ---------------------------------------------------------------------------
# T8: Tanla-style — analyst registry correctly detects limitation support
# ---------------------------------------------------------------------------
def test_tanla_style_analyst_registry_detects_limitation():
    analysts = [
        {
            "doctrine_id": a,
            "analyst_financial_truth_pack": {},
            "financial_assessment": {
                "basis_used": "standalone",
                "missing_financial_data": [
                    "Free cash flow is missing, so owner earnings cannot be assessed."
                ],
            },
            "financial_interpretation_limits": [
                "Margin-of-safety judgment limited because FCF is unavailable."
            ],
        }
        for a in ("graham", "buffett", "fisher", "munger", "lynch")
    ]
    registry = _owner_earnings_support_registry(analysts)
    assert registry["owner_earnings_limitation_supported"] is True
    assert registry["owner_earnings_positive_claim_supported"] is False
    # Now verify the fcv validation passes with this registry support
    support = {
        "owner_earnings_limitation_supported": registry["owner_earnings_limitation_supported"],
        "owner_earnings_positive_claim_supported": registry["owner_earnings_positive_claim_supported"],
        "fcf_missing": registry["fcf_missing"],
        "capex_missing": registry["capex_missing"],
        "payables_missing": registry.get("payables_missing", False),
        "basis_unknown": registry.get("basis_unknown", False),
        "owner_earnings_status": "missing",
    }
    fcv = _minimal_fcv(missing_financial_data=[_LIMITATION_TEXT])
    result = _validate_fcv(fcv, support)
    assert any("owner" in m.lower() or "precision" in m.lower()
               for m in (result.get("missing_financial_data") or []))


# ---------------------------------------------------------------------------
# T9: truth_detected=True path (sun_pharma style) remains unchanged
#     — uses real committee synthesis; just re-validates it
# ---------------------------------------------------------------------------
def test_sun_pharma_existing_committee_synthesis_still_validates():
    cs_path = Path("companies/sun_pharma/company_memory/investor_panel/committee_synthesis.json")
    if not cs_path.exists():
        pytest.skip("sun_pharma committee_synthesis.json not present")
    cs = json.loads(cs_path.read_text())
    # Load analyst payloads for sun_pharma
    panel_dir = Path("companies/sun_pharma/company_memory/investor_panel")
    analysts = []
    for a in ("graham", "buffett", "fisher", "munger", "lynch"):
        p = panel_dir / f"{a}_analysis.json"
        if p.exists():
            analysts.append(json.loads(p.read_text()))
    result = validate_committee_output(
        cs,
        company="sun_pharma",
        included_analysts=[a.get("doctrine_id", a.get("analyst", "")) for a in analysts],
        missing_analysts=cs.get("missing_analysts", []),
        excluded_analysts=cs.get("excluded_analysts", []),
        allowed_evidence_ids=cs.get("evidence_ids", []),
        analyst_uncertainties={},
        included_analyst_payloads=analysts,
        mode="final",
    )
    assert result.get("company") == "sun_pharma"


# ---------------------------------------------------------------------------
# T10: no company/year hardcoding — owner_earnings_support_registry
#      works with any analyst slug
# ---------------------------------------------------------------------------
def test_no_hardcoded_company_names_in_registry():
    for slug in ("acme_corp", "generic_firm", "unit_test_co"):
        analyst = {
            "doctrine_id": "graham",
            "analyst_financial_truth_pack": {},
            "financial_assessment": {
                "basis_used": "standalone",
                "missing_financial_data": [
                    "Free cash flow is missing; owner earnings cannot be assessed."
                ],
            },
            "financial_interpretation_limits": [],
        }
        registry = _owner_earnings_support_registry([analyst])
        assert registry["owner_earnings_limitation_supported"] is True, (
            f"Registry must not be company-specific; failed for {slug}"
        )
