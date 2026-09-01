from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# ── Evidence hierarchy ─────────────────────────────────────────────────────────

_HIERARCHY = [
    "ALLOCATION_IDENTIFIED",
    "EXECUTION_VISIBLE",
    "OPERATING_OUTCOME_VISIBLE",
    "FINANCIAL_OUTCOME_VISIBLE",
    "RETURN_EVIDENCE_VISIBLE",
]


def resolve_evidence_level(record: Dict[str, Any]) -> str:
    """
    Assess the highest supported evidence level for a capital allocation.

    Does NOT assume higher levels from lower ones — each level requires
    its own supporting text in the record.
    """
    operating = (
        record.get("operating_outcome") or
        record.get("operating_evidence") or ""
    ).strip().lower()
    financial = (
        record.get("financial_outcome") or
        record.get("financial_evidence") or ""
    ).strip().lower()
    exec_status = (record.get("execution_status") or record.get("deployment_status") or "").lower()
    balance_sheet = (record.get("balance_sheet_outcome") or "").strip().lower()

    # RETURN_EVIDENCE_VISIBLE: explicit return metric (ROIC, ROCE, IRR, ROE attributable)
    return_signals = ("roic", "roce", "irr", "return on capital", "return on equity",
                      "return on investment", "incremental return")
    if any(s in financial for s in return_signals) or any(s in balance_sheet for s in return_signals):
        return "RETURN_EVIDENCE_VISIBLE"

    # FINANCIAL_OUTCOME_VISIBLE: revenue, PAT, margin, FCF mentions with numbers
    financial_metric_signals = (
        "revenue", "pat", "profit", "margin", "cash flow", "fcf",
        "ebitda", "interest cost", "eps", "earnings"
    )
    has_financial_numbers = any(
        s in financial for s in financial_metric_signals
    ) and any(c.isdigit() for c in financial)
    if has_financial_numbers:
        return "FINANCIAL_OUTCOME_VISIBLE"

    # OPERATING_OUTCOME_VISIBLE: commissioning, utilisation, ramp, operational
    operating_signals = (
        "commission", "operational", "utiliz", "ramp", "deployed", "launched",
        "integrated", "completed", "opened", "acquired"
    )
    if any(s in operating for s in operating_signals):
        return "OPERATING_OUTCOME_VISIBLE"
    # Also check balance sheet for asset creation
    if any(s in balance_sheet for s in ("net_worth", "total_assets", "asset")):
        return "OPERATING_OUTCOME_VISIBLE"

    # EXECUTION_VISIBLE: deployment confirmed but no operational traction yet
    execution_signals = ("deployed", "completed", "acquired", "paid", "spent", "invested")
    if exec_status in ("deployed", "completed", "invested"):
        return "EXECUTION_VISIBLE"
    if any(s in operating for s in execution_signals):
        return "EXECUTION_VISIBLE"

    # Minimum: we know an allocation was made
    return "ALLOCATION_IDENTIFIED"


# ── Return status ──────────────────────────────────────────────────────────────

# Allocation types that use capital-return logic (not reinvestment return logic)
_CAPITAL_RETURN_TYPES = {"DIVIDEND", "DEBT_REPAYMENT"}

_NEGATIVE_OUTCOME_SIGNALS = (
    "impairment", "write-off", "write-down", "goodwill impaired",
    "loss on acquisition", "failed", "discontinued", "destructive",
    "margin declined", "returns weakened", "loss-making"
)

_POSITIVE_OUTCOME_SIGNALS = (
    "revenue grew", "revenue growth", "profit grew", "margin improved",
    "utilisation reached", "ebitda improved", "cash generation improved",
    "returns improved", "roic", "roce improved", "positive return"
)

_PARTIAL_SIGNALS = (
    "partial", "mixed", "some improvement", "partly", "not fully",
    "not yet", "limited", "modest"
)


def resolve_return_status(
    record: Dict[str, Any],
    allocation_type: str,
    evidence_level: str,
) -> str:
    """
    Assess investor-relevant return status.

    Capital-return types (DIVIDEND, DEBT_REPAYMENT) use dedicated logic.
    Reinvestment types use evidence-based hierarchy.
    """
    financial = (
        record.get("financial_outcome") or
        record.get("financial_evidence") or ""
    ).strip().lower()
    operating = (
        record.get("operating_outcome") or
        record.get("operating_evidence") or ""
    ).strip().lower()
    causal = (record.get("causal_confidence") or "").lower()
    outcome = (record.get("outcome_status") or "").lower()

    combined = financial + " " + operating

    # DIVIDEND: NOT_APPLICABLE by default; flag if clearly unsustainable
    if allocation_type == "DIVIDEND":
        if "fcf" in combined or "surplus" in combined or "payout" in combined:
            return "NOT_APPLICABLE"
        return "NOT_APPLICABLE"

    # DEBT_REPAYMENT: positive if leverage fell
    if allocation_type == "DEBT_REPAYMENT":
        if any(s in combined for s in ("leverage fell", "debt reduced", "interest burden", "resilience improved")):
            return "EARLY_POSITIVE_SIGNAL"
        return "NOT_APPLICABLE"

    # BUYBACK: NOT_APPLICABLE if valuation context not available
    if allocation_type == "BUYBACK":
        return "NOT_APPLICABLE"

    # Destructive / negative
    if any(s in combined for s in _NEGATIVE_OUTCOME_SIGNALS):
        return "DESTRUCTIVE"

    # Only below FINANCIAL_OUTCOME_VISIBLE → UNPROVEN
    if evidence_level in ("ALLOCATION_IDENTIFIED", "EXECUTION_VISIBLE"):
        return "UNPROVEN"

    # RETURN_EVIDENCE_VISIBLE with positive signals
    if evidence_level == "RETURN_EVIDENCE_VISIBLE":
        if any(s in combined for s in _POSITIVE_OUTCOME_SIGNALS):
            if any(s in combined for s in _PARTIAL_SIGNALS):
                return "MIXED"
            if causal in ("high", "medium"):
                return "PROVEN_POSITIVE"
            return "EARLY_POSITIVE_SIGNAL"
        return "MIXED"

    # FINANCIAL_OUTCOME_VISIBLE: check causality
    if evidence_level == "FINANCIAL_OUTCOME_VISIBLE":
        if causal in ("high",) and any(s in combined for s in _POSITIVE_OUTCOME_SIGNALS):
            return "EARLY_POSITIVE_SIGNAL"
        if causal == "low" or any(s in combined for s in _PARTIAL_SIGNALS):
            return "MIXED"
        if any(s in combined for s in _POSITIVE_OUTCOME_SIGNALS):
            return "EARLY_POSITIVE_SIGNAL"
        return "UNPROVEN"

    # OPERATING_OUTCOME_VISIBLE: traction visible but financial impact not linked
    if evidence_level == "OPERATING_OUTCOME_VISIBLE":
        if any(s in combined for s in _POSITIVE_OUTCOME_SIGNALS):
            return "EARLY_POSITIVE_SIGNAL"
        return "UNPROVEN"

    return "UNPROVEN"


# ── Financial link status ──────────────────────────────────────────────────────

def resolve_financial_link_status(record: Dict[str, Any], return_status: str) -> str:
    """
    Assess whether the financial outcome is attributable to this allocation,
    not merely coincident.

    PROVEN  — strong causal evidence
    PARTIAL — suggestive but not conclusive
    UNPROVEN — no causal link established
    """
    causal = (record.get("causal_confidence") or "").lower()
    financial = (record.get("financial_outcome") or record.get("financial_evidence") or "").strip().lower()

    if return_status in ("PROVEN_POSITIVE",):
        return "PROVEN"

    if return_status in ("DESTRUCTIVE", "WEAK"):
        return "PROVEN"  # negative causal proof is still proof

    if causal == "high":
        return "PROVEN"

    if causal == "medium":
        return "PARTIAL"

    # Check whether financial text contains causal connectors
    causal_connectors = (
        "contributed to", "driven by", "attributable to", "led to",
        "resulting in", "caused", "because of", "due to"
    )
    if any(c in financial for c in causal_connectors):
        return "PARTIAL"

    if financial and any(c.isdigit() for c in financial):
        return "PARTIAL"

    return "UNPROVEN"


# ── Investor interpretation templates ─────────────────────────────────────────

_TEMPLATES: Dict[Tuple[str, str], str] = {
    # (evidence_level, return_status): template
    ("ALLOCATION_IDENTIFIED", "UNPROVEN"): (
        "Capital was allocated but no subsequent execution or outcome evidence is available in the current record."
    ),
    ("EXECUTION_VISIBLE", "UNPROVEN"): (
        "Capital was deployed and the allocation appears to have been executed. "
        "No operating traction or financial outcome has been established yet."
    ),
    ("OPERATING_OUTCOME_VISIBLE", "UNPROVEN"): (
        "Execution is visible and there are initial operating signals. "
        "The financial consequence — revenue contribution, margin effect, or return — remains unproven."
    ),
    ("OPERATING_OUTCOME_VISIBLE", "EARLY_POSITIVE_SIGNAL"): (
        "Execution is visible and early operational traction is present. "
        "Financial returns are not yet established; the operating signal is promising but not conclusive."
    ),
    ("FINANCIAL_OUTCOME_VISIBLE", "EARLY_POSITIVE_SIGNAL"): (
        "A financial metric improved after this allocation. "
        "Causal attribution is partial — the improvement is consistent with the thesis but not definitively attributable."
    ),
    ("FINANCIAL_OUTCOME_VISIBLE", "UNPROVEN"): (
        "A financial metric is visible in the period following this allocation, "
        "but the causal link between the deployment and the financial outcome has not been established."
    ),
    ("FINANCIAL_OUTCOME_VISIBLE", "MIXED"): (
        "Some financial metrics moved in the expected direction; others did not. "
        "The stated economic rationale is only partially supported by the available evidence."
    ),
    ("RETURN_EVIDENCE_VISIBLE", "PROVEN_POSITIVE"): (
        "Return evidence is available and supports a positive outcome. "
        "Verify the causal link and period comparability before treating this as fully conclusive."
    ),
    ("RETURN_EVIDENCE_VISIBLE", "EARLY_POSITIVE_SIGNAL"): (
        "Return indicators are visible. The evidence is positive but not yet at full-proof standard."
    ),
    ("RETURN_EVIDENCE_VISIBLE", "MIXED"): (
        "Return evidence is available but the picture is mixed — some metrics improved, others did not."
    ),
    # Capital-return types
    ("EXECUTION_VISIBLE", "NOT_APPLICABLE"): (
        "Capital was returned to shareholders or used to reduce financial obligations. "
        "Return-on-investment logic does not apply; assess sustainability and balance-sheet impact separately."
    ),
    ("OPERATING_OUTCOME_VISIBLE", "NOT_APPLICABLE"): (
        "Capital was returned or debt was reduced, with visible financial-structure improvement. "
        "Whether this was the optimal use of capital relative to reinvestment alternatives is not assessed here."
    ),
    ("FINANCIAL_OUTCOME_VISIBLE", "NOT_APPLICABLE"): (
        "Capital was returned to shareholders or used to reduce debt. "
        "A financial-structure metric is visible (e.g. EPS, leverage). "
        "Whether the payout was appropriate given available reinvestment opportunities is not determined."
    ),
    # Destructive
    ("FINANCIAL_OUTCOME_VISIBLE", "DESTRUCTIVE"): (
        "The available evidence suggests this allocation produced an adverse financial outcome — "
        "impairment, margin erosion, or loss. Treat this as a red flag warranting further investigation."
    ),
    ("RETURN_EVIDENCE_VISIBLE", "DESTRUCTIVE"): (
        "Return evidence is available and indicates a destructive outcome — "
        "impairment, write-down, or sustained economic loss. "
        "Management's rationale for the original allocation should be scrutinised."
    ),
}


def build_investor_interpretation(
    record: Dict[str, Any],
    allocation_type: str,
    evidence_level: str,
    return_status: str,
) -> str:
    """Build investor-grade interpretation text. Never exceeds the evidence level."""
    # Use existing investor_implication if it's substantive and not generic boilerplate
    existing = (record.get("investor_implication") or "").strip()
    _GENERIC_PHRASES = (
        "there is not enough later evidence",
        "judge this allocation confidently",
        "capital has been deployed, but later outcome attribution",
        "not yet observable",
    )
    if existing and len(existing) > 80 and not any(p in existing.lower() for p in _GENERIC_PHRASES):
        return existing.rstrip(".") + "."

    return _TEMPLATES.get(
        (evidence_level, return_status),
        (
            f"This allocation is tracked at level {evidence_level}. "
            f"Return status: {return_status}. "
            "Consult the source evidence for further detail."
        ),
    )


# ── Capital-specific interpretation for dividends / buybacks / debt repayment ─

def build_capital_return_interpretation(
    record: Dict[str, Any],
    allocation_type: str,
    financial_data: Dict[str, Any],
) -> str:
    """
    Dedicated investor interpretation for capital-structure decisions.
    Does NOT apply ROI logic.
    """
    amount_cr = _resolve_amount(record)
    fcf_series = financial_data.get("fcf_series") or []
    cfo_series = financial_data.get("cfo_series") or []

    if allocation_type == "DIVIDEND":
        if fcf_series:
            avg_fcf = sum(v for v in fcf_series if v is not None) / max(len([v for v in fcf_series if v is not None]), 1)
            if amount_cr and avg_fcf and amount_cr < avg_fcf * 0.7:
                return (
                    "Dividend payout appears comfortably within free cash flow generation. "
                    "Sustainability is supported, but whether reinvestment alternatives were available is not assessed."
                )
        return (
            "Capital was returned to shareholders via dividend. "
            "The payout's sustainability relative to free cash flow and reinvestment opportunities "
            "requires separate assessment."
        )

    if allocation_type == "BUYBACK":
        return (
            "Shares were repurchased. Whether the repurchase was economically sensible relative to "
            "intrinsic value is not assessable without valuation context. "
            "The effect on per-share metrics depends on the price paid relative to business value."
        )

    if allocation_type == "DEBT_REPAYMENT":
        return (
            "Debt was repaid or reduced. If leverage declined, financial resilience improved. "
            "Whether this was the optimal use of capital relative to growth investment depends on "
            "the available reinvestment opportunities at the time."
        )

    return build_investor_interpretation(record, allocation_type, "EXECUTION_VISIBLE", "NOT_APPLICABLE")


def _resolve_amount(record: Dict[str, Any]) -> Optional[float]:
    for field in ("amount", "capital_amount", "amount_crore"):
        v = record.get(field)
        if isinstance(v, (int, float)) and v != 0:
            return abs(float(v))
    return None


# ── Materiality rank for sorting ───────────────────────────────────────────────

_TYPE_RANK = {
    "ACQUISITION": 10,
    "CAPACITY_EXPANSION": 9,
    "ORGANIC_CAPEX": 8,
    "DIGITAL_OR_TECH_INVESTMENT": 8,
    "R_AND_D": 7,
    "NEW_MARKET_OR_PRODUCT": 6,
    "BUYBACK": 5,
    "DIVIDEND": 4,
    "DEBT_REPAYMENT": 4,
    "WORKING_CAPITAL": 3,
    "OTHER": 1,
}

_RETURN_RANK_BONUS = {
    "PROVEN_POSITIVE": 3,
    "EARLY_POSITIVE_SIGNAL": 2,
    "DESTRUCTIVE": 3,
    "WEAK": 2,
    "MIXED": 1,
    "UNPROVEN": 0,
    "NOT_APPLICABLE": 0,
}

_EVIDENCE_RANK_BONUS = {
    "RETURN_EVIDENCE_VISIBLE": 3,
    "FINANCIAL_OUTCOME_VISIBLE": 2,
    "OPERATING_OUTCOME_VISIBLE": 1,
    "EXECUTION_VISIBLE": 0,
    "ALLOCATION_IDENTIFIED": 0,
}


def materiality_rank(allocation: Dict[str, Any]) -> int:
    base = _TYPE_RANK.get(allocation.get("allocation_type") or "OTHER", 1)
    ret_bonus = _RETURN_RANK_BONUS.get(allocation.get("return_status") or "UNPROVEN", 0)
    ev_bonus = _EVIDENCE_RANK_BONUS.get(allocation.get("evidence_level") or "ALLOCATION_IDENTIFIED", 0)
    # Amount bonus: significant deployments float higher
    amount = allocation.get("capital_amount_crore")
    amount_bonus = 2 if (amount and amount >= 200) else (1 if amount and amount >= 50 else 0)
    return base + ret_bonus + ev_bonus + amount_bonus
