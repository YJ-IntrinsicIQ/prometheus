from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from knowledge.business_blueprint import BusinessBlueprint
from knowledge.company_memory import CompanyMemory

from .parser import ParserError, parse_interpretation_bundle
from .prompt import build_input_pack, build_prompt
from .validator import ValidationError, validate_blueprint_payload


@dataclass
class BusinessInterpretationResult:
    blueprint: BusinessBlueprint
    classification: Optional[Dict[str, object]] = None


class BusinessInterpreter:
    def __init__(self, company_memory: CompanyMemory, llm_client: Optional[Callable[[str], str]] = None):
        self.company_memory = company_memory
        self.llm_client = llm_client

    def interpret(self, classification_context: Optional[Dict[str, object]] = None) -> BusinessInterpretationResult:
        if self.llm_client is None:
            raise ValueError("llm_client is required")

        llm_input_pack = build_input_pack(
            self.company_memory,
            classification_context=classification_context,
        )
        prompt = build_prompt(
            self.company_memory,
            classification_context=classification_context,
            llm_input_pack=llm_input_pack,
        )
        try:
            response = self.llm_client(prompt, llm_input_pack=llm_input_pack)
        except TypeError:
            response = self.llm_client(prompt)

        interpretation = parse_interpretation_bundle(response)
        blueprint, classification = validate_blueprint_payload(
            {
                **interpretation.blueprint.to_dict(),
                **({"classification": interpretation.classification} if interpretation.classification is not None else {}),
            }
        )
        return BusinessInterpretationResult(
            blueprint=blueprint,
            classification=classification,
        )
