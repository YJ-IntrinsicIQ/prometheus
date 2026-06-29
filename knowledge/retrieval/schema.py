from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    retrieval_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "retrieval_score": self.retrieval_score,
            "metadata": self.metadata,
        }


@dataclass
class RetrievalResult:
    company: str
    module: str
    chunks: List[RetrievedChunk] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "module": self.module,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
        }
