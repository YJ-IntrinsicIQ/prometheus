import json
from pathlib import Path

import pytest

from intelligence.investor_panel.committee_brief_renderer import (
    CommitteeBriefRenderer,
    build_canonical_committee_brief_view,
    finalize_committee_brief_for_user,
    finalize_committee_brief_quality,
    validate_brief_view,
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


def _committee_payload_v2():
    payload = _committee_payload()
    payload.update(
        {
            "company": "acme",
            "analysis_mode": "committee_synthesis_v2",
            "company_slug": "acme",
            "committee_view": "mixed",
            "committee_direction": "strengthening",
            "consensus_strength": "medium",
            "committee_summary": "The committee sees operating progress improving, but cash conversion and return evidence still limit conviction.",
            "strongest_shared_convictions": [
                {
                    "conclusion": "Operating delivery is visible.",
                    "supporting_analysts": ["Buffett", "Fisher"],
                    "supporting_evidence": "Execution evidence across the latest period.",
                    "progression": "Delivery moved from planned to operational.",
                    "why_it_matters": "This shows the business is still moving forward.",
                    "confidence": "high",
                }
            ],
            "major_disagreements": [
                {
                    "topic": "Capital returns",
                    "analysts_on_side_a": ["Buffett", "Fisher"],
                    "side_a_view": "Return evidence is starting to appear.",
                    "analysts_on_side_b": ["Graham", "Munger"],
                    "side_b_view": "Deployment is visible, but returns are still unproven.",
                    "reason_for_disagreement": "The panel is weighting later payoff differently.",
                    "evidence_causing_tension": "Capital deployment is present, but later evidence is limited.",
                    "what_evidence_would_resolve_it": "Later periods would need to show durable per-share improvement.",
                    "investor_importance": "This changes conviction around capital allocation.",
                    "confidence": "medium",
                    "disagreement_type": "execution_vs_outcome_tension",
                }
            ],
            "thesis_strengtheners": [
                {
                    "summary": "Delivery moved from announced to operational.",
                    "period": "fy26",
                    "source_streams": ["projects"],
                    "supporting_analysts": ["Buffett", "Fisher"],
                    "why_it_matters": "This is the clearest operational progression.",
                    "conviction_effect": "strengthened",
                    "confidence": "high",
                },
                {
                    "summary": "Capacity now looks more visible.",
                    "period": "fy26",
                    "source_streams": ["capacity evolution"],
                    "supporting_analysts": ["Fisher", "Lynch"],
                    "why_it_matters": "It shows execution is still unfolding.",
                    "conviction_effect": "strengthened",
                    "confidence": "medium",
                },
            ],
            "thesis_weakeners": [
                {
                    "summary": "Cash conversion remains difficult.",
                    "period": "fy26",
                    "source_streams": ["financial memory"],
                    "supporting_analysts": ["Graham", "Munger"],
                    "why_it_matters": "This limits confidence in the quality of growth.",
                    "conviction_effect": "weakened",
                    "confidence": "medium",
                },
                {
                    "summary": "Capital returns are still not proven.",
                    "period": "fy26",
                    "source_streams": ["capital allocation outcomes"],
                    "supporting_analysts": ["Graham", "Munger"],
                    "why_it_matters": "Deployment is not the same as payoff.",
                    "conviction_effect": "weakened",
                    "confidence": "medium",
                },
            ],
            "unresolved_items": [
                {
                    "question": "Will the newer operating evidence turn into durable cash generation?",
                    "why_it_matters": "This is central to the conviction call.",
                    "affected_analysts": ["Graham", "Buffett"],
                    "affected_thesis_area": ["financial memory"],
                    "evidence_needed": "Later periods need to show durable conversion.",
                    "current_confidence": "low",
                },
                {
                    "question": "Do capital deployments produce per-share improvement?",
                    "why_it_matters": "Return evidence remains incomplete.",
                    "affected_analysts": ["Graham", "Munger"],
                    "affected_thesis_area": ["capital allocation outcomes"],
                    "evidence_needed": "Later periods need to show payoff, not just spend.",
                    "current_confidence": "low",
                },
            ],
            "major_turning_points": [
                {
                    "period": "fy26",
                    "event": "Delivery moved from announced to operational.",
                    "before": "planned",
                    "after": "operational",
                    "why_it_matters": "This is the clearest turning point.",
                    "affected_analysts": ["Buffett", "Fisher"],
                    "conviction_effect": "strengthened",
                    "confidence": "high",
                },
                {
                    "period": "fy26",
                    "event": "Capital deployment is visible, but returns are still unproven.",
                    "before": "deployment",
                    "after": "return proof pending",
                    "why_it_matters": "Execution is not yet the same as economic success.",
                    "affected_analysts": ["Graham", "Munger"],
                    "conviction_effect": "unchanged",
                    "confidence": "medium",
                },
            ],
            "financial_judgment": {
                "assessment": "Financial quality is improving, but cash conversion and basis clarity still constrain conviction.",
                "direction": "stable",
                "strongest_evidence": "Positive operating cash-flow evidence is visible.",
                "main_concern": "Cash conversion remains uneven.",
                "unresolved_issue": "Whether the newer operating evidence becomes durable.",
                "confidence": "medium",
            },
            "management_judgment": {
                "assessment": "Management follow-through is improving, but the record still needs more time.",
                "direction": "strengthening",
                "strongest_evidence": "Delivery moved from planned to operational.",
                "main_concern": "Later evidence still needs to match the stated direction.",
                "unresolved_issue": "Whether follow-through keeps matching the stated plan.",
                "confidence": "high",
            },
            "capital_allocation_judgment": {
                "assessment": "Capital allocation is visible, but outcome evidence is still incomplete.",
                "direction": "unclear",
                "strongest_evidence": "New deployment is visible in the latest period.",
                "main_concern": "Deployment is not the same as payoff.",
                "unresolved_issue": "Whether deployed capital improves per-share economics.",
                "confidence": "medium",
            },
            "risk_judgment": {
                "assessment": "Risk remains part of the thesis rather than a footnote.",
                "direction": "stable",
                "strongest_evidence": "Working-capital intensity remains visible.",
                "main_concern": "The core risk remains unresolved.",
                "unresolved_issue": "Whether the next periods reduce cash-strain risk.",
                "confidence": "medium",
            },
            "evidence_confidence": {
                "level": "medium",
                "basis": ["progression evidence preserved", "disagreement preserved", "unresolved items preserved"],
                "limitations": ["Later evidence is still needed to prove durable returns."],
            },
            "what_would_change_the_view": [
                "Later evidence shows durable cash generation.",
                "Later evidence shows capital deployment improving per-share economics.",
            ],
            "top_diligence_questions": [
                {
                    "rank": 1,
                    "question": "Will newer operating evidence turn into durable cash generation?",
                    "why_it_matters": "This is the main unresolved question.",
                    "evidence_needed": "Later periods need to show durable conversion.",
                },
                {
                    "rank": 2,
                    "question": "Do capital deployments produce per-share improvement?",
                    "why_it_matters": "Deployment is not the same as payoff.",
                    "evidence_needed": "Later periods need to show payoff, not just spend.",
                },
            ],
        }
    )
    return payload


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
    assert "**Missing / Incomplete Inputs:**" in output
    assert "How much weight to put on growth momentum versus funding pressure." in output
    assert "ev_1" not in output
    assert "## Evidence References" not in output


def test_committee_brief_v2_renders_concise_sections(tmp_path):
    _write_committee_synthesis(tmp_path, _committee_payload_v2())
    renderer = CommitteeBriefRenderer(company="acme", companies_root=tmp_path / "companies")
    output = renderer.build()["committee_brief.md"].read_text(encoding="utf-8")

    assert "## Bottom Line" in output
    assert "## What Changed" in output
    assert "## What Strengthened" in output
    assert "## What Weakened" in output
    assert "## Major Disagreement" in output
    assert "## Management View" in output
    assert "## Capital Allocation View" in output
    assert "## What Remains Unproven" in output
    assert "## Top Questions to Investigate" in output
    assert "buy" not in output.lower()
    assert "target price" not in output.lower()
    assert "pcim" not in output.lower()


def test_committee_brief_v2_builds_progression_view(tmp_path):
    _write_committee_synthesis(tmp_path, _committee_payload_v2())
    renderer = CommitteeBriefRenderer(company="acme", companies_root=tmp_path / "companies")
    output = renderer.build()["committee_brief.md"].read_text(encoding="utf-8")

    assert "planned" in output.lower()
    assert "operational" in output.lower()
    assert "deployment is not the same as payoff" in output.lower()
    assert "later evidence shows durable cash generation" in output.lower()


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


def test_committee_brief_quality_finalizer_rewrites_internal_financial_phrases():
    payload = _committee_payload()
    payload["financial_committee_view"]["financial_interpretation_limits"] = [
        "fcf: derived value used",
        "critical financial fields include unknown basis entries",
        "diluted shares missing",
    ]
    payload["financial_committee_view"]["investor_questions_from_financials"] = [
        "What explains capex timing for owner-earnings assessment readiness"
    ]

    finalized = finalize_committee_brief_quality(payload)

    missing = finalized["financial_committee_view"]["missing_financial_data"]
    assert "Standalone versus consolidated basis remains unclear, limiting comparability." in missing
    assert "Weighted-average and diluted share-count evidence is incomplete, limiting per-share analysis." in missing
    assert finalized["financial_committee_view"]["investor_questions_from_financials"][0].endswith("?")


def test_committee_brief_quality_finalizer_redacts_invalid_evidence_id_diagnostics():
    payload = _committee_payload()
    payload["evidence_quality_notes"] = [
        "graham was excluded because final analyst evidence IDs are invalid: "
        "[{'path': '$.evidence_ids', 'invalid_id': 'ev_unknown', "
        "'reason': 'unknown_evidence_id'}]."
    ]

    finalized = finalize_committee_brief_quality(payload)

    assert finalized["evidence_quality_notes"] == [
        "Graham was excluded because cited source references could not be verified."
    ]
    validate_committee_brief_source(finalized)


def test_committee_brief_finalizer_rewrites_stale_fcf_contradiction():
    payload = _committee_payload()
    payload["financial_committee_view"]["financial_interpretation_limits"] = [
        "FCF-based conclusions cannot be assessed"
    ]

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])

    joined = " ".join(finalized["financial_committee_view"]["financial_strengths"]).lower()
    assert "fcf-based conclusions cannot be assessed" not in joined
    assert "derived fcf / owner-earnings estimate is available" in joined


def test_committee_brief_finalizer_cleans_active_synthesis_fields():
    payload = _committee_payload()
    payload["overall_committee_view"]["summary"] = "Free cash flow and capex data are not provided."
    payload["synthesis_narrative"] = [
        "FCF-based conclusions cannot be assessed.",
        "Owner earnings cannot be assessed.",
    ]
    payload["what_to_watch_next"] = [
        "Capex data are not provided",
    ]

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])

    assert "not provided" not in finalized["overall_committee_view"]["summary"].lower()
    assert all("cannot be assessed" not in item.lower() for item in finalized["synthesis_narrative"])
    assert all("capex data are not provided" not in item.lower() for item in finalized["what_to_watch_next"])


def test_committee_brief_finalizer_rewrites_stale_capex_contradiction():
    payload = _committee_payload()
    payload["financial_committee_view"]["missing_financial_data"] = [
        "capex data are not provided"
    ]

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])

    joined = " ".join(finalized["financial_committee_view"]["missing_financial_data"]).lower()
    assert "capex data are not provided" not in joined
    assert "maintenance versus growth capex split is unavailable" in joined


def test_committee_brief_finalizer_rewrites_missing_data_default_when_precision_gaps_exist():
    payload = _committee_payload()
    payload["financial_committee_view"]["missing_financial_data"] = []
    payload["committee_financial_truth"]["basis_unknown"] = True
    payload["committee_financial_truth"]["weighted_avg_shares_missing"] = True
    payload["committee_financial_truth"]["multi_year_bridge_history_incomplete"] = True

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])

    missing = finalized["financial_committee_view"]["missing_financial_data"]
    assert "Standalone versus consolidated basis remains unclear, limiting comparability." in missing
    assert "Weighted-average and diluted share-count evidence is incomplete, limiting per-share analysis." in missing
    assert "Multi-year CFO/capex bridge history remains incomplete." in missing


def test_build_canonical_brief_view_replaces_raw_stale_risk():
    payload = _committee_payload()
    payload["most_important_risks"] = [
        {
            "risk": "Missing free cash flow support",
            "raised_by": ["graham"],
            "summary": "Free cash flow and capex data are not provided; owner-earnings and FCF-based conclusions cannot be assessed.",
            "severity": "high",
            "evidence_ids": ["ev_9"],
        }
    ]

    brief_view = build_canonical_committee_brief_view(payload, payload["committee_financial_truth"])

    summary = brief_view["most_important_risks"][0]["summary"].lower()
    assert "free cash flow and capex data are not provided" not in summary
    assert "precision is limited" in summary


def test_build_canonical_brief_view_does_not_leak_raw_broken_signal_to_markdown(tmp_path):
    payload = _committee_payload()
    payload["strongest_positive_signals"] = [
        {
            "signal": "Current owner-earnings / conservative FCF estimate is present (≈₹98.",
            "supported_by": ["buffett"],
            "summary": "Current owner-earnings / conservative FCF estimate is present (≈₹98.",
            "evidence_ids": ["ev_3"],
        }
    ]
    _write_committee_synthesis(tmp_path, payload)

    renderer = CommitteeBriefRenderer(company="polymatech", companies_root=tmp_path / "companies")
    output = renderer.build()["committee_brief.md"].read_text(encoding="utf-8")

    assert "≈₹98." not in output
    assert "## Strongest Positive Signals" in output


def test_build_canonical_brief_view_replaces_not_appends_duplicate_signals():
    payload = _committee_payload()
    payload["strongest_positive_signals"] = [
        {
            "signal": "Owner earnings estimate in-…",
            "supported_by": ["buffett"],
            "summary": "Owner earnings estimate in-…",
            "evidence_ids": ["ev_3"],
        },
        {
            "signal": "Derived owner-earnings estimate",
            "supported_by": ["buffett"],
            "summary": "Derived FCF / owner-earnings estimate is available for the current usable year, but precision is limited because maintenance-versus-growth capex split and multi-year bridge history are incomplete.",
            "evidence_ids": ["ev_3"],
        },
    ]

    brief_view = build_canonical_committee_brief_view(payload, payload["committee_financial_truth"])

    assert len(brief_view["strongest_positive_signals"]) == 1
    assert "in-…" not in brief_view["strongest_positive_signals"][0]["signal"]


def test_validate_brief_view_rejects_empty_supported_by():
    payload = _committee_payload()
    brief_view = build_canonical_committee_brief_view(payload, payload["committee_financial_truth"])
    brief_view["strongest_positive_signals"] = [
        {
            "signal": "Clean signal",
            "summary": "Clean summary.",
            "supported_by": [],
            "evidence_ids": [],
        }
    ]

    with pytest.raises(ValueError, match="empty supported_by"):
        validate_brief_view(brief_view, payload["committee_financial_truth"])


def test_validate_brief_view_rejects_ellipsis_and_incomplete_currency():
    payload = _committee_payload()
    brief_view = build_canonical_committee_brief_view(payload, payload["committee_financial_truth"])
    brief_view["committee_view"]["summary"] = "This is broken..."

    with pytest.raises(ValueError, match="ellipsis truncation"):
        validate_brief_view(brief_view, payload["committee_financial_truth"])

    brief_view = build_canonical_committee_brief_view(payload, payload["committee_financial_truth"])
    brief_view["committee_view"]["summary"] = "Derived value is about ₹98."
    with pytest.raises(ValueError, match="incomplete currency fragment"):
        validate_brief_view(brief_view, payload["committee_financial_truth"])


def test_validate_brief_view_rejects_semantic_truncation_without_ellipsis():
    payload = _committee_payload()
    brief_view = build_canonical_committee_brief_view(payload, payload["committee_financial_truth"])
    brief_view["strongest_positive_signals"][0]["signal"] = "advantages that can act as barriers to"

    with pytest.raises(ValueError, match="semantically truncated fragment"):
        validate_brief_view(brief_view, payload["committee_financial_truth"])


def test_committee_brief_finalizer_repairs_incomplete_currency_fragment():
    payload = _committee_payload()
    payload["financial_committee_view"]["financial_strengths"] = [
        "Current owner-earnings / conservative FCF estimate is present (≈₹98."
    ]

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])

    strengths = finalized["financial_committee_view"]["financial_strengths"]
    assert strengths
    assert all("≈₹98." not in item for item in strengths)
    assert any("derived fcf / owner-earnings estimate is available" in item.lower() for item in strengths)


def test_committee_brief_finalizer_moves_business_only_strength_out_of_financial_strengths():
    payload = _committee_payload()
    payload["financial_committee_view"]["financial_strengths"] = [
        "The business model and certification profile support the operating story."
    ]

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])

    assert all(
        "business model" not in item.lower()
        for item in finalized["financial_committee_view"]["financial_strengths"]
    )
    assert finalized["strongest_positive_signals"]


def test_committee_brief_finalizer_canonicalizes_positive_signal_heading():
    payload = _committee_payload()
    payload["strongest_positive_signals"] = [
        {
            "signal": "The business is described as an aerospace and defence electronics manufacturer with design, qualification, and manufacturing capabilities.",
            "supported_by": ["buffett", "fisher"],
            "summary": "The business is described as an aerospace and defence electronics manufacturer with design, qualification, and manufacturing capabilities.",
            "evidence_ids": ["ev_3"],
        }
    ]

    brief_view = build_canonical_committee_brief_view(payload, payload["committee_financial_truth"])

    assert brief_view["strongest_positive_signals"][0]["signal"] == "B2G/B2B aerospace and defence manufacturing model"
    assert "design, qualification, and manufacturing capabilities" in brief_view["strongest_positive_signals"][0]["summary"]


def test_committee_brief_finalizer_enriches_financial_strengths_when_truth_available():
    payload = _committee_payload()
    payload["committee_financial_truth"].update(
        {
            "payables_available": True,
            "working_capital_metrics_available": True,
            "owner_earnings_estimate_available": True,
        }
    )

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])
    strengths = finalized["financial_committee_view"]["financial_strengths"]

    assert len(strengths) >= 3
    assert any("working-capital metrics are available" in item.lower() for item in strengths)
    assert any("owner-earnings" in item.lower() for item in strengths)


def test_committee_brief_finalizer_does_not_render_basis_unknown_as_strength():
    payload = _committee_payload()
    payload["financial_committee_view"]["financial_strengths"] = [
        "Standalone/consolidated basis is unclear; financial comparability remains limited.",
        "Revenue, PAT, and EPS are all directionally supportive.",
    ]
    payload["committee_financial_truth"]["basis_unknown"] = True

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])

    assert all("basis" not in item.lower() for item in finalized["financial_committee_view"]["financial_strengths"])
    assert "Standalone versus consolidated basis remains unclear, limiting comparability." in finalized["financial_committee_view"]["missing_financial_data"]


def test_committee_brief_finalizer_dedupes_duplicate_derived_fcf_lines():
    payload = _committee_payload()
    payload["financial_committee_view"]["financial_strengths"] = [
        "Derived owner-earnings / conservative FCF estimate is available for the current usable year, but precision is limited.",
        "Derived FCF / owner-earnings estimate is available for the current usable year, but precision is limited because maintenance-versus-growth capex split and multi-year bridge history are incomplete.",
    ]

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])
    strengths = finalized["financial_committee_view"]["financial_strengths"]

    assert strengths.count(
        "Derived FCF / owner-earnings estimate is available for the current usable year, but precision is limited because maintenance-versus-growth capex split and multi-year bridge history are incomplete."
    ) == 1


def test_committee_brief_finalizer_dedupes_basis_and_share_count_variants():
    payload = _committee_payload()
    payload["financial_committee_view"]["missing_financial_data"] = [
        "Standalone/consolidated basis is unclear; financial comparability remains limited.",
        "Standalone versus consolidated basis remains unclear.",
        "Share-count evidence is incomplete; per-share analysis remains limited.",
        "Weighted-average and diluted share-count evidence is incomplete, limiting per-share analysis.",
    ]
    payload["committee_financial_truth"]["basis_unknown"] = True
    payload["committee_financial_truth"]["weighted_avg_shares_missing"] = True
    payload["committee_financial_truth"]["diluted_shares_missing"] = True

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])
    missing = finalized["financial_committee_view"]["missing_financial_data"]

    assert missing.count("Standalone versus consolidated basis remains unclear, limiting comparability.") == 1
    assert missing.count("Weighted-average and diluted share-count evidence is incomplete, limiting per-share analysis.") == 1


def test_committee_brief_finalizer_mentions_working_capital_risk_in_committee_view():
    payload = _committee_payload()
    payload["committee_financial_truth"]["working_capital_risk"] = True
    payload["committee_financial_truth"]["owner_earnings_status"] = "available_derived_precision_limited"

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])

    assert "working-capital" in finalized["overall_committee_view"]["summary"].lower()


def test_committee_brief_finalizer_strengthens_dominant_tension_for_working_capital():
    payload = _committee_payload()
    payload["committee_financial_truth"]["working_capital_risk"] = True
    payload["committee_financial_truth"]["owner_earnings_status"] = "available_derived_precision_limited"

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])
    tension = finalized["overall_committee_view"]["dominant_tension"].lower()

    assert "working-capital" in tension
    assert "profitability" in tension or "cash-generation" in tension


def test_build_canonical_brief_view_lists_specific_missing_incomplete_inputs():
    payload = _committee_payload()
    payload["financial_committee_view"]["missing_financial_data"] = []
    payload["committee_financial_truth"].update(
        {
            "basis_unknown": True,
            "weighted_avg_shares_missing": True,
            "diluted_shares_missing": True,
            "maintenance_growth_split_missing": True,
            "multi_year_bridge_history_incomplete": True,
        }
    )

    brief_view = build_canonical_committee_brief_view(payload, payload["committee_financial_truth"])
    missing = brief_view["financial_view"]["missing_financial_data"]

    assert "Standalone versus consolidated basis remains unclear, limiting comparability." in missing
    assert "Weighted-average and diluted share-count evidence is incomplete, limiting per-share analysis." in missing
    assert "Maintenance versus growth capex split is unavailable." in missing
    assert "Multi-year CFO/capex bridge history remains incomplete." in missing
    assert all("no material missing financial data" not in item.lower() for item in missing)


def test_committee_brief_finalizer_dedupes_fcf_unknowns_and_generates_real_questions():
    payload = _committee_payload()
    payload["critical_unknowns"] = [
        {
            "unknown": "fcf derived, not explicitly disclosed.",
            "raised_by": ["graham"],
            "why_it_matters": "fcf derived, not explicitly disclosed.",
        },
        {
            "unknown": "FCF is derived rather than explicitly reported, so treat it as an estimate.",
            "raised_by": ["buffett"],
            "why_it_matters": "Owner earnings depend on the estimate.",
        },
    ]
    payload["investigation_questions"] = [
        {
            "question": "",
            "reason": "fcf derived, not explicitly disclosed.",
            "linked_unknown_or_risk": "fcf derived, not explicitly disclosed.",
        }
    ]

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])

    assert len(finalized["critical_unknowns"]) == 1
    assert finalized["investigation_questions"][0]["question"].endswith("?")
    assert "derived fcf estimate" in finalized["investigation_questions"][0]["question"].lower()


def test_committee_brief_renders_no_material_disagreement_message_when_empty(tmp_path):
    payload = _committee_payload()
    payload["areas_of_disagreement"] = []
    _write_committee_synthesis(tmp_path, payload)

    renderer = CommitteeBriefRenderer(company="polymatech", companies_root=tmp_path / "companies")
    output = renderer.build()["committee_brief.md"].read_text(encoding="utf-8")

    assert "## Where the Analysts Differ" in output
    assert "No material disagreement was recorded." in output


def test_committee_brief_quality_finalizer_generates_nonblank_question_body():
    payload = _committee_payload()
    payload["investigation_questions"] = [
        {
            "question": "",
            "reason": "Diluted share-count data is missing, limiting per-share analysis.",
            "linked_unknown_or_risk": "Diluted share-count data is missing, limiting per-share analysis.",
        }
    ]

    finalized = finalize_committee_brief_for_user(payload, payload["committee_financial_truth"])

    assert finalized["investigation_questions"][0]["question"]
    assert finalized["investigation_questions"][0]["question"].endswith("?")


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
