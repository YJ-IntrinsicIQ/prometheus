from __future__ import annotations

from typing import Optional

from .merger import merge_memory
from .schema import CompanyMemory


class CompanyMemoryBuilder:
    def __init__(self, existing_memory: Optional[CompanyMemory], new_document: dict):
        self.existing_memory = existing_memory
        self.new_document = new_document

    def build(self) -> CompanyMemory:
        return merge_memory(self.existing_memory, self.new_document)
