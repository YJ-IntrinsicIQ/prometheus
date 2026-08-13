from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence


def _should_keep_semantic_item(item: Dict[str, Any]) -> bool:
    relevance = item.get("semantic_relevance") or {}
    period = item.get("period_resolution") or {}
    materiality = item.get("progression_materiality") or {}
    if isinstance(relevance, dict) and relevance.get("quarantine"):
        return False
    if isinstance(period, dict) and str(period.get("status") or "").upper() in {"INVALID", "AMBIGUOUS", "OUTSIDE_ANALYSIS_WINDOW", "HISTORICAL_CONTEXT"}:
        return False
    if isinstance(materiality, dict) and not materiality.get("should_promote", True):
        return False
    return True


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").split())


def _first_text(*values: Any) -> str:
    for value in values:
        text = " ".join(str(value or "").split()).strip()
        if text:
            return text
    return ""


def _coalesce_period(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip().lower()
        if text:
            return text
    return ""


def _refs(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    refs = item.get("source_references") or []
    return [ref for ref in refs if isinstance(ref, dict)]


def _evidence(
    *,
    source_stream: str,
    source_item_id: Any,
    period: str,
    evidence_type: str,
    direction: str,
    relevance: str,
    confidence: str,
    summary: str,
    dimensions: Sequence[str],
    polarity: str,
    source_references: Sequence[Dict[str, Any]],
    turning_point: bool = False,
    source_label: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "source_stream": source_stream,
        "source_item_id": str(source_item_id or "").strip(),
        "period": period,
        "evidence_type": evidence_type,
        "direction": direction,
        "relevance": relevance,
        "confidence": confidence,
        "summary": summary,
        "dimensions": list(dict.fromkeys([str(item) for item in dimensions if str(item).strip()])),
        "polarity": polarity,
        "source_references": list(source_references),
        "turning_point": turning_point,
    }
    if source_label:
        payload["source_label"] = source_label
    return payload


def _status_polarity(status: str, positive: Sequence[str], negative: Sequence[str], mixed: Sequence[str] = ()) -> str:
    text = _normalize_text(status)
    if any(term in text for term in positive):
        return "positive"
    if any(term in text for term in negative):
        return "negative"
    if any(term in text for term in mixed):
        return "mixed"
    return "neutral"


def _direction_from_polarity(polarity: str) -> str:
    return {
        "positive": "improving",
        "negative": "deteriorating",
        "mixed": "mixed",
        "neutral": "unclear",
    }.get(polarity, "unclear")


def extract_commitment_evidence(commitments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for commitment in commitments:
        status = _first_text(commitment.get("status"), commitment.get("delivery_assessment"))
        polarity = _status_polarity(
            status,
            positive=("delivered", "partially delivered", "fulfilled", "on track", "completed"),
            negative=("delayed", "abandoned", "superseded", "unable to verify", "not delivered"),
            mixed=("in progress", "partially", "ongoing"),
        )
        evidence.append(
            _evidence(
                source_stream="management_commitments",
                source_item_id=commitment.get("id"),
                period=_coalesce_period(commitment.get("announcement_period"), commitment.get("latest_period")),
                evidence_type=f"commitment_{_normalize_text(status or commitment.get('category') or 'unknown').replace(' ', '_') or 'unknown'}",
                direction=_direction_from_polarity(polarity),
                relevance="high" if commitment.get("category") in {"Capacity", "Capex", "Manufacturing", "Financial Target", "Growth"} else "medium",
                confidence=str((commitment.get("confidence") or {}).get("level") or "medium").lower() if isinstance(commitment.get("confidence"), dict) else "medium",
                summary=_first_text(commitment.get("normalized_commitment"), commitment.get("topic"), commitment.get("original_statement")),
                dimensions=(
                    "execution_discipline",
                    "strategic_clarity",
                    "adaptability" if polarity in {"negative", "mixed"} else "candor_and_consistency" if polarity == "positive" else "execution_discipline",
                ),
                polarity=polarity,
                source_references=_refs(commitment),
                turning_point=bool(commitment.get("progression", {}).get("turning_points")),
                source_label=commitment.get("category"),
            )
        )
    return evidence


def extract_project_evidence(projects: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for project in projects:
        if not _should_keep_semantic_item(project):
            continue
        status = _first_text(project.get("current_status"), project.get("assessment", {}).get("execution_status"), project.get("progression_summary", {}).get("current_state"))
        polarity = _status_polarity(
            status,
            positive=("commissioned", "operational", "partially operational", "under execution", "completed"),
            negative=("delayed", "cancelled", "abandoned", "paused", "unable to verify"),
            mixed=("planning", "funded", "in progress"),
        )
        evidence.append(
            _evidence(
                source_stream="projects",
                source_item_id=project.get("project_id"),
                period=_coalesce_period(project.get("announcement_period"), project.get("latest_period")),
                evidence_type=f"project_{_normalize_text(status or project.get('project_type') or 'unknown').replace(' ', '_') or 'unknown'}",
                direction=_direction_from_polarity(polarity),
                relevance="high" if project.get("current_status") in {"commissioned", "operational", "delayed", "cancelled"} else "medium",
                confidence=str((project.get("confidence") or {}).get("level") or "medium").lower() if isinstance(project.get("confidence"), dict) else "medium",
                summary=_first_text(project.get("project_name"), project.get("objective"), project.get("business_rationale"), project.get("economic_relevance")),
                dimensions=("execution_discipline", "strategic_clarity", "adaptability"),
                polarity=polarity,
                source_references=_refs(project),
                turning_point=bool(project.get("progression", {}).get("turning_points")),
                source_label=project.get("project_type"),
            )
        )
    return evidence


def extract_capacity_evidence(capacity_items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for capacity in capacity_items:
        if not _should_keep_semantic_item(capacity):
            continue
        status = _first_text(capacity.get("current_status"), capacity.get("capacity_assessment", {}).get("execution_status"), capacity.get("utilization_assessment", {}).get("utilization_status"))
        utilization = _first_text(capacity.get("utilization_status"), capacity.get("utilization_assessment", {}).get("utilization_status"))
        polarity = _status_polarity(
            f"{status} {utilization}",
            positive=("operational", "commissioned", "materially utilized", "partially utilized", "ramping"),
            negative=("underutilized", "delayed", "paused", "cancelled", "unable to verify"),
            mixed=("installed", "planned", "funded", "unclear"),
        )
        evidence.append(
            _evidence(
                source_stream="capacity",
                source_item_id=capacity.get("capacity_id"),
                period=_coalesce_period(capacity.get("announcement_period"), capacity.get("latest_period")),
                evidence_type=f"capacity_{_normalize_text(status or utilization or capacity.get('capacity_type') or 'unknown').replace(' ', '_') or 'unknown'}",
                direction=_direction_from_polarity(polarity),
                relevance="high" if capacity.get("current_status") in {"operational", "commissioned", "underutilized", "delayed"} or utilization in {"materially utilized", "underutilized"} else "medium",
                confidence=str((capacity.get("confidence") or {}).get("level") or "medium").lower() if isinstance(capacity.get("confidence"), dict) else "medium",
                summary=_first_text(capacity.get("capacity_name"), capacity.get("purpose"), capacity.get("economic_relevance")),
                dimensions=("execution_discipline", "strategic_clarity", "owner_alignment", "adaptability"),
                polarity=polarity,
                source_references=_refs(capacity),
                turning_point=bool(capacity.get("progression_summary")),
                source_label=capacity.get("capacity_type"),
            )
        )
    return evidence


def extract_risk_evidence(risks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for risk in risks:
        status = _first_text(risk.get("current_status"), risk.get("risk_assessment", {}).get("risk_status"), risk.get("status"))
        mitigation = _first_text(*(item.get("mitigation_action") for item in risk.get("mitigations", []) if isinstance(item, dict)))
        polarity = _status_polarity(
            f"{status} {mitigation}",
            positive=("mitigated", "resolved", "reducing"),
            negative=("persistent", "increasing", "recurring", "contradictory"),
            mixed=("stable", "emerging"),
        )
        evidence.append(
            _evidence(
                source_stream="risks",
                source_item_id=risk.get("risk_id"),
                period=_coalesce_period(risk.get("first_observed_period"), risk.get("latest_period")),
                evidence_type=f"risk_{_normalize_text(status or risk.get('risk_category') or 'unknown').replace(' ', '_') or 'unknown'}",
                direction=_direction_from_polarity(polarity),
                relevance="high" if risk.get("materiality", {}).get("level") in {"high", "medium"} or status in {"persistent", "increasing", "recurring", "mitigated", "resolved"} else "medium",
                confidence=str((risk.get("confidence") or {}).get("level") or "medium").lower() if isinstance(risk.get("confidence"), dict) else "medium",
                summary=_first_text(risk.get("risk_name"), risk.get("risk_mechanism"), risk.get("progression_summary")),
                dimensions=("risk_handling", "candor_and_consistency", "adaptability"),
                polarity=polarity,
                source_references=_refs(risk),
                turning_point=bool(risk.get("mitigations")),
                source_label=risk.get("risk_category"),
            )
        )
    return evidence


def extract_commentary_evidence(themes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for theme in themes:
        if not _should_keep_semantic_item(theme):
            continue
        position = _first_text(theme.get("current_position"), theme.get("consistency_assessment", {}).get("consistency_status"), theme.get("evidence_alignment", {}).get("alignment_status"))
        polarity = _status_polarity(
            position,
            positive=("strengthened", "stable_priority", "increasing_priority", "revised", "aligned"),
            negative=("contradicted", "dropped_without_follow_up", "softened"),
            mixed=("newly_introduced", "unresolved", "unable_to_verify"),
        )
        evidence.append(
            _evidence(
                source_stream="management_commentary",
                source_item_id=theme.get("theme_id"),
                period=_coalesce_period(theme.get("first_observed_period"), theme.get("latest_period")),
                evidence_type=f"commentary_{_normalize_text(position or theme.get('theme_category') or 'unknown').replace(' ', '_') or 'unknown'}",
                direction=_direction_from_polarity(polarity),
                relevance="high" if theme.get("theme_category") in {"strategy", "execution", "risk", "capital_allocation", "capacity", "growth"} else "medium",
                confidence=str((theme.get("confidence") or {}).get("level") or "medium").lower() if isinstance(theme.get("confidence"), dict) else "medium",
                summary=_first_text(theme.get("theme_name"), theme.get("current_emphasis"), theme.get("progression_summary", {}).get("what_changed")),
                dimensions=("candor_and_consistency", "strategic_clarity", "adaptability"),
                polarity=polarity,
                source_references=_refs(theme),
                turning_point=bool(theme.get("progression_summary", {}).get("what_changed")),
                source_label=theme.get("theme_category"),
            )
        )
    return evidence


def extract_capital_allocation_evidence(allocations: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for allocation in allocations:
        outcome = _first_text(allocation.get("outcome_status"), allocation.get("operating_outcome"), allocation.get("financial_outcome"), allocation.get("per_share_outcome"))
        polarity = _status_polarity(
            outcome,
            positive=("clearly observed", "early evidence", "partially observed", "positive", "improving", "benefit"),
            negative=("negative outcome", "unclear", "not yet observable", "pressure", "negative"),
            mixed=("partially", "early", "uncertain"),
        )
        evidence.append(
            _evidence(
                source_stream="capital_allocation_outcomes",
                source_item_id=allocation.get("allocation_id"),
                period=_coalesce_period(*(allocation.get("deployment_periods") or []), allocation.get("latest_period")),
                evidence_type=f"capital_outcome_{_normalize_text(outcome or allocation.get('allocation_category') or 'unknown').replace(' ', '_') or 'unknown'}",
                direction=_direction_from_polarity(polarity),
                relevance="high" if allocation.get("outcome_status") in {"clearly_observed", "negative_outcome"} else "medium",
                confidence=str((allocation.get("confidence") or {}).get("level") or "medium").lower() if isinstance(allocation.get("confidence"), dict) else "medium",
                summary=_first_text(allocation.get("allocation_name"), allocation.get("stated_rationale"), allocation.get("progression_summary")),
                dimensions=("capital_allocation_discipline", "evidence_confidence"),
                polarity=polarity,
                source_references=_refs(allocation),
                turning_point=bool(allocation.get("return_evidence")),
                source_label=allocation.get("allocation_category"),
            )
        )
    return evidence


def extract_owner_earnings_evidence(bridges: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    ordered = sorted(bridges, key=lambda item: str(item.get("fiscal_year") or "").lower())
    previous = None
    for bridge in ordered:
        current = bridge.get("owner_earnings_estimate")
        conservative = bridge.get("conservative_fcf_after_total_capex")
        polarity = "neutral"
        direction = "unclear"
        if current is not None or conservative is not None:
            if previous is not None and current is not None and isinstance(previous, (int, float)) and isinstance(current, (int, float)):
                if current > previous:
                    polarity = "positive"
                    direction = "improving"
                elif current < previous:
                    polarity = "negative"
                    direction = "deteriorating"
                else:
                    polarity = "neutral"
                    direction = "stable"
            elif current is not None and isinstance(current, (int, float)):
                polarity = "positive" if current >= 0 else "negative"
                direction = "improving" if current >= 0 else "deteriorating"
            elif conservative is not None and isinstance(conservative, (int, float)):
                polarity = "positive" if conservative >= 0 else "negative"
                direction = "improving" if conservative >= 0 else "deteriorating"
        evidence.append(
            _evidence(
                source_stream="owner_earnings",
                source_item_id=bridge.get("fiscal_year"),
                period=str(bridge.get("fiscal_year") or "").lower(),
                evidence_type="owner_earnings_bridge",
                direction=direction,
                relevance="high" if bridge.get("owner_earnings_precision_status") in {"usable", "high", "medium"} else "medium",
                confidence=str(bridge.get("owner_earnings_precision_status") or "low").lower() if str(bridge.get("owner_earnings_precision_status") or "").strip() else "low",
                summary=_first_text(f"Owner earnings {bridge.get('fiscal_year')}", bridge.get("owner_earnings_precision_status"), bridge.get("maintenance_growth_split_status")),
                dimensions=("capital_allocation_discipline", "owner_alignment", "evidence_confidence"),
                polarity=polarity,
                source_references=[
                    {"source_artifact": "owner_earnings_bridge.json", "source_item_id": bridge.get("fiscal_year"), "period": bridge.get("fiscal_year")}
                ],
                source_label="owner_earnings_bridge",
            )
        )
        previous = current if isinstance(current, (int, float)) else previous
    return evidence


def extract_per_share_evidence(analysis: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    ordered = sorted(analysis, key=lambda item: str(item.get("fiscal_year") or "").lower())
    previous_eps = None
    previous_shares = None
    for item in ordered:
        eps = item.get("eps_basic")
        shares = item.get("closing_shares") or item.get("weighted_average_basic_shares")
        polarity = "neutral"
        direction = "unclear"
        summary = _first_text(f"Per-share compounding {item.get('fiscal_year')}", item.get("per_share_compounding_status"), item.get("dilution_status"))
        if isinstance(eps, (int, float)) and previous_eps is not None:
            if eps > previous_eps:
                polarity = "positive"
                direction = "improving"
            elif eps < previous_eps:
                polarity = "negative"
                direction = "deteriorating"
            else:
                direction = "stable"
        if isinstance(shares, (int, float)) and previous_shares is not None:
            if shares < previous_shares and polarity != "negative":
                polarity = "positive"
                direction = "improving"
            elif shares > previous_shares:
                polarity = "negative" if polarity != "positive" else "mixed"
                direction = "deteriorating"
        if str(item.get("dilution_status") or "").lower() in {"dilutive", "comparability_partial"} and polarity == "positive":
            polarity = "mixed"
        evidence.append(
            _evidence(
                source_stream="per_share_compounding",
                source_item_id=item.get("fiscal_year"),
                period=str(item.get("fiscal_year") or "").lower(),
                evidence_type="per_share_compounding",
                direction=direction,
                relevance="high" if item.get("per_share_compounding_status") in {"usable", "strong"} else "medium",
                confidence=str(item.get("fcf_per_share_confidence") or item.get("per_share_compounding_status") or "low").lower(),
                summary=summary,
                dimensions=("owner_alignment", "capital_allocation_discipline", "evidence_confidence"),
                polarity=polarity,
                source_references=[{"source_artifact": "per_share_compounding_analysis.json", "source_item_id": item.get("fiscal_year"), "period": item.get("fiscal_year")}],
                source_label="per_share_compounding_analysis",
            )
        )
        previous_eps = eps if isinstance(eps, (int, float)) else previous_eps
        previous_shares = shares if isinstance(shares, (int, float)) else previous_shares
    return evidence


def extract_financial_truth_evidence(financial_truth: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    if not financial_truth:
        return evidence
    level = _first_text(financial_truth.get("financial_panel_status"), financial_truth.get("financial_panel_status_reason"))
    polarity = _status_polarity(level, positive=("usable", "pass", "ready"), negative=("blocked", "fail"), mixed=("partial", "limited"))
    evidence.append(
        _evidence(
            source_stream="financial_truth",
            source_item_id="financial_truth_pack",
            period=_coalesce_period(*(financial_truth.get("years_covered") or [])),
            evidence_type="financial_truth_pack",
            direction=_direction_from_polarity(polarity),
            relevance="medium",
            confidence="medium",
            summary=_first_text("Financial truth pack", financial_truth.get("financial_panel_status_reason")),
            dimensions=("evidence_confidence", "owner_alignment"),
            polarity=polarity,
            source_references=[{"source_artifact": "financial_truth_pack.json", "source_item_id": "financial_truth_pack", "period": _coalesce_period(*(financial_truth.get("years_covered") or []))}],
            source_label="financial_truth_pack",
        )
    )
    return evidence


def extract_investor_panel_evidence(panel_payload: Dict[str, Any] | None, company_slug: str) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    if not isinstance(panel_payload, dict):
        return evidence
    summary = _first_text(panel_payload.get("overall_committee_view", {}).get("summary"), panel_payload.get("executive_committee_summary"))
    if summary:
        evidence.append(
            _evidence(
                source_stream="investor_panel",
                source_item_id="committee_synthesis",
                period=_coalesce_period(*(panel_payload.get("years_considered") or [])),
                evidence_type="committee_synthesis",
                direction=_direction_from_polarity(_status_polarity(summary, positive=("strength", "clear", "aligned"), negative=("risk", "weak", "concern", "tension"))),
                relevance="medium",
                confidence="medium",
                summary=summary,
                dimensions=("candor_and_consistency", "strategic_clarity", "evidence_confidence"),
                polarity="neutral",
                source_references=[{"source_artifact": "committee_synthesis.json", "source_item_id": "overall_committee_view", "period": _coalesce_period(*(panel_payload.get("years_considered") or []))}],
                source_label="committee_synthesis",
            )
        )
    return evidence


def build_management_quality_evidence(sources: Dict[str, Any], *, company_slug: str) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    evidence.extend(extract_commitment_evidence(sources.get("commitments") or []))
    evidence.extend(extract_project_evidence(sources.get("projects") or []))
    evidence.extend(extract_capacity_evidence(sources.get("capacity") or []))
    evidence.extend(extract_risk_evidence(sources.get("risks") or []))
    evidence.extend(extract_commentary_evidence(sources.get("commentary") or []))
    evidence.extend(extract_capital_allocation_evidence(sources.get("capital_allocation_outcomes") or []))
    evidence.extend(extract_owner_earnings_evidence(sources.get("owner_earnings") or []))
    evidence.extend(extract_per_share_evidence(sources.get("per_share_compounding") or []))
    evidence.extend(extract_financial_truth_evidence(sources.get("financial_truth") or {}))

    stream_order = {
        "management_commitments": 0,
        "projects": 1,
        "capacity": 2,
        "risks": 3,
        "management_commentary": 4,
        "capital_allocation_outcomes": 5,
        "owner_earnings": 6,
        "per_share_compounding": 7,
        "financial_truth": 8,
    }
    evidence = sorted(
        evidence,
        key=lambda item: (
            item.get("period") or "",
            stream_order.get(str(item.get("source_stream") or ""), 99),
            str(item.get("source_item_id") or ""),
            str(item.get("evidence_type") or ""),
        ),
    )
    for index, item in enumerate(evidence, start=1):
        item["evidence_id"] = f"MQE-{index:04d}"
    return evidence
