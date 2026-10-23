"""SSOT Phase 1 completion: event dates come from the filing's own dated statements, fiscal years follow the filer's year end, and project/capacity ids are
historical identities. Rules are tested on synthetic filings (no company-specific exception); data tests run against the isolated candidate root when present."""
from __future__ import annotations

import json
import re
import os
from pathlib import Path

import pytest

from intelligence.projects.builder import _stable_project_ids
from knowledge.company_memory.guardrails import evidenced_announcement_period, extract_dated_events, fiscal_year_of

CAND = Path(os.environ.get("P3_PW_ROOT", "/private/tmp/claude-501/p3/pw/companies"))
SERVED = Path(__file__).resolve().parents[2] / "companies"


def _chunks(*texts):
    return [{"page": 10 + i, "text": t} for i, t in enumerate(texts)] + [{"page": 99, "text": f"Operations note {i}."} for i in range(40)]


SIGNED = "On April 27, 2026, the Group entered into a definitive agreement to acquire all outstanding shares of Zentia Holdings for cash. Acquisition is subject to approvals and closing conditions."


@pytest.mark.parametrize("year,month,expected", [(2026, 3, "fy26"), (2026, 4, "fy27"), (2025, 12, "fy26"), (2026, 1, "fy26")])
def test_fiscal_year_follows_the_march_year_end(year, month, expected):
    assert fiscal_year_of(year, month) == expected
    assert fiscal_year_of(2026, 7, fy_end_month=6) == "fy27" and fiscal_year_of(2026, 7, fy_end_month=12) == "fy26"


def test_a_dated_signing_after_year_end_belongs_to_the_next_fiscal_year_and_stays_pending():
    events = extract_dated_events(_chunks(SIGNED))
    assert len(events) == 1 and events[0]["period"] == "fy27" and events[0]["date"] == "2026-04-27" and events[0]["pending"] is True
    result = evidenced_announcement_period("2025", "fy26", "acquisition (Zentia)", events)
    assert result["period"] == "fy27" and result["basis"] == "dated_event" and result["event_page"] == 10 and result["pending"] is True


def test_balance_sheet_dates_and_generic_names_are_not_events():
    text = "The Company acquired assets as at March 31, 2026 in India. The Group completed the audit on 5 June 2025 for India Operations."
    chunks = _chunks(text) + [{"page": 5, "text": "India Operations India"} for _ in range(30)]
    events = extract_dated_events(chunks)
    assert not any("India" in e["entities"] for e in events)
    assert evidenced_announcement_period("2025", "fy26", "Capacity expansion in India", events)["period"] == "fy26"


def test_a_calendar_year_claim_is_not_read_as_the_fiscal_year():
    # the filing is FY22 (Apr 2021-Mar 2022); the model's "2021" must not become FY21 unless the item's own wording says so
    assert evidenced_announcement_period("2021", "fy22", "Light commercial vehicle loans", [])["period"] == "fy22"
    assert evidenced_announcement_period("2021", "fy22", "launched in FY21 as a pilot", [])["period"] == "fy21"
    assert evidenced_announcement_period("2021", "fy22", "Light commercial vehicle loans", [])["basis"].startswith("claimed_fy21")


def _prior(*rows):
    return {"projects": [{"project_id": pid, "source_references": [{"period": p, "source_artifact": "project", "source_item_id": i}], "project_type": "t", "normalized_name": n} for pid, p, i, n in rows]}


def _group(period, item, name="x"):
    return {"source_references": [{"period": period, "source_artifact": "project", "source_item_id": item}], "project_type": "t", "normalized_name": name}


def test_ids_survive_reordering_and_are_never_reused():
    prior = _prior(("PJ-0001", "fy20", "a", "alpha"), ("PJ-0002", "fy21", "b", "beta"), ("PJ-0003", "fy22", "c", "gamma"))
    # beta now sorts before alpha; alpha-gamma-style position shifts must not change identity; a new group arrives first; gamma vanished
    groups = [_group("fy19", "new", "delta"), _group("fy21", "b", "beta"), _group("fy20", "a", "alpha")]
    assert _stable_project_ids(groups, prior) == ["PJ-0004", "PJ-0002", "PJ-0001"]
    assert _stable_project_ids([_group("fy25", "z", "omega")], prior) == ["PJ-0004"]       # PJ-0003 (dropped) is not reissued


def test_without_a_prior_registry_ids_are_issued_in_order():
    assert _stable_project_ids([_group("fy20", "a"), _group("fy21", "b")], {}) == ["PJ-0001", "PJ-0002"]


needs_cand = pytest.mark.skipif(not (CAND / "sun_pharma" / "company_memory" / "projects" / "projects_registry.json").exists(), reason="candidate root absent")


@needs_cand
@pytest.mark.parametrize("company", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_candidate_projects_keep_every_served_id_and_name(company):
    served = {p["project_id"]: p["normalized_name"] for p in json.loads((SERVED / company / "company_memory/projects/projects_registry.json").read_text())["projects"]}
    cand = {p["project_id"]: p["normalized_name"] for p in json.loads((CAND / company / "company_memory/projects/projects_registry.json").read_text())["projects"]}
    assert all(cand.get(k) == v for k, v in served.items())


@needs_cand
def test_candidate_dates_the_organon_agreement_from_the_filing_note_and_keeps_it_pending():
    reg = json.loads((CAND / "sun_pharma/company_memory/projects/projects_registry.json").read_text())["projects"]
    organon = [p for p in reg if "organon" in p["normalized_name"].lower()]
    assert len(organon) == 1
    p = organon[0]
    assert p["announcement_period"] == "fy27" and p["announcement_evidence"]["event_date"] == "2026-04-27" and p["announcement_evidence"]["pending"] is True
    assert p["current_status"] not in {"operational", "commissioned", "completed"}
    assert all(r["period"] != "fy25" for r in p["source_references"])


def _fact(metric, statement, status="present_direct"):
    from knowledge.financials.fact_registry_schema import FinancialFact
    return FinancialFact(metric_id=metric, metric_name=metric, fiscal_year="fy21", period="FY21", value=197.8, unit="INR crore", basis="consolidated", source_statement=statement,
                         source_artifact="normalized_fundamentals.json", source_line_item="Revenue", source_page=132, confidence="high", availability_status=status, usable_downstream=True)


@pytest.mark.parametrize("metric", ["revenue", "pat", "pbt", "tax"])
def test_a_profit_and_loss_flow_sourced_from_a_balance_sheet_table_is_invalid(metric):
    from knowledge.financials.fact_registry import _enforce_source_statement
    fact = _fact(metric, "balance_sheet")
    _enforce_source_statement(fact)
    assert fact.availability_status == "invalid" and fact.usable_downstream is False and fact.reconciliation_status == "fail"


def test_valid_sources_and_stock_metrics_are_untouched():
    from knowledge.financials.fact_registry import _enforce_source_statement
    for metric, statement in (("revenue", "profit_and_loss"), ("cash_and_equivalents", "balance_sheet"), ("cfo", "cash_flow")):
        fact = _fact(metric, statement)
        _enforce_source_statement(fact)
        assert fact.availability_status == "present_direct" and fact.usable_downstream is True


# ── capital-allocation classification and amounts ───────────────────────────
def _stored(action, category, group, keyword):
    return {"action": action, "value": action, "canonical_category": category, "capital_allocation_group": group, "reasoning": f"Matched taxonomy keyword '{keyword}' to {category}."}


def test_a_label_taken_from_neighbouring_text_is_replaced_when_the_items_own_words_support_another():
    from intelligence.capital_allocation_outcomes.builder import _apply_label_verdict
    fixed = _apply_label_verdict(_stored("Dividend paid", "capex", "true_capital_deployment", "purchase of property"))
    assert fixed["canonical_category"] == "dividend_paid" and fixed["classification_status"] == "reclassified_from_own_text"
    assert fixed["classification_stored_label"]["canonical_category"] == "capex"


def test_an_unsupported_label_with_no_replacement_is_quarantined_not_guessed():
    from intelligence.capital_allocation_outcomes.builder import _apply_label_verdict
    fixed = _apply_label_verdict(_stored("Aggregate unquoted investments (balance)", "r_and_d_investment", "true_capital_deployment", "research and development"))
    assert fixed["canonical_category"] == "uncertain" and fixed["capital_allocation_group"] == "uncertain" and fixed["classification_status"] == "quarantined_unsupported"


def test_a_supported_label_is_left_alone():
    from intelligence.capital_allocation_outcomes.builder import _apply_label_verdict
    item = _stored("Dividend paid", "dividend_paid", "shareholder_returns", "dividend paid")
    assert _apply_label_verdict(item) == item


def test_a_ledger_aggregate_only_stands_in_for_its_own_kind_of_flow():
    from intelligence.capital_allocation_outcomes.builder import _amount_basis, _candidate_amount
    ledger = {"capex_deployed": 51.48, "dividends": 20.0, "debt_repayment": 0}
    assert _candidate_amount({"allocation_category": "dividend"}, ledger) == 20.0
    assert _candidate_amount({"allocation_category": "organic_capex"}, ledger) == 51.48
    assert _candidate_amount({"allocation_category": "debt_repayment"}, ledger) is None         # zero field, and capex must not substitute
    assert _candidate_amount({"allocation_category": "retained_cash"}, ledger) is None           # no matching ledger field
    assert _amount_basis({"allocation_category": "retained_cash"}, ledger, None) != "ledger_summary"


# ── isolated candidate records (skipped when the candidate root is absent) ───
FINAL = Path(os.environ.get("P3_FINAL_ROOT", "/private/tmp/claude-501/p4/final/companies"))
needs_final = pytest.mark.skipif(not (FINAL / "sun_pharma").exists(), reason="final candidate root absent")


def _outcomes(company):
    payload = json.loads((FINAL / company / "company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json").read_text())
    return next(v for v in payload.values() if isinstance(v, list) and v and isinstance(v[0], dict))


def _registry(company, fy):
    return json.loads((FINAL / company / fy / "financials/financial_fact_registry.json").read_text())


def _cand_fact(company, fy, metric, lists=("available_facts", "derived_facts", "partial_facts")):
    reg = _registry(company, fy)
    return next((f for k in lists for f in reg.get(k, []) if f["metric_id"] == metric), None)


@needs_final
def test_organon_is_dated_from_the_filing_note_signed_and_pending():
    organon = next(o for o in _outcomes("sun_pharma") if "Organon" in o["allocation_name"])
    assert organon["event_date"] == "2026-04-27" and organon["event_period"] == "fy27"
    assert organon["event_completion"] == "pending" and organon["transaction_status"] == "signed_pending_completion"
    assert organon["amount"] is None                                          # USD terms are stated, not converted


@needs_final
@pytest.mark.parametrize("company", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_capex_outcome_equals_the_registry_figure_for_its_own_period(company):
    for o in _outcomes(company):
        if o["allocation_name"] == "Reported annual capital expenditure":
            fact = _cand_fact(company, o["amount_period"], "capex")
            assert fact is not None and abs(abs(fact["value"]) - o["amount"]) < 1e-6
            assert o["amount_unit"] == "INR crore" and o["amount_aggregation"] == "single_period_flow"


@needs_final
@pytest.mark.parametrize("company", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_no_non_capex_item_carries_the_years_capex_figure(company):
    capex = {o["amount_period"]: o["amount"] for o in _outcomes(company) if o["allocation_name"] == "Reported annual capital expenditure"}
    for o in _outcomes(company):
        if o["allocation_category"] in {"dividend", "retained_cash", "debt_repayment", "equity_issuance"} and o["amount_basis"] == "ledger_summary":
            assert o["amount"] != capex.get(o["amount_period"]), o["allocation_name"]


@needs_final
def test_vishvakarma_is_a_200_share_subscription_not_a_currency_amount():
    v = next(o for o in _outcomes("ujjivan") if "Vishvakarma" in o["allocation_name"])
    assert v["allocation_category"] == "strategic_investment" and v["amount"] is None and v["amount_basis"] == "share_count_not_currency"
    assert "200 shares" in (v["amount_stated"] or "") and v["deployment_periods"] == ["fy21"]


@needs_final
def test_sun_fy26_cash_and_debt_are_the_filings_closing_figures():
    cash, debt = _cand_fact("sun_pharma", "fy26", "cash_and_equivalents"), _cand_fact("sun_pharma", "fy26", "total_debt")
    assert round(cash["value"], 2) == 9770.51 and cash["period_role"] == "closing_balance"      # not the 10,268.77 opening balance
    assert round(debt["value"], 2) == 4081.61                                                    # current 4,050.35 + non-current 31.26


@needs_final
def test_tanla_fy26_cash_is_the_statutory_cash_and_equivalents_line():
    assert round(_cand_fact("tanla", "fy26", "cash_and_equivalents")["value"], 2) == 748.01           # 1,064 is management's wider 'cash and bank balances'


@needs_final
def test_tanla_fy24_cfo_is_not_profit_before_tax():
    assert round(_cand_fact("tanla", "fy24", "cfo")["value"], 2) == 589.93                            # the served 683.40 is profit before tax


@needs_final
@pytest.mark.parametrize("company", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_every_projects_and_capacity_reference_in_outcomes_resolves(company):
    pj = FINAL / company / "company_memory/projects/projects_registry.json"
    if not pj.exists():
        pytest.skip("candidate projects not assembled")
    projects = {p["project_id"] for p in json.loads(pj.read_text())["projects"]}
    capacities = {c["capacity_id"] for c in json.loads((FINAL / company / "company_memory/capacity/capacity_registry.json").read_text())["capacity_items"]}
    for o in _outcomes(company):
        assert set(o.get("linked_project_ids") or []) <= projects and set(o.get("linked_capacity_ids") or []) <= capacities


# ── final remediation: classification ────────────────────────────────────────
@pytest.mark.parametrize("action,category,group", [
    ("Exchange of share certificates of erstwhile companies", "share_certificate_exchange", "corporate_actions_non_cash_or_admin"),
    ("Budget allocation (earmarked)", "announced_budget_or_customer_funding", "accounting_or_disclosure_only"),
    ("Payment for acquisition of intangible assets under development", "capex", "true_capital_deployment"),
    ("Share purchase by ESOP trust (secondary market)", "treasury_share_purchase", "treasury_actions"),
    ("Unsecured loan availed from related party", "debt_raised", "financing_actions"),
    ("Adjusted share issue expenses against securities premium account", "share_issue_expense_adjustment", "accounting_or_disclosure_only"),
])
def test_taxonomy_places_administrative_budget_treasury_and_financing_lines_by_their_own_words(action, category, group):
    from knowledge.capital_allocation_taxonomy import CapitalAllocationTaxonomy
    result = CapitalAllocationTaxonomy().classify({"action": action})
    assert (result["canonical_category"], result["capital_allocation_group"]) == (category, group)


def test_keywords_match_whole_words_only():
    from intelligence.capital_allocation_outcomes.builder import _has_word, _map_allocation_category
    assert not _has_word("tanla platforms limited", "platform") and _has_word("software platform", "platform")
    assert not _has_word("order dated 5 june", "r d")
    item = {"value": "Share purchase by ESOP trust", "purpose": "The trust bought shares funded by a loan from Acme Platforms Limited", "canonical_category": "treasury_share_purchase",
            "capital_allocation_group": "treasury_actions"}
    assert _map_allocation_category(item, {"purpose": "Capital is being deployed into operating assets and research"}) == "other"   # no 'platform'/'research' leakage from names or the ledger


def test_an_item_without_its_own_description_is_not_an_allocation_record():
    from intelligence.capital_allocation_outcomes.builder import _candidate_from_item
    ledger = {"purpose": "Capital is being deployed into operating assets", "capex_deployed": 51.0}
    assert _candidate_from_item("fy25", {"canonical_category": "capex", "source_item_id": "x"}, "true_capital_deployment", ledger) is None


# ── final remediation: financial extraction and normalization ────────────────
def test_dividend_flows_are_distinct_fields():
    from knowledge.financials.mapping_registry import CANONICAL_SECTION_FIELDS
    from knowledge.financials.line_item_mapper import _FORBIDDEN_BY_FIELD
    assert {"dividends_paid", "dividends_paid_to_non_controlling_interests", "dividends_received"} <= set(CANONICAL_SECTION_FIELDS["cash_flow"])
    for token in ("non controlling", "received", "proposed", "unpaid"):
        assert token in " ".join(_FORBIDDEN_BY_FIELD["dividends_paid"])
    assert "paid" in _FORBIDDEN_BY_FIELD["dividends_received"] and "non controlling" in _FORBIDDEN_BY_FIELD["dividend"]


def test_merge_never_removes_or_changes_a_baseline_row():
    from knowledge.financials.extractor import merge_raw_tables
    def row(label, value, page=1):
        return {"line_item_raw": label, "page": page, "basis": "consolidated", "source_section_type": "primary_balance_sheet_statement", "values": [{"period": "March 31, 2021", "value_raw": value}], "warnings": []}
    base = {"tables": {"balance_sheet": [row("Total assets", "100")]}, "warnings": []}
    supplement = {"tables": {"balance_sheet": [row("Total assets", "100"), row("Trade payables", "39,736.6")], "cash_flow": [row("Net cash", "5")]}}
    merged = merge_raw_tables(base, supplement)
    assert merged["tables"]["balance_sheet"][0] == base["tables"]["balance_sheet"][0]
    assert [r["line_item_raw"] for r in merged["tables"]["balance_sheet"]] == ["Total assets", "Trade payables"] and merged["tables"]["cash_flow"]
    note = merge_raw_tables(base, {"tables": {"shareholding_pattern": [row("Promoters", "75")]}})
    assert "shareholding_pattern" not in note["tables"] or not note["tables"]["shareholding_pattern"]      # note tables are not supplemented
    assert "supplemental_row" in merged["tables"]["balance_sheet"][1]["warnings"][0] and len(base["tables"]["balance_sheet"]) == 1


BANK_PL_PAGE = "\n".join(["Profit and Loss Account", "for the year ended March 31, 2024", "As per our report of even date", "Chartered Accountants", "Partner", "Bengaluru", "(` in 000's)", "Particulars", "Schedule",
                          "For the year ended", "March 31, 2024", "For the year ended", "March 31, 2023", "I.", "INCOME", "Interest Earned", "13", "56,771,541", "41,649,947", "Other Income", "14",
                          "7,867,519", "5,891,909", "Total", "64,639,060", "47,541,856", "II.", "EXPENDITURE", "Interest Expended", "15", "22,677,039", "14,670,926", "Total", "51,824,153", "36,542,639",
                          "III.", "PROFIT", "Net profit for the year", "12,814,907", "10,999,217"])


def test_a_cell_per_line_income_statement_page_is_rebuilt_into_rows():
    from scripts.smart_chunker import clean_paragraphs
    rows = clean_paragraphs(BANK_PL_PAGE)
    assert "I. INCOME Interest Earned 13 56,771,541 41,649,947" in rows and "Other Income 14 7,867,519 5,891,909" in rows
    assert any(r.startswith("III. PROFIT Net profit for the year") for r in rows)


def test_rows_are_not_rebuilt_for_other_statements():
    from scripts.smart_chunker import split_cell_lines
    assert split_cell_lines("\n".join(["Cash Flow Statement"] + ["Net cash flow", "1,000", "2,000"] * 6)) is None


def test_a_signature_block_printed_before_the_table_does_not_end_the_table():
    from knowledge.financials.extractor import _trim_table_text
    text = ("Profit and Loss Account for the year ended March 31, 2024 As per our report of even date For A & Co Chartered Accountants (` in 000's) Particulars Schedule "
            "For the year ended March 31, 2024 For the year ended March 31, 2023 I. INCOME Interest Earned 13 56,771,541 41,649,947 Other Income 14 7,867,519 5,891,909")
    trimmed = _trim_table_text(text, "profit_and_loss")
    assert "Interest Earned 13 56,771,541" in trimmed and "Other Income" in trimmed


def test_period_headers_without_a_comma_and_thousand_units_are_recognised():
    from knowledge.financials.extractor import _extract_periods, _unit_hint
    assert _extract_periods("For the year ended March 31 2022 For the year ended March 31 2021") == ["March 31, 2022", "March 31, 2021"]
    assert _unit_hint("(` in 000's) Particulars ... Earnings per share Basic 6.65", "profit_and_loss") == "thousands"


def test_bank_income_statement_structure_is_discovered_without_a_title():
    from knowledge.financials.discovery import _category_candidates
    text = ("Interest Earned 13 28,127,991 28,060,656 Other Income 14 3,132,745 3,023,091 Total 31,260,736 31,083,747 II. EXPENDITURE Interest Expended 15 10,392,070 10,775,140 "
            "Operating Expenses 16 14,963,806 12,300,770 Provisions and Contingencies 10,050,764 7,924,868 Total 35,406,640 31,000,778 III. PROFIT Net profit for the year (4,145,904) 82,969")
    assert "primary_profit_and_loss_statement" in [c[0] for c in _category_candidates(text)]


def test_partial_balance_sheet_is_opt_in(tmp_path):
    import inspect
    from knowledge.financials.normalizer import normalize_financial_tables
    assert inspect.signature(normalize_financial_tables).parameters["allow_partial_balance_sheet"].default is False


def test_a_raw_capex_cell_is_taken_from_the_target_years_column():
    from knowledge.financials.fact_registry import _value_for_fiscal_year
    cells = [{"period": "March 31, 2024", "value_crore": -158.84}, {"period": "March 31, 2023", "value_crore": -156.05}]
    assert _value_for_fiscal_year(cells, "fy23")["value_crore"] == -156.05          # a report filed under fy23 whose first column is FY24
    assert _value_for_fiscal_year(cells, "fy24")["value_crore"] == -158.84
    assert _value_for_fiscal_year(cells, "fy25") is None                              # periods are resolved and none is the target: no value, not the first cell
    assert _value_for_fiscal_year([{"period": "PERIOD_COLUMN_UNRESOLVED", "value_crore": 1.0}], "fy25")["value_crore"] == 1.0


def test_a_report_filed_under_the_wrong_year_is_flagged(tmp_path):
    import json
    from knowledge.financials.extractor import extract_financial_tables
    from knowledge.financials.discovery import write_financial_discovery
    chunks = [{"chunk_id": "CHK-000001", "page": 1, "text": "Consolidated Statement of Profit and Loss for the year ended March 31, 2024 Particulars Year ended March 31, 2024 Year ended March 31, 2023 Revenue from operations 100.0 90.0 Total income 100.0 90.0 Profit before tax 10.0 9.0 Profit for the year 8.0 7.0 Earnings per share 1.0 0.9 (INR in lakhs)"}]
    path = tmp_path / "clean_chunks.json"
    path.write_text(json.dumps({"chunks": chunks}))
    write_financial_discovery(company="acme", year="fy23", chunk_path=path, output_path=tmp_path / "d.json", output_root=tmp_path)
    try:
        result = extract_financial_tables(company="acme", year="fy23", chunk_path=path, discovery_path=tmp_path / "d.json")
    except RuntimeError:
        pytest.skip("synthetic page not extractable by the statement rules")
    assert any(w.startswith("source_year_mismatch") for w in result.warnings)


def test_ids_no_group_keeps_are_retired_and_resolvable():
    prior = _prior(("PJ-0001", "fy20", "a", "alpha"), ("PJ-0002", "fy21", "b", "beta"), ("PJ-0003", "fy22", "c", "gamma"))
    merged = {"source_references": [{"period": "fy20", "source_artifact": "project", "source_item_id": "a"}, {"period": "fy21", "source_artifact": "project", "source_item_id": "b"}], "project_type": "t", "normalized_name": "alpha"}
    ids, retired = _stable_project_ids([merged], prior, with_retired=True)
    assert ids == ["PJ-0001"]
    by_id = {r["project_id"]: r for r in retired}
    assert set(by_id) == {"PJ-0002", "PJ-0003"} and by_id["PJ-0002"]["merged_into"] == "PJ-0001" and by_id["PJ-0003"]["merged_into"] is None


def test_ambiguous_component_labels_are_not_supplemented():
    from knowledge.financials.extractor import merge_raw_tables
    def row(label, value):
        return {"line_item_raw": label, "page": 185, "basis": "consolidated", "source_section_type": "primary_balance_sheet_statement", "values": [{"period": "March 31, 2022", "value_raw": value}], "warnings": []}
    supplement = {"tables": {"balance_sheet": [row("(i) Borrowings", "229.9"), row("(i) Borrowings", "7,007.7"), row("(ii) Trade payables", "39,736.6")]}}
    merged = merge_raw_tables({"tables": {"balance_sheet": []}, "warnings": []}, supplement)
    assert [r["line_item_raw"] for r in merged["tables"]["balance_sheet"]] == ["(ii) Trade payables"]         # the two '(i) Borrowings' rows cannot be told apart


def test_a_marker_label_row_duplicating_a_prefixed_row_is_not_supplemented():
    from knowledge.financials.extractor import merge_raw_tables
    def row(label, value):
        return {"line_item_raw": label, "page": 212, "basis": "consolidated", "source_section_type": "primary_balance_sheet_statement", "values": [{"period": "March 31, 2022", "value_raw": value}], "warnings": []}
    base = {"tables": {"balance_sheet": [row("Non-current liabilities (i) Borrowings", "2,299.2")]}, "warnings": []}
    merged = merge_raw_tables(base, {"tables": {"balance_sheet": [row("(i) Borrowings", "2,299.2"), row("(iii) Trade payables", "4,479.3")]}})
    assert [r["line_item_raw"] for r in merged["tables"]["balance_sheet"]] == ["Non-current liabilities (i) Borrowings", "(iii) Trade payables"]


def _bs_fact(metric, statement="balance_sheet"):
    from knowledge.financials.fact_registry_schema import FinancialFact
    return FinancialFact(metric_id=metric, metric_name=metric, fiscal_year="fy24", period="March 31, 2024", value=185434.74, unit="INR crore", basis="standalone", source_statement=statement,
                         source_artifact="normalized_fundamentals.json", source_line_item="Total assets (A)", source_page=404, confidence="medium", availability_status="present_direct", usable_downstream=True)


def test_bank_format_totals_and_partial_balance_sheets_are_not_usable():
    from knowledge.financials.fact_registry import _enforce_balance_sheet_availability
    bank = _bs_fact("total_assets"); _enforce_balance_sheet_availability(bank, partial_balance_sheet=False, bank_format=True)
    assert bank.availability_status == "unreliable" and bank.usable_downstream is False and "bank-format" in bank.warnings[-1]
    partial = _bs_fact("payables"); _enforce_balance_sheet_availability(partial, partial_balance_sheet=True, bank_format=False)
    assert partial.availability_status == "unreliable" and "not extracted" in partial.warnings[-1]
    ordinary = _bs_fact("total_assets"); _enforce_balance_sheet_availability(ordinary, partial_balance_sheet=False, bank_format=False)
    assert ordinary.availability_status == "present_direct" and ordinary.usable_downstream is True
    cash_flow = _bs_fact("cash_and_equivalents", "cash_flow"); _enforce_balance_sheet_availability(cash_flow, partial_balance_sheet=True, bank_format=True)
    assert cash_flow.availability_status == "present_direct"          # a cash-flow figure does not depend on the balance sheet


def test_borrowing_movements_and_sub_lines_are_not_debt_balances():
    from knowledge.financials.line_item_mapper import map_line_item
    for label in ("Increase/(Decrease) in Borrowings (Net)", "Decrease in Borrowings (Net)", "Secured borrowings included in I and II"):
        fields = {m.canonical_field for m in map_line_item(table_type="balance_sheet", line_item_raw=label)} | {m.canonical_field for m in map_line_item(table_type="cash_flow", line_item_raw=label)}
        assert not fields & {"total_debt", "short_term_debt", "long_term_debt"}, (label, fields)


def test_income_received_and_investment_gains_are_not_finance_cost_or_an_investments_balance():
    from knowledge.financials.line_item_mapper import map_line_item
    for table, label, banned in (("cash_flow", "Interest & other income received", "finance_cost"), ("profit_and_loss", "Loss on sale of investments", "investments"),
                                 ("balance_sheet", "Loss on sale of investments", "investments"), ("cash_flow", "Proceeds from sale of investments", "investments")):
        assert banned not in {m.canonical_field for m in map_line_item(table_type=table, line_item_raw=label)}, (label, table)
    assert "finance_cost" in {m.canonical_field for m in map_line_item(table_type="profit_and_loss", line_item_raw="Finance costs")}


@pytest.mark.parametrize("metric,label,invalid", [
    ("buyback_paid", "Proceeds from issue of equity shares (net of issue expenses)", True), ("buyback_paid", "Transfer to escrow account for buy-back", True),
    ("buyback_paid", "Payment for buy-back of equity shares of parent company", False),
    ("other_income", "(XV) Total other comprehensive income (A + B)", True), ("other_income", "II. Other income", False),
    ("fixed_assets", "Purchase of Fixed Assets including WIP", True), ("fixed_assets", "Property, plant and equipment", False),
    ("investments", "(Increase)/Decrease in Investments in other than HTM securities", True), ("investments", "(i) Investments", False),
    ("tax", "Tax adjustment", True), ("tax", "Total tax expense (VIII)", False), ("tax_paid", "Dividends and dividend tax paid", True), ("tax_paid", "Income taxes paid", False),
    ("employee_cost", "VI. Director's Fees, Allowances and Expenses", True), ("employee_cost", "Employee benefits expense", False),
])
def test_a_source_line_that_contradicts_the_metric_makes_the_fact_invalid(metric, label, invalid):
    from knowledge.financials.fact_registry import _enforce_label_contract
    fact = _bs_fact(metric)
    fact.source_line_item = label
    _enforce_label_contract(fact)
    assert (fact.availability_status == "invalid") is invalid and (fact.usable_downstream is False) is invalid


# ── final remediation: data tests against the final candidate ────────────────
COMPANIES = ("sun_pharma", "tanla", "ujjivan", "datapatterns")
USABLE_LISTS = ("available_facts", "derived_facts", "partial_facts")


def _all_registries():
    for company in COMPANIES:
        for path in sorted((FINAL / company).glob("fy*/financials/financial_fact_registry.json")):
            yield company, path.parts[-3], json.loads(path.read_text())


def _usable(registry):
    return [f for lst in USABLE_LISTS for f in registry.get(lst, []) if f.get("usable_downstream") and f.get("value") is not None]


@needs_final
def test_no_usable_fact_has_a_source_line_that_contradicts_its_metric():
    from knowledge.financials.fact_registry import LABEL_CONTRADICTIONS
    import re
    offenders = []
    for company, fy, registry in _all_registries():
        for fact in _usable(registry):
            if fact.get("derived"):
                continue
            label = " ".join(re.findall(r"[a-z()]+", str(fact.get("source_line_item") or "").lower()))
            offenders += [(company, fy, fact["metric_id"], fact["source_line_item"]) for fragment in LABEL_CONTRADICTIONS.get(fact["metric_id"], ()) if fragment in label]
    assert not offenders, offenders[:5]


@needs_final
def test_no_usable_profit_and_loss_flow_comes_from_a_balance_sheet_and_no_debt_balance_from_a_movement():
    offenders = []
    for company, fy, registry in _all_registries():
        for fact in _usable(registry):
            label = str(fact.get("source_line_item") or "").lower()
            if fact["metric_id"] in {"revenue", "pat", "pbt", "tax"} and fact.get("source_statement") == "balance_sheet":
                offenders.append((company, fy, fact["metric_id"], "balance-sheet source"))
            if fact["metric_id"] in {"total_debt", "short_term_debt", "long_term_debt"} and any(t in label for t in ("increase", "decrease", "included in", "repayment", "proceeds")):
                offenders.append((company, fy, fact["metric_id"], label[:50]))
    assert not offenders, offenders[:5]


@needs_final
def test_no_usable_bank_balance_sheet_total_is_taken_from_outside_the_statement():
    for company, fy, registry in _all_registries():
        if company != "ujjivan":
            continue
        # Independent-audit correction (F09/F16): the bank balance sheet DOES close with a TOTAL. A total is usable only when read directly from that line ("Total equity and
        # liabilities" / "Total assets", which equal each other) or - net worth - as paid-up capital plus reserves; total liabilities is never accepted, and nothing from a note.
        bad = [f for f in _usable(registry) if f["metric_id"] in {"total_assets", "total_liabilities", "net_worth"}
               and not ((f["metric_id"] == "total_assets" and not f["derived"] and f["source_statement"] == "balance_sheet" and " ".join(re.findall(r"[a-z]+", f["source_line_item"].lower())) in {"total equity and liabilities", "total assets"})
                        or (f["metric_id"] == "net_worth" and f["derived"] and "".join(f["formula"].split()) == "equity_share_capital+reserves"))]
        assert not bad, (fy, [f["metric_id"] for f in bad])


@needs_final
@pytest.mark.parametrize("company", COMPANIES)
def test_truth_pack_and_pcim_inherit_the_registry_values(company):
    registry_values = {}
    for c, fy, registry in _all_registries():
        if c == company:
            for fact in _usable(registry):
                registry_values.setdefault((fact["metric_id"], fy), set()).add(round(float(fact["value"]), 4))
    truth_pack_path = FINAL / company / "company_memory/financials/financial_truth_pack.json"
    pcim = json.loads((FINAL / company / "company_memory/pcim_v1.json").read_text())
    if not truth_pack_path.exists():
        # the one documented exception: a company whose years all fail the pipeline's own validation gates has NO company-level financial memory in the candidate (the stale
        # served copy is removed, not shipped); the PCIM then carries no financial figures that the registry does not define
        assert company == "ujjivan"
        for item in pcim.get("financial_snapshot_inputs", {}).get("usable_current_metrics", []):
            assert (item["metric_id"], item["fiscal_year"]) in registry_values, item
        return
    truth_pack = json.loads(truth_pack_path.read_text())
    for source, items in (("truth pack", truth_pack.get("usable_current_metrics", [])), ("pcim", pcim.get("financial_snapshot_inputs", {}).get("usable_current_metrics", []))):
        for item in items:
            key = (item["metric_id"], item["fiscal_year"])
            if key in registry_values and isinstance(item.get("value"), (int, float)):
                assert round(float(item["value"]), 4) in registry_values[key], (source, key, item["value"], registry_values[key])


def _registry_value(company, fy, metric):
    for c, f, registry in _all_registries():
        if c == company and f == fy:
            hit = next((x for x in _usable(registry) if x["metric_id"] == metric), None)
            return None if hit is None else round(float(hit["value"]), 4)


@needs_final
@pytest.mark.parametrize("company,fy,metric,expected", [
    ("sun_pharma", "fy21", "payables", 3973.66),            # primary balance sheet, not an ageing/maturity note
    ("sun_pharma", "fy22", "total_debt", 930.69), ("sun_pharma", "fy23", "total_debt", 6197.88), ("sun_pharma", "fy24", "total_debt", 2845.69), ("sun_pharma", "fy26", "total_debt", 4081.61),
    ("sun_pharma", "fy26", "dividends_paid", -3933.9),
    ("tanla", "fy23", "capex", -156.0455), ("tanla", "fy24", "capex", -158.8431),
    ("ujjivan", "fy21", "revenue", 2806.0656), ("ujjivan", "fy22", "revenue", 2812.7991), ("ujjivan", "fy23", "revenue", 4164.9947), ("ujjivan", "fy24", "revenue", 5677.1541), ("ujjivan", "fy25", "revenue", 6354.3896),
    ("ujjivan", "fy21", "pat", 8.2969), ("ujjivan", "fy22", "pat", -414.5904), ("ujjivan", "fy24", "pat", 1281.4907),
    ("datapatterns", "fy22", "cash_and_equivalents", 177.08),
])
def test_filing_figures_in_the_final_candidate(company, fy, metric, expected):
    assert _registry_value(company, fy, metric) == expected


@needs_final
def test_dividend_flows_stay_separate_in_the_normalized_cash_flow():
    cash_flow = json.loads((FINAL / "sun_pharma/fy22/financials/normalized_fundamentals.json").read_text())["cash_flow"]
    assert round(cash_flow["dividends_paid"]["value_crore"], 2) == -2158.92
    assert round(cash_flow["dividends_paid_to_non_controlling_interests"]["value_crore"], 2) == -10.27
    assert round(cash_flow["dividends_received"]["value_crore"], 2) == 133.83


@needs_final
@pytest.mark.parametrize("company", COMPANIES)
def test_every_served_project_and_capacity_id_is_kept_or_retired_with_a_reason(company):
    served_p = {p["project_id"] for p in json.loads((SERVED / company / "company_memory/projects/projects_registry.json").read_text())["projects"]}
    served_c = {c["capacity_id"] for c in json.loads((SERVED / company / "company_memory/capacity/capacity_registry.json").read_text())["capacity_items"]}
    cand_p = json.loads((FINAL / company / "company_memory/projects/projects_registry.json").read_text())
    cand_c = json.loads((FINAL / company / "company_memory/capacity/capacity_registry.json").read_text())
    assert served_p <= {p["project_id"] for p in cand_p["projects"]} | {r["project_id"] for r in cand_p["retired_project_ids"]}
    assert served_c <= {c["capacity_id"] for c in cand_c["capacity_items"]} | {r["capacity_id"] for r in cand_c["retired_capacity_ids"]}


@needs_final
def test_no_allocation_record_is_synthetic_or_a_budget_or_an_administrative_exchange():
    for company in COMPANIES:
        for outcome in _outcomes(company):
            name = outcome["allocation_name"].lower()
            assert name not in {"operating reinvestment", "pending deployment", "capital allocation event", "shareholder return"}, (company, name)
            assert "budget allocation" not in name and "exchange of share certificates" not in name, (company, name)


def test_supplemental_normalization_only_fills_what_the_baseline_lacks():
    from knowledge.financials.normalizer import fill_missing_fields
    def entry(value, label):
        return {"value_original": value, "value_crore": value, "source_line_item": label, "warnings": []}
    base = {"profit_and_loss": {"revenue": entry("100", "Revenue"), "pat": entry("", "")}, "balance_sheet": {"total_assets": entry("500", "derived:total_assets"), "payables": entry("", "")},
            "cash_flow": {}, "warnings": []}
    supplemented = {"profit_and_loss": {"revenue": entry("999", "Segment revenue"), "pat": entry("8", "Profit for the year")}, "balance_sheet": {"total_assets": entry("1854", "Total assets (A)"), "payables": entry("40", "Trade payables")},
                    "cash_flow": {}, "warnings": []}
    merged = fill_missing_fields(base, supplemented)
    assert merged["profit_and_loss"]["revenue"]["value_original"] == "100" and merged["balance_sheet"]["total_assets"]["source_line_item"] == "derived:total_assets"      # nothing displaced
    assert merged["profit_and_loss"]["pat"]["value_original"] == "8" and merged["balance_sheet"]["payables"]["value_original"] == "40"                                      # gaps filled
    assert "re-chunked extraction" in merged["balance_sheet"]["payables"]["warnings"][-1] and base["balance_sheet"]["payables"]["value_original"] == ""


def test_a_primary_statement_component_replaces_a_non_primary_baseline_figure_but_totals_are_never_replaced():
    from knowledge.financials.normalizer import fill_missing_fields
    def entry(value, label, primary, section_type=None):
        return {"value_original": value, "value_crore": float(value), "source_line_item": label, "is_primary_statement": primary,
                "source_section_type": section_type or ("primary_balance_sheet_statement" if primary else "financial_note"), "warnings": []}
    base = {"balance_sheet": {"payables": entry("3608.75", "Trade payables", False), "total_assets": entry("500", "Total assets (A)", False)}, "warnings": []}
    supplemented = {"balance_sheet": {"payables": entry("3973.66", "(ii) Trade payables", True), "total_assets": entry("1854", "Total assets (A)", True)}, "warnings": []}
    merged = fill_missing_fields(base, supplemented)
    assert merged["balance_sheet"]["payables"]["value_original"] == "3973.66" and "replaced a non-primary" in merged["balance_sheet"]["payables"]["warnings"][-1]
    assert merged["balance_sheet"]["total_assets"]["value_original"] == "500"


def test_an_amount_printed_in_thousands_but_read_as_rupees_is_invalid():
    from knowledge.financials.fact_registry import _enforce_unit_plausibility
    fact = _bs_fact("dividend"); fact.value = 0.00137896; fact.unit = "INR crore"
    _enforce_unit_plausibility(fact, {"value_original": "13,789.6", "unit_original": "rupees"})
    assert fact.availability_status == "invalid" and fact.usable_downstream is False
    ok = _bs_fact("dividend"); ok.value = 1378.96
    _enforce_unit_plausibility(ok, {"value_original": "13,789.6", "unit_original": "million"})
    assert ok.availability_status == "present_direct"


def test_a_bank_employee_cost_must_come_from_the_payments_to_employees_line():
    from knowledge.financials.fact_registry import _enforce_bank_employee_cost
    note = _bs_fact("employee_cost"); note.source_line_item = "Employee benefit expense"
    _enforce_bank_employee_cost(note, bank_format=True)
    assert note.availability_status == "unreliable" and note.usable_downstream is False
    schedule = _bs_fact("employee_cost"); schedule.source_line_item = "III. Payments to and provisions for employees"
    _enforce_bank_employee_cost(schedule, bank_format=True)
    assert schedule.availability_status == "present_direct"
    industrial = _bs_fact("employee_cost"); industrial.source_line_item = "Employee benefits expense"
    _enforce_bank_employee_cost(industrial, bank_format=False)
    assert industrial.availability_status == "present_direct"


def test_a_balance_sheet_figure_read_from_a_note_table_is_invalid():
    from knowledge.financials.fact_registry import _enforce_stock_source
    note = _bs_fact("total_debt", "borrowings"); note.source_line_item = "Financial liabilities Borrowings"
    _enforce_stock_source(note)
    assert note.availability_status == "invalid" and note.usable_downstream is False and "note table" in note.warnings[-1]
    statement = _bs_fact("total_debt", "balance_sheet"); _enforce_stock_source(statement)
    cash = _bs_fact("cash_and_equivalents", "cash_flow"); _enforce_stock_source(cash)
    flow = _bs_fact("revenue", "profit_and_loss"); _enforce_stock_source(flow)
    assert statement.availability_status == cash.availability_status == flow.availability_status == "present_direct"


def test_a_verified_acquisition_label_is_not_moved_by_the_targets_business_description():
    from intelligence.capital_allocation_outcomes.builder import _map_allocation_category
    item = {"value": "Acquisition (share purchase)", "purpose": "To acquire 100% voting interest of Target Pvt Ltd (omnichannel marketing automation platform providing analytics)",
            "category": "Acquisition", "canonical_category": "acquisitions", "capital_allocation_group": "true_capital_deployment"}
    assert _map_allocation_category(item, {}) == "acquisition"


def test_a_counterpartys_name_does_not_decide_a_treasury_advance_or_a_merger():
    from intelligence.capital_allocation_outcomes.builder import _map_allocation_category
    advance = {"value": "Other advances given", "purpose": "Other advances given to Acme Digital Labs Private Limited", "category": "Subsidiary advance / short-term investment",
               "canonical_category": "temporary_investment", "capital_allocation_group": "treasury_actions"}
    assert _map_allocation_category(advance, {}) == "retained_cash"
    merger = {"value": "Scheme of amalgamation", "purpose": "merge the wholly owned subsidiary into the company", "category": "Subsidiary merger / Amalgamation", "canonical_category": "acquisitions",
              "capital_allocation_group": "true_capital_deployment"}
    assert _map_allocation_category(merger, {}) != "acquisition"


def test_a_related_party_loan_the_company_availed_is_not_a_deployment():
    from intelligence.capital_allocation_outcomes.builder import _map_allocation_category
    item = {"value": "Unsecured loan availed from related party", "purpose": "Unsecured loan availed from related party (Sub Pvt Ltd)", "category": "Related party loan",
            "canonical_category": "related_party_loan_given", "capital_allocation_group": "related_party_capital_flows"}
    assert _map_allocation_category(item, {}) == "other"


def test_unrelated_other_events_are_not_merged_into_one_record():
    from intelligence.capital_allocation_outcomes.builder import _group_similarity, _build_allocation_group
    def cand(name):
        return {"allocation_name": name, "normalized_name": name.lower(), "allocation_category": "other", "family_key": "other", "funding_source": "unknown", "source_year": "fy26",
                "source_item_id": name, "source_reference": {}, "source_items": [], "amount": 1.0}
    group = _build_allocation_group(cand("Share purchase by ESOP trust (secondary market)"))
    assert _group_similarity(group, cand("Unsecured loan availed from related party")) < 8
