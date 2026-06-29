from typing import Any, Dict, List

from .schema import RetrievedChunk, RetrievalResult


def validate_retrieval_result(result: RetrievalResult) -> None:
    if not isinstance(result.company, str) or not result.company.strip():
        raise ValueError("company must be a non-empty string")
    if not isinstance(result.module, str) or not result.module.strip():
        raise ValueError("module must be a non-empty string")
    if not isinstance(result.chunks, list):
        raise ValueError("chunks must be a list")

    for chunk in result.chunks:
        if not isinstance(chunk, RetrievedChunk):
            raise ValueError("each chunk must be a RetrievedChunk")
        if not isinstance(chunk.chunk_id, str) or not chunk.chunk_id.strip():
            raise ValueError("chunk_id must be a non-empty string")
        if not isinstance(chunk.text, str) or not chunk.text.strip():
            raise ValueError("text must be a non-empty string")
        if not isinstance(chunk.metadata, dict):
            raise ValueError("metadata must be a dict")
