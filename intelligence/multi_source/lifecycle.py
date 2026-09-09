"""Phase 9 — Parts 4–12: Commitment lifecycle state machine.

Groups evidence atoms by theme_slug, resolves the lifecycle state, and
links financial consequences where evidence permits.

Said → did → outcome logic:
  CLAIMED      — first evidence atom for this theme (highest-authority COMMITMENT)
  PROGRESSING  — subsequent atoms in the same theme showing advancement
  CONFIRMED    — high-authority atom (EXCHANGE_DISCLOSURE or ANNUAL_REPORT) for
                 FACTUAL_EVENT on the same theme after the claim was made
  CONTRADICTED — high-authority atom contradicts the claimed direction
  UNPROVEN     — no subsequent evidence found for a COMMITMENT-domain claim
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from intelligence.multi_source.contracts import (
    ClaimDomain,
    CommitmentLifecycle,
    LongitudinalCommitment,
    MultiSourceEvidence,
    SourceAuthority,
    authority_rank,
)
from intelligence.multi_source.theme_registry import _THEMES


_THEME_LABEL: Dict[str, str] = {slug: label for slug, label, *_ in _THEMES}
_THEME_DOMAIN: Dict[str, ClaimDomain] = {slug: domain for slug, label, domain, *_ in _THEMES}

_PERIOD_ORDER = ["fy20", "fy21", "fy22", "fy23", "fy24", "fy25", "fy26", "fy27",
                 "q1 fy25", "q2 fy25", "q3 fy25", "q4 fy25",
                 "q1 fy26", "q2 fy26", "q3 fy26", "q4 fy26",
                 "undated"]

_HIGH_AUTHORITY = {SourceAuthority.EXCHANGE_DISCLOSURE, SourceAuthority.ANNUAL_REPORT, SourceAuthority.EARNINGS_RELEASE}


def _period_index(period: Optional[str]) -> int:
    if not period:
        return len(_PERIOD_ORDER)
    key = period.lower().strip()
    try:
        return _PERIOD_ORDER.index(key)
    except ValueError:
        return len(_PERIOD_ORDER)


def _sort_key(e: MultiSourceEvidence) -> tuple:
    return (_period_index(e.source_period), e.authority.value)


def _is_confirmation_claim(e: MultiSourceEvidence) -> bool:
    """True if this evidence atom confirms execution of a prior commitment."""
    confirming_types = {"FACTUAL_EVENT", "FACTUAL_STATEMENT", "MANAGEMENT_CHANGE", "APPOINTMENT", "RESIGNATION"}
    if e.claim_type.upper() in confirming_types and e.authority in _HIGH_AUTHORITY:
        return True
    if e.claim_domain == ClaimDomain.FACTUAL_EVENT and e.authority in _HIGH_AUTHORITY:
        return True
    return False


def _is_progression_claim(e: MultiSourceEvidence) -> bool:
    progression_types = {"COMMITMENT", "INTENTION", "EXPECTATION", "STRATEGIC_PRIORITY", "FACTUAL_STATEMENT"}
    return e.claim_type.upper() in progression_types


def _best_claim_atom(atoms: List[MultiSourceEvidence], domain: ClaimDomain) -> MultiSourceEvidence:
    """Pick the highest-authority COMMITMENT-domain atom as the canonical claim."""
    commitment_atoms = [a for a in atoms if a.claim_domain == ClaimDomain.COMMITMENT]
    pool = commitment_atoms or atoms
    return min(pool, key=lambda a: authority_rank(a.authority, domain))


def resolve_commitments(evidence: List[MultiSourceEvidence]) -> List[LongitudinalCommitment]:
    """Group evidence by theme_slug and resolve lifecycle for each thread."""
    by_theme: Dict[str, List[MultiSourceEvidence]] = defaultdict(list)
    for e in evidence:
        by_theme[e.theme_slug].append(e)

    commitments: List[LongitudinalCommitment] = []
    now = datetime.utcnow().isoformat()

    for slug, atoms in by_theme.items():
        atoms_sorted = sorted(atoms, key=_sort_key)
        domain = _THEME_DOMAIN.get(slug, ClaimDomain.FACTUAL_EVENT)
        label = _THEME_LABEL.get(slug, slug)

        # Identify the canonical claim (first/best COMMITMENT atom)
        claim_atom = _best_claim_atom(atoms_sorted, domain)

        # Determine lifecycle
        lifecycle = CommitmentLifecycle.CLAIMED
        confirmed_period: Optional[str] = None
        confirmed_source: Optional[SourceAuthority] = None
        confirmed_text: Optional[str] = None
        financial_consequence: Optional[str] = None
        unproven_reason: Optional[str] = None

        later_atoms = [a for a in atoms_sorted if _period_index(a.source_period) >= _period_index(claim_atom.source_period) and a is not claim_atom]

        confirmations = [a for a in later_atoms if _is_confirmation_claim(a)]
        progressions = [a for a in later_atoms if _is_progression_claim(a)]

        # A factual event from a high-authority source IS the confirmation — no
        # separate subsequent evidence is needed.
        if domain == ClaimDomain.FACTUAL_EVENT and claim_atom.authority in _HIGH_AUTHORITY:
            lifecycle = CommitmentLifecycle.CONFIRMED
            confirmed_period = claim_atom.source_period
            confirmed_source = claim_atom.authority
            confirmed_text = claim_atom.text
        elif confirmations:
            lifecycle = CommitmentLifecycle.CONFIRMED
            best_conf = min(confirmations, key=lambda a: authority_rank(a.authority, ClaimDomain.FACTUAL_EVENT))
            confirmed_period = best_conf.source_period
            confirmed_source = best_conf.authority
            confirmed_text = best_conf.text
        elif progressions:
            lifecycle = CommitmentLifecycle.PROGRESSING
        elif domain == ClaimDomain.COMMITMENT and len(atoms_sorted) == 1:
            lifecycle = CommitmentLifecycle.UNPROVEN
            unproven_reason = "No subsequent evidence found across any source family."

        # Part 11: Financial consequence heuristic — if an ANNUAL_REPORT or EARNINGS_RELEASE
        # evidence atom on this theme references a metric, annotate it.
        financial_atoms = [
            a for a in atoms_sorted
            if a.source_type in ("ANNUAL_REPORT", "EARNINGS_RELEASE", "EARNINGS_CALL_TRANSCRIPT")
            and any(kw in a.text.lower() for kw in ["₹", "crore", "%", "revenue", "profit", "ebitda", "margin"])
        ]
        if financial_atoms:
            best_fin = financial_atoms[0]
            financial_consequence = f"[{best_fin.source_period} / {best_fin.source_type}] {best_fin.text[:200]}"

        cid = f"LC-{slug.upper()[:20]}-{claim_atom.fiscal_year.upper()}"

        commitments.append(LongitudinalCommitment(
            commitment_id=cid,
            company=claim_atom.company,
            theme_slug=slug,
            theme_label=label,
            claim_domain=domain,
            lifecycle=lifecycle,
            claimed_period=claim_atom.source_period,
            claimed_by=claim_atom.speaker,
            claimed_source=claim_atom.authority,
            claimed_text=claim_atom.text,
            evidence=atoms_sorted,
            confirmed_period=confirmed_period,
            confirmed_source=confirmed_source,
            confirmed_text=confirmed_text,
            financial_consequence=financial_consequence,
            unproven_reason=unproven_reason,
        ))

    # Sort: CONFIRMED first, then PROGRESSING, CLAIMED, UNPROVEN, CONTRADICTED
    _ORDER = [
        CommitmentLifecycle.CONFIRMED,
        CommitmentLifecycle.PROGRESSING,
        CommitmentLifecycle.CLAIMED,
        CommitmentLifecycle.UNPROVEN,
        CommitmentLifecycle.CONTRADICTED,
    ]
    commitments.sort(key=lambda c: _ORDER.index(c.lifecycle))
    return commitments
