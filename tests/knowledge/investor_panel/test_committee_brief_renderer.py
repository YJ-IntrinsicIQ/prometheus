import json
from pathlib import Path

import pytest

from intelligence.investor_panel.committee_brief_renderer import (
    CommitteeBriefRenderer,
    validate_committee_brief_source,
)
from pipelines import run_company_pipeline


def _write_committee_synthesis(base_dir: Path, payload: dict) -> Path:
    panel_dir = base_dir / "companies" / "polymatech" / "company_memory" / "investor_panel"
    panel_dir.mkdir(parents=True, exist_ok=True)
    path = panel_dir / "committee_synthesis.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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
        "financial_committee_view": {
            "financials_used": True,
            "basis_used": "consolidated",
            "financial_consensus": [
                "Revenue, PAT, and cash-conversion evidence support the business, but leverage still needs scrutiny."
            ],
            "financial_strengths": ["Revenue, PAT, and EPS are all directionally supportive."],
            "financial_concerns": ["Debt and funding pressure remain important constraints."],
            "financial_disagreements": [
                {
                    "topic": "cash conversion",
                    "analysts": ["graham", "fisher"],
                    "disagreement": "How much weight to put on growth momentum versus funding pressure.",
                    "financial_relevance": "That weighting shapes how durable the expansion story looks.",
                    "evidence_limit": "Cash-flow durability still needs more evidence.",
                    "disagreement_type": "risk_weighting_difference",
                }
            ],
            "missing_financial_data": ["Share-count comparability remains limited."],
            "financial_red_flags": ["Debt and funding pressure remain important constraints."],
            "financial_interpretation_limits": [
                "No new ratios were calculated beyond supplied financial inputs."
            ],
            "investor_questions_from_financials": [
                "How sustainable are CFO and FCF as expansion continues?"
            ],
        },
        "areas_of_agreement": [
            {
                "theme": "Capital-intensive manufacturing",
                "analysts": ["graham", "buffett", "fisher", "munger", "lynch"],
                "summary": "All analysts describe a capital-intensive manufacturing buildout.",
                "evidence_ids": ["ev_1"],
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
                "evidence_ids": ["ev_2"],
            }
        ],
        "strongest_positive_signals": [
            {
                "signal": "Visible capacity expansion",
                "supported_by": ["buffett", "fisher"],
                "summary": "The company has visible project momentum and expansion signals.",
                "evidence_ids": ["ev_3"],
            }
        ],
        "most_important_risks": [
            {
                "risk": "Liquidity pressure",
                "raised_by": ["graham", "munger"],
                "summary": "Liquidity pressure remains a meaningful risk.",
                "severity": "high",
                "evidence_ids": ["ev_4"],
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
        "evidence_ids": ["ev_1", "ev_2", "ev_3", "ev_4"],
        "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
        "evidence_quality_notes": [
            "graham included with evidence grounding warnings: 4 issue(s)."
        ],
        "synthesis_limits": [
            "Two-year history remains provisional."
        ],
        "generated_at": "2026-07-13T00:00:00Z",
    }


def test_committee_brief_renders_markdown_without_evidence_ids_by_default(tmp_path):
    _write_committee_synthesis(tmp_path, _committee_payload())
    renderer = CommitteeBriefRenderer(company="polymatech", companies_root=tmp_path / "companies")
    written = renderer.build()
    output = written["committee_brief.md"].read_text(encoding="utf-8")

    assert "# Investment Committee Brief — Polymatech" in output
    assert "## Committee View" in output
    assert "## Financial View" in output
    assert "## Where the Analysts Agree" in output
    assert "## Where the Analysts Differ" in output
    assert "## Most Important Risks" in output
    assert "## Critical Unknowns" in output
    assert "## Investigation Questions" in output
    assert "## Synthesis Limits" in output
    assert "**Basis Used:** consolidated" in output
    assert "**Financial Strengths:**" in output
    assert "How much weight to put on growth momentum versus funding pressure." in output
    assert "ev_1" not in output
    assert "## Evidence References" not in output


def test_committee_brief_validator_accepts_normalized_financial_disagreements_shape():
    payload = _committee_payload()
    payload["financial_committee_view"]["financial_disagreements"] = [
        {
            "topic": "cash conversion",
            "analysts": ["graham", "fisher"],
            "disagreement": "Some analysts trust margin progress more than cash conversion.",
            "financial_relevance": "This affects confidence in profit-to-cash conversion.",
            "evidence_limit": "FCF/capex data is missing.",
        }
    ]

    validated = validate_committee_brief_source(payload)
    assert validated["financial_committee_view"]["financial_disagreements"][0]["topic"] == "cash conversion"


def test_committee_brief_includes_evidence_ids_when_requested(tmp_path):
    _write_committee_synthesis(tmp_path, _committee_payload())
    renderer = CommitteeBriefRenderer(company="polymatech", companies_root=tmp_path / "companies")
    written = renderer.build(include_evidence_ids=True)
    output = written["committee_brief.md"].read_text(encoding="utf-8")

    assert "## Evidence References" in output
    assert "- ev_1" in output
    assert "- ev_4" in output


def test_committee_brief_handles_missing_optional_evidence_notes(tmp_path):
    payload = _committee_payload()
    payload["evidence_quality_notes"] = []
    _write_committee_synthesis(tmp_path, payload)
    renderer = CommitteeBriefRenderer(company="polymatech", companies_root=tmp_path / "companies")
    output = renderer.build()["committee_brief.md"].read_text(encoding="utf-8")

    assert "No material evidence-quality warnings were recorded." in output


def test_committee_brief_validator_rejects_forbidden_language():
    payload = _committee_payload()
    payload["overall_committee_view"]["summary"] = "The committee would buy after more diligence."
    with pytest.raises(ValueError, match="forbidden recommendation language"):
        validate_committee_brief_source(payload)


def test_committee_brief_validator_rejects_internal_terms_in_financial_view():
    payload = _committee_payload()
    payload["financial_committee_view"]["financial_consensus"] = [
        "PCIM shows revenue growth but missing leverage detail."
    ]
    with pytest.raises(ValueError, match="forbidden internal term"):
        validate_committee_brief_source(payload)


def test_committee_brief_validator_allows_offer_for_sale_language():
    payload = _committee_payload()
    payload["overall_committee_view"]["summary"] = "The committee reviewed the offer-for-sale and QIP disclosures."
    validated = validate_committee_brief_source(payload)
    assert validated["overall_committee_view"]["summary"].startswith("The committee reviewed the offer-for-sale")


def test_committee_brief_validator_rejects_source_chunk():
    payload = _committee_payload()
    payload["areas_of_agreement"][0]["source_chunk"] = "raw excerpt"
    with pytest.raises(ValueError, match="source_chunk"):
        validate_committee_brief_source(payload)


def test_committee_brief_validator_rejects_forbidden_internal_fields():
    payload = _committee_payload()
    payload["grounding_status"] = "warning"
    with pytest.raises(ValueError, match="forbidden internal fields"):
        validate_committee_brief_source(payload)


def test_pipeline_committee_brief_stage_dispatch(monkeypatch):
    calls = []

    def fake_stage(company, context=None, include_evidence_ids=False):
        calls.append((company, context, include_evidence_ids))
        return {"committee_brief.md": Path("committee_brief.md")}

    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_brief_stage",
        fake_stage,
    )

    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(
        ["polymatech", "--stage", "committee_brief", "--include-evidence-ids"]
    )

    if args.stage == "committee_brief":
        run_company_pipeline.run_committee_brief_stage(
            company=args.company,
            context=None,
            include_evidence_ids=args.include_evidence_ids,
        )

    assert calls == [("polymatech", None, True)]
