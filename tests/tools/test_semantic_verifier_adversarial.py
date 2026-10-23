"""The independent retest obtained VERIFIED for ten facts that were not the facts they claimed (revenue as PAT, employee cost as depreciation, inventories as receivables, a USD / lakh
unit, a consolidated claim on a standalone report, another year, a quarter, current debt as long-term debt, other income as revenue) and DERIVED_VERIFIED for a fabricated 4,000 total
debt. These are those cases and fresh variants, on the original filings. A record is certified only if its complete identity - metric, year, duration, basis, unit, source row, column,
exact value - is the one the filing states."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("verify_vs_filing", ROOT / "tools" / "verify_vs_filing.py")
V = importlib.util.module_from_spec(spec)
sys.modules["verify_vs_filing"] = V
spec.loader.exec_module(V)

pytestmark = pytest.mark.skipif(not (ROOT / "data/Processed/datapatterns/fy26/annual_report/datapatterns_fy26.pdf").exists(), reason="original filings not available")


def dp(metric, value, label, statement="profit_and_loss", **kw):
    flow = statement in {"profit_and_loss", "cash_flow"}
    base = {"metric_id": metric, "value": value, "source_line_item": label, "basis": "standalone", "source_page": 133 if statement == "profit_and_loss" else 132, "derived": False, "fiscal_year": "fy26",
            "source_statement": statement, "unit": "INR crore", "period": "March 31, 2026", "period_role": "annual_flow" if flow else "closing_balance"}
    return {**base, **kw}


def status(fact, company="datapatterns", fy="fy26", **kw):
    return V.verify_fact(fact, company=company, fy=fy, **kw)["status"]


@pytest.mark.parametrize("fact", [dp("pat", 271.37, "Profit for the year (A)"), dp("employee_cost", 154.26, "Employee benefits expense"), dp("revenue", 924.77, "Revenue from operations"),
                                  dp("receivables", 727.77, "Trade receivables", "balance_sheet")])
def test_positive_controls_are_verified(fact):
    assert status(fact) == "VERIFIED"


@pytest.mark.parametrize("fact,reason", [
    (dp("pat", 924.77, "Profit for the year (A)"), "the PAT row does not state the revenue figure"),
    (dp("depreciation", 154.26, "Employee benefits expense"), "an employee-cost row is not a depreciation row"),
    (dp("payables", 727.77, "Trade receivables", "balance_sheet"), "a receivables row is not a payables row"),
    (dp("finance_cost", 22.95, "Finance costs"), "finance costs are 12.45, not the depreciation figure"),
    (dp("revenue", 92477.0, "Revenue from operations"), "x100"),
    (dp("revenue", 9.2477, "Revenue from operations"), "/100"),
    (dp("pat", -271.37, "Profit for the year (A)"), "sign"),
    (dp("revenue", 708.35, "Revenue from operations"), "the FY25 column"),
    (dp("revenue", 924.77, "Revenue from operations", fiscal_year="fy27", period="March 31, 2027"), "a record for another year"),
    (dp("revenue", 924.77, "Revenue from operations", unit="INR million"), "another unit"),
    (dp("revenue", 924.77, "Revenue from operations", unit="USD crore"), "another currency"),
    (dp("revenue", 924.77, "Revenue from operations", period="Half-year ended September 30, 2025"), "a half-year period"),
    (dp("revenue", 924.77, "Revenue from operations", period_role="cumulative"), "a cumulative period role"),
    (dp("revenue", 924.77, "Revenue from operations", basis="consolidated"), "DP presents standalone statements only"),
    (dp("other_expenses", 586.18, "Total expenses"), "a total is not the residual"),
    (dp("revenue", 27.96, "Other income"), "other income is not operating revenue"),
])
def test_a_record_that_is_not_the_fact_it_claims_is_never_verified(fact, reason):
    assert status(fact) != "VERIFIED", reason


def test_a_consolidated_claim_on_a_single_entity_bank_is_not_verified():
    bank = {"metric_id": "reserves", "value": 4058.7647, "source_line_item": "Reserves and Surplus", "basis": "consolidated", "source_page": 257, "derived": False, "fiscal_year": "fy25",
            "source_statement": "balance_sheet", "unit": "INR crore", "period": "March 31, 2025", "period_role": "closing_balance"}
    assert status(bank, "ujjivan", "fy25", bank_format=True) != "VERIFIED"
    assert status({**bank, "basis": "standalone"}, "ujjivan", "fy25", bank_format=True) == "VERIFIED"


def registry(*facts):
    common = {"fiscal_year": "fy23", "period": "March 31, 2023", "period_role": "closing_balance", "unit": "INR crore", "basis": "standalone", "source_page": 132, "source_statement": "balance_sheet",
              "availability_status": "present_direct", "usable_downstream": True, "derived": False, "formula": "", "inputs_used": []}
    return {"available_facts": [{**common, **f} for f in facts], "derived_facts": []}


def test_fabricated_inputs_of_a_derived_fact_do_not_verify_it_the_canonical_components_decide():
    reg = registry({"metric_id": "short_term_debt", "value": 0.46, "source_line_item": "Current liabilities (a) Financial Liabilities (i) Borrowings"},
                   {"metric_id": "long_term_debt", "value": 0.26, "source_line_item": "Liabilities Non-current liabilities (a) Financial Liabilities (i) Borrowings"})
    canonical = V.CanonicalRegistry("datapatterns", {"fy23": reg}, bank_format=False)
    for stored, supplied in ((0.72, {"short_term_debt": 0.46, "long_term_debt": 0.26}), (4000.0, {"short_term_debt": 1000.0, "long_term_debt": 3000.0})):
        derived = {"metric_id": "total_debt", "value": stored, "source_line_item": "derived:total_debt", "derived": True, "formula": "short_term_debt + long_term_debt", "inputs_used": supplied,
                   "fiscal_year": "fy23", "unit": "INR crore", "basis": "standalone", "period": "March 31, 2023", "period_role": "closing_balance", "source_page": 132, "source_statement": "balance_sheet",
                   "availability_status": "present_derived", "usable_downstream": True}
        verdict = V.verify_fact(derived, company="datapatterns", fy="fy23", canonical=canonical)
        assert verdict["status"] == ("DERIVED_VERIFIED" if stored == 0.72 else "REJECTED"), (stored, verdict)
        assert [i["value"] for i in verdict["evidence"]["inputs"]] == [0.46, 0.26]               # the inputs are the canonical facts, whatever the caller supplied


def test_net_debt_and_free_cash_flow_are_re_derived_from_canonical_inputs_too():
    reg = registry({"metric_id": "total_debt", "value": 0.72, "source_line_item": "derived:total_debt", "derived": True, "availability_status": "present_derived"},
                   {"metric_id": "cash_and_equivalents", "value": 56.85, "source_line_item": "Cash and cash equivalents", "fiscal_year": "fy23"})
    canonical = V.CanonicalRegistry("datapatterns", {"fy23": reg})
    fabricated = {"metric_id": "net_debt", "value": 500.0, "source_line_item": "derived:net_debt", "derived": True, "formula": "total_debt - cash_and_equivalents", "inputs_used": {"total_debt": 600.0, "cash_and_equivalents": 100.0},
                  "fiscal_year": "fy23", "unit": "INR crore", "basis": "standalone", "period": "March 31, 2023", "period_role": "closing_balance"}
    assert V.verify_fact(fabricated, company="datapatterns", fy="fy23", canonical=canonical)["status"] == "REJECTED"
    assert V.verify_fact({**fabricated, "value": 0.72 - 56.85}, company="datapatterns", fy="fy23", canonical=canonical)["status"] in {"DERIVED_UNVERIFIED", "DERIVED_VERIFIED"}


def test_a_derived_fact_is_never_stronger_than_an_unusable_input():
    reg = registry({"metric_id": "short_term_debt", "value": 0.46, "source_line_item": "Current liabilities (a) Financial Liabilities (i) Borrowings", "usable_downstream": False},
                   {"metric_id": "long_term_debt", "value": 0.26, "source_line_item": "Liabilities Non-current liabilities (a) Financial Liabilities (i) Borrowings"})
    derived = {"metric_id": "total_debt", "value": 0.72, "source_line_item": "derived:total_debt", "derived": True, "formula": "x", "inputs_used": ["short_term_debt", "long_term_debt"], "fiscal_year": "fy23",
               "unit": "INR crore", "basis": "standalone", "period": "March 31, 2023", "period_role": "closing_balance"}
    verdict = V.verify_fact(derived, company="datapatterns", fy="fy23", canonical=V.CanonicalRegistry("datapatterns", {"fy23": reg}))
    assert verdict["status"] == "DERIVED_UNVERIFIED" and "not usable" in " ".join(verdict["reasons"])
