from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .registry import QuestionRegistry
from .schema import DiscoveryPlan, Question, QuestionModule
from .validator import validate_discovery_plan


def _unique_preserve_order(values: Iterable[str]) -> List[str]:
    return list(
        dict.fromkeys(
            value
            for value in values
            if value
        )
    )


class QuestionPlanner:
    def __init__(self, registry: QuestionRegistry | None = None):
        self.registry = registry or QuestionRegistry()

    def build_plan(self, business_classification: Dict[str, Any]) -> DiscoveryPlan:
        business_dnas = _unique_preserve_order(
            business_classification.get("business_dnas", [])
        )

        modules = self.registry.modules_for_classification(
            business_classification
        )

        questions = self._merge_questions(
            modules
        )

        plan = DiscoveryPlan(
            business_dnas=business_dnas,
            loaded_modules=[
                module.module_id
                for module in modules
            ],
            questions=questions,
        )

        validate_discovery_plan(plan)

        return plan

    def _merge_questions(self, modules: Iterable[QuestionModule]) -> List[Question]:
        question_by_text = {}

        for module in modules:
            for question in module.questions:
                key = question.question.strip().lower()

                if key not in question_by_text:
                    question_by_text[key] = question
                    continue

                existing = question_by_text[key]

                if question.priority < existing.priority:
                    question_by_text[key] = question

        return sorted(
            question_by_text.values(),
            key=lambda question: (
                question.priority,
                question.module,
                question.id,
            ),
        )
