from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from knowledge.company_memory import parse_financial_year

from knowledge.capital_allocation_taxonomy import normalize_capital_allocation_item

from .contracts import (
    ALLOCATION_CATEGORIES,
    ALLOCATION_CURRENT_STATUSES,
    ALLOCATION_FUNDING_SOURCES,
    ALLOCATION_OUTCOME_STATUSES,
    ALLOCATION_OUTCOMES_GENERATOR_VERSION,
    ALLOCATION_OUTCOMES_MANIFEST_SCHEMA_VERSION,
    ALLOCATION_OUTCOMES_SCHEMA_VERSION,
)
from .manifest import build_capital_allocation_manifest
from .paths import (
    get_capital_allocation_assessments_path,
    get_capital_allocation_manifest_path,
    get_capital_allocation_outcomes_dir,
    get_capital_allocation_outcomes_path,
    get_capital_allocation_timelines_path,
    get_capital_allocation_validation_path,
)
from .progression import CapitalAllocationOutcomesProgressionAdapter, build_capital_allocation_event, build_timeline
from .validators import validate_capital_allocation_outcomes_payload
from .writer import write_json_file
from intelligence.progression import build_confidence


RELEVANT_SOURCE_GROUPS = {
    "true_capital_deployment",
    "shareholder_returns",
    "financing_actions",
    "treasury_actions",
    "related_party_capital_flows",
}

IGNORED_SOURCE_GROUPS = {
    "corporate_actions_non_cash_or_admin",
    "ownership_transfer_non_company_cashflow",
    "accounting_or_disclosure_only",
    "uncertain",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "our",
    "the",
    "to",
    "with",
    "we",
    "will",
    "this",
    "that",
    "these",
    "those",
    "company",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Dict[str, Any] | List[Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_company_payload(path: Path) -> Dict[str, Any]:
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


def _normalize_text(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _token_set(value: Any) -> set[str]:
    return {token for token in _normalize_text(value).split() if token and token not in STOPWORDS}


def _short_excerpt(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _slug(value: Any) -> str:
    slug = _normalize_text(value).replace(" ", "_").strip("_")
    return slug or "item"


def _year_sort_key(value: str) -> int:
    try:
        return parse_financial_year(str(value).strip().lower())
    except Exception:
        return 10_000


def _years_covered(periods: Iterable[str]) -> List[str]:
    return sorted({str(period).strip().lower() for period in periods if str(period).strip()}, key=_year_sort_key)


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = " ".join(str(value or "").split()).strip()
        if text:
            return text
    return ""


def _value_to_float(value: Any) -> Optional[float]:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"([-+]?[0-9][0-9,]*\.?[0-9]*)", str(value))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _company_root(company: str) -> Path:
    return Path("companies") / company


def _load_related_records(company_root: Path) -> Dict[str, List[Dict[str, Any]]]:
    def _extract(path: Path, key_options: Sequence[str]) -> List[Dict[str, Any]]:
        payload = _load_company_payload(path)
        for key in key_options:
            items = payload.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    return {
        "commitments": _extract(company_root / "company_memory" / "management_commitments" / "management_commitments.json", ("commitments",)),
        "projects": _extract(company_root / "company_memory" / "projects" / "projects_registry.json", ("projects",)),
        "capacity": _extract(company_root / "company_memory" / "capacity" / "capacity_registry.json", ("capacity_items", "capacities")),
        "risks": _extract(company_root / "company_memory" / "risks" / "risk_registry.json", ("risks",)),
    }


def _load_financial_artifacts(company_root: Path) -> Dict[str, Any]:
    financial_root = company_root / "company_memory" / "financials"
    investor_dir = financial_root / "investor_financial_modules"
    return {
        "financial_memory_summary": _load_company_payload(financial_root / "financial_memory_summary.json"),
        "financial_driver_attribution": _load_company_payload(financial_root / "financial_driver_attribution.json"),
        "financial_truth_pack": _load_company_payload(financial_root / "financial_truth_pack.json"),
        "capital_allocation_financial_timeline": _load_company_payload(financial_root / "capital_allocation_financial_timeline.json"),
        "capital_allocation_roi_ledger": _load_company_payload(investor_dir / "capital_allocation_roi_ledger.json"),
    }


def _build_source_reference(
    *,
    source_year: str,
    source_artifact: str,
    source_item_id: Any,
    source_page: Any = None,
    short_excerpt: Any = "",
    evidence_ids: Sequence[Any] | None = None,
    capital_allocation_group: str | None = None,
    canonical_category: str | None = None,
) -> Dict[str, Any]:
    reference = {
        "source_year": source_year,
        "source_artifact": source_artifact,
        "source_item_id": source_item_id,
        "source_page": source_page,
        "short_excerpt": _short_excerpt(short_excerpt),
        "evidence_ids": [str(item) for item in (evidence_ids or []) if str(item).strip()],
    }
    if capital_allocation_group:
        reference["capital_allocation_group"] = capital_allocation_group
    if canonical_category:
        reference["canonical_category"] = canonical_category
    return {key: value for key, value in reference.items() if value not in (None, "", [], {})}


def _allocation_name_from_item(item: Dict[str, Any], ledger_entry: Dict[str, Any], allocation_category: str) -> str:
    raw_name = _first_nonempty(
        item.get("value"),
        item.get("purpose"),
        ledger_entry.get("purpose"),
        item.get("canonical_category"),
        item.get("capital_allocation_group"),
    )
    if not raw_name:
        raw_name = allocation_category.replace("_", " ")
    cleaned = " ".join(raw_name.split())
    lowered = cleaned.lower()
    replacements = {
        "capital is being returned to shareholders": "Shareholder return",
        "capital is being deployed into operating assets": "Operating reinvestment",
        "raised capital is still not fully deployed": "Pending deployment",
        "no clear capital-allocation event was identified": "Capital allocation event",
        "no clear capital allocation event was identified": "Capital allocation event",
    }
    for needle, replacement in replacements.items():
        if needle in lowered:
            return replacement
    if allocation_category == "dividend" and "dividend" not in lowered:
        return "Dividend return"
    if allocation_category == "share_buyback" and "buyback" not in lowered and "repurchase" not in lowered:
        return "Share buyback"
    if allocation_category == "equity_issuance" and "equity" not in lowered and "issue" not in lowered:
        return "Equity issuance"
    if allocation_category == "debt_repayment" and "debt" not in lowered and "repay" not in lowered:
        return "Debt repayment"
    if allocation_category in {"capacity_expansion", "organic_capex", "maintenance_capex"} and "capex" not in lowered and "capacity" not in lowered:
        return allocation_category.replace("_", " ").title()
    return cleaned[:140]


def _name_specificity_score(name: str) -> int:
    return len(_token_set(name))


def _family_key(allocation_category: str, allocation_name: str) -> str:
    tokens = [token for token in _token_set(allocation_name) if token not in {"capital", "allocation", "event", "capitalallocation"}]
    if len(tokens) < 3:
        return allocation_category
    return " ".join(tokens[:6])


def _inferred_business_purpose(allocation_category: str, item: Dict[str, Any], ledger_entry: Dict[str, Any]) -> str:
    text = _first_nonempty(
        item.get("reasoning"),
        item.get("value"),
        item.get("purpose"),
        ledger_entry.get("purpose"),
        ledger_entry.get("investor_interpretation"),
    )
    if allocation_category in {"dividend", "special_dividend", "share_buyback"}:
        return "Return excess capital or cash to shareholders."
    if allocation_category in {"equity_issuance", "debt_funded_investment"}:
        return "Raise capital to fund future investment capacity."
    if allocation_category == "debt_repayment":
        return "Reduce leverage and strengthen the balance sheet."
    if allocation_category == "working_capital":
        return "Fund working capital needs and operating cycle pressure."
    if allocation_category in {"capacity_expansion", "organic_capex", "maintenance_capex"}:
        return "Expand or maintain the asset base that supports operations."
    if allocation_category in {"product_development", "research_and_development", "technology_investment"}:
        return "Invest in future product, technology, and capability development."
    if allocation_category in {"acquisition", "acquisition_integration", "strategic_investment", "joint_venture", "subsidiary_investment"}:
        return "Allocate capital toward strategic control, integration, or partnership outcomes."
    if allocation_category == "retained_cash":
        return "Preserve liquidity until management identifies a better use of capital."
    return text or "The capital allocation purpose is not yet specific enough to classify with confidence."


def _map_allocation_category(item: Dict[str, Any], ledger_entry: Dict[str, Any]) -> str:
    text = _normalize_text(
        " ".join(
            part
            for part in (
                item.get("value"),
                item.get("purpose"),
                item.get("category"),
                item.get("canonical_category"),
                item.get("capital_allocation_group"),
                ledger_entry.get("capital_allocation_event_type"),
                ledger_entry.get("purpose"),
                ledger_entry.get("investor_interpretation"),
            )
            if part
        )
    )
    canonical = _normalize_text(item.get("canonical_category"))
    group = _normalize_text(item.get("capital_allocation_group"))

    if canonical in {"cwip", "capex"}:
        return "organic_capex"
    # debt_raised = financing source (proceeds of borrowings), not a deployment — skip to "other"
    # so it doesn't get misclassified as debt_repayment via the canonical check below.
    if canonical == "debt raised":
        return "other"
    if any(term in text for term in ("special dividend", "extra dividend", "one-off dividend", "exceptional dividend")):
        return "special_dividend"
    if canonical in {"dividend_paid", "dividend_declared"} or "dividend" in text:
        return "dividend"
    # "buy back" (hyphen removed by normalizer) must be caught before the debt_repaid canonical check
    if canonical == "buyback" or any(term in text for term in ("buyback", "buy back", "share repurchase", "repurchase of shares")):
        return "share_buyback"
    if canonical == "equity_issuance" or any(term in text for term in ("rights issue", "qip", "preferential allotment", "equity issuance", "fresh issue", "shares allotted")):
        return "equity_issuance"
    if canonical in {"debt_repaid", "lease_liability_payment"} or any(term in text for term in ("debt repayment", "loan repaid", "borrowings repaid", "repayment of borrowings", "lease liability")):
        return "debt_repayment"
    if any(term in text for term in ("working capital", "receivable", "inventory", "payable", "cash conversion")):
        return "working_capital"
    if any(term in text for term in ("unutilised proceeds", "unutilized proceeds", "retained earnings", "cash parked", "surplus cash", "idle cash")):
        return "retained_cash"
    if any(term in text for term in ("maintain", "maintenance", "replacement", "upkeep", "sustaining capex", "sustain capex")):
        return "maintenance_capex"
    if any(term in text for term in ("capacity", "plant", "facility", "factory", "production line", "manufacturing line", "commission", "throughput", "output", "expansion")):
        return "capacity_expansion"
    if any(term in text for term in ("product", "new product", "feature", "offering")):
        return "product_development"
    if any(term in text for term in ("research and development", "r and d", "r&d", "research", "intangible", "innovation")):
        return "research_and_development"
    if any(term in text for term in ("technology", "digital", "software", "automation", "platform", "system")):
        return "technology_investment"
    if any(term in text for term in ("acquisition integration", "integration", "amalgamation", "post merger", "post-acquisition", "m&a integration")):
        return "acquisition_integration"
    if any(term in text for term in ("acquisition", "acquire", "purchase", "takeover", "merge", "amalgamation")):
        return "acquisition"
    if any(term in text for term in ("joint venture", "jv", "partnership", "alliance", "collaboration")):
        return "joint_venture"
    if any(term in text for term in ("subsidiary", "wholly owned subsidiary")):
        return "subsidiary_investment"
    if any(term in text for term in ("restructuring", "reorganization", "reorganisation", "demerger", "spin off", "spin-off")):
        return "restructuring"
    if any(term in text for term in ("debt funded", "borrowed funds", "borrowed capital")):
        return "debt_funded_investment"
    if canonical in {"capital_reduction"} or "capital reduction" in text:
        return "restructuring"
    if canonical in {"cwip", "capex", "strategic_investments"} or group == "true_capital_deployment":
        if any(term in text for term in ("strategic", "investment")):
            return "strategic_investment"
        return "organic_capex"
    if group == "shareholder_returns" and "dividend" in text:
        return "dividend"
    if group == "shareholder_returns" and "buyback" in text:
        return "share_buyback"
    if group == "financing_actions" and any(term in text for term in ("equity", "issue", "allotment", "rights", "qip")):
        return "equity_issuance"
    if group == "financing_actions" and any(term in text for term in ("debt", "repay", "loan", "lease")):
        return "debt_repayment"
    if "retained" in text or "cash" in text:
        return "retained_cash"
    if canonical and canonical not in {"uncertain", "other"} and group in RELEVANT_SOURCE_GROUPS:
        return "other"
    return "unknown"


def _infer_funding_source(allocation_category: str, item: Dict[str, Any], ledger_entry: Dict[str, Any]) -> str:
    text = _normalize_text(
        " ".join(
            part
            for part in (
                item.get("value"),
                item.get("purpose"),
                ledger_entry.get("purpose"),
                ledger_entry.get("investor_interpretation"),
            )
            if part
        )
    )
    if allocation_category in {"equity_issuance"} or any(term in text for term in ("equity issuance", "qip", "rights issue", "preferential allotment", "fresh issue")):
        return "equity_issuance"
    if allocation_category in {"debt_funded_investment"} or any(term in text for term in ("debt funded", "borrowed", "loan", "debt")):
        return "debt"
    if allocation_category in {"dividend", "special_dividend", "share_buyback"}:
        return "retained_cash"
    if allocation_category in {"debt_repayment"}:
        return "operating_cash_flow"
    if allocation_category in {"working_capital", "organic_capex", "capacity_expansion", "maintenance_capex", "product_development", "research_and_development", "technology_investment", "acquisition", "acquisition_integration", "strategic_investment", "joint_venture", "subsidiary_investment"}:
        if ledger_entry.get("capital_raised") not in (None, 0):
            return "equity_issuance"
        if ledger_entry.get("unutilised_issue_proceeds") not in (None, 0):
            return "equity_issuance"
        if any(term in text for term in ("cash reserves", "retained earnings", "surplus cash", "internal accrual", "internal accruals")):
            return "retained_cash"
        return "operating_cash_flow"
    if allocation_category == "retained_cash":
        return "cash_reserves"
    return "unknown"


def _candidate_amount(item: Dict[str, Any], ledger_entry: Dict[str, Any]) -> Optional[float]:
    fields = ("amount", "amount_crore", "amount_raised_crore", "capex_deployed", "working_capital_deployed", "product_development_or_intangible_investment", "debt_repayment", "dividends", "buybacks", "acquisitions", "capital_raised", "retained_earnings", "unutilised_issue_proceeds")
    # Prefer the typed source item. A year-level ledger can describe another
    # allocation family (for example capex while this item is a dividend).
    for field in fields:
        value = _value_to_float(item.get(field))
        if value is not None:
            return abs(value)
    if item.get("suppress_ledger_amount"):
        return None
    for field in fields:
        value = _value_to_float(ledger_entry.get(field))
        if value is not None:
            return abs(value)
    return None


def _amount_basis(item: Dict[str, Any], ledger_entry: Dict[str, Any], amount: Optional[float]) -> str:
    if amount is None:
        return "unknown"
    if _value_to_float(item.get("amount")) is not None or _value_to_float(item.get("amount_crore")) is not None:
        return "source_item"
    if any(_value_to_float(ledger_entry.get(field)) is not None for field in ("capital_raised", "retained_earnings", "capex_deployed", "working_capital_deployed", "product_development_or_intangible_investment", "debt_repayment", "dividends", "buybacks", "acquisitions", "related_party_flows", "unutilised_issue_proceeds")):
        return "ledger_summary"
    return "derived"


def _evidence_status(source_item: Dict[str, Any], ledger_entry: Dict[str, Any], linked_evidence_count: int) -> str:
    if linked_evidence_count >= 2:
        return "supported"
    if source_item.get("evidence_ids") or ledger_entry:
        return "partial"
    return "missing"


def _candidate_text(item: Dict[str, Any], ledger_entry: Dict[str, Any], allocation_name: str, allocation_category: str) -> str:
    return " ".join(
        part
        for part in (
            allocation_name,
            allocation_category,
            item.get("value"),
            item.get("purpose"),
            item.get("status"),
            item.get("reasoning"),
            ledger_entry.get("purpose"),
            ledger_entry.get("investor_interpretation"),
        )
        if part
    )


def _compact_source_item(year: str, item: Dict[str, Any], group: str) -> Dict[str, Any]:
    return _build_source_reference(
        source_year=year,
        source_artifact="capital_allocation_timeline.json",
        source_item_id=item.get("source_item_id"),
        source_page=item.get("source_page"),
        short_excerpt=_first_nonempty(item.get("value"), item.get("purpose"), item.get("reasoning"), item.get("status")),
        evidence_ids=item.get("evidence_ids") or [],
        capital_allocation_group=group,
        canonical_category=item.get("canonical_category"),
    )


def _compact_ledger_reference(year: str, ledger_entry: Dict[str, Any]) -> Dict[str, Any]:
    return _build_source_reference(
        source_year=year,
        source_artifact="capital_allocation_roi_ledger.json",
        source_item_id=year,
        source_page=None,
        short_excerpt=_first_nonempty(ledger_entry.get("purpose"), ledger_entry.get("investor_interpretation")),
    )


def _trend_texts(summary: Dict[str, Any], category: str) -> List[str]:
    if not isinstance(summary, dict):
        return []
    pattern_map = {
        "capacity_expansion": ("scale_pattern", "profitability_pattern", "return_pattern", "capital_allocation_pattern"),
        "organic_capex": ("scale_pattern", "profitability_pattern", "return_pattern", "capital_allocation_pattern"),
        "maintenance_capex": ("scale_pattern", "profitability_pattern", "capital_allocation_pattern"),
        "product_development": ("scale_pattern", "profitability_pattern", "capital_allocation_pattern"),
        "research_and_development": ("scale_pattern", "profitability_pattern", "capital_allocation_pattern"),
        "technology_investment": ("scale_pattern", "profitability_pattern", "capital_allocation_pattern"),
        "acquisition": ("scale_pattern", "profitability_pattern", "return_pattern", "capital_allocation_pattern"),
        "acquisition_integration": ("scale_pattern", "profitability_pattern", "return_pattern", "capital_allocation_pattern"),
        "strategic_investment": ("scale_pattern", "profitability_pattern", "return_pattern", "capital_allocation_pattern"),
        "joint_venture": ("scale_pattern", "profitability_pattern", "capital_allocation_pattern"),
        "subsidiary_investment": ("scale_pattern", "profitability_pattern", "capital_allocation_pattern"),
        "working_capital": ("working_capital_pattern", "cash_conversion_pattern", "capital_allocation_pattern"),
        "debt_repayment": ("balance_sheet_pattern", "cash_conversion_pattern", "capital_allocation_pattern"),
        "equity_issuance": ("balance_sheet_pattern", "per_share_pattern", "capital_allocation_pattern"),
        "share_buyback": ("per_share_pattern", "balance_sheet_pattern", "capital_allocation_pattern"),
        "dividend": ("per_share_pattern", "balance_sheet_pattern", "capital_allocation_pattern"),
        "special_dividend": ("per_share_pattern", "balance_sheet_pattern", "capital_allocation_pattern"),
        "retained_cash": ("balance_sheet_pattern", "capital_allocation_pattern"),
    }
    keys = pattern_map.get(category, ("capital_allocation_pattern", "summary"))
    lines: List[str] = []
    for key in keys:
        value = summary.get(key)
        if isinstance(value, list):
            for item in value[-2:]:
                text = str(item or "").strip()
                if text and text not in lines:
                    lines.append(text)
        elif isinstance(value, str) and value.strip():
            if value not in lines:
                lines.append(value)
    return lines


def _driver_evidence(driver_payload: Dict[str, Any], allocation_text: str) -> List[Dict[str, Any]]:
    attributions = driver_payload.get("attributions") if isinstance(driver_payload, dict) else []
    if not isinstance(attributions, list):
        return []
    candidate_tokens = _token_set(allocation_text)
    selected: List[Dict[str, Any]] = []
    for attribution in attributions:
        if not isinstance(attribution, dict):
            continue
        text = " ".join(
            str(attribution.get(field) or "").strip()
            for field in ("metric", "observed_change", "possible_driver", "supporting_event", "driver_type")
        ).strip()
        if not text:
            continue
        overlap = len(_token_set(text) & candidate_tokens)
        metric = str(attribution.get("metric") or "").lower()
        if overlap >= 2:
            selected.append(
                {
                    "period": attribution.get("period"),
                    "kind": "financial_driver",
                    "note": _short_excerpt(_first_nonempty(attribution.get("observed_change"), attribution.get("possible_driver"), attribution.get("supporting_event"))),
                    "source_artifacts": attribution.get("source_artifacts") or [],
                    "source_references": attribution.get("evidence_ids") or [],
                    "confidence": attribution.get("confidence") or "medium",
                }
            )
        if len(selected) >= 3:
            break
    return selected


def _link_records(record: Dict[str, Any], records: Sequence[Dict[str, Any]], *, fields: Sequence[str], id_field: str, threshold: int = 5) -> List[str]:
    record_text = _normalize_text(" ".join(str(record.get(field) or "") for field in ("allocation_name", "normalized_name", "stated_rationale", "inferred_business_purpose", "progression_summary")))
    record_tokens = _token_set(record_text)
    linked: List[Tuple[int, str]] = []
    for item in records:
        item_text = _normalize_text(" ".join(str(item.get(field) or "") for field in fields))
        item_tokens = _token_set(item_text)
        score = len(record_tokens & item_tokens)
        if record.get("allocation_category") and record.get("allocation_category").replace("_", " ") in item_text:
            score += 2
        if item_text and record_text and (record_text in item_text or item_text in record_text):
            score += 2
        if score >= threshold and item.get(id_field):
            linked.append((score, str(item.get(id_field))))
    linked.sort(key=lambda pair: (-pair[0], pair[1]))
    return [item[1] for item in linked]


def _link_acquisition_records(record: Dict[str, Any], projects: Sequence[Dict[str, Any]]) -> List[str]:
    if record.get("allocation_category") not in {"acquisition", "acquisition_integration"}:
        return []
    record_text = _normalize_text(" ".join(str(record.get(field) or "") for field in ("allocation_name", "normalized_name", "stated_rationale", "inferred_business_purpose")))
    record_tokens = _token_set(record_text)
    linked: List[Tuple[int, str]] = []
    for project in projects:
        project_text = _normalize_text(
            " ".join(
                str(project.get(field) or "")
                for field in ("project_name", "normalized_name", "objective", "business_rationale", "project_type")
            )
        )
        project_tokens = _token_set(project_text)
        score = len(record_tokens & project_tokens)
        if "acquisition" in project_text or "integration" in project_text:
            score += 2
        if score >= 4 and project.get("project_id"):
            linked.append((score, str(project.get("project_id"))))
    linked.sort(key=lambda pair: (-pair[0], pair[1]))
    return [item[1] for item in linked]


def _evidence_from_links(
    record: Dict[str, Any],
    linked_projects: Sequence[Dict[str, Any]],
    linked_capacity: Sequence[Dict[str, Any]],
    linked_commitments: Sequence[Dict[str, Any]],
    linked_risks: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []

    for project in linked_projects:
        if project.get("project_id") not in record.get("linked_project_ids", []):
            continue
        evidence.append(
            {
                "period": project.get("latest_period") or project.get("announcement_period") or project.get("first_observed_period"),
                "kind": "project",
                "note": _short_excerpt(_first_nonempty(project.get("current_status"), project.get("economic_relevance"), project.get("progression_summary"), project.get("objective"))),
                "source_artifacts": ["projects_registry.json", "project_timelines.json"],
                "source_references": project.get("source_references") or [],
            }
        )
        if len(evidence) >= 2:
            break

    for capacity in linked_capacity:
        if capacity.get("capacity_id") not in record.get("linked_capacity_ids", []):
            continue
        evidence.append(
            {
                "period": capacity.get("latest_period") or capacity.get("announcement_period") or capacity.get("first_observed_period"),
                "kind": "capacity",
                "note": _short_excerpt(_first_nonempty(capacity.get("current_status"), capacity.get("economic_relevance"), capacity.get("progression_summary"), capacity.get("purpose"))),
                "source_artifacts": ["capacity_registry.json", "capacity_timelines.json"],
                "source_references": capacity.get("source_references") or [],
            }
        )
        if len(evidence) >= 4:
            break

    for commitment in linked_commitments:
        if commitment.get("id") not in record.get("linked_commitment_ids", []):
            continue
        evidence.append(
            {
                "period": commitment.get("latest_period") or commitment.get("announcement_period"),
                "kind": "commitment",
                "note": _short_excerpt(_first_nonempty(commitment.get("normalized_commitment"), commitment.get("topic"), commitment.get("investor_implication"))),
                "source_artifacts": ["management_commitments.json", "commitment_timeline.json"],
                "source_references": commitment.get("source_references") or [],
            }
        )

    for risk in linked_risks:
        if risk.get("risk_id") not in record.get("linked_risk_ids", []):
            continue
        evidence.append(
            {
                "period": risk.get("latest_period") or risk.get("first_observed_period"),
                "kind": "risk",
                "note": _short_excerpt(_first_nonempty(risk.get("current_status"), risk.get("progression_summary"), risk.get("investor_implication"))),
                "source_artifacts": ["risk_registry.json", "risk_timelines.json"],
                "source_references": risk.get("source_references") or [],
            }
        )
    return evidence


def _financial_outcome_text(record: Dict[str, Any], summary: Dict[str, Any], driver_payload: Dict[str, Any], evidence: Sequence[Dict[str, Any]]) -> Tuple[str, str, str, str]:
    category = str(record.get("allocation_category") or "unknown")
    summary_lines = _trend_texts(summary, category)
    driver_evidence = _driver_evidence(driver_payload, " ".join(summary_lines + [record.get("allocation_name") or "", record.get("stated_rationale") or ""]))
    combined = list(evidence) + driver_evidence

    def _join_notes(kind: str) -> str:
        notes = [item["note"] for item in combined if item.get("kind") == kind and item.get("note")]
        return "; ".join(notes[:2])

    if category in {"capacity_expansion", "organic_capex", "maintenance_capex", "product_development", "research_and_development", "technology_investment", "acquisition", "acquisition_integration", "strategic_investment", "joint_venture", "subsidiary_investment"}:
        operating_outcome = _first_nonempty(
            _join_notes("project"),
            _join_notes("capacity"),
            "No direct operating outcome is yet observable.",
        )
        financial_outcome = _first_nonempty(
            _join_notes("project"),
            _join_notes("capacity"),
            "UNABLE_TO_ATTRIBUTE: No allocation-specific financial outcome is verifiable without a direct causal link.",
        )
        per_share_outcome = "Per-share effects remain indirect and are not yet cleanly attributable."
        balance_sheet_outcome = "The balance sheet absorbed the deployment, but the long-run return profile is still being proven."
    elif category in {"working_capital"}:
        operating_outcome = _first_nonempty(
            _join_notes("capacity"),
            "; ".join(summary_lines[:2]),
            "Working-capital pressure remains visible and needs more follow-up.",
        )
        financial_outcome = _first_nonempty(
            _join_notes("capacity"),
            "UNABLE_TO_ATTRIBUTE: Working-capital deployment financial outcome is not directly attributable.",
        )
        per_share_outcome = "Working-capital efficiency can support per-share compounding, but the evidence is still partial."
        balance_sheet_outcome = "The balance-sheet effect should show up through working-capital intensity and cash conversion."
    elif category in {"debt_repayment"}:
        operating_outcome = "Debt repayment does not change operations directly, but it can reduce financial pressure."
        financial_outcome = "CASH_FLOW_EFFECT: Debt repayment reduces financial liability; interest savings and leverage improvement are the direct financial outcomes."
        per_share_outcome = "Lower leverage may support per-share outcomes over time, but the link is indirect."
        balance_sheet_outcome = "Balance sheet liability reduced; coverage ratios and interest expense are the verifiable outcomes."
    elif category in {"dividend", "special_dividend", "share_buyback", "equity_issuance", "retained_cash"}:
        operating_outcome = "This is primarily a capital-structure or distribution decision rather than an operating investment."
        financial_outcome = "CASH_FLOW_EFFECT: Capital returned to shareholders; the financial outcome is the distribution itself."
        if category in {"equity_issuance"}:
            per_share_outcome = "New equity can improve flexibility, but it may dilute per-share economics."
        elif category in {"share_buyback", "dividend", "special_dividend"}:
            per_share_outcome = "Capital returned to shareholders can support per-share economics if the cash was not needed elsewhere."
        else:
            per_share_outcome = "Retained cash can protect flexibility, but its per-share effect depends on later deployment discipline."
        balance_sheet_outcome = _first_nonempty(
            "; ".join(summary_lines[:2]),
            "The balance-sheet effect is visible, but the opportunity cost of the chosen path still matters.",
        )
    else:
        operating_outcome = "No direct operating outcome is yet observable."
        financial_outcome = "UNABLE_TO_ATTRIBUTE: Insufficient allocation-specific evidence to attribute a financial outcome."
        per_share_outcome = "The per-share implication is still unclear."
        balance_sheet_outcome = "The balance-sheet implication is still being worked through."

    return operating_outcome, financial_outcome, per_share_outcome, balance_sheet_outcome


_INVESTMENT_CATEGORIES = frozenset({
    "acquisition", "acquisition_integration", "strategic_investment",
    "joint_venture", "subsidiary_investment",
})
_DEPLOYMENT_CATEGORIES = frozenset({
    "organic_capex", "capacity_expansion", "maintenance_capex",
    "product_development", "research_and_development", "technology_investment",
})
_DISTRIBUTION_CATEGORIES = frozenset({
    "dividend", "special_dividend", "share_buyback",
})


def _causal_attribution_states(record: Dict[str, Any], evidence: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """Compute canonical semantic state fields for each causal layer.

    These layers are strictly ordered and non-interchangeable:
    deployment → execution → operating outcome → financial outcome → per-share.
    Revenue growth after an acquisition is NOT a financial outcome of the acquisition.
    """
    category = str(record.get("allocation_category") or "unknown")
    current_status = str(record.get("current_status") or "")
    outcome_status = str(record.get("outcome_status") or "")
    has_project_evidence = any(e.get("kind") in {"project", "capacity"} for e in evidence)

    note_text = " ".join(e.get("note", "") for e in evidence if e.get("kind") in {"project", "capacity"}).lower()

    # --- Deployment state ---
    if current_status == "cancelled" or current_status == "abandoned":
        deployment_state = "CANCELLED"
    elif current_status in {"deployed", "partially_deployed", "in_progress"}:
        if category in _INVESTMENT_CATEGORIES:
            deployment_state = "COMPLETED_TRANSACTION"
        else:
            deployment_state = "DEPLOYED"
    elif current_status == "announced":
        deployment_state = "ANNOUNCED"
    elif current_status == "delayed":
        deployment_state = "COMMITTED"
    elif category in _DISTRIBUTION_CATEGORIES or category == "debt_repayment":
        deployment_state = "COMPLETED_TRANSACTION"
    elif record.get("amount_crore"):
        deployment_state = "DEPLOYED"
    else:
        deployment_state = "UNABLE_TO_VERIFY"

    # --- Execution state ---
    if category in _DISTRIBUTION_CATEGORIES or category == "debt_repayment":
        execution_state = "COMPLETED"
    elif has_project_evidence and any(t in note_text for t in ("operational", "commissioned", "integrated")):
        execution_state = "OPERATIONAL"
    elif has_project_evidence and any(t in note_text for t in ("in progress", "ongoing", "underway")):
        execution_state = "IN_PROGRESS"
    elif has_project_evidence:
        execution_state = "IN_PROGRESS"
    else:
        execution_state = "UNABLE_TO_VERIFY"
    # Layer ordering: execution cannot exceed deployment
    if deployment_state == "UNABLE_TO_VERIFY" and execution_state not in {"UNABLE_TO_VERIFY", "NOT_STARTED"}:
        execution_state = "UNABLE_TO_VERIFY"

    # --- Operating outcome state ---
    if category in _DISTRIBUTION_CATEGORIES or category == "debt_repayment":
        operating_outcome_state = "NO_VERIFIED_OUTCOME"
    elif execution_state == "OPERATIONAL" and category in _DEPLOYMENT_CATEGORIES:
        operating_outcome_state = "CAPACITY_ADDED"
    elif execution_state == "OPERATIONAL" and category in {"acquisition", "acquisition_integration"}:
        operating_outcome_state = "ACQUIRED_BUSINESS_INTEGRATED"
    elif has_project_evidence:
        operating_outcome_state = "UTILIZATION_VISIBLE"
    else:
        operating_outcome_state = "UNABLE_TO_VERIFY"

    # --- Financial outcome state (strict: only cash transactions have attributable financial outcomes) ---
    if category in {"dividend", "special_dividend", "share_buyback", "debt_repayment"}:
        financial_outcome_state = "CASH_FLOW_EFFECT"
    else:
        # Revenue/profit growth after an acquisition or capex program is NOT attributable
        # to that specific allocation without a direct causal link in the evidence
        financial_outcome_state = "UNABLE_TO_ATTRIBUTE"

    # --- Per-share consequence state ---
    if category == "share_buyback":
        per_share_consequence_state = "SHARE_COUNT_REDUCTION"
    elif category in {"dividend", "special_dividend"}:
        per_share_consequence_state = "OWNER_EARNINGS_EFFECT"
    else:
        per_share_consequence_state = "UNABLE_TO_ATTRIBUTE"

    # --- Value creation classification ---
    if category in _DEPLOYMENT_CATEGORIES and operating_outcome_state in {"CAPACITY_ADDED", "UTILIZATION_VISIBLE"}:
        value_creation_classification = "TOO_EARLY_TO_JUDGE"
    elif outcome_status == "negative_outcome":
        value_creation_classification = "VALUE_DESTRUCTION_EVIDENCE"
    elif not evidence and category not in _DISTRIBUTION_CATEGORIES and category != "debt_repayment":
        value_creation_classification = "UNABLE_TO_VERIFY"
    else:
        value_creation_classification = "UNABLE_TO_VERIFY"

    # --- Causal attribution confidence ---
    if category in _DISTRIBUTION_CATEGORIES:
        causal_attribution_confidence = "MEDIUM"
    elif category == "debt_repayment":
        causal_attribution_confidence = "LOW"
    elif execution_state in {"OPERATIONAL", "COMPLETED"} and has_project_evidence:
        causal_attribution_confidence = "MEDIUM"
    elif has_project_evidence:
        causal_attribution_confidence = "LOW"
    else:
        causal_attribution_confidence = "UNKNOWN"

    return {
        "deployment_state": deployment_state,
        "execution_state": execution_state,
        "operating_outcome_state": operating_outcome_state,
        "financial_outcome_state": financial_outcome_state,
        "per_share_consequence_state": per_share_consequence_state,
        "value_creation_classification": value_creation_classification,
        "causal_attribution_confidence": causal_attribution_confidence,
    }


def _validate_semantic_states(record: Dict[str, Any]) -> List[str]:
    """Contract validator — returns list of violations; empty = valid."""
    violations: List[str] = []
    fos = record.get("financial_outcome_state", "")
    eos = record.get("execution_state", "")
    dos = record.get("deployment_state", "")
    cat = str(record.get("allocation_category") or "")
    vcc = record.get("value_creation_classification", "")
    pss = record.get("per_share_consequence_state", "")
    cac = record.get("causal_attribution_confidence", "")
    evidence = record.get("return_evidence") or []
    has_specific = any(e.get("kind") in {"project", "capacity"} for e in evidence)

    if fos not in {"UNABLE_TO_ATTRIBUTE", "CASH_FLOW_EFFECT"} and not has_specific:
        violations.append(f"financial_outcome_state={fos!r} without specific project/capacity evidence")
    if vcc == "VALUE_CREATION_EVIDENCE" and eos not in {"OPERATIONAL", "INTEGRATED", "COMPLETED"}:
        violations.append("VALUE_CREATION_EVIDENCE requires operational execution evidence")
    if pss == "SHARE_COUNT_REDUCTION" and cat != "share_buyback":
        violations.append(f"SHARE_COUNT_REDUCTION is only valid for share_buyback; got {cat!r}")
    if cac == "HIGH" and not has_specific:
        violations.append("causal_attribution_confidence=HIGH requires direct project/capacity evidence")
    if dos == "UNABLE_TO_VERIFY" and eos not in {"UNABLE_TO_VERIFY", "NOT_STARTED"}:
        violations.append(f"execution_state={eos!r} cannot exceed deployment_state=UNABLE_TO_VERIFY")
    if cat in {"acquisition", "acquisition_integration"} and fos == "REVENUE_CONTRIBUTION":
        violations.append("REVENUE_CONTRIBUTION for acquisition requires explicit attribution evidence; chronological overlap is insufficient")
    if eos == "ACQUIRED_BUSINESS_INTEGRATED" and not has_specific:
        violations.append("ACQUIRED_BUSINESS_INTEGRATED requires project/capacity evidence of integration")
    return violations


def _outcome_status(record: Dict[str, Any], evidence: Sequence[Dict[str, Any]]) -> str:
    combined_text = " ".join(item.get("note") or "" for item in evidence if item.get("note"))
    text = _normalize_text(combined_text)
    direct_evidence = [
        item
        for item in evidence
        if item.get("kind") in {"project", "capacity", "risk"}
    ]
    positive = sum(
        1
        for term in (
            "improved",
            "growth",
            "commissioned",
            "operational",
            "delivered",
            "deployed",
            "visible",
            "strengthened",
            "lower debt",
            "reduced leverage",
            "better",
            "efficient",
            "early evidence",
        )
        if term in text
    )
    negative = sum(
        1
        for term in (
            "delayed",
            "underutilized",
            "underutilised",
            "abandoned",
            "superseded",
            "slipped",
            "weaker",
            "decline",
            "negative",
            "not yet",
            "unclear",
            "pressure",
            "mixed",
        )
        if term in text
    )
    if not direct_evidence and text:
        return "not_yet_observable"
    if not direct_evidence and not text:
        return "unable_to_verify"
    if record.get("current_status") in {"abandoned", "superseded", "delayed"} and negative >= positive:
        return "negative_outcome"
    if positive and not negative:
        return "early_evidence" if len(direct_evidence) == 1 else "partially_observed" if len(direct_evidence) >= 2 else "not_yet_observable"
    if positive and negative:
        return "partially_observed"
    if negative and not positive:
        return "negative_outcome"
    if len(direct_evidence) >= 2:
        return "partially_observed"
    if len(direct_evidence) == 1:
        return "not_yet_observable"
    return "unable_to_verify"


def _current_status_from_candidate(candidate: Dict[str, Any]) -> str:
    text = _normalize_text(
        " ".join(
            str(part or "")
            for part in (
                candidate.get("stated_rationale"),
                candidate.get("inferred_business_purpose"),
                candidate.get("ledger_event_type"),
                candidate.get("ledger_investor_interpretation"),
                candidate.get("event_summary"),
            )
        )
    )
    ledger_event = _normalize_text(candidate.get("ledger_event_type"))
    if any(term in text for term in ("abandoned", "cancelled", "canceled", "dropped")):
        return "abandoned"
    if any(term in text for term in ("superseded", "replaced", "shifted", "reframed")):
        return "superseded"
    if any(term in text for term in ("delayed", "slipped", "postponed", "deferred", "pending deployment")):
        return "delayed"
    if ledger_event in {"shareholder_return", "operating_reinvestment", "deleveraging", "capital_raised"}:
        return "deployed"
    if any(term in text for term in ("commissioned", "operational", "executed", "deployed", "completed", "paid", "repaid", "issued")):
        return "deployed"
    if any(term in text for term in ("progress", "ongoing", "in progress", "underway", "partial", "partially")):
        return "partially_deployed"
    if any(term in text for term in ("planned", "expected", "expect", "announced", "intend", "target", "will")):
        return "announced"
    if candidate.get("deployment_periods") and len(candidate.get("deployment_periods") or []) > 1:
        return "in_progress"
    return "unable_to_verify"


def _supporting_questions(record: Dict[str, Any], outcome_status: str) -> List[str]:
    category = str(record.get("allocation_category") or "unknown")
    questions: List[str] = []
    if outcome_status in {"not_yet_observable", "unable_to_verify"}:
        if category in {"capacity_expansion", "organic_capex", "maintenance_capex", "product_development", "research_and_development", "technology_investment", "acquisition", "acquisition_integration", "strategic_investment", "joint_venture", "subsidiary_investment"}:
            questions.append("What later revenue, margin, utilization, or cash-flow outcome can be linked to this deployment?")
        elif category in {"working_capital"}:
            questions.append("Did cash conversion improve after the working-capital deployment?")
        elif category in {"dividend", "special_dividend", "share_buyback", "equity_issuance", "retained_cash"}:
            questions.append("Was the capital return or balance-sheet move efficient versus alternative uses of cash?")
        else:
            questions.append("What later evidence shows whether this allocation created durable value?")
    return questions


def _progression_summary(record: Dict[str, Any], timeline: Dict[str, Any], outcome_status: str) -> str:
    periods = list(record.get("deployment_periods") or [])
    if not periods:
        return "No deployment periods were recovered."
    first = periods[0]
    latest = periods[-1]
    current_state = str(timeline.get("current_state") or record.get("current_status") or "unable_to_verify")
    return (
        f"{first}: {record.get('allocation_name')} first observed; "
        f"{latest}: latest state is {current_state}; outcome is {outcome_status}."
    )


def _build_allocation_group(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "allocation_category": candidate["allocation_category"],
        "allocation_name": candidate["allocation_name"],
        "normalized_name": candidate["normalized_name"],
        "family_key": candidate["family_key"],
        "funding_source": candidate["funding_source"],
        "deployment_periods": [candidate["source_year"]],
        "source_years": [candidate["source_year"]],
        "source_references": [candidate["source_reference"]],
        "source_items": [candidate],
        "candidate_count": 1,
        "signature_tokens": set(_token_set(candidate["allocation_name"])),
    }


def _group_similarity(group: Dict[str, Any], candidate: Dict[str, Any]) -> int:
    score = 0
    if group["allocation_category"] == candidate["allocation_category"]:
        score += 4
    if group["family_key"] == candidate["family_key"]:
        score += 4
    if group["funding_source"] == candidate["funding_source"]:
        score += 1
    tokens = _token_set(candidate["allocation_name"]) - _MERGE_NOISE
    overlap = len((group["signature_tokens"] - _MERGE_NOISE) & tokens)
    if overlap >= 3:
        score += 3
    elif overlap >= 2:
        score += 2
    elif overlap >= 1:
        score += 1
    if candidate["allocation_name"] and candidate["allocation_name"].lower() in " ".join(group["signature_tokens"]):
        score += 1
    return score


def _merge_group(group: Dict[str, Any], candidate: Dict[str, Any]) -> None:
    if candidate["source_year"] not in group["source_years"]:
        group["source_years"].append(candidate["source_year"])
    if candidate["source_year"] not in group["deployment_periods"]:
        group["deployment_periods"].append(candidate["source_year"])
    if candidate["source_reference"] not in group["source_references"]:
        group["source_references"].append(candidate["source_reference"])
    group["source_items"].append(candidate)
    group["candidate_count"] += 1
    group["signature_tokens"] |= _token_set(candidate["allocation_name"])
    if _name_specificity_score(candidate["allocation_name"]) > _name_specificity_score(group["allocation_name"]):
        group["allocation_name"] = candidate["allocation_name"]
        group["normalized_name"] = candidate["normalized_name"]
        group["family_key"] = candidate["family_key"]
    if candidate["funding_source"] != group["funding_source"]:
        if "unknown" in {candidate["funding_source"], group["funding_source"]}:
            group["funding_source"] = candidate["funding_source"] if group["funding_source"] == "unknown" else group["funding_source"]
        else:
            group["funding_source"] = "mixed"


# Acquisitions and similar named-entity events require stronger overlap to merge so
# that distinct acquisition targets (e.g. Proactiv vs Concert Pharmaceuticals) are
# not collapsed into a single record.
_HIGH_SPECIFICITY_CATEGORIES = {"acquisition", "acquisition_integration", "strategic_investment", "joint_venture", "subsidiary_investment"}
_HIGH_SPECIFICITY_MERGE_THRESHOLD = 6
_DEFAULT_MERGE_THRESHOLD = 5

# Generic terms that appear in virtually every acquisition name and should be
# excluded from the overlap computation so they don't create false similarity.
_MERGE_NOISE = frozenset({
    "acquisition", "incorporation", "incorporated", "date", "inc", "ltd",
    "corp", "llc", "formerly", "known", "investment", "pharma",
    "pharmaceuticals", "pharmaceutical", "securities", "security",
    "limited", "sun",
})


def _merge_candidates(candidates: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    groups: List[Dict[str, Any]] = []
    merged = 0
    for candidate in sorted(candidates, key=lambda item: (_year_sort_key(item["source_year"]), item["allocation_category"], item["normalized_name"], item["source_item_id"] or "")):
        best_group = None
        best_score = 0
        for group in groups:
            score = _group_similarity(group, candidate)
            if score > best_score:
                best_score = score
                best_group = group
        threshold = (
            _HIGH_SPECIFICITY_MERGE_THRESHOLD
            if candidate["allocation_category"] in _HIGH_SPECIFICITY_CATEGORIES
            else _DEFAULT_MERGE_THRESHOLD
        )
        if best_group is not None and best_score >= threshold:
            _merge_group(best_group, candidate)
            merged += 1
            continue
        groups.append(_build_allocation_group(candidate))
    return groups, merged


def _candidate_from_item(
    year: str,
    item: Dict[str, Any],
    group_name: str,
    ledger_entry: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    allocation_category = _map_allocation_category(item, ledger_entry)
    if group_name in IGNORED_SOURCE_GROUPS and allocation_category in {"unknown", "other"}:
        return None
    if group_name not in RELEVANT_SOURCE_GROUPS and allocation_category in {"unknown", "other"}:
        return None

    allocation_name = _allocation_name_from_item(item, ledger_entry, allocation_category)
    normalized_name = _normalize_text(allocation_name)
    family_key = _family_key(allocation_category, allocation_name)
    funding_source = _infer_funding_source(allocation_category, item, ledger_entry)
    amount = _candidate_amount(item, ledger_entry)
    amount_basis = _amount_basis(item, ledger_entry, amount)
    source_reference = _compact_source_item(year, item, group_name)
    if ledger_entry:
        source_reference.setdefault("linked_ledger_reference", _compact_ledger_reference(year, ledger_entry))

    current_status = _current_status_from_candidate(
        {
            "stated_rationale": _first_nonempty(item.get("reasoning"), item.get("status"), ledger_entry.get("investor_interpretation")),
            "inferred_business_purpose": _inferred_business_purpose(allocation_category, item, ledger_entry),
            "ledger_event_type": ledger_entry.get("capital_allocation_event_type"),
            "ledger_investor_interpretation": ledger_entry.get("investor_interpretation"),
            "deployment_periods": [year],
        }
    )

    evidence_status = _evidence_status(item, ledger_entry, len(source_reference.get("evidence_ids") or []))
    if ledger_entry.get("reliability") == "unreliable":
        evidence_status = "partial"

    candidate = {
        "source_year": year,
        "source_item_id": item.get("source_item_id"),
        "source_artifact": item.get("source_artifact") or "capital_allocation_timeline.json",
        "source_page": item.get("source_page"),
        "source_reference": source_reference,
        "allocation_category": allocation_category,
        "allocation_name": allocation_name,
        "normalized_name": normalized_name,
        "family_key": family_key,
        "funding_source": funding_source if funding_source in ALLOCATION_FUNDING_SOURCES else "unknown",
        "amount": amount,
        "amount_basis": amount_basis,
        "stated_rationale": _first_nonempty(item.get("reasoning"), ledger_entry.get("purpose"), ledger_entry.get("investor_interpretation"), item.get("status")),
        "inferred_business_purpose": _inferred_business_purpose(allocation_category, item, ledger_entry),
        "current_status": current_status,
        "outcome_status": "not_yet_observable",
        "return_evidence": [],
        "what_changed": "",
        "why_it_changed": "",
        "conviction_impact": "unchanged",
        "investor_implication": _first_nonempty(ledger_entry.get("investor_interpretation"), "The allocation is visible, but later payoff remains to be proven."),
        "evidence_status": evidence_status,
        "source_references": [source_reference],
        "deployment_periods": [year],
        "linked_project_ids": [],
        "linked_capacity_ids": [],
        "linked_commitment_ids": [],
        "linked_risk_ids": [],
        "linked_acquisition_ids_if_available": [],
        "ledger_event_type": ledger_entry.get("capital_allocation_event_type"),
        "ledger_investor_interpretation": ledger_entry.get("investor_interpretation"),
        "ledger_follow_up_questions": list(ledger_entry.get("follow_up_questions") or []),
        "ledger_amount": ledger_entry.get("amount"),
        "ledger_purpose": ledger_entry.get("purpose"),
        "ledger_reliability": ledger_entry.get("reliability"),
        "ledger_roi_measurability_status": ledger_entry.get("roi_measurability_status"),
    }
    return candidate


def _load_pcim_allocation_items(company_root: Path) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Read capital_allocation_inputs from the PCIM as a supplementary evidence source.

    Returns (year, group_name, item) tuples for each PCIM capital allocation item.
    Skips groups that represent non-deployment events and items the financial-timeline
    already covers via typed fields (dividend_paid, capex).
    """
    pcim_path = company_root / "company_memory" / "pcim_v1.json"
    if not pcim_path.exists():
        return []
    try:
        pcim = json.loads(pcim_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    ca_inputs = pcim.get("capital_allocation_inputs") if isinstance(pcim, dict) else None
    if not isinstance(ca_inputs, dict):
        return []

    # Groups we skip entirely — they either duplicate financial-timeline data or
    # are non-deployment administrative events.
    skip_groups = {
        "corporate_actions_non_cash_or_admin",
        "ownership_transfer_non_company_cashflow",
        "accounting_or_disclosure_only",
        "uncertain",
    }
    # Canonical categories that represent capital SOURCES, not deployments.
    skip_canonicals = {"debt_raised"}

    # Text-based patterns for items that are definitively NOT capital deployment
    # regardless of their PCIM canonical classification.
    _NON_DEPLOYMENT_PATTERNS = (
        "proceeds from",   # capital sources (proceeds of borrowings)
        "proceeds of",
        "debt raised",     # capital source, not deployment
        "interest payment",
        "payment of interest",
        "finance costs",   # financing costs, not capital deployment
        "change in authorised capital",  # corporate admin action
        "change in authorized capital",
    )

    results: List[Tuple[str, str, Dict[str, Any]]] = []
    for year_entry in ca_inputs.get("capital_allocation_by_year") or []:
        if not isinstance(year_entry, dict):
            continue
        year = str(year_entry.get("year") or "").strip().lower()
        if not year:
            continue
        for item in year_entry.get("items") or []:
            if not isinstance(item, dict):
                continue
            group_name = str(item.get("capital_allocation_group") or "uncertain")
            if group_name in skip_groups:
                continue
            # Use raw (un-normalized) canonical so underscores match the skip set.
            if (item.get("canonical_category") or "") in skip_canonicals:
                continue
            item_text = _normalize_text(item.get("value") or "")
            if any(pat in item_text for pat in _NON_DEPLOYMENT_PATTERNS):
                continue
            # Give each item a stable source_item_id if not already set
            if not item.get("source_item_id"):
                item = {**item, "source_item_id": f"pcim_{year}_{_slug(item.get('value', ''))[:40]}"}
            results.append((year, group_name, item))
    return results


def _build_candidates(company_root: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    artifacts = _load_financial_artifacts(company_root)
    capital_timeline = artifacts.get("capital_allocation_financial_timeline") or {}
    ledger = artifacts.get("capital_allocation_roi_ledger") or {}
    ledger_map = {str(entry.get("fiscal_year") or "").strip().lower(): entry for entry in ledger.get("entries", []) if isinstance(entry, dict)}

    candidates: List[Dict[str, Any]] = []
    timeline = capital_timeline.get("timeline") if isinstance(capital_timeline, dict) else []
    for year_entry in timeline if isinstance(timeline, list) else []:
        if not isinstance(year_entry, dict):
            continue
        year = str(year_entry.get("year") or "").strip().lower()
        if not year:
            continue
        ledger_entry = ledger_map.get(year, {})
        for group_name in (
            "true_capital_deployment",
            "shareholder_returns",
            "financing_actions",
            "treasury_actions",
            "related_party_capital_flows",
            "corporate_actions_non_cash_or_admin",
            "ownership_transfer_non_company_cashflow",
            "accounting_or_disclosure_only",
            "uncertain",
        ):
            items = year_entry.get(group_name) or []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                candidate = _candidate_from_item(year, item, group_name, ledger_entry)
                if candidate is None:
                    continue
                candidates.append(candidate)

        # Current financial-memory schema exposes typed fields rather than the
        # legacy grouped buckets above. Adapt both contracts deterministically.
        for dividend in year_entry.get("dividend_actions") or []:
            if isinstance(dividend, dict):
                item = {
                    **dividend,
                    "source_item_id": dividend.get("source_item_id") or f"dividend_{year}",
                    "canonical_category": "dividend_paid",
                    "value": dividend.get("value") or "Dividend paid to shareholders",
                    "reasoning": "Dividend paid to shareholders",
                }
                candidate = _candidate_from_item(year, item, "shareholder_returns", ledger_entry)
                if candidate is not None:
                    candidates.append(candidate)
        for action in year_entry.get("share_issue_actions") or []:
            if isinstance(action, dict):
                line_item = _normalize_text(action.get("source_line_item"))
                if any(term in line_item for term in ("expense", "payable", "unutilised", "unutilized", "monitoring agency")):
                    continue
                if not (action.get("amount_raised_crore") is not None or action.get("shares_issued") is not None):
                    continue
                item = {
                    **action,
                    "source_item_id": action.get("source_item_id") or f"share_issue_{year}",
                    "canonical_category": "equity_issuance",
                    "value": action.get("value") or "Equity issuance",
                    "suppress_ledger_amount": True,
                }
                candidate = _candidate_from_item(year, item, "financing_actions", ledger_entry)
                if candidate is not None:
                    candidates.append(candidate)
        capex = year_entry.get("capex") or {}
        if isinstance(capex, dict) and capex.get("value") is not None:
            item = {
                "source_item_id": f"capex_{year}", "source_artifact": capex.get("source_artifact"),
                "amount": capex.get("value"), "value": "Capital expenditure", "canonical_category": "capex",
                "reasoning": "Capital expenditure deployed",
            }
            candidate = _candidate_from_item(year, item, "true_capital_deployment", ledger_entry)
            if candidate is not None:
                candidates.append(candidate)

    # The investor ROI ledger is canonical allocation evidence even when the
    # financial timeline cannot express the action in its legacy buckets.
    existing_year_types = {(item.get("source_year"), item.get("ledger_event_type")) for item in candidates}
    for ledger_entry in ledger.get("entries", []) if isinstance(ledger, dict) else []:
        if not isinstance(ledger_entry, dict):
            continue
        year = str(ledger_entry.get("fiscal_year") or "").strip().lower()
        event_type = str(ledger_entry.get("capital_allocation_event_type") or "").strip()
        if not year or (year, event_type) in existing_year_types:
            continue
        amount = ledger_entry.get("amount")
        material_fields = (
            "capital_raised", "capex_deployed", "working_capital_deployed",
            "product_development_or_intangible_investment", "debt_repayment",
            "dividends", "buybacks", "acquisitions",
        )
        if amount is None and not any(ledger_entry.get(field) is not None for field in material_fields):
            continue
        group = "shareholder_returns" if event_type == "shareholder_return" else "financing_actions" if event_type in {"capital_raise", "debt_repayment"} else "true_capital_deployment"
        item = {
            "source_item_id": f"roi_ledger_{year}_{event_type or 'allocation'}",
            "source_artifact": "capital_allocation_roi_ledger.json",
            "amount": amount,
            "value": ledger_entry.get("purpose") or event_type or "Capital allocation",
            "reasoning": ledger_entry.get("purpose") or ledger_entry.get("investor_interpretation"),
        }
        candidate = _candidate_from_item(year, item, group, ledger_entry)
        if candidate is not None:
            candidates.append(candidate)

    # PCIM capital_allocation_inputs provides richer categorical evidence (acquisitions,
    # buybacks, debt repayment, R&D) that the financial-memory timeline does not yet
    # carry.  The existing _merge_candidates() deduplication handles overlap with the
    # financial-timeline items (dividends, capex) via similarity scoring.
    for year, group_name, item in _load_pcim_allocation_items(company_root):
        ledger_entry = ledger_map.get(year, {})
        candidate = _candidate_from_item(year, item, group_name, ledger_entry)
        if candidate is not None:
            candidates.append(candidate)

    return candidates, artifacts


def _finalize_allocation_record(
    company: str,
    allocation_id: str,
    group: Dict[str, Any],
    linked: Dict[str, List[Dict[str, Any]]],
    artifacts: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    candidates = sorted(group["source_items"], key=lambda item: (_year_sort_key(item["source_year"]), item["source_item_id"] or "", item["allocation_name"]))
    deployment_periods = _years_covered(item["source_year"] for item in candidates)
    first_observed_period = deployment_periods[0] if deployment_periods else ""
    latest_period = deployment_periods[-1] if deployment_periods else ""
    latest_candidate = candidates[-1]
    amount = next((candidate["amount"] for candidate in reversed(candidates) if candidate.get("amount") is not None), None)
    amount_basis = next((candidate["amount_basis"] for candidate in reversed(candidates) if candidate.get("amount") is not None), "unknown")
    current_status = _current_status_from_candidate(latest_candidate)

    project_lookup = linked["projects"]
    capacity_lookup = linked["capacity"]
    commitment_lookup = linked["commitments"]
    risk_lookup = linked["risks"]

    record = {
        "allocation_id": allocation_id,
        "allocation_category": group["allocation_category"],
        "allocation_name": group["allocation_name"],
        "normalized_name": group["normalized_name"],
        "first_observed_period": first_observed_period,
        "deployment_periods": deployment_periods,
        "amount": amount,
        "amount_basis": amount_basis,
        "funding_source": group["funding_source"] if group["funding_source"] in ALLOCATION_FUNDING_SOURCES else "unknown",
        "linked_project_ids": [],
        "linked_capacity_ids": [],
        "linked_commitment_ids": [],
        "linked_risk_ids": [],
        "linked_acquisition_ids_if_available": [],
        "stated_rationale": _first_nonempty(latest_candidate.get("stated_rationale"), latest_candidate.get("ledger_investor_interpretation"), latest_candidate.get("ledger_purpose"), group["allocation_name"]),
        "inferred_business_purpose": _inferred_business_purpose(group["allocation_category"], latest_candidate, latest_candidate),
        "deployment_status": current_status,
        "current_status": current_status,
        "outcome_status": "not_yet_observable",
        "causal_confidence": "low",
        "progression_summary": "",
        "operating_outcome": "",
        "financial_outcome": "",
        "per_share_outcome": "",
        "operating_evidence": "",
        "financial_evidence": "",
        "per_share_evidence": "",
        "balance_sheet_outcome": "",
        "return_evidence": [],
        "opportunity_cost_notes": "",
        "what_changed": "",
        "why_it_changed": "",
        "conviction_impact": "unchanged",
        "investor_implication": _first_nonempty(latest_candidate.get("investor_implication"), "The allocation is visible, but later payoff remains to be proven."),
        "confidence": build_confidence(
            "medium" if len(candidates) == 1 else "high",
            basis=[
                "capital allocation financial timeline",
                "capital allocation roi ledger",
                "company memory evidence",
            ],
            limitations=[
                "Later payoff remains conservative unless a later source explicitly confirms it.",
            ]
            if len(candidates) == 1
            else [],
        ),
        "evidence_status": "supported" if len(candidates) > 1 else "partial",
        "source_references": [],
        "unresolved_questions": [],
    }

    record["linked_project_ids"] = _link_records(
        record,
        project_lookup,
        fields=("project_name", "normalized_name", "objective", "business_rationale", "project_type"),
        id_field="project_id",
        threshold=4,
    )
    record["linked_capacity_ids"] = _link_records(
        record,
        capacity_lookup,
        fields=("capacity_name", "normalized_name", "purpose", "economic_relevance", "capacity_type"),
        id_field="capacity_id",
        threshold=4,
    )
    record["linked_commitment_ids"] = _link_records(
        record,
        commitment_lookup,
        fields=("topic", "normalized_commitment", "delivery_assessment", "investor_implication", "category"),
        id_field="id",
        threshold=4,
    )
    record["linked_risk_ids"] = _link_records(
        record,
        risk_lookup,
        fields=("risk_name", "normalized_name", "progression_summary", "investor_implication", "risk_category", "risk_mechanism"),
        id_field="risk_id",
        threshold=3,
    )
    record["linked_acquisition_ids_if_available"] = _link_acquisition_records(record, project_lookup)

    for candidate in candidates:
        record["source_references"].extend(ref for ref in [candidate["source_reference"]] if ref not in record["source_references"])

    evidence = _evidence_from_links(record, project_lookup, capacity_lookup, commitment_lookup, risk_lookup)
    # NOTE: No generic financial fallback here — company-wide revenue/PAT trends are NOT
    # causal evidence for individual allocations. Unknown > fabricated causality.

    return_evidence = []
    for item in evidence:
        if item not in return_evidence:
            return_evidence.append(item)
    record["return_evidence"] = return_evidence[:5]
    record["outcome_status"] = _outcome_status(record, record["return_evidence"])
    if record["outcome_status"] in {"positive_evidence", "negative_evidence", "clearly_observed"}:
        record["causal_confidence"] = "medium"
    elif record["outcome_status"] in {"partially_observed", "early_evidence"}:
        record["causal_confidence"] = "low"
    elif not record["return_evidence"]:
        record["causal_confidence"] = "unknown"
    else:
        record["causal_confidence"] = "low"
    semantic_states = _causal_attribution_states(record, record["return_evidence"])
    record.update(semantic_states)
    record["semantic_state_violations"] = _validate_semantic_states(record)
    record["operating_outcome"], record["financial_outcome"], record["per_share_outcome"], record["balance_sheet_outcome"] = _financial_outcome_text(
        record,
        artifacts.get("financial_memory_summary", {}).get("summary") or {},
        artifacts.get("financial_driver_attribution") or {},
        record["return_evidence"],
    )
    record["operating_evidence"] = record["operating_outcome"]
    record["financial_evidence"] = record["financial_outcome"]
    record["per_share_evidence"] = record["per_share_outcome"]
    if record["outcome_status"] in {"negative_outcome"}:
        record["conviction_impact"] = "weakened"
    elif record["outcome_status"] in {"clearly_observed", "partially_observed", "early_evidence", "positive_evidence"}:
        record["conviction_impact"] = "strengthened"
    elif record["current_status"] in {"delayed", "abandoned", "superseded"}:
        record["conviction_impact"] = "weakened"

    timeline_events: List[Dict[str, Any]] = []
    for sequence, candidate in enumerate(candidates, start=1):
        event_candidate = dict(candidate)
        event_candidate["allocation_id"] = allocation_id
        event_candidate["current_status"] = record["current_status"] if sequence == len(candidates) else candidate["current_status"]
        event_candidate["outcome_status"] = record["outcome_status"] if sequence == len(candidates) else candidate["outcome_status"]
        event_candidate["event_type"] = None
        event_candidate["event_summary"] = _first_nonempty(candidate.get("stated_rationale"), candidate.get("inferred_business_purpose"), candidate.get("ledger_investor_interpretation"))
        timeline_events.append(build_capital_allocation_event(event_candidate, sequence))

    timeline = build_timeline(record, timeline_events, unresolved_questions=_supporting_questions(record, record["outcome_status"]))
    current_state = str(timeline.get("current_state") or record["current_status"] or "unable_to_verify")
    record["current_status"] = current_state if current_state in ALLOCATION_CURRENT_STATUSES else record["current_status"]
    record["progression_summary"] = _progression_summary(record, timeline, record["outcome_status"])
    record["what_changed"] = timeline.get("investor_implication", {}).get("what_changed") or record["progression_summary"]
    record["why_it_changed"] = timeline.get("investor_implication", {}).get("why_it_changed") or "The latest evidence update changed the view on execution or payoff."
    record["investor_implication"] = timeline.get("investor_implication", {}).get("what_changed") or record["investor_implication"]
    if timeline.get("investor_implication", {}).get("conviction_impact") == "weakened":
        record["conviction_impact"] = "weakened"
    elif timeline.get("investor_implication", {}).get("conviction_impact") == "strengthened" and record["conviction_impact"] != "weakened":
        record["conviction_impact"] = "strengthened"
    record["unresolved_questions"] = list(timeline.get("unresolved_questions") or _supporting_questions(record, record["outcome_status"]))
    assessment = {
        "allocation_id": allocation_id,
        "allocation_category": record["allocation_category"],
        "allocation_name": record["allocation_name"],
        "period": timeline.get("latest_period") or record.get("latest_period") or "",
        "latest_period": timeline.get("latest_period") or record.get("latest_period") or "",
        "current_status": record["current_status"],
        "deployment_status": record["deployment_status"],
        "outcome_status": record["outcome_status"],
        "what_changed": record["what_changed"],
        "why_it_changed": record["why_it_changed"],
        "conviction_impact": record["conviction_impact"],
        "investor_implication": record["investor_implication"],
        "operating_outcome": record["operating_outcome"],
        "financial_outcome": record["financial_outcome"],
        "per_share_outcome": record["per_share_outcome"],
        "operating_evidence": record["operating_evidence"],
        "financial_evidence": record["financial_evidence"],
        "per_share_evidence": record["per_share_evidence"],
        "balance_sheet_outcome": record["balance_sheet_outcome"],
        "causal_confidence": record["causal_confidence"],
        "deployment_state": record.get("deployment_state", "UNABLE_TO_VERIFY"),
        "execution_state": record.get("execution_state", "UNABLE_TO_VERIFY"),
        "operating_outcome_state": record.get("operating_outcome_state", "UNABLE_TO_VERIFY"),
        "financial_outcome_state": record.get("financial_outcome_state", "UNABLE_TO_ATTRIBUTE"),
        "per_share_consequence_state": record.get("per_share_consequence_state", "UNABLE_TO_ATTRIBUTE"),
        "value_creation_classification": record.get("value_creation_classification", "UNABLE_TO_VERIFY"),
        "causal_attribution_confidence": record.get("causal_attribution_confidence", "UNKNOWN"),
        "semantic_state_violations": record.get("semantic_state_violations", []),
        "return_evidence": list(record["return_evidence"]),
        "unresolved_questions": list(record["unresolved_questions"]),
        "evidence_status": record["evidence_status"],
        "confidence": build_confidence(
            "high" if len(record["return_evidence"]) >= 2 else "medium",
            basis=[
                "capital allocation timeline",
                "capital allocation roi ledger",
                "linked company memory evidence",
            ],
            limitations=[
                "Outcome remains conservative where linked evidence is fragmentary.",
            ]
            if len(record["return_evidence"]) < 2
            else [],
        ),
    }
    return record, timeline, assessment


class CapitalAllocationOutcomesBuilder:
    def __init__(self, company: str):
        self.company = company
        self.company_root = _company_root(company)
        self.output_dir = get_capital_allocation_outcomes_dir(company)

    def build(self) -> Dict[str, Path]:
        payloads = build_capital_allocation_outcomes(company=self.company, company_root=self.company_root)
        outputs = {
            "capital_allocation_outcomes.json": payloads["capital_allocation_outcomes.json"],
            "capital_allocation_timelines.json": payloads["capital_allocation_timelines.json"],
            "capital_allocation_assessments.json": payloads["capital_allocation_assessments.json"],
            "capital_allocation_validation.json": payloads["capital_allocation_validation.json"],
            "capital_allocation_manifest.json": payloads["capital_allocation_manifest.json"],
        }
        written: Dict[str, Path] = {}
        for filename, payload in payloads.items():
            written[filename] = write_json_file(self.output_dir / filename, payload)
        return written


def build_capital_allocation_outcomes(*, company: str, company_root: Path) -> Dict[str, Dict[str, Any]]:
    artifacts = _load_financial_artifacts(company_root)
    related = _load_related_records(company_root)
    candidates, source_artifacts = _build_candidates(company_root)
    grouped_candidates, merged_candidates = _merge_candidates(candidates)

    records: List[Dict[str, Any]] = []
    timelines: List[Dict[str, Any]] = []
    assessments: List[Dict[str, Any]] = []

    for index, group in enumerate(sorted(grouped_candidates, key=lambda item: (_year_sort_key(item["deployment_periods"][0] if item["deployment_periods"] else ""), item["allocation_category"], item["normalized_name"])), start=1):
        allocation_id = f"CAO-{index:04d}"
        record, timeline, assessment = _finalize_allocation_record(company, allocation_id, group, related, artifacts)
        records.append(record)
        timelines.append(timeline)
        assessments.append(assessment)

    outcomes_payload = {
        "schema_version": ALLOCATION_OUTCOMES_SCHEMA_VERSION,
        "generator_version": ALLOCATION_OUTCOMES_GENERATOR_VERSION,
        "company": company,
        "generated_at": _utc_now(),
        "years_covered": _years_covered(item["source_year"] for item in candidates),
        "allocation_count": len(records),
        "allocations": records,
        "warnings": [],
        "limitations": [
            "This module is deterministic and does not call an LLM.",
            "Later payoff is only counted when later company-memory evidence makes it explicit.",
        ],
    }

    latest_period = max(
        [str(timeline.get("latest_period") or "") for timeline in timelines if str(timeline.get("latest_period") or "").strip()],
        key=lambda value: parse_financial_year(value) if str(value).lower().startswith("fy") else -1,
        default="",
    )

    timelines_payload = {
        "schema_version": ALLOCATION_OUTCOMES_SCHEMA_VERSION,
        "generator_version": ALLOCATION_OUTCOMES_GENERATOR_VERSION,
        "company": company,
        "generated_at": _utc_now(),
        "latest_period": latest_period,
        "years_covered": _years_covered(item["source_year"] for item in candidates),
        "timeline_count": len(timelines),
        "timelines": timelines,
        "warnings": [],
        "limitations": outcomes_payload["limitations"],
    }

    assessments_payload = {
        "schema_version": ALLOCATION_OUTCOMES_SCHEMA_VERSION,
        "generator_version": ALLOCATION_OUTCOMES_GENERATOR_VERSION,
        "company": company,
        "generated_at": _utc_now(),
        "latest_period": max(
            [str(assessment.get("latest_period") or assessment.get("period") or "") for assessment in assessments if str(assessment.get("latest_period") or assessment.get("period") or "").strip()],
            key=lambda value: parse_financial_year(value) if str(value).lower().startswith("fy") else -1,
            default="",
        ),
        "years_covered": _years_covered(item["source_year"] for item in candidates),
        "assessment_count": len(assessments),
        "assessments": assessments,
        "warnings": [],
        "limitations": outcomes_payload["limitations"],
    }

    validation_payload = validate_capital_allocation_outcomes_payload(
        outcomes_payload,
        timelines_payload=timelines_payload,
        assessments_payload=assessments_payload,
        commitment_ids=[item.get("id") for item in related.get("commitments", []) if item.get("id")],
        project_ids=[item.get("project_id") for item in related.get("projects", []) if item.get("project_id")],
        capacity_ids=[item.get("capacity_id") for item in related.get("capacity", []) if item.get("capacity_id")],
        risk_ids=[item.get("risk_id") for item in related.get("risks", []) if item.get("risk_id")],
        upstream_material_evidence_count=len(candidates),
    )
    validation_payload.update(
        {
            "company": company,
            "generated_at": _utc_now(),
            "warnings": [],
            "limitations": outcomes_payload["limitations"],
        }
    )

    validation_status = validation_payload["status"]
    manifest_payload = build_capital_allocation_manifest(
        company_slug=company,
        generated_at=_utc_now(),
        upstream_sources_considered=[
            "company_memory/financials/capital_allocation_financial_timeline.json",
            "company_memory/financials/investor_financial_modules/capital_allocation_roi_ledger.json",
            "company_memory/financials/financial_memory_summary.json",
            "company_memory/financials/financial_driver_attribution.json",
            "company_memory/projects/projects_registry.json",
            "company_memory/capacity/capacity_registry.json",
            "company_memory/management_commitments/management_commitments.json",
            "company_memory/risks/risk_registry.json",
        ],
        upstream_sources_found=[
            str(path)
            for path in (
                company_root / "company_memory" / "financials" / "capital_allocation_financial_timeline.json",
                company_root / "company_memory" / "financials" / "investor_financial_modules" / "capital_allocation_roi_ledger.json",
                company_root / "company_memory" / "financials" / "financial_memory_summary.json",
                company_root / "company_memory" / "financials" / "financial_driver_attribution.json",
                company_root / "company_memory" / "projects" / "projects_registry.json",
                company_root / "company_memory" / "capacity" / "capacity_registry.json",
                company_root / "company_memory" / "management_commitments" / "management_commitments.json",
                company_root / "company_memory" / "risks" / "risk_registry.json",
            )
            if path.exists()
        ],
        upstream_sources_missing=[
            str(path)
            for path in (
                company_root / "company_memory" / "financials" / "capital_allocation_financial_timeline.json",
                company_root / "company_memory" / "financials" / "investor_financial_modules" / "capital_allocation_roi_ledger.json",
                company_root / "company_memory" / "financials" / "financial_memory_summary.json",
                company_root / "company_memory" / "financials" / "financial_driver_attribution.json",
                company_root / "company_memory" / "projects" / "projects_registry.json",
                company_root / "company_memory" / "capacity" / "capacity_registry.json",
                company_root / "company_memory" / "management_commitments" / "management_commitments.json",
                company_root / "company_memory" / "risks" / "risk_registry.json",
            )
            if not path.exists()
        ],
        allocation_candidates=len(candidates),
        allocations_written=len(records),
        duplicate_candidates_merged=merged_candidates,
        timelines_written=len(timelines),
        assessments_written=len(assessments),
        validation_status=validation_status,
        limitations=outcomes_payload["limitations"],
    )

    return {
        "capital_allocation_outcomes.json": outcomes_payload,
        "capital_allocation_timelines.json": timelines_payload,
        "capital_allocation_assessments.json": assessments_payload,
        "capital_allocation_validation.json": validation_payload,
        "capital_allocation_manifest.json": manifest_payload,
    }


def write_capital_allocation_outcomes(*, company: str, company_root: Path, output_dir: Path) -> Dict[str, Path]:
    payloads = build_capital_allocation_outcomes(company=company, company_root=company_root)
    written: Dict[str, Path] = {}
    for filename, payload in payloads.items():
        written[filename] = write_json_file(output_dir / filename, payload)
    return written
