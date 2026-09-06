"""Adversarial tests for capital_allocation_outcomes/builder.py.

Phase 1 (ENG-105) tests target:
  - Acquisition disambiguation (distinct targets must not merge)
  - Generic 'Acquisition' must not merge with named acquisitions
  - Non-deployment items (proceeds, finance costs, admin actions) must be filtered
  - Hyphenated 'buy-back' text must map to share_buyback
  - skip_canonicals must work with raw (un-normalized) canonical strings

Phase 2 (ENG-105) tests target causal attribution contract:
  - Driver evidence must not fire on generic metric names alone (chronology ≠ causality)
  - Generic financial fallback must not populate return_evidence when no specific links
  - Semantic state contract: deployment/execution/operating/financial/per-share layers
  - Validator catches forbidden state combinations
  - Buyback gets SHARE_COUNT_REDUCTION; acquisition/capex gets UNABLE_TO_ATTRIBUTE
"""
import json
from pathlib import Path

from intelligence.capital_allocation_outcomes.builder import (
    _build_allocation_group,
    _causal_attribution_states,
    _driver_evidence,
    _group_similarity,
    _load_pcim_allocation_items,
    _map_allocation_category,
    _merge_candidates,
    _token_set,
    _validate_semantic_states,
)


# ---------------------------------------------------------------------------
# Helper to build a minimal candidate dict
# ---------------------------------------------------------------------------
def _candidate(
    *,
    year: str,
    category: str,
    name: str,
    family_key: str = "",
    funding: str = "unknown",
    rationale: str = "",
    purpose: str = "",
    item_id: str = "test-id",
) -> dict:
    norm = " ".join(t for t in name.lower().split() if t.isalpha() and len(t) > 1)
    return {
        "source_year": year,
        "allocation_category": category,
        "allocation_name": name,
        "normalized_name": norm,
        "family_key": family_key or norm[:40],
        "funding_source": funding,
        "stated_rationale": rationale,
        "inferred_business_purpose": purpose,
        "source_item_id": item_id,
        "source_reference": {},
        "amount_crore": None,
    }


# ---------------------------------------------------------------------------
# 1. Acquisition disambiguation: distinct named targets must not merge
# ---------------------------------------------------------------------------
def test_distinct_acquisition_targets_not_merged():
    """Proactiv and Concert acquisitions share only generic tokens; must be separate groups."""
    candidates = [
        _candidate(year="fy23", category="acquisition",
                   name="Acquisition/incorporation of The Proactiv Company KK",
                   item_id="pcim_fy23_proactiv_kk"),
        _candidate(year="fy23", category="acquisition",
                   name="Acquisition/incorporation of The Proactiv Company Holdings, Inc.",
                   item_id="pcim_fy23_proactiv_holdings"),
        _candidate(year="fy23", category="acquisition",
                   name="Incorporation/acquisition of Concert Pharmaceuticals Securities Corp.",
                   item_id="pcim_fy23_concert_sec"),
        _candidate(year="fy23", category="acquisition",
                   name="Incorporation/acquisition of Concert Pharma U.K. Ltd",
                   item_id="pcim_fy23_concert_uk"),
    ]
    groups, merged = _merge_candidates(candidates)
    # Proactiv KK + Holdings should merge (share "proactiv"),
    # Concert Sec + UK should merge (share "concert"),
    # but Proactiv and Concert clusters must NOT merge.
    assert len(groups) == 2, (
        f"Expected 2 acquisition groups (Proactiv, Concert); got {len(groups)}: "
        + ", ".join(g["allocation_name"][:40] for g in groups)
    )
    names_joined = " ".join(g["allocation_name"] for g in groups).lower()
    assert "proactiv" in names_joined, "Proactiv group missing"
    assert "concert" in names_joined, "Concert group missing"


# ---------------------------------------------------------------------------
# 2. Generic 'Acquisition' (no entity name) must not absorb named acquisitions
# ---------------------------------------------------------------------------
def test_generic_acquisition_does_not_merge_with_named():
    """A bare 'Acquisition' record from fy20 must not merge with the fy23 named entities."""
    candidates = [
        _candidate(year="fy20", category="acquisition",
                   name="Acquisition",
                   item_id="pcim_fy20_acq"),
        _candidate(year="fy23", category="acquisition",
                   name="Acquisition/incorporation of Alchemee Skincare Corporation",
                   item_id="pcim_fy23_alchemee"),
    ]
    groups, _ = _merge_candidates(candidates)
    assert len(groups) == 2, (
        "Generic 'Acquisition' must remain separate from Alchemee; "
        f"got {len(groups)} group(s)"
    )


# ---------------------------------------------------------------------------
# 3. Signature tokens use name-only; boilerplate rationale must not inflate scores
# ---------------------------------------------------------------------------
def test_signature_tokens_are_name_only():
    """Identical boilerplate in rationale/purpose must not cause unrelated items to merge."""
    boilerplate = "Allocate capital toward strategic control, integration, or partnership outcomes."
    candidates = [
        _candidate(year="fy23", category="acquisition",
                   name="Concert Pharmaceuticals Security",
                   rationale=boilerplate, purpose=boilerplate,
                   item_id="c1"),
        _candidate(year="fy23", category="acquisition",
                   name="Proactiv Holdings Inc",
                   rationale=boilerplate, purpose=boilerplate,
                   item_id="c2"),
    ]
    g = _build_allocation_group(candidates[0])
    # Signature should only contain tokens from 'Concert Pharmaceuticals Security'
    assert "allocate" not in g["signature_tokens"], (
        "Rationale token 'allocate' must not appear in signature_tokens"
    )
    assert "control" not in g["signature_tokens"], (
        "Rationale token 'control' must not appear in signature_tokens"
    )
    assert "concert" in g["signature_tokens"]


# ---------------------------------------------------------------------------
# 4. Hyphenated 'buy-back' must map to share_buyback
# ---------------------------------------------------------------------------
def test_map_category_hyphenated_buyback():
    item = {"value": "Payment for buy-back of equity shares", "canonical_category": "buyback"}
    assert _map_allocation_category(item, {}) == "share_buyback"


def test_map_category_buyback_with_space():
    item = {"value": "Buy back of equity shares", "canonical_category": ""}
    assert _map_allocation_category(item, {}) == "share_buyback"


# ---------------------------------------------------------------------------
# 5. Non-deployment PCIM items must be filtered by text patterns
# ---------------------------------------------------------------------------
def _make_pcim_fixture(tmp_path: Path, items_by_year: dict) -> Path:
    company_root = tmp_path / "companies" / "testco"
    mem_dir = company_root / "company_memory"
    mem_dir.mkdir(parents=True)
    pcim = {
        "capital_allocation_inputs": {
            "capital_allocation_by_year": [
                {
                    "year": yr,
                    "items": items,
                }
                for yr, items in items_by_year.items()
            ]
        }
    }
    (mem_dir / "pcim_v1.json").write_text(json.dumps(pcim), encoding="utf-8")
    return company_root


def test_pcim_filters_proceeds_from_borrowings(tmp_path):
    company_root = _make_pcim_fixture(tmp_path, {
        "fy22": [
            {
                "value": "Proceeds from borrowings",
                "canonical_category": "debt_repaid",
                "capital_allocation_group": "financing_actions",
                "source_item_id": "x1",
            }
        ]
    })
    items = _load_pcim_allocation_items(company_root)
    values = [item.get("value") for _, _, item in items]
    assert "Proceeds from borrowings" not in values, (
        "'Proceeds from borrowings' is a capital source and must be filtered"
    )


def test_pcim_filters_finance_costs(tmp_path):
    company_root = _make_pcim_fixture(tmp_path, {
        "fy21": [
            {
                "value": "Interest/payment of finance costs",
                "canonical_category": "debt_repaid",
                "capital_allocation_group": "financing_actions",
                "source_item_id": "x2",
            }
        ]
    })
    items = _load_pcim_allocation_items(company_root)
    values = [item.get("value") for _, _, item in items]
    assert "Interest/payment of finance costs" not in values, (
        "Finance costs are not capital deployment and must be filtered"
    )


def test_pcim_filters_change_in_authorised_capital(tmp_path):
    company_root = _make_pcim_fixture(tmp_path, {
        "fy26": [
            {
                "value": "Change in authorised capital and composite scheme",
                "canonical_category": "r_and_d_investment",
                "capital_allocation_group": "true_capital_deployment",
                "source_item_id": "x3",
            }
        ]
    })
    items = _load_pcim_allocation_items(company_root)
    values = [item.get("value") for _, _, item in items]
    assert not any("authorised capital" in v.lower() for v in values), (
        "'Change in authorised capital' is an admin action and must be filtered"
    )


def test_pcim_filters_debt_raised_by_canonical(tmp_path):
    """Items with canonical_category='debt_raised' must be filtered (capital source)."""
    company_root = _make_pcim_fixture(tmp_path, {
        "fy22": [
            {
                "value": "Borrowings from bank",
                "canonical_category": "debt_raised",
                "capital_allocation_group": "financing_actions",
                "source_item_id": "x4",
            }
        ]
    })
    items = _load_pcim_allocation_items(company_root)
    assert len(items) == 0, (
        "canonical_category='debt_raised' must be filtered by skip_canonicals"
    )


def test_pcim_filters_debt_raised_by_text(tmp_path):
    """Items whose value says 'Debt raised' but with wrong canonical must also be filtered."""
    company_root = _make_pcim_fixture(tmp_path, {
        "fy21": [
            {
                "value": "Debt raised",
                "canonical_category": "debt_repaid",  # PCIM misclassification
                "capital_allocation_group": "financing_actions",
                "source_item_id": "x5",
            }
        ]
    })
    items = _load_pcim_allocation_items(company_root)
    assert len(items) == 0, (
        "Items with 'Debt raised' text must be filtered even if canonical is wrong"
    )


# ===========================================================================
# Phase 2 — ENG-105: Causal attribution contract tests
# ===========================================================================

# ---------------------------------------------------------------------------
# 11. _driver_evidence must NOT fire on generic metric names alone
# ---------------------------------------------------------------------------

def test_driver_evidence_does_not_fire_on_metric_name_alone():
    """Revenue attribution must not attach to an unrelated allocation via metric name."""
    driver_payload = {
        "attributions": [
            {
                "metric": "revenue",
                "observed_change": "Revenue grew 11.2% to ₹47,000 crore",
                "possible_driver": "scale expansion and market share gains",
                "driver_type": "organic_growth",
                "period": "fy23",
                "confidence": "medium",
                "source_artifacts": [],
                "evidence_ids": [],
            }
        ]
    }
    # Capex allocation — no revenue/metric tokens in common with the driver text
    evidence = _driver_evidence(driver_payload, "Maintenance capital expenditure plant equipment")
    # After fix: overlap < 2 for these tokens; must not fire
    assert evidence == [], (
        "_driver_evidence must not fire when token overlap < 2; "
        "generic metric name alone is not causal evidence"
    )


def test_driver_evidence_fires_on_real_overlap():
    """If the driver text genuinely overlaps with the allocation name, it should fire."""
    driver_payload = {
        "attributions": [
            {
                "metric": "revenue",
                "observed_change": "Concert acquisition contributed revenue from specialty pharma",
                "possible_driver": "Concert integration benefit",
                "driver_type": "acquisition_synergy",
                "period": "fy24",
                "confidence": "medium",
                "source_artifacts": [],
                "evidence_ids": [],
            }
        ]
    }
    # Allocation name contains "Concert" — strong overlap with the driver text
    evidence = _driver_evidence(driver_payload, "Concert Pharmaceuticals acquisition integration")
    # At least "concert" and "acquisition" overlap -> score >= 2 -> should fire
    assert len(evidence) >= 1, (
        "_driver_evidence should fire when specific entity tokens overlap (>= 2)"
    )


# ---------------------------------------------------------------------------
# 12. Causal attribution states for acquisitions
# ---------------------------------------------------------------------------

def _minimal_record(category: str, current_status: str = "deployed") -> dict:
    return {
        "allocation_category": category,
        "current_status": current_status,
        "outcome_status": "unable_to_verify",
        "allocation_name": f"Test {category}",
        "amount_crore": 100.0,
    }


def test_acquisition_financial_outcome_unable_to_attribute():
    """Acquisitions must produce UNABLE_TO_ATTRIBUTE financial_outcome_state with no specific evidence."""
    record = _minimal_record("acquisition")
    states = _causal_attribution_states(record, [])
    assert states["financial_outcome_state"] == "UNABLE_TO_ATTRIBUTE", (
        "Acquisition financial_outcome_state must be UNABLE_TO_ATTRIBUTE without direct causal evidence; "
        "company-level revenue growth after acquisition is NOT attributable"
    )


def test_acquisition_causal_confidence_unknown_without_evidence():
    """Acquisitions with no project/capacity evidence must have causal_attribution_confidence=UNKNOWN."""
    record = _minimal_record("acquisition")
    states = _causal_attribution_states(record, [])
    assert states["causal_attribution_confidence"] == "UNKNOWN", (
        "causal_attribution_confidence must be UNKNOWN when only textual similarity links exist"
    )


def test_capex_announced_only_deployment_not_proven():
    """Capex announced but not commissioned: deployment_state must not be DEPLOYED."""
    record = _minimal_record("organic_capex", current_status="announced")
    record["amount_crore"] = None  # no financial confirmation yet
    states = _causal_attribution_states(record, [])
    assert states["deployment_state"] == "ANNOUNCED", (
        "Capex with status=announced and no amount must have deployment_state=ANNOUNCED"
    )
    assert states["execution_state"] == "UNABLE_TO_VERIFY", (
        "Execution state must not exceed deployment state"
    )


def test_acquisition_completed_but_value_creation_unknown():
    """Completing a transaction (COMPLETED_TRANSACTION) does not imply value was created."""
    record = _minimal_record("acquisition", current_status="deployed")
    states = _causal_attribution_states(record, [])
    assert states["deployment_state"] == "COMPLETED_TRANSACTION"
    assert states["value_creation_classification"] == "UNABLE_TO_VERIFY", (
        "Acquisition completed ≠ acquisition successful; value_creation must remain UNABLE_TO_VERIFY"
    )


# ---------------------------------------------------------------------------
# 13. Causal attribution states for distributions (dividend, buyback)
# ---------------------------------------------------------------------------

def test_buyback_gets_share_count_reduction():
    """Share buyback must produce SHARE_COUNT_REDUCTION per-share consequence."""
    record = _minimal_record("share_buyback")
    states = _causal_attribution_states(record, [])
    assert states["per_share_consequence_state"] == "SHARE_COUNT_REDUCTION", (
        "Share buyback must produce SHARE_COUNT_REDUCTION — this IS the per-share mechanism"
    )
    assert states["financial_outcome_state"] == "CASH_FLOW_EFFECT"
    assert states["causal_attribution_confidence"] == "MEDIUM"


def test_dividend_financial_outcome_is_cash_flow_effect():
    """Dividend is a distribution; its financial outcome IS the transaction itself."""
    record = _minimal_record("dividend")
    states = _causal_attribution_states(record, [])
    assert states["financial_outcome_state"] == "CASH_FLOW_EFFECT"
    assert states["per_share_consequence_state"] == "OWNER_EARNINGS_EFFECT"
    assert states["operating_outcome_state"] == "NO_VERIFIED_OUTCOME"


def test_capex_financial_outcome_unable_to_attribute():
    """Organic capex financial_outcome_state must be UNABLE_TO_ATTRIBUTE without causal link."""
    record = _minimal_record("organic_capex")
    states = _causal_attribution_states(record, [])
    assert states["financial_outcome_state"] == "UNABLE_TO_ATTRIBUTE", (
        "Revenue growth after capex is NOT an attributable financial outcome of that capex"
    )


# ---------------------------------------------------------------------------
# 14. Validator contract: forbidden state combinations
# ---------------------------------------------------------------------------

def test_validator_rejects_revenue_contribution_for_acquisition():
    """REVENUE_CONTRIBUTION for acquisition without specific evidence must be a violation."""
    record = {
        "allocation_category": "acquisition",
        "financial_outcome_state": "REVENUE_CONTRIBUTION",
        "execution_state": "UNABLE_TO_VERIFY",
        "deployment_state": "COMPLETED_TRANSACTION",
        "value_creation_classification": "UNABLE_TO_VERIFY",
        "per_share_consequence_state": "UNABLE_TO_ATTRIBUTE",
        "causal_attribution_confidence": "MEDIUM",
        "return_evidence": [],
    }
    violations = _validate_semantic_states(record)
    assert any("REVENUE_CONTRIBUTION" in v for v in violations), (
        "Validator must flag REVENUE_CONTRIBUTION for acquisition without specific evidence"
    )


def test_validator_rejects_share_count_reduction_for_non_buyback():
    """SHARE_COUNT_REDUCTION for a non-buyback category must be a violation."""
    record = {
        "allocation_category": "acquisition",
        "financial_outcome_state": "UNABLE_TO_ATTRIBUTE",
        "execution_state": "UNABLE_TO_VERIFY",
        "deployment_state": "COMPLETED_TRANSACTION",
        "value_creation_classification": "UNABLE_TO_VERIFY",
        "per_share_consequence_state": "SHARE_COUNT_REDUCTION",
        "causal_attribution_confidence": "UNKNOWN",
        "return_evidence": [],
    }
    violations = _validate_semantic_states(record)
    assert any("SHARE_COUNT_REDUCTION" in v for v in violations), (
        "Validator must flag SHARE_COUNT_REDUCTION for non-buyback categories"
    )


def test_validator_rejects_execution_exceeding_deployment():
    """Execution state must not exceed deployment state."""
    record = {
        "allocation_category": "organic_capex",
        "financial_outcome_state": "UNABLE_TO_ATTRIBUTE",
        "execution_state": "OPERATIONAL",
        "deployment_state": "UNABLE_TO_VERIFY",
        "value_creation_classification": "UNABLE_TO_VERIFY",
        "per_share_consequence_state": "UNABLE_TO_ATTRIBUTE",
        "causal_attribution_confidence": "LOW",
        "return_evidence": [],
    }
    violations = _validate_semantic_states(record)
    assert any("UNABLE_TO_VERIFY" in v and "execution_state" in v for v in violations), (
        "Validator must flag execution_state=OPERATIONAL when deployment_state=UNABLE_TO_VERIFY"
    )


def test_validator_clean_for_valid_buyback():
    """A well-formed buyback record must produce zero violations."""
    record = {
        "allocation_category": "share_buyback",
        "financial_outcome_state": "CASH_FLOW_EFFECT",
        "execution_state": "COMPLETED",
        "deployment_state": "COMPLETED_TRANSACTION",
        "value_creation_classification": "UNABLE_TO_VERIFY",
        "per_share_consequence_state": "SHARE_COUNT_REDUCTION",
        "causal_attribution_confidence": "MEDIUM",
        "return_evidence": [],
    }
    violations = _validate_semantic_states(record)
    assert violations == [], f"Valid buyback record must have no violations; got: {violations}"


def test_validator_clean_for_acquisition_with_unknown_states():
    """An acquisition with all unknowns/unable_to_attribute must produce zero violations."""
    record = {
        "allocation_category": "acquisition",
        "financial_outcome_state": "UNABLE_TO_ATTRIBUTE",
        "execution_state": "UNABLE_TO_VERIFY",
        "deployment_state": "COMPLETED_TRANSACTION",
        "value_creation_classification": "UNABLE_TO_VERIFY",
        "per_share_consequence_state": "UNABLE_TO_ATTRIBUTE",
        "causal_attribution_confidence": "UNKNOWN",
        "return_evidence": [],
    }
    violations = _validate_semantic_states(record)
    assert violations == [], f"Acquisition with honest unknowns must have no violations; got: {violations}"
