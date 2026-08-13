import json
from pathlib import Path

from intelligence.investor_panel.company_memory_context import build_company_memory_context
from intelligence.investor_panel.doctrine_registry import InvestorDoctrineRegistry
from intelligence.investor_panel.runner import _build_compact_prompt, _build_prompt_input_pack


def _write_company_memory(base_dir: Path, company: str) -> Path:
    company_root = base_dir / "companies" / company
    memory_root = company_root / "company_memory"
    (memory_root / "management_commitments").mkdir(parents=True, exist_ok=True)
    (memory_root / "projects").mkdir(parents=True, exist_ok=True)
    (memory_root / "capacity").mkdir(parents=True, exist_ok=True)
    (memory_root / "financials").mkdir(parents=True, exist_ok=True)
    (memory_root / "management_quality").mkdir(parents=True, exist_ok=True)

    (memory_root / "company_memory_index.json").write_text(
        json.dumps({"company": company, "usable_years": ["fy24", "fy25"], "ordered_years": ["fy24", "fy25"]}),
        encoding="utf-8",
    )
    (memory_root / "management_commitments" / "management_commitments.json").write_text(
        json.dumps(
            {
                "company": company,
                "commitment_count": 1,
                "status_counts": {"Delivered": 1},
                "category_counts": {"Capacity": 1},
                "commitments": [
                    {
                        "id": "MC-0001",
                        "topic": "Capacity expansion",
                        "category": "Capacity",
                        "announcement_period": "fy24",
                        "normalized_commitment": "Expand capacity.",
                        "status": "Delivered",
                        "delivery_assessment": "Delivered",
                        "investor_implication": "Execution appears on schedule.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (memory_root / "management_commitments" / "commitment_timeline.json").write_text(
        json.dumps(
            {
                "company": company,
                "timeline": [
                    {
                        "id": "MC-0001",
                        "topic": "Capacity expansion",
                        "latest_status": "Delivered",
                        "events": [{"period": "fy24", "event_type": "completion", "status": "Delivered"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (memory_root / "projects" / "project_assessments.json").write_text(
        json.dumps(
            {
                "company": company,
                "assessments": [
                    {
                        "project_id": "PJ-0001",
                        "project_name": "New plant",
                        "execution_status": "commissioned",
                        "conviction_impact": "strengthened",
                        "what_changed": "The plant moved to commissioning.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (memory_root / "capacity" / "capacity_assessments.json").write_text(
        json.dumps(
            {
                "company": company,
                "assessments": [
                    {
                        "capacity_id": "CP-0001",
                        "capacity_name": "New production line",
                        "execution_status": "installed",
                        "utilization_status": "unclear",
                        "conviction_impact": "unchanged",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (memory_root / "financials" / "financial_memory_summary.json").write_text(
        json.dumps(
            {
                "company": company,
                "status": "warning",
                "years_covered": ["fy24", "fy25"],
                "basis_used": "consolidated",
                "summary": "Owner earnings improved but share count remains a watch item.",
                "key_strengths": ["Owner earnings improved."],
                "key_concerns": ["Share-count comparability remains a watch item."],
                "missing_data": ["Per-share history is limited."],
                "investor_questions": ["Has per-share compounding improved?"],
                "warnings": ["Limited period coverage."],
                "limitations": ["Two-year history only."],
            }
        ),
        encoding="utf-8",
    )
    (memory_root / "management_quality" / "management_quality_summary.json").write_text(
        json.dumps(
            {
                "company_slug": company,
                "overall_view": "Management execution appears dependable.",
                "overall_direction": "improving",
                "strongest_dimension": "execution_discipline",
                "weakest_dimension": "risk_handling",
                "investor_implication": "Execution appears dependable enough to support conviction.",
                "what_strengthened_conviction": [{"dimension": "execution_discipline", "summary": "Repeated delivery."}],
                "what_weakened_conviction": [{"dimension": "risk_handling", "summary": "Risk evidence remains thin."}],
                "what_remains_unproven": [{"dimension": "risk_handling", "summary": "Follow-through on mitigations."}],
                "major_turning_points": [{"period": "fy25", "summary": "Execution improved."}],
                "evidence_confidence": {"level": "high", "basis": ["linked evidence"], "limitations": []},
            }
        ),
        encoding="utf-8",
    )
    return company_root


def _write_pcim(base_dir: Path, company: str) -> Path:
    memory_root = base_dir / "companies" / company / "company_memory"
    memory_root.mkdir(parents=True, exist_ok=True)
    pcim = {
        "contract_version": "1.0",
        "company": company,
        "business_understanding": {"latest_business_view": {"year": "fy25", "business_model": {"business_summary": "Synthetic business", "evidence_ids": ["ev_bu_1"]}}},
        "management_quality_inputs": {"management_focus_by_year": [{"year": "fy25", "items": [{"value": "Execution focus", "evidence_ids": ["ev_mgmt_1"]}]}]},
        "financial_truth_inputs": {"usable_current_metrics": [{"metric_id": "revenue", "value": 100.0, "basis": "consolidated", "confidence": "high"}]},
        "evidence_map": {"management_quality_inputs": ["ev_mgmt_1"], "business_understanding": ["ev_bu_1"], "financial_truth_inputs": ["ev_fin_1"]},
        "uncertainty_missing_data": {"incomplete_years": [], "missing_sections": [], "missing_items": []},
    }
    path = memory_root / "pcim_v1.json"
    path.write_text(json.dumps(pcim), encoding="utf-8")
    return path


def test_company_memory_context_orders_streams_by_doctrine(tmp_path):
    company_root = _write_company_memory(tmp_path, "syntheticco")

    graham_context = build_company_memory_context(company_root, "graham", token_budget=2000)
    buffett_context = build_company_memory_context(company_root, "buffett", token_budget=2000)

    assert graham_context["streams_found"][0] == "financial memory"
    assert buffett_context["streams_found"][0] == "management quality"
    assert graham_context["streams"][0]["stream"] == "financial memory"
    assert buffett_context["streams"][0]["stream"] == "management quality"
    assert graham_context["source_artifact_count"] >= 1


def test_investor_panel_prompt_carries_company_memory_summaries(tmp_path):
    company_root = _write_company_memory(tmp_path, "syntheticco")
    pcim_path = _write_pcim(tmp_path, "syntheticco")
    pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    doctrine = InvestorDoctrineRegistry(Path("intelligence/investor_panel/doctrines")).get("buffett")

    prompt, compact_pcim, _stats, limits_used, input_compacted, _budget_report = _build_compact_prompt(
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
    rendered = json.dumps(llm_input_pack, ensure_ascii=False)

    assert "company_memory_context" in rendered
    assert "management commitments" in rendered
    assert "management quality" in rendered
    assert "Treat company-memory streams as longitudinal evidence" not in rendered
    assert "company-memory progression summaries" not in prompt
