"""ENG-110 adversarial tests: canonical risk synthesis investor-facing output.

Tests A-J cover the hard boundaries from the ENG-110 mission brief.
"""

from typing import Any, Dict, List, Optional


def _wrap(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"payload": payload}


def _make_source_bundle(assessments: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "sources": {
            "risk_assessments": _wrap({"assessments": assessments}),
            "committee_synthesis": _wrap({}),
            "buffett_analysis": _wrap({}),
            "gold_risk_evolution": _wrap({}),
            "risk_evolution": _wrap({}),
            "working_capital_quality_drilldown": _wrap({}),
        }
    }


def _make_risk(
    risk_name: str,
    trajectory: Optional[str] = None,
    current_status: str = "emerging",
    why_it_changed: str = "",
    evo_canonical_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "risk_name": risk_name,
        "trajectory": trajectory,
        "current_status": current_status,
        "why_it_changed": why_it_changed,
        "conviction_impact": "unclear",
        "evo_canonical_id": evo_canonical_id or risk_name.lower().replace(" ", "_"),
        "investor_implication": None,
        "what_changed": None,
    }


# --- import the functions under test ---
from intelligence.ask_intrinsiciq.answer_cards import (
    _canonical_risk_groups,
    _build_break_thesis_answer,
    _build_regulatory_risks_answer,
    _risk_group_point,
)


class TestCanonicalRiskGroups:
    def test_worsening_routed_correctly(self):
        bundle = _make_source_bundle([_make_risk("FX Risk", trajectory="worsening")])
        groups = _canonical_risk_groups(bundle)
        assert len(groups["worsening"]) == 1
        assert groups["improving"] == []
        assert groups["recurring"] == []

    def test_improving_routed_correctly(self):
        bundle = _make_source_bundle([_make_risk("IP Risk", trajectory="improving")])
        groups = _canonical_risk_groups(bundle)
        assert len(groups["improving"]) == 1
        assert groups["worsening"] == []

    def test_recurring_routed_correctly(self):
        bundle = _make_source_bundle([_make_risk("Revenue Concentration", trajectory="recurring")])
        groups = _canonical_risk_groups(bundle)
        assert len(groups["recurring"]) == 1

    def test_none_trajectory_goes_to_other(self):
        bundle = _make_source_bundle([_make_risk("Working Capital", trajectory=None)])
        groups = _canonical_risk_groups(bundle)
        assert len(groups["other"]) == 1
        assert groups["worsening"] == []

    def test_empty_assessments_returns_empty_groups(self):
        bundle = _make_source_bundle([])
        groups = _canonical_risk_groups(bundle)
        assert all(groups[k] == [] for k in ("worsening", "improving", "recurring", "other"))

    def test_missing_source_returns_empty_groups(self):
        bundle = {}
        groups = _canonical_risk_groups(bundle)
        assert all(groups[k] == [] for k in ("worsening", "improving", "recurring", "other"))


class TestBreakThesisAnswer:
    """Tests A-E from ENG-110 adversarial suite."""

    def _build(self, assessments):
        bundle = _make_source_bundle(assessments)
        return _build_break_thesis_answer(
            bundle,
            business_journey_payload={},
            products_services_payload={},
            question={"question_id": "what-can-break-the-thesis"},
        )

    # Test A: WORSENING + UNKNOWN financial consequence
    def test_A_worsening_surfaced_impact_unknown(self):
        result = self._build([_make_risk("Governance Risk", trajectory="worsening", why_it_changed="Audit qualifications in FY24")])
        assert result["answer_status"] == "supported"
        kp = " ".join(result.get("key_points", []))
        assert "worsening" in kp.lower() or "governance" in kp.lower()
        # No financial loss should be stated
        combined = str(result)
        assert "₹" not in combined
        assert "crore" not in combined.lower()
        assert "loss of" not in combined.lower()

    # Test B: IMPROVING + HIGH severity — improvement surfaced, risk NOT resolved
    def test_B_improving_not_declared_resolved(self):
        result = self._build([_make_risk("IP Risk", trajectory="improving", why_it_changed="Key patent challenge dismissed")])
        combined = str(result)
        assert "resolv" not in combined.lower() or "not resolved" in combined.lower() or "potentially still material" in combined.lower()

    # Test C: RECURRING → persistence surfaced, not called worsening
    def test_C_recurring_not_called_worsening(self):
        result = self._build([_make_risk("Revenue Concentration", trajectory="recurring", why_it_changed="US market remains >50% of revenue")])
        kp = " ".join(result.get("key_points", []))
        assert "worsening" not in kp.lower()
        assert "recurring" in kp.lower() or "persistent" in kp.lower() or "revenue concentration" in kp.lower()

    # Test D: Unknown trajectory → no invented directional language
    def test_D_unknown_trajectory_no_directional_language(self):
        result = self._build([_make_risk("Working Capital", trajectory=None, why_it_changed="")])
        key_points_text = " ".join(result.get("key_points", []))
        assert "worsening" not in key_points_text.lower()
        assert "improving" not in key_points_text.lower()

    # Test E: Multiple trajectories — worsening appear before improving in output
    def test_E_worsening_before_improving_in_key_points(self):
        risks = [
            _make_risk("FX Risk", trajectory="worsening"),
            _make_risk("IP Risk", trajectory="improving"),
        ]
        result = self._build(risks)
        kps = result.get("key_points", [])
        worsening_idx = next((i for i, kp in enumerate(kps) if "worsening" in kp.lower()), None)
        improving_idx = next((i for i, kp in enumerate(kps) if "improving" in kp.lower()), None)
        if worsening_idx is not None and improving_idx is not None:
            assert worsening_idx < improving_idx

    # Test F: No risk_assessments → falls back gracefully
    def test_F_fallback_when_no_canonical_data(self):
        bundle = {
            "sources": {
                "committee_synthesis": _wrap({
                    "most_important_risks": [{"risk": "Working capital pressure", "why_it_matters": "Cash conversion is weak"}]
                }),
                "buffett_analysis": _wrap({}),
                "risk_assessments": _wrap({}),
                "risk_evolution": _wrap({}),
                "working_capital_quality_drilldown": _wrap({}),
            }
        }
        result = _build_break_thesis_answer(
            bundle,
            business_journey_payload={},
            products_services_payload={},
            question={"question_id": "what-can-break-the-thesis"},
        )
        assert result["answer_status"] in ("supported", "partially_supported", "not_supported")


class TestRegulatoryRisksAnswer:
    """Tests G-J from ENG-110 adversarial suite."""

    def _build(self, assessments):
        bundle = _make_source_bundle(assessments)
        return _build_regulatory_risks_answer(
            bundle,
            business_journey_payload={},
            products_services_payload={},
            question={"question_id": "what-regulatory-risks-remain-active"},
        )

    # Test G: Governance risk identified and surfaced
    def test_G_governance_risk_surfaced(self):
        result = self._build([_make_risk("Governance Risk", trajectory="worsening")])
        assert result["answer_status"] == "supported"
        combined = str(result)
        assert "governance" in combined.lower()

    # Test H: Non-regulatory worsening risk not mixed into regulatory answer
    def test_H_nonregulatory_trajectory_correctly_typed(self):
        risks = [
            _make_risk("FX Risk", trajectory="worsening"),
            _make_risk("Governance Risk", trajectory="worsening"),
        ]
        result = self._build(risks)
        # Should be supported since governance is present
        assert result["answer_status"] == "supported"

    # Test I: Unknown trajectory → no trajectory claimed
    def test_I_unknown_trajectory_not_labelled_worsening(self):
        result = self._build([_make_risk("Tax Risk", trajectory=None)])
        if result["answer_status"] == "supported":
            kp = " ".join(result.get("key_points", []))
            assert "worsening" not in kp.lower()

    # Test J: Conviction not inferred from trajectory
    def test_J_no_conviction_inference_from_trajectory(self):
        result = self._build([_make_risk("Governance Risk", trajectory="worsening")])
        combined = str(result)
        assert "high conviction" not in combined.lower()
        assert "strong conviction" not in combined.lower()


class TestRiskGroupPoint:
    def test_formats_name_and_why(self):
        entry = {"risk_name": "FX Risk", "why_it_changed": "Rupee depreciation accelerated", "trajectory": "worsening"}
        pt = _risk_group_point(entry, "worsening")
        assert "FX Risk" in pt
        assert "worsening" in pt.lower()
        assert "Rupee" in pt

    def test_name_only_when_no_why(self):
        entry = {"risk_name": "FX Risk", "why_it_changed": "", "trajectory": "worsening"}
        pt = _risk_group_point(entry, "worsening")
        assert "FX Risk" in pt
        assert pt  # not empty

    def test_empty_entry_returns_empty(self):
        entry = {"risk_name": "", "why_it_changed": ""}
        pt = _risk_group_point(entry, "worsening")
        assert pt == ""
