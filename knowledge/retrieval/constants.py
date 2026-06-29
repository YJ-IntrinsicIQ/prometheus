from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = "retrieval_chunks"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_TOP_K = 25
SEMANTIC_TOP_K = 40
BM25_TOP_K = 40
SEMANTIC_WEIGHT = 0.6
BM25_WEIGHT = 0.4
