import json

import pytest

from knowledge.ai.input_packs import (
    build_llm_input_pack,
    validate_llm_input_pack,
)


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
