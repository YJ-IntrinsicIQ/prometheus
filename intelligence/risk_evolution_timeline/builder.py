from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from knowledge.company_memory import parse_financial_year


SCHEMA_VERSION = "risk_evolution_gold.v1"

RISK_STATES = {
    "NEW",
    "RECURRING",
    "WORSENING",
    "STABLE",
    "IMPROVING",
    "MITIGATION_STARTED",
    "MITIGATED",
    "RESOLVED",
    "REAPPEARED",
    "NOT_RECONFIRMED",
}

_SEVERITY_RANK = {
    "critical": 4,
    "severe": 4,
    "high": 3,
    "medium": 2,
    "moderate": 2,
    "low": 1,
    "minor": 1,
    "unknown": 0,
    "not stated": 0,
    "": 0,
}

_GENERIC_RISK_PHRASES = (
    "global uncertainty",
    "changing market conditions",
    "competition exists",
    "cybersecurity is important",
    "risk to business",
    "general economic conditions",
    "macroeconomic conditions",
    "may affect operations",
)

_MATERIAL_TERMS = (
    "earnings",
    "cash",
    "cash flow",
    "capital",
    "revenue",
    "margin",
    "pricing",
    "customer",
    "market share",
    "competition",
    "regulatory",
    "restriction",
    "usfda",
    "compliance",
    "license",
    "facility",
    "plant",
    "supply",
    "debt",
    "liquidity",
    "leverage",
    "credit",
    "npa",
    "collection",
    "receivable",
    "working capital",
    "acquisition",
    "integration",
    "impairment",
    "technology",
    "cyber",
    "security",
    "execution",
    "delivery",
    "governance",
)

_MITIGATION_STARTED_TERMS = (
    "mitigation",
    "mitigate",
    "remediation",
    "remediate",
    "corrective action",
    "action plan",
    "response",
    "commissioned",
    "introduced",
    "implemented",
    "established",
    "launched",
    "started",
    "began",
    "strengthened",
)

_MITIGATION_COMPLETED_TERMS = (
    "completed",
    "commissioned",
    "operational",
    "implemented",
    "established",
    "resolved",
    "closed",
)

_RISK_RESPONSE_CONTEXT_TERMS = (
    "mitigation",
    "mitigate",
    "remediation",
    "remediate",
    "corrective action",
    "response",
    "company's response",
    "company response",
    "grievance",
    "complaint",
    "collection",
    "recovery",
    "compliance",
    "customer service",
    "customer satisfaction",
)

_RESOLUTION_TERMS = (
    "formally lifted",
    "restriction lifted",
    "settled",
    "closed",
    "withdrawn",
    "fully repaid",
)

_ADVERSE_TERMS = (
    "worsen",
    "deteriorat",
    "increase",
    "rise",
    "higher",
    "elevated",
    "restriction",
    "prohibited",
    "alert",
    "oai",
    "observation",
    "impairment",
    "loss",
    "decline",
    "pressure",
    "strain",
)

_IMPROVING_TERMS = (
    "improv",
    "decline",
    "reduced",
    "lower",
    "normalis",
    "normaliz",
    "lifted",
    "resolved",
    "repaid",
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


def _slug(value: Any) -> str:
    slug = _norm(value).replace(" ", "_").strip("_")
    return slug or "risk"


def _period_sort_key(value: Any) -> int:
    try:
        return parse_financial_year(str(value).lower())
    except Exception:
        return 10_000


def _ordered_periods(periods: Iterable[Any]) -> List[str]:
    return sorted({str(p).strip().lower() for p in periods if str(p).strip()}, key=_period_sort_key)


def _severity_rank(value: Any) -> int:
    text = str(value or "").strip().lower()
    return _SEVERITY_RANK.get(text, 0)


def _severity_label(rank: int) -> str:
    if rank >= 4:
        return "critical"
    if rank == 3:
        return "high"
    if rank == 2:
        return "medium"
    if rank == 1:
        return "low"
    return "unknown"


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


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
    seen: set[str] = set()
    ordered: List[str] = []
    for eid in ids:
        if eid not in seen:
            seen.add(eid)
            ordered.append(eid)
    return ordered


def _is_generic_or_immaterial(name: str, description: str) -> bool:
    text = f"{name} {description}".lower()
    if not text.strip():
        return True
    if any(phrase in text for phrase in _GENERIC_RISK_PHRASES):
        return True
    if len(_norm(description or name).split()) < 3:
        return True
    return not _contains_any(text, _MATERIAL_TERMS)


def normalize_risk_theme(value: Any, description: Any = "") -> Tuple[str, str]:
    text = f"{value or ''} {description or ''}".lower()
    families: Sequence[Tuple[Sequence[str], str, str]] = (
        (("regulatory", "usfda", "compliance", "consent decree", "import alert", "restriction", "oai", "legal provision"), "regulatory", "regulatory"),
        (("working capital", "cash conversion", "receivable", "inventory days", "payable days"), "working-capital and cash-conversion", "working_capital"),
        (("credit", "npa", "delinquen", "over-indebted", "collection", "restructur"), "credit quality", "credit_quality"),
        (("competition", "price erosion", "market share", "generic approval", "pricing pressure"), "competitive intensity", "competition"),
        (("customer concentration", "revenue concentration", "churn", "customer experience"), "customer concentration / retention", "customer"),
        (("acquisition", "integration", "contingent liabilit", "impairment", "patent dispute"), "acquisition integration", "acquisition_integration"),
        (("cyber", "data protection", "privacy", "security breach"), "cyber / data-protection", "cyber_operational"),
        (("supply", "supplier", "raw material", "vendor", "procurement"), "supply-chain disruption", "supply_chain"),
        (("technology", "technical debt", "obsolescence", "disruption"), "technology disruption", "technology"),
        (("execution", "project", "delivery", "deadline", "implementation"), "execution and delivery", "execution"),
        (("liquidity", "funding", "debt", "leverage", "wholesale funds"), "liquidity / leverage", "liquidity_leverage"),
        (("governance", "ethics", "related-party", "incentive"), "governance", "governance"),
        (("margin", "cost inflation", "cost pressure", "price pressure"), "pricing / margin pressure", "margin_pressure"),
        (("capacity utilisation", "capacity utilization"), "capacity utilisation", "capacity_utilisation"),
    )
    for needles, theme, risk_type in families:
        if any(needle in text for needle in needles):
            return theme, risk_type
    label = str(value or description or "other risk").replace("_", " ").strip().lower()
    return label[:80] or "other risk", "other"


def classify_event_type(text: str, *, first_period: bool = False, severity_delta: int = 0) -> str:
    lowered = text.lower()
    if first_period:
        return "risk_emerged"
    if _contains_any(lowered, _RESOLUTION_TERMS):
        return "resolution_claim_or_evidence"
    if severity_delta > 0 or _contains_any(lowered, _ADVERSE_TERMS):
        return "risk_worsened"
    if severity_delta < 0 or _contains_any(lowered, _IMPROVING_TERMS):
        return "risk_improved"
    return "risk_reconfirmed"


def _load_sources(company_slug: str, companies_root: Path) -> Dict[str, Any]:
    mem = companies_root / company_slug / "company_memory"
    return {
        "risk_evolution": _load_json(mem / "multi_year" / "risk_evolution.json") or _load_json(mem / "risk_evolution.json"),
        "risk_registry": _load_json(mem / "risks" / "risk_registry.json"),
        "management_progression": _load_json(mem / "management_progression" / "management_progression.json"),
        "management_commitments": _load_json(mem / "management_commitments" / "management_commitments.json"),
        "management_commentary": _load_json(mem / "management_commentary" / "commentary_timelines.json"),
        "projects": _load_json(mem / "projects" / "projects_registry.json"),
        "capacity": _load_json(mem / "capacity" / "capacity_registry.json"),
        "capital_allocation_gold": _load_json(mem / "gold" / "capital_allocation_outcome_tracker.json"),
        "strategy_gold": _load_json(mem / "gold" / "strategy_evolution_timeline.json"),
        "financial_truth": _load_json(mem / "financials" / "financial_truth_pack.json"),
        "financial_trends": _load_json(mem / "financials" / "financial_trends.json"),
        "working_capital": _load_json(mem / "financials" / "investor_financial_modules" / "working_capital_quality_drilldown.json"),
        "company_model": _load_json(mem / "company_model" / "company_model.json"),
    }


def _theme_seed_records(risk_evolution: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if not isinstance(risk_evolution, dict):
        return records
    for risk in risk_evolution.get("risks") or []:
        if not isinstance(risk, dict):
            continue
        mentions = [m for m in (risk.get("source_mentions") or []) if isinstance(m, dict)]
        if not mentions:
            mentions = [
                {
                    "source_year": risk.get("first_seen_year") or risk.get("latest_period"),
                    "value": risk.get("risk_name") or risk.get("normalized_risk"),
                    "severity": risk.get("latest_severity") or risk.get("current_state"),
                    "evidence_ids": risk.get("related_evidence_ids") or [],
                    "source_artifact": "multi_year/risk_evolution.json",
                    "source_item_id": risk.get("risk_id"),
                }
            ]
        for mention in mentions:
            description = mention.get("value") or risk.get("risk_name") or risk.get("normalized_risk")
            theme, risk_type = normalize_risk_theme(description, "")
            if _is_generic_or_immaterial(theme, description):
                continue
            period = str(mention.get("source_year") or risk.get("first_seen_year") or risk.get("latest_period") or "").lower()
            severity = mention.get("severity") or (risk.get("severity_by_year") or {}).get(period) or risk.get("latest_severity")
            records.append(
                {
                    "source": risk,
                    "theme": theme,
                    "risk_type": risk_type,
                    "mentions": [mention],
                    "first_seen": period,
                    "latest_seen": period,
                    "repeated_years": risk.get("repeated_years") or [],
                    "severity_by_year": {period: severity} if period else {},
                    "risk_name": theme,
                    "description": description,
                    "evidence_ids": mention.get("evidence_ids") or risk.get("related_evidence_ids") or [],
                }
            )
    return records


def _financial_working_capital_records(working_capital: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if not isinstance(working_capital, dict):
        return records
    for item in working_capital.get("drilldown") or []:
        if not isinstance(item, dict):
            continue
        intensity = str(item.get("working_capital_intensity_status") or "").lower()
        strain = str(item.get("cash_strain_risk") or "").lower()
        if intensity not in {"severe", "high"} and strain not in {"elevated", "high", "severe"}:
            continue
        year = item.get("fiscal_year") or item.get("period")
        description = (
            f"Working-capital intensity {intensity or 'unknown'}; receivable days {item.get('receivable_days')}, "
            f"inventory days {item.get('inventory_days')}, payable days {item.get('payable_days')}."
        )
        records.append(
            {
                "source": item,
                "theme": "working-capital and cash-conversion",
                "risk_type": "working_capital",
                "mentions": [
                    {
                        "source_year": year,
                        "value": description,
                        "severity": "high" if intensity == "severe" or strain in {"high", "severe"} else "medium",
                        "source_artifact": "working_capital_quality_drilldown.json",
                        "source_item_id": f"working_capital_{year}",
                    }
                ],
                "first_seen": year,
                "latest_seen": year,
                "repeated_years": [],
                "severity_by_year": {str(year): "high" if intensity == "severe" else "medium"} if year else {},
                "risk_name": "Working-capital and cash-conversion pressure",
                "description": description,
                "evidence_ids": _evidence_ids(item),
            }
        )
    return records


def _management_progression_mitigations(progression: Dict[str, Any]) -> List[Dict[str, Any]]:
    links: List[Dict[str, Any]] = []
    if not isinstance(progression, dict):
        return links
    for item in progression.get("progression_items") or []:
        if not isinstance(item, dict):
            continue
        chain = item.get("synthesis_chain") if isinstance(item.get("synthesis_chain"), dict) else {}
        status = str(chain.get("chain_status") or "").upper()
        action = chain.get("action") if isinstance(chain.get("action"), dict) else {}
        outcome = chain.get("outcome") if isinstance(chain.get("outcome"), dict) else {}
        financial = chain.get("financial_consequence") if isinstance(chain.get("financial_consequence"), dict) else {}
        text = action.get("text") or outcome.get("text") or item.get("description") or item.get("theme") or ""
        response_context = f"{text} {item.get('theme') or ''} {item.get('topic') or ''}".lower()
        if not _contains_any(response_context, _MITIGATION_STARTED_TERMS) or not _contains_any(response_context, _RISK_RESPONSE_CONTEXT_TERMS):
            continue
        theme, risk_type = normalize_risk_theme(f"{text} {item.get('theme') or ''} {item.get('topic') or ''}", "")
        event_type = "mitigation_completed" if status == "ACTION_COMPLETED" else "mitigation_started"
        if status in {"OUTCOME_POSITIVE", "FINANCIAL_IMPACT_CONFIRMED"}:
            event_type = "mitigation_effect_visible"
        links.append(
            {
                "theme": theme,
                "risk_type": risk_type,
                "event": {
                    "period": item.get("period") or item.get("latest_period") or item.get("source_period") or "",
                    "event_type": event_type,
                    "evidence": _short(text, 260),
                    "management_response": _short(text, 220),
                    "financial_or_operating_effect": _short(outcome.get("text") or financial.get("text") or "", 220),
                    "evidence_ids": _evidence_ids(chain)[:5],
                    "source_artifact": "management_progression/management_progression.json",
                    "source_item_id": item.get("item_id"),
                    "chain_status": status,
                    "financial_link_status": financial.get("link_status"),
                },
            }
        )
    return links


def _strategy_links(strategy_gold: Dict[str, Any], theme: str, risk_type: str) -> List[str]:
    if not isinstance(strategy_gold, dict):
        return []
    theme_tokens = set(_norm(theme).split()) | set(_norm(risk_type).split())
    ids: List[str] = []
    for item in strategy_gold.get("strategy_themes") or []:
        if not isinstance(item, dict):
            continue
        text = _norm(f"{item.get('theme_name')} {item.get('theme_category')} {item.get('investor_implication')}")
        if theme_tokens and any(token in text for token in theme_tokens if len(token) >= 6):
            ids.append(str(item.get("theme_id") or item.get("theme_name")))
    return [item for item in ids if item][:5]


def _capital_links(capital_gold: Dict[str, Any], theme: str, risk_type: str) -> List[str]:
    if not isinstance(capital_gold, dict):
        return []
    relevant = {"acquisition_integration", "liquidity_leverage", "capacity_utilisation"}
    if risk_type not in relevant:
        return []
    tokens = set(_norm(theme).split()) | set(_norm(risk_type).split())
    ids: List[str] = []
    for item in capital_gold.get("material_allocations") or []:
        if not isinstance(item, dict):
            continue
        text = _norm(json.dumps(item, ensure_ascii=False))
        if any(token in text for token in tokens if len(token) >= 7):
            ids.append(str(item.get("allocation_id") or item.get("theme")))
    return [item for item in ids if item][:5]


def _risk_description(theme: str, records: List[Dict[str, Any]]) -> str:
    descriptions = [r.get("description") for r in records if r.get("description")]
    if descriptions:
        return _short(max(descriptions, key=len), 280)
    return f"{theme.title()} risk remains visible in company evidence."


def _economic_exposure(theme: str, risk_type: str) -> str:
    mapping = {
        "regulatory": "May affect the company's ability to operate, sell into regulated markets, or avoid remediation/legal costs.",
        "working_capital": "Can consume cash, weaken owner earnings, and reduce the quality of reported growth.",
        "credit_quality": "Can increase credit losses, provisioning, capital strain, and lending-growth risk.",
        "competition": "Can pressure pricing, revenue durability, margins, or market position.",
        "customer": "Can weaken revenue durability, retention, bargaining power, and growth visibility.",
        "acquisition_integration": "Can impair capital allocation outcomes through integration costs, legal exposure, or write-downs.",
        "cyber_operational": "Can disrupt operations, create compliance costs, or damage customer trust.",
        "technology": "Can erode product relevance, increase reinvestment needs, or weaken competitiveness.",
        "supply_chain": "Can disrupt production, increase costs, or delay delivery.",
        "execution": "Can delay projects, weaken delivery, or reduce strategy credibility.",
        "liquidity_leverage": "Can restrict funding flexibility and reduce balance-sheet resilience.",
        "governance": "Can create capital-allocation, disclosure, and minority-investor risk.",
        "margin_pressure": "Can reduce earnings power and cash-generation durability.",
        "capacity_utilisation": "Can turn capacity/capex into under-earned capital.",
    }
    return mapping.get(risk_type, f"May affect earnings, cash flow, capital, market position, or execution depending on how {theme} evolves.")


def _resolve_direction(periods: List[str], severity_by_period: Dict[str, int], listed_worsening: bool, listed_improving: bool) -> str:
    if len(periods) <= 1:
        return "new"
    first = severity_by_period.get(periods[0], 0)
    latest = severity_by_period.get(periods[-1], 0)
    if latest > first:
        return "worsening"
    if latest < first and latest > 0:
        return "improving"
    if listed_worsening and not listed_improving and latest >= first and latest > 0:
        return "worsening"
    if listed_improving and not listed_worsening and latest <= first:
        return "improving"
    return "stable"


def _resolve_current_state(
    *,
    periods: List[str],
    latest_period: str,
    direction: str,
    has_latest_resolution: bool,
    has_mitigation: bool,
    has_effect_visible: bool,
    had_gap_then_returned: bool,
) -> str:
    if has_latest_resolution:
        return "RESOLVED"
    if had_gap_then_returned:
        return "REAPPEARED"
    if direction == "worsening":
        return "WORSENING"
    if direction == "improving":
        return "IMPROVING" if not has_effect_visible else "MITIGATED"
    if has_mitigation and not has_effect_visible:
        return "MITIGATION_STARTED"
    if len(periods) > 1:
        return "RECURRING"
    if periods and periods[-1] != latest_period:
        return "NOT_RECONFIRMED"
    return "NEW"


def _mitigation_status(events: List[Dict[str, Any]]) -> str:
    types = {event.get("event_type") for event in events}
    if "mitigation_effect_visible" in types:
        return "effect_visible"
    if "mitigation_completed" in types:
        return "completed_outcome_unproven"
    if "mitigation_started" in types:
        return "started"
    return "not_evidenced"


def _economic_impact_status(events: List[Dict[str, Any]]) -> str:
    if any(event.get("financial_link_status") == "confirmed" for event in events):
        return "PROVEN"
    if any(event.get("financial_or_operating_effect") for event in events):
        return "PARTIAL"
    return "UNPROVEN"


def _investor_interpretation(theme: str, state: str, direction: str, mitigation: str, economic_status: str) -> str:
    base = f"{theme.title()} is {state.lower().replace('_', ' ')}"
    if direction in {"worsening", "improving", "stable"}:
        base += f" with {direction} direction evidence"
    if mitigation == "completed_outcome_unproven":
        return base + "; mitigation activity is completed, but risk resolution remains unproven."
    if mitigation == "started":
        return base + "; management response has started, but effect is not yet proven."
    if state == "RESOLVED":
        return base + "; affirmative closure evidence supports resolution."
    if economic_status == "UNPROVEN":
        return base + "; economic impact attribution remains unproven."
    return base + "."


def _critical_follow_up(theme_record: Dict[str, Any]) -> Dict[str, Any]:
    state = theme_record.get("current_state")
    theme = theme_record.get("theme")
    risk_type = theme_record.get("risk_type")
    if state == "WORSENING":
        trigger = f"Look for objective evidence that {theme} stops worsening across the next filing."
    elif state in {"MITIGATION_STARTED", "MITIGATED"}:
        trigger = f"Look for operating or financial proof that mitigation reduced {theme} exposure."
    elif state == "RECURRING":
        trigger = f"Look for whether {theme} is reconfirmed again or receives affirmative mitigation evidence."
    elif state == "NOT_RECONFIRMED":
        trigger = f"Look for affirmative closure evidence before treating {theme} as resolved."
    else:
        trigger = f"Look for new evidence changing {theme} direction or economic exposure."
    if risk_type == "working_capital":
        trigger = "Receivable days, inventory days, payable days, and CFO/earnings conversion should improve across future filings."
    elif risk_type == "credit_quality":
        trigger = "Gross/net NPA, credit cost, collections, and restructuring evidence should improve while loan growth continues."
    elif risk_type == "regulatory":
        trigger = "Regulatory observations, restrictions, import alerts, consent-decree items, or remediation status should receive affirmative closure evidence."
    return {
        "risk_theme_id": theme_record.get("risk_theme_id"),
        "theme": theme,
        "trigger": trigger,
        "state": state,
    }


def _build_theme_records(sources: Dict[str, Any]) -> List[Dict[str, Any]]:
    seeds = _theme_seed_records(sources["risk_evolution"])
    seeds.extend(_financial_working_capital_records(sources["working_capital"]))
    by_theme: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for seed in seeds:
        by_theme[(seed["theme"], seed["risk_type"])].append(seed)

    listed_worsening = set(sources["risk_evolution"].get("worsening_risks") or []) if isinstance(sources["risk_evolution"], dict) else set()
    listed_improving = set(sources["risk_evolution"].get("improving_risks") or []) if isinstance(sources["risk_evolution"], dict) else set()
    mitigation_links = _management_progression_mitigations(sources["management_progression"])

    latest_period = ""
    all_periods: List[str] = []
    for seed in seeds:
        all_periods.extend(seed.get("severity_by_year", {}).keys())
        for mention in seed.get("mentions") or []:
            all_periods.append(mention.get("source_year"))
    if all_periods:
        latest_period = _ordered_periods(all_periods)[-1]

    records: List[Dict[str, Any]] = []
    for idx, ((theme, risk_type), grouped) in enumerate(sorted(by_theme.items()), start=1):
        severity_by_period: Dict[str, int] = {}
        timeline: List[Dict[str, Any]] = []
        source_ids: List[str] = []
        raw_risk_ids: List[str] = []
        for seed in grouped:
            raw_risk_id = seed.get("source", {}).get("risk_id")
            if raw_risk_id:
                raw_risk_ids.append(raw_risk_id)
            source_ids.extend(seed.get("evidence_ids") or [])
            for period, sev in (seed.get("severity_by_year") or {}).items():
                severity_by_period[str(period).lower()] = max(severity_by_period.get(str(period).lower(), 0), _severity_rank(sev))
            for mention in seed.get("mentions") or []:
                period = str(mention.get("source_year") or seed.get("first_seen") or "").lower()
                if not period:
                    continue
                rank = _severity_rank(mention.get("severity")) or severity_by_period.get(period, 0)
                prior = severity_by_period.get(period, 0)
                severity_by_period[period] = max(prior, rank)
                timeline.append(
                    {
                        "period": period,
                        "event_type": "risk_signal",
                        "evidence": _short(mention.get("value") or seed.get("description"), 280),
                        "management_response": "",
                        "financial_or_operating_effect": "",
                        "severity": _severity_label(rank),
                        "evidence_ids": _evidence_ids(mention)[:6] or list(seed.get("evidence_ids") or [])[:6],
                        "source_artifact": mention.get("source_artifact") or "multi_year/risk_evolution.json",
                        "source_item_id": mention.get("source_item_id") or seed.get("source", {}).get("risk_id"),
                    }
                )

        periods = _ordered_periods(severity_by_period.keys() or [event.get("period") for event in timeline])
        for pidx, event in enumerate(sorted(timeline, key=lambda e: (_period_sort_key(e.get("period")), e.get("source_item_id") or ""))):
            period = event.get("period")
            prior_period = periods[periods.index(period) - 1] if period in periods and periods.index(period) > 0 else None
            delta = severity_by_period.get(period, 0) - (severity_by_period.get(prior_period, 0) if prior_period else 0)
            event["event_type"] = classify_event_type(
                event.get("evidence") or "",
                first_period=(period == periods[0] if periods else pidx == 0),
                severity_delta=delta,
            )

        linked_mitigations = [
            link["event"]
            for link in mitigation_links
            if link["theme"] == theme or link["risk_type"] == risk_type
        ]
        timeline.extend(linked_mitigations)
        timeline = sorted(timeline, key=lambda e: (_period_sort_key(e.get("period")), str(e.get("event_type") or "")))
        resolution_periods = {
            event.get("period")
            for event in timeline
            if event.get("event_type") == "resolution_claim_or_evidence"
            and _contains_any(event.get("evidence", ""), _RESOLUTION_TERMS)
        }
        has_latest_resolution = bool(periods and periods[-1] in resolution_periods)
        has_mitigation = any(str(event.get("event_type") or "").startswith("mitigation") for event in timeline)
        has_effect_visible = any(event.get("event_type") == "mitigation_effect_visible" for event in timeline)
        raw_ids = set(raw_risk_ids)
        direction = _resolve_direction(
            periods,
            severity_by_period,
            bool(raw_ids & listed_worsening),
            bool(raw_ids & listed_improving),
        )
        gaps = [
            _period_sort_key(periods[i + 1]) - _period_sort_key(periods[i])
            for i in range(len(periods) - 1)
        ]
        latest_return_after_gap = bool(gaps and max(gaps) > 1 and periods[-1] == latest_period)
        had_prior_closure_signal = any(period in resolution_periods for period in periods[:-1])
        had_gap_then_returned = latest_return_after_gap and had_prior_closure_signal
        state = _resolve_current_state(
            periods=periods,
            latest_period=latest_period,
            direction=direction,
            has_latest_resolution=has_latest_resolution,
            has_mitigation=has_mitigation,
            has_effect_visible=has_effect_visible,
            had_gap_then_returned=had_gap_then_returned,
        )
        mitigation = _mitigation_status(timeline)
        economic_status = _economic_impact_status(timeline)
        record = {
            "risk_theme_id": f"RG-{idx:04d}",
            "theme": theme,
            "risk_type": risk_type,
            "first_seen_period": periods[0] if periods else "",
            "latest_seen_period": periods[-1] if periods else "",
            "current_state": state,
            "direction": direction,
            "risk_description": _risk_description(theme, grouped),
            "economic_exposure": _economic_exposure(theme, risk_type),
            "timeline": timeline,
            "linked_strategy_theme_ids": _strategy_links(sources["strategy_gold"], theme, risk_type),
            "linked_management_promise_ids": [],
            "linked_capital_allocation_ids": _capital_links(sources["capital_allocation_gold"], theme, risk_type),
            "linked_project_ids": [],
            "mitigation_status": mitigation,
            "economic_impact_status": economic_status,
            "investor_interpretation": _investor_interpretation(theme, state, direction, mitigation, economic_status),
            "evidence_ids": list(dict.fromkeys(source_ids + [eid for event in timeline for eid in event.get("evidence_ids") or []]))[:12],
        }
        records.append(record)

    return sorted(
        records,
        key=lambda r: (
            0 if r["current_state"] in {"WORSENING", "REAPPEARED"} else 1,
            0 if r["current_state"] in {"RECURRING", "MITIGATION_STARTED", "MITIGATED"} else 1,
            -len(r.get("timeline") or []),
            r.get("theme") or "",
        ),
    )


def _summary(themes: List[Dict[str, Any]]) -> Dict[str, Any]:
    active = [t for t in themes if t["current_state"] not in {"RESOLVED", "NOT_RECONFIRMED"}]
    worsening = [t for t in themes if t["current_state"] == "WORSENING"]
    improving = [t for t in themes if t["current_state"] in {"IMPROVING", "MITIGATED", "RESOLVED"}]
    resolved = [t for t in themes if t["current_state"] == "RESOLVED"]
    top = active[:5]
    if top:
        current = "; ".join(f"{t['theme']} is {t['current_state'].lower().replace('_', ' ')}" for t in top[:4])
    else:
        current = "No material risk theme has sufficient evidence for a current risk profile."
    return {
        "current_risk_summary": current,
        "active_material_risks": len(active),
        "worsening_risks": len(worsening),
        "improving_risks": len(improving),
        "resolved_risks": len(resolved),
        "state_breakdown": dict(Counter(t["current_state"] for t in themes)),
    }


def _patterns(themes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    patterns: List[Dict[str, Any]] = []
    if any(t["current_state"] == "WORSENING" and t["risk_type"] == "working_capital" for t in themes):
        patterns.append({"pattern": "working_capital_deterioration", "description": "Working-capital risk is worsening on objective financial evidence."})
    recurring = [t for t in themes if t["current_state"] == "RECURRING"]
    if recurring:
        patterns.append({"pattern": "recurring_risks", "description": f"{len(recurring)} material risks recur across multiple periods."})
    mitigation_unresolved = [t for t in themes if t["mitigation_status"] in {"started", "completed_outcome_unproven"} and t["current_state"] != "RESOLVED"]
    if mitigation_unresolved:
        patterns.append({"pattern": "repeated_mitigation_without_resolution", "description": "Mitigation evidence exists, but risk resolution remains unproven."})
    if any(t.get("linked_strategy_theme_ids") for t in themes):
        patterns.append({"pattern": "strategy_created_or_strategy_linked_risk", "description": "Some risks link to documented strategy themes where risk evidence also exists."})
    if any(t.get("linked_capital_allocation_ids") for t in themes):
        patterns.append({"pattern": "capital_allocation_risk", "description": "Some risks link to capital allocation records where risk evidence also exists."})
    return patterns


def build_risk_evolution_timeline(
    company_slug: str,
    *,
    companies_root: Path | str = Path("companies"),
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    companies_root = Path(companies_root)
    sources = _load_sources(company_slug, companies_root)
    themes = _build_theme_records(sources)
    timeline = [
        {
            "risk_theme_id": theme["risk_theme_id"],
            "theme": theme["theme"],
            "period": event.get("period"),
            "event_type": event.get("event_type"),
            "evidence": event.get("evidence"),
            "evidence_ids": event.get("evidence_ids") or [],
        }
        for theme in themes
        for event in theme.get("timeline") or []
    ]
    worsening_or_recurring = [
        t for t in themes if t["current_state"] in {"WORSENING", "RECURRING", "REAPPEARED"}
    ]
    improving_or_resolved = [
        t for t in themes if t["current_state"] in {"IMPROVING", "MITIGATED", "RESOLVED"}
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "company_slug": company_slug,
        "generated_at": generated_at or _utc_now(),
        "summary": _summary(themes),
        "risk_themes": themes,
        "timeline": sorted(timeline, key=lambda e: (_period_sort_key(e.get("period")), e.get("risk_theme_id") or "")),
        "worsening_or_recurring": worsening_or_recurring,
        "improving_or_resolved": improving_or_resolved,
        "risk_patterns": _patterns(themes),
        "critical_follow_up": [_critical_follow_up(t) for t in themes[:8] if t["current_state"] != "RESOLVED"],
        "source_contract": {
            "repeated_disclosure_is_not_worsening": True,
            "silence_is_not_resolution": True,
            "mitigation_is_not_resolution": True,
            "financial_movement_is_not_causal_proof": True,
            "strategy_links_require_risk_evidence": True,
        },
    }


def write_risk_evolution_timeline(
    company_slug: str,
    *,
    companies_root: Path | str = Path("companies"),
    generated_at: Optional[str] = None,
) -> Path:
    companies_root = Path(companies_root)
    payload = build_risk_evolution_timeline(company_slug, companies_root=companies_root, generated_at=generated_at)
    out_dir = companies_root / company_slug / "company_memory" / "gold"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "risk_evolution_timeline.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path
