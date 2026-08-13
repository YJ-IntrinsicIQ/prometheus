from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from intelligence.progression import build_confidence, validate_progression_payload
from knowledge.company_memory import parse_financial_year

from .classifier import _normalize_text, is_bounded_project_candidate, project_similarity
from .contracts import PROJECTS_GENERATOR_VERSION, PROJECTS_MANIFEST_SCHEMA_VERSION, PROJECTS_SCHEMA_VERSION
from .impact import assess_project_impact
from .manifest import build_projects_manifest
from .normalizer import normalize_candidate, _year_label
from .paths import (
    get_project_assessments_path,
    get_project_timelines_path,
    get_projects_dir,
    get_projects_manifest_path,
    get_projects_registry_path,
    get_projects_validation_path,
)
from .progression import ProjectsProgressionAdapter, build_project_event, build_timeline
from .validators import validate_projects_payload
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


def _candidate_sources(company_root: Path) -> List[Tuple[str, Path]]:
    sources = [
        ("clean_projects", Path("extracted") / "clean_projects.json"),
        ("clean_capacity", Path("extracted") / "clean_capacity.json"),
        ("company_intelligence", Path("intelligence") / "company_intelligence.json"),
        ("management_summary", Path("intelligence") / "management_summary.json"),
    ]
    return sources


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
        record["source_artifacts"][source_name] = {
            "path": str(path),
            "found": found,
        }
        record[source_name] = payload if isinstance(payload, (dict, list)) else {}
    return record


def _build_source_item_years(year_record: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for source_kind, key in (("project", "clean_projects"), ("capacity", "clean_capacity")):
        items = year_record.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            normalized = normalize_candidate(year_record, item, source_kind=source_kind)
            if normalized is not None:
                candidates.append(normalized)
    return candidates


def _merge_project_group(group: Dict[str, Any], candidate: Dict[str, Any]) -> None:
    group["source_references"].append(candidate["source_reference"])
    group["source_items"].append(candidate)
    group["related_commitment_ids"] = sorted(set(group.get("related_commitment_ids") or []) | set(candidate.get("related_commitment_ids") or []))
    if candidate.get("project_name") and len(str(candidate.get("project_name")).split()) >= len(str(group.get("project_name") or "").split()):
        group["project_name"] = candidate["project_name"]
    if candidate.get("normalized_name") and len(str(candidate.get("normalized_name")).split()) >= len(str(group.get("normalized_name") or "").split()):
        group["normalized_name"] = candidate["normalized_name"]
    if candidate.get("objective") and len(str(candidate.get("objective")).split()) >= len(str(group.get("objective") or "").split()):
        group["objective"] = candidate["objective"]
    if candidate.get("business_rationale") and len(str(candidate.get("business_rationale")).split()) >= len(str(group.get("business_rationale") or "").split()):
        group["business_rationale"] = candidate["business_rationale"]
    if candidate.get("location") and not group.get("location"):
        group["location"] = candidate["location"]
    if candidate.get("expected_output_or_capacity") and not group.get("expected_output_or_capacity"):
        group["expected_output_or_capacity"] = candidate["expected_output_or_capacity"]
    if candidate.get("expected_cost") and not group.get("expected_cost"):
        group["expected_cost"] = candidate["expected_cost"]
    if candidate.get("expected_timeframe") and not group.get("expected_timeframe"):
        group["expected_timeframe"] = candidate["expected_timeframe"]
    if candidate.get("confidence"):
        group["confidence"].append(candidate["confidence"])
    group["announcement_period"] = min(group["announcement_period"], candidate["announcement_period"], key=lambda value: parse_financial_year(value) if str(value).lower().startswith("fy") else 10_000)
    group["latest_period"] = max(group["latest_period"], candidate["source_year"], key=lambda value: parse_financial_year(value) if str(value).lower().startswith("fy") else -1)


def _merge_groups(groups: List[Dict[str, Any]], candidate: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    best_group = None
    best_score = 0
    for group in groups:
        score = project_similarity(group, candidate)
        if score > best_score:
            best_score = score
            best_group = group
    if best_group is not None and best_score >= 5:
        _merge_project_group(best_group, candidate)
        return best_group, True
    new_group = {
        "project_name": candidate["project_name"],
        "normalized_name": candidate["normalized_name"],
        "project_type": candidate["project_type"],
        "objective": candidate["objective"],
        "business_rationale": candidate["business_rationale"],
        "announcement_period": candidate["announcement_period"],
        "expected_timeframe": candidate["expected_timeframe"],
        "expected_output_or_capacity": candidate["expected_output_or_capacity"],
        "expected_cost": candidate["expected_cost"],
        "location": candidate["location"],
        "related_commitment_ids": list(candidate.get("related_commitment_ids") or []),
        "source_references": [candidate["source_reference"]],
        "source_items": [candidate],
        "confidence": [candidate["confidence"]],
        "latest_period": candidate["source_year"],
    }
    groups.append(new_group)
    return new_group, False


def _project_status_from_events(events: Sequence[Dict[str, Any]]) -> str:
    if not events:
        return "unable_to_verify"
    states = [str((event.get("metadata") or {}).get("derived_status") or "unable_to_verify") for event in events]
    for state in ("cancelled", "superseded", "paused", "delayed", "operational", "commissioned", "partially_operational", "under_execution", "funded", "planning", "announced"):
        if state in states:
            return state
    return "unable_to_verify"


def _dedupe_project_events(project_id: str, candidate_records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    seen_signatures = set()
    sequence = 1
    last_signature = None
    for candidate in sorted(candidate_records, key=lambda item: (parse_financial_year(item["source_year"]), item["project_name"], item["status_text"])):
        event_candidate = dict(candidate)
        event_candidate["project_id"] = project_id
        event = build_project_event(event_candidate, sequence)
        signature = (
            event["event_type"],
            event["metadata"].get("derived_status"),
            _normalize_text(event["title"]),
            _normalize_text(event["description"]),
        )
        if signature == last_signature:
            events[-1]["source_references"].extend(ref for ref in event["source_references"] if ref not in events[-1]["source_references"])
            continue
        if signature in seen_signatures and event["event_type"] == "latest_assessment":
            continue
        seen_signatures.add(signature)
        events.append(event)
        last_signature = signature
        sequence += 1
    return events


def _link_commitments(projects: List[Dict[str, Any]], commitments: List[Dict[str, Any]]) -> None:
    commitment_lookup = commitments
    for project in projects:
        project_text = " ".join(
            [
                project.get("project_name") or "",
                project.get("normalized_name") or "",
                project.get("objective") or "",
                project.get("business_rationale") or "",
            ]
        ).lower()
        related: List[Tuple[int, str]] = []
        for commitment in commitment_lookup:
            commitment_text = " ".join(
                [
                    commitment.get("topic") or "",
                    commitment.get("normalized_commitment") or "",
                    commitment.get("investor_implication") or "",
                    commitment.get("delivery_assessment") or "",
                ]
            ).lower()
            score = 0
            if commitment.get("id"):
                score += 1
            if commitment.get("category") and commitment.get("category").lower() in project_text:
                score += 2
            project_tokens = set(project_text.split())
            commitment_tokens = set(commitment_text.split())
            if len(project_tokens & commitment_tokens) >= 3:
                score += 3
            elif len(project_tokens & commitment_tokens) >= 2:
                score += 2
            if any(term in project_text for term in ("facility", "capacity", "manufacturing", "plant", "line")) and any(term in commitment_text for term in ("capacity", "manufacturing", "facility", "capex", "expansion")):
                score += 2
            if score >= 5:
                related.append((score, commitment["id"]))
        project["related_commitment_ids"] = [item[1] for item in sorted(related, key=lambda item: (-item[0], item[1]))]


def _build_project_record(company: str, group: Dict[str, Any], project_id: str, commitments: List[Dict[str, Any]]) -> Dict[str, Any]:
    candidate_events = _dedupe_project_events(project_id, group["source_items"])
    project = {
        "project_id": project_id,
        "project_name": group["project_name"],
        "normalized_name": group["normalized_name"],
        "project_type": group["project_type"],
        "objective": group["objective"],
        "business_rationale": group["business_rationale"],
        "announcement_period": group["announcement_period"],
        "expected_timeframe": group["expected_timeframe"],
        "expected_output_or_capacity": group["expected_output_or_capacity"],
        "expected_cost": group["expected_cost"],
        "location": group["location"],
        "related_commitment_ids": list(group.get("related_commitment_ids") or []),
        "source_references": list(group["source_references"]),
        "confidence": build_confidence(
            max((item.get("confidence", {}).get("level") for item in group["confidence"]), key=lambda level: {"high": 3, "medium": 2, "low": 1, "unavailable": 0}.get(str(level), 0), default="unavailable"),
            basis=sorted({basis for item in group["confidence"] for basis in (item.get("basis") or [])}),
            limitations=sorted({limit for item in group["confidence"] for limit in (item.get("limitations") or [])}),
        ),
        "semantic_quality": (group.get("source_items") or [{}])[0].get("semantic_quality") or {},
    }
    _link_commitments([project], commitments)
    timeline = build_timeline(project, candidate_events, unresolved_questions=[])
    impact = assess_project_impact(project, timeline)
    project_status = str(timeline.get("current_state") or _project_status_from_events(timeline.get("events") or []))
    project.update(
        {
            "current_status": project_status,
            "latest_period": timeline.get("latest_period") or group["latest_period"],
            "progression_summary": timeline.get("investor_implication") or {},
            "economic_relevance": group.get("business_rationale") or "",
            "investor_implication": {
                "what_changed": impact["execution_summary"],
                "why_it_changed": timeline.get("investor_implication", {}).get("why_it_changed") or "The latest evidence or evidence gap changed the project view.",
                "conviction_impact": timeline.get("investor_implication", {}).get("conviction_impact") or "unclear",
            },
            "evidence_status": timeline.get("coverage_status") or "supported",
            "unresolved_questions": list((timeline.get("unresolved_questions") or []) + (impact.get("unresolved_questions") or [])),
            "progression": timeline,
            "assessment": impact,
        }
    )
    return project


@dataclass
class ProjectsBuilder:
    company: str
    companies_root: Path | str = Path("companies")
    output_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.companies_root = Path(self.companies_root)
        self.company_root = self.companies_root / self.company
        self.output_dir = get_projects_dir(self.company)

    def _discover_years(self) -> List[Path]:
        return _discover_years(self.company_root)

    def _load_year_record(self, year_dir: Path) -> Dict[str, Any]:
        return _load_year_record(year_dir)

    def _extract_candidates(self, year_record: Dict[str, Any]) -> List[Dict[str, Any]]:
        return _build_source_item_years(year_record)

    def _load_commitments(self) -> List[Dict[str, Any]]:
        path = self.company_root / "company_memory" / "management_commitments" / "management_commitments.json"
        payload = _load_json(path)
        commitments = payload.get("commitments") if isinstance(payload, dict) else []
        return commitments if isinstance(commitments, list) else []

    def build(self) -> Dict[str, Path]:
        year_records = [self._load_year_record(year_dir) for year_dir in self._discover_years()]
        commitments = self._load_commitments()
        candidates: List[Dict[str, Any]] = []
        for year_record in year_records:
            candidates.extend(self._extract_candidates(year_record))

        groups: List[Dict[str, Any]] = []
        duplicate_candidates_merged = 0
        for candidate in sorted(candidates, key=lambda item: (parse_financial_year(item["announcement_period"]), item["project_type"], item["normalized_name"], item["source_year"])):
            _, merged = _merge_groups(groups, candidate)
            if merged:
                duplicate_candidates_merged += 1

        projects: List[Dict[str, Any]] = []
        timelines: List[Dict[str, Any]] = []
        assessments: List[Dict[str, Any]] = []
        unresolved_projects = 0
        turning_points_detected = 0
        for index, group in enumerate(groups, start=1):
            project_id = f"PJ-{index:04d}"
            project = _build_project_record(self.company, group, project_id, commitments)
            projects.append(project)
            timeline = project["progression"]
            timelines.append(timeline)
            turning_points_detected += len(timeline.get("turning_points") or [])
            assessment = {
                "project_id": project_id,
                "project_name": project["project_name"],
                "period": timeline.get("latest_period") or group["latest_period"],
                "latest_period": timeline.get("latest_period") or group["latest_period"],
                "execution_status": project["assessment"]["execution_status"],
                "execution_summary": project["assessment"]["execution_summary"],
                "economic_impact_status": project["assessment"]["economic_impact_status"],
                "observed_business_effect": project["assessment"]["observed_business_effect"],
                "observed_financial_effect": project["assessment"]["observed_financial_effect"],
                "evidence_periods": project["assessment"]["evidence_periods"],
                "confidence": project["assessment"]["confidence"],
                "unresolved_questions": project["assessment"]["unresolved_questions"],
                "what_changed": project["investor_implication"]["what_changed"],
                "why_it_changed": project["investor_implication"]["why_it_changed"],
                "conviction_impact": project["investor_implication"]["conviction_impact"],
            }
            if assessment["economic_impact_status"] in {"not_yet_observable", "unclear"} or assessment["execution_status"] in {"announced", "planning", "funded", "under_execution"}:
                unresolved_projects += 1
            assessments.append(assessment)

        registry = {
            "schema_version": PROJECTS_SCHEMA_VERSION,
            "company": self.company,
            "generated_at": _utc_now(),
            "generator_version": PROJECTS_GENERATOR_VERSION,
            "project_count": len(projects),
            "projects": projects,
        }
        timelines_payload = {
            "schema_version": PROJECTS_SCHEMA_VERSION,
            "company": self.company,
            "generated_at": _utc_now(),
            "latest_period": max(
                [str(timeline.get("latest_period") or "") for timeline in timelines if str(timeline.get("latest_period") or "").strip()],
                key=lambda value: parse_financial_year(value) if str(value).lower().startswith("fy") else -1,
                default="",
            ),
            "timelines": timelines,
        }
        assessments_payload = {
            "schema_version": PROJECTS_SCHEMA_VERSION,
            "company": self.company,
            "generated_at": _utc_now(),
            "latest_period": max(
                [str(assessment.get("latest_period") or assessment.get("period") or "") for assessment in assessments if str(assessment.get("latest_period") or assessment.get("period") or "").strip()],
                key=lambda value: parse_financial_year(value) if str(value).lower().startswith("fy") else -1,
                default="",
            ),
            "assessments": assessments,
        }

        commitment_ids = [commitment.get("id") for commitment in commitments if commitment.get("id")]
        validation = validate_projects_payload(registry, timelines_payload=timelines_payload, assessments_payload=assessments_payload, commitment_ids=commitment_ids)
        if projects:
            status = validation.get("status", "pass")
        else:
            status = "warning"
        validation_payload = {
            "schema_version": PROJECTS_SCHEMA_VERSION,
            "company": self.company,
            "generated_at": _utc_now(),
            "status": status if validation["status"] == "pass" else validation["status"],
            "issue_count": validation["issue_count"],
            "issues": validation["issues"],
        }
        source_paths = []
        source_found = []
        source_missing = []
        for year_record in year_records:
            for source_name, meta in year_record.get("source_artifacts", {}).items():
                source_paths.append(meta["path"])
                if meta.get("found"):
                    source_found.append(meta["path"])
                else:
                    source_missing.append(meta["path"])
        limitations = []
        if unresolved_projects:
            limitations.append("Some projects remain unresolved because later execution or economic evidence is still thin.")
        if any(item.get("status") == "warning" for item in [validation_payload]):
            limitations.append("Validation produced warnings.")

        manifest = build_projects_manifest(
            company_slug=self.company,
            generated_at=_utc_now(),
            upstream_sources_considered=source_paths,
            upstream_sources_found=source_found,
            upstream_sources_missing=source_missing,
            project_candidates=len(candidates),
            projects_written=len(projects),
            duplicate_candidates_merged=duplicate_candidates_merged,
            timelines_written=len(timelines),
            turning_points_detected=turning_points_detected,
            unresolved_projects=unresolved_projects,
            validation_status=validation_payload["status"],
            limitations=limitations,
        )

        files = {
            "projects_registry.json": registry,
            "project_timelines.json": timelines_payload,
            "project_assessments.json": assessments_payload,
            "projects_validation.json": validation_payload,
            "projects_manifest.json": manifest,
        }
        written_paths: Dict[str, Path] = {}
        for filename, payload in files.items():
            written_paths[filename] = write_json_file(self.output_dir / filename, payload)
        return written_paths


def build_projects(company: str, companies_root: Path | str = Path("companies")) -> Dict[str, Path]:
    return ProjectsBuilder(company=company, companies_root=companies_root).build()
