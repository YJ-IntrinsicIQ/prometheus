from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


YEAR_PATTERN = re.compile(r"^fy(\d{2,4})$", re.IGNORECASE)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
ENTITY_STOPWORDS = {
    "API",
    "Annual",
    "Board",
    "Build",
    "Built",
    "Business",
    "Channel",
    "Company",
    "Corporate",
    "Conduct",
    "Continue",
    "Continually",
    "Financial",
    "Framework",
    "Growth",
    "India",
    "Initiative",
    "Maintain",
    "Patent",
    "Platform",
    "Product",
    "Report",
    "Scale",
    "Scaled",
    "Strategic",
    "The",
    "Year",
}
GEOGRAPHY_NAMES = {
    "India",
    "UAE",
    "United States",
    "US",
    "Southeast Asia",
}
PARTNER_NAMES = {
    "Google",
    "Meta",
    "Truecaller",
}


def parse_financial_year(label: str) -> int:
    match = YEAR_PATTERN.match(str(label or "").strip())
    if not match:
        raise ValueError(f"Unrecognized financial year label: {label}")
    return int(match.group(1))


def _normalize_text(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return " ".join(normalized.split())


def _significant_tokens(value: Any) -> List[str]:
    return [
        token
        for token in _normalize_text(value).split()
        if token and token not in STOPWORDS
    ]


def _token_overlap(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    shared = left_set & right_set
    return len(shared) / max(len(left_set), len(right_set))


def _promise_theme_key(value: str) -> str:
    tokens = _significant_tokens(value)
    return " ".join(tokens[:8])


def _promises_match(left: str, right: str) -> bool:
    left_normalized = _normalize_text(left)
    right_normalized = _normalize_text(right)
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return True
    return _token_overlap(_significant_tokens(left), _significant_tokens(right)) >= 0.72


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _field_value(item: Dict[str, Any], field_names: Iterable[str]) -> str:
    for field_name in field_names:
        value = item.get(field_name)
        if value:
            return str(value)
    return ""


def _evidence_refs(item: Dict[str, Any]) -> Dict[str, Any]:
    refs: Dict[str, Any] = {}
    for key in ("page", "source_chunk", "confidence", "category", "timeline", "severity", "status"):
        value = item.get(key)
        if value not in (None, "", [], {}):
            refs[key] = value
    relationships = item.get("relationships")
    if relationships:
        refs["relationships"] = relationships
    return refs


def _selected_items(
    source_items: List[Dict[str, Any]],
    selected_texts: List[str],
    text_fields: Iterable[str],
    year: str,
    artifact_name: str,
) -> List[Dict[str, Any]]:
    if not selected_texts:
        selected_texts = [
            _field_value(item, text_fields)
            for item in source_items
            if _field_value(item, text_fields)
        ]

    selected: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()

    for text in selected_texts:
        for item in source_items:
            item_text = _field_value(item, text_fields)
            if item_text != text:
                continue
            item_id = str(item.get("id") or item_text)
            key = (year, item_id)
            if key in seen:
                continue
            seen.add(key)
            selected.append(
                {
                    "value": item_text,
                    "source_year": year,
                    "source_artifact": artifact_name,
                    "source_item_id": item.get("id"),
                    "evidence_references": _evidence_refs(item),
                }
            )
            break

    return selected


def _all_items(
    source_items: List[Dict[str, Any]],
    text_fields: Iterable[str],
    year: str,
    artifact_name: str,
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()

    for item in source_items:
        item_text = _field_value(item, text_fields)
        if not item_text:
            continue
        item_id = str(item.get("id") or item_text)
        key = (year, item_id)
        if key in seen:
            continue
        seen.add(key)
        selected.append(
            {
                "value": item_text,
                "source_year": year,
                "source_artifact": artifact_name,
                "source_item_id": item.get("id"),
                "evidence_references": _evidence_refs(item),
                "status": item.get("status"),
            }
        )

    return selected


def _selected_focus_areas(
    initiatives: List[Dict[str, Any]],
    selected_categories: List[str],
    year: str,
    artifact_name: str,
) -> List[Dict[str, Any]]:
    categories = selected_categories or sorted(
        {
            str(item.get("category"))
            for item in initiatives
            if item.get("category")
        }
    )
    selected: List[Dict[str, Any]] = []
    for category in categories:
        matching_ids = sorted(
            str(item.get("id"))
            for item in initiatives
            if item.get("category") == category and item.get("id")
        )
        evidence = [
            _evidence_refs(item)
            for item in initiatives
            if item.get("category") == category
        ][:5]
        selected.append(
            {
                "value": category,
                "source_year": year,
                "source_artifact": artifact_name,
                "source_item_id": matching_ids[0] if matching_ids else None,
                "source_item_ids": matching_ids,
                "evidence_references": evidence,
            }
        )
    return selected


def _dna_items(classification: Dict[str, Any], year: str) -> List[Dict[str, Any]]:
    items = []
    for dna in classification.get("business_dnas", []) or []:
        items.append(
            {
                "value": dna,
                "source_year": year,
                "source_artifact": "business_classification.json",
                "source_item_id": None,
                "evidence_references": {
                    "question_modules": classification.get("question_modules", []),
                    "confidence": classification.get("confidence"),
                    "rationale": classification.get("rationale", []),
                    "evidence_used": classification.get("evidence_used", []),
                },
            }
        )
    return items


def _risk_items(cim: Dict[str, Any], year: str) -> List[Dict[str, Any]]:
    items = []
    for item in (((cim.get("risk") or {}).get("identified") or {}).get("items") or []):
        value = item.get("risk")
        if not value:
            continue
        items.append(
            {
                "value": value,
                "source_year": year,
                "source_artifact": "company_intelligence.json",
                "source_item_id": item.get("id"),
                "evidence_references": _evidence_refs(item),
            }
        )
    return items


def _capital_items(cim: Dict[str, Any], summary: Dict[str, Any], year: str) -> List[Dict[str, Any]]:
    source_items = (((cim.get("financial") or {}).get("capital_allocation") or {}).get("items") or [])
    return _all_items(
        source_items,
        ("action",),
        year,
        "company_intelligence.json",
    )


def _project_items(cim: Dict[str, Any], summary: Dict[str, Any], year: str) -> List[Dict[str, Any]]:
    source_items = (((cim.get("operations") or {}).get("projects") or {}).get("items") or [])
    selected_texts = list(summary.get("major_projects", []) or [])
    return _selected_items(
        source_items,
        selected_texts,
        ("project_name",),
        year,
        "company_intelligence.json",
    )


def _promise_items(cim: Dict[str, Any], summary: Dict[str, Any], year: str) -> List[Dict[str, Any]]:
    source_items = (((cim.get("management") or {}).get("promises") or {}).get("items") or [])
    return _all_items(
        source_items,
        ("promise",),
        year,
        "company_intelligence.json",
    )


def _all_promise_items(cim: Dict[str, Any], year: str) -> List[Dict[str, Any]]:
    items = []
    for item in (((cim.get("management") or {}).get("promises") or {}).get("items") or []):
        value = item.get("promise")
        if not value:
            continue
        items.append(
            {
                "value": value,
                "source_year": year,
                "source_artifact": "company_intelligence.json",
                "source_item_id": item.get("id"),
                "evidence_references": _evidence_refs(item),
                "status": item.get("status") or "UNKNOWN",
            }
        )
    return items


def _initiative_items(cim: Dict[str, Any], summary: Dict[str, Any], year: str) -> List[Dict[str, Any]]:
    source_items = (((cim.get("operations") or {}).get("initiatives") or {}).get("items") or [])
    return _all_items(
        source_items,
        ("initiative",),
        year,
        "company_intelligence.json",
    )


def _focus_area_items(cim: Dict[str, Any], summary: Dict[str, Any], year: str) -> List[Dict[str, Any]]:
    initiatives = (((cim.get("operations") or {}).get("initiatives") or {}).get("items") or [])
    selected_categories = list(summary.get("management_focus_areas", []) or [])
    return _selected_focus_areas(
        initiatives,
        selected_categories,
        year,
        "management_summary.json",
    )


def _text_candidates(snapshot: Dict[str, Any]) -> List[Tuple[str, str]]:
    cim = snapshot["company_intelligence"]
    business = cim.get("business") or {}
    industry_profile = business.get("industry_profile") or {}
    candidates = []
    for field in ("business_summary", "business_model", "value_creation"):
        value = industry_profile.get(field)
        if value:
            candidates.append((str(value), "business_text"))
    for value in industry_profile.get("characteristics", []) or []:
        if value:
            candidates.append((str(value), "characteristic"))
    for item in snapshot["major_projects"]:
        candidates.append((item["value"], "project"))
    for item in snapshot["key_initiatives"]:
        candidates.append((item["value"], "initiative"))
    return candidates


def _detect_entity_type(name: str, text: str, origin: str) -> str:
    normalized = _normalize_text(text)
    if name in GEOGRAPHY_NAMES:
        return "geography"
    if name in PARTNER_NAMES:
        return "partner"
    if origin == "project":
        return "project"
    if "partner" in normalized or "telco" in normalized or "operator" in normalized:
        return "partner"
    if "platform" in normalized or "product" in normalized or "channel" in normalized:
        return "platform"
    if "uae" in normalized or "india" in normalized or "asia" in normalized or "united states" in normalized or "us " in f"{normalized} ":
        return "geography"
    return "named_entity"


def _extract_named_entities(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    found: Dict[Tuple[str, str], Dict[str, Any]] = {}
    year = snapshot["year"]
    for text, origin in _text_candidates(snapshot):
        for raw_name in re.findall(r"\b(?:[A-Z][A-Za-z0-9&.+/-]*|[A-Z]{2,})(?:\s+(?:[A-Z][A-Za-z0-9&.+/-]*|[A-Z]{2,}))*", text):
            name = raw_name.strip(" ,.;:()[]")
            if len(name) < 3:
                continue
            if name in ENTITY_STOPWORDS:
                continue
            entity_type = _detect_entity_type(name, text, origin)
            key = (entity_type, name)
            record = found.setdefault(
                key,
                {
                    "entity_name": name,
                    "entity_type": entity_type,
                    "mentions": [],
                },
            )
            mention = {
                "source_year": year,
                "source_artifact": "company_intelligence.json",
                "source_item_id": None,
                "evidence_references": {
                    "origin": origin,
                    "text": text,
                },
            }
            if mention not in record["mentions"]:
                record["mentions"].append(mention)
    return sorted(
        found.values(),
        key=lambda item: (item["entity_type"], item["entity_name"]),
    )


class CompanyMemoryAggregateBuilder:
    def __init__(self, company: str, companies_root: Path | str = Path("companies")):
        self.company = company
        self.companies_root = Path(companies_root)
        self.company_root = self.companies_root / company
        self.output_dir = self.company_root / "company_memory"

    def _discover_years(self) -> List[Path]:
        if not self.company_root.exists():
            return []
        return sorted(
            [
                path
                for path in self.company_root.iterdir()
                if path.is_dir() and YEAR_PATTERN.match(path.name)
            ],
            key=lambda path: parse_financial_year(path.name),
        )

    def _load_year_record(self, year_dir: Path) -> Dict[str, Any]:
        year = year_dir.name
        intelligence_dir = year_dir / "intelligence"
        cim_path = intelligence_dir / "company_intelligence.json"
        classification_path = intelligence_dir / "business_classification.json"
        summary_path = intelligence_dir / "management_summary.json"

        cim = _load_json(cim_path)
        classification = _load_json(classification_path)
        summary = _load_json(summary_path)

        available_artifacts = {
            "company_intelligence.json": cim is not None,
            "business_classification.json": classification is not None,
            "management_summary.json": summary is not None,
        }

        if cim is not None:
            status = "usable"
            reason = ""
        elif any(available_artifacts.values()):
            status = "partial"
            reason = "company_intelligence.json missing or unreadable"
        else:
            status = "missing"
            reason = "No usable intelligence artifacts found"

        return {
            "year": year,
            "sort_key": parse_financial_year(year),
            "status": status,
            "reason": reason,
            "paths": {
                "year_root": str(year_dir),
                "intelligence_dir": str(intelligence_dir),
            },
            "available_artifacts": available_artifacts,
            "company_intelligence": cim,
            "business_classification": classification or {},
            "management_summary": summary or {},
        }

    def _build_snapshot(self, year_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        cim = year_record["company_intelligence"]
        if cim is None:
            return None

        year = year_record["year"]
        classification = year_record["business_classification"]
        summary = year_record["management_summary"]

        snapshot = {
            "year": year,
            "business_dnas": _dna_items(classification, year),
            "management_focus_areas": _focus_area_items(cim, summary, year),
            "major_projects": _project_items(cim, summary, year),
            "major_promises": _promise_items(cim, summary, year),
            "key_initiatives": _initiative_items(cim, summary, year),
            "risks": _risk_items(cim, year),
            "capital_allocation_actions": _capital_items(cim, summary, year),
            "all_promises": _all_promise_items(cim, year),
            "company_intelligence": cim,
        }
        snapshot["important_entities"] = _extract_named_entities(snapshot)
        return snapshot

    def _build_promise_tracker(self, snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        groups: List[Dict[str, Any]] = []
        for snapshot in snapshots:
            for item in snapshot["all_promises"]:
                matched_group = None
                for group in groups:
                    if _promises_match(item["value"], group["representative_promise"]):
                        matched_group = group
                        break
                if matched_group is None:
                    matched_group = {
                        "normalized_promise_theme": _promise_theme_key(item["value"]) or _normalize_text(item["value"]),
                        "representative_promise": item["value"],
                        "yearly_mentions": [],
                        "first_seen_year": item["source_year"],
                        "latest_seen_year": item["source_year"],
                        "status": "UNKNOWN",
                        "source_references": [],
                    }
                    groups.append(matched_group)
                matched_group["yearly_mentions"].append(
                    {
                        "year": item["source_year"],
                        "promise": item["value"],
                        "source_artifact": item["source_artifact"],
                        "source_item_id": item["source_item_id"],
                        "status": item.get("status") or "UNKNOWN",
                    }
                )
                matched_group["source_references"].append(
                    {
                        "source_year": item["source_year"],
                        "source_artifact": item["source_artifact"],
                        "source_item_id": item["source_item_id"],
                        "evidence_references": item["evidence_references"],
                    }
                )
                years = [mention["year"] for mention in matched_group["yearly_mentions"]]
                matched_group["first_seen_year"] = min(years, key=parse_financial_year)
                matched_group["latest_seen_year"] = max(years, key=parse_financial_year)
                statuses = [mention["status"] for mention in matched_group["yearly_mentions"] if mention.get("status")]
                matched_group["status"] = statuses[-1] if statuses else "UNKNOWN"

        groups.sort(
            key=lambda item: (
                parse_financial_year(item["first_seen_year"]),
                item["normalized_promise_theme"],
            )
        )
        return {
            "company": self.company,
            "promise_groups": groups,
        }

    def _timeline_payload(self, snapshots: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        payload = []
        for snapshot in snapshots:
            payload.append(
                {
                    "year": snapshot["year"],
                    key: snapshot[key],
                }
            )
        return payload

    def _build_entity_registry(self, snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        registry: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for snapshot in snapshots:
            for entity in snapshot["important_entities"]:
                key = (entity["entity_type"], entity["entity_name"])
                current = registry.setdefault(
                    key,
                    {
                        "entity_name": entity["entity_name"],
                        "entity_type": entity["entity_type"],
                        "mentions": [],
                    },
                )
                for mention in entity["mentions"]:
                    if mention not in current["mentions"]:
                        current["mentions"].append(mention)

        entities = sorted(
            registry.values(),
            key=lambda item: (item["entity_type"], item["entity_name"]),
        )
        return {
            "company": self.company,
            "entities": entities,
        }

    def build(self) -> Dict[str, Path]:
        year_records = [self._load_year_record(year_dir) for year_dir in self._discover_years()]
        snapshots = [
            snapshot
            for snapshot in (
                self._build_snapshot(year_record)
                for year_record in year_records
            )
            if snapshot is not None
        ]

        company_memory_index = {
            "company": self.company,
            "discovered_years": [record["year"] for record in year_records],
            "ordered_years": [record["year"] for record in year_records],
            "usable_years": [record["year"] for record in year_records if record["status"] == "usable"],
            "incomplete_years": [
                {
                    "year": record["year"],
                    "status": record["status"],
                    "reason": record["reason"],
                }
                for record in year_records
                if record["status"] != "usable"
            ],
        }

        yearly_intelligence_index = {
            "company": self.company,
            "years": [
                {
                    "year": record["year"],
                    "sort_key": record["sort_key"],
                    "status": record["status"],
                    "reason": record["reason"],
                    "available_artifacts": record["available_artifacts"],
                    "paths": record["paths"],
                }
                for record in year_records
            ],
        }

        company_cim = {
            "metadata": {
                "company": self.company,
                "ordered_years": [snapshot["year"] for snapshot in snapshots],
                "usable_years": [snapshot["year"] for snapshot in snapshots],
            },
            "yearly_snapshots": [
                {
                    "year": snapshot["year"],
                    "business_dnas": snapshot["business_dnas"],
                    "management_focus_areas": snapshot["management_focus_areas"],
                    "major_projects": snapshot["major_projects"],
                    "major_promises": snapshot["major_promises"],
                    "key_initiatives": snapshot["key_initiatives"],
                    "risks": snapshot["risks"],
                    "capital_allocation_actions": snapshot["capital_allocation_actions"],
                    "important_entities": snapshot["important_entities"],
                }
                for snapshot in snapshots
            ],
        }

        strategy_timeline = {
            "company": self.company,
            "timeline": [
                {
                    "year": snapshot["year"],
                    "business_dnas": snapshot["business_dnas"],
                    "management_focus_areas": snapshot["management_focus_areas"],
                    "major_projects": snapshot["major_projects"],
                    "key_initiatives": snapshot["key_initiatives"],
                }
                for snapshot in snapshots
            ],
        }

        risk_evolution = {
            "company": self.company,
            "timeline": self._timeline_payload(snapshots, "risks"),
        }

        capital_allocation_timeline = {
            "company": self.company,
            "timeline": self._timeline_payload(snapshots, "capital_allocation_actions"),
        }

        files = {
            "company_memory_index.json": company_memory_index,
            "yearly_intelligence_index.json": yearly_intelligence_index,
            "company_cim.json": company_cim,
            "strategy_timeline.json": strategy_timeline,
            "promise_tracker.json": self._build_promise_tracker(snapshots),
            "risk_evolution.json": risk_evolution,
            "capital_allocation_timeline.json": capital_allocation_timeline,
            "entity_registry.json": self._build_entity_registry(snapshots),
        }

        written_paths: Dict[str, Path] = {}
        for filename, payload in files.items():
            written_paths[filename] = _write_json(self.output_dir / filename, payload)
        return written_paths
