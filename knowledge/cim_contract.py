from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from knowledge.company_memory import CompanyMemoryAggregateBuilder, parse_financial_year


CONTRACT_VERSION = "1.0"
MISSING_ITEM_SPECS = [
    {
        "missing_item": "free_cash_flow",
        "section": "financial_strength_inputs",
        "needed_by": ["graham", "buffett"],
        "reason": "Required to judge dividend sustainability and owner earnings quality",
    },
    {
        "missing_item": "operating_cash_flow",
        "section": "financial_strength_inputs",
        "needed_by": ["graham", "buffett"],
        "reason": "Required to assess internal cash generation and balance-sheet resilience",
    },
    {
        "missing_item": "net_cash_or_net_debt",
        "section": "financial_strength_inputs",
        "needed_by": ["graham", "buffett"],
        "reason": "Required to judge leverage conservatism and downside protection",
    },
    {
        "missing_item": "working_capital_signals",
        "section": "financial_strength_inputs",
        "needed_by": ["graham"],
        "reason": "Required to judge short-term liquidity and receivable discipline",
    },
    {
        "missing_item": "board_or_committee_references",
        "section": "governance_and_incentive_inputs",
        "needed_by": ["munger"],
        "reason": "Required to judge governance oversight and decision discipline",
    },
    {
        "missing_item": "management_compensation_signals",
        "section": "governance_and_incentive_inputs",
        "needed_by": ["munger"],
        "reason": "Required to judge incentives beyond generic equity issuance",
    },
    {
        "missing_item": "customer_revenue_concentration_quantification",
        "section": "business_economics_inputs",
        "needed_by": ["buffett", "lynch"],
        "reason": "Required to assess concentration risk and business resilience",
    },
    {
        "missing_item": "multi_year_growth_trend",
        "section": "growth_execution_inputs",
        "needed_by": ["fisher", "lynch"],
        "reason": "Required to judge whether growth claims show repeatable execution",
    },
]


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _evidence_id(source_year: str, source_artifact: str, source_item_id: Optional[str], fallback: str) -> str:
    item_part = source_item_id or fallback or "item"
    return f"ev_{_slug(source_year)}_{_slug(source_artifact)}_{_slug(item_part)}"


def _year_root(companies_root: Path, company: str, year: str) -> Path:
    return companies_root / company / year / "intelligence"


def _business_model_entry(year: str, cim_payload: Dict[str, Any]) -> Dict[str, Any]:
    business = cim_payload.get("business") or {}
    industry = business.get("industry_profile") or {}
    competitive = business.get("competitive_position") or {}
    dna = business.get("dna") or {}
    return {
        "year": year,
        "business_summary": industry.get("business_summary"),
        "business_model": industry.get("business_model"),
        "value_creation": industry.get("value_creation"),
        "characteristics": industry.get("characteristics", []),
        "competitive_position_summary": competitive.get("summary"),
        "source_year": year,
        "source_artifact": "company_intelligence.json",
        "source_item_id": None,
        "evidence_references": {
            "report_template": dna.get("report_template"),
            "question_modules": dna.get("question_modules", []),
            "supporting_modules": competitive.get("supporting_modules", []),
        },
    }


def _copy_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(item) for item in items]


def _text_blob(item: Dict[str, Any]) -> str:
    evidence_references = item.get("evidence_references") or {}
    parts = [
        item.get("value"),
        item.get("business_summary"),
        item.get("business_model"),
        item.get("project_name"),
        item.get("initiative"),
        item.get("promise"),
        item.get("risk"),
        item.get("action"),
        item.get("entity_name"),
        item.get("summary"),
        item.get("category"),
        item.get("status"),
        item.get("severity"),
        item.get("amount"),
        item.get("purpose"),
        item.get("benefit"),
        item.get("timeline"),
        item.get("source_chunk"),
    ]
    if isinstance(evidence_references, dict):
        parts.extend(
            [
                evidence_references.get("category"),
                evidence_references.get("severity"),
                evidence_references.get("confidence"),
                evidence_references.get("source_chunk"),
            ]
        )
    elif isinstance(evidence_references, list):
        for reference in evidence_references:
            if isinstance(reference, dict):
                parts.extend(
                    [
                        reference.get("category"),
                        reference.get("status"),
                        reference.get("confidence"),
                        reference.get("source_chunk"),
                    ]
                )
    return " ".join(str(part or "") for part in parts)


def _matches_keywords(item: Dict[str, Any], keywords: Iterable[str]) -> bool:
    text = _text_blob(item).lower()
    return any(keyword.lower() in text for keyword in keywords)


def _extract_reference_field(item: Dict[str, Any], field: str) -> Any:
    evidence_references = item.get("evidence_references")
    if isinstance(evidence_references, dict):
        return evidence_references.get(field)
    if isinstance(evidence_references, list):
        for reference in evidence_references:
            if isinstance(reference, dict) and reference.get(field) is not None:
                return reference.get(field)
    return None


def _signal_entry(item: Dict[str, Any], *, signal_type: str, note: Optional[str] = None) -> Dict[str, Any]:
    entry = {
        "signal_type": signal_type,
        "value": (
            item.get("value")
            or item.get("business_summary")
            or item.get("project_name")
            or item.get("initiative")
            or item.get("promise")
            or item.get("risk")
            or item.get("action")
            or item.get("entity_name")
        ),
        "source_year": item.get("source_year"),
        "source_artifact": item.get("source_artifact"),
        "source_item_id": item.get("source_item_id"),
        "evidence_ids": list(item.get("evidence_ids", [])),
        "category": item.get("category") or _extract_reference_field(item, "category"),
        "status": item.get("status") or _extract_reference_field(item, "status"),
        "confidence": item.get("confidence") or _extract_reference_field(item, "confidence"),
        "page": item.get("page") or _extract_reference_field(item, "page"),
        "amount": item.get("amount"),
        "purpose": item.get("purpose"),
        "benefit": item.get("benefit"),
        "timeline": item.get("timeline"),
        "evidence_references": item.get("evidence_references", {}),
    }
    if note:
        entry["note"] = note
    return entry


def _bucket_items_by_year(
    buckets: List[Dict[str, Any]],
    *,
    signal_type: str,
    keywords: Iterable[str],
    note: Optional[str] = None,
) -> List[Dict[str, Any]]:
    matched_buckets: List[Dict[str, Any]] = []
    for bucket in buckets:
        items = []
        for item in bucket.get("items", []):
            if _matches_keywords(item, keywords):
                items.append(_signal_entry(item, signal_type=signal_type, note=note))
        if items:
            matched_buckets.append({"year": bucket.get("year"), "items": items})
    return matched_buckets


def _flatten_buckets(buckets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flat = []
    for bucket in buckets:
        flat.extend(bucket.get("items", []))
    return flat


def _dedupe_missing_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for item in items:
        key = (item.get("section"), item.get("missing_item"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


class CIMContractBuilder:
    def __init__(self, company: str, companies_root: Path | str = Path("companies")):
        self.company = company
        self.companies_root = Path(companies_root)
        self.company_root = self.companies_root / company
        self.output_dir = self.company_root / "company_memory"

    def _ensure_company_memory(self) -> None:
        CompanyMemoryAggregateBuilder(
            company=self.company,
            companies_root=self.companies_root,
        ).build()

    def _load_company_memory_artifacts(self) -> Dict[str, Any]:
        return {
            "company_memory_index": _load_json(self.output_dir / "company_memory_index.json"),
            "yearly_intelligence_index": _load_json(self.output_dir / "yearly_intelligence_index.json"),
            "company_cim": _load_json(self.output_dir / "company_cim.json"),
            "strategy_timeline": _load_json(self.output_dir / "strategy_timeline.json"),
            "promise_tracker": _load_json(self.output_dir / "promise_tracker.json"),
            "risk_evolution": _load_json(self.output_dir / "risk_evolution.json"),
            "capital_allocation_timeline": _load_json(self.output_dir / "capital_allocation_timeline.json"),
            "entity_registry": _load_json(self.output_dir / "entity_registry.json"),
        }

    def _year_artifact_paths(self, year: str) -> Dict[str, str]:
        intelligence_dir = _year_root(self.companies_root, self.company, year)
        return {
            "company_intelligence.json": str(intelligence_dir / "company_intelligence.json"),
            "business_classification.json": str(intelligence_dir / "business_classification.json"),
            "business_blueprint.json": str(intelligence_dir / "business_blueprint.json"),
            "management_summary.json": str(intelligence_dir / "management_summary.json"),
        }

    def _load_year_payloads(self, years: List[str]) -> Dict[str, Dict[str, Any]]:
        payloads: Dict[str, Dict[str, Any]] = {}
        for year in years:
            intelligence_dir = _year_root(self.companies_root, self.company, year)
            payloads[year] = {
                "company_intelligence": _load_json(intelligence_dir / "company_intelligence.json"),
                "business_classification": _load_json(intelligence_dir / "business_classification.json"),
                "business_blueprint": _load_json(intelligence_dir / "business_blueprint.json"),
                "management_summary": _load_json(intelligence_dir / "management_summary.json"),
            }
        return payloads

    def _build_uncertainty_notes(
        self,
        available_years: List[str],
        yearly_payloads: Dict[str, Dict[str, Any]],
        company_memory_index: Dict[str, Any],
    ) -> Dict[str, Any]:
        incomplete_years = list(company_memory_index.get("incomplete_years", []))
        missing_sections = []
        for year in available_years:
            payloads = yearly_payloads.get(year, {})
            cim_payload = payloads.get("company_intelligence") or {}
            business = cim_payload.get("business") or {}
            management = cim_payload.get("management") or {}
            operations = cim_payload.get("operations") or {}
            financial = cim_payload.get("financial") or {}
            risk = cim_payload.get("risk") or {}
            if not (business.get("dna") or {}).get("business_dnas"):
                missing_sections.append({"year": year, "section": "business_dna_by_year", "reason": "No business DNAs available"})
            if not (business.get("industry_profile") or {}).get("business_model"):
                missing_sections.append({"year": year, "section": "business_model", "reason": "No business model summary available"})
            if not ((management.get("promises") or {}).get("items")):
                missing_sections.append({"year": year, "section": "promises", "reason": "No promise items available"})
            if not ((operations.get("projects") or {}).get("items")):
                missing_sections.append({"year": year, "section": "projects", "reason": "No project items available"})
            if not ((operations.get("initiatives") or {}).get("items")):
                missing_sections.append({"year": year, "section": "initiatives", "reason": "No initiative items available"})
            if not ((financial.get("capital_allocation") or {}).get("items")):
                missing_sections.append({"year": year, "section": "capital_allocation", "reason": "No capital allocation items available"})
            if not ((risk.get("identified") or {}).get("items")):
                missing_sections.append({"year": year, "section": "risks", "reason": "No identified risks available"})
        return {
            "incomplete_years": incomplete_years,
            "missing_sections": missing_sections,
            "missing_items": [],
        }

    def _build_cim_v1(self, artifacts: Dict[str, Any], yearly_payloads: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        company_memory_index = artifacts["company_memory_index"]
        company_cim = artifacts["company_cim"]
        promise_tracker = artifacts["promise_tracker"]
        entity_registry = artifacts["entity_registry"]

        available_years = list(company_memory_index.get("usable_years", []))
        yearly_snapshots = list(company_cim.get("yearly_snapshots", []))
        business_model = [
            _business_model_entry(year, yearly_payloads.get(year, {}).get("company_intelligence") or {})
            for year in available_years
            if yearly_payloads.get(year, {}).get("company_intelligence")
        ]

        cim_v1 = {
            "contract_version": CONTRACT_VERSION,
            "company": self.company,
            "available_years": available_years,
            "business_dna_by_year": [
                {
                    "year": snapshot["year"],
                    "items": _copy_items(snapshot.get("business_dnas", [])),
                }
                for snapshot in yearly_snapshots
            ],
            "business_model": business_model,
            "management_focus": [
                {
                    "year": snapshot["year"],
                    "items": _copy_items(snapshot.get("management_focus_areas", [])),
                }
                for snapshot in yearly_snapshots
            ],
            "projects": [
                {
                    "year": snapshot["year"],
                    "items": _copy_items(snapshot.get("major_projects", [])),
                }
                for snapshot in yearly_snapshots
            ],
            "promises": [
                {
                    "year": snapshot["year"],
                    "items": _copy_items(snapshot.get("major_promises", [])),
                }
                for snapshot in yearly_snapshots
            ],
            "initiatives": [
                {
                    "year": snapshot["year"],
                    "items": _copy_items(snapshot.get("key_initiatives", [])),
                }
                for snapshot in yearly_snapshots
            ],
            "risks": [
                {
                    "year": snapshot["year"],
                    "items": _copy_items(snapshot.get("risks", [])),
                }
                for snapshot in yearly_snapshots
            ],
            "capital_allocation": [
                {
                    "year": snapshot["year"],
                    "items": _copy_items(snapshot.get("capital_allocation_actions", [])),
                }
                for snapshot in yearly_snapshots
            ],
            "entities": _copy_items(entity_registry.get("entities", [])),
            "evidence_index": [],
            "source_artifacts": {
                "company_memory": [
                    "company_memory_index.json",
                    "yearly_intelligence_index.json",
                    "company_cim.json",
                    "strategy_timeline.json",
                    "promise_tracker.json",
                    "risk_evolution.json",
                    "capital_allocation_timeline.json",
                    "entity_registry.json",
                ],
                "yearly": {
                    year: self._year_artifact_paths(year)
                    for year in available_years
                },
            },
            "uncertainty_missing_data": self._build_uncertainty_notes(
                available_years,
                yearly_payloads,
                company_memory_index,
            ),
            "derived_context": {
                "promise_tracker": promise_tracker.get("promise_groups", []),
                "strategy_timeline": artifacts["strategy_timeline"].get("timeline", []),
                "risk_evolution": artifacts["risk_evolution"].get("timeline", []),
                "capital_allocation_timeline": artifacts["capital_allocation_timeline"].get("timeline", []),
            },
        }

        self._attach_evidence_index(cim_v1)
        return cim_v1

    def _attach_evidence_index(self, cim_v1: Dict[str, Any]) -> None:
        evidence_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        def register(item: Dict[str, Any], fallback: str) -> None:
            source_year = item.get("source_year")
            source_artifact = item.get("source_artifact")
            if not source_year or not source_artifact:
                return
            evidence_id = _evidence_id(
                source_year,
                source_artifact,
                item.get("source_item_id"),
                fallback,
            )
            evidence_map.setdefault(
                (source_year, source_artifact, evidence_id),
                {
                    "evidence_id": evidence_id,
                    "source_year": source_year,
                    "source_artifact": source_artifact,
                    "source_item_id": item.get("source_item_id"),
                    "evidence_references": item.get("evidence_references", {}),
                },
            )
            item["evidence_ids"] = [evidence_id]

        for section_name in (
            "business_dna_by_year",
            "management_focus",
            "projects",
            "promises",
            "initiatives",
            "risks",
            "capital_allocation",
        ):
            for year_bucket in cim_v1.get(section_name, []):
                for item in year_bucket.get("items", []):
                    fallback = f"{section_name}_{year_bucket.get('year')}_{item.get('value', '')}"
                    register(item, fallback)

        for item in cim_v1.get("business_model", []):
            register(item, f"business_model_{item.get('year')}")

        for item in cim_v1.get("entities", []):
            for mention in item.get("mentions", []):
                register(mention, f"entity_{item.get('entity_name')}")

        cim_v1["evidence_index"] = [
            evidence_map[key]
            for key in sorted(evidence_map.keys())
        ]

    def _latest_year(self, years: List[str]) -> Optional[str]:
        if not years:
            return None
        return max(years, key=parse_financial_year)

    def _find_year_bucket(self, buckets: List[Dict[str, Any]], year: Optional[str]) -> Dict[str, Any]:
        if not year:
            return {}
        for bucket in buckets:
            if bucket.get("year") == year:
                return bucket
        return {}

    def _find_business_model(self, entries: List[Dict[str, Any]], year: Optional[str]) -> Dict[str, Any]:
        if not year:
            return {}
        for entry in entries:
            if entry.get("year") == year:
                return entry
        return {}

    def _pcim_section_evidence(self, *groups: Dict[str, Any]) -> List[str]:
        evidence_ids: List[str] = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            items = group.get("items")
            if isinstance(items, list):
                for item in items:
                    evidence_ids.extend(item.get("evidence_ids", []))
            else:
                evidence_ids.extend(group.get("evidence_ids", []))
        return list(dict.fromkeys(evidence_ids))

    def _missing_item_record(self, *, missing_item: str, section: str, needed_by: List[str], reason: str) -> Dict[str, Any]:
        return {
            "missing_item": missing_item,
            "section": section,
            "needed_by": needed_by,
            "reason": reason,
            "status": "not_available_in_current_artifacts",
        }

    def _missing_items_for_section(self, section: str, present_signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        present_types = {item.get("signal_type") for item in present_signals}
        records = []
        for spec in MISSING_ITEM_SPECS:
            if spec["section"] != section:
                continue
            if spec["missing_item"] in present_types:
                continue
            records.append(
                self._missing_item_record(
                    missing_item=spec["missing_item"],
                    section=spec["section"],
                    needed_by=spec["needed_by"],
                    reason=spec["reason"],
                )
            )
        return records

    def _build_governance_and_incentive_inputs(self, cim_v1: Dict[str, Any]) -> Dict[str, Any]:
        capital = cim_v1.get("capital_allocation", [])
        risks = cim_v1.get("risks", [])
        promises = cim_v1.get("promises", [])
        management_focus = cim_v1.get("management_focus", [])

        equity_items = _bucket_items_by_year(
            capital,
            signal_type="equity_incentives",
            keywords=["rsu", "esop", "share-based", "equity-settled", "equity issuance"],
        )
        related_party_items = _bucket_items_by_year(
            capital,
            signal_type="related_party_exposure",
            keywords=["related party", "related-party", "advance in nature of loan", "repayable on demand", "section 185", "section 186"],
        )
        governance_flags = _bucket_items_by_year(
            risks,
            signal_type="governance_risk",
            keywords=["risk governance", "governance", "control", "procure-to-pay", "p2p", "vendor", "supplier code", "board", "committee"],
        )
        auditor_and_control = _bucket_items_by_year(
            capital,
            signal_type="auditor_or_control_observation",
            keywords=["according to the information", "no default", "statutory dues", "dispute", "auditor", "section 185", "section 186", "internal control"],
        )
        management_signals = _bucket_items_by_year(
            promises + management_focus,
            signal_type="incentive_or_conduct_signal",
            keywords=["code of conduct", "ethical", "risk-conscious", "reward", "compensation", "human rights", "posh"],
        )

        present = (
            _flatten_buckets(equity_items)
            + _flatten_buckets(related_party_items)
            + _flatten_buckets(governance_flags)
            + _flatten_buckets(auditor_and_control)
            + _flatten_buckets(management_signals)
        )
        return {
            "equity_incentives_by_year": equity_items,
            "related_party_and_control_items_by_year": related_party_items + auditor_and_control,
            "risk_governance_flags_by_year": governance_flags,
            "management_conduct_signals_by_year": management_signals,
            "uncertainty_notes": self._missing_items_for_section("governance_and_incentive_inputs", present),
        }

    def _build_business_economics_inputs(self, cim_v1: Dict[str, Any]) -> Dict[str, Any]:
        projects = cim_v1.get("projects", [])
        initiatives = cim_v1.get("initiatives", [])
        risks = cim_v1.get("risks", [])
        management_focus = cim_v1.get("management_focus", [])
        business_model = cim_v1.get("business_model", [])

        customer_and_scale = _bucket_items_by_year(
            initiatives + projects + management_focus,
            signal_type="customer_and_scale_signal",
            keywords=["customer", "messages/month", "ott", "whatsapp", "marquee enterprises", "product penetration", "nps", "csat", "customers", "throughput", "telco"],
        )
        pricing_and_margin = _bucket_items_by_year(
            initiatives + projects,
            signal_type="pricing_or_margin_signal",
            keywords=["high-margin", "margin", "pricing", "operating leverage", "efficiency", "deployment timelines", "downtime"],
        )
        concentration_and_recurrence = _bucket_items_by_year(
            risks + initiatives,
            signal_type="concentration_or_recurrence_signal",
            keywords=["customer concentration", "retention", "cohort", "revenue stability", "nps", "csat", "product penetration"],
        )

        present = (
            _flatten_buckets(customer_and_scale)
            + _flatten_buckets(pricing_and_margin)
            + _flatten_buckets(concentration_and_recurrence)
        )
        return {
            "business_model_by_year": business_model,
            "customer_and_scale_signals_by_year": customer_and_scale,
            "pricing_and_margin_signals_by_year": pricing_and_margin,
            "concentration_and_recurrence_signals_by_year": concentration_and_recurrence,
            "uncertainty_notes": self._missing_items_for_section("business_economics_inputs", present),
        }

    def _build_growth_execution_inputs(self, cim_v1: Dict[str, Any]) -> Dict[str, Any]:
        projects = cim_v1.get("projects", [])
        initiatives = cim_v1.get("initiatives", [])
        promises = cim_v1.get("promises", [])
        strategy_timeline = cim_v1.get("derived_context", {}).get("strategy_timeline", [])

        growth_claims = _bucket_items_by_year(
            initiatives + projects,
            signal_type="growth_claim",
            keywords=["scaled", "growth", "customers", "expansion", "deployment", "messages/month", "capacity", "market leadership", "partnership", "adoption"],
        )
        executed_promises = _bucket_items_by_year(
            promises,
            signal_type="execution_follow_through",
            keywords=["implemented", "maintain", "ensure", "repeat", "monitor", "security", "automation", "compliance"],
        )
        trend_markers = []
        for marker in strategy_timeline:
            trend_markers.append(dict(marker))

        present = _flatten_buckets(growth_claims) + _flatten_buckets(executed_promises)
        return {
            "projects_by_year": projects,
            "initiatives_by_year": initiatives,
            "promises_by_year": promises,
            "growth_claims_by_year": growth_claims,
            "executed_promises_by_year": executed_promises,
            "multi_year_trend_markers": trend_markers,
            "uncertainty_notes": self._missing_items_for_section("growth_execution_inputs", present),
        }

    def _build_story_vs_numbers_inputs(self, cim_v1: Dict[str, Any], business_understanding: Dict[str, Any]) -> Dict[str, Any]:
        initiatives = cim_v1.get("initiatives", [])
        projects = cim_v1.get("projects", [])
        management_focus = cim_v1.get("management_focus", [])

        numeric_support = _bucket_items_by_year(
            initiatives + projects,
            signal_type="numeric_support",
            keywords=["%", "customers", "messages/month", "lakhs", "bn", "mn", "nps", "csat", "patents"],
        )
        hype_or_unverified = _bucket_items_by_year(
            initiatives + projects + management_focus,
            signal_type="hype_or_unverified_claim",
            keywords=["market leader", "world’s largest", "world's largest", "transform", "greenfield", "reimagination", "gen ai", "ai", "leadership"],
        )
        confidence_notes = []
        for bucket in initiatives + projects + management_focus:
            notes = []
            for item in bucket.get("items", []):
                confidence = item.get("confidence") or _extract_reference_field(item, "confidence")
                if str(confidence).lower() in {"low", "medium"}:
                    notes.append(_signal_entry(item, signal_type="confidence_note", note=f"confidence={confidence}"))
            if notes:
                confidence_notes.append({"year": bucket.get("year"), "items": notes})

        present = _flatten_buckets(numeric_support) + _flatten_buckets(hype_or_unverified)
        return {
            "latest_business_view": business_understanding["latest_business_view"],
            "numeric_support_by_year": numeric_support,
            "hype_or_unverified_claims_by_year": hype_or_unverified,
            "evidence_confidence_notes": confidence_notes,
            "uncertainty_notes": self._missing_items_for_section("story_vs_numbers_inputs", present),
        }

    def _build_pcim_v1(self, cim_v1: Dict[str, Any]) -> Dict[str, Any]:
        available_years = list(cim_v1.get("available_years", []))
        latest_year = self._latest_year(available_years)
        latest_business_model = self._find_business_model(cim_v1.get("business_model", []), latest_year)
        latest_dna = self._find_year_bucket(cim_v1.get("business_dna_by_year", []), latest_year)
        latest_focus = self._find_year_bucket(cim_v1.get("management_focus", []), latest_year)

        business_understanding = {
            "latest_business_view": {
                "year": latest_year,
                "business_dnas": latest_dna.get("items", []),
                "business_model": latest_business_model,
                "management_focus": latest_focus.get("items", []),
            },
            "business_dna_by_year": cim_v1.get("business_dna_by_year", []),
            "business_model_by_year": cim_v1.get("business_model", []),
        }

        capital_allocation = cim_v1.get("capital_allocation", [])
        risks = cim_v1.get("risks", [])
        management_focus = cim_v1.get("management_focus", [])
        promises = cim_v1.get("promises", [])
        initiatives = cim_v1.get("initiatives", [])
        projects = cim_v1.get("projects", [])

        liquidity_signals = _bucket_items_by_year(
            risks + capital_allocation,
            signal_type="working_capital_signals",
            keywords=["cash and equivalents", "cash equivalents", "receivable", "working capital", "foreign currency", "liquidity", "cash"],
        )
        leverage_signals = _bucket_items_by_year(
            capital_allocation + risks,
            signal_type="net_cash_or_net_debt",
            keywords=["borrowings", "debt", "term loans", "loan", "default", "no default"],
        )
        dividend_signals = _bucket_items_by_year(
            capital_allocation,
            signal_type="dividend_payout",
            keywords=["dividend", "payout", "shareholders", "dividend distribution policy"],
        )
        auditor_signals = _bucket_items_by_year(
            capital_allocation,
            signal_type="auditor_observation",
            keywords=["according to the information", "auditor", "statutory dues", "dispute", "default", "section 185", "section 186", "deposits"],
        )
        related_party_financial_signals = _bucket_items_by_year(
            capital_allocation,
            signal_type="related_party_financial_exposure",
            keywords=["related party", "related-party", "advance in nature of loan", "repayable on demand"],
        )
        operating_cash_flow_signals = _bucket_items_by_year(
            capital_allocation + risks + projects,
            signal_type="operating_cash_flow",
            keywords=["operating cash flow", "cash flow from operations"],
        )
        free_cash_flow_signals = _bucket_items_by_year(
            capital_allocation + projects,
            signal_type="free_cash_flow",
            keywords=["free cash flow", "owner earnings"],
        )
        financial_strength_present = (
            _flatten_buckets(liquidity_signals)
            + _flatten_buckets(leverage_signals)
            + _flatten_buckets(dividend_signals)
            + _flatten_buckets(auditor_signals)
            + _flatten_buckets(related_party_financial_signals)
            + _flatten_buckets(operating_cash_flow_signals)
            + _flatten_buckets(free_cash_flow_signals)
        )

        governance_and_incentive_inputs = self._build_governance_and_incentive_inputs(cim_v1)
        business_economics_inputs = self._build_business_economics_inputs(cim_v1)
        growth_execution_inputs = self._build_growth_execution_inputs(cim_v1)
        story_vs_numbers_inputs = self._build_story_vs_numbers_inputs(cim_v1, business_understanding)

        pcim_v1 = {
            "contract_version": CONTRACT_VERSION,
            "company": self.company,
            "available_years": available_years,
            "business_understanding": business_understanding,
            "financial_strength_inputs": {
                "capital_allocation_by_year": capital_allocation,
                "working_capital_and_liquidity_signals_by_year": liquidity_signals,
                "leverage_and_default_signals_by_year": leverage_signals,
                "dividend_and_distribution_signals_by_year": dividend_signals,
                "auditor_and_statutory_signals_by_year": auditor_signals,
                "related_party_financial_exposures_by_year": related_party_financial_signals,
                "operating_cash_flow_signals_by_year": operating_cash_flow_signals,
                "free_cash_flow_signals_by_year": free_cash_flow_signals,
                "uncertainty_notes": [
                    note
                    for note in cim_v1.get("uncertainty_missing_data", {}).get("missing_sections", [])
                    if note.get("section") == "capital_allocation"
                ] + self._missing_items_for_section("financial_strength_inputs", financial_strength_present),
            },
            "management_quality_inputs": {
                "management_focus_by_year": management_focus,
                "promise_tracker": cim_v1.get("derived_context", {}).get("promise_tracker", []),
                "promises_by_year": promises,
            },
            "growth_quality_inputs": {
                "projects_by_year": projects,
                "initiatives_by_year": initiatives,
                "strategy_timeline": cim_v1.get("derived_context", {}).get("strategy_timeline", []),
            },
            "moat_inputs": {
                "business_dna_by_year": cim_v1.get("business_dna_by_year", []),
                "business_model_by_year": cim_v1.get("business_model", []),
                "entities": cim_v1.get("entities", []),
            },
            "capital_allocation_inputs": {
                "capital_allocation_by_year": capital_allocation,
                "promises_by_year": promises,
                "dividend_and_distribution_signals_by_year": dividend_signals,
                "equity_and_issuance_signals_by_year": _bucket_items_by_year(
                    capital_allocation,
                    signal_type="equity_issuance_or_compensation",
                    keywords=["rsu", "esop", "share-based", "equity issuance", "share capital"],
                ),
                "related_party_and_advance_signals_by_year": related_party_financial_signals,
            },
            "risk_inputs": {
                "risk_by_year": risks,
                "risk_evolution": cim_v1.get("derived_context", {}).get("risk_evolution", []),
            },
            "incentive_inputs": {
                "capital_allocation_by_year": capital_allocation,
                "promise_tracker": cim_v1.get("derived_context", {}).get("promise_tracker", []),
                "uncertainty_notes": [
                    note
                    for note in cim_v1.get("uncertainty_missing_data", {}).get("missing_sections", [])
                    if note.get("section") in {"promises", "capital_allocation"}
                ],
            },
            "simplicity_and_story_inputs": {
                "latest_business_view": business_understanding["latest_business_view"],
                "strategy_timeline": cim_v1.get("derived_context", {}).get("strategy_timeline", []),
                "focus_by_year": management_focus,
            },
            "governance_and_incentive_inputs": governance_and_incentive_inputs,
            "business_economics_inputs": business_economics_inputs,
            "growth_execution_inputs": growth_execution_inputs,
            "story_vs_numbers_inputs": story_vs_numbers_inputs,
            "evidence_map": {
                "business_understanding": self._pcim_section_evidence(latest_business_model, latest_dna, latest_focus),
                "financial_strength_inputs": [
                    evidence_id
                    for item in financial_strength_present
                    for evidence_id in item.get("evidence_ids", [])
                ],
                "management_quality_inputs": [
                    evidence_id
                    for bucket in promises + management_focus
                    for item in bucket.get("items", [])
                    for evidence_id in item.get("evidence_ids", [])
                ],
                "growth_quality_inputs": [
                    evidence_id
                    for bucket in projects + initiatives
                    for item in bucket.get("items", [])
                    for evidence_id in item.get("evidence_ids", [])
                ],
                "moat_inputs": [
                    evidence.get("evidence_id")
                    for evidence in cim_v1.get("evidence_index", [])
                    if "business" in evidence.get("evidence_id", "") or "entity" in evidence.get("evidence_id", "")
                ],
                "capital_allocation_inputs": [
                    evidence_id
                    for bucket in capital_allocation
                    for item in bucket.get("items", [])
                    for evidence_id in item.get("evidence_ids", [])
                ],
                "risk_inputs": [
                    evidence_id
                    for bucket in risks
                    for item in bucket.get("items", [])
                    for evidence_id in item.get("evidence_ids", [])
                ],
                "incentive_inputs": [
                    evidence_id
                    for bucket in promises + capital_allocation
                    for item in bucket.get("items", [])
                    for evidence_id in item.get("evidence_ids", [])
                ],
                "simplicity_and_story_inputs": self._pcim_section_evidence(latest_business_model, latest_focus),
                "governance_and_incentive_inputs": [
                    evidence_id
                    for bucket in governance_and_incentive_inputs.get("equity_incentives_by_year", [])
                    + governance_and_incentive_inputs.get("related_party_and_control_items_by_year", [])
                    + governance_and_incentive_inputs.get("risk_governance_flags_by_year", [])
                    + governance_and_incentive_inputs.get("management_conduct_signals_by_year", [])
                    for item in bucket.get("items", [])
                    for evidence_id in item.get("evidence_ids", [])
                ],
                "business_economics_inputs": [
                    evidence_id
                    for bucket in business_economics_inputs.get("customer_and_scale_signals_by_year", [])
                    + business_economics_inputs.get("pricing_and_margin_signals_by_year", [])
                    + business_economics_inputs.get("concentration_and_recurrence_signals_by_year", [])
                    for item in bucket.get("items", [])
                    for evidence_id in item.get("evidence_ids", [])
                ],
                "growth_execution_inputs": [
                    evidence_id
                    for bucket in growth_execution_inputs.get("projects_by_year", [])
                    + growth_execution_inputs.get("initiatives_by_year", [])
                    + growth_execution_inputs.get("promises_by_year", [])
                    + growth_execution_inputs.get("growth_claims_by_year", [])
                    + growth_execution_inputs.get("executed_promises_by_year", [])
                    for item in bucket.get("items", [])
                    for evidence_id in item.get("evidence_ids", [])
                ],
                "story_vs_numbers_inputs": [
                    evidence_id
                    for bucket in story_vs_numbers_inputs.get("numeric_support_by_year", [])
                    + story_vs_numbers_inputs.get("hype_or_unverified_claims_by_year", [])
                    + story_vs_numbers_inputs.get("evidence_confidence_notes", [])
                    for item in bucket.get("items", [])
                    for evidence_id in item.get("evidence_ids", [])
                ],
            },
            "uncertainty_missing_data": cim_v1.get("uncertainty_missing_data", {}),
            "source_cim": "cim_v1.json",
        }

        pcim_v1["uncertainty_missing_data"]["missing_items"] = _dedupe_missing_items(
            list(pcim_v1["uncertainty_missing_data"].get("missing_items", []))
            + pcim_v1["financial_strength_inputs"]["uncertainty_notes"]
            + governance_and_incentive_inputs.get("uncertainty_notes", [])
            + business_economics_inputs.get("uncertainty_notes", [])
            + growth_execution_inputs.get("uncertainty_notes", [])
            + story_vs_numbers_inputs.get("uncertainty_notes", [])
        )

        for key, values in list(pcim_v1["evidence_map"].items()):
            pcim_v1["evidence_map"][key] = list(dict.fromkeys(values))
        return pcim_v1

    def build(self) -> Dict[str, Path]:
        self._ensure_company_memory()
        artifacts = self._load_company_memory_artifacts()
        available_years = list((artifacts["company_memory_index"] or {}).get("usable_years", []))
        yearly_payloads = self._load_year_payloads(available_years)
        cim_v1 = self._build_cim_v1(artifacts, yearly_payloads)
        pcim_v1 = self._build_pcim_v1(cim_v1)

        written = {
            "cim_v1.json": _write_json(self.output_dir / "cim_v1.json", cim_v1),
            "pcim_v1.json": _write_json(self.output_dir / "pcim_v1.json", pcim_v1),
        }
        return written
