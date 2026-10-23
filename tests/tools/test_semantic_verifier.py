"""The verifier certifies a fact only when meaning, source identity, statement/row, year column, basis, declared unit, sign and precision all hold. These adversarial cases are the
ways the previous label-and-number matcher certified wrong facts. They read the original annual-report PDFs under data/Processed and skip when those are absent."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("verify_vs_filing", ROOT / "tools" / "verify_vs_filing.py")
V = importlib.util.module_from_spec(spec)
sys.modules["verify_vs_filing"] = V
spec.loader.exec_module(V)

pytestmark = pytest.mark.skipif(not (ROOT / "data/Processed/sun_pharma/fy21/annual_report/sun_pharma_fy21.pdf").exists(), reason="original filings not available")


def f(metric, value, label, **kw):
    flow = kw.get("source_statement") in {"profit_and_loss", "cash_flow"}
    base = {"metric_id": metric, "value": value, "source_line_item": label, "basis": "consolidated", "source_page": None, "derived": False, "fiscal_year": "fy21", "source_statement": "balance_sheet",
            "unit": "INR crore", "period": "March 31, 2021", "period_role": "annual_flow" if flow else "closing_balance"}     # a registry fact states its whole identity
    return {**base, **kw}


def status(fact, company="sun_pharma", fy="fy21", **kw):
    return V.verify_fact(fact, company=company, fy=fy, **kw)["status"]


def test_the_true_current_year_figure_is_verified_with_its_evidence():
    v = V.verify_fact(f("payables", 3973.66, "Trade payables"), company="sun_pharma", fy="fy21")
    assert v["status"] == "VERIFIED" and v["evidence"]["page"] == 185 and v["evidence"]["unit"] == "million" and len(v["evidence"]["report_sha256"]) == 64


def test_the_prior_year_column_is_rejected_not_verified():
    assert status(f("payables", 3583.64, "Trade payables")) == "REJECTED"           # the FY20 comparative of the same row


def test_a_total_cannot_verify_as_the_residual_even_though_the_number_is_on_the_page():
    assert status(f("other_expenses", 586.18, "Total Expenses", source_statement="profit_and_loss", basis="standalone"), company="datapatterns", fy="fy26") == "REJECTED"


def test_one_part_of_payables_is_rejected_as_the_total():
    assert status(f("payables", 26.5945, "Total outstanding dues of micro enterprises and small enterprises; and"), company="tanla", fy="fy26") == "REJECTED"


def test_authorised_capital_is_rejected_as_paid_up_capital():
    assert status(f("equity_share_capital", 2625.0, "to Rs. 1,931.80. Furthermore, the authorised share capital of the Bank was `"), company="ujjivan", fy="fy25") == "REJECTED"


def test_a_note_reference_is_not_a_balance():
    assert status(f("other_bank_balances", 8.1, "(iv) Other Bank balances", basis="standalone"), company="datapatterns", fy="fy23") != "VERIFIED"


def test_a_value_wrong_by_a_scale_factor_is_not_verified():
    assert status(f("payables", 397366.0, "Trade payables")) != "VERIFIED"            # x100: no other scale is tried
    assert status(f("payables", 39.7366, "Trade payables")) != "VERIFIED"


def test_the_wrong_basis_is_not_verified():
    assert status(f("payables", 3973.66, "Trade payables", basis="standalone")) in {"REJECTED", "PROVISIONAL"}


def test_a_wrong_sign_is_not_verified_for_a_stock():
    assert status(f("payables", -3973.66, "Trade payables")) != "VERIFIED"


def test_an_outflow_metric_may_be_compared_on_magnitude_by_name_only():
    assert status(f("capex", -3609.37, "Payments for purchase of property, plant and equipment", source_statement="cash_flow", fiscal_year="fy26", period="March 31, 2026"), fy="fy26") == "VERIFIED"


def _sun_fy21_registry():
    """The canonical registry facts of Sun FY21's debt (identity as a registry fact states it)."""
    common = {"fiscal_year": "fy21", "period": "March 31, 2021", "period_role": "closing_balance", "unit": "INR crore", "basis": "consolidated", "source_page": 185, "source_statement": "balance_sheet",
              "availability_status": "present_direct", "usable_downstream": True, "derived": False, "formula": "", "inputs_used": []}
    short = {**common, "metric_id": "short_term_debt", "value": 2444.9, "source_line_item": "Current liabilities (a) Financial liabilities (i) Borrowings"}
    long_ = {**common, "metric_id": "long_term_debt", "value": 898.13, "source_line_item": "Non-current liabilities (a) Financial liabilities (i) Borrowings"}
    total = {**common, "metric_id": "total_debt", "value": 3343.03, "source_line_item": "derived:total_debt", "derived": True, "availability_status": "present_derived",
             "formula": "short_term_debt + long_term_debt", "inputs_used": ["short_term_debt", "long_term_debt"]}
    return {"available_facts": [short, long_], "derived_facts": [total]}


def test_a_derived_fact_is_verified_only_from_its_canonical_inputs_resolved_by_identity():
    registry = _sun_fy21_registry()
    verdicts = V.verify_registry("sun_pharma", "fy21", registry)
    assert verdicts["short_term_debt"]["status"] == verdicts["long_term_debt"]["status"] == "VERIFIED"
    total = verdicts["total_debt"]
    assert total["status"] == "DERIVED_VERIFIED" and [i["metric"] for i in total["evidence"]["inputs"]] == ["short_term_debt", "long_term_debt"]
    assert all(len(i["fingerprint"]) == 64 for i in total["evidence"]["inputs"])


def test_numbers_supplied_with_a_derived_fact_are_not_evidence():
    """The fabricated case: inputs_used copied as {1000, 3000} and a stored 4000 - while the actual canonical components total 3343.03."""
    registry = _sun_fy21_registry()
    fabricated = {**registry["derived_facts"][0], "value": 4000.0, "inputs_used": {"short_term_debt": 1000.0, "long_term_debt": 3000.0}}
    canonical = V.CanonicalRegistry("sun_pharma", {"fy21": registry})
    verdict = V.verify_fact(fabricated, company="sun_pharma", fy="fy21", canonical=canonical)
    assert verdict["status"] == "REJECTED" and "3343.03" in verdict["reasons"][0]
    # with no canonical registry at all, supplied numbers cannot verify anything
    assert V.verify_fact(fabricated, company="sun_pharma", fy="fy21")["status"] == "DERIVED_UNVERIFIED"


def test_a_derived_fact_is_never_stronger_than_its_weakest_input():
    registry = _sun_fy21_registry()
    registry["available_facts"][0] = {**registry["available_facts"][0], "value": 2444.5}           # the short-term input no longer matches the filing
    total = V.verify_registry("sun_pharma", "fy21", registry)["total_debt"]
    assert total["status"] in {"DERIVED_UNVERIFIED", "REJECTED"} and total["status"] != "DERIVED_VERIFIED"


def test_a_metric_with_no_defined_statement_is_only_provisional():
    assert status(f("some_new_metric", 3973.66, "Trade payables")) == "PROVISIONAL"


def test_the_report_is_identified_by_what_it_states_not_by_its_folder():
    tanla = [Path(p).name for p in V.reports_for("tanla", "fy24")]
    assert tanla == ["tanla_fy23.pdf"]


def test_a_record_for_another_year_unit_duration_or_basis_cannot_be_certified_by_a_matching_page():
    """The record's own identity is checked before the filing: the page can only confirm a number, not repair a record that names the wrong year, unit, duration or basis."""
    ok = f("payables", 3973.66, "Trade payables")
    assert status(ok) == "VERIFIED"
    assert status({**ok, "fiscal_year": "fy20", "period": "March 31, 2020"}) == "REJECTED"
    assert status({**ok, "unit": "USD crore"}) == "REJECTED" and status({**ok, "unit": "INR lakh"}) == "REJECTED"
    assert status({**ok, "period": "Quarter ended March 31, 2021"}) == "REJECTED"
    assert status({**ok, "period_role": "annual_flow"}) == "REJECTED"                          # a closing balance claimed as a flow
    assert status({**ok, "basis": "unknown"}) == "PROVISIONAL"


def test_the_source_row_must_be_a_recognised_row_of_the_metric_not_just_pass_exclusions():
    assert status(f("pat", 3973.66, "Trade payables", source_statement="profit_and_loss")) == "REJECTED"
    assert status(f("revenue", 3973.66, "Other income", source_statement="profit_and_loss")) == "REJECTED"
    assert status(f("long_term_debt", 2444.9, "Current liabilities (a) Financial liabilities (i) Borrowings")) == "REJECTED"        # a current maturity is not long-term debt


def test_verdicts_supplied_by_the_caller_are_ignored_the_old_call_shape_cannot_certify_a_fabricated_derivation():
    registry = _sun_fy21_registry()
    fabricated = {**registry["derived_facts"][0], "value": 4000.0, "inputs_used": {"short_term_debt": 1000.0, "long_term_debt": 3000.0}}
    claimed = {"short_term_debt": {"status": "VERIFIED"}, "long_term_debt": {"status": "VERIFIED"}}
    assert V.verify_fact(fabricated, company="sun_pharma", fy="fy21", registry_verdicts=claimed)["status"] == "DERIVED_UNVERIFIED"


def test_the_truth_pack_flags_a_high_impact_figure_that_was_not_independently_checked_and_says_so_in_its_precision_limits(tmp_path):
    import json
    fin = tmp_path / "acme" / "fy25" / "financials"
    mem = tmp_path / "acme" / "company_memory" / "financials"
    fin.mkdir(parents=True), mem.mkdir(parents=True)
    fact = {"metric_id": "payables", "fiscal_year": "fy25", "period": "March 31, 2025", "value": 1.0, "unit": "INR crore", "basis": "standalone", "source_statement": "balance_sheet", "source_line_item": "Trade payables",
            "source_page": 1, "availability_status": "present_direct", "usable_downstream": True, "derived": False, "period_role": "closing_balance"}
    (fin / "financial_fact_registry.json").write_text(json.dumps({"available_facts": [fact], "derived_facts": []}))
    (mem / "financial_truth_pack.json").write_text(json.dumps({"usable_current_metrics": [{"metric_id": "payables", "fiscal_year": "fy25", "value": 1.0}], "usable_derived_metrics": [], "partial_metrics": [], "precision_limits": ["existing"]}))
    V.stamp(tmp_path)
    pack = json.loads((mem / "financial_truth_pack.json").read_text())
    item = pack["usable_current_metrics"][0]
    assert item["verification_status"] in {"NO_FILING", "PROVISIONAL"} and item["reliance"] == "qualified" and item["must_qualify"] is True
    assert pack["precision_limits"][0] == "existing" and pack["precision_limits"][-1].startswith("Not independently checked against the filing") and "payables fy25" in pack["precision_limits"][-1]
    V.stamp(tmp_path)                                                                                 # idempotent: the limit is replaced, not duplicated
    assert sum(x.startswith("Not independently checked") for x in json.loads((mem / "financial_truth_pack.json").read_text())["precision_limits"]) == 1
