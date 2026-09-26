"""
Claim-level validation for AI-generated investor answers.

Checks each claim in an AI answer against the evidence package that grounded it.
Returns per-claim verdicts: SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, CONTRADICTED.

Also validates narrative fields (why_it_matters, simple_answer, key_points,
economic_reasoning) for forbidden patterns and unsupported inferences.

This is answer-validation only — it does NOT modify canonical management lifecycle states.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


VERDICT_SUPPORTED = "SUPPORTED"
VERDICT_PARTIALLY = "PARTIALLY_SUPPORTED"
VERDICT_UNSUPPORTED = "UNSUPPORTED"
VERDICT_CONTRADICTED = "CONTRADICTED"

# Dual-verdict acceptance statuses
ACCEPT = "ACCEPT"
NEEDS_REVIEW = "NEEDS_REVIEW"
REJECT = "REJECT"


# ── Forbidden phrase groups ────────────────────────────────────────────────────

_PRESCRIPTION_RAMP_PHRASES = [
    "prescriptions increased",
    "prescription growth",
    "prescriptions ramped",
    "prescription volumes",
    "ramp-up successful",
    "ramp was successful",
    "ramp was achieved",
    "commitment fulfilled",
    "commitment was met",
    "commitment was achieved",
    "promise was kept",
    "promise was fulfilled",
]

_FAILED_COMMITMENT_PHRASES = [
    "commitment failed",
    "commitment was missed",
    "promise was missed",
    "promise was broken",
    "did not fulfill",
    "did not deliver",
    "failed to deliver",
    "failed to achieve",
    "missed the commitment",
    "not delivered",
    "not fulfilled",
    "was not met",
]

_REVENUE_ATTRIBUTION_PHRASES = [
    "revenue from ilumya",
    "ilumya revenue",
    "revenue attributable",
    "generated revenue",
    "contributed revenue",
    "drove revenue",
    "led to revenue",
    "increased revenue due to",
    "revenue grew because",
]

# Phrases that assert a value/price hierarchy not supported by evidence.
# Specialty products being "higher-value" is a market inference, not a canonical fact.
_VALUE_HIERARCHY_PHRASES = [
    "higher-value specialty",
    "higher value specialty",
    "premium specialty",
    "higher-margin specialty",
    "higher margin specialty",
    "more profitable specialty",
    "higher-priced specialty",
    "specialty generates higher",
    "specialty commands higher",
]

# Period tokens that can appear in claims (for period-attribution checks)
_PERIOD_PATTERN = re.compile(r"\bfy\d{2,4}\b", re.IGNORECASE)

# Geography tokens for deterministic narrative scope validation.
# These are specific enough to be meaningful scope claims. Common ambiguous
# tokens (e.g. "us", "in") are excluded to avoid false positives.
_GEOGRAPHY_RE = re.compile(
    r"\b(japan|japanese|china|chinese|australia|australian|india|indian|"
    r"singapore|indonesia|thailand|vietnam|malaysia|"
    r"europe|european|germany|german|france|french|brazil|brazilian|"
    r"russia|russian|spain|spanish|italy|italian|netherlands|dutch|"
    r"canada|canadian|south korea|korean|taiwan|"
    r"united kingdom|united states of america|usa|u\.s\.a)\b",
    re.IGNORECASE,
)


def _extract_geography_tokens(text: str) -> List[str]:
    return list({m.group().lower() for m in _GEOGRAPHY_RE.finditer(text)})


def _build_evidence_text_corpus(package: Dict[str, Any]) -> str:
    """Collect all text from all evidence items for geography cross-referencing."""
    parts: List[str] = []
    for section_items in package.get("sections", {}).values():
        if isinstance(section_items, list):
            for item in section_items:
                if not isinstance(item, dict):
                    continue
                for field in ("excerpt", "original_statement", "content", "description"):
                    val = item.get(field) or ""
                    if val:
                        parts.append(val.lower())
    return " ".join(parts)


def _lower(text: str) -> str:
    return str(text or "").lower()


def _build_evidence_index(package: Dict[str, Any]) -> Dict[str, Any]:
    """Build a flat index of all evidence items by their canonical ID.

    Items in most sections use 'item_id'.
    source_limitations items use 'limitation_id' instead.
    Both are indexed so claims can cite either.
    """
    idx: Dict[str, Any] = {}
    for section_items in package.get("sections", {}).values():
        if isinstance(section_items, list):
            for item in section_items:
                if not isinstance(item, dict):
                    continue
                # Most sections use item_id; source_limitations use limitation_id
                key = item.get("item_id") or item.get("limitation_id")
                if key:
                    idx[key] = item
    return idx


def _build_must_not_assert_index(package: Dict[str, Any]) -> Dict[str, List[str]]:
    """Build per-item_id list of must_not_assert phrases for quick lookup."""
    idx: Dict[str, List[str]] = {}
    for section_items in package.get("sections", {}).values():
        if isinstance(section_items, list):
            for item in section_items:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id")
                if not item_id:
                    continue
                guidance = item.get("ai_reasoning_guidance") or {}
                must_not = guidance.get("must_not_assert") or []
                if must_not:
                    idx[item_id] = [_lower(m) for m in must_not]
    return idx


# In narrative fields (why_it_matters, economic_reasoning, key_points), forbidden
# phrases may legitimately appear in negated or conditional contexts, e.g.:
#   "does not establish prescription growth"  (negation — good)
#   "securing prescription growth would require..."  (conditional — good)
# This guard skips a phrase if negation/conditional tokens appear within
# _NARRATIVE_GUARD_WINDOW words before it.
_NARRATIVE_GUARD_WINDOW = 15
_NARRATIVE_GUARD_TOKENS = re.compile(
    r"\b(not|no|without|absent|cannot|does not|do not|absence|lacking|never|"
    r"would|could|if|whether|potential|aiming|targeting|securing|hypothetically)\b",
    re.IGNORECASE,
)


def _is_guarded_context(text: str, phrase: str) -> bool:
    """Return True if the phrase appears in a negated or conditional context."""
    lower = text.lower()
    pos = lower.find(phrase)
    if pos < 0:
        return False
    # Extract the window of text just before the phrase
    window_start = max(0, pos - _NARRATIVE_GUARD_WINDOW * 7)  # ~7 chars/word avg
    preceding = lower[window_start:pos]
    return bool(_NARRATIVE_GUARD_TOKENS.search(preceding))


def _check_forbidden_patterns(text: str, narrative: bool = False, claim_type: Optional[str] = None) -> List[str]:
    """
    Return list of forbidden-pattern violations found in text.
    In narrative mode, negated/conditional contexts are skipped.
    EVIDENCE_GAP_STATEMENT claims are exempt from prescription-ramp checks
    because they describe absent data, not asserted execution.
    """
    lower = _lower(text)
    violations = []
    for phrase in _PRESCRIPTION_RAMP_PHRASES:
        if claim_type == "EVIDENCE_GAP_STATEMENT":
            continue
        if phrase in lower:
            if narrative and _is_guarded_context(text, phrase):
                continue
            violations.append(f"Asserts prescription ramp completion without evidence: '{phrase}'")
    for phrase in _FAILED_COMMITMENT_PHRASES:
        if phrase in lower:
            if narrative and _is_guarded_context(text, phrase):
                continue
            violations.append(f"Treats UNVERIFIED commitment as FAILED: '{phrase}'")
    for phrase in _REVENUE_ATTRIBUTION_PHRASES:
        if phrase in lower:
            if narrative and _is_guarded_context(text, phrase):
                continue
            violations.append(f"Claims revenue attribution without evidence: '{phrase}'")
    for phrase in _VALUE_HIERARCHY_PHRASES:
        if phrase in lower:
            # No guard for value-hierarchy — there's no legitimate conditional/negated
            # use of "higher-value specialty" in an evidence-grounded answer
            violations.append(
                f"Asserts unsupported value hierarchy (not in evidence package): '{phrase}'"
            )
    return violations


def _check_period_attribution(
    claim: Dict[str, Any],
    evidence_index: Dict[str, Any],
) -> List[str]:
    """
    For COMMITMENT_STATEMENT claims, verify the period mentioned in claim_text
    matches the announcement_period of each cited evidence item.

    Returns a list of issue strings for any period mismatches found.
    This catches the most dangerous form of content mismatch: attributing a
    statement to the wrong fiscal year.
    """
    if claim.get("claim_type") not in ("COMMITMENT_STATEMENT", "STRATEGIC_DIRECTION"):
        return []

    claim_text = claim.get("claim_text", "")
    claim_periods = set(m.lower() for m in _PERIOD_PATTERN.findall(claim_text))
    if not claim_periods:
        # No period mentioned in claim — no check possible
        return []

    issues = []
    for ref in claim.get("evidence_refs") or []:
        item = evidence_index.get(ref)
        if not item:
            continue
        item_period = _lower(item.get("announcement_period") or "")
        if not item_period:
            continue
        # Normalise to "fyYY" form for comparison
        if item_period not in claim_periods and not any(
            item_period.endswith(p[-2:]) for p in claim_periods
        ):
            issues.append(
                f"Period mismatch: claim mentions {claim_periods} but {ref} has "
                f"announcement_period={item_period}"
            )
    return issues


def _check_must_not_assert_semantic(
    claim_text: str,
    ref: str,
    must_not_phrases: List[str],
) -> List[str]:
    """
    Improved must_not_assert check using all-key-token matching.

    A violation fires only when ALL semantically loaded tokens (>= 4 chars)
    from the forbidden phrase appear in the claim.  This avoids false positives
    from subject nouns shared between the commitment description and the
    forbidden assertion (e.g. 'prescriptions' appearing in 'ramping up
    ILUMYA prescriptions' should not trigger 'prescriptions increased').

    Limitation: does not catch stem-level paraphrases ('prescription volumes
    increased' ≠ 'prescriptions increased') — deterministic detection at that
    level requires embedding similarity, which is out of scope here.
    """
    lower_claim = _lower(claim_text)
    issues = []
    for forbidden in must_not_phrases:
        # Key tokens: meaningful words (>= 4 chars) from the forbidden phrase
        key_tokens = [t for t in forbidden.split() if len(t) >= 4]
        if not key_tokens:
            continue
        matching = [t for t in key_tokens if t in lower_claim]
        # Require ALL key tokens to match (conservative: avoids false positives
        # from shared subject nouns)
        if len(matching) == len(key_tokens):
            issues.append(
                f"Claim may violate must_not_assert guidance for {ref}: "
                f"'{forbidden[:80]}'"
            )
    return issues


def validate_narrative_fields(
    ai_answer: Dict[str, Any],
    package: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Scan all free-text narrative fields for forbidden patterns and scope violations.

    Returns a list of {field, violation} dicts.
    These are answer-level issues separate from per-claim verdicts.

    Scope check: if a narrative field mentions a specific geography not present in
    any evidence item, that is a scope violation — the claim cannot be grounded.
    This catches fabricated geographies even when the extractor topic-matches them
    to a declared claim with a different geography.
    """
    issues: List[Dict[str, str]] = []

    # Collect all narrative text with their field labels
    to_check: List[Tuple[str, str]] = [
        ("simple_answer", ai_answer.get("simple_answer") or ""),
        ("why_it_matters", ai_answer.get("why_it_matters") or ""),
    ]
    for i, kp in enumerate(ai_answer.get("key_points") or []):
        to_check.append((f"key_points[{i}]", kp))
    er = ai_answer.get("economic_reasoning") or {}
    for field in (
        "management_intentions",
        "economic_purpose",
        "observable_execution",
        "established_outcomes",
        "remaining_uncertainty",
    ):
        if er.get(field):
            to_check.append((f"economic_reasoning.{field}", er[field]))

    for field_label, text in to_check:
        violations = _check_forbidden_patterns(text, narrative=True)
        for v in violations:
            issues.append({"field": field_label, "violation": v})

    # Geography scope check: flag any geography not found in the evidence package.
    # Build corpus once and reuse across all fields.
    evidence_corpus = _build_evidence_text_corpus(package)
    for field_label, text in to_check:
        for geo in _extract_geography_tokens(text):
            if not re.search(r"\b" + re.escape(geo) + r"\b", evidence_corpus):
                issues.append({
                    "field": field_label,
                    "violation": (
                        f"Narrative mentions geography '{geo}' not found in "
                        f"any evidence item — cannot be grounded"
                    ),
                })

    return issues


def validate_claim(
    claim: Dict[str, Any],
    evidence_index: Dict[str, Any],
    must_not_assert_index: Dict[str, List[str]],
    global_constraints: List[str],
) -> Dict[str, Any]:
    """
    Validate one AI-generated claim against the evidence package.
    Returns a validation record with verdict, rationale, and issues.
    """
    claim_id = claim.get("claim_id", "?")
    claim_text = claim.get("claim_text", "")
    evidence_refs = claim.get("evidence_refs") or []
    claim_type = claim.get("claim_type", "UNKNOWN")

    issues: List[str] = []
    warnings: List[str] = []
    supporting_evidence: List[str] = []

    # 1. Check forbidden patterns (absolute violations)
    forbidden = _check_forbidden_patterns(claim_text, claim_type=claim_type)
    issues.extend(forbidden)

    # 2. Check evidence refs resolve
    unresolved_refs: List[str] = []
    for ref in evidence_refs:
        if ref not in evidence_index:
            unresolved_refs.append(ref)
        else:
            supporting_evidence.append(ref)

    if unresolved_refs:
        issues.append(f"Unresolved evidence refs: {unresolved_refs}")

    # 3. Check must_not_assert for each cited evidence item (improved semantic check)
    for ref in evidence_refs:
        if ref in must_not_assert_index:
            semantic_issues = _check_must_not_assert_semantic(
                claim_text, ref, must_not_assert_index[ref]
            )
            issues.extend(semantic_issues)

    # 4. Period attribution check for COMMITMENT_STATEMENT and STRATEGIC_DIRECTION claims
    period_issues = _check_period_attribution(claim, evidence_index)
    # Period mismatches are warnings (not hard issues) — a claim may use a
    # different normalisation of the year (e.g. "FY2020" vs "fy20")
    warnings.extend(period_issues)

    # 5. EXECUTION_GAP claims should reference adverse_evidence
    if claim_type == "EXECUTION_GAP":
        has_ae_ref = any(
            evidence_index.get(r, {}).get("evidence_type") == "ADVERSE_EVIDENCE"
            for r in evidence_refs
        )
        if not has_ae_ref and evidence_refs:
            warnings.append(
                "EXECUTION_GAP claim does not cite adverse_evidence item — check grounding"
            )

    # 6. PRODUCT_AVAILABILITY claims should reference OE items
    if claim_type == "PRODUCT_AVAILABILITY":
        has_oe_ref = any(
            evidence_index.get(r, {}).get("evidence_type") == "PRODUCT_AVAILABILITY"
            for r in evidence_refs
        )
        if not has_oe_ref and evidence_refs:
            warnings.append(
                "PRODUCT_AVAILABILITY claim does not cite observable_execution_evidence item"
            )

    # 7. Claims with no evidence refs (outside BUSINESS_CONTEXT / UNCERTAINTY / EVIDENCE_GAP_STATEMENT)
    if not evidence_refs and claim_type not in ("BUSINESS_CONTEXT", "UNCERTAINTY", "EVIDENCE_GAP_STATEMENT"):
        warnings.append("Claim has no evidence_refs — cannot verify grounding")

    # Determine verdict
    if issues:
        is_contradiction = any(
            any(
                phrase in _lower(issue)
                for phrase in [
                    "must_not_assert",
                    "treats unverified",
                    "prescription ramp",
                    "revenue attribution",
                    "value hierarchy",
                ]
            )
            for issue in issues
        )
        verdict = VERDICT_CONTRADICTED if is_contradiction else VERDICT_UNSUPPORTED
    elif warnings and not supporting_evidence:
        verdict = VERDICT_UNSUPPORTED
    elif warnings:
        verdict = VERDICT_PARTIALLY
    else:
        verdict = VERDICT_SUPPORTED

    return {
        "claim_id": claim_id,
        "claim_text": claim_text,
        "claim_type": claim_type,
        "evidence_refs": evidence_refs,
        "verdict": verdict,
        "issues": issues,
        "warnings": warnings,
        "supporting_evidence": supporting_evidence,
    }


def _determine_acceptance(
    det_verdict: str,
    ai_verdict: str,
    ai_scope_issues: Optional[List[str]] = None,
    ai_qualifications_missing: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """
    Combine deterministic and AI verdicts into (final_verdict, final_acceptance_status).

    Deterministic rejection is absolute — AI cannot override it.
    When the two mechanisms disagree, the claim is flagged NEEDS_REVIEW rather than
    accepted.  Only full agreement (both SUPPORTED) yields ACCEPT.

    Inconsistent reviewer responses (UNSUPPORTED verdict but no issues identified, or
    PARTIALLY_SUPPORTED with scope issues) must result in NEEDS_REVIEW, never
    automatic acceptance — a silent inconsistency cannot approve a claim.
    """
    # Deterministic rejections are final
    if det_verdict in (VERDICT_CONTRADICTED, VERDICT_UNSUPPORTED):
        return det_verdict, REJECT

    # AI errors flag for human review
    if ai_verdict == "REVIEW_ERROR":
        return det_verdict, NEEDS_REVIEW

    # Inconsistent reviewer response: AI says UNSUPPORTED but identified no specific
    # issues. This cannot be auto-promoted to acceptance — the inconsistency itself
    # is a signal that requires human review.
    if (
        ai_verdict == VERDICT_UNSUPPORTED
        and not (ai_scope_issues or [])
        and not (ai_qualifications_missing or [])
    ):
        return VERDICT_UNSUPPORTED, NEEDS_REVIEW

    # Both fully support → accept
    if det_verdict == VERDICT_SUPPORTED and ai_verdict == VERDICT_SUPPORTED:
        return VERDICT_SUPPORTED, ACCEPT

    # Det supported + AI partial → only accept when no scope mismatches identified.
    # Scope issues indicate a geographic, period, or financial scope problem that
    # must not be silently accepted.
    if det_verdict == VERDICT_SUPPORTED and ai_verdict == VERDICT_PARTIALLY:
        if ai_scope_issues:
            return VERDICT_PARTIALLY, NEEDS_REVIEW
        return VERDICT_PARTIALLY, ACCEPT

    # Det has warnings (PARTIALLY) + AI also sees issues → reject
    if det_verdict == VERDICT_PARTIALLY and ai_verdict in (
        VERDICT_UNSUPPORTED, VERDICT_CONTRADICTED
    ):
        return ai_verdict, REJECT

    # Any other combination = disagreement → flag for review
    return ai_verdict if ai_verdict != "REVIEW_ERROR" else det_verdict, NEEDS_REVIEW


def validate_claim_with_ai(
    claim: Dict[str, Any],
    evidence_index: Dict[str, Any],
    must_not_assert_index: Dict[str, List[str]],
    global_constraints: List[str],
    model: str = "gpt-5-mini-2025-08-07",
) -> Dict[str, Any]:
    """
    Validate a single claim with both deterministic and independent AI review.

    Deterministic checks run first.  For claims that pass deterministic checks,
    an independent AI model evaluates whether the cited evidence actually
    establishes the claim.  AI approval cannot override deterministic rejection.

    Returns the acceptance contract per claim.
    """
    from intelligence.ask_intrinsiciq.ai_claim_reviewer import review_claim

    det = validate_claim(claim, evidence_index, must_not_assert_index, global_constraints)

    # Skip AI call if deterministic already rejects — saves tokens
    if det["verdict"] in (VERDICT_CONTRADICTED, VERDICT_UNSUPPORTED):
        final_verdict, acceptance = det["verdict"], REJECT
        ai_result = {
            "verdict": "SKIPPED",
            "confidence": "N/A",
            "reason": "AI review skipped — deterministic rejection is final",
            "scope_issues": [],
            "qualifications_missing": [],
        }
    else:
        cited_items = [
            evidence_index[ref]
            for ref in (claim.get("evidence_refs") or [])
            if ref in evidence_index
        ]
        ai_result = review_claim(claim, cited_items, model=model)
        final_verdict, acceptance = _determine_acceptance(
            det["verdict"],
            ai_result["verdict"],
            ai_scope_issues=ai_result.get("scope_issues"),
            ai_qualifications_missing=ai_result.get("qualifications_missing"),
        )

    return {
        "claim_id": det["claim_id"],
        "claim_text": det["claim_text"],
        "claim_type": det["claim_type"],
        "evidence_refs": det["evidence_refs"],
        # Deterministic leg
        "deterministic_verdict": det["verdict"],
        "deterministic_issues": det["issues"],
        "deterministic_warnings": det["warnings"],
        # AI leg
        "ai_verdict": ai_result["verdict"],
        "ai_confidence": ai_result.get("confidence", ""),
        "ai_reason": ai_result.get("reason", ""),
        "ai_scope_issues": ai_result.get("scope_issues", []),
        "ai_qualifications_missing": ai_result.get("qualifications_missing", []),
        # Combined
        "final_verdict": final_verdict,
        "final_acceptance_status": acceptance,
        "reason": (
            ai_result.get("reason", "")
            if acceptance != REJECT or not det["issues"]
            else "; ".join(det["issues"][:3])
        ),
    }


def validate_answer_with_ai(
    ai_answer: Dict[str, Any],
    package: Dict[str, Any],
    model: str = "gpt-5-mini-2025-08-07",
) -> Dict[str, Any]:
    """
    Dual-validation: deterministic + independent AI review for every claim.

    answer_status values:
      PASS              all claims ACCEPT, no narrative issues
      FAIL_NEEDS_REVIEW one or more claims are NEEDS_REVIEW
      FAIL_CONTRADICTED one or more claims are REJECT due to contradiction
      FAIL_UNSUPPORTED  one or more claims are REJECT due to unsupported
      FAIL_NARRATIVE    claims pass but narrative fields have violations
    """
    evidence_index = _build_evidence_index(package)
    must_not_assert_index = _build_must_not_assert_index(package)
    global_constraints = package.get("package_constraints", {}).get(
        "ai_reasoning_global_constraints", []
    )

    claims = ai_answer.get("claims") or []
    claim_results: List[Dict[str, Any]] = []
    for claim in claims:
        result = validate_claim_with_ai(
            claim, evidence_index, must_not_assert_index, global_constraints, model=model
        )
        claim_results.append(result)

    narrative_issues = validate_narrative_fields(ai_answer, package)

    accepted = [r for r in claim_results if r["final_acceptance_status"] == ACCEPT]
    needs_review = [r for r in claim_results if r["final_acceptance_status"] == NEEDS_REVIEW]
    rejected = [r for r in claim_results if r["final_acceptance_status"] == REJECT]

    rejected_contradicted = [
        r for r in rejected if r["deterministic_verdict"] == VERDICT_CONTRADICTED
        or r["final_verdict"] == VERDICT_CONTRADICTED
    ]

    if rejected_contradicted:
        answer_status = "FAIL_CONTRADICTED"
    elif rejected:
        answer_status = "FAIL_UNSUPPORTED"
    elif needs_review:
        answer_status = "FAIL_NEEDS_REVIEW"
    elif narrative_issues:
        answer_status = "FAIL_NARRATIVE"
    else:
        answer_status = "PASS"

    return {
        "answer_status": answer_status,
        "total_claims": len(claim_results),
        "claims_accepted": len(accepted),
        "claims_needs_review": len(needs_review),
        "claims_rejected": len(rejected),
        "claim_results": claim_results,
        "narrative_issues": narrative_issues,
        "narrative_issues_count": len(narrative_issues),
        "all_issues": [
            {"claim_id": r["claim_id"], "issue": issue}
            for r in claim_results
            for issue in r["deterministic_issues"]
        ],
        "all_warnings": [
            {"claim_id": r["claim_id"], "warning": w}
            for r in claim_results
            for w in r["deterministic_warnings"]
        ],
    }


def validate_answer(
    ai_answer: Dict[str, Any],
    package: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Validate all claims and narrative fields in an AI-generated answer.
    Returns a validation report.
    """
    evidence_index = _build_evidence_index(package)
    must_not_assert_index = _build_must_not_assert_index(package)
    global_constraints = package.get("package_constraints", {}).get(
        "ai_reasoning_global_constraints", []
    )

    # Per-claim validation
    claims = ai_answer.get("claims") or []
    claim_results: List[Dict[str, Any]] = []
    for claim in claims:
        result = validate_claim(claim, evidence_index, must_not_assert_index, global_constraints)
        claim_results.append(result)

    # Narrative field validation
    narrative_issues = validate_narrative_fields(ai_answer, package)

    # Summary counts
    by_verdict: Dict[str, int] = {
        VERDICT_SUPPORTED: 0,
        VERDICT_PARTIALLY: 0,
        VERDICT_UNSUPPORTED: 0,
        VERDICT_CONTRADICTED: 0,
    }
    for r in claim_results:
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1

    all_issues = [
        {"claim_id": r["claim_id"], "issue": issue}
        for r in claim_results
        for issue in r["issues"]
    ]
    all_warnings = [
        {"claim_id": r["claim_id"], "warning": w}
        for r in claim_results
        for w in r["warnings"]
    ]

    # Overall pass/fail — narrative violations are separate from claim verdicts
    n_contradicted = by_verdict[VERDICT_CONTRADICTED]
    n_unsupported = by_verdict[VERDICT_UNSUPPORTED]
    has_narrative_issues = len(narrative_issues) > 0
    claims_passed = n_contradicted == 0 and n_unsupported == 0

    if n_contradicted > 0:
        answer_status = "FAIL_CONTRADICTED"
    elif n_unsupported > 0:
        answer_status = "FAIL_UNSUPPORTED"
    elif has_narrative_issues:
        answer_status = "FAIL_NARRATIVE"
    else:
        answer_status = "PASS"

    return {
        "answer_status": answer_status,
        "total_claims": len(claim_results),
        "verdict_summary": by_verdict,
        "issues_count": len(all_issues),
        "warnings_count": len(all_warnings),
        "narrative_issues": narrative_issues,
        "narrative_issues_count": len(narrative_issues),
        "claim_results": claim_results,
        "all_issues": all_issues,
        "all_warnings": all_warnings,
        "evidence_items_available": len(evidence_index),
    }


def _get_source_field_text(ai_answer: Dict[str, Any], source_field: str) -> str:
    """Return the original narrative text for a given source_field path string."""
    if not source_field:
        return ""
    if source_field.startswith("evidence_gaps["):
        m = re.search(r"\[(\d+)\]", source_field)
        if m:
            idx = int(m.group(1))
            gaps = ai_answer.get("evidence_gaps") or []
            return gaps[idx] if idx < len(gaps) else ""
        return ""
    if source_field.startswith("key_points["):
        m = re.search(r"\[(\d+)\]", source_field)
        if m:
            idx = int(m.group(1))
            kps = ai_answer.get("key_points") or []
            return kps[idx] if idx < len(kps) else ""
        return ""
    if source_field.startswith("economic_reasoning."):
        field = source_field[len("economic_reasoning."):]
        er = ai_answer.get("economic_reasoning") or {}
        return er.get(field, "") or ""
    return ai_answer.get(source_field, "") or ""


def _find_source_text_by_content(ai_answer: Dict[str, Any], claim_text: str) -> str:
    """
    Fallback: when the extractor did not record source_field, scan all narrative
    fields for text that contains or substantially overlaps the claim text.
    Returns the full field text if found, so the reviewer has surrounding context.
    """
    if not claim_text:
        return ""
    needle = claim_text.lower().strip().rstrip(".")
    if len(needle) < 8:
        return ""

    er = ai_answer.get("economic_reasoning") or {}
    candidates = [
        ("simple_answer", ai_answer.get("simple_answer", "") or ""),
        ("why_it_matters", ai_answer.get("why_it_matters", "") or ""),
    ]
    for field in ("management_intentions", "economic_purpose", "observable_execution",
                  "established_outcomes", "remaining_uncertainty"):
        val = er.get(field, "") or ""
        if val:
            candidates.append((f"economic_reasoning.{field}", val))
    for i, kp in enumerate(ai_answer.get("key_points") or []):
        candidates.append((f"key_points[{i}]", kp or ""))
    for i, gap in enumerate(ai_answer.get("evidence_gaps") or []):
        candidates.append((f"evidence_gaps[{i}]", gap or ""))

    for _field, text in candidates:
        if needle in text.lower():
            return text
    return ""


def validate_answer_complete(
    ai_answer: Dict[str, Any],
    package: Dict[str, Any],
    model: str = "gpt-5-mini-2025-08-07",
) -> Dict[str, Any]:
    """
    End-to-end answer integrity validation (Mission 5).

    Step 1: Independent claim extraction from all narrative fields.
    Step 2: Dual-validation of all declared claims.
    Step 3: Dual-validation of all undeclared material claims against full package.
    Step 4: Final acceptance gate.

    answer_status values:
      PASS                all claims ACCEPT + extraction COMPLETE + no narrative issues
      FAIL_INCOMPLETE     extraction failed or critical validation errors
      FAIL_UNDECLARED     undeclared material claims found that did not ACCEPT
      FAIL_CONTRADICTED   one or more declared claims REJECTED for contradiction
      FAIL_UNSUPPORTED    one or more declared claims REJECTED for lack of support
      FAIL_NEEDS_REVIEW   claims flagged for human review
      FAIL_NARRATIVE      narrative field violations
    """
    from intelligence.ask_intrinsiciq.claim_extractor import extract_claims
    from intelligence.ask_intrinsiciq.ai_claim_reviewer import review_claim

    evidence_index = _build_evidence_index(package)
    must_not_assert_index = _build_must_not_assert_index(package)
    global_constraints = package.get("package_constraints", {}).get(
        "ai_reasoning_global_constraints", []
    )

    # ── Step 1: Independent claim extraction ──────────────────────────────────
    extraction_result = extract_claims(ai_answer, package, model=model)
    extraction_error = extraction_result.get("extraction_error")
    coverage_assessment = extraction_result.get("coverage_assessment", "INCOMPLETE")

    # ── Step 2: Dual-validate declared claims ─────────────────────────────────
    declared_claims = ai_answer.get("claims") or []
    declared_results: List[Dict[str, Any]] = []
    for claim in declared_claims:
        result = validate_claim_with_ai(
            claim, evidence_index, must_not_assert_index, global_constraints, model=model
        )
        declared_results.append(result)

    # ── Step 3: Validate undeclared material claims ───────────────────────────
    # For undeclared claims (no declared evidence_refs), pass full package evidence
    all_package_items: List[Dict[str, Any]] = []
    for section_items in package.get("sections", {}).values():
        if isinstance(section_items, list):
            all_package_items.extend(
                item for item in section_items if isinstance(item, dict)
            )

    undeclared_results: List[Dict[str, Any]] = []
    for ec in extraction_result.get("undeclared_claims") or []:
        suggested = ec.get("suggested_refs") or []
        cited_items = [evidence_index[r] for r in suggested if r in evidence_index]
        # For undeclared claims, always pass full package as fallback context
        context_items = all_package_items if not cited_items else None

        ec_text = ec.get("claim_text") or ec.get("text", "")
        ec_claim_type = ec.get("claim_type", "UNCERTAINTY")
        synth_claim = {
            "claim_id": ec.get("extraction_id", "EX-?"),
            "claim_text": ec_text,
            "claim_type": ec_claim_type,
            "evidence_refs": suggested,
        }

        # For undeclared claims, only check forbidden patterns deterministically.
        # Absence of refs is expected (they were not declared) — skip the "no refs"
        # warning and always call the AI reviewer with full package context.
        det_issues = _check_forbidden_patterns(ec_text, claim_type=ec_claim_type)
        if det_issues:
            # Forbidden pattern in an undeclared claim → immediate REJECT
            det_verdict = VERDICT_CONTRADICTED
            det_warnings: List[str] = []
            ai_result = {
                "verdict": "SKIPPED",
                "confidence": "N/A",
                "reason": "AI review skipped — deterministic forbidden-pattern rejection",
                "scope_issues": [],
                "qualifications_missing": [],
            }
            final_verdict, acceptance = VERDICT_CONTRADICTED, REJECT
        else:
            det_verdict = VERDICT_SUPPORTED  # no deterministic issues; defer to AI
            det_warnings = []
            source_field = ec.get("source_field", "")
            source_text = _get_source_field_text(ai_answer, source_field)
            # Fallback: when extractor did not record source_field, search answer fields
            # for the claim text to recover source context.
            if not source_text and ec_text:
                source_text = _find_source_text_by_content(ai_answer, ec_text)
            ai_result = review_claim(
                synth_claim,
                cited_items,
                model=model,
                package_context_items=context_items,
                source_context=source_text or None,
            )
            ai_v = ai_result["verdict"]
            ai_scope_issues = ai_result.get("scope_issues") or []
            ai_qual_missing = ai_result.get("qualifications_missing") or []
            if ai_v in (VERDICT_CONTRADICTED, VERDICT_UNSUPPORTED) and (
                ai_scope_issues or ai_qual_missing
            ):
                # Reviewer identified specific issues → reliable rejection
                final_verdict, acceptance = ai_v, REJECT
            elif ai_v in (VERDICT_CONTRADICTED, VERDICT_UNSUPPORTED):
                # No scope_issues / qualifications supplied — inconsistent response
                # (mirrors _determine_acceptance M8 fix for declared claims)
                final_verdict, acceptance = ai_v, NEEDS_REVIEW
            elif ai_v == VERDICT_SUPPORTED:
                final_verdict, acceptance = VERDICT_SUPPORTED, ACCEPT
            elif ai_v == "REVIEW_ERROR":
                final_verdict, acceptance = VERDICT_PARTIALLY, NEEDS_REVIEW
            else:
                final_verdict, acceptance = ai_v, NEEDS_REVIEW
        det_issues_final = det_issues

        undeclared_results.append({
            "claim_id": ec.get("extraction_id", "EX-?"),
            "claim_text": ec_text,
            "claim_type": ec_claim_type,
            "source_field": ec.get("source_field", ""),
            "evidence_refs": suggested,
            "is_undeclared": True,
            "deterministic_verdict": det_verdict,
            "deterministic_issues": det_issues_final,
            "deterministic_warnings": det_warnings,
            "ai_verdict": ai_result["verdict"],
            "ai_confidence": ai_result.get("confidence", ""),
            "ai_reason": ai_result.get("reason", ""),
            "ai_scope_issues": ai_result.get("scope_issues", []),
            "ai_qualifications_missing": ai_result.get("qualifications_missing", []),
            "final_verdict": final_verdict,
            "final_acceptance_status": acceptance,
            "reason": ai_result.get("reason", "") or "; ".join(det_issues_final[:2]),
        })

    # ── Step 4: Narrative validation ──────────────────────────────────────────
    narrative_issues = validate_narrative_fields(ai_answer, package)

    # ── Step 5: Final acceptance gate ─────────────────────────────────────────
    all_results = declared_results + undeclared_results

    declared_accepted = [r for r in declared_results if r.get("final_acceptance_status") == ACCEPT]
    declared_needs_review = [r for r in declared_results if r.get("final_acceptance_status") == NEEDS_REVIEW]
    declared_rejected = [r for r in declared_results if r.get("final_acceptance_status") == REJECT]
    declared_rejected_contradiction = [
        r for r in declared_rejected
        if r.get("deterministic_verdict") == VERDICT_CONTRADICTED
        or r.get("final_verdict") == VERDICT_CONTRADICTED
    ]

    undeclared_accepted = [r for r in undeclared_results if r.get("final_acceptance_status") == ACCEPT]
    undeclared_needs_review = [r for r in undeclared_results if r.get("final_acceptance_status") == NEEDS_REVIEW]
    undeclared_rejected = [r for r in undeclared_results if r.get("final_acceptance_status") == REJECT]

    # Determine overall answer status (most severe wins)
    if extraction_error:
        answer_status = "FAIL_INCOMPLETE"
    elif declared_rejected_contradiction:
        answer_status = "FAIL_CONTRADICTED"
    elif declared_rejected:
        answer_status = "FAIL_UNSUPPORTED"
    elif undeclared_rejected:
        answer_status = "FAIL_UNDECLARED"
    elif declared_needs_review or undeclared_needs_review:
        answer_status = "FAIL_NEEDS_REVIEW"
    elif narrative_issues:
        answer_status = "FAIL_NARRATIVE"
    elif coverage_assessment == "INCOMPLETE" and not extraction_error:
        answer_status = "FAIL_INCOMPLETE"
    else:
        answer_status = "PASS"

    return {
        "answer_status": answer_status,
        # Declared claims
        "declared_total": len(declared_claims),
        "declared_accepted": len(declared_accepted),
        "declared_needs_review": len(declared_needs_review),
        "declared_rejected": len(declared_rejected),
        "declared_claim_results": declared_results,
        # Undeclared claims
        "undeclared_total": len(undeclared_results),
        "undeclared_accepted": len(undeclared_accepted),
        "undeclared_needs_review": len(undeclared_needs_review),
        "undeclared_rejected": len(undeclared_rejected),
        "undeclared_claim_results": undeclared_results,
        # Extraction
        "extraction_result": {
            "coverage_assessment": coverage_assessment,
            "total_extracted": extraction_result.get("total_extracted", 0),
            "undeclared_count": extraction_result.get("undeclared_count", 0),
            "coverage_notes": extraction_result.get("coverage_notes", ""),
            "extraction_error": extraction_error,
            "all_extracted_claims": extraction_result.get("extracted_claims", []),
        },
        # Narrative
        "narrative_issues": narrative_issues,
        "narrative_issues_count": len(narrative_issues),
        # Flat issue lists for reporting
        "all_issues": [
            {"claim_id": r["claim_id"], "issue": issue}
            for r in all_results
            for issue in r.get("deterministic_issues", []) + r.get("issues", [])
        ],
        "all_warnings": [
            {"claim_id": r["claim_id"], "warning": w}
            for r in all_results
            for w in r.get("deterministic_warnings", []) + r.get("warnings", [])
        ],
    }
