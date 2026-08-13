import json
from pathlib import Path
from typing import Optional

import pytest

from core.company_context import CompanyContext
from intelligence.investor_panel.forbidden_language import find_forbidden_recommendation_language
from knowledge.company_memory.pcim_multi_year_builder import _sha256
from pipelines import run_company_pipeline


def _panel_dir(base: Path, company: str = "polymatech", year: Optional[str] = None) -> Path:
    return base / "companies" / company / "company_memory" / "investor_panel"


def _write_pcim(base: Path, company: str = "polymatech", *, manifest_status: str = "pass", manifest_warnings=None) -> Path:
    company_memory = base / "companies" / company / "company_memory"
    company_memory.mkdir(parents=True, exist_ok=True)
    path = company_memory / "pcim_v1.json"
    path.write_text(
        json.dumps(
            {
                "company": company,
                "contract_version": "1.0",
                "pcim_source_manifest": {
                    "status": manifest_status,
                    "stale_source_warnings": list(manifest_warnings or []),
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_analyst_output(
    base: Path,
    analyst: str,
    *,
    status: str = "pass",
    warning_count: int = 0,
    year: Optional[str] = None,
):
    panel_dir = _panel_dir(base, year=year)
    panel_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "doctrine_id": analyst,
        "evidence_grounding_status": status,
        "historical_context_used": True,
        "years_considered": ["fy24", "fy25"],
        "supporting_pcim_sections": ["risk_inputs"],
        "user_facing_brief": {"title": "t"},
        "reasoning_limits": [],
        "financial_assessment": {
            "financials_used": True,
            "basis_used": "consolidated",
        },
        "financial_sections_consumed": ["financial_quality_inputs"],
        "financial_warnings_carried_forward": [],
    }
    path = panel_dir / f"{analyst}_analysis.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    diagnostics_path = panel_dir / f"{analyst}_analysis_diagnostics.json"
    diagnostics_path.write_text(
        json.dumps(
            {
                "doctrine_id": analyst,
                "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
                "evidence_grounding_warnings": [{"issue": str(i)} for i in range(warning_count)],
                "schema_warnings": [],
                "evidence_routing_diagnostics": {},
                "post_finalization_status": {"status": status, "validation_status": status, "evidence_grounding_status": status},
                "finalization_summary": {"hard_failures": [], "warnings": [], "active_unresolved_claims": [], "non_active_unresolved_claims": []},
            }
        ),
        encoding="utf-8",
    )
    return path


def _make_context(tmp_path: Path, company: str = "polymatech", year: str = "fy24") -> CompanyContext:
    context = CompanyContext(company=company, year=year)
    context.create_directories()
    return context


def _write_financial_artifacts(base: Path, company: str = "polymatech", year: str = "fy24", *, quality_status: str = "pass"):
    fin_dir = base / "companies" / company / year / "financials"
    fin_dir.mkdir(parents=True, exist_ok=True)
    base_payload = {"status": "pass", "warnings": [], "limitations": []}
    for filename in (
        "normalized_fundamentals.json",
        "financial_validation_report.json",
        "financial_reconciliation_report.json",
        "financial_ratios.json",
        "financial_growth.json",
        "corporate_actions.json",
        "shareholding_pattern.json",
    ):
        (fin_dir / filename).write_text(json.dumps(base_payload), encoding="utf-8")
    quality_payload = {
        "status": quality_status,
        "warnings": [] if quality_status == "pass" else ["capex missing"],
        "limitations": [] if quality_status == "pass" else ["share count missing"],
    }
    (fin_dir / "financial_quality_summary.json").write_text(
        json.dumps(quality_payload),
        encoding="utf-8",
    )
    return fin_dir


def _panel_summary_path(base: Path, company: str = "polymatech", year: Optional[str] = None) -> Path:
    return _panel_dir(base, company) / "panel_run_summary.json"


def _write_committee_outputs(
    base: Path,
    company: str = "polymatech",
    *,
    qa_status: str = "pass",
    disagreements=None,
    year: Optional[str] = None,
):
    panel_dir = _panel_dir(base, company, year=year)
    panel_dir.mkdir(parents=True, exist_ok=True)
    synthesis = panel_dir / "committee_synthesis.json"
    synthesis.write_text(
        json.dumps(
            {
                "evidence_id_normalization": {"applied": True, "replacements": [], "unresolved_ids": []},
                "areas_of_disagreement": (
                    [{"disagreement_type": "different_emphasis"}]
                    if disagreements is None
                    else disagreements
                ),
            }
        ),
        encoding="utf-8",
    )
    brief = panel_dir / "committee_brief.md"
    brief.write_text("brief", encoding="utf-8")
    qa = panel_dir / "committee_brief_qa.json"
    qa.write_text(
        json.dumps({"status": qa_status, "warnings": [], "failures": []}),
        encoding="utf-8",
    )
    return synthesis, brief, qa


def test_panel_stage_accepts_empty_committee_disagreements(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, manifest_status="pass")
    company_memory = tmp_path / "companies" / "polymatech" / "company_memory"
    multi_year_dir = company_memory / "multi_year"
    multi_year_dir.mkdir(parents=True, exist_ok=True)
    (multi_year_dir / "company_year_index.json").write_text(
        json.dumps({"years": ["fy24"]}),
        encoding="utf-8",
    )
    (multi_year_dir / "multi_year_index.json").write_text(
        json.dumps({"years_covered": ["fy24"]}),
        encoding="utf-8",
    )
    _write_financial_artifacts(tmp_path, quality_status="pass")
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        _write_analyst_output(tmp_path, analyst, status="pass")
    _write_committee_outputs(tmp_path, disagreements=[])

    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        lambda company, context=None, cleanup_only=False: {
            "committee_synthesis.json": _panel_dir(tmp_path, company) / "committee_synthesis.json"
        },
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        lambda company, context=None, include_evidence_ids=False: {
            "committee_brief.md": _panel_dir(tmp_path, company) / "committee_brief.md"
        },
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        lambda company, context=None, include_evidence_ids=False: {
            "committee_brief_qa.json": _panel_dir(tmp_path, company) / "committee_brief_qa.json"
        },
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "_assess_pcim_freshness",
        lambda company, pcim_payload: {"status": "pass", "warnings": [], "failures": []},
    )

    outputs = run_company_pipeline.run_panel_stage(company="polymatech")
    summary = json.loads(_panel_summary_path(tmp_path).read_text(encoding="utf-8"))

    assert "committee_synthesis.json" in outputs
    assert summary["stages"]["committee_synthesis"]["status"] == "pass"


def test_assess_panel_financial_context_uses_hydrated_truth_pack(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    company = "polymatech"
    year = "fy24"
    context = _make_context(tmp_path, company=company, year=year)
    _write_financial_artifacts(tmp_path, company=company, year=year, quality_status="warning")
    company_fin = tmp_path / "companies" / company / "company_memory" / "financials"
    company_fin.mkdir(parents=True, exist_ok=True)
    (company_fin / "financial_truth_pack.json").write_text(
        json.dumps(
            {
                "company": company,
                "generated_at": "2026-07-26T00:00:00Z",
                "years_covered": ["fy24"],
                "source_files_checked": [],
                "source_files_used": [],
                "source_files_missing": [],
                "usable_current_metrics": [{"metric_id": "revenue"}],
                "usable_derived_metrics": [],
                "partial_metrics": [],
                "precise_missing_metrics": [],
                "unreliable_metrics": [],
                "invalid_or_quarantined_metrics": [],
                "derived_not_explicitly_reported": [],
                "trend_durability_limits": [],
                "precision_limits": ["Maintenance versus growth capex is estimated."],
                "financial_warnings_allowed_downstream": [],
                "financial_warnings_blocked_downstream": [],
                "financial_warnings_rewritten": [],
                "investor_relevant_questions": ["What explains capex timing?"],
                "financial_panel_status": "warning",
                "financial_panel_status_reason": "Hydrated truth exists with some limits.",
                "financial_panel_usable_domains": ["owner_earnings"],
                "financial_panel_limited_domains": ["working_capital"],
                "financial_panel_blocked_domains": [],
                "source_provenance": ["company_memory/financials/financial_truth_pack.json"],
            }
        ),
        encoding="utf-8",
    )

    result = run_company_pipeline._assess_panel_financial_context(context)

    assert result["available"] is True
    assert result["status"] in {"warning", "partial", "pass"}
    assert result["artifacts_checked"]


def test_assess_panel_financial_context_uses_existing_analyst_financial_usage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    company = "polymatech"
    year = "fy24"
    context = _make_context(tmp_path, company=company, year=year)
    _write_financial_artifacts(tmp_path, company=company, year=year, quality_status="warning")
    _write_pcim(tmp_path, company=company)
    panel_dir = _panel_dir(tmp_path, company)
    panel_dir.mkdir(parents=True, exist_ok=True)
    (panel_dir / "graham_analysis.json").write_text(
        json.dumps(
            {
                "doctrine_id": "graham",
                "financial_assessment": {"financials_used": True},
                "financial_sections_consumed": ["balance_sheet_strength_inputs"],
            }
        ),
        encoding="utf-8",
    )

    result = run_company_pipeline._assess_panel_financial_context(context)

    assert result["available"] is True
    assert result["artifacts_checked"]
    assert any("graham_analysis.json" in item for item in result["artifacts_checked"])
    assert result["status"] in {"warning", "partial", "pass"}


def test_assess_panel_financial_context_without_year_context_uses_company_memory_truth(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    company = "polymatech"
    company_fin = tmp_path / "companies" / company / "company_memory" / "financials"
    company_fin.mkdir(parents=True, exist_ok=True)
    (company_fin / "financial_truth_pack.json").write_text(
        json.dumps(
            {
                "financial_panel_status": "pass",
                "usable_current_metrics": [{"metric_id": "fcf"}],
                "usable_derived_metrics": [],
                "partial_metrics": [],
            }
        ),
        encoding="utf-8",
    )
    panel_dir = _panel_dir(tmp_path, company)
    panel_dir.mkdir(parents=True, exist_ok=True)
    (panel_dir / "graham_analysis.json").write_text(
        json.dumps({"financial_assessment": {"financials_used": True}}),
        encoding="utf-8",
    )

    result = run_company_pipeline._assess_panel_financial_context(None)

    assert result["available"] is True
    assert result["status"] == "pass"
    assert result["artifacts_checked"]


def test_panel_stage_records_financial_context_without_year_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pcim_path = _write_pcim(tmp_path)
    company_fin = tmp_path / "companies" / "polymatech" / "company_memory" / "financials"
    company_fin.mkdir(parents=True, exist_ok=True)
    (company_fin / "financial_truth_pack.json").write_text(
        json.dumps(
            {
                "financial_panel_status": "pass",
                "usable_current_metrics": [{"metric_id": "revenue"}],
                "usable_derived_metrics": [],
                "partial_metrics": [],
            }
        ),
        encoding="utf-8",
    )
    pcim_path.touch()
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        _write_analyst_output(tmp_path, analyst, status="pass")

    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        lambda company, context=None, cleanup_only=False: (
            _write_committee_outputs(tmp_path),
            {"committee_synthesis.json": _panel_dir(tmp_path) / "committee_synthesis.json"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {"committee_brief.md": _panel_dir(tmp_path) / "committee_brief.md"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {"committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json"},
        )[1],
    )

    run_company_pipeline.run_panel_stage(company="polymatech")
    summary = json.loads(_panel_summary_path(tmp_path).read_text(encoding="utf-8"))

    assert summary["financial_context"]["available"] is True
    assert summary["financial_context"]["status"] == "pass"
    assert summary["financial_context"]["artifacts_checked"]


def test_panel_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["polymatech", "--stage", "panel"])
    assert args.stage == "panel"


def test_panel_stage_fails_if_pcim_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="PCIM missing"):
        run_company_pipeline.run_panel_stage(company="polymatech")


def test_panel_stage_fails_if_pcim_source_manifest_is_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, manifest_status="fail")
    with pytest.raises(RuntimeError, match="PCIM source manifest unusable"):
        run_company_pipeline.run_panel_stage(company="polymatech")


def test_panel_stage_fails_if_current_multi_year_sources_changed_after_pcim_build(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    company = "polymatech"
    company_memory = tmp_path / "companies" / company / "company_memory"
    company_memory.mkdir(parents=True, exist_ok=True)
    pcim_path = company_memory / "pcim_v1.json"
    pcim_path.write_text(
        json.dumps(
            {
                "company": company,
                "contract_version": "1.0",
                "available_years": ["fy24"],
                "multi_year_inputs": {"available": False, "years_covered": [], "limitations": ["old"]},
                "pcim_source_manifest": {
                    "company": company,
                    "generated_at": "2026-07-14T00:00:00Z",
                    "source_files": [],
                    "years_available": ["fy24"],
                    "years_covered_in_multi_year_inputs": [],
                    "missing_years": ["fy24"],
                    "stale_source_warnings": [],
                    "status": "warning",
                },
            }
        ),
        encoding="utf-8",
    )
    multi_year_dir = company_memory / "multi_year"
    multi_year_dir.mkdir(parents=True, exist_ok=True)
    (multi_year_dir / "company_year_index.json").write_text(
        json.dumps({"available_years": ["fy24"], "years_detected": ["fy24"]}),
        encoding="utf-8",
    )
    (multi_year_dir / "multi_year_index.json").write_text(
        json.dumps({"years_covered": ["fy24"], "limitations": []}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="stale"):
        run_company_pipeline.run_panel_stage(company=company)


def test_panel_stage_reuses_existing_validated_analysts_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        _write_analyst_output(tmp_path, analyst, status="pass")

    def should_not_run(*args, **kwargs):
        raise AssertionError("panel should reuse existing analyst artifacts by default")

    def fake_synthesis(company, context=None, cleanup_only=False):
        _write_committee_outputs(tmp_path)
        return {"committee_synthesis.json": _panel_dir(tmp_path) / "committee_synthesis.json"}

    def fake_brief(company, context=None, include_evidence_ids=False):
        _write_committee_outputs(tmp_path)
        return {
            "committee_brief.md": _panel_dir(tmp_path) / "committee_brief.md",
            "committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json",
        }

    def fake_brief_qa(company, context=None, include_evidence_ids=False):
        _write_committee_outputs(tmp_path)
        return {"committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json"}

    monkeypatch.setattr(run_company_pipeline, "run_investor_panel_stage", should_not_run)
    monkeypatch.setattr(run_company_pipeline, "run_committee_synthesis_stage", fake_synthesis)
    monkeypatch.setattr(run_company_pipeline, "run_committee_brief_stage", fake_brief)
    monkeypatch.setattr(run_company_pipeline, "run_committee_brief_qa_stage", fake_brief_qa)

    result = run_company_pipeline.run_panel_stage(company="polymatech")

    summary = json.loads(_panel_summary_path(tmp_path).read_text(encoding="utf-8"))
    assert summary["status"] == "warning"
    assert summary["analyst_source_mode"] == "loaded_existing"
    assert summary["financial_context"]["available"] is True
    assert result["panel_run_summary.json"].name == "panel_run_summary.json"


def test_loaded_existing_finalization_summary_overrides_intermediate_unresolved_claims(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    _write_analyst_output(tmp_path, "munger", status="warning")
    diagnostics_path = _panel_dir(tmp_path) / "munger_analysis_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["evidence_routing_diagnostics"] = {
        "unresolved_claims": [{"claim_text": "old unsupported claim"}],
    }
    diagnostics["finalization_diagnostics"] = {
        "post_finalization_status": {"status": "warning", "validation_status": "warning", "evidence_grounding_status": "warning"},
        "finalization_summary": {"hard_failures": [], "warnings": [], "active_unresolved_claims": [], "non_active_unresolved_claims": []},
    }
    diagnostics_path.write_text(json.dumps(diagnostics), encoding="utf-8")

    result = run_company_pipeline._validate_analyst_output("polymatech", "munger")

    assert result["status"] == "warning"
    assert result["failures"] == []


def test_loaded_existing_true_active_unresolved_claim_still_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    _write_analyst_output(tmp_path, "lynch", status="warning")
    diagnostics_path = _panel_dir(tmp_path) / "lynch_analysis_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["finalization_diagnostics"] = {
        "post_finalization_status": {"status": "fail", "validation_status": "fail", "evidence_grounding_status": "fail"},
        "finalization_summary": {
            "hard_failures": ["unresolved factual claims remain after evidence routing repair"],
            "warnings": [],
            "active_unresolved_claims": [{"claim_text": "unsupported active claim"}],
            "non_active_unresolved_claims": [],
        },
    }
    diagnostics_path.write_text(json.dumps(diagnostics), encoding="utf-8")

    result = run_company_pipeline._validate_analyst_output("polymatech", "lynch")

    assert result["status"] == "fail"
    assert any("unresolved factual claims remain after evidence routing repair" in item for item in result["failures"])


def test_loaded_existing_missing_post_finalization_status_falls_back_to_artifact_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    _write_analyst_output(tmp_path, "graham", status="warning")
    diagnostics_path = _panel_dir(tmp_path) / "graham_analysis_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics.pop("post_finalization_status", None)
    diagnostics.pop("finalization_summary", None)
    diagnostics_path.write_text(json.dumps(diagnostics), encoding="utf-8")

    result = run_company_pipeline._validate_analyst_output("polymatech", "graham")

    assert result["status"] == "warning"
    assert result["resolved_final_status"] == "warning"


def test_panel_summary_uses_resolved_post_finalization_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        _write_analyst_output(tmp_path, analyst, status="warning")
    diagnostics_path = _panel_dir(tmp_path) / "munger_analysis_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["finalization_diagnostics"] = {
        "post_finalization_status": {"status": "warning", "validation_status": "warning", "evidence_grounding_status": "warning"},
        "finalization_summary": {"hard_failures": [], "warnings": [], "active_unresolved_claims": [], "non_active_unresolved_claims": []},
    }
    diagnostics["evidence_routing_diagnostics"] = {"unresolved_claims": [{"claim_text": "stale intermediate claim"}]}
    diagnostics_path.write_text(json.dumps(diagnostics), encoding="utf-8")

    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        lambda company, context=None, cleanup_only=False: (
            _write_committee_outputs(tmp_path),
            {"committee_synthesis.json": _panel_dir(tmp_path) / "committee_synthesis.json"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {"committee_brief.md": _panel_dir(tmp_path) / "committee_brief.md"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {"committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json"},
        )[1],
    )

    run_company_pipeline.run_panel_stage(company="polymatech")
    summary = json.loads(_panel_summary_path(tmp_path).read_text(encoding="utf-8"))

    assert summary["analysts"]["munger"]["status"] == "warning"
    assert summary["analysts"]["munger"]["evidence_grounding_status"] == "warning"
    assert summary["analysts"]["munger"]["validation_status"] == "warning"
    assert summary["analysts"]["munger"]["raw_artifact_status"] in {"warning", "fail", "pass"}
    assert not any("munger: unresolved factual claims remain after evidence routing repair" in item for item in summary["failures"])


def test_canonicalize_panel_run_summary_overrides_stale_fail_and_infers_financial_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    company = "polymatech"
    _write_pcim(tmp_path, company=company)
    panel_dir = _panel_dir(tmp_path, company=company)
    panel_dir.mkdir(parents=True, exist_ok=True)
    (panel_dir / "munger_analysis.json").write_text("{}", encoding="utf-8")

    summary = {
        "company": company,
        "year": None,
        "status": "fail",
        "financial_context": {
            "available": False,
            "status": "missing",
            "artifacts_checked": [],
            "missing_artifacts": [],
            "warnings": [],
            "limitations": [],
        },
        "stages": {
            "analysts": {
                "status": "fail",
                "output": "munger:fail",
                "warnings": [],
                "hard_failures": ["munger: unresolved factual claims remain after evidence routing repair"],
                "failures": ["munger: unresolved factual claims remain after evidence routing repair"],
            },
            "pcim": {"status": "pass", "output": "companies/polymatech/company_memory/pcim_v1.json", "warnings": [], "hard_failures": [], "failures": []},
        },
        "analysts": {
            "munger": {
                "status": "fail",
                "raw_artifact_status": "fail",
                "output_path": str(panel_dir / "munger_analysis.json"),
                "financials_used": True,
                "financial_sections_consumed": ["financial_quality_inputs"],
                "evidence_grounding_status": "fail",
                "validation_status": "fail",
                "post_finalization_status": {
                    "status": "warning",
                    "validation_status": "warning",
                    "evidence_grounding_status": "warning",
                },
                "finalization_summary": {
                    "hard_failures": [],
                    "warnings": [],
                    "active_unresolved_claims": [],
                    "non_active_unresolved_claims": [],
                },
                "warnings": [],
                "hard_failures": ["munger: unresolved factual claims remain after evidence routing repair"],
            }
        },
        "warnings": [],
        "hard_failures": ["munger: unresolved factual claims remain after evidence routing repair"],
        "failures": ["munger: unresolved factual claims remain after evidence routing repair"],
    }

    canonical = run_company_pipeline.canonicalize_panel_run_summary(summary)

    assert canonical["analysts"]["munger"]["status"] == "warning"
    assert canonical["analysts"]["munger"]["validation_status"] == "warning"
    assert canonical["analysts"]["munger"]["evidence_grounding_status"] == "warning"
    assert canonical["analysts"]["munger"]["hard_failures"] == []
    assert canonical["stages"]["analysts"]["status"] == "warning"
    assert canonical["stages"]["analysts"]["output"] == "munger:warning"
    assert canonical["stages"]["analysts"]["hard_failures"] == []
    assert canonical["stages"]["analysts"]["failures"] == []
    assert canonical["status"] == "warning"
    assert canonical["hard_failures"] == []
    assert canonical["failures"] == []
    assert canonical["financial_context"]["available"] is True
    assert canonical["financial_context"]["status"] == "warning"
    assert canonical["financial_context"]["artifacts_checked"]
    assert any("Financial context was inferred from analyst financial usage" in item for item in canonical["financial_context"]["warnings"])


def test_canonicalize_panel_run_summary_preserves_true_final_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    summary = {
        "company": "polymatech",
        "year": None,
        "status": "warning",
        "financial_context": {"available": True, "status": "warning", "artifacts_checked": [], "missing_artifacts": [], "warnings": [], "limitations": []},
        "stages": {"analysts": {"status": "warning", "output": "", "warnings": [], "hard_failures": [], "failures": []}},
        "analysts": {
            "lynch": {
                "status": "warning",
                "financials_used": True,
                "evidence_grounding_status": "warning",
                "validation_status": "warning",
                "post_finalization_status": {
                    "status": "fail",
                    "validation_status": "fail",
                    "evidence_grounding_status": "fail",
                },
                "finalization_summary": {
                    "hard_failures": [],
                    "warnings": [],
                    "active_unresolved_claims": [{"claim_text": "unsupported active claim"}],
                    "non_active_unresolved_claims": [],
                },
                "warnings": [],
                "hard_failures": [],
            }
        },
        "warnings": [],
        "hard_failures": [],
        "failures": [],
    }

    canonical = run_company_pipeline.canonicalize_panel_run_summary(summary)

    assert canonical["analysts"]["lynch"]["status"] == "fail"
    assert canonical["stages"]["analysts"]["status"] == "fail"
    assert any("unresolved factual claims remain after evidence routing repair" in item for item in canonical["stages"]["analysts"]["hard_failures"])
    assert canonical["status"] == "fail"


def test_panel_stage_collects_all_existing_analyst_failures_before_stopping(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        status = "fail" if analyst in {"graham", "munger"} else "pass"
        _write_analyst_output(tmp_path, analyst, status=status)

    with pytest.raises(RuntimeError, match="See panel_run_summary.json for all failures"):
        run_company_pipeline.run_panel_stage(company="polymatech")

    summary = json.loads(_panel_summary_path(tmp_path).read_text(encoding="utf-8"))
    assert "graham: evidence_grounding_status=fail" in summary["failures"]
    assert "munger: evidence_grounding_status=fail" in summary["failures"]


def test_panel_stage_finalize_gate_uses_canonicalized_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, company="acme")
    panel_dir = _panel_dir(tmp_path, company="acme")
    panel_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(run_company_pipeline, "_assess_pcim_freshness", lambda company, payload: {"status": "pass", "warnings": [], "failures": []})
    monkeypatch.setattr(run_company_pipeline, "run_investor_panel_stage", lambda company, analyst, context=None: None)
    monkeypatch.setattr(
        run_company_pipeline,
        "_validate_analyst_output",
        lambda company, analyst, context=None: {
            "status": "fail",
            "resolved_final_status": "warning",
            "resolved_final_validation_status": "warning",
            "resolved_final_evidence_grounding_status": "warning",
            "warning_count": 1,
            "output": str(panel_dir / f"{analyst}_analysis.json"),
            "payload": {
                "status": "fail",
                "financial_assessment": {"financials_used": True},
                "financial_sections_consumed": ["financial_quality_inputs"],
            },
            "warnings": [],
            "failures": [f"{analyst}: unresolved factual claims remain after evidence routing repair"],
            "post_finalization_status": {
                "status": "warning",
                "validation_status": "warning",
                "evidence_grounding_status": "warning",
            },
            "finalization_summary": {
                "hard_failures": [],
                "warnings": [],
                "active_unresolved_claims": [],
                "non_active_unresolved_claims": [],
            },
        },
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        lambda company, context=None, cleanup_only=False: (
            _write_committee_outputs(tmp_path, company="acme"),
            {"committee_synthesis.json": _panel_dir(tmp_path, company="acme") / "committee_synthesis.json"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path, company="acme"),
            {"committee_brief.md": _panel_dir(tmp_path, company="acme") / "committee_brief.md"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path, company="acme"),
            {"committee_brief_qa.json": _panel_dir(tmp_path, company="acme") / "committee_brief_qa.json"},
        )[1],
    )

    result = run_company_pipeline.run_panel_stage(company="acme", regenerate_analysts=True)
    summary = json.loads((panel_dir / "panel_run_summary.json").read_text(encoding="utf-8"))

    assert result["panel_run_summary.json"].name == "panel_run_summary.json"
    assert summary["stages"]["analysts"]["status"] == "warning"
    assert summary["status"] in {"warning", "pass"}
    assert summary["analysts"]["munger"]["status"] == "warning"
    assert summary["stages"]["analysts"]["hard_failures"] == []
    assert summary["stages"]["analysts"]["failures"] == []


def test_panel_doctor_reports_all_analysts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_analyst_output(tmp_path, "graham", status="fail", warning_count=1)
    _write_analyst_output(tmp_path, "buffett", status="warning", warning_count=1)
    result = run_company_pipeline.run_panel_doctor_stage(company="polymatech")
    report = json.loads(result["panel_doctor_report.json"].read_text(encoding="utf-8"))
    assert len(report["analysts"]) == 5
    graham = next(item for item in report["analysts"] if item["analyst"] == "graham")
    assert graham["status"] == "fail"
    assert graham["analysis_exists"] is True
    assert graham["diagnostics_exists"] is True
    assert graham["clean_status"] in {"pass", "fail", "missing"}
    assert graham["analysis_path"].endswith("companies/polymatech/company_memory/investor_panel/graham_analysis.json")
    assert graham["diagnostics_path"].endswith(
        "companies/polymatech/company_memory/investor_panel/graham_analysis_diagnostics.json"
    )


def test_panel_doctor_uses_company_memory_scope_even_with_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _make_context(tmp_path)
    panel_dir = _panel_dir(tmp_path)
    panel_dir.mkdir(parents=True, exist_ok=True)
    _write_analyst_output(tmp_path, "graham")
    (panel_dir / "graham_analysis.json").write_text(
        json.dumps({"doctrine_id": "graham", "schema_warnings": ["stale"]}),
        encoding="utf-8",
    )
    (panel_dir / "graham_analysis_diagnostics.json").write_text(
        json.dumps({"doctrine_id": "graham", "schema_warnings": ["stale"]}),
        encoding="utf-8",
    )

    result = run_company_pipeline.run_panel_doctor_stage(company="polymatech", context=context)
    report = json.loads(result["panel_doctor_report.json"].read_text(encoding="utf-8"))

    assert result["panel_doctor_report.json"].resolve().parent == panel_dir.resolve()
    assert report["scope"] == "company_memory"
    assert report["source_pcim"] == "companies/polymatech/company_memory/pcim_v1.json"
    assert report["panel_dir"].endswith("companies/polymatech/company_memory/investor_panel")
    graham = next(item for item in report["analysts"] if item["analyst"] == "graham")
    assert graham["analysis_path"].endswith(
        "companies/polymatech/company_memory/investor_panel/graham_analysis.json"
    )
    assert graham["diagnostics_path"].endswith(
        "companies/polymatech/company_memory/investor_panel/graham_analysis_diagnostics.json"
    )
    assert graham["analysis_exists"] is True
    assert graham["diagnostics_exists"] is True
    assert graham["failed_clean_candidate_exists"] is False


def test_panel_doctor_reports_failed_clean_candidate_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    panel_dir = _panel_dir(tmp_path)
    panel_dir.mkdir(parents=True, exist_ok=True)
    _write_analyst_output(tmp_path, "graham")
    diagnostics_path = panel_dir / "graham_analysis_diagnostics.json"
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["clean_writer_status"] = "fail"
    diagnostics["remaining_forbidden_strings"] = ["$.assessment.management_rationality_assessment"]
    diagnostics_path.write_text(json.dumps(diagnostics), encoding="utf-8")
    (panel_dir / "graham_analysis_failed_clean_candidate.json").write_text(
        json.dumps({"doctrine_id": "graham"}),
        encoding="utf-8",
    )

    result = run_company_pipeline.run_panel_doctor_stage(company="polymatech")
    report = json.loads(result["panel_doctor_report.json"].read_text(encoding="utf-8"))
    graham = next(item for item in report["analysts"] if item["analyst"] == "graham")

    assert graham["failed_clean_candidate_exists"] is True
    assert graham["clean_status"] == "fail"
    assert graham["remaining_forbidden_strings"] == ["$.assessment.management_rationality_assessment"]
    assert graham["suggested_fix_category"] == "clean_writer"


def test_panel_stage_records_pcim_source_manifest_warning_and_continues(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, manifest_status="warning", manifest_warnings=["Missing fy23 in risk_evolution coverage."])
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        _write_analyst_output(tmp_path, analyst, status="pass")

    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        lambda company, context=None, cleanup_only=False: (
            _write_committee_outputs(tmp_path),
            {"committee_synthesis.json": _panel_dir(tmp_path) / "committee_synthesis.json"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {
                "committee_brief.md": _panel_dir(tmp_path) / "committee_brief.md",
                "committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json",
            },
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {"committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json"},
        )[1],
    )

    run_company_pipeline.run_panel_stage(company="polymatech")
    summary = json.loads(_panel_summary_path(tmp_path).read_text(encoding="utf-8"))
    assert summary["stages"]["pcim"]["status"] == "warning"
    assert "Missing fy23 in risk_evolution coverage." in summary["stages"]["pcim"]["warnings"]


def test_investor_panel_stage_uses_current_pcim_freshness_audit(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    company = "polymatech"
    company_memory = tmp_path / "companies" / company / "company_memory"
    company_memory.mkdir(parents=True, exist_ok=True)
    pcim_path = company_memory / "pcim_v1.json"
    pcim_path.write_text(
        json.dumps(
            {
                "company": company,
                "contract_version": "1.0",
                "available_years": ["fy24", "fy25"],
                "multi_year_inputs": {
                    "available": True,
                    "years_covered": ["fy24"],
                    "limitations": ["Partial synthetic coverage."],
                },
                "pcim_source_manifest": {
                    "company": company,
                    "generated_at": "2026-07-15T00:00:00Z",
                    "source_files": [
                        {
                            "name": "company_year_index.json",
                            "path": "companies/polymatech/company_memory/multi_year/company_year_index.json",
                            "exists": True,
                            "loaded": True,
                            "modified_at": "2026-07-15T00:00:00Z",
                            "content_hash": "",
                            "years_detected": ["fy24", "fy25"],
                            "warnings": [],
                        },
                        {
                            "name": "multi_year_index.json",
                            "path": "companies/polymatech/company_memory/multi_year/multi_year_index.json",
                            "exists": True,
                            "loaded": True,
                            "modified_at": "2026-07-15T00:00:00Z",
                            "content_hash": "",
                            "years_detected": ["fy24"],
                            "warnings": [],
                        },
                    ],
                    "years_available": ["fy24", "fy25"],
                    "years_covered_in_multi_year_inputs": ["fy24"],
                    "missing_years": ["fy25"],
                    "stale_source_warnings": ["Synthetic partial coverage warning."],
                    "status": "warning",
                },
            }
        ),
        encoding="utf-8",
    )
    multi_year_dir = company_memory / "multi_year"
    multi_year_dir.mkdir(parents=True, exist_ok=True)
    (multi_year_dir / "company_year_index.json").write_text(
        json.dumps({"available_years": ["fy24", "fy25"], "years_detected": ["fy24", "fy25"]}),
        encoding="utf-8",
    )
    (multi_year_dir / "multi_year_index.json").write_text(
        json.dumps({"years_covered": ["fy24"], "limitations": ["Partial synthetic coverage warning."]}),
        encoding="utf-8",
    )
    company_year_index_path = multi_year_dir / "company_year_index.json"
    multi_year_index_path = multi_year_dir / "multi_year_index.json"
    payload = json.loads(pcim_path.read_text(encoding="utf-8"))
    payload["pcim_source_manifest"]["source_files"][0]["content_hash"] = _sha256(company_year_index_path)
    payload["pcim_source_manifest"]["source_files"][1]["content_hash"] = _sha256(multi_year_index_path)
    pcim_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(
        run_company_pipeline,
        "InvestorPanelRunner",
        lambda company, output_dir=None: type(
            "FakeRunner",
            (),
            {"run": lambda self, analyst=None: {"graham_analysis.json": _panel_dir(tmp_path) / "graham_analysis.json"}},
        )(),
    )
    _write_analyst_output(tmp_path, "graham", status="pass")

    result = run_company_pipeline.run_investor_panel_stage(company=company, analyst="graham")
    captured = capsys.readouterr()

    assert "PCIM source manifest status is warning" in captured.out
    assert "Synthetic partial coverage warning." in captured.out
    assert "graham_analysis.json" in result


def test_panel_stage_fails_when_existing_artifact_has_hard_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        status = "fail" if analyst == "buffett" else "pass"
        _write_analyst_output(tmp_path, analyst, status=status)

    with pytest.raises(RuntimeError, match="See panel_run_summary.json for all failures"):
        run_company_pipeline.run_panel_stage(company="polymatech")


def test_panel_stage_writes_summary_when_analyst_execution_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)

    def fake_panel(company, analyst=None, context=None):
        if analyst == "graham":
            raise RuntimeError("provider down")
        _write_analyst_output(tmp_path, analyst, status="pass")
        return {f"{analyst}_analysis.json": _panel_dir(tmp_path) / f"{analyst}_analysis.json"}

    monkeypatch.setattr(run_company_pipeline, "run_investor_panel_stage", fake_panel)

    with pytest.raises(RuntimeError, match="See panel_run_summary.json for all failures"):
        run_company_pipeline.run_panel_stage(company="polymatech", regenerate_analysts=True)

    summary_path = _panel_summary_path(tmp_path)
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "fail"
    assert summary["stages"]["analysts"]["status"] == "fail"
    assert "stage execution failed" in summary["stages"]["analysts"]["failures"][0]


def test_panel_stage_allows_warning_and_records_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        if analyst == "graham":
            _write_analyst_output(tmp_path, analyst, status="warning", warning_count=2)
        else:
            _write_analyst_output(tmp_path, analyst, status="pass")
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        lambda company, context=None, cleanup_only=False: (
            _write_committee_outputs(tmp_path),
            {"committee_synthesis.json": _panel_dir(tmp_path) / "committee_synthesis.json"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {
                "committee_brief.md": _panel_dir(tmp_path) / "committee_brief.md",
                "committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json",
            },
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {"committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json"},
        )[1],
    )

    run_company_pipeline.run_panel_stage(company="polymatech")
    summary = json.loads(_panel_summary_path(tmp_path).read_text(encoding="utf-8"))
    assert summary["status"] == "warning"
    assert summary["analysts"]["graham"]["status"] == "warning"


def test_panel_stage_fails_if_committee_brief_qa_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        _write_analyst_output(tmp_path, analyst, status="pass")

    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        lambda company, context=None, cleanup_only=False: (
            _write_committee_outputs(tmp_path, qa_status="fail"),
            {"committee_synthesis.json": _panel_dir(tmp_path) / "committee_synthesis.json"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path, qa_status="fail"),
            {
                "committee_brief.md": _panel_dir(tmp_path) / "committee_brief.md",
                "committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json",
            },
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path, qa_status="fail"),
            {"committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json"},
        )[1],
    )

    with pytest.raises(RuntimeError, match="committee brief QA failed"):
        run_company_pipeline.run_panel_stage(company="polymatech")


def test_panel_stage_regenerates_analysts_when_flag_is_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    calls = []

    def fake_panel(company, analyst=None, context=None):
        calls.append(analyst)
        _write_analyst_output(tmp_path, analyst, status="pass")
        return {f"{analyst}_analysis.json": _panel_dir(tmp_path) / f"{analyst}_analysis.json"}

    monkeypatch.setattr(run_company_pipeline, "run_investor_panel_stage", fake_panel)
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        lambda company, context=None, cleanup_only=False: (
            _write_committee_outputs(tmp_path),
            {"committee_synthesis.json": _panel_dir(tmp_path) / "committee_synthesis.json"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {
                "committee_brief.md": _panel_dir(tmp_path) / "committee_brief.md",
                "committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json",
            },
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {"committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json"},
        )[1],
    )

    run_company_pipeline.run_panel_stage(company="polymatech", regenerate_analysts=True)

    summary = json.loads(_panel_summary_path(tmp_path).read_text(encoding="utf-8"))
    assert calls == ["graham", "buffett", "fisher", "munger", "lynch"]
    assert summary["analyst_source_mode"] == "regenerated"


def test_panel_stage_and_panel_doctor_agree_on_existing_statuses(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    _write_analyst_output(tmp_path, "graham", status="warning", warning_count=1)
    _write_analyst_output(tmp_path, "buffett", status="pass")
    _write_analyst_output(tmp_path, "fisher", status="pass")
    _write_analyst_output(tmp_path, "munger", status="pass")
    _write_analyst_output(tmp_path, "lynch", status="pass")
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        lambda company, context=None, cleanup_only=False: (
            _write_committee_outputs(tmp_path),
            {"committee_synthesis.json": _panel_dir(tmp_path) / "committee_synthesis.json"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {
                "committee_brief.md": _panel_dir(tmp_path) / "committee_brief.md",
                "committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json",
            },
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path),
            {"committee_brief_qa.json": _panel_dir(tmp_path) / "committee_brief_qa.json"},
        )[1],
    )

    panel_result = run_company_pipeline.run_panel_stage(company="polymatech")
    doctor_result = run_company_pipeline.run_panel_doctor_stage(company="polymatech")

    panel_summary = json.loads(panel_result["panel_run_summary.json"].read_text(encoding="utf-8"))
    doctor_summary = json.loads(doctor_result["panel_doctor_report.json"].read_text(encoding="utf-8"))
    doctor_statuses = {item["analyst"]: item["status"] for item in doctor_summary["analysts"]}

    assert panel_summary["analysts"]["graham"]["status"] == doctor_statuses["graham"] == "warning"
    assert panel_summary["analysts"]["buffett"]["status"] == doctor_statuses["buffett"] == "pass"


@pytest.mark.parametrize(
    "text",
    [
        "IPO/offer-for-sale, equity issuance, share split, QIP",
        "sale of shares under offer for sale",
        "sales revenue increased",
        "cost of sales improved",
        "defence sales grew with order wins",
        "capital raising and authorized placement were disclosed",
    ],
)
def test_forbidden_language_helper_allows_corporate_action_phrases(text):
    assert find_forbidden_recommendation_language(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "Buy this stock",
        "Sell this stock",
        "Hold the stock",
        "Recommendation: buy",
        "Target price is ₹100",
        "The stock is undervalued",
        "Invest now",
        "Exit the position",
        "Avoid this company",
        "The committee would buy after more work.",
    ],
)
def test_forbidden_language_helper_blocks_real_recommendation_language(text):
    assert find_forbidden_recommendation_language(text)


def test_panel_stage_does_not_fail_on_offer_for_sale_language(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        if analyst == "munger":
            path = _write_analyst_output(tmp_path, analyst, status="warning", warning_count=1)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["assessment"] = "The company disclosed an offer-for-sale and authorized placement."
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            _write_analyst_output(tmp_path, analyst, status="pass")
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        lambda company, context=None, cleanup_only=False: (
            _write_committee_outputs(tmp_path, year="fy24"),
            {"committee_synthesis.json": _panel_dir(tmp_path, year="fy24") / "committee_synthesis.json"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path, year="fy24"),
            {
                "committee_brief.md": _panel_dir(tmp_path, year="fy24") / "committee_brief.md",
                "committee_brief_qa.json": _panel_dir(tmp_path, year="fy24") / "committee_brief_qa.json",
            },
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path, year="fy24"),
            {"committee_brief_qa.json": _panel_dir(tmp_path, year="fy24") / "committee_brief_qa.json"},
        )[1],
    )

    run_company_pipeline.run_panel_stage(company="polymatech")

    summary = json.loads(_panel_summary_path(tmp_path).read_text(encoding="utf-8"))
    assert summary["status"] == "warning"
    assert summary["analysts"]["munger"]["status"] == "warning"
    assert "forbidden recommendation language" not in " ".join(summary["failures"]).lower()


def test_panel_stage_with_year_context_records_financial_context_and_year_scoped_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _make_context(tmp_path)
    _write_financial_artifacts(tmp_path, quality_status="warning")
    _write_pcim(tmp_path)
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        _write_analyst_output(tmp_path, analyst, status="pass", year="fy24")

    monkeypatch.setattr(
        run_company_pipeline,
        "run_cim_stage",
        lambda company, context=None: {"pcim_v1.json": Path("companies") / company / "company_memory" / "pcim_v1.json"},
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        lambda company, context=None, cleanup_only=False: (
            _write_committee_outputs(tmp_path, year="fy24"),
            {"committee_synthesis.json": _panel_dir(tmp_path, year="fy24") / "committee_synthesis.json"},
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path, year="fy24"),
            {
                "committee_brief.md": _panel_dir(tmp_path, year="fy24") / "committee_brief.md",
                "committee_brief_qa.json": _panel_dir(tmp_path, year="fy24") / "committee_brief_qa.json",
            },
        )[1],
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        lambda company, context=None, include_evidence_ids=False: (
            _write_committee_outputs(tmp_path, year="fy24"),
            {"committee_brief_qa.json": _panel_dir(tmp_path, year="fy24") / "committee_brief_qa.json"},
        )[1],
    )

    run_company_pipeline.run_panel_stage(company="polymatech", context=context)
    summary = json.loads(_panel_summary_path(tmp_path, year="fy24").read_text(encoding="utf-8"))

    assert summary["year"] == "fy24"
    assert summary["financial_context"]["status"] == "warning"
    assert summary["financial_context"]["available"] is True
    assert summary["stages"]["cim"]["status"] == "pass"
    assert summary["stages"]["pcim"]["status"] == "pass"


def test_panel_stage_stops_when_financial_quality_status_is_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _make_context(tmp_path)
    _write_financial_artifacts(tmp_path, quality_status="fail")
    _write_pcim(tmp_path)

    with pytest.raises(RuntimeError, match="financial_quality_summary.json status is fail"):
        run_company_pipeline.run_panel_stage(company="polymatech", context=context)

    summary = json.loads(_panel_summary_path(tmp_path, year="fy24").read_text(encoding="utf-8"))
    assert summary["status"] == "fail"
    assert summary["financial_context"]["status"] == "fail"


def test_panel_stage_stops_when_financial_truth_is_newer_than_pcim(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    truth_pack = tmp_path / "companies" / "polymatech" / "company_memory" / "financials" / "financial_truth_pack.json"
    truth_pack.parent.mkdir(parents=True, exist_ok=True)
    truth_pack.write_text(json.dumps({"years_covered": ["fy25"]}), encoding="utf-8")
    pcim_path = tmp_path / "companies" / "polymatech" / "company_memory" / "pcim_v1.json"
    pcim_path.touch()
    truth_pack.touch()

    with pytest.raises(RuntimeError, match="PCIM is stale relative to governed financial outputs"):
        run_company_pipeline.run_panel_stage(company="polymatech")
