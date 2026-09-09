"""
ENG-119A: Commitment Specificity and Entity Preservation — production proof tests.

Validates:
  A  Named product + geography in source → preserved in normalized_commitment
  B  Generic source (no named entity) → no invented specificity in named_subjects
  C  Named molecule + regulatory in source → captured in named_subjects
  D  Facility name in source → captured in named_subjects as FACILITY
  E  Fiscal year in source → captured in extracted_timelines
  F  Adversarial: generic "aim to develop new products" → empty named_subjects
  G  Multi-subject: source with Nafamostat AND AQCH → 2 named_subjects
  H  Specificity-loss check: named_subjects present but not in normalized → warning issued
"""

import pytest

from knowledge.company_memory.commitment_identity import (
    check_specificity_loss,
    extract_commitment_identity,
)
from knowledge.company_memory.management_commitments import _normalize_commitment


# ---------------------------------------------------------------------------
# A: named product + geography preserved in normalized_commitment
# ---------------------------------------------------------------------------
def test_A_product_and_geography_preserved_in_normalized():
    statement = "Target products specifically for emerging markets and India"
    category = "Product"
    topic = "Product launch"
    result = _normalize_commitment(statement, category, topic)
    # Must preserve "india" — not collapse to "{topic} expected."
    assert "india" in result.lower(), (
        f"'india' should survive normalization but got: {result!r}"
    )
    assert "product launch expected" not in result.lower(), (
        f"Should not collapse to generic topic label, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# B: generic source → no invented specificity in named_subjects
# ---------------------------------------------------------------------------
def test_B_generic_source_produces_empty_named_subjects():
    generic_statement = "Aim to develop new products and strengthen our portfolio"
    identity = extract_commitment_identity(generic_statement)
    assert identity["named_subjects"] == [], (
        f"Generic statement must produce empty named_subjects, got: {identity['named_subjects']}"
    )
    # Geography: "india" etc. must NOT be invented
    for geo in identity["geography"]:
        assert geo in generic_statement.lower(), (
            f"Geography '{geo}' not present in source — invented specificity"
        )


# ---------------------------------------------------------------------------
# C: named molecule + regulatory context → captured in named_subjects
# ---------------------------------------------------------------------------
def test_C_molecule_captured_in_named_subjects():
    statement = "We are evaluating Nafamostat for COVID-19 treatment and filed for approval"
    identity = extract_commitment_identity(statement)
    canonicals = [s["canonical"] for s in identity["named_subjects"]]
    assert "nafamostat" in canonicals, (
        f"nafamostat should be in named_subjects, got: {canonicals}"
    )
    subject = next(s for s in identity["named_subjects"] if s["canonical"] == "nafamostat")
    assert subject["subject_type"] == "MOLECULE"


# ---------------------------------------------------------------------------
# D: facility name → captured as FACILITY type
# ---------------------------------------------------------------------------
def test_D_facility_captured_as_facility_type():
    statement = "The Halol facility received USFDA inspection and is expected to resume exports"
    identity = extract_commitment_identity(statement)
    canonicals = [s["canonical"] for s in identity["named_subjects"]]
    assert "halol" in canonicals, f"halol should be captured, got: {canonicals}"
    subject = next(s for s in identity["named_subjects"] if s["canonical"] == "halol")
    assert subject["subject_type"] == "FACILITY"


# ---------------------------------------------------------------------------
# E: fiscal year in source → captured in extracted_timelines
# ---------------------------------------------------------------------------
def test_E_fiscal_year_captured_in_extracted_timelines():
    statement = (
        "The company increased specialty revenue from 7% in FY18 to 13% in FY22, "
        "with new product launches planned for global markets."
    )
    identity = extract_commitment_identity(statement)
    timelines = identity["extracted_timelines"]
    assert any("fy18" in t or "fy22" in t for t in timelines), (
        f"FY18/FY22 should be in extracted_timelines, got: {timelines}"
    )


# ---------------------------------------------------------------------------
# F: adversarial — generic commitment → no invented named_subjects
# ---------------------------------------------------------------------------
def test_F_adversarial_no_invented_subjects():
    generic_statements = [
        "Aim to develop new products and strengthen our portfolio",
        "Continue to invest in R&D and innovation",
        "Expand into high-growth markets with our product portfolio",
        "Enhance manufacturing efficiency and reduce costs",
    ]
    for stmt in generic_statements:
        identity = extract_commitment_identity(stmt)
        assert identity["named_subjects"] == [], (
            f"No named_subjects should be invented for generic statement: {stmt!r}\n"
            f"Got: {identity['named_subjects']}"
        )
        # Also verify no geography is invented (none are named in the statements above)
        for geo in identity["geography"]:
            assert geo in stmt.lower(), (
                f"Geography '{geo}' not in source statement: {stmt!r}"
            )


# ---------------------------------------------------------------------------
# G: multi-subject — Nafamostat AND AQCH → 2 named_subjects
# ---------------------------------------------------------------------------
def test_G_multi_subject_two_molecules():
    statement = (
        "We are evaluating Nafamostat and AQCH for COVID-19 treatment "
        "and exploring regulatory pathways in Japan."
    )
    identity = extract_commitment_identity(statement)
    canonicals = [s["canonical"] for s in identity["named_subjects"]]
    assert "nafamostat" in canonicals, f"nafamostat missing from: {canonicals}"
    assert "aqch" in canonicals, f"aqch missing from: {canonicals}"
    assert len(identity["named_subjects"]) == 2, (
        f"Expected 2 named_subjects, got {len(identity['named_subjects'])}: {canonicals}"
    )
    # Geography should capture Japan
    assert "japan" in identity["geography"], (
        f"japan should be in geography, got: {identity['geography']}"
    )


# ---------------------------------------------------------------------------
# H: specificity-loss check fires when named_subjects present but not in normalized
# ---------------------------------------------------------------------------
def test_H_specificity_loss_warning_fires():
    original = "Plan to launch Ilumya in Japan and Australia"
    # Simulate what would happen if normalization had collapsed it
    collapsed_normalized = "Product launch planned."
    identity = extract_commitment_identity(original)
    # "ilumya" should be in named_subjects
    assert any(s["canonical"] == "ilumya" for s in identity["named_subjects"]), (
        "ilumya should be in named_subjects"
    )
    warnings = check_specificity_loss(original, collapsed_normalized, identity)
    assert "COMMITMENT_SPECIFICITY_LOSS" in warnings, (
        f"Expected COMMITMENT_SPECIFICITY_LOSS warning, got: {warnings}"
    )
    assert "COMMITMENT_GEOGRAPHY_LOSS" in warnings, (
        f"Expected COMMITMENT_GEOGRAPHY_LOSS warning, got: {warnings}"
    )

    # Verify: when normalization IS faithful, no warning fires
    good_normalized = "Plan to launch ilumya in japan and australia."
    good_warnings = check_specificity_loss(original, good_normalized, identity)
    assert not good_warnings, (
        f"No warnings expected for faithful normalization, got: {good_warnings}"
    )
