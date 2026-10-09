"""
Management Quality Answer Capability Parity Validator — ENG-MISSION48

Checks whether a candidate answer satisfies all required semantic capabilities
defined in capability_registry. Separate from EIV (which checks investor value
heuristics); this checks structural capability presence and minimum content.

No AI calls. All checks are deterministic.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from intelligence.management_quality.capability_registry import (
    REQUIRED_CAPABILITIES,
    CANONICAL_DESCRIPTOR_VALUES,
    CAPABILITY_REGISTRY_VERSION,
)

PARITY_VALIDATOR_VERSION = "management_parity_validator.v1"

# Specific date patterns that indicate hard commitment specificity
_SPECIFIC_DATE_RE = re.compile(
    r"(fy\d{2,4}|H\d\s*CY\d{2,4}|Q\d\s*FY\d{2,4}|by\s+20\d{2}|in\s+20\d{2}|20\d{2}|\d+%)",
    re.IGNORECASE,
)

# Patterns that indicate generic uncertainty (abstract questions without named items)
_GENERIC_UNCERTAINTY_PATTERNS = [
    re.compile(r"^Are\s+", re.IGNORECASE),
    re.compile(r"^Has\s+", re.IGNORECASE),
    re.compile(r"^Is\s+", re.IGNORECASE),
]

_COUNT_RE = re.compile(
    r"(\d+\s+of\s+\d+)|(\d+\s+(?:delivered|in_progress|announced|verified|unverified|items?|commitments?))",
    re.IGNORECASE,
)


def _get_text(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return " ".join(str(x) for x in obj)
    if isinstance(obj, dict):
        return " ".join(str(v) for v in obj.values())
    return str(obj) if obj else ""


def _is_specific_uncertainty(text: str) -> bool:
    """True if what_is_not_yet_proven contains named specific items, not only abstract questions."""
    # Has a year, percentage, filing name, or specific named risk
    if _SPECIFIC_DATE_RE.search(text):
        return True
    specific_keywords = re.compile(
        r"\b(filing|EMA|FDA|USFDA|carbon|supply chain|FX|capex|NIM|GNPA|revenue share|"
        r"commitment|hard commitment|MC-\d+|platform|specialty|diversif)\b",
        re.IGNORECASE,
    )
    return bool(specific_keywords.search(text))


def _monitoring_items_are_specific(items: List) -> bool:
    """True if what_to_monitor items are substantive named monitors, not category labels."""
    if not isinstance(items, list) or len(items) < 3:
        return False
    # At least 2 of the 3 items must be longer than 25 chars
    long_items = [it for it in items if len(str(it)) >= 25]
    return len(long_items) >= 2


def _has_hard_commitment_granularity(answer: Dict) -> bool:
    """True if DPF for commitments mentions hard commitment count or status beyond just UTV."""
    dpfs = answer.get("deterministic_precision_facts", [])
    if not isinstance(dpfs, list):
        return False
    for dpf in dpfs:
        if not isinstance(dpf, dict):
            continue
        metric = str(dpf.get("metric", "")).lower()
        if "commit" not in metric:
            continue
        value = str(dpf.get("value", "")).lower()
        # PASS if value has "hard", "delivered", "delayed", "in progress", or similar status beyond UTV
        positive_markers = re.compile(
            r"\b(hard|delivered|delayed|in.progress|partially|confirmed)\b",
            re.IGNORECASE,
        )
        if positive_markers.search(value):
            return True
        # FAIL if value is ONLY "N total; N unable to verify" (no differentiation)
        # Check: if value has only "total" and "unable to verify" variants
    # Also check simple_answer for hard commitment count
    sa = str(answer.get("simple_answer", ""))
    if re.search(r"\b\d+\s+hard\b", sa, re.IGNORECASE):
        return True
    return False


def _check_capability(cap_name: str, cap_def: Dict, answer: Dict) -> Dict[str, Any]:
    """Check a single capability. Returns {name, result, reason, severity}."""
    severity = cap_def.get("severity_if_missing", "MEDIUM")

    def fail(reason: str) -> Dict:
        return {"capability": cap_name, "result": "FAIL", "reason": reason, "severity": severity}

    def warn(reason: str) -> Dict:
        return {"capability": cap_name, "result": "WARN", "reason": reason, "severity": severity}

    def ok(reason: str) -> Dict:
        return {"capability": cap_name, "result": "PASS", "reason": reason, "severity": severity}

    if cap_name == "management.lifecycle_counts":
        dpfs = answer.get("deterministic_precision_facts", [])
        if not isinstance(dpfs, list) or len(dpfs) < 1:
            return fail("deterministic_precision_facts absent — lifecycle counts not grounded")
        delivery_dpf = any(
            "delivery" in str(d.get("metric", "")).lower() or "progression" in str(d.get("metric", "")).lower()
            for d in dpfs if isinstance(d, dict)
        )
        if not delivery_dpf:
            return fail("No delivery DPF — lifecycle counts not present")
        return ok(f"{len(dpfs)} DPFs present including delivery DPF")

    if cap_name == "management.hard_commitment_detail":
        if _has_hard_commitment_granularity(answer):
            return ok("DPF or simple_answer includes hard commitment granularity")
        dpfs = answer.get("deterministic_precision_facts", [])
        commit_dpf = any("commit" in str(d.get("metric", "")).lower() for d in dpfs if isinstance(d, dict))
        if not commit_dpf:
            return fail("No commitment DPF found — hard commitment detail absent")
        return fail(
            "FACTUAL_GRANULARITY_REGRESSION: commitment DPF shows only total+UTV without "
            "hard commitment count or status breakdown (M47 pattern: '46 total; 46 unable to verify')"
        )

    if cap_name == "management.evidence_observations":
        wes = answer.get("what_evidence_shows", [])
        if not wes:
            return fail("what_evidence_shows absent — evidence observations not present")
        if isinstance(wes, list):
            valid = [e for e in wes if len(str(e).strip()) > 15]
            if len(valid) >= 2:
                return ok(f"what_evidence_shows has {len(valid)} substantive entries")
            return fail(f"what_evidence_shows has only {len(valid)} substantive entries (minimum 2)")
        if isinstance(wes, str) and len(wes.strip()) > 50:
            return ok("what_evidence_shows present as non-empty string")
        return fail("what_evidence_shows present but insufficient content")

    if cap_name == "management.management_statements":
        wms = answer.get("what_management_says", [])
        if not wms:
            return fail("what_management_says absent — management statements not present")
        if isinstance(wms, list) and len(wms) >= 1:
            if any(len(str(s)) > 20 for s in wms):
                return ok(f"what_management_says has {len(wms)} entries")
            return fail("what_management_says entries too short to be meaningful")
        if isinstance(wms, str) and len(wms.strip()) > 20:
            return ok("what_management_says present as non-empty string")
        return fail("what_management_says present but trivially short")

    if cap_name == "management.consistency_analysis":
        cmap = answer.get("management_consistency_map", {})
        wmwc = answer.get("where_management_was_consistent", [])
        has_map = isinstance(cmap, dict) and len(cmap) >= 3
        has_bullets = (
            (isinstance(wmwc, list) and len(wmwc) >= 1) or
            (isinstance(wmwc, str) and len(wmwc.strip()) > 20)
        )
        if has_map and has_bullets:
            return ok(f"management_consistency_map ({len(cmap)} entries) + where_management_was_consistent present")
        if not has_map and not has_bullets:
            return fail("management_consistency_map absent AND where_management_was_consistent absent")
        if not has_map:
            return warn(f"management_consistency_map has only {len(cmap) if isinstance(cmap, dict) else 0} entries (min 3)")
        return warn("where_management_was_consistent absent (consistency map present but no bullets)")

    if cap_name == "management.economic_context":
        wmme = answer.get("what_may_mean_economically")
        if wmme and len(_get_text(wmme).strip()) > 30:
            fin_terms = re.compile(
                r"\b(NPM|margin|revenue|PAT|profit|return|ROCE|capital|dividend|compounding)\b",
                re.IGNORECASE,
            )
            if fin_terms.search(_get_text(wmme)):
                return ok("what_may_mean_economically present with financial terms")
            return warn("what_may_mean_economically present but lacks specific financial metric")
        # Accept financial DPF as partial credit
        dpfs = answer.get("deterministic_precision_facts", [])
        if isinstance(dpfs, list):
            has_npm_in_dpf = any(
                "NPM" in str(d.get("value", "")) for d in dpfs if isinstance(d, dict)
            )
            if has_npm_in_dpf:
                return warn("NPM in DPF but what_may_mean_economically absent — MEDIUM gap")
        return fail(
            "what_may_mean_economically absent AND no NPM in DPFs — "
            "economic context for investor not present"
        )

    if cap_name == "management.uncertainty":
        winp = answer.get("what_is_not_yet_proven")
        if not winp:
            return fail("what_is_not_yet_proven absent — uncertainty map not present")
        text = _get_text(winp)
        if len(text.strip()) < 20:
            return fail("what_is_not_yet_proven too short to be meaningful")
        if _is_specific_uncertainty(text):
            return ok("what_is_not_yet_proven contains specific named items")
        return fail(
            "UNCERTAINTY_CAPABILITY_REGRESSION: what_is_not_yet_proven is generic abstract questions "
            "without named specific commitments/risks (M47 pattern: raw mq_summary.unresolved)"
        )

    if cap_name == "management.monitoring":
        wtm = answer.get("what_to_monitor", [])
        if not wtm:
            # Check evidence_gaps as fallback
            gaps = answer.get("evidence_gaps", [])
            if gaps:
                return warn("what_to_monitor absent; evidence_gaps provides fallback monitoring proxy")
            return fail("what_to_monitor absent — investor monitoring agenda not present")
        if isinstance(wtm, list):
            if len(wtm) < 3:
                return fail(f"what_to_monitor has only {len(wtm)} items (minimum 3)")
            if _monitoring_items_are_specific(wtm):
                return ok(f"what_to_monitor has {len(wtm)} specific items")
            return fail(
                f"what_to_monitor has {len(wtm)} items but they appear to be generic category labels "
                "(M47 pattern: raw mq_summary.what_to_watch — 'Industry_outlook', etc.)"
            )
        return ok("what_to_monitor present")

    if cap_name == "management.dpfs":
        dpfs = answer.get("deterministic_precision_facts", [])
        if not isinstance(dpfs, list):
            return fail("deterministic_precision_facts absent")
        valid = [d for d in dpfs if isinstance(d, dict) and d.get("metric") and d.get("value") and d.get("semantic_meaning")]
        if len(valid) < 3:
            return fail(f"Only {len(valid)} valid DPF entries (minimum 3)")
        return ok(f"{len(valid)} valid DPF entries")

    if cap_name == "management.behavioral_descriptor":
        # Check simple_answer or behavioral_descriptor field
        sa = str(answer.get("simple_answer", ""))
        bd_field = str(answer.get("behavioral_descriptor", ""))
        all_text = sa + " " + bd_field
        for descriptor in CANONICAL_DESCRIPTOR_VALUES:
            if descriptor in all_text:
                return ok(f"Canonical descriptor '{descriptor}' present")
        return fail(
            "Behavioral descriptor not found in simple_answer or behavioral_descriptor field. "
            "Must be one of: " + ", ".join(sorted(CANONICAL_DESCRIPTOR_VALUES))
        )

    if cap_name == "management.evidence_traceability":
        wes = answer.get("what_evidence_shows", [])
        if isinstance(wes, list) and len(wes) >= 2:
            return ok("what_evidence_shows provides evidence traceability")
        claims = answer.get("claims", [])
        if isinstance(claims, list):
            with_refs = [c for c in claims if isinstance(c, dict) and c.get("evidence_refs")]
            if len(with_refs) >= 3:
                return ok(f"{len(with_refs)} claims with evidence_refs provide traceability")
        return fail("No evidence traceability path: what_evidence_shows absent/short AND insufficient claims with evidence_refs")

    return warn(f"Unknown capability: {cap_name}")


def validate_management_semantic_capability_parity(
    candidate: Dict[str, Any],
    trusted_contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Validate candidate answer against all required capabilities.

    Args:
        candidate: The candidate answer dict (handles wrapped {answer: {...}} or bare answer).
        trusted_contract: Optional trusted baseline for comparison (unused structurally,
                          capabilities are checked against registry not baseline).

    Returns:
        {
            "overall": "PASS" | "WARN" | "FAIL",
            "capability_results": [...],
            "fail_count": N,
            "warn_count": N,
            "high_severity_fails": [...],
            "medium_severity_fails": [...],
            "schema_version": "management_parity_validator.v1",
        }
    """
    # Unwrap if needed
    if "answer" in candidate and isinstance(candidate.get("answer"), dict):
        ans = candidate["answer"]
    else:
        ans = candidate

    results = []
    for cap_name, cap_def in REQUIRED_CAPABILITIES.items():
        result = _check_capability(cap_name, cap_def, ans)
        results.append(result)

    fails = [r for r in results if r["result"] == "FAIL"]
    warns = [r for r in results if r["result"] == "WARN"]
    high_fails = [r for r in fails if r.get("severity") == "HIGH"]
    medium_fails = [r for r in fails if r.get("severity") == "MEDIUM"]

    # FAIL if any HIGH capability fails; WARN if only MEDIUM fails
    if high_fails:
        overall = "FAIL"
    elif medium_fails or warns:
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "schema_version": PARITY_VALIDATOR_VERSION,
        "overall": overall,
        "fail_count": len(fails),
        "warn_count": len(warns),
        "high_severity_fails": [r["capability"] for r in high_fails],
        "medium_severity_fails": [r["capability"] for r in medium_fails],
        "capability_results": results,
    }
