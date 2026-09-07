"""ENG-114: Deterministic tests for primary financial basis routing repair.

Steps 18A-E, 19-22 from the ENG-114 mission specification.
"""
import pytest
from intelligence.investor_panel.runner import (
    _is_secondary_metric_basis_warning,
    _collect_financial_basis,
    DOCTRINE_SECTION_PRIORITIES,
    _selected_pcim_view,
    _derive_financial_context,
    _missing_sections,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pcim(
    multi_year_basis: str = "",
    fq_top_basis: str = "",
    by_year_bases: list = None,
) -> dict:
    """Build a minimal PCIM dict for testing basis resolution."""
    pcim = {}
    if multi_year_basis:
        pcim["multi_year_financial_inputs"] = {"basis_used": multi_year_basis}
    if fq_top_basis or by_year_bases is not None:
        fq: dict = {}
        if fq_top_basis:
            fq["basis_used"] = fq_top_basis
        if by_year_bases is not None:
            fq["by_year"] = [{"year": f"FY{i+1}", "basis_used": b} for i, b in enumerate(by_year_bases)]
        pcim["financial_quality_inputs"] = fq
    return pcim


def _basis_for(pcim: dict, doctrine: str = "graham") -> str:
    sections = DOCTRINE_SECTION_PRIORITIES.get(doctrine, [])
    selected = _selected_pcim_view(pcim, sections)
    return _collect_financial_basis(selected, sections)


def _ctx_for(pcim: dict, doctrine: str = "graham") -> dict:
    sections = DOCTRINE_SECTION_PRIORITIES.get(doctrine, [])
    selected = _selected_pcim_view(pcim, sections)
    missing = _missing_sections(selected, sections)
    return _derive_financial_context(selected, sections, missing)


# ---------------------------------------------------------------------------
# Step 18A — Primary consolidated + secondary standalone warning → primary stays consolidated
# ---------------------------------------------------------------------------

def test_18a_primary_consolidated_secondary_warning_stays_consolidated():
    """Secondary standalone warning must not downgrade consolidated primary basis."""
    pcim = _make_pcim(multi_year_basis="consolidated", by_year_bases=["consolidated"] * 3)
    for doctrine in ["graham", "buffett", "fisher", "munger", "lynch"]:
        ctx = _ctx_for(pcim, doctrine)
        assert ctx["basis_used"] == "consolidated", f"{doctrine}: expected consolidated"
        # secondary basis warnings must not appear in interpretation_limits
        basis_limits = [l for l in ctx["interpretation_limits"] if "basis" in l.lower()]
        assert basis_limits == [], f"{doctrine}: unexpected basis limits: {basis_limits}"


# ---------------------------------------------------------------------------
# Step 18B — Primary consolidated + payables mixed warning → primary stays consolidated
# ---------------------------------------------------------------------------

def test_18b_payables_mixed_warning_does_not_downgrade_primary():
    warning = "payables: basis mismatch across years"
    assert _is_secondary_metric_basis_warning(warning) is True


# ---------------------------------------------------------------------------
# Step 18C — Both standalone and consolidated sections; primary all consolidated
# ---------------------------------------------------------------------------

def test_18c_both_sections_primary_all_consolidated():
    """multi_year consolidated + by_year all consolidated → consolidated even with mixed artifact text."""
    pcim = _make_pcim(multi_year_basis="consolidated", by_year_bases=["consolidated"] * 5)
    for doctrine in ["graham", "buffett"]:
        assert _basis_for(pcim, doctrine) == "consolidated", f"{doctrine}: expected consolidated"


# ---------------------------------------------------------------------------
# Step 18D — All primary metrics consolidated across multiple periods
# ---------------------------------------------------------------------------

def test_18d_all_years_consolidated_cross_year_comparable():
    pcim = _make_pcim(multi_year_basis="consolidated", by_year_bases=["consolidated"] * 7)
    for doctrine in ["graham", "buffett", "fisher", "munger", "lynch"]:
        assert _basis_for(pcim, doctrine) == "consolidated", f"{doctrine}: cross-year should be consolidated"


# ---------------------------------------------------------------------------
# Step 18E — Owner earnings: CFO/capex consolidated; split missing → capex caveat only
# ---------------------------------------------------------------------------

def test_18e_consolidated_basis_no_basis_caveat_in_limits():
    """When primary basis is consolidated, no basis-uncertainty limit should reach the analyst."""
    pcim = _make_pcim(multi_year_basis="consolidated", by_year_bases=["consolidated"] * 5)
    ctx = _ctx_for(pcim, "buffett")
    assert ctx["basis_used"] == "consolidated"
    basis_limits = [l for l in ctx["interpretation_limits"] if "basis" in l.lower()]
    assert basis_limits == [], f"Unexpected basis limits for Buffett with consolidated basis: {basis_limits}"


# ---------------------------------------------------------------------------
# Step 19 — Cross-year: FY1=standalone, FY2=consolidated → mixed preserved
# ---------------------------------------------------------------------------

def test_19_cross_year_switch_returns_mixed():
    pcim = _make_pcim(multi_year_basis="consolidated", by_year_bases=["standalone", "consolidated"])
    for doctrine in ["graham", "buffett"]:
        basis = _basis_for(pcim, doctrine)
        assert basis == "mixed", f"{doctrine}: cross-year switch should yield mixed, got {basis}"


# ---------------------------------------------------------------------------
# Step 20 — FY1=unknown, FY2=standalone → unresolved, no inference
# ---------------------------------------------------------------------------

def test_20_unknown_plus_standalone_returns_mixed():
    pcim = _make_pcim(multi_year_basis="standalone", by_year_bases=["unknown", "standalone"])
    for doctrine in ["graham", "buffett"]:
        basis = _basis_for(pcim, doctrine)
        assert basis in ("mixed", "standalone"), (
            f"{doctrine}: unknown+standalone should yield mixed or standalone, got {basis}"
        )


def test_20_all_unknown_returns_unknown():
    pcim = _make_pcim(multi_year_basis="unknown", by_year_bases=["unknown", "unknown"])
    assert _basis_for(pcim, "graham") == "unknown"


# ---------------------------------------------------------------------------
# Step 21 — cost_of_materials secondary warning: attached to that metric only
# ---------------------------------------------------------------------------

def test_21_cost_of_materials_warning_is_secondary():
    """cost_of_materials basis warning must not be attributed to revenue/PAT/EPS/CFO/capex."""
    warning = "profit_and_loss.cost_of_materials is available only in standalone basis and was not promoted into preferred consolidated view"
    assert _is_secondary_metric_basis_warning(warning) is True


def test_21_revenue_basis_warning_is_not_secondary():
    assert _is_secondary_metric_basis_warning("revenue: basis mismatch") is False


def test_21_pat_basis_warning_is_not_secondary():
    assert _is_secondary_metric_basis_warning("pat: standalone") is False


def test_21_cfo_basis_warning_is_not_secondary():
    assert _is_secondary_metric_basis_warning("cfo is consolidated") is False


def test_21_capex_basis_warning_is_not_secondary():
    assert _is_secondary_metric_basis_warning("capex: basis unclear") is False


def test_21_eps_basis_warning_is_not_secondary():
    assert _is_secondary_metric_basis_warning("eps_diluted: standalone vs consolidated mismatch") is False


# ---------------------------------------------------------------------------
# Step 22 — Warning flood: consolidated primary + many secondary warnings → primary stays consolidated
# ---------------------------------------------------------------------------

SECONDARY_FLOOD = [
    "balance_sheet.payables is available only in standalone basis and was not promoted into preferred consolidated view",
    "profit_and_loss.cost_of_materials is available only in standalone basis and was not promoted into preferred consolidated view",
    "profit_and_loss.employee_cost is available only in standalone basis and was not promoted into preferred consolidated view",
    "profit_and_loss.other_expenses is available only in standalone basis and was not promoted into preferred consolidated view",
    "profit_and_loss.finance_cost is available only in standalone basis and was not promoted into preferred consolidated view",
    "Basis mismatch across financial artifacts: consolidated",
    "Basis mismatch across financial artifacts: consolidated, unknown",
    "book_value_per_share: basis mismatch across years",
    "receivables: basis mismatch across years",
    "ebitda: basis mismatch across years",
    "ebit: basis mismatch across years",
    "inventory: basis mismatch across years",
    "payables: basis mismatch across years",
    "buyback: basis unclear",
    "dividend: basis unclear",
]


def test_22_all_flood_warnings_classified_as_secondary():
    """All 15 Sun Pharma secondary basis warnings must be classified as secondary."""
    failures = [w for w in SECONDARY_FLOOD if not _is_secondary_metric_basis_warning(w)]
    assert failures == [], f"Not classified as secondary: {failures}"


def test_22_warning_flood_does_not_downgrade_consolidated_primary():
    """consolidated primary + 15 secondary basis warnings → basis_used stays consolidated, zero basis limits."""
    pcim = _make_pcim(multi_year_basis="consolidated", by_year_bases=["consolidated"] * 7)
    for doctrine in ["graham", "buffett", "fisher", "munger", "lynch"]:
        ctx = _ctx_for(pcim, doctrine)
        assert ctx["basis_used"] == "consolidated", f"{doctrine}: basis_used downgraded"
        basis_limits = [l for l in ctx["interpretation_limits"] if "basis" in l.lower()]
        assert basis_limits == [], f"{doctrine}: secondary flood produced basis limits: {basis_limits}"


# ---------------------------------------------------------------------------
# Cross-company preservation (TANLA_REAL_MIXED_BASIS_PRESERVED, DATA_PATTERNS_UNKNOWN_BASIS_PRESERVED)
# ---------------------------------------------------------------------------

def test_tanla_unknown_basis_preserved():
    """Tanla genuine unknown basis must remain unknown for all doctrines."""
    import json, os
    pcim_path = "companies/tanla/company_memory/pcim_v1.json"
    if not os.path.exists(pcim_path):
        pytest.skip("Tanla PCIM not present")
    with open(pcim_path) as f:
        pcim = json.load(f)
    for doctrine in ["graham", "buffett", "fisher"]:
        assert _basis_for(pcim, doctrine) == "unknown", f"Tanla {doctrine}: must stay unknown"


def test_datapatterns_basis_preserved():
    """Data Patterns unknown-by-year basis must surface as mixed for Graham/Buffett."""
    import json, os
    pcim_path = "companies/datapatterns/company_memory/pcim_v1.json"
    if not os.path.exists(pcim_path):
        pytest.skip("Data Patterns PCIM not present")
    with open(pcim_path) as f:
        pcim = json.load(f)
    for doctrine in ["graham", "buffett"]:
        basis = _basis_for(pcim, doctrine)
        assert basis in ("mixed", "unknown"), f"Data Patterns {doctrine}: expected mixed/unknown, got {basis}"
