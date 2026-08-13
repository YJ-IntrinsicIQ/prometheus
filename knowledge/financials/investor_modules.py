from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .financial_memory_truth import build_financial_truth_pack, load_financial_truth_by_year
from .investor_modules_schema import (
    validate_capital_allocation_roi_ledger_payload,
    validate_investor_financial_modules_manifest_payload,
    validate_order_revenue_cash_conversion_tracker_payload,
    validate_owner_earnings_bridge_payload,
    validate_per_share_compounding_analysis_payload,
    validate_working_capital_quality_drilldown_payload,
)


MODULE_DIRNAME = "investor_financial_modules"
MODULE_FILENAMES = {
    "owner_earnings_bridge": "owner_earnings_bridge.json",
    "capital_allocation_roi_ledger": "capital_allocation_roi_ledger.json",
    "working_capital_quality_drilldown": "working_capital_quality_drilldown.json",
    "order_revenue_cash_conversion_tracker": "order_revenue_cash_conversion_tracker.json",
    "per_share_compounding_analysis": "per_share_compounding_analysis.json",
    "investor_financial_modules_manifest": "investor_financial_modules_manifest.json",
}


def _load_optional_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _append_unique(items: List[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _metric_key(metric_id: str) -> str:
    return str(metric_id or "").strip().lower()


def _tokenize_metric_name(value: Any) -> str:
    return _metric_key(str(value or "").replace("-", "_").replace(" ", "_"))


def _fact_value(fact: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(fact, dict):
        return None
    value = fact.get("value")
    if isinstance(value, (int, float)):
        return float(value)
    for key in ("value_crore", "value_per_share", "raw_number", "holding_percent", "amount_crore"):
        raw = fact.get(key)
        if isinstance(raw, (int, float)):
            return float(raw)
    return None


def _fact_artifacts(fact: Optional[Dict[str, Any]]) -> List[str]:
    artifacts: List[str] = []
    if not isinstance(fact, dict):
        return artifacts
    for key in ("source_artifact",):
        if str(fact.get(key) or "").strip():
            _append_unique(artifacts, fact.get(key))
    for item in fact.get("source_artifacts", []) if isinstance(fact.get("source_artifacts"), list) else []:
        _append_unique(artifacts, item)
    return artifacts


def _first_note(fact: Optional[Dict[str, Any]]) -> str:
    if not isinstance(fact, dict):
        return ""
    for field in ("notes", "warnings"):
        values = fact.get(field)
        if isinstance(values, list):
            for item in values:
                text = str(item or "").strip()
                if text:
                    return text
    return ""


def _availability(fact: Optional[Dict[str, Any]]) -> str:
    return str((fact or {}).get("availability_status") or "missing")


def _confidence(fact: Optional[Dict[str, Any]]) -> str:
    return str((fact or {}).get("confidence") or "missing")


def _usable(fact: Optional[Dict[str, Any]]) -> bool:
    return bool((fact or {}).get("usable_downstream"))


def _normalize_facts(bundle: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}
    for metric_id, facts in (bundle.get("fact_map") or {}).items():
        if not facts:
            continue
        normalized[_metric_key(metric_id)] = facts[0]
    return normalized


def _find_fact(bundle: Dict[str, Any], *metric_ids: str) -> Optional[Dict[str, Any]]:
    fact_map = _normalize_facts(bundle)
    for metric_id in metric_ids:
        fact = fact_map.get(_metric_key(metric_id))
        if fact is not None:
            return fact
    return None


def _metric_in_truth_list(items: Sequence[Dict[str, Any]], metric_ids: Sequence[str]) -> bool:
    expected = {_metric_key(metric_id) for metric_id in metric_ids}
    for item in items:
        metric_id = _metric_key(item.get("metric_id") or item.get("metric_name"))
        if metric_id in expected:
            return True
    return False


def _blocked_metric_ids(truth_pack: Dict[str, Any]) -> set[str]:
    blocked: set[str] = set()
    for item in truth_pack.get("invalid_or_quarantined_metrics", []) or []:
        blocked.add(_metric_key(item.get("metric_id") or item.get("metric_name")))
    return blocked


def _unreliable_metric_ids(truth_pack: Dict[str, Any]) -> set[str]:
    blocked: set[str] = set()
    for item in truth_pack.get("unreliable_metrics", []) or []:
        blocked.add(_metric_key(item.get("metric_id") or item.get("metric_name")))
    return blocked


def _precise_missing_ids(truth_pack: Dict[str, Any]) -> set[str]:
    missing: set[str] = set()
    for item in truth_pack.get("precise_missing_metrics", []) or []:
        missing.add(_metric_key(item.get("metric_id") or item.get("metric_name")))
    return missing


def _years_covered(bundles: Dict[str, Dict[str, Any]]) -> List[str]:
    return sorted(bundles.keys(), key=lambda item: int(str(item).lower().replace("fy", "") or "0"))


def _source_provenance(*facts: Optional[Dict[str, Any]], extras: Optional[Iterable[str]] = None) -> List[str]:
    provenance: List[str] = []
    for fact in facts:
        for artifact in _fact_artifacts(fact):
            _append_unique(provenance, artifact)
    for item in extras or []:
        _append_unique(provenance, item)
    return provenance


def _fact_unit(fact: Optional[Dict[str, Any]]) -> str:
    return str((fact or {}).get("unit") or (fact or {}).get("unit_original") or "").strip().lower()


def _fact_share_denominator(fact: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(fact, dict):
        return None
    if isinstance(fact.get("raw_number"), (int, float)):
        return float(fact.get("raw_number"))
    if isinstance(fact.get("value_shares"), (int, float)):
        return float(fact.get("value_shares"))
    if isinstance(fact.get("value"), (int, float)):
        unit = _fact_unit(fact)
        value = float(fact.get("value"))
        if "crore shares" in unit:
            return value * 10_000_000.0
        return value
    if isinstance(fact.get("crore_shares"), (int, float)):
        return float(fact.get("crore_shares")) * 10_000_000.0
    return None


def _fact_crore_value(fact: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(fact, dict):
        return None
    if isinstance(fact.get("value_crore"), (int, float)):
        return float(fact.get("value_crore"))
    if isinstance(fact.get("amount_crore"), (int, float)):
        return float(fact.get("amount_crore"))
    if isinstance(fact.get("value"), (int, float)):
        unit = _fact_unit(fact)
        value = float(fact.get("value"))
        if unit in {"₹ crore", "crore", "crores", "cr"}:
            return value
    return None


def _direct_per_share_metric_metadata(metric_id: str, value: Optional[float], *, source_unit: str = "INR/share") -> Dict[str, Any]:
    return {
        "metric_id": metric_id,
        "value": value,
        "value_per_share": value,
        "unit": "INR/share",
        "numerator_metric": metric_id,
        "numerator_value": value,
        "numerator_unit": source_unit,
        "denominator_metric": "",
        "denominator_value": None,
        "denominator_unit": "",
        "calculation_formula": "reported_directly",
        "share_count_basis": "reported_directly",
        "source_unit": source_unit,
        "warnings": [],
    }


def _derived_per_share_metric_metadata(
    metric_id: str,
    *,
    numerator_metric: str,
    numerator_value_crore: Optional[float],
    denominator_metric: str,
    denominator_value: Optional[float],
    share_count_basis: str,
    warning: str = "",
) -> Tuple[Optional[float], Dict[str, Any]]:
    value_per_share = (
        numerator_value_crore * 10_000_000.0 / denominator_value
        if numerator_value_crore is not None and denominator_value not in (None, 0)
        else None
    )
    warnings: List[str] = []
    if warning:
        warnings.append(warning)
    return value_per_share, {
        "metric_id": metric_id,
        "value": value_per_share,
        "value_per_share": value_per_share,
        "unit": "INR/share",
        "numerator_metric": numerator_metric,
        "numerator_value": numerator_value_crore,
        "numerator_unit": "INR crore",
        "denominator_metric": denominator_metric,
        "denominator_value": denominator_value,
        "denominator_unit": "shares",
        "calculation_formula": f"{numerator_metric}_value_crore * 10000000 / {denominator_metric}",
        "share_count_basis": share_count_basis,
        "source_unit": "derived",
        "warnings": warnings,
    }


def _status_from_entries(entries: Sequence[Dict[str, Any]], primary_field: str) -> str:
    if not entries:
        return "skipped"
    statuses = [str(item.get(primary_field) or "").strip().lower() for item in entries]
    if any(status in {"unavailable", "unreliable", "insufficient_data"} for status in statuses):
        return "partial"
    if any(status in {"partial", "estimate_available", "partially_measurable", "watch", "stretched", "comparability_partial"} for status in statuses):
        return "warning"
    return "pass"


def _build_owner_earnings_bridge(company: str, bundles: Dict[str, Dict[str, Any]], truth_pack: Dict[str, Any]) -> Dict[str, Any]:
    bridges: List[Dict[str, Any]] = []
    warnings: List[str] = []
    limitations: List[str] = []
    invalid_metrics = _blocked_metric_ids(truth_pack)
    unreliable_metrics = _unreliable_metric_ids(truth_pack)

    for year in _years_covered(bundles):
        bundle = bundles[year]
        cfo = _find_fact(bundle, "cfo")
        pat = _find_fact(bundle, "pat")
        dep = _find_fact(bundle, "depreciation_and_amortization", "depreciation", "amortization")
        capex = _find_fact(bundle, "capex", "total_capex_for_fcf")
        ppe_capex = _find_fact(bundle, "ppe_cwip_capex", "ppe_capex", "cwip_capex")
        intangible_capex = _find_fact(bundle, "intangible_capex", "capitalized_product_development")
        maintenance = _find_fact(bundle, "estimated_maintenance_capex", "maintenance_capex")
        growth = _find_fact(bundle, "estimated_growth_capex", "growth_capex")

        item_warnings: List[str] = []
        if _metric_key("cfo") in invalid_metrics or _metric_key("capex") in invalid_metrics:
            precision_status = "unavailable"
            item_warnings.append("Owner-earnings bridge is blocked because a required fact is invalid or quarantined.")
        elif _metric_key("cfo") in unreliable_metrics or _metric_key("capex") in unreliable_metrics:
            precision_status = "partial"
            item_warnings.append("Owner-earnings bridge uses unreliable CFO or capex evidence and should be treated cautiously.")
        elif _fact_value(cfo) is not None and _fact_value(capex) is not None:
            precision_status = "precise" if _fact_value(maintenance) is not None or _fact_value(growth) is not None else "estimate_available"
            if precision_status == "estimate_available":
                item_warnings.append("Maintenance versus growth capex split is not disclosed, so owner-earnings precision is limited.")
        elif _fact_value(cfo) is not None or _fact_value(capex) is not None:
            precision_status = "partial"
            item_warnings.append("Only part of the owner-earnings bridge is available.")
        else:
            precision_status = "unavailable"
            item_warnings.append("Owner-earnings bridge cannot be built because CFO or capex evidence is absent.")

        cfo_value = _fact_value(cfo)
        capex_value = _fact_value(capex)
        ppe_value = _fact_value(ppe_capex)
        intangible_value = _fact_value(intangible_capex)
        identified_capex = None
        if ppe_value is not None or intangible_value is not None:
            identified_capex = float((ppe_value or 0.0) + (intangible_value or 0.0))
        elif capex_value is not None:
            identified_capex = capex_value
        maintenance_value = _fact_value(maintenance)
        growth_value = _fact_value(growth)
        fcf_after_ppe = cfo_value + ppe_value if cfo_value is not None and ppe_value is not None else None
        conservative_fcf = cfo_value + identified_capex if cfo_value is not None and identified_capex is not None else None
        owner_estimate = None
        if cfo_value is not None and maintenance_value is not None:
            owner_estimate = cfo_value + maintenance_value
        elif conservative_fcf is not None:
            owner_estimate = conservative_fcf

        split_status = "available" if maintenance_value is not None or growth_value is not None else "missing"
        bridges.append(
            {
                "fiscal_year": year,
                "cfo": cfo_value,
                "reported_pat": _fact_value(pat),
                "depreciation_and_amortization": _fact_value(dep),
                "ppe_cwip_capex": ppe_value,
                "intangible_capex": intangible_value,
                "total_identified_capex": identified_capex,
                "estimated_maintenance_capex": maintenance_value,
                "estimated_growth_capex": growth_value,
                "maintenance_growth_split_status": split_status,
                "fcf_after_ppe_cwip_capex": fcf_after_ppe,
                "conservative_fcf_after_total_capex": conservative_fcf,
                "owner_earnings_estimate": owner_estimate,
                "owner_earnings_precision_status": precision_status,
                "owner_earnings_warnings": item_warnings,
                "source_provenance": _source_provenance(cfo, pat, dep, capex, ppe_capex, intangible_capex, maintenance, growth),
            }
        )
        for warning in item_warnings:
            _append_unique(warnings, f"{year}: {warning}")

    payload = {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years_covered": _years_covered(bundles),
        "bridges": bridges,
        "warnings": warnings,
        "limitations": limitations,
    }
    errors = validate_owner_earnings_bridge_payload(payload)
    if errors:
        raise ValueError("Invalid owner earnings bridge payload: " + "; ".join(errors))
    return payload


def _build_capital_allocation_roi_ledger(company: str, bundles: Dict[str, Dict[str, Any]], truth_pack: Dict[str, Any]) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    warnings: List[str] = []
    limitations: List[str] = []
    invalid_metrics = _blocked_metric_ids(truth_pack)
    unreliable_metrics = _unreliable_metric_ids(truth_pack)

    for year in _years_covered(bundles):
        bundle = bundles[year]
        capital_raised = _find_fact(bundle, "capital_raised", "qip_proceeds", "ipo_proceeds", "equity_raised")
        retained_earnings = _find_fact(bundle, "retained_earnings")
        capex = _find_fact(bundle, "capex", "total_capex_for_fcf")
        working_capital = _find_fact(bundle, "working_capital_deployed", "working_capital_investment")
        intangible = _find_fact(bundle, "product_development_or_intangible_investment", "intangible_capex", "capitalized_product_development")
        debt_repayment = _find_fact(bundle, "debt_repayment")
        dividends = _find_fact(bundle, "dividends_paid", "dividend_paid")
        buybacks = _find_fact(bundle, "buybacks", "buyback")
        acquisitions = _find_fact(bundle, "acquisitions", "acquisition")
        related_party = _find_fact(bundle, "related_party_flows", "related_party")
        unutilised = _find_fact(bundle, "unutilised_issue_proceeds", "unused_issue_proceeds")
        revenue = _find_fact(bundle, "revenue")
        roce = _find_fact(bundle, "roce")
        cfo = _find_fact(bundle, "cfo")

        investor_interpretation = "Capital actions require more follow-up."
        roi_status = "not_yet_measurable"
        item_warnings: List[str] = []
        if _metric_key("capital_raised") in invalid_metrics or _metric_key("qip_proceeds") in invalid_metrics:
            roi_status = "unreliable"
            investor_interpretation = "Capital-raising evidence is invalid or quarantined."
            item_warnings.append("Capital-raising evidence is invalid or quarantined and should not drive investor conclusions.")
        elif any(_metric_key(metric) in unreliable_metrics for metric in ("capital_raised", "qip_proceeds", "capex")):
            roi_status = "unreliable"
            investor_interpretation = "Capital-allocation evidence is available but unreliable."
            item_warnings.append("Capital-allocation evidence is unreliable and should be interpreted cautiously.")
        elif _fact_value(unutilised) not in (None, 0):
            roi_status = "not_yet_measurable"
            investor_interpretation = "Raised capital remains pending deployment."
        elif _fact_value(capex) is not None or _fact_value(working_capital) is not None or _fact_value(intangible) is not None:
            if any(_fact_value(item) is not None for item in (revenue, roce, cfo)):
                roi_status = "partially_measurable"
                investor_interpretation = "Capital has been deployed, but later outcome attribution remains partial."
            else:
                roi_status = "not_yet_measurable"
                investor_interpretation = "Capital has been deployed, but later outcome evidence is not yet available."
        elif _fact_value(capital_raised) is None and _fact_value(retained_earnings) is None and _fact_value(capex) is None:
            roi_status = "not_yet_measurable"
            investor_interpretation = "No clear capital-allocation event was captured."

        amount = next(
            (
                _fact_value(item)
                for item in (
                    capital_raised,
                    capex,
                    working_capital,
                    intangible,
                    debt_repayment,
                    dividends,
                    buybacks,
                    acquisitions,
                )
                if _fact_value(item) is not None
            ),
            None,
        )
        if _fact_value(unutilised) not in (None, 0):
            event_type = "pending_deployment"
            purpose = "Raised capital is still not fully deployed."
        elif _fact_value(capital_raised) is not None:
            event_type = "capital_raised"
            purpose = "Fresh capital has been raised."
        elif _fact_value(capex) is not None:
            event_type = "operating_reinvestment"
            purpose = "Capital is being deployed into operating assets."
        elif _fact_value(dividends) is not None or _fact_value(buybacks) is not None:
            event_type = "shareholder_return"
            purpose = "Capital is being returned to shareholders."
        elif _fact_value(debt_repayment) is not None:
            event_type = "deleveraging"
            purpose = "Capital is being used to reduce debt."
        else:
            event_type = "unclear"
            purpose = "No clear capital-allocation event was identified."

        follow_up_questions: List[str] = []
        if roi_status == "not_yet_measurable":
            follow_up_questions.append("What later revenue, margin, CFO, or ROIC outcomes can be linked to this capital deployment?")
        if _fact_value(unutilised) not in (None, 0):
            follow_up_questions.append("When will the unutilised capital be deployed, and into which specific uses?")

        entries.append(
            {
                "fiscal_year": year,
                "capital_raised": _fact_value(capital_raised),
                "retained_earnings": _fact_value(retained_earnings),
                "capex_deployed": _fact_value(capex),
                "working_capital_deployed": _fact_value(working_capital),
                "product_development_or_intangible_investment": _fact_value(intangible),
                "debt_repayment": _fact_value(debt_repayment),
                "dividends": _fact_value(dividends),
                "buybacks": _fact_value(buybacks),
                "acquisitions": _fact_value(acquisitions),
                "related_party_flows": _fact_value(related_party),
                "unutilised_issue_proceeds": _fact_value(unutilised),
                "capital_allocation_event_type": event_type,
                "amount": amount,
                "purpose": purpose,
                "source": _source_provenance(capital_raised, retained_earnings, capex, working_capital, intangible, debt_repayment, dividends, buybacks, acquisitions, related_party, unutilised),
                "reliability": "unreliable" if roi_status == "unreliable" else "usable",
                "investor_interpretation": investor_interpretation,
                "roi_measurability_status": roi_status,
                "follow_up_questions": follow_up_questions,
            }
        )
        for warning in item_warnings:
            _append_unique(warnings, f"{year}: {warning}")

    payload = {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years_covered": _years_covered(bundles),
        "entries": entries,
        "warnings": warnings,
        "limitations": limitations,
    }
    errors = validate_capital_allocation_roi_ledger_payload(payload)
    if errors:
        raise ValueError("Invalid capital allocation roi ledger payload: " + "; ".join(errors))
    return payload


def _build_working_capital_quality_drilldown(company: str, bundles: Dict[str, Dict[str, Any]], truth_pack: Dict[str, Any]) -> Dict[str, Any]:
    drilldown: List[Dict[str, Any]] = []
    warnings: List[str] = []
    limitations: List[str] = []
    precise_missing_ids = _precise_missing_ids(truth_pack)

    for year in _years_covered(bundles):
        bundle = bundles[year]
        receivables = _find_fact(bundle, "receivables")
        inventory = _find_fact(bundle, "inventory", "inventories")
        payables = _find_fact(bundle, "payables")
        receivable_days = _find_fact(bundle, "receivable_days")
        inventory_days = _find_fact(bundle, "inventory_days")
        payable_days = _find_fact(bundle, "payable_days")
        ccc = _find_fact(bundle, "cash_conversion_cycle")
        revenue_growth = _find_fact(bundle, "revenue_growth", "revenue_growth_percent")
        receivables_growth = _find_fact(bundle, "receivables_growth", "receivables_growth_percent")
        inventory_growth = _find_fact(bundle, "inventory_growth", "inventory_growth_percent")

        rec_days = _fact_value(receivable_days)
        inv_days = _fact_value(inventory_days)
        pay_days = _fact_value(payable_days)
        ccc_value = _fact_value(ccc)
        severity_score = 0
        for value in (rec_days, inv_days, ccc_value):
            if value is None:
                continue
            if value >= 150:
                severity_score = max(severity_score, 4)
            elif value >= 90:
                severity_score = max(severity_score, 3)
            elif value >= 60:
                severity_score = max(severity_score, 2)
            else:
                severity_score = max(severity_score, 1)
        intensity = {0: "insufficient_data", 1: "healthy", 2: "watch", 3: "stretched", 4: "severe"}[severity_score]

        quality_questions: List[str] = []
        if rec_days is not None and rec_days >= 90:
            quality_questions.append("Are receivable days elevated because of billing cycles, milestone collection, or collectability pressure?")
        if inv_days is not None and inv_days >= 90:
            quality_questions.append("Do inventory days reflect ageing, obsolescence, or a long project/production cycle?")
        if pay_days is None and _metric_key("payables") in precise_missing_ids:
            quality_questions.append("Which payable component is missing, and does that limit cash-conversion interpretation?")
        if pay_days is not None:
            payable_support_quality = "available"
        elif _fact_value(payables) is not None:
            payable_support_quality = "present_but_days_unavailable"
        else:
            payable_support_quality = "missing"
        cash_strain_risk = "elevated" if intensity in {"stretched", "severe"} else ("watch" if intensity == "watch" else "contained")

        rec_vs_rev = None
        if _fact_value(receivables_growth) is not None and _fact_value(revenue_growth) is not None:
            rec_vs_rev = float(_fact_value(receivables_growth) - _fact_value(revenue_growth))
        inv_vs_rev = None
        if _fact_value(inventory_growth) is not None and _fact_value(revenue_growth) is not None:
            inv_vs_rev = float(_fact_value(inventory_growth) - _fact_value(revenue_growth))

        item = {
            "fiscal_year": year,
            "receivables": _fact_value(receivables),
            "inventory": _fact_value(inventory),
            "payables": _fact_value(payables),
            "receivable_days": rec_days,
            "inventory_days": inv_days,
            "payable_days": pay_days,
            "cash_conversion_cycle": ccc_value,
            "receivables_growth_vs_revenue_growth": rec_vs_rev,
            "inventory_growth_vs_revenue_growth": inv_vs_rev,
            "payable_support_quality": payable_support_quality,
            "working_capital_intensity_status": intensity,
            "cash_strain_risk": cash_strain_risk,
            "quality_questions": quality_questions,
            "source_provenance": _source_provenance(receivables, inventory, payables, receivable_days, inventory_days, payable_days, ccc, revenue_growth, receivables_growth, inventory_growth),
        }
        drilldown.append(item)
        if pay_days is None and _fact_value(payables) is not None:
            _append_unique(warnings, f"{year}: Payables are present, but payable-days evidence is incomplete.")
        if len(_years_covered(bundles)) == 1:
            _append_unique(limitations, "Only one year is available, so working-capital analysis is a current-year snapshot rather than a trend.")

    payload = {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years_covered": _years_covered(bundles),
        "drilldown": drilldown,
        "warnings": warnings,
        "limitations": limitations,
    }
    errors = validate_working_capital_quality_drilldown_payload(payload)
    if errors:
        raise ValueError("Invalid working capital quality drilldown payload: " + "; ".join(errors))
    return payload


def _build_order_revenue_cash_conversion_tracker(company: str, bundles: Dict[str, Dict[str, Any]], truth_pack: Dict[str, Any]) -> Dict[str, Any]:
    tracker: List[Dict[str, Any]] = []
    warnings: List[str] = []
    limitations: List[str] = []

    for year in _years_covered(bundles):
        bundle = bundles[year]
        order_book = _find_fact(bundle, "order_book")
        order_inflow = _find_fact(bundle, "order_inflow")
        revenue = _find_fact(bundle, "revenue")
        receivables = _find_fact(bundle, "receivables")
        inventory = _find_fact(bundle, "inventory", "inventories")
        advances = _find_fact(bundle, "advances_from_customers")
        deferred = _find_fact(bundle, "deferred_revenue", "contract_liabilities", "deferred_revenue_or_contract_liabilities")
        cfo = _find_fact(bundle, "cfo")
        fcf = _find_fact(bundle, "fcf")
        receivable_days = _find_fact(bundle, "receivable_days")
        inventory_days = _find_fact(bundle, "inventory_days")

        conversion_status = "insufficient_data"
        order_visibility = "Order-book evidence is not available."
        revenue_cash_visibility = "Revenue-to-cash conversion evidence is limited."
        questions: List[str] = []

        if _fact_value(order_book) is not None or _fact_value(order_inflow) is not None:
            order_visibility = "Order-book or order-inflow evidence exists."
        if _fact_value(revenue) is not None and _fact_value(cfo) is not None:
            revenue_cash_visibility = "Revenue and cash evidence can be compared."
            conversion_status = "strong"
            if (_fact_value(receivable_days) or 0) >= 90 or (_fact_value(inventory_days) or 0) >= 90:
                conversion_status = "watch"
                questions.append("Why are receivables or inventory rising relative to revenue conversion?")
            if _fact_value(fcf) is not None and _fact_value(fcf) < 0:
                conversion_status = "stretched"
                questions.append("What is preventing revenue from converting into free cash flow?")
        elif _fact_value(revenue) is not None:
            conversion_status = "watch"
            revenue_cash_visibility = "Revenue exists, but cash conversion cannot be fully checked without CFO."
        if _fact_value(order_book) is None and _fact_value(revenue) is not None:
            questions.append("What evidence is available on forward demand if order-book disclosure is absent?")

        tracker.append(
            {
                "fiscal_year": year,
                "order_book": _fact_value(order_book),
                "order_inflow": _fact_value(order_inflow),
                "revenue": _fact_value(revenue),
                "execution_timeline": _first_note(order_book) or _first_note(order_inflow),
                "receivables": _fact_value(receivables),
                "inventory": _fact_value(inventory),
                "advances_from_customers": _fact_value(advances),
                "deferred_revenue_or_contract_liabilities": _fact_value(deferred),
                "cfo": _fact_value(cfo),
                "fcf": _fact_value(fcf),
                "conversion_status": conversion_status,
                "order_to_revenue_visibility": order_visibility,
                "revenue_to_cash_visibility": revenue_cash_visibility,
                "cash_conversion_questions": questions,
                "source_provenance": _source_provenance(order_book, order_inflow, revenue, receivables, inventory, advances, deferred, cfo, fcf, receivable_days, inventory_days),
            }
        )

    payload = {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years_covered": _years_covered(bundles),
        "tracker": tracker,
        "warnings": warnings,
        "limitations": limitations,
    }
    errors = validate_order_revenue_cash_conversion_tracker_payload(payload)
    if errors:
        raise ValueError("Invalid order revenue cash conversion tracker payload: " + "; ".join(errors))
    return payload


def _corporate_actions_by_year(company_root: Path) -> Dict[str, List[Dict[str, Any]]]:
    actions_by_year: Dict[str, List[Dict[str, Any]]] = {}
    for year_dir in company_root.iterdir() if company_root.exists() else []:
        if not year_dir.is_dir() or not year_dir.name.lower().startswith("fy"):
            continue
        payload = _load_optional_json(year_dir / "financials" / "corporate_actions.json") or {}
        actions = payload.get("actions") or payload.get("corporate_actions") or []
        if not isinstance(actions, list):
            actions = []
        actions_by_year[year_dir.name] = [item for item in actions if isinstance(item, dict)]
    return actions_by_year


def _build_per_share_compounding_analysis(
    company: str,
    bundles: Dict[str, Dict[str, Any]],
    truth_pack: Dict[str, Any],
    company_root: Path,
    owner_bridge_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    analysis: List[Dict[str, Any]] = []
    warnings: List[str] = []
    limitations: List[str] = []
    actions_by_year = _corporate_actions_by_year(company_root)
    invalid_metrics = _blocked_metric_ids(truth_pack)
    unreliable_metrics = _unreliable_metric_ids(truth_pack)
    owner_bridge_by_year = {
        str(item.get("fiscal_year") or "").strip(): item
        for item in (owner_bridge_payload or {}).get("bridges", []) or []
        if isinstance(item, dict) and str(item.get("fiscal_year") or "").strip()
    }

    previous_closing_shares: Optional[float] = None
    for year in _years_covered(bundles):
        bundle = bundles[year]
        closing = _find_fact(bundle, "closing_shares", "shares_outstanding", "share_count")
        weighted = _find_fact(bundle, "weighted_avg_shares")
        diluted = _find_fact(bundle, "weighted_average_diluted_shares", "diluted_shares")
        eps_basic = _find_fact(bundle, "eps_basic")
        eps_diluted = _find_fact(bundle, "eps_diluted")
        bvps = _find_fact(bundle, "book_value_per_share")
        fcf = _find_fact(bundle, "fcf")
        dividend_per_share = _find_fact(bundle, "dividend_per_share")
        owner_bridge = owner_bridge_by_year.get(year) or {}

        closing_value = _fact_value(closing)
        weighted_value = _fact_value(weighted)
        diluted_value = _fact_value(diluted)
        closing_shares = _fact_share_denominator(closing)
        weighted_shares = _fact_share_denominator(weighted)
        denominator = weighted_shares if weighted_shares is not None else closing_shares
        denominator_metric = "weighted_average_basic_shares" if weighted_shares not in (None, 0) else "closing_shares"
        share_count_basis = denominator_metric
        fcf_crore = _fact_crore_value(fcf)
        fcf_per_share_warning = ""
        if denominator not in (None, 0) and weighted_shares in (None, 0):
            fcf_per_share_warning = (
                "Weighted-average shares unavailable; calculated using closing shares."
            )
        fcf_per_share, fcf_meta = _derived_per_share_metric_metadata(
            "fcf_per_share",
            numerator_metric="fcf",
            numerator_value_crore=fcf_crore,
            denominator_metric=denominator_metric,
            denominator_value=denominator,
            share_count_basis=share_count_basis,
            warning=fcf_per_share_warning,
        )
        owner_earnings_crore = (
            float(owner_bridge.get("owner_earnings_estimate"))
            if isinstance(owner_bridge.get("owner_earnings_estimate"), (int, float))
            else None
        )
        owner_earnings_per_share, owner_meta = _derived_per_share_metric_metadata(
            "owner_earnings_per_share",
            numerator_metric="owner_earnings_estimate",
            numerator_value_crore=owner_earnings_crore,
            denominator_metric=denominator_metric,
            denominator_value=denominator,
            share_count_basis=share_count_basis,
            warning=fcf_per_share_warning if owner_earnings_crore is not None else "",
        )
        fcf_per_share_confidence = "high" if weighted_shares not in (None, 0) else "medium"
        if fcf_per_share is not None and weighted_shares in (None, 0):
            fcf_per_share_note = "FCF/share using closing shares; precision limited because weighted-average shares are unavailable."
        else:
            fcf_per_share_note = ""
        share_change = None
        if closing_value is not None and previous_closing_shares not in (None, 0):
            share_change = closing_value - previous_closing_shares
        previous_closing_shares = closing_value if closing_value is not None else previous_closing_shares

        qip_effect = "none"
        bonus_split_effect = "none"
        dilution_status = "no_material_dilution_detected"
        year_actions = actions_by_year.get(year, [])
        for action in year_actions:
            action_type = _metric_key(action.get("action_type") or action.get("action_subtype"))
            if "qip" in action_type or "preferential" in action_type or "rights" in action_type or "equity_issue" in action_type:
                qip_effect = "equity issuance affects per-share comparability"
                dilution_status = "dilution_warning"
            if "bonus" in action_type or "split" in action_type or "subdivision" in action_type:
                bonus_split_effect = "bonus or split affects comparability but is not economic dilution"
                if dilution_status != "dilution_warning":
                    dilution_status = "comparability_partial"

        if closing_value is not None and weighted_value is None:
            if dilution_status != "dilution_warning":
                dilution_status = "comparability_partial"
            _append_unique(warnings, f"{year}: Closing shares are present, but weighted-average shares are missing for EPS comparability.")
        if _metric_key("closing_shares") in invalid_metrics or _metric_key("shares_outstanding") in invalid_metrics:
            dilution_status = "unreliable"
        elif any(_metric_key(metric) in unreliable_metrics for metric in ("closing_shares", "weighted_avg_shares", "diluted_shares")):
            dilution_status = "unreliable"
        elif closing_value is None and weighted_value is None and diluted_value is None:
            dilution_status = "insufficient_data"

        per_share_status = "usable" if denominator not in (None, 0) else "limited"
        per_share_metric_metadata = {
            "eps_basic": _direct_per_share_metric_metadata("eps_basic", _fact_value(eps_basic)),
            "eps_diluted": _direct_per_share_metric_metadata("eps_diluted", _fact_value(eps_diluted)),
            "book_value_per_share": _direct_per_share_metric_metadata("book_value_per_share", _fact_value(bvps)),
            "dividend_per_share": _direct_per_share_metric_metadata("dividend_per_share", _fact_value(dividend_per_share)),
            "fcf_per_share": fcf_meta,
        }
        if owner_earnings_per_share is not None:
            per_share_metric_metadata["owner_earnings_per_share"] = owner_meta

        analysis.append(
            {
                "fiscal_year": year,
                "closing_shares": closing_value,
                "weighted_average_basic_shares": weighted_value,
                "weighted_average_diluted_shares": diluted_value,
                "eps_basic": _fact_value(eps_basic),
                "eps_diluted": _fact_value(eps_diluted),
                "book_value_per_share": _fact_value(bvps),
                "fcf_per_share": fcf_per_share,
                "owner_earnings_per_share": owner_earnings_per_share,
                "fcf_per_share_unit": "INR/share" if fcf_per_share is not None else "",
                "fcf_per_share_numerator_unit": "INR crore" if fcf_per_share is not None else "",
                "fcf_per_share_denominator_unit": "shares" if fcf_per_share is not None else "",
                "fcf_per_share_calculation_formula": (
                    "fcf_value_crore * 10000000 / weighted_average_basic_shares"
                    if fcf_per_share is not None and weighted_shares not in (None, 0)
                    else "fcf_value_crore * 10000000 / closing_shares"
                    if fcf_per_share is not None and closing_shares not in (None, 0)
                    else ""
                ),
                "fcf_per_share_confidence": fcf_per_share_confidence if fcf_per_share is not None else "missing",
                "fcf_per_share_warning": fcf_per_share_warning,
                "fcf_per_share_note": fcf_per_share_note,
                "dividend_per_share": _fact_value(dividend_per_share),
                "per_share_metric_metadata": per_share_metric_metadata,
                "share_count_change": share_change,
                "qip_or_equity_issuance_effect": qip_effect,
                "bonus_or_split_effect": bonus_split_effect,
                "dilution_status": dilution_status,
                "per_share_compounding_status": per_share_status,
                "source_provenance": _source_provenance(closing, weighted, diluted, eps_basic, eps_diluted, bvps, fcf, dividend_per_share, extras=["corporate_actions.json"] if year_actions else []),
            }
        )

    payload = {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "years_covered": _years_covered(bundles),
        "analysis": analysis,
        "warnings": warnings,
        "limitations": limitations,
    }
    errors = validate_per_share_compounding_analysis_payload(payload)
    if errors:
        raise ValueError("Invalid per share compounding analysis payload: " + "; ".join(errors))
    return payload


def build_investor_financial_modules(*, company: str, company_root: Path) -> Dict[str, Dict[str, Any]]:
    bundles = load_financial_truth_by_year(company_root=company_root)
    if not bundles:
        raise RuntimeError(f"investor_financials requires at least one financial year for {company}")
    truth_pack = build_financial_truth_pack(company=company, company_root=company_root)
    modules_dir = company_root / "company_memory" / "financials" / MODULE_DIRNAME
    owner = _build_owner_earnings_bridge(company, bundles, truth_pack)
    capital = _build_capital_allocation_roi_ledger(company, bundles, truth_pack)
    working = _build_working_capital_quality_drilldown(company, bundles, truth_pack)
    order = _build_order_revenue_cash_conversion_tracker(company, bundles, truth_pack)
    per_share = _build_per_share_compounding_analysis(company, bundles, truth_pack, company_root, owner)

    manifest = {
        "company": company,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "modules_run": [
            "owner_earnings_bridge",
            "capital_allocation_roi_ledger",
            "working_capital_quality_drilldown",
            "order_revenue_cash_conversion_tracker",
            "per_share_compounding_analysis",
        ],
        "module_statuses": {
            "owner_earnings_bridge": _status_from_entries(owner["bridges"], "owner_earnings_precision_status"),
            "capital_allocation_roi_ledger": _status_from_entries(capital["entries"], "roi_measurability_status"),
            "working_capital_quality_drilldown": _status_from_entries(working["drilldown"], "working_capital_intensity_status"),
            "order_revenue_cash_conversion_tracker": _status_from_entries(order["tracker"], "conversion_status"),
            "per_share_compounding_analysis": _status_from_entries(per_share["analysis"], "dilution_status"),
        },
        "source_truth_pack_used": {
            "years_covered": list(truth_pack.get("years_covered", [])),
            "generated_at": truth_pack.get("generated_at"),
        },
        "usable_domains": [
            "owner_earnings_bridge",
            "capital_allocation_roi",
            "working_capital_quality",
            "revenue_to_cash_conversion",
            "per_share_compounding",
        ],
        "limited_domains": list(
            dict.fromkeys(
                owner["limitations"]
                + capital["limitations"]
                + working["limitations"]
                + order["limitations"]
                + per_share["limitations"]
            )
        ),
        "blocked_domains": sorted({_metric_key(item.get("metric_id") or item.get("metric_name")) for item in truth_pack.get("invalid_or_quarantined_metrics", []) or []}),
        "warnings": list(
            dict.fromkeys(
                owner["warnings"]
                + capital["warnings"]
                + working["warnings"]
                + order["warnings"]
                + per_share["warnings"]
            )
        ),
        "limitations": list(
            dict.fromkeys(
                owner["limitations"]
                + capital["limitations"]
                + working["limitations"]
                + order["limitations"]
                + per_share["limitations"]
            )
        ),
        "recommended_next_investor_questions": list(
            dict.fromkeys(
                truth_pack.get("investor_relevant_questions", [])
                + [q for entry in capital["entries"] for q in entry.get("follow_up_questions", [])]
                + [q for entry in working["drilldown"] for q in entry.get("quality_questions", [])]
                + [q for entry in order["tracker"] for q in entry.get("cash_conversion_questions", [])]
            )
        ),
        "investor_financial_intelligence_pack": {
            "owner_earnings_bridge_summary": [item.get("owner_earnings_precision_status") for item in owner["bridges"]],
            "capital_allocation_roi_summary": [item.get("roi_measurability_status") for item in capital["entries"]],
            "working_capital_quality_summary": [item.get("working_capital_intensity_status") for item in working["drilldown"]],
            "order_revenue_cash_conversion_summary": [item.get("conversion_status") for item in order["tracker"]],
            "per_share_compounding_summary": [item.get("dilution_status") for item in per_share["analysis"]],
            "key_financial_questions": list(
                dict.fromkeys(
                    truth_pack.get("investor_relevant_questions", [])
                    + [q for entry in capital["entries"] for q in entry.get("follow_up_questions", [])]
                )
            ),
            "blocked_claims": [item.get("original_warning") for item in truth_pack.get("financial_warnings_blocked_downstream", []) or []],
            "allowed_claims": list(truth_pack.get("financial_warnings_allowed_downstream", [])),
            "source_provenance": [str((modules_dir / name).name) for name in MODULE_FILENAMES.values() if name != "investor_financial_modules_manifest.json"],
        },
    }
    errors = validate_investor_financial_modules_manifest_payload(manifest)
    if errors:
        raise ValueError("Invalid investor financial modules manifest payload: " + "; ".join(errors))
    return {
        MODULE_FILENAMES["owner_earnings_bridge"]: owner,
        MODULE_FILENAMES["capital_allocation_roi_ledger"]: capital,
        MODULE_FILENAMES["working_capital_quality_drilldown"]: working,
        MODULE_FILENAMES["order_revenue_cash_conversion_tracker"]: order,
        MODULE_FILENAMES["per_share_compounding_analysis"]: per_share,
        MODULE_FILENAMES["investor_financial_modules_manifest"]: manifest,
    }


def write_investor_financial_modules(*, company: str, company_root: Path, output_dir: Path) -> Dict[str, Path]:
    payloads = build_investor_financial_modules(company=company, company_root=company_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}
    for filename, payload in payloads.items():
        path = output_dir / filename
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        written[filename] = path
    return written
