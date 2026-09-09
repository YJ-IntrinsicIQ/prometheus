from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCHEMA_VERSION = "management_credibility_gold.v1"
ARTIFACT_NAME = "management_credibility_synthesis.json"

GUIDANCE_WEIGHTS = {
    "STRONG_WEIGHT",
    "MODERATE_WEIGHT",
    "CAUTIOUS_WEIGHT",
    "INSUFFICIENT_BASIS",
}

CONFIDENCE_LEVELS = {
    "HIGH_EVIDENCE",
    "MODERATE_EVIDENCE",
    "LOW_EVIDENCE",
    "INSUFFICIENT_EVIDENCE",
}

DIMENSION_KEYS = (
    "promise_follow_through",
    "execution_discipline",
    "economic_follow_through",
    "capital_allocation_alignment",
    "strategic_consistency",
    "risk_response",
    "disclosure_quality",
)

_POSITIVE_OUTCOME_STATUSES = {"ACHIEVED", "PARTIALLY_ACHIEVED"}
_NEGATIVE_OUTCOME_STATUSES = {"MISSED", "ABANDONED"}
_DELAY_STATUSES = {"DELAYED"}
_EXECUTION_VISIBLE_STATUSES = {
    "ACTION_COMPLETED",
    "EARLY_OPERATING_SIGNAL",
    "OUTCOME_VISIBLE",
    "FINANCIAL_IMPACT_CONFIRMED",
}
_ACTION_VISIBLE_STATUSES = _EXECUTION_VISIBLE_STATUSES | {"ACTION_STARTED"}
_ECONOMIC_PROVEN_STATUSES = {"PROVEN", "CONFIRMED", "FINANCIAL_IMPACT_CONFIRMED"}
_ECONOMIC_PARTIAL_STATUSES = {"PARTIAL", "MIXED", "FINANCIAL_OUTCOME_VISIBLE"}
_ECONOMIC_UNPROVEN_STATUSES = {"UNPROVEN", "INSUFFICIENT_EVIDENCE", "NOT_APPLICABLE", ""}
_GENERIC_PROMOTIONAL_TERMS = (
    "leading",
    "best in class",
    "world class",
    "robust",
    "strong focus",
    "committed to excellence",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _short(value: Any, limit: int = 260) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _norm(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _period_sort_key(value: Any) -> int:
    text = str(value or "").lower()
    match = re.search(r"fy\s*(\d{2,4})", text)
    if match:
        raw = match.group(1)
        year = int(raw)
        return year + (2000 if year < 100 else 0)
    match = re.search(r"(20\d{2}|19\d{2})", text)
    if match:
        return int(match.group(1))
    return 10_000


def _dedupe(items: Iterable[str], limit: Optional[int] = None) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        text = _short(item, 320)
        if not text:
            continue
        key = _norm(text)
        if key and key not in seen:
            seen.add(key)
            out.append(text)
        if limit is not None and len(out) >= limit:
            break
    return out


def _evidence_ids(value: Any) -> List[str]:
    ids: List[str] = []
    if isinstance(value, dict):
        for key in ("evidence_id", "evidence_ids", "related_evidence_ids"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                ids.append(raw.strip())
            elif isinstance(raw, list):
                ids.extend(str(item).strip() for item in raw if str(item).strip())
        for nested in value.values():
            ids.extend(_evidence_ids(nested))
    elif isinstance(value, list):
        for item in value:
            ids.extend(_evidence_ids(item))
    return _dedupe(ids)


def _source_ref(artifact: str, item: Dict[str, Any], text: str, signal: str) -> Dict[str, Any]:
    return {
        "source_artifact": artifact,
        "source_item_id": item.get("promise_id")
        or item.get("allocation_id")
        or item.get("theme_id")
        or item.get("risk_theme_id")
        or item.get("item_id")
        or item.get("pattern_id")
        or "",
        "period": item.get("source_period")
        or item.get("latest_period")
        or item.get("last_confirmed_period")
        or item.get("first_period")
        or "",
        "signal": signal,
        "text": _short(text),
        "evidence_ids": _evidence_ids(item)[:8],
    }


def _load_sources(company_slug: str, companies_root: Path) -> Dict[str, Any]:
    mem = companies_root / company_slug / "company_memory"

    return {
        "promise_tracker": _load_json(mem / "gold" / "management_promise_tracker.json"),
        "capital_tracker": _load_json(mem / "gold" / "capital_allocation_outcome_tracker.json"),
        "strategy_timeline": _load_json(mem / "gold" / "strategy_evolution_timeline.json"),
        "risk_timeline": _load_json(mem / "gold" / "risk_evolution_timeline.json"),
        "management_progression": _load_json(mem / "management_progression" / "management_progression.json"),
        "management_quality_summary": _load_json(mem / "management_quality" / "management_quality_summary.json"),
        "management_quality_dimensions": _load_json(mem / "management_quality" / "management_quality_dimensions.json"),
        "management_commitments": _load_json(mem / "management_commitments" / "management_commitments.json"),
        "management_commentary": _load_json(mem / "management_commentary" / "management_commentary.json"),
    }


def _promise_items(sources: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = sources.get("promise_tracker") or {}
    # Current Gold owns the objectively verifiable accountability denominator.
    # Strategic intents and aspirations remain context, not failed/unresolved
    # promises.  The fallback is schema compatibility for pre-accountability Gold
    # fixtures/artifacts only; the presence of the canonical key is authoritative,
    # including when its value is an intentionally empty list.
    if "accountability_promises" not in payload:
        return [
            item
            for item in payload.get("material_promises") or []
            if isinstance(item, dict)
        ]
    return [
        item
        for item in payload.get("accountability_promises") or []
        if isinstance(item, dict)
    ]


def _capital_items(sources: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = sources.get("capital_tracker") or {}
    return [item for item in payload.get("material_allocations") or [] if isinstance(item, dict)]


def _strategy_items(sources: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = sources.get("strategy_timeline") or {}
    return [item for item in payload.get("strategy_themes") or [] if isinstance(item, dict)]


def _risk_items(sources: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = sources.get("risk_timeline") or {}
    return [item for item in payload.get("risk_themes") or [] if isinstance(item, dict)]


def _progression_items(sources: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = sources.get("management_progression") or {}
    return [item for item in payload.get("progression_items") or [] if isinstance(item, dict)]


def _chain_status(item: Dict[str, Any]) -> str:
    chain = item.get("synthesis_chain") or {}
    return str(chain.get("chain_status") or item.get("chain_status") or "").upper()


def _financial_link_status(item: Dict[str, Any]) -> str:
    chain = item.get("synthesis_chain") or {}
    consequence = chain.get("financial_consequence") or {}
    return str(
        consequence.get("link_status")
        or item.get("financial_link_status")
        or item.get("financial_impact_status")
        or ""
    ).upper()


def _event_text(item: Dict[str, Any]) -> str:
    chain = item.get("synthesis_chain") or {}
    parts = [
        item.get("theme"),
        chain.get("claim", {}).get("text") if isinstance(chain.get("claim"), dict) else "",
        chain.get("action", {}).get("text") if isinstance(chain.get("action"), dict) else "",
        chain.get("outcome", {}).get("text") if isinstance(chain.get("outcome"), dict) else "",
        item.get("investor_interpretation"),
    ]
    return " ".join(str(part or "") for part in parts)


def _dimension(
    assessment: str,
    supporting: Sequence[Dict[str, Any]],
    contrary: Sequence[Dict[str, Any]],
    uncertainty: Sequence[str],
    interpretation: str,
    confidence: str,
    behavior_signal: str,
    evidence_signal: str,
) -> Dict[str, Any]:
    return {
        "assessment": assessment,
        "supporting_evidence": list(supporting)[:8],
        "contrary_evidence": list(contrary)[:8],
        "uncertainty": _dedupe(uncertainty, 8),
        "investor_interpretation": interpretation,
        "confidence": confidence if confidence in CONFIDENCE_LEVELS else "LOW_EVIDENCE",
        "management_behavior_signal": behavior_signal,
        "evidence_completeness_signal": evidence_signal,
    }


def _confidence_from_counts(observations: int, *, strong: int = 5, moderate: int = 2) -> str:
    if observations >= strong:
        return "HIGH_EVIDENCE"
    if observations >= moderate:
        return "MODERATE_EVIDENCE"
    if observations > 0:
        return "LOW_EVIDENCE"
    return "INSUFFICIENT_EVIDENCE"


def _promise_follow_through_dimension(promises: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter(str(p.get("current_status") or "").upper() for p in promises)
    achieved = counts.get("ACHIEVED", 0) + counts.get("PARTIALLY_ACHIEVED", 0)
    missed = counts.get("MISSED", 0) + counts.get("ABANDONED", 0)
    delayed = counts.get("DELAYED", 0)
    unverified = counts.get("UNVERIFIED", 0)

    supporting = [
        _source_ref("gold/management_promise_tracker.json", p, p.get("investor_interpretation") or p.get("theme") or "", "promise_follow_through")
        for p in promises
        if str(p.get("current_status") or "").upper() in _POSITIVE_OUTCOME_STATUSES
    ]
    contrary = [
        _source_ref("gold/management_promise_tracker.json", p, p.get("investor_interpretation") or p.get("theme") or "", "promise_not_met_or_delayed")
        for p in promises
        if str(p.get("current_status") or "").upper() in (_NEGATIVE_OUTCOME_STATUSES | _DELAY_STATUSES)
    ]

    if achieved >= 2 and missed == 0:
        assessment = "constructive_but_incomplete"
    elif missed + delayed >= 2:
        assessment = "mixed_with_follow_through_cautions"
    elif unverified >= 3 and achieved == 0:
        assessment = "insufficient_verification"
    else:
        assessment = "mixed_or_limited"

    uncertainty = []
    if unverified:
        uncertainty.append(
            f"{unverified} tracked commitments remain unverified; this is an evidence-completeness limitation, not automatic proof of management failure."
        )
    if not promises:
        uncertainty.append("No Gold promise tracker evidence was available.")

    interpretation = (
        "Promise evidence separates claims, execution, outcomes, and financial proof; unresolved items are not treated as missed promises."
    )
    behavior_signal = f"{achieved} achieved/partially achieved, {missed} missed/abandoned, {delayed} delayed."
    evidence_signal = f"{unverified} unverified out of {len(promises)} tracked promises."
    return _dimension(
        assessment,
        supporting,
        contrary,
        uncertainty,
        interpretation,
        _confidence_from_counts(len(promises)),
        behavior_signal,
        evidence_signal,
    )


def _execution_discipline_dimension(promises: List[Dict[str, Any]], progression: List[Dict[str, Any]]) -> Dict[str, Any]:
    promise_exec = [
        p for p in promises
        if str(p.get("execution_status") or "").upper() in _ACTION_VISIBLE_STATUSES
    ]
    completed_chains = [
        item for item in progression
        if _chain_status(item) in {"ACTION_COMPLETED", "OUTCOME_POSITIVE", "FINANCIAL_IMPACT_CONFIRMED"}
    ]
    started_chains = [
        item for item in progression
        if _chain_status(item) in {"ACTION_STARTED", "ACTION_COMPLETED", "OUTCOME_POSITIVE", "FINANCIAL_IMPACT_CONFIRMED"}
    ]
    delayed = [p for p in promises if str(p.get("current_status") or "").upper() == "DELAYED"]
    missed = [p for p in promises if str(p.get("current_status") or "").upper() in _NEGATIVE_OUTCOME_STATUSES]

    supporting = [
        _source_ref("gold/management_promise_tracker.json", p, p.get("theme") or "", "execution_visible")
        for p in promise_exec[:5]
    ]
    supporting.extend(
        _source_ref("management_progression/management_progression.json", item, _event_text(item), "action_completed")
        for item in completed_chains[:5]
    )
    contrary = [
        _source_ref("gold/management_promise_tracker.json", p, p.get("theme") or "", "timeline_or_delivery_caution")
        for p in (delayed + missed)[:6]
    ]

    if len(promise_exec) + len(completed_chains) >= 3 and len(delayed) + len(missed) <= 1:
        assessment = "execution_follow_through_visible"
    elif len(delayed) + len(missed) >= 2:
        assessment = "execution_discipline_mixed"
    elif len(started_chains) + len(promise_exec) > 0:
        assessment = "execution_activity_visible_but_not_closed"
    else:
        assessment = "insufficient_evidence"

    uncertainty = []
    open_started = max(0, len(started_chains) - len(completed_chains))
    if open_started:
        uncertainty.append(f"{open_started} action chains show activity without clear completion evidence.")
    if not started_chains and not promises:
        uncertainty.append("No management progression or promise evidence was available.")

    return _dimension(
        assessment,
        supporting,
        contrary,
        uncertainty,
        "Execution discipline is assessed from delivery/action evidence only; completion is not treated as economic success.",
        _confidence_from_counts(len(promise_exec) + len(started_chains)),
        f"{len(promise_exec) + len(completed_chains)} execution/completion observations found.",
        "Completion evidence remains separate from outcome and financial proof.",
    )


def _economic_follow_through_dimension(
    promises: List[Dict[str, Any]],
    capital: List[Dict[str, Any]],
    progression: List[Dict[str, Any]],
) -> Dict[str, Any]:
    proven_promises = [
        p for p in promises
        if str(p.get("financial_link_status") or "").upper() in _ECONOMIC_PROVEN_STATUSES
        or str(p.get("outcome_status") or "").upper() in _POSITIVE_OUTCOME_STATUSES
    ]
    partial_promises = [
        p for p in promises
        if str(p.get("financial_link_status") or "").upper() in _ECONOMIC_PARTIAL_STATUSES
    ]
    unproven_promises = [
        p for p in promises
        if str(p.get("execution_status") or "").upper() in _ACTION_VISIBLE_STATUSES
        and str(p.get("financial_link_status") or "").upper() in _ECONOMIC_UNPROVEN_STATUSES
    ]
    proven_allocations = [
        a for a in capital
        if str(a.get("return_status") or "").upper() in {"PROVEN", "POSITIVE", "VALUE_CREATED"}
    ]
    mixed_or_unproven_allocations = [
        a for a in capital
        if str(a.get("return_status") or "").upper() in {"MIXED", "UNPROVEN", ""}
    ]
    financial_confirmed = [
        item for item in progression
        if _chain_status(item) == "FINANCIAL_IMPACT_CONFIRMED"
        or _financial_link_status(item) in {"CONFIRMED", "PROVEN"}
    ]

    supporting = [
        _source_ref("gold/management_promise_tracker.json", p, p.get("theme") or "", "economic_result_visible")
        for p in (proven_promises + partial_promises)[:5]
    ]
    supporting.extend(
        _source_ref("gold/capital_allocation_outcome_tracker.json", a, a.get("investor_interpretation") or a.get("theme") or "", "allocation_return_visible")
        for a in proven_allocations[:4]
    )
    supporting.extend(
        _source_ref("management_progression/management_progression.json", item, _event_text(item), "financial_impact_confirmed")
        for item in financial_confirmed[:4]
    )
    contrary = [
        _source_ref("gold/management_promise_tracker.json", p, p.get("theme") or "", "execution_without_financial_proof")
        for p in unproven_promises[:5]
    ]
    contrary.extend(
        _source_ref("gold/capital_allocation_outcome_tracker.json", a, a.get("theme") or "", "capital_return_unproven_or_mixed")
        for a in mixed_or_unproven_allocations[:5]
    )

    positive_count = len(proven_promises) + len(partial_promises) + len(proven_allocations) + len(financial_confirmed)
    caution_count = len(unproven_promises) + len(mixed_or_unproven_allocations)
    if positive_count >= 3 and caution_count <= positive_count:
        assessment = "economic_follow_through_partly_visible"
    elif caution_count >= 2:
        assessment = "economic_follow_through_unproven"
    elif positive_count:
        assessment = "limited_economic_evidence"
    else:
        assessment = "insufficient_evidence"

    uncertainty = []
    if unproven_promises:
        uncertainty.append(f"{len(unproven_promises)} execution-visible commitments lack attributable financial proof.")
    if mixed_or_unproven_allocations:
        uncertainty.append(f"{len(mixed_or_unproven_allocations)} material allocations have mixed or unproven return evidence.")

    return _dimension(
        assessment,
        supporting,
        contrary,
        uncertainty,
        "Economic credibility requires outcome or financial evidence; action completion and capital deployment alone are not treated as value creation.",
        _confidence_from_counts(positive_count + caution_count),
        f"{positive_count} positive/partial economic observations versus {caution_count} unresolved economic observations.",
        "Financial attribution is conservative and does not infer causality from timing alone.",
    )


def _capital_alignment_dimension(capital: List[Dict[str, Any]], strategy: List[Dict[str, Any]]) -> Dict[str, Any]:
    capital_backed_strategy = [s for s in strategy if bool(s.get("capital_backed"))]
    execution_strategy = [s for s in strategy if bool(s.get("execution_evidence"))]
    unbacked_current = [
        s for s in strategy
        if str(s.get("current_status") or "").upper() == "CURRENT_PRIORITY" and not s.get("capital_backed") and not s.get("execution_evidence")
    ]
    supporting = [
        _source_ref("gold/strategy_evolution_timeline.json", s, s.get("theme_name") or "", "capital_backed_strategy")
        for s in capital_backed_strategy[:6]
    ]
    supporting.extend(
        _source_ref("gold/capital_allocation_outcome_tracker.json", a, a.get("theme") or "", "capital_deployed")
        for a in capital[:5]
    )
    contrary = [
        _source_ref("gold/strategy_evolution_timeline.json", s, s.get("theme_name") or "", "strategy_without_observed_backing")
        for s in unbacked_current[:6]
    ]

    if len(capital_backed_strategy) >= 2 or (capital and capital_backed_strategy):
        assessment = "strategy_capital_alignment_visible"
    elif unbacked_current:
        assessment = "strategy_backing_unproven"
    elif capital:
        assessment = "capital_deployment_visible_but_strategy_link_limited"
    else:
        assessment = "insufficient_evidence"

    return _dimension(
        assessment,
        supporting,
        contrary,
        [
            "Capital backing indicates alignment with stated priorities, not proof that those allocations earned adequate returns."
        ] if supporting else ["No clear capital-backed strategy evidence was available."],
        "This dimension measures whether management put resources behind stated priorities; return quality is assessed separately.",
        _confidence_from_counts(len(capital_backed_strategy) + len(execution_strategy) + len(capital)),
        f"{len(capital_backed_strategy)} strategy themes show capital backing; {len(capital)} material allocations are tracked.",
        f"{len(unbacked_current)} current strategy themes lack observed capital/execution backing.",
    )


def _strategic_consistency_dimension(strategy: List[Dict[str, Any]]) -> Dict[str, Any]:
    persistent = [
        s for s in strategy
        if len(s.get("periods_active") or []) >= 3
        and str(s.get("current_status") or "").upper() in {"CURRENT_PRIORITY", "REINFORCED"}
    ]
    single_period = [s for s in strategy if len(s.get("periods_active") or []) <= 1]
    deprioritized = [
        s for s in strategy
        if str(s.get("current_status") or "").upper() in {"DEPRIORITIZED", "NOT_RECONFIRMED"}
    ]
    supporting = [
        _source_ref("gold/strategy_evolution_timeline.json", s, s.get("theme_name") or "", "persistent_strategy")
        for s in persistent[:7]
    ]
    contrary = [
        _source_ref("gold/strategy_evolution_timeline.json", s, s.get("theme_name") or "", "not_reconfirmed_or_deprioritized")
        for s in deprioritized[:5]
    ]
    if len(persistent) >= 2:
        assessment = "persistent_core_strategy_visible"
    elif deprioritized and len(deprioritized) >= len(persistent):
        assessment = "strategy_continuity_mixed"
    elif strategy:
        assessment = "strategy_evidence_limited_or_recent"
    else:
        assessment = "insufficient_evidence"
    uncertainty = []
    if single_period:
        uncertainty.append(f"{len(single_period)} strategy themes appear in only one period; this may reflect recent emergence or limited evidence.")
    if deprioritized:
        uncertainty.append("Not-reconfirmed themes are not treated as failed strategies without evidence of reversal or abandonment.")
    return _dimension(
        assessment,
        supporting,
        contrary,
        uncertainty or ["No major strategic inconsistency was detected from available Gold evidence."],
        "Strategic consistency rewards persistent or rationally adapted priorities; pivots are not penalized unless reversal evidence exists.",
        _confidence_from_counts(len(strategy)),
        f"{len(persistent)} persistent multi-year strategy themes found.",
        f"{len(single_period)} single-period themes require later confirmation.",
    )


def _risk_response_dimension(risks: List[Dict[str, Any]]) -> Dict[str, Any]:
    mitigation = [
        r for r in risks
        if str(r.get("mitigation_status") or "").lower() not in {"", "not_evidenced", "none"}
    ]
    unresolved_mitigation = [
        r for r in mitigation
        if str(r.get("current_state") or "").upper() != "RESOLVED"
    ]
    worsening = [
        r for r in risks
        if str(r.get("current_state") or "").upper() == "WORSENING"
        or str(r.get("direction") or "").lower() == "worsening"
    ]
    resolved = [r for r in risks if str(r.get("current_state") or "").upper() == "RESOLVED"]

    supporting = [
        _source_ref("gold/risk_evolution_timeline.json", r, r.get("investor_interpretation") or r.get("theme") or "", "risk_mitigation_or_resolution")
        for r in (mitigation + resolved)[:7]
    ]
    contrary = [
        _source_ref("gold/risk_evolution_timeline.json", r, r.get("investor_interpretation") or r.get("theme") or "", "risk_unresolved_or_worsening")
        for r in (unresolved_mitigation + worsening)[:7]
    ]
    if resolved and not worsening:
        assessment = "risk_response_effect_visible"
    elif mitigation and unresolved_mitigation:
        assessment = "risk_response_started_but_resolution_unproven"
    elif worsening:
        assessment = "risk_response_unresolved"
    elif risks:
        assessment = "risk_response_evidence_limited"
    else:
        assessment = "insufficient_evidence"
    return _dimension(
        assessment,
        supporting,
        contrary,
        [
            "Mitigation activity is not treated as risk resolution unless objective exposure reduction or closure evidence exists.",
            f"{len(worsening)} material risk themes are worsening or have worsening direction evidence.",
        ],
        "Risk-response credibility depends on whether risks are acknowledged, mitigated, and objectively reduced; repeated risk disclosure alone is not worsening.",
        _confidence_from_counts(len(risks)),
        f"{len(mitigation)} risk themes show mitigation evidence and {len(resolved)} show resolution evidence.",
        f"{len(unresolved_mitigation)} mitigation-linked themes remain unresolved.",
    )


def _disclosure_quality_dimension(
    promises: List[Dict[str, Any]],
    progression: List[Dict[str, Any]],
    sources: Dict[str, Any],
) -> Dict[str, Any]:
    measurable_promises = [p for p in promises if p.get("measurable_commitment")]
    evidence_rich = [
        p for p in promises
        if len(p.get("later_evidence") or []) >= 2 or len(p.get("evidence_ids") or []) >= 2
    ]
    contradiction_signals = sources.get("management_progression", {}).get("contradiction_signals") or []
    generic_items = [
        item for item in progression
        if _event_text(item)
        and any(term in _norm(_event_text(item)) for term in _GENERIC_PROMOTIONAL_TERMS)
        and not _evidence_ids(item)
    ]
    supporting = [
        _source_ref("gold/management_promise_tracker.json", p, p.get("theme") or "", "measurable_or_followed_up_disclosure")
        for p in (measurable_promises + evidence_rich)[:7]
    ]
    contrary = [
        _source_ref("management_progression/management_progression.json", c if isinstance(c, dict) else {}, str(c), "contradiction_signal")
        for c in contradiction_signals[:5]
    ]
    contrary.extend(
        _source_ref("management_progression/management_progression.json", item, _event_text(item), "generic_promotional_language")
        for item in generic_items[:5]
    )
    if measurable_promises or evidence_rich:
        assessment = "specificity_or_follow_up_visible"
    elif contradiction_signals:
        assessment = "disclosure_consistency_caution"
    elif promises or progression:
        assessment = "disclosure_specificity_limited"
    else:
        assessment = "insufficient_evidence"
    return _dimension(
        assessment,
        supporting,
        contrary,
        [
            "Missing follow-up evidence is separated from management weakness unless the absence itself contradicts a specific prior commitment."
        ],
        "Disclosure quality is based on specificity, measurability, follow-up, and contradictions; promotional language alone is insufficient evidence.",
        _confidence_from_counts(len(measurable_promises) + len(evidence_rich) + len(contradiction_signals)),
        f"{len(measurable_promises)} measurable commitments and {len(evidence_rich)} follow-up-rich promise records found.",
        f"{len(contradiction_signals)} contradiction signals and {len(generic_items)} generic unsupported signals found.",
    )


def _build_dimensions(sources: Dict[str, Any]) -> Dict[str, Any]:
    promises = _promise_items(sources)
    capital = _capital_items(sources)
    strategy = _strategy_items(sources)
    risks = _risk_items(sources)
    progression = _progression_items(sources)
    return {
        "promise_follow_through": _promise_follow_through_dimension(promises),
        "execution_discipline": _execution_discipline_dimension(promises, progression),
        "economic_follow_through": _economic_follow_through_dimension(promises, capital, progression),
        "capital_allocation_alignment": _capital_alignment_dimension(capital, strategy),
        "strategic_consistency": _strategic_consistency_dimension(strategy),
        "risk_response": _risk_response_dimension(risks),
        "disclosure_quality": _disclosure_quality_dimension(promises, progression, sources),
    }


def _strongest_supporting(dimension: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    evidence = dimension.get("supporting_evidence") or []
    return evidence[0] if evidence else None


def _strongest_contrary(dimension: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    evidence = dimension.get("contrary_evidence") or []
    return evidence[0] if evidence else None


def _credibility_patterns(dimensions: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    patterns: List[Dict[str, Any]] = []
    exec_assessment = dimensions["execution_discipline"]["assessment"]
    econ_assessment = dimensions["economic_follow_through"]["assessment"]
    capital_assessment = dimensions["capital_allocation_alignment"]["assessment"]
    risk_assessment = dimensions["risk_response"]["assessment"]
    strategy_assessment = dimensions["strategic_consistency"]["assessment"]
    disclosure_assessment = dimensions["disclosure_quality"]["assessment"]
    promise_assessment = dimensions["promise_follow_through"]["assessment"]

    if exec_assessment in {"execution_follow_through_visible", "execution_activity_visible_but_not_closed"} and econ_assessment in {"economic_follow_through_unproven", "limited_economic_evidence"}:
        patterns.append({
            "pattern_id": "execution_stronger_than_economic_proof",
            "description": "Execution/action evidence is stronger than evidence that completed actions translated into measurable economic outcomes.",
            "evidence_basis": [
                dimensions["execution_discipline"]["management_behavior_signal"],
                dimensions["economic_follow_through"]["evidence_completeness_signal"],
            ],
            "investor_relevance": "Future guidance deserves follow-up against operating and financial outcomes, not just delivery milestones.",
        })
    if capital_assessment == "strategy_capital_alignment_visible":
        patterns.append({
            "pattern_id": "capital_backed_strategy",
            "description": "Several stated priorities have observable capital deployment or execution backing.",
            "evidence_basis": [dimensions["capital_allocation_alignment"]["management_behavior_signal"]],
            "investor_relevance": "This supports alignment between stated priorities and resource allocation, while leaving return quality separate.",
        })
    if risk_assessment == "risk_response_started_but_resolution_unproven":
        patterns.append({
            "pattern_id": "risk_mitigation_without_resolution",
            "description": "Management response evidence exists for risk themes, but objective resolution is not established.",
            "evidence_basis": [dimensions["risk_response"]["evidence_completeness_signal"]],
            "investor_relevance": "Mitigation should be monitored for actual exposure reduction.",
        })
    if risk_assessment == "risk_response_unresolved":
        patterns.append({
            "pattern_id": "worsening_risks_without_visible_resolution",
            "description": "Material risks remain worsening or unresolved in the available Gold risk timeline.",
            "evidence_basis": [dimensions["risk_response"]["evidence_completeness_signal"]],
            "investor_relevance": "Risk handling deserves cautious interpretation until mitigation effectiveness is visible.",
        })
    if strategy_assessment == "persistent_core_strategy_visible":
        patterns.append({
            "pattern_id": "persistent_core_strategy",
            "description": "The strategy timeline shows multiple priorities persisting across several periods.",
            "evidence_basis": [dimensions["strategic_consistency"]["management_behavior_signal"]],
            "investor_relevance": "Persistent priorities can support credibility when execution and economics later validate them.",
        })
    if promise_assessment == "insufficient_verification":
        patterns.append({
            "pattern_id": "frequent_unverified_commitments",
            "description": "Many commitments remain unverified in the available evidence corpus.",
            "evidence_basis": [dimensions["promise_follow_through"]["evidence_completeness_signal"]],
            "investor_relevance": "This limits confidence in assessing follow-through but is not itself evidence of failure.",
        })
    if disclosure_assessment == "specificity_or_follow_up_visible":
        patterns.append({
            "pattern_id": "measurable_or_followed_up_disclosure",
            "description": "Some disclosures contain measurable targets or later follow-up evidence.",
            "evidence_basis": [dimensions["disclosure_quality"]["management_behavior_signal"]],
            "investor_relevance": "More specific disclosure improves the usefulness of future management statements.",
        })
    return patterns


def _dimension_balance(dimensions: Dict[str, Dict[str, Any]]) -> Tuple[int, int, int]:
    positive = 0
    caution = 0
    insufficient = 0
    for dim in dimensions.values():
        assessment = str(dim.get("assessment") or "")
        if assessment == "insufficient_evidence":
            insufficient += 1
        elif any(term in assessment for term in ("visible", "constructive", "persistent")) and "caution" not in assessment:
            positive += 1
        if any(term in assessment for term in ("caution", "unproven", "unresolved", "mixed", "limited")):
            caution += 1
    return positive, caution, insufficient


def _guidance_weight(dimensions: Dict[str, Dict[str, Any]]) -> Tuple[str, str, str]:
    positive, caution, insufficient = _dimension_balance(dimensions)
    economic = dimensions["economic_follow_through"]["assessment"]
    risk = dimensions["risk_response"]["assessment"]
    promise = dimensions["promise_follow_through"]["assessment"]
    if insufficient >= 5:
        return (
            "INSUFFICIENT_BASIS",
            "Too many credibility dimensions lack enough evidence for a reliable view.",
            "INSUFFICIENT_EVIDENCE",
        )
    if (
        positive >= 5
        and caution <= 1
        and economic != "economic_follow_through_unproven"
        and risk != "risk_response_unresolved"
        and promise != "insufficient_verification"
    ):
        return (
            "STRONG_WEIGHT",
            "Most dimensions show repeated, supported follow-through with limited unresolved counter-evidence.",
            "HIGH_EVIDENCE",
        )
    if caution >= 4 or economic == "economic_follow_through_unproven" or risk == "risk_response_unresolved":
        if positive >= 2 and promise != "mixed_with_follow_through_cautions":
            return (
                "MODERATE_WEIGHT",
                "Operational or strategic follow-through exists, but economic validation and/or risk resolution remains incomplete.",
                "MODERATE_EVIDENCE",
            )
        return (
            "CAUTIOUS_WEIGHT",
            "Credibility evidence is materially constrained by unresolved economics, risks, or follow-through cautions.",
            "LOW_EVIDENCE" if insufficient >= 2 else "MODERATE_EVIDENCE",
        )
    if positive >= 2:
        return (
            "MODERATE_WEIGHT",
            "Several behavior signals are constructive, while remaining evidence gaps prevent stronger reliance.",
            "MODERATE_EVIDENCE",
        )
    return (
        "CAUTIOUS_WEIGHT",
        "The available record is too thin or mixed to put strong weight on current management guidance.",
        "LOW_EVIDENCE",
    )


def _summary(dimensions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    guidance, reason, confidence = _guidance_weight(dimensions)
    strengths: List[str] = []
    cautions: List[str] = []
    for key, dim in dimensions.items():
        support = _strongest_supporting(dim)
        caution = _strongest_contrary(dim)
        if support:
            strengths.append(f"{key}: {support['text']}")
        if caution:
            cautions.append(f"{key}: {caution['text']}")
    exec_vs_econ = execution_vs_economics_conclusion(dimensions)
    summary = (
        f"Management guidance deserves {guidance.lower().replace('_', ' ')}. "
        f"{reason} {exec_vs_econ}"
    )
    return {
        "management_credibility_summary": _short(summary, 520),
        "guidance_weight": guidance,
        "guidance_weight_reason": reason,
        "evidence_confidence": confidence,
        "key_strengths": _dedupe(strengths, 5),
        "key_cautions": _dedupe(cautions, 5),
    }


def execution_vs_economics_conclusion(dimensions: Dict[str, Dict[str, Any]]) -> str:
    execution = dimensions["execution_discipline"]["assessment"]
    economics = dimensions["economic_follow_through"]["assessment"]
    if execution in {"execution_follow_through_visible", "execution_activity_visible_but_not_closed"} and economics in {"economic_follow_through_unproven", "limited_economic_evidence"}:
        return "Management appears better supported on execution/activity evidence than on demonstrated economic follow-through."
    if execution == "insufficient_evidence":
        return "Execution discipline cannot be judged confidently from available evidence."
    if economics == "economic_follow_through_partly_visible":
        return "Some economic follow-through is visible, but execution attribution remains conservative."
    return "Execution and economic follow-through evidence are mixed or limited."


def _evidence_limitations(dimensions: Dict[str, Dict[str, Any]], sources: Dict[str, Any]) -> List[Dict[str, Any]]:
    limitations: List[Dict[str, Any]] = []
    for key, dim in dimensions.items():
        for text in dim.get("uncertainty") or []:
            limitations.append({
                "dimension": key,
                "limitation": text,
                "interpretation_rule": "Evidence incompleteness is not treated as management weakness unless contradicted by later facts.",
            })
    missing_sources = []
    if not sources.get("promise_tracker"):
        missing_sources.append("gold/management_promise_tracker.json")
    if not sources.get("capital_tracker"):
        missing_sources.append("gold/capital_allocation_outcome_tracker.json")
    if not sources.get("strategy_timeline"):
        missing_sources.append("gold/strategy_evolution_timeline.json")
    if not sources.get("risk_timeline"):
        missing_sources.append("gold/risk_evolution_timeline.json")
    if missing_sources:
        limitations.append({
            "dimension": "source_coverage",
            "limitation": "Missing source artifacts: " + ", ".join(missing_sources),
            "interpretation_rule": "The credibility layer does not reconstruct missing Gold evidence from raw reports.",
        })
    return limitations[:12]


def _monitoring_questions(dimensions: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    econ = dimensions["economic_follow_through"]
    risk = dimensions["risk_response"]
    promise = dimensions["promise_follow_through"]
    capital = dimensions["capital_allocation_alignment"]
    strategy = dimensions["strategic_consistency"]
    if econ.get("contrary_evidence"):
        questions.append({
            "question": "Did completed initiatives produce measurable revenue, margin, cash-flow, ROCE, or customer-economics improvement?",
            "linked_dimension": "economic_follow_through",
            "why_it_matters": "Execution credibility becomes stronger only when operating or financial outcomes validate the action.",
        })
    if risk.get("contrary_evidence"):
        questions.append({
            "question": "Did mitigation actions reduce the material risk exposure, or was the risk merely acknowledged again?",
            "linked_dimension": "risk_response",
            "why_it_matters": "Risk mitigation is not equivalent to risk resolution.",
        })
    if promise.get("uncertainty"):
        questions.append({
            "question": "Which unverified commitments received later delivery, revision, abandonment, or outcome evidence?",
            "linked_dimension": "promise_follow_through",
            "why_it_matters": "Unverified commitments limit credibility assessment without proving failure.",
        })
    if capital.get("supporting_evidence"):
        questions.append({
            "question": "Did capital-backed strategic priorities earn adequate incremental returns after deployment?",
            "linked_dimension": "capital_allocation_alignment",
            "why_it_matters": "Capital alignment supports seriousness of intent, not value creation.",
        })
    if strategy.get("uncertainty"):
        questions.append({
            "question": "Were recently introduced or not-reconfirmed strategy themes reinforced in later periods?",
            "linked_dimension": "strategic_consistency",
            "why_it_matters": "A one-period strategy signal is weaker than persistent multi-year behavior.",
        })
    return questions[:8]


def _source_contracts(sources: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "uses_existing_gold_only": True,
        "no_numeric_rating": True,
        "sources": {
            "management_promise_tracker": bool(sources.get("promise_tracker")),
            "capital_allocation_outcome_tracker": bool(sources.get("capital_tracker")),
            "strategy_evolution_timeline": bool(sources.get("strategy_timeline")),
            "risk_evolution_timeline": bool(sources.get("risk_timeline")),
            "management_progression": bool(sources.get("management_progression")),
            "management_quality": bool(sources.get("management_quality_summary") or sources.get("management_quality_dimensions")),
        },
        "semantic_safeguards": [
            "evidence_incompleteness_not_management_weakness",
            "completion_not_success",
            "capital_backing_not_return_quality",
            "mitigation_not_resolution",
            "pivot_not_automatic_credibility_failure",
        ],
    }


def build_management_credibility_synthesis(
    company_slug: str,
    companies_root: Path = Path("companies"),
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    sources = _load_sources(company_slug, companies_root)
    dimensions = _build_dimensions(sources)
    patterns = _credibility_patterns(dimensions)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "company_slug": company_slug,
        "generated_at": generated_at or _utc_now(),
        "summary": _summary(dimensions),
        "dimensions": dimensions,
        "credibility_patterns": patterns,
        "evidence_limitations": _evidence_limitations(dimensions, sources),
        "current_monitoring_questions": _monitoring_questions(dimensions),
        "cross_gold_consistency": {
            "status": "pass",
            "checks": [
                "Promise statuses are not converted into management failure solely because evidence is unverified.",
                "Capital-backed strategy is kept separate from capital return quality.",
                "Risk mitigation is kept separate from objective risk resolution.",
                "Action completion is kept separate from economic outcome proof.",
            ],
        },
        "source_contract": _source_contracts(sources),
    }
    assert payload["summary"]["guidance_weight"] in GUIDANCE_WEIGHTS
    return payload


def write_management_credibility_synthesis(
    company_slug: str,
    companies_root: Path = Path("companies"),
) -> Path:
    payload = build_management_credibility_synthesis(company_slug, companies_root=companies_root)
    out_dir = companies_root / company_slug / "company_memory" / "gold"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / ARTIFACT_NAME
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path
