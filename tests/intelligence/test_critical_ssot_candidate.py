"""Data tests for the critical-remediation candidate (CRIT_ROOT, default the scratch assembly). Every oracle below is a figure the independent audit read from the original filing
(PDF page given) and that this work re-checked with the semantic verifier; nothing here feeds the code. A usable fact must equal its oracle; a figure the audit showed to be the wrong
quantity must not be usable anywhere. They skip when the candidate has not been assembled."""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CRIT = Path(os.environ.get("CRIT_ROOT", "/private/tmp/claude-501/p5/final/companies"))
needs = pytest.mark.skipif(not CRIT.exists(), reason="critical-remediation candidate not assembled")

spec = importlib.util.spec_from_file_location("verify_vs_filing", ROOT / "tools" / "verify_vs_filing.py")
V = importlib.util.module_from_spec(spec)
sys.modules.setdefault("verify_vs_filing", V)
spec.loader.exec_module(V)
spec2 = importlib.util.spec_from_file_location("quarantine_propagation_scan", ROOT / "tools" / "quarantine_propagation_scan.py")
Q = importlib.util.module_from_spec(spec2)
sys.modules.setdefault("quarantine_propagation_scan", Q)
spec2.loader.exec_module(Q)

from knowledge.financials.semantic_contracts import semantic_problems          # noqa: E402
from knowledge.financials.fact_registry_schema import FinancialFact           # noqa: E402


def registry(company, fy):
    path = CRIT / company / fy / "financials" / "financial_fact_registry.json"
    return json.loads(path.read_text()) if path.exists() else {}


def facts(company, fy, usable_only=True):
    d = registry(company, fy)
    out = [f for k in ("available_facts", "derived_facts", "partial_facts") for f in d.get(k) or []]
    return [f for f in out if f.get("usable_downstream")] if usable_only else out


def usable(company, fy, metric):
    return next((f for f in facts(company, fy) if f["metric_id"] == metric), None)


def years(company):
    return sorted(p.name for p in (CRIT / company).glob("fy*") if (p / "financials" / "financial_fact_registry.json").exists())


# (company, fy, metric, filing value, PDF page) -- a usable fact must be this figure
MUST_EQUAL = [
    ("datapatterns", "fy22", "other_expenses", 21.39, 60), ("datapatterns", "fy25", "other_expenses", 43.19, 115), ("datapatterns", "fy26", "other_expenses", 56.62, 133),
    ("tanla", "fy24", "other_expenses", 129.9112, 291), ("sun_pharma", "fy26", "other_expenses", 19008.28, 243),
    ("datapatterns", "fy23", "other_bank_balances", 329.75, 132), ("datapatterns", "fy22", "total_debt", 6.77, 59), ("datapatterns", "fy23", "total_debt", 0.72, 132),
    ("sun_pharma", "fy20", "total_debt", 7578.30, 185), ("sun_pharma", "fy21", "total_debt", 3343.03, 185), ("tanla", "fy26", "payables", 678.7635, 384),
    ("ujjivan", "fy25", "investments", 11729.9902, 257), ("ujjivan", "fy25", "fixed_assets", 456.9131, 257), ("ujjivan", "fy25", "other_assets", 942.4489, 257),
    ("ujjivan", "fy24", "investments", 9766.0182, 335), ("ujjivan", "fy24", "equity_share_capital", 1931.4285, 335), ("ujjivan", "fy25", "equity_share_capital", 1935.0036, 257),
    ("ujjivan", "fy25", "reserves", 4058.7647, 257), ("ujjivan", "fy24", "other_assets", 809.8230, 335), ("ujjivan", "fy22", "other_assets", 730.8651, 116), ("ujjivan", "fy25", "cash_and_equivalents", 3156.9659, 260),
    ("sun_pharma", "fy22", "fixed_assets", 10371.38, 211), ("sun_pharma", "fy25", "fixed_assets", 10035.94, 225), ("tanla", "fy26", "other_expenses", 151.4759, 385), ("sun_pharma", "fy22", "total_debt", 930.69, 212),
    ("sun_pharma", "fy21", "payables", 3973.66, 185), ("sun_pharma", "fy26", "cash_and_equivalents", 9770.51, 241), ("tanla", "fy26", "cash_and_equivalents", 748.0121, 383),
    ("datapatterns", "fy22", "cash_and_equivalents", 177.08, 59), ("ujjivan", "fy21", "pat", 8.2969, 113), ("ujjivan", "fy25", "pat", 726.1031, 258),
]
# (company, fy, metric, wrong value): the audited candidate used this quantity as the metric; it must not be usable now
MUST_NOT_BE_USABLE = [
    ("datapatterns", "fy22", "other_expenses", 187.43), ("datapatterns", "fy26", "other_expenses", 586.18), ("tanla", "fy24", "other_expenses", 3287.0262), ("sun_pharma", "fy26", "other_expenses", 44007.40),
    ("datapatterns", "fy22", "face_value", 15.75), ("datapatterns", "fy22", "gross_block_additions", 0.03), ("datapatterns", "fy23", "other_bank_balances", 8.1),
    ("datapatterns", "fy22", "total_debt", 6.04), ("datapatterns", "fy23", "total_debt", 0.46), ("sun_pharma", "fy20", "total_debt", 5549.38), ("sun_pharma", "fy21", "total_debt", 1376.63),
    ("tanla", "fy26", "payables", 26.5945), ("ujjivan", "fy24", "equity_share_capital", 2625.0), ("ujjivan", "fy25", "equity_share_capital", 2625.0), ("ujjivan", "fy24", "depreciation", -482.6204),
    ("ujjivan", "fy22", "ebit", 642.6584), ("ujjivan", "fy22", "other_assets", 443.6611), ("ujjivan", "fy24", "other_assets", 5888.7184), ("ujjivan", "fy22", "other_expenses", 1318.58),
    ("ujjivan", "fy24", "investments", 167982.96), ("ujjivan", "fy25", "fixed_assets", 0.03), ("ujjivan", "fy25", "investments", 1679.83), ("ujjivan", "fy25", "other_assets", 3.85),
    ("ujjivan", "fy25", "reserves", 1732.67), ("ujjivan", "fy24", "cash_and_equivalents", 2518.3148), ("sun_pharma", "fy21", "investments", 232.73), ("sun_pharma", "fy26", "fixed_assets", 13.37),
]


@needs
@pytest.mark.parametrize("company,fy,metric,truth,page", MUST_EQUAL)
def test_a_usable_fact_is_the_filings_figure_when_present(company, fy, metric, truth, page):
    f = usable(company, fy, metric)
    assert f is not None, f"{company} {fy} {metric}: no usable fact (the filing prints {truth} on PDF page {page})"
    assert abs(abs(f["value"]) - truth) <= max(0.006, 1e-4 * abs(truth)), (f["value"], truth)


@needs
@pytest.mark.parametrize("company,fy,metric,wrong", MUST_NOT_BE_USABLE)
def test_the_wrong_quantity_is_not_usable_anywhere(company, fy, metric, wrong):
    f = usable(company, fy, metric)
    assert f is None or abs(abs(f["value"]) - abs(wrong)) > max(0.006, 1e-6 * abs(wrong)), f"{company} {fy} {metric} still usable at {f['value']}"


@needs
@pytest.mark.parametrize("company", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_no_usable_fact_of_any_year_fails_a_metric_meaning_contract(company):
    """The census of ALL facts, changed or not: the audit's changed-fact census missed unchanged errors such as a total filed as the residual."""
    bad = []
    for fy in years(company):
        bank = bool((json.loads((CRIT / company / fy / "financials" / "normalized_fundamentals.json").read_text()).get("registry_context") or {}).get("bank_format"))
        for f in facts(company, fy):
            problems = semantic_problems(FinancialFact(**{k: f.get(k) for k in ("metric_id", "metric_name", "fiscal_year", "period", "value", "unit", "basis", "source_statement", "source_artifact", "source_line_item",
                                                                              "source_page", "confidence", "availability_status", "derived", "formula", "usable_downstream")}, inputs_used=f.get("inputs_used") or []), bank_format=bank)
            if problems:
                bad.append((fy, f["metric_id"], f["value"], problems[0][:80]))
    assert not bad, bad


@needs
def test_no_figure_the_registry_rejected_survives_in_any_downstream_artifact_or_the_panels_metric_registry():
    scan = Q.scan(CRIT)
    assert scan["rejected_figures"] > 0 and scan["artifacts_scanned"] > 100
    assert scan["leaks"] == [], scan["leaks"][:5]
    panel = Q.panel_registry_leaks(CRIT)
    assert panel["leaks"] == [] and all(n > 0 for n in panel["panel_registry_sizes"].values()), panel


@needs
@pytest.mark.parametrize("company", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_truth_pack_and_pcim_carry_only_registry_usable_values(company):
    registry_all = {(f["metric_id"], fy): f for fy in years(company) for f in facts(company, fy, usable_only=False)}
    registry_usable = {k: f["value"] for k, f in registry_all.items() if f.get("usable_downstream")}
    pack_path = CRIT / company / "company_memory" / "financials" / "financial_truth_pack.json"
    if not pack_path.exists():
        pytest.skip("no company financial memory for this company (explicitly unavailable)")
    pack = json.loads(pack_path.read_text())
    hydrated = 0
    for key in ("usable_current_metrics", "usable_derived_metrics", "partial_metrics"):
        for item in pack.get(key) or []:
            k = (item["metric_id"], item["fiscal_year"])
            if k in registry_all:                                      # the registry defines this metric for this year: it alone decides, and only if it let it be used
                assert key == "partial_metrics" or k in registry_usable, (key, k, "the registry did not let this be used")
                if isinstance(item.get("value"), (int, float)):
                    assert abs(registry_usable[k] - item["value"]) < 1e-6, (key, k)
            else:
                hydrated += 1                                           # a module-derived metric the registry does not define: it must say where it came from
                assert item.get("source_artifact"), (key, k)
            assert item.get("verification_status"), "every truth-pack metric states its verification status separately from its eligibility"
    assert hydrated < 0.5 * max(1, sum(len(pack.get(k) or []) for k in ("usable_current_metrics", "usable_derived_metrics", "partial_metrics")))


@needs
def test_sun_fy21_debt_is_the_primary_statements_total_and_the_liquidity_bucket_is_nowhere():
    f = usable("sun_pharma", "fy21", "total_debt")
    assert f is not None and abs(f["value"] - 3343.03) < 0.006 and f["derived"] is True
    assert "1376.63" not in "".join(p.read_text() for p in (CRIT / "sun_pharma").rglob("*.json") if p.name in {"pcim_v1.json", "cim_v1.json", "financial_truth_pack.json", "financial_trends.json", "financial_ratios.json"})


@needs
def test_a_company_without_its_financial_authority_is_not_panel_ready():
    for company in ["sun_pharma", "tanla", "ujjivan", "datapatterns"]:
        pcim = json.loads((CRIT / company / "company_memory" / "pcim_v1.json").read_text())
        pack = CRIT / company / "company_memory" / "financials" / "financial_truth_pack.json"
        has_authority = pack.exists() and bool(json.loads(pack.read_text()).get("usable_current_metrics"))
        assert pcim["financial_panel_ready"] is has_authority or (has_authority is False and pcim["financial_panel_ready"] is False), company
        if not has_authority:
            assert pcim["financial_panel_status"]["status"] == "unavailable"


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------
# F17-F21: economic events
def outcomes(company):
    path = CRIT / company / "company_memory" / "capital_allocation_outcomes" / "capital_allocation_outcomes.json"
    return json.loads(path.read_text())["allocations"] if path.exists() else []


@needs
def test_no_cumulative_closing_or_proposed_figure_is_a_period_flow_amount():
    for company in ["sun_pharma", "tanla", "ujjivan", "datapatterns"]:
        for a in outcomes(company):
            for n in a.get("non_flow_amounts") or []:
                assert n["role"] in {"cumulative_utilisation", "closing_balance", "proposed_not_paid"}
                assert a["amount"] is None or abs(a["amount"] - n["value"]) > 1e-9 or a["amount_basis"] not in {"cumulative_utilisation_not_a_period_flow", "closing_balance_not_a_period_flow", "proposed_not_paid"}
            if a["amount"] is not None:
                assert a["amount_aggregation"] == "single_period_flow" and a["amount_period"] in a["deployment_periods"]


@needs
def test_data_patterns_qip_issue_use_of_proceeds_and_land_are_distinct_typed_events():
    records = outcomes("datapatterns")
    issue = next(a for a in records if a["allocation_category"] == "equity_issuance" and "Qualified Institutional Placement" in a["allocation_name"])
    assert issue["amount"] == 487.74 and issue["amount_period"] == "fy23" and issue["event_period"] == "fy23"             # allotted March 13, 2023 (PDF 182, Note 39)
    gcp = next(a for a in records if "general corporate" in a["allocation_name"].lower())
    assert gcp["amount"] is None and gcp["allocation_category"] != "equity_issuance" and gcp["non_flow_amounts"][0]["role"] == "cumulative_utilisation" and gcp["non_flow_amounts"][0]["value"] == 104.52
    land = next(a for a in records if "land" in a["allocation_name"].lower())
    assert land["allocation_category"] == "organic_capex" and land["amount"] is None and land["non_flow_amounts"][0]["value"] == 7.75
    assert land["allocation_category"] not in {"acquisition", "acquisition_integration"}
    capex = next(a for a in records if a["allocation_name"] == "Reported annual capital expenditure")
    assert capex["amount"] == 72.06 and capex["amount_period"] == "fy26"                                                   # the 7.75 never joined the annual capex record


@needs
def test_data_patterns_paid_and_proposed_dividends_are_separate_events_with_the_filings_amounts():
    records = [a for a in outcomes("datapatterns") if a["allocation_category"] == "dividend"]
    paid = {a["amount_period"]: a["amount"] for a in records if a.get("lifecycle") == "paid" and a["amount"] is not None}
    assert paid == {"fy23": 18.16, "fy24": 25.19, "fy25": 36.39, "fy26": 44.23}                                           # dividends paid per the cash-flow statements
    proposed = [a for a in records if a.get("lifecycle") == "proposed"]
    assert proposed and all(a["amount"] is None and a["current_status"] == "announced" for a in proposed)
    assert not any(a.get("lifecycle") == "paid" and a.get("lifecycle") == "proposed" for a in records)


@needs
def test_tanla_related_party_loan_is_a_closing_balance_in_its_actual_period_not_a_fy26_inflow():
    loan = next(a for a in outcomes("tanla") if "unsecured loan" in a["allocation_name"].lower())
    assert loan["amount"] is None and loan["non_flow_amounts"][0]["role"] == "closing_balance" and abs(loan["non_flow_amounts"][0]["value"] - 132.1914) < 1e-4
    assert loan["event_period"] == "fy24"
    esop = next(a for a in outcomes("tanla") if "ESOP trust" in a["allocation_name"])
    assert esop["amount"] == 18.2146 and esop["amount_period"] == "fy26"


@needs
@pytest.mark.parametrize("company", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_every_dividend_amount_in_the_outcomes_is_the_registry_figure_for_its_year(company):
    registry_paid = {fy: abs(f["value"]) for fy in years(company) for f in facts(company, fy) if f["metric_id"] == "dividends_paid"}
    for a in outcomes(company):
        if a["allocation_category"] == "dividend" and a["amount"] is not None and a.get("lifecycle") != "proposed":
            fy = a["amount_period"]
            if fy in registry_paid:
                assert abs(a["amount"] - registry_paid[fy]) <= max(0.5, 0.01 * registry_paid[fy]), (company, fy, a["amount"], registry_paid[fy])


@needs
@pytest.mark.parametrize("company", ["sun_pharma", "tanla", "ujjivan", "datapatterns"])
def test_every_stored_capital_label_in_cim_and_pcim_is_a_fixed_point_of_the_own_text_rule(company):
    """No label survives in the CIM / PCIM capital-allocation sources that the shared own-text rule would replace or quarantine (the corrected outcomes alone are not enough)."""
    from knowledge.capital_allocation_taxonomy import apply_label_verdict
    bad = []
    def walk(node):
        if isinstance(node, dict):
            if "canonical_category" in node and "value" in node and not node.get("classification_status"):
                if apply_label_verdict(node).get("canonical_category") != node["canonical_category"]:
                    bad.append((node.get("source_year"), str(node["value"])[:50], node["canonical_category"]))
            for x in node.values():
                walk(x)
        elif isinstance(node, list):
            for x in node:
                walk(x)
    pcim = json.loads((CRIT / company / "company_memory" / "pcim_v1.json").read_text())
    walk(pcim.get("capital_allocation_inputs"))
    assert not bad, bad[:5]
    if company == "sun_pharma":
        text = json.dumps(pcim.get("capital_allocation_inputs"))
        assert not ("Proceeds from borrowings" in text and '"canonical_category": "debt_repaid"' in text.split("Proceeds from borrowings")[1][:900])


@needs
def test_verified_organon_and_vishvakarma_interpretations_are_preserved():
    organon = next(a for a in outcomes("sun_pharma") if "Organon" in a["allocation_name"])
    assert organon["event_period"] == "fy27" and organon["current_status"] == "announced" and organon["amount"] is None and organon["event_date"] == "2026-04-27"
    vish = next(a for a in outcomes("ujjivan") if "Vishvakarma" in a["allocation_name"])
    assert vish["event_nature"] == "minority_or_subscription" and vish["amount"] is None and vish["amount_basis"] == "share_count_not_currency"


def test_the_recorded_injection_experiment_found_no_trace_of_the_reinjected_liquidity_bucket():
    """Sun FY21's 1,376.63 (a liquidity-note bucket) was re-injected as normalized total debt and the year-level chain, company-level chain, CIM / PCIM and the panel's real metric registry
    were rebuilt (preview/critical_remediation_evidence/inject_experiment.py). The recorded result is part of the evidence."""
    report = ROOT / "preview" / "critical_remediation_evidence" / "inject_report.json"
    if not report.exists():
        pytest.skip("evidence not present")
    data = json.loads(report.read_text())
    assert any(r["metric"] == "total_debt" and r["fy"] == "fy21" and abs(r["value"] - 1376.63) < 1e-6 for r in data["scan"]["rejected"])
    assert data["scan"]["leaks"] == [] and data["panel"]["leaks"] == [] and data["panel"]["panel_registry_sizes"]["sun_pharma"] > 500
