from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .fact_registry_schema import (
    FinancialArtifactQuarantineReport,
    FinancialFact,
    FinancialFactRegistry,
    FinancialTruthReconciliationReport,
    validate_financial_artifact_quarantine_payload,
    validate_financial_fact_registry_payload,
    validate_financial_truth_reconciliation_payload,
)


ARTIFACT_FILENAMES = (
    "normalized_fundamentals.json",
    "raw_financial_tables.json",
    "financial_ratios.json",
    "financial_growth.json",
    "financial_validation_report.json",
    "financial_reconciliation_report.json",
    "financial_quality_summary.json",
    "corporate_actions.json",
    "shareholding_pattern.json",
)

CAPEX_PPE_PATTERNS = (
    "property plant and equipment",
    "ppe",
    "fixed assets",
    "capital work in progress",
    "cwip",
    "plant and equipment",
)
CAPEX_INTANGIBLE_PATTERNS = (
    "intangible",
    "product development",
    "development cost",
    "software",
)
CAPITALIZED_PRODUCT_DEVELOPMENT_PATTERNS = (
    "capitalized product development",
    "capitalised product development",
    "capitalised development cost",
    "capitalized development cost",
)
CAPITAL_COMMITMENT_PATTERNS = (
    "capital commitment",
    "capital commitments",
)
MAINTENANCE_CAPEX_PATTERNS = (
    "maintenance capex",
    "maintenance capital expenditure",
)
GROWTH_CAPEX_PATTERNS = (
    "growth capex",
    "expansion capex",
    "growth capital expenditure",
)

SOURCE_RANK = {
    "normalized_direct": 50,
    "normalized_derived": 45,
    "validated_note_derived": 40,
    "ratio_or_growth_derived": 30,
    "financial_summary_interpretation": 10,
}

METRIC_NAME_MAP = {
    "cfo": "Cash From Operations",
    "capex": "Capital Expenditure",
    "capex_ppe_cwip_cash_outflow": "PPE/CWIP Capex Cash Outflow",
    "capex_intangible_cash_outflow": "Intangible Capex Cash Outflow",
    "capitalized_product_development": "Capitalized Product Development",
    "gross_block_additions": "Gross Block Additions",
    "capital_commitments": "Capital Commitments",
    "total_capex_for_fcf": "Total Capex For FCF",
    "total_growth_or_expansion_capex": "Total Growth Or Expansion Capex",
    "fcf": "Free Cash Flow",
    "fcf_explicitly_reported": "FCF Explicitly Reported",
    "fcf_computable": "FCF Computable",
    "fcf_after_ppe_cwip_capex": "FCF After PPE/CWIP Capex",
    "fcf_after_total_identified_capex": "FCF After Total Identified Capex",
    "fcf_formula_used": "FCF Formula Used",
    "fcf_inputs_used": "FCF Inputs Used",
    "fcf_confidence": "FCF Confidence",
    "payables": "Trade Payables",
    "trade_payables": "Trade Payables",
    "payables_current": "Current Payables",
    "payables_non_current": "Non-current Payables",
    "capital_creditors": "Capital Creditors",
    "payable_days": "Payable Days",
    "payable_turnover": "Payable Turnover",
    "cash_conversion_cycle": "Cash Conversion Cycle",
    "working_capital_data_status": "Working Capital Data Status",
    "roe": "Return on Equity",
    "roce": "Return on Capital Employed",
    "borrowings": "Borrowings",
    "lease_liabilities": "Lease Liabilities",
    "gross_debt": "Gross Debt",
    "net_debt": "Net Debt",
    "debt_source_reliability": "Debt Source Reliability",
    "debt_reconciliation_status": "Debt Reconciliation Status",
    "opening_shares": "Opening Shares",
    "closing_shares": "Closing Shares",
    "weighted_average_basic_shares": "Weighted Average Basic Shares",
    "weighted_average_diluted_shares": "Weighted Average Diluted Shares",
    "weighted_avg_shares": "Weighted Average Shares",
    "shares_outstanding": "Shares Outstanding",
    "share_count_status": "Share Count Status",
    "eps_comparability_status": "EPS Comparability Status",
    "dilution_status": "Dilution Status",
    "fcf_per_share": "FCF Per Share",
    "dividend_per_share": "Dividend Per Share",
}

TEXT_ALIAS_MAP = {
    "fcf": ("free cash flow", "fcf"),
    "payables": ("payables", "trade payables", "payable days", "payable-days", "payable turnover"),
    "roe": ("roe", "return on equity"),
    "roce": ("roce", "return on capital employed"),
    "total_debt": ("debt", "total debt", "borrowings"),
    "gross_debt": ("debt", "gross debt", "borrowings"),
    "net_debt": ("net debt", "debt"),
    "debt_to_equity": ("debt to equity", "debt/equity", "debt equity"),
    "weighted_avg_shares": ("weighted average shares", "weighted-average shares", "weighted average basic shares"),
    "weighted_average_basic_shares": ("weighted average basic shares", "weighted average shares", "weighted-average shares"),
    "weighted_average_diluted_shares": ("weighted average diluted shares", "diluted shares"),
    "shares_outstanding": ("share count", "shares outstanding", "closing shares"),
    "closing_shares": ("closing shares", "shares outstanding", "share count"),
}


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _append_unique(items: List[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _canonical_metric_name(metric_id: str) -> str:
    return METRIC_NAME_MAP.get(metric_id, metric_id.replace("_", " ").title())


def _infer_fact_value(entry: Dict[str, Any]) -> Tuple[float | None, str, str]:
    value_type = str(entry.get("value_type") or entry.get("source_value_type") or "").strip().lower()
    if value_type == "per_share":
        value = entry.get("value_per_share")
        if value is None:
            value = entry.get("value")
        if value is None:
            value = entry.get("value_original")
        try:
            return (float(value), str(entry.get("unit_original") or "per share"), "per_share")
        except (TypeError, ValueError):
            return (None, str(entry.get("unit_original") or "per share"), "per_share")
    if value_type == "share_count":
        value = entry.get("value_shares")
        if value is None:
            value = entry.get("raw_number")
        if value is None:
            value = entry.get("crore_shares")
        unit = "shares" if entry.get("value_shares") is not None or entry.get("raw_number") is not None else "crore shares"
        try:
            return (float(value), unit, "share_count")
        except (TypeError, ValueError):
            return (None, unit, "share_count")
    value = entry.get("value_crore")
    try:
        return (float(value), "INR crore", "monetary")
    except (TypeError, ValueError):
        return (None, "INR crore", "monetary")


def _availability_status(*, value: float | None, derived: bool, confidence: str) -> str:
    if confidence == "invalid":
        return "invalid"
    if confidence == "unreliable":
        return "unreliable"
    if value is None:
        return "missing"
    return "present_derived" if derived else "present_direct"


def _reconciliation_map(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    checks = payload.get("checks")
    return checks if isinstance(checks, dict) else {}


def _metric_alias_candidates(metric_id: str) -> Iterable[str]:
    yield metric_id
    for alias in TEXT_ALIAS_MAP.get(metric_id, ()):
        yield alias


def _warning_mentions_metric(text: str, metric_id: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(alias in lowered for alias in _metric_alias_candidates(metric_id))


def _warning_claims_missing(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    return any(token in lowered for token in ("missing", "unavailable", "cannot be assessed", "not available"))


def _warning_claims_available(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    return any(token in lowered for token in ("available", "present", "usable"))


def _contains_pattern(text: str, patterns: Iterable[str]) -> bool:
    lowered = _normalize(text)
    return any(pattern in lowered for pattern in patterns)


def _normalize(text: str) -> str:
    return " ".join(str(text or "").lower().replace("/", " ").replace("-", " ").split())


def _source_rank(fact: FinancialFact) -> int:
    if fact.source_artifact == "normalized_fundamentals.json":
        return SOURCE_RANK["normalized_derived" if fact.derived else "normalized_direct"]
    if fact.source_artifact in {"financial_ratios.json", "financial_growth.json"}:
        return SOURCE_RANK["ratio_or_growth_derived"]
    return SOURCE_RANK["financial_summary_interpretation"]


def _pick_best_fact(facts: List[FinancialFact]) -> FinancialFact:
    return sorted(
        facts,
        key=lambda fact: (
            1 if fact.usable_downstream else 0,
            1 if fact.availability_status == "present_direct" else 0,
            1 if fact.availability_status == "present_derived" else 0,
            _source_rank(fact),
        ),
        reverse=True,
    )[0]


def _is_near_integer(value: float | None, tolerance: float = 0.05) -> bool:
    if value is None:
        return False
    return abs(value - round(value)) <= tolerance


def _is_valid_percentage(value: float | None) -> bool:
    return value is not None and 0.0 <= value <= 100.0


def _append_quarantine_finding(
    findings: List[Dict[str, Any]],
    *,
    artifact_name: str,
    domain: str,
    metric_id: str,
    status: str,
    usable_downstream: bool,
    invalid_reason: str,
    source_line_item: str,
    source_artifact: str,
    invalid_fields: List[str] | None = None,
    reliable_fields: List[str] | None = None,
    warnings_to_block_downstream: List[str] | None = None,
    warnings_allowed_downstream: List[str] | None = None,
) -> None:
    findings.append(
        {
            "artifact_name": artifact_name,
            "domain": domain,
            "metric_id": metric_id,
            "status": status,
            "usable_downstream": usable_downstream,
            "invalid_reason": invalid_reason,
            "source_line_item": source_line_item,
            "source_artifact": source_artifact,
            "invalid_fields": list(invalid_fields or []),
            "reliable_fields": list(reliable_fields or []),
            "warnings_to_block_downstream": list(warnings_to_block_downstream or []),
            "warnings_allowed_downstream": list(warnings_allowed_downstream or []),
        }
    )


def _build_fact_from_normalized(
    *,
    metric_id: str,
    fiscal_year: str,
    section_name: str,
    entry: Dict[str, Any],
    reconciliation: Dict[str, Any] | None,
) -> FinancialFact:
    value, unit, _value_type = _infer_fact_value(entry)
    confidence = str(entry.get("confidence") or ("missing" if value is None else "medium"))
    warnings = [str(item) for item in entry.get("warnings", []) if str(item or "").strip()]
    derived = bool(entry.get("derived"))
    reconciliation_status = "unknown"
    usable_downstream = value is not None and confidence not in {"invalid", "unreliable"}
    if isinstance(reconciliation, dict):
        reconciliation_status = str(reconciliation.get("status") or "unknown")
        if reconciliation_status == "fail":
            confidence = "unreliable"
            usable_downstream = False
            _append_unique(warnings, str(reconciliation.get("reason") or "reconciliation failed"))
        elif reconciliation_status == "warning":
            _append_unique(warnings, str(reconciliation.get("reason") or "reconciliation warning"))
    availability = _availability_status(value=value, derived=derived, confidence=confidence)
    return FinancialFact(
        metric_id=metric_id,
        metric_name=_canonical_metric_name(metric_id),
        fiscal_year=fiscal_year,
        period=str(entry.get("period") or fiscal_year),
        value=value,
        unit=unit,
        basis=str(entry.get("basis") or "unknown"),
        source_statement=str(entry.get("statement_type") or section_name),
        source_artifact="normalized_fundamentals.json",
        source_line_item=str(entry.get("source_line_item") or ""),
        source_page=entry.get("source_page"),
        confidence=confidence if confidence in {"high", "medium", "low", "missing", "invalid", "unreliable"} else "medium",
        availability_status=availability,
        derived=derived,
        formula=str(entry.get("formula") or ""),
        inputs_used=[str(item) for item in entry.get("inputs_used", []) if str(item or "").strip()],
        warnings=warnings,
        reconciliation_status=reconciliation_status,
        usable_downstream=usable_downstream and availability in {"present_direct", "present_derived"},
        notes=[str(item) for item in entry.get("notes", []) if str(item or "").strip()],
    )


def _derive_fcf_if_possible(facts_by_metric: Dict[str, List[FinancialFact]], fiscal_year: str) -> FinancialFact | None:
    if facts_by_metric.get("fcf"):
        best = _pick_best_fact(facts_by_metric["fcf"])
        if best.availability_status in {"present_direct", "present_derived"}:
            return None
    cfo_facts = facts_by_metric.get("cfo", [])
    capex_facts = facts_by_metric.get("capex", [])
    if not cfo_facts or not capex_facts:
        return None
    cfo = _pick_best_fact(cfo_facts)
    capex = _pick_best_fact(capex_facts)
    if cfo.value is None or capex.value is None:
        return None
    derived_value = cfo.value + capex.value if capex.value < 0 else cfo.value - capex.value
    warnings: List[str] = []
    if capex.value >= 0:
        warnings.append("Capex sign convention assumed as positive outflow during FCF derivation.")
    return FinancialFact(
        metric_id="fcf",
        metric_name=_canonical_metric_name("fcf"),
        fiscal_year=fiscal_year,
        period=fiscal_year,
        value=derived_value,
        unit="INR crore",
        basis=cfo.basis if cfo.basis == capex.basis else "unknown",
        source_statement="derived_from_normalized_fundamentals",
        source_artifact="normalized_fundamentals.json",
        source_line_item="derived:fcf",
        source_page=None,
        confidence="medium",
        availability_status="present_derived",
        derived=True,
        formula="cfo + capex if capex is cash-flow signed, else cfo - capex",
        inputs_used=["cfo", "capex"],
        warnings=warnings,
        reconciliation_status="pass" if cfo.usable_downstream and capex.usable_downstream else "warning",
        usable_downstream=cfo.usable_downstream and capex.usable_downstream,
        notes=["Derived deterministically from normalized CFO and capex."],
    )


def _derive_payables_proxy(facts_by_metric: Dict[str, List[FinancialFact]], fiscal_year: str) -> FinancialFact | None:
    if facts_by_metric.get("payables"):
        best = _pick_best_fact(facts_by_metric["payables"])
        if best.availability_status in {"present_direct", "present_derived"}:
            return None
    payable_days_facts = facts_by_metric.get("payable_days", [])
    if not payable_days_facts:
        return None
    proxy = _pick_best_fact(payable_days_facts)
    if proxy.value is None:
        return None
    return FinancialFact(
        metric_id="payables",
        metric_name=_canonical_metric_name("payables"),
        fiscal_year=fiscal_year,
        period=fiscal_year,
        value=proxy.value,
        unit="days_proxy",
        basis=proxy.basis,
        source_statement="derived_from_financial_ratios",
        source_artifact="financial_ratios.json",
        source_line_item="derived:payables_proxy_from_payable_days",
        source_page=None,
        confidence="low",
        availability_status="present_derived",
        derived=True,
        formula="payable_days proxy implies payables evidence exists even if direct payables row is unavailable.",
        inputs_used=["payable_days"],
        warnings=["Payables amount is not available directly; registry preserves only proxy evidence from payable days."],
        reconciliation_status="warning",
        usable_downstream=False,
        notes=["This avoids classifying payables as fully missing when payable-days evidence exists."],
    )


def _derive_payable_days_from_turnover(facts_by_metric: Dict[str, List[FinancialFact]], fiscal_year: str) -> FinancialFact | None:
    if facts_by_metric.get("payable_days"):
        best = _pick_best_fact(facts_by_metric["payable_days"])
        if best.availability_status in {"present_direct", "present_derived"}:
            return None
    turnover_facts = facts_by_metric.get("payable_turnover", [])
    if not turnover_facts:
        return None
    turnover = _pick_best_fact(turnover_facts)
    if turnover.value in (None, 0):
        return None
    derived_value = 365.0 / turnover.value
    return FinancialFact(
        metric_id="payable_days",
        metric_name=_canonical_metric_name("payable_days"),
        fiscal_year=fiscal_year,
        period=fiscal_year,
        value=derived_value,
        unit="days",
        basis=turnover.basis,
        source_statement="derived_from_financial_ratios",
        source_artifact="financial_ratios.json",
        source_line_item="derived:payable_days_from_turnover",
        source_page=None,
        confidence="medium",
        availability_status="present_derived",
        derived=True,
        formula="365 / payable_turnover",
        inputs_used=["payable_turnover"],
        warnings=["Payable days derived from payable turnover."],
        reconciliation_status="warning",
        usable_downstream=turnover.usable_downstream,
        notes=["This avoids treating payable-days evidence as fully missing when turnover is available."],
    )


def _derive_cash_conversion_cycle(facts_by_metric: Dict[str, List[FinancialFact]], fiscal_year: str) -> FinancialFact | None:
    if facts_by_metric.get("cash_conversion_cycle"):
        best = _pick_best_fact(facts_by_metric["cash_conversion_cycle"])
        if best.availability_status in {"present_direct", "present_derived"}:
            return None
    required = {}
    for metric in ("receivable_days", "inventory_days", "payable_days"):
        items = facts_by_metric.get(metric, [])
        if not items:
            return None
        best = _pick_best_fact(items)
        if best.value is None:
            return None
        required[metric] = best
    derived_value = required["receivable_days"].value + required["inventory_days"].value - required["payable_days"].value
    usable = all(item.usable_downstream for item in required.values())
    return FinancialFact(
        metric_id="cash_conversion_cycle",
        metric_name=_canonical_metric_name("cash_conversion_cycle"),
        fiscal_year=fiscal_year,
        period=fiscal_year,
        value=derived_value,
        unit="days",
        basis=required["receivable_days"].basis,
        source_statement="derived_from_financial_ratios",
        source_artifact="financial_ratios.json",
        source_line_item="derived:cash_conversion_cycle",
        source_page=None,
        confidence="medium",
        availability_status="present_derived",
        derived=True,
        formula="receivable_days + inventory_days - payable_days",
        inputs_used=["receivable_days", "inventory_days", "payable_days"],
        warnings=["Cash conversion cycle derived from working-capital day metrics."],
        reconciliation_status="warning",
        usable_downstream=usable,
        notes=[],
    )


def _add_raw_capex_classification_facts(
    facts_by_metric: Dict[str, List[FinancialFact]],
    raw_payload: Dict[str, Any] | None,
    fiscal_year: str,
) -> None:
    if not isinstance(raw_payload, dict):
        return
    tables = raw_payload.get("tables")
    if not isinstance(tables, dict):
        return
    rows = []
    for items in tables.values():
        if isinstance(items, list):
            rows.extend(item for item in items if isinstance(item, dict))
    for row in rows:
        line_item = str(row.get("line_item_raw") or "")
        normalized = _normalize(line_item)
        values = row.get("values")
        if not isinstance(values, list) or not values:
            continue
        first = values[0] if isinstance(values[0], dict) else {}
        value = first.get("value_crore")
        if not isinstance(value, (int, float)):
            continue
        base_kwargs = dict(
            fiscal_year=fiscal_year,
            period=str(first.get("period") or fiscal_year),
            basis=str(row.get("basis") or "unknown"),
            source_statement=str(row.get("table_type") or row.get("statement_type") or "raw_financial_tables"),
            source_artifact="raw_financial_tables.json",
            source_line_item=line_item,
            source_page=row.get("page"),
            confidence=str(row.get("confidence") or "medium"),
            availability_status="present_direct",
            derived=False,
            formula="",
            inputs_used=[],
            warnings=[str(item) for item in row.get("warnings", []) if str(item).strip()],
            reconciliation_status="unknown",
            usable_downstream=True,
            notes=[],
        )
        if _contains_pattern(normalized, CAPITAL_COMMITMENT_PATTERNS):
            facts_by_metric.setdefault("capital_commitments", []).append(
                FinancialFact(metric_id="capital_commitments", metric_name=_canonical_metric_name("capital_commitments"), value=float(value), unit="INR crore", **base_kwargs)
            )
            continue
        if _contains_pattern(normalized, MAINTENANCE_CAPEX_PATTERNS):
            facts_by_metric.setdefault("maintenance_capex_disclosed", []).append(
                FinancialFact(metric_id="maintenance_capex_disclosed", metric_name="Maintenance Capex Disclosed", value=float(value), unit="INR crore", **base_kwargs)
            )
        if _contains_pattern(normalized, GROWTH_CAPEX_PATTERNS):
            facts_by_metric.setdefault("growth_capex_disclosed", []).append(
                FinancialFact(metric_id="growth_capex_disclosed", metric_name="Growth Capex Disclosed", value=float(value), unit="INR crore", **base_kwargs)
            )
        if _contains_pattern(normalized, CAPITALIZED_PRODUCT_DEVELOPMENT_PATTERNS):
            facts_by_metric.setdefault("capitalized_product_development", []).append(
                FinancialFact(metric_id="capitalized_product_development", metric_name=_canonical_metric_name("capitalized_product_development"), value=float(value), unit="INR crore", **base_kwargs)
            )
        if _contains_pattern(normalized, CAPEX_INTANGIBLE_PATTERNS):
            facts_by_metric.setdefault("capex_intangible_cash_outflow", []).append(
                FinancialFact(metric_id="capex_intangible_cash_outflow", metric_name=_canonical_metric_name("capex_intangible_cash_outflow"), value=float(value), unit="INR crore", **base_kwargs)
            )
        if _contains_pattern(normalized, CAPEX_PPE_PATTERNS):
            facts_by_metric.setdefault("capex_ppe_cwip_cash_outflow", []).append(
                FinancialFact(metric_id="capex_ppe_cwip_cash_outflow", metric_name=_canonical_metric_name("capex_ppe_cwip_cash_outflow"), value=float(value), unit="INR crore", **base_kwargs)
            )
        if "gross block" in normalized or "additions" in normalized:
            facts_by_metric.setdefault("gross_block_additions", []).append(
                FinancialFact(metric_id="gross_block_additions", metric_name=_canonical_metric_name("gross_block_additions"), value=float(value), unit="INR crore", **base_kwargs)
            )


def _derive_fcf_ratio(
    *,
    metric_id: str,
    metric_name: str,
    unit: str,
    formula: str,
    fcf: "FinancialFact",
    denominator: "FinancialFact",
    multiplier: float = 1.0,
    fiscal_year: str,
) -> "FinancialFact":
    value = round(fcf.value / denominator.value * multiplier, 4)  # type: ignore[operator]
    usable = fcf.usable_downstream and denominator.usable_downstream
    return FinancialFact(
        metric_id=metric_id,
        metric_name=metric_name,
        fiscal_year=fiscal_year,
        period=fiscal_year,
        value=value,
        unit=unit,
        basis=fcf.basis if fcf.basis == denominator.basis else "unknown",
        source_statement="derived_from_financial_truth_registry",
        source_artifact="financial_truth_registry.json",
        source_line_item=f"derived:{metric_id}",
        source_page=None,
        confidence="medium",
        availability_status="present_derived" if usable else "partial",
        derived=True,
        formula=formula,
        inputs_used=["fcf", denominator.metric_id],
        warnings=["Derived from canonical FCF and normalized fundamentals; financial_ratios.json not used as input."],
        reconciliation_status="warning",
        usable_downstream=usable,
        notes=["Canonical FCF-derived ratio — consistent with ratio_calculator sign contract."],
    )


def _derive_fcf_to_pat(facts_by_metric: Dict[str, List[FinancialFact]], fiscal_year: str) -> FinancialFact | None:
    if facts_by_metric.get("fcf_to_pat"):
        best = _pick_best_fact(facts_by_metric["fcf_to_pat"])
        if best.availability_status in {"present_direct", "present_derived"}:
            return None
    fcf_facts = facts_by_metric.get("fcf", [])
    pat_facts = facts_by_metric.get("pat", [])
    if not fcf_facts or not pat_facts:
        return None
    fcf = _pick_best_fact(fcf_facts)
    pat = _pick_best_fact(pat_facts)
    if fcf.value is None or pat.value is None or pat.value == 0:
        return None
    if not fcf.usable_downstream or not pat.usable_downstream:
        return None
    return _derive_fcf_ratio(
        metric_id="fcf_to_pat",
        metric_name="FCF to PAT",
        unit="x",
        formula="fcf / pat",
        fcf=fcf,
        denominator=pat,
        fiscal_year=fiscal_year,
    )


def _derive_fcf_margin(facts_by_metric: Dict[str, List[FinancialFact]], fiscal_year: str) -> FinancialFact | None:
    if facts_by_metric.get("fcf_margin"):
        best = _pick_best_fact(facts_by_metric["fcf_margin"])
        if best.availability_status in {"present_direct", "present_derived"}:
            return None
    fcf_facts = facts_by_metric.get("fcf", [])
    revenue_facts = facts_by_metric.get("revenue", [])
    if not fcf_facts or not revenue_facts:
        return None
    fcf = _pick_best_fact(fcf_facts)
    revenue = _pick_best_fact(revenue_facts)
    if fcf.value is None or revenue.value is None or revenue.value == 0:
        return None
    if not fcf.usable_downstream or not revenue.usable_downstream:
        return None
    return _derive_fcf_ratio(
        metric_id="fcf_margin",
        metric_name="FCF Margin",
        unit="%",
        formula="fcf / revenue * 100",
        fcf=fcf,
        denominator=revenue,
        multiplier=100.0,
        fiscal_year=fiscal_year,
    )


def _derive_fcf_variants(facts_by_metric: Dict[str, List[FinancialFact]], fiscal_year: str) -> List[FinancialFact]:
    cfo_facts = facts_by_metric.get("cfo", [])
    if not cfo_facts:
        return []
    cfo = _pick_best_fact(cfo_facts)
    if cfo.value is None:
        return []
    variants: List[FinancialFact] = []
    for source_metric, target_metric in (
        ("capex_ppe_cwip_cash_outflow", "fcf_after_ppe_cwip_capex"),
        ("capex", "fcf_after_total_identified_capex"),
    ):
        source_facts = facts_by_metric.get(source_metric, [])
        if not source_facts:
            continue
        capex_fact = _pick_best_fact(source_facts)
        if capex_fact.value is None:
            continue
        derived_value = cfo.value + capex_fact.value if capex_fact.value < 0 else cfo.value - capex_fact.value
        variants.append(
            FinancialFact(
                metric_id=target_metric,
                metric_name=_canonical_metric_name(target_metric),
                fiscal_year=fiscal_year,
                period=fiscal_year,
                value=derived_value,
                unit="INR crore",
                basis=cfo.basis if cfo.basis == capex_fact.basis else "unknown",
                source_statement="derived_from_financial_truth_registry",
                source_artifact="financial_truth_registry.json",
                source_line_item=f"derived:{target_metric}",
                source_page=None,
                confidence="medium",
                availability_status="present_derived",
                derived=True,
                formula=f"cfo + {source_metric} if signed, else cfo - {source_metric}",
                inputs_used=["cfo", source_metric],
                warnings=[],
                reconciliation_status="warning",
                usable_downstream=cfo.usable_downstream and capex_fact.usable_downstream,
                notes=[],
            )
        )
    return variants


def _derive_total_capex_for_fcf(facts_by_metric: Dict[str, List[FinancialFact]], fiscal_year: str) -> FinancialFact | None:
    if facts_by_metric.get("total_capex_for_fcf"):
        best = _pick_best_fact(facts_by_metric["total_capex_for_fcf"])
        if best.availability_status in {"present_direct", "present_derived"}:
            return None
    preferred = facts_by_metric.get("capex", [])
    if preferred:
        best = _pick_best_fact(preferred)
        if best.value is not None:
            return FinancialFact(
                metric_id="total_capex_for_fcf",
                metric_name=_canonical_metric_name("total_capex_for_fcf"),
                fiscal_year=fiscal_year,
                period=fiscal_year,
                value=best.value,
                unit=best.unit,
                basis=best.basis,
                source_statement="derived_from_normalized_fundamentals",
                source_artifact=best.source_artifact,
                source_line_item="derived:total_capex_for_fcf_from_capex",
                source_page=best.source_page,
                confidence=best.confidence,
                availability_status="present_derived",
                derived=True,
                formula="Use normalized capex when available as the primary FCF capex input.",
                inputs_used=["capex"],
                warnings=list(best.warnings),
                reconciliation_status=best.reconciliation_status,
                usable_downstream=best.usable_downstream,
                notes=["Canonical FCF capex input selected from normalized capex."],
            )
    components: List[FinancialFact] = []
    for metric_id in ("capex_ppe_cwip_cash_outflow", "capex_intangible_cash_outflow"):
        items = facts_by_metric.get(metric_id, [])
        if items:
            best = _pick_best_fact(items)
            if best.value is not None:
                components.append(best)
    if not components:
        return None
    value = sum(item.value for item in components if item.value is not None)
    usable = all(item.usable_downstream for item in components)
    return FinancialFact(
        metric_id="total_capex_for_fcf",
        metric_name=_canonical_metric_name("total_capex_for_fcf"),
        fiscal_year=fiscal_year,
        period=fiscal_year,
        value=value,
        unit="INR crore",
        basis=components[0].basis if len({item.basis for item in components}) == 1 else "unknown",
        source_statement="derived_from_financial_truth_registry",
        source_artifact="financial_truth_registry.json",
        source_line_item="derived:total_capex_for_fcf",
        source_page=None,
        confidence="medium",
        availability_status="present_derived",
        derived=True,
        formula="sum(ppe/cwip cash outflow, intangible cash outflow)",
        inputs_used=[item.metric_id for item in components],
        warnings=["Total capex for FCF derived from identified capex components."],
        reconciliation_status="warning",
        usable_downstream=usable,
        notes=[],
    )


def _derive_total_growth_or_expansion_capex(facts_by_metric: Dict[str, List[FinancialFact]], fiscal_year: str) -> FinancialFact | None:
    components: List[FinancialFact] = []
    for metric_id in ("growth_capex_disclosed", "capital_commitments"):
        items = facts_by_metric.get(metric_id, [])
        if items:
            best = _pick_best_fact(items)
            if best.value is not None:
                components.append(best)
    if not components:
        return None
    value = sum(item.value for item in components if item.value is not None)
    return FinancialFact(
        metric_id="total_growth_or_expansion_capex",
        metric_name=_canonical_metric_name("total_growth_or_expansion_capex"),
        fiscal_year=fiscal_year,
        period=fiscal_year,
        value=value,
        unit="INR crore",
        basis=components[0].basis if len({item.basis for item in components}) == 1 else "unknown",
        source_statement="derived_from_financial_truth_registry",
        source_artifact="financial_truth_registry.json",
        source_line_item="derived:total_growth_or_expansion_capex",
        source_page=None,
        confidence="medium",
        availability_status="present_derived",
        derived=True,
        formula="sum(disclosed growth capex, capital commitments where relevant)",
        inputs_used=[item.metric_id for item in components],
        warnings=["Growth/expansion capex derived from disclosed expansion signals."],
        reconciliation_status="warning",
        usable_downstream=all(item.usable_downstream for item in components),
        notes=["Capital commitments are future obligations, not current-period cash capex."],
    )


def _derive_net_debt(facts_by_metric: Dict[str, List[FinancialFact]], fiscal_year: str) -> FinancialFact | None:
    debt_items = facts_by_metric.get("total_debt") or facts_by_metric.get("gross_debt") or []
    cash_items = facts_by_metric.get("cash_and_equivalents", [])
    if not debt_items or not cash_items:
        return None
    debt = _pick_best_fact(debt_items)
    cash = _pick_best_fact(cash_items)
    if debt.value is None or cash.value is None:
        return None
    confidence = "medium" if debt.usable_downstream and cash.usable_downstream else "unreliable"
    availability = "present_derived" if confidence != "unreliable" else "unreliable"
    return FinancialFact(
        metric_id="net_debt",
        metric_name=_canonical_metric_name("net_debt"),
        fiscal_year=fiscal_year,
        period=fiscal_year,
        value=debt.value - cash.value,
        unit="INR crore",
        basis=debt.basis if debt.basis == cash.basis else "unknown",
        source_statement="derived_from_financial_truth_registry",
        source_artifact="financial_truth_registry.json",
        source_line_item="derived:net_debt",
        source_page=None,
        confidence=confidence,
        availability_status=availability,
        derived=True,
        formula="gross debt - cash and equivalents",
        inputs_used=[debt.metric_id, "cash_and_equivalents"],
        warnings=[] if confidence != "unreliable" else ["Net debt derived from debt/cash inputs that are not fully reliable downstream."],
        reconciliation_status="warning" if confidence == "unreliable" else "pass",
        usable_downstream=confidence != "unreliable",
        notes=[],
    )


def _parse_corporate_action_facts(payload: Dict[str, Any], year: str) -> Dict[str, List[FinancialFact]]:
    facts: Dict[str, List[FinancialFact]] = {}
    actions = payload.get("actions")
    if not isinstance(actions, list):
        return facts
    comparability_like = {"qip_issue", "preferential_issue", "rights_issue", "bonus_issue", "stock_split", "split", "buyback", "esop_dilution", "warrants"}
    dilution_like = {"qip_issue", "preferential_issue", "rights_issue", "esop_dilution", "warrants"}
    active_actions = [item for item in actions if isinstance(item, dict) and item.get("active", True) is not False and str(item.get("status") or "").lower() != "rejected"]
    if not active_actions:
        return facts
    has_comparability_warning = False
    has_dilution_event = False
    for action in active_actions:
        subtype = _normalize(str(action.get("action_subtype") or action.get("action_type") or ""))
        impact = _normalize(str(action.get("impact_on_share_count") or "unknown"))
        if subtype in comparability_like or impact in {"increase", "decrease", "unknown"}:
            has_comparability_warning = True
        if subtype in dilution_like or (impact == "increase" and subtype not in {"bonus_issue", "stock_split", "split"}):
            has_dilution_event = True
    if has_comparability_warning:
        facts.setdefault("eps_comparability_status", []).append(
            FinancialFact(
                metric_id="eps_comparability_status",
                metric_name=_canonical_metric_name("eps_comparability_status"),
                fiscal_year=year,
                period=year,
                value=None,
                unit="",
                basis="not_applicable",
                source_statement="corporate_actions",
                source_artifact="corporate_actions.json",
                source_line_item="derived:eps_comparability_status",
                source_page=None,
                confidence="medium",
                availability_status="partial",
                derived=True,
                formula="corporate actions may affect per-share comparability",
                inputs_used=["corporate_actions"],
                warnings=["Per-share comparability requires caution because share-count-affecting corporate actions exist."],
                reconciliation_status="not_applicable",
                usable_downstream=False,
                notes=[],
            )
        )
    if has_dilution_event:
        facts.setdefault("dilution_status", []).append(
            FinancialFact(
                metric_id="dilution_status",
                metric_name=_canonical_metric_name("dilution_status"),
                fiscal_year=year,
                period=year,
                value=None,
                unit="",
                basis="not_applicable",
                source_statement="corporate_actions",
                source_artifact="corporate_actions.json",
                source_line_item="derived:dilution_status",
                source_page=None,
                confidence="medium",
                availability_status="partial",
                derived=True,
                formula="active share-count-increasing action detected",
                inputs_used=["corporate_actions"],
                warnings=["Potential dilution event detected; weighted-average or diluted denominators may need extra review."],
                reconciliation_status="not_applicable",
                usable_downstream=False,
                notes=[],
            )
        )
    return facts


def _parse_normalized_facts(
    payload: Dict[str, Any],
    year: str,
    reconciliation_checks: Dict[str, Dict[str, Any]],
) -> Dict[str, List[FinancialFact]]:
    facts: Dict[str, List[FinancialFact]] = {}
    for section_name, section_payload in payload.items():
        if not isinstance(section_payload, dict):
            continue
        for metric_id, entry in section_payload.items():
            if not isinstance(entry, dict):
                continue
            if metric_id in {"warnings", "limitations", "basis_manifest"}:
                continue
            if not any(
                key in entry
                for key in (
                    "canonical_field",
                    "value_crore",
                    "value_original",
                    "value_per_share",
                    "value_shares",
                    "raw_number",
                )
            ):
                continue
            fact = _build_fact_from_normalized(
                metric_id=metric_id,
                fiscal_year=year,
                section_name=section_name,
                entry=entry,
                reconciliation=reconciliation_checks.get(metric_id),
            )
            facts.setdefault(metric_id, []).append(fact)
            if metric_id == "shares_outstanding":
                clone = FinancialFact(**{**fact.__dict__, "metric_id": "closing_shares", "metric_name": _canonical_metric_name("closing_shares")})
                facts.setdefault("closing_shares", []).append(clone)
            if metric_id == "weighted_avg_shares":
                clone = FinancialFact(**{**fact.__dict__, "metric_id": "weighted_average_basic_shares", "metric_name": _canonical_metric_name("weighted_average_basic_shares")})
                facts.setdefault("weighted_average_basic_shares", []).append(clone)
    return facts


def _parse_ratio_facts(payload: Dict[str, Any], year: str) -> Dict[str, List[FinancialFact]]:
    facts: Dict[str, List[FinancialFact]] = {}
    ratios = payload.get("ratios")
    if not isinstance(ratios, dict):
        return facts
    for metric_id, item in ratios.items():
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        confidence = str(item.get("confidence") or ("missing" if value is None else "medium"))
        fact = FinancialFact(
            metric_id=metric_id,
            metric_name=_canonical_metric_name(metric_id),
            fiscal_year=year,
            period=year,
            value=float(value) if isinstance(value, (int, float)) else None,
            unit=str(item.get("unit") or ""),
            basis=str(item.get("basis") or "unknown"),
            source_statement="financial_ratios",
            source_artifact="financial_ratios.json",
            source_line_item=metric_id,
            source_page=None,
            confidence=confidence if confidence in {"high", "medium", "low", "missing"} else "medium",
            availability_status="present_derived" if isinstance(value, (int, float)) else "missing",
            derived=True,
            formula=str(item.get("formula") or ""),
            inputs_used=[str(part.get("name") or part) for part in item.get("inputs_used", []) if str(part).strip()],
            warnings=[str(w) for w in item.get("warnings", []) if str(w).strip()],
            reconciliation_status="unknown",
            usable_downstream=isinstance(value, (int, float)),
            notes=[],
        )
        facts.setdefault(metric_id, []).append(fact)
        if metric_id == "shares_outstanding":
            clone = FinancialFact(**{**fact.__dict__, "metric_id": "closing_shares", "metric_name": _canonical_metric_name("closing_shares")})
            facts.setdefault("closing_shares", []).append(clone)
        if metric_id == "weighted_avg_shares":
            clone = FinancialFact(**{**fact.__dict__, "metric_id": "weighted_average_basic_shares", "metric_name": _canonical_metric_name("weighted_average_basic_shares")})
            facts.setdefault("weighted_average_basic_shares", []).append(clone)
    return facts


def _parse_growth_facts(payload: Dict[str, Any], year: str) -> Dict[str, List[FinancialFact]]:
    facts: Dict[str, List[FinancialFact]] = {}
    for container_name in ("growth_metrics", "margin_changes"):
        container = payload.get(container_name)
        if not isinstance(container, dict):
            continue
        suffix = "_growth" if container_name == "growth_metrics" else "_margin_change"
        for metric_id, item in container.items():
            if not isinstance(item, dict):
                continue
            value = item.get("growth_percent")
            if container_name == "margin_changes":
                value = item.get("absolute_change")
            metric_key = f"{metric_id}{suffix}"
            fact = FinancialFact(
                metric_id=metric_key,
                metric_name=_canonical_metric_name(metric_key),
                fiscal_year=year,
                period=year,
                value=float(value) if isinstance(value, (int, float)) else None,
                unit=str(item.get("unit") or "%"),
                basis=str(item.get("basis") or "unknown"),
                source_statement="financial_growth",
                source_artifact="financial_growth.json",
                source_line_item=metric_id,
                source_page=None,
                confidence=str(item.get("confidence") or ("missing" if value is None else "medium")),
                availability_status="present_derived" if isinstance(value, (int, float)) else "missing",
                derived=True,
                formula="deterministic growth calculation",
                inputs_used=[metric_id],
                warnings=[str(w) for w in item.get("warnings", []) if str(w).strip()],
                reconciliation_status="unknown",
                usable_downstream=isinstance(value, (int, float)),
                notes=[],
            )
            facts.setdefault(metric_key, []).append(fact)
    return facts


def _parse_shareholding_facts(payload: Dict[str, Any], year: str) -> Dict[str, List[FinancialFact]]:
    facts: Dict[str, List[FinancialFact]] = {}
    rows: List[Dict[str, Any]] = []
    for key in ("items", "holdings", "shareholding_items"):
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend(item for item in value if isinstance(item, dict))
    if not rows:
        rows.extend(item for item in payload.get("shareholding", []) if isinstance(item, dict))
    if not rows:
        return facts
    valid_percent_by_category: Dict[str, float] = {}
    for row in rows:
        category = str(row.get("holder_category") or row.get("category") or "").strip().lower().replace(" ", "_")
        if not category:
            continue
        metric_id = f"shareholding_{category}_percent"
        raw_value = row.get("holding_percent")
        value = float(raw_value) if isinstance(raw_value, (int, float)) else None
        confidence = str(row.get("confidence") or ("missing" if value is None else "medium"))
        warnings = [str(w) for w in row.get("warnings", []) if str(w).strip()]
        availability = "present_direct" if value is not None else "missing"
        usable = value is not None
        if value is not None:
            if value < 0 or value > 100:
                confidence = "invalid"
                availability = "invalid"
                usable = False
                _append_unique(warnings, "Shareholding percentage is outside sane bounds.")
            else:
                valid_percent_by_category[category] = value
        facts.setdefault(metric_id, []).append(
            FinancialFact(
                metric_id=metric_id,
                metric_name=_canonical_metric_name(metric_id),
                fiscal_year=year,
                period=str(row.get("period") or year),
                value=value,
                unit="percent",
                basis="not_applicable",
                source_statement="shareholding_pattern",
                source_artifact="shareholding_pattern.json",
                source_line_item=str(row.get("source_line_item") or category),
                source_page=row.get("source_page"),
                confidence=confidence,
                availability_status=availability,
                derived=False,
                formula="",
                inputs_used=[],
                warnings=warnings,
                reconciliation_status="not_applicable",
                usable_downstream=usable,
                notes=[],
            )
        )

    sum_check_value: Optional[float] = None
    sum_check_inputs: List[str] = []
    promoter_value = valid_percent_by_category.get("promoter_holding_percent")
    public_value = valid_percent_by_category.get("public_holding_percent")
    if promoter_value is not None and public_value is not None:
        sum_check_value = promoter_value + public_value
        sum_check_inputs = ["promoter_holding_percent", "public_holding_percent"]
    elif promoter_value is None and public_value is None:
        ownership_components = [
            "fii_holding_percent",
            "dii_holding_percent",
            "mutual_fund_holding_percent",
            "insurance_holding_percent",
            "body_corporates_percent",
            "retail_holding_percent",
            "others_percent",
        ]
        component_values = [
            valid_percent_by_category[category]
            for category in ownership_components
            if category in valid_percent_by_category
        ]
        if len(component_values) >= 4:
            sum_check_value = sum(component_values)
            sum_check_inputs = [category for category in ownership_components if category in valid_percent_by_category]

    if sum_check_value is not None and not (95.0 <= sum_check_value <= 105.0):
        facts.setdefault("shareholding_sum_check", []).append(
            FinancialFact(
                metric_id="shareholding_sum_check",
                metric_name="Shareholding Category Sum Check",
                fiscal_year=year,
                period=year,
                value=sum_check_value,
                unit="percent",
                basis="not_applicable",
                source_statement="shareholding_pattern",
                source_artifact="shareholding_pattern.json",
                source_line_item="derived:shareholding_sum",
                source_page=None,
                confidence="invalid",
                availability_status="invalid",
                derived=True,
                formula="sum(shareholding category percentages)",
                inputs_used=sum_check_inputs or ["shareholding percentages"],
                warnings=["Shareholding category percentages do not sum near 100."],
                reconciliation_status="not_applicable",
                usable_downstream=False,
                notes=[],
            )
        )
    return facts


def _collect_shareholding_quarantine(
    payload: Dict[str, Any] | None,
    year: str,
) -> Tuple[List[FinancialFact], List[Dict[str, Any]], Dict[str, Any]]:
    if not isinstance(payload, dict):
        return [], [], {
            "status": "missing",
            "usable_downstream": False,
            "domain": "shareholding",
            "invalid_fields": [],
            "reliable_fields": [],
            "warnings_to_block_downstream": [],
            "warnings_allowed_downstream": [],
        }
    rows = payload.get("items")
    if not isinstance(rows, list):
        return [], [], {
            "status": "missing",
            "usable_downstream": False,
            "domain": "shareholding",
            "invalid_fields": [],
            "reliable_fields": [],
            "warnings_to_block_downstream": [],
            "warnings_allowed_downstream": list(payload.get("warnings", []) if isinstance(payload.get("warnings"), list) else []),
        }
    findings: List[Dict[str, Any]] = []
    quarantined_facts: List[FinancialFact] = []
    valid_percent_count = 0
    invalid_percent_count = 0
    valid_percent_by_category: Dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        category = _normalize(str(row.get("holder_category") or "unknown"))
        value = row.get("holding_percent")
        shares_held = row.get("shares_held")
        source_line_item = str(row.get("source_line_item") or category)
        if isinstance(value, (int, float)):
            if _is_valid_percentage(float(value)):
                valid_percent_count += 1
                valid_percent_by_category[category] = float(value)
            else:
                invalid_percent_count += 1
                reason = "Percentage field is outside sane 0-100 bounds; likely share-count/percentage mixup."
                fact = FinancialFact(
                    metric_id=f"shareholding_{category}_percent",
                    metric_name=_canonical_metric_name(f"shareholding_{category}_percent"),
                    fiscal_year=year,
                    period=str(row.get("period") or year),
                    value=float(value),
                    unit="percent",
                    basis="not_applicable",
                    source_statement="shareholding_pattern",
                    source_artifact="shareholding_pattern.json",
                    source_line_item=source_line_item,
                    source_page=row.get("source_page"),
                    confidence="invalid",
                    availability_status="invalid",
                    derived=False,
                    formula="",
                    inputs_used=[],
                    warnings=[reason],
                    reconciliation_status="not_applicable",
                    usable_downstream=False,
                    notes=[reason],
                )
                quarantined_facts.append(fact)
                _append_quarantine_finding(
                    findings,
                    artifact_name="shareholding_pattern.json",
                    domain="shareholding",
                    metric_id=fact.metric_id,
                    status="quarantined",
                    usable_downstream=False,
                    invalid_reason=reason,
                    source_line_item=source_line_item,
                    source_artifact="shareholding_pattern.json",
                    invalid_fields=["holding_percent"],
                    reliable_fields=["shares_held"] if isinstance(shares_held, (int, float)) else [],
                    warnings_to_block_downstream=["ownership quality", "ownership_inputs", "ownership trend use"],
                )
        if isinstance(shares_held, (int, float)) and not _is_near_integer(float(shares_held), tolerance=0.5):
            reason = "Share-count field is not integer-like enough for reliable downstream ownership use."
            _append_quarantine_finding(
                findings,
                artifact_name="shareholding_pattern.json",
                domain="ownership",
                metric_id=f"shareholding_{category}_shares_held",
                status="quarantined",
                usable_downstream=False,
                invalid_reason=reason,
                source_line_item=source_line_item,
                source_artifact="shareholding_pattern.json",
                invalid_fields=["shares_held"],
                reliable_fields=["holding_percent"] if isinstance(value, (int, float)) and _is_valid_percentage(float(value)) else [],
                warnings_to_block_downstream=["ownership quality"],
            )
    artifact_status = "usable"
    usable_downstream = True
    warnings_to_block = []
    warnings_allowed = list(payload.get("warnings", []) if isinstance(payload.get("warnings"), list) else [])
    if invalid_percent_count and valid_percent_count == 0:
        artifact_status = "quarantined"
        usable_downstream = False
        warnings_to_block.append("ownership percent facts quarantined")
    elif invalid_percent_count:
        artifact_status = "partial"
        usable_downstream = False
        warnings_to_block.append("some ownership categories quarantined")
    top_level_sum: Optional[float] = None
    promoter_value = valid_percent_by_category.get("promoter_holding_percent")
    public_value = valid_percent_by_category.get("public_holding_percent")
    if promoter_value is not None and public_value is not None:
        top_level_sum = promoter_value + public_value
    elif promoter_value is None and public_value is None:
        component_categories = (
            "fii_holding_percent",
            "dii_holding_percent",
            "mutual_fund_holding_percent",
            "insurance_holding_percent",
            "body_corporates_percent",
            "retail_holding_percent",
            "others_percent",
        )
        component_values = [
            valid_percent_by_category[category]
            for category in component_categories
            if category in valid_percent_by_category
        ]
        if len(component_values) >= 4:
            top_level_sum = sum(component_values)
    if top_level_sum is not None and not (95.0 <= top_level_sum <= 105.0):
        if invalid_percent_count >= max(2, valid_percent_count):
            artifact_status = "quarantined"
            usable_downstream = False
        elif artifact_status == "usable":
            artifact_status = "usable_with_warnings"
        warnings_allowed.append("Ownership categories do not sum near 100%.")
    return quarantined_facts, findings, {
        "status": artifact_status,
        "usable_downstream": usable_downstream,
        "domain": "shareholding",
        "invalid_fields": sorted({field for item in findings for field in item.get("invalid_fields", [])}),
        "reliable_fields": sorted({field for item in findings for field in item.get("reliable_fields", [])}),
        "warnings_to_block_downstream": warnings_to_block,
        "warnings_allowed_downstream": warnings_allowed,
    }


def _collect_corporate_action_quarantine(
    payload: Dict[str, Any] | None,
    year: str,
) -> Tuple[List[FinancialFact], List[Dict[str, Any]], Dict[str, Any]]:
    if not isinstance(payload, dict):
        return [], [], {
            "status": "missing",
            "usable_downstream": False,
            "domain": "corporate_actions",
            "invalid_fields": [],
            "reliable_fields": [],
            "warnings_to_block_downstream": [],
            "warnings_allowed_downstream": [],
        }
    actions = payload.get("actions")
    if not isinstance(actions, list):
        return [], [], {
            "status": "missing",
            "usable_downstream": False,
            "domain": "corporate_actions",
            "invalid_fields": [],
            "reliable_fields": [],
            "warnings_to_block_downstream": [],
            "warnings_allowed_downstream": list(payload.get("warnings", []) if isinstance(payload.get("warnings"), list) else []),
        }
    findings: List[Dict[str, Any]] = []
    quarantined_facts: List[FinancialFact] = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        action_type = _normalize(str(action.get("action_type") or "corporate_action"))
        source_line_item = str(action.get("source_line_item") or action_type)
        source_artifact = str(action.get("source_artifact") or "corporate_actions.json")
        value_type_used = _normalize(str(action.get("value_type_used") or ""))
        metric_prefix = f"corporate_action_{action_type}_{index}"
        if action.get("shares_issued") is not None and (
            value_type_used == "monetary"
            or (isinstance(action.get("shares_issued"), (int, float)) and not _is_near_integer(float(action.get("shares_issued")), tolerance=0.5))
        ):
            reason = "shares_issued appears monetary or non-integer-like and is quarantined."
            fact = FinancialFact(
                metric_id=f"{metric_prefix}_shares_issued",
                metric_name="Corporate Action Shares Issued",
                fiscal_year=year,
                period=year,
                value=float(action.get("shares_issued")),
                unit="shares",
                basis="not_applicable",
                source_statement="corporate_actions",
                source_artifact="corporate_actions.json",
                source_line_item=source_line_item,
                source_page=action.get("source_page"),
                confidence="invalid",
                availability_status="invalid",
                derived=False,
                formula="",
                inputs_used=[],
                warnings=[reason],
                reconciliation_status="not_applicable",
                usable_downstream=False,
                notes=[reason],
            )
            quarantined_facts.append(fact)
            _append_quarantine_finding(
                findings,
                artifact_name="corporate_actions.json",
                domain="corporate_actions",
                metric_id=fact.metric_id,
                status="quarantined",
                usable_downstream=False,
                invalid_reason=reason,
                source_line_item=source_line_item,
                source_artifact=source_artifact,
                invalid_fields=["shares_issued"],
                reliable_fields=[],
                warnings_to_block_downstream=["per-share comparability", "capital allocation", "ownership dilution"],
            )
        if action.get("amount_crore") is not None and value_type_used == "share_count":
            reason = "amount_crore appears to carry share-count context and is quarantined."
            fact = FinancialFact(
                metric_id=f"{metric_prefix}_amount_crore",
                metric_name="Corporate Action Amount",
                fiscal_year=year,
                period=year,
                value=float(action.get("amount_crore")),
                unit="INR crore",
                basis="not_applicable",
                source_statement="corporate_actions",
                source_artifact="corporate_actions.json",
                source_line_item=source_line_item,
                source_page=action.get("source_page"),
                confidence="invalid",
                availability_status="invalid",
                derived=False,
                formula="",
                inputs_used=[],
                warnings=[reason],
                reconciliation_status="not_applicable",
                usable_downstream=False,
                notes=[reason],
            )
            quarantined_facts.append(fact)
            _append_quarantine_finding(
                findings,
                artifact_name="corporate_actions.json",
                domain="capital_allocation",
                metric_id=fact.metric_id,
                status="quarantined",
                usable_downstream=False,
                invalid_reason=reason,
                source_line_item=source_line_item,
                source_artifact=source_artifact,
                invalid_fields=["amount_crore"],
                reliable_fields=[],
                warnings_to_block_downstream=["capital allocation", "per-share comparability"],
            )
        if action_type in {"dividend", "final_dividend", "interim_dividend"} and action.get("per_share_amount") is not None:
            lower_line = _normalize(source_line_item)
            if "paid" in lower_line and "per share" not in lower_line and "record" not in lower_line:
                reason = "Dividend cash outflow was interpreted as per-share dividend and is quarantined."
                _append_quarantine_finding(
                    findings,
                    artifact_name="corporate_actions.json",
                    domain="per_share",
                    metric_id=f"{metric_prefix}_per_share_amount",
                    status="quarantined",
                    usable_downstream=False,
                    invalid_reason=reason,
                    source_line_item=source_line_item,
                    source_artifact=source_artifact,
                    invalid_fields=["per_share_amount"],
                    reliable_fields=["amount_crore"] if action.get("amount_crore") is not None else [],
                    warnings_to_block_downstream=["dividend_per_share", "per-share analysis"],
                )
        if action_type == "share_capital_change":
            shares_before = action.get("shares_before")
            shares_after = action.get("shares_after")
            fv_before = action.get("face_value_before")
            fv_after = action.get("face_value_after")
            if shares_before == shares_after and fv_before == fv_after:
                reason = "Unchanged share capital should not be treated as a corporate action."
                _append_quarantine_finding(
                    findings,
                    artifact_name="corporate_actions.json",
                    domain="corporate_actions",
                    metric_id=f"{metric_prefix}_share_capital_change",
                    status="quarantined",
                    usable_downstream=False,
                    invalid_reason=reason,
                    source_line_item=source_line_item,
                    source_artifact=source_artifact,
                    invalid_fields=["share_capital_change"],
                    reliable_fields=[],
                    warnings_to_block_downstream=["share count change", "dilution inference"],
                )
    artifact_status = "usable"
    usable_downstream = True
    if findings:
        artifact_status = "partial"
        usable_downstream = False
    return quarantined_facts, findings, {
        "status": artifact_status,
        "usable_downstream": usable_downstream,
        "domain": "corporate_actions",
        "invalid_fields": sorted({field for item in findings for field in item.get("invalid_fields", [])}),
        "reliable_fields": sorted({field for item in findings for field in item.get("reliable_fields", [])}),
        "warnings_to_block_downstream": sorted({warning for item in findings for warning in item.get("warnings_to_block_downstream", [])}),
        "warnings_allowed_downstream": list(payload.get("per_share_comparability_warnings", []) if isinstance(payload.get("per_share_comparability_warnings"), list) else []),
    }


def _collect_warning_texts(artifacts: Dict[str, Dict[str, Any]]) -> List[str]:
    texts: List[str] = []
    for filename, payload in artifacts.items():
        if filename not in {"financial_quality_summary.json", "financial_validation_report.json", "financial_reconciliation_report.json"}:
            continue
        for field in ("warnings", "limitations", "missing_data", "hard_failures"):
            value = payload.get(field)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        texts.append(item)
    return texts


def _fact_from_missing(metric_id: str, year: str, note: str) -> FinancialFact:
    return FinancialFact(
        metric_id=metric_id,
        metric_name=_canonical_metric_name(metric_id),
        fiscal_year=year,
        period=year,
        value=None,
        unit="",
        basis="unknown",
        source_statement="financial_truth_registry",
        source_artifact="financial_truth_registry.json",
        source_line_item="",
        source_page=None,
        confidence="missing",
        availability_status="missing",
        derived=False,
        formula="",
        inputs_used=[],
        warnings=[],
        reconciliation_status="unknown",
        usable_downstream=False,
        notes=[note],
    )


def _fact_from_precise_missing(metric_id: str, year: str, note: str) -> FinancialFact:
    fact = _fact_from_missing(metric_id, year, note)
    fact.notes = [note]
    return fact


def build_financial_fact_registry(
    *,
    company: str,
    year: str,
    financial_root: Path,
) -> Tuple[FinancialFactRegistry, FinancialTruthReconciliationReport, FinancialArtifactQuarantineReport]:
    artifacts: Dict[str, Dict[str, Any]] = {}
    registry_warnings: List[str] = []
    source_artifacts_read: List[str] = []
    for filename in ARTIFACT_FILENAMES:
        path = financial_root / filename
        if not path.exists():
            _append_unique(registry_warnings, f"Optional artifact missing: {filename}")
            continue
        artifacts[filename] = _load_json(path)
        source_artifacts_read.append(filename)

    reconciliation_checks = _reconciliation_map(artifacts.get("financial_reconciliation_report.json", {}))
    facts_by_metric: Dict[str, List[FinancialFact]] = {}
    for parser, filename in (
        (_parse_normalized_facts, "normalized_fundamentals.json"),
        (_parse_ratio_facts, "financial_ratios.json"),
        (_parse_growth_facts, "financial_growth.json"),
        (_parse_shareholding_facts, "shareholding_pattern.json"),
        (_parse_corporate_action_facts, "corporate_actions.json"),
    ):
        payload = artifacts.get(filename)
        if not payload:
            continue
        if parser is _parse_normalized_facts:
            parsed = parser(payload, year, reconciliation_checks)
        else:
            parsed = parser(payload, year)
        for metric_id, items in parsed.items():
            facts_by_metric.setdefault(metric_id, []).extend(items)

    _add_raw_capex_classification_facts(facts_by_metric, artifacts.get("raw_financial_tables.json"), year)

    for derivation in (
        _derive_fcf_if_possible,
        _derive_fcf_to_pat,
        _derive_fcf_margin,
        _derive_payable_days_from_turnover,
        _derive_payables_proxy,
        _derive_cash_conversion_cycle,
        _derive_total_capex_for_fcf,
        _derive_total_growth_or_expansion_capex,
        _derive_net_debt,
    ):
        derived_fact = derivation(facts_by_metric, year)
        if derived_fact is not None:
            facts_by_metric.setdefault(derived_fact.metric_id, []).append(derived_fact)
    for derived_fact in _derive_fcf_variants(facts_by_metric, year):
        facts_by_metric.setdefault(derived_fact.metric_id, []).append(derived_fact)

    best_facts: Dict[str, FinancialFact] = {
        metric_id: _pick_best_fact(items)
        for metric_id, items in facts_by_metric.items()
        if items
    }

    shareholding_quarantined_facts, shareholding_findings, shareholding_status = _collect_shareholding_quarantine(
        artifacts.get("shareholding_pattern.json"),
        year,
    )
    corporate_quarantined_facts, corporate_findings, corporate_status = _collect_corporate_action_quarantine(
        artifacts.get("corporate_actions.json"),
        year,
    )
    quarantined_facts = shareholding_quarantined_facts + corporate_quarantined_facts
    quarantine_findings = shareholding_findings + corporate_findings
    for fact in quarantined_facts:
        facts_by_metric.setdefault(fact.metric_id, []).append(fact)
        best_facts[fact.metric_id] = fact

    debt_fact = best_facts.get("total_debt") or best_facts.get("gross_debt")
    if debt_fact and debt_fact.availability_status in {"unreliable", "invalid"}:
        for metric_id in ("gross_debt", "net_debt", "debt_to_equity"):
            fact = best_facts.get(metric_id)
            if not fact or fact.availability_status not in {"present_direct", "present_derived"}:
                continue
            best_facts[metric_id] = FinancialFact(
                **{
                    **fact.__dict__,
                    "confidence": "unreliable",
                    "availability_status": "unreliable",
                    "warnings": list(fact.warnings)
                    + ["Debt-based metric downgraded because debt source failed reconciliation or remains ambiguous."],
                    "usable_downstream": False,
                    "reconciliation_status": "warning" if fact.reconciliation_status == "pass" else fact.reconciliation_status,
                }
            )

    contradictions_found: List[str] = []
    resolved_contradictions: List[str] = []
    unresolved_contradictions: List[str] = []
    false_missing_warnings: List[str] = []
    warning_normalizations: List[Dict[str, Any]] = []
    unreliable_metrics: List[str] = []
    invalid_metrics: List[str] = []
    quarantined_metrics: List[str] = []
    usable_metrics: List[str] = []
    downstream_blockers: List[str] = []

    warning_texts = _collect_warning_texts(artifacts)
    for text in warning_texts:
        for metric_id, fact in best_facts.items():
            if not _warning_mentions_metric(text, metric_id):
                continue
            claims_missing = _warning_claims_missing(text)
            claims_available = _warning_claims_available(text)
            if not claims_missing and not claims_available:
                continue
            contradictions_found.append(f"{metric_id}: {text}")
            if claims_missing and fact.availability_status in {"present_direct", "present_derived"}:
                false_missing_warnings.append(f"{metric_id}: {text}")
                resolved_contradictions.append(
                    f"{metric_id} is {fact.availability_status} from {fact.source_artifact}, so the missing warning is false."
                )
                normalized_warning = text
                if metric_id == "fcf" and fact.availability_status == "present_derived":
                    normalized_warning = "FCF derived from CFO and capex; it is not explicitly disclosed."
                elif metric_id == "capex":
                    normalized_warning = "Capex exists; maintenance/growth capex split is not disclosed."
                elif metric_id == "total_capex_for_fcf":
                    normalized_warning = "Capex exists through identified cash outflows; maintenance/growth split is not disclosed."
                elif metric_id == "payables" and any(item.metric_id == "payable_days" for item in facts_by_metric.get("payable_days", [])):
                    normalized_warning = "Payables present through trade-payables or payable-days evidence."
                elif metric_id == "payable_days" and fact.availability_status == "present_derived":
                    normalized_warning = "Payable days derived from payable turnover."
                elif metric_id in {"shares_outstanding", "closing_shares"} and "share count missing" in text.lower():
                    normalized_warning = "Closing shares exist; weighted-average shares may still be missing."
                warning_normalizations.append(
                    {
                        "original_warning": text,
                        "normalized_warning": normalized_warning,
                        "affected_metric": metric_id,
                        "reason": f"{fact.availability_status} fact contradicts broad missing warning.",
                        "evidence_used": [fact.metric_id, fact.source_artifact],
                        "resolution_status": "resolved",
                    }
                )
            elif fact.availability_status in {"unreliable", "invalid"}:
                resolved_contradictions.append(
                    f"{metric_id} exists but is {fact.availability_status}, so it should not be treated as cleanly available."
                )
                if metric_id in {"total_debt", "gross_debt", "net_debt", "debt_to_equity"} and claims_available:
                    warning_normalizations.append(
                        {
                            "original_warning": text,
                            "normalized_warning": "Debt exists but is unreliable because reconciliation failed or the source is ambiguous.",
                            "affected_metric": metric_id,
                            "reason": "Debt value exists but is not reliable enough for high-confidence downstream use.",
                            "evidence_used": [fact.metric_id, fact.source_artifact],
                            "resolution_status": "normalized_to_unreliable",
                        }
                    )
            else:
                unresolved_contradictions.append(f"{metric_id}: {text}")

    for metric_id, fact in list(best_facts.items()):
        if fact.availability_status == "unreliable":
            unreliable_metrics.append(metric_id)
            downstream_blockers.append(f"{metric_id} exists but failed reconciliation or is unreliable.")
        elif fact.availability_status == "invalid":
            invalid_metrics.append(metric_id)
            downstream_blockers.append(f"{metric_id} is invalid and quarantined.")
            if any(q.metric_id == metric_id for q in quarantined_facts):
                quarantined_metrics.append(metric_id)
        elif fact.usable_downstream:
            usable_metrics.append(metric_id)

    for metric_id in (
        "fcf",
        "payables",
        "roe",
        "roce",
        "shares_outstanding",
        "closing_shares",
        "weighted_avg_shares",
        "weighted_average_basic_shares",
        "weighted_average_diluted_shares",
        "eps_basic",
        "eps_diluted",
        "total_debt",
        "gross_debt",
        "net_debt",
        "capex",
        "total_capex_for_fcf",
        "payable_days",
        "payable_turnover",
        "cash_conversion_cycle",
    ):
        if metric_id not in best_facts:
            best_facts[metric_id] = _fact_from_missing(metric_id, year, "No usable fact was found in the available year-level artifacts.")

    available_facts: List[FinancialFact] = []
    derived_facts: List[FinancialFact] = []
    partial_facts: List[FinancialFact] = []
    missing_facts: List[FinancialFact] = []
    precise_missing_facts: List[FinancialFact] = []
    unreliable_facts: List[FinancialFact] = []
    invalid_facts: List[FinancialFact] = []
    registry_quarantined_facts: List[FinancialFact] = []
    for fact in best_facts.values():
        if fact.availability_status == "present_direct":
            available_facts.append(fact)
        elif fact.availability_status == "present_derived":
            derived_facts.append(fact)
        elif fact.availability_status == "partial":
            partial_facts.append(fact)
        elif fact.availability_status == "missing":
            missing_facts.append(fact)
        elif fact.availability_status == "unreliable":
            unreliable_facts.append(fact)
        elif fact.availability_status == "invalid":
            invalid_facts.append(fact)
            if any(q.metric_id == fact.metric_id for q in quarantined_facts):
                registry_quarantined_facts.append(fact)

    if facts_by_metric.get("capex") and not facts_by_metric.get("maintenance_capex_disclosed") and not facts_by_metric.get("growth_capex_disclosed"):
        partial_facts.append(
            FinancialFact(
                metric_id="capex_classification_status",
                metric_name="Capex Classification Status",
                fiscal_year=year,
                period=year,
                value=None,
                unit="",
                basis="unknown",
                source_statement="financial_truth_registry",
                source_artifact="financial_truth_registry.json",
                source_line_item="derived:capex_classification_status",
                source_page=None,
                confidence="medium",
                availability_status="partial",
                derived=True,
                formula="capex exists but maintenance/growth split unavailable",
                inputs_used=["capex"],
                warnings=["Maintenance/growth capex split is not disclosed."],
                reconciliation_status="warning",
                usable_downstream=False,
                notes=["Capex is present, but maintenance versus growth breakdown is unavailable."],
            )
        )
    if best_facts.get("payable_days") and best_facts["payable_days"].availability_status in {"present_direct", "present_derived"} and best_facts.get("payables", _fact_from_missing("x", year, "")).availability_status == "missing":
        partial_facts.append(
            FinancialFact(
                metric_id="working_capital_data_status",
                metric_name=_canonical_metric_name("working_capital_data_status"),
                fiscal_year=year,
                period=year,
                value=None,
                unit="",
                basis=best_facts["payable_days"].basis,
                source_statement="financial_truth_registry",
                source_artifact="financial_truth_registry.json",
                source_line_item="derived:working_capital_data_status",
                source_page=None,
                confidence="medium",
                availability_status="partial",
                derived=True,
                formula="payable-days evidence exists even though direct payables amount is unavailable",
                inputs_used=["payable_days"],
                warnings=["Working-capital evidence is partial because payable-days exist but direct payables are unavailable."],
                reconciliation_status="warning",
                usable_downstream=False,
                notes=[],
            )
        )
    if best_facts.get("closing_shares") and best_facts["closing_shares"].availability_status in {"present_direct", "present_derived"} and best_facts.get("weighted_avg_shares", _fact_from_missing("x", year, "")).availability_status == "missing":
        precise_missing_facts.append(_fact_from_precise_missing("weighted_avg_shares", year, "Closing shares exist, but weighted-average shares are missing."))
        partial_facts.append(
            FinancialFact(
                metric_id="share_count_status",
                metric_name=_canonical_metric_name("share_count_status"),
                fiscal_year=year,
                period=year,
                value=None,
                unit="",
                basis=best_facts["closing_shares"].basis,
                source_statement="financial_truth_registry",
                source_artifact="financial_truth_registry.json",
                source_line_item="derived:share_count_status",
                source_page=None,
                confidence="medium",
                availability_status="partial",
                derived=True,
                formula="closing shares exist but weighted-average denominator is missing",
                inputs_used=["closing_shares"],
                warnings=["Share count is available, but weighted-average shares are missing."],
                reconciliation_status="warning",
                usable_downstream=False,
                notes=[],
            )
        )
    if best_facts.get("eps_diluted") and best_facts["eps_diluted"].availability_status in {"present_direct", "present_derived"} and best_facts.get("weighted_average_diluted_shares", _fact_from_missing("x", year, "")).availability_status == "missing":
        precise_missing_facts.append(_fact_from_precise_missing("weighted_average_diluted_shares", year, "Diluted EPS exists, but diluted share denominator is missing."))
    if best_facts.get("fcf") and best_facts["fcf"].availability_status in {"present_derived"}:
        partial_facts.append(
            FinancialFact(
                metric_id="owner_earnings_readiness",
                metric_name="Owner Earnings Readiness",
                fiscal_year=year,
                period=year,
                value=None,
                unit="",
                basis=best_facts["fcf"].basis,
                source_statement="financial_truth_registry",
                source_artifact="financial_truth_registry.json",
                source_line_item="derived:owner_earnings_readiness",
                source_page=None,
                confidence="medium",
                availability_status="partial",
                derived=True,
                formula="fcf derivable but maintenance/growth capex split may be missing",
                inputs_used=["fcf", "capex"],
                warnings=["Owner earnings estimate is available but may not be precise when maintenance/growth capex split is not disclosed."],
                reconciliation_status="warning",
                usable_downstream=False,
                notes=["Estimate available but not precise."],
            )
        )

    if invalid_facts:
        truth_status = "invalid"
    elif unreliable_facts or unresolved_contradictions:
        truth_status = "partial"
    elif false_missing_warnings or registry_warnings:
        truth_status = "warning"
    else:
        truth_status = "pass"

    reconciliation_report = FinancialTruthReconciliationReport(
        company=company,
        year=year,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        contradictions_found=contradictions_found,
        resolved_contradictions=resolved_contradictions,
        unresolved_contradictions=unresolved_contradictions,
        false_missing_warnings=false_missing_warnings,
        unreliable_metrics=sorted(set(unreliable_metrics)),
        invalid_metrics=sorted(set(invalid_metrics)),
        usable_metrics=sorted(set(usable_metrics)),
        downstream_blockers=sorted(set(downstream_blockers)),
        warning_normalizations=warning_normalizations,
        invalid_artifact_findings=quarantine_findings,
        quarantined_artifacts=[
            {"artifact_name": "shareholding_pattern.json", **shareholding_status},
            {"artifact_name": "corporate_actions.json", **corporate_status},
        ],
        resolved_false_warnings=[
            {
                "original_warning": item["original_warning"],
                "normalized_warning": item["normalized_warning"],
                "affected_metric": item["affected_metric"],
                "resolution_status": item["resolution_status"],
            }
            for item in warning_normalizations
        ],
        warnings=registry_warnings,
    )
    registry = FinancialFactRegistry(
        company=company,
        year=year,
        generated_at=reconciliation_report.generated_at,
        source_artifacts_read=source_artifacts_read,
        registry_warnings=registry_warnings,
        available_facts=sorted(available_facts, key=lambda fact: fact.metric_id),
        derived_facts=sorted(derived_facts, key=lambda fact: fact.metric_id),
        partial_facts=sorted(partial_facts, key=lambda fact: fact.metric_id),
        missing_facts=sorted(missing_facts, key=lambda fact: fact.metric_id),
        precise_missing_facts=sorted(precise_missing_facts, key=lambda fact: fact.metric_id),
        unreliable_facts=sorted(unreliable_facts, key=lambda fact: fact.metric_id),
        invalid_facts=sorted(invalid_facts, key=lambda fact: fact.metric_id),
        quarantined_facts=sorted(registry_quarantined_facts, key=lambda fact: fact.metric_id),
        contradiction_summary={
            "contradictions_found": reconciliation_report.contradictions_found,
            "resolved_contradictions": reconciliation_report.resolved_contradictions,
            "unresolved_contradictions": reconciliation_report.unresolved_contradictions,
            "false_missing_warnings": reconciliation_report.false_missing_warnings,
            "warning_normalizations": reconciliation_report.warning_normalizations,
            "invalid_artifact_findings": reconciliation_report.invalid_artifact_findings,
        },
        downstream_readiness={
            "financial_truth_status": truth_status,
            "usable_metrics": reconciliation_report.usable_metrics,
            "unreliable_metrics": reconciliation_report.unreliable_metrics,
            "invalid_metrics": reconciliation_report.invalid_metrics,
            "quarantined_metrics": sorted(set(quarantined_metrics)),
            "partial_metrics": [fact.metric_id for fact in partial_facts],
            "missing_metrics": [fact.metric_id for fact in missing_facts],
            "precise_missing_metrics": [fact.metric_id for fact in precise_missing_facts],
            "downstream_blockers": reconciliation_report.downstream_blockers,
            "warnings": registry_warnings,
        },
    )
    quarantine_report = FinancialArtifactQuarantineReport(
        company=company,
        fiscal_year=year,
        generated_at=reconciliation_report.generated_at,
        artifact_status_by_file={
            "shareholding_pattern.json": {
                "artifact_name": "shareholding_pattern.json",
                **shareholding_status,
            },
            "corporate_actions.json": {
                "artifact_name": "corporate_actions.json",
                **corporate_status,
            },
        },
        quarantined_facts=quarantine_findings,
        quarantined_artifacts=[
            {"artifact_name": "shareholding_pattern.json", **shareholding_status},
            {"artifact_name": "corporate_actions.json", **corporate_status},
        ],
        usable_artifacts=[
            item
            for item in (
                {"artifact_name": "shareholding_pattern.json", **shareholding_status},
                {"artifact_name": "corporate_actions.json", **corporate_status},
            )
            if item["status"] in {"usable", "usable_with_warnings", "partial"}
        ],
        invalid_reason=[item["invalid_reason"] for item in quarantine_findings],
        affected_metrics=sorted({item["metric_id"] for item in quarantine_findings}),
        downstream_blockers=sorted(set(downstream_blockers + [warning for item in quarantine_findings for warning in item.get("warnings_to_block_downstream", [])])),
        recommended_reparse_targets=sorted(
            {
                item["artifact_name"]
                for item in quarantine_findings
                if item["artifact_name"] in {"shareholding_pattern.json", "corporate_actions.json"}
            }
        ),
        warnings=registry_warnings,
    )
    registry_errors = validate_financial_fact_registry_payload(registry.to_dict())
    if registry_errors:
        raise ValueError("; ".join(registry_errors))
    report_errors = validate_financial_truth_reconciliation_payload(reconciliation_report.to_dict())
    if report_errors:
        raise ValueError("; ".join(report_errors))
    quarantine_errors = validate_financial_artifact_quarantine_payload(quarantine_report.to_dict())
    if quarantine_errors:
        raise ValueError("; ".join(quarantine_errors))
    return registry, reconciliation_report, quarantine_report


def write_financial_fact_registry(
    *,
    company: str,
    year: str,
    financial_root: Path,
    registry_output_path: Path,
    reconciliation_output_path: Path,
    quarantine_output_path: Path,
) -> Tuple[FinancialFactRegistry, FinancialTruthReconciliationReport, FinancialArtifactQuarantineReport]:
    registry, report, quarantine_report = build_financial_fact_registry(
        company=company,
        year=year,
        financial_root=financial_root,
    )
    registry_output_path.parent.mkdir(parents=True, exist_ok=True)
    registry_output_path.write_text(
        json.dumps(registry.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    reconciliation_output_path.parent.mkdir(parents=True, exist_ok=True)
    reconciliation_output_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    quarantine_output_path.parent.mkdir(parents=True, exist_ok=True)
    quarantine_output_path.write_text(
        json.dumps(quarantine_report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return registry, report, quarantine_report
