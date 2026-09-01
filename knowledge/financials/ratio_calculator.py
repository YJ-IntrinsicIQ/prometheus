from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .ratio_schema import (
    FinancialRatioReport,
    RATIO_FIELDS,
    RatioItem,
    validate_financial_ratio_report_payload,
)
from .reconciler import reconciliation_blocks_stage


PERCENT_RATIO_FIELDS = {
    "gross_margin",
    "ebitda_margin",
    "ebit_margin",
    "opm",
    "npm",
    "roe",
    "roce",
    "roa",
    "payout_ratio",
}

X_RATIO_FIELDS = {
    "debt_to_equity",
    "net_debt_to_equity",
    "interest_coverage",
    "cfo_to_pat",
    "fcf_to_pat",
}

DAY_RATIO_FIELDS = {
    "receivable_days",
    "inventory_days",
    "payable_days",
    "cash_conversion_cycle",
}

CRITICAL_RECONCILIATION_FIELDS = {
    "revenue",
    "pat",
    "total_assets",
    "eps_basic",
    "eps_diluted",
    "shares_outstanding",
    "weighted_avg_shares",
    "diluted_shares",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _entry(payload: Dict[str, Any], section: str, field: str) -> Dict[str, Any]:
    return payload.get(section, {}).get(field, {}) if isinstance(payload.get(section), dict) else {}


def _value(entry_payload: Dict[str, Any], prefer_original_numeric: bool = False) -> Optional[float]:
    value = entry_payload.get("value_crore")
    if isinstance(value, (int, float)):
        return float(value)
    if prefer_original_numeric:
        raw = str(entry_payload.get("value_original", "")).strip().replace(",", "")
        if not raw:
            return None
        negative = raw.startswith("(") or raw.startswith("[") or raw.startswith("-")
        raw = raw.strip("()[]")
        if raw.startswith("-"):
            raw = raw[1:]
        try:
            number = float(raw)
        except ValueError:
            return None
        return -number if negative else number
    return None


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _basis_from_normalized(payload: Dict[str, Any]) -> str:
    return str(payload.get("preferred_basis", "unknown") or "unknown")


def _basis_confidence_from_normalized(payload: Dict[str, Any]) -> str:
    return str(payload.get("basis_confidence", "low") or "low")


def _basis_warnings_from_normalized(payload: Dict[str, Any]) -> List[str]:
    manifest = payload.get("basis_manifest") or {}
    warnings = manifest.get("basis_warnings", []) if isinstance(manifest, dict) else []
    results = [str(item) for item in warnings if str(item).strip()]
    basis = _basis_from_normalized(payload)
    if basis == "unknown":
        _append_unique(results, "preferred basis is unknown")
    return results


def _empty_ratio(name: str) -> RatioItem:
    if name in PERCENT_RATIO_FIELDS:
        unit = "%"
    elif name in X_RATIO_FIELDS:
        unit = "x"
    elif name in DAY_RATIO_FIELDS:
        unit = "days"
    elif name in {"net_debt", "fcf"}:
        unit = "₹ crore"
    else:
        unit = "₹/share"
    return RatioItem(
        ratio_name=name,
        value=None,
        unit=unit,
        formula="",
        inputs_used=[],
        basis="unknown",
        confidence="missing",
        warnings=[],
        source_artifacts=[],
    )


def _input_item(name: str, value: Optional[float], unit: str) -> Dict[str, Any]:
    return {"name": name, "value": round(float(value), 4) if isinstance(value, (int, float)) else None, "unit": unit}


def _source_artifacts(*entry_payloads: Dict[str, Any]) -> List[str]:
    artifacts: List[str] = []
    for entry_payload in entry_payloads:
        source = str(entry_payload.get("source_artifact", "") or "")
        if source:
            _append_unique(artifacts, source)
    return artifacts


def _set_ratio(
    ratios: Dict[str, RatioItem],
    name: str,
    *,
    value: Optional[float],
    unit: str,
    formula: str,
    inputs_used: List[Dict[str, Any]],
    basis: str,
    confidence: str,
    warnings: Sequence[str],
    source_artifacts: Sequence[str],
) -> None:
    ratios[name] = RatioItem(
        ratio_name=name,
        value=round(float(value), 4) if isinstance(value, (int, float)) else None,
        unit=unit,
        formula=formula,
        inputs_used=list(inputs_used),
        basis=basis,
        confidence=confidence,
        warnings=list(warnings),
        source_artifacts=list(source_artifacts),
    )


def _safe_divide(numerator: Optional[float], denominator: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    if numerator is None or denominator is None:
        return None, "missing inputs"
    if denominator == 0:
        return None, "division by zero"
    return numerator / denominator, None


def _normalize_label(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split())


def _period_year(period: str) -> Optional[int]:
    years = [int(item) for item in re.findall(r"(?:19|20)\d{2}", str(period or ""))]
    return years[-1] if years else None


def _target_period_year(year: str) -> Optional[int]:
    match = re.search(r"fy\s*(\d{2,4})", str(year or "").lower())
    if not match:
        return None
    value = int(match.group(1))
    return 2000 + value if value < 100 else value


def _is_monetary_entry(entry_payload: Dict[str, Any]) -> bool:
    if _value(entry_payload) is None:
        return False
    unit = str(entry_payload.get("unit_original") or "").lower()
    if not unit:
        return True
    return any(token in unit for token in ("crore", "million", "lakh", "inr", "rs", "₹"))


def _working_capital_denominator_warning(
    *,
    ratio_name: str,
    numerator: Optional[float],
    numerator_entry: Dict[str, Any],
    denominator: Optional[float],
    denominator_entry: Dict[str, Any],
    preferred_basis: str,
    target_year: str,
) -> Optional[str]:
    if numerator is None or denominator is None:
        return None
    numerator_basis = str(numerator_entry.get("basis") or "unknown")
    denominator_basis = str(denominator_entry.get("basis") or "unknown")
    if numerator_basis != "unknown" and denominator_basis != "unknown" and numerator_basis != denominator_basis:
        return f"{ratio_name} unavailable: numerator and denominator basis mismatch"
    if denominator_basis not in {preferred_basis, "unknown"}:
        return f"{ratio_name} unavailable: denominator basis is not the preferred basis"

    expected_year = _target_period_year(target_year)
    denominator_year = _period_year(str(denominator_entry.get("period") or ""))
    if expected_year is not None and denominator_year is not None and denominator_year != expected_year:
        return f"{ratio_name} unavailable: denominator period does not match fiscal year"

    if not _is_monetary_entry(numerator_entry) or not _is_monetary_entry(denominator_entry):
        return f"{ratio_name} unavailable: numerator and denominator units are not compatible monetary values"

    label = _normalize_label(str(denominator_entry.get("source_line_item") or ""))
    if ratio_name in {"inventory_days", "payable_days"}:
        if "stores and spare parts" in label or "stores and spares" in label or "spare parts" in label:
            return f"{ratio_name} unavailable: denominator is stores/spares consumption, not a compatible purchases or COGS base"
        compatible_tokens = (
            "cost of materials consumed",
            "cost of materials",
            "cost of goods sold",
            "cogs",
            "purchases of stock in trade",
            "purchases of stock-in-trade",
            "supplier purchases",
            "raw material consumed",
            "materials consumed",
        )
        if not any(token in label for token in compatible_tokens):
            return f"{ratio_name} unavailable: denominator is not a compatible purchases or COGS base"

    implied_days = (numerator / denominator) * 365 if denominator else None
    if implied_days is not None and implied_days > 730:
        return f"{ratio_name} unavailable: denominator produces implausible working-capital days"
    return None


def _confidence_from_inputs(*values: Optional[float], closing_only: bool = False) -> str:
    if any(value is None for value in values):
        return "low"
    return "medium" if closing_only else "high"


def _comparative_value(entry_payload: Dict[str, Any], *, prefer_original_numeric: bool = False) -> Optional[float]:
    comparatives = entry_payload.get("comparatives", [])
    if not isinstance(comparatives, list) or not comparatives:
        return None
    first = comparatives[0]
    if not isinstance(first, dict):
        return None
    value = first.get("value_crore")
    if isinstance(value, (int, float)) and not prefer_original_numeric:
        return float(value)
    if prefer_original_numeric:
        if isinstance(first.get("value_per_share"), (int, float)):
            return float(first["value_per_share"])
        if isinstance(first.get("value_shares"), (int, float)):
            return float(first["value_shares"])
        raw = str(first.get("value_original", "")).strip().replace(",", "")
        if not raw:
            return None
        negative = raw.startswith("(") or raw.startswith("[") or raw.startswith("-")
        raw = raw.strip("()[]")
        if raw.startswith("-"):
            raw = raw[1:]
        try:
            numeric = float(raw)
        except ValueError:
            return None
        return -numeric if negative else numeric
    return None


def _average_or_closing(entry_payload: Dict[str, Any], warnings: List[str], *, prefer_original_numeric: bool = False) -> Tuple[Optional[float], bool]:
    closing = _value(entry_payload, prefer_original_numeric=prefer_original_numeric)
    prior = _comparative_value(entry_payload, prefer_original_numeric=prefer_original_numeric)
    if closing is None:
        return None, False
    if prior is None:
        _append_unique(warnings, "used closing value because prior-year average was unavailable")
        return closing, True
    return (closing + prior) / 2.0, False


def _capital_employed_values(normalized_payload: Dict[str, Any], warnings: List[str]) -> Tuple[Optional[float], bool]:
    net_worth_entry = _entry(normalized_payload, "balance_sheet", "net_worth")
    debt_entry = _entry(normalized_payload, "balance_sheet", "total_debt")
    cash_entry = _entry(normalized_payload, "balance_sheet", "cash_and_equivalents")

    current_equity = _value(net_worth_entry)
    current_debt = _value(debt_entry)
    current_cash = _value(cash_entry) or 0.0
    if current_equity is None or current_debt is None:
        return None, False
    current_capital = current_equity + current_debt - current_cash

    prior_equity = _comparative_value(net_worth_entry)
    prior_debt = _comparative_value(debt_entry)
    prior_cash = _comparative_value(cash_entry) or 0.0
    if prior_equity is None or prior_debt is None:
        _append_unique(warnings, "used closing capital employed because prior-year average was unavailable")
        return current_capital, True
    prior_capital = prior_equity + prior_debt - prior_cash
    return (current_capital + prior_capital) / 2.0, False


def _fcf_from(
    cfo: Optional[float],
    capex: Optional[float],
    warnings: List[str],
    *,
    sign_convention: str = "",
) -> Optional[float]:
    if cfo is None or capex is None:
        return None
    if sign_convention == "positive_outflow":
        _append_unique(warnings, "capex treated as positive outflow during FCF calculation")
        return cfo - capex
    if capex <= 0 or sign_convention == "cash_flow_signed":
        return cfo + capex
    _append_unique(warnings, "capex treated as positive outflow during FCF calculation")
    return cfo - capex


def calculate_financial_ratios(
    *,
    company: str,
    year: str,
    normalized_path: Path,
    reconciliation_path: Path,
) -> FinancialRatioReport:
    normalized = _load_json(normalized_path)
    reconciliation = _load_json(reconciliation_path)

    reconciliation_failures = reconciliation_blocks_stage(
        reconciliation,
        required_fields=sorted(CRITICAL_RECONCILIATION_FIELDS),
    )
    if reconciliation_failures:
        raise RuntimeError(
            "financial_ratios requires reconciled normalized fundamentals; blocking reconciliation failures: "
            + "; ".join(reconciliation_failures)
        )

    revenue_entry = _entry(normalized, "profit_and_loss", "revenue")
    pat_entry = _entry(normalized, "profit_and_loss", "pat")
    ebitda_entry = _entry(normalized, "profit_and_loss", "ebitda")
    ebit_entry = _entry(normalized, "profit_and_loss", "ebit")
    finance_cost_entry = _entry(normalized, "profit_and_loss", "finance_cost")
    cost_entry = _entry(normalized, "profit_and_loss", "cost_of_materials")
    net_worth_entry = _entry(normalized, "balance_sheet", "net_worth")
    total_assets_entry = _entry(normalized, "balance_sheet", "total_assets")
    debt_entry = _entry(normalized, "balance_sheet", "total_debt")
    cash_entry = _entry(normalized, "balance_sheet", "cash_and_equivalents")
    receivables_entry = _entry(normalized, "balance_sheet", "receivables")
    inventory_entry = _entry(normalized, "balance_sheet", "inventories")
    payables_entry = _entry(normalized, "balance_sheet", "payables")
    cfo_entry = _entry(normalized, "cash_flow", "cfo")
    capex_entry = _entry(normalized, "cash_flow", "capex")
    dividends_entry = _entry(normalized, "cash_flow", "dividends_paid")
    eps_basic_entry = _entry(normalized, "profit_and_loss", "eps_basic")
    eps_diluted_entry = _entry(normalized, "profit_and_loss", "eps_diluted")
    shares_entry = _entry(normalized, "share_data", "shares_outstanding")
    diluted_shares_entry = _entry(normalized, "share_data", "diluted_shares")

    revenue = _value(revenue_entry)
    pat = _value(pat_entry)
    if revenue is None:
        raise RuntimeError("financial_ratios requires revenue in normalized fundamentals")
    if pat is None:
        raise RuntimeError("financial_ratios requires PAT in normalized fundamentals")

    basis = _basis_from_normalized(normalized)
    report_warnings: List[str] = []
    ratios: Dict[str, RatioItem] = {name: _empty_ratio(name) for name in RATIO_FIELDS}

    cost_of_materials = _value(cost_entry)
    gross_profit = (revenue - cost_of_materials) if revenue is not None and cost_of_materials is not None else None
    gross_result, gross_issue = _safe_divide(gross_profit, revenue)
    _set_ratio(
        ratios,
        "gross_margin",
        value=gross_result * 100 if gross_result is not None else None,
        unit="%",
        formula="(revenue - cost_of_materials) / revenue * 100",
        inputs_used=[_input_item("revenue", revenue, "₹ crore"), _input_item("cost_of_materials", cost_of_materials, "₹ crore")],
        basis=basis,
        confidence=_confidence_from_inputs(gross_profit, revenue),
        warnings=[gross_issue] if gross_issue else [],
        source_artifacts=_source_artifacts(revenue_entry, cost_entry),
    )

    for name, entry_payload, numerator_name in (
        ("ebitda_margin", ebitda_entry, "ebitda"),
        ("ebit_margin", ebit_entry, "ebit"),
        ("opm", ebit_entry, "ebit"),
        ("npm", pat_entry, "pat"),
    ):
        numerator = _value(entry_payload)
        result, issue = _safe_divide(numerator, revenue)
        _set_ratio(
            ratios,
            name,
            value=result * 100 if result is not None else None,
            unit="%",
            formula=f"{numerator_name} / revenue * 100",
            inputs_used=[_input_item(numerator_name, numerator, "₹ crore"), _input_item("revenue", revenue, "₹ crore")],
            basis=basis,
            confidence=_confidence_from_inputs(numerator, revenue),
            warnings=[issue] if issue else [],
            source_artifacts=_source_artifacts(entry_payload, revenue_entry),
        )

    roe_warnings: List[str] = []
    avg_equity, roe_closing_only = _average_or_closing(net_worth_entry, roe_warnings)
    roa_warnings: List[str] = []
    avg_assets, roa_closing_only = _average_or_closing(total_assets_entry, roa_warnings)
    roce_warnings: List[str] = []
    avg_capital, roce_closing_only = _capital_employed_values(normalized, roce_warnings)

    for warning in roe_warnings + roa_warnings + roce_warnings:
        _append_unique(report_warnings, warning)

    for name, numerator, denominator, formula, extra_warnings, closing_only, entry_payloads in (
        ("roe", pat, avg_equity, "pat / average_net_worth * 100", roe_warnings, roe_closing_only, [pat_entry, net_worth_entry]),
        ("roa", pat, avg_assets, "pat / average_total_assets * 100", roa_warnings, roa_closing_only, [pat_entry, total_assets_entry]),
        ("roce", _value(ebit_entry), avg_capital, "ebit / average_capital_employed * 100", roce_warnings, roce_closing_only, [ebit_entry, net_worth_entry, debt_entry, cash_entry]),
    ):
        result, issue = _safe_divide(numerator, denominator)
        _set_ratio(
            ratios,
            name,
            value=result * 100 if result is not None else None,
            unit="%",
            formula=formula,
            inputs_used=[_input_item("numerator", numerator, "₹ crore"), _input_item("denominator", denominator, "₹ crore")],
            basis=basis,
            confidence=_confidence_from_inputs(numerator, denominator, closing_only=closing_only),
            warnings=list(extra_warnings) + ([issue] if issue else []),
            source_artifacts=_source_artifacts(*entry_payloads),
        )

    debt = _value(debt_entry)
    cash = _value(cash_entry)
    net_worth = _value(net_worth_entry)
    net_debt_warnings: List[str] = []
    net_debt = _fcf_from(debt, -cash if cash is not None else None, net_debt_warnings) if debt is not None else None
    for warning in net_debt_warnings:
        _append_unique(report_warnings, warning)
    _set_ratio(
        ratios,
        "net_debt",
        value=net_debt,
        unit="₹ crore",
        formula="total_debt - cash_and_equivalents",
        inputs_used=[_input_item("total_debt", debt, "₹ crore"), _input_item("cash_and_equivalents", cash, "₹ crore")],
        basis=basis,
        confidence=_confidence_from_inputs(debt, cash),
        warnings=net_debt_warnings,
        source_artifacts=_source_artifacts(debt_entry, cash_entry),
    )

    for name, numerator, denominator, formula, payloads in (
        ("debt_to_equity", debt, net_worth, "total_debt / net_worth", [debt_entry, net_worth_entry]),
        ("net_debt_to_equity", net_debt, net_worth, "net_debt / net_worth", [debt_entry, cash_entry, net_worth_entry]),
        ("interest_coverage", _value(ebit_entry), _value(finance_cost_entry), "ebit / finance_cost", [ebit_entry, finance_cost_entry]),
    ):
        result, issue = _safe_divide(numerator, denominator)
        _set_ratio(
            ratios,
            name,
            value=result,
            unit="x",
            formula=formula,
            inputs_used=[_input_item("numerator", numerator, "₹ crore"), _input_item("denominator", denominator, "₹ crore")],
            basis=basis,
            confidence=_confidence_from_inputs(numerator, denominator),
            warnings=[issue] if issue else [],
            source_artifacts=_source_artifacts(*payloads),
        )

    cfo = _value(cfo_entry)
    capex = _value(capex_entry)
    capex_sign_convention = str(capex_entry.get("sign_convention", "") or "")
    if cfo is None:
        _append_unique(report_warnings, "CFO missing")
    if capex is None:
        _append_unique(report_warnings, "capex missing")
    fcf_warnings: List[str] = []
    fcf = _fcf_from(cfo, capex, fcf_warnings, sign_convention=capex_sign_convention)
    for warning in fcf_warnings:
        _append_unique(report_warnings, warning)
    _set_ratio(
        ratios,
        "fcf",
        value=fcf,
        unit="₹ crore",
        formula="cfo + capex (or cfo - capex when capex sign is positive outflow)",
        inputs_used=[
            _input_item("cfo", cfo, "₹ crore"),
            _input_item("capex", capex, "₹ crore"),
            {"name": "capex_sign_convention", "value": capex_sign_convention or "unknown", "unit": "metadata"},
        ],
        basis=basis,
        confidence=_confidence_from_inputs(cfo, capex),
        warnings=fcf_warnings,
        source_artifacts=_source_artifacts(cfo_entry, capex_entry),
    )

    for name, numerator, denominator, formula, unit in (
        ("cfo_to_pat", cfo, pat, "cfo / pat", "x"),
        ("fcf_to_pat", fcf, pat, "fcf / pat", "x"),
        ("fcf_margin", fcf, revenue, "fcf / revenue * 100", "%"),
    ):
        result, issue = _safe_divide(numerator, denominator)
        _set_ratio(
            ratios,
            name,
            value=result * 100 if name == "fcf_margin" and result is not None else result,
            unit=unit,
            formula=formula,
            inputs_used=[_input_item("numerator", numerator, "₹ crore"), _input_item("denominator", denominator, "₹ crore")],
            basis=basis,
            confidence=_confidence_from_inputs(numerator, denominator),
            warnings=[issue] if issue else [],
            source_artifacts=_source_artifacts(cfo_entry if name == "cfo_to_pat" else cfo_entry, capex_entry if name != "cfo_to_pat" else pat_entry, pat_entry, revenue_entry),
        )

    wc_warnings: List[str] = []
    avg_receivables, recv_closing_only = _average_or_closing(receivables_entry, wc_warnings)
    avg_inventory, inv_closing_only = _average_or_closing(inventory_entry, wc_warnings)
    avg_payables, pay_closing_only = _average_or_closing(payables_entry, wc_warnings)
    for warning in wc_warnings:
        _append_unique(report_warnings, warning)

    for name, numerator, denominator, formula, source_entries, closing_only in (
        ("receivable_days", avg_receivables, revenue, "average_receivables / revenue * 365", [receivables_entry, revenue_entry], recv_closing_only),
        ("inventory_days", avg_inventory, cost_of_materials, "average_inventory / cost_of_materials * 365", [inventory_entry, cost_entry], inv_closing_only),
        ("payable_days", avg_payables, cost_of_materials, "average_payables / cost_of_materials * 365", [payables_entry, cost_entry], pay_closing_only),
    ):
        compatibility_issue = None
        if name == "inventory_days":
            compatibility_issue = _working_capital_denominator_warning(
                ratio_name=name,
                numerator=numerator,
                numerator_entry=inventory_entry,
                denominator=denominator,
                denominator_entry=cost_entry,
                preferred_basis=basis,
                target_year=year,
            )
        elif name == "payable_days":
            compatibility_issue = _working_capital_denominator_warning(
                ratio_name=name,
                numerator=numerator,
                numerator_entry=payables_entry,
                denominator=denominator,
                denominator_entry=cost_entry,
                preferred_basis=basis,
                target_year=year,
            )
        result, issue = (None, compatibility_issue) if compatibility_issue else _safe_divide(numerator, denominator)
        ratio_warnings = [issue] if issue else []
        if result is not None and closing_only:
            ratio_warnings.append("used closing value because prior-year average was unavailable")
        _set_ratio(
            ratios,
            name,
            value=result * 365 if result is not None else None,
            unit="days",
            formula=formula,
            inputs_used=[_input_item("numerator", numerator, "₹ crore"), _input_item("denominator", denominator, "₹ crore")],
            basis=basis,
            confidence="low" if result is None else _confidence_from_inputs(numerator, denominator, closing_only=closing_only),
            warnings=ratio_warnings,
            source_artifacts=_source_artifacts(*source_entries),
        )

    rec_days = ratios["receivable_days"].value
    inv_days = ratios["inventory_days"].value
    pay_days = ratios["payable_days"].value
    ccc_warnings: List[str] = []
    ccc = None if rec_days is None or inv_days is None or pay_days is None else rec_days + inv_days - pay_days
    if ccc is None:
        ccc_warnings.append("missing working capital fields")
        _append_unique(report_warnings, "working capital fields missing")
    _set_ratio(
        ratios,
        "cash_conversion_cycle",
        value=ccc,
        unit="days",
        formula="receivable_days + inventory_days - payable_days",
        inputs_used=[
            _input_item("receivable_days", rec_days, "days"),
            _input_item("inventory_days", inv_days, "days"),
            _input_item("payable_days", pay_days, "days"),
        ],
        basis=basis,
        confidence="medium" if ccc is not None else "low",
        warnings=ccc_warnings,
        source_artifacts=[],
    )

    eps_basic = _value(eps_basic_entry, prefer_original_numeric=True)
    eps_diluted = _value(eps_diluted_entry, prefer_original_numeric=True)
    shares_outstanding = _value(shares_entry, prefer_original_numeric=True)
    diluted_shares = _value(diluted_shares_entry, prefer_original_numeric=True)
    if shares_outstanding is None and diluted_shares is None:
        _append_unique(report_warnings, "share count missing")

    _set_ratio(
        ratios,
        "eps_basic",
        value=eps_basic,
        unit="₹/share",
        formula="reconciled basic EPS",
        inputs_used=[_input_item("eps_basic", eps_basic, "₹/share")],
        basis=basis,
        confidence="high" if eps_basic is not None else "low",
        warnings=[] if eps_basic is not None else ["missing inputs"],
        source_artifacts=_source_artifacts(eps_basic_entry),
    )
    _set_ratio(
        ratios,
        "eps_diluted",
        value=eps_diluted,
        unit="₹/share",
        formula="reconciled diluted EPS",
        inputs_used=[_input_item("eps_diluted", eps_diluted, "₹/share")],
        basis=basis,
        confidence="high" if eps_diluted is not None else "low",
        warnings=[] if eps_diluted is not None else ["missing inputs"],
        source_artifacts=_source_artifacts(eps_diluted_entry),
    )

    bvps_value = None
    bvps_issue = None
    if net_worth is not None and shares_outstanding not in (None, 0):
        bvps_value = (net_worth * 10_000_000) / shares_outstanding
    elif shares_outstanding == 0:
        bvps_issue = "division by zero"
    else:
        bvps_issue = "missing inputs"
    _set_ratio(
        ratios,
        "book_value_per_share",
        value=bvps_value,
        unit="₹/share",
        formula="net_worth * 1e7 / shares_outstanding",
        inputs_used=[_input_item("net_worth", net_worth, "₹ crore"), _input_item("shares_outstanding", shares_outstanding, "shares")],
        basis=basis,
        confidence=_confidence_from_inputs(net_worth, shares_outstanding),
        warnings=[bvps_issue] if bvps_issue else [],
        source_artifacts=_source_artifacts(net_worth_entry, shares_entry),
    )

    _set_ratio(
        ratios,
        "tangible_book_value_per_share",
        value=None,
        unit="₹/share",
        formula="not available from current normalized fundamentals",
        inputs_used=[],
        basis=basis,
        confidence="low",
        warnings=["missing inputs"],
        source_artifacts=[],
    )

    dividend_amount = abs(_value(dividends_entry)) if _value(dividends_entry) is not None else None
    shares_for_dividend = shares_outstanding
    dividend_per_share = None
    dps_issue = None
    if dividend_amount is not None and shares_for_dividend not in (None, 0):
        dividend_per_share = (dividend_amount * 10_000_000) / shares_for_dividend
    elif dividend_amount is None:
        dps_issue = "missing dividend input"
    elif shares_for_dividend == 0:
        dps_issue = "division by zero"
    else:
        dps_issue = "share count missing"
    _set_ratio(
        ratios,
        "dividend_per_share",
        value=dividend_per_share,
        unit="₹/share",
        formula="abs(dividends_paid) * 1e7 / shares_outstanding",
        inputs_used=[_input_item("dividends_paid", dividend_amount, "₹ crore"), _input_item("shares_outstanding", shares_for_dividend, "shares")],
        basis=basis,
        confidence=_confidence_from_inputs(dividend_amount, shares_for_dividend),
        warnings=[dps_issue] if dps_issue else [],
        source_artifacts=_source_artifacts(dividends_entry, shares_entry),
    )

    payout, payout_issue = _safe_divide(dividend_amount, pat)
    _set_ratio(
        ratios,
        "payout_ratio",
        value=payout * 100 if payout is not None else None,
        unit="%",
        formula="abs(dividends_paid) / pat * 100",
        inputs_used=[_input_item("dividends_paid", dividend_amount, "₹ crore"), _input_item("pat", pat, "₹ crore")],
        basis=basis,
        confidence=_confidence_from_inputs(dividend_amount, pat),
        warnings=[payout_issue] if payout_issue else [],
        source_artifacts=_source_artifacts(dividends_entry, pat_entry),
    )

    status = "warning" if report_warnings or any(item.warnings for item in ratios.values()) else "pass"
    report = FinancialRatioReport(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        status=status,
        basis_used=basis if basis in {"standalone", "consolidated", "unknown"} else "mixed",
        basis_confidence=_basis_confidence_from_normalized(normalized),
        basis_warnings=_basis_warnings_from_normalized(normalized),
        warnings=report_warnings,
        ratios=ratios,
        limitations=[
            "Financial ratios are calculated deterministically from reconciled normalized fundamentals only.",
            "Average-based return and working-capital ratios fall back to closing balances when prior-year normalized comparatives are unavailable.",
        ],
    )
    errors = validate_financial_ratio_report_payload(report.to_dict())
    if errors:
        raise ValueError("; ".join(errors))
    return report


def write_financial_ratios(
    *,
    company: str,
    year: str,
    normalized_path: Path,
    reconciliation_path: Path,
    output_path: Path,
) -> FinancialRatioReport:
    report = calculate_financial_ratios(
        company=company,
        year=year,
        normalized_path=normalized_path,
        reconciliation_path=reconciliation_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return report
