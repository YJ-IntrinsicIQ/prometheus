import json
import re
from pathlib import Path


TARGET_CHUNK_SIZE = 1200
OVERLAP_PARAGRAPHS = 1


def is_mostly_numeric(text: str) -> bool:

    tokens = text.split()

    if not tokens:
        return False

    numeric_tokens = 0

    for token in tokens:

        cleaned = token.replace(",", "").replace(".", "")

        if cleaned.isdigit():
            numeric_tokens += 1

    return (
        numeric_tokens / len(tokens)
    ) > 0.6


def clean_paragraphs(text: str):

    raw_paragraphs = re.split(
        r"\n\s*\n",
        text
    )

    paragraphs = []

    for para in raw_paragraphs:

        para = re.sub(
            r"\s+",
            " ",
            para
        ).strip()

        if len(para) < 150:
            continue

        if is_mostly_numeric(para):
            continue

        paragraphs.append(
            para
        )

    return paragraphs


def chunk_text(
    text: str,
    target_chunk_size: int = TARGET_CHUNK_SIZE
):

    paragraphs = clean_paragraphs(
        text
    )

    chunks = []

    current_chunk = []
    current_size = 0

    for para in paragraphs:

        para_size = len(para)

        if (
            current_size + para_size
            <= target_chunk_size
        ):

            current_chunk.append(
                para
            )

            current_size += para_size

        else:

            chunk_text_value = "\n\n".join(
                current_chunk
            )

            if chunk_text_value.strip():
                chunks.append(
                    chunk_text_value
                )

            overlap = (
                current_chunk[
                    -OVERLAP_PARAGRAPHS:
                ]
                if current_chunk
                else []
            )

            current_chunk = (
                overlap + [para]
            )

            current_size = sum(
                len(x)
                for x in current_chunk
            )

    if current_chunk:

        final_chunk = "\n\n".join(
            current_chunk
        )
        if final_chunk.strip():
            chunks.append(
                final_chunk
            )

    return chunks

def _build_chunk_id(index: int) -> str:
    return f"CHK-{index + 1:06d}"


def persist_clean_chunks(
    chunks,
    *,
    company: str = "",
    year: str = "",
    document_type: str = "annual_report",
    output_path=None,
):
    output_path = Path(output_path) if output_path is not None else None

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "company": company or "",
        "year": year or "",
        "document_type": document_type or "annual_report",
        "chunk_count": len(chunks),
        "chunks": [
            {
                "chunk_id": chunk.get("chunk_id") or _build_chunk_id(index),
                "page": chunk.get("page"),
                "text": chunk.get("text", ""),
                "metadata": {
                    "page": chunk.get("page"),
                    "company": company or "",
                    "year": year or "",
                    "document_type": document_type or "annual_report",
                },
            }
            for index, chunk in enumerate(chunks)
        ],
    }

    seen_chunk_ids = set()
    for index, chunk in enumerate(payload["chunks"]):
        chunk_id = chunk.get("chunk_id") or _build_chunk_id(index)
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("chunk_id is required")
        if chunk_id in seen_chunk_ids:
            raise ValueError(f"duplicate chunk_id: {chunk_id}")
        seen_chunk_ids.add(chunk_id)

        if not isinstance(chunk.get("text"), str) or not chunk.get("text", "").strip():
            raise ValueError(f"chunk {chunk_id} must contain text")
        if chunk.get("page") is None:
            raise ValueError(f"chunk {chunk_id} must contain page")
        metadata = chunk.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError(f"chunk {chunk_id} must include metadata")
        for field in ("page", "company", "year", "document_type"):
            if field not in metadata:
                raise ValueError(f"chunk {chunk_id} missing metadata field {field}")

    if output_path is not None:
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return payload


def chunk_pages(
    pages,
    *,
    company: str = "",
    year: str = "",
    document_type: str = "annual_report",
    output_path=None,
):

    all_chunks = []

    for page_data in pages:

        page_number = page_data["page"]

        page_chunks = chunk_text(
            page_data["text"]
        )

        for chunk in page_chunks:
            all_chunks.append(
                {
                    "page": page_number,
                    "text": chunk,
                }
            )

    if output_path is not None or any([company, year, document_type]):
        persist_clean_chunks(
            all_chunks,
            company=company,
            year=year,
            document_type=document_type,
            output_path=output_path,
        )

    return all_chunks