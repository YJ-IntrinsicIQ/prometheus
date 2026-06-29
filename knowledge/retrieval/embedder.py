import os
import re
from collections import Counter
from pathlib import Path
from typing import List

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - environment dependent
    SentenceTransformer = None

from .constants import EMBEDDING_MODEL_NAME, ROOT

os.environ.setdefault("HF_HOME", str(ROOT / "hf_cache"))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(ROOT / "hf_cache"))

_MODEL = None


def load_embedding_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if SentenceTransformer is None:
        raise ImportError("sentence-transformers is required for embeddings; install it from requirements.txt")

    _MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME, cache_folder=str(ROOT / "hf_cache"))
    return _MODEL


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    if SentenceTransformer is None:
        vocab = sorted({token for text in texts for token in _tokenize(text)})
        return [[float(count) for count in _vectorize(text, vocab)] for text in texts]

    model = load_embedding_model()
    return model.encode(texts, convert_to_numpy=False).tolist()


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _vectorize(text: str, vocab: List[str]) -> List[float]:
    counts = Counter(_tokenize(text))
    return [float(counts.get(token, 0)) for token in vocab]
