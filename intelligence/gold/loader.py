"""
Compact Gold context loader — shared across Ask, Buffett, and Committee.

Loads all five Gold intelligence layers, extracts the highest-value 3-5 items
per layer, translates internal vocabulary to investor language, checks cross-Gold
consistency, and returns a single lean dict.

Rule: Gold is preferred over re-inference for questions it already answers,
but it does not override contradictory canonical evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Vocabulary translation ─────────────────────────────────────────────────────

_RETURN_STATUS_NATURAL: Dict[str, str] = {
    "PROVEN_POSITIVE": "return confirmed",
    "EARLY_POSITIVE_SIGNAL": "early return signals visible",
    "UNPROVEN": "return unproven",
    "MIXED": "mixed return signals",
    "WEAK": "weak returns",
    "DESTRUCTIVE": "value-destructive outcome",
    "NOT_APPLICABLE": "",  # dividends / buybacks — do not show in investor prose
}

_GUIDANCE_WEIGHT_NATURAL: Dict[str, str] = {
    "HIGH_WEIGHT": "management guidance carries strong weight",
    "MODERATE_WEIGHT": "management guidance deserves moderate weight",
    "LOW_WEIGHT": "management guidance carries limited weight",
    "VERY_LOW_WEIGHT": "management guidance carries very limited weight",
}

_RISK_STATE_NATURAL: Dict[str, str] = {
    "WORSENING": "worsening",
    "RECURRING": "recurring",
    "NEW": "newly emerged",
    "STABLE": "stable",
    "IMPROVING": "improving",
    "MITIGATION_STARTED": "mitigation active",
    "MITIGATED": "mitigation completed",
    "RESOLVED": "resolved",
    "REAPPEARED": "reappeared",
    "NOT_RECONFIRMED": "not recently reconfirmed",
}

_STRATEGY_STATUS_NATURAL: Dict[str, str] = {
    "CURRENT_PRIORITY": "active priority",
    "NOT_RECONFIRMED": "not recently reconfirmed",
    "DEPRIORITIZED": "deprioritized",
}


def _translate_return_status(status: str) -> str:
    return _RETURN_STATUS_NATURAL.get(status, status.lower().replace("_", " "))


def _translate_guidance_weight(weight: str) -> str:
    return _GUIDANCE_WEIGHT_NATURAL.get(weight, weight.lower().replace("_", " "))


def _translate_risk_state(state: str) -> str:
    return _RISK_STATE_NATURAL.get(state, state.lower().replace("_", " "))


def _translate_strategy_status(status: str) -> str:
    return _STRATEGY_STATUS_NATURAL.get(status, status.lower().replace("_", " "))


# ── File loading ───────────────────────────────────────────────────────────────

_GOLD_FILES: Dict[str, str] = {
    "promise_tracker": "company_memory/gold/management_promise_tracker.json",
    "capital_allocation": "company_memory/gold/capital_allocation_outcome_tracker.json",
    "strategy_evolution": "company_memory/gold/strategy_evolution_timeline.json",
    "risk_evolution": "company_memory/gold/risk_evolution_timeline.json",
    "credibility": "company_memory/gold/management_credibility_synthesis.json",
}


def _load_gold_artifact(company_root: Path, key: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return (payload, generated_at) or (None, None) if missing."""
    relative = _GOLD_FILES.get(key, "")
    if not relative:
        return None, None
    path = company_root / relative
    if not path.exists():
        return None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None, None
        return payload, str(payload.get("generated_at") or "")
    except (OSError, json.JSONDecodeError):
        return None, None


def _tr(text: Any, limit: int = 200) -> str:
    s = str(text or "").strip()
    return (s[:limit - 3].rstrip() + "...") if len(s) > limit else s


# ── Per-layer compaction ───────────────────────────────────────────────────────

def _compact_promise_tracker(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = payload.get("summary") or {}
    promises = payload.get("material_promises") or []
    unresolved = payload.get("unresolved_promises") or []
    patterns = payload.get("credibility_patterns") or []
    follow_up = payload.get("critical_follow_up") or []

    # Top 3 unresolved promises
    top_unresolved = [
        {
            "promise": _tr(p.get("commitment_text") or p.get("theme") or "", 140),
            "status": str(p.get("status") or "").lower(),
            "period": str(p.get("period") or p.get("announcement_period") or ""),
            "evidence_ids": (p.get("evidence_ids") or [])[:2],
        }
        for p in (unresolved or promises)[:3]
        if isinstance(p, dict)
    ]

    # Top 1-2 patterns (text only)
    pattern_texts = [
        _tr(p.get("description") or p.get("pattern_id") or "", 120)
        for p in patterns[:2]
        if isinstance(p, dict)
    ]

    return {
        "tracked_count": int(summary.get("tracked_promises") or len(promises)),
        "unverified_count": int(summary.get("status_breakdown", {}).get("unverified", 0) if isinstance(summary.get("status_breakdown"), dict) else 0),
        "achieved_count": int(summary.get("status_breakdown", {}).get("achieved", 0) if isinstance(summary.get("status_breakdown"), dict) else 0),
        "top_unresolved": top_unresolved,
        "patterns": pattern_texts,
        "critical_follow_up": [_tr(item, 140) for item in (follow_up or [])[:2] if isinstance(item, str)],
        "evidence_ids": _collect_evidence_ids(promises[:3]),
        "source_artifact": "company_memory/gold/management_promise_tracker.json",
    }


def _compact_capital_allocation(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = payload.get("summary") or {}
    allocations = payload.get("material_allocations") or []
    patterns = payload.get("allocation_patterns") or []
    owner_summary = payload.get("owner_capital_summary") or {}
    follow_up = payload.get("critical_follow_up") or []

    top_allocations = []
    for a in allocations[:4]:
        if not isinstance(a, dict):
            continue
        return_status = str(a.get("return_status") or "")
        natural = _translate_return_status(return_status)
        if not natural:  # NOT_APPLICABLE — still show but mark as distribution
            natural = "capital distribution (not an investment return)"
        top_allocations.append({
            "name": _tr(a.get("allocation_name") or a.get("allocation_type") or "", 100),
            "type": str(a.get("allocation_type") or ""),
            "return_status": natural,
            "evidence_level": str(a.get("evidence_level") or ""),
            "investor_interpretation": _tr(a.get("investor_interpretation") or "", 150),
            "evidence_ids": (a.get("evidence_ids") or [])[:2],
        })

    pattern_texts = [
        _tr(p.get("description") or p.get("pattern_id") or "", 120)
        for p in patterns[:2]
        if isinstance(p, dict)
    ]

    return {
        "tracked_count": int(summary.get("tracked_allocations") or len(allocations)),
        "return_status_breakdown": summary.get("return_status_breakdown") or {},
        "major_allocations": top_allocations,
        "owner_capital_note": _tr(owner_summary.get("interpretation") or owner_summary.get("summary") or "", 200),
        "patterns": pattern_texts,
        "critical_follow_up": [_tr(item, 140) for item in (follow_up or [])[:2] if isinstance(item, str)],
        "evidence_ids": _collect_evidence_ids(allocations[:3]),
        "source_artifact": "company_memory/gold/capital_allocation_outcome_tracker.json",
    }


def _compact_strategy_evolution(payload: Dict[str, Any]) -> Dict[str, Any]:
    arc = payload.get("strategy_arc") or {}
    themes = payload.get("strategy_themes") or []
    patterns = payload.get("strategy_patterns") or []

    # Persistent + current-priority themes
    current_themes = [
        {
            "theme": _tr(t.get("theme_name") or "", 80),
            "status": _translate_strategy_status(str(t.get("current_status") or "")),
            "capital_backed": bool(t.get("capital_backed")),
            "periods": (t.get("periods_active") or [])[:3],
        }
        for t in themes[:5]
        if isinstance(t, dict) and t.get("current_status") in ("CURRENT_PRIORITY", "NOT_RECONFIRMED")
    ]

    # Themes with significant events (PIVOTED, REVERSED, ACCELERATED)
    significant_events = []
    for t in themes:
        if not isinstance(t, dict):
            continue
        for e in (t.get("events") or []):
            if not isinstance(e, dict):
                continue
            if e.get("event_type") in ("PIVOTED", "REVERSED", "ACCELERATED", "NARROWED"):
                significant_events.append({
                    "theme": _tr(t.get("theme_name") or "", 60),
                    "event_type": str(e.get("event_type") or "").lower(),
                    "period": str(e.get("period") or ""),
                    "description": _tr(e.get("description") or "", 100),
                })
        if len(significant_events) >= 3:
            break

    pattern_texts = [
        _tr(p.get("description") or p.get("pattern_id") or "", 120)
        for p in patterns[:2]
        if isinstance(p, dict)
    ]

    return {
        "opening_state": _tr(arc.get("opening_state") or "", 200),
        "current_state": _tr(arc.get("current_state") or "", 200),
        "active_themes": current_themes,
        "significant_changes": significant_events,
        "patterns": pattern_texts,
        "source_artifact": "company_memory/gold/strategy_evolution_timeline.json",
    }


def _compact_risk_evolution(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = payload.get("summary") or {}
    risk_themes = payload.get("risk_themes") or []
    worsening = payload.get("worsening_or_recurring") or []
    improving = payload.get("improving_or_resolved") or []
    patterns = payload.get("risk_patterns") or []
    follow_up = payload.get("critical_follow_up") or []

    def _compact_risk(r: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "theme": _tr(r.get("theme") or "", 70),
            "current_state": _translate_risk_state(str(r.get("current_state") or "")),
            "direction": str(r.get("direction") or ""),
            "mitigation_status": str(r.get("mitigation_status") or ""),
            "investor_interpretation": _tr(r.get("investor_interpretation") or "", 150),
            "evidence_ids": (r.get("evidence_ids") or [])[:2],
        }

    # Top current risks (WORSENING + RECURRING first)
    active_risks = sorted(
        [r for r in risk_themes if isinstance(r, dict)],
        key=lambda r: (
            0 if str(r.get("current_state") or "").upper() in ("WORSENING", "RECURRING") else
            1 if str(r.get("current_state") or "").upper() == "MITIGATION_STARTED" else 2
        ),
    )[:5]

    pattern_texts = [
        _tr(p.get("description") or str(p.get("pattern") or ""), 120)
        for p in patterns[:2]
        if isinstance(p, dict)
    ]

    return {
        "current_risk_summary": _tr(summary.get("current_risk_summary") or "", 300),
        "active_material_risks": int(summary.get("active_material_risks") or 0),
        "worsening_count": int(summary.get("worsening_risks") or 0),
        "improving_count": int(summary.get("improving_risks") or 0),
        "top_risks": [_compact_risk(r) for r in active_risks],
        "unresolved_mitigation": [
            _compact_risk(r) for r in risk_themes
            if isinstance(r, dict) and str(r.get("mitigation_status") or "") == "started"
        ][:3],
        "patterns": pattern_texts,
        "critical_follow_up": [_tr(item, 140) for item in (follow_up or [])[:2] if isinstance(item, str)],
        "source_artifact": "company_memory/gold/risk_evolution_timeline.json",
    }


def _compact_credibility(payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = payload.get("summary") or {}
    patterns = payload.get("credibility_patterns") or []
    limits = payload.get("evidence_limitations") or []
    consistency = payload.get("cross_gold_consistency") or {}

    guidance_weight = str(summary.get("guidance_weight") or "")
    guidance_natural = _translate_guidance_weight(guidance_weight)

    key_strengths = []
    key_cautions = []
    for item in (summary.get("key_strengths") or []):
        key_strengths.append(_tr(item, 140))
        if len(key_strengths) >= 2:
            break
    for item in (summary.get("key_cautions") or []):
        key_cautions.append(_tr(item, 140))
        if len(key_cautions) >= 2:
            break

    pattern_texts = [
        _tr(p.get("description") or p.get("pattern_id") or "", 120)
        for p in patterns[:2]
        if isinstance(p, dict)
    ]

    return {
        "guidance_weight": guidance_weight,
        "guidance_weight_natural": guidance_natural,
        "credibility_summary": _tr(summary.get("management_credibility_summary") or "", 250),
        "key_strengths": key_strengths,
        "key_cautions": key_cautions,
        "evidence_confidence": str(summary.get("evidence_confidence") or ""),
        "patterns": pattern_texts,
        "cross_gold_consistency": consistency,
        "evidence_limitations": [
            _tr(item.get("limitation") or "", 120) if isinstance(item, dict) else _tr(item, 120)
            for item in (limits or [])[:3]
            if (isinstance(item, dict) and item.get("limitation")) or (isinstance(item, str) and item)
        ] + ["Same underlying evidence may appear across multiple Gold layers; do not treat as independent confirmation."],
        "source_artifact": "company_memory/gold/management_credibility_synthesis.json",
    }


# ── Cross-Gold consistency check ───────────────────────────────────────────────

def _check_cross_gold_consistency(
    credibility: Optional[Dict[str, Any]],
    capital: Optional[Dict[str, Any]],
    promises: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Detect credibility/capital conflicts.

    Example inconsistency: credibility says "strong follow-through" but
    capital shows only UNPROVEN or DESTRUCTIVE outcomes.
    """
    inconsistencies: List[str] = []

    if credibility and capital:
        weight = credibility.get("guidance_weight", "")
        breakdown = (capital.get("return_status_breakdown") or {}) if isinstance(capital, dict) else {}
        unproven = int(breakdown.get("UNPROVEN", 0) if isinstance(breakdown, dict) else 0)
        destructive = int(breakdown.get("DESTRUCTIVE", 0) if isinstance(breakdown, dict) else 0)
        total = sum(int(v) for v in breakdown.values()) if isinstance(breakdown, dict) else 0

        if weight == "HIGH_WEIGHT" and total > 0 and (unproven + destructive) / max(total, 1) > 0.8:
            inconsistencies.append(
                "Credibility layer assigns HIGH_WEIGHT, but Capital Allocation shows most outcomes unproven or destructive."
            )

    if credibility and promises:
        weight = credibility.get("guidance_weight", "")
        achieved = int(promises.get("achieved_count", 0) if isinstance(promises, dict) else 0)
        tracked = int(promises.get("tracked_count", 1) if isinstance(promises, dict) else 1)
        if weight in ("HIGH_WEIGHT",) and tracked > 0 and achieved / max(tracked, 1) < 0.1:
            inconsistencies.append(
                "Credibility layer assigns HIGH_WEIGHT, but Promise Tracker shows very few achieved commitments."
            )

    return {
        "status": "inconsistent" if inconsistencies else "consistent",
        "inconsistencies": inconsistencies,
        "note": (
            "One or more Gold layers conflict. Downstream should surface the conflict, not resolve it silently."
            if inconsistencies
            else ""
        ),
    }


# ── Evidence collection (shared utility) ──────────────────────────────────────

def _collect_evidence_ids(records: List[Any]) -> List[str]:
    ids: List[str] = []
    for r in records:
        if isinstance(r, dict):
            for eid in (r.get("evidence_ids") or []):
                s = str(eid or "").strip()
                if s and s not in ids:
                    ids.append(s)
    return ids[:10]


# ── Main entry point ───────────────────────────────────────────────────────────

_GOLD_STALENESS_DAYS = 30  # Gold older than this vs. source artifacts is flagged stale

_GOLD_SOURCE_ARTIFACTS = [
    "company_memory/management_progression/management_progression.json",
    "company_memory/multi_year/strategy_timeline.json",
    "company_memory/multi_year/risk_evolution.json",
    "company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json",
    "company_memory/management_commitments/management_commitments.json",
]


def _iso_to_comparable(ts: str) -> str:
    """Return a comparable string from ISO timestamp (strip microseconds/timezone tail)."""
    return str(ts or "")[:19]


def _check_gold_freshness(company_root: Path, gold_generated_at: str) -> str:
    """
    Compare Gold generated_at against primary source artifact timestamps.
    Returns "fresh" | "stale" | "unknown" (if no source timestamps found).
    """
    if not gold_generated_at:
        return "unknown"
    gold_ts = _iso_to_comparable(gold_generated_at)
    source_ts_list: List[str] = []
    for rel in _GOLD_SOURCE_ARTIFACTS:
        p = company_root / rel
        if not p.exists():
            continue
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
            src_ts = _iso_to_comparable(str(payload.get("generated_at") or ""))
            if src_ts:
                source_ts_list.append(src_ts)
        except (OSError, json.JSONDecodeError):
            continue
    if not source_ts_list:
        return "unknown"
    latest_source = max(source_ts_list)
    # Stale: source is significantly newer than Gold
    try:
        from datetime import datetime
        g_dt = datetime.fromisoformat(gold_ts)
        s_dt = datetime.fromisoformat(latest_source)
        delta_days = (s_dt - g_dt).days
        return "stale" if delta_days > _GOLD_STALENESS_DAYS else "fresh"
    except (ValueError, TypeError):
        return "unknown"


def load_gold_context(
    company_slug: str,
    companies_root: Path = Path("companies"),
) -> Dict[str, Any]:
    """
    Load and compact all five Gold intelligence layers for one company.

    Always succeeds — returns partial context if some layers are absent.
    Each layer has a `source_artifact` field for provenance.

    Freshness: `gold_freshness_status` = "fresh" | "stale" | "unknown".
    Stale Gold is still returned — caller decides whether to use it — but the
    stale flag is surfaced so downstream can warn rather than silently trust.
    """
    company_root = companies_root / company_slug

    layer_payloads: Dict[str, Optional[Dict[str, Any]]] = {}
    generated_ats: List[str] = []

    for key in _GOLD_FILES:
        payload, gen_at = _load_gold_artifact(company_root, key)
        layer_payloads[key] = payload
        if gen_at:
            generated_ats.append(gen_at)

    available = [k for k, v in layer_payloads.items() if v is not None]
    missing = [k for k, v in layer_payloads.items() if v is None]

    promise_compact = (
        _compact_promise_tracker(layer_payloads["promise_tracker"])
        if layer_payloads.get("promise_tracker")
        else None
    )
    capital_compact = (
        _compact_capital_allocation(layer_payloads["capital_allocation"])
        if layer_payloads.get("capital_allocation")
        else None
    )
    strategy_compact = (
        _compact_strategy_evolution(layer_payloads["strategy_evolution"])
        if layer_payloads.get("strategy_evolution")
        else None
    )
    risk_compact = (
        _compact_risk_evolution(layer_payloads["risk_evolution"])
        if layer_payloads.get("risk_evolution")
        else None
    )
    credibility_compact = (
        _compact_credibility(layer_payloads["credibility"])
        if layer_payloads.get("credibility")
        else None
    )

    consistency = _check_cross_gold_consistency(
        credibility_compact,
        capital_compact,
        promise_compact,
    )

    gold_generated_at = max(generated_ats) if generated_ats else ""
    freshness_status = _check_gold_freshness(company_root, gold_generated_at)

    return {
        "company_slug": company_slug,
        "gold_generated_at": gold_generated_at,
        "gold_layers_available": available,
        "gold_layers_missing": missing,
        "gold_freshness": "partial" if missing else "full",
        "gold_freshness_status": freshness_status,
        "management_promises": promise_compact,
        "capital_allocation": capital_compact,
        "strategy_evolution": strategy_compact,
        "risk_evolution": risk_compact,
        "management_credibility": credibility_compact,
        "cross_gold_consistency": consistency,
    }
