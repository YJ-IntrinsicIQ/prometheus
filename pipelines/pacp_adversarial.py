"""
PACP Adversarial Check Suite — ENG-MISSION34.1

Implements deterministic invariant checks established in Missions 31–33.6.
Each check returns (result, detail) where result ∈ {PASS, FAIL, SKIP, WARN, INCOMPLETE}.

SKIP  = invariant does not apply to this question/sector combination.
INCOMPLETE = cannot determine without information not available to the checker.

Counts:
  named_checks   = number of distinct check functions called
  assertions     = number of individual re.search / condition evaluations within those checks

These are tracked separately. Never inflate named_checks by splitting one check into trivial sub-calls.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APPROVAL_REGISTRY_PATH = _REPO_ROOT / "governance" / "approval_registry.json"

# ── Types ──────────────────────────────────────────────────────────────────────

CheckResult = tuple[str, str]  # (PASS|FAIL|SKIP|WARN|INCOMPLETE, detail)

# ── Sector mapping ─────────────────────────────────────────────────────────────
# Sectors for known companies; extendable without changing central orchestrator.
COMPANY_SECTORS: dict[str, str] = {
    "sun_pharma": "pharma",
    "tanla": "cpaas",
    "datapatterns": "defence",
    "data_patterns": "defence",
    "ujjivan": "banking",
}

# ── Question-family to family_id mapping ──────────────────────────────────────
QUESTION_FAMILY_MAP: dict[str, str] = {
    "what-could-go-wrong": "risk",
    "what-has-management-promised": "promises",
    "what-did-management-actually-deliver": "delivery",
    "how-good-is-management": "management_quality",
    "how-is-capital-allocated": "capital",
    "did-execution-lead-to-outcomes": "execution",
    "which-investments-created-value": "capital",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _text(answer: dict[str, Any]) -> str:
    parts = []
    for field in ["simple_answer", "what_evidence_shows", "what_may_mean_economically",
                  "what_is_not_yet_proven", "what_to_monitor", "key_points"]:
        val = answer.get(field)
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, list):
            parts.extend(str(x) for x in val)
    return " ".join(parts)


def _dpf_map(answer: dict[str, Any]) -> dict[str, Any]:
    """Build {field_name: value} index from DPFs for consequence_status lookups."""
    dpfs = answer.get("deterministic_precision_facts") or []
    result: dict[str, Any] = {}
    for d in dpfs:
        if isinstance(d, dict):
            k = d.get("field") or d.get("metric") or d.get("name")
            if k:
                result[str(k)] = d.get("value") or d.get("status") or d
    return result


def _family(question_id: str) -> str:
    return QUESTION_FAMILY_MAP.get(question_id, "unknown")


def _sector(company: str) -> str:
    return COMPANY_SECTORS.get(company, "unknown")


# ─── Runtime sanitizer contract ──────────────────────────────────────────────
# Versioned contract. Both this file and presentation.ts must use the same version.
# Canonical spec: governance/sanitizer_contract.json
# Update BOTH files together when changing patterns; bump _SANITIZER_CONTRACT_VERSION in both.
_SANITIZER_CONTRACT_VERSION = "2.0"  # Must match presentation.ts SANITIZER_CONTRACT_VERSION
_RUNTIME_NOISE_PATTERNS: list[re.Pattern] = [
    re.compile(r"company memory", re.IGNORECASE),
    re.compile(r"company-memory", re.IGNORECASE),
    re.compile(r"available evidence summary", re.IGNORECASE),
    re.compile(r"source set summaries?", re.IGNORECASE),
    re.compile(r"saved analyst outputs", re.IGNORECASE),
    re.compile(r"compact financial inputs", re.IGNORECASE),
    re.compile(r"committee-level output", re.IGNORECASE),
    re.compile(r"committee level output", re.IGNORECASE),
    re.compile(r"source_artifact", re.IGNORECASE),
    re.compile(r"source_item_id", re.IGNORECASE),
    re.compile(r"evidence_ids?", re.IGNORECASE),
    re.compile(r"evidence_map", re.IGNORECASE),
    re.compile(r"source chunk", re.IGNORECASE),
    re.compile(r"input pack", re.IGNORECASE),
    re.compile(r"companies/[^\s]+", re.IGNORECASE),
    re.compile(r"source lineage", re.IGNORECASE),
    re.compile(r"raw artifact", re.IGNORECASE),
    re.compile(r"\bpcim\b", re.IGNORECASE),
    re.compile(r"\bcim\b", re.IGNORECASE),
    re.compile(r"\bllm\b", re.IGNORECASE),
    re.compile(r"\b(?:data|ingestion|ML|AI|LLM|ETL|CI|CD|deployment|processing|training|inference|feature|extraction|scoring)\s+pipeline\b", re.IGNORECASE),  # Infra pipeline refs only; allows "drug pipeline", "R&D pipeline", "product pipeline" — M35.3 Phase 6
    re.compile(r"\bartifact(s)?\b", re.IGNORECASE),
    re.compile(r"\bschema\b", re.IGNORECASE),
    re.compile(r"\bcanonical\b", re.IGNORECASE),
]

_RUNTIME_EMPTY_FILLERS = frozenset([
    "this remains a central caution",
    "unspecified",
    "none",
    "no material evidence limitation was identified",
    "no material evidence limitation was identified for this answer",
    "no material uncertainty could be mapped from the available evidence",
    "no material uncertainty was identified",
    "uncertainty note: unspecified",
    "uncertainty note unspecified",
])

_RUNTIME_TRAILING = re.compile(r"(?:\.\.\.|…)$|[''']$|[;:,/\\-]$")
_RUNTIME_MALFORMED = re.compile(r"\b(?:in|on|for|of|at|to|with|from|by)\s*;", re.IGNORECASE)


def _would_survive_sanitizer(text: str) -> bool:
    """Mirror cleanPublicText() rejection logic — returns True only if text would not be emptied."""
    if not text or not text.strip():
        return False
    normalized = text.strip()
    if any(p.search(normalized) for p in _RUNTIME_NOISE_PATTERNS):
        return False
    if _RUNTIME_TRAILING.search(normalized):
        return False
    cleaned = normalized.strip()
    if not cleaned:
        return False
    lowered = cleaned.lower().strip(" .,!?:;")
    if lowered in _RUNTIME_EMPTY_FILLERS:
        return False
    if _RUNTIME_MALFORMED.search(cleaned):
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL CHECKS — apply to all families
# ═══════════════════════════════════════════════════════════════════════════════

def check_no_forbidden_public_terms(answer: dict, **_kw) -> CheckResult:
    """G1 — No internal pipeline terms in investor-facing text (ENG-136 contract)."""
    text = _text(answer)
    # assertions: 1 search
    forbidden = re.search(
        r"\b(directly_attributable|associated_not_attributable|not_supported|"
        r"partially_supported|evidence_summary|uncertainty_note|answer_status|"
        r"execution_outcome|accountability_ontology|company_memory|shadow_level3|"
        r"BLOCKED_IN_PLAN|HARD_COMMITMENT|STRATEGIC_INTENT|ASPIRATION)\b",
        text,
        re.IGNORECASE,
    )
    if forbidden:
        return "FAIL", f"forbidden internal term: {forbidden.group()!r}"
    return "PASS", "no forbidden internal terms"


def check_uncertainty_discipline(answer: dict, **_kw) -> CheckResult:
    """G2 — what_is_not_yet_proven must not contain definitive affirmative confirmed claims.

    Must NOT fire on:
      - "not established" / "none established" / "no confirmed X"  (explicit negation)
      - "whether X is established"  (rhetorical question form — the section's normal idiom)
      - "cannot be confirmed"  (modal negation)
      - "Unable To Verify"  (standing uncertainty label)

    MUST fire on: "X has been confirmed" / "X is established" as a standalone assertion
    (not inside a whether-clause and not preceded by a negation word).
    """
    niytf = str(answer.get("what_is_not_yet_proven") or "")
    # assertion 1: look for the target words at all
    confirmed = re.search(
        r"\b(confirmed|proven|established|demonstrated|verified|shown to have)\b",
        niytf, re.IGNORECASE,
    )
    if not confirmed:
        return "PASS", "uncertainty section is appropriately qualified"
    # assertion 2: check for any negation/question context near the match
    # Window: 80 chars before to 40 chars after the matched word
    window_start = max(0, confirmed.start() - 80)
    window_end = min(len(niytf), confirmed.end() + 40)
    context = niytf[window_start:window_end]
    negation_ok = re.search(
        r"\b(not|no|none|never|cannot|can't|hasn't|haven't|isn't|without|"
        r"whether|unconfirmed|unverified|unable|UNKNOWN)\b",
        context, re.IGNORECASE,
    )
    if negation_ok:
        return "PASS", f"target word {confirmed.group()!r} appears in negated/question context"
    return "FAIL", f"apparent affirmative confirmed claim in what_is_not_yet_proven: {confirmed.group()!r}"


def check_evidence_shows_non_causal(answer: dict, **_kw) -> CheckResult:
    """G3 — what_evidence_shows must not introduce unhedged causal conclusions."""
    wes = answer.get("what_evidence_shows")
    lines = [wes] if isinstance(wes, str) else (wes or [])
    # assertions: 1 per line
    for line in lines:
        # Pattern: "X caused/drove/led to Y" (active causal verb, no hedge)
        causal = re.search(
            r"\b(caused|caused by|drove|driven by|led to|resulted in|triggered)\b",
            str(line), re.IGNORECASE,
        )
        hedge = re.search(
            r"\b(may|might|could|appears|seems|possibly|unclear|not (yet )?established)\b",
            str(line), re.IGNORECASE,
        )
        if causal and not hedge:
            return "FAIL", f"unhedged causal claim in what_evidence_shows: {str(line)[:80]!r}"
    return "PASS", "evidence section uses appropriately hedged language"


def check_economic_qualifier_discipline(answer: dict, **_kw) -> CheckResult:
    """G4 — what_may_mean_economically must not assert unrealized impacts as facts."""
    econ = str(answer.get("what_may_mean_economically") or "")
    # assertions: 2 checks
    # Pattern: "margin compressed" / "revenue declined" stated as fact, no hedge
    hard_assertion = re.search(
        r"\b(margins? (compressed|declined|deteriorated)|revenue (fell|declined|dropped)|"
        r"(caused|led to|resulted in) .*(?:loss|decline|compression|impact))\b",
        econ, re.IGNORECASE,
    )
    if hard_assertion:
        hedge = re.search(
            r"\b(may|might|could|if|not (yet )?established|not established|"
            r"not been (confirmed|demonstrated)|remains? (forward-looking|unconfirmed))\b",
            econ, re.IGNORECASE,
        )
        if not hedge:
            return "FAIL", f"unhedged economic assertion: {hard_assertion.group()!r}"
    return "PASS", "economic interpretation is appropriately hedged"


def check_runtime_sanitizer_compat(answer: dict, **_kw) -> CheckResult:
    """G5 — All investor-facing text must survive the runtime cleanPublicText() sanitizer.

    simple_answer is a hard gate (loadHybridAnswerCard returns null when empty).
    Other fields silently drop; we warn so authors don't lose investor content unexpectedly.
    Contract: governance/sanitizer_contract.json v{_SANITIZER_CONTRACT_VERSION}.
    """
    # assertion 1: simple_answer is a hard null-return gate
    simple = str(answer.get("simple_answer") or "")
    if not _would_survive_sanitizer(simple):
        matched = next(
            (p.pattern for p in _RUNTIME_NOISE_PATTERNS if p.search(simple)),
            "empty/trailing/malformed/filler",
        )
        return "FAIL", f"simple_answer rejected by runtime sanitizer (pattern: {matched!r})"

    # assertion 2: other investor-facing fields — warn if sanitizer would silently empty them
    silently_emptied: list[str] = []
    for field in ("what_may_mean_economically", "what_is_not_yet_proven"):
        val = str(answer.get(field) or "")
        if val and not _would_survive_sanitizer(val):
            silently_emptied.append(field)
    for field in ("what_evidence_shows", "key_points"):
        items = answer.get(field) or []
        if isinstance(items, list):
            n = sum(1 for item in items if item and not _would_survive_sanitizer(str(item)))
            if n:
                silently_emptied.append(f"{field}[{n} items]")

    if silently_emptied:
        return "WARN", f"sanitizer would silently empty: {silently_emptied}"
    return "PASS", "all investor-facing fields survive runtime sanitizer"


# ═══════════════════════════════════════════════════════════════════════════════
# RISK FAMILY — what-could-go-wrong
# ═══════════════════════════════════════════════════════════════════════════════

def _risk_only(fn):
    def wrapper(answer, question_id="", **kw):
        if _family(question_id) != "risk":
            return "SKIP", "not applicable to this question family"
        return fn(answer, question_id=question_id, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


@_risk_only
def check_risk_stale_worsening(answer: dict, **_kw) -> CheckResult:
    """R1 — LAST_OBSERVED_WORSENING ≠ CURRENTLY_WORSENING (M31 invariant).
    A risk last observed worsening in FY20-FY23 cannot be called 'currently worsening'
    without FY24-FY26 evidence."""
    text = _text(answer)
    # assertion 1: look for stale-period + currently-worsening pattern
    stale_period = re.search(r"\bFY(20|21|22|23)\b", text, re.IGNORECASE)
    currently_worsening = re.search(r"\bcurrently worsening\b", text, re.IGNORECASE)
    if not (stale_period and currently_worsening):
        return "PASS", "no stale-worsening pattern detected"
    # assertion 2: check if FY24-FY26 evidence also present (would legitimate 'currently worsening')
    recent = re.search(r"\bFY(24|25|26)\b", text, re.IGNORECASE)
    if not recent:
        return "FAIL", (
            "risk presented as 'currently worsening' but only pre-FY24 periods cited; "
            "LAST_OBSERVED_WORSENING ≠ CURRENTLY_WORSENING (M31 ADV-R1)"
        )
    return "PASS", "FY24-26 evidence present alongside current-worsening claim"


@_risk_only
def check_risk_severity_not_disruption(answer: dict, **_kw) -> CheckResult:
    """R2 — CRITICAL_RISK_SEVERITY ≠ ACTUAL_SERVICE_DISRUPTION (M33.5 invariant)."""
    text = _text(answer)
    # assertion 1: check if critical severity mentioned
    critical_sev = re.search(r"\b(critical|high|severe)\b.*\b(risk|severity)\b", text, re.IGNORECASE)
    if not critical_sev:
        return "PASS", "no critical-severity language to check"
    # assertion 2: check if disruption is asserted as realized (not conditional)
    disruption_realized = re.search(
        r"\b(critical|high|severe)\b.{0,60}\b(disrupted|service disruption|failure occurred|"
        r"operations (failed|halted|disrupted))\b",
        text, re.IGNORECASE,
    )
    if disruption_realized:
        hedge = re.search(r"\b(could|may|might|if|would)\b", text[:disruption_realized.start() + 80], re.IGNORECASE)
        if not hedge:
            return "FAIL", (
                f"severity label implies realized disruption without hedging: "
                f"{disruption_realized.group()!r} — CRITICAL_RISK_SEVERITY ≠ ACTUAL_SERVICE_DISRUPTION (M33.5)"
            )
    return "PASS", "severity language correctly not conflated with realized disruption"


@_risk_only
def check_risk_cyber_not_incident(answer: dict, **_kw) -> CheckResult:
    """R3 — CYBERSECURITY_EXPOSURE ≠ CONFIRMED_INCIDENT (M33.5 invariant)."""
    text = _text(answer)
    # assertion 1: cyber language present?
    cyber = re.search(r"\b(cybersecurity|cyber security|data breach|cyberattack)\b", text, re.IGNORECASE)
    if not cyber:
        return "SKIP", "no cybersecurity language in answer"
    # assertion 2: confirmed incident asserted?
    confirmed_incident = re.search(
        r"\b(cybersecurity|cyber).{0,60}\b(incident occurred|breach (occurred|confirmed|happened)|"
        r"attack (occurred|confirmed|happened)|confirmed (incident|breach|attack))\b",
        text, re.IGNORECASE,
    )
    if confirmed_incident:
        conditional = re.search(
            r"\b(could|may|might|if|would|potential|risk of)\b",
            text[max(0, confirmed_incident.start()-50):confirmed_incident.end() + 50],
            re.IGNORECASE,
        )
        if not conditional:
            return "FAIL", (
                f"cybersecurity incident asserted without conditional hedging: "
                f"{confirmed_incident.group()!r} — CYBERSECURITY_EXPOSURE ≠ CONFIRMED_INCIDENT (M33.5)"
            )
    return "PASS", "cybersecurity language correctly hedged as exposure, not confirmed incident"


@_risk_only
def check_risk_execution_not_failure(answer: dict, **_kw) -> CheckResult:
    """R4 — EXECUTION_RISK ≠ CONFIRMED_EXECUTION_FAILURE (M33.3 invariant)."""
    text = _text(answer)
    # assertion 1: look for confirmed-failure framing
    confirmed_fail = re.search(
        r"\b(failed to execute|execution (has )?failed|confirmed execution failure|"
        r"blueprint (was )?not executed|delivery failed)\b",
        text, re.IGNORECASE,
    )
    if not confirmed_fail:
        return "PASS", "no confirmed-execution-failure language"
    # assertion 2: check for risk framing (should say "risk of failing")
    risk_frame = re.search(r"\b(risk of|risk that|failure to execute)\b", text, re.IGNORECASE)
    if not risk_frame:
        return "FAIL", (
            f"execution framed as confirmed failure, not risk: {confirmed_fail.group()!r} — "
            "EXECUTION_RISK ≠ CONFIRMED_EXECUTION_FAILURE (M33.3)"
        )
    return "PASS", "execution language correctly framed as risk, not confirmed failure"


@_risk_only
def check_risk_no_consequence_bind(answer: dict, **_kw) -> CheckResult:
    """R5 — If consequence_status=NO_CONSEQUENCE_EVIDENCE, text must not assert realized impact."""
    dpfs = answer.get("deterministic_precision_facts") or []
    # assertion 1: find any NO_CONSEQUENCE_EVIDENCE DPF
    no_consequence_fields = []
    for d in dpfs:
        if isinstance(d, dict):
            val = str(d.get("value") or d.get("status") or "")
            if "NO_CONSEQUENCE_EVIDENCE" in val or "no_consequence_evidence" in val.lower():
                no_consequence_fields.append(str(d.get("field") or d.get("metric") or "unknown"))
    if not no_consequence_fields:
        return "PASS", "no NO_CONSEQUENCE_EVIDENCE DPFs to check against"
    text = _text(answer)
    # assertion 2: check text doesn't assert realized impact
    realized_impact = re.search(
        r"\b(caused|resulted in|led to|produced).{0,60}\b(loss|decline|compression|impact|"
        r"disruption|financial impact|revenue impact|margin impact)\b",
        text, re.IGNORECASE,
    )
    if realized_impact:
        # Check if it's hedged
        hedge = re.search(
            r"\b(may|might|could|not (yet )?established|not established)\b",
            text[max(0, realized_impact.start()-30):realized_impact.end() + 50],
            re.IGNORECASE,
        )
        if not hedge:
            return "FAIL", (
                f"consequence asserted despite NO_CONSEQUENCE_EVIDENCE in DPF "
                f"(fields: {no_consequence_fields}): {realized_impact.group()!r}"
            )
    return "PASS", f"NO_CONSEQUENCE_EVIDENCE DPF binding respected (fields: {no_consequence_fields})"


@_risk_only
def check_risk_sector_not_company(answer: dict, company: str = "", **_kw) -> CheckResult:
    """R6 — Industry/sector-wide risk must not be presented as company-specific.
    Special case: banking AUM sector decline ≠ Ujjivan AUM decline (M33.3 UJR18)."""
    text = _text(answer)
    sector = _sector(company)
    # assertion 1: sector-wide language
    sector_patterns = {
        "banking": re.compile(
            r"\b(across the (microfinance|banking|sector|industry)|"
            r"(microfinance|banking) (sector|industry).*decline|"
            r"industry.wide.*AUM)\b", re.IGNORECASE,
        ),
        "pharma": re.compile(
            r"\b(across the (pharma(ceutical)?|generic|drug) (sector|industry)|"
            r"industry.wide (pricing|regulatory|competitive) pressure)\b", re.IGNORECASE,
        ),
    }
    pattern = sector_patterns.get(sector)
    if not pattern:
        return "SKIP", f"no sector-specific check for sector={sector!r}"
    sector_match = pattern.search(text)
    if not sector_match:
        return "PASS", "no sector-wide language detected"
    # assertion 2: check if it's correctly attributed as sector vs company
    # Look for company-specific attribution nearby that would constitute conflation
    conflation = re.search(
        r"\b" + re.escape(company.replace("_", " ")) + r"\b.{0,60}\b(decline|fell|worsened|deteriorated)\b",
        text, re.IGNORECASE,
    )
    if conflation:
        return "WARN", (
            f"sector-wide language ({sector_match.group()!r}) near company-specific claim — "
            "verify SECTOR_RISK ≠ COMPANY_SPECIFIC (M33.3 UJR18)"
        )
    return "PASS", "sector-wide language correctly distinguished from company-specific context"


@_risk_only
def check_risk_duplicate_identity(answer: dict, **_kw) -> CheckResult:
    """R7 — Same risk identity must not be listed as two distinct risks in a count claim.

    M33.2 TR14/TR15 invariant: the same risk from the same FY source must not be counted twice.
    The invariant concerns SOURCE-LEVEL duplication in a stated risk count (e.g., "N risks identified"),
    NOT multiple mentions of the same risk ID across different fields of a single answer.

    A risk ID legitimately appears in both what_evidence_shows and key_points to provide
    context in each field. This is correct structure, not a duplicate count.

    The check tests: does a stated count claim (e.g., "5 currently worsening risks") appear to
    be inflated by a clearly duplicate risk named identically in consecutive evidence items?
    """
    # assertion 1: look for risk IDs in key_points only (count claims live here)
    # Multiple risk IDs across ALL fields is normal; duplicates WITHIN key_points is suspicious.
    key_points_text = " ".join(
        str(x) for x in (answer.get("key_points") or [])
    )
    risk_ids_in_kp = re.findall(r"\brisk_[0-9a-f]{16}\b", key_points_text)
    from collections import Counter
    if risk_ids_in_kp:
        kp_counts = Counter(risk_ids_in_kp)
        kp_duplicates = [r for r, c in kp_counts.items() if c > 1]
        if kp_duplicates:
            return "FAIL", (
                f"same risk ID appears twice within key_points — likely double-counted: {kp_duplicates}"
            )
    # assertion 2: look for same-description consecutive evidence items (SAME_RISK from M33.2)
    # If two consecutive evidence items share >70% of their words, they may be the same risk.
    wes = answer.get("what_evidence_shows") or []
    if isinstance(wes, list) and len(wes) >= 2:
        for i in range(len(wes) - 1):
            a_words = set(str(wes[i]).lower().split())
            b_words = set(str(wes[i + 1]).lower().split())
            if len(a_words) > 4 and len(b_words) > 4:
                overlap = len(a_words & b_words) / max(len(a_words), len(b_words))
                if overlap > 0.7:
                    return "WARN", (
                        f"consecutive evidence items share {overlap:.0%} word overlap — "
                        "verify no SAME_RISK double-count (M33.2 TR14/TR15)"
                    )
    return "PASS", "no duplicate risk identity detected"


# ═══════════════════════════════════════════════════════════════════════════════
# MANAGEMENT PROMISES FAMILY
# ═══════════════════════════════════════════════════════════════════════════════

def _promise_only(fn):
    def wrapper(answer, question_id="", **kw):
        if _family(question_id) != "promises":
            return "SKIP", "not applicable to this question family"
        return fn(answer, question_id=question_id, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


@_promise_only
def check_promise_deadline_not_missed(answer: dict, **_kw) -> CheckResult:
    """P1 — DEADLINE_PASSED ≠ MISSED; NO_FOLLOW_UP ≠ FAILED (M25 invariant)."""
    text = _text(answer)
    # assertion 1: "deadline passed" → must not say "missed" or "failed"
    deadline_fail = re.search(
        r"\b(deadline (passed|expired|lapsed)).{0,60}\b(missed|failed to deliver|not delivered)\b",
        text, re.IGNORECASE,
    )
    if deadline_fail:
        return "FAIL", (
            f"deadline passage conflated with missed/failed: {deadline_fail.group()!r} — "
            "DEADLINE_PASSED ≠ MISSED (M25)"
        )
    # assertion 2: "no follow-up" → must not say "failed"
    no_followup_fail = re.search(
        r"\b(no follow.?up|no update|no confirmation).{0,60}\b(failed|failure|not delivered)\b",
        text, re.IGNORECASE,
    )
    if no_followup_fail:
        return "FAIL", (
            f"absence of follow-up conflated with failure: {no_followup_fail.group()!r} — "
            "NO_FOLLOW_UP ≠ FAILED (M25)"
        )
    return "PASS", "deadline and follow-up language correctly disciplined"


@_promise_only
def check_promise_hard_commitment_only(answer: dict, **_kw) -> CheckResult:
    """P2 — Only HARD_COMMITMENT/VERIFIABLE_COMMITMENT triggers delivery tracking (M23 invariant)."""
    text = _text(answer)
    # assertion 1: strategic intents not called commitments requiring delivery
    soft_as_hard = re.search(
        r"\b(strategic intent|aspiration|stated direction|stated goal|stated vision).{0,80}"
        r"\b(committed|delivered|achieved|on track|overdue|deadline)\b",
        text, re.IGNORECASE,
    )
    if soft_as_hard:
        return "FAIL", (
            f"strategic intent/aspiration presented as tracked commitment: "
            f"{soft_as_hard.group()!r} — only HARD_COMMITMENT requires delivery tracking (M23)"
        )
    return "PASS", "commitment taxonomy correctly applied"


@_promise_only
def check_promise_similar_wording_not_canonical(answer: dict, **_kw) -> CheckResult:
    """P3 — SIMILAR_WORDING ≠ CANONICAL_LINK (M23 invariant)."""
    text = _text(answer)
    # assertion 1: deduplicated commitments should be identified by canonical IDs, not just similar wording
    # If same commitment stated twice without explicit MC ID dedup annotation, it's a risk
    # This is a heuristic warning, not a hard fail
    duplicate_phrases = []
    simple_answer = str(answer.get("simple_answer") or "")
    # Look for counts: if "28 commitments" and "27 unique" both present, dedup was done right
    raw_and_unique = re.search(r"\d+\s*raw.*\d+\s*unique|\d+\s*unique.*\d+\s*raw", simple_answer, re.IGNORECASE)
    # An MC ID mentioned across multiple sections (simple_answer, what_is_not_yet_proven,
    # key_points, what_to_monitor) is correct structure — the same commitment is tracked
    # end-to-end. Only flag if the same MC ID appears within the SAME evidence item list,
    # which would suggest duplicate listing of the same commitment in a count.
    wes = answer.get("what_evidence_shows") or []
    if isinstance(wes, list) and len(wes) >= 2:
        from collections import Counter
        wes_mc_ids = re.findall(r"\b(MC-\w+)\b", " ".join(str(x) for x in wes))
        wes_counts = Counter(wes_mc_ids)
        wes_dupes = [mc for mc, cnt in wes_counts.items() if cnt > 1]
        if wes_dupes:
            return "WARN", (
                f"MC IDs appear multiple times within what_evidence_shows: {wes_dupes} — "
                "verify no duplicate commitment listing (M23 P3)"
            )
    return "PASS", "no canonical-link deduplication issues detected"


# ═══════════════════════════════════════════════════════════════════════════════
# DELIVERY HISTORY FAMILY
# ═══════════════════════════════════════════════════════════════════════════════

def _delivery_only(fn):
    def wrapper(answer, question_id="", **kw):
        if _family(question_id) != "delivery":
            return "SKIP", "not applicable to this question family"
        return fn(answer, question_id=question_id, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


@_delivery_only
def check_delivery_intention_not_delivery(answer: dict, **_kw) -> CheckResult:
    """D1 — INTENTION ≠ DELIVERY; announced ≠ delivered (M27 invariant)."""
    text = _text(answer)
    # assertion 1: "announced/promised/committed" → then "delivered"
    intention_as_delivery = re.search(
        r"\b(announced|committed to|promised|planned to|intends? to).{0,80}\b(delivered|achieved|completed)\b",
        text, re.IGNORECASE,
    )
    if intention_as_delivery:
        # Check if there's explicit stage separation
        stage_sep = re.search(
            r"\b(Unable to Verify|ANNOUNCED|unverified|not yet|no confirmation)\b",
            text, re.IGNORECASE,
        )
        if not stage_sep:
            return "FAIL", (
                f"intention framed as delivery without stage separation: "
                f"{intention_as_delivery.group()!r} — INTENTION ≠ DELIVERY (M27)"
            )
    return "PASS", "delivery stage correctly separated from intention"


@_delivery_only
def check_delivery_not_economic_outcome(answer: dict, **_kw) -> CheckResult:
    """D2 — DELIVERY ≠ ECONOMIC_OUTCOME without attribution evidence (M27 invariant)."""
    text = _text(answer)
    # assertion 1: "delivered X → created value / generated returns"
    delivery_to_value = re.search(
        r"\b(delivered|completed|executed).{0,80}\b(created value|value creation|"
        r"generated (returns?|revenue)|economic outcome|attributable return)\b",
        text, re.IGNORECASE,
    )
    if delivery_to_value:
        attribution = re.search(
            r"\b(directly attributable|attribution confirmed|with confirmed|economically confirmed)\b",
            text, re.IGNORECASE,
        )
        if not attribution:
            return "FAIL", (
                f"delivery conflated with economic outcome without attribution: "
                f"{delivery_to_value.group()!r} — DELIVERY ≠ ECONOMIC_OUTCOME (M27)"
            )
    return "PASS", "delivery and economic outcome correctly separated"


@_delivery_only
def check_delivery_no_bridge_violation(answer: dict, **_kw) -> CheckResult:
    """D3 — Execution activity must not be linked to commitment without canonical MC ID (ENG-119 bridge)."""
    text = _text(answer)
    # assertion 1: execution described as delivery-linked without MC reference
    exec_as_delivery = re.search(
        r"\b(executed|completed|operational).{0,100}\b(commitment|promise|pledg)\b",
        text, re.IGNORECASE,
    )
    if exec_as_delivery:
        has_mc_id = re.search(r"\bMC-\d{4}\b", text)
        if not has_mc_id:
            return "WARN", (
                "execution activity linked to commitment language without canonical MC ID — "
                "verify bridge contract (ENG-119)"
            )
    return "PASS", "no bridge violation detected"


# ═══════════════════════════════════════════════════════════════════════════════
# CAPITAL ALLOCATION FAMILY
# ═══════════════════════════════════════════════════════════════════════════════

def _capital_only(fn):
    def wrapper(answer, question_id="", **kw):
        if _family(question_id) not in ("capital",):
            return "SKIP", "not applicable to this question family"
        return fn(answer, question_id=question_id, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


@_capital_only
def check_capital_transaction_not_operating(answer: dict, **_kw) -> CheckResult:
    """C1 — TRANSACTION_VALUE ≠ OPERATING_VALUE (M17/M22 invariant)."""
    text = _text(answer)
    # assertion 1: dividend/buyback framed as generating operational returns
    tx_as_operating = re.search(
        r"\b(dividend|share buyback|debt repay).{0,80}\b(generated|produced|created).{0,40}"
        r"\b(operating|operational|business) (return|value|income)\b",
        text, re.IGNORECASE,
    )
    if tx_as_operating:
        return "FAIL", (
            f"transaction value (dividend/buyback) conflated with operating return: "
            f"{tx_as_operating.group()!r} — TRANSACTION_VALUE ≠ OPERATING_VALUE (M17)"
        )
    return "PASS", "transaction and operating value correctly distinguished"


@_capital_only
def check_capital_no_unattributed_roi(answer: dict, **_kw) -> CheckResult:
    """C2 — ROI/return claims must be attribution-confirmed (M22 invariant)."""
    text = _text(answer)
    # assertion 1: ROI or return percentage without attribution
    roi_claim = re.search(
        r"\b(ROI|return on (capital|investment|capex)|generated? [\d]+%? return)\b",
        text, re.IGNORECASE,
    )
    if roi_claim:
        attributed = re.search(
            r"\b(directly attributable|attribution (confirmed|established)|"
            r"economically (attributed|confirmed)|confirmed (return|outcome))\b",
            text, re.IGNORECASE,
        )
        if not attributed:
            return "WARN", (
                f"ROI/return claim without explicit attribution confirmation: {roi_claim.group()!r} — "
                "verify against ENG-122 attribution taxonomy (M22)"
            )
    return "PASS", "no unattributed ROI claims found"


@_capital_only
def check_capital_associated_not_causal(answer: dict, **_kw) -> CheckResult:
    """C3 — ASSOCIATED_NOT_ATTRIBUTABLE must not be promoted to DIRECTLY_ATTRIBUTABLE (M22 invariant)."""
    text = _text(answer)
    # assertion 1: acquisition outcomes presented as causally proven
    acq_causal = re.search(
        r"\b(acquisition|acquired).{0,100}\b(caused|drove|produced|generated|resulted in).{0,60}"
        r"\b(revenue|profit|margin|return|growth)\b",
        text, re.IGNORECASE,
    )
    if acq_causal:
        assoc_hedge = re.search(
            r"\b(associated|co-occurrence|temporal|context|alongside|following)\b",
            text[max(0, acq_causal.start()-50):acq_causal.end() + 80],
            re.IGNORECASE,
        )
        if not assoc_hedge:
            return "FAIL", (
                f"acquisition outcome presented as causally proven without association hedge: "
                f"{acq_causal.group()!r} — ASSOCIATED_NOT_ATTRIBUTABLE (M22)"
            )
    return "PASS", "acquisition outcomes correctly hedged"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTOR-SPECIFIC: Banking
# ═══════════════════════════════════════════════════════════════════════════════

def _banking_only(fn):
    def wrapper(answer, company="", **kw):
        if _sector(company) != "banking":
            return "SKIP", "not applicable to non-banking company"
        return fn(answer, company=company, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


@_banking_only
def check_banking_no_industrial_working_capital(answer: dict, **_kw) -> CheckResult:
    """B1 — Banking working capital logic must not be applied (M21 ADV-U5 invariant)."""
    text = _text(answer)
    # assertions: 2 checks
    wc_days = re.search(r"\b(receivable days|inventory days|payable days|working capital days)\b", text, re.IGNORECASE)
    if wc_days:
        return "FAIL", (
            f"industrial working-capital metric in banking answer: {wc_days.group()!r} — "
            "working capital days inapplicable to bank portfolio (M21 ADV-U5)"
        )
    # Banking-specific: check that loan receivables not called "receivables" in industrial sense
    industrial_receivables = re.search(r"\b(trade receivables|accounts receivable)\b", text, re.IGNORECASE)
    if industrial_receivables:
        return "WARN", (
            f"industrial receivables language in banking answer: {industrial_receivables.group()!r}"
        )
    return "PASS", "no industrial working-capital logic detected in banking answer"


@_banking_only
def check_banking_sector_aum_not_company(answer: dict, company: str = "", **_kw) -> CheckResult:
    """B2 — SECTOR_AUM_DECLINE ≠ UJJIVAN_AUM_DECLINE (M33.3 UJR18 invariant)."""
    text = _text(answer)
    # assertion 1: AUM decline language
    aum_decline = re.search(r"\b(AUM|assets under management).{0,60}\b(declined|fell|dropped|worsened)\b", text, re.IGNORECASE)
    if not aum_decline:
        return "PASS", "no AUM decline language"
    # assertion 2: is it attributed to company specifically or sector?
    sector_attrib = re.search(
        r"\b(across (the )?(microfinance|banking|sector|industry)|"
        r"(microfinance|banking) (sector|industry) (AUM|AUM decline))\b",
        text, re.IGNORECASE,
    )
    if sector_attrib:
        company_specific = re.search(
            r"\b" + re.escape(company) + r"\b.{0,60}\b(AUM|assets).{0,40}\b(declined|fell|dropped)\b",
            text, re.IGNORECASE,
        )
        if company_specific:
            return "FAIL", (
                "sector-wide AUM decline conflated with company-specific AUM — "
                "SECTOR_AUM_DECLINE ≠ COMPANY_AUM_DECLINE (M33.3 UJR18)"
            )
        return "PASS", "AUM decline correctly attributed to sector, not company-specific"
    return "PASS", "AUM decline language present without sector conflation"


def check_full_artifact_digest(answer: dict, company: str = "", question_id: str = "", **_kw) -> CheckResult:
    """G6 — Full-artifact digest (SHA-256 including DPFs) must match registry record.
    Catches DPF tampering that legacy MD5 fingerprint cannot detect.
    Only enforced when registry contains full_artifact_digest for this pair.
    """
    if not company or not question_id:
        return "SKIP", "company or question_id not provided"
    try:
        if not _APPROVAL_REGISTRY_PATH.exists():
            return "FAIL", "approval_registry.json not found"
        with open(_APPROVAL_REGISTRY_PATH) as f:
            registry = json.load(f)
        record = registry.get("approvals", {}).get(f"{company}:{question_id}")
        if not record:
            return "FAIL", f"no approval registry record for {company}:{question_id}"
        stored_digest = record.get("full_artifact_digest")
        if not stored_digest:
            return "SKIP", "no full_artifact_digest in registry (legacy approval — migration pending)"
        # Compute SHA-256 of full answer including DPFs
        computed = hashlib.sha256(
            json.dumps(answer, sort_keys=True, ensure_ascii=True).encode()
        ).hexdigest()
        if computed != stored_digest:
            return "FAIL", f"full_artifact_digest mismatch: computed={computed[:16]}... stored={stored_digest[:16]}..."
        return "PASS", f"full_artifact_digest verified: {computed[:16]}..."
    except Exception as exc:
        return "FAIL", f"full_artifact_digest check error: {exc}"


# ═══════════════════════════════════════════════════════════════════════════════
# MANAGEMENT QUALITY FAMILY — how-good-is-management (M37/M37.1)
# ═══════════════════════════════════════════════════════════════════════════════

def _mq_only(fn):
    def wrapper(answer, question_id="", **kw):
        if _family(question_id) != "management_quality":
            return "SKIP", "not applicable to this question family"
        return fn(answer, question_id=question_id, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


@_mq_only
def check_mq_no_promise_to_delivered(answer: dict, **_kw) -> CheckResult:
    """MQ-01 — PROMISE ≠ DELIVERED; stated ≠ verified (M37.1 invariant)."""
    text = _text(answer)
    promise_delivered = re.search(
        r"\b(promised|committed to|stated.{0,30}will|pledged).{0,120}"
        r"\b(confirmed delivered|delivered as promised|delivered this commitment)\b",
        text, re.IGNORECASE,
    )
    if promise_delivered:
        verified = re.search(r"\b(verified|confirmed|independent evidence)\b", text, re.IGNORECASE)
        if not verified:
            return "FAIL", (
                f"promise presented as confirmed delivery without independent verification: "
                f"{promise_delivered.group()!r} — PROMISE ≠ DELIVERED (MQ-01)"
            )
    return "PASS", "no promise-to-delivered conflation detected"


@_mq_only
def check_mq_deadline_not_missed(answer: dict, **_kw) -> CheckResult:
    """MQ-02 — DEADLINE_PASSED ≠ COMMITMENT_FAILED; absence of confirmation ≠ failure (M37.1 invariant)."""
    text = _text(answer)
    deadline_failed = re.search(
        r"\b(deadline.{0,60}(passed|elapsed|expired)|target (date|year).{0,60}(passed|missed)).{0,80}"
        r"\b(commitment failed|failed to deliver|missed commitment|delivery failed)\b",
        text, re.IGNORECASE,
    )
    if deadline_failed:
        hedge = re.search(
            r"\b(unable to verify|unverified|not confirmed|no disclosure|not established)\b",
            text, re.IGNORECASE,
        )
        if not hedge:
            return "FAIL", (
                f"deadline passage presented as confirmed failure without verification: "
                f"{deadline_failed.group()!r} — DEADLINE_PASSED ≠ FAILED (MQ-02)"
            )
    return "PASS", "deadline/failure distinction correctly maintained"


@_mq_only
def check_mq_strategy_change_not_contradiction(answer: dict, **_kw) -> CheckResult:
    """MQ-03 — STRATEGY_CHANGED ≠ MANAGEMENT_CONTRADICTION unless prior commitment was HARD (M37.1 invariant)."""
    text = _text(answer)
    strategy_contradiction = re.search(
        r"\b(strategy (changed|pivoted|shifted)).{0,100}"
        r"\b(contradicts?|inconsistent with|reversal of|abandons?).{0,60}\b(commitment|promise|stated goal)\b",
        text, re.IGNORECASE,
    )
    if strategy_contradiction:
        hard_commitment = re.search(r"\b(hard commitment|HARD_COMMITMENT|verifiable commitment)\b", text, re.IGNORECASE)
        if not hard_commitment:
            return "WARN", (
                "strategy change framed as contradiction without confirming the prior was a HARD_COMMITMENT — "
                "STRATEGY_CHANGED ≠ CONTRADICTION for strategic intents (MQ-03)"
            )
    return "PASS", "strategy change framing is appropriate"


@_mq_only
def check_mq_spending_not_good_strategy(answer: dict, **_kw) -> CheckResult:
    """MQ-04 — SPENDING_ALIGNED ≠ GOOD_STRATEGY; alignment doesn't confirm value (M37.1 invariant)."""
    text = _text(answer)
    aligned_is_good = re.search(
        r"\b(capital.{0,40}aligned with|spending.{0,40}aligned with).{0,80}"
        r"\b(confirms? (good|sound|quality|wise) strategy|validates? strategy|demonstrates? quality)\b",
        text, re.IGNORECASE,
    )
    if aligned_is_good:
        return "FAIL", (
            f"spending alignment presented as confirming strategy quality: "
            f"{aligned_is_good.group()!r} — SPENDING_ALIGNED ≠ GOOD_STRATEGY (MQ-04)"
        )
    return "PASS", "spending alignment correctly not conflated with strategy quality"


@_mq_only
def check_mq_project_complete_not_value(answer: dict, **_kw) -> CheckResult:
    """MQ-05 — PROJECT_COMPLETED ≠ VALUE_CREATED; execution ≠ economic return (M37.1 invariant)."""
    text = _text(answer)
    project_to_value = re.search(
        r"\b(project.{0,40}(completed|delivered)|initiative.{0,40}(completed|delivered)).{0,120}"
        r"\b(value created|created (significant )?(value|return)|generated (economic|operating) (return|value))\b",
        text, re.IGNORECASE,
    )
    if project_to_value:
        attribution = re.search(
            r"\b(directly attributable|attribution confirmed|with confirmed (return|outcome)|"
            r"economic outcome.{0,40}confirmed)\b",
            text, re.IGNORECASE,
        )
        if not attribution:
            return "FAIL", (
                f"project completion conflated with value creation without attribution evidence: "
                f"{project_to_value.group()!r} — PROJECT_COMPLETED ≠ VALUE_CREATED (MQ-05)"
            )
    return "PASS", "project completion and value creation correctly separated"


@_mq_only
def check_mq_financial_improvement_not_causation(answer: dict, **_kw) -> CheckResult:
    """MQ-06 — FINANCIAL_IMPROVEMENT ≠ MANAGEMENT_CAUSED; correlation ≠ causation (M37.1 invariant)."""
    text = _text(answer)
    fin_caused = re.search(
        r"\b(revenue|margin|profit|EBITDA|ROE|ROCE).{0,60}"
        r"\b(improved|grew|expanded).{0,80}"
        r"\b(because of management|management (caused|drove|delivered|produced)|due to management)\b",
        text, re.IGNORECASE,
    )
    if fin_caused:
        hedge = re.search(
            r"\b(causal attribution.{0,30}not established|not directly attributable|"
            r"attribution not (available|established)|cannot be attributed)\b",
            text, re.IGNORECASE,
        )
        if not hedge:
            return "FAIL", (
                f"financial improvement attributed to management without causal evidence: "
                f"{fin_caused.group()!r} — FINANCIAL_IMPROVEMENT ≠ MANAGEMENT_CAUSATION (MQ-06)"
            )
    return "PASS", "financial improvement and management causation correctly separated"


@_mq_only
def check_mq_risk_unmentioned_not_resolved(answer: dict, **_kw) -> CheckResult:
    """MQ-07 — RISK_NOT_MENTIONED ≠ RISK_RESOLVED; absence of disclosure ≠ resolution (M37.1 invariant)."""
    text = _text(answer)
    absence_resolved = re.search(
        r"\b(no longer (mentioned|disclosed|flagged)|risk (removed|no longer present|dropped from)).{0,80}"
        r"\b(resolved|addressed|mitigated|no longer a risk)\b",
        text, re.IGNORECASE,
    )
    if absence_resolved:
        confirmed = re.search(
            r"\b(confirmed (resolved|addressed|mitigated)|resolution (confirmed|verified|evidence))\b",
            text, re.IGNORECASE,
        )
        if not confirmed:
            return "FAIL", (
                f"risk described as resolved based on absence of mention without confirmation: "
                f"{absence_resolved.group()!r} — RISK_UNMENTIONED ≠ RESOLVED (MQ-07)"
            )
    return "PASS", "risk absence correctly not conflated with resolution"


@_mq_only
def check_mq_mitigation_announced_not_effective(answer: dict, **_kw) -> CheckResult:
    """MQ-08 — MITIGATION_ANNOUNCED ≠ MITIGATION_EFFECTIVE; announcement ≠ outcome (M37.1 invariant)."""
    text = _text(answer)
    announced_effective = re.search(
        r"\b(announced|introduced|implemented).{0,60}(mitigation|risk management|risk reduction).{0,80}"
        r"\b(is effective|is working|has mitigated|has reduced|has addressed|resolved the risk)\b",
        text, re.IGNORECASE,
    )
    if announced_effective:
        outcome_evidence = re.search(
            r"\b(outcome confirmed|measurable reduction|quantified|evidence of effectiveness)\b",
            text, re.IGNORECASE,
        )
        if not outcome_evidence:
            return "FAIL", (
                f"mitigation announcement presented as confirmed effective without outcome evidence: "
                f"{announced_effective.group()!r} — MITIGATION_ANNOUNCED ≠ EFFECTIVE (MQ-08)"
            )
    return "PASS", "mitigation effectiveness correctly requires outcome evidence"


@_mq_only
def check_mq_acquisition_complete_not_well_executed(answer: dict, **_kw) -> CheckResult:
    """MQ-09 — ACQUISITION_COMPLETED ≠ EXECUTED_WELL; transaction closed ≠ integration success (M37.1 invariant)."""
    text = _text(answer)
    acq_well = re.search(
        r"\b(acquisition.{0,40}(completed|closed|finalised|finalized)).{0,100}"
        r"\b(executed well|well.?executed|successful (integration|acquisition)|"
        r"integration (successful|completed successfully|a success))\b",
        text, re.IGNORECASE,
    )
    if acq_well:
        integration_evidence = re.search(
            r"\b(revenue contribution (confirmed|verified|evidenced)|"
            r"integration (outcomes?|metrics?) (confirmed|evidenced|verified|documented))\b",
            text, re.IGNORECASE,
        )
        if not integration_evidence:
            return "FAIL", (
                f"acquisition completion presented as evidence of good execution without integration outcomes: "
                f"{acq_well.group()!r} — ACQUISITION_COMPLETED ≠ EXECUTED_WELL (MQ-09)"
            )
    return "PASS", "acquisition execution correctly requires outcome evidence"


@_mq_only
def check_mq_repeated_statement_not_commitment(answer: dict, **_kw) -> CheckResult:
    """MQ-10 — REPEATED_STATEMENT ≠ HARD_COMMITMENT; frequency ≠ commitment strength (M37.1 invariant)."""
    text = _text(answer)
    repeated_is_committed = re.search(
        r"\b(repeated (across|in) \d+|consistently (stated|mentioned|said)).{0,80}"
        r"\b(hard commitment|firm commitment|committed to deliver|strong commitment)\b",
        text, re.IGNORECASE,
    )
    if repeated_is_committed:
        return "FAIL", (
            f"repeated statement presented as hard commitment: "
            f"{repeated_is_committed.group()!r} — REPEATED_STATEMENT ≠ HARD_COMMITMENT (MQ-10)"
        )
    return "PASS", "statement frequency correctly not conflated with commitment strength"


@_mq_only
def check_mq_one_success_not_consistent(answer: dict, **_kw) -> CheckResult:
    """MQ-11 — ONE_SUCCESS ≠ CONSISTENT_CAPABILITY; single instance ≠ pattern (M37.1 invariant)."""
    text = _text(answer)
    single_is_pattern = re.search(
        r"\b(one (delivered|successful|confirmed)).{0,120}"
        r"\b(demonstrates? (consistent|proven|reliable) capability|"
        r"pattern of (delivery|execution|success)|consistently (delivers?|executes?|succeeds?))\b",
        text, re.IGNORECASE,
    )
    if single_is_pattern:
        multi_evidence = re.search(r"\b(\d+|multiple|several|consistent(ly)?).{0,20}(delivered|confirmed|achieved)\b", text, re.IGNORECASE)
        count = re.search(r"\b([3-9]|\d{2,}) (confirmed|delivered|completed)\b", text, re.IGNORECASE)
        if not (multi_evidence and count):
            return "WARN", (
                "single delivery instance used to assert consistent capability pattern — "
                "verify count ≥ 3 confirmed deliveries (MQ-11)"
            )
    return "PASS", "capability claims appropriately supported by multiple instances"


@_mq_only
def check_mq_one_failure_not_poor_management(answer: dict, **_kw) -> CheckResult:
    """MQ-12 — ONE_FAILURE ≠ POOR_MANAGEMENT; single miss ≠ overall management quality (M37.1 invariant)."""
    text = _text(answer)
    single_failure_overall = re.search(
        r"\b(one (missed|failed|delayed|undelivered)).{0,120}"
        r"\b(poor management|poor (delivery|execution) quality|management (is|are) (weak|poor|ineffective))\b",
        text, re.IGNORECASE,
    )
    if single_failure_overall:
        return "FAIL", (
            f"single failure generalized to overall management quality judgment: "
            f"{single_failure_overall.group()!r} — ONE_FAILURE ≠ POOR_MANAGEMENT (MQ-12)"
        )
    return "PASS", "single failures not generalized to overall management quality"


@_mq_only
def check_mq_cash_return_not_shareholder_friendly(answer: dict, **_kw) -> CheckResult:
    """MQ-13 — CASH_RETURN ≠ SHAREHOLDER_FRIENDLY_INTENT; transaction ≠ value orientation (M37.1 invariant)."""
    text = _text(answer)
    cash_is_friendly = re.search(
        r"\b(dividend|buyback|share repurchase|cash return).{0,80}"
        r"\b(demonstrates? (shareholder.?friendly|shareholder value orientation|commitment to shareholders)|"
        r"confirms? management is shareholder.?friendly|management (is|are) shareholder.?friendly)\b",
        text, re.IGNORECASE,
    )
    if cash_is_friendly:
        return "FAIL", (
            f"cash return transaction presented as confirming shareholder-friendly intent: "
            f"{cash_is_friendly.group()!r} — CASH_RETURN ≠ SHAREHOLDER_FRIENDLY_INTENT (MQ-13)"
        )
    return "PASS", "cash return correctly not conflated with management intent quality"


@_mq_only
def check_mq_roce_improvement_not_quality_confirmed(answer: dict, **_kw) -> CheckResult:
    """MQ-14 — ROCE_IMPROVEMENT ≠ MANAGEMENT_QUALITY_CONFIRMED; metric ≠ quality proof (M37.1 invariant)."""
    text = _text(answer)
    roce_quality = re.search(
        r"\bROCE.{0,60}(improved|increased|expanded).{0,80}"
        r"\b(confirms? (management quality|good management|quality management)|"
        r"demonstrates? (management quality|management capability|quality of management))\b",
        text, re.IGNORECASE,
    )
    if roce_quality:
        return "FAIL", (
            f"ROCE improvement presented as confirming management quality: "
            f"{roce_quality.group()!r} — ROCE_IMPROVEMENT ≠ QUALITY_CONFIRMED (MQ-14)"
        )
    return "PASS", "ROCE improvement correctly not conflated with management quality confirmation"


@_mq_only
def check_mq_unknown_outcome_not_failure(answer: dict, **_kw) -> CheckResult:
    """MQ-15 — UNKNOWN_OUTCOME ≠ FAILED_OUTCOME; unverified ≠ failed (M37.1 invariant)."""
    text = _text(answer)
    unknown_is_failed = re.search(
        r"\b(unable to verify|unverified|not confirmed|not established|no public disclosure).{0,100}"
        r"\b(therefore failed|means? (failed|not delivered|unsuccessful)|"
        r"(failed|unsuccessful) because (unverified|not confirmed|not established))\b",
        text, re.IGNORECASE,
    )
    if unknown_is_failed:
        return "FAIL", (
            f"unknown/unverified outcome presented as confirmed failure: "
            f"{unknown_is_failed.group()!r} — UNKNOWN_OUTCOME ≠ FAILED_OUTCOME (MQ-15)"
        )
    return "PASS", "unverified outcomes correctly not conflated with failed outcomes"


@_mq_only
def check_mq_no_rating_leakage(answer: dict, **_kw) -> CheckResult:
    """MQ-R1 — MANAGEMENT_EVALUATIVE_JUDGMENT_LEAKAGE (M37.1/M37.3 invariant).

    Blocks three classes of management-quality judgment:
    A. Direct rating labels: management is weak/strong/mixed/poor
    B. Quality label phrases: disciplined management, capable management, credible management
    C. Implied capability upgrades: genuine/proven/demonstrated management capability/competence/quality

    Does NOT block factual metrics: strong capital ratio, high EBITDA margin, demonstrated revenue growth,
    demonstrated project completion — these describe events/metrics, not management quality.
    The distinguishing principle: block when quality upgrade targets management/execution capability,
    allow when it targets a financial metric, a ratio, or a specific event.
    """
    # Check investor-rendered fields AND internal consistency fields (M37.5: extended scope)
    ALL_INVESTOR_FIELDS = [
        "simple_answer", "what_evidence_shows", "what_may_mean_economically",
        "what_is_not_yet_proven", "what_to_monitor", "key_points",
        "where_management_was_consistent",  # M37.5: internal consistency field, must also be clean
    ]

    # Pattern A: direct rating labels + shorthand + MQ meta-references (M37.5: MQ weakness/strength added)
    _DIRECT_RATINGS = re.compile(
        r"\b(management quality is (weak|mixed|strong|poor|good|excellent)|"
        r"management is (weak|mixed|strong|poor|good|excellent)|"
        r"management (quality|rating) (score|assessment|label)|"
        r"assessed as (WEAK|MIXED|STRONG)|rating:\s*(WEAK|MIXED|STRONG|weak|mixed|strong))\b"
        # Shorthand notation: "MQ overall: WEAK", "MQ overall: MIXED (stable)", etc.
        r"|(?:MQ|Management quality|Management rating|Overall management quality)"
        r"(?:\s+overall)?\s*[:\-—]\s*"
        r"(?:WEAK|MIXED|STRONG|weak|mixed|strong|Weak|Mixed|Strong)"
        r"(?:\s*\([^)]*\))?"
        # M37.5: MQ meta-references ("MQ weakness is...", "MQ strength")
        r"|\bMQ (weakness|strength)\b"
        # M37.5: individual dimension ratings ("candor weak", "risk handling weak")
        r"|\bcandor (is |)(weak|strong|mixed|poor|good)\b"
        r"|\brisk.?handling (is |)(weak|strong|mixed|poor|good)\b",
        re.IGNORECASE,
    )

    # Pattern B: quality label phrases — adjective modifying "management" as subject/quality holder
    # Only block when the adjective upgrades the quality of management itself, not a metric.
    # M37.5: added strong/weak as trigger adjectives; execution credibility; coherent direction;
    #        reversed "discipline is strong/weak"; weak transparency; standalone allocator forms.
    _QUALITY_LABELS = re.compile(
        r"\b(disciplined|capable|competent|credible|effective|trustworthy|high.?quality|impressive|"
        r"reliable|proven|superior|strong|weak) (management|execution|capital allocation|allocator)\b"
        r"|\bmanagement (is|has been|appears|shows|has proven itself to be|proves? itself to be) "
        r"(disciplined|capable|competent|credible|effective|"
        r"trustworthy|reliable|high.?quality|proven|superior|impressive)\b"
        r"|\b(shareholder.?friendly|good|disciplined|credible) (capital )?allocator\b"
        r"|\bshareholder.?friendly management\b"
        r"|\bmanagement deserves confidence\b"
        r"|\bmanagement (execution )?quality is (high|good|strong|established|verified|confirmed)\b"
        # M37.5 additions
        r"|\bexecution credibility\b"
        r"|\bcoherent (management|direction|execution)\b"
        r"|\b(management|direction|execution) is coherent\b"
        r"|\b(execution|capital allocation) discipline is (strong|weak|mixed|poor|good)\b"
        r"|\bweak (commitment.level )?transparency\b"
        r"|\b(disciplined|strong|capable|credible) allocation\b",
        re.IGNORECASE,
    )

    # Pattern C: implied capability upgrades — "genuine/proven/demonstrated" + management quality noun
    # Financial nouns (capital ratio, EBITDA margin, NIM, etc.) are not in the targets list so they
    # never trigger this regex — no allowlist needed.
    _CAPABILITY_UPGRADES = re.compile(
        r"\b(genuine|proven|demonstrate[sd]?|demonstrated|strong|high) (management |execution |delivery |capital )??"
        r"(capability|competence|quality|discipline|credibility|execution ability|delivery capability|"
        r"execution quality|management quality|execution competence|management execution)\b",
        re.IGNORECASE,
    )

    hits = []
    for field in ALL_INVESTOR_FIELDS:
        val = answer.get(field, "")
        text = " ".join(val) if isinstance(val, list) else str(val)
        if not text:
            continue

        # Pattern A
        m = _DIRECT_RATINGS.search(text)
        if m:
            hits.append(f"{field}[A-direct-rating]: {m.group()!r}")
            continue

        # Pattern B
        m = _QUALITY_LABELS.search(text)
        if m:
            hits.append(f"{field}[B-quality-label]: {m.group()!r}")
            continue

        # Pattern C
        for m in _CAPABILITY_UPGRADES.finditer(text):
            hits.append(f"{field}[C-capability-upgrade]: {m.group()!r}")
            break

    if hits:
        return "FAIL", f"management evaluative judgment leaked into investor-facing fields: {hits} — MQ-R1"
    return "PASS", "no management evaluative judgment in investor-facing fields"


@_mq_only
def check_mq_behavioral_descriptor_present(answer: dict, **_kw) -> CheckResult:
    """MQ-R2 — simple_answer must contain a behavioral delivery descriptor (M37.1 invariant)."""
    simple = str(answer.get("simple_answer") or "")
    DESCRIPTORS = [
        "FOLLOW_THROUGH_LARGELY_UNVERIFIED",
        "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS",
        "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS",
        "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED",
    ]
    has_descriptor = any(d in simple for d in DESCRIPTORS)
    if not has_descriptor:
        return "FAIL", (
            "simple_answer missing behavioral delivery descriptor — "
            "must contain one of: FOLLOW_THROUGH_LARGELY_UNVERIFIED, "
            "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS, "
            "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS, "
            "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED (MQ-R2)"
        )
    return "PASS", f"behavioral delivery descriptor present in simple_answer"


@_mq_only
def check_mq_no_dpf_rating_leakage(answer: dict, **_kw) -> CheckResult:
    """MQ-R3 — DPFs must NOT contain management-quality ratings (M37.5 invariant).

    DPF contract:
      ALLOWED: counts, amounts, periods, source-backed statuses, evidence-confidence metadata
      BLOCKED: management quality rating, competence judgment, credibility judgment,
               execution-quality score, capital-allocation quality rating, candor rating,
               overall grade/tier

    Two checks:
      1. Metric name is a synthesis-dimension label (blocked by name alone)
      2. Value is a bare quality rating (WEAK/MIXED/STRONG as the entire value or at start)
    """
    _DPF_BLOCKED_METRIC = re.compile(
        r"\bmanagement quality\b"
        r"|\bexecution discipline\b"
        r"|\bcapital allocation discipline\b"
        r"|\bcandor\b"
        r"|\brisk.?handling\b"
        r"|\bowner alignment\b"
        r"|\bmanagement credibility\b"
        r"|\bmanagement overall\b",
        re.IGNORECASE,
    )
    # Bare WEAK/MIXED/STRONG at start of value (optionally followed by semicolon/whitespace)
    _DPF_BLOCKED_VALUE = re.compile(
        r"^\s*(WEAK|MIXED|STRONG)\s*($|;|\s)",
        re.IGNORECASE | re.MULTILINE,
    )

    dpfs = answer.get("deterministic_precision_facts") or []
    hits = []
    for i, dpf in enumerate(dpfs):
        metric = str(dpf.get("metric") or "")
        value = str(dpf.get("value") or "")

        m = _DPF_BLOCKED_METRIC.search(metric)
        if m:
            hits.append(f"dpf[{i}].metric[blocked-rating-dimension]: {m.group()!r}")
            continue  # metric already blocked, skip value check for this DPF

        m = _DPF_BLOCKED_VALUE.search(value)
        if m:
            hits.append(f"dpf[{i}].value[blocked-rating-value]: {m.group().strip()!r}")

    if hits:
        return "FAIL", f"DPF management rating leakage: {hits} — MQ-R3"
    return "PASS", "no DPF management rating leakage"


@_mq_only
def check_mq_no_metric_inference(answer: dict, **_kw) -> CheckResult:
    """MQ-R4 — METRIC_TO_INFERENCE_GUARD (M37.6 invariant).

    A factual metric (FCF/PAT ratio, cash conversion, delivery count) must not be
    automatically upgraded to a management-quality judgment (working-capital discipline,
    capital efficiency, execution capability, strategy success).

    Blocked patterns:
    - FCF/cash conversion → working-capital discipline / capital efficiency
    - capital efficiency narrative (standalone)
    - working capital discipline (inference label in consistency maps or investor fields)
    - EBITDA/margin → management quality (via demonstrates/confirms)
    - dividend consistency → capital discipline (via proves/confirms)
    - revenue growth → management strategy successful (via confirms)
    """
    _INFERENCE = re.compile(
        # FCF/PAT or cash conversion → efficiency or discipline label
        r"\bFCF.{0,120}\b(confirms?|proves?|demonstrates?|establishes?|shows?|supports?)\b"
        r".{0,80}\b(working.?capital discipline|capital efficiency|capital allocation (quality|discipline))\b"
        r"|\b(cash conversion|FCF.?PAT).{0,80}"
        r"\b(confirms?|proves?|demonstrates?|supports?)\b.{0,60}"
        r"\b(capital efficiency|capital discipline|efficiency)\b"
        # Standalone inference labels
        r"|\bcapital efficiency narrative\b"
        r"|\bworking capital discipline\b"
        # EBITDA/margin → management quality
        r"|\b(EBITDA|margin|NPM|PAT)\b.{0,80}"
        r"\b(demonstrates?|confirms?|shows?|proves?)\b.{0,60}"
        r"\bmanagement (quality|capability|excellence)\b"
        # Dividend consistency → capital discipline
        r"|\b(dividend consistency|dividends.{0,20}(paid|confirmed)).{0,100}"
        r"\b(proves?|confirms?|demonstrates?)\b.{0,60}"
        r"\bcapital (discipline|allocation quality)\b"
        # Revenue growth → strategy successful
        r"|\brevenue growth.{0,80}"
        r"\b(confirms?|proves?|shows?)\b.{0,60}"
        r"\bmanagement strategy.{0,40}successful\b"
        # Revenue growth → strategy working (M37.8)
        r"|\brevenue growth.{0,80}\b(proves?|confirms?|shows?)\b.{0,60}"
        r"\bstrategy.{0,30}(is )?working\b"
        # Metric → structural economic / pricing-power inference (M37.8)
        r"|\b(suggest[s]?|indicate[s]?|demonstrates?|confirms?|establishes?|proves?|implies?)\b.{0,120}"
        r"\b(structural\s+|durable\s+|sustainable\s+)?pricing power\b"
        r"|\b(confirms?|suggest[s]?|indicates?|demonstrates?|establishes?|proves?)\b.{0,80}"
        r"\bsuperior capital allocation\b"
        r"|\b(suggest[s]?|indicate[s]?|demonstrates?|confirms?|establishes?|proves?|implies?)\b.{0,120}"
        r"\b(durable|strong)\s+(competitive\s+)?moat\b"
        # Measurement activity ≠ outcome quality (M37.8)
        r"|\b(survey[s]?|assessment[s]?|audit[s]?|certification[s]?).{0,120}"
        r"\b(confirm\w*|prove\w*|demonstrate\w*|establish\w*)\b.{0,80}"
        r"\b(service quality|control effectiveness|consistent quality|quality is consistent)\b"
        r"|\btraining.{0,60}(completion|delivered|conducted).{0,100}"
        r"\b(demonstrate\w*|prove\w*|confirm\w*)\b.{0,80}"
        r"\b(improved|enhanced)\b.{0,60}\b(capability|effectiveness)\b"
        r"|\bgrievance.{0,50}(mechanism|system).{0,120}"
        r"\b(prove\w*|demonstrate\w*|confirm\w*)\b.{0,80}"
        r"\b(effectively resolved|handled effectively)\b"
        r"|\bcertification.{0,80}\b(confirm\w*|prove\w*)\b.{0,60}"
        r"\b(quality|superior quality|product quality)\b"
        # Quality label as consistency-map key when evidence is only measurement (M37.8)
        r"|\b(service quality|customer quality).{0,30}"
        r"\b(CONSISTENT|confirmed|established)\b.{0,80}"
        r"\b(assessment[s]?|survey[s]?|audit[s]?).{0,40}delivered\b",
        re.IGNORECASE,
    )

    _INVESTOR_FIELDS = [
        "simple_answer", "what_evidence_shows", "what_may_mean_economically",
        "what_is_not_yet_proven", "what_to_monitor", "key_points",
        "where_management_was_consistent",
    ]

    hits = []
    for field in _INVESTOR_FIELDS:
        val = answer.get(field, "")
        text = " ".join(val) if isinstance(val, list) else str(val)
        if not text:
            continue
        m = _INFERENCE.search(text)
        if m:
            hits.append(f"{field}: {m.group()!r}")

    for i, dpf in enumerate(answer.get("deterministic_precision_facts") or []):
        sm = str(dpf.get("semantic_meaning") or "")
        if sm:
            m = _INFERENCE.search(sm)
            if m:
                hits.append(f"dpf[{i}].semantic_meaning: {m.group()!r}")

    for k, v in (answer.get("management_consistency_map") or {}).items():
        m = _INFERENCE.search(f"{k}: {v}")
        if m:
            hits.append(f"management_consistency_map[{k!r}]: {m.group()!r}")

    if hits:
        return "FAIL", f"metric-to-inference upgrade detected: {hits} — MQ-R4"
    return "PASS", "no unsupported metric-to-inference upgrades"


@_mq_only
def check_mq_comparative_integrity(answer: dict, **_kw) -> CheckResult:
    """MQ-R5 — COMPARATIVE_INTEGRITY_GUARD (M37.6 invariant).

    Comparative claims require an explicit cohort with deterministic values.
    Superlatives without evidence are unsupported inferences.

    Blocked without explicit comparison context:
    - strongest/best/worst/weakest/exceptional/superior/leading in delivery/execution context
    - unusual in accountability/mechanism context
    - highest/lowest/second-highest delivery rate without explicit comparison values

    Allowed: claims accompanied by named cohort + deterministic values
    (e.g., "compared with", two or more % figures, "among [N]-company cohort").
    """
    # Absolute superlatives — block unconditionally in delivery/execution/management context
    _ABSOLUTE = re.compile(
        r"\b(strongest|best|worst|weakest|exceptional|superior|leading)\b"
        r".{0,80}"
        r"\b(delivery (rate|record|count|percentage)|execution (record|capability|quality)|"
        r"management (record|capability)|in (the )?(dataset|cohort))\b"
        r"|\bunusual\b.{0,80}"
        r"\b(accountability|mechanism|external (evidence|assessment|accountability)|track record)\b",
        re.IGNORECASE,
    )

    # Relative superlatives — block when no explicit comparison evidence is present
    _RELATIVE = re.compile(
        r"\b(highest|lowest|second.highest|second.lowest)\b"
        r".{0,80}"
        r"\b(delivery rate|delivered.item rate|in (the )?(dataset|cohort|4.company|4-company))\b",
        re.IGNORECASE,
    )

    # Explicit comparison evidence that permits relative superlatives
    _COMPARISON_EVIDENCE = re.compile(
        r"\bcompared (with|to)\b"
        r"|\b\d+%.{0,30}\d+%"
        r"|\bamong.{0,40}cohort\b",
        re.IGNORECASE,
    )

    _INVESTOR_FIELDS = [
        "simple_answer", "what_evidence_shows", "what_may_mean_economically",
        "what_is_not_yet_proven", "what_to_monitor", "key_points",
        "where_management_was_consistent",
    ]

    hits = []
    for field in _INVESTOR_FIELDS:
        val = answer.get(field, "")
        text = " ".join(val) if isinstance(val, list) else str(val)
        if not text:
            continue
        m = _ABSOLUTE.search(text)
        if m:
            hits.append(f"{field}[absolute-superlative]: {m.group()!r}")
            continue
        m = _RELATIVE.search(text)
        if m and not _COMPARISON_EVIDENCE.search(text):
            hits.append(f"{field}[relative-superlative-no-comparison]: {m.group()!r}")

    for i, dpf in enumerate(answer.get("deterministic_precision_facts") or []):
        sm = str(dpf.get("semantic_meaning") or "")
        if not sm:
            continue
        m = _ABSOLUTE.search(sm)
        if m:
            hits.append(f"dpf[{i}].semantic_meaning[absolute-superlative]: {m.group()!r}")
            continue
        m = _RELATIVE.search(sm)
        if m and not _COMPARISON_EVIDENCE.search(sm):
            hits.append(f"dpf[{i}].semantic_meaning[relative-superlative-no-comparison]: {m.group()!r}")

    if hits:
        return "FAIL", f"unsupported comparative claim: {hits} — MQ-R5"
    return "PASS", "no unsupported comparative claims"


@_mq_only
def check_mq_lifecycle_consistency(answer: dict, **_kw) -> CheckResult:
    """MQ-R6 — LIFECYCLE_CONSISTENCY_GUARD (M37.8 invariant).

    A downstream investor-facing statement cannot claim a later lifecycle stage
    than upstream evidence supports:
      acquisition completed → does NOT imply → integration completed
      integration completed → does NOT imply → revenue attributed
      revenue attributed    → does NOT imply → economic value created
      capex spent           → does NOT imply → capacity operational
      capacity operational  → does NOT imply → revenue generated
      revenue generated     → does NOT imply → return on capital proven
    """
    _LIFECYCLE_OVERCLAIM = re.compile(
        # Acquisition/entity described as a revenue contributor (attribution implied)
        r"\brevenue contributor\b"
        # Integration claimed as successfully completed
        r"|\bintegration (was )?successfully completed\b"
        r"|\bsuccessfully integrated\b"
        # Acquisition asserted to have created economic or shareholder value
        r"|\bacquisition.{0,100}\b(created|generates?|deliver[s]?)\b.{0,60}"
        r"\b(shareholder value|economic value|value creation)\b"
        r"|\b(created|generates?)\b.{0,60}\bshareholder value\b"
        # Capex/investment asserted to be generating returns without return evidence
        r"|\b(investment|capex).{0,100}\bgenerating returns\b",
        re.IGNORECASE,
    )
    _INVESTOR_FIELDS = [
        "simple_answer", "what_evidence_shows", "what_may_mean_economically",
        "what_is_not_yet_proven", "what_to_monitor", "key_points",
        "where_management_was_consistent",
    ]
    hits = []
    for field in _INVESTOR_FIELDS:
        val = answer.get(field, "")
        text = " ".join(val) if isinstance(val, list) else str(val)
        if not text:
            continue
        m = _LIFECYCLE_OVERCLAIM.search(text)
        if m:
            hits.append(f"{field}: {m.group()!r}")
    for i, dpf in enumerate(answer.get("deterministic_precision_facts") or []):
        sm = str(dpf.get("semantic_meaning") or "")
        if sm:
            m = _LIFECYCLE_OVERCLAIM.search(sm)
            if m:
                hits.append(f"dpf[{i}].semantic_meaning: {m.group()!r}")
    for k, v in (answer.get("management_consistency_map") or {}).items():
        m = _LIFECYCLE_OVERCLAIM.search(f"{k}: {v}")
        if m:
            hits.append(f"management_consistency_map[{k!r}]: {m.group()!r}")
    if hits:
        return "FAIL", f"lifecycle stage overclaim detected: {hits} — MQ-R6"
    return "PASS", "no lifecycle consistency violations"


# ═══════════════════════════════════════════════════════════════════════════════
# Registry and dispatch
# ═══════════════════════════════════════════════════════════════════════════════

# All validator functions in dispatch order
GLOBAL_VALIDATORS = [
    check_no_forbidden_public_terms,
    check_uncertainty_discipline,
    check_evidence_shows_non_causal,
    check_economic_qualifier_discipline,
    check_runtime_sanitizer_compat,
    # check_full_artifact_digest is NOT in GLOBAL_VALIDATORS — it runs against the real stored
    # artifact (not fixture answers) via Stage K / --mode certify. For adversarial fixture
    # testing use mode_test_trust's "full_artifact_digest_check" category (see NF-24).
]

FAMILY_VALIDATORS: dict[str, list] = {
    "risk": [
        check_risk_stale_worsening,
        check_risk_severity_not_disruption,
        check_risk_cyber_not_incident,
        check_risk_execution_not_failure,
        check_risk_no_consequence_bind,
        check_risk_sector_not_company,
        check_risk_duplicate_identity,
    ],
    "promises": [
        check_promise_deadline_not_missed,
        check_promise_hard_commitment_only,
        check_promise_similar_wording_not_canonical,
    ],
    "delivery": [
        check_delivery_intention_not_delivery,
        check_delivery_not_economic_outcome,
        check_delivery_no_bridge_violation,
    ],
    "capital": [
        check_capital_transaction_not_operating,
        check_capital_no_unattributed_roi,
        check_capital_associated_not_causal,
    ],
    "management_quality": [
        check_mq_no_promise_to_delivered,
        check_mq_deadline_not_missed,
        check_mq_strategy_change_not_contradiction,
        check_mq_spending_not_good_strategy,
        check_mq_project_complete_not_value,
        check_mq_financial_improvement_not_causation,
        check_mq_risk_unmentioned_not_resolved,
        check_mq_mitigation_announced_not_effective,
        check_mq_acquisition_complete_not_well_executed,
        check_mq_repeated_statement_not_commitment,
        check_mq_one_success_not_consistent,
        check_mq_one_failure_not_poor_management,
        check_mq_cash_return_not_shareholder_friendly,
        check_mq_roce_improvement_not_quality_confirmed,
        check_mq_unknown_outcome_not_failure,
        check_mq_no_rating_leakage,
        check_mq_behavioral_descriptor_present,
        check_mq_no_dpf_rating_leakage,
        check_mq_no_metric_inference,       # MQ-R4 (M37.6)
        check_mq_comparative_integrity,     # MQ-R5 (M37.6)
        check_mq_lifecycle_consistency,     # MQ-R6 (M37.8)
    ],
}

SECTOR_VALIDATORS: dict[str, list] = {
    "banking": [
        check_banking_no_industrial_working_capital,
        check_banking_sector_aum_not_company,
    ],
}


def run_adversarial_suite(
    answer: dict[str, Any],
    company: str,
    question_id: str,
) -> dict[str, Any]:
    """
    Run all applicable adversarial checks for (answer, company, question_id).
    Returns:
      {
        "checks": {check_name: {result, detail}},
        "named_checks": int,
        "assertions_approx": int,  # approximate; see function docstrings
        "fails": [check_names],
        "warns": [check_names],
        "skips": [check_names],
        "incomplete": [check_names],
        "overall": PASS|FAIL|WARN|INCOMPLETE,
        "coverage_note": str,
      }
    """
    family = _family(question_id)
    sector = _sector(company)

    validators = list(GLOBAL_VALIDATORS)
    validators += FAMILY_VALIDATORS.get(family, [])
    validators += SECTOR_VALIDATORS.get(sector, [])

    if family == "unknown":
        return {
            "checks": {},
            "named_checks": 0,
            "assertions_approx": 0,
            "fails": [],
            "warns": [],
            "skips": [],
            "incomplete": [],
            "overall": "INCOMPLETE",
            "coverage_note": f"CERTIFICATION_INCOMPLETE — no validator registered for question_id={question_id!r}",
        }

    checks: dict[str, dict] = {}
    fails, warns, skips, incomplete = [], [], [], []

    for fn in validators:
        name = fn.__name__
        try:
            result, detail = fn(answer, company=company, question_id=question_id)
        except Exception as exc:
            result, detail = "INCOMPLETE", f"validator raised {type(exc).__name__}: {exc}"
        checks[name] = {"result": result, "detail": detail}
        if result == "FAIL":
            fails.append(name)
        elif result == "WARN":
            warns.append(name)
        elif result == "SKIP":
            skips.append(name)
        elif result == "INCOMPLETE":
            incomplete.append(name)

    # Count named checks (all called) and approximate assertions
    named_checks = len(validators)
    # Each function runs ~2 re.search assertions on average (documented in docstrings)
    # This is an approximation; exact counts are in each function's docstring.
    assertions_approx = named_checks * 2

    active_checks = [v for v in validators if v.__name__ not in [s for s in skips]]
    family_registered = bool(FAMILY_VALIDATORS.get(family))
    sector_registered = bool(SECTOR_VALIDATORS.get(sector))

    if incomplete:
        overall = "INCOMPLETE"
    elif fails:
        overall = "FAIL"
    elif warns:
        overall = "WARN"
    else:
        overall = "PASS"

    coverage_note = (
        f"family={family!r}: {'registered' if family_registered else 'NO_VALIDATORS_REGISTERED'}, "
        f"sector={sector!r}: {'registered' if sector_registered else 'no sector-specific validators'}"
    )
    if not family_registered:
        overall = "INCOMPLETE"
        coverage_note += " — CERTIFICATION_INCOMPLETE"

    return {
        "checks": checks,
        "named_checks": named_checks,
        "assertions_approx": assertions_approx,
        "active_checks": len(validators) - len(skips),
        "fails": fails,
        "warns": warns,
        "skips": skips,
        "incomplete": incomplete,
        "overall": overall,
        "coverage_note": coverage_note,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Negative Fixture Library — used by --mode test-trust
# ═══════════════════════════════════════════════════════════════════════════════

NEGATIVE_FIXTURES: list[dict[str, Any]] = [
    # NF-01: Stale worsening — risk last worsened FY22, called "currently worsening" without FY24-26 support
    {
        "id": "NF-01",
        "description": "Risk last worsened FY22 presented as currently worsening",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_risk_stale_worsening",
        "answer": {
            "simple_answer": "Technology risk worsened significantly in FY22 and is currently worsening.",
            "what_evidence_shows": ["FY22=high severity; this is currently worsening."],
            "what_may_mean_economically": "Margins may compress if this continues.",
            "what_is_not_yet_proven": "Whether actual financial impact has occurred.",
            "what_to_monitor": ["Monitor FY27 for continuation."],
            "key_points": ["Technology risk: FY22=high, currently worsening"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-02: Critical severity → realized disruption
    {
        "id": "NF-02",
        "description": "Critical risk severity conflated with realized service disruption",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_risk_severity_not_disruption",
        "answer": {
            "simple_answer": "Third-party ecosystem dependency is critical severity; partners disrupted service in FY26.",
            "what_evidence_shows": ["FY26=critical severity. Partners disrupted service."],
            "what_may_mean_economically": "Service disruption affected delivery.",
            "what_is_not_yet_proven": "Nothing further.",
            "what_to_monitor": ["Watch for further disruption."],
            "key_points": ["Critical risk; service disruption occurred FY26"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-03: Cybersecurity incident asserted as confirmed
    {
        "id": "NF-03",
        "description": "Cybersecurity incident presented as confirmed without hedge",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_risk_cyber_not_incident",
        "answer": {
            "simple_answer": "A cybersecurity incident occurred in FY26 affecting platform operations.",
            "what_evidence_shows": ["FY26: cybersecurity incident confirmed."],
            "what_may_mean_economically": "Operational consequences followed.",
            "what_is_not_yet_proven": "Financial magnitude.",
            "what_to_monitor": ["Monitor security posture."],
            "key_points": ["Cybersecurity incident occurred FY26"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-04: Execution framed as confirmed failure
    {
        "id": "NF-04",
        "description": "Execution risk framed as confirmed delivery failure",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_risk_execution_not_failure",
        "answer": {
            "simple_answer": "Tanla failed to execute international expansion in FY26.",
            "what_evidence_shows": ["FY26: execution failed. Blueprint not executed."],
            "what_may_mean_economically": "Revenue targets not met.",
            "what_is_not_yet_proven": "Future recovery.",
            "what_to_monitor": ["Watch FY27 expansion."],
            "key_points": ["Execution failed FY26"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-05: Consequence asserted despite NO_CONSEQUENCE_EVIDENCE DPF
    {
        "id": "NF-05",
        "description": "Impact claimed despite NO_CONSEQUENCE_EVIDENCE DPF",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_risk_no_consequence_bind",
        "answer": {
            "simple_answer": "Third-party dependency caused margin compression in FY26.",
            "what_evidence_shows": ["FY26: dependency caused margin compression."],
            "what_may_mean_economically": "This resulted in significant margin impact.",
            "what_is_not_yet_proven": "Whether FY27 will recover.",
            "what_to_monitor": ["Watch for margin recovery."],
            "key_points": ["Margin compression caused by third-party FY26"],
            "deterministic_precision_facts": [
                {"field": "supply_chain_consequence_status", "value": "NO_CONSEQUENCE_EVIDENCE"}
            ],
        },
    },
    # NF-06: Industrial working capital logic applied to banking
    {
        "id": "NF-06",
        "description": "Industrial working-capital metrics used for banking company",
        "company": "ujjivan",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_banking_no_industrial_working_capital",
        "answer": {
            "simple_answer": "Ujjivan has working capital concerns; receivable days reached 180 in FY25.",
            "what_evidence_shows": ["FY25: receivable days=180, inventory days=45."],
            "what_may_mean_economically": "Working capital risk is rising.",
            "what_is_not_yet_proven": "Whether management will address this.",
            "what_to_monitor": ["Monitor receivable days and inventory days."],
            "key_points": ["Receivable days=180 FY25"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-07: Sector AUM decline conflated with company AUM
    {
        "id": "NF-07",
        "description": "Industry-wide AUM decline attributed to Ujjivan specifically",
        "company": "ujjivan",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_banking_sector_aum_not_company",
        "answer": {
            "simple_answer": "Microfinance sector AUM declined across the industry. Ujjivan AUM fell accordingly.",
            "what_evidence_shows": ["FY25: microfinance sector AUM declined. Ujjivan AUM declined."],
            "what_may_mean_economically": "Revenue impact expected.",
            "what_is_not_yet_proven": "Recovery timeline.",
            "what_to_monitor": ["Watch Ujjivan AUM trends."],
            "key_points": ["Sector AUM decline equals Ujjivan AUM decline"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-08: Management intention presented as delivery
    {
        "id": "NF-08",
        "description": "Management intention presented as confirmed delivery",
        "company": "sun_pharma",
        "question_id": "what-did-management-actually-deliver",
        "expected_fail": "check_delivery_intention_not_delivery",
        "answer": {
            "simple_answer": "Sun Pharma committed to launch ILUMYA in Japan and has delivered this milestone.",
            "what_evidence_shows": ["Management committed to Japan ILUMYA; this was delivered."],
            "what_may_mean_economically": "Revenue expansion achieved.",
            "what_is_not_yet_proven": "Future commercial scale.",
            "what_to_monitor": ["Watch revenue from Japan."],
            "key_points": ["ILUMYA Japan: committed and delivered"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-09: Delivery conflated with economic outcome
    {
        "id": "NF-09",
        "description": "Delivery conflated with economic value creation without attribution",
        "company": "sun_pharma",
        "question_id": "what-did-management-actually-deliver",
        "expected_fail": "check_delivery_not_economic_outcome",
        "answer": {
            "simple_answer": "Project Alchemee was executed and delivered, generating significant returns.",
            "what_evidence_shows": ["Alchemee executed and completed, creating value for shareholders."],
            "what_may_mean_economically": "Delivery generated operating returns of 15%.",
            "what_is_not_yet_proven": "Long-term sustainability.",
            "what_to_monitor": ["Watch Alchemee revenue."],
            "key_points": ["Alchemee delivered; economic outcome confirmed"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-10: Deadline passed = missed (promise family)
    {
        "id": "NF-10",
        "description": "Deadline passage conflated with missed commitment",
        "company": "tanla",
        "question_id": "what-has-management-promised",
        "expected_fail": "check_promise_deadline_not_missed",
        "answer": {
            "simple_answer": "Tanla's FY25 deadline passed and management missed this commitment.",
            "what_evidence_shows": ["Deadline passed. Management missed FY25 commitment."],
            "what_may_mean_economically": "Reliability concern raised.",
            "what_is_not_yet_proven": "Whether delivery will occur.",
            "what_to_monitor": ["Watch FY27 for resolution."],
            "key_points": ["MC-0019: deadline passed; missed"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-11: Fingerprint mismatch (structural — not content check)
    {
        "id": "NF-11",
        "description": "Fingerprint mismatch against governance record",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "fingerprint_check",  # handled in Stage D, not adversarial
        "answer": {
            "simple_answer": "This is a tampered answer with a different fingerprint.",
            "what_evidence_shows": ["Tampered evidence."],
            "what_may_mean_economically": "Tampered economic interpretation.",
            "what_is_not_yet_proven": "Whether the tampering will be noticed.",
            "what_to_monitor": ["Monitor integrity checks."],
            "key_points": ["Tampered answer"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-12: Transaction value as operating return
    {
        "id": "NF-12",
        "description": "Dividend presented as generating operating business return",
        "company": "tanla",
        "question_id": "how-is-capital-allocated",
        "expected_fail": "check_capital_transaction_not_operating",
        "answer": {
            "simple_answer": "Dividend payments generated significant operating returns for Tanla.",
            "what_evidence_shows": ["Dividend of ₹5/share generated operational value."],
            "what_may_mean_economically": "This produced operating returns for the business.",
            "what_is_not_yet_proven": "Sustainability of returns.",
            "what_to_monitor": ["Watch dividend yield."],
            "key_points": ["Dividends produced operating return"],
            "deterministic_precision_facts": [],
        },
    },
    # ── Regression fixtures added in M34.2 to test fixed validators ──────────────
    # PC-01 (Positive Control): check_uncertainty_discipline must PASS on "none established"
    # A valid uncertainty section uses "— none established" as a trailing negation.
    {
        "id": "PC-01",
        "description": "[POSITIVE CONTROL] Valid answer using 'none established' negation form — must PASS G2",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": None,  # must NOT fail check_uncertainty_discipline
        "answer": {
            "simple_answer": "Tanla faces third-party dependency concentration risk as of FY25.",
            "what_evidence_shows": ["FY25: three major telcos account for >70% of Trubloq revenue."],
            "what_may_mean_economically": "Revenue concentration may compress margins.",
            "what_is_not_yet_proven": "Whether third-party dependency mechanism is established; whether FY26 entries reflect a new incident — none established.",
            "what_to_monitor": ["Watch FY26 telco revenue share."],
            "key_points": ["Ecosystem concentration: FY25=HIGH"],
            "deterministic_precision_facts": [],
        },
    },
    # PC-02 (Positive Control): check_uncertainty_discipline must PASS on "No confirmed X"
    # A valid uncertainty section uses "No confirmed execution link" as a negation.
    {
        "id": "PC-02",
        "description": "[POSITIVE CONTROL] Valid answer using 'No confirmed X' negation form — must PASS G2",
        "company": "tanla",
        "question_id": "what-did-management-actually-deliver",
        "expected_fail": None,
        "answer": {
            "simple_answer": "MC-0004 remains Unable To Verify across FY22–FY26.",
            "what_evidence_shows": ["FY22: profitability focus stated. No delivery milestone in evidence."],
            "what_may_mean_economically": "Delivery may have occurred but cannot be verified.",
            "what_is_not_yet_proven": "MC-0004 (FY22 — profitability focus): No confirmed execution link. Unable To Verify. MC-0019 (FY25): Deadline passed. No score-target confirmation.",
            "what_to_monitor": ["Watch FY27 disclosures for MC-0004 confirmation."],
            "key_points": ["MC-0004: Unable To Verify FY22–FY26"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-13: check_uncertainty_discipline must still FAIL on genuine definitive claim in NIYTF
    {
        "id": "NF-13",
        "description": "Definitive confirmed claim in what_is_not_yet_proven — must FAIL G2",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_uncertainty_discipline",
        "answer": {
            "simple_answer": "Tanla faces technology scalability risk in FY25.",
            "what_evidence_shows": ["FY25: technology cost pressures observed."],
            "what_may_mean_economically": "Margins may compress.",
            "what_is_not_yet_proven": "The margin impact has been confirmed and demonstrated in the FY25 results.",
            "what_to_monitor": ["Watch FY26 margins."],
            "key_points": ["Technology risk: FY25"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-14: check_risk_duplicate_identity must still FAIL on genuinely double-listed risk in key_points
    {
        "id": "NF-14",
        "description": "Same risk ID listed twice in key_points (double-counted risk) — must FAIL R7",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_risk_duplicate_identity",
        "answer": {
            "simple_answer": "Tanla has 3 worsening risks in FY25.",
            "what_evidence_shows": [
                "FY25: technology risk (risk_abc123def456abcd) escalated.",
                "FY25: supply-chain risk (risk_111222333444aaaa) elevated.",
            ],
            "what_may_mean_economically": "Multiple concurrent risks may compress margins.",
            "what_is_not_yet_proven": "Whether risks will compound.",
            "what_to_monitor": ["Watch FY26 for risk crystallization."],
            "key_points": [
                "Technology risk: risk_abc123def456abcd — CURRENTLY_WORSENING FY25",
                "Supply-chain risk: risk_111222333444aaaa — CURRENTLY_WORSENING FY25",
                "Technology risk: risk_abc123def456abcd — counted again as separate risk",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # NF-15: check_no_forbidden_public_terms must still FAIL on HARD_COMMITMENT in narrative
    {
        "id": "NF-15",
        "description": "Internal taxonomy label HARD_COMMITMENT in investor-facing evidence — must FAIL G1",
        "company": "sun_pharma",
        "question_id": "what-has-management-promised",
        "expected_fail": "check_no_forbidden_public_terms",
        "answer": {
            "simple_answer": "Sun Pharma has 4 hard commitments remaining Unable To Verify.",
            "what_evidence_shows": ["Total: 46; HARD_COMMITMENT: 4; SOFT_INTENT: 37"],
            "what_may_mean_economically": "Tracking commitments requires delivery evidence.",
            "what_is_not_yet_proven": "Whether commitments were abandoned or deferred.",
            "what_to_monitor": ["Watch FY27 for delivery confirmation."],
            "key_points": ["4 hard commitments remain Unable To Verify"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-16: Runtime sanitizer rejects "canonical" in simple_answer (the M35.1 root cause)
    {
        "id": "NF-16",
        "description": "Internal pipeline term 'canonical' in simple_answer — must FAIL G5",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_runtime_sanitizer_compat",
        "answer": {
            "simple_answer": "FY26 canonical describes the risk of failing to execute international expansion blueprint.",
            "what_evidence_shows": ["FY26: canonical risk — international expansion."],
            "what_may_mean_economically": "Revenue growth may stall if expansion fails.",
            "what_is_not_yet_proven": "Whether expansion targets have been abandoned.",
            "what_to_monitor": ["Watch FY27 for international revenue contribution."],
            "key_points": ["FY26: international expansion risk"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-17: Runtime sanitizer rejects "llm" in simple_answer
    {
        "id": "NF-17",
        "description": "Internal infra term 'llm' in simple_answer — must FAIL G5",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_runtime_sanitizer_compat",
        "answer": {
            "simple_answer": "Tanla faces dependency risk — the llm component underlies route optimization.",
            "what_evidence_shows": ["FY26: llm dependency observed."],
            "what_may_mean_economically": "Technology concentration may increase operational risk.",
            "what_is_not_yet_proven": "Whether diversification plans are underway.",
            "what_to_monitor": ["Watch for vendor diversification signals."],
            "key_points": ["Technology dependency risk: FY26"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-18: empty simple_answer — hard null-return gate in loadHybridAnswerCard
    {
        "id": "NF-18",
        "description": "Empty simple_answer — must FAIL G5 (loader returns null for empty text)",
        "company": "ujjivan",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_runtime_sanitizer_compat",
        "answer": {
            "simple_answer": "",
            "what_evidence_shows": ["FY26: credit risk observed."],
            "what_may_mean_economically": "Loan losses may increase.",
            "what_is_not_yet_proven": "Whether provisions are sufficient.",
            "what_to_monitor": ["Watch NPA ratios."],
            "key_points": ["Credit risk: FY26"],
            "deterministic_precision_facts": [],
        },
    },
    # NF-19: Runtime sanitizer rejects filler value in simple_answer
    {
        "id": "NF-19",
        "description": "Filler value 'unspecified' in simple_answer — must FAIL G5",
        "company": "ujjivan",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_runtime_sanitizer_compat",
        "answer": {
            "simple_answer": "unspecified",
            "what_evidence_shows": ["FY26: credit risk observed."],
            "what_may_mean_economically": "Loan losses may increase.",
            "what_is_not_yet_proven": "Whether provisions are sufficient.",
            "what_to_monitor": ["Watch NPA ratios."],
            "key_points": ["Credit risk: FY26"],
            "deterministic_precision_facts": [],
        },
    },
    # PC-03: Positive control — clean investment terminology passes G5
    {
        "id": "PC-03",
        "description": "[POSITIVE CONTROL] Clean answer with investment terminology — must PASS all validators including G5",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": None,
        "answer": {
            "simple_answer": "FY26 risk: failing to execute international expansion blueprint.",
            "what_evidence_shows": [
                "FY26: revenue growth from international markets not yet established.",
                "FY25–FY26: reliance on multi-carrier revenue-share arrangements.",
            ],
            "what_may_mean_economically": "Revenue diversification may stall if expansion targets are not met.",
            "what_is_not_yet_proven": "Whether international contribution will reach stated targets.",
            "what_to_monitor": ["Watch FY27 disclosures for international revenue contribution."],
            "key_points": [
                "International expansion: execution risk FY26",
                "Revenue-share dependency: not yet diversified",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # PC-04: Positive control — legitimate pharma "drug pipeline" reference must PASS G5
    # Regression for M35.3 Phase 6 pipeline overblocking fix
    {
        "id": "PC-04",
        "description": "[POSITIVE CONTROL] Pharma 'drug pipeline' in simple_answer — must PASS G5 (not blocked by infra pipeline pattern)",
        "company": "sun_pharma",
        "question_id": "what-could-go-wrong",
        "expected_fail": None,
        "answer": {
            "simple_answer": "FY26 risk: delays in the drug pipeline could reduce new product launches below management targets.",
            "what_evidence_shows": [
                "FY26: R&D pipeline includes 3 Phase III candidates; none confirmed approved.",
                "Product pipeline execution risk if USFDA review timelines extend.",
            ],
            "what_may_mean_economically": "A stalled R&D pipeline would reduce revenue visibility for FY28 onwards.",
            "what_is_not_yet_proven": "Whether product pipeline candidates will achieve regulatory approval on schedule.",
            "what_to_monitor": ["Monitor USFDA approval timelines for product pipeline candidates."],
            "key_points": [
                "Drug pipeline: 3 Phase III candidates, none yet approved",
                "R&D pipeline execution risk acknowledged in FY26 disclosures",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # NF-20: Runtime sanitizer rejects "data pipeline" in simple_answer
    # Regression for M35.3 Phase 6 — infra pipeline must still be blocked
    {
        "id": "NF-20",
        "description": "Internal infra term 'data pipeline' in simple_answer — must FAIL G5",
        "company": "sun_pharma",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_runtime_sanitizer_compat",
        "answer": {
            "simple_answer": "The data pipeline processes market data for risk scoring.",
            "what_evidence_shows": ["FY26: risk assessment via data pipeline."],
            "what_may_mean_economically": "Infrastructure dependency.",
            "what_is_not_yet_proven": "Unresolved.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    # NF-21: Runtime sanitizer rejects bare "ML pipeline" in simple_answer
    {
        "id": "NF-21",
        "description": "Internal infra term 'ML pipeline' in simple_answer — must FAIL G5",
        "company": "datapatterns",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_runtime_sanitizer_compat",
        "answer": {
            "simple_answer": "Risk: the ML pipeline scoring system may produce inaccurate outputs.",
            "what_evidence_shows": ["FY26: ML pipeline dependencies disclosed."],
            "what_may_mean_economically": "Model risk.",
            "what_is_not_yet_proven": "Model accuracy.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },

    # ── M35.4 Phase 9 fixtures ────────────────────────────────────────────────

    # NF-22: PENDING_MIGRATION_REVIEW must be hard-blocked by _is_approved (M35.4 Phase 2)
    {
        "id": "NF-22",
        "description": "PENDING_MIGRATION_REVIEW status must be hard-blocked by _is_approved",
        "company": "sun_pharma",
        "question_id": "what-has-management-promised",
        "expected_fail": "approval_check",
        "answer": {
            "simple_answer": "Sun Pharma management has made delivery commitments across specialty launches.",
            "what_evidence_shows": ["FY26: management committed to 2 specialty launches."],
            "what_may_mean_economically": "Revenue impact depends on launch execution.",
            "what_is_not_yet_proven": "Whether launches deliver as guided.",
            "what_to_monitor": ["FY27 specialty launch milestones"],
            "key_points": ["2 specialty launches committed FY26"],
            "deterministic_precision_facts": [],
        },
        "_approval_override": {"status": "PENDING_MIGRATION_REVIEW", "fingerprint": "aaaaaaaaaaaaaaaa"},
    },

    # NF-23: PENDING_INDEPENDENT_REVIEW must be hard-blocked (regression for existing behavior)
    {
        "id": "NF-23",
        "description": "PENDING_INDEPENDENT_REVIEW must be hard-blocked by _is_approved",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "approval_check",
        "answer": {
            "simple_answer": "Tanla has worsening technology scalability risk as of FY26.",
            "what_evidence_shows": ["FY26: technology scalability high severity."],
            "what_may_mean_economically": "Margin compression possible if costs rise.",
            "what_is_not_yet_proven": "Actual cost impact not established.",
            "what_to_monitor": ["FY27 technology cost disclosures"],
            "key_points": ["Technology scalability FY20=medium → FY26=high"],
            "deterministic_precision_facts": [],
        },
        "_approval_override": {"status": "PENDING_INDEPENDENT_REVIEW", "fingerprint": "bbbbbbbbbbbbbbbb"},
    },

    # NF-24: Changed DPF with unchanged legacy fingerprint — full_artifact_digest detects tampering
    # This fixture uses expected_fail="full_artifact_digest_check" which is handled specially
    # in mode_test_trust (not via run_adversarial_suite, which uses fixture answers, not real answers).
    {
        "id": "NF-24",
        "description": "DPF content changed after approval — full_artifact_digest must catch this",
        "company": "ujjivan",
        "question_id": "what-could-go-wrong",
        "expected_fail": "full_artifact_digest_check",
        "answer": {
            "simple_answer": "Ujjivan has credit quality risk from microfinance exposure.",
            "what_evidence_shows": ["FY26: credit quality deteriorating."],
            "what_may_mean_economically": "Loan losses could compress margins.",
            "what_is_not_yet_proven": "Extent of deterioration not quantified.",
            "what_to_monitor": ["FY27 NPA ratios"],
            "key_points": ["Credit quality risk FY26"],
            # DPF values CHANGED from what was approved — full_artifact_digest should catch this
            "deterministic_precision_facts": [{"fact": "npa_fy26", "value": "TAMPERED", "period": "fy26", "source": "INJECTED"}],
        },
    },

    # NF-25: Missing approval registry record must block serving
    {
        "id": "NF-25",
        "description": "Answer with no registry record must be hard-blocked",
        "company": "hypothetical_co",
        "question_id": "what-could-go-wrong",
        "expected_fail": "approval_check",
        "answer": {
            "simple_answer": "Risk: no registry record exists for this pair.",
            "what_evidence_shows": ["FY26: unregistered answer."],
            "what_may_mean_economically": "Unapproved content.",
            "what_is_not_yet_proven": "Everything.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },

    # PC-05: Legitimate "drug pipeline" in what_evidence_shows must pass G5 (pharma allowlist)
    {
        "id": "PC-05",
        "description": "Legitimate 'drug pipeline' in what_evidence_shows must PASS G5",
        "company": "sun_pharma",
        "question_id": "what-could-go-wrong",
        "answer": {
            "simple_answer": "Sun Pharma's drug pipeline faces R&D execution risk.",
            "what_evidence_shows": ["FY26: drug pipeline includes 3 Phase III candidates."],
            "what_may_mean_economically": "Pipeline concentration creates binary risk on approvals.",
            "what_is_not_yet_proven": "Whether Phase III candidates receive regulatory approval.",
            "what_to_monitor": ["FY27 NDA filings for pipeline compounds"],
            "key_points": ["Drug pipeline concentration risk FY26"],
            "deterministic_precision_facts": [],
        },
    },

    # PC-06: Legitimate "R&D pipeline" and "product pipeline" must pass G5
    {
        "id": "PC-06",
        "description": "Legitimate 'R&D pipeline' and 'product pipeline' must PASS G5",
        "company": "sun_pharma",
        "question_id": "what-could-go-wrong",
        "answer": {
            "simple_answer": "Sun Pharma's R&D pipeline and product pipeline are concentrated in specialty segments.",
            "what_evidence_shows": ["FY26: product pipeline includes dermatology and oncology candidates."],
            "what_may_mean_economically": "Specialty segment concentration amplifies approval risk.",
            "what_is_not_yet_proven": "Whether the R&D pipeline delivers commercially viable compounds.",
            "what_to_monitor": ["FY27 R&D pipeline progress disclosures"],
            "key_points": ["R&D pipeline FY26: specialty concentration"],
            "deterministic_precision_facts": [],
        },
    },

    # NF-26: Internal "data pipeline" disclosure in what_evidence_shows must FAIL G5
    {
        "id": "NF-26",
        "description": "Internal 'data pipeline' term in what_evidence_shows must FAIL G5",
        "company": "datapatterns",
        "question_id": "what-could-go-wrong",
        "expected_fail": "check_runtime_sanitizer_compat",
        "answer": {
            "simple_answer": "Data Patterns has technology execution risk.",
            "what_evidence_shows": ["FY26: the data pipeline processes 10TB of telemetry daily."],
            "what_may_mean_economically": "Processing bottlenecks could disrupt service.",
            "what_is_not_yet_proven": "Whether pipeline capacity is sufficient.",
            "what_to_monitor": ["FY27 technology capacity disclosures"],
            "key_points": ["Technology execution risk FY26"],
            "deterministic_precision_facts": [],
        },
    },

    # NF-28: MQ-R1 — rating label leaked into simple_answer
    {
        "id": "NF-28",
        "description": "management quality rating 'WEAK' leaked into simple_answer — must FAIL MQ-R1",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Sun Pharma's management quality is WEAK based on delivery record.",
            "what_evidence_shows": ["0 of 25 progression items confirmed delivered."],
            "what_may_mean_economically": "Weak management quality may limit upside.",
            "what_is_not_yet_proven": "Whether quality improves.",
            "what_to_monitor": ["Delivery count in subsequent disclosures."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-29: MQ-R1 — rating label "management is strong" leaked
    {
        "id": "NF-29",
        "description": "management quality rating 'management is strong' leaked — must FAIL MQ-R1",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Data Patterns management is strong given 3 confirmed delivered items.",
            "what_evidence_shows": ["3 confirmed deliveries: nano-satellite, vibration table, 3D AOI."],
            "what_may_mean_economically": "Strong management indicates continued delivery.",
            "what_is_not_yet_proven": "Capital return attribution.",
            "what_to_monitor": ["Commitment delivery count."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-30: MQ-R2 — behavioral descriptor absent
    {
        "id": "NF-30",
        "description": "simple_answer missing behavioral descriptor — must FAIL MQ-R2",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_behavioral_descriptor_present",
        "answer": {
            "simple_answer": "Tanla management shows mixed delivery with 4 confirmed items and uncertain capital economics.",
            "what_evidence_shows": ["4 confirmed delivered items."],
            "what_may_mean_economically": "Platform transition drives value.",
            "what_is_not_yet_proven": "Capital deployment economics.",
            "what_to_monitor": ["Platform revenue share."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-31: MQ-01 — promise→delivered conflation
    {
        "id": "NF-31",
        "description": "promise presented as confirmed delivery without independent verification — must FAIL MQ-01",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_promise_to_delivered",
        "answer": {
            "simple_answer": "Sun Pharma FOLLOW_THROUGH_LARGELY_UNVERIFIED: management promised ILUMYA expansion and delivered this commitment.",
            "what_evidence_shows": ["Management promised ILUMYA expansion and delivered this commitment as promised."],
            "what_may_mean_economically": "Specialty expansion on track.",
            "what_is_not_yet_proven": "Scale of revenue.",
            "what_to_monitor": ["US specialty revenue."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-32: MQ-06 — financial improvement attributed to management
    {
        "id": "NF-32",
        "description": "revenue growth attributed to management causation without attribution evidence — must FAIL MQ-06",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_financial_improvement_not_causation",
        "answer": {
            "simple_answer": "Data Patterns PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS: revenue improved because of management decisions.",
            "what_evidence_shows": ["Revenue improved because of management execution decisions in FY26."],
            "what_may_mean_economically": "Management caused margin expansion.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Revenue trajectory."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-33: MQ-15 — unknown outcome presented as failure
    {
        "id": "NF-33",
        "description": "unverified outcome presented as confirmed failure — must FAIL MQ-15",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_unknown_outcome_not_failure",
        "answer": {
            "simple_answer": "Ujjivan HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED: branch commitment unable to verify, therefore failed.",
            "what_evidence_shows": ["568-branch commitment: unable to verify, therefore failed to deliver."],
            "what_may_mean_economically": "Delivery failure limits expansion.",
            "what_is_not_yet_proven": "Nothing — failure confirmed.",
            "what_to_monitor": ["Branch count."],
            "deterministic_precision_facts": [],
        },
    },
    # PC-07: Positive — behavioral descriptor present, no ratings, observable facts
    {
        "id": "PC-07",
        "description": "[POSITIVE CONTROL] Valid MQ answer: behavioral descriptor, observable counts, no ratings — must PASS all MQ validators",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": (
                "Sun Pharma's management delivery pattern is FOLLOW_THROUGH_LARGELY_UNVERIFIED: "
                "none of the 25 tracked progression items have reached a confirmed delivered state. "
                "4 verifiable hard commitments all remain Unable To Verify. Revenue ₹58,462 cr confirmed."
            ),
            "what_evidence_shows": [
                "0 of 25 progression items confirmed delivered. 4 hard commitments: all Unable To Verify.",
                "Supply-chain, FX, and IP risks are recurring conviction-weakening signals; "
                "resolution actions are not systematically updated.",
            ],
            "what_may_mean_economically": (
                "Specialty revenue may improve margins. Recurring risk signals are not accompanied "
                "by systematic resolution updates; causal attribution to management plans is not established."
            ),
            "what_is_not_yet_proven": "Whether any hard commitment reaches confirmed delivered status.",
            "what_to_monitor": ["US specialty revenue share.", "Hard commitment delivery status in subsequent disclosures."],
            "deterministic_precision_facts": [],
        },
    },
    # PC-08: Positive — observable counts and behavioral language allowed
    {
        "id": "PC-08",
        "description": "[POSITIVE CONTROL] Observable: '4 commitments were delivered', 'capital outcomes remain unattributed' — must PASS MQ-R1",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": (
                "Tanla's management delivery pattern is MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: "
                "4 commitments were delivered (ValueFirst, OTT platform, digital revenue, Wisely ATP). "
                "Capital outcomes remain unattributed."
            ),
            "what_evidence_shows": [
                "4 confirmed delivered items: ValueFirst, AI-powered OTT, Digital revenue contribution, Wisely ATP.",
                "Capital allocation and owner alignment both have insufficient evidence.",
            ],
            "what_may_mean_economically": (
                "FCF/PAT ~1.11x confirms cash generation. Deployment-to-return linkages not established."
            ),
            "what_is_not_yet_proven": "Whether capital deployment economics are established.",
            "what_to_monitor": ["Platform revenue share.", "Capital allocation linkages."],
            "deterministic_precision_facts": [],
        },
    },

    # NF-MQ-01: Implied capability upgrade — "genuine delivery capability"
    {
        "id": "NF-MQ-01",
        "description": "Management has genuine delivery capability — must FAIL MQ-R1 (Pattern C)",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Ujjivan HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED: 10 of 25 tracked items confirmed delivered.",
            "what_evidence_shows": ["10 confirmed delivered items."],
            "what_may_mean_economically": "Management has genuine delivery capability based on the 10 confirmed items.",
            "what_is_not_yet_proven": "Capital outcomes.",
            "what_to_monitor": ["NIM trend."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-02: Implied capability upgrade — "demonstrated strong management execution"
    {
        "id": "NF-MQ-02",
        "description": "Demonstrated strong management execution — must FAIL MQ-R1 (Pattern C)",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Data Patterns PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS: 3 of 25 items confirmed delivered.",
            "what_evidence_shows": ["The company has demonstrated strong management execution over FY22–FY26."],
            "what_may_mean_economically": "Continued execution expected.",
            "what_is_not_yet_proven": "Capital outcomes.",
            "what_to_monitor": ["Delivery rate."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-03: Quality label — "proven itself to be disciplined"
    {
        "id": "NF-MQ-03",
        "description": "Management has proven itself to be disciplined — must FAIL MQ-R1 (Pattern B)",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Tanla MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: 4 of 25 items confirmed delivered.",
            "what_evidence_shows": ["Management has proven itself to be disciplined in delivering on stated initiatives."],
            "what_may_mean_economically": "Continued delivery expected.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Platform revenue share."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-04: Quality label — "credible capital allocator"
    {
        "id": "NF-MQ-04",
        "description": "Management appears to be a credible capital allocator — must FAIL MQ-R1 (Pattern B)",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Sun Pharma FOLLOW_THROUGH_LARGELY_UNVERIFIED: 0 of 25 items confirmed delivered.",
            "what_evidence_shows": ["Management appears to be a credible capital allocator based on dividend consistency."],
            "what_may_mean_economically": "Capital compounding likely to continue.",
            "what_is_not_yet_proven": "Commitment delivery.",
            "what_to_monitor": ["US specialty revenue."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-05: Implied capability upgrade — "demonstrate management competence"
    {
        "id": "NF-MQ-05",
        "description": "Project deliveries demonstrate management competence — must FAIL MQ-R1 (Pattern C)",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Ujjivan HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED: 10 of 25 items confirmed.",
            "what_evidence_shows": ["The repeated project deliveries demonstrate management competence in digital banking."],
            "what_may_mean_economically": "NIM improvement possible.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["NIM trend."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-06: Direct rating — "execution quality is high"
    {
        "id": "NF-MQ-06",
        "description": "Management execution quality is high — must FAIL MQ-R1 (Pattern C)",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Data Patterns PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS: 3 of 25 delivered.",
            "what_evidence_shows": ["Management execution quality is high based on 3 confirmed deliveries."],
            "what_may_mean_economically": "Strong outcomes expected.",
            "what_is_not_yet_proven": "Capital returns.",
            "what_to_monitor": ["Delivery rate."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-07: Quality label — "management deserves confidence"
    {
        "id": "NF-MQ-07",
        "description": "Management deserves confidence based on delivery record — must FAIL MQ-R1 (Pattern B)",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Tanla MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: 4 of 25 confirmed.",
            "what_evidence_shows": ["Management deserves confidence based on its delivery record."],
            "what_may_mean_economically": "Platform transition on track.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Platform revenue share."],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-08: Quality label — "shareholder-friendly management" from cash returns
    {
        "id": "NF-MQ-08",
        "description": "Capital returns show shareholder-friendly management — must FAIL MQ-R1 (Pattern B)",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Sun Pharma FOLLOW_THROUGH_LARGELY_UNVERIFIED: 0/25 delivered.",
            "what_evidence_shows": ["Capital returns confirm shareholder-friendly management."],
            "what_may_mean_economically": "Investors benefit from consistent dividends.",
            "what_is_not_yet_proven": "Delivery commitments.",
            "what_to_monitor": ["US specialty revenue."],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-01: Positive — delivery count allowed
    {
        "id": "PC-MQ-01",
        "description": "[POSITIVE CONTROL] 10 of 25 progression items were confirmed delivered — must PASS MQ-R1",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Ujjivan HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED: 10 of 25 progression items were confirmed delivered.",
            "what_evidence_shows": ["10 confirmed delivered items across digital and operational areas."],
            "what_may_mean_economically": "Digital adoption may reduce cost-of-acquisition.",
            "what_is_not_yet_proven": "Capital outcomes.",
            "what_to_monitor": ["NIM trend."],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-02: Positive — "four projects reached delivered status" allowed
    {
        "id": "PC-MQ-02",
        "description": "[POSITIVE CONTROL] Four projects reached delivered status — must PASS MQ-R1",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Tanla MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: four projects reached delivered status.",
            "what_evidence_shows": ["Four items confirmed delivered: ValueFirst, OTT platform, digital revenue, Wisely ATP."],
            "what_may_mean_economically": "Platform transition continues.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Platform revenue share."],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-03: Positive — "strong capital ratio" as financial metric allowed
    {
        "id": "PC-MQ-03",
        "description": "[POSITIVE CONTROL] Strong capital ratio allowed — must PASS MQ-R1 (financial metric, not management quality)",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Ujjivan HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED: 10 of 25 confirmed.",
            "what_evidence_shows": ["CRAR remains above regulatory minimum — strong capital ratio (FY25)."],
            "what_may_mean_economically": "Capital adequacy supports expansion.",
            "what_is_not_yet_proven": "Whether organic capex produces NIM improvement.",
            "what_to_monitor": ["NIM and credit cost."],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-04: Positive — operating cash flow fact allowed
    {
        "id": "PC-MQ-04",
        "description": "[POSITIVE CONTROL] Operating cash flow ₹574 cr FY26 — must PASS MQ-R1 (financial fact)",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Tanla MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: 4 of 25 delivered.",
            "what_evidence_shows": ["Operating cash flow was ₹563 cr in FY26."],
            "what_may_mean_economically": "Cash generation confirmed; deployment economics unattributed.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Platform revenue."],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-05: Positive — "multiple digital initiatives reached delivered status" allowed
    {
        "id": "PC-MQ-05",
        "description": "[POSITIVE CONTROL] Multiple digital initiatives reached delivered status — must PASS MQ-R1",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Ujjivan HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED: 10 of 25 confirmed.",
            "what_evidence_shows": ["Multiple digital initiatives reached delivered status across FY22–FY25."],
            "what_may_mean_economically": "Digital execution record supports retention thesis.",
            "what_is_not_yet_proven": "Capital outcomes.",
            "what_to_monitor": ["NIM trend."],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-06: Positive — "capital outcomes remain unattributed" allowed
    {
        "id": "PC-MQ-06",
        "description": "[POSITIVE CONTROL] Capital deployment outcomes remain unattributed — must PASS MQ-R1",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Data Patterns PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS: 3 of 25 delivered.",
            "what_evidence_shows": ["7/10 capital deployment outcomes remain unattributed in public disclosures."],
            "what_may_mean_economically": "Capital base nearly tripled; incremental returns not disclosed.",
            "what_is_not_yet_proven": "Operating returns on unattributed deployments.",
            "what_to_monitor": ["ROCE trajectory."],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-07: Positive — "management repeatedly emphasized" allowed (observation, not quality)
    {
        "id": "PC-MQ-07",
        "description": "[POSITIVE CONTROL] Management repeatedly emphasized digital distribution — must PASS MQ-R1",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Ujjivan HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED: 10 of 25 confirmed.",
            "what_evidence_shows": ["Management repeatedly emphasized digital distribution across FY22–FY25 commentary themes."],
            "what_may_mean_economically": "Digital focus is observable; economic outcomes unattributed.",
            "what_is_not_yet_proven": "Whether digital emphasis translates to NIM improvement.",
            "what_to_monitor": ["NIM trend."],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-08: Positive — "three commitments remain unable to verify" allowed
    {
        "id": "PC-MQ-08",
        "description": "[POSITIVE CONTROL] Three commitments remain unable to verify — must PASS MQ-R1",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Sun Pharma FOLLOW_THROUGH_LARGELY_UNVERIFIED: 0 of 25 items confirmed.",
            "what_evidence_shows": ["Three commitments remain unable to verify: Nidlegy EMA filing, carbon reduction, Japan launch."],
            "what_may_mean_economically": "Specialty revenue may improve; causal attribution not established.",
            "what_is_not_yet_proven": "Whether any hard commitment reaches delivered status.",
            "what_to_monitor": ["Nidlegy EMA filing status."],
            "deterministic_precision_facts": [],
        },
    },

    # NF-MQ-09: Shorthand rating — "MQ overall: WEAK (stable)"
    {
        "id": "NF-MQ-09",
        "description": "MQ overall: WEAK (stable) in key_points — must FAIL MQ-R1 (Pattern A shorthand)",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Sun Pharma FOLLOW_THROUGH_LARGELY_UNVERIFIED: 0 of 25 tracked items confirmed.",
            "what_evidence_shows": ["0 confirmed delivered items."],
            "what_may_mean_economically": "Specialty revenue may improve margins.",
            "what_is_not_yet_proven": "Any hard commitment.",
            "what_to_monitor": ["US specialty revenue."],
            "key_points": [
                "MQ overall: WEAK (stable). Strongest: capital_allocation_discipline.",
                "25 progression items: 0 delivered.",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-10: Shorthand rating — "MQ overall: MIXED"
    {
        "id": "NF-MQ-10",
        "description": "MQ overall: MIXED in key_points — must FAIL MQ-R1 (Pattern A shorthand)",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Tanla MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: 4 of 25 delivered.",
            "what_evidence_shows": ["4 confirmed delivered items."],
            "what_may_mean_economically": "Platform transition continues.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Platform revenue share."],
            "key_points": [
                "MQ overall: MIXED. Strongest: execution_discipline.",
                "4 delivered, 2 partially (of 25).",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-11: Shorthand rating — "MQ overall: STRONG"
    {
        "id": "NF-MQ-11",
        "description": "MQ overall: STRONG in key_points — must FAIL MQ-R1 (Pattern A shorthand)",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Data Patterns PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS: 3 of 25 delivered.",
            "what_evidence_shows": ["3 confirmed delivered items."],
            "what_may_mean_economically": "Space sector opportunity.",
            "what_is_not_yet_proven": "Capital returns.",
            "what_to_monitor": ["ROCE trajectory."],
            "key_points": [
                "MQ overall: STRONG. Strongest: execution_discipline.",
                "3 delivered, 4 partially (of 25).",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-12: Shorthand rating — "Management quality: WEAK"
    {
        "id": "NF-MQ-12",
        "description": "Management quality: WEAK in key_points — must FAIL MQ-R1 (Pattern A shorthand)",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Ujjivan HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED: 10 of 25 confirmed.",
            "what_evidence_shows": ["10 confirmed delivered items."],
            "what_may_mean_economically": "NIM improvement possible.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["NIM trend."],
            "key_points": [
                "Management quality: WEAK. Strongest: execution_discipline.",
                "10 delivered, 2 partially (of 25).",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-13: Shorthand rating — "Management rating: STRONG"
    {
        "id": "NF-MQ-13",
        "description": "Management rating: STRONG in key_points — must FAIL MQ-R1 (Pattern A shorthand)",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Sun Pharma FOLLOW_THROUGH_LARGELY_UNVERIFIED: 0 of 25 confirmed.",
            "what_evidence_shows": ["0 confirmed."],
            "what_may_mean_economically": "Specialty may improve margins.",
            "what_is_not_yet_proven": "Any hard commitment.",
            "what_to_monitor": ["US specialty revenue."],
            "key_points": [
                "Management rating: STRONG. Strongest: capital_allocation_discipline.",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # NF-MQ-14: Shorthand rating with dash — "Overall management quality — MIXED"
    {
        "id": "NF-MQ-14",
        "description": "Overall management quality — MIXED in key_points — must FAIL MQ-R1 (Pattern A shorthand)",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_rating_leakage",
        "answer": {
            "simple_answer": "Tanla MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: 4 of 25 confirmed.",
            "what_evidence_shows": ["4 confirmed delivered items."],
            "what_may_mean_economically": "Platform transition continues.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Platform revenue share."],
            "key_points": [
                "Overall management quality — MIXED. Execution strong; capital unattributed.",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-09: Positive — "Overall delivery count: 4 confirmed" allowed
    {
        "id": "PC-MQ-09",
        "description": "[POSITIVE CONTROL] Overall delivery count: 4 confirmed, 2 partial — must PASS MQ-R1",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Tanla MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: 4 of 25 confirmed.",
            "what_evidence_shows": ["4 confirmed delivered items."],
            "what_may_mean_economically": "Platform transition continues.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Platform revenue share."],
            "key_points": [
                "Overall delivery count: 4 confirmed, 2 partial.",
                "FCF/PAT ~1.11x; revenue ₹4,418 cr; NPM 11.5% (FY26).",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-10: Positive — "Management statements tracked: 46" allowed
    {
        "id": "PC-MQ-10",
        "description": "[POSITIVE CONTROL] Management statements tracked: 46 — must PASS MQ-R1",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Sun Pharma FOLLOW_THROUGH_LARGELY_UNVERIFIED: 0 of 25 confirmed.",
            "what_evidence_shows": ["0 confirmed."],
            "what_may_mean_economically": "Specialty may improve margins.",
            "what_is_not_yet_proven": "Any hard commitment.",
            "what_to_monitor": ["US specialty revenue."],
            "key_points": [
                "Management statements tracked: 46 total; 4 hard commitments, 0 confirmed delivered.",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-11: Positive — "Overall capital outcomes: 7 unattributed" allowed
    {
        "id": "PC-MQ-11",
        "description": "[POSITIVE CONTROL] Overall capital outcomes: 7 unattributed — must PASS MQ-R1",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Data Patterns PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS: 3 of 25 confirmed.",
            "what_evidence_shows": ["3 confirmed."],
            "what_may_mean_economically": "Space sector opportunity.",
            "what_is_not_yet_proven": "Capital returns.",
            "what_to_monitor": ["ROCE trajectory."],
            "key_points": [
                "Overall capital outcomes: 7 unattributed (₹325+ cr combined).",
            ],
            "deterministic_precision_facts": [],
        },
    },
    # PC-MQ-12: Positive — "Delivery pattern: multiple deliveries with economic attribution gaps" allowed
    {
        "id": "PC-MQ-12",
        "description": "[POSITIVE CONTROL] Delivery pattern: multiple deliveries with economic attribution gaps — must PASS MQ-R1",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Tanla MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: 4 of 25 confirmed.",
            "what_evidence_shows": ["4 confirmed delivered items."],
            "what_may_mean_economically": "Platform transition continues.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Platform revenue share."],
            "key_points": [
                "Delivery pattern: multiple deliveries with economic attribution gaps.",
            ],
            "deterministic_precision_facts": [],
        },
    },

    # ── M37.5: DPF rating leakage fixtures (NF-MQ-DPF-01..05, PC-MQ-DPF-01..04) ──
    # NF-MQ-DPF-01: "Management quality overall = WEAK" in DPF metric — must FAIL MQ-R3
    {
        "id": "NF-MQ-DPF-01",
        "description": "DPF metric 'Management quality overall' with WEAK value — must FAIL MQ-R3",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_dpf_rating_leakage",
        "answer": {
            "simple_answer": "Sun Pharma FOLLOW_THROUGH_LARGELY_UNVERIFIED: 0 of 25 confirmed.",
            "what_evidence_shows": ["0 confirmed."],
            "what_may_mean_economically": "Specialty revenue may grow.",
            "what_is_not_yet_proven": "Any hard commitment.",
            "what_to_monitor": ["US specialty revenue."],
            "key_points": ["0 of 25 delivered."],
            "deterministic_precision_facts": [
                {"metric": "Management quality overall", "value": "WEAK", "period": "FY26", "semantic_meaning": "synthesis"},
            ],
        },
    },
    # NF-MQ-DPF-02: "Execution discipline = STRONG" — must FAIL MQ-R3
    {
        "id": "NF-MQ-DPF-02",
        "description": "DPF metric 'Execution discipline' with STRONG value — must FAIL MQ-R3",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_dpf_rating_leakage",
        "answer": {
            "simple_answer": "Data Patterns PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS: 3 of 25 confirmed.",
            "what_evidence_shows": ["3 confirmed."],
            "what_may_mean_economically": "Margins may expand.",
            "what_is_not_yet_proven": "Capital returns.",
            "what_to_monitor": ["ROCE trajectory."],
            "key_points": ["3 of 25 delivered."],
            "deterministic_precision_facts": [
                {"metric": "Execution discipline", "value": "STRONG", "period": "FY26", "semantic_meaning": "synthesis"},
            ],
        },
    },
    # NF-MQ-DPF-03: "Candor = WEAK" — must FAIL MQ-R3
    {
        "id": "NF-MQ-DPF-03",
        "description": "DPF metric 'Candor' with WEAK value — must FAIL MQ-R3",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_dpf_rating_leakage",
        "answer": {
            "simple_answer": "Tanla MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: 4 of 25 confirmed.",
            "what_evidence_shows": ["4 confirmed."],
            "what_may_mean_economically": "Platform transition.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Platform revenue."],
            "key_points": ["4 of 25 delivered."],
            "deterministic_precision_facts": [
                {"metric": "Candor", "value": "WEAK", "period": "FY26", "semantic_meaning": "synthesis"},
            ],
        },
    },
    # NF-MQ-DPF-04: "Capital allocation discipline = MIXED" — must FAIL MQ-R3
    {
        "id": "NF-MQ-DPF-04",
        "description": "DPF metric 'Capital allocation discipline' with MIXED value — must FAIL MQ-R3",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_dpf_rating_leakage",
        "answer": {
            "simple_answer": "Ujjivan HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED: 10 of 25 confirmed.",
            "what_evidence_shows": ["10 confirmed."],
            "what_may_mean_economically": "Digital gains.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["NIM trend."],
            "key_points": ["10 of 25 delivered."],
            "deterministic_precision_facts": [
                {"metric": "Capital allocation discipline", "value": "MIXED", "period": "FY25", "semantic_meaning": "synthesis"},
            ],
        },
    },
    # NF-MQ-DPF-05: "Management credibility = HIGH" — must FAIL MQ-R3 (metric is a quality dimension)
    {
        "id": "NF-MQ-DPF-05",
        "description": "DPF metric 'Management credibility' (even with HIGH value) — must FAIL MQ-R3",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_dpf_rating_leakage",
        "answer": {
            "simple_answer": "Sun Pharma FOLLOW_THROUGH_LARGELY_UNVERIFIED: 0 of 25 confirmed.",
            "what_evidence_shows": ["0 confirmed."],
            "what_may_mean_economically": "Specialty revenue may grow.",
            "what_is_not_yet_proven": "Any hard commitment.",
            "what_to_monitor": ["US specialty revenue."],
            "key_points": ["0 of 25 delivered."],
            "deterministic_precision_facts": [
                {"metric": "Management credibility", "value": "HIGH", "period": "FY26", "semantic_meaning": "synthesis"},
            ],
        },
    },
    # PC-MQ-DPF-01: "Progression items = 4 delivered / 2 partial" — must PASS MQ-R3
    {
        "id": "PC-MQ-DPF-01",
        "description": "[POSITIVE CONTROL] DPF 'Progression items' with delivery count — must PASS MQ-R3",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Tanla MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: 4 of 25 confirmed.",
            "what_evidence_shows": ["4 confirmed."],
            "what_may_mean_economically": "Platform transition.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Platform revenue."],
            "key_points": ["4 of 25 delivered."],
            "deterministic_precision_facts": [
                {"metric": "Progression items", "value": "4 delivered / 2 partial", "period": "FY26", "semantic_meaning": "delivery count"},
            ],
        },
    },
    # PC-MQ-DPF-02: "Commitments = 3 measurable; 1 delayed; 2 unverified" — must PASS MQ-R3
    {
        "id": "PC-MQ-DPF-02",
        "description": "[POSITIVE CONTROL] DPF 'Commitments' with structured count — must PASS MQ-R3",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Tanla MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS: 4 of 25 confirmed.",
            "what_evidence_shows": ["4 confirmed."],
            "what_may_mean_economically": "Platform transition.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": ["Platform revenue."],
            "key_points": ["4 of 25 delivered."],
            "deterministic_precision_facts": [
                {"metric": "Commitments", "value": "3 measurable; 1 delayed; 2 unverified", "period": "FY26", "semantic_meaning": "commitment tracking"},
            ],
        },
    },
    # PC-MQ-DPF-03: "Capital outcomes = 7 UNABLE_TO_ATTRIBUTE" — must PASS MQ-R3
    {
        "id": "PC-MQ-DPF-03",
        "description": "[POSITIVE CONTROL] DPF 'Capital outcomes' with attribution status — must PASS MQ-R3",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Data Patterns PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS: 3 of 25 confirmed.",
            "what_evidence_shows": ["3 confirmed."],
            "what_may_mean_economically": "Margins may expand.",
            "what_is_not_yet_proven": "Capital returns.",
            "what_to_monitor": ["ROCE trajectory."],
            "key_points": ["3 of 25 delivered."],
            "deterministic_precision_facts": [
                {"metric": "Capital outcomes", "value": "7 UNABLE_TO_ATTRIBUTE", "period": "FY26", "semantic_meaning": "capital attribution"},
            ],
        },
    },
    # PC-MQ-DPF-04: "Evidence confidence = HIGH" — must PASS MQ-R3 (evidence confidence is allowed)
    {
        "id": "PC-MQ-DPF-04",
        "description": "[POSITIVE CONTROL] DPF 'Evidence confidence = HIGH' — must PASS MQ-R3",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": None,
        "answer": {
            "simple_answer": "Sun Pharma FOLLOW_THROUGH_LARGELY_UNVERIFIED: 0 of 25 confirmed.",
            "what_evidence_shows": ["0 confirmed."],
            "what_may_mean_economically": "Specialty revenue may grow.",
            "what_is_not_yet_proven": "Any hard commitment.",
            "what_to_monitor": ["US specialty revenue."],
            "key_points": ["0 of 25 delivered."],
            "deterministic_precision_facts": [
                {"metric": "Evidence confidence", "value": "HIGH", "period": "FY26", "semantic_meaning": "5+ source streams"},
            ],
        },
    },

    # NF-27: Content served under wrong company — tanla:what-could-go-wrong is PENDING_INDEPENDENT_REVIEW
    {
        "id": "NF-27",
        "description": "Cross-company content: tanla:what-could-go-wrong approval is PENDING_INDEPENDENT_REVIEW — must block",
        "company": "tanla",
        "question_id": "what-could-go-wrong",
        "expected_fail": "approval_check",
        # tanla:what-could-go-wrong has PENDING_INDEPENDENT_REVIEW → _is_approved returns False
        "answer": {
            "simple_answer": "Ujjivan credit risk content served under tanla identity.",
            "what_evidence_shows": ["FY26: credit risk worsening."],
            "what_may_mean_economically": "Margin compression.",
            "what_is_not_yet_proven": "Extent.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },

    # ── MQ-R4 negative fixtures (NF-MQ-INF-01..06) — M37.6 ────────────────────
    {
        "id": "NF-MQ-INF-01",
        "description": "FCF/PAT confirms working-capital discipline — metric-to-inference upgrade must fail",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS. 4 of 25 delivered.",
            "what_evidence_shows": ["FCF/PAT above 1.0x."],
            "what_may_mean_economically": "FCF/PAT above 1.0x confirms working-capital discipline.",
            "what_is_not_yet_proven": "Attribution.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-02",
        "description": "Strong cash conversion confirms capital efficiency — metric-to-inference upgrade must fail",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS. 4 of 25 delivered.",
            "what_evidence_shows": ["FCF exceeded PAT."],
            "what_may_mean_economically": "Strong cash conversion confirms capital efficiency.",
            "what_is_not_yet_proven": "Attribution.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-03",
        "description": "capital efficiency narrative in where_management_was_consistent — must fail",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS. 4 of 25 delivered.",
            "what_evidence_shows": ["4 delivered."],
            "what_may_mean_economically": "Attribution gaps remain.",
            "what_is_not_yet_proven": "Deployment outcomes.",
            "what_to_monitor": [],
            "key_points": [],
            "where_management_was_consistent": [
                "FCF/PAT ~1.11x confirms capital efficiency narrative.",
            ],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-04",
        "description": "working capital discipline as consistency map key — must fail",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS. 4 of 25 delivered.",
            "what_evidence_shows": ["FCF exceeded PAT."],
            "what_may_mean_economically": "Cash generation observed.",
            "what_is_not_yet_proven": "Drivers.",
            "what_to_monitor": [],
            "key_points": [],
            "management_consistency_map": {
                "Working capital discipline": "CONSISTENT — FCF/PAT ~1.11x supports narrative",
            },
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-05",
        "description": "Dividend consistency proves capital discipline — must fail",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "FOLLOW_THROUGH_LARGELY_UNVERIFIED. 0 of 25 delivered.",
            "what_evidence_shows": ["Dividends paid annually."],
            "what_may_mean_economically": "Dividend consistency proves capital discipline.",
            "what_is_not_yet_proven": "Delivery.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-06",
        "description": "Revenue growth confirms management strategy successful — must fail",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS. 3 of 25 delivered.",
            "what_evidence_shows": ["Revenue ₹925 cr FY26."],
            "what_may_mean_economically": "Revenue growth confirms management strategy was successful.",
            "what_is_not_yet_proven": "Attribution.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },

    # ── MQ-R4 positive controls (PC-MQ-INF-01..04) — M37.6 ───────────────────
    {
        "id": "PC-MQ-INF-01",
        "description": "FCF/PAT stated as factual ratio — no inference upgrade — must pass all checks",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "answer": {
            "simple_answer": "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS. 4 of 25 delivered.",
            "what_evidence_shows": ["FCF/PAT was approximately 1.11x in FY26; cash generated exceeded profit reported."],
            "what_may_mean_economically": "FCF exceeded PAT in FY26; persistence and drivers of this cash conversion are not established.",
            "what_is_not_yet_proven": "Deployment-to-return linkages.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "PC-MQ-INF-02",
        "description": "Cash conversion stated as observed ratio, drivers unknown — must pass",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "answer": {
            "simple_answer": "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS. 4 of 25 delivered.",
            "what_evidence_shows": ["FCF ₹563 cr; PAT ₹509 cr in FY26."],
            "what_may_mean_economically": "Cash conversion: FCF ₹563 cr exceeded PAT ₹509 cr in FY26; persistence and drivers not established.",
            "what_is_not_yet_proven": "Attribution.",
            "what_to_monitor": [],
            "key_points": [],
            "management_consistency_map": {
                "Cash conversion": "OBSERVED — FCF ₹563 cr exceeded PAT ₹509 cr in FY26; persistence and drivers not established",
            },
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "PC-MQ-INF-03",
        "description": "Delivery count stated as factual count — no inference upgrade — must pass",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "answer": {
            "simple_answer": "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS. 3 of 25 delivered.",
            "what_evidence_shows": ["3 items confirmed delivered (nano-satellite, vibration table, 3D AOI); 4 partially delivered."],
            "what_may_mean_economically": "Direction is confirmed by delivery evidence; economic attribution is not established.",
            "what_is_not_yet_proven": "Revenue impact.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "PC-MQ-INF-04",
        "description": "Dividend stated as payment fact, continuity not assessed — must pass",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "answer": {
            "simple_answer": "FOLLOW_THROUGH_LARGELY_UNVERIFIED. 0 of 25 delivered.",
            "what_evidence_shows": ["Dividend declared for FY25 and FY26; payout continuity not yet assessed across cycles."],
            "what_may_mean_economically": "Capital returns are confirmed as a pattern; allocation decision quality not established.",
            "what_is_not_yet_proven": "Long-term allocation quality.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },

    # ── MQ-R5 negative fixtures (NF-MQ-CMP-01..05) — M37.6 ───────────────────
    {
        "id": "NF-MQ-CMP-01",
        "description": "strongest delivery rate in 4-company dataset — unsupported comparative must fail",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_comparative_integrity",
        "answer": {
            "simple_answer": "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS. 3 of 25 delivered.",
            "what_evidence_shows": ["3 delivered."],
            "what_may_mean_economically": "Attribution gaps.",
            "what_is_not_yet_proven": "Outcomes.",
            "what_to_monitor": [],
            "key_points": ["3 delivered — strongest delivery rate in 4-company dataset."],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-CMP-02",
        "description": "best delivery rate in dataset in where_management_was_consistent — must fail",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_comparative_integrity",
        "answer": {
            "simple_answer": "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS. 3 of 25 delivered.",
            "what_evidence_shows": ["3 delivered."],
            "what_may_mean_economically": "Attribution gaps.",
            "what_is_not_yet_proven": "Outcomes.",
            "what_to_monitor": [],
            "key_points": [],
            "where_management_was_consistent": [
                "3 items confirmed delivered — best delivery rate in dataset.",
            ],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-CMP-03",
        "description": "unusual external accountability — unsupported rarity claim must fail",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_comparative_integrity",
        "answer": {
            "simple_answer": "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED. 10 of 25 delivered.",
            "what_evidence_shows": ["IPSOS assessments."],
            "what_may_mean_economically": "Customer data exists.",
            "what_is_not_yet_proven": "Capital attribution.",
            "what_to_monitor": [],
            "key_points": [],
            "where_management_was_consistent": [
                "Three IPSOS assessments delivered — unusual external accountability.",
            ],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-CMP-04",
        "description": "highest delivery rate in dataset in DPF semantic_meaning — must fail",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_comparative_integrity",
        "answer": {
            "simple_answer": "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED. 10 of 25 delivered.",
            "what_evidence_shows": ["10 delivered."],
            "what_may_mean_economically": "Capital outcomes unattributed.",
            "what_is_not_yet_proven": "Attribution.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [
                {"metric": "Delivery count", "value": "10 of 25", "period": "FY21–FY25",
                 "semantic_meaning": "10 items confirmed delivered; highest delivery rate in 4-company dataset"},
            ],
        },
    },
    {
        "id": "NF-MQ-CMP-05",
        "description": "weakest execution record — unsupported negative comparative must fail",
        "company": "sun_pharma",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_comparative_integrity",
        "answer": {
            "simple_answer": "FOLLOW_THROUGH_LARGELY_UNVERIFIED. 0 of 25 delivered.",
            "what_evidence_shows": ["0 delivered."],
            "what_may_mean_economically": "No confirmed delivery.",
            "what_is_not_yet_proven": "Any delivery.",
            "what_to_monitor": [],
            "key_points": ["0 of 25 delivered — weakest execution record in the dataset."],
            "deterministic_precision_facts": [],
        },
    },

    # ── MQ-R5 positive control (PC-MQ-CMP-01) — M37.6 ────────────────────────
    {
        "id": "PC-MQ-CMP-01",
        "description": "highest delivery rate with explicit cohort comparison — must pass all checks",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "answer": {
            "simple_answer": "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED. 10 of 25 delivered.",
            "what_evidence_shows": ["10 of 25 items confirmed delivered (40%), compared with Tanla 4/25 (16%), Data Patterns 3/25 (12%), Sun Pharma 0/25 (0%)."],
            "what_may_mean_economically": "Delivery evidence count is 10 of 25 items; capital attribution not established.",
            "what_is_not_yet_proven": "Economic outcomes.",
            "what_to_monitor": [],
            "key_points": ["The highest delivery rate in the cohort was Ujjivan at 40%, compared with Tanla 16%, Data Patterns 12%, Sun Pharma 0%."],
            "deterministic_precision_facts": [],
        },
    },

    # ── MQ-R4 negative fixtures (NF-MQ-INF-07..11) — pricing power (M37.8) ──
    {
        "id": "NF-MQ-INF-07",
        "description": "EBITDA margin suggests structural pricing power — must fail MQ-R4",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS. 3 of 25 delivered.",
            "what_evidence_shows": ["Revenue ₹925 cr (FY26)."],
            "what_may_mean_economically": "A 39.5% EBITDA margin suggests structural pricing power.",
            "what_is_not_yet_proven": "Attribution.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-08",
        "description": "high margins demonstrate durable pricing power — must fail MQ-R4",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS. 3 of 25 delivered.",
            "what_evidence_shows": ["Margins confirmed."],
            "what_may_mean_economically": "High margins demonstrate durable pricing power.",
            "what_is_not_yet_proven": "Sustainability.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-09",
        "description": "high ROCE confirms superior capital allocation — must fail MQ-R4",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS. 3 of 25 delivered.",
            "what_evidence_shows": ["ROCE improved."],
            "what_may_mean_economically": "High ROCE confirms superior capital allocation.",
            "what_is_not_yet_proven": "Attribution.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-10",
        "description": "revenue growth proves the strategy is working — must fail MQ-R4",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS. 4 of 25 delivered.",
            "what_evidence_shows": ["Revenue ₹4,418 cr (FY26)."],
            "what_may_mean_economically": "Revenue growth proves the strategy is working.",
            "what_is_not_yet_proven": "Attribution.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-11",
        "description": "high NPM indicates a durable competitive moat — must fail MQ-R4",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS. 3 of 25 delivered.",
            "what_evidence_shows": ["NPM 29.3% (FY26)."],
            "what_may_mean_economically": "High NPM indicates a durable competitive moat.",
            "what_is_not_yet_proven": "Moat evidence.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },

    # ── MQ-R4 positive controls (PC-MQ-INF-05..07) — pricing-power safe (M37.8) ─
    {
        "id": "PC-MQ-INF-05",
        "description": "EBITDA margin stated as factual figure — no inference — must pass",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "answer": {
            "simple_answer": "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS. 3 of 25 delivered.",
            "what_evidence_shows": ["Revenue ₹925 cr (FY26)."],
            "what_may_mean_economically": "EBITDA margin was 39.5% and NPM was 29.3% in FY26.",
            "what_is_not_yet_proven": "Whether margins are sustainable.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "PC-MQ-INF-06",
        "description": "structural pricing power qualified as not established — must pass",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "answer": {
            "simple_answer": "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS. 3 of 25 delivered.",
            "what_evidence_shows": ["Revenue ₹925 cr (FY26)."],
            "what_may_mean_economically": "Whether these margins reflect structural pricing power is not established from the available evidence.",
            "what_is_not_yet_proven": "Pricing power.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "PC-MQ-INF-07",
        "description": "ROCE improvement stated as fact, causal attribution qualified as not established — must pass",
        "company": "datapatterns",
        "question_id": "how-good-is-management",
        "answer": {
            "simple_answer": "PARTIAL_DELIVERY_WITH_MATERIAL_OUTCOME_GAPS. 3 of 25 delivered.",
            "what_evidence_shows": ["ROCE improved during the period."],
            "what_may_mean_economically": "ROCE improved during the period; causal attribution to management decisions is not established.",
            "what_is_not_yet_proven": "Capital allocation quality.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },

    # ── MQ-R4 negative fixtures (NF-MQ-INF-12..15) — measurement≠quality (M37.8) ─
    {
        "id": "NF-MQ-INF-12",
        "description": "three customer surveys confirm consistent service quality — must fail MQ-R4",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED. 10 of 25 delivered.",
            "what_evidence_shows": ["Three customer surveys confirm consistent service quality."],
            "what_may_mean_economically": "Delivery confirmed.",
            "what_is_not_yet_proven": "Economic attribution.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-13",
        "description": "training completion demonstrates improved employee capability — must fail MQ-R4",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED. 10 of 25 delivered.",
            "what_evidence_shows": ["Training completion demonstrates improved employee capability."],
            "what_may_mean_economically": "Capability impact not attributed.",
            "what_is_not_yet_proven": "Outcome quality.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-14",
        "description": "audit completed confirming control effectiveness — must fail MQ-R4",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED. 10 of 25 delivered.",
            "what_evidence_shows": ["An audit was completed, confirming control effectiveness."],
            "what_may_mean_economically": "Governance activity confirmed.",
            "what_is_not_yet_proven": "Control quality.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-MQ-INF-15",
        "description": "grievance mechanism proves customer issues are effectively resolved — must fail MQ-R4",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_no_metric_inference",
        "answer": {
            "simple_answer": "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED. 10 of 25 delivered.",
            "what_evidence_shows": ["A grievance mechanism proves customer issues are effectively resolved."],
            "what_may_mean_economically": "Mechanism operational.",
            "what_is_not_yet_proven": "Resolution effectiveness.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },

    # ── MQ-R4 positive controls (PC-MQ-INF-08..10) — measurement safe (M37.8) ─
    {
        "id": "PC-MQ-INF-08",
        "description": "three assessments completed stated as fact — no quality inference — must pass",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "answer": {
            "simple_answer": "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED. 10 of 25 delivered.",
            "what_evidence_shows": ["Three independent customer-satisfaction assessments were completed."],
            "what_may_mean_economically": "External measurement activity confirmed; quality outcomes not established.",
            "what_is_not_yet_proven": "Service quality levels.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "PC-MQ-INF-09",
        "description": "assessments provide external evidence, results to be evaluated — must pass",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "answer": {
            "simple_answer": "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED. 10 of 25 delivered.",
            "what_evidence_shows": ["The assessments provide external customer-satisfaction evidence; their results must be evaluated separately."],
            "what_may_mean_economically": "External evidence available; interpretation not established.",
            "what_is_not_yet_proven": "Quality outcomes.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "PC-MQ-INF-10",
        "description": "grievance mechanism operational, effectiveness not established — must pass",
        "company": "ujjivan",
        "question_id": "how-good-is-management",
        "answer": {
            "simple_answer": "HIGH_DELIVERY_COUNT_WITH_CAPITAL_OUTCOMES_UNATTRIBUTED. 10 of 25 delivered.",
            "what_evidence_shows": ["A grievance mechanism is operational; its effectiveness is not established here."],
            "what_may_mean_economically": "Mechanism exists; resolution quality not assessed.",
            "what_is_not_yet_proven": "Grievance resolution effectiveness.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },

    # ── MQ-R6 negative fixtures (NF-XMOD-01..04) — lifecycle overclaim (M37.8) ─
    {
        "id": "NF-XMOD-01",
        "description": "acquisition described as revenue contributor without attribution — must fail MQ-R6",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_lifecycle_consistency",
        "answer": {
            "simple_answer": "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS. 4 of 25 delivered.",
            "what_evidence_shows": ["ValueFirst acquisition (Enterprise Communications revenue contributor)."],
            "what_may_mean_economically": "Revenue attribution not established.",
            "what_is_not_yet_proven": "Economic value.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-XMOD-02",
        "description": "integration claimed as successfully completed without evidence — must fail MQ-R6",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_lifecycle_consistency",
        "answer": {
            "simple_answer": "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS. 4 of 25 delivered.",
            "what_evidence_shows": ["Integration was successfully completed."],
            "what_may_mean_economically": "Value unknown.",
            "what_is_not_yet_proven": "Economic return.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-XMOD-03",
        "description": "acquisition asserted to have created shareholder value — must fail MQ-R6",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_lifecycle_consistency",
        "answer": {
            "simple_answer": "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS. 4 of 25 delivered.",
            "what_evidence_shows": ["Acquisition created shareholder value."],
            "what_may_mean_economically": "Economic outcomes pending.",
            "what_is_not_yet_proven": "Return attribution.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
    {
        "id": "NF-XMOD-04",
        "description": "investment asserted to be generating returns without established evidence — must fail MQ-R6",
        "company": "tanla",
        "question_id": "how-good-is-management",
        "expected_fail": "check_mq_lifecycle_consistency",
        "answer": {
            "simple_answer": "MULTIPLE_DELIVERIES_WITH_ECONOMIC_ATTRIBUTION_GAPS. 4 of 25 delivered.",
            "what_evidence_shows": ["The investment is generating returns."],
            "what_may_mean_economically": "Capital deployment economics not attributed.",
            "what_is_not_yet_proven": "Return evidence.",
            "what_to_monitor": [],
            "key_points": [],
            "deterministic_precision_facts": [],
        },
    },
]

# ── Positive control runner — used by test-trust ──────────────────────────────

POSITIVE_CONTROLS = [f for f in NEGATIVE_FIXTURES if f.get("expected_fail") is None]
NEGATIVE_CASES = [f for f in NEGATIVE_FIXTURES if f.get("expected_fail") is not None]
