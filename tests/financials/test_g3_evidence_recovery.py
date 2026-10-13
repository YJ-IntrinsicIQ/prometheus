"""M63/G3 regression tests: shared extraction repairs. Every case is a generic text/table shape (no company data is read, nothing is written under companies/).
The wording of the examples is taken from the failure shapes found in real filings but the assertions are about the mechanism."""
import json

import pytest

from knowledge.financials import extractor as E
from knowledge.financials.corporate_actions import buyback_disclosures_from_chunks, dividend_disclosures_from_chunks
from knowledge.financials.discovery import _category_candidates, _document_basis
from knowledge.financials.fact_registry import _add_headline_metric_facts, _repair_capex_for_separate_intangibles
from knowledge.financials.fact_registry_schema import FinancialFact
from knowledge.financials.line_item_mapper import map_line_item


def chunk(text, page=1):
    return {"chunk_id": f"C{page}", "page": page, "text": text}


# ── statement titles, units, section headers, nil cells ──
def test_a_statement_title_printed_after_its_rows_still_identifies_the_statement():
    text = ("Particulars Notes No Year ended March 31, 2026 Year ended March 31, 2025 Revenue from operations 23 924.77 708.35 Other income 24 27.96 46.34 Total income 952.73 754.69 "
            "Depreciation and amortization expenses 29 22.95 13.92 Profit before tax 363.54 295.34 Profit for the year (A) 271.37 221.81 "
            "The accompanying notes are an integral part of the financial statements This is the statement of profit and loss referred to in our report of even date "
            "Statement of Profit and Loss For the year ended March 31, 2026 (All figures are in INR Crores unless specifically stated otherwise)")
    best = max(_category_candidates(text), key=lambda item: item[2])
    assert best[0] == "primary_profit_and_loss_statement"          # it used to be read as a cash-flow page (shared lines: profit before tax, depreciation)


def test_a_heading_that_starts_the_next_page_is_not_taken_for_this_pages_statement():
    rows = " ".join(f"Line item number {i} of the schedule {100 + i}.25 {90 + i}.10" for i in range(12))
    text = f"Particulars Year ended March 31, 2026 Year ended March 31, 2025 Net cash from operating activities 80.15 (89.88) {rows} Net increase in cash 19.21 (50.50) Balance Sheet as at March 31, 2026"
    assert "primary_balance_sheet_statement" not in {c[0] for c in _category_candidates(text)}


@pytest.mark.parametrize("phrase", ["(All amounts are in INR lakhs, unless otherwise stated)", "(All amounts are in INR lakhs unless otherwise stated)"])
def test_the_unit_line_is_read_with_or_without_a_comma(phrase):
    assert E._unit_hint(f"Consolidated Balance Sheet as at March 31, 2026 {phrase} Particulars", "balance_sheet") == "lakhs"


def test_a_lost_unit_line_is_inherited_only_from_an_explicit_declaration_on_an_adjacent_statement():
    chunks = [chunk("Particulars Note No As at March 31, 2026 Cash 12 74,801.21 50,150.30", 383), chunk("Total equity 2,48,800.01", 384),
              chunk("Consolidated Statement of Profit and Loss (All amounts are in INR lakhs, unless otherwise stated)", 385), chunk("unrelated text far away (All amounts are in INR crore)", 380)]
    positions = {c["chunk_id"]: i for i, c in enumerate(chunks)}
    by_id = {c["chunk_id"]: c for c in chunks}
    assert "lakhs" in E._inherited_unit_text(["C383", "C384"], chunks, positions, by_id)
    assert E._inherited_unit_text(["C380"], chunks[:1], {"C380": 0}, {"C380": chunks[3]}) == ""     # nothing adjacent to inherit from


def test_a_section_title_glued_to_the_first_row_does_not_swallow_the_row():
    text = "Particulars Year ended March 31, 2026 Year ended March 31, 2025 B. Cash flows from investing activities Purchase of property, plant and equipment, capital work in progress, net including adjustment of capital advance and creditors (44.47) (35.86) Purchase of investments (186.75) (157.49)"
    rows, _, _ = E._split_rows(E._trim_table_text(text, "cash_flow"), "cash_flow")
    labels = {label: values for label, values in rows}
    assert any(label.startswith("Purchase of property") and values == ["(44.47)", "(35.86)"] for label, values in labels.items())


def test_a_nil_cell_keeps_the_row_and_the_column_position():
    text = "Particulars Year ended March 31, 2026 Year ended March 31, 2025 Proceeds from issue of shares - 1.57 Shares bought back including transaction cost (17,928.76) - Dividends paid (16,034.08) (16,144.63)"
    rows, _, _ = E._split_rows(E._trim_table_text(text, "cash_flow"), "cash_flow")
    by_label = dict(rows)
    assert by_label["Shares bought back including transaction cost"] == ["(17,928.76)", "-"] and by_label["Proceeds from issue of shares"] == ["-", "1.57"]


def test_a_dash_inside_a_label_is_not_a_nil_cell():
    rows, _, _ = E._split_rows("Particulars Year ended March 31, 2026 Year ended March 31, 2025 Costs - others 12.5 11.0 Total 20.0 19.0", "profit_and_loss")
    assert dict(rows)["Costs - others"] == ["12.5", "11.0"]


# ── mapping ──
@pytest.mark.parametrize("label, field", [
    ("Earnings per equity share Basic and diluted (in INR)", {"eps_basic", "eps_diluted"}),
    ("1. Basic (INR)", {"eps_basic"}), ("2. Diluted (INR)", {"eps_diluted"}), ("Basic (in `)", {"eps_basic"}),
])
def test_per_share_variant_labels_map_to_eps(label, field):
    assert {m.canonical_field for m in map_line_item(table_type="profit_and_loss", line_item_raw=label)} == field


@pytest.mark.parametrize("label", ["Basic EPS Profit after tax from Continuing Operations", "Weighted average number of equity shares used in computing basic and diluted earnings per share"])
def test_the_numerator_or_share_count_row_of_an_eps_note_is_not_a_per_share_figure(label):
    assert not [m for m in map_line_item(table_type="profit_and_loss", line_item_raw=label) if m.canonical_field in {"eps_basic", "eps_diluted"}]


def test_cash_and_equivalents_and_other_bank_balances_stay_separate():
    cash = {m.canonical_field for m in map_line_item(table_type="balance_sheet", line_item_raw="(iii) Cash and cash equivalent")}
    other = {m.canonical_field for m in map_line_item(table_type="balance_sheet", line_item_raw="(iv) Bank balances other than cash and cash equivalents")}
    assert cash == {"cash_and_equivalents"} and other == {"other_bank_balances"}


@pytest.mark.parametrize("label, field", [("Dividend received", "dividend"), ("Unclaimed dividend", "dividend"), ("Purchase of treasury Shares", "buyback_paid")])
def test_income_liability_and_esop_lines_are_not_dividend_or_buyback_facts(label, field):
    assert field not in {m.canonical_field for m in map_line_item(table_type="cash_flow", line_item_raw=label)}


def test_shares_bought_back_is_the_buyback_cash_outflow():
    assert "buyback_paid" in {m.canonical_field for m in map_line_item(table_type="cash_flow", line_item_raw="Shares bought back including transaction cost")}


# ── document-level basis ──
def test_a_filing_with_no_subsidiaries_and_no_consolidated_statement_is_standalone():
    chunks = [chunk("Subsidiaries and Branches: The Company has no subsidiaries. Hence, there is no requirement to prepare Consolidated Financial Statements."), chunk("Balance Sheet as at March 31, 2026 Particulars")]
    assert _document_basis(chunks)[0] == "standalone"


def test_a_filing_with_both_statements_stays_unknown_so_table_level_basis_decides():
    chunks = [chunk("Consolidated Balance Sheet as at March 31, 2026"), chunk("Balance Sheet as at March 31, 2026")]
    assert _document_basis(chunks)[0] == "unknown"


# ── narrative disclosures ──
def test_a_completed_buyback_is_read_from_the_sentence_only_when_shares_times_price_reproduce_the_total():
    ok = chunk("The fourth buyback was completed, with 2 million shares repurchased at INR 875 per share for a total consideration of INR 175 Cr.", 73)
    bad = chunk("The buyback was completed, with 2 million shares repurchased at INR 875 per share for a total consideration of INR 150 Cr.", 74)
    assert [(d.amount_crore, d.issue_price, d.source_page) for d in buyback_disclosures_from_chunks([ok], "fy26")] == [(175.0, 875.0, 73)]
    assert buyback_disclosures_from_chunks([bad], "fy26") == []


def test_a_board_authorisation_is_not_a_paid_buyback():
    text = chunk("The Board approved the buyback of up to 20,00,000 shares at a price of INR 875 per equity share for an aggregate consideration not exceeding INR 17,500.00 lakhs.")
    assert buyback_disclosures_from_chunks([text], "fy26") == []


def test_per_share_dividends_are_read_with_their_kind_and_prior_year_comparatives_are_ignored():
    text = chunk("the Board declared an interim dividend of ₹ 11.00 (Rupees Eleven only) per equity share [previous year ₹ 10.50 (Rupees Ten and Paise Fifty only) per equity share]. It recommended a final dividend of ₹ 5.00 per equity share.", 50)
    got = sorted((d.action_subtype, d.per_share_amount) for d in dividend_disclosures_from_chunks([text], "fy26"))
    assert got == [("final", 5.0), ("interim", 11.0)]


def test_headline_metrics_are_kept_only_when_every_occurrence_agrees():
    agree = [chunk("Our deposits: we reported total deposits of ` 37,630 Crores, up 20%."), chunk("` 37,630 Crores Total Deposits 20% YoY")]
    clash = [chunk("` 1,000 Crores Total Deposits"), chunk("` 2,000 Crores Total Deposits")]
    assert [(m["metric_id"], m["value"]) for m in E.extract_headline_metrics(agree)["metrics"]] == [("total_deposits", 37630.0)]
    out = E.extract_headline_metrics(clash)
    assert out["metrics"] == [] and out["conflicts"][0]["metric_id"] == "total_deposits"


def test_a_headline_figure_never_overrides_a_statement_fact():
    stated = FinancialFact(metric_id="total_income", metric_name="x", fiscal_year="fy25", period="fy25", value=6000.0, unit="INR crore", basis="standalone", source_statement="profit_and_loss",
                           source_artifact="n", source_line_item="Total income", source_page=5, confidence="high", availability_status="present_direct", usable_downstream=True)
    facts = {"total_income": [stated]}
    _add_headline_metric_facts(facts, {"metrics": [{"metric_id": "total_income", "value": 7201.0, "unit": "INR crore", "source_page": 12, "source_line_item": "x"}]}, "fy25", "unknown")
    assert facts["total_income"] == [stated]


def test_a_signed_acquisition_is_signed_not_completed_and_completion_is_never_inferred():
    text = ("Subsequent to the close of the financial year, the company announced the proposed acquisition of Orion Co., a global firm. The transaction remains subject to shareholder and regulatory approvals. "
            "Signs Definitive Agreement to Acquire Orion The company will acquire all outstanding shares of Orion for US$ 14.00 per share in an all cash transaction with an enterprise valuation of US$ 11.75 Billion, The proposed acquisition is aligned with strategy.")
    (tx,) = E.extract_transaction_disclosures([chunk(text, 30)])["transactions"]
    assert tx["target"] == "Orion" and tx["status"] == "signed_pending_completion" and tx["terms_as_stated"].endswith("US$ 11.75 Billion") and "subject to shareholder" in tx["status_basis"]
    done = E.extract_transaction_disclosures([chunk(text + " The company completed the acquisition of Orion on 5 June.", 30)])["transactions"][0]
    assert done["status"] == "completed"


def test_an_acquisition_with_no_status_sentence_is_announced_not_pending_and_not_completed():
    (tx,) = E.extract_transaction_disclosures([chunk("The company announced the acquisition of Vega Ltd, a software firm.")])["transactions"]
    assert tx["status"] == "announced"


# ── capex that spans two cash-flow lines ──
def _fact(metric, value, line, basis="consolidated", page=386):
    return FinancialFact(metric_id=metric, metric_name=metric, fiscal_year="fy26", period="fy26", value=value, unit="INR crore", basis=basis, source_statement="cash_flow", source_artifact="raw",
                         source_line_item=line, source_page=page, confidence="high", availability_status="present_direct", usable_downstream=True)


def test_capex_is_the_sum_when_ppe_and_intangibles_are_separate_lines_and_fcf_is_rebuilt():
    facts = {"capex": [_fact("capex", -10.87, "Payments for acquisition of property plant and equipment")], "capex_ppe_cwip_cash_outflow": [_fact("capex_ppe_cwip_cash_outflow", -10.87, "Payments for acquisition of property plant and equipment")],
             "capex_intangible_cash_outflow": [_fact("capex_intangible_cash_outflow", -86.78, "Payments for acquisition of other intangibles")], "cfo": [_fact("cfo", 574.19, "Net cash from operating activities")],
             "fcf": [_fact("fcf", 563.32, "derived:fcf")]}
    _repair_capex_for_separate_intangibles(facts, "fy26")
    assert round(facts["capex"][0].value, 2) == -97.65 and round(facts["fcf"][-1].value, 2) == 476.54


def test_one_combined_line_is_never_counted_twice():
    line = "Purchase of property, plant and equipment and intangibles"
    facts = {"capex": [_fact("capex", -185.1, line)], "capex_ppe_cwip_cash_outflow": [_fact("capex_ppe_cwip_cash_outflow", -185.1, line)],
             "capex_intangible_cash_outflow": [_fact("capex_intangible_cash_outflow", -185.1, line)], "cfo": [_fact("cfo", 1455.1, "Net cash from operating activities")]}
    _repair_capex_for_separate_intangibles(facts, "fy26")
    assert facts["capex"][0].value == -185.1


def test_the_json_artifacts_are_valid_json(tmp_path):
    out = tmp_path / "x.json"
    out.write_text(json.dumps(E.extract_headline_metrics([chunk("` 5 Crores Total Deposits")])))
    assert json.loads(out.read_text())["metrics"][0]["metric_id"] == "total_deposits"


def test_a_row_on_a_continuation_page_is_cited_to_the_page_it_is_printed_on(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    pdf = tmp_path / "filing.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Balance sheet page one. Equity share capital 212 212")
    doc.new_page().insert_text((72, 72), "Continuation. Borrowings 1,234.50 980.00 Lease liabilities 4,092 4,423")
    doc.save(str(pdf))
    from types import SimpleNamespace

    def row(label, value, page):
        return SimpleNamespace(page=page, line_item_raw=label, values=[SimpleNamespace(value_raw=value)], warnings=[])

    result = SimpleNamespace(tables={"balance_sheet": [row("Equity share capital", "212", 1), row("Borrowings", "1,234.50", 1), row("Unprinted line", "999.99", 1)]})
    moved = E._resolve_exact_pages(result, pdf)
    pages = {r.line_item_raw: r.page for r in result.tables["balance_sheet"]}
    assert moved == 1 and pages == {"Equity share capital": 1, "Borrowings": 2, "Unprinted line": 1}      # unmatched rows keep the chunk page


def test_a_small_genuine_amount_after_a_note_reference_is_a_value_not_a_second_note_reference():
    text = "Particulars Note No. As at March 31, 2026 As at March 31, 2025 (iii) Cash and cash equivalent 12 16,497 13,831 (iv) Other bank balances 13 8 1,827 (v) Other financial assets 14 2,892 1,786"
    rows, _, _ = E._split_rows(E._trim_table_text(text, "balance_sheet"), "balance_sheet")
    assert dict(rows)["(iv) Other bank balances"] == ["8", "1,827"] and dict(rows)["(v) Other financial assets"] == ["2,892", "1,786"]


# Completion regressions: source shape, never a company-specific number.
def test_explicit_nil_borrowing_cells_are_zero_but_missing_cells_are_not():
    rows, _, _ = E._split_rows("Particulars Year ended March 31, 2027 Year ended March 31, 2026 Borrowings 12 - -", "balance_sheet")
    assert rows == [("Borrowings", ["-", "-"])]
    def build(primary):
        return E._build_row_objects(destination_table_type="balance_sheet", source_section_type="primary_balance_sheet_statement" if primary else "financial_note",
            statement_type="balance_sheet", source_artifact="clean_chunks.json", page=40, chunk_id="GENERIC",
            source_text="INR crores", table_text="As at March 31, 2027 As at March 31, 2026", row_pairs=rows, basis="standalone", score=20,
            warnings=[], is_primary_statement=primary)
    assert [v.value_crore for v in build(True)[0].values] == [0.0, 0.0]
    assert [v.value_raw for v in build(True)[0].values] == ["-", "-"]  # original nil notation survives
    assert [v.value_crore for v in build(False)[0].values] == [None, None]


def test_financial_liabilities_headers_do_not_turn_component_borrowings_into_a_total():
    assert [m.canonical_field for m in map_line_item(table_type="balance_sheet", line_item_raw="Liabilities Non-current Liabilities Financial liabilities Borrowings")] == ["long_term_debt"]
    assert [m.canonical_field for m in map_line_item(table_type="balance_sheet", line_item_raw="Current Liabilities Financial liabilities Borrowings")] == ["short_term_debt"]


def test_bank_interest_income_never_becomes_either_kind_of_cash():
    matches = map_line_item(table_type="balance_sheet", line_item_raw="Interest on Balances with Reserve Bank and Other inter-bank funds")
    assert not {m.canonical_field for m in matches} & {"cash_and_equivalents", "other_bank_balances"}


def test_explicit_npa_label_value_beats_an_unordered_scorecard_pair():
    out = E.extract_headline_metrics([chunk("23.8% Gross NPA Credit Cost chart"), chunk("Gross NPA ratio of 2.4% and Net NPA: 0.6%", 9)])
    assert next(x for x in out["metrics"] if x["metric_id"] == "gross_npa_ratio")["value"] == 2.4
    assert not out["conflicts"]


def test_total_branch_network_is_not_confused_with_regional_or_subset_counts():
    out = E.extract_headline_metrics([chunk("We serve customers through a network of 812 branches. A district has 24 branches; 30 branches offer a pilot service.")])
    assert next(x for x in out["metrics"] if x["metric_id"] == "branch_network")["value"] == 812


def test_a_missing_statement_placeholder_does_not_hide_a_reported_bank_highlight():
    missing = _fact("total_income", None, "")
    missing.availability_status, missing.usable_downstream = "missing", False
    facts = {"total_income": [missing]}
    _add_headline_metric_facts(facts, {"metrics": [{"metric_id":"total_income","value":8001,"unit":"INR crore","source_page":12,"source_line_item":"Total income INR 8,001 crore"}]}, "fy26", "standalone")
    assert any(f.value == 8001 and f.usable_downstream for f in facts["total_income"])


def test_reported_treasury_definition_is_not_the_statement_cash_definition():
    out = E.extract_headline_metrics([chunk("Cash and cash equivalents at INR 1,200 Cr post dividend and buyback of INR 300 Cr")])
    item = next(x for x in out["metrics"] if x["metric_id"] == "management_cash_and_liquid_investments")
    assert item["value"] == 1200
    assert not any(x["metric_id"] == "cash_and_equivalents" for x in out["metrics"])


def test_contingent_claims_and_segment_disclosures_keep_their_sources_and_units():
    out = E.extract_headline_metrics([chunk("All figures are in INR crores unless specifically stated otherwise", 1),
        chunk("The company operates only in a single segment dealing in instruments.", 3),
        chunk("Contingent liabilities As at March 31, 2027 As at March 31, 2026 Claims not acknowledged as debt Tax 2.11 3.20 Total 2.11 3.20", 40)])
    by = {x["metric_id"]:x for x in out["metrics"]}
    assert by["contingent_liabilities"]["value"] == 2.11 and by["contingent_liabilities"]["source_page"] == 40
    assert by["contingent_liabilities"]["source_statement"] == "financial_note"
    assert by["reportable_segment_count"]["value"] == 1 and by["reportable_segment_count"]["unit"] == "count"


def test_compact_eps_currency_rows_survive_the_existing_chunker():
    from scripts.smart_chunker import clean_paragraphs
    assert clean_paragraphs("Basic (in ₹) 8.4 7.6") == ["Basic (in ₹) 8.4 7.6"]



def test_a_preceding_fcf_figure_cannot_be_assigned_to_the_treasury_disclosure():
    out = E.extract_headline_metrics([chunk("Free cash flow was INR 477 Cr Cash and cash equivalents at INR 1,144 Cr post dividend and buyback of INR 340 Cr")])
    assert next(x for x in out["metrics"] if x["metric_id"] == "management_cash_and_liquid_investments")["value"] == 1144
    assert not out["conflicts"]


def test_equally_complete_headlines_keep_the_consolidated_preference():
    from knowledge.financials.basis import choose_preferred_basis
    views = {basis:{"profit_and_loss":{"revenue":{"value_crore":100},"pat":{"value_crore":10}}} for basis in ("standalone","consolidated","unknown")}
    views["standalone"]["profit_and_loss"]["other_income"] = {"value_crore":2}
    assert choose_preferred_basis(views)[0] == "consolidated"



def test_a_statement_mention_in_oci_does_not_trim_away_the_prior_pat_row():
    text = "Deferred Tax (0.81) 0.04 VII. Profit(Loss)for the period 91.21 52.11 VIII. Other Comprehensive Income not to be reclassified to Statement of Profit and Loss in subsequent periods: Gain (1.51) (1.21)"
    trimmed = E._trim_table_text(text, "profit_and_loss")
    assert "Profit(Loss)for the period 91.21 52.11" in trimmed
    rows, _, _ = E._split_rows(trimmed, "profit_and_loss")
    assert any("Profit(Loss)for the period" in label for label, _ in rows)



def test_recovered_bank_measures_reach_the_existing_trend_consumer(tmp_path):
    from knowledge.financials.trend_builder import build_financial_trends
    directory = tmp_path / "fy27/financials"; directory.mkdir(parents=True)
    facts = [{"metric_id":metric,"metric_name":metric,"fiscal_year":"fy27","period":"fy27","value":value,"unit":unit,"basis":"standalone",
              "source_statement":"management_highlights","source_artifact":"financial_headline_metrics.json","source_page":8,"confidence":"medium",
              "availability_status":"present_direct","usable_downstream":True,"warnings":[]} for metric,value,unit in [("revenue",100,"INR crore"),("pat",10,"INR crore"),("gross_npa_ratio",2.4,"%"),("branch_network",812,"count")]]
    (directory / "financial_fact_registry.json").write_text(json.dumps({"company":"acme","year":"fy27","available_facts":facts,"derived_facts":[],"partial_facts":[],"missing_facts":[],"unreliable_facts":[],"invalid_facts":[]}))
    intelligence = tmp_path / "fy27/intelligence"; intelligence.mkdir()
    for name in ("company_intelligence.json", "business_classification.json"):
        (intelligence / name).write_text(json.dumps({"company":"acme","year":"fy27","sector":"banking"}))
    report = build_financial_trends(company="acme",company_root=tmp_path)
    assert report.trend_groups["banking_measures"]["gross_npa_ratio"].series[0].value == 2.4
    assert report.trend_groups["banking_measures"]["branch_network"].series[0].value == 812



def test_capital_memory_consumes_the_canonical_aggregate_not_the_ppe_only_line(tmp_path):
    from knowledge.financials.memory_builder import build_capital_allocation_financial_timeline
    directory = tmp_path / "fy27/financials"; directory.mkdir(parents=True)
    (directory / "normalized_fundamentals.json").write_text(json.dumps({"cash_flow":{"capex":{"value_crore":-11},"cfo":{"value_crore":574}},"balance_sheet":{}}))
    facts = [{"metric_id":metric,"fiscal_year":"fy27","value":value,"usable_downstream":True} for metric,value in [("capex",-97),("fcf",477),("total_debt",0)]]
    (directory / "financial_fact_registry.json").write_text(json.dumps({"available_facts":facts,"derived_facts":[],"basis_variants":[{"metric_id":"capex","value":-5}]}))
    row = build_capital_allocation_financial_timeline(company="acme",company_root=tmp_path,years_used=["fy27"])["timeline"][0]
    assert row["capex"]["value"] == -97 and row["fcf"]["value"] == 477 and row["debt"]["value"] == 0
    assert row["capex"]["source_artifact"] == "financial_fact_registry.json"



def test_a_canonical_annual_capex_total_cannot_inherit_a_ppe_only_event_name():
    from intelligence.capital_allocation_outcomes.builder import _candidate_from_item, _build_allocation_group, _merge_group, _finalize_allocation_record
    old = _candidate_from_item("fy27", {"value":"Capex added to PPE (gross block)","amount":27,"source_item_id":"old","source_artifact":"company_intelligence.json","canonical_category":"capex"}, "true_capital_deployment", {})
    total = _candidate_from_item("fy27", {"value":"Capital expenditure","amount":72,"source_item_id":"capex_fy27","source_artifact":"financial_fact_registry.json","canonical_category":"capex"}, "true_capital_deployment", {})
    assert old is not None and total is not None
    group = _build_allocation_group(old); _merge_group(group,total)
    record, _, _ = _finalize_allocation_record("acme","CAO-1",group,{"projects":[],"capacity":[],"commitments":[],"risks":[]}, {})
    assert record["amount"] == 72 and record["amount_period"] == "fy27"
    assert record["allocation_name"] == "Reported annual capital expenditure"


# ── G3.1: generalisation to an unfamiliar filing ──
def test_a_statement_title_that_follows_the_previous_pages_signoff_still_identifies_the_statement():
    signoff = "The accompanying notes form an integral part of the financial statements. In terms of our report of even date For and on behalf of the Board of Directors Chartered Accountants Place : Mumbai Date : April 23, 2025"
    rows = " ".join(f"Line item {i} {i + 3} {100 + i}.25 {90 + i}.10" for i in range(14))
    text = f"{signoff} Balance Sheet as at March 31, 2025 (All amounts in INR lakhs, unless otherwise stated) Particulars Notes As at March 31, 2025 As at March 31, 2024 ASSETS Non-current assets {rows} Total assets 3,394.03 3,300.00"
    best = max(_category_candidates(text), key=lambda item: item[2])
    assert best[0] == "primary_balance_sheet_statement"


@pytest.mark.parametrize("declaration", ["(All amounts in INR lakhs, unless otherwise stated)", "(All amounts are in INR lakhs unless otherwise stated)", "(INR in lakhs)"])
def test_a_declared_money_unit_survives_the_words_per_share_in_the_same_statement(declaration):
    text = f"Statement of Profit and Loss {declaration} Particulars Revenue 31,068.73 Earnings per equity share (Nominal value per share INR 1/-) Basic 13.02 9.90"
    assert E._unit_hint(text, "profit_and_loss") == "lakhs"


def test_without_a_declared_unit_a_per_share_table_stays_per_share():
    assert E._unit_hint("Earnings per share Basic 13.02 9.90", "profit_and_loss") == "per share"
    assert E._unit_hint("Nominal value per share INR 1/- Basic 13.02", "eps") == "INR per share"


def test_a_row_enumerator_after_a_complete_row_is_not_a_third_value_column():
    text = "Particulars Notes Year ended March 31, 2025 Year ended March 31, 2024 Earnings per equity share (1) Basic 38(16) 13.02 9.90 (2) Diluted 38(16) 13.02 9.90"
    rows, _, _ = E._split_rows(E._trim_table_text(text, "profit_and_loss"), "profit_and_loss")
    assert dict(rows) == {"Basic": ["13.02", "9.90"], "Diluted": ["13.02", "9.90"]}


# ── G3.1: the minimum anchor-family coverage contract ──
def _row(label, value="1.0", page=1, section="primary_statement"):
    return {"line_item_raw": label, "values": [{"period": "FY25", "value_raw": value}], "page": page, "source_section_type": section}


def test_coverage_distinguishes_found_not_extracted_and_not_disclosed_and_never_invents_an_absence():
    from knowledge.financials.anchor_coverage import build_anchor_coverage, extraction_status

    tables = {"profit_and_loss": [_row("Revenue from operations")], "balance_sheet": [_row("Total equity"), _row("Borrowings", "-")], "cash_flow": [_row("Net cash from operating activities"), _row("Dividend paid", "(5.0)")]}
    chunks = [chunk("The company operates in a single reportable segment."), chunk("Contingent liabilities not provided for: claims against the company Rs 6.92 Cr", 9), chunk("Balance sheet, statement of profit and loss, cash flows", 3)]
    cov = build_anchor_coverage(chunks=chunks, raw_tables={"tables": tables}, year="fy25")
    fam = {k: v["status"] for k, v in cov["families"].items()}
    assert fam["primary_statements"] == "FOUND" and fam["capital_allocation"] == "FOUND" and fam["segments_and_geography"] == "FOUND"
    assert fam["risks_and_contingencies"] == "NOT_EXTRACTED"                                    # the filing mentions it, no row was extracted
    assert fam["material_transactions"] == "NOT_DISCLOSED_WITH_SEARCH_EVIDENCE"                 # searched, never mentioned
    assert cov["families"]["material_transactions"]["search"]["chunks_searched"] == 3 and cov["completeness"] == "INCOMPLETE"
    assert extraction_status("READY", cov) == "READY_STATEMENTS_ONLY" and extraction_status("BLOCKED", cov) == "BLOCKED"


def test_a_bank_has_no_industrial_borrowings_test_and_guidance_without_a_register_is_not_called_found():
    from knowledge.financials.anchor_coverage import build_anchor_coverage

    tables = {"profit_and_loss": [_row("Interest earned", section="schedule_13")], "balance_sheet": [_row("Total liabilities")], "cash_flow": [_row("Net cash from operating activities")]}
    cov = build_anchor_coverage(chunks=[chunk("We will open new branches. Outlook for next year is positive.")], raw_tables={"tables": tables}, year="fy25")
    assert cov["families"]["cash_flow_and_borrowings"]["status"] == "FOUND"
    assert cov["families"]["guidance_and_commitments"]["status"] == "NOT_EXTRACTED" and "not supplied" in cov["families"]["guidance_and_commitments"]["note"]
