from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List


def event_deduplication_key(event: Dict[str, Any]) -> str:
    metadata = event.get("metadata") or {}
    metadata_key = ",".join(f"{key}={metadata[key]}" for key in sorted(metadata))
    return "|".join(
        [
            str(event.get("stream_type") or ""),
            str(event.get("subject_id") or ""),
            str(event.get("period") or ""),
            str(event.get("sequence") or 0),
            str(event.get("event_type") or ""),
            str(event.get("title") or ""),
            str(event.get("description") or ""),
            str(event.get("evidence_status") or ""),
            metadata_key,
        ]
    )


def deduplicate_events(events: Iterable[Dict[str, Any]], key_fn: Callable[[Dict[str, Any]], str] = event_deduplication_key) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for event in events:
        key = key_fn(event)
        if key not in seen:
            normalized = dict(event)
            normalized["source_references"] = list(event.get("source_references") or [])
            normalized["metadata"] = dict(event.get("metadata") or {})
            seen[key] = normalized
            order.append(key)
            continue
        existing = seen[key]
        for ref in event.get("source_references") or []:
            if ref not in existing.setdefault("source_references", []):
                existing["source_references"].append(ref)
        for meta_key, meta_value in (event.get("metadata") or {}).items():
            existing.setdefault("metadata", {})
            existing["metadata"].setdefault(meta_key, meta_value)

    for key in order:
        deduped.append(seen[key])
    return deduped
