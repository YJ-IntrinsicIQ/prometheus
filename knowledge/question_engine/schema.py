from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class Question:
    id: str
    module: str
    priority: int
    category: str
    question: str
    expected_entity_types: List[str] = field(default_factory=list)
    expected_event_types: List[str] = field(default_factory=list)
    output_type: str = "structured"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "module": self.module,
            "priority": self.priority,
            "category": self.category,
            "question": self.question,
            "expected_entity_types": list(self.expected_entity_types),
            "expected_event_types": list(self.expected_event_types),
            "output_type": self.output_type,
        }


@dataclass(frozen=True)
class QuestionModule:
    module_id: str
    module_name: str
    description: str
    questions: List[Question]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "module_name": self.module_name,
            "description": self.description,
            "questions": [
                question.to_dict()
                for question in self.questions
            ],
        }


@dataclass(frozen=True)
class DiscoveryPlan:
    business_dnas: List[str]
    loaded_modules: List[str]
    questions: List[Question]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_dnas": list(self.business_dnas),
            "loaded_modules": list(self.loaded_modules),
            "questions": [
                question.to_dict()
                for question in self.questions
            ],
        }
