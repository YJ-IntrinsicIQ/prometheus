import json
from pathlib import Path

import pytest

from intelligence.investor_panel.committee_synthesizer import (
    InvestmentCommitteeSynthesizer,
)
from intelligence.investor_panel.committee_validator import (
    validate_committee_output,
)
from pipelines import run_company_pipeline


def _analysis_payload(
    doctrine_id: str,
    *,
    status: str = "pass",
    warnings=None,
    evidence_ids=None,
    uncertainties=None,
):
    if warnings is None:
        warnings = []
    if evidence_ids is None:
        evidence_ids = [f"ev_{doctrine_id}_1"]
    if uncertainties is None:
        uncertainties = [f"{doctrine_id} wants more cash flow evidence"]
    return {
        "doctrine_id": doctrine_id,
        "company": "polymatech",
        "pcim_version": "1.0",
        "pcim_source": "companies/polymatech/company_memory/pcim_v1.json",
        "analysis_mode": "llm_reasoning_v1",
        "sections_consumed": ["risk_inputs"],
        "assessment": {"summary": f"{doctrine_id} assessment"},
        "rating": "mixed",
        "key_findings": [f"{doctrine_id} sees a capex-heavy business"],
        "red_flags": [f"{doctrine_id} sees liquidity pressure"],
        "open_uncertainties": uncertainties,
        "evidence_ids": evidence_ids,
        "historical_context_used": True,
        "years_considered": ["fy24", "fy25"],
        "supporting_pcim_sections": ["risk_inputs"],
        "evidence_id_normalization": {
            "applied": False,
            "replacements": [],
            "unresolved_ids": [],
        },
        "evidence_grounding_status": status,
        "evidence_grounding_warnings": warnings,
        "reasoning_limits": [],
        "user_facing_brief": {
            "title": f"{doctrine_id.title()} School of Thought",
            "lens": "This lens focuses on the available evidence and known uncertainties.",
            "what_looks_good": ["The business has some visible strengths."],
            "what_needs_caution": ["There are material risks worth watching."],
            "what_is_missing": ["More evidence is needed on key unknowns."],
            "bottom_line": "The current evidence supports a cautious, incomplete view.",
        },
        "generated_at": "2026-07-12T00:00:00Z",
    }


def _write_analysis(base_dir: Path, analyst: str, payload: dict) -> None:
    panel_dir = base_dir / "companies" / "polymatech" / "company_memory" / "investor_panel"
    panel_dir.mkdir(parents=True, exist_ok=True)
    (panel_dir / f"{analyst}_analysis.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _write_pcim_with_evidence_ids(base_dir: Path, company: str, evidence_ids: list[str]) -> None:
    company_memory_dir = base_dir / "companies" / company / "company_memory"
    company_memory_dir.mkdir(parents=True, exist_ok=True)
    items = [
        {"value": f"evidence {idx}", "evidence_ids": [evidence_id]}
        for idx, evidence_id in enumerate(evidence_ids, start=1)
    ]
    payload = {
        "contract_version": "1.0",
        "company": company,
        "management_quality_inputs": {
            "management_focus_by_year": [
                {
                    "year": "fy24",
                    "items": items,
                }
            ]
        },
        "evidence_map": {},
    }
    (company_memory_dir / "pcim_v1.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _committee_response(*, include_normalization: bool = True, include_disagreement_type: bool = True) -> str:
    payload = {
            "company": "polymatech",
            "analysis_mode": "committee_synthesis_v1",
            "analysts_considered": ["graham", "buffett", "fisher"],
            "missing_analysts": ["lynch"],
            "excluded_analysts": ["munger"],
            "years_considered": ["fy24", "fy25"],
            "overall_committee_view": {
                "summary": "The committee sees growth ambition offset by financing and execution risk.",
                "confidence": "medium",
                "dominant_tension": "Growth ambition versus balance-sheet resilience.",
            },
            "areas_of_agreement": [
                {
                    "theme": "capex-heavy business",
                    "analysts": ["graham", "buffett"],
                    "summary": "Multiple analysts describe a capital-intensive operating model.",
                    "evidence_ids": ["ev_graham_1"],
                }
            ],
            "areas_of_disagreement": [
                {
                    "theme": "growth versus downside",
                    "analysts_positive_or_less_concerned": ["fisher"],
                    "analysts_cautious_or_negative": ["graham"],
                    "summary": "Growth-oriented analysts are more open to the expansion story.",
                    "why_it_matters": "This tension shapes how much execution risk the investor can tolerate.",
                    "evidence_ids": ["ev_fisher_1", "ev_graham_1"],
                }
            ],
            "strongest_positive_signals": [
                {
                    "signal": "Management ambition appears credible in parts of the evidence.",
                    "supported_by": ["fisher", "buffett"],
                    "summary": "Some analysts see execution signals that support the growth case.",
                    "evidence_ids": ["ev_fisher_1"],
                }
            ],
            "most_important_risks": [
                {
                    "risk": "Liquidity and funding pressure",
                    "raised_by": ["graham", "buffett"],
                    "summary": "Funding needs remain central to the downside case.",
                    "severity": "high",
                    "evidence_ids": ["ev_buffett_1"],
                }
            ],
            "critical_unknowns": [
                {
                    "unknown": "Cash flow evidence remains limited.",
                    "raised_by": ["graham", "buffett"],
                    "why_it_matters": "Without better cash-flow evidence, downside protection is harder to judge.",
                }
            ],
            "investigation_questions": [
                {
                    "question": "What do future filings show about operating cash flow and debt maturity coverage?",
                    "reason": "This would clarify the main financing unknown.",
                    "linked_unknown_or_risk": "Cash flow evidence remains limited.",
                }
            ],
            "evidence_ids": ["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
            "evidence_quality_notes": ["buffett included with evidence grounding warnings: 1 issue(s)."],
            "synthesis_limits": ["Only three analysts were available for this synthesis."],
            "generated_at": "2026-07-12T00:00:00Z",
        }
    if include_disagreement_type:
        payload["areas_of_disagreement"][0]["disagreement_type"] = "risk_weighting_difference"
    if include_normalization:
        payload["evidence_id_normalization"] = {
            "applied": False,
            "replacements": [],
            "unresolved_ids": [],
        }
    return json.dumps(payload)


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeLLM:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self.text)


def test_committee_synthesis_handles_missing_and_excluded_analysts(tmp_path, monkeypatch):
    _write_analysis(tmp_path, "graham", _analysis_payload("graham"))
    _write_analysis(
        tmp_path,
        "buffett",
        _analysis_payload(
            "buffett",
            status="warning",
            warnings=[{"issue": "metadata gap"}],
        ),
    )
    _write_analysis(tmp_path, "fisher", _analysis_payload("fisher"))
    _write_analysis(tmp_path, "munger", _analysis_payload("munger", status="fail"))

    fake_llm = _FakeLLM(_committee_response())
    monkeypatch.setattr(
        "intelligence.investor_panel.committee_synthesizer.get_llm",
        lambda: fake_llm,
    )

    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    output_path = synthesizer.run()
    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path.name == "committee_synthesis.json"
    assert saved["analysts_considered"] == ["graham", "buffett", "fisher"]
    assert saved["missing_analysts"] == ["lynch"]
    assert saved["excluded_analysts"] == ["munger"]
    assert "buffett included with evidence grounding warnings: 1 issue(s)." in saved["evidence_quality_notes"]
    assert saved["evidence_id_normalization"]["applied"] is False
    assert saved["areas_of_disagreement"][0]["disagreement_type"] == "risk_weighting_difference"
    assert "Missing analyst inputs: lynch." in saved["synthesis_limits"]
    assert "Excluded analyst inputs due to evidence grounding failure: munger." in saved["synthesis_limits"]
    assert fake_llm.calls[0]["system_prompt"].strip().startswith(
        "You are the Investment Committee Synthesizer for Prometheus."
    )
    assert "graham" in fake_llm.calls[0]["prompt"]
    assert "munger" in fake_llm.calls[0]["prompt"]


def test_committee_validator_rejects_forbidden_language():
    bad_payload = json.dumps(
        {
            "company": "polymatech",
            "analysis_mode": "committee_synthesis_v1",
            "analysts_considered": ["graham"],
            "missing_analysts": ["buffett", "fisher", "munger", "lynch"],
            "excluded_analysts": [],
            "years_considered": ["fy25"],
            "overall_committee_view": {
                "summary": "The committee would buy after more work.",
                "confidence": "low",
                "dominant_tension": "Growth versus risk.",
            },
            "areas_of_agreement": [],
            "areas_of_disagreement": [],
            "strongest_positive_signals": [],
            "most_important_risks": [],
            "critical_unknowns": [],
            "investigation_questions": [],
            "evidence_ids": ["ev_graham_1"],
            "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
            "evidence_quality_notes": [],
            "synthesis_limits": [],
            "generated_at": "2026-07-12T00:00:00Z",
        }
    )

    with pytest.raises(ValueError, match="forbidden language"):
        validate_committee_output(
            bad_payload,
            company="polymatech",
            included_analysts=["graham"],
            missing_analysts=["buffett", "fisher", "munger", "lynch"],
            excluded_analysts=[],
            allowed_evidence_ids=["ev_graham_1"],
            analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
            mode="final",
        )


def test_committee_validator_allows_offer_for_sale_language():
    payload = json.dumps(
        {
            "company": "polymatech",
            "analysis_mode": "committee_synthesis_v1",
            "analysts_considered": ["graham"],
            "missing_analysts": ["buffett", "fisher", "munger", "lynch"],
            "excluded_analysts": [],
            "years_considered": ["fy25"],
            "overall_committee_view": {
                "summary": "The committee noted the offer-for-sale and equity issuance without making a recommendation.",
                "confidence": "low",
                "dominant_tension": "Corporate actions versus business quality.",
            },
            "areas_of_agreement": [],
            "areas_of_disagreement": [],
            "strongest_positive_signals": [],
            "most_important_risks": [],
            "critical_unknowns": [],
            "investigation_questions": [],
            "evidence_ids": ["ev_graham_1"],
            "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
            "evidence_quality_notes": [],
            "synthesis_limits": [],
            "generated_at": "2026-07-12T00:00:00Z",
        }
    )

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham"],
        missing_analysts=["buffett", "fisher", "munger", "lynch"],
        excluded_analysts=[],
        allowed_evidence_ids=["ev_graham_1"],
        analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
        mode="final",
    )
    assert parsed["overall_committee_view"]["summary"].startswith("The committee noted the offer-for-sale")


def test_raw_committee_output_without_normalization_passes_raw_validation():
    payload = _committee_response(include_normalization=False, include_disagreement_type=False)
    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={
            "graham": ["Need more cash flow evidence."],
            "buffett": ["Need more cash flow evidence."],
            "fisher": ["Need more cash flow evidence."],
        },
        mode="raw",
    )
    assert "evidence_id_normalization" not in parsed


def test_raw_committee_output_without_normalization_fails_final_validation():
    payload = _committee_response(include_normalization=False, include_disagreement_type=False)
    with pytest.raises(ValueError, match="evidence_id_normalization"):
        validate_committee_output(
            payload,
            company="polymatech",
            included_analysts=["graham", "buffett", "fisher"],
            missing_analysts=["lynch"],
            excluded_analysts=["munger"],
            allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
            analyst_uncertainties={
                "graham": ["Need more cash flow evidence."],
                "buffett": ["Need more cash flow evidence."],
                "fisher": ["Need more cash flow evidence."],
            },
            mode="final",
        )


def test_pipeline_committee_synthesis_stage_dispatch(monkeypatch):
    calls = []

    def fake_stage(company, context=None, cleanup_only=False):
        calls.append((company, context, cleanup_only))
        return {"committee_synthesis.json": Path("committee_synthesis.json")}

    monkeypatch.setattr(
        run_company_pipeline,
        "run_committee_synthesis_stage",
        fake_stage,
    )

    parser = run_company_pipeline.build_parser()
    args = parser.parse_args(["polymatech", "--stage", "committee_synthesis"])

    if args.stage == "committee_synthesis":
        run_company_pipeline.run_committee_synthesis_stage(company=args.company, context=None)

    assert calls == [("polymatech", None, False)]


def test_committee_cleanup_canonicalizes_nested_ids_and_warning_counts(tmp_path, monkeypatch):
    _write_pcim_with_evidence_ids(
        tmp_path,
        "polymatech",
        ["ev_fy24_business_classification_json_business_dna_by_year_fy24_export"],
    )
    _write_analysis(
        tmp_path,
        "graham",
        _analysis_payload(
            "graham",
            status="warning",
            warnings=[{"issue": "a"}, {"issue": "b"}, {"issue": "c"}, {"issue": "d"}],
            evidence_ids=[
                "ev_fy24_business_classification_json_business_dna_by_year_fy24_export",
                "ev_graham_1",
            ],
        ),
    )
    _write_analysis(
        tmp_path,
        "buffett",
        _analysis_payload(
            "buffett",
            status="warning",
            warnings=[{"issue": "a"}, {"issue": "b"}, {"issue": "c"}],
            evidence_ids=["ev_fy25_business_classification_json_business_dna_by_year_fy25_manufacturing"],
        ),
    )
    _write_analysis(tmp_path, "fisher", _analysis_payload("fisher"))
    _write_analysis(
        tmp_path,
        "munger",
        _analysis_payload(
            "munger",
            status="warning",
            warnings=[{"issue": "a"}],
            evidence_ids=["ev_munger_1"],
        ),
    )
    _write_analysis(tmp_path, "lynch", _analysis_payload("lynch"))

    panel_dir = tmp_path / "companies" / "polymatech" / "company_memory" / "investor_panel"
    panel_dir.mkdir(parents=True, exist_ok=True)
    committee_payload = {
        "company": "polymatech",
        "analysis_mode": "committee_synthesis_v1",
        "analysts_considered": ["graham", "buffett", "fisher", "munger", "lynch"],
        "missing_analysts": [],
        "excluded_analysts": [],
        "years_considered": ["fy24", "fy25"],
        "overall_committee_view": {
            "summary": "Committee summary.",
            "confidence": "medium",
            "dominant_tension": "Growth versus downside.",
        },
        "areas_of_agreement": [
            {
                "theme": "export history",
                "analysts": ["graham"],
                "summary": "Export mattered historically.",
                "evidence_ids": ["ev_fy24_business_classification_export"],
            }
        ],
        "areas_of_disagreement": [
            {
                "theme": "Moat / durability of advantage",
                "analysts_positive_or_less_concerned": ["buffett"],
                "analysts_cautious_or_negative": ["graham", "munger", "lynch"],
                "summary": "Buffett accepts the business and others are cautious.",
                "why_it_matters": "Moat matters.",
                "evidence_ids": ["ev_fy25_business_classification_manufacturing"],
            }
        ],
        "strongest_positive_signals": [],
        "most_important_risks": [],
        "critical_unknowns": [
            {
                "unknown": "graham wants more cash flow evidence",
                "raised_by": ["graham"],
                "why_it_matters": "Needed.",
            }
        ],
        "investigation_questions": [
            {
                "question": "Question?",
                "reason": "Reason.",
                "linked_unknown_or_risk": "graham wants more cash flow evidence",
            }
        ],
        "evidence_ids": ["ev_fy24_business_classification_export"],
        "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
        "evidence_quality_notes": ["stale note"],
        "synthesis_limits": ["keep this"],
        "generated_at": "2026-07-12T00:00:00Z",
    }
    (panel_dir / "committee_synthesis.json").write_text(json.dumps(committee_payload), encoding="utf-8")

    monkeypatch.setattr(
        "intelligence.investor_panel.committee_synthesizer.get_llm",
        lambda: _FakeLLM(_committee_response()),
    )
    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    output_path = synthesizer.cleanup_existing()
    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert saved["evidence_ids"] == [
        "ev_fy24_business_classification_json_business_dna_by_year_fy24_export"
    ]
    assert saved["areas_of_agreement"][0]["evidence_ids"] == [
        "ev_fy24_business_classification_json_business_dna_by_year_fy24_export"
    ]
    assert saved["areas_of_disagreement"][0]["evidence_ids"] == [
        "ev_fy25_business_classification_json_business_dna_by_year_fy25_manufacturing"
    ]
    assert saved["evidence_id_normalization"]["applied"] is True
    assert saved["areas_of_disagreement"][0]["disagreement_type"] == "different_emphasis"
    assert saved["areas_of_disagreement"][0]["analysts_positive_or_less_concerned"] == []
    assert saved["areas_of_disagreement"][0]["analysts_with_business_quality_focus"] == ["buffett"]
    assert "moat durability as unproven" in saved["areas_of_disagreement"][0]["summary"].lower()
    assert saved["evidence_quality_notes"] == [
        "graham included with evidence grounding warnings: 4 issue(s).",
        "buffett included with evidence grounding warnings: 3 issue(s).",
        "munger included with evidence grounding warnings: 1 issue(s).",
    ]


def test_committee_cleanup_resolves_management_summary_alias_via_pcim_lookup(tmp_path, monkeypatch):
    _write_pcim_with_evidence_ids(
        tmp_path,
        "polymatech",
        ["ev_fy24_management_summary_json_init_00007"],
    )
    _write_analysis(
        tmp_path,
        "munger",
        _analysis_payload(
            "munger",
            status="warning",
            warnings=[{"issue": "a"}],
            evidence_ids=["ev_fy24_management_summary_init_00007"],
        ),
    )
    for analyst in ["graham", "buffett", "fisher", "lynch"]:
        _write_analysis(tmp_path, analyst, _analysis_payload(analyst))

    panel_dir = tmp_path / "companies" / "polymatech" / "company_memory" / "investor_panel"
    committee_payload = {
        "company": "polymatech",
        "analysis_mode": "committee_synthesis_v1",
        "analysts_considered": ["graham", "buffett", "fisher", "munger", "lynch"],
        "missing_analysts": [],
        "excluded_analysts": [],
        "years_considered": ["fy24"],
        "overall_committee_view": {
            "summary": "Summary.",
            "confidence": "low",
            "dominant_tension": "Tension.",
        },
        "areas_of_agreement": [],
        "areas_of_disagreement": [],
        "strongest_positive_signals": [],
        "most_important_risks": [
            {
                "risk": "Management signal",
                "raised_by": ["munger"],
                "summary": "Summary.",
                "severity": "uncertain",
                "evidence_ids": ["ev_fy24_management_summary_init_00007"],
            }
        ],
        "critical_unknowns": [
            {
                "unknown": "munger wants more cash flow evidence",
                "raised_by": ["munger"],
                "why_it_matters": "Needed.",
            }
        ],
        "investigation_questions": [
            {
                "question": "Question?",
                "reason": "Reason.",
                "linked_unknown_or_risk": "munger wants more cash flow evidence",
            }
        ],
        "evidence_ids": ["ev_fy24_management_summary_init_00007"],
        "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
        "evidence_quality_notes": [],
        "synthesis_limits": [],
        "generated_at": "2026-07-12T00:00:00Z",
    }
    (panel_dir / "committee_synthesis.json").write_text(json.dumps(committee_payload), encoding="utf-8")

    monkeypatch.setattr(
        "intelligence.investor_panel.committee_synthesizer.get_llm",
        lambda: _FakeLLM(_committee_response()),
    )
    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    saved = json.loads(synthesizer.cleanup_existing().read_text(encoding="utf-8"))

    assert saved["evidence_ids"] == ["ev_fy24_management_summary_json_init_00007"]
    assert saved["most_important_risks"][0]["evidence_ids"] == [
        "ev_fy24_management_summary_json_init_00007"
    ]
    assert saved["evidence_id_normalization"]["applied"] is True
    assert saved["evidence_id_normalization"]["replacements"] == [
        {
            "original_id": "ev_fy24_management_summary_init_00007",
            "canonical_id": "ev_fy24_management_summary_json_init_00007",
        }
    ]
    assert saved["evidence_id_normalization"]["unresolved_ids"] == []


def test_committee_cleanup_fails_when_unresolved_management_summary_alias_remains(tmp_path, monkeypatch):
    _write_pcim_with_evidence_ids(tmp_path, "polymatech", [])
    _write_analysis(
        tmp_path,
        "munger",
        _analysis_payload(
            "munger",
            status="warning",
            warnings=[{"issue": "a"}],
            evidence_ids=["ev_fy24_management_summary_init_00007"],
        ),
    )
    for analyst in ["graham", "buffett", "fisher", "lynch"]:
        _write_analysis(tmp_path, analyst, _analysis_payload(analyst))

    panel_dir = tmp_path / "companies" / "polymatech" / "company_memory" / "investor_panel"
    committee_payload = {
        "company": "polymatech",
        "analysis_mode": "committee_synthesis_v1",
        "analysts_considered": ["graham", "buffett", "fisher", "munger", "lynch"],
        "missing_analysts": [],
        "excluded_analysts": [],
        "years_considered": ["fy24"],
        "overall_committee_view": {
            "summary": "Summary.",
            "confidence": "low",
            "dominant_tension": "Tension.",
        },
        "areas_of_agreement": [],
        "areas_of_disagreement": [],
        "strongest_positive_signals": [],
        "most_important_risks": [],
        "critical_unknowns": [
            {
                "unknown": "munger wants more cash flow evidence",
                "raised_by": ["munger"],
                "why_it_matters": "Needed.",
            }
        ],
        "investigation_questions": [
            {
                "question": "Question?",
                "reason": "Reason.",
                "linked_unknown_or_risk": "munger wants more cash flow evidence",
            }
        ],
        "evidence_ids": ["ev_fy24_management_summary_init_00007"],
        "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
        "evidence_quality_notes": [],
        "synthesis_limits": [],
        "generated_at": "2026-07-12T00:00:00Z",
    }
    (panel_dir / "committee_synthesis.json").write_text(json.dumps(committee_payload), encoding="utf-8")

    monkeypatch.setattr(
        "intelligence.investor_panel.committee_synthesizer.get_llm",
        lambda: _FakeLLM(_committee_response()),
    )
    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    with pytest.raises(ValueError, match="unresolved_ids must be empty"):
        synthesizer.cleanup_existing()


def test_committee_validator_rejects_unresolved_committee_alias():
    payload = json.dumps(
        {
            "company": "polymatech",
            "analysis_mode": "committee_synthesis_v1",
            "analysts_considered": ["graham"],
            "missing_analysts": ["buffett", "fisher", "munger", "lynch"],
            "excluded_analysts": [],
            "years_considered": ["fy24"],
            "overall_committee_view": {
                "summary": "Summary only.",
                "confidence": "low",
                "dominant_tension": "Tension.",
            },
            "areas_of_agreement": [],
            "areas_of_disagreement": [
                {
                    "theme": "theme",
                    "analysts_positive_or_less_concerned": [],
                    "analysts_cautious_or_negative": ["graham"],
                    "disagreement_type": "different_emphasis",
                    "summary": "summary",
                    "why_it_matters": "matters",
                    "evidence_ids": ["ev_fy24_business_classification_export"],
                }
            ],
            "strongest_positive_signals": [],
            "most_important_risks": [],
            "critical_unknowns": [
                {
                    "unknown": "Need more cash flow evidence",
                    "raised_by": ["graham"],
                    "why_it_matters": "matters",
                }
            ],
            "investigation_questions": [
                {
                    "question": "Question?",
                    "reason": "Reason.",
                    "linked_unknown_or_risk": "Need more cash flow evidence",
                }
            ],
            "evidence_ids": ["ev_fy24_business_classification_export"],
            "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
            "evidence_quality_notes": [],
            "synthesis_limits": [],
            "generated_at": "2026-07-12T00:00:00Z",
        }
    )
    with pytest.raises(ValueError, match="unresolved evidence_ids"):
        validate_committee_output(
            payload,
            company="polymatech",
            included_analysts=["graham"],
            missing_analysts=["buffett", "fisher", "munger", "lynch"],
            excluded_analysts=[],
            allowed_evidence_ids=["ev_graham_1"],
            analyst_uncertainties={"graham": ["Need more cash flow evidence"]},
            mode="final",
        )


def test_committee_synthesizer_adds_normalization_before_final_validation(tmp_path, monkeypatch):
    _write_analysis(tmp_path, "graham", _analysis_payload("graham"))
    _write_analysis(
        tmp_path,
        "buffett",
        _analysis_payload("buffett", status="warning", warnings=[{"issue": "metadata gap"}]),
    )
    _write_analysis(tmp_path, "fisher", _analysis_payload("fisher"))
    _write_analysis(tmp_path, "munger", _analysis_payload("munger", status="fail"))

    fake_llm = _FakeLLM(_committee_response(include_normalization=False, include_disagreement_type=False))
    monkeypatch.setattr(
        "intelligence.investor_panel.committee_synthesizer.get_llm",
        lambda: fake_llm,
    )

    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    output_path = synthesizer.run()
    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert "evidence_id_normalization" in saved
    assert "unresolved_ids" in saved["evidence_id_normalization"]
    assert "disagreement_type" in saved["areas_of_disagreement"][0]
