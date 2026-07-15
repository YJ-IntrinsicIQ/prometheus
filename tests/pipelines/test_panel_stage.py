import json
from pathlib import Path

import pytest

from intelligence.investor_panel.forbidden_language import find_forbidden_recommendation_language
from pipelines import run_company_pipeline


def _panel_dir(base: Path, company: str = "polymatech") -> Path:
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


def _write_analyst_output(base: Path, analyst: str, *, status: str = "pass", warning_count: int = 0):
    panel_dir = _panel_dir(base)
    panel_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "doctrine_id": analyst,
        "evidence_grounding_status": status,
        "historical_context_used": True,
        "years_considered": ["fy24", "fy25"],
        "supporting_pcim_sections": ["risk_inputs"],
        "user_facing_brief": {"title": "t"},
        "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
        "evidence_grounding_warnings": [{"issue": str(i)} for i in range(warning_count)],
    }
    path = panel_dir / f"{analyst}_analysis.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_committee_outputs(base: Path, company: str = "polymatech", *, qa_status: str = "pass"):
    panel_dir = _panel_dir(base, company)
    panel_dir.mkdir(parents=True, exist_ok=True)
    synthesis = panel_dir / "committee_synthesis.json"
    synthesis.write_text(
        json.dumps(
            {
                "evidence_id_normalization": {"applied": True, "replacements": [], "unresolved_ids": []},
                "areas_of_disagreement": [{"disagreement_type": "different_emphasis"}],
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


def test_panel_stage_runs_analysts_in_correct_order_and_writes_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    calls = []

    def fake_panel(company, analyst=None, context=None):
        calls.append(analyst)
        _write_analyst_output(tmp_path, analyst, status="pass")
        return {f"{analyst}_analysis.json": _panel_dir(tmp_path) / f"{analyst}_analysis.json"}

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

    monkeypatch.setattr(run_company_pipeline, "run_investor_panel_stage", fake_panel)
    monkeypatch.setattr(run_company_pipeline, "run_committee_synthesis_stage", fake_synthesis)
    monkeypatch.setattr(run_company_pipeline, "run_committee_brief_stage", fake_brief)
    monkeypatch.setattr(run_company_pipeline, "run_committee_brief_qa_stage", fake_brief_qa)

    result = run_company_pipeline.run_panel_stage(company="polymatech")

    assert calls == ["graham", "buffett", "fisher", "munger", "lynch"]
    summary = json.loads((_panel_dir(tmp_path) / "panel_run_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "pass"
    assert result["panel_run_summary.json"].name == "panel_run_summary.json"


def test_panel_stage_records_pcim_source_manifest_warning_and_continues(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path, manifest_status="warning", manifest_warnings=["Missing fy23 in risk_evolution coverage."])

    def fake_panel(company, analyst=None, context=None):
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

    run_company_pipeline.run_panel_stage(company="polymatech")
    summary = json.loads((_panel_dir(tmp_path) / "panel_run_summary.json").read_text(encoding="utf-8"))
    assert summary["stages"][0]["stage"] == "pcim_check"
    assert summary["stages"][0]["status"] == "warning"
    assert "Missing fy23 in risk_evolution coverage." in summary["stages"][0]["warnings"]


def test_panel_stage_stops_on_failed_analyst(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)
    calls = []

    def fake_panel(company, analyst=None, context=None):
        calls.append(analyst)
        status = "fail" if analyst == "buffett" else "pass"
        _write_analyst_output(tmp_path, analyst, status=status)
        return {f"{analyst}_analysis.json": _panel_dir(tmp_path) / f"{analyst}_analysis.json"}

    monkeypatch.setattr(run_company_pipeline, "run_investor_panel_stage", fake_panel)

    with pytest.raises(RuntimeError, match="buffett analyst validation failed"):
        run_company_pipeline.run_panel_stage(company="polymatech")

    assert calls == ["graham", "buffett"]


def test_panel_stage_writes_summary_when_analyst_execution_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)

    def fake_panel(company, analyst=None, context=None):
        if analyst == "graham":
            raise RuntimeError("provider down")
        _write_analyst_output(tmp_path, analyst, status="pass")
        return {f"{analyst}_analysis.json": _panel_dir(tmp_path) / f"{analyst}_analysis.json"}

    monkeypatch.setattr(run_company_pipeline, "run_investor_panel_stage", fake_panel)

    with pytest.raises(RuntimeError, match="graham analyst execution failed"):
        run_company_pipeline.run_panel_stage(company="polymatech")

    summary_path = _panel_dir(tmp_path) / "panel_run_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "fail"
    assert summary["stages"][1]["stage"] == "graham"
    assert "stage execution failed" in summary["stages"][1]["failures"][0]


def test_panel_stage_allows_warning_and_records_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)

    def fake_panel(company, analyst=None, context=None):
        if analyst == "graham":
            _write_analyst_output(tmp_path, analyst, status="warning", warning_count=2)
        else:
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

    run_company_pipeline.run_panel_stage(company="polymatech")
    summary = json.loads((_panel_dir(tmp_path) / "panel_run_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "warning"
    assert summary["analysts"]["graham"]["status"] == "warning"


def test_panel_stage_fails_if_committee_brief_qa_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_pcim(tmp_path)

    monkeypatch.setattr(
        run_company_pipeline,
        "run_investor_panel_stage",
        lambda company, analyst=None, context=None: (
            _write_analyst_output(tmp_path, analyst, status="pass"),
            {f"{analyst}_analysis.json": _panel_dir(tmp_path) / f"{analyst}_analysis.json"},
        )[1],
    )
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

    def fake_panel(company, analyst=None, context=None):
        if analyst == "munger":
            path = _write_analyst_output(tmp_path, analyst, status="warning", warning_count=1)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["assessment"] = "The company disclosed an offer-for-sale and authorized placement."
            path.write_text(json.dumps(payload), encoding="utf-8")
        else:
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

    run_company_pipeline.run_panel_stage(company="polymatech")

    summary = json.loads((_panel_dir(tmp_path) / "panel_run_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "warning"
    assert summary["analysts"]["munger"]["status"] == "warning"
    assert "forbidden recommendation language" not in " ".join(summary["failures"]).lower()
