import json
from pathlib import Path

import pytest

from intelligence.ask_intrinsiciq.answer_cards import build_answer_cards
from intelligence.ask_intrinsiciq.answer_cards import finalize_answer_against_reconciled_truth
from intelligence.ask_intrinsiciq.business_journey import (
    build_business_journey,
    build_journey_summary,
    extract_candidate_journey_events,
    merge_related_journey_events,
    validate_business_journey_quality,
)
from intelligence.ask_intrinsiciq.financial_visuals import build_financial_visual_summaries
from intelligence.ask_intrinsiciq.generator import generate_ask_intrinsiciq_view
from intelligence.ask_intrinsiciq.loader import load_company_memory_sources
from intelligence.ask_intrinsiciq.products_services import (
    build_products_services,
    extract_offering_candidates,
    merge_duplicate_offerings,
    normalize_offering_name,
)
from intelligence.ask_intrinsiciq.paths import (
    get_answer_cards_path,
    get_ask_intrinsiciq_dir,
    get_business_journey_path,
    get_company_research_view_path,
    get_financial_visual_summaries_path,
    get_manifest_path,
    get_products_services_path,
    get_uncertainty_map_path,
    get_validation_report_path,
)
from intelligence.ask_intrinsiciq.sanitizer import contains_forbidden_public_term, sanitize_public_text
from intelligence.ask_intrinsiciq.uncertainty_mapper import build_uncertainty_map, rank_uncertainties_for_question
from intelligence.ask_intrinsiciq.validator import (
    validate_answer_cards_payload,
    validate_business_journey_payload,
    validate_company_research_view,
    validate_financial_visual_summaries_payload,
    validate_products_services_payload,
    validate_uncertainty_map_payload,
)
from intelligence.ask_intrinsiciq.writer import write_json_file


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _source_bundle(
    *,
    years=None,
    business_models=None,
    cim_business_models=None,
    strategy_shifts=None,
    dna_changes=None,
    project_items=None,
    cim_initiatives=None,
    cim_projects=None,
    cim_promises=None,
    truth_precision_limits=None,
    truth_investor_questions=None,
    truth_usable_current_metrics=None,
    truth_usable_derived_metrics=None,
    owner_bridges=None,
    working_capital_drilldown=None,
    capital_allocation_entries=None,
    per_share_analysis=None,
    committee_synthesis=None,
    graham_analysis=None,
    buffett_analysis=None,
    fisher_analysis=None,
    munger_analysis=None,
    lynch_analysis=None,
):
    years = years or ["fy23", "fy24"]
    business_models = business_models or []
    cim_business_models = cim_business_models or []
    strategy_shifts = strategy_shifts or []
    dna_changes = dna_changes or []
    project_items = project_items or {}
    cim_initiatives = cim_initiatives or []
    cim_projects = cim_projects or []
    cim_promises = cim_promises or []
    truth_precision_limits = truth_precision_limits or [
        "Maintenance versus growth capex split is not disclosed, so owner-earnings precision is limited."
    ]
    truth_investor_questions = truth_investor_questions or [
        "What later revenue, margin, CFO, or ROIC outcomes can be linked to this capital deployment?"
    ]
    truth_usable_current_metrics = truth_usable_current_metrics or [
        {
            "metric_id": "revenue",
            "canonical_metric": "revenue",
            "fiscal_year": "fy24",
            "value": 530.0,
        }
    ]
    truth_usable_derived_metrics = truth_usable_derived_metrics or [
        {
            "metric_id": "owner_earnings_estimate",
            "canonical_metric": "owner_earnings_estimate",
            "fiscal_year": "fy24",
            "value": 98.2,
            "value_crore": 98.2,
        }
    ]
    owner_bridges = owner_bridges or [
        {
            "fiscal_year": "fy24",
            "reported_pat": 181.69,
            "cfo": 139.38,
            "owner_earnings_estimate": 98.2,
            "owner_earnings_warnings": ["Maintenance versus growth capex is not split clearly."],
            "warnings": ["Maintenance versus growth capex is not split clearly."],
        }
    ]
    working_capital_drilldown = working_capital_drilldown or [
        {
            "fiscal_year": "fy24",
            "receivables": 398.78,
            "inventory": 266.8,
            "payables": 50.11,
            "receivable_days": 274.3,
            "inventory_days": 464.0,
            "payable_days": 95.5,
            "cash_conversion_cycle": 642.8,
            "working_capital_intensity_status": "severe",
            "cash_strain_risk": "elevated",
        }
    ]
    capital_allocation_entries = capital_allocation_entries or [
        {
            "fiscal_year": "fy24",
            "capex_deployed": -41.18,
            "dividends": -25.19,
            "debt_repayment": None,
            "capital_use": "Facility and technology buildout.",
            "purpose": "Expand operating capacity.",
            "investor_interpretation": "Capital is being deployed into operating capacity.",
            "roi_measurability_status": "partial",
        }
    ]
    per_share_analysis = per_share_analysis or [
        {
            "fiscal_year": "fy24",
            "owner_earnings_per_share": 17.54,
            "book_value_per_share": 42.1,
            "eps_basic": 12.4,
        }
    ]
    committee_synthesis = committee_synthesis or {
        "overall_committee_view": {
            "summary": "The main risks are working-capital strain, concentration, and evidence limits around owner economics."
        },
        "financial_committee_view": {
            "missing_financial_data": ["Maintenance versus growth capex split is not disclosed."],
            "investor_questions_from_financials": ["How much of current capex is maintenance versus growth?"],
            "financial_concerns": ["Working-capital intensity is severe.", "Customer concentration can affect revenue timing."],
        },
        "critical_unknowns": [
            {"unknown": "Owner-economics precision remains limited.", "why_it_matters": "It changes how much cash is really distributable."}
        ],
        "investigation_questions": [
            {"question": "Can management separate maintenance capex from growth capex?"},
            {"question": "Why are receivable days so elevated?"},
        ],
        "most_important_risks": [
            {"risk": "Working-capital strain", "why_it_matters": "Cash can remain trapped despite reported profit."}
        ],
    }
    graham_analysis = graham_analysis or {
        "assessment": {"financial_strength_assessment": "Working-capital stress is the main downside concern."},
        "key_findings": ["Receivable days are very high.", "Cash conversion looks stretched."],
        "red_flags": ["Working-capital risk is elevated."],
        "open_uncertainties": ["The reason for elevated receivable days is unclear."],
    }
    buffett_analysis = buffett_analysis or {
        "assessment": {"business_quality_assessment": "The business looks specialized, but owner-economics precision is still limited."},
        "key_findings": ["The company serves specialized programs.", "Qualification depth appears important."],
        "red_flags": ["Capital efficiency is not yet fully measurable."],
        "open_uncertainties": ["Customer concentration is not fully disclosed."],
    }
    fisher_analysis = fisher_analysis or {
        "assessment": {"management_quality_assessment": "Growth quality depends on execution and reinvestment discipline."},
        "key_findings": ["Reinvestment appears active.", "Working capital deserves monitoring."],
        "red_flags": ["Order-book visibility is limited."],
        "open_uncertainties": ["Multi-year execution evidence is still thin."],
    }
    munger_analysis = munger_analysis or {
        "assessment": {"incentive_alignment_assessment": "Incentive questions deserve monitoring."},
        "key_findings": ["Capital-raising discipline matters.", "Related-party exposure deserves review."],
        "red_flags": ["Governance evidence is incomplete."],
        "open_uncertainties": ["More detail on oversight would help."],
    }
    lynch_analysis = lynch_analysis or {
        "assessment": {"business_simplicity_assessment": "The business story is understandable, but cash conversion makes it less simple than it first appears."},
        "key_findings": ["Profitability is visible.", "Working capital complicates the simple story."],
        "red_flags": ["Per-share comparability is limited."],
        "open_uncertainties": ["Forward demand visibility is limited."],
    }
    return {
        "sources": {
            "pcim": {
                "payload": {
                    "available_years": years,
                    "business_understanding": {
                        "business_model_by_year": business_models,
                        "business_dna_by_year": [
                            {"year": year, "business_dnas": ["Manufacturing"]} for year in years
                        ],
                        "latest_business_view": {
                            "business_model": business_models[-1] if business_models else {},
                        },
                    },
                    "growth_quality_inputs": {
                        "projects_by_year": [
                            {"year": year, "items": project_items.get(year, [])} for year in years
                        ]
                    },
                }
            },
            "cim": {
                "payload": {
                    "business_model": cim_business_models,
                    "initiatives": cim_initiatives,
                    "projects": cim_projects,
                    "promises": cim_promises,
                }
            },
            "financial_truth_pack": {
                "payload": {
                    "precision_limits": truth_precision_limits,
                    "investor_relevant_questions": truth_investor_questions,
                    "usable_current_metrics": truth_usable_current_metrics,
                    "usable_derived_metrics": truth_usable_derived_metrics,
                }
            },
            "owner_earnings_bridge": {"payload": {"bridges": owner_bridges}},
            "working_capital_quality_drilldown": {"payload": {"drilldown": working_capital_drilldown}},
            "capital_allocation_roi_ledger": {"payload": {"entries": capital_allocation_entries}},
            "per_share_compounding_analysis": {"payload": {"analysis": per_share_analysis, "warnings": ["Weighted-average shares are unavailable."]}},
            "committee_synthesis": {"payload": committee_synthesis},
            "graham_analysis": {"payload": graham_analysis},
            "buffett_analysis": {"payload": buffett_analysis},
            "fisher_analysis": {"payload": fisher_analysis},
            "munger_analysis": {"payload": munger_analysis},
            "lynch_analysis": {"payload": lynch_analysis},
            "company_memory_index": {"payload": {"usable_years": years}},
            "multi_year_strategy_timeline": {"payload": {"strategy_shifts": strategy_shifts}},
            "multi_year_business_dna_evolution": {"payload": {"changes_detected": dna_changes}},
        }
    }


def test_path_helpers_are_company_agnostic():
    assert get_ask_intrinsiciq_dir("acme") == Path("companies/acme/company_memory/ask_intrinsiciq")
    assert get_company_research_view_path("acme") == Path("companies/acme/company_memory/ask_intrinsiciq/company_research_view.json")
    assert get_business_journey_path("acme").name == "business_journey.json"
    assert get_products_services_path("acme").name == "products_services.json"
    assert get_answer_cards_path("acme").name == "answer_cards.json"
    assert get_financial_visual_summaries_path("acme").name == "financial_visual_summaries.json"
    assert get_uncertainty_map_path("acme").name == "uncertainty_map.json"
    assert get_manifest_path("acme").name == "ask_intrinsiciq_manifest.json"
    assert get_validation_report_path("acme").name == "ask_intrinsiciq_validation_report.json"


def test_missing_upstream_sources_return_partial_not_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = generate_ask_intrinsiciq_view("acme")

    assert result["manifest"]["generation_status"] == "partial"
    assert result["validation_report"]["status"] == "pass"
    assert len(result["company_research_view"]["categories"]) == 5
    assert result["source_bundle"]["source_files_missing"]


def test_loader_lists_found_and_missing_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_json(
        tmp_path / "companies/acme/company_memory/pcim_v1.json",
        {"company": "Acme", "available_years": ["fy24"]},
    )

    bundle = load_company_memory_sources("acme")

    assert "company_memory/pcim_v1.json" in bundle["source_files_found"]
    assert "company_memory/financials/financial_truth_pack.json" in bundle["source_files_missing"]


def test_loader_rejects_company_mismatched_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_json(
        tmp_path / "companies/tanla/company_memory/pcim_v1.json",
        {"company_slug": "datapatterns", "available_years": ["fy24"]},
    )

    bundle = load_company_memory_sources("tanla")
    pcim = bundle["sources"]["pcim"]

    assert pcim["status"] == "company_mismatch"
    assert pcim["failure_class"] == "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION"
    assert "company_memory/pcim_v1.json" in bundle["source_files_missing"]
    assert "company_memory/pcim_v1.json" not in bundle["source_files_found"]


def test_generator_writes_minimal_valid_company_research_view(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_json(
        tmp_path / "companies/acme/company_memory/pcim_v1.json",
        {
            "company": "Acme Corp",
            "available_years": ["fy24", "fy25"],
            "business_identity_manifest": {
                "primary_sector": "Industrial software",
                "business_summary": "Acme provides workflow software to industrial customers.",
            },
        },
    )

    result = generate_ask_intrinsiciq_view("acme", force=True)
    view = result["company_research_view"]

    assert view["company"]["displayName"] == "Acme Corp"
    assert view["company"]["reportingPeriodsCovered"] == ["fy24", "fy25"]
    assert view["coverage"]["summary"]
    assert "businessJourney" in view
    assert len(view["categories"]) == 5
    assert (tmp_path / "companies/acme/company_memory/ask_intrinsiciq/company_research_view.json").exists()


def test_sanitizer_blocks_forbidden_terms():
    sanitized = sanitize_public_text("PCIM validation artifact JSON")
    assert "PCIM" not in sanitized
    assert "artifact" not in sanitized.lower()
    assert ".json" not in sanitized.lower()
    assert not contains_forbidden_public_term(sanitized)


def test_sanitizer_rejects_obviously_truncated_public_text():
    assert (
        sanitize_public_text(
            "By emphasizing process excellence and operational discipline, management describes the organization as leaner and more a"
        )
        == ""
    )


def test_sanitizer_rejects_malformed_public_fragments():
    assert (
        sanitize_public_text(
            "Management quality / capital-allocation discipline described as weak in; execution commitments have unproven delivery in later-year evidence."
        )
        == ""
    )


def test_finalize_answer_generates_concrete_commitment_watch_item():
    finalized = finalize_answer_against_reconciled_truth(
        {
            "question_id": "what-has-management-promised",
            "simple_answer": "Management promises are visible, but credibility still depends on later execution.",
            "why_it_matters": "This matters because execution needs later evidence.",
            "detailed_explanation": "The evidence is limited.",
            "key_points": ["Commitment A"],
            "evidence_summary": {"summary": "Evidence supports the answer.", "supporting_points": ["Point"], "status": "partial"},
            "uncertainty_note": {"message": "No material evidence limitation was identified for this answer."},
            "progression": {"what_changed": "Commitment A", "unresolved_items": [], "turning_points": []},
            "interpretation": {
                "conclusion": "Management promises are visible, but credibility still depends on later execution.",
                "what_changed": ["Commitment A"],
                "why_it_matters": "This matters because execution needs later evidence.",
                "economic_mechanism": "Credibility compounds when follow-through appears.",
                "thesis_impact": "neutral",
                "positive_evidence": ["Point"],
                "negative_evidence": [],
                "unresolved": [],
                "what_to_watch": [],
                "confidence": {"level": "medium", "basis": [], "limitations": []},
            },
            "answer_status": "supported",
        },
        {"usable_current_metrics": [], "usable_derived_metrics": [], "investor_relevant_questions": [], "precision_limits": []},
        {},
        {},
    )

    assert finalized["interpretation"]["what_to_watch"] == ["Completion evidence for commitment a"]


def test_finalize_answer_moves_unresolved_facts_out_of_strengths():
    finalized = finalize_answer_against_reconciled_truth(
        {
            "question_id": "what-can-break-the-thesis",
            "simple_answer": "The thesis is exposed to working-capital strain.",
            "why_it_matters": "Working capital can trap cash.",
            "detailed_explanation": "The evidence remains mixed.",
            "key_points": ["Risk note"],
            "evidence_summary": {"summary": "Risk evidence is present.", "supporting_points": ["Risk note"], "status": "partial"},
            "uncertainty_note": {"message": "Receivables and inventory appear heavy, but the evidence does not yet show how much comes from billing cycles."},
            "progression": {"what_changed": "Working-capital financing pressure", "unresolved_items": ["Receivables and inventory appear heavy, but the evidence does not yet show how much comes from billing cycles."], "turning_points": []},
            "interpretation": {
                "conclusion": "The thesis is exposed to working-capital strain.",
                "what_changed": ["Working-capital financing pressure"],
                "why_it_matters": "Working capital can trap cash.",
                "economic_mechanism": "Cash can get trapped.",
                "thesis_impact": "weakens",
                "positive_evidence": ["Incomplete capex disclosure / missing maintenance-vs-growth capex split, limiting owner-earnings precision"],
                "negative_evidence": [],
                "unresolved": ["Receivables and inventory appear heavy, but the evidence does not yet show how much comes from billing cycles."],
                "what_to_watch": [],
                "confidence": {"level": "medium", "basis": [], "limitations": []},
            },
            "answer_status": "supported",
        },
        {"usable_current_metrics": [], "usable_derived_metrics": [], "investor_relevant_questions": [], "precision_limits": []},
        {},
        {},
    )

    assert finalized["interpretation"]["positive_evidence"] == []
    assert finalized["interpretation"]["unresolved"]


def test_finalize_answer_clears_positive_bucket_on_risk_page():
    finalized = finalize_answer_against_reconciled_truth(
        {
            "question_id": "what-can-break-the-thesis",
            "simple_answer": "Working-capital strain can break the thesis.",
            "why_it_matters": "Working capital can trap cash.",
            "detailed_explanation": "Risk evidence is mixed.",
            "key_points": ["Risk note"],
            "evidence_summary": {"summary": "Risk evidence is present.", "supporting_points": ["Risk note"], "status": "partial"},
            "uncertainty_note": {"message": "Receivables and inventory appear heavy, but the evidence does not yet show how much comes from billing cycles."},
            "progression": {"what_changed": "Working-capital financing pressure", "unresolved_items": ["Receivables and inventory appear heavy, but the evidence does not yet show how much comes from billing cycles."], "turning_points": []},
            "interpretation": {
                "conclusion": "Working-capital strain can break the thesis.",
                "what_changed": ["Working-capital financing pressure"],
                "why_it_matters": "Working capital can trap cash.",
                "economic_mechanism": "Cash can get trapped.",
                "thesis_impact": "weakens",
                "positive_evidence": ["announcements outpace clear follow-through; capacity remains under construction"],
                "negative_evidence": ["Receivables and inventory appear heavy, but the evidence does not yet show how much comes from billing cycles."],
                "unresolved": ["Receivables and inventory appear heavy, but the evidence does not yet show how much comes from billing cycles."],
                "what_to_watch": [],
                "confidence": {"level": "medium", "basis": [], "limitations": []},
            },
            "answer_status": "supported",
        },
        {"usable_current_metrics": [], "usable_derived_metrics": [], "investor_relevant_questions": [], "precision_limits": []},
        {},
        {},
    )

    assert finalized["interpretation"]["positive_evidence"] == []


def test_validator_rejects_negative_or_unresolved_text_in_strengthens():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards["answers"][0]["interpretation"]["positive_evidence"] = ["Returns on capital remain mixed, and execution momentum is still uncertain."]

    errors = validate_answer_cards_payload(answer_cards, products_services_payload=products_payload, financial_visual_ids=[])
    assert any("positive_evidence" in error for error in errors)


def test_management_commitment_answers_surface_specific_material_commitments():
    bundle = load_company_memory_sources("datapatterns")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="datapatterns", generated_at="2026-08-11T00:00:00+00:00")
    by_question = {answer["question_id"]: answer for answer in answer_cards["answers"]}

    promises = by_question["what-has-management-promised"]["interpretation"]["what_changed"]
    claims = by_question["did-past-claims-come-true"]["interpretation"]["what_changed"]
    promise_conclusion = by_question["what-has-management-promised"]["interpretation"]["conclusion"].lower()
    claims_conclusion = by_question["did-past-claims-come-true"]["interpretation"]["conclusion"].lower()

    assert len(promises) >= 2
    assert len(claims) >= 2
    assert any("fy22" in item.lower() for item in promises)
    assert any("fy25" in item.lower() for item in claims)
    assert all(item.lower() != "capacity expansion" for item in promises)
    assert "capacity expansion" in promise_conclusion
    assert ("follow-through" in claims_conclusion) or ("mixed" in claims_conclusion)
    assert promise_conclusion != claims_conclusion


def test_incentives_answer_uses_signal_level_evidence_not_summary_labels():
    bundle = load_company_memory_sources("datapatterns")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="datapatterns", generated_at="2026-08-11T00:00:00+00:00")
    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-incentives-matter")

    positive = [item.lower() for item in answer["interpretation"]["positive_evidence"]]
    negative = [item.lower() for item in answer["interpretation"]["negative_evidence"]]

    assert positive
    assert all(item not in {"weak", "stable"} for item in positive)
    assert any("improved" in item or "deteriorated" in item or "remained mixed" in item for item in positive + negative)


def test_empty_state_filler_strings_are_not_serialized():
    bundle = load_company_memory_sources("datapatterns")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="datapatterns", generated_at="2026-08-11T00:00:00+00:00")

    text = json.dumps(
        {
            "promises": next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-has-management-promised"),
            "claims": next(answer for answer in answer_cards["answers"] if answer["question_id"] == "did-past-claims-come-true"),
            "risk": next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-can-break-the-thesis"),
        }
    ).lower()

    assert "no material evidence limitation was identified" not in text
    assert "no separate weakening evidence is available" not in text
    assert "this remains a central caution" not in text


def test_buffett_answer_stays_compact_and_strips_backend_phrasing():
    bundle = load_company_memory_sources("datapatterns")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="datapatterns", generated_at="2026-08-11T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-would-buffett-focus-on")
    text = json.dumps(answer).lower()

    assert "earlier promise" not in text
    assert "compact financial inputs" not in text
    assert "source set summaries" not in text
    assert "described as weak in;" not in text
    assert len(answer["interpretation"]["positive_evidence"]) <= 3
    assert len(answer["interpretation"]["negative_evidence"]) <= 3
    assert len(answer["interpretation"]["unresolved"]) <= 3
    assert len(answer["interpretation"]["what_to_watch"]) <= 3


def test_validator_accepts_explicit_empty_unavailable_sections():
    payload = {
        "schemaVersion": "v1",
        "company": {
            "companySlug": "acme",
            "companyName": "Acme",
            "displayName": "Acme",
            "reportingPeriodsCovered": [],
            "primaryIndustry": "",
            "shortDescription": "A concise company description is not yet available in this release.",
        },
        "coverage": {
            "availableCategoryIds": [],
            "sourcedAnswerCount": 0,
            "partiallySupportedAnswerCount": 0,
            "unsupportedAnswerCount": 0,
            "unavailableAnswerCount": 0,
            "evidenceStatus": "missing",
            "summary": "Coverage is still incomplete.",
        },
        "categories": [],
        "businessJourney": {
            "summary": "Not yet available.",
            "stages": [],
            "currentDirection": "Not yet prepared.",
            "openQuestions": [],
        },
        "productsAndServices": [],
        "financialVisuals": [],
        "generatedAt": "2026-08-02T00:00:00+00:00",
        "sourceState": {
            "contentStatus": "incomplete",
            "sourceMode": "deterministic_skeleton",
            "summary": "A minimal research shell is available.",
        },
    }

    assert validate_company_research_view(payload) == []


def test_validator_rejects_duplicate_ids():
    payload = {
        "schemaVersion": "v1",
        "company": {
            "companySlug": "acme",
            "companyName": "Acme",
            "displayName": "Acme",
            "reportingPeriodsCovered": [],
            "primaryIndustry": "",
            "shortDescription": "Safe company description.",
        },
        "coverage": {
            "availableCategoryIds": ["business"],
            "sourcedAnswerCount": 0,
            "partiallySupportedAnswerCount": 0,
            "unsupportedAnswerCount": 0,
            "unavailableAnswerCount": 0,
            "evidenceStatus": "missing",
            "summary": "Coverage is incomplete.",
        },
        "categories": [
            {
                "id": "business",
                "title": "Business",
                "shortDescription": "One",
                "displayOrder": 1,
                "questions": [
                    {
                        "id": "q1",
                        "categoryId": "business",
                        "title": "What does it do?",
                        "shortLabel": "What",
                        "recommended": False,
                        "availabilityStatus": "unavailable",
                        "answerCardId": "a1",
                    },
                    {
                        "id": "q1",
                        "categoryId": "business",
                        "title": "How?",
                        "shortLabel": "How",
                        "recommended": False,
                        "availabilityStatus": "unavailable",
                        "answerCardId": "a2",
                    },
                ],
            }
        ],
        "businessJourney": {"summary": "Safe summary.", "stages": [], "currentDirection": "None.", "openQuestions": []},
        "productsAndServices": [],
        "financialVisuals": [],
        "generatedAt": "2026-08-02T00:00:00+00:00",
        "sourceState": {"contentStatus": "incomplete", "sourceMode": "deterministic_skeleton", "summary": "Safe summary."},
    }

    errors = validate_company_research_view(payload)
    assert any("duplicate question id" in error for error in errors)


def test_validator_rejects_forbidden_public_terminology():
    payload = {
        "schemaVersion": "v1",
        "company": {
            "companySlug": "acme",
            "companyName": "Acme",
            "displayName": "Acme",
            "reportingPeriodsCovered": [],
            "primaryIndustry": "",
            "shortDescription": "PCIM summary.",
        },
        "coverage": {
            "availableCategoryIds": [],
            "sourcedAnswerCount": 0,
            "partiallySupportedAnswerCount": 0,
            "unsupportedAnswerCount": 0,
            "unavailableAnswerCount": 0,
            "evidenceStatus": "missing",
            "summary": "Coverage is incomplete.",
        },
        "categories": [],
        "businessJourney": {"summary": "Safe summary.", "stages": [], "currentDirection": "None.", "openQuestions": []},
        "productsAndServices": [],
        "financialVisuals": [],
        "generatedAt": "2026-08-02T00:00:00+00:00",
        "sourceState": {"contentStatus": "incomplete", "sourceMode": "deterministic_skeleton", "summary": "Safe summary."},
    }

    errors = validate_company_research_view(payload)
    assert any("forbidden public term" in error for error in errors)


def test_writer_creates_canonical_output_directory(tmp_path):
    path = tmp_path / "companies/acme/company_memory/ask_intrinsiciq/company_research_view.json"
    write_json_file(path, {"ok": True})
    assert path.exists()


def test_stage_executes_successfully_for_synthetic_company_without_llm(tmp_path, monkeypatch):
    from pipelines import run_company_pipeline

    monkeypatch.chdir(tmp_path)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM should not be called")

    monkeypatch.setattr(run_company_pipeline, "get_llm", fail_if_called)

    result = run_company_pipeline.run_ask_intrinsiciq_stage(company="acme")

    assert "company_research_view.json" in result
    assert "business_journey.json" in result
    assert "products_services.json" in result
    manifest = json.loads((tmp_path / "companies/acme/company_memory/ask_intrinsiciq/ask_intrinsiciq_manifest.json").read_text(encoding="utf-8"))
    assert manifest["generation_status"] == "partial"


def test_ask_intrinsiciq_stage_exists_in_parser():
    from pipelines import run_company_pipeline

    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "--stage", "ask_intrinsiciq"])
    assert args.stage == "ask_intrinsiciq"


def test_multi_year_business_transition_creates_three_ordered_stages():
    bundle = _source_bundle(
        years=["fy22", "fy23", "fy24"],
        business_models=[
            {"year": "fy22", "business_summary": "The company manufactures defence electronics for domestic programmes.", "business_model": "Manufacturing for government programmes.", "value_creation": "This built the operating base."},
            {"year": "fy23", "business_summary": "The company manufactures defence electronics and has visible export activity.", "business_model": "Manufacturing plus export programmes.", "value_creation": "This broadened the customer reach."},
            {"year": "fy24", "business_summary": "The company is expanding testing and integration facilities.", "business_model": "Manufacturing supported by facility expansion.", "value_creation": "This increases delivery capability."},
        ],
        strategy_shifts=[
            {"from_year": "fy22", "to_year": "fy23", "added_themes": ["geographic_expansion"], "removed_themes": []},
            {"from_year": "fy23", "to_year": "fy24", "added_themes": ["land_facility_expansion"], "removed_themes": []},
        ],
    )
    payload, diagnostics = build_business_journey(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert payload["coverage_status"] == "supported"
    assert len(payload["stages"]) == 3
    assert [stage["display_order"] for stage in payload["stages"]] == [1, 2, 3]
    assert diagnostics["candidate_events"]


def test_duplicate_yearly_descriptions_merge_into_one_stage():
    bundle = _source_bundle(
        years=["fy23", "fy24"],
        business_models=[
            {"year": "fy23", "business_summary": "The company manufactures defence electronics for government customers.", "business_model": "Manufacturing for government customers.", "value_creation": "This built the operating base."},
            {"year": "fy24", "business_summary": "The company manufactures defence electronics for government customers.", "business_model": "Manufacturing for government customers.", "value_creation": "This built the operating base."},
        ],
    )

    events = extract_candidate_journey_events(bundle)
    merged = merge_related_journey_events(events)

    assert len(events) == 2
    assert len(merged) == 1


def test_management_ambition_is_labeled_as_direction_not_completed_fact():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {"year": "fy24", "business_summary": "The company manufactures defence electronics.", "business_model": "Manufacturing business.", "value_creation": "This built the operating base."},
        ],
        project_items={
            "fy24": [
                {"value": "New testing facility expansion", "evidence_references": {"status": "Planned"}}
            ]
        },
    )

    payload, _ = build_business_journey(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert payload["current_direction"].startswith("Management has stated")


def test_single_year_evidence_produces_current_state_only_partial_output():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {"year": "fy24", "business_summary": "The company manufactures defence electronics.", "business_model": "Manufacturing business.", "value_creation": "This built the operating base."},
        ],
    )

    payload, _ = build_business_journey(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert payload["coverage_status"] == "partial"
    assert len(payload["stages"]) == 1


def test_missing_history_returns_unavailable_output_without_crashing():
    payload, _ = build_business_journey({"sources": {}}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert payload["coverage_status"] == "unavailable"
    assert payload["stages"] == []


def test_more_than_five_candidate_events_are_compacted():
    business_models = []
    years = []
    for index in range(1, 8):
        year = f"fy2{index}"
        years.append(year)
        business_models.append(
            {
                "year": year,
                "business_summary": f"Transition phase {index} with different operating focus {index}.",
                "business_model": f"Business model {index}.",
                "value_creation": f"Significance {index}.",
            }
        )
    bundle = _source_bundle(years=years, business_models=business_models)

    payload, _ = build_business_journey(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert len(payload["stages"]) == 4


def test_unsupported_inference_is_excluded():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {"year": "fy24", "business_summary": "The company manufactures defence electronics.", "business_model": "Manufacturing business.", "value_creation": "This built the operating base."},
        ],
        strategy_shifts=[{"from_year": "fy23", "to_year": "fy24", "added_themes": ["unknown_new_theme"], "removed_themes": []}],
    )

    payload, _ = build_business_journey(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert all("unknown" not in stage["title"].lower() for stage in payload["stages"])


def test_forbidden_internal_terminology_is_removed_from_public_output():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {"year": "fy24", "business_summary": "The company manufactures defence electronics from PCIM JSON records.", "business_model": "Manufacturing business.", "value_creation": "This built the operating base."},
        ],
    )

    payload, _ = build_business_journey(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert json.dumps(payload).lower().find("pcim") == -1
    assert json.dumps(payload).lower().find(".json") == -1


def test_internal_provenance_stays_in_diagnostics_only():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {"year": "fy24", "business_summary": "The company manufactures defence electronics.", "business_model": "Manufacturing business.", "value_creation": "This built the operating base."},
        ],
    )

    payload, diagnostics = build_business_journey(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert "provenance" in json.dumps(diagnostics)
    assert "provenance" not in json.dumps(payload)


def test_stage_order_is_deterministic():
    bundle = _source_bundle(
        years=["fy24", "fy22", "fy23"],
        business_models=[
            {"year": "fy24", "business_summary": "Stage c.", "business_model": "Model c.", "value_creation": "Sig c."},
            {"year": "fy22", "business_summary": "Stage a.", "business_model": "Model a.", "value_creation": "Sig a."},
            {"year": "fy23", "business_summary": "Stage b.", "business_model": "Model b.", "value_creation": "Sig b."},
        ],
    )

    payload, _ = build_business_journey(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    labels = [stage["period_label"] for stage in payload["stages"]]
    assert labels == sorted(labels)


def test_business_journey_validator_accepts_generated_partial_output():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {"year": "fy24", "business_summary": "The company manufactures defence electronics.", "business_model": "Manufacturing business.", "value_creation": "This built the operating base."},
        ],
    )
    payload, _ = build_business_journey(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert validate_business_journey_payload(payload) == []


def test_business_journey_exposes_historical_current_and_stated_direction_contract():
    bundle = _source_bundle(
        years=["fy22", "fy23", "fy24"],
        business_models=[
            {"year": "fy22", "business_summary": "The company builds automated test equipment with in-house manufacturing and testing.", "business_model": "Integrated design and manufacturing.", "value_creation": "This established the operating base."},
            {"year": "fy23", "business_summary": "The company builds radar systems and defence electronics for export-capable programmes.", "business_model": "Programme delivery for defence and aerospace customers.", "value_creation": "This broadened customer and programme reach."},
            {"year": "fy24", "business_summary": "The company is investing in EMI-EMC testing, land and building upgrades.", "business_model": "Capacity and testing infrastructure buildout.", "value_creation": "This can expand delivery capacity."},
        ],
        project_items={"fy24": [{"value": "Testing facility expansion", "evidence_references": {"status": "Planned"}}]},
    )

    payload, diagnostics = build_business_journey(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert "historical_stages" in payload
    assert "current_state" in payload
    assert "stated_direction" in payload
    assert len(payload["historical_stages"]) <= 3
    assert payload["current_state"]["title"]
    assert payload["stated_direction"]["description"].startswith("Management has stated")
    assert diagnostics["quality_issues"] == []


def test_products_services_builds_grouped_ui_ready_output():
    bundle = _source_bundle(
        years=["fy23", "fy24"],
        business_models=[
            {
                "year": "fy23",
                "business_summary": "The company builds electronic systems and radar systems for defence programmes.",
                "business_model": "Project-based delivery for government and export customers.",
                "value_creation": "Testing and systems integration support delivery.",
            },
            {
                "year": "fy24",
                "business_summary": "The company builds electronic systems, automated test equipment and software tools.",
                "business_model": "Project and order-based contracts for government, OEM and export customers.",
                "value_creation": "Systems integration and lifecycle support deepen delivery scope.",
            },
        ],
        cim_projects=[
            {
                "year": "fy24",
                "items": [
                    {"value": "Radar integration programme"},
                    {"value": "Environmental testing facility"},
                ],
            }
        ],
    )

    payload, diagnostics = build_products_services(
        bundle,
        business_journey_payload={"summary": "Safe journey summary."},
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    assert payload["coverage_status"] == "supported"
    assert payload["groups"]
    assert validate_products_services_payload(payload) == []
    assert any(item["name"] == "Automated Test Equipment" for group in payload["groups"] for item in group["items"])
    assert "provenance_items" in json.dumps(diagnostics)
    assert all("group" in item for group in payload["groups"] for item in group["items"])
    assert all("revenue_model" in item for group in payload["groups"] for item in group["items"])


def test_products_services_separates_software_from_systems_when_supported():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company sells electronic systems and embedded software tools.",
                "business_model": "Project-based delivery.",
                "value_creation": "Software tools support testing workflows.",
            }
        ],
    )

    payload, _ = build_products_services(
        bundle,
        business_journey_payload={},
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    titles = [group["title"] for group in payload["groups"]]
    assert "Systems and solutions" in titles
    assert "Software and tools" in titles


def test_enterprise_communications_does_not_inherit_defence_template_language():
    bundle = _source_bundle(
        years=["fy20", "fy26"],
        business_models=[
            {
                "year": "fy20",
                "business_summary": "Tanla operates an enterprise-focused communications and marketing automation platform.",
                "business_model": "B2B CPaaS platform selling communications and marketing automation services to large enterprises.",
                "value_creation": "Creates value through omnichannel messaging, predictive analytics and customer engagement workflows.",
            },
            {
                "year": "fy26",
                "business_summary": "Tanla operates enterprise messaging and communications platforms with AI-enabled products.",
                "business_model": "B2B technology platform provider selling messaging and security solutions to enterprises and telecom operators.",
                "value_creation": "Creates value through platform traffic, managed deployments and enterprise communication workflows.",
            },
        ],
    )

    journey_payload, _ = build_business_journey(
        bundle,
        company_slug="tanla",
        generated_at="2026-08-13T00:00:00+00:00",
    )
    products_payload, _ = build_products_services(
        bundle,
        business_journey_payload=journey_payload,
        company_slug="tanla",
        generated_at="2026-08-13T00:00:00+00:00",
    )
    answer_cards, _ = build_answer_cards(
        bundle,
        business_journey_payload=journey_payload,
        products_services_payload=products_payload,
        financial_visual_summaries_payload={"visuals": []},
        uncertainty_map_payload={"items": []},
        company_slug="tanla",
        generated_at="2026-08-13T00:00:00+00:00",
    )

    combined = json.dumps(
        {
            "journey": journey_payload,
            "products": products_payload,
            "answers": [
                answer
                for answer in answer_cards["answers"]
                if answer["question_id"] in {"what-does-company-do", "how-does-it-make-money"}
            ],
        }
    ).lower()
    assert "enterprise communications platform" in combined
    assert "defence integrator" not in combined
    assert "defence and space" not in combined
    assert "defence, aerospace" not in combined
    assert "build and qualify" not in combined
    assert "government agency" not in combined


def test_products_services_merges_duplicate_yearly_offerings():
    candidates = [
        {
            "name": "Automated Test Equipment",
            "normalized_name": normalize_offering_name("Automated Test Equipment"),
            "classification": "physical_product",
            "group_hint": "Products",
            "simple_explanation": "Test equipment.",
            "customer_type": "government agency",
            "role_in_business": "project-based offering",
            "revenue_contribution_status": "unknown",
            "revenue_contribution": None,
            "evidence_status": "direct",
            "provenance": {"source_kind": "pcim_business_model", "year": "fy23", "matched_alias": "automated test equipment"},
        },
        {
            "name": "Automated Test Equipment",
            "normalized_name": normalize_offering_name("ATE"),
            "classification": "physical_product",
            "group_hint": "Products",
            "simple_explanation": "Test equipment.",
            "customer_type": "government agency",
            "role_in_business": "project-based offering",
            "revenue_contribution_status": "partial",
            "revenue_contribution": None,
            "evidence_status": "partial",
            "provenance": {"source_kind": "cim_project", "year": "fy24", "matched_alias": "ate"},
        },
    ]

    merged = merge_duplicate_offerings(candidates)

    assert len(merged) == 1
    assert merged[0]["revenue_contribution_status"] == "partial"
    assert len(merged[0]["provenance_items"]) == 2


def test_products_services_unknown_revenue_does_not_invent_value():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company supplies communication systems.",
                "business_model": "Order-driven delivery.",
                "value_creation": "Programme execution drives revenue.",
            }
        ],
    )

    payload, _ = build_products_services(
        bundle,
        business_journey_payload={},
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    items = [item for group in payload["groups"] for item in group["items"]]
    assert all(item["revenue_contribution"] is None for item in items)


def test_products_services_supporting_capability_can_be_not_applicable():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company uses a captive manufacturing facility and testing facility.",
                "business_model": "Project-based delivery.",
                "value_creation": "Manufacturing capability supports larger programmes.",
            }
        ],
    )

    payload, _ = build_products_services(
        bundle,
        business_journey_payload={},
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    capability_items = [item for group in payload["groups"] for item in group["items"] if item["name"] == "Electronics manufacturing capability"]
    assert capability_items
    assert capability_items[0]["revenue_contribution_status"] == "not_applicable"


def test_products_services_ignores_vague_strategic_themes():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company focuses on innovation, synergy and strategic transformation.",
                "business_model": "A broad strategy statement without clear offerings.",
                "value_creation": "Execution discipline matters.",
            }
        ],
    )

    candidates = extract_offering_candidates(bundle)
    payload, _ = build_products_services(
        bundle,
        business_journey_payload={},
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    assert candidates == []
    assert payload["coverage_status"] == "unavailable"


def test_products_services_validator_rejects_promotional_wording():
    payload = {
        "schema_version": "ask_intrinsiciq_products_services.v1",
        "company_slug": "acme",
        "summary": "Safe summary.",
        "groups": [
            {
                "id": "products",
                "title": "Products",
                "description": "Safe description.",
                "items": [
                    {
                        "id": "item-1",
                        "name": "World-class software tools",
                        "simple_explanation": "Cutting-edge workflow support.",
                        "customer_type": "enterprise customer",
                        "role_in_business": "strategic but economically unproven",
                        "revenue_contribution_status": "unknown",
                        "revenue_contribution": None,
                        "evidence_status": "direct",
                        "display_order": 1,
                    }
                ],
            }
        ],
        "business_model_summary": "Safe summary.",
        "customer_summary": "Safe summary.",
        "revenue_logic_summary": "Safe summary.",
        "open_questions": [],
        "coverage_status": "partial",
        "generated_at": "2026-08-02T00:00:00+00:00",
    }

    errors = validate_products_services_payload(payload)
    assert any("promotional wording" in error for error in errors)


def test_products_services_compacts_to_no_more_than_five_groups():
    original_patterns = []
    for pattern in extract_offering_candidates.__globals__["OFFERING_PATTERNS"]:
        original_patterns.append(dict(pattern))
    temporary_patterns = [
        {
            "canonical_name": f"Offering {index}",
            "aliases": [f"offering {index}"],
            "classification": "other",
            "group_hint": f"Group {index}",
            "simple_explanation": f"Offering {index} explanation.",
            "role_in_business": "project-based offering",
            "revenue_contribution_status": "unknown",
        }
        for index in range(1, 8)
    ]

    try:
        extract_offering_candidates.__globals__["OFFERING_PATTERNS"][:] = temporary_patterns
        bundle = _source_bundle(
            years=["fy24"],
            business_models=[
                {
                    "year": "fy24",
                    "business_summary": " ".join(f"offering {index}" for index in range(1, 8)),
                    "business_model": "Project-based delivery.",
                    "value_creation": "Diverse offerings.",
                }
            ],
        )

        payload, _ = build_products_services(
            bundle,
            business_journey_payload={},
            company_slug="acme",
            generated_at="2026-08-02T00:00:00+00:00",
        )
    finally:
        extract_offering_candidates.__globals__["OFFERING_PATTERNS"][:] = original_patterns

    assert len(payload["groups"]) == 5
    assert payload["groups"][-1]["title"] == "Other offerings"


def test_products_services_separates_subsystems_group_when_supported():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company supplies control systems, navigation systems, and space subsystems.",
                "business_model": "Project-based subsystem delivery.",
                "value_creation": "Subsystem depth supports larger programmes.",
            }
        ],
    )

    payload, _ = build_products_services(
        bundle,
        business_journey_payload={},
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    titles = [group["title"] for group in payload["groups"]]
    assert "Subsystems" in titles


def test_products_services_forbidden_internal_terms_stay_out_of_public_output():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company sells electronic systems from PCIM JSON records.",
                "business_model": "Project-based delivery.",
                "value_creation": "Internal artifact wording should be scrubbed.",
            }
        ],
    )

    payload, _ = build_products_services(
        bundle,
        business_journey_payload={},
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    assert "pcim" not in json.dumps(payload).lower()
    assert ".json" not in json.dumps(payload).lower()


def test_products_services_ordering_is_deterministic_within_groups():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company sells radar systems, automated test equipment and communication systems.",
                "business_model": "Project-based delivery.",
                "value_creation": "Complex systems matter.",
            }
        ],
    )

    payload, _ = build_products_services(
        bundle,
        business_journey_payload={},
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    for group in payload["groups"]:
        orders = [item["display_order"] for item in group["items"]]
        assert orders == list(range(1, len(orders) + 1))


def test_answer_cards_supported_business_question_is_complete():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company builds automated test equipment and electronic systems for defence programmes.",
                "business_model": "Project-based delivery for defence customers.",
                "value_creation": "Qualification and integration depth support delivery.",
            }
        ],
        cim_projects=[{"year": "fy24", "items": [{"value": "Radar integration facility"}]}],
    )
    products_payload, _ = build_products_services(
        bundle,
        business_journey_payload={"summary": "Safe journey summary.", "stages": [{"id": "fy24-stage"}]},
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )
    answer_cards, _ = build_answer_cards(
        bundle,
        business_journey_payload={"summary": "Safe journey summary.", "stages": [{"id": "fy24-stage"}]},
        products_services_payload=products_payload,
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-does-company-do")

    assert answer["answer_status"] in {"supported", "partially_supported"}
    assert answer["simple_answer"]
    assert answer["why_it_matters"]
    assert answer["key_points"]
    assert answer["detailed_explanation"]
    assert len(answer["next_questions"]) == 3


def test_answer_cards_product_refs_are_valid():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company builds automated test equipment and electronic systems.",
                "business_model": "Project-based delivery.",
                "value_creation": "Qualification depth matters.",
            }
        ],
    )
    journey_payload = {"summary": "Safe journey summary.", "stages": [{"id": "fy24-stage"}]}
    products_payload, _ = build_products_services(bundle, business_journey_payload=journey_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload=journey_payload, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert validate_answer_cards_payload(answer_cards, products_services_payload=products_payload, financial_visual_ids=[]) == []


def test_financial_visual_summaries_generate_supported_current_state_visuals():
    bundle = _source_bundle()

    payload, _ = build_financial_visual_summaries(
        bundle,
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    visual_ids = {visual["id"] for visual in payload["visuals"]}
    assert "cfo_vs_pat" in visual_ids
    assert "owner_earnings_bridge" in visual_ids
    assert "working_capital_days" in visual_ids
    assert "cash_conversion_cycle" in visual_ids
    assert "per_share_economics" in visual_ids
    assert "capital_allocation_summary" in visual_ids
    assert validate_financial_visual_summaries_payload(payload) == []


def test_financial_visual_summaries_skip_multi_year_trends_without_enough_periods():
    bundle = _source_bundle(
        truth_usable_current_metrics=[{"metric_id": "revenue", "fiscal_year": "fy24", "value": 530.0}],
        owner_bridges=[{"fiscal_year": "fy24", "reported_pat": 181.69, "cfo": 139.38, "owner_earnings_estimate": 98.2}],
    )

    payload, _ = build_financial_visual_summaries(
        bundle,
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    visual_ids = {visual["id"] for visual in payload["visuals"]}
    assert "revenue_trend" not in visual_ids
    assert "pat_trend" not in visual_ids


def test_financial_visual_summaries_allow_multi_year_revenue_and_pat_when_supported():
    bundle = _source_bundle(
        truth_usable_current_metrics=[
            {"metric_id": "revenue", "fiscal_year": "fy23", "value": 410.0},
            {"metric_id": "revenue", "fiscal_year": "fy24", "value": 530.0},
        ],
        owner_bridges=[
            {"fiscal_year": "fy23", "reported_pat": 120.0, "cfo": 110.0, "owner_earnings_estimate": 85.0},
            {"fiscal_year": "fy24", "reported_pat": 181.69, "cfo": 139.38, "owner_earnings_estimate": 98.2},
        ],
    )

    payload, _ = build_financial_visual_summaries(
        bundle,
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    revenue = next(visual for visual in payload["visuals"] if visual["id"] == "revenue_trend")
    pat = next(visual for visual in payload["visuals"] if visual["id"] == "pat_trend")
    assert len(revenue["series"][0]["points"]) == 2
    assert len(pat["series"][0]["points"]) == 2


def test_uncertainty_map_generates_key_investor_readable_items():
    bundle = _source_bundle(
        truth_investor_questions=["Why are receivables or inventory rising relative to revenue conversion?"]
    )
    journey_payload = {
        "summary": "Safe journey summary.",
        "stages": [{"id": "fy24-stage"}],
        "open_questions": ["Has the added capacity become economically meaningful yet?"],
    }
    products_payload = {
        "summary": "Safe products summary.",
        "groups": [],
        "business_model_summary": "Project-based delivery.",
        "customer_summary": "Institutional customers.",
        "revenue_logic_summary": "Revenue visibility is still partial.",
        "open_questions": ["Which offerings contribute the most revenue?"],
        "coverage_status": "supported",
    }

    payload, _ = build_uncertainty_map(
        bundle,
        business_journey_payload=journey_payload,
        products_services_payload=products_payload,
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    item_ids = {item["id"] for item in payload["items"]}
    assert "uncertainty-capex_split" in item_ids
    assert "uncertainty-working_capital_drivers" in item_ids
    assert "uncertainty-product_revenue_mix" in item_ids
    assert validate_uncertainty_map_payload(payload) == []


def test_uncertainty_map_deduplicates_capex_split_related_gaps():
    bundle = _source_bundle(
        truth_precision_limits=[
            "Maintenance versus growth capex split is not disclosed, so owner-earnings precision is limited.",
            "derived fcf is available for the current usable year, but precision is limited because maintenance versus growth capex split is unavailable",
        ],
        committee_synthesis={
            "overall_committee_view": {"summary": "Safe summary."},
            "financial_committee_view": {
                "missing_financial_data": ["Maintenance versus growth capex split is unavailable."],
                "financial_disagreements": [],
            },
            "critical_unknowns": [
                {
                    "unknown": "maintenance/growth capex split unavailable",
                    "why_it_matters": "It changes owner-oriented cash interpretation.",
                }
            ],
            "investigation_questions": [{"question": "How much of current capex is maintenance capex versus growth capex?"}],
        },
    )

    payload, _ = build_uncertainty_map(
        bundle,
        business_journey_payload={"summary": "", "stages": [], "open_questions": []},
        products_services_payload={"summary": "", "groups": [], "business_model_summary": "", "customer_summary": "", "revenue_logic_summary": "", "open_questions": [], "coverage_status": "partial"},
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    capex_items = [item for item in payload["items"] if item["id"] == "uncertainty-capex_split"]
    assert len(capex_items) == 1


def test_answer_cards_use_uncertainty_map_when_available():
    bundle = _source_bundle()
    journey_payload = {"summary": "Safe journey summary.", "stages": [{"id": "fy24-stage"}], "open_questions": []}
    products_payload, _ = build_products_services(bundle, business_journey_payload=journey_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    visual_payload, _ = build_financial_visual_summaries(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    uncertainty_payload, _ = build_uncertainty_map(
        bundle,
        business_journey_payload=journey_payload,
        products_services_payload=products_payload,
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )
    answer_cards, _ = build_answer_cards(
        bundle,
        business_journey_payload=journey_payload,
        products_services_payload=products_payload,
        financial_visual_summaries_payload=visual_payload,
        uncertainty_map_payload=uncertainty_payload,
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-is-owner-earnings")
    assert "maintenance and growth capex" in answer["uncertainty_note"]["message"].lower()


def test_uncertainty_ranking_prefers_question_specific_theme():
    ranked = rank_uncertainties_for_question(
        "what-would-buffett-focus-on",
        [
            {"theme_key": "working_capital_drivers", "severity": "high", "display_order": 4},
            {"theme_key": "capex_split", "severity": "medium", "display_order": 1},
        ],
    )

    assert ranked[0]["theme_key"] == "capex_split"


def test_customer_answer_exposes_customer_role_object():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company builds electronic systems for government customers, OEM partners, defence integrators, and export programmes.",
                "business_model": "Project-based delivery for government customers, OEM partners, defence integrators, and export programmes.",
                "value_creation": "Qualification depth and system integration support delivery.",
            }
        ],
    )
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "who-are-the-customers")

    assert answer["customer_roles"]["payers"]
    assert answer["customer_roles"]["integrators_or_partners"]
    assert "government agency" not in " ".join(answer["customer_roles"]["integrators_or_partners"]).lower()


def test_revenue_answer_exposes_revenue_flow_object():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company builds automated test equipment and communication systems.",
                "business_model": "Project-based order and programme delivery with milestone-linked acceptance.",
                "value_creation": "Testing and qualification support customer acceptance.",
            }
        ],
    )
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "how-does-it-make-money")

    assert answer["revenue_flow"]["model_type"] == "project_based"
    assert 5 <= len(answer["revenue_flow"]["steps"]) <= 6


def test_buffett_answer_exposes_structured_sections():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-would-buffett-focus-on")

    titles = [section["title"] for section in answer["structured_sections"]]
    assert "What he may like" in titles
    assert "What he would question" in titles


def test_generate_view_writes_uncertainty_map_and_company_summary():
    result = generate_ask_intrinsiciq_view("datapatterns", force=True)

    uncertainty_payload = result["uncertainty_map"]
    assert uncertainty_payload["items"]
    assert get_uncertainty_map_path("datapatterns").exists()
    assert result["manifest"]["outputs_written"].count("uncertainty_map.json") == 1
    uncertainty_summary = result["company_research_view"]["sourceState"]["uncertaintySummary"]
    assert uncertainty_summary["importantUnknownsCount"] >= 1
    assert "mainUncertainty" in uncertainty_summary


def test_answer_cards_include_only_existing_financial_visual_refs():
    bundle = _source_bundle()
    journey_payload = {"summary": "Safe journey summary.", "stages": [{"id": "fy24-stage"}]}
    products_payload, _ = build_products_services(bundle, business_journey_payload=journey_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    visual_payload, _ = build_financial_visual_summaries(bundle, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(
        bundle,
        business_journey_payload=journey_payload,
        products_services_payload=products_payload,
        financial_visual_summaries_payload=visual_payload,
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    visual_ids = [visual["id"] for visual in visual_payload["visuals"]]
    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "are-profits-converting-into-cash")
    assert answer["financial_visual_refs"]
    assert validate_answer_cards_payload(answer_cards, products_services_payload=products_payload, financial_visual_ids=visual_ids) == []


def test_answer_cards_business_journey_reference_is_included_when_available():
    bundle = _source_bundle(
        years=["fy24"],
        business_models=[
            {
                "year": "fy24",
                "business_summary": "The company builds automated test equipment.",
                "business_model": "Project-based delivery.",
                "value_creation": "Specialized testing matters.",
            }
        ],
    )
    journey_payload = {"summary": "Safe journey summary.", "stages": [{"id": "fy22-stage"}, {"id": "fy24-stage"}]}
    products_payload, _ = build_products_services(bundle, business_journey_payload=journey_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload=journey_payload, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-does-company-do")
    assert answer["business_journey_ref"] is None
    assert answer["business_journey_mode"] == "full"


def test_answer_cards_non_business_questions_do_not_leak_business_journey_context():
    bundle = _source_bundle()
    journey_payload = {"summary": "Safe journey summary.", "stages": [{"id": "fy22-stage"}, {"id": "fy24-stage"}]}
    products_payload, _ = build_products_services(bundle, business_journey_payload=journey_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload=journey_payload, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    by_question = {answer["question_id"]: answer for answer in answer_cards["answers"]}

    assert by_question["what-has-management-promised"]["business_journey_mode"] == "none"
    assert by_question["what-has-management-promised"]["business_journey_ref"] is None
    assert by_question["how-is-capital-allocated"]["business_journey_mode"] == "none"
    assert by_question["how-is-capital-allocated"]["business_journey_ref"] is None


def test_financial_visual_bridge_points_include_semantic_labels():
    bundle = _source_bundle(
        owner_bridges=[
            {
                "fiscal_year": "fy24",
                "reported_pat": 181.69,
                "cfo": 139.38,
                "total_identified_capex": 41.18,
                "owner_earnings_estimate": 98.2,
                "owner_earnings_warnings": ["Maintenance versus growth capex is not split clearly."],
                "warnings": ["Maintenance versus growth capex is not split clearly."],
            }
        ]
    )
    payload, _ = build_financial_visual_summaries(
        bundle,
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    bridge = next(visual for visual in payload["visuals"] if visual["id"] == "owner_earnings_bridge")
    labels = [point.get("semantic_label") for point in bridge["series"][0]["points"]]

    assert labels == [
        "Operating cash flow",
        "Identified capex",
        "Owner-oriented cash estimate",
    ]


def test_business_journey_summary_avoids_repeating_same_start_and_end_title():
    stages = [
        {"title": "Integrated manufacturing buildout"},
        {"title": "Export-capable defence electronics maker"},
        {"title": "Integrated manufacturing buildout"},
    ]

    summary = build_journey_summary(stages, current_direction=None)

    assert "moved from integrated manufacturing buildout toward integrated manufacturing buildout" not in summary.lower()


def test_answer_cards_missing_products_services_produces_partial_or_not_supported_not_crash():
    bundle = _source_bundle()
    answer_cards, _ = build_answer_cards(
        bundle,
        business_journey_payload={"summary": "", "stages": []},
        products_services_payload={"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"},
        company_slug="acme",
        generated_at="2026-08-02T00:00:00+00:00",
    )

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-does-company-do")
    assert answer["answer_status"] in {"not_supported", "partially_supported"}


def test_answer_cards_financial_answer_uses_current_financial_truth():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "are-profits-converting-into-cash")
    assert "₹181.69 crore" in answer["simple_answer"]
    assert answer["answer_status"] in {"supported", "partially_supported"}


def test_answer_cards_multi_year_limitation_prevents_false_improvement_claim():
    bundle = _source_bundle(
        per_share_analysis=[{"fiscal_year": "fy24", "owner_earnings_per_share": 17.54, "book_value_per_share": 42.1, "eps_basic": 12.4}]
    )
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "are-per-share-economics-improving")
    assert answer["answer_status"] == "partially_supported"
    assert "does not yet support a clean multi-year improvement claim" in answer["simple_answer"].lower()


def test_answer_cards_missing_management_history_produces_not_supported():
    bundle = _source_bundle(cim_promises=[])
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "did-past-claims-come-true")
    assert answer["answer_status"] == "not_supported"
    assert "does not yet support" in answer["simple_answer"].lower()


def test_answer_cards_investor_lens_preserves_doctrine_focus():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-would-buffett-focus-on")
    assert "durable" in answer["why_it_matters"].lower() or "business quality" in answer["simple_answer"].lower()


def test_answer_cards_buffett_answer_strips_backend_phrasing():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-would-buffett-focus-on")
    text = json.dumps(answer).lower()

    assert "compact financial inputs" not in text
    assert "company memory" not in text
    assert "available evidence summary" not in text


def test_answer_cards_risk_page_removes_filler_caution_phrase():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-can-break-the-thesis")
    text = json.dumps(answer).lower()

    assert "this remains a central caution" not in text
    assert answer["interpretation"]["positive_evidence"] == []


def test_answer_cards_exactly_three_next_questions_are_generated_for_all_answers():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert all(len(answer["next_questions"]) == 3 for answer in answer_cards["answers"])


def test_answer_cards_validator_rejects_invalid_next_question_id():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards["answers"][0]["next_questions"][0]["question_id"] = "not-a-real-question"

    errors = validate_answer_cards_payload(answer_cards, products_services_payload=products_payload, financial_visual_ids=[])
    assert any("next question is invalid" in error for error in errors)


def test_answer_cards_validator_rejects_more_than_four_key_points():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards["answers"][0]["key_points"] = ["a", "b", "c", "d", "e"]

    errors = validate_answer_cards_payload(answer_cards, products_services_payload=products_payload, financial_visual_ids=[])
    assert any("more than 4 key_points" in error for error in errors)


def test_answer_cards_forbidden_internal_terminology_is_removed():
    bundle = _source_bundle(
        committee_synthesis={
            "overall_committee_view": {"summary": "PCIM artifact JSON summary."},
            "financial_committee_view": {"missing_financial_data": ["schema issue"], "investor_questions_from_financials": ["How?"]},
            "critical_unknowns": [],
            "investigation_questions": [{"question": "Need more clarity."}],
            "most_important_risks": [{"risk": "risk", "why_it_matters": "artifact"}],
        }
    )
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert "pcim" not in json.dumps(answer_cards).lower()
    assert ".json" not in json.dumps(answer_cards).lower()


def test_answer_cards_validator_rejects_buy_sell_hold_language():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards["answers"][0]["simple_answer"] = "Investors should buy this company."

    errors = validate_answer_cards_payload(answer_cards, products_services_payload=products_payload, financial_visual_ids=[])
    assert any("forbidden investment language" in error for error in errors)


def test_answer_cards_all_catalog_questions_receive_records_and_are_deterministic():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    first_payload, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    second_payload, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    assert len(first_payload["answers"]) == 25
    assert [answer["question_id"] for answer in first_payload["answers"]] == [answer["question_id"] for answer in second_payload["answers"]]


def test_generate_view_writes_financial_visual_artifact_and_links_it():
    result = generate_ask_intrinsiciq_view("datapatterns", force=True)

    visual_payload = result["financial_visual_summaries"]
    assert visual_payload["visuals"]
    assert get_financial_visual_summaries_path("datapatterns").exists()
    assert result["manifest"]["outputs_written"].count("financial_visual_summaries.json") == 1
    assert result["company_research_view"]["financialVisuals"]


def test_company_research_view_rejects_stale_source_freshness():
    payload = {
        "schemaVersion": "ask_intrinsiciq.company_research_view.v1",
        "company": {
            "companySlug": "acme",
            "companyName": "Acme",
            "displayName": "Acme",
            "reportingPeriodsCovered": ["fy24"],
            "primaryIndustry": "Manufacturing",
            "shortDescription": "A sample company.",
        },
        "coverage": {
            "availableCategoryIds": [],
            "sourcedAnswerCount": 0,
            "partiallySupportedAnswerCount": 0,
            "unsupportedAnswerCount": 0,
            "unavailableAnswerCount": 0,
            "evidenceStatus": "missing",
            "summary": "No answers are available.",
        },
        "categories": [],
        "businessJourney": {"summary": "", "stages": [], "currentDirection": "", "openQuestions": []},
        "productsAndServices": [],
        "financialVisuals": [],
        "generatedAt": "2026-08-09T00:00:00Z",
        "sourceState": {
            "contentStatus": "stale",
            "sourceMode": "deterministic_skeleton",
            "summary": "Stale upstream inputs should not be published.",
            "foundSourceCount": 1,
            "missingSourceCount": 0,
            "uncertaintySummary": {
                "importantUnknownsCount": 0,
                "highSeverityCount": 0,
                "mainUncertainty": "",
                "unresolvedQuestionCount": 0,
            },
            "sourceFreshness": {
                "freshnessStatus": "stale",
                "checkedAt": "2026-08-09T00:00:00Z",
                "latestSourceGeneratedAt": "2026-08-10T00:00:00Z",
                "latestSourceModifiedAt": "2026-08-10T00:00:00Z",
                "loadedSources": [
                    {"sourceName": "pcim", "generatedAt": "2026-08-10T00:00:00Z", "fileMtime": "2026-08-10T00:00:00Z"}
                ],
                "staleSources": ["pcim"],
            },
        },
    }

    errors = validate_company_research_view(payload)

    assert errors
    assert any("stale upstream inputs" in error for error in errors)
    assert any("stale sources" in error for error in errors)
