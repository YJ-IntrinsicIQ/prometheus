#!/usr/bin/env python3
"""
Manual verification tool for the Retrieval foundation.

Starts after companies/tips/2024/extracted/clean_chunks.json has been created.
Uses real loader, embedding, Chroma indexing, semantic search, BM25, and hybrid
merge logic. This script is diagnostic only and does not modify production code.
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence
import traceback

ROOT = Path(__file__).resolve().parents[2]

import os

CACHE_DIR = ROOT / "hf_cache"

os.environ.setdefault("HF_HOME", str(CACHE_DIR))
os.environ.setdefault("TRANSFORMERS_CACHE", str(CACHE_DIR))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(CACHE_DIR))

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RETRIEVAL_IMPORT_ERROR = None
try:
    from knowledge.retrieval.bm25 import BM25
    from knowledge.retrieval.constants import (  # noqa: E402
        BM25_TOP_K,
        DEFAULT_TOP_K,
        EMBEDDING_MODEL_NAME,
        SEMANTIC_TOP_K,
    )
    from knowledge.retrieval.embedder import SentenceTransformer, embed_texts  # noqa: E402
    from knowledge.retrieval.hybrid import merge_results  # noqa: E402
    from knowledge.retrieval.indexer import ChunkIndexer  # noqa: E402
    from knowledge.retrieval.loader import load_chunks  # noqa: E402
    from knowledge.retrieval.retriever import HybridRetriever  # noqa: E402
except Exception as exc:  # pragma: no cover - diagnostic setup failure
    RETRIEVAL_IMPORT_ERROR = exc
    BM25 = None
    BM25_TOP_K = 40
    DEFAULT_TOP_K = 25
    EMBEDDING_MODEL_NAME = "unknown"
    SEMANTIC_TOP_K = 40
    SentenceTransformer = None
    embed_texts = None
    merge_results = None
    ChunkIndexer = None
    load_chunks = None
    HybridRetriever = None


COMPANY = "tips"
YEAR = "2024"

DNA_QUERY_REGISTRY = {
    "Manufacturing": [
        "technology",
        "capital allocation",
        "capacity expansion",
        "plant",
        "production",
        "capex",
    ],
    "Media": [
        "music",
        "catalogue",
        "royalty",
        "licensing",
        "content",
        "digital",
    ],
    "Financial": [
        "loan",
        "deposit",
        "interest",
        "asset quality",
        "capital adequacy",
        "branch",
    ],
    "Technology": [
        "software",
        "platform",
        "AI",
        "cloud",
        "subscription",
        "customers",
    ],
}

GENERIC_INVESTOR_QUERIES = [
    "management",
    "strategy",
    "growth",
    "risk",
    "capital allocation",
    "technology",
]


def main() -> int:
    print_header("Retrieval Foundation Verification")
    print(f"Company: {COMPANY}")
    print(f"Year: {YEAR}")
    print(f"Workspace: {ROOT}")

    queries = get_test_queries(COMPANY, YEAR)
    chunks = step_1_load_chunks()
    embeddings = step_2_generate_embeddings(chunks)
    persist_dir, retriever = step_3_build_vector_index(chunks)

    try:
        semantic_by_query = step_4_semantic_search(retriever, queries)
        bm25_by_query = step_5_bm25_search(chunks, queries)
        hybrid_by_query = step_6_hybrid_retrieval(semantic_by_query, bm25_by_query)
        validate(chunks, embeddings, semantic_by_query, bm25_by_query, hybrid_by_query)
    finally:
        shutil.rmtree(persist_dir, ignore_errors=True)

    print("\nFINAL: PASS - Retrieval foundation verified")
    return 0


def get_test_queries(company: str, year: str) -> list[str]:
    classification_path = (
        ROOT
        / "companies"
        / company
        / year
        / "intelligence"
        / "business_classification.json"
    )

    try:
        with classification_path.open("r", encoding="utf-8") as f:
            classification = json.load(f)
    except Exception as exc:
        fail("Business DNA query selection", exc)

    business_dnas = classification.get("business_dnas") or []
    if isinstance(business_dnas, str):
        business_dnas = [business_dnas]

    queries = []
    for dna in business_dnas:
        for query in DNA_QUERY_REGISTRY.get(str(dna), []):
            if query not in queries:
                queries.append(query)

    if not queries:
        queries = list(GENERIC_INVESTOR_QUERIES)

    print("\nBusiness DNA:")
    if business_dnas:
        for dna in business_dnas:
            print(str(dna))
    else:
        print("Unknown")

    print("\nQueries:")
    for query in queries:
        print(query)

    return queries


def step_1_load_chunks() -> List[Dict[str, Any]]:
    print_header("STEP 1 - Load clean_chunks.json")
    if RETRIEVAL_IMPORT_ERROR is not None:
        fail("STEP 1 - existing retrieval Loader import", RETRIEVAL_IMPORT_ERROR)

    try:
        chunks = load_chunks(COMPANY, YEAR, base_dir=ROOT / "companies")
    except Exception as exc:
        fail("STEP 1 - chunks loaded", exc)

    lengths = [len(chunk["text"]) for chunk in chunks]
    average_length = sum(lengths) / len(lengths) if lengths else 0.0

    print(f"Chunk count: {len(chunks)}")
    print(f"Average chunk length: {average_length:.2f}")

    if not chunks:
        fail("STEP 1 - chunks loaded", "chunk count is 0")

    print("PASS: Chunks loaded")
    return chunks


def step_2_generate_embeddings(chunks: Sequence[Dict[str, Any]]) -> List[List[float]]:
    print_header("STEP 2 - Generate embeddings")
    texts = [chunk["text"] for chunk in chunks]

    try:
        embeddings = embed_texts(texts)
    except Exception as exc:
        fail("STEP 2 - embeddings generated", exc)

    is_valid, reason = validate_chroma_embedding_format(embeddings, expected_count=len(texts))
    dimension = len(embeddings[0]) if embeddings and isinstance(embeddings[0], Sequence) else 0
    embedding_type = type(embeddings[0]).__name__ if embeddings else "none"
    model_label = EMBEDDING_MODEL_NAME
    if SentenceTransformer is None:
        model_label = f"{EMBEDDING_MODEL_NAME} unavailable; using retrieval fallback token vectors"

    print(f"Embedding model: {model_label}")
    print(f"Embedding dimension: {dimension}")
    print(f"Embedding type: {embedding_type}")
    print(f"Embedding count: {len(embeddings)}")

    if not is_valid:
        fail("STEP 2 - Chroma-compatible embedding format", reason)

    print("PASS: Embeddings generated and Chroma-compatible")
    return embeddings


def step_3_build_vector_index(chunks: Sequence[Dict[str, Any]]) -> tuple[Path, HybridRetriever]:
    print_header("STEP 3 - Build vector index")
    persist_dir = Path(tempfile.mkdtemp(prefix="retrieval-foundation-chroma-"))

    try:
        indexer = ChunkIndexer(persist_directory=persist_dir)
        if indexer.client is None:
            shutil.rmtree(persist_dir, ignore_errors=True)
            fail("STEP 3 - Chroma index built", "chromadb is not installed or could not be imported")

        retriever = HybridRetriever(persist_directory=str(persist_dir))
        start = time.perf_counter()
        ids = retriever.build_index(list(chunks))
        elapsed = time.perf_counter() - start
    except SystemExit:
        raise
    except Exception as exc:
        shutil.rmtree(persist_dir, ignore_errors=True)
        fail("STEP 3 - Chroma index built", exc)

    print(f"Chunks indexed: {len(ids)}")
    print(f"Time taken: {elapsed:.2f}s")

    if len(ids) != len(chunks):
        shutil.rmtree(persist_dir, ignore_errors=True)
        fail("STEP 3 - Chroma index built", f"indexed {len(ids)} of {len(chunks)} chunks")

    print("PASS: Chroma index built")
    return persist_dir, retriever


def step_4_semantic_search(
    retriever: HybridRetriever,
    queries: Sequence[str],
) -> Dict[str, List[Dict[str, Any]]]:
    print_header("STEP 4 - Semantic search")
    results_by_query = {}

    for query in queries:
        try:
            results = retriever._semantic_search(query, top_k=SEMANTIC_TOP_K)
        except Exception as exc:
            fail("STEP 4 - semantic search returns results", exc)

        results_by_query[query] = results
        print_query_diagnostics(query, results)

    if not all(results_by_query[query] for query in queries):
        empty = [query for query, results in results_by_query.items() if not results]
        fail("STEP 4 - semantic search returns results", f"no results for: {', '.join(empty)}")

    print("PASS: Semantic search returns results")
    return results_by_query


def step_5_bm25_search(
    chunks: Sequence[Dict[str, Any]],
    queries: Sequence[str],
) -> Dict[str, List[Dict[str, Any]]]:
    print_header("STEP 5 - BM25 search")
    documents = [chunk["text"] for chunk in chunks]
    bm25 = BM25(documents)
    results_by_query = {}

    for query in queries:
        ranked = sorted(bm25.scores(query), key=lambda item: item[1], reverse=True)[:BM25_TOP_K]
        results = [
            {
                "chunk_id": f"bm25-{idx}",
                "text": documents[idx],
                "metadata": chunks[idx].get("metadata", {}),
                "score": score,
            }
            for idx, score in ranked
            if score > 0.0
        ]
        results_by_query[query] = results
        print_query_diagnostics(query, results)

    if not all(results_by_query[query] for query in queries):
        empty = [query for query, results in results_by_query.items() if not results]
        fail("STEP 5 - BM25 returns results", f"no results for: {', '.join(empty)}")

    print("PASS: BM25 returns results")
    return results_by_query


def step_6_hybrid_retrieval(
    semantic_by_query: Dict[str, List[Dict[str, Any]]],
    bm25_by_query: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    print_header("STEP 6 - Hybrid retrieval")
    results_by_query = {}

    for query in semantic_by_query:
        semantic_results = semantic_by_query[query]
        bm25_results = bm25_by_query[query]
        merged_all = merge_results(
            semantic_results,
            bm25_results,
            top_k=len(semantic_results) + len(bm25_results),
        )
        final_results = merge_results(semantic_results, bm25_results, top_k=DEFAULT_TOP_K)
        duplicates_removed = len(semantic_results) + len(bm25_results) - len(merged_all)

        results_by_query[query] = final_results

        print(f"\nQuery: {query}")
        print(f"Semantic results: {len(semantic_results)}")
        print(f"BM25 results: {len(bm25_results)}")
        print(f"Merged results: {len(merged_all)}")
        print(f"Duplicate chunks removed: {duplicates_removed}")
        print(f"Final retrieved chunks: {len(final_results)}")
        print_top_chunks(final_results)

    if not all(results_by_query[query] for query in semantic_by_query):
        empty = [query for query, results in results_by_query.items() if not results]
        fail("STEP 6 - hybrid retrieval returns results", f"no results for: {', '.join(empty)}")

    print("PASS: Hybrid retrieval returns results")
    return results_by_query


def validate(
    chunks: Sequence[Dict[str, Any]],
    embeddings: Sequence[Sequence[float]],
    semantic_by_query: Dict[str, List[Dict[str, Any]]],
    bm25_by_query: Dict[str, List[Dict[str, Any]]],
    hybrid_by_query: Dict[str, List[Dict[str, Any]]],
) -> None:
    print_header("Validation")
    checks = [
        ("Chunks loaded", bool(chunks)),
        ("Embeddings generated", bool(embeddings)),
        ("Chroma index built", True),
        ("Semantic search returns results", all(semantic_by_query.values())),
        ("BM25 returns results", all(bm25_by_query.values())),
        ("Hybrid retrieval returns results", all(hybrid_by_query.values())),
    ]

    for label, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'}: {label}")
        if not passed:
            fail(label, "validation check failed")


def validate_chroma_embedding_format(
    embeddings: Any,
    expected_count: int,
) -> tuple[bool, str]:
    if not isinstance(embeddings, list):
        return False, f"embeddings must be list[list[float]], got {type(embeddings).__name__}"
    if len(embeddings) != expected_count:
        return False, f"embedding count {len(embeddings)} does not match chunk count {expected_count}"
    if not embeddings:
        return False, "embedding list is empty"

    dimension = None
    for idx, embedding in enumerate(embeddings):
        if not isinstance(embedding, list):
            return False, f"embedding {idx} must be a list, got {type(embedding).__name__}"
        if not embedding:
            return False, f"embedding {idx} is empty"
        if dimension is None:
            dimension = len(embedding)
        elif len(embedding) != dimension:
            return False, f"embedding {idx} dimension {len(embedding)} != expected {dimension}"

        for value_idx, value in enumerate(embedding):
            if not isinstance(value, (float, int)):
                return False, (
                    f"embedding {idx} value {value_idx} must be numeric, "
                    f"got {type(value).__name__}"
                )
            if not math.isfinite(float(value)):
                return False, f"embedding {idx} value {value_idx} is not finite"

    return True, "ok"


def print_query_diagnostics(query: str, results: Sequence[Dict[str, Any]]) -> None:
    print(f"\nQuery: {query}")
    print(f"Retrieved chunk count: {len(results)}")
    print_top_chunks(results)


def print_top_chunks(results: Sequence[Dict[str, Any]]) -> None:
    print("Top 5 chunks:")
    for rank, item in enumerate(results[:5], start=1):
        metadata = item.get("metadata") or {}
        page = extract_page_number(metadata)
        score = item.get("score", 0.0)
        preview = normalize_preview(item.get("text", ""))
        print(f"  {rank}. Chunk ID: {item.get('chunk_id')}")
        print(f"     Page number: {page}")
        print(f"     Similarity score: {score:.6f}")
        print(f"     First 200 characters: {preview}")


def extract_page_number(metadata: Dict[str, Any]) -> Any:
    for key in ("page", "page_number", "source_page"):
        if key in metadata:
            return metadata[key]
    return "unknown"


def normalize_preview(text: str, limit: int = 200) -> str:
    return " ".join(text.split())[:limit]


def print_header(title: str) -> None:
    print(f"\n{'=' * 80}")
    print(title)
    print(f"{'=' * 80}")


def fail(stage: str, detail: Any) -> None:
    print(f"FAIL: {stage}")
    print(f"Failing stage: {stage}")
    print(f"Reason: {detail}")
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
