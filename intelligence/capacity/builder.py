from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from knowledge.company_memory import parse_financial_year

from .classifier import capacity_similarity, sanitize_public_text, _compact_lower, _normalize_text
from .contracts import CAPACITY_GENERATOR_VERSION, CAPACITY_MANIFEST_SCHEMA_VERSION, CAPACITY_SCHEMA_VERSION
from .economic_impact import assess_capacity_impact
from .manifest import build_capacity_manifest
from .normalizer import normalize_candidate, _year_label
from .paths import (
    get_capacity_dir,
    get_capacity_assessments_path,
    get_capacity_manifest_path,
    get_capacity_registry_path,
    get_capacity_timelines_path,
    get_capacity_validation_path,
)
from .progression import CapacityProgressionAdapter, build_capacity_event, build_timeline
from .utilization import assess_utilization
from .validators import validate_capacity_payload
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


def _candidate_sources(year_dir: Path) -> List[Tuple[str, Path]]:
    return [
        ("clean_capacity", Path("extracted") / "clean_capacity.json"),
        ("clean_projects", Path("extracted") / "clean_projects.json"),
        ("company_intelligence", Path("intelligence") / "company_intelligence.json"),
        ("management_summary", Path("intelligence") / "management_summary.json"),
    ]


def _load_year_record(year_dir: Path) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "year": year_dir.name,
        "sort_key": parse_financial_year(year_dir.name),
        "paths": {"year_root": str(year_dir)},
        "source_artifacts": {},
    }
    for source_name, rel_path in _candidate_sources(year_dir):
        path = year_dir / rel_path
        payload = _load_json(path)
        found = bool(payload)
        record["source_artifacts"][source_name] = {"path": str(path), "found": found}
        record[source_name] = payload if isinstance(payload, (dict, list)) else {}
    return record


def _load_company_memory_payload(path: Path) -> Dict[str, Any]:
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


def _load_related_projects(company_root: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    projects_path = company_root / "company_memory" / "projects" / "projects_registry.json"
    assessments_path = company_root / "company_memory" / "projects" / "project_assessments.json"
    registry = _load_company_memory_payload(projects_path)
    assessments = _load_company_memory_payload(assessments_path)
    projects = list(registry.get("projects") or [])
    assessment_map = {
        str(item.get("project_id") or ""): item
        for item in (assessments.get("assessments") or [])
        if str(item.get("project_id") or "").strip()
    }
    return projects, assessment_map


def _load_related_commitments(company_root: Path) -> List[Dict[str, Any]]:
    path = company_root / "company_memory" / "management_commitments" / "management_commitments.json"
    payload = _load_company_memory_payload(path)
    return list(payload.get("commitments") or [])


def _load_optional_financial_truth(company_root: Path) -> Dict[str, Any]:
    path = company_root / "company_memory" / "financials" / "financial_truth_pack.json"
    return _load_company_memory_payload(path)


def _clean_tokens(value: Any) -> set[str]:
    return {token for token in _compact_lower(value).split() if token}


def _link_projects(capacity: Dict[str, Any], projects: Sequence[Dict[str, Any]]) -> List[str]:
    capacity_text = " ".join(
        [
            _compact_lower(capacity.get("capacity_name")),
            _compact_lower(capacity.get("normalized_name")),
            _compact_lower(capacity.get("purpose")),
            _compact_lower(capacity.get("location")),
            _compact_lower(capacity.get("capacity_type")),
        ]
    )
    capacity_tokens = _clean_tokens(capacity_text)
    linked: List[Tuple[int, str]] = []
    for project in projects:
        project_text = " ".join(
            [
                _compact_lower(project.get("project_name")),
                _compact_lower(project.get("normalized_name")),
                _compact_lower(project.get("objective")),
                _compact_lower(project.get("business_rationale")),
                _compact_lower(project.get("location")),
                _compact_lower(project.get("project_type")),
            ]
        )
        score = 0
        project_tokens = _clean_tokens(project_text)
        shared = capacity_tokens & project_tokens
        if len(shared) >= 4:
            score += 4
        elif len(shared) >= 3:
            score += 3
        elif len(shared) >= 2:
            score += 2
        if _compact_lower(capacity.get("location")) and _compact_lower(capacity.get("location")) in project_text:
            score += 2
        if any(term in capacity_text for term in ("facility", "plant", "line", "manufacturing", "testing", "workforce", "infrastructure")) and any(term in project_text for term in ("facility", "plant", "line", "capacity", "manufacturing", "testing", "expansion", "upgrade")):
            score += 2
        if any(term in project_text for term in ("commissioned", "operational", "utilization", "capacity", "expansion")):
            score += 1
        if score >= 5 and project.get("project_id"):
            linked.append((score, str(project["project_id"])))
    return [item[1] for item in sorted(linked, key=lambda item: (-item[0], item[1]))]


def _link_commitments(capacity: Dict[str, Any], commitments: Sequence[Dict[str, Any]]) -> List[str]:
    capacity_text = " ".join(
        [
            _compact_lower(capacity.get("capacity_name")),
            _compact_lower(capacity.get("normalized_name")),
            _compact_lower(capacity.get("purpose")),
            _compact_lower(capacity.get("location")),
            _compact_lower(capacity.get("capacity_type")),
        ]
    )
    capacity_tokens = _clean_tokens(capacity_text)
    linked: List[Tuple[int, str]] = []
    for commitment in commitments:
        commitment_text = " ".join(
            [
                _compact_lower(commitment.get("topic")),
                _compact_lower(commitment.get("normalized_commitment")),
                _compact_lower(commitment.get("delivery_assessment")),
                _compact_lower(commitment.get("investor_implication")),
                _compact_lower(commitment.get("category")),
            ]
        )
        score = 0
        commitment_tokens = _clean_tokens(commitment_text)
        shared = capacity_tokens & commitment_tokens
        if len(shared) >= 4:
            score += 4
        elif len(shared) >= 3:
            score += 3
        elif len(shared) >= 2:
            score += 2
        if any(term in capacity_text for term in ("capacity", "manufacturing", "facility", "capex", "expansion", "plant")) and any(term in commitment_text for term in ("capacity", "manufacturing", "facility", "capex", "expansion")):
            score += 2
        if commitment.get("category") and _compact_lower(commitment.get("category")) in capacity_text:
            score += 1
        if score >= 5 and commitment.get("id"):
            linked.append((score, str(commitment["id"])))
    return [item[1] for item in sorted(linked, key=lambda item: (-item[0], item[1]))]


def _group_candidates(candidates: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    groups: List[Dict[str, Any]] = []
    merged = 0
    for candidate in sorted(candidates, key=lambda item: (item["sort_key"], item["capacity_type"], item["capacity_name"], item["source_year"])):
        best_group = None
        best_score = 0
        for group in groups:
            if group.get("capacity_family") and candidate.get("capacity_family") and group.get("capacity_family") != candidate.get("capacity_family"):
                continue
            score = capacity_similarity(group, candidate)
            if score > best_score:
                best_score = score
                best_group = group
        if best_group is not None and best_score >= 6:
            best_group["source_references"].append(candidate["source_reference"])
            best_group["source_items"].append(candidate)
            best_group["linked_project_ids"] = sorted(set(best_group.get("linked_project_ids") or []) | set(candidate.get("linked_project_ids") or []))
            best_group["linked_commitment_ids"] = sorted(set(best_group.get("linked_commitment_ids") or []) | set(candidate.get("linked_commitment_ids") or []))
            if candidate.get("capacity_name") and len(str(candidate.get("capacity_name")).split()) >= len(str(best_group.get("capacity_name") or "").split()):
                best_group["capacity_name"] = candidate["capacity_name"]
            if candidate.get("normalized_name") and len(str(candidate.get("normalized_name")).split()) >= len(str(best_group.get("normalized_name") or "").split()):
                best_group["normalized_name"] = candidate["normalized_name"]
            if candidate.get("purpose") and len(str(candidate.get("purpose")).split()) >= len(str(best_group.get("purpose") or "").split()):
                best_group["purpose"] = candidate["purpose"]
            if candidate.get("location") and not best_group.get("location"):
                best_group["location"] = candidate["location"]
            if candidate.get("unit") and not best_group.get("unit"):
                best_group["unit"] = candidate["unit"]
            if candidate.get("planned_capacity") and not best_group.get("planned_capacity"):
                best_group["planned_capacity"] = candidate["planned_capacity"]
            if candidate.get("installed_capacity") and not best_group.get("installed_capacity"):
                best_group["installed_capacity"] = candidate["installed_capacity"]
            if candidate.get("operational_capacity") and not best_group.get("operational_capacity"):
                best_group["operational_capacity"] = candidate["operational_capacity"]
            if candidate.get("utilized_capacity") and not best_group.get("utilized_capacity"):
                best_group["utilized_capacity"] = candidate["utilized_capacity"]
            if candidate.get("capital_deployed") and not best_group.get("capital_deployed"):
                best_group["capital_deployed"] = candidate["capital_deployed"]
            if candidate.get("utilization_rate") is not None and best_group.get("utilization_rate") is None:
                best_group["utilization_rate"] = candidate["utilization_rate"]
            if candidate.get("confidence"):
                best_group["confidence"].append(candidate["confidence"])
            best_group["latest_period"] = max(best_group["latest_period"], candidate["source_year"], key=lambda value: parse_financial_year(value) if str(value).lower().startswith("fy") else -1)
            merged += 1
        else:
            groups.append(
                {
                    "capacity_name": candidate["capacity_name"],
                    "normalized_name": candidate["normalized_name"],
                    "capacity_type": candidate["capacity_type"],
                    "capacity_family": candidate.get("capacity_family") or "other",
                    "location": candidate["location"],
                    "purpose": candidate["purpose"],
                    "announcement_period": candidate["announcement_period"],
                    "planned_capacity": candidate["planned_capacity"],
                    "installed_capacity": candidate["installed_capacity"],
                    "operational_capacity": candidate["operational_capacity"],
                    "utilized_capacity": candidate["utilized_capacity"],
                    "utilization_rate": candidate["utilization_rate"],
                    "unit": candidate["unit"],
                    "expected_timeframe": candidate["expected_timeframe"],
                    "capital_deployed": candidate["capital_deployed"],
                    "current_status_hint": candidate["current_status_hint"],
                    "latest_period": candidate["source_year"],
                    "linked_project_ids": list(candidate.get("linked_project_ids") or []),
                    "linked_commitment_ids": list(candidate.get("linked_commitment_ids") or []),
                    "source_references": [candidate["source_reference"]],
                    "source_items": [candidate],
                    "confidence": [candidate["confidence"]],
                    "evidence_status": candidate["evidence_status"],
                    "economic_relevance": candidate["economic_relevance"],
                    "investor_implication": candidate.get("investor_implication") or "",
                    "source_year": candidate["source_year"],
                }
            )
    return groups, merged


def _build_registry_record(capacity_id: str, group: Dict[str, Any], utilization: Dict[str, Any], timeline: Dict[str, Any], impact: Dict[str, Any]) -> Dict[str, Any]:
    current_status = str(timeline.get("current_state") or "unable_to_verify")
    confidence_containers = [
        *(group.get("confidence") or []),
        utilization.get("confidence") or {},
        impact.get("confidence") or {},
    ]
    best_container = max(
        confidence_containers,
        key=lambda item: {"high": 3, "medium": 2, "low": 1, "unavailable": 0}.get(str((item or {}).get("level") or ""), 0),
    ) if confidence_containers else {}

    def _sanitize_list(values: Any) -> List[str]:
        return [
            sanitize_public_text(value)
            for value in (values or [])
            if sanitize_public_text(value)
        ]

    return {
        "capacity_id": capacity_id,
        "capacity_name": group["capacity_name"],
        "normalized_name": group["normalized_name"],
        "capacity_type": group["capacity_type"],
        "capacity_family": group.get("capacity_family") or "other",
        "location": group["location"],
        "purpose": group["purpose"],
        "linked_project_ids": list(group.get("linked_project_ids") or []),
        "linked_commitment_ids": list(group.get("linked_commitment_ids") or []),
        "announcement_period": group["announcement_period"],
        "planned_capacity": group.get("planned_capacity", ""),
        "installed_capacity": group.get("installed_capacity", ""),
        "operational_capacity": group.get("operational_capacity", ""),
        "utilized_capacity": group.get("utilized_capacity", ""),
        "utilization_rate": group.get("utilization_rate"),
        "unit": group.get("unit", ""),
        "expected_timeframe": group.get("expected_timeframe", ""),
        "capital_deployed": group.get("capital_deployed", ""),
        "utilization_measure": utilization,
        "current_status": current_status,
        "latest_period": timeline.get("latest_period") or group.get("latest_period"),
        "progression_summary": timeline.get("investor_implication") or {},
        "economic_relevance": group.get("economic_relevance") or "",
        "investor_implication": impact.get("observed_business_effect") or timeline.get("investor_implication", {}).get("what_changed") or "",
        "confidence": {
            "level": best_container.get("level", "unavailable"),
            "basis": sorted(
                {
                    sanitize_public_text(basis)
                    for container in confidence_containers
                    for basis in (container.get("basis") or [])
                    if sanitize_public_text(basis)
                }
            ),
            "limitations": sorted(
                {
                    sanitize_public_text(limitation)
                    for container in confidence_containers
                    for limitation in (container.get("limitations") or [])
                    if sanitize_public_text(limitation)
                }
            ),
        },
        "evidence_status": group.get("evidence_status") or "partial",
        "source_references": list(group.get("source_references") or []),
        "unresolved_questions": sorted(set(utilization.get("limitations") or []) | set(impact.get("unresolved_questions") or [])),
        "utilization_assessment": utilization,
        "capacity_assessment": impact,
        "semantic_quality": (group.get("source_items") or [{}])[0].get("semantic_quality") or {},
        "_source_items": list(group.get("source_items") or []),
    }


def _build_timeline_record(capacity: Dict[str, Any], events: Sequence[Dict[str, Any]], unresolved_questions: Sequence[str] | None = None) -> Dict[str, Any]:
    return build_timeline(capacity, events, unresolved_questions=unresolved_questions)


def _build_assessment_record(capacity: Dict[str, Any], timeline: Dict[str, Any], utilization: Dict[str, Any], impact: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "capacity_id": capacity["capacity_id"],
        "capacity_name": capacity["capacity_name"],
        "period": timeline.get("latest_period") or capacity.get("latest_period") or capacity.get("announcement_period") or "",
        "latest_period": timeline.get("latest_period") or capacity.get("latest_period") or capacity.get("announcement_period") or "",
        "execution_status": timeline.get("current_state") or capacity.get("current_status"),
        "utilization_status": utilization.get("utilization_status"),
        "observed_business_effect": impact.get("observed_business_effect"),
        "observed_financial_effect": impact.get("observed_financial_effect"),
        "economic_impact_status": impact.get("economic_impact_status"),
        "evidence_periods": impact.get("evidence_periods") or [],
        "what_changed": timeline.get("investor_implication", {}).get("what_changed"),
        "why_it_changed": timeline.get("investor_implication", {}).get("why_it_changed"),
        "conviction_impact": timeline.get("investor_implication", {}).get("conviction_impact"),
        "progression_summary": timeline.get("investor_implication") or {},
        "confidence": impact.get("confidence") or utilization.get("confidence") or {},
        "unresolved_questions": sorted(set((impact.get("unresolved_questions") or []) + (utilization.get("limitations") or []))),
        "utilization_assessment": utilization,
        "utilization_measure": capacity.get("utilization_measure") or capacity.get("utilization_assessment") or {},
        "source_references": list(capacity.get("source_references") or []),
    }


def _latest_assessment_event(assessment: Dict[str, Any], capacity_id: str, sequence: int, timeline: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event_id": f"{capacity_id}-E{sequence:03d}",
        "period": timeline.get("latest_period") or timeline.get("announcement_period") or "",
        "event_type": "latest_assessment",
        "title": assessment.get("capacity_name") or "Latest assessment",
        "description": assessment.get("what_changed") or assessment.get("observed_business_effect") or "Latest assessment",
        "status": assessment.get("execution_status"),
        "source_reference": assessment.get("source_references", [{}])[0] if assessment.get("source_references") else {},
    }


@dataclass
class CapacityEvolutionBuilder:
    company: str
    companies_root: Path | str = Path("companies")
    output_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.companies_root = Path(self.companies_root)
        self.company_root = self.companies_root / self.company
        self.output_dir = get_capacity_dir(self.company, self.companies_root)

    def _extract_candidates(self, year_record: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = year_record.get("clean_capacity") or []
        if not isinstance(items, list):
            return []
        candidates: List[Dict[str, Any]] = []
        for item in items:
            candidate = normalize_candidate(year_record, item, source_kind="capacity")
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _build_registry_from_groups(
        self,
        groups: Sequence[Dict[str, Any]],
        projects: Sequence[Dict[str, Any]],
        project_assessments: Dict[str, Dict[str, Any]],
        commitments: Sequence[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        registry: List[Dict[str, Any]] = []
        timelines: List[Dict[str, Any]] = []
        assessments: List[Dict[str, Any]] = []
        for index, group in enumerate(groups, start=1):
            capacity_id = f"CP-{index:04d}"
            linked_projects = _link_projects(group, projects)
            linked_commitments = _link_commitments(group, commitments)
            group["capacity_id"] = capacity_id
            for source_item in group.get("source_items") or []:
                source_item["capacity_id"] = capacity_id
            group["linked_project_ids"] = sorted(set(group.get("linked_project_ids") or []) | set(linked_projects))
            group["linked_commitment_ids"] = sorted(set(group.get("linked_commitment_ids") or []) | set(linked_commitments))
            events = []
            last_signature = None
            for event_index, candidate in enumerate(
                sorted(group["source_items"], key=lambda item: (parse_financial_year(item["source_year"]), item["capacity_name"], item["current_status_hint"] or ""))
            ):
                event = build_capacity_event(candidate, sequence=event_index + 1)
                signature = (
                    _compact_lower(event.get("event_type")),
                    _compact_lower(event.get("title")),
                    _compact_lower(event.get("description")),
                    _compact_lower((event.get("metadata") or {}).get("derived_status")),
                )
                if signature == last_signature:
                    continue
                events.append(event)
                last_signature = signature
            timeline = _build_timeline_record(group, events, unresolved_questions=[])
            utilization = assess_utilization(group, timeline)
            related_project_assessments = [project_assessments.get(pid) for pid in group.get("linked_project_ids") or [] if project_assessments.get(pid)]
            impact = assess_capacity_impact(group, timeline, utilization, related_project_assessments=related_project_assessments)
            current_status = str(timeline.get("current_state") or "unable_to_verify")
            group["current_status"] = current_status
            group["investor_implication"] = timeline.get("investor_implication", {}).get("what_changed") or impact.get("observed_business_effect") or ""
            registry_record = _build_registry_record(capacity_id, group, utilization, timeline, impact)
            registry.append({key: value for key, value in registry_record.items() if key != "_source_items"})
            timelines.append(
                {
                    **timeline,
                    "capacity_id": capacity_id,
                    "capacity_name": group["capacity_name"],
                    "current_status": current_status,
                    "utilization_assessment": utilization,
                    "capacity_assessment": impact,
                    "source_references": list(group.get("source_references") or []),
                }
            )
            assessments.append(_build_assessment_record(registry_record, timeline, utilization, impact))
            latest_event = _latest_assessment_event(assessments[-1], capacity_id, len(events) + 1, timeline)
            timelines[-1]["events"].append(latest_event)
        return registry, timelines, assessments

    def build(self) -> Dict[str, Path]:
        year_records = [_load_year_record(year_dir) for year_dir in _discover_years(self.company_root)]
        candidates: List[Dict[str, Any]] = []
        for year_record in year_records:
            candidates.extend(self._extract_candidates(year_record))

        projects, project_assessments = _load_related_projects(self.company_root)
        commitments = _load_related_commitments(self.company_root)
        financial_truth = _load_optional_financial_truth(self.company_root)
        project_ids = {str(project.get("project_id") or "").strip() for project in projects if str(project.get("project_id") or "").strip()}
        commitment_ids = {str(commitment.get("id") or "").strip() for commitment in commitments if str(commitment.get("id") or "").strip()}

        for candidate in candidates:
            candidate["linked_project_ids"] = _link_projects(candidate, projects)
            candidate["linked_commitment_ids"] = _link_commitments(candidate, commitments)

        groups, merged = _group_candidates(candidates)
        registry_records, timeline_records, assessment_records = self._build_registry_from_groups(groups, projects, project_assessments, commitments)

        validation = validate_capacity_payload(
            {
                "company": self.company,
                "capacities": registry_records,
            },
            timelines_payload={"timelines": timeline_records},
            assessments_payload={"assessments": assessment_records},
            project_ids=project_ids,
            commitment_ids=commitment_ids,
        )

        status_counts = defaultdict(int)
        for capacity in registry_records:
            status_counts[str(capacity.get("current_status") or "unable_to_verify")] += 1
        utilization_counts = defaultdict(int)
        for assessment in assessment_records:
            utilization_counts[str(assessment.get("utilization_status") or "unclear")] += 1
        impact_observable = sum(
            1
            for assessment in assessment_records
            if assessment.get("economic_impact_status") in {"early_evidence", "partially_observed", "clearly_observed", "negative_outcome"}
        )

        summary = {
            "schema_version": CAPACITY_SCHEMA_VERSION,
            "company": self.company,
            "generated_at": _utc_now(),
            "generator_version": CAPACITY_GENERATOR_VERSION,
            "capacity_count": len(registry_records),
            "status_counts": {status: status_counts[status] for status in ["announced", "planned", "funded", "under_construction", "installed", "commissioned", "operational", "ramping", "partially_utilized", "materially_utilized", "underutilized", "delayed", "paused", "cancelled", "superseded", "unable_to_verify"]},
            "utilization_status_counts": {status: utilization_counts[status] for status in ["not_disclosed", "pre_operational", "ramping", "low", "moderate", "high", "fully_utilized", "unclear"]},
            "capacity_items": registry_records,
        }

        timeline_payload = {
            "schema_version": CAPACITY_SCHEMA_VERSION,
            "company": self.company,
            "generated_at": _utc_now(),
            "latest_period": max(
                [str(timeline.get("latest_period") or "") for timeline in timeline_records if str(timeline.get("latest_period") or "").strip()],
                key=lambda value: parse_financial_year(value) if str(value).lower().startswith("fy") else -1,
                default="",
            ),
            "timelines": timeline_records,
        }
        assessment_payload = {
            "schema_version": CAPACITY_SCHEMA_VERSION,
            "company": self.company,
            "generated_at": _utc_now(),
            "latest_period": max(
                [str(assessment.get("latest_period") or assessment.get("period") or "") for assessment in assessment_records if str(assessment.get("latest_period") or assessment.get("period") or "").strip()],
                key=lambda value: parse_financial_year(value) if str(value).lower().startswith("fy") else -1,
                default="",
            ),
            "assessments": assessment_records,
        }

        considered_sources = [
            "companies/<company>/<year>/extracted/clean_capacity.json",
            "companies/<company>/<year>/extracted/clean_projects.json",
            "companies/<company>/<year>/intelligence/company_intelligence.json",
            "companies/<company>/<year>/intelligence/management_summary.json",
            "companies/<company>/company_memory/projects/projects_registry.json",
            "companies/<company>/company_memory/projects/project_assessments.json",
            "companies/<company>/company_memory/management_commitments/management_commitments.json",
            "companies/<company>/company_memory/financials/financial_truth_pack.json",
        ]
        found_sources: List[str] = []
        missing_sources: List[str] = []
        for year_record in year_records:
            for source_name, meta in (year_record.get("source_artifacts") or {}).items():
                label = f"{year_record['year']}/{source_name}"
                if meta.get("found"):
                    found_sources.append(label)
                else:
                    missing_sources.append(label)
        for extra_path in [
            self.company_root / "company_memory" / "projects" / "projects_registry.json",
            self.company_root / "company_memory" / "projects" / "project_assessments.json",
            self.company_root / "company_memory" / "management_commitments" / "management_commitments.json",
            self.company_root / "company_memory" / "financials" / "financial_truth_pack.json",
        ]:
            label = str(extra_path)
            if extra_path.exists():
                found_sources.append(label)
            else:
                missing_sources.append(label)

        capacity_items_written = len(registry_records)
        turning_points_detected = sum(len(timeline.get("turning_points") or []) for timeline in timeline_records)
        unresolved_items = sum(len(item.get("unresolved_questions") or []) for item in registry_records)
        validation_status = validation.get("status", "fail")
        limitations: List[str] = []
        if not found_sources:
            limitations.append("No usable capacity evidence was found.")
        if unresolved_items:
            limitations.append("Some capacities still have unresolved questions.")
        if validation_status != "pass":
            limitations.append("Validation surfaced issues that should be reviewed.")
        if financial_truth:
            limitations.append("Financial truth was available but not force-fitted into capacity outcomes.")

        manifest = build_capacity_manifest(
            company_slug=self.company,
            generated_at=_utc_now(),
            upstream_sources_considered=considered_sources,
            upstream_sources_found=sorted(set(found_sources)),
            upstream_sources_missing=sorted(set(missing_sources)),
            capacity_candidates=len(candidates),
            capacity_items_written=capacity_items_written,
            duplicate_candidates_merged=merged,
            project_links={
                "count": len({pid for record in registry_records for pid in (record.get("linked_project_ids") or [])}),
                "ids": sorted({pid for record in registry_records for pid in (record.get("linked_project_ids") or [])}),
            },
            commitment_links={
                "count": len({cid for record in registry_records for cid in (record.get("linked_commitment_ids") or [])}),
                "ids": sorted({cid for record in registry_records for cid in (record.get("linked_commitment_ids") or [])}),
            },
            timelines_written=len(timeline_records),
            turning_points_detected=turning_points_detected,
            unresolved_items=unresolved_items,
            validation_status=validation_status,
            limitations=limitations,
        )

        files = {
            "capacity_registry.json": summary,
            "capacity_timelines.json": timeline_payload,
            "capacity_assessments.json": assessment_payload,
            "capacity_validation.json": {
                "schema_version": CAPACITY_SCHEMA_VERSION,
                "company": self.company,
                "generated_at": _utc_now(),
                **validation,
            },
            "capacity_manifest.json": manifest,
        }

        written_paths: Dict[str, Path] = {}
        for filename, payload in files.items():
            written_paths[filename] = write_json_file(self.output_dir / filename, payload)
        return written_paths


def build_capacity_evolution(company: str, companies_root: Path | str = Path("companies")) -> Dict[str, Path]:
    return CapacityEvolutionBuilder(company=company, companies_root=companies_root).build()
