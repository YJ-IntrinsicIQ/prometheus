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


def test_generic_financial_services_description_rejected():
    payload = build_company_model("tanla", generated_at="2026-08-13T00:00:00Z")
    payload["current_business_model"].update(
        {
            "summary": "A financial services company serving retail customers.",
            "business_model_type": "financial_services",
            "what_company_does": "A financial services company serving retail customers.",
            "what_it_sells": ["financial services"],
            "who_pays": ["customers"],
            "how_revenue_happens": "The business earns revenue from customers.",
            "economic_mechanism": "The company serves customers and earns financial-services revenue over time.",
        }
    )
    payload["offerings"] = []

    validation = validate_company_model(payload)

    assert validation["status"] == "fail"
    assert any("specificity" in error for error in validation["errors"])


def test_company_name_padding_alone_is_not_specific_enough():
    payload = build_company_model("tanla", generated_at="2026-08-13T00:00:00Z")
    payload["current_business_model"].update(
        {
            "summary": "Tanla is a company.",
            "what_company_does": "Tanla is a company.",
            "what_it_sells": ["Tanla"],
            "who_pays": ["Tanla customers"],
            "how_revenue_happens": "Tanla earns revenue from customers.",
            "economic_mechanism": "Tanla operates a business.",
        }
    )
    payload["offerings"] = []

    validation = validate_company_model(payload)

    assert validation["status"] == "fail"
    assert any("specificity" in error for error in validation["errors"])


def test_specific_financial_services_description_accepted(tmp_path: Path):
    business_model = {
        "year": "fy25",
        "business_summary": "Retail financial-services institution focused on mass-market borrowers and underserved Indian customer segments.",
        "business_model": "Generates interest income from microfinance, secured retail, vehicle and MSME lending, funded by retail deposits and short-term borrowings, with fee and commission income from insurance and dealer financing.",
        "value_creation": "Uses branch, business-correspondent, dealer-partner and digital channels to underwrite, originate, service and collect loans while expanding customers into higher-ticket secured and MSME products.",
        "competitive_position_summary": "Distribution reach, underwriting discipline, deposit funding and collection infrastructure determine spread quality and credit-loss control.",
        "characteristics": [
            "Microfinance, retail secured lending and MSME working-capital products",
            "Branch-led and digital distribution model",
        ],
        "evidence_ids": ["ev_specific_financial_services"],
    }
    _write_json(
        tmp_path / "companies" / "acme_finance" / "company_memory" / "pcim_v1.json",
        _pcim_payload("acme_finance", business_model),
    )

    payload = build_company_model("acme_finance", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    validation = validate_company_model(payload)

    assert validation["status"] == "pass"
    assert payload["current_business_model"]["business_model_type"] == "financial_services"
    description = payload["current_business_model"]["what_company_does"].lower()
    assert "lending" in description
    assert "deposits" in description
    assert any("microfinance" in item["name"].lower() for item in payload["offerings"])
    assert any(item["billing_basis"] == "interest_spread" for item in payload["revenue_engines"])


def test_company_model_uses_richer_pcim_business_model_for_specific_description(tmp_path: Path):
    business_model = {
        "year": "fy26",
        "business_summary": "Global pharmaceutical company with a broad portfolio.",
        "business_model": "Develops, manufactures and commercializes branded and generic pharmaceutical products and biologics across global markets.",
        "value_creation": "Growth driven by product innovation, acquisition-led portfolio expansion, and manufacturing scale investments.",
        "competitive_position_summary": "Global regulated-market footprint and manufacturing quality emphasis.",
        "characteristics": [
            "Manufacturing scale investments",
            "Global regulated-market commercialization",
        ],
        "evidence_ids": ["ev_specific_business_model"],
    }
    _write_json(
        tmp_path / "companies" / "sun_pharma" / "company_memory" / "pcim_v1.json",
        _pcim_payload("sun_pharma", business_model),
    )

    payload = build_company_model("sun_pharma", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    validation = validate_company_model(payload)

    assert validation["status"] == "pass"
    assert "pharmaceutical" in payload["current_business_model"]["what_company_does"].lower()
    assert "manufacturing" in payload["current_business_model"]["what_company_does"].lower()
    assert "capacity" in payload["current_business_model"]["what_company_does"].lower()
    assert any("medicines" in item["name"].lower() for item in payload["offerings"])
    assert any("healthcare" in item["payer_type"].lower() for item in payload["customers"])


def test_multiple_business_segments_are_preserved_coherently(tmp_path: Path):
    business_model = {
        "year": "fy24",
        "business_summary": "A diversified business with software tools and managed services.",
        "business_model": "Sells workflow software to enterprises and managed services to support implementations.",
        "value_creation": "Creates value by combining recurring software usage with implementation services.",
        "competitive_position_summary": "Combines platform and services economics.",
        "characteristics": ["Recurring software usage", "Implementation services"],
        "evidence_ids": ["ev_multi_segment"],
    }
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json",
        _pcim_payload("acme", business_model),
    )

    payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    validation = validate_company_model(payload)

    assert validation["status"] == "pass"
    description = payload["current_business_model"]["what_company_does"].lower()
    assert "software" in description
    assert "services" in description
    assert payload["offerings"]
    assert payload["revenue_engines"]


def test_heterogeneous_real_company_models_generalize_without_company_branches():
    expected = {
        "tanla": "platform",
        "datapatterns": "manufacturing",
        "tips": "content_ip",
        "polymatech": "manufacturing",
        "ujjivan": "financial_services",
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
