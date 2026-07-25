from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from knowledge.module_extractor import ModuleExtractor
from knowledge.module_extractor.schema import ModuleExtractionResult
from knowledge.question_engine import QuestionRegistry
from knowledge.question_engine.schema import DiscoveryPlan, QuestionModule

from .merger import ModuleMerger
from .schema import DiscoveryResult, ExecutionStatistics


class _FallbackLLMClient:
    def __call__(self, prompt: str) -> str:
        return json.dumps({"module_id": "", "module_name": "", "answers": []})


class DiscoveryRuntime:
    def __init__(
        self,
        retriever: Optional[Any] = None,
        extractor: Optional[ModuleExtractor] = None,
        module_definitions: Optional[List[QuestionModule]] = None,
    ):
        self.retriever = retriever
        if extractor is None:
            self.extractor = ModuleExtractor(llm_client=_FallbackLLMClient())
        else:
            self.extractor = extractor
            if getattr(self.extractor, "llm_client", None) is None:
                self.extractor.llm_client = _FallbackLLMClient()
        self.module_definitions = module_definitions or []
        self.module_registry = QuestionRegistry()

    def run(self, plan: DiscoveryPlan, business_classification: Optional[Dict[str, Any]] = None) -> DiscoveryResult:
        if not isinstance(plan, DiscoveryPlan):
            raise TypeError("plan must be a DiscoveryPlan")

        started_at = time.time()
        executed_modules: List[str] = []
        module_results: List[ModuleExtractionResult] = []
        questions_asked = 0
        questions_answered = 0
        questions_not_found = 0
        total_confidence = 0.0
        retrieved_chunks = 0
        llm_calls = 0

        module_lookup = {module.module_id: module for module in self.module_definitions}
        if not module_lookup and hasattr(plan, "questions"):
            module_lookup = {}

        business_company = None
        business_year = None
        if isinstance(business_classification, dict):
            business_company = business_classification.get("company") or business_classification.get("company_name")
            business_year = business_classification.get("year") or business_classification.get("report_year")

        max_chunks_per_question = _resolve_positive_int_env("BI_MAX_CHUNKS_PER_QUESTION")
        if max_chunks_per_question is not None:
            print(
                f"[BUSINESS INTELLIGENCE] BI_MAX_CHUNKS_PER_QUESTION active: "
                f"capped to {max_chunks_per_question}"
            )

        for module_id in getattr(plan, "loaded_modules", []):
            if not isinstance(module_id, str) or not module_id.strip():
                continue
            executed_modules.append(module_id)

            module = None
            if hasattr(self, "module_registry") and self.module_registry:
                try:
                    module = self.module_registry.get_module(module_id)
                except Exception:
                    module = None
            if module is None:
                module = module_lookup.get(module_id)
            if module is None:
                raise ValueError(f"No module definition found for {module_id}")

            if self.retriever is not None and hasattr(self.retriever, "build_company_index"):
                try:
                    print("=" * 60)
                    print("[DEBUG] Building Company Index")
                    print(f"Company: {business_company!r}")
                    print(f"Year   : {business_year!r}")
                    print("=" * 60)

                    self.retriever.build_company_index(
                        company=business_company or "",
                        year=business_year or "",
                    )
                except Exception as exc:
                    print(f"[WARNING] Unable to build retriever index: {exc}")

            questions_asked += len(module.questions)
            retrieved = []

            if self.retriever is not None and hasattr(self.retriever, "retrieve"):
                for question in module.questions:
                    try:
                        result = self.retriever.retrieve(
                            query=question.question,
                            top_k=10,
                        )
                        question_chunks = list(getattr(result, "chunks", []))
                        if max_chunks_per_question is not None and len(question_chunks) > max_chunks_per_question:
                            print(
                                f"[BUSINESS INTELLIGENCE] question chunk cap active: "
                                f"retrieved={len(question_chunks)}, capped to {max_chunks_per_question} "
                                f"for question {question.id}"
                            )
                            question_chunks = question_chunks[:max_chunks_per_question]
                        retrieved.extend(question_chunks)
                    except Exception as exc:
                        print(f"[WARNING] Retrieval failed for {question.question}: {exc}")

            # Deduplicate by chunk_id
            unique_chunks = {}
            for chunk in retrieved:
                unique_chunks[chunk.chunk_id] = chunk

            retrieved = list(unique_chunks.values())

            retrieved_chunks += len(retrieved)

            llm_calls += 1
            if self.extractor is None:
                raise RuntimeError("extractor is required")
            if not retrieved:
                print(f"[WARNING] No chunks retrieved for module: {module.module_name}")
            result = self.extractor.extract(
                module,
                retrieved,
                business_context=business_classification or {},
            )
            module_results.append(result)
            questions_answered += len(result.answers)
            questions_not_found += sum(1 for answer in result.answers if answer.status == "NOT_FOUND")
            total_confidence += sum(answer.confidence for answer in result.answers)

        merged_results = ModuleMerger.merge_results(module_results)
        elapsed = max(0.0, time.time() - started_at)
        statistics = ExecutionStatistics(
            modules_executed=len(executed_modules),
            questions_asked=questions_asked,
            questions_answered=questions_answered,
            questions_not_found=questions_not_found,
            average_confidence=(total_confidence / questions_answered) if questions_answered else 0.0,
            execution_time_seconds=elapsed,
            retrieved_chunks=retrieved_chunks,
            llm_calls=llm_calls,
        )
        return DiscoveryResult(
            business_classification=business_classification or {},
            executed_modules=executed_modules,
            module_results=merged_results,
            statistics=statistics,
        )


def _resolve_positive_int_env(name: str) -> Optional[int]:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return None

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer when set") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than 0 when set")

    return value
