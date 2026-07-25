from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from knowledge.archetypes import ArchetypeRegistry
from knowledge.capital_allocation_taxonomy import normalize_capital_allocation_item
from .company_layer import (
    CompanyMemoryAggregateBuilder,
    _normalize_text,
    _promises_match,
    _promise_theme_key,
    _write_json,
    parse_financial_year,
)


YEARLY_ARTIFACTS = (
    "company_intelligence.json",
    "business_classification.json",
    "management_summary.json",
)

OPTIONAL_COMPANY_MEMORY_ARTIFACTS = (
    "cim_v1.json",
    "pcim_v1.json",
)

MAX_EXCERPT_CHARS = 300
SEVERITY_RANK = {
    "unknown": 0,
    "not specified": 0,
    "low": 1,
    "moderate": 2,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

CAPITAL_TIMELINE_FIELDS = {
    "true_capital_deployment": "true_capital_deployment",
    "shareholder_returns": "shareholder_returns",
    "financing_actions": "financing_actions",
    "treasury_actions": "treasury_actions",
    "corporate_actions_non_cash_or_admin": "corporate_actions_non_cash_or_admin",
    "ownership_transfer_non_company_cashflow": "ownership_transfer_non_company_cashflow",
    "related_party_capital_flows": "related_party_capital_flows",
    "accounting_or_disclosure_only": "accounting_or_disclosure_only",
    "uncertain": "uncertain",
}

CAPITAL_CATEGORY_TIMELINE_FIELDS = {
    "dividend_paid": "dividends",
    "dividend_declared": "dividends",
    "buyback": "buybacks",
    "capex": "capex",
    "capacity_expansion": "capex",
    "technology_investment": "capex",
    "r_and_d_investment": "capex",
    "strategic_investments": "capex",
    "working_capital_investment": "capex",
    "cwip": "cwip",
    "acquisitions": "acquisitions",
    "share_split": "share_splits",
    "equity_issuance": "equity_issuance",
    "qualified_institutional_placement": "equity_issuance",
    "preferential_allotment": "equity_issuance",
    "rights_issue": "equity_issuance",
    "mutual_fund_investment": "treasury_investments",
    "temporary_investment": "treasury_investments",
    "bank_deposit": "treasury_investments",
    "cash_management": "treasury_investments",
    "security_margin_deposit": "treasury_investments",
    "debt_raised": "debt_borrowings",
    "debt_repaid": "debt_repayments",
    "lease_liability_payment": "debt_repayments",
    "related_party_loan_given": "related_party_transactions",
    "related_party_loan_received": "related_party_transactions",
    "related_party_investment": "related_party_transactions",
    "related_party_guarantee": "related_party_transactions",
    "related_party_dividend": "related_party_transactions",
    "related_party_repayment": "related_party_transactions",
    "auditor_observation": "auditor_observations",
    "offer_for_sale": "ownership_transfers",
    "promoter_sale": "ownership_transfers",
    "secondary_sale": "ownership_transfers",
    "stake_sale_by_existing_shareholders": "ownership_transfers",
    "authorised_capital_change": "corporate_actions",
    "bonus_issue": "corporate_actions",
    "face_value_change": "corporate_actions",
    "listing": "corporate_actions",
    "name_change": "corporate_actions",
    "share_split": "share_splits",
    "accounting_policy": "accounting_disclosures",
    "depreciation_policy": "accounting_disclosures",
    "impairment_policy": "accounting_disclosures",
    "fair_value_measurement": "accounting_disclosures",
    "actuarial_assumption": "accounting_disclosures",
    "contingent_liability_disclosure": "accounting_disclosures",
}

BORROWINGS_RE = re.compile(r"Borrowings\s+([0-9][0-9,]*\.?[0-9]*)", re.IGNORECASE)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _slug(value: Any) -> str:
    return _normalize_text(value).replace(" ", "_") or "item"


def _evidence_id(source_year: str, source_artifact: str, source_item_id: Any, fallback: Any) -> str:
    artifact_slug = _slug(source_artifact).replace("_json", "")
    return f"ev_{_slug(source_year)}_{artifact_slug}_{_slug(source_item_id or fallback)}"


def _with_evidence_ids(items: Sequence[Dict[str, Any]], fallback_key: str) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for item in items:
        copy = dict(item)
        evidence_ids = list(copy.get("evidence_ids") or [])
        if not evidence_ids:
            fallback = copy.get("value") or copy.get(fallback_key) or copy.get("source_item_id") or fallback_key
            evidence_ids = [
                _evidence_id(
                    str(copy.get("source_year") or ""),
                    str(copy.get("source_artifact") or ""),
                    copy.get("source_item_id"),
                    fallback,
                )
            ]
        copy["evidence_ids"] = evidence_ids
        enriched.append(copy)
    return enriched


def _generated_at(paths: Iterable[Path]) -> Optional[str]:
    mtimes = [path.stat().st_mtime for path in paths if path.exists()]
    if not mtimes:
        return None
    latest = datetime.fromtimestamp(max(mtimes), tz=timezone.utc).replace(microsecond=0)
    return latest.isoformat().replace("+00:00", "Z")


def _latest_year(years: Sequence[str]) -> Optional[str]:
    if not years:
        return None
    return max(years, key=parse_financial_year)


def _theme_key(value: Any) -> str:
    return _promise_theme_key(str(value or "")) or _slug(value)


def _clean_severity(value: Any) -> str:
    normalized = _normalize_text(value)
    if normalized in SEVERITY_RANK:
        return normalized
    if "critical" in normalized:
        return "critical"
    if "high" in normalized:
        return "high"
    if "medium" in normalized or "moderate" in normalized:
        return "medium"
    if "low" in normalized:
        return "low"
    return "unknown"


def _severity_value(item: Dict[str, Any]) -> str:
    severity = item.get("severity")
    if severity:
        return _clean_severity(severity)
    evidence = item.get("evidence_references") or {}
    if isinstance(evidence, dict) and evidence.get("severity"):
        return _clean_severity(evidence["severity"])
    return "unknown"


def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", [], {}):
        return None
    match = re.search(r"([0-9][0-9,]*\.?[0-9]*)", str(value))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _short_excerpt(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= MAX_EXCERPT_CHARS:
        return text
    return text[: MAX_EXCERPT_CHARS - 3].rstrip() + "..."


def _compact_evidence(evidence: Any) -> List[Dict[str, Any]]:
    refs = evidence if isinstance(evidence, list) else [evidence]
    compact: List[Dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        compact.append(
            {
                "source_page": ref.get("page"),
                "source_artifact": ref.get("source_artifact"),
                "short_excerpt": _short_excerpt(ref.get("source_chunk")),
                "confidence": ref.get("confidence"),
                "severity": _clean_severity(ref.get("severity")),
                "category": ref.get("category"),
                "status": ref.get("status"),
            }
        )
    return compact


def _first_compact_evidence(evidence: Any) -> Dict[str, Any]:
    compact = _compact_evidence(evidence)
    return compact[0] if compact else {}


def _normalize_status(value: Any) -> str:
    normalized = _normalize_text(value)
    if any(token in normalized for token in ("implemented", "completed", "done", "executed")):
        return "completed"
    if any(token in normalized for token in ("executing", "in progress", "ongoing", "active")):
        return "in_progress"
    if any(token in normalized for token in ("planned", "proposed", "approved")):
        return "planned"
    return "unknown"


def _capital_category_order(categories: List[str]) -> List[str]:
    if "share_split" in categories:
        return ["share_split"]
    if "treasury_investment" in categories:
        return ["treasury_investment"]
    if "cwip" in categories:
        return ["cwip", "capex"]
    if "related_party_transaction" in categories and "loan_or_advance" in categories:
        return ["related_party_transaction", "loan_or_advance"]
    if "debt_borrowing" in categories and "treasury_investment" not in categories:
        return ["debt_borrowing"]
    if not categories:
        return ["capex"]
    return categories


def _borrowings_signal(item: Dict[str, Any], canonical_risk: Optional[str] = None) -> Optional[float]:
    text = _normalize_text(
        " ".join(
            str(part or "")
            for part in (
                item.get("value"),
                item.get("category"),
                item.get("severity"),
                item.get("numeric_value"),
            )
        )
    )
    if canonical_risk not in {"liquidity_risk", "interest_rate_risk"}:
        return None
    if canonical_risk == "liquidity_risk" and not any(
        token in text for token in ("borrowing", "borrowings", "debt", "liquidity", "refinancing", "maturity", "loan")
    ):
        return None
    if canonical_risk == "interest_rate_risk" and not any(
        token in text for token in ("interest", "rate", "floating", "variable")
    ):
        return None
    values: List[float] = []
    evidence = item.get("evidence_references") or {}
    refs = evidence if isinstance(evidence, list) else [evidence]
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        source_chunk = str(ref.get("source_chunk") or "")
        for match in BORROWINGS_RE.findall(source_chunk):
            value = _to_float(match)
            if value is not None:
                values.append(value)
    return max(values) if values else None


def _risk_validation_warning(item: Dict[str, Any]) -> Optional[str]:
    canonical = str(item.get("canonical_risk") or "")
    value_text = _normalize_text(item.get("value"))
    category_text = _normalize_text(" ".join(ref.get("category", "") for ref in item.get("evidence_references", []) if isinstance(ref, dict)))
    numeric_value = item.get("numeric_value")

    if canonical == "liquidity_risk" and "foreign currency" in value_text and "liquidity" not in category_text:
        return "liquidity_risk carries foreign-currency wording without liquidity category support."
    if canonical == "interest_rate_risk" and any(token in value_text for token in ("internal control", "risk identification", "mitigation processes")):
        return "interest_rate_risk carries governance/control wording."
    if canonical in {"foreign_exchange_risk", "market_risk"} and numeric_value is not None:
        return f"{canonical} carries borrowings-derived numeric signal."
    return None


def _bucket_payload(item: Dict[str, Any], *, category: Optional[str] = None) -> Dict[str, Any]:
    compact = _first_compact_evidence(item.get("evidence_references"))
    payload = {
        "value": item.get("value"),
        "category": category or item.get("canonical_category"),
        "canonical_category": item.get("canonical_category") or category,
        "capital_allocation_group": item.get("capital_allocation_group"),
        "source_year": item.get("source_year"),
        "source_artifact": item.get("source_artifact"),
        "source_item_id": item.get("source_item_id"),
        "evidence_ids": list(item.get("evidence_ids") or []),
        "status": item.get("status"),
        "confidence": item.get("confidence") or compact.get("confidence"),
        "source_page": item.get("page") or compact.get("source_page"),
        "short_excerpt": compact.get("short_excerpt"),
        "cash_flow_effect": item.get("cash_flow_effect"),
        "balance_sheet_effect": item.get("balance_sheet_effect"),
        "is_true_capital_deployment": item.get("is_true_capital_deployment"),
        "is_shareholder_return": item.get("is_shareholder_return"),
        "is_financing_action": item.get("is_financing_action"),
        "is_corporate_action": item.get("is_corporate_action"),
        "is_related_party": item.get("is_related_party"),
        "reasoning": item.get("reasoning"),
    }
    for field in (
        "amount",
        "counterparty",
        "relationship",
        "repayment_terms",
        "approval_oversight_detail",
        "auditor_observation",
        "numeric_value",
    ):
        value = item.get(field)
        if value not in (None, "", [], {}):
            payload[field] = value
    return payload


class MultiYearCompanyMemoryBuilder(CompanyMemoryAggregateBuilder):
    def __init__(self, company: str, companies_root: Path | str = Path("companies")):
        super().__init__(company=company, companies_root=companies_root)
        self.company_memory_dir = self.company_root / "company_memory"
        self.output_dir = self.company_memory_dir / "multi_year"
        self.taxonomy: Optional[ArchetypeRegistry] = None

    def _source_paths(self, year_records: Sequence[Dict[str, Any]]) -> List[Path]:
        paths: List[Path] = []
        for record in year_records:
            intelligence_dir = Path(record["paths"]["intelligence_dir"])
            for filename in YEARLY_ARTIFACTS:
                paths.append(intelligence_dir / filename)
        for filename in OPTIONAL_COMPANY_MEMORY_ARTIFACTS:
            paths.append(self.company_memory_dir / filename)
        return paths

    def _build_snapshot(self, year_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        snapshot = super()._build_snapshot(year_record)
        if snapshot is None:
            return None

        cim = year_record.get("company_intelligence") or {}
        raw_items = (((cim.get("financial") or {}).get("capital_allocation") or {}).get("items") or [])
        enriched_capital_actions = []
        for item in raw_items:
            action = item.get("action")
            if not action:
                continue
            evidence_references = {
                key: item.get(key)
                for key in (
                    "page",
                    "source_chunk",
                    "confidence",
                    "category",
                    "timeline",
                    "severity",
                    "status",
                    "amount",
                    "counterparty",
                    "relationship",
                    "repayment_terms",
                    "approval_oversight_detail",
                    "auditor_observation",
                    "purpose",
                    "canonical_category",
                    "capital_allocation_group",
                    "cash_flow_effect",
                    "balance_sheet_effect",
                    "is_true_capital_deployment",
                    "is_shareholder_return",
                    "is_financing_action",
                    "is_corporate_action",
                    "is_related_party",
                    "reasoning",
                    "currency",
                )
                if item.get(key) not in (None, "", [], {})
            }
            normalized = normalize_capital_allocation_item(item)
            enriched_capital_actions.append(
                {
                    "value": action,
                    "source_year": year_record["year"],
                    "source_artifact": "company_intelligence.json",
                    "source_item_id": item.get("id"),
                    "evidence_references": evidence_references,
                    "status": item.get("status"),
                    "category": item.get("category"),
                    "canonical_category": normalized.get("canonical_category"),
                    "capital_allocation_group": normalized.get("capital_allocation_group"),
                    "cash_flow_effect": normalized.get("cash_flow_effect"),
                    "balance_sheet_effect": normalized.get("balance_sheet_effect"),
                    "is_true_capital_deployment": normalized.get("is_true_capital_deployment"),
                    "is_shareholder_return": normalized.get("is_shareholder_return"),
                    "is_financing_action": normalized.get("is_financing_action"),
                    "is_corporate_action": normalized.get("is_corporate_action"),
                    "is_related_party": normalized.get("is_related_party"),
                    "amount": item.get("amount"),
                    "currency": normalized.get("currency"),
                    "counterparty": item.get("counterparty"),
                    "relationship": item.get("relationship"),
                    "repayment_terms": item.get("repayment_terms"),
                    "approval_oversight_detail": item.get("approval_oversight_detail"),
                    "auditor_observation": item.get("auditor_observation"),
                    "purpose": item.get("purpose"),
                    "reasoning": normalized.get("reasoning"),
                }
            )
        if enriched_capital_actions:
            snapshot["capital_allocation_actions"] = enriched_capital_actions
        return snapshot

    def _decorate_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        decorated = dict(snapshot)
        for key, fallback_key in (
            ("business_dnas", "value"),
            ("management_focus_areas", "value"),
            ("major_projects", "value"),
            ("major_promises", "value"),
            ("key_initiatives", "value"),
            ("risks", "value"),
            ("capital_allocation_actions", "value"),
            ("all_promises", "value"),
            ("important_entities", "entity_name"),
        ):
            decorated[key] = _with_evidence_ids(snapshot.get(key, []), fallback_key)
        return decorated

    def _build_company_year_index(self, year_records: Sequence[Dict[str, Any]], generated_at: Optional[str]) -> Dict[str, Any]:
        return {
            "company": self.company,
            "available_years": [record["year"] for record in year_records if record["status"] == "usable"],
            "years_detected": [record["year"] for record in year_records],
            "artifacts_by_year": {
                record["year"]: [name for name, present in record["available_artifacts"].items() if present]
                for record in year_records
            },
            "missing_artifacts_by_year": {
                record["year"]: [name for name, present in record["available_artifacts"].items() if not present]
                for record in year_records
            },
            "generated_at": generated_at,
        }

    def _build_business_dna_evolution(self, snapshots: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        per_year: Dict[str, Dict[str, Dict[str, Any]]] = {}
        rationale_missing: List[str] = []
        for snapshot in snapshots:
            year = snapshot["year"]
            classification = _load_json(self.company_root / year / "intelligence" / "business_classification.json")
            rationales = list(classification.get("rationale") or [])
            if not rationales:
                rationale_missing.append(year)
            per_year[year] = {}
            for item in snapshot["business_dnas"]:
                dna = str(item.get("value"))
                per_year[year][dna] = {
                    "evidence_ids": list(item.get("evidence_ids", [])),
                    "rationale": rationales,
                }

        all_dnas = sorted({dna for year_map in per_year.values() for dna in year_map})
        years = [snapshot["year"] for snapshot in snapshots]
        timeline: List[Dict[str, Any]] = []
        changes: List[Dict[str, Any]] = []
        stable: List[str] = []
        emerging: List[str] = []
        disappearing: List[str] = []

        for year_index, year in enumerate(years):
            statuses: List[Dict[str, Any]] = []
            detected_dnas = sorted(per_year.get(year, {}).keys())
            previous_years = years[:year_index]
            later_years = years[year_index + 1 :]
            for dna in all_dnas:
                year_info = per_year.get(year, {}).get(dna)
                present = year_info is not None
                if present:
                    previously_seen = any(dna in per_year.get(prev, {}) for prev in previous_years)
                    status = "continued" if previously_seen else "newly_detected"
                    evidence_ids = year_info["evidence_ids"]
                    rationale = year_info["rationale"]
                    missing_rationale = not rationale
                else:
                    future_absences = [later for later in later_years if dna not in per_year.get(later, {})]
                    if not previous_years:
                        continue
                    if len(future_absences) >= 2:
                        status = "possibly_discontinued"
                    else:
                        status = "not_detected_this_year"
                    evidence_ids = []
                    rationale = []
                    missing_rationale = True

                statuses.append(
                    {
                        "dna": dna,
                        "status": status,
                        "evidence_ids": evidence_ids,
                        "rationale": rationale,
                        "missing_rationale": missing_rationale,
                    }
                )

            timeline.append(
                {
                    "year": year,
                    "business_dnas": detected_dnas,
                    "dna_statuses": statuses,
                    "rationale": list({r for item in statuses for r in item["rationale"]}),
                    "evidence_ids": sorted(
                        {
                            evidence_id
                            for item in statuses
                            for evidence_id in item.get("evidence_ids", [])
                        }
                    ),
                }
            )

        for dna in all_dnas:
            detected_years = [year for year in years if dna in per_year.get(year, {})]
            if len(detected_years) > 1:
                stable.append(dna)
            if detected_years and detected_years[-1] == years[-1] and len(detected_years) == 1:
                emerging.append(dna)
            absent_after_last = [year for year in years[years.index(detected_years[-1]) + 1 :] if dna not in per_year.get(year, {})] if detected_years else []
            if len(absent_after_last) >= 2:
                disappearing.append(dna)

        for previous, current in zip(timeline, timeline[1:]):
            previous_map = {item["dna"]: item["status"] for item in previous["dna_statuses"]}
            current_map = {item["dna"]: item["status"] for item in current["dna_statuses"]}
            changed = [
                {
                    "dna": dna,
                    "from_status": previous_map.get(dna),
                    "to_status": current_map.get(dna),
                }
                for dna in all_dnas
                if previous_map.get(dna) != current_map.get(dna)
            ]
            if changed:
                changes.append(
                    {
                        "from_year": previous["year"],
                        "to_year": current["year"],
                        "status_changes": changed,
                    }
                )

        result = {
            "company": self.company,
            "timeline": timeline,
            "changes_detected": changes,
            "stable_themes": stable,
            "emerging_themes": emerging,
            "disappearing_themes": disappearing,
        }
        if rationale_missing:
            result["missing_rationale"] = rationale_missing
        return result

    def _enrich_theme_items(self, items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        for item in items:
            first_evidence = _first_compact_evidence(item.get("evidence_references"))
            canonical = self.taxonomy.normalize_theme(
                item.get("value"),
                category=item.get("category"),
                status=item.get("status"),
                source_year=item.get("source_year"),
                source_artifact=item.get("source_artifact"),
                source_item_id=item.get("source_item_id"),
                evidence_ids=item.get("evidence_ids", []),
                evidence_category=first_evidence.get("category"),
            )
            copy = dict(item)
            copy["canonical_theme"] = canonical["canonical_theme"]
            copy["theme_group"] = canonical["theme_group"]
            copy["raw_label"] = item.get("value")
            if canonical.get("candidate_label") is not None:
                copy["candidate_label"] = canonical["candidate_label"]
            if canonical.get("needs_taxonomy_review"):
                copy["needs_taxonomy_review"] = True
            copy["normalized_status"] = _normalize_status(item.get("status") or first_evidence.get("status"))
            copy["evidence_references"] = _compact_evidence(item.get("evidence_references"))
            enriched.append(copy)
        return enriched

    def _build_strategy_timeline(self, year_records: Sequence[Dict[str, Any]], snapshots: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        timeline: List[Dict[str, Any]] = []
        unresolved: List[str] = []

        for record in year_records:
            if record["status"] != "usable":
                unresolved.append(f"{record['year']}: not enough yearly intelligence artifacts to compare strategy.")

        for snapshot in snapshots:
            management_focus = self._enrich_theme_items(snapshot["management_focus_areas"])
            major_projects = self._enrich_theme_items(snapshot["major_projects"])
            major_initiatives = self._enrich_theme_items(snapshot["key_initiatives"])
            external_context = self._enrich_theme_items(snapshot.get("external_context_items", []))
            strategic_themes = sorted(
                {
                    item["canonical_theme"]
                    for item in management_focus + major_projects + major_initiatives
                    if item.get("canonical_theme")
                }
            )
            if not strategic_themes:
                unresolved.append(f"{snapshot['year']}: no management focus or initiative themes found in available artifacts.")
            timeline.append(
                {
                    "year": snapshot["year"],
                    "management_focus": management_focus,
                    "major_projects": major_projects,
                    "major_initiatives": major_initiatives,
                    "external_context": external_context,
                    "strategic_themes": strategic_themes,
                    "evidence_ids": sorted(
                        {
                            evidence_id
                            for bucket in (management_focus, major_projects, major_initiatives, external_context)
                            for item in bucket
                            for evidence_id in item.get("evidence_ids", [])
                        }
                    ),
                }
            )

        continuity: Dict[str, List[str]] = {}
        external_continuity: Dict[str, List[str]] = {}
        raw_labels_by_theme: Dict[str, List[str]] = {}
        external_raw_labels_by_theme: Dict[str, List[str]] = {}
        for entry in timeline:
            year = entry["year"]
            for item in entry["management_focus"] + entry["major_projects"]:
                continuity.setdefault(item["canonical_theme"], [])
                if year not in continuity[item["canonical_theme"]]:
                    continuity[item["canonical_theme"]].append(year)
                raw_labels_by_theme.setdefault(item["canonical_theme"], [])
                if item["raw_label"] and item["raw_label"] not in raw_labels_by_theme[item["canonical_theme"]]:
                    raw_labels_by_theme[item["canonical_theme"]].append(item["raw_label"])
            for item in entry.get("external_context", []):
                external_continuity.setdefault(item["canonical_theme"], [])
                if year not in external_continuity[item["canonical_theme"]]:
                    external_continuity[item["canonical_theme"]].append(year)
                external_raw_labels_by_theme.setdefault(item["canonical_theme"], [])
                if item["raw_label"] and item["raw_label"] not in external_raw_labels_by_theme[item["canonical_theme"]]:
                    external_raw_labels_by_theme[item["canonical_theme"]].append(item["raw_label"])

        repeated_focus = sorted([theme for theme, years in continuity.items() if len(years) > 1])
        shifts = []
        for previous, current in zip(timeline, timeline[1:]):
            previous_themes = set(previous["strategic_themes"])
            current_themes = set(current["strategic_themes"])
            added = sorted(current_themes - previous_themes)
            removed = sorted(previous_themes - current_themes)
            if added or removed:
                shifts.append(
                    {
                        "from_year": previous["year"],
                        "to_year": current["year"],
                        "added_themes": added,
                        "removed_themes": removed,
                    }
                )

        return {
            "company": self.company,
            "timeline": timeline,
            "strategy_continuity": [
                {"theme": theme, "years_active": years}
                for theme, years in sorted(continuity.items())
                if len(years) > 1
            ],
            "strategy_shifts": shifts,
            "unresolved_strategy_questions": unresolved,
            "theme_mentions_by_year": {theme: years for theme, years in sorted(continuity.items())},
            "raw_labels_by_canonical_theme": {theme: labels for theme, labels in sorted(raw_labels_by_theme.items())},
            "external_context_theme_mentions_by_year": {theme: years for theme, years in sorted(external_continuity.items())},
            "external_context_raw_labels_by_canonical_theme": {
                theme: labels for theme, labels in sorted(external_raw_labels_by_theme.items())
            },
            "repeated_focus_areas": repeated_focus,
            "changed_focus_areas": sorted({theme for shift in shifts for theme in shift["added_themes"] + shift["removed_themes"]}),
        }

    def _build_promise_tracker(self, snapshots: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
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
                        "promise_id": f"promise_{_slug(item['source_year'])}_{_theme_key(item['value'])}",
                        "normalized_promise": _theme_key(item["value"]),
                        "representative_promise": item["value"],
                        "mentions": [],
                    }
                    groups.append(matched_group)
                matched_group["mentions"].append(item)

        promises: List[Dict[str, Any]] = []
        for group in sorted(groups, key=lambda current: parse_financial_year(current["mentions"][0]["source_year"])):
            mentions = sorted(group["mentions"], key=lambda item: parse_financial_year(item["source_year"]))
            years = [item["source_year"] for item in mentions]
            statuses = {item["source_year"]: item.get("status") or "UNKNOWN" for item in mentions}
            exact_forms = {_normalize_text(item["value"]) for item in mentions}
            confidence = 0.95 if len(exact_forms) == 1 else 0.75
            promises.append(
                {
                    "promise_id": group["promise_id"],
                    "normalized_promise": group["normalized_promise"],
                    "first_seen_year": years[0],
                    "repeated_years": years[1:],
                    "latest_status": statuses[years[-1]],
                    "status_by_year": statuses,
                    "related_evidence_ids": sorted(
                        {
                            evidence_id
                            for item in mentions
                            for evidence_id in item.get("evidence_ids", [])
                        }
                    ),
                    "confidence": confidence,
                    "source_mentions": [
                        {
                            "value": item["value"],
                            "source_year": item["source_year"],
                            "source_artifact": item["source_artifact"],
                            "source_item_id": item["source_item_id"],
                            "evidence_ids": item.get("evidence_ids", []),
                        }
                        for item in mentions
                    ],
                }
            )

        return {
            "company": self.company,
            "promises": promises,
            "fulfilled_promises": [item["promise_id"] for item in promises if str(item["latest_status"]).upper() in {"DONE", "FULFILLED", "COMPLETED"}],
            "repeated_unresolved_promises": [item["promise_id"] for item in promises if item["repeated_years"] and str(item["latest_status"]).upper() == "UNKNOWN"],
            "abandoned_or_disappeared_promises": [item["promise_id"] for item in promises if str(item["latest_status"]).upper() in {"ABANDONED", "DROPPED", "DISCONTINUED"}],
            "unclear_promises": [item["promise_id"] for item in promises if str(item["latest_status"]).upper() == "UNKNOWN"],
        }

    def _dedupe_year_risks(self, items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for item in items:
            compact_evidence = _first_compact_evidence(item.get("evidence_references"))
            primary_category = item.get("category") or compact_evidence.get("category")
            canonical = None
            if primary_category:
                category_only = self.taxonomy.normalize_risk(
                    primary_category,
                    None,
                    severity=_severity_value(item),
                    evidence_category=primary_category,
                )
                if category_only != _slug(primary_category):
                    canonical = category_only
            if canonical is None:
                canonical = self.taxonomy.normalize_risk(
                    primary_category or item.get("value"),
                    item.get("value") if primary_category else item.get("category"),
                    severity=_severity_value(item),
                    evidence_category=primary_category,
                )
            current = merged.setdefault(
                canonical,
                {
                    "canonical_risk": canonical,
                    "value": item.get("value"),
                    "source_year": item.get("source_year"),
                    "source_artifact": item.get("source_artifact"),
                    "source_item_id": item.get("source_item_id"),
                    "confidence": item.get("confidence"),
                    "severity": _severity_value(item),
                    "evidence_ids": [],
                    "evidence_references": [],
                    "numeric_value": None,
                    "source_page": None,
                },
            )
            current["evidence_ids"] = sorted(set(current["evidence_ids"]) | set(item.get("evidence_ids", [])))
            current["evidence_references"].extend(_compact_evidence(item.get("evidence_references")))
            current_score = (
                SEVERITY_RANK.get(str(current.get("severity") or "unknown"), 0),
                len(str(current.get("value") or "")),
            )
            candidate_score = (
                SEVERITY_RANK.get(_severity_value(item), 0),
                len(str(item.get("value") or "")),
            )
            if candidate_score > current_score:
                current["value"] = item.get("value")
                current["source_item_id"] = item.get("source_item_id")
                current["source_page"] = compact_evidence.get("source_page")
            new_severity = _severity_value(item)
            if SEVERITY_RANK.get(new_severity, 0) > SEVERITY_RANK.get(current["severity"], 0):
                current["severity"] = new_severity
            numeric_value = _borrowings_signal(item, canonical)
            if numeric_value is not None and (current["numeric_value"] is None or numeric_value > current["numeric_value"]):
                current["numeric_value"] = numeric_value
        for current in merged.values():
            current["validation_warning"] = _risk_validation_warning(current)
        return list(merged.values())

    def _build_risk_evolution(self, snapshots: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        groups: Dict[str, Dict[str, Any]] = {}
        timeline: List[Dict[str, Any]] = []
        latest_year = _latest_year([snapshot["year"] for snapshot in snapshots])

        for snapshot in snapshots:
            year_risks = self._dedupe_year_risks(snapshot["risks"])
            timeline.append({"year": snapshot["year"], "risks": year_risks})
            for item in year_risks:
                group = groups.setdefault(
                    item["canonical_risk"],
                    {
                        "risk_id": f"risk_{item['canonical_risk']}",
                        "normalized_risk": item["canonical_risk"],
                        "mentions": [],
                    },
                )
                group["mentions"].append(item)

        risks: List[Dict[str, Any]] = []
        worsening: List[str] = []
        improving: List[str] = []
        recurring: List[str] = []
        new_risks: List[str] = []
        unresolved: List[str] = []
        qa_warnings: List[Dict[str, Any]] = []

        for canonical, group in sorted(groups.items()):
            mentions = sorted(group["mentions"], key=lambda item: parse_financial_year(item["source_year"]))
            years = [item["source_year"] for item in mentions]
            severity_by_year = {item["source_year"]: item["severity"] for item in mentions}
            latest_severity = severity_by_year[years[-1]]
            numeric_by_year = {item["source_year"]: item["numeric_value"] for item in mentions if item.get("numeric_value") is not None}
            first_rank = SEVERITY_RANK.get(severity_by_year[years[0]], 0)
            latest_rank = SEVERITY_RANK.get(latest_severity, 0)
            if latest_rank > first_rank:
                worsening.append(group["risk_id"])
            elif latest_rank < first_rank:
                improving.append(group["risk_id"])

            if canonical == "liquidity_risk" and len(numeric_by_year) >= 2:
                ordered_numeric_years = sorted(numeric_by_year, key=parse_financial_year)
                first_value = numeric_by_year[ordered_numeric_years[0]]
                last_value = numeric_by_year[ordered_numeric_years[-1]]
                if first_value and last_value and last_value > first_value * 1.2:
                    if group["risk_id"] not in worsening:
                        worsening.append(group["risk_id"])

            record = {
                "risk_id": group["risk_id"],
                "normalized_risk": canonical,
                "first_seen_year": years[0],
                "repeated_years": years[1:],
                "severity_by_year": severity_by_year,
                "latest_severity": latest_severity,
                "related_evidence_ids": sorted({evidence_id for item in mentions for evidence_id in item["evidence_ids"]}),
                "confidence": 0.8 if len(mentions) > 1 else 0.7,
                "numeric_signals_by_year": numeric_by_year,
                "source_mentions": [
                    {
                        "value": item["value"],
                        "source_year": item["source_year"],
                        "source_artifact": item["source_artifact"],
                        "source_item_id": item["source_item_id"],
                        "evidence_ids": item["evidence_ids"],
                        "source_page": next((ref.get("source_page") for ref in item["evidence_references"] if ref.get("source_page") is not None), None),
                        "short_excerpt": next((ref.get("short_excerpt") for ref in item["evidence_references"] if ref.get("short_excerpt")), None),
                        "confidence": item.get("confidence"),
                        "severity": item["severity"],
                    }
                    for item in mentions
                ],
            }
            warnings = [item.get("validation_warning") for item in mentions if item.get("validation_warning")]
            if warnings:
                record["validation_warnings"] = sorted(set(warnings))
                qa_warnings.append(
                    {
                        "risk_id": record["risk_id"],
                        "normalized_risk": canonical,
                        "warnings": sorted(set(warnings)),
                    }
                )
            risks.append(record)
            if record["repeated_years"]:
                recurring.append(record["risk_id"])
            if record["first_seen_year"] == latest_year:
                new_risks.append(record["risk_id"])
            if latest_severity not in {"low", "unknown"}:
                unresolved.append(record["risk_id"])

        return {
            "company": self.company,
            "timeline": timeline,
            "risks": risks,
            "recurring_risks": recurring,
            "new_risks": new_risks,
            "worsening_risks": sorted(set(worsening)),
            "improving_risks": sorted(set(improving)),
            "unresolved_risks": unresolved,
            "qa_warnings": qa_warnings,
        }

    def _build_capital_allocation_timeline(self, year_records: Sequence[Dict[str, Any]], snapshots: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        timeline: List[Dict[str, Any]] = []
        category_years: Dict[str, List[str]] = {}
        missing_evidence: List[Dict[str, Any]] = []

        for record in year_records:
            if record["status"] != "usable":
                missing_evidence.append({"year": record["year"], "reason": record["reason"] or "No usable intelligence artifacts found"})

        for snapshot in snapshots:
            bucket_payload = {
                field: []
                for field in (
                    list(CAPITAL_TIMELINE_FIELDS.values())
                    + list(dict.fromkeys(CAPITAL_CATEGORY_TIMELINE_FIELDS.values()))
                )
            }
            evidence_ids: List[str] = []
            for item in snapshot["capital_allocation_actions"]:
                normalized = dict(item)
                if not normalized.get("canonical_category") or not normalized.get("capital_allocation_group"):
                    fallback = normalize_capital_allocation_item(
                        {
                            "action": item.get("value"),
                            "category": item.get("category"),
                            "purpose": item.get("purpose"),
                            "status": item.get("status"),
                            "counterparty": item.get("counterparty"),
                            "relationship": item.get("relationship"),
                        }
                    )
                    normalized.update(
                        {
                            "canonical_category": fallback.get("canonical_category"),
                            "capital_allocation_group": fallback.get("capital_allocation_group"),
                            "cash_flow_effect": fallback.get("cash_flow_effect"),
                            "balance_sheet_effect": fallback.get("balance_sheet_effect"),
                            "is_true_capital_deployment": fallback.get("is_true_capital_deployment"),
                            "is_shareholder_return": fallback.get("is_shareholder_return"),
                            "is_financing_action": fallback.get("is_financing_action"),
                            "is_corporate_action": fallback.get("is_corporate_action"),
                            "is_related_party": fallback.get("is_related_party"),
                            "reasoning": fallback.get("reasoning"),
                        }
                    )

                detail = _bucket_payload(
                    normalized,
                    category=normalized.get("canonical_category"),
                )
                evidence_ids.extend(detail["evidence_ids"])

                group = str(normalized.get("capital_allocation_group") or "uncertain")
                group_field = CAPITAL_TIMELINE_FIELDS.get(group, "uncertain")
                bucket_payload[group_field].append(detail)
                if snapshot["year"] not in category_years.setdefault(group, []):
                    category_years[group].append(snapshot["year"])

                category = str(normalized.get("canonical_category") or "uncertain")
                category_field = CAPITAL_CATEGORY_TIMELINE_FIELDS.get(category)
                if category_field:
                    bucket_payload[category_field].append(detail)

            if not snapshot["capital_allocation_actions"]:
                missing_evidence.append({"year": snapshot["year"], "reason": "No capital allocation actions found in available yearly intelligence."})

            timeline.append(
                {
                    "year": snapshot["year"],
                    **bucket_payload,
                    "evidence_ids": sorted(set(evidence_ids)),
                }
            )

        patterns = [{"category": category, "years_active": years} for category, years in category_years.items() if years]
        recurring_concerns = [
            category
            for category in (
                "related_party_capital_flows",
                "accounting_or_disclosure_only",
                "financing_actions",
                "ownership_transfer_non_company_cashflow",
            )
            if len(category_years.get(category, [])) > 1
        ]

        return {
            "company": self.company,
            "timeline": timeline,
            "capital_allocation_patterns": patterns,
            "recurring_concerns": recurring_concerns,
            "missing_financial_evidence": missing_evidence,
        }

    def _build_management_consistency(self, strategy_timeline: Dict[str, Any], promise_tracker: Dict[str, Any]) -> Dict[str, Any]:
        theme_mentions = strategy_timeline.get("theme_mentions_by_year", {})
        raw_labels = strategy_timeline.get("raw_labels_by_canonical_theme", {})
        external_theme_mentions = strategy_timeline.get("external_context_theme_mentions_by_year", {})
        observations: List[Dict[str, Any]] = []
        for theme, years in sorted(theme_mentions.items()):
            status = "consistent" if len(years) > 1 else "unclear"
            explanation = (
                "Available disclosures show this canonical focus area recurring across multiple years."
                if status == "consistent"
                else "Not enough evidence to judge consistency from available yearly artifacts."
            )
            evidence_ids = sorted(
                {
                    evidence_id
                    for entry in strategy_timeline.get("timeline", [])
                    if entry["year"] in years
                    for item in entry.get("management_focus", [])
                    if item.get("canonical_theme") == theme
                    for evidence_id in item.get("evidence_ids", [])
                }
            )
            observations.append(
                {
                    "theme": theme,
                    "years_active": years,
                    "raw_labels": raw_labels.get(theme, []),
                    "evidence_ids": evidence_ids,
                    "consistency_status": status,
                    "explanation": explanation,
                }
            )

        evidence_gaps = list(strategy_timeline.get("unresolved_strategy_questions", []))
        if len(strategy_timeline.get("timeline", [])) <= 2:
            evidence_gaps.append("Only two usable years are currently available; consistency conclusions remain provisional.")
        if not observations:
            evidence_gaps.append("No repeated management-focus themes were available for cross-year consistency review.")

        return {
            "company": self.company,
            "consistency_observations": observations,
            "repeated_focus_areas": strategy_timeline.get("repeated_focus_areas", []),
            "changed_focus_areas": strategy_timeline.get("changed_focus_areas", []),
            "theme_mentions_by_year": theme_mentions,
            "raw_labels_by_canonical_theme": raw_labels,
            "external_context_recurring_themes": sorted(
                [theme for theme, years in external_theme_mentions.items() if len(years) > 1]
            ),
            "external_context_theme_mentions_by_year": external_theme_mentions,
            "promise_follow_through_summary": {
                "fulfilled_promises": promise_tracker.get("fulfilled_promises", []),
                "repeated_unresolved_promises": promise_tracker.get("repeated_unresolved_promises", []),
                "unclear_promises": promise_tracker.get("unclear_promises", []),
            },
            "evidence_gaps": evidence_gaps,
        }

    def _build_multi_year_index(
        self,
        year_records: Sequence[Dict[str, Any]],
        generated_at: Optional[str],
        artifacts_generated: Sequence[str],
        business_dna_evolution: Dict[str, Any],
        management_consistency: Dict[str, Any],
        risk_evolution: Dict[str, Any],
    ) -> Dict[str, Any]:
        source_artifacts = {
            "yearly_intelligence": {
                record["year"]: [filename for filename, present in record["available_artifacts"].items() if present]
                for record in year_records
            },
            "company_memory": [filename for filename in OPTIONAL_COMPANY_MEMORY_ARTIFACTS if (self.company_memory_dir / filename).exists()],
        }
        limitations = [f"{record['year']}: {record['reason']}" for record in year_records if record["status"] != "usable"]
        usable_years = [record["year"] for record in year_records if record["status"] == "usable"]
        if len(usable_years) <= 2:
            limitations.append("Only two usable years are available, so trend and discontinuation judgments remain provisional.")
        if business_dna_evolution.get("missing_rationale"):
            limitations.append(f"Missing business-classification rationale for: {', '.join(business_dna_evolution['missing_rationale'])}.")
        if any(item.get("consistency_status") == "unclear" for item in management_consistency.get("consistency_observations", [])):
            limitations.append("Theme matching is deterministic and may need human review for borderline wording differences.")
        if not any(risk.get("numeric_signals_by_year") for risk in risk_evolution.get("risks", [])):
            limitations.append("No numeric trend extraction was available for risk worsening detection in the current artifacts.")
        if not limitations:
            limitations.append("Deterministic normalization is in use; cross-year grouping may still require human review for ambiguous labels.")

        return {
            "company": self.company,
            "generated_at": generated_at,
            "artifacts_generated": list(artifacts_generated),
            "years_covered": usable_years,
            "limitations": limitations,
            "source_artifacts": source_artifacts,
        }

    def build(self) -> Dict[str, Path]:
        year_records = [self._load_year_record(year_dir) for year_dir in self._discover_years()]
        snapshots = [
            self._decorate_snapshot(snapshot)
            for snapshot in (self._build_snapshot(year_record) for year_record in year_records)
            if snapshot is not None
        ]
        business_dnas = sorted(
            {
                str(item.get("value"))
                for snapshot in snapshots
                for item in snapshot.get("business_dnas", [])
                if item.get("value")
            }
        )
        self.taxonomy = ArchetypeRegistry(
            company=self.company,
            business_dnas=business_dnas,
            company_root=self.company_root,
        )
        generated_at = _generated_at(self._source_paths(year_records))

        company_year_index = self._build_company_year_index(year_records, generated_at)
        business_dna_evolution = self._build_business_dna_evolution(snapshots)
        strategy_timeline = self._build_strategy_timeline(year_records, snapshots)
        promise_tracker = self._build_promise_tracker(snapshots)
        risk_evolution = self._build_risk_evolution(snapshots)
        capital_allocation_timeline = self._build_capital_allocation_timeline(year_records, snapshots)
        management_consistency = self._build_management_consistency(strategy_timeline, promise_tracker)

        files = {
            "company_year_index.json": company_year_index,
            "business_dna_evolution.json": business_dna_evolution,
            "strategy_timeline.json": strategy_timeline,
            "promise_tracker.json": promise_tracker,
            "risk_evolution.json": risk_evolution,
            "capital_allocation_timeline.json": capital_allocation_timeline,
            "management_consistency.json": management_consistency,
            "taxonomy_review_candidates.json": {
                "company": self.company,
                "loaded_archetypes": self.taxonomy.get_loaded_pack_ids(),
                "review_candidates": self.taxonomy.get_review_candidates(),
            },
        }
        files["multi_year_index.json"] = self._build_multi_year_index(
            year_records,
            generated_at,
            artifacts_generated=files.keys(),
            business_dna_evolution=business_dna_evolution,
            management_consistency=management_consistency,
            risk_evolution=risk_evolution,
        )

        written_paths: Dict[str, Path] = {}
        for filename, payload in files.items():
            written_paths[filename] = _write_json(self.output_dir / filename, payload)
        return written_paths
