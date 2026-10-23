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
)
# NOT source_chunk: the chunk is the whole neighbouring statement text, so a keyword anywhere in it ("repayment of borrowings") used to label every other line of the
# chunk ("Dividend paid" -> debt_repaid). A capital-allocation item is classified from its own fields only.

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

_DEPLOYMENT_ELIGIBILITY = {
    "deployment": "ELIGIBLE_DEPLOYMENT",
    "distribution": "ELIGIBLE_DISTRIBUTION",
    "deleveraging": "ELIGIBLE_DELEVERAGING",
    "capital_source": "INELIGIBLE_CAPITAL_SOURCE",
    "balance_stock": "INELIGIBLE_BALANCE_STOCK",
    "disposal": "INELIGIBLE_DISPOSAL_PROCEEDS",
    "announced": "INELIGIBLE_ANNOUNCED_NOT_DEPLOYED",
    "operating_expense": "INELIGIBLE_OPERATING_EXPENSE",
    "ambiguous": "ELIGIBILITY_AMBIGUOUS",
}


_ASSET_SPEND_CATEGORIES = frozenset({"organic_capex", "capex", "maintenance_capex", "capacity_expansion"})
_BUSINESS_ACQUISITION_CATEGORIES = frozenset({"acquisition", "acquisition_integration", "strategic_investment", "merger", "business_acquisition"})
_ASSET_ACQUISITION = re.compile(r"\b(?:acquisition|acquire[sd]?|purchase|purchased) of (?:the )?(?:land|building|plant|property|equipment|machinery|premises|office|factory|facility|facilities|fixed assets?)\b")


def resolve_economic_role(item: Dict[str, Any]) -> Dict[str, str]:
    """Resolve economic role from explicit, high-signal source semantics.

    This is deliberately conservative: a unit-confirmed amount is not enough
    to make an event a deployment.  Unclear stock/flow or source/use semantics
    remain qualitative and are excluded from weighted totals.
    """
    text = _combined_text(item)
    # Explicit identity is the only authority for SAME_ECONOMIC_FLOW.
    if item.get("economic_flow_id") or item.get("transaction_id") or item.get("deal_id"):
        return {"economic_role": "ECONOMIC_ROLE_AMBIGUOUS", "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["ambiguous"], "economic_flow_relation": "SAME_ECONOMIC_FLOW", "economic_flow_authority": "EXPLICIT_STRUCTURED_ID"}
    category = _normalize_text(item.get("canonical_category") or item.get("category"))
    group = _normalize_text(item.get("capital_allocation_group"))
    if any(x in text for x in ("sanctioned", "sanctioned facility", "approved limit", "available facility", "credit line")):
        return {"economic_role": "ANNOUNCED_OR_SANCTIONED_NOT_DEPLOYED", "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["announced"]}
    if re.search(r"\bbonus (?:equity )?(?:shares?|issue)\b|\bissued? (?:and allotted )?bonus\b", text):
        # bonus shares capitalise reserves: no cash comes in, so the event is not a capital source, a deployment or a distribution
        return {"economic_role": "NON_CASH_CAPITALISATION", "deployment_eligibility": "INELIGIBLE_NON_CASH_EVENT"}
    if any(x in text for x in ("proceeds from", "proceeds of", "equity issuance", "shares issued", "loan availed", "debt raised", "borrowings received", "fresh issue")) or group == "financing_actions":
        if any(x in text for x in ("repaid", "repayment", "debt repayment", "loan repayment", "lease liability payment")):
            return {"economic_role": "BALANCE_SHEET_DELEVERAGING", "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["deleveraging"]}
        return {"economic_role": "CAPITAL_SOURCE", "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["capital_source"]}
    if any(x in text for x in ("repaid", "repayment", "debt repayment", "loan repayment", "lease liability payment")):
        result = {"economic_role": "BALANCE_SHEET_DELEVERAGING", "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["deleveraging"]}
        if "sale consideration" in text and "against loan" in text:
            result.update({"economic_flow_relation": "LINKED_BUT_DISTINCT_FLOW", "economic_flow_authority": "EXPLICIT_SOURCE_STATEMENT"})
        return result
    if any(x in text for x in ("sale of", "sold", "divested", "disposal proceeds", "sale consideration received")):
        return {"economic_role": "DISPOSAL_PROCEEDS", "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["disposal"]}
    if any(x in text for x in ("balance", "carried at cost", "outstanding balance", "closing balance", "aggregate investments", "rental deposit")):
        return {"economic_role": "BALANCE_SHEET_STOCK", "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["balance_stock"]}
    if any(x in text for x in ("dividend paid", "dividend declared", "dividend")):
        return {"economic_role": "DISTRIBUTION_DIVIDEND", "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["distribution"]}
    if any(x in text for x in ("buyback", "buy back", "repurchase of shares", "share repurchase")):
        return {"economic_role": "DISTRIBUTION_BUYBACK", "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["distribution"]}
    if any(x in text for x in ("operating expense", "expense incurred", "research expense", "r&d expense")):
        return {"economic_role": "OPERATING_EXPENSE", "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["operating_expense"]}
    if any(x in text for x in ("purchase consideration", "acquired for", "acquisition", "capital expenditure", "capex", "invested during the year", "capital contribution", "paid for")):
        role = "DEPLOYMENT_ACQUISITION" if any(x in text for x in ("acquisition", "purchase consideration", "acquired for")) else "DEPLOYMENT_ORGANIC_CAPEX"
        # Spending on a physical asset (land, a building, plant, equipment) is capital expenditure, not the acquisition of a business: the wording "acquisition of land" does not make
        # it M&A, and an item whose category says organic capex cannot carry an acquisition role.
        if role == "DEPLOYMENT_ACQUISITION" and category not in _BUSINESS_ACQUISITION_CATEGORIES and (category in _ASSET_SPEND_CATEGORIES or _ASSET_ACQUISITION.search(text)):
            role = "DEPLOYMENT_ORGANIC_CAPEX"
        return {"economic_role": role, "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["deployment"]}
    return {"economic_role": "ECONOMIC_ROLE_AMBIGUOUS", "deployment_eligibility": _DEPLOYMENT_ELIGIBILITY["ambiguous"], "economic_flow_relation": "UNKNOWN_FLOW_RELATION", "economic_flow_authority": "NONE"}


def _normalize_text(value: Any) -> str:
    return " ".join(_INLINE_SPACE_RE.sub(" ", str(value or "").lower()).split())


def _contains_phrase(text: str, phrase: str) -> bool:
    """Whole-word phrase match: a normalised keyword such as 'r d' (R&D) must not be found inside 'order dated'."""
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


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
                if normalized_keyword and _contains_phrase(text, normalized_keyword):
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


_RE_MATCHED_KEYWORD = re.compile(r"Matched taxonomy keyword '([^']+)'")


def verify_stored_classification(item: Dict[str, Any]) -> Dict[str, Any]:
    """Is the label a stored item carries supported by the item's own wording? Older runs classified against the whole source chunk, so the recorded 'matched keyword' can be a
    different line's. Returns {'status': 'supported'|'refreshed'|'unverified'|'untested', 'classification': <fresh taxonomy result or None>}. Nothing is invented: 'refreshed' is
    the current taxonomy's own result for the item's own fields; 'unverified' means the stored label is contaminated and the taxonomy has no opinion either."""
    own = {"action": item.get("action") or item.get("value"), "category": item.get("category"), "purpose": item.get("purpose"), "status": item.get("status"),
           "counterparty": item.get("counterparty"), "relationship": item.get("relationship")}
    text = _combined_text(own)
    m = _RE_MATCHED_KEYWORD.search(str(item.get("reasoning") or ""))
    if m:
        if _contains_phrase(text, _normalize_text(m.group(1))):
            return {"status": "supported", "classification": None}
    else:
        # no recorded keyword to check: the taxonomy itself decides whether ANY keyword of the stored category appears in the item's own wording
        stored = str(item.get("canonical_category") or "")
        if not stored:
            return {"status": "untested", "classification": None}
        entry_keywords = [_normalize_text(k) for e in CapitalAllocationTaxonomy().categories if e.get("canonical_category") == stored for k in e.get("keywords", [])]
        if not entry_keywords or any(k and _contains_phrase(text, k) for k in entry_keywords):
            return {"status": "supported" if entry_keywords else "untested", "classification": None}
    fresh = CapitalAllocationTaxonomy().classify(own)
    return {"status": "unverified" if fresh.get("canonical_category") in (None, "", "uncertain") else "refreshed", "classification": fresh}


_NOT_AN_ALLOCATION_GROUPS = {"corporate_actions_non_cash_or_admin", "ownership_transfer_non_company_cashflow", "accounting_or_disclosure_only"}
_LABEL_DERIVED_FIELDS = ("canonical_category", "capital_allocation_group", "cash_flow_effect", "balance_sheet_effect", "is_true_capital_deployment", "is_shareholder_return",
                         "is_financing_action", "is_corporate_action", "is_related_party")


def apply_label_verdict(item: Dict[str, Any]) -> Dict[str, Any]:
    """Stored labels from older runs were matched against the whole source chunk, so a label can belong to a neighbouring line ('Proceeds from borrowings' filed as
    debt_repaid, 'Dividend paid' as capex). The taxonomy decides whether the stored label is supported by the item's OWN wording:
    - supported / untested: unchanged;
    - the taxonomy classifies the item's own text with a keyword that appears IN that text: label, cash-flow effect, balance-sheet effect and role flags are all replaced
      (the stored label is kept in `classification_stored_label`);
    - otherwise the label is quarantined as 'uncertain' (role flags cleared), never guessed.
    Both outcomes are stamped in `classification_status`. Every consumer of a stored capital-allocation item (outcomes, timeline, CIM, PCIM) applies this one rule."""
    verdict = verify_stored_classification(item)
    if verdict["status"] in ("supported", "untested"):
        return item
    stored = {field: item.get(field) for field in _LABEL_DERIVED_FIELDS}
    fresh = verdict["classification"] or {}
    # Treasury sub-categories are synonyms (a debt mutual fund placement is "mutual_fund_investment" or "cash_management" with the same group and effects): a stored one the keywords do
    # not literally support is not wrong. Every other group's sub-categories name different events (R&D vs an equity subscription, capex vs an acquisition) and are replaced.
    if stored["capital_allocation_group"] == "treasury_actions" and all(stored.get(f) == fresh.get(f) for f in ("capital_allocation_group", "cash_flow_effect", "balance_sheet_effect")):
        return item
    keyword = _RE_MATCHED_KEYWORD.search(str(fresh.get("reasoning") or ""))
    action_text = _normalize_text(" ".join(str(item.get(k) or "") for k in ("action", "value", "purpose", "category", "status")))
    if fresh.get("capital_allocation_group") in _NOT_AN_ALLOCATION_GROUPS or (verdict["status"] == "refreshed" and keyword and _contains_phrase(action_text, _normalize_text(keyword.group(1)))):
        replaced = {field: fresh.get(field) for field in _LABEL_DERIVED_FIELDS if field in fresh}
        return {**item, **replaced, "reasoning": fresh.get("reasoning"), "classification_status": "reclassified_from_own_text", "classification_stored_label": stored}
    uncertain = CapitalAllocationTaxonomy()._uncertain(item)
    return {**item, **{field: uncertain.get(field) for field in _LABEL_DERIVED_FIELDS}, "reasoning": uncertain.get("reasoning"), "classification_status": "quarantined_unsupported",
            "classification_stored_label": stored}


def normalize_capital_allocation_item(item: Dict[str, Any]) -> Dict[str, Any]:
    taxonomy = CapitalAllocationTaxonomy()
    normalized = dict(item)
    classification = taxonomy.classify(item)
    normalized.update(classification)
    normalized["currency"] = item.get("currency") or _extract_currency(item.get("amount"))
    normalized["evidence_ids"] = list(item.get("evidence_ids") or [])
    normalized.update(resolve_economic_role(normalized))
    normalized["economic_flow_relation"] = item.get("economic_flow_relation") or normalized.get("economic_flow_relation") or "DISTINCT_FLOW"
    normalized["economic_flow_authority"] = item.get("economic_flow_authority") or normalized.get("economic_flow_authority") or "NONE"
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


# ── Event nature: one vocabulary for what a recorded capital event IS, shared by answer generation (the prompt's typed evidence) and answer verification (G5 event check) ──
ACQ_TYPE = re.compile(r"acquisition|business combination|merger|amalgamat|takeover|buy-?out|acquired\s+(?:\d{2,3}(?:\.\d+)?\s*%|control|the business|all)|wholly[- ]owned|controlling", re.I)
MERGER_TYPE = re.compile(r"merger|amalgamat", re.I)
MINOR_TYPE = re.compile(r"minority|equity investment|stake|subscri|investment in|preference shares?|\d+\s+equity shares", re.I)
PENDING_STATUS = re.compile(r"subject to|pending|proposed|signed|agreement to|expected to|yet to be|announced", re.I)
DONE_STATUS = re.compile(r"\bcompleted\b|\beffective\b|\bconsummated\b|\bclosed\b|\bacquired\b|\bwas acquired\b", re.I)

_NATURE_WORDING = {
    "minority_or_subscription": (["invested in", "subscribed to shares of", "took a minority stake in", "equity investment in"], ["acquisition", "takeover", "acquired the company", "bought the company"]),
    "acquisition": (["acquired", "acquisition of"], []),
    "merger_or_amalgamation": (["merged with", "amalgamation of", "the scheme took effect"], ["acquired the company"]),
    "other": (["use the record's own words"], ["acquisition", "takeover", "merger"]),
}


def event_nature(category: str = "", value: str = "", status: str = "") -> Dict[str, Any]:
    """What a recorded capital event is, from its typed category first and its source wording second: 'minority_or_subscription', 'acquisition', 'merger_or_amalgamation' or
    'other'; whether it is completed, pending or unspecified; and the wording that keeps its meaning. A share subscription is never an acquisition; a pending deal is never completed."""
    cat, val, st = str(category or ""), str(value or ""), str(status or "")
    if ACQ_TYPE.search(cat):
        nature = "merger_or_amalgamation" if MERGER_TYPE.search(cat) else "acquisition"
    elif MINOR_TYPE.search(cat + " " + val):
        nature = "minority_or_subscription"
    elif ACQ_TYPE.search(val):
        nature = "merger_or_amalgamation" if MERGER_TYPE.search(val) else "acquisition"
    else:
        nature = "other"
    pending, done = bool(PENDING_STATUS.search(st + " " + val)), bool(DONE_STATUS.search(st + " " + val))
    completion = "pending" if pending and not re.search(r"\bcompleted\b|\bconsummated\b|\beffective\b", st + " " + val, re.I) else ("completed" if done else "unspecified")
    allowed, forbidden = _NATURE_WORDING[nature]
    if completion == "pending" and nature in ("acquisition", "merger_or_amalgamation"):
        allowed = ["agreed to acquire", "signed an agreement to acquire", "proposed acquisition"] if nature == "acquisition" else ["proposed merger", "scheme awaiting approval"]
    forbidden = list(forbidden) + (["completed", "closed", "acquired (past tense)"] if completion == "pending" else [])
    return {"nature": nature, "completion": completion, "allowed_wording": list(allowed), "forbidden_wording": forbidden}
