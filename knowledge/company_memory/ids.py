import hashlib
from datetime import datetime, timezone


def _stable_hash(*parts: str) -> str:
    payload = "|".join(part or "" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def make_entity_id(company_id: str, name: str) -> str:
    return f"ENT-{_stable_hash(company_id, name).upper()}"


def make_event_id(company_id: str, entity_id: str, event_type: str) -> str:
    return f"EVT-{_stable_hash(company_id, entity_id, event_type).upper()}"


def make_evidence_id(company_id: str, source: str, source_type: str) -> str:
    return f"EVD-{_stable_hash(company_id, source, source_type).upper()}"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
