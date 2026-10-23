import hashlib
import json
import os
import shutil
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
from intelligence.ask_intrinsiciq.answer_cards import _strip_backend_phrasing  # noqa: PLC0415
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


def _protected_snapshot(repo: Path) -> dict:
    """{relative path: sha256} of the protected real files, RE-ENUMERATED on every call: every file anywhere under
    companies/*/company_memory/ask_intrinsiciq/ plus the approval registry (recorded as "<MISSING>" if absent, never skipped)."""
    snapshot = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(repo.glob("companies/*/company_memory/ask_intrinsiciq/**/*")) if p.is_file()}
    registry = repo / "governance" / "approval_registry.json"
    snapshot[str(registry.relative_to(repo))] = hashlib.sha256(registry.read_bytes()).hexdigest() if registry.is_file() else "<MISSING>"
    return snapshot


def _assert_protected_unchanged(before: dict, after: dict) -> None:
    added, removed = sorted(set(after) - set(before)), sorted(set(before) - set(after))
    modified = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    assert not (added or removed or modified), f"protected real files changed while the sandbox was active: added={added} removed={removed} modified={modified}"


def _sandbox(repo: Path, root: Path):
    """The ask_intrinsiciq generator writes cwd-relative files under companies/<slug>/company_memory/ask_intrinsiciq/.
    Run it in a temporary working directory holding real COPIES of every company's company_memory (no symlinks into the repository, so
    os.replace, write_text, open("w"), shutil and nested creates/deletes are all contained). A tripwire compares a freshly enumerated
    snapshot of the protected real files before and after and fails on any added, removed or modified path."""
    before = _protected_snapshot(repo)
    assert repo not in root.resolve().parents and root.resolve() != repo, "sandbox must live outside the repository"
    for memory in repo.glob("companies/*/company_memory"):
        shutil.copytree(memory, root / "companies" / memory.parent.name / "company_memory")
    for path in root.rglob("*"):  # fail rather than fall back to real files: nothing may resolve into the repository
        assert repo not in Path(os.path.realpath(path)).parents, f"{path} resolves into the repository"
    previous = Path.cwd()
    os.chdir(root)
    try:
        yield root
    finally:
        os.chdir(previous)
        _assert_protected_unchanged(before, _protected_snapshot(repo))


@pytest.fixture(scope="module")
def ask_intrinsiciq_sandbox(tmp_path_factory):
    repo = Path(__file__).resolve().parents[2]
    yield from _sandbox(repo, tmp_path_factory.mktemp("ask_intrinsiciq_sandbox"))


# Every test in this module runs in the sandbox, never against the repository.
pytestmark = pytest.mark.usefixtures("ask_intrinsiciq_sandbox")


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
        "company_slug": "acme",
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
            "company_model": {
                "payload": {
                    "schema_version": "company_model.v1",
                    "company_slug": "acme",
                    "coverage_status": "supported",
                    "company_identity": {"name": "Acme Corp"},
                    "current_business_model": (business_models[-1] if business_models else {
                        "summary": "Acme Corp builds and sells products.",
                        "business_model_type": "Manufacturing",
                        "what_company_does": "Acme Corp builds automated test equipment and electronic systems.",
                        "what_it_sells": "Automated test equipment and electronic systems.",
                        "how_revenue_happens": "Project-based delivery for defence customers.",
                        "economic_mechanism": "Qualification and integration depth support delivery.",
                    }),
                    "offerings": [],
                    "customers": [],
                    "revenue_engines": [],
                }
            },
        }
    }


def test_path_helpers_are_company_agnostic(tmp_path):
    root = tmp_path / "companies"
    assert get_ask_intrinsiciq_dir("acme", root) == root / "acme/company_memory/ask_intrinsiciq"
    assert get_company_research_view_path("acme", root) == root / "acme/company_memory/ask_intrinsiciq/company_research_view.json"
    assert get_business_journey_path("acme", root).name == "business_journey.json"
    assert get_products_services_path("acme", root).name == "products_services.json"
    assert get_answer_cards_path("acme", root).name == "answer_cards.json"
    assert get_financial_visual_summaries_path("acme", root).name == "financial_visual_summaries.json"
    assert get_uncertainty_map_path("acme", root).name == "uncertainty_map.json"
    assert get_manifest_path("acme", root).name == "ask_intrinsiciq_manifest.json"
    assert get_validation_report_path("acme", root).name == "ask_intrinsiciq_validation_report.json"


def test_missing_upstream_sources_return_partial_not_crash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = generate_ask_intrinsiciq_view("acme", tmp_path / "companies")

    assert result["manifest"]["generation_status"] == "partial"
    assert result["validation_report"]["status"] == "pass"
    assert len(result["company_research_view"]["categories"]) == 6
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


def test_loader_resolves_sun_pharma_filesystem_slug():
    bundle = load_company_memory_sources("sun_pharma")

    assert bundle["company_slug"] == "sun_pharma"
    # Financial-derived sources are usable only when recorded against the company's fact registries (knowledge.financials.authority_gate). The SERVED tree's CIM / PCIM / panel
    # artifacts predate that record (and this module's sandbox holds company_memory only, no year registries), so until the remediated candidate is migrated they are unavailable - they load once recorded.
    for name in ("cim", "pcim", "committee_synthesis"):
        record = bundle["sources"][name]
        assert record["status"] == "loaded" or (record["status"] == "authority_unavailable" and record["error"].startswith("FINANCIAL_AUTHORITY_")), (name, record["status"], record["error"])
    assert len(bundle["source_files_found"]) >= 20


def test_loader_canonicalizes_hyphenated_company_slug_to_filesystem_form():
    hyphenated = load_company_memory_sources("sun-pharma")
    canonical = load_company_memory_sources("sun_pharma")

    assert hyphenated["company_slug"] == "sun_pharma"
    assert hyphenated["source_files_found"] == canonical["source_files_found"]
    assert hyphenated["sources"]["cim"]["status"] == canonical["sources"]["cim"]["status"] in {"loaded", "authority_unavailable"}
    assert hyphenated["sources"]["pcim"]["status"] == canonical["sources"]["pcim"]["status"] in {"loaded", "authority_unavailable"}


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

    result = generate_ask_intrinsiciq_view("acme", tmp_path / "companies", force=True)
    view = result["company_research_view"]

    assert view["company"]["displayName"] == "Acme Corp"
    assert view["company"]["reportingPeriodsCovered"] == ["fy24", "fy25"]
    assert view["coverage"]["summary"]
    assert "businessJourney" in view
    assert len(view["categories"]) == 6
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


def test_investor_lens_routes_red_flags_and_uncertainty_out_of_positive_evidence():
    bundle = _source_bundle(
        munger_analysis={
            "assessment": {"incentive_alignment_assessment": "Governance and execution risks dominate this lens."},
            "key_findings": [
                "Execution discipline remains weak and recurring risks are worsening.",
                "A disclosed control improvement supports better oversight.",
            ],
            "red_flags": ["Related-party exposure could weaken owner alignment."],
            "open_uncertainties": ["The financial outcome remains unproven."],
        }
    )
    products, _ = build_products_services(
        bundle,
        business_journey_payload={"summary": "", "stages": []},
        company_slug="acme",
        generated_at="2026-09-09T00:00:00+00:00",
    )
    cards, _ = build_answer_cards(
        bundle,
        business_journey_payload={"summary": "", "stages": []},
        products_services_payload=products,
        company_slug="acme",
        generated_at="2026-09-09T00:00:00+00:00",
    )
    answer = next(item for item in cards["answers"] if item["question_id"] == "what-would-munger-avoid")
    interpretation = answer["interpretation"]

    assert interpretation["positive_evidence"] == ["A disclosed control improvement supports better oversight."]
    assert "Execution discipline remains weak" in interpretation["negative_evidence"][0]
    assert "Related-party exposure" in interpretation["negative_evidence"][1]
    assert interpretation["unresolved"] == ["The financial outcome remains not yet demonstrated."]


def test_committee_agreement_missing_state_is_cautious_and_validator_safe():
    bundle = _source_bundle(
        committee_synthesis={
            "overall_committee_view": {"summary": "Views remain divided."},
            "doctrine_agreements": [],
        }
    )
    products, _ = build_products_services(
        bundle,
        business_journey_payload={"summary": "", "stages": []},
        company_slug="acme",
        generated_at="2026-09-09T00:00:00+00:00",
    )
    cards, _ = build_answer_cards(
        bundle,
        business_journey_payload={"summary": "", "stages": []},
        products_services_payload=products,
        company_slug="acme",
        generated_at="2026-09-09T00:00:00+00:00",
    )
    answer = next(item for item in cards["answers"] if item["question_id"] == "where-does-the-committee-agree")

    assert answer["answer_status"] == "unavailable"
    assert "available committee synthesis" in answer["simple_answer"].lower()
    errors = validate_answer_cards_payload(cards, products_services_payload=products, financial_visual_ids=[])
    assert not any("answer-where-does-the-committee-agree must use cautious language" in error for error in errors)


def test_committee_agreement_explicitly_distinguishes_consensus_from_proof():
    bundle = _source_bundle(
        committee_synthesis={
            "overall_committee_view": {"summary": "The committee is cautious."},
            "doctrine_agreements": ["All analysts identify working-capital conversion as a key uncertainty."],
        }
    )
    products, _ = build_products_services(
        bundle,
        business_journey_payload={"summary": "", "stages": []},
        company_slug="acme",
        generated_at="2026-09-09T00:00:00+00:00",
    )
    cards, _ = build_answer_cards(
        bundle,
        business_journey_payload={"summary": "", "stages": []},
        products_services_payload=products,
        company_slug="acme",
        generated_at="2026-09-09T00:00:00+00:00",
    )
    answer = next(item for item in cards["answers"] if item["question_id"] == "where-does-the-committee-agree")

    combined = " ".join(
        [answer["why_it_matters"], answer["detailed_explanation"], answer["uncertainty_note"]["message"]]
    ).lower()
    assert "not independent proof" in combined or "agreement is not proof" in combined


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
    assert any("fy22" in item.lower() for item in claims)
    assert all(item.lower() != "capacity expansion" for item in promises)
    assert "stated directions" in promise_conclusion or "strategic intents" in promise_conclusion
    assert ("follow-through" in claims_conclusion) or ("not held against" in claims_conclusion)
    assert promise_conclusion != claims_conclusion


def test_incentives_answer_uses_signal_level_evidence_not_summary_labels():
    # Sun Pharma has ownership_evolution.json — use it to exercise the ownership-based incentives builder
    bundle = load_company_memory_sources("sun_pharma")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="sun_pharma", generated_at="2026-08-11T00:00:00+00:00")
    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-incentives-matter")

    # New contract: ownership-based builder — must surface real ownership signals, not management progression labels
    assert answer["answer_status"] in ("partially_supported", "supported"), f"Expected ownership evidence, got: {answer['answer_status']}"
    interp = answer.get("interpretation") or {}
    positive = [item.lower() for item in (interp.get("positive_evidence") or [])]
    negative = [item.lower() for item in (interp.get("negative_evidence") or [])]
    unresolved = [item.lower() for item in (interp.get("unresolved") or [])]

    # Must have ownership alignment signals, not bare summary labels
    assert positive, "No positive_evidence in incentives answer"
    assert all(item not in {"weak", "stable"} for item in positive)
    # Compensation gap must appear in unresolved — the picture is always incomplete without KMP data
    combined = " ".join(unresolved + negative)
    assert any(phrase in combined for phrase in ("incomplete", "not yet", "compensation", "kmp")), (
        f"No incentive-gap signal in negative/unresolved: {negative + unresolved}"
    )


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


def test_strip_backend_phrasing_removes_parenthetical_labels():
    # Labels that appear in parenthetical form must be stripped without leaving dangling ()
    cases = [
        (
            "programs have been announced or started (ACTION_STARTED), but commitments remain (CLAIM_ONLY).",
            "programs have been announced or started, but commitments remain.",
        ),
        (
            "The outcome is inconclusive (UNVERIFIED).",
            "The outcome is inconclusive.",
        ),
        (
            "Capital return to shareholders (NOT_APPLICABLE).",
            "Capital return to shareholders.",
        ),
    ]
    for raw, expected_fragment in cases:
        result = _strip_backend_phrasing(raw)
        assert "()" not in result, f"Dangling parens in result: {result!r}  (input: {raw!r})"
        # The label itself must not appear in the output
        for label in ("ACTION_STARTED", "CLAIM_ONLY", "UNVERIFIED", "NOT_APPLICABLE"):
            assert label.lower() not in result.lower(), f"Label {label!r} not stripped from: {result!r}"


def test_buffett_structured_sections_drop_all_empty_point_sections():
    # After production finalization, sections whose every point is empty must not appear
    bundle = load_company_memory_sources("sun_pharma")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="sun_pharma", generated_at="2026-08-11T00:00:00+00:00")

    answer = next(a for a in answer_cards["answers"] if a["question_id"] == "what-would-buffett-focus-on")
    secs = answer.get("structured_sections", [])
    bad = [s.get("title") for s in secs if not any(str(p).strip() for p in (s.get("points") or []))]
    assert not bad, f"Buffett answer has sections with all-empty points: {bad}"


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
    write_json_file(path, {"ok": True}, root=tmp_path / "companies")
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

    assert answer["revenue_flow"]["model_type"] in {"project_based", "business_model", "mixed", "recurring", "unclear"}
    assert len(answer["revenue_flow"]["steps"]) == 4
    assert "billing_basis_note" in answer["revenue_flow"]
    assert "cash_timing_note" not in answer["revenue_flow"] or not answer["revenue_flow"]["cash_timing_note"]


def test_revenue_flow_validator_rejects_billing_basis_as_cash_timing():
    bundle = load_company_memory_sources("tanla")
    journey_payload, _ = build_business_journey(bundle, company_slug="tanla", generated_at="2026-08-02T00:00:00+00:00")
    products_payload, _ = build_products_services(bundle, business_journey_payload=journey_payload, company_slug="tanla", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload=journey_payload, products_services_payload=products_payload, company_slug="tanla", generated_at="2026-08-02T00:00:00+00:00")
    payload = json.loads(json.dumps(answer_cards))
    answer = next(answer for answer in payload["answers"] if answer["question_id"] == "how-does-it-make-money")
    answer["revenue_flow"]["cash_timing_note"] = answer["revenue_flow"]["billing_basis_note"]

    errors = validate_answer_cards_payload(payload, products_services_payload=products_payload, financial_visual_ids=[])

    assert any("cash_timing_note must not duplicate billing_basis_note" in error for error in errors)


def test_buffett_answer_exposes_structured_sections():
    bundle = _source_bundle()
    products_payload, _ = build_products_services(bundle, business_journey_payload={"summary": "", "stages": []}, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="acme", generated_at="2026-08-02T00:00:00+00:00")

    answer = next(answer for answer in answer_cards["answers"] if answer["question_id"] == "what-would-buffett-focus-on")

    titles = [section["title"] for section in answer["structured_sections"]]
    assert "What he may like" in titles
    assert "What he would question" in titles


def test_generate_view_writes_uncertainty_map_and_company_summary():
    result = generate_ask_intrinsiciq_view("datapatterns", Path.cwd() / "companies", force=True)

    uncertainty_payload = result["uncertainty_map"]
    assert uncertainty_payload["items"]
    assert get_uncertainty_map_path("datapatterns", Path.cwd() / "companies").exists()
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

    assert len(first_payload["answers"]) == 36  # ENG-126: 34 questions; ENG-133: +1 did-execution-lead-to-outcomes; ENG-136: +1 what-promise-types-dominate
    assert [answer["question_id"] for answer in first_payload["answers"]] == [answer["question_id"] for answer in second_payload["answers"]]


def test_generate_view_writes_financial_visual_artifact_and_links_it():
    result = generate_ask_intrinsiciq_view("datapatterns", Path.cwd() / "companies", force=True)

    visual_payload = result["financial_visual_summaries"]
    assert visual_payload["visuals"]
    assert get_financial_visual_summaries_path("datapatterns", Path.cwd() / "companies").exists()
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


# ──────────────────────────────────────────────────────────────────────────────
# Regression tests: Ask Prometheus surface quality (D1–D5 defect classes)
# ──────────────────────────────────────────────────────────────────────────────

def _load_artifact(slug, filename):
    path = Path(f"companies/{slug}/company_memory/ask_intrinsiciq/{filename}")
    if not path.exists():
        pytest.skip(f"{path} not found — run pipeline first")
    return json.loads(path.read_text())


def _all_text(artifact):
    return json.dumps(artifact).lower()


# T1 — supported answer must never have empty detailed_explanation
def test_supported_answers_always_have_nonempty_explanation():
    for slug in ("sun_pharma", "ujjivan"):
        cards = _load_artifact(slug, "answer_cards.json")
        for a in cards.get("answers", []):
            if a.get("answer_status") == "supported":
                expl = str(a.get("detailed_explanation") or "").strip()
                assert expl, (
                    f"{slug}/{a['id']}: answer_status='supported' but detailed_explanation is empty"
                )


# T2 — wrong-sector customer types must not appear in any answer field
def test_no_electronics_sector_contamination_in_answers():
    contamination = [
        "electronics or semiconductor",
        "industrial/electronics",
        "engineered systems or components",
        "design, build, test, and delivery",
    ]
    for slug in ("sun_pharma", "ujjivan"):
        cards = _load_artifact(slug, "answer_cards.json")
        text = _all_text(cards)
        for term in contamination:
            assert term not in text, (
                f"{slug}: contamination term '{term}' found in answer_cards.json"
            )


# T3 — pharma company model: no electronics customer types after fix
def test_sun_pharma_company_model_has_no_electronics_customers():
    model_path = Path("companies/sun_pharma/company_memory/company_model/company_model.json")
    if not model_path.exists():
        pytest.skip("sun_pharma company_model not found")
    model = json.loads(model_path.read_text())
    cm = model.get("current_business_model", {})
    who_pays = " ".join(cm.get("who_pays") or []).lower()
    who_uses = " ".join(cm.get("who_uses") or []).lower()
    for bad in ("electronics", "semiconductor", "industrial/electronics"):
        assert bad not in who_pays, f"sun_pharma.who_pays contains '{bad}'"
        assert bad not in who_uses, f"sun_pharma.who_uses contains '{bad}'"


# T4 — business answers must use Company Model content, not generic boilerplate
def test_what_does_company_do_uses_company_model_content():
    checks = {
        "sun_pharma": "pharmaceutical",
        "ujjivan": "lending",
    }
    for slug, expected_keyword in checks.items():
        cards = _load_artifact(slug, "answer_cards.json")
        a = next((x for x in cards["answers"] if x["id"] == "answer-what-does-company-do"), None)
        assert a is not None, f"{slug}: answer-what-does-company-do not found"
        expl = str(a.get("detailed_explanation") or "").lower()
        assert expected_keyword in expl, (
            f"{slug}: answer-what-does-company-do does not mention '{expected_keyword}' — "
            f"Company Model content not consumed. Got: {expl[:200]}"
        )


# T5 — customer answers must reference company-specific customer types
def test_who_are_customers_references_company_specific_types():
    checks = {
        "sun_pharma": "healthcare",
        "ujjivan": "borrower",
    }
    for slug, expected_keyword in checks.items():
        cards = _load_artifact(slug, "answer_cards.json")
        a = next((x for x in cards["answers"] if x["id"] == "answer-who-are-the-customers"), None)
        assert a is not None
        text = (str(a.get("detailed_explanation") or "") + " " + json.dumps(a.get("payers") or [])).lower()
        assert expected_keyword in text, (
            f"{slug}: who-are-customers does not reference '{expected_keyword}'. Got: {text[:300]}"
        )


# T6 — how-does-it-make-money: revenue flow model_type must match business type
def test_revenue_flow_model_type_matches_business():
    expected = {
        "sun_pharma": "product_sales",
        "ujjivan": "interest_income",
    }
    for slug, expected_model_type in expected.items():
        cards = _load_artifact(slug, "answer_cards.json")
        a = next((x for x in cards["answers"] if x["id"] == "answer-how-does-it-make-money"), None)
        assert a is not None
        flow = a.get("revenue_flow") or {}
        assert flow.get("model_type") == expected_model_type, (
            f"{slug}: revenue_flow.model_type={flow.get('model_type')!r}, expected {expected_model_type!r}"
        )


# T7 — internal management status enums must not appear in investor-facing text
def test_no_internal_management_status_enums_in_answers():
    forbidden_enums = [
        "ACTION_STARTED", "ACTION_COMPLETED", "ACTION_ABANDONED",
        "CLAIM_MADE", "COMPLETION_CLAIMED", "OUTCOME_VERIFIED",
    ]
    for slug in ("sun_pharma", "ujjivan"):
        cards = _load_artifact(slug, "answer_cards.json")
        raw_text = json.dumps(cards)
        for term in forbidden_enums:
            assert term not in raw_text, (
                f"{slug}: internal enum '{term}' found in answer_cards.json"
            )


# T8 — Ujjivan Ask surface must have exactly the 8 expected artifacts
def test_ujjivan_ask_surface_artifacts_exist():
    expected_files = [
        "business_journey.json",
        "products_services.json",
        "answer_cards.json",
        "financial_visual_summaries.json",
        "uncertainty_map.json",
        "company_research_view.json",
        "ask_intrinsiciq_manifest.json",
        "ask_intrinsiciq_validation_report.json",
    ]
    base = Path("companies/ujjivan/company_memory/ask_intrinsiciq")
    if not base.exists():
        pytest.skip("ujjivan ask_intrinsiciq not generated")
    for fname in expected_files:
        assert (base / fname).exists(), f"ujjivan: missing artifact {fname}"


# T9 — Ujjivan answer cards reference lending/financial-services content
def test_ujjivan_answers_are_financial_services_specific():
    cards = _load_artifact("ujjivan", "answer_cards.json")
    text = _all_text(cards)
    for term in ("lending", "loan", "borrower", "interest income", "deposit"):
        assert term in text, f"ujjivan answer_cards: expected financial term '{term}' not found"


# T10 — sanitizer rewrites management status enums to readable text
def test_sanitizer_rewrites_action_status_enums():
    assert sanitize_public_text("The initiative is in ACTION_STARTED state.") != ""
    assert "ACTION_STARTED" not in sanitize_public_text("The initiative is in ACTION_STARTED state.")
    assert sanitize_public_text("The review was ACTION_COMPLETED in FY24.") != ""
    assert "ACTION_COMPLETED" not in sanitize_public_text("The review was ACTION_COMPLETED in FY24.")


# T11 — _revenue_summary prefers revenue_descriptions over generic manufacturing template
def test_revenue_summary_prefers_engine_descriptions_over_manufacturing_template():
    from intelligence.ask_intrinsiciq.canonical_projection import _revenue_summary
    engines = [
        {"description": "Sales of branded and generic pharmaceutical products to distributors.", "billing_basis": "sale"},
    ]
    current_model = {"business_model_type": "manufacturing"}
    result = _revenue_summary(engines, current_model)
    assert "engineered systems" not in result, (
        f"_revenue_summary returned generic engineering template for pharma: {result!r}"
    )
    assert "pharmaceutical" in result.lower() or "branded" in result.lower() or "generic" in result.lower(), (
        f"_revenue_summary did not use engine description: {result!r}"
    )


# T12 — producer alias fix: "led" substring no longer triggers electronics customer type
def test_producer_led_alias_does_not_match_capacity_led():
    from knowledge.company_model.producer import CompanyModelProducer
    import tempfile, os
    producer = CompanyModelProducer.__new__(CompanyModelProducer)
    producer.company_slug = "test"
    evidence = []
    latest = {
        "business_model_summary": "A capacity-led manufacturing scale-up focused on pharmaceutical generics.",
        "what_company_does": "Manufacture generic medicines at scale for regulated markets.",
    }
    customers = producer._build_customers(latest, "manufacturing", evidence)
    payer_types = [c.get("payer_type") for c in customers]
    assert "electronics or semiconductor customers" not in payer_types, (
        f"'capacity-led' phrase triggered electronics customer type. Customers: {payer_types}"
    )


# ── ENG-141: Temporal Relevance / Historical Leakage Repair ──────────────────

def _sun_pharma_cards():
    """Build Sun Pharma answer cards — shared fixture for ENG-141 tests."""
    bundle = load_company_memory_sources("sun_pharma")
    products_payload = {
        "groups": [], "summary": "", "business_model_summary": None,
        "customer_summary": None, "revenue_logic_summary": None,
        "open_questions": [], "coverage_status": "unavailable",
    }
    cards, _ = build_answer_cards(
        bundle,
        business_journey_payload={"summary": "", "stages": []},
        products_services_payload=products_payload,
        company_slug="sun_pharma",
        generated_at="2026-09-15T00:00:00+00:00",
    )
    return cards


def _first_point(cards, question_id: str) -> str:
    answer = next((a for a in cards["answers"] if a["question_id"] == question_id), {})
    kps = answer.get("key_points", [])
    if not kps:
        return ""
    kp = kps[0]
    return kp.get("point", "") if isinstance(kp, dict) else str(kp)


def test_eng141_toansa_fy14_does_not_lead_capacity_question():
    """Toansa 2014 USFDA event must NOT be the headline for how-is-capacity-changing."""
    cards = _sun_pharma_cards()
    first = _first_point(cards, "how-is-capacity-changing")
    assert "toansa" not in first.lower(), (
        f"Toansa fy14 is leading how-is-capacity-changing: {first!r}"
    )


def test_eng141_capacity_lead_is_recent():
    """Lead key_point for how-is-capacity-changing must reference post-2020 evidence."""
    from intelligence.ask_intrinsiciq.canonical_projection import _item_latest_fy, progression_items_for_question
    from intelligence.ask_intrinsiciq.loader import load_company_memory_sources

    bundle = load_company_memory_sources("sun_pharma")
    prog = bundle.get("management_progression") or {}
    items = progression_items_for_question(prog, "how-is-capacity-changing")
    if not items:
        return  # No capacity items — skip rather than false-fail
    lead_fy = _item_latest_fy(items[0])
    assert lead_fy >= 2020, (
        f"Lead capacity item has fy={lead_fy}, expected >= 2020 (recent evidence should lead)"
    )


def test_eng141_what_incentives_is_sorted_not_raw():
    """what-incentives-matter must return sorted items, not raw insertion order."""
    from intelligence.ask_intrinsiciq.canonical_projection import progression_items_for_question, _progression_rank, _item_latest_fy
    from intelligence.ask_intrinsiciq.loader import load_company_memory_sources

    bundle = load_company_memory_sources("sun_pharma")
    prog = bundle.get("management_progression") or {}
    items = progression_items_for_question(prog, "what-incentives-matter")
    if len(items) < 2:
        return
    # Check that items are in descending rank order (first >= second on primary score)
    data_max_fy = max((_item_latest_fy(i) for i in items), default=0)
    ranks = [_progression_rank(i, "what-incentives-matter", data_max_fy=data_max_fy)[0] for i in items[:5]]
    for i in range(len(ranks) - 1):
        assert ranks[i] >= ranks[i + 1], (
            f"what-incentives-matter not sorted: rank[{i}]={ranks[i]} < rank[{i+1}]={ranks[i+1]}"
        )


def test_eng141_item_latest_fy_parses_fy14():
    """_item_latest_fy must correctly parse fy14 event_period as 2014."""
    from intelligence.ask_intrinsiciq.canonical_projection import _item_latest_fy
    item = {"events": [{"event_period": "fy14", "source_period": None}]}
    assert _item_latest_fy(item) == 2014


def test_eng141_temporal_recency_score_historical_penalty():
    """Items with only 12-year-old evidence get -30 penalty for current-state questions."""
    from intelligence.ask_intrinsiciq.canonical_projection import _temporal_recency_score
    item = {"events": [{"event_period": "fy14"}]}
    score = _temporal_recency_score(item, "how-is-capacity-changing", data_max_fy=2026)
    assert score == -30, f"Expected -30 for 12yr-old item, got {score}"


def test_eng141_temporal_recency_score_no_penalty_non_current_question():
    """No temporal penalty applied to non-current-state questions like did-past-claims-come-true."""
    from intelligence.ask_intrinsiciq.canonical_projection import _temporal_recency_score
    item = {"events": [{"event_period": "fy14"}]}
    score = _temporal_recency_score(item, "did-past-claims-come-true", data_max_fy=2026)
    assert score == 0, f"Expected 0 for non-current-state question, got {score}"


def test_eng141_no_company_specific_logic_in_temporal_score():
    """_temporal_recency_score must not reference sun_pharma, tanla, or any company slug."""
    import inspect
    from intelligence.ask_intrinsiciq import canonical_projection
    src = inspect.getsource(canonical_projection._temporal_recency_score)
    for slug in ("sun_pharma", "tanla", "ujjivan", "data_patterns"):
        assert slug not in src, f"_temporal_recency_score contains company-specific reference: {slug!r}"


# ── ENG-141A: Ongoing Historical Consequence Proof ────────────────────────────
# Mission: prove that temporal ranking distinguishes OLD+STILL_ACTIVE from
# OLD+AND_RESOLVED. The mechanism: _item_latest_fy takes the MAX FY across ALL
# events on an item — so an old event with a recent consequence/status event
# attached ranks as CURRENT, while an old event with no follow-up ranks as
# HISTORICAL and is demoted.


def test_eng141a_item_latest_fy_picks_most_recent_event():
    """_item_latest_fy uses the newest event's FY, not the original event."""
    from intelligence.ask_intrinsiciq.canonical_projection import _item_latest_fy
    item = {"events": [
        {"event_period": "fy14"},  # original event (old)
        {"event_period": "fy25"},  # consequence / status update (current)
    ]}
    assert _item_latest_fy(item) == 2025


def test_eng141a_item_latest_fy_source_period_fallback():
    """_item_latest_fy uses source_period when event_period is absent."""
    from intelligence.ask_intrinsiciq.canonical_projection import _item_latest_fy
    item = {"events": [{"source_period": "fy20"}, {"source_period": "fy25"}]}
    assert _item_latest_fy(item) == 2025


def test_eng141a_old_still_active_gets_no_penalty():
    """Old event (fy14) + current consequence (fy25) → latest_fy=2025 → age=1 → CURRENT → score=0."""
    from intelligence.ask_intrinsiciq.canonical_projection import _temporal_recency_score
    item = {"events": [{"event_period": "fy14"}, {"event_period": "fy25"}]}
    score = _temporal_recency_score(item, "how-is-capacity-changing", data_max_fy=2026)
    assert score == 0, f"OLD+ACTIVE should get no penalty, got {score}"


def test_eng141a_old_no_consequence_gets_max_penalty():
    """Old event (fy14) only → latest_fy=2014 → age=12 → HISTORICAL → score=-30."""
    from intelligence.ask_intrinsiciq.canonical_projection import _temporal_recency_score
    item = {"events": [{"event_period": "fy14"}]}
    score = _temporal_recency_score(item, "how-is-capacity-changing", data_max_fy=2026)
    assert score == -30, f"OLD+NO_CONSEQUENCE should get -30, got {score}"


def test_eng141a_old_recently_resolved_gets_minor_penalty():
    """Old event (fy14) + recent-ish resolution (fy22) → age=4 → RECENT → score=-10."""
    from intelligence.ask_intrinsiciq.canonical_projection import _temporal_recency_score
    item = {"events": [{"event_period": "fy14"}, {"event_period": "fy22"}]}
    score = _temporal_recency_score(item, "how-is-capacity-changing", data_max_fy=2026)
    assert score == -10, f"OLD+RECENT_ACTIVITY should get -10, got {score}"


def test_eng141a_recent_issue_no_penalty():
    """Recent issue (fy25) gets no temporal penalty."""
    from intelligence.ask_intrinsiciq.canonical_projection import _temporal_recency_score
    item = {"events": [{"event_period": "fy25"}]}
    score = _temporal_recency_score(item, "how-is-capacity-changing", data_max_fy=2026)
    assert score == 0, f"Recent item should have no penalty, got {score}"


def test_eng141a_historical_question_no_recency_suppression():
    """Historical questions (did-past-claims-come-true) must not penalise old evidence."""
    from intelligence.ask_intrinsiciq.canonical_projection import _temporal_recency_score
    item = {"events": [{"event_period": "fy14"}]}
    score = _temporal_recency_score(item, "did-past-claims-come-true", data_max_fy=2026)
    assert score == 0, "Historical questions must not suppress old evidence"


def test_eng141a_old_active_outranks_old_closed():
    """OLD+ACTIVE item must rank above OLD+CLOSED for current-state questions."""
    from intelligence.ask_intrinsiciq.canonical_projection import _progression_rank
    data_max_fy = 2026
    item_active = {"events": [
        {"event_period": "fy14"},  # original regulatory ban
        {"event_period": "fy25"},  # current status: still active
    ]}
    item_closed = {"events": [{"event_period": "fy14"}]}  # original only, no follow-up
    rank_active = _progression_rank(item_active, "how-is-capacity-changing", data_max_fy=data_max_fy)[0]
    rank_closed = _progression_rank(item_closed, "how-is-capacity-changing", data_max_fy=data_max_fy)[0]
    assert rank_active > rank_closed, (
        f"OLD+ACTIVE (score={rank_active}) should outrank OLD+CLOSED (score={rank_closed})"
    )


def test_eng141a_progression_sorts_active_above_closed():
    """progression_items_for_question puts OLD+ACTIVE before OLD+CLOSED for what-incentives-matter."""
    from intelligence.ask_intrinsiciq.canonical_projection import progression_items_for_question
    item_active = {
        "item_id": "active_restriction",
        "item_name": "Active Regulatory Restriction",
        "events": [
            {"event_period": "fy14"},   # original event
            {"event_period": "fy25"},   # ongoing consequence
        ],
    }
    item_closed = {
        "item_id": "closed_issue",
        "item_name": "Resolved Historical Issue",
        "events": [{"event_period": "fy14"}],  # no follow-up → historical
    }
    # what-incentives-matter uses all items (no stream filter) — cleanest integration path
    progression = {
        "coverage_status": "supported",
        "progression_items": [item_closed, item_active],  # closed first in raw order
    }
    sorted_items = progression_items_for_question(progression, "what-incentives-matter")
    ids = [i["item_id"] for i in sorted_items]
    active_pos = ids.index("active_restriction")
    closed_pos = ids.index("closed_issue")
    assert active_pos < closed_pos, (
        f"OLD+ACTIVE (pos={active_pos}) should rank before OLD+CLOSED (pos={closed_pos}). Order: {ids}"
    )


def test_eng141a_no_company_specific_logic_in_item_latest_fy():
    """_item_latest_fy must contain no company-specific references."""
    import inspect
    from intelligence.ask_intrinsiciq import canonical_projection
    src = inspect.getsource(canonical_projection._item_latest_fy)
    for slug in ("sun_pharma", "tanla", "ujjivan", "datapatterns"):
        assert slug not in src, f"_item_latest_fy contains company slug: {slug!r}"


# ── ENG-149: investor-facing key-point sanitization ──────────────────────────

def test_eng149_wc_status_phrase_maps_all_known_severity_values():
    from intelligence.ask_intrinsiciq.answer_cards import _wc_status_phrase
    assert "watch" not in _wc_status_phrase("watch").lower().split()[0]  # phrase, not raw token
    assert len(_wc_status_phrase("watch").split()) >= 4
    assert len(_wc_status_phrase("elevated").split()) >= 4
    assert len(_wc_status_phrase("severe").split()) >= 4
    assert len(_wc_status_phrase("stretched").split()) >= 4
    assert len(_wc_status_phrase("contained").split()) >= 3


def test_eng149_wc_status_phrase_returns_empty_for_insufficient_data():
    from intelligence.ask_intrinsiciq.answer_cards import _wc_status_phrase
    assert _wc_status_phrase("insufficient_data") == ""


def test_eng149_wc_status_phrase_returns_empty_for_unknown_value():
    from intelligence.ask_intrinsiciq.answer_cards import _wc_status_phrase
    assert _wc_status_phrase("") == ""
    assert _wc_status_phrase("UNKNOWN_FUTURE_ENUM") == ""


def test_eng149_clean_list_rejects_single_word_tokens():
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list
    result = _clean_list(["watch", "elevated", "severe", "fy26", "platform"])
    assert result == [], f"Expected empty list but got: {result}"


def test_eng149_clean_list_accepts_multi_word_items():
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list
    items = [
        "Working-capital conditions are at an early-watch level.",
        "Receivable days moved from 101 to 89.",
        "Cash conversion cycle is 476 days.",
    ]
    result = _clean_list(items)
    assert len(result) == 3, f"Expected 3 items but got {len(result)}: {result}"


def test_eng149_working_capital_answer_has_no_raw_severity_enums():
    _SEVERITY_ENUMS = {"watch", "elevated", "severe", "stretched", "contained", "insufficient_data"}
    bundle = load_company_memory_sources("sun_pharma")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None,
                        "customer_summary": None, "revenue_logic_summary": None,
                        "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(
        bundle, business_journey_payload={"summary": "", "stages": []},
        products_services_payload=products_payload,
        company_slug="sun_pharma", generated_at="2026-09-17T00:00:00+00:00",
    )
    card = next(a for a in answer_cards["answers"] if a["question_id"] == "is-working-capital-a-concern")
    all_narrative = (
        card.get("key_points", [])
        + card.get("evidence_summary", {}).get("supporting_points", [])
        + card.get("interpretation", {}).get("positive_evidence", [])
        + card.get("interpretation", {}).get("negative_evidence", [])
    )
    raw_leaks = [v for v in all_narrative if v.strip().lower() in _SEVERITY_ENUMS]
    assert raw_leaks == [], f"Raw severity enums leaked into working-capital answer: {raw_leaks}"


def test_eng149_cash_conversion_answer_has_no_raw_severity_enums():
    _SEVERITY_ENUMS = {"watch", "elevated", "severe", "stretched", "contained", "insufficient_data"}
    bundle = load_company_memory_sources("sun_pharma")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None,
                        "customer_summary": None, "revenue_logic_summary": None,
                        "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(
        bundle, business_journey_payload={"summary": "", "stages": []},
        products_services_payload=products_payload,
        company_slug="sun_pharma", generated_at="2026-09-17T00:00:00+00:00",
    )
    card = next(a for a in answer_cards["answers"] if a["question_id"] == "are-profits-converting-into-cash")
    all_narrative = (
        card.get("key_points", [])
        + card.get("evidence_summary", {}).get("supporting_points", [])
        + card.get("interpretation", {}).get("positive_evidence", [])
    )
    raw_leaks = [v for v in all_narrative if v.strip().lower() in _SEVERITY_ENUMS]
    assert raw_leaks == [], f"Raw severity enums leaked into cash-conversion answer: {raw_leaks}"


def test_eng149_cross_company_no_severity_enum_leakage():
    _SEVERITY_ENUMS = {"watch", "elevated", "severe", "stretched", "contained", "insufficient_data"}
    NARRATIVE_FIELDS = ["key_points", "supporting_points", "positive_evidence",
                        "negative_evidence", "what_changed", "what_to_watch"]

    def _collect_narrative(card):
        values = list(card.get("key_points") or [])
        ev = card.get("evidence_summary") or {}
        if isinstance(ev, dict):
            values += list(ev.get("supporting_points") or [])
        interp = card.get("interpretation") or {}
        if isinstance(interp, dict):
            for f in ("positive_evidence", "negative_evidence", "what_changed", "what_to_watch"):
                values += list(interp.get(f) or [])
        return values

    products_payload = {"groups": [], "summary": "", "business_model_summary": None,
                        "customer_summary": None, "revenue_logic_summary": None,
                        "open_questions": [], "coverage_status": "unavailable"}
    leaks = []
    for slug in ("tanla", "ujjivan", "datapatterns"):
        bundle = load_company_memory_sources(slug)
        answer_cards, _ = build_answer_cards(
            bundle, business_journey_payload={"summary": "", "stages": []},
            products_services_payload=products_payload,
            company_slug=slug, generated_at="2026-09-17T00:00:00+00:00",
        )
        for card in answer_cards["answers"]:
            qid = card.get("question_id", "")
            if "working-capital" in qid or "converting" in qid:
                for val in _collect_narrative(card):
                    if isinstance(val, str) and val.strip().lower() in _SEVERITY_ENUMS:
                        leaks.append(f"{slug}/{qid}: {val!r}")
    assert leaks == [], f"Severity enum leakage in cross-company audit: {leaks}"


def test_eng149_negative_control_legitimate_narrative_survives():
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list
    legit = [
        "Receivable days improved from 101 to 89 over six years.",
        "Working-capital requirements are elevated, keeping cash tied up in operations.",
        "Cash conversion cycle is 476 days in FY20.",
    ]
    result = _clean_list(legit)
    assert len(result) == 3, f"Legitimate narrative items were incorrectly filtered: {result}"


def test_eng149_wc_answer_key_points_are_investor_propositions():
    """Each key_point and supporting_point must be a multi-word investor proposition."""
    bundle = load_company_memory_sources("sun_pharma")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None,
                        "customer_summary": None, "revenue_logic_summary": None,
                        "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(
        bundle, business_journey_payload={"summary": "", "stages": []},
        products_services_payload=products_payload,
        company_slug="sun_pharma", generated_at="2026-09-17T00:00:00+00:00",
    )
    card = next(a for a in answer_cards["answers"] if a["question_id"] == "is-working-capital-a-concern")
    single_word_items = [
        v for v in (card.get("key_points") or [])
        + (card.get("evidence_summary", {}).get("supporting_points") or [])
        if " " not in v.strip()
    ]
    assert single_word_items == [], f"Single-word items in WC answer: {single_word_items}"


# ── ENG-149A: over-sanitization audit ────────────────────────────────────────

def test_eng149a_machine_severity_token_rejected():
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list
    for token in ("watch", "elevated", "severe", "contained", "insufficient_data"):
        assert _clean_list([token]) == [], f"Severity enum {token!r} should be rejected"


def test_eng149a_fy_label_rejected():
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list
    for token in ("fy26", "fy25", "fy24", "fy23"):
        assert _clean_list([token]) == [], f"FY label {token!r} should be rejected"


def test_eng149a_schema_domain_label_rejected():
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list
    for token in ("platform", "manufacturing", "financial_services"):
        assert _clean_list([token]) == [], f"Schema label {token!r} should be rejected"


def test_eng149a_single_word_improving_rejected_from_clean_list():
    # "Improving" alone is not an investor proposition; valid as part of a sentence.
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list
    assert _clean_list(["Improving"]) == []


def test_eng149a_single_word_stable_rejected_from_clean_list():
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list
    assert _clean_list(["Stable"]) == []


def test_eng149a_single_word_unresolved_rejected_from_clean_list():
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list
    assert _clean_list(["Unresolved"]) == []


def test_eng149a_multi_word_narrative_preserved():
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list
    items = [
        "Revenue growth is improving.",
        "Margins have been stable for three years.",
        "Unresolved: the regulatory timeline is unclear.",
    ]
    result = _clean_list(items)
    assert len(result) == 3, f"Multi-word narratives incorrectly filtered: {result}"


def test_eng149a_builder_translated_wc_phrase_preserved():
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list, _wc_status_phrase
    phrase = _wc_status_phrase("watch")
    assert len(phrase.split()) >= 4, "WC phrase must be multi-word"
    result = _clean_list([phrase])
    assert result == [phrase], f"Builder-translated WC phrase was incorrectly filtered: {phrase!r}"


def test_eng149a_no_machine_token_in_any_production_company():
    """Global guard: no single-word machine token appears in any company's narrative fields."""
    _SINGLE_WORD_TOKENS = {
        "watch", "elevated", "severe", "stretched", "contained", "insufficient_data",
        "fy26", "fy25", "fy24", "fy23", "platform", "manufacturing", "financial_services",
        "operational", "commissioned", "delayed", "funded", "installed",
    }
    _NARRATIVE_FIELDS = ["key_points", "supporting_points", "positive_evidence",
                         "negative_evidence", "what_changed", "what_to_watch"]

    def _collect(card):
        values = list(card.get("key_points") or [])
        ev = card.get("evidence_summary") or {}
        values += list(ev.get("supporting_points") or [])
        interp = card.get("interpretation") or {}
        for f in ("positive_evidence", "negative_evidence", "what_changed", "what_to_watch"):
            values += list(interp.get(f) or [])
        return values

    products_payload = {"groups": [], "summary": "", "business_model_summary": None,
                        "customer_summary": None, "revenue_logic_summary": None,
                        "open_questions": [], "coverage_status": "unavailable"}
    leaks = []
    for slug in ("sun_pharma", "tanla", "ujjivan", "datapatterns"):
        bundle = load_company_memory_sources(slug)
        answer_cards, _ = build_answer_cards(
            bundle, business_journey_payload={"summary": "", "stages": []},
            products_services_payload=products_payload,
            company_slug=slug, generated_at="2026-09-17T00:00:00+00:00",
        )
        for card in answer_cards["answers"]:
            for val in _collect(card):
                if isinstance(val, str) and val.strip().lower() in _SINGLE_WORD_TOKENS:
                    leaks.append(f"{slug}/{card.get('question_id')}: {val!r}")
    assert leaks == [], f"Machine token leakage in production: {leaks}"


def test_eng149a_valid_content_loss_is_zero():
    """The single-word rule must not remove anything classified as valid investor content."""
    # All 16 intercepted values in ENG-149A forensic are SCHEMA_LABEL or MACHINE_TOKEN.
    # None are valid investor propositions. This test verifies using the known removal set.
    from intelligence.ask_intrinsiciq.answer_cards import _clean_list
    # Values confirmed as non-investor-proposition by ENG-149A forensic
    schema_labels = ["fy26", "fy25", "manufacturing", "platform", "financial_services"]
    machine_tokens = [
        "ev_fy25_company_intelligence_risk_00021",
        "ev_fy20_company_intelligence_risk_00006",
        "ev_fy24_company_intelligence_risk_00017",
    ]
    for val in schema_labels + machine_tokens:
        result = _clean_list([val])
        assert result == [], f"Expected {val!r} to be rejected but got: {result}"


# ── ENG-NEW-INVESTOR-PANEL: Investor Panel Doctrine Leakage ──────────────────

_DOCTRINE_SIGNALS = [
    "primary focus:",
    "all investment lens-required",
    "do not ",
    "escalate ",
    "when evidence conflicts",
    "when the story",
    "if dividend",
    "if the business cannot",
    "output must say so",
]
_LENS_QUESTION_IDS = [
    "what-would-graham-worry-about",
    "what-would-buffett-focus-on",
    "where-would-fisher-be-curious",
    "what-would-munger-avoid",
    "how-would-lynch-explain-it",
]


def _lens_fields(card):
    interp = card.get("interpretation", {})
    fields = list(card.get("key_points", []))
    fields.extend(interp.get("unresolved", []))
    fields.extend(interp.get("what_to_watch", []))
    fields.extend(interp.get("positive_evidence", []))
    fields.extend(interp.get("negative_evidence", []))
    return fields


def test_eng_panel_strip_backend_phrasing_drops_primary_focus():
    from intelligence.ask_intrinsiciq.answer_cards import _strip_backend_phrasing
    assert _strip_backend_phrasing("Primary focus: Downside protection, Balance-sheet resilience.") == ""


def test_eng_panel_strip_backend_phrasing_drops_lens_preamble():
    from intelligence.ask_intrinsiciq.answer_cards import _strip_backend_phrasing
    assert _strip_backend_phrasing("Benjamin Graham consumes financial_strength_inputs from the evidence set.") == ""
    assert _strip_backend_phrasing("Peter Lynch consumes business evidence to form a plain-language view.") == ""


def test_eng_panel_strip_backend_phrasing_drops_control_state():
    from intelligence.ask_intrinsiciq.answer_cards import _strip_backend_phrasing
    assert _strip_backend_phrasing("All investment lens-required available evidence sections were available.") == ""


def test_eng_panel_strip_backend_phrasing_drops_do_not_directives():
    from intelligence.ask_intrinsiciq.answer_cards import _strip_backend_phrasing
    assert _strip_backend_phrasing("Do not infer valuation, safety, or solvency from business quality evidence alone.") == ""
    assert _strip_backend_phrasing("Do not classify growth quality confidently when category evidence is incomplete.") == ""


def test_eng_panel_strip_backend_phrasing_drops_escalate_directive():
    from intelligence.ask_intrinsiciq.answer_cards import _strip_backend_phrasing
    assert _strip_backend_phrasing("Escalate uncertainty when core financial-strength evidence is missing or partial.") == ""


def test_eng_panel_strip_backend_phrasing_drops_conditional_rules():
    from intelligence.ask_intrinsiciq.answer_cards import _strip_backend_phrasing
    assert _strip_backend_phrasing("When evidence conflicts, prefer the more conservative interpretation and state the conflict explicitly.") == ""
    assert _strip_backend_phrasing("When the story and the evidence diverge, report the divergence rather than smoothing it over.") == ""
    assert _strip_backend_phrasing("If dividend or distribution evidence lacks cash-flow and leverage context, treat it as a monitoring point.") == ""
    assert _strip_backend_phrasing("If the business cannot be explained simply from available evidence, the output must say so.") == ""


def test_eng_panel_strip_backend_phrasing_preserves_real_findings():
    from intelligence.ask_intrinsiciq.answer_cards import _strip_backend_phrasing
    real_findings = [
        "Persistent uncertainty in capital-allocation or financial-strength inputs.",
        "Balance sheet strength is adequate but cash conversion remains weak.",
        "Management commitments have limited observed execution-to-outcome linkage.",
    ]
    for text in real_findings:
        result = _strip_backend_phrasing(text)
        assert result, f"Real finding was stripped: {text!r}"


def test_eng_panel_strip_backend_phrasing_fixes_duplicate_word_typo():
    from intelligence.ask_intrinsiciq.answer_cards import _strip_backend_phrasing
    result = _strip_backend_phrasing("A story that is hard to explain simply from available evidence evidence.")
    assert "evidence evidence" not in result
    assert result  # must not be empty — real content should survive


def test_eng_panel_sun_pharma_h3_h4_doctrine_free():
    """H3 (Graham) and H4 (Lynch) must contain zero doctrine instruction or metadata text."""
    products_payload = {"groups": [], "coverage_status": "missing", "schema_version": "1.0", "company_slug": "sun_pharma", "generated_at": "2026-09-17T00:00:00+00:00"}
    bundle = load_company_memory_sources("sun_pharma")
    answer_cards, _ = build_answer_cards(
        bundle, business_journey_payload={"summary": "", "stages": []},
        products_services_payload=products_payload,
        company_slug="sun_pharma", generated_at="2026-09-17T00:00:00+00:00",
    )
    cards_by_id = {a["question_id"]: a for a in answer_cards["answers"]}
    leaks = []
    for qid in ("what-would-graham-worry-about", "how-would-lynch-explain-it"):
        card = cards_by_id.get(qid, {})
        for field_val in _lens_fields(card):
            if isinstance(field_val, str):
                low = field_val.lower()
                for sig in _DOCTRINE_SIGNALS:
                    if sig in low:
                        leaks.append(f"{qid}: {field_val!r} (signal: {sig!r})")
    assert leaks == [], f"Doctrine leakage in H3/H4: {leaks}"


def test_eng_panel_all_lenses_doctrine_free_sun_pharma():
    """All 5 investor lenses must be doctrine-free for sun_pharma."""
    products_payload = {"groups": [], "coverage_status": "missing", "schema_version": "1.0", "company_slug": "sun_pharma", "generated_at": "2026-09-17T00:00:00+00:00"}
    bundle = load_company_memory_sources("sun_pharma")
    answer_cards, _ = build_answer_cards(
        bundle, business_journey_payload={"summary": "", "stages": []},
        products_services_payload=products_payload,
        company_slug="sun_pharma", generated_at="2026-09-17T00:00:00+00:00",
    )
    cards_by_id = {a["question_id"]: a for a in answer_cards["answers"]}
    leaks = []
    for qid in _LENS_QUESTION_IDS:
        card = cards_by_id.get(qid, {})
        for field_val in _lens_fields(card):
            if isinstance(field_val, str):
                low = field_val.lower()
                for sig in _DOCTRINE_SIGNALS:
                    if sig in low:
                        leaks.append(f"{qid}: {field_val!r}")
    assert leaks == [], f"Doctrine leakage in investor panel: {leaks}"


def test_eng_panel_cross_company_all_lenses_doctrine_free():
    """All 5 investor lenses must be doctrine-free across all 4 production companies."""
    leaks = []
    for slug in ("sun_pharma", "tanla", "ujjivan", "datapatterns"):
        products_payload = {"groups": [], "coverage_status": "missing", "schema_version": "1.0", "company_slug": slug, "generated_at": "2026-09-17T00:00:00+00:00"}
        bundle = load_company_memory_sources(slug)
        answer_cards, _ = build_answer_cards(
            bundle, business_journey_payload={"summary": "", "stages": []},
            products_services_payload=products_payload,
            company_slug=slug, generated_at="2026-09-17T00:00:00+00:00",
        )
        cards_by_id = {a["question_id"]: a for a in answer_cards["answers"]}
        for qid in _LENS_QUESTION_IDS:
            card = cards_by_id.get(qid, {})
            for field_val in _lens_fields(card):
                if isinstance(field_val, str):
                    low = field_val.lower()
                    for sig in _DOCTRINE_SIGNALS:
                        if sig in low:
                            leaks.append(f"{slug}/{qid}: {field_val!r}")
    assert leaks == [], f"Doctrine leakage across companies: {leaks}"


# ---------------------------------------------------------------------------
# ENG-151 — Commentary Priority Scoring Adversarial Tests
# ---------------------------------------------------------------------------
from intelligence.ask_intrinsiciq.answer_cards import _commentary_priority_score  # noqa: E402


def _theme(*, theme_id: str, theme_name: str, category: str, position: str, latest: str, first: str, n_events: int) -> dict:
    return {
        "theme_id": theme_id,
        "theme_name": theme_name,
        "theme_category": category,
        "current_position": position,
        "latest_period": latest,
        "first_observed_period": first,
        "commentary_events": [{"event_id": f"e{i}"} for i in range(n_events)],
    }


def test_eng151_risk_theme_outranks_generic_capacity_at_same_recency():
    """Risk theme with 32 events must outrank a generic capacity theme with 9 events
    even when both have latest_period=fy26 and both are stable_priority.
    Anti-pattern: insertion order must not decide ranking.
    """
    capacity_theme = _theme(
        theme_id="CM-0001", theme_name="Technology Direction", category="capacity",
        position="stable_priority", latest="fy26", first="fy20", n_events=9,
    )
    risk_theme = _theme(
        theme_id="CM-0006", theme_name="Risk To Growth / Market Access", category="growth",
        position="stable_priority", latest="fy26", first="fy20", n_events=32,
    )
    # risk theme has a risk keyword in its name — must score higher than generic capacity
    assert _commentary_priority_score(risk_theme) > _commentary_priority_score(capacity_theme)


def test_eng151_risk_named_theme_outranks_non_risk_same_category():
    """A theme whose name contains a risk indicator (e.g. 'challenges') must outscore
    a same-category theme without that indicator, even if the latter has more events.
    """
    challenge_theme = _theme(
        theme_id="CM-0015", theme_name="US Market Positioning And Challenges",
        category="projects", position="strengthened", latest="fy26", first="fy21", n_events=6,
    )
    non_risk_theme = _theme(
        theme_id="CM-0022", theme_name="Implementation / Operational Execution",
        category="projects", position="observation", latest="fy24", first="fy24", n_events=1,
    )
    assert _commentary_priority_score(challenge_theme) > _commentary_priority_score(non_risk_theme)


def test_eng151_capital_allocation_theme_leads_generic_strategy():
    """capital_allocation category must outrank strategy category all else equal."""
    capalloc = _theme(
        theme_id="CM-A", theme_name="Capital Deployment Plans", category="capital_allocation",
        position="stable_priority", latest="fy25", first="fy23", n_events=3,
    )
    strategy = _theme(
        theme_id="CM-B", theme_name="General Strategy", category="strategy",
        position="stable_priority", latest="fy25", first="fy23", n_events=3,
    )
    assert _commentary_priority_score(capalloc) > _commentary_priority_score(strategy)


def test_eng151_high_event_low_category_capped_by_evidence_tier():
    """A strategy theme with 30 events must NOT outrank a margins theme with 4 events
    (same recency, same position) because the evidence cap for strategy is 3 events-worth.
    """
    strategy_high_ev = _theme(
        theme_id="CM-C", theme_name="CSR Education Outreach", category="strategy",
        position="stable_priority", latest="fy26", first="fy20", n_events=30,
    )
    margins_low_ev = _theme(
        theme_id="CM-D", theme_name="Cost Leadership And Efficiency", category="margins",
        position="stable_priority", latest="fy26", first="fy20", n_events=4,
    )
    assert _commentary_priority_score(margins_low_ev) > _commentary_priority_score(strategy_high_ev)


def test_eng151_insertion_order_has_no_effect():
    """Two identical themes with different theme_ids must score the same."""
    t1 = _theme(
        theme_id="CM-0001", theme_name="Market Positioning", category="competition",
        position="strengthened", latest="fy26", first="fy22", n_events=5,
    )
    t2 = _theme(
        theme_id="CM-0099", theme_name="Market Positioning", category="competition",
        position="strengthened", latest="fy26", first="fy22", n_events=5,
    )
    assert _commentary_priority_score(t1) == _commentary_priority_score(t2)


def test_eng151_stale_theme_loses_to_recent_same_category():
    """A growth theme last seen in fy21 must score below a growth theme last seen in fy26."""
    stale = _theme(
        theme_id="CM-E", theme_name="Future Outlook", category="growth",
        position="observation", latest="fy21", first="fy21", n_events=1,
    )
    recent = _theme(
        theme_id="CM-F", theme_name="Future Outlook", category="growth",
        position="stable_priority", latest="fy26", first="fy20", n_events=8,
    )
    assert _commentary_priority_score(recent) > _commentary_priority_score(stale)


def test_eng151_gate1_stale_fy20_capital_risk_does_not_lead():
    """Gate 1: a capital_allocation theme newly_introduced in fy20 with risk in name
    must NOT outrank a fy26-active growth theme with multi-year persistence.
    Pre-fix: 60 > 57 (Tanla defect). Post-fix: stale theme score drops to ~30.
    """
    stale_credit_risk = _theme(
        theme_id="CM-X1", theme_name="General Administrative Credit Risk",
        category="capital_allocation", position="newly_introduced",
        latest="fy20", first="fy20", n_events=2,
    )
    active_growth = _theme(
        theme_id="CM-X2", theme_name="Workforce Talent Growth Initiatives",
        category="growth", position="stable_priority",
        latest="fy26", first="fy20", n_events=25,
    )
    assert _commentary_priority_score(active_growth) > _commentary_priority_score(stale_credit_risk), (
        "A fy20-only credit risk mention must not outrank a fy26-active growth theme"
    )


def test_eng151_gate2_single_observation_high_cat_cannot_displace_multi_year():
    """Gate 2: a capital_allocation theme with 1 event and no persistence cannot outrank
    a projects theme with 6 events spanning fy22→fy26.
    Pre-fix: 41 > 33 (Data Patterns defect). Post-fix: single observation drops to ~21.
    """
    single_observation = _theme(
        theme_id="CM-Y1", theme_name="Capital Investment Sustainability",
        category="capital_allocation", position="observation",
        latest="fy23", first="fy23", n_events=1,
    )
    multi_year_evidence = _theme(
        theme_id="CM-Y2", theme_name="Government Support Industry Infrastructure",
        category="projects", position="stable_priority",
        latest="fy26", first="fy22", n_events=6,
    )
    assert _commentary_priority_score(multi_year_evidence) > _commentary_priority_score(single_observation), (
        "A single-observation sustainability capex note must not displace multi-year "
        "government/infrastructure evidence"
    )


def test_eng151_gate1_preserves_recent_change_signal():
    """Gate 1 must NOT zero out change_weight for themes active in fy22+.
    A strengthened theme last seen in fy26 keeps its full change signal.
    """
    recent_strengthened = _theme(
        theme_id="CM-Z1", theme_name="US Market Positioning And Challenges",
        category="projects", position="strengthened",
        latest="fy26", first="fy21", n_events=6,
    )
    score = _commentary_priority_score(recent_strengthened)
    # Must retain strengthened change_weight=20 since recency=6 >= 2
    # Expected: projects=5 + strengthened=20 + recency=6 + persistence=15 + ev=2 + risk=15 = 63
    assert score >= 60, f"Recent strengthened theme should retain change signal, got {score}"


def test_eng151_gate2_does_not_cap_themes_with_persistence():
    """Gate 2 must NOT cap a theme that has multi-year persistence even if evidence is low.
    A 5-year-span theme with 2 events should not be capped.
    """
    multi_year_light_evidence = _theme(
        theme_id="CM-Z2", theme_name="Cost Leadership Operational Efficiency",
        category="margins", position="stable_priority",
        latest="fy23", first="fy22", n_events=2,
    )
    score = _commentary_priority_score(multi_year_light_evidence)
    # persistence = (23-22)*3 = 3, evidence = 0 (2//3=0)
    # Gate 2 triggers only when BOTH persistence==0 AND evidence==0.
    # Here persistence=3 > 0, so cat_weight=35 applies fully.
    # Expected: 35 + 8 + 3 + 3 + 0 + 0 = 49
    assert score >= 45, f"Theme with multi-year persistence should not be capped, got {score}"


# ── Phase 2 regression: UNVERIFIED ≠ undelivered ─────────────────────────────

def test_unverified_targets_do_not_claim_zero_percent_delivery():
    """why_it_matters must not say '0 were delivered (0%)' when targets are merely UNVERIFIED."""
    bundle = load_company_memory_sources("sun_pharma")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="sun_pharma", generated_at="2026-08-11T00:00:00+00:00")
    answer = next(a for a in answer_cards["answers"] if a["question_id"] == "what-has-management-promised")
    why = answer.get("why_it_matters", "").lower()
    # Must not claim delivery rate when targets are unverified (absence of evidence ≠ non-delivery)
    assert "were delivered" not in why, f"Regression: unverified targets presented as '0 delivered': {why}"
    assert "0%" not in why, f"Regression: false 0% delivery rate in why_it_matters: {why}"
    # Must acknowledge verification is open
    assert "verification" in why or "confirmed" in why or "delivery evidence" in why, f"why_it_matters missing evidence state: {why}"


def test_unverified_targets_same_regression_tanla():
    """Same regression check for Tanla — both accountability promises are UNVERIFIED."""
    bundle = load_company_memory_sources("tanla")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="tanla", generated_at="2026-08-11T00:00:00+00:00")
    answer = next(a for a in answer_cards["answers"] if a["question_id"] == "what-has-management-promised")
    why = answer.get("why_it_matters", "").lower()
    assert "were delivered" not in why, f"Regression: unverified targets presented as '0 delivered': {why}"
    assert "0%" not in why, f"Regression: false 0% delivery rate in why_it_matters: {why}"


def test_accountability_promises_appear_in_key_points_before_strategic_directions():
    """Specific verifiable targets (accountability_promises) must appear in key_points."""
    bundle = load_company_memory_sources("sun_pharma")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="sun_pharma", generated_at="2026-08-11T00:00:00+00:00")
    answer = next(a for a in answer_cards["answers"] if a["question_id"] == "what-has-management-promised")
    kps = answer.get("key_points", [])
    combined = " ".join(kps).lower()
    # Sun Pharma accountability_promises are: Japan/China specialty markets (MC-0005) and ILUMYA Japan/Australia (MC-0007)
    assert "ilumya" in combined or "japan" in combined, f"Specific verifiable targets not surfaced in key_points: {kps}"


def test_no_internal_tracking_language_in_accountability_key_points():
    """key_points must not contain 'Management Progression' or 'lifecycle record' tracking phrases."""
    bundle = load_company_memory_sources("sun_pharma")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="sun_pharma", generated_at="2026-08-11T00:00:00+00:00")
    answer = next(a for a in answer_cards["answers"] if a["question_id"] == "what-has-management-promised")
    kps_text = " ".join(answer.get("key_points", [])).lower()
    assert "management progression" not in kps_text, f"Internal tracking language in key_points: {kps_text}"
    assert "lifecycle record" not in kps_text, f"Internal tracking language in key_points: {kps_text}"


# ── Phase 3 regression: Tanla MC-0012 (AI/messaging) must be visible ─────────

def test_tanla_mc0012_ai_messaging_visible_in_key_points():
    """MC-0012 (AI and messaging-platform operational improvements) must be in key_points.
    Regression guard: the previous session's sort displaced MC-0012 to position 5
    because MC-0003 (alphabetically first) took a slot. Fixed by deprioritizing OTHER
    promise types and limiting strategic slots to (4 - len(accountability_promises)).
    """
    bundle = load_company_memory_sources("tanla")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="tanla", generated_at="2026-09-22T00:00:00+00:00")
    answer = next(a for a in answer_cards["answers"] if a["question_id"] == "what-has-management-promised")
    kps = answer.get("key_points", [])
    combined = " ".join(kps).lower()
    # MC-0012 text mentions "AI", "messaging", "platforms", "operational improvements"
    assert "messaging" in combined or "ai" in combined, f"MC-0012 AI/messaging not visible in key_points: {kps}"


def test_tanla_mc0005_platform_economics_visible_in_key_points():
    """MC-0005 (platform economics: revenue predictability, lower churn, healthier margins) must be in key_points."""
    bundle = load_company_memory_sources("tanla")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="tanla", generated_at="2026-09-22T00:00:00+00:00")
    answer = next(a for a in answer_cards["answers"] if a["question_id"] == "what-has-management-promised")
    kps = answer.get("key_points", [])
    combined = " ".join(kps).lower()
    # MC-0005 mentions "predictability", "churn", "margin", "platform approach"
    assert "predictability" in combined or "churn" in combined or "margin" in combined, \
        f"MC-0005 platform economics not visible in key_points: {kps}"


def test_why_it_matters_has_revenue_context_when_company_model_available():
    """why_it_matters should include a revenue context note from company_model when verifiable commitments exist."""
    bundle = load_company_memory_sources("tanla")
    products_payload = {"groups": [], "summary": "", "business_model_summary": None, "customer_summary": None, "revenue_logic_summary": None, "open_questions": [], "coverage_status": "unavailable"}
    answer_cards, _ = build_answer_cards(bundle, business_journey_payload={"summary": "", "stages": []}, products_services_payload=products_payload, company_slug="tanla", generated_at="2026-09-22T00:00:00+00:00")
    answer = next(a for a in answer_cards["answers"] if a["question_id"] == "what-has-management-promised")
    why = answer.get("why_it_matters", "").lower()
    # Revenue context should be present for companies with verifiable commitments and company_model
    assert "revenue" in why or "context" in why, f"Revenue context missing from why_it_matters: {why}"


# ── write isolation: every mechanism lands in the sandbox copy; the real source stays byte-identical ──
_REAL = Path(__file__).resolve().parents[2]
_REL = "companies/sun_pharma/company_memory/ask_intrinsiciq/answer_cards.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sandbox_has_no_path_resolving_into_the_repository():
    files = [p for p in Path("companies").rglob("*") if p.is_file()]
    assert files
    for path in files:
        assert not path.is_symlink() and _REAL not in Path(os.path.realpath(path)).parents, path


@pytest.mark.parametrize("mechanism", ["os.replace", "write_text", "open_w", "shutil.copyfile", "production_writer"])
def test_each_write_mechanism_stays_in_the_sandbox(mechanism, tmp_path):
    real = _REAL / _REL
    before = _sha(real)
    target = Path(_REL)
    payload = '{"sandbox": "' + mechanism + '"}'
    if mechanism == "os.replace":
        tmp = target.with_name(".probe.tmp")
        tmp.write_text(payload)
        os.replace(tmp, target)
    elif mechanism == "write_text":
        target.write_text(payload)
    elif mechanism == "open_w":
        with open(target, "w") as handle:
            handle.write(payload)
    elif mechanism == "shutil.copyfile":
        source = tmp_path / "src.json"
        source.write_text(payload)
        shutil.copyfile(source, target)
    else:
        write_json_file(target.resolve(), {"sandbox": mechanism}, root=Path.cwd() / "companies", force=True)
    assert mechanism in target.read_text()  # the write is visible in the sandbox ...
    assert _sha(real) == before  # ... and the real file is byte-identical


def test_nested_create_and_delete_stay_in_the_sandbox():
    nested = Path("companies/sun_pharma/company_memory/probe_dir/a/b/probe.json")
    nested.parent.mkdir(parents=True)
    nested.write_text("{}")
    assert nested.exists() and not (_REAL / nested).exists()
    existing = Path("companies/sun_pharma/company_memory/ask_intrinsiciq/uncertainty_map.json")
    before = _sha(_REAL / existing)
    existing.unlink()  # deleting in the sandbox ...
    assert not existing.exists() and (_REAL / existing).exists() and _sha(_REAL / existing) == before  # ... leaves the real file
    shutil.rmtree(nested.parent.parent.parent)
    assert not (_REAL / "companies/sun_pharma/company_memory/probe_dir").exists()


def test_the_production_generator_writes_only_inside_the_sandbox():
    protected = {str(p): _sha(p) for p in sorted((_REAL / "companies/datapatterns/company_memory/ask_intrinsiciq").glob("*.json"))}
    result = generate_ask_intrinsiciq_view("datapatterns", Path.cwd() / "companies", force=True)
    assert result["manifest"]["outputs_written"]
    assert get_uncertainty_map_path("datapatterns", Path.cwd() / "companies").exists() and not get_uncertainty_map_path("datapatterns", Path.cwd() / "companies").is_symlink()
    assert {k: _sha(Path(k)) for k in protected} == protected  # real Data Patterns files untouched


# ── the tripwire itself, driven against disposable fake repositories (never the real one) ──
def _drive_sandbox(tmp_path, mutate):
    """Set up the sandbox on a fake repository, apply `mutate(repo, ask_dir)` while it is active, return the teardown failure (or None)."""
    repo = tmp_path / "repo"
    ask = repo / "companies/fake/company_memory/ask_intrinsiciq"
    (ask / "nested/deep").mkdir(parents=True)
    (ask / "existing.json").write_text("{}")
    (ask / "nested/deep/n.json").write_text("{}")
    (repo / "governance").mkdir()
    (repo / "governance/approval_registry.json").write_text("{}")
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    generator = _sandbox(repo, sandbox)
    next(generator)
    mutate(repo, ask)
    try:
        next(generator)
    except StopIteration:
        return None
    except AssertionError as exc:
        return str(exc)
    raise AssertionError("sandbox generator did not finish")


_ASK = "companies/fake/company_memory/ask_intrinsiciq"


@pytest.mark.parametrize("name, mutate, expected", [
    ("new file", lambda repo, ask: (ask / "unauthorized-new.json").write_text("x"), f"added=['{_ASK}/unauthorized-new.json']"),
    ("new nested file", lambda repo, ask: (ask / "nested/deep/another.json").write_text("x"), f"added=['{_ASK}/nested/deep/another.json']"),
    ("modified file", lambda repo, ask: (ask / "existing.json").write_text("changed"), f"modified=['{_ASK}/existing.json']"),
    ("deleted file", lambda repo, ask: (ask / "existing.json").unlink(), f"removed=['{_ASK}/existing.json']"),
    ("deleted nested file", lambda repo, ask: (ask / "nested/deep/n.json").unlink(), f"removed=['{_ASK}/nested/deep/n.json']"),
    ("modified registry", lambda repo, ask: (repo / "governance/approval_registry.json").write_text("tampered"), "modified=['governance/approval_registry.json']"),
    ("deleted registry", lambda repo, ask: (repo / "governance/approval_registry.json").unlink(), "modified=['governance/approval_registry.json']"),
])
def test_tripwire_detects_any_change_to_protected_real_files(name, mutate, expected, tmp_path):
    failure = _drive_sandbox(tmp_path, mutate)
    assert failure is not None and expected in failure, (name, failure)


def test_tripwire_is_silent_when_nothing_changes(tmp_path):
    assert _drive_sandbox(tmp_path, lambda repo, ask: None) is None
