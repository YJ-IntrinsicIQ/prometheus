import json
import re
from pathlib import Path

from intelligence.investor_panel.company_memory_context import (
    _compact_company_model,
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
