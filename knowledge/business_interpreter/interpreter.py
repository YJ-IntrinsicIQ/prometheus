from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from knowledge.business_blueprint import BusinessBlueprint
from knowledge.company_memory import CompanyMemory

from .parser import ParserError, parse_interpretation_payload
from .prompt import build_prompt
from .validator import ValidationError, validate_blueprint_payload


class BusinessInterpreter:
    def __init__(self, company_memory: CompanyMemory, llm_client: Optional[Callable[[str], str]] = None):
        self.company_memory = company_memory
        self.llm_client = llm_client

    def interpret(self) -> BusinessBlueprint:
        if self.llm_client is None:
            raise ValueError("llm_client is required")

        prompt = build_prompt(self.company_memory)
        response = self.llm_client(prompt)

        blueprint = parse_interpretation_payload(response)
        return validate_blueprint_payload(blueprint.to_dict())
