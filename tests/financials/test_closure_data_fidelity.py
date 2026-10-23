"""SSOT critical closure RT03: facts that stayed usable while wrong. Share counts carry the unit and class their row states, stores and spares are not the materials consumed, a scope-
qualified headline is not the company-wide measure, one section's borrowings is not the other maturity, a report that presents one set of statements has one basis, capex is the
registry's total, and a margin on part of the cost of goods sold is not computed."""
from types import SimpleNamespace

from knowledge.financials.entity_basis import basis_from_text
from knowledge.financials.extractor import extract_headline_metrics
from knowledge.financials.fact_registry_schema import FinancialFact
from knowledge.financials.line_item_mapper import map_line_item
from knowledge.financials.normalizer import _share_count_label_scale
from knowledge.financials.registry_authority import _apply_entity_basis, _sync_registry_capex
from knowledge.financials.semantic_contracts import semantic_problems


def fields(label, table="profit_and_loss"):
    return {m.canonical_field for m in map_line_item(table_type=table, line_item_raw=label)}


def fact(metric, label, value=1.0, **kw):
    base = dict(metric_id=metric, metric_name=metric, fiscal_year="fy21", period="March 31, 2021", value=value, unit="INR crore", basis="consolidated", source_statement="balance_sheet",
                source_artifact="x", source_line_item=label, source_page=1, confidence="high", availability_status="present_direct", usable_downstream=True)
    return FinancialFact(**{**base, **kw})


# ---- share counts ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_a_share_count_row_states_its_own_unit_and_the_count_is_scaled_by_it():
    assert _share_count_label_scale("Weighted average shares outstanding – Basic (Nos. in 000's) - (B)") == 1e3
    assert _share_count_label_scale("Weighted average shares outstanding – Basic (Nos. in Crores) - (B)*") == 1e7
    assert _share_count_label_scale("Weighted average shares outstanding (Nos. in lakhs)") == 1e5
    assert _share_count_label_scale("Weighted average number of equity shares") == 1.0


def test_the_diluted_denominator_is_not_the_basic_one_and_the_basic_is_not_the_diluted_one():
    basic = "Weighted average shares outstanding – Basic (Nos. in 000's) - (B)"
    diluted = "Weighted average shares outstanding – Diluted (Nos. in 000's) - (C)*"
    assert "weighted_avg_shares" in fields(basic, "eps") and "weighted_avg_shares" not in fields(diluted, "eps")
    assert "diluted_shares" not in fields(basic, "eps")
    both = "Weighted average number of shares used in computing basic and diluted earnings per share"
    assert {"weighted_avg_shares", "diluted_shares"} <= fields(both, "eps")


# ---- cost of materials ----------------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_stores_and_spares_consumed_inside_other_expenses_are_not_the_materials_consumed():
    assert "cost_of_materials" not in fields("Consumption of materials, stores and spare parts", "tax")
    assert "cost_of_materials" in fields("Cost of materials consumed")
    assert semantic_problems(fact("cost_of_materials", "Consumption of materials, stores and spare parts", source_statement="profit_and_loss"))


# ---- headline scope -------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_a_headline_amount_qualified_with_including_is_a_scope_figure_not_the_company_wide_measure():
    segment = [{"page": 18, "text": "Gross loan book (OSP) ₹1,029 Cr Total deposits (including deposit of J163 Crores from the parent) ₹ 10,868 Cr"}]
    result = extract_headline_metrics(segment)
    assert all(m["metric_id"] != "total_deposits" for m in result["metrics"])
    assert {"metric_id": "total_deposits", "values": [1029.0], "reason": "scope_qualified"} in result["conflicts"]
    whole = [{"page": 7, "text": "On the deposit side, we reported total deposits of ` 37,630 Crores, marking a significant growth"}]
    assert [m["value"] for m in extract_headline_metrics(whole)["metrics"] if m["metric_id"] == "total_deposits"] == [37630.0]


# ---- maturity -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_one_maturity_of_borrowings_is_not_the_other():
    assert semantic_problems(fact("long_term_debt", "Current liabilities (a) Financial liabilities (i) Borrowings"))
    assert semantic_problems(fact("long_term_debt", "Current maturities of long-term debt"))
    assert not semantic_problems(fact("long_term_debt", "Non-current liabilities (a) Financial liabilities (i) Borrowings"))
    assert semantic_problems(fact("short_term_debt", "Non-current liabilities (a) Financial liabilities (i) Borrowings"))
    assert not semantic_problems(fact("short_term_debt", "Current liabilities (a) Financial liabilities (i) Borrowings"))


# ---- basis ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_a_report_that_declares_one_set_of_statements_has_one_basis_whatever_a_table_says():
    assert basis_from_text("These standalone financial statements have been prepared on a going concern basis") == "standalone"
    assert basis_from_text("there is no requirement to prepare Consolidated Financial Statements") == "standalone"
    assert basis_from_text("Total consolidated assets as per published financial statements 4,76,000") == "unknown"       # a capital-adequacy line is not a declaration
    assert basis_from_text("These standalone financial statements ... These consolidated financial statements ...") == "both"


def test_entity_basis_relabels_figures_that_a_table_signal_called_consolidated_and_keeps_the_old_label():
    normalized = {"profit_and_loss": {"revenue": {"value_crore": 10.0, "basis": "consolidated"}}, "balance_sheet": {"investments": {"value_crore": 5.0, "basis": "unknown"}}, "preferred_basis": "consolidated"}
    _apply_entity_basis(normalized, "standalone")
    assert normalized["profit_and_loss"]["revenue"]["basis"] == "standalone" and normalized["profit_and_loss"]["revenue"]["basis_relabelled_from"] == "consolidated"
    assert normalized["balance_sheet"]["investments"]["basis"] == "standalone" and normalized["preferred_basis"] == "standalone"


# ---- capex ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_the_registrys_total_capex_is_written_back_so_free_cash_flow_is_computed_on_all_of_it():
    normalized = {"cash_flow": {"capex": {"value_crore": -70.57, "capex_abs_crore": 70.57},
                                "fcf": {"value_crore": -160.45, "derived": True, "inputs_used": {"cfo": -89.88, "capex": -70.57, "capex_sign_convention": "cash_flow_signed"}}}}
    components = [SimpleNamespace(metric_id="capex_ppe_cwip_cash_outflow", usable_downstream=True, value=-35.86), SimpleNamespace(metric_id="capex_intangible_cash_outflow", usable_downstream=True, value=-70.57)]
    registry = SimpleNamespace(available_facts=components, derived_facts=[SimpleNamespace(metric_id="capex", usable_downstream=True, value=-106.43)])
    _sync_registry_capex(normalized, registry)
    entry = normalized["cash_flow"]["capex"]
    assert entry["derived"] is True and entry["inputs_used"] == {"capex_ppe_cwip_cash_outflow": -35.86, "capex_intangible_cash_outflow": -70.57} and entry["source_line_item"].startswith("derived:")
    assert entry["value_crore"] == -106.43 and entry["capex_abs_crore"] == 106.43 and entry["value_crore_before_registry"] == -70.57
    fcf = normalized["cash_flow"]["fcf"]
    assert fcf["value_crore"] == -196.31 and fcf["inputs_used"]["capex"] == -106.43 and fcf["value_crore_before_registry"] == -160.45
    _sync_registry_capex(normalized, SimpleNamespace(derived_facts=[SimpleNamespace(metric_id="capex", usable_downstream=False, value=-1.0)]))
    assert normalized["cash_flow"]["capex"]["value_crore"] == -106.43
