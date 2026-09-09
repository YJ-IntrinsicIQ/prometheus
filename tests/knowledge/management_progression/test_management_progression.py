from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge.management_progression import (
    build_management_progression,
    validate_management_progression,
    write_management_progression,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _company_model(company: str) -> dict:
    return {
        "schema_version": "company_model.v1",
        "company_slug": company,
        "coverage_status": "supported",
        "offerings": [
            {
                "offering_id": "enterprise_platform",
                "name": "Enterprise messaging platform",
                "description": "Enterprise messaging and communication workflows",
            }
        ],
        "revenue_engines": [
            {
                "engine_id": "platform_usage",
                "description": "Usage-linked platform revenue from enterprise messaging",
            }
        ],
        "source_manifest": {"company_slug": company},
    }


def test_management_progression_contract_for_real_company():
    payload = build_management_progression("tanla", generated_at="2026-08-13T00:00:00Z")
    validation = validate_management_progression(payload)

    assert validation["status"] == "pass"
    assert payload["schema_version"] == "management_progression.v1"
    assert payload["company_slug"] == "tanla"
    assert payload["progression_items"]
    assert payload["source_manifest"]["legacy_adapter_used"] is True
    first_event = payload["progression_items"][0]["events"][0]
    assert first_event["source_period"]
    assert first_event["role"] in {"statement", "commitment", "action", "milestone", "completion", "outcome"}
    assert first_event["evidence"]


def test_cross_company_source_identity_fails(tmp_path: Path):
    _write_json(tmp_path / "companies" / "tanla" / "company_memory" / "company_model" / "company_model.json", _company_model("datapatterns"))

    payload = build_management_progression("tanla", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    validation = validate_management_progression(payload)

    assert validation["status"] == "fail"
    assert "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION" in " ".join(validation["errors"])
    with pytest.raises(ValueError):
        write_management_progression("tanla", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")


def test_insufficient_evidence_state_is_valid(tmp_path: Path):
    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    validation = validate_management_progression(payload)

    assert payload["coverage_status"] == "insufficient_evidence"
    assert payload["progression_items"] == []
    assert validation["status"] == "pass"


def test_chronology_preserves_source_event_target_and_resolved_periods(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "projects" / "projects_registry.json",
        {
            "company": "acme",
            "projects": [
                {
                    "project_id": "PJ-1",
                    "project_name": "Enterprise messaging platform rollout",
                    "description": "Enterprise messaging platform rollout for operator customers",
                    "announcement_period": "fy22",
                    "target_period": "fy24",
                    "assessment": {
                        "execution_status": "under_execution",
                        "period": "fy23",
                        "latest_period": "fy24",
                        "observed_business_effect": "Customer rollout evidence is still partial.",
                    },
                    "evidence_ids": ["ev_project"],
                }
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    event = payload["progression_items"][0]["events"][0]

    assert event["source_period"] == "fy22"
    assert event["event_period"] == "fy22"
    assert event["verification_status"] == "partially_verified"


def test_multi_source_longitudinal_feeds_management_progression(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "longitudinal" / "longitudinal_report.json",
        {
            "schema_version": "9.0",
            "company": "acme",
            "source_periods": ["Q4 FY26", "FY27"],
            "source_families_present": ["EARNINGS_CALL_TRANSCRIPT", "EXCHANGE_DISCLOSURE"],
            "commitment_count": 1,
            "lifecycle_counts": {"CONFIRMED": 1},
            "commitments": [
                {
                    "commitment_id": "LC-PLATFORM-FY27",
                    "theme_slug": "platform_launch",
                    "theme_label": "Customer messaging platform launch",
                    "claim_domain": "COMMITMENT",
                    "lifecycle": "CONFIRMED",
                    "claimed_period": "Q4 FY26",
                    "claimed_by": "Chief Executive Officer",
                    "claimed_source": "TRANSCRIPT",
                    "claimed_text": "Management expects to launch a customer messaging platform by Q2 FY27.",
                    "confirmed_period": "FY27",
                    "confirmed_source": "EXCHANGE_DISCLOSURE",
                    "confirmed_text": "The customer messaging platform was launched for enterprise customers.",
                    "evidence": [
                        {
                            "evidence_id": "call-1",
                            "source_period": "Q4 FY26",
                            "source_type": "EARNINGS_CALL_TRANSCRIPT",
                            "claim_domain": "COMMITMENT",
                            "speaker_role": "MANAGEMENT",
                            "speaker": "CEO",
                            "target_period": "Q2 FY27",
                            "text": "Management expects to launch a customer messaging platform by Q2 FY27.",
                        },
                        {
                            "evidence_id": "filing-1",
                            "source_period": "FY27",
                            "source_type": "EXCHANGE_DISCLOSURE",
                            "claim_domain": "FACTUAL_EVENT",
                            "speaker": "company",
                            "text": "The customer messaging platform was launched for enterprise customers.",
                        },
                    ],
                }
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")
    validation = validate_management_progression(payload)
    events = [event for item in payload["progression_items"] for event in item["events"]]

    assert validation["status"] == "pass"
    assert "longitudinal/longitudinal_report.json" in payload["source_manifest"]["sources_used"]
    assert any(event["source_period"] == "Q4 FY26" and event["target_period"] == "Q2 FY27" for event in events)
    assert any(event["role"] == "completion" and event["event_period"] == "FY27" for event in events)
    assert all(event["evidence"][0]["source_artifact"] == "longitudinal/longitudinal_report.json" for event in events)


def test_multi_source_unproven_commitment_stays_unresolved(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "longitudinal" / "longitudinal_report.json",
        {
            "schema_version": "9.0",
            "company": "acme",
            "commitments": [
                {
                    "commitment_id": "LC-GTM-FY26",
                    "theme_slug": "gtm_investment",
                    "theme_label": "GTM investment",
                    "claim_domain": "STRATEGIC_PRIORITY",
                    "lifecycle": "UNPROVEN",
                    "claimed_period": "Q4 FY26",
                    "claimed_by": "CFO",
                    "claimed_source": "TRANSCRIPT",
                    "claimed_text": "Management is investing in GTM and expects benefits in coming quarters.",
                    "unproven_reason": "No later source confirms operating or financial payoff.",
                    "evidence": [
                        {
                            "evidence_id": "call-gtm",
                            "source_period": "Q4 FY26",
                            "source_type": "EARNINGS_CALL_TRANSCRIPT",
                            "claim_domain": "STRATEGIC_PRIORITY",
                            "speaker_role": "MANAGEMENT",
                            "text": "Management is investing in GTM and expects benefits in coming quarters.",
                        }
                    ],
                }
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")
    item = payload["progression_items"][0]
    event = item["events"][0]

    assert item["current_status"] == "announced"
    assert event["verification_status"] == "unresolved"
    assert item["investor_implication"]["thesis_impact"] == "unresolved"
    assert item["unresolved"]


def test_multi_source_financial_consequence_is_distinct_from_claim(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "longitudinal" / "longitudinal_report.json",
        {
            "schema_version": "9.0",
            "company": "acme",
            "commitments": [
                {
                    "commitment_id": "LC-MARGIN-FY26",
                    "theme_slug": "profitability",
                    "theme_label": "Margin improvement programme",
                    "claim_domain": "FINANCIAL_METRIC",
                    "lifecycle": "PROGRESSING",
                    "claimed_period": "FY25",
                    "claimed_source": "ANNUAL_REPORT",
                    "claimed_text": "Management described a margin improvement programme for enterprise products.",
                    "financial_consequence": "[Q1 FY27 / EARNINGS_RELEASE] Gross margin improved as enterprise product mix improved.",
                    "evidence": [
                        {
                            "evidence_id": "annual-margin",
                            "source_period": "FY25",
                            "source_type": "ANNUAL_REPORT",
                            "claim_domain": "STRATEGIC_PRIORITY",
                            "speaker": "company",
                            "text": "Management described a margin improvement programme for enterprise products.",
                        },
                        {
                            "evidence_id": "release-margin",
                            "source_period": "Q1 FY27",
                            "source_type": "EARNINGS_RELEASE",
                            "claim_domain": "FINANCIAL_METRIC",
                            "speaker": "company",
                            "text": "Gross margin improved as enterprise product mix improved.",
                        },
                    ],
                }
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-09-03T00:00:00Z")
    events = [event for item in payload["progression_items"] for event in item["events"]]

    assert {event["role"] for event in events} == {"statement", "outcome"}
    outcome = [event for event in events if event["role"] == "outcome"][0]
    assert outcome["event_type"] == "financial_outcome"
    assert outcome["source_period"] == "Q1 FY27"
    assert outcome["evidence"][0]["evidence_id"] == "release-margin"


def test_distinct_statement_action_and_outcome_events_are_not_collapsed(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "management_commitments" / "management_commitments.json",
        {
            "company": "acme",
            "commitments": [
                {
                    "commitment_id": "C-1",
                    "normalized_commitment": "launch enterprise messaging platform",
                    "first_seen_period": "fy22",
                    "latest_status": "UNKNOWN",
                    "evidence_ids": ["ev_commitment"],
                }
            ],
        },
    )
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "capital_allocation_outcomes" / "capital_allocation_outcomes.json",
        {
            "company": "acme",
            "allocations": [
                {
                    "allocation_id": "A-1",
                    "allocation_name": "Platform product investment",
                    "deployment_periods": ["fy23"],
                    "financial_outcome": "Revenue impact remains unproven.",
                    "evidence_ids": ["ev_allocation"],
                }
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    events = [event for item in payload["progression_items"] for event in item["events"]]

    assert {event["role"] for event in events} >= {"commitment", "outcome"}
    assert len(events) == 2


def test_duplicate_events_are_not_repeated(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "projects" / "projects_registry.json",
        {
            "company": "acme",
            "projects": [
                {
                    "project_id": "PJ-GOVERNED",
                    "description": "Enterprise messaging platform customer rollout",
                    "announcement_period": "fy22",
                    "assessment": {"execution_status": "under_execution"},
                    "evidence_ids": ["ev_project"],
                }
            ],
        },
    )
    duplicate = {
        "value": "Enterprise messaging platform rollout",
        "source_item_id": "INIT-1",
        "normalized_status": "completed",
        "evidence_ids": ["ev_same"],
    }
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "strategy_timeline.json",
        {"company": "acme", "timeline": [{"year": "fy22", "management_focus": [duplicate, dict(duplicate)]}]},
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    events = [event for item in payload["progression_items"] for event in item["events"]]
    legacy_events = [event for event in events if event["evidence"][0]["source_artifact"].endswith("strategy_timeline.json")]

    assert len(legacy_events) == 1
    assert validate_management_progression(payload)["status"] == "pass"


def test_generic_legacy_strategy_bucket_is_not_promoted(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "projects" / "projects_registry.json",
        {
            "company": "acme",
            "projects": [
                {
                    "project_id": "PJ-GOVERNED",
                    "description": "Enterprise messaging platform customer rollout",
                    "announcement_period": "fy24",
                    "assessment": {"execution_status": "under_execution"},
                    "evidence_ids": ["ev_project"],
                }
            ],
        },
    )
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "multi_year" / "strategy_timeline.json",
        {
            "company": "acme",
            "timeline": [
                {
                    "year": "fy24",
                    "management_focus": [
                        {"value": "Technology direction", "source_item_id": "GENERIC-1"},
                        {
                            "value": "Enterprise messaging platform rollout",
                            "source_item_id": "SPECIFIC-1",
                            "normalized_status": "completed",
                            "evidence_ids": ["ev_specific"],
                        },
                    ],
                }
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    texts = " ".join(item["theme"] for item in payload["progression_items"])

    assert "Technology direction" not in texts
    assert "Enterprise messaging platform" in texts


def test_statement_is_not_promoted_to_verified_outcome():
    payload = build_management_progression("tanla", generated_at="2026-08-13T00:00:00Z")
    event = payload["progression_items"][0]["events"][0]
    event["role"] = "commitment"
    event["verification_status"] = "verified"

    validation = validate_management_progression(payload)

    assert validation["status"] == "fail"
    assert any("cannot be verified outcome" in error for error in validation["errors"])


def test_company_model_links_are_created_when_specific_overlap_exists(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "management_commitments" / "management_commitments.json",
        {
            "company": "acme",
            "commitments": [
                {
                    "commitment_id": "C-1",
                    "normalized_commitment": "launch enterprise messaging platform",
                    "first_seen_period": "fy22",
                    "latest_status": "UNKNOWN",
                    "evidence_ids": ["ev_commitment"],
                }
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")

    assert payload["progression_items"][0]["linked_company_model_ids"]


def test_generic_wrapper_is_stripped_while_named_project_survives(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "projects" / "projects_registry.json",
        {
            "company": "acme",
            "projects": [
                {
                    "project_id": "PJ-WISELY",
                    "description": "Advance execution on a bounded business objective to deliver Wisely ATP anti-phishing platform for enterprise messaging customers.",
                    "announcement_period": "fy24",
                    "assessment": {
                        "execution_status": "under_execution",
                        "observed_business_effect": "Customer adoption remains unproven.",
                        "observed_financial_effect": "Financial returns remain unproven.",
                    },
                    "evidence_ids": ["ev_wisely"],
                }
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    text = " ".join(item["theme"] for item in payload["progression_items"])

    assert "Wisely ATP anti-phishing platform" in text
    assert "Advance execution on a bounded business objective" not in text
    assert validate_management_progression(payload)["status"] == "pass"


def test_generic_strategy_language_without_specific_anchor_is_excluded(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "projects" / "projects_registry.json",
        {
            "company": "acme",
            "projects": [
                {
                    "project_id": "PJ-GENERIC",
                    "description": "Improve operating capability, control, or speed",
                    "announcement_period": "fy24",
                    "assessment": {"execution_status": "under_execution"},
                    "evidence_ids": ["ev_generic"],
                }
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")

    assert payload["coverage_status"] == "insufficient_evidence"
    assert payload["progression_items"] == []


def test_unrelated_similar_wrapped_initiatives_remain_separate(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "projects" / "projects_registry.json",
        {
            "company": "acme",
            "projects": [
                {
                    "project_id": "PJ-ATP",
                    "description": "Improve operating capability, control, or speed to deliver Wisely ATP anti-phishing product for enterprises.",
                    "announcement_period": "fy24",
                    "assessment": {"execution_status": "under_execution", "observed_business_effect": "Adoption remains unproven."},
                    "evidence_ids": ["ev_atp"],
                },
                {
                    "project_id": "PJ-GENAI",
                    "description": "Improve operating capability, control, or speed to deliver GenAI conversational commerce platform for enterprises.",
                    "announcement_period": "fy25",
                    "assessment": {"execution_status": "under_execution", "observed_business_effect": "Adoption remains unproven."},
                    "evidence_ids": ["ev_genai"],
                },
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    themes = [item["theme"] for item in payload["progression_items"]]

    assert len(themes) == 2
    assert any("Wisely ATP" in theme for theme in themes)
    assert any("GenAI conversational commerce" in theme for theme in themes)


def test_material_named_initiative_ranks_above_low_value_cwip_noise(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "projects" / "projects_registry.json",
        {
            "company": "acme",
            "projects": [
                {
                    "project_id": "PJ-CWIP",
                    "description": "Support execution capacity and delivery readiness to deliver CWIP line item 'Furniture and Fixtures'.",
                    "announcement_period": "fy24",
                    "assessment": {"execution_status": "under_execution", "observed_financial_effect": "No direct financial effect is established."},
                    "evidence_ids": ["ev_cwip"],
                },
                {
                    "project_id": "PJ-FACILITY",
                    "description": "Support execution capacity and delivery readiness to deliver satellite integration testing facility for defence programmes.",
                    "announcement_period": "fy24",
                    "assessment": {
                        "execution_status": "under_execution",
                        "observed_business_effect": "Utilization and incremental returns remain unproven.",
                    },
                    "evidence_ids": ["ev_facility"],
                },
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    themes = [item["theme"] for item in payload["progression_items"]]

    assert themes[0].startswith("satellite integration testing facility")
    assert not any("Furniture and Fixtures" in theme for theme in themes)


def test_missing_later_evidence_stays_unresolved(tmp_path: Path):
    _write_json(tmp_path / "companies" / "acme" / "company_memory" / "company_model" / "company_model.json", _company_model("acme"))
    _write_json(
        tmp_path / "companies" / "acme" / "company_memory" / "projects" / "projects_registry.json",
        {
            "company": "acme",
            "projects": [
                {
                    "project_id": "PJ-PLATFORM",
                    "description": "Enterprise messaging platform rollout for operator customers.",
                    "announcement_period": "fy24",
                    "assessment": {"execution_status": "under_execution"},
                    "evidence_ids": ["ev_platform"],
                }
            ],
        },
    )

    payload = build_management_progression("acme", companies_root=tmp_path / "companies", generated_at="2026-08-13T00:00:00Z")
    item = payload["progression_items"][0]

    assert item["current_status"] == "in_progress"
    assert item["management_credibility_signal"] == "IN_PROGRESS"
    assert item["investor_implication"]["thesis_impact"] == "unresolved"
    assert item["unresolved"]


def test_heterogeneous_real_companies_build_without_company_branches():
    expected_minimum = {
        "tanla": "supported",
        "datapatterns": "supported",
        "tips": "insufficient_evidence",
    }
    for company, coverage in expected_minimum.items():
        payload = build_management_progression(company, generated_at="2026-08-13T00:00:00Z")
        validation = validate_management_progression(payload)
        assert validation["status"] == "pass", (company, validation)
        assert payload["coverage_status"] == coverage


def test_legacy_only_progression_is_insufficient_until_governed_stream_exists():
    payload = build_management_progression("tips", generated_at="2026-08-13T00:00:00Z")

    assert payload["coverage_status"] == "insufficient_evidence"
    assert payload["progression_items"] == []


def test_no_company_specific_production_branches():
    producer_source = Path("knowledge/management_progression/producer.py").read_text(encoding="utf-8")

    assert 'company == "' not in producer_source
    assert "company_slug == " not in producer_source
