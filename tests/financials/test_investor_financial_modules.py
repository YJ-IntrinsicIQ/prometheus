from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge.financials.investor_modules import build_investor_financial_modules


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    if path.name == "financial_fact_registry.json" and path.parent.name == "financials":
        year_root = path.parent.parent
        _write_json(year_root / "intelligence" / "company_intelligence.json", {"company": "acme", "year": year_root.name})
        _write_json(year_root / "intelligence" / "business_classification.json", {"company": "acme", "year": year_root.name})


def _registry_payload(year: str, *, include_order_book: bool = False) -> dict:
    def fact(
        metric_id: str,
        value,
        *,
        unit: str = "₹ crore",
        availability: str = "present_direct",
        derived: bool = False,
        source_artifact: str = "financial_fact_registry.json",
        notes=None,
    ) -> dict:
        return {
            "metric_id": metric_id,
            "metric_name": metric_id.replace("_", " "),
            "fiscal_year": year,
            "period": year.upper(),
            "value": value,
            "unit": unit,
            "basis": "consolidated",
            "source_statement": "synthetic",
            "source_artifact": source_artifact,
            "source_line_item": metric_id,
            "source_page": 1,
            "confidence": "high",
            "availability_status": availability,
            "derived": derived,
            "formula": "cfo + capex" if metric_id == "fcf" and derived else "",
            "inputs_used": ["cfo", "capex"] if metric_id == "fcf" and derived else [],
            "warnings": [],
            "reconciliation_status": "pass",
            "usable_downstream": True,
            "notes": notes or [],
        }

    direct = [
        fact("cfo", 30.0),
        fact("pat", 20.0),
        fact("capex", -8.0),
        fact("ppe_cwip_capex", -6.0),
        fact("intangible_capex", -2.0),
        fact("revenue", 120.0),
        fact("receivables", 18.0),
        fact("inventory", 15.0),
        fact("payables", 12.0),
        fact("receivable_days", 55.0, unit="days"),
        fact("inventory_days", 42.0, unit="days"),
        fact("payable_days", 36.0, unit="days"),
        fact("cash_conversion_cycle", 61.0, unit="days"),
        fact("revenue_growth", 15.0, unit="%"),
        fact("receivables_growth", 10.0, unit="%"),
        fact("inventory_growth", 9.0, unit="%"),
        fact("weighted_avg_shares", 10.0, unit="crore shares"),
        fact("closing_shares", 10.5, unit="crore shares"),
        fact("weighted_average_diluted_shares", 10.7, unit="crore shares"),
        fact("eps_basic", 20.0, unit="INR/share"),
        fact("eps_diluted", 18.5, unit="INR/share"),
        fact("book_value_per_share", 110.0, unit="INR/share"),
        fact("dividend_per_share", 4.0, unit="INR/share"),
        fact("roce", 18.0, unit="%"),
        fact("retained_earnings", 14.0),
        fact("working_capital_deployed", 5.0),
        fact("debt_repayment", 3.0),
        fact("unutilised_issue_proceeds", 0.0),
    ]
    if include_order_book:
        direct.append(fact("order_book", 200.0))
        direct.append(fact("order_inflow", 150.0))
    derived = [
        fact(
            "fcf",
            22.0,
            availability="present_derived",
            derived=True,
            notes=["Derived from CFO and capex."],
        )
    ]
    return {
        "company": "acme",
        "year": year,
        "generated_at": "2026-07-25T00:00:00Z",
        "source_artifacts_read": ["financial_fact_registry.json"],
        "registry_warnings": [],
        "available_facts": direct,
        "derived_facts": derived,
        "partial_facts": [],
        "missing_facts": [],
        "precise_missing_facts": [],
        "unreliable_facts": [],
        "invalid_facts": [],
        "quarantined_facts": [],
        "contradiction_summary": {},
        "downstream_readiness": {
            "financial_truth_status": "pass",
            "usable_metrics": [item["metric_id"] for item in direct + derived],
            "unreliable_metrics": [],
            "invalid_metrics": [],
            "quarantined_metrics": [],
            "missing_metrics": [],
            "downstream_blockers": [],
            "warnings": [],
        },
    }


def _reconciliation_payload() -> dict:
    return {
        "company": "acme",
        "generated_at": "2026-07-25T00:00:00Z",
        "contradictions_found": [],
        "resolved_contradictions": [],
        "unresolved_contradictions": [],
        "false_missing_warnings": [],
        "unreliable_metrics": [],
        "invalid_metrics": [],
        "usable_metrics": ["cfo", "capex", "fcf"],
        "downstream_blockers": [],
        "warning_normalizations": [],
        "invalid_artifact_findings": [],
        "quarantined_artifacts": [],
        "resolved_false_warnings": [],
        "warnings": [],
    }


def _quarantine_payload() -> dict:
    return {
        "company": "acme",
        "generated_at": "2026-07-25T00:00:00Z",
        "artifact_status_by_file": {},
        "quarantined_facts": [],
        "quarantined_artifacts": [],
        "usable_artifacts": [],
        "invalid_reason": [],
        "affected_metrics": [],
        "downstream_blockers": [],
        "recommended_reparse_targets": [],
        "warnings": [],
    }


def _corporate_actions_payload(action_type: str) -> dict:
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "actions": [
            {
                "action_type": action_type,
                "source_artifact": "corporate_actions.json",
            }
        ],
        "share_count_summary": {},
        "per_share_comparability_warnings": [],
        "warnings": [],
        "limitations": [],
    }


def test_build_investor_financial_modules_creates_expected_payloads(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    for year, include_order_book in (("fy24", False), ("fy25", True)):
        _write_json(company_root / year / "financials" / "financial_fact_registry.json", _registry_payload(year, include_order_book=include_order_book))
        _write_json(company_root / year / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
        _write_json(company_root / year / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())
    _write_json(company_root / "fy25" / "financials" / "corporate_actions.json", _corporate_actions_payload("qip_issue"))

    payloads = build_investor_financial_modules(company="acme", company_root=company_root)

    owner = payloads["owner_earnings_bridge.json"]
    capital = payloads["capital_allocation_roi_ledger.json"]
    working = payloads["working_capital_quality_drilldown.json"]
    order = payloads["order_revenue_cash_conversion_tracker.json"]
    per_share = payloads["per_share_compounding_analysis.json"]
    manifest = payloads["investor_financial_modules_manifest.json"]

    assert owner["bridges"][0]["conservative_fcf_after_total_capex"] == 22.0
    assert owner["bridges"][0]["owner_earnings_precision_status"] == "estimate_available"
    assert capital["entries"][0]["roi_measurability_status"] == "partially_measurable"
    assert working["drilldown"][0]["working_capital_intensity_status"] == "watch"
    assert order["tracker"][1]["conversion_status"] in {"strong", "watch", "stretched"}
    assert per_share["analysis"][1]["dilution_status"] == "dilution_warning"
    assert manifest["modules_run"] == [
        "owner_earnings_bridge",
        "capital_allocation_roi_ledger",
        "working_capital_quality_drilldown",
        "order_revenue_cash_conversion_tracker",
        "per_share_compounding_analysis",
    ]
    assert "owner_earnings_bridge" in manifest["module_statuses"]
    assert manifest["source_truth_pack_used"]["years_covered"] == ["fy24", "fy25"]


def test_per_share_compounding_converts_fcf_crore_to_inr_per_share_with_absolute_shares(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    payload = _registry_payload("fy25", include_order_book=False)
    for fact in payload["available_facts"]:
        if fact["metric_id"] == "weighted_avg_shares":
            fact["value"] = 9_800_000.0
            fact["unit"] = "shares"
            fact["raw_number"] = 9_800_000.0
        if fact["metric_id"] == "closing_shares":
            fact["value"] = 10_000_000.0
            fact["unit"] = "shares"
            fact["raw_number"] = 10_000_000.0
    for fact in payload["derived_facts"]:
        if fact["metric_id"] == "fcf":
            fact["value_crore"] = 22.0
            fact["unit"] = "₹ crore"
    _write_json(company_root / "fy25" / "financials" / "financial_fact_registry.json", payload)
    _write_json(company_root / "fy25" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy25" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())

    per_share = build_investor_financial_modules(company="acme", company_root=company_root)[
        "per_share_compounding_analysis.json"
    ]
    row = per_share["analysis"][0]

    assert row["fcf_per_share"] == pytest.approx(22.0 * 10_000_000 / 9_800_000.0)
    assert row["fcf_per_share_unit"] == "INR/share"
    assert row["fcf_per_share_numerator_unit"] == "INR crore"
    assert row["fcf_per_share_denominator_unit"] == "shares"
    assert row["fcf_per_share_calculation_formula"] == "fcf_value_crore * 10000000 / weighted_average_basic_shares"


def test_per_share_compounding_uses_closing_shares_with_precision_warning_when_weighted_average_missing(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    payload = _registry_payload("fy25", include_order_book=False)
    for fact in payload["available_facts"]:
        if fact["metric_id"] == "weighted_avg_shares":
            fact["value"] = None
            fact["raw_number"] = None
            fact["usable_downstream"] = False
        if fact["metric_id"] == "closing_shares":
            fact["value"] = 10_000_000.0
            fact["unit"] = "shares"
            fact["raw_number"] = 10_000_000.0
    for fact in payload["derived_facts"]:
        if fact["metric_id"] == "fcf":
            fact["value_crore"] = 22.0
            fact["unit"] = "₹ crore"
    _write_json(company_root / "fy25" / "financials" / "financial_fact_registry.json", payload)
    _write_json(company_root / "fy25" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy25" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())

    per_share = build_investor_financial_modules(company="acme", company_root=company_root)[
        "per_share_compounding_analysis.json"
    ]
    row = per_share["analysis"][0]

    assert row["fcf_per_share"] == pytest.approx(22.0)
    assert row["fcf_per_share_confidence"] == "medium"
    assert "weighted-average shares unavailable" in row["fcf_per_share_warning"].lower()


def test_per_share_compounding_preserves_direct_eps_and_dividend_with_reported_directly_metadata(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    payload = _registry_payload("fy25", include_order_book=False)
    _write_json(company_root / "fy25" / "financials" / "financial_fact_registry.json", payload)
    _write_json(company_root / "fy25" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy25" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())

    per_share = build_investor_financial_modules(company="acme", company_root=company_root)[
        "per_share_compounding_analysis.json"
    ]
    row = per_share["analysis"][0]
    metadata = row["per_share_metric_metadata"]

    assert row["eps_basic"] == 20.0
    assert metadata["eps_basic"]["calculation_formula"] == "reported_directly"
    assert metadata["eps_basic"]["source_unit"] == "INR/share"
    assert row["dividend_per_share"] == 4.0
    assert metadata["dividend_per_share"]["calculation_formula"] == "reported_directly"
    assert metadata["dividend_per_share"]["source_unit"] == "INR/share"


def test_per_share_compounding_skips_missing_alias_when_equivalent_share_fact_is_present(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    payload = _registry_payload("fy25", include_order_book=False)
    payload["available_facts"] = [
        fact
        for fact in payload["available_facts"]
        if fact["metric_id"] not in {"weighted_avg_shares", "weighted_average_diluted_shares"}
    ]
    missing_basic = {
        **payload["available_facts"][0],
        "metric_id": "weighted_avg_shares",
        "metric_name": "weighted avg shares",
        "value": None,
        "raw_number": None,
        "availability_status": "missing",
        "usable_downstream": False,
        "unit": "shares",
        "source_line_item": "",
    }
    missing_diluted = {
        **missing_basic,
        "metric_id": "weighted_average_diluted_shares",
        "metric_name": "weighted average diluted shares",
    }
    valid_basic_alias = {
        **payload["available_facts"][0],
        "metric_id": "weighted_average_basic_shares",
        "metric_name": "weighted average basic shares",
        "value": 9_800_000.0,
        "raw_number": 9_800_000.0,
        "unit": "shares",
        "source_line_item": "Weighted average number of shares used in computing basic and diluted earnings per share",
    }
    valid_diluted_alias = {
        **valid_basic_alias,
        "metric_id": "diluted_shares",
        "metric_name": "diluted shares",
    }
    payload["available_facts"].extend([valid_basic_alias, valid_diluted_alias])
    payload["missing_facts"].extend([missing_basic, missing_diluted])
    for fact in payload["derived_facts"]:
        if fact["metric_id"] == "fcf":
            fact["value_crore"] = 22.0
            fact["unit"] = "₹ crore"
    _write_json(company_root / "fy25" / "financials" / "financial_fact_registry.json", payload)
    _write_json(company_root / "fy25" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy25" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())

    per_share = build_investor_financial_modules(company="acme", company_root=company_root)[
        "per_share_compounding_analysis.json"
    ]
    row = per_share["analysis"][0]

    assert row["weighted_average_basic_shares"] == 9_800_000.0
    assert row["weighted_average_diluted_shares"] == 9_800_000.0
    assert row["fcf_per_share"] == pytest.approx(22.0 * 10_000_000 / 9_800_000.0)
    assert row["eps_basic"] == 20.0
    assert row["eps_diluted"] == 18.5


def test_per_share_compounding_builds_owner_earnings_per_share_when_owner_bridge_available(tmp_path: Path):
    company_root = tmp_path / "companies" / "acme"
    payload = _registry_payload("fy25", include_order_book=False)
    for fact in payload["available_facts"]:
        if fact["metric_id"] == "weighted_avg_shares":
            fact["value"] = 5_000_000.0
            fact["unit"] = "shares"
            fact["raw_number"] = 5_000_000.0
    _write_json(company_root / "fy25" / "financials" / "financial_fact_registry.json", payload)
    _write_json(company_root / "fy25" / "financials" / "financial_truth_reconciliation_report.json", _reconciliation_payload())
    _write_json(company_root / "fy25" / "financials" / "financial_artifact_quarantine_report.json", _quarantine_payload())

    modules = build_investor_financial_modules(company="acme", company_root=company_root)
    owner = modules["owner_earnings_bridge.json"]
    per_share = modules["per_share_compounding_analysis.json"]
    row = per_share["analysis"][0]
    owner_estimate = owner["bridges"][0]["owner_earnings_estimate"]

    assert row["owner_earnings_per_share"] == pytest.approx(owner_estimate * 10_000_000 / 5_000_000.0)
    assert row["per_share_metric_metadata"]["owner_earnings_per_share"]["numerator_metric"] == "owner_earnings_estimate"
    assert row["per_share_metric_metadata"]["owner_earnings_per_share"]["unit"] == "INR/share"
