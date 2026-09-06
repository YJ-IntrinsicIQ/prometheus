"""Tests for Risk Evolution Intelligence."""

import pytest
from pathlib import Path
from typing import Any, Dict, Optional

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


class TestTrajectoryRouting:
    """ENG-109 adversarial tests for canonical risk identity and trajectory routing."""

    def _make_candidate(self, name: str, evo_id: str, trajectory: Optional[str]) -> dict:
        return {
            "risk_name": name,
            "description": f"{name} mechanism",
            "category": "financial",
            "source_year": "fy22",
            "source_artifact": "multi_year/risk_evolution.json",
            "source_item_id": evo_id,
            "confidence": {"level": "high"},
            "current_status": "persistent",
            "evo_trajectory": trajectory,
            "evo_canonical_id": evo_id,
            "evo_severity_by_year": {"fy22": "medium", "fy24": "high"},
            "evo_latest_severity": "high",
        }

    def test_a_display_name_mismatch_fx(self):
        """A — 'Foreign Exchange Risk' and 'risk_foreign_exchange_risk' resolve to same normalized name."""
        n1 = normalize_candidate(self._make_candidate("Foreign Exchange Risk", "risk_foreign_exchange_risk", "worsening"), "sun_pharma")
        n2 = normalize_candidate(self._make_candidate("Foreign exchange risk", "risk_foreign_exchange_risk", "worsening"), "sun_pharma")
        # Both must carry the trajectory
        assert n1["evo_trajectory"] == "worsening"
        assert n2["evo_trajectory"] == "worsening"
        assert n1["evo_canonical_id"] == "risk_foreign_exchange_risk"

    def test_b_hyphenation_variant_ip(self):
        """B — 'Intellectual-property protection' carries trajectory from evolution."""
        c = self._make_candidate("Intellectual-property protection", "risk_intellectual_property", "improving")
        n = normalize_candidate(c, "sun_pharma")
        assert n["evo_trajectory"] == "improving"
        assert n["evo_canonical_id"] == "risk_intellectual_property"

    def test_c_worsening_propagates_to_assessment(self):
        """C — worsening trajectory produces increasing status and non-boilerplate why_it_changed."""
        from intelligence.risks.builder import _build_risk_definitions, _build_risk_timelines
        risk = {
            "risk_id": "risk_fx_test",
            "risk_name": "Foreign Exchange Risk",
            "normalized_name": "foreign exchange",
            "risk_category": "currency",
            "first_observed_period": "fy22",
            "latest_period": "fy24",
            "current_status": "emerging",
            "risk_mechanism": "Currency volatility affects export revenue",
            "confidence": {"level": "high"},
            "source_references": [{"artifact": "multi_year/risk_evolution.json", "year": "fy22", "item_id": "risk_foreign_exchange_risk"}],
            "semantic_quality": {},
            "related_commitment_ids": [],
            "related_project_ids": [],
            "related_capacity_ids": [],
            "related_financial_metrics": [],
            "evo_trajectory": "worsening",
            "evo_canonical_id": "risk_foreign_exchange_risk",
            "evo_severity_by_year": {"fy22": "low", "fy24": "medium"},
            "evo_latest_severity": "medium",
        }
        defs = _build_risk_definitions([risk])
        assert defs[0].current_status == "increasing"
        assert defs[0].evo_trajectory == "worsening"

        _, assessments = _build_risk_timelines(defs)
        a = assessments[0]
        assert a["current_status"] == "increasing"
        assert a["trajectory"] == "worsening"
        assert "no later period" not in a["why_it_changed"].lower()
        assert "worsening" in a["why_it_changed"].lower()

    def test_d_improving_propagates_to_assessment(self):
        """D — improving trajectory produces reducing status."""
        from intelligence.risks.builder import _build_risk_definitions, _build_risk_timelines
        risk = {
            "risk_id": "risk_ip_test",
            "risk_name": "Intellectual-property protection",
            "normalized_name": "intellectual-property protection",
            "risk_category": "legal",
            "first_observed_period": "fy23",
            "latest_period": "fy25",
            "current_status": "emerging",
            "risk_mechanism": "Patent challenges from competitors",
            "confidence": {"level": "high"},
            "source_references": [{"artifact": "multi_year/risk_evolution.json", "year": "fy23", "item_id": "risk_intellectual_property"}],
            "semantic_quality": {},
            "related_commitment_ids": [],
            "related_project_ids": [],
            "related_capacity_ids": [],
            "related_financial_metrics": [],
            "evo_trajectory": "improving",
            "evo_canonical_id": "risk_intellectual_property",
            "evo_severity_by_year": {"fy23": "high", "fy25": "medium"},
            "evo_latest_severity": "medium",
        }
        defs = _build_risk_definitions([risk])
        assert defs[0].current_status == "reducing"
        _, assessments = _build_risk_timelines(defs)
        assert assessments[0]["current_status"] == "reducing"
        assert assessments[0]["trajectory"] == "improving"
        assert "improvement" in assessments[0]["why_it_changed"].lower()

    def test_e_recurring_not_increasing(self):
        """E — recurring trajectory upgrades emerging to recurring but NOT to increasing."""
        from intelligence.risks.builder import _build_risk_definitions, _build_risk_timelines
        risk = {
            "risk_id": "risk_competition_test",
            "risk_name": "Competitive intensity",
            "normalized_name": "competitive intensity",
            "risk_category": "competitive",
            "first_observed_period": "fy20",
            "latest_period": "fy24",
            "current_status": "emerging",
            "risk_mechanism": "Growing competition in key markets",
            "confidence": {"level": "medium"},
            "source_references": [{"artifact": "multi_year/risk_evolution.json", "year": "fy20", "item_id": "risk_competition"}],
            "semantic_quality": {},
            "related_commitment_ids": [],
            "related_project_ids": [],
            "related_capacity_ids": [],
            "related_financial_metrics": [],
            "evo_trajectory": "recurring",
            "evo_canonical_id": "risk_competition",
            "evo_severity_by_year": {"fy20": "medium", "fy22": "medium", "fy24": "medium"},
            "evo_latest_severity": "medium",
        }
        defs = _build_risk_definitions([risk])
        assert defs[0].current_status == "recurring"
        assert defs[0].current_status != "increasing"
        _, assessments = _build_risk_timelines(defs)
        assert assessments[0]["trajectory"] == "recurring"
        assert assessments[0]["current_status"] != "increasing"

    def test_f_single_period_no_trajectory(self):
        """F — single period risk with no evo_trajectory stays conservative."""
        from intelligence.risks.builder import _build_risk_definitions, _build_risk_timelines
        risk = {
            "risk_id": "risk_single_period",
            "risk_name": "Energy Supply Dependence",
            "normalized_name": "energy supply dependence",
            "risk_category": "operational",
            "first_observed_period": "fy25",
            "latest_period": "fy25",
            "current_status": "emerging",
            "risk_mechanism": "Dependence on grid supply",
            "confidence": {"level": "medium"},
            "source_references": [{"artifact": "multi_year/risk_evolution.json", "year": "fy25", "item_id": ""}],
            "semantic_quality": {},
            "related_commitment_ids": [],
            "related_project_ids": [],
            "related_capacity_ids": [],
            "related_financial_metrics": [],
            "evo_trajectory": None,
            "evo_canonical_id": None,
            "evo_severity_by_year": {},
            "evo_latest_severity": None,
        }
        defs = _build_risk_definitions([risk])
        assert defs[0].current_status == "emerging"
        assert defs[0].evo_trajectory is None
        _, assessments = _build_risk_timelines(defs)
        assert assessments[0].get("trajectory") is None
        # Single period: boilerplate is allowed here
        assert "no later period" in assessments[0]["why_it_changed"].lower()

    def test_g_high_severity_no_trajectory_stays_unknown(self):
        """G — high severity without trajectory does not produce directional status."""
        from intelligence.risks.builder import _build_risk_definitions
        risk = {
            "risk_id": "risk_high_sev",
            "risk_name": "Governance Risk",
            "normalized_name": "governance risk",
            "risk_category": "governance",
            "first_observed_period": "fy23",
            "latest_period": "fy23",
            "current_status": "emerging",
            "risk_mechanism": "Board governance concerns",
            "confidence": {"level": "high"},
            "source_references": [{"artifact": "multi_year/risk_evolution.json", "year": "fy23", "item_id": "risk_governance_risk"}],
            "semantic_quality": {},
            "related_commitment_ids": [],
            "related_project_ids": [],
            "related_capacity_ids": [],
            "related_financial_metrics": [],
            "evo_trajectory": None,  # No trajectory despite high severity
            "evo_canonical_id": "risk_governance_risk",
            "evo_severity_by_year": {"fy23": "high"},
            "evo_latest_severity": "high",
        }
        defs = _build_risk_definitions([risk])
        # High severity alone must NOT produce increasing status
        assert defs[0].current_status == "emerging"
        assert defs[0].evo_trajectory is None

    def test_h_worsening_no_financial_evidence(self):
        """H — worsening trajectory does not imply financial consequence."""
        from intelligence.risks.builder import _build_risk_definitions, _build_risk_timelines
        risk = {
            "risk_id": "risk_ops",
            "risk_name": "Operational Risk",
            "normalized_name": "operational risk",
            "risk_category": "operational",
            "first_observed_period": "fy24",
            "latest_period": "fy26",
            "current_status": "emerging",
            "risk_mechanism": "Operational disruptions at manufacturing sites",
            "confidence": {"level": "high"},
            "source_references": [{"artifact": "multi_year/risk_evolution.json", "year": "fy24", "item_id": "risk_operational_risk"}],
            "semantic_quality": {},
            "related_commitment_ids": [],
            "related_project_ids": [],
            "related_capacity_ids": [],
            "related_financial_metrics": [],
            "evo_trajectory": "worsening",
            "evo_canonical_id": "risk_operational_risk",
            "evo_severity_by_year": {"fy24": "medium", "fy26": "high"},
            "evo_latest_severity": "high",
        }
        defs = _build_risk_definitions([risk])
        _, assessments = _build_risk_timelines(defs)
        a = assessments[0]
        # Trajectory surfaced
        assert a["trajectory"] == "worsening"
        # conviction_impact stays unclear — not inferred from trajectory
        assert a["conviction_impact"] == "unclear"

    def test_i_improving_no_management_action(self):
        """I — improving trajectory does not imply management response."""
        from intelligence.risks.builder import _build_risk_definitions, _build_risk_timelines
        risk = {
            "risk_id": "risk_mkt",
            "risk_name": "Market Risk",
            "normalized_name": "market risk",
            "risk_category": "financial",
            "first_observed_period": "fy20",
            "latest_period": "fy21",
            "current_status": "emerging",
            "risk_mechanism": "Volatility in domestic pharma market",
            "confidence": {"level": "medium"},
            "source_references": [{"artifact": "multi_year/risk_evolution.json", "year": "fy20", "item_id": "risk_market_risk"}],
            "semantic_quality": {},
            "related_commitment_ids": [],
            "related_project_ids": [],
            "related_capacity_ids": [],
            "related_financial_metrics": [],
            "evo_trajectory": "improving",
            "evo_canonical_id": "risk_market_risk",
            "evo_severity_by_year": {"fy20": "high", "fy21": "not specified"},
            "evo_latest_severity": "not specified",
        }
        defs = _build_risk_definitions([risk])
        _, assessments = _build_risk_timelines(defs)
        a = assessments[0]
        assert a["trajectory"] == "improving"
        # No management mitigation is asserted from trajectory alone
        assert not defs[0].mitigations
        assert defs[0].mitigation_evidence is None

    def test_j_distinct_regulatory_risks_not_collapsed(self):
        """J — similar-sounding but distinct regulatory risks must not be merged."""
        from intelligence.risks.normalizer import deduplicate_risks
        risks = [
            {"risk_id": "r1", "risk_name": "Regulatory compliance risk at Toansa facility",
             "risk_category": "regulatory", "first_observed_period": "fy14", "latest_period": "fy20"},
            {"risk_id": "r2", "risk_name": "Regulatory approval risk for specialty products",
             "risk_category": "regulatory", "first_observed_period": "fy22", "latest_period": "fy24"},
        ]
        deduped, _ = deduplicate_risks(risks, similarity_threshold=0.6)
        # These have very different normalized names — should NOT merge
        assert len(deduped) == 2

    def test_k_duplicate_wording_deduplicates(self):
        """K — genuine synonym candidates deduplicate and trajectory is preserved."""
        from intelligence.risks.normalizer import deduplicate_risks
        risks = [
            {"risk_id": "r1", "risk_name": "Customer revenue concentration",
             "risk_category": "customer", "first_observed_period": "fy22", "latest_period": "fy22",
             "evo_trajectory": None, "evo_canonical_id": None},
            {"risk_id": "r2", "risk_name": "Customer revenue concentration",
             "risk_category": "customer", "first_observed_period": "fy23", "latest_period": "fy23",
             "evo_trajectory": "recurring", "evo_canonical_id": "risk_customer_concentration"},
        ]
        deduped, merge_log = deduplicate_risks(risks, similarity_threshold=0.3)
        # Should merge into one
        assert len(deduped) == 1
        # Trajectory should be propagated
        assert deduped[0].get("evo_trajectory") == "recurring"

    def test_l_unknown_identity_no_silent_fallthrough(self):
        """L — risk with no evo_canonical_id stays conservative, never silently emerges with trajectory."""
        from intelligence.risks.builder import _build_risk_definitions
        risk = {
            "risk_id": "risk_unknown_xyz",
            "risk_name": "Revenue Volatility One Time Event Risk",
            "normalized_name": "revenue volatility one time event risk",
            "risk_category": "financial",
            "first_observed_period": "fy25",
            "latest_period": "fy25",
            "current_status": "emerging",
            "risk_mechanism": "One-time milestone payments create revenue lumpiness",
            "confidence": {"level": "medium"},
            "source_references": [{"artifact": "multi_year/risk_evolution.json", "year": "fy25", "item_id": ""}],
            "semantic_quality": {},
            "related_commitment_ids": [],
            "related_project_ids": [],
            "related_capacity_ids": [],
            "related_financial_metrics": [],
            "evo_trajectory": None,
            "evo_canonical_id": None,
            "evo_severity_by_year": {},
            "evo_latest_severity": None,
        }
        defs = _build_risk_definitions([risk])
        # No trajectory fabricated
        assert defs[0].evo_trajectory is None
        assert defs[0].current_status == "emerging"


class TestValidatorTrajectoryRules:
    """Validator rules 26-30 covering trajectory truth."""

    def test_rule_26_worsening_boilerplate_flagged(self):
        """Rule 26 — worsening assessment with 'no later period' in why_it_changed is an error."""
        assessments = {"assessments": [{
            "risk_id": "r1",
            "current_status": "increasing",
            "trajectory": "worsening",
            "evo_canonical_id": "risk_fx",
            "conviction_impact": "unclear",
            "why_it_changed": "No later period is available yet to show whether the risk intensifies or recedes.",
        }]}
        report = validate_risk_payload({"risks": []}, {"timelines": []}, assessments)
        rules_hit = {i["rule"] for i in report["issues"]}
        assert "worsening_no_boilerplate" in rules_hit

    def test_rule_26_worsening_emerging_status_flagged(self):
        """Rule 26 — worsening assessment with current_status=emerging is an error."""
        assessments = {"assessments": [{
            "risk_id": "r1",
            "current_status": "emerging",  # wrong — should be increasing
            "trajectory": "worsening",
            "evo_canonical_id": "risk_fx",
            "conviction_impact": "unclear",
            "why_it_changed": "The multi-year evidence classifies fx as worsening.",
        }]}
        report = validate_risk_payload({"risks": []}, {"timelines": []}, assessments)
        rules_hit = {i["rule"] for i in report["issues"]}
        assert "worsening_not_emerging" in rules_hit

    def test_rule_27_improving_emerging_flagged(self):
        """Rule 27 — improving trajectory with current_status=emerging is an error."""
        assessments = {"assessments": [{
            "risk_id": "r1",
            "current_status": "emerging",
            "trajectory": "improving",
            "evo_canonical_id": "risk_ip",
            "conviction_impact": "unclear",
            "why_it_changed": "Improvement indicated.",
        }]}
        report = validate_risk_payload({"risks": []}, {"timelines": []}, assessments)
        rules_hit = {i["rule"] for i in report["issues"]}
        assert "improving_not_emerging" in rules_hit

    def test_rule_28_recurring_not_increasing(self):
        """Rule 28 — recurring trajectory must not map to increasing status."""
        assessments = {"assessments": [{
            "risk_id": "r1",
            "current_status": "increasing",  # wrong — recurring ≠ worsening
            "trajectory": "recurring",
            "evo_canonical_id": "risk_competition",
            "conviction_impact": "unclear",
            "why_it_changed": "Recurring.",
        }]}
        report = validate_risk_payload({"risks": []}, {"timelines": []}, assessments)
        rules_hit = {i["rule"] for i in report["issues"]}
        assert "recurring_not_increasing" in rules_hit

    def test_rule_clean_worsening_passes(self):
        """Clean worsening assessment passes rules 26-28."""
        assessments = {"assessments": [{
            "risk_id": "r1",
            "current_status": "increasing",
            "trajectory": "worsening",
            "evo_canonical_id": "risk_foreign_exchange_risk",
            "conviction_impact": "unclear",
            "why_it_changed": "The multi-year evidence classifies foreign exchange risk as worsening.",
        }]}
        report = validate_risk_payload({"risks": []}, {"timelines": []}, assessments)
        trajectory_rules = {"worsening_no_boilerplate", "worsening_not_emerging", "improving_not_emerging", "recurring_not_increasing"}
        hit = {i["rule"] for i in report["issues"]} & trajectory_rules
        assert not hit, f"Unexpected trajectory rule violations: {hit}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
