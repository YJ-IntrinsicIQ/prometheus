from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .contract import SCHEMA_VERSION, confidence, evidence_ref
from .evidence_adapter import ManagementProgressionSources, load_management_progression_sources, loaded_payload
from .linker import duplicate_key, link_company_model_ids, theme_key
from .validator import validate_management_progression


_GENERIC_LEGACY_PROGRESSIONS = {
    "business strategy",
    "capex - physical infrastructure",
    "capital investment in sustainability",
    "competitive positioning",
    "future outlook",
    "growth strategy",
    "market opportunity",
    "manufacturing & capability development",
    "manufacturing & testing facilities",
    "operational efficiency",
    "technology direction",
}

_GENERIC_PROGRESSIONS = _GENERIC_LEGACY_PROGRESSIONS | {
    "advance execution on a bounded business objective",
    "improve competitive positioning",
    "improve operating capability, control, or speed",
    "integrate a purchased asset or business",
    "pursue growth",
    "serve a specific customer or programme",
    "strengthen technology direction",
    "support execution capacity and delivery readiness",
}

_GENERIC_PROGRESSIVE_WORDS = {
    "advance",
    "bounded",
    "business",
    "capability",
    "capacity",
    "control",
    "deliver",
    "delivery",
    "development",
    "direction",
    "efficiency",
    "execution",
    "focus",
    "growth",
    "improve",
    "increase",
    "management",
    "objective",
    "operating",
    "operational",
    "positioning",
    "project",
    "readiness",
    "speed",
    "strengthen",
    "support",
}

_MATERIAL_ANCHOR_WORDS = {
    "3d",
    "acquisition",
    "ai",
    "api",
    "automation",
    "capex",
    "chamber",
    "commissioning",
    "customer",
    "defence",
    "defense",
    "design",
    "development",
    "emc",
    "enterprise",
    "facility",
    "build",
    "integration",
    "manufacturing",
    "platform",
    "product",
    "programme",
    "solution",
    "solutions",
    "qip",
    "radar",
    "rcs",
    "revenue",
    "satellite",
    "security",
    "software",
    "testing",
    "workflow",
    "aerospace",
}

_LOW_VALUE_NOISE_WORDS = {
    "administrative",
    "csr",
    "environmental",
    "fixtures",
    "furniture",
    "interiors",
    "iso",
    "office",
    "occupational",
    "scope",
    "sustainability",
}


def build_management_progression(company_slug: str, *, companies_root: Path | str = Path("companies"), generated_at: str | None = None) -> Dict[str, Any]:
    sources = load_management_progression_sources(company_slug, companies_root=companies_root)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return ManagementProgressionProducer(sources=sources, generated_at=generated_at).build()


def write_management_progression(company_slug: str, *, companies_root: Path | str = Path("companies"), generated_at: str | None = None) -> Dict[str, Path]:
    payload = build_management_progression(company_slug, companies_root=companies_root, generated_at=generated_at)
    validation = validate_management_progression(payload)
    output_dir = Path(companies_root) / company_slug / "company_memory" / "management_progression"
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "management_progression.json": output_dir / "management_progression.json",
        "management_progression_validation.json": output_dir / "management_progression_validation.json",
        "management_progression_manifest.json": output_dir / "management_progression_manifest.json",
    }
    paths["management_progression.json"].write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["management_progression_validation.json"].write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["management_progression_manifest.json"].write_text(json.dumps(payload["source_manifest"], indent=2, ensure_ascii=False), encoding="utf-8")
    if validation["status"] == "fail":
        raise ValueError(f"Management Progression validation failed for {company_slug}: {validation['errors']}")
    return paths


class ManagementProgressionProducer:
    def __init__(self, *, sources: ManagementProgressionSources, generated_at: str) -> None:
        self.sources = sources
        self.company_slug = sources.company_slug
        self.generated_at = generated_at
        self.company_model = loaded_payload(sources, "company_model")

    def build(self) -> Dict[str, Any]:
        events = self._collect_events()
        events = self._dedupe_events(events)
        items = self._group_events(events)
        if not _has_governed_progression_stream(items):
            items = []
        coverage = "supported" if len(items) >= 2 else "partial" if items else "insufficient_evidence"
        return {
            "schema_version": SCHEMA_VERSION,
            "company_slug": self.company_slug,
            "generated_at": self.generated_at,
            "coverage_status": coverage,
            "progression_items": items,
            "source_manifest": self._source_manifest(coverage),
        }

    def _collect_events(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        events.extend(self._events_from_commitments())
        events.extend(self._events_from_projects())
        events.extend(self._events_from_capacity())
        events.extend(self._events_from_commentary())
        events.extend(self._events_from_capital_allocation_outcomes())
        events.extend(self._events_from_legacy_strategy())
        events.extend(self._events_from_legacy_promises())
        events.extend(self._events_from_legacy_capital_allocation())
        return events

    def _events_from_commitments(self) -> List[Dict[str, Any]]:
        payload = loaded_payload(self.sources, "management_commitments")
        results = []
        for item in payload.get("commitments", []) or []:
            if not isinstance(item, dict):
                continue
            text = _pick(item, "normalized_commitment", "commitment", "topic", "title", "promise")
            text = _canonical_progression_text(text)
            if not _specific_enough(text) or _is_low_value_progression_text(text):
                continue
            period = _pick(item, "first_seen_period", "announcement_period", "source_period", "first_seen_year", "period")
            status = _pick(item, "latest_status", "delivery_status", "status") or "unresolved"
            evidence = _evidence_from_item(item, "company_memory/management_commitments/management_commitments.json", period)
            results.append(
                self._event(
                    event_id=_pick(item, "commitment_id", "promise_id", default=f"commitment_{len(results)+1}"),
                    role="commitment",
                    event_type=_event_type_from_text(text),
                    source_period=period,
                    event_period=period,
                    statement_text=text,
                    verification_status="unresolved" if _status_to_current(status) in {"announced", "unresolved"} else "partially_verified",
                    evidence=evidence,
                    stream_type="commitment",
                )
            )
        return results

    def _events_from_projects(self) -> List[Dict[str, Any]]:
        payload = loaded_payload(self.sources, "projects_registry")
        results = []
        for item in payload.get("projects", []) or []:
            if not isinstance(item, dict):
                continue
            name = _pick(item, "project_name", "normalized_name", "title", "name")
            description = _pick(item, "description", "business_rationale", "project_description") or name
            description = _canonical_progression_text(description)
            if not _specific_enough(description) or _is_low_value_progression_text(description):
                continue
            assessment = item.get("assessment") if isinstance(item.get("assessment"), dict) else {}
            period = _pick(item, "announcement_period", "source_period", "period", default=_pick(assessment, "period", "latest_period"))
            execution = _pick(assessment, "execution_status", default=_pick(item, "current_status", "status"))
            current = _status_to_current(execution)
            role = "completion" if current == "delivered" else "action"
            results.append(
                self._event(
                    event_id=_pick(item, "project_id", default=f"project_{len(results)+1}"),
                    role=role,
                    event_type="project_execution",
                    source_period=period,
                    event_period=period,
                    action_taken=description,
                    operational_outcome=_pick(assessment, "observed_business_effect", "execution_summary"),
                    financial_or_business_outcome=_pick(assessment, "observed_financial_effect"),
                    verification_status=_verification_from_current(current),
                    evidence=_evidence_from_item(item, "company_memory/projects/projects_registry.json", period),
                    stream_type="project",
                )
            )
        return results

    def _events_from_capacity(self) -> List[Dict[str, Any]]:
        payload = loaded_payload(self.sources, "capacity_registry")
        results = []
        for item in payload.get("capacity_items", []) or []:
            if not isinstance(item, dict):
                continue
            name = _pick(item, "capacity_name", "normalized_name", "capacity_type")
            name = _canonical_progression_text(name)
            if not _specific_enough(name) or _is_low_value_progression_text(name):
                continue
            assessment = item.get("capacity_assessment") if isinstance(item.get("capacity_assessment"), dict) else {}
            period = _pick(item, "announcement_period", "source_period", "period", default=_pick(assessment, "latest_period"))
            current = _status_to_current(_pick(assessment, "execution_status", default=_pick(item, "current_status", "status")))
            results.append(
                self._event(
                    event_id=_pick(item, "capacity_id", default=f"capacity_{len(results)+1}"),
                    role="milestone" if current in {"in_progress", "delivered", "partially_delivered"} else "action",
                    event_type="capacity_expansion",
                    source_period=period,
                    event_period=period,
                    action_taken=name,
                    operational_outcome=_pick(assessment, "observed_business_effect"),
                    financial_or_business_outcome=_pick(assessment, "observed_financial_effect"),
                    verification_status=_verification_from_current(current),
                    evidence=_evidence_from_item(item, "company_memory/capacity/capacity_registry.json", period),
                    stream_type="capacity",
                )
            )
        return results

    def _events_from_commentary(self) -> List[Dict[str, Any]]:
        payload = loaded_payload(self.sources, "commentary_themes")
        results = []
        for theme in (payload.get("commentary_themes") or payload.get("themes") or []):
            if not isinstance(theme, dict):
                continue
            title = _pick(theme, "theme_name", "theme_label", "title") or "Management commentary"
            for event in theme.get("commentary_events", []) or []:
                if not isinstance(event, dict):
                    continue
                description = _pick(event, "description", "commentary", "summary")
                description = _canonical_progression_text(description)
                if not _specific_enough(description) or _is_low_value_progression_text(description):
                    continue
                period = _pick(event, "period", "source_period")
                results.append(
                    self._event(
                        event_id=_pick(event, "event_id", default=f"commentary_{len(results)+1}"),
                        role="statement",
                        event_type="commentary_change",
                        source_period=period,
                        event_period=period,
                        statement_text=description,
                        verification_status="unresolved",
                        evidence=_evidence_from_item(event, "company_memory/management_commentary/commentary_themes.json", period),
                        stream_type="commentary",
                        theme_hint=title,
                    )
                )
        return results

    def _events_from_capital_allocation_outcomes(self) -> List[Dict[str, Any]]:
        payload = loaded_payload(self.sources, "capital_allocation_outcomes")
        results = []
        for item in payload.get("allocations", []) or []:
            if not isinstance(item, dict):
                continue
            name = _pick(item, "allocation_name", "capital_use", "title")
            name = _canonical_progression_text(name)
            if not _specific_enough(name) or _is_low_value_progression_text(name):
                continue
            periods = item.get("deployment_periods") or []
            period = str(periods[0]) if periods else _pick(item, "first_observed_period", "source_period", "period")
            results.append(
                self._event(
                    event_id=_pick(item, "allocation_id", default=f"capital_allocation_{len(results)+1}"),
                    role="outcome" if _pick(item, "financial_outcome", "business_outcome") else "action",
                    event_type="capital_deployment",
                    source_period=period,
                    event_period=period,
                    resolved_period=_pick(item, "latest_period"),
                    action_taken=name,
                    financial_or_business_outcome=_pick(item, "financial_outcome", "business_outcome", "balance_sheet_outcome"),
                    verification_status="partially_verified" if _pick(item, "financial_outcome", "business_outcome") else "unresolved",
                    evidence=_evidence_from_item(item, "company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json", period),
                    stream_type="capital_allocation",
                )
            )
        return results

    def _events_from_legacy_strategy(self) -> List[Dict[str, Any]]:
        payload = loaded_payload(self.sources, "strategy_timeline")
        results = []
        for row in payload.get("timeline", []) or []:
            if not isinstance(row, dict):
                continue
            period = _pick(row, "year")
            for item in row.get("management_focus", []) or []:
                if not isinstance(item, dict):
                    continue
                text = _pick(item, "value", "raw_label", "candidate_label")
                text = _canonical_progression_text(text)
                if not _specific_enough(text) or _is_generic_legacy_progression(text) or _is_low_value_progression_text(text):
                    continue
                results.append(
                    self._event(
                        event_id=_pick(item, "source_item_id", default=f"legacy_strategy_{len(results)+1}"),
                        role="action" if _pick(item, "normalized_status") == "completed" else "statement",
                        event_type="strategic_change",
                        source_period=period,
                        event_period=period,
                        statement_text=text if _pick(item, "normalized_status") != "completed" else "",
                        action_taken=text if _pick(item, "normalized_status") == "completed" else "",
                        verification_status="partially_verified" if _pick(item, "normalized_status") == "completed" else "unresolved",
                        evidence=_evidence_from_item(item, "company_memory/multi_year/strategy_timeline.json", period),
                        stream_type="legacy_strategy",
                    )
                )
        return results

    def _events_from_legacy_promises(self) -> List[Dict[str, Any]]:
        if loaded_payload(self.sources, "management_commitments").get("commitments"):
            return []
        payload = loaded_payload(self.sources, "promise_tracker")
        results = []
        for item in payload.get("promises", []) or []:
            if not isinstance(item, dict):
                continue
            text = _pick(item, "normalized_promise")
            text = _canonical_progression_text(text)
            if not _specific_enough(text) or _is_low_value_progression_text(text):
                continue
            period = _pick(item, "first_seen_year")
            results.append(
                self._event(
                    event_id=_pick(item, "promise_id", default=f"legacy_promise_{len(results)+1}"),
                    role="commitment",
                    event_type=_event_type_from_text(text),
                    source_period=period,
                    event_period=period,
                    statement_text=text,
                    verification_status="unresolved",
                    evidence=_evidence_from_item(item, "company_memory/multi_year/promise_tracker.json", period),
                    stream_type="legacy_promise",
                )
            )
        return results

    def _events_from_legacy_capital_allocation(self) -> List[Dict[str, Any]]:
        if loaded_payload(self.sources, "capital_allocation_outcomes").get("allocations"):
            return []
        payload = loaded_payload(self.sources, "capital_allocation_timeline")
        results = []
        for row in payload.get("timeline", []) or []:
            if not isinstance(row, dict):
                continue
            period = _pick(row, "year")
            for group in ("true_capital_deployment", "financing_actions", "shareholder_returns"):
                for item in row.get(group, []) or []:
                    if not isinstance(item, dict):
                        continue
                    text = _pick(item, "value", "category", "canonical_category")
                    text = _canonical_progression_text(text)
                    if not _specific_enough(text) or _is_low_value_progression_text(text):
                        continue
                    results.append(
                        self._event(
                            event_id=_pick(item, "source_item_id", default=f"legacy_capital_{len(results)+1}"),
                            role="action",
                            event_type="capital_deployment",
                            source_period=period,
                            event_period=period,
                            action_taken=text,
                            verification_status="partially_verified",
                            evidence=_evidence_from_item(item, "company_memory/multi_year/capital_allocation_timeline.json", period),
                            stream_type="legacy_capital_allocation",
                        )
                    )
        return results

    def _dedupe_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        deduped = []
        for event in events:
            markers = {duplicate_key(event), _validator_like_event_marker(event)}
            if seen & markers:
                continue
            seen.update(markers)
            deduped.append(event)
        return deduped

    def _group_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for event in events:
            key = theme_key(_event_primary_text(event) or _event_grouping_text(event))
            groups.setdefault(key, []).append(event)
        items = []
        for index, (key, grouped) in enumerate(sorted(groups.items()), start=1):
            grouped = sorted(grouped, key=lambda event: (_period_sort_key(event.get("event_period") or event.get("source_period")), event.get("event_id", "")))
            theme = _title_from_event(grouped[-1])
            stream_types = sorted(set(event.get("_stream_type") for event in grouped if event.get("_stream_type")))
            current = _derive_current_status(grouped)
            linked_ids = link_company_model_ids(" ".join(_event_grouping_text(event) for event in grouped), self.company_model)
            items.append(
                {
                    "item_id": f"MP-{index:04d}-{key[:40]}",
                    "theme": theme,
                    "linked_company_model_ids": linked_ids,
                    "stream_types": stream_types,
                    "current_status": current,
                    "management_credibility_signal": _management_credibility_signal(current, grouped),
                    "events": [_public_event(event) for event in grouped],
                    "investor_implication": _investor_implication(theme, grouped, current),
                    "unresolved": _unresolved_for(grouped, current),
                }
            )
        return sorted(items, key=lambda item: (-_materiality_score(item), item["item_id"]))[:25]

    def _event(self, *, event_id: str, role: str, event_type: str, source_period: str, event_period: str = "", target_period: str = "", resolved_period: str = "", actor: str = "management", statement_text: str = "", action_taken: str = "", operational_outcome: str = "", financial_or_business_outcome: str = "", verification_status: str = "unresolved", evidence: List[Dict[str, Any]] | None = None, stream_type: str = "", theme_hint: str = "") -> Dict[str, Any]:
        return {
            "event_id": event_id,
            "role": role,
            "event_type": event_type,
            "source_period": source_period,
            "event_period": event_period or source_period,
            "target_period": target_period,
            "resolved_period": resolved_period,
            "actor": actor,
            "statement_text": statement_text,
            "action_taken": action_taken,
            "operational_outcome": operational_outcome,
            "financial_or_business_outcome": financial_or_business_outcome,
            "verification_status": verification_status,
            "confidence": confidence("medium", basis=[stream_type or "source stream"]),
            "evidence": evidence or [],
            "_stream_type": stream_type,
            "_theme_hint": theme_hint,
        }

    def _source_manifest(self, coverage: str) -> Dict[str, Any]:
        return {
            "schema_version": "management_progression_manifest.v1",
            "company_slug": self.company_slug,
            "generated_at": self.generated_at,
            "coverage_status": coverage,
            "sources_used": self.sources.source_files_found,
            "sources_missing": self.sources.source_files_missing,
            "legacy_adapter_used": self.sources.legacy_adapter_used,
            "legacy_adapter_sources": self.sources.legacy_adapter_sources,
            "legacy_adapter_sunset_condition": "Delete once dedicated Management Progression streams cover commitments, strategy, capital allocation, risks, and downstream consumers stop reading legacy multi_year artifacts.",
            "company_mismatch_errors": self.sources.warnings,
        }


def _public_event(event: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in event.items() if not key.startswith("_")}


def _has_governed_progression_stream(items: List[Dict[str, Any]]) -> bool:
    governed_streams = {"commitment", "project", "capacity", "commentary", "capital_allocation"}
    for item in items:
        if governed_streams & set(item.get("stream_types") or []):
            return True
    return False


def _validator_like_event_marker(event: Dict[str, Any]) -> str:
    return "|".join(
        [
            str(event.get("role") or ""),
            str(event.get("event_type") or ""),
            str(event.get("source_period") or ""),
            str(event.get("event_period") or ""),
            " ".join(str(event.get("statement_text") or event.get("action_taken") or event.get("operational_outcome") or "").lower().split())[:180],
        ]
    )


def _event_text(event: Dict[str, Any]) -> str:
    return " ".join(str(event.get(key) or "") for key in ("_theme_hint", "statement_text", "action_taken", "operational_outcome", "financial_or_business_outcome"))


def _event_primary_text(event: Dict[str, Any]) -> str:
    return _canonical_progression_text(
        event.get("statement_text")
        or event.get("action_taken")
        or event.get("operational_outcome")
        or event.get("financial_or_business_outcome")
    )


def _event_grouping_text(event: Dict[str, Any]) -> str:
    primary = " ".join(str(event.get(key) or "") for key in ("statement_text", "action_taken", "operational_outcome", "financial_or_business_outcome"))
    cleaned = _canonical_progression_text(primary)
    if cleaned:
        return cleaned
    return _canonical_progression_text(_event_text(event))


def _title_from_event(event: Dict[str, Any]) -> str:
    text = _event_primary_text(event) or _event_grouping_text(event)
    return _truncate(text, 96) or "Management progression item"


def _investor_implication(theme: str, events: List[Dict[str, Any]], current: str) -> Dict[str, Any]:
    has_outcome = any(event.get("operational_outcome") or event.get("financial_or_business_outcome") for event in events)
    unresolved = current in {"announced", "in_progress", "unresolved", "historical_context"} or not has_outcome
    if unresolved:
        conclusion = f"{theme} is visible, but outcome evidence remains incomplete."
        impact = "unresolved"
    elif current in {"delivered", "partially_delivered"}:
        conclusion = f"{theme} shows evidence of follow-through, but economic value still depends on later utilization or returns."
        impact = "neutral"
    elif current in {"failed", "abandoned", "reversed"}:
        conclusion = f"{theme} weakens execution confidence because later evidence points away from the original direction."
        impact = "weakens"
    else:
        conclusion = f"{theme} remains a management progression item under observation."
        impact = "unresolved"
    return {
        "conclusion": conclusion,
        "economic_mechanism": "Investor conviction should move only when management action creates observable operating capability, utilization, customer adoption, cash generation, or returns.",
        "thesis_impact": impact,
        "confidence": confidence("medium" if events else "low", basis=["deterministic progression assembly"]),
        "what_to_watch": ["Later operating outcome evidence", "Financial payoff or cash conversion", "Whether management updates remain consistent with the original claim"],
    }


def _unresolved_for(events: List[Dict[str, Any]], current: str) -> List[Dict[str, Any]]:
    questions = []
    if current in {"announced", "in_progress", "unresolved", "historical_context"}:
        questions.append("Has management converted this statement or action into verified operating results?")
    if not any(event.get("financial_or_business_outcome") for event in events):
        questions.append("What financial or business outcome followed this progression?")
    return [
        {
            "question": question,
            "why_it_matters": "The distinction between intention, execution, and economic outcome determines management credibility.",
            "disconfirming_evidence_needed": "Later evidence showing delivery, abandonment, reversal, utilization, or financial payoff.",
        }
        for question in questions[:3]
    ]


def _derive_current_status(events: List[Dict[str, Any]]) -> str:
    roles = {event.get("role") for event in events}
    verifications = {event.get("verification_status") for event in events}
    if "reversal" in roles:
        return "reversed"
    if "abandonment" in roles:
        return "abandoned"
    if "contradicted" in verifications:
        return "failed"
    if "completion" in roles or "outcome" in roles:
        return "partially_delivered" if "partially_verified" in verifications else "delivered"
    if "action" in roles or "milestone" in roles:
        return "in_progress"
    if "commitment" in roles or "statement" in roles:
        return "announced"
    return "unresolved"


def _management_credibility_signal(current: str, events: List[Dict[str, Any]]) -> str:
    if current == "delivered":
        return "DELIVERED"
    if current == "partially_delivered":
        return "PARTIALLY_DELIVERED"
    if current == "in_progress":
        return "IN_PROGRESS"
    if current == "failed":
        return "CONTRADICTED"
    if current == "abandoned":
        return "ABANDONED"
    if current == "reversed":
        return "SUPERSEDED"
    if any(event.get("role") in {"commitment", "statement"} for event in events):
        return "UNABLE_TO_VERIFY"
    return "UNABLE_TO_VERIFY"


def _status_to_current(status: Any) -> str:
    text = str(status or "").lower()
    if any(token in text for token in ("delivered", "completed", "commissioned", "fulfilled", "implemented")):
        return "delivered"
    if any(token in text for token in ("partial", "early", "progress")):
        return "partially_delivered"
    if any(token in text for token in ("under", "ongoing", "construction", "in_progress", "deployed")):
        return "in_progress"
    if any(token in text for token in ("failed", "negative", "delayed")):
        return "failed"
    if any(token in text for token in ("abandon", "dropped")):
        return "abandoned"
    return "unresolved"


def _verification_from_current(status: str) -> str:
    if status == "delivered":
        return "verified"
    if status in {"in_progress", "partially_delivered"}:
        return "partially_verified"
    if status in {"failed", "reversed"}:
        return "contradicted"
    return "unresolved"


def _event_type_from_text(text: str) -> str:
    lowered = str(text or "").lower()
    if any(token in lowered for token in ("capacity", "facility", "plant", "manufacturing")):
        return "capacity_expansion"
    if any(token in lowered for token in ("launch", "product", "platform", "catalogue", "catalog")):
        return "product_launch"
    if any(token in lowered for token in ("capex", "investment", "debt", "loan", "acquisition", "dividend")):
        return "capital_deployment"
    return "strategic_change"


def _evidence_from_item(item: Dict[str, Any], artifact: str, period: str) -> List[Dict[str, Any]]:
    ids = []
    for key in ("evidence_ids", "related_evidence_ids"):
        ids.extend(str(value) for value in item.get(key, []) or [] if str(value).strip())
    refs = item.get("source_references") or item.get("evidence_references") or []
    for ref in refs:
        if isinstance(ref, dict):
            ids.extend(str(value) for value in ref.get("evidence_ids", []) or [] if str(value).strip())
    excerpt = _pick(item, "value", "description", "normalized_commitment", "project_name", "capacity_name", "allocation_name", "risk_name", "commentary")
    if not ids:
        return [evidence_ref(source_artifact=artifact, source_period=period, source_item_id=_pick(item, "source_item_id", "project_id", "capacity_id"), excerpt=_truncate(excerpt, 220))]
    return [
        evidence_ref(source_artifact=artifact, source_period=period, evidence_id=ids[0], source_item_id=_pick(item, "source_item_id", "project_id", "capacity_id"), excerpt=_truncate(excerpt, 220))
    ]


def _specific_enough(text: Any) -> bool:
    words = _specific_progression_words(_canonical_progression_text(text))
    return len(words) >= 2 and (_has_material_anchor(text) or len(words) >= 4)


def _is_generic_legacy_progression(text: Any) -> bool:
    normalized = " ".join(str(text or "").lower().replace("—", "-").split())
    return normalized in _GENERIC_LEGACY_PROGRESSIONS


def _canonical_progression_text(text: Any) -> str:
    cleaned = " ".join(str(text or "").replace("—", "-").split())
    if not cleaned:
        return ""
    for wrapper in (
        "advance execution on a bounded business objective",
        "support execution capacity and delivery readiness",
        "improve operating capability, control, or speed",
        "strengthen technology direction",
        "pursue growth",
        "improve competitive positioning",
        "integrate a purchased asset or business",
        "extend the product set or system capability",
        "serve a specific customer or programme",
    ):
        cleaned = re.sub(
            rf"(?i)^{re.escape(wrapper)}(?: at .*?)? to deliver\s+",
            "",
            cleaned,
        )
    cleaned = re.sub(r"(?i)\s+at not specified\s+", " ", cleaned)
    return cleaned.strip(" -:;,.")


def _specific_progression_words(text: Any) -> List[str]:
    return [
        word
        for word in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(word) >= 4 and word not in _GENERIC_PROGRESSIVE_WORDS
    ]


def _has_material_anchor(text: Any) -> bool:
    lowered = str(text or "").lower()
    words = set(re.findall(r"[a-z0-9]+", lowered))
    if words & _MATERIAL_ANCHOR_WORDS:
        return True
    if re.search(r"\b[A-Z][A-Za-z0-9]*(?:[A-Z][A-Za-z0-9]*)+\b", str(text or "")):
        return True
    if re.search(r"\b(?:inr|rs\.?)\s*[\d,.]+", lowered):
        return True
    return False


def _is_low_value_progression_text(text: Any) -> bool:
    cleaned = _canonical_progression_text(text)
    lowered = cleaned.lower()
    if not cleaned:
        return True
    if lowered in _GENERIC_PROGRESSIONS:
        return True
    words = set(re.findall(r"[a-z0-9]+", lowered))
    if "cwip" in words and not (words & {"facility", "manufacturing", "testing", "plant", "capacity"}):
        return True
    if words & _LOW_VALUE_NOISE_WORDS and not (words & _MATERIAL_ANCHOR_WORDS):
        return True
    if not _has_material_anchor(cleaned) and len(_specific_progression_words(cleaned)) < 4:
        return True
    return False


def _materiality_score(item: Dict[str, Any]) -> int:
    score = len(item.get("events") or [])
    score += len(item.get("linked_company_model_ids") or []) * 2
    text = " ".join([str(item.get("theme") or ""), " ".join(_event_grouping_text(event) for event in item.get("events") or [])])
    anchor_count = len(set(re.findall(r"[a-z0-9]+", text.lower())) & _MATERIAL_ANCHOR_WORDS)
    score += min(anchor_count, 5) * 2
    stream_types = set(item.get("stream_types") or [])
    if "commitment" in stream_types:
        score += 8
    if "legacy_promise" in stream_types:
        score += 6
    score += 4 if {"project", "capacity"} & stream_types else 0
    score += 3 if {"capital_allocation"} & set(item.get("stream_types") or []) and _has_material_anchor(text) else 0
    score += 2 if item.get("current_status") in {"delivered", "partially_delivered", "failed"} else 0
    if item.get("current_status") == "announced" and not any(event.get("operational_outcome") or event.get("financial_or_business_outcome") for event in item.get("events") or []):
        score -= 3
    if _is_low_value_progression_text(text):
        score -= 6
    return score


def _pick(mapping: Dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", []):
            return " ".join(str(value).split())
    return default


def _truncate(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _period_sort_key(period: Any) -> int:
    match = re.search(r"(\d{2,4})", str(period or "").lower())
    if not match:
        return -1
    value = int(match.group(1))
    return value % 100 if value >= 100 else value


def main(argv: Optional[List[str]] = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build canonical Management Progression v1 artifacts.")
    parser.add_argument("company")
    parser.add_argument("--companies-root", default="companies")
    args = parser.parse_args(argv)
    for name, path in write_management_progression(args.company, companies_root=Path(args.companies_root)).items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
