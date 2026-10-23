"""Financial authority is enforced where evidence is CONSUMED. These are the states a consumer can meet that a successful full rebuild never produces: registries missing, a truth pack
empty, both gone, a rejected fact beside a valid-looking normalized figure, a derived ratio older than the rejection, an artifact from an earlier build next to current registries, an
edited artifact. The real Ask loader, the real panel metric registry and the real ratio calculator are used; nothing is mocked."""
import json
import shutil
from pathlib import Path

from intelligence.ask_intrinsiciq.loader import load_company_memory_sources
from intelligence.investor_panel.runner import _build_financial_metric_registry
from knowledge.financials.authority_gate import bind_company, check_artifact, contradictions, load_company_authority
from knowledge.financials.ratio_calculator import calculate_financial_ratios
from tests.financials.test_financial_fact_registry import _normalized_entry, _normalized_payload, _reconciliation_payload

GOOD, BAD = 3343.03, 1376.63


def _w(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fact(metric, value, *, usable=True, status="present_direct", year="fy21"):
    return {"metric_id": metric, "metric_name": metric, "fiscal_year": year, "period": year, "value": value, "unit": "INR crore", "basis": "consolidated", "source_statement": "balance_sheet",
            "source_line_item": metric, "source_page": 1, "availability_status": status, "usable_downstream": usable, "derived": False}


def _registry(debt_fact):
    return {"available_facts": [_fact("net_worth", 49479.83), _fact("cash_and_equivalents", 600.0)] + ([debt_fact] if debt_fact["usable_downstream"] else []),
            "invalid_facts": [] if debt_fact["usable_downstream"] else [debt_fact], "derived_facts": [], "partial_facts": [], "missing_facts": [], "unreliable_facts": []}


def _company(tmp_path, *, debt=GOOD, bind=True):
    base = tmp_path / "companies"
    root = base / "acme"
    _w(root / "fy21" / "financials" / "financial_fact_registry.json", _registry(_fact("total_debt", debt)))
    point = {"metric": "total_debt", "series": [{"year": "fy21", "value": debt}]}
    pack = {"company": "acme", "usable_current_metrics": [{"metric_id": "total_debt", "fiscal_year": "fy21", "value": debt}], "usable_derived_metrics": [], "partial_metrics": []}
    for rel in ("company_memory/financials/financial_truth_pack.json", "company_memory/financial_truth_pack.json"):
        _w(root / rel, pack)
    _w(root / "company_memory/financials/financial_trends.json", {"company": "acme", "metric_series": {"total_debt": [{"year": "fy21", "value": debt}]}})
    _w(root / "company_memory/pcim_v1.json", {"company": "acme", "financial_panel_ready": True,
                                              "balance_sheet_strength_inputs": {"summary": "Balance sheet strength looks healthy.", "metrics": [point]}})
    _w(root / "company_memory/cim_v1.json", {"company": "acme", "financial_intelligence": {"trends": {"metric_series": {"total_debt": [{"year": "fy21", "value": debt}]}}}})
    _w(root / "company_memory/investor_panel/graham_analysis.json", {"company": "acme", "rating": "strong", "evidence": [{"metric": "total_debt", "year": "fy21", "value": debt}]})
    if bind:
        bind_company(root, output_root=base)
    return base, root


def _load(base):
    sources = load_company_memory_sources("acme", companies_root=base)["sources"]
    pcim = sources["pcim"].get("payload") or {}
    return sources, pcim, _build_financial_metric_registry(pcim, list(pcim))


def _statuses(sources):
    return {name: sources[name]["status"] for name in ("pcim", "cim", "financial_truth_pack", "financial_trends", "graham_analysis")}


def test_control_a_consistent_bound_company_loads_and_feeds_the_panel(tmp_path):
    base, _ = _company(tmp_path)
    sources, pcim, panel = _load(base)
    assert set(_statuses(sources).values()) == {"loaded"} and pcim["financial_panel_ready"] is True
    assert {e["value"] for e in panel if e["canonical_metric"] == "total_debt"} == {GOOD}


def test_scenario_1_missing_registries_make_every_financial_artifact_unavailable(tmp_path):
    base, root = _company(tmp_path)
    (root / "fy21/financials/financial_fact_registry.json").unlink()
    sources, pcim, panel = _load(base)
    assert set(_statuses(sources).values()) == {"authority_unavailable"} and pcim == {} and panel == []
    assert "FINANCIAL_AUTHORITY_NO_AUTHORITY" in sources["pcim"]["error"]


def test_scenario_2_an_empty_truth_pack_is_unavailable_not_loaded_with_zero_metrics(tmp_path):
    base, root = _company(tmp_path)
    for rel in ("company_memory/financials/financial_truth_pack.json", "company_memory/financial_truth_pack.json"):
        _w(root / rel, {})
    sources, pcim, panel = _load(base)
    assert sources["financial_truth_pack"]["status"] == "authority_unavailable"
    # everything built FROM the truth pack is unavailable too: a stored 'ready' flag and a healthy-sounding summary do not survive the loss of the evidence they summarise
    assert sources["pcim"]["status"] == "authority_unavailable" and "FINANCIAL_AUTHORITY_STALE" in sources["pcim"]["error"] and pcim == {} and panel == []
    assert sources["graham_analysis"]["status"] == "authority_unavailable"


def test_scenario_2b_a_truth_pack_that_is_recorded_but_holds_no_metric_is_unavailable(tmp_path):
    base, root = _company(tmp_path, bind=False)
    for rel in ("company_memory/financials/financial_truth_pack.json", "company_memory/financial_truth_pack.json"):
        _w(root / rel, {"company": "acme", "usable_current_metrics": [], "usable_derived_metrics": [], "partial_metrics": []})
    bind_company(root, output_root=base)
    assert load_company_memory_sources("acme", companies_root=base)["sources"]["financial_truth_pack"]["status"] == "authority_unavailable"


def test_scenario_3_registries_and_truth_packs_both_gone_leave_no_ready_flag_summary_or_panel_input(tmp_path):
    base, root = _company(tmp_path)
    (root / "fy21/financials/financial_fact_registry.json").unlink()
    for rel in ("company_memory/financials/financial_truth_pack.json", "company_memory/financial_truth_pack.json"):
        (root / rel).unlink()
    sources, pcim, panel = _load(base)
    assert sources["financial_truth_pack"]["status"] == "missing" and sources["pcim"]["status"] == "authority_unavailable"
    assert pcim.get("financial_panel_ready") is None and not pcim.get("balance_sheet_strength_inputs") and panel == []
    assert sources["financial_trends"]["status"] == "authority_unavailable" and sources["graham_analysis"]["status"] == "authority_unavailable"


def test_scenario_4_a_registry_that_now_rejects_the_figure_invalidates_everything_built_before_the_rejection(tmp_path):
    base, root = _company(tmp_path)
    _w(root / "fy21/financials/financial_fact_registry.json", _registry(_fact("total_debt", BAD, usable=False, status="invalid")))      # the registry quarantines the debt
    n = _normalized_payload()
    n["balance_sheet"]["total_debt"] = _normalized_entry("total_debt", value_crore=BAD, value_original=str(BAD))                      # ...while the normalized file still looks valid
    _w(root / "fy21/financials/normalized_fundamentals.json", n)
    sources, pcim, panel = _load(base)
    assert set(_statuses(sources).values()) == {"authority_unavailable"} and pcim == {} and panel == []
    assert "FINANCIAL_AUTHORITY_STALE" in sources["pcim"]["error"]


def test_scenario_5_a_ratio_calculation_reads_the_persisted_rejection_even_though_the_normalized_figure_looks_valid(tmp_path, monkeypatch):
    monkeypatch.setattr("knowledge.financials.ratio_calculator.reconciliation_blocks_stage", lambda *a, **k: [])
    root = tmp_path / "companies" / "acme" / "fy21" / "financials"
    n = _normalized_payload()
    n["balance_sheet"]["total_debt"] = {**_normalized_entry("total_debt", value_crore=BAD, value_original=str(BAD)), "source_line_item": "Total Borrowings"}
    n["balance_sheet"]["net_worth"] = _normalized_entry("net_worth", value_crore=49479.83, value_original="49479.83")
    n["balance_sheet"]["total_assets"] = _normalized_entry("total_assets", value_crore=80000.0, value_original="80000")
    n["profit_and_loss"]["revenue"] = {**_normalized_entry("revenue", value_crore=200.0, value_original="200"), "statement_type": "profit_and_loss", "source_line_item": "Revenue from operations"}
    n["profit_and_loss"]["pat"] = {**_normalized_entry("pat", value_crore=20.0, value_original="20"), "statement_type": "profit_and_loss", "source_line_item": "Profit for the year"}
    _w(root / "normalized_fundamentals.json", n)
    _w(root / "financial_reconciliation_report.json", _reconciliation_payload())
    args = dict(company="acme", year="fy21", normalized_path=root / "normalized_fundamentals.json", reconciliation_path=root / "financial_reconciliation_report.json")
    assert calculate_financial_ratios(**args).ratios["debt_to_equity"].value is not None                         # nothing rejects it yet
    _w(root / "financial_fact_registry.json", _registry(_fact("total_debt", BAD, usable=False, status="invalid")))   # the registry now does
    ratios = calculate_financial_ratios(**args).ratios
    assert ratios["debt_to_equity"].value is None and ratios["net_debt"].value is None


def test_scenario_6_a_derived_artifact_older_than_the_rejection_is_stale(tmp_path):
    base, root = _company(tmp_path)
    ratios = root / "fy21/financials/financial_ratios.json"
    _w(ratios, {"ratios": {"debt_to_equity": {"value": BAD / 49479.83}}})
    bind_company(root, output_root=base)
    assert check_artifact(root, "fy21/financials/financial_ratios.json")[0] == "valid"
    _w(root / "fy21/financials/financial_fact_registry.json", _registry(_fact("total_debt", BAD, usable=False, status="invalid")))
    assert check_artifact(root, "fy21/financials/financial_ratios.json")[0] == "stale"


def test_scenario_7_artifacts_from_an_earlier_build_beside_current_registries_are_unbound_and_unavailable(tmp_path):
    """The October 16 files carry no record of the registries they were built against; with the CURRENT registries beside them they must not be trusted."""
    base, root = _company(tmp_path, bind=False)
    old = {"company": "acme", "financial_panel_ready": True, "balance_sheet_strength_inputs": {"summary": "Balance sheet strength looks healthy.",
                                                                                              "metrics": [{"metric": "total_debt", "series": [{"year": "fy21", "value": BAD}]}]}}
    _w(root / "company_memory/pcim_v1.json", old)
    sources, pcim, panel = _load(base)
    assert sources["pcim"]["status"] == "authority_unavailable" and "UNBOUND" in sources["pcim"]["error"]
    assert pcim == {} and not any(e.get("value") == BAD for e in panel)


def test_an_artifact_edited_after_it_was_recorded_is_tampered(tmp_path):
    base, root = _company(tmp_path)
    path = root / "company_memory/pcim_v1.json"
    payload = json.loads(path.read_text())
    payload["balance_sheet_strength_inputs"]["metrics"][0]["series"][0]["value"] = BAD
    _w(path, payload)
    assert check_artifact(root, "company_memory/pcim_v1.json")[0] == "tampered"
    assert load_company_memory_sources("acme", companies_root=base)["sources"]["pcim"]["status"] == "authority_unavailable"


def test_the_old_figure_cannot_reappear_in_ask_or_the_panel_registry_with_or_without_a_rebuild(tmp_path):
    base, root = _company(tmp_path, debt=BAD)                                   # a stale company built with the wrong debt
    _w(root / "fy21/financials/financial_fact_registry.json", _registry(_fact("total_debt", GOOD)))   # the registry now holds the right one
    sources, pcim, panel = _load(base)
    assert pcim == {} and not any(e.get("value") == BAD for e in panel)          # without a rebuild: stale evidence is unavailable
    bind_company(root, output_root=base)                                          # a "rebuild" that kept the old content is still caught by the content check
    payload = json.loads((root / "company_memory/pcim_v1.json").read_text())
    assert contradictions(payload, load_company_authority(root))                 # ...because the registry's usable value is not the one the artifact states


def test_contradictions_follow_the_parent_metric_into_nested_series_and_ignore_coincident_values(tmp_path):
    base, root = _company(tmp_path)
    registry = _registry(_fact("total_debt", BAD, usable=False, status="invalid"))
    registry["available_facts"] = [_fact("cash_and_equivalents", BAD)]            # a DIFFERENT metric legitimately holds the same number
    _w(root / "fy21/financials/financial_fact_registry.json", registry)
    authority = load_company_authority(root)
    nested = {"balance_sheet_strength_inputs": {"metrics": [{"metric": "total_debt", "series": [{"year": "fy21", "value": BAD}]}]},
              "trends": {"metric_series": {"total_debt": [{"year": "fy21", "value": BAD}]}},
              "other": {"metrics": [{"metric": "cash_and_equivalents", "series": [{"year": "fy21", "value": BAD}]}]}}        # a different metric that happens to share the number
    hits = contradictions(nested, authority)
    assert sorted(h["path"] for h in hits) == ["/balance_sheet_strength_inputs/metrics/0/series/0", "/trends/metric_series/total_debt/0"]
    assert all(h["metric"] == "total_debt" for h in hits)


def test_a_small_rejected_value_below_one_crore_is_found_like_any_other(tmp_path):
    base, root = _company(tmp_path)
    _w(root / "fy21/financials/financial_fact_registry.json", _registry(_fact("total_debt", 0.72, usable=False, status="invalid")))
    hits = contradictions({"m": {"metric": "total_debt", "year": "fy21", "value": 0.72}}, load_company_authority(root))
    assert len(hits) == 1


def test_an_artifact_is_unavailable_when_an_input_it_was_built_from_is_replaced_even_though_its_own_record_matches(tmp_path):
    base, root = _company(tmp_path)
    trends = root / "company_memory/financials/financial_trends.json"
    _w(trends, {"company": "acme", "metric_series": {"total_debt": [{"year": "fy21", "value": GOOD}]}, "generated_at": "later"})       # a different (even correct-looking) trends file
    assert check_artifact(root, "company_memory/financials/financial_trends.json")[0] == "tampered"
    for rel in ("company_memory/pcim_v1.json", "company_memory/cim_v1.json", "company_memory/investor_panel/graham_analysis.json"):
        assert check_artifact(root, rel)[0] == "stale", rel


def test_a_panel_analysis_depends_on_the_pcim_it_was_generated_from(tmp_path):
    base, root = _company(tmp_path)
    pcim = root / "company_memory/pcim_v1.json"
    payload = json.loads(pcim.read_text())
    payload["balance_sheet_strength_inputs"]["summary"] = "Balance sheet strength looks weak."
    from tests.authority_support import save_vouched
    save_vouched(pcim, payload)                                         # the PCIM is legitimately rebuilt and recorded again
    assert check_artifact(root, "company_memory/pcim_v1.json")[0] == "valid"
    assert check_artifact(root, "company_memory/investor_panel/graham_analysis.json")[0] == "stale"          # the analysis was written for the PCIM that no longer exists


def test_a_final_bind_does_not_vouch_for_an_artifact_that_was_built_from_other_inputs(tmp_path):
    base, root = _company(tmp_path)
    _w(root / "company_memory/financials/financial_trends.json", {"company": "acme", "metric_series": {}})       # inputs change after the CIM / PCIM were recorded
    bind_company(root, output_root=base)                                  # a later "bind everything" step
    assert check_artifact(root, "company_memory/pcim_v1.json")[0] == "stale"
    bind_company(root, output_root=base, rebind=True)                      # only an explicit rebind (after rebuilding them) re-records the dependants
    assert check_artifact(root, "company_memory/pcim_v1.json")[0] == "valid"
