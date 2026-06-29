from knowledge.company_memory import CompanyMemoryBuilder, validate_memory


def test_builder_adds_entities_events_and_evidence():
    existing = None
    new_document = {
        "company_id": "acme",
        "entities": [
            {
                "name": "Plant A",
                "entity_type": "facility",
                "events": [
                    {
                        "event_type": "announced",
                        "summary": "Construction announced",
                        "evidence": [
                            {
                                "source": "Annual Report",
                                "source_type": "annual_report",
                                "content": "Construction announced in annual report"
                            }
                        ],
                    }
                ],
            }
        ],
    }

    memory = CompanyMemoryBuilder(existing, new_document).build()

    assert memory.company_id == "acme"
    assert len(memory.entities) == 1
    assert len(memory.events) == 1
    assert len(memory.evidence) == 1
    assert memory.entities["Plant A"].id is not None

    errors = validate_memory(memory)
    assert errors == []
