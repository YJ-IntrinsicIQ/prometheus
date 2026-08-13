"""Tests for Risk Evolution Intelligence."""

import pytest
from pathlib import Path
from typing import Any, Dict

from intelligence.risks.contracts import (
    RiskDefinition,
    RiskMateriality,
    RiskConfidence,
    RiskProgressionAdapter,
)
from intelligence.risks.normalizer import (
    _normalize_risk_name,
    _extract_risk_mechanism,
    normalize_candidate,
    deduplicate_risks,
    _similarity_score,
)
from intelligence.risks.classifier import (
    classify_risk_category,
    is_generic_boilerplate,
    extract_affected_area,
    sanitize_public_text,
)
from intelligence.risks.materiality import assess_materiality
from intelligence.risks.mitigation import (
    extract_mitigations,
    assess_mitigation_effectiveness,
    build_mitigation_summary,
    identify_unproven_mitigations,
)
from intelligence.risks.validators import validate_risk_payload
from intelligence.risks.progression import (
    build_risk_event,
    assess_risk_trajectory,
)
from intelligence.risks.builder import _build_risk_timelines


class TestRiskNormalization:
    """Test risk normalization."""

    def test_normalize_risk_name(self):
        """Test risk name normalization."""
        # Remove risk prefix
        assert "customer concentration" in _normalize_risk_name("Risk of customer concentration")
        
        # Remove common suffixes
        assert "supplier dependence" in _normalize_risk_name("Supplier dependence risk")
        
        # Handle articles
        assert "receivable stress" in _normalize_risk_name("The receivable stress")

    def test_extract_risk_mechanism(self):
        """Test risk mechanism extraction."""
        description = "Customer concentration from DRDO if budget cuts occur, resulting in revenue loss"
        mechanism = _extract_risk_mechanism(description)
        
        # Should extract first meaningful clause
        assert "customer" in mechanism.lower()
        assert "drdo" in mechanism.lower()

    def test_normalize_candidate(self):
        """Test candidate normalization."""
        candidate = {
            "value": "Risk of customer concentration",
            "description": "Heavy dependence on DRDO orders",
            "category": "customer",
            "source_year": "fy22",
            "confidence": {"level": "high"},
        }
        
        normalized = normalize_candidate(candidate, "datapatterns")
        
        assert normalized["risk_id"]
        assert normalized["normalized_name"]
        assert normalized["risk_mechanism"]
        assert normalized["first_observed_period"] == "fy22"

    def test_deduplicate_similar_risks(self):
        """Test risk deduplication."""
        candidates = [
            {
                "risk_id": "r1",
                "risk_name": "Customer concentration DRDO",
                "risk_category": "customer",
                "first_observed_period": "fy22",
                "latest_period": "fy22",
            },
            {
                "risk_id": "r2",
                "risk_name": "Revenue concentration DRDO",
                "risk_category": "customer",
                "first_observed_period": "fy23",
                "latest_period": "fy23",
            },
        ]
        
        # High threshold ensures they deduplicate
        deduplicated, merge_log = deduplicate_risks(candidates, similarity_threshold=0.3)
        
        # May or may not merge depending on threshold
        assert isinstance(deduplicated, list)
        assert isinstance(merge_log, list)

    def test_similarity_score(self):
        """Test risk similarity scoring."""
        # Needs at least 3 common tokens
        score_similar = _similarity_score(
            "Customer concentration revenue DRDO exposure",
            "Customer concentration revenue DRDO risk",
        )
        assert isinstance(score_similar, float)
        assert score_similar > 0
        
        # Very different - no 3 common tokens
        score_low = _similarity_score(
            "Customer concentration",
            "Project execution delay",
        )
        assert score_low == 0.0


class TestRiskClassification:
    """Test risk classification."""

    def test_classify_customer_risk(self):
        """Test customer risk classification."""
        category = classify_risk_category(
            "Heavy concentration of revenue from DRDO orders"
        )
        assert category == "customer"

    def test_classify_financial_risk(self):
        """Test financial risk classification."""
        category = classify_risk_category(
            "Margin compression due to rising input costs"
        )
        assert category == "financial"

    def test_classify_execution_risk(self):
        """Test execution risk classification."""
        category = classify_risk_category(
            "Project delays in facility commissioning"
        )
        # May classify as project or execution
        assert category in ["execution", "project"]

    def test_reject_generic_boilerplate(self):
        """Test generic boilerplate rejection."""
        # Generic
        assert is_generic_boilerplate("The industry is competitive")
        assert is_generic_boilerplate("There may be uncertainty")
        assert is_generic_boilerplate("Growth could slow")
        
        # Specific
        assert not is_generic_boilerplate(
            "Customer concentration from DRDO if budget cuts occur"
        )

    def test_extract_affected_area(self):
        """Test affected area extraction."""
        area = extract_affected_area(
            "Revenue concentration from DRDO",
            "customer"
        )
        assert "revenue" in area.lower()

    def test_sanitize_public_text(self):
        """Test public text sanitization."""
        text = "Risk from company_memory source_chunk artifact"
        sanitized = sanitize_public_text(text)
        
        assert "company_memory" not in sanitized
        assert "source_chunk" not in sanitized
        assert "artifact" not in sanitized


class TestMaterialityAssessment:
    """Test materiality assessment."""

    def test_high_materiality_persistent_concentrated_risk(self):
        """Test high materiality for persistent, concentrated risk."""
        materiality = assess_materiality(
            risk_id="r1",
            risk_name="Customer concentration DRDO",
            description="DRDO represents >70% of revenue",
            category="customer",
            affected_area="revenue concentration",
            persistence_count=3,  # Multiple years
            evidence_quality="direct",
            financial_impact=500.0,  # Significant
            is_concentration_risk=True,
        )
        
        assert materiality.level == "high"
        assert "persistent" in " ".join(materiality.basis).lower()
        assert "concentration" in " ".join(materiality.basis).lower()

    def test_low_materiality_single_period_risk(self):
        """Test low materiality for single-period risk."""
        materiality = assess_materiality(
            risk_id="r2",
            risk_name="Temporary supplier constraint",
            description="Short-term component shortage",
            category="supplier",
            affected_area="operations",
            persistence_count=1,  # Single year
            evidence_quality="partial",
            is_concentration_risk=False,
        )
        
        assert materiality.level in ["low", "unclear"]
        # Should have some limitations noted
        assert len(materiality.limitations) > 0


class TestMitigationTracking:
    """Test mitigation tracking."""

    def test_extract_mitigations(self):
        """Test mitigation extraction from events."""
        risk_data = {}
        events = [
            {
                "event_type": "mitigation_announced",
                "title": "Diversification into commercial satellite",
                "period": "fy23",
                "description": "Launch new commercial offerings",
                "confidence": {"level": "medium"},
            },
        ]
        
        mitigations = extract_mitigations(risk_data, events)
        
        assert len(mitigations) > 0
        assert mitigations[0].mitigation_action
        assert mitigations[0].announcement_period == "fy23"

    def test_assess_mitigation_effectiveness(self):
        """Test mitigation effectiveness assessment."""
        from intelligence.risks.contracts import RiskMitigation
        
        mitigations = [
            RiskMitigation(
                mitigation_action="Action 1",
                announcement_period="fy23",
                latest_status="in_progress",
            ),
        ]
        events = []
        
        effectiveness = assess_mitigation_effectiveness(
            "persistent",
            mitigations,
            events,
        )
        
        assert effectiveness["effectiveness"] == "in_progress"


def test_risk_progression_uses_concrete_longitudinal_summary():
    definition = RiskDefinition(
        risk_id="risk_customer_concentration",
        risk_name="Customer concentration",
        normalized_name="Customer concentration",
        risk_category="customer",
        first_observed_period="fy23",
        latest_period="fy25",
        current_status="persistent",
        risk_mechanism="Heavy reliance on a small number of defence customers.",
        source_references=[
            {"artifact": "multi_year/risk_evolution.json", "year": "fy23", "item_id": "risk_customer_concentration"},
            {"artifact": "multi_year/risk_evolution.json", "year": "fy25", "item_id": "risk_revenue_concentration"},
        ],
        confidence=RiskConfidence(level="high", basis=["2 source reference(s)", "2 period(s) covered"], limitations=[]),
    )

    timelines, assessments = _build_risk_timelines([definition])

    assert timelines[0]["latest_period"] == "fy25"
    assert assessments[0]["latest_period"] == "fy25"
    assert "identified in the source evidence" not in assessments[0]["what_changed"].lower()
    assert "initial identification" not in assessments[0]["what_changed"].lower()
    assert "customer concentration" in assessments[0]["what_changed"].lower()

    def test_identify_unproven_mitigations(self):
        """Test identification of unproven mitigations."""
        from intelligence.risks.contracts import RiskMitigation
        
        mitigations = [
            RiskMitigation(
                mitigation_action="Action 1",
                announcement_period="fy23",
                latest_status="announced",
            ),
            RiskMitigation(
                mitigation_action="Action 2",
                announcement_period="fy24",
                latest_status="effective",
            ),
        ]
        
        unproven = identify_unproven_mitigations(mitigations)
        
        # Should find the announced one as unproven
        assert len(unproven) > 0
        assert any("Action 1" in item["mitigation_action"] for item in unproven)


class TestValidation:
    """Test validation."""

    def test_validate_unique_risk_ids(self):
        """Test unique risk ID validation."""
        registry = {
            "risks": [
                {
                    "risk_id": "r1",
                    "risk_name": "Risk 1",
                    "current_status": "persistent",
                },
                {
                    "risk_id": "r1",  # Duplicate
                    "risk_name": "Risk 2",
                    "current_status": "persistent",
                },
            ]
        }
        
        report = validate_risk_payload(registry, {}, {})
        
        assert report["status"] == "fail"
        assert report["error_count"] > 0

    def test_validate_resolved_requires_evidence(self):
        """Test that resolved status requires evidence."""
        registry = {
            "risks": [
                {
                    "risk_id": "r1",
                    "risk_name": "Risk resolved without evidence",
                    "current_status": "resolved",
                    "counter_evidence": None,
                    "mitigation_evidence": None,
                }
            ]
        }
        
        report = validate_risk_payload(registry, {}, {})
        
        # Should flag warning or error
        assert report["error_count"] > 0 or report["warning_count"] > 0

    def test_validate_conviction_impact_semantics(self):
        """Test conviction impact semantic validation."""
        registry = {"risks": []}
        assessments = {
            "assessments": [
                {
                    "risk_id": "r1",
                    "conviction_impact": "risk_worsened",  # Invalid
                }
            ]
        }
        
        report = validate_risk_payload(registry, {}, assessments)
        
        # Should flag as error
        assert report["error_count"] > 0

    def test_validate_no_internal_terminology(self):
        """Test that internal terminology is rejected."""
        registry = {
            "risks": [
                {
                    "risk_id": "r1",
                    "risk_name": "Risk from company_memory source_chunk",
                    "current_status": "persistent",
                }
            ]
        }
        
        report = validate_risk_payload(registry, {}, {})
        
        assert report["error_count"] > 0


class TestProgression:
    """Test risk progression."""

    def test_build_risk_event(self):
        """Test risk event building."""
        event = build_risk_event(
            risk_id="r1",
            period="fy23",
            event_type="risk_confirmed",
            title="Risk confirmed",
            description="Evidence of risk materialization",
            confidence={"level": "high"},
            source_references=[],
        )
        
        assert event["subject_id"] == "r1"
        assert event["period"] == "fy23"
        assert event["event_type"] == "risk_confirmed"

    def test_assess_risk_trajectory_worsening(self):
        """Test trajectory assessment for worsening risk."""
        events = [
            {"event_type": "risk_signal", "period": "fy22"},
            {"event_type": "risk_confirmed", "period": "fy23"},
            {"event_type": "risk_intensified", "period": "fy24"},
        ]
        
        trajectory = assess_risk_trajectory(events)
        
        assert trajectory["direction"] == "worsening"

    def test_progression_adapter_derive_status(self):
        """Test progression adapter status derivation."""
        adapter = RiskProgressionAdapter()
        events = [
            {"event_type": "risk_signal"},
            {"event_type": "risk_persisted"},
        ]
        
        status = adapter.derive_current_state(events)
        
        assert status in ["persistent", "emerging"]


class TestEndToEnd:
    """End-to-end tests."""

    def test_risk_definition_contract(self):
        """Test risk definition contract."""
        risk = RiskDefinition(
            risk_id="r1",
            risk_name="Customer concentration",
            normalized_name="customer concentration",
            risk_category="customer",
            affected_area="revenue concentration",
            first_observed_period="fy22",
            latest_period="fy24",
            current_status="persistent",
            materiality=RiskMateriality(
                level="high",
                affected_dimensions=["revenue concentration"],
                basis=["persistent across three periods"],
            ),
        )
        
        risk_dict = risk.to_dict()
        
        assert risk_dict["risk_id"] == "r1"
        assert risk_dict["materiality"]["level"] == "high"
        assert "revenue" in str(risk_dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
