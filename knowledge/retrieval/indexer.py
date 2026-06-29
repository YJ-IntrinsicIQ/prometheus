import json
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import chromadb
except ImportError:  # pragma: no cover - environment dependent
    chromadb = None

from .constants import CHROMA_PATH, COLLECTION_NAME
from .embedder import embed_texts


class _InMemoryCollection:
    def __init__(self):
        self.ids = []
        self.documents = []
        self.metadatas = []
        self.embeddings = []

    def add(self, embeddings, documents, metadatas, ids):
        self.ids.extend(ids)
        self.documents.extend(documents)
        self.metadatas.extend(metadatas)
        self.embeddings.extend(embeddings)

    def query(self, query_embeddings, n_results):
        if not self.documents:
            return {"documents": [[]], "metadatas": [[]], "ids": [[]], "distances": [[]]}
        scores = []
        for embedding, doc, meta, doc_id in zip(self.embeddings, self.documents, self.metadatas, self.ids):
            if not embedding or not query_embeddings:
                score = 0.0
            else:
                score = _cosine_similarity(embedding, query_embeddings[0])
            scores.append((score, doc, meta, doc_id))
        ranked = sorted(scores, key=lambda item: item[0], reverse=True)[:n_results]
        return {
            "documents": [[item[1] for item in ranked]],
            "metadatas": [[item[2] for item in ranked]],
            "ids": [[item[3] for item in ranked]],
            "distances": [[max(0.0, 1.0 - item[0]) for item in ranked]],
        }


class ChunkIndexer:
    def __init__(self, persist_directory: Optional[Path] = None):
        self.persist_directory = Path(persist_directory or CHROMA_PATH)
        if chromadb is None:
            self.client = None
            self.collection = _InMemoryCollection()
            return
        self.client = chromadb.PersistentClient(path=str(self.persist_directory))
        self.collection = self.client.get_or_create_collection(name=COLLECTION_NAME)

    def index_chunks(self, chunks: List[Dict[str, Any]]) -> List[str]:
        if not chunks:
            return []

        texts = [chunk["text"] for chunk in chunks]
        embeddings = embed_texts(texts)
        ids = []
        metadatas = []

        for idx, chunk in enumerate(chunks):
            chunk_id = f"chunk-{idx}"
            ids.append(chunk_id)
            metadata = dict(chunk.get("metadata") or {})
            metadata["text_length"] = len(chunk["text"])
            metadatas.append(metadata)

        self.collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )
        return ids

    def clear(self) -> None:
        if self.client is None:
            self.collection = _InMemoryCollection()
            return
        self.client.delete_collection(name=COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(name=COLLECTION_NAME)


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
