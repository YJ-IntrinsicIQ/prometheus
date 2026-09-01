from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Chain status vocabulary
# ---------------------------------------------------------------------------

CHAIN_STATUS_CLAIM_ONLY = "CLAIM_ONLY"
CHAIN_STATUS_ACTION_STARTED = "ACTION_STARTED"
CHAIN_STATUS_ACTION_COMPLETED = "ACTION_COMPLETED"
CHAIN_STATUS_OUTCOME_POSITIVE = "OUTCOME_POSITIVE"
CHAIN_STATUS_OUTCOME_NEGATIVE = "OUTCOME_NEGATIVE"
CHAIN_STATUS_OUTCOME_MIXED = "OUTCOME_MIXED"
CHAIN_STATUS_OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
CHAIN_STATUS_FINANCIAL_IMPACT_CONFIRMED = "FINANCIAL_IMPACT_CONFIRMED"
CHAIN_STATUS_FINANCIAL_IMPACT_NOT_YET_VISIBLE = "FINANCIAL_IMPACT_NOT_YET_VISIBLE"
CHAIN_STATUS_FINANCIAL_LINK_UNPROVEN = "FINANCIAL_LINK_UNPROVEN"
# Post-completion early operating evidence (utilisation ramp, initial traction) —
# more than completion alone, less than confirmed positive outcome.
CHAIN_STATUS_EARLY_OPERATING_SIGNAL = "EARLY_OPERATING_SIGNAL"
# Partial, phased, or delayed execution — action started but not yet fully delivered.
CHAIN_STATUS_PARTIAL_EXECUTION = "PARTIAL_EXECUTION"

CHAIN_STATUSES = frozenset(
    {
        CHAIN_STATUS_CLAIM_ONLY,
        CHAIN_STATUS_ACTION_STARTED,
        CHAIN_STATUS_ACTION_COMPLETED,
        CHAIN_STATUS_EARLY_OPERATING_SIGNAL,
        CHAIN_STATUS_PARTIAL_EXECUTION,
        CHAIN_STATUS_OUTCOME_POSITIVE,
        CHAIN_STATUS_OUTCOME_NEGATIVE,
        CHAIN_STATUS_OUTCOME_MIXED,
        CHAIN_STATUS_OUTCOME_UNKNOWN,
        CHAIN_STATUS_FINANCIAL_IMPACT_CONFIRMED,
        CHAIN_STATUS_FINANCIAL_IMPACT_NOT_YET_VISIBLE,
        CHAIN_STATUS_FINANCIAL_LINK_UNPROVEN,
    }
)

FINANCIAL_LINK_CONFIRMED = "confirmed"
FINANCIAL_LINK_NOT_YET_VISIBLE = "not_yet_visible"
FINANCIAL_LINK_UNPROVEN = "unproven"

FINANCIAL_LINK_STATUSES = frozenset(
    {FINANCIAL_LINK_CONFIRMED, FINANCIAL_LINK_NOT_YET_VISIBLE, FINANCIAL_LINK_UNPROVEN}
)

# ---------------------------------------------------------------------------
# Metric keyword map
# Canonical metric_id → tuple of lowercased keywords that mention it in text.
# Used for text-matching only — never as causal proof.
# ---------------------------------------------------------------------------

_METRIC_KEYWORDS: Dict[str, tuple] = {
    "revenue": ("revenue", "sales", "income", "turnover", "top line"),
    "ebitda": ("ebitda", "operating profit"),
    "ebit": ("ebit",),
    "pat": ("pat", "profit after tax", "net profit", "earnings", "bottom line"),
    "capex": ("capex", "capital expenditure", "fixed assets", "plant and equipment"),
    "fcf": ("fcf", "free cash flow"),
    "cfo": (
        "cfo",
        "cash from operations",
        "operating cash",
        "cash flow from operations",
    ),
    "roe": ("roe", "return on equity"),
    "roce": ("roce", "return on capital employed", "return on capital"),
    "total_debt": ("debt", "borrowing", "loans"),
    "receivables": ("receivables", "debtors", "accounts receivable"),
    "inventory": ("inventory", "inventories"),
}

_POSITIVE_SIGNALS = frozenset(
    {
        "improved",
        "growth",
        "increased",
        "higher",
        "rose",
        "reduced",
        "lower",
        "delivered",
        "achieved",
        "success",
        "positive",
        "gained",
        "approved",
        "clearance",
        "reinstated",
        "resolved",
        "expanded",
        "grew",
        "profitable",
    }
)

_COMPLETION_SIGNALS = frozenset(
    {
        "commissioned",
        "commissioning",
        "completed",
        "launched",
        "opened",
        "installed",
        "implemented",
        "deployed",
        "operational",
        "rolled out",
    }
)

# Multi-word phrases signalling early operating traction — present after commissioning
# but before a confirmed positive outcome.  Must be specific enough to avoid matching
# "utilization is not yet proven" or similar negation contexts.
_EARLY_OPERATING_SIGNAL_PHRASES = frozenset(
    {
        "ramping up",
        "ramp up",
        "ramp-up",
        "ramp underway",
        "utilisation ramp",
        "utilization ramp",
        "utilisation visible",
        "utilization visible",
        "utilisation improving",
        "utilization improving",
        "beginning to materialise",
        "beginning to materialize",
        "starting to materialise",
        "starting to materialize",
        "initial contribution",
        "early contribution",
        "starting to contribute",
        "some post-execution evidence",
        "post-execution evidence",
        "early traction",
        "early adoption",
        "customer response encouraging",
        "encouraging customer response",
        "initial uptake",
        "immaterial contribution",
        "contribution immaterial",
        "operationally active",
        "partially operational",
        "business use or utilisation",
        "business use or utilization",
        "early signs of utilisation",
        "early signs of utilization",
        "initial ramp",
    }
)

# Tokens indicating partial, phased, or delayed execution state.
_PARTIAL_EXECUTION_SIGNALS = frozenset(
    {
        "partially implemented",
        "partially delivered",
        "partial implementation",
        "partial delivery",
        "phased rollout",
        "phased implementation",
        "first phase complete",
        "phase 1 complete",
        "timeline delayed",
        "timeline slipped",
        "schedule slipped",
        "behind schedule",
        "delayed rollout",
        "execution delayed",
    }
)

# Tokens indicating the initiative was cancelled or abandoned.
_ABANDONED_SIGNALS = frozenset(
    {
        "cancelled",
        "canceled",
        "abandoned",
        "scrapped",
        "discontinued",
        "wound down",
        "called off",
        "written off",
        "project abandoned",
        "project cancelled",
        "project canceled",
    }
)

_POSITIVE_OUTCOME_PHRASES = (
    "improved",
    "increased",
    "higher",
    "rose",
    "reduced",
    "lower",
    "declined defects",
    "lower defects",
    "higher utilization",
    "utilisation rose",
    "utilization rose",
    "service levels improved",
    "delivery improved",
    "capacity increased",
    "revenue grew",
    "profit grew",
    "regulatory clearance",
    "clearance received",
)

_NEGATIVE_SIGNALS = frozenset(
    {
        "failed",
        "failure",
        "negative",
        "declined",
        "worsened",
        "dropped",
        "penalty",
        "adverse",
        "challenged",
        "deteriorated",
        "loss",
        "deficit",
        "missed",
        "shortfall",
        "prohibition",
        "banned",
        "restricted",
        "rejected",
        "warning letter",
        "import alert",
        "consent decree",
        "contradicted",
    }
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_synthesis_chain(
    item: Dict[str, Any],
    metric_series: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """
    Build a synthesis chain for one progression item.

    Parameters
    ----------
    item:
        A fully-assembled progression_item dict (events already public-stripped).
    metric_series:
        Dict mapping metric_id → list of {year, value, confidence, ...}
        sourced from financial_trends.json. May be empty if unavailable.

    Returns
    -------
    synthesis_chain dict with keys:
        chain_status, claim, action, outcome,
        financial_consequence, investor_implication
    """
    events = _sorted_events(item)
    claim = _extract_claim(events)
    action = _extract_action(events)
    outcome = _extract_outcome(events)
    financial_consequence = _build_financial_consequence(item, action, outcome, metric_series)
    chain_status = _compute_chain_status(
        claim,
        action,
        outcome,
        financial_consequence,
        has_financial_data=bool(metric_series),
        item_current_status=str(item.get("current_status") or ""),
    )
    investor_implication = _build_investor_implication(chain_status, financial_consequence, action=action)
    return {
        "chain_status": chain_status,
        "claim": claim,
        "action": action,
        "outcome": outcome,
        "financial_consequence": financial_consequence,
        "investor_implication": investor_implication,
    }


# ---------------------------------------------------------------------------
# Stage extractors
# ---------------------------------------------------------------------------


def _extract_claim(events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for ev in events:
        if ev.get("role") in {"commitment", "statement"}:
            return {
                "text": _best_text(ev, ("statement_text", "action_taken")),
                "period": ev.get("event_period") or ev.get("source_period") or "",
                "source_event_id": ev.get("event_id") or "",
                "evidence_ids": _ev_ids(ev),
            }
    return None


def _extract_action(events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    action_ev: Optional[Dict[str, Any]] = None
    completed = False
    for ev in events:
        role = ev.get("role") or ""
        text = _best_text(ev, ("action_taken", "statement_text"))
        if role == "completion":
            action_ev = ev
            completed = True
            break
        if role in {"action", "milestone"} and action_ev is None:
            action_ev = ev
            completed = ev.get("verification_status") == "verified" or _has_completion_evidence(text)
    if action_ev is None:
        return None
    return {
        "text": _best_text(action_ev, ("action_taken", "statement_text")),
        "period": action_ev.get("event_period") or action_ev.get("source_period") or "",
        "completed": completed,
        "actor": _actor_class(action_ev),
        "action_actor": _actor_class(action_ev),
        "source_event_id": action_ev.get("event_id") or "",
        "evidence_ids": _ev_ids(action_ev),
    }


def _extract_outcome(events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    # Primary pass: explicit outcome/completion/reversal/abandonment role events.
    # Prefer later events so that subsequent-year evidence upgrades earlier chains.
    for ev in reversed(events):
        role = ev.get("role") or ""
        if role not in {"outcome", "completion", "reversal", "abandonment"}:
            continue
        op = ev.get("operational_outcome") or ""
        fin = ev.get("financial_or_business_outcome") or ""
        combined = f"{op} {fin}".strip()
        if role == "reversal":
            direction = "negative"
        elif role == "abandonment":
            direction = "negative"
        else:
            direction = _infer_direction(combined)
        # Keep combined text so financial_consequence detection can see metric references.
        text = combined or _best_text(ev, ("action_taken",))
        if not text:
            continue
        if role in {"completion", "outcome"} and not (
            _has_true_outcome_evidence(text) or _has_early_operating_signal(text)
        ):
            continue
        return {
            "text": text,
            "period": ev.get("event_period") or ev.get("source_period") or "",
            "direction": direction,
            "actor": _actor_class(ev),
            "source_event_id": ev.get("event_id") or "",
            "evidence_ids": _ev_ids(ev),
        }

    # Secondary pass: action/milestone events whose operational_outcome field contains
    # genuine operating evidence (true outcome or early signal).  This captures cases
    # where an action event carries a populated operational_outcome that would otherwise
    # be invisible to the synthesis layer.
    for ev in reversed(events):
        role = ev.get("role") or ""
        if role not in {"action", "milestone"}:
            continue
        op = str(ev.get("operational_outcome") or "").strip()
        if not op:
            continue
        if not (_has_true_outcome_evidence(op) or _has_early_operating_signal(op)):
            continue
        direction = _infer_direction(op)
        return {
            "text": op,
            "period": ev.get("event_period") or ev.get("source_period") or "",
            "direction": direction,
            "actor": _actor_class(ev),
            "source_event_id": ev.get("event_id") or "",
            "evidence_ids": _ev_ids(ev),
        }

    return None


# ---------------------------------------------------------------------------
# Financial consequence
# ---------------------------------------------------------------------------


def _build_financial_consequence(
    item: Dict[str, Any],
    action: Optional[Dict[str, Any]],
    outcome: Optional[Dict[str, Any]],
    metric_series: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    if action is None or not metric_series:
        return {
            "link_status": FINANCIAL_LINK_NOT_YET_VISIBLE,
            "basis": (
                "No action evidence is available, so financial consequences cannot be evaluated."
                if action is None
                else "No financial time series available; consequences cannot be assessed."
            ),
            "metrics_observed": [],
        }

    action_year = _period_year(action.get("period") or "")
    item_text = _item_text(item)
    mentioned = _find_mentioned_metrics(item_text)

    metrics_observed: List[Dict[str, Any]] = []
    for metric_id in mentioned:
        series = metric_series.get(metric_id) or []
        post = [
            pt
            for pt in series
            if _period_year(pt.get("year") or "") > action_year
            and pt.get("value") is not None
            and pt.get("confidence") not in ("missing",)
        ]
        if not post:
            continue
        direction = _metric_direction(post)
        years = [pt["year"] for pt in post if pt.get("year")]
        metrics_observed.append(
            {
                "metric_id": metric_id,
                "direction": direction,
                "years_observed": years,
                "causal_link": "not_established",
                "note": (
                    f"{metric_id.replace('_', ' ').title()} data is available after the action"
                    " period but causal attribution is not established by evidence."
                ),
            }
        )

    link_status = _determine_link_status(action, outcome, metrics_observed, action_year, metric_series)
    basis = _financial_basis_text(link_status, metrics_observed, action.get("period") or "")

    return {
        "link_status": link_status,
        "basis": basis,
        "metrics_observed": metrics_observed,
    }


def _determine_link_status(
    action: Dict[str, Any],
    outcome: Optional[Dict[str, Any]],
    metrics_observed: List[Dict[str, Any]],
    action_year: int,
    metric_series: Dict[str, List[Dict[str, Any]]],
) -> str:
    # confirmed: only when outcome text explicitly states specific metric values —
    # a numeric quantity AND a metric keyword, indicating management documented the link.
    if outcome is not None and metrics_observed:
        out_text = (outcome.get("text") or "").lower()
        has_number = bool(re.search(r"\b\d[\d,]*\s*(?:crore|million|billion|%|percent|bps)\b", out_text))
        if has_number:
            for m in metrics_observed:
                metric_kws = _METRIC_KEYWORDS.get(m["metric_id"], ())
                if any(kw in out_text for kw in metric_kws):
                    return FINANCIAL_LINK_CONFIRMED

    # not_yet_visible: action year is at or beyond the last year with financial data
    if metric_series:
        all_years = [
            _period_year(pt.get("year") or "")
            for series in metric_series.values()
            for pt in series
            if pt.get("value") is not None and _period_year(pt.get("year") or "") > 0
        ]
        if all_years and action_year >= max(all_years):
            return FINANCIAL_LINK_NOT_YET_VISIBLE

    # unproven: metrics moved after the action, but no causal evidence
    if metrics_observed:
        return FINANCIAL_LINK_UNPROVEN

    return FINANCIAL_LINK_NOT_YET_VISIBLE


# ---------------------------------------------------------------------------
# Chain status computation
# ---------------------------------------------------------------------------


def _compute_chain_status(
    claim: Optional[Dict[str, Any]],
    action: Optional[Dict[str, Any]],
    outcome: Optional[Dict[str, Any]],
    financial_consequence: Dict[str, Any],
    *,
    has_financial_data: bool = False,
    item_current_status: str = "",
) -> str:
    fc_status = financial_consequence.get("link_status")
    metrics_observed = financial_consequence.get("metrics_observed") or []

    # Confirmed financial consequence supersedes all other statuses.
    if fc_status == FINANCIAL_LINK_CONFIRMED:
        return CHAIN_STATUS_FINANCIAL_IMPACT_CONFIRMED

    if action is None:
        return CHAIN_STATUS_CLAIM_ONLY

    completed = action.get("completed", False)
    action_actor = action.get("action_actor") or action.get("actor") or "unknown"

    if outcome is None:
        if action_actor not in {"management", "company"}:
            return CHAIN_STATUS_OUTCOME_UNKNOWN
        # Partial/phased execution: item-level status or action text signals incomplete delivery.
        if item_current_status == "partially_delivered" or _is_partial_execution(action.get("text") or ""):
            return CHAIN_STATUS_PARTIAL_EXECUTION
        if not completed:
            return CHAIN_STATUS_ACTION_STARTED
        return CHAIN_STATUS_ACTION_COMPLETED

    # Outcome evidence exists.
    direction = outcome.get("direction") or "unknown"
    outcome_text = outcome.get("text") or ""

    # FINANCIAL_LINK_UNPROVEN: financial metrics moved after the action but causality is absent.
    if metrics_observed and fc_status == FINANCIAL_LINK_UNPROVEN:
        return CHAIN_STATUS_FINANCIAL_LINK_UNPROVEN

    # EARLY_OPERATING_SIGNAL: early-traction evidence visible but not yet a confirmed outcome.
    # Only applies when the outcome text contains early-signal phrases WITHOUT the stronger
    # confirmed-outcome phrases that would push direction to positive/negative.
    if _has_early_operating_signal(outcome_text) and not _has_true_outcome_evidence(outcome_text):
        return CHAIN_STATUS_EARLY_OPERATING_SIGNAL

    _direction_map = {
        "positive": CHAIN_STATUS_OUTCOME_POSITIVE,
        "negative": CHAIN_STATUS_OUTCOME_NEGATIVE,
        "mixed": CHAIN_STATUS_OUTCOME_MIXED,
        "unknown": CHAIN_STATUS_OUTCOME_UNKNOWN,
    }
    return _direction_map.get(direction, CHAIN_STATUS_OUTCOME_UNKNOWN)


# ---------------------------------------------------------------------------
# Investor implication (grounded in chain_status — no generic templates)
# ---------------------------------------------------------------------------


def _build_investor_implication(
    chain_status: str,
    financial_consequence: Dict[str, Any],
    *,
    action: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metrics_observed = financial_consequence.get("metrics_observed") or []
    metric_list = ", ".join(m["metric_id"] for m in metrics_observed) if metrics_observed else ""
    action_actor = (action or {}).get("action_actor") or (action or {}).get("actor") or "unknown"

    if chain_status == CHAIN_STATUS_OUTCOME_UNKNOWN and action_actor == "regulator":
        return {
            "conclusion": (
                "A regulatory action occurred. Management response, operational outcome, and"
                " financial consequence remain unproven from available evidence."
            ),
            "confidence": "low",
        }
    if chain_status == CHAIN_STATUS_OUTCOME_UNKNOWN and action_actor not in {"management", "company", "unknown"}:
        return {
            "conclusion": (
                "An external actor event occurred. Management action and downstream outcome"
                " remain unproven from available evidence."
            ),
            "confidence": "low",
        }

    _text_map: Dict[str, str] = {
        CHAIN_STATUS_CLAIM_ONLY: (
            "Management made a statement or commitment, but no evidence of action has been documented."
            " Conviction should not move until action is verified."
        ),
        CHAIN_STATUS_ACTION_STARTED: (
            "Management has initiated action. Outcome and financial consequence remain undetermined."
            " The gap between intention and completed execution is not yet closed."
        ),
        CHAIN_STATUS_ACTION_COMPLETED: (
            "Execution was completed, but neither the downstream operating impact nor financial"
            " consequence has been documented. Completion alone does not confirm economic value."
        ),
        CHAIN_STATUS_EARLY_OPERATING_SIGNAL: (
            "Execution is complete and early operating evidence is visible — utilisation ramp,"
            " initial adoption, or early traction is present. However, the economic translation"
            " (sustained revenue contribution, margin improvement, or returns) has not yet been"
            " established. This is an intermediate signal: stronger than completion alone, weaker"
            " than a confirmed business outcome."
        ),
        CHAIN_STATUS_PARTIAL_EXECUTION: (
            "Implementation is partial or delivery is delayed. Economic outcomes cannot be"
            " assessed until execution is substantially complete. Track whether the delay is"
            " temporary or signals a structural constraint on delivery."
        ),
        CHAIN_STATUS_OUTCOME_POSITIVE: (
            "Action was followed by positive operational evidence. Economic returns have not yet"
            " been independently linked to this action."
        ),
        CHAIN_STATUS_OUTCOME_NEGATIVE: (
            "Action was followed by negative outcomes. This weakens management credibility on"
            " this initiative and warrants investor scrutiny of whether recovery is in progress."
        ),
        CHAIN_STATUS_OUTCOME_MIXED: (
            "Evidence is mixed. Partial delivery or conflicting signals mean investor conclusions"
            " must remain conditional on later evidence."
        ),
        CHAIN_STATUS_OUTCOME_UNKNOWN: (
            "Action is documented but outcome direction cannot be assessed from available evidence."
        ),
        CHAIN_STATUS_FINANCIAL_IMPACT_CONFIRMED: (
            "A financial consequence is directly linked to this initiative by documented evidence."
        ),
        CHAIN_STATUS_FINANCIAL_IMPACT_NOT_YET_VISIBLE: (
            "Action is documented but the financial time horizon is too short for consequences to"
            " appear in available data. Monitor in subsequent periods."
        ),
        CHAIN_STATUS_FINANCIAL_LINK_UNPROVEN: (
            f"Financial metrics ({metric_list}) moved after the action period, but the causal link"
            " is not established in evidence. Do not attribute the financial movement to this action"
            " without corroborating evidence."
        ),
    }

    _confidence_map: Dict[str, str] = {
        CHAIN_STATUS_CLAIM_ONLY: "low",
        CHAIN_STATUS_ACTION_STARTED: "low",
        CHAIN_STATUS_ACTION_COMPLETED: "medium",
        CHAIN_STATUS_EARLY_OPERATING_SIGNAL: "medium",
        CHAIN_STATUS_PARTIAL_EXECUTION: "low",
        CHAIN_STATUS_OUTCOME_POSITIVE: "medium",
        CHAIN_STATUS_OUTCOME_NEGATIVE: "medium",
        CHAIN_STATUS_OUTCOME_MIXED: "medium",
        CHAIN_STATUS_OUTCOME_UNKNOWN: "low",
        CHAIN_STATUS_FINANCIAL_IMPACT_CONFIRMED: "high",
        CHAIN_STATUS_FINANCIAL_IMPACT_NOT_YET_VISIBLE: "medium",
        CHAIN_STATUS_FINANCIAL_LINK_UNPROVEN: "medium",
    }

    conclusion = _text_map.get(chain_status, "Insufficient evidence to draw investor conclusions.")
    confidence = _confidence_map.get(chain_status, "low")

    return {"conclusion": conclusion, "confidence": confidence}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sorted_events(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = [e for e in (item.get("events") or []) if isinstance(e, dict)]
    return sorted(events, key=lambda e: _period_year(e.get("event_period") or e.get("source_period") or ""))


def _best_text(event: Dict[str, Any], keys: tuple) -> str:
    for key in keys:
        v = str(event.get(key) or "").strip()
        if v:
            return v
    return ""


def _ev_ids(event: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for ref in event.get("evidence") or []:
        if isinstance(ref, dict) and ref.get("evidence_id"):
            ids.append(str(ref["evidence_id"]))
    return ids


def _actor_class(event: Dict[str, Any]) -> str:
    text = " ".join(
        str(event.get(key) or "")
        for key in ("statement_text", "action_taken", "operational_outcome", "financial_or_business_outcome")
    ).lower()
    if _is_regulator_driven_event(text):
        return "regulator"

    explicit = str(
        event.get("action_actor")
        or event.get("actor_class")
        or event.get("actor")
        or ""
    ).strip().lower()
    if explicit in {"management", "company", "regulator", "customer", "partner", "market", "other", "unknown"}:
        return explicit

    if any(token in text for token in ("usfda", "fda", "regulator", "regulatory authority", "sebi", "rbi", "environment agency")):
        return "regulator"
    if any(token in text for token in ("management", "board", "leadership")):
        return "management"
    if any(token in text for token in ("company", "business", "plant", "facility")):
        return "company"
    if "customer" in text or "client" in text:
        return "customer"
    if "partner" in text or "supplier" in text or "vendor" in text:
        return "partner"
    if "market" in text or "industry" in text or "demand" in text:
        return "market"
    return "unknown"


def _is_regulator_driven_event(text: str) -> bool:
    lowered = text.lower()
    regulator_terms = ("usfda", "fda", "regulator", "regulatory authority", "sebi", "rbi", "environment agency")
    if not any(term in lowered for term in regulator_terms):
        return False
    regulator_action_patterns = (
        r"\b(?:usfda|fda|regulator|regulatory authority|sebi|rbi)\s+(?:prohibited|issued|inspected|classified|restricted|rejected|approved|cleared|lifted|imposed|put|placed)\b",
        r"\b(?:import alert|warning letter|consent decree|official action indicated|oai)\b",
        r"\b(?:prohibited|restricted|banned)\s+use\b",
    )
    return any(re.search(pattern, lowered) for pattern in regulator_action_patterns)


def _item_text(item: Dict[str, Any]) -> str:
    parts = [str(item.get("theme") or "")]
    for ev in item.get("events") or []:
        if isinstance(ev, dict):
            for key in ("statement_text", "action_taken", "operational_outcome", "financial_or_business_outcome"):
                parts.append(str(ev.get(key) or ""))
    return " ".join(parts)


def _find_mentioned_metrics(text: str) -> List[str]:
    lowered = text.lower()
    return [
        metric_id
        for metric_id, keywords in _METRIC_KEYWORDS.items()
        if any(kw in lowered for kw in keywords)
    ]


def _infer_direction(text: str) -> str:
    words = set(re.findall(r"[a-z]+", text.lower()))
    # Check multi-word phrases first
    for phrase in ("warning letter", "import alert", "consent decree"):
        if phrase in text.lower():
            return "negative"
    pos = len(words & _POSITIVE_SIGNALS)
    neg = len(words & _NEGATIVE_SIGNALS)
    if pos > 0 and neg > 0:
        return "mixed"
    if neg > 0:
        return "negative"
    if pos > 0:
        return "positive"
    return "unknown"


def _has_completion_evidence(text: str) -> bool:
    lowered = text.lower()
    return any(signal in lowered for signal in _COMPLETION_SIGNALS)


def _has_early_operating_signal(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _EARLY_OPERATING_SIGNAL_PHRASES)


def _is_partial_execution(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _PARTIAL_EXECUTION_SIGNALS)


def _has_true_outcome_evidence(text: str) -> bool:
    lowered = text.lower()
    if any(phrase in lowered for phrase in ("warning letter", "import alert", "consent decree")):
        return True
    if any(signal in lowered for signal in _NEGATIVE_SIGNALS):
        return True
    if any(phrase in lowered for phrase in _POSITIVE_OUTCOME_PHRASES):
        return True

    words = set(re.findall(r"[a-z]+", lowered))
    positive_words = words & _POSITIVE_SIGNALS
    completion_words = words & _COMPLETION_SIGNALS
    if positive_words - completion_words:
        return True

    return False


def _metric_direction(post_action_points: List[Dict[str, Any]]) -> str:
    values = [pt["value"] for pt in post_action_points if pt.get("value") is not None]
    if len(values) < 2:
        return "unknown"
    if values[-1] > values[0] * 1.01:
        return "increasing"
    if values[-1] < values[0] * 0.99:
        return "decreasing"
    return "flat"


def _period_year(period: Any) -> int:
    """Return a sortable integer from a period string like 'fy24' → 24."""
    m = re.search(r"(\d{2,4})", str(period or "").lower())
    if not m:
        return -1
    v = int(m.group(1))
    return v % 100 if v >= 100 else v


def _financial_basis_text(
    link_status: str,
    metrics_observed: List[Dict[str, Any]],
    action_period: str,
) -> str:
    if link_status == FINANCIAL_LINK_CONFIRMED:
        return "Financial consequence is explicitly linked by documented evidence in the outcome record."
    if link_status == FINANCIAL_LINK_NOT_YET_VISIBLE:
        if not metrics_observed:
            return (
                f"No relevant financial metrics are mentioned in the initiative text, or"
                f" action period ({action_period}) is at or beyond the last available data year."
            )
        return (
            f"Action period ({action_period}) is at or beyond the latest available financial"
            " data; financial consequences cannot yet be assessed."
        )
    metric_ids = ", ".join(m["metric_id"] for m in metrics_observed)
    return (
        f"Financial metrics ({metric_ids}) moved after the action period ({action_period}),"
        " but this is correlation only. No evidence establishes a causal link."
    )
