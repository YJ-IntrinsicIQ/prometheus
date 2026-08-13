import json
from pathlib import Path

import pytest

from core.company_context import CompanyContext
from pipelines import run_company_pipeline


def _context(company: str = "acme", year: str = "fy25") -> CompanyContext:
    context = CompanyContext(company=company, year=year)
    context.create_directories()
    return context


def test_financials_stage_runs_year_level_pipeline_in_canonical_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context()
    calls = []

    monkeypatch.setattr(run_company_pipeline, "run_financial_discovery", lambda context=None: calls.append("financial_discovery") or Path("financial_discovery.json"))
    monkeypatch.setattr(run_company_pipeline, "run_financial_extraction", lambda context=None: calls.append("financial_extraction") or Path("raw_financial_tables.json"))
    monkeypatch.setattr(run_company_pipeline, "run_financial_normalization", lambda context=None: calls.append("financial_normalization") or Path("normalized_fundamentals.json"))
    monkeypatch.setattr(run_company_pipeline, "run_financial_validation", lambda context=None: calls.append("financial_validation") or Path("financial_validation_report.json"))
    monkeypatch.setattr(run_company_pipeline, "run_financial_reconciliation", lambda context=None: calls.append("financial_reconciliation") or Path("financial_reconciliation_report.json"))
    monkeypatch.setattr(run_company_pipeline, "run_financial_ratios", lambda context=None: calls.append("financial_ratios") or Path("financial_ratios.json"))
    monkeypatch.setattr(run_company_pipeline, "run_financial_growth", lambda context=None: calls.append("financial_growth") or Path("financial_growth.json"))
    monkeypatch.setattr(run_company_pipeline, "run_corporate_actions", lambda context=None: calls.append("corporate_actions") or Path("corporate_actions.json"))
    monkeypatch.setattr(run_company_pipeline, "run_shareholding_pattern", lambda context=None: calls.append("shareholding_pattern") or Path("shareholding_pattern.json"))

    class _AuditReport:
        status = "warning"
        warnings = ["Only one financial year available."]
        hard_failures = []

    monkeypatch.setattr(
        run_company_pipeline,
        "write_financial_audit_report",
        lambda **kwargs: calls.append("financial_audit") or _AuditReport(),
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "get_llm",
        lambda: (_ for _ in ()).throw(AssertionError("LLM should not be called for financials stage")),
    )

    written = run_company_pipeline.run_financials_stage(context=context)

    assert calls == [
        "financial_discovery",
        "financial_extraction",
        "financial_normalization",
        "financial_validation",
        "financial_reconciliation",
        "financial_ratios",
        "financial_growth",
        "corporate_actions",
        "shareholding_pattern",
        "financial_audit",
    ]
    assert written["financial_audit_report.json"] == context.financials_dir / "financial_audit_report.json"


def test_financial_memory_stage_runs_company_level_pipeline_in_canonical_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []

    monkeypatch.setattr(
        run_company_pipeline,
        "run_financial_trends_stage",
        lambda company, context=None: calls.append("financial_trends") or {"financial_trends.json": Path("financial_trends.json")},
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_financial_quality_stage",
        lambda company, context=None: calls.append("financial_quality") or {"financial_quality_summary.json": Path("financial_quality_summary.json")},
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "_refresh_year_level_financial_quality",
        lambda company: calls.append("year_financial_quality") or {},
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "run_financial_attribution_stage",
        lambda company, context=None: calls.append("financial_attribution") or {"financial_driver_attribution.json": Path("financial_driver_attribution.json")},
    )

    class _AuditReport:
        status = "pass"
        warnings = []
        hard_failures = []

    monkeypatch.setattr(
        run_company_pipeline,
        "write_financial_memory_audit_report",
        lambda **kwargs: calls.append("financial_memory_audit") or _AuditReport(),
    )
    monkeypatch.setattr(
        run_company_pipeline,
        "write_financial_memory_artifacts",
        lambda **kwargs: calls.append("financial_memory_artifacts") or {"financial_memory_summary.json": Path("financial_memory_summary.json")},
    )

    written = run_company_pipeline.run_financial_memory_stage(company="acme")

    assert calls == [
        "financial_trends",
        "year_financial_quality",
        "financial_quality",
        "financial_attribution",
        "financial_memory_artifacts",
        "financial_memory_audit",
    ]
    assert written["financial_memory_audit_report.json"] == Path("companies") / "acme" / "company_memory" / "financials" / "financial_memory_audit_report.json"


def test_refresh_year_level_financial_quality_covers_every_discovered_financial_year(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    for year in ("fy24", "fy25", "fy26"):
        financial_root = tmp_path / "companies" / "acme" / year / "financials"
        financial_root.mkdir(parents=True)
        (financial_root / "normalized_fundamentals.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        run_company_pipeline,
        "write_financial_quality_summary",
        lambda **kwargs: calls.append(kwargs["year"]),
    )

    written = run_company_pipeline._refresh_year_level_financial_quality("acme")

    assert calls == ["fy24", "fy25", "fy26"]
    assert set(written) == {
        "fy24/financial_quality_summary.json",
        "fy25/financial_quality_summary.json",
        "fy26/financial_quality_summary.json",
    }


def test_financials_stage_writes_audit_before_reraising_downstream_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context()
    calls = []

    monkeypatch.setattr(run_company_pipeline, "run_financial_discovery", lambda context=None: calls.append("financial_discovery") or Path("financial_discovery.json"))
    monkeypatch.setattr(run_company_pipeline, "run_financial_extraction", lambda context=None: calls.append("financial_extraction") or Path("raw_financial_tables.json"))
    monkeypatch.setattr(run_company_pipeline, "run_financial_normalization", lambda context=None: calls.append("financial_normalization") or Path("normalized_fundamentals.json"))
    monkeypatch.setattr(run_company_pipeline, "run_financial_validation", lambda context=None: calls.append("financial_validation") or Path("financial_validation_report.json"))
    monkeypatch.setattr(run_company_pipeline, "run_financial_reconciliation", lambda context=None: calls.append("financial_reconciliation") or Path("financial_reconciliation_report.json"))

    def _raise_on_ratios(context=None):
        calls.append("financial_ratios")
        raise RuntimeError("validation failed upstream")

    monkeypatch.setattr(run_company_pipeline, "run_financial_ratios", _raise_on_ratios)
    monkeypatch.setattr(run_company_pipeline, "run_financial_growth", lambda context=None: calls.append("financial_growth") or Path("financial_growth.json"))
    monkeypatch.setattr(run_company_pipeline, "run_corporate_actions", lambda context=None: calls.append("corporate_actions") or Path("corporate_actions.json"))
    monkeypatch.setattr(run_company_pipeline, "run_shareholding_pattern", lambda context=None: calls.append("shareholding_pattern") or Path("shareholding_pattern.json"))

    class _AuditReport:
        status = "fail"
        warnings = []
        hard_failures = ["validation failed upstream"]

    monkeypatch.setattr(
        run_company_pipeline,
        "write_financial_audit_report",
        lambda **kwargs: calls.append("financial_audit") or _AuditReport(),
    )

    try:
        run_company_pipeline.run_financials_stage(context=context)
    except RuntimeError as exc:
        assert str(exc) == "validation failed upstream"
    else:
        raise AssertionError("financials stage should re-raise downstream failures")

    assert calls == [
        "financial_discovery",
        "financial_extraction",
        "financial_normalization",
        "financial_validation",
        "financial_reconciliation",
        "financial_ratios",
        "financial_audit",
    ]


def test_financials_stage_blocks_downstream_when_final_audit_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context()
    for name in (
        "run_financial_discovery",
        "run_financial_extraction",
        "run_financial_normalization",
        "run_financial_validation",
        "run_financial_reconciliation",
        "run_financial_ratios",
        "run_financial_growth",
        "run_corporate_actions",
        "run_shareholding_pattern",
    ):
        monkeypatch.setattr(run_company_pipeline, name, lambda context=None: Path("output.json"))

    class _AuditReport:
        status = "fail"
        warnings = []
        hard_failures = ["financial_validation_report.json status is fail."]

    monkeypatch.setattr(run_company_pipeline, "write_financial_audit_report", lambda **kwargs: _AuditReport())

    with pytest.raises(RuntimeError, match="financials audit failed for acme fy25"):
        run_company_pipeline.run_financials_stage(context=context)


def test_production_reuses_only_same_year_non_failing_financial_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = _context(year="fy25")
    required = {
        "normalized_fundamentals.json": {},
        "financial_validation_report.json": {"status": "warning", "hard_failures": []},
        "financial_reconciliation_report.json": {"status": "pass", "hard_failures": []},
        "financial_ratios.json": {},
        "financial_growth.json": {},
        "corporate_actions.json": {},
        "shareholding_pattern.json": {},
        "financial_audit_report.json": {"status": "warning", "hard_failures": []},
    }
    for filename, extra in required.items():
        payload = {"company": "acme", "year": "fy25", **extra}
        (context.financials_dir / filename).write_text(json.dumps(payload), encoding="utf-8")

    called = []
    monkeypatch.setattr(
        run_company_pipeline,
        "run_financials_stage",
        lambda context=None: called.append("financials"),
    )
    outputs = run_company_pipeline._build_stage_output_map(context)
    result = run_company_pipeline._run_stage_by_name(
        "financials",
        context,
        stage_outputs=outputs,
        options={"_profile_name": "production"},
        state={},
    )

    assert called == []
    assert result["status"] == "warning"
    assert "no cross-period values" in result["warnings"][0]

    required["normalized_fundamentals.json"]["year"] = "fy24"
    (context.financials_dir / "normalized_fundamentals.json").write_text(
        json.dumps({"company": "acme", "year": "fy24"}), encoding="utf-8"
    )
    run_company_pipeline._run_stage_by_name(
        "financials",
        context,
        stage_outputs=outputs,
        options={"_profile_name": "production"},
        state={},
    )
    assert called == ["financials"]
