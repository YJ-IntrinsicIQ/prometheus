"""Phase 1 SSOT: upstream data integrity (financial facts and capital-allocation records).

Unit tests exercise the shared mechanisms on synthetic inputs. Data tests read a candidate root built by `tools/g1_candidate_build.py` (P1_ROOT, default
/private/tmp/claude-501/p1/c1) and, for the 'before' state, the served companies/ tree; they are skipped when the root is absent."""
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get("P1_ROOT", "/private/tmp/claude-501/p1/c1"))
needs_root = pytest.mark.skipif(not (ROOT / "companies").exists(), reason="candidate root absent")

from intelligence.capital_allocation_outcomes import builder as B  # noqa: E402
from intelligence.capital_allocation_outcomes.validators import validate_capital_allocation_outcomes_payload as V  # noqa: E402
from knowledge import capital_allocation_taxonomy as T  # noqa: E402
from knowledge.company_memory.guardrails import evidenced_announcement_period  # noqa: E402
from knowledge.financials import fact_registry as FR  # noqa: E402
from knowledge.financials.fact_registry_schema import FinancialFact, derive_period_role  # noqa: E402


def j(p):
    return json.loads(Path(p).read_text())


# ── taxonomy: an item is classified from its own fields ──
def test_minority_equity_investment_is_a_strategic_investment_not_r_and_d():
    c = T.normalize_capital_allocation_item({"action": "Acquired 200 equity shares of Zeta Payments Private Limited", "category": "Equity investment (minority stake)",
                                              "purpose": "support incorporation of Zeta to apply to RBI to set up a pan-India umbrella entity for retail payments, research and technology"})
    assert c["canonical_category"] == "strategic_investments"


def test_the_source_chunk_does_not_classify_other_lines():
    chunk = "Repayment of borrowings (120.5)\nDividend paid (30.0)\nProceeds from borrowings 10.0"
    c = T.normalize_capital_allocation_item({"action": "Dividend paid", "category": "Dividend", "purpose": "Dividend paid", "source_chunk": chunk})
    assert c["canonical_category"] == "dividend_paid" and c["capital_allocation_group"] == "shareholder_returns"


@pytest.mark.parametrize("action,category,purpose", [
    ("Transfer to Statutory Reserve", "Reserve transfer", "Appropriation to statutory reserve (includes takeover of statutory reserves under a scheme of amalgamation)"),
    ("Issued / subscribed and paid-up equity capital", "Common equity (Tier 1)", ""),
])
def test_reserve_transfers_and_regulatory_capital_are_not_allocations(action, category, purpose):
    assert T.normalize_capital_allocation_item({"action": action, "category": category, "purpose": purpose})["capital_allocation_group"] in B._NOT_AN_ALLOCATION_GROUPS


def test_a_stored_label_is_verified_against_the_items_own_wording():
    ok = {"value": "Dividend paid", "category": "Dividend", "purpose": "Dividend paid", "reasoning": "Matched taxonomy keyword 'dividend paid' to dividend_paid.", "canonical_category": "dividend_paid"}
    bad = {**ok, "canonical_category": "debt_repaid", "reasoning": "Matched taxonomy keyword 'repayment of borrowings' to debt_repaid."}
    assert T.verify_stored_classification(ok)["status"] == "supported"
    v = T.verify_stored_classification(bad)
    assert v["status"] == "refreshed" and v["classification"]["canonical_category"] == "dividend_paid"
    assert T.verify_stored_classification({"value": "x"})["status"] == "untested"


# ── allocation builder: event meaning, amount meaning, determinism ──
VISH = {"value": "Acquired 200 equity shares of Vishvakarma Payments Private Limited", "category": "Equity investment (minority stake)", "canonical_category": "r_and_d_investment",
        "capital_allocation_group": "true_capital_deployment", "amount": "200 shares at INR 10 per share (total INR 2,000)",
        "purpose": "support incorporation of Vishvakarma to set up an umbrella entity for retail payments (platform, technology, research)"}


def test_a_minority_subscription_is_never_mapped_to_r_and_d_whatever_the_stored_label_says():
    assert B._map_allocation_category(VISH, {}) == "strategic_investment"


def test_the_companys_own_preference_share_issuance_is_not_an_investment():
    item = {"value": "Issued perpetual non-cumulative preference shares (PNCPS)", "category": "Perpetual Non-Cumulative Preference Shares (Additional Tier 1)", "canonical_category": "r_and_d_investment",
            "capital_allocation_group": "true_capital_deployment"}
    assert B._map_allocation_category(item, {}) != "strategic_investment"


def test_a_share_count_is_never_a_currency_amount():
    item = {**VISH, "allocation_category": "strategic_investment"}
    assert B._candidate_amount(item, {"amount": 200.0}) is None
    assert B._amount_basis(item, {}, None) == "share_count_not_currency"
    assert B._amount_basis({"amount": "20,298 equity shares; face value 10; issue price 35"}, {}, None) == "share_count_not_currency"


def test_named_investments_merge_only_on_a_distinctive_name_token():
    a = B._build_allocation_group(B._candidate_from_item("fy21", VISH, "true_capital_deployment", {}))
    other = B._candidate_from_item("fy25", {"value": "Selective investments in equity IPOs", "category": "Equity investment", "capital_allocation_group": "true_capital_deployment",
                                            "canonical_category": "strategic_investments"}, "true_capital_deployment", {})
    assert B._group_similarity(a, other) == 0
    same = B._candidate_from_item("fy22", {**VISH, "value": "Vishvakarma Payments Private Limited - further equity subscription"}, "true_capital_deployment", {})
    assert B._group_similarity(a, same) >= B._HIGH_SPECIFICITY_MERGE_THRESHOLD


def test_the_family_key_does_not_depend_on_token_order():
    assert B._family_key("dividend", "Dividend paid to shareholders") == B._family_key("dividend", "shareholders paid dividend to")


def test_entity_is_parsed_only_for_entity_events_with_a_legal_suffix():
    assert B._entity_from_name(VISH["value"], "strategic_investment") == "Vishvakarma Payments Private Limited"
    assert B._entity_from_name("Acquisition of ValueFirst from Twilio", "acquisition") is None
    assert B._entity_from_name(VISH["value"], "organic_capex") is None


# ── contract at the existing validator ──
def _alloc(**kw):
    base = {"allocation_id": "CAO-0001", "allocation_name": "x", "normalized_name": "x", "allocation_category": "organic_capex", "current_status": "deployed", "outcome_status": "unable_to_verify",
            "deployment_periods": ["fy25", "fy26"], "first_observed_period": "fy25", "source_references": [{"a": 1}], "confidence": {"level": "high", "basis": ["x"], "limitations": []}, "amount": 10.0,
            "amount_period": "fy26", "amount_unit": "INR crore", "amount_aggregation": "single_period_flow", "amount_basis": "source_item"}
    return {**base, **kw}


def codes(a):
    return {i["code"] for i in V({"allocations": [a]}, timelines_payload={"timelines": []}, assessments_payload={"assessments": []})["issues"]}


def test_contract_accepts_a_single_period_amount_and_rejects_the_unsupported_combinations():
    assert not ({"amount_without_period", "amount_period_outside_deployment", "amount_unit_or_aggregation_unsupported", "non_currency_amount_promoted"} & codes(_alloc()))
    assert "amount_without_period" in codes(_alloc(amount_period=None))
    assert "amount_period_outside_deployment" in codes(_alloc(amount_period="fy20"))
    assert "amount_unit_or_aggregation_unsupported" in codes(_alloc(amount_aggregation="cumulative"))
    assert "non_currency_amount_promoted" in codes(_alloc(amount_basis="share_count_not_currency"))
    assert "event_nature_category_conflict" in codes(_alloc(event_nature="minority_or_subscription", allocation_category="research_and_development"))


def test_a_legacy_record_without_typed_fields_is_a_warning_not_a_failure():
    legacy = _alloc()
    for k in ("amount_period", "amount_unit", "amount_aggregation"):
        legacy.pop(k)
    r = V({"allocations": [legacy]}, timelines_payload={"timelines": []}, assessments_payload={"assessments": []})
    assert any(i["code"] == "amount_without_period" and i["severity"] == "warning" for i in r["issues"])


# ── financial registry: what a figure IS in time ──
def test_period_role_from_statement_and_wording():
    assert derive_period_role("cash_and_equivalents", "balance_sheet", "(iii) Cash and cash equivalents") == "closing_balance"
    assert derive_period_role("cash_and_equivalents", "cash_flow", "Cash and cash equivalents at the beginning of the year") == "opening_balance"
    assert derive_period_role("cfo", "cash_flow", "Net cash from operating activities") == "annual_flow"
    assert derive_period_role("total_debt", "balance_sheet", "derived:total_debt", True) == "closing_balance"


def _fact(**kw):
    base = dict(metric_id="cash_and_equivalents", metric_name="Cash", fiscal_year="fy26", period="March 31, 2026", value=10268.77, unit="INR crore", basis="consolidated", source_statement="cash_flow",
                source_artifact="normalized_fundamentals.json", source_line_item="Cash and cash equivalents at the beginning of the year", source_page=247, confidence="high",
                availability_status="present_direct", usable_downstream=True)
    return FinancialFact(**{**base, **kw})


def test_an_opening_balance_can_never_be_a_closing_stock_fact():
    f = _fact()
    FR._enforce_period_role(f)
    assert (f.availability_status, f.usable_downstream, f.reconciliation_status) == ("invalid", False, "fail")
    g = _fact(source_statement="balance_sheet", source_line_item="(iii) Cash and cash equivalents", value=9770.51)
    FR._enforce_period_role(g)
    assert g.availability_status == "present_direct" and g.usable_downstream


# ── announcement period must be evidenced ──
def test_an_unevidenced_earlier_announcement_year_falls_back_to_the_filing_year():
    assert evidenced_announcement_period(2025, "fy26", "acquisition (Organon) announced")["period"] == "fy26"
    assert evidenced_announcement_period("fy24", "fy26", "plant commissioned in FY2024")["period"] == "fy24"
    assert evidenced_announcement_period(None, "fy26", "x")["period"] == "fy26"


# ── data: the candidate records, source → registry → truth pack → derived ──
def fact(co, fy, metric):
    r = j(ROOT / "companies" / co / fy / "financials" / "financial_fact_registry.json")
    return next(f for f in r["available_facts"] + r["derived_facts"] + r["partial_facts"] if f["metric_id"] == metric)


@needs_root
def test_sun_pharma_fy26_cash_and_debt_are_closing_balances_from_the_right_lines():
    cash, st, lt, total = (fact("sun_pharma", "fy26", m) for m in ("cash_and_equivalents", "short_term_debt", "long_term_debt", "total_debt"))
    assert (cash["value"], st["value"], lt["value"], total["value"]) == (9770.51, 4050.35, 31.26, 4081.61)
    assert all(f["period_role"] == "closing_balance" and f["basis"] == "consolidated" and f["unit"] == "INR crore" and f["source_page"] for f in (cash, st, lt))
    assert abs(st["value"] + lt["value"] - total["value"]) < 0.01 and total["inputs_used"] == ["short_term_debt", "long_term_debt"]
    n = j(ROOT / "companies/sun_pharma/fy26/financials/normalized_fundamentals.json")["balance_sheet"]
    assert n["long_term_debt"]["value_crore"] != 44894.03 and "assets" not in n["long_term_debt"]["source_line_item"].lower()


@needs_root
def test_the_truth_pack_and_net_debt_inherit_the_registry():
    tp = j(ROOT / "companies/sun_pharma/company_memory/financials/financial_truth_pack.json")
    got = {(f["metric_id"], f["fiscal_year"]): f["value"] for k in ("usable_current_metrics", "usable_derived_metrics") for f in tp[k]}
    assert got[("cash_and_equivalents", "fy26")] == 9770.51 and got[("total_debt", "fy26")] == 4081.61
    assert got[("net_debt", "fy26")] == pytest.approx(4081.61 - 9770.51, abs=0.01)


@needs_root
def test_every_registry_stock_fact_is_a_closing_balance_in_every_company_and_year():
    bad = []
    for co in ("sun_pharma", "ujjivan", "tanla", "datapatterns"):
        for p in sorted((ROOT / "companies" / co).glob("fy*/financials/financial_fact_registry.json")):
            r = j(p)
            bad += [(co, p.parts[-3], f["metric_id"], f["source_line_item"]) for f in r["available_facts"] + r["derived_facts"] + r["partial_facts"]
                    if f["metric_id"] in FR.CLOSING_STOCK_METRICS and f["period_role"] != "closing_balance"]
    assert bad == [], bad[:5]


@needs_root
def test_certified_flow_figures_are_unchanged():
    assert fact("sun_pharma", "fy26", "cfo")["value"] == 12419.18 and fact("sun_pharma", "fy26", "revenue")["value"] == 58462.04
    assert fact("sun_pharma", "fy26", "capex")["value"] == -3609.37


def allocations(co):
    return j(ROOT / "companies" / co / "company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json")["allocations"]


@needs_root
@pytest.mark.parametrize("co", ["sun_pharma", "ujjivan", "tanla", "datapatterns"])
def test_every_amount_names_its_one_period_unit_and_aggregation(co):
    for a in allocations(co):
        if a["amount"] is not None:
            assert a["amount_period"] in a["deployment_periods"], a["allocation_id"]
            assert (a["amount_unit"], a["amount_currency"], a["amount_aggregation"]) == ("INR crore", "INR", "single_period_flow"), a["allocation_id"]
            assert a["amount_basis"] not in ("share_count_not_currency", "unit_ambiguous", "face_value_not_consideration")


@needs_root
@pytest.mark.parametrize("co", ["sun_pharma", "ujjivan", "tanla", "datapatterns"])
def test_the_candidate_outcomes_pass_the_amount_contract(co):
    v = j(ROOT / "companies" / co / "company_memory/capital_allocation_outcomes/capital_allocation_validation.json")
    assert [i for i in v["issues"] if i["severity"] != "warning"] == []


@needs_root
def test_ujjivan_vishvakarma_is_a_minority_subscription_with_no_currency_amount():
    a = next(x for x in allocations("ujjivan") if "Vishvakarma" in x["allocation_name"])
    assert (a["allocation_category"], a["event_nature"], a["amount"]) == ("strategic_investment", "minority_or_subscription", None)
    assert a["amount_basis"] == "share_count_not_currency" and "INR 2,000" in a["amount_stated"] and a["entity"] == "Vishvakarma Payments Private Limited"
    assert a["deployment_periods"] == ["fy21"]


@needs_root
@pytest.mark.parametrize("co", ["tanla", "datapatterns"])
def test_annual_capex_is_the_registry_figure_for_its_own_year_only(co):
    a = next(x for x in allocations(co) if x["allocation_category"] == "organic_capex" and x["amount"] is not None)
    yr = a["amount_period"]
    assert a["amount"] == pytest.approx(abs(fact(co, yr, "capex")["value"]), abs=0.01), (a["allocation_id"], a["amount"], yr)
    assert a["amount_aggregation"] == "single_period_flow"


@needs_root
def test_a_stale_capital_timeline_is_not_served_to_the_candidate_ledger():
    t = j(ROOT / "companies/tanla/company_memory/financials/capital_allocation_financial_timeline.json")
    fy26 = next(y for y in t["timeline"] if y["year"] == "fy26")
    assert abs(fy26["capex"]["value"]) == pytest.approx(97.6502, abs=0.01)
    assert all(abs(d.get("amount_crore") or 0) < 1000 for y in t["timeline"] for d in y["dividend_actions"])


# ── before: the served records still carry the defects (this is the red state the repair addresses) ──
SERVED = REPO / "companies"


@pytest.mark.skipif(not (SERVED / "sun_pharma").exists(), reason="served tree absent")
def test_served_records_still_show_the_defects_pending_migration():
    n = j(SERVED / "sun_pharma/fy26/financials/normalized_fundamentals.json")["balance_sheet"]
    served_wrong = n["cash_and_equivalents"]["value_crore"] == 10268.77 and n["long_term_debt"]["value_crore"] == 44894.03
    if not served_wrong:
        pytest.skip("served financials were migrated")
    assert served_wrong
