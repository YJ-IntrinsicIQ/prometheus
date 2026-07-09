from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class ModuleAnswer:
    question_id: str
    question: str

    direct_answer: str

    supporting_points: List[str] = field(default_factory=list)

    primary_evidence: List[str] = field(default_factory=list)

    secondary_evidence: List[str] = field(default_factory=list)

    confidence: float = 0.0

    status: str = "FOUND"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "direct_answer": self.direct_answer,
            "supporting_points": list(self.supporting_points),
            "primary_evidence": list(self.primary_evidence),
            "secondary_evidence": list(self.secondary_evidence),
            "confidence": self.confidence,
            "status": self.status,
        }


@dataclass(frozen=True)
class ModuleExtractionResult:
    module_id: str

    module_name: str

    answers: List[ModuleAnswer] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "module_name": self.module_name,
            "answers": [
                answer.to_dict()
                for answer in self.answers
            ],
        }