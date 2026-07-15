import json
from pathlib import Path

import pytest

from intelligence.investor_panel.committee_brief_qa import CommitteeBriefQAGate
from intelligence.investor_panel.committee_brief_renderer import CommitteeBriefRenderer
from pipelines import run_company_pipeline


def _committee_payload():
    return {
        "company": "polymatech",
        "analysis_mode": "committee_synthesis_v1",
        "analysts_considered": ["graham", "buffett", "fisher", "munger", "lynch"],
        "missing_analysts": [],
        "excluded_analysts": [],
        "years_considered": ["fy24", "fy25"],
        "overall_committee_view": {
            "summary": "The committee sees growth ambition colliding with financing and execution risk.",
            "confidence": "medium",
            "dominant_tension": "Growth ambition versus balance-sheet resilience.",
        },
        "areas_of_agreement": [
            {
                "theme": "Capital-intensive manufacturing",
                "analysts": ["graham", "buffett", "fisher", "munger", "lynch"],
                "summary": "All analysts describe a capital-intensive manufacturing buildout.",
                "evidence_ids": ["ev_fy25_a"],
            }
        ],
        "areas_of_disagreement": [
            {
                "theme": "Growth versus downside",
                "analysts_positive_or_less_concerned": ["fisher", "lynch"],
                "analysts_cautious_or_negative": ["graham", "munger"],
                "disagreement_type": "risk_weighting_difference",
                "summary": "Some analysts emphasize growth while others focus on downside risk.",
                "why_it_matters": "This affects how durable the expansion story looks under funding pressure.",
                "evidence_ids": ["ev_fy25_b"],
            }
        ],
        "strongest_positive_signals": [
            {
                "signal": "Visible capacity expansion",
                "supported_by": ["buffett", "fisher"],
                "summary": "The company has visible project momentum and expansion signals.",
                "evidence_ids": ["ev_fy25_c"],
            }
        ],
        "most_important_risks": [
            {
                "risk": "Liquidity pressure",
                "raised_by": ["graham", "munger"],
                "summary": "Liquidity pressure remains a meaningful risk.",
                "severity": "high",
                "evidence_ids": ["ev_fy25_d"],
            }
        ],
        "critical_unknowns": [
            {
                "unknown": "Cash flow support",
                "raised_by": ["graham", "buffett"],
                "why_it_matters": "Cash flow quality determines whether capex can be funded safely.",
            }
        ],
        "investigation_questions": [
            {
                "question": "What do future filings show about operating cash flow coverage?",
                "reason": "This would clarify financing resilience.",
                "linked_unknown_or_risk": "Cash flow support",
            }
        ],
        "evidence_ids": ["ev_fy25_a", "ev_fy25_b", "ev_fy25_c", "ev_fy25_d"],
        "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
        "evidence_quality_notes": ["graham included with evidence grounding warnings: 4 issue(s)."],
        "synthesis_limits": ["Two-year history remains provisional."],
        "generated_at": "2026-07-13T00:00:00Z",
    }


def _write_committee_files(base_dir: Path, payload: dict, *, include_evidence_ids: bool = False) -> Path:
    panel_dir = base_dir / "companies" / "polymatech" / "company_memory" / "investor_panel"
    panel_dir.mkdir(parents=True, exist_ok=True)
    (panel_dir / "committee_synthesis.json").write_text(json.dumps(payload), encoding="utf-8")
    renderer = CommitteeBriefRenderer(company="polymatech", companies_root=base_dir / "companies")
    renderer.build(include_evidence_ids=include_evidence_ids)
    return panel_dir / "committee_brief.md"


def test_committee_brief_qa_passes_valid_brief(tmp_path):
    _write_committee_files(tmp_path, _committee_payload())
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result_path = gate.build()["committee_brief_qa.json"]
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert result["status"] == "pass"
    assert result["checks"]["required_sections"]["status"] == "pass"
    assert result["checks"]["forbidden_language"]["status"] == "pass"
    assert result["checks"]["evidence_id_visibility"]["status"] == "pass"
    assert result["checks"]["source_fidelity"]["status"] == "pass"


def test_committee_brief_qa_fails_missing_required_section(tmp_path):
    brief_path = _write_committee_files(tmp_path, _committee_payload())
    brief_path.write_text(brief_path.read_text(encoding="utf-8").replace("## Most Important Risks", ""), encoding="utf-8")
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert "## Most Important Risks" in result["checks"]["required_sections"]["missing_sections"]


def test_committee_brief_qa_fails_buy_language(tmp_path):
    brief_path = _write_committee_files(tmp_path, _committee_payload())
    brief_path.write_text(brief_path.read_text(encoding="utf-8") + "\nThis looks like a buy.\n", encoding="utf-8")
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert any("buy" in item.lower() for item in result["checks"]["forbidden_language"]["matches"])


def test_committee_brief_qa_fails_valuation_language(tmp_path):
    brief_path = _write_committee_files(tmp_path, _committee_payload())
    brief_path.write_text(brief_path.read_text(encoding="utf-8") + "\nIt looks undervalued.\n", encoding="utf-8")
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert "undervalued" in [item.lower() for item in result["checks"]["forbidden_language"]["matches"]]


def test_committee_brief_qa_allows_corporate_action_language(tmp_path):
    brief_path = _write_committee_files(tmp_path, _committee_payload())
    brief_path.write_text(
        brief_path.read_text(encoding="utf-8") + "\nThe company disclosed an offer-for-sale and QIP.\n",
        encoding="utf-8",
    )
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["checks"]["forbidden_language"]["status"] == "pass"


def test_committee_brief_qa_fails_evidence_ids_by_default(tmp_path):
    _write_committee_files(tmp_path, _committee_payload(), include_evidence_ids=True)
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert "ev_fy" in result["checks"]["evidence_id_visibility"]["matches"]


def test_committee_brief_qa_allows_evidence_ids_when_flag_true(tmp_path):
    _write_committee_files(tmp_path, _committee_payload(), include_evidence_ids=True)
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build(include_evidence_ids=True)["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["checks"]["evidence_id_visibility"]["status"] == "pass"


def test_committee_brief_qa_fails_unknown_analyst_name(tmp_path):
    brief_path = _write_committee_files(tmp_path, _committee_payload())
    brief_path.write_text(brief_path.read_text(encoding="utf-8").replace("Graham", "Porter", 1), encoding="utf-8")
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert "Porter" in result["checks"]["analyst_names"]["unknown_names"]


def test_committee_brief_qa_catches_missing_agreement_theme(tmp_path):
    brief_path = _write_committee_files(tmp_path, _committee_payload())
    brief_path.write_text(brief_path.read_text(encoding="utf-8").replace("### Capital-intensive manufacturing", ""), encoding="utf-8")
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert any("areas_of_agreement.theme" in item for item in result["checks"]["source_fidelity"]["missing_items"])


def test_committee_brief_qa_catches_missing_risk_severity(tmp_path):
    brief_path = _write_committee_files(tmp_path, _committee_payload())
    brief_path.write_text(brief_path.read_text(encoding="utf-8").replace("**Severity:** high", ""), encoding="utf-8")
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert any("most_important_risks.severity" in item for item in result["checks"]["source_fidelity"]["mismatched_items"])


def test_committee_brief_qa_catches_missing_investigation_question(tmp_path):
    brief_path = _write_committee_files(tmp_path, _committee_payload())
    brief_path.write_text(brief_path.read_text(encoding="utf-8").replace("What do future filings show about operating cash flow coverage?", ""), encoding="utf-8")
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert any("investigation_questions.question" in item for item in result["checks"]["source_fidelity"]["missing_items"])


def test_committee_brief_qa_preserves_synthesis_limits(tmp_path):
    _write_committee_files(tmp_path, _committee_payload())
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["checks"]["source_fidelity"]["status"] == "pass"
    assert result["status"] == "pass"


def test_pipeline_committee_brief_qa_stage_dispatch(monkeypatch):
    calls = []

    def fake_stage(company, context=None, include_evidence_ids=False):
        calls.append((company, context, include_evidence_ids))
        return {"committee_brief_qa.json": Path("committee_brief_qa.json")}

    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_qa_stage",
        fake_stage,
    )

    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(
        ["polymatech", "--stage", "committee_brief_qa", "--include-evidence-ids"]
    )

    if args.stage == "committee_brief_qa":
        run_company_pipeline.run_committee_brief_qa_stage(
            company=args.company,
            context=None,
            include_evidence_ids=args.include_evidence_ids,
        )

    assert calls == [("polymatech", None, True)]
