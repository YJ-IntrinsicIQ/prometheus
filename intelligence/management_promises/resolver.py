from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# ── Execution status ───────────────────────────────────────────────────────────

def resolve_execution_status(item: Dict[str, Any]) -> str:
    """Derive the highest execution status reached from event roles."""
    events = item.get("events") or []
    roles_seen = {e.get("role") or "" for e in events}

    # Walk the ladder: completion > outcome > milestone > action > commitment
    if "outcome" in roles_seen:
        for event in reversed(events):
            if event.get("role") == "outcome":
                outcome_text = (event.get("operational_outcome") or event.get("financial_or_business_outcome") or "").lower()
                if any(t in outcome_text for t in ("operating", "operational", "revenue", "utiliz", "deployed")):
                    return "EARLY_OPERATING_SIGNAL"
        return "ACTION_COMPLETED"

    if "completion" in roles_seen:
        return "ACTION_COMPLETED"

    if "milestone" in roles_seen or "action" in roles_seen:
        return "ACTION_STARTED"

    return "CLAIM_ONLY"


# ── Financial link status ──────────────────────────────────────────────────────

def resolve_financial_link_status(item: Dict[str, Any]) -> str:
    """Assess whether execution is linked to financial/economic outcomes."""
    events = item.get("events") or []
    financial_texts = [
        (e.get("financial_or_business_outcome") or "").strip()
        for e in events
        if (e.get("financial_or_business_outcome") or "").strip()
    ]

    if not financial_texts:
        # Investor interpretation is a conclusion, not financial evidence. A
        # completion warning that says returns remain unproven must never create
        # a financial link merely because it contains the word "returns".
        return "INSUFFICIENT_EVIDENCE"

    combined = " ".join(financial_texts).lower()
    # Strong proof signals
    if any(t in combined for t in ("confirmed", "demonstrated", "proven", "achieved margin", "revenue grew", "reported profit", "increased revenue")):
        return "PROVEN"
    # Weak proof: mentioned but not causal
    if any(t in combined for t in ("not yet", "unproven", "not proven", "not demonstrated", "economic value", "still depends", "not established")):
        return "INSUFFICIENT_EVIDENCE"

    return "PARTIAL"


# ── Outcome status ─────────────────────────────────────────────────────────────

def resolve_outcome_status(
    item: Dict[str, Any],
    *,
    execution_status: str,
    financial_link_status: str,
) -> str:
    """Resolve the investor-facing outcome status."""
    signal = (item.get("management_credibility_signal") or "").upper()
    current = (item.get("current_status") or "").lower()

    if signal == "CONTRADICTED" or current == "failed":
        return "MISSED"

    if signal == "DELIVERED":
        if financial_link_status in ("PROVEN", "PARTIAL"):
            return "ACHIEVED"
        # Execution complete but financial link not established
        return "UNVERIFIED"

    if signal == "PARTIALLY_DELIVERED" or current == "partially_delivered":
        return "PARTIALLY_ACHIEVED"

    if current == "delivered":
        if financial_link_status in ("PROVEN", "PARTIAL"):
            return "ACHIEVED"
        return "UNVERIFIED"

    return "UNVERIFIED"


# ── Delay detection ────────────────────────────────────────────────────────────

def resolve_current_status(
    item: Dict[str, Any],
    outcome_status: str,
    execution_status: str,
) -> str:
    """Combine outcome + delay signals into the top-level current_status."""
    # Check if originally time-bound but now overdue without completion
    events = item.get("events") or []
    has_target_period = any((e.get("target_period") or "").strip() for e in events)
    is_complete = execution_status in ("ACTION_COMPLETED", "EARLY_OPERATING_SIGNAL")
    is_in_progress = execution_status in ("ACTION_STARTED", "CLAIM_ONLY")

    if outcome_status == "MISSED":
        return "MISSED"
    if outcome_status in ("ACHIEVED", "PARTIALLY_ACHIEVED"):
        return outcome_status
    if has_target_period and not is_complete and outcome_status == "UNVERIFIED":
        return "DELAYED"
    if is_in_progress and outcome_status == "UNVERIFIED":
        return "UNVERIFIED"
    return outcome_status


# ── Later evidence ─────────────────────────────────────────────────────────────

def extract_later_evidence(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract later-period evidence events (post-commitment) from the item."""
    events = item.get("events") or []
    if not events:
        return []

    # Find the earliest commitment period
    commitment_periods = [e.get("source_period") or "" for e in events if e.get("role") == "commitment"]
    earliest_commitment = sorted(commitment_periods)[0] if commitment_periods else ""

    later = []
    for event in events:
        role = event.get("role") or ""
        period = event.get("source_period") or ""
        if role in ("action", "milestone", "completion", "outcome", "contradiction") and period >= earliest_commitment:
            action_text = (event.get("action_taken") or event.get("operational_outcome") or event.get("statement_text") or "").strip()
            financial_text = (event.get("financial_or_business_outcome") or "").strip()
            if action_text or financial_text:
                later.append({
                    "period": period,
                    "role": role,
                    "action": action_text[:300] if action_text else "",
                    "financial_outcome": financial_text[:300] if financial_text else "",
                    "verification_status": event.get("verification_status") or "",
                })
    return later


# ── Evidence IDs ───────────────────────────────────────────────────────────────

def extract_evidence_ids(item: Dict[str, Any]) -> List[str]:
    """Collect unique evidence IDs from all events."""
    ids = []
    for event in item.get("events") or []:
        for ev in event.get("evidence") or []:
            eid = ev.get("evidence_id") or ev.get("source_item_id")
            if eid and eid not in ids:
                ids.append(eid)
    return ids


# ── Investor interpretation ────────────────────────────────────────────────────

_INTERPRETATION_TEMPLATES = {
    ("ACTION_COMPLETED", "UNVERIFIED"): (
        "Execution evidence exists: management completed the operational step. "
        "The economic consequence — revenue, margin, or return impact — is not yet established in the available evidence."
    ),
    ("EARLY_OPERATING_SIGNAL", "UNVERIFIED"): (
        "Early operating evidence is visible. Management moved from commitment to action and there are initial operational signals. "
        "The full financial impact remains unproven and should not be assumed from operational activity alone."
    ),
    ("ACTION_STARTED", "UNVERIFIED"): (
        "Management has initiated action. The commitment moved beyond announcement, but neither completion nor financial outcome is confirmed."
    ),
    ("CLAIM_ONLY", "UNVERIFIED"): (
        "This commitment remains at the announcement stage. No subsequent action, completion, or outcome evidence is available."
    ),
    ("ACTION_COMPLETED", "ACHIEVED"): (
        "Management completed this commitment and there is evidence linking execution to a financial or business outcome. "
        "Verify the strength of the causal link before treating it as fully proven."
    ),
    ("ACTION_COMPLETED", "PARTIALLY_ACHIEVED"): (
        "Execution is complete but the original commitment is only partially fulfilled. "
        "The gap between what was promised and what was delivered should be quantified where possible."
    ),
    ("EARLY_OPERATING_SIGNAL", "PARTIALLY_ACHIEVED"): (
        "Early operating evidence is visible from this commitment. "
        "Management has moved from announcement to action and there are initial signs of delivery, but the original commitment is only partially fulfilled. "
        "Later evidence on whether the full economic premise is realised is still needed."
    ),
    ("EARLY_OPERATING_SIGNAL", "ACHIEVED"): (
        "Early operating evidence supports that this commitment reached a positive outcome. "
        "Verify the causal link between execution and the reported financial or business result before treating it as fully proven."
    ),
    ("ACTION_STARTED", "MISSED"): (
        "Management began action on this commitment but later evidence suggests it was not fulfilled as originally stated. "
        "The gap between the original direction and the later evidence is the investor concern."
    ),
    ("ACTION_STARTED", "DELAYED"): (
        "This commitment had a stated or implied deadline that appears to have slipped. "
        "Action has started but the original timeline was not met."
    ),
    ("CLAIM_ONLY", "MISSED"): (
        "Management made a claim or commitment that was later contradicted or not followed through. "
        "The gap between statement and action is the investor concern."
    ),
}


_AUTO_GENERATED_MARKERS = (
    "shows evidence of follow-through",
    "economic value still depends",
    "is visible, but outcome evidence remains incomplete",
    "investor conviction should move only",
)


def build_investor_interpretation(
    item: Dict[str, Any],
    execution_status: str,
    outcome_status: str,
) -> str:
    existing = item.get("investor_implication") or {}
    conclusion = (existing.get("conclusion") or "").strip()
    # Use the existing conclusion only if it's substantive and not auto-generated boilerplate
    is_auto = any(marker in conclusion.lower() for marker in _AUTO_GENERATED_MARKERS)
    # Also skip conclusions that are just the theme text re-stated (truncated with "...")
    is_theme_echo = "..." in conclusion and len(conclusion) < 200
    if conclusion and len(conclusion) > 60 and not is_auto and not is_theme_echo:
        conclusion = conclusion.rstrip(".")
        return conclusion + "."

    return _INTERPRETATION_TEMPLATES.get(
        (execution_status, outcome_status),
        "Evidence level is not sufficient to characterize this promise beyond its current tracking status.",
    )


# ── Materiality ranking ────────────────────────────────────────────────────────

_TYPE_MATERIALITY_RANK = {
    "CAPITAL_ALLOCATION": 10,
    "REGULATORY_REMEDIATION": 9,
    "GROWTH_TARGET": 8,
    "CAPACITY": 7,
    "MARGIN_OR_COST": 7,
    "PRODUCT_LAUNCH": 6,
    "DIGITAL_OR_TECH": 6,
    "MARKET_EXPANSION": 5,
    "CUSTOMER_OR_SERVICE": 4,
    "SUSTAINABILITY": 4,
    "OTHER": 1,
}

_STATUS_MATERIALITY_BONUS = {
    "MISSED": 3,
    "PARTIALLY_ACHIEVED": 2,
    "DELAYED": 2,
    "ACHIEVED": 2,
    "UNVERIFIED": 0,
}


def materiality_rank(promise: Dict[str, Any]) -> int:
    base = _TYPE_MATERIALITY_RANK.get(promise.get("promise_type") or "OTHER", 1)
    bonus = _STATUS_MATERIALITY_BONUS.get(promise.get("current_status") or "UNVERIFIED", 0)
    linked = len(promise.get("linked_company_model_ids") or [])
    return base + bonus + linked
