import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "hf_cache"
MODEL_NAME = "all-MiniLM-L6-v2"
MODEL_CACHE_DIR = CACHE_PATH / "hub" / "models--sentence-transformers--all-MiniLM-L6-v2"
MODEL_REF = MODEL_CACHE_DIR / "refs" / "main"

os.environ.setdefault("HF_HOME", str(CACHE_PATH))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(CACHE_PATH))
sys.path.insert(0, str(ROOT))

import chromadb  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from core.context_paths import extraction_path  # noqa: E402
from core.document_registry import (  # noqa: E402
    DocumentRegistry,
    metadata_filter,
    normalize_company,
    normalize_document_type,
    normalize_year,
)
from pipelines.pipeline_context import get_context  # noqa: E402
from scripts.pdf_reader import extract_pages  # noqa: E402
from scripts.smart_chunker import chunk_pages  # noqa: E402
from utils.noise_filter import is_noise_chunk  # noqa: E402


PDF_PATH = ROOT / "data" / "annual_reports" / "polymatech_fy25.pdf"
CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = "company_documents"


def load_embedding_model():
    print("Loading model...")

    model_path = MODEL_NAME
    local_files_only = False

    if MODEL_REF.exists():
        revision = MODEL_REF.read_text().strip()
        snapshot_path = MODEL_CACHE_DIR / "snapshots" / revision

        if snapshot_path.exists():
            model_path = str(snapshot_path)
            local_files_only = True

    return SentenceTransformer(
        model_path,
        cache_folder=str(CACHE_PATH),
        local_files_only=local_files_only,
    )


def infer_company_year(pdf_path):
    filename = Path(pdf_path).stem.lower()
    parts = filename.split("_")

    company = parts[0] if parts else None
    year = parts[1] if len(parts) > 1 else None

    return company, year


def resolve_document_metadata(
    pdf_path,
    company=None,
    year=None,
    document_type="annual_report",
):
    context = get_context()
    inferred_company, inferred_year = infer_company_year(
        pdf_path
    )

    return {
        "company": normalize_company(
            company or getattr(context, "company", None) or inferred_company
        ) or "",
        "year": normalize_year(
            year or getattr(context, "year", None) or inferred_year
        ) or "",
        "document_type": normalize_document_type(
            document_type
        ) or "",
        "source_file": Path(pdf_path).name,
    }


def build_chunk_id(
    chunk_data,
    metadata,
    idx,
):
    if chunk_data.get("chunk_id"):
        return str(
            chunk_data["chunk_id"]
        )

    return "_".join(
        [
            metadata["company"] or "unknown_company",
            metadata["year"] or "unknown_year",
            metadata["document_type"] or "document",
            str(idx),
        ]
    )


def chunk_metadata(
    chunk_data,
    document_metadata,
    chunk_id,
):
    return {
        "company": document_metadata["company"],
        "year": document_metadata["year"],
        "document_type": document_metadata["document_type"],
        "page": chunk_data.get("page"),
        "chunk_id": chunk_id,
        "source_file": document_metadata["source_file"],
    }


def indexed_chunk_count(
    company=None,
    year=None,
    document_type="annual_report",
):
    client = chromadb.PersistentClient(
        path=CHROMA_PATH
    )

    try:
        collection = client.get_collection(
            name=COLLECTION_NAME
        )
    except Exception:
        return 0

    where = metadata_filter(
        company=company,
        year=year,
        document_type=document_type,
    )

    payload = collection.get(
        where=where,
        include=["metadatas"],
    )

    return len(
        payload.get("ids", [])
    )


def ensure_company_year_index(
    pdf_path,
    company=None,
    year=None,
    document_type="annual_report",
):
    existing = indexed_chunk_count(
        company=company,
        year=year,
        document_type=document_type,
    )

    if existing > 0:
        print(
            f"Index already present for {company} {year} "
            f"({existing} chunks)"
        )
        return existing

    print(
        f"Index missing for {company} {year}; "
        f"building active company/year slice"
    )

    build_index(
        pdf_path=pdf_path,
        company=company,
        year=year,
        document_type=document_type,
    )

    return indexed_chunk_count(
        company=company,
        year=year,
        document_type=document_type,
    )


def build_index(
    pdf_path=PDF_PATH,
    company=None,
    year=None,
    document_type="annual_report",
):
    pdf_path = Path(pdf_path)

    model = load_embedding_model()

    document_metadata = resolve_document_metadata(
        pdf_path=pdf_path,
        company=company,
        year=year,
        document_type=document_type,
    )

    print("Loading PDF...")

    pages = extract_pages(pdf_path)
    chunks = chunk_pages(
        pages,
        company=document_metadata["company"],
        year=document_metadata["year"],
        document_type=document_metadata["document_type"],
        output_path=extraction_path("clean_chunks.json"),
    )

    print(
        f"Chunks before filtering: {len(chunks)}"
    )

    filtered_chunks = []

    for chunk in chunks:
        if is_noise_chunk(
            chunk["text"]
        ):
            continue

        filtered_chunks.append(
            chunk
        )

    print(
        f"Chunks after filtering: {len(filtered_chunks)}"
    )

    client = chromadb.PersistentClient(
        path=CHROMA_PATH
    )

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME
    )

    for idx, chunk_data in enumerate(filtered_chunks):
        chunk_text = chunk_data["text"]
        chunk_id = build_chunk_id(
            chunk_data,
            document_metadata,
            idx,
        )

        embedding = model.encode(
            chunk_text
        ).tolist()

        collection.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[chunk_text],
            metadatas=[
                chunk_metadata(
                    chunk_data,
                    document_metadata,
                    chunk_id,
                )
            ],
        )

    DocumentRegistry(
        company=document_metadata["company"],
        year=document_metadata["year"],
    ).register(
        document_type=document_metadata["document_type"],
        filename=document_metadata["source_file"],
    )

    print("\nIndex Complete")


def build_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--pdf",
        default=str(PDF_PATH),
    )

    parser.add_argument(
        "--company",
    )

    parser.add_argument(
        "--year",
    )

    parser.add_argument(
        "--document-type",
        default="annual_report",
    )

    return parser


def main():
    args = build_parser().parse_args()

    build_index(
        pdf_path=args.pdf,
        company=args.company,
        year=args.year,
        document_type=args.document_type,
    )


if __name__ == "__main__":
    main()
