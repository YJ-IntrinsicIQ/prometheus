"""
Independent AI-assisted claim reviewer for Mission 4.

Receives a single AI-generated claim and the evidence items it cited, then
asks a separate AI model invocation whether the claim is genuinely supported.

This reviewer is intentionally isolated from the answer generator:
- It sees only the claim text and its cited evidence items (not the full package).
- It cannot override a deterministic CONTRADICTED or UNSUPPORTED verdict.
- It evaluates support, not plausibility — a claim can be economically reasonable
  yet still UNSUPPORTED if the cited evidence does not establish it.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from knowledge.ai import get_llm, AIProviderError, AIResponseError
from knowledge.ai.cache import cache_get, cache_put, make_fingerprint

VERDICTS = frozenset({"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED"})
VERDICT_REVIEW_ERROR = "REVIEW_ERROR"

_REVIEW_SCHEMA = {
    "type": "object",
    "required": ["verdict", "confidence", "reason", "scope_issues", "qualifications_missing"],
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED"],
        },
        "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "reason": {"type": "string"},
        "scope_issues": {"type": "array", "items": {"type": "string"}},
        "qualifications_missing": {"type": "array", "items": {"type": "string"}},
    },
}

_EVIDENCE_GAP_REVIEWER_SYSTEM_PROMPT = """\
You are an independent investment research validator. You receive one EVIDENCE-GAP
STATEMENT — a claim that certain information is ABSENT from a provided evidence
package — and the evidence items associated with the claim.

Your task is to evaluate whether the stated absence is genuinely confirmed by the
available evidence items. This is NOT a review of whether evidence positively
establishes an outcome.

EVALUATION CRITERIA:

1. DOES THE PACKAGE CONFIRM THE ABSENCE? Examine the provided evidence items. Do they
   explicitly state that the described information is unavailable, missing, or unresolvable?
   Source limitation items (SL-*) and adverse evidence items (AE-*) that say "no data
   available" or "cannot be verified" SUPPORT the absence claim.

2. SCOPE OF THE CLAIM: Does the claim stay within what the package can establish?
   - "The package contains no prescription-volume data for ILUMYA" → reviewable from package
   - "Sun Pharma has never publicly disclosed prescription-volume data" → requires external
     knowledge beyond this package; flag as PARTIALLY_SUPPORTED at best

3. SPECIFICITY MATCH: Does the specific product, geography, or commitment described in
   the claim match the limitation items provided?

4. EMBEDDED QUANTITATIVE ASSERTIONS: If the gap description contains specific numbers,
   percentages, dates, growth rates, or named regulatory bodies as part of describing
   what is absent (e.g., "prescription data showing 500% growth", "approval from PMDA
   dated 2023"), those specifics are themselves factual assertions that require evidence.
   An absence claim cannot establish what the absent data would have shown. Flag any
   embedded quantitative or institutional specifics as PARTIALLY_SUPPORTED with a
   scope_issue describing which specific is unverifiable.

5. ORIGINAL SOURCE TEXT FIDELITY (when source text is provided): If an ORIGINAL SOURCE
   TEXT is included, verify that the extracted claim accurately represents it. If the claim
   adds specifics not in the source, changes conditional language to definitive, or
   introduces data not present in the source, return PARTIALLY_SUPPORTED with a scope_issue
   describing the fidelity problem.

VERDICT DEFINITIONS for absence claims:
- SUPPORTED: The provided items explicitly confirm the stated information is absent or
  unresolvable within the package scope, and no embedded quantitative assertions are present.
- PARTIALLY_SUPPORTED: The absence is partly confirmed but the claim overstates scope,
  embeds unverifiable specifics, or the evidence only indirectly supports the absence.
- UNSUPPORTED: The package actually DOES contain the information described as absent.
- CONTRADICTED: The claim directly contradicts what an evidence item explicitly shows
  (e.g., claims "no launch data" but an item explicitly records the launch date).

IMPORTANT: Do NOT evaluate absence claims as if they were positive factual claims.
The standard question for a positive claim ("does evidence establish X happened?") is
inverted here ("does evidence confirm X is missing from this package?").
"""

_REVIEWER_SYSTEM_PROMPT = """\
You are an independent investment research validator. You receive one investor claim
and the evidence items the claim cited. Your task is to determine whether the claim
is genuinely supported by those evidence items — not merely whether a citation exists.

EVALUATION CRITERIA — check each one explicitly before giving a verdict:

1. EVIDENCE ESTABLISHES CLAIM: Does the cited evidence actually establish what the claim
   asserts? A citation is not the same as proof. The content of the evidence must match
   the content of the claim.

2. SCOPE MATCH: Do the company, product, geography, fiscal period, and financial scope
   in the claim match those in the cited evidence?

3. OUTCOME vs INTENTION: If the evidence shows a management commitment, intention, or
   target, has the claim correctly labelled it as such rather than as a completed outcome?
   Evidence with outcome_status=UNVERIFIED or CLAIM_ONLY must not be presented as achieved.

4. CAUSAL LIMITS: Does the claim stay within what the evidence allows causally?
   Temporal proximity (X happened, then Y happened) does not establish causation.
   Product availability (is_product_availability=True) does not establish prescription
   growth or revenue uplift.

5. QUALIFICATIONS: Has the claim omitted material qualifications present in the evidence?
   For example: unverified status, adverse evidence, source limitations, or conditions
   that limit the conclusion.

6. ECONOMIC_INTERPRETATION CLAIMS: When claim_type is ECONOMIC_INTERPRETATION, the claim
   is asserting logical consistency between a stated management intention and the company's
   business model — NOT that the intention was executed. CLAIM_ONLY or UNVERIFIED outcome
   status of cited commitment items (PT-*) does NOT make the economic connection invalid.
   Evaluate whether the stated commitment falls within the business model category described
   by the cited BC-CM-* item. If it does (e.g., specialty product commitment + "revenue model
   includes specialty pharmaceutical sales"), the claim is SUPPORTED. The commitment's
   execution status is irrelevant to this logical consistency check.

VERDICT DEFINITIONS:
- SUPPORTED: The cited evidence directly and fully establishes the claim without scope
  mismatches or material omitted qualifications.
- PARTIALLY_SUPPORTED: The evidence partially supports the claim but scope issues,
  omitted qualifications, or limited over-interpretation are present.
- UNSUPPORTED: The cited items do not establish the claim. The claim may be accurate in
  isolation but the evidence provided does not prove it.
- CONTRADICTED: The claim contradicts the cited evidence — e.g. asserts a completed
  outcome when evidence explicitly marks it as UNVERIFIED or CLAIM_ONLY, or asserts
  prescription growth when evidence only shows product availability.

7. ORIGINAL SOURCE TEXT FIDELITY (when source text is provided): If an ORIGINAL SOURCE
   TEXT is included in the prompt, the claim was extracted from that passage. Before
   evaluating evidence support, verify that the claim accurately represents the source:
   - Does the claim add outcome language for what the source frames as an intention?
   - Does the claim drop a negation, conditional, or qualification present in the source?
   - Does the claim introduce specifics (numbers, geographies, dates) not in the source?
   If extraction has changed the meaning, return PARTIALLY_SUPPORTED and add a scope_issue
   describing the specific divergence. Evaluate evidence support AFTER checking fidelity.

IMPORTANT: You are evaluating support, not plausibility. Do not return SUPPORTED simply
because the claim sounds reasonable or because a citation is present. The citation content
must actually establish the assertion.
"""


def _serialize_evidence_item(item: Dict[str, Any]) -> str:
    """Produce a readable one-line description of an evidence item for the reviewer prompt."""
    item_id = item.get("item_id") or item.get("limitation_id") or "?"
    excerpt = (
        item.get("excerpt")
        or item.get("original_statement")
        or item.get("content")
        or item.get("description")
        or ""
    )
    meta: List[str] = []
    for key in ("outcome_status", "execution_status"):
        val = item.get(key)
        if val:
            meta.append(f"{key}={val}")
    sc = item.get("semantic_classification") or {}
    for flag in ("is_product_availability", "is_prescription_ramp_verification", "is_revenue_attribution"):
        val = sc.get(flag)
        if val is not None:
            meta.append(f"{flag}={val}")
    period = item.get("announcement_period")
    if period:
        meta.append(f"period={period}")
    line = f"[{item_id}] {excerpt}"
    if meta:
        line += f"  ({', '.join(meta)})"
    return line


def review_claim(
    claim: Dict[str, Any],
    cited_evidence_items: List[Dict[str, Any]],
    model: str = "gpt-5-mini-2025-08-07",
    package_context_items: Optional[List[Dict[str, Any]]] = None,
    source_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ask an independent AI model whether a claim is genuinely supported by its citations.

    For undeclared claims (no evidence_refs), pass package_context_items as the full
    evidence context. The reviewer will assess whether ANY item in the context supports
    the claim.

    source_context: the original narrative text the claim was extracted from.
    When provided, the reviewer checks extraction fidelity before evaluating evidence
    support — preventing distorted extractions from producing false CONTRADICTED verdicts.

    Returns a dict with:
      verdict                  SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED | CONTRADICTED
      confidence               HIGH | MEDIUM | LOW
      reason                   explanation of the verdict
      scope_issues             list of scope mismatch descriptions
      qualifications_missing   list of omitted qualifications from the evidence

    On any failure, returns verdict=REVIEW_ERROR with a reason string.
    """
    claim_text = claim.get("claim_text", "")
    claim_type = claim.get("claim_type", "UNKNOWN")
    evidence_refs = claim.get("evidence_refs") or []

    # For undeclared claims, use full package context
    effective_items = cited_evidence_items or package_context_items or []
    evidence_lines = [_serialize_evidence_item(item) for item in effective_items]
    is_full_context = bool(package_context_items) and not cited_evidence_items

    is_evidence_gap = (claim_type == "EVIDENCE_GAP_STATEMENT")
    context_label = (
        "FULL PACKAGE EVIDENCE (undeclared claim — check all items):"
        if is_full_context
        else "SOURCE LIMITATION / ADVERSE EVIDENCE ITEMS (confirm stated absence):"
        if is_evidence_gap
        else "CITED EVIDENCE ITEMS:"
    )

    if is_evidence_gap:
        eval_instruction = (
            "Evaluate whether the stated ABSENCE is genuinely confirmed by the evidence "
            "items above. SUPPORTED means the items explicitly confirm this information "
            "is absent/unresolvable within the package. UNSUPPORTED means the package "
            "actually contains the described information. Respond with JSON."
        )
        system_prompt_to_use = _EVIDENCE_GAP_REVIEWER_SYSTEM_PROMPT
    else:
        eval_instruction = (
            "Evaluate whether this claim is genuinely supported by the evidence. "
            "Respond with JSON."
        )
        system_prompt_to_use = _REVIEWER_SYSTEM_PROMPT

    source_section = ""
    if source_context:
        source_section = (
            f"\nORIGINAL SOURCE TEXT (the narrative passage this claim was extracted from):\n"
            f"\"{source_context}\"\n"
            f"Check extraction fidelity: verify the claim accurately represents the source "
            f"before evaluating evidence support (see criterion 7).\n"
        )

    prompt = (
        f"CLAIM TO EVALUATE:\n"
        f"claim_text: {claim_text}\n"
        f"claim_type: {claim_type}\n"
        f"evidence_refs_cited: {evidence_refs if evidence_refs else '(none — undeclared claim)'}\n"
        + source_section
        + f"\n{context_label}\n"
        + ("\n".join(evidence_lines) if evidence_lines else "(none resolved)")
        + f"\n\n{eval_instruction}"
    )

    try:
        llm = get_llm(model=model)
        response = llm.generate(
            prompt=prompt,
            response_schema=_REVIEW_SCHEMA,
            max_tokens=2000,
            system_prompt=system_prompt_to_use,
        )
        raw = response.text if hasattr(response, "text") else response
        text = raw.strip() if isinstance(raw, str) else str(raw)
        result = json.loads(text)
        if result.get("verdict") not in VERDICTS:
            result["verdict"] = "UNSUPPORTED"
        # Normalize fields — model may return reason under different keys or in nested structures
        if not result.get("reason"):
            # flat string fields tried first
            fallback = (
                result.get("summary")
                or result.get("final_explanation")
                or result.get("notes")
                or result.get("explanation")
                or ""
            )
            # checks / checklist dict: {check_id: {passes/result, notes/explanation}}
            if not fallback:
                checks = result.get("checks") or result.get("checklist") or {}
                # prefer failing/partial items for a concise reason
                failing = [
                    v.get("notes") or v.get("explanation") or ""
                    for v in checks.values()
                    if isinstance(v, dict)
                    and v.get("passes") is False
                    or (isinstance(v, dict) and v.get("result") not in ("YES", True, None))
                ]
                failing = [f for f in failing if f]
                fallback = " | ".join(failing[:3]) if failing else (
                    " | ".join(
                        (v.get("notes") or v.get("explanation") or "")[:80]
                        for v in list(checks.values())[:2]
                        if isinstance(v, dict) and (v.get("notes") or v.get("explanation"))
                    )
                )
            # checked_criteria dict fallback (older schema variant)
            if not fallback:
                criteria = result.get("checked_criteria") or {}
                parts = [
                    f"{k}: {v.get('explanation', v.get('result',''))}"
                    for k, v in criteria.items()
                    if v.get("result") not in ("YES", None)
                ]
                fallback = " | ".join(parts) if parts else (
                    " | ".join(
                        f"{k}: {v.get('explanation','')[:80]}"
                        for k, v in list(criteria.items())[:2]
                        if v.get("explanation")
                    )
                )
            result["reason"] = fallback
        if "confidence" not in result:
            result["confidence"] = "MEDIUM"
        result.setdefault("scope_issues", [])
        result.setdefault("qualifications_missing", [])
        return {
            "verdict": result["verdict"],
            "confidence": result["confidence"],
            "reason": result["reason"],
            "scope_issues": result["scope_issues"],
            "qualifications_missing": result["qualifications_missing"],
        }
    except Exception as exc:
        return {
            "verdict": VERDICT_REVIEW_ERROR,
            "confidence": "LOW",
            "reason": f"AI review call failed: {type(exc).__name__}: {exc}",
            "scope_issues": [],
            "qualifications_missing": [],
        }


# ── Batch claim review ────────────────────────────────────────────────────────

_BATCH_REVIEW_SCHEMA = {
    "type": "object",
    "required": ["reviews"],
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["claim_id", "verdict", "confidence", "reason", "scope_issues", "qualifications_missing"],
                "properties": {
                    "claim_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED"]},
                    "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "reason": {"type": "string"},
                    "scope_issues": {"type": "array", "items": {"type": "string"}},
                    "qualifications_missing": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}

_BATCH_REVIEWER_SYSTEM_PROMPT = """\
You are an independent investment research validator. Review multiple investor claims independently.
Each claim must be evaluated on its own merits — your verdict for one claim must NOT influence others.
For any claim you cannot confidently evaluate, return verdict=UNSUPPORTED with a reason explaining why.
Apply the same evaluation criteria as for individual claims:
- Does the cited evidence establish the claim? (not merely cite it)
- Scope match: company, product, geography, period
- Outcome vs intention framing
- Causal limits: temporal proximity is not causation
- Omitted qualifications
Return ONLY valid JSON: {"reviews": [{claim_id, verdict, confidence, reason, scope_issues, qualifications_missing}, ...]}.
One entry per input claim, in the same order. Never omit a claim.
"""


def _safe_review_item(raw_item: dict) -> dict:
    """Normalise one item from a batch response; route malformed items to REVIEW_ERROR."""
    verdict = raw_item.get("verdict", "")
    if verdict not in VERDICTS:
        return {
            "verdict": VERDICT_REVIEW_ERROR,
            "confidence": "LOW",
            "reason": f"Malformed batch item: verdict={verdict!r}",
            "scope_issues": [],
            "qualifications_missing": [],
        }
    return {
        "verdict": verdict,
        "confidence": raw_item.get("confidence", "MEDIUM"),
        "reason": raw_item.get("reason", ""),
        "scope_issues": raw_item.get("scope_issues") or [],
        "qualifications_missing": raw_item.get("qualifications_missing") or [],
    }


def review_claims_batch(
    claims_with_evidence: list,
    model: str = "gpt-5-mini-2025-08-07",
    schema_version: str = "1",
) -> dict:
    """
    Review multiple claims in a single AI call.

    Args:
        claims_with_evidence: list of dicts, each containing:
            claim_id, claim_text, claim_type, evidence_refs,
            evidence_items (list of resolved evidence dicts)
        model: AI model to use
        schema_version: increment to invalidate cache on prompt/schema changes

    Returns:
        dict mapping claim_id → review result dict (same shape as review_claim()).
        Malformed or missing items are routed to VERDICT_REVIEW_ERROR.
        A claim absent from the batch response is also routed to VERDICT_REVIEW_ERROR.
    """
    if not claims_with_evidence:
        return {}

    # Build prompt
    items_text = []
    for c in claims_with_evidence:
        ev_lines = [_serialize_evidence_item(e) for e in (c.get("evidence_items") or [])]
        items_text.append(
            f"claim_id: {c['claim_id']}\n"
            f"claim_text: {c.get('claim_text', '')}\n"
            f"claim_type: {c.get('claim_type', 'UNKNOWN')}\n"
            f"evidence_refs: {c.get('evidence_refs') or []}\n"
            f"evidence:\n" + ("\n".join(f"  {l}" for l in ev_lines) if ev_lines else "  (none)")
        )
    prompt = (
        "Review each claim independently. Return one verdict per claim.\n\n"
        + "\n\n---\n\n".join(items_text)
        + "\n\nReturn JSON: {\"reviews\": [{claim_id, verdict, confidence, reason, scope_issues, qualifications_missing}, ...]}"
    )

    # Cache lookup
    fp = make_fingerprint(model, prompt, _BATCH_REVIEWER_SYSTEM_PROMPT, 0.0, schema_version)
    cached = cache_get(fp)
    if cached:
        raw_reviews = cached["result"]
    else:
        try:
            llm = get_llm(model=model)
            response = llm.generate(
                prompt=prompt,
                response_schema=_BATCH_REVIEW_SCHEMA,
                max_tokens=4000,
                system_prompt=_BATCH_REVIEWER_SYSTEM_PROMPT,
            )
            raw_text = response.text if hasattr(response, "text") else str(response)
            raw_reviews = json.loads(raw_text.strip()).get("reviews", [])
            cache_put(fp, raw_reviews, {
                "model": model,
                "stage": "claim_review_batch",
                "batch_size": len(claims_with_evidence),
                "schema_version": schema_version,
                "prompt_tokens": getattr(response, "prompt_tokens", None),
                "completion_tokens": getattr(response, "completion_tokens", None),
            })
        except Exception as exc:
            # Fail the whole batch safely — callers will see REVIEW_ERROR per claim
            error_result = {
                "verdict": VERDICT_REVIEW_ERROR,
                "confidence": "LOW",
                "reason": f"Batch AI call failed: {type(exc).__name__}: {exc}",
                "scope_issues": [],
                "qualifications_missing": [],
            }
            return {c["claim_id"]: error_result for c in claims_with_evidence}

    # Build claim_id → result dict; missing items → REVIEW_ERROR
    by_id = {}
    for item in (raw_reviews or []):
        cid = item.get("claim_id")
        if cid:
            by_id[cid] = _safe_review_item(item)

    results = {}
    for c in claims_with_evidence:
        cid = c["claim_id"]
        if cid in by_id:
            results[cid] = by_id[cid]
        else:
            results[cid] = {
                "verdict": VERDICT_REVIEW_ERROR,
                "confidence": "LOW",
                "reason": "Claim absent from batch response",
                "scope_issues": [],
                "qualifications_missing": [],
            }
    return results
