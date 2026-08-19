from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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
    "total_assets": (
        "average total assets",
        "average assets",
        "segment assets",
        "earning assets",
        "risk weighted assets",
        "risk-weighted assets",
        "rwa",
        "aum",
        "assets under management",
        "assets under insurance",
    ),
    "net_worth": (
        "tranche",
        "off balance sheet",
        "off-balance-sheet",
        "increased from",
        "decreased from",
        "grew from",
        "rose from",
        "regulatory capital",
        "capital adequacy",
        "capital ratio",
        "tier i capital",
        "tier ii capital",
        "risk weighted assets",
        "risk-weighted assets",
        "rwa",
        "instrument",
        "security",
        "debenture",
        "bond",
    ),
    "pbt": (
        "working capital",
        "working capital changes",
        "operating profit",
        "operating loss",
        "cash flow",
    ),
    "tax": (
        "paid",
        "refund",
        "refunds",
        "payment",
        "payments",
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

    if canonical_field == "net_worth":
        if "liabilities" in normalized_label:
            return False

    if canonical_section == "profit_and_loss" and canonical_field == "total_income":
        if any(token in normalized_label for token in ("tax", "income tax", "profit before tax", "profit after tax")):
            return False
        if "total income" not in normalized_label and "total operating revenue" not in normalized_label:
            return False

    if canonical_section == "profit_and_loss" and canonical_field == "tax":
        if any(token in normalized_label for token in ("rate", "reconciliation", "estimated", "provision", "other comprehensive income")):
            return False
        if table_type == "cash_flow" and "tax adjustment" in normalized_label:
            return True
        if "deferred tax" in normalized_label and not any(
            token in normalized_label for token in ("tax expense", "income tax expense", "total tax expense", "current tax")
        ):
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
        if any(
            token in normalized_label
            for token in (
                "ratio",
                "margin",
                "per share",
                "comprehensive income",
                "attributable",
                "associate",
                "before tax",
                "profit before tax",
                "pbt",
            )
        ):
            return False
        if not (
            _contains_any(
                normalized_label,
                (
                    "profit after tax",
                    "profit after taxation",
                    "profit for the year",
                    "profit for the period",
                    "profit loss for the period",
                    "profit loss for the year",
                    "pat",
                ),
            )
            or (
                "net profit" in normalized_label
                and _contains_any(
                    normalized_label,
                    ("5 6 8 9", "5-6-8-9", "after tax", "after taxation", "after taxes"),
                )
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

    # Cross-family routing guards: prevent fields from mapping in wrong table contexts
    if canonical_section == "profit_and_loss" and canonical_field == "revenue":
        if table_type in {"share_capital", "eps", "dividend", "shareholding_pattern", "corporate_actions"}:
            return False
        if table_type == "balance_sheet":
            # Allow only explicit revenue aliases in balance_sheet context (e.g., revenue notes)
            if not _is_exact_alias(normalized_label, "profit_and_loss", "revenue"):
                return False
    if canonical_section == "profit_and_loss" and canonical_field in {"pat", "pbt"}:
        if table_type in {"share_capital", "eps", "dividend", "shareholding_pattern", "corporate_actions"}:
            return False
        if table_type == "balance_sheet":
            # Allow only explicit summary labels in balance sheet context
            if canonical_field == "pat" and not any(
                token in normalized_label
                for token in ("profit after tax", "profit after taxation", "total profit after", "profit for the year", "profit for the period", "net profit 5 6 8 9", "net profit 5-6-8-9")
            ):
                return False
            if canonical_field == "pbt" and not any(
                token in normalized_label
                for token in ("profit before tax", "profit before taxation", "total profit before")
            ):
                return False
        if table_type == "cash_flow":
            # Allow PAT/PBT in cash_flow context (e.g., "Net Profit/(Loss) After taxation" in operating activities)
            if canonical_field == "pat" and "after taxation" not in normalized_label and "after tax" not in normalized_label:
                return False
            if canonical_field == "pbt" and "before taxation" not in normalized_label and "before tax" not in normalized_label:
                return False
    if canonical_section == "profit_and_loss" and canonical_field == "tax":
        if table_type in {"share_capital", "eps", "dividend", "shareholding_pattern", "corporate_actions"}:
            return False
        if table_type == "cash_flow" and "tax expense" in normalized_label and "tax paid" not in normalized_label:
            return False  # tax expense in cash_flow should not map to P&L tax
        if table_type == "balance_sheet" and (
            "tax expense" in normalized_label or "tax expenses" in normalized_label or "deferred tax" in normalized_label
        ):
            return False  # tax expense/deferred tax in balance_sheet should not map to P&L tax
    if canonical_section == "balance_sheet" and canonical_field in {"total_assets", "total_liabilities", "net_worth", "equity_share_capital", "reserves"}:
        if table_type in {"profit_and_loss", "eps", "dividend", "shareholding_pattern", "corporate_actions"}:
            return False
    if canonical_section == "cash_flow" and canonical_field == "tax_paid":
        if table_type in {"profit_and_loss", "balance_sheet", "share_capital", "eps", "dividend", "shareholding_pattern", "corporate_actions"}:
            return False

    return True


# Exact/approved aliases for high-risk fields — these get precedence over fuzzy matches
_EXACT_ALIASES: Dict[str, Dict[str, List[str]]] = {
    "profit_and_loss": {
        "revenue": ["revenue", "total revenue", "revenue from operations", "income from operations", "total operating revenue"],
        "pat": [
            "profit for the year", "profit after tax", "profit after taxation", "profit for the period", "pat",
            "net profit loss after taxation", "net profit/(loss) after taxation", "net profit loss after tax",
            "a cash flow from operating activities net profit loss after taxation",
            "a. cash flow from operating activities net profit/(loss) after taxation",
            "net profit 5 6 8 9", "net profit 5-6-8-9",
            # Roman numeral prefixed P&L labels (common in Indian financial statements)
            "ix profit for the year vii viii", "vii profit for the year v vi", "xi profit for the year ix x",
            "profit for the year a", "profit for the year vii viii", "profit for the year v vi",
            # Datapatterns variants
            "vii profit loss for the period", "vii profit loss for the period",
            "add profit after tax", "profit after tax for the year", "profit after taxation rs in crores",
        ],
        "pbt": ["profit before tax", "profit before taxation", "net profit before tax"],
        "tax": [
            "total tax expense", "tax expense", "income tax expense", "current tax",
            # Negative exact aliases for tax rows that should NOT map to P&L tax
            # These are added to ensure they don't get fuzzy-matched to profit_and_loss.tax
        ],
    },
    "balance_sheet": {
        "total_assets": ["total assets"],
        "total_liabilities": ["total liabilities"],
        "net_worth": ["total equity", "net worth", "shareholders funds", "shareholders equity", "equity attributable to owners"],
        "equity_share_capital": ["equity share capital", "paid up capital", "paid-up capital", "issued subscribed and paid up equity shares"],
        "reserves": ["other equity", "reserves and surplus", "reserves"],
    },
    "cash_flow": {
        "tax_paid": [
            "income taxes paid", "taxes paid", "tax paid",
            "direct taxes paid net of funds",
            "tax adjustment", "tax adjustments",
        ],
        "cfo": ["net cash generated from operating activities", "net cash from operating activities", "operating cash flow"],
        "pat": [
            "a cash flow from operating activities net profit loss after taxation",
            "a. cash flow from operating activities net profit/(loss) after taxation",
            "net profit loss after taxation",
            "net profit/(loss) after taxation",
            "net profit loss after tax",
            "profit after tax",
            "profit after taxation",
        ],
    },
    "share_data": {
        "shares_outstanding": ["number of equity shares outstanding", "issued subscribed and paid up equity shares", "issued subscribed and fully paid up equity shares"],
        "weighted_avg_shares": ["weighted average number of equity shares", "weighted average shares outstanding"],
        "diluted_shares": ["weighted average number of diluted equity shares", "number of shares used for diluted eps"],
        "face_value": ["face value", "nominal value", "nominal value of equity shares", "face value of equity shares"],
    },
}


def _is_exact_alias(normalized_label: str, canonical_section: str, canonical_field: str) -> bool:
    """Check if the label exactly matches an approved exact alias."""
    exact_list = _EXACT_ALIASES.get(canonical_section, {}).get(canonical_field, [])
    return normalized_label in exact_list


def _resolve_ambiguity(matches: List[MappingMatch], normalized_label: str, table_type: str) -> List[MappingMatch]:
    """
    Resolve ambiguous matches where multiple fields have the same top score.
    Tiebreaker rules:
    1. Exact alias match wins over fuzzy match
    2. Primary table context wins (e.g., cash_flow.cfo in cash_flow table_type > profit_and_loss.pat in cash_flow)
    3. If still tied, return empty (ambiguity fail-safe: reject rather than guess)
    """
    if not matches:
        return []

    top_score = matches[0].score
    top_matches = [m for m in matches if m.score == top_score]

    # If only one match at top score, no ambiguity
    if len(top_matches) == 1:
        return top_matches

    # Tiebreaker 1: Exact alias match wins
    exact_matches = [m for m in top_matches if _is_exact_alias(normalized_label, m.canonical_section, m.canonical_field)]
    if len(exact_matches) == 1:
        return exact_matches
    if len(exact_matches) > 1:
        # Multiple exact matches — ambiguous
        return []

    # Tiebreaker 2: Primary table context (prefer field's native section for the table type)
    # E.g., for cash_flow table_type, prefer cash_flow section fields
    native_section = {
        "profit_and_loss": "profit_and_loss",
        "balance_sheet": "balance_sheet",
        "cash_flow": "cash_flow",
        "share_capital": "share_data",
        "eps": "share_data",
        "dividend": "corporate_actions",
        "corporate_actions": "corporate_actions",
        "shareholding_pattern": "shareholding_pattern",
        "borrowings": "balance_sheet",
        "fixed_assets": "balance_sheet",
        "revenue": "profit_and_loss",
        "tax": "profit_and_loss",
        "statement_of_changes_in_equity": "balance_sheet",
    }.get(table_type, table_type)

    native_matches = [m for m in top_matches if m.canonical_section == native_section]
    if len(native_matches) == 1:
        return native_matches
    if len(native_matches) > 1:
        # Still ambiguous within native section
        return []

    # Ambiguity fail-safe: reject rather than guess
    return []


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

            # Track if this was an exact alias match for tiebreaker
            is_exact = _is_exact_alias(normalized_label, section_name, field_name)
            matches.append(
                MappingMatch(
                    canonical_section=section_name,
                    canonical_field=field_name,
                    score=best_alias_score + (10 if is_exact else 0),  # Boost exact matches
                    confidence=_confidence_from_score(best_alias_score + (10 if is_exact else 0)),
                    reason=f"alias_match:{field_name}{':exact' if is_exact else ''}",
                )
            )

    matches.sort(key=lambda item: (-item.score, item.canonical_section, item.canonical_field))
    if not matches:
        return []

    # Apply ambiguity resolution
    resolved = _resolve_ambiguity(matches, normalized_label, table_type)
    return resolved


def mapping_registry_snapshot() -> Dict[str, Dict[str, Dict[str, object]]]:
    return FIELD_MAPPINGS
