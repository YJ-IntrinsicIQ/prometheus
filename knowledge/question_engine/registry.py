from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .constants import DEFAULT_DNA_MODULE_MAPPINGS, QUESTION_MODULE_ALIASES
from .module import default_modules
from .schema import QuestionModule
from .validator import QuestionEngineValidationError, validate_modules


def _normalize(value: str) -> str:
    return value.strip().lower()


class QuestionRegistry:
    def __init__(
        self,
        modules: Iterable[QuestionModule] | None = None,
        dna_module_mappings: List[Dict[str, Any]] | None = None,
        module_aliases: Dict[str, str] | None = None,
    ):
        module_list = list(
            modules or default_modules()
        )
        self._dna_module_mappings = dna_module_mappings or DEFAULT_DNA_MODULE_MAPPINGS
        self._module_aliases = module_aliases or QUESTION_MODULE_ALIASES

        validate_modules(
            module_list
        )

        self._modules = {
            module.module_id: module
            for module in module_list
        }

    def module_ids(self) -> List[str]:
        return sorted(
            self._modules
        )

    def get_module(self, module_id: str) -> QuestionModule:
        resolved = self.resolve_module_id(module_id)

        if resolved not in self._modules:
            raise QuestionEngineValidationError(
                f"Unknown question module: {module_id}"
            )

        return self._modules[resolved]

    def resolve_module_id(self, module_id: str) -> str:
        normalized = _normalize(module_id)

        return self._module_aliases.get(
            normalized,
            normalized,
        )

    def modules_for_dnas(self, business_dnas: Iterable[str]) -> List[QuestionModule]:
        normalized_dnas = {
            _normalize(dna)
            for dna in business_dnas
            if dna and dna.strip()
        }

        module_ids = []

        for mapping in self._dna_module_mappings:
            mapping_dnas = {
                _normalize(dna)
                for dna in mapping.get("business_dnas", [])
                if dna and dna.strip()
            }

            if not normalized_dnas.intersection(mapping_dnas):
                continue

            for module_id in mapping.get("module_ids", []):
                resolved = self.resolve_module_id(module_id)

                if resolved in self._modules:
                    module_ids.append(resolved)

        return [
            self._modules[module_id]
            for module_id in dict.fromkeys(module_ids)
        ]

    def modules_for_classification(self, classification: Dict[str, Any]) -> List[QuestionModule]:
        modules = self.modules_for_dnas(
            classification.get("business_dnas", [])
        )

        module_ids = [
            module.module_id
            for module in modules
        ]

        for module_id in classification.get("question_modules", []):
            resolved = self.resolve_module_id(module_id)

            if resolved in self._modules:
                module_ids.append(resolved)

        return [
            self._modules[module_id]
            for module_id in dict.fromkeys(module_ids)
        ]
