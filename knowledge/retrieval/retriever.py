from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional

from .bm25 import BM25
from .constants import DEFAULT_TOP_K, SEMANTIC_TOP_K, BM25_TOP_K
from .embedder import embed_texts
from .hybrid import merge_results
from .indexer import ChunkIndexer
from .loader import load_chunks_from_outputs
from .schema import RetrievedChunk, RetrievalResult


class HybridRetriever:
    def __init__(self, persist_directory: Optional[str] = None):
        self.indexer = ChunkIndexer(persist_directory=persist_directory)
        self._documents = []
        self._bm25 = None

    def build_index(self, chunks: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        documents = chunks or load_chunks_from_outputs()
        self._documents = [chunk["text"] for chunk in documents]
        self._bm25 = BM25(self._documents)
        self.indexer.clear()
        return self.indexer.index_chunks(documents)

    def search(self, query: str, top_k: int = DEFAULT_TOP_K) -> RetrievalResult:
        if not self._documents:
            self.build_index()

        semantic_results = self._semantic_search(query, top_k=SEMANTIC_TOP_K)
        bm25_results = self._bm25_search(query, top_k=BM25_TOP_K)
        merged = merge_results(semantic_results, bm25_results, top_k=top_k)

        chunks = [
            RetrievedChunk(
                chunk_id=item["chunk_id"],
                text=item["text"],
                retrieval_score=item["score"],
                metadata=item.get("metadata", {}),
            )
            for item in merged
        ]
        return RetrievalResult(company="unknown", module="retrieval", chunks=chunks)

    def _semantic_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        embedding = embed_texts([query])[0]
        result = self.indexer.collection.query(query_embeddings=[embedding], n_results=top_k)
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        scored = []
        for idx, doc in enumerate(docs):
            score = max(0.0, 1.0 - float(distances[idx])) if idx < len(distances) else 0.0
            scored.append({"chunk_id": ids[idx], "text": doc, "metadata": metas[idx], "score": score})
        return scored

    def _bm25_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        if self._bm25 is None:
            self.build_index()

        ranked = self._bm25.scores(query)
        ranked = sorted(ranked, key=lambda item: item[1], reverse=True)[:top_k]
        return [
            {
                "chunk_id": f"bm25-{idx}",
                "text": self._documents[idx],
                "metadata": {"source": "bm25"},
                "score": score,
            }
            for idx, score in ranked if score > 0.0
        ]
