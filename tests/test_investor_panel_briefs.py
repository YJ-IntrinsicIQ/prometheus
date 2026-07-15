import json
from pathlib import Path

import pytest

from intelligence.investor_panel.briefs import InvestorBriefBuilder
from pipelines import run_company_pipeline


def _write_analysis(base_dir: Path, company: str, analyst: str, *, rating="mixed", findings=None, red_flags=None, uncertainties=None):
    panel_dir = base_dir / "companies" / company / "company_memory" / "investor_panel"
    panel_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "doctrine_id": analyst,
        "company": company,
        "pcim_version": "1.0",
        "pcim_source": f"companies/{company}/company_memory/pcim_v1.json",
        "analysis_mode": "llm_reasoning_v1",
        "sections_consumed": ["risk_inputs", "evidence_map"],
        "assessment": {
            "summary": "The analyst view is grounded in PCIM and evidence_map, with source_item_id references removed later."
        },
        "rating": rating,
        "key_findings": findings or [
            "Customer retention looks solid (ev_test_1).",
            "Platform scale appears real without a buy recommendation.",
        ],
        "red_flags": red_flags or [
            "Customer concentration remains meaningful (ev_test_2).",
        ],
        "open_uncertainties": uncertainties or [
            "Free cash flow detail is missing.",
            "Management compensation detail is missing.",
        ],
        "evidence_ids": ["ev_test_1", "ev_test_2"],
        "supporting_pcim_sections": ["risk_inputs", "evidence_map"],
        "reasoning_limits": ["This uses PCIM only."],
        "user_facing_brief": {
            "title": {
                "graham": "Graham School of Thought: Downside Protection",
                "buffett": "Buffett School of Thought: Business Quality & Capital Allocation",
                "fisher": "Fisher School of Thought: Growth Quality & Management Ambition",
                "munger": "Munger School of Thought: Incentives, Governance & Avoidable Mistakes",
                "lynch": "Lynch School of Thought: Simple Story, Growth Runway & Hype Check",
            }[analyst],
            "lens": "This school looks at the business through a specific investing lens.",
            "what_looks_good": ["Some strengths are visible in the current analysis."],
            "what_needs_caution": ["Some caution is still warranted."],
            "what_is_missing": ["Some important evidence is still missing."],
            "bottom_line": "The current view is useful, but it is not the full picture yet.",
        },
        "generated_at": "2026-07-10T12:00:00Z",
    }
    (panel_dir / f"{analyst}_analysis.json").write_text(json.dumps(payload), encoding="utf-8")


def test_briefs_are_generated_from_analysis_files_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_analysis(tmp_path, "acme", "graham")
    pcim_path = tmp_path / "companies" / "acme" / "company_memory" / "pcim_v1.json"
    pcim_path.write_text("SHOULD NOT BE READ", encoding="utf-8")

    written = InvestorBriefBuilder(company="acme").build()

    brief_text = written["graham_brief.md"].read_text(encoding="utf-8")
    assert "SHOULD NOT BE READ" not in brief_text


def test_renderer_uses_only_user_facing_brief(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_analysis(
        tmp_path,
        "acme",
        "graham",
        findings=["INTERNAL FINDING SHOULD NOT APPEAR."],
        red_flags=["INTERNAL RED FLAG SHOULD NOT APPEAR."],
        uncertainties=["INTERNAL UNCERTAINTY SHOULD NOT APPEAR."],
    )
    panel_dir = tmp_path / "companies" / "acme" / "company_memory" / "investor_panel"
    payload = json.loads((panel_dir / "graham_analysis.json").read_text(encoding="utf-8"))
    payload["user_facing_brief"] = {
        "title": "Graham School of Thought: Downside Protection",
        "lens": "This lens looks for downside protection first.",
        "what_looks_good": ["Visible balance-sheet caution."],
        "what_needs_caution": ["Concentration remains a concern."],
        "what_is_missing": ["Cash-flow detail is still incomplete."],
        "bottom_line": "The downside picture is usable but still incomplete.",
    }
    (panel_dir / "graham_analysis.json").write_text(json.dumps(payload), encoding="utf-8")

    written = InvestorBriefBuilder(company="acme").build()
    brief_text = written["graham_brief.md"].read_text(encoding="utf-8")

    assert "Visible balance-sheet caution." in brief_text
    assert "Concentration remains a concern." in brief_text
    assert "Cash-flow detail is still incomplete." in brief_text
    assert "INTERNAL FINDING SHOULD NOT APPEAR." not in brief_text
    assert "INTERNAL RED FLAG SHOULD NOT APPEAR." not in brief_text
    assert "INTERNAL UNCERTAINTY SHOULD NOT APPEAR." not in brief_text


def test_briefs_do_not_contain_internal_terms_or_evidence_ids(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_analysis(tmp_path, "acme", "graham")

    written = InvestorBriefBuilder(company="acme").build()
    brief_text = written["graham_brief.md"].read_text(encoding="utf-8")

    assert "PCIM" not in brief_text
    assert "evidence_map" not in brief_text
    assert "sections_consumed" not in brief_text
    assert "analysis_mode" not in brief_text
    assert "reasoning_limits" not in brief_text
    assert "source_item_id" not in brief_text
    assert "source_artifact" not in brief_text
    assert "ev_test_1" not in brief_text
    assert "ev_test_2" not in brief_text
    assert "provided in the." not in brief_text


def test_brief_index_preserves_hidden_evidence_traceability(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_analysis(tmp_path, "acme", "graham")
    _write_analysis(tmp_path, "acme", "buffett")

    written = InvestorBriefBuilder(company="acme").build()
    index_payload = json.loads(written["brief_index.json"].read_text(encoding="utf-8"))

    assert index_payload["company"] == "acme"
    assert index_payload["hidden_evidence_ids_by_analyst"]["graham"] == ["ev_test_1", "ev_test_2"]
    assert any(path.endswith("graham_analysis.json") for path in index_payload["source_analysis_files"])


def test_investor_briefs_stage_makes_no_llm_call(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_analysis(tmp_path, "acme", "graham")
    monkeypatch.setattr(
        run_company_pipeline,
        "get_llm",
        lambda: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )

    written = run_company_pipeline.run_investor_briefs_stage(company="acme", context=None)

    assert "graham_brief.md" in written


def test_briefs_do_not_use_recommendation_language(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_analysis(
        tmp_path,
        "acme",
        "buffett",
        findings=["The business looks like a strong buy if growth continues."],
        red_flags=["Investors may want to sell if margins weaken."],
    )

    written = InvestorBriefBuilder(company="acme").build()
    brief_text = written["buffett_brief.md"].read_text(encoding="utf-8").lower()

    assert "strong buy" not in brief_text
    assert " buy " not in f" {brief_text} "
    assert " sell " not in f" {brief_text} "
    assert " hold " not in f" {brief_text} "


def test_missing_evidence_is_explained_in_user_friendly_language(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_analysis(
        tmp_path,
        "acme",
        "lynch",
        uncertainties=["No board or committee references are provided.", "Free cash flow detail is missing."],
    )
    panel_dir = tmp_path / "companies" / "acme" / "company_memory" / "investor_panel"
    payload = json.loads((panel_dir / "lynch_analysis.json").read_text(encoding="utf-8"))
    payload["user_facing_brief"]["what_is_missing"] = [
        "No board or committee references are provided.",
        "Free cash flow detail is missing.",
    ]
    (panel_dir / "lynch_analysis.json").write_text(json.dumps(payload), encoding="utf-8")

    written = InvestorBriefBuilder(company="acme").build()
    brief_text = written["lynch_brief.md"].read_text(encoding="utf-8")

    assert "## What Is Missing" in brief_text
    assert "Free cash flow detail is missing." in brief_text
    assert "No board or committee references are provided." in brief_text


def test_output_works_when_one_analyst_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_analysis(tmp_path, "acme", "graham")
    _write_analysis(tmp_path, "acme", "buffett")

    written = InvestorBriefBuilder(company="acme").build()
    index_payload = json.loads(written["brief_index.json"].read_text(encoding="utf-8"))

    assert "graham_brief.md" in written
    assert "buffett_brief.md" in written
    assert "munger_brief.md" not in written
    assert any("munger_analysis.json was not found" in item for item in index_payload["limitations"])


def test_briefs_render_embedded_user_facing_brief(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_analysis(tmp_path, "acme", "graham")
    panel_dir = tmp_path / "companies" / "acme" / "company_memory" / "investor_panel"
    payload = json.loads((panel_dir / "graham_analysis.json").read_text(encoding="utf-8"))
    payload["user_facing_brief"]["lens"] = "This lens focuses on downside protection first."
    payload["user_facing_brief"]["what_looks_good"] = ["Balance-sheet caution is visible."]
    payload["user_facing_brief"]["what_needs_caution"] = ["Risk concentration is still meaningful."]
    payload["user_facing_brief"]["what_is_missing"] = ["Cash-flow detail is still incomplete."]
    payload["user_facing_brief"]["bottom_line"] = "The downside looks manageable, but the evidence is not complete."
    (panel_dir / "graham_analysis.json").write_text(json.dumps(payload), encoding="utf-8")

    written = InvestorBriefBuilder(company="acme").build()
    brief_text = written["graham_brief.md"].read_text(encoding="utf-8")

    assert "This lens focuses on downside protection first." in brief_text
    assert "- Balance-sheet caution is visible." in brief_text
    assert "- Risk concentration is still meaningful." in brief_text
    assert "- Cash-flow detail is still incomplete." in brief_text
    assert "The downside looks manageable, but the evidence is not complete." in brief_text


def test_missing_user_facing_brief_does_not_fall_back(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_analysis(tmp_path, "acme", "graham")
    panel_dir = tmp_path / "companies" / "acme" / "company_memory" / "investor_panel"
    payload = json.loads((panel_dir / "graham_analysis.json").read_text(encoding="utf-8"))
    payload.pop("user_facing_brief")
    (panel_dir / "graham_analysis.json").write_text(json.dumps(payload), encoding="utf-8")

    written = InvestorBriefBuilder(company="acme").build()
    index_payload = json.loads(written["brief_index.json"].read_text(encoding="utf-8"))

    assert "graham_brief.md" not in written
    assert any("graham_analysis.json was skipped" in item for item in index_payload["limitations"])


def test_main_runs_investor_briefs_without_year(monkeypatch):
    calls = []

    monkeypatch.setattr(
        run_company_pipeline,
        "run_investor_briefs_stage",
        lambda company, context=None: calls.append(
            ("run_investor_briefs_stage", company, context)
        ),
    )
    monkeypatch.setattr(
        run_company_pipeline.sys,
        "argv",
        ["run_company_pipeline", "tanla", "--stage", "investor_briefs"],
    )

    run_company_pipeline.main()

    assert calls == [("run_investor_briefs_stage", "tanla", None)]
