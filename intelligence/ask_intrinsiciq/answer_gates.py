"""Pre-save investor-output quality gates for Ask IntrinsicIQ answer cards.

Each gate is a small, focused validator. Gates classify each failure as one of:
  BLOCK_CARD          — reject the entire answer card
  QUARANTINE_POINT    — remove the offending key point but keep the card
  DEGRADE_TO_UNAVAILABLE — downgrade answer_status to unavailable
  OMIT_EMPTY_SECTION  — omit the section silently

No silent bypasses. Every rejected card records WHY it failed.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ── Internal-language patterns (G5) ──────────────────────────────────────────

_INTERNAL_PHRASE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\binvestment lens implication\b", re.IGNORECASE),
    re.compile(r"\bprimary investment lens question\b", re.IGNORECASE),
    re.compile(r"investment lens[- ]framed", re.IGNORECASE),
    re.compile(r"investment lens[- ]specific", re.IGNORECASE),
    re.compile(r"\bclaim evidence only\b", re.IGNORECASE),
    re.compile(r"\bfact and implication\b", re.IGNORECASE),
    re.compile(r"\bcounterpoint\s*:", re.IGNORECASE),
    re.compile(r"\bcompact financial inputs\b", re.IGNORECASE),
    re.compile(r"\bsource set summaries\b", re.IGNORECASE),
    re.compile(r"\bcommittee-level output\b", re.IGNORECASE),
    re.compile(r"\bpcim\b", re.IGNORECASE),
    re.compile(r"\bdoctrine_id\b", re.IGNORECASE),
    re.compile(r"[a-z]+_[a-z]+\.[a-z]+", re.IGNORECASE),  # snake_case.identifier
    re.compile(r"\bCLAIM_ONLY\b"),
    re.compile(r"\bACTION_STARTED\b"),
    re.compile(r"\bACTION_COMPLETED\b"),
    re.compile(r"\bFINANCIAL_LINK_[A-Z_]+\b"),
    re.compile(r"\bin the supplied (evidence|inputs)\b", re.IGNORECASE),
    re.compile(r"\bfrom supplied (evidence|inputs)\b", re.IGNORECASE),
]

# Internal ID patterns (G6)
_INTERNAL_ID_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\b[a-z]+_pharma\b", re.IGNORECASE),   # sun_pharma style internal slug
    re.compile(r"\b[a-z]+_[a-z]+_analysis\b", re.IGNORECASE),  # buffett_analysis style
    re.compile(r"companies/[a-z_]+/", re.IGNORECASE),   # filesystem path
    re.compile(r"/company_memory/", re.IGNORECASE),
]

# Contradiction pairs for G7 (phrase_a → phrase_b implies contradiction).
# Patterns are deliberately narrow to avoid false positives — only match
# when the claim and its contradictory evidence are clearly about the same concept.
_CONTRADICTION_PAIRS = [
    (re.compile(r"\bfcf cannot be assessed\b|\bfree cash flow\b.*\bcannot be assessed\b", re.IGNORECASE),
     re.compile(r"\bfcf\s*=\s*₹\d|\bfcf per share\b", re.IGNORECASE)),
    (re.compile(r"\bcurrent-year snapshot only\b|\bsnapshot only\b", re.IGNORECASE),
     re.compile(r"\bfy\d{2}\b.*?[–\-to].*?\bfy\d{2}\b", re.IGNORECASE)),  # "FY20 to FY26" pattern
    (re.compile(r"\bno management commitments exist\b|\bzero commitments tracked\b", re.IGNORECASE),
     re.compile(r"\bcommitments tracked\b|\bgold promise tracker\b|\bmc-\d+\b", re.IGNORECASE)),
]

# Analytical question IDs that must meet G9 decision-usefulness minimum
_ANALYTICAL_QUESTION_IDS = frozenset({
    "what-would-buffett-focus-on",
    "where-would-fisher-be-curious",
    "what-can-break-the-thesis",
    "what-evidence-would-change-the-view",
    "what-remains-unresolved",
})


# ── Gate helpers ─────────────────────────────────────────────────────────────

def _all_text(answer: Dict[str, Any]) -> str:
    """Flatten all investor-visible text from an answer card into one string."""
    parts: List[str] = []
    for field in ("simple_answer", "why_it_matters", "detailed_explanation", "uncertainty"):
        v = answer.get(field)
        if isinstance(v, str):
            parts.append(v)
    for kp in answer.get("key_points") or []:
        if isinstance(kp, str):
            parts.append(kp)
    for ep in answer.get("evidence_points") or []:
        if isinstance(ep, str):
            parts.append(ep)
    for section in answer.get("structured_sections") or []:
        if isinstance(section, dict):
            for pt in section.get("points") or []:
                if isinstance(pt, str):
                    parts.append(pt)
    interp = answer.get("interpretation") or {}
    if isinstance(interp, dict):
        for field in ("conclusion", "economic_mechanism", "thesis_impact"):
            v = interp.get(field)
            if isinstance(v, str):
                parts.append(v)
        for sub in ("positive_evidence", "negative_evidence", "unresolved", "what_to_watch"):
            for item in interp.get(sub) or []:
                if isinstance(item, str):
                    parts.append(item)
    return " ".join(parts)


def _contains_internal_language(text: str) -> Optional[str]:
    """Return the first matching internal phrase, or None."""
    for pat in _INTERNAL_PHRASE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group()
    return None


def _contains_internal_id(text: str) -> Optional[str]:
    """Return the first matching internal identifier, or None."""
    for pat in _INTERNAL_ID_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group()
    return None


def _has_named_metric_or_watchpoint(text: str) -> bool:
    """True if text contains a named metric, number, or concrete watchpoint."""
    # Named metric: a currency amount, percentage, or specific ratio
    if re.search(r"₹\d|[\d]+\.?\d*\s*%|[\d]+\.?\d*\s*(day|year|crore|times|x)\b", text, re.IGNORECASE):
        return True
    # Named company initiative, risk, or watchpoint (at least one capitalized multi-word phrase or watchpoint term)
    if re.search(r"\b(receivable|inventory|cash conversion|capex|FCF|ROE|CAGR|working capital|owner earnings)\b", text, re.IGNORECASE):
        return True
    return False


def _answer_has_multi_year_data(answer: Dict[str, Any]) -> bool:
    """True if the answer references at least two different fiscal years."""
    text = _all_text(answer)
    years = re.findall(r"\bfy\d{2,4}\b", text, re.IGNORECASE)
    return len(set(y.lower() for y in years)) >= 2


def _answer_claims_snapshot_only(answer: Dict[str, Any]) -> bool:
    """True if the answer claims snapshot-only / no-multi-year."""
    text = _all_text(answer).lower()
    return bool(re.search(
        r"snapshot only|insufficient history|does not.*support.*multi.year|"
        r"multi.year.*not.*available|only.*current.year",
        text, re.IGNORECASE,
    ))


# ── Individual gates ─────────────────────────────────────────────────────────

def _gate_g2_multi_year_synthesis(answer: Dict[str, Any], question_id: str) -> Optional[Dict[str, Any]]:
    """G2: If >=5 comparable years exist, the answer must not claim snapshot-only."""
    if question_id != "are-per-share-economics-improving":
        return None
    if _answer_claims_snapshot_only(answer) and _answer_has_multi_year_data(answer):
        return {
            "gate_id": "G2",
            "status": "fail",
            "action": "BLOCK_CARD",
            "reason": "Answer claims snapshot-only but references multiple fiscal years — contradiction detected.",
        }
    return None


def _gate_g3_project_temporal(answers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """G3: Active/underway project must have temporal support (enforced in builder; gate records)."""
    # The builder already enforces temporal integrity; this gate records the outcome
    # by checking that the projects answer does NOT reference unable_to_verify status
    # as active, and does NOT label historical events as current.
    failures: List[Dict[str, Any]] = []
    for answer in answers:
        if answer.get("question_id") != "what-projects-are-underway":
            continue
        text = _all_text(answer).lower()
        if re.search(r"\b(2014|fy14|fy15)\b", text) and re.search(r"\bunderway\b|\bcurrently\b|\bin progress\b", text):
            failures.append({
                "gate_id": "G3",
                "status": "fail",
                "action": "BLOCK_CARD",
                "reason": "Projects answer references historical events (FY14/FY15 era) as currently underway.",
                "question_id": "what-projects-are-underway",
            })
    return failures


def _gate_g5_internal_language(answer: Dict[str, Any], question_id: str) -> Optional[Dict[str, Any]]:
    """G5: No internal/template language in investor-facing text."""
    text = _all_text(answer)
    match = _contains_internal_language(text)
    if match:
        return {
            "gate_id": "G5",
            "status": "fail",
            "action": "BLOCK_CARD",
            "reason": f"Internal template phrase found: {match!r}",
            "question_id": question_id,
        }
    return None


def _gate_g6_internal_id(answer: Dict[str, Any], question_id: str) -> Optional[Dict[str, Any]]:
    """G6: No internal identifiers (filesystem paths, slug names) in investor text."""
    text = _all_text(answer)
    match = _contains_internal_id(text)
    if match:
        return {
            "gate_id": "G6",
            "status": "fail",
            "action": "QUARANTINE_POINT",
            "reason": f"Internal identifier found: {match!r}",
            "question_id": question_id,
        }
    return None


def _gate_g7_cross_section_contradiction(answer: Dict[str, Any], question_id: str) -> Optional[Dict[str, Any]]:
    """G7: Two sections of the same answer must not make incompatible factual claims."""
    text = _all_text(answer)
    for pattern_a, pattern_b in _CONTRADICTION_PAIRS:
        if pattern_a.search(text) and pattern_b.search(text):
            return {
                "gate_id": "G7",
                "status": "fail",
                "action": "BLOCK_CARD",
                "reason": f"Contradiction: pattern '{pattern_a.pattern[:40]}' conflicts with '{pattern_b.pattern[:40]}'",
                "question_id": question_id,
            }
    return None


def _gate_g8_empty_section(answer: Dict[str, Any], question_id: str) -> Optional[Dict[str, Any]]:
    """G8: Visible sections must have meaningful content."""
    for section in answer.get("structured_sections") or []:
        if isinstance(section, dict):
            points = [p for p in (section.get("points") or []) if isinstance(p, str) and p.strip()]
            title = section.get("title", "")
            if title and not points:
                return {
                    "gate_id": "G8",
                    "status": "fail",
                    "action": "OMIT_EMPTY_SECTION",
                    "reason": f"Section '{title}' has a title but no content.",
                    "question_id": question_id,
                }
    return None


def _gate_g9_decision_usefulness(answer: Dict[str, Any], question_id: str) -> Optional[Dict[str, Any]]:
    """G9: Analytical answers must contain at least one named metric, initiative, risk, or watchpoint."""
    if question_id not in _ANALYTICAL_QUESTION_IDS:
        return None
    text = _all_text(answer)
    if not _has_named_metric_or_watchpoint(text):
        # Also check for named initiatives (capitalized phrases of 2+ words)
        named_initiative = re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b|\b[A-Z]{2,}\b", text)
        if not named_initiative:
            return {
                "gate_id": "G9",
                "status": "fail",
                "action": "DEGRADE_TO_UNAVAILABLE",
                "reason": "Analytical answer contains no named metric, initiative, risk, or measurable watchpoint.",
                "question_id": question_id,
            }
    return None


# ── Main validator ────────────────────────────────────────────────────────────

def validate_answer_cards(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run all pre-save gates against an answer cards payload.

    Returns:
        {
            "passed": bool,
            "gate_failures": [...],
            "gates_run": int,
            "gate_pass_count": int,
            "gate_fail_count": int,
        }
    """
    answers = payload.get("answers") or []
    failures: List[Dict[str, Any]] = []
    gates_run = 0

    # Per-answer gates
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        qid = str(answer.get("question_id") or answer.get("id") or "")
        # Skip unavailable/not_supported answers — no content to validate
        if answer.get("answer_status") in ("unavailable", "not_supported", "not_applicable"):
            continue

        for gate_fn, args in [
            (_gate_g2_multi_year_synthesis, (answer, qid)),
            (_gate_g5_internal_language, (answer, qid)),
            (_gate_g6_internal_id, (answer, qid)),
            (_gate_g7_cross_section_contradiction, (answer, qid)),
            (_gate_g8_empty_section, (answer, qid)),
            (_gate_g9_decision_usefulness, (answer, qid)),
        ]:
            gates_run += 1
            result = gate_fn(*args)
            if result:
                failures.append(result)

    # Cross-answer gates
    g3_failures = _gate_g3_project_temporal(answers)
    gates_run += 1
    failures.extend(g3_failures)

    return {
        "passed": len(failures) == 0,
        "gate_failures": failures,
        "gates_run": gates_run,
        "gate_pass_count": gates_run - len(failures),
        "gate_fail_count": len(failures),
    }
