"""Phase 9 — Multi-Source Longitudinal Intelligence contracts.

Parts 2–3: Source authority and cross-source evidence identity.
Parts 4–6: Commitment lifecycle state model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Part 2: Source authority model
# Authority is claim-type-aware; the same document has different epistemic
# weight depending on what is being asserted.
# ---------------------------------------------------------------------------

class SourceAuthority(str, Enum):
    EXCHANGE_DISCLOSURE = "EXCHANGE_DISCLOSURE"
    ANNUAL_REPORT       = "ANNUAL_REPORT"
    EARNINGS_RELEASE    = "EARNINGS_RELEASE"
    QUARTERLY_REPORT    = "QUARTERLY_REPORT"
    TRANSCRIPT          = "TRANSCRIPT"
    INVESTOR_PRESENTATION = "INVESTOR_PRESENTATION"
    UNKNOWN             = "UNKNOWN"


class ClaimDomain(str, Enum):
    """Semantic domain of a claim, determines which source is most authoritative."""
    FACTUAL_EVENT       = "FACTUAL_EVENT"       # resignation, merger, regulatory
    FINANCIAL_METRIC    = "FINANCIAL_METRIC"    # revenue, EBITDA, margins
    COMMITMENT          = "COMMITMENT"          # forward-looking promise
    STRATEGIC_PRIORITY  = "STRATEGIC_PRIORITY"  # directional statement
    RISK                = "RISK"                # risk acknowledgement


# Authority rankings by claim domain (highest authority first).
_AUTHORITY_RANK: Dict[ClaimDomain, List[SourceAuthority]] = {
    ClaimDomain.FACTUAL_EVENT: [
        SourceAuthority.EXCHANGE_DISCLOSURE,
        SourceAuthority.ANNUAL_REPORT,
        SourceAuthority.EARNINGS_RELEASE,
        SourceAuthority.QUARTERLY_REPORT,
        SourceAuthority.TRANSCRIPT,
        SourceAuthority.INVESTOR_PRESENTATION,
    ],
    ClaimDomain.FINANCIAL_METRIC: [
        SourceAuthority.ANNUAL_REPORT,
        SourceAuthority.EARNINGS_RELEASE,
        SourceAuthority.QUARTERLY_REPORT,
        SourceAuthority.TRANSCRIPT,
        SourceAuthority.INVESTOR_PRESENTATION,
        SourceAuthority.EXCHANGE_DISCLOSURE,
    ],
    ClaimDomain.COMMITMENT: [
        SourceAuthority.TRANSCRIPT,
        SourceAuthority.INVESTOR_PRESENTATION,
        SourceAuthority.EARNINGS_RELEASE,
        SourceAuthority.QUARTERLY_REPORT,
        SourceAuthority.ANNUAL_REPORT,
        SourceAuthority.EXCHANGE_DISCLOSURE,
    ],
    ClaimDomain.STRATEGIC_PRIORITY: [
        SourceAuthority.ANNUAL_REPORT,
        SourceAuthority.TRANSCRIPT,
        SourceAuthority.INVESTOR_PRESENTATION,
        SourceAuthority.EARNINGS_RELEASE,
        SourceAuthority.QUARTERLY_REPORT,
        SourceAuthority.EXCHANGE_DISCLOSURE,
    ],
    ClaimDomain.RISK: [
        SourceAuthority.EXCHANGE_DISCLOSURE,
        SourceAuthority.ANNUAL_REPORT,
        SourceAuthority.EARNINGS_RELEASE,
        SourceAuthority.QUARTERLY_REPORT,
        SourceAuthority.TRANSCRIPT,
        SourceAuthority.INVESTOR_PRESENTATION,
    ],
}


def authority_rank(authority: SourceAuthority, domain: ClaimDomain) -> int:
    """Lower = higher authority. Returns 99 for unknown."""
    ranking = _AUTHORITY_RANK.get(domain, [])
    try:
        return ranking.index(authority)
    except ValueError:
        return 99


# ---------------------------------------------------------------------------
# Part 3: Cross-source evidence identity
# A theme slug is the canonical identity key that survives paraphrase
# and source differences.  Evidence items sharing the same theme_slug
# belong to the same longitudinal commitment thread.
# ---------------------------------------------------------------------------

@dataclass
class MultiSourceEvidence:
    """Normalised evidence atom from any processor output."""
    evidence_id: str
    company: str
    fiscal_year: str
    source_period: str          # "Q4 FY26", "FY25", etc.
    source_type: str            # SourceType enum value string
    authority: SourceAuthority
    claim_domain: ClaimDomain
    theme_slug: str             # canonical cross-source identity key
    claim_type: str             # raw claim_type from the processor
    speaker: Optional[str]
    speaker_role: Optional[str]
    text: str
    qualifiers: List[str] = field(default_factory=list)
    target_period: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "evidence_id": self.evidence_id,
            "company": self.company,
            "fiscal_year": self.fiscal_year,
            "source_period": self.source_period,
            "source_type": self.source_type,
            "authority": self.authority.value,
            "claim_domain": self.claim_domain.value,
            "theme_slug": self.theme_slug,
            "claim_type": self.claim_type,
            "speaker": self.speaker,
            "speaker_role": self.speaker_role,
            "text": self.text,
            "qualifiers": self.qualifiers,
            "target_period": self.target_period,
            "provenance": self.provenance,
        }
        return {k: v for k, v in d.items() if v is not None}


# ---------------------------------------------------------------------------
# Parts 4–6: Commitment lifecycle state machine
# CLAIMED → PROGRESSING → CONFIRMED | CONTRADICTED | UNPROVEN
# ---------------------------------------------------------------------------

class CommitmentLifecycle(str, Enum):
    CLAIMED      = "CLAIMED"       # first appearance in any source
    PROGRESSING  = "PROGRESSING"   # subsequent mention showing advancement
    CONFIRMED    = "CONFIRMED"     # execution evidence from authoritative source
    CONTRADICTED = "CONTRADICTED"  # directly contradicted by authoritative source
    UNPROVEN     = "UNPROVEN"      # no subsequent evidence found


@dataclass
class LongitudinalCommitment:
    """One commitment thread spanning multiple sources and time periods."""
    commitment_id: str
    company: str
    theme_slug: str
    theme_label: str
    claim_domain: ClaimDomain
    lifecycle: CommitmentLifecycle
    claimed_period: str                              # when first CLAIMED
    claimed_by: Optional[str]                        # speaker who made the claim
    claimed_source: SourceAuthority
    claimed_text: str
    evidence: List[MultiSourceEvidence] = field(default_factory=list)
    confirmed_period: Optional[str] = None
    confirmed_source: Optional[SourceAuthority] = None
    confirmed_text: Optional[str] = None
    financial_consequence: Optional[str] = None      # Part 11: linked financial impact
    unproven_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "commitment_id": self.commitment_id,
            "company": self.company,
            "theme_slug": self.theme_slug,
            "theme_label": self.theme_label,
            "claim_domain": self.claim_domain.value,
            "lifecycle": self.lifecycle.value,
            "claimed_period": self.claimed_period,
            "claimed_by": self.claimed_by,
            "claimed_source": self.claimed_source.value if self.claimed_source else None,
            "claimed_text": self.claimed_text,
            "evidence_count": len(self.evidence),
            "evidence": [e.to_dict() for e in self.evidence],
            "confirmed_period": self.confirmed_period,
            "confirmed_source": self.confirmed_source.value if self.confirmed_source else None,
            "confirmed_text": self.confirmed_text,
            "financial_consequence": self.financial_consequence,
            "unproven_reason": self.unproven_reason,
        }
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class LongitudinalReport:
    """Full multi-source longitudinal intelligence report for a company."""
    company: str
    generated_at: str
    source_periods: List[str]
    source_families_present: List[str]
    commitment_count: int
    lifecycle_counts: Dict[str, int]
    commitments: List[LongitudinalCommitment] = field(default_factory=list)
    stop_conditions: List[str] = field(default_factory=list)
    audit_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "9.0",
            "company": self.company,
            "generated_at": self.generated_at,
            "source_periods": self.source_periods,
            "source_families_present": self.source_families_present,
            "commitment_count": self.commitment_count,
            "lifecycle_counts": self.lifecycle_counts,
            "commitments": [c.to_dict() for c in self.commitments],
            "stop_conditions": self.stop_conditions,
            "audit_notes": self.audit_notes,
        }
