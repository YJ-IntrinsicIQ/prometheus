from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_STAGE_TOKEN_BUDGETS: Dict[str, int] = {
    "extraction": 6000,
    "business_understanding": 5000,
    "business_classification": 4500,
    "business_intelligence": 5000,
    "investor_panel_analyst": 7000,
    "committee_synthesis": 6000,
}

DEFAULT_STAGE_POLICIES: Dict[str, Dict[str, Any]] = {
    "extraction": {
        "allowed_sections": ["chunks"],
        "excluded_sections": ["debug_metadata", "validation_metadata"],
        "max_items": 8,
        "max_chars": 24000,
        "include_evidence_ids": False,
        "collect_evidence_ids": False,
        "include_short_excerpts": False,
        "include_source_chunks": True,
    },
    "business_understanding": {
        "allowed_sections": ["company_memory", "classification_context"],
        "excluded_sections": ["raw_text_fields", "debug_metadata", "validation_metadata"],
        "max_items": 40,
        "max_chars": 20000,
        "include_evidence_ids": True,
        "collect_evidence_ids": True,
        "include_short_excerpts": False,
        "include_source_chunks": False,
    },
    "business_intelligence": {
        "allowed_sections": ["module", "questions", "chunks"],
        "excluded_sections": ["debug_metadata", "validation_metadata"],
        "max_items": 18,
        "max_chars": 20000,
        "include_evidence_ids": True,
        "collect_evidence_ids": True,
        "include_short_excerpts": False,
        "include_source_chunks": True,
    },
    "investor_panel_analyst": {
        "allowed_sections": ["selected_pcim"],
        "excluded_sections": ["raw_text_fields", "debug_metadata", "validation_metadata"],
        "max_items": 25,
        "max_chars": 28000,
        "include_evidence_ids": True,
        "collect_evidence_ids": True,
        "include_short_excerpts": True,
        "include_source_chunks": False,
    },
    "committee_synthesis": {
        "allowed_sections": ["analysts", "missing_analysts", "excluded_analysts", "evidence_quality_notes"],
        "excluded_sections": ["raw_text_fields", "debug_metadata", "validation_metadata"],
        "max_items": 20,
        "max_chars": 24000,
        "include_evidence_ids": True,
        "collect_evidence_ids": True,
        "include_short_excerpts": False,
        "include_source_chunks": False,
    },
}

_DEBUG_FIELDS = {
    "debug",
    "debug_log",
    "debug_logs",
    "run_summary",
    "stack_trace",
    "token_usage",
    "token_usage_logs",
}

_VALIDATION_NOISE_FIELDS = {
    "validation_report",
    "validation_reports",
    "validation_status",
    "evidence_grounding_warnings",
    "source_manifest",
    "source_hashes",
    "content_hash",
    "modified_at",
}

_SOURCE_CHUNK_FIELDS = {
    "source_chunk",
    "raw_text",
    "full_page_text",
}

_DROP_EMPTY_KEYS = {
    "evidence_grounding_warnings",
    "reasoning_limits",
}


def estimate_tokens(text: str) -> int:
    return max(1, (len(text or "") + 3) // 4)


def cap_items(items: Sequence[Any], max_items: int) -> List[Any]:
    return list(items[: max(0, max_items)])


def strip_debug_fields(obj: Any) -> Any:
    return _strip_keys(obj, _DEBUG_FIELDS)


def strip_source_chunks(obj: Any) -> Any:
    return _strip_keys(obj, _SOURCE_CHUNK_FIELDS)


def strip_validation_noise(obj: Any) -> Any:
    return _strip_keys(obj, _VALIDATION_NOISE_FIELDS)


def select_relevant_sections(obj: Any, allowed_sections: Optional[Sequence[str]]) -> Any:
    if not allowed_sections or not isinstance(obj, dict):
        return obj
    return {key: deepcopy(value) for key, value in obj.items() if key in set(allowed_sections)}


def compact_evidence_refs(obj: Any, *, max_excerpt_chars: int = 300) -> Any:
    if isinstance(obj, dict):
        compacted: Dict[str, Any] = {}
        for key, value in obj.items():
            if key == "evidence_references" and isinstance(value, list):
                compacted[key] = [
                    _compact_single_evidence_reference(item, max_excerpt_chars=max_excerpt_chars)
                    for item in value
                ]
                continue
            compacted[key] = compact_evidence_refs(value, max_excerpt_chars=max_excerpt_chars)
        return compacted
    if isinstance(obj, list):
        return [compact_evidence_refs(item, max_excerpt_chars=max_excerpt_chars) for item in obj]
    return obj


def build_llm_input_pack(
    *,
    stage: str,
    purpose: str,
    company: str,
    year: Optional[str],
    selected_input: Any = None,
    facts: Optional[Sequence[Any]] = None,
    observations: Optional[Sequence[Any]] = None,
    evidence_ids: Optional[Sequence[str]] = None,
    limitations: Optional[Sequence[str]] = None,
    source_artifacts: Optional[Sequence[str]] = None,
    pack_name: Optional[str] = None,
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    resolved_policy = _resolve_policy(stage, policy)
    clean_selected = _sanitize_for_policy(selected_input, resolved_policy)

    clean_facts = _sanitize_for_policy(list(facts or []), resolved_policy)
    clean_observations = _sanitize_for_policy(list(observations or []), resolved_policy)
    if not clean_observations and clean_selected not in (None, {}, []):
        clean_observations = [clean_selected]

    clean_limitations = _normalize_string_list(limitations)
    clean_evidence_ids = _normalize_string_list(evidence_ids)
    if resolved_policy.get("collect_evidence_ids", True):
        for nested_id in _collect_evidence_ids(clean_observations):
            if nested_id not in clean_evidence_ids:
                clean_evidence_ids.append(nested_id)
        for nested_id in _collect_evidence_ids(clean_facts):
            if nested_id not in clean_evidence_ids:
                clean_evidence_ids.append(nested_id)

    facts_truncated = False
    observations_truncated = False
    max_items = int(resolved_policy["max_items"])
    if len(clean_facts) > max_items:
        clean_facts = cap_items(clean_facts, max_items)
        facts_truncated = True
    if len(clean_observations) > max_items:
        clean_observations = cap_items(clean_observations, max_items)
        observations_truncated = True

    pack = {
        "pack_name": pack_name or f"{stage}_input_pack",
        "stage": stage,
        "company": company,
        "year": year,
        "purpose": purpose,
        "input_policy": deepcopy(resolved_policy),
        "facts": clean_facts,
        "observations": clean_observations,
        "evidence_ids": clean_evidence_ids,
        "limitations": clean_limitations,
        "metadata": {
            "source_artifacts": list(source_artifacts or []),
            "source_hashes": [],
            "tokens_estimated": 0,
            "chars": 0,
            "truncation_applied": facts_truncated or observations_truncated,
            "warnings": [],
        },
    }

    pack = _enforce_pack_budget(pack)
    return pack


def validate_llm_input_pack(
    pack: Dict[str, Any],
    *,
    require_source_artifacts: bool = False,
) -> Dict[str, Any]:
    if not isinstance(pack, dict):
        raise ValueError("LLM input pack must be a dictionary")

    required_keys = {
        "pack_name",
        "stage",
        "company",
        "purpose",
        "input_policy",
        "facts",
        "observations",
        "evidence_ids",
        "limitations",
        "metadata",
    }
    missing = [key for key in required_keys if key not in pack]
    if missing:
        raise ValueError(f"LLM input pack missing required keys: {missing}")

    metadata = pack.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("LLM input pack metadata must be a dictionary")

    source_artifacts = metadata.get("source_artifacts") or []
    if require_source_artifacts and not source_artifacts:
        raise ValueError("LLM input pack requires at least one source artifact")

    payload_text = json.dumps(pack, ensure_ascii=False)
    policy = pack.get("input_policy") or {}
    scan_payload = {
        "facts": pack.get("facts"),
        "observations": pack.get("observations"),
        "evidence_ids": pack.get("evidence_ids"),
        "limitations": pack.get("limitations"),
        "source_artifacts": metadata.get("source_artifacts"),
    }
    scan_text = json.dumps(scan_payload, ensure_ascii=False)

    if not policy.get("include_source_chunks", False):
        for field in _SOURCE_CHUNK_FIELDS:
            if f'"{field}"' in scan_text:
                raise ValueError(f"LLM input pack contains forbidden raw field: {field}")

    for field in _DEBUG_FIELDS | _VALIDATION_NOISE_FIELDS:
        if f'"{field}"' in scan_text:
            raise ValueError(f"LLM input pack contains forbidden debug/validation field: {field}")

    tokens_estimated = metadata.get("tokens_estimated") or estimate_tokens(payload_text)
    budget = resolve_stage_token_budget(pack["stage"])
    if tokens_estimated > budget:
        raise ValueError(
            f"LLM input pack exceeds stage token budget for {pack['stage']}: "
            f"{tokens_estimated} > {budget}"
        )
    return pack


def render_llm_input_pack(
    pack: Dict[str, Any],
    *,
    title: str = "LLM Input Pack",
    include_policy: bool = True,
) -> str:
    rendered = deepcopy(pack)
    if not include_policy:
        rendered.pop("input_policy", None)
    return f"{title}:\n{json.dumps(rendered, indent=2, ensure_ascii=False)}"


def call_llm_with_input_pack(
    *,
    llm: Any,
    prompt: str,
    input_pack: Dict[str, Any],
    manifest_path: Optional[Path],
    require_source_artifacts: bool = False,
    response_schema: Optional[Dict[str, Any]] = None,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
    system_prompt: Optional[str] = None,
) -> Any:
    validate_llm_input_pack(input_pack, require_source_artifacts=require_source_artifacts)
    response = llm.generate(
        prompt=prompt,
        response_schema=response_schema,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=system_prompt,
    )
    if manifest_path is not None:
        append_llm_call_manifest(
            manifest_path,
            input_pack=input_pack,
            response=response,
        )
    return response


def append_llm_call_manifest(
    path: Path,
    *,
    input_pack: Dict[str, Any],
    response: Any,
) -> Path:
    existing = {"entries": []}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("entries"), list):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {"entries": []}

    metadata = input_pack.get("metadata") or {}
    entry = {
        "stage": input_pack.get("stage"),
        "pack_name": input_pack.get("pack_name"),
        "model": getattr(response, "model", None),
        "provider": getattr(response, "provider", None),
        "estimated_prompt_tokens": metadata.get("tokens_estimated"),
        "actual_prompt_tokens": getattr(response, "prompt_tokens", None),
        "completion_tokens": getattr(response, "completion_tokens", None),
        "total_tokens": getattr(response, "total_tokens", None),
        "source_artifacts": list(metadata.get("source_artifacts") or []),
        "excluded_fields": list((input_pack.get("input_policy") or {}).get("excluded_sections") or []),
        "truncation_applied": bool(metadata.get("truncation_applied")),
        "warnings": list(metadata.get("warnings") or []),
        "generated_at": getattr(response, "generated_at", None),
    }
    existing["entries"].append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def resolve_stage_token_budget(stage: str) -> int:
    env_name = f"PROMETHEUS_LLM_BUDGET_{stage.upper()}"
    raw_value = os.getenv(env_name)
    default = DEFAULT_STAGE_TOKEN_BUDGETS.get(stage, 5000)
    if raw_value in (None, ""):
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _enforce_pack_budget(pack: Dict[str, Any]) -> Dict[str, Any]:
    policy = pack["input_policy"]
    max_chars = int(policy["max_chars"])
    stage_budget = resolve_stage_token_budget(pack["stage"])

    while True:
        payload_text = json.dumps(pack, ensure_ascii=False)
        chars = len(payload_text)
        tokens_estimated = estimate_tokens(payload_text)
        pack["metadata"]["chars"] = chars
        pack["metadata"]["tokens_estimated"] = tokens_estimated
        if chars <= max_chars and tokens_estimated <= stage_budget:
            return pack

        shrunk = False
        if len(pack["observations"]) > 1:
            pack["observations"] = cap_items(pack["observations"], max(1, len(pack["observations"]) - 1))
            shrunk = True
        elif len(pack["facts"]) > 1:
            pack["facts"] = cap_items(pack["facts"], max(1, len(pack["facts"]) - 1))
            shrunk = True

        if not shrunk:
            pack["metadata"]["warnings"].append(
                f"Input pack remains close to or above budget for stage {pack['stage']}."
            )
            pack["metadata"]["truncation_applied"] = True
            pack["metadata"]["chars"] = chars
            pack["metadata"]["tokens_estimated"] = tokens_estimated
            return pack

        pack["metadata"]["truncation_applied"] = True
        warning = (
            f"Input pack truncated to respect budget for stage {pack['stage']}."
        )
        if warning not in pack["metadata"]["warnings"]:
            pack["metadata"]["warnings"].append(warning)


def _resolve_policy(stage: str, policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    resolved = deepcopy(DEFAULT_STAGE_POLICIES.get(stage, {}))
    if policy:
        resolved.update(policy)
    if "max_chars" not in resolved:
        resolved["max_chars"] = resolve_stage_token_budget(stage) * 4
    if "max_items" not in resolved:
        resolved["max_items"] = 25
    if "include_source_chunks" not in resolved:
        resolved["include_source_chunks"] = False
    if "include_evidence_ids" not in resolved:
        resolved["include_evidence_ids"] = True
    if "include_short_excerpts" not in resolved:
        resolved["include_short_excerpts"] = False
    if "collect_evidence_ids" not in resolved:
        resolved["collect_evidence_ids"] = True
    if "allowed_sections" not in resolved:
        resolved["allowed_sections"] = []
    if "excluded_sections" not in resolved:
        resolved["excluded_sections"] = []
    return resolved


def _sanitize_for_policy(value: Any, policy: Dict[str, Any]) -> Any:
    value = deepcopy(value)
    value = select_relevant_sections(value, policy.get("allowed_sections"))
    value = strip_debug_fields(value)
    value = strip_validation_noise(value)
    if not policy.get("include_source_chunks", False):
        value = strip_source_chunks(value)
    value = compact_evidence_refs(
        value,
        max_excerpt_chars=300 if policy.get("include_short_excerpts") else 120,
    )
    return _prune_empty_values(value)


def _strip_keys(obj: Any, keys: Iterable[str]) -> Any:
    key_set = set(keys)
    if isinstance(obj, dict):
        return {
            key: _strip_keys(value, key_set)
            for key, value in obj.items()
            if key not in key_set
        }
    if isinstance(obj, list):
        return [_strip_keys(item, key_set) for item in obj]
    return obj


def _compact_single_evidence_reference(reference: Any, *, max_excerpt_chars: int) -> Dict[str, Any]:
    if not isinstance(reference, dict):
        text = str(reference or "").strip()
        return {
            "evidence_id": None,
            "page": None,
            "short_excerpt": _truncate_text(text, max_excerpt_chars),
            "source_artifact": None,
        }

    evidence_id = reference.get("evidence_id")
    if evidence_id is None:
        evidence_ids = reference.get("evidence_ids") or []
        if isinstance(evidence_ids, list) and evidence_ids:
            evidence_id = evidence_ids[0]

    excerpt_source = (
        reference.get("short_excerpt")
        or reference.get("content")
        or reference.get("summary")
        or reference.get("statement")
        or reference.get("source_chunk")
        or ""
    )
    return {
        "evidence_id": evidence_id,
        "page": reference.get("page"),
        "short_excerpt": _truncate_text(excerpt_source, max_excerpt_chars),
        "source_artifact": reference.get("source_artifact"),
    }


def _truncate_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


def _normalize_string_list(values: Optional[Sequence[Any]]) -> List[str]:
    normalized: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _collect_evidence_ids(value: Any) -> List[str]:
    evidence_ids: List[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "evidence_id":
                text = str(nested or "").strip()
                if text and text not in evidence_ids:
                    evidence_ids.append(text)
                continue
            if key == "evidence_ids" and isinstance(nested, list):
                for item in nested:
                    text = str(item or "").strip()
                    if text and text not in evidence_ids:
                        evidence_ids.append(text)
                continue
            for nested_id in _collect_evidence_ids(nested):
                if nested_id not in evidence_ids:
                    evidence_ids.append(nested_id)
        return evidence_ids
    if isinstance(value, list):
        for item in value:
            for nested_id in _collect_evidence_ids(item):
                if nested_id not in evidence_ids:
                    evidence_ids.append(nested_id)
    return evidence_ids


def _prune_empty_values(value: Any) -> Any:
    if isinstance(value, dict):
        compacted: Dict[str, Any] = {}
        for key, nested in value.items():
            pruned = _prune_empty_values(nested)
            if key in _DROP_EMPTY_KEYS and pruned in (None, "", [], {}):
                continue
            if pruned in (None, "", [], {}):
                continue
            compacted[key] = pruned
        return compacted
    if isinstance(value, list):
        compacted_list = [_prune_empty_values(item) for item in value]
        return [item for item in compacted_list if item not in (None, "", [], {})]
    return value
