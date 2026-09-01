from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from knowledge.company_memory import CompanyMemoryAggregateBuilder, parse_financial_year
from knowledge.company_year_eligibility import year_eligibility_status
from knowledge.business_identity import build_business_identity_manifest
from knowledge.company_memory.pcim_multi_year_builder import (
    PCIMMultiYearBuilder,
    canonicalize_fiscal_year_label,
)


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


def _financial_year_root(companies_root: Path, company: str, year: str) -> Path:
    return companies_root / company / year / "financials"


def _dedupe_strings(values: Iterable[Any]) -> List[str]:
    deduped: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


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


def _management_summary_bucket(year: str, summary_payload: Dict[str, Any]) -> Dict[str, Any]:
    grouped_sections = (
        "company_management_actions",
        "company_promises",
        "company_capabilities",
        "company_results",
        "risk_responses",
        "external_context",
        "accounting_disclosures",
        "governance_disclosures",
        "uncertain_items",
    )
    bucket = {"year": year}
    for section in grouped_sections:
        bucket[section] = _copy_items(summary_payload.get(section, []))
    bucket["management_identity_limitations"] = list(
        ((summary_payload.get("routing_validation") or {}).get("warnings")) or []
    )
    return bucket


def _copy_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(item) for item in items]


def _strip_source_chunk(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: _strip_source_chunk(value) for key, value in node.items() if key != "source_chunk"}
    if isinstance(node, list):
        return [_strip_source_chunk(item) for item in node]
    if isinstance(node, str) and "raw_financial_tables.json" in node:
        return node.replace("raw_financial_tables.json", "normalized_fundamentals.json")
    return node


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


def _filter_capital_buckets(
    buckets: List[Dict[str, Any]],
    *,
    groups: Iterable[str] = (),
    categories: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    target_groups = set(groups)
    target_categories = set(categories)
    filtered: List[Dict[str, Any]] = []
    for bucket in buckets:
        items = []
        for item in bucket.get("items", []):
            group = item.get("capital_allocation_group")
            category = item.get("canonical_category") or item.get("category")
            if target_groups and group in target_groups:
                items.append(dict(item))
                continue
            if target_categories and category in target_categories:
                items.append(dict(item))
        if items:
            filtered.append({"year": bucket.get("year"), "items": items})
    return filtered


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


def _append_unique(items: List[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _entry_has_value(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    for key in ("value_crore", "value_original", "value_per_share", "raw_number", "crore_shares", "value"):
        value = entry.get(key)
        if value not in (None, "", []):
            return True
    return False


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
            "financial_year_index": _load_json(self.output_dir / "financials" / "financial_year_index.json"),
            "financial_trends": _load_json(self.output_dir / "financials" / "financial_trends.json"),
            "financial_quality_evolution": _load_json(self.output_dir / "financials" / "financial_quality_evolution.json"),
            "capital_allocation_financial_timeline": _load_json(self.output_dir / "financials" / "capital_allocation_financial_timeline.json"),
            "ownership_evolution": _load_json(self.output_dir / "financials" / "ownership_evolution.json"),
            "financial_memory_summary": _load_json(self.output_dir / "financials" / "financial_memory_summary.json"),
            "financial_truth_pack": _load_json(self.output_dir / "financials" / "financial_truth_pack.json"),
            "financial_quality_summary": _load_json(self.output_dir / "financials" / "financial_quality_summary.json"),
            "financial_driver_attribution": _load_json(self.output_dir / "financials" / "financial_driver_attribution.json"),
            "owner_earnings_bridge": _load_json(self.output_dir / "financials" / "investor_financial_modules" / "owner_earnings_bridge.json"),
            "capital_allocation_roi_ledger": _load_json(self.output_dir / "financials" / "investor_financial_modules" / "capital_allocation_roi_ledger.json"),
            "working_capital_quality_drilldown": _load_json(self.output_dir / "financials" / "investor_financial_modules" / "working_capital_quality_drilldown.json"),
            "order_revenue_cash_conversion_tracker": _load_json(self.output_dir / "financials" / "investor_financial_modules" / "order_revenue_cash_conversion_tracker.json"),
            "per_share_compounding_analysis": _load_json(self.output_dir / "financials" / "investor_financial_modules" / "per_share_compounding_analysis.json"),
            "investor_financial_modules_manifest": _load_json(self.output_dir / "financials" / "investor_financial_modules" / "investor_financial_modules_manifest.json"),
        }

    def _year_artifact_paths(self, year: str) -> Dict[str, str]:
        intelligence_dir = _year_root(self.companies_root, self.company, year)
        financial_dir = _financial_year_root(self.companies_root, self.company, year)
        return {
            "company_intelligence.json": str(intelligence_dir / "company_intelligence.json"),
            "business_classification.json": str(intelligence_dir / "business_classification.json"),
            "business_blueprint.json": str(intelligence_dir / "business_blueprint.json"),
            "management_summary.json": str(intelligence_dir / "management_summary.json"),
            "normalized_fundamentals.json": str(financial_dir / "normalized_fundamentals.json"),
            "financial_ratios.json": str(financial_dir / "financial_ratios.json"),
            "financial_growth.json": str(financial_dir / "financial_growth.json"),
            "corporate_actions.json": str(financial_dir / "corporate_actions.json"),
            "shareholding_pattern.json": str(financial_dir / "shareholding_pattern.json"),
        }

    def _load_year_payloads(self, years: List[str]) -> Dict[str, Dict[str, Any]]:
        payloads: Dict[str, Dict[str, Any]] = {}
        for year in years:
            intelligence_dir = _year_root(self.companies_root, self.company, year)
            financial_dir = _financial_year_root(self.companies_root, self.company, year)
            payloads[year] = {
                "company_intelligence": _load_json(intelligence_dir / "company_intelligence.json"),
                "business_classification": _load_json(intelligence_dir / "business_classification.json"),
                "business_blueprint": _load_json(intelligence_dir / "business_blueprint.json"),
                "management_summary": _load_json(intelligence_dir / "management_summary.json"),
                "normalized_fundamentals": _load_json(financial_dir / "normalized_fundamentals.json"),
                "financial_validation_report": _load_json(financial_dir / "financial_validation_report.json"),
                "financial_reconciliation_report": _load_json(financial_dir / "financial_reconciliation_report.json"),
                "financial_ratios": _load_json(financial_dir / "financial_ratios.json"),
                "financial_growth": _load_json(financial_dir / "financial_growth.json"),
                "financial_quality_summary": _load_json(financial_dir / "financial_quality_summary.json"),
                "corporate_actions": _load_json(financial_dir / "corporate_actions.json"),
                "shareholding_pattern": _load_json(financial_dir / "shareholding_pattern.json"),
            }
        return payloads

    def _compact_metric_entry(
        self,
        year: str,
        field: str,
        entry: Dict[str, Any],
        *,
        include_original: bool = True,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(entry, dict):
            return None
        value_crore = entry.get("value_crore")
        value_original = entry.get("value_original")
        if value_crore is None and value_original in (None, "", []):
            return None
        compact = {
            "field": field,
            "source_year": year,
            "source_artifact": "normalized_fundamentals.json",
            "source_page": entry.get("source_page"),
            "basis": entry.get("basis") or entry.get("period") or "unknown",
            "confidence": entry.get("confidence"),
            "warnings": list(entry.get("warnings", [])) if isinstance(entry.get("warnings"), list) else [],
        }
        if value_crore is not None:
            compact["value_crore"] = value_crore
        if include_original:
            compact["value_original"] = value_original
            compact["unit_original"] = entry.get("unit_original")
        return compact

    def _compact_ratio_item(self, year: str, name: str, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict) or item.get("value") is None:
            return None
        return {
            "metric": name,
            "value": item.get("value"),
            "unit": item.get("unit"),
            "basis": item.get("basis") or "unknown",
            "confidence": item.get("confidence"),
            "warnings": list(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else [],
            "source_year": year,
            "source_artifact": "financial_ratios.json",
            "formula": item.get("formula"),
        }

    def _pcim_metric_value(
        self,
        *,
        metric: str,
        value: Any,
        unit: str,
        period: str,
        basis: str,
        confidence: Any,
        source_artifacts: Iterable[Any],
        warnings: Iterable[Any] = (),
        limitations: Iterable[Any] = (),
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        payload = {
            "metric": metric,
            "value": value,
            "unit": unit,
            "period": period,
            "basis": basis or "unknown",
            "confidence": confidence or "missing",
            "source_artifacts": _dedupe_strings(source_artifacts),
            "warnings": _dedupe_strings(warnings),
            "limitations": _dedupe_strings(limitations),
        }
        if extra:
            payload.update({key: value for key, value in extra.items() if value not in (None, "", [], {})})
        return payload

    def _metric_value_from_normalized(
        self,
        year: str,
        metric: str,
        entry: Dict[str, Any],
        *,
        unit_fallback: str = "₹ crore",
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(entry, dict):
            return None
        value = entry.get("value_crore")
        unit = unit_fallback
        if value is None:
            for key, detected_unit in (
                ("value_per_share", "per share"),
                ("raw_number", "count"),
                ("crore_shares", "crore shares"),
                ("value", entry.get("unit") or unit_fallback),
            ):
                if entry.get(key) is not None:
                    value = entry.get(key)
                    unit = detected_unit
                    break
        if value is None:
            return None
        return self._pcim_metric_value(
            metric=metric,
            value=value,
            unit=unit,
            period=year,
            basis=entry.get("basis") or entry.get("period") or "unknown",
            confidence=entry.get("confidence"),
            source_artifacts=[entry.get("source_artifact") or "normalized_fundamentals.json"],
            warnings=entry.get("warnings", []),
            limitations=entry.get("limitations", []),
        )

    def _metric_value_from_ratio(
        self,
        year: str,
        metric: str,
        item: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict) or item.get("value") is None:
            return None
        return self._pcim_metric_value(
            metric=metric,
            value=item.get("value"),
            unit=item.get("unit") or "",
            period=year,
            basis=item.get("basis") or "unknown",
            confidence=item.get("confidence"),
            source_artifacts=item.get("source_artifacts", []) or ["financial_ratios.json"],
            warnings=item.get("warnings", []),
            limitations=[],
            extra={"formula": item.get("formula")},
        )

    def _metric_value_from_growth(
        self,
        year: str,
        metric: str,
        item: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        return self._pcim_metric_value(
            metric=metric,
            value=item.get("growth_percent"),
            unit="%",
            period=item.get("current_year") or year,
            basis=item.get("basis") or "unknown",
            confidence=item.get("confidence"),
            source_artifacts=["financial_growth.json"],
            warnings=item.get("warnings", []),
            limitations=[],
            extra={
                "absolute_change": item.get("absolute_change"),
                "cagr_percent": item.get("cagr_percent"),
            },
        )

    def _quality_metric_bundle(
        self,
        *,
        year: str,
        section_name: str,
        section: Dict[str, Any],
        source_artifact: str = "financial_quality_summary.json",
    ) -> Dict[str, Any]:
        return {
            "period": year,
            "section": section_name,
            "assessment": section.get("assessment") or section.get("status") or "insufficient_data",
            "confidence": section.get("confidence") or "missing",
            "source_artifacts": [source_artifact],
            "warnings": _dedupe_strings(section.get("warnings", [])),
            "limitations": _dedupe_strings(section.get("limitations", [])),
            "highlights": _dedupe_strings(section.get("highlights", []) or section.get("signals", [])),
            "evidence_metrics": section.get("evidence_metrics") or section.get("metrics") or {},
            "summary": section.get("summary", ""),
        }

    def _compact_growth_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        year = item.get("current_year") or item.get("year")
        if not year:
            return None
        return {
            "metric": item.get("metric"),
            "source_year": year,
            "source_artifact": "financial_growth.json",
            "growth_percent": item.get("growth_percent"),
            "cagr_percent": item.get("cagr_percent"),
            "absolute_change": item.get("absolute_change"),
            "basis": item.get("basis") or "unknown",
            "confidence": item.get("confidence"),
            "warnings": list(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else [],
        }

    def _compact_trend_series(self, payload: Dict[str, Any], metric: str, container: str) -> Optional[Dict[str, Any]]:
        section = payload.get(container, {})
        item = section.get(metric, {}) if isinstance(section, dict) else {}
        series = item.get("series", []) if isinstance(item, dict) else []
        if not isinstance(series, list) or not series:
            return None
        compact_series = []
        for point in series:
            if not isinstance(point, dict):
                continue
            compact_series.append(
                {
                    "year": point.get("year"),
                    "value": point.get("value"),
                    "basis": point.get("basis") or payload.get("basis") or "unknown",
                    "source_artifact": point.get("source_artifact") or "financial_trends.json",
                    "confidence": point.get("confidence"),
                    "warnings": list(point.get("warnings", [])) if isinstance(point.get("warnings"), list) else [],
                }
            )
        if not compact_series:
            return None
        return {
            "metric": metric,
            "unit": item.get("unit"),
            "series": compact_series,
            "comparability_warnings": list(item.get("comparability_warnings", []))
            if isinstance(item.get("comparability_warnings"), list)
            else [],
            "source_artifact": "financial_trends.json",
        }

    def _compact_financial_driver_inputs(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        attributions = []
        for item in payload.get("attributions", []) if isinstance(payload.get("attributions"), list) else []:
            if not isinstance(item, dict):
                continue
            attributions.append(
                {
                    "metric": item.get("metric"),
                    "movement": item.get("movement"),
                    "period": item.get("period"),
                    "possible_driver": item.get("possible_driver"),
                    "driver_type": item.get("driver_type"),
                    "supporting_event": item.get("supporting_event"),
                    "confidence": item.get("confidence"),
                    "causality_status": item.get("causality_status"),
                    "evidence_ids": list(item.get("evidence_ids", [])) if isinstance(item.get("evidence_ids"), list) else [],
                    "source_artifacts": list(item.get("source_artifacts", [])) if isinstance(item.get("source_artifacts"), list) else [],
                    "warnings": list(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else [],
                    "verification_questions": list(item.get("verification_questions", []))
                    if isinstance(item.get("verification_questions"), list)
                    else [],
                }
            )
        return {
            "status": payload.get("status"),
            "years_covered": list(payload.get("years_covered", [])) if isinstance(payload.get("years_covered"), list) else [],
            "attributions": attributions[:12],
            "warnings": list(payload.get("warnings", [])) if isinstance(payload.get("warnings"), list) else [],
            "limitations": list(payload.get("limitations", [])) if isinstance(payload.get("limitations"), list) else [],
            "source_artifact": "financial_driver_attribution.json",
        }

    def _financial_artifact_manifest(
        self,
        available_years: List[str],
        yearly_payloads: Dict[str, Dict[str, Any]],
        company_artifacts: Dict[str, Any],
    ) -> Dict[str, Any]:
        entries: List[Dict[str, Any]] = []
        warnings: List[str] = []
        years_covered: List[str] = []

        def add_entry(path: Path, years_detected: List[str]) -> None:
            exists = path.exists()
            entry = {
                "name": path.name,
                "path": str(path),
                "exists": exists,
                "loaded": False,
                "years_detected": years_detected,
                "warnings": [],
            }
            if exists:
                payload = _load_json(path)
                entry["loaded"] = isinstance(payload, dict) and bool(payload)
                entry["modified_at"] = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
                if not entry["loaded"]:
                    entry["warnings"].append("Artifact is empty or malformed.")
            else:
                entry["warnings"].append("Artifact missing.")
            entries.append(entry)

        for year in available_years:
            fin_root = _financial_year_root(self.companies_root, self.company, year)
            add_entry(fin_root / "normalized_fundamentals.json", [year])
            add_entry(fin_root / "financial_validation_report.json", [year])
            add_entry(fin_root / "financial_reconciliation_report.json", [year])
            add_entry(fin_root / "financial_ratios.json", [year])
            add_entry(fin_root / "financial_growth.json", [year])
            add_entry(fin_root / "financial_quality_summary.json", [year])
            add_entry(fin_root / "corporate_actions.json", [year])
            add_entry(fin_root / "shareholding_pattern.json", [year])

            year_payload = yearly_payloads.get(year, {})
            if year_payload.get("normalized_fundamentals"):
                years_covered.append(year)
            ratios = year_payload.get("financial_ratios") or {}
            growth = year_payload.get("financial_growth") or {}
            validation = year_payload.get("financial_validation_report") or {}
            reconciliation = year_payload.get("financial_reconciliation_report") or {}
            quality_summary = year_payload.get("financial_quality_summary") or {}
            corp = year_payload.get("corporate_actions") or {}
            share = year_payload.get("shareholding_pattern") or {}
            if not validation:
                _append_unique(warnings, f"{year}: financial validation missing.")
            if not reconciliation:
                _append_unique(warnings, f"{year}: financial reconciliation missing.")
            if not ratios:
                _append_unique(warnings, f"{year}: financial ratios missing.")
            if not growth:
                _append_unique(warnings, f"{year}: financial growth missing.")
            if not quality_summary:
                _append_unique(warnings, f"{year}: financial quality summary missing.")
            if not corp:
                _append_unique(warnings, f"{year}: corporate actions missing.")
            if not share:
                _append_unique(warnings, f"{year}: shareholding pattern missing.")

        company_fin_root = self.output_dir / "financials"
        add_entry(company_fin_root / "financial_year_index.json", list(company_artifacts.get("financial_year_index", {}).get("years_used", [])))
        add_entry(company_fin_root / "financial_trends.json", list(company_artifacts.get("financial_trends", {}).get("years_covered", [])))
        add_entry(company_fin_root / "financial_quality_evolution.json", list(company_artifacts.get("financial_quality_evolution", {}).get("years_covered", [])))
        add_entry(company_fin_root / "capital_allocation_financial_timeline.json", list(company_artifacts.get("capital_allocation_financial_timeline", {}).get("years_covered", [])))
        add_entry(company_fin_root / "ownership_evolution.json", list(company_artifacts.get("ownership_evolution", {}).get("years_covered", [])))
        add_entry(company_fin_root / "financial_memory_summary.json", list(company_artifacts.get("financial_memory_summary", {}).get("years_covered", [])))
        add_entry(company_fin_root / "financial_quality_summary.json", list(company_artifacts.get("financial_quality_summary", {}).get("years_covered", [])))
        add_entry(company_fin_root / "financial_driver_attribution.json", list(company_artifacts.get("financial_driver_attribution", {}).get("years_covered", [])))

        if company_artifacts.get("financial_trends"):
            for year in company_artifacts["financial_trends"].get("years_covered", []):
                if year not in years_covered:
                    years_covered.append(year)

        if len(years_covered) <= 1:
            _append_unique(warnings, "Only one financial year available.")

        trends = company_artifacts.get("financial_trends") or {}
        quality = company_artifacts.get("financial_quality_summary") or {}
        for warning in trends.get("warnings", []) if isinstance(trends.get("warnings"), list) else []:
            if any(token in str(warning).lower() for token in ("cfo", "fcf", "basis mismatch", "shareholding", "comparability")):
                _append_unique(warnings, str(warning))
        for item in quality.get("missing_data", []) if isinstance(quality.get("missing_data"), list) else []:
            if any(token in str(item).lower() for token in ("cfo", "fcf", "share count")):
                _append_unique(warnings, str(item))

        available_set = set(available_years)
        covered_set = set(years_covered)
        extra_years = sorted(covered_set - available_set)
        missing_years = sorted(available_set - covered_set)
        if extra_years:
            diagnostics = []
            for year in extra_years:
                status = year_eligibility_status(
                    company=self.company,
                    company_root=self.company_root,
                    year=year,
                )
                introducing_artifacts = [
                    entry["name"]
                    for entry in entries
                    if year in entry.get("years_detected", [])
                ]
                diagnostics.append(
                    {
                        "year": year,
                        "canonical_status": status.get("status"),
                        "reason": status.get("reason"),
                        "missing_required_artifacts": status.get("missing_required_artifacts", []),
                        "introduced_by": introducing_artifacts,
                    }
                )
            raise ValueError(
                "financial years mismatch company years: unexpected financial years "
                f"{extra_years}; diagnostics={diagnostics}"
            )
        if missing_years:
            _append_unique(warnings, "Financial artifacts do not cover all company years: " + ", ".join(missing_years))

        loaded = [entry for entry in entries if entry["loaded"]]
        if not loaded:
            status = "fail"
        elif warnings or any(entry["warnings"] for entry in entries):
            status = "warning"
        else:
            status = "pass"

        for entry in entries:
            if entry["warnings"]:
                warnings.extend(f"{entry['name']}: {warning}" for warning in entry["warnings"])

        loaded_entries = [entry for entry in entries if entry.get("loaded") and entry.get("modified_at")]
        latest_generated_at = ""
        if loaded_entries:
            latest_generated_at = max(str(entry.get("modified_at") or "") for entry in loaded_entries)

        return {
            "financial_artifacts_used": entries,
            "financial_years_covered": sorted(set(years_covered), key=parse_financial_year),
            "financial_status": status,
            "financial_warnings": list(dict.fromkeys(warnings)),
            "latest_generated_at": latest_generated_at,
            "limitations": [
                warning for warning in list(dict.fromkeys(warnings))
                if any(token in warning.lower() for token in ("missing", "unknown", "incomplete"))
            ],
        }

    def _build_cim_financial_intelligence(
        self,
        available_years: List[str],
        yearly_payloads: Dict[str, Dict[str, Any]],
        artifacts: Dict[str, Any],
    ) -> Dict[str, Any]:
        fundamentals = []
        ratios = []
        growth = []
        corporate_actions = []
        shareholding = []
        for year in available_years:
            payload = yearly_payloads.get(year, {})
            normalized = payload.get("normalized_fundamentals") or {}
            if normalized:
                fundamentals.append({"year": year, "artifact": _strip_source_chunk(normalized)})
            ratio_payload = payload.get("financial_ratios") or {}
            if ratio_payload:
                ratios.append({"year": year, "artifact": _strip_source_chunk(ratio_payload)})
            growth_payload = payload.get("financial_growth") or {}
            if growth_payload:
                growth.append({"year": year, "artifact": _strip_source_chunk(growth_payload)})
            corp_payload = payload.get("corporate_actions") or {}
            if corp_payload:
                corporate_actions.append({"year": year, "artifact": _strip_source_chunk(corp_payload)})
            share_payload = payload.get("shareholding_pattern") or {}
            if share_payload:
                shareholding.append({"year": year, "artifact": _strip_source_chunk(share_payload)})

        year_index = _strip_source_chunk(artifacts.get("financial_year_index") or {})
        trends = _strip_source_chunk(artifacts.get("financial_trends") or {})
        quality_evolution = _strip_source_chunk(artifacts.get("financial_quality_evolution") or {})
        capital_timeline = _strip_source_chunk(artifacts.get("capital_allocation_financial_timeline") or {})
        ownership_evolution = _strip_source_chunk(artifacts.get("ownership_evolution") or {})
        memory_summary = _strip_source_chunk(artifacts.get("financial_memory_summary") or {})
        quality = _strip_source_chunk(artifacts.get("financial_quality_summary") or {})
        attribution = _strip_source_chunk(artifacts.get("financial_driver_attribution") or {})
        limitations: List[str] = []
        for source in (year_index, trends, quality_evolution, capital_timeline, ownership_evolution, memory_summary, quality, attribution):
            if isinstance(source.get("limitations"), list):
                for item in source["limitations"]:
                    _append_unique(limitations, str(item))
        return {
            "fundamentals": fundamentals,
            "ratios": ratios,
            "growth": growth,
            "year_index": year_index,
            "trends": trends,
            "quality_evolution": quality_evolution,
            "capital_allocation_financial_timeline": capital_timeline,
            "ownership_evolution": ownership_evolution,
            "memory_summary": memory_summary,
            "quality_summary": quality,
            "driver_attribution": attribution,
            "corporate_actions": corporate_actions,
            "shareholding_pattern": shareholding,
            "limitations": limitations,
        }

    def _build_cim_financials(
        self,
        available_years: List[str],
        yearly_payloads: Dict[str, Dict[str, Any]],
        artifacts: Dict[str, Any],
    ) -> Dict[str, Any]:
        latest_year = available_years[-1] if available_years else ""
        latest_payload = yearly_payloads.get(latest_year, {}) if latest_year else {}
        normalized = latest_payload.get("normalized_fundamentals") or {}
        ratios = latest_payload.get("financial_ratios") or {}
        growth = latest_payload.get("financial_growth") or {}
        validation = latest_payload.get("financial_validation_report") or {}
        reconciliation = latest_payload.get("financial_reconciliation_report") or {}
        quality = latest_payload.get("financial_quality_summary") or {}
        corporate_actions = latest_payload.get("corporate_actions") or {}
        shareholding = latest_payload.get("shareholding_pattern") or {}
        manifest = self._financial_artifact_manifest(available_years, yearly_payloads, artifacts)
        memory_summary = artifacts.get("financial_memory_summary") or {}

        ratio_map = (ratios.get("ratios") or {}) if isinstance(ratios, dict) else {}
        growth_map = (growth.get("growth_metrics") or {}) if isinstance(growth, dict) else {}
        quality_sections = (quality.get("sections") or {}) if isinstance(quality.get("sections"), dict) else {}

        def growth_item(name: str) -> Optional[Dict[str, Any]]:
            items = growth_map.get(name) or []
            if isinstance(items, list) and items:
                return self._metric_value_from_growth(latest_year, name, items[0])
            return None

        def ratio_item(name: str) -> Optional[Dict[str, Any]]:
            return self._metric_value_from_ratio(latest_year, name, ratio_map.get(name) or {})

        def normalized_item(section: str, field: str, metric: Optional[str] = None, unit_fallback: str = "₹ crore") -> Optional[Dict[str, Any]]:
            return self._metric_value_from_normalized(
                latest_year,
                metric or field,
                ((normalized.get(section) or {}).get(field) or {}),
                unit_fallback=unit_fallback,
            )

        warnings: List[str] = []
        limitations: List[str] = []
        for payload in (normalized, validation, reconciliation, ratios, growth, quality, corporate_actions, shareholding):
            if isinstance(payload.get("warnings"), list):
                for item in payload.get("warnings", []):
                    _append_unique(warnings, str(item))
            if isinstance(payload.get("limitations"), list):
                for item in payload.get("limitations", []):
                    _append_unique(limitations, str(item))
        for item in manifest.get("financial_warnings", []):
            _append_unique(warnings, str(item))
        for item in manifest.get("limitations", []):
            _append_unique(limitations, str(item))

        def compact_mapping(pairs: List[Tuple[str, Optional[Dict[str, Any]]]]) -> Dict[str, Dict[str, Any]]:
            return {
                key: value
                for key, value in pairs
                if value is not None
            }

        return {
            "basis_used": normalized.get("preferred_basis") or ratios.get("basis_used") or growth.get("basis_used") or quality.get("basis_used") or "unknown",
            "basis_confidence": normalized.get("basis_confidence") or ratios.get("basis_confidence") or growth.get("basis_confidence") or "missing",
            "core_fundamentals": compact_mapping(
                [
                    ("revenue", normalized_item("profit_and_loss", "revenue")),
                    ("pat", normalized_item("profit_and_loss", "pat")),
                    ("cfo", normalized_item("cash_flow", "cfo")),
                    ("capex", normalized_item("cash_flow", "capex")),
                    ("net_worth", normalized_item("balance_sheet", "net_worth")),
                    ("total_debt", normalized_item("balance_sheet", "total_debt")),
                    ("cash_and_equivalents", normalized_item("balance_sheet", "cash_and_equivalents")),
                ]
            ),
            "profitability": compact_mapping(
                [
                    ("gross_margin", ratio_item("gross_margin")),
                    ("ebitda_margin", ratio_item("ebitda_margin")),
                    ("ebit_margin", ratio_item("ebit_margin")),
                    ("opm", ratio_item("opm")),
                    ("npm", ratio_item("npm")),
                ]
            ),
            "growth": compact_mapping(
                [
                    ("revenue", growth_item("revenue")),
                    ("pat", growth_item("pat")),
                    ("eps_basic", growth_item("eps_basic")),
                    ("book_value_per_share", growth_item("book_value_per_share")),
                ]
            ),
            "return_on_capital": compact_mapping(
                [
                    ("roe", ratio_item("roe")),
                    ("roce", ratio_item("roce")),
                    ("roa", ratio_item("roa")),
                ]
            ),
            "cash_conversion": compact_mapping(
                [
                    ("cfo_to_pat", ratio_item("cfo_to_pat")),
                    ("fcf", ratio_item("fcf")),
                    ("fcf_to_pat", ratio_item("fcf_to_pat")),
                    ("fcf_margin", ratio_item("fcf_margin")),
                ]
            ),
            "balance_sheet": compact_mapping(
                [
                    ("debt_to_equity", ratio_item("debt_to_equity")),
                    ("net_debt", ratio_item("net_debt")),
                    ("cash_and_equivalents", normalized_item("balance_sheet", "cash_and_equivalents")),
                    ("reserves", normalized_item("balance_sheet", "reserves")),
                ]
            ),
            "working_capital": compact_mapping(
                [
                    ("receivable_days", ratio_item("receivable_days")),
                    ("inventory_days", ratio_item("inventory_days")),
                    ("payable_days", ratio_item("payable_days")),
                    ("cash_conversion_cycle", ratio_item("cash_conversion_cycle")),
                    ("receivables_growth", growth_item("receivables")),
                    ("inventory_growth", growth_item("inventory")),
                    ("payables_growth", growth_item("payables")),
                ]
            ),
            "per_share": compact_mapping(
                [
                    ("eps_basic", ratio_item("eps_basic")),
                    ("eps_diluted", ratio_item("eps_diluted")),
                    ("book_value_per_share", ratio_item("book_value_per_share")),
                    ("dividend_per_share", ratio_item("dividend_per_share")),
                    ("payout_ratio", ratio_item("payout_ratio")),
                    ("shares_outstanding", normalized_item("share_data", "shares_outstanding", unit_fallback="count")),
                ]
            ),
            "corporate_actions": {
                "status": corporate_actions.get("status"),
                "actions": [
                    {
                        "action_type": item.get("action_type"),
                        "period": item.get("year") or latest_year,
                        "impact_on_share_count": item.get("impact_on_share_count"),
                        "impact_on_eps_comparability": item.get("impact_on_eps_comparability"),
                        "source_artifacts": ["corporate_actions.json"],
                        "warnings": list(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else [],
                    }
                    for item in corporate_actions.get("actions", []) if isinstance(item, dict)
                ][:10],
                "warnings": list(corporate_actions.get("warnings", [])) if isinstance(corporate_actions.get("warnings"), list) else [],
                "limitations": list(corporate_actions.get("limitations", [])) if isinstance(corporate_actions.get("limitations"), list) else [],
            },
            "shareholding": {
                "status": shareholding.get("status"),
                "items": [
                    {
                        "metric": item.get("holder_category"),
                        "value": item.get("holding_percent"),
                        "unit": "%",
                        "period": item.get("period") or latest_year,
                        "basis": "ownership",
                        "confidence": item.get("confidence"),
                        "source_artifacts": ["shareholding_pattern.json"],
                        "warnings": list(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else [],
                        "limitations": [],
                    }
                    for item in shareholding.get("items", []) if isinstance(item, dict)
                ][:10],
                "warnings": list(shareholding.get("warnings", [])) if isinstance(shareholding.get("warnings"), list) else [],
                "limitations": list(shareholding.get("limitations", [])) if isinstance(shareholding.get("limitations"), list) else [],
            },
            "financial_quality_summary": {
                "status": quality.get("status"),
                "basis_used": quality.get("basis_used") or normalized.get("preferred_basis") or "unknown",
                "growth_quality": self._quality_metric_bundle(year=latest_year, section_name="growth_quality", section=quality_sections.get("growth_quality") or quality.get("growth_quality") or {}),
                "margin_quality": self._quality_metric_bundle(year=latest_year, section_name="margin_quality", section=quality_sections.get("margin_quality") or quality.get("margin_quality") or {}),
                "return_on_capital_quality": self._quality_metric_bundle(year=latest_year, section_name="return_on_capital_quality", section=quality_sections.get("return_on_capital_quality") or quality.get("return_on_capital_quality") or {}),
                "cash_conversion_quality": self._quality_metric_bundle(year=latest_year, section_name="cash_conversion_quality", section=quality_sections.get("cash_conversion_quality") or quality.get("cash_conversion_quality") or {}),
                "balance_sheet_strength": self._quality_metric_bundle(year=latest_year, section_name="balance_sheet_strength", section=quality_sections.get("balance_sheet_strength") or quality.get("balance_sheet_strength") or {}),
                "working_capital_pressure": self._quality_metric_bundle(year=latest_year, section_name="working_capital_pressure", section=quality_sections.get("working_capital_pressure") or {}),
                "capital_allocation_signals": self._quality_metric_bundle(year=latest_year, section_name="capital_allocation_signals", section=quality_sections.get("capital_allocation_signals") or {}),
                "per_share_quality": self._quality_metric_bundle(year=latest_year, section_name="per_share_quality", section=quality_sections.get("per_share_quality") or quality.get("dilution_and_corporate_action_quality") or {}),
                "ownership_signal_quality": self._quality_metric_bundle(year=latest_year, section_name="ownership_signal_quality", section=quality_sections.get("ownership_signal_quality") or quality.get("ownership_quality") or {}),
                "dividend_quality": self._quality_metric_bundle(year=latest_year, section_name="dividend_quality", section=quality_sections.get("dividend_quality") or {}),
                "red_flags": list((quality_sections.get("red_flags") or quality.get("red_flags") or [])),
                "missing_data": list((quality_sections.get("missing_data") or quality.get("missing_data") or [])),
                "investor_questions": list((quality_sections.get("investor_questions") or [])),
            },
            "multi_year_financial_memory": memory_summary,
            "warnings": warnings,
            "limitations": limitations,
            "source_manifest": manifest,
        }

    def _precise_share_warning_bundle(self, normalized: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        share_data = (normalized.get("share_data") or {}) if isinstance(normalized, dict) else {}
        shares_outstanding = share_data.get("shares_outstanding") or {}
        weighted_avg_shares = share_data.get("weighted_avg_shares") or {}
        diluted_shares = share_data.get("diluted_shares") or {}

        has_shares_outstanding = _entry_has_value(shares_outstanding)
        has_weighted_avg_shares = _entry_has_value(weighted_avg_shares)
        has_diluted_shares = _entry_has_value(diluted_shares)

        warnings: List[str] = []
        limitations: List[str] = []

        if not has_shares_outstanding and not has_weighted_avg_shares and not has_diluted_shares:
            _append_unique(warnings, "share count missing")
            return warnings, limitations

        if not has_weighted_avg_shares:
            _append_unique(warnings, "weighted average shares missing")
            _append_unique(limitations, "Per-share analysis is limited because weighted average share count is missing.")
        if not has_diluted_shares:
            _append_unique(warnings, "diluted shares missing")
            _append_unique(limitations, "Per-share analysis is limited because diluted share count is missing.")

        return warnings, limitations

    def _apply_precise_share_warning_contract(
        self,
        *,
        warnings: List[str],
        limitations: List[str],
        normalized: Dict[str, Any],
    ) -> Tuple[List[str], List[str]]:
        lowered_filtered_warnings: List[str] = []
        for item in warnings:
            lowered = str(item).lower()
            if "share count missing" in lowered or "shares outstanding missing" in lowered:
                continue
            lowered_filtered_warnings.append(item)

        lowered_filtered_limitations: List[str] = []
        for item in limitations:
            lowered = str(item).lower()
            if "share count missing" in lowered:
                continue
            lowered_filtered_limitations.append(item)

        precise_warnings, precise_limitations = self._precise_share_warning_bundle(normalized)
        for item in precise_warnings:
            _append_unique(lowered_filtered_warnings, item)
        for item in precise_limitations:
            _append_unique(lowered_filtered_limitations, item)
        return lowered_filtered_warnings, lowered_filtered_limitations

    def _build_pcim_financial_sections(
        self,
        available_years: List[str],
        yearly_payloads: Dict[str, Dict[str, Any]],
        artifacts: Dict[str, Any],
    ) -> Dict[str, Any]:
        financial_manifest = self._financial_artifact_manifest(available_years, yearly_payloads, artifacts)
        trends = artifacts.get("financial_trends") or {}
        quality = artifacts.get("financial_quality_summary") or {}
        attribution = artifacts.get("financial_driver_attribution") or {}
        memory_summary = artifacts.get("financial_memory_summary") or {}
        truth_pack = artifacts.get("financial_truth_pack") or {}
        owner_earnings_bridge = artifacts.get("owner_earnings_bridge") or {}
        capital_allocation_roi_ledger = artifacts.get("capital_allocation_roi_ledger") or {}
        working_capital_quality_drilldown = artifacts.get("working_capital_quality_drilldown") or {}
        order_revenue_cash_conversion_tracker = artifacts.get("order_revenue_cash_conversion_tracker") or {}
        per_share_compounding_analysis = artifacts.get("per_share_compounding_analysis") or {}
        investor_financial_modules_manifest = artifacts.get("investor_financial_modules_manifest") or {}
        latest_year = available_years[-1] if available_years else ""
        latest_normalized = ((yearly_payloads.get(latest_year) or {}).get("normalized_fundamentals") or {}) if latest_year else {}

        adjusted_manifest_warnings, adjusted_manifest_limitations = self._apply_precise_share_warning_contract(
            warnings=list(financial_manifest.get("financial_warnings", [])),
            limitations=list(financial_manifest.get("limitations", [])),
            normalized=latest_normalized,
        )
        financial_manifest["financial_warnings"] = adjusted_manifest_warnings
        financial_manifest["limitations"] = adjusted_manifest_limitations

        fundamentals_by_year = []
        corporate_action_inputs = []
        ownership_inputs_by_year = []
        financial_growth_by_year = []
        profitability_by_year = []
        working_capital_by_year = []
        financial_quality_by_year = []
        for year in available_years:
            payload = yearly_payloads.get(year, {})
            normalized = payload.get("normalized_fundamentals") or {}
            validation_payload = payload.get("financial_validation_report") or {}
            reconciliation_payload = payload.get("financial_reconciliation_report") or {}
            if normalized:
                fundamentals_by_year.append(
                    {
                        "year": year,
                        "basis": normalized.get("preferred_basis", "unknown"),
                        "key_metrics": list(
                            filter(
                                None,
                                [
                                    self._compact_metric_entry(year, "revenue", ((normalized.get("profit_and_loss") or {}).get("revenue") or {})),
                                    self._compact_metric_entry(year, "pat", ((normalized.get("profit_and_loss") or {}).get("pat") or {})),
                                    self._compact_metric_entry(year, "net_worth", ((normalized.get("balance_sheet") or {}).get("net_worth") or {})),
                                    self._compact_metric_entry(year, "total_debt", ((normalized.get("balance_sheet") or {}).get("total_debt") or {})),
                                    self._compact_metric_entry(year, "cash_and_equivalents", ((normalized.get("balance_sheet") or {}).get("cash_and_equivalents") or {})),
                                    self._compact_metric_entry(year, "cfo", ((normalized.get("cash_flow") or {}).get("cfo") or {})),
                                    self._compact_metric_entry(year, "capex", ((normalized.get("cash_flow") or {}).get("capex") or {})),
                                    self._compact_metric_entry(year, "shares_outstanding", ((normalized.get("share_data") or {}).get("shares_outstanding") or {}), include_original=True),
                                ],
                            )
                        ),
                        "warnings": list(normalized.get("warnings", [])) if isinstance(normalized.get("warnings"), list) else [],
                    }
                )
            ratio_payload = payload.get("financial_ratios") or {}
            if ratio_payload:
                profitability_metrics = list(
                    filter(
                        None,
                        [
                            self._metric_value_from_ratio(year, "gross_margin", ((ratio_payload.get("ratios") or {}).get("gross_margin") or {})),
                            self._metric_value_from_ratio(year, "ebitda_margin", ((ratio_payload.get("ratios") or {}).get("ebitda_margin") or {})),
                            self._metric_value_from_ratio(year, "ebit_margin", ((ratio_payload.get("ratios") or {}).get("ebit_margin") or {})),
                            self._metric_value_from_ratio(year, "opm", ((ratio_payload.get("ratios") or {}).get("opm") or {})),
                            self._metric_value_from_ratio(year, "npm", ((ratio_payload.get("ratios") or {}).get("npm") or {})),
                        ],
                    )
                )
                if profitability_metrics:
                    profitability_by_year.append(
                        {
                            "year": year,
                            "metrics": profitability_metrics,
                            "warnings": list(ratio_payload.get("warnings", [])) if isinstance(ratio_payload.get("warnings"), list) else [],
                            "limitations": list(ratio_payload.get("limitations", [])) if isinstance(ratio_payload.get("limitations"), list) else [],
                        }
                    )
                working_capital_metrics = list(
                    filter(
                        None,
                        [
                            self._metric_value_from_ratio(year, "receivable_days", ((ratio_payload.get("ratios") or {}).get("receivable_days") or {})),
                            self._metric_value_from_ratio(year, "inventory_days", ((ratio_payload.get("ratios") or {}).get("inventory_days") or {})),
                            self._metric_value_from_ratio(year, "payable_days", ((ratio_payload.get("ratios") or {}).get("payable_days") or {})),
                            self._metric_value_from_ratio(year, "cash_conversion_cycle", ((ratio_payload.get("ratios") or {}).get("cash_conversion_cycle") or {})),
                        ],
                    )
                )
                if working_capital_metrics:
                    working_capital_by_year.append(
                        {
                            "year": year,
                            "metrics": working_capital_metrics,
                            "warnings": list(ratio_payload.get("warnings", [])) if isinstance(ratio_payload.get("warnings"), list) else [],
                            "limitations": list(ratio_payload.get("limitations", [])) if isinstance(ratio_payload.get("limitations"), list) else [],
                        }
                    )
            growth_payload = payload.get("financial_growth") or {}
            if growth_payload:
                compact_growth = []
                for metric_name in ("revenue", "pat", "eps_basic", "book_value_per_share"):
                    for item in ((growth_payload.get("growth_metrics") or {}).get(metric_name) or []):
                        compact = self._compact_growth_item(item)
                        if compact:
                            compact_growth.append(compact)
                if compact_growth:
                    financial_growth_by_year.append(
                        {
                            "year": year,
                            "growth_metrics": compact_growth,
                            "warnings": list(growth_payload.get("warnings", [])) if isinstance(growth_payload.get("warnings"), list) else [],
                            "limitations": list(growth_payload.get("limitations", [])) if isinstance(growth_payload.get("limitations"), list) else [],
                        }
                    )
                for metric_name in ("receivables", "inventory", "payables"):
                    for item in ((growth_payload.get("growth_metrics") or {}).get(metric_name) or []):
                        compact = self._metric_value_from_growth(year, metric_name, item)
                        if compact:
                            existing = next((bucket for bucket in working_capital_by_year if bucket.get("year") == year), None)
                            if existing is None:
                                existing = {"year": year, "metrics": [], "warnings": [], "limitations": []}
                                working_capital_by_year.append(existing)
                            existing["metrics"].append(compact)
            corp_payload = payload.get("corporate_actions") or {}
            if corp_payload:
                corporate_action_inputs.append(
                    {
                        "year": year,
                        "status": corp_payload.get("status"),
                        "actions": [
                            {
                                "action_type": item.get("action_type"),
                                "source_year": item.get("year") or year,
                                "source_artifact": "corporate_actions.json",
                                "ratio": item.get("ratio"),
                                "impact_on_share_count": item.get("impact_on_share_count"),
                                "impact_on_eps_comparability": item.get("impact_on_eps_comparability"),
                                "warnings": list(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else [],
                            }
                            for item in corp_payload.get("actions", []) if isinstance(item, dict)
                        ][:10],
                        "per_share_comparability_warnings": list(corp_payload.get("per_share_comparability_warnings", []))
                        if isinstance(corp_payload.get("per_share_comparability_warnings"), list)
                        else [],
                    }
                )
            share_payload = payload.get("shareholding_pattern") or {}
            if share_payload:
                ownership_inputs_by_year.append(
                    {
                        "year": year,
                        "status": share_payload.get("status"),
                        "items": [
                            {
                                "holder_category": item.get("holder_category"),
                                "holding_percent": item.get("holding_percent"),
                                "source_year": year,
                                "source_artifact": "shareholding_pattern.json",
                                "confidence": item.get("confidence"),
                                "warnings": list(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else [],
                            }
                            for item in share_payload.get("items", []) if isinstance(item, dict)
                        ][:10],
                        "warnings": list(share_payload.get("warnings", [])) if isinstance(share_payload.get("warnings"), list) else [],
                    }
                )
            quality_payload = payload.get("financial_quality_summary") or {}
            if quality_payload:
                quality_sections = quality_payload.get("sections") or {}
                financial_quality_by_year.append(
                    {
                        "year": year,
                        "status": quality_payload.get("status"),
                        "basis_used": quality_payload.get("basis_used") or normalized.get("preferred_basis") or "unknown",
                        "sections": {
                            section_name: self._quality_metric_bundle(
                                year=year,
                                section_name=section_name,
                                section=section_value if isinstance(section_value, dict) else {},
                            )
                            for section_name, section_value in quality_sections.items()
                            if section_name not in {"red_flags", "missing_data", "investor_questions"} and isinstance(section_value, dict)
                        },
                        "red_flags": list(quality_sections.get("red_flags", [])) if isinstance(quality_sections.get("red_flags"), list) else [],
                        "missing_data": list(quality_sections.get("missing_data", [])) if isinstance(quality_sections.get("missing_data"), list) else [],
                        "investor_questions": list(quality_sections.get("investor_questions", [])) if isinstance(quality_sections.get("investor_questions"), list) else [],
                        "warnings": _dedupe_strings(
                            (list(quality_payload.get("warnings", [])) if isinstance(quality_payload.get("warnings"), list) else [])
                            + (list(validation_payload.get("warnings", [])) if isinstance(validation_payload.get("warnings"), list) else [])
                            + (list(reconciliation_payload.get("warnings", [])) if isinstance(reconciliation_payload.get("warnings"), list) else [])
                        ),
                        "limitations": _dedupe_strings(
                            list(quality_payload.get("limitations", [])) if isinstance(quality_payload.get("limitations"), list) else []
                        ),
                    }
                )

        if not financial_quality_by_year and quality:
            fallback_year = available_years[-1] if available_years else "unknown"
            fallback_sections = {
                "growth_quality": quality.get("growth_quality") or {},
                "cash_conversion_quality": quality.get("cash_conversion_quality") or {},
                "return_on_capital_quality": quality.get("return_on_capital_quality") or {},
                "balance_sheet_strength": quality.get("balance_sheet_strength") or {},
                "ownership_quality": quality.get("ownership_quality") or {},
                "dilution_and_corporate_action_quality": quality.get("dilution_and_corporate_action_quality") or {},
            }
            financial_quality_by_year.append(
                {
                    "year": fallback_year,
                    "status": quality.get("status") or "warning",
                    "basis_used": trends.get("basis") or "unknown",
                    "sections": {
                        section_name: self._quality_metric_bundle(
                            year=fallback_year,
                            section_name=section_name,
                            section=section_value if isinstance(section_value, dict) else {},
                            source_artifact="financial_quality_summary.json",
                        )
                        for section_name, section_value in fallback_sections.items()
                        if isinstance(section_value, dict) and section_value
                    },
                    "red_flags": list(quality.get("red_flags", [])) if isinstance(quality.get("red_flags"), list) else [],
                    "missing_data": list(quality.get("missing_data", [])) if isinstance(quality.get("missing_data"), list) else [],
                    "investor_questions": list(quality.get("investor_questions", [])) if isinstance(quality.get("investor_questions"), list) else [],
                    "warnings": _dedupe_strings(list(quality.get("warnings", [])) if isinstance(quality.get("warnings"), list) else []),
                    "limitations": _dedupe_strings(list(quality.get("limitations", [])) if isinstance(quality.get("limitations"), list) else []),
                }
            )

        financial_trend_inputs = {
            "years_covered": list(trends.get("years_covered", [])) if isinstance(trends.get("years_covered"), list) else [],
            "basis": trends.get("basis"),
            "metric_trends": list(
                filter(
                    None,
                    [
                        self._compact_trend_series(trends, "revenue", "metric_trends"),
                        self._compact_trend_series(trends, "pat", "metric_trends"),
                        self._compact_trend_series(trends, "net_worth", "metric_trends"),
                        self._compact_trend_series(trends, "total_assets", "metric_trends"),
                    ],
                )
            ),
            "warnings": list(trends.get("warnings", [])) if isinstance(trends.get("warnings"), list) else [],
            "limitations": list(trends.get("limitations", [])) if isinstance(trends.get("limitations"), list) else [],
            "source_artifact": "financial_trends.json",
        }
        financial_growth_inputs = {
            "by_year": financial_growth_by_year,
            "warnings": list(financial_manifest.get("financial_warnings", [])),
            "limitations": list(financial_manifest.get("limitations", [])),
            "source_artifact": "financial_growth.json",
        }
        cash_conversion_inputs = {
            "status": (quality.get("cash_conversion_quality") or {}).get("status"),
            "summary": (quality.get("cash_conversion_quality") or {}).get("summary"),
            "signals": list((quality.get("cash_conversion_quality") or {}).get("signals", [])),
            "warnings": list((quality.get("cash_conversion_quality") or {}).get("warnings", [])),
            "metrics": list(
                filter(
                    None,
                    [
                        self._compact_trend_series(trends, "cfo", "cash_conversion_trends"),
                        self._compact_trend_series(trends, "fcf", "cash_conversion_trends"),
                        self._compact_trend_series(trends, "cfo_to_pat", "cash_conversion_trends"),
                        self._compact_trend_series(trends, "fcf_to_pat", "cash_conversion_trends"),
                        self._compact_trend_series(trends, "receivable_days", "cash_conversion_trends"),
                        self._compact_trend_series(trends, "cash_conversion_cycle", "cash_conversion_trends"),
                    ],
                )
            ),
            "source_artifact": "financial_quality_summary.json",
        }
        return_on_capital_inputs = {
            "status": (quality.get("return_on_capital_quality") or {}).get("status"),
            "summary": (quality.get("return_on_capital_quality") or {}).get("summary"),
            "signals": list((quality.get("return_on_capital_quality") or {}).get("signals", [])),
            "warnings": list((quality.get("return_on_capital_quality") or {}).get("warnings", [])),
            "metrics": list(
                filter(
                    None,
                    [
                        self._compact_trend_series(trends, "roe", "return_trends"),
                        self._compact_trend_series(trends, "roce", "return_trends"),
                        self._compact_trend_series(trends, "roa", "return_trends"),
                    ],
                )
            ),
            "source_artifact": "financial_quality_summary.json",
        }
        balance_sheet_strength_inputs = {
            "status": (quality.get("balance_sheet_strength") or {}).get("status"),
            "summary": (quality.get("balance_sheet_strength") or {}).get("summary"),
            "signals": list((quality.get("balance_sheet_strength") or {}).get("signals", [])),
            "warnings": list((quality.get("balance_sheet_strength") or {}).get("warnings", [])),
            "metrics": list(
                filter(
                    None,
                    [
                        self._compact_trend_series(trends, "total_debt", "balance_sheet_trends"),
                        self._compact_trend_series(trends, "debt_to_equity", "balance_sheet_trends"),
                        self._compact_trend_series(trends, "cash_and_equivalents", "balance_sheet_trends"),
                        self._compact_trend_series(trends, "reserves", "balance_sheet_trends"),
                    ],
                )
            ),
            "source_artifact": "financial_quality_summary.json",
        }
        profitability_inputs = {
            "by_year": profitability_by_year,
            "warnings": list(financial_manifest.get("financial_warnings", [])),
            "source_artifact": "financial_ratios.json",
        }
        working_capital_inputs = {
            "by_year": working_capital_by_year,
            "warnings": list(financial_manifest.get("financial_warnings", [])),
            "source_artifact": "financial_ratios.json",
        }
        per_share_inputs = {
            "metrics": list(
                filter(
                    None,
                    [
                        self._compact_trend_series(trends, "eps_basic", "per_share_trends"),
                        self._compact_trend_series(trends, "eps_diluted", "per_share_trends"),
                        self._compact_trend_series(trends, "book_value_per_share", "per_share_trends"),
                        self._compact_trend_series(trends, "dividend_per_share", "per_share_trends"),
                        self._compact_trend_series(trends, "share_count", "per_share_trends"),
                    ],
                )
            ),
            "warnings": list((quality.get("dilution_and_corporate_action_quality") or {}).get("warnings", [])),
            "source_artifact": "financial_trends.json",
        }
        ownership_inputs = {
            "by_year": ownership_inputs_by_year,
            "summary_status": (quality.get("ownership_quality") or {}).get("status"),
            "summary": (quality.get("ownership_quality") or {}).get("summary"),
            "warnings": list((quality.get("ownership_quality") or {}).get("warnings", [])),
            "source_artifact": "shareholding_pattern.json",
        }
        financial_driver_inputs = self._compact_financial_driver_inputs(attribution)
        financial_quality_inputs = {
            "by_year": financial_quality_by_year,
            "warnings": list(financial_manifest.get("financial_warnings", [])),
            "source_artifact": "financial_quality_summary.json",
        }
        multi_year_financial_inputs = {
            "years_covered": list(memory_summary.get("years_covered", [])),
            "basis_used": memory_summary.get("basis_used") or "unknown",
            "scale_pattern": list((memory_summary.get("summary") or {}).get("scale_pattern", [])),
            "profitability_pattern": list((memory_summary.get("summary") or {}).get("profitability_pattern", [])),
            "return_pattern": list((memory_summary.get("summary") or {}).get("return_pattern", [])),
            "cash_conversion_pattern": list((memory_summary.get("summary") or {}).get("cash_conversion_pattern", [])),
            "balance_sheet_pattern": list((memory_summary.get("summary") or {}).get("balance_sheet_pattern", [])),
            "working_capital_pattern": list((memory_summary.get("summary") or {}).get("working_capital_pattern", [])),
            "capital_allocation_pattern": list((memory_summary.get("summary") or {}).get("capital_allocation_pattern", [])),
            "ownership_pattern": list((memory_summary.get("summary") or {}).get("ownership_pattern", [])),
            "key_strengths": list(memory_summary.get("key_strengths", [])),
            "key_concerns": list(memory_summary.get("key_concerns", [])),
            "missing_data": list(memory_summary.get("missing_data", [])),
            "investor_questions": list(memory_summary.get("investor_questions", [])),
            "warnings": list(memory_summary.get("warnings", [])),
            "limitations": list(memory_summary.get("limitations", [])),
            "source_artifact": "financial_memory_summary.json",
        }
        financial_truth_inputs = {
            "years_covered": list(truth_pack.get("years_covered", [])),
            "usable_current_metrics": list(truth_pack.get("usable_current_metrics", [])),
            "usable_derived_metrics": list(truth_pack.get("usable_derived_metrics", [])),
            "partial_metrics": list(truth_pack.get("partial_metrics", [])),
            "derived_not_explicitly_reported": list(truth_pack.get("derived_not_explicitly_reported", [])),
            "trend_durability_limits": list(truth_pack.get("trend_durability_limits", [])),
            "precision_limits": list(truth_pack.get("precision_limits", [])),
            "investor_financial_questions": list(truth_pack.get("investor_relevant_questions", [])),
            "source_provenance": list(truth_pack.get("source_provenance", [])),
            "source_artifact": "financial_truth_pack.json",
        }
        financial_snapshot_inputs = {
            "years_covered": list(truth_pack.get("years_covered", [])),
            "usable_current_metrics": list(truth_pack.get("usable_current_metrics", [])),
            "trend_durability_limits": list(truth_pack.get("trend_durability_limits", [])),
            "precision_limits": list(truth_pack.get("precision_limits", [])),
            "source_artifact": "financial_truth_pack.json",
        }
        owner_earnings_readiness_inputs = {
            "bridges": list(owner_earnings_bridge.get("bridges", []))[:5],
            "usable_derived_metrics": [
                item
                for item in list(truth_pack.get("usable_derived_metrics", []))
                if str(item.get("metric_id") or item.get("canonical_metric") or "").strip().lower()
                in {"fcf", "owner_earnings_estimate", "fcf_after_ppe_cwip_capex"}
            ],
            "precision_limits": list(truth_pack.get("precision_limits", [])),
            "warnings": list(owner_earnings_bridge.get("warnings", [])) if isinstance(owner_earnings_bridge.get("warnings"), list) else [],
            "source_artifact": "owner_earnings_bridge.json",
        }
        working_capital_quality_inputs = {
            "drilldown": list(working_capital_quality_drilldown.get("drilldown", []))[:5],
            "order_to_cash_tracker": list(order_revenue_cash_conversion_tracker.get("tracker", []))[:5],
            "trend_durability_limits": list(truth_pack.get("trend_durability_limits", [])),
            "precision_limits": list(truth_pack.get("precision_limits", [])),
            "warnings": list(working_capital_quality_drilldown.get("warnings", [])) if isinstance(working_capital_quality_drilldown.get("warnings"), list) else [],
            "source_artifact": "working_capital_quality_drilldown.json",
        }
        capital_allocation_financial_inputs = {
            "entries": list(capital_allocation_roi_ledger.get("entries", []))[:8],
            "precision_limits": list(truth_pack.get("precision_limits", [])),
            "warnings": list(capital_allocation_roi_ledger.get("warnings", [])) if isinstance(capital_allocation_roi_ledger.get("warnings"), list) else [],
            "source_artifact": "capital_allocation_roi_ledger.json",
        }
        per_share_compounding_inputs = {
            "analysis": list(per_share_compounding_analysis.get("analysis", []))[:5],
            "trend_durability_limits": list(truth_pack.get("trend_durability_limits", [])),
            "precision_limits": list(truth_pack.get("precision_limits", [])),
            "warnings": list(per_share_compounding_analysis.get("warnings", [])) if isinstance(per_share_compounding_analysis.get("warnings"), list) else [],
            "source_artifact": "per_share_compounding_analysis.json",
        }
        unreliable_financial_inputs = {
            "metrics": list(truth_pack.get("unreliable_metrics", [])),
            "source_artifact": "financial_truth_pack.json",
        }
        invalid_or_quarantined_financial_inputs = {
            "metrics": list(truth_pack.get("invalid_or_quarantined_metrics", [])),
            "source_artifact": "financial_truth_pack.json",
        }
        precise_missing_financial_inputs = {
            "metrics": list(truth_pack.get("precise_missing_metrics", [])),
            "investor_questions": list(truth_pack.get("investor_relevant_questions", [])),
            "source_artifact": "financial_truth_pack.json",
        }
        financial_panel_ready = bool(financial_quality_by_year) and financial_manifest.get("financial_status") in {"pass", "warning"}
        if truth_pack.get("financial_panel_status") == "invalid":
            financial_panel_ready = False
        financial_warning_policy = {
            "allowed_financial_warnings": list(truth_pack.get("financial_warnings_allowed_downstream", [])),
            "financial_warnings_blocked_downstream": [
                item.get("original_warning") if isinstance(item, dict) else item
                for item in truth_pack.get("financial_warnings_blocked_downstream", [])
            ],
            "financial_warnings_rewritten": list(truth_pack.get("financial_warnings_rewritten", [])),
            "source_artifact": "financial_truth_pack.json",
        }
        financial_panel_status = {
            "status": truth_pack.get("financial_panel_status") or ("pass" if financial_panel_ready else "warning"),
            "reason": truth_pack.get("financial_panel_status_reason") or "",
            "source_artifact": "financial_truth_pack.json",
        }

        sections = {
            "financial_fundamentals_inputs": {
                "by_year": fundamentals_by_year,
                "warnings": list(financial_manifest.get("financial_warnings", [])),
            },
            "financial_truth_inputs": financial_truth_inputs,
            "financial_snapshot_inputs": financial_snapshot_inputs,
            "financial_trend_inputs": financial_trend_inputs,
            "financial_growth_inputs": financial_growth_inputs,
            "cash_conversion_inputs": cash_conversion_inputs,
            "return_on_capital_inputs": return_on_capital_inputs,
            "balance_sheet_strength_inputs": balance_sheet_strength_inputs,
            "growth_quality_inputs_financial": {
                "quality_status": (quality.get("growth_quality") or {}).get("status"),
                "summary": (quality.get("growth_quality") or {}).get("summary"),
                "signals": list((quality.get("growth_quality") or {}).get("signals", [])),
                "by_year": financial_growth_by_year,
                "source_artifact": "financial_quality_summary.json",
            },
            "profitability_inputs": profitability_inputs,
            "per_share_inputs": per_share_inputs,
            "working_capital_inputs": working_capital_inputs,
            "owner_earnings_readiness_inputs": owner_earnings_readiness_inputs,
            "working_capital_quality_inputs": working_capital_quality_inputs,
            "capital_allocation_financial_inputs": capital_allocation_financial_inputs,
            "per_share_compounding_inputs": per_share_compounding_inputs,
            "unreliable_financial_inputs": unreliable_financial_inputs,
            "invalid_or_quarantined_financial_inputs": invalid_or_quarantined_financial_inputs,
            "precise_missing_financial_inputs": precise_missing_financial_inputs,
            "financial_warning_policy": financial_warning_policy,
            "investor_financial_questions": list(truth_pack.get("investor_relevant_questions", [])),
            "financial_panel_status": financial_panel_status,
            "financial_panel_usable_domains": list(truth_pack.get("financial_panel_usable_domains", investor_financial_modules_manifest.get("usable_domains", []))),
            "financial_panel_limited_domains": list(truth_pack.get("financial_panel_limited_domains", investor_financial_modules_manifest.get("limited_domains", []))),
            "financial_panel_blocked_domains": list(truth_pack.get("financial_panel_blocked_domains", investor_financial_modules_manifest.get("blocked_domains", []))),
            "corporate_action_inputs": {
                "by_year": corporate_action_inputs,
                "warnings": list(financial_manifest.get("financial_warnings", [])),
                "source_artifact": "corporate_actions.json",
            },
            "ownership_inputs": ownership_inputs,
            "financial_quality_inputs": financial_quality_inputs,
            "financial_driver_inputs": financial_driver_inputs,
            "multi_year_financial_inputs": multi_year_financial_inputs,
            "financial_source_manifest": {
                "financial_artifacts_used": list(financial_manifest.get("financial_artifacts_used", [])),
                "latest_generated_at": financial_manifest.get("latest_generated_at", ""),
                "status": financial_manifest.get("financial_status", "fail"),
                "warnings": list(financial_manifest.get("financial_warnings", [])),
                "limitations": list(financial_manifest.get("limitations", [])),
            },
            "financial_panel_ready": financial_panel_ready,
        }
        return _strip_source_chunk(sections), financial_manifest

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
        latest_year = self._latest_year(available_years)
        latest_payload = yearly_payloads.get(latest_year or "", {})

        cim_v1 = {
            "contract_version": CONTRACT_VERSION,
            "company": self.company,
            "available_years": available_years,
            "business_identity_manifest": build_business_identity_manifest(
                latest_payload.get("business_blueprint"),
                latest_payload.get("business_classification"),
                require_classification=bool(latest_year),
            ),
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
            "management_summary_by_year": [
                _management_summary_bucket(
                    snapshot["year"],
                    yearly_payloads.get(snapshot["year"], {}).get("management_summary") or {},
                )
                for snapshot in yearly_snapshots
            ],
            "external_context": [
                {
                    "year": snapshot["year"],
                    "items": _copy_items(snapshot.get("external_context_items", [])),
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
            "financials": self._build_cim_financials(
                available_years,
                yearly_payloads,
                artifacts,
            ),
            "financial_intelligence": self._build_cim_financial_intelligence(
                available_years,
                yearly_payloads,
                artifacts,
            ),
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
                    "financials/financial_year_index.json",
                    "financials/financial_trends.json",
                    "financials/financial_quality_evolution.json",
                    "financials/capital_allocation_financial_timeline.json",
                    "financials/ownership_evolution.json",
                    "financials/financial_memory_summary.json",
                    "financials/financial_quality_summary.json",
                    "financials/financial_driver_attribution.json",
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
        cim_v1["management_identity_limitations"] = [
            {
                "year": bucket.get("year"),
                "items": list(bucket.get("management_identity_limitations", [])),
            }
            for bucket in cim_v1.get("management_summary_by_year", [])
            if bucket.get("management_identity_limitations")
        ]

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
            "external_context",
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
        latest_external_context = self._find_year_bucket(cim_v1.get("external_context", []), latest_year)

        business_understanding = {
            "latest_business_view": {
                "year": latest_year,
                "business_dnas": latest_dna.get("items", []),
                "business_model": latest_business_model,
                "management_focus": latest_focus.get("items", []),
                "external_context": latest_external_context.get("items", []),
            },
            "business_dna_by_year": cim_v1.get("business_dna_by_year", []),
            "business_model_by_year": cim_v1.get("business_model", []),
        }

        capital_allocation = cim_v1.get("capital_allocation", [])
        risks = cim_v1.get("risks", [])
        management_focus = cim_v1.get("management_focus", [])
        management_summary_by_year = cim_v1.get("management_summary_by_year", [])
        external_context = cim_v1.get("external_context", [])
        promises = cim_v1.get("promises", [])
        initiatives = cim_v1.get("initiatives", [])
        projects = cim_v1.get("projects", [])
        true_capital_deployment = _filter_capital_buckets(
            capital_allocation,
            groups=["true_capital_deployment"],
        )
        shareholder_returns = _filter_capital_buckets(
            capital_allocation,
            groups=["shareholder_returns"],
        )
        financing_actions = _filter_capital_buckets(
            capital_allocation,
            groups=["financing_actions"],
        )
        treasury_actions = _filter_capital_buckets(
            capital_allocation,
            groups=["treasury_actions"],
        )
        related_party_capital_flows = _filter_capital_buckets(
            capital_allocation,
            groups=["related_party_capital_flows"],
        )
        corporate_actions = _filter_capital_buckets(
            capital_allocation,
            groups=["corporate_actions_non_cash_or_admin"],
        )
        ownership_transfer_items = _filter_capital_buckets(
            capital_allocation,
            groups=["ownership_transfer_non_company_cashflow"],
        )
        accounting_only_items = _filter_capital_buckets(
            capital_allocation,
            groups=["accounting_or_disclosure_only"],
        )
        uncertain_capital_items = _filter_capital_buckets(
            capital_allocation,
            groups=["uncertain"],
        )

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
        financial_sections, financial_manifest = self._build_pcim_financial_sections(
            available_years,
            self._load_year_payloads(available_years),
            self._load_company_memory_artifacts(),
        )
        multi_year_builder = PCIMMultiYearBuilder(self.company_root, expected_years=available_years)
        multi_year_inputs = multi_year_builder.build()
        pcim_source_manifest = multi_year_builder.source_manifest
        pcim_source_manifest.update(financial_manifest)

        pcim_v1 = {
            "contract_version": CONTRACT_VERSION,
            "company": self.company,
            "generated_at": pcim_source_manifest.get("generated_at"),
            "available_years": available_years,
            "business_identity_manifest": cim_v1.get("business_identity_manifest", {}),
            "business_understanding": business_understanding,
            "financial_strength_inputs": {
                "capital_allocation_by_year": capital_allocation,
                "true_capital_deployment_by_year": true_capital_deployment,
                "financing_actions_by_year": financing_actions,
                "shareholder_returns_by_year": shareholder_returns,
                "treasury_actions_by_year": treasury_actions,
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
                "management_grouped_by_year": [
                    {
                        "year": bucket.get("year"),
                        "company_management_actions": _copy_items(bucket.get("company_management_actions", [])),
                        "company_promises": _copy_items(bucket.get("company_promises", [])),
                        "company_capabilities": _copy_items(bucket.get("company_capabilities", [])),
                        "company_results": _copy_items(bucket.get("company_results", [])),
                        "risk_responses": _copy_items(bucket.get("risk_responses", [])),
                    }
                    for bucket in management_summary_by_year
                ],
                "promise_tracker": cim_v1.get("derived_context", {}).get("promise_tracker", []),
                "promises_by_year": promises,
                "management_identity_limitations": list(cim_v1.get("management_identity_limitations", [])),
            },
            "business_context": {
                "external_context_by_year": external_context,
            },
            "growth_quality_inputs": {
                "projects_by_year": projects,
                "initiatives_by_year": initiatives,
                "strategy_timeline": cim_v1.get("derived_context", {}).get("strategy_timeline", []),
                "financial_growth_summary": financial_sections.get("growth_quality_inputs_financial", {}),
            },
            "moat_inputs": {
                "business_dna_by_year": cim_v1.get("business_dna_by_year", []),
                "business_model_by_year": cim_v1.get("business_model", []),
                "entities": cim_v1.get("entities", []),
            },
            "capital_allocation_inputs": {
                "capital_allocation_by_year": capital_allocation,
                "true_capital_deployment_by_year": true_capital_deployment,
                "shareholder_returns_by_year": shareholder_returns,
                "financing_actions_by_year": financing_actions,
                "treasury_actions_by_year": treasury_actions,
                "related_party_flows_by_year": related_party_capital_flows,
                "corporate_actions_by_year": corporate_actions,
                "ownership_transfer_items_by_year": ownership_transfer_items,
                "accounting_and_disclosure_limitations_by_year": accounting_only_items,
                "uncertain_items_by_year": uncertain_capital_items,
                "promises_by_year": promises,
                "dividend_and_distribution_signals_by_year": dividend_signals,
                "equity_and_issuance_signals_by_year": _bucket_items_by_year(
                    financing_actions + corporate_actions,
                    signal_type="equity_issuance_or_compensation",
                    keywords=["rsu", "esop", "share-based", "equity issuance", "share capital", "qip", "preferential allotment"],
                ),
                "related_party_and_advance_signals_by_year": related_party_capital_flows,
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
            "financial_fundamentals_inputs": financial_sections.get("financial_fundamentals_inputs", {}),
            "financial_truth_inputs": financial_sections.get("financial_truth_inputs", {}),
            "financial_snapshot_inputs": financial_sections.get("financial_snapshot_inputs", {}),
            "financial_trend_inputs": financial_sections.get("financial_trend_inputs", {}),
            "financial_growth_inputs": financial_sections.get("financial_growth_inputs", {}),
            "profitability_inputs": financial_sections.get("profitability_inputs", {}),
            "cash_conversion_inputs": financial_sections.get("cash_conversion_inputs", {}),
            "return_on_capital_inputs": financial_sections.get("return_on_capital_inputs", {}),
            "balance_sheet_strength_inputs": financial_sections.get("balance_sheet_strength_inputs", {}),
            "working_capital_inputs": financial_sections.get("working_capital_inputs", {}),
            "per_share_inputs": financial_sections.get("per_share_inputs", {}),
            "owner_earnings_readiness_inputs": financial_sections.get("owner_earnings_readiness_inputs", {}),
            "working_capital_quality_inputs": financial_sections.get("working_capital_quality_inputs", {}),
            "capital_allocation_financial_inputs": financial_sections.get("capital_allocation_financial_inputs", {}),
            "per_share_compounding_inputs": financial_sections.get("per_share_compounding_inputs", {}),
            "unreliable_financial_inputs": financial_sections.get("unreliable_financial_inputs", {}),
            "invalid_or_quarantined_financial_inputs": financial_sections.get("invalid_or_quarantined_financial_inputs", {}),
            "precise_missing_financial_inputs": financial_sections.get("precise_missing_financial_inputs", {}),
            "financial_warning_policy": financial_sections.get("financial_warning_policy", {}),
            "investor_financial_questions": financial_sections.get("investor_financial_questions", []),
            "financial_panel_status": financial_sections.get("financial_panel_status", {}),
            "financial_panel_usable_domains": financial_sections.get("financial_panel_usable_domains", []),
            "financial_panel_limited_domains": financial_sections.get("financial_panel_limited_domains", []),
            "financial_panel_blocked_domains": financial_sections.get("financial_panel_blocked_domains", []),
            "corporate_action_inputs": financial_sections.get("corporate_action_inputs", {}),
            "ownership_inputs": financial_sections.get("ownership_inputs", {}),
            "financial_quality_inputs": financial_sections.get("financial_quality_inputs", {}),
            "financial_driver_inputs": financial_sections.get("financial_driver_inputs", {}),
            "multi_year_financial_inputs": financial_sections.get("multi_year_financial_inputs", {}),
            "financial_panel_ready": financial_sections.get("financial_panel_ready", False),
            "financial_source_manifest": financial_sections.get("financial_source_manifest", {}),
            "multi_year_inputs": multi_year_inputs,
            "pcim_source_manifest": pcim_source_manifest,
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
                ] + [
                    evidence_id
                    for bucket in management_summary_by_year
                    for group_name in (
                        "company_management_actions",
                        "company_promises",
                        "company_capabilities",
                        "company_results",
                        "risk_responses",
                    )
                    for item in bucket.get(group_name, [])
                    for evidence_id in item.get("evidence_ids", [])
                ],
                "business_context": [
                    evidence_id
                    for bucket in external_context
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
                "financial_fundamentals_inputs": [],
                "financial_trend_inputs": [],
                "financial_growth_inputs": [],
                "profitability_inputs": [],
                "cash_conversion_inputs": [],
                "return_on_capital_inputs": [],
                "balance_sheet_strength_inputs": [],
                "working_capital_inputs": [],
                "per_share_inputs": [],
                "corporate_action_inputs": [],
                "ownership_inputs": [],
                "financial_quality_inputs": [],
                "financial_driver_inputs": [
                    evidence_id
                    for item in (financial_sections.get("financial_driver_inputs", {}).get("attributions", []) or [])
                    for evidence_id in item.get("evidence_ids", [])
                ],
                "multi_year_financial_inputs": [],
                "multi_year_inputs": list((multi_year_inputs.get("evidence_map") or {}).keys()),
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
        pcim_v1 = _strip_source_chunk(pcim_v1)
        self._validate_pcim_v1(pcim_v1)
        return pcim_v1

    def _validate_pcim_v1(self, pcim_v1: Dict[str, Any]) -> None:
        if '"source_chunk"' in json.dumps(pcim_v1, ensure_ascii=False):
            raise ValueError("PCIM output must not contain source_chunk")

        manifest = pcim_v1.get("pcim_source_manifest") or {}
        if not manifest:
            raise ValueError("pcim_source_manifest is required in PCIM output")

        source_files = manifest.get("source_files") or []
        multi_year_inputs = pcim_v1.get("multi_year_inputs") or {}
        loaded_files = [entry for entry in source_files if entry.get("loaded")]
        status = manifest.get("status")
        years_covered = list(multi_year_inputs.get("years_covered", []))
        manifest_years = list(manifest.get("years_covered_in_multi_year_inputs", []))

        if loaded_files and not multi_year_inputs:
            raise ValueError("multi_year_inputs missing despite loaded multi-year source files")
        if years_covered != manifest_years:
            raise ValueError("pcim_source_manifest.years_covered_in_multi_year_inputs does not match multi_year_inputs.years_covered")

        if '"source_chunk"' in json.dumps(multi_year_inputs, ensure_ascii=False):
            raise ValueError("multi_year_inputs must not contain source_chunk")

        available_keys = {
            canonicalize_fiscal_year_label(year)
            for year in manifest.get("years_available", [])
            if canonicalize_fiscal_year_label(year)
        }
        covered_keys = {
            canonicalize_fiscal_year_label(year)
            for year in years_covered
            if canonicalize_fiscal_year_label(year)
        }
        expected_missing = [
            year for year in manifest.get("years_available", [])
            if canonicalize_fiscal_year_label(year) in (available_keys - covered_keys)
        ]
        if list(manifest.get("missing_years", [])) != expected_missing:
            raise ValueError("pcim_source_manifest.missing_years does not match available minus covered years")

        generated_at = pcim_v1.get("generated_at")
        if generated_at:
            generated_dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
            for entry in loaded_files:
                modified_at = entry.get("modified_at")
                if not modified_at:
                    continue
                modified_dt = datetime.fromisoformat(str(modified_at).replace("Z", "+00:00"))
                if generated_dt < modified_dt:
                    raise ValueError("PCIM generated_at predates a loaded multi-year source file")

        if not loaded_files and status != "fail":
            raise ValueError("pcim_source_manifest must be fail when no multi-year source files are loaded")
        for entry in source_files:
            if entry.get("loaded") and entry.get("warnings"):
                raise ValueError(
                    f"pcim_source_manifest source file cannot be both loaded and warning-bearing: {entry.get('name')}"
                )

        financial_sections = {
            "financial_fundamentals_inputs": pcim_v1.get("financial_fundamentals_inputs"),
            "financial_trend_inputs": pcim_v1.get("financial_trend_inputs"),
            "financial_growth_inputs": pcim_v1.get("financial_growth_inputs"),
            "profitability_inputs": pcim_v1.get("profitability_inputs"),
            "cash_conversion_inputs": pcim_v1.get("cash_conversion_inputs"),
            "return_on_capital_inputs": pcim_v1.get("return_on_capital_inputs"),
            "balance_sheet_strength_inputs": pcim_v1.get("balance_sheet_strength_inputs"),
            "growth_quality_inputs": (pcim_v1.get("growth_quality_inputs") or {}).get("financial_growth_summary"),
            "working_capital_inputs": pcim_v1.get("working_capital_inputs"),
            "per_share_inputs": pcim_v1.get("per_share_inputs"),
            "corporate_action_inputs": pcim_v1.get("corporate_action_inputs"),
            "ownership_inputs": pcim_v1.get("ownership_inputs"),
            "financial_quality_inputs": pcim_v1.get("financial_quality_inputs"),
            "financial_driver_inputs": pcim_v1.get("financial_driver_inputs"),
            "multi_year_financial_inputs": pcim_v1.get("multi_year_financial_inputs"),
        }
        has_financial_content = any(section for section in financial_sections.values())
        required_financial_manifest_keys = {
            "financial_artifacts_used",
            "financial_years_covered",
            "financial_status",
            "financial_warnings",
        }
        if has_financial_content and not required_financial_manifest_keys.issubset(manifest):
            missing = sorted(required_financial_manifest_keys - set(manifest))
            raise ValueError(
                f"pcim_source_manifest missing required financial fields: {missing}"
            )
        if has_financial_content and '"source_chunk"' in json.dumps(financial_sections, ensure_ascii=False):
            raise ValueError("financial PCIM sections must not contain source_chunk")
        if has_financial_content and any(
            token in json.dumps(financial_sections, ensure_ascii=False)
            for token in ('"raw_financial_tables.json"', '"line_item_raw"', '"table_type"', '"statement_type"', '"chunk_id"')
        ):
            raise ValueError("financial PCIM sections must not embed raw financial tables")

        financial_years = list(manifest.get("financial_years_covered", []))
        unexpected_financial_years = [
            year
            for year in financial_years
            if canonicalize_fiscal_year_label(year) not in available_keys
        ]
        if unexpected_financial_years:
            raise ValueError(
                "financial years mismatch company years: "
                + ", ".join(unexpected_financial_years)
            )

        def _assert_traceability(node: Any, path: str = "financial") -> None:
            if isinstance(node, dict):
                has_numeric = any(
                    node.get(key) is not None
                    for key in ("value_crore", "value", "growth_percent", "cagr_percent", "holding_percent")
                )
                if has_numeric:
                    if not (node.get("source_artifact") or node.get("source_artifacts")):
                        raise ValueError(f"financial traceability missing source_artifact at {path}")
                    if not (
                        node.get("source_year")
                        or node.get("period")
                        or node.get("years_covered")
                        or node.get("year")
                    ):
                        raise ValueError(f"financial traceability missing source year at {path}")
                for key, value in node.items():
                    _assert_traceability(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    _assert_traceability(value, f"{path}[{index}]")

        if has_financial_content:
            _assert_traceability(financial_sections)

        financial_source_manifest = pcim_v1.get("financial_source_manifest") or {}
        if has_financial_content and not financial_source_manifest:
            raise ValueError("financial_source_manifest is required when financial PCIM sections exist")
        if financial_source_manifest:
            for key in ("financial_artifacts_used", "latest_generated_at", "status", "warnings", "limitations"):
                if key not in financial_source_manifest:
                    raise ValueError(f"financial_source_manifest missing required field: {key}")
            if financial_source_manifest.get("status") not in {"pass", "warning", "fail"}:
                raise ValueError("financial_source_manifest.status must be pass|warning|fail")

        financial_panel_ready = pcim_v1.get("financial_panel_ready")
        if has_financial_content and not isinstance(financial_panel_ready, bool):
            raise ValueError("financial_panel_ready must be a boolean when financial PCIM sections exist")
        has_quality = bool((pcim_v1.get("financial_quality_inputs") or {}).get("by_year"))
        if has_quality and financial_panel_ready is False and manifest.get("financial_status") in {"pass", "warning"}:
            raise ValueError("financial_panel_ready must be true when financial quality inputs are present and usable")

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
