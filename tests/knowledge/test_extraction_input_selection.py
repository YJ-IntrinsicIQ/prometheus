from knowledge.evidence_layer import select_discovery_chunks


def test_macro_chunk_is_downranked_for_company_action_extraction():
    chunks = [
        {
            "chunk": "The global economy and industry outlook remain uncertain due to macro conditions and policy support.",
            "page": 4,
        },
        {
            "chunk": "The Company commissioned a new facility in FY2025 with Rs 120 crore of investment.",
            "page": 18,
        },
    ]

    selected, metadata = select_discovery_chunks(
        chunks,
        module_name="projects",
        positive_patterns=["commissioned", "facility"],
        negative_patterns=["industry outlook"],
    )

    assert len(selected) == 1
    assert "commissioned a new facility" in selected[0]["chunk"]
    assert metadata["chunks_seen"] == 2
    assert metadata["chunks_selected"] == 1


def test_duplicate_chunks_are_suppressed_before_llm_selection():
    repeated = "The Company launched a new product line in FY2025 with Rs 20 crore budget."
    chunks = [
        {"chunk": repeated, "page": 10},
        {"chunk": repeated, "page": 10},
        {"chunk": "The Company expects to expand the line next year.", "page": 11},
    ]

    selected, metadata = select_discovery_chunks(
        chunks,
        module_name="initiatives",
        positive_patterns=["launched", "expand"],
        negative_patterns=[],
    )

    assert len(selected) == 2
    rejected = [reason for reason in metadata["selection_reasons"] if reason["decision"] == "rejected"]
    assert any(reason["reason"] == "duplicate_chunk" for reason in rejected)


def test_selection_respects_budget_caps():
    chunks = [
        {"chunk": f"The Company approved project {idx} in FY2025 with Rs {idx} crore capex.", "page": idx}
        for idx in range(1, 8)
    ]

    selected, metadata = select_discovery_chunks(
        chunks,
        module_name="capital_allocations",
        positive_patterns=["approved", "capex"],
        max_chunks=3,
        max_total_chars=400,
    )

    assert len(selected) <= 3
    assert metadata["budget_applied"] is True
