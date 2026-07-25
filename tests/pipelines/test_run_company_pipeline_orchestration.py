import json
import sys
from pathlib import Path

import pytest

from core.company_context import CompanyContext
from pipelines import run_company_pipeline


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _context(tmp_path: Path, company: str = "acme", year: str = "fy25") -> CompanyContext:
    context = CompanyContext(company=company, year=year)
    context.create_directories()
    return context


def test_run_all_executes_stages_in_dependency_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)
    calls = []

    monkeypatch.setattr(run_company_pipeline, "_run_preflight", lambda ctx: calls.append("preflight") or {})
    monkeypatch.setattr(run_company_pipeline, "run_discovery", lambda context=None: calls.append("discovery") or {})
    monkeypatch.setattr(run_company_pipeline, "run_extraction", lambda context=None: calls.append("extraction") or {})
    monkeypatch.setattr(run_company_pipeline, "run_cleaning", lambda context=None: calls.append("cleaning") or {})

    def fake_bu(context=None):
        calls.append("business_understanding")
        _write_json(context.intelligence_dir / "business_blueprint.json", {"business_understanding": {"business_summary": "x"}})
        classification = {
            "business_dnas": ["Manufacturing"],
            "question_modules": ["capital_allocation"],
            "rationale": ["Synthetic manufacturing evidence is present."],
            "evidence_used": ["business_summary=x"],
        }
        _write_json(context.intelligence_dir / "business_classification.json", classification)
        return {"business_classification": classification}

    monkeypatch.setattr(
        run_company_pipeline,
        "run_business_understanding_stage",
        fake_bu,
    )

    def fake_bi(context=None, bundle=None):
        calls.append("business_intelligence")
        _write_json(context.intelligence_dir / "discovery_plan.json", {"questions": []})
        _write_json(context.intelligence_dir / "module_results.json", {"module_results": [{"module": "x"}]})
        _write_json(context.intelligence_dir / "discovery_runtime.json", {"statistics": {"questions_answered": 1}})
        return {}

    monkeypatch.setattr(
        run_company_pipeline,
        "run_business_intelligence_stage",
        fake_bi,
    )
    monkeypatch.setattr(run_company_pipeline, "run_intelligence", lambda context=None: calls.append("intelligence") or {})
    monkeypatch.setattr(
        run_company_pipeline,
        "_require_company_level_intelligence",
        lambda company, stage_name: (["fy25"], []),
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_multi_year_memory_stage",
        lambda company, context=None: calls.append("multi_year_memory") or {},
    )
    monkeypatch.setattr(run_company_pipeline, "run_cim_stage", lambda company, context=None: calls.append("cim") or {})

    run_company_pipeline.run_all(context=context)

    assert calls == [
        "preflight",
        "discovery",
        "extraction",
        "cleaning",
        "business_understanding",
        "business_intelligence",
        "intelligence",
        "multi_year_memory",
        "cim",
    ]
    summary = json.loads((context.year_root / "run_summary.json").read_text(encoding="utf-8"))
    assert [stage["stage"] for stage in summary["stages"]] == [
        "preflight",
        "discovery",
        "extraction",
        "cleaning",
        "business_understanding",
        "business_intelligence",
        "intelligence",
        "multi_year_memory",
        "cim",
        "pcim",
    ]
    assert summary["status"] == "pass"


def test_run_all_writes_fail_summary_on_preflight_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)

    with pytest.raises(RuntimeError, match="No raw documents found"):
        run_company_pipeline.run_all(context=context)

    summary_path = context.year_root / "run_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "fail"
    assert summary["stages"][0]["stage"] == "preflight"
    assert summary["stages"][0]["status"] == "fail"


def test_discovery_fails_without_raw_docs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)

    with pytest.raises(RuntimeError, match="No raw documents found"):
        run_company_pipeline.run_discovery(context=context)

    assert not (context.raw_dir / "project_discovery_results.json").exists()


def test_discovery_fails_when_chunk_generation_is_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)
    pdf_path = context.raw_dir / "annual_report.pdf"
    pdf_path.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(run_company_pipeline, "_iter_raw_document_candidates", lambda ctx: [pdf_path])
    monkeypatch.setattr(run_company_pipeline, "_read_text_from_document", lambda path: "extractable text")

    def fake_clean_chunks(ctx):
        chunk_path = ctx.extracted_dir / "clean_chunks.json"
        _write_json(chunk_path, [])
        return chunk_path

    monkeypatch.setattr(run_company_pipeline, "_ensure_clean_chunks", fake_clean_chunks)

    with pytest.raises(RuntimeError, match="chunk generation produced 0 chunks"):
        run_company_pipeline.run_discovery(context=context)


def test_extraction_requires_nonempty_discovery_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)
    for filename in run_company_pipeline.DISCOVERY_OUTPUT_FILES:
        _write_json(context.raw_dir / filename, [])

    with pytest.raises(RuntimeError, match="requires non-empty discovery inputs"):
        run_company_pipeline.run_extraction(context=context)


def test_cleaning_requires_nonempty_extraction_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)
    for filename in run_company_pipeline.EXTRACTION_OUTPUT_FILES:
        _write_json(context.extracted_dir / filename, [])

    with pytest.raises(RuntimeError, match="requires non-empty extraction inputs"):
        run_company_pipeline.run_cleaning(context=context)


def test_cleaning_writes_evidence_layer_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)
    for filename in run_company_pipeline.EXTRACTION_OUTPUT_FILES:
        _write_json(context.extracted_dir / filename, [{"value": "x"}])
    for filename in run_company_pipeline.CLEANING_OUTPUT_FILES:
        _write_json(context.extracted_dir / filename, [{"value": "x"}])

    calls = []
    monkeypatch.setattr(
        run_company_pipeline,
        "run_steps",
        lambda stage_label, steps: calls.append(stage_label),
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "write_evidence_layer_summary",
        lambda ctx: calls.append(f"summary:{ctx.company}:{ctx.year}"),
    )

    counts = run_company_pipeline.run_cleaning(context=context)

    assert calls == ["CLEANING", "summary:acme:fy25"]
    assert counts["clean_projects.json"] == 1


def test_intelligence_requires_business_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)
    for filename in run_company_pipeline.CLEANING_OUTPUT_FILES:
        _write_json(context.extracted_dir / filename, [{"value": "x"}])

    with pytest.raises(RuntimeError, match="requires non-empty business_understanding inputs"):
        run_company_pipeline.run_intelligence(context=context)


def test_list_stages_prints_catalog(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_company_pipeline.py", "--list-stages"])
    run_company_pipeline.main()
    output = capsys.readouterr().out
    assert "discovery" in output
    assert "audit" in output
    assert "Requires:" in output
    assert "LLM calls:" in output


def test_audit_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "--stage", "audit"])
    assert args.stage == "audit"


def test_financial_pcim_validation_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "fy25", "--stage", "financial_pcim_validation"])
    assert args.stage == "financial_pcim_validation"


def test_audit_stage_writes_financial_quality_scorecard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(
        run_company_pipeline,
        "run_company_artifact_audit",
        lambda company, fix_safe=False: calls.append(("artifact_audit", company, fix_safe))
        or {"company_artifact_audit.json": Path("companies") / company / "audit" / "company_artifact_audit.json"},
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "write_financial_quality_scorecard",
        lambda company, companies_root=Path("companies"): calls.append(("financial_scorecard", company, companies_root))
        or {"financial_quality_scorecard.json": Path("companies") / company / "audit" / "financial_quality_scorecard.json"},
    )

    outputs = run_company_pipeline.run_audit_stage(company="acme", fix_safe=True)

    assert calls[0] == ("artifact_audit", "acme", True)
    assert calls[1] == ("financial_scorecard", "acme", Path("companies"))
    assert "financial_quality_scorecard.json" in outputs


def test_financial_discovery_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "fy25", "--stage", "financial_discovery"])
    assert args.stage == "financial_discovery"


def test_financial_extraction_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "fy25", "--stage", "financial_extraction"])
    assert args.stage == "financial_extraction"


def test_financial_normalization_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "fy25", "--stage", "financial_normalization"])
    assert args.stage == "financial_normalization"


def test_financial_validation_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "fy25", "--stage", "financial_validation"])
    assert args.stage == "financial_validation"


def test_financial_reconciliation_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "fy25", "--stage", "financial_reconciliation"])
    assert args.stage == "financial_reconciliation"


def test_financial_ratios_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "fy25", "--stage", "financial_ratios"])
    assert args.stage == "financial_ratios"


def test_financial_growth_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "fy25", "--stage", "financial_growth"])
    assert args.stage == "financial_growth"


def test_corporate_actions_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "fy25", "--stage", "corporate_actions"])
    assert args.stage == "corporate_actions"


def test_shareholding_pattern_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "fy25", "--stage", "shareholding_pattern"])
    assert args.stage == "shareholding_pattern"


def test_financial_trends_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "--stage", "financial_trends"])
    assert args.stage == "financial_trends"


def test_financial_quality_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "--stage", "financial_quality"])
    assert args.stage == "financial_quality"


def test_financial_attribution_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "--stage", "financial_attribution"])
    assert args.stage == "financial_attribution"


def test_financials_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "fy25", "--stage", "financials"])
    assert args.stage == "financials"


def test_financial_memory_stage_exists_in_parser():
    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["acme", "--stage", "financial_memory"])
    assert args.stage == "financial_memory"


def test_financial_discovery_fails_without_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)

    with pytest.raises(RuntimeError, match="financial_discovery requires raw or extracted sources"):
        run_company_pipeline.run_financial_discovery(context=context)


def test_financial_extraction_requires_discovery_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)

    with pytest.raises(RuntimeError, match="financial_extraction requires financial_discovery.json"):
        run_company_pipeline.run_financial_extraction(context=context)


def test_financial_normalization_requires_raw_tables(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)

    with pytest.raises(RuntimeError, match="financial_normalization requires raw_financial_tables.json"):
        run_company_pipeline.run_financial_normalization(context=context)


def test_financial_validation_requires_normalized_fundamentals(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)

    with pytest.raises(RuntimeError, match="financial_validation requires normalized_fundamentals.json"):
        run_company_pipeline.run_financial_validation(context=context)


def test_financial_ratios_requires_reconciliation_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)
    _write_json(context.financials_dir / "normalized_fundamentals.json", {"company": "acme"})

    with pytest.raises(RuntimeError, match="financial_ratios requires financial_reconciliation_report.json"):
        run_company_pipeline.run_financial_ratios(context=context)


def test_financial_growth_requires_normalized_fundamentals(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)

    with pytest.raises(RuntimeError, match="financial_growth requires normalized_fundamentals.json"):
        run_company_pipeline.run_financial_growth(context=context)


def test_corporate_actions_requires_normalized_fundamentals(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)

    with pytest.raises(RuntimeError, match="corporate_actions requires normalized_fundamentals.json"):
        run_company_pipeline.run_corporate_actions(context=context)


def test_shareholding_pattern_requires_normalized_fundamentals(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)

    with pytest.raises(RuntimeError, match="shareholding_pattern requires normalized_fundamentals.json"):
        run_company_pipeline.run_shareholding_pattern(context=context)


def test_financial_trends_requires_at_least_one_financial_year(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="financial_trends requires at least one valid financial year"):
        run_company_pipeline.run_financial_trends_stage(company="acme")


def test_financial_quality_requires_financial_trends(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="financial_quality requires financial_trends.json"):
        run_company_pipeline.run_financial_quality_stage(company="acme")


def test_financial_quality_stage_writes_year_level_summary_when_context_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(tmp_path)

    class _Report:
        status = "warning"
        basis_used = "consolidated"
        warnings = ["capex missing"]

    calls = {}

    def _write_financial_quality_summary(**kwargs):
        calls.update(kwargs)
        output_path = kwargs["output_path"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("{}", encoding="utf-8")
        return _Report()

    monkeypatch.setattr(
        run_company_pipeline,
        "write_financial_quality_summary",
        _write_financial_quality_summary,
    )

    written = run_company_pipeline.run_financial_quality_stage(company="acme", context=context)

    assert calls["year"] == "fy25"
    assert calls["financial_root"] == context.financials_dir
    assert written["financial_quality_summary.json"] == context.financials_dir / "financial_quality_summary.json"


def test_financial_attribution_requires_financial_trends(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="financial_attribution requires financial_trends.json"):
        run_company_pipeline.run_financial_attribution_stage(company="acme")


def test_panel_stage_accepts_year(monkeypatch):
    calls = []

    monkeypatch.setattr(
        run_company_pipeline,
        "run_panel_stage",
        lambda company, context=None, include_evidence_ids=False: calls.append(
            (company, getattr(context, "year", None), include_evidence_ids)
        ) or {},
    )
    monkeypatch.setattr(sys, "argv", ["run_company_pipeline.py", "acme", "fy25", "--stage", "panel"])

    run_company_pipeline.main()

    assert calls == [("acme", "fy25", False)]


def test_multi_year_warning_when_only_one_valid_year(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    intelligence_dir = tmp_path / "companies" / "acme" / "fy25" / "intelligence"
    _write_json(intelligence_dir / "company_intelligence.json", {"company": "acme"})
    _write_json(intelligence_dir / "business_classification.json", {"business_dnas": ["Manufacturing"]})

    years, warnings = run_company_pipeline._require_company_level_intelligence("acme", "multi_year_memory")
    assert years == ["fy25"]
    assert warnings
