from __future__ import annotations

import json
from pathlib import Path

from knowledge.financials.fact_registry import build_financial_fact_registry, write_financial_fact_registry


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _normalized_entry(field: str, *, value_crore=None, value_original="", basis="consolidated", confidence="high"):
    return {
        "canonical_field": field,
        "value_crore": value_crore,
        "value_original": value_original,
        "unit_original": "crores",
        "basis": basis,
        "period": "FY25",
        "source_line_item": field,
        "source_page": 10,
        "source_artifact": "annual_report.pdf",
        "confidence": confidence,
        "warnings": [],
        "source_section_type": "financial_note",
        "statement_type": "cash_flow" if field in {"cfo", "capex", "fcf"} else "balance_sheet",
        "source_value_type": "monetary",
    }


def _share_count_entry(field: str, raw_number: int, source_line_item: str):
    return {
        "canonical_field": field,
        "value_type": "share_count",
        "value_shares": raw_number,
        "raw_number": raw_number,
        "value_crore": None,
        "value_original": str(raw_number),
        "unit_original": "shares",
        "basis": "consolidated",
        "period": "FY25",
        "source_line_item": source_line_item,
        "source_page": 12,
        "source_artifact": "annual_report.pdf",
        "confidence": "high",
        "warnings": [],
        "statement_type": "share_data",
        "source_value_type": "share_count",
    }


def _per_share_entry(field: str, value_per_share: float):
    return {
        "canonical_field": field,
        "value_type": "per_share",
        "value_per_share": value_per_share,
        "value_crore": None,
        "value_original": str(value_per_share),
        "unit_original": "INR per share",
        "basis": "consolidated",
        "period": "FY25",
        "source_line_item": field,
        "source_page": 11,
        "source_artifact": "annual_report.pdf",
        "confidence": "high",
        "warnings": [],
        "statement_type": "profit_and_loss",
        "source_value_type": "per_share",
    }


def _normalized_payload(
    *,
    include_fcf=False,
    include_payables=False,
    include_total_debt=True,
    include_cash=True,
    include_weighted_avg=False,
    include_diluted_eps=False,
):
    payload = {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "preferred_basis": "consolidated",
        "profit_and_loss": {},
        "balance_sheet": {},
        "cash_flow": {
            "cfo": _normalized_entry("cfo", value_crore=20.0, value_original="20"),
            "capex": _normalized_entry("capex", value_crore=-8.0, value_original="-8"),
        },
        "share_data": {
            "shares_outstanding": _share_count_entry(
                "shares_outstanding", 1000000, "Issued, subscribed and fully paid up equity shares"
            ),
            "eps_basic": _per_share_entry("eps_basic", 12.5),
        },
        "shareholding_pattern": {},
        "warnings": [],
        "limitations": [],
        "unmapped_rows": [],
    }
    if include_total_debt:
        payload["balance_sheet"]["total_debt"] = _normalized_entry("total_debt", value_crore=30.0, value_original="30")
    if include_cash:
        payload["balance_sheet"]["cash_and_equivalents"] = _normalized_entry(
            "cash_and_equivalents", value_crore=6.0, value_original="6"
        )
    if include_fcf:
        payload["cash_flow"]["fcf"] = _normalized_entry("fcf", value_crore=12.0, value_original="12")
    if include_payables:
        payload["balance_sheet"]["payables"] = _normalized_entry("payables", value_crore=14.0, value_original="14")
    if include_weighted_avg:
        payload["share_data"]["weighted_avg_shares"] = _share_count_entry(
            "weighted_avg_shares", 990000, "Weighted average number of equity shares"
        )
    if include_diluted_eps:
        payload["share_data"]["eps_diluted"] = _per_share_entry("eps_diluted", 12.5)
    return payload


def _reconciliation_payload(*, total_debt_status="pass"):
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "status": "warning" if total_debt_status != "pass" else "pass",
        "checks": {
            "cfo": {"status": "pass", "reason": ""},
            "capex": {"status": "pass", "reason": ""},
            "shares_outstanding": {"status": "pass", "reason": ""},
            "total_debt": {"status": total_debt_status, "reason": "debt source failed reconciliation"},
        },
        "warnings": [],
        "hard_failures": [],
        "limitations": [],
    }


def _ratios_payload(*, include_roe=True, include_roce=True, include_payable_days=False):
    ratios = {}
    if include_roe:
        ratios["roe"] = {
            "ratio_name": "roe",
            "value": 15.0,
            "unit": "%",
            "formula": "pat / equity",
            "inputs_used": [{"name": "pat"}, {"name": "equity"}],
            "basis": "consolidated",
            "confidence": "high",
            "warnings": [],
        }
    if include_roce:
        ratios["roce"] = {
            "ratio_name": "roce",
            "value": 18.0,
            "unit": "%",
            "formula": "ebit / capital employed",
            "inputs_used": [{"name": "ebit"}, {"name": "capital employed"}],
            "basis": "consolidated",
            "confidence": "high",
            "warnings": [],
        }
    if include_payable_days:
        ratios["payable_days"] = {
            "ratio_name": "payable_days",
            "value": 47.0,
            "unit": "days",
            "formula": "average payables / com * 365",
            "inputs_used": [{"name": "payables"}],
            "basis": "consolidated",
            "confidence": "medium",
            "warnings": [],
        }
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "status": "pass",
        "basis_used": "consolidated",
        "warnings": [],
        "ratios": ratios,
        "limitations": [],
    }


def _growth_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "status": "pass",
        "growth_metrics": {},
        "margin_changes": {},
        "warnings": [],
        "limitations": [],
    }


def _raw_tables_payload(rows):
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "tables": {"cash_flow": rows},
        "warnings": [],
        "limitations": [],
    }


def _quality_payload(messages=None):
    return {
        "company": "acme",
        "generated_at": "2026-07-25T00:00:00Z",
        "years_covered": ["fy25"],
        "status": "warning",
        "overall_financial_quality": "mixed",
        "warnings": list(messages or []),
        "limitations": [],
        "missing_data": [],
        "red_flags": [],
        "positive_signals": [],
    }


def _corporate_actions_payload(actions):
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "status": "warning",
        "actions": actions,
        "warnings": [],
        "limitations": [],
    }


def _shareholding_payload(items):
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "status": "pass",
        "items": items,
        "warnings": [],
        "limitations": [],
    }


def test_fact_registry_derives_fcf_and_resolves_false_missing_warning(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())
    _write_json(financial_root / "financial_ratios.json", _ratios_payload())
    _write_json(financial_root / "financial_growth.json", _growth_payload())
    _write_json(financial_root / "financial_quality_summary.json", _quality_payload(["Free cash flow is missing."]))

    registry, report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert any(fact.metric_id == "fcf" and fact.derived and fact.value == 12.0 for fact in registry.derived_facts)
    assert any("fcf" in item.lower() for item in report.false_missing_warnings)
    assert registry.downstream_readiness["financial_truth_status"] == "warning"


def test_fact_registry_uses_payable_days_proxy_when_summary_claims_payables_missing(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())
    _write_json(financial_root / "financial_ratios.json", _ratios_payload(include_payable_days=True))
    _write_json(financial_root / "financial_quality_summary.json", _quality_payload(["Payables missing from current-year evidence."]))

    registry, report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert any(fact.metric_id == "payables" for fact in registry.derived_facts)
    assert any("payables" in item.lower() for item in report.false_missing_warnings)


def test_fact_registry_recognizes_present_roe_and_roce_against_summary_unavailable_claim(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())
    _write_json(financial_root / "financial_ratios.json", _ratios_payload())
    _write_json(financial_root / "financial_quality_summary.json", _quality_payload(["ROE unavailable.", "ROCE unavailable."]))

    registry, report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert "roe" in [fact.metric_id for fact in registry.derived_facts]
    assert "roce" in [fact.metric_id for fact in registry.derived_facts]
    assert any("roe" in item.lower() for item in report.false_missing_warnings)
    assert any("roce" in item.lower() for item in report.false_missing_warnings)


def test_fact_registry_preserves_missing_weighted_average_shares_without_false_direct_substitution(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())

    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    missing_metric_ids = [fact.metric_id for fact in registry.missing_facts]
    available_metric_ids = [fact.metric_id for fact in registry.available_facts]
    assert "shares_outstanding" in available_metric_ids
    assert "weighted_avg_shares" in missing_metric_ids


def test_fact_registry_quarantines_invalid_shareholding_percentages(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())
    _write_json(
        financial_root / "shareholding_pattern.json",
        _shareholding_payload(
            [
                {"holder_category": "promoter", "holding_percent": 120.0, "period": "FY25", "source_line_item": "Promoter", "source_page": 15, "confidence": "high", "warnings": []},
                {"holder_category": "public", "holding_percent": 10.0, "period": "FY25", "source_line_item": "Public", "source_page": 15, "confidence": "high", "warnings": []},
            ]
        ),
    )

    registry, report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert registry.downstream_readiness["financial_truth_status"] == "invalid"
    assert any(fact.metric_id.startswith("shareholding_") for fact in registry.invalid_facts)
    assert "shareholding_promoter_percent" in report.invalid_metrics


def test_fact_registry_shareholding_sum_check_uses_top_level_totals_not_subcategories(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())
    _write_json(
        financial_root / "shareholding_pattern.json",
        _shareholding_payload(
            [
                {"holder_category": "promoter_holding_percent", "holding_percent": 54.48, "shares_held": 1307134535.0, "period": "FY25", "source_line_item": "Promoters", "source_page": 15, "confidence": "high", "warnings": []},
                {"holder_category": "public_holding_percent", "holding_percent": 45.52, "shares_held": 1092200435.0, "period": "FY25", "source_line_item": "Total Public Shareholding", "source_page": 15, "confidence": "high", "warnings": []},
                {"holder_category": "retail_holding_percent", "holding_percent": 5.63, "shares_held": 135055794.0, "period": "FY25", "source_line_item": "Indian Public", "source_page": 15, "confidence": "high", "warnings": []},
                {"holder_category": "mutual_fund_holding_percent", "holding_percent": 12.21, "shares_held": 293051620.0, "period": "FY25", "source_line_item": "Mutual Funds", "source_page": 15, "confidence": "high", "warnings": []},
            ]
        ),
    )

    registry, report, quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert "shareholding_sum_check" not in report.invalid_metrics
    assert not any(fact.metric_id == "shareholding_sum_check" for fact in registry.invalid_facts)
    assert quarantine.artifact_status_by_file["shareholding_pattern.json"]["status"] == "usable"
    metric_values = {fact.metric_id: fact.value for fact in registry.available_facts if fact.metric_id.startswith("shareholding_")}
    assert metric_values["shareholding_public_holding_percent_percent"] == 45.52
    assert metric_values["shareholding_retail_holding_percent_percent"] == 5.63


def test_fact_registry_derives_two_fcf_variants_from_ppe_and_intangible_capex(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())
    _write_json(
        financial_root / "raw_financial_tables.json",
        _raw_tables_payload(
            [
                {
                    "statement_type": "cash_flow",
                    "table_type": "cash_flow",
                    "basis": "consolidated",
                    "line_item_raw": "Purchase of property, plant and equipment",
                    "values": [{"period": "FY25", "value_crore": -7.0}],
                    "page": 8,
                    "confidence": "high",
                    "warnings": [],
                },
                {
                    "statement_type": "cash_flow",
                    "table_type": "cash_flow",
                    "basis": "consolidated",
                    "line_item_raw": "Purchase of intangible assets",
                    "values": [{"period": "FY25", "value_crore": -2.0}],
                    "page": 8,
                    "confidence": "high",
                    "warnings": [],
                },
            ]
        ),
    )

    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    derived = {fact.metric_id: fact for fact in registry.derived_facts}
    assert derived["fcf_after_ppe_cwip_capex"].value == 13.0
    assert derived["fcf_after_total_identified_capex"].value == 12.0
    assert derived["total_capex_for_fcf"].value == -8.0


def test_fact_registry_marks_capex_split_partial_not_missing(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())
    _write_json(financial_root / "financial_quality_summary.json", _quality_payload(["Capex missing."]))

    registry, report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert any(fact.metric_id == "capex_classification_status" for fact in registry.partial_facts)
    assert any(item["affected_metric"] == "capex" for item in report.warning_normalizations)
    assert all(fact.metric_id != "capex" for fact in registry.missing_facts)


def test_fact_registry_derivable_fcf_normalizes_broad_missing_warning(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())
    _write_json(financial_root / "financial_quality_summary.json", _quality_payload(["FCF missing from the current evidence set."]))

    registry, report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert any(fact.metric_id == "fcf" and fact.availability_status == "present_derived" for fact in registry.derived_facts)
    assert any(item["normalized_warning"] == "FCF derived from CFO and capex; it is not explicitly disclosed." for item in report.warning_normalizations)


def test_fact_registry_derives_payable_days_from_turnover(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())
    ratios = _ratios_payload()
    ratios["ratios"]["payable_turnover"] = {
        "ratio_name": "payable_turnover",
        "value": 10.0,
        "unit": "x",
        "formula": "cost / payables",
        "inputs_used": [{"name": "payables"}],
        "basis": "consolidated",
        "confidence": "medium",
        "warnings": [],
    }
    _write_json(financial_root / "financial_ratios.json", ratios)
    _write_json(financial_root / "financial_quality_summary.json", _quality_payload(["Payables missing."]))

    registry, report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    derived = {fact.metric_id: fact for fact in registry.derived_facts}
    assert derived["payable_days"].value == 36.5
    assert any(item["affected_metric"] in {"payables", "payable_days"} for item in report.warning_normalizations)


def test_fact_registry_marks_debt_metrics_unreliable_after_reconciliation_failure(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload(total_debt_status="fail"))
    ratios = _ratios_payload()
    ratios["ratios"]["debt_to_equity"] = {
        "ratio_name": "debt_to_equity",
        "value": 0.6,
        "unit": "x",
        "formula": "debt / equity",
        "inputs_used": [{"name": "total_debt"}],
        "basis": "consolidated",
        "confidence": "high",
        "warnings": [],
    }
    _write_json(financial_root / "financial_ratios.json", ratios)
    _write_json(financial_root / "financial_quality_summary.json", _quality_payload(["Debt available."]))

    registry, report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    unreliable_ids = {fact.metric_id for fact in registry.unreliable_facts}
    assert "total_debt" in unreliable_ids
    assert "debt_to_equity" in unreliable_ids
    assert any(item["affected_metric"] == "total_debt" for item in report.warning_normalizations)


def test_fact_registry_tracks_precise_share_count_missing_status(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())
    _write_json(financial_root / "financial_quality_summary.json", _quality_payload(["Share count missing."]))

    registry, report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert any(fact.metric_id == "share_count_status" for fact in registry.partial_facts)
    assert any(fact.metric_id == "weighted_avg_shares" for fact in registry.precise_missing_facts)
    assert any(item["normalized_warning"] == "Closing shares exist; weighted-average shares may still be missing." for item in report.warning_normalizations)


def test_fact_registry_tracks_diluted_denominator_gap_without_marking_eps_missing(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(
        financial_root / "normalized_fundamentals.json",
        _normalized_payload(include_diluted_eps=True),
    )
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())

    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    precise_missing_ids = {fact.metric_id for fact in registry.precise_missing_facts}
    available_or_derived_ids = {fact.metric_id for fact in registry.available_facts + registry.derived_facts}
    assert "weighted_average_diluted_shares" in precise_missing_ids
    assert "eps_diluted" in available_or_derived_ids


def test_fact_registry_marks_per_share_status_partial_for_qip_without_invalidating_everything(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(
        financial_root / "normalized_fundamentals.json",
        _normalized_payload(include_weighted_avg=True),
    )
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())
    _write_json(
        financial_root / "corporate_actions.json",
        _corporate_actions_payload(
            [
                {
                    "action_type": "equity_raise",
                    "action_subtype": "qip_issue",
                    "status": "active",
                    "active": True,
                    "impact_on_share_count": "unknown",
                }
            ]
        ),
    )

    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    partial_ids = {fact.metric_id for fact in registry.partial_facts}
    invalid_ids = {fact.metric_id for fact in registry.invalid_facts}
    assert "eps_comparability_status" in partial_ids
    assert "dilution_status" in partial_ids
    assert "eps_comparability_status" not in invalid_ids


def test_fact_registry_present_direct_and_partial_beat_missing(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload(include_payables=True))
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())

    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    missing_ids = {fact.metric_id for fact in registry.missing_facts}
    available_ids = {fact.metric_id for fact in registry.available_facts}
    assert "payables" in available_ids
    assert "payables" not in missing_ids


def test_fact_registry_marks_reconciliation_failed_total_debt_as_unreliable_not_missing(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload(include_total_debt=True))
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload(total_debt_status="fail"))

    registry, report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert any(fact.metric_id == "total_debt" for fact in registry.unreliable_facts)
    assert "total_debt" in report.unreliable_metrics
    assert "total_debt" not in [fact.metric_id for fact in registry.missing_facts]
    assert registry.downstream_readiness["financial_truth_status"] == "partial"


def test_fact_registry_missing_artifacts_warn_but_do_not_crash(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())

    registry, report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert registry.registry_warnings
    assert report.warnings
    assert registry.company == "acme"


def test_write_financial_fact_registry_persists_both_artifacts(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", _reconciliation_payload())

    registry_path = financial_root / "financial_fact_registry.json"
    reconciliation_path = financial_root / "financial_truth_reconciliation_report.json"
    quarantine_path = financial_root / "financial_artifact_quarantine_report.json"
    write_financial_fact_registry(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        registry_output_path=registry_path,
        reconciliation_output_path=reconciliation_path,
        quarantine_output_path=quarantine_path,
    )

    assert registry_path.exists()
    assert reconciliation_path.exists()
    assert quarantine_path.exists()


def test_shareholding_artifact_with_all_invalid_percentages_becomes_quarantined(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(
        financial_root / "shareholding_pattern.json",
        _shareholding_payload(
            [
                {"holder_category": "promoter", "holding_percent": 1200000.0, "shares_held": 1200000.0, "period": "FY25", "source_line_item": "Promoter group", "source_page": 1, "confidence": "high", "warnings": []},
                {"holder_category": "public", "holding_percent": 800000.0, "shares_held": 800000.0, "period": "FY25", "source_line_item": "Public", "source_page": 1, "confidence": "high", "warnings": []},
            ]
        ),
    )

    registry, report, quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert quarantine.artifact_status_by_file["shareholding_pattern.json"]["status"] == "quarantined"
    assert quarantine.artifact_status_by_file["shareholding_pattern.json"]["usable_downstream"] is False
    assert registry.quarantined_facts
    assert report.quarantined_artifacts


def test_qip_monetary_amount_in_shares_issued_is_quarantined(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload(include_weighted_avg=True))
    _write_json(
        financial_root / "corporate_actions.json",
        _corporate_actions_payload(
            [
                {
                    "action_type": "qip",
                    "action_subtype": "qip_issue",
                    "source_line_item": "QIP issue proceeds",
                    "source_artifact": "corporate_actions.json",
                    "shares_issued": 250.25,
                    "value_type_used": "monetary",
                    "impact_on_share_count": "increase",
                    "impact_on_eps_comparability": "yes",
                    "confidence": "high",
                    "warnings": [],
                }
            ]
        ),
    )

    registry, report, quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert any("shares_issued" in item["invalid_fields"] for item in quarantine.quarantined_facts)
    assert any("corporate_action_qip" in fact.metric_id for fact in registry.quarantined_facts)
    assert report.invalid_artifact_findings


def test_qip_share_count_in_amount_crore_is_quarantined(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(
        financial_root / "corporate_actions.json",
        _corporate_actions_payload(
            [
                {
                    "action_type": "qip",
                    "action_subtype": "qip_issue",
                    "source_line_item": "Issue of shares through QIP",
                    "source_artifact": "corporate_actions.json",
                    "amount_crore": 4097319.0,
                    "value_type_used": "share_count",
                    "impact_on_share_count": "increase",
                    "impact_on_eps_comparability": "yes",
                    "confidence": "high",
                    "warnings": [],
                }
            ]
        ),
    )

    registry, _report, quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert any("amount_crore" in item["invalid_fields"] for item in quarantine.quarantined_facts)
    assert any(fact.metric_id.endswith("_amount_crore") for fact in registry.quarantined_facts)


def test_dividend_cash_outflow_not_treated_as_per_share_dividend(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(
        financial_root / "corporate_actions.json",
        _corporate_actions_payload(
            [
                {
                    "action_type": "dividend",
                    "source_line_item": "Dividend paid",
                    "source_artifact": "corporate_actions.json",
                    "amount_crore": -35.0,
                    "per_share_amount": -35.0,
                    "value_type_used": "monetary",
                    "impact_on_share_count": "none",
                    "impact_on_eps_comparability": "no",
                    "confidence": "high",
                    "warnings": [],
                }
            ]
        ),
    )

    _registry, _report, quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert any(item["domain"] == "per_share" for item in quarantine.quarantined_facts)


def test_unchanged_share_capital_is_not_treated_as_real_change(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload())
    _write_json(
        financial_root / "corporate_actions.json",
        _corporate_actions_payload(
            [
                {
                    "action_type": "share_capital_change",
                    "source_line_item": "Share capital",
                    "source_artifact": "corporate_actions.json",
                    "shares_before": 1000000.0,
                    "shares_after": 1000000.0,
                    "face_value_before": 10.0,
                    "face_value_after": 10.0,
                    "value_type_used": "share_count",
                    "impact_on_share_count": "none",
                    "impact_on_eps_comparability": "no",
                    "confidence": "medium",
                    "warnings": [],
                }
            ]
        ),
    )

    _registry, _report, quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    assert any("share_capital_change" in item["metric_id"] for item in quarantine.quarantined_facts)


def test_bonus_split_warns_comparability_without_economic_dilution(tmp_path):
    financial_root = tmp_path / "companies" / "acme" / "fy25" / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload(include_weighted_avg=True))
    _write_json(
        financial_root / "corporate_actions.json",
        _corporate_actions_payload(
            [
                {
                    "action_type": "bonus_issue",
                    "action_subtype": "bonus_issue",
                    "source_line_item": "Bonus issue 1:1",
                    "source_artifact": "corporate_actions.json",
                    "impact_on_share_count": "increase",
                    "impact_on_eps_comparability": "yes",
                    "confidence": "high",
                    "warnings": [],
                }
            ]
        ),
    )

    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    partial_ids = {fact.metric_id for fact in registry.partial_facts}
    assert "eps_comparability_status" in partial_ids
    assert "dilution_status" not in partial_ids


# ---------------------------------------------------------------------------
# FCF-derived ratio regression tests
# Requirement: fact_registry must derive fcf_to_pat and fcf_margin from
# canonical FCF when financial_ratios.json is stale or null.
# ---------------------------------------------------------------------------

def _normalized_payload_with_pl(
    *,
    cfo: float = 4959.33,
    capex: float = -2085.58,
    revenue: float = 43885.68,
    pat: float = 8473.58,
    capex_sign_convention: str = "cash_flow_signed",
):
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "preferred_basis": "consolidated",
        "profit_and_loss": {
            "revenue": dict(_normalized_entry("revenue", value_crore=revenue, value_original=str(revenue)), usable_downstream=True),
            "pat": dict(_normalized_entry("pat", value_crore=pat, value_original=str(pat)), usable_downstream=True),
        },
        "balance_sheet": {},
        "cash_flow": {
            "cfo": dict(_normalized_entry("cfo", value_crore=cfo, value_original=str(cfo)), usable_downstream=True),
            "capex": dict(
                _normalized_entry("capex", value_crore=capex, value_original=str(capex)),
                sign_convention=capex_sign_convention,
                usable_downstream=True,
            ),
        },
        "share_data": {
            "shares_outstanding": _share_count_entry("shares_outstanding", 1000000, "shares outstanding"),
        },
        "warnings": [],
        "limitations": [],
        "unmapped_rows": [],
    }


def _stale_ratios_payload():
    """Simulates a financial_ratios.json generated when capex was None → FCF null."""
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "basis_used": "consolidated",
        "ratios": {
            "fcf": {"value": None, "unit": "₹ crore", "formula": "cfo + capex", "inputs_used": [], "warnings": ["capex missing"], "basis": "consolidated", "confidence": "missing"},
            "fcf_to_pat": {"value": None, "unit": "x", "formula": "fcf / pat", "inputs_used": [{"name": "numerator"}, {"name": "denominator"}], "warnings": ["missing inputs"], "basis": "consolidated", "confidence": "low"},
            "fcf_margin": {"value": None, "unit": "%", "formula": "fcf / revenue * 100", "inputs_used": [{"name": "numerator"}, {"name": "denominator"}], "warnings": ["missing inputs"], "basis": "consolidated", "confidence": "low"},
        },
        "warnings": [],
        "limitations": [],
    }


def test_signed_negative_capex_produces_correct_fcf(tmp_path):
    """cfo=4959.33, capex=-2085.58 (cash_flow_signed) → FCF=2873.75"""
    financial_root = tmp_path / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload_with_pl())

    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    fcf_facts = [f for f in registry.derived_facts if f.metric_id == "fcf"]
    assert fcf_facts, "FCF must be in derived_facts"
    assert abs(fcf_facts[0].value - 2873.75) < 0.1
    assert fcf_facts[0].usable_downstream


def test_positive_outflow_capex_produces_correct_fcf(tmp_path):
    """cfo=100, capex=+30 (positive outflow) → FCF=70"""
    financial_root = tmp_path / "financials"
    payload = _normalized_payload_with_pl(cfo=100.0, capex=30.0, capex_sign_convention="positive_outflow")
    _write_json(financial_root / "normalized_fundamentals.json", payload)

    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    fcf_facts = [f for f in registry.derived_facts if f.metric_id == "fcf"]
    assert fcf_facts, "FCF must be derived"
    assert abs(fcf_facts[0].value - 70.0) < 0.1


def test_fcf_to_pat_derived_when_ratios_stale(tmp_path):
    """When financial_ratios.json shows fcf_to_pat=null, fact_registry derives it from canonical FCF + PAT."""
    financial_root = tmp_path / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload_with_pl())
    _write_json(financial_root / "financial_ratios.json", _stale_ratios_payload())

    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    all_facts = registry.derived_facts + registry.available_facts
    fcf_to_pat_facts = [f for f in all_facts if f.metric_id == "fcf_to_pat" and f.value is not None]
    assert fcf_to_pat_facts, "fcf_to_pat must be derived when stale ratios show null"
    expected = round(2873.75 / 8473.58, 4)
    assert abs(fcf_to_pat_facts[0].value - expected) < 0.01
    assert fcf_to_pat_facts[0].usable_downstream


def test_fcf_margin_derived_when_ratios_stale(tmp_path):
    """When financial_ratios.json shows fcf_margin=null, fact_registry derives it from canonical FCF + revenue."""
    financial_root = tmp_path / "financials"
    _write_json(financial_root / "normalized_fundamentals.json", _normalized_payload_with_pl())
    _write_json(financial_root / "financial_ratios.json", _stale_ratios_payload())

    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    all_facts = registry.derived_facts + registry.available_facts
    fcf_margin_facts = [f for f in all_facts if f.metric_id == "fcf_margin" and f.value is not None]
    assert fcf_margin_facts, "fcf_margin must be derived when stale ratios show null"
    expected = round(2873.75 / 43885.68 * 100, 4)
    assert abs(fcf_margin_facts[0].value - expected) < 0.1
    assert fcf_margin_facts[0].usable_downstream


def test_genuinely_missing_cfo_leaves_fcf_ratios_unavailable(tmp_path):
    """When CFO is absent, FCF cannot be derived and fcf_to_pat/fcf_margin must stay missing."""
    financial_root = tmp_path / "financials"
    payload = {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-25T00:00:00Z",
        "preferred_basis": "consolidated",
        "profit_and_loss": {
            "revenue": dict(_normalized_entry("revenue", value_crore=43885.68), usable_downstream=True),
            "pat": dict(_normalized_entry("pat", value_crore=8473.58), usable_downstream=True),
        },
        "balance_sheet": {},
        "cash_flow": {},
        "share_data": {"shares_outstanding": _share_count_entry("shares_outstanding", 1000000, "shares")},
        "warnings": [],
        "limitations": [],
        "unmapped_rows": [],
    }
    _write_json(financial_root / "normalized_fundamentals.json", payload)

    registry, _report, _quarantine = build_financial_fact_registry(company="acme", year="fy25", financial_root=financial_root)

    all_ids_with_value = {f.metric_id for f in registry.derived_facts + registry.available_facts if f.value is not None}
    assert "fcf" not in all_ids_with_value, "FCF must not be present when CFO is missing"
    assert "fcf_to_pat" not in all_ids_with_value
    assert "fcf_margin" not in all_ids_with_value


def test_no_company_year_hardcoding_in_fact_registry_fcf():
    """fact_registry.py must not reference Sun Pharma or FY23 for the FCF fix."""
    text = Path("knowledge/financials/fact_registry.py").read_text(encoding="utf-8").lower()
    assert "sun_pharma" not in text
    assert "sun pharma" not in text
    assert "fy23" not in text
