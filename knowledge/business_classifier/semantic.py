from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, Optional, Tuple

from knowledge.retrieval.constants import EMBEDDING_MODEL_NAME
from knowledge.retrieval.embedder import SentenceTransformer, load_embedding_model


SEMANTIC_SIMILARITY_ENV = "BUSINESS_CLASSIFIER_ENABLE_SEMANTIC"


@dataclass(frozen=True)
class SemanticSimilarityResult:
    active: bool
    backend: str
    model_name: Optional[str]
    disabled_reason: Optional[str]
    scores: Dict[str, float]


def compute_similarity_scores(
    source_text: str,
    candidates: Dict[str, str],
) -> SemanticSimilarityResult:
    if not _semantic_similarity_enabled():
        return SemanticSimilarityResult(
            active=False,
            backend="disabled",
            model_name=None,
            disabled_reason=f"{SEMANTIC_SIMILARITY_ENV}=0",
            scores={candidate_id: 0.0 for candidate_id in candidates},
        )

    if not source_text.strip() or not candidates:
        return SemanticSimilarityResult(
            active=False,
            backend="disabled",
            model_name=None,
            disabled_reason="missing_source_or_candidates",
            scores={candidate_id: 0.0 for candidate_id in candidates},
        )

    if SentenceTransformer is None:
        return SemanticSimilarityResult(
            active=False,
            backend="unavailable",
            model_name=None,
            disabled_reason="sentence_transformers_not_installed",
            scores={candidate_id: 0.0 for candidate_id in candidates},
        )

    try:
        model = load_embedding_model()
        candidate_ids = tuple(candidates.keys())
        candidate_texts = tuple(candidates[candidate_id] for candidate_id in candidate_ids)
        source_embedding = _embed_one(source_text, model)
        candidate_embeddings = _embed_many(candidate_texts)
    except Exception as exc:  # pragma: no cover - environment dependent
        return SemanticSimilarityResult(
            active=False,
            backend="unavailable",
            model_name=EMBEDDING_MODEL_NAME,
            disabled_reason=str(exc),
            scores={candidate_id: 0.0 for candidate_id in candidates},
        )

    scores = {
        candidate_id: round(_dot(source_embedding, embedding), 4)
        for candidate_id, embedding in zip(candidate_ids, candidate_embeddings)
    }
    return SemanticSimilarityResult(
        active=True,
        backend="sentence_transformers",
        model_name=EMBEDDING_MODEL_NAME,
        disabled_reason=None,
        scores=scores,
    )


def _semantic_similarity_enabled() -> bool:
    value = os.getenv(SEMANTIC_SIMILARITY_ENV, "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _embed_one(text: str, model) -> Tuple[float, ...]:
    embeddings = model.encode(
        [text],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return tuple(float(value) for value in embeddings[0])


@lru_cache(maxsize=32)
def _embed_many(texts: Tuple[str, ...]) -> Tuple[Tuple[float, ...], ...]:
    model = load_embedding_model()
    embeddings = model.encode(
        list(texts),
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return tuple(
        tuple(float(value) for value in embedding)
        for embedding in embeddings
    )


def _dot(left: Iterable[float], right: Iterable[float]) -> float:
    return sum(left_value * right_value for left_value, right_value in zip(left, right))
