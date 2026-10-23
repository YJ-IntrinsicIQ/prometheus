"""Critical SSOT remediation (independent Phase 1 audit F01-F21): each defect class reproduced as an adversarial unit case, with the rule that closes it. No company amounts
are hard-coded as a remedy: the cases are the statement wordings that exposed the defects."""
import json
from pathlib import Path

import pytest

from knowledge.financials import line_item_mapper as mapper
from knowledge.financials.extractor import _drop_subnote_reference, _split_rows
from knowledge.financials.discovery import _category_candidates, _is_business_combination_note
from knowledge.financials.fact_registry_schema import FinancialFact
from knowledge.financials.semantic_contracts import enforce_semantic_contracts, semantic_problems
from scripts.smart_chunker import clean_paragraphs


def fields(label, table="profit_and_loss"):
    return [m.canonical_field for m in mapper.map_line_item(table_type=table, line_item_raw=label)]


def fact(metric, label, value=10.0, statement="profit_and_loss", derived=False):
    return FinancialFact(metric_id=metric, metric_name=metric, fiscal_year="fy25", period="March 31, 2025", value=value, unit="INR crore", basis="consolidated", source_statement=statement,
                         source_artifact="normalized_fundamentals.json", source_line_item=label, source_page=1, confidence="high", availability_status="present_direct", derived=derived,
                         usable_downstream=True)


# F01 -------------------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("label", ["Total Expenses", "Total expenses (IV)", "Total operating expenses", "Operating Expenses (I to X)", "Rent, taxes and lighting"])
def test_f01_a_total_or_a_sub_line_is_not_other_expenses(label):
    assert "other_expenses" not in fields(label)


@pytest.mark.parametrize("label", ["Other expenses", "Other Expenses (Refer Note 26)"])
def test_f01_the_residual_heading_is_other_expenses(label):
    assert fields(label) == ["other_expenses"]


def test_f01_the_registry_rejects_a_total_even_if_a_mapper_let_it_through():
    f = fact("other_expenses", "Total expenses (IV)")
    enforce_semantic_contracts(f)
    assert (f.availability_status, f.usable_downstream) == ("invalid", False) and "total" in " ".join(f.warnings).lower()


# F04 / F10 -------------------------------------------------------------------------------------------------------------------------------------------------------------
def test_f04_a_capital_amount_beside_a_par_label_is_not_a_face_value():
    f = fact("face_value", "Equity shares of Rs.10 each)", value=15.75, statement="share_capital")
    enforce_semantic_contracts(f)
    assert f.usable_downstream is False


def test_f04_a_cell_equal_to_the_stated_par_still_is_a_face_value():
    f = fact("face_value", "Equity shares of Rs.2 each", value=2.0, statement="share_capital")
    enforce_semantic_contracts(f)
    assert f.usable_downstream is True


@pytest.mark.parametrize("label", ["to ` 1,931.80. Furthermore, the authorised share capital of the Bank was `", "Authorised share capital", "Pending allotment"])
def test_f10_authorised_or_narrative_capital_is_not_paid_up_capital(label):
    assert "equity_share_capital" not in fields(label, "balance_sheet")
    f = fact("equity_share_capital", label, value=2625.0, statement="balance_sheet")
    enforce_semantic_contracts(f)
    assert f.usable_downstream is False


# F05 -------------------------------------------------------------------------------------------------------------------------------------------------------------------
def test_f05_a_bare_additions_row_is_not_total_additions():
    f = fact("gross_block_additions", "Additions", value=0.03, statement="fixed_assets")
    enforce_semantic_contracts(f)
    assert f.usable_downstream is False
    g = fact("gross_block_additions", "Total additions during the year", value=19.9, statement="fixed_assets")
    assert semantic_problems(g) == []


# F06 -------------------------------------------------------------------------------------------------------------------------------------------------------------------
def test_f06_a_sub_note_reference_is_not_the_current_year_amount():
    text = "Particulars Notes As at March 31, 2023 As at March 31, 2022 (iii) Cash and cash equivalents 8 214.78 177.08 (iv) Other Bank balances 8.1 329.75 - (g) Other non- current assets 4.1 2.21 3.49"
    rows = dict(_split_rows(text, "balance_sheet")[0])
    assert rows["(iv) Other Bank balances"] == ["329.75", "-"] and rows["(g) Other non- current assets"] == ["2.21", "3.49"]


def test_f06_a_leading_one_decimal_amount_is_kept_when_the_row_has_no_extra_cell():
    assert _drop_subnote_reference(["8.1", "329.75"], 2) == ["8.1", "329.75"]
    assert _drop_subnote_reference(["8.1", "329.75", "-"], 2) == ["329.75", "-"]


# F07 / F08 -------------------------------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("label,field", [
    ("Current liabilities (a) Financial Liabilities (i) Borrowings", "short_term_debt"),
    ("Non-current liabilities (a) Financial liabilities (i) Borrowings", "long_term_debt"),
    ("Liabilities (1) Non-current liabilities (a) Financial liabilities (i) Borrowings", "long_term_debt"),
])
def test_f07_section_prefixed_borrowings_are_components_not_total_debt(label, field):
    assert fields(label, "balance_sheet") == [field]


def test_f07_the_registry_rejects_one_section_as_total_debt():
    f = fact("total_debt", "Current liabilities (i) Borrowings", statement="balance_sheet")
    enforce_semantic_contracts(f)
    assert f.usable_downstream is False
    assert semantic_problems(fact("total_debt", "Current liabilities (i) Borrowings", statement="balance_sheet", derived=True)) == []


def test_f07_the_non_current_heading_survives_chunk_cleaning():
    page = "Total equity 494,798.3 491,246.9\n\nLiabilities\n\n(1) Non-current liabilities\n\n(a) Financial liabilities\n\n(i) Borrowings 21 8,981.3 20,289.2\n\n(2) Current liabilities\n\n(a) Financial liabilities\n\n(i) Borrowings 25 24,449.0 55,493.8"
    joined = " ".join(clean_paragraphs(page))
    assert "Non-current liabilities" in joined and "Current liabilities" in joined


def test_f08_one_part_of_trade_payables_is_not_trade_payables():
    f = fact("payables", "Total outstanding dues of micro enterprises and small enterprises; and", value=26.59, statement="balance_sheet")
    enforce_semantic_contracts(f)
    assert f.usable_downstream is False
    assert semantic_problems(fact("payables", "derived:trade_payables", value=678.76, statement="balance_sheet", derived=True)) == []


# F09 -------------------------------------------------------------------------------------------------------------------------------------------------------------------
AMALGAMATION_NOTE = ("The amalgamation was accounted under the pooling of interest method. Summarised values of assets and liabilities taken over in accordance with the terms of the Scheme "
                     "Particulars (` in Crores) Balances with banks 170.64 Investments 1,679.83 Fixed assets 0.03 Other assets 3.85 Total assets (A) 1,854.35 Reserves and Surplus 1,731.50")


def test_f09_a_note_of_assets_taken_over_is_never_a_primary_statement_or_schedule():
    assert _is_business_combination_note(AMALGAMATION_NOTE)
    assert not [c for c, *_ in _category_candidates(AMALGAMATION_NOTE) if c.startswith("primary_") or c.startswith("schedule_")]


def test_f09_a_balance_sheet_heading_keeps_a_page_a_statement():
    page = "Balance Sheet as at March 31, 2025 Particulars Schedule As at March 31, 2025 CAPITAL AND LIABILITIES Capital 1,935.00 Total 100.00 scheme of amalgamation note"
    assert not _is_business_combination_note(page)


# F11 / F12 / F13 -------------------------------------------------------------------------------------------------------------------------------------------------------
def test_f11_depreciation_to_date_is_a_stock_not_the_annual_charge():
    assert "depreciation" not in fields("Depreciation to date", "fixed_assets") and "depreciation" in fields("Depreciation and amortisation expense")
    f = fact("depreciation", "Depreciation to date", value=-482.6)
    enforce_semantic_contracts(f)
    assert f.usable_downstream is False


def test_f12_an_operating_cash_subtotal_is_not_ebit_and_a_bare_others_line_is_not_other_assets():
    assert "ebit" not in fields("Operating Profit/(Loss) before Working Capital changes", "cash_flow")
    assert "other_assets" not in fields("(iv) Others", "balance_sheet") and "other_assets" in fields("Other assets", "balance_sheet")
    f = fact("other_assets", "(iv) Others", statement="balance_sheet")
    enforce_semantic_contracts(f)
    assert f.usable_downstream is False


def test_f13_bank_balance_sheet_cash_is_not_cash_and_cash_equivalents():
    bank = fact("cash_and_equivalents", "ASSETS Cash and Balances with Reserve Bank of India", statement="balance_sheet")
    enforce_semantic_contracts(bank, bank_format=True)
    assert bank.usable_downstream is False
    cfs = fact("cash_and_equivalents", "Cash and cash equivalents at the end of the year", statement="cash_flow")
    assert semantic_problems(cfs, bank_format=True) == []
    corporate = fact("cash_and_equivalents", "Cash and cash equivalents", statement="balance_sheet")
    assert semantic_problems(corporate, bank_format=False) == []


# F24 -------------------------------------------------------------------------------------------------------------------------------------------------------------------
def test_f24_one_combined_capex_line_is_one_combined_fact_not_two_invented_components():
    from knowledge.financials.fact_registry import _add_raw_capex_classification_facts
    raw = {"tables": {"cash_flow": [{"line_item_raw": "Payments for purchase of property, plant and equipment (including capital work-in-progress, other intangible assets and intangible assets under development)",
                                     "table_type": "cash_flow", "basis": "consolidated", "page": 246, "confidence": "high",
                                     "values": [{"period": "March 31, 2026", "value_crore": -3609.37}]}]}}
    facts = {}
    _add_raw_capex_classification_facts(facts, raw, "fy26")
    assert set(k for k in facts if k.startswith("capex_")) == {"capex_ppe_and_intangible_cash_outflow"}
    assert facts["capex_ppe_and_intangible_cash_outflow"][0].value == -3609.37


def test_f24_separate_ppe_and_intangible_lines_stay_separate_components():
    from knowledge.financials.fact_registry import _add_raw_capex_classification_facts
    rows = [{"line_item_raw": "Payments for acquisition of property, plant and equipment", "values": [{"period": "March 31, 2026", "value_crore": -10.88}]},
            {"line_item_raw": "Payments for acquisition of intangible assets", "values": [{"period": "March 31, 2026", "value_crore": -86.78}]}]
    raw = {"tables": {"cash_flow": [{**r, "table_type": "cash_flow", "basis": "consolidated", "page": 10, "confidence": "high"} for r in rows]}}
    facts = {}
    _add_raw_capex_classification_facts(facts, raw, "fy26")
    assert "capex_ppe_and_intangible_cash_outflow" not in facts
    assert facts["capex_ppe_cwip_cash_outflow"][0].value == -10.88 and facts["capex_intangible_cash_outflow"][0].value == -86.78


# F25 -------------------------------------------------------------------------------------------------------------------------------------------------------------------
def test_f25_a_holding_in_associates_is_not_the_investments_balance():
    assert "investments" not in fields("(f) Investment in associates", "balance_sheet") and "investments" in fields("(i) Investments", "balance_sheet")
    f = fact("investments", "(f) Investment in associates", value=232.73, statement="balance_sheet")
    enforce_semantic_contracts(f)
    assert f.usable_downstream is False


def test_f12_an_exposure_category_row_is_not_the_other_assets_balance():
    label = "All other assets not included in the above categories"
    assert "other_assets" not in fields(label, "balance_sheet")
    f = fact("other_assets", label, value=1626.37, statement="balance_sheet")
    enforce_semantic_contracts(f)
    assert f.usable_downstream is False


# F09 / F16 (bank totals) ---------------------------------------------------------------------------------------------------------------------------------------------
def _bank_fact(metric, label, *, derived=False, formula="", statement="balance_sheet"):
    return FinancialFact(metric_id=metric, metric_name=metric, fiscal_year="fy25", period="March 31, 2025", value=47689.15, unit="INR crore", basis="consolidated", source_statement=statement,
                         source_artifact="normalized_fundamentals.json", source_line_item=label, source_page=257, confidence="high", availability_status="present_direct" if not derived else "present_derived",
                         derived=derived, formula=formula, usable_downstream=True)


def test_a_bank_total_is_accepted_only_when_read_from_the_statements_own_closing_total():
    from knowledge.financials.fact_registry import _enforce_balance_sheet_availability
    sound = _bank_fact("total_assets", "Total equity and liabilities")
    _enforce_balance_sheet_availability(sound, partial_balance_sheet=False, bank_format=True)
    assert sound.usable_downstream is True
    for unsound in (_bank_fact("total_assets", "Total assets (A)", statement="financial_note"), _bank_fact("total_assets", "derived:total_assets", derived=True, formula="x + y"),
                    _bank_fact("total_liabilities", "derived:total_liabilities", derived=True, formula="total_assets - net_worth")):
        _enforce_balance_sheet_availability(unsound, partial_balance_sheet=False, bank_format=True)
        assert unsound.usable_downstream is False, unsound.source_line_item
    networth = _bank_fact("net_worth", "derived:net_worth", derived=True, formula="equity_share_capital + reserves")
    _enforce_balance_sheet_availability(networth, partial_balance_sheet=False, bank_format=True)
    assert networth.usable_downstream is True


def test_a_tax_that_was_withheld_is_unknown_not_nil_in_the_pat_bridge(tmp_path):
    """A bank's P&L carries tax only inside provisions and the cash-flow 'Tax adjustment' add-back is withheld by the registry: the PBT-to-PAT bridge must say 'insufficient data',
    not treat the missing tax as zero and fail the whole year."""
    from knowledge.financials.statement_validator import validate_normalized_fundamentals
    from tests.financials.test_financial_fact_registry import _normalized_entry, _normalized_payload, _write_json
    payload = _normalized_payload()
    payload["profit_and_loss"] = {"pbt": _normalized_entry("pbt", value_crore=941.57, value_original="941.57"), "pat": _normalized_entry("pat", value_crore=726.10, value_original="726.10")}
    path = tmp_path / "normalized_fundamentals.json"
    _write_json(path, payload)
    report = validate_normalized_fundamentals(company="acme", year="fy25", normalized_path=path).to_dict()
    bridge = next(c for c in report["checks"] if c["check_name"] == "pat_bridge")
    assert bridge["status"] == "warning" and "insufficient" in bridge["details"]



def test_capex_is_both_lines_when_the_intangible_line_outranked_a_long_wrapped_ppe_caption():
    from knowledge.financials.fact_registry import _repair_capex_for_separate_intangibles
    def cf(metric, value, line):
        return FinancialFact(metric_id=metric, metric_name=metric, fiscal_year="fy25", period="fy25", value=value, unit="INR crore", basis="standalone", source_statement="cash_flow", source_artifact="raw",
                             source_line_item=line, source_page=116, confidence="high", availability_status="present_direct", usable_downstream=True)
    ppe = "Purchase of property, plant and equipment, capital work in progress, net including adjustment of capital advance and creditors"
    intang = "Purchase of intangible assets and intangible under development"
    facts = {"capex": [cf("capex", -70.57, intang)], "capex_ppe_cwip_cash_outflow": [cf("capex_ppe_cwip_cash_outflow", -35.86, ppe)], "capex_intangible_cash_outflow": [cf("capex_intangible_cash_outflow", -70.57, intang)],
             "cfo": [cf("cfo", -89.88, "Net cash used in operating activities")]}
    _repair_capex_for_separate_intangibles(facts, "fy25")
    assert round(facts["capex"][0].value, 2) == -106.43 and facts["capex"][0].derived is True


def test_f08_the_trade_payables_remainder_is_recognised_whatever_its_lead_in():
    from knowledge.financials.normalizer import _payables_component_kind
    assert _payables_component_kind("Total outstanding dues of trade payables other than micro enterprises and small enterprises.") == "other_trade_payables"
    assert _payables_component_kind("Total outstanding dues of creditors other than micro enterprises and small enterprises") == "other_trade_payables"
    assert _payables_component_kind("Total outstanding dues of micro enterprises and small enterprises; and") == "msme_trade_payables"


def test_f07_a_total_built_from_one_section_only_is_incomplete_not_total_debt():
    one = fact("total_debt", "derived:total_debt", value=2444.9, statement="balance_sheet", derived=True)
    one.formula = "short_term_debt only; long_term_debt not found in the primary statement"
    enforce_semantic_contracts(one)
    assert one.usable_downstream is False
    both = fact("total_debt", "derived:total_debt", value=3343.03, statement="balance_sheet", derived=True)
    both.formula = "short_term_debt + long_term_debt"
    assert semantic_problems(both) == []


def test_f07_both_section_lines_make_the_total_even_when_a_bare_borrowings_line_was_also_mapped(tmp_path):
    import json
    from tests.financials.test_financial_normalizer import _minimum_required_sections, _raw_payload, _row, _write_json
    from knowledge.financials.normalizer import normalize_financial_tables
    def primary(row):
        row["is_primary_statement"] = True
        row["source_section_type"] = "primary_balance_sheet_statement"
        return row
    sections = _minimum_required_sections()
    sections["balance_sheet"] += [
        primary(_row("balance_sheet", "Non-current liabilities (a) Financial liabilities (i) Borrowings", [("March 31, 2020", "202.89", 202.89)])),
        primary(_row("balance_sheet", "Current liabilities (a) Financial liabilities (i) Borrowings", [("March 31, 2020", "554.94", 554.94)])),
        primary(_row("balance_sheet", "(i) Borrowings", [("March 31, 2020", "554.94", 554.94)])),             # the bare line, mapped to the total, is the current section's again
    ]
    path = tmp_path / "raw_financial_tables.json"
    _write_json(path, _raw_payload(sections))
    payload = normalize_financial_tables(company="acme", year="fy20", raw_tables_path=path)
    td = payload["balance_sheet"]["total_debt"]
    assert td["derived"] is True and abs(td["value_crore"] - 757.83) < 1e-6 and td["formula"] == "short_term_debt + long_term_debt"


def test_a_negative_expense_is_a_cash_outflow_or_reversal_not_the_periods_expense():
    f = fact("finance_cost", "Finance costs", value=-144.25, statement="cash_flow")
    enforce_semantic_contracts(f)
    assert f.usable_downstream is False
    ok = fact("finance_cost", "Finance costs", value=144.25, statement="profit_and_loss")
    assert semantic_problems(ok) == []
    credit = fact("tax", "Tax expense", value=-12.0, statement="profit_and_loss")
    assert semantic_problems(credit) == []          # a tax credit is a legitimate negative


def test_a_note_tables_same_words_do_not_make_the_statements_row_ambiguous():
    from knowledge.financials.extractor import merge_raw_tables
    def row(label, value, page, primary):
        return {"line_item_raw": label, "basis": "consolidated", "page": page, "is_primary_statement": primary, "values": [{"period": "March 31, 2026", "value_raw": value}]}
    base = {"tables": {"balance_sheet": []}}
    supplement = {"tables": {"balance_sheet": [row("Non-current assets (a) Property, plant and equipment", "111,141.1", 241, True),
                                               row("Property, plant and equipment", "133.7", 315, False), row("Property, plant and equipment", "4.2", 298, False)]}}
    merged = merge_raw_tables(base, supplement)
    pages = {r["page"] for r in merged["tables"]["balance_sheet"]}
    assert 241 in pages


def test_a_note_rows_balance_sheet_figure_is_not_used_when_the_statement_itself_was_extracted(tmp_path):
    from knowledge.financials.fact_registry import build_financial_fact_registry
    from tests.financials.test_financial_fact_registry import _normalized_entry, _normalized_payload, _reconciliation_payload, _write_json
    payload = _normalized_payload()
    primary = {**_normalized_entry("cash_and_equivalents", value_crore=6.0, value_original="6"), "is_primary_statement": True, "source_section_type": "primary_balance_sheet_statement", "source_line_item": "Cash and cash equivalents"}
    note = {**_normalized_entry("fixed_assets", value_crore=13.37, value_original="13.37"), "is_primary_statement": False, "source_section_type": "financial_note", "source_line_item": "Property, Plant and equipment"}
    payload["balance_sheet"] = {"cash_and_equivalents": primary, "fixed_assets": note, "total_debt": payload["balance_sheet"]["total_debt"]}
    root = tmp_path
    _write_json(root / "normalized_fundamentals.json", payload)
    _write_json(root / "financial_reconciliation_report.json", _reconciliation_payload())
    registry, _r, _q = build_financial_fact_registry(company="acme", year="fy25", financial_root=root)
    invalid = {f.metric_id for f in registry.invalid_facts}
    usable = {f.metric_id for f in [*registry.available_facts, *registry.derived_facts, *registry.partial_facts] if f.usable_downstream}
    assert "fixed_assets" in invalid and "fixed_assets" not in usable and "cash_and_equivalents" in usable


def test_a_corporate_action_column_of_another_fiscal_year_is_not_this_years_action():
    from knowledge.financials.corporate_actions import _period_names_other_year
    assert _period_names_other_year("FY2023", "2025") and _period_names_other_year("FY 2023-24", "2025") and _period_names_other_year("For the year ended March 31, 2024", "2025")
    assert not _period_names_other_year("FY2024-25", "2025") and not _period_names_other_year("March 31, 2025", "2025") and not _period_names_other_year("", "2025")
