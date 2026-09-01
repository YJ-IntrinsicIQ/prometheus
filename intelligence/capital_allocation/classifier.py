from __future__ import annotations

from typing import Any, Dict, Optional


# ── Allocation type mapping ─────────────────────────────────────────────────────

# Source category strings → canonical allocation type (first match wins)
_SOURCE_CATEGORY_MAP: list[tuple[str, str]] = [
    # Acquisitions
    ("acquisition", "ACQUISITION"),
    ("merger", "ACQUISITION"),
    ("business combination", "ACQUISITION"),
    # Buybacks
    ("buyback", "BUYBACK"),
    ("share repurchase", "BUYBACK"),
    ("treasury share", "BUYBACK"),
    # Dividends
    ("dividend", "DIVIDEND"),
    # Debt repayment
    ("debt repayment", "DEBT_REPAYMENT"),
    ("loan repayment", "DEBT_REPAYMENT"),
    ("debt reduction", "DEBT_REPAYMENT"),
    # Digital / Tech
    ("digital", "DIGITAL_OR_TECH_INVESTMENT"),
    ("platform", "DIGITAL_OR_TECH_INVESTMENT"),
    ("technology", "DIGITAL_OR_TECH_INVESTMENT"),
    ("software", "DIGITAL_OR_TECH_INVESTMENT"),
    ("intangible", "DIGITAL_OR_TECH_INVESTMENT"),
    # R&D
    ("r&d", "R_AND_D"),
    ("research", "R_AND_D"),
    ("product development", "R_AND_D"),
    ("pipeline", "R_AND_D"),
    # Capacity expansion
    ("capacity", "CAPACITY_EXPANSION"),
    ("capacity expansion", "CAPACITY_EXPANSION"),
    ("facility", "CAPACITY_EXPANSION"),
    ("plant", "CAPACITY_EXPANSION"),
    ("manufacturing", "CAPACITY_EXPANSION"),
    # Organic capex (catch-all for ppe/cwip)
    ("organic_capex", "ORGANIC_CAPEX"),
    ("capex", "ORGANIC_CAPEX"),
    ("capital expenditure", "ORGANIC_CAPEX"),
    ("ppe", "ORGANIC_CAPEX"),
    ("property", "ORGANIC_CAPEX"),
    # New market / product expansion
    ("new market", "NEW_MARKET_OR_PRODUCT"),
    ("geographic expansion", "NEW_MARKET_OR_PRODUCT"),
    ("market entry", "NEW_MARKET_OR_PRODUCT"),
    ("product launch", "NEW_MARKET_OR_PRODUCT"),
    # Working capital
    ("working capital", "WORKING_CAPITAL"),
    ("receivables", "WORKING_CAPITAL"),
    ("inventory", "WORKING_CAPITAL"),
    # Subsidiary disposal — not a use of capital but a return; exclude via materiality
]


def classify_allocation_type(record: Dict[str, Any]) -> str:
    """
    Map a source allocation record to a canonical Gold allocation type.

    Source category is checked first (high confidence); name/purpose keywords
    are used only as fallback so that e.g. 'payment for acquisition of PPE'
    (category: capex) is not misclassified as ACQUISITION.
    """
    category = (record.get("allocation_category") or "").lower()
    event_category = (record.get("category") or "").lower()

    # Category-first: if the source category unambiguously maps, use it
    _CATEGORY_OVERRIDES = {
        "capex spending": "ORGANIC_CAPEX",
        "capital expenditure": "ORGANIC_CAPEX",
        "r&d spending": "R_AND_D",
        "research and development": "R_AND_D",
        "organic_capex": "ORGANIC_CAPEX",
        "dividend": "DIVIDEND",
        "buyback": "BUYBACK",
        "buyback (tender offer)": "BUYBACK",
        "share repurchase": "BUYBACK",
        "debt repayment": "DEBT_REPAYMENT",
        "debt repayment / settlement": "DEBT_REPAYMENT",
        "subsidiary acquisition": "ACQUISITION",
        "subsidiary acquisition/incorporation": "ACQUISITION",
        "subsidiary incorporation/acquisition": "ACQUISITION",
        "investment in associate": "ACQUISITION",
        "acquisition": "ACQUISITION",
    }
    for src_cat in (event_category, category):
        if src_cat in _CATEGORY_OVERRIDES:
            return _CATEGORY_OVERRIDES[src_cat]

    # Fallback: keyword scan on name and purpose only
    name = (record.get("allocation_name") or record.get("value") or "").lower()
    purpose = (record.get("inferred_business_purpose") or "").lower()
    full_text = " ".join([name, purpose])

    for keyword, alloc_type in _SOURCE_CATEGORY_MAP:
        if keyword in full_text:
            return alloc_type

    return "OTHER"


def extract_management_rationale(record: Dict[str, Any]) -> str:
    """Extract why management said capital was allocated."""
    rationale = (record.get("inferred_business_purpose") or "").strip()
    if rationale and len(rationale) > 15:
        return rationale
    name = (record.get("value") or record.get("allocation_name") or "").strip()
    if name:
        return name
    return ""


# ── Materiality filter ──────────────────────────────────────────────────────────

# Minimum absolute amounts to qualify as material (INR crore equivalents)
_MATERIAL_AMOUNT_THRESHOLD_CR = 10.0  # ₹10 Cr minimum

# Allocation types that are material regardless of amount (when amount unknown)
_ALWAYS_MATERIAL_TYPES = {"ACQUISITION", "BUYBACK", "CAPACITY_EXPANSION", "DIGITAL_OR_TECH_INVESTMENT"}

# Allocation types that are capital-structure decisions, not operating reinvestment
_CAPITAL_RETURN_TYPES = {"DIVIDEND", "BUYBACK", "DEBT_REPAYMENT"}

# Signals of immateriality
_IMMATERIAL_CATEGORIES = {
    "deposits / loans (unsecured)",
    "guarantee/contingent liability",
    "equity issuance (employee stock grant)",
    "collateral / security for borrowings",
    "intercompany borrowing / advance",
}

_IMMATERIAL_KEYWORDS = {
    "emd deposit",
    "rental deposit",
    "rsu grant",
    "esop",
    "esps",
    "rsu plan",
    "pledged assets",
    "dividend received",  # income, not a capital outflow
    "loan repayment received",  # inflow
    "proceeds from sale",  # inflow / divestiture
}


def is_material_allocation(record: Dict[str, Any], alloc_type: str) -> bool:
    """Return True if this allocation is worth tracking in the Gold layer."""
    category = (record.get("category") or record.get("allocation_category") or "").lower()
    name = (record.get("value") or record.get("allocation_name") or "").lower()

    # Exclude known immaterial categories
    if category in _IMMATERIAL_CATEGORIES:
        return False

    # Exclude known immaterial keywords
    if any(kw in name for kw in _IMMATERIAL_KEYWORDS):
        return False

    # Always track acquisitions, buybacks, and platform investments
    if alloc_type in _ALWAYS_MATERIAL_TYPES:
        return True

    # Quantified allocations: apply threshold
    amount = _parse_amount_crore(record)
    if amount is not None:
        return amount >= _MATERIAL_AMOUNT_THRESHOLD_CR

    # Unquantified: include if category is substantive
    if alloc_type in {"ORGANIC_CAPEX", "CAPACITY_EXPANSION", "R_AND_D", "DIVIDEND",
                      "NEW_MARKET_OR_PRODUCT", "WORKING_CAPITAL"}:
        return True

    return False


def _parse_amount_crore(record: Dict[str, Any]) -> Optional[float]:
    """
    Parse a numeric amount in INR crore from a record.

    Only trusts numeric (int/float) fields — string amounts from raw timeline
    events are ambiguous (mixed units, Indian number format) and are not parsed.
    """
    for field in ("amount", "capital_amount", "amount_crore"):
        v = record.get(field)
        if isinstance(v, (int, float)) and v != 0:
            return abs(float(v))
    return None
