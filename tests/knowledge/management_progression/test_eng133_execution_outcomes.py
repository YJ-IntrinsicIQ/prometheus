from __future__ import annotations

import pytest

from knowledge.management_progression.synthesis import build_execution_outcome_summary


def _item(
    status: str,
    *,
    current: str = "in_progress",
    completed: bool = False,
    outcome: str | None = None,
    direction: str = "unknown",
    financial_link: str = "not_yet_visible",
    metric: bool = False,
    stream: str = "project",
):
    return {
        "item_id": f"MP-{status}-{current}-{stream}",
        "theme": "Named operating initiative",
        "stream_types": [stream],
        "current_status": current,
        "synthesis_chain": {
            "chain_status": status,
            "claim": {"text": "Management stated a specific initiative", "period": "fy22", "evidence_ids": ["claim-1"]},
            "action": None
            if status == "CLAIM_ONLY"
            else {
                "text": "The company commissioned the named initiative" if completed else "The company began the named initiative",
                "period": "fy23",
                "completed": completed,
                "actor": "company",
                "action_actor": "company",
                "evidence_ids": ["action-1"],
            },
            "outcome": None
            if outcome is None
            else {"text": outcome, "period": "fy24", "direction": direction, "evidence_ids": ["outcome-1"]},
            "financial_consequence": {
                "link_status": financial_link,
                "basis": "Test evidence",
                "metrics_observed": [{"metric_id": "revenue"}] if metric else [],
            },
            "investor_implication": {"conclusion": "Evidence-bounded conclusion."},
        },
    }


@pytest.mark.parametrize(
    ("item", "execution", "outcome", "attribution"),
    [
        (_item("CLAIM_ONLY", current="announced"), "ANNOUNCED", "OUTCOME_UNKNOWN", "NO_OUTCOME_EVIDENCE"),
        (_item("ACTION_STARTED"), "ACTION_STARTED", "OUTCOME_NOT_YET_OBSERVED", "NO_OUTCOME_EVIDENCE"),
        (_item("PARTIAL_EXECUTION"), "PARTIAL_EXECUTION", "OUTCOME_NOT_YET_OBSERVED", "NO_OUTCOME_EVIDENCE"),
        (_item("ACTION_COMPLETED", current="delivered", completed=True), "ACTION_COMPLETED", "OUTCOME_NOT_DISCLOSED", "NO_OUTCOME_EVIDENCE"),
        (_item("OUTCOME_POSITIVE", current="delivered", completed=True, outcome="Utilisation rose to 80%", direction="positive"), "ACTION_COMPLETED", "OUTCOME_OBSERVED", "ASSOCIATED_NOT_ATTRIBUTABLE"),
        (_item("EARLY_OPERATING_SIGNAL", completed=True, outcome="Initial utilisation ramp is visible"), "ACTION_COMPLETED", "PARTIAL_OUTCOME", "ASSOCIATED_NOT_ATTRIBUTABLE"),
        (_item("FINANCIAL_LINK_UNPROVEN", completed=True, outcome="Revenue rose later", direction="positive", financial_link="unproven", metric=True), "ACTION_COMPLETED", "OUTCOME_OBSERVED", "ASSOCIATED_NOT_ATTRIBUTABLE"),
        (_item("FINANCIAL_IMPACT_CONFIRMED", current="delivered", completed=True, outcome="The initiative contributed ₹10 crore revenue", direction="positive", financial_link="confirmed", metric=True), "ACTION_COMPLETED", "OUTCOME_OBSERVED", "DIRECTLY_ATTRIBUTABLE"),
        (_item("OUTCOME_NEGATIVE", current="failed", outcome="The rollout failed", direction="negative"), "FAILED_OR_ABANDONED", "NEGATIVE_OUTCOME", "NEGATIVE_OUTCOME"),
    ],
)
def test_execution_outcome_semantics(item, execution, outcome, attribution):
    record = build_execution_outcome_summary([item])["records"][0]
    assert record["execution_state"] == execution
    assert record["outcome_state"] == outcome
    assert record["attribution_strength"] == attribution


def test_completed_acquisition_is_not_value_creation():
    item = _item("ACTION_COMPLETED", current="delivered", completed=True, stream="capital_allocation")
    item["theme"] = "Completed acquisition of a named business"
    record = build_execution_outcome_summary([item])["records"][0]
    assert record["execution_state"] == "ACTION_COMPLETED"
    assert record["outcome_state"] == "OUTCOME_NOT_DISCLOSED"
    assert record["attribution_strength"] == "NO_OUTCOME_EVIDENCE"
    assert record["credibility_evidence"]["economic_proof"] == "UNPROVEN"


def test_busy_management_does_not_become_proven_without_outcomes():
    items = [
        _item("ACTION_COMPLETED", current="delivered", completed=True, stream=f"project-{index}")
        for index in range(6)
    ]
    summary = build_execution_outcome_summary(items)
    assert summary["coverage"]["execution_completed_or_operational"] == 6
    assert summary["coverage"]["operating_outcome_observed"] == 0
    assert summary["coverage"]["economic_consequence_attributable"] == 0
    assert summary["credibility"]["economic_proof"] == "UNPROVEN"


def test_management_remediation_execution_does_not_prove_effectiveness():
    item = _item("ACTION_COMPLETED", current="delivered", completed=True, stream="risk_response")
    item["theme"] = "Governance remediation programme"
    record = build_execution_outcome_summary([item])["records"][0]
    assert record["outcome_state"] == "OUTCOME_NOT_DISCLOSED"
    assert "post-execution operating outcome" in record["unresolved_gap"]


def test_strategic_intent_action_is_visible_but_not_reclassified_as_promise():
    item = _item("ACTION_STARTED", stream="strategy")
    record = build_execution_outcome_summary([item])["records"][0]
    assert record["stream_types"] == ["strategy"]
    assert "commitment" not in record
    assert record["credibility_evidence"]["follow_through"] == "PARTIALLY_PROVEN"


def test_evidence_and_identity_are_preserved_without_cross_item_matching():
    first = _item("ACTION_STARTED", stream="project-a")
    first["item_id"] = "MP-FIRST"
    second = _item("ACTION_COMPLETED", current="delivered", completed=True, stream="project-b")
    second["item_id"] = "MP-SECOND"
    records = build_execution_outcome_summary([first, second])["records"]
    assert [record["initiative_id"] for record in records] == ["MP-FIRST", "MP-SECOND"]
    assert records[0]["execution_state"] == "ACTION_STARTED"
    assert records[1]["execution_state"] == "ACTION_COMPLETED"
    assert records[0]["evidence_ids"] == ["claim-1", "action-1"]


def test_regulator_activity_does_not_credit_management_execution():
    item = _item("OUTCOME_UNKNOWN")
    item["synthesis_chain"]["action"]["actor"] = "regulator"
    item["synthesis_chain"]["action"]["action_actor"] = "regulator"
    item["synthesis_chain"]["action"]["text"] = "The regulator imposed an import alert"
    summary = build_execution_outcome_summary([item])
    assert summary["records"][0]["management_execution_eligible"] is False
    assert summary["coverage"]["action_observed"] == 0
    assert summary["coverage"]["external_actor_events_excluded"] == 1
    assert summary["credibility"]["follow_through"] == "UNPROVEN"
