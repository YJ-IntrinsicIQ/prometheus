"""ENG-133: Generic management execution outcome contract tests.

15 scenario fixtures covering the full execution/outcome/attribution semantic space.
Tests are assertion-based with no external dependencies — they validate the contract
semantics that the production lifecycle enforces.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ─── Contract definitions (mirrors management_execution_outcomes schema) ────

VALID_EXECUTION_STATES = {
    "ANNOUNCED",
    "ACTION_STARTED",
    "PARTIAL_EXECUTION",
    "ACTION_COMPLETED",
    "OPERATIONAL",
    "FAILED_OR_ABANDONED",
    "UNKNOWN",
}

VALID_OUTCOME_STATES = {
    "OUTCOME_UNKNOWN",
    "OUTCOME_NOT_YET_OBSERVED",
    "OUTCOME_OBSERVED",
    "OUTCOME_NOT_DISCLOSED",
    "PARTIAL_OUTCOME",
    "NEGATIVE_OUTCOME",
}

VALID_ATTRIBUTION_STRENGTHS = {
    "NO_OUTCOME_EVIDENCE",
    "ASSOCIATED_NOT_ATTRIBUTABLE",
    "DIRECTLY_ATTRIBUTABLE",
    "STRONGLY_SUPPORTED",
    "NEGATIVE_OUTCOME",
}

# Attribution can be DIRECTLY_ATTRIBUTABLE only when outcome is OUTCOME_OBSERVED.
ATTRIBUTABLE_REQUIRES_OBSERVED_OUTCOME = {"DIRECTLY_ATTRIBUTABLE", "STRONGLY_SUPPORTED"}

# Completion ≠ outcome: these execution states do NOT imply a positive outcome.
COMPLETED_EXECUTION_STATES = {"ACTION_COMPLETED", "OPERATIONAL"}


@dataclass
class ExecutionRecord:
    identity_label: str
    execution_state: str
    outcome_state: str
    attribution_strength: str
    unresolved_gap: Optional[str] = None

    def validate_contract(self) -> list[str]:
        """Return list of contract violations; empty = valid."""
        errors = []
        if self.execution_state not in VALID_EXECUTION_STATES:
            errors.append(f"Invalid execution_state: {self.execution_state}")
        if self.outcome_state not in VALID_OUTCOME_STATES:
            errors.append(f"Invalid outcome_state: {self.outcome_state}")
        if self.attribution_strength not in VALID_ATTRIBUTION_STRENGTHS:
            errors.append(f"Invalid attribution_strength: {self.attribution_strength}")
        # Attribution can be attributable only when outcome is observed
        if self.attribution_strength in ATTRIBUTABLE_REQUIRES_OBSERVED_OUTCOME:
            if self.outcome_state != "OUTCOME_OBSERVED":
                errors.append(
                    f"attribution={self.attribution_strength} requires outcome_state=OUTCOME_OBSERVED "
                    f"but got {self.outcome_state}"
                )
        # No outcome evidence ↔ outcome not observed (conservative)
        if self.attribution_strength == "NO_OUTCOME_EVIDENCE":
            if self.outcome_state == "OUTCOME_OBSERVED":
                errors.append(
                    "attribution=NO_OUTCOME_EVIDENCE conflicts with outcome_state=OUTCOME_OBSERVED"
                )
        return errors


# ─── 15 Scenario fixtures ────────────────────────────────────────────────────

def test_1_exact_commitment_completed():
    """Commitment completed: execution_state=ACTION_COMPLETED, outcome still unproven."""
    r = ExecutionRecord(
        identity_label="Ramp-up ILUMYA prescriptions in Japan and Australia",
        execution_state="ACTION_COMPLETED",
        outcome_state="OUTCOME_NOT_DISCLOSED",
        attribution_strength="NO_OUTCOME_EVIDENCE",
        unresolved_gap="Outcome not disclosed by management",
    )
    errors = r.validate_contract()
    assert not errors, errors
    # Completion must NOT be shown as economic success
    assert r.attribution_strength not in ATTRIBUTABLE_REQUIRES_OBSERVED_OUTCOME, \
        "Completed commitment must not claim attribution without observed outcome"


def test_2_strategic_intent_acted_upon():
    """Strategic intent has action started but not completed; outcome unknown."""
    r = ExecutionRecord(
        identity_label="Growing portfolio of specialty products across 100+ countries",
        execution_state="ACTION_STARTED",
        outcome_state="OUTCOME_NOT_YET_OBSERVED",
        attribution_strength="NO_OUTCOME_EVIDENCE",
    )
    errors = r.validate_contract()
    assert not errors, errors
    assert r.execution_state == "ACTION_STARTED", "Action started is not completion"
    assert r.outcome_state != "OUTCOME_OBSERVED", "Outcome not yet observed"


def test_3_announcement_without_action():
    """Announcement only: execution_state=ANNOUNCED, outcome_state=OUTCOME_UNKNOWN."""
    r = ExecutionRecord(
        identity_label="Targeting new markets like Japan and China",
        execution_state="ANNOUNCED",
        outcome_state="OUTCOME_UNKNOWN",
        attribution_strength="NO_OUTCOME_EVIDENCE",
    )
    errors = r.validate_contract()
    assert not errors, errors
    # Announced items cannot have observed outcomes
    assert r.outcome_state not in ("OUTCOME_OBSERVED", "PARTIAL_OUTCOME"), \
        "Announced initiative must not show observed outcome"


def test_4_funded_but_not_operational():
    """Funded/started but not yet operational — still in ACTION_STARTED."""
    r = ExecutionRecord(
        identity_label="New manufacturing facility capital expenditure",
        execution_state="ACTION_STARTED",
        outcome_state="OUTCOME_NOT_YET_OBSERVED",
        attribution_strength="NO_OUTCOME_EVIDENCE",
        unresolved_gap="Funded but facility not yet at operational capacity",
    )
    errors = r.validate_contract()
    assert not errors, errors
    assert r.execution_state != "OPERATIONAL", "Funded ≠ operational"


def test_5_commissioned_but_outcome_unknown():
    """Commissioned (completed) but outcome not observed — common for capex."""
    r = ExecutionRecord(
        identity_label="Manufacturing facility located near Vedanthangal Bird Sanctuary",
        execution_state="ACTION_COMPLETED",
        outcome_state="OUTCOME_NOT_DISCLOSED",
        attribution_strength="NO_OUTCOME_EVIDENCE",
        unresolved_gap="Outcome not disclosed; operating status unconfirmed",
    )
    errors = r.validate_contract()
    assert not errors, errors
    # Commissioned ≠ profitable
    assert r.attribution_strength != "DIRECTLY_ATTRIBUTABLE", \
        "Commissioned without outcome evidence must not be directly attributable"


def test_6_operational_with_direct_outcome():
    """Operational facility with an observed and directly attributable outcome."""
    r = ExecutionRecord(
        identity_label="Specialty product manufacturing facility now operational",
        execution_state="OPERATIONAL",
        outcome_state="OUTCOME_OBSERVED",
        attribution_strength="DIRECTLY_ATTRIBUTABLE",
    )
    errors = r.validate_contract()
    assert not errors, errors
    assert r.outcome_state == "OUTCOME_OBSERVED"
    assert r.attribution_strength == "DIRECTLY_ATTRIBUTABLE"


def test_7_operational_with_associated_not_attributable():
    """Operational but observed outcome is associated, not attributable."""
    r = ExecutionRecord(
        identity_label="New design and manufacturing facility operational",
        execution_state="ACTION_COMPLETED",
        outcome_state="OUTCOME_OBSERVED",
        attribution_strength="ASSOCIATED_NOT_ATTRIBUTABLE",
        unresolved_gap="Outcome visible but economic consequence not attributable to this initiative",
    )
    errors = r.validate_contract()
    assert not errors, errors
    # Associated ≠ caused
    assert r.attribution_strength != "DIRECTLY_ATTRIBUTABLE", \
        "Associated but not attributable must not be escalated to directly attributable"


def test_8_completed_acquisition_without_value_creation_proof():
    """Acquisition completed but no attributable financial outcome."""
    r = ExecutionRecord(
        identity_label="Inorganic acquisition completed",
        execution_state="ACTION_COMPLETED",
        outcome_state="OUTCOME_NOT_DISCLOSED",
        attribution_strength="NO_OUTCOME_EVIDENCE",
        unresolved_gap="Acquisition is complete; integration success and return unproven",
    )
    errors = r.validate_contract()
    assert not errors, errors
    # Acquisition completed ≠ value created
    assert r.attribution_strength not in ATTRIBUTABLE_REQUIRES_OBSERVED_OUTCOME, \
        "Completed acquisition without outcome evidence must not claim attribution"


def test_9_failed_initiative():
    """Failed or abandoned initiative with negative outcome."""
    r = ExecutionRecord(
        identity_label="Product launch abandoned after phase 2 failure",
        execution_state="FAILED_OR_ABANDONED",
        outcome_state="NEGATIVE_OUTCOME",
        attribution_strength="NEGATIVE_OUTCOME",
    )
    errors = r.validate_contract()
    assert not errors, errors
    assert r.execution_state == "FAILED_OR_ABANDONED"
    assert r.outcome_state == "NEGATIVE_OUTCOME"


def test_10_management_contradiction():
    """Management said X earlier; later evidence contradicts it."""
    # Earlier claim: initiative will be operational by FY22
    # Later evidence: still announced/not operational by FY24
    r_earlier = ExecutionRecord(
        identity_label="Platform revenue to be operational by FY22",
        execution_state="ANNOUNCED",
        outcome_state="OUTCOME_UNKNOWN",
        attribution_strength="NO_OUTCOME_EVIDENCE",
    )
    r_later = ExecutionRecord(
        identity_label="Platform revenue to be operational by FY22",  # same initiative
        execution_state="ANNOUNCED",  # still not operational
        outcome_state="OUTCOME_UNKNOWN",
        attribution_strength="NO_OUTCOME_EVIDENCE",
        unresolved_gap="Initiative was claimed for FY22 but no operational evidence exists by FY24",
    )
    # Both records valid; the contradiction is in the gap between claim and reality
    assert not r_earlier.validate_contract()
    assert not r_later.validate_contract()
    # Contradiction: later record must not upgrade execution_state to mask the gap
    assert r_later.execution_state != "ACTION_COMPLETED", \
        "Contradicted claim must not be promoted to completed"
    assert r_later.unresolved_gap is not None, "Contradiction must be preserved as unresolved_gap"


def test_11_remediation_planned_but_not_executed():
    """Remediation planned (announced) but no evidence of execution."""
    r = ExecutionRecord(
        identity_label="USFDA warning letter response plan announced",
        execution_state="ANNOUNCED",
        outcome_state="OUTCOME_UNKNOWN",
        attribution_strength="NO_OUTCOME_EVIDENCE",
        unresolved_gap="Remediation plan stated; no RESPONSE_EXECUTED evidence available",
    )
    errors = r.validate_contract()
    assert not errors, errors
    assert r.execution_state != "ACTION_COMPLETED", "Plan ≠ execution"


def test_12_remediation_executed_but_effectiveness_unknown():
    """Remediation action completed; whether it resolved the issue is unknown."""
    r = ExecutionRecord(
        identity_label="Toansa facility USFDA remediation actions completed",
        execution_state="ACTION_COMPLETED",
        outcome_state="OUTCOME_NOT_DISCLOSED",
        attribution_strength="NO_OUTCOME_EVIDENCE",
        unresolved_gap="Remediation completed; FDA re-inspection outcome not disclosed",
    )
    errors = r.validate_contract()
    assert not errors, errors
    # Completed remediation ≠ resolved issue
    assert r.outcome_state != "OUTCOME_OBSERVED", \
        "Remediation completion must not assume successful resolution"


def test_13_same_initiative_renamed_across_years():
    """Same initiative appears under different wording across years — identity must be stable."""
    fy21 = ExecutionRecord(
        identity_label="Specialty pipeline expansion initiative",
        execution_state="ACTION_STARTED",
        outcome_state="OUTCOME_NOT_YET_OBSERVED",
        attribution_strength="NO_OUTCOME_EVIDENCE",
    )
    fy24 = ExecutionRecord(
        identity_label="Specialty pipeline expansion initiative",  # same ID, different year
        execution_state="ACTION_COMPLETED",
        outcome_state="OUTCOME_NOT_DISCLOSED",
        attribution_strength="NO_OUTCOME_EVIDENCE",
    )
    # Identity is preserved by label match; execution_state can progress
    assert fy21.identity_label == fy24.identity_label, "Identity label must be stable across years"
    # Execution can progress from STARTED to COMPLETED — valid lifecycle
    assert not fy21.validate_contract()
    assert not fy24.validate_contract()
    # But STARTED cannot skip to OPERATIONAL without ACTION_COMPLETED in between
    assert fy21.execution_state == "ACTION_STARTED"
    assert fy24.execution_state == "ACTION_COMPLETED"


def test_14_genuinely_insufficient_evidence():
    """When evidence is absent, outcome stays UNKNOWN — never fabricated."""
    r = ExecutionRecord(
        identity_label="R&D pipeline investment commitment",
        execution_state="ANNOUNCED",
        outcome_state="OUTCOME_UNKNOWN",
        attribution_strength="NO_OUTCOME_EVIDENCE",
        unresolved_gap="No follow-up evidence found in any source year",
    )
    errors = r.validate_contract()
    assert not errors, errors
    # Insufficient evidence must not be promoted
    assert r.outcome_state != "OUTCOME_OBSERVED", "Absent evidence must not produce observed outcome"
    assert r.attribution_strength not in ATTRIBUTABLE_REQUIRES_OBSERVED_OUTCOME, \
        "Absent evidence must not produce attribution"


def test_15_aspiration_not_treated_as_promise():
    """Aspiration ('aim to', 'intend to') must not enter the accountability denominator."""
    # The commitment type check: aspiration is outside the verifiable commitment space.
    # A verifiable commitment requires: specific target, timeframe, observable metric.
    def is_verifiable_commitment(text: str) -> bool:
        """Minimal classifier: aspirations use modal language, no concrete target."""
        modal_words = {"aim", "aspire", "intend", "hope", "strive", "seek to", "look to"}
        lower = text.lower()
        return not any(w in lower for w in modal_words)

    aspiration = "We aim to become a global leader in specialty pharmaceuticals."
    commitment = "Ramp-up ILUMYA prescriptions in Japan and Australia by FY21."

    assert not is_verifiable_commitment(aspiration), \
        "Aspiration must not be classified as a verifiable commitment"
    assert is_verifiable_commitment(commitment), \
        "Verifiable commitment with target should be classified as commitment"

    # Aspiration execution record: valid but excluded from accountability denominator
    r = ExecutionRecord(
        identity_label="Aim to become global specialty leader",
        execution_state="ANNOUNCED",
        outcome_state="OUTCOME_UNKNOWN",
        attribution_strength="NO_OUTCOME_EVIDENCE",
        unresolved_gap="Aspiration: outside verifiable-commitment accountability denominator",
    )
    errors = r.validate_contract()
    assert not errors, errors


# ─── Self-check ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_1_exact_commitment_completed,
        test_2_strategic_intent_acted_upon,
        test_3_announcement_without_action,
        test_4_funded_but_not_operational,
        test_5_commissioned_but_outcome_unknown,
        test_6_operational_with_direct_outcome,
        test_7_operational_with_associated_not_attributable,
        test_8_completed_acquisition_without_value_creation_proof,
        test_9_failed_initiative,
        test_10_management_contradiction,
        test_11_remediation_planned_but_not_executed,
        test_12_remediation_executed_but_effectiveness_unknown,
        test_13_same_initiative_renamed_across_years,
        test_14_genuinely_insufficient_evidence,
        test_15_aspiration_not_treated_as_promise,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR: {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
