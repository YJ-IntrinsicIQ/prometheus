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
    collect_user_facing_brief_validation_issues,
    finalize_user_facing_brief,
    finalize_user_facing_brief_for_external_reader,
    LENS_CONFIG,
    normalize_user_facing_brief_lengths,
    normalize_user_facing_brief_shape,
    rewrite_text_for_external_reader,
    sanitize_user_facing_brief,
    validate_user_facing_brief,
)
from .company_memory_context import build_company_memory_context
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
DEFAULT_MAX_TOTAL_PROMPT_CHARS = 36_000
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
MIN_TOTAL_PROMPT_BUDGET_TOKENS = 4000
MIN_COMPACT_INPUT_PACK_BUDGET_TOKENS = 1200
MIN_FINANCIAL_TRUTH_PACK_BUDGET_TOKENS = 250
MIN_EVIDENCE_PACK_BUDGET_TOKENS = 120
MIN_DOCTRINE_CONTEXT_BUDGET_TOKENS = 600
DEFAULT_TOTAL_PROMPT_BUDGET_TOKENS = 9000
DEFAULT_HARD_MAX_PROMPT_TOKENS = 10000
DEFAULT_COMPACT_INPUT_PACK_BUDGET_TOKENS = 4200
DEFAULT_FINANCIAL_TRUTH_PACK_BUDGET_TOKENS = 900
DEFAULT_EVIDENCE_PACK_BUDGET_TOKENS = 500
DEFAULT_DOCTRINE_CONTEXT_BUDGET_TOKENS = 2200
DEFAULT_RESERVED_SYSTEM_TOKENS = 250
DEFAULT_RESERVED_INSTRUCTION_TOKENS = 1000
DEFAULT_RESERVED_OUTPUT_SCHEMA_TOKENS = 700
DEFAULT_WARNING_POLICY_PACK_BUDGET_TOKENS = 400
DEFAULT_FINANCIAL_TRUTH_TOKEN_SHARE = 0.25
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
DOCTRINE_SECTION_PRIORITIES = {
    "graham": [
        "financial_truth_inputs",
        "balance_sheet_strength_inputs",
        "cash_conversion_inputs",
        "working_capital_inputs",
        "financial_quality_inputs",
        "per_share_inputs",
        "governance_and_incentive_inputs",
        "risk_inputs",
    ],
    "buffett": [
        "financial_truth_inputs",
        "business_understanding",
        "moat_inputs",
        "business_economics_inputs",
        "return_on_capital_inputs",
        "capital_allocation_inputs",
        "management_quality_inputs",
        "financial_quality_inputs",
    ],
    "fisher": [
        "financial_truth_inputs",
        "growth_quality_inputs",
        "growth_execution_inputs",
        "profitability_inputs",
        "working_capital_inputs",
        "management_quality_inputs",
        "moat_inputs",
    ],
    "munger": [
        "financial_truth_inputs",
        "governance_and_incentive_inputs",
        "risk_inputs",
        "capital_allocation_inputs",
        "working_capital_inputs",
        "ownership_inputs",
    ],
    "lynch": [
        "financial_truth_inputs",
        "business_understanding",
        "simplicity_and_story_inputs",
        "story_vs_numbers_inputs",
        "profitability_inputs",
        "per_share_inputs",
        "growth_quality_inputs",
    ],
}

DOCTRINE_DIFFERENTIATION_GUIDANCE: Dict[str, Dict[str, Any]] = {
    "graham": {
        "primary_doctrine_question": "Does the evidence protect the investor from permanent loss, weak financial integrity, or inadequate margin of safety?",
        "shared_fact_interpretation": {
            "capex": "Does the spending weaken balance-sheet protection, financing resilience, or downside protection?",
            "revenue_growth": "Is growth stable enough to support asset protection, or is it distracting from weaker safety evidence?",
            "management_execution": "Does execution reduce financial fragility, accounting uncertainty, or downside risk?",
            "low_debt": "Use debt conservatism as protection evidence only when cash conversion and asset quality also support it.",
        },
        "must_prioritize": [
            "balance-sheet resilience",
            "debt and liquidity risk",
            "cash conversion and working-capital strain",
            "financial integrity, reconciliation warnings, and missing evidence",
            "downside protection before upside narrative",
        ],
        "downweight_generic": [
            "growth ambition unless it affects downside or earnings stability",
            "moat language without financial protection evidence",
            "management optimism not tied to conservative financing or risk control",
        ],
    },
    "buffett": {
        "primary_doctrine_question": "Does the evidence show a durable, understandable business that can compound owner capital under rational stewardship?",
        "shared_fact_interpretation": {
            "capex": "Is retained capital being deployed into durable economics with visible incremental returns or owner-value evidence?",
            "revenue_growth": "Does growth reinforce durable competitive advantage and owner earnings rather than merely adding scale?",
            "management_execution": "Does management behavior show rational stewardship and capital-allocation discipline over time?",
            "low_debt": "Treat low debt as helpful only if paired with durable returns, cash generation, and reinvestment runway.",
        },
        "must_prioritize": [
            "business quality and moat durability",
            "owner earnings and cash conversion quality",
            "return on capital and per-share economics",
            "capital allocation and management stewardship",
            "long-term compounding durability",
        ],
        "downweight_generic": [
            "short-term growth not tied to durable economics",
            "one-off execution items without owner-return evidence",
            "financial strength facts that do not change compounding quality",
        ],
    },
    "fisher": {
        "primary_doctrine_question": "Does the evidence reveal a long runway for quality growth through products, customers, R&D, distribution, or management depth?",
        "shared_fact_interpretation": {
            "capex": "Does the investment expand product capability, capacity, customer reach, or the long-term growth runway?",
            "revenue_growth": "Is growth supported by products, customers, distribution, innovation, or repeatable execution?",
            "management_execution": "Does execution show management depth and follow-through on long-term growth initiatives?",
            "low_debt": "Use low debt mainly as funding flexibility for growth, not as the central conclusion.",
        },
        "must_prioritize": [
            "growth runway and durability",
            "product, customer, R&D, and distribution evidence",
            "management depth and execution follow-through",
            "growth quality versus cash-consuming growth",
            "scuttlebutt-style operating clues from supplied evidence",
        ],
        "downweight_generic": [
            "static balance-sheet comfort unless it funds growth quality",
            "valuation or downside framing",
            "generic profitability facts without growth mechanism",
        ],
    },
    "munger": {
        "primary_doctrine_question": "What could make the apparent story wrong through incentives, complexity, fragility, accounting traps, or repeated misjudgment?",
        "shared_fact_interpretation": {
            "capex": "Does the spending create complexity, irreversible exposure, poor incentives, or execution risk?",
            "revenue_growth": "Could growth mask fragility, accounting weakness, cash strain, or incentive-driven behavior?",
            "management_execution": "Does the behavior reveal sound judgment, avoidable mistakes, or recurring blind spots?",
            "low_debt": "Low debt reduces one failure mode but does not offset complexity, governance, or cash-conversion traps.",
        },
        "must_prioritize": [
            "incentives and governance sanity",
            "failure modes and self-inflicted risk",
            "complexity, fragility, and accounting/economic traps",
            "contradictions between story, numbers, and behavior",
            "recurring mistakes or weak risk judgment",
        ],
        "downweight_generic": [
            "simple praise for growth or low debt",
            "success claims that ignore contradictions",
            "capital allocation applause without downside or behavior analysis",
        ],
    },
    "lynch": {
        "primary_doctrine_question": "Is there a simple, believable business story, and do the operating facts show that story improving or deteriorating?",
        "shared_fact_interpretation": {
            "capex": "Does the spending make the growth story easier to believe, or does it complicate the story?",
            "revenue_growth": "Does growth fit a clear category and operating story, or does it look like hype outrunning reality?",
            "management_execution": "Does execution make the business story simpler and more credible for a practical investor?",
            "low_debt": "Use low debt as a sanity check, not as a substitute for a clear business story.",
        },
        "must_prioritize": [
            "plain-language business category",
            "story versus operating evidence",
            "growth expectations versus reality",
            "momentum, simplicity, and balance-sheet sanity",
            "hype or category mismatch",
        ],
        "downweight_generic": [
            "technical detail that does not clarify the story",
            "financial facts not connected to investor-readable business progress",
            "doctrine jargon or abstract quality labels",
        ],
    },
}

HEAVY_SECTION_KEYS = {
    "multi_year_inputs",
    "management_quality_inputs",
    "capital_allocation_inputs",
    "moat_inputs",
    "business_economics_inputs",
    "financial_truth_inputs",
}
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
    "precise_missing_financial_data",
    "derived_not_explicitly_reported",
    "partial_financial_data",
    "unreliable_financial_data",
    "invalid_or_quarantined_financial_data",
    "trend_durability_limits",
    "financial_missing_data",
    "financial_interpretation_limits",
    "financial_questions_for_investor",
    "analyst_financial_truth_pack",
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
    "financial_truth_inputs",
    "financial_snapshot_inputs",
    "owner_earnings_readiness_inputs",
    "working_capital_quality_inputs",
    "capital_allocation_financial_inputs",
    "per_share_compounding_inputs",
    "unreliable_financial_inputs",
    "invalid_or_quarantined_financial_inputs",
    "precise_missing_financial_inputs",
    "financial_warning_policy",
    "financial_panel_status",
    "financial_panel_usable_domains",
    "financial_panel_limited_domains",
    "financial_panel_blocked_domains",
    "investor_financial_questions",
}

BLOCKED_FINANCIAL_WARNING_REWRITES = {
    "fcf missing": "FCF is derived from CFO and capex, but explicit FCF disclosure was not found.",
    "free cash flow missing": "FCF is derived from CFO and capex, but explicit FCF disclosure was not found.",
    "capex missing": "Capex exists, but maintenance versus growth capex split is not disclosed.",
    "payables missing": "Payables or payable-days are available, but cash-conversion interpretation remains limited by coverage or comparability.",
    "roe unavailable": "ROE is available for limited periods, but durability is unproven without broader comparable history.",
    "roce unavailable": "ROCE is available for limited periods, but durability is unproven without broader comparable history.",
    "share count missing": "Closing shares exist, but weighted-average or diluted-share comparability remains limited.",
    "ownership missing": "Ownership/shareholding data is invalid or quarantined and should not be used downstream.",
    "cfo/pat missing": "CFO and PAT may be present, but cash-conversion durability remains limited by coverage or reconciliation quality.",
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
    "capex_deployed": ("capex deployed", "capex deployed capital allocation ledger", "capex deployed capital-allocation ledger"),
    "fcf": ("fcf", "free cash flow", "free cashflow"),
    "fcf_to_pat": ("fcf to pat", "fcf/pat"),
    "conservative_fcf_after_total_capex": (
        "conservative fcf",
        "fcf estimate",
        "conservative free cash flow",
        "conservative fcf after total capex",
    ),
    "total_debt": ("total debt", "debt", "borrowings"),
    "net_debt": ("net debt",),
    "cash_and_equivalents": ("cash and equivalents", "cash equivalents", "cash"),
    "net_worth": ("net worth", "equity", "net worth / reserves"),
    "reserves": ("reserves", "other equity"),
    "receivables": ("receivables", "trade receivables", "receivables value"),
    "inventory": ("inventory", "inventories", "inventory value"),
    "payables": ("payables", "trade payables", "payables value"),
    "receivable_days": ("receivable days", "debtor days"),
    "inventory_days": ("inventory days",),
    "payable_days": ("payable days",),
    "cash_conversion_cycle": ("cash conversion cycle", "ccc"),
    "eps_basic": ("eps basic", "basic eps", "basic earnings per share"),
    "eps_diluted": ("eps diluted", "diluted eps", "diluted earnings per share"),
    "shares_outstanding": ("shares outstanding", "share count", "reported share count", "number of shares outstanding", "closing shares"),
    "weighted_avg_shares": ("weighted average shares", "weighted avg shares"),
    "diluted_shares": ("diluted shares",),
    "dividend_paid": ("dividend paid",),
    "dividend_per_share": ("dividend per share", "dps"),
    "payout_ratio": ("payout ratio",),
    "book_value_per_share": ("book value per share", "bvps"),
    "debt_to_equity": ("debt to equity", "debt/equity"),
    "tangible_book_value_per_share": ("tangible book value per share",),
    "owner_earnings_estimate": ("owner earnings estimate", "owner-earnings estimate", "owner earnings estimate derived", "owner-earnings estimate derived", "owner earnings"),
    "total_identified_capex": ("total identified capex", "identified capex total", "identified capex", "identified capex total derived"),
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
KNOWN_ANALYST_FINAL_STATUS = {"pass", "warning", "fail"}

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


def _resolve_budget_int_env(name: str, default: int, minimum: int) -> int:
    value = _resolve_positive_int_env(name, default)
    return max(minimum, value)


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
    total_prompt_budget_tokens = _resolve_budget_int_env(
        "INVESTOR_PANEL_TOTAL_PROMPT_BUDGET_TOKENS",
        DEFAULT_TOTAL_PROMPT_BUDGET_TOKENS,
        MIN_TOTAL_PROMPT_BUDGET_TOKENS,
    )
    hard_max_prompt_tokens = _resolve_budget_int_env(
        "INVESTOR_PANEL_HARD_MAX_PROMPT_TOKENS",
        DEFAULT_HARD_MAX_PROMPT_TOKENS,
        total_prompt_budget_tokens,
    )
    compact_input_pack_budget_tokens = _resolve_budget_int_env(
        "INVESTOR_PANEL_COMPACT_INPUT_PACK_BUDGET_TOKENS",
        DEFAULT_COMPACT_INPUT_PACK_BUDGET_TOKENS,
        MIN_COMPACT_INPUT_PACK_BUDGET_TOKENS,
    )
    financial_truth_pack_budget_tokens = _resolve_budget_int_env(
        "INVESTOR_PANEL_FINANCIAL_TRUTH_PACK_BUDGET_TOKENS",
        DEFAULT_FINANCIAL_TRUTH_PACK_BUDGET_TOKENS,
        MIN_FINANCIAL_TRUTH_PACK_BUDGET_TOKENS,
    )
    evidence_pack_budget_tokens = _resolve_budget_int_env(
        "INVESTOR_PANEL_EVIDENCE_PACK_BUDGET_TOKENS",
        DEFAULT_EVIDENCE_PACK_BUDGET_TOKENS,
        MIN_EVIDENCE_PACK_BUDGET_TOKENS,
    )
    doctrine_context_budget_tokens = _resolve_budget_int_env(
        "INVESTOR_PANEL_DOCTRINE_CONTEXT_BUDGET_TOKENS",
        DEFAULT_DOCTRINE_CONTEXT_BUDGET_TOKENS,
        MIN_DOCTRINE_CONTEXT_BUDGET_TOKENS,
    )
    warning_policy_pack_budget_tokens = _resolve_budget_int_env(
        "INVESTOR_PANEL_WARNING_POLICY_PACK_BUDGET_TOKENS",
        DEFAULT_WARNING_POLICY_PACK_BUDGET_TOKENS,
        150,
    )
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
        "total_prompt_budget_tokens": total_prompt_budget_tokens,
        "hard_max_prompt_tokens": hard_max_prompt_tokens,
        "compact_input_pack_budget_tokens": compact_input_pack_budget_tokens,
        "financial_truth_pack_budget_tokens": financial_truth_pack_budget_tokens,
        "evidence_pack_budget_tokens": evidence_pack_budget_tokens,
        "doctrine_context_budget_tokens": doctrine_context_budget_tokens,
        "warning_policy_pack_budget_tokens": warning_policy_pack_budget_tokens,
        "max_sections": DEFAULT_MAX_SECTIONS,
        "max_nested_items_per_item": DEFAULT_MAX_NESTED_ITEMS_PER_ITEM,
        "max_text_chars_per_value": DEFAULT_MAX_TEXT_CHARS_PER_VALUE,
        "max_evidence_ids_per_item": DEFAULT_MAX_EVIDENCE_IDS_PER_ITEM,
        "max_dict_keys_per_item": DEFAULT_MAX_DICT_KEYS_PER_ITEM,
        "reserved_system_tokens": DEFAULT_RESERVED_SYSTEM_TOKENS,
        "reserved_instruction_tokens": DEFAULT_RESERVED_INSTRUCTION_TOKENS,
        "reserved_output_schema_tokens": DEFAULT_RESERVED_OUTPUT_SCHEMA_TOKENS,
        "financial_truth_token_share": DEFAULT_FINANCIAL_TRUTH_TOKEN_SHARE,
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
        section_value = evidence_map.get(section, []) or []
        if isinstance(section_value, dict):
            if isinstance(section_value.get("sample_evidence_ids"), list):
                iter_ids = section_value.get("sample_evidence_ids", [])
            elif isinstance(section_value.get("evidence_ids"), list):
                iter_ids = section_value.get("evidence_ids", [])
            else:
                iter_ids = []
        else:
            iter_ids = section_value
        for evidence_id in iter_ids:
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


def _financial_metric_id_from_entry(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return str(
        item.get("metric_id")
        or item.get("canonical_metric")
        or item.get("metric")
        or item.get("metric_name")
        or item.get("field")
        or ""
    ).strip()


def _financial_metric_source_field(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ("source_field", "metric_id", "canonical_metric", "metric", "metric_name", "field"):
        value = str(item.get(key) or "").strip()
        if value:
            return key
    return ""


def _build_registry_metric_entry(
    canonical_metric: str,
    *,
    period: Any = None,
    value: Any = None,
    unit: str = "",
    basis: Any = None,
    confidence: Any = None,
    source_section: str,
    source_field: str = "",
    source_file: str = "",
) -> Dict[str, Any]:
    period_value = str(period or "").strip().lower()
    metric_id = canonical_metric if not period_value else f"{canonical_metric}:{period_value}"
    return {
        "metric_id": metric_id,
        "canonical_metric": canonical_metric,
        "display_name": canonical_metric.replace("_", " "),
        "period": period_value or None,
        "value": value,
        "unit": unit or "",
        "basis": str(basis or "").strip() or "unknown",
        "confidence": str(confidence or "").strip() or "unknown",
        "source_section": source_section,
        "source_field": source_field or canonical_metric,
        "source_file": source_file or "",
        "aliases": _metric_aliases(canonical_metric),
    }


def _iter_truth_pack_metrics(payload: Dict[str, Any], source_section: str) -> Iterable[Tuple[Dict[str, Any], str]]:
    for field in (
        "usable_current_metrics",
        "usable_derived_metrics",
        "partial_metrics",
        "unreliable_metrics",
        "invalid_or_quarantined_metrics",
        "precise_missing_metrics",
        "derived_not_explicitly_reported",
    ):
        for item in payload.get(field, []) or []:
            if isinstance(item, dict):
                yield item, field


def _collect_metric_entries_from_value(
    value: Any,
    *,
    source_section: str,
    source_file: str,
    source_field: str,
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        candidate_metric = _financial_metric_id_from_entry(value)
        if candidate_metric:
            metric_value, metric_unit = _extract_metric_value(value)
            entries.append(
                _build_registry_metric_entry(
                    candidate_metric,
                    period=value.get("period") or value.get("year") or value.get("source_year"),
                    value=metric_value,
                    unit=metric_unit,
                    basis=value.get("basis"),
                    confidence=value.get("confidence"),
                    source_section=source_section,
                    source_field=source_field or _financial_metric_source_field(value),
                    source_file=source_file,
                )
            )
        for nested_key, nested_value in value.items():
            entries.extend(
                _collect_metric_entries_from_value(
                    nested_value,
                    source_section=source_section,
                    source_file=source_file,
                    source_field=source_field or str(nested_key),
                )
            )
    elif isinstance(value, list):
        for item in value:
            entries.extend(
                _collect_metric_entries_from_value(
                    item,
                    source_section=source_section,
                    source_file=source_file,
                    source_field=source_field,
                )
            )
    return entries


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
        latest = max(
            (point for point in series if isinstance(point, dict)),
            key=lambda point: _financial_period_sort_key(point.get("year") or point.get("period")),
            default={},
        )
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


def _financial_period_sort_key(value: Any) -> Tuple[int, str]:
    text = str(value or "").strip().lower()
    match = re.search(r"(?:fy)?\s*(\d{2,4})", text)
    if not match:
        return (-1, text)
    year = int(match.group(1))
    if year < 100:
        year += 2000
    return (year, text)


def _build_financial_metric_registry(selected_pcim: Dict[str, Any], sections: List[str]) -> List[Dict[str, Any]]:
    registry: List[Dict[str, Any]] = []
    seen_metric_ids: set[str] = set()

    def add_entry(entry: Dict[str, Any]) -> None:
        metric_id = str(entry.get("metric_id") or "").strip()
        canonical = str(entry.get("canonical_metric") or "").strip()
        if not metric_id or not canonical or metric_id in seen_metric_ids:
            return
        seen_metric_ids.add(metric_id)
        registry.append(entry)

    def add_metric(
        canonical_metric: Any,
        *,
        period: Any = None,
        value: Any = None,
        unit: str = "",
        basis: Any = None,
        confidence: Any = None,
        source_section: str,
        source_field: str = "",
        source_file: str = "",
    ) -> None:
        canonical = str(canonical_metric or "").strip()
        if not canonical:
            return
        add_entry(
            _build_registry_metric_entry(
                canonical,
                period=period,
                value=value,
                unit=unit,
                basis=basis,
                confidence=confidence,
                source_section=source_section,
                source_field=source_field,
                source_file=source_file,
            )
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
                        source_field="by_year.key_metrics.field",
                        source_file=str(payload.get("source_artifact") or ""),
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
                        source_field=f"by_year.{key}.metric",
                        source_file=str(payload.get("source_artifact") or ""),
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
                    latest_point = max(
                        (point for point in series if isinstance(point, dict)),
                        key=lambda point: _financial_period_sort_key(point.get("year") or point.get("period")),
                        default={},
                    )
                    period = latest_point.get("year") or latest_point.get("period")
                add_metric(
                    item.get("metric"),
                    period=period,
                    value=value,
                    unit=unit,
                    basis=item.get("basis") or payload.get("basis") or payload.get("basis_used"),
                    confidence=item.get("confidence"),
                    source_section=section,
                    source_field="metric_trends.metric" if section == "financial_trend_inputs" else "metrics.metric",
                    source_file=str(payload.get("source_artifact") or ""),
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
                            source_field="by_year.sections.evidence_metrics",
                            source_file=str(payload.get("source_artifact") or ""),
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
                    source_field="attributions.metric",
                    source_file=str(payload.get("source_artifact") or ""),
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
                        source_field="financial_growth_summary.by_year.growth_metrics.metric",
                        source_file=str(growth_quality.get("source_artifact") or ""),
                    )

    truth_pack_sections = (
        "financial_truth_inputs",
        "owner_earnings_readiness_inputs",
        "working_capital_quality_inputs",
        "capital_allocation_financial_inputs",
        "per_share_compounding_inputs",
    )
    for section in truth_pack_sections:
        payload = selected_pcim.get(section) or {}
        if not isinstance(payload, dict):
            continue
        source_file = str(payload.get("source_artifact") or "")
        if section == "financial_truth_inputs":
            for item, field_name in _iter_truth_pack_metrics(payload, section):
                metric_id = _financial_metric_id_from_entry(item)
                if not metric_id:
                    continue
                metric_value, metric_unit = _extract_metric_value(item)
                add_metric(
                    metric_id,
                    period=item.get("period") or item.get("year") or item.get("source_year"),
                    value=metric_value,
                    unit=metric_unit,
                    basis=item.get("basis") or payload.get("basis_used"),
                    confidence=item.get("confidence"),
                    source_section=section,
                    source_field=field_name,
                    source_file=source_file,
                )
        elif section == "owner_earnings_readiness_inputs":
            for item in payload.get("bridges", []) or []:
                if not isinstance(item, dict):
                    continue
                year = item.get("fiscal_year") or item.get("year")
                for key in (
                    "cfo",
                    "reported_pat",
                    "ppe_cwip_capex",
                    "intangible_capex",
                    "total_identified_capex",
                    "estimated_maintenance_capex",
                    "estimated_growth_capex",
                    "fcf_after_ppe_cwip_capex",
                    "conservative_fcf_after_total_capex",
                    "owner_earnings_estimate",
                ):
                    if key not in item:
                        continue
                    add_metric(
                        key,
                        period=year,
                        value=item.get(key),
                        unit="₹ crore",
                        basis=payload.get("basis_used"),
                        confidence=item.get("owner_earnings_precision_status") or item.get("confidence"),
                        source_section=section,
                        source_field=f"bridges.{key}",
                        source_file=source_file,
                    )
        elif section == "working_capital_quality_inputs":
            for field_name in ("drilldown", "order_to_cash_tracker"):
                for entry in _collect_metric_entries_from_value(
                    payload.get(field_name),
                    source_section=section,
                    source_file=source_file,
                    source_field=field_name,
                ):
                    add_entry(entry)
        elif section == "capital_allocation_financial_inputs":
            for entry in _collect_metric_entries_from_value(
                payload.get("entries"),
                source_section=section,
                source_file=source_file,
                source_field="entries",
            ):
                add_entry(entry)
        elif section == "per_share_compounding_inputs":
            for entry in _collect_metric_entries_from_value(
                payload.get("analysis"),
                source_section=section,
                source_file=source_file,
                source_field="analysis",
            ):
                add_entry(entry)
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
            _build_registry_metric_entry(
                canonical_metric,
                value=preferred.get("value"),
                unit=str(preferred.get("unit") or ""),
                basis=preferred.get("basis"),
                confidence=preferred.get("confidence"),
                source_section=str(preferred.get("source_section") or ""),
                source_field=str(preferred.get("source_field") or canonical_metric),
                source_file=str(preferred.get("source_file") or ""),
            )
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


def _normalize_financial_truth_list(value: Any) -> List[str]:
    return _unique_preserve_order(
        [str(item).strip() for item in (value or []) if str(item).strip()]
    )


def _metric_entry_has_usable_value(entry: Dict[str, Any]) -> bool:
    value = entry.get("value")
    return isinstance(value, (int, float))


def _metric_present_in_registry(
    metric_registry: List[Dict[str, Any]],
    aliases: Sequence[str],
    *,
    require_usable_value: bool = False,
) -> bool:
    alias_set = {str(alias).strip().lower() for alias in aliases if str(alias).strip()}
    for entry in metric_registry:
        canonical = str(entry.get("canonical_metric") or "").strip().lower()
        metric_id = str(entry.get("metric_id") or "").strip().lower()
        if require_usable_value and not _metric_entry_has_usable_value(entry):
            continue
        if canonical in alias_set or metric_id in alias_set:
            return True
        for alias in entry.get("aliases", []) or []:
            if str(alias).strip().lower() in alias_set:
                return True
    return False


def _financial_warning_is_blocked(warning: str, metric_registry: List[Dict[str, Any]]) -> bool:
    lowered = str(warning or "").strip().lower()
    if not lowered:
        return False
    if "fcf missing" in lowered or "free cash flow missing" in lowered:
        return _metric_present_in_registry(metric_registry, ("fcf",), require_usable_value=True)
    if "cfo/pat missing" in lowered:
        return _metric_present_in_registry(metric_registry, ("cfo_to_pat", "cfo", "pat"), require_usable_value=True)
    if "capex missing" in lowered:
        return _metric_present_in_registry(metric_registry, ("capex",), require_usable_value=True)
    if "payables missing" in lowered or "payable days missing" in lowered:
        return _metric_present_in_registry(metric_registry, ("payables", "payable_days"), require_usable_value=True)
    if "roe unavailable" in lowered:
        return _metric_present_in_registry(metric_registry, ("roe",), require_usable_value=True)
    if "roce unavailable" in lowered:
        return _metric_present_in_registry(metric_registry, ("roce",), require_usable_value=True)
    if "share count missing" in lowered:
        return _metric_present_in_registry(
            metric_registry,
            ("shares_outstanding", "share_count", "weighted_avg_shares", "diluted_shares"),
            require_usable_value=True,
        )
    return False


def _rewrite_blocked_financial_warning(warning: str) -> str:
    lowered = str(warning or "").strip().lower()
    for key, replacement in BLOCKED_FINANCIAL_WARNING_REWRITES.items():
        if key in lowered:
            return replacement
    return str(warning or "").strip()


def _build_analyst_financial_truth_pack(selected_pcim: Dict[str, Any], sections: List[str]) -> Dict[str, Any]:
    metric_registry = _build_financial_metric_registry(selected_pcim, sections)
    warnings = _collect_financial_warnings(selected_pcim, sections)
    basis_used = _collect_financial_basis(selected_pcim, sections)
    financial_truth = selected_pcim.get("financial_truth_inputs") or {}
    warning_policy = selected_pcim.get("financial_warning_policy") or {}
    precise_missing_inputs = selected_pcim.get("precise_missing_financial_inputs") or {}
    unreliable_inputs = selected_pcim.get("unreliable_financial_inputs") or {}
    invalid_inputs = selected_pcim.get("invalid_or_quarantined_financial_inputs") or {}
    panel_status = selected_pcim.get("financial_panel_status") or {}
    financial_snapshot = selected_pcim.get("financial_snapshot_inputs") or {}
    owner_earnings = selected_pcim.get("owner_earnings_readiness_inputs") or {}
    working_capital_quality = selected_pcim.get("working_capital_quality_inputs") or {}
    capital_allocation = selected_pcim.get("capital_allocation_financial_inputs") or {}
    per_share_compounding = selected_pcim.get("per_share_compounding_inputs") or {}

    usable_current = _normalize_financial_truth_list(
        financial_truth.get("usable_current_metrics")
        or financial_snapshot.get("usable_current_metrics")
        or _registry_metric_names(metric_registry)
    )
    usable_derived = _normalize_financial_truth_list(
        financial_truth.get("usable_derived_metrics")
        or owner_earnings.get("usable_derived_metrics")
    )
    partial_metrics = _normalize_financial_truth_list(financial_truth.get("partial_metrics"))
    unreliable_metrics = _normalize_financial_truth_list(
        financial_truth.get("unreliable_metrics") or unreliable_inputs.get("metrics")
    )
    invalid_metrics = _normalize_financial_truth_list(
        financial_truth.get("invalid_or_quarantined_metrics") or invalid_inputs.get("metrics")
    )
    precise_missing = _normalize_financial_truth_list(
        financial_truth.get("precise_missing_metrics") or precise_missing_inputs.get("metrics")
    )
    trend_durability_limits = _normalize_financial_truth_list(
        financial_truth.get("trend_durability_limits")
        or financial_snapshot.get("trend_durability_limits")
        or working_capital_quality.get("trend_durability_limits")
        or per_share_compounding.get("trend_durability_limits")
    )
    precision_limits = _normalize_financial_truth_list(
        financial_truth.get("precision_limits")
        or financial_snapshot.get("precision_limits")
        or owner_earnings.get("precision_limits")
        or capital_allocation.get("precision_limits")
    )
    blocked_warning_inputs = _normalize_financial_truth_list(
        warning_policy.get("financial_warnings_blocked_downstream")
        or selected_pcim.get("financial_panel_blocked_domains")
        or []
    )
    allowed_warning_inputs = _normalize_financial_truth_list(
        warning_policy.get("allowed_financial_warnings")
        or warnings
    )
    blocked_warning_inputs.extend(
        warning for warning in warnings if _financial_warning_is_blocked(warning, metric_registry)
    )
    blocked_financial_warnings = _unique_preserve_order(blocked_warning_inputs)
    rewritten_financial_warnings = _unique_preserve_order(
        [_rewrite_blocked_financial_warning(warning) for warning in blocked_financial_warnings]
    )
    allowed_financial_warnings = [
        warning
        for warning in allowed_warning_inputs
        if warning not in blocked_financial_warnings
        and _rewrite_blocked_financial_warning(warning) == warning
    ]
    investor_questions = _normalize_financial_truth_list(
        selected_pcim.get("investor_financial_questions")
        or precise_missing_inputs.get("investor_questions")
        or financial_truth.get("investor_financial_questions")
    )
    source_provenance = _unique_preserve_order(
        [
            str((selected_pcim.get(name) or {}).get("source_artifact") or "").strip()
            for name in (
                "financial_truth_inputs",
                "financial_snapshot_inputs",
                "financial_quality_inputs",
                "owner_earnings_readiness_inputs",
                "working_capital_quality_inputs",
                "capital_allocation_financial_inputs",
                "per_share_compounding_inputs",
                "unreliable_financial_inputs",
                "invalid_or_quarantined_financial_inputs",
                "precise_missing_financial_inputs",
            )
            if str((selected_pcim.get(name) or {}).get("source_artifact") or "").strip()
        ]
    )
    return {
        "usable_current_metrics": usable_current,
        "usable_derived_metrics": usable_derived,
        "partial_metrics": partial_metrics,
        "unreliable_metrics": unreliable_metrics,
        "invalid_or_quarantined_metrics": invalid_metrics,
        "precise_missing_metrics": precise_missing,
        "trend_durability_limits": trend_durability_limits,
        "precision_limits": precision_limits,
        "allowed_financial_warnings": allowed_financial_warnings,
        "blocked_financial_warnings": blocked_financial_warnings,
        "rewritten_financial_warnings": rewritten_financial_warnings,
        "investor_financial_questions": investor_questions,
        "financial_panel_status": panel_status if isinstance(panel_status, dict) else {"status": str(panel_status or "").strip() or "unknown"},
        "source_provenance": source_provenance,
        "basis_used": basis_used,
    }


def _derive_financial_context(selected_pcim: Dict[str, Any], sections: List[str], missing_sections: List[str]) -> Dict[str, Any]:
    financial_sections = _financial_sections_for_doctrine(sections)
    metric_registry = _build_financial_metric_registry(selected_pcim, sections)
    metrics_used = _registry_metric_names(metric_registry)
    warnings = _collect_financial_warnings(selected_pcim, sections)
    basis_used = _collect_financial_basis(selected_pcim, sections)
    truth_pack = _build_analyst_financial_truth_pack(selected_pcim, sections)
    missing_data: List[str] = []
    interpretation_limits: List[str] = []
    metric_flags = _financial_context_metric_flags({"metrics_used": metrics_used, "metric_registry": metric_registry})

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
        if not metric_flags["has_any_share_count"]:
            missing_data.append("share count missing")
        else:
            if not metric_flags["has_shares_outstanding"]:
                interpretation_limits.append(
                    "Closing shares are missing; dividend-per-share and book-value-per-share derivations remain limited."
                )
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

    for warning in truth_pack["allowed_financial_warnings"]:
        lowered = warning.lower()
        if "share count missing" in lowered and metric_flags["has_any_share_count"]:
            continue
        if any(token in lowered for token in ("basis", "share count", "weighted average shares", "diluted shares", "comparability", "fcf", "capex", "debt", "dilution", "qip", "payables", "payable days", "cash conversion cycle")):
            interpretation_limits.append(warning)

    return {
        "financials_used": bool(financial_sections),
        "basis_used": basis_used,
        "financial_sections_consumed": financial_sections,
        "warnings": list(truth_pack["allowed_financial_warnings"]),
        "blocked_warnings": list(truth_pack["blocked_financial_warnings"]),
        "rewritten_warnings": list(truth_pack["rewritten_financial_warnings"]),
        "metrics_used": metrics_used,
        "metric_registry": metric_registry,
        "missing_data": list(dict.fromkeys(missing_data)),
        "interpretation_limits": list(dict.fromkeys(interpretation_limits)),
        "truth_pack": truth_pack,
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
        "- Do not treat dividends, related-party advances, or governance ambiguity as automatic condemnation without context from supplied evidence.",
    ]
    doctrine_specific = {
        "graham": [
            "- Focus on balance-sheet strength, debt/equity, net cash or debt, cash conversion, dividend safety, working-capital risk, and reconciliation or audit warnings.",
            "- If share count, FCF, capex, basis, or debt mapping is missing or warning-heavy, say so explicitly.",
            "- Do not treat dividends as a red flag by default.",
            "- If dividend or distribution evidence lacks cash-flow and leverage context, describe the limitation rather than forcing a harsher conclusion.",
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
            "- For related-party or governance ambiguity, use monitoring signals first and escalate only when evidence supports it.",
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
    truth_pack = financial_context["truth_pack"]
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
        "precise_missing_financial_data": list(truth_pack["precise_missing_metrics"]),
        "derived_not_explicitly_reported": list(truth_pack["usable_derived_metrics"]),
        "partial_financial_data": list(truth_pack["partial_metrics"]),
        "unreliable_financial_data": list(truth_pack["unreliable_metrics"]),
        "invalid_or_quarantined_financial_data": list(truth_pack["invalid_or_quarantined_metrics"]),
        "trend_durability_limits": list(truth_pack["trend_durability_limits"]),
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
        "financial_questions_for_investor": list(truth_pack["investor_financial_questions"]),
        "analyst_financial_truth_pack": truth_pack,
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
    always_include = {
        "financial_truth_inputs",
        "financial_snapshot_inputs",
        "owner_earnings_readiness_inputs",
        "working_capital_quality_inputs",
        "capital_allocation_financial_inputs",
        "per_share_compounding_inputs",
        "unreliable_financial_inputs",
        "invalid_or_quarantined_financial_inputs",
        "precise_missing_financial_inputs",
        "financial_warning_policy",
        "financial_panel_status",
        "financial_panel_usable_domains",
        "financial_panel_limited_domains",
        "financial_panel_blocked_domains",
        "investor_financial_questions",
    }
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
    for section in always_include:
        if section not in selected and section in pcim:
            selected[section] = pcim.get(section)
    return selected


def _doctrine_priority_order(doctrine_id: str, sections: List[str]) -> List[str]:
    preferred = DOCTRINE_SECTION_PRIORITIES.get(doctrine_id, [])
    ordered: List[str] = []
    for section in preferred:
        if section in sections and section not in ordered:
            ordered.append(section)
    for section in sections:
        if section not in ordered:
            ordered.append(section)
    return ordered


def compact_financial_truth_for_analyst(
    financial_truth_inputs: Any,
    analyst: str,
    *,
    token_budget: int,
) -> Dict[str, Any]:
    if not isinstance(financial_truth_inputs, dict):
        return {
            "analyst": analyst,
            "top_usable_metrics": [],
            "top_derived_metrics": [],
            "allowed_warnings": [],
            "blocked_warnings": [],
            "investor_questions": [],
            "owner_earnings_status": "unknown",
            "working_capital_status": "unknown",
            "per_share_status": "unknown",
            "basis_status": "unknown",
            "debt_reliability_status": "unknown",
            "source_provenance_summary": [],
        }

    metric_limit = 12
    derived_limit = 6
    warning_limit = 6
    question_limit = 5
    if token_budget < 350:
        metric_limit = 8
        derived_limit = 4
        warning_limit = 4
        question_limit = 3

    def _compact_metric(item: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        label = _truncate_text(
            str(item.get("metric_name") or item.get("display_name") or item.get("metric_id") or item.get("canonical_metric") or "").strip(),
            60,
        )
        if not label:
            return None
        compact: Dict[str, Any] = {
            "metric": label,
            "period": _truncate_text(str(item.get("fiscal_year") or item.get("period") or "").strip(), 20),
            "basis": _truncate_text(str(item.get("basis") or "unknown").strip(), 20),
            "confidence": _truncate_text(str(item.get("confidence") or "unknown").strip(), 20),
        }
        for key in ("value", "value_crore", "value_per_share", "raw_number"):
            value = item.get(key)
            if isinstance(value, (int, float)):
                compact["value"] = value
                break
        note = ""
        if isinstance(item.get("notes"), list) and item.get("notes"):
            note = str(item["notes"][0])
        elif isinstance(item.get("warnings"), list) and item.get("warnings"):
            note = str(item["warnings"][0])
        if note:
            compact["note"] = _truncate_text(note, 160)
        return compact

    def _latest_first(values: Any, limit: int) -> List[Dict[str, Any]]:
        compacted = [item for item in (_compact_metric(value) for value in values or []) if item]
        compacted.sort(key=lambda item: _financial_period_sort_key(item.get("period")), reverse=True)
        return compacted[:limit]

    usable = _latest_first(financial_truth_inputs.get("usable_current_metrics", []), metric_limit)
    derived = _latest_first(financial_truth_inputs.get("usable_derived_metrics", []), derived_limit)
    partial = _latest_first(financial_truth_inputs.get("partial_metrics", []), 4)
    derived_not_reported = _latest_first(
        financial_truth_inputs.get("derived_not_explicitly_reported", []),
        derived_limit,
    )

    metric_blob = json.dumps(usable + derived + partial + derived_not_reported, ensure_ascii=False).lower()
    owner_earnings_status = "available" if "owner earnings" in metric_blob or "owner_earnings" in metric_blob else "unknown"
    working_capital_status = "available" if any(token in metric_blob for token in ("receivable", "inventory", "payable", "cash conversion")) else "unknown"
    per_share_status = "available" if any(token in metric_blob for token in ("eps", "book value", "share")) else "unknown"
    debt_reliability_status = "available" if any(token in metric_blob for token in ("debt", "cash", "net worth")) else "unknown"

    blocked_warning_summaries = []
    for item in financial_truth_inputs.get("financial_warnings_blocked_downstream", []) or []:
        if isinstance(item, dict):
            blocked_warning_summaries.append(item.get("normalized_warning") or item.get("original_warning") or "")
        else:
            blocked_warning_summaries.append(str(item))

    return {
        "analyst": analyst,
        "top_usable_metrics": usable,
        "top_derived_metrics": derived,
        "partial_metrics": partial,
        "derived_not_explicitly_reported": derived_not_reported,
        "allowed_warnings": _extract_summary_fragments(
            financial_truth_inputs.get("financial_warnings_allowed_downstream", []),
            max_items=warning_limit,
            item_limit=160,
        ),
        "blocked_warnings": _extract_summary_fragments(
            blocked_warning_summaries,
            max_items=warning_limit,
            item_limit=160,
        ),
        "investor_questions": _extract_summary_fragments(
            financial_truth_inputs.get("investor_financial_questions") or financial_truth_inputs.get("investor_relevant_questions") or [],
            max_items=question_limit,
            item_limit=160,
        ),
        "owner_earnings_status": owner_earnings_status,
        "working_capital_status": working_capital_status,
        "per_share_status": per_share_status,
        "basis_status": _truncate_text(str(financial_truth_inputs.get("financial_panel_status_reason") or financial_truth_inputs.get("financial_panel_status") or "unknown"), 120),
        "debt_reliability_status": debt_reliability_status,
        "source_provenance_summary": _extract_summary_fragments(
            financial_truth_inputs.get("source_provenance", []),
            max_items=4,
            item_limit=120,
        ),
    }


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
    if section_name == "financial_truth_inputs":
        return compact_financial_truth_for_analyst(
            section_value,
            analyst,
            token_budget=DEFAULT_FINANCIAL_TRUTH_PACK_BUDGET_TOKENS,
        )
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
    *,
    include_sections: Optional[List[str]] = None,
    excluded_sections: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], bool]:
    selected_pcim = _selected_pcim_view(pcim, include_sections or sections)
    compacted: Dict[str, Any] = {}
    stats: Dict[str, Dict[str, Any]] = {}
    truncated = False
    excluded = list(excluded_sections or [])

    for section, value in selected_pcim.items():
        if section in FINANCIAL_PCIM_SECTIONS:
            value = _prioritize_recent_financial_items(value)
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

    if excluded:
        compacted["available_but_not_included_due_budget"] = {
            "analyst": analyst,
            "sections": excluded[:8],
            "count": len(excluded),
        }

    return compacted, stats, truncated


def _prioritize_recent_financial_items(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _prioritize_recent_financial_items(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        prioritized = [_prioritize_recent_financial_items(item) for item in value]
        dated_items = [
            item
            for item in prioritized
            if isinstance(item, dict)
            and _financial_period_sort_key(
                item.get("fiscal_year") or item.get("year") or item.get("period") or item.get("source_year")
            )[0] >= 0
        ]
        if dated_items and len(dated_items) == len(prioritized):
            prioritized.sort(
                key=lambda item: _financial_period_sort_key(
                    item.get("fiscal_year") or item.get("year") or item.get("period") or item.get("source_year")
                ),
                reverse=True,
            )
        return prioritized
    return value


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


def _token_usage_by_budget_class(
    *,
    system_instructions: str,
    analyst_doctrine_instructions: str,
    output_schema_or_contract: str,
    compact_pcim_input_pack: Any,
    compact_financial_truth_pack: Any,
    compact_evidence_pack: Any,
    warning_policy_pack: Any,
) -> Dict[str, int]:
    return {
        "system_instructions": _estimate_prompt_tokens(system_instructions),
        "analyst_doctrine_instructions": _estimate_prompt_tokens(analyst_doctrine_instructions),
        "output_schema_or_contract": _estimate_prompt_tokens(output_schema_or_contract),
        "compact_pcim_input_pack": _estimate_prompt_tokens(json.dumps(compact_pcim_input_pack, ensure_ascii=False)),
        "compact_financial_truth_pack": _estimate_prompt_tokens(json.dumps(compact_financial_truth_pack, ensure_ascii=False)),
        "compact_evidence_pack": _estimate_prompt_tokens(json.dumps(compact_evidence_pack, ensure_ascii=False)),
        "warning_policy_pack": _estimate_prompt_tokens(json.dumps(warning_policy_pack, ensure_ascii=False)),
    }


def _compact_evidence_subset(
    compact_pcim: Dict[str, Any],
    *,
    token_budget: int,
) -> Dict[str, Any]:
    evidence_map = compact_pcim.get("evidence_map") or {}
    if not isinstance(evidence_map, dict):
        return {}
    subset: Dict[str, Any] = {}
    for section, value in evidence_map.items():
        ids: List[str] = []
        if isinstance(value, dict):
            ids = [str(item).strip() for item in value.get("sample_evidence_ids", []) if str(item).strip()]
        elif isinstance(value, list):
            ids = [str(item).strip() for item in value if str(item).strip()]
        if ids:
            subset[section] = ids[:8]
    if _estimate_prompt_tokens(json.dumps(subset, ensure_ascii=False)) <= token_budget:
        return subset
    ids_only: List[str] = []
    for ids in subset.values():
        for evidence_id in ids:
            if evidence_id not in ids_only:
                ids_only.append(evidence_id)
    compact = {"evidence_ids": ids_only[:8], "evidence_text_omitted_due_budget": True}
    while _estimate_prompt_tokens(json.dumps(compact, ensure_ascii=False)) > token_budget and len(compact["evidence_ids"]) > 3:
        compact["evidence_ids"] = compact["evidence_ids"][:-1]
    return compact


def _build_emergency_prompt_payload(
    *,
    company: str,
    doctrine: Dict[str, Any],
    compact_pcim: Dict[str, Any],
    excluded_sections: List[str],
) -> Dict[str, Any]:
    years = _collect_years_from_value(compact_pcim)[:4]
    top_business = _extract_summary_fragments(
        [
            compact_pcim.get("business_understanding"),
            compact_pcim.get("business_economics_inputs"),
            compact_pcim.get("management_quality_inputs"),
            compact_pcim.get("moat_inputs"),
        ],
        max_items=3,
        item_limit=150,
    )
    top_financial = _extract_summary_fragments(
        [
            compact_pcim.get("financial_truth_inputs"),
            compact_pcim.get("financial_quality_inputs"),
            compact_pcim.get("cash_conversion_inputs"),
            compact_pcim.get("return_on_capital_inputs"),
        ],
        max_items=3,
        item_limit=150,
    )
    top_risks = _extract_summary_fragments(
        [compact_pcim.get("risk_inputs"), compact_pcim.get("financial_quality_inputs")],
        max_items=3,
        item_limit=150,
    )
    top_uncertainties = _extract_summary_fragments(
        [
            compact_pcim.get("uncertainty_missing_data"),
            compact_pcim.get("investor_financial_questions"),
            compact_pcim.get("financial_warning_policy"),
        ],
        max_items=3,
        item_limit=150,
    )
    evidence_subset = _compact_evidence_subset(compact_pcim, token_budget=DEFAULT_EVIDENCE_PACK_BUDGET_TOKENS)
    top_evidence_ids = []
    if isinstance(evidence_subset, dict):
        ids = evidence_subset.get("evidence_ids")
        if isinstance(ids, list):
            top_evidence_ids = ids[:8]
        else:
            for value in evidence_subset.values():
                if isinstance(value, list):
                    for evidence_id in value:
                        if evidence_id not in top_evidence_ids:
                            top_evidence_ids.append(evidence_id)
    return {
        "company": company,
        "available_years": years,
        "doctrine_id": doctrine["doctrine_id"],
        "compact_financial_truth_summary": compact_pcim.get("financial_truth_inputs") or {},
        "top_business_facts": top_business[:3],
        "top_financial_facts": top_financial[:3],
        "top_risks": top_risks[:3],
        "top_uncertainties": top_uncertainties[:3],
        "top_evidence_ids": top_evidence_ids[:8],
        "omitted_sections_summary": excluded_sections[:8],
        "required_output_contract": {
            "rating": "strong|mixed|weak|insufficient_evidence",
            "must_include": [
                "assessment",
                "key_findings",
                "red_flags",
                "open_uncertainties",
                "financial_assessment",
                "user_facing_brief",
            ],
        },
    }


def _prepare_compact_prompt_pack(
    pcim: Dict[str, Any],
    sections: List[str],
    analyst: str,
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], Dict[str, int], bool, Dict[str, Any]]:
    limits = _prompt_compaction_limits()
    ordered_sections = _doctrine_priority_order(analyst, sections)
    include_count = len(ordered_sections)
    excluded_sections: List[str] = []
    shrink_passes = 0
    emergency_mode_used = False
    sections_dropped_due_budget: List[str] = []

    while True:
        include_sections = ordered_sections[:include_count]
        excluded_sections = ordered_sections[include_count:]
        compacted_pcim, stats, truncated = _build_compact_pcim_view(
            pcim,
            sections,
            limits,
            analyst,
            include_sections=include_sections,
            excluded_sections=excluded_sections,
        )
        compact_chars = len(json.dumps(compacted_pcim, ensure_ascii=False))
        compact_tokens = _estimate_prompt_tokens(json.dumps(compacted_pcim, ensure_ascii=False))
        if (
            compact_chars <= limits["max_total_prompt_chars"]
            and compact_tokens <= limits["compact_input_pack_budget_tokens"]
        ):
            diagnostics = {
                "included_sections": include_sections,
                "excluded_sections": excluded_sections,
                "shrink_passes_applied": shrink_passes,
                "emergency_mode_used": emergency_mode_used,
                "sections_dropped_due_budget": sections_dropped_due_budget,
                "compact_input_pack_tokens": compact_tokens,
            }
            return compacted_pcim, stats, limits, truncated, diagnostics
        if include_count > 3:
            dropped = ordered_sections[include_count - 1]
            include_count -= 1
            if dropped not in sections_dropped_due_budget:
                sections_dropped_due_budget.append(dropped)
            shrink_passes += 1
            continue
        next_limits = _shrink_limits(limits)
        if next_limits is None:
            emergency_payload = _build_emergency_prompt_payload(
                company=str(pcim.get("company") or ""),
                doctrine={"doctrine_id": analyst},
                compact_pcim=compacted_pcim,
                excluded_sections=excluded_sections or sections_dropped_due_budget,
            )
            diagnostics = {
                "included_sections": ["emergency_skeleton"],
                "excluded_sections": excluded_sections,
                "shrink_passes_applied": shrink_passes,
                "emergency_mode_used": True,
                "sections_dropped_due_budget": sections_dropped_due_budget,
                "compact_input_pack_tokens": compact_tokens,
            }
            return emergency_payload, stats, limits, True, diagnostics
        limits = next_limits
        if limits["max_items_per_section"] == 1:
            emergency_mode_used = True
        shrink_passes += 1


def _build_compact_prompt(
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    pcim: Dict[str, Any],
    sections: List[str],
) -> Tuple[str, Dict[str, Any], Dict[str, Dict[str, int]], Dict[str, int], bool, Dict[str, Any]]:
    limits_used = _prompt_compaction_limits()
    stage_budget = max(
        resolve_stage_token_budget("investor_panel_analyst"),
        limits_used["total_prompt_budget_tokens"],
    )
    reserved_system_tokens = limits_used["reserved_system_tokens"]
    reserved_instruction_tokens = limits_used["reserved_instruction_tokens"]
    reserved_output_schema_tokens = limits_used["reserved_output_schema_tokens"]
    available_input_pack_tokens = limits_used["compact_input_pack_budget_tokens"]
    raw_selected_pcim = _selected_pcim_view(pcim, sections)
    raw_largest_sections = _largest_offending_fields(raw_selected_pcim)
    # Compute required warning groups from the full PCIM so metrics dropped during
    # compaction do not falsely trigger missing-data groups in the analyst prompt.
    # (The compact PCIM can lose canonical metric IDs like "capex" while retaining
    # only derived IDs, making an otherwise-available metric appear absent.)
    _full_required_warning_groups = _canonical_required_financial_warning_groups(
        _derive_financial_context(raw_selected_pcim, sections, [])
    )[:8]
    compact_pcim, section_stats, limits_used, input_compacted, pack_diagnostics = _prepare_compact_prompt_pack(
        pcim,
        sections,
        doctrine["doctrine_id"],
    )
    if "financial_truth_inputs" in compact_pcim:
        compact_pcim["financial_truth_inputs"] = compact_financial_truth_for_analyst(
            compact_pcim["financial_truth_inputs"],
            doctrine["doctrine_id"],
            token_budget=limits_used["financial_truth_pack_budget_tokens"],
        )
    if "evidence_map" in compact_pcim:
        compact_pcim["evidence_map"] = _compact_evidence_subset(
            compact_pcim,
            token_budget=limits_used["evidence_pack_budget_tokens"],
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
        required_warning_groups=_full_required_warning_groups,
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
        input_pack_over_cap = pack_tokens > limits_used["compact_input_pack_budget_tokens"]
        hard_char_limit = limits_used.get("hard_max_prompt_chars") or 0
        over_hard_char_limit = bool(hard_char_limit and prompt_chars > hard_char_limit)
        if (
            prompt_tokens <= stage_budget
            and prompt_tokens <= limits_used["hard_max_prompt_tokens"]
            and pack_tokens <= stage_budget
            and not input_pack_over_cap
            and not over_hard_char_limit
        ):
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
        if "financial_truth_inputs" in compact_pcim:
            compact_pcim["financial_truth_inputs"] = compact_financial_truth_for_analyst(
                compact_pcim["financial_truth_inputs"],
                doctrine["doctrine_id"],
                token_budget=limits_used["financial_truth_pack_budget_tokens"],
            )
        if "evidence_map" in compact_pcim:
            compact_pcim["evidence_map"] = _compact_evidence_subset(
                compact_pcim,
                token_budget=limits_used["evidence_pack_budget_tokens"],
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
            required_warning_groups=_full_required_warning_groups,
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
    budget_classes = _token_usage_by_budget_class(
        system_instructions=_build_system_prompt(),
        analyst_doctrine_instructions=json.dumps(
            {
                "primary_focus": doctrine.get("primary_focus", [])[:4],
                "financial_rules": _financial_instruction_block(doctrine["doctrine_id"])[:4],
                "evidence_routing": _shared_evidence_routing_rules(),
            },
            ensure_ascii=False,
        ),
        output_schema_or_contract=json.dumps(_llm_output_template(doctrine, sections), ensure_ascii=False),
        compact_pcim_input_pack=((llm_input_pack.get("observations") or [{}])[0].get("selected_pcim") or {}),
        compact_financial_truth_pack=compact_pcim.get("financial_truth_inputs") or {},
        compact_evidence_pack=compact_pcim.get("evidence_map") or {},
        warning_policy_pack={"required_warning_groups": _canonical_required_financial_warning_groups(_derive_financial_context(compact_pcim, sections, []))[:8]},
    )
    hard_char_limit = limits_used.get("hard_max_prompt_chars") or 0
    over_hard_char_limit = bool(hard_char_limit and prompt_chars > hard_char_limit)
    warnings: List[str] = []
    budget_status = "pass"
    if prompt_chars > limits_used["max_total_prompt_chars"]:
        budget_status = "pass_with_warning"
        warnings.append("prompt_chars exceeded soft target but token budget passed")
    if pack_tokens > limits_used["compact_input_pack_budget_tokens"]:
        warnings.append("compact input pack remained above hard sub-budget before final fallback")
    if (
        prompt_tokens > stage_budget
        or prompt_tokens > limits_used["hard_max_prompt_tokens"]
        or pack_tokens > stage_budget
        or pack_tokens > limits_used["compact_input_pack_budget_tokens"]
        or over_hard_char_limit
        or section_cap_violations
    ):
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
        "reserved_system_tokens": reserved_system_tokens,
        "reserved_instruction_tokens": reserved_instruction_tokens,
        "reserved_output_schema_tokens": reserved_output_schema_tokens,
        "available_input_pack_tokens": available_input_pack_tokens,
        "total_prompt_budget_tokens": limits_used["total_prompt_budget_tokens"],
        "hard_max_prompt_tokens": limits_used["hard_max_prompt_tokens"],
        "compact_input_pack_budget_tokens": limits_used["compact_input_pack_budget_tokens"],
        "financial_truth_pack_budget_tokens": limits_used["financial_truth_pack_budget_tokens"],
        "evidence_pack_budget_tokens": limits_used["evidence_pack_budget_tokens"],
        "doctrine_context_budget_tokens": limits_used["doctrine_context_budget_tokens"],
        "prompt_tokens_before": initial_prompt_tokens,
        "prompt_tokens_after": prompt_tokens,
        "pack_tokens_before": initial_pack_tokens,
        "pack_tokens_after": pack_tokens,
        "prompt_chars_before": initial_prompt_chars,
        "prompt_chars_after": prompt_chars,
        "raw_largest_sections": raw_largest_sections,
        "compacted_largest_sections": compacted_largest_sections,
        "raw_section_tokens": {
            key: _estimate_prompt_tokens(json.dumps(value, ensure_ascii=False))
            for key, value in raw_selected_pcim.items()
        },
        "compacted_section_tokens": {
            key: _estimate_prompt_tokens(json.dumps(value, ensure_ascii=False))
            for key, value in compact_pcim.items()
        },
        "section_caps": {
            section: stats["section_cap"]
            for section, stats in section_stats.items()
        },
        "included_sections": list(pack_diagnostics.get("included_sections", [])),
        "excluded_sections": list(pack_diagnostics.get("excluded_sections", [])),
        "shrink_passes_applied": int(pack_diagnostics.get("shrink_passes_applied", 0)),
        "emergency_mode_used": bool(pack_diagnostics.get("emergency_mode_used", False)),
        "sections_dropped_due_budget": list(pack_diagnostics.get("sections_dropped_due_budget", [])),
        "token_usage_by_budget_class": budget_classes,
        "evidence_map_included": "evidence_map" in compact_pcim,
        "evidence_map_tokens": _estimate_prompt_tokens(json.dumps(compact_pcim.get("evidence_map") or {}, ensure_ascii=False)),
        "financial_truth_tokens": _estimate_prompt_tokens(json.dumps(compact_pcim.get("financial_truth_inputs") or {}, ensure_ascii=False)),
        "static_instruction_tokens": budget_classes["system_instructions"] + budget_classes["analyst_doctrine_instructions"],
        "output_schema_tokens": budget_classes["output_schema_or_contract"],
        "omitted_evidence_count": max(0, len(_collect_section_evidence_ids(pcim, sections)) - len(_collect_section_evidence_ids(compact_pcim, list(compact_pcim.keys())))),
        "evidence_compaction_note": "Only evidence IDs reachable from included compact sections are passed to the analyst prompt.",
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
    company_memory_context = build_company_memory_context(
        pcim_path.parent.parent,
        doctrine["doctrine_id"],
        token_budget=limits_used["doctrine_context_budget_tokens"],
    )
    limitations = [COMPACTION_REASONING_LIMIT] if input_compacted else []
    limitations.extend(company_memory_context.get("limitations") or [])
    limitations = list(dict.fromkeys(limitations))
    financial_truth_summary = compact_pcim.get("financial_truth_inputs") if isinstance(compact_pcim, dict) else {}
    evidence_subset = _compact_evidence_subset(
        compact_pcim if isinstance(compact_pcim, dict) else {},
        token_budget=limits_used["evidence_pack_budget_tokens"],
    )
    max_dict_keys = max(
        limits_used["max_dict_keys_per_item"],
        len(allowed_sections) + 2,
    )
    max_sections = max(
        limits_used["max_sections"],
        len(allowed_sections) + 1,
    )
    pack = build_llm_input_pack(
        stage="investor_panel_analyst",
        purpose=(
            f"Produce doctrine-bound investor analysis for {doctrine['doctrine_id']} from declared PCIM sections, "
            "structured management synthesis chains, and longitudinal company-memory summaries only."
        ),
        company=company,
        year=None,
        observations=[
            {
                "selected_pcim": compact_pcim,
                "company_memory_context": company_memory_context,
                "financial_truth_summary": financial_truth_summary,
                "evidence_subset": evidence_subset,
            }
        ],
        limitations=limitations,
        source_artifacts=[str(pcim_path)],
        pack_name=f"{doctrine['doctrine_id']}_input_pack",
        policy={
            "allowed_sections": ["selected_pcim", "company_memory_context"],
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
    pack["financial_truth_summary_for_prompt"] = financial_truth_summary
    pack["evidence_subset_for_prompt"] = evidence_subset
    pack["company_memory_context_for_prompt"] = company_memory_context
    return pack


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
        "Reason only from the supplied PCIM sections, company-memory progression summaries, and doctrine configuration. "
        "Do not use outside knowledge, do not invent evidence, and do not make buy/sell/hold recommendations. "
        "Treat company-memory streams as longitudinal evidence, not a snapshot scorecard. "
        "Do not treat ambition, commissioning, or a management statement as delivered execution without later evidence. "
        "Return exactly one valid JSON object matching the requested schema."
    )


def _shared_evidence_routing_rules() -> List[str]:
    return [
        "Evidence routing:",
        "- Revenue, CFO, receivable, debt, and similar financial claims should rely on financial_metrics_used, matching financial evidence, or both.",
        "- Treat the latest fiscal year in the supplied financial truth as the current baseline; include latest-year metrics before using older years as trend context.",
        "- Governance, integrity, and incentive claims must use governance, ownership, compensation, board, committee, related-party, capital-allocation, or explicit uncertainty evidence.",
        "- Market-risk evidence supports only FX, currency, interest-rate, or market-risk claims unless risk oversight is explicit.",
        "- Section names and JSON filenames are never valid evidence IDs.",
        "- If stronger evidence is missing, downgrade the claim into a limitation rather than forcing unrelated evidence IDs.",
    ]


def _management_synthesis_chain_rules() -> List[str]:
    return [
        "Management synthesis-chain rules:",
        "- Use company_memory_context.management progression.synthesis_chains as the source of truth for claim/action/outcome/financial-link state.",
        "- CLAIM_ONLY is statement evidence only; it is not execution, delivery, capital-allocation success, or realized operating outcome evidence.",
        "- ACTION_STARTED means action began; do not claim completion, outcome, or financial impact unless later chain fields prove it.",
        "- ACTION_COMPLETED means completion occurred; completion alone is not evidence of value creation or a positive operating outcome.",
        "- OUTCOME_POSITIVE and OUTCOME_NEGATIVE require separately evidenced operating or financial results.",
        "- If actor is regulator, customer, partner, market, other, or unknown, do not describe the action as management-initiated unless separate management-action evidence is present.",
        "- If financial_link_status is not confirmed, say the economic consequence remains unproven.",
    ]


def _doctrine_differentiation_block(doctrine_id: str) -> Dict[str, Any]:
    guidance = DOCTRINE_DIFFERENTIATION_GUIDANCE.get(doctrine_id, {})
    if not guidance:
        return {}
    return {
        "primary_doctrine_question": guidance.get("primary_doctrine_question"),
        "shared_fact_interpretation": {
            "capex": (guidance.get("shared_fact_interpretation") or {}).get("capex"),
        },
        "must_prioritize": list(guidance.get("must_prioritize") or [])[:3],
    }


def _doctrine_differentiation_rules(doctrine_id: str) -> List[str]:
    guidance = _doctrine_differentiation_block(doctrine_id)
    if not guidance:
        return []
    return [
        "Doctrine differentiation:",
        "- Make the doctrine-specific causal question visible.",
        "- Shared facts are allowed, but interpret them through this doctrine's mechanism.",
        "- Do not force disagreement; agree only when this lens supports it.",
        "- Downweight generic facts unless they answer this doctrine's primary question.",
        "- Translate internal labels into investor-usable implications.",
        f"- Primary doctrine question: {guidance.get('primary_doctrine_question')}",
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
    *,
    required_warning_groups: Optional[List[Dict[str, Any]]] = None,
) -> str:
    compact_pack = deepcopy(llm_input_pack)
    compact_pack.pop("input_policy", None)
    compact_pack.pop("company_memory_context_for_prompt", None)
    compact_pack.pop("financial_truth_summary_for_prompt", None)
    compact_pack.pop("evidence_subset_for_prompt", None)
    first_observation = (llm_input_pack.get("observations") or [{}])[0]
    compact_selected_pcim = first_observation.get("selected_pcim") or {}
    compact_financial_truth_summary = (
        llm_input_pack.get("financial_truth_summary_for_prompt")
        or first_observation.get("financial_truth_summary")
        or compact_selected_pcim.get("financial_truth_inputs")
        or {}
    )
    evidence_subset = _compact_evidence_subset(
        compact_selected_pcim,
        token_budget=DEFAULT_EVIDENCE_PACK_BUDGET_TOKENS,
    )
    warning_policy_pack = {
        "required_warning_groups": (
            required_warning_groups
            if required_warning_groups is not None
            else _canonical_required_financial_warning_groups(
                _derive_financial_context(
                    compact_selected_pcim,
                    allowed_sections,
                    [],
                )
            )[:8]
        )
    }
    compact_company_memory_context = (
        llm_input_pack.get("company_memory_context_for_prompt")
        or first_observation.get("company_memory_context")
        or {}
    )
    compact_pack["observations"] = [
        {
            "selected_pcim": compact_selected_pcim,
            "company_memory_context": compact_company_memory_context,
        }
    ]
    compact_pack["evidence_subset"] = evidence_subset
    compact_pack["warning_policy_pack"] = warning_policy_pack
    compact_pack_text = json.dumps(compact_pack, ensure_ascii=False, separators=(",", ":"))
    compact_shape_text = json.dumps(
        {
            "assessment": "object with doctrine-required strings",
            "rating": "strong|mixed|weak|insufficient_evidence",
            "key_findings": [{"finding": "string", "evidence_ids": ["string"]}],
            "red_flags": [{"flag": "string", "severity": "low|medium|high", "evidence_ids": ["string"]}],
            "open_uncertainties": [{"uncertainty": "string", "evidence_ids": ["string"]}],
            "financial_metrics_used": [{"metric_id": "string", "metric": "string", "period": "string", "used_for": "string"}],
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
            "reasoning_limits": ["string"],
            "user_facing_brief": {
                "title": "string",
                "lens": "string",
                "what_looks_good": ["string"],
                "what_needs_caution": ["string"],
                "what_is_missing": ["string"],
                "financial_lens": "string",
                "bottom_line": "string",
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    metric_registry = _build_financial_metric_registry(compact_selected_pcim, allowed_sections)
    rules = [
        "Use only provided PCIM facts.",
        "Return one valid JSON object only.",
        "Do not invent evidence_ids, facts, metrics, or ratios.",
        "Do not calculate new ratios, owner earnings, margin of safety, or valuation.",
        "Carry forward major financial warnings and missing-data limits.",
        "If FCF/capex/share-count/basis data is missing, say so explicitly.",
        "Do not treat dividends, related-party advances, or governance ambiguity as automatic condemnation without context.",
        "Do not upgrade a management claim into execution, a completed action into a positive outcome, or an unconfirmed chain into financial impact.",
        "No buy, sell, hold, target price, fair value, undervalued, or overvalued language.",
        "Never mention internal system names such as PCIM, CIM, artifact, JSON, evidence IDs, source artifacts, input sections, schema, validation, prompt, or LLM wording.",
        "Write as an investment analyst speaking to a human reader, not as a pipeline describing its internals.",
    ]
    doctrine_block = {
        "doctrine_id": doctrine["doctrine_id"],
        "investor_lens": doctrine["investor_lens"],
        "primary_focus": doctrine.get("primary_focus", [])[:4],
        "financial_rules": _financial_instruction_block(doctrine["doctrine_id"])[:12],
        "doctrine_differentiation": _doctrine_differentiation_block(doctrine["doctrine_id"]),
        "canonical_questions": doctrine.get("canonical_questions", [])[:4],
        "red_flags": doctrine.get("red_flags", [])[:4],
        "uncertainty_rules": doctrine.get("uncertainty_rules", [])[:4],
    }
    return "\n".join(
        [
            f"Company: {company}",
            f"Doctrine ID: {doctrine['doctrine_id']}",
            f"Investor Lens: {doctrine['investor_lens']}",
            "Task: Produce structured investor analysis from compact PCIM and company-memory synthesis chains.",
            "Rules:",
            *[f"- {rule}" for rule in rules],
            *_shared_evidence_routing_rules(),
            *_management_synthesis_chain_rules(),
            *_doctrine_differentiation_rules(doctrine["doctrine_id"]),
            "Allowed supporting_pcim_sections:",
            json.dumps(allowed_sections, ensure_ascii=False, separators=(",", ":")),
            "Allowed Financial Metrics:",
            json.dumps(
                _format_allowed_financial_metrics(metric_registry),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "List-shape rule: all list fields must be valid JSON arrays, never a single string.",
            "Major Financial Warnings To Carry Forward:",
            json.dumps(warning_policy_pack, ensure_ascii=False, separators=(",", ":")),
            "Doctrine context:",
            json.dumps(doctrine_block, ensure_ascii=False, separators=(",", ":")),
            "Compact financial truth:",
            json.dumps(compact_financial_truth_summary, ensure_ascii=False, separators=(",", ":")),
            "Required JSON shape:",
            compact_shape_text,
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


def _preferred_metric_matches(metric_text: str, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_metric = _normalize_metric_label(metric_text)
    preferred_canonical: List[str] = []
    if normalized_metric == _normalize_metric_label("closing shares"):
        preferred_canonical = ["shares_outstanding"]
    elif normalized_metric == _normalize_metric_label("owner-earnings estimate (derived)"):
        preferred_canonical = ["owner_earnings_estimate"]
    elif normalized_metric == _normalize_metric_label("identified capex (total)"):
        preferred_canonical = ["total_identified_capex"]
    elif normalized_metric == _normalize_metric_label("capex deployed (capital allocation ledger)"):
        preferred_canonical = ["capex_deployed"]
    elif normalized_metric == _normalize_metric_label("conservative fcf"):
        preferred_canonical = ["conservative_fcf_after_total_capex"]
    if not preferred_canonical:
        return matches
    preferred = [match for match in matches if str(match.get("canonical_metric") or "") in preferred_canonical]
    return preferred or matches


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
            "canonical_metric_id": entry["metric_id"],
            "canonical_metric_name": entry["canonical_metric"],
            "original_metric_label": str(item.get("metric") or metric_id).strip(),
            "normalization_status": "exact_metric_id_match",
            "period": entry.get("period"),
            "used_for": item.get("used_for") or "unspecified",
            "source_file": entry.get("source_file") or "",
            "source_field": entry.get("source_field") or "",
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
    unique_matches = _preferred_metric_matches(metric_text, unique_matches)
    if len(unique_matches) == 1:
        entry = unique_matches[0]
        return {
            "metric_id": entry["metric_id"],
            "metric": entry["canonical_metric"],
            "canonical_metric_id": entry["metric_id"],
            "canonical_metric_name": entry["canonical_metric"],
            "original_metric_label": metric_text,
            "normalization_status": "alias_match",
            "period": entry.get("period"),
            "used_for": item.get("used_for") or "unspecified",
            "source_file": entry.get("source_file") or "",
            "source_field": entry.get("source_field") or "",
        }, f"financial metric canonicalized via alias: {metric_text} -> {entry['metric_id']}"
    if len(unique_matches) > 1:
        if not period:
            periodless = [match for match in unique_matches if not str(match.get("period") or "").strip()]
            if len(periodless) == 1:
                entry = periodless[0]
                return {
                    "metric_id": entry["metric_id"],
                    "metric": entry["canonical_metric"],
                    "canonical_metric_id": entry["metric_id"],
                    "canonical_metric_name": entry["canonical_metric"],
                    "original_metric_label": metric_text,
                    "normalization_status": "periodless_alias_match",
                    "period": entry.get("period"),
                    "used_for": item.get("used_for") or "unspecified",
                    "source_file": entry.get("source_file") or "",
                    "source_field": entry.get("source_field") or "",
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
                "canonical_metric_id": preferred["metric_id"],
                "canonical_metric_name": preferred["canonical_metric"],
                "original_metric_label": metric_text,
                "normalization_status": "same_canonical_alias_match",
                "period": preferred.get("period"),
                "used_for": item.get("used_for") or "unspecified",
                "source_file": preferred.get("source_file") or "",
                "source_field": preferred.get("source_field") or "",
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
        "precise_missing_financial_data": _normalize_string_list(
            value.get("precise_missing_financial_data"),
            "financial_assessment.precise_missing_financial_data",
            schema_warnings,
            default_empty=True,
        ),
        "derived_not_explicitly_reported": _normalize_string_list(
            value.get("derived_not_explicitly_reported"),
            "financial_assessment.derived_not_explicitly_reported",
            schema_warnings,
            default_empty=True,
        ),
        "partial_financial_data": _normalize_string_list(
            value.get("partial_financial_data"),
            "financial_assessment.partial_financial_data",
            schema_warnings,
            default_empty=True,
        ),
        "unreliable_financial_data": _normalize_string_list(
            value.get("unreliable_financial_data"),
            "financial_assessment.unreliable_financial_data",
            schema_warnings,
            default_empty=True,
        ),
        "invalid_or_quarantined_financial_data": _normalize_string_list(
            value.get("invalid_or_quarantined_financial_data"),
            "financial_assessment.invalid_or_quarantined_financial_data",
            schema_warnings,
            default_empty=True,
        ),
        "trend_durability_limits": _normalize_string_list(
            value.get("trend_durability_limits"),
            "financial_assessment.trend_durability_limits",
            schema_warnings,
            default_empty=True,
        ),
        "financial_questions_for_investor": _normalize_string_list(
            value.get("financial_questions_for_investor"),
            "financial_assessment.financial_questions_for_investor",
            schema_warnings,
            default_empty=True,
        ),
        "schema_warnings": schema_warnings,
    }


def _build_analyst_output_skeleton(
    *,
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    pcim: Dict[str, Any],
) -> Dict[str, Any]:
    skeleton = _deterministic_panel_output(
        doctrine=doctrine,
        company=company,
        pcim_path=pcim_path,
        pcim=pcim,
    )
    skeleton["analysis_mode"] = "llm_reasoning_v1"
    return skeleton


def _repair_assessment_draft(
    draft_value: Any,
    *,
    doctrine: Dict[str, Any],
    skeleton: Dict[str, Any],
    schema_warnings: List[str],
) -> Dict[str, Any]:
    assessment_keys = _required_assessment_keys(doctrine)
    repaired = dict(skeleton.get("assessment") or {})
    primary_key = assessment_keys[0] if assessment_keys else ""
    if isinstance(draft_value, dict):
        unknown = [key for key in draft_value.keys() if key not in assessment_keys]
        if unknown:
            schema_warnings.append(
                f"Unknown assessment fields were removed to diagnostics: {sorted(unknown)}."
            )
        for key in assessment_keys:
            value = draft_value.get(key)
            if isinstance(value, str) and value.strip():
                repaired[key] = value.strip()
            elif isinstance(value, list):
                normalized = _normalize_string_list(
                    value,
                    f"assessment.{key}",
                    schema_warnings,
                    default_empty=True,
                )
                if normalized:
                    repaired[key] = " ".join(normalized)
        return repaired
    if isinstance(draft_value, str) and draft_value.strip() and primary_key:
        repaired[primary_key] = draft_value.strip()
        schema_warnings.append("assessment was returned as string and normalized into the primary doctrine assessment field.")
        return repaired
    if isinstance(draft_value, list) and primary_key:
        normalized = _normalize_string_list(
            draft_value,
            "assessment",
            schema_warnings,
            default_empty=True,
        )
        if normalized:
            repaired[primary_key] = " ".join(normalized)
        schema_warnings.append("assessment was returned as list and normalized into the primary doctrine assessment field.")
        return repaired
    if draft_value is None:
        schema_warnings.append("assessment was missing; deterministic skeleton defaults were retained.")
        return repaired
    schema_warnings.append("assessment had unsupported shape; deterministic skeleton defaults were retained.")
    return repaired


def _repair_financial_assessment_draft(
    draft_value: Any,
    *,
    skeleton: Dict[str, Any],
    schema_warnings: List[str],
) -> Dict[str, Any]:
    repaired = deepcopy(skeleton.get("financial_assessment") or {})
    if isinstance(draft_value, dict):
        bool_value = draft_value.get("financials_used")
        if isinstance(bool_value, bool):
            repaired["financials_used"] = bool_value
        elif isinstance(bool_value, str) and bool_value.strip().lower() in {"true", "yes", "1"}:
            repaired["financials_used"] = True
            schema_warnings.append("financial_assessment.financials_used was normalized from string to boolean.")
        elif isinstance(bool_value, str) and bool_value.strip().lower() in {"false", "no", "0"}:
            repaired["financials_used"] = False
            schema_warnings.append("financial_assessment.financials_used was normalized from string to boolean.")
        basis_used = str(draft_value.get("basis_used") or "").strip()
        if basis_used:
            repaired["basis_used"] = basis_used
        for field in (
            "key_financial_strengths",
            "key_financial_concerns",
            "financial_red_flags",
            "missing_financial_data",
            "financial_interpretation_limits",
            "financial_warnings_carried_forward",
            "precise_missing_financial_data",
            "derived_not_explicitly_reported",
            "partial_financial_data",
            "unreliable_financial_data",
            "invalid_or_quarantined_financial_data",
            "trend_durability_limits",
            "financial_questions_for_investor",
        ):
            if field in draft_value:
                repaired[field] = _normalize_string_list(
                    draft_value.get(field),
                    f"financial_assessment.{field}",
                    schema_warnings,
                    default_empty=True,
                )
        unknown = [
            key for key in draft_value.keys()
            if key not in {
                "financials_used",
                "basis_used",
                "key_financial_strengths",
                "key_financial_concerns",
                "financial_red_flags",
                "missing_financial_data",
                "financial_interpretation_limits",
                "financial_warnings_carried_forward",
                "precise_missing_financial_data",
                "derived_not_explicitly_reported",
                "partial_financial_data",
                "unreliable_financial_data",
                "invalid_or_quarantined_financial_data",
                "trend_durability_limits",
                "financial_questions_for_investor",
            }
        ]
        if unknown:
            schema_warnings.append(
                f"Unknown financial_assessment fields were removed to diagnostics: {sorted(unknown)}."
            )
        return repaired
    if isinstance(draft_value, str) and draft_value.strip():
        repaired.setdefault("financial_interpretation_limits", [])
        repaired["financial_interpretation_limits"] = _unique_preserve_order(
            list(repaired.get("financial_interpretation_limits") or []) + [draft_value.strip()]
        )
        schema_warnings.append("financial_assessment was returned as string and normalized into financial_interpretation_limits.")
        return repaired
    if isinstance(draft_value, list):
        normalized = _normalize_string_list(
            draft_value,
            "financial_assessment",
            schema_warnings,
            default_empty=True,
        )
        if normalized:
            repaired.setdefault("financial_interpretation_limits", [])
            repaired["financial_interpretation_limits"] = _unique_preserve_order(
                list(repaired.get("financial_interpretation_limits") or []) + normalized
            )
        schema_warnings.append("financial_assessment was returned as list and normalized into financial_interpretation_limits.")
        return repaired
    if draft_value is None:
        schema_warnings.append("financial_assessment was missing; deterministic skeleton defaults were retained.")
        return repaired
    schema_warnings.append("financial_assessment had unsupported shape; deterministic skeleton defaults were retained.")
    return repaired


def _repair_user_facing_brief_draft(
    draft_value: Any,
    *,
    skeleton: Dict[str, Any],
    schema_warnings: List[str],
) -> Dict[str, Any]:
    repaired = deepcopy(skeleton.get("user_facing_brief") or {})
    if isinstance(draft_value, dict):
        for field in ("title", "lens", "financial_lens", "bottom_line"):
            value = draft_value.get(field)
            if isinstance(value, str) and value.strip():
                repaired[field] = value.strip()
        for field in ("what_looks_good", "what_needs_caution", "what_is_missing"):
            if field in draft_value:
                repaired[field] = _normalize_string_list(
                    draft_value.get(field),
                    f"user_facing_brief.{field}",
                    schema_warnings,
                    default_empty=True,
                )
        unknown = [
            key for key in draft_value.keys()
            if key not in {"title", "lens", "what_looks_good", "what_needs_caution", "what_is_missing", "financial_lens", "bottom_line"}
        ]
        if unknown:
            schema_warnings.append(
                f"Unknown user_facing_brief fields were removed to diagnostics: {sorted(unknown)}."
            )
        return repaired
    if isinstance(draft_value, str) and draft_value.strip():
        repaired["bottom_line"] = draft_value.strip()
        schema_warnings.append("user_facing_brief was returned as string and normalized into bottom_line.")
        return repaired
    if isinstance(draft_value, list):
        normalized = _normalize_string_list(
            draft_value,
            "user_facing_brief",
            schema_warnings,
            default_empty=True,
        )
        if normalized:
            repaired["what_needs_caution"] = _unique_preserve_order(
                list(repaired.get("what_needs_caution") or []) + normalized
            )
        schema_warnings.append("user_facing_brief was returned as list and normalized into what_needs_caution.")
        return repaired
    if draft_value is None:
        schema_warnings.append("user_facing_brief was missing; deterministic skeleton defaults were retained.")
        return repaired
    schema_warnings.append("user_facing_brief had unsupported shape; deterministic skeleton defaults were retained.")
    return repaired


def _repair_llm_panel_output_draft(
    parsed: Dict[str, Any],
    *,
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    pcim_version: Any,
    pcim: Dict[str, Any],
    consumed_sections: List[str],
) -> Tuple[Dict[str, Any], List[str]]:
    skeleton = _build_analyst_output_skeleton(
        doctrine=doctrine,
        company=company,
        pcim_path=pcim_path,
        pcim=pcim,
    )
    repaired = deepcopy(skeleton)
    schema_warnings: List[str] = []
    known_fields = {
        "assessment",
        "rating",
        "key_findings",
        "red_flags",
        "open_uncertainties",
        "financial_metrics_used",
        "financial_red_flags",
        "financial_positive_signals",
        "precise_missing_financial_data",
        "derived_not_explicitly_reported",
        "partial_financial_data",
        "unreliable_financial_data",
        "invalid_or_quarantined_financial_data",
        "trend_durability_limits",
        "financial_missing_data",
        "financial_interpretation_limits",
        "financial_questions_for_investor",
        "financial_assessment",
        "financial_sections_consumed",
        "financial_warnings_carried_forward",
        "evidence_ids",
        "historical_context_used",
        "years_considered",
        "supporting_pcim_sections",
        "reasoning_limits",
        "user_facing_brief",
        "key_concerns",
        "key_questions",
        "evidence_gaps",
        "generated_at",
    }
    unknown_fields = sorted(key for key in parsed.keys() if key not in known_fields)
    if unknown_fields:
        schema_warnings.append(f"Unknown top-level fields were removed to diagnostics: {unknown_fields}.")

    repaired["pcim_version"] = pcim_version
    repaired["pcim_source"] = str(pcim_path)
    repaired["sections_consumed"] = consumed_sections
    repaired["assessment"] = _repair_assessment_draft(
        parsed.get("assessment"),
        doctrine=doctrine,
        skeleton=skeleton,
        schema_warnings=schema_warnings,
    )
    repaired["financial_assessment"] = _repair_financial_assessment_draft(
        parsed.get("financial_assessment"),
        skeleton=skeleton,
        schema_warnings=schema_warnings,
    )
    repaired["user_facing_brief"] = _repair_user_facing_brief_draft(
        parsed.get("user_facing_brief"),
        skeleton=skeleton,
        schema_warnings=schema_warnings,
    )
    passthrough_fields = [
        "rating",
        "key_findings",
        "red_flags",
        "open_uncertainties",
        "financial_metrics_used",
        "financial_red_flags",
        "financial_positive_signals",
        "precise_missing_financial_data",
        "derived_not_explicitly_reported",
        "partial_financial_data",
        "unreliable_financial_data",
        "invalid_or_quarantined_financial_data",
        "trend_durability_limits",
        "financial_missing_data",
        "financial_interpretation_limits",
        "financial_questions_for_investor",
        "financial_sections_consumed",
        "financial_warnings_carried_forward",
        "evidence_ids",
        "historical_context_used",
        "years_considered",
        "supporting_pcim_sections",
        "reasoning_limits",
        "key_concerns",
        "key_questions",
        "evidence_gaps",
        "generated_at",
    ]
    for field in passthrough_fields:
        if field in parsed:
            repaired[field] = parsed.get(field)
    repaired["schema_warnings"] = _unique_preserve_order(
        list(repaired.get("schema_warnings") or []) + schema_warnings
    )
    return repaired, schema_warnings


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


def _payload_text_at_path(payload: Dict[str, Any], path: str) -> List[str]:
    root: Any = payload
    for part in path.split("."):
        if not isinstance(root, dict):
            return []
        root = root.get(part)
    if isinstance(root, str):
        text = root.strip()
        return [text] if text else []
    if isinstance(root, list):
        return [str(item).strip() for item in root if str(item).strip()]
    return []


ANALYST_BOILERPLATE_PATTERNS = (
    "assessment is grounded in",
    "is interpreted through the doctrine focus",
    "consumes sections",
    "consumes ",
    "input pcim was compacted",
    "analysis is limited to supplied facts",
    "primary focus:",
)

ANALYST_LIMITATION_ASSESSMENT_DEFAULT = (
    "Insufficient direct evidence in the compacted PCIM to make a confident doctrine-specific assessment. "
    "Treat this as a limitation, not a company conclusion."
)


def _is_boilerplate_assessment_text(text: Any) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(pattern in lowered for pattern in ANALYST_BOILERPLATE_PATTERNS)


def _normalize_boilerplate_assessment_fields(payload: Dict[str, Any], diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = deepcopy(payload if isinstance(payload, dict) else {})
    assessment = cleaned.get("assessment")
    if not isinstance(assessment, dict):
        return cleaned
    replacements: List[Dict[str, str]] = []
    for key, value in list(assessment.items()):
        if _is_boilerplate_assessment_text(value):
            replacements.append(
                {
                    "field": f"assessment.{key}",
                    "original": str(value),
                    "replacement": ANALYST_LIMITATION_ASSESSMENT_DEFAULT,
                    "reason": "boilerplate_assessment_default",
                }
            )
            assessment[key] = ANALYST_LIMITATION_ASSESSMENT_DEFAULT
    if replacements:
        diagnostics.setdefault("boilerplate_assessment_repairs", []).extend(replacements)
    return cleaned


ACTIVE_ANALYST_EXTERNAL_TEXT_FIELDS = (
    "key_findings",
    "red_flags",
    "open_uncertainties",
    "financial_red_flags",
    "financial_missing_data",
    "financial_interpretation_limits",
    "financial_warnings_carried_forward",
    "precise_missing_financial_data",
    "derived_not_explicitly_reported",
    "partial_financial_data",
    "unreliable_financial_data",
    "invalid_or_quarantined_financial_data",
    "trend_durability_limits",
    "financial_questions_for_investor",
    "reasoning_limits",
    "key_concerns",
    "key_questions",
    "evidence_gaps",
)

ACTIVE_ANALYST_EXTERNAL_NESTED_LIST_FIELDS = (
    "financial_assessment.key_financial_strengths",
    "financial_assessment.key_financial_concerns",
    "financial_assessment.financial_red_flags",
    "financial_assessment.missing_financial_data",
    "financial_assessment.financial_interpretation_limits",
    "financial_assessment.financial_warnings_carried_forward",
    "user_facing_brief.what_looks_good",
    "user_facing_brief.what_needs_caution",
    "user_facing_brief.what_is_missing",
)

ACTIVE_ANALYST_EXTERNAL_NESTED_SCALARS = (
    "user_facing_brief.title",
    "user_facing_brief.lens",
    "user_facing_brief.bottom_line",
    "user_facing_brief.financial_lens",
)


def _sanitize_active_external_reader_fields(payload: Dict[str, Any], diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = deepcopy(payload if isinstance(payload, dict) else {})

    assessment = cleaned.get("assessment")
    if isinstance(assessment, dict):
        for key, value in list(assessment.items()):
            if isinstance(value, str):
                assessment[key] = rewrite_text_for_external_reader(
                    value,
                    field_path=f"assessment.{key}",
                    diagnostics=diagnostics,
                )

    for field in ACTIVE_ANALYST_EXTERNAL_TEXT_FIELDS:
        value = cleaned.get(field)
        if not isinstance(value, list):
            continue
        cleaned[field] = [
            rewrite_text_for_external_reader(item, field_path=field, diagnostics=diagnostics)
            for item in value
            if str(item or "").strip()
        ]

    for path in ACTIVE_ANALYST_EXTERNAL_NESTED_LIST_FIELDS:
        parent, child = path.split(".", 1)
        container = cleaned.get(parent)
        if not isinstance(container, dict):
            continue
        value = container.get(child)
        if not isinstance(value, list):
            continue
        container[child] = [
            rewrite_text_for_external_reader(item, field_path=path, diagnostics=diagnostics)
            for item in value
            if str(item or "").strip()
        ]

    for path in ACTIVE_ANALYST_EXTERNAL_NESTED_SCALARS:
        parent, child = path.split(".", 1)
        container = cleaned.get(parent)
        if not isinstance(container, dict):
            continue
        container[child] = rewrite_text_for_external_reader(
            container.get(child),
            field_path=path,
            diagnostics=diagnostics,
        )

    return cleaned


def _active_claim_texts(payload: Dict[str, Any]) -> List[str]:
    texts: List[str] = []
    assessment = payload.get("assessment")
    if isinstance(assessment, dict):
        for value in assessment.values():
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
    for item in payload.get("key_findings") or []:
        if isinstance(item, dict):
            value = str(item.get("finding") or "").strip()
            if value:
                texts.append(value)
        elif isinstance(item, str) and item.strip():
            texts.append(item.strip())
    for item in payload.get("red_flags") or []:
        if isinstance(item, dict):
            value = str(item.get("flag") or "").strip()
            if value:
                texts.append(value)
        elif isinstance(item, str) and item.strip():
            texts.append(item.strip())
    for item in payload.get("financial_red_flags") or []:
        if isinstance(item, str) and item.strip():
            texts.append(item.strip())
    brief = payload.get("user_facing_brief") or {}
    if isinstance(brief, dict):
        for field in ("what_looks_good", "what_needs_caution"):
            for item in brief.get(field) or []:
                if isinstance(item, str) and item.strip():
                    texts.append(item.strip())
        for field in ("bottom_line", "financial_lens"):
            value = brief.get(field)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
    return texts


def _claim_text_present_in_active_fields(payload: Dict[str, Any], claim_text: Any) -> bool:
    needle = str(claim_text or "").strip().lower()
    if not needle:
        return False
    if _is_boilerplate_assessment_text(needle):
        return False
    for text in _active_claim_texts(payload):
        lowered = text.lower()
        if needle == lowered or needle in lowered or lowered in needle:
            return True
    return False


def _metric_pool_contains(truth_pack: Dict[str, Any], metric_aliases: Tuple[str, ...], pool_keys: Tuple[str, ...]) -> bool:
    aliases = {str(alias).strip().lower() for alias in metric_aliases if str(alias).strip()}
    for pool_key in pool_keys:
        for item in truth_pack.get(pool_key, []) or []:
            lowered = str(item or "").strip().lower()
            if lowered in aliases:
                return True
    return False


def _warning_resolution(text: str, truth_pack: Dict[str, Any]) -> Optional[Dict[str, str]]:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return None
    rules = (
        (
            ("fcf missing", "free cash flow missing"),
            ("fcf",),
            ("usable_current_metrics", "usable_derived_metrics"),
            "Derived FCF / owner-earnings estimate is available for the current usable year, but precision is limited because maintenance versus growth capex split and multi-year bridge history are incomplete.",
            "fcf",
            "usable_or_derived",
        ),
        (
            (
                "fcf-based conclusions cannot be assessed",
                "cannot construct owner-earnings bridge",
                "free cash flow and capex data are not provided",
                "owner-earnings cannot be assessed",
            ),
            ("fcf", "owner_earnings", "owner_earnings_estimate", "conservative_fcf"),
            ("usable_current_metrics", "usable_derived_metrics"),
            "Derived FCF / owner-earnings estimate is available for the current usable year, but precision is limited because maintenance versus growth capex split and multi-year bridge history are incomplete.",
            "owner_earnings",
            "usable_or_derived",
        ),
        (
            ("capex missing", "capex is unavailable", "capex unavailable", "capex data are not provided", "capex details are unavailable"),
            ("capex", "ppe_cwip_capex", "total_capex_for_fcf", "intangible_capex", "estimated_maintenance_capex", "estimated_growth_capex"),
            ("usable_current_metrics", "usable_derived_metrics", "partial_metrics"),
            "Identified capex is available, but maintenance versus growth capex split is unavailable.",
            "capex",
            "capex_precision_limit",
        ),
        (
            ("payables missing", "payables or payable-days evidence is missing", "payable days missing"),
            ("payables", "payable_days", "payable_turnover"),
            ("usable_current_metrics", "usable_derived_metrics", "partial_metrics"),
            "Payables and payable-days are available for the current usable year; multi-year payable-support history may still be limited.",
            "payables",
            "payables_available",
        ),
        (
            ("cash conversion cycle cannot be assessed",),
            ("cash_conversion_cycle", "payable_days", "payables"),
            ("usable_current_metrics", "usable_derived_metrics", "partial_metrics"),
            "Payables and payable-days are available for the current usable year; multi-year payable-support history may still be limited.",
            "cash_conversion_cycle",
            "payables_available",
        ),
        (
            ("cfo/pat missing",),
            ("cfo_to_pat", "cfo", "pat"),
            ("usable_current_metrics", "usable_derived_metrics"),
            "CFO and PAT evidence exists, but cash-conversion durability may still be limited.",
            "cfo_to_pat",
            "cash_conversion_available",
        ),
        (
            ("roe unavailable",),
            ("roe",),
            ("usable_current_metrics", "usable_derived_metrics"),
            "ROE is available, though multi-period durability may remain limited.",
            "roe",
            "roe_available",
        ),
        (
            ("roce unavailable",),
            ("roce",),
            ("usable_current_metrics", "usable_derived_metrics"),
            "ROCE is available, though multi-period durability may remain limited.",
            "roce",
            "roce_available",
        ),
        (
            ("share count missing",),
            ("shares_outstanding", "share_count", "closing_shares", "weighted_avg_shares", "weighted_average_diluted_shares", "diluted_shares"),
            ("usable_current_metrics", "usable_derived_metrics", "partial_metrics"),
            "Closing shares exist; weighted-average or diluted-share comparability may be limited.",
            "shares_outstanding",
            "share_count_available",
        ),
        (
            ("ownership missing",),
            ("promoter_holding", "pledged_promoter_holding", "fii_holding", "dii_holding", "mutual_fund_holding", "public_holding"),
            ("invalid_or_quarantined_metrics", "unreliable_metrics"),
            "Ownership/shareholding data is invalid or quarantined and should not be used downstream.",
            "ownership",
            "ownership_invalid_or_quarantined",
        ),
        (
            ("basis unknown", "basis unclear", "standalone/consolidated basis unclear", "standalone/consolidated basis is unclear"),
            ("basis",),
            ("usable_current_metrics", "usable_derived_metrics", "partial_metrics"),
            "Financial basis has been classified, but comparability may still require care.",
            "basis",
            "basis_resolved_or_classified",
        ),
    )
    for phrases, aliases, pool_keys, rewritten, metric, reason in rules:
        if any(phrase in lowered for phrase in phrases) and _metric_pool_contains(truth_pack, aliases, pool_keys):
            return {
                "rewritten_warning": rewritten,
                "supporting_metric": metric,
                "source_truth_pack_field": ",".join(pool_keys),
                "resolution_status": reason,
            }
    return None


ANALYST_FINANCIAL_TRUTH_ACTIVE_PATHS = (
    "red_flags",
    "open_uncertainties",
    "key_findings",
    "financial_red_flags",
    "financial_missing_data",
    "financial_interpretation_limits",
    "financial_warnings_carried_forward",
    "precise_missing_financial_data",
    "reasoning_limits",
    "user_facing_brief.what_looks_good",
    "user_facing_brief.what_needs_caution",
    "user_facing_brief.what_is_missing",
    "user_facing_brief.financial_lens",
    "financial_assessment.key_financial_strengths",
    "financial_assessment.key_financial_concerns",
    "financial_assessment.financial_red_flags",
    "financial_assessment.missing_financial_data",
    "financial_assessment.financial_interpretation_limits",
    "financial_assessment.financial_warnings_carried_forward",
)

FINANCIAL_WARNING_PROVENANCE_ACTIVE = {
    "active_current_year_absence",
    "active_multi_year_limitation",
    "active_precision_limitation",
    "active_basis_limitation",
    "active_per_share_limitation",
}


def _classify_financial_warning_provenance(text: str) -> str:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return "active_precision_limitation"
    if any(token in lowered for token in ("basis", "standalone", "consolidated", "comparability")):
        return "active_basis_limitation"
    if any(
        token in lowered
        for token in (
            "weighted-average shares",
            "weighted average shares",
            "diluted shares",
            "share-count",
            "share count",
            "per-share",
            "per share",
            "eps comparability",
            "book value per share",
            "fcf/share",
            "fcf per share",
        )
    ):
        return "active_per_share_limitation"
    if any(
        token in lowered
        for token in (
            "multi-year",
            "multi year",
            "bridge history",
            "bridge unavailable",
            "cagr",
            "durability",
            "history is incomplete",
            "history may still be limited",
            "fy22/fy23",
            "fy22",
            "fy23",
        )
    ):
        return "active_multi_year_limitation"
    if any(
        token in lowered
        for token in (
            "precision is limited",
            "precision remains limited",
            "precision may remain limited",
            "split is unavailable",
            "drivers unclear",
            "unmapped",
            "maintenance versus growth",
            "maintenance-versus-growth",
            "owner-earnings estimate is available",
            "derived fcf",
            "identified capex is available",
        )
    ):
        return "active_precision_limitation"
    if any(
        token in lowered
        for token in ("missing", "unavailable", "not supplied", "not provided", "not disclosed", "not available")
    ):
        return "active_current_year_absence"
    return "active_precision_limitation"


def _metric_label_from_warning(text: str) -> str:
    metric = str(text or "").split(":", 1)[0].strip().replace("_", " ")
    metric = " ".join(metric.split())
    if not metric:
        return "This metric"
    if metric.lower() == "weighted avg shares":
        return "Weighted-average shares"
    if metric.lower() == "shares outstanding":
        return "Shares outstanding"
    if metric.lower() == "diluted shares":
        return "Diluted shares"
    if metric.lower() == "fcf":
        return "FCF"
    if metric.lower() == "capex":
        return "Capex"
    return metric[:1].upper() + metric[1:]


def _rewrite_internal_financial_label(text: str, truth_pack: Dict[str, Any]) -> Optional[Dict[str, str]]:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return None
    if lowered in {
        "fcf: derived value used",
        "fcf: fcf is derived from normalized inputs",
    }:
        return {
            "rewritten_warning": "Derived FCF is available for the current usable year, but precision is limited because maintenance versus growth capex split is unavailable.",
            "classification": "active_precision_limitation",
            "reason": "derived_fcf_internal_label_rewritten",
        }
    if lowered in {
        "critical financial fields include unknown basis entries",
        "preferred basis is unknown",
    }:
        return {
            "rewritten_warning": "Standalone versus consolidated basis remains unclear, which limits financial comparability.",
            "classification": "active_basis_limitation",
            "reason": "basis_internal_label_rewritten",
        }
    if lowered.endswith("current-year reconciliation blocks cagr") or lowered.endswith("current year reconciliation blocks cagr"):
        return {
            "rewritten_warning": "Current-year values are usable, but CAGR analysis remains limited because comparable multi-year history is incomplete.",
            "classification": "active_multi_year_limitation",
            "reason": "cagr_internal_label_rewritten",
        }
    if lowered.endswith("important rows unmapped"):
        return {
            "rewritten_warning": "Some financial line items remain unmapped, which limits precision in the available financial evidence.",
            "classification": "active_precision_limitation",
            "reason": "unmapped_rows_internal_label_rewritten",
        }
    if "field has no populated normalized value" in lowered:
        metric_label = _metric_label_from_warning(text)
        if any(token in lowered for token in ("weighted_avg_shares", "weighted average shares")):
            rewritten = "Weighted-average shares are unavailable, so per-share comparability is limited."
            classification = "active_per_share_limitation"
        elif "diluted_shares" in lowered or "diluted shares" in lowered:
            rewritten = "Diluted shares are unavailable, so per-share comparability is limited."
            classification = "active_per_share_limitation"
        elif any(token in lowered for token in ("shares_outstanding", "share count", "closing_shares")):
            rewritten = "Share-count evidence is incomplete, so per-share comparability is limited."
            classification = "active_per_share_limitation"
        else:
            rewritten = f"{metric_label} is unavailable in the normalized financial data."
            classification = "active_current_year_absence"
        return {
            "rewritten_warning": rewritten,
            "classification": classification,
            "reason": "missing_normalized_value_internal_label_rewritten",
        }
    return None


def _set_string_list_path(payload: Dict[str, Any], path: str, values: List[str]) -> None:
    parts = path.split(".")
    root: Any = payload
    for part in parts[:-1]:
        if not isinstance(root.get(part), dict):
            root[part] = {}
        root = root[part]
    root[parts[-1]] = _unique_preserve_order(values)


def finalize_analyst_financial_truth_consistency(
    analysis: Dict[str, Any],
    analyst_financial_truth_pack: Dict[str, Any],
    diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    payload = deepcopy(analysis if isinstance(analysis, dict) else {})
    truth_pack = analyst_financial_truth_pack if isinstance(analyst_financial_truth_pack, dict) else {}
    diagnostics.setdefault("financial_warning_resolution", [])
    diagnostics.setdefault("financial_warning_provenance", [])
    diagnostics.setdefault("blocked_financial_warnings", [])
    diagnostics.setdefault("blocked_stale_financial_warnings", [])
    diagnostics.setdefault("diagnostic_only_financial_warnings", [])
    blocked_warnings = {str(item).strip().lower() for item in truth_pack.get("blocked_financial_warnings", []) or [] if str(item).strip()}
    rewritten_truth = {
        str(item).strip().lower(): str(item).strip()
        for item in truth_pack.get("rewritten_financial_warnings", []) or []
        if str(item).strip()
    }

    for path in ANALYST_FINANCIAL_TRUTH_ACTIVE_PATHS:
        items = _payload_text_at_path(payload, path)
        rewritten_items: List[str] = []
        for item in items:
            resolution = _warning_resolution(item, truth_pack)
            lowered = item.strip().lower()
            if resolution is not None:
                rewritten = resolution["rewritten_warning"]
                rewritten_items.append(rewritten)
                diagnostics["blocked_stale_financial_warnings"].append(item)
                diagnostics["financial_warning_resolution"].append(
                    {
                        "path": path,
                        "original_warning": item,
                        "rewritten_warning": rewritten,
                        "reason": resolution["resolution_status"],
                        "supporting_metric": resolution["supporting_metric"],
                        "source_truth_pack_field": resolution["source_truth_pack_field"],
                        "resolution_status": "rewritten",
                    }
                )
                diagnostics["financial_warning_provenance"].append(
                    {
                        "path": path,
                        "text": rewritten,
                        "classification": _classify_financial_warning_provenance(rewritten),
                        "original_text": item,
                    }
                )
                continue
            if lowered in blocked_warnings:
                rewritten = rewritten_truth.get(lowered) or _rewrite_blocked_financial_warning(item)
                diagnostics["blocked_stale_financial_warnings"].append(item)
                if rewritten and rewritten != item:
                    rewritten_items.append(rewritten)
                    diagnostics["financial_warning_resolution"].append(
                        {
                            "path": path,
                            "original_warning": item,
                            "rewritten_warning": rewritten,
                            "reason": "blocked_downstream_warning",
                            "supporting_metric": "",
                            "source_truth_pack_field": "blocked_financial_warnings",
                            "resolution_status": "rewritten",
                        }
                    )
                    diagnostics["financial_warning_provenance"].append(
                        {
                            "path": path,
                            "text": rewritten,
                            "classification": _classify_financial_warning_provenance(rewritten),
                            "original_text": item,
                        }
                    )
                else:
                    diagnostics["blocked_financial_warnings"].append(
                        {
                            "path": path,
                            "original_warning": item,
                            "resolution_status": "moved_to_diagnostics",
                        }
                    )
                continue
            internal_rewrite = _rewrite_internal_financial_label(item, truth_pack)
            if internal_rewrite is not None:
                rewritten = internal_rewrite["rewritten_warning"]
                diagnostics["diagnostic_only_financial_warnings"].append(item)
                if rewritten and rewritten != item:
                    rewritten_items.append(rewritten)
                    diagnostics["financial_warning_resolution"].append(
                        {
                            "path": path,
                            "original_warning": item,
                            "rewritten_warning": rewritten,
                            "reason": internal_rewrite["reason"],
                            "supporting_metric": "",
                            "source_truth_pack_field": "internal_financial_label",
                            "resolution_status": "rewritten",
                        }
                    )
                    diagnostics["financial_warning_provenance"].append(
                        {
                            "path": path,
                            "text": rewritten,
                            "classification": internal_rewrite["classification"],
                            "original_text": item,
                        }
                    )
                continue
            rewritten_items.append(item)
            diagnostics["financial_warning_provenance"].append(
                {
                    "path": path,
                    "text": item,
                    "classification": _classify_financial_warning_provenance(item),
                }
            )
        _set_string_list_path(payload, path, rewritten_items)

    if isinstance(payload.get("user_facing_brief"), dict):
        for field in ("bottom_line",):
            path = f"user_facing_brief.{field}"
            value = str(payload["user_facing_brief"].get(field) or "").strip()
            if not value:
                continue
            resolution = _warning_resolution(value, truth_pack)
            internal_rewrite = _rewrite_internal_financial_label(value, truth_pack)
            if resolution is not None:
                payload["user_facing_brief"][field] = resolution["rewritten_warning"]
                diagnostics["blocked_stale_financial_warnings"].append(value)
                diagnostics["financial_warning_resolution"].append(
                    {
                        "path": path,
                        "original_warning": value,
                        "rewritten_warning": resolution["rewritten_warning"],
                        "reason": resolution["resolution_status"],
                        "supporting_metric": resolution["supporting_metric"],
                        "source_truth_pack_field": resolution["source_truth_pack_field"],
                        "resolution_status": "rewritten",
                    }
                )
                diagnostics["financial_warning_provenance"].append(
                    {
                        "path": path,
                        "text": resolution["rewritten_warning"],
                        "classification": _classify_financial_warning_provenance(resolution["rewritten_warning"]),
                        "original_text": value,
                    }
                )
                continue
            if internal_rewrite is not None:
                payload["user_facing_brief"][field] = internal_rewrite["rewritten_warning"]
                diagnostics["diagnostic_only_financial_warnings"].append(value)
                diagnostics["financial_warning_resolution"].append(
                    {
                        "path": path,
                        "original_warning": value,
                        "rewritten_warning": internal_rewrite["rewritten_warning"],
                        "reason": internal_rewrite["reason"],
                        "supporting_metric": "",
                        "source_truth_pack_field": "internal_financial_label",
                        "resolution_status": "rewritten",
                    }
                )
                diagnostics["financial_warning_provenance"].append(
                    {
                        "path": path,
                        "text": internal_rewrite["rewritten_warning"],
                        "classification": internal_rewrite["classification"],
                        "original_text": value,
                    }
                )

    diagnostics["financial_warning_resolution"] = _unique_preserve_order(diagnostics["financial_warning_resolution"])
    diagnostics["financial_warning_provenance"] = _unique_preserve_order(diagnostics["financial_warning_provenance"])
    diagnostics["blocked_stale_financial_warnings"] = _unique_preserve_order(
        diagnostics["blocked_stale_financial_warnings"]
    )
    diagnostics["diagnostic_only_financial_warnings"] = _unique_preserve_order(
        diagnostics["diagnostic_only_financial_warnings"]
    )
    payload["blocked_stale_financial_warnings"] = (
        ["Stale missing-data warnings were blocked after financial truth reconciliation."]
        if diagnostics["blocked_stale_financial_warnings"]
        else []
    )
    payload["diagnostic_only_financial_warnings"] = (
        ["Internal raw financial warning labels were moved to diagnostics."]
        if diagnostics["diagnostic_only_financial_warnings"]
        else []
    )
    active_classes = [
        item.get("classification")
        for item in diagnostics["financial_warning_provenance"]
        if isinstance(item, dict)
    ]
    active_has_invalid = any(classification not in FINANCIAL_WARNING_PROVENANCE_ACTIVE for classification in active_classes if classification)
    if active_has_invalid:
        payload["financial_truth_consistency_status"] = "fail"
    elif diagnostics["blocked_stale_financial_warnings"] or diagnostics["diagnostic_only_financial_warnings"] or diagnostics["financial_warning_resolution"]:
        payload["financial_truth_consistency_status"] = "warning"
    else:
        payload["financial_truth_consistency_status"] = "pass"
    return payload


def finalize_analyst_financial_warnings(
    analysis: Dict[str, Any],
    analyst_financial_truth_pack: Dict[str, Any],
    diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    return finalize_analyst_financial_truth_consistency(
        analysis,
        analyst_financial_truth_pack,
        diagnostics,
    )


def finalize_analyst_validation_status(
    analysis: Dict[str, Any],
    diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    payload = _normalize_boilerplate_assessment_fields(
        deepcopy(analysis if isinstance(analysis, dict) else {}),
        diagnostics if isinstance(diagnostics, dict) else {},
    )
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    routing = diagnostics.get("evidence_routing_diagnostics") or {}
    normalization = diagnostics.get("evidence_id_normalization") or {}
    warning_entries = diagnostics.get("evidence_grounding_warnings") or payload.get("evidence_grounding_warnings") or []
    unresolved_claims = [item for item in (routing.get("unresolved_claims") or []) if item]
    unresolved_ids = [str(item).strip() for item in (normalization.get("unresolved_ids") or []) if str(item).strip()]
    removed_invalid_ids = list(normalization.get("removed_invalid_ids") or [])
    clean_writer_status = str(diagnostics.get("clean_writer_status") or "unknown").strip().lower()
    payload_text = json.dumps(payload, ensure_ascii=False)
    prior_evidence_status = str(payload.get("evidence_grounding_status") or "").strip().lower()
    prior_validation_status = str(payload.get("validation_status") or "").strip().lower()
    prior_status = str(payload.get("status") or "").strip().lower()
    prior_final_status = next(
        (
            candidate
            for candidate in (prior_status, prior_validation_status, prior_evidence_status)
            if candidate in KNOWN_ANALYST_FINAL_STATUS
        ),
        "unknown",
    )
    has_meaningful_post_repair_diagnostics = any(
        (
            bool(unresolved_claims),
            bool(unresolved_ids),
            bool(removed_invalid_ids),
            bool(diagnostics.get("boilerplate_assessment_repairs")),
            bool(routing.get("replaced_evidence") or routing.get("claims_converted_to_limitations") or routing.get("removed_misrouted_evidence")),
            bool(diagnostics.get("remaining_forbidden_keys") or diagnostics.get("remaining_forbidden_strings")),
            clean_writer_status in {"pass", "fail", "warning"},
        )
    )

    hard_failures: List[str] = []
    warnings: List[str] = []
    repaired: List[str] = []
    diagnostic_only: List[str] = []

    active_unresolved_claims: List[Dict[str, Any]] = []
    non_active_unresolved_claims: List[Dict[str, Any]] = []
    for item in unresolved_claims:
        claim_text = (
            item.get("claim_text")
            or item.get("text")
            or item.get("claim")
            or item.get("finding")
            or item.get("value")
            or item.get("summary")
            or ""
        ) if isinstance(item, dict) else str(item)
        if _is_boilerplate_assessment_text(claim_text):
            diagnostic_only.append("boilerplate assessment text was excluded from active claim finalization")
            continue
        if _claim_text_present_in_active_fields(payload, claim_text):
            active_unresolved_claims.append(item if isinstance(item, dict) else {"claim_text": str(item)})
        else:
            non_active_unresolved_claims.append(item if isinstance(item, dict) else {"claim_text": str(item)})

    if active_unresolved_claims:
        hard_failures.append("unresolved factual claims remain after evidence routing repair")
    elif non_active_unresolved_claims:
        warnings.append("unsupported factual claims were removed from active conclusions after evidence routing repair")

    active_evidence_ids = set()
    for evidence_id in payload.get("evidence_ids", []) or []:
        if str(evidence_id).strip():
            active_evidence_ids.add(str(evidence_id).strip())
    for block in (payload.get("key_findings") or [], payload.get("red_flags") or [], payload.get("open_uncertainties") or []):
        if isinstance(block, dict):
            for evidence_id in block.get("evidence_ids", []) or []:
                if str(evidence_id).strip():
                    active_evidence_ids.add(str(evidence_id).strip())
    unresolved_active = [item for item in unresolved_ids if item in active_evidence_ids]
    if unresolved_active:
        hard_failures.append("unresolved evidence IDs remain in active support")
    elif unresolved_ids:
        warnings.append(f"unresolved evidence IDs were removed from active support ({len(unresolved_ids)})")

    if removed_invalid_ids:
        repaired.append("invalid evidence IDs were removed before final save")

    replacements = list(normalization.get("replacements") or [])
    if replacements:
        repaired.append("evidence IDs were normalized to canonical IDs before final save")
    if diagnostics.get("boilerplate_assessment_repairs"):
        repaired.append("boilerplate assessment defaults were replaced with conservative limitation wording")

    if clean_writer_status == "fail":
        hard_failures.append("clean writer validation failed")
    elif clean_writer_status == "pass":
        diagnostic_only.append("clean writer passed")

    if diagnostics.get("remaining_forbidden_keys") or diagnostics.get("remaining_forbidden_strings"):
        hard_failures.append("forbidden clean-payload content remains after sanitization")

    forbidden_matches = find_forbidden_recommendation_language(payload_text)
    if forbidden_matches:
        hard_failures.append("forbidden recommendation or valuation language remains in final payload")

    if routing.get("replaced_evidence") or routing.get("claims_converted_to_limitations") or routing.get("removed_misrouted_evidence"):
        repaired.append("evidence routing was repaired deterministically")

    blocked_stale_financial_warnings = _unique_preserve_order(
        list(diagnostics.get("blocked_stale_financial_warnings", []) or [])
    )
    diagnostic_only_financial_warnings = _unique_preserve_order(
        list(diagnostics.get("diagnostic_only_financial_warnings", []) or [])
    )
    financial_truth_consistency_status = str(
        payload.get("financial_truth_consistency_status") or "pass"
    ).strip().lower()
    if financial_truth_consistency_status not in KNOWN_ANALYST_FINAL_STATUS:
        financial_truth_consistency_status = "pass"
    if financial_truth_consistency_status == "fail":
        hard_failures.append("financial truth consistency finalization failed")
    elif financial_truth_consistency_status == "warning":
        warnings.append("financial truth consistency required stale-warning or internal-label cleanup")

    for warning in warning_entries:
        text = json.dumps(warning, ensure_ascii=False) if isinstance(warning, dict) else str(warning)
        lowered = text.lower()
        if "routing" in lowered or "metadata" in lowered or "category" in lowered:
            warnings.append(text)
            if "category" in lowered and "metadata" in lowered:
                diagnostics.setdefault("evidence_category_metadata_weak", True)
        else:
            diagnostic_only.append(text)

    if hard_failures:
        final_status = "fail"
    elif warnings or repaired or unresolved_ids:
        final_status = "warning"
    elif has_meaningful_post_repair_diagnostics:
        final_status = "pass"
    elif prior_final_status in KNOWN_ANALYST_FINAL_STATUS:
        final_status = prior_final_status
    else:
        final_status = "pass"

    if final_status == "warning" and not warnings and prior_final_status == "warning":
        warnings.append("existing analyst artifact retained warning status after finalization review")
    if final_status == "fail" and not hard_failures and prior_final_status == "fail":
        hard_failures.append(f"evidence_grounding_status={prior_final_status}")

    payload["evidence_grounding_status"] = final_status
    payload["validation_status"] = final_status
    payload["status"] = final_status
    payload["financial_truth_consistency_status"] = financial_truth_consistency_status
    payload["hard_failures"] = _unique_preserve_order(hard_failures)
    payload["warnings"] = _unique_preserve_order(warnings)

    diagnostics["pre_finalization_status"] = {
        "evidence_grounding_status": str(analysis.get("evidence_grounding_status") or "").strip().lower() or "unknown",
        "validation_status": str(analysis.get("validation_status") or "").strip().lower() or "unknown",
        "status": str(analysis.get("status") or "").strip().lower() or "unknown",
    }
    diagnostics["post_finalization_status"] = {
        "evidence_grounding_status": final_status,
        "validation_status": final_status,
        "status": final_status,
    }
    diagnostics["finalization_summary"] = {
        "hard_failures": _unique_preserve_order(hard_failures),
        "warnings": _unique_preserve_order(warnings),
        "repaired": _unique_preserve_order(repaired),
        "diagnostic_only": _unique_preserve_order(diagnostic_only),
        "active_unresolved_claims": active_unresolved_claims,
        "non_active_unresolved_claims": non_active_unresolved_claims,
        "blocked_stale_financial_warnings": blocked_stale_financial_warnings,
        "diagnostic_only_financial_warnings": diagnostic_only_financial_warnings,
        "financial_truth_consistency_status": financial_truth_consistency_status,
    }
    return payload


def _financial_context_metric_flags(context: Dict[str, Any]) -> Dict[str, bool]:
    metric_registry = context.get("metric_registry") or []
    metrics = {metric.lower() for metric in context.get("metrics_used", [])}
    has_shares_outstanding = _metric_present_in_registry(
        metric_registry,
        ("shares_outstanding", "share_count"),
        require_usable_value=True,
    ) if metric_registry else any(metric in metrics for metric in {"shares_outstanding", "share_count"})
    has_weighted_avg_shares = _metric_present_in_registry(
        metric_registry,
        ("weighted_avg_shares",),
        require_usable_value=True,
    ) if metric_registry else "weighted_avg_shares" in metrics
    has_diluted_shares = _metric_present_in_registry(
        metric_registry,
        ("diluted_shares",),
        require_usable_value=True,
    ) if metric_registry else "diluted_shares" in metrics
    return {
        "has_fcf": "fcf" in metrics,
        "has_capex": "capex" in metrics,
        "has_shares_outstanding": has_shares_outstanding,
        "has_weighted_avg_shares": has_weighted_avg_shares,
        "has_diluted_shares": has_diluted_shares,
        "has_any_share_count": has_shares_outstanding or has_weighted_avg_shares or has_diluted_shares,
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


_MANAGEMENT_EXECUTION_CLAIM_TERMS: Tuple[str, ...] = (
    "delivered",
    "delivery",
    "executed",
    "execution",
    "completed",
    "implemented",
    "commissioned",
    "launched",
    "achieved",
    "followed through",
    "successful capital allocation",
    "realized operating outcome",
)

_MANAGEMENT_POSITIVE_OUTCOME_TERMS: Tuple[str, ...] = (
    "positive outcome",
    "successful outcome",
    "improved",
    "improvement",
    "higher utilization",
    "higher revenue",
    "higher profit",
    "lower defects",
    "reduced defects",
    "value creation",
    "created value",
    "strengthened returns",
    "operating benefit",
    "financial impact confirmed",
)

_MANAGEMENT_NEGATION_OR_UNCERTAINTY_TERMS: Tuple[str, ...] = (
    "not ",
    "no evidence",
    "unproven",
    "unknown",
    "unclear",
    "insufficient",
    "cannot",
    "could not",
    "has not",
    "have not",
    "remains to be seen",
    "remains unproven",
)

_MANAGEMENT_ATTRIBUTION_TERMS: Tuple[str, ...] = (
    "management initiated",
    "management has initiated",
    "management executed",
    "management delivered",
    "management completed",
    "management implemented",
    "management action",
    "management response has delivered",
)


def _iter_management_progression_chains(company_memory_context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(company_memory_context, dict):
        return []
    chains: List[Dict[str, Any]] = []
    for stream in company_memory_context.get("streams") or []:
        if not isinstance(stream, dict):
            continue
        if str(stream.get("stream") or "").strip().lower() != "management progression":
            continue
        for item in stream.get("synthesis_chains") or []:
            if isinstance(item, dict):
                chains.append(item)
    return chains


def _token_set_for_management_chain(item: Dict[str, Any]) -> set[str]:
    text = " ".join(
        str(item.get(key) or "")
        for key in (
            "theme",
            "claim_summary",
            "action_summary",
            "outcome_summary",
            "investor_implication",
        )
    ).lower()
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9]{4,}", text)
        if token
        not in {
            "management",
            "company",
            "business",
            "evidence",
            "outcome",
            "action",
            "financial",
            "investor",
            "period",
            "remains",
            "unproven",
        }
    }


def _claim_mentions_management_chain(claim_text: str, item: Dict[str, Any]) -> bool:
    claim_tokens = {
        token
        for token in re.findall(r"[a-z][a-z0-9]{4,}", claim_text.lower())
        if token not in {"management", "company", "business", "evidence", "outcome", "action", "financial"}
    }
    chain_tokens = _token_set_for_management_chain(item)
    return len(claim_tokens & chain_tokens) >= 2


def _has_any_term(text: str, terms: Tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _is_uncertainty_or_negated_management_claim(text: str) -> bool:
    return _has_any_term(text, _MANAGEMENT_NEGATION_OR_UNCERTAINTY_TERMS)


def _active_analyst_claim_texts(
    *,
    assessment: Dict[str, str],
    key_findings: List[str],
    red_flags: List[str],
    open_uncertainties: List[str],
    user_facing_brief: Dict[str, Any],
) -> List[str]:
    texts: List[str] = list(assessment.values()) + list(key_findings) + list(red_flags) + list(open_uncertainties)
    for key in ("what_looks_good", "what_needs_caution", "what_is_missing"):
        for item in user_facing_brief.get(key) or []:
            if isinstance(item, str):
                texts.append(item)
    for key in ("financial_lens", "bottom_line"):
        value = user_facing_brief.get(key)
        if isinstance(value, str):
            texts.append(value)
    return [text for text in texts if isinstance(text, str) and text.strip()]


def _management_chain_subject(chain: Dict[str, Any]) -> str:
    for key in ("action_summary", "outcome_summary", "claim_summary", "theme"):
        value = str(chain.get(key) or "").strip()
        if value:
            return _truncate_text(value, 180)
    return "The management-progression item"


def _conservative_management_chain_text(chain: Dict[str, Any], reason: str) -> str:
    subject = _management_chain_subject(chain)
    actor = str(chain.get("actor") or "").strip().lower()
    status = str(chain.get("chain_status") or "").strip().upper()
    if reason == "non_management_actor":
        actor_label = actor if actor in {"regulator", "customer", "partner", "market", "other", "unknown"} else "non-management"
        return f"A {actor_label} action occurred: {subject}. Management response and economic outcome remain unproven."
    if status == "CLAIM_ONLY":
        return f"{subject} is claim evidence only; execution, operating outcome, and financial consequence remain unproven."
    if status == "ACTION_STARTED":
        return f"{subject} shows action began; completion, operating outcome, and financial consequence remain unproven."
    if status == "ACTION_COMPLETED":
        return f"{subject} shows completion; operating outcome and financial consequence remain unproven."
    return f"{subject} does not confirm financial consequence; economic impact remains unproven."


def _management_chain_inflation_reason(claim_text: str, chain: Dict[str, Any]) -> Optional[str]:
    if _is_uncertainty_or_negated_management_claim(claim_text):
        return None
    if not _claim_mentions_management_chain(claim_text, chain):
        return None
    actor = str(chain.get("actor") or "").strip().lower()
    status = str(chain.get("chain_status") or "").strip().upper()
    financial_status = str(chain.get("financial_link_status") or "").strip().lower()
    if actor not in {"", "management", "company"} and _has_any_term(claim_text, _MANAGEMENT_ATTRIBUTION_TERMS):
        return "non_management_actor"
    if status == "CLAIM_ONLY" and _has_any_term(claim_text, _MANAGEMENT_EXECUTION_CLAIM_TERMS):
        return "claim_only_execution"
    if status == "ACTION_STARTED" and _has_any_term(
        claim_text,
        _MANAGEMENT_EXECUTION_CLAIM_TERMS + _MANAGEMENT_POSITIVE_OUTCOME_TERMS,
    ):
        return "action_started_outcome"
    if status == "ACTION_COMPLETED" and _has_any_term(claim_text, _MANAGEMENT_POSITIVE_OUTCOME_TERMS):
        return "action_completed_outcome_inflation"
    if financial_status and financial_status not in {"confirmed", "financial_impact_confirmed"} and _has_any_term(
        claim_text,
        ("financial impact confirmed", "financial benefit", "returns improved", "profit improved", "revenue improved"),
    ):
        return "unconfirmed_financial_link"
    return None


def _repair_management_synthesis_chain_inflation(
    *,
    company_memory_context: Optional[Dict[str, Any]],
    assessment: Dict[str, str],
    key_findings: List[str],
    red_flags: List[str],
    open_uncertainties: List[str],
    user_facing_brief: Dict[str, Any],
) -> List[str]:
    chains = _iter_management_progression_chains(company_memory_context)
    if not chains:
        return []
    repair_notes: List[str] = []

    def repair_text(text: str, field_path: str) -> str:
        if not isinstance(text, str) or not text.strip():
            return text
        for chain in chains:
            reason = _management_chain_inflation_reason(text, chain)
            if not reason:
                continue
            repair_notes.append(
                "management synthesis-chain inflation repaired "
                f"at {field_path}: {reason}; chain_status={str(chain.get('chain_status') or '').strip() or 'unknown'}"
            )
            return _conservative_management_chain_text(chain, reason)
        return text

    for key, value in list(assessment.items()):
        assessment[key] = repair_text(value, f"assessment.{key}")
    for items, label in (
        (key_findings, "key_findings"),
        (red_flags, "red_flags"),
        (open_uncertainties, "open_uncertainties"),
    ):
        for idx, value in enumerate(list(items)):
            items[idx] = repair_text(value, f"{label}.{idx}")
    for key in ("what_looks_good", "what_needs_caution", "what_is_missing"):
        values = user_facing_brief.get(key)
        if not isinstance(values, list):
            continue
        for idx, value in enumerate(list(values)):
            values[idx] = repair_text(value, f"user_facing_brief.{key}.{idx}")
    for key in ("financial_lens", "bottom_line"):
        value = user_facing_brief.get(key)
        if isinstance(value, str):
            user_facing_brief[key] = repair_text(value, f"user_facing_brief.{key}")
    return repair_notes


def _raise_if_management_synthesis_chain_contradicted(
    *,
    company_memory_context: Optional[Dict[str, Any]],
    assessment: Dict[str, str],
    key_findings: List[str],
    red_flags: List[str],
    open_uncertainties: List[str],
    user_facing_brief: Dict[str, Any],
) -> None:
    chains = _iter_management_progression_chains(company_memory_context)
    if not chains:
        return
    claim_texts = _active_analyst_claim_texts(
        assessment=assessment,
        key_findings=key_findings,
        red_flags=red_flags,
        open_uncertainties=open_uncertainties,
        user_facing_brief=user_facing_brief,
    )
    for chain in chains:
        for text in claim_texts:
            reason = _management_chain_inflation_reason(text, chain)
            if not reason:
                continue
            if reason == "non_management_actor":
                raise ValueError(
                    "analyst contradicts management synthesis chain: non-management actor cannot be "
                    "attributed to management action"
                )
            if reason == "claim_only_execution":
                raise ValueError(
                    "analyst contradicts management synthesis chain: CLAIM_ONLY cannot support execution, "
                    "delivery, capital-allocation success, or realized outcome"
                )
            if reason == "action_started_outcome":
                raise ValueError(
                    "analyst contradicts management synthesis chain: ACTION_STARTED cannot support completion, "
                    "outcome, or financial impact"
                )
            if reason == "action_completed_outcome_inflation":
                raise ValueError(
                    "analyst contradicts management synthesis chain: ACTION_COMPLETED alone cannot support "
                    "positive operating or financial outcome"
                )
            if reason == "unconfirmed_financial_link":
                raise ValueError(
                    "analyst contradicts management synthesis chain: financial consequence is not confirmed"
                )


def _validate_repaired_llm_panel_output(
    parsed: Dict[str, Any],
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    pcim_version: Any,
    pcim: Dict[str, Any],
    consumed_sections: List[str],
    allowed_evidence_ids: List[str],
    company_memory_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    if '"source_chunk"' in json.dumps(parsed, ensure_ascii=False):
        raise ValueError("source_chunk is not allowed in analyst output")
    schema_warnings: List[str] = list(parsed.get("schema_warnings") or [])

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
    precise_missing_financial_data = _normalize_string_list(
        parsed.get("precise_missing_financial_data"),
        "precise_missing_financial_data",
        schema_warnings,
        default_empty=True,
    )
    derived_not_explicitly_reported = _normalize_string_list(
        parsed.get("derived_not_explicitly_reported"),
        "derived_not_explicitly_reported",
        schema_warnings,
        default_empty=True,
    )
    partial_financial_data = _normalize_string_list(
        parsed.get("partial_financial_data"),
        "partial_financial_data",
        schema_warnings,
        default_empty=True,
    )
    unreliable_financial_data = _normalize_string_list(
        parsed.get("unreliable_financial_data"),
        "unreliable_financial_data",
        schema_warnings,
        default_empty=True,
    )
    invalid_or_quarantined_financial_data = _normalize_string_list(
        parsed.get("invalid_or_quarantined_financial_data"),
        "invalid_or_quarantined_financial_data",
        schema_warnings,
        default_empty=True,
    )
    trend_durability_limits = _normalize_string_list(
        parsed.get("trend_durability_limits"),
        "trend_durability_limits",
        schema_warnings,
        default_empty=True,
    )
    financial_questions_for_investor = _normalize_string_list(
        parsed.get("financial_questions_for_investor"),
        "financial_questions_for_investor",
        schema_warnings,
        default_empty=True,
    )
    reasoning_limits = _normalize_string_list(
        parsed.get("reasoning_limits"),
        "reasoning_limits",
        schema_warnings,
        default_empty=True,
    )
    brief_repair_diagnostics: Dict[str, Any] = {"brief_repair_diagnostics": []}
    normalized_brief = normalize_user_facing_brief_shape(parsed.get("user_facing_brief"))
    sanitized_brief = sanitize_user_facing_brief(normalized_brief)
    finalized_brief = finalize_user_facing_brief_for_external_reader(
        doctrine["doctrine_id"],
        sanitize_user_facing_brief(normalize_user_facing_brief_shape(sanitized_brief)),
        doctrine=doctrine,
        diagnostics=brief_repair_diagnostics,
    )
    brief_issues = collect_user_facing_brief_validation_issues(doctrine["doctrine_id"], finalized_brief)
    if brief_issues:
        finalized_brief = finalize_user_facing_brief_for_external_reader(
            doctrine["doctrine_id"],
            finalized_brief,
            doctrine=doctrine,
            diagnostics=brief_repair_diagnostics,
        )
    normalized_length_brief = normalize_user_facing_brief_lengths(finalized_brief)
    user_facing_brief = validate_user_facing_brief(doctrine["doctrine_id"], normalized_length_brief)
    if brief_repair_diagnostics.get("brief_repair_diagnostics") or brief_repair_diagnostics.get("rewritten_fields"):
        schema_warnings.append("user_facing_brief canonical fields were finalized before validation.")

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
    truth_pack = derived_financial_context["truth_pack"]
    metric_registry = derived_financial_context["metric_registry"]
    by_metric_id, by_alias = _build_financial_metric_lookup(metric_registry)
    financial_metrics_used: List[Dict[str, Any]] = []
    invalid_financial_metrics: List[str] = []
    metric_normalizations_applied: List[Dict[str, Any]] = []
    unsupported_financial_metric_references: List[Dict[str, Any]] = []
    canonicalization_warnings = list(metric_normalization_warnings)
    for metric_item in financial_metrics_used_raw:
        canonical_metric_item, warning = _canonicalize_financial_metric_ref(
            metric_item,
            by_metric_id=by_metric_id,
            by_alias=by_alias,
        )
        if canonical_metric_item is None:
            invalid_financial_metrics.append(warning or str(metric_item))
            unsupported_financial_metric_references.append(
                {
                    "original_metric_label": str(metric_item.get("metric") or metric_item.get("metric_id") or "").strip(),
                    "canonical_metric_id": "",
                    "repair_status": "omitted",
                    "reason": warning or "unknown financial metric reference",
                }
            )
            continue
        financial_metrics_used.append(canonical_metric_item)
        if canonical_metric_item.get("normalization_status") != "exact_metric_id_match":
            metric_normalizations_applied.append(
                {
                    "original_metric_label": canonical_metric_item.get("original_metric_label") or canonical_metric_item.get("metric"),
                    "canonical_metric_id": canonical_metric_item.get("canonical_metric_id") or canonical_metric_item.get("metric_id"),
                    "canonical_metric_name": canonical_metric_item.get("canonical_metric_name") or canonical_metric_item.get("metric"),
                    "repair_status": canonical_metric_item.get("normalization_status") or "normalized",
                    "source_file": canonical_metric_item.get("source_file") or "",
                    "source_field": canonical_metric_item.get("source_field") or "",
                }
            )
        if warning:
            canonicalization_warnings.append(warning)
    if canonicalization_warnings:
        reasoning_limits.extend(_unique_preserve_order(canonicalization_warnings))
    if unsupported_financial_metric_references:
        schema_warnings.append("unsupported metric reference omitted from financial_metrics_used after deterministic normalization.")

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
    context_metric_flags = _financial_context_metric_flags(derived_financial_context)
    imprecise_financial_warning_messages: List[str] = []
    blocked_warning_hits = [
        item
        for item in (
            financial_warnings_carried_forward
            + financial_missing_data
            + financial_interpretation_limits
            + precise_missing_financial_data
            + financial_assessment["missing_financial_data"]
            + financial_assessment["financial_warnings_carried_forward"]
        )
        if str(item).strip() in set(truth_pack["blocked_financial_warnings"])
    ]
    if blocked_warning_hits:
        raise ValueError(
            "analyst output contains blocked financial warnings: "
            + ", ".join(sorted(set(blocked_warning_hits)))
        )
    raw_context_warning_texts = _texts_for_financial_matching(
        _collect_financial_warnings(selected_pcim, consumed_sections),
        derived_financial_context.get("missing_data", []),
    )
    if context_metric_flags["has_shares_outstanding"] and any(
        "share count missing" in item.lower()
        for item in raw_context_warning_texts
    ):
        imprecise_financial_warning_messages.append(
            "PCIM share-count warning was imprecise; shares_outstanding exists, so equivalent per-share limitation wording was accepted."
        )
    invalid_as_positive = [
        item for item in financial_positive_signals
        if any(token and token.lower() in item.lower() for token in truth_pack["invalid_or_quarantined_metrics"] + truth_pack["unreliable_metrics"])
    ]
    if invalid_as_positive:
        raise ValueError(
            "analyst used invalid, quarantined, or unreliable financial data as positive evidence: "
            + ", ".join(sorted(set(invalid_as_positive)))
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
    if "fcf" not in {metric.lower() for metric in _registry_metric_names(metric_registry)} and _contains_any(
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

    management_chain_repair_notes = _repair_management_synthesis_chain_inflation(
        company_memory_context=company_memory_context,
        assessment=normalized_assessment,
        key_findings=key_findings,
        red_flags=red_flags,
        open_uncertainties=open_uncertainties,
        user_facing_brief=user_facing_brief,
    )
    if management_chain_repair_notes:
        schema_warnings.extend(management_chain_repair_notes)
        if grounding["evidence_grounding_status"] == "pass":
            grounding["evidence_grounding_status"] = "warning"

    _raise_if_management_synthesis_chain_contradicted(
        company_memory_context=company_memory_context,
        assessment=normalized_assessment,
        key_findings=key_findings,
        red_flags=red_flags,
        open_uncertainties=open_uncertainties,
        user_facing_brief=user_facing_brief,
    )

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
        "financial_metric_normalizations_applied": metric_normalizations_applied,
        "unsupported_financial_metric_references": unsupported_financial_metric_references,
        "financial_red_flags": financial_red_flags,
        "financial_positive_signals": financial_positive_signals,
        "precise_missing_financial_data": precise_missing_financial_data,
        "derived_not_explicitly_reported": derived_not_explicitly_reported,
        "partial_financial_data": partial_financial_data,
        "unreliable_financial_data": unreliable_financial_data,
        "invalid_or_quarantined_financial_data": invalid_or_quarantined_financial_data,
        "trend_durability_limits": trend_durability_limits,
        "financial_missing_data": financial_missing_data,
        "financial_interpretation_limits": financial_interpretation_limits,
        "financial_questions_for_investor": financial_questions_for_investor,
        "analyst_financial_truth_pack": truth_pack,
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
        "brief_repair_diagnostics": brief_repair_diagnostics.get("brief_repair_diagnostics", []),
        "generated_at": utc_now(),
    }
    finalization_diagnostics: Dict[str, Any] = {
        "brief_rewrite_diagnostics": brief_repair_diagnostics.get("rewritten_fields", []),
        "brief_validation_issues": brief_repair_diagnostics.get("remaining_validation_issues", []),
    }
    payload = finalize_analyst_financial_warnings(
        payload,
        truth_pack,
        finalization_diagnostics,
    )
    hygiene_diagnostics: Dict[str, Any] = {"removed_invalid_evidence_ids": []}
    payload = sanitize_active_evidence_ids(
        payload,
        evidence_lookup=evidence_lookup,
        diagnostics=hygiene_diagnostics,
    )
    payload = _sanitize_active_external_reader_fields(payload, hygiene_diagnostics)
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
    payload = finalize_analyst_validation_status(payload, finalization_diagnostics)
    payload["finalization_diagnostics"] = finalization_diagnostics
    assert_valid_routed_payload(payload, evidence_lookup=evidence_lookup)
    return payload


def _validate_llm_panel_output(
    payload_text: str,
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    pcim_version: Any,
    pcim: Dict[str, Any],
    consumed_sections: List[str],
    allowed_evidence_ids: List[str],
    company_memory_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        parsed = json.loads(payload_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    repaired, _repair_warnings = _repair_llm_panel_output_draft(
        parsed,
        doctrine=doctrine,
        company=company,
        pcim_path=pcim_path,
        pcim_version=pcim_version,
        pcim=pcim,
        consumed_sections=consumed_sections,
    )
    return _validate_repaired_llm_panel_output(
        repaired,
        doctrine=doctrine,
        company=company,
        pcim_path=pcim_path,
        pcim_version=pcim_version,
        pcim=pcim,
        consumed_sections=consumed_sections,
        allowed_evidence_ids=allowed_evidence_ids,
        company_memory_context=company_memory_context,
    )


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

    def _write_prompt_budget_diagnostics(self, analyst: str, payload: Dict[str, Any]) -> Path:
        diagnostics_path = self.output_dir / f"prompt_budget_diagnostics_{_safe_slug(analyst)}.json"
        return _write_json(diagnostics_path, payload)

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
            "excluded_sections": budget_report.get("excluded_sections", []),
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
        self._write_prompt_budget_diagnostics(
            doctrine["doctrine_id"],
            {
                "company": self.company,
                "analyst": doctrine["doctrine_id"],
                "sections_requested": consumed_sections,
                **budget_report,
            },
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
            company_memory_context=llm_input_pack.get("company_memory_context_for_prompt"),
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
                company_memory_context=llm_input_pack.get("company_memory_context_for_prompt"),
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
        self._write_prompt_budget_diagnostics(
            doctrine["doctrine_id"],
            {
                "company": self.company,
                "analyst": doctrine["doctrine_id"],
                "sections_requested": consumed_sections,
                **budget_report,
            },
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
