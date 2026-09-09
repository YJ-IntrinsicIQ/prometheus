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


# ── Phase 12.1 — Company Model Longitudinal Propagation ─────────────────────


def _mp_item(item_id: str, theme: str, *, status: str = "partially_delivered", credibility: str = "PARTIALLY_DELIVERED", streams: list | None = None, linked: list | None = None, events: list | None = None) -> dict:
    return {
        "item_id": item_id,
        "theme": theme,
        "stream_types": streams if streams is not None else ["multi_source_longitudinal"],
        "current_status": status,
        "management_credibility_signal": credibility,
        "linked_company_model_ids": linked or [],
        "events": events or [
            {
                "event_id": f"{item_id}:ev1",
                "role": "completion",
                "event_type": "product_launch",
                "source_period": "fy25",
                "event_period": "fy25",
                "statement_text": "",
                "action_taken": f"[fy25 / EARNINGS_RELEASE] {theme} confirmed by operating evidence.",
                "verification_status": "partially_verified",
                "evidence": [
                    {
                        "source_artifact": "longitudinal/longitudinal_report.json",
                        "source_period": "fy25",
                        "evidence_id": f"er-chunk:fy25:{item_id[:12]}",
                        "source_item_id": item_id,
                        "field_path": "commitments[]",
                        "excerpt": f"{theme} confirmed.",
                    }
                ],
            }
        ],
    }


def _mp_payload(company: str, items: list) -> dict:
    return {
        "schema_version": "management_progression.v1",
        "company_slug": company,
        "generated_at": "2026-09-03T00:00:00Z",
        "coverage_status": "supported",
        "progression_items": items,
        "management_thesis_chains": [],
        "measurable_commitments": [],
        "contradiction_signals": [],
        "source_manifest": {
            "schema_version": "management_progression_manifest.v1",
            "company_slug": company,
            "generated_at": "2026-09-03T00:00:00Z",
            "coverage_status": "supported",
            "sources_used": ["longitudinal/longitudinal_report.json"],
            "sources_missing": [],
            "legacy_adapter_used": False,
            "legacy_adapter_sources": [],
            "company_mismatch_errors": [],
        },
    }


class TestPhase121LongitudinalCurrentState:
    """Phase 12.1 — longitudinal evidence enters Company Model via Management Progression."""

    def _make_company(self, tmp_path: Path, company: str, mp_items: list, pcim_model: dict | None = None) -> Path:
        root = tmp_path / "companies" / company
        _write_json(root / "company_memory" / "management_progression" / "management_progression.json", _mp_payload(company, mp_items))
        if pcim_model is not None:
            _write_json(root / "company_memory" / "pcim_v1.json", _pcim_payload(company, pcim_model))
        return root

    def _default_pcim(self) -> dict:
        return {
            "year": "fy25",
            "business_summary": "A specialised industrial sensor platform for machine monitoring.",
            "business_model": "Sells sensor software and monitoring services to industrial users and enterprises.",
            "value_creation": "Converts machine data into uptime alerts and recurring monitoring revenue.",
            "competitive_position_summary": "Manufacturing quality and platform integration.",
            "evidence_ids": ["ev_platform_base"],
        }

    def test_longitudinal_items_enter_company_model(self, tmp_path: Path):
        """Gate 1: longitudinal evidence enters Company Model via Management Progression."""
        self._make_company(tmp_path, "acme", [_mp_item("LC-X-FY25", "Platform Launch", status="partially_delivered", credibility="PARTIALLY_DELIVERED")], self._default_pcim())
        payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")

        lcs = payload.get("longitudinal_current_state", [])
        assert len(lcs) >= 1, "longitudinal_current_state must contain items when management_progression has longitudinal threads"
        assert lcs[0]["state_id"]
        assert lcs[0]["theme"] == "Platform Launch"
        assert lcs[0]["current_status"] == "partially_delivered"
        assert lcs[0]["evidence"], "each state must carry evidence reference"

    def test_management_claim_without_confirmation_is_not_confirmed(self, tmp_path: Path):
        """Gate 2: latest management claim alone does not become confirmed current state."""
        claimed_item = _mp_item("LC-CLAIM-FY26", "Revenue Growth Guidance", status="announced", credibility="UNABLE_TO_VERIFY")
        self._make_company(tmp_path, "acme", [claimed_item], self._default_pcim())
        payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")

        lcs = payload.get("longitudinal_current_state", [])
        claim_states = [s for s in lcs if s["theme"] == "Revenue Growth Guidance"]
        assert len(claim_states) == 1
        # Status must NOT be confirmed — it's only claimed/announced
        assert claim_states[0]["current_status"] not in {"confirmed_operational", "delivered", "verified"}
        # Confidence must be low when credibility is UNABLE_TO_VERIFY
        assert claim_states[0]["confidence"]["level"] == "low"

    def test_confirmed_current_state_preserved_with_high_confidence(self, tmp_path: Path):
        """Gate 3: confirmed lifecycle state is preserved with high confidence."""
        confirmed_item = _mp_item("LC-CONF-FY26", "Leadership Change", status="partially_delivered", credibility="CONFIRMED")
        self._make_company(tmp_path, "acme", [confirmed_item], self._default_pcim())
        payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")

        lcs = payload.get("longitudinal_current_state", [])
        confirmed_states = [s for s in lcs if s["theme"] == "Leadership Change"]
        assert len(confirmed_states) == 1
        assert confirmed_states[0]["confidence"]["level"] == "high"

    def test_future_target_does_not_become_current_confirmed_state(self, tmp_path: Path):
        """Gate 4: future management targets remain future — not promoted to confirmed current state."""
        future_item = _mp_item("LC-FUTURE-FY28", "Capacity Target FY28", status="announced", credibility="CLAIMED")
        future_item["events"][0]["event_period"] = "fy28"
        self._make_company(tmp_path, "acme", [future_item], self._default_pcim())
        payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")

        lcs = payload.get("longitudinal_current_state", [])
        future_states = [s for s in lcs if s["theme"] == "Capacity Target FY28"]
        assert len(future_states) == 1
        # Must remain announced, not delivered/confirmed
        assert future_states[0]["current_status"] == "announced"
        assert future_states[0]["confidence"]["level"] in {"low", "medium"}

    def test_unresolved_state_preserved_as_unresolved(self, tmp_path: Path):
        """Gate 7: unresolved state remains unresolved — unknown is not converted to confident assertion."""
        unresolved_item = _mp_item("LC-UNRES-FY26", "Market Share Growth", status="in_progress", credibility="UNABLE_TO_VERIFY")
        self._make_company(tmp_path, "acme", [unresolved_item], self._default_pcim())
        payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")

        lcs = payload.get("longitudinal_current_state", [])
        unresolved = [s for s in lcs if s["theme"] == "Market Share Growth"]
        assert len(unresolved) == 1
        # Confidence must not be high when credibility is unverified
        assert unresolved[0]["confidence"]["level"] in {"low", "medium"}

    def test_evidence_ids_preserved_in_state_entries(self, tmp_path: Path):
        """Gate 10: evidence IDs are preserved so Company Model state is traceable."""
        item = _mp_item("LC-EV-FY25", "International Expansion", status="partially_delivered", credibility="PARTIALLY_DELIVERED")
        self._make_company(tmp_path, "acme", [item], self._default_pcim())
        payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")

        lcs = payload.get("longitudinal_current_state", [])
        ev_states = [s for s in lcs if s["theme"] == "International Expansion"]
        assert len(ev_states) == 1
        ev = ev_states[0].get("evidence", [])
        assert ev, "evidence reference must be present"
        assert ev[0].get("source_artifact"), "source_artifact must be set"
        assert ev[0].get("evidence_id") or ev[0].get("source_artifact")  # provenance preserved

    def test_no_raw_source_chunk_in_state_evidence(self, tmp_path: Path):
        """Gate 11: no raw source-chunk leakage into Company Model longitudinal state."""
        item = _mp_item("LC-CHUNK-FY25", "Capital Allocation", status="partially_delivered", credibility="PARTIALLY_DELIVERED")
        # Inject a forbidden field into the underlying event evidence (simulating leakage attempt)
        item["events"][0]["evidence"][0]["source_chunk"] = "RAW_LEAK"
        self._make_company(tmp_path, "acme", [item], self._default_pcim())
        payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")

        lcs = payload.get("longitudinal_current_state", [])
        for state in lcs:
            for ev in state.get("evidence", []):
                assert "source_chunk" not in ev, "source_chunk must never leak into Company Model state evidence"
                assert "raw_text" not in ev
                assert "full_text" not in ev

    def test_company_model_does_not_duplicate_full_management_progression_events(self, tmp_path: Path):
        """Gate 12: Company Model must not include the full event list — that belongs to Management Progression."""
        item = _mp_item("LC-DUP-FY25", "Platform Launch", status="partially_delivered", credibility="PARTIALLY_DELIVERED")
        self._make_company(tmp_path, "acme", [item], self._default_pcim())
        payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")

        lcs = payload.get("longitudinal_current_state", [])
        for state in lcs:
            assert "events" not in state, "full events list must not appear in Company Model longitudinal_current_state"

    def test_abandoned_and_reversed_items_excluded(self, tmp_path: Path):
        """Abandoned and reversed threads must not appear in current state."""
        items = [
            _mp_item("LC-ABAND-FY24", "Old Strategy", status="abandoned", credibility="UNABLE_TO_VERIFY"),
            _mp_item("LC-REV-FY24", "Changed Position", status="reversed", credibility="UNABLE_TO_VERIFY"),
            _mp_item("LC-GOOD-FY25", "Active Theme", status="in_progress", credibility="PARTIALLY_DELIVERED"),
        ]
        self._make_company(tmp_path, "acme", items, self._default_pcim())
        payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")

        lcs = payload.get("longitudinal_current_state", [])
        themes = [s["theme"] for s in lcs]
        assert "Old Strategy" not in themes, "abandoned items must be excluded"
        assert "Changed Position" not in themes, "reversed items must be excluded"
        assert "Active Theme" in themes, "active items must be included"

    def test_non_longitudinal_mp_items_do_not_enter_longitudinal_current_state(self, tmp_path: Path):
        """Gate 12 corollary: annual-report-only MP items must not appear in longitudinal_current_state."""
        non_longitudinal = _mp_item("MP-PROJ-FY25", "Annual Report Project", status="in_progress", credibility="PARTIALLY_DELIVERED", streams=["project"])
        longitudinal = _mp_item("LC-LONG-FY25", "Longitudinal Theme", status="in_progress", credibility="PARTIALLY_DELIVERED", streams=["multi_source_longitudinal"])
        self._make_company(tmp_path, "acme", [non_longitudinal, longitudinal], self._default_pcim())
        payload = build_company_model("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")

        lcs = payload.get("longitudinal_current_state", [])
        themes = [s["theme"] for s in lcs]
        assert "Annual Report Project" not in themes, "non-longitudinal items must not appear in longitudinal_current_state"
        assert "Longitudinal Theme" in themes

    def test_validator_rejects_events_in_longitudinal_state(self):
        """Validator gate: Company Model must not duplicate full Management Progression event list."""
        payload = build_company_model("tanla", generated_at="2026-09-03T00:00:00Z")
        # Inject events into a state entry
        if payload.get("longitudinal_current_state"):
            payload["longitudinal_current_state"][0]["events"] = [{"event_id": "injected"}]
        else:
            payload["longitudinal_current_state"] = [
                {"state_id": "lcs-test", "theme": "Test", "current_status": "in_progress", "evidence": [], "events": [{"event_id": "injected"}]}
            ]
        validation = validate_company_model(payload)
        assert validation["status"] == "fail"
        assert any("events" in e and "Management Progression" in e for e in validation["errors"])

    def test_validator_rejects_source_chunk_in_evidence(self):
        """Validator gate: source_chunk must never appear in longitudinal state evidence."""
        payload = build_company_model("tanla", generated_at="2026-09-03T00:00:00Z")
        payload["longitudinal_current_state"] = [
            {
                "state_id": "lcs-leak",
                "theme": "Test",
                "current_status": "in_progress",
                "evidence": [{"source_artifact": "x.json", "source_chunk": "RAW TEXT"}],
            }
        ]
        validation = validate_company_model(payload)
        assert validation["status"] == "fail"
        assert any("source_chunk" in e for e in validation["errors"])

    def test_management_progression_source_in_manifest(self):
        """Gate 15/16: management_progression must appear in Company Model source manifest when available."""
        payload = build_company_model("tanla", generated_at="2026-09-03T00:00:00Z")
        sources_used = payload["source_manifest"]["sources_used"]
        assert any("management_progression" in s for s in sources_used)

    def test_tanla_production_regression(self):
        """Gate 13: Tanla production regression — Company Model must validate and include longitudinal state."""
        payload = build_company_model("tanla", generated_at="2026-09-03T00:00:00Z")
        validation = validate_company_model(payload)

        assert validation["status"] == "pass", validation["errors"]
        assert payload["company_slug"] == "tanla"
        assert payload["current_business_model"]["business_model_type"] == "platform"
        lcs = payload.get("longitudinal_current_state", [])
        assert len(lcs) >= 1, "Tanla must have longitudinal current state items from Phase 12 Management Progression"

    def test_datapatterns_production_regression(self):
        """Gate 14: Data Patterns production regression — Company Model must validate and include longitudinal state."""
        payload = build_company_model("datapatterns", generated_at="2026-09-03T00:00:00Z")
        validation = validate_company_model(payload)

        assert validation["status"] == "pass", validation["errors"]
        assert payload["company_slug"] == "datapatterns"
        assert payload["current_business_model"]["business_model_type"] == "manufacturing"
        lcs = payload.get("longitudinal_current_state", [])
        assert len(lcs) >= 1, "Data Patterns must have longitudinal current state items from Phase 12 Management Progression"
