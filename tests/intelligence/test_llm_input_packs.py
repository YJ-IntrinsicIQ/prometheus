import json

import pytest

from knowledge.ai.input_packs import (
    build_llm_input_pack,
    validate_llm_input_pack,
)
from knowledge.business_interpreter.prompt import build_input_pack
from knowledge.company_memory import CompanyMemory, Entity, Event


def test_validate_llm_input_pack_rejects_non_pack_payload():
    with pytest.raises(ValueError, match="missing required keys"):
        validate_llm_input_pack({"company": "syntheticco"})


def test_build_llm_input_pack_strips_source_chunk_and_validation_noise():
    pack = build_llm_input_pack(
        stage="business_understanding",
        purpose="Summarize synthetic business facts.",
        company="syntheticco",
        year="fy25",
        selected_input={
            "company_memory": {
                "facts": [
                    {
                        "summary": "Platform reliability focus",
                        "source_chunk": "raw chunk that should not leak",
                        "validation_report": {"status": "pass"},
                        "content_hash": "abc123",
                        "evidence_ids": ["ev_bu_1"],
                    }
                ]
            }
        },
        source_artifacts=["company_memory.json"],
    )

    payload = json.dumps(pack, ensure_ascii=False)
    assert '"source_chunk":' not in payload
    assert "validation_report" not in payload
    assert "content_hash" not in payload
    assert "ev_bu_1" in payload
    validate_llm_input_pack(pack, require_source_artifacts=True)


def test_extraction_pack_can_keep_source_text():
    pack = build_llm_input_pack(
        stage="extraction",
        purpose="Extract structured items from discovery chunks.",
        company="syntheticco",
        year="fy25",
        selected_input={"chunks": [{"chunk_id": "chunk_1", "text": "Original source text"}]},
        observations=[{"chunks": [{"chunk_id": "chunk_1", "text": "Original source text"}]}],
        source_artifacts=["project_discovery_results.json"],
    )

    payload = json.dumps(pack, ensure_ascii=False)
    assert "Original source text" in payload
    validate_llm_input_pack(pack, require_source_artifacts=True)


def test_budget_enforcement_preserves_evidence_ids_and_limitations(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_LLM_BUDGET_BUSINESS_UNDERSTANDING", "120")
    observations = []
    for idx in range(12):
        observations.append(
            {
                "value": f"Observation {idx}",
                "summary": "Very long synthetic summary " * 15,
                "evidence_ids": [f"ev_{idx}"],
            }
        )

    pack = build_llm_input_pack(
        stage="business_understanding",
        purpose="Summarize many synthetic observations.",
        company="budgetco",
        year="fy25",
        observations=observations,
        limitations=["Synthetic limitation should survive."],
        source_artifacts=["company_memory.json"],
    )

    assert pack["metadata"]["truncation_applied"] is True
    assert pack["limitations"] == ["Synthetic limitation should survive."]
    assert pack["evidence_ids"]
    assert pack["metadata"]["tokens_estimated"] <= 120 or pack["metadata"]["warnings"]


def test_business_intelligence_pack_compacts_chunks_below_budget(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_LLM_BUDGET_BUSINESS_INTELLIGENCE", "500")
    chunks = []
    for idx in range(12):
        chunks.append(
            {
                "chunk_id": f"chunk_{idx}",
                "text": ("The company commissioned a facility in FY2025 with Rs 80 crore capex. " * 30),
                "retrieval_score": 0.2,
                "page": idx + 1,
                "year": "fy25",
                "evidence_ids": [f"ev_{idx}"],
                "evidence_quality": {
                    "company_specificity": "low" if idx < 10 else "high",
                    "actor_type": "industry" if idx < 10 else "company",
                },
            }
        )
    chunks[-1]["text"] = "Management commissioned a new line in FY2025 with Rs 80 crore capex and evidence id ev_keep."
    chunks[-1]["retrieval_score"] = 0.99
    chunks[-1]["evidence_ids"] = ["ev_keep"]

    pack = build_llm_input_pack(
        stage="business_intelligence",
        purpose="Answer business intelligence questions.",
        company="syntheticco",
        year="fy25",
        selected_input={
            "module": {"module_id": "capital_allocation", "module_name": "Capital Allocation"},
            "questions": [{"question_id": "q1", "question": "What major capital allocation decisions has management made?"}],
            "chunks": chunks,
        },
        facts=[{"business_dnas": ["Manufacturing", "Semiconductor"]}],
        source_artifacts=["retrieval_chunks"],
    )

    payload = json.dumps(pack, ensure_ascii=False)
    assert pack["metadata"]["truncation_applied"] is True
    assert pack["metadata"]["tokens_estimated"] <= 500
    assert "ev_keep" in payload
    assert '"business_dnas": ["Manufacturing", "Semiconductor"]' in payload
    assert pack["metadata"]["truncation_details"]["chunks_before"] == 12
    assert pack["metadata"]["truncation_details"]["chunks_after"] < 12
    assert pack["metadata"]["truncation_details"]["dropped_chunk_count"] > 0


def test_business_intelligence_pack_preserves_highest_ranked_chunks(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_LLM_BUDGET_BUSINESS_INTELLIGENCE", "300")
    pack = build_llm_input_pack(
        stage="business_intelligence",
        purpose="Answer business intelligence questions.",
        company="syntheticco",
        year="fy25",
        selected_input={
            "module": {"module_id": "technology", "module_name": "Technology"},
            "questions": [{"question_id": "q1", "question": "What operating signals matter most?"}],
            "chunks": [
                {
                    "chunk_id": "macro_1",
                    "text": "The global economy remains uncertain and industry outlook is mixed. " * 20,
                    "retrieval_score": 0.1,
                    "evidence_quality": {"company_specificity": "low", "actor_type": "industry"},
                },
                {
                    "chunk_id": "keep_1",
                    "text": "Management launched a named platform in FY2025 with 120 customers and Rs 40 crore revenue.",
                    "retrieval_score": 0.9,
                    "page": 7,
                    "year": "fy25",
                    "evidence_ids": ["ev_keep_1"],
                    "evidence_quality": {"company_specificity": "high", "actor_type": "company"},
                },
            ],
        },
        source_artifacts=["retrieval_chunks"],
    )

    chunks = pack["observations"][0]["chunks"]
    assert any(chunk["chunk_id"] == "keep_1" for chunk in chunks)
    assert all(len(chunk["text"]) <= 900 for chunk in chunks)


def test_investor_panel_pack_recursively_compacts_nested_payload(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_LLM_BUDGET_INVESTOR_PANEL_ANALYST", "700")
    long_text = "Long nested value from selected PCIM. " * 60
    pack = build_llm_input_pack(
        stage="investor_panel_analyst",
        purpose="Produce doctrine-bound investor analysis.",
        company="syntheticco",
        year=None,
        observations=[
            {
                "selected_pcim": {
                    "risk_inputs": {
                        "risk_by_year": [
                            {
                                "year": "fy25",
                                "items": [
                                    {
                                        "value": f"Risk item {idx}",
                                        "source_chunk": long_text,
                                        "raw_text": long_text,
                                        "evidence_ids": [f"ev_{idx}_{j}" for j in range(10)],
                                        "evidence_references": [
                                            {
                                                "source_chunk": long_text,
                                                "page": idx,
                                                "source_artifact": "company_intelligence.json",
                                                "evidence_ids": [f"ev_{idx}_0"],
                                            }
                                        ],
                                    }
                                    for idx in range(8)
                                ],
                            }
                        ]
                    }
                }
            }
        ],
        limitations=["Keep doctrine limitations."],
        source_artifacts=["pcim_v1.json"],
    )

    payload = json.dumps(
        {
            "facts": pack["facts"],
            "observations": pack["observations"],
            "limitations": pack["limitations"],
            "evidence_ids": pack["evidence_ids"],
        },
        ensure_ascii=False,
    )
    assert "source_chunk" not in payload
    assert "raw_text" not in payload
    assert "evidence_references" not in payload
    assert pack["metadata"]["truncation_applied"] is True
    assert pack["limitations"] == ["Keep doctrine limitations."]
    assert pack["metadata"]["tokens_estimated"] <= 700 or pack["metadata"]["warnings"]
    risk_items = pack["observations"][0]["selected_pcim"]["risk_inputs"]["risk_by_year"][0]["items"]
    assert len(risk_items) <= 3
    assert len(risk_items[0]["evidence_ids"]) <= 5


@pytest.mark.parametrize(
    ("company", "year", "fact"),
    [
        ("synthetic_manufacturing", "fy24", "Capacity expansion project"),
        ("synthetic_media", "fy25", "Rights monetization initiative"),
    ],
)
def test_input_pack_builder_is_generic_across_synthetic_companies(company, year, fact):
    pack = build_llm_input_pack(
        stage="business_understanding",
        purpose="Summarize synthetic observations.",
        company=company,
        year=year,
        facts=[{"summary": fact}],
        source_artifacts=["company_memory.json"],
    )

    assert pack["company"] == company
    assert pack["year"] == year
    assert pack["facts"][0]["summary"] == fact


def test_business_understanding_input_pack_excludes_source_chunks_and_debug_metadata():
    memory = CompanyMemory(company_id="syntheticco")
    entity = Entity(id="entity-1", name="Synthetic Co", entity_type="company")
    memory.entities[entity.name] = entity
    memory.events["evt-1"] = Event(
        id="evt-1",
        entity_id=entity.id,
        event_type="initiative",
        summary="API-led platform expansion",
        evidence_ids=["ev_1"],
        metadata={"source_chunk": "do not leak", "validation_report": {"status": "pass"}, "content_hash": "abc"},
    )

    pack = build_input_pack(
        memory,
        classification_context={
            "allowed_dnas": ["Enterprise Platform"],
            "candidate_archetypes": [{"archetype_id": "enterprise_platform"}],
            "source_manifest": {"status": "warning"},
        },
    )

    payload = json.dumps(pack, ensure_ascii=False)
    assert '"source_chunk":' not in payload
    assert "validation_report" not in payload
    assert '"content_hash"' not in payload
    assert pack["metadata"]["source_artifacts"] == ["company_memory.json", "business_classification_context"]
