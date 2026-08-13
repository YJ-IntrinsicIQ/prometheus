from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from .mapping_registry import CANONICAL_SECTION_FIELDS, FIELD_MAPPINGS, SPECIAL_MULTI_FIELD_ALIASES


_FORBIDDEN_BY_FIELD = {
    "ebit": (
        "surplus",
        "opening balance",
        "retained earnings",
        "statement of changes in equity",
        "other equity",
        "reserves",
    ),
    "ebitda": (
        "surplus",
        "opening balance",
        "retained earnings",
        "statement of changes in equity",
        "other equity",
        "reserves",
    ),
    "face_value": (
        "fair value gain",
        "fair value loss",
        "remeasurement",
        "fvtpl",
        "fvoci",
    ),
    "shares_outstanding": (
        "trade payable",
        "trade payables",
        "msme",
        "dues",
        "other non current assets",
        "other current assets",
        "liabilities",
        "payables",
    ),
    "weighted_avg_shares": (
        "trade payable",
        "trade payables",
        "msme",
        "dues",
        "liabilities",
        "payables",
    ),
    "diluted_shares": (
        "trade payable",
        "trade payables",
        "msme",
        "dues",
        "liabilities",
        "payables",
    ),
    "short_term_debt": (
        "assets",
        "cash and cash equivalents",
        "cash equivalents",
        "investments",
        "receivables",
        "inventory",
        "inventories",
    ),
    "long_term_debt": (
        "repayment of long term borrowings",
        "prepayment",
        "repayment",
        "cash flow",
    ),
    "revenue": (
        "growth %",
        "growth percentage",
        "intensity",
        "energy intensity",
        "emissions intensity",
        "per employee",
        "per head",
        "concentration",
        "mix %",
        "mix percentage",
        "revenue per employee",
        "revenue intensity",
        "revenue concentration",
        "revenue mix",
        "revenue growth",
        "turnover ratio",
    ),
}

_REVENUE_CONTAMINATION_TOKENS = (
    "ghg",
    "greenhouse",
    "emission",
    "emissions",
    "tco2e",
    "scope 1",
    "scope 2",
    "scope 3",
    "carbon",
)

_CORPORATE_ACTION_EXPLICIT_TOKENS = {
    "dividend": ("dividend",),
    "split": ("split", "sub-division", "subdivision"),
    "bonus": ("bonus",),
    "buyback": ("buyback", "buy-back"),
    "rights_issue": ("rights issue", "rights shares", "rights entitlement"),
    "qip": ("qip", "qualified institutional placement"),
    "preferential_issue": ("preferential issue", "preferential allotment"),
}

_NOTE_CONTEXT_TOKENS = {
    "eps_basic": ("earnings per share", "eps", "per share"),
    "eps_diluted": ("earnings per share", "eps", "per share"),
    "face_value": ("face value", "nominal value", "equity shares of rs", "equity shares of re"),
    "shares_outstanding": ("shares", "equity share"),
    "weighted_avg_shares": ("weighted average", "equity share"),
    "diluted_shares": ("diluted", "equity share"),
}

_SHARES_OUTSTANDING_EXPLICIT_TOKENS = (
    "number of equity shares",
    "issued equity shares",
    "subscribed equity shares",
    "paid up equity shares",
    "paid-up equity shares",
    "outstanding equity shares",
    "equity shares outstanding",
    "number of shares outstanding",
    "number of equity shares outstanding",
    "issued subscribed and paid up equity shares",
    "issued subscribed and paid-up equity shares",
    "issued subscribed and fully paid up equity shares",
    "issued subscribed and fully paid-up equity shares",
    "issued subscribed paid up equity shares",
    "issued subscribed paid-up equity shares",
    "subscribed and paid up equity shares",
    "subscribed and paid-up equity shares",
    "subscribed paid up equity shares",
    "subscribed paid-up equity shares",
)

_WEIGHTED_AVG_SHARES_EXPLICIT_TOKENS = (
    "weighted average number of equity shares",
    "weighted average shares outstanding",
    "weighted average number of shares used in eps calculation",
    "weighted average number of shares used for eps",
    "weighted average number of shares",
)

_DILUTED_SHARES_EXPLICIT_TOKENS = (
    "weighted average number of diluted equity shares",
    "diluted weighted average number of equity shares",
    "diluted weighted average shares",
    "number of shares used for diluted eps",
    "number of shares used in diluted eps calculation",
)

_FACE_VALUE_EXPLICIT_TOKENS = (
    "face value",
    "nominal value",
    "nominal value of equity shares",
    "face value of equity shares",
)

_SHARE_COUNT_DISALLOWED_TOKENS = (
    "authorised share capital",
    "authorized share capital",
    "authorised equity shares",
    "authorized equity shares",
    "mutual fund",
    "investment units",
    "units held",
    "qip proceeds",
    "dividend amount",
    "securities premium",
    "reserves",
    "face value",
    "nominal value",
    "at the beginning",
    "beginning of the period",
    "beginning of the year",
    "opening balance",
)

_FACE_VALUE_ROW_DISALLOWED_TOKENS = (
    "authorised",
    "authorized",
    "issued",
    "subscribed",
    "paid up",
    "paid-up",
    "fully paid",
    "opening balance",
    "closing balance",
    "numbers amount",
)

_CAPEX_ALLOWED_TOKENS = (
    "purchase of property plant and equipment",
    "purchase of property, plant and equipment",
    "purchase of ppe",
    "acquisition of property plant and equipment",
    "acquisition of property, plant and equipment",
    "payment for property plant and equipment",
    "payment for property, plant and equipment",
    "capital expenditure",
    "capex",
    "purchase of intangible assets",
    "purchase of fixed assets",
)

_CAPEX_CWIP_ALLOWED_TOKENS = (
    "investment in capital work in progress",
    "investment in capital work-in-progress",
)

_CAPEX_DISALLOWED_TOKENS = (
    "net cash used in investing activities",
    "net cash from investing activities",
    "investing activities",
    "cash flow statement",
    "year ended",
    "march 31",
    "balance as at",
    "property plant and equipment balance",
    "closing balance",
    "opening balance",
    "depreciation",
    "right of use asset",
    "right-of-use asset",
    "lease liability",
    "lease liabilities",
    "lease payment",
    "lease payments",
    "investment in mutual fund",
    "investment in mutual funds",
    "mutual fund",
    "mutual funds",
)

_PAYABLES_ALLOWED_TOKENS = (
    "trade payables",
    "total trade payables",
    "accounts payable",
    "supplier payables",
    "dues to suppliers",
    "creditors for goods services",
    "creditors for goods and services",
    "total outstanding dues of micro enterprises and small enterprises",
    "total outstanding dues of creditors other than micro enterprises and small enterprises",
)

_PAYABLES_DISALLOWED_TOKENS = (
    "total liabilities",
    "other financial liabilities",
    "borrowings",
    "lease liabilities",
    "lease liability",
    "provisions",
    "deferred tax liabilities",
    "other current liabilities",
    "contract liabilities",
    "employee liabilities",
    "employee related payables",
    "statutory dues",
    "current liabilities",
    "capital creditors",
    "advance to suppliers",
    "turnover ratio",
    "page",
    "note",
)


@dataclass
class MappingMatch:
    canonical_section: str
    canonical_field: str
    score: int
    confidence: str
    reason: str


def normalize_label(text: str) -> str:
    normalized = str(text or "").lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9%]+", " ", normalized)
    normalized = " ".join(normalized.split())
    return normalized


def _score_alias(normalized_label: str, normalized_alias: str) -> int:
    if not normalized_alias:
        return 0
    if normalized_label == normalized_alias:
        return 100
    if normalized_alias in normalized_label:
        return 85
    alias_tokens = normalized_alias.split()
    label_tokens = normalized_label.split()
    if len(alias_tokens) == 1:
        return 70 if alias_tokens[0] in label_tokens else 0
    if alias_tokens and all(token in label_tokens for token in alias_tokens):
        return 70
    overlap = len(set(alias_tokens) & set(label_tokens))
    if len(alias_tokens) >= 3 and overlap >= len(alias_tokens) - 1:
        return 55
    return 0


def _confidence_from_score(score: int) -> str:
    if score >= 95:
        return "high"
    if score >= 75:
        return "medium"
    return "low"


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _is_explicit_fcf_label(normalized_label: str) -> bool:
    if normalized_label in {"fcf", "free cash flow", "free cashflow"}:
        return True
    return "fcf" in normalized_label.split()


def _contains_equity_shares_of_rs_each(normalized_label: str) -> bool:
    return bool(re.search(r"equity shares of r(?:s|e)\s*\d+(?:\.\d+)? each", normalized_label))


def _field_allowed(*, canonical_section: str, canonical_field: str, normalized_label: str, table_type: str) -> bool:
    forbidden = _FORBIDDEN_BY_FIELD.get(canonical_field, ())
    if forbidden and _contains_any(normalized_label, forbidden):
        return False

    if canonical_field == "total_assets":
        if "total assets" not in normalized_label:
            return False

    if canonical_field == "total_liabilities":
        if "total liabilities" not in normalized_label:
            return False

    if canonical_section == "profit_and_loss" and canonical_field == "total_income":
        if any(token in normalized_label for token in ("tax", "income tax", "profit before tax", "profit after tax")):
            return False
        if "total income" not in normalized_label and "total operating revenue" not in normalized_label:
            return False

    if canonical_section == "profit_and_loss" and canonical_field == "tax":
        if any(token in normalized_label for token in ("rate", "reconciliation", "estimated", "provision", "deferred tax", "other comprehensive income")):
            return False
        if not any(
            token in normalized_label
            for token in ("tax expense", "income tax expense", "total tax expense", "current tax")
        ):
            return False

    if canonical_section == "profit_and_loss" and canonical_field == "revenue":
        if _contains_any(normalized_label, _FORBIDDEN_BY_FIELD.get("revenue", ())):
            return False
        if _contains_any(normalized_label, _REVENUE_CONTAMINATION_TOKENS):
            return False
        if not any(
            token in normalized_label
            for token in ("revenue from operations", "revenue", "income from operations", "total operating revenue")
        ):
            return False

    if canonical_section == "profit_and_loss" and canonical_field == "pat":
        if not any(
            token in normalized_label
            for token in (
                "profit after tax",
                "profit for the year",
                "profit for the period",
                "profit loss for the period",
                "profit loss for the year",
                "pat",
            )
        ):
            return False

    if canonical_section == "corporate_actions":
        required = _CORPORATE_ACTION_EXPLICIT_TOKENS.get(canonical_field, ())
        if required and not _contains_any(normalized_label, required):
            return False

    if canonical_field in _NOTE_CONTEXT_TOKENS:
        if table_type in {"eps", "share_capital", "shareholding_pattern", "corporate_actions"}:
            required = _NOTE_CONTEXT_TOKENS[canonical_field]
            if not _contains_any(normalized_label, required):
                return False

    if canonical_field == "shares_outstanding":
        if "authorised" in normalized_label or "authorized" in normalized_label:
            return False
        if _contains_any(normalized_label, _SHARE_COUNT_DISALLOWED_TOKENS):
            return False
        if not _contains_any(normalized_label, _SHARES_OUTSTANDING_EXPLICIT_TOKENS):
            return False

    if canonical_field == "weighted_avg_shares":
        if _contains_any(normalized_label, _SHARE_COUNT_DISALLOWED_TOKENS):
            return False
        if table_type != "eps":
            return False
        if not _contains_any(normalized_label, _WEIGHTED_AVG_SHARES_EXPLICIT_TOKENS):
            return False

    if canonical_field == "diluted_shares":
        if _contains_any(normalized_label, _SHARE_COUNT_DISALLOWED_TOKENS):
            return False
        if table_type != "eps":
            return False
        if not _contains_any(normalized_label, _DILUTED_SHARES_EXPLICIT_TOKENS):
            return False

    if canonical_field == "face_value":
        if any(token in normalized_label for token in ("fair value", "market value", "nav", "investment value")):
            return False
        if _contains_equity_shares_of_rs_each(normalized_label) and _contains_any(normalized_label, _FACE_VALUE_ROW_DISALLOWED_TOKENS):
            return False
        if not (
            _contains_any(normalized_label, _FACE_VALUE_EXPLICIT_TOKENS)
            or _contains_equity_shares_of_rs_each(normalized_label)
        ):
            return False

    if canonical_field == "fcf":
        if not _is_explicit_fcf_label(normalized_label):
            return False
        if any(
            token in normalized_label
            for token in ("statement", "year ended", "year ending", "march", "balance as at")
        ):
            return False

    if canonical_field == "capex":
        if _contains_any(normalized_label, _CAPEX_DISALLOWED_TOKENS):
            return False
        if _contains_any(normalized_label, _CAPEX_ALLOWED_TOKENS):
            return True
        if _contains_any(normalized_label, _CAPEX_CWIP_ALLOWED_TOKENS):
            return table_type == "cash_flow"
        return False

    if canonical_field == "payables":
        if _contains_any(normalized_label, _PAYABLES_DISALLOWED_TOKENS):
            return False
        return _contains_any(normalized_label, _PAYABLES_ALLOWED_TOKENS)

    if canonical_field == "ebitda" and "margin" in normalized_label:
        return False
    if canonical_field == "ebit" and "margin" in normalized_label:
        return False
    if canonical_field in {"shares_outstanding", "weighted_avg_shares", "diluted_shares"} and "%" in normalized_label:
        return False
    if canonical_field == "face_value" and "per share" in normalized_label and "face value" not in normalized_label and "nominal value" not in normalized_label:
        return False

    return True


def map_line_item(*, table_type: str, line_item_raw: str) -> List[MappingMatch]:
    normalized_label = normalize_label(line_item_raw)
    matches: List[MappingMatch] = []

    special_fields = SPECIAL_MULTI_FIELD_ALIASES.get(normalized_label)
    if special_fields:
        for field in special_fields:
            for section_name, fields in CANONICAL_SECTION_FIELDS.items():
                if field in fields:
                    matches.append(
                        MappingMatch(
                            canonical_section=section_name,
                            canonical_field=field,
                            score=95,
                            confidence="high",
                            reason="special_multi_field_alias",
                        )
                    )
        return matches

    for section_name, fields in FIELD_MAPPINGS.items():
        for field_name, rule in fields.items():
            allowed_tables = [str(item) for item in rule.get("table_types", [])]
            aliases = [normalize_label(str(item)) for item in rule.get("aliases", [])]
            if allowed_tables and table_type not in allowed_tables:
                continue
            best_alias_score = max((_score_alias(normalized_label, alias) for alias in aliases), default=0)
            if best_alias_score <= 0:
                continue
            if not _field_allowed(
                canonical_section=section_name,
                canonical_field=field_name,
                normalized_label=normalized_label,
                table_type=table_type,
            ):
                continue
            matches.append(
                MappingMatch(
                    canonical_section=section_name,
                    canonical_field=field_name,
                    score=best_alias_score,
                    confidence=_confidence_from_score(best_alias_score),
                    reason=f"alias_match:{field_name}",
                )
            )

    matches.sort(key=lambda item: (-item.score, item.canonical_section, item.canonical_field))
    if not matches:
        return []
    top_score = matches[0].score
    return [match for match in matches if match.score == top_score]


def mapping_registry_snapshot() -> Dict[str, Dict[str, Dict[str, object]]]:
    return FIELD_MAPPINGS
