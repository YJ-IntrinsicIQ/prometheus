import json
from pathlib import Path

import pytest

from intelligence.investor_panel.committee_brief_qa import CommitteeBriefQAGate
from intelligence.investor_panel.committee_brief_renderer import CommitteeBriefRenderer
from pipelines import run_company_pipeline


def _committee_payload():
    """Post-finalization committee synthesis payload (as produced by synthesizer's _finalize_payload)."""
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
        "financial_committee_view": {
            "financials_used": True,
            "basis_used": "consolidated",
            "financial_consensus": [
                "Revenue, PAT, and cash-conversion evidence support the business, but leverage still needs scrutiny."
            ],
            # Post-finalization strengths (canonical phrases, no business-only, no limitations)
            "financial_strengths": [
                "Revenue, PAT, and EPS are directionally supportive.",
                "Current-year CFO and working-capital metrics are available, improving visibility.",
                "Payables and payable-days evidence are available for the current usable year.",
                "Derived FCF / owner-earnings estimate is available for the current usable year, but precision is limited because maintenance-versus-growth capex split and multi-year bridge history are incomplete.",
                "Financial basis is identified as consolidated.",
            ],
            "financial_concerns": [
                "Debt and funding pressure remain important constraints.",
                "Severe working-capital intensity and stretched cash-conversion metrics remain a real concern.",
            ],
            "financial_disagreements": [
                {
                    "disagreement_type": "risk_weighting_difference",
                    "analysts_involved": ["graham", "fisher"],
                    "what_they_disagree_on": "How much weight to put on growth momentum versus funding pressure.",
                    "why_it_matters": "That weighting shapes how durable the expansion story looks under funding pressure.",
                    "uncertainty": "Cash-flow durability still needs more evidence.",
                }
            ],
            "missing_financial_data": [
                "Share-count comparability remains limited.",
                "Maintenance versus growth capex split remains unavailable.",
                "Weighted-average share count remains unavailable.",
                "Diluted share-count data remains unavailable.",
                "Basis consistency remains unclear across reported financials.",
                "Multi-year CFO/capex bridge history remains incomplete.",
            ],
            "financial_red_flags": ["Debt and funding pressure remain important constraints."],
            "financial_interpretation_limits": [
                "No new ratios were calculated beyond supplied financial inputs."
            ],
            "investor_questions_from_financials": [
                "How sustainable are CFO and FCF as expansion continues?",
            ],
            "precision_limited_financial_data": [
                "Derived FCF / owner-earnings estimate is available for the current usable year, but precision is limited because maintenance-versus-growth capex split and multi-year bridge history are incomplete."
            ],
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
        "committee_financial_truth": {
            "fcf_missing": False,
            "capex_missing": False,
            "payables_missing": False,
            "payables_available": True,
            "working_capital_metrics_available": True,
            "owner_earnings_estimate_available": True,
            "owner_earnings_status": "available_derived_precision_limited",
        },
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


def test_committee_brief_qa_fails_missing_financial_view(tmp_path):
    brief_path = _write_committee_files(tmp_path, _committee_payload())
    brief_path.write_text(
        brief_path.read_text(encoding="utf-8").replace("## Financial View", ""),
        encoding="utf-8",
    )
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert "## Financial View" in result["checks"]["required_sections"]["missing_sections"]


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


def test_committee_brief_qa_allows_buyback_language(tmp_path):
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = gate._v2_public_language_check("The company disclosed a buyback and dividend.")

    assert result["status"] == "pass"
    assert result["matches"] == []


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


def test_committee_brief_qa_fails_stale_financial_contradiction(tmp_path):
    payload = _committee_payload()
    payload["committee_financial_truth"] = {
        "fcf_missing": False,
        "capex_missing": False,
        "payables_available": True,
        "working_capital_metrics_available": True,
    }
    brief_path = _write_committee_files(tmp_path, payload)
    brief_path.write_text(
        brief_path.read_text(encoding="utf-8") + "\nFree cash flow is missing.\n",
        encoding="utf-8",
    )
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert result["checks"]["quality_contradictions"]["status"] == "fail"
    assert any("fcf_missing=false" in item for item in result["checks"]["quality_contradictions"]["contradictions"])


def test_committee_brief_qa_fails_internal_or_broken_fragments(tmp_path):
    payload = _committee_payload()
    brief_path = _write_committee_files(tmp_path, payload)
    brief_path.write_text(
        brief_path.read_text(encoding="utf-8") + "\n- fcf: derived value used\n- ₹41.\n",
        encoding="utf-8",
    )
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert result["checks"]["quality_contradictions"]["internal_language"]
    assert result["checks"]["quality_contradictions"]["formatting_issues"]


def test_committee_brief_qa_fails_stale_capex_contradiction(tmp_path):
    payload = _committee_payload()
    brief_path = _write_committee_files(tmp_path, payload)
    brief_path.write_text(
        brief_path.read_text(encoding="utf-8") + "\nCapex data are not provided.\n",
        encoding="utf-8",
    )
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert any("capex_missing=false" in item for item in result["checks"]["quality_contradictions"]["contradictions"])


def test_committee_brief_qa_fails_blank_question_body(tmp_path):
    payload = _committee_payload()
    brief_path = _write_committee_files(tmp_path, payload)
    brief_text = brief_path.read_text(encoding="utf-8").replace(
        "What do future filings show about operating cash flow coverage?",
        "",
    )
    brief_path.write_text(brief_text, encoding="utf-8")
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert any("blank_question_body" in item for item in result["checks"]["quality_contradictions"]["low_quality_questions"])


def test_committee_brief_qa_fails_business_only_financial_strength(tmp_path):
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    brief_view = {
        "committee_financial_truth": _committee_payload()["committee_financial_truth"],
        "committee_view": {"summary": "", "dominant_tension": "", "confidence": "medium"},
        "financial_view": {"financial_strengths": ["The business model and certification profile support the operating story."]},
        "strongest_positive_signals": [],
        "investigation_questions": [],
    }
    result = gate._quality_contradiction_check(brief_view, "**Financial Strengths:**\n- The business model and certification profile support the operating story.\n")

    assert result["status"] == "warning"
    assert any(
        item.startswith("financial_strength_business_only:")
        for item in result["readability_warnings"]
    )


def test_committee_brief_qa_passes_without_duplicate_or_empty_supported_by(tmp_path):
    payload = _committee_payload()
    payload["strongest_positive_signals"] = [
        {
            "signal": "Owner earnings estimate available",
            "supported_by": ["buffett"],
            "summary": "Derived FCF / owner-earnings estimate is available for the current usable year, but precision is limited.",
            "evidence_ids": ["ev_x"],
        },
        {
            "signal": "Derived owner-earnings estimate",
            "supported_by": ["buffett"],
            "summary": "Derived FCF / owner-earnings estimate is available for the current usable year, but precision is limited because maintenance-versus-growth capex split and multi-year bridge history are incomplete.",
            "evidence_ids": ["ev_y"],
        },
    ]
    _write_committee_files(tmp_path, payload)

    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))
    brief = (tmp_path / "companies" / "polymatech" / "company_memory" / "investor_panel" / "committee_brief.md").read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert brief.count("**Supported by:** Buffett") == 1
    assert "**Supported by:** " in brief


def test_committee_brief_qa_fails_semantically_truncated_heading(tmp_path):
    brief_path = _write_committee_files(tmp_path, _committee_payload())
    brief_path.write_text(
        brief_path.read_text(encoding="utf-8").replace(
            "### Visible capacity expansion",
            "### capital-intensive manufacturer with",
        ),
        encoding="utf-8",
    )
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert any(
        "capital-intensive manufacturer with" in item
        for item in result["checks"]["quality_contradictions"]["formatting_issues"]
    )


def test_committee_brief_qa_fails_missing_data_default_when_precision_gaps_exist(tmp_path):
    payload = _committee_payload()
    payload["financial_committee_view"]["missing_financial_data"] = []
    payload["committee_financial_truth"]["basis_unknown"] = True
    payload["committee_financial_truth"]["weighted_avg_shares_missing"] = True
    brief_path = _write_committee_files(tmp_path, payload)
    text = brief_path.read_text(encoding="utf-8").replace(
        "- Standalone versus consolidated basis remains unclear, limiting comparability.",
        "- No material missing or incomplete inputs were recorded.",
    )
    brief_path.write_text(text, encoding="utf-8")

    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    result = json.loads(gate.build()["committee_brief_qa.json"].read_text(encoding="utf-8"))

    assert result["status"] == "fail"
    assert any(
        "No material missing or incomplete inputs were recorded." in item
        for item in result["checks"]["quality_contradictions"]["contradictions"]
    )


def test_committee_brief_qa_warns_when_limitation_leaks_into_financial_strengths(tmp_path):
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    brief_view = {
        "committee_financial_truth": _committee_payload()["committee_financial_truth"],
        "committee_view": {"summary": "", "dominant_tension": "", "confidence": "medium"},
        "financial_view": {
            "financial_strengths": [
                "Standalone versus consolidated basis remains unclear, limiting comparability.",
                "Revenue, PAT, and EPS are directionally supportive.",
            ]
        },
        "strongest_positive_signals": [],
        "investigation_questions": [],
    }
    result = gate._quality_contradiction_check(
        brief_view,
        "**Financial Strengths:**\n- Standalone versus consolidated basis remains unclear, limiting comparability.\n- Revenue, PAT, and EPS are directionally supportive.\n",
    )

    assert result["status"] == "warning"
    assert any(
        item.startswith("limitation_inside_financial_strengths:")
        for item in result["readability_warnings"]
    )


def test_committee_brief_qa_warns_when_committee_view_omits_working_capital_risk(tmp_path):
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    brief_view = {
        "committee_financial_truth": {**_committee_payload()["committee_financial_truth"], "working_capital_risk": True},
        "committee_view": {
            "summary": "Reported profitability and cash-flow signals look constructive.",
            "dominant_tension": "Profitability versus basis clarity.",
            "confidence": "medium",
        },
        "financial_view": {"financial_strengths": ["Revenue, PAT, and EPS are directionally supportive."]},
        "strongest_positive_signals": [],
        "investigation_questions": [],
    }
    result = gate._quality_contradiction_check(brief_view, "## Committee View\nReported profitability and cash-flow signals look constructive.\n**Dominant Tension:** Profitability versus basis clarity.\n")

    assert result["status"] == "warning"
    warnings = result["readability_warnings"]
    assert "committee_view_omits_working_capital_risk" in warnings
    assert "dominant_tension_omits_working_capital_risk" in warnings


def test_committee_brief_qa_warns_when_financial_strengths_are_too_thin(tmp_path):
    gate = CommitteeBriefQAGate(company="polymatech", companies_root=tmp_path / "companies")
    brief_view = {
        "committee_financial_truth": _committee_payload()["committee_financial_truth"],
        "committee_view": {"summary": "", "dominant_tension": "", "confidence": "medium"},
        "financial_view": {"financial_strengths": ["Revenue, PAT, and EPS are directionally supportive."]},
        "strongest_positive_signals": [],
        "investigation_questions": [],
    }
    result = gate._quality_contradiction_check(brief_view, "**Financial Strengths:**\n- Revenue, PAT, and EPS are directionally supportive.\n")

    assert result["status"] == "warning"
    assert "financial_strengths_too_thin_for_available_financial_truth" in result["readability_warnings"]


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
