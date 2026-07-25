from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


MAX_ITEMS_PER_SECTION = 10
GENERIC_LIMITATION = "Multi-year memory artifacts not available."
SOURCE_FILE_NAMES = (
    "company_year_index.json",
    "business_dna_evolution.json",
    "strategy_timeline.json",
    "promise_tracker.json",
    "risk_evolution.json",
    "capital_allocation_timeline.json",
    "management_consistency.json",
    "multi_year_index.json",
)
FISCAL_YEAR_PATTERNS = (
    re.compile(r"^fy(\d{2,4})$", re.IGNORECASE),
    re.compile(r"^(\d{4})-(\d{2,4})$"),
    re.compile(r"^(\d{4})$"),
)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _dedupe_preserve(values: Iterable[Any]) -> List[Any]:
    seen = set()
    deduped = []
    for value in values:
        marker = json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list)) else value
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(value)
    return deduped


def _limit(items: Iterable[Any], size: int = MAX_ITEMS_PER_SECTION) -> List[Any]:
    return list(items)[:size]


def _compact_reference(reference: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_year": reference.get("source_year"),
        "source_artifact": reference.get("source_artifact"),
        "source_item_id": reference.get("source_item_id"),
        "source_page": reference.get("source_page") or reference.get("page"),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iso_utc(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_fiscal_year_sort_key(label: Any) -> Optional[int]:
    text = str(label or "").strip()
    if not text:
        return None
    for pattern in FISCAL_YEAR_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        if pattern.pattern.startswith("^fy"):
            value = int(match.group(1))
            return value % 100 if value >= 100 else value
        if pattern.pattern.startswith("^(\\d{4})-(\\d{2,4})"):
            trailing = int(match.group(2))
            return trailing % 100 if trailing >= 100 else trailing
        if pattern.pattern.startswith("^(\\d{4})$"):
            return int(match.group(1)) % 100
    return None


def canonicalize_fiscal_year_label(label: Any) -> Optional[str]:
    sort_key = _parse_fiscal_year_sort_key(label)
    if sort_key is None:
        return None
    return f"fy{sort_key:02d}"


def sort_fiscal_year_labels(years: Sequence[Any]) -> Tuple[List[str], List[str]]:
    canonical_to_label: Dict[str, str] = {}
    warnings: List[str] = []
    for year in years:
        canonical = canonicalize_fiscal_year_label(year)
        if canonical is None:
            if year not in (None, ""):
                warnings.append(f"Could not parse fiscal year label: {year}")
            continue
        canonical_to_label.setdefault(canonical, canonical)
    sorted_years = sorted(canonical_to_label.values(), key=lambda value: _parse_fiscal_year_sort_key(value) or 0)
    return sorted_years, _dedupe_preserve(warnings)


def _collect_year_labels(node: Any) -> List[str]:
    labels: List[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            canonical_key = canonicalize_fiscal_year_label(key)
            if canonical_key:
                labels.append(canonical_key)
            labels.extend(_collect_year_labels(value))
        return labels
    if isinstance(node, list):
        for item in node:
            labels.extend(_collect_year_labels(item))
        return labels
    canonical = canonicalize_fiscal_year_label(node)
    return [canonical] if canonical else []


def _strip_source_chunk(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: _strip_source_chunk(value) for key, value in node.items() if key != "source_chunk"}
    if isinstance(node, list):
        return [_strip_source_chunk(item) for item in node]
    return node


class PCIMMultiYearBuilder:
    def __init__(self, company_root: Path | str, *, expected_years: Optional[Sequence[str]] = None):
        self.company_root = Path(company_root)
        self.multi_year_dir = self.company_root / "company_memory" / "multi_year"
        self.expected_years = list(expected_years or [])
        self._evidence_map: Dict[str, Dict[str, Any]] = {}
        self._last_source_manifest: Dict[str, Any] = {}

    @property
    def source_manifest(self) -> Dict[str, Any]:
        return dict(self._last_source_manifest)

    def build(self) -> Dict[str, Any]:
        artifacts, source_files = self._load_artifacts()
        years_available, year_warnings = self._determine_years_available(artifacts)
        loaded_artifacts = [entry for entry in source_files if entry["loaded"]]

        if not loaded_artifacts or not artifacts["multi_year_index"]:
            multi_year_inputs = {
                "available": False,
                "years_covered": [],
                "limitations": [GENERIC_LIMITATION] + year_warnings,
            }
            self._last_source_manifest = self._build_source_manifest(
                source_files=source_files,
                years_available=years_available,
                years_covered=[],
                multi_year_inputs=multi_year_inputs,
                extra_warnings=[GENERIC_LIMITATION] + year_warnings,
            )
            return multi_year_inputs

        business_dna = self._build_business_dna_evolution(artifacts["business_dna_evolution"])
        management_consistency = self._build_management_consistency(artifacts["management_consistency"])
        strategy_evolution = self._build_strategy_evolution(artifacts["strategy_timeline"])
        promise_follow_through = self._build_promise_follow_through(artifacts["promise_tracker"])
        recurring_risks = self._build_recurring_risks(artifacts["risk_evolution"])
        capital_allocation_pattern = self._build_capital_allocation_pattern(artifacts["capital_allocation_timeline"])

        years_covered = self._determine_years_covered(artifacts, source_files)
        limitations = _dedupe_preserve(
            list(artifacts["multi_year_index"].get("limitations", []))
            + management_consistency.get("evidence_gaps", [])
            + promise_follow_through.get("limitations", [])
            + capital_allocation_pattern.get("missing_financial_evidence", [])
            + year_warnings
        )
        multi_year_inputs = {
            "available": True,
            "years_covered": years_covered,
            "business_dna_evolution": business_dna,
            "management_consistency": management_consistency,
            "strategy_evolution": strategy_evolution,
            "promise_follow_through": promise_follow_through,
            "recurring_risks": recurring_risks,
            "capital_allocation_pattern": capital_allocation_pattern,
            "evidence_map": {
                evidence_id: self._evidence_map[evidence_id]
                for evidence_id in sorted(self._evidence_map.keys())
            },
            "limitations": limitations,
        }
        multi_year_inputs = _strip_source_chunk(multi_year_inputs)
        self._last_source_manifest = self._build_source_manifest(
            source_files=source_files,
            years_available=years_available,
            years_covered=years_covered,
            multi_year_inputs=multi_year_inputs,
            extra_warnings=year_warnings,
        )
        return multi_year_inputs

    def _load_artifacts(self) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
        payloads: Dict[str, Dict[str, Any]] = {
            "company_year_index": {},
            "business_dna_evolution": {},
            "strategy_timeline": {},
            "promise_tracker": {},
            "risk_evolution": {},
            "capital_allocation_timeline": {},
            "management_consistency": {},
            "multi_year_index": {},
        }
        source_files: List[Dict[str, Any]] = []

        for filename in SOURCE_FILE_NAMES:
            path = self.multi_year_dir / filename
            payload, entry = self._load_source_file(path)
            source_files.append(entry)
            key = filename.replace(".json", "")
            payloads[key] = payload
        return payloads, source_files

    def _load_source_file(self, path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        entry = {
            "name": path.name,
            "path": str(path),
            "exists": path.exists(),
            "loaded": False,
            "modified_at": "",
            "content_hash": "",
            "years_detected": [],
            "warnings": [],
        }
        if not path.exists():
            entry["warnings"].append("Source file missing.")
            return {}, entry
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            entry["modified_at"] = _iso_utc(path.stat().st_mtime)
            entry["content_hash"] = _sha256(path)
            entry["warnings"].append(f"Invalid JSON: {exc}")
            return {}, entry

        years_detected, warnings = sort_fiscal_year_labels(_collect_year_labels(payload))
        entry.update(
            {
                "loaded": True,
                "modified_at": _iso_utc(path.stat().st_mtime),
                "content_hash": _sha256(path),
                "years_detected": years_detected,
                "warnings": warnings,
            }
        )
        return payload if isinstance(payload, dict) else {}, entry

    def _determine_years_available(self, artifacts: Dict[str, Dict[str, Any]]) -> Tuple[List[str], List[str]]:
        candidates: List[Any] = []
        company_year_index = artifacts.get("company_year_index") or {}
        multi_year_index = artifacts.get("multi_year_index") or {}
        candidates.extend(company_year_index.get("available_years", []))
        candidates.extend(company_year_index.get("years_detected", []))
        candidates.extend(multi_year_index.get("years_covered", []))
        candidates.extend(self.expected_years)
        years, warnings = sort_fiscal_year_labels(candidates)
        return years, warnings

    def _determine_years_covered(
        self,
        artifacts: Dict[str, Dict[str, Any]],
        source_files: List[Dict[str, Any]],
    ) -> List[str]:
        candidates: List[Any] = list((artifacts.get("multi_year_index") or {}).get("years_covered", []))
        for entry in source_files:
            if entry["loaded"] and entry["name"] not in {"company_year_index.json", "multi_year_index.json"}:
                candidates.extend(entry.get("years_detected", []))
        years, _warnings = sort_fiscal_year_labels(candidates)
        return years

    def _build_source_manifest(
        self,
        *,
        source_files: List[Dict[str, Any]],
        years_available: List[str],
        years_covered: List[str],
        multi_year_inputs: Dict[str, Any],
        extra_warnings: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        available_keys = {canonicalize_fiscal_year_label(year) for year in years_available}
        covered_keys = {canonicalize_fiscal_year_label(year) for year in years_covered}
        missing_years = [
            year for year in years_available
            if canonicalize_fiscal_year_label(year) in available_keys - covered_keys
        ]
        stale_source_warnings = list(extra_warnings or [])
        if years_available and missing_years:
            stale_source_warnings.append(
                "PCIM multi_year_inputs do not cover all available years: " + ", ".join(missing_years)
            )
        for entry in source_files:
            if entry["warnings"]:
                stale_source_warnings.extend(f"{entry['name']}: {warning}" for warning in entry["warnings"])
        loaded_files = [entry for entry in source_files if entry["loaded"]]
        if not loaded_files:
            status = "fail"
        elif stale_source_warnings:
            status = "warning"
        else:
            status = "pass"
        generated_at = self._next_generated_at(loaded_files)
        return {
            "company": self.company_root.name,
            "generated_at": generated_at,
            "source_files": source_files,
            "years_available": years_available,
            "years_covered_in_multi_year_inputs": years_covered,
            "missing_years": missing_years,
            "stale_source_warnings": _dedupe_preserve(stale_source_warnings),
            "status": status,
        }

    def _next_generated_at(self, source_files: List[Dict[str, Any]]) -> str:
        timestamps = []
        for entry in source_files:
            modified_at = entry.get("modified_at")
            if not modified_at:
                continue
            try:
                timestamps.append(datetime.fromisoformat(modified_at.replace("Z", "+00:00")))
            except ValueError:
                continue
        if not timestamps:
            return ""
        return (max(timestamps) + timedelta(seconds=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _register_evidence_ids(
        self,
        evidence_ids: Iterable[str],
        *,
        source_year: Optional[str] = None,
        source_artifact: Optional[str] = None,
        source_item_id: Optional[str] = None,
        source_page: Optional[Any] = None,
    ) -> None:
        for evidence_id in evidence_ids:
            if not evidence_id:
                continue
            self._evidence_map.setdefault(
                evidence_id,
                {
                    "source_year": source_year,
                    "source_artifact": source_artifact,
                    "source_item_id": source_item_id,
                    "source_page": source_page,
                },
            )

    def _register_mentions(self, mentions: Iterable[Dict[str, Any]]) -> None:
        for mention in mentions:
            self._register_evidence_ids(
                mention.get("evidence_ids", []),
                source_year=mention.get("source_year"),
                source_artifact=mention.get("source_artifact"),
                source_item_id=mention.get("source_item_id"),
                source_page=mention.get("source_page") or mention.get("page"),
            )

    def _build_business_dna_evolution(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        timeline = payload.get("timeline", [])
        stable_dnas = list(payload.get("stable_themes", []))
        emerging_dnas = list(payload.get("emerging_themes", []))
        newly_detected: List[str] = []
        not_detected_this_year: List[str] = []
        possible_discontinuities: List[Dict[str, Any]] = []
        evidence_ids: List[str] = []
        yearly_dna_statuses: List[Dict[str, Any]] = []

        for year_entry in timeline:
            evidence_ids.extend(year_entry.get("evidence_ids", []))
            compact_statuses = []
            for status_entry in year_entry.get("dna_statuses", []):
                dna = status_entry.get("dna")
                status = status_entry.get("status")
                if status == "newly_detected" and dna:
                    newly_detected.append(dna)
                if status == "not_detected_this_year" and dna:
                    not_detected_this_year.append(dna)
                    possible_discontinuities.append(
                        {
                            "dna": dna,
                            "year": year_entry.get("year"),
                            "status": "not_detected_this_year",
                            "note": "Not detected in this year's artifacts; discontinuation is not confirmed.",
                        }
                    )
                self._register_evidence_ids(
                    status_entry.get("evidence_ids", []),
                    source_year=year_entry.get("year"),
                    source_artifact="business_classification.json",
                    source_item_id=dna,
                )
                compact_statuses.append(
                    {
                        "dna": dna,
                        "status": status,
                        "evidence_ids": list(status_entry.get("evidence_ids", [])),
                    }
                )
            yearly_dna_statuses.append(
                {
                    "year": year_entry.get("year"),
                    "business_dnas": list(year_entry.get("business_dnas", [])),
                    "dna_statuses": compact_statuses,
                    "evidence_ids": list(year_entry.get("evidence_ids", [])),
                }
            )

        for change in payload.get("changes_detected", []):
            for status_change in change.get("status_changes", []):
                if status_change.get("to_status") in {"not_detected_this_year", "possibly_discontinued"}:
                    possible_discontinuities.append(
                        {
                            "dna": status_change.get("dna"),
                            "from_year": change.get("from_year"),
                            "to_year": change.get("to_year"),
                            "status": status_change.get("to_status"),
                            "note": "Later-year artifacts do not confirm continuation.",
                        }
                    )

        return {
            "stable_dnas": stable_dnas,
            "stable_themes": stable_dnas,
            "emerging_themes": emerging_dnas,
            "newly_detected_dnas": _dedupe_preserve(newly_detected),
            "not_detected_this_year": _dedupe_preserve(not_detected_this_year),
            "possible_discontinuities": _limit(_dedupe_preserve(possible_discontinuities)),
            "yearly_dna_statuses": _limit(yearly_dna_statuses),
            "missing_rationale_years": list(payload.get("missing_rationale", [])),
            "evidence_ids": _dedupe_preserve(evidence_ids),
        }

    def _build_management_consistency(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        observations = []
        for item in payload.get("consistency_observations", []):
            compact = {
                "theme": item.get("theme"),
                "years_active": list(item.get("years_active", [])),
                "consistency_status": item.get("consistency_status"),
                "explanation": item.get("explanation"),
                "evidence_ids": list(item.get("evidence_ids", [])),
            }
            self._register_evidence_ids(
                compact["evidence_ids"],
                source_artifact="management_summary.json",
            )
            observations.append(compact)

        return {
            "repeated_focus_areas": _limit(payload.get("repeated_focus_areas", [])),
            "themes_active_across_years": _limit(payload.get("repeated_focus_areas", [])),
            "changed_focus_areas": _limit(payload.get("changed_focus_areas", [])),
            "unclear_themes": _limit(payload.get("changed_focus_areas", [])),
            "external_context_recurring_themes": _limit(payload.get("external_context_recurring_themes", [])),
            "consistency_observations": _limit(observations),
            "evidence_gaps": list(payload.get("evidence_gaps", [])),
        }

    def _build_strategy_evolution(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        evidence_ids: List[str] = []
        continued = [item.get("theme") for item in payload.get("strategy_continuity", []) if item.get("theme")]
        added: List[str] = []
        removed: List[str] = []
        shifts = []
        yearly_theme_evolution = []

        for year_entry in payload.get("timeline", []):
            yearly_theme_evolution.append(
                {
                    "year": year_entry.get("year"),
                    "management_focus": _limit(
                        [
                            {
                                "value": focus.get("value"),
                                "canonical_theme": focus.get("canonical_theme"),
                                "source_year": focus.get("source_year"),
                                "source_artifact": focus.get("source_artifact"),
                                "source_item_id": focus.get("source_item_id"),
                                "evidence_ids": list(focus.get("evidence_ids", [])),
                            }
                            for focus in year_entry.get("management_focus", [])
                        ]
                    ),
                }
            )
            for focus in year_entry.get("management_focus", []):
                evidence_ids.extend(focus.get("evidence_ids", []))
                self._register_evidence_ids(
                    focus.get("evidence_ids", []),
                    source_year=focus.get("source_year"),
                    source_artifact=focus.get("source_artifact"),
                    source_item_id=focus.get("source_item_id"),
                    source_page=(focus.get("evidence_references") or [{}])[0].get("source_page")
                    if isinstance(focus.get("evidence_references"), list)
                    else None,
                )

        for shift in payload.get("strategy_shifts", []):
            added.extend(shift.get("added_themes", []))
            removed.extend(shift.get("removed_themes", []))
            shifts.append(
                {
                    "from_year": shift.get("from_year"),
                    "to_year": shift.get("to_year"),
                    "added_themes": list(shift.get("added_themes", [])),
                    "removed_or_not_detected_themes": list(shift.get("removed_themes", [])),
                    "note": "Removed themes indicate they were not detected in later artifacts, not confirmed abandonment.",
                }
            )

        return {
            "continued_themes": _limit(_dedupe_preserve(continued)),
            "added_themes": _limit(_dedupe_preserve(added)),
            "removed_or_not_detected_themes": _limit(_dedupe_preserve(removed)),
            "possible_strategy_shifts": _limit(shifts),
            "yearly_theme_evolution": _limit(yearly_theme_evolution),
            "unresolved_strategy_questions": _limit(payload.get("unresolved_strategy_questions", [])),
            "evidence_ids": _dedupe_preserve(evidence_ids),
        }

    def _compact_promise(self, item: Dict[str, Any]) -> Dict[str, Any]:
        self._register_evidence_ids(
            item.get("related_evidence_ids", []),
            source_year=item.get("first_seen_year"),
            source_artifact="company_intelligence.json",
            source_item_id=item.get("promise_id"),
        )
        self._register_mentions(item.get("source_mentions", []))
        return {
            "promise_id": item.get("promise_id"),
            "normalized_promise": item.get("normalized_promise"),
            "first_seen_year": item.get("first_seen_year"),
            "repeated_years": list(item.get("repeated_years", [])),
            "latest_status": item.get("latest_status"),
            "status_by_year": dict(item.get("status_by_year", {})),
            "confidence": item.get("confidence"),
            "related_evidence_ids": list(item.get("related_evidence_ids", [])),
            "source_mentions": _limit(
                [
                    {
                        "value": mention.get("value"),
                        **_compact_reference(mention),
                        "evidence_ids": list(mention.get("evidence_ids", [])),
                    }
                    for mention in item.get("source_mentions", [])
                ],
                3,
            ),
        }

    def _build_promise_follow_through(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        promises = {item.get("promise_id"): item for item in payload.get("promises", []) if item.get("promise_id")}

        def resolve(ids_or_items: List[Any]) -> List[Dict[str, Any]]:
            resolved = []
            for value in ids_or_items:
                item = promises.get(value) if isinstance(value, str) else value
                if isinstance(item, dict):
                    resolved.append(self._compact_promise(item))
            return _limit(resolved)

        limitations = []
        if payload.get("unclear_promises"):
            limitations.append("Several promise statuses remain UNKNOWN because fulfillment is not explicit in current artifacts.")

        return {
            "fulfilled_promises": resolve(payload.get("fulfilled_promises", [])),
            "repeated_unresolved_promises": resolve(payload.get("repeated_unresolved_promises", [])),
            "unclear_promises": resolve(payload.get("unclear_promises", [])),
            "abandoned_or_disappeared_promises": resolve(payload.get("abandoned_or_disappeared_promises", [])),
            "follow_through_observations": _limit(
                [
                    {
                        "promise_id": promise.get("promise_id"),
                        "latest_status": promise.get("latest_status"),
                        "repeated_years": list(promise.get("repeated_years", [])),
                        "related_evidence_ids": list(promise.get("related_evidence_ids", [])),
                    }
                    for promise in payload.get("promises", [])
                    if promise.get("promise_id")
                ]
            ),
            "limitations": limitations,
        }

    def _compact_risk(self, item: Dict[str, Any]) -> Dict[str, Any]:
        self._register_evidence_ids(
            item.get("related_evidence_ids", []),
            source_year=item.get("first_seen_year"),
            source_artifact="company_intelligence.json",
            source_item_id=item.get("risk_id"),
        )
        self._register_mentions(item.get("source_mentions", []))
        return {
            "risk_id": item.get("risk_id"),
            "normalized_risk": item.get("normalized_risk"),
            "first_seen_year": item.get("first_seen_year"),
            "repeated_years": list(item.get("repeated_years", [])),
            "severity_by_year": dict(item.get("severity_by_year", {})),
            "latest_severity": item.get("latest_severity"),
            "confidence": item.get("confidence"),
            "numeric_signals_by_year": dict(item.get("numeric_signals_by_year", {})),
            "related_evidence_ids": list(item.get("related_evidence_ids", [])),
            "source_mentions": _limit(
                [
                    {
                        "value": mention.get("value"),
                        **_compact_reference(mention),
                        "evidence_ids": list(mention.get("evidence_ids", [])),
                        "severity": mention.get("severity"),
                    }
                    for mention in item.get("source_mentions", [])
                ],
                3,
            ),
        }

    def _build_recurring_risks(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        risks = {item.get("risk_id"): item for item in payload.get("risks", []) if item.get("risk_id")}

        def resolve(ids: List[str], *, include_generic_market: bool = True) -> List[Dict[str, Any]]:
            resolved = []
            for risk_id in ids:
                item = risks.get(risk_id)
                if not isinstance(item, dict):
                    continue
                if not include_generic_market and item.get("normalized_risk") == "market_risk":
                    continue
                resolved.append(self._compact_risk(item))
            return _limit(resolved)

        top_observations = resolve(payload.get("worsening_risks", []), include_generic_market=False)
        if len(top_observations) < 3:
            top_observations.extend(
                [
                    item
                    for item in resolve(payload.get("recurring_risks", []), include_generic_market=False)
                    if item["risk_id"] not in {existing["risk_id"] for existing in top_observations}
                ]
            )

        return {
            "recurring_risks": resolve(payload.get("recurring_risks", [])),
            "new_risks": resolve(payload.get("new_risks", [])),
            "worsening_risks": resolve(payload.get("worsening_risks", [])),
            "improving_risks": resolve(payload.get("improving_risks", [])),
            "unresolved_risks": resolve(payload.get("unresolved_risks", [])),
            "top_risk_observations": _limit(top_observations, 5),
            "risk_category_changes": _limit(payload.get("risk_category_changes", [])),
        }

    def _timeline_entries(self, timeline: List[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
        entries = []
        for year_bucket in timeline:
            for item in year_bucket.get(field, []):
                compact = {
                    "value": item.get("value"),
                    "category": item.get("category"),
                    "source_year": item.get("source_year"),
                    "source_artifact": item.get("source_artifact"),
                    "source_item_id": item.get("source_item_id"),
                    "source_page": item.get("source_page"),
                    "amount": item.get("amount"),
                    "confidence": item.get("confidence"),
                    "evidence_ids": list(item.get("evidence_ids", [])),
                }
                self._register_evidence_ids(
                    compact["evidence_ids"],
                    source_year=compact["source_year"],
                    source_artifact=compact["source_artifact"],
                    source_item_id=compact["source_item_id"],
                    source_page=compact["source_page"],
                )
                entries.append(compact)
        return _limit(entries)

    def _build_capital_allocation_pattern(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        timeline = payload.get("timeline", [])
        recurring_categories = [
            item for item in payload.get("capital_allocation_patterns", [])
            if len(item.get("years_active", [])) > 1
        ]
        return {
            "recurring_capital_allocation_categories": _limit(recurring_categories),
            "true_capital_deployment": self._timeline_entries(timeline, "true_capital_deployment"),
            "shareholder_returns": self._timeline_entries(timeline, "shareholder_returns"),
            "financing_actions": self._timeline_entries(timeline, "financing_actions"),
            "treasury_actions": self._timeline_entries(timeline, "treasury_actions"),
            "related_party_capital_flows": self._timeline_entries(timeline, "related_party_capital_flows"),
            "corporate_actions_non_cash_or_admin": self._timeline_entries(timeline, "corporate_actions_non_cash_or_admin"),
            "ownership_transfer_non_company_cashflow": self._timeline_entries(timeline, "ownership_transfer_non_company_cashflow"),
            "accounting_or_disclosure_only": self._timeline_entries(timeline, "accounting_or_disclosure_only"),
            "uncertain_items": self._timeline_entries(timeline, "uncertain"),
            "dividends": self._timeline_entries(timeline, "dividends"),
            "buybacks": self._timeline_entries(timeline, "buybacks"),
            "capex_or_cwip_activity": _limit(
                self._timeline_entries(timeline, "capex") + self._timeline_entries(timeline, "cwip")
            ),
            "share_splits": self._timeline_entries(timeline, "share_splits"),
            "equity_issuance": self._timeline_entries(timeline, "equity_issuance"),
            "treasury_investments": self._timeline_entries(timeline, "treasury_investments"),
            "debt_borrowing_signals": self._timeline_entries(timeline, "debt_borrowings"),
            "related_party_transactions": self._timeline_entries(timeline, "related_party_transactions"),
            "debt_repayment_signals": self._timeline_entries(timeline, "debt_repayments"),
            "ownership_transfer_items": self._timeline_entries(timeline, "ownership_transfers"),
            "corporate_action_items": self._timeline_entries(timeline, "corporate_actions"),
            "accounting_disclosure_items": self._timeline_entries(timeline, "accounting_disclosures"),
            "missing_financial_evidence": list(payload.get("missing_financial_evidence", [])),
        }


def audit_saved_pcim_manifest(
    company_root: Path | str,
    saved_manifest: Dict[str, Any],
    *,
    saved_multi_year_inputs: Optional[Dict[str, Any]] = None,
    expected_years: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    builder = PCIMMultiYearBuilder(company_root, expected_years=expected_years)
    current_multi_year_inputs = builder.build()
    current_manifest = builder.source_manifest

    failures: List[str] = []
    warnings: List[str] = []

    if not isinstance(saved_manifest, dict) or not saved_manifest:
        failures.append("PCIM source manifest missing or malformed.")
        return {
            "status": "fail",
            "failures": failures,
            "warnings": warnings,
            "current_manifest": current_manifest,
            "current_multi_year_inputs": current_multi_year_inputs,
        }

    saved_status = str(saved_manifest.get("status") or "").lower()
    if saved_status == "fail":
        failures.append("Saved PCIM source manifest status is fail.")

    saved_manifest_warnings = list(saved_manifest.get("stale_source_warnings", []) or [])

    saved_source_files = {
        str(item.get("name")): item
        for item in (saved_manifest.get("source_files") or [])
        if isinstance(item, dict) and item.get("name")
    }
    current_source_files = {
        str(item.get("name")): item
        for item in (current_manifest.get("source_files") or [])
        if isinstance(item, dict) and item.get("name")
    }
    has_current_loaded_files = any(item.get("loaded") for item in current_source_files.values())

    if not has_current_loaded_files:
        warnings.extend(saved_manifest_warnings)
        status = "fail" if failures else ("warning" if saved_status == "warning" or warnings else "pass")
        return {
            "status": status,
            "failures": _dedupe_preserve(failures),
            "warnings": _dedupe_preserve(warnings),
            "current_manifest": current_manifest,
            "current_multi_year_inputs": current_multi_year_inputs,
        }

    for name, saved_entry in saved_source_files.items():
        current_entry = current_source_files.get(name)
        if current_entry is None:
            failures.append(f"Saved PCIM references missing source file entry: {name}")
            continue
        if saved_entry.get("loaded") and not current_entry.get("loaded"):
            failures.append(f"PCIM source file was previously loaded but is no longer readable: {name}")
            continue
        if bool(saved_entry.get("loaded")) != bool(current_entry.get("loaded")):
            warnings.append(f"PCIM source file load state changed since last PCIM build: {name}")
        if saved_entry.get("content_hash") and current_entry.get("content_hash"):
            if saved_entry.get("content_hash") != current_entry.get("content_hash"):
                failures.append(f"PCIM source file changed after the last PCIM build: {name}")

    for name, current_entry in current_source_files.items():
        if current_entry.get("loaded") and name not in saved_source_files:
            failures.append(
                f"PCIM source state is stale: new multi-year source file exists but was not included in saved PCIM: {name}"
            )

    saved_years_available, _ = sort_fiscal_year_labels(saved_manifest.get("years_available", []))
    current_years_available, _ = sort_fiscal_year_labels(current_manifest.get("years_available", []))
    if saved_years_available != current_years_available:
        failures.append(
            "PCIM years_available is stale relative to current multi-year sources: "
            f"saved={saved_years_available}, current={current_years_available}"
        )

    saved_years_covered, _ = sort_fiscal_year_labels(
        saved_manifest.get("years_covered_in_multi_year_inputs", [])
    )
    current_years_covered, _ = sort_fiscal_year_labels(
        current_manifest.get("years_covered_in_multi_year_inputs", [])
    )
    if saved_years_covered != current_years_covered:
        failures.append(
            "PCIM years_covered_in_multi_year_inputs is stale relative to current multi-year sources: "
            f"saved={saved_years_covered}, current={current_years_covered}"
        )

    saved_missing_years, _ = sort_fiscal_year_labels(saved_manifest.get("missing_years", []))
    current_missing_years, _ = sort_fiscal_year_labels(current_manifest.get("missing_years", []))
    if saved_missing_years != current_missing_years:
        warnings.append(
            "PCIM missing_years differs from the current multi-year source state: "
            f"saved={saved_missing_years}, current={current_missing_years}"
        )

    if saved_multi_year_inputs is not None:
        saved_multi_year_covered, _ = sort_fiscal_year_labels(saved_multi_year_inputs.get("years_covered", []))
        current_multi_year_covered, _ = sort_fiscal_year_labels(current_multi_year_inputs.get("years_covered", []))
        if saved_multi_year_covered != current_multi_year_covered:
            failures.append(
                "Saved PCIM multi_year_inputs.years_covered does not match the current rebuilt multi-year inputs: "
                f"saved={saved_multi_year_covered}, current={current_multi_year_covered}"
            )

    warnings.extend(saved_manifest_warnings)
    warnings.extend(current_manifest.get("stale_source_warnings", []))
    status = "fail" if failures else ("warning" if current_manifest.get("status") == "warning" or warnings else "pass")
    return {
        "status": status,
        "failures": _dedupe_preserve(failures),
        "warnings": _dedupe_preserve(warnings),
        "current_manifest": current_manifest,
        "current_multi_year_inputs": current_multi_year_inputs,
    }
