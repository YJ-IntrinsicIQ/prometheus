import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from .constants import ROOT


def iter_chunk_files(base_dir: Optional[Path] = None) -> List[Path]:
    base = base_dir or ROOT / "outputs"
    files = []
    for path in sorted(base.glob("*.json")):
        if path.name.endswith("_results.json") or path.name.startswith("clean_") or path.name.startswith("extracted_"):
            files.append(path)
    return files


def load_chunks_from_outputs(base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    chunks = []
    for path in iter_chunk_files(base_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if isinstance(data, dict):
            items = data.get("results") if isinstance(data.get("results"), list) else data.get("items")
            if isinstance(items, list):
                data = items
            else:
                data = [data]

        if not isinstance(data, list):
            continue

        for item in data:
            if not isinstance(item, dict):
                continue
            text = item.get("chunk") or item.get("text") or item.get("source_chunk") or ""
            if not isinstance(text, str) or not text.strip():
                continue
            metadata = dict(item.get("metadata") or {})
            metadata.setdefault("source_file", path.name)
            metadata.setdefault("company", metadata.get("company") or path.stem.replace("_results", "").replace("clean_", "").replace("extracted_", ""))
            chunks.append({"text": text.strip(), "metadata": metadata})
    return chunks
