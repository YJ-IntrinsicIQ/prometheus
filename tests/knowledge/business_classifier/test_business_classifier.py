from knowledge.business_blueprint import BusinessBlueprint, BusinessCharacteristic, BusinessUnderstanding, Metadata
from knowledge.business_classifier import (
    ArchetypeDefinition,
    BusinessClassifier,
    ClassificationValidationError,
    Registry,
    validate_classification,
)
from knowledge.business_classifier.semantic import SemanticSimilarityResult
from knowledge.company_memory import CompanyMemory, Entity, Event


def build_blueprint() -> BusinessBlueprint:
    return BusinessBlueprint(
        metadata=Metadata(company="Acme"),
        business_understanding=BusinessUnderstanding(
            business_summary="Manufactures advanced equipment using wafer-based process technology",
            business_model="B2B semiconductor components manufacturing",
        ),
        characteristics=[
            BusinessCharacteristic(name="Capital Intensive", confidence=0.9),
            BusinessCharacteristic(name="Advanced Manufacturing", confidence=0.8),
            BusinessCharacteristic(name="Asset Heavy", confidence=0.85),
        ],
    )


def test_classifier_returns_deterministic_profile():
    classifier = BusinessClassifier()
    classification = classifier.classify(build_blueprint())

    assert classification["business_dnas"] == ["Manufacturing", "Semiconductor"]
    assert classification["question_modules"] == ["capital_allocation", "technology"]
    assert classification["discovery_profile"]["priority_entities"] == ["Plant", "Technology", "Research"]
    assert classification["extraction_profile"]["high_priority_sections"] == [
        "Operations",
        "Capex",
        "Technology",
        "R&D",
        "Intellectual Property",
    ]
    assert classification["report_template"] == "semiconductor_v1"


def test_registry_exposes_archetype_library_structure():
    registry = Registry()

    archetypes = registry.archetypes

    assert archetypes
    assert isinstance(archetypes[0], ArchetypeDefinition)
    manufacturing = next(
        archetype
        for archetype in archetypes
        if "Manufacturing" in archetype.dnas
    )
    assert manufacturing.definition
    assert manufacturing.signals.positive_signals
    assert manufacturing.defaults.discovery_profile["priority_entities"]


def test_classifier_maps_real_business_understanding_taxonomy():
    blueprint = BusinessBlueprint(
        metadata=Metadata(company="Polymatech"),
        business_understanding=BusinessUnderstanding(
            business_summary="Semiconductor manufacturer with automation and global expansion",
            business_model="Manufacturing and technology-led growth",
        ),
        characteristics=[
            BusinessCharacteristic(name="Global Expansion", confidence=0.95),
            BusinessCharacteristic(name="Energy Efficiency", confidence=0.94),
            BusinessCharacteristic(name="Advanced Manufacturing", confidence=0.93),
            BusinessCharacteristic(name="R&D Collaboration", confidence=0.92),
            BusinessCharacteristic(name="Financial Flexibility", confidence=0.91),
        ],
    )

    classification = BusinessClassifier().classify(blueprint)

    assert classification["business_dnas"] == ["Manufacturing", "Semiconductor", "Export"]
    assert classification["question_modules"] == ["capital_allocation", "technology"]
    assert classification["discovery_profile"]["priority_entities"] == [
        "Plant",
        "Technology",
        "Research",
        "Geography",
        "Customer",
    ]
    assert classification["report_template"] == "semiconductor_v1"


def test_classifier_detects_semiconductor_from_archetype_business_patterns():
    blueprint = BusinessBlueprint(
        metadata=Metadata(company="Polymatech"),
        business_understanding=BusinessUnderstanding(
            business_summary=(
                "Manufactures sapphire and silicon wafers, HTCC/LTCC packaged chips, "
                "and other electronics components for export markets."
            ),
            business_model=(
                "Capital-intensive semiconductor materials and components manufacturing "
                "with global distribution and export-led growth."
            ),
            value_creation="Scales wafer and packaged-chip output for international customers.",
            competitive_position="Global supplier of substrates and packaged chips with export dependence.",
        ),
        characteristics=[
            BusinessCharacteristic(
                name="Export-led revenue model with majority of revenue earned in foreign currency",
                confidence=0.95,
            ),
            BusinessCharacteristic(
                name="Capital-intensive capacity expansion via phased construction",
                confidence=0.92,
            ),
            BusinessCharacteristic(
                name="Strategic geographic diversification with U.S. investments",
                confidence=0.9,
            ),
        ],
    )

    classification = BusinessClassifier().classify(blueprint)

    assert classification["business_dnas"] == ["Manufacturing", "Semiconductor", "Export"]
    assert classification["question_modules"] == ["capital_allocation", "technology"]


def test_registry_matches_substring_variants_from_real_blueprint_phrases():
    blueprint = BusinessBlueprint(
        metadata=Metadata(company="Polymatech"),
        business_understanding=BusinessUnderstanding(
            business_summary="Semiconductor and electronics materials manufacturer expanding globally with advanced manufacturing.",
            business_model="Semiconductor materials manufacturing and export-led growth",
        ),
        characteristics=[
            BusinessCharacteristic(
                name="Global market expansion via overseas subsidiaries and acquisitions",
                confidence=0.95,
            ),
            BusinessCharacteristic(
                name="Advanced manufacturing and digitalization (AI, digital twin, precision automation)",
                confidence=0.94,
            ),
            BusinessCharacteristic(
                name="Strong sustainability and energy-efficiency agenda (net-zero 2035, measured kWh and ₹ savings)",
                confidence=0.93,
            ),
            BusinessCharacteristic(
                name="Active capital allocation (acquisitions, equity, debt, private placement) with some financial exposures",
                confidence=0.92,
            ),
            BusinessCharacteristic(
                name="Investment in domestic manufacturing capacity (Chhattisgarh land allotted)",
                confidence=0.91,
            ),
        ],
    )

    classification = BusinessClassifier().classify(blueprint)

    assert classification["business_dnas"] == ["Manufacturing", "Semiconductor", "Export"]
    assert classification["question_modules"] == ["capital_allocation", "technology"]


def test_registry_uses_broader_semiconductor_archetype_text_signals():
    registry = Registry()

    result = registry.build_profile(
        ["Capital-intensive capacity expansion"],
        texts=[
            "Supplies sapphire substrates, silicon wafers and chip packaging components.",
        ],
    )

    assert result["business_dnas"] == ["Manufacturing", "Semiconductor"]


def test_registry_profiles_do_not_leak_between_classifications():
    registry = Registry()

    export_result = registry.build_profile(
        ["Geographic expansion"],
        texts=["Revenue earned in foreign currency across export markets."],
    )
    semiconductor_result = registry.build_profile(
        ["Capital-intensive capacity expansion"],
        texts=["Supplies silicon wafers and HTCC packaged chips."],
    )

    assert export_result["business_dnas"] == ["Export"]
    assert semiconductor_result["business_dnas"] == ["Manufacturing", "Semiconductor"]
    assert semiconductor_result["question_modules"] == ["capital_allocation", "technology"]


def test_classifier_detects_ip_library_and_platform_monetization_archetype():
    blueprint = BusinessBlueprint(
        metadata=Metadata(company="Tips"),
        business_understanding=BusinessUnderstanding(
            business_summary=(
                "Builds and monetizes a large music catalogue through streaming platforms "
                "and a high-reach YouTube channel."
            ),
            business_model=(
                "Monetizes owned and licensed content via streaming, sync licensing, "
                "performance rights, digital licensing and audience-platform distribution."
            ),
            value_creation=(
                "Creates recurring revenue from evergreen catalogue assets, release cadence, "
                "and third-party digital platform reach."
            ),
            competitive_position=(
                "Catalogue-driven rights holder with strong platform presence but dependence "
                "on external platforms and piracy enforcement."
            ),
        ),
        characteristics=[
            BusinessCharacteristic(
                name="Large diversified music library with high release cadence",
                confidence=0.95,
            ),
            BusinessCharacteristic(
                name="Multi-channel rights monetization across sync licensing, performance rights and digital licensing",
                confidence=0.94,
            ),
            BusinessCharacteristic(
                name="High-reach owned-channel monetization through a major YouTube audience",
                confidence=0.93,
            ),
        ],
    )

    classification = BusinessClassifier().classify(blueprint)

    assert classification["business_dnas"] == ["IP Library", "Platform Monetization"]
    assert classification["question_modules"] == [
        "library_economics",
        "platform_dependency",
        "technology",
    ]
    assert classification["report_template"] == "media_v1"


def test_classifier_matches_varied_ip_library_platform_wording():
    registry = Registry()

    result = registry.build_profile(
        ["Recurring revenue from evergreen content assets"],
        texts=[
            (
                "The business monetizes a large owned content catalog through third-party "
                "streaming platforms, sync deals, performance rights, digital licensing, "
                "and audience reach on its YouTube channel."
            ),
        ],
    )

    assert result["business_dnas"] == ["Subscription", "IP Library", "Platform Monetization"]
    assert result["question_modules"] == [
        "library_economics",
        "platform_dependency",
        "technology",
    ]


def test_classifier_routes_enterprise_platform_and_compliance_infrastructure():
    blueprint = BusinessBlueprint(
        metadata=Metadata(company="Tanla"),
        business_understanding=BusinessUnderstanding(
            business_summary=(
                "Provides enterprise messaging and communications platforms with "
                "high-throughput API-led infrastructure and telco-integrated deployments."
            ),
            business_model=(
                "Monetizes enterprise platform usage across MaaP, RCS, WhatsApp Business, "
                "and omnichannel communications through partner-integrated deployments."
            ),
            value_creation=(
                "Improves secure communication workflows, platform reliability, and "
                "customer deployment speed through automation, observability, and scale."
            ),
            competitive_position=(
                "Differentiates through compliance and trust products, operator partnerships, "
                "and active-active platform resilience rather than hardware manufacturing."
            ),
        ),
        characteristics=[
            BusinessCharacteristic(
                name="Messaging-as-a-Platform leader with enterprise deployment scale",
                confidence=0.95,
            ),
            BusinessCharacteristic(
                name="Security and compliance-led product differentiation",
                confidence=0.94,
            ),
            BusinessCharacteristic(
                name="API-first platform architecture with active-active infrastructure and observability",
                confidence=0.93,
            ),
            BusinessCharacteristic(
                name="Regional expansion through telco partnerships",
                confidence=0.92,
            ),
        ],
    )

    classification = BusinessClassifier().classify(blueprint)

    assert classification["business_dnas"] == [
        "Enterprise Platform",
        "Compliance Infrastructure",
        "Export",
    ]
    assert classification["question_modules"] == [
        "technology",
        "platform_dependency",
        "platform_economics",
        "compliance_infrastructure",
    ]
    assert classification["report_template"] == "software_v1"


def test_classifier_does_not_route_platform_business_to_semiconductor_without_hardware_signals():
    registry = Registry()

    result = registry.build_profile(
        [
            "API-first platform architecture with automation-driven operational efficiency",
            "Security and compliance-led product differentiation",
        ],
        texts=[
            (
                "Enterprise communications platform with telco partnerships, active-active "
                "infrastructure, observability, and anti-phishing compliance products."
            ),
        ],
    )

    assert result["business_dnas"] == [
        "Enterprise Platform",
        "Compliance Infrastructure",
    ]
    assert "Semiconductor" not in result["business_dnas"]


def test_classifier_does_not_route_platform_dependence_alone_to_ip_library():
    registry = Registry()

    result = registry.build_profile(
        [
            "Messaging-as-a-Platform leader with enterprise deployment scale",
            "Global expansion via telco partnerships in Southeast Asia and established enterprise presence in UAE",
        ],
        texts=[
            (
                "Positioned as a scale-focused messaging and security platform supported by "
                "telco partnerships and regional expansion; risks include infrastructure "
                "scalability challenges, customer concentration and supply-chain dependence."
            ),
        ],
    )

    assert "IP Library" not in result["business_dnas"]
    assert "Platform Monetization" not in result["business_dnas"]


def test_registry_matches_contains_without_exact_string_equality():
    registry = Registry()

    result = registry.build_profile(
        ["Strong sustainability and energy-efficiency agenda across operations"]
    )

    assert result["business_dnas"] == ["Manufacturing"]
    assert result["question_modules"] == ["capital_allocation"]


def test_registry_can_be_extended_with_custom_mappings():
    registry = Registry([
        {
            "characteristics": ["Recurring Revenue"],
            "keyword_groups": [["recurring", "revenue"]],
            "dnas": ["Subscription"],
            "question_modules": ["Recurring Revenue"],
            "discovery_profile": {"priority_entities": ["Customer"], "priority_events": ["Renewal"]},
            "extraction_profile": {"high_priority_sections": ["Revenue"]},
            "report_template": "software_v1",
        }
    ])

    result = registry.build_profile(["Recurring Revenue"])

    assert result["business_dnas"] == ["Subscription"]
    assert result["question_modules"] == ["Recurring Revenue"]
    assert result["report_template"] == "software_v1"


def test_registry_preserves_legacy_mapping_compatibility_for_find_matches():
    registry = Registry()

    matches = registry.find_matches(
        ["Regional expansion through telco partnerships"],
        texts=["Enterprise communications platform with MaaP and operator partnerships."],
    )

    assert matches
    assert isinstance(matches[0], dict)
    assert all("dnas" in match for match in matches)


def test_classifier_builds_compact_candidate_context_from_company_memory():
    memory = CompanyMemory(company_id="tanla")
    entity = Entity(id="entity-1", name="Tanla", entity_type="company")
    memory.entities[entity.name] = entity
    memory.events["evt-1"] = Event(
        id="evt-1",
        entity_id=entity.id,
        event_type="initiative_1",
        summary="Enterprise messaging platform scaled through telco partnerships and API-first integrations.",
    )
    memory.events["evt-2"] = Event(
        id="evt-2",
        entity_id=entity.id,
        event_type="risk_1",
        summary="Security and compliance products reduce spam and phishing risk for enterprise customers.",
    )

    context = BusinessClassifier().build_candidate_context(memory, company="tanla", year="fy25")

    assert context["company"] == "tanla"
    assert context["year"] == "fy25"
    assert "Enterprise Platform" in context["allowed_dnas"]
    assert context["candidate_archetypes"]
    assert context["evidence_snippets"]
    assert context["candidate_scores"]


def test_candidate_context_ranks_tanla_toward_platform_and_compliance():
    memory = CompanyMemory(company_id="tanla")
    entity = Entity(id="entity-1", name="Tanla", entity_type="company")
    memory.entities[entity.name] = entity
    memory.events["evt-1"] = Event(
        id="evt-1",
        entity_id=entity.id,
        event_type="initiative_1",
        summary="Enterprise messaging platform scaled through telco partnerships, MaaP deployments, and API-first integrations.",
    )
    memory.events["evt-2"] = Event(
        id="evt-2",
        entity_id=entity.id,
        event_type="risk_1",
        summary="Security and compliance products reduce spam and phishing risk for enterprise customers with high-throughput platform operations.",
    )

    context = BusinessClassifier().build_candidate_context(memory, company="tanla", year="fy25")

    ranked_dnas = [candidate["dnas"][0] for candidate in context["candidate_archetypes"]]
    assert ranked_dnas[:2] == ["Enterprise Platform", "Compliance Infrastructure"]
    assert "IP Library" not in ranked_dnas
    assert context["candidate_scores"][0]["confidence"] > 0


def test_candidate_context_ranks_tips_toward_ip_library_and_platform_monetization():
    memory = CompanyMemory(company_id="tips")
    entity = Entity(id="entity-1", name="Tips", entity_type="company")
    memory.entities[entity.name] = entity
    memory.events["evt-1"] = Event(
        id="evt-1",
        entity_id=entity.id,
        event_type="initiative_1",
        summary="Large owned music catalogue monetized through streaming revenue, digital licensing, and royalties across third-party platforms.",
    )
    memory.events["evt-2"] = Event(
        id="evt-2",
        entity_id=entity.id,
        event_type="initiative_2",
        summary="YouTube audience reach and release cadence support recurring catalogue monetization and rights licensing.",
    )

    context = BusinessClassifier().build_candidate_context(memory, company="tips", year="fy24")

    ranked_dnas = [candidate["dnas"][0] for candidate in context["candidate_archetypes"]]
    assert ranked_dnas[0] == "IP Library"
    assert "Enterprise Platform" not in ranked_dnas[:2]


def test_candidate_context_ranks_polymatech_toward_manufacturing_and_semiconductor():
    memory = CompanyMemory(company_id="polymatech")
    entity = Entity(id="entity-1", name="Polymatech", entity_type="company")
    memory.entities[entity.name] = entity
    memory.events["evt-1"] = Event(
        id="evt-1",
        entity_id=entity.id,
        event_type="project_1",
        summary="New facility and plant expansion increase wafer and substrate manufacturing capacity through capex-led buildout.",
    )
    memory.events["evt-2"] = Event(
        id="evt-2",
        entity_id=entity.id,
        event_type="initiative_1",
        summary="Semiconductor materials and chip-packaging operations improve production throughput and export growth.",
    )

    context = BusinessClassifier().build_candidate_context(memory, company="polymatech", year="fy24")

    ranked_dnas = [candidate["dnas"][0] for candidate in context["candidate_archetypes"]]
    assert ranked_dnas[:2] == ["Manufacturing", "Semiconductor"]
    assert "Enterprise Platform" not in ranked_dnas


def test_candidate_context_rejects_false_positive_ip_library_for_platform_business():
    memory = CompanyMemory(company_id="tanla")
    entity = Entity(id="entity-1", name="Tanla", entity_type="company")
    memory.entities[entity.name] = entity
    memory.events["evt-1"] = Event(
        id="evt-1",
        entity_id=entity.id,
        event_type="initiative_1",
        summary="Enterprise communications platform with telco integrations, observability, and anti-phishing compliance products.",
    )

    context = BusinessClassifier().build_candidate_context(memory, company="tanla", year="fy25")

    rejected = {
        tuple(item["dnas"]): item["rejected_reason"]
        for item in context["rejected_candidates"]
    }
    assert ("IP Library", "Platform Monetization") in rejected
    assert rejected[("IP Library", "Platform Monetization")] in {
        "suppressed_by_negative_signals",
        "overpowered_by_neighboring_archetype",
        "weak_evidence_coverage",
        "insufficient_positive_support",
    }


def test_candidate_context_exposes_margin_and_ambiguity_metadata():
    memory = CompanyMemory(company_id="hybridco")
    entity = Entity(id="entity-1", name="HybridCo", entity_type="company")
    memory.entities[entity.name] = entity
    memory.events["evt-1"] = Event(
        id="evt-1",
        entity_id=entity.id,
        event_type="initiative_1",
        summary="Platform business with recurring revenue from enterprise contracts and API-led integrations.",
    )

    context = BusinessClassifier().build_candidate_context(memory, company="hybridco", year="fy25")

    assert "margin_to_next_candidate" in context
    assert "ambiguity_flag" in context
    assert all("score_breakdown" in item for item in context["candidate_scores"])


def test_candidate_context_exposes_semantic_fallback_metadata(monkeypatch):
    monkeypatch.setenv("BUSINESS_CLASSIFIER_ENABLE_SEMANTIC", "0")

    memory = CompanyMemory(company_id="tanla")
    entity = Entity(id="entity-1", name="Tanla", entity_type="company")
    memory.entities[entity.name] = entity
    memory.events["evt-1"] = Event(
        id="evt-1",
        entity_id=entity.id,
        event_type="initiative_1",
        summary="Enterprise messaging platform scaled through telco partnerships and API-first integrations.",
    )

    context = BusinessClassifier().build_candidate_context(memory, company="tanla", year="fy25")

    assert context["semantic_similarity_active"] is False
    assert context["semantic_backend"] == "disabled"
    assert context["semantic_disabled_reason"] == "BUSINESS_CLASSIFIER_ENABLE_SEMANTIC=0"
    assert all(
        item["score_breakdown"]["used_semantic_similarity"] is False
        for item in context["candidate_scores"]
    )


def test_candidate_context_uses_semantic_similarity_as_secondary_boost(monkeypatch):
    memory = CompanyMemory(company_id="catalogco")
    entity = Entity(id="entity-1", name="CatalogCo", entity_type="company")
    memory.entities[entity.name] = entity
    memory.events["evt-1"] = Event(
        id="evt-1",
        entity_id=entity.id,
        event_type="initiative_1",
        summary="Owned rights archive generates recurring monetization through downstream digital outlets and audience channels.",
    )

    classifier = BusinessClassifier()
    monkeypatch.setattr(
        classifier,
        "_compute_semantic_similarity",
        lambda evidence_snippets: SemanticSimilarityResult(
            active=True,
            backend="sentence_transformers",
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            disabled_reason=None,
            scores={
                "manufacturing": 0.18,
                "semiconductor": 0.12,
                "enterprise_platform": 0.26,
                "compliance_infrastructure": 0.14,
                "subscription": 0.41,
                "ip_library_platform_monetization": 0.91,
                "consumer_brand": 0.19,
                "export": 0.2,
            },
        ),
    )

    context = classifier.build_candidate_context(memory, company="catalogco", year="fy25")

    assert context["semantic_similarity_active"] is True
    assert context["candidate_scores"][0]["archetype_id"] == "ip_library_platform_monetization"
    assert context["candidate_scores"][0]["score_breakdown"]["semantic_boost"] > 0
    assert context["candidate_scores"][0]["score_breakdown"]["used_semantic_similarity"] is True


def test_semantic_similarity_does_not_override_family_support_gates(monkeypatch):
    memory = CompanyMemory(company_id="tanla")
    entity = Entity(id="entity-1", name="Tanla", entity_type="company")
    memory.entities[entity.name] = entity
    memory.events["evt-1"] = Event(
        id="evt-1",
        entity_id=entity.id,
        event_type="initiative_1",
        summary="Enterprise communications platform with telco integrations, observability, and anti-phishing compliance products.",
    )

    classifier = BusinessClassifier()
    monkeypatch.setattr(
        classifier,
        "_compute_semantic_similarity",
        lambda evidence_snippets: SemanticSimilarityResult(
            active=True,
            backend="sentence_transformers",
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            disabled_reason=None,
            scores={
                "manufacturing": 0.22,
                "semiconductor": 0.21,
                "enterprise_platform": 0.76,
                "compliance_infrastructure": 0.72,
                "subscription": 0.33,
                "ip_library_platform_monetization": 0.97,
                "consumer_brand": 0.2,
                "export": 0.31,
            },
        ),
    )

    context = classifier.build_candidate_context(memory, company="tanla", year="fy25")

    ranked_dnas = [candidate["dnas"][0] for candidate in context["candidate_archetypes"]]
    rejected = {
        tuple(item["dnas"]): item
        for item in context["rejected_candidates"]
    }

    assert ranked_dnas[:2] == ["Enterprise Platform", "Compliance Infrastructure"]
    assert ("IP Library", "Platform Monetization") in rejected
    assert rejected[("IP Library", "Platform Monetization")]["score_breakdown"]["semantic_similarity"] == 0.97


def test_classifier_finalizes_llm_selected_dnas_into_canonical_profile():
    blueprint = BusinessBlueprint(
        metadata=Metadata(company="Tanla"),
        business_understanding=BusinessUnderstanding(
            business_summary="Enterprise communications platform",
            business_model="API-first platform",
        ),
        characteristics=[BusinessCharacteristic(name="API-first platform architecture", confidence=0.9)],
    )

    classification = BusinessClassifier().finalize_classification(
        blueprint,
        {
            "selected_dnas": [
                {"name": "Enterprise Platform", "confidence": 0.9, "reason": "API-first platform evidence."},
                {"name": "Compliance Infrastructure", "confidence": 0.8, "reason": "Security product evidence."},
            ],
            "rejected_dnas": [
                {"name": "IP Library", "reason": "No content library evidence."},
            ],
            "rationale": ["Enterprise platform with embedded compliance layer."],
            "evidence_used": ["Enterprise communications platform"],
            "confidence": 0.86,
        },
        company="tanla",
        year="fy25",
    )

    assert classification["business_dnas"] == [
        "Enterprise Platform",
        "Compliance Infrastructure",
    ]
    assert classification["question_modules"] == [
        "technology",
        "platform_dependency",
        "platform_economics",
        "compliance_infrastructure",
    ]
    assert classification["report_template"] == "software_v1"
    assert classification["rejected_dnas"][0]["name"] == "IP Library"
    assert classification["company"] == "tanla"
    assert classification["year"] == "fy25"


def test_validator_rejects_duplicate_dnas():
    classification = {
        "business_dnas": ["Manufacturing", "Manufacturing"],
        "question_modules": ["Capex"],
        "discovery_profile": {"priority_entities": [], "priority_events": []},
        "extraction_profile": {"high_priority_sections": []},
        "report_template": "manufacturing_v1",
    }

    try:
        validate_classification(classification)
    except ClassificationValidationError as exc:
        assert "business_dnas" in str(exc)
    else:
        raise AssertionError("Expected validation failure")
