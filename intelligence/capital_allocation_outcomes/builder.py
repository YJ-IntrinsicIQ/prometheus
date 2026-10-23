from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from knowledge.company_memory import parse_financial_year
from knowledge.company_memory.guardrails import evidenced_announcement_period, extract_dated_events, extract_issue_dates, extract_issue_economics

from knowledge.financials.authority_gate import load_vouched
from knowledge.capital_allocation_taxonomy import _NOT_AN_ALLOCATION_GROUPS, apply_label_verdict, event_nature, normalize_capital_allocation_item, resolve_economic_role, verify_stored_classification

from .contracts import (
    ALLOCATION_CATEGORIES,
    ALLOCATION_CURRENT_STATUSES,
    ALLOCATION_FUNDING_SOURCES,
    ALLOCATION_OUTCOME_STATUSES,
    ALLOCATION_OUTCOMES_GENERATOR_VERSION,
    ALLOCATION_OUTCOMES_MANIFEST_SCHEMA_VERSION,
    ALLOCATION_OUTCOMES_SCHEMA_VERSION,
    OUTCOME_ATTRIBUTION_LEVELS,
)
from .manifest import build_capital_allocation_manifest
from .longitudinal_profile import build_longitudinal_profile, write_longitudinal_profile
from .paths import (
    get_capital_allocation_assessments_path,
    get_capital_allocation_longitudinal_profile_path,
    get_capital_allocation_manifest_path,
    get_capital_allocation_outcomes_dir,
    get_capital_allocation_outcomes_path,
    get_capital_allocation_timelines_path,
    get_capital_allocation_validation_path,
)
from .progression import CapitalAllocationOutcomesProgressionAdapter, build_capital_allocation_event, build_timeline
from .validators import validate_capital_allocation_outcomes_payload
from .writer import write_json_file
from core.context_paths import logical_company_path, resolve_output_root, safe_destination
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


# ---------------------------------------------------------------------------
# Unit-aware amount parser (ENG-118 Phase 1)
# ---------------------------------------------------------------------------

_RE_UNIT_CRORE = re.compile(r"\b(?:crore|crores|cr)\b", re.IGNORECASE)
_RE_UNIT_LAKH = re.compile(r"\b(?:lakh|lakhs|lac|lacs)\b", re.IGNORECASE)
# million/billion only trusted when accompanied by explicit INR indicator in the string
_RE_UNIT_MILLION = re.compile(r"\b(?:million|millions|mn|mln)\b", re.IGNORECASE)
_RE_UNIT_BILLION = re.compile(r"\b(?:billion|billions|bn)\b", re.IGNORECASE)
# Explicit INR indicator required for million/billion trust
_RE_INR_INDICATOR = re.compile(r"(?:INR|₹|Rs\.?|rupee|rupees)", re.IGNORECASE)
# Non-INR currencies: unsupported for amount aggregation
_RE_FOREIGN_CCY = re.compile(r"\b(?:USD|EUR|GBP|JPY|CNY|AUD|CAD|SGD|CHF)\b", re.IGNORECASE)
# Per-share amounts cannot determine total capital deployment
_RE_PER_SHARE = re.compile(r"\bper\s+(?:equity\s+)?share\b", re.IGNORECASE)
_RE_NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
_RE_INVESTEE_STAKE = re.compile(r"minority\s+(?:stake|investment|interest)|equity\s+investment|stake\s+in\b|subscri", re.IGNORECASE)
_RE_OWN_ISSUANCE = re.compile(r"issu|allot|esop|esop|buy-?back|dividend|rights|preferential|qip", re.IGNORECASE)
_RE_SHARE_COUNT = re.compile(r"\b\d[\d,]*\s+(?:(?:equity|preference|ordinary)\s+)?shares?\b", re.IGNORECASE)


def _parse_amount_to_crore(value: Any) -> Optional[float]:
    """Parse an amount to INR crore with deterministic unit authority.

    Returns crore value only when unit is unambiguously attributable.
    Returns None for: no unit, conflicting units, per-share amounts,
    unsupported currencies, multiple semicolon-separated amounts,
    balance-outstanding compound strings, or million/billion without
    explicit INR currency indicator.
    """
    if value in (None, "", [], {}):
        return None
    if isinstance(value, (int, float)):
        # Numeric typed value — trust as crore (caller must verify schema contract)
        return abs(float(value)) if value != 0 else None

    s = str(value).strip()
    if not s:
        return None

    # Non-INR currency: no canonical FX conversion in current architecture
    if _RE_FOREIGN_CCY.search(s):
        return None

    # Explicitly labelled total cash distribution outranks a per-share figure.
    cash_total = re.search(r"(?:cash\s+outflow|total\s+(?:dividend|distribution)\s+(?:paid|amount)|amount\s+distributed)[^0-9₹]*(?:₹|INR|Rs\.?\s*)?([\d,]+(?:\.\d+)?)\s*(crore|crores|cr)\b", s, re.IGNORECASE)
    if cash_total:
        return float(cash_total.group(1).replace(",", ""))

    # Per-share amount without an explicitly labelled total cannot determine cash outflow.
    if _RE_PER_SHARE.search(s):
        return None

    # Semicolon-separated compound amounts are otherwise ambiguous.
    if ";" in s:
        return None

    # "balance outstanding" and similar stock-vs-flow compound strings
    s_lower = s.lower()
    if "outstanding" in s_lower or "balance outstanding" in s_lower:
        return None

    # Determine unit — require exactly one unit type
    has_crore = bool(_RE_UNIT_CRORE.search(s))
    has_lakh = bool(_RE_UNIT_LAKH.search(s))
    has_million = bool(_RE_UNIT_MILLION.search(s))
    has_billion = bool(_RE_UNIT_BILLION.search(s))

    # million/billion require explicit INR context — denomination is otherwise ambiguous
    # (could be USD millions, EUR millions, etc.)
    if (has_million or has_billion) and not _RE_INR_INDICATOR.search(s):
        return None

    unit_count = sum([has_crore, has_lakh, has_million, has_billion])
    if unit_count == 0:
        # Bare numeric string without explicit unit — UNIT_AMBIGUOUS
        return None
    if unit_count > 1:
        # Conflicting unit labels — UNIT_AMBIGUOUS
        return None

    # Locate the unit keyword and find the primary number immediately before it
    if has_crore:
        unit_match = _RE_UNIT_CRORE.search(s)
        multiplier = 1.0
    elif has_lakh:
        unit_match = _RE_UNIT_LAKH.search(s)
        multiplier = 0.01  # 1 lakh = 0.01 crore
    elif has_million:
        unit_match = _RE_UNIT_MILLION.search(s)
        multiplier = 0.1   # 1 INR million = 10 lakh = 0.1 crore
    else:
        unit_match = _RE_UNIT_BILLION.search(s)
        multiplier = 100.0  # 1 billion = 100 crore

    s_before_unit = s[: unit_match.start()]  # type: ignore[union-attr]
    nums_before = list(_RE_NUMBER.finditer(s_before_unit))
    if nums_before:
        primary_str = nums_before[-1].group()  # last number before unit keyword
    else:
        s_after_unit = s[unit_match.end():]  # type: ignore[union-attr]
        nums_after = list(_RE_NUMBER.finditer(s_after_unit))
        if not nums_after:
            return None
        primary_str = nums_after[0].group()

    try:
        primary = float(primary_str.replace(",", ""))
    except ValueError:
        return None

    return abs(primary) * multiplier if primary != 0 else None


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
    """Financial inputs are read only if they were built against the current registries (knowledge.financials.authority_gate): otherwise they are absent."""
    financial_root = company_root / "company_memory" / "financials"
    investor_dir = financial_root / "investor_financial_modules"
    return {
        "financial_memory_summary": load_vouched(financial_root / "financial_memory_summary.json"),
        "financial_driver_attribution": load_vouched(financial_root / "financial_driver_attribution.json"),
        "financial_truth_pack": load_vouched(financial_root / "financial_truth_pack.json"),
        "capital_allocation_financial_timeline": load_vouched(financial_root / "capital_allocation_financial_timeline.json"),
        "capital_allocation_roi_ledger": load_vouched(investor_dir / "capital_allocation_roi_ledger.json"),
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
    extraction_item_id: Any = None,
) -> Dict[str, Any]:
    reference = {
        "source_year": source_year,
        "source_artifact": source_artifact,
        "source_item_id": source_item_id,
        "source_page": source_page,
        "short_excerpt": _short_excerpt(short_excerpt),
        "evidence_ids": [str(item) for item in (evidence_ids or []) if str(item).strip()],
        "extraction_item_id": extraction_item_id,
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
    # sorted: _token_set is a set, so its iteration order (and with it the family key and which records merge) varied with PYTHONHASHSEED between runs
    tokens = sorted(token for token in _token_set(allocation_name) if token not in {"capital", "allocation", "event", "capitalallocation"})
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


def _has_word(text: str, phrase: str) -> bool:
    """Whole-word phrase match on normalised text: 'platform' must not be found in 'Tanla Platforms', nor 'r d' in 'order dated'."""
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


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
                # The year-level ledger entry (event type, purpose, interpretation) describes the whole year, not this item: using its words labelled an amalgamation as
                # R&D because the year's ledger text mentioned research. Classification reads the item's own fields only.
            )
            if part
        )
    )
    canonical = _normalize_text(item.get("canonical_category"))
    group = _normalize_text(item.get("capital_allocation_group"))

    # A typed minority/subscription investment is decided by its extracted category's event nature, not by a stored label from an older taxonomy (an equity
    # subscription once tagged 'r_and_d_investment') or by free-text words in its stated purpose ("platform", "research", ...). The company's own issuances are excluded.
    typed_category = str(item.get("category") or "")
    if (typed_category and group != "treasury_actions" and _RE_INVESTEE_STAKE.search(typed_category) and not _RE_OWN_ISSUANCE.search(typed_category)
            and event_nature(typed_category, "")["nature"] == "minority_or_subscription"):
        return "strategic_investment"
    # "Allocation of QIP proceeds to working capital" / "Use of IPO proceeds to repay borrowings": the record is the OBJECT the issue proceeds were used for (its category), not
    # another equity issuance. The object decides the category; a land or building purchase is operating-asset spending, not the acquisition of a business.
    use_action = _normalize_text(" ".join(str(item.get(k) or "") for k in ("action", "value", "category")))
    if _USE_OF_PROCEEDS.search(use_action):
        if re.search(r"\bunutili[sz]ed\b", use_action) and not re.search(r"\b(?:allocation|use|used)\b", use_action):
            return "retained_cash"                      # proceeds not yet spent are held, not deployed
        obj = _normalize_text(" ".join(str(item.get(k) or "") for k in ("category", "action", "value", "purpose")))
        for pattern, category in (
            (r"working capital", "working_capital"), (r"product development|research and development|\br d\b", "product_development"),
            (r"repay|prepay|debt repayment|borrowings", "debt_repayment"), (r"capital expenditure|\bcapex\b|facility|land|building|plant|equipment", "organic_capex"),
            (r"general corporate|\bgcp\b", "other"),
        ):
            if re.search(pattern, obj):
                return category
        return "other"
    if canonical in {"cwip", "capex"}:
        return "organic_capex"
    # A label the taxonomy has verified against the item's own words (see _apply_label_verdict) as an acquisition is an acquisition, whatever descriptive words ("platform",
    # "analytics") the target's business adds to the purpose; those words used to move a 100% share purchase into 'technology_investment'.
    if canonical in {"acquisitions", "acquisition"} and not any(_has_word(text, w) for w in ("amalgamation", "merger", "merge", "merged")):
        return "acquisition"
    # Treasury placements and intra-group advances keep the meaning their verified label gives them; a word in the counterparty's NAME ("Digital Labs") must not decide it.
    if canonical in {"temporary investment", "bank deposit", "mutual fund investment"}:
        return "retained_cash"
    # A related-party loan the company RECEIVED or availed is a financing inflow, never a deployment into the counterparty.
    if canonical.startswith("related party loan") and any(_has_word(text, w) for w in ("availed", "availing", "received", "taken", "borrowed")):
        return "other"
    if canonical.startswith("related party loan given"):
        return "subsidiary_investment"
    # Shares an ESOP trust buys in the market are neither a buyback by the company nor a technology/R&D spend: an outflow on its own terms.
    if canonical == "treasury share purchase":
        return "other"
    # debt_raised = financing source (proceeds of borrowings), not a deployment — skip to "other"
    # so it doesn't get misclassified as debt_repayment via the canonical check below.
    if canonical == "debt raised":
        return "other"
    if any(_has_word(text, term) for term in ("special dividend", "extra dividend", "one-off dividend", "exceptional dividend")):
        return "special_dividend"
    if canonical in {"dividend_paid", "dividend_declared"} or "dividend" in text:
        return "dividend"
    # "buy back" (hyphen removed by normalizer) must be caught before the debt_repaid canonical check
    if canonical == "buyback" or any(_has_word(text, term) for term in ("buyback", "buy back", "share repurchase", "repurchase of shares")):
        return "share_buyback"
    if canonical in {"debt repaid", "debt_repaid", "lease liability payment", "lease_liability_payment"}:
        return "debt_repayment"                   # an explicit typed label decides before words in a free-text purpose ("...funded from the equity issuance")
    if canonical == "equity_issuance" or any(_has_word(text, term) for term in ("rights issue", "qip", "preferential allotment", "equity issuance", "fresh issue", "shares allotted")):
        return "equity_issuance"
    if canonical in {"debt_repaid", "lease_liability_payment"} or any(_has_word(text, term) for term in ("debt repayment", "loan repaid", "borrowings repaid", "repayment of borrowings", "lease liability")):
        return "debt_repayment"
    if any(_has_word(text, term) for term in ("working capital", "receivable", "inventory", "payable", "cash conversion")):
        return "working_capital"
    if any(_has_word(text, term) for term in ("unutilised proceeds", "unutilized proceeds", "retained earnings", "cash parked", "surplus cash", "idle cash")):
        return "retained_cash"
    if any(_has_word(text, term) for term in ("maintain", "maintenance", "replacement", "upkeep", "sustaining capex", "sustain capex")):
        return "maintenance_capex"
    if any(_has_word(text, term) for term in ("capacity", "plant", "facility", "factory", "production line", "manufacturing line", "commission", "throughput", "output", "expansion")):
        return "capacity_expansion"
    if any(_has_word(text, term) for term in ("product", "new product", "feature", "offering")):
        return "product_development"
    if any(_has_word(text, term) for term in ("research and development", "r and d", "r&d", "research", "intangible", "innovation")):
        return "research_and_development"
    if any(_has_word(text, term) for term in ("technology", "digital", "software", "automation", "platform", "system")):
        return "technology_investment"
    if any(_has_word(text, term) for term in ("acquisition integration", "integration", "amalgamation", "post merger", "post-acquisition", "m&a integration")):
        return "acquisition_integration"
    if any(_has_word(text, term) for term in ("acquisition", "acquire", "purchase", "takeover", "merge", "amalgamation")):
        return "acquisition"
    if any(_has_word(text, term) for term in ("joint venture", "jv", "partnership", "alliance", "collaboration")):
        return "joint_venture"
    if any(_has_word(text, term) for term in ("subsidiary", "wholly owned subsidiary")):
        return "subsidiary_investment"
    if any(_has_word(text, term) for term in ("restructuring", "reorganization", "reorganisation", "demerger", "spin off", "spin-off")):
        return "restructuring"
    if any(_has_word(text, term) for term in ("debt funded", "borrowed funds", "borrowed capital")):
        return "debt_funded_investment"
    if canonical in {"capital_reduction"} or _has_word(text, "capital reduction"):
        return "restructuring"
    if canonical in {"cwip", "capex", "strategic_investments"} or group == "true_capital_deployment":
        if any(_has_word(text, term) for term in ("strategic", "investment")):
            return "strategic_investment"
        return "organic_capex"
    if group == "shareholder_returns" and "dividend" in text:
        return "dividend"
    if group == "shareholder_returns" and "buyback" in text:
        return "share_buyback"
    if group == "financing_actions" and any(_has_word(text, term) for term in ("equity", "issue", "allotment", "rights", "qip")):
        return "equity_issuance"
    if group == "financing_actions" and any(_has_word(text, term) for term in ("debt", "repay", "loan", "lease")):
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


_LEDGER_CRORE_FIELDS = (
    "capex_deployed", "working_capital_deployed",
    "product_development_or_intangible_investment", "debt_repayment",
    "dividends", "buybacks", "acquisitions", "capital_raised",
    "retained_earnings", "unutilised_issue_proceeds",
)


_LEDGER_FIELDS_BY_CATEGORY = {
    "organic_capex": ("capex_deployed",), "maintenance_capex": ("capex_deployed",), "capacity_expansion": ("capex_deployed",), "technology_investment": ("capex_deployed",),
    "working_capital": ("working_capital_deployed",),
    "product_development": ("product_development_or_intangible_investment",), "research_and_development": ("product_development_or_intangible_investment",),
    "debt_repayment": ("debt_repayment",), "dividend": ("dividends",), "special_dividend": ("dividends",),
    "equity_issuance": ("capital_raised",), "retained_cash": ("retained_earnings",),
}
_RE_AMOUNT_FOR_SHARES = re.compile(r"^(?P<amt>.*?)\s+for\s+(?P<n>[\d,]+)\s+(?:equity\s+)?shares\b", re.IGNORECASE)
_BUYBACK_CATEGORIES = {"buyback", "share_buyback", "buy_back"}
_FACE_VALUE_CEILING_PER_SHARE = 10.0  # INR: a buyback pays at least market price; at or below this the figure is the shares' nominal (share-capital) value


def _is_face_value_statement(item: Dict[str, Any]) -> bool:
    """True when a buyback 'INR X for N shares' string implies a per-share figure at nominal-value scale.

    Such a figure (e.g. INR 20.00 lakhs for 20,00,000 shares = INR 1/share) is the share-capital effect of the buyback,
    not the consideration paid, and must not be reported as the buyback amount.
    """
    category = str(item.get("allocation_category") or item.get("category") or "").lower().replace(" ", "_")
    raw = item.get("amount")
    if category not in _BUYBACK_CATEGORIES or not isinstance(raw, str):
        return False
    m = _RE_AMOUNT_FOR_SHARES.match(raw.strip())
    amount_crore = _parse_amount_to_crore(m.group("amt")) if m else None
    shares = float(m.group("n").replace(",", "")) if m else 0.0
    return bool(amount_crore and shares and amount_crore * 1e7 / shares <= _FACE_VALUE_CEILING_PER_SHARE)


def _candidate_amount(item: Dict[str, Any], ledger_entry: Dict[str, Any]) -> Optional[float]:
    """Return confirmed crore amount using deterministic unit authority.

    Canonical crore schema fields (amount_crore, amount_raised_crore) are trusted
    when numeric. The generic 'amount' field is trusted when numeric (financial
    timeline convention) or parsed with explicit unit when a string. String amounts
    without a deterministic unit label return None. If a string amount is present
    but ambiguous, the ledger fallback is suppressed — an ambiguous source amount
    must not be silently replaced by a ledger estimate.
    """
    # Schema-guaranteed crore fields — always numeric in producer
    for field in ("amount_crore", "amount_raised_crore"):
        v = item.get(field)
        if isinstance(v, (int, float)) and v != 0:
            return abs(float(v))

    # Generic 'amount' field: numeric from financial timeline (trust as crore),
    # or string from PCIM items (must parse with unit authority).
    amount_raw = item.get("amount")
    if amount_raw not in (None, "", [], {}):
        if _is_face_value_statement(item):
            return None  # nominal value of the shares, not the consideration; do not fall through to a ledger estimate
        if isinstance(amount_raw, (int, float)):
            v = float(amount_raw)
            return abs(v) if v != 0 else None
        # String amount: unit-aware parse only
        parsed = _parse_amount_to_crore(amount_raw)
        # Do NOT fall through to ledger when string is present but ambiguous:
        # an ambiguous source amount should not be silently superseded.
        return parsed

    if item.get("suppress_ledger_amount"):
        return None

    # Ledger aggregates are not transaction consideration.  In particular,
    # an acquisition record may only carry an amount when its own source item
    # discloses that consideration; never project the annual acquisitions
    # aggregate onto a named target.
    category = str(item.get("allocation_category") or item.get("category") or "").lower()
    if category in {"acquisition", "acquisition_integration", "strategic_investment", "joint_venture", "subsidiary_investment"}:
        return None
    # Same for a buyback: the consideration is the transaction's own figure; a ledger aggregate is not (it has shown a different year's
    # total against the record). Without its own parseable amount the buyback is "not stated", not an estimate.
    if category.replace(" ", "_") in _BUYBACK_CATEGORIES:
        return None

    # Ledger numeric crore fields — typed in producer. A ledger field is the annual aggregate of ONE kind of flow, so it can only stand in for an item of that kind: the
    # first non-zero field used to be returned for every item (a dividend line carried the year's capex figure, a deposit line the year's capex).
    for field in _LEDGER_FIELDS_BY_CATEGORY.get(category.replace(" ", "_"), ()):
        v = ledger_entry.get(field)
        if isinstance(v, (int, float)) and v != 0:
            return abs(float(v))
    return None


def _amount_basis(item: Dict[str, Any], ledger_entry: Dict[str, Any], amount: Optional[float]) -> str:
    if amount is None:
        if _is_face_value_statement(item):
            return "face_value_not_consideration"
        # Check if a string amount was present but ambiguous
        amount_raw = item.get("amount")
        if amount_raw not in (None, "", [], {}):
            if isinstance(amount_raw, str) and amount_raw.strip():
                # A count of shares (or a per-share price) is not a currency amount: the typed basis says so instead of leaving a bare unknown unit.
                if _RE_SHARE_COUNT.search(amount_raw):
                    return "share_count_not_currency"
                return "unit_ambiguous"
        return "unknown"
    for field in ("amount_crore", "amount_raised_crore"):
        if isinstance(item.get(field), (int, float)) and item.get(field) != 0:
            return "source_item"
    if item.get("amount") not in (None, "", [], {}):
        return "source_item"
    category = str(item.get("allocation_category") or item.get("category") or "").lower().replace(" ", "_")
    if any(isinstance(ledger_entry.get(f), (int, float)) and ledger_entry.get(f) != 0
           for f in _LEDGER_FIELDS_BY_CATEGORY.get(category, ())):
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
        extraction_item_id=item.get("extraction_item_id"),
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
    # Similar business purposes are not initiative identity.  Keep threshold in
    # the signature for callers, but never use similarity as execution authority.
    matches: List[Tuple[str, str]] = []
    identity_fields = ("canonical_initiative_id", "transaction_id", "initiative_id", "source_fingerprint")
    label_fields = ("allocation_name", "normalized_name", "project_name", "capacity_name", "commitment_name", "risk_name")
    generic = {"acquisition", "integration", "expansion", "project", "capacity", "investment", "capital", "allocation", "organic", "capex", "new", "business"}

    def labels(value: Dict[str, Any]) -> set:
        result = set()
        for field in label_fields:
            label = _normalize_text(str(value.get(field) or ""))
            if label and set(label.split()) - generic:
                result.add(label)
        return result

    source_labels = labels(record)
    for item in records:
        if not item.get(id_field):
            continue
        if record.get("company") and item.get("company") and record["company"] != item["company"]:
            continue
        # Conflicting explicit identity must not be rescued by an equal label.
        if any(record.get(key) and item.get(key) and record[key] != item[key] for key in identity_fields):
            continue
        reason = next((key for key in identity_fields if record.get(key) and record.get(key) == item.get(key)), None)
        if not reason and source_labels & labels(item):
            reason = "exact_unambiguous_normalized_identity"
        if reason:
            matches.append((str(item[id_field]), reason))
    unique = {identity for identity, _ in matches}
    if len(unique) != 1:
        return []
    return sorted(unique)


def _link_acquisition_records(record: Dict[str, Any], projects: Sequence[Dict[str, Any]]) -> List[str]:
    if record.get("allocation_category") not in {"acquisition", "acquisition_integration"}:
        return []
    return _link_records(record, projects, fields=("project_name", "normalized_name"), id_field="project_id")


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
    elif _pending_distribution(record):
        operating_outcome = "This is primarily a capital-structure or distribution decision rather than an operating investment."
        financial_outcome = "UNABLE_TO_ATTRIBUTE: The dividend is proposed or recommended; no payment is evidenced, so no capital has been returned and no distribution outcome exists yet."
        per_share_outcome = "No per-share consequence until the dividend is paid."
        balance_sheet_outcome = "No balance-sheet effect until the dividend is paid."
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


_DIRECTLY_ATTRIBUTABLE_CATEGORIES = frozenset({
    "dividend", "special_dividend", "share_buyback", "debt_repayment",
})


def _pending_distribution(record: Dict[str, Any]) -> bool:
    """A dividend that is only proposed / recommended / declared-subject-to-approval - or whose payment is not evidenced - is not a completed distribution: nothing has left the company,
    no capital was returned and no owner-value consequence exists. Only a dividend whose lifecycle is evidenced as PAID is executed."""
    if str(record.get("allocation_category") or "") not in {"dividend", "special_dividend"} or record.get("lifecycle") == "paid":
        return False
    # a lifecycle that is not stated falls back to the record's status: only a dividend whose status says it was carried out is treated as executed
    return record.get("lifecycle") == "proposed" or str(record.get("current_status") or "") in {"", "announced", "proposed", "committed", "planned"}

# ENG-122: Five-tier outcome attribution.
# HEURISTIC_CAUSAL_ATTRIBUTION_PATHS = 0 — no token-overlap or temporal inference.
def _determine_outcome_attribution(record: Dict[str, Any], evidence: Sequence[Dict[str, Any]]) -> str:
    """Classify the evidence quality for economic value attribution.

    Strictly evidence-gated: does NOT use temporal sequence as causality proxy.

    DIRECTLY_ATTRIBUTABLE  — transaction itself IS the economic event (distributions, debt repayment),
                             or source explicitly attributes a financial outcome to this allocation.
    STRONGLY_SUPPORTED     — multiple convergent project/capacity evidence items confirm both
                             execution and an explicit positive outcome signal in the record.
    ASSOCIATED_NOT_ATTRIBUTABLE — execution confirmed by evidence, but financial outcome attribution
                             to this specific allocation is not explicit in any source.
    NO_OUTCOME_EVIDENCE    — deployment visible but no execution or downstream evidence available.
    NEGATIVE_OUTCOME       — explicit evidence of delay, abandonment, or value destruction.
    """
    category = str(record.get("allocation_category") or "")
    outcome_status = str(record.get("outcome_status") or "")
    current_status = str(record.get("current_status") or "")
    execution_state = str(record.get("execution_state") or "")

    # Negative: explicit failure / abandonment in record or evidence
    if outcome_status == "negative_outcome" or current_status in {"abandoned", "superseded"}:
        return "NEGATIVE_OUTCOME"

    # Directly attributable: the cash transaction itself IS the economic event.
    # No causal inference required — distribution/repayment is self-evidencing ONCE IT HAS HAPPENED: a proposal is not the event.
    if _pending_distribution(record):
        return "NO_OUTCOME_EVIDENCE"
    if category in _DIRECTLY_ATTRIBUTABLE_CATEGORIES:
        return "DIRECTLY_ATTRIBUTABLE"

    # Strongly supported: multiple explicit project/capacity evidence items AND execution is confirmed.
    # This is still NOT a claim of revenue/earnings attribution — it claims visible operating proof.
    specific = [e for e in evidence if e.get("kind") in {"project", "capacity"}]
    if execution_state == "OPERATIONAL" and len(specific) >= 2:
        return "STRONGLY_SUPPORTED"

    # Associated but not attributable: execution trace confirmed, but financial outcome cannot be
    # cleanly attributed to this specific allocation without an explicit source statement.
    if specific or execution_state in {"OPERATIONAL", "IN_PROGRESS"}:
        return "ASSOCIATED_NOT_ATTRIBUTABLE"

    # No outcome evidence: deployment is recorded but no downstream execution or outcome trace.
    return "NO_OUTCOME_EVIDENCE"


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

    pending_distribution = _pending_distribution(record)
    # --- Execution state ---
    if pending_distribution:
        execution_state = "NOT_STARTED"                     # announced / proposed: no payment is evidenced
    elif category in _DISTRIBUTION_CATEGORIES or category == "debt_repayment":
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
    elif execution_state == "OPERATIONAL" and category in {"acquisition", "acquisition_integration"} and note_text.strip() == "integrated":
        operating_outcome_state = "ACQUIRED_BUSINESS_INTEGRATED"
    elif has_project_evidence and note_text.strip() in {"materially_utilized", "partially_utilized", "underutilized"}:
        operating_outcome_state = "UTILIZATION_VISIBLE"
    else:
        operating_outcome_state = "UNABLE_TO_VERIFY"

    # --- Financial outcome state (strict: only cash transactions have attributable financial outcomes) ---
    if category in {"dividend", "special_dividend", "share_buyback", "debt_repayment"} and not pending_distribution:
        financial_outcome_state = "CASH_FLOW_EFFECT"
    else:
        # Revenue/profit growth after an acquisition or capex program is NOT attributable
        # to that specific allocation without a direct causal link in the evidence
        financial_outcome_state = "UNABLE_TO_ATTRIBUTE"

    # --- Per-share consequence state ---
    if category == "share_buyback":
        per_share_consequence_state = "SHARE_COUNT_REDUCTION"
    elif category in {"dividend", "special_dividend"} and not pending_distribution:
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
    if pending_distribution:
        causal_attribution_confidence = "UNKNOWN"
    elif category in _DISTRIBUTION_CATEGORIES:
        causal_attribution_confidence = "MEDIUM"
    elif category == "debt_repayment":
        causal_attribution_confidence = "LOW"
    elif execution_state in {"OPERATIONAL", "COMPLETED"} and has_project_evidence:
        causal_attribution_confidence = "MEDIUM"
    elif has_project_evidence:
        causal_attribution_confidence = "LOW"
    else:
        causal_attribution_confidence = "UNKNOWN"

    outcome_attribution = _determine_outcome_attribution(record, evidence)

    return {
        "deployment_state": deployment_state,
        "execution_state": execution_state,
        "operating_outcome_state": operating_outcome_state,
        "financial_outcome_state": financial_outcome_state,
        "per_share_consequence_state": per_share_consequence_state,
        "value_creation_classification": value_creation_classification,
        "causal_attribution_confidence": causal_attribution_confidence,
        "outcome_attribution": outcome_attribution,
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
    oa = record.get("outcome_attribution", "")
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
    # ENG-122: outcome_attribution contract
    if oa not in OUTCOME_ATTRIBUTION_LEVELS:
        violations.append(f"outcome_attribution={oa!r} is not a valid OUTCOME_ATTRIBUTION_LEVEL")
    if oa == "STRONGLY_SUPPORTED" and not has_specific:
        violations.append("outcome_attribution=STRONGLY_SUPPORTED requires project/capacity evidence")
    if oa == "DIRECTLY_ATTRIBUTABLE" and cat not in _DIRECTLY_ATTRIBUTABLE_CATEGORIES:
        violations.append(f"DIRECTLY_ATTRIBUTABLE requires a distribution or repayment category; got {cat!r}")
    if oa == "ASSOCIATED_NOT_ATTRIBUTABLE" and cat in _DIRECTLY_ATTRIBUTABLE_CATEGORIES:
        violations.append(f"ASSOCIATED_NOT_ATTRIBUTABLE must not be assigned to distribution/repayment category {cat!r}")
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


_PROCEEDS_NOISE = frozenset({"allocation", "allocated", "proceeds", "proceed", "qip", "ipo", "issue", "use", "used", "funding", "from", "for", "to", "of", "the", "and", "including", "purposes",
                             "purpose", "utilized", "utilised", "spending", "towards", "as", "per", "objects", "object", "with"})


def _object_tokens(value: str) -> set:
    """The words that name WHAT issue proceeds were used for, lightly stemmed (facilities / facility)."""
    out = set()
    for token in _token_set(value) - _PROCEEDS_NOISE:
        out.add(token[:-3] + "y" if token.endswith("ies") else token[:-1] if token.endswith("s") and len(token) > 4 else token)
    return out


_INSTRUMENT = re.compile(r"\b(qip|ipo|rights issue|preferential)\b|qualified institutional placement|initial public", re.I)


def _proceeds_instrument(name: str) -> str:
    match = _INSTRUMENT.search(name or "")
    if not match:
        return ""
    word = match.group(0).lower()
    return {"qualified institutional placement": "qip", "initial public": "ipo"}.get(word, word)


_ISSUE_INSTRUMENTS = (("qip", re.compile(r"\bqip\b|qualified institutional|qualified_institutional", re.I)), ("ipo", re.compile(r"\bipo\b|initial public", re.I)),
                      ("bonus", re.compile(r"\bbonus\b", re.I)), ("rights", re.compile(r"\brights?\s+issue\b", re.I)),
                      ("private_placement", re.compile(r"private placement|preferential", re.I)), ("esop", re.compile(r"\besop\b|employee stock|stock option", re.I)))


def _candidate_text(candidate: Dict[str, Any]) -> str:
    reference = candidate.get("source_reference") or {}
    return " ".join(str(x or "") for x in (candidate.get("allocation_name"), candidate.get("event_category_text"), reference.get("short_excerpt"), reference.get("canonical_category")))


def _issue_instrument(candidate: Dict[str, Any]) -> str:
    """The instrument an issue of shares used (a QIP, an IPO, bonus shares, a rights issue, a private placement, an ESOP issue): different instruments are different events with different
    proceeds, dates and uses, whatever their shared category."""
    text = _candidate_text(candidate)
    return next((name for name, pattern in _ISSUE_INSTRUMENTS if pattern.search(text)), "")


def _financing_family(candidate: Dict[str, Any]) -> str:
    canonical = str((candidate.get("source_reference") or {}).get("canonical_category") or "")
    return "debt" if canonical.startswith("debt") else "equity" if canonical in {"equity_issuance", "qualified_institutional_placement", "share_issuance"} else ""


def _dividend_recipient(candidate: Dict[str, Any]) -> str:
    text = _normalize_text(f"{candidate.get('allocation_name') or ''} {candidate.get('event_category_text') or ''}")
    return "non_controlling_interests" if re.search(r"non controlling|minority", text) else "shareholders"


def _same_event_kind(group_member: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    """Whether two candidates can be the same kind of event. A known lifecycle (a proposed dividend is not a paid one) and a known amount role (a closing balance is not a period flow,
    a cumulative utilisation of issue proceeds is neither the issue nor annual spending) must agree; an unknown one (None) is compatible. A use of issue proceeds is further tied to
    the instrument that raised them (QIP vs IPO) and to the object it was used for, so that two uses never merge for sharing a category."""
    a_life, b_life = group_member.get("lifecycle"), candidate.get("lifecycle")
    if a_life and b_life and a_life != b_life:
        return False
    if candidate.get("allocation_category") in {"dividend", "special_dividend"} and "proposed" in {a_life, b_life} and a_life != b_life:
        return False                      # a dividend whose lifecycle is not stated may be the paid one, but never the proposed one
    if candidate.get("allocation_category") in {"dividend", "special_dividend"} and _dividend_recipient(group_member) != _dividend_recipient(candidate):
        return False                      # a dividend paid to the minority holders of a subsidiary is not the company's dividend to its own shareholders
    a_fam, b_fam = _financing_family(group_member), _financing_family(candidate)
    if a_fam and b_fam and a_fam != b_fam:
        return False                      # a repayment of borrowings is not part of an equity issue
    if candidate.get("allocation_category") == "equity_issuance" and not candidate.get("use_of_issue_proceeds") and not group_member.get("use_of_issue_proceeds"):
        a_inst, b_inst = _issue_instrument(group_member), _issue_instrument(candidate)
        if a_inst and b_inst and a_inst != b_inst:
            return False                  # a QIP, an IPO, bonus shares and a private placement are distinct events
    a_role, b_role = (group_member.get("non_flow_amount") or {}).get("role"), (candidate.get("non_flow_amount") or {}).get("role")
    if bool(a_role) != bool(b_role) or (a_role and b_role and a_role != b_role):
        return False
    if bool(group_member.get("use_of_issue_proceeds")) != bool(candidate.get("use_of_issue_proceeds")):
        return False
    if candidate.get("use_of_issue_proceeds"):
        a_inst, b_inst = _proceeds_instrument(group_member.get("allocation_name", "")), _proceeds_instrument(candidate.get("allocation_name", ""))
        if a_inst and b_inst and a_inst != b_inst:
            return False
        a_obj = _object_tokens(f"{group_member.get('allocation_name', '')} {group_member.get('event_category_text') or ''}")
        b_obj = _object_tokens(f"{candidate.get('allocation_name', '')} {candidate.get('event_category_text') or ''}")
        if not (a_obj & b_obj):
            return False
    return True


def _group_similarity(group: Dict[str, Any], candidate: Dict[str, Any]) -> int:
    if any(not _same_event_kind(member, candidate) for member in group.get("source_items", [])):
        return 0
    # A dividend is paid (or proposed) for one fiscal year: the same wording in another year is another event unless an explicit transaction identity proves otherwise.
    if group["allocation_category"] in {"dividend", "special_dividend"} and candidate["source_year"] not in group["source_years"]:
        if not candidate.get("economic_flow_id") and not candidate.get("transaction_id") and not candidate.get("deal_id"):
            return -1
    # Named-entity events (investments, acquisitions, JVs) are one event only when they share a distinctive name token; the same category plus generic words
    # ("equity", "shares", "investments") is not identity.
    # "other"/"unknown" say nothing about WHAT the event is, so two such records are one event only when they also share a distinctive name token (a related-party loan was
    # merged into an ESOP-trust share purchase, and took its amount, because both were "other").
    if candidate["allocation_category"] in _HIGH_SPECIFICITY_CATEGORIES or candidate["allocation_category"] in {"other", "unknown"}:
        distinctive = (_token_set(candidate["allocation_name"]) - _MERGE_NOISE - _GENERIC_EVENT_WORDS) & (group["signature_tokens"] - _MERGE_NOISE - _GENERIC_EVENT_WORDS)
        if not distinctive:
            return 0
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


_GENERIC_EVENT_WORDS = frozenset({
    "equity", "equities", "share", "shares", "investment", "investments", "invested", "acquired", "acquire", "acquires", "acquiring", "selective", "stake", "minority",
    "subscription", "subscribed", "private", "public", "company", "group", "holdings", "services", "india", "indian", "fy", "year", "ipo", "ipos", "capital",
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


# --- amount role and lifecycle -------------------------------------------------------------------------------------------------------------------------------------------
# An allocation record's `amount` is ONE period's flow. Three kinds of figure look like amounts but are not: a cumulative utilisation of issue proceeds (the QIP table's
# "utilised up to March 31, 2026"), a closing balance (a loan's outstanding principal, unchanged year to year), and a proposed amount that has not been paid. Each is kept
# - typed, with its basis and as-of period - in `non_flow_amounts`, and none is promoted to `amount` (a stock never silently becomes a flow, a plan never becomes spending).
_USE_OF_PROCEEDS = re.compile(r"\b(?:allocation|allocated|use|used|utili[sz]ation|utili[sz]ed|unutili[sz]ed)\b.*\bproceeds?\b|\bproceeds?\b.*\b(?:allocation|utili[sz]ed|utili[sz]ation|unutili[sz]ed)\b|"
                               r"\bfrom (?:the )?(?:qip|ipo|rights issue|preferential (?:issue|allotment)|issue) proceeds\b|\b(?:qip|ipo) proceeds\b|\bobjects? of the (?:issue|offer)\b|\bunutili[sz]ed\b", re.I)
_BORROWING_VERBS = re.compile(r"\b(?:availed|taken|raised|borrowed|sanctioned|disbursed|granted|advanced)\b", re.I)
_BALANCE_CUE = re.compile(r"\bbalance outstanding\b|\boutstanding (?:as at|at)\b|\bclosing balance\b", re.I)
_PROPOSED_CUE = re.compile(r"\b(?:recommended|proposed|propose[sd]?|declare|to be paid|subject to (?:the )?(?:shareholders?'?s?'?|member'?s?'?)? ?approval|subject to approval)\b", re.I)
_PAID_CUE = re.compile(r"\b(?:paid|payout|distributed|disbursed)\b", re.I)
_EXPLICIT_FY = re.compile(r"(?:\bfy\.?\s*|financial year\s+|year ended\s+(?:march\s+31,?\s+)?)(\d{4})(?:\s*[-\u2013/]\s*(\d{2,4}))?", re.I)


def _explicit_fiscal_year(text: str) -> Optional[str]:
    """The fiscal year an item's OWN wording names ("availed during FY 2023-24", "year ended March 31, 2024"), as fyYY; None when it names none or several."""
    years = set()
    for first, second in _EXPLICIT_FY.findall(text or ""):
        end = int(second[-2:]) if second else int(first) % 100
        years.add(f"fy{end:02d}")
    return years.pop() if len(years) == 1 else None


def _amount_role(item: Dict[str, Any], source_year: str) -> Tuple[str, Optional[str]]:
    """(role, event_period) of the item's amount: period_flow | cumulative_utilisation | closing_balance. The event period is the fiscal year the item's own wording names."""
    action = _normalize_text(" ".join(str(item.get(k) or "") for k in ("action", "value", "category")))
    purpose = _normalize_text(str(item.get("purpose") or ""))
    if _USE_OF_PROCEEDS.search(action):
        return ("closing_balance" if re.search(r"\bunutili[sz]ed\b", action) and not re.search(r"\b(?:allocation|use|used)\b", action) else "cumulative_utilisation"), None
    named = _explicit_fiscal_year(f"{item.get('action') or item.get('value') or ''} {item.get('purpose') or ''}")
    borrowing = _BORROWING_VERBS.search(action) or _BORROWING_VERBS.search(purpose)
    category = str(item.get("canonical_category") or item.get("category") or "").lower()
    if borrowing and ("loan" in action or "borrowing" in action or "debt" in category or "loan" in purpose):
        this_year = named == source_year or bool(re.search(r"\bduring (?:the )?(?:year|period|fy)\b|\bfor the year\b", f"{action} {purpose}"))
        if named and named < source_year:
            return "closing_balance", named              # "availed during FY 2023-24", reported in a later year: the figure is the balance the later statements carry
        if _BALANCE_CUE.search(purpose) and not re.search(r"\bduring the year\b|\bduring year\b", str(item.get("amount") or ""), re.I):
            return "closing_balance", named
        if not this_year:
            return "closing_balance", named              # a loan's stated amount with no statement that it was raised in this year is a principal / balance, not a period flow
    return "period_flow", named


def _dividend_lifecycle(item: Dict[str, Any]) -> Optional[str]:
    """proposed | paid for a dividend item, from its own wording. A recommended / declared-subject-to-approval dividend has not been paid."""
    text = _normalize_text(" ".join(str(item.get(k) or "") for k in ("action", "value", "purpose", "status")))
    if "dividend" not in text:
        return None
    if _PROPOSED_CUE.search(text) and not _PAID_CUE.search(_normalize_text(str(item.get("action") or item.get("value") or ""))):
        return "proposed"
    return "paid" if _PAID_CUE.search(text) else None



def _candidate_from_item(
    year: str,
    item: Dict[str, Any],
    group_name: str,
    ledger_entry: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    # An allocation record needs its own description. An item with neither a `value` nor a `purpose` used to be named from the YEAR's ledger summary ("Operating
    # reinvestment") and given the year's ledger figure: a synthetic record, not an evidenced event, and a duplicate of the typed capex record.
    if not (_normalize_text(item.get("value")) or _normalize_text(item.get("purpose"))):
        return None
    allocation_category = _map_allocation_category(item, ledger_entry)
    if group_name in IGNORED_SOURCE_GROUPS and allocation_category in {"unknown", "other"}:
        return None
    if group_name not in RELEVANT_SOURCE_GROUPS and allocation_category in {"unknown", "other"}:
        return None

    lifecycle = _dividend_lifecycle(item) if allocation_category in {"dividend", "special_dividend"} else None
    if lifecycle == "proposed":
        item = {**item, "suppress_ledger_amount": True}      # the ledger's dividend figure is what was PAID in the year; it is not a proposal's amount
    amount_role, named_period = _amount_role(item, year)
    allocation_name = _allocation_name_from_item(item, ledger_entry, allocation_category)
    if amount_role == "cumulative_utilisation" and (item.get("action") or item.get("value")):
        allocation_name = str(item.get("action") or item.get("value")).strip()        # a use of issue proceeds keeps the wording that names the issue and the object
    normalized_name = _normalize_text(allocation_name)
    family_key = _family_key(allocation_category, allocation_name)
    funding_source = _infer_funding_source(allocation_category, item, ledger_entry)
    amount = _candidate_amount({**item, "allocation_category": allocation_category}, ledger_entry)
    amount_basis = _amount_basis(item, ledger_entry, amount)
    non_flow_amount = None
    if amount is not None and amount_role != "period_flow":
        non_flow_amount = {"value": amount, "unit": "INR crore", "role": amount_role, "as_of": year, "basis": amount_basis, "stated": item.get("amount") if isinstance(item.get("amount"), str) else None}
        amount, amount_basis = None, f"{amount_role}_not_a_period_flow"
    if lifecycle == "proposed" and amount is not None:
        non_flow_amount = {"value": amount, "unit": "INR crore", "role": "proposed_not_paid", "as_of": year, "basis": amount_basis, "stated": item.get("amount") if isinstance(item.get("amount"), str) else None}
        amount, amount_basis = None, "proposed_not_paid"
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
        "amount_stated": item.get("amount") if isinstance(item.get("amount"), str) else None,
        "event_category_text": item.get("category") if isinstance(item.get("category"), str) else None,
        "counterparty": item.get("counterparty") or item.get("entity") or None,
        "event_date": item.get("announcement_date") or item.get("effective_date") or item.get("event_date") or None,
        "classification_status": item.get("classification_status"),
        "lifecycle": lifecycle,
        "use_of_issue_proceeds": amount_role == "cumulative_utilisation",
        "non_flow_amount": non_flow_amount,
        "named_period": named_period,
        **resolve_economic_role({"action": allocation_name, "purpose": item.get("purpose"), "status": item.get("status"), "category": allocation_category, "canonical_category": allocation_category, "capital_allocation_group": group_name, **{k: item.get(k) for k in ("economic_flow_id", "transaction_id", "deal_id")}}),
        "economic_flow_relation": item.get("economic_flow_relation") or ("LINKED_BUT_DISTINCT_FLOW" if "sale consideration" in _normalize_text(allocation_name) and "against loan" in _normalize_text(allocation_name) else "DISTINCT_FLOW"),
        "economic_flow_authority": item.get("economic_flow_authority") or ("EXPLICIT_SOURCE_STATEMENT" if "sale consideration" in _normalize_text(allocation_name) and "against loan" in _normalize_text(allocation_name) else "NONE"),
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


_apply_label_verdict = apply_label_verdict      # the one shared rule (knowledge.capital_allocation_taxonomy.apply_label_verdict)


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
            item = _apply_label_verdict(item)
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


def _enrich_buyback_amounts(company_root: Path, candidates: List[Dict[str, Any]]) -> None:
    """G3: a buyback carries the consideration the filing itself states (financials/corporate_actions.json, value_type_used=consideration_reported, i.e.
    shares x price reproduces the stated total). A candidate with no amount of its own gets that figure, labelled amount_basis='filing_disclosure' and stamped
    with the page it came from; nothing is estimated and a ledger aggregate is still never used."""
    cache: Dict[str, List[Dict[str, Any]]] = {}
    for candidate in candidates:
        if candidate.get("allocation_category") not in _BUYBACK_CATEGORIES or candidate.get("amount") is not None:
            continue
        year = str(candidate.get("source_year") or "").lower()
        if year not in cache:
            try:
                payload = json.loads((company_root / year / "financials" / "corporate_actions.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                payload = {}
            cache[year] = [a for a in payload.get("actions", []) if isinstance(a, dict) and a.get("action_type") == "buyback" and a.get("value_type_used") == "consideration_reported" and isinstance(a.get("amount_crore"), (int, float))]
        if len(cache[year]) == 1:
            action = cache[year][0]
            candidate["amount"], candidate["amount_basis"] = abs(float(action["amount_crore"])), "filing_disclosure"
            candidate["amount_source_page"] = action.get("source_page")
            candidate.setdefault("source_reference", {})["disclosure_page"] = action.get("source_page")


def _year_chunks(year_dir: Path) -> List[Dict[str, Any]]:
    """The year's clean chunks; the re-chunked file (made from the filing PDF by the current chunker) outranks a stored one."""
    for name in ("clean_chunks_rechunked.json", "clean_chunks.json"):
        try:
            payload = json.loads((year_dir / "extracted" / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        chunks = payload.get("chunks") if isinstance(payload, dict) else payload
        if isinstance(chunks, list):
            return [c for c in chunks if isinstance(c, dict)]
    return []


def _filing_dated_events(year_dir: Path) -> List[Dict[str, Any]]:
    return extract_dated_events(_year_chunks(year_dir))


def _attach_issue_dates(company_root: Path, candidates: List[Dict[str, Any]]) -> None:
    """An equity issuance's period is the year the filing says it was allotted, not the year of the report that recites it (a FY26 note on the QIP allotted on March 13, 2023)."""
    wanted = [c for c in candidates if c.get("allocation_category") == "equity_issuance" and not c.get("event_date")]
    if not wanted:
        return
    instruments: Dict[str, Dict[str, Any]] = {}
    for year_dir in sorted(p for p in company_root.glob("fy*") if p.is_dir()):
        for name, found in extract_issue_dates(_year_chunks(year_dir)).items():
            if name not in instruments or found["date"] < instruments[name]["date"]:
                instruments[name] = {**found, "source_year": year_dir.name}
    for candidate in wanted:
        text = _normalize_text(f"{candidate.get('allocation_name')} {candidate.get('event_category_text')}")
        for name, pattern in (("qip", r"\bqip\b|qualified institutional placement"), ("ipo", r"\bipo\b|initial public"), ("rights", r"rights issue"), ("preferential", r"preferential")):
            if re.search(pattern, text) and name in instruments:
                found = instruments[name]
                candidate.update({"event_date": found["date"], "event_period": found["period"], "event_date_page": found["page"], "event_date_source_year": found["source_year"]})
                break


def _attach_issue_economics(company_root: Path, candidates: List[Dict[str, Any]]) -> None:
    """Gross versus net proceeds of a QIP: the filing states the shares and the issue price (gross = shares x price) and the issue expenses; the objects table totals the NET proceeds
    (gross less expenses). The figure a record carries as its `amount` is named for what it is, and the other two travel beside it - only when the three reconcile."""
    wanted = [c for c in candidates if c.get("allocation_category") == "equity_issuance" and _issue_instrument(c) == "qip" and c.get("amount") is not None and not c.get("use_of_issue_proceeds")]
    if not wanted:
        return
    economics: Dict[str, Any] = {}
    for year_dir in sorted(p for p in company_root.glob("fy*") if p.is_dir()):
        for key, value in extract_issue_economics(_year_chunks(year_dir)).items():
            economics.setdefault(key, value)
    gross, expenses = economics.get("gross_crore"), economics.get("issue_expenses_crore")
    for candidate in wanted:
        net = float(candidate["amount"])
        if gross is not None and expenses is not None and abs(net + expenses - gross) <= max(0.1, 0.001 * gross):
            candidate["amount_basis_detail"] = "net_proceeds_after_issue_expenses"
            candidate["proceeds_breakdown"] = {"gross_proceeds_crore": gross, "issue_expenses_crore": expenses, "net_proceeds_crore": net, "shares_allotted": economics.get("shares"),
                                               "issue_price": economics.get("issue_price"), "gross_check": f"{economics.get('shares'):,} shares x {economics.get('issue_price')} = {gross}",
                                               "pages": {"gross": economics.get("gross_page"), "issue_expenses": economics.get("issue_expenses_page")}}
        else:
            candidate["amount_basis_detail"] = "proceeds_basis_not_established"        # the filing's figures do not reconcile (or one is missing): the amount is not called gross or net


def _transaction_candidates(company_root: Path) -> List[Dict[str, Any]]:
    """G3: acquisitions the filing announces but has not completed. Read from financials/financial_transaction_disclosures.json (the filing's own status sentence and
    terms, in the stated currency). The record states SIGNED, NOT COMPLETED; nothing is converted, estimated or inferred as done."""
    out: List[Dict[str, Any]] = []
    for year_dir in sorted(p for p in company_root.glob("fy*") if (p / "financials" / "financial_transaction_disclosures.json").exists()):
        try:
            payload = json.loads((year_dir / "financials" / "financial_transaction_disclosures.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        dated_events = None
        for index, tx in enumerate(payload.get("transactions", [])):
            if tx.get("status") not in {"signed_pending_completion", "announced"} or not tx.get("target"):
                continue
            if dated_events is None:
                dated_events = _filing_dated_events(year_dir)
            item = {
                "source_item_id": f"txn_{year_dir.name}_{index}", "source_page": tx.get("source_page"), "canonical_category": "acquisition", "value": f"Proposed acquisition of {tx['target']} (signed; closing pending)",
                "reasoning": f"{tx.get('source_line_item', '')} {tx.get('status_basis', '')}".strip(), "status": "announced", "source_artifact": "financial_transaction_disclosures.json",
            }
            candidate = _candidate_from_item(year_dir.name, item, "true_capital_deployment", {})
            if candidate is None:
                continue
            dated = evidenced_announcement_period(None, year_dir.name, str(tx["target"]), dated_events)
            if dated["basis"] == "dated_event":     # the filing's own dated statement (e.g. a note: "On April 27, 2026, the Group entered into a definitive agreement ...")
                candidate.update({"event_date": dated["event_date"], "event_period": dated["period"], "event_date_page": dated.get("event_page")})
            candidate.update({"transaction_status": tx["status"], "transaction_terms": tx.get("terms_as_stated"), "transaction_status_basis": tx.get("status_basis"), "disclosure_page": tx.get("source_page"),
                              "amount": None, "amount_basis": "foreign_currency_terms_not_converted" if tx.get("terms_as_stated") else "unknown"})
            out.append(candidate)
    return out


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
                # The same own-text check as the PCIM path: a stored label from an older run can belong to a neighbouring line. Replaced or quarantined labels also move the
                # item's group, and a financing inflow (debt raised) is a capital SOURCE, never a deployment.
                item = _apply_label_verdict(item)
                group_name_effective = str(item.get("capital_allocation_group") or group_name)
                if str(item.get("canonical_category") or "") == "debt_raised":
                    continue
                candidate = _candidate_from_item(year, item, group_name_effective, ledger_entry)
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
                line_item = _normalize_text(f"{action.get('source_line_item') or ''} {action.get('value') or ''}")
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
        # A ledger entry of the generic kinds ("operating reinvestment", "unclear") is the year's aggregate, not an event: it duplicates the typed capex record and would be
        # named from the ledger summary. Only entries that name a specific event (a shareholder return, a raise, a repayment) may create a record here.
        if event_type in {"", "operating_reinvestment", "unclear", "unknown", "capital_deployment"}:
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

    _enrich_buyback_amounts(company_root, candidates)
    _attach_issue_dates(company_root, candidates)
    _attach_issue_economics(company_root, candidates)
    candidates.extend(_transaction_candidates(company_root))
    return candidates, artifacts


_ENTITY_EVENT_CATEGORIES = {"acquisition", "acquisition_integration", "strategic_investment", "joint_venture", "subsidiary_investment"}
_RE_ENTITY = re.compile(r"\b(?:shares?|stake|interest|units?)\s+(?:of|in)\s+((?:[A-Z][\w&.\-]*\s+){0,5}?[A-Z][\w&.\-]*(?:\s+(?:Private|Pvt\.?|Public))?\s+(?:Limited|Ltd\.?|Inc\.?|Corporation|Corp\.?|LLC|LLP|plc|Pte\.?\s+Ltd\.?))", re.UNICODE)
_RE_ENTITY_ACQ = re.compile(r"\b(?:acquisition of|acquire[sd]?|acquiring)\s+(?:\d[\d.,]*\s*%\s+(?:of\s+)?)?((?:[A-Z][\w&.\-]*\s+){0,5}?[A-Z][\w&.\-]*(?:\s+(?:Private|Pvt\.?|Public))?\s+(?:Limited|Ltd\.?|Inc\.?|Corporation|Corp\.?|LLC|LLP|plc))", re.UNICODE)


def _entity_from_name(name: str, category: str) -> Optional[str]:
    """The counterparty named in the event wording, only for events that have one and only when it carries a legal-entity suffix; otherwise unknown."""
    if category not in _ENTITY_EVENT_CATEGORIES or not name:
        return None
    m = _RE_ENTITY.search(name) or _RE_ENTITY_ACQ.search(name)
    return " ".join(m.group(1).split()) if m else None


def _typed_event(group: Dict[str, Any], candidates: Sequence[Dict[str, Any]], latest: Dict[str, Any]) -> Dict[str, Any]:
    """Event nature/completion from the shared taxonomy vocabulary. Only a deployment-type event has a nature here; the company's own issuances and returns are not
    'subscriptions' or 'stakes' even when their wording says 'preference shares'."""
    if group["allocation_category"] not in _ENTITY_EVENT_CATEGORIES:
        return {"nature": "other", "completion": "unspecified"}
    category_text = next((c.get("event_category_text") for c in reversed(candidates) if c.get("event_category_text")), "")
    return event_nature(category_text, group["allocation_name"], latest.get("transaction_status") or "")


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
    amount_source = next((candidate for candidate in reversed(candidates) if candidate.get("amount") is not None), None)
    if group["allocation_category"] == "organic_capex":
        canonical = next((candidate for candidate in reversed(candidates) if candidate.get("amount") is not None
                          and candidate.get("source_year") == latest_period and candidate.get("source_artifact") == "financial_fact_registry.json"
                          and str(candidate.get("source_item_id", "")).startswith("capex_")), None)
        amount_source = canonical or amount_source  # source authority beats arbitrary source-item alphabetic order
    amount = amount_source["amount"] if amount_source else None
    # Conflicting dividend totals across source representations are not safely
    # resolvable by recency; retain the event but remove it from weighted totals.
    if group["allocation_category"] in {"dividend", "special_dividend"}:
        dividend_amounts = sorted({round(float(c["amount"]), 6) for c in candidates if c.get("amount") is not None})
        # a rounded highlight (161.0) beside the statement's own figure (161.4463) is one amount at two precisions, not a conflict: within half a percent the most precise stands
        clustered = [a for i, a in enumerate(dividend_amounts) if i == 0 or abs(a - dividend_amounts[i - 1]) > max(0.5, 0.005 * abs(a))]
        if len(clustered) > 1:
            amount = None
        elif len(dividend_amounts) > 1:
            precise = max(dividend_amounts, key=lambda a: len(repr(a).split(".")[-1]))
            amount_source = next((c for c in reversed(candidates) if c.get("amount") is not None and round(float(c["amount"]), 6) == precise), amount_source)
            amount = amount_source["amount"]
    # An amount is the figure of ONE source item, so it is stamped with that item's own period; it is not the total of deployment_periods.
    amount_period = amount_source["source_year"] if (amount is not None and amount_source) else None
    if amount is not None and amount_source and group["allocation_category"] == "equity_issuance" and amount_source.get("event_period") and amount_source["event_period"] != amount_period:
        # the issue's proceeds belong to the year the filing says the shares were allotted, whichever later report recites them
        amount_period = amount_source["event_period"]
        deployment_periods = _years_covered([*deployment_periods, amount_period])
        first_observed_period = deployment_periods[0]
    if amount is not None:
        amount_basis = "semantic_amount_ambiguous" if group["allocation_category"] in {"dividend", "special_dividend"} and len({round(float(c["amount"]), 6) for c in candidates if c.get("amount") is not None}) > 1 else next(
            (candidate["amount_basis"] for candidate in reversed(candidates) if candidate.get("amount") is not None),
            "unknown",
        )
    else:
        # No confirmed amount: surface unit_ambiguous if any candidate had a string amount with no parseable unit
        amount_basis = next(
            (candidate["amount_basis"] for candidate in reversed(candidates) if candidate.get("amount_basis") in ("share_count_not_currency", "unit_ambiguous")),
            "unknown",
        )
    current_status = _current_status_from_candidate(latest_candidate)
    if latest_candidate.get("lifecycle") == "proposed":
        current_status = "announced"             # recommended / subject to approval: not yet paid
    if latest_candidate.get("transaction_status") in {"signed_pending_completion", "announced"}:
        current_status = "announced"       # signed is not completed: the filing's status sentence outranks keyword matching on its own wording

    project_lookup = linked["projects"]
    capacity_lookup = linked["capacity"]
    commitment_lookup = linked["commitments"]
    risk_lookup = linked["risks"]

    record = {
        "allocation_id": allocation_id,
        "allocation_category": group["allocation_category"],
        # A canonical annual total must not inherit a component-only/PPE/project name from an older merged source.
        "allocation_name": "Reported annual capital expenditure" if (amount_source and amount_source.get("source_artifact") == "financial_fact_registry.json"
                                                                   and str(amount_source.get("source_item_id", "")).startswith("capex_")) else group["allocation_name"],
        "normalized_name": group["normalized_name"],
        "first_observed_period": first_observed_period,
        "deployment_periods": deployment_periods,
        "amount": amount,
        "amount_period": amount_period,
        "amount_basis": amount_basis,
        # SSOT typed fields: an amount is ONE source item's figure in crore INR for ONE period; the stated wording stays for audit.
        "amount_unit": "INR crore" if amount is not None else None,
        "amount_currency": "INR" if amount is not None else None,
        "amount_aggregation": "single_period_flow" if amount is not None else None,
        "amount_basis_detail": next((c.get("amount_basis_detail") for c in reversed(candidates) if c.get("amount_basis_detail")), None),
        "proceeds_breakdown": next((c.get("proceeds_breakdown") for c in reversed(candidates) if c.get("proceeds_breakdown")), None),
        "amount_source_item_id": amount_source.get("source_item_id") if (amount is not None and amount_source) else None,
        "amount_stated": next((c.get("amount_stated") for c in reversed(candidates) if c.get("amount_stated")), None),
        "non_flow_amounts": [c["non_flow_amount"] for c in candidates if c.get("non_flow_amount")],
        "lifecycle": next((c.get("lifecycle") for c in reversed(candidates) if c.get("lifecycle")), None),
        "event_nature": _typed_event(group, candidates, latest_candidate)["nature"],
        "event_completion": _typed_event(group, candidates, latest_candidate)["completion"],
        "event_category_text": next((c.get("event_category_text") for c in reversed(candidates) if c.get("event_category_text")), None),
        "entity": next((c.get("counterparty") for c in reversed(candidates) if c.get("counterparty")), None) or _entity_from_name(group["allocation_name"], group["allocation_category"]),
        "event_date": next((c.get("event_date") for c in reversed(candidates) if c.get("event_date")), None),
        "event_period": next((c.get("event_period") for c in reversed(candidates) if c.get("event_period")), None) or next((c.get("named_period") for c in reversed(candidates) if c.get("named_period") and c.get("non_flow_amount")), None),
        "transaction_status": next((c.get("transaction_status") for c in reversed(candidates) if c.get("transaction_status")), None),
        "transaction_terms": next((c.get("transaction_terms") for c in reversed(candidates) if c.get("transaction_terms")), None),
        "transaction_status_basis": next((c.get("transaction_status_basis") for c in reversed(candidates) if c.get("transaction_status_basis")), None),
        "economic_role": latest_candidate.get("economic_role", "ECONOMIC_ROLE_AMBIGUOUS"),
        "deployment_eligibility": latest_candidate.get("deployment_eligibility", "ELIGIBILITY_AMBIGUOUS"),
        "economic_flow_relation": latest_candidate.get("economic_flow_relation", "DISTINCT_FLOW"),
        "economic_flow_authority": latest_candidate.get("economic_flow_authority", "NONE"),
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
    if _pending_distribution(record):
        record["deployment_eligibility"] = "INELIGIBLE_ANNOUNCED_NOT_DEPLOYED"          # a proposal is not a completed distribution
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
        "economic_role": record.get("economic_role", "ECONOMIC_ROLE_AMBIGUOUS"),
        "deployment_eligibility": record.get("deployment_eligibility", "ELIGIBILITY_AMBIGUOUS"),
        "economic_flow_relation": record.get("economic_flow_relation", "DISTINCT_FLOW"),
        "execution_state": record.get("execution_state", "UNABLE_TO_VERIFY"),
        "operating_outcome_state": record.get("operating_outcome_state", "UNABLE_TO_VERIFY"),
        "financial_outcome_state": record.get("financial_outcome_state", "UNABLE_TO_ATTRIBUTE"),
        "per_share_consequence_state": record.get("per_share_consequence_state", "UNABLE_TO_ATTRIBUTE"),
        "value_creation_classification": record.get("value_creation_classification", "UNABLE_TO_VERIFY"),
        "causal_attribution_confidence": record.get("causal_attribution_confidence", "UNKNOWN"),
        "outcome_attribution": record.get("outcome_attribution", "NO_OUTCOME_EVIDENCE"),
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


_OUTPUT_FILES = (
    "capital_allocation_outcomes.json",
    "capital_allocation_timelines.json",
    "capital_allocation_assessments.json",
    "capital_allocation_validation.json",
    "capital_allocation_manifest.json",
    "capital_allocation_longitudinal_profile.json",
)


class CapitalAllocationOutcomesBuilder:
    def __init__(self, company: str, companies_root: Path | str, *, authorize_served_write: bool = False):
        self.company = company
        # explicit, absolute, symlink-resolved; the served companies/ tree is refused unless authorize_served_write=True
        self.companies_root = resolve_output_root(companies_root, authorize_served=authorize_served_write)
        self.company_root = self.companies_root / company
        self.output_dir = get_capital_allocation_outcomes_dir(company, self.companies_root)

    def plan_outputs(self) -> Dict[str, Path]:
        """The exact files build() would write. Read-only: nothing is created."""
        return {name: safe_destination(self.companies_root, self.output_dir / name) for name in _OUTPUT_FILES}

    def build(self) -> Dict[str, Path]:
        payloads = build_capital_allocation_outcomes(company=self.company, company_root=self.company_root)
        written: Dict[str, Path] = {}
        for filename, payload in payloads.items():
            written[filename] = write_json_file(self.output_dir / filename, payload, root=self.companies_root)
        # Phase 3: longitudinal profile (reads Phase 2 artifacts just written, from this same root)
        longitudinal_path = get_capital_allocation_longitudinal_profile_path(self.company, self.companies_root)
        profile = build_longitudinal_profile(self.company, self.company_root)
        written["capital_allocation_longitudinal_profile.json"] = write_longitudinal_profile(self.companies_root, longitudinal_path, profile)
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
            logical_company_path(path, company_root.parent)
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
            logical_company_path(path, company_root.parent)
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


def write_capital_allocation_outcomes(*, company: str, company_root: Path, output_dir: Path, output_root: Path | str, authorize_served_write: bool = False) -> Dict[str, Path]:
    """Write the bundle under output_dir, which must lie inside the explicit, absolute output_root."""
    root = resolve_output_root(output_root, authorize_served=authorize_served_write)
    payloads = build_capital_allocation_outcomes(company=company, company_root=company_root)
    written: Dict[str, Path] = {}
    for filename, payload in payloads.items():
        written[filename] = write_json_file(output_dir / filename, payload, root=root)
    return written
