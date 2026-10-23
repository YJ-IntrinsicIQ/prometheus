from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.context_paths import guarded_write_text


def write_json_file(path: Path, payload: Dict[str, Any], *, root: Path | str, force: bool = False) -> Path:
    """Serialize and write atomically; the destination must lie inside the explicit, already-authorized output root."""
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return guarded_write_text(root, path, encoded, force=force)
