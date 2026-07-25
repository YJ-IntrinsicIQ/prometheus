from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from knowledge.question_engine.schema import QuestionModule

from .parser import ParserError, parse_module_extraction_payload
from .prompt import build_input_pack, build_prompt
from .schema import ModuleAnswer, ModuleExtractionResult


class ModuleExtractor:
    def __init__(self, llm_client: Optional[Any] = None, manifest_path: Optional[Path] = None):
        self.llm_client = llm_client
        self.manifest_path = manifest_path

    def extract(
        self,
        module: QuestionModule,
        chunks: List[dict],
        *,
        business_context: Optional[dict] = None,
    ) -> ModuleExtractionResult:
        if not isinstance(module, QuestionModule):
            raise TypeError("module must be a QuestionModule")
        if not isinstance(chunks, list):
            raise TypeError("chunks must be a list")
        if not self.llm_client:
            raise RuntimeError("llm_client is required")

        llm_input_pack = build_input_pack(module, chunks, business_context=business_context)
        prompt = build_prompt(module, chunks, llm_input_pack=llm_input_pack)
        try:
            response = self.llm_client(prompt, llm_input_pack=llm_input_pack)
        except TypeError:
            response = self.llm_client(prompt)
        if not isinstance(response, str) or not response.strip():
            raise ValueError("llm_client returned an empty response")

        try:
            return parse_module_extraction_payload(response)
        except ParserError:
            answers = [
                ModuleAnswer(
                    question_id=question.id,
                    question=question.question,
                    direct_answer="No answer generated in fallback mode.",
                    supporting_points=[],
                    primary_evidence=[],
                    secondary_evidence=[],
                    confidence=0.0,
                    status="UNCERTAIN",
                )
                for question in module.questions
            ]
            return ModuleExtractionResult(
                module_id=module.module_id,
                module_name=module.module_name,
                answers=answers,
            )
