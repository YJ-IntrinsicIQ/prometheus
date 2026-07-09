import pytest

from knowledge.question_engine import (
    Question,
    QuestionEngineValidationError,
    QuestionModule,
    QuestionPlanner,
    QuestionRegistry,
    validate_modules,
)


def test_planner_builds_deterministic_discovery_plan():
    classification = {
        "business_dnas": ["Manufacturing", "Semiconductor", "Manufacturing"],
        "question_modules": ["capital_allocation", "technology"],
    }

    plan = QuestionPlanner().build_plan(classification)

    assert plan.business_dnas == ["Manufacturing", "Semiconductor"]
    assert plan.loaded_modules == ["capital_allocation", "technology"]
    assert len(plan.questions) == 12
    assert [
        question.priority
        for question in plan.questions
    ] == sorted(
        question.priority
        for question in plan.questions
    )

    payload = plan.to_dict()
    assert payload["business_dnas"] == ["Manufacturing", "Semiconductor"]
    assert payload["loaded_modules"] == ["capital_allocation", "technology"]
    assert payload["questions"][0]["id"]
    assert "expected_entity_types" in payload["questions"][0]


def test_planner_loads_ip_library_and_platform_modules_for_new_archetype():
    classification = {
        "business_dnas": ["IP Library", "Platform Monetization", "Export"],
        "question_modules": ["library_economics", "platform_dependency", "technology"],
    }

    plan = QuestionPlanner().build_plan(classification)

    assert plan.business_dnas == ["IP Library", "Platform Monetization", "Export"]
    assert plan.loaded_modules == [
        "technology",
        "library_economics",
        "platform_dependency",
    ]
    question_ids = [question.id for question in plan.questions]
    assert "library_economics.monetization_base" in question_ids
    assert "platform_dependency.concentration" in question_ids
    assert "technology.core_capabilities" in question_ids


def test_planner_loads_platform_modules_for_enterprise_platform_archetype():
    classification = {
        "business_dnas": ["Enterprise Platform", "Compliance Infrastructure", "Export"],
        "question_modules": [],
    }

    plan = QuestionPlanner().build_plan(classification)

    assert plan.loaded_modules == [
        "technology",
        "platform_dependency",
        "platform_economics",
        "compliance_infrastructure",
    ]
    question_ids = [question.id for question in plan.questions]
    assert "platform_economics.usage_scale" in question_ids
    assert "compliance_infrastructure.core_controls" in question_ids


def test_manufacturing_flow_still_loads_expected_modules():
    classification = {
        "business_dnas": ["Manufacturing", "Semiconductor"],
        "question_modules": ["capital_allocation", "technology"],
    }

    plan = QuestionPlanner().build_plan(classification)

    assert plan.loaded_modules == ["capital_allocation", "technology"]


def test_registry_is_data_driven_and_supports_custom_mapping():
    registry = QuestionRegistry(
        dna_module_mappings=[
            {
                "business_dnas": ["Custom DNA"],
                "module_ids": ["Technology"],
            }
        ]
    )

    modules = registry.modules_for_dnas(
        ["Custom DNA"]
    )

    assert [
        module.module_id
        for module in modules
    ] == ["technology"]


def test_planner_merges_duplicate_question_text_and_preserves_highest_priority():
    first = QuestionModule(
        module_id="first",
        module_name="First",
        description="First module",
        questions=[
            Question(
                id="first.same_question",
                module="first",
                priority=3,
                category="test",
                question="What matters most?",
                expected_entity_types=[],
                expected_event_types=[],
                output_type="structured",
            )
        ],
    )
    second = QuestionModule(
        module_id="second",
        module_name="Second",
        description="Second module",
        questions=[
            Question(
                id="second.same_question",
                module="second",
                priority=1,
                category="test",
                question="What matters most?",
                expected_entity_types=[],
                expected_event_types=[],
                output_type="structured",
            )
        ],
    )

    questions = QuestionPlanner()._merge_questions(
        [first, second]
    )

    assert len(questions) == 1
    assert questions[0].id == "second.same_question"
    assert questions[0].priority == 1


def test_validation_rejects_duplicate_question_ids():
    first = QuestionModule(
        module_id="first",
        module_name="First",
        description="First module",
        questions=[
            Question(
                id="duplicate",
                module="first",
                priority=1,
                category="test",
                question="First question?",
                output_type="structured",
            )
        ],
    )
    second = QuestionModule(
        module_id="second",
        module_name="Second",
        description="Second module",
        questions=[
            Question(
                id="duplicate",
                module="second",
                priority=1,
                category="test",
                question="Second question?",
                output_type="structured",
            )
        ],
    )

    with pytest.raises(QuestionEngineValidationError):
        validate_modules([first, second])


def test_validation_rejects_empty_module_and_invalid_priority():
    empty = QuestionModule(
        module_id="empty",
        module_name="Empty",
        description="Empty module",
        questions=[],
    )

    with pytest.raises(QuestionEngineValidationError):
        validate_modules([empty])

    invalid = QuestionModule(
        module_id="invalid",
        module_name="Invalid",
        description="Invalid priority",
        questions=[
            Question(
                id="invalid.priority",
                module="invalid",
                priority=99,
                category="test",
                question="Is this invalid?",
                output_type="structured",
            )
        ],
    )

    with pytest.raises(QuestionEngineValidationError):
        validate_modules([invalid])


def test_registry_rejects_duplicate_module_ids():
    first = QuestionModule(
        module_id="duplicate",
        module_name="First",
        description="First module",
        questions=[
            Question(
                id="first.question",
                module="duplicate",
                priority=1,
                category="test",
                question="First question?",
                output_type="structured",
            )
        ],
    )
    second = QuestionModule(
        module_id="duplicate",
        module_name="Second",
        description="Second module",
        questions=[
            Question(
                id="second.question",
                module="duplicate",
                priority=1,
                category="test",
                question="Second question?",
                output_type="structured",
            )
        ],
    )

    with pytest.raises(QuestionEngineValidationError):
        QuestionRegistry(modules=[first, second])
