from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


DOCTRINE_MEMORY_PRIORITIES: Dict[str, List[str]] = {
    "graham": [
        "financial memory",
        "company model",
        "management progression",
        "risk evolution",
        "capital allocation outcomes",
        "management commitments",
        "capacity evolution",
        "projects",
        "management quality",
        "management commentary",
    ],
    "buffett": [
        "gold intelligence",        # Gold first for Buffett: management + capital + strategy
        "company model",
        "management progression",
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
        "company model",
        "management progression",
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
        "management progression",
        "management quality",
        "management commitments",
        "company model",   # Phase 13: Munger needs business model to assess fragility
        "capital allocation outcomes",
        "risk evolution",
        "management commentary",
        "capacity evolution",
        "projects",
        "financial memory",
    ],
    "lynch": [
        "company model",
        "management progression",
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
    "gold intelligence": [
        Path("company_memory/gold/management_credibility_synthesis.json"),
        Path("company_memory/gold/capital_allocation_outcome_tracker.json"),
        Path("company_memory/gold/management_promise_tracker.json"),
        Path("company_memory/gold/strategy_evolution_timeline.json"),
        Path("company_memory/gold/risk_evolution_timeline.json"),
    ],
    "company model": [
        Path("company_memory/company_model/company_model.json"),
    ],
    "management progression": [
        Path("company_memory/management_progression/management_progression.json"),
    ],
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
        Path("company_memory/capital_allocation_outcomes/capital_allocation_longitudinal_profile.json"),
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


def _panel_citable_evidence_ids(value: Any, *, limit: int = 5) -> List[str]:
    """Return only evidence identifiers that panel validators can cite.

    Management Progression also carries internal item IDs such as PJ-0003 or
    commitment_1. Those are useful provenance inside the progression module,
    but they are not valid analyst evidence IDs and must not be exposed as
    citation candidates.
    """

    ids = _collect_evidence_ids(value)
    citable = [
        item
        for item in ids
        if item.startswith("ev_") or item.startswith("evidence_")
    ]
    return citable[:limit]


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


def _company_model_text_items(value: Any, *, limit: int = 3, char_limit: int = 140) -> List[str]:
    if not isinstance(value, list):
        return []
    items: List[str] = []
    for item in value:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = (
                item.get("mechanism")
                or item.get("driver")
                or item.get("question")
                or item.get("why_it_matters")
                or item.get("summary")
                or item.get("description")
            )
        else:
            text = item
        cleaned = _truncate_text(text, char_limit)
        if cleaned and cleaned not in items:
            items.append(cleaned)
        if len(items) >= limit:
            break
    return items


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


def _compact_capital_allocation_outcomes(
    candidates: "List[Tuple[Path, Dict[str, Any]]]",
) -> Dict[str, Any]:
    """Compact capital allocation stream, preferring Phase 3 longitudinal profile."""
    longitudinal: Dict[str, Any] = {}
    raw_outcomes: Dict[str, Any] = {}
    for path, payload in candidates:
        name = path.name
        if "longitudinal_profile" in name:
            longitudinal = payload
        elif "capital_allocation_outcomes" in name and not longitudinal:
            raw_outcomes = payload

    if longitudinal:
        scope = longitudinal.get("profile_scope") or {}
        cov = longitudinal.get("amount_coverage") or {}
        avs = longitudinal.get("allocation_activity_vs_skill") or {}
        oi = longitudinal.get("organic_vs_inorganic") or {}
        obs = longitudinal.get("stewardship_observations") or []
        acq = longitudinal.get("acquisition_profile") or {}
        psc = longitudinal.get("per_share_context") or {}
        om = longitudinal.get("outcome_maturity") or {}
        uq = longitudinal.get("unresolved_questions") or []

        start = str(scope.get("start_period") or "").upper()
        end = str(scope.get("end_period") or "").upper()
        period_range = f"{start}–{end}" if start and end else start or end
        capital_weighted = cov.get("capital_weighted_conclusions_permitted", False)
        coverage_pct = int(cov.get("coverage_ratio", 0) * 100)

        obs_texts = [
            _truncate_text(o.get("detail", ""), 200)
            for o in obs[:3]
            if isinstance(o, dict) and o.get("detail")
        ]
        l2_plus = (
            len(om.get("level_2_execution_verified") or [])
            + len(om.get("level_3_operating_outcome_visible") or [])
            + len(om.get("level_4_financial_outcome_attributable") or [])
            + len(om.get("level_5_per_share_attributable") or [])
        )
        return {
            "generated_at": longitudinal.get("generated_at"),
            "profile_period": period_range,
            "event_count": scope.get("total_events", 0),
            "amount_coverage": f"{coverage_pct}% of events have known amounts. {cov.get('note', '')}",
            "event_mix": {
                "organic_reinvestment": oi.get("organic_event_count", 0),
                "inorganic_m_and_a": oi.get("inorganic_event_count", 0),
                "shareholder_distributions": oi.get("distribution_event_count", 0),
                "balance_sheet": oi.get("balance_sheet_event_count", 0),
            },
            "outcome_maturity": {
                "events_with_verified_execution": l2_plus,
                "events_unverified": len(om.get("level_0_deployment_unverified") or []) + len(om.get("level_1_deployment_verified") or []),
                "financial_attributable": avs.get("financial_attributable_count", 0),
            },
            "allocation_skill": {
                "assessment": avs.get("skill_assessment", "UNABLE_TO_VERIFY"),
                "basis": _truncate_text(avs.get("skill_basis", ""), 200),
                "activity_vs_skill_note": "Allocation activity (what management did) is separate from allocation skill (whether it created value).",
            },
            "acquisition_profile": _truncate_text(acq.get("activity_vs_success_note", ""), 200) if isinstance(acq, dict) else "",
            "per_share_highlights": {
                "share_count_reduction": psc.get("share_count_reduction_documented", False),
                "dividend_distribution": psc.get("dividend_distribution_documented", False),
                "note": psc.get("attribution_note", ""),
            },
            "stewardship_observations": obs_texts,
            "unresolved_diligence": uq[:2],
            "capital_mix_note": "Capital-weighted conclusions permitted." if capital_weighted else cov.get("note", ""),
            "limitations": longitudinal.get("limitations") or [],
        }

    # Fallback: compact Phase 2 raw outcomes
    allocations = (raw_outcomes.get("allocations") or [])[:3]
    return {
        "allocation_count": raw_outcomes.get("allocation_count", len(allocations)),
        "note": "Phase 3 longitudinal profile not yet available.",
        "allocations": [
            {
                "id": a.get("allocation_id"),
                "category": a.get("allocation_category"),
                "amount_crore": a.get("amount"),
                "periods": (a.get("deployment_periods") or [])[:3],
            }
            for a in allocations
        ],
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


_TRAJECTORY_ORDER = ("worsening", "recurring", "improving")


def _compact_risk_evolution(candidates: List[Any], *, limit: int = 6) -> Dict[str, Any]:
    """Group canonical risk assessments by trajectory for analyst lenses.

    Returns a dict with grouped worsening/recurring/improving/other lists
    alongside a flat assessments list for backward compatibility.
    """
    primary_payload = candidates[0][1] if candidates else {}
    all_assessments: List[Dict[str, Any]] = list(primary_payload.get("assessments") or [])
    # Merge additional assessment sources
    for _, payload in candidates[1:]:
        for item in payload.get("assessments") or []:
            if isinstance(item, dict):
                all_assessments.append(item)

    groups: Dict[str, List[Dict[str, Any]]] = {"worsening": [], "recurring": [], "improving": [], "other": []}
    seen_ids: set = set()
    for item in all_assessments:
        if not isinstance(item, dict):
            continue
        rid = item.get("risk_id") or item.get("evo_canonical_id") or item.get("risk_name")
        if rid and rid in seen_ids:
            continue
        if rid:
            seen_ids.add(rid)
        trajectory = item.get("trajectory") or ""
        entry = {
            "id": rid,
            "risk_name": item.get("risk_name") or item.get("risk_id"),
            "current_status": item.get("current_status"),
            "trajectory": trajectory,
            "what_changed": _truncate_text(item.get("what_changed"), 120),
            "why_it_changed": _truncate_text(item.get("why_it_changed"), 120),
            "investor_implication": _truncate_text(item.get("investor_implication"), 120),
            "evo_canonical_id": item.get("evo_canonical_id"),
        }
        bucket = trajectory if trajectory in groups else "other"
        groups[bucket].append(entry)

    flat = []
    for bucket in _TRAJECTORY_ORDER:
        flat.extend(groups[bucket])
    flat.extend(groups["other"])
    flat = flat[:limit]

    return {
        "company": primary_payload.get("company") or primary_payload.get("company_slug"),
        "schema_version": primary_payload.get("schema_version"),
        "generated_at": primary_payload.get("generated_at"),
        "assessment_count": len(all_assessments),
        "worsening_count": len(groups["worsening"]),
        "recurring_count": len(groups["recurring"]),
        "improving_count": len(groups["improving"]),
        "worsening": groups["worsening"][:3],
        "recurring": groups["recurring"][:3],
        "improving": groups["improving"][:3],
        "assessments": flat,
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


_MQ_INTERNAL_ID_KEYS: frozenset = frozenset({"evidence_ids", "evidence_id", "source_item_id", "source_item_ids"})


def _strip_mq_internal_ids(items: List[Any]) -> List[Any]:
    cleaned: List[Any] = []
    for item in items:
        if isinstance(item, dict):
            cleaned.append({k: v for k, v in item.items() if k not in _MQ_INTERNAL_ID_KEYS})
        else:
            cleaned.append(item)
    return cleaned


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
        "what_strengthened_conviction": _top_list(_strip_mq_internal_ids(payload.get("what_strengthened_conviction") or []), limit=2),
        "what_weakened_conviction": _top_list(_strip_mq_internal_ids(payload.get("what_weakened_conviction") or []), limit=2),
        "what_remains_unproven": _top_list(_strip_mq_internal_ids(payload.get("what_remains_unproven") or []), limit=2),
        "major_turning_points": _top_list(_strip_mq_internal_ids(payload.get("major_turning_points") or []), limit=2),
        "evidence_confidence": _deep_trim(payload.get("evidence_confidence") or {}, max_depth=0, max_list_items=2, max_str=60),
    }


def _compact_longitudinal_current_state(lcs_items: List[Any], *, limit: int = 4) -> List[Dict[str, Any]]:
    """Compact longitudinal_current_state items for Panel consumption.

    Keeps only lifecycle-authority fields. No events, no raw text, no source_chunk.
    Confidence level disambiguates CONFIRMED (high) from CLAIMED (low).
    """
    result: List[Dict[str, Any]] = []
    for item in lcs_items:
        if not isinstance(item, dict):
            continue
        credibility = str(item.get("management_credibility_signal") or "").upper()
        current_status = str(item.get("current_status") or "unresolved")
        conf = item.get("confidence") if isinstance(item.get("confidence"), dict) else {}
        result.append({
            "theme": _truncate_text(item.get("theme"), 100),
            "current_status": current_status,
            "management_credibility_signal": credibility,
            "confidence_level": conf.get("level") or "low",
            "source_period": str(item.get("source_period") or "").strip(),
            "linked_company_model_ids": list(item.get("linked_company_model_ids") or [])[:3],
        })
        if len(result) >= limit:
            break
    return result


def _compact_company_model(payload: Dict[str, Any]) -> Dict[str, Any]:
    business_model = payload.get("current_business_model") if isinstance(payload.get("current_business_model"), dict) else {}
    lcs_items = payload.get("longitudinal_current_state") or []
    lcs_compact = _compact_longitudinal_current_state(lcs_items, limit=4) if isinstance(lcs_items, list) else []
    result: Dict[str, Any] = {
        "company_slug": payload.get("company_slug") or payload.get("company"),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "coverage_status": payload.get("coverage_status"),
        "business_model_type": business_model.get("business_model_type"),
        "business_summary": _truncate_text(business_model.get("summary"), 180),
        "what_it_sells": _top_list(business_model.get("what_it_sells") or payload.get("offerings") or [], limit=2),
        "who_pays": _top_list(business_model.get("who_pays") or [], limit=2),
        "how_revenue_happens": _truncate_text(business_model.get("how_revenue_happens"), 140),
        "economic_drivers": _company_model_text_items(payload.get("economic_drivers") or [], limit=1, char_limit=120),
        "evidence_ids": _panel_citable_evidence_ids(payload, limit=3),
    }
    if lcs_compact:
        result["longitudinal_current_state_summary"] = lcs_compact
    return result


def _compact_management_progression(payload: Dict[str, Any], *, limit: int = 5) -> Dict[str, Any]:
    items = payload.get("progression_items") or []
    compacted: List[Dict[str, Any]] = []
    for item in [entry for entry in items if isinstance(entry, dict)][:limit]:
        chain = item.get("synthesis_chain") if isinstance(item.get("synthesis_chain"), dict) else {}
        claim = chain.get("claim") if isinstance(chain.get("claim"), dict) else {}
        action = chain.get("action") if isinstance(chain.get("action"), dict) else {}
        outcome = chain.get("outcome") if isinstance(chain.get("outcome"), dict) else {}
        financial_consequence = (
            chain.get("financial_consequence") if isinstance(chain.get("financial_consequence"), dict) else {}
        )
        implication = chain.get("investor_implication") if isinstance(chain.get("investor_implication"), dict) else {}
        # Phase 13: expose lifecycle authority fields so specialists can calibrate evidence weight
        stream_types = list(item.get("stream_types") or [])
        credibility = str(item.get("management_credibility_signal") or "").upper()
        current_status = str(item.get("current_status") or "").strip()
        compacted.append(
            {
                "theme": _truncate_text(item.get("theme") or item.get("topic"), 140),
                "period": item.get("period") or item.get("latest_period"),
                "stream_types": stream_types,
                "management_credibility_signal": credibility,
                "current_status": current_status,
                "chain_status": str(chain.get("chain_status") or "").strip().upper(),
                "actor": action.get("action_actor") or action.get("actor") or outcome.get("actor") or "unknown",
                "claim_summary": _truncate_text(claim.get("text"), 180),
                "action_summary": _truncate_text(action.get("text"), 180),
                "action_completed": bool(action.get("completed")),
                "outcome_summary": _truncate_text(outcome.get("text"), 180),
                "outcome_direction": outcome.get("direction") or outcome.get("outcome_direction"),
                "financial_link_status": financial_consequence.get("link_status"),
                "investor_implication": _truncate_text(implication.get("conclusion"), 220),
                "confidence": implication.get("confidence") or item.get("confidence"),
                "evidence_ids": _panel_citable_evidence_ids(chain, limit=5),
            }
        )
    return {
        "company_slug": payload.get("company_slug") or payload.get("company"),
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "coverage_status": payload.get("coverage_status"),
        "progression_item_count": len(items) if isinstance(items, list) else 0,
        "synthesis_chains": compacted,
        "chain_rules": [
            "CLAIM_ONLY is statement evidence, not delivery or execution evidence.",
            "ACTION_STARTED shows management/company action began; outcome and financial consequence remain unproven unless separately evidenced.",
            "ACTION_COMPLETED shows completion only; completion alone is not a positive operating or financial outcome.",
            "OUTCOME_POSITIVE/OUTCOME_NEGATIVE require separately evidenced operating or financial result.",
            "FINANCIAL_LINK_UNPROVEN means do not claim realized financial impact.",
        ],
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


_GUIDANCE_WEIGHT_NATURAL: Dict[str, str] = {
    "HIGH_WEIGHT": "management guidance carries strong weight",
    "MODERATE_WEIGHT": "management guidance deserves moderate weight",
    "LOW_WEIGHT": "management guidance carries limited weight",
    "VERY_LOW_WEIGHT": "management guidance carries very limited weight",
}

_RETURN_STATUS_NATURAL: Dict[str, str] = {
    "PROVEN_POSITIVE": "return confirmed",
    "EARLY_POSITIVE_SIGNAL": "early return signals visible",
    "UNPROVEN": "return unproven",
    "MIXED": "mixed return signals",
    "DESTRUCTIVE": "value-destructive outcome",
    "NOT_APPLICABLE": "",
}


def _compact_gold_stream(candidates: List[Tuple[Path, Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Compact all available Gold artifacts into a single panel-ready block.

    Returns investor-language summaries only — no internal Gold vocabulary exposed.
    Called by build_company_memory_context when 'gold intelligence' stream is selected.
    """
    payloads: Dict[str, Dict[str, Any]] = {}
    for path, payload in candidates:
        key = path.stem  # e.g. management_credibility_synthesis
        payloads[key] = payload

    credibility = payloads.get("management_credibility_synthesis", {})
    capital = payloads.get("capital_allocation_outcome_tracker", {})
    promises = payloads.get("management_promise_tracker", {})
    strategy = payloads.get("strategy_evolution_timeline", {})
    risk = payloads.get("risk_evolution_timeline", {})

    cred_summary = credibility.get("summary") or {}
    guidance_weight = str(cred_summary.get("guidance_weight") or "")
    guidance_natural = _GUIDANCE_WEIGHT_NATURAL.get(guidance_weight, guidance_weight)
    cred_text = _truncate_text(cred_summary.get("management_credibility_summary") or "", 220)

    # Capital allocation: top 3 allocations with natural return status
    cap_allocs = (capital.get("material_allocations") or [])[:3]
    cap_items = []
    for a in cap_allocs:
        if not isinstance(a, dict):
            continue
        rs = str(a.get("return_status") or "")
        natural = _RETURN_STATUS_NATURAL.get(rs, rs.lower().replace("_", " "))
        if not natural:
            continue
        cap_items.append(
            f"{_truncate_text(a.get('allocation_name') or a.get('allocation_type') or '', 60)}: {natural}"
        )

    # Promise tracker
    pt_summary = promises.get("summary") or {}
    tracked = int(pt_summary.get("tracked_promises") or 0)
    unverified = int((pt_summary.get("status_breakdown") or {}).get("unverified", 0) if isinstance(pt_summary.get("status_breakdown"), dict) else 0)
    promise_note = (
        f"{tracked} commitments tracked; {unverified} remain unverified."
        if tracked
        else ""
    )

    # Strategy arc
    arc = strategy.get("strategy_arc") or {}
    current_strategy = _truncate_text(arc.get("current_state") or "", 200)

    # Risk summary
    risk_summary_text = _truncate_text((risk.get("summary") or {}).get("current_risk_summary") or "", 200)

    # Evidence IDs from Gold layers
    ev_ids: List[str] = []
    for p in (credibility, capital, promises):
        for eid in (p.get("evidence_ids") or _collect_evidence_ids(p)):
            if isinstance(eid, str) and eid.strip() and eid not in ev_ids:
                ev_ids.append(eid)
    ev_ids = ev_ids[:10]

    block: Dict[str, Any] = {
        "management_credibility": {
            "guidance_weight_natural": guidance_natural,
            "summary": cred_text,
        },
        "capital_allocation_outcomes": {
            "allocations_summary": cap_items,
        },
        "promise_tracker": {
            "note": promise_note,
        },
        "limitations": [
            "Gold intelligence is derived from canonical evidence; verify currency against source artifacts.",
            "Capital allocation return evidence should not be treated as independent confirmation when same evidence appears across multiple Gold layers.",
        ],
    }
    if current_strategy:
        block["strategy_evolution"] = {"current_state": current_strategy}
    if risk_summary_text:
        block["risk_evolution"] = {"current_summary": risk_summary_text}

    block["evidence_ids"] = ev_ids
    return block


def _collect_evidence_ids(payload: Any) -> List[str]:
    """Recursively collect evidence_id strings from a nested dict/list."""
    ids: List[str] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in ("evidence_id", "evidence_ids") and isinstance(v, (str, list)):
                for eid in ([v] if isinstance(v, str) else v):
                    s = str(eid or "").strip()
                    if s and s not in ids:
                        ids.append(s)
            else:
                ids.extend(_collect_evidence_ids(v))
    elif isinstance(payload, list):
        for item in payload:
            ids.extend(_collect_evidence_ids(item))
    return ids[:20]


def _stream_priority(doctrine_id: str) -> List[str]:
    return DOCTRINE_MEMORY_PRIORITIES.get(
        doctrine_id,
        [
            "management quality",
            "management commitments",
            "projects",
            "capacity evolution",
            "risk evolution",
            "management progression",
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
    protected_streams = {"management progression", "capital allocation outcomes", "risk evolution"}
    selected_streams = ordered_streams[:max_streams]
    selected_names = {name for name, _candidates in selected_streams}
    for stream_name, candidates in ordered_streams[max_streams:]:
        if stream_name in protected_streams and stream_name not in selected_names:
            selected_streams.append((stream_name, candidates))
            selected_names.add(stream_name)

    for stream_name, candidates in selected_streams:
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
        if stream_name == "company model":
            block.update(_compact_company_model(primary_payload))
        elif stream_name == "management progression":
            block.update(_compact_management_progression(primary_payload, limit=4))
        elif stream_name == "management commitments":
            merged_commitments = deepcopy(primary_payload)
            for path, payload in candidates[1:]:
                if not merged_commitments.get("timeline") and payload.get("timeline"):
                    merged_commitments["timeline"] = payload.get("timeline")
                if not merged_commitments.get("validation") and payload.get("validation"):
                    merged_commitments["validation"] = payload.get("validation")
            block.update(_compact_commitments(merged_commitments))
        elif stream_name == "capital allocation outcomes":
            block.update(_compact_capital_allocation_outcomes(candidates))
        elif stream_name == "risk evolution":
            block.update(_compact_risk_evolution(candidates, limit=max(max_items_per_stream, 6)))
        elif stream_name in {"projects", "capacity evolution", "management commentary"}:
            merged_assessments = deepcopy(primary_payload)
            for path, payload in candidates[1:]:
                if not merged_assessments.get("timelines") and payload.get("timelines"):
                    merged_assessments["timelines"] = payload.get("timelines")
                if not merged_assessments.get("timeline") and payload.get("timeline"):
                    merged_assessments["timeline"] = payload.get("timeline")
            block.update(_compact_assessments(merged_assessments, limit=max_items_per_stream))
        elif stream_name == "gold intelligence":
            block.update(_compact_gold_stream(candidates))
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
