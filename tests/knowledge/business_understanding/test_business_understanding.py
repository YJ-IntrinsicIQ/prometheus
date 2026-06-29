import json
from pathlib import Path

import pytest

from core.company_context import CompanyContext
from pipelines import run_company_pipeline
from pipelines.pipeline_context import set_context
from knowledge.business_understanding import run_business_understanding


def test_run_business_understanding_persists_artifacts(tmp_path, monkeypatch):
    context = CompanyContext(company="tips", year="fy24")
    context.intelligence_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    set_context(context)

    bundle = run_business_understanding(context=context)

    assert bundle["company_memory"].company_id == "tips"
    assert bundle["business_blueprint"].metadata.company == "tips"
    assert bundle["business_classification"]["report_template"]

    memory_path = context.intelligence_dir / "company_memory.json"
    blueprint_path = context.intelligence_dir / "business_blueprint.json"
    classification_path = context.intelligence_dir / "business_classification.json"

    assert memory_path.exists()
    assert blueprint_path.exists()
    assert classification_path.exists()

    assert json.loads(memory_path.read_text())["company_id"] == "tips"


def test_pipeline_wiring_runs_business_understanding_before_discovery(monkeypatch):
    calls = []

    monkeypatch.setattr(run_company_pipeline, "run_business_understanding", lambda: calls.append("business_understanding"))
    monkeypatch.setattr(run_company_pipeline, "run_discovery", lambda: calls.append("discovery"))
    monkeypatch.setattr(run_company_pipeline, "run_extraction", lambda: calls.append("extraction"))
    monkeypatch.setattr(run_company_pipeline, "run_cleaning", lambda: calls.append("cleaning"))
    monkeypatch.setattr(run_company_pipeline, "run_intelligence", lambda: calls.append("intelligence"))

    monkeypatch.setattr(
        run_company_pipeline,
        "CompanyContext",
        lambda company, year: type("Context", (), {"company": company, "year": year, "raw_dir": Path("/tmp"), "extracted_dir": Path("/tmp"), "intelligence_dir": Path("/tmp"), "create_directories": lambda self: None})(),
    )
    monkeypatch.setattr(run_company_pipeline, "set_context", lambda context: None)
    monkeypatch.setattr(run_company_pipeline.sys, "argv", ["run_company_pipeline", "tips", "fy24", "--stage", "all"])

    run_company_pipeline.main()

    assert calls[:2] == ["business_understanding", "discovery"]
