from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .validation_schema import (
    FinancialValidationReport,
    ValidationCheck,
    validate_financial_validation_report_payload,
)


MONETARY_FIELDS = {
    ("profit_and_loss", "revenue"),
    ("profit_and_loss", "other_income"),
    ("profit_and_loss", "total_income"),
    ("profit_and_loss", "cost_of_materials"),
    ("profit_and_loss", "employee_cost"),
    ("profit_and_loss", "other_expenses"),
    ("profit_and_loss", "ebitda"),
    ("profit_and_loss", "depreciation"),
    ("profit_and_loss", "ebit"),
    ("profit_and_loss", "finance_cost"),
    ("profit_and_loss", "pbt"),
    ("profit_and_loss", "tax"),
    ("profit_and_loss", "pat"),
    ("balance_sheet", "equity_share_capital"),
    ("balance_sheet", "reserves"),
    ("balance_sheet", "net_worth"),
    ("balance_sheet", "total_debt"),
    ("balance_sheet", "short_term_debt"),
    ("balance_sheet", "long_term_debt"),
    ("balance_sheet", "cash_and_equivalents"),
    ("balance_sheet", "investments"),
    ("balance_sheet", "inventories"),
    ("balance_sheet", "receivables"),
    ("balance_sheet", "payables"),
    ("balance_sheet", "fixed_assets"),
    ("balance_sheet", "cwip"),
    ("balance_sheet", "total_assets"),
    ("balance_sheet", "total_liabilities"),
    ("cash_flow", "cfo"),
    ("cash_flow", "cfi"),
    ("cash_flow", "cff"),
    ("cash_flow", "capex"),
    ("cash_flow", "fcf"),
    ("cash_flow", "dividends_paid"),
    ("cash_flow", "interest_paid"),
    ("cash_flow", "tax_paid"),
}

WARNING_MISSING_FIELDS = [
    ("cash_flow", "cfo", "CFO missing"),
    ("cash_flow", "capex", "capex missing"),
    ("balance_sheet", "total_debt", "debt missing or unclear"),
    ("profit_and_loss", "eps_basic", "EPS missing"),
    ("share_data", "shares_outstanding", "share count missing"),
    ("balance_sheet", "reserves", "reserves missing"),
    ("share_data", "book_value_per_share", "book value inputs missing"),
]

_FORBIDDEN_SOURCE_PATTERNS = {
    ("profit_and_loss", "ebit"): (
        "surplus in statement of profit and loss",
        "opening balance",
        "other equity",
        "reserves and surplus",
    ),
    ("profit_and_loss", "ebitda"): (
        "surplus in statement of profit and loss",
        "opening balance",
        "other equity",
        "reserves and surplus",
    ),
    ("share_data", "face_value"): (
        "fair value gain",
        "re-measurement",
        "fvtpl",
        "fvoci",
    ),
    ("share_data", "shares_outstanding"): (
        "micro enterprises",
        "small enterprises",
        "outstanding dues",
        "payables",
        "liabilities",
    ),
    ("share_data", "weighted_avg_shares"): (
        "micro enterprises",
        "small enterprises",
        "outstanding dues",
        "payables",
        "liabilities",
    ),
    ("share_data", "diluted_shares"): (
        "micro enterprises",
        "small enterprises",
        "outstanding dues",
        "payables",
        "liabilities",
    ),
}

_PER_SHARE_FIELDS = {
    ("profit_and_loss", "eps_basic"),
    ("profit_and_loss", "eps_diluted"),
    ("share_data", "face_value"),
    ("share_data", "book_value_per_share"),
}

_SHARE_COUNT_FIELDS = {
    ("share_data", "shares_outstanding"),
    ("share_data", "weighted_avg_shares"),
    ("share_data", "diluted_shares"),
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _entry(payload: Dict[str, Any], section: str, field: str) -> Dict[str, Any]:
    return payload.get(section, {}).get(field, {}) if isinstance(payload.get(section), dict) else {}


def _value(entry_payload: Dict[str, Any]) -> Optional[float]:
    value = entry_payload.get("value_crore")
    return float(value) if isinstance(value, (int, float)) else None


def _has_original(entry_payload: Dict[str, Any]) -> bool:
    return bool(str(entry_payload.get("value_original", "")).strip())


def _basis_checked(payload: Dict[str, Any]) -> str:
    bases = set()
    for section_name in ("profit_and_loss", "balance_sheet", "cash_flow", "share_data", "corporate_actions", "shareholding_pattern"):
        section = payload.get(section_name, {})
        if not isinstance(section, dict):
            continue
        for entry_payload in section.values():
            if not isinstance(entry_payload, dict):
                continue
            if _has_original(entry_payload):
                basis = str(entry_payload.get("basis", "unknown"))
                if basis:
                    bases.add(basis)
    if not bases:
        return "unknown"
    if len(bases) == 1:
        only = next(iter(bases))
        return only if only in {"standalone", "consolidated", "unknown"} else "unknown"
    return "mixed"


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _source_line(entry_payload: Dict[str, Any]) -> str:
    return str(entry_payload.get("source_line_item", "") or "").lower()


def _consistency_status(delta: float, base: float) -> str:
    tolerance_warn = max(1.0, base * 0.02)
    tolerance_fail = max(5.0, base * 0.10)
    if delta > tolerance_fail:
        return "fail"
    if delta > tolerance_warn:
        return "warning"
    return "pass"


def _check_consistency(
    *,
    checks: List[ValidationCheck],
    warnings: List[str],
    hard_failures: List[str],
    name: str,
    left: Optional[float],
    right: Optional[float],
    details_prefix: str,
) -> None:
    if left is None or right is None:
        checks.append(ValidationCheck(name, "warning", f"{details_prefix}: insufficient data"))
        _append_unique(warnings, f"{name} could not be fully checked")
        return
    delta = abs(left - right)
    status = _consistency_status(delta, max(abs(left), abs(right), 1.0))
    details = f"{details_prefix}: left={left:.2f}, right={right:.2f}, delta={delta:.2f}"
    checks.append(ValidationCheck(name, status, details))
    if status == "warning":
        _append_unique(warnings, f"{name} mismatch exceeds warning tolerance")
    elif status == "fail":
        _append_unique(hard_failures, f"{name} mismatch exceeds fail tolerance")


def validate_normalized_fundamentals(*, company: str, year: str, normalized_path: Path) -> FinancialValidationReport:
    payload = _load_json(normalized_path)

    hard_failures: List[str] = []
    warnings: List[str] = []
    checks: List[ValidationCheck] = []
    missing_fields: List[str] = []
    suspicious_values: List[str] = []

    required_fields = [
        ("profit_and_loss", "revenue", "revenue missing"),
        ("profit_and_loss", "pat", "PAT missing"),
        ("balance_sheet", "total_assets", "total_assets missing"),
    ]
    for section_name, field_name, message in required_fields:
        if not _has_original(_entry(payload, section_name, field_name)):
            _append_unique(hard_failures, message)
            _append_unique(missing_fields, f"{section_name}.{field_name}")

    equity_entry = _entry(payload, "balance_sheet", "net_worth")
    share_capital_entry = _entry(payload, "balance_sheet", "equity_share_capital")
    if not (_has_original(equity_entry) or _has_original(share_capital_entry)):
        _append_unique(hard_failures, "net_worth / equity missing")
        _append_unique(missing_fields, "balance_sheet.net_worth")

    cash_flow_present = any(
        _has_original(_entry(payload, "cash_flow", field_name))
        for field_name in ("cfo", "cfi", "cff", "capex", "dividends_paid", "interest_paid", "tax_paid")
    )
    if not cash_flow_present:
        _append_unique(hard_failures, "cash flow statement entirely missing")
        _append_unique(missing_fields, "cash_flow")

    for section_name, field_name, message in WARNING_MISSING_FIELDS:
        if not _has_original(_entry(payload, section_name, field_name)):
            _append_unique(warnings, message)
            _append_unique(missing_fields, f"{section_name}.{field_name}")

    total_assets = _value(_entry(payload, "balance_sheet", "total_assets"))
    total_liabilities = _value(_entry(payload, "balance_sheet", "total_liabilities"))
    net_worth = _value(_entry(payload, "balance_sheet", "net_worth")) or _value(_entry(payload, "balance_sheet", "equity_share_capital"))
    _check_consistency(
        checks=checks,
        warnings=warnings,
        hard_failures=hard_failures,
        name="balance_sheet_equation",
        left=total_assets,
        right=(total_liabilities + net_worth) if total_liabilities is not None and net_worth is not None else None,
        details_prefix="total_assets versus total_liabilities + equity",
    )

    revenue = _value(_entry(payload, "profit_and_loss", "revenue"))
    other_income = _value(_entry(payload, "profit_and_loss", "other_income")) or 0.0
    total_income = _value(_entry(payload, "profit_and_loss", "total_income"))
    _check_consistency(
        checks=checks,
        warnings=warnings,
        hard_failures=hard_failures,
        name="total_income_equation",
        left=total_income,
        right=(revenue + other_income) if revenue is not None else None,
        details_prefix="total_income versus revenue + other_income",
    )

    pbt = _value(_entry(payload, "profit_and_loss", "pbt"))
    ebit = _value(_entry(payload, "profit_and_loss", "ebit"))
    finance_cost = _value(_entry(payload, "profit_and_loss", "finance_cost"))
    if ebit is not None and finance_cost is not None:
        derived_formula = str(_entry(payload, "profit_and_loss", "ebit").get("formula", "") or "").lower()
        bridge_right = ebit - finance_cost
        if "pbt + finance_cost" in derived_formula and pbt is not None:
            bridge_right = pbt
        _check_consistency(
            checks=checks,
            warnings=warnings,
            hard_failures=hard_failures,
            name="pbt_bridge",
            left=pbt,
            right=bridge_right,
            details_prefix="PBT versus EBIT - finance_cost",
        )
    else:
        checks.append(ValidationCheck("pbt_bridge", "warning", "PBT bridge: insufficient data"))
        _append_unique(warnings, "PBT bridge could not be fully checked")

    pat = _value(_entry(payload, "profit_and_loss", "pat"))
    tax = _value(_entry(payload, "profit_and_loss", "tax")) or 0.0
    _check_consistency(
        checks=checks,
        warnings=warnings,
        hard_failures=hard_failures,
        name="pat_bridge",
        left=pat,
        right=(pbt - tax) if pbt is not None else None,
        details_prefix="PAT versus PBT - tax",
    )

    equity_share_capital = _value(_entry(payload, "balance_sheet", "equity_share_capital"))
    reserves = _value(_entry(payload, "balance_sheet", "reserves"))
    if equity_share_capital is not None and reserves is not None:
        _check_consistency(
            checks=checks,
            warnings=warnings,
            hard_failures=hard_failures,
            name="net_worth_bridge",
            left=net_worth,
            right=equity_share_capital + reserves,
            details_prefix="net_worth versus equity_share_capital + reserves",
        )
    else:
        checks.append(ValidationCheck("net_worth_bridge", "warning", "net worth bridge: insufficient data"))
        _append_unique(warnings, "net worth bridge could not be fully checked")

    cfo = _value(_entry(payload, "cash_flow", "cfo"))
    capex = _value(_entry(payload, "cash_flow", "capex"))
    if cfo is not None and capex is not None:
        checks.append(
            ValidationCheck(
                "fcf_readiness",
                "pass",
                f"FCF can be derived from CFO and capex: cfo={cfo:.2f}, capex={capex:.2f}",
            )
        )
    else:
        checks.append(ValidationCheck("fcf_readiness", "warning", "FCF cannot be derived because CFO or capex is missing"))
        _append_unique(warnings, "FCF not derivable from current normalized fundamentals")

    period_values = set()
    for section_name in ("profit_and_loss", "balance_sheet", "cash_flow"):
        section = payload.get(section_name, {})
        if not isinstance(section, dict):
            continue
        for entry_payload in section.values():
            if isinstance(entry_payload, dict) and _has_original(entry_payload):
                period_values.add(str(entry_payload.get("period", "")))
    if len(period_values) > 1:
        checks.append(ValidationCheck("period_consistency", "warning", f"Multiple periods detected: {sorted(period_values)}"))
        _append_unique(warnings, "periods are not fully consistent across normalized fundamentals")
    else:
        checks.append(ValidationCheck("period_consistency", "pass", f"Consistent period set: {sorted(period_values)}"))

    for section_name, field_name in MONETARY_FIELDS:
        entry_payload = _entry(payload, section_name, field_name)
        if not _has_original(entry_payload):
            continue
        if _value(entry_payload) is None:
            _append_unique(warnings, f"monetary value_crore missing for {section_name}.{field_name}")
        if not str(entry_payload.get("unit_original", "")).strip():
            _append_unique(warnings, f"unit_original missing for {section_name}.{field_name}")
        if entry_payload.get("source_page") is None:
            _append_unique(warnings, f"source_page missing for {section_name}.{field_name}")
        if not str(entry_payload.get("source_artifact", "")).strip():
            _append_unique(warnings, f"source_artifact missing for {section_name}.{field_name}")
        if str(entry_payload.get("basis", "") or "unknown") not in {"standalone", "consolidated", "unknown"}:
            _append_unique(warnings, f"basis invalid for {section_name}.{field_name}")

    for section_name, field_name in _PER_SHARE_FIELDS:
        entry_payload = _entry(payload, section_name, field_name)
        if not _has_original(entry_payload):
            continue
        if _value(entry_payload) is not None:
            _append_unique(warnings, f"{section_name}.{field_name} should not carry value_crore")
        unit_original = str(entry_payload.get("unit_original", "") or "").lower()
        if unit_original and "share" not in unit_original and "inr" not in unit_original and "₹" not in unit_original:
            _append_unique(warnings, f"{section_name}.{field_name} has suspicious per-share unit_original")

    for section_name, field_name in _SHARE_COUNT_FIELDS:
        entry_payload = _entry(payload, section_name, field_name)
        if not _has_original(entry_payload):
            continue
        if _value(entry_payload) is not None:
            _append_unique(warnings, f"{section_name}.{field_name} should not carry value_crore")
        unit_original = str(entry_payload.get("unit_original", "") or "").lower()
        if unit_original and "share" not in unit_original:
            _append_unique(warnings, f"{section_name}.{field_name} has suspicious share-count unit_original")

    for (section_name, field_name), patterns in _FORBIDDEN_SOURCE_PATTERNS.items():
        entry_payload = _entry(payload, section_name, field_name)
        if not _has_original(entry_payload):
            continue
        source_line = _source_line(entry_payload)
        if any(pattern in source_line for pattern in patterns):
            _append_unique(warnings, f"{section_name}.{field_name} mapped from suspicious source_line_item")

    def _flag_if(condition: bool, message: str) -> None:
        if condition:
            _append_unique(suspicious_values, message)
            _append_unique(warnings, message)

    depreciation = _value(_entry(payload, "profit_and_loss", "depreciation"))
    finance_cost_value = _value(_entry(payload, "profit_and_loss", "finance_cost"))
    total_debt = _value(_entry(payload, "balance_sheet", "total_debt"))
    cash_and_equivalents = _value(_entry(payload, "balance_sheet", "cash_and_equivalents"))
    _flag_if(depreciation is not None and depreciation < 0, "depreciation is negative")
    _flag_if(finance_cost_value is not None and finance_cost_value < 0, "finance_cost is negative")
    _flag_if(capex is not None and capex > 0, "capex sign looks suspiciously positive")
    _flag_if(cfo is not None and abs(cfo) == 0, "CFO is zero")
    _flag_if(total_debt is not None and total_debt < 0, "debt is negative")
    _flag_if(cash_and_equivalents is not None and cash_and_equivalents < 0, "cash_and_equivalents is negative")

    status = "pass"
    if hard_failures or any(check.status == "fail" for check in checks):
        status = "fail"
    elif warnings or any(check.status == "warning" for check in checks):
        status = "warning"

    report = FinancialValidationReport(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status=status,
        basis_checked=_basis_checked(payload),
        hard_failures=hard_failures,
        warnings=warnings,
        checks=checks,
        missing_fields=missing_fields,
        suspicious_values=suspicious_values,
        limitations=[
            "Financial validation checks readiness for downstream ratio calculation but does not rewrite normalized fundamentals.",
            "Consistency checks use tolerances because annual-report extraction and normalization can still contain rounding and mapping noise.",
        ],
    )

    errors = validate_financial_validation_report_payload(report.to_dict())
    if errors:
        raise ValueError("; ".join(errors))
    return report


def write_financial_validation_report(
    *,
    company: str,
    year: str,
    normalized_path: Path,
    output_path: Path,
) -> FinancialValidationReport:
    report = validate_normalized_fundamentals(company=company, year=year, normalized_path=normalized_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return report
