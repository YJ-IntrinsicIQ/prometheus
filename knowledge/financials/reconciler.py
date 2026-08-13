from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .line_item_mapper import map_line_item
from .reconciliation_schema import (
    FinancialReconciliationReport,
    ReconciliationFieldCheck,
    validate_financial_reconciliation_payload,
)


CRITICAL_GATE_FIELDS = {
    "revenue",
    "pat",
    "total_assets",
    "capex",
    "fcf",
    "eps_basic",
    "eps_diluted",
    "shares_outstanding",
    "weighted_avg_shares",
    "diluted_shares",
}

EXPECTED_VALUE_TYPES = {
    "eps_basic": "per_share",
    "eps_diluted": "per_share",
    "face_value": "per_share",
    "book_value_per_share": "per_share",
    "shares_outstanding": "share_count",
    "weighted_avg_shares": "share_count",
    "diluted_shares": "share_count",
}

FIELD_SPECS = {
    "revenue": ("profit_and_loss", "revenue"),
    "ebitda": ("profit_and_loss", "ebitda"),
    "ebit": ("profit_and_loss", "ebit"),
    "finance_cost": ("profit_and_loss", "finance_cost"),
    "pat": ("profit_and_loss", "pat"),
    "eps_basic": ("profit_and_loss", "eps_basic"),
    "eps_diluted": ("profit_and_loss", "eps_diluted"),
    "net_worth": ("balance_sheet", "net_worth"),
    "total_assets": ("balance_sheet", "total_assets"),
    "total_debt": ("balance_sheet", "total_debt"),
    "cash_and_equivalents": ("balance_sheet", "cash_and_equivalents"),
    "receivables": ("balance_sheet", "receivables"),
    "inventories": ("balance_sheet", "inventories"),
    "payables": ("balance_sheet", "payables"),
    "cfo": ("cash_flow", "cfo"),
    "capex": ("cash_flow", "capex"),
    "fcf": ("cash_flow", "fcf"),
    "dividends_paid": ("cash_flow", "dividends_paid"),
    "shares_outstanding": ("share_data", "shares_outstanding"),
    "weighted_avg_shares": ("share_data", "weighted_avg_shares"),
    "diluted_shares": ("share_data", "diluted_shares"),
}

ALLOWED_SOURCE_SECTIONS = {
    "profit_and_loss": {"primary_profit_and_loss_statement", "financial_note"},
    "balance_sheet": {"primary_balance_sheet_statement", "financial_note", "share_capital_note", "statement_of_changes_in_equity"},
    "cash_flow": {"primary_cash_flow_statement", "financial_note"},
    "share_data": {
        "share_capital_note",
        "shareholding_note",
        "eps_note",
        "primary_profit_and_loss_statement",
        "equity_note",
        "share_data",
        "notes_to_accounts",
    },
}

DISALLOWED_SOURCE_SECTIONS = {
    "management_discussion_financial_summary",
    "accounting_policy",
    "auditor_report",
    "irrelevant_financial_text",
}

CAPEX_ALLOWED_SOURCE_TOKENS = (
    "purchase of property, plant and equipment",
    "purchase of property plant and equipment",
    "purchase of ppe",
    "acquisition of property, plant and equipment",
    "acquisition of property plant and equipment",
    "payment for property, plant and equipment",
    "payment for property plant and equipment",
    "capital expenditure",
    "capex",
    "purchase of intangible assets",
    "purchase of fixed assets",
    "investment in capital work in progress",
    "investment in capital work-in-progress",
)

CAPEX_DISALLOWED_SOURCE_TOKENS = (
    "net cash used in investing activities",
    "net cash from investing activities",
    "closing balance",
    "opening balance",
    "balance as at",
    "depreciation",
    "right-of-use",
    "right of use",
    "lease payment",
    "lease liability",
    "mutual fund",
    "generic investing activity",
)

PAYABLES_ALLOWED_SOURCE_TOKENS = (
    "trade payables",
    "total trade payables",
    "accounts payable",
    "supplier payables",
    "dues to suppliers",
    "creditors for goods services",
    "creditors for goods and services",
)

PAYABLES_COMPONENT_SOURCE_TOKENS = (
    "total outstanding dues of micro enterprises and small enterprises",
    "total outstanding dues of creditors other than micro enterprises and small enterprises",
)

PAYABLES_DISALLOWED_SOURCE_TOKENS = (
    "total liabilities",
    "other financial liabilities",
    "borrowings",
    "lease liabilities",
    "lease liability",
    "provisions",
    "deferred tax liabilities",
    "other current liabilities",
    "contract liabilities",
    "employee liabilities",
    "employee related payables",
    "statutory dues",
    "current liabilities",
    "capital creditors",
    "advance to suppliers",
)

SHARES_OUTSTANDING_ALLOWED_LINE_TOKENS = (
    "issued",
    "subscribed",
    "fully paid",
    "fully paid up",
    "paid up equity shares",
    "issued subscribed and fully paid up",
    "equity shares outstanding",
    "outstanding equity shares",
    "number of shares outstanding",
    "number of equity shares outstanding",
)

SHARES_OUTSTANDING_DISALLOWED_LINE_TOKENS = (
    "authorised",
    "authorized",
    "securities premium",
    "reserves",
    "dividend",
    "qip proceeds",
    "proceeds utilisation",
    "share application money",
)

SHARES_OUTSTANDING_ALLOWED_SECTION_TYPES = {
    "share_capital_note",
    "equity_note",
    "share_data",
    "notes_to_accounts",
}

SHARES_OUTSTANDING_ALLOWED_STATEMENT_TYPES = {
    "share_capital_note",
    "equity_note",
    "share_data",
    "notes_to_accounts",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _entry(payload: Dict[str, Any], section: str, field: str) -> Dict[str, Any]:
    section_payload = payload.get(section, {})
    return section_payload.get(field, {}) if isinstance(section_payload, dict) else {}


def _expected_table_type(section: str, field: str, entry_payload: Dict[str, Any]) -> str:
    statement_type = str(entry_payload.get("statement_type", "") or "")
    if statement_type:
        return statement_type
    if section == "share_data":
        if field in {"shares_outstanding", "weighted_avg_shares", "diluted_shares", "face_value"}:
            return "share_capital"
        return "eps"
    return section


def _is_related_source(section: str, field: str, entry_payload: Dict[str, Any]) -> bool:
    if entry_payload.get("derived") is True:
        return True
    line_item = str(entry_payload.get("source_line_item", "") or "")
    if not line_item:
        return False
    table_type = _expected_table_type(section, field, entry_payload)
    matches = map_line_item(table_type=table_type, line_item_raw=line_item)
    return any(match.canonical_section == section and match.canonical_field == field for match in matches)


def _is_valid_shares_outstanding_source(entry_payload: Dict[str, Any]) -> bool:
    source_line_item = str(entry_payload.get("source_line_item", "") or "").lower()
    source_section_type = str(entry_payload.get("source_section_type", "") or "").lower()
    statement_type = str(entry_payload.get("statement_type", "") or "").lower()
    source_value_type = str(entry_payload.get("source_value_type", "") or "").lower()
    value_type = str(entry_payload.get("value_type", "") or "").lower()

    if not source_line_item:
        return False
    if any(token in source_line_item for token in SHARES_OUTSTANDING_DISALLOWED_LINE_TOKENS):
        return False
    if not any(token in source_line_item for token in SHARES_OUTSTANDING_ALLOWED_LINE_TOKENS):
        return False
    if source_section_type not in SHARES_OUTSTANDING_ALLOWED_SECTION_TYPES and statement_type not in SHARES_OUTSTANDING_ALLOWED_STATEMENT_TYPES:
        return False
    if source_value_type != "share_count" and value_type != "share_count":
        return False
    if entry_payload.get("value_shares") in (None, "") and entry_payload.get("raw_number") in (None, ""):
        return False
    if entry_payload.get("value_crore") not in (None, ""):
        return False
    return True


def _check_field(field_name: str, section: str, entry_payload: Dict[str, Any]) -> ReconciliationFieldCheck:
    source_section_type = str(entry_payload.get("source_section_type", "") or "")
    source_line_item = str(entry_payload.get("source_line_item", "") or "")
    statement_type = str(entry_payload.get("statement_type", "") or "")
    basis = str(entry_payload.get("basis", "unknown") or "unknown")
    source_artifact = str(entry_payload.get("source_artifact", "") or "")
    warnings: List[str] = []
    hard_failure = False
    status = "pass"
    reason = "reconciled source looks relevant"

    has_value = entry_payload.get("value_original") not in (None, "", [])
    if not has_value and entry_payload.get("value_crore") is None:
        status = "warning"
        reason = "field has no populated normalized value"
        warnings.append("missing normalized value")
        return ReconciliationFieldCheck(
            field_name=field_name,
            status=status,
            hard_failure=False,
            reason=reason,
            source_line_item=source_line_item,
            source_section_type=source_section_type,
            statement_type=statement_type,
            basis=basis,
            source_artifacts=[source_artifact] if source_artifact else [],
            warnings=warnings,
        )

    if source_section_type in DISALLOWED_SOURCE_SECTIONS:
        status = "fail"
        hard_failure = field_name in CRITICAL_GATE_FIELDS
        reason = f"normalized field uses disallowed source section: {source_section_type}"

    allowed_sections = ALLOWED_SOURCE_SECTIONS.get(section, set())
    if status == "pass" and source_section_type and allowed_sections and source_section_type not in allowed_sections:
        status = "warning"
        reason = f"source section is unusual for {field_name}: {source_section_type}"
        warnings.append(reason)

    if status == "pass" and field_name == "shares_outstanding":
        if not _is_valid_shares_outstanding_source(entry_payload):
            status = "fail"
            hard_failure = field_name in CRITICAL_GATE_FIELDS
            reason = "normalized field uses unrelated source line item"
    elif status == "pass" and not _is_related_source(section, field_name, entry_payload):
        status = "fail"
        hard_failure = field_name in CRITICAL_GATE_FIELDS
        reason = "normalized field uses unrelated source line item"

    if field_name == "capex" and has_value and status == "pass":
        normalized_line_item = source_line_item.lower()
        if any(token in normalized_line_item for token in CAPEX_DISALLOWED_SOURCE_TOKENS):
            status = "fail"
            hard_failure = True
            reason = "capex uses disallowed balance or non-capex source line item"
        elif not any(token in normalized_line_item for token in CAPEX_ALLOWED_SOURCE_TOKENS):
            status = "fail"
            hard_failure = True
            reason = "capex is populated without clear investing cash-flow evidence"

    if field_name == "payables" and has_value and status == "pass":
        normalized_line_item = source_line_item.lower()
        if entry_payload.get("derived") is True:
            if source_line_item != "derived:trade_payables":
                status = "fail"
                hard_failure = True
                reason = "derived payables uses unsupported source line item"
            elif str(entry_payload.get("formula", "") or "") != "msme_trade_payables + other_trade_payables":
                status = "fail"
                hard_failure = True
                reason = "derived payables is missing the canonical aggregation formula"
            else:
                inputs_used = entry_payload.get("inputs_used")
                if not isinstance(inputs_used, dict) or not {
                    "msme_trade_payables",
                    "other_trade_payables",
                }.issubset(inputs_used.keys()):
                    status = "fail"
                    hard_failure = True
                    reason = "derived payables is missing trade-payable component inputs"
        elif any(token in normalized_line_item for token in PAYABLES_DISALLOWED_SOURCE_TOKENS):
            status = "fail"
            hard_failure = True
            reason = "payables uses generic liabilities or non-trade-payable source line item"
        elif not any(token in normalized_line_item for token in PAYABLES_ALLOWED_SOURCE_TOKENS + PAYABLES_COMPONENT_SOURCE_TOKENS):
            status = "fail"
            hard_failure = True
            reason = "payables is populated without clear trade-payable evidence"

    expected_value_type = EXPECTED_VALUE_TYPES.get(field_name)
    source_value_type = str(entry_payload.get("source_value_type", "") or "")
    if expected_value_type:
        if not source_value_type:
            status = "fail" if field_name in CRITICAL_GATE_FIELDS else "warning"
            hard_failure = field_name in CRITICAL_GATE_FIELDS
            reason = f"value type missing for {field_name}"
        elif source_value_type != expected_value_type:
            status = "fail"
            hard_failure = field_name in CRITICAL_GATE_FIELDS
            reason = f"value type mismatch: expected {expected_value_type}, got {source_value_type}"

    if field_name == "fcf" and has_value:
        if entry_payload.get("derived") is True:
            if not entry_payload.get("formula") or not isinstance(entry_payload.get("inputs_used"), dict) or not entry_payload.get("inputs_used"):
                status = "fail"
                hard_failure = True
                reason = "derived FCF is missing formula or inputs_used"
        elif status == "pass":
            normalized_line_item = source_line_item.lower()
            if "free cash flow" not in normalized_line_item and "free cashflow" not in normalized_line_item and "fcf" not in normalized_line_item.split():
                status = "fail"
                hard_failure = True
                reason = "FCF uses unrelated source line item"

    if field_name == "capex" and has_value and status == "pass":
        sign_convention = str(entry_payload.get("sign_convention", "") or "")
        if sign_convention not in {"cash_flow_signed", "positive_outflow"}:
            status = "warning"
            reason = "capex sign convention missing or unclear"
            warnings.append("capex sign convention missing or unclear")

    if entry_payload.get("derived") is True and status == "pass" and field_name != "payables":
        status = "warning"
        reason = f"{field_name} is derived from normalized inputs"
        warnings.append("derived value used")

    return ReconciliationFieldCheck(
        field_name=field_name,
        status=status,
        hard_failure=hard_failure,
        reason=reason,
        source_line_item=source_line_item,
        source_section_type=source_section_type,
        statement_type=statement_type,
        basis=basis,
        source_artifacts=[source_artifact] if source_artifact else [],
        warnings=warnings,
    )


def build_financial_reconciliation_report(*, company: str, year: str, normalized_path: Path) -> FinancialReconciliationReport:
    normalized = _load_json(normalized_path)
    if not isinstance(normalized, dict):
        raise RuntimeError("financial_reconciliation requires normalized_fundamentals.json to contain an object")

    checks: Dict[str, ReconciliationFieldCheck] = {}
    hard_failures: List[str] = []
    warnings: List[str] = []
    for field_name, (section, field) in FIELD_SPECS.items():
        check = _check_field(field_name, section, _entry(normalized, section, field))
        checks[field_name] = check
        if check.hard_failure and check.status == "fail":
            _append_unique(hard_failures, f"{field_name}: {check.reason}")
        if check.status == "warning":
            _append_unique(warnings, f"{field_name}: {check.reason}")
        for warning in check.warnings:
            _append_unique(warnings, f"{field_name}: {warning}")

    preferred_basis = str(normalized.get("preferred_basis", "unknown") or "unknown")
    basis_manifest = normalized.get("basis_manifest") or {}
    explicit_basis_warnings = [
        str(item)
        for item in (basis_manifest.get("basis_warnings", []) if isinstance(basis_manifest, dict) else [])
        if str(item).strip()
    ]
    critical_basis_values = {
        check.basis
        for field_name, check in checks.items()
        if field_name in CRITICAL_GATE_FIELDS
        and check.basis in {"standalone", "consolidated", "unknown"}
        and checks[field_name].status != "warning"
    }
    explicit_warning_present = bool(explicit_basis_warnings)
    if len({basis for basis in critical_basis_values if basis in {"standalone", "consolidated"}}) > 1 and not explicit_warning_present:
        _append_unique(
            hard_failures,
            "critical financial fields mix standalone and consolidated basis without explicit basis warning",
        )
    elif preferred_basis == "unknown" or "unknown" in critical_basis_values or explicit_warning_present:
        if preferred_basis == "unknown":
            _append_unique(warnings, "preferred basis is unknown")
        if "unknown" in critical_basis_values:
            _append_unique(warnings, "critical financial fields include unknown basis entries")
        for warning in explicit_basis_warnings:
            _append_unique(warnings, warning)

    status = "fail" if hard_failures else "warning" if warnings else "pass"
    report = FinancialReconciliationReport(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status=status,
        checks=checks,
        hard_failures=hard_failures,
        warnings=warnings,
        limitations=[
            "Financial reconciliation is deterministic and checks normalized field relevance before ratios or growth are calculated.",
            "Reconciliation validates source relevance and value typing; it does not restate or recalculate raw financial numbers.",
        ],
    )
    errors = validate_financial_reconciliation_payload(report.to_dict())
    if errors:
        raise ValueError("Invalid financial reconciliation payload: " + "; ".join(errors))
    return report


def write_financial_reconciliation_report(
    *,
    company: str,
    year: str,
    normalized_path: Path,
    output_path: Path,
) -> FinancialReconciliationReport:
    report = build_financial_reconciliation_report(
        company=company,
        year=year,
        normalized_path=normalized_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def reconciliation_blocks_stage(
    payload: Dict[str, Any],
    *,
    required_fields: Sequence[str],
) -> List[str]:
    status = str(payload.get("status", "fail") or "fail")
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        return [f"financial_reconciliation_report status={status}"] if status not in {"pass", "warning"} else [
            "financial_reconciliation_report checks missing"
        ]

    failures: List[str] = []
    required = set(required_fields)
    for field_name in required:
        item = checks.get(field_name)
        if not isinstance(item, dict):
            failures.append(f"missing reconciliation check for {field_name}")
            continue
        if item.get("status") == "fail":
            failures.append(f"{field_name}: {item.get('reason', 'reconciliation failed')}")
    if failures:
        return failures
    if status not in {"pass", "warning"}:
        return [f"financial_reconciliation_report status={status}"]
    return []
