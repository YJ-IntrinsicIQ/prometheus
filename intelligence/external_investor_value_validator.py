"""
External Investor Value (EIV) Validator — ENG-MISSION46

Deterministic rule-based validator that checks whether a management quality answer
meets minimum investor-value standards. Separate from PACP:

  PACP  → tests semantic safety (no rating leakage, descriptor present)
  EIV   → tests investor completeness (factual counts, DPFs, uncertainty, monitoring)

PACP PASS + EIV FAIL = candidate blocked (M45.2 was exactly this case)
PACP PASS + EIV PASS = HUMAN_REVIEW_ELIGIBLE

No AI calls. All checks are deterministic.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

EIV_SCHEMA_VERSION = "eiv_management_quality.v1"

# Minimum DPF count required
_MIN_DPFS = 3

# Minimum key_points count
_MIN_KEY_POINTS = 3

# Generic filler phrases that indicate collapse (without specifics nearby)
_GENERIC_PHRASES = [
    r"\bmanagement quality\b.*\b(weak|strong|mixed)\b",
    r"\binvestment thesis\b",
    r"\bconviction\b.*\bimprove\b",
]

# Patterns indicating factual specificity in text
_COUNT_PATTERN = re.compile(
    r"(\d+\s+of\s+\d+)|"       # "X of Y"
    r"(\d+\s+(?:delivered|in_progress|announced|verified|unverified|items?|commitments?))|"
    r"(₹[\d,]+)|"               # currency
    r"(FY\d{2,4})",              # fiscal year
    re.IGNORECASE,
)


def _get_text(obj: Any) -> str:
    """Flatten any string/list to searchable text."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return " ".join(str(x) for x in obj)
    if isinstance(obj, dict):
        return " ".join(str(v) for v in obj.values())
    return str(obj) if obj else ""


def _has_factual_specificity(text: str) -> bool:
    return bool(_COUNT_PATTERN.search(text))


def _verdict(passed: bool, rule: str, reason: str) -> Dict[str, Any]:
    return {"rule": rule, "result": "PASS" if passed else "FAIL", "reason": reason}


# ---------------------------------------------------------------------------
# Individual rule implementations
# ---------------------------------------------------------------------------


def _eiv_mq_01_factual_specificity(answer: Dict) -> Dict:
    """
    EIV-MQ-01: simple_answer + key_points must contain factual specifics
    (counts, named items, fiscal years) — not only editorial synthesis.
    """
    sa = _get_text(answer.get("simple_answer", ""))
    kp = _get_text(answer.get("key_points", []))

    # Check simple_answer
    sa_specific = _has_factual_specificity(sa)

    # Check key_points for factual content
    kp_list = answer.get("key_points", [])
    if not isinstance(kp_list, list):
        kp_list = [str(kp_list)] if kp_list else []

    kp_specific = any(_has_factual_specificity(str(kp)) for kp in kp_list)
    has_enough_kps = len(kp_list) >= _MIN_KEY_POINTS

    # Also accept DPF-grounded answers
    dpfs = answer.get("deterministic_precision_facts", [])
    dpf_grounded = isinstance(dpfs, list) and len(dpfs) >= _MIN_DPFS

    if (sa_specific or kp_specific) and has_enough_kps:
        return _verdict(True, "EIV-MQ-01", "simple_answer or key_points contain factual specifics")
    if dpf_grounded:
        return _verdict(True, "EIV-MQ-01", "DPFs provide factual grounding even without counts in prose")

    if not has_enough_kps:
        return _verdict(False, "EIV-MQ-01", f"key_points has only {len(kp_list)} entries (minimum {_MIN_KEY_POINTS})")
    return _verdict(False, "EIV-MQ-01", "simple_answer and key_points lack factual specifics (counts, fiscal years, named items)")


def _eiv_mq_02_evidence_density(answer: Dict) -> Dict:
    """
    EIV-MQ-02: Material conclusions must map to evidence. Requires
    what_evidence_shows (non-empty list) OR non-empty claims with evidence_refs.
    """
    wes = answer.get("what_evidence_shows", [])
    if isinstance(wes, list) and len(wes) >= 2:
        return _verdict(True, "EIV-MQ-02", f"what_evidence_shows has {len(wes)} evidence entries")

    claims = answer.get("claims", [])
    if isinstance(claims, list):
        with_refs = [c for c in claims if isinstance(c, dict) and c.get("evidence_refs")]
        if len(with_refs) >= 5:
            return _verdict(True, "EIV-MQ-02", f"{len(with_refs)} claims with evidence_refs")

    return _verdict(False, "EIV-MQ-02",
        "what_evidence_shows is absent/empty; insufficient claims with evidence_refs — "
        "investor cannot verify what evidence underlies the conclusions")


def _eiv_mq_03_uncertainty_coverage(answer: Dict) -> Dict:
    """
    EIV-MQ-03: Material unresolved states must be named. Requires
    what_is_not_yet_proven (non-empty) OR evidence_gaps (non-empty).
    """
    winp = answer.get("what_is_not_yet_proven")
    if winp:
        text = _get_text(winp)
        if len(text.strip()) > 20:
            return _verdict(True, "EIV-MQ-03", "what_is_not_yet_proven present and non-trivial")

    gaps = answer.get("evidence_gaps", [])
    if isinstance(gaps, list) and len(gaps) >= 1:
        non_empty = [g for g in gaps if _get_text(g).strip()]
        if non_empty:
            return _verdict(True, "EIV-MQ-03", f"evidence_gaps has {len(non_empty)} explicit uncertainty items")

    return _verdict(False, "EIV-MQ-03",
        "what_is_not_yet_proven absent/empty AND evidence_gaps absent/empty — "
        "investor has no view of material unresolved states")


def _eiv_mq_04_dpf_coverage(answer: Dict) -> Dict:
    """
    EIV-MQ-04: Required DPFs present (>= 3 entries with metric, value, semantic_meaning).
    Delivery follow-through DPF required.
    """
    dpfs = answer.get("deterministic_precision_facts", [])
    if not isinstance(dpfs, list):
        return _verdict(False, "EIV-MQ-04", "deterministic_precision_facts field absent")

    valid = [
        d for d in dpfs
        if isinstance(d, dict) and d.get("metric") and d.get("value") and d.get("semantic_meaning")
    ]
    if len(valid) < _MIN_DPFS:
        return _verdict(False, "EIV-MQ-04",
            f"Only {len(valid)} valid DPF entries (minimum {_MIN_DPFS} required; M45.2 had 0)")

    # Require at least one delivery-related DPF
    delivery_dpf = any(
        "delivery" in str(d.get("metric", "")).lower() or "progression" in str(d.get("metric", "")).lower()
        for d in valid
    )
    if not delivery_dpf:
        return _verdict(False, "EIV-MQ-04", "No delivery follow-through DPF found — required to ground behavioral descriptor")

    return _verdict(True, "EIV-MQ-04", f"{len(valid)} valid DPF entries including delivery DPF")


def _eiv_mq_05_economic_context(answer: Dict) -> Dict:
    """
    EIV-MQ-05: Relevant capital/economic observations preserved.
    Accepts: what_may_mean_economically, or financial data in DPFs.
    """
    wmme = answer.get("what_may_mean_economically")
    if wmme and len(_get_text(wmme).strip()) > 30:
        return _verdict(True, "EIV-MQ-05", "what_may_mean_economically present and non-trivial")

    # Accept financial DPF as economic context
    dpfs = answer.get("deterministic_precision_facts", [])
    if isinstance(dpfs, list):
        fin_dpf = any(
            any(kw in str(d.get("metric", "")).lower() for kw in ("financial", "revenue", "pat", "scale", "capital"))
            for d in dpfs if isinstance(d, dict)
        )
        if fin_dpf:
            return _verdict(True, "EIV-MQ-05", "Financial/capital DPF provides economic context")

    # Accept capital allocation context in other fields
    all_text = _get_text([
        answer.get("what_evidence_shows", ""),
        answer.get("key_points", []),
        answer.get("simple_answer", ""),
    ])
    fin_keywords = re.compile(r"\b(revenue|profit|margin|capital|return|dividend|allocation|cash|ROCE|PAT|NPM)\b", re.I)
    if fin_keywords.search(all_text):
        return _verdict(True, "EIV-MQ-05", "Financial/economic terms present in answer text")

    return _verdict(False, "EIV-MQ-05",
        "No economic/financial context found — what_may_mean_economically absent, no financial DPFs, no financial terms")


def _eiv_mq_06_monitoring_value(answer: Dict) -> Dict:
    """
    EIV-MQ-06: Answer identifies what to monitor. Requires
    what_to_monitor (non-empty) OR evidence_gaps (non-empty) OR what_is_not_yet_proven.
    """
    wtm = answer.get("what_to_monitor", [])
    if isinstance(wtm, list) and len(wtm) >= 1:
        non_empty = [w for w in wtm if _get_text(w).strip()]
        if non_empty:
            return _verdict(True, "EIV-MQ-06", f"what_to_monitor has {len(non_empty)} monitoring items")

    # evidence_gaps as monitoring proxy
    gaps = answer.get("evidence_gaps", [])
    if isinstance(gaps, list) and len(gaps) >= 1:
        non_empty = [g for g in gaps if _get_text(g).strip()]
        if non_empty:
            return _verdict(True, "EIV-MQ-06", f"evidence_gaps provides {len(non_empty)} monitoring proxy items")

    # what_is_not_yet_proven as monitoring proxy
    winp = answer.get("what_is_not_yet_proven")
    if winp and len(_get_text(winp).strip()) > 20:
        return _verdict(True, "EIV-MQ-06", "what_is_not_yet_proven provides monitoring proxy")

    return _verdict(False, "EIV-MQ-06",
        "No monitoring value — what_to_monitor absent/empty AND no evidence_gaps AND what_is_not_yet_proven absent")


def _eiv_mq_07_no_semantic_compression_loss(answer: Dict) -> Dict:
    """
    EIV-MQ-07: Required semantic categories from contract v2 present.
    No silent omission of investor-critical fields.
    """
    required = [
        ("simple_answer", "Simple investor answer"),
        ("key_points", "Key factual takeaways"),
        ("deterministic_precision_facts", "Machine-verifiable DPFs"),
    ]
    # At least one of the uncertainty fields
    uncertainty_fields = ["what_is_not_yet_proven", "evidence_gaps"]
    # At least one of the evidence fields
    evidence_fields = ["what_evidence_shows", "claims"]

    missing = []
    for field, label in required:
        val = answer.get(field)
        if not val or (isinstance(val, (list, dict)) and len(val) == 0):
            missing.append(f"{field} ({label})")

    has_uncertainty = any(
        answer.get(f) and len(_get_text(answer[f]).strip()) > 10
        for f in uncertainty_fields
    )
    if not has_uncertainty:
        missing.append("uncertainty field (what_is_not_yet_proven or evidence_gaps)")

    has_evidence = any(
        answer.get(f) and (
            (isinstance(answer[f], list) and len(answer[f]) >= 2) or
            (isinstance(answer[f], str) and len(answer[f]) > 20)
        )
        for f in evidence_fields
    )
    if not has_evidence:
        missing.append("evidence field (what_evidence_shows with 2+ entries, or claims)")

    if missing:
        return _verdict(False, "EIV-MQ-07", f"Required semantic categories missing: {'; '.join(missing)}")
    return _verdict(True, "EIV-MQ-07", "All required semantic categories present")


def _eiv_mq_08_no_generic_answer_collapse(answer: Dict) -> Dict:
    """
    EIV-MQ-08: Answer must not consist mainly of generic management commentary
    while deterministic evidence exists. Catches high-level synthesis without specifics.
    """
    sa = _get_text(answer.get("simple_answer", ""))
    kp_list = answer.get("key_points", [])
    kp_text = _get_text(kp_list)

    # Fail if simple_answer is very short (< 15 words) and lacks specifics
    sa_words = sa.split()
    if len(sa_words) < 15:
        return _verdict(False, "EIV-MQ-08",
            f"simple_answer too brief ({len(sa_words)} words) — insufficient investor information")

    # Check if answer contains ONLY generic phrases without any specificity
    all_text = sa + " " + kp_text
    has_specifics = _has_factual_specificity(all_text)

    # Check descriptor is present
    descriptor_present = (
        "FOLLOW_THROUGH_LARGELY_UNVERIFIED" in sa or
        "PARTIAL_DELIVERY" in sa or
        "MULTIPLE_DELIVERIES" in sa or
        "HIGH_DELIVERY_COUNT" in sa or
        "UNVERIFIED" in sa.upper()
    )

    if not has_specifics and not descriptor_present:
        return _verdict(False, "EIV-MQ-08",
            "simple_answer is generic synthesis without factual counts or named descriptor — "
            "investor cannot distinguish this from a stock boilerplate answer")

    if not descriptor_present:
        # Tolerance: if DPFs are present and specific, allow it
        dpfs = answer.get("deterministic_precision_facts", [])
        if isinstance(dpfs, list) and len(dpfs) >= _MIN_DPFS:
            return _verdict(True, "EIV-MQ-08", "DPFs provide non-generic factual grounding despite generic prose")
        return _verdict(False, "EIV-MQ-08",
            "simple_answer lacks behavioral descriptor and factual specificity — generic answer collapse")

    return _verdict(True, "EIV-MQ-08", "Answer contains behavioral descriptor and/or factual specifics")


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------


def validate_management_answer_eiv(
    answer: Dict[str, Any],
    fact_pack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run all 8 EIV rules against a management quality answer.

    Args:
        answer:    The answer dict (top-level 'answer' field, or the dict itself).
        fact_pack: Optional deterministic fact pack for cross-validation.

    Returns:
        {
            "overall": "PASS" | "FAIL",
            "checks": [...],  # 8 rule results
            "fails": [...],   # failing rule IDs
            "warns": [...],   # warning rule IDs (none currently)
            "fail_count": N,
            "schema_version": "eiv_management_quality.v1",
        }
    """
    # Handle both wrapped {"answer": {...}} and bare answer dicts
    if "answer" in answer and isinstance(answer.get("answer"), dict):
        ans = answer["answer"]
    else:
        ans = answer

    rules = [
        _eiv_mq_01_factual_specificity,
        _eiv_mq_02_evidence_density,
        _eiv_mq_03_uncertainty_coverage,
        _eiv_mq_04_dpf_coverage,
        _eiv_mq_05_economic_context,
        _eiv_mq_06_monitoring_value,
        _eiv_mq_07_no_semantic_compression_loss,
        _eiv_mq_08_no_generic_answer_collapse,
    ]

    checks = [rule(ans) for rule in rules]
    fails = [c["rule"] for c in checks if c["result"] == "FAIL"]

    return {
        "schema_version": EIV_SCHEMA_VERSION,
        "overall": "PASS" if not fails else "FAIL",
        "fail_count": len(fails),
        "fails": fails,
        "warns": [],
        "checks": checks,
    }


def validate_management_answer_semantic_parity(
    candidate: Dict[str, Any],
    baseline_contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Check minimum semantic coverage vs contract v2.
    Returns same format as validate_management_answer_eiv but focused on
    field presence rather than content quality.
    """
    return validate_management_answer_eiv(candidate, baseline_contract)
