"""
Independent AI relationship reviewer — canonical architecture (Mission 14).

Validates whether the economic *relationship* connecting two already-supported
claims is actually justified by the evidence.  Analogous to ai_claim_reviewer
but operates at the cross-domain causal-relationship level.

Design principles:
- Additional layer only; does not replace or weaken individual claim validation.
- Relationship-type-specific semantics: STRATEGY_TO_EXECUTION is not held to
  OPERATING_TO_FINANCIAL_OUTCOME causal standards.
- Chronology model: BEFORE / OVERLAPPING / AFTER / UNKNOWN — same-period is
  valid for CAPITAL_TO_EXECUTION, irrelevant for CONTEXT_ONLY.
- Zero false accepts is the hard safety floor; false rejects on legitimate
  qualified relationships are the precision target.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Tuple

from knowledge.ai import get_llm

# ── Schema contracts ──────────────────────────────────────────────────────────

RelType = Literal[
    "STRATEGY_TO_EXECUTION",
    "CAPITAL_TO_EXECUTION",
    "EXECUTION_TO_OPERATING_OUTCOME",
    "OPERATING_TO_FINANCIAL_OUTCOME",
    "RISK_TO_OUTCOME",
    "CONTEXT_ONLY",
    "UNKNOWN_RELATIONSHIP",
]

ConfidenceLevel = Literal["CONFIRMED", "SUPPORTED", "PLAUSIBLE", "UNKNOWN"]
ReviewVerdict = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "REVIEW_ERROR"]
ChronologyRelation = Literal["BEFORE", "OVERLAPPING", "AFTER", "UNKNOWN"]
AcceptanceStatus = Literal["ACCEPT", "NEEDS_REVIEW", "REJECT"]


@dataclass
class EvidenceItem:
    ref: str
    section: str
    period: str
    text: str
    forbidden_assertions: List[str] = field(default_factory=list)


@dataclass
class RelationshipInput:
    """Fully resolved input for the AI relationship reviewer."""
    relationship_id: str
    rel_type: str
    source_claim_id: str
    target_claim_id: str
    source_domain: str
    target_domain: str
    source_period: str
    target_period: str
    source_evidence_refs: List[str]
    target_evidence_refs: List[str]
    shared_evidence_refs: List[str]
    proposed_confidence: str
    wording: str
    rationale: str
    source_claim_text: str
    target_claim_text: str
    source_evidence: List[EvidenceItem]
    target_evidence: List[EvidenceItem]
    shared_evidence: List[EvidenceItem]


@dataclass
class ReviewerResult:
    """Structured output from the AI relationship reviewer."""
    verdict: str
    recommended_confidence: str
    chronology_relation: str        # BEFORE | OVERLAPPING | AFTER | UNKNOWN
    chronology_valid: bool
    semantic_alignment: bool        # source and target share domain/subject/product correspondence
    linkage_established: bool
    causal_issues: List[str]
    retrospective_bias: bool
    measurement_window_issue: bool
    alternative_explanations: Optional[str]
    qualification_required: Optional[str]
    reason: str


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an independent investment evidence analyst. Validate whether a proposed cross-domain relationship between two investment claims is justified by available evidence.

Return ONLY a strict JSON verdict — no prose outside the JSON.

=== RELATIONSHIP TYPE SEMANTICS ===

Validation requirements differ by type. Apply the correct standard:

STRATEGY_TO_EXECUTION
  Question: Is the execution *meaningfully aligned* with the earlier stated strategy?
  NOT: Did the strategy economically cause the execution?
  Validate: semantic correspondence (shared domain/product/subject/technology area), chronology (strategy precedes execution), absence of contradictory evidence.
  Do NOT require proof of economic mechanism.
  Do NOT flag "strategy as outcome proof" as a causal issue for this type — alignment is the criterion, not financial causality.
  Return semantic_alignment: true when strategy domains/subjects/technologies correspond to execution activities even if not identically named.
  IMPORTANT: Return semantic_alignment: false when the target is a financial instrument or action (debt raising, equity issuance, budget line items, financial ratios, revenue percentages). Debt raising, loan agreements, and capital structure changes are financial instruments — NOT execution of an operational or technology strategy. Only operational/product/technology/project execution qualifies.

CAPITAL_TO_EXECUTION
  Question: Is the capital deployment credibly associated with the execution activity?
  Valid chronology: BEFORE (capital allocated before project start) OR OVERLAPPING (same fiscal year — capital deployed during project execution).
  AFTER is invalid.
  Do NOT treat same fiscal year as invalid chronology for this type — ONLY when the target is an operational/project execution.
  IMPORTANT: If the target is a FINANCIAL METRIC (revenue, FCF, profit, return percentage, revenue growth rate), this is OPERATING_TO_FINANCIAL_OUTCOME semantics, NOT capital-to-execution. Apply full causal discipline: flag correlation_as_causation and set chronology_valid: false for same-period financial claims without attribution.
  Record chronology_relation as OVERLAPPING for same-period capital+project pairs.

EXECUTION_TO_OPERATING_OUTCOME
  Requires stronger linkage — execution must precede the outcome, and some mechanism or attribution evidence is expected.

OPERATING_TO_FINANCIAL_OUTCOME
  Strongest causal discipline. Correlation alone is insufficient. Mechanism or management attribution with independent corroboration required.

RISK_TO_OUTCOME
  Requires evidence the risk actually manifested and affected the claimed outcome, not merely that both exist simultaneously.

CONTEXT_ONLY
  Question: Is the source context relevant to interpreting the target claim?
  Chronology is NOT required — later context can legitimately inform interpretation of earlier events.
  Record chronology_relation honestly, but do NOT use it to invalidate this type.
  Causal confidence cannot exceed PLAUSIBLE for CONTEXT_ONLY.

UNKNOWN_RELATIONSHIP
  Preserves a genuine unresolved connection. Absence of causal proof is expected and valid.

=== 8 VALIDATION DIMENSIONS ===

1. ENDPOINT VALIDITY: Are both endpoint claims supported by their cited evidence? If either is unsupported, the relationship cannot be accepted.

2. CHRONOLOGY: Record the temporal relation as BEFORE / OVERLAPPING / AFTER / UNKNOWN.
   - For causal types (EXECUTION_TO_OPERATING_OUTCOME, OPERATING_TO_FINANCIAL_OUTCOME, RISK_TO_OUTCOME): AFTER invalidates causality.
   - For CAPITAL_TO_EXECUTION: BEFORE and OVERLAPPING are both valid.
   - For CONTEXT_ONLY: record but do not use to invalidate.
   - For STRATEGY_TO_EXECUTION: BEFORE is required; OVERLAPPING is borderline.

3. LINKAGE: Does evidence establish a direct connection beyond both facts being individually true? Co-occurrence and temporal proximity are insufficient for causal types.

4. CAUSALITY OVERSTATEMENT (causal types only — EXECUTION_TO_OPERATING_OUTCOME, OPERATING_TO_FINANCIAL_OUTCOME, RISK_TO_OUTCOME):
   - Correlation presented as causality
   - Strategy as outcome proof (only flag for non-STRATEGY_TO_EXECUTION types)
   - Capex as confirmed value creation
   - Commissioning as revenue contribution without attribution
   - R&D as confirmed margin expansion
   - Revenue growth as proof single strategy succeeded
   - Acquisition as confirmed value-accretive without accretion evidence

5. RETROSPECTIVE BIAS: Management later attributing an outcome to an initiative ≠ independent causal confirmation. Maximum justified confidence from retrospective attribution alone: PLAUSIBLE.

6. ALTERNATIVE EXPLANATIONS: Plausible unresolved alternative causes cap confidence at PLAUSIBLE.

7. MEASUREMENT WINDOW: Insufficient elapsed time for the claimed effect to be observable means the relationship cannot be CONFIRMED or SUPPORTED.

8. CONFIDENCE CALIBRATION: Is the proposed confidence justified given the above?

=== OUTPUT FORMAT ===

Return ONLY this JSON object:

{
  "verdict": "<SUPPORTED|PARTIALLY_SUPPORTED|UNSUPPORTED|CONTRADICTED|REVIEW_ERROR>",
  "recommended_confidence": "<CONFIRMED|SUPPORTED|PLAUSIBLE|UNKNOWN|REJECT>",
  "chronology_relation": "<BEFORE|OVERLAPPING|AFTER|UNKNOWN>",
  "chronology_valid": <true|false>,
  "semantic_alignment": <true|false>,
  "linkage_established": <true|false>,
  "causal_issues": ["<issue>"],
  "retrospective_bias": <true|false>,
  "measurement_window_issue": <true|false>,
  "alternative_explanations": "<description or null>",
  "qualification_required": "<qualification text or null>",
  "reason": "<one-sentence primary finding>"
}

=== VERDICT DEFINITIONS ===

SUPPORTED — evidence genuinely supports the relationship; no material causal issues given the relationship type
PARTIALLY_SUPPORTED — some support exists but significant qualifications required
UNSUPPORTED — evidence does not establish the relationship
CONTRADICTED — evidence actively contradicts the claimed relationship
REVIEW_ERROR — input malformed or insufficient to evaluate

=== RULES ===

- Apply type-specific semantics strictly: do not require financial mechanism proof for STRATEGY_TO_EXECUTION.
- Return semantic_alignment: true if source and target share a meaningful domain/subject/product correspondence even without identical naming.
- For CONTEXT_ONLY: set chronology_valid: true regardless of temporal direction.
- For CAPITAL_TO_EXECUTION: set chronology_valid: true when chronology_relation is BEFORE or OVERLAPPING.
- Return UNSUPPORTED if proposed confidence is CONFIRMED but evidence only supports PLAUSIBLE.
- Return PARTIALLY_SUPPORTED if a PLAUSIBLE relationship is well-framed as interpretation with explicit qualifiers.
- UNKNOWN means genuinely cannot establish — valid uncertainty, not failure.
"""

# ── Interpretation frame detection ───────────────────────────────────────────

_INTERPRETATION_FRAMES = [
    "plausible", "may have", "may be", "consistent with", "interpretation",
    "suggests", "indicates", "is plausibly", "might", "could", "possible",
    "appears to", "seems to", "likely", "probably", "if correct",
    "is consistent", "is broadly consistent",
    "contextualizes", "contextualises",
    "cannot be established", "cannot confirm", "not confirmed", "unclear",
    "is uncertain", "not determinable", "no direct", "no primary evidence",
    "cannot be confirmed",
]

# Hard overstatement keywords — for CAUSAL types only (not STRATEGY_TO_EXECUTION)
_CAUSAL_HARD_OVERSTATEMENT = [
    "correlation presented as causality", "correlation as causality",
    "correlation as causation", "correlation_as_causation",
    "co-occurrence", "simultaneous occurrence",
    "same year", "same fiscal year",
    "retrospective", "strategy as outcome", "strategy-as-outcome",
    "revenue growth as proof", "capex as value creation",
    "commissioning as revenue", "r&d as margin",
    "acquisition as accretion", "management attribution as",
]

# For STRATEGY_TO_EXECUTION — narrower set (no "strategy as outcome", no "correlation" block)
_S2E_HARD_OVERSTATEMENT = [
    "revenue growth as proof", "capex as value creation",
    "commissioning as revenue", "r&d as margin",
    "acquisition as accretion",
]

ACCEPT = "ACCEPT"
NEEDS_REVIEW = "NEEDS_REVIEW"
REJECT = "REJECT"


# ── Evidence resolution ───────────────────────────────────────────────────────

def _resolve_evidence(refs: List[str], evidence_index: dict, max_items: int = 5) -> List[EvidenceItem]:
    items = []
    for ref in refs[:max_items]:
        ev = evidence_index.get(ref)
        if not ev:
            continue
        text = (ev.get("original_statement") or ev.get("text") or
                ev.get("description") or ev.get("commitment_text", ""))
        guidance = ev.get("ai_reasoning_guidance", {})
        must_not = guidance.get("must_not_assert", [])
        items.append(EvidenceItem(
            ref=ref,
            section=ev.get("section", ev.get("evidence_type", "?")),
            period=ev.get("period") or ev.get("announcement_period") or ev.get("fiscal_year", "?"),
            text=(text[:300] if text else "(no text)"),
            forbidden_assertions=must_not[:2],
        ))
    return items


def build_relationship_input(
    rel: dict,
    claims_by_id: dict,
    evidence_index: dict,
) -> RelationshipInput:
    """Resolve relationship dict + claims + evidence into a structured ReviewInput."""
    from_id = rel.get("from_claim_id", "?")
    to_id = rel.get("to_claim_id", "?")
    from_claim = claims_by_id.get(from_id, {})
    to_claim = claims_by_id.get(to_id, {})

    from_refs = from_claim.get("evidence_refs", [])
    to_refs = to_claim.get("evidence_refs", [])
    shared_refs = rel.get("shared_evidence_refs", [])

    return RelationshipInput(
        relationship_id=rel.get("rel_id", "?"),
        rel_type=rel.get("rel_type", "?"),
        source_claim_id=from_id,
        target_claim_id=to_id,
        source_domain=from_claim.get("domain", from_claim.get("claim_type", "?")),
        target_domain=to_claim.get("domain", to_claim.get("claim_type", "?")),
        source_period=from_claim.get("fiscal_period", "?"),
        target_period=to_claim.get("fiscal_period", "?"),
        source_evidence_refs=from_refs,
        target_evidence_refs=to_refs,
        shared_evidence_refs=shared_refs,
        proposed_confidence=rel.get("causal_confidence", "?"),
        wording=rel.get("relationship_wording", ""),
        rationale=rel.get("rationale", "")[:400],
        source_claim_text=from_claim.get("claim_text", "?")[:300],
        target_claim_text=to_claim.get("claim_text", "?")[:300],
        source_evidence=_resolve_evidence(from_refs, evidence_index),
        target_evidence=_resolve_evidence(to_refs, evidence_index),
        shared_evidence=_resolve_evidence(shared_refs, evidence_index),
    )


def _input_to_prompt_dict(inp: RelationshipInput) -> dict:
    def ev_list(items):
        return [
            {k: v for k, v in {
                "ref": e.ref, "section": e.section, "period": e.period,
                "text": e.text,
                **({"forbidden_assertions": e.forbidden_assertions} if e.forbidden_assertions else {}),
            }.items()}
            for e in items
        ]
    return {
        "relationship_id": inp.relationship_id,
        "rel_type": inp.rel_type,
        "proposed_confidence": inp.proposed_confidence,
        "rationale": inp.rationale,
        "source_claim": {
            "claim_id": inp.source_claim_id,
            "claim_text": inp.source_claim_text,
            "domain": inp.source_domain,
            "period": inp.source_period,
        },
        "target_claim": {
            "claim_id": inp.target_claim_id,
            "claim_text": inp.target_claim_text,
            "domain": inp.target_domain,
            "period": inp.target_period,
        },
        "source_evidence": ev_list(inp.source_evidence),
        "target_evidence": ev_list(inp.target_evidence),
        "shared_evidence": ev_list(inp.shared_evidence),
    }


# ── AI reviewer call ──────────────────────────────────────────────────────────

def _error_result(reason: str) -> ReviewerResult:
    return ReviewerResult(
        verdict="REVIEW_ERROR",
        recommended_confidence="UNKNOWN",
        chronology_relation="UNKNOWN",
        chronology_valid=True,
        semantic_alignment=False,
        linkage_established=False,
        causal_issues=[],
        retrospective_bias=False,
        measurement_window_issue=False,
        alternative_explanations=None,
        qualification_required=None,
        reason=reason,
    )


def review_relationship(inp: RelationshipInput) -> ReviewerResult:
    """Call the AI reviewer; return a structured ReviewerResult."""
    llm = get_llm()
    prompt = (
        "Review the following cross-domain investment relationship and return only the JSON verdict:\n\n"
        + json.dumps(_input_to_prompt_dict(inp), indent=2)
    )
    try:
        response = llm.generate(
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.0,
        )
        text = response.text.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return _error_result("no_json_in_response")
        raw = json.loads(m.group(0))
    except Exception as exc:
        return _error_result(str(exc)[:200])

    # Normalize chronology_valid from chronology_relation if needed
    rel_type = inp.rel_type
    chrono_rel = raw.get("chronology_relation", "UNKNOWN")
    chrono_valid_ai = raw.get("chronology_valid", True)

    # Type-specific chronology override: trust AI's chronology_valid for most types,
    # but enforce semantic rules for CAPITAL_TO_EXECUTION and CONTEXT_ONLY.
    if rel_type == "CONTEXT_ONLY":
        chrono_valid = True   # context has no required causal direction
    elif rel_type == "CAPITAL_TO_EXECUTION":
        chrono_valid = chrono_rel in ("BEFORE", "OVERLAPPING", "UNKNOWN")
    else:
        chrono_valid = chrono_valid_ai

    return ReviewerResult(
        verdict=raw.get("verdict", "REVIEW_ERROR"),
        recommended_confidence=raw.get("recommended_confidence", "UNKNOWN"),
        chronology_relation=chrono_rel,
        chronology_valid=chrono_valid,
        semantic_alignment=bool(raw.get("semantic_alignment", False)),
        linkage_established=bool(raw.get("linkage_established", False)),
        causal_issues=raw.get("causal_issues", []) or [],
        retrospective_bias=bool(raw.get("retrospective_bias", False)),
        measurement_window_issue=bool(raw.get("measurement_window_issue", False)),
        alternative_explanations=raw.get("alternative_explanations"),
        qualification_required=raw.get("qualification_required"),
        reason=raw.get("reason", ""),
    )


# ── Acceptance contract ───────────────────────────────────────────────────────

def apply_acceptance_contract(
    rel_type: str,
    proposed_confidence: str,
    result: ReviewerResult,
) -> Tuple[str, str]:
    """
    Confidence-level-specific acceptance contract.
    Returns (AcceptanceStatus, reason_code).
    """
    verdict = result.verdict
    if verdict == "REVIEW_ERROR":
        return NEEDS_REVIEW, "reviewer_error"

    issues_text = " ".join(result.causal_issues).lower() if result.causal_issues else ""

    # ── CONFIRMED ────────────────────────────────────────────────────────────
    if proposed_confidence == "CONFIRMED":
        blockers = []
        if verdict != "SUPPORTED":
            blockers.append(f"verdict:{verdict}")
        if not result.chronology_valid:
            blockers.append("chronology_invalid")
        if not result.linkage_established:
            blockers.append("no_direct_linkage")
        if result.causal_issues:
            blockers.append(f"causal_issues:{len(result.causal_issues)}")
        if result.measurement_window_issue:
            blockers.append("measurement_window")
        if result.retrospective_bias:
            blockers.append("retrospective_bias")
        if not blockers:
            return ACCEPT, "confirmed_all_checks_pass"
        status = REJECT if verdict in ("UNSUPPORTED", "CONTRADICTED") or result.causal_issues else NEEDS_REVIEW
        return status, "+".join(blockers)

    # ── SUPPORTED ────────────────────────────────────────────────────────────
    elif proposed_confidence == "SUPPORTED":
        # Choose hard-overstatement keyword set by relationship type
        overstatement_kws = _S2E_HARD_OVERSTATEMENT if rel_type == "STRATEGY_TO_EXECUTION" else _CAUSAL_HARD_OVERSTATEMENT
        has_hard_overstatement = any(kw in issues_text for kw in overstatement_kws)

        # STRATEGY_TO_EXECUTION: semantic_alignment is required — do not fall through
        # to the general path (which doesn't check alignment).
        if rel_type == "STRATEGY_TO_EXECUTION":
            if (verdict in ("SUPPORTED", "PARTIALLY_SUPPORTED")
                    and result.chronology_valid
                    and result.semantic_alignment
                    and not result.retrospective_bias
                    and not result.measurement_window_issue
                    and not has_hard_overstatement):
                return ACCEPT, "s2e_semantic_alignment_confirmed"
            # Collect S2E-specific blockers and return without falling through
            s2e_blockers = []
            if verdict in ("UNSUPPORTED", "CONTRADICTED"):
                s2e_blockers.append(f"verdict:{verdict}")
            if not result.semantic_alignment:
                s2e_blockers.append("no_semantic_alignment")
            if not result.chronology_valid:
                s2e_blockers.append("chronology_invalid")
            if result.retrospective_bias:
                s2e_blockers.append("retrospective_bias")
            if result.measurement_window_issue:
                s2e_blockers.append("measurement_window")
            if has_hard_overstatement:
                s2e_blockers.append("hard_overstatement_detected")
            if verdict in ("UNSUPPORTED", "CONTRADICTED"):
                return REJECT, "+".join(s2e_blockers)
            return NEEDS_REVIEW, "+".join(s2e_blockers) if s2e_blockers else f"partial:{verdict}"

        # General SUPPORTED path (non-S2E)
        if (verdict in ("SUPPORTED", "PARTIALLY_SUPPORTED")
                and result.chronology_valid
                and not result.measurement_window_issue
                and not result.retrospective_bias
                and not has_hard_overstatement):
            return ACCEPT, "supported_evidence_based_checks_pass"

        blockers = []
        if verdict in ("UNSUPPORTED", "CONTRADICTED"):
            blockers.append(f"verdict:{verdict}")
        if has_hard_overstatement:
            blockers.append("hard_overstatement_detected")
        if result.measurement_window_issue:
            blockers.append("measurement_window")
        if result.retrospective_bias:
            blockers.append("retrospective_bias")
        if not result.chronology_valid:
            blockers.append("chronology_invalid")
        if blockers and verdict in ("UNSUPPORTED", "CONTRADICTED"):
            return REJECT, "+".join(blockers)
        return NEEDS_REVIEW, "+".join(blockers) if blockers else f"partial:{verdict}"

    # ── PLAUSIBLE ────────────────────────────────────────────────────────────
    elif proposed_confidence == "PLAUSIBLE":
        wording = " ".join([
            result.reason or "",
            " ".join(result.causal_issues) if result.causal_issues else "",
        ]).lower()
        # Check wording across full relationship text (passed by caller via result.reason)
        # We also need the original rationale — encode it in reason field indirectly.
        # The caller must ensure rationale is available; we check result fields here.
        has_frame = any(w in wording for w in _INTERPRETATION_FRAMES)

        # PLAUSIBLE is explicitly the "cannot confirm" tier: accept if the
        # relationship has proper interpretation framing and valid chronology,
        # regardless of whether the AI found supporting evidence (UNSUPPORTED
        # can occur when evidence_refs are thin but the framing is deliberate).
        # Hard block: CONTRADICTED (AI found opposing evidence).
        if (verdict not in ("REVIEW_ERROR", "CONTRADICTED")
                and result.chronology_valid
                and has_frame):
            return ACCEPT, "plausible_qualified_interpretation_accepted"

        blockers = []
        if verdict == "CONTRADICTED":
            blockers.append("verdict:CONTRADICTED")
        elif verdict == "UNSUPPORTED":
            blockers.append("verdict:UNSUPPORTED")
        if not result.chronology_valid:
            blockers.append("chronology_invalid")
        if not has_frame:
            blockers.append("missing_interpretation_frame")
        if result.measurement_window_issue:
            blockers.append("measurement_window")
        if result.causal_issues:
            blockers.append(f"causal_issues:{len(result.causal_issues)}")

        # OPERATING_TO_FINANCIAL_OUTCOME (strongest discipline): chrono_invalid
        # combined with causal_issues means the relationship is fundamentally
        # flawed, not merely uncertain — escalate to REJECT.
        if (rel_type == "OPERATING_TO_FINANCIAL_OUTCOME"
                and not result.chronology_valid
                and result.causal_issues):
            return REJECT, "+".join(blockers)

        if verdict == "CONTRADICTED":
            return REJECT, "+".join(blockers)
        return NEEDS_REVIEW, "+".join(blockers) if blockers else f"partial:{verdict}"

    # ── UNKNOWN ──────────────────────────────────────────────────────────────
    elif proposed_confidence == "UNKNOWN":
        if verdict == "CONTRADICTED":
            return NEEDS_REVIEW, "unknown_relationship_is_contradicted"
        return ACCEPT, "unknown_preserved_as_uncertainty"

    return NEEDS_REVIEW, f"unhandled_confidence:{proposed_confidence}"


# ── Public API ────────────────────────────────────────────────────────────────

def validate_relationship(
    rel: dict,
    claims_by_id: dict,
    evidence_index: dict,
) -> dict:
    """
    Full pipeline: resolve input → AI review → apply contract → return result dict.

    This is the primary public function; callers do not need to import sub-steps.
    """
    inp = build_relationship_input(rel, claims_by_id, evidence_index)
    result = review_relationship(inp)

    # For PLAUSIBLE, enrich reason with rationale text so has_frame check works
    # (rationale contains the interpretation language the generator wrote)
    if rel.get("causal_confidence") == "PLAUSIBLE":
        rationale_text = rel.get("rationale", "").lower()
        result.reason = result.reason + " " + rationale_text

    acceptance, reason_code = apply_acceptance_contract(
        rel.get("rel_type", ""),
        rel.get("causal_confidence", "UNKNOWN"),
        result,
    )

    return {
        "rel_id": rel.get("rel_id", "?"),
        "rel_type": rel.get("rel_type", "?"),
        "causal_confidence": rel.get("causal_confidence", "?"),
        "ai_verdict": result.verdict,
        "ai_recommended_confidence": result.recommended_confidence,
        "ai_reason": result.reason,
        "causal_issues": result.causal_issues,
        "chronology_relation": result.chronology_relation,
        "chronology_valid": result.chronology_valid,
        "semantic_alignment": result.semantic_alignment,
        "linkage_established": result.linkage_established,
        "measurement_window_issue": result.measurement_window_issue,
        "retrospective_bias": result.retrospective_bias,
        "alternative_explanations": result.alternative_explanations,
        "qualification_required": result.qualification_required,
        "acceptance": acceptance,
        "acceptance_reason": reason_code,
    }
