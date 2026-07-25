from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


_TEXT_FIELDS = (
    "action",
    "category",
    "purpose",
    "status",
    "counterparty",
    "relationship",
    "source_chunk",
)

_ALLOWED_CASH_FLOW_EFFECTS = {
    "company_cash_outflow",
    "company_cash_inflow",
    "non_company_cashflow",
    "non_cash",
    "cash_reallocation",
    "unknown",
}

_GROUP_FLAGS = {
    "true_capital_deployment": {
        "is_true_capital_deployment": True,
        "is_shareholder_return": False,
        "is_financing_action": False,
        "is_corporate_action": False,
        "is_related_party": False,
    },
    "shareholder_returns": {
        "is_true_capital_deployment": False,
        "is_shareholder_return": True,
        "is_financing_action": False,
        "is_corporate_action": False,
        "is_related_party": False,
    },
    "financing_actions": {
        "is_true_capital_deployment": False,
        "is_shareholder_return": False,
        "is_financing_action": True,
        "is_corporate_action": False,
        "is_related_party": False,
    },
    "treasury_actions": {
        "is_true_capital_deployment": False,
        "is_shareholder_return": False,
        "is_financing_action": False,
        "is_corporate_action": False,
        "is_related_party": False,
    },
    "corporate_actions_non_cash_or_admin": {
        "is_true_capital_deployment": False,
        "is_shareholder_return": False,
        "is_financing_action": False,
        "is_corporate_action": True,
        "is_related_party": False,
    },
    "ownership_transfer_non_company_cashflow": {
        "is_true_capital_deployment": False,
        "is_shareholder_return": False,
        "is_financing_action": False,
        "is_corporate_action": True,
        "is_related_party": False,
    },
    "related_party_capital_flows": {
        "is_true_capital_deployment": False,
        "is_shareholder_return": False,
        "is_financing_action": False,
        "is_corporate_action": False,
        "is_related_party": True,
    },
    "accounting_or_disclosure_only": {
        "is_true_capital_deployment": False,
        "is_shareholder_return": False,
        "is_financing_action": False,
        "is_corporate_action": False,
        "is_related_party": False,
    },
    "uncertain": {
        "is_true_capital_deployment": False,
        "is_shareholder_return": False,
        "is_financing_action": False,
        "is_corporate_action": False,
        "is_related_party": False,
    },
}

_COMPANY_CASH_INFLOW_HINTS = (
    "company received proceeds",
    "proceeds to the company",
    "cash proceeds to the company",
    "fresh issue",
)

_INLINE_SPACE_RE = re.compile(r"[^a-z0-9]+")
_COMMON_CURRENCIES = {
    "₹": "INR",
    "rs": "INR",
    "inr": "INR",
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
}


def _normalize_text(value: Any) -> str:
    return " ".join(_INLINE_SPACE_RE.sub(" ", str(value or "").lower()).split())


def _combined_text(item: Dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (_normalize_text(item.get(field)) for field in _TEXT_FIELDS)
        if part
    )


def _extract_currency(amount: Any) -> Any:
    text = str(amount or "")
    if not text.strip():
        return None
    lowered = text.lower()
    for token, code in _COMMON_CURRENCIES.items():
        if token in lowered or token in text:
            return code
    return None


@lru_cache(maxsize=1)
def _taxonomy_payload() -> Dict[str, Any]:
    path = Path(__file__).resolve().parent.parent / "taxonomies" / "capital_allocation_taxonomy.json"
    return json.loads(path.read_text(encoding="utf-8"))


class CapitalAllocationTaxonomy:
    def __init__(self) -> None:
        payload = _taxonomy_payload()
        self.groups = payload.get("groups", {})
        self.categories = payload.get("categories", [])

    def classify(self, item: Dict[str, Any]) -> Dict[str, Any]:
        text = _combined_text(item)
        best_entry = None
        best_score: Tuple[int, int] = (-1, -1)
        best_keyword = ""

        for index, entry in enumerate(self.categories):
            for keyword in entry.get("keywords", []):
                normalized_keyword = _normalize_text(keyword)
                if normalized_keyword and normalized_keyword in text:
                    score = (len(normalized_keyword.split()), len(normalized_keyword))
                    if score > best_score:
                        best_entry = (index, entry)
                        best_score = score
                        best_keyword = keyword

        if best_entry is None:
            return self._uncertain(item)

        entry = best_entry[1]
        group = str(entry.get("capital_allocation_group") or "uncertain")
        defaults = self.groups.get(group, {})
        result = {
            "canonical_category": str(entry.get("canonical_category") or "uncertain"),
            "capital_allocation_group": group,
            "cash_flow_effect": str(entry.get("cash_flow_effect") or defaults.get("cash_flow_effect") or "unknown"),
            "balance_sheet_effect": str(
                entry.get("balance_sheet_effect") or defaults.get("balance_sheet_effect") or "unknown"
            ),
            "reasoning": f"Matched taxonomy keyword '{best_keyword}' to {entry.get('canonical_category')}.",
        }
        result.update(_GROUP_FLAGS.get(group, _GROUP_FLAGS["uncertain"]))

        if group == "ownership_transfer_non_company_cashflow" and any(hint in text for hint in _COMPANY_CASH_INFLOW_HINTS):
            result["cash_flow_effect"] = "company_cash_inflow"
            result["reasoning"] += " Company-level proceeds language was detected."

        if group == "related_party_capital_flows":
            result = self._specialize_related_party(result, text)

        if result["cash_flow_effect"] not in _ALLOWED_CASH_FLOW_EFFECTS:
            result["cash_flow_effect"] = "unknown"

        return result

    def _specialize_related_party(self, result: Dict[str, Any], text: str) -> Dict[str, Any]:
        category = result.get("canonical_category")
        if category == "related_party_repayment":
            if "to related party" in text:
                result["cash_flow_effect"] = "company_cash_outflow"
                result["balance_sheet_effect"] = "liability_reduction"
            else:
                result["cash_flow_effect"] = "company_cash_inflow"
                result["balance_sheet_effect"] = "asset_increase"
        elif category == "related_party_dividend":
            result["cash_flow_effect"] = "company_cash_inflow"
            result["balance_sheet_effect"] = "asset_increase"
        return result

    def _uncertain(self, item: Dict[str, Any]) -> Dict[str, Any]:
        action = item.get("action") or item.get("category") or "unknown item"
        return {
            "canonical_category": "uncertain",
            "capital_allocation_group": "uncertain",
            "cash_flow_effect": "unknown",
            "balance_sheet_effect": "unknown",
            "is_true_capital_deployment": False,
            "is_shareholder_return": False,
            "is_financing_action": False,
            "is_corporate_action": False,
            "is_related_party": False,
            "reasoning": f"No taxonomy match found for '{action}'.",
        }


def normalize_capital_allocation_item(item: Dict[str, Any]) -> Dict[str, Any]:
    taxonomy = CapitalAllocationTaxonomy()
    normalized = dict(item)
    classification = taxonomy.classify(item)
    normalized.update(classification)
    normalized["currency"] = item.get("currency") or _extract_currency(item.get("amount"))
    normalized["evidence_ids"] = list(item.get("evidence_ids") or [])
    normalized.pop("source_chunk", None)
    return normalized


def validate_capital_allocation_items(items: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    seen: set[Tuple[str, str, str, str]] = set()

    for index, item in enumerate(items, start=1):
        label = item.get("action") or item.get("value") or f"item_{index}"
        group = str(item.get("capital_allocation_group") or "")
        category = str(item.get("canonical_category") or "")
        cash_flow_effect = str(item.get("cash_flow_effect") or "")
        reasoning = str(item.get("reasoning") or "")

        if item.get("source_chunk"):
            errors.append(f"{label}: source_chunk must not appear in cleaned capital allocation output.")
        if not category:
            errors.append(f"{label}: canonical_category is required.")
        if not group:
            errors.append(f"{label}: capital_allocation_group is required.")
        if group == "true_capital_deployment" and category in {
            "offer_for_sale",
            "promoter_sale",
            "secondary_sale",
            "stake_sale_by_existing_shareholders",
            "share_split",
            "authorised_capital_change",
            "accounting_policy",
            "depreciation_policy",
            "impairment_policy",
            "fair_value_measurement",
            "actuarial_assumption",
            "contingent_liability_disclosure",
        }:
            errors.append(f"{label}: non-deployment item cannot be grouped as true_capital_deployment.")
        if group == "ownership_transfer_non_company_cashflow" and cash_flow_effect == "company_cash_inflow":
            if not any(hint in reasoning.lower() for hint in _COMPANY_CASH_INFLOW_HINTS):
                errors.append(f"{label}: ownership transfer cannot be marked company_cash_inflow without proceeds evidence.")
        if group == "accounting_or_disclosure_only" and item.get("is_true_capital_deployment"):
            errors.append(f"{label}: accounting/disclosure-only item cannot be true capital deployment.")

        if not item.get("amount"):
            warnings.append(f"{label}: amount missing.")
        if cash_flow_effect in {"", "unknown"}:
            warnings.append(f"{label}: cash_flow_effect unknown.")
        if category == "uncertain" or group == "uncertain":
            warnings.append(f"{label}: uncertain category.")
        if str(item.get("confidence") or "").lower() in {"", "low"}:
            warnings.append(f"{label}: low confidence.")

        key = (
            _normalize_text(item.get("action") or item.get("value")),
            category,
            str(item.get("amount") or ""),
            str(item.get("page") or ""),
        )
        if key in seen:
            warnings.append(f"{label}: duplicate-looking capital allocation item.")
        else:
            seen.add(key)

    return {
        "errors": list(dict.fromkeys(errors)),
        "warnings": list(dict.fromkeys(warnings)),
    }
