from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from knowledge.module_extractor.schema import ModuleExtractionResult
from knowledge.question_engine.schema import DiscoveryPlan


@dataclass(frozen=True)
class ExecutionStatistics:
    modules_executed: int
    questions_asked: int
    questions_answered: int
    questions_not_found: int
    average_confidence: float
    execution_time_seconds: float
    retrieved_chunks: int
    llm_calls: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "modules_executed": self.modules_executed,
            "questions_asked": self.questions_asked,
            "questions_answered": self.questions_answered,
            "questions_not_found": self.questions_not_found,
            "average_confidence": self.average_confidence,
            "execution_time_seconds": self.execution_time_seconds,
            "retrieved_chunks": self.retrieved_chunks,
            "llm_calls": self.llm_calls,
        }


@dataclass(frozen=True)
class DiscoveryResult:
    business_classification: Dict[str, Any]
    executed_modules: List[str]
    module_results: List[ModuleExtractionResult]
    statistics: ExecutionStatistics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_classification": dict(self.business_classification),
            "executed_modules": list(self.executed_modules),
            "module_results": [result.to_dict() for result in self.module_results],
            "statistics": self.statistics.to_dict(),
        }
