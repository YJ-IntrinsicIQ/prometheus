from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict


def write_json_file(path: Path, payload: Dict[str, Any], *, force: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return path
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp") as handle:
        handle.write(serialized)
        temp_path = Path(handle.name)
    temp_path.replace(path)
    return path

