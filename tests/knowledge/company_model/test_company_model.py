from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge.company_model import build_company_model, validate_company_model, write_company_model


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _pcim_payload(company: str, business_model: dict) -> dict:
    return {
        "contract_version": "pcim.v1",
        "company": company,
        "business_understanding": {
            "latest_business_view": {"business_model": business_model},
            "business_model_by_year": [business_model],
        },
    }


def test_company_model_contract_preserves_evidence_for_real_company():
    payload = build_company_model("tanla", generated_at="2026-08-13T00:00:00Z")
    validation = validate_company_model(payload)

    assert validation["status"] == "pass"
    assert payload["schema_version"] == "company_model.v1"
    assert payload["company_slug"] == "tanla"
    assert payload["current_business_model"]["business_model_type"] == "platform"
    assert payload["current_business_model"]["evidence"]
    assert payload["source_manifest"]["legacy_adapter_used"] is True
    assert "company_memory/pcim_v1.json" in payload["source_manifest"]["sources_used"]


def test_company_model_rejects_cross_company_source_identity(tmp_path: Path):
    _write_json(
        tmp_path / "companies" / "tanla" / "company_memory" / "pcim_v1.json",
        _pcim_payload(
            "datapatterns",
            {
                "year": "fy24",
                "business_summary": "Data Patterns manufactures defence electronics systems.",
                "business_model": "Project delivery for defence aerospace customers.",
                "value_creation": "Engineering and manufacturing capacity convert orders into delivered systems.",
            },
        ),
    )

    payload = build_company_model("tanla", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    validation = validate_company_model(payload)

    assert validation["status"] == "fail"
    assert "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION" in " ".join(validation["errors"])
    with pytest.raises(ValueError):
        write_company_model("tanla", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")


def test_insufficient_evidence_state_is_valid_when_sources_missing(tmp_path: Path):
    payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    validation = validate_company_model(payload)

    assert payload["coverage_status"] == "insufficient_evidence"
    assert validation["status"] == "pass"
    assert payload["uncertainties"][0]["blocking"] is True


def test_missing_optional_customer_detail_can_remain_partial(tmp_path: Path):
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json",
        _pcim_payload(
            "acme",
            {
                "year": "fy24",
                "business_summary": "Acme operates a specialised industrial sensor platform for machine monitoring.",
                "business_model": "The platform sells sensor software and monitoring services, but customer concentration is not disclosed.",
                "value_creation": "It converts machine data into uptime alerts and recurring monitoring revenue for industrial users.",
                "evidence_ids": ["ev_acme_business"],
            },
        ),
    )

    payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    validation = validate_company_model(payload)

    assert payload["coverage_status"] in {"supported", "partial"}
    assert validation["status"] in {"pass", "warning"}
    assert any(item["uncertainty_id"] == "customer_concentration_unknown" for item in payload["uncertainties"])


def test_contradictory_business_and_revenue_model_fails_validation():
    payload = build_company_model("tanla", generated_at="2026-08-13T00:00:00Z")
    payload["revenue_engines"] = [
        {
            "engine_id": "bad_milestone",
            "description": "Project delivery revenue from manufacturing sale milestones",
            "billing_basis": "milestone",
            "evidence": payload["current_business_model"]["evidence"],
        }
    ]

    validation = validate_company_model(payload)

    assert validation["status"] == "fail"
    assert any("platform business" in error for error in validation["errors"])


def test_generic_output_specificity_failure():
    payload = build_company_model("tanla", generated_at="2026-08-13T00:00:00Z")
    payload["current_business_model"].update(
        {
            "summary": "Management is focused on growth and operational efficiency.",
            "what_company_does": "Management is focused on growth and operational efficiency.",
            "what_it_sells": ["solutions"],
            "who_pays": ["customers"],
            "how_revenue_happens": "The company earns revenue from customers.",
            "economic_mechanism": "The company improves performance over time.",
        }
    )
    payload["offerings"] = []

    validation = validate_company_model(payload)

    assert validation["status"] == "fail"
    assert any("generic" in error or "specificity" in error for error in validation["errors"])


def test_heterogeneous_real_company_models_generalize_without_company_branches():
    expected = {
        "tanla": "platform",
        "datapatterns": "manufacturing",
        "tips": "content_ip",
        "polymatech": "manufacturing",
    }

    for company, model_type in expected.items():
        payload = build_company_model(company, generated_at="2026-08-13T00:00:00Z")
        validation = validate_company_model(payload)
        assert validation["status"] == "pass", (company, validation)
        assert payload["current_business_model"]["business_model_type"] == model_type
        assert payload["offerings"], company
        assert payload["customers"], company
        assert payload["revenue_engines"], company


def test_no_company_specific_production_branches():
    producer_source = Path("knowledge/company_model/producer.py").read_text(encoding="utf-8")

    assert 'company == "' not in producer_source
    assert "company_slug == " not in producer_source

