from __future__ import annotations

from typing import Iterable

from .constants import VALID_OUTPUT_TYPES, VALID_PRIORITIES
from .schema import DiscoveryPlan, Question, QuestionModule


class QuestionEngineValidationError(ValueError):
    pass


def validate_question(question: Question) -> None:
    if not question.id or not question.id.strip():
        raise QuestionEngineValidationError("Question id is required")

    if not question.module or not question.module.strip():
        raise QuestionEngineValidationError("Question module is required")

    if question.priority not in VALID_PRIORITIES:
        raise QuestionEngineValidationError("Question priority is invalid")

    if not question.category or not question.category.strip():
        raise QuestionEngineValidationError("Question category is required")

    if not question.question or not question.question.strip():
        raise QuestionEngineValidationError("Question text is required")

    if question.output_type not in VALID_OUTPUT_TYPES:
        raise QuestionEngineValidationError("Question output_type is invalid")


def validate_modules(modules: Iterable[QuestionModule]) -> None:
    module_ids = set()
    question_ids = set()
    question_texts = set()

    for module in modules:
        if not module.module_id or not module.module_id.strip():
            raise QuestionEngineValidationError("Module id is required")

        if module.module_id in module_ids:
            raise QuestionEngineValidationError("Module ids must be unique")

        module_ids.add(module.module_id)

        if not module.questions:
            raise QuestionEngineValidationError("Every module must contain at least one question")

        for question in module.questions:
            validate_question(question)

            if question.module != module.module_id:
                raise QuestionEngineValidationError("Question module must match parent module")

            if question.id in question_ids:
                raise QuestionEngineValidationError("Question ids must be unique")

            question_ids.add(question.id)

            normalized_text = question.question.strip().lower()
            if normalized_text in question_texts:
                raise QuestionEngineValidationError("Question texts must be unique")

            question_texts.add(normalized_text)


def validate_discovery_plan(plan: DiscoveryPlan) -> None:
    if len(plan.business_dnas) != len(set(plan.business_dnas)):
        raise QuestionEngineValidationError("Discovery plan business_dnas must be unique")

    if len(plan.loaded_modules) != len(set(plan.loaded_modules)):
        raise QuestionEngineValidationError("Discovery plan loaded_modules must be unique")

    question_ids = set()
    question_texts = set()

    for question in plan.questions:
        validate_question(question)

        if question.id in question_ids:
            raise QuestionEngineValidationError("Discovery plan question ids must be unique")

        question_ids.add(question.id)

        normalized_text = question.question.strip().lower()
        if normalized_text in question_texts:
            raise QuestionEngineValidationError("Discovery plan questions must be unique")

        question_texts.add(normalized_text)
