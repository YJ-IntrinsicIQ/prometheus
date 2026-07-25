from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, List, Tuple

PCIM_SECTION_NAME_DENYLIST = {
    "business_understanding",
    "business_economics_inputs",
    "moat_inputs",
    "financial_fundamentals_inputs",
    "financial_growth_inputs",
    "profitability_inputs",
    "cash_conversion_inputs",
    "return_on_capital_inputs",
    "balance_sheet_strength_inputs",
    "financial_quality_inputs",
    "per_share_inputs",
    "financial_driver_inputs",
    "multi_year_financial_inputs",
    "capital_allocation_inputs",
    "management_quality_inputs",
    "governance_and_incentive_inputs",
    "working_capital_inputs",
    "growth_execution_inputs",
    "growth_quality_inputs",
    "risk_inputs",
    "ownership_inputs",
    "corporate_action_inputs",
    "multi_year_inputs",
    "evidence_map",
    "uncertainty_missing_data",
}

GENERIC_GOVERNANCE_LIMITATION = (
    "Governance or incentive evidence is incomplete in the available record, so a stronger governance conclusion cannot be made."
)

FINANCIAL_WARNING_DIAGNOSTIC_TOKENS = (
    "artifact",
    "artifacts",
    ".json",
    "financial_audit_report",
    "normalized_fundamentals",
    "financial_validation_report",
    "financial_reconciliation_report",
    "financial_ratios",
    "financial_growth",
    "financial_quality_summary",
    "corporate_actions",
    "shareholding_pattern",
    "financial_year_index",
    "financial_memory_summary",
    "stale relative",
    "derived value used",
    "missing reconciliation check",
    "field has no populated normalized value",
    "current-year reconciliation blocks cagr",
)

CLAIM_TYPE_ALLOWED_EVIDENCE: Dict[str, Tuple[str, ...]] = {
    "revenue_scale": ("revenue", "sales", "customer", "scale", "business economics", "growth claim"),
    "cash_generation": ("cash conversion", "cfo", "operating cash flow", "fcf", "free cash flow"),
    "working_capital": ("receivable", "inventory", "payable", "working capital", "cash conversion cycle"),
    "leverage": ("debt", "borrowings", "liquidity risk", "refinancing", "maturity", "interest coverage"),
    "financial_strength": ("net worth", "balance sheet", "cash", "debt", "liquidity", "financial strength"),
    "governance_integrity": (
        "governance", "board", "committee", "ownership", "promoter", "related party", "compensation", "incentive", "control"
    ),
    "governance_incentive": (
        "governance", "board", "committee", "ownership", "promoter", "related party", "compensation", "incentive", "control"
    ),
    "capital_allocation": ("capital allocation", "capex", "cwip", "qip", "buyback", "dividend", "reinvestment", "equity issuance"),
    "moat_business_quality": ("moat", "pricing", "recurring", "customer", "business model", "durable", "embedded"),
    "growth_execution": ("growth", "execution", "initiative", "project", "customer", "expansion", "release", "platform"),
    "market_risk": (
        "market risk",
        "market-price movement",
        "market price movement",
        "foreign exchange",
        "foreign exchange exposure",
        "currency",
        "currency exposure",
        "interest rate",
        "fx",
        "hedging",
        "risk",
    ),
    "per_share_limitation": ("share count", "weighted average shares", "diluted shares", "eps", "book value per share"),
    "missing_data_limitation": ("uncertainty", "missing", "not available", "not disclosed", "not provided"),
    "owner_earnings_limitation": ("fcf", "free cash flow", "capex", "owner earnings"),
}

CLAIM_TYPE_METRIC_SUPPORT: Dict[str, Tuple[str, ...]] = {
    "revenue_scale": ("revenue",),
    "cash_generation": ("cfo", "fcf", "cfo_to_pat", "fcf_to_pat"),
    "working_capital": ("receivable_days", "inventory_days", "payable_days", "cash_conversion_cycle"),
    "leverage": ("total_debt", "debt_to_equity", "net_debt", "interest_coverage"),
    "financial_strength": ("net_worth", "cash_and_equivalents", "total_debt", "book_value_per_share"),
    "capital_allocation": ("capex", "fcf", "share_count"),
    "per_share_limitation": ("share_count", "weighted_avg_shares", "diluted_shares", "eps_basic", "eps_diluted", "book_value_per_share"),
}


def classify_investor_claim(doctrine_id: str, path: str, text: str) -> str:
    haystack = f"{doctrine_id} {path} {text}".replace("_", " ").lower()
    governance_tokens = (
        "governance",
        "board",
        "committee",
        "promoter",
        "ownership",
        "related party",
        "conduct",
        "control",
        "oversight",
        "integrity",
        "incentive",
        "compensation",
        "alignment",
        "stewardship",
    )
    market_risk_tokens = (
        "market risk",
        "foreign exchange",
        "fx",
        "currency",
        "currency exposure",
        "interest rate",
        "interest-rate",
        "market-price movement",
        "market price movement",
        "sensitivity to market-price movements",
        "sensitivity to market price movements",
    )
    if any(token in haystack for token in ("owner earnings", "free cash flow", "fcf")) and any(
        token in haystack for token in ("cannot", "missing", "unavailable", "limited", "not assess")
    ):
        return "owner_earnings_limitation"
    if any(token in haystack for token in ("missing", "unavailable", "not available", "not disclosed", "not provided", "insufficient")):
        return "missing_data_limitation"
    if any(token in haystack for token in ("share count", "weighted average shares", "diluted shares", "per-share", "per share", "eps comparability")):
        return "per_share_limitation"
    has_governance = any(token in haystack for token in governance_tokens)
    has_market_risk = any(token in haystack for token in market_risk_tokens)
    if has_governance and not (
        "risk oversight" in haystack
        or "oversight of market risk" in haystack
        or "risk governance" in haystack
    ):
        if any(token in haystack for token in ("incentive", "compensation", "alignment", "owner minded", "owner-minded", "stewardship")):
            return "governance_incentive"
        return "governance_integrity"
    if has_market_risk:
        return "market_risk"
    if any(token in haystack for token in ("incentive", "compensation", "alignment", "owner minded", "owner-minded", "stewardship")):
        return "governance_incentive"
    if any(token in haystack for token in ("receivable", "inventory", "payable", "working capital", "cash conversion")):
        return "working_capital"
    if any(token in haystack for token in ("debt", "borrowings", "leverage", "liquidity", "refinancing", "maturity")):
        return "leverage"
    if any(token in haystack for token in ("financial strength", "margin of safety", "balance-sheet", "balance sheet", "net worth")):
        return "financial_strength"
    if any(token in haystack for token in ("cfo", "operating cash flow", "cash generation", "free cash flow", "fcf")):
        return "cash_generation"
    if any(token in haystack for token in ("revenue", "sales", "topline", "top line", "scale")):
        return "revenue_scale"
    if any(token in haystack for token in ("capex", "cwip", "qip", "buyback", "dividend", "capital allocation", "equity issuance", "preferential")):
        return "capital_allocation"
    if any(token in haystack for token in ("moat", "pricing power", "durable", "embedded", "switching cost", "business quality")):
        return "moat_business_quality"
    if any(token in haystack for token in ("growth", "execution", "expansion", "initiative", "project", "release cadence", "customer additions")):
        return "growth_execution"
    return "unknown"


def evidence_matches_claim_type(evidence_id: str, claim_type: str, evidence_lookup: Dict[str, Dict[str, Any]]) -> bool:
    if claim_type == "unknown":
        return True
    entry = evidence_lookup.get(evidence_id)
    if not entry:
        return False
    metadata = " ".join(
        str(entry.get(field) or "").replace("_", " ").lower()
        for field in ("category", "canonical_risk", "canonical_theme", "signal_type", "section_path", "value", "source_item_id", "source_artifact")
    )
    return any(token in metadata for token in CLAIM_TYPE_ALLOWED_EVIDENCE.get(claim_type, ()))


def metric_provenance_supports_claim(claim_type: str, financial_metrics_used: List[Dict[str, Any]]) -> bool:
    allowed_metrics = CLAIM_TYPE_METRIC_SUPPORT.get(claim_type, ())
    if not allowed_metrics:
        return False
    seen = {
        str(item.get("metric") or "").strip().lower()
        for item in financial_metrics_used
        if isinstance(item, dict)
    }
    seen |= {
        str(item.get("metric_id") or "").split(":", 1)[0].strip().lower()
        for item in financial_metrics_used
        if isinstance(item, dict) and str(item.get("metric_id") or "").strip()
    }
    return any(metric in seen for metric in allowed_metrics)


def _unique_preserve(items: List[Any]) -> List[Any]:
    unique: List[Any] = []
    for item in items:
        if item not in unique:
            unique.append(item)
    return unique


def _normalize_clean_financial_warning_text(warning: str) -> str:
    text = str(warning or "").strip()
    lowered = text.lower()
    if not text:
        return ""
    if "financial artifacts do not cover all company years" in lowered:
        return "Financial data does not cover all company years."
    if "weighted_avg_shares" in lowered and "field has no populated normalized value" in lowered:
        return "Weighted average shares are missing; per-share interpretation remains limited."
    if "diluted_shares" in lowered and "field has no populated normalized value" in lowered:
        return "Diluted shares are missing; per-share interpretation remains limited."
    if "shares_outstanding" in lowered and "field has no populated normalized value" in lowered:
        return "Share count is missing; per-share interpretation remains limited."
    if "standalone/consolidated basis unclear" in lowered or (
        "basis" in lowered and "unclear" in lowered and ("standalone" in lowered or "consolidated" in lowered)
    ):
        return "Standalone/consolidated basis is unclear; financial comparability remains limited."
    if lowered in {"fcf missing", "free cash flow missing"} or (
        "free cash flow" in lowered and "missing" in lowered
    ):
        return "Free cash flow is missing; FCF-based conclusions cannot be assessed."
    if lowered == "capex missing" or ("capex" in lowered and "missing" in lowered):
        return "Capex is missing; free-cash-flow interpretation remains limited."
    if "weighted average shares missing" in lowered:
        return "Weighted average shares are missing; per-share interpretation remains limited."
    if "diluted shares missing" in lowered:
        return "Diluted shares are missing; per-share interpretation remains limited."
    return text


def split_financial_warnings_for_clean_payload(warnings: List[str]) -> Tuple[List[str], List[str]]:
    clean_warnings: List[str] = []
    diagnostic_warnings: List[str] = []
    for raw_warning in warnings or []:
        text = str(raw_warning or "").strip()
        if not text:
            continue
        normalized = _normalize_clean_financial_warning_text(text)
        lowered_normalized = normalized.lower()
        lowered_raw = text.lower()
        if any(token in lowered_raw for token in FINANCIAL_WARNING_DIAGNOSTIC_TOKENS):
            if normalized != text and not any(token in lowered_normalized for token in ("artifact", ".json")):
                if normalized not in clean_warnings:
                    clean_warnings.append(normalized)
            else:
                if text not in diagnostic_warnings:
                    diagnostic_warnings.append(text)
                continue
        elif normalized:
            if normalized not in clean_warnings:
                clean_warnings.append(normalized)
            continue

        if text not in diagnostic_warnings and any(token in lowered_raw for token in FINANCIAL_WARNING_DIAGNOSTIC_TOKENS):
            diagnostic_warnings.append(text)
    return clean_warnings, diagnostic_warnings


def sanitize_active_evidence_ids(
    value: Any,
    *,
    evidence_lookup: Dict[str, Dict[str, Any]],
    diagnostics: Dict[str, Any],
    path: str = "$",
) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            child = f"{path}.{key}"
            if key == "evidence_ids":
                cleaned: List[str] = []
                if not isinstance(item, list):
                    diagnostics.setdefault("removed_invalid_ids", []).append(
                        {"path": child, "invalid_id": str(item), "reason": "evidence_ids_not_list"}
                    )
                    sanitized[key] = []
                    continue
                for raw in item:
                    evidence_id = str(raw or "").strip()
                    if not evidence_id:
                        continue
                    if evidence_id in PCIM_SECTION_NAME_DENYLIST:
                        diagnostics.setdefault("removed_invalid_ids", []).append(
                            {"path": child, "invalid_id": evidence_id, "reason": "pcim_section_name"}
                        )
                        continue
                    if evidence_id.endswith(".json"):
                        diagnostics.setdefault("removed_invalid_ids", []).append(
                            {"path": child, "invalid_id": evidence_id, "reason": "json_filename"}
                        )
                        continue
                    if evidence_id not in evidence_lookup:
                        diagnostics.setdefault("removed_invalid_ids", []).append(
                            {"path": child, "invalid_id": evidence_id, "reason": "unknown_evidence_id"}
                        )
                        continue
                    if evidence_id not in cleaned:
                        cleaned.append(evidence_id)
                sanitized[key] = cleaned
                continue
            sanitized[key] = sanitize_active_evidence_ids(
                item,
                evidence_lookup=evidence_lookup,
                diagnostics=diagnostics,
                path=child,
            )
        return sanitized
    if isinstance(value, list):
        return [
            sanitize_active_evidence_ids(item, evidence_lookup=evidence_lookup, diagnostics=diagnostics, path=f"{path}[{idx}]")
            for idx, item in enumerate(value)
        ]
    return value


def assert_valid_routed_payload(payload: Dict[str, Any], *, evidence_lookup: Dict[str, Dict[str, Any]]) -> None:
    def walk(value: Any, path: str = "$") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{path}.{key}"
                if key == "evidence_ids":
                    if not isinstance(item, list):
                        raise ValueError(f"invalid evidence_ids field at {child}: expected list")
                    for raw in item:
                        evidence_id = str(raw or "").strip()
                        if evidence_id in PCIM_SECTION_NAME_DENYLIST:
                            raise ValueError(f"invalid evidence_id at {child}: {evidence_id} (reason=pcim_section_name)")
                        if evidence_id.endswith(".json"):
                            raise ValueError(f"invalid evidence_id at {child}: {evidence_id} (reason=json_filename)")
                        if evidence_id and evidence_id not in evidence_lookup:
                            raise ValueError(f"invalid evidence_id at {child}: {evidence_id} (reason=unknown_evidence_id)")
                    continue
                walk(item, child)
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                walk(item, f"{path}[{idx}]")
    walk(payload)


def route_analyst_claims(
    *,
    doctrine_id: str,
    assessment: Dict[str, str],
    key_findings: List[str],
    red_flags: List[str],
    open_uncertainties: List[str],
    key_finding_map: List[List[str]],
    red_flag_map: List[List[str]],
    uncertainty_map: List[List[str]],
    assessment_evidence_map: Dict[str, List[str]],
    evidence_lookup: Dict[str, Dict[str, Any]],
    available_ids: List[str],
    financial_metrics_used: List[Dict[str, Any]],
) -> Tuple[Dict[str, str], List[str], List[str], List[str], List[List[str]], List[List[str]], List[List[str]], Dict[str, List[str]], Dict[str, Any]]:
    diagnostics: Dict[str, Any] = {
        "removed_misrouted_evidence": [],
        "replaced_evidence": [],
        "claims_converted_to_limitations": [],
        "metric_provenance_supported_claims": [],
        "accepted_market_risk_evidence": [],
        "unresolved_claims": [],
    }
    preferred_ids = _unique_preserve(
        [item for values in assessment_evidence_map.values() for item in values]
        + [item for group in key_finding_map for item in group]
        + [item for group in red_flag_map for item in group]
        + [item for group in uncertainty_map for item in group]
        + list(available_ids)
    )

    def candidate_ids(claim_type: str) -> List[str]:
        return [
            evidence_id for evidence_id in preferred_ids
            if evidence_matches_claim_type(evidence_id, claim_type, evidence_lookup)
        ]

    def repair(path: str, text: str, evidence_ids: List[str]) -> Tuple[str, List[str]]:
        claim_type = classify_investor_claim(doctrine_id, path, text)
        if claim_type == "unknown":
            return text, evidence_ids
        allowed_ids = [eid for eid in evidence_ids if evidence_matches_claim_type(eid, claim_type, evidence_lookup)]
        removed = [eid for eid in evidence_ids if eid not in allowed_ids]
        for evidence_id in removed:
            diagnostics["removed_misrouted_evidence"].append(
                {"claim_path": path, "claim_type": claim_type, "evidence_id": evidence_id}
            )
        if allowed_ids:
            if claim_type == "market_risk":
                for evidence_id in allowed_ids:
                    entry = evidence_lookup.get(evidence_id) or {}
                    diagnostics["accepted_market_risk_evidence"].append(
                        {
                            "claim_path": path,
                            "claim_type": claim_type,
                            "evidence_id": evidence_id,
                            "evidence_category": entry.get("category") or entry.get("canonical_risk"),
                            "routing_decision": "accepted_market_risk_evidence",
                        }
                    )
            return text, _unique_preserve(allowed_ids)
        if metric_provenance_supports_claim(claim_type, financial_metrics_used):
            diagnostics["metric_provenance_supported_claims"].append(
                {"claim_path": path, "claim_type": claim_type}
            )
            return text, []
        replacements = candidate_ids(claim_type)
        if replacements:
            replacement = replacements[:1]
            diagnostics["replaced_evidence"].append(
                {"claim_path": path, "claim_type": claim_type, "replacement_ids": replacement}
            )
            return text, replacement
        if claim_type in {"governance_integrity", "governance_incentive"}:
            diagnostics["claims_converted_to_limitations"].append(
                {
                    "claim_path": path,
                    "claim_type": claim_type,
                    "original_claim": text,
                    "replacement_claim": GENERIC_GOVERNANCE_LIMITATION,
                }
            )
            return GENERIC_GOVERNANCE_LIMITATION, []
        diagnostics["unresolved_claims"].append(
            {"claim_path": path, "claim_type": claim_type, "claim": text}
        )
        return text, []

    repaired_assessment = dict(assessment)
    repaired_assessment_map: Dict[str, List[str]] = {}
    repaired_uncertainties = list(open_uncertainties)
    repaired_uncertainty_map = deepcopy(uncertainty_map)
    for key, text in assessment.items():
        new_text, new_ids = repair(f"assessment.{key}", text, assessment_evidence_map.get(key, []))
        repaired_assessment[key] = new_text
        repaired_assessment_map[key] = new_ids
        if new_text != text and new_text not in repaired_uncertainties:
            repaired_uncertainties.append(new_text)
            repaired_uncertainty_map.append([])

    def repair_list(field: str, texts: List[str], evidence_map: List[List[str]]) -> Tuple[List[str], List[List[str]]]:
        repaired_texts: List[str] = []
        repaired_maps: List[List[str]] = []
        for idx, text in enumerate(texts):
            ids = evidence_map[idx] if idx < len(evidence_map) else []
            new_text, new_ids = repair(f"{field}.{idx}", text, ids)
            if new_text == GENERIC_GOVERNANCE_LIMITATION and field != "open_uncertainties":
                if new_text not in repaired_uncertainties:
                    repaired_uncertainties.append(new_text)
                    repaired_uncertainty_map.append(new_ids)
                continue
            repaired_texts.append(new_text)
            repaired_maps.append(new_ids)
        return repaired_texts, repaired_maps

    repaired_findings, repaired_finding_map = repair_list("key_findings", key_findings, key_finding_map)
    repaired_flags, repaired_flag_map = repair_list("red_flags", red_flags, red_flag_map)
    repaired_uncertainties, repaired_uncertainty_map = repair_list("open_uncertainties", repaired_uncertainties, repaired_uncertainty_map)

    for key in diagnostics:
        diagnostics[key] = _unique_preserve(diagnostics[key])

    return (
        repaired_assessment,
        repaired_findings,
        repaired_flags,
        repaired_uncertainties,
        repaired_finding_map,
        repaired_flag_map,
        repaired_uncertainty_map,
        repaired_assessment_map,
        diagnostics,
    )


def split_clean_and_diagnostics(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    clean = deepcopy(payload)
    raw_top_level_financial_warnings = list(payload.get("financial_warnings_carried_forward", []) or [])
    raw_nested_financial_warnings = list(
        ((payload.get("financial_assessment") or {}).get("financial_warnings_carried_forward", [])) or []
    )
    clean_top_level_financial_warnings, removed_top_level_financial_warnings = split_financial_warnings_for_clean_payload(
        raw_top_level_financial_warnings
    )
    clean_nested_financial_warnings, removed_nested_financial_warnings = split_financial_warnings_for_clean_payload(
        raw_nested_financial_warnings
    )
    clean["financial_warnings_carried_forward"] = clean_top_level_financial_warnings
    if isinstance(clean.get("financial_assessment"), dict):
        clean["financial_assessment"]["financial_warnings_carried_forward"] = clean_nested_financial_warnings
    diagnostics: Dict[str, Any] = {
        "doctrine_id": payload.get("doctrine_id"),
        "company": payload.get("company"),
        "analysis_mode": payload.get("analysis_mode"),
        "generated_at": payload.get("generated_at"),
        "schema_warnings": payload.get("schema_warnings", []),
        "evidence_grounding_warnings": payload.get("evidence_grounding_warnings", []),
        "evidence_id_normalization": payload.get("evidence_id_normalization", {}),
        "evidence_routing_diagnostics": payload.get(
            "evidence_routing_diagnostics",
            payload.get("munger_evidence_routing_diagnostics", {}),
        ),
        "financial_warning_diagnostics": {
            "raw_financial_warnings_carried_forward": _unique_preserve(
                raw_top_level_financial_warnings + raw_nested_financial_warnings
            ),
            "removed_internal_financial_warnings": _unique_preserve(
                removed_top_level_financial_warnings + removed_nested_financial_warnings
            ),
            "clean_financial_warnings": _unique_preserve(
                clean_top_level_financial_warnings + clean_nested_financial_warnings
            ),
        },
    }
    for key in (
        "schema_warnings",
        "evidence_grounding_warnings",
        "evidence_id_normalization",
        "evidence_routing_diagnostics",
        "munger_evidence_routing_diagnostics",
        "raw_validator_output",
        "prompt",
        "input_pack",
        "token_budget",
        "compacted_sections",
        "internal_debug",
    ):
        clean.pop(key, None)
    return clean, diagnostics
