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
    monkeypatch.setattr(run_company_pipeline, "run_cim_stage", lambda company, context=None: calls.append("cim") or {})
    monkeypatch.setattr(
        run_company_pipeline,
        "run_multi_year_memory_stage",
        lambda company, context=None: calls.append("multi_year_memory") or {},
    )

    run_company_pipeline.run_all(context=context)

    assert calls == [
        "preflight",
        "discovery",
        "extraction",
        "cleaning",
        "business_understanding",
        "business_intelligence",
        "intelligence",
        "cim",
        "multi_year_memory",
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
        "cim",
        "pcim",
        "multi_year_memory",
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
    assert "Requires:" in output
    assert "LLM calls:" in output


def test_company_level_stage_rejects_year(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_company_pipeline.py", "acme", "fy25", "--stage", "panel"])
    with pytest.raises(SystemExit):
        run_company_pipeline.main()


def test_multi_year_warning_when_only_one_valid_year(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    intelligence_dir = tmp_path / "companies" / "acme" / "fy25" / "intelligence"
    _write_json(intelligence_dir / "company_intelligence.json", {"company": "acme"})
    _write_json(intelligence_dir / "business_classification.json", {"business_dnas": ["Manufacturing"]})

    years, warnings = run_company_pipeline._require_company_level_intelligence("acme", "multi_year_memory")
    assert years == ["fy25"]
    assert warnings
