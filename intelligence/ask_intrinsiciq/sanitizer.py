from __future__ import annotations

import re
from typing import Any


FORBIDDEN_PUBLIC_TERMS = {
    "company memory",
    "company-memory",
    "available evidence summary",
    "saved analyst outputs",
    "pcim",
    "cim",
    "canonical",
    "artifact",
    "artifacts",
    ".json",
    "json",
    "source_artifact",
    "source_item_id",
    "evidence_id",
    "evidence_ids",
    "evidence_map",
    "source lineage",
    "pipeline",
    "uncertainty_missing_data",
    "schema",
    "validation",
    "diagnostics",
    "prompt",
    "llm",
    "raw artifact",
    "source chunk",
    "input pack",
    "doctrine_id",
    "normalized_ids",
    "original_ids",
    "action_started",
    "action_completed",
    "action_abandoned",
    "claim_made",
    "completion_claimed",
    "outcome_verified",
    "insufficient_evidence",
    "evidence_quality",
    "financial_strength_inputs",
    "management_execution_inputs",
    "financial_quality_summary",
    "capital_allocation_roi_ledger",
    "gold promise tracker",
    "gold credibility synthesis",
    "gold credibility",
    "gold promise",
    "canonical assessments",
    "canonical phase",
    "causal-attribution ledger",
    "allocation skill requires",
    "primary assessments",
    "conclusive capital-weighted ranking is not permitted",
}

PUBLIC_REWRITES = {
    "company memory": "source set",
    "company-memory": "source set",
    "available evidence summary": "evidence summary",
    "saved analyst outputs": "related analyst output",
    "pcim": "company research summary",
    "cim": "company research summary",
    "canonical": "primary",
    "artifact": "source record",
    "artifacts": "source records",
    ".json": "",
    "json": "saved file",
    "source_artifact": "source record",
    "source_item_id": "source reference",
    "evidence_id": "evidence reference",
    "evidence_ids": "evidence references",
    "evidence_map": "evidence summary",
    "source lineage": "source trail",
    "pipeline": "workflow",
    "uncertainty_missing_data": "evidence gap summary",
    "schema": "contract",
    "validation": "review",
    "diagnostics": "system checks",
    "prompt": "instruction",
    "llm": "model",
    "raw artifact": "raw source record",
    "source chunk": "source excerpt",
    "input pack": "source package",
    "doctrine_id": "lens reference",
    "normalized_ids": "standardized references",
    "original_ids": "original references",
    "directly_attributable": "confirmed by the transaction itself",
    "associated_not_attributable": "associated with subsequent financial changes",
    "no_outcome_evidence": "no disclosed outcome yet",
    "attribution_unknown": "outcome not yet determinable",
    "partially_proven": "partially demonstrated",
    "unproven": "not yet demonstrated",
    "proven": "demonstrated",
    "share_count_reduction": "share count reduction",
    "capital_allocation_outcomes": "capital allocation outcomes",
    "supplied sections": "the available sections",
    "ownership evidence summary": "ownership evidence",
    "capital-allocation and governance signals weak": "capital allocation discipline looks weak",
    "business model: product/system oem + systems integration for defence & space": "defence and space systems integration",
    "product/system oem + systems integration for defence & space, with explicit verticalisation and indigenous-manufacturing objectives": "defence and space systems integration with vertical manufacturing goals",
    "related analyst output": "related analysis",
    "this remains a central caution in the related analyst output": "this remains a central caution",
    "commitments and projects with announcements but limited or unverifiable follow-through; capacity under construction without clear evidence of economic use": "announcements outpace clear follow-through; capacity remains under construction",
    "returns on capital show positive roe and roa in the latest year but are described as weak or deteriorating in the evidence summary": "returns on capital remain mixed",
    "action_started": "underway",
    "action_completed": "completed",
    "action_abandoned": "discontinued",
    "claim_made": "announced",
    "completion_claimed": "reported as complete",
    "outcome_verified": "outcome confirmed",
    "insufficient_evidence": "evidence not yet sufficient",
    "evidence_quality": "evidence quality",
    "event(s)": "events",
    "risk(s)": "risks",
    "area(s)": "areas",
    "disagreement(s)": "disagreements",
    "gold promise tracker": "management commitment tracking",
    "gold credibility synthesis": "management credibility analysis",
    "gold credibility": "management credibility analysis",
    "gold promise": "management commitment tracking",
    "canonical assessments": "available assessments",
    "canonical phase": "tracking phase",
    "causal-attribution ledger": "attribution records",
    "primary assessments": "available assessments",
    "conclusive capital-weighted ranking is not permitted": "a capital-weighted conclusion is not yet possible",
    "allocation skill requires attributable causal evidence": "attributing skill requires causal evidence",
}

PUBLIC_EMPTY_FILLERS = {
    "this remains a central caution",
}

PUBLIC_MALFORMED_PATTERNS = (
    re.compile(r"\b(?:in|on|for|of|at|to|with|from|by)\s*;"),
    re.compile(r"\bdescribed as [^.;]{0,80}\b(?:in|on|for|of|at|to|with|from|by)\s*;"),
)


def sanitize_public_text(value: str) -> str:
    text = " ".join(str(value or "").strip().split())
    lowered = text.lower()
    for term, replacement in sorted(PUBLIC_REWRITES.items(), key=lambda item: len(item[0]), reverse=True):
        if term in lowered:
            text = _replace_case_insensitive(text, term, replacement)
            lowered = text.lower()
    text = " ".join(text.split()).strip()
    if not text:
        return ""
    if " ".join(text.lower().split()).strip(" .,!?:;") in PUBLIC_EMPTY_FILLERS:
        return ""
    if _is_obviously_truncated_text(text):
        return ""
    if _contains_malformed_public_clause(text):
        return ""
    if contains_forbidden_public_term(text):
        return ""
    return text


def contains_forbidden_public_term(value: str) -> bool:
    lowered = str(value or "").lower()
    return any(term in lowered for term in FORBIDDEN_PUBLIC_TERMS)


def sanitize_public_payload(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_public_text(value)
    if isinstance(value, list):
        return [sanitize_public_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_public_payload(item) for key, item in value.items()}
    return value


def _replace_case_insensitive(text: str, needle: str, replacement: str) -> str:
    lower_text = text.lower()
    lower_needle = needle.lower()
    pieces = []
    start = 0
    while True:
        index = lower_text.find(lower_needle, start)
        if index == -1:
            pieces.append(text[start:])
            break
        pieces.append(text[start:index])
        pieces.append(replacement)
        start = index + len(needle)
    return "".join(pieces)


def _contains_malformed_public_clause(text: str) -> bool:
    normalized = " ".join(str(text or "").strip().split())
    return any(pattern.search(normalized) for pattern in PUBLIC_MALFORMED_PATTERNS)


def _is_obviously_truncated_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.endswith(("...", "…", "'", "’")):
        return True
    if stripped.endswith(("(", "[", "{", "/", "-", "–", "—", ":", ";")):
        return True
    if "..." in stripped or "…" in stripped:
        return True
    words = stripped.split()
    if len(words) >= 12 and not stripped.endswith((".", "?", "!")):
        return True
    return False
