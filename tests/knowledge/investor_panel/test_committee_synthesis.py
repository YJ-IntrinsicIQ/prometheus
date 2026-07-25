import json
from pathlib import Path
from typing import Any

import pytest

from knowledge.ai.input_packs import estimate_tokens
from intelligence.investor_panel.committee_synthesizer import (
    InvestmentCommitteeSynthesizer,
    build_committee_synthesis_skeleton,
)
from intelligence.investor_panel.committee_brief_renderer import (
    validate_committee_brief_source,
)
from intelligence.investor_panel.committee_validator import (
    COMMITTEE_FIELD_CONTRACTS,
    _classify_owner_earnings_reference,
    normalize_known_analyst_reference,
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
        "financial_metrics_used": ["revenue", "pat", "cfo", "fcf", "roe", "roce", "debt", "eps"],
        "financial_red_flags": ["Debt still weighs on balance-sheet resilience."],
        "financial_positive_signals": ["Cash conversion is better than PAT in the available evidence."],
        "financial_missing_data": ["Share-count comparability is still limited."],
        "financial_interpretation_limits": [
            "No new ratios were calculated beyond supplied financial inputs."
        ],
        "financial_assessment": {
            "financials_used": True,
            "basis_used": "consolidated",
            "key_financial_strengths": ["Revenue and PAT are moving in the right direction."],
            "key_financial_concerns": ["Debt and funding pressure remain important constraints."],
            "financial_red_flags": ["Debt still weighs on balance-sheet resilience."],
            "missing_financial_data": ["Share-count comparability is still limited."],
            "financial_interpretation_limits": [
                "No new ratios were calculated beyond supplied financial inputs."
            ],
            "financial_warnings_carried_forward": [
                "Share-count comparability is still limited."
            ],
        },
        "financial_sections_consumed": [
            "financial_trend_inputs",
            "cash_conversion_inputs",
            "balance_sheet_strength_inputs",
        ],
        "financial_warnings_carried_forward": [
            "Share-count comparability is still limited."
        ],
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
    clean_payload = dict(payload)
    diagnostics_payload = {
        "doctrine_id": analyst,
        "evidence_id_normalization": clean_payload.pop(
            "evidence_id_normalization",
            {"applied": False, "replacements": [], "unresolved_ids": []},
        ),
        "evidence_grounding_warnings": clean_payload.pop("evidence_grounding_warnings", []),
        "schema_warnings": clean_payload.pop("schema_warnings", []),
        "evidence_routing_diagnostics": clean_payload.pop("evidence_routing_diagnostics", {}),
    }
    (panel_dir / f"{analyst}_analysis.json").write_text(
        json.dumps(clean_payload),
        encoding="utf-8",
    )
    (panel_dir / f"{analyst}_analysis_diagnostics.json").write_text(
        json.dumps(diagnostics_payload),
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
            "financial_committee_view": _financial_committee_view(),
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


def _committee_payload_dict() -> dict:
    return json.loads(_committee_response())


def _financial_committee_view() -> dict:
    return {
        "financials_used": True,
        "basis_used": "consolidated",
        "financial_consensus": [
            "Revenue, PAT, and cash-conversion evidence point to a real operating base, but debt still matters."
        ],
        "financial_strengths": [
            "Revenue and PAT are moving in the right direction."
        ],
        "financial_concerns": [
            "Debt and funding pressure remain important constraints."
        ],
        "financial_disagreements": [
            {
                "disagreement_type": "risk_weighting_difference",
                "analysts_involved": ["graham", "fisher"],
                "what_they_disagree_on": "How much weight to put on growth momentum versus financing pressure.",
                "why_it_matters": "That weighting changes whether current progress looks durable enough for downside-tolerant investors.",
                "uncertainty": "Cash-conversion durability and capex funding still need more evidence.",
            }
        ],
        "missing_financial_data": ["Share-count comparability is still limited."],
        "financial_red_flags": [
            "Debt and funding pressure remain important constraints."
        ],
        "financial_interpretation_limits": [
            "No new ratios were calculated beyond supplied financial inputs."
        ],
        "investor_questions_from_financials": [
            "How sustainable are CFO and FCF as debt obligations continue?"
        ],
    }


def test_build_sanitized_committee_analyst_input_prefers_nested_financial_warnings():
    from intelligence.investor_panel.committee_synthesizer import build_sanitized_committee_analyst_input

    payload = _analysis_payload("graham")
    payload["financial_warnings_carried_forward"] = ["Top-level noisy warning"]
    payload["financial_assessment"]["financial_warnings_carried_forward"] = [
        "Nested canonical warning",
        "nested canonical warning",
    ]
    payload["evidence_ids"] = ["risk_inputs", "ev_graham_1"]

    sanitized = build_sanitized_committee_analyst_input(payload)

    assert sanitized["financial_assessment"]["financial_warnings_carried_forward"] == [
        "Nested canonical warning"
    ]
    assert any("section names" in item for item in sanitized["schema_warnings"])


def test_committee_validator_normalizes_string_financial_consensus():
    payload = _committee_payload_dict()
    payload["financial_committee_view"]["financial_consensus"] = (
        "Revenue and PAT evidence is directionally supportive."
    )

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["financial_committee_view"]["financial_consensus"] == [
        "Revenue and PAT evidence is directionally supportive."
    ]
    assert any(
        "financial_committee_view.financial_consensus was normalized from string to list"
        in item
        for item in parsed["schema_warnings"]
    )


def test_committee_synthesizer_ignores_llm_owned_financial_consensus_objects(tmp_path, monkeypatch):
    _write_analysis(tmp_path, "graham", _analysis_payload("graham"))
    _write_analysis(tmp_path, "buffett", _analysis_payload("buffett"))
    _write_analysis(tmp_path, "fisher", _analysis_payload("fisher"))

    response_payload = json.loads(_committee_response())
    response_payload["financial_committee_view"]["financial_consensus"] = [
        {
            "point": "Cash conversion is below PAT quality.",
            "supporting_analysts": ["graham", "munger"],
        }
    ]
    fake_llm = _FakeLLM(json.dumps(response_payload))
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
    assert saved["financial_committee_view"]["financial_consensus"] == []
    assert "executive_committee_summary" in saved


def test_committee_synthesizer_preserves_deterministic_financial_lists_despite_nested_llm_objects(tmp_path, monkeypatch):
    _write_analysis(tmp_path, "graham", _analysis_payload("graham"))
    _write_analysis(tmp_path, "buffett", _analysis_payload("buffett"))
    _write_analysis(tmp_path, "fisher", _analysis_payload("fisher"))

    response_payload = json.loads(_committee_response())
    response_payload["financial_committee_view"]["financial_consensus"] = [
        {
            "summary": {"text": "Cash conversion is below PAT quality."},
            "supporting_analysts": ["graham", "munger"],
        }
    ]
    response_payload["financial_committee_view"]["financial_concerns"] = [
        {"concern": "Debt still constrains flexibility.", "source_analysts": ["graham"]}
    ]
    fake_llm = _FakeLLM(json.dumps(response_payload))
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
    assert all(isinstance(item, str) for item in saved["financial_committee_view"]["financial_consensus"])
    assert all(isinstance(item, str) for item in saved["financial_committee_view"]["financial_concerns"])
    assert saved["financial_committee_view"]["financial_consensus"] == []


def test_committee_synthesizer_writes_deterministic_financial_lists_when_llm_objects_are_unsupported(tmp_path, monkeypatch):
    _write_analysis(tmp_path, "graham", _analysis_payload("graham"))
    _write_analysis(tmp_path, "buffett", _analysis_payload("buffett"))
    _write_analysis(tmp_path, "fisher", _analysis_payload("fisher"))

    response_payload = json.loads(_committee_response())
    response_payload["financial_committee_view"]["financial_consensus"] = [
        {"unsupported": {"deep": {"deeper": {"deepest": object()}}}}
    ]
    response_payload["financial_committee_view"]["financial_consensus"][0] = {
        "unsupported": {"deep": {"deeper": {"deepest": None}}},
        "empty": [],
    }
    fake_llm = _FakeLLM(json.dumps(response_payload))
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
    assert saved["financial_committee_view"]["financial_consensus"] == []


def test_build_committee_synthesis_skeleton_is_deterministic():
    analyst_artifacts = [
        _analysis_payload("graham"),
        _analysis_payload("buffett"),
        _analysis_payload("fisher"),
    ]
    uncertainty_registry = [
        {
            "uncertainty_id": "graham_u001",
            "analyst": "graham",
            "category": "financials",
            "text": "Cash-flow evidence remains limited.",
            "source_path": "graham_analysis.json#open_uncertainties",
        },
        {
            "uncertainty_id": "buffett_u001",
            "analyst": "buffett",
            "category": "financials",
            "text": "Free cash flow cannot be assessed cleanly.",
            "source_path": "buffett_analysis.json#financial_interpretation_limits",
        },
    ]

    skeleton = build_committee_synthesis_skeleton(
        "polymatech",
        analyst_artifacts,
        {},
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        uncertainty_registry=uncertainty_registry,
        financial_warning_manifest={
            "fcf_missing": True,
            "capex_missing": True,
            "basis_unknown": False,
        },
    )

    assert skeleton["company"] == "polymatech"
    assert skeleton["analysis_mode"] == "committee_synthesis_v1"
    assert skeleton["analysts_considered"] == ["graham", "buffett", "fisher"]
    assert skeleton["missing_analysts"] == ["lynch"]
    assert skeleton["excluded_analysts"] == ["munger"]
    assert skeleton["financial_warning_manifest"]["fcf_missing"] is True
    assert skeleton["critical_unknowns"]
    assert all(
        item["grounding_status"] == "registry_grounded"
        for item in skeleton["critical_unknowns"]
    )


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("buffett (registry)", ["buffett"]),
        ("Warren Buffett", ["buffett"]),
        ("munger / buffett", ["munger", "buffett"]),
        ("graham, buffett", ["graham", "buffett"]),
    ],
)
def test_normalize_known_analyst_reference_variants(raw_value, expected):
    normalized, repairs = normalize_known_analyst_reference(
        raw_value,
        field="critical_unknowns[0].raised_by",
    )

    assert normalized == expected
    assert repairs


def test_normalize_known_analyst_reference_removes_unknown_values():
    normalized, repairs = normalize_known_analyst_reference(
        "porter / buffett",
        field="critical_unknowns[0].raised_by",
        remove_unknown=True,
    )

    assert normalized == ["buffett"]
    assert any(repair["reason"] == "unknown_analyst_reference_removed" for repair in repairs)


def test_committee_synthesizer_grounds_critical_unknowns_from_registry_not_llm_raised_by_variants(tmp_path, monkeypatch):
    _write_analysis(tmp_path, "graham", _analysis_payload("graham"))
    _write_analysis(tmp_path, "buffett", _analysis_payload("buffett"))
    _write_analysis(tmp_path, "fisher", _analysis_payload("fisher"))

    response_payload = json.loads(_committee_response())
    response_payload["critical_unknowns"][0]["raised_by"] = "buffett (registry)"
    fake_llm = _FakeLLM(json.dumps(response_payload))
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
    assert set(saved["critical_unknowns"][0]["raised_by"]).issubset({"graham", "buffett", "fisher"})
    assert saved["critical_unknowns"][0]["source_uncertainty_ids"]
    assert saved["critical_unknowns"][0]["evidence_limit"] == "Grounded in analyst uncertainty registry."


def test_committee_synthesizer_ignores_unknown_llm_raised_by_when_registry_grounds_critical_unknowns(tmp_path, monkeypatch):
    _write_analysis(tmp_path, "graham", _analysis_payload("graham"))
    _write_analysis(tmp_path, "buffett", _analysis_payload("buffett"))
    _write_analysis(tmp_path, "fisher", _analysis_payload("fisher"))

    response_payload = json.loads(_committee_response())
    response_payload["critical_unknowns"][0]["raised_by"] = "porter / buffett"
    fake_llm = _FakeLLM(json.dumps(response_payload))
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
    assert set(saved["critical_unknowns"][0]["raised_by"]).issubset({"graham", "buffett", "fisher"})
    diagnostics = json.loads(
        (output_path.parent / "committee_synthesis_diagnostics.json").read_text(encoding="utf-8")
    )
    assert diagnostics.get("ungrounded_suggested_unknowns", []) == []


def test_committee_validator_rejects_forbidden_prompt_content_in_list_field():
    payload = _committee_payload_dict()
    payload["financial_committee_view"]["financial_consensus"] = [
        "input_pack says revenue is strong"
    ]

    with pytest.raises(ValueError, match="forbidden internal or prompt content"):
        validate_committee_output(
            payload,
            company="polymatech",
            included_analysts=["graham", "buffett", "fisher"],
            missing_analysts=["lynch"],
            excluded_analysts=["munger"],
            allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
            analyst_uncertainties={},
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
            allow_unresolved_ids=True,
        )


def test_committee_validator_normalizes_financial_disagreements_string():
    payload = _committee_payload_dict()
    payload["financial_committee_view"]["financial_disagreements"] = (
        "Analysts disagree on cash conversion durability."
    )

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["financial_committee_view"]["financial_disagreements"] == [
        {
            "topic": "unspecified",
            "analysts": [],
            "disagreement": "Analysts disagree on cash conversion durability.",
            "financial_relevance": "",
            "evidence_limit": "",
        }
    ]


def test_committee_validator_normalizes_financial_disagreements_dict():
    payload = _committee_payload_dict()
    payload["financial_committee_view"]["financial_disagreements"] = {
        "topic": "cash conversion",
        "analysts": "graham",
        "disagreement": "Some analysts trust margin progress more than cash conversion.",
        "financial_relevance": "This affects confidence in profit-to-cash conversion.",
        "evidence_limit": "FCF/capex data is missing.",
    }

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["financial_committee_view"]["financial_disagreements"][0]["topic"] == "cash conversion"
    assert parsed["financial_committee_view"]["financial_disagreements"][0]["analysts"] == ["graham"]


def test_committee_validator_normalizes_financial_disagreements_null_to_empty_list():
    payload = _committee_payload_dict()
    payload["financial_committee_view"]["financial_disagreements"] = None

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["financial_committee_view"]["financial_disagreements"] == []


def test_committee_validator_rejects_invalid_financial_disagreement_analyst():
    payload = _committee_payload_dict()
    payload["financial_committee_view"]["financial_disagreements"] = [
        {
            "topic": "cash conversion",
            "analysts": ["porter"],
            "disagreement": "Analysts disagree on cash conversion.",
            "financial_relevance": "This affects confidence in profit-to-cash conversion.",
            "evidence_limit": "",
        }
    ]

    with pytest.raises(ValueError, match="invalid analysts"):
        validate_committee_output(
            payload,
            company="polymatech",
            included_analysts=["graham", "buffett", "fisher"],
            missing_analysts=["lynch"],
            excluded_analysts=["munger"],
            allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
            analyst_uncertainties={},
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
            allow_unresolved_ids=True,
        )


def test_committee_validator_rejects_raw_field_in_financial_disagreement():
    payload = _committee_payload_dict()
    payload["financial_committee_view"]["financial_disagreements"] = [
        {
            "topic": "cash conversion",
            "analysts": ["graham"],
            "disagreement": "Analysts disagree on cash conversion.",
            "financial_relevance": "This affects confidence in profit-to-cash conversion.",
            "evidence_limit": "",
            "source_chunk": "raw excerpt",
        }
    ]

    with pytest.raises(ValueError, match="forbidden internal fields|forbidden internal or raw payload content"):
        validate_committee_output(
            payload,
            company="polymatech",
            included_analysts=["graham", "buffett", "fisher"],
            missing_analysts=["lynch"],
            excluded_analysts=["munger"],
            allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
            analyst_uncertainties={},
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
            allow_unresolved_ids=True,
        )


def test_committee_validator_normalizes_area_of_agreement_string():
    payload = _committee_payload_dict()
    payload["areas_of_agreement"] = ["Analysts agree that cash-flow evidence remains limited."]

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["areas_of_agreement"] == [
        {
            "theme": "unspecified",
            "summary": "Analysts agree that cash-flow evidence remains limited.",
            "evidence_ids": [],
            "source_analysts": [],
            "evidence_limit": (
                "No direct evidence ID supplied by committee output; agreement is grounded in analyst summaries."
            ),
        }
    ]


def test_committee_validator_normalizes_area_of_agreement_alias_dict_and_analyst_string():
    payload = _committee_payload_dict()
    payload["areas_of_agreement"] = [
        {
            "topic": "cash conversion",
            "agreement": "Graham and Buffett both want better cash-flow evidence.",
            "evidence": ["ev_graham_1"],
            "analysts": "Graham, Buffett",
        }
    ]

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["areas_of_agreement"][0]["theme"] == "cash conversion"
    assert parsed["areas_of_agreement"][0]["summary"] == (
        "Graham and Buffett both want better cash-flow evidence."
    )
    assert parsed["areas_of_agreement"][0]["evidence_ids"] == ["ev_graham_1"]
    assert parsed["areas_of_agreement"][0]["source_analysts"] == ["graham", "buffett"]


def test_committee_validator_fills_agreement_theme_and_evidence_ids_when_missing():
    payload = _committee_payload_dict()
    payload["areas_of_agreement"] = [
        {
            "summary": "Analysts agree that funding pressure remains important.",
        }
    ]

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["areas_of_agreement"][0]["theme"] == "unspecified"
    assert parsed["areas_of_agreement"][0]["evidence_ids"] == []
    assert parsed["areas_of_agreement"][0]["evidence_limit"]


def test_committee_validator_drops_invalid_agreement_evidence_ids_to_schema_warning():
    payload = _committee_payload_dict()
    payload["areas_of_agreement"] = [
        {
            "theme": "cash conversion",
            "summary": "Analysts agree that cash-flow evidence remains limited.",
            "evidence_ids": ["financial_quality_inputs", "ev_missing_1", "ev_graham_1"],
            "source_analysts": ["graham"],
        }
    ]

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["areas_of_agreement"][0]["evidence_ids"] == ["ev_graham_1"]
    assert any("areas_of_agreement.evidence_ids dropped evidence IDs" in item for item in parsed["schema_warnings"])


def test_committee_validator_rejects_invalid_agreement_source_analyst():
    payload = _committee_payload_dict()
    payload["areas_of_agreement"] = [
        {
            "theme": "cash conversion",
            "summary": "Analysts agree that cash-flow evidence remains limited.",
            "source_analysts": ["porter"],
            "evidence_ids": [],
        }
    ]

    with pytest.raises(ValueError, match="invalid analysts"):
        validate_committee_output(
            payload,
            company="polymatech",
            included_analysts=["graham", "buffett", "fisher"],
            missing_analysts=["lynch"],
            excluded_analysts=["munger"],
            allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
            analyst_uncertainties={},
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
            allow_unresolved_ids=True,
        )


def test_committee_validator_normalizes_area_of_disagreement_string():
    payload = _committee_payload_dict()
    payload["areas_of_disagreement"] = [
        {
            "topic": "growth versus downside",
            "disagreement": "Fisher weights growth more heavily while Graham weights downside.",
            "analysts_positive": "Fisher",
            "analysts_cautious": "Graham",
            "evidence": ["multi_year_inputs", "ev_fisher_1"],
            "disagreement_type": "risk_weighting_difference",
        }
    ]

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["areas_of_disagreement"][0]["theme"] == "growth versus downside"
    assert parsed["areas_of_disagreement"][0]["analysts_positive_or_less_concerned"] == ["fisher"]
    assert parsed["areas_of_disagreement"][0]["analysts_cautious_or_negative"] == ["graham"]
    assert parsed["areas_of_disagreement"][0]["evidence_ids"] == ["ev_fisher_1"]


def test_committee_validator_normalizes_positive_signals_list_of_strings():
    payload = _committee_payload_dict()
    payload["strongest_positive_signals"] = [
        "Reported margins appear strong.",
        "Growth execution has some analyst support.",
    ]

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["strongest_positive_signals"][0]["signal"] == "Reported margins appear strong."
    assert parsed["strongest_positive_signals"][0]["source_analysts"] == []
    assert parsed["strongest_positive_signals"][0]["evidence_ids"] == []
    assert parsed["strongest_positive_signals"][0]["evidence_limit"]


def test_committee_validator_normalizes_positive_signal_dict_aliases_and_drops_section_ids():
    payload = _committee_payload_dict()
    payload["strongest_positive_signals"] = {
        "title": "margin strength",
        "importance": "It supports the quality side of the story.",
        "analysts": "Buffett, Fisher",
        "evidence_ids": ["profitability_inputs", "ev_fisher_1"],
    }

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["strongest_positive_signals"][0]["signal"] == "margin strength"
    assert parsed["strongest_positive_signals"][0]["source_analysts"] == ["buffett", "fisher"]
    assert parsed["strongest_positive_signals"][0]["supported_by"] == ["buffett", "fisher"]
    assert parsed["strongest_positive_signals"][0]["evidence_ids"] == ["ev_fisher_1"]
    assert any("strongest_positive_signals.evidence_ids dropped evidence IDs" in item for item in parsed["schema_warnings"])


def test_committee_validator_normalizes_positive_signals_null_to_empty_list():
    payload = _committee_payload_dict()
    payload["strongest_positive_signals"] = None

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["strongest_positive_signals"] == []


def test_committee_validator_normalizes_risk_signals_list_of_strings():
    payload = _committee_payload_dict()
    payload["most_important_risks"] = ["Free cash flow remains unavailable."]

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["most_important_risks"][0]["risk"] == "Free cash flow remains unavailable."
    assert parsed["most_important_risks"][0]["severity"] == "uncertain"
    assert parsed["most_important_risks"][0]["source_analysts"] == []


def test_committee_validator_normalizes_investigation_question_string():
    payload = _committee_payload_dict()
    payload["investigation_questions"] = [
        "What future filings clarify free cash flow and capex?"
    ]

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
        allow_unresolved_ids=True,
    )

    assert parsed["investigation_questions"][0] == {
        "question": "What future filings clarify free cash flow and capex?",
        "reason": "",
        "linked_unknown_or_risk": "",
    }


def test_committee_validator_rejects_raw_text_in_positive_signal():
    payload = _committee_payload_dict()
    payload["strongest_positive_signals"] = [
        {
            "signal": "margin strength",
            "raw_text": "raw internal payload",
        }
    ]

    with pytest.raises(ValueError, match="forbidden internal or raw payload content|forbidden internal fields"):
        validate_committee_output(
            payload,
            company="polymatech",
            included_analysts=["graham", "buffett", "fisher"],
            missing_analysts=["lynch"],
            excluded_analysts=["munger"],
            allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
            analyst_uncertainties={},
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
            allow_unresolved_ids=True,
        )


def test_committee_object_list_contracts_cover_strict_validator_fields():
    for field in (
        "areas_of_agreement",
        "areas_of_disagreement",
        "strongest_positive_signals",
        "most_important_risks",
        "critical_unknowns",
        "investigation_questions",
        "financial_committee_view.financial_disagreements",
    ):
        assert COMMITTEE_FIELD_CONTRACTS[field]["type"] == "object_list"


def _no_financial_analysis_payload(doctrine_id: str) -> dict:
    payload = _analysis_payload(doctrine_id)
    payload["financial_metrics_used"] = []
    payload["financial_red_flags"] = []
    payload["financial_positive_signals"] = []
    payload["financial_missing_data"] = []
    payload["financial_interpretation_limits"] = []
    payload["financial_sections_consumed"] = []
    payload["financial_warnings_carried_forward"] = []
    payload["financial_assessment"] = {
        "financials_used": False,
        "basis_used": "unknown",
        "key_financial_strengths": [],
        "key_financial_concerns": [],
        "financial_red_flags": [],
        "missing_financial_data": [],
        "financial_interpretation_limits": [],
    }
    return payload


def _single_analyst_committee_payload(
    analyst: str,
    *,
    financials_used: Any,
    include_financial_detail: bool,
) -> dict:
    payload = _committee_payload_dict()
    payload["analysts_considered"] = [analyst]
    payload["missing_analysts"] = [item for item in ["buffett", "fisher", "munger", "lynch"] if item != analyst]
    payload["excluded_analysts"] = []
    payload["areas_of_agreement"] = [
        {
            "theme": "focused issue",
            "analysts": [analyst],
            "summary": "The single available analyst raised this issue.",
            "evidence_ids": [f"ev_{analyst}_1"],
        }
    ]
    payload["areas_of_disagreement"] = []
    payload["strongest_positive_signals"] = [
        {
            "signal": "The available analyst sees a visible positive.",
            "supported_by": [analyst],
            "summary": "This signal is drawn from the available analyst only.",
            "evidence_ids": [f"ev_{analyst}_1"],
        }
    ]
    payload["most_important_risks"] = [
        {
            "risk": "The available analyst sees a visible risk.",
            "raised_by": [analyst],
            "summary": "This risk is drawn from the available analyst only.",
            "severity": "medium",
            "evidence_ids": [f"ev_{analyst}_1"],
        }
    ]
    payload["critical_unknowns"] = [
        {
            "unknown": f"{analyst} wants more cash flow evidence",
            "raised_by": [analyst],
            "why_it_matters": "More evidence is still needed.",
            "source_uncertainty_ids": [f"{analyst}_u001"],
        }
    ]
    payload["evidence_ids"] = [f"ev_{analyst}_1"]
    payload["financial_committee_view"]["financials_used"] = financials_used
    if include_financial_detail:
        payload["financial_committee_view"] = {
            "financials_used": financials_used,
            "basis_used": "consolidated",
            "financial_consensus": ["Revenue and PAT evidence is available from the analyst."],
            "financial_strengths": ["Revenue and PAT are moving in the right direction."],
            "financial_concerns": ["Debt and funding pressure remain important constraints."],
            "financial_disagreements": [],
            "missing_financial_data": ["Share-count comparability is still limited."],
            "financial_red_flags": ["Debt and funding pressure remain important constraints."],
            "financial_interpretation_limits": ["No new ratios were calculated beyond supplied financial inputs."],
            "investor_questions_from_financials": ["How sustainable are CFO and FCF as debt obligations continue?"],
        }
    else:
        payload["financial_committee_view"] = {
            "financials_used": financials_used,
            "basis_used": "unknown",
            "financial_consensus": [],
            "financial_strengths": [],
            "financial_concerns": [],
            "financial_disagreements": [],
            "missing_financial_data": [],
            "financial_red_flags": [],
            "financial_interpretation_limits": [],
            "investor_questions_from_financials": [],
        }
    return payload


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
    _write_analysis(
        tmp_path,
        "munger",
        _analysis_payload("munger", status="fail", evidence_ids=["risk_inputs"]),
    )

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
    assert isinstance(saved["areas_of_disagreement"], list)
    assert "Missing analyst inputs: lynch." in saved["synthesis_limits"]
    assert "Excluded analyst inputs due to evidence grounding failure: munger." in saved["synthesis_limits"]
    assert fake_llm.calls[0]["system_prompt"].strip().startswith(
        "You are the committee narrative writer for Prometheus."
    )
    assert "graham" in fake_llm.calls[0]["prompt"]
    assert "munger" in fake_llm.calls[0]["prompt"]


def test_committee_synthesis_owns_metadata_deterministically_before_validation(tmp_path, monkeypatch):
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
    _write_analysis(
        tmp_path,
        "munger",
        _analysis_payload("munger", status="fail", evidence_ids=["risk_inputs"]),
    )

    response_payload = json.loads(_committee_response())
    response_payload.pop("analysis_mode")
    response_payload["company"] = "wrong-company"
    response_payload["analysts_considered"] = ["graham"]
    response_payload["missing_analysts"] = []
    response_payload["excluded_analysts"] = []
    response_payload.pop("generated_at")
    fake_llm = _FakeLLM(json.dumps(response_payload))
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
    assert saved["company"] == "polymatech"
    assert saved["analysis_mode"] == "committee_synthesis_v1"
    assert saved["analysts_considered"] == ["graham", "buffett", "fisher"]
    assert saved["missing_analysts"] == ["lynch"]
    assert saved["excluded_analysts"] == ["munger"]
    assert saved["generated_at"]


@pytest.mark.parametrize("raw_confidence", ["moderate", "medium confidence", None, "totally unclear"])
def test_committee_synthesizer_uses_deterministic_confidence_not_llm_confidence(tmp_path, monkeypatch, raw_confidence):
    _write_analysis(tmp_path, "graham", _analysis_payload("graham"))
    _write_analysis(tmp_path, "buffett", _analysis_payload("buffett"))
    _write_analysis(tmp_path, "fisher", _analysis_payload("fisher"))
    response_payload = json.loads(_committee_response())
    if raw_confidence is None:
        response_payload["overall_committee_view"].pop("confidence", None)
    else:
        response_payload["overall_committee_view"]["confidence"] = raw_confidence
    fake_llm = _FakeLLM(json.dumps(response_payload))
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
    assert saved["overall_committee_view"]["confidence"] == "medium"


def test_committee_enum_normalizer_repairs_rating_variants():
    synthesizer = InvestmentCommitteeSynthesizer(company="polymatech")
    payload = {
        "overall_committee_view": {"confidence": "moderate"},
        "areas_of_agreement": [{"rating": "neutral"}],
        "strongest_positive_signals": [{"rating": "insufficient evidence"}],
        "areas_of_disagreement": [{"disagreement_type": "different emphasis"}],
    }

    normalized, repairs = synthesizer._normalize_committee_output_enums(payload)

    assert normalized["overall_committee_view"]["confidence"] == "medium"
    assert normalized["areas_of_agreement"][0]["rating"] == "mixed"
    assert (
        normalized["strongest_positive_signals"][0]["rating"]
        == "insufficient_evidence"
    )
    assert (
        normalized["areas_of_disagreement"][0]["disagreement_type"]
        == "different_emphasis"
    )
    assert any(
        repair["path"] == "areas_of_agreement.0.rating"
        and repair["normalized"] == "mixed"
        for repair in repairs
    )
    assert any(
        repair["path"] == "strongest_positive_signals.0.rating"
        and repair["normalized"] == "insufficient_evidence"
        for repair in repairs
    )


@pytest.mark.parametrize("raw_value", ["risk concern", "different angle", "conflicting views", None, "weird enum"])
def test_committee_synthesizer_uses_deterministic_disagreement_candidates_not_llm_disagreement_type(
    tmp_path, monkeypatch, raw_value
):
    _write_analysis(tmp_path, "graham", _analysis_payload("graham"))
    _write_analysis(tmp_path, "buffett", _analysis_payload("buffett"))
    _write_analysis(tmp_path, "fisher", _analysis_payload("fisher"))

    response_payload = json.loads(_committee_response())
    response_payload["areas_of_disagreement"][0]["summary"] = "LLM disagreement content should not own the clean committee structure."
    if raw_value is None:
        response_payload["areas_of_disagreement"][0].pop("disagreement_type", None)
    else:
        response_payload["areas_of_disagreement"][0]["disagreement_type"] = raw_value
    fake_llm = _FakeLLM(json.dumps(response_payload))
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
    assert isinstance(saved["areas_of_disagreement"], list)
    if saved["areas_of_disagreement"]:
        assert saved["areas_of_disagreement"][0]["disagreement_type"] in {
            "risk_weighting_difference",
            "different_emphasis",
            "true_disagreement",
        }


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
                "financial_committee_view": {
                    "financials_used": True,
                    "basis_used": "consolidated",
                    "financial_consensus": [],
                    "financial_strengths": [],
                    "financial_concerns": [],
                "financial_disagreements": [],
                "missing_financial_data": ["Financial evidence is limited."],
                "financial_red_flags": [],
                "financial_interpretation_limits": ["Financial evidence is limited."],
                "investor_questions_from_financials": [],
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
            included_analyst_payloads=[_analysis_payload("graham")],
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
                "financial_committee_view": {
                    "financials_used": True,
                    "basis_used": "consolidated",
                    "financial_consensus": ["Revenue evidence is available."],
                    "financial_strengths": ["Revenue evidence is available."],
                    "financial_concerns": ["Debt evidence remains incomplete."],
                "financial_disagreements": [],
                "missing_financial_data": ["FCF evidence is limited."],
                "financial_red_flags": ["Debt evidence remains incomplete."],
                "financial_interpretation_limits": ["Cash conversion evidence is limited."],
                "investor_questions_from_financials": [],
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
        included_analyst_payloads=[_analysis_payload("graham")],
        mode="final",
    )
    assert parsed["overall_committee_view"]["summary"].startswith("The committee noted the offer-for-sale")


@pytest.mark.parametrize(
    ("raw_value", "expected_value", "warning_fragment"),
    [
        ("true", True, "financial_committee_view.financials_used was normalized from string to boolean."),
        ("yes", True, "financial_committee_view.financials_used was normalized from string to boolean."),
        ("false", False, "financial_committee_view.financials_used was normalized from string to boolean."),
        ("no", False, "financial_committee_view.financials_used was normalized from string to boolean."),
        (1, True, "financial_committee_view.financials_used was normalized from integer to boolean."),
        (0, False, "financial_committee_view.financials_used was normalized from integer to boolean."),
    ],
)
def test_committee_validator_normalizes_financials_used_variants(
    raw_value,
    expected_value,
    warning_fragment,
):
    analyst_payload = _analysis_payload("graham") if expected_value else _no_financial_analysis_payload("graham")
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=raw_value,
        include_financial_detail=expected_value,
    )

    parsed = validate_committee_output(
        json.dumps(payload),
        company="polymatech",
        included_analysts=["graham"],
        missing_analysts=["buffett", "fisher", "munger", "lynch"],
        excluded_analysts=[],
        allowed_evidence_ids=["ev_graham_1"],
        analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
        included_analyst_payloads=[analyst_payload],
        mode="final",
    )
    assert parsed["financial_committee_view"]["financials_used"] is expected_value
    assert warning_fragment in parsed["schema_warnings"]


def test_committee_validator_accepts_explicit_financials_used_true():
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=True,
        include_financial_detail=True,
    )
    parsed = validate_committee_output(
        json.dumps(payload),
        company="polymatech",
        included_analysts=["graham"],
        missing_analysts=["buffett", "fisher", "munger", "lynch"],
        excluded_analysts=[],
        allowed_evidence_ids=["ev_graham_1"],
        analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
        included_analyst_payloads=[_analysis_payload("graham")],
        mode="final",
    )
    assert parsed["financial_committee_view"]["financials_used"] is True


def test_committee_validator_accepts_explicit_financials_used_false():
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=False,
        include_financial_detail=False,
    )
    parsed = validate_committee_output(
        json.dumps(payload),
        company="polymatech",
        included_analysts=["graham"],
        missing_analysts=["buffett", "fisher", "munger", "lynch"],
        excluded_analysts=[],
        allowed_evidence_ids=["ev_graham_1"],
        analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
        included_analyst_payloads=[_no_financial_analysis_payload("graham")],
        mode="final",
    )
    assert parsed["financial_committee_view"]["financials_used"] is False


def test_committee_validator_rejects_ambiguous_financials_used():
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used="maybe",
        include_financial_detail=True,
    )
    with pytest.raises(ValueError, match="financial_committee_view.financials_used must be a boolean"):
        validate_committee_output(
            json.dumps(payload),
            company="polymatech",
            included_analysts=["graham"],
            missing_analysts=["buffett", "fisher", "munger", "lynch"],
            excluded_analysts=[],
            allowed_evidence_ids=["ev_graham_1"],
            analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
            included_analyst_payloads=[_analysis_payload("graham")],
            mode="final",
        )


def test_committee_validator_rejects_financials_used_false_when_analysts_used_financials():
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=False,
        include_financial_detail=True,
    )
    with pytest.raises(ValueError, match="financial_committee_view.financials_used must match analyst financial input usage"):
        validate_committee_output(
            json.dumps(payload),
            company="polymatech",
            included_analysts=["graham"],
            missing_analysts=["buffett", "fisher", "munger", "lynch"],
            excluded_analysts=[],
            allowed_evidence_ids=["ev_graham_1"],
            analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
            included_analyst_payloads=[_analysis_payload("graham")],
            mode="final",
        )


def test_committee_validator_rejects_financials_used_true_when_analysts_did_not_use_financials():
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=True,
        include_financial_detail=False,
    )
    with pytest.raises(ValueError, match="financial_committee_view.financials_used must match analyst financial input usage"):
        validate_committee_output(
            json.dumps(payload),
            company="polymatech",
            included_analysts=["graham"],
            missing_analysts=["buffett", "fisher", "munger", "lynch"],
            excluded_analysts=[],
            allowed_evidence_ids=["ev_graham_1"],
            analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
            included_analyst_payloads=[_no_financial_analysis_payload("graham")],
            mode="final",
        )


@pytest.mark.parametrize(
    ("raw_basis", "expected_basis", "warning_fragment"),
    [
        ("consolidated basis", "consolidated", "financial_committee_view.basis_used normalized to consolidated."),
        ("Consolidated Financials", "consolidated", "financial_committee_view.basis_used normalized to consolidated."),
        ("standalone basis", "standalone", "financial_committee_view.basis_used normalized to standalone."),
        ("both", "mixed", "financial_committee_view.basis_used normalized to mixed."),
    ],
)
def test_committee_validator_normalizes_basis_used_variants(
    raw_basis,
    expected_basis,
    warning_fragment,
):
    if expected_basis == "standalone":
        analyst_payload = _analysis_payload("graham")
        analyst_payload["financial_assessment"]["basis_used"] = "standalone"
    elif expected_basis == "mixed":
        analyst_payload = _analysis_payload("graham")
        analyst_payload["financial_assessment"]["basis_used"] = "mixed"
    else:
        analyst_payload = _analysis_payload("graham")

    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=True,
        include_financial_detail=True,
    )
    payload["financial_committee_view"]["basis_used"] = raw_basis

    parsed = validate_committee_output(
        json.dumps(payload),
        company="polymatech",
        included_analysts=["graham"],
        missing_analysts=["buffett", "fisher", "munger", "lynch"],
        excluded_analysts=[],
        allowed_evidence_ids=["ev_graham_1"],
        analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
        included_analyst_payloads=[analyst_payload],
        mode="final",
    )
    assert parsed["financial_committee_view"]["basis_used"] == expected_basis
    assert warning_fragment in parsed["schema_warnings"]


def test_committee_validator_null_basis_uses_expected_basis():
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=True,
        include_financial_detail=True,
    )
    payload["financial_committee_view"]["basis_used"] = None

    parsed = validate_committee_output(
        json.dumps(payload),
        company="polymatech",
        included_analysts=["graham"],
        missing_analysts=["buffett", "fisher", "munger", "lynch"],
        excluded_analysts=[],
        allowed_evidence_ids=["ev_graham_1"],
        analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
        included_analyst_payloads=[_analysis_payload("graham")],
        mode="final",
    )
    assert parsed["financial_committee_view"]["basis_used"] == "consolidated"
    assert "financial_committee_view.basis_used normalized to consolidated." in parsed["schema_warnings"]


def test_committee_validator_null_basis_becomes_unknown_when_no_expected_basis():
    analyst_payload = _analysis_payload("graham")
    analyst_payload["financial_assessment"]["basis_used"] = "unknown"
    analyst_payload["financial_warnings_carried_forward"] = ["Basis is unknown."]
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=True,
        include_financial_detail=True,
    )
    payload["financial_committee_view"]["basis_used"] = None
    payload["financial_committee_view"]["basis_used"] = None
    payload["financial_committee_view"]["basis_used"] = None

    parsed = validate_committee_output(
        json.dumps(payload),
        company="polymatech",
        included_analysts=["graham"],
        missing_analysts=["buffett", "fisher", "munger", "lynch"],
        excluded_analysts=[],
        allowed_evidence_ids=["ev_graham_1"],
        analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
        included_analyst_payloads=[analyst_payload],
        mode="final",
    )
    assert parsed["financial_committee_view"]["basis_used"] == "unknown"
    assert "financial_committee_view.basis_used normalized to unknown." in parsed["schema_warnings"]


def test_committee_validator_rejects_basis_mismatch_consolidated_vs_standalone():
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=True,
        include_financial_detail=True,
    )
    payload["financial_committee_view"]["basis_used"] = "standalone"
    with pytest.raises(ValueError, match="financial_committee_view.basis_used must match analyst financial basis usage"):
        validate_committee_output(
            json.dumps(payload),
            company="polymatech",
            included_analysts=["graham"],
            missing_analysts=["buffett", "fisher", "munger", "lynch"],
            excluded_analysts=[],
            allowed_evidence_ids=["ev_graham_1"],
            analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
            included_analyst_payloads=[_analysis_payload("graham")],
            mode="final",
        )


def test_committee_validator_rejects_basis_mismatch_mixed_vs_consolidated():
    analyst_payload = _analysis_payload("graham")
    analyst_payload["financial_assessment"]["basis_used"] = "mixed"
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=True,
        include_financial_detail=True,
    )
    payload["financial_committee_view"]["basis_used"] = "consolidated"
    with pytest.raises(ValueError, match="financial_committee_view.basis_used must match analyst financial basis usage"):
        validate_committee_output(
            json.dumps(payload),
            company="polymatech",
            included_analysts=["graham"],
            missing_analysts=["buffett", "fisher", "munger", "lynch"],
            excluded_analysts=[],
            allowed_evidence_ids=["ev_graham_1"],
            analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
            included_analyst_payloads=[analyst_payload],
            mode="final",
        )


def test_committee_validator_rejects_invalid_basis_string():
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=True,
        include_financial_detail=True,
    )
    payload["financial_committee_view"]["basis_used"] = "group basis"
    with pytest.raises(ValueError, match="financial_committee_view.basis_used must be consolidated\\|standalone\\|mixed\\|unknown"):
        validate_committee_output(
            json.dumps(payload),
            company="polymatech",
            included_analysts=["graham"],
            missing_analysts=["buffett", "fisher", "munger", "lynch"],
            excluded_analysts=[],
            allowed_evidence_ids=["ev_graham_1"],
            analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
            included_analyst_payloads=[_analysis_payload("graham")],
            mode="final",
        )


def test_committee_validator_rejects_source_chunk_leak_in_basis_field():
    payload = _single_analyst_committee_payload(
        "graham",
        financials_used=True,
        include_financial_detail=True,
    )
    payload["financial_committee_view"]["basis_used"] = "source_chunk: consolidated"
    with pytest.raises(ValueError, match="financial_committee_view.basis_used must be consolidated\\|standalone\\|mixed\\|unknown"):
        validate_committee_output(
            json.dumps(payload),
            company="polymatech",
            included_analysts=["graham"],
            missing_analysts=["buffett", "fisher", "munger", "lynch"],
            excluded_analysts=[],
            allowed_evidence_ids=["ev_graham_1"],
            analyst_uncertainties={"graham": ["Need more cash flow evidence."]},
            included_analyst_payloads=[_analysis_payload("graham")],
            mode="final",
        )


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
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
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
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
        )


def test_committee_validator_rejects_unsupported_financial_claim():
    payload = json.loads(_committee_response())
    payload["financial_committee_view"]["financial_consensus"] = [
        "Interest coverage is strong even though analysts did not provide that metric."
    ]

    with pytest.raises(ValueError, match="financial concepts not present in analyst outputs"):
        validate_committee_output(
            json.dumps(payload),
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
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
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


@pytest.mark.parametrize(
    ("missing_value", "expected_warning"),
    [
        ([], None),
        (None, "missing_analysts was normalized to []"),
        ("none", "missing_analysts was normalized to []"),
    ],
)
def test_committee_validator_normalizes_empty_missing_analysts_variants(
    missing_value,
    expected_warning,
):
    payload = _committee_payload_dict()
    payload["analysts_considered"] = ["graham", "buffett", "fisher", "munger", "lynch"]
    payload["missing_analysts"] = missing_value
    payload["excluded_analysts"] = []
    payload["evidence_ids"] = [
        "ev_graham_1",
        "ev_buffett_1",
        "ev_fisher_1",
        "ev_munger_1",
        "ev_lynch_1",
    ]

    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher", "munger", "lynch"],
        missing_analysts=[],
        excluded_analysts=[],
        allowed_evidence_ids=payload["evidence_ids"],
        analyst_uncertainties={
            "graham": ["Need more cash flow evidence."],
            "buffett": ["Need more cash flow evidence."],
            "fisher": ["Need more cash flow evidence."],
            "munger": ["Need more governance evidence."],
            "lynch": ["Need more simple-story evidence."],
        },
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
            _analysis_payload("munger"),
            _analysis_payload("lynch"),
        ],
        mode="final",
    )
    assert parsed["missing_analysts"] == []
    if expected_warning:
        assert expected_warning in parsed["schema_warnings"]


def test_committee_validator_accepts_exact_missing_analyst_list():
    payload = _committee_payload_dict()
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
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
    )
    assert parsed["missing_analysts"] == ["lynch"]


def test_committee_validator_rejects_hidden_missing_analyst():
    payload = _committee_payload_dict()
    payload["missing_analysts"] = []
    with pytest.raises(ValueError, match="missing_analysts must match missing analysts"):
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
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
        )


def test_committee_validator_rejects_invented_missing_analyst():
    payload = _committee_payload_dict()
    payload["analysts_considered"] = ["graham", "buffett", "fisher", "munger", "lynch"]
    payload["missing_analysts"] = ["fisher"]
    payload["excluded_analysts"] = []
    payload["evidence_ids"] = [
        "ev_graham_1",
        "ev_buffett_1",
        "ev_fisher_1",
        "ev_munger_1",
        "ev_lynch_1",
    ]
    with pytest.raises(ValueError, match="missing_analysts must match missing analysts"):
        validate_committee_output(
            payload,
            company="polymatech",
            included_analysts=["graham", "buffett", "fisher", "munger", "lynch"],
            missing_analysts=[],
            excluded_analysts=[],
            allowed_evidence_ids=payload["evidence_ids"],
            analyst_uncertainties={
                "graham": ["Need more cash flow evidence."],
                "buffett": ["Need more cash flow evidence."],
                "fisher": ["Need more cash flow evidence."],
                "munger": ["Need more governance evidence."],
                "lynch": ["Need more simple-story evidence."],
            },
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
                _analysis_payload("munger"),
                _analysis_payload("lynch"),
            ],
            mode="final",
        )


def test_committee_validator_rejects_invalid_missing_analyst_name():
    payload = _committee_payload_dict()
    payload["missing_analysts"] = ["ghost"]
    with pytest.raises(ValueError, match="missing_analysts contains invalid analysts"):
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
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
        )


def test_committee_validator_allows_owner_earnings_limitation_when_analyst_limitation_exists():
    payload = json.loads(_committee_response())
    payload["financial_committee_view"]["financial_interpretation_limits"] = [
        "Owner earnings cannot be assessed because FCF/capex data is missing."
    ]
    graham = _analysis_payload("graham")
    graham["financial_assessment"]["financial_interpretation_limits"] = [
        "Owner earnings cannot be assessed because FCF/capex data is missing."
    ]

    parsed = validate_committee_output(
        json.dumps(payload),
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
        included_analyst_payloads=[
            graham,
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
    )

    assert parsed["financial_committee_view"]["financial_interpretation_limits"] == [
        "Owner earnings cannot be assessed because FCF/capex data is missing."
    ]


def test_committee_validator_allows_owner_earnings_limitation_from_fcf_capex_warning():
    payload = json.loads(_committee_response())
    payload["financial_committee_view"]["financial_interpretation_limits"] = [
        "Owner-earnings analysis is limited by missing capex and FCF."
    ]
    graham = _analysis_payload("graham")
    graham["financial_warnings_carried_forward"] = [
        "Free cash flow is missing; FCF-based conclusions cannot be assessed.",
        "Capex data is missing.",
    ]

    parsed = validate_committee_output(
        json.dumps(payload),
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
        included_analyst_payloads=[
            graham,
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
    )

    assert "Owner-earnings analysis is limited" in parsed["financial_committee_view"]["financial_interpretation_limits"][0]


@pytest.mark.parametrize(
    "claim",
    [
        "Owner earnings could not be assessed because FCF/capex is missing.",
        "Owner earnings are not assessable with missing free cash flow.",
        "FCF/capex missing prevents owner earnings assessment.",
        "Capex missing prevents owner-earnings or reinvestment-rate interpretation.",
    ],
)
def test_committee_validator_allows_owner_earnings_limitation_variants(claim):
    payload = json.loads(_committee_response())
    payload["financial_committee_view"]["financial_interpretation_limits"] = [claim]
    graham = _analysis_payload("graham")
    graham["reasoning_limits"] = [
        "Owner earnings could not be assessed because FCF/capex is missing."
    ]

    parsed = validate_committee_output(
        json.dumps(payload),
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
        included_analyst_payloads=[
            graham,
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
    )

    assert parsed["financial_committee_view"]["financial_interpretation_limits"] == [claim]


def test_owner_earnings_reference_classifier_distinguishes_limitation_positive_and_ambiguous():
    assert (
        _classify_owner_earnings_reference(
            "Owner earnings cannot be assessed because FCF/capex is missing."
        )
        == "limitation"
    )
    assert _classify_owner_earnings_reference("Owner earnings are strong.") == "positive_claim"
    assert _classify_owner_earnings_reference("Owner earnings require more review.") == "neutral_reference"
    assert _classify_owner_earnings_reference("Free cash flow is missing.") == "none"


def test_owner_earnings_reference_classifier_treats_supported_questions_as_question():
    from intelligence.investor_panel.committee_validator import classify_owner_earnings_reference

    assert (
        classify_owner_earnings_reference(
            "What were capital expenditures required to assess free cash flow and owner earnings?",
            path="financial_committee_view.investor_questions_from_financials[0]",
            financial_context={"fcf_missing": True, "capex_missing": True},
        )
        == "question"
    )


@pytest.mark.parametrize(
    "claim",
    [
        "What were capital expenditures (amounts and timing) for FY22-FY24? Reason: Capex magnitude/timing is required to assess free cash flow and owner-earnings readiness.",
        "Capex is needed to assess owner earnings.",
        "Owner earnings cannot be assessed without capex.",
        "Free cash flow and owner-earnings readiness require capex timing.",
    ],
)
def test_committee_validator_allows_owner_earnings_question_or_limitation_with_missing_capex(claim):
    payload = json.loads(_committee_response())
    payload["financial_committee_view"]["investor_questions_from_financials"] = [claim]
    payload["financial_committee_view"]["financial_interpretation_limits"] = []
    graham = _analysis_payload("graham")
    graham["financial_warnings_carried_forward"] = [
        "Free cash flow is missing; FCF-based conclusions cannot be assessed."
    ]
    graham["financial_interpretation_limits"] = [
        "Capex is missing or incomplete; owner earnings cannot be assessed."
    ]

    parsed = validate_committee_output(
        json.dumps(payload),
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
        included_analyst_payloads=[
            graham,
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
    )

    assert parsed["financial_committee_view"]["investor_questions_from_financials"] == [claim]
    assert any(
        "owner earnings reference allowed as" in warning
        and "investor_questions_from_financials[0]" in warning
        for warning in parsed["schema_warnings"]
    )


def test_committee_sanitizer_rewrites_owner_earnings_readiness_phrase():
    from intelligence.investor_panel.committee_synthesizer import _sanitize_committee_text

    assert (
        _sanitize_committee_text("Capex is needed for owner-earnings readiness.")
        == "Capex is needed for owner-earnings assessment readiness."
    )


@pytest.mark.parametrize(
    "claim",
    [
        "Owner earnings are strong.",
        "Owner earnings are positive.",
        "Owner earnings support dividends.",
        "Owner earnings yield is attractive.",
        "Owner earnings margin is improving.",
        "Owner earnings can be assessed.",
    ],
)
def test_committee_validator_rejects_positive_owner_earnings_claims_without_support(claim):
    payload = json.loads(_committee_response())
    payload["financial_committee_view"]["financial_strengths"] = [claim]
    graham = _analysis_payload("graham")
    graham["financial_warnings_carried_forward"] = [
        "Free cash flow is missing; FCF-based conclusions cannot be assessed."
    ]

    with pytest.raises(ValueError, match="positive owner earnings"):
        validate_committee_output(
            json.dumps(payload),
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
            included_analyst_payloads=[
                graham,
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
        )


def test_committee_validator_rejects_ambiguous_owner_earnings_language():
    payload = json.loads(_committee_response())
    payload["financial_committee_view"]["financial_concerns"] = [
        "Owner earnings require additional discussion."
    ]
    graham = _analysis_payload("graham")
    graham["financial_warnings_carried_forward"] = [
        "Free cash flow is missing; FCF-based conclusions cannot be assessed."
    ]

    with pytest.raises(ValueError, match="ambiguous owner earnings language"):
        validate_committee_output(
            json.dumps(payload),
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
            included_analyst_payloads=[
                graham,
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
        )


def test_committee_validator_owner_earnings_failure_diagnostic_includes_path_and_flags():
    payload = json.loads(_committee_response())
    payload["financial_committee_view"]["financial_strengths"] = [
        "Owner earnings yield is attractive."
    ]
    graham = _analysis_payload("graham")
    graham["financial_warnings_carried_forward"] = [
        "Free cash flow is missing; FCF-based conclusions cannot be assessed.",
        "Capex data is missing.",
    ]

    with pytest.raises(ValueError) as excinfo:
        validate_committee_output(
            json.dumps(payload),
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
            included_analyst_payloads=[
                graham,
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
        )

    message = str(excinfo.value)
    assert "financial_committee_view.financial_strengths[0]" in message
    assert "classified_type=positive_claim" in message
    assert "fcf_missing=True" in message
    assert "capex_missing=True" in message


def test_committee_synthesis_compacts_analyst_blocks_and_preserves_financial_warning_manifest(tmp_path):
    long_text = "Very long analyst detail that should be compacted before committee synthesis. " * 60
    payload = _analysis_payload(
        "graham",
        uncertainties=[long_text, "Free cash flow is missing.", "Capex data is missing."],
    )
    payload["key_findings"] = [long_text] * 6
    payload["red_flags"] = [long_text] * 6
    payload["financial_metrics_used"] = [
        "revenue",
        "pat",
        "cfo",
        "fcf",
        "roe",
        "roce",
        "debt",
        "eps",
        "book_value_per_share",
    ]
    payload["financial_assessment"]["key_financial_strengths"] = [long_text] * 5
    payload["financial_assessment"]["key_financial_concerns"] = [long_text] * 5
    payload["financial_assessment"]["financial_interpretation_limits"] = [
        "Free cash flow is missing, so owner earnings cannot be assessed.",
        "Basis is unknown.",
        long_text,
    ]
    payload["financial_warnings_carried_forward"] = [
        "Free cash flow is missing; FCF-based conclusions cannot be assessed.",
        "Capex data is missing.",
        "Payables are missing.",
        "Share count comparability is still limited.",
        "Basis is unknown.",
        "Audit warning remains open.",
    ]
    _write_analysis(tmp_path, "graham", payload)

    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    included, missing, excluded, warnings = synthesizer._load_inputs()
    committee_input = synthesizer._build_committee_input(
        included=included,
        missing=missing,
        excluded=excluded,
        warning_notes=warnings,
    )

    analyst_block = committee_input["analysts"][0]
    serialized = json.dumps(analyst_block, ensure_ascii=False)
    assert len(serialized) <= synthesizer.ANALYST_CHAR_BUDGET
    assert len(analyst_block["top_positive_signals"]) <= 2
    assert len(analyst_block["financial_strengths"]) <= 2
    assert len(analyst_block["financial_warnings"]) <= 3
    assert committee_input["financial_warning_manifest"]["missing_fcf"] == ["graham"]
    assert committee_input["financial_warning_manifest"]["missing_capex"] == ["graham"]
    assert committee_input["financial_warning_manifest"]["missing_payables"] == ["graham"]
    assert committee_input["financial_warning_manifest"]["share_count_limitations"] == ["graham"]
    assert committee_input["financial_warning_manifest"]["basis_unknown"] is True
    assert committee_input["financial_warning_manifest"]["basis_unknown_analysts"] == ["graham"]


def test_committee_synthesis_prompt_uses_compact_analyst_view_not_full_json(tmp_path):
    payload = _analysis_payload("graham")
    payload["schema_warnings"] = ["debug noise"]
    payload["user_facing_brief"]["bottom_line"] = "This should not appear in the committee prompt."
    payload["financial_sections_consumed"] = ["financial_trend_inputs", "cash_conversion_inputs"]
    _write_analysis(tmp_path, "graham", payload)

    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    included, missing, excluded, warnings = synthesizer._load_inputs()
    committee_input = synthesizer._build_committee_input(
        included=included,
        missing=missing,
        excluded=excluded,
        warning_notes=warnings,
    )
    prompt, llm_input_pack, manifest = synthesizer._build_compact_prompt_assets(committee_input)

    assert '"user_facing_brief"' not in prompt
    assert '"schema_warnings"' not in prompt
    assert '"sections_consumed"' not in prompt
    assert '"source_chunk"' not in prompt
    assert "financial_warning_manifest" in prompt
    assert '"user_facing_bottom_line"' not in prompt
    assert '"financial_assessment"' not in prompt
    assert manifest["analysts_included"] == ["graham"]
    assert llm_input_pack["metadata"]["tokens_estimated"] <= 6000
    assert manifest["instruction_tokens"] > 0
    assert manifest["schema_tokens"] > 0
    assert manifest["schema_tokens"] <= synthesizer.MAX_SCHEMA_PROMPT_TOKENS
    assert manifest["input_pack_tokens"] > 0
    assert manifest["total_prompt_tokens"] >= manifest["input_pack_tokens"]
    assert manifest["largest_prompt_sections"][0][1] >= manifest["largest_prompt_sections"][-1][1]


def test_committee_prompt_budget_tracks_full_prompt_and_soft_char_warning(tmp_path):
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        payload = _analysis_payload(
            analyst,
            uncertainties=[
                "Free cash flow is missing and owner earnings cannot be assessed." * 8,
                "Capex evidence is incomplete." * 8,
                "More evidence is needed on debt maturity and refinancing." * 8,
            ],
        )
        payload["key_findings"] = [
            ("Long committee synthesis strength detail for prompt budget testing. " * 10).strip(),
            ("Second long strength detail for prompt budget testing. " * 10).strip(),
            ("Third long strength detail for prompt budget testing. " * 10).strip(),
        ]
        payload["key_concerns"] = [
            ("Long committee synthesis concern detail for prompt budget testing. " * 10).strip(),
            ("Second long concern detail for prompt budget testing. " * 10).strip(),
        ]
        payload["financial_warnings_carried_forward"] = [
            "Free cash flow is missing; FCF-based conclusions cannot be assessed.",
            "Capex data is missing.",
            "Basis is unknown.",
            "Share-count comparability is still limited.",
        ]
        payload["financial_assessment"]["financial_interpretation_limits"] = [
            ("Long financial interpretation limit text for total prompt compaction testing. " * 10).strip(),
            "Free cash flow is missing, so owner earnings cannot be assessed.",
            "No new ratios were calculated beyond supplied financial inputs.",
        ]
        _write_analysis(tmp_path, analyst, payload)

    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    included, missing, excluded, warnings = synthesizer._load_inputs()
    committee_input = synthesizer._build_committee_input(
        included=included,
        missing=missing,
        excluded=excluded,
        warning_notes=warnings,
    )

    _prompt, llm_input_pack, manifest = synthesizer._build_compact_prompt_assets(committee_input)
    assert manifest["total_prompt_tokens"] >= manifest["input_pack_tokens"]
    assert manifest["instruction_tokens"] > 0
    assert manifest["schema_tokens"] > 0
    assert manifest["largest_prompt_sections"]
    raw_largest_analyst_blocks = sorted(
        manifest["analyst_block_chars"].items(),
        key=lambda item: item[1],
        reverse=True,
    )
    assert raw_largest_analyst_blocks[0][1] >= raw_largest_analyst_blocks[-1][1]

    manifest["prompt_tokens_after"] = manifest["total_prompt_tokens"]
    manifest["prompt_chars_after"] = synthesizer.SOFT_MAX_PROMPT_CHARS + 10
    manifest["budget_status"] = "pass"
    if (
        manifest["prompt_chars_after"] > synthesizer.SOFT_MAX_PROMPT_CHARS
        and llm_input_pack["metadata"]["tokens_estimated"] <= 6000
    ):
        manifest["budget_status"] = "pass_with_warning"
        manifest["warnings"] = list(manifest.get("warnings") or []) + [
            "Committee synthesis prompt chars exceeded soft target but token budget passed."
        ]

    assert llm_input_pack["metadata"]["tokens_estimated"] <= synthesizer.TARGET_TOTAL_PROMPT_TOKENS
    assert manifest["budget_status"] in {"pass", "pass_with_warning"}
    if manifest["budget_status"] == "pass_with_warning":
        assert "Committee synthesis prompt chars exceeded soft target but token budget passed." in manifest["warnings"]


def test_committee_prompt_schema_and_five_large_analysts_fit_target_budget(tmp_path):
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        payload = _analysis_payload(
            analyst,
            uncertainties=[
                ("Free cash flow is missing and owner earnings cannot be assessed. " * 15).strip(),
                ("Capex evidence is incomplete and share-count comparability remains limited. " * 15).strip(),
            ],
        )
        payload["key_findings"] = [("Positive signal detail " * 40).strip()] * 4
        payload["red_flags"] = [("Risk signal detail " * 40).strip()] * 4
        payload["financial_assessment"]["key_financial_strengths"] = [("Financial strength detail " * 35).strip()] * 4
        payload["financial_assessment"]["key_financial_concerns"] = [("Financial concern detail " * 35).strip()] * 4
        payload["financial_assessment"]["financial_interpretation_limits"] = [("Interpretation limit detail " * 35).strip()] * 4
        payload["financial_warnings_carried_forward"] = [
            "Free cash flow is missing; FCF-based conclusions cannot be assessed.",
            "Capex data is missing.",
            "Basis is unknown.",
            "Payables are missing.",
        ]
        _write_analysis(tmp_path, analyst, payload)

    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    included, missing, excluded, warnings = synthesizer._load_inputs()
    committee_input = synthesizer._build_committee_input(
        included=included,
        missing=missing,
        excluded=excluded,
        warning_notes=warnings,
    )
    _prompt, _pack, manifest = synthesizer._build_compact_prompt_assets(committee_input)

    assert len(committee_input["analysts"]) == 5
    assert manifest["schema_tokens"] <= synthesizer.MAX_SCHEMA_PROMPT_TOKENS
    assert all(
        estimate_tokens(json.dumps(block, ensure_ascii=False)) <= synthesizer.MAX_ANALYST_BLOCK_TOKENS
        for block in committee_input["analysts"]
    )


def test_ultra_compact_fallback_produces_minimal_analyst_digest(tmp_path):
    payload = _analysis_payload("graham", uncertainties=[("Need more evidence. " * 50).strip()])
    payload["key_findings"] = [("Long positive signal " * 40).strip()] * 4
    payload["red_flags"] = [("Long risk signal " * 40).strip()] * 4
    payload["financial_warnings_carried_forward"] = [
        "Free cash flow is missing; FCF-based conclusions cannot be assessed.",
        "Capex data is missing.",
        "Basis is unknown.",
    ]
    _write_analysis(tmp_path, "graham", payload)

    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    included, missing, excluded, warnings = synthesizer._load_inputs()
    committee_input = synthesizer._build_committee_input(
        included=included,
        missing=missing,
        excluded=excluded,
        warning_notes=warnings,
    )
    compacted, _warnings = synthesizer._apply_ultra_compact_fallback(committee_input)
    block = compacted["analysts"][0]

    assert set(block.keys()) <= {"analyst", "rating", "view", "risks", "warnings", "unknowns"}
    assert len(block.get("risks", [])) <= 1
    assert len(block.get("warnings", [])) <= 3
    assert len(block.get("unknowns", [])) <= 1


def test_committee_final_prompt_compaction_preserves_all_analysts_and_major_financial_warnings(tmp_path):
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        payload = _analysis_payload(
            analyst,
            uncertainties=[
                "Free cash flow is missing; owner earnings cannot be assessed." * 12,
                "Capex evidence is incomplete and debt maturity detail is still thin." * 12,
            ],
        )
        payload["key_findings"] = [("Doctrinal observation " * 30).strip()] * 4
        payload["red_flags"] = [("Risk observation " * 30).strip()] * 4
        payload["financial_warnings_carried_forward"] = [
            "Free cash flow is missing; FCF-based conclusions cannot be assessed.",
            "Capex data is missing.",
            "Basis is unknown.",
        ]
        payload["financial_assessment"]["missing_financial_data"] = [
            ("Missing-data detail " * 25).strip(),
            "Share-count comparability is still limited.",
        ]
        _write_analysis(tmp_path, analyst, payload)

    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    included, missing, excluded, warnings = synthesizer._load_inputs()
    committee_input = synthesizer._build_committee_input(
        included=included,
        missing=missing,
        excluded=excluded,
        warning_notes=warnings,
    )

    compacted, compact_warnings = synthesizer._apply_final_prompt_compaction(committee_input)

    assert [item["analyst"] for item in compacted["analysts"]] == ["graham", "buffett", "fisher", "munger", "lynch"]
    assert "Final prompt compaction applied using total prompt tokens." in compact_warnings
    for analyst_block in compacted["analysts"]:
        assert len(json.dumps(analyst_block, ensure_ascii=False)) <= synthesizer.FINAL_PROMPT_ANALYST_CHAR_BUDGET
        warning_blob = " ".join(analyst_block.get("financial_warnings", [])).lower()
        assert "fcf_missing" in warning_blob or "capex_missing" in warning_blob


def test_committee_includes_analysts_with_stale_fail_status_when_final_evidence_ids_are_clean(tmp_path):
    _write_pcim_with_evidence_ids(
        tmp_path,
        "polymatech",
        ["ev_graham_1", "ev_buffett_1", "ev_fisher_1", "ev_munger_1", "ev_lynch_1"],
    )
    _write_analysis(tmp_path, "graham", _analysis_payload("graham"))
    for analyst in ("buffett", "fisher", "munger", "lynch"):
        payload = _analysis_payload(
            analyst,
            status="fail",
            warnings=["old grounding failure from removed section-name evidence id"],
            evidence_ids=[f"ev_{analyst}_1"],
        )
        payload["evidence_id_normalization"]["unresolved_ids"] = [
            "governance_and_incentive_inputs"
        ]
        payload["evidence_id_normalization"]["removed_invalid_ids"] = [
            {
                "path": "$.evidence_ids",
                "invalid_id": "governance_and_incentive_inputs",
                "reason": "pcim_section_name",
            }
        ]
        _write_analysis(tmp_path, analyst, payload)

    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    included, missing, excluded, warning_notes = synthesizer._load_inputs()

    assert [payload["doctrine_id"] for payload in included] == [
        "graham",
        "buffett",
        "fisher",
        "munger",
        "lynch",
    ]
    assert missing == []
    assert excluded == []
    assert any("stale evidence grounding failure metadata" in item for item in warning_notes)


def test_committee_finalize_strips_internal_fields_and_writes_diagnostics(tmp_path):
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        _write_analysis(tmp_path, analyst, _analysis_payload(analyst))
    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    included, missing, excluded, _warnings = synthesizer._load_inputs()
    payload = _committee_payload_dict()
    payload["grounding_status"] = "warning"
    payload["validation_status"] = "warning"
    payload["internal_debug"] = {"token_budget": 6000}
    payload["areas_of_agreement"][0]["source_chunk"] = "raw excerpt"
    payload["financial_committee_view"]["source_artifacts"] = ["financial_quality_summary.json"]

    finalized = synthesizer._finalize_payload(
        payload,
        included=included,
        missing=missing,
        excluded=excluded,
    )
    serialized = json.dumps(finalized, ensure_ascii=False)
    assert "grounding_status" not in serialized
    assert "validation_status" not in serialized
    assert "source_chunk" not in serialized
    assert "internal_debug" not in serialized
    assert "source_artifacts" not in serialized

    diagnostics = json.loads(synthesizer.diagnostics_path.read_text(encoding="utf-8"))
    stripped_paths = {item["path"] for item in diagnostics["stripped_fields"]}
    assert "$.grounding_status" in stripped_paths
    assert "$.validation_status" in stripped_paths
    assert "$.internal_debug" in stripped_paths
    assert "$.areas_of_agreement[0].source_chunk" in stripped_paths
    assert "$.financial_committee_view.source_artifacts" in stripped_paths
    assert diagnostics["field_shapes"]["areas_of_agreement"] == "list[dict]"
    assert "strongest_positive_signals" in diagnostics["object_list_fields_checked"]


def test_committee_finalize_rephrases_artifact_terms_for_brief_source(tmp_path):
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        _write_analysis(tmp_path, analyst, _analysis_payload(analyst))
    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    included, missing, excluded, _warnings = synthesizer._load_inputs()
    payload = _committee_payload_dict()
    payload["financial_committee_view"]["missing_financial_data"] = [
        "normalized_fundamentals.json: Artifact missing.",
        "financial_validation_report.json: Artifact missing.",
        "financial_reconciliation_report.json: Artifact missing.",
        "financial artifacts do not cover all company years",
        "Existing financial_audit_report.json is stale relative to financial_ratios.json.",
    ]

    finalized = synthesizer._finalize_payload(
        payload,
        included=included,
        missing=missing,
        excluded=excluded,
    )

    serialized = json.dumps(finalized, ensure_ascii=False)
    assert "Artifact" not in serialized
    assert "artifact" not in serialized
    missing_data = finalized["financial_committee_view"]["missing_financial_data"]
    assert "Normalized financial fundamentals are missing." in missing_data
    assert "Financial validation output is missing." in missing_data
    assert "Financial reconciliation output is missing." in missing_data
    assert "Financial data does not cover all company years" in missing_data
    assert any("Financial audit output may be stale" in item for item in missing_data)
    validate_committee_brief_source(finalized)

    diagnostics = json.loads(synthesizer.diagnostics_path.read_text(encoding="utf-8"))
    original_text = json.dumps(diagnostics["rewritten_strings"], ensure_ascii=False)
    assert "Artifact missing" in original_text
    assert "financial artifacts do not cover all company years" in original_text


def test_committee_validator_accepts_grounded_critical_unknown_with_source_ids():
    payload = _committee_payload_dict()
    payload["critical_unknowns"] = [
        {
            "unknown": "graham wants more cash flow evidence",
            "raised_by": ["graham"],
            "why_it_matters": "Needed.",
            "source_uncertainty_ids": ["graham_u001"],
        }
    ]
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
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
    )
    assert parsed["critical_unknowns"][0]["source_uncertainty_ids"] == ["graham_u001"]
    assert parsed["critical_unknowns"][0]["raised_by"] == ["graham"]
    assert parsed["critical_unknowns"][0]["evidence_limit"] == "Grounded in analyst uncertainty registry."


def test_committee_validator_derives_critical_unknown_raised_by_from_source_ids():
    payload = _committee_payload_dict()
    payload["critical_unknowns"] = [
        {
            "uncertainty": "graham wants more cash flow evidence",
            "importance": "Needed for downside assessment.",
            "source_uncertainty_ids": ["graham_u001"],
        }
    ]
    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
    )

    assert parsed["critical_unknowns"][0]["raised_by"] == ["graham"]
    assert parsed["critical_unknowns"][0]["why_it_matters"] == "Needed for downside assessment."
    assert parsed["critical_unknowns"][0]["source_uncertainty_ids"] == ["graham_u001"]


def test_committee_validator_derives_critical_unknown_source_ids_from_raised_by():
    payload = _committee_payload_dict()
    payload["critical_unknowns"] = [
        {
            "issue": "buffett wants more cash flow evidence",
            "raised_by": ["buffett"],
            "rationale": "Needed for business quality assessment.",
            "limitation": "Analyst uncertainty registry only.",
        }
    ]
    parsed = validate_committee_output(
        payload,
        company="polymatech",
        included_analysts=["graham", "buffett", "fisher"],
        missing_analysts=["lynch"],
        excluded_analysts=["munger"],
        allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
        analyst_uncertainties={},
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
    )

    assert parsed["critical_unknowns"][0]["raised_by"] == ["buffett"]
    assert parsed["critical_unknowns"][0]["source_uncertainty_ids"] == ["buffett_u001"]
    assert parsed["critical_unknowns"][0]["evidence_limit"] == "Analyst uncertainty registry only."


def test_committee_validator_normalizes_string_critical_unknown_via_registry():
    payload = _committee_payload_dict()
    payload["critical_unknowns"] = ["graham wants more cash flow evidence"]
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
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
    )
    assert parsed["critical_unknowns"][0]["source_uncertainty_ids"] == [
        "graham_u001",
        "buffett_u001",
        "fisher_u001",
    ]
    assert parsed["critical_unknowns"][0]["evidence_limit"] == "Grounded in analyst uncertainty registry."
    assert any("critical_unknowns string entry was normalized" in item for item in parsed["schema_warnings"])


def test_committee_validator_rejects_unmatched_string_critical_unknown():
    payload = _committee_payload_dict()
    payload["critical_unknowns"] = ["A brand new unknown nobody raised"]

    with pytest.raises(ValueError, match="critical_unknowns must be grounded in analyst uncertainty registry"):
        validate_committee_output(
            payload,
            company="polymatech",
            included_analysts=["graham", "buffett", "fisher"],
            missing_analysts=["lynch"],
            excluded_analysts=["munger"],
            allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
            analyst_uncertainties={},
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
        )


def test_committee_validator_rejects_invalid_critical_unknown_analyst():
    payload = _committee_payload_dict()
    payload["critical_unknowns"] = [
        {
            "unknown": "graham wants more cash flow evidence",
            "raised_by": ["porter"],
            "why_it_matters": "Needed.",
        }
    ]

    with pytest.raises(ValueError, match="invalid analysts"):
        validate_committee_output(
            payload,
            company="polymatech",
            included_analysts=["graham", "buffett", "fisher"],
            missing_analysts=["lynch"],
            excluded_analysts=["munger"],
            allowed_evidence_ids=["ev_graham_1", "ev_buffett_1", "ev_fisher_1"],
            analyst_uncertainties={},
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
        )


def test_committee_validator_rejects_ungrounded_critical_unknown():
    payload = _committee_payload_dict()
    payload["critical_unknowns"] = [
        {
            "unknown": "A brand new unknown nobody raised",
            "raised_by": ["graham"],
            "why_it_matters": "Needed.",
            "source_uncertainty_ids": ["graham_u001"],
        }
    ]
    with pytest.raises(ValueError, match="critical_unknowns must be grounded in analyst uncertainty registry"):
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
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
        )


def test_committee_validator_rejects_fake_source_uncertainty_id():
    payload = _committee_payload_dict()
    payload["critical_unknowns"] = [
        {
            "unknown": "graham wants more cash flow evidence",
            "raised_by": ["graham"],
            "why_it_matters": "Needed.",
            "source_uncertainty_ids": ["graham_u999"],
        }
    ]
    with pytest.raises(ValueError, match="source_uncertainty_ids not present"):
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
            included_analyst_payloads=[
                _analysis_payload("graham"),
                _analysis_payload("buffett"),
                _analysis_payload("fisher"),
            ],
            mode="final",
        )


def test_committee_validator_generates_deterministic_critical_unknowns_when_missing():
    payload = _committee_payload_dict()
    payload["critical_unknowns"] = []
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
        included_analyst_payloads=[
            _analysis_payload("graham"),
            _analysis_payload("buffett"),
            _analysis_payload("fisher"),
        ],
        mode="final",
    )
    assert parsed["critical_unknowns"]
    assert all(item["source_uncertainty_ids"] for item in parsed["critical_unknowns"])
    assert any("critical_unknowns generated deterministically" in item for item in parsed["schema_warnings"])


def test_committee_cleanup_canonicalizes_nested_ids_and_warning_counts(tmp_path, monkeypatch):
    _write_pcim_with_evidence_ids(
        tmp_path,
        "polymatech",
            [
                "ev_fy24_business_classification_json_business_dna_by_year_fy24_export",
                "ev_graham_1",
                "ev_fy25_business_classification_json_business_dna_by_year_fy25_manufacturing",
                "ev_fisher_1",
                "ev_munger_1",
                "ev_lynch_1",
            ],
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
        "financial_committee_view": _financial_committee_view(),
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
        [
            "ev_fy24_management_summary_json_init_00007",
            "ev_graham_1",
            "ev_buffett_1",
            "ev_fisher_1",
            "ev_lynch_1",
        ],
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
        "financial_committee_view": _financial_committee_view(),
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


def test_committee_finalize_applies_canonical_normalization_boundary(tmp_path, monkeypatch):
    for analyst in ("graham", "buffett", "fisher", "munger", "lynch"):
        _write_analysis(tmp_path, analyst, _analysis_payload(analyst))
    synthesizer = InvestmentCommitteeSynthesizer(
        company="polymatech",
        companies_root=tmp_path / "companies",
    )
    included, missing, excluded, _warnings = synthesizer._load_inputs()
    payload = _committee_payload_dict()
    payload["areas_of_disagreement"][0]["disagreement_type"] = "risk concern"

    original_validate = validate_committee_output
    calls = []

    def _wrapped_validate(*args, **kwargs):
        payload_arg = args[0]
        if isinstance(payload_arg, dict):
            calls.append(payload_arg["areas_of_disagreement"][0]["disagreement_type"])
        return original_validate(*args, **kwargs)

    monkeypatch.setattr(
        "intelligence.investor_panel.committee_synthesizer.validate_committee_output",
        _wrapped_validate,
    )

    finalized = synthesizer._finalize_payload(
        payload,
        included=included,
        missing=missing,
        excluded=excluded,
    )

    assert calls
    assert all(call == "risk_weighting_difference" for call in calls)
    assert finalized["areas_of_disagreement"][0]["disagreement_type"] == "risk_weighting_difference"


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
        "financial_committee_view": _financial_committee_view(),
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
            "financial_committee_view": _financial_committee_view(),
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
            included_analyst_payloads=[_analysis_payload("graham")],
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
    _write_analysis(
        tmp_path,
        "munger",
        _analysis_payload("munger", status="fail", evidence_ids=["risk_inputs"]),
    )

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
    if saved["areas_of_disagreement"]:
        assert "disagreement_type" in saved["areas_of_disagreement"][0]
