"""Adversarial tests for capital_allocation_outcomes/builder.py.

These tests target the structural bugs fixed in ENG-105:
  - Acquisition disambiguation (distinct targets must not merge)
  - Generic 'Acquisition' must not merge with named acquisitions
  - Non-deployment items (proceeds, finance costs, admin actions) must be filtered
  - Hyphenated 'buy-back' text must map to share_buyback
  - skip_canonicals must work with raw (un-normalized) canonical strings
"""
import json
from pathlib import Path

from intelligence.capital_allocation_outcomes.builder import (
    _build_allocation_group,
    _group_similarity,
    _load_pcim_allocation_items,
    _map_allocation_category,
    _merge_candidates,
    _token_set,
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
