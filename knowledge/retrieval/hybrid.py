from __future__ import annotations

from typing import List, Dict, Any, Optional, Sequence

from .bm25 import BM25
from .schema import RetrievedChunk, RetrievalResult
from .constants import DEFAULT_TOP_K, SEMANTIC_WEIGHT, BM25_WEIGHT


def merge_results(
    semantic_results: Sequence[Dict[str, Any]],
    bm25_results: Sequence[Dict[str, Any]],
    top_k: int = DEFAULT_TOP_K,
) -> List[Dict[str, Any]]:
    aggregate = {}
    for item in semantic_results:
        chunk_id = item["chunk_id"]
        aggregate[chunk_id] = {
            "chunk_id": chunk_id,
            "text": item["text"],
            "metadata": item.get("metadata", {}),
            "score": item.get("score", 0.0) * SEMANTIC_WEIGHT,
        }

    for item in bm25_results:
        chunk_id = item["chunk_id"]
        if chunk_id not in aggregate:
            aggregate[chunk_id] = {
                "chunk_id": chunk_id,
                "text": item["text"],
                "metadata": item.get("metadata", {}),
                "score": 0.0,
            }
        aggregate[chunk_id]["score"] += item.get("score", 0.0) * BM25_WEIGHT

    ordered = sorted(aggregate.values(), key=lambda item: item["score"], reverse=True)
    return ordered[:top_k]
