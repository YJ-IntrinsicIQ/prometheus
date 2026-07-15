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

CACHE_PATH = ROOT / "hf_cache"
MODEL_CACHE_DIR = CACHE_PATH / "hub" / "models--sentence-transformers--all-MiniLM-L6-v2"
MODEL_REF = MODEL_CACHE_DIR / "refs" / "main"

os.environ.setdefault("HF_HOME", str(CACHE_PATH))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(CACHE_PATH))

_MODEL = None


def load_embedding_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if SentenceTransformer is None:
        raise ImportError("sentence-transformers is required for embeddings; install it from requirements.txt")

    model_path = EMBEDDING_MODEL_NAME
    local_files_only = False

    if MODEL_REF.exists():
        revision = MODEL_REF.read_text().strip()
        snapshot_path = MODEL_CACHE_DIR / "snapshots" / revision

        if snapshot_path.exists():
            model_path = str(snapshot_path)
            local_files_only = True

    _MODEL = SentenceTransformer(
        model_path,
        cache_folder=str(CACHE_PATH),
        local_files_only=local_files_only,
    )
    return _MODEL


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    if SentenceTransformer is None:
        vocab = sorted({token for text in texts for token in _tokenize(text)})
        return [[float(count) for count in _vectorize(text, vocab)] for text in texts]

    model = load_embedding_model()
    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings.tolist()


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _vectorize(text: str, vocab: List[str]) -> List[float]:
    counts = Counter(_tokenize(text))
    return [float(counts.get(token, 0)) for token in vocab]
