from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


DOCTRINE_MEMORY_PRIORITIES: Dict[str, List[str]] = {
    "graham": [
        "financial memory",
        "risk evolution",
        "capital allocation outcomes",
        "management commitments",
        "capacity evolution",
        "projects",
        "management quality",
        "management commentary",
    ],
    "buffett": [
        "management quality",
        "capital allocation outcomes",
        "management commitments",
        "financial memory",
        "projects",
        "capacity evolution",
        "management commentary",
        "risk evolution",
    ],
    "fisher": [
        "management commitments",
        "projects",
        "capacity evolution",
        "management commentary",
        "management quality",
        "financial memory",
        "capital allocation outcomes",
        "risk evolution",
    ],
    "munger": [
        "management quality",
        "management commitments",
        "capital allocation outcomes",
        "risk evolution",
        "management commentary",
        "capacity evolution",
        "projects",
        "financial memory",
    ],
    "lynch": [
        "projects",
        "capacity evolution",
        "management commentary",
        "management commitments",
        "financial memory",
        "management quality",
        "risk evolution",
        "capital allocation outcomes",
    ],
}

STREAM_FILE_PRIORITY: Dict[str, List[Path]] = {
    "management commitments": [
        Path("company_memory/management_commitments/management_commitments.json"),
        Path("company_memory/management_commitments/commitment_timeline.json"),
        Path("company_memory/management_commitments/commitment_validation.json"),
    ],
    "projects": [
        Path("company_memory/projects/project_assessments.json"),
        Path("company_memory/projects/project_timelines.json"),
        Path("company_memory/projects/projects_registry.json"),
    ],
    "capacity evolution": [
        Path("company_memory/capacity/capacity_assessments.json"),
        Path("company_memory/capacity/capacity_timelines.json"),
        Path("company_memory/capacity/capacity_registry.json"),
    ],
    "risk evolution": [
        Path("company_memory/risks/risk_assessments.json"),
        Path("company_memory/risks/risk_timelines.json"),
        Path("company_memory/risks/risk_registry.json"),
        Path("company_memory/risk_evolution.json"),
    ],
    "management commentary": [
        Path("company_memory/management_commentary/commentary_assessments.json"),
        Path("company_memory/management_commentary/commentary_timelines.json"),
        Path("company_memory/management_commentary/commentary_themes.json"),
    ],
    "capital allocation outcomes": [
        Path("company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json"),
        Path("company_memory/capital_allocation_outcomes/capital_allocation_timelines.json"),
        Path("company_memory/capital_allocation_outcomes/capital_allocation_assessments.json"),
    ],
    "management quality": [
        Path("company_memory/management_quality/management_quality_summary.json"),
        Path("company_memory/management_quality/management_quality_dimensions.json"),
        Path("company_memory/management_quality/management_quality_evidence.json"),
    ],
    "financial memory": [
        Path("company_memory/financials/financial_memory_summary.json"),
        Path("company_memory/financials/financial_truth_pack.json"),
        Path("company_memory/financials/investor_financial_modules/owner_earnings_bridge.json"),
        Path("company_memory/financials/investor_financial_modules/working_capital_quality_drilldown.json"),
        Path("company_memory/financials/investor_financial_modules/per_share_compounding_analysis.json"),
    ],
}


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _truncate_text(value: Any, limit: int = 220) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def _normalize_string_list(value: Any, limit: int = 12) -> List[str]:
    items: List[str] = []
    if isinstance(value, str):
        cleaned = _truncate_text(value, 220)
        if cleaned:
            items.append(cleaned)
    elif isinstance(value, list):
        for item in value:
            items.extend(_normalize_string_list(item, limit=limit))
    elif isinstance(value, dict):
        for item in value.values():
            items.extend(_normalize_string_list(item, limit=limit))
    seen = set()
    result: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _deep_trim(value: Any, *, max_depth: int = 2, max_list_items: int = 3, max_str: int = 200) -> Any:
    if max_depth < 0:
        return _truncate_text(value, max_str)
    if isinstance(value, str):
        return _truncate_text(value, max_str)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [
            _deep_trim(item, max_depth=max_depth - 1, max_list_items=max_list_items, max_str=max_str)
            for item in value[:max_list_items]
        ]
    if isinstance(value, dict):
        trimmed: Dict[str, Any] = {}
        for key, nested in list(value.items())[:12]:
            trimmed[key] = _deep_trim(
                nested,
                max_depth=max_depth - 1,
                max_list_items=max_list_items,
                max_str=max_str,
            )
        return trimmed
    return _truncate_text(value, max_str)


def _collect_evidence_ids(value: Any) -> List[str]:
    ids: List[str] = []
    if isinstance(value, dict):
        direct = value.get("evidence_id")
        if isinstance(direct, str) and direct.strip():
            ids.append(direct.strip())
        many = value.get("evidence_ids")
        if isinstance(many, list):
            ids.extend(str(item).strip() for item in many if str(item).strip())
        source_refs = value.get("source_references")
        if isinstance(source_refs, list):
            for ref in source_refs:
                ids.extend(_collect_evidence_ids(ref))
        for nested in value.values():
            ids.extend(_collect_evidence_ids(nested))
    elif isinstance(value, list):
        for item in value:
            ids.extend(_collect_evidence_ids(item))
    seen = set()
    ordered: List[str] = []
    for item in ids:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _collect_source_artifacts(value: Any) -> List[str]:
    artifacts: List[str] = []
    if isinstance(value, dict):
        artifact = value.get("source_artifact")
        if isinstance(artifact, str) and artifact.strip():
            artifacts.append(artifact.strip())
        many = value.get("source_artifacts")
        if isinstance(many, list):
            artifacts.extend(str(item).strip() for item in many if str(item).strip())
        for nested in value.values():
            artifacts.extend(_collect_source_artifacts(nested))
    elif isinstance(value, list):
        for item in value:
            artifacts.extend(_collect_source_artifacts(item))
    seen = set()
    ordered: List[str] = []
    for item in artifacts:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _top_list(value: Any, limit: int = 3) -> List[Any]:
    if isinstance(value, list):
        return [_deep_trim(item, max_depth=0, max_list_items=2, max_str=140) for item in value[:limit]]
    return []


def _period_sort_key(value: Any) -> tuple:
    text = str(value or "").strip()
    if text.lower().startswith("fy"):
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits.isdigit():
            return (0, int(digits), text)
    return (1, text)


def _latest_period_from_records(records: Any) -> str:
    periods: List[str] = []
    if not isinstance(records, list):
        return ""
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in ("latest_period", "period", "first_observed_period", "announcement_period"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                periods.append(value.strip())
    if not periods:
        return ""
    return max(periods, key=_period_sort_key)


def _compact_commitments(payload: Dict[str, Any]) -> Dict[str, Any]:
    commitments = payload.get("commitments") or []
    timelines = payload.get("timeline") or []
    return {
        "company": payload.get("company"),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "commitment_count": payload.get("commitment_count"),
        "status_counts": _deep_trim(payload.get("status_counts") or {}, max_depth=0, max_list_items=4, max_str=60),
        "category_counts": _deep_trim(payload.get("category_counts") or {}, max_depth=0, max_list_items=4, max_str=60),
        "commitments": _top_list(commitments, limit=1),
        "timeline": _top_list(timelines, limit=1),
    }


def _compact_assessments(payload: Dict[str, Any], *, limit: int = 3) -> Dict[str, Any]:
    assessments = payload.get("assessments") or []
    compacted: List[Dict[str, Any]] = []
    for item in assessments[:limit]:
        if not isinstance(item, dict):
            continue
        compacted.append(
            {
                "id": item.get("project_id") or item.get("capacity_id") or item.get("risk_id") or item.get("theme_id") or item.get("allocation_id") or item.get("theme"),
                "period": item.get("period") or item.get("latest_period") or item.get("announcement_period"),
                "latest_period": item.get("latest_period") or item.get("period") or item.get("announcement_period"),
                "status": item.get("execution_status") or item.get("current_status") or item.get("status") or item.get("conviction_impact"),
                "what_changed": _truncate_text(item.get("what_changed") or item.get("execution_summary") or item.get("current_emphasis") or item.get("progression_summary"), 120),
                "why_it_changed": _truncate_text(item.get("why_it_changed") or item.get("why_it_matters") or item.get("investor_implication"), 120),
                "investor_implication": _truncate_text(item.get("investor_implication") or item.get("conviction_impact"), 120),
                "interpretation": _deep_trim(item.get("interpretation") or {}, max_depth=1, max_list_items=2, max_str=120),
            }
        )
    return {
        "company": payload.get("company") or payload.get("company_slug"),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "assessment_count": payload.get("assessment_count") or len(compacted),
        "assessments": compacted,
    }


def _compact_timelines(payload: Dict[str, Any], *, limit: int = 2) -> Dict[str, Any]:
    timelines = payload.get("timelines") or payload.get("timeline") or []
    return {
        "company": payload.get("company") or payload.get("company_slug"),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "timeline_count": payload.get("timeline_count") or len(timelines),
        "timelines": _top_list(timelines, limit=limit),
    }


def _compact_management_quality(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "company_slug": payload.get("company_slug") or payload.get("company"),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "latest_period": payload.get("latest_period"),
        "overall_view": _truncate_text(payload.get("overall_view"), 260),
        "overall_direction": payload.get("overall_direction"),
        "strongest_dimension": payload.get("strongest_dimension"),
        "weakest_dimension": payload.get("weakest_dimension"),
        "investor_implication": _truncate_text(payload.get("investor_implication"), 260),
        "interpretation": _deep_trim(payload.get("interpretation") or {}, max_depth=1, max_list_items=3, max_str=120),
        "what_strengthened_conviction": _top_list(payload.get("what_strengthened_conviction") or [], limit=2),
        "what_weakened_conviction": _top_list(payload.get("what_weakened_conviction") or [], limit=2),
        "what_remains_unproven": _top_list(payload.get("what_remains_unproven") or [], limit=2),
        "major_turning_points": _top_list(payload.get("major_turning_points") or [], limit=2),
        "evidence_confidence": _deep_trim(payload.get("evidence_confidence") or {}, max_depth=0, max_list_items=2, max_str=60),
    }


def _compact_financial_memory(payload: Dict[str, Any], source_dir: Path) -> Dict[str, Any]:
    compacted: Dict[str, Any] = {
        "company": payload.get("company"),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "status": payload.get("status"),
        "years_covered": list(payload.get("years_covered") or [])[:5],
        "basis_used": payload.get("basis_used"),
        "summary": _truncate_text(payload.get("summary"), 320),
        "key_strengths": _top_list(payload.get("key_strengths") or [], limit=2),
        "key_concerns": _top_list(payload.get("key_concerns") or [], limit=2),
        "missing_data": _top_list(payload.get("missing_data") or [], limit=2),
        "investor_questions": _top_list(payload.get("investor_questions") or [], limit=2),
        "warnings": _top_list(payload.get("warnings") or [], limit=2),
        "limitations": _top_list(payload.get("limitations") or [], limit=2),
    }

    module_dir = source_dir / "company_memory" / "financials" / "investor_financial_modules"
    module_files = [
        ("owner earnings bridge", module_dir / "owner_earnings_bridge.json"),
        ("working capital quality", module_dir / "working_capital_quality_drilldown.json"),
        ("per share compounding", module_dir / "per_share_compounding_analysis.json"),
        ("capital allocation ledger", module_dir / "capital_allocation_roi_ledger.json"),
    ]
    module_summaries: List[Dict[str, Any]] = []
    for label, path in module_files:
        module_payload = _load_json(path)
        if not module_payload:
            continue
        summary = {
            "module": label,
            "source_artifact": path.name,
            "years_covered": list(module_payload.get("years_covered") or [])[:5],
            "warnings": _top_list(module_payload.get("warnings") or [], limit=1),
            "limitations": _top_list(module_payload.get("limitations") or [], limit=1),
        }
        if "bridges" in module_payload:
            summary["bridges"] = _top_list(module_payload.get("bridges") or [], limit=1)
        if "drilldown" in module_payload:
            summary["drilldown"] = _top_list(module_payload.get("drilldown") or [], limit=1)
        if "analysis" in module_payload:
            summary["analysis"] = _top_list(module_payload.get("analysis") or [], limit=1)
        if "entries" in module_payload:
            summary["entries"] = _top_list(module_payload.get("entries") or [], limit=1)
        module_summaries.append(summary)
    if module_summaries:
        compacted["modules"] = module_summaries
    compacted["evidence_ids"] = _collect_evidence_ids(payload)[:20]
    return compacted


def _stream_priority(doctrine_id: str) -> List[str]:
    return DOCTRINE_MEMORY_PRIORITIES.get(
        doctrine_id,
        [
            "management quality",
            "management commitments",
            "projects",
            "capacity evolution",
            "risk evolution",
            "management commentary",
            "capital allocation outcomes",
            "financial memory",
        ],
    )


def _load_stream_payloads(company_root: Path) -> Dict[str, List[Tuple[Path, Dict[str, Any]]]]:
    company_memory_dir = company_root / "company_memory"
    payloads: Dict[str, List[Tuple[Path, Dict[str, Any]]]] = {}
    for stream_name, candidates in STREAM_FILE_PRIORITY.items():
        for relative in candidates:
            path = company_root / relative
            payload = _load_json(path)
            if not payload:
                continue
            payloads.setdefault(stream_name, []).append((path, payload))
    if not payloads:
        index_payload = _load_json(company_memory_dir / "company_memory_index.json")
        if index_payload:
            payloads["company memory index"] = [(company_memory_dir / "company_memory_index.json", index_payload)]
    return payloads


def build_company_memory_context(
    company_root: Path | str,
    doctrine_id: str,
    *,
    token_budget: int,
) -> Dict[str, Any]:
    company_root = Path(company_root)
    payloads_by_stream = _load_stream_payloads(company_root)
    if not payloads_by_stream:
        return {
            "company": company_root.name,
            "doctrine_id": doctrine_id,
            "context_version": "v2",
            "streams_considered": [],
            "streams_found": [],
            "streams_missing": [],
            "evidence_ids": [],
            "source_artifacts": [],
            "limitations": ["No company-memory streams were available for investor-panel context."],
        }

    company_memory_index = _load_json(company_root / "company_memory" / "company_memory_index.json")
    latest_years = list(company_memory_index.get("usable_years") or company_memory_index.get("ordered_years") or [])
    stream_blocks: List[Dict[str, Any]] = []
    source_artifacts: List[str] = []
    evidence_ids: List[str] = []

    stream_order = _stream_priority(doctrine_id)
    ordered_streams = sorted(
        payloads_by_stream.items(),
        key=lambda item: (
            stream_order.index(item[0]) if item[0] in stream_order else len(stream_order),
            item[0],
        ),
    )

    max_streams = 3
    max_items_per_stream = 1

    for stream_name, candidates in ordered_streams[:max_streams]:
        primary_path, primary_payload = candidates[0]
        source_artifacts.extend(str(path.relative_to(company_root)) for path, _payload in candidates if path.is_relative_to(company_root))
        derived_latest_period = (
            primary_payload.get("latest_period")
            or _latest_period_from_records(primary_payload.get("assessments") or primary_payload.get("timelines") or primary_payload.get("timeline") or [])
            or primary_payload.get("generated_at")
        )
        block: Dict[str, Any] = {
            "stream": stream_name,
            "source_artifacts": [
                str(path.relative_to(company_root))
                if path.is_relative_to(company_root)
                else path.name
                for path, _payload in candidates[:3]
            ],
            "primary_artifact": primary_path.name,
            "latest_period": derived_latest_period,
            "limitations": _top_list(primary_payload.get("limitations") or [], limit=3),
        }
        if stream_name == "management commitments":
            merged_commitments = deepcopy(primary_payload)
            for path, payload in candidates[1:]:
                if not merged_commitments.get("timeline") and payload.get("timeline"):
                    merged_commitments["timeline"] = payload.get("timeline")
                if not merged_commitments.get("validation") and payload.get("validation"):
                    merged_commitments["validation"] = payload.get("validation")
            block.update(_compact_commitments(merged_commitments))
        elif stream_name in {"projects", "capacity evolution", "risk evolution", "management commentary", "capital allocation outcomes"}:
            merged_assessments = deepcopy(primary_payload)
            for path, payload in candidates[1:]:
                if not merged_assessments.get("timelines") and payload.get("timelines"):
                    merged_assessments["timelines"] = payload.get("timelines")
                if not merged_assessments.get("timeline") and payload.get("timeline"):
                    merged_assessments["timeline"] = payload.get("timeline")
            block.update(_compact_assessments(merged_assessments, limit=max_items_per_stream))
        elif stream_name == "management quality":
            block.update(_compact_management_quality(primary_payload))
        elif stream_name == "financial memory":
            merged_financial = deepcopy(primary_payload)
            for path, payload in candidates[1:]:
                for key in ("summary", "key_strengths", "key_concerns", "missing_data", "investor_questions", "warnings", "limitations", "years_covered", "basis_used"):
                    if key not in merged_financial or not merged_financial.get(key):
                        if payload.get(key):
                            merged_financial[key] = payload.get(key)
            block.update(_compact_financial_memory(merged_financial, company_root))
        else:
            block["payload"] = _deep_trim(primary_payload, max_depth=1, max_list_items=max_items_per_stream, max_str=220)

        if "assessments" in block and isinstance(block["assessments"], list):
            block["assessments"] = block["assessments"][:max_items_per_stream]
        if "commitments" in block and isinstance(block["commitments"], list):
            block["commitments"] = block["commitments"][:max_items_per_stream]
        if "timeline" in block and isinstance(block["timeline"], list):
            block["timeline"] = block["timeline"][:2]
        if "modules" in block and isinstance(block["modules"], list):
            block["modules"] = block["modules"][:3]

        stream_blocks.append(block)
        source_artifacts.extend(_collect_source_artifacts(block))
        evidence_ids.extend(_collect_evidence_ids(block))

    seen_sources = set()
    source_artifacts = [item for item in source_artifacts if not (item in seen_sources or seen_sources.add(item))]
    seen_evidence = set()
    evidence_ids = [item for item in evidence_ids if not (item in seen_evidence or seen_evidence.add(item))]

    streams_found = [item["stream"] for item in stream_blocks]
    streams_missing = [name for name in stream_order if name not in streams_found]

    context = {
        "company": company_root.name,
        "doctrine_id": doctrine_id,
        "context_version": "v2",
        "latest_years": latest_years[:5],
        "streams_considered": stream_order,
        "streams_found": streams_found,
        "streams_missing": streams_missing,
        "streams": stream_blocks,
        "evidence_ids": evidence_ids[:20],
        "source_artifact_count": len(source_artifacts),
        "limitations": [
            "Deterministic longitudinal summary; read as progression evidence, not a snapshot scorecard."
        ],
    }
    return context
