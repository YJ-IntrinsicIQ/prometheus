"""P1A classifier tests — generic, no company- or sector-specific terms.

Covers:
- Statement-type classifier: gerund, imperative, implicit-subject, explicit,
  target, guidance, generic_aspiration, historical, external, non-investor
- build_semantic_quality outcome → eligibility mapping (DEMOTE, QUARANTINE, HARD_FAIL)
- ELIGIBLE_COMMITMENT_STATEMENTS and QUARANTINE_REASON_CODES constants
- End-to-end ManagementCommitmentsBuilder acceptance for rescued forms
"""
import json
from pathlib import Path

import pytest

from knowledge.company_memory import ManagementCommitmentsBuilder
from knowledge.company_memory.guardrails import (
    ELIGIBLE_COMMITMENT_STATEMENTS,
    QUARANTINE_REASON_CODES,
    build_semantic_quality,
    classify_statement_type,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _sq(outcome: str, *, commitment_eligible: bool = False) -> dict:
    """Minimal build_semantic_quality call with a given four-outcome result."""
    return build_semantic_quality(
        classification="company_management",
        relevance={"outcome": outcome, "status": "core", "limitations": []},
        period={"status": "RESOLVED"},
        materiality={"level": "high", "basis": [], "should_promote": True},
        commitment_eligible=commitment_eligible,
    )


def _stmt(text: str, **kw) -> dict:
    return classify_statement_type(text, **kw)


def _write_item(base: Path, company: str, year: str, items: list) -> None:
    d = base / "companies" / company / year / "intelligence"
    d.mkdir(parents=True, exist_ok=True)
    (d / "company_intelligence.json").write_text(
        json.dumps({"management": {"promises": {"items": items}}}), encoding="utf-8"
    )
    (d / "management_summary.json").write_text(
        json.dumps({"major_promises": []}), encoding="utf-8"
    )


def _load(base: Path, company: str) -> dict:
    out = base / "companies" / company / "company_memory" / "management_commitments"
    return {
        "commitments": json.loads((out / "management_commitments.json").read_text()),
        "validation": json.loads((out / "commitment_validation.json").read_text()),
        "manifest": json.loads((out / "management_commitments_manifest.json").read_text()),
    }


# ── 1. ELIGIBLE_COMMITMENT_STATEMENTS includes future_action ─────────────────

def test_eligible_set_includes_future_action():
    assert "future_action" in ELIGIBLE_COMMITMENT_STATEMENTS


def test_eligible_set_core_types_present():
    for t in ("explicit_commitment", "target", "guidance", "strategic_priority", "planned_action"):
        assert t in ELIGIBLE_COMMITMENT_STATEMENTS, f"missing: {t}"


# ── 2. QUARANTINE_REASON_CODES completeness ───────────────────────────────────

def test_quarantine_reason_codes_contains_expected():
    expected = {
        "EXTERNAL_ACTOR", "NOT_FUTURE_ORIENTED", "NO_ACTIONABLE_INTENT",
        "GENERIC_ASPIRATION", "HISTORICAL_FACT", "NON_INVESTOR_MATERIAL",
        "AMBIGUOUS_ACTOR", "UNCLASSIFIED_STATEMENT", "OTHER",
    }
    assert expected <= QUARANTINE_REASON_CODES


# ── 3. Gerund form with specific object → future_action ──────────────────────

def test_gerund_with_specific_object_is_future_action():
    result = _stmt("Expanding the distribution network across ten new regions by FY26.")
    assert result["statement_type"] == "future_action"
    assert result["future_orientation"] is True
    assert result["actionability"] == "specific"


def test_gerund_with_trackable_noun_is_future_action():
    # "platform" is a trackable noun; FY target also triggers specific-object detection
    result = _stmt("Deploying a new distribution platform across all regions by FY25.")
    assert result["statement_type"] == "future_action"
    assert result["future_orientation"] is True


# ── 4. Gerund form without specific object → strategic_priority ───────────────

def test_gerund_without_specific_object_is_strategic_priority():
    result = _stmt("Strengthening our competitive position in the core business.")
    assert result["statement_type"] == "strategic_priority"
    assert result["future_orientation"] is True
    assert result["actionability"] == "directional"


# ── 5. Imperative form with specific object → future_action ──────────────────

def test_imperative_with_specific_object_is_future_action():
    # "build" matches imperative prefix; "manufacturing facilities" is a trackable
    # noun and "FY25" satisfies the FY-target check → future_action/specific
    result = _stmt("Build three additional manufacturing facilities by FY25.")
    assert result["statement_type"] == "future_action"
    assert result["future_orientation"] is True
    assert result["actionability"] == "specific"


# ── 6. Imperative form without specific object → strategic_priority ───────────

def test_imperative_without_specific_object_is_strategic_priority():
    # "improve" matches imperative prefix; no trackable noun, no FY target,
    # no numeric quantity → directional/strategic_priority
    result = _stmt("Improve overall performance and reduce operating costs.")
    assert result["statement_type"] == "strategic_priority"
    assert result["future_orientation"] is True


# ── 7. Implicit subject with "plan to" → planned_action ──────────────────────

def test_implicit_subject_plan_to_is_planned_action():
    result = _stmt("We plan to enter the European market.")
    assert result["statement_type"] == "planned_action"
    assert result["future_orientation"] is True


# ── 8. Explicit commitment language ──────────────────────────────────────────

def test_explicit_commitment_keyword():
    result = _stmt("We commit to achieving net-zero emissions by 2040.")
    assert result["statement_type"] == "explicit_commitment"
    assert result["future_orientation"] is True
    assert result["actionability"] == "specific"


# ── 9. Target statement ───────────────────────────────────────────────────────

def test_target_statement_classified_as_target():
    result = _stmt("We are targeting revenue growth of 15% for the next fiscal year.")
    assert result["statement_type"] == "target"
    assert result["future_orientation"] is True


# ── 10. Generic aspiration → excluded type ───────────────────────────────────

def test_generic_aspiration_not_eligible():
    result = _stmt("We remain committed to excellence and creating shareholder value.")
    assert result["statement_type"] == "generic_aspiration"
    assert result["statement_type"] not in ELIGIBLE_COMMITMENT_STATEMENTS


# ── 11. Historical fact → not future-oriented ────────────────────────────────

def test_historical_fact_not_future_oriented():
    result = _stmt("During the year, revenue stood at record levels.")
    assert result["statement_type"] == "historical_fact"
    assert result["future_orientation"] is False


# ── 12. External / government statement → external_statement ─────────────────

def test_government_objective_classified_as_external():
    result = _stmt("The government aims to increase defence production of aerospace parts.")
    assert result["statement_type"] == "external_statement"
    assert result["future_orientation"] is False


# ── 13. Non-investor material → non_investor_material ───────────────────────

def test_pension_mechanics_classified_as_non_investor_material():
    result = _stmt("Contributions to the gratuity fund are made on the basis of actuarial valuation.")
    assert result["statement_type"] == "non_investor_material"
    assert result["statement_type"] not in ELIGIBLE_COMMITMENT_STATEMENTS


# ── 14. build_semantic_quality: KEEP → eligible ──────────────────────────────

def test_quality_keep_is_always_eligible():
    assert _sq("KEEP")["eligibility"] == "eligible"
    assert _sq("KEEP", commitment_eligible=True)["eligibility"] == "eligible"


# ── 15. build_semantic_quality: DEMOTE + commitment_eligible=True → eligible ──

def test_quality_demote_eligible_when_genuine_commitment():
    assert _sq("DEMOTE", commitment_eligible=True)["eligibility"] == "eligible"


def test_quality_demote_quarantined_when_not_commitment():
    assert _sq("DEMOTE", commitment_eligible=False)["eligibility"] == "quarantined"


# ── 16. build_semantic_quality: QUARANTINE + commitment_eligible=True → eligible

def test_quality_quarantine_eligible_when_genuine_commitment():
    assert _sq("QUARANTINE", commitment_eligible=True)["eligibility"] == "eligible"


def test_quality_quarantine_quarantined_when_not_commitment():
    assert _sq("QUARANTINE", commitment_eligible=False)["eligibility"] == "quarantined"


# ── 17. build_semantic_quality: HARD_FAIL always excluded ─────────────────────

def test_quality_hard_fail_always_excluded():
    assert _sq("HARD_FAIL", commitment_eligible=True)["eligibility"] == "excluded"
    assert _sq("HARD_FAIL", commitment_eligible=False)["eligibility"] == "excluded"


# ── 18. End-to-end: gerund commitment rescued and captured ────────────────────

def test_end_to_end_gerund_commitment_captured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_item(tmp_path, "alpha", "fy24", [
        {
            "id": "G1",
            "promise": "Expanding the network of distribution centres by FY25.",
            "category": "Logistics",
            "page": 3,
            "source_chunk": "Expanding distribution centres by FY25.",
        }
    ])
    ManagementCommitmentsBuilder(company="alpha").build()
    out = _load(tmp_path, "alpha")
    assert out["commitments"]["commitment_count"] >= 1


# ── 19. End-to-end: generic aspiration excluded ───────────────────────────────

def test_end_to_end_generic_aspiration_excluded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_item(tmp_path, "beta", "fy24", [
        {
            "id": "A1",
            "promise": "We remain committed to excellence and creating long-term value.",
            "category": "General",
            "page": 1,
            "source_chunk": "Committed to excellence.",
        }
    ])
    ManagementCommitmentsBuilder(company="beta").build()
    out = _load(tmp_path, "beta")
    assert out["commitments"]["commitment_count"] == 0


# ── 20. End-to-end: quarantine_reason always populated when quarantined ───────

def test_end_to_end_quarantine_reason_always_populated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_item(tmp_path, "gamma", "fy24", [
        {
            "id": "Q1",
            "promise": "We remain committed to excellence.",
            "category": "General",
            "page": 1,
            "source_chunk": "Committed to excellence.",
        }
    ])
    ManagementCommitmentsBuilder(company="gamma").build()
    out = _load(tmp_path, "gamma")
    q_candidates = out["commitments"].get("quarantined_candidates", [])
    for qc in q_candidates:
        reason = qc.get("quarantine_reason", "")
        assert reason, f"quarantine_reason missing for candidate: {qc.get('text')}"
        assert reason in QUARANTINE_REASON_CODES, f"unknown quarantine_reason: {reason}"


# ── 21. End-to-end: imperative commitment with FY target rescued ──────────────

def test_end_to_end_imperative_with_fy_target_captured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_item(tmp_path, "delta", "fy23", [
        {
            "id": "I1",
            "promise": "Launch the next-generation product line by FY24.",
            "category": "Product",
            "page": 7,
            "source_chunk": "Launch next-generation product line by FY24.",
        }
    ])
    ManagementCommitmentsBuilder(company="delta").build()
    out = _load(tmp_path, "delta")
    assert out["commitments"]["commitment_count"] >= 1


# ── 22. No pharma or sector-specific terms required for admission ──────────────

def test_admission_requires_no_sector_specific_terms():
    """Commitment classifier must work for banking, technology, consumer, etc."""
    generic_commitments = [
        "We will open five new branches in the eastern region.",      # banking
        "Deploying the cloud migration for all core systems by Q3.",  # technology
        "We plan to launch two new product SKUs in the next quarter.",# consumer
        "Commissioning a second data centre by FY26.",               # infra
        "We intend to acquire controlling interest in the target.",   # M&A
    ]
    for text in generic_commitments:
        result = _stmt(text)
        assert result["statement_type"] in ELIGIBLE_COMMITMENT_STATEMENTS, (
            f"Expected eligible type for: {text!r}, got: {result['statement_type']}"
        )


# ── 23. No sector-specific hard-excludes in classifier ────────────────────────

def test_classifier_does_not_hardcode_pharma_terms():
    """Manufacturing/pharma vocabulary should not trigger blanket exclusion."""
    pharma_adjacent = [
        "We plan to commission a new API manufacturing facility.",
        "Expanding production capacity at the formulation plant.",
        "We intend to file regulatory submissions for three new products.",
    ]
    for text in pharma_adjacent:
        result = _stmt(text)
        assert result["statement_type"] in ELIGIBLE_COMMITMENT_STATEMENTS, (
            f"Pharma-adjacent text incorrectly excluded: {text!r} → {result['statement_type']}"
        )
