from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.context_paths import investor_panel_dir
from knowledge.ai import get_llm
from knowledge.ai.input_packs import (
    build_llm_input_pack,
    call_llm_with_input_pack,
    render_llm_input_pack,
    resolve_stage_token_budget,
)

from .briefs import (
    LENS_CONFIG,
    normalize_user_facing_brief_lengths,
    normalize_user_facing_brief_shape,
    sanitize_user_facing_brief,
    validate_user_facing_brief,
)
from .forbidden_language import find_forbidden_recommendation_language
from .doctrine_registry import InvestorDoctrineRegistry
from .evidence_router import (
    PCIM_SECTION_NAME_DENYLIST as ROUTER_SECTION_NAME_DENYLIST,
    assert_valid_routed_payload,
    route_analyst_claims,
    sanitize_active_evidence_ids,
    split_clean_and_diagnostics,
)
from .evidence_grounding import (
    PCIM_SECTION_NAME_DENYLIST,
    build_evidence_lookup,
    normalize_evidence_ids_with_summary,
    normalize_text_evidence_ids,
    validate_analyst_evidence_grounding,
    validate_prompt_payload,
)


PCIM_FILE = "pcim_v1.json"
ALLOWED_RATINGS = {"strong", "mixed", "weak", "insufficient_evidence"}
DEFAULT_MAX_ITEMS_PER_SECTION = 25
DEFAULT_MAX_RISKS = 20
DEFAULT_MAX_CAPITAL_ALLOCATION_ITEMS = 20
DEFAULT_MAX_EVIDENCE_EXCERPT_CHARS = 300
DEFAULT_MAX_TOTAL_PROMPT_CHARS = 28_000
DEFAULT_MAX_SECTIONS = 8
DEFAULT_MAX_NESTED_ITEMS_PER_ITEM = 5
DEFAULT_MAX_TEXT_CHARS_PER_VALUE = 500
DEFAULT_MAX_EVIDENCE_IDS_PER_ITEM = 5
DEFAULT_MAX_DICT_KEYS_PER_ITEM = 8
MIN_MAX_ITEMS_PER_SECTION = 1
MIN_MAX_RISKS = 1
MIN_MAX_CAPITAL_ALLOCATION_ITEMS = 1
MIN_MAX_EVIDENCE_EXCERPT_CHARS = 80
MIN_MAX_TOTAL_PROMPT_CHARS = 12_000
MIN_MAX_TEXT_CHARS_PER_VALUE = 80
COMPACTION_REASONING_LIMIT = "Input PCIM was compacted for token budget; evidence_ids preserved."
DEFAULT_SECTION_CHAR_CAP = 2500
SECTION_CHAR_CAPS = {
    "multi_year_inputs": 4000,
    "financial_quality_inputs": 3000,
    "capital_allocation_inputs": 3000,
    "business_understanding": 2500,
    "business_economics_inputs": 2500,
    "management_quality_inputs": 3000,
    "moat_inputs": 3000,
    "governance_and_incentive_inputs": 3000,
}
SECTION_REPLACEMENT_LIMITATION = (
    "Detailed source context omitted due prompt budget; use PCIM/evidence artifacts for full trace."
)
DROP_KEYS = {
    "source_chunk",
    "raw_text",
    "full_text",
    "document_text",
}
FORBIDDEN_CLEAN_ANALYST_KEYS = {
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
}
HARD_FORBIDDEN_CLEAN_ANALYST_STRING_TOKENS = {
    "source_chunk",
    "raw_text",
    "full_text",
    "prompt",
    "input_pack",
    "token_budget",
}
SOFT_FORBIDDEN_CLEAN_ANALYST_TERMS = {
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
}
REQUIRED_OUTPUT_KEYS = {
    "doctrine_id",
    "company",
    "pcim_version",
    "pcim_source",
    "analysis_mode",
    "sections_consumed",
    "assessment",
    "rating",
    "key_findings",
    "red_flags",
    "open_uncertainties",
    "financial_metrics_used",
    "financial_red_flags",
    "financial_positive_signals",
    "financial_missing_data",
    "financial_interpretation_limits",
    "financial_assessment",
    "financial_sections_consumed",
    "financial_warnings_carried_forward",
    "evidence_ids",
    "historical_context_used",
    "years_considered",
    "supporting_pcim_sections",
    "evidence_id_normalization",
    "evidence_grounding_status",
    "evidence_grounding_warnings",
    "evidence_routing_diagnostics",
    "schema_warnings",
    "reasoning_limits",
    "user_facing_brief",
    "generated_at",
}
FINANCIAL_PCIM_SECTIONS = {
    "financial_fundamentals_inputs",
    "financial_trend_inputs",
    "financial_growth_inputs",
    "profitability_inputs",
    "cash_conversion_inputs",
    "return_on_capital_inputs",
    "balance_sheet_strength_inputs",
    "working_capital_inputs",
    "per_share_inputs",
    "corporate_action_inputs",
    "ownership_inputs",
    "financial_quality_inputs",
    "financial_driver_inputs",
    "multi_year_financial_inputs",
}
INVALID_SECTION_NAME_EVIDENCE_IDS = ROUTER_SECTION_NAME_DENYLIST
FINANCIAL_LIMITATION_PATTERNS = (
    ("fcf_missing", ("free cash flow", "fcf"), "Free cash flow is unavailable or not supplied in the current PCIM."),
    ("capex_missing", ("capex", "capital expenditure"), "Capex is unavailable or not supplied in the current PCIM."),
    ("share_count_missing", ("share count", "shares outstanding", "weighted average shares"), "Share-count evidence is incomplete for per-share interpretation."),
    ("basis_unknown", ("basis", "standalone", "consolidated"), "Financial basis remains unknown or unclear."),
)
FINANCIAL_WARNING_GROUPS = {
    "share_count_missing": (
        "share count missing",
        "shares outstanding missing",
        "weighted average shares missing",
        "diluted shares missing",
        "per-share analysis is limited",
        "per share analysis is limited",
        "eps comparability limited",
        "bvps comparability limited",
        "share-count data incomplete",
        "share-count evidence is incomplete",
        "share-count data incomplete",
    ),
    "fcf_missing": (
        "fcf missing",
        "free cash flow missing",
        "free cash flow unavailable",
        "capex missing prevents fcf",
        "owner earnings cannot be assessed",
        "free cash flow is unavailable",
    ),
    "capex_missing": (
        "capex missing",
        "capital expenditure not available",
        "capital expenditure missing",
        "fcf cannot be calculated due capex missing",
        "owner earnings limited due capex missing",
        "capex is unavailable",
    ),
    "payables_missing": (
        "payables missing",
        "trade payables missing",
        "payable days missing",
        "ccc incomplete",
        "cash conversion cycle unavailable",
        "payables unavailable",
    ),
    "basis_unknown": (
        "basis unknown",
        "standalone/consolidated basis unclear",
        "basis unclear",
        "basis uncertainty",
        "financial basis remains unknown or unclear",
    ),
}
FINANCIAL_WARNING_GROUP_DEFINITIONS = {
    "fcf_missing": {
        "warning_id": "fcf_missing",
        "canonical_warning": "free cash flow missing",
        "severity": "major",
        "required_carry_forward_text": "Free cash flow is missing; FCF-based conclusions cannot be assessed.",
        "equivalent_phrases": list(FINANCIAL_WARNING_GROUPS["fcf_missing"])
        + [
            "fcf cannot be calculated",
            "free cash flow cannot be calculated",
            "free cash flow is missing; fcf-based conclusions cannot be assessed",
        ],
    },
    "capex_missing": {
        "warning_id": "capex_missing",
        "canonical_warning": "capex missing",
        "severity": "major",
        "required_carry_forward_text": "Capex is missing or incomplete; free cash flow and owner-earnings interpretation remain limited.",
        "equivalent_phrases": list(FINANCIAL_WARNING_GROUPS["capex_missing"])
        + [
            "capex missing prevents fcf",
            "capital expenditure unavailable",
            "capex is missing or incomplete",
        ],
    },
    "weighted_avg_shares_missing": {
        "warning_id": "weighted_avg_shares_missing",
        "canonical_warning": "weighted average shares missing",
        "severity": "major",
        "required_carry_forward_text": "Weighted average shares are missing; EPS and per-share interpretation remain limited.",
        "equivalent_phrases": [
            "weighted average shares missing",
            "weighted avg shares missing",
            "weighted average shares are missing",
            "weighted average share count is missing",
            "per-share analysis is limited because weighted average share count is missing",
        ],
    },
    "diluted_shares_missing": {
        "warning_id": "diluted_shares_missing",
        "canonical_warning": "diluted shares missing",
        "severity": "major",
        "required_carry_forward_text": "Diluted shares are missing; diluted EPS and full per-share comparability remain limited.",
        "equivalent_phrases": [
            "diluted shares missing",
            "diluted shares are missing",
            "diluted share count is missing",
            "per-share analysis is limited because diluted share count is missing",
            "diluted eps comparability limited",
        ],
    },
    "share_count_missing": {
        "warning_id": "share_count_missing",
        "canonical_warning": "share count missing",
        "severity": "major",
        "required_carry_forward_text": "Share-count evidence is incomplete; per-share analysis remains limited.",
        "equivalent_phrases": list(FINANCIAL_WARNING_GROUPS["share_count_missing"])
        + [
            "share-count evidence is incomplete",
            "per-share analysis remains limited",
        ],
    },
    "payables_missing": {
        "warning_id": "payables_missing",
        "canonical_warning": "payables missing",
        "severity": "major",
        "required_carry_forward_text": "Payables or payable-days evidence is missing; cash conversion cycle cannot be assessed cleanly.",
        "equivalent_phrases": list(FINANCIAL_WARNING_GROUPS["payables_missing"])
        + [
            "payables or payable-days evidence is missing",
            "cash conversion cycle cannot be assessed cleanly",
        ],
    },
    "basis_unknown": {
        "warning_id": "basis_unknown",
        "canonical_warning": "basis unknown",
        "severity": "major",
        "required_carry_forward_text": "Standalone/consolidated basis is unclear; financial comparability remains limited.",
        "equivalent_phrases": list(FINANCIAL_WARNING_GROUPS["basis_unknown"])
        + [
            "standalone/consolidated basis is unclear",
            "financial comparability remains limited",
            "standalone/consolidated basis is unclear; financial comparability remains limited",
        ],
    },
    "reconciliation_warning": {
        "warning_id": "reconciliation_warning",
        "canonical_warning": "reconciliation warning",
        "severity": "major",
        "required_carry_forward_text": "Financial reconciliation warnings remain unresolved; ratio interpretation should stay conservative.",
        "equivalent_phrases": [
            "reconciliation warning",
            "financial reconciliation warning",
            "reconciliation remains unresolved",
            "ratio interpretation should stay conservative",
        ],
    },
    "audit_warning": {
        "warning_id": "audit_warning",
        "canonical_warning": "audit warning",
        "severity": "major",
        "required_carry_forward_text": "Financial audit warnings remain unresolved; financial interpretation should stay conservative.",
        "equivalent_phrases": [
            "audit warning",
            "financial audit warning",
            "audit remains unresolved",
            "financial interpretation should stay conservative",
        ],
    },
}
FINANCIAL_METRIC_ALIASES = {
    "revenue": ("revenue", "sales", "operating revenue", "income from operations"),
    "pat": ("pat", "profit after tax", "net profit", "net income"),
    "pbt": ("pbt", "profit before tax"),
    "ebitda": ("ebitda",),
    "ebit": ("ebit",),
    "gross_margin": ("gross margin",),
    "ebitda_margin": ("ebitda margin",),
    "ebit_margin": ("ebit margin",),
    "opm": ("opm", "operating margin", "operating profit margin"),
    "npm": ("npm", "net margin", "net profit margin"),
    "roe": ("roe", "return on equity"),
    "roce": ("roce", "return on capital employed"),
    "roa": ("roa", "return on assets"),
    "cfo": ("cfo", "cash flow from operations", "cash flow from operating activities"),
    "cfo_to_pat": ("cfo to pat", "cfo/pat", "cash conversion"),
    "capex": ("capex", "capital expenditure"),
    "fcf": ("fcf", "free cash flow", "free cashflow"),
    "fcf_to_pat": ("fcf to pat", "fcf/pat"),
    "total_debt": ("total debt", "debt", "borrowings"),
    "net_debt": ("net debt",),
    "cash_and_equivalents": ("cash and equivalents", "cash equivalents", "cash"),
    "net_worth": ("net worth", "equity", "net worth / reserves"),
    "reserves": ("reserves", "other equity"),
    "receivables": ("receivables", "trade receivables"),
    "inventory": ("inventory", "inventories"),
    "payables": ("payables", "trade payables"),
    "receivable_days": ("receivable days", "debtor days"),
    "inventory_days": ("inventory days",),
    "payable_days": ("payable days",),
    "cash_conversion_cycle": ("cash conversion cycle", "ccc"),
    "eps_basic": ("eps basic", "basic eps", "basic earnings per share"),
    "eps_diluted": ("eps diluted", "diluted eps", "diluted earnings per share"),
    "shares_outstanding": ("shares outstanding", "share count", "reported share count", "number of shares outstanding"),
    "weighted_avg_shares": ("weighted average shares", "weighted avg shares"),
    "diluted_shares": ("diluted shares",),
    "dividend_paid": ("dividend paid",),
    "dividend_per_share": ("dividend per share", "dps"),
    "payout_ratio": ("payout ratio",),
    "book_value_per_share": ("book value per share", "bvps"),
    "debt_to_equity": ("debt to equity", "debt/equity"),
    "tangible_book_value_per_share": ("tangible book value per share",),
}
FINANCIAL_METRIC_PERIOD_RE = re.compile(r"\b(fy\d{2})\b", re.IGNORECASE)
NORMALIZED_LIST_STRING_LIMIT = 350
SAFE_LIST_DICT_PREFERRED_KEYS = (
    "value",
    "text",
    "finding",
    "flag",
    "uncertainty",
    "question",
    "concern",
    "reason",
    "note",
    "summary",
    "label",
    "message",
    "title",
)

RATING_NORMALIZATION_MAP = {
    "insufficient evidence": "insufficient_evidence",
    "insufficient-evidence": "insufficient_evidence",
    "not enough evidence": "insufficient_evidence",
    "inconclusive": "insufficient_evidence",
    "neutral": "mixed",
    "cautious": "mixed",
    "positive": "strong",
    "negative": "weak",
}
CLAIM_TYPE_ALLOWED_EVIDENCE = {
    "governance_incentive": [
        "governance",
        "incentive",
        "ownership",
        "promoter",
        "board",
        "committee",
        "compensation",
        "related_party",
        "related party",
        "capital_allocation",
        "capital allocation",
        "corporate_action",
        "corporate action",
        "uncertainty",
        "missing_data",
        "missing data",
    ],
    "market_risk": [
        "market risk",
        "fx risk",
        "foreign exchange",
        "interest rate",
        "currency risk",
        "risk",
    ],
    "working_capital": [
        "working capital",
        "receivable",
        "inventory",
        "payable",
        "cash conversion",
        "financial",
    ],
    "capital_allocation": [
        "capital allocation",
        "capex",
        "equity issuance",
        "qip",
        "preferential",
        "related_party",
        "related party",
        "corporate_action",
        "corporate action",
    ],
}
MUNGER_GOVERNANCE_LIMITATION = (
    "Governance evidence is incomplete because board, committee, ownership, "
    "compensation, or oversight references are missing in the supplied record."
)


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _section_payload(pcim: Dict[str, Any], section: str) -> Any:
    return pcim.get(section)


def _resolve_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer when set") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0 when set")
    return value


def _normalize_rating_value(rating: Any, schema_warnings: List[str]) -> str:
    if not isinstance(rating, str) or not rating.strip():
        raise ValueError("rating must be one of strong, mixed, weak, insufficient_evidence")
    normalized = rating.strip().lower()
    if normalized in ALLOWED_RATINGS:
        return normalized
    mapped = RATING_NORMALIZATION_MAP.get(normalized)
    if mapped:
        schema_warnings.append(f"rating was normalized from {rating!r} to {mapped!r}.")
        return mapped
    raise ValueError("rating must be one of strong, mixed, weak, insufficient_evidence")


def _prompt_compaction_limits() -> Dict[str, int]:
    hard_prompt_chars_raw = os.getenv("INVESTOR_PANEL_HARD_MAX_PROMPT_CHARS")
    hard_prompt_chars = 0
    if hard_prompt_chars_raw is not None and hard_prompt_chars_raw.strip():
        try:
            hard_prompt_chars = int(hard_prompt_chars_raw)
        except ValueError as exc:
            raise ValueError("INVESTOR_PANEL_HARD_MAX_PROMPT_CHARS must be an integer when set") from exc
        if hard_prompt_chars <= 0:
            raise ValueError("INVESTOR_PANEL_HARD_MAX_PROMPT_CHARS must be greater than 0 when set")
    return {
        "max_items_per_section": _resolve_positive_int_env(
            "INVESTOR_PANEL_MAX_ITEMS_PER_SECTION",
            3,
        ),
        "max_risks": _resolve_positive_int_env(
            "INVESTOR_PANEL_MAX_RISKS",
            20,
        ),
        "max_capital_allocation_items": 20,
        "max_evidence_excerpt_chars": _resolve_positive_int_env(
            "INVESTOR_PANEL_MAX_EVIDENCE_EXCERPT_CHARS",
            DEFAULT_MAX_EVIDENCE_EXCERPT_CHARS,
        ),
        "max_total_prompt_chars": _resolve_positive_int_env(
            "INVESTOR_PANEL_MAX_PROMPT_CHARS",
            DEFAULT_MAX_TOTAL_PROMPT_CHARS,
        ),
        "hard_max_prompt_chars": hard_prompt_chars,
        "max_sections": DEFAULT_MAX_SECTIONS,
        "max_nested_items_per_item": DEFAULT_MAX_NESTED_ITEMS_PER_ITEM,
        "max_text_chars_per_value": DEFAULT_MAX_TEXT_CHARS_PER_VALUE,
        "max_evidence_ids_per_item": DEFAULT_MAX_EVIDENCE_IDS_PER_ITEM,
        "max_dict_keys_per_item": DEFAULT_MAX_DICT_KEYS_PER_ITEM,
    }


def _safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def _section_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, dict):
        return not any(_section_empty(v) is False for v in value.values())
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _collect_section_evidence_ids(pcim: Dict[str, Any], sections: List[str]) -> List[str]:
    evidence_map = pcim.get("evidence_map") or {}
    evidence_ids: List[str] = []
    for section in sections:
        for evidence_id in evidence_map.get(section, []) or []:
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
    return evidence_ids


def _missing_sections(pcim: Dict[str, Any], sections: List[str]) -> List[str]:
    missing = []
    for section in sections:
        value = _section_payload(pcim, section)
        if section in {"evidence_map", "uncertainty_missing_data"}:
            if not isinstance(value, dict) or not value:
                missing.append(section)
            continue
        if _section_empty(value):
            missing.append(section)
    return missing


def _financial_sections_for_doctrine(sections: List[str]) -> List[str]:
    return [section for section in sections if section in FINANCIAL_PCIM_SECTIONS]


def _normalize_metric_label(value: Any) -> str:
    text = str(value or "").strip().lower().replace("&", " and ")
    text = FINANCIAL_METRIC_PERIOD_RE.sub(" ", text)
    text = re.sub(r"[\(\)\[\]\{\}/,:;-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_metric_period(value: Any) -> str:
    match = FINANCIAL_METRIC_PERIOD_RE.search(str(value or ""))
    return match.group(1).lower() if match else ""


def _metric_aliases(canonical_metric: str) -> List[str]:
    aliases = list(FINANCIAL_METRIC_ALIASES.get(canonical_metric, (canonical_metric.replace("_", " "),)))
    aliases.append(canonical_metric)
    aliases.append(canonical_metric.replace("_", " "))
    return _unique_preserve_order([_normalize_metric_label(alias) for alias in aliases if str(alias or "").strip()])


def _extract_metric_value(item: Dict[str, Any]) -> Tuple[Any, str]:
    for key, unit in (
        ("value_crore", "₹ crore"),
        ("value_per_share", "per share"),
        ("holding_percent", "%"),
        ("growth_percent", "%"),
        ("value", str(item.get("unit") or "").strip()),
        ("raw_number", "count"),
        ("value_shares", "shares"),
    ):
        value = item.get(key)
        if isinstance(value, (int, float)):
            return value, unit
    series = item.get("series")
    if isinstance(series, list) and series:
        latest = series[0]
        if isinstance(latest, dict):
            for key, unit in (
                ("value", str(item.get("unit") or "").strip()),
                ("value_crore", "₹ crore"),
                ("value_per_share", "per share"),
            ):
                value = latest.get(key)
                if isinstance(value, (int, float)):
                    return value, unit
    return None, str(item.get("unit") or "").strip()


def _build_financial_metric_registry(selected_pcim: Dict[str, Any], sections: List[str]) -> List[Dict[str, Any]]:
    registry: List[Dict[str, Any]] = []
    seen_metric_ids: set[str] = set()

    def add_metric(
        canonical_metric: Any,
        *,
        period: Any = None,
        value: Any = None,
        unit: str = "",
        basis: Any = None,
        confidence: Any = None,
        source_section: str,
    ) -> None:
        canonical = str(canonical_metric or "").strip()
        if not canonical:
            return
        period_value = str(period or "").strip().lower()
        metric_id = canonical if not period_value else f"{canonical}:{period_value}"
        if metric_id in seen_metric_ids:
            return
        seen_metric_ids.add(metric_id)
        registry.append(
            {
                "metric_id": metric_id,
                "canonical_metric": canonical,
                "display_name": canonical.replace("_", " "),
                "period": period_value or None,
                "value": value,
                "unit": unit or "",
                "basis": str(basis or "").strip() or "unknown",
                "confidence": str(confidence or "").strip() or "unknown",
                "source_section": source_section,
                "aliases": _metric_aliases(canonical),
            }
        )

    for section in _financial_sections_for_doctrine(sections):
        payload = selected_pcim.get(section) or {}
        if not isinstance(payload, dict):
            continue
        if section == "financial_fundamentals_inputs":
            for bucket in payload.get("by_year", []) or []:
                if not isinstance(bucket, dict):
                    continue
                for item in bucket.get("key_metrics", []) or []:
                    if not isinstance(item, dict):
                        continue
                    value, unit = _extract_metric_value(item)
                    add_metric(
                        item.get("field"),
                        period=item.get("source_year") or bucket.get("year") or item.get("period"),
                        value=value,
                        unit=unit,
                        basis=item.get("basis") or bucket.get("basis") or payload.get("basis_used"),
                        confidence=item.get("confidence"),
                        source_section=section,
                    )
        elif section in {"financial_growth_inputs", "profitability_inputs", "working_capital_inputs"}:
            for bucket in payload.get("by_year", []) or []:
                if not isinstance(bucket, dict):
                    continue
                key = "growth_metrics" if section == "financial_growth_inputs" else "metrics"
                for item in bucket.get(key, []) or []:
                    if not isinstance(item, dict):
                        continue
                    value, unit = _extract_metric_value(item)
                    add_metric(
                        item.get("metric"),
                        period=item.get("period") or bucket.get("year"),
                        value=value,
                        unit=unit,
                        basis=item.get("basis") or bucket.get("basis") or payload.get("basis"),
                        confidence=item.get("confidence"),
                        source_section=section,
                    )
        elif section in {
            "financial_trend_inputs",
            "cash_conversion_inputs",
            "return_on_capital_inputs",
            "balance_sheet_strength_inputs",
            "per_share_inputs",
        }:
            items = payload.get("metric_trends", []) if section == "financial_trend_inputs" else payload.get("metrics", [])
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                value, unit = _extract_metric_value(item)
                period = item.get("period")
                series = item.get("series")
                if not period and isinstance(series, list) and series and isinstance(series[0], dict):
                    period = series[0].get("year")
                add_metric(
                    item.get("metric"),
                    period=period,
                    value=value,
                    unit=unit,
                    basis=item.get("basis") or payload.get("basis") or payload.get("basis_used"),
                    confidence=item.get("confidence"),
                    source_section=section,
                )
        elif section == "financial_quality_inputs":
            for bucket in payload.get("by_year", []) or []:
                if not isinstance(bucket, dict):
                    continue
                for section_payload in (bucket.get("sections") or {}).values():
                    if not isinstance(section_payload, dict):
                        continue
                    for metric_name, metric_value in (section_payload.get("evidence_metrics") or {}).items():
                        add_metric(
                            metric_name,
                            period=section_payload.get("period") or bucket.get("year"),
                            value=metric_value,
                            unit="",
                            basis=section_payload.get("basis") or bucket.get("basis_used") or payload.get("basis_used"),
                            confidence=section_payload.get("confidence"),
                            source_section=section,
                        )
        elif section == "financial_driver_inputs":
            for item in payload.get("attributions", []) or []:
                if not isinstance(item, dict):
                    continue
                add_metric(
                    item.get("metric"),
                    period=item.get("period"),
                    value=None,
                    unit="",
                    basis=payload.get("basis_used"),
                    confidence=item.get("confidence"),
                    source_section=section,
                )

    growth_quality = selected_pcim.get("growth_quality_inputs") or {}
    if isinstance(growth_quality, dict):
        financial_growth = growth_quality.get("financial_growth_summary") or {}
        if isinstance(financial_growth, dict):
            for bucket in financial_growth.get("by_year", []) or []:
                if not isinstance(bucket, dict):
                    continue
                for item in bucket.get("growth_metrics", []) or []:
                    if not isinstance(item, dict):
                        continue
                    value, unit = _extract_metric_value(item)
                    add_metric(
                        item.get("metric"),
                        period=item.get("period") or bucket.get("year"),
                        value=value,
                        unit=unit,
                        basis=item.get("basis") or bucket.get("basis") or "unknown",
                        confidence=item.get("confidence"),
                        source_section="growth_quality_inputs",
                    )
    canonical_groups: Dict[str, List[Dict[str, Any]]] = {}
    for entry in list(registry):
        canonical_groups.setdefault(entry["canonical_metric"], []).append(entry)
    for canonical_metric, entries in canonical_groups.items():
        if canonical_metric in seen_metric_ids:
            continue
        preferred = sorted(
            entries,
            key=lambda item: (str(item.get("period") or ""), str(item.get("metric_id") or "")),
            reverse=True,
        )[0]
        seen_metric_ids.add(canonical_metric)
        registry.append(
            {
                "metric_id": canonical_metric,
                "canonical_metric": canonical_metric,
                "display_name": canonical_metric.replace("_", " "),
                "period": None,
                "value": preferred.get("value"),
                "unit": preferred.get("unit"),
                "basis": preferred.get("basis"),
                "confidence": preferred.get("confidence"),
                "source_section": preferred.get("source_section"),
                "aliases": _metric_aliases(canonical_metric),
            }
        )
    return registry


def _registry_metric_names(registry: List[Dict[str, Any]]) -> List[str]:
    return _unique_preserve_order(
        [
            str(entry.get("canonical_metric") or "").strip()
            for entry in registry
            if str(entry.get("canonical_metric") or "").strip()
        ]
    )


def _collect_financial_metric_names(selected_pcim: Dict[str, Any], sections: List[str]) -> List[str]:
    return _registry_metric_names(_build_financial_metric_registry(selected_pcim, sections))


def _collect_financial_warnings(selected_pcim: Dict[str, Any], sections: List[str]) -> List[str]:
    warnings: List[str] = []

    def add_warning(text: Any) -> None:
        if not isinstance(text, str):
            return
        value = text.strip()
        if value and value not in warnings:
            warnings.append(value)

    for section in _financial_sections_for_doctrine(sections):
        payload = selected_pcim.get(section) or {}
        if isinstance(payload, dict):
            for item in payload.get("warnings", []) or []:
                add_warning(item)
            for item in payload.get("limitations", []) or []:
                add_warning(item)
            for bucket in payload.get("by_year", []) or []:
                if isinstance(bucket, dict):
                    for item in bucket.get("warnings", []) or []:
                        add_warning(item)
                    for item in bucket.get("per_share_comparability_warnings", []) or []:
                        add_warning(item)
    growth_quality = selected_pcim.get("growth_quality_inputs") or {}
    if isinstance(growth_quality, dict):
        financial_growth = growth_quality.get("financial_growth_summary") or {}
        if isinstance(financial_growth, dict):
            for item in financial_growth.get("signals", []) or []:
                add_warning(item)
    return warnings


def _collect_financial_basis(selected_pcim: Dict[str, Any], sections: List[str]) -> str:
    for section in _financial_sections_for_doctrine(sections):
        payload = selected_pcim.get(section) or {}
        if not isinstance(payload, dict):
            continue
        for key in ("basis", "basis_used"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        for bucket in payload.get("by_year", []) or []:
            if isinstance(bucket, dict):
                value = str(bucket.get("basis") or bucket.get("basis_used") or "").strip()
                if value:
                    return value
    return "unknown"


def _derive_financial_context(selected_pcim: Dict[str, Any], sections: List[str], missing_sections: List[str]) -> Dict[str, Any]:
    financial_sections = _financial_sections_for_doctrine(sections)
    metric_registry = _build_financial_metric_registry(selected_pcim, sections)
    metrics_used = _registry_metric_names(metric_registry)
    warnings = _collect_financial_warnings(selected_pcim, sections)
    basis_used = _collect_financial_basis(selected_pcim, sections)
    missing_data: List[str] = []
    interpretation_limits: List[str] = []
    metric_flags = _financial_context_metric_flags({"metrics_used": metrics_used})

    for section in missing_sections:
        if section in financial_sections:
            missing_data.append(f"Missing financial section: {section}")

    metrics_set = {metric.lower() for metric in metrics_used}
    per_share_signals_present = (
        not _section_empty(selected_pcim.get("per_share_inputs"))
        or any(
            token in warning.lower()
            for warning in warnings
            for token in ("share count", "weighted average shares", "diluted shares", "per-share")
        )
    )
    if "fcf" not in metrics_set:
        missing_data.append("Free cash flow is unavailable or not supplied in the current PCIM.")
    if "capex" not in metrics_set:
        missing_data.append("Capex is unavailable or not supplied in the current PCIM.")
    if per_share_signals_present:
        if not any(metric in metrics_set for metric in {"share_count", "shares_outstanding", "weighted_avg_shares", "diluted_shares"}):
            missing_data.append("share count missing")
        else:
            if metric_flags["has_shares_outstanding"] and not metric_flags["has_weighted_avg_shares"]:
                missing_data.append("weighted average shares missing")
                interpretation_limits.append("Per-share analysis is limited because weighted average share count is missing.")
            if not metric_flags["has_diluted_shares"]:
                missing_data.append("diluted shares missing")
                interpretation_limits.append("Per-share analysis is limited because diluted share count is missing.")
    if basis_used == "unknown" and any("basis" in warning.lower() for warning in warnings):
        interpretation_limits.append("Financial basis remains unknown or unclear.")
    payables_signals_present = (
        not _section_empty(selected_pcim.get("working_capital_inputs"))
        or any(
            token in warning.lower()
            for warning in warnings
            for token in ("payables", "payable days", "cash conversion cycle", "ccc")
        )
    )
    if payables_signals_present and not metric_flags["has_payable_days"]:
        interpretation_limits.append("payable days missing")
    if payables_signals_present and (
        not metric_flags["has_payable_days"] or not metric_flags["has_cash_conversion_cycle"]
    ):
        interpretation_limits.append("cash conversion cycle unavailable")

    for warning in warnings:
        lowered = warning.lower()
        if "share count missing" in lowered and metric_flags["has_shares_outstanding"]:
            continue
        if any(token in lowered for token in ("basis", "share count", "weighted average shares", "diluted shares", "comparability", "fcf", "capex", "debt", "dilution", "qip", "payables", "payable days", "cash conversion cycle")):
            interpretation_limits.append(warning)

    return {
        "financials_used": bool(financial_sections),
        "basis_used": basis_used,
        "financial_sections_consumed": financial_sections,
        "warnings": warnings,
        "metrics_used": metrics_used,
        "metric_registry": metric_registry,
        "missing_data": list(dict.fromkeys(missing_data)),
        "interpretation_limits": list(dict.fromkeys(interpretation_limits)),
    }


def _matches_financial_expectation(texts: List[str], keywords: Tuple[str, ...]) -> bool:
    joined = " ".join(texts).lower()
    return all(any(keyword_part in joined for keyword_part in keywords) for keyword_part in (keywords[:1]))


def _must_carry_financial_limitations(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _canonical_required_financial_warning_groups(context)


def _financial_instruction_block(doctrine_id: str) -> List[str]:
    shared = [
        "- Use financial numbers only from the supplied PCIM sections.",
        "- Do not calculate new ratios, spreads, intrinsic value, owner earnings, or margin of safety.",
        "- Interpret only supplied ratios, growth metrics, quality signals, and warnings.",
        "- Mention missing financial data explicitly as limitations.",
        "- Never hide uncertainty, never give buy/sell/hold, and never use valuation language.",
    ]
    doctrine_specific = {
        "graham": [
            "- Focus on balance-sheet strength, debt/equity, net cash or debt, cash conversion, dividend safety, working-capital risk, and reconciliation or audit warnings.",
            "- If share count, FCF, capex, basis, or debt mapping is missing or warning-heavy, say so explicitly.",
        ],
        "buffett": [
            "- Focus on ROE, ROCE, ROA, profitability durability, cash conversion quality, balance-sheet strength, FCF readiness, capital allocation, and per-share economics.",
            "- If FCF or capex is missing, say owner-earnings readiness cannot be assessed rather than inferring it.",
        ],
        "fisher": [
            "- Focus on revenue growth, PAT growth, EPS growth, margin expansion or compression, reinvestment intensity, working-capital build-up, and whether growth looks healthy or cash-consuming.",
            "- Distinguish growth quality, growth quantity, and growth funding quality.",
        ],
        "munger": [
            "- Focus on financial red flags, dilution and per-share comparability, QIP or proceeds usage, working-capital pressure, cash conversion weakness, debt mistakes, and ownership or incentive risk.",
            "- Stay skeptical but evidence-bound; do not infer dilution without actual issuance evidence.",
        ],
        "lynch": [
            "- Focus on whether the numbers support the business story, revenue growth versus EPS growth, margin direction, cash conversion, and whether the story is getting simpler or more complicated.",
            "- Explain the financial signals in plain investor language.",
        ],
    }
    return shared + doctrine_specific.get(doctrine_id, [])


def _section_signal(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        score = 0
        for nested in value.values():
            score += _section_signal(nested)
        return score
    if isinstance(value, str):
        return 1 if value.strip() else 0
    return 1


def _rating_for_sections(
    doctrine: Dict[str, Any],
    pcim: Dict[str, Any],
    required_sections: List[str],
    evidence_ids: List[str],
) -> str:
    missing = _missing_sections(pcim, required_sections)
    substantive_missing = [
        section
        for section in missing
        if section not in {"evidence_map", "uncertainty_missing_data"}
    ]
    if len(substantive_missing) >= 2 or len(missing) >= max(2, (len(required_sections) + 1) // 2):
        return "insufficient_evidence"

    signal_score = sum(_section_signal(_section_payload(pcim, section)) for section in required_sections)
    uncertainty_penalty = len((pcim.get("uncertainty_missing_data") or {}).get("missing_sections", []))
    adjusted = signal_score + len(evidence_ids) - uncertainty_penalty

    if adjusted >= 25 and not missing:
        return "strong"
    if adjusted >= 12:
        return "mixed"
    if evidence_ids:
        return "weak"
    return "insufficient_evidence"


def _generic_section_assessment(
    doctrine: Dict[str, Any],
    section_name: str,
    consumed_sections: List[str],
    missing_sections: List[str],
) -> str:
    focus = ", ".join(doctrine.get("primary_focus", [])[:2])
    if missing_sections:
        return (
            f"{section_name.replace('_', ' ').capitalize()} is constrained because "
            f"required PCIM evidence is incomplete for {', '.join(missing_sections)}. "
            f"The doctrine remains focused on {focus}."
        )
    return (
        f"{section_name.replace('_', ' ').capitalize()} is grounded in "
        f"{', '.join(consumed_sections)} and is interpreted through the doctrine focus on {focus}."
    )


def _key_findings(doctrine: Dict[str, Any], consumed_sections: List[str], missing_sections: List[str]) -> List[str]:
    findings = [
        f"{doctrine['investor_lens']} consumes {', '.join(consumed_sections)} from PCIM."
    ]
    findings.append(
        f"Primary focus: {', '.join(doctrine.get('primary_focus', [])[:3])}."
    )
    if missing_sections:
        findings.append(
            f"Evidence gaps remain in: {', '.join(missing_sections)}."
        )
    else:
        findings.append("All doctrine-required PCIM sections were available.")
    return findings


def _open_uncertainties(doctrine: Dict[str, Any], missing_sections: List[str], pcim: Dict[str, Any]) -> List[str]:
    uncertainties = []
    if missing_sections:
        uncertainties.append(
            f"Required PCIM sections missing or thin: {', '.join(missing_sections)}."
        )
    uncertainties.extend(doctrine.get("uncertainty_rules", []))
    for note in (pcim.get("uncertainty_missing_data") or {}).get("missing_sections", [])[:5]:
        year = note.get("year")
        section = note.get("section")
        reason = note.get("reason")
        uncertainties.append(f"{year} {section}: {reason}")
    return uncertainties


def _deterministic_panel_output(
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    pcim: Dict[str, Any],
) -> Dict[str, Any]:
    consumed_sections = list(doctrine["evidence_required_from_pcim"])
    missing_sections = _missing_sections(pcim, consumed_sections)
    evidence_ids = _collect_section_evidence_ids(pcim, consumed_sections)
    selected_pcim = _selected_pcim_view(pcim, consumed_sections)
    financial_context = _derive_financial_context(selected_pcim, consumed_sections, missing_sections)
    financial_metrics_used = [
        {
            "metric_id": entry["metric_id"],
            "metric": entry["canonical_metric"],
            "period": entry["period"],
            "used_for": "deterministic scaffold",
        }
        for entry in financial_context["metric_registry"]
    ]
    financial_warnings = financial_context["warnings"]
    financial_missing_sections = [
        section for section in missing_sections if section in FINANCIAL_PCIM_SECTIONS
    ]
    rating = _rating_for_sections(doctrine, pcim, consumed_sections, evidence_ids)
    multi_year = pcim.get("multi_year_inputs") or {}
    historical_context_used = "multi_year_inputs" in consumed_sections and not _section_empty(multi_year)
    years_considered = list(multi_year.get("years_covered", []) or pcim.get("available_years", []))

    assessment = {}
    for section_name in doctrine["output_contract"]["required_sections"]:
        assessment[section_name] = _generic_section_assessment(
            doctrine,
            section_name,
            consumed_sections,
            missing_sections,
        )

    return {
        "doctrine_id": doctrine["doctrine_id"],
        "company": company,
        "pcim_version": pcim.get("contract_version"),
        "pcim_source": str(pcim_path),
        "analysis_mode": "deterministic_scaffold",
        "sections_consumed": consumed_sections,
        "assessment": assessment,
        "rating": rating,
        "key_findings": _key_findings(doctrine, consumed_sections, missing_sections),
        "red_flags": list(doctrine.get("red_flags", [])),
        "open_uncertainties": _open_uncertainties(doctrine, missing_sections, pcim),
        "financial_metrics_used": financial_metrics_used,
        "financial_red_flags": [
            warning for warning in financial_warnings
            if any(token in warning.lower() for token in ("debt", "dilution", "fcf", "cfo", "comparability", "share count", "basis mismatch"))
        ],
        "financial_positive_signals": [],
        "financial_missing_data": list(dict.fromkeys(
            [f"Missing financial section: {section}" for section in financial_missing_sections]
            + list(financial_context["missing_data"])
        )),
        "financial_interpretation_limits": list(dict.fromkeys(
            list(financial_context["interpretation_limits"])
            + financial_warnings
            + (
                ["No compact financial PCIM sections were provided for this doctrine."]
                if not financial_context["financial_sections_consumed"]
                else []
            )
        )),
        "financial_assessment": {
            "financials_used": financial_context["financials_used"],
            "basis_used": financial_context["basis_used"],
            "key_financial_strengths": [],
            "key_financial_concerns": [
                f"Missing financial section: {section}" for section in financial_missing_sections
            ],
            "financial_red_flags": [
                warning for warning in financial_warnings
                if any(token in warning.lower() for token in ("debt", "dilution", "comparability", "basis", "fcf", "capex"))
            ],
            "missing_financial_data": list(financial_context["missing_data"]),
            "financial_interpretation_limits": list(financial_context["interpretation_limits"]),
            "financial_warnings_carried_forward": list(financial_warnings),
        },
        "financial_sections_consumed": financial_context["financial_sections_consumed"],
        "financial_warnings_carried_forward": financial_warnings,
        "evidence_ids": evidence_ids,
        "historical_context_used": historical_context_used,
        "years_considered": years_considered,
        "supporting_pcim_sections": consumed_sections,
        "evidence_id_normalization": {
            "applied": False,
            "replacements": [],
            "unresolved_ids": [],
        },
        "evidence_grounding_status": "pass",
        "evidence_grounding_warnings": [],
        "evidence_routing_diagnostics": {
            "removed_misrouted_evidence": [],
            "replaced_evidence": [],
            "claims_converted_to_limitations": [],
            "unresolved_claims": [],
        },
        "schema_warnings": [],
        "reasoning_limits": [
            "Dry-run/deterministic scaffold mode does not perform analyst-style LLM reasoning.",
            "Assessment text is structural and derived from doctrine plus PCIM availability only.",
        ],
        "user_facing_brief": {
            "title": LENS_CONFIG[doctrine["doctrine_id"]]["title"],
            "lens": LENS_CONFIG[doctrine["doctrine_id"]]["lens_text"],
            "what_looks_good": ["No live analyst reasoning was run in dry-run mode."],
            "what_needs_caution": ["This output is a deterministic scaffold and not a final investor judgment."],
            "what_is_missing": ["Analyst-specific LLM reasoning was not executed in dry-run mode."],
            "financial_lens": "Financial interpretation was not generated in dry-run mode, so any financial strengths or concerns remain provisional.",
            "bottom_line": "This dry-run payload preserves the schema shape only and should not be read as a finished analyst brief.",
        },
        "generated_at": utc_now(),
    }


def _filter_uncertainty_for_sections(pcim: Dict[str, Any], sections: List[str]) -> Dict[str, Any]:
    uncertainty = pcim.get("uncertainty_missing_data") or {}
    if not isinstance(uncertainty, dict):
        return {"incomplete_years": [], "missing_sections": [], "missing_items": []}

    relevant_missing = []
    for note in uncertainty.get("missing_sections", []) or []:
        if not isinstance(note, dict):
            continue
        if note.get("section") in sections:
            relevant_missing.append(note)

    relevant_missing_items = []
    for note in uncertainty.get("missing_items", []) or []:
        if not isinstance(note, dict):
            continue
        if note.get("section") in sections:
            relevant_missing_items.append(note)

    return {
        "incomplete_years": list(uncertainty.get("incomplete_years", []) or []),
        "missing_sections": relevant_missing,
        "missing_items": relevant_missing_items,
    }


def _selected_pcim_view(pcim: Dict[str, Any], sections: List[str]) -> Dict[str, Any]:
    selected: Dict[str, Any] = {}
    for section in sections:
        if section == "evidence_map":
            evidence_map = pcim.get("evidence_map") or {}
            selected["evidence_map"] = {
                key: list(evidence_map.get(key, []) or [])
                for key in sections
                if key not in {"evidence_map", "uncertainty_missing_data"}
            }
            continue
        if section == "uncertainty_missing_data":
            selected["uncertainty_missing_data"] = _filter_uncertainty_for_sections(pcim, sections)
            continue
        selected[section] = pcim.get(section)
    return selected


def _truncate_text(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3].rstrip() + "..."


def _estimate_prompt_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _serialized_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False))


def _section_char_cap(section: str) -> int:
    return SECTION_CHAR_CAPS.get(section, DEFAULT_SECTION_CHAR_CAP)


def _unique_preserve_order(items: List[Any]) -> List[Any]:
    seen = set()
    ordered: List[Any] = []
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _iter_string_values(value: Any) -> List[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        strings: List[str] = []
        for item in value:
            strings.extend(_iter_string_values(item))
        return strings
    if isinstance(value, dict):
        strings = []
        for nested in value.values():
            strings.extend(_iter_string_values(nested))
        return strings
    return []


def _collect_years_from_value(value: Any) -> List[str]:
    years: List[str] = []
    if isinstance(value, dict):
        year = value.get("year")
        if isinstance(year, str) and year.strip():
            years.append(year.strip())
        years_field = value.get("years")
        if isinstance(years_field, list):
            years.extend(str(item).strip() for item in years_field if str(item).strip())
        for nested in value.values():
            years.extend(_collect_years_from_value(nested))
    elif isinstance(value, list):
        for item in value:
            years.extend(_collect_years_from_value(item))
    return _unique_preserve_order([year for year in years if year])


def _collect_source_artifacts_from_value(value: Any) -> List[str]:
    artifacts: List[str] = []
    if isinstance(value, dict):
        artifact = value.get("source_artifact")
        if isinstance(artifact, str) and artifact.strip():
            artifacts.append(artifact.strip())
        artifacts_field = value.get("source_artifacts")
        if isinstance(artifacts_field, list):
            artifacts.extend(str(item).strip() for item in artifacts_field if str(item).strip())
        for nested in value.values():
            artifacts.extend(_collect_source_artifacts_from_value(nested))
    elif isinstance(value, list):
        for item in value:
            artifacts.extend(_collect_source_artifacts_from_value(item))
    return _unique_preserve_order([artifact for artifact in artifacts if artifact])


def _collect_evidence_ids_from_value(value: Any) -> List[str]:
    evidence_ids: List[str] = []
    if isinstance(value, dict):
        direct = value.get("evidence_id")
        if isinstance(direct, str) and direct.strip():
            evidence_ids.append(direct.strip())
        many = value.get("evidence_ids")
        if isinstance(many, list):
            evidence_ids.extend(str(item).strip() for item in many if str(item).strip())
        for nested in value.values():
            evidence_ids.extend(_collect_evidence_ids_from_value(nested))
    elif isinstance(value, list):
        for item in value:
            evidence_ids.extend(_collect_evidence_ids_from_value(item))
    return _unique_preserve_order([evidence_id for evidence_id in evidence_ids if evidence_id])


def _extract_summary_fragments(value: Any, *, max_items: int, item_limit: int) -> List[str]:
    fragments: List[str] = []
    for fragment in _iter_string_values(value):
        lowered = fragment.lower()
        if lowered.startswith("ev_"):
            continue
        if "source_chunk" in lowered:
            continue
        compact = _truncate_text(fragment, item_limit)
        if compact:
            fragments.append(compact)
        if len(fragments) >= max_items:
            break
    return _unique_preserve_order(fragments)[:max_items]


def _extract_metric_summaries(value: Any, *, max_items: int = 8) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []

    def visit(node: Any) -> None:
        if len(metrics) >= max_items:
            return
        if isinstance(node, dict):
            metric_name = node.get("metric") or node.get("field") or node.get("ratio_name")
            if metric_name:
                metric_payload: Dict[str, Any] = {"metric": str(metric_name)}
                if "value" in node and isinstance(node.get("value"), (int, float)):
                    metric_payload["value"] = node.get("value")
                elif "value_crore" in node and isinstance(node.get("value_crore"), (int, float)):
                    metric_payload["value"] = node.get("value_crore")
                elif "growth_percent" in node and isinstance(node.get("growth_percent"), (int, float)):
                    metric_payload["value"] = node.get("growth_percent")
                series = node.get("series")
                if isinstance(series, list) and series:
                    latest = series[0]
                    if isinstance(latest, dict):
                        if isinstance(latest.get("year"), str):
                            metric_payload["year"] = latest.get("year")
                        if isinstance(latest.get("value"), (int, float)):
                            metric_payload["value"] = latest.get("value")
                metrics.append(metric_payload)
                if len(metrics) >= max_items:
                    return
            for nested in node.values():
                visit(nested)
        elif isinstance(node, list):
            for item in node:
                visit(item)
                if len(metrics) >= max_items:
                    return

    visit(value)
    return _unique_preserve_order(metrics)[:max_items]


def _trim_strings_deep(value: Any, char_limit: int) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, char_limit)
    if isinstance(value, list):
        return [_trim_strings_deep(item, char_limit) for item in value]
    if isinstance(value, dict):
        return {key: _trim_strings_deep(nested, char_limit) for key, nested in value.items()}
    return value


def _generic_trim_section_to_cap(value: Any, cap: int) -> Tuple[Any, int, List[str]]:
    compacted = deepcopy(value)
    warnings: List[str] = []
    dropped_items = 0
    string_limits = [240, 180, 120, 80]
    list_caps = [8, 5, 3, 2, 1]

    def trim_lists(node: Any, item_cap: int) -> Any:
        nonlocal dropped_items
        if isinstance(node, list):
            if len(node) > item_cap:
                dropped_items += len(node) - item_cap
            return [trim_lists(item, item_cap) for item in node[:item_cap]]
        if isinstance(node, dict):
            return {key: trim_lists(nested, item_cap) for key, nested in node.items()}
        return node

    for string_limit in string_limits:
        compacted = _trim_strings_deep(compacted, string_limit)
        if _serialized_chars(compacted) <= cap:
            warnings.append(f"strings trimmed to {string_limit} chars")
            return compacted, dropped_items, warnings
        for item_cap in list_caps:
            compacted = trim_lists(compacted, item_cap)
            if _serialized_chars(compacted) <= cap:
                warnings.append(f"list items capped at {item_cap}")
                return compacted, dropped_items, warnings
    warnings.append("generic trim exhausted")
    return compacted, dropped_items, warnings


def _compact_section_replacement(
    section_name: str,
    section_value: Any,
    analyst: str,
    cap: int,
) -> Dict[str, Any]:
    retained_summary = _extract_summary_fragments(section_value, max_items=2, item_limit=160)
    limitations = _extract_summary_fragments(
        {"limitations": section_value.get("limitations")} if isinstance(section_value, dict) else section_value,
        max_items=2,
        item_limit=160,
    )
    replacement = {
        "section_compacted": True,
        "section_name": section_name,
        "analyst": analyst,
        "reason": "Section exceeded investor panel budget.",
        "retained_summary": retained_summary,
        "limitations": _unique_preserve_order(limitations + [SECTION_REPLACEMENT_LIMITATION])[:3],
    }
    if section_name == "multi_year_inputs":
        replacement["years_covered"] = _collect_years_from_value(section_value)[:4]
        replacement["evidence_ids"] = _collect_evidence_ids_from_value(section_value)[:4]
    while _serialized_chars(replacement) > cap:
        if replacement.get("retained_summary"):
            replacement["retained_summary"] = replacement["retained_summary"][:-1]
            continue
        if replacement.get("evidence_ids"):
            replacement["evidence_ids"] = replacement["evidence_ids"][:-1]
            continue
        if len(replacement.get("limitations", [])) > 1:
            replacement["limitations"] = replacement["limitations"][:1]
            continue
        if replacement.get("analyst"):
            replacement["analyst"] = ""
            continue
        if replacement.get("section_name"):
            replacement["section_name"] = ""
            continue
        replacement["reason"] = "Section omitted for prompt budget."
        if _serialized_chars(replacement) <= cap:
            break
        replacement = {
            "section_compacted": True,
            "reason": "Section exceeded investor panel budget.",
            "limitations": ["Context omitted due prompt budget."],
        }
        if section_name == "multi_year_inputs":
            replacement["years_covered"] = _collect_years_from_value(section_value)[:2]
        break
    return replacement


def _compact_multi_year_section(value: Any, analyst: str) -> Any:
    if not isinstance(value, dict):
        return {
            "available": False,
            "years_covered": [],
            "patterns": [
                {
                    "pattern": _truncate_text(str(value), 140),
                    "why_it_matters": "Historical context is compressed for the analyst prompt.",
                    "years": [],
                    "confidence": "low",
                    "warnings": [],
                    "limitations": [SECTION_REPLACEMENT_LIMITATION],
                    "source_artifacts": [],
                }
            ],
            "limitations": [SECTION_REPLACEMENT_LIMITATION],
            "evidence_ids": [],
        }

    pattern_descriptions = {
        "business_dna_evolution": "Business identity pattern remains relevant across years.",
        "management_consistency": "Management follow-through matters for repeatability and discipline.",
        "strategy_evolution": "Strategy shifts affect durability and comparability of the story.",
        "promise_follow_through": "Promise follow-through matters for management credibility.",
        "recurring_risks": "Recurring risks may persist despite changing commentary.",
        "capital_allocation_pattern": "Capital allocation pattern helps judge management choices over time.",
        "multi_year_financial_context": "Multi-year financial context affects historical interpretation.",
        "business_model_evolution": "Business-model changes affect historical comparability.",
    }
    patterns: List[Dict[str, Any]] = []
    for key, nested in value.items():
        if key in {"years_covered", "warnings", "limitations", "source_artifacts"}:
            continue
        fragments = _extract_summary_fragments(nested, max_items=2, item_limit=140)
        if not fragments:
            continue
        pattern = {
            "pattern": _truncate_text(key.replace("_", " "), 80),
            "why_it_matters": _truncate_text(pattern_descriptions.get(key, "Historical context is relevant to the analyst view."), 160),
            "years": _collect_years_from_value(nested)[:4] or list(value.get("years_covered", []) or [])[:4],
            "confidence": "medium",
            "warnings": _extract_summary_fragments(
                nested.get("warnings") if isinstance(nested, dict) else [],
                max_items=1,
                item_limit=120,
            ),
            "limitations": _extract_summary_fragments(
                nested.get("limitations") if isinstance(nested, dict) else [],
                max_items=1,
                item_limit=120,
            ),
            "source_artifacts": _collect_source_artifacts_from_value(nested)[:3],
        }
        if fragments:
            pattern["pattern"] = _truncate_text(f"{pattern['pattern']}: {fragments[0]}", 180)
        while _serialized_chars(pattern) > 500:
            if pattern["warnings"]:
                pattern["warnings"] = pattern["warnings"][:0]
                continue
            if pattern["limitations"]:
                pattern["limitations"] = pattern["limitations"][:0]
                continue
            if len(pattern["source_artifacts"]) > 1:
                pattern["source_artifacts"] = pattern["source_artifacts"][:1]
                continue
            pattern["why_it_matters"] = _truncate_text(pattern["why_it_matters"], max(80, len(pattern["why_it_matters"]) - 40))
            pattern["pattern"] = _truncate_text(pattern["pattern"], max(100, len(pattern["pattern"]) - 40))
            if _serialized_chars(pattern) <= 500:
                break
            break
        patterns.append(pattern)
        if len(patterns) >= 4:
            break
    compacted = {
        "years_covered": list(value.get("years_covered", []) or [])[:4],
        "patterns": patterns[:4],
        "evidence_ids": _collect_evidence_ids_from_value(value)[:8],
        "warnings": _extract_summary_fragments(value.get("warnings", []), max_items=2, item_limit=120),
        "limitations": _extract_summary_fragments(
            value.get("limitations", []),
            max_items=3,
            item_limit=140,
        )[:3],
        "source_artifacts": _collect_source_artifacts_from_value(value)[:4],
    }
    if not compacted["patterns"]:
        compacted["patterns"] = [
            {
                "pattern": "Historical context remained too large for full inclusion.",
                "why_it_matters": "Only the highest-level multi-year context is retained for this analyst.",
                "years": list(value.get("years_covered", []) or [])[:4],
                "confidence": "low",
                "warnings": [],
                "limitations": [SECTION_REPLACEMENT_LIMITATION],
                "source_artifacts": _collect_source_artifacts_from_value(value)[:2],
            }
        ]
    return compacted


def _compact_financial_quality_section(value: Any, analyst: str) -> Any:
    if not isinstance(value, dict):
        return {
            "basis_used": "unknown",
            "strengths": [],
            "concerns": _extract_summary_fragments(value, max_items=3, item_limit=160),
            "missing_data": [],
            "investor_questions": [],
            "key_metrics": [],
            "warnings": [SECTION_REPLACEMENT_LIMITATION],
            "analyst": analyst,
        }
    return {
        "basis_used": value.get("basis_used") or value.get("basis") or "unknown",
        "strengths": _extract_summary_fragments(
            value.get("strengths") or value.get("positive_signals") or value.get("signals") or [],
            max_items=5,
            item_limit=160,
        ),
        "concerns": _extract_summary_fragments(
            value.get("concerns") or value.get("red_flags") or value.get("warnings") or [],
            max_items=5,
            item_limit=160,
        ),
        "missing_data": _extract_summary_fragments(
            value.get("missing_data") or value.get("limitations") or [],
            max_items=5,
            item_limit=160,
        ),
        "investor_questions": _extract_summary_fragments(
            value.get("investor_questions") or value.get("recommended_next_actions") or [],
            max_items=5,
            item_limit=180,
        ),
        "key_metrics": _extract_metric_summaries(value, max_items=8),
        "warnings": _extract_summary_fragments(value.get("warnings", []), max_items=3, item_limit=140),
        "analyst": analyst,
    }


def _classify_capital_allocation_item(text: str) -> str:
    lowered = text.lower()
    shareholder_terms = ("dividend", "buyback", "payout", "shareholder return", "distribution")
    financing_terms = ("qip", "rights issue", "preferential", "debt", "borrow", "equity raise", "fund raise", "warrant")
    if any(term in lowered for term in shareholder_terms):
        return "shareholder_returns"
    if any(term in lowered for term in financing_terms):
        return "financing_actions"
    return "company_controlled_actions"


def _compact_capital_allocation_section(value: Any) -> Any:
    fragments = _extract_summary_fragments(value, max_items=18, item_limit=180)
    grouped = {
        "company_controlled_actions": [],
        "shareholder_returns": [],
        "financing_actions": [],
    }
    for fragment in fragments:
        bucket = _classify_capital_allocation_item(fragment)
        grouped[bucket].append(fragment)
    return {
        "company_controlled_actions": grouped["company_controlled_actions"][:5],
        "shareholder_returns": grouped["shareholder_returns"][:3],
        "financing_actions": grouped["financing_actions"][:3],
        "warnings": _extract_summary_fragments(
            value.get("warnings") if isinstance(value, dict) else [],
            max_items=3,
            item_limit=140,
        ),
        "limitations": _extract_summary_fragments(
            value.get("limitations") if isinstance(value, dict) else [],
            max_items=3,
            item_limit=140,
        ),
    }


def _section_specific_compaction(section_name: str, section_value: Any, analyst: str) -> Any:
    if section_name == "multi_year_inputs":
        return _compact_multi_year_section(section_value, analyst)
    if section_name == "financial_quality_inputs":
        return _compact_financial_quality_section(section_value, analyst)
    if section_name == "capital_allocation_inputs":
        return _compact_capital_allocation_section(section_value)
    return section_value


def enforce_section_char_cap(
    section_name: str,
    section_value: Any,
    cap: int,
    analyst: str,
) -> Tuple[Any, bool, int, int, int, List[str]]:
    original_chars = _serialized_chars(section_value)
    compacted = _section_specific_compaction(section_name, section_value, analyst)
    warnings: List[str] = []
    dropped_items_count = 0
    if compacted is not section_value:
        warnings.append(f"{section_name} received section-specific compaction")
    final_chars = _serialized_chars(compacted)
    if final_chars <= cap:
        return compacted, final_chars < original_chars, original_chars, final_chars, dropped_items_count, warnings

    compacted, dropped, generic_warnings = _generic_trim_section_to_cap(compacted, cap)
    dropped_items_count += dropped
    warnings.extend(generic_warnings)
    final_chars = _serialized_chars(compacted)
    if final_chars <= cap:
        return compacted, True, original_chars, final_chars, dropped_items_count, warnings

    replacement = _compact_section_replacement(section_name, compacted, analyst, cap)
    replacement_chars = _serialized_chars(replacement)
    warnings.append(f"{section_name} replaced with limitation object")
    return replacement, True, original_chars, replacement_chars, dropped_items_count, warnings


def _count_compactable_items(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, list):
        return sum(_count_compactable_items(item) for item in value)
    if isinstance(value, dict):
        score = 1 if any(
            key in value
            for key in (
                "value",
                "source_item_id",
                "source_item_ids",
                "entity_name",
                "business_summary",
                "normalized_promise_theme",
                "year",
            )
        ) else 0
        for nested in value.values():
            score += _count_compactable_items(nested)
        return score
    return 0


def _limit_for_section(section: str, limits: Dict[str, int]) -> int:
    if section == "risk_inputs":
        return limits["max_risks"]
    if section == "capital_allocation_inputs":
        return limits["max_capital_allocation_items"]
    return limits["max_items_per_section"]


def _compact_evidence_reference(
    reference: Any,
    *,
    excerpt_chars: int,
    fallback_source_artifact: Any = None,
) -> Tuple[Dict[str, Any], bool]:
    if not isinstance(reference, dict):
        excerpt = _truncate_text(reference, excerpt_chars)
        payload = {
            "evidence_id": None,
            "page": None,
            "short_excerpt": excerpt,
            "source_artifact": fallback_source_artifact,
        }
        return payload, bool(str(reference or "").strip())

    evidence_id = reference.get("evidence_id")
    if evidence_id is None:
        evidence_ids = reference.get("evidence_ids")
        if isinstance(evidence_ids, list) and evidence_ids:
            evidence_id = evidence_ids[0]
    short_excerpt_source = (
        reference.get("short_excerpt")
        or reference.get("source_chunk")
        or reference.get("content")
        or reference.get("summary")
        or reference.get("statement")
        or ""
    )
    payload = {
        "evidence_id": evidence_id,
        "page": reference.get("page"),
        "short_excerpt": _truncate_text(short_excerpt_source, excerpt_chars),
        "source_artifact": reference.get("source_artifact") or fallback_source_artifact,
    }
    truncated = bool(reference.get("source_chunk")) or len(str(short_excerpt_source or "")) > excerpt_chars
    return payload, truncated


def _compact_value_for_prompt(
    value: Any,
    *,
    section: str,
    limits: Dict[str, int],
    current_key: Optional[str] = None,
    fallback_source_artifact: Any = None,
) -> Tuple[Any, bool]:
    excerpt_chars = limits["max_evidence_excerpt_chars"]
    if value is None or isinstance(value, (bool, int, float)):
        return value, False

    if isinstance(value, str):
        if current_key in DROP_KEYS:
            return None, bool(value.strip())
        string_limit = excerpt_chars if current_key in {"content", "summary", "statement", "reason"} else excerpt_chars * 2
        truncated = len(value) > string_limit
        return _truncate_text(value, string_limit), truncated

    if isinstance(value, list):
        if current_key == "evidence_ids":
            normalized = [str(item) for item in value if str(item).strip()]
            return normalized, False

        if current_key == "evidence_references":
            cap = min(10, limits["max_items_per_section"])
            items = value[:cap]
            compacted_items = []
            truncated = len(value) > cap
            for item in items:
                compacted, item_truncated = _compact_evidence_reference(
                    item,
                    excerpt_chars=excerpt_chars,
                    fallback_source_artifact=fallback_source_artifact,
                )
                compacted_items.append(compacted)
                truncated = truncated or item_truncated
            return compacted_items, truncated

        cap = _limit_for_section(section, limits)
        items = value[:cap]
        compacted_items = []
        truncated = len(value) > cap
        for item in items:
            compacted, item_truncated = _compact_value_for_prompt(
                item,
                section=section,
                limits=limits,
                current_key=current_key,
                fallback_source_artifact=fallback_source_artifact,
            )
            if compacted in (None, {}, []):
                truncated = truncated or item_truncated
                continue
            compacted_items.append(compacted)
            truncated = truncated or item_truncated
        return compacted_items, truncated

    if isinstance(value, dict):
        if current_key == "evidence_map":
            cap = min(10, limits["max_items_per_section"])
            compacted_map = {}
            truncated = False
            for evidence_section, evidence_ids in value.items():
                ids = [str(item) for item in (evidence_ids or []) if str(item).strip()]
                compacted_map[evidence_section] = {
                    "count": len(ids),
                    "sample_evidence_ids": ids[:cap],
                }
                truncated = truncated or len(ids) > cap
            return compacted_map, truncated

        if current_key == "uncertainty_missing_data":
            missing_sections = value.get("missing_sections") or []
            cap = _limit_for_section(section, limits)
            compacted_missing = []
            truncated = len(missing_sections) > cap
            for note in missing_sections[:cap]:
                if not isinstance(note, dict):
                    continue
                compacted_missing.append(
                    {
                        "year": note.get("year"),
                        "section": note.get("section"),
                        "reason": _truncate_text(note.get("reason"), excerpt_chars),
                    }
                )
            return {
                "incomplete_years": list(value.get("incomplete_years", []) or [])[:cap],
                "missing_sections": compacted_missing,
            }, truncated

        compacted_dict: Dict[str, Any] = {}
        truncated = False
        next_fallback_source_artifact = value.get("source_artifact") or fallback_source_artifact
        for key, nested in value.items():
            if key in DROP_KEYS:
                truncated = truncated or bool(str(nested or "").strip())
                continue
            compacted, nested_truncated = _compact_value_for_prompt(
                nested,
                section=section,
                limits=limits,
                current_key=key,
                fallback_source_artifact=next_fallback_source_artifact,
            )
            if compacted in (None, {}, []):
                truncated = truncated or nested_truncated
                continue
            compacted_dict[key] = compacted
            truncated = truncated or nested_truncated
        return compacted_dict, truncated

    return str(value), False


def _build_compact_pcim_view(
    pcim: Dict[str, Any],
    sections: List[str],
    limits: Dict[str, int],
    analyst: str,
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], bool]:
    selected_pcim = _selected_pcim_view(pcim, sections)
    compacted: Dict[str, Any] = {}
    stats: Dict[str, Dict[str, Any]] = {}
    truncated = False

    for section, value in selected_pcim.items():
        before = _count_compactable_items(value)
        compacted_value, section_truncated = _compact_value_for_prompt(
            value,
            section=section,
            limits=limits,
            current_key=section,
        )
        section_cap = _section_char_cap(section)
        (
            compacted_value,
            hard_compacted,
            original_chars,
            final_chars,
            dropped_items_count,
            cap_warnings,
        ) = enforce_section_char_cap(
            section,
            compacted_value,
            section_cap,
            analyst,
        )
        after = _count_compactable_items(compacted_value)
        compacted[section] = compacted_value
        stats[section] = {
            "before": before,
            "after": after,
            "original_chars": original_chars,
            "final_chars": final_chars,
            "section_cap": section_cap,
            "dropped_items_count": dropped_items_count,
            "warnings": cap_warnings,
        }
        truncated = truncated or section_truncated or hard_compacted or after < before

    return compacted, stats, truncated


def _shrink_limits(limits: Dict[str, int]) -> Optional[Dict[str, int]]:
    next_limits = dict(limits)
    next_limits["max_items_per_section"] = max(
        MIN_MAX_ITEMS_PER_SECTION,
        next_limits["max_items_per_section"] // 2,
    )
    next_limits["max_risks"] = max(
        MIN_MAX_RISKS,
        next_limits["max_risks"] // 2,
    )
    next_limits["max_capital_allocation_items"] = max(
        MIN_MAX_CAPITAL_ALLOCATION_ITEMS,
        next_limits["max_capital_allocation_items"] // 2,
    )
    next_limits["max_evidence_excerpt_chars"] = max(
        MIN_MAX_EVIDENCE_EXCERPT_CHARS,
        next_limits["max_evidence_excerpt_chars"] // 2,
    )
    next_limits["max_total_prompt_chars"] = max(
        MIN_MAX_TOTAL_PROMPT_CHARS,
        int(next_limits["max_total_prompt_chars"] * 0.8),
    )
    next_limits["max_text_chars_per_value"] = max(
        MIN_MAX_TEXT_CHARS_PER_VALUE,
        int(next_limits["max_text_chars_per_value"] * 0.75),
    )
    next_limits["max_nested_items_per_item"] = max(
        1,
        next_limits["max_nested_items_per_item"] - 1,
    )
    next_limits["max_evidence_ids_per_item"] = max(
        1,
        next_limits["max_evidence_ids_per_item"] - 1,
    )
    next_limits["max_dict_keys_per_item"] = max(
        3,
        next_limits["max_dict_keys_per_item"] - 1,
    )
    if next_limits == limits:
        return None
    return next_limits


def _section_prompt_sizes(compact_pcim: Dict[str, Any]) -> Dict[str, int]:
    selected = compact_pcim or {}
    return {
        key: len(json.dumps(value, ensure_ascii=False))
        for key, value in selected.items()
    }


def _largest_offending_fields(compact_pcim: Dict[str, Any], *, limit: int = 5) -> List[str]:
    section_sizes = _section_prompt_sizes(compact_pcim)
    ordered = sorted(section_sizes.items(), key=lambda item: item[1], reverse=True)
    return [f"{name}={size}" for name, size in ordered[:limit]]


def _prepare_compact_prompt_pack(
    pcim: Dict[str, Any],
    sections: List[str],
    analyst: str,
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], Dict[str, int], bool]:
    limits = _prompt_compaction_limits()
    while True:
        compacted_pcim, stats, truncated = _build_compact_pcim_view(pcim, sections, limits, analyst)
        compact_chars = len(json.dumps(compacted_pcim, ensure_ascii=False))
        if compact_chars <= limits["max_total_prompt_chars"]:
            return compacted_pcim, stats, limits, truncated
        next_limits = _shrink_limits(limits)
        if next_limits is None:
            return compacted_pcim, stats, limits, True
        limits = next_limits


def _build_compact_prompt(
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    pcim: Dict[str, Any],
    sections: List[str],
) -> Tuple[str, Dict[str, Any], Dict[str, Dict[str, int]], Dict[str, int], bool, Dict[str, Any]]:
    stage_budget = resolve_stage_token_budget("investor_panel_analyst")
    raw_selected_pcim = _selected_pcim_view(pcim, sections)
    raw_largest_sections = _largest_offending_fields(raw_selected_pcim)
    compact_pcim, section_stats, limits_used, input_compacted = _prepare_compact_prompt_pack(
        pcim,
        sections,
        doctrine["doctrine_id"],
    )
    llm_input_pack = _build_prompt_input_pack(
        company=company,
        doctrine=doctrine,
        pcim_path=pcim_path,
        compact_pcim=compact_pcim,
        allowed_sections=sections,
        limits_used=limits_used,
        input_compacted=input_compacted,
    )
    prompt = _build_llm_prompt(
        doctrine=doctrine,
        company=company,
        pcim_path=pcim_path,
        llm_input_pack=llm_input_pack,
        allowed_sections=sections,
    )
    initial_prompt_chars = len(prompt)
    initial_prompt_tokens = _estimate_prompt_tokens(prompt)
    initial_pack_tokens = llm_input_pack.get("metadata", {}).get("tokens_estimated") or _estimate_prompt_tokens(
        json.dumps(llm_input_pack, ensure_ascii=False)
    )
    while True:
        prompt_chars = len(prompt)
        prompt_tokens = _estimate_prompt_tokens(prompt)
        pack_tokens = llm_input_pack.get("metadata", {}).get("tokens_estimated") or _estimate_prompt_tokens(
            json.dumps(llm_input_pack, ensure_ascii=False)
        )
        hard_char_limit = limits_used.get("hard_max_prompt_chars") or 0
        over_hard_char_limit = bool(hard_char_limit and prompt_chars > hard_char_limit)
        if prompt_tokens <= stage_budget and pack_tokens <= stage_budget and not over_hard_char_limit:
            break
        next_limits = _shrink_limits(limits_used)
        if next_limits is None:
            break
        limits_used = next_limits
        compact_pcim, section_stats, next_truncated = _build_compact_pcim_view(
            pcim,
            sections,
            limits_used,
            doctrine["doctrine_id"],
        )
        input_compacted = input_compacted or next_truncated
        llm_input_pack = _build_prompt_input_pack(
            company=company,
            doctrine=doctrine,
            pcim_path=pcim_path,
            compact_pcim=compact_pcim,
            allowed_sections=sections,
            limits_used=limits_used,
            input_compacted=input_compacted,
        )
        prompt = _build_llm_prompt(
            doctrine=doctrine,
            company=company,
            pcim_path=pcim_path,
            llm_input_pack=llm_input_pack,
            allowed_sections=sections,
        )
    prompt_chars = len(prompt)
    prompt_tokens = _estimate_prompt_tokens(prompt)
    pack_tokens = llm_input_pack.get("metadata", {}).get("tokens_estimated") or _estimate_prompt_tokens(
        json.dumps(llm_input_pack, ensure_ascii=False)
    )
    compacted_largest_sections = _largest_offending_fields(compact_pcim)
    section_cap_violations = [
        f"{section}={stats['final_chars']}>{stats['section_cap']}"
        for section, stats in section_stats.items()
        if stats["final_chars"] > stats["section_cap"]
    ]
    hard_char_limit = limits_used.get("hard_max_prompt_chars") or 0
    over_hard_char_limit = bool(hard_char_limit and prompt_chars > hard_char_limit)
    warnings: List[str] = []
    budget_status = "pass"
    if prompt_chars > limits_used["max_total_prompt_chars"]:
        budget_status = "pass_with_warning"
        warnings.append("prompt_chars exceeded soft target but token budget passed")
    if prompt_tokens > stage_budget or pack_tokens > stage_budget or over_hard_char_limit or section_cap_violations:
        raise ValueError(
            "Investor panel prompt remains above budget after compaction: "
            f"prompt_chars={prompt_chars}, prompt_tokens={prompt_tokens}, pack_tokens={pack_tokens}, "
            f"raw_largest_sections={raw_largest_sections}, "
            f"compacted_largest_sections={compacted_largest_sections}, "
            f"section_cap_violations={section_cap_violations}, "
            f"suggested_caps=max_items_per_section<={limits_used['max_items_per_section']}, "
            f"max_nested_items_per_item<={limits_used['max_nested_items_per_item']}, "
            f"max_text_chars_per_value<={limits_used['max_text_chars_per_value']}"
        )
    budget_report = {
        "token_budget": stage_budget,
        "prompt_tokens_before": initial_prompt_tokens,
        "prompt_tokens_after": prompt_tokens,
        "pack_tokens_before": initial_pack_tokens,
        "pack_tokens_after": pack_tokens,
        "prompt_chars_before": initial_prompt_chars,
        "prompt_chars_after": prompt_chars,
        "raw_largest_sections": raw_largest_sections,
        "compacted_largest_sections": compacted_largest_sections,
        "section_caps": {
            section: stats["section_cap"]
            for section, stats in section_stats.items()
        },
        "budget_status": budget_status,
        "warnings": warnings,
    }
    return prompt, compact_pcim, section_stats, limits_used, input_compacted, budget_report


def _build_prompt_input_pack(
    *,
    company: str,
    doctrine: Dict[str, Any],
    pcim_path: Path,
    compact_pcim: Dict[str, Any],
    allowed_sections: List[str],
    limits_used: Dict[str, int],
    input_compacted: bool,
) -> Dict[str, Any]:
    limitations = [COMPACTION_REASONING_LIMIT] if input_compacted else []
    max_dict_keys = max(
        limits_used["max_dict_keys_per_item"],
        len(allowed_sections) + 2,
    )
    max_sections = max(
        limits_used["max_sections"],
        len(allowed_sections) + 1,
    )
    return build_llm_input_pack(
        stage="investor_panel_analyst",
        purpose=f"Produce doctrine-bound investor analysis for {doctrine['doctrine_id']} from declared PCIM sections only.",
        company=company,
        year=None,
        observations=[
            {
                "selected_pcim": compact_pcim,
            }
        ],
        limitations=limitations,
        source_artifacts=[str(pcim_path)],
        pack_name=f"{doctrine['doctrine_id']}_input_pack",
        policy={
            "allowed_sections": ["selected_pcim"],
            "max_items": limits_used["max_items_per_section"],
            "max_chars": limits_used["max_total_prompt_chars"],
            "include_evidence_ids": True,
            "collect_evidence_ids": False,
            "include_short_excerpts": False,
            "include_source_chunks": False,
            "max_sections": max_sections,
            "max_items_per_section": limits_used["max_items_per_section"],
            "max_nested_items_per_item": limits_used["max_nested_items_per_item"],
            "max_text_chars_per_value": limits_used["max_text_chars_per_value"],
            "max_evidence_ids_per_item": limits_used["max_evidence_ids_per_item"],
            "max_dict_keys_per_item": max_dict_keys,
            "drop_raw_evidence_references": True,
        },
    )


def _required_assessment_keys(doctrine: Dict[str, Any]) -> List[str]:
    return [
        key
        for key in doctrine["output_contract"]["required_sections"]
        if key != "open_uncertainties"
    ]


def _llm_output_template(doctrine: Dict[str, Any], allowed_sections: List[str]) -> Dict[str, Any]:
    assessment = {key: "string" for key in _required_assessment_keys(doctrine)}
    return {
        "assessment": assessment,
        "rating": "strong | mixed | weak | insufficient_evidence",
        "key_findings": [
            {
                "finding": "string",
                "evidence_ids": ["string"],
            }
        ],
        "red_flags": [
            {
                "flag": "string",
                "severity": "low | medium | high",
                "evidence_ids": ["string"],
            }
        ],
        "open_uncertainties": [
            {
                "uncertainty": "string",
                "evidence_ids": ["string"],
            }
        ],
        "financial_metrics_used": [
            {
                "metric_id": "revenue:fy25",
                "metric": "revenue",
                "period": "fy25",
                "used_for": "growth context",
            }
        ],
        "financial_red_flags": ["string"],
        "financial_positive_signals": ["string"],
        "financial_missing_data": ["string"],
        "financial_interpretation_limits": ["string"],
        "financial_assessment": {
            "financials_used": True,
            "basis_used": "consolidated|standalone|unknown",
            "key_financial_strengths": ["string"],
            "key_financial_concerns": ["string"],
            "financial_red_flags": ["string"],
            "missing_financial_data": ["string"],
            "financial_interpretation_limits": ["string"],
            "financial_warnings_carried_forward": ["string"],
        },
        "evidence_ids": ["string"],
        "historical_context_used": True,
        "years_considered": ["fy24", "fy25"],
        "supporting_pcim_sections": allowed_sections,
        "schema_warnings": ["string"],
        "reasoning_limits": ["string"],
        "user_facing_brief": {
            "title": {
                "graham": "Graham School of Thought: Downside Protection",
                "buffett": "Buffett School of Thought: Business Quality & Capital Allocation",
                "fisher": "Fisher School of Thought: Growth Quality & Management Ambition",
                "munger": "Munger School of Thought: Incentives, Governance & Avoidable Mistakes",
                "lynch": "Lynch School of Thought: Simple Story, Growth Runway & Hype Check",
            }.get(doctrine["doctrine_id"], "string"),
            "lens": LENS_CONFIG[doctrine["doctrine_id"]]["lens_text"],
            "what_looks_good": ["string"],
            "what_needs_caution": ["string"],
            "what_is_missing": ["string"],
            "financial_lens": "string",
            "bottom_line": "string",
        },
    }


def _build_system_prompt() -> str:
    return (
        "You are an investor-panel analyst inside Prometheus. "
        "Reason only from the supplied PCIM sections and doctrine configuration. "
        "Do not use outside knowledge, do not invent evidence, and do not make buy/sell/hold recommendations. "
        "Return exactly one valid JSON object matching the requested schema."
    )


def _shared_evidence_routing_rules() -> List[str]:
    return [
        "Evidence routing:",
        "- Revenue, CFO, receivable, debt, and similar financial claims should rely on financial_metrics_used, matching financial evidence, or both.",
        "- Governance, integrity, and incentive claims must use governance, ownership, compensation, board, committee, related-party, capital-allocation, or explicit uncertainty evidence.",
        "- Market-risk evidence supports only FX, currency, interest-rate, or market-risk claims unless risk oversight is explicit.",
        "- Section names and JSON filenames are never valid evidence IDs.",
        "- If stronger evidence is missing, downgrade the claim into a limitation rather than forcing unrelated evidence IDs.",
    ]


def _format_allowed_financial_metrics(metric_registry: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    formatted: List[Dict[str, Any]] = []
    for entry in metric_registry:
        formatted.append(
            {
                "metric_id": entry.get("metric_id"),
                "display_name": entry.get("display_name"),
                "period": entry.get("period"),
                "value": entry.get("value"),
                "unit": entry.get("unit"),
                "basis": entry.get("basis"),
                "confidence": entry.get("confidence"),
            }
        )
    return formatted


def _build_llm_prompt(
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    llm_input_pack: Dict[str, Any],
    allowed_sections: List[str],
) -> str:
    compact_pack = deepcopy(llm_input_pack)
    compact_pack.pop("input_policy", None)
    compact_pack_text = json.dumps(compact_pack, ensure_ascii=False, separators=(",", ":"))
    compact_shape_text = json.dumps(_llm_output_template(doctrine, allowed_sections), ensure_ascii=False, separators=(",", ":"))
    compact_selected_pcim = ((llm_input_pack.get("observations") or [{}])[0].get("selected_pcim") or {})
    metric_registry = _build_financial_metric_registry(compact_selected_pcim, allowed_sections)
    return "\n".join(
        [
            f"Company: {company}",
            f"Doctrine ID: {doctrine['doctrine_id']}",
            f"Investor Lens: {doctrine['investor_lens']}",
            f"PCIM Source: {pcim_path}",
            "Task: Produce a structured investor analysis from PCIM only.",
            "",
            "Rules:",
            "- Use only the PCIM sections provided below.",
            "- Return only valid JSON. No markdown, no prose before or after JSON.",
            "- Return one valid JSON object containing both the internal analysis fields and user_facing_brief.",
            "- If evidence is missing or conflicting, say so explicitly.",
            "- Cite evidence_ids for every major finding, red flag, and uncertainty when available.",
            "- Financial interpretation must use only metrics already present in the supplied PCIM sections.",
            "- Do not calculate new ratios, spreads, or derived financial metrics that are not already present in PCIM.",
            "- If CFO, FCF, ROCE, share count, or comparability inputs are missing, say so under financial_missing_data or financial_interpretation_limits.",
            "- You must mention each major financial warning in financial_assessment.missing_financial_data, financial_assessment.financial_interpretation_limits, or financial_assessment.financial_warnings_carried_forward.",
            "- You must include the exact major financial warnings below in financial_assessment.financial_warnings_carried_forward.",
            "- You must also include those warnings in missing_financial_data or financial_interpretation_limits where relevant.",
            "- Do not hide missing financial data. If a warning is doctrine-irrelevant, still carry it forward as a limitation.",
            "- Do not invent a fix or estimate missing values.",
            "- Do not claim FCF, owner earnings, or FCF-supported dividend quality when FCF or capex is missing.",
            "- Do not introduce facts or conclusions not present in selected PCIM.",
            "- Prefer the most material 3-7 findings rather than listing everything.",
            "- Do not treat dividends, related-party advances, or governance ambiguity as automatic condemnation without context from the supplied PCIM.",
            *_shared_evidence_routing_rules(),
            "- Use multi_year_inputs only as historical context when that section is provided.",
            "- Treat two-year trends as provisional unless the supplied evidence clearly supports a stronger claim.",
            "- Do not infer promise fulfillment unless it is explicitly shown in the supplied evidence.",
            "- Treat not_detected_this_year as absence of detection, not confirmed discontinuation.",
            "- user_facing_brief must not mention PCIM, evidence_ids, analysis_mode, sections_consumed, evidence_map, or reasoning_limits.",
            "- user_facing_brief must not contain evidence ID patterns like ev_ and must not contain buy/sell/hold recommendation language.",
            "- user_facing_brief should use simple, serious investor language and preserve the analyst's school of thought.",
            "- user_facing_brief must be a faithful summary of the internal analysis, not a second analysis.",
            "- The user_facing_brief must be written for an investor and must not mention internal system terms such as PCIM, CIM, evidence IDs, schemas, artifacts, validators, source chunks, or input packs.",
            "- supporting_pcim_sections must contain only values from the allowed list shown below.",
            "",
            "Allowed supporting_pcim_sections:",
            json.dumps(allowed_sections, ensure_ascii=False, separators=(",", ":")),
            "",
            "Allowed Financial Metrics:",
            json.dumps(
                _format_allowed_financial_metrics(metric_registry),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "- financial_metrics_used should prefer objects with metric_id, metric, period, and used_for.",
            "- supporting_pcim_sections must use only the allowed section names above.",
            "- financial_metrics_used must use only the allowed metric_ids or obvious aliases of the allowed metrics with the correct period.",
            "- If a metric is not listed above, do not mention it under financial_metrics_used.",
            "- If you need to mention missing evidence, do that under financial_missing_data or financial_interpretation_limits instead of inventing a metric.",
            '- All list fields must be valid JSON arrays. Never return a plain string for reasoning_limits, evidence_gaps, missing_financial_data, financial_interpretation_limits, financial_warnings_carried_forward, key_financial_strengths, key_financial_concerns, financial_red_flags, or financial_sections_consumed.',
            '- Correct example: "reasoning_limits": ["No valuation was performed.", "Owner earnings could not be assessed because FCF/capex is missing."]',
            '- Incorrect example: "reasoning_limits": "No valuation was performed."',
            "",
            "Major Financial Warnings To Carry Forward:",
            json.dumps(
                _canonical_required_financial_warning_groups(
                    _derive_financial_context(
                        compact_selected_pcim,
                        allowed_sections,
                        [],
                    )
                ),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "",
            "Doctrine primary focus:",
            json.dumps(doctrine.get("primary_focus", []), ensure_ascii=False, separators=(",", ":")),
            "",
            "Financial reasoning instructions:",
            json.dumps(_financial_instruction_block(doctrine["doctrine_id"]), ensure_ascii=False, separators=(",", ":")),
            "",
            "Canonical principles:",
            json.dumps(doctrine.get("canonical_principles", []), ensure_ascii=False, separators=(",", ":")),
            "",
            "Canonical questions:",
            json.dumps(doctrine.get("canonical_questions", []), ensure_ascii=False, separators=(",", ":")),
            "",
            "Red flags to watch:",
            json.dumps(doctrine.get("red_flags", []), ensure_ascii=False, separators=(",", ":")),
            "",
            "Uncertainty rules:",
            json.dumps(doctrine.get("uncertainty_rules", []), ensure_ascii=False, separators=(",", ":")),
            "",
            "Historical-context guidance for this analyst:",
            json.dumps(
                {
                    "graham": "Use multi_year_inputs to assess recurring financial or risk concerns, worsening liquidity, capital-allocation pattern, and missing cash-flow evidence.",
                    "buffett": "Use multi_year_inputs to assess consistency of business direction, capital-allocation pattern, repeated themes, and durability of business quality.",
                    "fisher": "Use multi_year_inputs to assess management ambition, execution continuity, product or R&D promises, and whether growth claims are followed through.",
                    "munger": "Use multi_year_inputs to assess incentives, governance ambiguity, recurring risks, related-party or internal-control or regulatory issues, and avoidable mistakes.",
                    "lynch": "Use multi_year_inputs to assess whether the story remains simple and consistent, whether growth matches observable evidence, and whether hype is increasing.",
                }.get(doctrine["doctrine_id"], ""),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "",
            "Required JSON shape:",
            compact_shape_text,
            "",
            "Selected compact PCIM sections:",
            compact_pack_text,
        ]
    )


def _truncate_normalized_list_string(value: str) -> str:
    return _truncate_text(value, NORMALIZED_LIST_STRING_LIMIT)


def _contains_raw_payload_leak(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).strip().lower() in {"source_chunk", "raw_text", "full_text"}:
                return True
            if _contains_raw_payload_leak(nested):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_raw_payload_leak(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(token in lowered for token in ('"source_chunk"', "source_chunk", "raw_text", "full_text"))
    return False


def _safe_stringify_list_item(item: Any, field: str) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, (int, float, bool)):
        return str(item).strip()
    if isinstance(item, dict):
        if _contains_raw_payload_leak(item):
            raise ValueError(f"{field} contains forbidden raw payload fields")
        for key in SAFE_LIST_DICT_PREFERRED_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (int, float, bool)):
                return str(value).strip()
        scalar_pairs: List[str] = []
        for key, value in item.items():
            if isinstance(value, (dict, list)):
                raise ValueError(f"{field} contains nested objects that cannot be safely normalized")
            if value is None:
                continue
            compact = str(value).strip()
            if compact:
                scalar_pairs.append(f"{key}: {compact}")
        if not scalar_pairs:
            raise ValueError(f"{field} contains an object that cannot be safely normalized")
        return "; ".join(scalar_pairs[:3])
    raise ValueError(f"{field} contains items that cannot be safely normalized")


def _normalize_string_list(
    value: Any,
    field: str,
    schema_warnings: Optional[List[str]] = None,
    *,
    default_empty: bool = False,
) -> List[str]:
    warnings = schema_warnings if schema_warnings is not None else []
    if value is None:
        if default_empty:
            warnings.append(f"{field} was null or missing and normalized to empty list.")
            return []
        raise ValueError(f"{field} must be a list")
    if _contains_raw_payload_leak(value):
        raise ValueError(f"{field} contains forbidden raw payload fields")

    items: List[Any]
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        warnings.append(f"{field} was returned as string and normalized to list.")
        items = [value]
    elif isinstance(value, dict):
        warnings.append(f"{field} was returned as object and normalized to list.")
        items = [value]
    else:
        raise ValueError(f"{field} must be a list")

    normalized: List[str] = []
    coerced = not isinstance(value, list)
    for item in items:
        if isinstance(item, list):
            raise ValueError(f"{field} contains nested lists that cannot be safely normalized")
        text = _safe_stringify_list_item(item, field).strip()
        if not text:
            continue
        truncated = _truncate_normalized_list_string(text)
        if truncated != text:
            coerced = True
            warnings.append(f"{field} contained a long value and it was truncated during normalization.")
        normalized.append(truncated)
        if not isinstance(item, str):
            coerced = True

    normalized = _unique_preserve_order([item for item in normalized if item])
    if coerced and isinstance(value, list) and any(not isinstance(item, str) for item in items):
        warnings.append(f"{field} contained non-string items and was normalized to list[str].")
    return normalized


def _normalize_optional_bool(value: Any, field: str, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean when provided")
    return value


def _normalize_findings(value: Any, field: str) -> Tuple[List[str], List[str]]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    findings: List[str] = []
    evidence_ids: List[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            item_evidence: List[str] = []
        elif isinstance(item, dict):
            text = str(item.get("finding") or item.get("flag") or item.get("uncertainty") or "").strip()
            item_evidence = _normalize_optional_evidence_ids(item.get("evidence_ids"), field)
        else:
            raise ValueError(f"{field} items must be strings or objects")
        if not text:
            raise ValueError(f"{field} items must include non-empty text")
        findings.append(text)
        for evidence_id in item_evidence:
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
    return findings, evidence_ids


def _normalize_findings_with_map(value: Any, field: str) -> Tuple[List[str], List[str], List[List[str]]]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    findings: List[str] = []
    merged_evidence: List[str] = []
    per_item_evidence: List[List[str]] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            item_evidence = []
        elif isinstance(item, dict):
            text = str(item.get("finding") or item.get("flag") or item.get("uncertainty") or "").strip()
            item_evidence = _normalize_optional_evidence_ids(item.get("evidence_ids"), field)
        else:
            raise ValueError(f"{field} items must be strings or objects")
        if not text:
            raise ValueError(f"{field} items must include non-empty text")
        findings.append(text)
        per_item_evidence.append(item_evidence)
        for evidence_id in item_evidence:
            if evidence_id not in merged_evidence:
                merged_evidence.append(evidence_id)
    return findings, merged_evidence, per_item_evidence


def _normalize_optional_text_list_fields(parsed: Dict[str, Any], schema_warnings: List[str]) -> Dict[str, List[str]]:
    optional_fields = (
        "key_concerns",
        "key_questions",
        "evidence_gaps",
    )
    normalized: Dict[str, List[str]] = {}
    for field in optional_fields:
        normalized[field] = _normalize_string_list(
            parsed.get(field),
            field,
            schema_warnings,
            default_empty=True,
        )
    return normalized


def _merge_normalization_summaries(*summaries: Dict[str, Any]) -> Dict[str, Any]:
    replacements: List[Dict[str, str]] = []
    unresolved_ids: List[str] = []
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        for replacement in summary.get("replacements", []) or []:
            if replacement not in replacements:
                replacements.append(replacement)
        for unresolved_id in summary.get("unresolved_ids", []) or []:
            if unresolved_id not in unresolved_ids:
                unresolved_ids.append(unresolved_id)
    return {
        "applied": bool(replacements),
        "replacements": replacements,
        "unresolved_ids": unresolved_ids,
    }


def _strip_section_name_evidence_ids(
    evidence_ids: List[str],
    *,
    field_name: str,
    schema_warnings: List[str],
    removed_records: Optional[List[Dict[str, str]]] = None,
) -> List[str]:
    cleaned: List[str] = []
    removed: List[str] = []
    for evidence_id in evidence_ids:
        if evidence_id in INVALID_SECTION_NAME_EVIDENCE_IDS:
            removed.append(evidence_id)
            if removed_records is not None:
                removed_records.append(
                    {
                        "path": f"$.{field_name}",
                        "invalid_id": evidence_id,
                        "reason": "pcim_section_name",
                    }
                )
            continue
        if evidence_id not in cleaned:
            cleaned.append(evidence_id)
    if removed:
        schema_warnings.append(
            f"{field_name} contained section-name references instead of evidence IDs and they were moved to diagnostics only: {removed}"
        )
    return cleaned


def _drop_unresolved_evidence_ids(
    evidence_ids: List[str],
    unresolved_ids: List[str],
    *,
    field_name: str,
    schema_warnings: List[str],
    removed_records: Optional[List[Dict[str, str]]] = None,
) -> List[str]:
    unresolved = {str(item or "").strip() for item in unresolved_ids if str(item or "").strip()}
    if not unresolved:
        return evidence_ids
    cleaned: List[str] = []
    removed: List[str] = []
    for evidence_id in evidence_ids:
        if evidence_id in unresolved:
            removed.append(evidence_id)
            if removed_records is not None:
                removed_records.append(
                    {
                        "path": f"$.{field_name}",
                        "invalid_id": evidence_id,
                        "reason": "unknown_evidence_id",
                    }
                )
            continue
        if evidence_id not in cleaned:
            cleaned.append(evidence_id)
    if removed:
        schema_warnings.append(
            f"{field_name} contained unknown evidence IDs and they were moved to diagnostics only: {removed}"
        )
    return cleaned


def _sanitize_evidence_ids_for_save(
    value: Any,
    *,
    evidence_lookup: Dict[str, Dict[str, Any]],
    diagnostics: Dict[str, Any],
    path: str = "$",
) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key == "evidence_ids":
                if not isinstance(item, list):
                    sanitized[key] = []
                    diagnostics.setdefault("removed_invalid_evidence_ids", []).append(
                        {
                            "path": child_path,
                            "invalid_id": str(item),
                            "reason": "evidence_ids field was not a list",
                        }
                    )
                    continue
                cleaned: List[str] = []
                for evidence_id in item:
                    evidence_text = str(evidence_id or "").strip()
                    if not evidence_text:
                        continue
                    if evidence_text in PCIM_SECTION_NAME_DENYLIST:
                        diagnostics.setdefault("removed_invalid_evidence_ids", []).append(
                            {
                                "path": child_path,
                                "invalid_id": evidence_text,
                                "reason": "pcim_section_name",
                            }
                        )
                        continue
                    if evidence_text not in evidence_lookup:
                        diagnostics.setdefault("removed_invalid_evidence_ids", []).append(
                            {
                                "path": child_path,
                                "invalid_id": evidence_text,
                                "reason": "unknown_evidence_id",
                            }
                        )
                        continue
                    if evidence_text not in cleaned:
                        cleaned.append(evidence_text)
                sanitized[key] = cleaned
                continue
            sanitized[key] = _sanitize_evidence_ids_for_save(
                item,
                evidence_lookup=evidence_lookup,
                diagnostics=diagnostics,
                path=child_path,
            )
        return sanitized
    if isinstance(value, list):
        return [
            _sanitize_evidence_ids_for_save(
                item,
                evidence_lookup=evidence_lookup,
                diagnostics=diagnostics,
                path=f"{path}[{idx}]",
            )
            for idx, item in enumerate(value)
        ]
    return value


def assert_no_invalid_evidence_ids(
    value: Any,
    *,
    evidence_lookup: Dict[str, Dict[str, Any]],
    path: str = "$",
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key == "evidence_ids":
                if not isinstance(item, list):
                    raise ValueError(f"invalid evidence_ids field at {child_path}: expected list")
                for evidence_id in item:
                    evidence_text = str(evidence_id or "").strip()
                    if evidence_text in PCIM_SECTION_NAME_DENYLIST:
                        raise ValueError(
                            f"invalid evidence_id at {child_path}: {evidence_text} "
                            "(reason=pcim_section_name)"
                        )
                    if evidence_text and evidence_text not in evidence_lookup:
                        raise ValueError(
                            f"invalid evidence_id at {child_path}: {evidence_text} "
                            "(reason=unknown_evidence_id)"
                        )
                continue
            assert_no_invalid_evidence_ids(item, evidence_lookup=evidence_lookup, path=child_path)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            assert_no_invalid_evidence_ids(item, evidence_lookup=evidence_lookup, path=f"{path}[{idx}]")


def _has_governance_routing_failure(payload: Dict[str, Any]) -> bool:
    if str(payload.get("evidence_grounding_status") or "").strip().lower() != "fail":
        return False
    for warning in payload.get("evidence_grounding_warnings") or []:
        if not isinstance(warning, dict):
            continue
        issue = str(warning.get("issue") or "").lower()
        if "market-risk evidence should not support governance/incentive claim" in issue:
            return True
    return False


def _evidence_metadata_text(entry: Dict[str, Any]) -> str:
    parts = [
        entry.get("category"),
        entry.get("canonical_risk"),
        entry.get("canonical_theme"),
        entry.get("signal_type"),
        entry.get("section_path"),
        entry.get("value"),
        entry.get("source_item_id"),
        entry.get("source_artifact"),
    ]
    return " ".join(str(part or "").replace("_", " ").lower() for part in parts)


def _classify_munger_claim(path: str, text: str) -> str:
    haystack = f"{path} {text}".replace("_", " ").lower()
    if (
        path.endswith("governance_sanity_assessment")
        or path.endswith("incentive_alignment_assessment")
        or any(
            token in haystack
            for token in (
                "governance",
                "incentive",
                "compensation",
                "board",
                "committee",
                "promoter",
                "ownership",
                "related party",
                "stewardship",
                "alignment",
            )
        )
    ):
        return "governance_incentive"
    if any(token in haystack for token in ("fx", "foreign exchange", "interest rate", "currency", "market risk")):
        return "market_risk"
    if any(token in haystack for token in ("receivable", "inventory", "payable", "working capital", "cash conversion")):
        return "working_capital"
    if any(token in haystack for token in ("qip", "equity issuance", "preferential", "capex", "capital allocation", "related party lending")):
        return "capital_allocation"
    return "unknown"


def _evidence_matches_claim_type(
    evidence_id: str,
    claim_type: str,
    evidence_lookup: Dict[str, Dict[str, Any]],
) -> bool:
    if claim_type == "unknown":
        return True
    entry = evidence_lookup.get(evidence_id)
    if not entry:
        return False
    metadata = _evidence_metadata_text(entry)
    return any(token in metadata for token in CLAIM_TYPE_ALLOWED_EVIDENCE.get(claim_type, []))


def _candidate_evidence_ids_for_claim_type(
    claim_type: str,
    *,
    preferred_ids: List[str],
    available_ids: List[str],
    evidence_lookup: Dict[str, Dict[str, Any]],
) -> List[str]:
    candidates = _unique_preserve_order(preferred_ids + available_ids)
    return [
        evidence_id
        for evidence_id in candidates
        if _evidence_matches_claim_type(evidence_id, claim_type, evidence_lookup)
    ]


def _is_governance_claim_type(claim_type: str) -> bool:
    return claim_type == "governance_incentive"


def _repair_munger_claim_evidence(
    *,
    path: str,
    text: str,
    evidence_ids: List[str],
    evidence_lookup: Dict[str, Dict[str, Any]],
    available_ids: List[str],
    preferred_ids: List[str],
    diagnostics: Dict[str, Any],
) -> Tuple[str, List[str]]:
    claim_type = _classify_munger_claim(path, text)
    if claim_type == "unknown":
        return text, evidence_ids
    allowed_ids = [
        evidence_id
        for evidence_id in evidence_ids
        if _evidence_matches_claim_type(evidence_id, claim_type, evidence_lookup)
    ]
    removed_ids = [evidence_id for evidence_id in evidence_ids if evidence_id not in allowed_ids]
    if removed_ids:
        diagnostics.setdefault("removed_misrouted_evidence", []).extend(
            {
                "claim_path": path,
                "claim_type": claim_type,
                "evidence_id": evidence_id,
            }
            for evidence_id in removed_ids
        )
        if _is_governance_claim_type(claim_type) and any(
            token in str(text or "").lower()
            for token in ("market-risk", "market risk", "fx risk", "foreign exchange", "interest-rate", "interest rate")
        ):
            diagnostics.setdefault("claims_converted_to_limitations", []).append(
                {
                    "claim_path": path,
                    "original_claim": text,
                    "replacement_claim": MUNGER_GOVERNANCE_LIMITATION,
                    "evidence_limit": "Market-risk evidence cannot support governance or incentive conclusions.",
                }
            )
            return MUNGER_GOVERNANCE_LIMITATION, []
    if allowed_ids:
        return text, _unique_preserve_order(allowed_ids)

    replacements = _candidate_evidence_ids_for_claim_type(
        claim_type,
        preferred_ids=preferred_ids,
        available_ids=available_ids,
        evidence_lookup=evidence_lookup,
    )
    if replacements:
        replacement = replacements[:1]
        diagnostics.setdefault("replaced_evidence", []).append(
            {
                "claim_path": path,
                "claim_type": claim_type,
                "replacement_ids": replacement,
            }
        )
        return text, replacement

    if _is_governance_claim_type(claim_type):
        diagnostics.setdefault("claims_converted_to_limitations", []).append(
            {
                "claim_path": path,
                "original_claim": text,
                "replacement_claim": MUNGER_GOVERNANCE_LIMITATION,
                "evidence_limit": "No governance-specific evidence available.",
            }
        )
        return MUNGER_GOVERNANCE_LIMITATION, []

    diagnostics.setdefault("unresolved_claims", []).append(
        {
            "claim_path": path,
            "claim_type": claim_type,
            "claim": text,
            "evidence_limit": "No claim-specific evidence available.",
        }
    )
    return text, []


def _repair_munger_evidence_routing(
    *,
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
    diagnostics: Dict[str, Any],
) -> Tuple[Dict[str, str], List[str], List[str], List[str], List[List[str]], List[List[str]], List[List[str]], Dict[str, List[str]]]:
    preferred_ids = _unique_preserve_order(
        [item for values in assessment_evidence_map.values() for item in values]
        + [item for group in key_finding_map for item in group]
        + [item for group in red_flag_map for item in group]
        + [item for group in uncertainty_map for item in group]
    )

    repaired_assessment = dict(assessment)
    repaired_assessment_map: Dict[str, List[str]] = {}
    for key, text in assessment.items():
        path = f"assessment.{key}"
        repaired_text, repaired_ids = _repair_munger_claim_evidence(
            path=path,
            text=text,
            evidence_ids=assessment_evidence_map.get(key, []),
            evidence_lookup=evidence_lookup,
            available_ids=available_ids,
            preferred_ids=preferred_ids,
            diagnostics=diagnostics,
        )
        repaired_assessment[key] = repaired_text
        repaired_assessment_map[key] = repaired_ids
        if repaired_text != text and repaired_text not in open_uncertainties:
            open_uncertainties.append(repaired_text)
            uncertainty_map.append([])

    def repair_list(field: str, texts: List[str], maps: List[List[str]]) -> Tuple[List[str], List[List[str]]]:
        repaired_texts: List[str] = []
        repaired_maps: List[List[str]] = []
        for idx, text in enumerate(texts):
            repaired_text, repaired_ids = _repair_munger_claim_evidence(
                path=f"{field}.{idx}",
                text=text,
                evidence_ids=maps[idx] if idx < len(maps) else [],
                evidence_lookup=evidence_lookup,
                available_ids=available_ids,
                preferred_ids=preferred_ids,
                diagnostics=diagnostics,
            )
            if repaired_text == MUNGER_GOVERNANCE_LIMITATION and field != "open_uncertainties":
                if repaired_text not in open_uncertainties:
                    open_uncertainties.append(repaired_text)
                    uncertainty_map.append(repaired_ids)
                continue
            repaired_texts.append(repaired_text)
            repaired_maps.append(repaired_ids)
        return repaired_texts, repaired_maps

    key_findings, key_finding_map = repair_list("key_findings", key_findings, key_finding_map)
    red_flags, red_flag_map = repair_list("red_flags", red_flags, red_flag_map)
    open_uncertainties, uncertainty_map = repair_list("open_uncertainties", open_uncertainties, uncertainty_map)

    for key in ("removed_misrouted_evidence", "replaced_evidence", "claims_converted_to_limitations", "unresolved_claims"):
        diagnostics[key] = _unique_preserve_order(diagnostics.get(key, []) or [])

    return (
        repaired_assessment,
        key_findings,
        red_flags,
        open_uncertainties,
        key_finding_map,
        red_flag_map,
        uncertainty_map,
        repaired_assessment_map,
    )


def assert_no_munger_routing_violations(
    payload: Dict[str, Any],
    *,
    evidence_lookup: Dict[str, Dict[str, Any]],
) -> None:
    assert_no_invalid_evidence_ids(payload, evidence_lookup=evidence_lookup)
    for forbidden_key in ("source_chunk", "raw_text", "full_text", "prompt", "input_pack"):
        if f'"{forbidden_key}"' in json.dumps(payload, ensure_ascii=False):
            raise ValueError(f"Munger output contains forbidden raw/internal field: {forbidden_key}")
    warnings = payload.get("evidence_grounding_warnings") or []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        if "market-risk evidence should not support governance/incentive claim" in str(warning.get("issue") or ""):
            raise ValueError("Munger routing violation remains: governance/incentive claim cites market-risk evidence.")


def _normalize_optional_evidence_ids(value: Any, field: str) -> List[str]:
    if value is None:
        return []
    return _normalize_string_list(value, f"{field}.evidence_ids")


def _normalize_brief_string_list(value: Any, field: str) -> List[str]:
    if value is None:
        return []
    return _normalize_string_list(value, field)


def _normalize_financial_metric_refs(value: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    if value is None:
        return [], []
    if not isinstance(value, list):
        raise ValueError("financial_metrics_used must be a list")
    normalized: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for item in value:
        if isinstance(item, str):
            metric_text = item.strip()
            if not metric_text:
                raise ValueError("financial_metrics_used must contain non-empty strings or objects")
            normalized.append(
                {
                    "metric_id": "",
                    "metric": metric_text,
                    "period": _extract_metric_period(metric_text) or None,
                    "used_for": "string fallback from LLM output",
                }
            )
            warnings.append(f"financial_metrics_used used string fallback: {metric_text}")
            continue
        if not isinstance(item, dict):
            raise ValueError("financial_metrics_used items must be strings or objects")
        metric_id = str(item.get("metric_id") or "").strip()
        metric = str(item.get("metric") or "").strip()
        period = str(item.get("period") or "").strip().lower() or None
        used_for = str(item.get("used_for") or "").strip() or "unspecified"
        if not metric_id and not metric:
            raise ValueError("financial_metrics_used objects must include metric_id or metric")
        normalized.append(
            {
                "metric_id": metric_id,
                "metric": metric,
                "period": period,
                "used_for": used_for,
            }
        )
        if not metric_id:
            warnings.append(f"financial_metrics_used missing metric_id for metric: {metric or 'unknown'}")
    return normalized, warnings


def _build_financial_metric_lookup(metric_registry: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    by_metric_id: Dict[str, Dict[str, Any]] = {}
    by_alias: Dict[str, List[Dict[str, Any]]] = {}
    for entry in metric_registry:
        metric_id = str(entry.get("metric_id") or "").strip()
        if metric_id:
            by_metric_id[metric_id] = entry
        aliases = list(entry.get("aliases") or [])
        aliases.append(str(entry.get("canonical_metric") or ""))
        aliases.append(str(entry.get("display_name") or ""))
        period = str(entry.get("period") or "").strip().lower()
        for alias in aliases:
            normalized_alias = _normalize_metric_label(alias)
            if not normalized_alias:
                continue
            keys = [normalized_alias]
            if period:
                keys.append(f"{normalized_alias}|{period}")
            for key in keys:
                by_alias.setdefault(key, []).append(entry)
    return by_metric_id, by_alias


def _canonicalize_financial_metric_ref(
    item: Dict[str, Any],
    *,
    by_metric_id: Dict[str, Dict[str, Any]],
    by_alias: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    metric_id = str(item.get("metric_id") or "").strip()
    if metric_id and metric_id in by_metric_id:
        entry = by_metric_id[metric_id]
        return {
            "metric_id": entry["metric_id"],
            "metric": entry["canonical_metric"],
            "period": entry.get("period"),
            "used_for": item.get("used_for") or "unspecified",
        }, None

    metric_text = str(item.get("metric") or metric_id or "").strip()
    if not metric_text:
        return None, "missing metric text"
    period = str(item.get("period") or _extract_metric_period(metric_text) or "").strip().lower()
    normalized_metric = _normalize_metric_label(metric_text)
    lookup_keys = [f"{normalized_metric}|{period}"] if period else []
    lookup_keys.append(normalized_metric)
    matches: List[Dict[str, Any]] = []
    for key in lookup_keys:
        matches.extend(by_alias.get(key, []))
    unique_matches = []
    seen_metric_ids: set[str] = set()
    for match in matches:
        match_metric_id = str(match.get("metric_id") or "")
        if match_metric_id and match_metric_id not in seen_metric_ids:
            seen_metric_ids.add(match_metric_id)
            unique_matches.append(match)
    if len(unique_matches) == 1:
        entry = unique_matches[0]
        return {
            "metric_id": entry["metric_id"],
            "metric": entry["canonical_metric"],
            "period": entry.get("period"),
            "used_for": item.get("used_for") or "unspecified",
        }, f"financial metric canonicalized via alias: {metric_text} -> {entry['metric_id']}"
    if len(unique_matches) > 1:
        if not period:
            periodless = [match for match in unique_matches if not str(match.get("period") or "").strip()]
            if len(periodless) == 1:
                entry = periodless[0]
                return {
                    "metric_id": entry["metric_id"],
                    "metric": entry["canonical_metric"],
                    "period": entry.get("period"),
                    "used_for": item.get("used_for") or "unspecified",
                }, f"financial metric canonicalized via alias: {metric_text} -> {entry['metric_id']}"
        same_canonical = {str(match.get("canonical_metric") or "") for match in unique_matches}
        if len(same_canonical) == 1:
            preferred = sorted(
                unique_matches,
                key=lambda match: (str(match.get("period") or "") == "", str(match.get("period") or "")),
                reverse=True,
            )[0]
            return {
                "metric_id": preferred["metric_id"],
                "metric": preferred["canonical_metric"],
                "period": preferred.get("period"),
                "used_for": item.get("used_for") or "unspecified",
            }, f"financial metric canonicalized via alias: {metric_text} -> {preferred['metric_id']}"
        return None, f"ambiguous financial metric reference: {metric_text}"
    return None, f"unknown financial metric reference: {metric_text}"


def _normalize_financial_assessment(value: Any) -> Dict[str, Any]:
    schema_warnings: List[str] = []
    if not isinstance(value, dict):
        raise ValueError("financial_assessment must be an object")
    financials_used = value.get("financials_used")
    if not isinstance(financials_used, bool):
        raise ValueError("financial_assessment.financials_used must be a boolean")
    basis_used = str(value.get("basis_used") or "").strip()
    if not basis_used:
        raise ValueError("financial_assessment.basis_used is required")
    return {
        "financials_used": financials_used,
        "basis_used": basis_used,
        "key_financial_strengths": _normalize_string_list(
            value.get("key_financial_strengths"),
            "financial_assessment.key_financial_strengths",
            schema_warnings,
            default_empty=True,
        ),
        "key_financial_concerns": _normalize_string_list(
            value.get("key_financial_concerns"),
            "financial_assessment.key_financial_concerns",
            schema_warnings,
            default_empty=True,
        ),
        "financial_red_flags": _normalize_string_list(
            value.get("financial_red_flags"),
            "financial_assessment.financial_red_flags",
            schema_warnings,
            default_empty=True,
        ),
        "missing_financial_data": _normalize_string_list(
            value.get("missing_financial_data"),
            "financial_assessment.missing_financial_data",
            schema_warnings,
            default_empty=True,
        ),
        "financial_interpretation_limits": _normalize_string_list(
            value.get("financial_interpretation_limits"),
            "financial_assessment.financial_interpretation_limits",
            schema_warnings,
            default_empty=True,
        ),
        "financial_warnings_carried_forward": _normalize_string_list(
            value.get("financial_warnings_carried_forward", []),
            "financial_assessment.financial_warnings_carried_forward",
            schema_warnings,
            default_empty=True,
        ),
        "schema_warnings": schema_warnings,
    }


def _contains_any(texts: List[str], needles: Tuple[str, ...]) -> bool:
    joined = " ".join(texts).lower()
    return any(needle in joined for needle in needles)


def _texts_for_financial_matching(*groups: Any) -> List[str]:
    texts: List[str] = []
    for group in groups:
        if isinstance(group, str):
            texts.append(group.strip())
        elif isinstance(group, list):
            for item in group:
                if isinstance(item, str) and item.strip():
                    texts.append(item.strip())
    return texts


def _financial_warning_group_matches(texts: List[str], label: str) -> bool:
    lowered = " ".join(texts).lower()
    definition = FINANCIAL_WARNING_GROUP_DEFINITIONS.get(label) or {}
    phrases = definition.get("equivalent_phrases") or FINANCIAL_WARNING_GROUPS.get(label, ())
    return any(phrase in lowered for phrase in phrases)


def _financial_context_metric_flags(context: Dict[str, Any]) -> Dict[str, bool]:
    metrics = {metric.lower() for metric in context.get("metrics_used", [])}
    return {
        "has_fcf": "fcf" in metrics,
        "has_capex": "capex" in metrics,
        "has_shares_outstanding": any(metric in metrics for metric in {"shares_outstanding", "share_count"}),
        "has_weighted_avg_shares": "weighted_avg_shares" in metrics,
        "has_diluted_shares": "diluted_shares" in metrics,
        "has_payable_days": "payable_days" in metrics,
        "has_cash_conversion_cycle": "cash_conversion_cycle" in metrics,
    }


def _canonical_required_financial_warning_groups(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    combined_texts = _texts_for_financial_matching(
        context.get("warnings", []),
        context.get("missing_data", []),
        context.get("interpretation_limits", []),
    )
    required: List[Dict[str, Any]] = []
    for label in (
        "fcf_missing",
        "capex_missing",
        "weighted_avg_shares_missing",
        "diluted_shares_missing",
        "share_count_missing",
        "payables_missing",
        "basis_unknown",
        "reconciliation_warning",
        "audit_warning",
    ):
        if _financial_warning_group_matches(combined_texts, label):
            required.append(dict(FINANCIAL_WARNING_GROUP_DEFINITIONS[label]))
    return required


def _append_unique_text(target: List[str], value: str) -> bool:
    text = str(value or "").strip()
    if not text or text in target:
        return False
    target.append(text)
    return True


def _apply_required_financial_warning_groups(
    *,
    required_groups: List[Dict[str, Any]],
    doctrine_id: str,
    financial_missing_data: List[str],
    financial_interpretation_limits: List[str],
    financial_warnings_carried_forward: List[str],
    financial_assessment: Dict[str, Any],
    schema_warnings: List[str],
) -> None:
    financial_assessment.setdefault("missing_financial_data", [])
    financial_assessment.setdefault("financial_interpretation_limits", [])
    financial_assessment.setdefault("financial_warnings_carried_forward", [])
    financial_assessment.setdefault("key_financial_concerns", [])

    carried_texts = _texts_for_financial_matching(
        financial_missing_data,
        financial_interpretation_limits,
        financial_warnings_carried_forward,
        financial_assessment.get("missing_financial_data", []),
        financial_assessment.get("financial_interpretation_limits", []),
        financial_assessment.get("financial_warnings_carried_forward", []),
        financial_assessment.get("key_financial_concerns", []),
        financial_assessment.get("financial_red_flags", []),
    )
    for group in required_groups:
        warning_id = str(group.get("warning_id") or "").strip()
        carry_text = str(group.get("required_carry_forward_text") or "").strip()
        if not warning_id:
            continue
        injected = False

        warning_items: List[str] = []
        missing_items: List[str] = []
        interpretation_items: List[str] = []
        concern_items: List[str] = []

        if warning_id == "fcf_missing":
            warning_items.append("Free cash flow is missing; FCF-based conclusions cannot be assessed.")
            interpretation_items.append(
                "Free cash flow is missing, so owner earnings, FCF margin, and FCF-supported dividend sustainability cannot be assessed."
            )
            missing_items.append("free cash flow missing")
            if doctrine_id == "graham":
                interpretation_items.append(
                    "Margin-of-safety judgment is limited because free cash flow is unavailable."
                )
            if doctrine_id == "buffett":
                interpretation_items.append(
                    "Owner earnings cannot be assessed because free cash flow/capex data is missing or incomplete."
                )
        elif warning_id == "capex_missing":
            warning_items.append(carry_text)
            interpretation_items.append(
                "Capex is missing or incomplete, so free cash flow and owner-earnings interpretation remain limited."
            )
            missing_items.append("capex missing")
            if doctrine_id == "buffett":
                interpretation_items.append(
                    "Owner earnings cannot be assessed because free cash flow/capex data is missing or incomplete."
                )
        elif warning_id in {"weighted_avg_shares_missing", "diluted_shares_missing", "share_count_missing"}:
            warning_items.append(carry_text)
            interpretation_items.append(carry_text)
            missing_items.append(str(group.get("canonical_warning") or warning_id).strip())
            concern_items.append(carry_text)
        elif warning_id == "payables_missing":
            warning_items.append(carry_text)
            interpretation_items.append(carry_text)
            missing_items.append("payables missing")
            concern_items.append(carry_text)
        elif warning_id == "basis_unknown":
            warning_items.append(carry_text)
            interpretation_items.append(carry_text)
            concern_items.append(carry_text)
        else:
            if carry_text:
                warning_items.append(carry_text)
                interpretation_items.append(carry_text)
                concern_items.append(carry_text)

        for item in warning_items:
            if item and not _financial_warning_group_matches(carried_texts, warning_id):
                injected = _append_unique_text(financial_warnings_carried_forward, item) or injected
                injected = _append_unique_text(financial_assessment["financial_warnings_carried_forward"], item) or injected
                carried_texts.append(item)
        for item in missing_items:
            if item and not _financial_warning_group_matches(carried_texts, warning_id):
                injected = _append_unique_text(financial_missing_data, item) or injected
                injected = _append_unique_text(financial_assessment["missing_financial_data"], item) or injected
                carried_texts.append(item)
        for item in interpretation_items:
            if item:
                injected = _append_unique_text(financial_interpretation_limits, item) or injected
                injected = _append_unique_text(financial_assessment["financial_interpretation_limits"], item) or injected
                carried_texts.append(item)
        for item in concern_items:
            if item:
                injected = _append_unique_text(financial_assessment["key_financial_concerns"], item) or injected
                carried_texts.append(item)

        if injected:
            _append_unique_text(
                schema_warnings,
                f"financial warning auto-carried from PCIM: {warning_id}",
            )

    if doctrine_id == "buffett" and any(
        group.get("warning_id") in {"fcf_missing", "capex_missing"} for group in required_groups
    ):
        owner_earnings_limit = (
            "Owner earnings cannot be assessed because free cash flow/capex data is missing or incomplete."
        )
        injected = False
        injected = _append_unique_text(financial_interpretation_limits, owner_earnings_limit) or injected
        injected = _append_unique_text(
            financial_assessment["financial_interpretation_limits"],
            owner_earnings_limit,
        ) or injected
        if injected:
            _append_unique_text(
                schema_warnings,
                "financial warning auto-carried from PCIM: buffett_owner_earnings_limit",
            )


def _apply_required_financial_warning_carry_forward(
    payload: Dict[str, Any],
    required_warning_groups: List[Dict[str, Any]],
    analyst: str,
    schema_warnings: List[str],
) -> None:
    payload.setdefault("financial_missing_data", [])
    payload.setdefault("financial_interpretation_limits", [])
    payload.setdefault("financial_warnings_carried_forward", [])
    if not isinstance(payload.get("financial_assessment"), dict):
        payload["financial_assessment"] = {}
    payload["financial_assessment"].setdefault("missing_financial_data", [])
    payload["financial_assessment"].setdefault("financial_interpretation_limits", [])
    payload["financial_assessment"].setdefault("financial_warnings_carried_forward", [])
    payload["financial_assessment"].setdefault("key_financial_concerns", [])
    payload["financial_assessment"].setdefault("financial_red_flags", [])
    _apply_required_financial_warning_groups(
        required_groups=required_warning_groups,
        doctrine_id=analyst,
        financial_missing_data=payload["financial_missing_data"],
        financial_interpretation_limits=payload["financial_interpretation_limits"],
        financial_warnings_carried_forward=payload["financial_warnings_carried_forward"],
        financial_assessment=payload["financial_assessment"],
        schema_warnings=schema_warnings,
    )


def _raise_if_financial_warning_contradicted(
    *,
    required_groups: List[Dict[str, Any]],
    all_financial_text: List[str],
    financial_metrics_used: List[Dict[str, Any]],
) -> None:
    joined = " ".join(all_financial_text).lower()
    metric_ids = {str(item.get("metric_id") or "").strip().lower() for item in financial_metrics_used}
    required_ids = {str(group.get("warning_id") or "").strip() for group in required_groups}

    def has_any_phrase(*phrases: str) -> bool:
        return any(phrase in joined for phrase in phrases)

    if "fcf_missing" in required_ids:
        if "fcf" in metric_ids:
            raise ValueError("analyst claims FCF exists when required PCIM warning says free cash flow is missing")
        if has_any_phrase(
            "strong fcf",
            "positive fcf",
            "free cash flow supports dividends",
            "fcf supports dividends",
            "free cash flow yield",
            "fcf margin is",
            "healthy fcf margin",
            "positive free cash flow",
            "strong free cash flow",
        ):
            raise ValueError("analyst contradicts required PCIM warning: free cash flow missing")
        if has_any_phrase(
            "owner earnings remain strong",
            "owner earnings are strong",
            "owner earnings are calculable",
            "owner earnings can be assessed",
            "owner earnings are assessable",
        ):
            raise ValueError("analyst contradicts required PCIM warning: owner earnings cannot be assessed")
    if "capex_missing" in required_ids and has_any_phrase(
        "owner earnings remain strong",
        "owner earnings are strong",
        "owner earnings are calculable",
        "owner earnings can be assessed",
        "owner earnings are assessable",
    ):
        raise ValueError("analyst contradicts required PCIM warning: capex missing prevents owner-earnings assessment")
    if "payables_missing" in required_ids and has_any_phrase(
        "cash conversion cycle is healthy",
        "ccc is healthy",
        "payable days are healthy",
        "payable days support",
    ):
        raise ValueError("analyst contradicts required PCIM warning: payables missing")
    if "basis_unknown" in required_ids and has_any_phrase(
        "basis is clear",
        "consolidated basis is clear",
        "standalone basis is clear",
        "comparability is clean",
    ):
        raise ValueError("analyst contradicts required PCIM warning: basis unknown")


def _validate_llm_panel_output(
    payload_text: str,
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    pcim_version: Any,
    pcim: Dict[str, Any],
    consumed_sections: List[str],
    allowed_evidence_ids: List[str],
) -> Dict[str, Any]:
    try:
        parsed = json.loads(payload_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    if '"source_chunk"' in json.dumps(parsed, ensure_ascii=False):
        raise ValueError("source_chunk is not allowed in analyst output")
    schema_warnings: List[str] = []

    assessment = parsed.get("assessment")
    if not isinstance(assessment, dict):
        raise ValueError("assessment must be an object")

    normalized_assessment = {}
    for key in _required_assessment_keys(doctrine):
        value = assessment.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"assessment.{key} is required")
        normalized_assessment[key] = value.strip()

    rating = _normalize_rating_value(parsed.get("rating"), schema_warnings)

    key_findings, finding_evidence, key_finding_map = _normalize_findings_with_map(parsed.get("key_findings"), "key_findings")
    red_flags, red_flag_evidence, red_flag_map = _normalize_findings_with_map(parsed.get("red_flags"), "red_flags")
    open_uncertainties, uncertainty_evidence, uncertainty_map = _normalize_findings_with_map(
        parsed.get("open_uncertainties"), "open_uncertainties"
    )
    _normalize_optional_text_list_fields(parsed, schema_warnings)
    financial_metrics_used_raw, metric_normalization_warnings = _normalize_financial_metric_refs(
        parsed.get("financial_metrics_used")
    )
    financial_red_flags = _normalize_string_list(
        parsed.get("financial_red_flags"),
        "financial_red_flags",
        schema_warnings,
        default_empty=True,
    )
    financial_positive_signals = _normalize_string_list(
        parsed.get("financial_positive_signals"),
        "financial_positive_signals",
        schema_warnings,
        default_empty=True,
    )
    financial_missing_data = _normalize_string_list(
        parsed.get("financial_missing_data"),
        "financial_missing_data",
        schema_warnings,
        default_empty=True,
    )
    financial_interpretation_limits = _normalize_string_list(
        parsed.get("financial_interpretation_limits"),
        "financial_interpretation_limits",
        schema_warnings,
        default_empty=True,
    )
    financial_warnings_carried_forward = _normalize_string_list(
        parsed.get("financial_warnings_carried_forward", []),
        "financial_warnings_carried_forward",
        schema_warnings,
        default_empty=True,
    )
    financial_assessment = _normalize_financial_assessment(parsed.get("financial_assessment"))
    schema_warnings.extend(financial_assessment.pop("schema_warnings", []))
    reasoning_limits = _normalize_string_list(
        parsed.get("reasoning_limits"),
        "reasoning_limits",
        schema_warnings,
        default_empty=True,
    )
    if parsed.get("user_facing_brief") is None:
        raise ValueError("user_facing_brief is required")
    normalized_brief = normalize_user_facing_brief_shape(parsed.get("user_facing_brief"))
    sanitized_brief = sanitize_user_facing_brief(normalized_brief)
    normalized_sanitized_brief = normalize_user_facing_brief_shape(sanitized_brief)
    normalized_length_brief = normalize_user_facing_brief_lengths(normalized_sanitized_brief)
    user_facing_brief = validate_user_facing_brief(doctrine["doctrine_id"], normalized_length_brief)

    supporting_pcim_sections = _normalize_string_list(
        parsed.get("supporting_pcim_sections"),
        "supporting_pcim_sections",
        schema_warnings,
    )
    invalid_sections = [section for section in supporting_pcim_sections if section not in consumed_sections]
    if invalid_sections:
        invalid_unique = sorted(set(invalid_sections))
        supporting_pcim_sections = [section for section in supporting_pcim_sections if section in consumed_sections]
        reasoning_limits.append(
            "LLM referenced unsupported PCIM sections and they were removed during validation: "
            f"{invalid_unique}"
        )
        if not supporting_pcim_sections:
            raise ValueError(
                "Invalid supporting_pcim_sections returned: "
                f"{invalid_unique}. Allowed sections: {consumed_sections}. Analyst: {doctrine['doctrine_id']}"
            )

    selected_pcim = _selected_pcim_view(pcim, consumed_sections)
    derived_financial_context = _derive_financial_context(selected_pcim, consumed_sections, [])
    metric_registry = derived_financial_context["metric_registry"]
    allowed_financial_metrics = set(_registry_metric_names(metric_registry))
    by_metric_id, by_alias = _build_financial_metric_lookup(metric_registry)
    financial_metrics_used: List[Dict[str, Any]] = []
    invalid_financial_metrics: List[str] = []
    canonicalization_warnings = list(metric_normalization_warnings)
    for metric_item in financial_metrics_used_raw:
        canonical_metric_item, warning = _canonicalize_financial_metric_ref(
            metric_item,
            by_metric_id=by_metric_id,
            by_alias=by_alias,
        )
        if canonical_metric_item is None:
            invalid_financial_metrics.append(warning or str(metric_item))
            continue
        financial_metrics_used.append(canonical_metric_item)
        if warning:
            canonicalization_warnings.append(warning)
    if canonicalization_warnings:
        reasoning_limits.extend(_unique_preserve_order(canonicalization_warnings))

    financial_sections_consumed = _financial_sections_for_doctrine(consumed_sections)
    if (
        financial_metrics_used
        or financial_red_flags
        or financial_positive_signals
        or financial_missing_data
        or financial_interpretation_limits
    ) and not financial_sections_consumed:
        raise ValueError("financial claims require supporting financial PCIM sections")

    if financial_assessment["financials_used"] and not financial_sections_consumed:
        raise ValueError("financial_assessment.financials_used cannot be true without supporting financial PCIM sections")

    if financial_assessment["financials_used"] and not (
        financial_metrics_used
        or financial_assessment["key_financial_strengths"]
        or financial_assessment["key_financial_concerns"]
        or financial_assessment["financial_red_flags"]
    ):
        raise ValueError("financial_assessment indicates financials were used but no financial reasoning was provided")

    if financial_assessment["basis_used"].lower() not in {"consolidated", "standalone", "mixed", "unknown"}:
        raise ValueError("financial_assessment.basis_used must be consolidated|standalone|mixed|unknown")

    required_limitations = _must_carry_financial_limitations(derived_financial_context)
    carry_forward_payload = {
        "financial_missing_data": financial_missing_data,
        "financial_interpretation_limits": financial_interpretation_limits,
        "financial_warnings_carried_forward": financial_warnings_carried_forward,
        "financial_assessment": financial_assessment,
    }
    _apply_required_financial_warning_carry_forward(
        payload=carry_forward_payload,
        required_warning_groups=required_limitations,
        analyst=doctrine["doctrine_id"],
        schema_warnings=schema_warnings,
    )
    financial_missing_data = carry_forward_payload["financial_missing_data"]
    financial_interpretation_limits = carry_forward_payload["financial_interpretation_limits"]
    financial_warnings_carried_forward = carry_forward_payload["financial_warnings_carried_forward"]
    financial_assessment = carry_forward_payload["financial_assessment"]
    carried_financial_items = (
        financial_missing_data
        + financial_interpretation_limits
        + financial_warnings_carried_forward
        + financial_assessment["missing_financial_data"]
        + financial_assessment["financial_interpretation_limits"]
        + financial_assessment["financial_warnings_carried_forward"]
        + financial_assessment["key_financial_concerns"]
        + financial_assessment["financial_red_flags"]
    )
    context_metric_flags = _financial_context_metric_flags(derived_financial_context)
    imprecise_financial_warning_messages: List[str] = []
    for group in required_limitations:
        label = str(group.get("warning_id") or "").strip()
        if label == "fcf_missing" and not _financial_warning_group_matches(carried_financial_items, label):
            raise ValueError("major financial warning from PCIM was not carried forward: free cash flow missing")
        if label == "capex_missing" and not _financial_warning_group_matches(carried_financial_items, label):
            raise ValueError("major financial warning from PCIM was not carried forward: capex missing")
        if label in {"share_count_missing", "weighted_avg_shares_missing", "diluted_shares_missing"}:
            if not _financial_warning_group_matches(carried_financial_items, label):
                raise ValueError("major financial warning from PCIM was not carried forward: share count missing")
            if context_metric_flags["has_shares_outstanding"] and any(
                "share count missing" in item.lower()
                for item in _texts_for_financial_matching(
                    derived_financial_context.get("warnings", []),
                    derived_financial_context.get("missing_data", []),
                    derived_financial_context.get("interpretation_limits", []),
                )
            ):
                imprecise_financial_warning_messages.append(
                    "PCIM warning wording was imprecise: shares_outstanding exists, so per-share limitation wording was accepted instead of generic share-count absence."
                )
        if label == "payables_missing" and not _financial_warning_group_matches(carried_financial_items, label):
            raise ValueError("major financial warning from PCIM was not carried forward: payables missing")
        if label == "basis_unknown" and not _financial_warning_group_matches(carried_financial_items, label):
            raise ValueError("major financial warning from PCIM was not carried forward: basis unknown")
        if label == "reconciliation_warning" and not _financial_warning_group_matches(carried_financial_items, label):
            raise ValueError("major financial warning from PCIM was not carried forward: reconciliation warning")
        if label == "audit_warning" and not _financial_warning_group_matches(carried_financial_items, label):
            raise ValueError("major financial warning from PCIM was not carried forward: audit warning")

    all_financial_text = (
        [f"{item['metric']} {item.get('period') or ''}".strip() for item in financial_metrics_used]
        + financial_red_flags
        + financial_positive_signals
        + financial_missing_data
        + financial_interpretation_limits
        + financial_warnings_carried_forward
        + financial_assessment["key_financial_strengths"]
        + financial_assessment["key_financial_concerns"]
        + financial_assessment["financial_red_flags"]
        + financial_assessment["missing_financial_data"]
        + financial_assessment["financial_interpretation_limits"]
        + financial_assessment["financial_warnings_carried_forward"]
        + list(normalized_assessment.values())
        + key_findings
        + red_flags
        + open_uncertainties
    )
    _raise_if_financial_warning_contradicted(
        required_groups=required_limitations,
        all_financial_text=carried_financial_items + all_financial_text,
        financial_metrics_used=financial_metrics_used,
    )
    if "fcf" not in {metric.lower() for metric in allowed_financial_metrics} and _contains_any(
        carried_financial_items + all_financial_text,
        ("owner earnings", "free cash flow", "fcf"),
    ):
        missing_context_text = " ".join(
            financial_missing_data
            + financial_interpretation_limits
            + financial_assessment["missing_financial_data"]
            + financial_assessment["financial_interpretation_limits"]
        ).lower()
        if not any(token in missing_context_text for token in ("free cash flow", "fcf", "owner earnings")):
            raise ValueError("analyst claims FCF or owner earnings without supplied FCF evidence")
    if invalid_financial_metrics:
        raise ValueError(
            "financial_metrics_used contains metrics not present in selected PCIM: "
            f"{sorted(set(invalid_financial_metrics))}"
        )
    forbidden_matches = find_forbidden_recommendation_language(" ".join(all_financial_text))
    if forbidden_matches:
        raise ValueError(
            "analyst output contains forbidden recommendation or valuation language: "
            + ", ".join(match["matched_text"] for match in forbidden_matches)
        )

    supplied_evidence_ids = _normalize_string_list(parsed.get("evidence_ids"), "evidence_ids", schema_warnings)
    removed_invalid_evidence_records: List[Dict[str, str]] = []
    supplied_evidence_ids = _strip_section_name_evidence_ids(
        supplied_evidence_ids,
        field_name="evidence_ids",
        schema_warnings=schema_warnings,
        removed_records=removed_invalid_evidence_records,
    )
    multi_year = pcim.get("multi_year_inputs") or {}
    historical_context_used = _normalize_optional_bool(
        parsed.get("historical_context_used"),
        "historical_context_used",
        default=("multi_year_inputs" in consumed_sections and not _section_empty(multi_year)),
    )
    years_considered = _normalize_string_list(
        parsed.get("years_considered"),
        "years_considered",
        schema_warnings,
        default_empty=True,
    ) if parsed.get("years_considered") is not None else []
    if historical_context_used and not years_considered:
        years_considered = list(multi_year.get("years_covered", []) or pcim.get("available_years", []))

    evidence_lookup = build_evidence_lookup(pcim)
    allowed_set = list(allowed_evidence_ids)

    normalized_key_finding_map: List[List[str]] = []
    key_finding_summaries: List[Dict[str, Any]] = []
    for evidence_ids in key_finding_map:
        normalized_ids, summary = normalize_evidence_ids_with_summary(
            evidence_ids,
            evidence_lookup,
            allowed_evidence_ids=allowed_set,
        )
        normalized_ids = _strip_section_name_evidence_ids(
            normalized_ids,
            field_name="key_findings.evidence_ids",
            schema_warnings=schema_warnings,
            removed_records=removed_invalid_evidence_records,
        )
        normalized_ids = _drop_unresolved_evidence_ids(
            normalized_ids,
            summary.get("unresolved_ids", []) or [],
            field_name="key_findings.evidence_ids",
            schema_warnings=schema_warnings,
            removed_records=removed_invalid_evidence_records,
        )
        normalized_key_finding_map.append(normalized_ids)
        key_finding_summaries.append(summary)

    normalized_red_flag_map: List[List[str]] = []
    red_flag_summaries: List[Dict[str, Any]] = []
    for evidence_ids in red_flag_map:
        normalized_ids, summary = normalize_evidence_ids_with_summary(
            evidence_ids,
            evidence_lookup,
            allowed_evidence_ids=allowed_set,
        )
        normalized_ids = _strip_section_name_evidence_ids(
            normalized_ids,
            field_name="red_flags.evidence_ids",
            schema_warnings=schema_warnings,
            removed_records=removed_invalid_evidence_records,
        )
        normalized_ids = _drop_unresolved_evidence_ids(
            normalized_ids,
            summary.get("unresolved_ids", []) or [],
            field_name="red_flags.evidence_ids",
            schema_warnings=schema_warnings,
            removed_records=removed_invalid_evidence_records,
        )
        normalized_red_flag_map.append(normalized_ids)
        red_flag_summaries.append(summary)

    normalized_uncertainty_map: List[List[str]] = []
    uncertainty_summaries: List[Dict[str, Any]] = []
    for evidence_ids in uncertainty_map:
        normalized_ids, summary = normalize_evidence_ids_with_summary(
            evidence_ids,
            evidence_lookup,
            allowed_evidence_ids=allowed_set,
        )
        normalized_ids = _strip_section_name_evidence_ids(
            normalized_ids,
            field_name="open_uncertainties.evidence_ids",
            schema_warnings=schema_warnings,
            removed_records=removed_invalid_evidence_records,
        )
        normalized_ids = _drop_unresolved_evidence_ids(
            normalized_ids,
            summary.get("unresolved_ids", []) or [],
            field_name="open_uncertainties.evidence_ids",
            schema_warnings=schema_warnings,
            removed_records=removed_invalid_evidence_records,
        )
        normalized_uncertainty_map.append(normalized_ids)
        uncertainty_summaries.append(summary)

    supplied_evidence_ids, top_level_summary = normalize_evidence_ids_with_summary(
        supplied_evidence_ids,
        evidence_lookup,
        allowed_evidence_ids=allowed_set,
    )
    supplied_evidence_ids = _strip_section_name_evidence_ids(
        supplied_evidence_ids,
        field_name="evidence_ids",
        schema_warnings=schema_warnings,
        removed_records=removed_invalid_evidence_records,
    )
    supplied_evidence_ids = _drop_unresolved_evidence_ids(
        supplied_evidence_ids,
        top_level_summary.get("unresolved_ids", []) or [],
        field_name="evidence_ids",
        schema_warnings=schema_warnings,
        removed_records=removed_invalid_evidence_records,
    )
    merged_evidence_ids, merged_summary = normalize_evidence_ids_with_summary(
        supplied_evidence_ids
        + [item for group in normalized_key_finding_map for item in group]
        + [item for group in normalized_red_flag_map for item in group]
        + [item for group in normalized_uncertainty_map for item in group],
        evidence_lookup,
        allowed_evidence_ids=allowed_set,
    )
    text_summaries = []
    normalized_assessment_final = {}
    for key, value in normalized_assessment.items():
        normalized_text, replacements, unresolved = normalize_text_evidence_ids(value, evidence_lookup)
        normalized_assessment_final[key] = normalized_text
        text_summaries.append(
            {
                "applied": bool(replacements),
                "replacements": replacements,
                "unresolved_ids": unresolved,
            }
        )
    normalized_assessment = normalized_assessment_final
    normalization_summary = _merge_normalization_summaries(
        top_level_summary,
        merged_summary,
        *key_finding_summaries,
        *red_flag_summaries,
        *uncertainty_summaries,
        *text_summaries,
    )
    if removed_invalid_evidence_records:
        normalization_summary["applied"] = True
        normalization_summary["removed_invalid_ids"] = _unique_preserve_order(
            removed_invalid_evidence_records
        )

    assessment_evidence_map = {
        key: list(merged_evidence_ids)
        for key in normalized_assessment.keys()
    }
    (
        normalized_assessment,
        key_findings,
        red_flags,
        open_uncertainties,
        normalized_key_finding_map,
        normalized_red_flag_map,
        normalized_uncertainty_map,
        assessment_evidence_map,
        evidence_routing_diagnostics,
    ) = route_analyst_claims(
        doctrine_id=doctrine["doctrine_id"],
        assessment=normalized_assessment,
        key_findings=key_findings,
        red_flags=red_flags,
        open_uncertainties=open_uncertainties,
        key_finding_map=normalized_key_finding_map,
        red_flag_map=normalized_red_flag_map,
        uncertainty_map=normalized_uncertainty_map,
        assessment_evidence_map=assessment_evidence_map,
        evidence_lookup=evidence_lookup,
        available_ids=allowed_set,
        financial_metrics_used=financial_metrics_used,
    )
    merged_evidence_ids = _unique_preserve_order(
        [item for values in assessment_evidence_map.values() for item in values]
        + [item for group in normalized_key_finding_map for item in group]
        + [item for group in normalized_red_flag_map for item in group]
        + [item for group in normalized_uncertainty_map for item in group]
    )
    if any(evidence_routing_diagnostics.get(key) for key in evidence_routing_diagnostics):
        schema_warnings.append("Evidence routing was repaired deterministically before grounding validation.")

    claim_evidence_map = {
        **{
            f"key_findings.{idx}": evidence_ids
            for idx, evidence_ids in enumerate(normalized_key_finding_map)
        },
        **{
            f"red_flags.{idx}": evidence_ids
            for idx, evidence_ids in enumerate(normalized_red_flag_map)
        },
        **{
            f"open_uncertainties.{idx}": evidence_ids
            for idx, evidence_ids in enumerate(normalized_uncertainty_map)
        },
        **{
            f"assessment.{key}": evidence_ids
            for key, evidence_ids in assessment_evidence_map.items()
        },
    }
    grounding = validate_analyst_evidence_grounding(
        assessment=normalized_assessment,
        key_findings=key_findings,
        red_flags=red_flags,
        open_uncertainties=open_uncertainties,
        claim_evidence_map=claim_evidence_map,
        supporting_pcim_sections=supporting_pcim_sections,
        consumed_sections=consumed_sections,
        supplied_evidence_ids=supplied_evidence_ids,
        evidence_lookup=evidence_lookup,
    )
    unresolved_ids = normalization_summary.get("unresolved_ids", []) or []
    if unresolved_ids:
        if grounding["evidence_grounding_status"] == "pass":
            grounding["evidence_grounding_status"] = "warning"
        critical_unresolved = any(
            unresolved_id in evidence_ids
            for unresolved_id in unresolved_ids
            for evidence_ids in (
                [claim_evidence_map.get(f"key_findings.{idx}", []) for idx in range(len(key_findings))]
                + [claim_evidence_map.get(f"red_flags.{idx}", []) for idx in range(len(red_flags))]
                + [claim_evidence_map.get(f"assessment.{key}", []) for key in normalized_assessment.keys()]
            )
        )
        if critical_unresolved:
            grounding["evidence_grounding_status"] = "fail"

    warning_messages = grounding["evidence_grounding_warnings"]
    if financial_sections_consumed and not financial_assessment["financials_used"]:
        warning_messages.append("Financial PCIM sections were available but the analyst did not mark them as used.")
    if derived_financial_context["basis_used"] == "unknown" and not any("basis" in item.lower() for item in financial_missing_data + financial_interpretation_limits + financial_assessment["missing_financial_data"] + financial_assessment["financial_interpretation_limits"]):
        warning_messages.append("Financial basis was unknown in PCIM but the analyst did not mention that limitation clearly.")
    if any("share-count" in item.lower() or "share count" in item.lower() for item in derived_financial_context["missing_data"]) and not any("share" in item.lower() for item in financial_missing_data + financial_interpretation_limits + financial_assessment["missing_financial_data"] + financial_assessment["financial_interpretation_limits"]):
        warning_messages.append("Share-count limitations were available in PCIM but not surfaced clearly.")
    warning_messages.extend(imprecise_financial_warning_messages)
    if any(item.startswith("financial warning auto-carried from PCIM:") for item in schema_warnings):
        warning_messages.append("Deterministic PCIM financial warnings were auto-carried into analyst output.")
    if context_metric_flags["has_shares_outstanding"] and any(
        "share count missing" in item.lower()
        for item in _texts_for_financial_matching(
            derived_financial_context.get("warnings", []),
            derived_financial_context.get("missing_data", []),
        )
    ):
        warning_messages.append(
            "PCIM share-count warning was imprecise; shares_outstanding exists, so equivalent per-share limitation wording was accepted."
        )
    if warning_messages and grounding["evidence_grounding_status"] == "pass":
        grounding["evidence_grounding_status"] = "warning"

    payload = {
        "doctrine_id": doctrine["doctrine_id"],
        "company": company,
        "pcim_version": pcim_version,
        "pcim_source": str(pcim_path),
        "analysis_mode": "llm_reasoning_v1",
        "sections_consumed": consumed_sections,
        "assessment": normalized_assessment,
        "rating": rating,
        "key_findings": key_findings,
        "red_flags": red_flags,
        "open_uncertainties": open_uncertainties,
        "financial_metrics_used": financial_metrics_used,
        "financial_red_flags": financial_red_flags,
        "financial_positive_signals": financial_positive_signals,
        "financial_missing_data": financial_missing_data,
        "financial_interpretation_limits": financial_interpretation_limits,
        "financial_assessment": financial_assessment,
        "financial_sections_consumed": financial_sections_consumed,
        "financial_warnings_carried_forward": financial_warnings_carried_forward or derived_financial_context["warnings"],
        "evidence_ids": merged_evidence_ids,
        "historical_context_used": historical_context_used,
        "years_considered": years_considered,
        "supporting_pcim_sections": supporting_pcim_sections,
        "evidence_id_normalization": normalization_summary,
        "evidence_grounding_status": grounding["evidence_grounding_status"],
        "evidence_grounding_warnings": grounding["evidence_grounding_warnings"],
        "evidence_routing_diagnostics": evidence_routing_diagnostics,
        "schema_warnings": _unique_preserve_order(schema_warnings),
        "reasoning_limits": reasoning_limits,
        "user_facing_brief": user_facing_brief,
        "generated_at": utc_now(),
    }
    hygiene_diagnostics: Dict[str, Any] = {"removed_invalid_evidence_ids": []}
    payload = sanitize_active_evidence_ids(
        payload,
        evidence_lookup=evidence_lookup,
        diagnostics=hygiene_diagnostics,
    )
    removed_invalid = hygiene_diagnostics.get("removed_invalid_evidence_ids", []) or []
    if removed_invalid:
        payload.setdefault("evidence_id_normalization", {})["applied"] = True
        payload.setdefault("evidence_id_normalization", {}).setdefault(
            "removed_invalid_ids",
            [],
        ).extend(removed_invalid)
        payload["schema_warnings"] = _unique_preserve_order(
            list(payload.get("schema_warnings") or [])
            + ["Invalid or non-evidence IDs were removed before analyst output save."]
        )
        if payload.get("evidence_grounding_status") == "pass":
            payload["evidence_grounding_status"] = "warning"
        payload["evidence_grounding_warnings"] = _unique_preserve_order(
            list(payload.get("evidence_grounding_warnings") or [])
            + ["Invalid or non-evidence IDs were removed before analyst output save."]
        )
    assert_valid_routed_payload(payload, evidence_lookup=evidence_lookup)
    return payload


def _analysis_filename(doctrine_id: str, analysis_mode: str) -> str:
    base = f"{_safe_slug(doctrine_id)}_analysis"
    if analysis_mode == "deterministic_scaffold":
        return f"{base}_dry_run.json"
    return f"{base}.json"


def _analysis_diagnostics_filename(doctrine_id: str, analysis_mode: str) -> str:
    base = f"{_safe_slug(doctrine_id)}_analysis_diagnostics"
    if analysis_mode == "deterministic_scaffold":
        return f"{base}_dry_run.json"
    return f"{base}.json"


def _failed_clean_candidate_filename(doctrine_id: str, analysis_mode: str) -> str:
    base = f"{_safe_slug(doctrine_id)}_analysis_failed_clean_candidate"
    if analysis_mode == "deterministic_scaffold":
        return f"{base}_dry_run.json"
    return f"{base}.json"


def sanitize_clean_string(value: str, path: str, diagnostics: Dict[str, Any]) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    if path == "$.pcim_source":
        return text
    lowered = text.lower()
    if not any(term in lowered for term in SOFT_FORBIDDEN_CLEAN_ANALYST_TERMS):
        return text

    if ".json" in lowered or "artifact missing" in lowered:
        diagnostics.setdefault("removed_internal_strings", []).append(
            {"path": path, "original": text, "action": "removed"}
        )
        return ""

    replacements = (
        ("financial artifacts do not cover all company years", "Financial data does not cover all company years"),
        ("provided artifacts", "provided materials"),
        ("available artifacts", "available materials"),
        ("source artifacts", "source materials"),
        ("financial artifacts", "financial data"),
        ("artifacts", "materials"),
        ("artifact", "material"),
    )
    sanitized = text
    for src, dest in replacements:
        sanitized = re.sub(src, dest, sanitized, flags=re.IGNORECASE)
    if sanitized != text:
        diagnostics.setdefault("rewritten_strings", []).append(
            {"path": path, "original": text, "sanitized": sanitized}
        )
    return sanitized.strip()


def _sanitize_clean_payload(value: Any, path: str, diagnostics: Dict[str, Any]) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            child = f"{path}.{key}"
            sanitized_item = _sanitize_clean_payload(item, child, diagnostics)
            if isinstance(sanitized_item, str) and not sanitized_item.strip():
                if key in {"financial_warnings_carried_forward"}:
                    continue
            sanitized[key] = sanitized_item
        return sanitized
    if isinstance(value, list):
        sanitized_list: List[Any] = []
        for idx, item in enumerate(value):
            sanitized_item = _sanitize_clean_payload(item, f"{path}[{idx}]", diagnostics)
            if isinstance(sanitized_item, str) and not sanitized_item.strip():
                continue
            sanitized_list.append(sanitized_item)
        return sanitized_list
    if isinstance(value, str):
        return sanitize_clean_string(value, path, diagnostics)
    return value


def _scan_clean_payload_issues(value: Any, path: str = "$") -> Tuple[List[str], List[str]]:
    forbidden_keys: List[str] = []
    forbidden_strings: List[str] = []

    def walk(item: Any, item_path: str) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = f"{item_path}.{key}"
                if key in FORBIDDEN_CLEAN_ANALYST_KEYS:
                    forbidden_keys.append(child_path)
                walk(child, child_path)
            return
        if isinstance(item, list):
            for idx, child in enumerate(item):
                walk(child, f"{item_path}[{idx}]")
            return
        if isinstance(item, str):
            lowered = item.lower()
            if any(term in lowered for term in HARD_FORBIDDEN_CLEAN_ANALYST_STRING_TOKENS):
                forbidden_strings.append(item_path)

    walk(value, path)
    return _unique_preserve_order(forbidden_keys), _unique_preserve_order(forbidden_strings)


def assert_clean_analysis_payload(payload: Dict[str, Any]) -> None:
    def walk(value: Any, path: str = "$") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{path}.{key}"
                if key in FORBIDDEN_CLEAN_ANALYST_KEYS:
                    raise ValueError(f"clean analyst payload contains forbidden internal key at {child}")
                if key == "evidence_ids":
                    if not isinstance(item, list):
                        raise ValueError(f"clean analyst payload has invalid evidence_ids at {child}")
                    for raw in item:
                        evidence_id = str(raw or "").strip()
                        if evidence_id in ROUTER_SECTION_NAME_DENYLIST:
                            raise ValueError(f"clean analyst payload contains section-name evidence_id at {child}: {evidence_id}")
                        if evidence_id.endswith(".json"):
                            raise ValueError(f"clean analyst payload contains JSON-filename evidence_id at {child}: {evidence_id}")
                    continue
                walk(item, child)
            return
        if isinstance(value, list):
            for idx, item in enumerate(value):
                walk(item, f"{path}[{idx}]")
            return
        if isinstance(value, str):
            if path == "$.pcim_source":
                return
            lowered = value.lower()
            if any(term in lowered for term in HARD_FORBIDDEN_CLEAN_ANALYST_STRING_TOKENS):
                raise ValueError(f"clean analyst payload contains forbidden internal string at {path}")

    walk(payload)
    matches = find_forbidden_recommendation_language(json.dumps(payload, ensure_ascii=False))
    if matches:
        raise ValueError("clean analyst payload contains forbidden recommendation or valuation language")


def write_clean_analyst_artifacts(
    *,
    payload: Dict[str, Any],
    output_dir: Path,
    doctrine_id: str,
    analysis_mode: str,
) -> Dict[str, Path]:
    filename = _analysis_filename(
        doctrine_id=doctrine_id,
        analysis_mode=analysis_mode,
    )
    diagnostics_filename = _analysis_diagnostics_filename(
        doctrine_id=doctrine_id,
        analysis_mode=analysis_mode,
    )
    failed_candidate_filename = _failed_clean_candidate_filename(
        doctrine_id=doctrine_id,
        analysis_mode=analysis_mode,
    )
    clean_payload, diagnostics_payload = split_clean_and_diagnostics(payload)
    diagnostics_payload.setdefault("rewritten_strings", [])
    diagnostics_payload.setdefault("removed_internal_strings", [])
    diagnostics_payload.setdefault("clean_writer_status", "pending")
    diagnostics_payload.setdefault("clean_writer_error", "")
    clean_payload = _sanitize_clean_payload(clean_payload, "$", diagnostics_payload)
    diagnostics_path = _write_json(output_dir / diagnostics_filename, diagnostics_payload)
    try:
        assert_clean_analysis_payload(clean_payload)
        diagnostics_payload["remaining_forbidden_keys"] = []
        diagnostics_payload["remaining_forbidden_strings"] = []
        clean_path = _write_json(output_dir / filename, clean_payload)
        diagnostics_payload["clean_writer_status"] = "pass"
        diagnostics_payload["clean_writer_error"] = ""
        diagnostics_path = _write_json(output_dir / diagnostics_filename, diagnostics_payload)
    except Exception as exc:
        remaining_keys, remaining_strings = _scan_clean_payload_issues(clean_payload)
        failed_candidate_path = _write_json(output_dir / failed_candidate_filename, clean_payload)
        diagnostics_payload["clean_writer_status"] = "fail"
        diagnostics_payload["clean_writer_error"] = str(exc)
        diagnostics_payload["failed_clean_candidate_path"] = str(failed_candidate_path)
        diagnostics_payload["remaining_forbidden_keys"] = remaining_keys
        diagnostics_payload["remaining_forbidden_strings"] = remaining_strings
        diagnostics_path = _write_json(output_dir / diagnostics_filename, diagnostics_payload)
        raise ValueError(f"clean analyst payload failed validation for {doctrine_id}: {exc}") from exc
    return {
        filename: clean_path,
        diagnostics_filename: diagnostics_path,
    }


class InvestorPanelRunner:
    def __init__(
        self,
        company: str,
        companies_root: Path | str = Path("companies"),
        doctrines_dir: Path | str = Path(__file__).resolve().parent / "doctrines",
        output_dir: Path | str | None = None,
    ):
        self.company = company
        self.companies_root = Path(companies_root)
        self.company_root = self.companies_root / company
        self.company_memory_dir = self.company_root / "company_memory"
        self.output_dir = (
            Path(output_dir)
            if output_dir is not None
            else investor_panel_dir(company)
        )
        self.registry = InvestorDoctrineRegistry(doctrines_dir)
        self.llm = get_llm()

    def _load_pcim(self) -> Tuple[Path, Dict[str, Any]]:
        pcim_path = self.company_memory_dir / PCIM_FILE
        pcim = _load_json(pcim_path)
        if not pcim:
            raise FileNotFoundError(f"PCIM not found or unreadable: {pcim_path}")
        if '"source_chunk"' in json.dumps(pcim, ensure_ascii=False):
            raise ValueError(f"PCIM must not contain source_chunk: {pcim_path}")
        return pcim_path, pcim

    def _selected_doctrines(self, analyst: Optional[str]) -> List[Dict[str, Any]]:
        doctrines = self.registry.load_all()
        if analyst:
            doctrines = [doctrine for doctrine in doctrines if doctrine["doctrine_id"] == analyst]
            if not doctrines:
                raise ValueError(f"Unknown analyst: {analyst}")

        max_analysts_raw = os.getenv("INVESTOR_PANEL_MAX_ANALYSTS")
        if max_analysts_raw and max_analysts_raw.strip():
            max_analysts = int(max_analysts_raw)
            if max_analysts <= 0:
                raise ValueError("INVESTOR_PANEL_MAX_ANALYSTS must be greater than 0 when set")
            doctrines = doctrines[:max_analysts]
        return doctrines

    def _is_dry_run(self) -> bool:
        return os.getenv("INVESTOR_PANEL_DRY_RUN", "").strip() in {"1", "true", "TRUE", "yes", "YES"}

    def _build_llm_payload(
        self,
        doctrine: Dict[str, Any],
        pcim_path: Path,
        pcim: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        consumed_sections = list(doctrine["evidence_required_from_pcim"])
        prompt, compact_pcim, section_stats, limits_used, input_compacted, budget_report = _build_compact_prompt(
            doctrine=doctrine,
            company=self.company,
            pcim_path=pcim_path,
            pcim=pcim,
            sections=consumed_sections,
        )
        llm_input_pack = _build_prompt_input_pack(
            company=self.company,
            doctrine=doctrine,
            pcim_path=pcim_path,
            compact_pcim=compact_pcim,
            allowed_sections=consumed_sections,
            limits_used=limits_used,
            input_compacted=input_compacted,
        )
        validate_prompt_payload(compact_pcim, pcim_source=str(pcim_path))
        allowed_evidence_ids = _collect_section_evidence_ids(pcim, consumed_sections)
        prompt_chars = len(prompt)
        prompt_tokens = _estimate_prompt_tokens(prompt)
        pack_metadata = llm_input_pack.setdefault("metadata", {})
        truncation_details = pack_metadata.setdefault("truncation_details", {})
        truncation_details["estimated_tokens_before"] = max(
            int(truncation_details.get("estimated_tokens_before") or 0),
            prompt_tokens,
        )
        truncation_details["estimated_tokens_after"] = pack_metadata.get("tokens_estimated") or truncation_details.get(
            "estimated_tokens_after", 0
        )
        manifest_extra = dict(pack_metadata.get("manifest_extra") or {})
        manifest_extra.update({
            "analyst": doctrine["doctrine_id"],
            "sections_requested": consumed_sections,
            "sections_included": list(compact_pcim.keys()),
            "prompt_chars_before": budget_report["prompt_chars_before"],
            "prompt_chars_after": budget_report["prompt_chars_after"],
            "estimated_tokens_before": budget_report["prompt_tokens_before"],
            "estimated_tokens_after": budget_report["pack_tokens_after"],
            "truncation_applied": bool(pack_metadata.get("truncation_applied")),
            "token_budget": budget_report["token_budget"],
            "prompt_tokens_before": budget_report["prompt_tokens_before"],
            "prompt_tokens_after": budget_report["prompt_tokens_after"],
            "pack_tokens_before": budget_report["pack_tokens_before"],
            "pack_tokens_after": budget_report["pack_tokens_after"],
            "raw_largest_sections": budget_report["raw_largest_sections"],
            "compacted_largest_sections": budget_report["compacted_largest_sections"],
            "budget_status": budget_report["budget_status"],
        })
        pack_metadata["manifest_extra"] = manifest_extra
        for warning in budget_report.get("warnings", []):
            if warning not in pack_metadata.setdefault("warnings", []):
                pack_metadata["warnings"].append(warning)
        print(
            "[INVESTOR PANEL] "
            f"analyst={doctrine['doctrine_id']} "
            f"sections={consumed_sections} "
            f"prompt_chars={prompt_chars} "
            f"approx_tokens={prompt_tokens} "
            f"budget_status={budget_report['budget_status']} "
            f"item_counts={section_stats} "
            f"limits={limits_used}"
        )

        response = call_llm_with_input_pack(
            llm=self.llm,
            prompt=prompt,
            input_pack=llm_input_pack,
            manifest_path=self.output_dir / "investor_panel_llm_call_manifest.json",
            require_source_artifacts=True,
            response_schema={"type": "object"},
            temperature=0.0,
            system_prompt=_build_system_prompt(),
        )
        payload = _validate_llm_panel_output(
            payload_text=response.text,
            doctrine=doctrine,
            company=self.company,
            pcim_path=pcim_path,
            pcim_version=pcim.get("contract_version"),
            pcim=pcim,
            consumed_sections=consumed_sections,
            allowed_evidence_ids=allowed_evidence_ids,
        )
        if doctrine["doctrine_id"] == "munger" and _has_governance_routing_failure(payload):
            repair_instruction = (
                "\n\nMunger evidence routing repair required: Replace governance/incentive evidence IDs "
                "with governance/ownership/capital-allocation/uncertainty evidence. If not available, "
                "downgrade the claim to a limitation. Do not use market-risk, FX-risk, interest-rate-risk, "
                "generic operational-risk, or generic business-model evidence for governance or incentive "
                "claims unless the claim is explicitly about risk oversight or risk governance."
            )
            repaired_prompt = prompt + repair_instruction
            response = call_llm_with_input_pack(
                llm=self.llm,
                prompt=repaired_prompt,
                input_pack=llm_input_pack,
                manifest_path=self.output_dir / "investor_panel_llm_call_manifest.json",
                require_source_artifacts=True,
                response_schema={"type": "object"},
                temperature=0.0,
                system_prompt=_build_system_prompt(),
            )
            payload = _validate_llm_panel_output(
                payload_text=response.text,
                doctrine=doctrine,
                company=self.company,
                pcim_path=pcim_path,
                pcim_version=pcim.get("contract_version"),
                pcim=pcim,
                consumed_sections=consumed_sections,
                allowed_evidence_ids=allowed_evidence_ids,
            )
            if _has_governance_routing_failure(payload):
                raise ValueError(
                    "Munger evidence grounding failed after one repair attempt: "
                    "governance/incentive claims still cite market-risk evidence."
                )
            prompt = repaired_prompt
        if input_compacted and COMPACTION_REASONING_LIMIT not in payload["reasoning_limits"]:
            payload["reasoning_limits"].append(COMPACTION_REASONING_LIMIT)
        return payload, prompt

    def _build_dry_run_payload(
        self,
        doctrine: Dict[str, Any],
        pcim_path: Path,
        pcim: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        consumed_sections = list(doctrine["evidence_required_from_pcim"])
        prompt, compact_pcim, section_stats, limits_used, input_compacted, budget_report = _build_compact_prompt(
            doctrine=doctrine,
            company=self.company,
            pcim_path=pcim_path,
            pcim=pcim,
            sections=consumed_sections,
        )
        _build_prompt_input_pack(
            company=self.company,
            doctrine=doctrine,
            pcim_path=pcim_path,
            compact_pcim=compact_pcim,
            allowed_sections=consumed_sections,
            limits_used=limits_used,
            input_compacted=input_compacted,
        )
        validate_prompt_payload(compact_pcim, pcim_source=str(pcim_path))
        payload = _deterministic_panel_output(
            doctrine=doctrine,
            company=self.company,
            pcim_path=pcim_path,
            pcim=pcim,
        )
        if input_compacted and COMPACTION_REASONING_LIMIT not in payload["reasoning_limits"]:
            payload["reasoning_limits"].append(COMPACTION_REASONING_LIMIT)
        print(
            f"[INVESTOR PANEL DRY RUN] analyst={doctrine['doctrine_id']} "
            f"sections={consumed_sections} prompt_chars={len(prompt)} "
            f"approx_tokens={_estimate_prompt_tokens(prompt)} "
            f"budget_status={budget_report['budget_status']} "
            f"item_counts={section_stats} limits={limits_used}"
        )
        return payload, prompt

    def run(self, analyst: Optional[str] = None) -> Dict[str, Path]:
        pcim_path, pcim = self._load_pcim()
        doctrines = self._selected_doctrines(analyst)
        written_paths: Dict[str, Path] = {}
        analyses = []
        dry_run = self._is_dry_run()

        for doctrine in doctrines:
            if dry_run:
                payload, prompt = self._build_dry_run_payload(
                    doctrine=doctrine,
                    pcim_path=pcim_path,
                    pcim=pcim,
                )
            else:
                payload, prompt = self._build_llm_payload(
                    doctrine=doctrine,
                    pcim_path=pcim_path,
                    pcim=pcim,
                )

            missing_output_keys = REQUIRED_OUTPUT_KEYS - set(payload.keys())
            if missing_output_keys:
                raise ValueError(
                    f"Investor panel output missing required keys: {sorted(missing_output_keys)}"
                )

            written_paths.update(
                write_clean_analyst_artifacts(
                    payload=payload,
                    output_dir=self.output_dir,
                    doctrine_id=doctrine["doctrine_id"],
                    analysis_mode=payload["analysis_mode"],
                )
            )
            analyses.append(
                {
                    "doctrine_id": doctrine["doctrine_id"],
                    "output_file": _analysis_filename(
                        doctrine_id=doctrine["doctrine_id"],
                        analysis_mode=payload["analysis_mode"],
                    ),
                    "diagnostics_file": _analysis_diagnostics_filename(
                        doctrine_id=doctrine["doctrine_id"],
                        analysis_mode=payload["analysis_mode"],
                    ),
                    "analysis_mode": payload["analysis_mode"],
                    "rating": payload["rating"],
                    "sections_consumed": payload["sections_consumed"],
                    "prompt_chars": len(prompt),
                }
            )

        panel_index = {
            "company": self.company,
            "pcim_source": str(pcim_path),
            "analysis_mode": "deterministic_scaffold" if dry_run else "llm_reasoning_v1",
            "analysts_run": analyses,
            "generated_at": utc_now(),
        }
        written_paths["panel_index.json"] = _write_json(self.output_dir / "panel_index.json", panel_index)
        return written_paths
