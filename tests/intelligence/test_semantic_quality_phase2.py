from __future__ import annotations

from intelligence.capital_allocation_outcomes.validators import validate_capital_allocation_outcomes_payload
from intelligence.capacity.classifier import has_bounded_capacity_signals
from intelligence.management_commentary.builder import is_management_commentary
from intelligence.projects.classifier import is_bounded_project_candidate
from intelligence.risks.validators import validate_risk_payload
from knowledge.company_memory.guardrails import classify_actor, classify_statement_type, validate_lineage


def test_company_target_is_commitment_eligible_semantics():
    text = "We will expand the Chennai manufacturing facility by FY25."
    assert classify_actor(text)["actor_type"] == "company_management"
    assert classify_statement_type(text)["statement_type"] == "planned_action"


def test_government_target_and_industry_forecast_are_external():
    government = "The Government of India targets defence production of USD 25 billion."
    forecast = "The defence industry is projected to grow at a 13% CAGR."
    assert classify_actor(government)["actor_type"] == "government"
    assert classify_statement_type(government)["statement_type"] == "external_target"
    assert classify_actor(forecast)["actor_type"] == "industry"
    assert classify_statement_type(forecast)["statement_type"] == "forecast"


def test_existing_capability_and_csr_are_not_commitments():
    assert classify_statement_type("The company possesses an in-house EMS manufacturing line.")["statement_type"] == "existing_capability"
    assert classify_statement_type("The company completed a CSR classroom project.")["statement_type"] == "CSR_activity"


def test_csr_and_historical_products_are_not_projects():
    assert not is_bounded_project_candidate(
        {"project_name": "School classroom building", "timeline": "FY25", "status": "completed"}, source_kind="project"
    )
    assert not is_bounded_project_candidate(
        {"project_name": "Avionics Suite Tester", "status": "manufactured"}, source_kind="project"
    )


def test_productive_capacity_required():
    assert has_bounded_capacity_signals(
        {"capacity_type": "New EMS line", "status": "installed", "target_capacity": "100 units/day"}, source_kind="capacity"
    )
    assert not has_bounded_capacity_signals(
        {"capacity_type": "student capacity", "status": "expanded", "target_capacity": "260 students"}, source_kind="capacity"
    )
    assert not has_bounded_capacity_signals(
        {"capacity_type": "scalable capacity", "status": "available"}, source_kind="capacity"
    )


def test_management_thought_is_distinct_from_corporate_fact():
    assert is_management_commentary("Management attributed higher debt to temporary working-capital needs.", actor="management")
    assert not is_management_commentary("The scheme of amalgamation was approved.", actor="company")
    assert is_management_commentary("Management said the amalgamation will simplify the structure and improve efficiency.", actor="management")


def test_zero_risk_output_fails_when_material_evidence_exists():
    result = validate_risk_payload({"risks": []}, {"timelines": []}, {"assessments": []}, upstream_material_evidence_count=2)
    assert result["status"] == "fail"
    assert any(issue["rule"] == "material_evidence_zero_output" for issue in result["issues"])


def test_zero_allocation_output_fails_when_material_evidence_exists():
    result = validate_capital_allocation_outcomes_payload(
        {"allocations": []}, timelines_payload={"timelines": []}, assessments_payload={"assessments": []}, upstream_material_evidence_count=2
    )
    assert result["status"] == "fail"
    assert any(issue["code"] == "material_evidence_zero_output" for issue in result["issues"])


def test_stale_lineage_fails_and_current_lineage_passes():
    stale = validate_lineage(
        artifact_generated_at="2026-08-09T09:00:00Z",
        dependencies=[{"name": "projects", "generated_at": "2026-08-09T10:00:00Z"}],
    )
    current = validate_lineage(
        artifact_generated_at="2026-08-09T11:00:00Z",
        dependencies=[{"name": "projects", "generated_at": "2026-08-09T10:00:00Z"}],
    )
    assert stale["status"] == "fail"
    assert current["status"] == "pass"
