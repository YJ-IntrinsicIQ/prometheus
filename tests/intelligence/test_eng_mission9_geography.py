"""
Mission 9 geography-rule regression tests.

Verifies that validate_narrative_fields():
  - Blocks foreign geographies not in evidence (the primary guard)
  - Does NOT block home-market geographies for Indian companies (the M9 fix)
  - Does NOT block geographies explicitly present in the evidence corpus
  - Cross-company: Sun Pharma geo (Japan) correctly fires for non-pharma companies
"""
import json
import copy
import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOVERNANCE = REPO / "governance"

import sys
sys.path.insert(0, str(REPO))

from intelligence.ask_intrinsiciq.claim_validator import validate_narrative_fields


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _load_pkg(name: str) -> dict:
    return json.loads((GOVERNANCE / name).read_text())


def _load_m9_pkg(slug: str) -> dict:
    return _load_pkg(f"ENG_MISSION9_{slug.upper()}_EVIDENCE_PACKAGE.json")


def _base_answer() -> dict:
    return {
        "simple_answer": "Management has stated priorities.",
        "why_it_matters": "Execution matters for investors.",
        "claims": [],
    }


def _with_geo(answer: dict, geo_sentence: str, field: str = "simple_answer") -> dict:
    a = copy.deepcopy(answer)
    a[field] = a.get(field, "") + " " + geo_sentence
    return a


# ── 1. Foreign geo fires for all M9 companies ─────────────────────────────────

@pytest.mark.parametrize("slug", ["tanla", "ujjivan", "data_patterns"])
def test_foreign_geo_detected(slug):
    """Germany/Japan not in any company's evidence → violation fires."""
    pkg = _load_m9_pkg(slug)
    ans = _with_geo(_base_answer(), "Management expanded to Germany and Japan.")
    issues = validate_narrative_fields(ans, pkg)
    geo_violations = [i for i in issues if "germany" in i["violation"].lower() or "japan" in i["violation"].lower()]
    assert geo_violations, f"[{slug}] Expected Germany/Japan violation, got none. Issues: {issues}"


# ── 2. Home-market India allowed for Indian companies ─────────────────────────

@pytest.mark.parametrize("slug", ["ujjivan", "data_patterns"])
def test_home_market_india_allowed(slug):
    """'India'/'Indian' in answer for Indian company should NOT fire geography violation.

    These two companies do NOT have 'india' in their evidence corpus text, so
    without the home_market_geographies fix, this would be a false alarm.
    """
    pkg = _load_m9_pkg(slug)
    ans = _with_geo(_base_answer(), "Management aims to expand across the Indian market.")
    issues = validate_narrative_fields(ans, pkg)
    india_violations = [i for i in issues if "india" in i["violation"].lower()]
    assert not india_violations, (
        f"[{slug}] False alarm: 'India' incorrectly flagged for Indian company. Issues: {india_violations}"
    )


def test_tanla_india_allowed():
    """Tanla already has 'india' in corpus — no violation expected either way."""
    pkg = _load_m9_pkg("tanla")
    ans = _with_geo(_base_answer(), "Tanla operates across the Indian CPaaS market.")
    issues = validate_narrative_fields(ans, pkg)
    india_violations = [i for i in issues if "india" in i["violation"].lower()]
    assert not india_violations, f"False alarm on Tanla India: {india_violations}"


# ── 3. Evidence-corpus geography allowed ──────────────────────────────────────

def test_sun_pharma_japan_allowed():
    """Sun Pharma evidence explicitly mentions Japan → Japan in answer OK."""
    pkg = _load_pkg("ENG_MISSION1_SUN_PHARMA_EVIDENCE_PACKAGE.json")
    ans = _with_geo(_base_answer(), "Management committed to ILUMYA ramp in Japan.")
    issues = validate_narrative_fields(ans, pkg)
    japan_violations = [i for i in issues if "japan" in i["violation"].lower()]
    assert not japan_violations, f"False alarm: Japan flagged for Sun Pharma. Issues: {japan_violations}"


# ── 4. Sun Pharma geo fires for non-pharma companies ──────────────────────────

@pytest.mark.parametrize("slug", ["tanla", "ujjivan", "data_patterns"])
def test_sun_pharma_japan_fires_for_non_pharma(slug):
    """Japan appears in Sun Pharma evidence, but not in other companies' packages → violation."""
    pkg = _load_m9_pkg(slug)
    ans = _with_geo(_base_answer(), "Management committed to ramping up ILUMYA in Japan.")
    issues = validate_narrative_fields(ans, pkg)
    japan_violations = [i for i in issues if "japan" in i["violation"].lower()]
    assert japan_violations, (
        f"[{slug}] Expected Japan violation (cross-company contamination), got none. Issues: {issues}"
    )


# ── 5. Clean baseline answer has no false positives ───────────────────────────

@pytest.mark.parametrize("slug", ["tanla", "ujjivan", "data_patterns"])
def test_clean_baseline_no_violations(slug):
    """A factual, geography-free answer should produce zero violations."""
    pkg = _load_m9_pkg(slug)
    ans = _base_answer()
    issues = validate_narrative_fields(ans, pkg)
    assert not issues, f"[{slug}] Unexpected violations on clean answer: {issues}"


# ── 6. home_market_geographies field honoured dynamically ─────────────────────

def test_custom_home_market_geo_honoured():
    """Dynamically adding home_market_geo to a package prevents that geo from firing."""
    pkg = _load_m9_pkg("ujjivan")
    # Remove the fix to simulate pre-fix state
    pkg_no_fix = copy.deepcopy(pkg)
    pkg_no_fix["package_constraints"].pop("home_market_geographies", None)
    ans = _with_geo(_base_answer(), "Ujjivan serves the Indian microfinance market.")

    # Without fix: India not in corpus AND not in home_market_geos → violation
    issues_before = validate_narrative_fields(ans, pkg_no_fix)
    india_violations_before = [i for i in issues_before if "india" in i["violation"].lower()]
    assert india_violations_before, "Pre-fix: India should have fired but did not"

    # With fix: home_market_geographies present → no violation
    issues_after = validate_narrative_fields(ans, pkg)
    india_violations_after = [i for i in issues_after if "india" in i["violation"].lower()]
    assert not india_violations_after, f"Post-fix: India still fires. Issues: {india_violations_after}"
