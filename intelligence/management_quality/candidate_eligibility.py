"""
M46.1: Release eligibility evaluation for management quality candidates.

New gate (Contract V2, effective M47 onward):
    ARTIFACT_IDENTITY_VALID AND PACP_PASS AND EIV_PASS → HUMAN_REVIEW_ELIGIBLE

Old gate (pre-M46.1):
    PACP_PASS → HUMAN_REVIEW_ELIGIBLE   ← M45.2 proved this insufficient

This evaluator NEVER:
  - writes the approval registry
  - sets reviewer or approval timestamp
  - activates a candidate
  - resets a human REJECT decision

HUMAN_REVIEW_ELIGIBLE != APPROVED.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# ── Eligibility states ────────────────────────────────────────────────────────
HUMAN_REVIEW_ELIGIBLE = "HUMAN_REVIEW_ELIGIBLE"
BLOCKED_PACP = "BLOCKED_PACP"
BLOCKED_EIV = "BLOCKED_EIV"
BLOCKED_ARTIFACT_IDENTITY = "BLOCKED_ARTIFACT_IDENTITY"
BLOCKED_MULTIPLE = "BLOCKED_MULTIPLE"

_PACP_PASS_STATES = frozenset({"PASS", "WARN"})
_EIV_SUPPORTED_SCHEMAS = frozenset({"eiv_management_quality.v1"})


def evaluate_candidate_release_eligibility(
    candidate: Dict[str, Any],
    pacp_result: Optional[Dict[str, Any]] = None,
    eiv_result: Optional[Dict[str, Any]] = None,
    check_artifact_identity: bool = True,
) -> Dict[str, Any]:
    """
    Determine whether a candidate is eligible for human review.

    Args:
        candidate:              Raw candidate dict (top-level keys include answer, etc.)
        pacp_result:            Pre-run PACP result, or None to read from candidate.
        eiv_result:             Pre-run EIV result, or None to run EIV inline.
        check_artifact_identity: Verify candidate has a non-empty digest.

    Returns dict with:
        eligible:               bool
        eligibility_state:      one of the state constants
        blocks:                 list of block reasons
        pacp_overall:           PASS | FAIL | WARN | UNKNOWN
        eiv_overall:            PASS | FAIL | WARN | MISSING
        artifact_identity_valid: bool
    """
    blocks = []

    # ── 1. Artifact identity ──────────────────────────────────────────────────
    artifact_identity_valid = True
    if check_artifact_identity:
        digest = (
            candidate.get("candidate_digest") or
            candidate.get("digest") or
            candidate.get("artifact_digest") or
            ""
        )
        if not digest or digest.startswith("NOT_WRITTEN"):
            artifact_identity_valid = False
            blocks.append(BLOCKED_ARTIFACT_IDENTITY)

    # ── 2. PACP ───────────────────────────────────────────────────────────────
    _pacp = pacp_result
    if _pacp is None:
        _pacp = candidate.get("pacp_result") or {}
    pacp_overall = _pacp.get("overall", "UNKNOWN") if isinstance(_pacp, dict) else "UNKNOWN"
    if pacp_overall not in _PACP_PASS_STATES:
        blocks.append(BLOCKED_PACP)

    # ── 3. EIV — fail-closed ──────────────────────────────────────────────────
    if eiv_result is None:
        eiv_result = _run_eiv_inline(candidate)
    eiv_overall = _extract_eiv_overall(eiv_result)
    if eiv_overall != "PASS":
        blocks.append(BLOCKED_EIV)

    # ── 4. Resolve state ──────────────────────────────────────────────────────
    if not blocks:
        state = HUMAN_REVIEW_ELIGIBLE
    elif len(blocks) == 1:
        state = blocks[0]
    else:
        state = BLOCKED_MULTIPLE

    return {
        "eligible": state == HUMAN_REVIEW_ELIGIBLE,
        "eligibility_state": state,
        "blocks": blocks,
        "pacp_overall": pacp_overall,
        "eiv_overall": eiv_overall,
        "artifact_identity_valid": artifact_identity_valid,
        # Invariant proof
        "_approval_registry_mutated": False,
        "_candidate_activated": False,
    }


def _run_eiv_inline(candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Run EIV on candidate's answer field. Returns None on import/runtime error."""
    try:
        from intelligence.external_investor_value_validator import (
            validate_management_answer_eiv,
            EIV_SCHEMA_VERSION,
        )
        answer = candidate.get("answer") or candidate
        result = validate_management_answer_eiv(answer)
        if result.get("schema_version") not in _EIV_SUPPORTED_SCHEMAS:
            return {"overall": "MISSING", "reason": "EIV_SCHEMA_VERSION_UNSUPPORTED"}
        return result
    except Exception as exc:
        return {"overall": "MISSING", "reason": f"EIV_RUNTIME_ERROR: {exc}"}


def _extract_eiv_overall(eiv_result: Optional[Dict[str, Any]]) -> str:
    """Extract EIV verdict. Fail-closed: missing/invalid → MISSING."""
    if eiv_result is None:
        return "MISSING"
    if not isinstance(eiv_result, dict):
        return "MISSING"
    overall = eiv_result.get("overall")
    if overall not in ("PASS", "FAIL", "WARN"):
        return "MISSING"
    return overall
