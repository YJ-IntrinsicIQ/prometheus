from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from knowledge.company_memory import parse_financial_year
from knowledge.company_memory.guardrails import (
    assess_progression_materiality,
    build_semantic_quality,
    classify_business_relevance,
    resolve_period_status,
    semantic_validation,
)

from intelligence.progression import build_confidence, validate_progression_payload

from .consistency import assess_consistency
from .contracts import COMMENTARY_GENERATOR_VERSION, COMMENTARY_SCHEMA_VERSION
from .manifest import build_commentary_manifest
from .paths import (
    get_commentary_assessments_path,
    get_commentary_dir,
    get_commentary_manifest_path,
    get_commentary_themes_path,
    get_commentary_timelines_path,
    get_commentary_validation_path,
)
from .progression import ManagementCommentaryProgressionAdapter, build_commentary_event, build_timeline
from .specificity import assess_specificity
from .theme_mapper import (
    build_source_reference,
    build_theme_name,
    compact_text,
    derive_theme_category,
    extract_year_label,
    normalize_text,
    sanitize_public_text,
    slugify,
    title_case_label,
    token_set,
)
from .validators import validate_commentary_payload
from .writer import write_json_file


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Dict[str, Any] | List[Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _discover_years(company_root: Path) -> List[Path]:
    if not company_root.exists():
        return []
    return sorted(
        [path for path in company_root.iterdir() if path.is_dir() and path.name.lower().startswith("fy")],
        key=lambda path: parse_financial_year(path.name),
    )


def _candidate_sources() -> List[Tuple[str, Path]]:
    return [
        ("management_summary", Path("intelligence") / "management_summary.json"),
        ("company_intelligence", Path("intelligence") / "company_intelligence.json"),
    ]


def _load_year_record(year_dir: Path) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "year": year_dir.name,
        "sort_key": parse_financial_year(year_dir.name),
        "paths": {"year_root": str(year_dir)},
        "source_artifacts": {},
    }
    for source_name, rel_path in _candidate_sources():
        path = year_dir / rel_path
        payload = _load_json(path)
        record["source_artifacts"][source_name] = {"path": str(path), "found": bool(payload)}
        record[source_name] = payload if isinstance(payload, (dict, list)) else {}
    return record


def _load_company_memory_payload(path: Path) -> Dict[str, Any]:
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


def _load_related_commitments(company_root: Path) -> List[Dict[str, Any]]:
    path = company_root / "company_memory" / "management_commitments" / "management_commitments.json"
    payload = _load_company_memory_payload(path)
    return list(payload.get("commitments") or [])


def _load_related_projects(company_root: Path) -> List[Dict[str, Any]]:
    path = company_root / "company_memory" / "projects" / "projects_registry.json"
    payload = _load_company_memory_payload(path)
    return list(payload.get("projects") or [])


def _load_related_capacity(company_root: Path) -> List[Dict[str, Any]]:
    path = company_root / "company_memory" / "capacity" / "capacity_registry.json"
    payload = _load_company_memory_payload(path)
    return list(payload.get("capacity_items") or payload.get("capacities") or [])


def _load_related_risks(company_root: Path) -> List[Dict[str, Any]]:
    path = company_root / "company_memory" / "risks" / "risk_registry.json"
    payload = _load_company_memory_payload(path)
    return list(payload.get("risks") or [])


def _load_financial_artifacts(company_root: Path) -> Dict[str, Any]:
    financial_root = company_root / "company_memory" / "financials"
    return {
        "summary": _load_company_memory_payload(financial_root / "financial_memory_summary.json"),
        "driver_attribution": _load_company_memory_payload(financial_root / "financial_driver_attribution.json"),
        "truth_pack": _load_company_memory_payload(financial_root / "financial_truth_pack.json"),
        "capital_timeline": _load_company_memory_payload(financial_root / "capital_allocation_financial_timeline.json"),
    }


def is_management_commentary(text: Any, *, actor: Any = "", source_bucket: str = "") -> bool:
    normalized = " ".join(str(text or "").lower().split())
    actor_text = str(actor or "").lower()
    thought_markers = (
        "management believes", "management expects", "management attributed", "management explained",
        "we believe", "we expect", "expect", "we plan", "we intend", "we aim", "our strategy", "management said",
        "our priority", "focus on", "outlook", "anticipate", "because", "due to",
        "in order to", "with the objective", "to prepare for", "views", "caution",
    )
    corporate_fact_markers = ("approved", "completed", "installed", "acquired", "debt increased", "capex investment", "dividend paid")
    has_thought = any(marker in normalized for marker in thought_markers)
    explicit_management = actor_text in {"management", "company_management", "company board", "board"}
    if any(marker in normalized for marker in corporate_fact_markers) and not has_thought:
        return False
    return has_thought or (explicit_management and source_bucket in {"management_focus", "management_credibility"})


def _extract_candidate_items(year_record: Dict[str, Any]) -> List[Dict[str, Any]]:
    commentary_items: List[Dict[str, Any]] = []
    management_summary = year_record.get("management_summary") or {}
    for bucket_name in ("company_management_actions", "company_results", "risk_responses"):
        items = management_summary.get(bucket_name) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if bucket_name == "company_management_actions" and not item.get("should_feed_management_consistency", True):
                continue
            commentary_text = select_commentary_text(item)
            if not commentary_text:
                continue
            if not is_management_commentary(commentary_text, actor=item.get("actor"), source_bucket=bucket_name):
                continue
            raw_theme = item.get("theme") or item.get("category") or item.get("value") or commentary_text
            theme_name = build_theme_name({"theme": raw_theme, "category": item.get("category"), "value": item.get("value"), "commentary": commentary_text})
            normalized_theme = slugify(theme_name)
            theme_category = derive_theme_category(theme_name, commentary_text, item.get("category"))
            relevance = classify_business_relevance(
                commentary_text,
                module_name="commentary",
                actor_type=str(item.get("actor") or ""),
                source_kind="management_summary",
            )
            period_resolution = resolve_period_status(
                source_year=year_record.get("year"),
                text=commentary_text,
                explicit_year=item.get("year") or year_record.get("year"),
            )
            materiality = assess_progression_materiality(
                commentary_text,
                module_name="commentary",
                relevance_status=str(relevance.get("status") or "ambiguous"),
                period_status=str(period_resolution.get("status") or "AMBIGUOUS"),
                evidence_quality=None,
                status_text=str(item.get("status") or ""),
            )
            semantic_flags = semantic_validation(
                module_name="commentary",
                relevance=relevance,
                period=period_resolution,
                materiality=materiality,
            )
            if semantic_flags["errors"] or not materiality.get("should_promote"):
                continue
            source_reference = build_source_reference(year_record, item, "management_summary")
            specificity = assess_specificity(
                item,
                commentary_text,
                repeated_years=1,
                related_links=0,
            )
            commentary_items.append(
                {
                    "source_year": extract_year_label(year_record.get("year")),
                    "sort_key": year_record.get("sort_key", 10_000),
                    "source_artifact": "management_summary.json",
                    "source_item_id": item.get("item_id") or item.get("source_item_id") or item.get("id") or item.get("value"),
                    "source_reference": source_reference,
                    "theme_name": theme_name,
                    "normalized_theme": normalized_theme,
                    "theme_category": theme_category,
                    "raw_theme": item.get("theme"),
                    "raw_category": item.get("category"),
                    "commentary": commentary_text,
                    "status": item.get("status"),
                    "sentiment": item.get("sentiment") or item.get("status"),
                    "actor": item.get("actor"),
                    "time_reference": item.get("time_reference"),
                    "page": item.get("page"),
                    "confidence": item.get("confidence") if isinstance(item.get("confidence"), dict) else build_confidence(str(item.get("confidence") or "medium"), basis=["management_summary record"], limitations=[]),
                    "evidence_status": "supported" if len(specificity["basis"]) >= 2 else "partial",
                    "specificity": specificity,
                    "should_feed_management_consistency": item.get("should_feed_management_consistency", True),
                    "should_feed_company_strategy": item.get("should_feed_company_strategy", True),
                    "should_feed_external_context": item.get("should_feed_external_context", False),
                    "semantic_relevance": relevance,
                    "period_resolution": period_resolution,
                    "progression_materiality": materiality,
                    "semantic_validation": semantic_flags,
                }
            )

    management = year_record.get("company_intelligence", {}).get("management") or {}
    for key in ("summary", "focus", "credibility"):
        payload = management.get(key)
        if isinstance(payload, dict):
            for subkey, value in payload.items():
                text = sanitize_public_text(value)
                if not text:
                    continue
                if not is_management_commentary(text, actor="management", source_bucket=f"management_{key}"):
                    continue
                item = {
                    "theme": title_case_label(subkey or key),
                    "category": "Strategy" if key == "summary" else "Other",
                    "value": text,
                    "commentary": text,
                    "page": None,
                    "status": "informational",
                    "confidence": "medium",
                    "time_reference": "period_specific",
                }
                relevance = classify_business_relevance(
                    text,
                    module_name="commentary",
                    actor_type="management",
                    source_kind="company_intelligence",
                )
                period_resolution = resolve_period_status(
                    source_year=year_record.get("year"),
                    text=text,
                    explicit_year=year_record.get("year"),
                )
                materiality = assess_progression_materiality(
                    text,
                    module_name="commentary",
                    relevance_status=str(relevance.get("status") or "ambiguous"),
                    period_status=str(period_resolution.get("status") or "AMBIGUOUS"),
                    evidence_quality=None,
                    status_text="informational",
                )
                semantic_flags = semantic_validation(
                    module_name="commentary",
                    relevance=relevance,
                    period=period_resolution,
                    materiality=materiality,
                )
                if semantic_flags["errors"] or not materiality.get("should_promote"):
                    continue
                semantic_quality = build_semantic_quality(
                    classification="management_commentary",
                    relevance=relevance,
                    period=period_resolution,
                    materiality=materiality,
                    eligibility="eligible",
                    evidence_confidence="medium",
                )
                source_reference = build_source_reference(year_record, {"item_id": f"management_{key}_{subkey}", "page": None, "confidence": "medium", "value": text}, "company_intelligence")
                specificity = assess_specificity(item, text)
                commentary_items.append(
                    {
                        "source_year": extract_year_label(year_record.get("year")),
                        "sort_key": year_record.get("sort_key", 10_000),
                        "source_artifact": "company_intelligence.json",
                        "source_item_id": f"management_{key}_{subkey}",
                        "source_reference": source_reference,
                        "theme_name": build_theme_name(item),
                        "normalized_theme": slugify(build_theme_name(item)),
                        "theme_category": derive_theme_category(item.get("theme"), text, item.get("category")),
                        "raw_theme": item.get("theme"),
                        "raw_category": item.get("category"),
                        "commentary": text,
                        "status": item.get("status"),
                        "sentiment": item.get("sentiment") or "neutral",
                        "actor": "management",
                        "time_reference": "period_specific",
                        "page": None,
                        "confidence": build_confidence("medium", basis=["company intelligence management summary"], limitations=[]),
                        "evidence_status": "partial",
                        "specificity": specificity,
                        "should_feed_management_consistency": True,
                        "should_feed_company_strategy": True,
                        "should_feed_external_context": False,
                        "semantic_quality": semantic_quality,
                        "semantic_relevance": relevance,
                        "period_resolution": period_resolution,
                        "progression_materiality": materiality,
                        "semantic_validation": semantic_flags,
                    }
                )
        elif isinstance(payload, list):
            for idx, value in enumerate(payload, start=1):
                text = sanitize_public_text(value)
                if not text:
                    continue
                if not is_management_commentary(text, actor="management", source_bucket=f"management_{key}"):
                    continue
                item = {
                    "theme": title_case_label(key),
                    "category": "Strategy" if key == "summary" else "Other",
                    "value": text,
                    "commentary": text,
                    "page": None,
                    "status": "informational",
                    "confidence": "medium",
                    "time_reference": "period_specific",
                }
                relevance = classify_business_relevance(
                    text,
                    module_name="commentary",
                    actor_type="management",
                    source_kind="company_intelligence",
                )
                period_resolution = resolve_period_status(
                    source_year=year_record.get("year"),
                    text=text,
                    explicit_year=year_record.get("year"),
                )
                materiality = assess_progression_materiality(
                    text,
                    module_name="commentary",
                    relevance_status=str(relevance.get("status") or "ambiguous"),
                    period_status=str(period_resolution.get("status") or "AMBIGUOUS"),
                    evidence_quality=None,
                    status_text="informational",
                )
                semantic_flags = semantic_validation(
                    module_name="commentary",
                    relevance=relevance,
                    period=period_resolution,
                    materiality=materiality,
                )
                if semantic_flags["errors"] or not materiality.get("should_promote"):
                    continue
                semantic_quality = build_semantic_quality(
                    classification="management_commentary",
                    relevance=relevance,
                    period=period_resolution,
                    materiality=materiality,
                    eligibility="eligible",
                    evidence_confidence="medium",
                )
                source_reference = build_source_reference(year_record, {"item_id": f"management_{key}_{idx}", "page": None, "confidence": "medium", "value": text}, "company_intelligence")
                specificity = assess_specificity(item, text)
                commentary_items.append(
                    {
                        "source_year": extract_year_label(year_record.get("year")),
                        "sort_key": year_record.get("sort_key", 10_000),
                        "source_artifact": "company_intelligence.json",
                        "source_item_id": f"management_{key}_{idx}",
                        "source_reference": source_reference,
                        "theme_name": build_theme_name(item),
                        "normalized_theme": slugify(build_theme_name(item)),
                        "theme_category": derive_theme_category(item.get("theme"), text, item.get("category")),
                        "raw_theme": item.get("theme"),
                        "raw_category": item.get("category"),
                        "commentary": text,
                        "status": item.get("status"),
                        "sentiment": item.get("sentiment") or "neutral",
                        "actor": "management",
                        "time_reference": "period_specific",
                        "page": None,
                        "confidence": build_confidence("medium", basis=["company intelligence management summary"], limitations=[]),
                        "evidence_status": "partial",
                        "specificity": specificity,
                        "should_feed_management_consistency": True,
                        "should_feed_company_strategy": True,
                        "should_feed_external_context": False,
                        "semantic_quality": semantic_quality,
                        "semantic_relevance": relevance,
                        "period_resolution": period_resolution,
                        "progression_materiality": materiality,
                        "semantic_validation": semantic_flags,
                    }
                )
    return commentary_items


def select_commentary_text(item: Dict[str, Any]) -> str:
    for field in ("commentary", "value", "summary", "description"):
        text = sanitize_public_text(item.get(field))
        if text:
            return text
    return ""


def _group_candidates(candidates: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    groups: List[Dict[str, Any]] = []
    merged = 0
    for candidate in sorted(candidates, key=lambda item: (item["sort_key"], item["theme_category"], item["normalized_theme"], item["source_item_id"])):
        best_group = None
        best_score = 0
        candidate_tokens = token_set(candidate["theme_name"], candidate["commentary"], candidate["raw_theme"], candidate["raw_category"])
        for group in groups:
            score = 0
            group_tokens = token_set(group["theme_name"], group["theme_category"], group["current_emphasis"])
            if group["normalized_theme"] == candidate["normalized_theme"]:
                score += 5
            elif str(group["theme_name"]).strip().lower() == str(candidate["theme_name"]).strip().lower():
                score += 5
            same_category = group["theme_category"] == candidate["theme_category"]
            shared = candidate_tokens & group_tokens
            if same_category and len(shared) >= 4:
                score += 5
            elif same_category and len(shared) >= 3:
                score += 3
            if group.get("related_commitment_ids") and candidate.get("source_item_id") in group.get("related_commitment_ids", []):
                score += 1
            if score > best_score:
                best_score = score
                best_group = group
        if best_group is not None and best_score >= 4:
            best_group["source_references"].append(candidate["source_reference"])
            best_group["source_items"].append(candidate)
            best_group["related_commitment_ids"] = sorted(set(best_group.get("related_commitment_ids") or []) | set(candidate.get("related_commitment_ids") or []))
            best_group["related_project_ids"] = sorted(set(best_group.get("related_project_ids") or []) | set(candidate.get("related_project_ids") or []))
            best_group["related_capacity_ids"] = sorted(set(best_group.get("related_capacity_ids") or []) | set(candidate.get("related_capacity_ids") or []))
            best_group["related_risk_ids"] = sorted(set(best_group.get("related_risk_ids") or []) | set(candidate.get("related_risk_ids") or []))
            best_group["related_financial_metrics"] = sorted(set(best_group.get("related_financial_metrics") or []) | set(candidate.get("related_financial_metrics") or []))
            if len(candidate["theme_name"].split()) >= len(str(best_group.get("theme_name") or "").split()):
                best_group["theme_name"] = candidate["theme_name"]
            if len(candidate["commentary"].split()) >= len(str(best_group.get("current_emphasis") or "").split()):
                best_group["current_emphasis"] = candidate["commentary"]
            best_group["latest_period"] = max(best_group["latest_period"], candidate["source_year"], key=lambda value: parse_financial_year(value) if str(value).lower().startswith("fy") else -1)
            merged += 1
        else:
            groups.append(
                {
                    "theme_name": candidate["theme_name"],
                    "normalized_theme": candidate["normalized_theme"],
                    "theme_category": candidate["theme_category"],
                    "current_emphasis": candidate["commentary"],
                    "current_position": "unable_to_verify",
                    "first_observed_period": candidate["source_year"],
                    "latest_period": candidate["source_year"],
                    "related_commitment_ids": list(candidate.get("related_commitment_ids") or []),
                    "related_project_ids": list(candidate.get("related_project_ids") or []),
                    "related_capacity_ids": list(candidate.get("related_capacity_ids") or []),
                    "related_risk_ids": list(candidate.get("related_risk_ids") or []),
                    "related_financial_metrics": list(candidate.get("related_financial_metrics") or []),
                    "source_references": [candidate["source_reference"]],
                    "source_items": [candidate],
                }
            )
    return groups, merged


def _load_related_financial_metrics(financial_artifacts: Dict[str, Any]) -> Dict[str, List[str]]:
    summary = financial_artifacts.get("summary") or {}
    metrics = {
        "growth": [],
        "margins": [],
        "working_capital": [],
        "cash_flow": [],
        "capital_allocation": [],
    }
    summary_map = summary.get("summary") if isinstance(summary, dict) else {}
    if isinstance(summary_map, dict):
        if summary_map.get("scale_pattern"):
            metrics["growth"].extend(["revenue", "pat"])
        if summary_map.get("profitability_pattern"):
            metrics["margins"].extend(["opm", "ebitda_margin", "npm"])
        if summary_map.get("cash_conversion_pattern"):
            metrics["cash_flow"].extend(["cfo", "fcf"])
        if summary_map.get("working_capital_pattern"):
            metrics["working_capital"].extend(["receivable_days", "inventory_days", "payable_days", "cash_conversion_cycle"])
        if summary_map.get("capital_allocation_pattern"):
            metrics["capital_allocation"].extend(["capex", "dividend", "debt", "share_issue"])
    driver = financial_artifacts.get("driver_attribution") or {}
    if isinstance(driver, dict):
        for attribution in driver.get("attributions") or []:
            metric = str(attribution.get("metric") or "").strip()
            if metric:
                metrics["growth"].append(metric)
    capital_timeline = financial_artifacts.get("capital_timeline") or {}
    if isinstance(capital_timeline, dict):
        for entry in capital_timeline.get("timeline") or []:
            for key in ("dividend_actions", "capex", "fcf", "share_issue_actions"):
                if entry.get(key):
                    metrics["capital_allocation"].append(key)
    for key in metrics:
        metrics[key] = sorted({item for item in metrics[key] if item})
    return metrics


def _link_related_entities(theme: Dict[str, Any], commitments: Sequence[Dict[str, Any]], projects: Sequence[Dict[str, Any]], capacity_items: Sequence[Dict[str, Any]], risks: Sequence[Dict[str, Any]], financial_metrics: Dict[str, List[str]]) -> None:
    theme_text = " ".join(
        [
            theme.get("theme_name") or "",
            theme.get("current_emphasis") or "",
            theme.get("theme_category") or "",
        ]
    ).lower()
    theme_tokens = token_set(theme_text)

    def _score_match(entity_text: str, *, min_shared: int = 2) -> bool:
        entity_tokens = token_set(entity_text)
        shared = theme_tokens & entity_tokens
        return len(shared) >= min_shared or any(token in entity_text.lower() for token in theme_tokens if len(token) >= 5)

    for commitment in commitments:
        text = " ".join(
            [
                commitment.get("topic") or "",
                commitment.get("normalized_commitment") or "",
                commitment.get("delivery_assessment") or "",
                commitment.get("investor_implication") or "",
                commitment.get("category") or "",
            ]
        )
        if _score_match(text, min_shared=2):
            theme.setdefault("related_commitment_ids", [])
            if commitment.get("id"):
                theme["related_commitment_ids"] = sorted(set(theme["related_commitment_ids"]) | {str(commitment["id"])})

    for project in projects:
        text = " ".join(
            [
                project.get("project_name") or "",
                project.get("normalized_name") or "",
                project.get("objective") or "",
                project.get("business_rationale") or "",
                project.get("project_type") or "",
            ]
        )
        if _score_match(text, min_shared=2):
            theme.setdefault("related_project_ids", [])
            if project.get("project_id"):
                theme["related_project_ids"] = sorted(set(theme["related_project_ids"]) | {str(project["project_id"])})

    for capacity in capacity_items:
        text = " ".join(
            [
                capacity.get("capacity_name") or "",
                capacity.get("normalized_name") or "",
                capacity.get("purpose") or "",
                capacity.get("economic_relevance") or "",
                capacity.get("current_status") or "",
            ]
        )
        if _score_match(text, min_shared=2):
            theme.setdefault("related_capacity_ids", [])
            cid = capacity.get("capacity_id")
            if cid:
                theme["related_capacity_ids"] = sorted(set(theme["related_capacity_ids"]) | {str(cid)})

    for risk in risks:
        text = " ".join(
            [
                risk.get("risk_name") or "",
                risk.get("normalized_name") or "",
                risk.get("risk_mechanism") or "",
                risk.get("current_status") or "",
                risk.get("risk_category") or "",
            ]
        )
        if _score_match(text, min_shared=2):
            theme.setdefault("related_risk_ids", [])
            rid = risk.get("risk_id")
            if rid:
                theme["related_risk_ids"] = sorted(set(theme["related_risk_ids"]) | {str(rid)})

    if theme.get("theme_category") in {"margins", "cash_flow", "working_capital", "capital_allocation", "growth"}:
        related_metrics = financial_metrics.get(theme.get("theme_category") or "", [])
        if related_metrics:
            theme["related_financial_metrics"] = sorted(set(theme.get("related_financial_metrics") or []) | set(related_metrics))


def _build_theme_record(theme_id: str, group: Dict[str, Any], events: Sequence[Dict[str, Any]], timeline: Dict[str, Any], current_position: str, consistency: Dict[str, Any], specificity: Dict[str, Any], evidence_alignment: Dict[str, Any], investor_implication: Dict[str, Any]) -> Dict[str, Any]:
    confidence = timeline.get("confidence") or build_confidence("medium", basis=["management commentary progression"], limitations=[])
    current_emphasis = compact_text(group.get("current_emphasis") or group.get("theme_name"), max_words=24)
    source_item = (group.get("source_items") or [{}])[0] or {}
    semantic_validation = source_item.get("semantic_validation") if isinstance(source_item.get("semantic_validation"), dict) else {}
    semantic_quality = (
        (events[0].get("semantic_quality") if events else None)
        or source_item.get("semantic_quality")
        or build_semantic_quality(
            classification="management_commentary",
            relevance=source_item.get("semantic_relevance") or {},
            period=source_item.get("period_resolution") or {},
            materiality=source_item.get("progression_materiality") or {},
            eligibility="eligible" if not semantic_validation.get("errors") else "quarantined",
            evidence_confidence=(source_item.get("confidence") or {}).get("level") if isinstance(source_item.get("confidence"), dict) else "medium",
        )
    )
    return {
        "theme_id": theme_id,
        "theme_name": group.get("theme_name"),
        "normalized_theme": group.get("normalized_theme"),
        "theme_category": group.get("theme_category"),
        "first_observed_period": group.get("first_observed_period"),
        "latest_period": timeline.get("latest_period") or group.get("latest_period"),
        "current_emphasis": current_emphasis,
        "current_position": current_position,
        "progression_summary": timeline.get("investor_implication") or investor_implication,
        "what_changed": investor_implication.get("what_changed"),
        "why_it_changed": investor_implication.get("why_it_changed"),
        "conviction_impact": investor_implication.get("conviction_impact"),
        "related_commitment_ids": list(group.get("related_commitment_ids") or []),
        "related_project_ids": list(group.get("related_project_ids") or []),
        "related_capacity_ids": list(group.get("related_capacity_ids") or []),
        "related_risk_ids": list(group.get("related_risk_ids") or []),
        "related_financial_metrics": list(group.get("related_financial_metrics") or []),
        "commentary_events": [
            {
                "event_id": event.get("event_id"),
                "period": event.get("period"),
                "event_type": event.get("event_type"),
                "title": event.get("title"),
                "description": event.get("description"),
                "sentiment": (event.get("metadata") or {}).get("sentiment"),
                "status": (event.get("metadata") or {}).get("status"),
                "derived_position": (event.get("metadata") or {}).get("derived_position"),
                "specificity_level": (event.get("metadata") or {}).get("specificity_level"),
                "source_references": event.get("source_references") or [],
            }
            for event in events
        ],
        "consistency_assessment": consistency,
        "specificity_assessment": specificity,
        "evidence_alignment": evidence_alignment,
        "investor_implication": investor_implication.get("what_changed") or current_emphasis,
        "confidence": confidence,
        "semantic_quality": semantic_quality,
        "evidence_status": "supported" if len(events) > 1 or len(group.get("source_references") or []) > 1 else "partial",
        "source_references": list(group.get("source_references") or []),
        "unresolved_questions": sorted(set(consistency.get("limitations") or []) | set(specificity.get("limitations") or []) | set(evidence_alignment.get("limitations") or [])),
    }


def _derive_current_position(events: Sequence[Dict[str, Any]], timeline: Dict[str, Any]) -> str:
    if not events:
        return "unable_to_verify"
    if len(events) == 1:
        return "observation"
    return str(timeline.get("current_state") or ((events[-1].get("metadata") or {}).get("derived_position") or "unable_to_verify"))


def _assess_evidence_alignment(theme: Dict[str, Any]) -> Dict[str, Any]:
    basis: List[str] = []
    limitations: List[str] = []
    related_count = sum(bool(theme.get(key)) for key in ("related_commitment_ids", "related_project_ids", "related_capacity_ids", "related_risk_ids", "related_financial_metrics"))
    if related_count >= 3:
        status = "aligned"
        basis.append("multiple downstream company-memory signals support the theme")
    elif related_count >= 1:
        status = "partially_aligned"
        basis.append("at least one downstream company-memory signal supports the theme")
    else:
        status = "commentary_only"
        basis.append("theme is supported by commentary evidence only")
        limitations.append("no direct downstream linkage was found")
    return {"alignment_status": status, "basis": basis, "limitations": limitations}


def _current_position_from_assessments(consistency: Dict[str, Any], specificity: Dict[str, Any], evidence_alignment: Dict[str, Any], timeline: Dict[str, Any], events: Sequence[Dict[str, Any]]) -> str:
    if not events:
        return "unable_to_verify"
    if len(events) == 1:
        return "observation"
    state = str(timeline.get("current_state") or "unable_to_verify")
    if state in {"contradicted", "softened", "dropped_without_follow_up", "revised", "strengthened", "increasing_priority", "reduced_priority", "newly_introduced", "stable_priority", "unresolved"}:
        return state
    if evidence_alignment.get("alignment_status") == "aligned" and specificity.get("level") == "high" and consistency.get("consistency_status") == "consistent":
        return "stable_priority"
    if specificity.get("level") == "high" and len(events) == 1:
        return "newly_introduced"
    if specificity.get("level") == "low":
        return "unresolved"
    return "stable_priority"


@dataclass
class ManagementCommentaryBuilder:
    company: str
    companies_root: Path | str = Path("companies")
    output_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.companies_root = Path(self.companies_root)
        self.company_root = self.companies_root / self.company
        self.output_dir = get_commentary_dir(self.company)

    def _load_financial_metrics(self) -> Dict[str, List[str]]:
        return _load_related_financial_metrics(_load_financial_artifacts(self.company_root))

    def _extract_candidates(self, year_record: Dict[str, Any]) -> List[Dict[str, Any]]:
        return _extract_candidate_items(year_record)

    def _build_records(self, groups: Sequence[Dict[str, Any]], commitments: Sequence[Dict[str, Any]], projects: Sequence[Dict[str, Any]], capacity_items: Sequence[Dict[str, Any]], risks: Sequence[Dict[str, Any]], financial_metrics: Dict[str, List[str]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        themes: List[Dict[str, Any]] = []
        timelines: List[Dict[str, Any]] = []
        assessments: List[Dict[str, Any]] = []

        for index, group in enumerate(groups, start=1):
            theme_id = f"CM-{index:04d}"
            group["theme_id"] = theme_id
            for source_item in group.get("source_items") or []:
                source_item["theme_id"] = theme_id

            _link_related_entities(group, commitments, projects, capacity_items, risks, financial_metrics)
            consistency = assess_consistency(group.get("source_items") or [])
            if len(group.get("source_items") or []) > 1:
                specificity_level = assess_specificity(group["source_items"][-1], group.get("current_emphasis") or "", repeated_years=len({item.get("source_year") for item in group.get("source_items") or []}), related_links=sum(bool(group.get(key)) for key in ("related_commitment_ids", "related_project_ids", "related_capacity_ids", "related_risk_ids")))
            else:
                specificity_level = (group.get("source_items") or [{}])[0].get("specificity") or {"level": "low", "basis": [], "limitations": []}
            timeline_events = []
            last_signature = None
            repeated_years = len({item.get("source_year") for item in group.get("source_items") or [] if item.get("source_year")})
            for event_index, candidate in enumerate(sorted(group.get("source_items") or [], key=lambda item: (parse_financial_year(item["source_year"]), item["theme_name"], item["source_item_id"] or ""))):
                event = build_commentary_event(candidate, event_index + 1, repeated_years=repeated_years, consistency_status=consistency.get("consistency_status") or "unclear")
                signature = (
                    str(event.get("period") or ""),
                    str(event.get("event_type") or ""),
                    str(event.get("title") or ""),
                    str(event.get("description") or ""),
                )
                if signature == last_signature:
                    continue
                timeline_events.append(event)
                last_signature = signature
            timeline = build_timeline(group, timeline_events, unresolved_questions=[])
            current_position = _current_position_from_assessments(consistency, specificity_level, _assess_evidence_alignment(group), timeline, timeline_events)
            timeline["current_state"] = current_position
            timeline["investor_implication"] = ManagementCommentaryProgressionAdapter().build_investor_implication(
                {
                    "subject_id": theme_id,
                    "stream_type": "management_commentary",
                    "events": timeline_events,
                    "turning_points": timeline.get("turning_points") or [],
                    "current_state": current_position,
                }
            )
            theme_record = _build_theme_record(
                theme_id,
                group,
                timeline_events,
                timeline,
                current_position,
                consistency,
                specificity_level,
                _assess_evidence_alignment(group),
                timeline.get("investor_implication") or {},
            )
            themes.append({k: v for k, v in theme_record.items()})
            timelines.append(
                {
                    **timeline,
                    "theme_id": theme_id,
                    "theme_name": group.get("theme_name"),
                    "normalized_theme": group.get("normalized_theme"),
                    "theme_category": group.get("theme_category"),
                    "current_position": current_position,
                    "semantic_quality": theme_record.get("semantic_quality") or {},
                    "source_references": list(group.get("source_references") or []),
                }
            )
            assessments.append(
                {
                    "theme_id": theme_id,
                    "theme_name": group.get("theme_name"),
                    "normalized_theme": group.get("normalized_theme"),
                    "theme_category": group.get("theme_category"),
                    "current_position": current_position,
                    "current_emphasis": group.get("current_emphasis"),
                    "first_observed_period": group.get("first_observed_period"),
                    "latest_period": group.get("latest_period"),
                    "what_changed": timeline.get("investor_implication", {}).get("what_changed"),
                    "why_it_changed": timeline.get("investor_implication", {}).get("why_it_changed"),
                    "conviction_impact": timeline.get("investor_implication", {}).get("conviction_impact"),
                    "consistency_assessment": consistency,
                    "specificity_assessment": specificity_level,
                    "evidence_alignment": _assess_evidence_alignment(group),
                    "investor_implication": timeline.get("investor_implication", {}).get("what_changed"),
                    "confidence": theme_record.get("confidence") or build_confidence("medium", basis=["management commentary progression"], limitations=[]),
                    "semantic_quality": theme_record.get("semantic_quality") or {},
                    "evidence_status": theme_record.get("evidence_status"),
                    "source_references": list(group.get("source_references") or []),
                    "unresolved_questions": list(theme_record.get("unresolved_questions") or []),
                }
            )
            if theme_record.get("theme_category") in {"margins", "cash_flow", "working_capital", "capital_allocation", "growth"}:
                theme_record["related_financial_metrics"] = sorted(set(theme_record.get("related_financial_metrics") or []) | set(financial_metrics.get(theme_record["theme_category"]) or []))
                assessments[-1]["related_financial_metrics"] = list(theme_record["related_financial_metrics"])
        return themes, timelines, assessments

    def build(self) -> Dict[str, Path]:
        year_records = [_load_year_record(year_dir) for year_dir in _discover_years(self.company_root)]
        candidates: List[Dict[str, Any]] = []
        for year_record in year_records:
            candidates.extend(self._extract_candidates(year_record))

        groups, merged = _group_candidates(candidates)

        commitments = _load_related_commitments(self.company_root)
        projects = _load_related_projects(self.company_root)
        capacity_items = _load_related_capacity(self.company_root)
        risks = _load_related_risks(self.company_root)
        financial_metrics = self._load_financial_metrics()

        theme_records, timeline_records, assessment_records = self._build_records(groups, commitments, projects, capacity_items, risks, financial_metrics)

        themes_payload = {
            "schema_version": COMMENTARY_SCHEMA_VERSION,
            "company": self.company,
            "generated_at": _utc_now(),
            "generator_version": COMMENTARY_GENERATOR_VERSION,
            "commentary_count": len(theme_records),
            "theme_category_counts": dict(Counter(str(theme.get("theme_category") or "other") for theme in theme_records)),
            "position_counts": dict(Counter(str(theme.get("current_position") or "unable_to_verify") for theme in theme_records)),
            "commentary_themes": theme_records,
            "themes": theme_records,
        }
        timelines_payload = {
            "schema_version": COMMENTARY_SCHEMA_VERSION,
            "company": self.company,
            "generated_at": _utc_now(),
            "timelines": timeline_records,
        }
        assessments_payload = {
            "schema_version": COMMENTARY_SCHEMA_VERSION,
            "company": self.company,
            "generated_at": _utc_now(),
            "assessments": assessment_records,
        }

        project_ids = {str(project.get("project_id") or "").strip() for project in projects if str(project.get("project_id") or "").strip()}
        commitment_ids = {str(commitment.get("id") or "").strip() for commitment in commitments if str(commitment.get("id") or "").strip()}
        capacity_ids = {str(item.get("capacity_id") or "").strip() for item in capacity_items if str(item.get("capacity_id") or "").strip()}
        risk_ids = {str(item.get("risk_id") or "").strip() for item in risks if str(item.get("risk_id") or "").strip()}
        financial_metric_ids = sorted({metric for metrics in financial_metrics.values() for metric in metrics})

        validation = validate_commentary_payload(
            themes_payload,
            timelines_payload=timelines_payload,
            assessments_payload=assessments_payload,
            commitment_ids=commitment_ids,
            project_ids=project_ids,
            capacity_ids=capacity_ids,
            risk_ids=risk_ids,
            financial_metrics=financial_metric_ids,
        )

        status_counts = Counter(str(theme.get("current_position") or "unable_to_verify") for theme in theme_records)
        theme_category_counts = Counter(str(theme.get("theme_category") or "other") for theme in theme_records)
        unresolved_items = sum(len(theme.get("unresolved_questions") or []) for theme in theme_records)
        validation_status = validation.get("status", "fail")
        limitations: List[str] = []
        if not theme_records:
            limitations.append("No commentary themes were found.")
        if unresolved_items:
            limitations.append("Some commentary themes still have unresolved questions.")
        if validation_status != "pass":
            limitations.append("Validation surfaced issues that should be reviewed.")

        manifest = build_commentary_manifest(
            company_slug=self.company,
            generated_at=_utc_now(),
            upstream_sources_considered=[
                "companies/<company>/<year>/intelligence/company_intelligence.json",
                "companies/<company>/<year>/intelligence/management_summary.json",
                "companies/<company>/company_memory/management_commitments/management_commitments.json",
                "companies/<company>/company_memory/projects/projects_registry.json",
                "companies/<company>/company_memory/capacity/capacity_registry.json",
                "companies/<company>/company_memory/risks/risk_registry.json",
                "companies/<company>/company_memory/financials/financial_memory_summary.json",
                "companies/<company>/company_memory/financials/financial_driver_attribution.json",
                "companies/<company>/company_memory/financials/capital_allocation_financial_timeline.json",
            ],
            upstream_sources_found=[str(path) for path in [
                self.company_root / "company_memory" / "management_commitments" / "management_commitments.json",
                self.company_root / "company_memory" / "projects" / "projects_registry.json",
                self.company_root / "company_memory" / "capacity" / "capacity_registry.json",
                self.company_root / "company_memory" / "risks" / "risk_registry.json",
                self.company_root / "company_memory" / "financials" / "financial_memory_summary.json",
                self.company_root / "company_memory" / "financials" / "financial_driver_attribution.json",
                self.company_root / "company_memory" / "financials" / "capital_allocation_financial_timeline.json",
            ] if path.exists()],
            upstream_sources_missing=[str(path) for path in [
                self.company_root / "company_memory" / "management_commitments" / "management_commitments.json",
                self.company_root / "company_memory" / "projects" / "projects_registry.json",
                self.company_root / "company_memory" / "capacity" / "capacity_registry.json",
                self.company_root / "company_memory" / "risks" / "risk_registry.json",
                self.company_root / "company_memory" / "financials" / "financial_memory_summary.json",
                self.company_root / "company_memory" / "financials" / "financial_driver_attribution.json",
                self.company_root / "company_memory" / "financials" / "capital_allocation_financial_timeline.json",
            ] if not path.exists()],
            theme_count=len(theme_records),
            timeline_count=len(timeline_records),
            assessment_count=len(assessment_records),
            validation_status=validation_status,
            limitations=limitations,
            position_counts=dict(status_counts),
            theme_category_counts=dict(theme_category_counts),
        )

        files = {
            "commentary_themes.json": themes_payload,
            "commentary_timelines.json": timelines_payload,
            "commentary_assessments.json": assessments_payload,
            "commentary_validation.json": {
                "schema_version": COMMENTARY_SCHEMA_VERSION,
                "company": self.company,
                "generated_at": _utc_now(),
                **validation,
            },
            "commentary_manifest.json": manifest,
        }

        written: Dict[str, Path] = {}
        for filename, payload in files.items():
            written[filename] = write_json_file(self.output_dir / filename, payload)
        return written


def build_management_commentary(company: str, companies_root: Path | str = Path("companies")) -> Dict[str, Path]:
    return ManagementCommentaryBuilder(company=company, companies_root=companies_root).build()
