"""
Independent narrative claim extraction for Mission 5.

Extracts material factual claims from all text fields in an AI-generated
investor answer WITHOUT relying on the generator's declared claims[] array.

This extraction pass is used to:
  1. Discover claims the generator made but did not formally declare.
  2. Compare declared vs extracted coverage.
  3. Ensure every material narrative assertion is either validated or flagged.

The extractor is intentionally separate from both the answer generator and
the claim reviewer — it is a third, independent model invocation.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from knowledge.ai import get_llm, AIProviderError, AIResponseError

_EXTRACTION_SCHEMA = {
    "type": "object",
    "required": ["extracted_claims", "coverage_assessment"],
    "properties": {
        "extracted_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "extraction_id",
                    "claim_text",
                    "claim_type",
                    "source_field",
                    "materiality",
                    "declared_match",
                    "suggested_refs",
                ],
                "properties": {
                    "extraction_id": {"type": "string"},
                    "claim_text": {"type": "string"},
                    "claim_type": {
                        "type": "string",
                        "enum": [
                            "COMMITMENT_STATEMENT",
                            "STRATEGIC_DIRECTION",
                            "PRODUCT_AVAILABILITY",
                            "ECONOMIC_INTERPRETATION",
                            "EXECUTION_GAP",
                            "UNCERTAINTY",
                            "BUSINESS_CONTEXT",
                            "EVIDENCE_GAP_STATEMENT",
                        ],
                    },
                    "source_field": {"type": "string"},
                    "materiality": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "declared_match": {"type": ["string", "null"]},
                    "suggested_refs": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "coverage_assessment": {
            "type": "string",
            "enum": ["COMPLETE", "PARTIAL", "INCOMPLETE"],
        },
        "coverage_notes": {"type": "string"},
    },
}

_EXTRACTOR_SYSTEM_PROMPT = """\
You are an independent investment research auditor. Your task is to extract every
material factual claim from an investor answer, then check whether each claim was
formally declared in the answer's claims[] array.

WHAT COUNTS AS A MATERIAL CLAIM:
A material claim is any sentence or clause that asserts a specific verifiable fact
about the company, its management commitments, its products, its commercial operations,
or economic outcomes. Examples:
- "Management committed to X" → COMMITMENT_STATEMENT
- "ILUMYA was launched in Japan" → PRODUCT_AVAILABILITY
- "Geographic expansion aligns with the stated business model" → ECONOMIC_INTERPRETATION
- "All commitments remain UNVERIFIED" → UNCERTAINTY
- "There is no prescription volume data for ILUMYA in Japan" → EVIDENCE_GAP_STATEMENT
- "No progression records link commitment PT-0004 to tracked execution" → EVIDENCE_GAP_STATEMENT
- "Revenue is generated via specialty pharmaceutical sales" → BUSINESS_CONTEXT

EVIDENCE_GAP_STATEMENT claims (from evidence_gaps field):
Claims from [evidence_gaps] assert that specific information is ABSENT from the
available evidence package. Extract them with claim_type=EVIDENCE_GAP_STATEMENT.
These are NOT positive factual claims about outcomes — they state that the package
lacks certain data. The reviewer will check whether this stated absence is genuinely
confirmed by the package's scope and source limitation items.
Distinguish:
- "The package contains no prescription volume data for ILUMYA" → EVIDENCE_GAP_STATEMENT (verifiable from package)
- "Sun Pharma has never disclosed prescription data" → this REQUIRES external knowledge, flag materiality=HIGH if present

WHAT DOES NOT COUNT:
- Hedging language without a factual assertion ("investors may want to...")
- Meta-commentary about the answer itself
- Questions in investor_action_items
- Generic industry statements not attributed to the company

FOR EACH EXTRACTED CLAIM:
- Set source_field to the EXACT field label shown in brackets above where you found the
  claim (e.g., "economic_reasoning.remaining_uncertainty", "why_it_matters",
  "simple_answer", "key_points[2]", "evidence_gaps[0]"). This is REQUIRED — never
  leave source_field empty or null. The field label is the text inside [...] that
  precedes the passage you extracted from.
- Set declared_match to the claim_id from the provided declared_claims list that best
  matches this claim (must be a close semantic match — NOT just same topic), OR null if
  no declared claim covers this assertion.
- Set suggested_refs to any evidence IDs from the provided available_evidence_ids list
  that could plausibly support this claim.
- Set materiality: HIGH if the claim is specific and verifiable; MEDIUM if general but
  company-specific; LOW if generic/background.

COVERAGE ASSESSMENT:
- COMPLETE: every material HIGH and MEDIUM claim is covered by a declared claim
- PARTIAL: some HIGH or MEDIUM claims are undeclared
- INCOMPLETE: the extractor cannot confidently assess coverage

IMPORTANT: Extract claims as they are stated. Do not rephrase or add qualifications.
Preserve the original wording. Including conditional language ("if executed"),
uncertainty markers ("remain unverified"), and intention framing ("management stated
it would") — do not convert intentions into outcomes.
"""


def _build_extraction_prompt(
    ai_answer: Dict[str, Any],
    declared_claims: List[Dict[str, Any]],
    available_evidence_ids: List[str],
) -> str:
    lines = ["INVESTOR ANSWER TO AUDIT:\n"]

    sa = ai_answer.get("simple_answer", "")
    if sa:
        lines.append(f"[simple_answer]\n{sa}\n")

    wim = ai_answer.get("why_it_matters", "")
    if wim:
        lines.append(f"[why_it_matters]\n{wim}\n")

    kps = ai_answer.get("key_points") or []
    if kps:
        lines.append("[key_points]")
        for i, kp in enumerate(kps):
            lines.append(f"  [{i}] {kp}")
        lines.append("")

    er = ai_answer.get("economic_reasoning") or {}
    for field in (
        "management_intentions",
        "economic_purpose",
        "observable_execution",
        "established_outcomes",
        "remaining_uncertainty",
    ):
        if er.get(field):
            lines.append(f"[economic_reasoning.{field}]\n{er[field]}\n")

    eg = ai_answer.get("evidence_gaps") or []
    if eg:
        lines.append(
            "[evidence_gaps] (absence-assertions about what is MISSING from the package — "
            "extract as EVIDENCE_GAP_STATEMENT type):"
        )
        for i, gap in enumerate(eg):
            lines.append(f"  [{i}] {gap}")
        lines.append("")

    lines.append("---\nDECLARED CLAIMS (already formally declared by the generator):")
    for c in declared_claims:
        lines.append(
            f"  {c.get('claim_id', '?')}: [{c.get('claim_type', '?')}] "
            f"{c.get('claim_text', '')[:120]}"
        )

    lines.append(
        f"\nAVAILABLE EVIDENCE IDs (you may reference these in suggested_refs):\n"
        f"  {available_evidence_ids}"
    )

    lines.append(
        "\nNow extract ALL material factual claims from the narrative fields above. "
        "You MUST return each claim as an item in extracted_claims[], "
        "even if it is already covered by a declared claim — set declared_match to the "
        "corresponding claim_id in that case. "
        "Use null for declared_match ONLY when no declared claim covers the assertion. "
        "Returning an empty extracted_claims[] is wrong unless the narrative has no "
        "material factual content at all. "
        "Respond with JSON."
    )
    return "\n".join(lines)


def extract_claims(
    ai_answer: Dict[str, Any],
    evidence_package: Dict[str, Any],
    model: str = "gpt-5-mini-2025-08-07",
) -> Dict[str, Any]:
    """
    Extract all material factual claims from narrative fields in an AI answer.

    Returns:
      extracted_claims      list of {extraction_id, claim_text, claim_type, source_field,
                            materiality, declared_match, suggested_refs}
      undeclared_claims     subset with declared_match=null and materiality HIGH/MEDIUM
      coverage_assessment   COMPLETE | PARTIAL | INCOMPLETE
      coverage_notes        free-text explanation
      extraction_error      present only on failure
    """
    declared_claims = ai_answer.get("claims") or []

    # Collect all evidence IDs
    available_ids: List[str] = []
    for section_items in evidence_package.get("sections", {}).values():
        if isinstance(section_items, list):
            for item in section_items:
                if isinstance(item, dict):
                    key = item.get("item_id") or item.get("limitation_id")
                    if key:
                        available_ids.append(key)

    prompt = _build_extraction_prompt(ai_answer, declared_claims, available_ids)

    try:
        llm = get_llm(model=model)
        response = llm.generate(
            prompt=prompt,
            response_schema=_EXTRACTION_SCHEMA,
            max_tokens=12000,  # reasoning model needs large budget for thinking + structured output
            system_prompt=_EXTRACTOR_SYSTEM_PROMPT,
        )
        raw = response.text if hasattr(response, "text") else str(response)
        result = json.loads(raw.strip())

        extracted = result.get("extracted_claims") or []
        # Normalize
        for i, ec in enumerate(extracted):
            ec.setdefault("extraction_id", f"EX-{i+1:03d}")
            ec.setdefault("materiality", "MEDIUM")
            ec.setdefault("declared_match", None)
            ec.setdefault("suggested_refs", [])

        undeclared = [
            ec for ec in extracted
            if ec.get("declared_match") is None
            and ec.get("materiality") in ("HIGH", "MEDIUM")
        ]

        return {
            "extracted_claims": extracted,
            "undeclared_claims": undeclared,
            "undeclared_count": len(undeclared),
            "total_extracted": len(extracted),
            "coverage_assessment": result.get("coverage_assessment", "INCOMPLETE"),
            "coverage_notes": result.get("coverage_notes", ""),
        }

    except Exception as exc:
        return {
            "extracted_claims": [],
            "undeclared_claims": [],
            "undeclared_count": 0,
            "total_extracted": 0,
            "coverage_assessment": "INCOMPLETE",
            "coverage_notes": "",
            "extraction_error": f"{type(exc).__name__}: {exc}",
        }
