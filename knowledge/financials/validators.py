from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Dict

from .schema import (
    BalanceSheet,
    CorporateActionValue,
    FinancialStatements,
    MonetaryValue,
    NumericValue,
)


FORBIDDEN_SCHEMA_KEYS = {
    "financial_ratios",
    "ratios",
    "financial_trends",
    "trends",
}

BALANCE_SHEET_TOLERANCE_CRORE = 0.5


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def extend(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def _validate_monetary_value(path: str, value: MonetaryValue) -> ValidationResult:
    result = ValidationResult()
    if value.value_original is None:
        if value.value_crore is not None:
            result.errors.append(f"{path}.value_crore must be null when value_original is missing")
        if "missing_value" not in value.notes:
            result.warnings.append(f"{path} is missing and should be marked in notes")
        return result

    if not value.unit_original:
        result.errors.append(f"{path}.unit_original is required when value_original is present")
    if value.value_crore is None:
        result.errors.append(f"{path}.value_crore is required when value_original is present")
    if not value.currency:
        result.errors.append(f"{path}.currency is required")
    return result


def _validate_numeric_value(path: str, value: NumericValue) -> ValidationResult:
    result = ValidationResult()
    if value.value is None and "missing_value" not in value.notes:
        result.warnings.append(f"{path} is missing and should be marked in notes")
    return result


def _walk_dataclass(prefix: str, value: Any) -> ValidationResult:
    result = ValidationResult()
    if isinstance(value, MonetaryValue):
        return _validate_monetary_value(prefix, value)
    if isinstance(value, NumericValue):
        return _validate_numeric_value(prefix, value)
    if isinstance(value, CorporateActionValue):
        result.extend(_validate_monetary_value(f"{prefix}.amount", value.amount))
        return result
    if is_dataclass(value):
        for item in fields(value):
            result.extend(_walk_dataclass(f"{prefix}.{item.name}" if prefix else item.name, getattr(value, item.name)))
    return result


def _value_crore(value: MonetaryValue) -> float | None:
    return value.value_crore if isinstance(value, MonetaryValue) else None


def _validate_balance_sheet_consistency(balance_sheet: BalanceSheet) -> ValidationResult:
    result = ValidationResult()
    share_capital = _value_crore(balance_sheet.equity_share_capital)
    reserves = _value_crore(balance_sheet.reserves)
    net_worth = _value_crore(balance_sheet.net_worth)
    total_assets = _value_crore(balance_sheet.total_assets)
    total_liabilities = _value_crore(balance_sheet.total_liabilities)

    if share_capital is not None and reserves is not None and net_worth is not None:
        diff = abs((share_capital + reserves) - net_worth)
        if diff > BALANCE_SHEET_TOLERANCE_CRORE:
            result.warnings.append(
                "balance_sheet.net_worth does not match equity_share_capital + reserves within tolerance"
            )

    if total_assets is not None and total_liabilities is not None and net_worth is not None:
        diff = abs(total_assets - (total_liabilities + net_worth))
        if diff > BALANCE_SHEET_TOLERANCE_CRORE:
            result.warnings.append(
                "balance_sheet equation warning: total_assets does not match total_liabilities + net_worth within tolerance"
            )
    return result


def validate_financial_statements_payload(payload: Dict[str, Any]) -> ValidationResult:
    result = ValidationResult()
    for key in FORBIDDEN_SCHEMA_KEYS:
        if key in payload:
            result.errors.append(f"{key} is not allowed in the financial schema layer")
    return result


def validate_financial_statements(statements: FinancialStatements | Dict[str, Any]) -> ValidationResult:
    if isinstance(statements, dict):
        payload_result = validate_financial_statements_payload(statements)
        schema = FinancialStatements.from_dict(statements)
    else:
        payload_result = ValidationResult()
        schema = statements

    result = ValidationResult()
    result.extend(payload_result)
    result.extend(_walk_dataclass("", schema))
    result.extend(_validate_balance_sheet_consistency(schema.balance_sheet))
    return result
