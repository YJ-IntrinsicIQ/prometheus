import json
from pathlib import Path

import pytest

from knowledge.robustness_baseline import (
    CODE_QUALITY_HARDENING_TARGETS,
    ROBUSTNESS_CORPUS_MANIFEST,
    ROBUSTNESS_FAILURE_CLASSES,
    artifact_cases,
    reopened_classes,
    robustness_metrics,
    status_counts,
    validate_robustness_baseline,
)


ROOT = Path(__file__).resolve().parents[2]


MINIMUM_REQUIRED_FAILURE_CLASSES = {
    "PERIOD_RESOLUTION_UNSUPPORTED",
    "PRIMARY_PNL_PAT_MISSING",
    "PRIMARY_BALANCE_SHEET_REQUIRED_FIELD_MISSING",
    "WRONG_TAX_ROW_SELECTED",
    "SEMANTIC_LINE_ITEM_COLLISION",
    "BASIS_MIXED_CONSOLIDATED_STANDALONE",
    "SOURCE_PERIOD_VS_TARGET_PERIOD_CONFLICT",
    "MULTI_EVENT_HISTORICAL_PERIOD_COLLISION",
    "CROSS_COMPANY_INTELLIGENCE_CONTAMINATION",
    "BUSINESS_RELEVANCE_QUARANTINE",
    "OCR_NO_TEXT_LAYER",
}


def _load_json(relative_path: str):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def _status(payload):
    if isinstance(payload, dict):
        return str(
            payload.get("status")
            or payload.get("overall_status")
            or payload.get("validation_status")
            or ""
        ).lower()
    return ""


def test_robustness_baseline_is_self_consistent():
    validation = validate_robustness_baseline(ROOT)

    assert validation["status"] == "pass", validation["issues"]
    assert not validation["issues"]
    assert MINIMUM_REQUIRED_FAILURE_CLASSES.issubset(
        {entry["failure_class"] for entry in ROBUSTNESS_FAILURE_CLASSES}
    )
    assert any(case["held_out"] for case in ROBUSTNESS_CORPUS_MANIFEST)
    assert {target["rank"] for target in CODE_QUALITY_HARDENING_TARGETS} == {1, 2, 3, 4, 5}


def test_status_governance_is_conservative_until_class_closure_criteria_are_met():
    counts = status_counts()

    assert counts == {
        "CLASS_FIXED": 11,
        "PARTIALLY_FIXED": 4,
        "OPEN": 0,
        "UNKNOWN": 0,
    }
    assert set(reopened_classes()) == set()
    for entry in ROBUSTNESS_FAILURE_CLASSES:
        if entry["status"] == "CLASS_FIXED":
            assert not entry["closure_gaps"]


def test_robustness_metrics_are_measurable():
    metrics = robustness_metrics()

    assert metrics["known_failure_classes"] == len(ROBUSTNESS_FAILURE_CLASSES)
    assert metrics["known_failure_instances"] >= 20
    assert metrics["stages_tested"] >= 6
    assert metrics["company_years_tested"] >= 10
    assert metrics["held_out_cases"] >= 2
    assert metrics["production_hard_fail_recurrence_count"] == len(reopened_classes())
    assert metrics["class_fixed_percent"] > 0.0


@pytest.mark.parametrize("case", list(artifact_cases(ROOT)), ids=lambda item: item["case_id"])
def test_real_corpus_artifacts_exist_and_match_expected_result(case):
    artifact_path = case["artifact_path"]

    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    expected = case["expected_result"]

    if expected == "PASS":
        if case["source_artifact"].endswith("normalized_fundamentals.json"):
            assert _has_required_financial_truth(payload)
        elif "committee_synthesis.json" in case["source_artifact"]:
            _assert_committee_unknowns_are_supported(payload)
        else:
            assert _status(payload) in {"pass", "ready", "supported", ""}
    elif expected == "WARNING":
        assert _status(payload) == "warning"
    elif expected == "REJECT":
        assert _status(payload) in {"blocked", "fail"}
    else:
        raise AssertionError(f"unsupported expected result: {expected}")


def test_financial_balance_sheet_regression_values_are_still_sane():
    fy21 = _load_json("companies/ujjivan/fy21/financials/normalized_fundamentals.json")
    fy22 = _load_json("companies/ujjivan/fy22/financials/normalized_fundamentals.json")
    fy24 = _load_json("companies/ujjivan/fy24/financials/normalized_fundamentals.json")
    fy23 = _load_json("companies/ujjivan/fy23/financials/normalized_fundamentals.json")
    tanla_fy24 = _load_json("companies/tanla/fy24/financials/normalized_fundamentals.json")
    datapatterns_fy24 = _load_json("companies/datapatterns/fy24/financials/normalized_fundamentals.json")
    datapatterns_fy25 = _load_json("companies/datapatterns/fy25/financials/normalized_fundamentals.json")
    tanla_fy22 = _load_json("companies/tanla/fy22/financials/normalized_fundamentals.json")

    assert fy21["balance_sheet"]["total_assets"]["value_crore"] == 18411.2438
    assert fy21["balance_sheet"]["total_liabilities"]["value_crore"] == 15213.0096
    assert fy22["balance_sheet"]["net_worth"]["value_crore"] == 2760.4381

    assert fy24["balance_sheet"]["equity_share_capital"]["value_crore"] == 1958.7633
    assert fy24["balance_sheet"]["net_worth"]["value_crore"] == 5568.5031
    assert fy24["balance_sheet"]["total_liabilities"]["value_crore"] == 34853.7132
    assert fy24["balance_sheet"]["total_assets"]["value_crore"] > fy24["balance_sheet"]["net_worth"]["value_crore"]

    assert fy23["balance_sheet"]["net_worth"]["value_crore"] == 3957.8865
    assert fy23["balance_sheet"]["total_liabilities"]["value_crore"] == 19646.5777
    assert tanla_fy24["balance_sheet"]["net_worth"]["value_crore"] == 1942.0
    assert tanla_fy24["balance_sheet"]["total_liabilities"]["value_crore"] == 1067.0
    assert datapatterns_fy24["balance_sheet"]["net_worth"]["value_crore"] == 1324.21
    assert datapatterns_fy24["balance_sheet"]["total_liabilities"]["value_crore"] == 367.56
    assert datapatterns_fy25["balance_sheet"]["net_worth"]["value_crore"] == 1508.22
    assert datapatterns_fy25["balance_sheet"]["total_liabilities"]["value_crore"] == 330.88
    for payload in (tanla_fy24, datapatterns_fy24, datapatterns_fy25):
        net_worth = payload["balance_sheet"]["net_worth"]
        assert "liabilities" not in net_worth["source_line_item"].lower()
    assert tanla_fy22["profit_and_loss"]["pat"]["value_crore"] is not None


def test_basis_class_regression_artifacts_preserve_field_ownership():
    tanla = _load_json("companies/tanla/fy25/financials/normalized_fundamentals.json")
    datapatterns = _load_json("companies/datapatterns/fy25/financials/normalized_fundamentals.json")
    ujjivan = _load_json("companies/ujjivan/fy24/financials/normalized_fundamentals.json")

    assert tanla["preferred_basis"] == "consolidated"
    for section_name, field_name in [
        ("profit_and_loss", "revenue"),
        ("profit_and_loss", "pat"),
        ("balance_sheet", "total_assets"),
        ("balance_sheet", "net_worth"),
        ("cash_flow", "cfo"),
    ]:
        assert tanla[section_name][field_name]["basis"] == "consolidated"
    for section in ("profit_and_loss", "balance_sheet", "cash_flow", "share_data", "corporate_actions", "shareholding_pattern"):
        for entry in tanla.get(section, {}).values():
            if isinstance(entry, dict) and entry.get("value_original"):
                assert entry.get("basis") in {"consolidated", "unknown"}

    assert datapatterns["preferred_basis"] == "standalone"
    assert datapatterns["profit_and_loss"]["revenue"]["basis"] == "standalone"
    assert datapatterns["balance_sheet"]["total_assets"]["basis"] == "standalone"

    assert ujjivan["preferred_basis"] == "unknown"
    assert ujjivan["profit_and_loss"]["revenue"]["basis"] == "unknown"
    assert ujjivan["balance_sheet"]["total_assets"]["basis"] == "standalone"


def test_ocr_no_text_layer_case_remains_a_blocked_reject():
    payload = _load_json("companies/polymatech/fy22/extracted/document_intake_report.json")

    assert payload["status"] == "blocked"
    assert payload["documents"][0]["classification"] == "IMAGE_ONLY_PDF"
    assert payload["documents"][0]["ocr_required"] is True
    assert payload["documents"][0]["has_extractable_text"] is False


def test_company_memory_isolation_held_out_cases_remain_valid():
    for path in [
        "companies/tips/company_memory/ask_intrinsiciq/ask_intrinsiciq_validation_report.json",
        "companies/datapatterns/company_memory/company_model/company_model_validation.json",
        "companies/polymatech/company_memory/management_progression/management_progression_validation.json",
    ]:
        assert _status(_load_json(path)) == "pass"


def _has_required_financial_truth(payload):
    pnl = payload.get("profit_and_loss", {})
    balance_sheet = payload.get("balance_sheet", {})
    return all(
        section.get(field, {}).get("value_crore") is not None
        for section, field in [
            (pnl, "revenue"),
            (pnl, "pat"),
            (balance_sheet, "total_assets"),
            (balance_sheet, "net_worth"),
            (balance_sheet, "total_liabilities"),
        ]
    )


def _assert_committee_unknowns_are_supported(payload):
    critical_unknowns = payload.get("critical_unknowns", [])

    assert isinstance(critical_unknowns, list)
    assert critical_unknowns
    for item in critical_unknowns:
        assert str(item.get("unknown") or "").strip()
