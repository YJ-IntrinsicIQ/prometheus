from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from knowledge.financials.quality_summary import (
    build_financial_quality_summary,
    write_financial_quality_summary,
)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _money(value, *, source_line_item="synthetic row", value_type="monetary", unit_original="₹ crore"):
    return {
        "canonical_field": source_line_item,
        "value_type": value_type,
        "value_crore": value if value_type == "monetary" else None,
        "value_per_share": value if value_type == "per_share" else None,
        "raw_number": value if value_type == "share_count" else None,
        "unit_original": unit_original,
        "basis": "consolidated",
        "period": "fy25",
        "source_line_item": source_line_item,
        "source_page": 12,
        "source_artifact": "normalized_fundamentals.json",
        "confidence": "high",
        "warnings": [],
    }


def _base_normalized_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "basis_used": "consolidated",
        "profit_and_loss": {
            "revenue": _money(120.0, source_line_item="Revenue"),
            "pat": _money(18.0, source_line_item="Profit after tax"),
        },
        "cash_flow": {
            "cfo": _money(14.0, source_line_item="Net cash from operating activities"),
            "capex": _money(-6.0, source_line_item="Purchase of PPE"),
            "dividends_paid": _money(-2.0, source_line_item="Dividend paid"),
        },
        "balance_sheet": {
            "total_debt": _money(12.0, source_line_item="Borrowings"),
            "cash_and_equivalents": _money(20.0, source_line_item="Cash and cash equivalents"),
        },
        "share_data": {
            "shares_outstanding": _money(10_000_000.0, source_line_item="Number of shares outstanding", value_type="share_count", unit_original="shares"),
            "weighted_avg_shares": _money(9_800_000.0, source_line_item="Weighted average shares", value_type="share_count", unit_original="shares"),
        },
    }


def _base_reconciliation_payload():
    def _check(field_name, status="pass", hard_failure=False):
        return {
            "field_name": field_name,
            "status": status,
            "hard_failure": hard_failure,
            "reason": "",
            "source_line_item": field_name,
            "source_section_type": "financial_statement",
            "statement_type": "synthetic",
            "basis": "consolidated",
            "source_artifacts": ["normalized_fundamentals.json"],
            "warnings": [],
        }

    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-18T00:00:00Z",
        "status": "pass",
        "checks": {
            "total_debt": _check("total_debt"),
            "net_worth": _check("net_worth"),
            "receivables": _check("receivables"),
            "payables": _check("payables"),
            "shares_outstanding": _check("shares_outstanding"),
        },
        "hard_failures": [],
        "warnings": [],
        "limitations": [],
    }


def _base_validation_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-18T00:00:00Z",
        "status": "pass",
        "basis_checked": "consolidated",
        "hard_failures": [],
        "warnings": [],
        "checks": [],
        "missing_fields": [],
        "suspicious_values": [],
        "limitations": [],
    }


def _ratio_item(name, value, unit, warnings=None):
    return {
        "ratio_name": name,
        "value": value,
        "unit": unit,
        "formula": "synthetic",
        "inputs_used": [],
        "basis": "consolidated",
        "confidence": "high" if value is not None else "missing",
        "warnings": list(warnings or []),
        "source_artifacts": ["financial_ratios.json"],
    }


def _base_ratio_payload():
    fields = {
        "gross_margin": (35.0, "%"),
        "ebitda_margin": (22.0, "%"),
        "ebit_margin": (18.0, "%"),
        "opm": (18.0, "%"),
        "npm": (15.0, "%"),
        "roe": (17.0, "%"),
        "roce": (21.0, "%"),
        "roa": (9.0, "%"),
        "debt_to_equity": (0.35, "x"),
        "net_debt": (-8.0, "₹ crore"),
        "net_debt_to_equity": (-0.2, "x"),
        "interest_coverage": (8.0, "x"),
        "cfo_to_pat": (0.9, "x"),
        "fcf": (8.0, "₹ crore"),
        "fcf_to_pat": (0.44, "x"),
        "fcf_margin": (6.7, "%"),
        "receivable_days": (52.0, "days"),
        "inventory_days": (24.0, "days"),
        "payable_days": (30.0, "days"),
        "cash_conversion_cycle": (46.0, "days"),
        "eps_basic": (12.5, "per share"),
        "eps_diluted": (12.0, "per share"),
        "book_value_per_share": (48.0, "per share"),
        "tangible_book_value_per_share": (47.0, "per share"),
        "dividend_per_share": (2.0, "per share"),
        "payout_ratio": (16.0, "%"),
    }
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-18T00:00:00Z",
        "status": "pass",
        "basis_used": "consolidated",
        "basis_confidence": "high",
        "basis_warnings": [],
        "warnings": [],
        "limitations": [],
        "ratios": {name: _ratio_item(name, value, unit) for name, (value, unit) in fields.items()},
    }


def _growth_item(metric, current_value, previous_value, growth_percent, absolute_change, unit="₹ crore"):
    return {
        "metric": metric,
        "current_year": "fy25",
        "previous_year": "fy24",
        "current_value": current_value,
        "previous_value": previous_value,
        "absolute_change": absolute_change,
        "growth_percent": growth_percent,
        "cagr_percent": growth_percent,
        "unit": unit,
        "basis": "consolidated",
        "confidence": "high" if growth_percent is not None else "missing",
        "warnings": [],
    }


def _base_growth_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-18T00:00:00Z",
        "status": "pass",
        "basis_used": "consolidated",
        "basis_confidence": "high",
        "years_available": ["fy24", "fy25"],
        "basis_warnings": [],
        "warnings": [],
        "limitations": [],
        "growth_metrics": {
            "revenue": _growth_item("revenue", 120.0, 100.0, 20.0, 20.0),
            "ebitda": _growth_item("ebitda", 26.0, 20.0, 30.0, 6.0),
            "ebit": _growth_item("ebit", 22.0, 18.0, 22.2, 4.0),
            "pat": _growth_item("pat", 18.0, 12.0, 50.0, 6.0),
            "eps_basic": _growth_item("eps_basic", 12.5, 10.0, 25.0, 2.5, unit="per share"),
            "eps_diluted": _growth_item("eps_diluted", 12.0, 9.8, 22.4, 2.2, unit="per share"),
            "book_value_per_share": _growth_item("book_value_per_share", 48.0, 42.0, 14.3, 6.0, unit="per share"),
            "net_worth": _growth_item("net_worth", 80.0, 68.0, 17.6, 12.0),
            "reserves": _growth_item("reserves", 62.0, 52.0, 19.2, 10.0),
            "total_debt": _growth_item("total_debt", 12.0, 10.0, 20.0, 2.0),
            "cfo": _growth_item("cfo", 14.0, 13.0, 7.7, 1.0),
            "fcf": _growth_item("fcf", 8.0, 6.0, 33.3, 2.0),
            "capex": _growth_item("capex", -6.0, -7.0, -14.3, 1.0),
            "receivables": _growth_item("receivables", 24.0, 20.0, 20.0, 4.0),
            "inventory": _growth_item("inventory", 12.0, 10.5, 14.3, 1.5),
            "payables": _growth_item("payables", 16.0, 14.0, 14.3, 2.0),
        },
        "margin_changes": {
            "gross_margin": _growth_item("gross_margin", 35.0, 33.0, None, 2.0, unit="pp"),
            "ebitda_margin": _growth_item("ebitda_margin", 22.0, 19.0, None, 3.0, unit="pp"),
            "ebit_margin": _growth_item("ebit_margin", 18.0, 16.0, None, 2.0, unit="pp"),
            "opm": _growth_item("opm", 18.0, 15.0, None, 3.0, unit="pp"),
            "npm": _growth_item("npm", 15.0, 12.0, None, 3.0, unit="pp"),
        },
    }


def _base_corporate_actions_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-18T00:00:00Z",
        "status": "pass",
        "actions": [
            {
                "action_type": "dividend",
                "year": "fy25",
                "ratio": "",
                "impact_on_share_count": "none",
                "impact_on_eps_comparability": "no",
                "source_line_item": "Dividend declared",
                "source_artifact": "corporate_actions.json",
                "confidence": "high",
                "warnings": [],
            }
        ],
        "share_count_summary": {
            "opening_shares": 9_500_000.0,
            "closing_shares": 10_000_000.0,
            "weighted_avg_shares": 9_800_000.0,
            "diluted_shares": 10_100_000.0,
            "face_value": 2.0,
            "share_count_events": [],
        },
        "rejection_reasons": [],
        "per_share_comparability_warnings": [],
        "warnings": [],
        "limitations": [],
    }


def _base_shareholding_payload():
    return {
        "company": "acme",
        "year": "fy25",
        "generated_at": "2026-07-18T00:00:00Z",
        "status": "pass",
        "items": [
            {
                "holder_category": "promoter_holding_percent",
                "period": "fy25",
                "holding_percent": 54.0,
                "shares_held": None,
                "change_percent": 1.0,
                "source_line_item": "Promoter",
                "source_page": 80,
                "source_artifact": "shareholding_pattern.json",
                "confidence": "high",
                "warnings": [],
            },
            {
                "holder_category": "institutional_holding_percent",
                "period": "fy25",
                "holding_percent": 18.0,
                "shares_held": None,
                "change_percent": 2.0,
                "source_line_item": "Institutional",
                "source_page": 80,
                "source_artifact": "shareholding_pattern.json",
                "confidence": "high",
                "warnings": [],
            },
        ],
        "ownership_summary": {
            "promoter_control": "Promoter holding recorded at 54.0%.",
            "institutional_interest": "Institutional ownership recorded at 18.0%.",
            "pledge_risk": "Promoter pledge data unavailable.",
            "public_float": "Public holding available.",
            "notable_changes": [],
        },
        "searched_sections": ["shareholding_pattern"],
        "rejection_reasons": [],
        "warnings": [],
        "limitations": [],
    }


def _write_year_inputs(financial_root: Path, *, normalized=None, reconciliation=None, validation=None, ratios=None, growth=None, corporate_actions=None, shareholding=None):
    _write_json(financial_root / "normalized_fundamentals.json", normalized or _base_normalized_payload())
    _write_json(financial_root / "financial_reconciliation_report.json", reconciliation or _base_reconciliation_payload())
    _write_json(financial_root / "financial_validation_report.json", validation or _base_validation_payload())
    _write_json(financial_root / "financial_ratios.json", ratios or _base_ratio_payload())
    _write_json(financial_root / "financial_growth.json", growth or _base_growth_payload())
    _write_json(financial_root / "corporate_actions.json", corporate_actions or _base_corporate_actions_payload())
    if shareholding is not False:
        _write_json(financial_root / "shareholding_pattern.json", shareholding or _base_shareholding_payload())


def test_year_financial_quality_flags_strong_growth(tmp_path: Path):
    financial_root = tmp_path / "financials"
    _write_year_inputs(financial_root)

    report = build_financial_quality_summary(company="acme", year="fy25", financial_root=financial_root)

    assert report.sections["growth_quality"].assessment == "strong"
    assert any("Revenue, PAT, and per-share growth" in item for item in report.sections["growth_quality"].highlights)


def test_year_financial_quality_warns_on_weak_cash_conversion(tmp_path: Path):
    financial_root = tmp_path / "financials"
    ratios = _base_ratio_payload()
    ratios["ratios"]["cfo_to_pat"]["value"] = 0.5
    _write_year_inputs(financial_root, ratios=ratios)

    report = build_financial_quality_summary(company="acme", year="fy25", financial_root=financial_root)

    assert report.sections["cash_conversion_quality"].assessment == "weak"
    assert any("weak relative to PAT" in item for item in report.sections["cash_conversion_quality"].warnings)


def test_year_financial_quality_adds_red_flag_for_negative_cfo_with_positive_pat(tmp_path: Path):
    financial_root = tmp_path / "financials"
    normalized = _base_normalized_payload()
    normalized["cash_flow"]["cfo"]["value_crore"] = -3.0
    _write_year_inputs(financial_root, normalized=normalized)

    report = build_financial_quality_summary(company="acme", year="fy25", financial_root=financial_root)

    assert "PAT is positive while CFO is negative." in report.sections["red_flags"]


def test_year_financial_quality_detects_net_cash_balance_sheet(tmp_path: Path):
    financial_root = tmp_path / "financials"
    _write_year_inputs(financial_root)

    report = build_financial_quality_summary(company="acme", year="fy25", financial_root=financial_root)

    assert report.sections["balance_sheet_strength"].assessment == "net_cash"


def test_year_financial_quality_treats_missing_capex_as_missing_data_not_red_flag(tmp_path: Path):
    financial_root = tmp_path / "financials"
    normalized = _base_normalized_payload()
    normalized["cash_flow"]["capex"]["value_crore"] = None
    ratios = _base_ratio_payload()
    ratios["ratios"]["fcf"]["value"] = None
    ratios["ratios"]["fcf_to_pat"]["value"] = None
    ratios["ratios"]["fcf_margin"]["value"] = None
    _write_year_inputs(financial_root, normalized=normalized, ratios=ratios)

    report = build_financial_quality_summary(company="acme", year="fy25", financial_root=financial_root)

    assert "FCF unavailable because capex is missing" in report.sections["missing_data"]
    assert not any("capex" in item.lower() for item in report.sections["red_flags"])


def test_year_financial_quality_marks_missing_share_count_as_per_share_limitation(tmp_path: Path):
    financial_root = tmp_path / "financials"
    normalized = _base_normalized_payload()
    normalized["share_data"]["shares_outstanding"]["raw_number"] = None
    normalized["share_data"]["weighted_avg_shares"]["raw_number"] = None
    _write_year_inputs(financial_root, normalized=normalized)

    report = build_financial_quality_summary(company="acme", year="fy25", financial_root=financial_root)

    assert any("share count" in item.lower() for item in report.sections["per_share_quality"].limitations)


def test_write_year_financial_quality_summary_persists_valid_payload(tmp_path: Path):
    financial_root = tmp_path / "financials"
    output_path = financial_root / "financial_quality_summary.json"
    _write_year_inputs(financial_root)

    report = write_financial_quality_summary(
        company="acme",
        year="fy25",
        financial_root=financial_root,
        output_path=output_path,
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["company"] == "acme"
    assert saved["year"] == "fy25"
    assert saved["sections"]["growth_quality"]["assessment"] == report.sections["growth_quality"].assessment


def test_legacy_company_memory_financial_quality_summary_still_works(tmp_path: Path):
    trends_path = tmp_path / "financial_trends.json"
    _write_json(
        trends_path,
        {
            "company": "acme",
            "generated_at": "2026-07-18T00:00:00Z",
            "years_covered": ["fy24", "fy25"],
            "basis": "consolidated",
            "metric_trends": {
                "revenue": {"series": [{"year": "fy24", "value": 100.0}, {"year": "fy25", "value": 120.0}]},
                "pat": {"series": [{"year": "fy24", "value": 10.0}, {"year": "fy25", "value": 15.0}]},
            },
            "growth_summary": {
                "revenue": [{"growth_percent": 20.0}],
                "pat": [{"growth_percent": 50.0}],
                "eps_basic": [{"growth_percent": 25.0}],
                "book_value_per_share": [{"growth_percent": 10.0}],
            },
            "margin_trends": {
                "opm": {"series": [{"year": "fy24", "value": 12.0}, {"year": "fy25", "value": 14.0}]},
                "ebitda_margin": {"series": [{"year": "fy24", "value": 18.0}, {"year": "fy25", "value": 20.0}]},
                "npm": {"series": [{"year": "fy24", "value": 9.0}, {"year": "fy25", "value": 11.0}]},
            },
            "return_trends": {
                "roe": {"series": [{"year": "fy24", "value": 10.0}, {"year": "fy25", "value": 14.0}]},
                "roce": {"series": [{"year": "fy24", "value": 12.0}, {"year": "fy25", "value": 16.0}]},
                "roa": {"series": [{"year": "fy24", "value": 5.0}, {"year": "fy25", "value": 7.0}]},
            },
            "cash_conversion_trends": {
                "cfo_to_pat": {"series": [{"year": "fy24", "value": 90.0}, {"year": "fy25", "value": 105.0}]},
                "fcf_to_pat": {"series": [{"year": "fy24", "value": 20.0}, {"year": "fy25", "value": 30.0}]},
                "fcf": {"series": [{"year": "fy24", "value": 2.0}, {"year": "fy25", "value": 4.0}]},
                "capex": {"series": [{"year": "fy24", "value": 5.0}, {"year": "fy25", "value": 6.0}]},
                "receivables": {"series": [{"year": "fy24", "value": 18.0}, {"year": "fy25", "value": 20.0}]},
                "inventory": {"series": [{"year": "fy24", "value": 9.0}, {"year": "fy25", "value": 10.0}]},
                "cash_conversion_cycle": {"series": [{"year": "fy24", "value": 42.0}, {"year": "fy25", "value": 39.0}]},
                "receivable_days": {"series": [{"year": "fy24", "value": 52.0}, {"year": "fy25", "value": 48.0}]},
            },
            "balance_sheet_trends": {
                "total_debt": {"series": [{"year": "fy24", "value": 20.0}, {"year": "fy25", "value": 16.0}]},
                "debt_to_equity": {"series": [{"year": "fy24", "value": 45.0}, {"year": "fy25", "value": 35.0}]},
                "net_debt": {"series": [{"year": "fy24", "value": 5.0}, {"year": "fy25", "value": -3.0}]},
                "cash_and_equivalents": {"series": [{"year": "fy24", "value": 12.0}, {"year": "fy25", "value": 18.0}]},
                "reserves": {"series": [{"year": "fy24", "value": 25.0}, {"year": "fy25", "value": 30.0}]},
            },
            "per_share_trends": {
                "share_count": {"series": [{"year": "fy24", "value": 100.0}, {"year": "fy25", "value": 100.0}]},
                "dividend_per_share": {"series": [{"year": "fy24", "value": 1.0}, {"year": "fy25", "value": 1.2}]},
            },
            "ownership_trends": {
                "promoter_holding": {"series": [{"year": "fy24", "value": 52.0}, {"year": "fy25", "value": 53.0}]},
                "pledged_promoter_holding": {"series": [{"year": "fy24", "value": 0.0}, {"year": "fy25", "value": 0.0}]},
                "fii_holding": {"series": [{"year": "fy24", "value": 8.0}, {"year": "fy25", "value": 10.0}]},
                "public_holding": {"series": [{"year": "fy24", "value": 28.0}, {"year": "fy25", "value": 26.0}]},
            },
            "corporate_actions_timeline": [],
            "warnings": [],
            "limitations": [],
        },
    )

    report = build_financial_quality_summary(company="acme", trends_path=trends_path)

    assert report.company == "acme"
    assert report.overall_financial_quality in {"strong", "adequate", "mixed"}


# ---------------------------------------------------------------------------
# Regression tests — blocked_downstream warning injection bug
# ---------------------------------------------------------------------------

_MINIMAL_TRENDS = {
    "company": "testco",
    "generated_at": "2026-08-01T00:00:00Z",
    "years_covered": ["fy24", "fy25"],
    "basis": "consolidated",
    "metric_trends": {
        "revenue": {"series": [{"year": "fy24", "value": 100.0}, {"year": "fy25", "value": 120.0}]},
        "pat": {"series": [{"year": "fy24", "value": 10.0}, {"year": "fy25", "value": 14.0}]},
    },
    "growth_summary": {
        "revenue": [{"growth_percent": 20.0}],
        "pat": [{"growth_percent": 40.0}],
        "eps_basic": [{"growth_percent": 20.0}],
        "book_value_per_share": [{"growth_percent": 10.0}],
    },
    "margin_trends": {
        "opm": {"series": [{"year": "fy24", "value": 10.0}, {"year": "fy25", "value": 12.0}]},
        "npm": {"series": [{"year": "fy24", "value": 8.0}, {"year": "fy25", "value": 9.0}]},
    },
    "return_trends": {},
    "cash_conversion_trends": {},
    "balance_sheet_trends": {
        "reserves": {"series": [{"year": "fy24", "value": 50.0}, {"year": "fy25", "value": 60.0}]},
    },
    "per_share_trends": {},
    "ownership_trends": {},
    "corporate_actions_timeline": [],
    "warnings": [],
    "limitations": [],
}

_EMPTY_TRUTH_PACK: dict = {
    "usable_current_metrics": [],
    "usable_derived_metrics": [],
    "precise_missing_metrics": [],
    "unreliable_metrics": [],
    "invalid_or_quarantined_metrics": [],
    "financial_warnings_blocked_downstream": [],
    "financial_warnings_allowed_downstream": [],
    "financial_warnings_rewritten": [],
}

_PATCH_TRUTH = "knowledge.financials.quality_summary.build_financial_truth_pack"
_PATCH_MANIFEST = "knowledge.financials.quality_summary.build_financial_memory_manifest"


def _run_legacy_with_truth_pack(tmp_path: Path, trends: dict, truth_pack: dict) -> object:
    trends_path = tmp_path / "company_memory" / "financials" / "financial_trends.json"
    trends_path.parent.mkdir(parents=True, exist_ok=True)
    trends_path.write_text(json.dumps(trends), encoding="utf-8")
    with patch(_PATCH_TRUTH, return_value=truth_pack), \
         patch(_PATCH_MANIFEST, return_value={}):
        return build_financial_quality_summary(company="testco", trends_path=trends_path)


def test_blocked_downstream_warning_absent_from_trends_is_not_injected(tmp_path: Path):
    truth_pack = dict(_EMPTY_TRUTH_PACK)
    truth_pack["financial_warnings_blocked_downstream"] = [
        {
            "original_warning": "cfo: previous-year data missing",
            "normalized_warning": "cfo: previous-year data missing",
            "affected_metric": "cfo",
            "resolution_status": "resolved",
        }
    ]
    report = _run_legacy_with_truth_pack(tmp_path, _MINIMAL_TRENDS, truth_pack)

    assert "cfo: previous-year data missing" not in report.warnings


def test_blocked_downstream_warning_present_and_same_normalized_is_removed(tmp_path: Path):
    trends = dict(_MINIMAL_TRENDS)
    trends["warnings"] = ["cfo: previous-year data missing"]
    truth_pack = dict(_EMPTY_TRUTH_PACK)
    truth_pack["financial_warnings_blocked_downstream"] = [
        {
            "original_warning": "cfo: previous-year data missing",
            "normalized_warning": "cfo: previous-year data missing",
            "affected_metric": "cfo",
            "resolution_status": "resolved",
        }
    ]
    report = _run_legacy_with_truth_pack(tmp_path, trends, truth_pack)

    assert "cfo: previous-year data missing" not in report.warnings


def test_blocked_downstream_warning_replaced_with_distinct_normalized_form(tmp_path: Path):
    trends = dict(_MINIMAL_TRENDS)
    trends["warnings"] = ["fcf: previous-year data missing"]
    truth_pack = dict(_EMPTY_TRUTH_PACK)
    truth_pack["financial_warnings_blocked_downstream"] = [
        {
            "original_warning": "fcf: previous-year data missing",
            "normalized_warning": "FCF derived, not explicitly disclosed.",
            "affected_metric": "fcf",
            "resolution_status": "resolved",
        }
    ]
    report = _run_legacy_with_truth_pack(tmp_path, trends, truth_pack)

    assert "fcf: previous-year data missing" not in report.warnings
    assert "FCF derived, not explicitly disclosed." in report.warnings


def test_blocked_downstream_100_stale_entries_add_zero_spurious_warnings(tmp_path: Path):
    stale_metrics = [
        "cfo", "npm", "reserves", "receivables", "gross_margin",
        "ebitda", "ebit", "capex", "payables", "inventory",
    ]
    blocked = []
    for metric in stale_metrics:
        for suffix in ["previous-year data missing", "5-year base data missing", "missing reconciliation check"]:
            blocked.append({
                "original_warning": f"{metric}: {suffix}",
                "normalized_warning": f"{metric}: {suffix}",
                "affected_metric": metric,
                "resolution_status": "resolved",
            })
    truth_pack = dict(_EMPTY_TRUTH_PACK)
    truth_pack["financial_warnings_blocked_downstream"] = blocked
    report = _run_legacy_with_truth_pack(tmp_path, _MINIMAL_TRENDS, truth_pack)

    for blocked_entry in blocked:
        assert blocked_entry["normalized_warning"] not in report.warnings, (
            f"Stale warning injected spuriously: {blocked_entry['normalized_warning']!r}"
        )


def test_blocked_downstream_only_matched_entries_are_replaced(tmp_path: Path):
    trends = dict(_MINIMAL_TRENDS)
    trends["warnings"] = ["reserves: previous-year data missing"]
    truth_pack = dict(_EMPTY_TRUTH_PACK)
    truth_pack["financial_warnings_blocked_downstream"] = [
        {
            "original_warning": "reserves: previous-year data missing",
            "normalized_warning": "reserves: previous-year data missing",
            "affected_metric": "reserves",
            "resolution_status": "resolved",
        },
        {
            "original_warning": "npm: previous-year data missing",
            "normalized_warning": "npm: previous-year data missing",
            "affected_metric": "npm",
            "resolution_status": "resolved",
        },
    ]
    report = _run_legacy_with_truth_pack(tmp_path, trends, truth_pack)

    assert "reserves: previous-year data missing" not in report.warnings
    assert "npm: previous-year data missing" not in report.warnings


def test_trends_top_level_warnings_pass_through_when_no_blocked_match(tmp_path: Path):
    trends = dict(_MINIMAL_TRENDS)
    trends["warnings"] = [
        "FCF derived, not explicitly disclosed.",
        "corporate actions affect per-share comparability in fy24: buyback",
    ]
    report = _run_legacy_with_truth_pack(tmp_path, trends, _EMPTY_TRUTH_PACK)

    assert "FCF derived, not explicitly disclosed." in report.warnings
    assert "corporate actions affect per-share comparability in fy24: buyback" in report.warnings


def test_blocked_downstream_fix_is_company_agnostic(tmp_path: Path):
    for company_name in ("widgetco", "pharmaltd", "infra_corp"):
        trends = dict(_MINIMAL_TRENDS)
        trends["company"] = company_name
        truth_pack = dict(_EMPTY_TRUTH_PACK)
        truth_pack["financial_warnings_blocked_downstream"] = [
            {
                "original_warning": "cfo: previous-year data missing",
                "normalized_warning": "cfo: previous-year data missing",
                "affected_metric": "cfo",
                "resolution_status": "resolved",
            }
        ]
        sub_path = tmp_path / company_name
        sub_path.mkdir(exist_ok=True)
        report = _run_legacy_with_truth_pack(sub_path, trends, truth_pack)
        assert "cfo: previous-year data missing" not in report.warnings, (
            f"Stale warning injected for company {company_name!r}"
        )
