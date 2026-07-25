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
        "max_chunks_per_question": 8,
        "max_chars_per_chunk": 900,
        "max_total_chunks": 20,
    },
    "investor_panel_analyst": {
        "allowed_sections": ["selected_pcim"],
        "excluded_sections": ["raw_text_fields", "debug_metadata", "validation_metadata"],
        "max_items": 3,
        "max_chars": 28000,
        "include_evidence_ids": True,
        "collect_evidence_ids": True,
        "include_short_excerpts": False,
        "include_source_chunks": False,
        "max_sections": 8,
        "max_items_per_section": 3,
        "max_nested_items_per_item": 5,
        "max_text_chars_per_value": 500,
        "max_evidence_ids_per_item": 5,
        "max_dict_keys_per_item": 8,
        "drop_raw_evidence_references": True,
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

_INVESTOR_PANEL_DROP_FIELDS = {
    "source_manifest",
    "pcim_source_manifest",
    "validation_report",
    "validation_reports",
    "validation_status",
    "debug",
    "debug_log",
    "debug_logs",
    "raw_text_fields",
    "raw_text",
    "full_text",
    "source_chunk",
    "source_chunks",
    "source_hashes",
    "content_hash",
    "modified_at",
    "generated_at",
    "run_summary",
    "stack_trace",
    "analysis_mode",
    "sections_consumed",
    "source_mentions",
    "source_references",
    "yearly_mentions",
    "full_evidence_map",
    "validation_debug",
}

_INVESTOR_PANEL_PREFERRED_KEYS = [
    "value",
    "year",
    "years_covered",
    "business_summary",
    "business_dnas",
    "category",
    "status",
    "confidence",
    "severity",
    "severity_by_year",
    "note",
    "explanation",
    "reason",
    "normalized_risk",
    "normalized_promise",
    "normalized_promise_theme",
    "theme",
    "signal_type",
    "evidence_ids",
    "source_year",
    "source_artifact",
    "source_item_id",
    "page",
    "limitations",
    "missing_sections",
    "incomplete_years",
    "items",
]


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
            "truncation_details": {
                "chunks_before": 0,
                "chunks_after": 0,
                "estimated_tokens_before": 0,
                "estimated_tokens_after": 0,
                "dropped_chunk_count": 0,
            },
            "warnings": [],
        },
    }

    pack = _apply_stage_specific_compaction(pack)
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
        "chunks_before": ((metadata.get("truncation_details") or {}).get("chunks_before")),
        "chunks_after": ((metadata.get("truncation_details") or {}).get("chunks_after")),
        "estimated_tokens_before": ((metadata.get("truncation_details") or {}).get("estimated_tokens_before")),
        "estimated_tokens_after": ((metadata.get("truncation_details") or {}).get("estimated_tokens_after")),
        "dropped_chunk_count": ((metadata.get("truncation_details") or {}).get("dropped_chunk_count")),
        "warnings": list(metadata.get("warnings") or []),
        "generated_at": getattr(response, "generated_at", None),
    }
    manifest_extra = metadata.get("manifest_extra") or {}
    if isinstance(manifest_extra, dict):
        entry.update(deepcopy(manifest_extra))
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
            truncation = pack["metadata"].setdefault("truncation_details", {})
            if truncation.get("estimated_tokens_after", 0) <= 0:
                truncation["estimated_tokens_after"] = tokens_estimated
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
            truncation = pack["metadata"].setdefault("truncation_details", {})
            truncation["estimated_tokens_after"] = tokens_estimated
            return pack

        pack["metadata"]["truncation_applied"] = True
        warning = (
            f"Input pack truncated to respect budget for stage {pack['stage']}."
        )
        if warning not in pack["metadata"]["warnings"]:
            pack["metadata"]["warnings"].append(warning)


def _apply_stage_specific_compaction(pack: Dict[str, Any]) -> Dict[str, Any]:
    stage = pack.get("stage")
    if stage == "business_intelligence":
        return _compact_business_intelligence_pack(pack)
    if stage == "investor_panel_analyst":
        return _compact_investor_panel_pack(pack)
    return pack


def _compact_investor_panel_pack(pack: Dict[str, Any]) -> Dict[str, Any]:
    policy = pack.get("input_policy") or {}
    metadata = pack.setdefault("metadata", {})
    truncation = metadata.setdefault(
        "truncation_details",
        {
            "chunks_before": 0,
            "chunks_after": 0,
            "estimated_tokens_before": 0,
            "estimated_tokens_after": 0,
            "dropped_chunk_count": 0,
        },
    )
    warnings = metadata.setdefault("warnings", [])

    before_text = json.dumps(pack, ensure_ascii=False)
    before_tokens = estimate_tokens(before_text)
    truncation["estimated_tokens_before"] = before_tokens
    metadata["chars"] = len(before_text)
    metadata["tokens_estimated"] = before_tokens

    items_before: Dict[str, int] = {}
    items_after: Dict[str, int] = {}
    dropped_items_count = 0

    observations = list(pack.get("observations") or [])
    compacted_observations = []
    for observation in observations:
        compacted, stats = _compact_investor_panel_value(
            observation,
            policy=policy,
            depth=0,
            top_section=None,
            parent_key=None,
        )
        compacted_observations.append(compacted)
        for key, value in stats["items_before"].items():
            items_before[key] = items_before.get(key, 0) + value
        for key, value in stats["items_after"].items():
            items_after[key] = items_after.get(key, 0) + value
        dropped_items_count += stats["dropped_items_count"]
    pack["observations"] = compacted_observations

    compacted_facts = []
    for fact in list(pack.get("facts") or []):
        compacted, stats = _compact_investor_panel_value(
            fact,
            policy=policy,
            depth=0,
            top_section=None,
            parent_key=None,
        )
        compacted_facts.append(compacted)
        for key, value in stats["items_before"].items():
            items_before[key] = items_before.get(key, 0) + value
        for key, value in stats["items_after"].items():
            items_after[key] = items_after.get(key, 0) + value
        dropped_items_count += stats["dropped_items_count"]
    pack["facts"] = compacted_facts

    after_text = json.dumps(pack, ensure_ascii=False)
    after_tokens = estimate_tokens(after_text)
    truncation["estimated_tokens_after"] = after_tokens
    metadata["chars"] = len(after_text)
    metadata["tokens_estimated"] = after_tokens
    if dropped_items_count > 0 or after_tokens < before_tokens:
        metadata["truncation_applied"] = True
        warning = "Investor panel input pack was recursively compacted to respect the analyst token budget."
        if warning not in warnings:
            warnings.append(warning)
    metadata["manifest_extra"] = {
        "sections_requested": sorted(items_before.keys()),
        "sections_included": sorted(items_after.keys()),
        "items_before": items_before,
        "items_after": items_after,
        "dropped_items_count": dropped_items_count,
        "dropped_sections": sorted([key for key, value in items_before.items() if value > 0 and items_after.get(key, 0) == 0]),
    }
    return pack


def _compact_investor_panel_value(
    value: Any,
    *,
    policy: Dict[str, Any],
    depth: int,
    top_section: Optional[str],
    parent_key: Optional[str],
) -> Tuple[Any, Dict[str, Any]]:
    stats = {
        "items_before": {},
        "items_after": {},
        "dropped_items_count": 0,
    }
    max_sections = int(policy.get("max_sections") or 8)
    max_items_per_section = int(policy.get("max_items_per_section") or 3)
    max_nested_items_per_item = int(policy.get("max_nested_items_per_item") or 5)
    max_text_chars_per_value = int(policy.get("max_text_chars_per_value") or 500)
    max_evidence_ids_per_item = int(policy.get("max_evidence_ids_per_item") or 5)
    max_dict_keys_per_item = int(policy.get("max_dict_keys_per_item") or 8)
    include_short_excerpts = bool(policy.get("include_short_excerpts", False))
    drop_raw_evidence_references = bool(policy.get("drop_raw_evidence_references", True))

    if value is None or isinstance(value, (bool, int, float)):
        return value, stats

    if isinstance(value, str):
        return _truncate_text(value, max_text_chars_per_value), stats

    if isinstance(value, list):
        section_key = top_section or parent_key or "items"
        limit = max_items_per_section if depth <= 2 or parent_key == "items" else max_nested_items_per_item
        if parent_key == "evidence_ids":
            trimmed = _normalize_string_list(value)[:max_evidence_ids_per_item]
            stats["dropped_items_count"] += max(0, len(_normalize_string_list(value)) - len(trimmed))
            return trimmed, stats
        if parent_key == "evidence_references" and drop_raw_evidence_references:
            if include_short_excerpts:
                compacted_refs = []
                for item in value[:max_nested_items_per_item]:
                    compacted_refs.append(_compact_single_evidence_reference(item, max_excerpt_chars=min(300, max_text_chars_per_value)))
                stats["dropped_items_count"] += max(0, len(value) - len(compacted_refs))
                return compacted_refs, stats
            stats["dropped_items_count"] += len(value)
            return [], stats

        stats["items_before"][section_key] = stats["items_before"].get(section_key, 0) + len(value)
        compacted_list = []
        for item in value[:limit]:
            compacted_item, child_stats = _compact_investor_panel_value(
                item,
                policy=policy,
                depth=depth + 1,
                top_section=top_section,
                parent_key=parent_key,
            )
            if compacted_item not in (None, "", [], {}):
                compacted_list.append(compacted_item)
            _merge_panel_compaction_stats(stats, child_stats)
        stats["items_after"][section_key] = stats["items_after"].get(section_key, 0) + len(compacted_list)
        stats["dropped_items_count"] += max(0, len(value) - len(compacted_list))
        return compacted_list, stats

    if isinstance(value, dict):
        if depth == 0 and "selected_pcim" in value and isinstance(value["selected_pcim"], dict):
            selected = value["selected_pcim"]
            compacted_selected = {}
            section_names = list(selected.keys())[:max_sections]
            stats["dropped_items_count"] += max(0, len(selected) - len(section_names))
            for section_name in section_names:
                compacted_item, child_stats = _compact_investor_panel_value(
                    selected.get(section_name),
                    policy=policy,
                    depth=1,
                    top_section=section_name,
                    parent_key=section_name,
                )
                if compacted_item not in (None, "", [], {}):
                    compacted_selected[section_name] = compacted_item
                _merge_panel_compaction_stats(stats, child_stats)
            return {"selected_pcim": compacted_selected}, stats

        compacted_dict: Dict[str, Any] = {}
        candidate_keys = [key for key in value.keys() if key not in _INVESTOR_PANEL_DROP_FIELDS]
        if depth >= 1:
            preferred_keys = [key for key in _INVESTOR_PANEL_PREFERRED_KEYS if key in candidate_keys]
            other_keys = [key for key in candidate_keys if key not in preferred_keys]
            key_limit = max_dict_keys_per_item if depth == 1 else max(4, max_dict_keys_per_item - 2)
            ordered_keys = (preferred_keys + other_keys)[:key_limit]
            stats["dropped_items_count"] += max(0, len(candidate_keys) - len(ordered_keys))
        else:
            ordered_keys = candidate_keys

        for key in ordered_keys:
            nested = value.get(key)
            if key == "evidence_ids":
                compacted_dict[key] = _normalize_string_list(nested)[:max_evidence_ids_per_item]
                if isinstance(nested, list):
                    stats["dropped_items_count"] += max(0, len(nested) - len(compacted_dict[key]))
                continue
            if key == "evidence_references":
                if include_short_excerpts:
                    compacted_refs = [
                        _compact_single_evidence_reference(item, max_excerpt_chars=min(300, max_text_chars_per_value))
                        for item in list(nested or [])[:max_nested_items_per_item]
                    ]
                    compacted_dict[key] = compacted_refs
                else:
                    stats["dropped_items_count"] += len(list(nested or []))
                continue
            if key == "evidence_map" and isinstance(nested, dict):
                compacted_map: Dict[str, Any] = {}
                for evidence_section, evidence_ids in list(nested.items())[:max_sections]:
                    ids = _normalize_string_list(evidence_ids)[:max_evidence_ids_per_item]
                    compacted_map[evidence_section] = ids
                    if isinstance(evidence_ids, list):
                        stats["dropped_items_count"] += max(0, len(evidence_ids) - len(ids))
                compacted_dict[key] = compacted_map
                stats["dropped_items_count"] += max(0, len(nested) - len(compacted_map))
                continue

            compacted_item, child_stats = _compact_investor_panel_value(
                nested,
                policy=policy,
                depth=depth + 1,
                top_section=top_section,
                parent_key=key,
            )
            if compacted_item in (None, "", [], {}):
                continue
            compacted_dict[key] = compacted_item
            _merge_panel_compaction_stats(stats, child_stats)
        return compacted_dict, stats

    return _truncate_text(str(value), max_text_chars_per_value), stats


def _merge_panel_compaction_stats(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    for bucket in ("items_before", "items_after"):
        target_bucket = target.setdefault(bucket, {})
        for key, value in (source.get(bucket) or {}).items():
            target_bucket[key] = target_bucket.get(key, 0) + value
    target["dropped_items_count"] = int(target.get("dropped_items_count") or 0) + int(source.get("dropped_items_count") or 0)


def _compact_business_intelligence_pack(pack: Dict[str, Any]) -> Dict[str, Any]:
    policy = pack.get("input_policy") or {}
    metadata = pack.setdefault("metadata", {})
    truncation = metadata.setdefault(
        "truncation_details",
        {
            "chunks_before": 0,
            "chunks_after": 0,
            "estimated_tokens_before": 0,
            "estimated_tokens_after": 0,
            "dropped_chunk_count": 0,
        },
    )

    max_chunks_per_question = int(policy.get("max_chunks_per_question") or 8)
    max_chars_per_chunk = int(policy.get("max_chars_per_chunk") or 900)
    max_total_chunks = int(policy.get("max_total_chunks") or 20)
    stage_budget = resolve_stage_token_budget(pack["stage"])

    observations = list(pack.get("observations") or [])
    if not observations:
        payload_text = json.dumps(pack, ensure_ascii=False)
        metadata["chars"] = len(payload_text)
        metadata["tokens_estimated"] = estimate_tokens(payload_text)
        truncation["estimated_tokens_before"] = metadata["tokens_estimated"]
        truncation["estimated_tokens_after"] = metadata["tokens_estimated"]
        return pack

    chunks_before = 0
    for observation in observations:
        if isinstance(observation, dict):
            chunks_before += len(observation.get("chunks") or [])

    raw_text = json.dumps(pack, ensure_ascii=False)
    truncation["chunks_before"] = chunks_before
    truncation["estimated_tokens_before"] = estimate_tokens(raw_text)

    compacted_observations = []
    dropped_chunk_count = 0
    warnings = metadata.setdefault("warnings", [])
    for observation in observations:
        if not isinstance(observation, dict):
            compacted_observations.append(observation)
            continue
        compacted, dropped = _compact_business_intelligence_observation(
            observation,
            max_chunks_per_question=max_chunks_per_question,
            max_chars_per_chunk=max_chars_per_chunk,
            max_total_chunks=max_total_chunks,
            stage_budget=stage_budget,
        )
        dropped_chunk_count += dropped
        compacted_observations.append(compacted)

    pack["observations"] = compacted_observations
    chunks_after = sum(
        len(item.get("chunks") or [])
        for item in compacted_observations
        if isinstance(item, dict)
    )
    truncation["chunks_after"] = chunks_after
    truncation["dropped_chunk_count"] = dropped_chunk_count
    if dropped_chunk_count > 0:
        metadata["truncation_applied"] = True
        warning = "Business intelligence chunks were compacted to respect the stage token budget."
        if warning not in warnings:
            warnings.append(warning)

    _finalize_business_intelligence_budget(pack, stage_budget=stage_budget)

    payload_text = json.dumps(pack, ensure_ascii=False)
    metadata["chars"] = len(payload_text)
    metadata["tokens_estimated"] = estimate_tokens(payload_text)
    truncation["estimated_tokens_after"] = metadata["tokens_estimated"]
    return pack


def _finalize_business_intelligence_budget(pack: Dict[str, Any], *, stage_budget: int) -> None:
    observations = [
        item for item in (pack.get("observations") or [])
        if isinstance(item, dict)
    ]
    if not observations:
        return

    metadata = pack.setdefault("metadata", {})
    truncation = metadata.setdefault("truncation_details", {})

    def total_tokens() -> int:
        return estimate_tokens(json.dumps(pack, ensure_ascii=False))

    def chunk_refs() -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        refs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        for observation in observations:
            for chunk in observation.get("chunks") or []:
                if isinstance(chunk, dict):
                    refs.append((observation, chunk))
        refs.sort(key=lambda item: _score_bi_chunk(item[1], original_text=item[1].get("text", "")))
        return refs

    while total_tokens() > stage_budget:
        refs = chunk_refs()
        if not refs:
            break
        changed = False
        for _, chunk in refs:
            text = str(chunk.get("text") or "")
            if len(text) > 240:
                chunk["text"] = _truncate_text(text, max(180, len(text) - 180))
                changed = True
                metadata["truncation_applied"] = True
                break
            if "evidence_quality" in chunk and chunk["evidence_quality"]:
                chunk.pop("evidence_quality", None)
                changed = True
                metadata["truncation_applied"] = True
                break
            if chunk.get("page") not in (None, ""):
                chunk.pop("page", None)
                changed = True
                metadata["truncation_applied"] = True
                break
            if chunk.get("year") not in (None, ""):
                chunk.pop("year", None)
                changed = True
                metadata["truncation_applied"] = True
                break
            if "retrieval_score" in chunk:
                chunk.pop("retrieval_score", None)
                changed = True
                metadata["truncation_applied"] = True
                break
        if changed:
            continue

        # Last resort: drop the lowest-ranked chunk, but keep at least one chunk per observation.
        dropped = False
        for observation, chunk in refs:
            chunks = observation.get("chunks") or []
            if len(chunks) <= 1:
                continue
            observation["chunks"] = [item for item in chunks if item is not chunk]
            truncation["dropped_chunk_count"] = int(truncation.get("dropped_chunk_count") or 0) + 1
            metadata["truncation_applied"] = True
            dropped = True
            break
        if not dropped:
            break

    truncation["chunks_after"] = sum(
        len(item.get("chunks") or [])
        for item in observations
    )


def _compact_business_intelligence_observation(
    observation: Dict[str, Any],
    *,
    max_chunks_per_question: int,
    max_chars_per_chunk: int,
    max_total_chunks: int,
    stage_budget: int,
) -> Tuple[Dict[str, Any], int]:
    compacted = deepcopy(observation)
    questions = compacted.get("questions") or []
    chunks = list(compacted.get("chunks") or [])
    if not isinstance(chunks, list):
        return compacted, 0

    ranked = [_normalize_bi_chunk(chunk, max_chars_per_chunk=max_chars_per_chunk) for chunk in chunks]
    ranked.sort(key=lambda item: item["_rank"], reverse=True)

    capped_limit = max_total_chunks
    if questions:
        capped_limit = min(max_total_chunks, max(1, len(questions)) * max(1, max_chunks_per_question))
    selected = ranked[:capped_limit]
    dropped = max(0, len(ranked) - len(selected))
    compacted["chunks"] = [_strip_bi_rank_fields(item) for item in selected]

    temp_pack = {
        "stage": "business_intelligence",
        "observations": [compacted],
        "facts": [],
        "limitations": [],
        "evidence_ids": _collect_evidence_ids(compacted),
        "input_policy": {"include_source_chunks": True},
        "metadata": {},
    }
    while estimate_tokens(json.dumps(temp_pack, ensure_ascii=False)) > stage_budget and len(compacted["chunks"]) > 1:
        compacted["chunks"] = compacted["chunks"][:-1]
        dropped += 1
        temp_pack["observations"] = [compacted]

    if estimate_tokens(json.dumps(temp_pack, ensure_ascii=False)) > stage_budget:
        for chunk in compacted["chunks"]:
            text = str(chunk.get("text") or "")
            chunk["text"] = _truncate_text(text, max(180, max_chars_per_chunk // 2))
        temp_pack["observations"] = [compacted]
        while estimate_tokens(json.dumps(temp_pack, ensure_ascii=False)) > stage_budget and len(compacted["chunks"]) > 1:
            compacted["chunks"] = compacted["chunks"][:-1]
            dropped += 1
            temp_pack["observations"] = [compacted]

    return compacted, dropped


def _normalize_bi_chunk(chunk: Any, *, max_chars_per_chunk: int) -> Dict[str, Any]:
    if isinstance(chunk, dict):
        metadata = deepcopy(chunk.get("metadata") or {})
        text = str(chunk.get("text") or "")
        retrieval_score = float(chunk.get("retrieval_score") or metadata.get("retrieval_score") or 0.0)
        chunk_id = chunk.get("chunk_id")
        page = chunk.get("page", metadata.get("page"))
        year = chunk.get("year", metadata.get("year"))
        evidence_ids = _normalize_string_list(chunk.get("evidence_ids") or metadata.get("evidence_ids") or [])
        evidence_quality = deepcopy(chunk.get("evidence_quality") or metadata.get("evidence_quality") or {})
    else:
        metadata = deepcopy(getattr(chunk, "metadata", {}) or {})
        text = str(getattr(chunk, "text", "") or "")
        retrieval_score = float(getattr(chunk, "retrieval_score", 0.0) or metadata.get("retrieval_score") or 0.0)
        chunk_id = getattr(chunk, "chunk_id", None)
        page = metadata.get("page")
        year = metadata.get("year")
        evidence_ids = _normalize_string_list(metadata.get("evidence_ids") or [])
        evidence_quality = deepcopy(metadata.get("evidence_quality") or {})

    normalized = {
        "chunk_id": chunk_id,
        "text": _truncate_text(text, max_chars_per_chunk),
        "retrieval_score": retrieval_score,
        "page": page,
        "year": year,
        "evidence_ids": evidence_ids,
        "evidence_quality": evidence_quality,
    }
    normalized["_rank"] = _score_bi_chunk(normalized, original_text=text)
    return normalized


def _score_bi_chunk(chunk: Dict[str, Any], *, original_text: str) -> float:
    text = str(original_text or chunk.get("text") or "")
    lowered = text.lower()
    score = float(chunk.get("retrieval_score") or 0.0) * 10.0
    evidence_quality = chunk.get("evidence_quality") or {}
    company_specificity = str(evidence_quality.get("company_specificity") or "").lower()
    actor_type = str(evidence_quality.get("actor_type") or "").lower()

    if company_specificity == "high":
        score += 8.0
    elif company_specificity == "medium":
        score += 4.0
    elif company_specificity == "low":
        score -= 3.0

    if actor_type in {"company", "management"}:
        score += 4.0
    elif actor_type in {"government", "industry", "auditor"}:
        score -= 4.0

    if chunk.get("evidence_ids"):
        score += 3.0
    if chunk.get("page") not in (None, ""):
        score += 1.5
    if chunk.get("year"):
        score += 1.5
    if any(char.isdigit() for char in text):
        score += 2.0
    if any(token in lowered for token in ("commissioned", "launched", "signed", "approved", "acquired", "invested", "expanded", "implemented", "deployed")):
        score += 2.5
    if any(token in lowered for token in ("macro", "industry outlook", "global economy", "table of contents", "corporate governance report")):
        score -= 4.0
    score -= min(len(text) / 2500.0, 2.0)
    return score


def _strip_bi_rank_fields(chunk: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(chunk)
    cleaned.pop("_rank", None)
    return cleaned


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
