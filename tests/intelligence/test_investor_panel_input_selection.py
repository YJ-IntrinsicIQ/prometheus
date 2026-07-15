import json
from pathlib import Path

from intelligence.investor_panel.committee_synthesizer import InvestmentCommitteeSynthesizer
from intelligence.investor_panel.doctrine_registry import InvestorDoctrineRegistry
from intelligence.investor_panel.runner import _build_compact_prompt, _build_prompt_input_pack


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

    prompt, compact_pcim, _stats, limits_used, input_compacted = _build_compact_prompt(
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
