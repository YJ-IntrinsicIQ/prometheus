"""
Deterministic LLM result cache for Prometheus pipelines.

Keyed by sha256(model + system_prompt + prompt + temperature + schema_version).
Results cached to .prometheus_cache/ (configurable via PROMETHEUS_CACHE_DIR).
A cache entry is only valid while all its inputs are unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _cache_dir() -> Path:
    return Path(os.getenv("PROMETHEUS_CACHE_DIR", ".prometheus_cache"))


def make_fingerprint(
    model: str,
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.0,
    schema_version: str = "1",
) -> str:
    """Return a deterministic cache key for these inputs."""
    payload = json.dumps(
        {"m": model, "s": system_prompt or "", "p": prompt, "t": temperature, "v": schema_version},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def cache_get(fingerprint: str) -> Optional[Dict[str, Any]]:
    """Return cached entry dict (containing 'result' key) or None on miss/error."""
    path = _cache_dir() / f"{fingerprint}.json"
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except Exception:
        return None


def cache_put(
    fingerprint: str,
    result: Any,
    metadata: Dict[str, Any],
) -> None:
    """Write result + metadata to the cache. Silently ignores write errors."""
    d = _cache_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        entry = {
            "fingerprint": fingerprint,
            "cached_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            **metadata,
            "result": result,
        }
        (d / f"{fingerprint}.json").write_text(
            json.dumps(entry, indent=2, ensure_ascii=False)
        )
    except Exception:
        pass  # ponytail: cache write failures are non-fatal; pipeline continues


def cache_invalidate(fingerprint: str) -> bool:
    """Delete a specific cache entry. Returns True if it existed."""
    path = _cache_dir() / f"{fingerprint}.json"
    if path.exists():
        path.unlink()
        return True
    return False
