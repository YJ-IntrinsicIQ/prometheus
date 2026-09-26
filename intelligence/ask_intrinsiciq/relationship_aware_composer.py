"""
Mission 15: Relationship-Aware Answer Composition

Compose investor-facing answers that satisfy Level 3 claim and relationship
contracts before delivery.  The validator's ACCEPT / NEEDS_REVIEW / REJECT
verdicts determine what prose is ALLOWED, QUALIFIED, or SUPPRESSED.

Target flow:
  validated claims + relationships
  → build_composition_plan()
  → compose_answer_from_plan()
  → assess_composition_gate()
  → investor answer
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# ── Prose permission constants ─────────────────────────────────────────────────
ALLOWED = "ALLOWED"
QUALIFIED = "QUALIFIED"
SUPPRESSED = "SUPPRESSED"

# ── Confidence-appropriate wording by tier ────────────────────────────────────
_CONFIDENCE_WORDING: Dict[str, List[str]] = {
    "CONFIRMED": ["contributed to", "resulted in", "was driven by"],
    "SUPPORTED": [
        "evidence supports a connection to",
        "appears linked to",
        "is consistent with",
    ],
    "PLAUSIBLE": [
        "may have contributed to",
        "could be consistent with",
        "is a plausible interpretation of",
    ],
    "UNKNOWN": [
        "cannot be established from available evidence",
        "remains uncertain",
        "attribution is unclear",
    ],
}

# Replacement prose for suppressed (REJECT) relationships
_REJECT_PROSE = "The available evidence does not establish this relationship."

_COMPOSITION_SCHEMA = {
    "type": "object",
    "required": ["simple_answer", "why_it_matters", "investor_interpretation", "key_points"],
    "properties": {
        "simple_answer": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "investor_interpretation": {"type": "string"},
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 5,
        },
    },
    "additionalProperties": False,
}


# ── Core permission functions ──────────────────────────────────────────────────

def get_prose_permission(acceptance: str, causal_confidence: str = "") -> str:
    """Map validation acceptance → prose permission.

    ACCEPT                           → ALLOWED  (state at validated confidence)
    NEEDS_REVIEW + PLAUSIBLE/UNKNOWN → QUALIFIED (state as explicit uncertainty)
    NEEDS_REVIEW + other             → SUPPRESSED
    REJECT                           → SUPPRESSED
    """
    if acceptance == "REJECT":
        return SUPPRESSED
    if acceptance == "NEEDS_REVIEW":
        if causal_confidence in ("PLAUSIBLE", "UNKNOWN"):
            return QUALIFIED
        return SUPPRESSED
    if acceptance == "ACCEPT":
        return ALLOWED
    return QUALIFIED  # default for unhandled states


def get_confidence_wording(causal_confidence: str) -> List[str]:
    """Return allowed wording phrases for a given confidence tier."""
    return list(_CONFIDENCE_WORDING.get(causal_confidence, _CONFIDENCE_WORDING["UNKNOWN"]))


# ── Composition plan ───────────────────────────────────────────────────────────

def build_composition_plan(
    claim_results: List[Dict[str, Any]],
    rel_results: List[Dict[str, Any]],
    evidence_gaps: Optional[List[Any]] = None,
    uncertainty_items: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a structured composition plan with prose permissions.

    claim_results: list of dicts from validate_answer_complete
                   (must have 'final_acceptance_status', 'claim_id', 'claim_text')
    rel_results:   list of dicts from validate_relationship
                   (must have 'acceptance', 'causal_confidence', 'rel_id')
    """
    plan: Dict[str, Any] = {
        "allowed_claims": [],
        "qualified_claims": [],
        "suppressed_claims": [],
        "allowed_relationships": [],
        "qualified_relationships": [],
        "suppressed_relationships": [],
        "unknown_relationships": [],
        "evidence_gaps": evidence_gaps or [],
        "uncertainty_items": uncertainty_items or [],
    }

    for c in claim_results:
        acceptance = c.get("final_acceptance_status", "NEEDS_REVIEW")
        permission = get_prose_permission(acceptance)
        bucket = (
            "allowed_claims" if permission == ALLOWED
            else "qualified_claims" if permission == QUALIFIED
            else "suppressed_claims"
        )
        plan[bucket].append({**c, "prose_permission": permission})

    for r in rel_results:
        acceptance = r.get("acceptance", "NEEDS_REVIEW")
        conf = r.get("causal_confidence", "UNKNOWN")
        permission = get_prose_permission(acceptance, conf)
        entry = {
            **r,
            "prose_permission": permission,
            "allowed_wording": get_confidence_wording(conf),
            "suppression_replacement": _REJECT_PROSE if permission == SUPPRESSED else None,
        }
        if permission == SUPPRESSED:
            plan["suppressed_relationships"].append(entry)
        elif permission == QUALIFIED:
            plan["qualified_relationships"].append(entry)
        elif conf == "UNKNOWN":
            plan["unknown_relationships"].append(entry)
        else:
            plan["allowed_relationships"].append(entry)

    return plan


# ── Prompt construction ────────────────────────────────────────────────────────

def _build_composition_system_prompt(plan: Dict[str, Any], domain_question: str) -> str:
    """Build the AI system prompt enforcing prose permissions."""
    lines = [
        "You are an investment analyst generating a concise, evidence-backed investor answer.",
        f"Domain question: {domain_question}",
        "",
        "COMPOSITION CONTRACT — follow these rules exactly:",
        "",
    ]

    def _append_section(header: str, items: list, fmt_fn):
        if not items:
            return
        lines.append(header)
        for item in items:
            lines.append(fmt_fn(item))
        lines.append("")

    _append_section(
        "ALLOWED CLAIMS (state at validated strength):",
        plan["allowed_claims"],
        lambda c: (
            f"  [{c.get('claim_id','?')}] {c.get('claim_text','?')}"
        ),
    )
    _append_section(
        "QUALIFIED CLAIMS (state only as explicit uncertainty):",
        plan["qualified_claims"],
        lambda c: f"  [{c.get('claim_id','?')}] {c.get('claim_text','?')}",
    )
    _append_section(
        "SUPPRESSED CLAIMS — DO NOT assert these as facts:",
        plan["suppressed_claims"],
        lambda c: f"  [{c.get('claim_id','?')}] {c.get('claim_text','?')}",
    )
    _append_section(
        "ALLOWED RELATIONSHIPS (use confidence-appropriate wording):",
        plan["allowed_relationships"],
        lambda r: (
            f"  [{r.get('rel_id','?')}] {r.get('rel_type','?')} "
            f"(confidence: {r.get('causal_confidence','?')}) "
            f"— allowed wording: {', '.join(repr(w) for w in r.get('allowed_wording',[])[:2])}"
        ),
    )
    _append_section(
        "QUALIFIED RELATIONSHIPS (state as tentative interpretation only):",
        plan["qualified_relationships"],
        lambda r: (
            f"  [{r.get('rel_id','?')}] {r.get('rel_type','?')} "
            "— frame as 'may have' / 'possibly' / 'is a plausible interpretation'"
        ),
    )
    _append_section(
        "UNKNOWN RELATIONSHIPS (preserve uncertainty explicitly):",
        plan["unknown_relationships"],
        lambda r: (
            f"  [{r.get('rel_id','?')}] {r.get('rel_type','?')} "
            "— use 'cannot be established' / 'attribution remains uncertain'"
        ),
    )

    if plan["suppressed_relationships"]:
        lines.append(
            "SUPPRESSED RELATIONSHIPS — DO NOT assert these as causal connections:"
        )
        for r in plan["suppressed_relationships"]:
            lines.append(
                f"  [{r.get('rel_id','?')}] {r.get('rel_type','?')}: "
                f"source [{r.get('from_claim_id','?')}] → target [{r.get('to_claim_id','?')}]"
            )
            lines.append(
                f'    If this area must be mentioned, use ONLY: "{_REJECT_PROSE}"'
            )
        lines.append("")

    if plan["evidence_gaps"]:
        lines.append("EVIDENCE GAPS — acknowledge these explicitly:")
        for g in plan["evidence_gaps"][:4]:
            text = g.get("gap_description", str(g)) if isinstance(g, dict) else str(g)
            lines.append(f"  - {text}")
        lines.append("")

    lines.extend([
        "OUTPUT FORMAT: JSON with exactly these fields:",
        '  "simple_answer": string (1-2 sentences, direct answer)',
        '  "why_it_matters": string (economic significance, 2-3 sentences)',
        '  "investor_interpretation": string (qualified interpretation, 3-4 sentences)',
        '  "key_points": array of 3-4 concrete fact strings',
        "",
        "RULES:",
        "- Do NOT use internal terms: ACCEPT, NEEDS_REVIEW, REJECT, claim_id, rel_id",
        "- Do NOT assert any suppressed claim or relationship as fact",
        "- Do NOT use stronger causal language than the confidence tier allows",
        "- Preserve material uncertainty explicitly — do not silently omit it",
        "- Evidence-backed language throughout",
    ])
    return "\n".join(lines)


# ── AI composition ─────────────────────────────────────────────────────────────

def compose_answer_from_plan(
    plan: Dict[str, Any],
    domain_question: str,
    company_name: str,
    model: str = "gpt-4o-mini",
) -> Dict[str, Any]:
    """Generate investor answer respecting composition plan constraints.

    Returns a dict that looks like an integrated answer (simple_answer, why_it_matters,
    investor_interpretation, key_points) plus composition metadata.
    """
    from knowledge.ai import get_llm

    system_prompt = _build_composition_system_prompt(plan, domain_question)

    # Context: top allowed + qualified claims
    evidence_lines = []
    for c in (plan["allowed_claims"] + plan["qualified_claims"])[:10]:
        evs = ", ".join(c.get("evidence_refs", [])[:3])
        evidence_lines.append(
            f"[{c.get('claim_id','?')}] {c.get('claim_text','?')}"
            + (f" (evidence: {evs})" if evs else "")
        )

    user_content = (
        f"Company: {company_name}\n"
        f"Question: {domain_question}\n\n"
        "Validated claims:\n"
        + "\n".join(evidence_lines)
        + "\n\nGenerate the investor answer as a JSON object following the composition contract."
    )

    try:
        llm = get_llm(model=model)
        response = llm.generate(
            prompt=user_content,
            response_schema=_COMPOSITION_SCHEMA,
            max_tokens=2000,
            system_prompt=system_prompt,
        )
        raw = response.text if hasattr(response, "text") else response
        text = raw.strip() if isinstance(raw, str) else str(raw)
        answer = json.loads(text)
    except Exception as e:
        answer = {
            "simple_answer": f"[COMPOSITION_ERROR: {e}]",
            "why_it_matters": "",
            "investor_interpretation": "",
            "key_points": [],
            "_composition_error": str(e),
        }

    # Attach validated structure (claims and relationships as declared in plan)
    answer["claims"] = [
        _strip_plan_meta(c)
        for c in plan["allowed_claims"] + plan["qualified_claims"]
    ]
    answer["relationships"] = [
        _strip_plan_meta(r)
        for r in (
            plan["allowed_relationships"]
            + plan["qualified_relationships"]
            + plan["unknown_relationships"]
            + plan["suppressed_relationships"]
        )
    ]
    answer["evidence_gaps"] = plan["evidence_gaps"]
    answer["_composition_plan_summary"] = {
        "allowed_claims": len(plan["allowed_claims"]),
        "qualified_claims": len(plan["qualified_claims"]),
        "suppressed_claims": len(plan["suppressed_claims"]),
        "allowed_rels": len(plan["allowed_relationships"]),
        "qualified_rels": len(plan["qualified_relationships"]),
        "suppressed_rels": len(plan["suppressed_relationships"]),
        "unknown_rels": len(plan["unknown_relationships"]),
    }

    return answer


def _strip_plan_meta(item: Dict[str, Any]) -> Dict[str, Any]:
    """Remove internal plan keys before publishing to answer structure."""
    skip = {"prose_permission", "allowed_wording", "suppression_replacement"}
    return {k: v for k, v in item.items() if k not in skip}


# ── Gate ───────────────────────────────────────────────────────────────────────

def assess_composition_gate(
    answer: Dict[str, Any],
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Quick deterministic gate — checks relationship constraints.

    Full gate (claim extraction, undeclared check) requires
    validate_answer_complete from claim_validator.py — done in runner.
    """
    suppressed_rel_ids = [r.get("rel_id", "") for r in plan.get("suppressed_relationships", [])]

    # Collect all prose
    prose_fields = [
        answer.get("simple_answer", ""),
        answer.get("why_it_matters", ""),
        answer.get("investor_interpretation", ""),
    ]
    for kp in answer.get("key_points", []):
        if isinstance(kp, str):
            prose_fields.append(kp)
    full_prose = " ".join(prose_fields).lower()

    # A rel_id in prose is a red flag (the AI should never mention them)
    suppressed_leaked = [rid for rid in suppressed_rel_ids if rid and rid.lower() in full_prose]

    # Check for composition errors
    has_error = bool(answer.get("_composition_error"))

    gate_issues = []
    if suppressed_leaked:
        gate_issues.append(f"suppressed_rel_ids_in_prose:{suppressed_leaked}")
    if has_error:
        gate_issues.append("composition_error")

    gate = "PASS" if not gate_issues else "FAIL_RELATIONSHIP_VALIDATION"

    return {
        "gate": gate,
        "gate_issues": gate_issues,
        "suppressed_rel_ids_found_in_prose": suppressed_leaked,
        "has_suppressed_rels": len(plan.get("suppressed_relationships", [])) > 0,
        "plan_summary": answer.get("_composition_plan_summary", {}),
        "note": (
            "Full gate requires validate_answer_complete() + extract_hidden_relationships()."
        ),
    }
