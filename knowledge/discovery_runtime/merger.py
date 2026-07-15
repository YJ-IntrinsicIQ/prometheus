from __future__ import annotations

from typing import List

from knowledge.module_extractor.schema import ModuleExtractionResult


class ModuleMerger:
    @staticmethod
    def merge_results(results: List[ModuleExtractionResult]) -> List[ModuleExtractionResult]:
        if not results:
            return []
        return [result for result in results if isinstance(result, ModuleExtractionResult)]
