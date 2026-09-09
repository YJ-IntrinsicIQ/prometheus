"""
Committee Brief Provenance Compatibility Tests
ENG-086: Repair validate_committee_brief_source() so structured canonical provenance
         containing evidence_id is allowed internally while internal terms must not
         leak into user-facing prose.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Helpers to build minimal valid committee synthesis payloads
# ---------------------------------------------------------------------------

def _minimal_synthesis(**overrides: Any) -> Dict[str, Any]:
    """Return the smallest committee_synthesis.json that passes validation."""
    base: Dict[str, Any] = {
        "company": "test_co",
        "overall_committee_view": {
            "summary": "The committee sees a constructive business story.",
            "confidence": "medium",
            "dominant_tension": "Growth versus capital efficiency.",
        },
        "financial_committee_view": {
            "financials_used": True,
            "basis_used": "standalone",
            "financial_consensus": [],
            "financial_strengths": [],
            "financial_concerns": [],
            "financial_disagreements": [],
            "missing_financial_data": [],
            "financial_red_flags": [],
            "financial_interpretation_limits": [],
            "investor_questions_from_financials": [],
        },
        "areas_of_agreement": [],
        "areas_of_disagreement": [],
        "strongest_positive_signals": [],
        "most_important_risks": [],
        "critical_unknowns": [],
        "investigation_questions": [],
        "synthesis_limits": [],
        "evidence_quality_notes": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Import the function under test
# ---------------------------------------------------------------------------

from intelligence.investor_panel.committee_brief_renderer import validate_committee_brief_source


# ---------------------------------------------------------------------------
# P1: Structured evidence_id as a key — must be ACCEPTED
# ---------------------------------------------------------------------------

class TestStructuredProvenanceAccepted:
    """Structured provenance with evidence_id as a dict key must pass validation."""

    def test_evidence_id_as_structured_key_accepted(self):
        """P1-1: evidence_id as a KEY in a structured provenance object is allowed."""
        synthesis = _minimal_synthesis(
            areas_of_agreement=[
                {
                    "theme": "Strong revenue growth",
                    "summary": "Analysts agree on consistent top-line momentum.",
                    "source_analysts": ["graham", "buffett"],
                    "evidence_ids": ["ev_fy26_revenue_growth"],
                }
            ]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None

    def test_nested_evidence_id_as_structured_key_accepted(self):
        """P1-2: Nested structured object with evidence_id as a key is allowed."""
        synthesis = _minimal_synthesis(
            strongest_positive_signals=[
                {
                    "signal": "Margin expansion",
                    "summary": "Margins have improved over three consecutive years.",
                    "supported_by": ["Graham"],
                    "evidence_ids": ["ev_fy26_margin_001"],
                }
            ]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None

    def test_evidence_ids_list_in_structured_field_accepted(self):
        """P1-3: Multiple evidence_ids in a list within a structured field are allowed."""
        synthesis = _minimal_synthesis(
            most_important_risks=[
                {
                    "risk": "Regulatory concentration",
                    "summary": "Heavy dependence on one regulator creates binary event risk.",
                    "severity": "high",
                    "raised_by": ["Munger"],
                    "evidence_ids": ["ev_fy26_reg_001", "ev_fy25_reg_002"],
                }
            ]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None

    def test_analyst_exclusion_message_with_raw_diagnostic_accepted(self):
        """P1-4: Analyst exclusion message in evidence_quality_notes with embedded diagnostic
        data (containing 'evidence_id' as a substring) is accepted after phrase-cleaning."""
        synthesis = _minimal_synthesis(
            evidence_quality_notes=[
                "graham contributed strong analysis.",
                "buffett was excluded because final analyst evidence IDs are invalid: "
                "[{'path': '$.evidence_ids', 'invalid_id': 'ev_some_artifact', "
                "'reason': 'unknown_evidence_id'}].",
            ]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None

    def test_multiple_analyst_exclusions_accepted(self):
        """P1-5: Multiple analyst exclusion messages with evidence_id diagnostic data are accepted."""
        synthesis = _minimal_synthesis(
            evidence_quality_notes=[
                "buffett was excluded because final analyst evidence IDs are invalid: "
                "[{'path': '$.evidence_ids', 'invalid_id': 'ev_cap_alloc', 'reason': 'unknown_evidence_id'}].",
                "munger was excluded because final analyst evidence IDs are invalid: "
                "[{'path': '$.evidence_ids', 'invalid_id': 'ev_fy24_mgmt', 'reason': 'unknown_evidence_id'}].",
                "lynch was excluded because final analyst evidence IDs are invalid: "
                "[{'path': '$.evidence_ids', 'invalid_id': 'ev_fy26_wc', 'reason': 'unknown_evidence_id'}].",
            ]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None


# ---------------------------------------------------------------------------
# P2: evidence_id in visible prose — must be REJECTED
# ---------------------------------------------------------------------------

class TestInternalTermInProseRejected:
    """Internal implementation terms that appear literally in user-facing prose must fail."""

    def test_evidence_id_in_summary_prose_rejected(self):
        """P2-1: 'evidence_id' appearing literally in a user-facing summary string is rejected."""
        synthesis = _minimal_synthesis()
        synthesis["overall_committee_view"]["summary"] = (
            "The analysis is supported by evidence_id ev-123."
        )
        with pytest.raises(ValueError, match="evidence_id"):
            validate_committee_brief_source(synthesis)

    def test_source_chunk_in_prose_rejected(self):
        """P2-2: 'source_chunk' appearing in user-facing prose is rejected."""
        synthesis = _minimal_synthesis(
            synthesis_limits=["The source_chunk context was too limited to conclude."]
        )
        with pytest.raises(ValueError, match="source_chunk"):
            validate_committee_brief_source(synthesis)

    def test_pcim_in_prose_rejected(self):
        """P2-3: 'pcim'/'cim' appearing literally in user-facing prose is rejected.
        Note: the check fires on 'cim' first since 'pcim' contains 'cim' as a substring."""
        synthesis = _minimal_synthesis(
            synthesis_limits=["The pcim artifact was not fully hydrated for this company."]
        )
        with pytest.raises(ValueError, match=r"cim"):
            validate_committee_brief_source(synthesis)

    def test_schema_in_prose_rejected(self):
        """P2-4: 'schema' appearing in user-facing prose is rejected."""
        synthesis = _minimal_synthesis(
            evidence_quality_notes=["schema warnings prevented full synthesis."]
        )
        with pytest.raises(ValueError, match="schema"):
            validate_committee_brief_source(synthesis)

    def test_artifact_in_prose_rejected(self):
        """P2-5: 'artifact' appearing in user-facing prose is rejected."""
        synthesis = _minimal_synthesis(
            synthesis_limits=["The upstream artifact contained incomplete data."]
        )
        with pytest.raises(ValueError, match="artifact"):
            validate_committee_brief_source(synthesis)


# ---------------------------------------------------------------------------
# P3: Ordinary investor language — must be ACCEPTED
# ---------------------------------------------------------------------------

class TestNormalInvestorLanguageAccepted:
    """Normal user-facing evidence language must not be over-blocked."""

    def test_supported_by_earnings_call_accepted(self):
        """P3-1: Natural evidence citation language is not blocked."""
        synthesis = _minimal_synthesis(
            synthesis_limits=["Analysis supported by the Q4 earnings call."]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None

    def test_management_stated_language_accepted(self):
        """P3-2: 'management stated' narrative phrasing is not blocked."""
        synthesis = _minimal_synthesis(
            synthesis_limits=["Management stated the new facility is 80% complete."]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None

    def test_available_evidence_uncertainty_accepted(self):
        """P3-3: Honest uncertainty language is not blocked."""
        synthesis = _minimal_synthesis(
            synthesis_limits=[
                "Available evidence does not establish whether the capex commitment will yield returns."
            ]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None

    def test_evidence_ids_plural_as_phrase_in_clean_context_accepted(self):
        """P3-4: After phrase-cleaning, the rewritten exclusion message passes."""
        synthesis = _minimal_synthesis(
            evidence_quality_notes=[
                "buffett was excluded because final analyst evidence IDs are invalid: "
                "[{'reason': 'unknown_evidence_id'}].",
            ]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None

    def test_empty_quality_notes_accepted(self):
        """P3-5: Synthesis with no evidence_quality_notes passes cleanly."""
        synthesis = _minimal_synthesis(evidence_quality_notes=[])
        result = validate_committee_brief_source(synthesis)
        assert result is not None


# ---------------------------------------------------------------------------
# P4: Structured provenance survives round-trip through build_canonical_committee_brief_view
# ---------------------------------------------------------------------------

class TestProvenancePreserved:
    """Evidence IDs must remain in the synthesis; they must not leak into rendered prose."""

    def test_internal_evidence_ids_preserved_in_synthesis(self):
        """P4-1: evidence_ids structured fields survive the synthesis payload unchanged."""
        synthesis = _minimal_synthesis(
            areas_of_agreement=[
                {
                    "theme": "Operational resilience",
                    "summary": "Analysts agree on sustained operational performance.",
                    "source_analysts": ["fisher"],
                    "evidence_ids": ["ev_fy26_ops_001"],
                }
            ]
        )
        validated = validate_committee_brief_source(synthesis)
        agreements = validated.get("areas_of_agreement", [])
        assert len(agreements) == 1
        assert "ev_fy26_ops_001" in agreements[0].get("evidence_ids", [])

    def test_rendered_brief_contains_no_evidence_id_prose(self):
        """P4-2: The rendered brief view must not expose 'evidence_id' in user-facing strings."""
        from intelligence.investor_panel.committee_brief_renderer import (
            build_canonical_committee_brief_view,
            _flatten_strings,
        )
        synthesis = _minimal_synthesis(
            evidence_quality_notes=[
                "buffett was excluded because final analyst evidence IDs are invalid: "
                "[{'path': '$.evidence_ids', 'invalid_id': 'ev_cap', 'reason': 'unknown_evidence_id'}].",
            ],
            areas_of_agreement=[
                {
                    "theme": "Growth",
                    "summary": "Analysts agree on top-line momentum.",
                    "source_analysts": ["graham"],
                    "evidence_ids": ["ev_fy26_rev"],
                }
            ],
        )
        validated = validate_committee_brief_source(synthesis)
        brief = build_canonical_committee_brief_view(validated)
        all_strings = _flatten_strings(brief)
        leaking = [s for s in all_strings if "evidence_id" in s.lower() and "evidence_ids" not in s.lower()]
        # evidence_ids plural may survive in structured provenance within the brief
        # but the literal "evidence_id" (singular, without _ids suffix) must not leak into prose
        prose_leaks = [s for s in all_strings if "evidence_id" in s.lower() and not s.strip().startswith("ev_") and "evidence_ids" not in s.lower()]
        assert prose_leaks == [], f"Brief contains evidence_id prose leakage: {prose_leaks}"

    def test_exclusion_message_rewritten_not_stripped(self):
        """P4-3: Analyst exclusion diagnostic is rewritten to user-safe form, not stripped."""
        from intelligence.investor_panel.committee_brief_renderer import _clean_phrase
        raw = (
            "buffett was excluded because final analyst evidence IDs are invalid: "
            "[{'path': '$.evidence_ids', 'invalid_id': 'ev_cap', 'reason': 'unknown_evidence_id'}]."
        )
        cleaned = _clean_phrase(raw)
        assert cleaned == "Buffett was excluded because cited source references could not be verified."
        # Internal diagnostic data is gone
        assert "evidence_id" not in cleaned.lower()
        assert "unknown_evidence_id" not in cleaned
        assert "ev_cap" not in cleaned


# ---------------------------------------------------------------------------
# P5: Sun Pharma production regression
# ---------------------------------------------------------------------------

class TestSunPharmaProductionRegression:
    """Sun Pharma committee_synthesis.json must now validate successfully."""

    @pytest.fixture
    def sun_pharma_synthesis(self):
        path = Path("companies/sun_pharma/company_memory/investor_panel/committee_synthesis.json")
        if not path.exists():
            pytest.skip("Sun Pharma committee_synthesis.json not available")
        return json.loads(path.read_text())

    def test_sun_pharma_synthesis_validates(self, sun_pharma_synthesis):
        """P5-1: The existing Sun Pharma committee synthesis passes validate_committee_brief_source."""
        result = validate_committee_brief_source(sun_pharma_synthesis)
        assert result is not None

    def test_sun_pharma_evidence_quality_notes_have_exclusion_messages(self, sun_pharma_synthesis):
        """P5-2: Confirm the Sun Pharma synthesis actually contains the problematic exclusion messages."""
        notes = sun_pharma_synthesis.get("evidence_quality_notes", [])
        exclusion_notes = [n for n in notes if "was excluded because" in str(n).lower()]
        assert len(exclusion_notes) >= 1, "Expected at least one analyst exclusion message"

    def test_sun_pharma_internal_evidence_ids_preserved(self, sun_pharma_synthesis):
        """P5-3: After validation, structured evidence_ids fields in Sun Pharma synthesis are unchanged."""
        validated = validate_committee_brief_source(sun_pharma_synthesis)
        # Verify the evidence_ids structured fields exist unchanged
        agreements = validated.get("areas_of_agreement", [])
        # Check any item with evidence_ids survives
        for item in agreements:
            if "evidence_ids" in item:
                assert isinstance(item["evidence_ids"], list)


# ---------------------------------------------------------------------------
# P6: Tanla regression
# ---------------------------------------------------------------------------

class TestTanlaRegression:
    """Tanla committee synthesis must continue to validate (no regression)."""

    @pytest.fixture
    def tanla_synthesis(self):
        path = Path("companies/tanla/company_memory/investor_panel/committee_synthesis.json")
        if not path.exists():
            pytest.skip("Tanla committee_synthesis.json not available")
        return json.loads(path.read_text())

    def test_tanla_synthesis_validates(self, tanla_synthesis):
        """P6-1: Tanla committee synthesis still passes validation after repair."""
        result = validate_committee_brief_source(tanla_synthesis)
        assert result is not None

    def test_tanla_synthesis_no_evidence_id_prose_leakage(self, tanla_synthesis):
        """P6-2: Tanla committee synthesis has no evidence_id leakage in prose fields."""
        from intelligence.investor_panel.committee_brief_renderer import _flatten_strings, _clean_phrase
        public_fields = [
            tanla_synthesis.get("evidence_quality_notes"),
            tanla_synthesis.get("synthesis_limits"),
            tanla_synthesis.get("overall_committee_view"),
        ]
        cleaned = [_clean_phrase(s) for s in _flatten_strings(public_fields) if _clean_phrase(s)]
        leaks = [s for s in cleaned if "evidence_id" in s.lower()]
        assert leaks == []


# ---------------------------------------------------------------------------
# P7: Data Patterns regression
# ---------------------------------------------------------------------------

class TestDataPatternsRegression:
    """Data Patterns committee synthesis must continue to validate (no regression)."""

    @pytest.fixture
    def datapatterns_synthesis(self):
        path = Path("companies/datapatterns/company_memory/investor_panel/committee_synthesis.json")
        if not path.exists():
            pytest.skip("Data Patterns committee_synthesis.json not available")
        return json.loads(path.read_text())

    def test_datapatterns_synthesis_validates(self, datapatterns_synthesis):
        """P7-1: Data Patterns committee synthesis still passes validation after repair."""
        result = validate_committee_brief_source(datapatterns_synthesis)
        assert result is not None


# ---------------------------------------------------------------------------
# P8: Adversarial nested structures
# ---------------------------------------------------------------------------

class TestAdversarialNestedStructures:
    """Nested structures with legal keys and illegal prose strings are handled correctly."""

    def test_nested_evidence_id_key_in_deep_structure_accepted(self):
        """P8-1: evidence_id as a key in a deeply nested structured object is allowed."""
        synthesis = _minimal_synthesis(
            critical_unknowns=[
                {
                    "unknown": "Whether FCF converts to per-share improvement.",
                    "why_it_matters": "Per-share improvement is the investor-grade test.",
                    "raised_by": ["graham"],
                    "evidence_ids": [
                        {
                            "evidence_id": "ev_fy26_fcf",
                            "source_period": "fy26",
                        }
                    ],
                }
            ]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None

    def test_internal_term_in_nested_prose_rejected(self):
        """P8-2: internal term in a nested string value in a public field is rejected."""
        synthesis = _minimal_synthesis(
            most_important_risks=[
                {
                    "risk": "Regulatory risk",
                    "summary": "The risks are described in the source_chunk context.",
                    "severity": "medium",
                    "raised_by": ["graham"],
                    "evidence_ids": [],
                }
            ]
        )
        with pytest.raises(ValueError, match="source_chunk"):
            validate_committee_brief_source(synthesis)

    def test_valid_nested_prose_with_structured_evidence_ids_accepted(self):
        """P8-3: Valid investor prose in nested field alongside structured evidence_ids is accepted."""
        synthesis = _minimal_synthesis(
            strongest_positive_signals=[
                {
                    "signal": "Net cash balance sheet",
                    "summary": "The company maintains net-cash position across measured periods.",
                    "supported_by": ["Fisher"],
                    "evidence_ids": ["ev_fy26_net_cash"],
                }
            ]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None


# ---------------------------------------------------------------------------
# P9: Committee finalization ownership — one canonical owner
# ---------------------------------------------------------------------------

class TestCommitteeFinalizationOwnership:
    """Committee finalization must occur once and through the canonical path."""

    def test_finalize_committee_brief_quality_is_idempotent(self):
        """P9-1: Running finalize_committee_brief_quality twice produces the same result."""
        from intelligence.investor_panel.committee_brief_renderer import finalize_committee_brief_quality
        synthesis = _minimal_synthesis(
            overall_committee_view={
                "summary": "The committee view is constructive.",
                "confidence": "medium",
                "dominant_tension": "Execution versus capital efficiency.",
            },
            financial_committee_view={
                "financials_used": True,
                "basis_used": "standalone",
                "financial_consensus": ["Revenue growth is visible."],
                "financial_strengths": [],
                "financial_concerns": [],
                "financial_disagreements": [],
                "missing_financial_data": [],
                "financial_red_flags": [],
                "financial_interpretation_limits": [],
                "investor_questions_from_financials": [],
            },
        )
        once = finalize_committee_brief_quality(synthesis)
        twice = finalize_committee_brief_quality(once)
        assert once["overall_committee_view"]["summary"] == twice["overall_committee_view"]["summary"]

    def test_validate_committee_brief_source_does_not_re_finalize(self):
        """P9-2: validate_committee_brief_source returns the payload unchanged (no re-finalization side effects)."""
        synthesis = _minimal_synthesis()
        synthesis["overall_committee_view"]["summary"] = "The committee view is stable."
        validated = validate_committee_brief_source(synthesis)
        # The validator returns the same payload object (no mutation of narrative content)
        assert validated["overall_committee_view"]["summary"] == "The committee view is stable."


# ---------------------------------------------------------------------------
# P10: Critical unknowns contract unchanged
# ---------------------------------------------------------------------------

class TestCriticalUnknownContractUnchanged:
    """The critical_unknowns validation contract must remain intact."""

    def test_critical_unknowns_with_valid_shape_accepted(self):
        """P10-1: critical_unknowns with valid unknown + why_it_matters pass."""
        synthesis = _minimal_synthesis(
            critical_unknowns=[
                {
                    "unknown": "Whether FCF is durable across cycles.",
                    "why_it_matters": "Durable FCF is required for conviction.",
                    "raised_by": ["graham"],
                }
            ]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None

    def test_critical_unknowns_with_evidence_id_key_accepted(self):
        """P10-2: critical_unknowns item with structured evidence_ids key passes."""
        synthesis = _minimal_synthesis(
            critical_unknowns=[
                {
                    "unknown": "Whether capex is maintenance or growth.",
                    "why_it_matters": "Capex classification determines owner-earnings reliability.",
                    "raised_by": ["buffett"],
                    "evidence_ids": ["ev_fy26_capex_001"],
                }
            ]
        )
        result = validate_committee_brief_source(synthesis)
        assert result is not None

    def test_critical_unknowns_with_evidence_id_in_prose_rejected(self):
        """P10-3: critical_unknowns item with 'evidence_id' in prose string is rejected."""
        synthesis = _minimal_synthesis(
            critical_unknowns=[
                {
                    "unknown": "This is grounded in evidence_id ev-001 but unclear.",
                    "why_it_matters": "Clarity is required.",
                    "raised_by": ["graham"],
                }
            ]
        )
        with pytest.raises(ValueError, match="evidence_id"):
            validate_committee_brief_source(synthesis)
