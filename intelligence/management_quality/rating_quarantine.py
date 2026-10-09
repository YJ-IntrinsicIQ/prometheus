"""
Management Rating Language Quarantine — ENG-MISSION50

Invariant: RATING_LANGUAGE_CANNOT_ENTER_GENERATION_INPUT_OR_INVESTOR_ARTIFACT

Detects management-quality rating language that must not appear in:
  - Generation inputs (LLM prompts derived from mq_summary)
  - Investor-facing answer fields

Sources of unsafe rating language (as of M50):
  - mq_summary.interpretation.conclusion: "Management quality is weak and the trajectory is stable."
  - mq_summary.interpretation.why_it_matters: "Management quality weakens conviction..."
  - mq_summary.interpretation.thesis_impact: "weakens"
  - management_quality_dimensions.assessment fields: "weak"/"strong"

None of these should enter investor-facing text directly.
A future explicit rating framework may change this invariant.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ── Rating language patterns ──────────────────────────────────────────────────

_RATING_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bmanagement quality\s+is\s+(weak|strong|poor|good|excellent|mixed|above[\s-]average|below[\s-]average)\b", re.IGNORECASE),
    re.compile(r"\b(weak|poor|good|strong|excellent|mixed)\s+management\b", re.IGNORECASE),
    re.compile(r"\bmanagement\s+is\s+(weak|strong|poor|good|excellent|mixed)\b", re.IGNORECASE),
    re.compile(r"\boverall_view\s*[:=]\s*(weak|strong|mixed|poor|good|excellent)\b", re.IGNORECASE),
    re.compile(r"\boverall management quality\s*[:=–—]\s*(weak|strong|poor|good|excellent|mixed)\b", re.IGNORECASE),
    re.compile(r"\bmanagement quality\s+(remains|was|rated|assessed|grades?|scores?)\s+(weak|strong|poor|good|excellent|mixed)\b", re.IGNORECASE),
    re.compile(r"\bquality\s+is\s+weak\b", re.IGNORECASE),
    re.compile(r"\bquality\s+is\s+strong\b", re.IGNORECASE),
]

# Substrings that are definitely unsafe rating language (fast path)
_UNSAFE_SUBSTRINGS = [
    "management quality is weak",
    "management quality is strong",
    "management quality is poor",
    "management quality is excellent",
    "management is weak",
    "management is strong",
    "management is poor",
    "management is excellent",
    "weak management",
    "poor management",
    "excellent management",
]

# Fields in mq_summary that contain unsafe rating language
UNSAFE_MQ_SUMMARY_FIELDS = frozenset([
    "conclusion",       # "Management quality is weak and the trajectory is stable."
    "why_it_matters",   # "Management quality weakens conviction..."
    "thesis_impact",    # "weakens"
    "overall_view",     # May contain "weak"/"mixed"
])


def contains_rating_language(text: str) -> bool:
    """Return True if text contains prohibited management-quality rating language."""
    lower = text.lower()
    for substr in _UNSAFE_SUBSTRINGS:
        if substr in lower:
            return True
    for pattern in _RATING_PATTERNS:
        if pattern.search(text):
            return True
    return False


def sanitize_mq_summary_for_generation(mqs: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of mq_summary safe for use in generation inputs.

    Removes or redacts fields that contain prohibited rating language.
    Fields removed: conclusion, why_it_matters, thesis_impact, overall_view.
    Fields kept: what_to_watch, what_changed, negative_evidence, positive_evidence
    (but what_to_watch items are still subject to internal-label sanitization).
    """
    safe = {}
    interpretation = mqs.get("interpretation", {}) if isinstance(mqs, dict) else {}
    for k, v in interpretation.items():
        if k in UNSAFE_MQ_SUMMARY_FIELDS:
            safe[k] = "[QUARANTINED: contains management-quality rating language]"
        else:
            safe[k] = v
    result = {k: v for k, v in mqs.items() if k != "interpretation"}
    result["interpretation"] = safe
    return result


def check_investor_field(field_name: str, value: Any) -> List[str]:
    """Check an investor-facing field for rating language violations.

    Returns list of violation strings (empty = clean).
    """
    violations = []
    if isinstance(value, str):
        if contains_rating_language(value):
            violations.append(f"{field_name}: contains prohibited rating language")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            if isinstance(item, str) and contains_rating_language(item):
                violations.append(f"{field_name}[{i}]: contains prohibited rating language")
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, str) and contains_rating_language(v):
                violations.append(f"{field_name}.{k}: contains prohibited rating language")
    return violations


def scan_answer_for_rating_violations(answer: Dict[str, Any]) -> List[str]:
    """Scan all investor-facing answer fields for rating language violations."""
    INVESTOR_FIELDS = [
        "simple_answer", "key_points", "what_evidence_shows", "what_management_says",
        "where_management_was_consistent", "management_consistency_map",
        "what_may_mean_economically", "what_is_not_yet_proven", "what_to_monitor",
    ]
    violations = []
    for field in INVESTOR_FIELDS:
        if field in answer:
            violations.extend(check_investor_field(field, answer[field]))
    return violations
