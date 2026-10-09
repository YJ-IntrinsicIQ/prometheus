"""
Evidence-grounded AI reasoning for investor answers.

Accepts a Mission-1-style evidence package, constructs a constrained prompt,
calls the configured AI provider, and returns a structured candidate answer
with per-claim citations for downstream validation.

This module is for PRECOMPUTED answer generation only.
It does NOT serve as a runtime inference path for individual investor queries.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from knowledge.ai import get_llm, AIProviderError, AIResponseError


# ── Output schema the AI must produce ─────────────────────────────────────────

ANSWER_SCHEMA = {
    "type": "object",
    "required": [
        "simple_answer",
        "why_it_matters",
        "key_points",
        "economic_reasoning",
        "claims",
        "evidence_gaps",
        "investor_action_items",
    ],
    "properties": {
        "simple_answer": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "economic_reasoning": {
            "type": "object",
            "properties": {
                "management_intentions": {"type": "string"},
                "economic_purpose": {"type": "string"},
                "observable_execution": {"type": "string"},
                "established_outcomes": {"type": "string"},
                "remaining_uncertainty": {"type": "string"},
            },
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["claim_id", "claim_text", "evidence_refs", "claim_type"],
                "properties": {
                    "claim_id": {"type": "string"},
                    "claim_text": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "claim_type": {"type": "string"},
                },
            },
        },
        "evidence_gaps": {"type": "array", "items": {"type": "string"}},
        "investor_action_items": {"type": "array", "items": {"type": "string"}},
    },
}


_SYSTEM_PROMPT = """\
You are a specialist investment research analyst. Your task is to explain what \
a pharmaceutical company's management has committed to achieving, using only \
the evidence provided in the user message.

ABSOLUTE RULES — NEVER VIOLATE:
1. UNVERIFIED means "no evidence is available in our sources" — it NEVER means the commitment was missed or failed.
2. A product launch citation establishes market AVAILABILITY only. It does NOT verify prescription growth, revenue uplift, or commercial success.
3. Do not create causal links from temporal proximity: "X happened after Y" does NOT mean Y caused X.
4. Do not claim financial attribution (revenue, profit) for any commitment unless the evidence explicitly provides financial_link_status=DIRECTLY_ATTRIBUTABLE.
5. Do not merge verifiable commitments and strategic directions into a single fulfilment percentage.
6. Do not invent mechanisms, numbers, or company facts not present in the evidence package.
7. Do not assign value rankings to product categories (e.g. "higher-value", "higher-margin", "premium", "higher-priced") unless the evidence package explicitly provides this comparative data in a business_model_context item.
8. Every material factual claim in your answer MUST be traceable to an evidence_ref from the package. Do NOT include elements in a claim that do not appear in the cited evidence item — if the source statement doesn't mention "maintaining generics" or "efficiency measures", the claim must not assert them.
9. For items with execution_status=CLAIM_ONLY or accountability_ontology=STRATEGIC_INTENT, use past-tense framing ("management stated", "management expressed this direction in FY20") — NOT present-ongoing tense ("continues to prioritise"). A single historical statement does not establish ongoing priority.
10. Every sentence in `why_it_matters` that connects a management commitment to business model context MUST be declared in claims[] as claim_type=ECONOMIC_INTERPRETATION with evidence_refs citing both the relevant commitment items (PT-*) and the business model context items (BC-CM-*). State only what the cited items establish — do not infer value hierarchies.
11. Every sentence in `economic_reasoning.remaining_uncertainty` that asserts specific information is absent from the package MUST be declared in claims[] as claim_type=UNCERTAINTY with evidence_refs citing the source_limitation items (SL-*) and adverse_evidence items (AE-*) that confirm the absence.
12. Each item in `evidence_gaps` that names a specific missing information type MUST correspond to a claim in claims[] of claim_type=EVIDENCE_GAP_STATEMENT with evidence_refs citing the SL-* limitation item(s) that confirm the absence. If no SL-* item exists for a gap, cite the most closely related adverse_evidence item (AE-*).
13. Claim_text must NEVER include materiality qualifiers from the evidence package metadata (e.g. "high-materiality strategic direction", "medium-materiality strategic direction"). These are package-level classification labels, NOT part of the management's original statement. State only what the evidence item's original_statement field actually establishes.
14. For ECONOMIC_INTERPRETATION claims: only assert a connection that the cited business model context item LITERALLY establishes. BC-CM-001 establishes the revenue model includes specialty pharmaceutical sales — asserting that specialty market commitments are "consistent with" or "within" this model is supportable. BC-CM-002 lists specific value-creation mechanisms (R&D-led launches, M&A, manufacturing investments) — only cite BC-CM-002 for a commitment if the commitment itself explicitly describes one of those mechanisms. A prescription ramp-up or market-targeting commitment does NOT involve R&D-led launches or M&A and must not cite BC-CM-002 as support.
15. Do NOT describe commitments in the verifiable_commitments section as "verifiable commitments" in simple_answer, key_points, or narrative fields. These commitments have outcome_status=UNVERIFIED and execution_status=CLAIM_ONLY. Use "stated commitments", "tracked commitments", or "management commitments" instead. The term "verifiable" is a package classification label, not a description of their verification status.

OUTPUT FORMAT: Respond with a single valid JSON object matching this schema exactly. No markdown, no prose outside the JSON.

The JSON must contain:
- simple_answer: 2-3 sentences. Plain English. No internal identifiers.
- why_it_matters: 2-3 sentences explaining the commercial/economic significance using only the provided business model context. Every factual assertion here must be declared in claims[].
- key_points: Array of 3-5 investor-facing bullet points. Lead with the verifiable commitments. Follow with the most material strategic directions.
- economic_reasoning: Object with 5 fields — management_intentions, economic_purpose, observable_execution, established_outcomes, remaining_uncertainty. If a stage has no supporting evidence, say so plainly. Do NOT invent evidence to fill a gap. Cite evidence item IDs where relevant.
- claims: Array of objects, one per distinct factual claim. Each must have: claim_id (C001, C002, ...), claim_text (the specific claim), evidence_refs (array of evidence item_ids from the package), claim_type (one of: COMMITMENT_STATEMENT, STRATEGIC_DIRECTION, PRODUCT_AVAILABILITY, EXECUTION_GAP, ECONOMIC_INTERPRETATION, BUSINESS_CONTEXT, UNCERTAINTY, EVIDENCE_GAP_STATEMENT).
- evidence_gaps: Array of strings naming what is missing that would resolve the key uncertainties.
- investor_action_items: Array of 2-4 specific, actionable questions an investor should seek to answer.
"""


def _build_evidence_prompt(package: Dict[str, Any], question: str = "What has management promised?") -> str:
    """
    Serialize the evidence package into a compact, structured prompt.
    Only includes fields the AI is permitted to reason about.
    """
    lines: List[str] = []
    lines.append(f"QUESTION: {question}")
    lines.append(f"COMPANY: {package.get('company_slug', 'unknown')}")
    lines.append("")

    # Global constraints — inlined so the model cannot miss them
    constraints = package.get("package_constraints", {})
    global_rules = constraints.get("ai_reasoning_global_constraints", [])
    if global_rules:
        lines.append("BINDING EVIDENCE CONSTRAINTS:")
        for rule in global_rules:
            lines.append(f"  • {rule}")
        silence_note = constraints.get("silence_is_not_failure", "")
        if silence_note:
            lines.append(f"  • {silence_note}")
        lines.append("")

    sections = package.get("sections", {})

    # Verifiable commitments — highest priority
    vc = sections.get("verifiable_commitments", [])
    if vc:
        lines.append("VERIFIABLE COMMITMENTS (these are specific, bounded management statements subject to accountability):")
        for item in vc:
            lines.append(f"  item_id: {item['item_id']}")
            lines.append(f"  statement: \"{item.get('original_statement', '')}\"")
            lines.append(f"  period: {item.get('announcement_period', 'unknown')}")
            lines.append(f"  execution_status: {item.get('execution_status', 'unknown')}")
            lines.append(f"  outcome_status: {item.get('outcome_status', 'unknown')}")
            lines.append(f"  later_evidence: {item.get('later_evidence', [])}")
            guidance = item.get("ai_reasoning_guidance", {})
            may = guidance.get("may_assert", [])
            must_not = guidance.get("must_not_assert", [])
            if may:
                lines.append(f"  MAY ASSERT: {' | '.join(may)}")
            if must_not:
                lines.append(f"  MUST NOT ASSERT: {' | '.join(must_not)}")
            lines.append("")

    # Strategic intents — directional, not verifiable
    si = sections.get("strategic_intents", [])
    if si:
        lines.append("STRATEGIC DIRECTIONS (not individually verifiable; excluded from accountability denominator):")
        for item in si[:4]:
            stmt = (item.get("original_statement") or "")[:200]
            lines.append(f"  item_id: {item['item_id']} | period: {item.get('announcement_period', '?')} | materiality: {item.get('materiality', '?')}")
            lines.append(f"  \"{stmt}{'...' if len(item.get('original_statement',''))>200 else ''}\"")
        lines.append("")

    # Observable execution evidence
    oe = sections.get("observable_execution_evidence", [])
    if oe:
        lines.append("OBSERVABLE EXECUTION EVIDENCE (from company research synthesis — NOT verbatim management disclosure):")
        for item in oe:
            sc = item.get("semantic_classification", {})
            lines.append(f"  item_id: {item['item_id']}")
            lines.append(f"  excerpt: \"{item.get('excerpt', '')}\"")
            lines.append(f"  is_product_availability={sc.get('is_product_availability')} | is_prescription_ramp_verification={sc.get('is_prescription_ramp_verification')} | is_revenue_attribution={sc.get('is_revenue_attribution')}")
            may = item.get("ai_reasoning_guidance", {}).get("may_assert", [])
            must_not = item.get("ai_reasoning_guidance", {}).get("must_not_assert", [])
            if may:
                lines.append(f"  MAY ASSERT: {' | '.join(may)}")
            if must_not:
                lines.append(f"  MUST NOT ASSERT: {' | '.join(must_not)}")
            lines.append("")

    # Business model context
    bmc = sections.get("business_model_context", [])
    if bmc:
        lines.append("BUSINESS MODEL CONTEXT (use this to explain commercial significance — no causal attribution):")
        for item in bmc:
            lines.append(f"  item_id: {item['item_id']} | field: {item.get('field', '?')}")
            lines.append(f"  \"{item.get('content', '')}\"")
        lines.append("")

    # Adverse evidence
    ae = sections.get("adverse_evidence", [])
    if ae:
        lines.append("ADVERSE EVIDENCE (must be preserved in the answer; do not soften or omit):")
        for item in ae:
            lines.append(f"  item_id: {item['item_id']}: {item.get('description', '')}")
        lines.append("")

    # Source limitations
    sl = sections.get("source_limitations", [])
    if sl:
        lines.append("SOURCE LIMITATIONS (inform what cannot be claimed):")
        for item in sl:
            lines.append(f"  {item['limitation_id']} [{item['type']}]: {item.get('description', '')}")
        lines.append("")

    # Accountability metrics
    am = constraints.get("accountability_metrics", {})
    if am:
        lines.append(f"ACCOUNTABILITY METRICS: {am.get('material_verifiable_commitments',0)} verifiable commitments tracked, {am.get('verified_commitments',0)} verified, {am.get('unresolved_verifiable_commitments',0)} unresolved. {am.get('strategic_intents',0)} strategic directions, {am.get('aspirations',0)} aspirations.")
        lines.append("")

    lines.append("Now generate the investor answer JSON following the schema.")
    return "\n".join(lines)


def _parse_ai_response(text: str) -> Dict[str, Any]:
    """Extract and parse JSON from AI response text."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```\s*$", "", text)
        text = text.strip()
    return json.loads(text)


def _fingerprint(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def generate_ai_answer(
    evidence_package: Dict[str, Any],
    question: str = "What has management promised?",
    model: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Generate a structured AI answer from the evidence package.

    Returns (answer_dict, metadata_dict).
    answer_dict contains the AI-generated structured answer.
    metadata_dict contains model, latency, token counts, and the raw response.

    Raises AIProviderError / AIResponseError on failure.
    """
    llm = get_llm(model=model)
    prompt = _build_evidence_prompt(evidence_package, question)

    response = llm.generate(
        prompt=prompt,
        response_schema=ANSWER_SCHEMA,
        temperature=0.0,
        max_tokens=8000,
        system_prompt=_SYSTEM_PROMPT,
    )

    answer = _parse_ai_response(response.text)

    metadata: Dict[str, Any] = {
        "model": response.model,
        "provider": response.provider,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "total_tokens": response.total_tokens,
        "latency_ms": round(response.latency_ms, 1) if response.latency_ms else None,
        "evidence_package_fingerprint": evidence_package.get("package_fingerprint"),
        "answer_fingerprint": _fingerprint(answer),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw_response_length": len(response.text),
    }

    return answer, metadata
