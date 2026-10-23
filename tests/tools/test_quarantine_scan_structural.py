"""The propagation scan judges a point by its parent metric and year - at any depth, in any projection, for every rejected fact (no monetary cut-off) - and tells a rejected
figure used as evidence from the same figure recorded as an unusable diagnostic."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("quarantine_propagation_scan", ROOT / "tools" / "quarantine_propagation_scan.py")
Q = importlib.util.module_from_spec(spec)
sys.modules["quarantine_propagation_scan"] = Q
spec.loader.exec_module(Q)


def _w(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fact(metric, value, year, usable):
    return {"metric_id": metric, "fiscal_year": year, "value": value, "availability_status": "present_direct" if usable else "invalid", "usable_downstream": usable, "source_line_item": metric,
            "source_page": 1, "warnings": ["rejected"] if not usable else [], "derived": False}


def _company(tmp_path):
    root = tmp_path / "companies"
    co = root / "bank"
    registry = {"available_facts": [_fact("revenue", 2518.3148, "fy24", True), _fact("net_worth", 4000.0, "fy24", True)],
                "invalid_facts": [_fact("cash_and_equivalents", 2518.3148, "fy24", False), _fact("total_debt", 0.72, "fy24", False)], "derived_facts": [], "partial_facts": []}
    _w(co / "fy24/financials/financial_fact_registry.json", registry)
    return root, co


def test_a_rejected_value_in_a_nested_unflagged_series_is_a_leak_and_found_by_its_parent_metric(tmp_path):
    root, co = _company(tmp_path)
    _w(co / "company_memory/pcim_v1.json", {"balance_sheet_strength_inputs": {"metrics": [{"metric": "cash_and_equivalents", "series": [{"year": "fy23", "value": 2000.0}, {"year": "fy24", "value": 2518.3148}]}]}})
    _w(co / "company_memory/financials/financial_trends.json", {"metric_series": {"cash_and_equivalents": [{"year": "fy24", "value": 2518.3148}]}})
    result = Q.scan(root)
    assert result["rejected_figures"] == 2
    assert sorted(l["where"] for l in result["leaks"]) == ["/balance_sheet_strength_inputs/metrics/0/series/1", "/metric_series/cash_and_equivalents/0"]


def test_the_same_figure_marked_unusable_is_a_diagnostic_not_a_leak(tmp_path):
    root, co = _company(tmp_path)
    _w(co / "company_memory/financials/financial_trends.json", {"metric_series": {"cash_and_equivalents": [{"year": "fy24", "value": 2518.3148, "usable_downstream": False, "availability_status": "invalid"}]}})
    result = Q.scan(root)
    assert result["leaks"] == [] and result["flagged_diagnostics"] == 1


def test_a_legitimate_fact_that_shares_the_number_with_a_rejected_one_is_untouched(tmp_path):
    root, co = _company(tmp_path)
    _w(co / "company_memory/financials/financial_trends.json", {"metric_series": {"revenue": [{"year": "fy24", "value": 2518.3148}]}})
    assert Q.scan(root)["leaks"] == []


def test_values_below_one_crore_are_scanned_like_any_other(tmp_path):
    root, co = _company(tmp_path)
    _w(co / "company_memory/cim_v1.json", {"financial_intelligence": {"balance": [{"metric": "total_debt", "year": "fy24", "value": 0.72}]}})
    assert [l["metric"] for l in Q.scan(root)["leaks"]] == ["total_debt"]


def test_another_years_report_stating_the_same_number_for_a_different_year_is_a_comparative_for_review_not_a_leak(tmp_path):
    root, co = _company(tmp_path)
    _w(co / "company_memory/financials/financial_trends.json", {"metric_series": {"cash_and_equivalents": [{"year": "fy25", "value": 2518.3148}]}})
    result = Q.scan(root)
    assert result["leaks"] == [] and len(result["independent_comparatives"]) == 1


def test_a_later_years_comparative_column_stating_the_same_number_is_an_independent_source_not_a_leak(tmp_path):
    root, co = _company(tmp_path)
    _w(co / "fy25/financials/normalized_fundamentals.json", {"balance_sheet": {"cash_and_equivalents": {"value_crore": 3000.0, "period": "March 31, 2025",
                                                                                                         "comparatives": [{"period": "March 31, 2024", "value_crore": 2518.3148}]}}})
    result = Q.scan(root)
    assert result["leaks"] == [] and [c["artifact"] for c in result["independent_comparatives"]] == ["bank/fy25/financials/normalized_fundamentals.json"]
