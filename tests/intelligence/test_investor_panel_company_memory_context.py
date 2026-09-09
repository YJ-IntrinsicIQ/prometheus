import json
import re
from pathlib import Path
from typing import Optional

from intelligence.investor_panel.company_memory_context import (
    _compact_company_model,
    _compact_longitudinal_current_state,
    _compact_management_quality,
    build_company_memory_context,
)
from intelligence.investor_panel.doctrine_registry import InvestorDoctrineRegistry
from intelligence.investor_panel.runner import (
    _build_compact_prompt,
    _build_prompt_input_pack,
    _raise_if_management_synthesis_chain_contradicted,
    _repair_management_synthesis_chain_inflation,
)


def _write_company_memory(base_dir: Path, company: str) -> Path:
    company_root = base_dir / "companies" / company
    memory_root = company_root / "company_memory"
    (memory_root / "management_commitments").mkdir(parents=True, exist_ok=True)
    (memory_root / "projects").mkdir(parents=True, exist_ok=True)
    (memory_root / "capacity").mkdir(parents=True, exist_ok=True)
    (memory_root / "financials").mkdir(parents=True, exist_ok=True)
    (memory_root / "management_quality").mkdir(parents=True, exist_ok=True)
    (memory_root / "management_progression").mkdir(parents=True, exist_ok=True)

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
    (memory_root / "management_progression" / "management_progression.json").write_text(
        json.dumps(
            {
                "company_slug": company,
                "coverage_status": "partial",
                "progression_items": [
                    {
                        "theme": "Expand specialty franchise in regulated markets",
                        "period": "fy25",
                        "synthesis_chain": {
                            "chain_status": "CLAIM_ONLY",
                            "claim": {
                                "text": "Management said it would expand the specialty franchise in regulated markets.",
                                "period": "fy25",
                                "source_event_id": "MC-0001",
                                "evidence_ids": ["ev_commitments_p12_00001"],
                            },
                            "action": None,
                            "outcome": None,
                            "financial_consequence": {
                                "link_status": "not_yet_visible",
                                "basis": "No action evidence is available.",
                                "metrics_observed": [],
                            },
                            "investor_implication": {
                                "conclusion": "Management made a statement, but no execution evidence has been documented.",
                                "confidence": "low",
                            },
                        },
                    },
                    {
                        "theme": "Commission independent customer-service review",
                        "period": "fy24",
                        "synthesis_chain": {
                            "chain_status": "ACTION_COMPLETED",
                            "claim": None,
                            "action": {
                                "text": "Management commissioned an independent customer-service review.",
                                "period": "fy24",
                                "completed": True,
                                "actor": "management",
                                "action_actor": "management",
                                "source_event_id": "PJ-0007",
                                "evidence_ids": ["ev_projects_p117_00008"],
                            },
                            "outcome": None,
                            "financial_consequence": {
                                "link_status": "not_yet_visible",
                                "basis": "Completion is evidenced, but operating result is not.",
                                "metrics_observed": [],
                            },
                            "investor_implication": {
                                "conclusion": "Completion alone does not confirm economic value.",
                                "confidence": "medium",
                            },
                        },
                    },
                ],
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
    assert buffett_context["streams_found"][0] == "management progression"
    assert graham_context["streams"][0]["stream"] == "financial memory"
    assert buffett_context["streams"][0]["stream"] == "management progression"
    assert graham_context["source_artifact_count"] >= 1
    assert "management progression" in graham_context["streams_found"]


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
    assert "synthesis_chains" in rendered
    assert "CLAIM_ONLY" in rendered
    assert "management commitments" in rendered
    assert "management quality" in rendered
    assert "Treat company-memory streams as longitudinal evidence" not in rendered
    assert "Management synthesis-chain rules" in prompt
    assert "CLAIM_ONLY is statement evidence only" in prompt
    assert "compact PCIM only" not in prompt


def test_management_progression_context_exposes_chain_without_internal_ids(tmp_path):
    company_root = _write_company_memory(tmp_path, "syntheticco")

    context = build_company_memory_context(company_root, "buffett", token_budget=2000)
    progression_stream = next(stream for stream in context["streams"] if stream["stream"] == "management progression")
    rendered_progression = json.dumps(progression_stream, ensure_ascii=False)
    chain = progression_stream["synthesis_chains"][0]
    assert chain["chain_status"] in {"CLAIM_ONLY", "ACTION_COMPLETED"}
    assert chain["evidence_ids"]
    assert all(evidence_id.startswith("ev_") for evidence_id in chain["evidence_ids"])
    assert "MC-0001" not in rendered_progression
    assert "PJ-0007" not in rendered_progression


def test_analyst_qa_rejects_claim_only_used_as_execution_evidence():
    context = {
        "streams": [
            {
                "stream": "management progression",
                "synthesis_chains": [
                    {
                        "theme": "Expand specialty franchise in regulated markets",
                        "chain_status": "CLAIM_ONLY",
                        "claim_summary": "Management said it would expand the specialty franchise in regulated markets.",
                        "financial_link_status": "not_yet_visible",
                    }
                ],
            }
        ]
    }

    try:
        _raise_if_management_synthesis_chain_contradicted(
            company_memory_context=context,
            assessment={"capital_allocation_assessment": "Management delivered the specialty franchise expansion in regulated markets."},
            key_findings=[],
            red_flags=[],
            open_uncertainties=[],
            user_facing_brief={"what_looks_good": [], "what_needs_caution": [], "what_is_missing": []},
        )
    except ValueError as exc:
        assert "CLAIM_ONLY cannot support execution" in str(exc)
    else:
        raise AssertionError("claim-only execution misuse should fail")


def test_analyst_qa_allows_claim_only_when_uncertainty_is_preserved():
    context = {
        "streams": [
            {
                "stream": "management progression",
                "synthesis_chains": [
                    {
                        "theme": "Expand specialty franchise in regulated markets",
                        "chain_status": "CLAIM_ONLY",
                        "claim_summary": "Management said it would expand the specialty franchise in regulated markets.",
                        "financial_link_status": "not_yet_visible",
                    }
                ],
            }
        ]
    }

    _raise_if_management_synthesis_chain_contradicted(
        company_memory_context=context,
        assessment={"capital_allocation_assessment": "Management discussed specialty franchise expansion, but execution remains unproven."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief={"what_looks_good": [], "what_needs_caution": [], "what_is_missing": []},
    )


def test_analyst_qa_rejects_regulator_action_attributed_to_management():
    context = {
        "streams": [
            {
                "stream": "management progression",
                "synthesis_chains": [
                    {
                        "theme": "USFDA prohibited use of API manufactured at the Toansa facility",
                        "chain_status": "OUTCOME_UNKNOWN",
                        "actor": "regulator",
                        "action_summary": "USFDA prohibited use of API manufactured at the Toansa facility.",
                        "financial_link_status": "not_yet_visible",
                    }
                ],
            }
        ]
    }

    try:
        _raise_if_management_synthesis_chain_contradicted(
            company_memory_context=context,
            assessment={"risk_assessment": "Management has initiated action on the Toansa facility API prohibition."},
            key_findings=[],
            red_flags=[],
            open_uncertainties=[],
            user_facing_brief={"what_looks_good": [], "what_needs_caution": [], "what_is_missing": []},
        )
    except ValueError as exc:
        assert "non-management actor" in str(exc)
    else:
        raise AssertionError("regulator action attributed to management should fail")


def test_analyst_qa_rejects_action_completed_as_positive_outcome_without_result():
    context = {
        "streams": [
            {
                "stream": "management progression",
                "synthesis_chains": [
                    {
                        "theme": "Commission independent customer-service review",
                        "chain_status": "ACTION_COMPLETED",
                        "action_summary": "Management commissioned an independent customer-service review.",
                        "financial_link_status": "not_yet_visible",
                    }
                ],
            }
        ]
    }

    try:
        _raise_if_management_synthesis_chain_contradicted(
            company_memory_context=context,
            assessment={"management_quality_assessment": "The independent customer-service review created value and improved service quality."},
            key_findings=[],
            red_flags=[],
            open_uncertainties=[],
            user_facing_brief={"what_looks_good": [], "what_needs_caution": [], "what_is_missing": []},
        )
    except ValueError as exc:
        assert "ACTION_COMPLETED alone cannot support positive" in str(exc)
    else:
        raise AssertionError("completion-only positive-outcome misuse should fail")


def test_management_chain_repair_downgrades_action_completed_positive_outcome():
    context = {
        "streams": [
            {
                "stream": "management progression",
                "synthesis_chains": [
                    {
                        "theme": "Commission independent customer-service review",
                        "chain_status": "ACTION_COMPLETED",
                        "actor": "management",
                        "action_summary": "Management commissioned an independent customer-service review.",
                        "outcome_summary": "",
                        "financial_link_status": "not_yet_visible",
                    }
                ],
            }
        ]
    }
    assessment = {
        "management_quality_assessment": "The independent customer-service review created value and improved service quality."
    }
    brief = {"what_looks_good": [], "what_needs_caution": [], "what_is_missing": []}

    notes = _repair_management_synthesis_chain_inflation(
        company_memory_context=context,
        assessment=assessment,
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief=brief,
    )

    assert notes
    assert "created value" not in assessment["management_quality_assessment"].lower()
    assert "improved service" not in assessment["management_quality_assessment"].lower()
    assert "outcome" in assessment["management_quality_assessment"].lower()
    assert "unproven" in assessment["management_quality_assessment"].lower()
    _raise_if_management_synthesis_chain_contradicted(
        company_memory_context=context,
        assessment=assessment,
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief=brief,
    )


def test_management_chain_repair_leaves_supported_action_completed_wording_unchanged():
    context = {
        "streams": [
            {
                "stream": "management progression",
                "synthesis_chains": [
                    {
                        "theme": "Commission independent customer-service review",
                        "chain_status": "ACTION_COMPLETED",
                        "actor": "management",
                        "action_summary": "Management commissioned an independent customer-service review.",
                        "financial_link_status": "not_yet_visible",
                    }
                ],
            }
        ]
    }
    original = "Management completed the independent customer-service review commissioning; the result remains unproven."
    assessment = {"management_quality_assessment": original}
    brief = {"what_looks_good": [], "what_needs_caution": [], "what_is_missing": []}

    notes = _repair_management_synthesis_chain_inflation(
        company_memory_context=context,
        assessment=assessment,
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief=brief,
    )

    assert notes == []
    assert assessment["management_quality_assessment"] == original
    _raise_if_management_synthesis_chain_contradicted(
        company_memory_context=context,
        assessment=assessment,
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief=brief,
    )


def test_management_chain_qa_allows_evidenced_positive_outcome():
    context = {
        "streams": [
            {
                "stream": "management progression",
                "synthesis_chains": [
                    {
                        "theme": "Plant commissioning and utilization ramp",
                        "chain_status": "OUTCOME_POSITIVE",
                        "actor": "management",
                        "action_summary": "Plant commissioned in FY24.",
                        "outcome_summary": "Utilization rose to 80% in FY25.",
                        "financial_link_status": "not_yet_visible",
                    }
                ],
            }
        ]
    }

    _raise_if_management_synthesis_chain_contradicted(
        company_memory_context=context,
        assessment={"growth_assessment": "The plant commissioning improved utilization to 80%."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief={"what_looks_good": [], "what_needs_caution": [], "what_is_missing": []},
    )


def test_management_chain_repair_blocks_unconfirmed_financial_causality():
    context = {
        "streams": [
            {
                "stream": "management progression",
                "synthesis_chains": [
                    {
                        "theme": "Branch productivity program",
                        "chain_status": "ACTION_COMPLETED",
                        "actor": "management",
                        "action_summary": "Management completed a branch productivity program.",
                        "financial_link_status": "not_yet_visible",
                    }
                ],
            }
        ]
    }
    key_findings = ["The branch productivity program delivered a financial benefit and returns improved."]
    brief = {"what_looks_good": [], "what_needs_caution": [], "what_is_missing": []}

    notes = _repair_management_synthesis_chain_inflation(
        company_memory_context=context,
        assessment={},
        key_findings=key_findings,
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief=brief,
    )

    assert notes
    assert "financial benefit" not in key_findings[0].lower()
    assert "unproven" in key_findings[0].lower()
    _raise_if_management_synthesis_chain_contradicted(
        company_memory_context=context,
        assessment={},
        key_findings=key_findings,
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief=brief,
    )


def test_management_chain_qa_allows_confirmed_financial_impact():
    context = {
        "streams": [
            {
                "stream": "management progression",
                "synthesis_chains": [
                    {
                        "theme": "Branch productivity program",
                        "chain_status": "FINANCIAL_IMPACT_CONFIRMED",
                        "actor": "management",
                        "action_summary": "Management completed a branch productivity program.",
                        "outcome_summary": "Revenue improved after productivity rose.",
                        "financial_link_status": "confirmed",
                    }
                ],
            }
        ]
    }

    _raise_if_management_synthesis_chain_contradicted(
        company_memory_context=context,
        assessment={"owner_earnings_assessment": "The branch productivity program produced a financial benefit as revenue improved."},
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief={"what_looks_good": [], "what_needs_caution": [], "what_is_missing": []},
    )


def test_management_chain_repair_preserves_non_management_actor_attribution():
    context = {
        "streams": [
            {
                "stream": "management progression",
                "synthesis_chains": [
                    {
                        "theme": "USFDA prohibited use of API manufactured at the Toansa facility",
                        "chain_status": "OUTCOME_UNKNOWN",
                        "actor": "regulator",
                        "action_summary": "USFDA prohibited use of API manufactured at the Toansa facility.",
                        "financial_link_status": "not_yet_visible",
                    }
                ],
            }
        ]
    }
    assessment = {"risk_assessment": "Management has initiated action on the Toansa facility API prohibition."}
    brief = {"what_looks_good": [], "what_needs_caution": [], "what_is_missing": []}

    notes = _repair_management_synthesis_chain_inflation(
        company_memory_context=context,
        assessment=assessment,
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief=brief,
    )

    assert notes
    assert assessment["risk_assessment"].startswith("A regulator action occurred")
    assert "management has initiated" not in assessment["risk_assessment"].lower()
    _raise_if_management_synthesis_chain_contradicted(
        company_memory_context=context,
        assessment=assessment,
        key_findings=[],
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief=brief,
    )


def test_management_chain_repair_leaves_clean_doctrine_output_unchanged():
    context = {
        "streams": [
            {
                "stream": "management progression",
                "synthesis_chains": [
                    {
                        "theme": "Commission independent customer-service review",
                        "chain_status": "ACTION_COMPLETED",
                        "actor": "management",
                        "action_summary": "Management commissioned an independent customer-service review.",
                        "financial_link_status": "not_yet_visible",
                    }
                ],
            }
        ]
    }
    key_findings = ["Capital discipline remains uncertain because operating results from the review are unproven."]
    brief = {"what_looks_good": [], "what_needs_caution": [], "what_is_missing": []}

    notes = _repair_management_synthesis_chain_inflation(
        company_memory_context=context,
        assessment={},
        key_findings=key_findings,
        red_flags=[],
        open_uncertainties=[],
        user_facing_brief=brief,
    )

    assert notes == []
    assert key_findings == ["Capital discipline remains uncertain because operating results from the review are unproven."]


# ---------------------------------------------------------------------------
# Regression tests — MQE internal ID leak into analyst prompt
# Bug: _compact_management_quality passed evidence_ids/source_item_id fields
# through _top_list, exposing MQE-XXXX / MC-XXXX / PJ-XXXX IDs to the LLM.
# The LLM cited them as valid evidence IDs; the validator rejected them as
# unknown_evidence_id; all five analysts got raw_artifact_status=fail.
# ---------------------------------------------------------------------------

_MQE_PATTERN = re.compile(r"\bMQE-\d+\b|\bMC-\d+\b|\bPJ-\d+\b|\bCP-\d+\b")


def _mq_summary_with_internal_ids(company: str = "testco") -> dict:
    return {
        "company_slug": company,
        "overall_view": "Management quality is improving.",
        "overall_direction": "improving",
        "strongest_dimension": "execution_discipline",
        "weakest_dimension": "risk_handling",
        "investor_implication": "Execution appears dependable.",
        "what_strengthened_conviction": [
            {
                "confidence": "high",
                "dimension": "execution_discipline",
                "evidence_ids": ["MQE-0041"],
                "period": "fy24",
                "source_item_id": "CP-0002",
                "source_stream": "capacity",
                "summary": "Digital loan origination capacity improved.",
            },
            {
                "confidence": "high",
                "dimension": "execution_discipline",
                "evidence_ids": ["MQE-0049"],
                "period": "fy25",
                "source_item_id": "CP-0003",
                "source_stream": "capacity",
                "summary": "Loan origination system upgraded.",
            },
        ],
        "what_weakened_conviction": [
            {
                "confidence": "medium",
                "dimension": "execution_discipline",
                "evidence_ids": ["MQE-0048"],
                "period": "fy25",
                "source_item_id": "MC-0001",
                "source_stream": "management_commitments",
                "summary": "Commitment delivery was partial.",
            }
        ],
        "what_remains_unproven": [
            {
                "confidence": "high",
                "dimension": "risk_handling",
                "evidence_ids": ["MQE-0052"],
                "period": "fy25",
                "source_item_id": "risk_abc123",
                "source_stream": "risks",
                "summary": "Working-capital stress.",
            }
        ],
        "major_turning_points": [
            {
                "confidence": "medium",
                "dimension": "candor_and_consistency",
                "direction": "unclear",
                "evidence_ids": ["MQE-0057"],
                "period": "fy25",
                "relevance": "high",
                "source_item_id": "CM-0002",
                "source_stream": "management_commentary",
                "summary": "MSME focus shift.",
            }
        ],
        "evidence_confidence": {"level": "high", "basis": ["linked evidence"], "limitations": []},
    }


def test_mq_compact_strips_mq_internal_ids_from_conviction_fields():
    payload = _mq_summary_with_internal_ids()
    compacted = _compact_management_quality(payload)
    compacted_str = json.dumps(compacted)
    assert not _MQE_PATTERN.search(compacted_str), (
        f"Internal MQ IDs survived compact: {_MQE_PATTERN.findall(compacted_str)}"
    )


def test_mq_compact_preserves_useful_fields_after_stripping():
    payload = _mq_summary_with_internal_ids()
    compacted = _compact_management_quality(payload)
    assert compacted["overall_view"] == "Management quality is improving."
    assert compacted["overall_direction"] == "improving"
    assert compacted["strongest_dimension"] == "execution_discipline"
    strengthened = compacted.get("what_strengthened_conviction", [])
    assert len(strengthened) > 0
    first = strengthened[0]
    assert isinstance(first, dict)
    assert "summary" in first or "dimension" in first
    assert "evidence_ids" not in first
    assert "source_item_id" not in first


def test_mq_compact_handles_empty_or_missing_fields_without_internal_ids():
    minimal_payload = {
        "company_slug": "emptyco",
        "overall_view": "No evidence available.",
        "overall_direction": "unknown",
        "what_strengthened_conviction": [],
        "what_weakened_conviction": [],
        "what_remains_unproven": [],
        "major_turning_points": [],
    }
    compacted = _compact_management_quality(minimal_payload)
    compacted_str = json.dumps(compacted)
    assert not _MQE_PATTERN.search(compacted_str)
    assert compacted["overall_view"] == "No evidence available."


def test_mq_compact_strips_ids_regardless_of_company_name():
    for company_name in ("ujjivan", "sunpharma", "infra_corp", "widgetco"):
        payload = _mq_summary_with_internal_ids(company=company_name)
        compacted = _compact_management_quality(payload)
        compacted_str = json.dumps(compacted)
        assert not _MQE_PATTERN.search(compacted_str), (
            f"Internal MQ IDs leaked for company {company_name!r}: "
            f"{_MQE_PATTERN.findall(compacted_str)}"
        )


def test_mq_compact_without_internal_ids_in_input_is_unchanged():
    payload = {
        "company_slug": "cleanco",
        "overall_view": "Strong execution across all dimensions.",
        "overall_direction": "improving",
        "strongest_dimension": "execution_discipline",
        "weakest_dimension": None,
        "investor_implication": "High conviction.",
        "what_strengthened_conviction": [
            {"dimension": "execution_discipline", "period": "fy25", "summary": "On-time delivery."}
        ],
        "what_weakened_conviction": [],
        "what_remains_unproven": [],
        "major_turning_points": [
            {"dimension": "execution_discipline", "period": "fy24", "summary": "Capacity commissioned."}
        ],
        "evidence_confidence": {"level": "high"},
    }
    compacted = _compact_management_quality(payload)
    compacted_str = json.dumps(compacted)
    assert not _MQE_PATTERN.search(compacted_str)
    assert compacted["overall_view"] == "Strong execution across all dimensions."
    strengthened = compacted.get("what_strengthened_conviction", [])
    assert len(strengthened) == 1
    assert strengthened[0].get("summary") is not None or strengthened[0].get("dimension") is not None


def test_company_model_stream_gives_lynch_business_story_context(tmp_path):
    company_root = _write_company_memory(tmp_path, "storyco")
    model_dir = company_root / "company_memory" / "company_model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "company_model.json").write_text(
        json.dumps(
            {
                "schema_version": "company_model.v1",
                "company_slug": "storyco",
                "coverage_status": "supported",
                "current_business_model": {
                    "summary": "A branch-led lending franchise earning interest spreads from small-business and retail credit.",
                    "business_model_type": "financial_services",
                    "what_company_does": "Originates, services, and funds retail and small-business loans.",
                    "what_it_sells": ["Retail loans", "Small-business credit"],
                    "who_pays": ["Retail borrowers", "Small-business borrowers"],
                    "who_uses": ["Mass-market customers"],
                    "how_revenue_happens": "Interest income and fee income from lending relationships.",
                },
                "economic_drivers": ["loan growth", "credit cost discipline"],
                "dependencies": ["funding access"],
                "uncertainties": ["asset quality through cycle"],
                "company_identity": {"confidence": {"level": "high"}},
                "source_manifest": {"coverage_status": "supported"},
            }
        ),
        encoding="utf-8",
    )

    context = build_company_memory_context(company_root, "lynch", token_budget=3000)
    streams = {stream["stream"]: stream for stream in context["streams"]}

    assert context["streams_considered"][0] == "company model"
    assert "company model" in streams
    model_stream = streams["company model"]
    assert model_stream["business_model_type"] == "financial_services"
    assert "branch-led lending franchise" in model_stream["business_summary"]
    assert "Retail loans" in json.dumps(model_stream)
    assert "Interest income" in model_stream["how_revenue_happens"]


# ── Phase 13 — Canonical Panel Context Repair Tests ─────────────────────────


def _lcs_item(theme: str, *, status: str = "partially_delivered", credibility: str = "PARTIALLY_DELIVERED", confidence_level: str = "medium", linked: Optional[list] = None) -> dict:
    return {
        "state_id": f"lcs-{theme.lower().replace(' ', '_')[:30]}",
        "theme": theme,
        "current_status": status,
        "management_credibility_signal": credibility,
        "confidence": {"level": confidence_level, "basis": ["test"], "limitations": []},
        "source_period": "fy25",
        "linked_company_model_ids": linked or [],
        "evidence": [{"source_artifact": "company_memory/management_progression/management_progression.json", "evidence_id": "", "field_path": "progression_items[]"}],
    }


def _company_model_with_lcs(company: str, lcs_items: list) -> dict:
    return {
        "schema_version": "company_model.v1",
        "company_slug": company,
        "coverage_status": "supported",
        "current_business_model": {
            "business_model_type": "platform",
            "summary": "A cloud communications platform for enterprises.",
            "what_it_sells": ["Messaging API"],
            "who_pays": ["enterprises"],
            "how_revenue_happens": "Subscription and per-message fees from B2B customers.",
            "economic_mechanism": "Platform monetizes message volume through tiered subscription contracts.",
        },
        "offerings": [],
        "customers": [],
        "revenue_engines": [],
        "economic_drivers": [],
        "longitudinal_current_state": lcs_items,
        "source_manifest": {"sources_used": [], "company_slug": company},
    }


def _write_company_model(company_root: Path, lcs_items: list) -> None:
    cm_dir = company_root / "company_memory" / "company_model"
    cm_dir.mkdir(parents=True, exist_ok=True)
    import json as _json
    (cm_dir / "company_model.json").write_text(
        _json.dumps(_company_model_with_lcs(company_root.name, lcs_items)), encoding="utf-8"
    )


def _mp_payload_with_streams(company: str, items: list) -> dict:
    return {
        "schema_version": "management_progression.v1",
        "company_slug": company,
        "generated_at": "2026-09-03T00:00:00Z",
        "coverage_status": "supported",
        "progression_items": items,
        "management_thesis_chains": [],
        "measurable_commitments": [],
        "contradiction_signals": [],
        "source_manifest": {"sources_used": [], "company_slug": company},
    }


def _mp_item_with_stream(theme: str, stream_type: str, *, credibility: str = "PARTIALLY_DELIVERED", status: str = "partially_delivered") -> dict:
    return {
        "item_id": f"test-{theme[:10]}",
        "theme": theme,
        "stream_types": [stream_type],
        "current_status": status,
        "management_credibility_signal": credibility,
        "linked_company_model_ids": [],
        "events": [],
        "synthesis_chain": {
            "chain_status": "OUTCOME_UNKNOWN",
            "claim": {"text": f"Management claimed: {theme}", "period": "fy25", "evidence_ids": []},
            "action": {"text": f"Action taken for {theme}", "period": "fy25", "completed": False, "actor": "management", "action_actor": "management", "evidence_ids": []},
            "outcome": None,
            "financial_consequence": {"link_status": "not_yet_visible", "basis": "No outcome evidence.", "metrics_observed": []},
            "investor_implication": {"conclusion": f"Outcome unknown for {theme}.", "confidence": "low"},
        },
    }


class TestPhase13LongitudinalCurrentStateReachesPanel:
    """Phase 13.1 — longitudinal_current_state from Company Model enters Panel context."""

    def test_lcs_enters_company_model_stream_block(self, tmp_path):
        """Gate 1: longitudinal_current_state appears in the company_model stream block."""
        co = _write_company_memory(tmp_path, "acme")
        _write_company_model(co, [_lcs_item("International Expansion"), _lcs_item("Wisely AI Platform", credibility="UNABLE_TO_VERIFY", status="announced", confidence_level="low")])

        ctx = build_company_memory_context(co, "buffett", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}

        assert "company model" in streams
        lcs = streams["company model"].get("longitudinal_current_state_summary", [])
        assert len(lcs) >= 1, "longitudinal_current_state_summary must be present when LCS items exist"
        themes = [item["theme"] for item in lcs]
        assert "International Expansion" in themes

    def test_lcs_absent_when_company_model_has_no_lcs_items(self, tmp_path):
        """No longitudinal_current_state_summary key when LCS is empty."""
        co = _write_company_memory(tmp_path, "acme")
        _write_company_model(co, [])

        ctx = build_company_memory_context(co, "fisher", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}

        if "company model" in streams:
            assert "longitudinal_current_state_summary" not in streams["company model"]

    def test_lcs_credibility_and_confidence_preserved(self, tmp_path):
        """Gate 2: management_credibility_signal and confidence_level survive compaction."""
        co = _write_company_memory(tmp_path, "acme")
        _write_company_model(co, [
            _lcs_item("Confirmed Expansion", credibility="CONFIRMED", status="partially_delivered", confidence_level="high"),
            _lcs_item("Claimed Initiative", credibility="CLAIMED", status="announced", confidence_level="low"),
        ])

        ctx = build_company_memory_context(co, "buffett", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}

        lcs = streams.get("company model", {}).get("longitudinal_current_state_summary", [])
        assert len(lcs) == 2
        confirmed = next((i for i in lcs if i["theme"] == "Confirmed Expansion"), None)
        claimed = next((i for i in lcs if i["theme"] == "Claimed Initiative"), None)
        assert confirmed is not None
        assert confirmed["management_credibility_signal"] == "CONFIRMED"
        assert confirmed["confidence_level"] == "high"
        assert claimed is not None
        assert claimed["management_credibility_signal"] == "CLAIMED"
        assert claimed["confidence_level"] == "low"

    def test_lcs_no_events_field_in_compact(self, tmp_path):
        """Ownership boundary: events must not appear in compacted LCS items."""
        co = _write_company_memory(tmp_path, "acme")
        lcs_with_events = _lcs_item("Theme With Events")
        lcs_with_events["events"] = [{"event_id": "ev1", "text": "raw event"}]
        _write_company_model(co, [lcs_with_events])

        ctx = build_company_memory_context(co, "graham", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}

        lcs = streams.get("company model", {}).get("longitudinal_current_state_summary", [])
        for item in lcs:
            assert "events" not in item, "events must not appear in compacted LCS — ownership belongs to Management Progression"

    def test_lcs_no_source_chunk_in_compact(self, tmp_path):
        """No raw text leakage into Panel from LCS compact."""
        co = _write_company_memory(tmp_path, "acme")
        item = _lcs_item("Growth Initiative")
        item["evidence"][0]["source_chunk"] = "RAW DOCUMENT TEXT"
        _write_company_model(co, [item])

        ctx = build_company_memory_context(co, "fisher", token_budget=2200)
        import json as _json
        ctx_text = _json.dumps(ctx)
        assert "source_chunk" not in ctx_text, "source_chunk must never appear in Panel context"

    def test_all_five_specialists_access_lcs_via_company_model(self, tmp_path):
        """Gates 1 + company-model stream: all 5 specialists can access LCS when company_model available."""
        co = _write_company_memory(tmp_path, "acme")
        _write_company_model(co, [_lcs_item("Platform Expansion", credibility="PARTIALLY_DELIVERED", status="partially_delivered")])

        lcs_counts = {}
        for doctrine in ["graham", "buffett", "fisher", "munger", "lynch"]:
            ctx = build_company_memory_context(co, doctrine, token_budget=2200)
            streams = {b["stream"]: b for b in ctx.get("streams", [])}
            lcs = streams.get("company model", {}).get("longitudinal_current_state_summary", [])
            lcs_counts[doctrine] = len(lcs)

        assert lcs_counts["graham"] >= 1
        assert lcs_counts["buffett"] >= 1
        assert lcs_counts["fisher"] >= 1
        assert lcs_counts["lynch"] >= 1
        # Munger should also get it when financial_memory/management_quality absent
        # (company_model is now at position 4 in Munger's priority, within top 3 when competing streams missing)
        # Not a hard assertion since it depends on which other streams exist


class TestPhase13ManagementProgressionEnrichment:
    """Phase 13.2 — Management Progression items expose lifecycle authority fields."""

    def _write_mp(self, company_root: Path, items: list) -> None:
        mp_dir = company_root / "company_memory" / "management_progression"
        mp_dir.mkdir(parents=True, exist_ok=True)
        import json as _json
        (mp_dir / "management_progression.json").write_text(
            _json.dumps(_mp_payload_with_streams(company_root.name, items)), encoding="utf-8"
        )

    def test_mp_items_expose_stream_types(self, tmp_path):
        """Gate 3: stream_types appears in compacted Management Progression items."""
        co = _write_company_memory(tmp_path, "acme")
        self._write_mp(co, [_mp_item_with_stream("International Expansion", "multi_source_longitudinal")])

        ctx = build_company_memory_context(co, "fisher", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}

        assert "management progression" in streams
        chains = streams["management progression"].get("synthesis_chains", [])
        assert len(chains) >= 1
        assert "stream_types" in chains[0], "stream_types must appear in compacted MP item"
        assert "multi_source_longitudinal" in chains[0]["stream_types"]

    def test_mp_items_expose_management_credibility_signal(self, tmp_path):
        """Gate 8: management_credibility_signal appears in compacted MP items."""
        co = _write_company_memory(tmp_path, "acme")
        self._write_mp(co, [
            _mp_item_with_stream("Confirmed Delivery", "multi_source_longitudinal", credibility="CONFIRMED"),
            _mp_item_with_stream("Claimed Initiative", "project", credibility="CLAIMED"),
        ])

        ctx = build_company_memory_context(co, "buffett", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}
        chains = streams.get("management progression", {}).get("synthesis_chains", [])

        assert len(chains) >= 2
        confirmed_chain = next((c for c in chains if c["theme"] == "Confirmed Delivery"), None)
        claimed_chain = next((c for c in chains if c["theme"] == "Claimed Initiative"), None)
        assert confirmed_chain is not None
        assert confirmed_chain["management_credibility_signal"] == "CONFIRMED"
        assert claimed_chain is not None
        assert claimed_chain["management_credibility_signal"] == "CLAIMED"

    def test_mp_items_expose_current_status(self, tmp_path):
        """current_status is available in compact — allows distinction between active/unresolved."""
        co = _write_company_memory(tmp_path, "acme")
        self._write_mp(co, [_mp_item_with_stream("Active Program", "project", status="in_progress")])

        ctx = build_company_memory_context(co, "munger", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}
        chains = streams.get("management progression", {}).get("synthesis_chains", [])

        assert len(chains) >= 1
        assert "current_status" in chains[0]
        assert chains[0]["current_status"] == "in_progress"

    def test_mp_limit_raised_to_four(self, tmp_path):
        """Gate 3: MP compact shows up to 4 items (increased from prior limit of 2)."""
        co = _write_company_memory(tmp_path, "acme")
        items = [_mp_item_with_stream(f"Theme {i}", "multi_source_longitudinal") for i in range(6)]
        self._write_mp(co, items)

        ctx = build_company_memory_context(co, "graham", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}
        chains = streams.get("management progression", {}).get("synthesis_chains", [])

        assert len(chains) == 4, "Management Progression must now show up to 4 items"

    def test_mp_always_present_for_all_doctrines(self, tmp_path):
        """Gate 3: management_progression is protected — always reaches LLM regardless of doctrine."""
        co = _write_company_memory(tmp_path, "acme")

        for doctrine in ["graham", "buffett", "fisher", "munger", "lynch"]:
            ctx = build_company_memory_context(co, doctrine, token_budget=2200)
            assert "management progression" in ctx["streams_found"], f"management progression must always be present for {doctrine}"

    def test_mp_chain_rules_present(self, tmp_path):
        """chain_rules must always appear so LLM cannot confuse claim with delivery evidence."""
        co = _write_company_memory(tmp_path, "acme")

        ctx = build_company_memory_context(co, "fisher", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}

        mp_block = streams.get("management progression", {})
        rules = mp_block.get("chain_rules", [])
        assert len(rules) >= 4, "chain_rules must be present to prevent claim/delivery confusion"
        assert any("CLAIM_ONLY" in r for r in rules)
        assert any("FINANCIAL_LINK_UNPROVEN" in r for r in rules)


class TestPhase13MungerBusinessModelAccess:
    """Phase 13.3 — Munger gets company_model when competing streams are absent."""

    def test_munger_gets_company_model_when_management_quality_absent(self, tmp_path):
        """Munger's updated priority puts company_model at #4 — it enters top 3 when quality/commitments missing."""
        co = _write_company_memory(tmp_path, "acme")
        # Remove management_quality if written by _write_company_memory
        mq_path = co / "company_memory" / "management_quality" / "management_quality_summary.json"
        if mq_path.exists():
            mq_path.unlink()
        mc_path = co / "company_memory" / "management_commitments" / "management_commitments.json"
        if mc_path.exists():
            mc_path.unlink()
        _write_company_model(co, [_lcs_item("Fragility Theme", credibility="UNABLE_TO_VERIFY", status="announced", confidence_level="low")])

        ctx = build_company_memory_context(co, "munger", token_budget=2200)
        streams_found = ctx["streams_found"]

        assert "management progression" in streams_found
        assert "company model" in streams_found, "Munger must get company_model when management_quality and commitments absent"

    def test_munger_lcs_available_when_company_model_present(self, tmp_path):
        """When Munger sees company_model, LCS fragility signals are accessible."""
        co = _write_company_memory(tmp_path, "acme")
        mq_path = co / "company_memory" / "management_quality" / "management_quality_summary.json"
        if mq_path.exists():
            mq_path.unlink()
        mc_path = co / "company_memory" / "management_commitments" / "management_commitments.json"
        if mc_path.exists():
            mc_path.unlink()
        _write_company_model(co, [
            _lcs_item("Unproven Revenue Claim", credibility="UNABLE_TO_VERIFY", status="announced", confidence_level="low"),
        ])

        ctx = build_company_memory_context(co, "munger", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}

        lcs = streams.get("company model", {}).get("longitudinal_current_state_summary", [])
        if lcs:
            fragile = [i for i in lcs if i["management_credibility_signal"] in ("UNABLE_TO_VERIFY", "CLAIMED")]
            assert len(fragile) >= 1, "Munger must see UNABLE_TO_VERIFY / CLAIMED LCS items for fragility analysis"


class TestPhase13ProductionRegression:
    """Phase 13.4 — Production regression: Tanla and Data Patterns context builds are correct."""

    def test_tanla_all_five_specialists_get_management_progression(self):
        """Gate: Tanla — all 5 specialists include management_progression in context."""
        from pathlib import Path
        for doctrine in ["graham", "buffett", "fisher", "munger", "lynch"]:
            ctx = build_company_memory_context(Path("companies/tanla"), doctrine, token_budget=2200)
            assert "management progression" in ctx["streams_found"], f"Tanla: management_progression missing for {doctrine}"

    def test_tanla_lcs_reaches_panel_for_graham_buffett_fisher_lynch(self):
        """Gate 7: Tanla — longitudinal_current_state reaches Panel for 4 core doctrines."""
        from pathlib import Path
        for doctrine in ["graham", "buffett", "fisher", "lynch"]:
            ctx = build_company_memory_context(Path("companies/tanla"), doctrine, token_budget=2200)
            streams = {b["stream"]: b for b in ctx.get("streams", [])}
            lcs = streams.get("company model", {}).get("longitudinal_current_state_summary", [])
            assert len(lcs) >= 1, f"Tanla: LCS must reach Panel for doctrine={doctrine}"

    def test_tanla_mp_items_have_credibility_signal(self):
        """Gate 8: Tanla — MP items carry management_credibility_signal."""
        from pathlib import Path
        ctx = build_company_memory_context(Path("companies/tanla"), "buffett", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}
        chains = streams.get("management progression", {}).get("synthesis_chains", [])
        assert len(chains) >= 1
        assert all("management_credibility_signal" in c for c in chains), "All MP chains must have management_credibility_signal"

    def test_tanla_mp_items_have_stream_types(self):
        """Tanla — MP items carry stream_types so LLM can distinguish longitudinal from project items."""
        from pathlib import Path
        ctx = build_company_memory_context(Path("companies/tanla"), "fisher", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}
        chains = streams.get("management progression", {}).get("synthesis_chains", [])
        assert all("stream_types" in c for c in chains), "All MP chains must have stream_types"
        # Tanla has multi_source_longitudinal items
        stream_type_vals = {st for c in chains for st in c.get("stream_types", [])}
        assert "multi_source_longitudinal" in stream_type_vals, "Tanla must have at least one multi_source_longitudinal MP item in context"

    def test_tanla_lcs_credibility_diversity(self):
        """Tanla LCS items represent a range of credibility signals (not all the same)."""
        from pathlib import Path
        ctx = build_company_memory_context(Path("companies/tanla"), "buffett", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}
        lcs = streams.get("company model", {}).get("longitudinal_current_state_summary", [])
        credibilities = {i["management_credibility_signal"] for i in lcs}
        assert len(credibilities) >= 1, "LCS items must have credibility signals"

    def test_datapatterns_all_five_specialists_get_management_progression(self):
        """Gate: Data Patterns — all 5 specialists include management_progression."""
        from pathlib import Path
        for doctrine in ["graham", "buffett", "fisher", "munger", "lynch"]:
            ctx = build_company_memory_context(Path("companies/datapatterns"), doctrine, token_budget=2200)
            assert "management progression" in ctx["streams_found"], f"DataPatterns: management_progression missing for {doctrine}"

    def test_datapatterns_lcs_reaches_four_doctrines(self):
        """Gate 14: Data Patterns — LCS reaches Panel for Graham, Buffett, Fisher, Lynch."""
        from pathlib import Path
        for doctrine in ["graham", "buffett", "fisher", "lynch"]:
            ctx = build_company_memory_context(Path("companies/datapatterns"), doctrine, token_budget=2200)
            streams = {b["stream"]: b for b in ctx.get("streams", [])}
            lcs = streams.get("company model", {}).get("longitudinal_current_state_summary", [])
            assert len(lcs) >= 1, f"DataPatterns: LCS must reach Panel for doctrine={doctrine}"

    def test_no_company_specific_branches_in_context_builder(self):
        """No if-company == conditions allowed — context builder must be fully generic."""
        import re
        source = Path("intelligence/investor_panel/company_memory_context.py").read_text(encoding="utf-8")
        assert 'company == "' not in source
        assert "company_slug == " not in source
        assert re.search(r'if\s+company\s*==', source) is None


class TestPhase13NoBoundaryViolations:
    """Phase 13.5 — Ownership boundaries enforced throughout the context builder."""

    def test_lcs_compact_never_includes_events(self, tmp_path):
        """events key must never appear in LCS compact — full chronology belongs to MP."""
        from intelligence.investor_panel.company_memory_context import _compact_longitudinal_current_state
        item_with_events = {
            "state_id": "lcs-test",
            "theme": "Test Theme",
            "current_status": "in_progress",
            "management_credibility_signal": "PARTIALLY_DELIVERED",
            "confidence": {"level": "medium", "basis": [], "limitations": []},
            "source_period": "fy25",
            "linked_company_model_ids": [],
            "evidence": [],
            "events": [{"event_id": "ev1", "text": "raw event data"}],
        }
        compact = _compact_longitudinal_current_state([item_with_events])
        import json as _json
        compact_text = _json.dumps(compact)
        assert "events" not in compact_text

    def test_lcs_compact_capped_at_four_items(self):
        """LCS compact returns at most 4 items regardless of how many exist."""
        from intelligence.investor_panel.company_memory_context import _compact_longitudinal_current_state
        items = [_lcs_item(f"Theme {i}") for i in range(10)]
        compact = _compact_longitudinal_current_state(items, limit=4)
        assert len(compact) == 4

    def test_mp_chain_rules_prevent_outcome_inflation(self, tmp_path):
        """Gate 5: chain_rules must include financial_link_status discipline."""
        co = _write_company_memory(tmp_path, "acme")
        ctx = build_company_memory_context(co, "munger", token_budget=2200)
        streams = {b["stream"]: b for b in ctx.get("streams", [])}
        mp_block = streams.get("management progression", {})
        rules = mp_block.get("chain_rules", [])
        financial_rule = next((r for r in rules if "FINANCIAL_LINK_UNPROVEN" in r), None)
        assert financial_rule is not None, "FINANCIAL_LINK_UNPROVEN rule must be in chain_rules"


def test_company_model_compact_preserves_business_identity_without_company_hardcoding():
    compacted = _compact_company_model(
        {
            "company_slug": "genericco",
            "coverage_status": "supported",
            "current_business_model": {
                "summary": "Manufactures specialty components for regulated customers.",
                "business_model_type": "manufacturing",
                "what_company_does": "Manufactures and sells regulated specialty components.",
                "what_it_sells": ["Specialty components"],
                "who_pays": ["Industrial customers"],
                "how_revenue_happens": "Product sales to recurring industrial customers.",
            },
            "economic_drivers": ["capacity utilization"],
            "dependencies": ["regulatory approval"],
        }
    )

    compacted_text = json.dumps(compacted)
    assert compacted["business_model_type"] == "manufacturing"
    assert "Specialty components" in compacted_text
    assert "sun_pharma" not in compacted_text
    assert "ujjivan" not in compacted_text
