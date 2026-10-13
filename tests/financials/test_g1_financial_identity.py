"""M63/G1 regression tests: a financial amount keeps its period, statement section and definition.

Generic rules are tested on labels; real raw tables of all four companies check the rules end to end (including a bank and an
unaffected control). Nothing here writes under companies/."""
import json
import pathlib

import pytest

from intelligence.capital_allocation_outcomes import builder as ledger
from knowledge.financials.line_item_mapper import map_line_item
from knowledge.financials.normalizer import normalize_financial_tables

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPANIES = ("sun_pharma", "tanla", "ujjivan", "datapatterns")


def fields(label, table="balance_sheet"):
    return [m.canonical_field for m in map_line_item(table_type=table, line_item_raw=label)]


def normalized(company, fy):
    raw = ROOT / "companies" / company / fy / "financials" / "raw_financial_tables.json"
    if not raw.exists():
        pytest.skip(f"{raw} not present")
    return normalize_financial_tables(company=company, year=fy, raw_tables_path=raw)["balance_sheet"]


# ── 1. period identity: an opening balance is never a closing balance ──
def test_opening_balance_row_is_not_cash_but_closing_rows_are():
    assert fields("Cash and cash equivalents at the beginning of the year", "cash_flow") == []
    assert fields("Opening balance of borrowings") == []
    assert fields("Cash and cash equivalents at the end of the year", "cash_flow") == ["cash_and_equivalents"]
    assert fields("(iii) Cash and cash equivalents") == ["cash_and_equivalents"]


def test_sun_fy26_cash_is_the_closing_balance_and_equals_fy25_report_comparative():
    cash = normalized("sun_pharma", "fy26")["cash_and_equivalents"]
    assert cash["value_crore"] == pytest.approx(9770.51)  # filing p.241: 97,705.1 mn
    assert "beginning" not in cash["source_line_item"].lower()
    fy25 = normalized("sun_pharma", "fy25")["cash_and_equivalents"]
    assert fy25["value_crore"] == pytest.approx(10268.77) and cash["value_crore"] != fy25["value_crore"]


def test_every_company_year_cash_is_never_sourced_from_an_opening_row():
    seen = 0
    for company in COMPANIES:
        for raw in sorted((ROOT / "companies" / company).glob("fy*/financials/raw_financial_tables.json")):
            try:
                cash = normalize_financial_tables(company=company, year=raw.parent.parent.name, raw_tables_path=raw)["balance_sheet"]["cash_and_equivalents"]
            except RuntimeError:  # a year the current normalizer cannot rebuild (pre-existing, unrelated)
                continue
            seen += 1
            assert not any(t in cash["source_line_item"].lower() for t in ("beginning of", "opening")), (company, raw.parent.parent.name, cash["source_line_item"])
    assert seen >= 15


def test_data_patterns_fy25_cash_is_closing_balance_not_the_fy24_balance():
    assert normalized("datapatterns", "fy25")["cash_and_equivalents"]["value_crore"] == pytest.approx(37.66)  # filing p.114/116; 88.14 was FY24


# ── 2. categories are not confused ──
def test_bank_balances_outside_cash_equivalents_and_cash_flow_movements_are_not_cash():
    for label in ("Bank balances other than cash and cash equivalents", "Other bank balances", "Net (decrease) / increase in cash and cash equivalents (A+B+C)",
                  "Cash and cash equivalents comprises of Balances with banks In current accounts"):
        assert "cash_and_equivalents" not in fields(label, "cash_flow"), label


def test_assets_are_never_debt_and_flows_and_titles_are_never_the_debt_balance():
    for label in ("Total non-current assets", "Total Non-current Assets (A)", "Prepayment or Repayment of Borrowings", "Proceeds from borrowings",
                  "Interest on borrowings", "BORROWINGS (NON-CURRENT) ` in Million As at March", "Financial liabilities Borrowings - - - - - Lease liability"):
        assert not set(fields(label)) & {"total_debt", "long_term_debt", "short_term_debt"}, label


def test_section_prefixed_borrowings_are_components_and_bare_borrowings_stay_the_total():
    assert fields("Non-current liabilities (i) Borrowings") == ["long_term_debt"]
    assert fields("Current liabilities (i) Borrowings") == ["short_term_debt"]
    assert fields("Borrowings") == ["total_debt"] and fields("Total borrowings") == ["total_debt"]


def test_sun_total_debt_is_current_plus_non_current_not_current_only():
    bs = normalized("sun_pharma", "fy26")
    assert bs["short_term_debt"]["value_crore"] == pytest.approx(4050.35)
    assert bs["long_term_debt"]["value_crore"] == pytest.approx(31.26)  # was ₹44,894 cr from "Total non-current assets"
    td = bs["total_debt"]
    assert td["derived"] and td["formula"] == "short_term_debt + long_term_debt"
    assert td["value_crore"] == pytest.approx(4050.35 + 31.26)
    # the FY26 report's FY25 comparative equals the FY25 report's own total: one fact, one value across years
    assert td["comparatives"][0]["value_crore"] == pytest.approx(normalized("sun_pharma", "fy25")["total_debt"]["value_crore"])


def test_only_one_component_found_is_kept_but_flagged_never_a_note_row():
    bs = normalized("sun_pharma", "fy24")  # non-current borrowings not extracted for this year
    td = bs["total_debt"]
    assert td["derivation_state"] == "PARTIAL_COMPONENT_ONLY" and "long_term_debt was not found" in " ".join(td["warnings"])
    assert td["value_crore"] == pytest.approx(bs["short_term_debt"]["value_crore"])


def test_no_company_year_takes_long_term_debt_from_an_asset_total_or_debt_from_a_flow():
    for company in COMPANIES:
        for raw in sorted((ROOT / "companies" / company).glob("fy*/financials/raw_financial_tables.json")):
            try:
                bs = normalize_financial_tables(company=company, year=raw.parent.parent.name, raw_tables_path=raw)["balance_sheet"]
            except RuntimeError:
                continue
            for name in ("total_debt", "short_term_debt", "long_term_debt"):
                line = bs[name]["source_line_item"].lower()
                assert "assets" not in line and not any(t in line for t in ("repayment", "proceeds", "interest on")), (company, raw.parent.parent.name, name, line)


def test_data_patterns_does_not_invent_debt_from_use_of_proceeds():
    bs = normalized("datapatterns", "fy25")
    assert bs["total_debt"]["value_crore"] is None  # the only candidate was the IPO "repayment of borrowings" flow (₹60.08 cr)


# ── 3. definitions stay truthful ──
def test_tanla_combined_cash_and_bank_balances_is_labelled_as_such_not_as_cash_equivalents():
    cash = normalized("tanla", "fy26")["cash_and_equivalents"]
    assert cash["value_crore"] == pytest.approx(1064.0)  # ₹748 cr cash equivalents + ₹316 cr other bank balances
    assert any(w.startswith("definition:cash_and_bank_balances") for w in cash["warnings"])
    assert not any(w.startswith("definition:") for w in normalized("sun_pharma", "fy26")["cash_and_equivalents"]["warnings"])


# ── 4. bank semantics preserved (control: unaffected by the industrial-company repairs) ──
def test_bank_balance_sheet_is_unchanged_by_the_repairs():
    for fy in ("fy21", "fy23", "fy24", "fy25"):
        stored = json.loads((ROOT / "companies/ujjivan" / fy / "financials/normalized_fundamentals.json").read_text())["balance_sheet"]
        now = normalized("ujjivan", fy)
        for name in ("cash_and_equivalents", "total_debt", "short_term_debt", "long_term_debt"):  # the fields the repairs could touch
            if fy == "fy23" and name == "cash_and_equivalents":
                # Original filing p277 labels 180,589 (INR thousands) as INTEREST income, not cash.
                # G3's other-bank-balances disambiguation must not preserve that historical false stock value.
                assert "Interest on Balances" in stored[name]["source_line_item"]
                assert now[name]["value_crore"] is None
                assert fields(stored[name]["source_line_item"]) == []
            else:
                assert (now[name]["value_crore"], now[name]["source_line_item"]) == (stored[name]["value_crore"], stored[name]["source_line_item"]), (fy, name)
    assert "receivable" not in json.dumps({k: v for k, v in normalized("ujjivan", "fy25").items() if k in ("total_debt", "cash_and_equivalents")}).lower()


# ── 5. amount scope = period scope in the capital ledger ──
def test_buyback_face_value_statement_is_not_a_consideration():
    face = {"allocation_category": "share_buyback", "amount": "INR 20.00 lakhs for 20,00,000 shares"}  # INR 1 per share = nominal value
    assert ledger._is_face_value_statement(face) and ledger._candidate_amount(face, {}) is None
    assert ledger._amount_basis(face, {}, None) == "face_value_not_consideration"
    real = {"allocation_category": "share_buyback", "amount": "INR 17,500 lakhs for 20,00,000 shares"}  # INR 875 per share
    assert ledger._candidate_amount(real, {}) == pytest.approx(175.0)
    # the same words on a non-buyback (ESOP trust purchase at market price) are a real amount
    assert ledger._candidate_amount({"allocation_category": "organic_capex", "amount": "INR 1,821.46 lakhs for 3,00,000 shares"}, {}) == pytest.approx(18.2146)


def test_buyback_never_takes_a_ledger_aggregate_as_its_amount():
    assert ledger._candidate_amount({"allocation_category": "share_buyback"}, {"amount_crore": 121.7}) is None


@pytest.mark.parametrize("company", COMPANIES)
def test_every_ledger_amount_is_stamped_with_its_own_period_inside_the_deployment_span(company):
    records = ledger.build_capital_allocation_outcomes(company=company, company_root=ROOT / "companies" / company)["capital_allocation_outcomes.json"]["allocations"]
    assert records
    for r in records:
        if r["amount"] is None:
            assert r["amount_period"] is None
        else:
            assert r["amount_period"] in r["deployment_periods"], (company, r["allocation_id"])


def test_sun_capex_is_a_single_year_amount_inside_a_multi_year_record():
    records = ledger.build_capital_allocation_outcomes(company="sun_pharma", company_root=ROOT / "companies/sun_pharma")["capital_allocation_outcomes.json"]["allocations"]
    capex = next(r for r in records if r["allocation_category"] == "organic_capex")
    assert capex["amount"] == pytest.approx(3609.37) and capex["amount_period"] == "fy26" and capex["deployment_periods"][0] == "fy20"


def test_tanla_buyback_is_not_stated_rather_than_a_face_value_or_aggregate_figure():
    records = ledger.build_capital_allocation_outcomes(company="tanla", company_root=ROOT / "companies/tanla")["capital_allocation_outcomes.json"]["allocations"]
    buyback = next(r for r in records if r["allocation_category"] == "share_buyback")
    assert buyback["amount"] is None and buyback["amount_period"] is None


# ── 6. the same fact reaches the downstream consumer unchanged ──
def test_economic_attribution_cases_carry_the_ledgers_amount_period(tmp_path):
    from intelligence.economic_attribution.builder import build_economic_attribution_intelligence

    mem = ROOT / "companies/sun_pharma/company_memory"
    cao = ledger.build_capital_allocation_outcomes(company="sun_pharma", company_root=ROOT / "companies/sun_pharma")["capital_allocation_outcomes.json"]
    path = tmp_path / "cao.json"
    path.write_text(json.dumps(cao))
    cases = build_economic_attribution_intelligence(path, mem / "management_progression/management_progression.json", mem / "gold/risk_evolution_timeline.json", mem / "financial_truth_pack.json")["cases"]
    by_id = {r["allocation_id"]: r for r in cao["allocations"]}
    stamped = [c for c in cases if c.get("amount_inr_cr") is not None]
    assert stamped
    for c in stamped:
        assert c["amount_period"] == by_id[c["source_action_id"]]["amount_period"] or c["amount_period"] is None
    capex = next(c for c in cases if c["action_type"] == "organic_capex")
    assert capex["amount_period"] == "fy26" and capex["deployment_periods"][0] == "fy20"


# ── G1.1: a debt BALANCE is not rejected for containing "interest" or "cost"; flows and expenses still are ──
@pytest.mark.parametrize("label", [
    "Interest bearing borrowings",
    "Interest-bearing loans and borrowings",
    "Borrowings measured at amortised cost",
    "Borrowings at amortised cost",
    "Borrowings (other than debt securities)",
    "Total borrowings",
])
def test_valid_debt_balances_are_accepted(label):
    assert set(fields(label)) & {"total_debt", "short_term_debt", "long_term_debt"}, label


@pytest.mark.parametrize("label", [
    "Interest on borrowings",
    "Interest expense on borrowings",
    "Interest cost on borrowings for the year",
    "Finance cost on borrowings",
    "Borrowing cost",
    "Cost of borrowings",
    "Prepayment or Repayment of Borrowings",
    "Repayment of borrowings",
    "Proceeds from borrowings",
    "Proceeds from long-term borrowings",
    "Accrued Interest from borrowings",
    "Total non-current assets",
    "Long term lease liability",
])
def test_debt_flows_expenses_and_non_debt_are_still_rejected(label):
    assert not set(fields(label)) & {"total_debt", "short_term_debt", "long_term_debt"}, label
    assert not set(fields(label, "cash_flow")) & {"total_debt", "short_term_debt", "long_term_debt"}, label
