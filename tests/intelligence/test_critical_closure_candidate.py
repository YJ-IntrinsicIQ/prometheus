"""SSOT critical closure - the assembled candidate (CLOSURE_ROOT = <candidate>/companies, default the scratch assembly) read through the REAL consumers: the Ask loader, the panel's metric
registry, the authority gate, the propagation scan and the verifier's stamped verdicts. Skipped when the candidate is not present."""
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLOSURE_ROOT = Path(os.environ.get("CLOSURE_ROOT", "/private/tmp/claude-501/p6/final/companies"))
pytestmark = pytest.mark.skipif(not (CLOSURE_ROOT / "sun_pharma").exists(), reason="closure candidate not present")
COMPANIES = ("sun_pharma", "tanla", "ujjivan", "datapatterns")

from intelligence.ask_intrinsiciq.loader import SOURCE_REGISTRY, load_company_memory_sources                       # noqa: E402
from intelligence.investor_panel.runner import _build_financial_metric_registry                                    # noqa: E402
from knowledge.financials.authority_gate import check_artifact, company_artifact_paths, contradictions, load_company_authority   # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import quarantine_propagation_scan as scan_tool                                                                    # noqa: E402


def j(*parts):
    return json.loads(CLOSURE_ROOT.joinpath(*parts).read_text(encoding="utf-8"))


def years(company):
    """The company's fiscal-year directories that hold a fact registry (a year folder can exist with no financial extraction, e.g. an upcoming-year shell)."""
    return sorted(p.name for p in (CLOSURE_ROOT / company).glob("fy*") if (p / "financials" / "financial_fact_registry.json").exists())


def registry_facts(company, fy):
    registry = j(company, fy, "financials", "financial_fact_registry.json")
    return {f["metric_id"]: f for key in ("available_facts", "derived_facts", "partial_facts") for f in registry.get(key) or []}, registry


def usable(company, fy, metric):
    fact = registry_facts(company, fy)[0].get(metric)
    return fact if fact and fact.get("usable_downstream") else None


# ---- authority at the consumer boundary -----------------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("company", COMPANIES)
def test_every_financial_artifact_of_the_candidate_is_recorded_against_the_current_registries_and_untouched(company):
    base = CLOSURE_ROOT / company
    paths = company_artifact_paths(base)
    assert paths
    authority = load_company_authority(base)
    bad = {p: check_artifact(base, p, authority)[0] for p in paths if check_artifact(base, p, authority)[0] != "valid"}
    assert not bad


@pytest.mark.parametrize("company", COMPANIES)
def test_the_real_ask_loader_loads_the_financial_sources_of_a_bound_company_and_the_panel_registry_is_populated(company):
    sources = load_company_memory_sources(company, companies_root=CLOSURE_ROOT)["sources"]
    for name in ("pcim", "cim", "financial_truth_pack", "financial_trends"):
        assert sources[name]["status"] == "loaded", (company, name, sources[name].get("error"))
    pcim = sources["pcim"]["payload"]
    assert pcim.get("financial_panel_ready") is True and len(_build_financial_metric_registry(pcim, list(pcim))) > 100


@pytest.mark.parametrize("company", COMPANIES)
def test_no_artifact_of_the_candidate_contradicts_the_registry_it_was_bound_to(company):
    authority = load_company_authority(CLOSURE_ROOT / company)
    for rel in ("company_memory/pcim_v1.json", "company_memory/cim_v1.json", "company_memory/financials/financial_trends.json", "company_memory/financials/financial_truth_pack.json"):
        payload = j(company, *rel.split("/"))
        found = [c for c in contradictions(payload, authority) if c["reason"].startswith("the registry rejects")]
        assert not found, (company, rel, found[:3])


def test_sun_fy21_debt_of_the_liquidity_note_is_not_in_ask_or_the_panel_registry_and_the_true_debt_is():
    sources = load_company_memory_sources("sun_pharma", companies_root=CLOSURE_ROOT)["sources"]
    pcim = sources["pcim"]["payload"]
    panel = _build_financial_metric_registry(pcim, list(pcim))
    values = [e.get("value") for e in panel if e.get("canonical_metric") == "total_debt" and e.get("period") == "fy21"]
    assert 1376.63 not in values and 3343.03 in values
    assert "1376.63" not in json.dumps(sources["financial_truth_pack"]["payload"]) and "1376.63" not in json.dumps(pcim)


# ---- propagation scan ---------------------------------------------------------------------------------------------------------------------------------------------------------------

def test_the_structural_scan_finds_no_rejected_fact_used_as_evidence_anywhere_in_any_projection():
    result = scan_tool.scan(CLOSURE_ROOT)
    assert result["rejected_figures"] >= 60                                       # every rejected fact, with no monetary cut-off
    assert result["points_examined"] > 10000
    assert result["leaks"] == [], result["leaks"][:5]


def test_the_panel_registry_built_from_every_candidate_pcim_holds_no_rejected_figure():
    assert scan_tool.panel_registry_leaks(CLOSURE_ROOT)["leaks"] == []


def test_ujjivan_fy24_cash_is_unavailable_or_the_cash_flow_statements_figure_never_the_bank_balance_sheet_component():
    fact = usable("ujjivan", "fy24", "cash_and_equivalents")
    assert fact is None or abs(fact["value"] - 2523.9622) < 0.001
    # the rejected figure may remain only where it is recorded as a rejected diagnostic; as evidence (a series point, a truth-pack metric) it must not appear anywhere
    assert [l for l in scan_tool.scan(CLOSURE_ROOT)["leaks"] if l["company"] == "ujjivan" and l["metric"] == "cash_and_equivalents"] == []
    pack = j("ujjivan", "company_memory", "financials", "financial_truth_pack.json")
    assert not [m for key in ("usable_current_metrics", "usable_derived_metrics", "partial_metrics") for m in pack[key] if m["metric_id"] == "cash_and_equivalents" and m["fiscal_year"] == "fy24"]


# ---- provisional facts that were materially wrong ----------------------------------------------------------------------------------------------------------------------------------

def test_ujjivan_fy21_deposits_are_not_the_microbanking_segment_figure():
    fact = usable("ujjivan", "fy21", "total_deposits")
    assert fact is None or abs(fact["value"] - 1029.0) > 1e-6


def test_ujjivan_weighted_average_share_counts_carry_the_unit_their_row_states():
    for fy, expected in (("fy22", 1_728_314_000), ("fy24", 1_927_790_000), ("fy25", 1_933_800_000)):
        fact = usable("ujjivan", fy, "weighted_avg_shares")
        assert fact is None or abs(fact["value"] - expected) < 1000, (fy, fact and fact["value"])
        basic = usable("ujjivan", fy, "weighted_average_basic_shares")
        assert basic is None or basic["value"] > 1e8
    for fy in ("fy22", "fy23", "fy24", "fy25"):
        fact = usable("ujjivan", fy, "weighted_avg_shares")
        assert fact is None or "diluted" not in fact["source_line_item"].lower()


def test_sun_cost_of_materials_is_the_primary_statements_line_not_stores_and_spares():
    for fy in ("fy22", "fy23", "fy24", "fy26"):
        fact = usable("sun_pharma", fy, "cost_of_materials")
        assert fact is None or "stores" not in fact["source_line_item"].lower(), (fy, fact and fact["source_line_item"])
    fact = usable("sun_pharma", "fy26", "cost_of_materials")
    assert fact is None or abs(fact["value"] - 7389.02) < 0.01


def test_no_company_carries_a_usable_gross_margin_or_cogs_days_computed_on_part_of_the_cost_of_goods_sold():
    for company in COMPANIES:
        for fy in years(company):
            facts = registry_facts(company, fy)[0]
            for metric in ("gross_margin", "inventory_days", "payable_days", "cash_conversion_cycle"):
                fact = facts.get(metric)
                assert not (fact and fact.get("usable_downstream") and isinstance(fact.get("value"), (int, float))), (company, fy, metric)
    assert "98.3542" not in json.dumps(j("sun_pharma", "company_memory", "pcim_v1.json"))


@pytest.mark.parametrize("company", COMPANIES)
def test_a_report_with_one_declared_basis_has_its_facts_on_that_basis(company):
    for fy in years(company):
        normalized = j(company, fy, "financials", "normalized_fundamentals.json")
        entity = (normalized.get("registry_context") or {}).get("entity_basis")
        if entity in ("standalone", "consolidated"):
            facts, _ = registry_facts(company, fy)
            wrong = {m: f["basis"] for m, f in facts.items() if f.get("usable_downstream") and f["basis"] in ("standalone", "consolidated") and f["basis"] != entity}
            assert not wrong, (company, fy, entity, list(wrong.items())[:3])


# ---- verifier state travels with the evidence ---------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("company", COMPANIES)
def test_no_usable_fact_is_one_the_verifier_rejects(company):
    rejected = []
    for fy in years(company):
        path = CLOSURE_ROOT / company / fy / "financials" / "financial_fact_verification.json"
        if not path.exists():
            continue
        verdicts = json.loads(path.read_text())["verdicts"]
        facts, _ = registry_facts(company, fy)
        rejected += [(fy, m) for m, v in verdicts.items() if v["status"] == "REJECTED" and facts.get(m, {}).get("usable_downstream")]
    assert not rejected, rejected[:5]


@pytest.mark.parametrize("company", COMPANIES)
def test_every_truth_pack_metric_and_every_registry_point_in_cim_and_pcim_states_its_verification(company):
    pack = j(company, "company_memory", "financials", "financial_truth_pack.json")
    for key in ("usable_current_metrics", "usable_derived_metrics", "partial_metrics"):
        for item in pack.get(key) or []:
            assert item.get("verification_status"), (company, key, item.get("metric_id"))
    authority = load_company_authority(CLOSURE_ROOT / company)
    from knowledge.financials.authority_gate import iter_metric_points, known_metrics
    known = known_metrics(authority)
    for name in ("pcim_v1.json", "cim_v1.json"):
        missing = [p for p, m, y, h, _k in iter_metric_points(j(company, "company_memory", name), known=known) if y and m in known and not h.get("verification_status")]
        assert not missing, (company, name, missing[:3])


# ---- economic events -----------------------------------------------------------------------------------------------------------------------------------------------------------------

def outcomes(company):
    return j(company, "company_memory", "capital_allocation_outcomes", "capital_allocation_outcomes.json")["allocations"]


def test_data_patterns_issues_are_separate_events_and_the_qip_proceeds_are_gross_net_and_expenses():
    records = outcomes("datapatterns")
    qips = [r for r in records if r["allocation_category"] == "equity_issuance" and re.search(r"qip|qualified institutional", r["allocation_name"], re.I) and not re.search(r"allocation|use of", r["allocation_name"], re.I)]
    assert len(qips) == 1
    qip = qips[0]
    assert qip["event_date"] == "2023-03-13" and qip["event_period"] == "fy23" and qip["amount"] == 487.74 and qip["amount_basis_detail"] == "net_proceeds_after_issue_expenses"
    assert qip["proceeds_breakdown"]["issue_expenses_crore"] == 12.24 and abs(qip["proceeds_breakdown"]["gross_proceeds_crore"] - 500.0) < 0.1
    sources = " ".join(s["short_excerpt"].lower() for s in qip["source_references"])
    assert "bonus" not in sources and "ipo" not in sources.replace("proceeds", "") and "private placement" not in sources and "repayment of borrowings" not in sources
    assert any(re.search(r"ipo", r["allocation_name"], re.I) and r["allocation_category"] == "equity_issuance" for r in records)
    assert any(re.search(r"bonus", r["allocation_name"], re.I) and r["economic_role"] == "NON_CASH_CAPITALISATION" for r in records)


def test_data_patterns_land_is_capital_expenditure_in_every_field():
    land = [r for r in outcomes("datapatterns") if re.search(r"land", r["allocation_name"], re.I)]
    assert land
    for r in land:
        assert r["allocation_category"] == "organic_capex" and r["economic_role"] == "DEPLOYMENT_ORGANIC_CAPEX" and r["amount"] is None
        assert any(n["role"] == "cumulative_utilisation" and n["value"] == 7.75 for n in r["non_flow_amounts"])


@pytest.mark.parametrize("company", COMPANIES)
def test_a_proposed_dividend_is_not_a_completed_distribution_in_the_outcomes_or_in_economic_attribution(company):
    proposed = [r for r in outcomes(company) if r["allocation_category"] in ("dividend", "special_dividend") and r.get("lifecycle") == "proposed"]
    for r in proposed:
        assert r["outcome_attribution"] == "NO_OUTCOME_EVIDENCE" and r["execution_state"] != "COMPLETED" and r["financial_outcome_state"] == "UNABLE_TO_ATTRIBUTE"
        assert r["deployment_eligibility"] == "INELIGIBLE_ANNOUNCED_NOT_DEPLOYED" and r["amount"] is None
        assert "no capital has been returned" in r["financial_outcome"] or "no payment is evidenced" in r["financial_outcome"]
    cases = j(company, "company_memory", "economic_attribution", "economic_attribution_intelligence.json")
    ids = {r["allocation_id"] for r in proposed}
    for case in json.dumps(cases) and cases.get("cases", []):
        if case.get("source_action_id") in ids:
            assert case["economic_consequence"] == "unknown" and case["financial_consequence"] == "none_disclosed"


def test_data_patterns_paid_dividends_remain_the_cash_flow_statements_amounts():
    paid = sorted(r["amount"] for r in outcomes("datapatterns") if r["allocation_category"] == "dividend" and r.get("lifecycle") == "paid" and r["amount"])
    assert paid == [18.16, 25.19, 36.39, 44.23]


def test_the_verified_organon_vishvakarma_and_tanla_corrections_are_preserved():
    organon = [r for r in outcomes("sun_pharma") if "organon" in (r["allocation_name"] + str(r.get("entity"))).lower()]
    assert organon and organon[0]["event_period"] == "fy27" and organon[0]["event_completion"] == "pending"
    vishva = [r for r in outcomes("ujjivan") if "vishvakarma" in (r["allocation_name"] + str(r.get("entity"))).lower()]
    assert vishva and vishva[0]["event_nature"] == "minority_or_subscription" and vishva[0]["amount"] is None
    loan = [r for r in outcomes("tanla") if any(n["role"] == "closing_balance" and abs(n["value"] - 132.1914) < 0.01 for n in r["non_flow_amounts"])]
    assert loan and loan[0]["amount"] is None and loan[0]["event_period"] == "fy24"
