"""Economic attribution intelligence builder (ENG-135).

Synthesises attribution intelligence from:
  1. Capital Allocation Outcomes (CAO) — authoritative allocation attribution
  2. Management Progression (MP) — execution/outcome state
  3. Risk Evolution Gold — risk trajectory and response state
  4. Financial Truth Pack — verified metrics for per-share / financial bridge

Attribution taxonomy, operating outcome, financial consequence, and economic
consequence contracts are frozen in contracts.py.

Canonical invariants (ENG-135A + ENG-135):
  - Chronology is NOT causality.
  - UNKNOWN is acceptable; false attribution is unacceptable.
  - DIRECTLY_ATTRIBUTABLE only for deterministic transaction consequences (dividends,
    buybacks, debt repayment) or explicit company attribution with source evidence.
  - Alternative explanations must be considered for any STRONGLY_SUPPORTED claim.

# ponytail: single builder module; no separate sub-builders per initiative type
# until multiple proven use cases require it.
"""
from __future__ import annotations
from knowledge.financials.authority_gate import load_vouched

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .contracts import (
    ATTRIBUTION_LEVELS,
    CHAIN_STOP_REASONS,
    ECONOMIC_CONSEQUENCE_TYPES,
    FINANCIAL_CONSEQUENCE_TYPES,
    GENERATOR_VERSION,
    MATERIALITY_LEVELS,
    OPERATING_OUTCOME_TYPES,
    SCHEMA_VERSION,
    SEMANTIC_CONTRACTS,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Any:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# ─── Attribution challenge: alternative explanations per category ─────────────

_ALTERNATIVE_EXPLANATIONS: Dict[str, List[str]] = {
    "acquisition": [
        "Industry revenue growth may explain post-acquisition revenue improvement.",
        "Pricing tailwinds or mix shift may explain margin improvement post-acquisition.",
        "Synergy claims are unverified without segment-level attribution disclosure.",
        "Organic business growth may have occurred regardless of the acquisition.",
    ],
    "organic_capex": [
        "Consolidated revenue growth may reflect pricing, mix, or existing capacity.",
        "New capacity utilisation rate and contribution not disclosed.",
        "Industry demand recovery may explain revenue improvement regardless of capex.",
    ],
    "product_initiative": [
        "Market size growth may explain product revenue increase.",
        "Pricing action rather than volume adoption may drive revenue.",
        "Geographic mix shift may explain contribution change.",
    ],
    "risk_remediation": [
        "Risk reduction may reflect industry-wide change rather than company-specific action.",
        "External regulatory changes may have resolved the risk without management action.",
        "Improvement may be temporary without structural fix evidence.",
    ],
    "working_capital": [
        "Working-capital release may reflect seasonal factors.",
        "Receivables improvement may reflect mix shift to cash-paying customers.",
        "CFO improvement may reflect earnings growth independent of WC management.",
    ],
    "distribution": [],  # deterministic transaction — no alternatives needed
}

_MATERIALITY_REVENUE_THRESHOLDS = {
    "MATERIAL": 0.02,    # ≥ 2% of consolidated revenue
    "MODERATE": 0.005,   # 0.5–2%
}


def _classify_materiality(amount: Optional[float], revenue: Optional[float]) -> str:
    if amount is None or revenue is None or revenue == 0:
        return "UNKNOWN"
    ratio = abs(amount) / revenue
    if ratio >= _MATERIALITY_REVENUE_THRESHOLDS["MATERIAL"]:
        return "MATERIAL"
    if ratio >= _MATERIALITY_REVENUE_THRESHOLDS["MODERATE"]:
        return "MODERATE"
    return "MINOR"


def _build_cao_cases(cao_data: Dict[str, Any], latest_revenue: Optional[float]) -> List[Dict[str, Any]]:
    """Build outcome intelligence records from Capital Allocation Outcomes."""
    cases = []
    for alloc in cao_data.get("allocations", []):
        allocation_id = alloc.get("allocation_id", "")
        category = alloc.get("allocation_category", "unknown")
        name = alloc.get("allocation_name", "")
        amount = alloc.get("amount")
        periods = alloc.get("deployment_periods", [])
        attribution = alloc.get("outcome_attribution", "NO_OUTCOME_EVIDENCE")
        depl_state = alloc.get("deployment_state", "UNKNOWN")
        exec_state = alloc.get("execution_state", "UNKNOWN")

        # Operating outcome — distributions are transaction-complete; acquisitions are COMPLETED_TRANSACTION
        if category in ("dividend", "special_dividend") and (exec_state != "COMPLETED" or alloc.get("lifecycle") != "paid"):
            # a proposed / recommended dividend is not a completed distribution: no payment evidenced, no owner-value consequence
            operating_outcome = "Dividend proposed or recommended; payment is not evidenced, so no distribution has been completed."
            operating_outcome_type = "none_disclosed"
            financial_consequence = "none_disclosed"
            economic_consequence = "unknown"
            chain_stop = "SOURCE_NOT_DISCLOSED"
        elif category in ("dividend", "special_dividend", "share_buyback", "debt_repayment"):
            operating_outcome = "none_disclosed"  # transaction IS the consequence
            operating_outcome_type = "none_disclosed"
            financial_consequence = "deterministic_transaction_consequence"
            economic_consequence = "per_share_owner_value_change" if category in ("dividend", "share_buyback") else "balance_sheet_resilience_change"
            chain_stop = "CORRECT_KNOWN"
        elif attribution == "ASSOCIATED_NOT_ATTRIBUTABLE":
            operating_outcome = "Execution confirmed (transaction completed); operating contribution not disclosed."
            operating_outcome_type = "none_disclosed"
            financial_consequence = "none_disclosed"
            economic_consequence = "unknown"
            chain_stop = "FINANCIAL_LINK_NOT_CAPTURED"
        else:
            operating_outcome = "Execution state: unable to verify."
            operating_outcome_type = "unknown"
            financial_consequence = "none_disclosed"
            economic_consequence = "unknown"
            chain_stop = "SOURCE_NOT_DISCLOSED"

        # Per-share consequence
        per_share = None
        if category in ("dividend", "share_buyback") and not (category == "dividend" and alloc.get("lifecycle") != "paid"):
            per_share = "Dividend/buyback directly reduces retained cash per share or increases EPS via share count reduction."
        elif category == "debt_repayment":
            per_share = "Debt reduction lowers interest burden per share prospectively."

        # Alternative explanations
        alt_expl = _ALTERNATIVE_EXPLANATIONS.get(
            "distribution" if category in ("dividend", "special_dividend", "share_buyback", "debt_repayment") else category,
            _ALTERNATIVE_EXPLANATIONS.get("organic_capex", []),
        )

        materiality = _classify_materiality(amount, latest_revenue)

        cases.append({
            "source_action_id": allocation_id,
            "initiative_id": allocation_id,
            "action_type": category,
            "source_system": "capital_allocation_outcomes",
            "action_description": name,
            "deployment_periods": periods,
            "amount_inr_cr": amount,
            "amount_period": alloc.get("amount_period"),  # the ONE period the amount belongs to (not deployment_periods)
            "execution_state": exec_state,
            "deployment_state": depl_state,
            "operating_outcome": operating_outcome,
            "operating_outcome_type": operating_outcome_type,
            "financial_consequence": financial_consequence,
            "economic_consequence": economic_consequence,
            "attribution_strength": attribution,
            "attribution_basis": "ENG-122 capital allocation taxonomy; transaction-consequence rule for distributions.",
            "alternative_explanations": alt_expl,
            "per_share_consequence": per_share,
            "unresolved_gap": chain_stop,
            "economic_materiality": materiality,
            "investor_interpretation": _investor_interpretation(attribution, category, name, amount, per_share),
            **_pending_transaction_fields(alloc),
        })
    return cases


def _build_mp_cases(mp_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build outcome intelligence records from Management Progression execution outcomes."""
    cases = []
    eo = mp_data.get("management_execution_outcomes") or {}
    records = eo.get("records") or []
    for rec in records:
        exec_state = rec.get("execution_state", "UNKNOWN")
        outcome_state = rec.get("outcome_state", "OUTCOME_UNKNOWN")
        attribution = rec.get("attribution_strength", "NO_OUTCOME_EVIDENCE")
        eligible = rec.get("management_execution_eligible", True)

        if not eligible:
            continue  # regulator/external actor events excluded

        identity = rec.get("identity_label") or rec.get("originating_statement") or ""
        init_id = rec.get("initiative_id") or ""

        # Operating outcome
        if outcome_state == "OUTCOME_OBSERVED":
            op_outcome = rec.get("operating_outcome") or "Outcome observed but not quantified."
            op_type = "volume_adoption_observed"
        elif outcome_state == "OUTCOME_NOT_DISCLOSED":
            op_outcome = "Execution confirmed; operating outcome not disclosed in source documents."
            op_type = "none_disclosed"
        elif outcome_state in ("OUTCOME_NOT_YET_OBSERVED", "OUTCOME_UNKNOWN"):
            op_outcome = "Execution not yet confirmed or announced only; no outcome evidence."
            op_type = "unknown"
        else:
            op_outcome = "Outcome state unknown."
            op_type = "unknown"

        # Chain stop
        if outcome_state == "OUTCOME_NOT_DISCLOSED":
            chain_stop = "SOURCE_NOT_DISCLOSED"
        elif outcome_state in ("OUTCOME_NOT_YET_OBSERVED", "OUTCOME_UNKNOWN"):
            chain_stop = "CORRECT_UNKNOWN"
        else:
            chain_stop = "FINANCIAL_LINK_NOT_CAPTURED"

        # Classify action type from identity label
        action_type = _classify_initiative_type(identity)

        cases.append({
            "source_action_id": init_id,
            "initiative_id": init_id,
            "action_type": action_type,
            "source_system": "management_progression",
            "action_description": identity[:120] if identity else "Initiative (identity not captured)",
            "deployment_periods": [],
            "amount_inr_cr": None,
            "execution_state": exec_state,
            "deployment_state": exec_state,
            "operating_outcome": op_outcome,
            "operating_outcome_type": op_type,
            "financial_consequence": "none_disclosed",
            "economic_consequence": "unknown",
            "attribution_strength": attribution,
            "attribution_basis": "Management Progression lifecycle; ENG-135A identity/lifecycle contracts.",
            "alternative_explanations": _ALTERNATIVE_EXPLANATIONS.get(action_type, []),
            "per_share_consequence": None,
            "unresolved_gap": chain_stop,
            "economic_materiality": "UNKNOWN",
            "investor_interpretation": _mp_investor_interpretation(exec_state, outcome_state, identity),
        })
    return cases


def _build_risk_remediation_cases(gold_risk: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build risk remediation outcome records from Risk Evolution Gold."""
    cases = []
    for risk in gold_risk.get("worsening_or_recurring", []) + gold_risk.get("improving_or_resolved", []):
        theme_id = risk.get("risk_theme_id", "")
        theme = risk.get("theme", "")
        state = risk.get("current_state", "UNKNOWN")
        desc = risk.get("risk_description", "")
        response = risk.get("management_response_assessed", risk.get("management_response", "NOT_ASSESSED"))
        economic_exposure = risk.get("economic_exposure", "")

        if state in ("WORSENING", "RECURRING"):
            attribution = "NO_OUTCOME_EVIDENCE"
            op_outcome = "Risk remains active; no management response assessed."
            chain_stop = "SOURCE_NOT_DISCLOSED"
            ec = "none_established"
        elif state == "IMPROVING":
            attribution = "ASSOCIATED_NOT_ATTRIBUTABLE"
            op_outcome = "Risk trajectory improving; causation of improvement unestablished."
            chain_stop = "ATTRIBUTION_NOT_DEFENSIBLE"
            ec = "unknown"
        else:
            attribution = "ATTRIBUTION_UNKNOWN"
            op_outcome = "Unknown trajectory."
            chain_stop = "CORRECT_UNKNOWN"
            ec = "unknown"

        cases.append({
            "source_action_id": theme_id,
            "initiative_id": theme_id,
            "action_type": "risk_remediation",
            "source_system": "risk_evolution_gold",
            "action_description": f"[{theme}] {desc[:100]}",
            "deployment_periods": [],
            "amount_inr_cr": None,
            "execution_state": "UNKNOWN",
            "deployment_state": "UNKNOWN",
            "operating_outcome": op_outcome,
            "operating_outcome_type": "none_disclosed" if state in ("WORSENING", "RECURRING") else "unknown",
            "financial_consequence": "none_disclosed",
            "economic_consequence": ec,
            "attribution_strength": attribution,
            "attribution_basis": "Risk Evolution Gold trajectory state.",
            "alternative_explanations": _ALTERNATIVE_EXPLANATIONS.get("risk_remediation", []),
            "per_share_consequence": None,
            "unresolved_gap": chain_stop,
            "economic_materiality": "UNKNOWN",
            "investor_interpretation": (
                f"Risk '{theme}' is {state.lower()}. Economic exposure: {economic_exposure[:100] if economic_exposure else 'not quantified'}. "
                f"Management response: {response}."
            ),
        })
    return cases


def _classify_initiative_type(identity: str) -> str:
    text = (identity or "").lower()
    if any(w in text for w in ["acquisition", "acqui", "incorpor"]):
        return "acquisition"
    if any(w in text for w in ["product", "launch", "ilumya", "ramp", "prescrip"]):
        return "product_initiative"
    if any(w in text for w in ["facility", "manufactur", "plant", "capac", "toansa", "mohali", "vedanth"]):
        return "organic_capex"
    if any(w in text for w in ["usfda", "fda", "regulat", "import alert"]):
        return "risk_remediation"
    if any(w in text for w in ["market", "geograph", "japan", "china", "india", "us", "emerg"]):
        return "product_initiative"
    return "strategic_initiative"


def _pending_transaction_fields(alloc: Dict[str, Any]) -> Dict[str, Any]:
    """G3: a signed-but-not-completed transaction is stated as that. Nothing has been deployed, so the generic 'capital deployed' reading does not apply; the filing's
    own terms and status sentence are carried through unchanged (stated currency, no conversion)."""
    status = alloc.get("transaction_status")
    if status not in {"signed_pending_completion", "announced"}:
        return {}
    terms, basis = alloc.get("transaction_terms"), alloc.get("transaction_status_basis")
    text = "Signed, not completed: no capital has been deployed yet and no operating outcome can exist."
    if terms:
        text += f" Stated terms: {terms}."
    if basis:
        text += f" The filing states the transaction {basis}."
    return {"transaction_status": status, "transaction_terms": terms, "transaction_status_basis": basis, "investor_interpretation": text}


def _investor_interpretation(attribution: str, category: str, name: str, amount: Optional[float], per_share: Optional[str]) -> str:
    amt_str = f"~₹{amount:,.0f} Cr" if amount else "amount not quantified"
    if attribution == "DIRECTLY_ATTRIBUTABLE":
        if category == "dividend":
            return f"Dividend ({amt_str}) paid to shareholders. Transaction consequence is direct — this IS the economic event. Per-share: {per_share or 'see EPS metrics'}."
        if category == "share_buyback":
            return f"Share buyback ({amt_str}). Directly reduces share count; per-share consequences are deterministic. Per-share: {per_share or 'see EPS metrics'}."
        if category == "debt_repayment":
            return f"Debt/lease repayment ({amt_str}). Balance-sheet liability reduced; coverage ratios improved. Per-share: {per_share or 'see debt metrics'}."
        return f"Directly attributable capital action ({amt_str})."
    if attribution == "ASSOCIATED_NOT_ATTRIBUTABLE":
        return (
            f"Capital deployed ({amt_str}) and execution confirmed. "
            f"Subsequent financial change is temporally associated but causally unestablished. "
            f"Alternative explanations (industry growth, pricing, mix) cannot be excluded."
        )
    return (
        f"Capital deployed ({amt_str}); no operating outcome or financial contribution disclosed. "
        f"Attribution cannot be established without source evidence."
    )


def _mp_investor_interpretation(exec_state: str, outcome_state: str, identity: str) -> str:
    short = (identity or "")[:80]
    if exec_state == "ACTION_COMPLETED" and outcome_state == "OUTCOME_NOT_DISCLOSED":
        return f"Action completed: '{short}'. Operating outcome not disclosed — completion ≠ success or value creation."
    if exec_state == "ACTION_STARTED":
        return f"Action visible: '{short}'. Execution underway; operating outcome not yet observed."
    return f"Initiative announced: '{short}'. No action evidence; outcome unknown (CORRECT_UNKNOWN — not failed)."


def _build_attribution_summary(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {level: 0 for level in ATTRIBUTION_LEVELS}
    for c in cases:
        attr = c.get("attribution_strength", "ATTRIBUTION_UNKNOWN")
        if attr in counts:
            counts[attr] += 1
        else:
            counts["ATTRIBUTION_UNKNOWN"] += 1
    return {
        "total_cases": len(cases),
        "directly_attributable": counts["DIRECTLY_ATTRIBUTABLE"],
        "strongly_supported": counts["STRONGLY_SUPPORTED"],
        "associated_not_attributable": counts["ASSOCIATED_NOT_ATTRIBUTABLE"],
        "no_outcome_evidence": counts["NO_OUTCOME_EVIDENCE"],
        "negative_outcome": counts["NEGATIVE_OUTCOME"],
        "attribution_unknown": counts["ATTRIBUTION_UNKNOWN"],
    }


def _build_financial_bridge(cases: List[Dict[str, Any]], financial_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Link outcomes to financial truth where defensible only."""
    direct = [c for c in cases if c["attribution_strength"] == "DIRECTLY_ATTRIBUTABLE"]
    associated = [c for c in cases if c["attribution_strength"] == "ASSOCIATED_NOT_ATTRIBUTABLE"]
    no_evidence = [c for c in cases if c["attribution_strength"] == "NO_OUTCOME_EVIDENCE"]

    # Per-share bridge: only for distributions (DIRECTLY_ATTRIBUTABLE)
    eps_fy26 = financial_metrics.get("eps_basic", {}).get("fy26")
    cfo_per_share_fy26 = financial_metrics.get("cfo_per_share", {}).get("fy26")
    revenue_fy26 = financial_metrics.get("revenue", {}).get("fy26")

    verdict = "PARTIAL"  # We have some direct + some unknown
    if len(direct) == 0:
        verdict = "FAIL"
    elif len(no_evidence) == 0:
        verdict = "PASS"

    return {
        "bridge_verdict": verdict,
        "directly_attributable_count": len(direct),
        "associated_not_attributable_count": len(associated),
        "no_outcome_evidence_count": len(no_evidence),
        "defensible_financial_links": [
            {
                "case_id": c["source_action_id"],
                "financial_consequence_type": c["financial_consequence"],
                "per_share_consequence": c["per_share_consequence"],
                "basis": "Deterministic transaction consequence",
            }
            for c in direct
        ],
        "financial_metrics_context": {
            "eps_basic_fy26": eps_fy26,
            "cfo_per_share_fy26": cfo_per_share_fy26,
            "revenue_fy26_inr_cr": revenue_fy26,
            "note": "Consolidated metrics. Initiative-level attribution not defensible from consolidated movement alone.",
        },
        "non_defensible_links": [
            f"{c['source_action_id']}: {c['action_description'][:60]} — {c['unresolved_gap']}"
            for c in associated + no_evidence
        ][:10],
    }


def _build_attribution_challenge_table(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """For every DIRECTLY_ATTRIBUTABLE or STRONGLY_SUPPORTED material case: ask 'what else could explain this?'"""
    table = []
    for c in cases:
        if c["attribution_strength"] not in ("DIRECTLY_ATTRIBUTABLE", "STRONGLY_SUPPORTED"):
            continue
        if c["economic_materiality"] not in ("MATERIAL", "MODERATE"):
            continue
        table.append({
            "case_id": c["source_action_id"],
            "action": c["action_description"][:80],
            "claimed_attribution": c["attribution_strength"],
            "alternative_explanations": c["alternative_explanations"],
            "downgrade_verdict": (
                "ATTRIBUTION_HOLDS — transaction IS the economic event (distributions)"
                if c["attribution_strength"] == "DIRECTLY_ATTRIBUTABLE"
                else "DOWNGRADE_REQUIRED — alternatives cannot be excluded"
            ),
        })
    return table


def _build_attribution_critical_unknowns(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate specific causal gap questions for investment due diligence."""
    unknowns = []
    # Acquisition cases with no financial link
    acq_cases = [c for c in cases if c["action_type"] == "acquisition" and c["attribution_strength"] == "ASSOCIATED_NOT_ATTRIBUTABLE"]
    for c in acq_cases[:3]:
        unknowns.append({
            "case_id": c["source_action_id"],
            "question": f"What evidence would demonstrate that '{c['action_description'][:60]}' produced attributable operating improvement — beyond post-acquisition revenue growth that could reflect industry trends, pricing, or organic capacity?",
            "priority": "HIGH",
            "evidence_needed": "Segment-level revenue contribution, margin accretion, or explicit management attribution with specific metrics.",
            "strengthens_attribution_if": "Company discloses segment-level contribution or explicit synergy with metrics.",
            "weakens_attribution_if": "Industry peers show similar growth in same period without the acquisition.",
        })
    # Organic capex cases
    capex_cases = [c for c in cases if c["action_type"] == "organic_capex" and c["attribution_strength"] == "NO_OUTCOME_EVIDENCE"]
    for c in capex_cases[:2]:
        unknowns.append({
            "case_id": c["source_action_id"],
            "question": f"What evidence would link capex deployment to specific capacity additions, utilization rates, or incremental revenue — rather than treating consolidated revenue growth as capex attribution?",
            "priority": "MEDIUM",
            "evidence_needed": "Utilisation rate data, capacity addition disclosures, incremental revenue by facility.",
            "strengthens_attribution_if": "Company discloses capacity utilisation rates and incremental output per facility.",
            "weakens_attribution_if": "Revenue growth tracks industry without facility-level disclosure.",
        })
    # Execution outcome unknowns
    mp_no_outcome = [c for c in cases if c["source_system"] == "management_progression" and c["attribution_strength"] == "NO_OUTCOME_EVIDENCE" and c["execution_state"] == "ACTION_COMPLETED"]
    for c in mp_no_outcome[:2]:
        unknowns.append({
            "case_id": c["source_action_id"],
            "question": f"Initiative '{c['action_description'][:60]}' reached completion but no operating outcome was disclosed. What observable indicator would confirm the initiative produced economic value?",
            "priority": "MEDIUM",
            "evidence_needed": "Volume data, market share data, or explicit contribution disclosure in next annual report.",
            "strengthens_attribution_if": "Subsequent disclosure confirms prescription volume, market entry, or contribution.",
            "weakens_attribution_if": "No mention in subsequent filings or investor communications.",
        })
    return unknowns


def build_economic_attribution_intelligence(
    cao_path: Path,
    mp_path: Path,
    gold_risk_path: Path,
    financial_truth_path: Path,
) -> Dict[str, Any]:
    """Build economic attribution intelligence for one company.

    Reads from four authoritative sources and synthesises without introducing
    heuristic causal inference. CHRONOLOGY IS NOT CAUSALITY.
    """
    cao_data = _load_json(cao_path)
    mp_data = _load_json(mp_path)
    gold_risk = _load_json(gold_risk_path)
    ftp = load_vouched(financial_truth_path)

    # Build per-year financial metrics lookup from FTP
    from collections import defaultdict
    by_metric: Dict[str, Dict[str, Any]] = defaultdict(dict)
    for m in ftp.get("usable_current_metrics", []):
        mid = m.get("metric_id", "")
        fy = m.get("fiscal_year", "")
        val = m.get("value")
        if mid and fy and val is not None:
            by_metric[mid][fy] = val
    financial_metrics = dict(by_metric)

    latest_revenue = financial_metrics.get("revenue", {}).get("fy26") or financial_metrics.get("revenue", {}).get("fy25")

    # Build cases from all three sources
    cao_cases = _build_cao_cases(cao_data, latest_revenue)
    mp_cases = _build_mp_cases(mp_data)
    risk_cases = _build_risk_remediation_cases(gold_risk)
    all_cases = cao_cases + mp_cases + risk_cases

    summary = _build_attribution_summary(all_cases)
    financial_bridge = _build_financial_bridge(cao_cases, financial_metrics)  # only CAO has financial amounts
    challenge_table = _build_attribution_challenge_table(cao_cases)
    critical_unknowns = _build_attribution_critical_unknowns(all_cases)

    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generated_at": _utc_now(),
        "company": cao_data.get("company", mp_data.get("company", "unknown")),
        "attribution_summary": summary,
        "semantic_contracts": SEMANTIC_CONTRACTS,
        "canonical_attribution_taxonomy": {
            "DIRECTLY_ATTRIBUTABLE": "Transaction IS the economic event (dividend, buyback, debt repayment). No causal inference required.",
            "STRONGLY_SUPPORTED": "Multiple convergent evidence items confirm execution + explicit outcome signal. Alternative explanations explicitly considered and excluded.",
            "ASSOCIATED_NOT_ATTRIBUTABLE": "Deployment and execution confirmed; economic change occurred around initiative; causality unestablished.",
            "NO_OUTCOME_EVIDENCE": "Execution exists (or announced); outcome evidence absent. Not FAILED.",
            "NEGATIVE_OUTCOME": "Evidence demonstrates adverse result defensibly linked to action.",
            "ATTRIBUTION_UNKNOWN": "Insufficient basis to classify.",
        },
        "cases": all_cases,
        "financial_bridge": financial_bridge,
        "attribution_challenge_table": challenge_table,
        "attribution_critical_unknowns": critical_unknowns,
        "evidence_hierarchy": [
            "(1) Explicit attributable disclosure with identifiable metric",
            "(2) Audited segment/product/geography contribution",
            "(3) Operational KPI directly tied to initiative",
            "(4) Deterministic transaction consequence",
            "(5) Multiple converging sources",
            "(6) Temporal/economic association only → ASSOCIATED_NOT_ATTRIBUTABLE at most",
            "(7) Unknown",
        ],
        "limitations": [
            "Initiative-level attribution is source-limited: Sun Pharma does not disclose segment-level initiative contribution.",
            "Consolidated financial movements cannot be attributed to specific initiatives without explicit disclosure.",
            "Temporal sequence of action followed by financial improvement does not constitute causal proof.",
            "Management narrative of attribution requires independent corroboration.",
        ],
    }
