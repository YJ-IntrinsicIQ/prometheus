import os
from pathlib import Path

_MODEL = None

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "hf_cache"
MODEL_NAME = "all-MiniLM-L6-v2"
MODEL_CACHE_DIR = CACHE_PATH / "hub" / "models--sentence-transformers--all-MiniLM-L6-v2"
MODEL_REF = MODEL_CACHE_DIR / "refs" / "main"

os.environ.setdefault("HF_HOME", str(CACHE_PATH))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(CACHE_PATH))

from sentence_transformers import SentenceTransformer
import chromadb

from core.document_registry import metadata_filter


CHROMA_PATH = ROOT / "chroma_db"


def load_embedding_model():

    global _MODEL

    if _MODEL is not None:
        return _MODEL

    model_path = MODEL_NAME
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

def search_chunks(
    query,
    company=None,
    year=None,
    document_type=None,
    n_results=5,
):

    model = load_embedding_model()

    client = chromadb.PersistentClient(
        path=CHROMA_PATH
    )

    collection = client.get_collection(
        "company_documents"
    )

    query_embedding = model.encode(
        query
    ).tolist()

    where = metadata_filter(
        company=company,
        year=year,
        document_type=document_type,
    )

    query_kwargs = {
        "query_embeddings": [
            query_embedding
        ],
        "n_results": n_results,
        "include": [
            "documents",
            "metadatas",
            "distances"
        ],
    }

    if where:
        query_kwargs["where"] = where

    results = collection.query(
        **query_kwargs
    )

    return results


if __name__ == "__main__":

    results = search_chunks(
        "capital expenditure"
    )

    print("\nRESULTS:\n")

    for doc in results["documents"][0]:

        print("=" * 80)

        print(doc[:1000])
