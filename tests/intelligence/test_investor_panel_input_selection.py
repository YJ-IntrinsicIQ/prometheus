import json
from pathlib import Path

from intelligence.investor_panel import runner as panel_runner
from intelligence.investor_panel.committee_synthesizer import InvestmentCommitteeSynthesizer
from intelligence.investor_panel.doctrine_registry import InvestorDoctrineRegistry
from intelligence.investor_panel.runner import _build_compact_prompt, _build_prompt_input_pack, enforce_section_char_cap


def _write_pcim(base_dir: Path, company: str) -> Path:
    company_memory_dir = base_dir / "companies" / company / "company_memory"
    company_memory_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "contract_version": "1.0",
        "company": company,
        "business_understanding": {
            "latest_business_view": {
                "year": "fy25",
                "business_model": {"business_summary": "Synthetic platform business", "evidence_ids": ["ev_bu_1"]},
            }
        },
        "financial_strength_inputs": {
            "capital_allocation_by_year": [{"year": "fy25", "items": [{"value": "Disciplined capex", "evidence_ids": ["ev_cap_1"]}]}],
        },
        "financial_fundamentals_inputs": {
            "by_year": [{"year": "fy25", "key_metrics": [{"field": "net_worth", "value_crore": 55.0, "source_year": "fy25", "source_artifact": "normalized_fundamentals.json"}]}],
            "warnings": [],
        },
        "cash_conversion_inputs": {
            "metrics": [{"metric": "cfo", "series": [{"year": "fy25", "value": 18.0, "source_artifact": "financial_trends.json"}]}],
            "warnings": [],
            "source_artifact": "financial_quality_summary.json",
        },
        "balance_sheet_strength_inputs": {
            "metrics": [{"metric": "debt_to_equity", "series": [{"year": "fy25", "value": 0.2, "source_artifact": "financial_trends.json"}]}],
            "warnings": [],
            "source_artifact": "financial_quality_summary.json",
        },
        "per_share_inputs": {
            "metrics": [{"metric": "book_value_per_share", "series": [{"year": "fy25", "value": 42.0, "source_artifact": "financial_trends.json"}]}],
            "warnings": [],
            "source_artifact": "financial_trends.json",
        },
        "financial_driver_inputs": {
            "attributions": [{"metric": "revenue", "possible_driver": "Platform expansion", "source_artifacts": ["financial_driver_attribution.json"], "evidence_ids": ["ev_fin_driver_1"]}],
            "warnings": [],
            "limitations": [],
            "source_artifact": "financial_driver_attribution.json",
        },
        "risk_inputs": {
            "risk_by_year": [{"year": "fy25", "items": [{"value": "Customer concentration", "evidence_ids": ["ev_risk_1"]}]}],
        },
        "governance_and_incentive_inputs": {
            "related_party_and_control_items_by_year": [{"year": "fy25", "items": [{"value": "Related-party advance", "evidence_ids": ["ev_gov_1"]}]}],
        },
        "capital_allocation_inputs": {
            "capital_allocation_by_year": [{"year": "fy25", "items": [{"value": "Reinvest in platform", "evidence_ids": ["ev_cap_1"]}]}],
        },
        "multi_year_inputs": {
            "years_covered": ["fy24", "fy25"],
            "limitations": ["Only two synthetic years are available."],
        },
        "evidence_map": {
            "financial_strength_inputs": ["ev_cap_1"],
            "financial_fundamentals_inputs": ["ev_cap_1"],
            "cash_conversion_inputs": ["ev_cap_1"],
            "balance_sheet_strength_inputs": ["ev_cap_1"],
            "per_share_inputs": ["ev_cap_1"],
            "financial_driver_inputs": ["ev_fin_driver_1"],
            "risk_inputs": ["ev_risk_1"],
            "governance_and_incentive_inputs": ["ev_gov_1"],
            "capital_allocation_inputs": ["ev_cap_1"],
            "multi_year_inputs": ["ev_cap_1"],
        },
        "uncertainty_missing_data": {"incomplete_years": [], "missing_sections": [], "missing_items": []},
    }
    path = company_memory_dir / "pcim_v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_analyst(panel_dir: Path, analyst: str) -> None:
    payload = {
        "doctrine_id": analyst,
        "company": "syntheticco",
        "pcim_version": "1.0",
        "pcim_source": "companies/syntheticco/company_memory/pcim_v1.json",
        "analysis_mode": "llm_reasoning_v1",
        "sections_consumed": ["risk_inputs"],
        "assessment": {"summary": f"{analyst} assessment"},
        "rating": "mixed",
        "key_findings": [{"finding": "Synthetic finding", "evidence_ids": ["ev_shared_1"]}],
        "red_flags": [{"flag": "Synthetic flag", "severity": "medium", "evidence_ids": ["ev_shared_1"]}],
        "open_uncertainties": [{"uncertainty": "Synthetic uncertainty", "evidence_ids": []}],
        "evidence_ids": ["ev_shared_1"],
        "historical_context_used": True,
        "years_considered": ["fy24", "fy25"],
        "supporting_pcim_sections": ["risk_inputs"],
        "financial_assessment": {
            "financials_used": True,
            "basis_used": "consolidated",
            "key_financial_strengths": ["Synthetic strength."],
            "key_financial_concerns": ["Synthetic concern."],
            "financial_red_flags": ["Synthetic flag."],
            "missing_financial_data": ["Synthetic missing."],
            "financial_interpretation_limits": ["Synthetic limit."],
            "financial_warnings_carried_forward": ["Synthetic warning."],
        },
        "financial_sections_consumed": ["risk_inputs"],
        "financial_warnings_carried_forward": ["Synthetic warning."],
        "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
        "evidence_grounding_status": "pass",
        "evidence_grounding_warnings": [],
        "reasoning_limits": ["Synthetic limit."],
        "user_facing_brief": {
            "title": f"{analyst.title()} brief",
            "lens": "Synthetic lens.",
            "what_looks_good": ["Synthetic good."],
            "what_needs_caution": ["Synthetic caution."],
            "what_is_missing": ["Synthetic missing."],
            "bottom_line": "Synthetic bottom line.",
        },
        "generated_at": "2026-07-14T00:00:00Z",
    }
    (panel_dir / f"{analyst}_analysis.json").write_text(json.dumps(payload), encoding="utf-8")


def test_investor_panel_input_pack_contains_only_declared_pcim_sections(tmp_path):
    pcim_path = _write_pcim(tmp_path, "syntheticco")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("graham")

    prompt, compact_pcim, _stats, limits_used, input_compacted, budget_report = _build_compact_prompt(
        doctrine=doctrine,
        company="syntheticco",
        pcim_path=pcim_path,
        pcim=pcim,
        sections=list(doctrine["evidence_required_from_pcim"]),
    )
    llm_input_pack = _build_prompt_input_pack(
        company="syntheticco",
        doctrine=doctrine,
        pcim_path=pcim_path,
        compact_pcim=compact_pcim,
        allowed_sections=list(doctrine["evidence_required_from_pcim"]),
        limits_used=limits_used,
        input_compacted=input_compacted,
    )

    payload = json.dumps(llm_input_pack, ensure_ascii=False)
    assert "financial_strength_inputs" in payload
    assert "risk_inputs" in payload
    assert "governance_and_incentive_inputs" in payload
    assert "capital_allocation_inputs" in payload
    assert "multi_year_inputs" in payload
    assert "business_understanding" not in payload
    assert '"source_chunk":' not in payload
    assert "Selected compact PCIM sections:" in prompt
    assert len(prompt) <= 28000
    assert budget_report["budget_status"] in {"pass", "pass_with_warning"}


def test_investor_panel_prompt_compaction_recursively_trims_nested_payloads(tmp_path):
    pcim_path = _write_pcim(tmp_path, "syntheticco")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    very_long = "Oversized nested text for investor panel prompt compaction. " * 80
    pcim["risk_inputs"] = {
        "risk_by_year": [
            {
                "year": "fy25",
                "items": [
                    {
                        "value": f"Nested risk {idx}",
                        "source_chunk": very_long,
                        "raw_text": very_long,
                        "evidence_ids": [f"ev_nested_{idx}_{j}" for j in range(12)],
                        "evidence_references": [
                            {
                                "page": idx,
                                "source_chunk": very_long,
                                "source_artifact": "company_intelligence.json",
                                "evidence_ids": [f"ev_nested_{idx}_0"],
                            }
                        ],
                    }
                    for idx in range(12)
                ],
            }
        ]
    }
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("graham")

    prompt, compact_pcim, _stats, limits_used, input_compacted, budget_report = _build_compact_prompt(
        doctrine=doctrine,
        company="syntheticco",
        pcim_path=pcim_path,
        pcim=pcim,
        sections=list(doctrine["evidence_required_from_pcim"]),
    )
    llm_input_pack = _build_prompt_input_pack(
        company="syntheticco",
        doctrine=doctrine,
        pcim_path=pcim_path,
        compact_pcim=compact_pcim,
        allowed_sections=list(doctrine["evidence_required_from_pcim"]),
        limits_used=limits_used,
        input_compacted=input_compacted,
    )

    rendered = json.dumps(
        {
            "facts": llm_input_pack["facts"],
            "observations": llm_input_pack["observations"],
            "limitations": llm_input_pack["limitations"],
            "evidence_ids": llm_input_pack["evidence_ids"],
        },
        ensure_ascii=False,
    )
    assert len(prompt) <= 28000
    assert '"source_chunk":' not in rendered
    assert '"raw_text":' not in rendered
    assert "evidence_references" not in rendered
    assert llm_input_pack["metadata"]["tokens_estimated"] <= 7000
    assert panel_runner.COMPACTION_REASONING_LIMIT in llm_input_pack["limitations"] or input_compacted
    assert budget_report["pack_tokens_after"] <= budget_report["token_budget"]


def test_soft_prompt_char_limit_becomes_warning_not_failure(tmp_path, monkeypatch):
    pcim_path = _write_pcim(tmp_path, "syntheticco")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    very_long = "Long but still token-safe business context for soft char warning. " * 150
    pcim["risk_inputs"] = {
        "risk_by_year": [
            {
                "year": "fy25",
                "items": [
                    {
                        "value": very_long,
                        "evidence_ids": ["ev_risk_1"],
                    }
                ],
            }
        ]
    }
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("graham")
    monkeypatch.setenv("INVESTOR_PANEL_MAX_PROMPT_CHARS", "8200")

    prompt, _compact_pcim, _stats, _limits_used, _input_compacted, budget_report = _build_compact_prompt(
        doctrine=doctrine,
        company="syntheticco",
        pcim_path=pcim_path,
        pcim=pcim,
        sections=list(doctrine["evidence_required_from_pcim"]),
    )

    assert budget_report["prompt_tokens_after"] <= budget_report["token_budget"]
    assert budget_report["pack_tokens_after"] <= budget_report["token_budget"]
    assert budget_report["budget_status"] == "pass_with_warning"
    assert "prompt_chars exceeded soft target but token budget passed" in budget_report["warnings"]
    assert budget_report["raw_largest_sections"]
    assert budget_report["compacted_largest_sections"]
    assert "Selected compact PCIM sections:" in prompt


def test_true_over_token_budget_still_fails(tmp_path, monkeypatch):
    pcim_path = _write_pcim(tmp_path, "syntheticco")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    very_long = "Oversized nested text for strict token budget failure. " * 250
    pcim["risk_inputs"] = {
        "risk_by_year": [
            {
                "year": "fy25",
                "items": [
                    {
                        "value": very_long,
                        "evidence_ids": ["ev_risk_1"],
                    }
                ],
            }
        ]
    }
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("graham")
    monkeypatch.setenv("INVESTOR_PANEL_TOTAL_PROMPT_BUDGET_TOKENS", "100")
    monkeypatch.setenv("INVESTOR_PANEL_HARD_MAX_PROMPT_TOKENS", "100")
    monkeypatch.setenv("PROMETHEUS_LLM_BUDGET_INVESTOR_PANEL_ANALYST", "100")

    try:
        _build_compact_prompt(
            doctrine=doctrine,
            company="syntheticco",
            pcim_path=pcim_path,
            pcim=pcim,
            sections=list(doctrine["evidence_required_from_pcim"]),
        )
    except ValueError as exc:
        message = str(exc)
        assert "Investor panel prompt remains above budget after compaction" in message
        assert "raw_largest_sections=" in message
        assert "compacted_largest_sections=" in message
    else:
        raise AssertionError("Expected strict token budget failure")


def test_multi_year_inputs_hard_cap_is_enforced(tmp_path):
    pcim_path = _write_pcim(tmp_path, "syntheticco")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    large_text = "Historical context with repeated management commentary and capital allocation detail. " * 250
    pcim["multi_year_inputs"] = {
        "years_covered": ["fy22", "fy23", "fy24", "fy25"],
        "business_dna_evolution": {
            "continued_themes": [large_text for _ in range(8)],
            "source_artifacts": ["strategy_timeline.json", "capital_allocation_timeline.json"],
        },
        "management_consistency": {
            "consistency_observations": [{"value": large_text, "year": "fy25"} for _ in range(10)],
            "limitations": [large_text],
        },
        "capital_allocation_pattern": {
            "top_observations": [{"value": large_text, "year": "fy24"} for _ in range(10)],
        },
        "warnings": [large_text],
        "limitations": [large_text],
    }
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("graham")

    _prompt, compact_pcim, stats, _limits_used, _input_compacted, _budget_report = _build_compact_prompt(
        doctrine=doctrine,
        company="syntheticco",
        pcim_path=pcim_path,
        pcim=pcim,
        sections=list(doctrine["evidence_required_from_pcim"]),
    )

    serialized = json.dumps(compact_pcim["multi_year_inputs"], ensure_ascii=False)
    assert len(serialized) <= 4000
    assert len(compact_pcim["multi_year_inputs"]["patterns"]) <= 4
    assert all(len(json.dumps(pattern, ensure_ascii=False)) <= 500 for pattern in compact_pcim["multi_year_inputs"]["patterns"])
    assert "source_chunk" not in serialized
    assert stats["multi_year_inputs"]["final_chars"] <= stats["multi_year_inputs"]["section_cap"]


def test_capital_allocation_inputs_hard_cap_is_enforced_without_source_chunks():
    large_text = "Capital allocation commentary with repeated expansion, financing, and payout detail. " * 120
    value = {
        "capital_allocation_by_year": [
            {
                "year": "fy25",
                "items": [
                    {
                        "value": large_text,
                        "source_chunk": large_text,
                        "source_artifact": "capital_allocation_timeline.json",
                    }
                    for _ in range(14)
                ],
            }
        ],
        "warnings": [large_text],
        "limitations": [large_text],
    }

    compacted, was_compacted, _original_chars, final_chars, _dropped_items_count, warnings = enforce_section_char_cap(
        "capital_allocation_inputs",
        value,
        3000,
        "buffett",
    )

    serialized = json.dumps(compacted, ensure_ascii=False)
    assert was_compacted
    assert final_chars <= 3000
    assert "source_chunk" not in serialized
    assert "company_controlled_actions" in compacted or compacted.get("section_compacted") is True
    assert warnings


def test_financial_quality_inputs_hard_cap_is_enforced():
    large_text = "Financial quality detail with extra narrative around cash conversion and return quality. " * 120
    value = {
        "basis_used": "consolidated",
        "strengths": [large_text for _ in range(12)],
        "concerns": [large_text for _ in range(12)],
        "missing_data": [large_text for _ in range(12)],
        "investor_questions": [large_text for _ in range(12)],
        "metrics": [{"metric": f"metric_{idx}", "series": [{"year": "fy25", "value": idx * 1.0}]} for idx in range(20)],
        "summary": large_text,
        "warnings": [large_text],
    }

    compacted, was_compacted, _original_chars, final_chars, _dropped_items_count, _warnings = enforce_section_char_cap(
        "financial_quality_inputs",
        value,
        3000,
        "graham",
    )

    serialized = json.dumps(compacted, ensure_ascii=False)
    assert was_compacted
    assert final_chars <= 3000
    assert len(compacted.get("strengths", [])) <= 5
    assert len(compacted.get("concerns", [])) <= 5
    assert len(compacted.get("missing_data", [])) <= 5
    assert len(compacted.get("investor_questions", [])) <= 5
    assert len(compacted.get("key_metrics", [])) <= 8
    assert "raw_financial_tables" not in serialized


def test_emergency_section_replacement_is_used_when_needed():
    huge_text = "X" * 10000
    value = {
        "warnings": [huge_text],
        "limitations": [huge_text],
        "nested": {"summary": huge_text, "source_artifact": "pcim_v1.json"},
    }

    compacted, was_compacted, _original_chars, final_chars, _dropped_items_count, warnings = enforce_section_char_cap(
        "business_understanding",
        value,
        220,
        "buffett",
    )

    assert was_compacted
    assert final_chars <= 220
    assert compacted["section_compacted"] is True
    assert compacted["reason"] == "Section exceeded investor panel budget."
    assert compacted["limitations"]
    assert warnings


def test_committee_synthesis_prompt_is_isolated_to_analyst_outputs(tmp_path):
    company_root = tmp_path / "companies" / "syntheticco" / "company_memory" / "investor_panel"
    company_root.mkdir(parents=True, exist_ok=True)
    _write_analyst(company_root, "graham")
    _write_analyst(company_root, "buffett")

    synthesizer = InvestmentCommitteeSynthesizer(company="syntheticco", companies_root=tmp_path / "companies")
    included, missing, excluded, warnings = synthesizer._load_inputs()
    committee_input = synthesizer._build_committee_input(
        included=included,
        missing=missing,
        excluded=excluded,
        warning_notes=warnings,
    )
    prompt = synthesizer._build_prompt(committee_input)

    assert "graham" in prompt
    assert "buffett" in prompt
    assert "pcim_v1.json" not in prompt
    assert '"source_chunk":' not in prompt
    assert "run_summary" not in prompt
