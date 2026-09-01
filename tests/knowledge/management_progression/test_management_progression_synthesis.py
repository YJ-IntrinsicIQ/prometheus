"""
Regression tests for the Management Synthesis Layer.

Tests cover all required scenario types:
 1. claim → action → successful outcome
 2. claim with no later action (CLAIM_ONLY)
 3. action completed but economic impact unknown
 4. action followed by negative outcome
 5. financial improvement exists but causal link is unsupported (FINANCIAL_LINK_UNPROVEN)
 6. explicit financial consequence with supporting evidence (FINANCIAL_IMPACT_CONFIRMED)
 7. conflicting management evidence
 8. multiple years linking the same initiative
 9. no company/year hardcoding

No real company data is used; all fixtures are synthetic and company-agnostic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge.management_progression import (
    CHAIN_STATUSES,
    CHAIN_STATUS_ACTION_COMPLETED,
    CHAIN_STATUS_ACTION_STARTED,
    CHAIN_STATUS_CLAIM_ONLY,
    CHAIN_STATUS_EARLY_OPERATING_SIGNAL,
    CHAIN_STATUS_FINANCIAL_IMPACT_CONFIRMED,
    CHAIN_STATUS_FINANCIAL_IMPACT_NOT_YET_VISIBLE,
    CHAIN_STATUS_FINANCIAL_LINK_UNPROVEN,
    CHAIN_STATUS_OUTCOME_MIXED,
    CHAIN_STATUS_OUTCOME_NEGATIVE,
    CHAIN_STATUS_OUTCOME_POSITIVE,
    CHAIN_STATUS_OUTCOME_UNKNOWN,
    CHAIN_STATUS_PARTIAL_EXECUTION,
    FINANCIAL_LINK_CONFIRMED,
    FINANCIAL_LINK_NOT_YET_VISIBLE,
    FINANCIAL_LINK_UNPROVEN,
    build_management_progression,
    build_synthesis_chain,
    validate_management_progression,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _series(*entries) -> list:
    """Build a metric_series list from (year, value) pairs."""
    return [
        {"year": y, "value": v, "unit": "INR crore", "basis": "consolidated", "confidence": "high"}
        for y, v in entries
    ]


def _item(events: list, theme: str = "Generic theme for test") -> dict:
    return {"theme": theme, "events": events}


def _ev(*, role: str, period: str, statement_text: str = "", action_taken: str = "",
         operational_outcome: str = "", financial_or_business_outcome: str = "",
         verification_status: str = "unresolved", evidence: list | None = None,
         actor: str = "management") -> dict:
    return {
        "event_id": f"ev_{role}_{period}",
        "role": role,
        "event_type": "project_execution",
        "source_period": period,
        "event_period": period,
        "actor": actor,
        "statement_text": statement_text,
        "action_taken": action_taken,
        "operational_outcome": operational_outcome,
        "financial_or_business_outcome": financial_or_business_outcome,
        "verification_status": verification_status,
        "confidence": {"level": "medium", "basis": ["test"], "limitations": []},
        "evidence": evidence or [],
    }


# ---------------------------------------------------------------------------
# Test 1: claim → action → successful outcome (OUTCOME_POSITIVE)
# ---------------------------------------------------------------------------


def test_claim_action_successful_outcome():
    """Full chain: commitment → action → positive operational outcome."""
    item = _item(
        theme="New manufacturing facility expansion",
        events=[
            _ev(role="commitment", period="fy22",
                statement_text="Management committed to expand manufacturing facility by FY24."),
            _ev(role="action", period="fy23",
                action_taken="Construction of manufacturing facility commenced in fy23.",
                verification_status="partially_verified"),
            _ev(role="completion", period="fy24",
                action_taken="Manufacturing facility commissioned in fy24.",
                operational_outcome="Facility commissioned and utilization rose to 80%.",
                verification_status="verified"),
        ],
    )
    chain = build_synthesis_chain(item, {})

    assert chain["chain_status"] == CHAIN_STATUS_OUTCOME_POSITIVE
    assert chain["claim"] is not None
    assert chain["action"] is not None
    assert chain["action"]["completed"] is True
    assert chain["outcome"] is not None
    assert chain["outcome"]["direction"] == "positive"
    assert chain["financial_consequence"]["link_status"] == FINANCIAL_LINK_NOT_YET_VISIBLE
    assert chain["investor_implication"]["confidence"] == "medium"
    assert "economic" in chain["investor_implication"]["conclusion"].lower() or \
           "financial" in chain["investor_implication"]["conclusion"].lower()


# ---------------------------------------------------------------------------
# Test 2: claim with no later action (CLAIM_ONLY)
# ---------------------------------------------------------------------------


def test_claim_only_no_action():
    """Commitment with no subsequent action evidence → CLAIM_ONLY."""
    item = _item(
        theme="Platform rollout commitment",
        events=[
            _ev(role="commitment", period="fy23",
                statement_text="Focus on rolling out enterprise platform across regions."),
        ],
    )
    chain = build_synthesis_chain(item, {})

    assert chain["chain_status"] == CHAIN_STATUS_CLAIM_ONLY
    assert chain["claim"] is not None
    assert chain["action"] is None
    assert chain["outcome"] is None
    assert "no evidence of action" in chain["investor_implication"]["conclusion"].lower() or \
           "commitment" in chain["investor_implication"]["conclusion"].lower()
    assert chain["investor_implication"]["confidence"] == "low"


# ---------------------------------------------------------------------------
# Test 3: action completed but economic impact unknown (ACTION_COMPLETED / NOT_YET_VISIBLE)
# ---------------------------------------------------------------------------


def test_action_completed_economic_impact_unknown():
    """Completion event with no financial trace → economic impact not yet visible."""
    item = _item(
        theme="Satellite integration testing facility",
        events=[
            _ev(role="completion", period="fy24",
                action_taken="Satellite integration testing facility commissioned.",
                operational_outcome="Commissioning is visible, but utilization is not yet proven.",
                verification_status="verified"),
        ],
    )
    # Metric series has no revenue or capex after fy24 (most recent year is fy24)
    metric_series = {
        "revenue": _series(("fy22", 1000), ("fy23", 1100), ("fy24", 1200)),
    }
    chain = build_synthesis_chain(item, metric_series)

    assert chain["financial_consequence"]["link_status"] == FINANCIAL_LINK_NOT_YET_VISIBLE
    assert chain["chain_status"] == CHAIN_STATUS_ACTION_COMPLETED
    assert chain["action"] is not None
    assert chain["action"]["completed"] is True
    assert chain["outcome"] is None


# ---------------------------------------------------------------------------
# Test 4: action followed by negative outcome (OUTCOME_NEGATIVE)
# ---------------------------------------------------------------------------


def test_action_followed_by_negative_outcome():
    """Action followed by regulatory failure → OUTCOME_NEGATIVE."""
    item = _item(
        theme="Regulatory compliance remediation",
        events=[
            _ev(role="commitment", period="fy19",
                statement_text="Management committed to address USFDA observations at the facility."),
            _ev(role="action", period="fy19",
                action_taken="Corrective actions submitted to USFDA.",
                verification_status="partially_verified"),
            _ev(role="outcome", period="fy20",
                operational_outcome="USFDA issued import alert; facility operations restricted.",
                financial_or_business_outcome="Revenue from US market declined following import alert."),
        ],
    )
    chain = build_synthesis_chain(item, {})

    assert chain["chain_status"] == CHAIN_STATUS_OUTCOME_NEGATIVE
    assert chain["outcome"] is not None
    assert chain["outcome"]["direction"] == "negative"
    assert chain["investor_implication"]["confidence"] == "medium"
    assert "weaken" in chain["investor_implication"]["conclusion"].lower() or \
           "negative" in chain["investor_implication"]["conclusion"].lower()


# ---------------------------------------------------------------------------
# Test 5: financial improvement exists but causal link is unsupported (FINANCIAL_LINK_UNPROVEN)
# ---------------------------------------------------------------------------


def test_financial_improvement_but_causal_link_unproven():
    """
    Revenue grew after the action period, and revenue is mentioned in the item text,
    but no evidence establishes that the action caused the revenue growth.
    Distinct stages: action (fy22) + outcome (fy23) + financial_trends showing revenue growth.
    """
    item = _item(
        theme="New revenue stream through digital platform expansion",
        events=[
            _ev(role="action", period="fy22",
                action_taken="Digital platform expanded to new customer segments."),
            _ev(role="outcome", period="fy23",
                operational_outcome="Platform adoption improved across target segments.",
                financial_or_business_outcome="Revenue impact remains unproven at this stage."),
        ],
    )
    metric_series = {
        "revenue": _series(("fy21", 500), ("fy22", 520), ("fy23", 590), ("fy24", 650)),
    }
    chain = build_synthesis_chain(item, metric_series)

    assert chain["financial_consequence"]["link_status"] == FINANCIAL_LINK_UNPROVEN
    assert chain["chain_status"] == CHAIN_STATUS_FINANCIAL_LINK_UNPROVEN
    rev_obs = [m for m in chain["financial_consequence"]["metrics_observed"] if m["metric_id"] == "revenue"]
    assert rev_obs, "revenue should appear in metrics_observed since it's mentioned in the theme"
    assert rev_obs[0]["causal_link"] == "not_established"
    assert "causal link" in chain["investor_implication"]["conclusion"].lower()


# ---------------------------------------------------------------------------
# Test 6: explicit financial consequence with supporting evidence (FINANCIAL_IMPACT_CONFIRMED)
# ---------------------------------------------------------------------------


def test_explicit_financial_consequence_confirmed():
    """
    Outcome text explicitly states a specific metric and a numeric value;
    that metric moved in financial_trends → FINANCIAL_IMPACT_CONFIRMED.
    """
    item = _item(
        theme="Capex investment in manufacturing capacity",
        events=[
            _ev(role="commitment", period="fy22",
                statement_text="Management committed 500 crore capex for new manufacturing line."),
            _ev(role="completion", period="fy23",
                action_taken="500 crore capex deployed in manufacturing line.",
                operational_outcome="New manufacturing line commissioned.",
                financial_or_business_outcome="Capex of 500 crore deployed; fixed assets increased by 480 crore.",
                verification_status="verified"),
        ],
    )
    # capex metric moved after fy22 (action/completion period is fy23 in the action event)
    # The outcome text mentions "capex" and "480 crore" → confirmed
    metric_series = {
        "capex": _series(("fy21", 200), ("fy22", 300), ("fy23", 500), ("fy24", 520)),
    }
    chain = build_synthesis_chain(item, metric_series)

    assert chain["financial_consequence"]["link_status"] == FINANCIAL_LINK_CONFIRMED
    assert chain["chain_status"] == CHAIN_STATUS_FINANCIAL_IMPACT_CONFIRMED
    assert chain["investor_implication"]["confidence"] == "high"
    assert "evidence" in chain["investor_implication"]["conclusion"].lower()


# ---------------------------------------------------------------------------
# Test 7: conflicting management evidence
# ---------------------------------------------------------------------------


def test_conflicting_management_evidence():
    """
    Statement says one thing; outcome contradicts it → OUTCOME_MIXED or OUTCOME_NEGATIVE.
    The synthesis should not collapse the contradiction into a positive.
    """
    item = _item(
        theme="Market share expansion commitment",
        events=[
            _ev(role="commitment", period="fy22",
                statement_text="Management committed to grow market share in specialty segment."),
            _ev(role="action", period="fy22",
                action_taken="Increased marketing spend in specialty segment."),
            _ev(role="outcome", period="fy23",
                operational_outcome=(
                    "Some growth achieved in specialty segment, but competitors also expanded;"
                    " net market share impact is mixed and challenged."
                )),
        ],
    )
    chain = build_synthesis_chain(item, {})

    assert chain["chain_status"] in {CHAIN_STATUS_OUTCOME_MIXED, CHAIN_STATUS_OUTCOME_NEGATIVE}
    # Claim should still be preserved
    assert chain["claim"] is not None
    # The outcome should not be presented as fully positive
    assert chain["outcome"]["direction"] in {"mixed", "negative"}


# ---------------------------------------------------------------------------
# Test 8: multiple years linking the same initiative
# ---------------------------------------------------------------------------


def test_multiple_years_same_initiative():
    """
    Multi-year chain: commitment (fy21) → action (fy22) → milestone (fy23) → completion (fy24).
    All events should be collected; chain should reflect the latest (most advanced) state.
    """
    item = _item(
        theme="Digital loan origination platform rollout",
        events=[
            _ev(role="commitment", period="fy21",
                statement_text="Launch digital loan origination platform by FY24."),
            _ev(role="action", period="fy22",
                action_taken="Development of digital loan origination system commenced."),
            _ev(role="milestone", period="fy23",
                action_taken="Pilot of digital loan origination system launched with select branches."),
            _ev(role="completion", period="fy24",
                action_taken="Digital loan origination platform rolled out across all branches.",
                operational_outcome="End-to-end digital origination achieved; processing time reduced.",
                verification_status="verified"),
        ],
    )
    metric_series = {
        "revenue": _series(("fy21", 200), ("fy22", 250), ("fy23", 310), ("fy24", 380), ("fy25", 450)),
    }
    chain = build_synthesis_chain(item, metric_series)

    # claim from fy21
    assert chain["claim"] is not None
    assert chain["claim"]["period"] == "fy21"

    # action should be the completion (most definitive)
    assert chain["action"] is not None
    assert chain["action"]["completed"] is True

    # outcome positive (processing time reduced, digital achieved)
    assert chain["outcome"] is not None

    # Revenue is mentioned nowhere in the events text so metrics_observed may be empty,
    # making chain_status OUTCOME_POSITIVE or FINANCIAL_IMPACT_NOT_YET_VISIBLE
    assert chain["chain_status"] in {
        CHAIN_STATUS_OUTCOME_POSITIVE,
        CHAIN_STATUS_FINANCIAL_LINK_UNPROVEN,
        CHAIN_STATUS_FINANCIAL_IMPACT_NOT_YET_VISIBLE,
    }


# ---------------------------------------------------------------------------
# Test 9: no company/year hardcoding — same logic across multiple companies
# ---------------------------------------------------------------------------


def test_no_company_year_hardcoding():
    """
    The same event structure should produce the same chain_status regardless of
    which company name or which fiscal years are used.
    """
    configs = [
        ("alphaco", "fy21", "fy22"),
        ("betaco", "fy24", "fy25"),
        ("gammaco", "fy19", "fy20"),
        ("widgetco", "fy18", "fy19"),
    ]
    for _company, claim_yr, action_yr in configs:
        item = _item(
            theme=f"Manufacturing platform expansion project",
            events=[
                _ev(role="commitment", period=claim_yr,
                    statement_text="Commit to expanding manufacturing platform."),
                _ev(role="action", period=action_yr,
                    action_taken="Manufacturing platform construction commenced."),
            ],
        )
        chain = build_synthesis_chain(item, {})
        assert chain["chain_status"] == CHAIN_STATUS_ACTION_STARTED, (
            f"Expected ACTION_STARTED for {_company} {claim_yr}→{action_yr},"
            f" got {chain['chain_status']}"
        )
        assert chain["claim"]["period"] == claim_yr
        assert chain["action"]["completed"] is False


# ---------------------------------------------------------------------------
# Integration: synthesis_chain survives validate_management_progression
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _company_model(company: str) -> dict:
    return {
        "schema_version": "company_model.v1",
        "company_slug": company,
        "coverage_status": "supported",
        "offerings": [{"offering_id": "platform", "name": "Enterprise platform", "description": "Messaging platform"}],
        "revenue_engines": [{"engine_id": "usage", "description": "Usage-linked revenue"}],
        "source_manifest": {"company_slug": company},
    }


def test_synthesis_chain_in_full_pipeline_passes_validation(tmp_path: Path):
    """
    End-to-end: a project with financial_trends available produces a synthesis_chain
    that passes validate_management_progression without errors.
    """
    company = "synthco"
    _write_json(
        tmp_path / "companies" / company / "company_memory" / "company_model" / "company_model.json",
        _company_model(company),
    )
    _write_json(
        tmp_path / "companies" / company / "company_memory" / "projects" / "projects_registry.json",
        {
            "company": company,
            "projects": [
                {
                    "project_id": "PJ-SYNTH",
                    "project_name": "Manufacturing facility for industrial customers",
                    "description": "Manufacturing facility for industrial customers",
                    "announcement_period": "fy22",
                    "assessment": {
                        "execution_status": "commissioned",
                        "observed_business_effect": "Facility commissioned; customer delivery improved.",
                        "observed_financial_effect": "Revenue from industrial segment grew.",
                    },
                    "evidence_ids": ["ev_synth_1"],
                }
            ],
        },
    )
    _write_json(
        tmp_path / "companies" / company / "company_memory" / "financials" / "financial_trends.json",
        {
            "company": company,
            "metric_series": {
                "revenue": [
                    {"year": "fy21", "value": 100, "unit": "crore", "basis": "consolidated", "confidence": "high"},
                    {"year": "fy22", "value": 120, "unit": "crore", "basis": "consolidated", "confidence": "high"},
                    {"year": "fy23", "value": 150, "unit": "crore", "basis": "consolidated", "confidence": "high"},
                ],
            },
        },
    )

    payload = build_management_progression(
        company,
        companies_root=tmp_path / "companies",
        generated_at="2026-01-01T00:00:00Z",
    )
    validation = validate_management_progression(payload)

    assert validation["status"] == "pass", validation["errors"]
    items = payload["progression_items"]
    assert items, "Expected at least one progression item"
    item = items[0]
    sc = item.get("synthesis_chain")
    assert sc is not None
    assert sc["chain_status"] in CHAIN_STATUSES
    assert sc["financial_consequence"]["link_status"] in {"confirmed", "not_yet_visible", "unproven"}
    assert sc["investor_implication"]["conclusion"]


def test_synthesis_chain_absent_financial_trends_passes_validation(tmp_path: Path):
    """
    When financial_trends.json is absent, synthesis_chain falls back gracefully
    (link_status = not_yet_visible) and validation still passes.
    """
    company = "nofin"
    _write_json(
        tmp_path / "companies" / company / "company_memory" / "company_model" / "company_model.json",
        _company_model(company),
    )
    _write_json(
        tmp_path / "companies" / company / "company_memory" / "projects" / "projects_registry.json",
        {
            "company": company,
            "projects": [
                {
                    "project_id": "PJ-NOFIN",
                    "project_name": "Satellite testing facility for defence programmes",
                    "description": "Satellite testing facility for defence programmes",
                    "announcement_period": "fy23",
                    "assessment": {
                        "execution_status": "commissioned",
                        "observed_business_effect": "Facility commissioned; customer testing capacity increased.",
                    },
                    "evidence_ids": ["ev_nofin"],
                }
            ],
        },
    )
    # No financial_trends.json written

    payload = build_management_progression(
        company,
        companies_root=tmp_path / "companies",
        generated_at="2026-01-01T00:00:00Z",
    )
    validation = validate_management_progression(payload)

    assert validation["status"] == "pass", validation["errors"]
    item = payload["progression_items"][0]
    sc = item["synthesis_chain"]
    assert sc["financial_consequence"]["link_status"] == FINANCIAL_LINK_NOT_YET_VISIBLE
    assert sc["chain_status"] in CHAIN_STATUSES


def test_no_auto_causality_revenue_growth_after_action():
    """
    Revenue grew substantially after the action. The synthesis must NOT claim
    that the action caused the revenue growth — causal_link must be 'not_established'.
    """
    item = _item(
        theme="Revenue growth through marketing investment",
        events=[
            _ev(role="action", period="fy21",
                action_taken="Increased marketing investment for revenue growth."),
            _ev(role="outcome", period="fy22",
                operational_outcome="Marketing campaigns executed across all geographies."),
        ],
    )
    metric_series = {
        "revenue": _series(("fy21", 1000), ("fy22", 1300), ("fy23", 1600)),
    }
    chain = build_synthesis_chain(item, metric_series)

    # Revenue is in the theme text → should appear in metrics_observed
    rev_obs = [m for m in chain["financial_consequence"]["metrics_observed"] if m["metric_id"] == "revenue"]
    if rev_obs:
        assert rev_obs[0]["causal_link"] == "not_established"

    # Must NOT be FINANCIAL_IMPACT_CONFIRMED (no explicit metric+number in outcome text)
    assert chain["chain_status"] != CHAIN_STATUS_FINANCIAL_IMPACT_CONFIRMED
    # Financial link must not be "confirmed" without explicit evidence
    assert chain["financial_consequence"]["link_status"] != FINANCIAL_LINK_CONFIRMED


def test_statement_not_promoted_to_action():
    """
    A management statement (role=statement) must NOT be treated as an action.
    chain_status must remain CLAIM_ONLY even if the statement text mentions an initiative.
    """
    item = _item(
        theme="Management strategy for platform expansion",
        events=[
            _ev(role="statement", period="fy23",
                statement_text="We plan to expand our platform to new geographies next year."),
        ],
    )
    chain = build_synthesis_chain(item, {})

    assert chain["chain_status"] == CHAIN_STATUS_CLAIM_ONLY
    assert chain["action"] is None


def test_regulator_action_is_not_described_as_management_action():
    item = _item(
        theme="Toansa regulatory restriction",
        events=[
            _ev(
                role="action",
                period="fy20",
                action_taken="USFDA prohibited use of API manufactured at the Toansa facility.",
                actor="regulator",
            ),
        ],
    )

    chain = build_synthesis_chain(item, {})

    assert chain["action"] is not None
    assert chain["action"]["action_actor"] == "regulator"
    assert chain["chain_status"] != CHAIN_STATUS_ACTION_STARTED
    assert chain["outcome"] is None
    conclusion = chain["investor_implication"]["conclusion"]
    assert "regulatory action occurred" in conclusion.lower()
    assert "management has initiated action" not in conclusion.lower()


def test_management_initiated_action_remains_management_attributed():
    item = _item(
        theme="Branch service improvement",
        events=[
            _ev(
                role="action",
                period="fy24",
                action_taken="Management initiated a branch service improvement programme.",
                actor="management",
            ),
        ],
    )

    chain = build_synthesis_chain(item, {})

    assert chain["action"]["action_actor"] == "management"
    assert chain["chain_status"] == CHAIN_STATUS_ACTION_STARTED
    assert "Management has initiated action" in chain["investor_implication"]["conclusion"]


def test_commissioned_alone_is_completion_not_positive_outcome():
    item = _item(
        theme="Customer service assessment",
        events=[
            _ev(
                role="completion",
                period="fy24",
                action_taken="Management commissioned an external research agency.",
                operational_outcome="Commissioned an external research agency to independently assess customer service standards.",
                verification_status="verified",
            ),
        ],
    )

    chain = build_synthesis_chain(item, {})

    assert chain["action"]["completed"] is True
    assert chain["chain_status"] == CHAIN_STATUS_ACTION_COMPLETED
    assert chain["outcome"] is None


def test_completed_alone_is_completion_not_positive_outcome():
    item = _item(
        theme="Technology implementation",
        events=[
            _ev(
                role="completion",
                period="fy24",
                action_taken="The company completed implementation of a new technology platform.",
                operational_outcome="Implementation completed.",
                verification_status="verified",
                actor="company",
            ),
        ],
    )

    chain = build_synthesis_chain(item, {})

    assert chain["action"]["completed"] is True
    assert chain["chain_status"] == CHAIN_STATUS_ACTION_COMPLETED
    assert chain["outcome"] is None


def test_completion_plus_beneficial_result_is_positive_outcome():
    item = _item(
        theme="Plant commissioning with utilization evidence",
        events=[
            _ev(
                role="completion",
                period="fy24",
                action_taken="Plant commissioned in FY24.",
                operational_outcome="Plant commissioned in FY24; utilization rose to 80% in FY25.",
                verification_status="verified",
                actor="company",
            ),
        ],
    )

    chain = build_synthesis_chain(item, {})

    assert chain["chain_status"] == CHAIN_STATUS_OUTCOME_POSITIVE
    assert chain["outcome"]["direction"] == "positive"


def test_completion_plus_adverse_result_is_negative_outcome():
    item = _item(
        theme="Plant commissioning with defect evidence",
        events=[
            _ev(
                role="completion",
                period="fy24",
                action_taken="Plant commissioned in FY24.",
                operational_outcome="Plant commissioned in FY24; defect rates worsened after launch.",
                verification_status="verified",
                actor="company",
            ),
        ],
    )

    chain = build_synthesis_chain(item, {})

    assert chain["chain_status"] == CHAIN_STATUS_OUTCOME_NEGATIVE
    assert chain["outcome"]["direction"] == "negative"


def test_unknown_actor_does_not_fabricate_management_attribution():
    item = _item(
        theme="External event with unclear ownership",
        events=[
            _ev(
                role="action",
                period="fy24",
                action_taken="A service review was initiated.",
                actor="unknown",
            ),
        ],
    )

    chain = build_synthesis_chain(item, {})

    assert chain["action"]["action_actor"] == "unknown"
    assert chain["chain_status"] == CHAIN_STATUS_OUTCOME_UNKNOWN
    assert "Management has initiated action" not in chain["investor_implication"]["conclusion"]


def test_synthesis_chain_statuses_are_all_valid():
    """Enumerate all CHAIN_STATUSES and verify none are duplicated."""
    expected = {
        "CLAIM_ONLY", "ACTION_STARTED", "ACTION_COMPLETED",
        "EARLY_OPERATING_SIGNAL", "PARTIAL_EXECUTION",
        "OUTCOME_POSITIVE", "OUTCOME_NEGATIVE", "OUTCOME_MIXED", "OUTCOME_UNKNOWN",
        "FINANCIAL_IMPACT_CONFIRMED", "FINANCIAL_IMPACT_NOT_YET_VISIBLE", "FINANCIAL_LINK_UNPROVEN",
    }
    assert CHAIN_STATUSES == expected


# ===========================================================================
# Management Intelligence Depth — 12 new regression tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Test MD-1: completion only → no positive outcome claimed
# ---------------------------------------------------------------------------


def test_md_completion_only_no_positive_outcome_claimed():
    """
    Commissioning alone must not produce OUTCOME_POSITIVE.
    'utilization is not yet proven' is a negation, not an early operating signal.
    """
    item = _item(
        theme="Industrial refrigeration plant",
        events=[
            _ev(role="completion", period="fy24",
                action_taken="Industrial refrigeration plant commissioned.",
                operational_outcome="Commissioning is visible, but utilization is not yet proven.",
                verification_status="verified"),
        ],
    )
    chain = build_synthesis_chain(item, {})
    assert chain["chain_status"] == CHAIN_STATUS_ACTION_COMPLETED
    assert chain["outcome"] is None
    assert "completion alone" in chain["investor_implication"]["conclusion"].lower()


# ---------------------------------------------------------------------------
# Test MD-2: completion + ramp evidence → EARLY_OPERATING_SIGNAL
# ---------------------------------------------------------------------------


def test_md_completion_with_ramp_evidence_gives_early_operating_signal():
    """
    An action event whose operational_outcome contains early-traction language
    (ramping up, early traction visible) must produce EARLY_OPERATING_SIGNAL,
    not ACTION_COMPLETED or OUTCOME_POSITIVE.
    """
    item = _item(
        theme="Digital platform build-out",
        events=[
            _ev(role="action", period="fy22",
                action_taken="Digital platform deployed across first cohort of branches.",
                operational_outcome="Early traction visible; adoption ramping up across branches.",
                verification_status="partially_verified"),
        ],
    )
    chain = build_synthesis_chain(item, {})
    assert chain["chain_status"] == CHAIN_STATUS_EARLY_OPERATING_SIGNAL
    assert chain["outcome"] is not None
    assert "intermediate" in chain["investor_implication"]["conclusion"].lower() or \
           "early" in chain["investor_implication"]["conclusion"].lower()
    assert chain["investor_implication"]["confidence"] == "medium"


# ---------------------------------------------------------------------------
# Test MD-3: early operating signal on completion event → EARLY_OPERATING_SIGNAL
# ---------------------------------------------------------------------------


def test_md_completion_event_with_post_execution_evidence_gives_early_signal():
    """
    A completion-role event whose operational_outcome says
    'some post-execution evidence of business use or utilisation'
    must produce EARLY_OPERATING_SIGNAL, not ACTION_COMPLETED.
    """
    item = _item(
        theme="Data platform for product-per-customer expansion",
        events=[
            _ev(role="completion", period="fy23",
                action_taken="Data platform deployed.",
                operational_outcome="There is some post-execution evidence of business use or utilisation.",
                verification_status="verified"),
        ],
    )
    chain = build_synthesis_chain(item, {})
    # The operational_outcome text passes _has_early_operating_signal but not _has_true_outcome_evidence
    assert chain["chain_status"] == CHAIN_STATUS_EARLY_OPERATING_SIGNAL


# ---------------------------------------------------------------------------
# Test MD-4: EARLY_OPERATING_SIGNAL does not inherit financial language
# ---------------------------------------------------------------------------


def test_md_early_operating_signal_investor_implication_does_not_claim_financial_outcome():
    """
    EARLY_OPERATING_SIGNAL investor implication must NOT claim financial returns.
    """
    item = _item(
        theme="Branch network expansion",
        events=[
            _ev(role="action", period="fy23",
                action_taken="100 new branches opened.",
                operational_outcome="Customer response encouraging; initial uptake visible across markets."),
        ],
    )
    chain = build_synthesis_chain(item, {})
    assert chain["chain_status"] == CHAIN_STATUS_EARLY_OPERATING_SIGNAL
    conclusion = chain["investor_implication"]["conclusion"].lower()
    assert "financial consequence" not in conclusion or "not yet" in conclusion or "unproven" in conclusion or \
           "not yet been established" in conclusion
    assert "shareholder value" not in conclusion
    assert "successfully" not in conclusion


# ---------------------------------------------------------------------------
# Test MD-5: partial execution from item current_status
# ---------------------------------------------------------------------------


def test_md_partially_delivered_item_produces_partial_execution():
    """
    An item with current_status='partially_delivered' and action evidence
    but no outcome evidence must produce PARTIAL_EXECUTION.
    """
    item = {
        "theme": "Regional rollout — phased delivery",
        "current_status": "partially_delivered",
        "events": [
            _ev(role="action", period="fy23",
                action_taken="Phase 1 of regional rollout completed; Phase 2 delayed to FY25.",
                verification_status="partially_verified"),
        ],
    }
    chain = build_synthesis_chain(item, {})
    assert chain["chain_status"] == CHAIN_STATUS_PARTIAL_EXECUTION
    conclusion = chain["investor_implication"]["conclusion"].lower()
    assert "partial" in conclusion or "delayed" in conclusion
    assert chain["investor_implication"]["confidence"] == "low"


# ---------------------------------------------------------------------------
# Test MD-6: delayed execution preserved via action text
# ---------------------------------------------------------------------------


def test_md_delayed_execution_in_action_text_produces_partial_execution():
    """
    When the action text itself contains 'timeline delayed' or 'execution delayed',
    the chain must produce PARTIAL_EXECUTION rather than ACTION_STARTED.
    """
    item = _item(
        theme="Capacity expansion project",
        events=[
            _ev(role="action", period="fy24",
                action_taken="Capacity expansion: execution delayed; timeline slipped to FY26.",
                verification_status="unresolved"),
        ],
    )
    chain = build_synthesis_chain(item, {})
    assert chain["chain_status"] == CHAIN_STATUS_PARTIAL_EXECUTION


# ---------------------------------------------------------------------------
# Test MD-7: later-year evidence upgrades earlier chain
# ---------------------------------------------------------------------------


def test_md_later_year_outcome_event_upgrades_chain():
    """
    When an earlier event is ACTION_STARTED and a later event has a positive
    outcome role, the synthesis must use the later evidence and produce
    OUTCOME_POSITIVE, not ACTION_STARTED.
    """
    item = _item(
        theme="API manufacturing facility expansion",
        events=[
            _ev(role="action", period="fy22",
                action_taken="API manufacturing expansion underway.",
                verification_status="unresolved"),
            _ev(role="outcome", period="fy24",
                operational_outcome="Capacity expanded and utilization rose to 85%; output improved significantly.",
                verification_status="verified"),
        ],
    )
    chain = build_synthesis_chain(item, {})
    assert chain["chain_status"] == CHAIN_STATUS_OUTCOME_POSITIVE
    assert chain["outcome"] is not None
    assert chain["outcome"]["direction"] == "positive"


# ---------------------------------------------------------------------------
# Test MD-8: later contradictory evidence marks outcome negative
# ---------------------------------------------------------------------------


def test_md_later_reversal_event_marks_outcome_negative():
    """
    A reversal event arriving after an action event must override the chain
    and produce OUTCOME_NEGATIVE with 'negative' direction.
    """
    item = _item(
        theme="Market expansion into new geography",
        events=[
            _ev(role="action", period="fy22",
                action_taken="Launched operations in new geography.",
                verification_status="partially_verified"),
            _ev(role="reversal", period="fy24",
                action_taken="Operations in new geography wound down; market exit announced.",
                operational_outcome="Strategy reversed; geography proved unviable.",
                verification_status="verified"),
        ],
    )
    chain = build_synthesis_chain(item, {})
    assert chain["chain_status"] == CHAIN_STATUS_OUTCOME_NEGATIVE
    assert chain["outcome"]["direction"] == "negative"
    assert "credibility" in chain["investor_implication"]["conclusion"].lower() or \
           "negative" in chain["investor_implication"]["conclusion"].lower()


# ---------------------------------------------------------------------------
# Test MD-9: cancelled/abandoned action not treated as completion
# ---------------------------------------------------------------------------


def test_md_abandoned_action_not_treated_as_completion():
    """
    An abandonment-role event must produce OUTCOME_NEGATIVE, not
    ACTION_COMPLETED, even when the action was started.
    """
    item = _item(
        theme="Product line extension",
        events=[
            _ev(role="action", period="fy22",
                action_taken="Product line extension initiated.",
                verification_status="partially_verified"),
            _ev(role="abandonment", period="fy24",
                action_taken="Product line extension project abandoned; project cancelled.",
                operational_outcome="Initiative cancelled after pilot showed unacceptable unit economics.",
                verification_status="verified"),
        ],
    )
    chain = build_synthesis_chain(item, {})
    assert chain["chain_status"] != CHAIN_STATUS_ACTION_COMPLETED
    assert chain["chain_status"] in {CHAIN_STATUS_OUTCOME_NEGATIVE, CHAIN_STATUS_OUTCOME_MIXED}
    assert chain["outcome"]["direction"] == "negative"


# ---------------------------------------------------------------------------
# Test MD-10: regulator/customer action not credited to management
# ---------------------------------------------------------------------------


def test_md_regulator_action_not_credited_to_management():
    """
    When the action actor is 'regulator', chain_status must be OUTCOME_UNKNOWN
    (not ACTION_STARTED or ACTION_COMPLETED) and investor implication must
    reference external actor, not management execution.
    """
    item = _item(
        theme="Regulatory facility prohibition",
        events=[
            _ev(role="action", period="fy20",
                actor="regulator",
                statement_text="USFDA prohibited use of API manufactured at Toansa facility.",
                action_taken="USFDA prohibited use of API manufactured at Toansa facility for US market.",
                verification_status="verified"),
        ],
    )
    chain = build_synthesis_chain(item, {})
    assert chain["chain_status"] == CHAIN_STATUS_OUTCOME_UNKNOWN
    conclusion = chain["investor_implication"]["conclusion"].lower()
    assert "regulatory" in conclusion or "external" in conclusion or "management action" in conclusion


# ---------------------------------------------------------------------------
# Test MD-11: investor implication cannot exceed strongest chain stage
# ---------------------------------------------------------------------------


def test_md_investor_implication_cannot_exceed_chain_stage():
    """
    Investor implication must not claim shareholder value or successful outcomes
    when the chain is only at ACTION_STARTED or ACTION_COMPLETED.
    Both are tested because neither proves economic value.
    """
    # ACTION_STARTED case: action underway, not yet complete
    item_started = _item(
        theme="New branch expansion programme",
        events=[
            _ev(role="action", period="fy23",
                action_taken="Management is rolling out 100 new branches across regions.",
                verification_status="unresolved"),
        ],
    )
    chain = build_synthesis_chain(item_started, {})
    assert chain["chain_status"] == CHAIN_STATUS_ACTION_STARTED
    conclusion = chain["investor_implication"]["conclusion"].lower()
    assert "shareholder value" not in conclusion
    assert "successfully" not in conclusion
    assert chain["investor_implication"]["confidence"] == "low"

    # ACTION_COMPLETED case: completion confirmed, still no value-creation claim
    item_completed = _item(
        theme="Heat-pump installation",
        events=[
            _ev(role="completion", period="fy24",
                action_taken="Heat pump installed and operational.",
                operational_outcome="Installation completed; energy savings not yet quantified.",
                verification_status="verified"),
        ],
    )
    chain2 = build_synthesis_chain(item_completed, {})
    assert chain2["chain_status"] == CHAIN_STATUS_ACTION_COMPLETED
    conclusion2 = chain2["investor_implication"]["conclusion"].lower()
    assert "shareholder value" not in conclusion2
    assert "successfully" not in conclusion2
    assert "completion alone" in conclusion2


# ---------------------------------------------------------------------------
# Test MD-12: no company/year hardcoding in synthesis
# ---------------------------------------------------------------------------


def test_md_no_company_or_year_hardcoding():
    """
    Synthesis chain must work identically for any company slug and any year.
    Uses a deliberately unusual company name and future year.
    """
    item = {
        "theme": "Arbitrary initiative",
        "company_slug": "xyzco_9999",
        "current_status": "in_progress",
        "events": [
            _ev(role="commitment", period="fy99",
                statement_text="Commitment to expand into adjacent markets in FY2099."),
            _ev(role="action", period="fy00",
                action_taken="Expansion into adjacent markets initiated in FY2100.",
                verification_status="partially_verified"),
        ],
    }
    chain = build_synthesis_chain(item, {})
    assert chain["chain_status"] in CHAIN_STATUSES
    assert chain["claim"] is not None
    assert chain["action"] is not None
    assert "xyzco" not in chain["investor_implication"]["conclusion"].lower()
    assert "fy99" not in chain["investor_implication"]["conclusion"].lower()
