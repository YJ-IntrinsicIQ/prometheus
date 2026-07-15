from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def load_chunks(
    company: str,
    year: str,
    base_dir: Path = Path("companies"),
) -> List[Dict[str, Any]]:
    """
    Load cleaned document chunks for a single company.

    The retrieval engine should NEVER scan the entire repository.
    It should index only the chunks belonging to the requested
    company/year.
    """

    chunk_file = (
        base_dir
        / company
        / year
        / "extracted"
        / "clean_chunks.json"
    )

    if not chunk_file.exists():
        raise FileNotFoundError(
            f"Chunk file not found: {chunk_file}"
        )

    with chunk_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = data.get("chunks", [])

    chunks: List[Dict[str, Any]] = []

    for item in data:

        if not isinstance(item, dict):
            continue

        text = item.get("text") or item.get("chunk")

        if not text:
            continue

        chunks.append(
            {
                "chunk_id": item.get("chunk_id"),
                "text": text,
                "metadata": item.get("metadata", {}),
            }
        )

    return chunks