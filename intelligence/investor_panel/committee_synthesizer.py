from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from knowledge.ai import get_llm
from knowledge.ai.input_packs import (
    build_llm_input_pack,
    call_llm_with_input_pack,
    render_llm_input_pack,
    resolve_stage_token_budget,
    estimate_tokens,
)

from .committee_validator import (
    COMMITTEE_FIELD_CONTRACTS,
    EXPECTED_ANALYSTS,
    _canonical_committee_evidence_id,
    normalize_known_analyst_reference,
    _safe_list_dict_to_string,
    _validate_normalized_list_text,
    validate_analyst_payload,
    validate_committee_output,
)
from intelligence.progression import build_interpretation_contract
from .committee_brief_renderer import finalize_committee_brief_for_user
from .company_memory_context import build_company_memory_context
from .evidence_grounding import build_evidence_lookup
from .evidence_grounding import PCIM_SECTION_NAME_DENYLIST
from pipelines.pipeline_context import get_context


COMMITTEE_SYNTHESIS_SYSTEM_PROMPT = """
You are the committee narrative writer for Prometheus.
You receive deterministic committee facts and must only write concise narrative text.
Do not invent facts, numbers, analysts, evidence IDs, risks, or unknowns.
Do not output metadata, enums, analyst IDs, critical unknowns, or financial warning flags.
No valuation, target prices, recommendation, or buy/sell/hold language.
Return JSON only.
"""

COMMITTEE_SCHEMA_PROMPT = """
keys=executive_committee_summary,synthesis_narrative,disagreement_explanation,what_to_watch_next,suggested_unknowns
executive_committee_summary=string
synthesis_narrative=list[string]
disagreement_explanation=list[string]
what_to_watch_next=list[string]
suggested_unknowns=list[string]
rules=use deterministic input only; no metadata; no analyst ids; no enums; no valuation; no buy/sell/hold
"""

COMMITTEE_SYNTHESIS_USER_PROMPT = """
Return JSON only with narrative fields.
DETERMINISTIC_INPUT:
{committee_input_json}
SCHEMA:
{committee_schema}
"""

CONFIDENCE_ENUM_MAP = {
    "low": "low",
    "low confidence": "low",
    "low_confidence": "low",
    "limited": "low",
    "uncertain": "low",
    "weak": "low",
    "medium": "medium",
    "medium confidence": "medium",
    "medium_confidence": "medium",
    "moderate": "medium",
    "mixed": "medium",
    "high": "high",
    "high confidence": "high",
    "high_confidence": "high",
    "strong": "high",
}

RATING_ENUM_MAP = {
    "strong": "strong",
    "positive": "strong",
    "mixed": "mixed",
    "neutral": "mixed",
    "moderate": "mixed",
    "balanced": "mixed",
    "cautious": "mixed",
    "weak": "weak",
    "negative": "weak",
    "insufficient_evidence": "insufficient_evidence",
    "insufficient evidence": "insufficient_evidence",
    "insufficient-evidence": "insufficient_evidence",
    "not enough evidence": "insufficient_evidence",
    "inconclusive": "insufficient_evidence",
}

DISAGREEMENT_TYPE_ENUM_MAP = {
    "different_emphasis": "different_emphasis",
    "different emphasis": "different_emphasis",
    "emphasis difference": "different_emphasis",
    "priority difference": "different_emphasis",
    "different priority": "different_emphasis",
    "different angle": "different_emphasis",
    "framing difference": "different_emphasis",
    "nuance": "different_emphasis",
    "mixed emphasis": "different_emphasis",
    "moderate disagreement": "different_emphasis",
    "risk_weighting_difference": "risk_weighting_difference",
    "risk weighting difference": "risk_weighting_difference",
    "risk weighting": "risk_weighting_difference",
    "different risk weight": "risk_weighting_difference",
    "risk emphasis": "risk_weighting_difference",
    "risk concern": "risk_weighting_difference",
    "risk severity difference": "risk_weighting_difference",
    "risk perception difference": "risk_weighting_difference",
    "true_disagreement": "true_disagreement",
    "true disagreement": "true_disagreement",
    "actual disagreement": "true_disagreement",
    "genuine disagreement": "true_disagreement",
    "conflicting views": "true_disagreement",
    "conflict": "true_disagreement",
    "contradiction": "true_disagreement",
    "opposing view": "true_disagreement",
    "disagreement": "true_disagreement",
}

COMMITTEE_V2_VIEW_VALUES = {
    "strong",
    "reasonably_strong",
    "mixed",
    "weak",
    "insufficient_evidence",
}

COMMITTEE_V2_DIRECTION_VALUES = {
    "strengthening",
    "weakening",
    "stable",
    "mixed",
    "unclear",
}

COMMITTEE_V2_CONSENSUS_VALUES = {
    "high",
    "medium",
    "low",
    "fragmented",
    "insufficient_evidence",
}

COMMITTEE_V2_DISAGREEMENT_TYPE_MAP = {
    "true_disagreement": "evidence_disagreement",
    "different_emphasis": "doctrine_weighting_difference",
    "risk_weighting_difference": "uncertainty_tolerance_difference",
    "evidence_gap": "unresolved_data_gap",
}

COMMITTEE_V2_STREAM_PRIORITY = [
    "management quality",
    "management commitments",
    "projects",
    "capacity evolution",
    "risk evolution",
    "management commentary",
    "capital allocation outcomes",
    "financial memory",
]

COMMITTEE_V2_STREAM_KEYWORDS = {
    "management quality": [
        "management quality",
        "candor",
        "credibility",
        "execution",
        "management",
        "discipline",
        "trust",
    ],
    "management commitments": [
        "commitment",
        "promise",
        "promised",
        "expected",
        "announced",
        "delivery",
        "superseded",
        "abandoned",
    ],
    "projects": [
        "project",
        "plant",
        "facility",
        "line",
        "programme",
        "program",
        "initiative",
        "expansion",
    ],
    "capacity evolution": [
        "capacity",
        "commission",
        "commissioned",
        "utilization",
        "throughput",
        "ramp",
        "operational",
        "underutilized",
    ],
    "risk evolution": [
        "risk",
        "receivable",
        "payable",
        "debt",
        "liquidity",
        "working capital",
        "customer concentration",
        "supplier",
    ],
    "management commentary": [
        "commentary",
        "management said",
        "management stated",
        "narrative",
        "emphasis",
        "conviction",
    ],
    "capital allocation outcomes": [
        "capital allocation",
        "capex",
        "acquisition",
        "roi",
        "return",
        "deployment",
        "payoff",
        "investment",
    ],
    "financial memory": [
        "revenue",
        "pat",
        "cfo",
        "fcf",
        "cash",
        "margin",
        "eps",
        "owner earnings",
        "working capital",
        "debt",
    ],
}


def _normalize_enum_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", " ").replace("_", " ")


def _record_enum_repair(
    repairs: List[Dict[str, Any]],
    *,
    path: str,
    original: Any,
    normalized: Any,
    reason: str,
) -> None:
    repairs.append(
        {
            "path": path,
            "original": original,
            "normalized": normalized,
            "reason": reason,
        }
    )


def _get_nested_path(payload: Dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_nested_path(payload: Dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: Dict[str, Any] = payload
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


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


def _flatten_strings(value: Any) -> List[str]:
    items: List[str] = []
    if isinstance(value, str):
        text = value.strip()
        if text:
            items.append(text)
    elif isinstance(value, dict):
        for child in value.values():
            items.extend(_flatten_strings(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(_flatten_strings(child))
    return items


def _truth_pack_metric_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        status = str(value.get("availability_status") or value.get("status") or "").strip().lower()
        if status in {"present_direct", "present_derived", "partial", "available", "estimate_available", "partially_measurable"}:
            return True
        for key in ("value", "value_crore", "metric_value", "current_value", "owner_earnings_estimate", "conservative_fcf_after_total_capex"):
            metric_value = value.get(key)
            if isinstance(metric_value, (int, float)) and not isinstance(metric_value, bool):
                return True
    elif isinstance(value, list):
        return any(_truth_pack_metric_present(item) for item in value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    return False


def _truth_pack_has_metric(payload: Dict[str, Any], *metric_ids: str) -> bool:
    for metric_id in metric_ids:
        for bucket_name in (
            "usable_current_metrics",
            "usable_derived_metrics",
            "partial_metrics",
            "derived_not_explicitly_reported",
            "precise_missing_metrics",
            "unreliable_metrics",
        ):
            bucket = payload.get(bucket_name)
            if isinstance(bucket, list):
                for item in bucket:
                    if not isinstance(item, dict):
                        continue
                    candidate = str(item.get("metric_id") or item.get("metric") or item.get("id") or "").strip().lower()
                    if candidate == metric_id and _truth_pack_metric_present(item):
                        return True
        for container_name in (
            "facts_by_metric",
            "metric_registry",
            "metrics",
            "financial_truth_inputs",
            "financial_snapshot_inputs",
            "owner_earnings_readiness_inputs",
            "working_capital_quality_inputs",
            "per_share_compounding_inputs",
        ):
            container = payload.get(container_name)
            if isinstance(container, dict):
                candidate = container.get(metric_id)
                if _truth_pack_metric_present(candidate):
                    return True
    return False


def resolve_committee_financial_truth(
    financial_truth_pack: Dict[str, Any] | None,
    analyst_outputs: Sequence[Dict[str, Any]],
    pcim: Dict[str, Any] | None,
) -> Dict[str, Any]:
    truth_pack = financial_truth_pack if isinstance(financial_truth_pack, dict) else {}
    pcim_payload = pcim if isinstance(pcim, dict) else {}
    analyst_payloads = [payload for payload in analyst_outputs if isinstance(payload, dict)]

    def _from_analyst_truth(*metric_ids: str) -> bool:
        return any(
            _truth_pack_has_metric(payload.get("analyst_financial_truth_pack") or {}, *metric_ids)
            for payload in analyst_payloads
        )

    def _from_selected_payload(*metric_ids: str) -> bool:
        return _truth_pack_has_metric(truth_pack, *metric_ids) or _truth_pack_has_metric(pcim_payload, *metric_ids)

    cfo_available = _from_selected_payload("cfo") or _from_analyst_truth("cfo")
    capex_available = _from_selected_payload(
        "capex",
        "capex_crore",
        "total_identified_capex",
        "ppe_cwip_capex",
        "intangible_capex",
        "capex_deployed",
    ) or _from_analyst_truth(
        "capex",
        "total_identified_capex",
        "ppe_cwip_capex",
        "intangible_capex",
        "capex_deployed",
    )
    fcf_available = _from_selected_payload(
        "fcf",
        "fcf_crore",
        "conservative_fcf_after_total_capex",
        "fcf_after_ppe_cwip_capex",
        "owner_earnings_estimate",
    ) or _from_analyst_truth(
        "fcf",
        "conservative_fcf_after_total_capex",
        "fcf_after_ppe_cwip_capex",
        "owner_earnings_estimate",
    )
    owner_earnings_estimate_available = _from_selected_payload("owner_earnings_estimate") or _from_analyst_truth("owner_earnings_estimate")
    conservative_fcf_available = _from_selected_payload("conservative_fcf_after_total_capex", "fcf_after_ppe_cwip_capex") or _from_analyst_truth(
        "conservative_fcf_after_total_capex",
        "fcf_after_ppe_cwip_capex",
    )
    maintenance_growth_split_available = _from_selected_payload("maintenance_growth_capex_split", "maintenance_capex", "growth_capex") or _from_analyst_truth(
        "maintenance_growth_capex_split",
        "maintenance_capex",
        "growth_capex",
    )
    working_capital_metrics_available = _from_selected_payload("receivable_days", "inventory_days", "payable_days", "cash_conversion_cycle") or _from_analyst_truth(
        "receivable_days",
        "inventory_days",
        "payable_days",
        "cash_conversion_cycle",
    )
    payables_available = _from_selected_payload("payables", "payable_days") or _from_analyst_truth("payables", "payable_days")
    share_count_available = _from_selected_payload("shares_outstanding", "share_count", "closing_shares") or _from_analyst_truth(
        "shares_outstanding",
        "share_count",
        "closing_shares",
    )
    weighted_average_shares_available = _from_selected_payload("weighted_avg_shares") or _from_analyst_truth("weighted_avg_shares")

    basis_candidates = {
        str(((payload.get("financial_assessment") or {}).get("basis_used") or "")).strip().lower()
        for payload in analyst_payloads
        if isinstance(payload.get("financial_assessment"), dict)
    }
    basis_candidates.discard("")
    if "mixed" in basis_candidates or basis_candidates == {"consolidated", "standalone"}:
        basis_status = "mixed"
    elif "consolidated" in basis_candidates and len(basis_candidates) == 1:
        basis_status = "consolidated"
    elif "standalone" in basis_candidates and len(basis_candidates) == 1:
        basis_status = "standalone"
    else:
        basis_status = "unknown"

    maintenance_growth_split_missing = (owner_earnings_estimate_available or conservative_fcf_available) and not maintenance_growth_split_available
    if owner_earnings_estimate_available or conservative_fcf_available:
        owner_earnings_status = "available_derived_precision_limited" if maintenance_growth_split_missing else "available_explicit"
    elif fcf_available:
        owner_earnings_status = "available_explicit"
    elif cfo_available and capex_available:
        owner_earnings_status = "available_derived_precision_limited"
    else:
        owner_earnings_status = "missing"

    return {
        "cfo_available": cfo_available,
        "capex_available": capex_available,
        "fcf_available": fcf_available or (cfo_available and capex_available),
        "owner_earnings_estimate_available": owner_earnings_estimate_available,
        "conservative_fcf_available": conservative_fcf_available,
        "maintenance_growth_split_available": maintenance_growth_split_available,
        "maintenance_growth_split_missing": maintenance_growth_split_missing,
        "working_capital_metrics_available": working_capital_metrics_available,
        "payables_available": payables_available,
        "share_count_available": share_count_available,
        "weighted_average_shares_available": weighted_average_shares_available,
        "basis_status": basis_status,
        "fcf_missing": not (fcf_available or owner_earnings_estimate_available or conservative_fcf_available or (cfo_available and capex_available)),
        "capex_missing": not capex_available,
        "owner_earnings_status": owner_earnings_status,
        "truth_detected": any(
            (
                cfo_available,
                capex_available,
                fcf_available,
                owner_earnings_estimate_available,
                conservative_fcf_available,
                working_capital_metrics_available,
                payables_available,
                share_count_available,
                weighted_average_shares_available,
            )
        ),
    }


FORBIDDEN_COMMITTEE_KEYS = {
    "grounding_status",
    "evidence_grounding_status",
    "validation_status",
    "schema_warnings",
    "raw_validator_output",
    "internal_debug",
    "source_chunk",
    "raw_text",
    "full_text",
    "selected_pcim",
    "prompt",
    "input_pack",
    "token_budget",
    "compacted_sections",
    "source_artifact",
    "source_artifacts",
}

FORBIDDEN_ANALYST_COMMITTEE_KEYS = {
    "pcim_source",
    "supporting_pcim_sections",
    "sections_consumed",
    "evidence_grounding_status",
    "evidence_grounding_warnings",
    "evidence_id_normalization",
    "schema_warnings",
    "generated_at",
    "prompt",
    "input_pack",
    "source_chunk",
    "raw_text",
    "full_text",
    "selected_pcim",
}

SECTION_NAME_EVIDENCE_IDS = PCIM_SECTION_NAME_DENYLIST


COMMITTEE_TEXT_REPLACEMENTS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bnormalized_fundamentals\.json\s*:\s*artifact missing\.?", re.IGNORECASE),
        "Normalized financial fundamentals are missing.",
    ),
    (
        re.compile(r"\bfinancial_validation_report\.json\s*:\s*artifact missing\.?", re.IGNORECASE),
        "Financial validation output is missing.",
    ),
    (
        re.compile(r"\bfinancial_reconciliation_report\.json\s*:\s*artifact missing\.?", re.IGNORECASE),
        "Financial reconciliation output is missing.",
    ),
    (
        re.compile(r"\bfinancial_ratios\.json\s*:\s*artifact missing\.?", re.IGNORECASE),
        "Financial ratio output is missing.",
    ),
    (
        re.compile(r"\bfinancial_growth\.json\s*:\s*artifact missing\.?", re.IGNORECASE),
        "Financial growth output is missing.",
    ),
    (
        re.compile(r"\bfinancial_quality_summary\.json\s*:\s*artifact missing\.?", re.IGNORECASE),
        "Financial quality summary is missing.",
    ),
    (
        re.compile(r"\bfinancial_driver_attribution\.json\s*:\s*artifact missing\.?", re.IGNORECASE),
        "Financial driver-attribution output is missing.",
    ),
    (
        re.compile(r"\bfinancial_audit_report\.json\s*:\s*artifact missing\.?", re.IGNORECASE),
        "Financial audit output is missing.",
    ),
    (
        re.compile(r"\bexisting financial_audit_report\.json is stale relative to\b", re.IGNORECASE),
        "Financial audit output may be stale relative to",
    ),
    (
        re.compile(r"\bfinancial artifacts do not cover all company years\b", re.IGNORECASE),
        "Financial data does not cover all company years",
    ),
    (
        re.compile(r"\bfcf\s*:\s*derived value used\b", re.IGNORECASE),
        "FCF is derived rather than explicitly reported, so treat it as an estimate.",
    ),
    (
        re.compile(r"\bfcf\s*:\s*fcf is derived from normalized inputs\b", re.IGNORECASE),
        "FCF is derived rather than explicitly reported, so treat it as an estimate.",
    ),
    (
        re.compile(r"\bcritical financial fields include unknown basis entries\b", re.IGNORECASE),
        "The reporting basis remains unclear, limiting comparability.",
    ),
    (
        re.compile(r"\bdiluted shares missing\b", re.IGNORECASE),
        "Diluted share-count data is missing, limiting per-share analysis.",
    ),
    (
        re.compile(r"\bfinancial basis remains unknown or unclear\b", re.IGNORECASE),
        "The reporting basis remains unclear, limiting comparability.",
    ),
    (
        re.compile(r"\bfinancial artifacts\b", re.IGNORECASE),
        "financial data",
    ),
    (
        re.compile(r"\bartifacts\b", re.IGNORECASE),
        "outputs",
    ),
    (
        re.compile(r"\bartifact\b", re.IGNORECASE),
        "output",
    ),
)


def _sanitize_committee_text(value: str) -> str:
    sanitized = value
    for pattern, replacement in COMMITTEE_TEXT_REPLACEMENTS:
        sanitized = pattern.sub(replacement, sanitized)
    sanitized = re.sub(
        r"\bowner-earnings readiness\b",
        "owner-earnings assessment readiness",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(r"\s+\.", ".", sanitized)
    sanitized = re.sub(r"\.{2,}", ".", sanitized)
    return sanitized.strip()


def _sanitize_committee_payload(
    value: Any,
    *,
    diagnostics: Optional[Dict[str, Any]] = None,
    path: str = "$",
) -> Any:
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_COMMITTEE_KEYS:
                if diagnostics is not None:
                    diagnostics.setdefault("stripped_fields", []).append(
                        {
                            "path": child_path,
                            "key": key,
                            "value": item,
                        }
                    )
                continue
            sanitized[key] = _sanitize_committee_payload(
                item,
                diagnostics=diagnostics,
                path=child_path,
            )
        return sanitized
    if isinstance(value, list):
        return [
            _sanitize_committee_payload(item, diagnostics=diagnostics, path=f"{path}[{idx}]")
            for idx, item in enumerate(value)
        ]
    if isinstance(value, str):
        sanitized_text = _sanitize_committee_text(value)
        if sanitized_text != value and diagnostics is not None:
            diagnostics.setdefault("rewritten_strings", []).append(
                {
                    "path": path,
                    "original": value,
                    "sanitized": sanitized_text,
                }
            )
        return sanitized_text
    return value


def _analyst_evidence_id_issues(
    value: Any,
    *,
    evidence_lookup: Dict[str, Dict[str, Any]],
    path: str = "$",
) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key == "evidence_ids":
                if not isinstance(item, list):
                    issues.append(
                        {
                            "path": child_path,
                            "invalid_id": str(item),
                            "reason": "evidence_ids field was not a list",
                        }
                    )
                    continue
                for evidence_id in item:
                    evidence_text = str(evidence_id or "").strip()
                    if not evidence_text:
                        continue
                    if evidence_text in PCIM_SECTION_NAME_DENYLIST:
                        issues.append(
                            {
                                "path": child_path,
                                "invalid_id": evidence_text,
                                "reason": "pcim_section_name",
                            }
                        )
                    elif evidence_lookup and evidence_text not in evidence_lookup:
                        issues.append(
                            {
                                "path": child_path,
                                "invalid_id": evidence_text,
                                "reason": "unknown_evidence_id",
                            }
                        )
                continue
            issues.extend(
                _analyst_evidence_id_issues(
                    item,
                    evidence_lookup=evidence_lookup,
                    path=child_path,
                )
            )
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            issues.extend(
                _analyst_evidence_id_issues(
                    item,
                    evidence_lookup=evidence_lookup,
                    path=f"{path}[{idx}]",
                )
            )
    return issues


def _describe_shape(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, list):
        if not value:
            return "list[empty]"
        item_types = {type(item).__name__ for item in value}
        if item_types == {"dict"}:
            if any(isinstance(item, dict) and not item for item in value):
                return "list[dict_empty]"
            return "list[dict]"
        if item_types == {"str"}:
            return "list[str]"
        return "list[mixed]"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, str):
        return "str"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def _committee_shape_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    financial = payload.get("financial_committee_view") if isinstance(payload, dict) else {}
    report_fields = {
        "areas_of_agreement": payload.get("areas_of_agreement"),
        "areas_of_disagreement": payload.get("areas_of_disagreement"),
        "strongest_positive_signals": payload.get("strongest_positive_signals"),
        "most_important_risks": payload.get("most_important_risks"),
        "critical_unknowns": payload.get("critical_unknowns"),
        "investigation_questions": payload.get("investigation_questions"),
        "evidence_quality_notes": payload.get("evidence_quality_notes"),
        "synthesis_limits": payload.get("synthesis_limits"),
    }
    if isinstance(financial, dict):
        for key in (
            "financial_consensus",
            "financial_strengths",
            "financial_concerns",
            "financial_disagreements",
            "missing_financial_data",
            "financial_red_flags",
            "financial_interpretation_limits",
            "investor_questions_from_financials",
        ):
            report_fields[f"financial_committee_view.{key}"] = financial.get(key)
    return {field: _describe_shape(value) for field, value in report_fields.items()}


def _dedupe(items: Sequence[str]) -> List[str]:
    deduped: List[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _normalize_optional_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    normalized: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_casefold_deduped_list(value: Any, *, max_items: int | None = None) -> List[str]:
    items = _normalize_optional_string_list(value)
    normalized: List[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
        if max_items is not None and len(normalized) >= max_items:
            break
    return normalized


def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    trimmed = text[: max(0, limit - 1)].rstrip()
    if "." in trimmed:
        sentence = trimmed.rsplit(".", 1)[0].strip()
        if len(sentence) >= max(40, limit // 3):
            return sentence + "."
    return trimmed.rstrip(",;: ") + "…"


def _ensure_sentence(text: Any) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    if value.endswith((".", "!", "?", "…")):
        return value
    return value + "."


def _normalize_string_list(value: Any, *, max_items: int, max_chars: int) -> List[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = []
    normalized: List[str] = []
    for item in items:
        if isinstance(item, dict):
            candidate = (
                item.get("finding")
                or item.get("flag")
                or item.get("uncertainty")
                or item.get("question")
                or item.get("summary")
                or item.get("value")
                or item.get("issue")
            )
            text = _truncate_text(candidate, max_chars) if candidate is not None else ""
        else:
            text = _truncate_text(item, max_chars)
        if text and text not in normalized:
            normalized.append(text)
        if len(normalized) >= max_items:
            break
    return normalized


def _compact_metric_ids(value: Any, *, max_items: int) -> List[str]:
    metrics = _normalize_optional_string_list(value)
    compacted: List[str] = []
    for metric in metrics:
        lowered = metric.lower()
        candidate = lowered.split("(", 1)[0].strip().replace(" ", "_")
        if candidate and candidate not in compacted:
            compacted.append(candidate)
        if len(compacted) >= max_items:
            break
    return compacted


def _safe_user_brief_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return _truncate_text(value, limit)


def _prioritize_financial_warnings(warnings: Sequence[str]) -> List[str]:
    def sort_key(item: str) -> tuple[int, str]:
        lowered = item.casefold()
        if "free cash flow" in lowered or "fcf" in lowered:
            return (0, lowered)
        if "capex" in lowered:
            return (1, lowered)
        if "basis" in lowered:
            return (2, lowered)
        if "payables" in lowered:
            return (3, lowered)
        if "share count" in lowered or "share-count" in lowered or "weighted average shares" in lowered or "diluted shares" in lowered:
            return (4, lowered)
        if "audit" in lowered or "reconciliation" in lowered:
            return (5, lowered)
        return (6, lowered)

    return sorted(list(warnings), key=sort_key)


def build_sanitized_committee_analyst_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    assessment = payload.get("assessment") or {}
    financial_assessment = payload.get("financial_assessment") or {}
    nested_financial_warnings = _normalize_casefold_deduped_list(
        financial_assessment.get("financial_warnings_carried_forward"),
        max_items=6,
    )
    top_level_warning_fallback = _normalize_casefold_deduped_list(
        payload.get("financial_warnings_carried_forward"),
        max_items=6,
    )
    canonical_financial_warnings = list(nested_financial_warnings)
    if not canonical_financial_warnings:
        canonical_financial_warnings = list(top_level_warning_fallback)
    else:
        major_warning_tokens = ("free cash flow", "fcf", "capex", "payables", "basis", "share count", "share-count")
        existing = {item.casefold() for item in canonical_financial_warnings}
        for warning in top_level_warning_fallback:
            lowered = warning.casefold()
            if lowered in existing:
                continue
            if any(token in lowered for token in major_warning_tokens):
                canonical_financial_warnings.append(warning)
                existing.add(lowered)
    user_facing_brief = payload.get("user_facing_brief") or {}

    invalid_evidence_ids = [
        evidence_id
        for evidence_id in _normalize_optional_string_list(payload.get("evidence_ids"))
        if evidence_id in SECTION_NAME_EVIDENCE_IDS
    ]

    sanitized = {
        "analyst": str(payload.get("doctrine_id") or "").strip().lower(),
        "rating": str(payload.get("rating") or "").strip().lower(),
        "assessment_summary": _normalize_string_list(
            [assessment.get("summary") or assessment.get("overall_assessment")],
            max_items=2,
            max_chars=220,
        ),
        "key_findings": _normalize_string_list(
            payload.get("key_findings"),
            max_items=4,
            max_chars=220,
        ),
        "red_flags": _normalize_string_list(
            payload.get("red_flags"),
            max_items=4,
            max_chars=220,
        ),
        "open_uncertainties": _normalize_string_list(
            payload.get("open_uncertainties"),
            max_items=5,
            max_chars=220,
        ),
        "financial_assessment": {
            "financials_used": bool(financial_assessment.get("financials_used")),
            "basis_used": _truncate_text(financial_assessment.get("basis_used") or "unknown", 40),
            "key_financial_strengths": _normalize_string_list(
                financial_assessment.get("key_financial_strengths")
                or payload.get("financial_positive_signals"),
                max_items=3,
                max_chars=220,
            ),
            "key_financial_concerns": _normalize_string_list(
                financial_assessment.get("key_financial_concerns"),
                max_items=3,
                max_chars=220,
            ),
            "financial_red_flags": _normalize_string_list(
                financial_assessment.get("financial_red_flags")
                or payload.get("financial_red_flags"),
                max_items=3,
                max_chars=220,
            ),
            "precise_missing_financial_data": _normalize_string_list(
                payload.get("precise_missing_financial_data")
                or financial_assessment.get("precise_missing_financial_data"),
                max_items=5,
                max_chars=220,
            ),
            "derived_not_explicitly_reported": _normalize_string_list(
                payload.get("derived_not_explicitly_reported")
                or financial_assessment.get("derived_not_explicitly_reported"),
                max_items=4,
                max_chars=220,
            ),
            "partial_financial_data": _normalize_string_list(
                payload.get("partial_financial_data")
                or financial_assessment.get("partial_financial_data"),
                max_items=4,
                max_chars=220,
            ),
            "unreliable_financial_data": _normalize_string_list(
                payload.get("unreliable_financial_data")
                or financial_assessment.get("unreliable_financial_data"),
                max_items=4,
                max_chars=220,
            ),
            "invalid_or_quarantined_financial_data": _normalize_string_list(
                payload.get("invalid_or_quarantined_financial_data")
                or financial_assessment.get("invalid_or_quarantined_financial_data"),
                max_items=4,
                max_chars=220,
            ),
            "trend_durability_limits": _normalize_string_list(
                payload.get("trend_durability_limits")
                or financial_assessment.get("trend_durability_limits"),
                max_items=4,
                max_chars=220,
            ),
            "missing_financial_data": _normalize_string_list(
                financial_assessment.get("missing_financial_data")
                or payload.get("financial_missing_data"),
                max_items=5,
                max_chars=220,
            ),
            "financial_interpretation_limits": _normalize_string_list(
                financial_assessment.get("financial_interpretation_limits")
                or payload.get("financial_interpretation_limits"),
                max_items=5,
                max_chars=220,
            ),
            "financial_warnings_carried_forward": _normalize_string_list(
                canonical_financial_warnings,
                max_items=6,
                max_chars=220,
            ),
            "financial_questions_for_investor": _normalize_string_list(
                payload.get("financial_questions_for_investor")
                or financial_assessment.get("financial_questions_for_investor"),
                max_items=5,
                max_chars=220,
            ),
        },
        "reasoning_limits": _normalize_string_list(
            payload.get("reasoning_limits"),
            max_items=4,
            max_chars=220,
        ),
        "user_facing_bottom_line": _safe_user_brief_text(
            user_facing_brief.get("bottom_line"),
            220,
        ),
        "user_facing_financial_lens": _safe_user_brief_text(
            user_facing_brief.get("financial_lens") or user_facing_brief.get("lens"),
            220,
        ),
        "schema_warnings": [],
    }
    if invalid_evidence_ids:
        sanitized["schema_warnings"].append(
            "Committee input dropped invalid analyst evidence_ids that matched section names: "
            + ", ".join(invalid_evidence_ids)
        )
    sanitized["financial_assessment"]["financial_warnings_carried_forward"] = _prioritize_financial_warnings(
        sanitized["financial_assessment"]["financial_warnings_carried_forward"]
    )
    for forbidden_key in FORBIDDEN_ANALYST_COMMITTEE_KEYS:
        if forbidden_key != "schema_warnings":
            sanitized.pop(forbidden_key, None)
    return sanitized


def _prune_empty_compact_fields(block: Dict[str, Any]) -> Dict[str, Any]:
    compacted = json.loads(json.dumps(block))
    removable_top_level = (
        "key_strengths",
        "key_concerns",
        "red_flags",
        "doctrine_specific_view",
        "reasoning_limits",
        "evidence_gaps",
        "investor_questions",
    )
    for field in removable_top_level:
        value = compacted.get(field)
        if value in (None, [], "", {}):
            compacted.pop(field, None)

    financial = compacted.get("financial_assessment")
    if isinstance(financial, dict):
        for field in list(financial.keys()):
            value = financial.get(field)
            if value in (None, [], "", {}):
                financial.pop(field, None)
        if not financial:
            compacted.pop("financial_assessment", None)
        else:
            compacted["financial_assessment"] = financial
    return compacted


def _minimal_committee_analyst_block(block: Dict[str, Any]) -> Dict[str, Any]:
    return _prune_empty_compact_fields(
        {
            "analyst": block.get("analyst"),
            "rating": block.get("rating"),
            "view": _truncate_text(block.get("core_view") or block.get("overall_assessment"), 180),
            "risks": _normalize_string_list(block.get("top_risks") or block.get("key_concerns"), max_items=1, max_chars=120),
            "warnings": _normalize_string_list(block.get("financial_warnings"), max_items=3, max_chars=48),
            "unknowns": _normalize_string_list(block.get("critical_unknowns") or block.get("evidence_gaps"), max_items=1, max_chars=120),
        }
    )


def _infer_uncertainty_category(text: str) -> str:
    lowered = str(text or "").lower()
    if any(token in lowered for token in ("free cash flow", "fcf", "capex", "cfo", "debt", "share count", "diluted shares", "weighted average shares", "payables", "basis", "cash flow")):
        return "financials"
    if any(token in lowered for token in ("governance", "compensation", "related party", "board", "control")):
        return "governance"
    if any(token in lowered for token in ("moat", "pricing power", "durability", "switching cost")):
        return "moat"
    if any(token in lowered for token in ("management", "execution", "capital allocation", "reinvestment", "promise")):
        return "management"
    if any(token in lowered for token in ("evidence", "missing", "limited", "uncertain", "unknown", "provisional")):
        return "evidence_gap"
    return "business_quality"


def _canonical_rating_value(value: Any) -> str:
    lowered = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return RATING_ENUM_MAP.get(lowered.replace("_", " "), RATING_ENUM_MAP.get(lowered, "insufficient_evidence"))


def _canonical_confidence_value(analyst_count: int, warning_count: int) -> str:
    if analyst_count <= 2 or warning_count >= 4:
        return "low"
    if analyst_count >= 4 and warning_count <= 1:
        return "high"
    return "medium"


def _deterministic_basis_used(analyst_artifacts: Sequence[Dict[str, Any]]) -> str:
    bases: set[str] = set()
    for payload in analyst_artifacts:
        assessment = payload.get("financial_assessment") or {}
        if not isinstance(assessment, dict):
            continue
        basis = str(assessment.get("basis_used") or "").strip().lower()
        if basis in {"consolidated", "standalone", "mixed"}:
            bases.add(basis)
        elif basis == "unknown":
            continue
    if "mixed" in bases or bases == {"consolidated", "standalone"}:
        return "mixed"
    if bases == {"consolidated"}:
        return "consolidated"
    if bases == {"standalone"}:
        return "standalone"
    return "unknown"


def _dominant_tension_from_inputs(financial_warning_manifest: Dict[str, Any], analyst_artifacts: Sequence[Dict[str, Any]]) -> str:
    ratings = {_canonical_rating_value(payload.get("rating")) for payload in analyst_artifacts}
    if financial_warning_manifest.get("fcf_missing") or financial_warning_manifest.get("capex_missing"):
        return "Growth and business ambition are harder to judge because cash-generation evidence is incomplete."
    if "strong" in ratings and "weak" in ratings:
        return "Analysts differ on how much weight to place on growth progress versus downside and execution risk."
    if financial_warning_manifest.get("basis_unknown"):
        return "Financial interpretation remains constrained by incomplete basis clarity."
    return "The committee view is shaped by how much confidence to place in incomplete but directionally useful evidence."


def _why_it_matters_for_unknown(category: str) -> str:
    mapping = {
        "financials": "This directly limits financial judgment and the ability to assess durability or downside.",
        "governance": "This affects confidence in oversight, incentives, and decision quality.",
        "moat": "This affects whether current business strength is durable or easily competed away.",
        "management": "This affects confidence in execution, capital allocation, and follow-through.",
        "evidence_gap": "This remains a missing-evidence issue that could materially change the investment view.",
        "business_quality": "This affects the quality and durability of the business case.",
    }
    return mapping.get(category, mapping["business_quality"])


def _append_agreement(
    bucket: List[Dict[str, Any]],
    *,
    theme: str,
    summary: str,
    analysts: Sequence[str],
    evidence_limit: str,
) -> None:
    normalized_analysts = [str(item).strip().lower() for item in analysts if str(item).strip()]
    if not theme or not summary or not normalized_analysts:
        return
    bucket.append(
        {
            "theme": theme,
            "summary": summary,
            "source_analysts": normalized_analysts,
            "analysts": normalized_analysts,
            "evidence_ids": [],
            "evidence_limit": evidence_limit,
        }
    )


def build_committee_synthesis_skeleton(
    company: str,
    analyst_artifacts: Sequence[Dict[str, Any]],
    pcim: Dict[str, Any] | None,
    *,
    missing_analysts: Sequence[str] | None = None,
    excluded_analysts: Sequence[str] | None = None,
    warning_notes: Sequence[str] | None = None,
    uncertainty_registry: Sequence[Dict[str, Any]] | None = None,
    financial_warning_manifest: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    included = [payload for payload in analyst_artifacts if isinstance(payload, dict)]
    missing = list(missing_analysts or [])
    excluded = list(excluded_analysts or [])
    notes = list(warning_notes or [])
    registry = list(uncertainty_registry or [])
    financial_manifest = dict(financial_warning_manifest or {})
    committee_financial_truth = dict(financial_manifest.get("committee_financial_truth") or {})
    blocked_warning_phrases = {
        phrase.casefold()
        for payload in included
        for phrase in ((payload.get("analyst_financial_truth_pack") or {}).get("blocked_financial_warnings") or [])
    }
    ratings = [_canonical_rating_value(payload.get("rating")) for payload in included]
    years: List[str] = []
    for payload in included:
        for year in payload.get("years_considered", []) or []:
            if year not in years:
                years.append(year)

    overall_rating = "mixed"
    if included and all(r == "strong" for r in ratings):
        overall_rating = "strong"
    elif included and all(r == "weak" for r in ratings):
        overall_rating = "weak"
    elif not included:
        overall_rating = "insufficient_evidence"

    confidence = _canonical_confidence_value(len(included), len(notes))
    dominant_tension = _dominant_tension_from_inputs(financial_manifest, included)

    evidence_ids: List[str] = []
    for payload in included:
        for evidence_id in payload.get("evidence_ids", []) or []:
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)

    positive_groups: Dict[str, Dict[str, Any]] = {}
    risk_groups: Dict[str, Dict[str, Any]] = {}
    coverage_map: Dict[str, Dict[str, Any]] = {}
    for payload in included:
        sanitized = build_sanitized_committee_analyst_input(payload)
        analyst = sanitized["analyst"]
        coverage_map[analyst] = {
            "rating": _canonical_rating_value(sanitized.get("rating")),
            "years_considered": list(payload.get("years_considered", []) or []),
            "evidence_grounding_status": str(payload.get("evidence_grounding_status") or "unknown"),
            "financials_used": bool((sanitized.get("financial_assessment") or {}).get("financials_used")),
        }
        for item in _normalize_string_list(sanitized.get("key_findings"), max_items=2, max_chars=180):
            group = positive_groups.setdefault(item.casefold(), {"signal": item, "analysts": []})
            if analyst not in group["analysts"]:
                group["analysts"].append(analyst)
        for item in _normalize_string_list(
            (sanitized.get("red_flags") or []) + (sanitized.get("open_uncertainties") or []),
            max_items=3,
            max_chars=180,
        ):
            group = risk_groups.setdefault(item.casefold(), {"risk": item, "analysts": []})
            if analyst not in group["analysts"]:
                group["analysts"].append(analyst)

    strongest_positive_signals = [
        {
            "signal": group["signal"],
            "supported_by": group["analysts"],
            "source_analysts": group["analysts"],
            "summary": f"Raised by {', '.join(group['analysts'])}.",
            "why_it_matters": "This is one of the clearer constructive signals repeated across analyst views.",
            "evidence_ids": [],
            "evidence_limit": "Built deterministically from analyst key findings.",
            "rating": "mixed" if len(group["analysts"]) == 1 else "strong",
        }
        for group in sorted(positive_groups.values(), key=lambda item: (-len(item["analysts"]), item["signal"]))[:5]
    ]

    most_important_risks = [
        {
            "risk": group["risk"],
            "raised_by": group["analysts"],
            "source_analysts": group["analysts"],
            "summary": f"Raised by {', '.join(group['analysts'])}.",
            "why_it_matters": "This remains a central caution in the saved analyst outputs.",
            "severity": "high" if len(group["analysts"]) >= 2 else "medium",
            "evidence_ids": [],
            "evidence_limit": "Built deterministically from analyst red flags and uncertainties.",
        }
        for group in sorted(risk_groups.values(), key=lambda item: (-len(item["analysts"]), item["risk"]))[:5]
    ]

    critical_unknowns: List[Dict[str, Any]] = []
    grouped_unknowns: Dict[str, Dict[str, Any]] = {}
    for entry in registry:
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        key = text.casefold()
        group = grouped_unknowns.setdefault(
            key,
            {
                "unknown": text,
                "raised_by": [],
                "source_uncertainty_ids": [],
                "source_paths": [],
                "category": str(entry.get("category") or "evidence_gap"),
            },
        )
        analyst = str(entry.get("analyst") or "").strip().lower()
        if analyst and analyst not in group["raised_by"]:
            group["raised_by"].append(analyst)
        uncertainty_id = str(entry.get("uncertainty_id") or "").strip()
        if uncertainty_id and uncertainty_id not in group["source_uncertainty_ids"]:
            group["source_uncertainty_ids"].append(uncertainty_id)
        source_path = str(entry.get("source_path") or "").strip()
        if source_path and source_path not in group["source_paths"]:
            group["source_paths"].append(source_path)

    for group in sorted(grouped_unknowns.values(), key=lambda item: (-len(item["raised_by"]), item["unknown"]))[:8]:
        critical_unknowns.append(
            {
                "unknown": group["unknown"],
                "raised_by": group["raised_by"],
                "why_it_matters": _why_it_matters_for_unknown(group["category"]),
                "source_uncertainty_ids": group["source_uncertainty_ids"],
                "evidence_limit": "Grounded in analyst uncertainty registry.",
                "source_path": group["source_paths"][0] if group["source_paths"] else "",
                "grounding_status": "registry_grounded",
            }
        )

    missing_financial_data: List[str] = []
    precise_missing_financial_data: List[str] = []
    derived_not_explicitly_reported: List[str] = []
    unreliable_financial_data: List[str] = []
    invalid_or_quarantined_financial_data: List[str] = []
    trend_durability_limits: List[str] = []
    financial_limits: List[str] = []
    financial_red_flags: List[str] = []
    investor_questions_from_financials: List[str] = []
    for payload in included:
        financial = payload.get("financial_assessment") or {}
        for field_name, target in (
            ("precise_missing_financial_data", precise_missing_financial_data),
            ("derived_not_explicitly_reported", derived_not_explicitly_reported),
            ("unreliable_financial_data", unreliable_financial_data),
            ("invalid_or_quarantined_financial_data", invalid_or_quarantined_financial_data),
            ("trend_durability_limits", trend_durability_limits),
            ("financial_questions_for_investor", investor_questions_from_financials),
        ):
            for item in (payload.get(field_name) or financial.get(field_name) or []):
                text = str(item or "").strip()
                if text:
                    target.append(text)
    financial_strengths = [
        item["signal"] for item in strongest_positive_signals[:3]
    ]
    financial_concerns = [item["risk"] for item in most_important_risks[:3]]

    if financial_manifest.get("fcf_missing"):
        missing_financial_data.append("Free cash flow is missing; FCF-based conclusions cannot be assessed.")
        financial_limits.append("Owner-earnings analysis is limited because free cash flow/capex evidence is incomplete.")
        investor_questions_from_financials.append("What capex and free-cash-flow evidence is needed to assess owner earnings and cash-generation quality?")
        financial_red_flags.append("Cash-generation evidence remains incomplete.")
    elif committee_financial_truth.get("owner_earnings_status") == "available_derived_precision_limited":
        financial_strengths.append(
            "Derived owner-earnings / conservative FCF estimate is available for the current usable year, but precision is limited."
        )
        financial_limits.append(
            "Derived owner-earnings / conservative FCF estimate is available, but precision is limited because maintenance versus growth capex split is unavailable."
        )
        investor_questions_from_financials.append(
            "What maintenance versus growth capex split would make the current owner-earnings estimate more decision-useful?"
        )
    if financial_manifest.get("capex_missing"):
        missing_financial_data.append("Capex evidence is missing or incomplete.")
    if financial_manifest.get("payables_missing"):
        missing_financial_data.append("Payables evidence is missing, limiting cash-conversion analysis.")
    if financial_manifest.get("basis_unknown"):
        financial_limits.append("Standalone versus consolidated basis remains unclear.")
    if financial_manifest.get("weighted_avg_shares_missing") or financial_manifest.get("diluted_shares_missing"):
        financial_limits.append("Share-count evidence is incomplete, so per-share analysis is limited.")

    areas_of_agreement: List[Dict[str, Any]] = []
    if committee_financial_truth.get("owner_earnings_status") == "available_derived_precision_limited":
        _append_agreement(
            areas_of_agreement,
            theme="derived owner-earnings estimate is available but precision-limited",
            summary="Current-year derived FCF / owner-earnings evidence exists, but precision is limited by missing maintenance-versus-growth capex split and incomplete multi-year bridge history.",
            analysts=[payload.get("doctrine_id") for payload in included],
            evidence_limit="Built deterministically from recomputed committee financial truth.",
        )
    if committee_financial_truth.get("maintenance_growth_split_missing"):
        _append_agreement(
            areas_of_agreement,
            theme="maintenance versus growth capex split remains unavailable",
            summary="Capex is identified, but the maintenance-versus-growth split is still unavailable, which limits owner-earnings precision.",
            analysts=[payload.get("doctrine_id") for payload in included],
            evidence_limit="Built deterministically from recomputed committee financial truth.",
        )
    if committee_financial_truth.get("working_capital_metrics_available"):
        _append_agreement(
            areas_of_agreement,
            theme="working-capital intensity is severe",
            summary="Working-capital metrics are available and keep cash-conversion pressure in view even when current-year metrics are usable.",
            analysts=[payload.get("doctrine_id") for payload in included if payload.get("doctrine_id")],
            evidence_limit="Built deterministically from recomputed committee financial truth and analyst financial sections.",
        )
    if committee_financial_truth.get("basis_status") == "unknown":
        _append_agreement(
            areas_of_agreement,
            theme="basis clarity remains incomplete",
            summary="The reporting basis remains unclear enough to limit full comparability across some financial conclusions.",
            analysts=list(financial_manifest.get("basis_unknown_analysts", [])) or [payload.get("doctrine_id") for payload in included],
            evidence_limit="Built deterministically from recomputed committee financial truth.",
        )

    areas_of_disagreement: List[Dict[str, Any]] = []
    if "strong" in ratings and ("weak" in ratings or "mixed" in ratings):
        positive = sorted(
            analyst for analyst, meta in coverage_map.items() if meta["rating"] == "strong"
        )
        cautious = sorted(
            analyst for analyst, meta in coverage_map.items() if meta["rating"] in {"weak", "mixed"}
        )
        areas_of_disagreement.append(
            {
                "theme": "growth versus downside weighting",
                "disagreement_type": "risk_weighting_difference",
                "summary": "Analysts do not disagree on the facts so much as on how heavily to weight growth signals against downside and execution risk.",
                "why_it_matters": "That weighting changes how much uncertainty an investor must tolerate.",
                "analysts_positive_or_less_concerned": positive,
                "analysts_cautious_or_negative": cautious,
                "evidence_ids": [],
                "evidence_limit": "Built deterministically from analyst rating dispersion.",
            }
        )

    investigation_questions = [
        {
            "question": unknown["unknown"],
            "reason": unknown["why_it_matters"],
            "linked_unknown_or_risk": unknown["unknown"],
        }
        for unknown in critical_unknowns[:5]
    ]

    skeleton = {
        "company": company,
        "analysis_mode": "committee_synthesis_v1",
        "analysts_considered": [str(payload.get("doctrine_id") or "").strip().lower() for payload in included],
        "missing_analysts": missing,
        "excluded_analysts": excluded,
        "years_considered": years,
        "overall_committee_view": {
            "summary": "The committee view is being built from deterministic analyst evidence and may be refined by narrative synthesis.",
            "confidence": confidence,
            "dominant_tension": dominant_tension,
            "rating": overall_rating,
        },
        "financial_committee_view": {
            "financials_used": any(bool(meta.get("financials_used")) for meta in coverage_map.values()),
            "basis_used": _deterministic_basis_used(included),
            "financial_consensus": [],
            "financial_strengths": financial_strengths,
            "financial_concerns": financial_concerns,
            "financial_disagreements": [],
            "missing_financial_data": _dedupe(missing_financial_data),
            "precise_missing_financial_data": _dedupe(precise_missing_financial_data),
            "derived_not_explicitly_reported": _dedupe(derived_not_explicitly_reported),
            "unreliable_financial_data": _dedupe(unreliable_financial_data),
            "invalid_or_quarantined_financial_data": _dedupe(invalid_or_quarantined_financial_data),
            "trend_durability_limits": _dedupe(trend_durability_limits),
            "financial_red_flags": _dedupe(financial_red_flags),
            "financial_interpretation_limits": _dedupe(financial_limits),
            "investor_questions_from_financials": _dedupe(investor_questions_from_financials),
        },
        "areas_of_agreement": areas_of_agreement,
        "areas_of_disagreement": areas_of_disagreement,
        "strongest_positive_signals": strongest_positive_signals,
        "most_important_risks": most_important_risks,
        "critical_unknowns": critical_unknowns,
        "investigation_questions": investigation_questions,
        "evidence_ids": evidence_ids,
        "evidence_quality_notes": notes,
        "synthesis_limits": ["Committee structure was built deterministically from saved analyst artifacts."],
        "generated_at": utc_now(),
        "evidence_id_normalization": {"applied": False, "replacements": [], "unresolved_ids": []},
        "analyst_coverage_map": coverage_map,
        "financial_warning_manifest": financial_manifest,
        "committee_financial_truth": committee_financial_truth,
        "blocked_financial_warning_manifest": sorted(blocked_warning_phrases),
        "executive_committee_summary": "",
        "synthesis_narrative": [],
        "disagreement_explanation": [],
        "what_to_watch_next": [],
        "ungrounded_suggested_unknowns": [],
    }
    return skeleton


def finalize_committee_financial_warnings(payload: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = json.loads(json.dumps(payload, ensure_ascii=False))
    blocked = {
        str(item or "").strip().casefold()
        for item in cleaned.get("blocked_financial_warning_manifest", []) or []
        if str(item or "").strip()
    }
    rewrites = {
        str(item or "").strip().casefold(): str(item or "").strip()
        for item in ((cleaned.get("financial_warning_policy") or {}).get("financial_warnings_rewritten", []) or [])
        if str(item or "").strip()
    }
    if not blocked:
        return cleaned

    def _should_block(text: str) -> bool:
        lowered = str(text or "").strip().casefold()
        return any(phrase in lowered for phrase in blocked)

    def _rewrite(text: str) -> str:
        lowered = str(text or "").strip().casefold()
        for phrase in blocked:
            if phrase in lowered:
                for replacement in rewrites.values():
                    if replacement:
                        return replacement
        return str(text or "").strip()

    financial_view = cleaned.get("financial_committee_view")
    if isinstance(financial_view, dict):
        for field in ("missing_financial_data", "financial_interpretation_limits", "financial_red_flags", "investor_questions_from_financials"):
            values = []
            for item in financial_view.get(field, []) or []:
                text = str(item or "").strip()
                if not text:
                    continue
                if _should_block(text):
                    replacement = _rewrite(text)
                    if replacement:
                        values.append(replacement)
                    continue
                values.append(text)
            financial_view[field] = _dedupe(values)

    critical_unknowns = []
    for item in cleaned.get("critical_unknowns", []) or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("unknown") or "").strip()
        if text and _should_block(text):
            replacement = _rewrite(text)
            if replacement:
                item = dict(item)
                item["unknown"] = replacement
            else:
                continue
        critical_unknowns.append(item)
    cleaned["critical_unknowns"] = critical_unknowns

    for field in ("areas_of_agreement", "strongest_positive_signals", "most_important_risks", "investigation_questions"):
        sanitized_items = []
        for item in cleaned.get(field, []) or []:
            if not isinstance(item, dict):
                continue
            blob = " ".join(
                str(item.get(key) or "").strip()
                for key in ("theme", "summary", "signal", "risk", "question", "reason", "linked_unknown_or_risk", "why_it_matters")
            ).strip()
            if blob and _should_block(blob):
                replacement = _rewrite(blob)
                if field == "investigation_questions" and replacement:
                    item = dict(item)
                    item["question"] = replacement if replacement.endswith("?") else f"{replacement}?"
                    item["reason"] = "This remains a precision limit rather than a fully missing-data gap."
                    sanitized_items.append(item)
                continue
            sanitized_items.append(item)
        cleaned[field] = sanitized_items
    return cleaned


def finalize_financial_committee_view(
    financial_committee_view: Dict[str, Any] | None,
    committee_financial_truth: Dict[str, Any] | None,
) -> tuple[Dict[str, Any], List[str], List[str]]:
    view = json.loads(json.dumps(financial_committee_view or {}, ensure_ascii=False))
    truth = committee_financial_truth if isinstance(committee_financial_truth, dict) else {}
    blocked_stale_financial_warnings: List[str] = []
    repairs: List[str] = []

    def _rewrite_items(field: str) -> None:
        values = []
        for item in view.get(field, []) or []:
            text = str(item or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if truth.get("fcf_missing") is False and ("free cash flow is missing" in lowered or "fcf missing" in lowered):
                blocked_stale_financial_warnings.append(text)
                repairs.append(f"{field}: blocked stale FCF-missing warning")
                continue
            if truth.get("capex_missing") is False and "capex missing" in lowered:
                blocked_stale_financial_warnings.append(text)
                repairs.append(f"{field}: blocked stale capex-missing warning")
                continue
            if (
                "owner earnings" in lowered
                and truth.get("owner_earnings_status") == "available_derived_precision_limited"
                and field == "financial_strengths"
            ):
                text = (
                    "Derived owner-earnings / conservative FCF estimate is available for the current usable year, "
                    "supported by available CFO and identified capex, but precision is limited because maintenance "
                    "versus growth capex split is unavailable."
                )
                repairs.append(f"{field}: rewrote owner-earnings strength to precision-limited wording")
            values.append(text)
        view[field] = _dedupe(values)

    for field_name in (
        "financial_strengths",
        "financial_concerns",
        "missing_financial_data",
        "financial_red_flags",
        "financial_interpretation_limits",
        "investor_questions_from_financials",
    ):
        _rewrite_items(field_name)

    if truth.get("owner_earnings_status") == "available_derived_precision_limited":
        limit = (
            "Derived owner-earnings / conservative FCF estimate is available, but precision is limited because "
            "maintenance versus growth capex split is unavailable."
        )
        if limit not in view.get("financial_interpretation_limits", []):
            view.setdefault("financial_interpretation_limits", []).append(limit)
            repairs.append("financial_interpretation_limits: added owner-earnings precision limitation")

    return view, blocked_stale_financial_warnings, repairs


class InvestmentCommitteeSynthesizer:
    TARGET_TOTAL_PROMPT_TOKENS = 5650
    PROMPT_SAFETY_MARGIN_TOKENS = 300
    MAX_SCHEMA_PROMPT_TOKENS = 350
    MAX_ANALYST_BLOCK_TOKENS = 450
    PREFERRED_ANALYST_BLOCK_TOKENS = 425
    ANALYST_FIELD_CAPS = {
        "top_positive_signals": 2,
        "top_risks": 2,
        "financial_strengths": 2,
        "financial_concerns": 2,
        "financial_warnings": 3,
        "critical_unknowns": 2,
        "evidence_limits": 2,
    }
    ANALYST_STRING_LIMIT = 160
    CORE_VIEW_LIMIT = 280
    FINANCIAL_ITEM_LIMIT = 140
    ANALYST_CHAR_BUDGET = 950
    EMERGENCY_ANALYST_CHAR_BUDGET = 700
    FINAL_PROMPT_ANALYST_CHAR_BUDGET = 560
    ULTRA_COMPACT_ANALYST_CHAR_BUDGET = 420
    SOFT_MAX_PROMPT_CHARS = 28000

    def __init__(self, company: str, companies_root: Path | str = Path("companies")):
        self.company = company
        self.companies_root = Path(companies_root)
        self.panel_dir = self.companies_root / company / "company_memory" / "investor_panel"
        self.output_path = self.panel_dir / "committee_synthesis.json"
        self.diagnostics_path = self.panel_dir / "committee_synthesis_diagnostics.json"
        self.llm = get_llm()

    def _analysis_path(self, analyst: str) -> Path:
        return self.panel_dir / f"{analyst}_analysis.json"

    def _analysis_diagnostics_path(self, analyst: str) -> Path:
        return self.panel_dir / f"{analyst}_analysis_diagnostics.json"

    def _pcim_path(self) -> Path:
        return self.companies_root / self.company / "company_memory" / "pcim_v1.json"

    def _load_analyst_payload(self, analyst: str) -> Optional[Dict[str, Any]]:
        path = self._analysis_path(analyst)
        if not path.exists():
            return None
        payload = _load_json(path)
        validate_analyst_payload(payload, analyst=analyst)
        diagnostics_path = self._analysis_diagnostics_path(analyst)
        if diagnostics_path.exists():
            payload["_diagnostics"] = _load_json(diagnostics_path)
        return payload

    def _load_inputs(self) -> Tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
        included: List[Dict[str, Any]] = []
        missing: List[str] = []
        excluded: List[str] = []
        warning_notes: List[str] = []
        evidence_lookup: Dict[str, Dict[str, Any]] = {}
        pcim = _load_json(self._pcim_path())
        if pcim:
            evidence_lookup = build_evidence_lookup(pcim)

        for analyst in EXPECTED_ANALYSTS:
            payload = self._load_analyst_payload(analyst)
            if payload is None:
                missing.append(analyst)
                continue

            status = str(payload.get("evidence_grounding_status") or "").strip().lower()
            diagnostics = payload.get("_diagnostics") or {}
            warning_count = len(diagnostics.get("evidence_grounding_warnings") or [])
            unresolved_count = len(
                ((diagnostics.get("evidence_id_normalization") or {}).get("unresolved_ids") or [])
            )
            final_evidence_issues = _analyst_evidence_id_issues(
                payload,
                evidence_lookup=evidence_lookup,
            )
            if status == "fail":
                if final_evidence_issues:
                    excluded.append(analyst)
                    warning_notes.append(
                        f"{analyst} was excluded because final analyst evidence IDs remain invalid "
                        f"after sanitization: {final_evidence_issues[:3]}."
                    )
                    continue
                warning_notes.append(
                    f"{analyst} had stale evidence grounding failure metadata but final saved "
                    "evidence_ids are clean; included with warning."
                )

            if status == "warning":
                warning_notes.append(
                    f"{analyst} included with evidence grounding warnings: {warning_count} issue(s)."
                )
            if final_evidence_issues:
                excluded.append(analyst)
                warning_notes.append(
                    f"{analyst} was excluded because final analyst evidence IDs are invalid: "
                    f"{final_evidence_issues[:3]}."
                )
                continue

            included.append(payload)

        return included, missing, excluded, warning_notes

    def _compact_analyst_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = build_sanitized_committee_analyst_input(payload)
        financial_assessment = sanitized.get("financial_assessment") or {}
        combined_positive = _normalize_string_list(
            (sanitized.get("key_findings") or []) + (financial_assessment.get("key_financial_strengths") or []),
            max_items=self.ANALYST_FIELD_CAPS["top_positive_signals"],
            max_chars=self.ANALYST_STRING_LIMIT,
        )
        combined_risks = _normalize_string_list(
            (sanitized.get("red_flags") or [])
            + (sanitized.get("open_uncertainties") or [])
            + (financial_assessment.get("key_financial_concerns") or []),
            max_items=self.ANALYST_FIELD_CAPS["top_risks"],
            max_chars=self.ANALYST_STRING_LIMIT,
        )
        core_view_source = (
            sanitized.get("assessment_summary")
            or sanitized.get("key_findings")
            or sanitized.get("open_uncertainties")
        )
        warning_keys = self._warning_keys_for_payload(payload)
        compacted = {
            "analyst": sanitized["analyst"],
            "rating": sanitized["rating"],
            "core_view": _truncate_text(" ".join(core_view_source or []), self.CORE_VIEW_LIMIT),
            "top_positive_signals": combined_positive,
            "top_risks": combined_risks,
            "financial_strengths": _normalize_string_list(
                financial_assessment.get("key_financial_strengths"),
                max_items=self.ANALYST_FIELD_CAPS["financial_strengths"],
                max_chars=self.FINANCIAL_ITEM_LIMIT,
            ),
            "financial_concerns": _normalize_string_list(
                (financial_assessment.get("key_financial_concerns") or [])
                + (financial_assessment.get("financial_red_flags") or []),
                max_items=self.ANALYST_FIELD_CAPS["financial_concerns"],
                max_chars=self.FINANCIAL_ITEM_LIMIT,
            ),
            "financial_warnings": warning_keys[: self.ANALYST_FIELD_CAPS["financial_warnings"]],
            "critical_unknowns": _normalize_string_list(
                (sanitized.get("open_uncertainties") or [])
                + (financial_assessment.get("missing_financial_data") or []),
                max_items=self.ANALYST_FIELD_CAPS["critical_unknowns"],
                max_chars=self.ANALYST_STRING_LIMIT,
            ),
            "evidence_limits": _normalize_string_list(
                (financial_assessment.get("financial_interpretation_limits") or [])
                + (sanitized.get("reasoning_limits") or []),
                max_items=self.ANALYST_FIELD_CAPS["evidence_limits"],
                max_chars=self.ANALYST_STRING_LIMIT,
            ),
        }
        compacted = _prune_empty_compact_fields(compacted)
        compacted = self._enforce_analyst_char_budget(compacted, self.ANALYST_CHAR_BUDGET)
        return self._enforce_analyst_token_budget(compacted, self.PREFERRED_ANALYST_BLOCK_TOKENS)

    def _enforce_analyst_char_budget(self, block: Dict[str, Any], max_chars: int) -> Dict[str, Any]:
        compacted = json.loads(json.dumps(block))
        removable_fields = [
            "evidence_limits",
            "top_positive_signals",
            "financial_strengths",
        ]
        while len(json.dumps(compacted, ensure_ascii=False)) > max_chars:
            changed = False
            for field in removable_fields:
                values = compacted.get(field)
                if isinstance(values, list) and len(values) > 1:
                    compacted[field] = values[:-1]
                    changed = True
                    break
            if changed:
                continue
            if isinstance(compacted.get("core_view"), str) and len(compacted["core_view"]) > 180:
                compacted["core_view"] = _truncate_text(compacted["core_view"], 180)
                changed = True
            if changed:
                continue
            for field in ("top_positive_signals", "top_risks", "financial_strengths", "financial_concerns", "critical_unknowns", "evidence_limits"):
                values = compacted.get(field)
                if isinstance(values, list) and values:
                    longest = max(range(len(values)), key=lambda idx: len(str(values[idx] or "")))
                    shortened = _truncate_text(values[longest], 120)
                    if shortened != values[longest]:
                        values[longest] = shortened
                        compacted[field] = values
                        changed = True
                        break
            if changed:
                continue
            for field in ("top_positive_signals", "top_risks", "financial_strengths", "financial_concerns", "critical_unknowns", "evidence_limits"):
                values = compacted.get(field)
                if isinstance(values, list) and len(values) > 1:
                    compacted[field] = values[:1]
                    changed = True
                    break
            if changed:
                continue
            if isinstance(compacted.get("core_view"), str) and len(compacted["core_view"]) > 140:
                compacted["core_view"] = _truncate_text(compacted["core_view"], 140)
                changed = True
            if changed:
                continue
            for field in ("evidence_limits", "top_positive_signals", "financial_strengths"):
                values = compacted.get(field)
                if isinstance(values, list) and values:
                    compacted[field] = []
                    changed = True
                    break
            if changed:
                continue
            for field in ("critical_unknowns", "financial_concerns", "top_risks"):
                values = compacted.get(field)
                if isinstance(values, list) and values and len(json.dumps(compacted, ensure_ascii=False)) > max_chars:
                    compacted[field] = []
                    changed = True
                    break
            if changed:
                continue
            break
        return compacted

    def _warning_keys_for_payload(self, payload: Dict[str, Any]) -> List[str]:
        manifest = self._build_committee_financial_warning_manifest([payload])
        keys: List[str] = []
        for key in (
            "fcf_missing",
            "capex_missing",
            "weighted_avg_shares_missing",
            "diluted_shares_missing",
            "payables_missing",
            "basis_unknown",
            "working_capital_risk",
        ):
            if manifest.get(key):
                keys.append(key)
        return keys

    def _enforce_analyst_token_budget(self, block: Dict[str, Any], max_tokens: int) -> Dict[str, Any]:
        compacted = json.loads(json.dumps(block))
        while estimate_tokens(json.dumps(compacted, ensure_ascii=False)) > max_tokens:
            changed = False
            for field in ("evidence_limits", "top_positive_signals", "financial_strengths"):
                values = compacted.get(field)
                if isinstance(values, list) and values:
                    compacted[field] = values[:-1]
                    changed = True
                    break
            if changed:
                continue
            for field in ("critical_unknowns", "financial_concerns", "top_risks"):
                values = compacted.get(field)
                if isinstance(values, list) and len(values) > 1:
                    compacted[field] = values[:1]
                    changed = True
                    break
            if changed:
                continue
            if isinstance(compacted.get("core_view"), str) and len(compacted["core_view"]) > 180:
                compacted["core_view"] = _truncate_text(compacted["core_view"], 180)
                changed = True
            if changed:
                continue
            compacted = _minimal_committee_analyst_block(compacted)
            if estimate_tokens(json.dumps(compacted, ensure_ascii=False)) <= max_tokens:
                break
            if isinstance(compacted.get("view"), str) and len(compacted["view"]) > 140:
                compacted["view"] = _truncate_text(compacted["view"], 140)
            break
        return _prune_empty_compact_fields(compacted)

    def _build_committee_financial_warning_manifest(
        self,
        included: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        pcim_payload = _load_json(self._pcim_path())
        company_truth_pack_path = self.companies_root / self.company / "company_memory" / "financials" / "financial_truth_pack.json"
        company_truth_pack = _load_json(company_truth_pack_path)
        committee_financial_truth = resolve_committee_financial_truth(company_truth_pack, included, pcim_payload)
        truth_detected = bool(committee_financial_truth.get("truth_detected"))
        manifest = {
            "fcf_missing": bool(committee_financial_truth.get("fcf_missing")) if truth_detected else False,
            "capex_missing": bool(committee_financial_truth.get("capex_missing")) if truth_detected else False,
            "payables_missing": False,
            "weighted_avg_shares_missing": False,
            "diluted_shares_missing": False,
            "basis_unknown": committee_financial_truth.get("basis_status") == "unknown" if truth_detected else False,
            "working_capital_risk": False,
            "audit_or_reconciliation_warnings": [],
            "missing_fcf": [],
            "missing_capex": [],
            "missing_payables": [],
            "basis_unknown_analysts": [],
            "share_count_limitations": [],
            "blocked_stale_financial_warnings": [],
            "committee_financial_truth": committee_financial_truth,
        }
        for payload in included:
            sanitized = build_sanitized_committee_analyst_input(payload)
            analyst = sanitized.get("analyst") or str(payload.get("doctrine_id") or "")
            financial = sanitized.get("financial_assessment") or {}
            combined = (
                _normalize_optional_string_list(financial.get("financial_warnings_carried_forward"))
                + _normalize_optional_string_list(financial.get("financial_interpretation_limits"))
                + _normalize_optional_string_list(financial.get("missing_financial_data"))
            )
            lowered_blob = " ".join(item.lower() for item in combined)
            if "free cash flow" in lowered_blob or "fcf" in lowered_blob:
                if not truth_detected:
                    manifest["fcf_missing"] = True
                else:
                    manifest["blocked_stale_financial_warnings"].extend(
                        item for item in combined if "free cash flow" in item.lower() or "fcf" in item.lower()
                    )
                if analyst and analyst not in manifest["missing_fcf"]:
                    manifest["missing_fcf"].append(analyst)
            if "capex" in lowered_blob:
                if not truth_detected:
                    manifest["capex_missing"] = True
                else:
                    manifest["blocked_stale_financial_warnings"].extend(
                        item for item in combined if "capex" in item.lower()
                    )
                if analyst and analyst not in manifest["missing_capex"]:
                    manifest["missing_capex"].append(analyst)
            if "payables" in lowered_blob:
                if not truth_detected:
                    manifest["payables_missing"] = True
                else:
                    manifest["blocked_stale_financial_warnings"].extend(
                        item for item in combined if "payables" in item.lower()
                    )
                if analyst and analyst not in manifest["missing_payables"]:
                    manifest["missing_payables"].append(analyst)
                manifest["working_capital_risk"] = True
            if "weighted average shares" in lowered_blob:
                manifest["weighted_avg_shares_missing"] = True
            if "diluted shares" in lowered_blob:
                manifest["diluted_shares_missing"] = True
            if (not truth_detected or not committee_financial_truth.get("share_count_available")) and ("share-count" in lowered_blob or "share count" in lowered_blob):
                if analyst and analyst not in manifest["share_count_limitations"]:
                    manifest["share_count_limitations"].append(analyst)
            if "basis" in lowered_blob and "unknown" in lowered_blob:
                if not truth_detected:
                    manifest["basis_unknown"] = True
                if analyst and analyst not in manifest["basis_unknown_analysts"]:
                    manifest.setdefault("basis_unknown_analysts", []).append(analyst)
            if any(token in lowered_blob for token in ("reconciliation", "audit", "validation warning")):
                manifest["audit_or_reconciliation_warnings"].extend(combined)
        manifest["audit_or_reconciliation_warnings"] = _normalize_casefold_deduped_list(
            manifest["audit_or_reconciliation_warnings"]
        )
        manifest["blocked_stale_financial_warnings"] = _normalize_casefold_deduped_list(
            manifest["blocked_stale_financial_warnings"]
        )
        if manifest["missing_payables"] and (not truth_detected or not committee_financial_truth.get("payables_available")):
            manifest["payables_missing"] = True
            manifest["working_capital_risk"] = True
        if not truth_detected or not committee_financial_truth.get("weighted_average_shares_available"):
            weighted_mentions = [
                payload for payload in included
                if "weighted average shares" in " ".join(
                    _flatten_strings((payload.get("financial_assessment") or {}).get("missing_financial_data"))
                    + _flatten_strings((payload.get("financial_assessment") or {}).get("financial_interpretation_limits"))
                    + _flatten_strings(payload.get("financial_warnings_carried_forward") or [])
                ).lower()
            ]
            if weighted_mentions:
                manifest["weighted_avg_shares_missing"] = True
        return manifest

    def _build_committee_input(
        self,
        included: Sequence[Dict[str, Any]],
        missing: Sequence[str],
        excluded: Sequence[str],
        warning_notes: Sequence[str],
    ) -> Dict[str, Any]:
        analysts = [self._compact_analyst_input(payload) for payload in included]
        analysts = self._apply_dynamic_analyst_budget(analysts)
        committee_input_bundle_v2 = self._build_committee_input_bundle_v2(
            analysts=analysts,
            missing=missing,
            excluded=excluded,
            warning_notes=warning_notes,
        )
        return {
            "company": self.company,
            "analysts": analysts,
            "missing_analysts": list(missing),
            "excluded_analysts": list(excluded),
            "evidence_quality_notes": list(warning_notes),
            "financial_warning_manifest": self._build_committee_financial_warning_manifest(included),
            "allowed_critical_unknowns_registry": self._build_uncertainty_registry(included),
            "committee_input_bundle_v2": committee_input_bundle_v2,
            "shared_progression": committee_input_bundle_v2.get("shared_progression", {}),
        }

    def _build_committee_input_bundle_v2(
        self,
        *,
        analysts: Sequence[Dict[str, Any]],
        missing: Sequence[str],
        excluded: Sequence[str],
        warning_notes: Sequence[str],
    ) -> Dict[str, Any]:
        company_root = self.companies_root / self.company
        doctrine_contexts: List[Dict[str, Any]] = []
        per_doctrine_budget = max(
            400,
            min(
                900,
                max(400, resolve_stage_token_budget("committee_synthesis") // 8),
            ),
        )
        for doctrine_id in EXPECTED_ANALYSTS:
            context = build_company_memory_context(
                company_root,
                doctrine_id,
                token_budget=per_doctrine_budget,
            )
            if context:
                doctrine_contexts.append(context)

        seen_streams: set[str] = set()
        merged_streams: List[Dict[str, Any]] = []
        streams_considered: List[str] = []
        latest_years: List[str] = []
        evidence_ids: List[str] = []
        source_artifact_count = 0
        limitations: List[str] = []

        def _extend_unique(bucket: List[str], values: Sequence[str]) -> None:
            for value in values:
                text = str(value or "").strip()
                if text and text not in bucket:
                    bucket.append(text)

        for context in doctrine_contexts:
            _extend_unique(streams_considered, context.get("streams_considered") or [])
            _extend_unique(latest_years, context.get("latest_years") or [])
            _extend_unique(limitations, context.get("limitations") or [])
            _extend_unique(evidence_ids, context.get("evidence_ids") or [])
            source_artifact_count += int(context.get("source_artifact_count") or 0)
            for stream in context.get("streams", []) or []:
                if not isinstance(stream, dict):
                    continue
                stream_name = str(stream.get("stream") or "").strip()
                if not stream_name or stream_name in seen_streams:
                    continue
                seen_streams.add(stream_name)
                merged_streams.append(json.loads(json.dumps(stream, ensure_ascii=False)))

        streams_by_name = {
            str(stream.get("stream") or "").strip().lower(): stream
            for stream in merged_streams
            if isinstance(stream, dict) and str(stream.get("stream") or "").strip()
        }
        shared_progression = {
            "company": self.company,
            "context_version": "v2",
            "latest_years": latest_years[:5],
            "streams_considered": streams_considered[:12] if streams_considered else list(COMMITTEE_V2_STREAM_PRIORITY),
            "streams_found": [stream.get("stream") for stream in merged_streams if isinstance(stream, dict) and stream.get("stream")],
            "streams_missing": [name for name in COMMITTEE_V2_STREAM_PRIORITY if name not in streams_by_name],
            "streams": merged_streams[:7],
            "streams_by_name": streams_by_name,
            "evidence_ids": evidence_ids[:30],
            "source_artifact_count": source_artifact_count,
            "limitations": _dedupe(
                limitations
                + [
                    "Committee progression context is compact and prioritizes the clearest longitudinal streams."
                ]
            ),
        }

        financial_truth_pack = _load_json(
            company_root / "company_memory" / "financials" / "financial_truth_pack.json"
        )
        shared_progression["financial_truth"] = {
            "company": self.company,
            "schema_version": financial_truth_pack.get("schema_version"),
            "generated_at": financial_truth_pack.get("generated_at"),
            "basis_used": financial_truth_pack.get("basis_used"),
            "owner_earnings_status": financial_truth_pack.get("owner_earnings_status"),
            "owner_earnings_estimate_available": financial_truth_pack.get("owner_earnings_estimate_available"),
            "fcf_missing": financial_truth_pack.get("fcf_missing"),
            "capex_missing": financial_truth_pack.get("capex_missing"),
            "payables_available": financial_truth_pack.get("payables_available"),
            "weighted_average_shares_available": financial_truth_pack.get("weighted_average_shares_available"),
            "summary": _truncate_text(financial_truth_pack.get("summary") or financial_truth_pack.get("financial_memory_summary"), 260),
            "limitations": _normalize_optional_string_list(financial_truth_pack.get("limitations")),
            "warnings": _normalize_optional_string_list(financial_truth_pack.get("warnings")),
        }
        for stream_name in (
            "management quality",
            "management commitments",
            "projects",
            "capacity evolution",
            "risk evolution",
            "management commentary",
            "capital allocation outcomes",
            "financial memory",
        ):
            shared_progression[stream_name.replace(" ", "_")] = streams_by_name.get(stream_name)

        analyst_outputs = {
            str(item.get("analyst") or item.get("doctrine_id") or "").strip().lower(): json.loads(
                json.dumps(item, ensure_ascii=False)
            )
            for item in analysts
            if isinstance(item, dict) and str(item.get("analyst") or item.get("doctrine_id") or "").strip()
        }
        analyst_evidence_ids: List[str] = []
        for item in analysts:
            if not isinstance(item, dict):
                continue
            _extend_unique(analyst_evidence_ids, _normalize_optional_string_list(item.get("evidence_ids")))
        evidence_coverage = {
            "analysts_considered": list(analyst_outputs.keys()),
            "analyst_count": len(analyst_outputs),
            "shared_stream_count": len(merged_streams),
            "source_artifact_count": source_artifact_count,
            "analyst_evidence_ids": analyst_evidence_ids[:40],
            "shared_evidence_ids": evidence_ids[:30],
        }

        return {
            "company_identity": {
                "company": self.company,
                "company_root": str(company_root),
                "analysis_mode": "committee_synthesis_v2",
            },
            "analyst_outputs": analyst_outputs,
            "shared_progression": shared_progression,
            "evidence_coverage": evidence_coverage,
            "limitations": _dedupe(
                _normalize_optional_string_list(warning_notes)
                + list(shared_progression.get("limitations") or [])
                + [
                    "Committee synthesis reads compact progression summaries, not raw company-memory blobs."
                ]
            ),
        }

    def _build_committee_narrative_input(
        self,
        *,
        skeleton: Dict[str, Any],
        committee_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        deterministic_disagreements = [
            {
                "theme": item.get("theme"),
                "disagreement_type": item.get("disagreement_type"),
                "analysts_positive_or_less_concerned": item.get("analysts_positive_or_less_concerned", []),
                "analysts_cautious_or_negative": item.get("analysts_cautious_or_negative", []),
                "summary": item.get("summary", ""),
                "why_it_matters": item.get("why_it_matters", ""),
            }
            for item in skeleton.get("areas_of_disagreement", [])
            if isinstance(item, dict)
        ]
        return {
            "company": self.company,
            "analyst_ratings": {
                item.get("analyst"): item.get("rating")
                for item in committee_input.get("analysts", [])
                if isinstance(item, dict) and item.get("analyst")
            },
            "top_positive_signals": [
                {"signal": item.get("signal"), "supported_by": item.get("supported_by", [])}
                for item in skeleton.get("strongest_positive_signals", [])[:5]
                if isinstance(item, dict)
            ],
            "top_risks": [
                {"risk": item.get("risk"), "raised_by": item.get("raised_by", [])}
                for item in skeleton.get("most_important_risks", [])[:5]
                if isinstance(item, dict)
            ],
            "financial_warning_manifest": skeleton.get("financial_warning_manifest", {}),
            "critical_unknown_registry": [
                {
                    "unknown": item.get("unknown"),
                    "raised_by": item.get("raised_by", []),
                    "source_uncertainty_ids": item.get("source_uncertainty_ids", []),
                }
                for item in skeleton.get("critical_unknowns", [])[:8]
                if isinstance(item, dict)
            ],
            "deterministic_disagreement_candidates": deterministic_disagreements,
            "existing_summary": skeleton.get("overall_committee_view", {}).get("summary", ""),
            "dominant_tension": skeleton.get("overall_committee_view", {}).get("dominant_tension", ""),
        }

    def _related_stream_names(self, text: str, shared_progression: Dict[str, Any]) -> List[str]:
        lower = str(text or "").lower()
        scored: List[Tuple[int, str]] = []
        for stream_name, keywords in COMMITTEE_V2_STREAM_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in lower)
            if score:
                scored.append((score, stream_name))
        if not scored:
            stream_names = [
                str(item.get("stream") or "").strip()
                for item in (shared_progression.get("streams") or [])
                if isinstance(item, dict) and str(item.get("stream") or "").strip()
            ]
            return stream_names[:2]
        return [name for _score, name in sorted(scored, key=lambda item: (-item[0], item[1]))[:3]]

    def _confidence_from_support(
        self,
        supporting_analysts: Sequence[str],
        supporting_evidence: Sequence[str],
    ) -> str:
        analysts = _dedupe([str(item).strip().lower() for item in supporting_analysts if str(item).strip()])
        evidence = _dedupe([str(item).strip() for item in supporting_evidence if str(item).strip()])
        if len(analysts) >= 3 or (len(analysts) >= 2 and len(evidence) >= 2):
            return "high"
        if analysts or evidence:
            return "medium"
        return "low"

    def _commitment_effect_from_text(self, text: str) -> str:
        lower = str(text or "").lower()
        if any(token in lower for token in ("delayed", "delay", "underutilized", "weaken", "worsen", "missing", "unable to verify", "unclear")):
            return "weakened"
        if any(token in lower for token in ("delivered", "commissioned", "operational", "improved", "strengthen", "ramp", "confirmed", "progress")):
            return "strengthened"
        return "unchanged"

    def _turning_point_confidence(self, item: Dict[str, Any]) -> str:
        supporting = _normalize_optional_string_list(item.get("supporting_analysts") or item.get("affected_analysts"))
        evidence = _normalize_optional_string_list(item.get("supporting_evidence") or item.get("evidence_ids"))
        return self._confidence_from_support(supporting, evidence)

    def _derive_v2_disagreement_type(self, item: Dict[str, Any]) -> str:
        text = " ".join(
            [
                str(item.get("theme") or ""),
                str(item.get("summary") or ""),
                str(item.get("why_it_matters") or ""),
                str(item.get("disagreement") or ""),
            ]
        ).lower()
        if any(token in text for token in ("fact", "factual", "evidence", "contradict", "conflict")):
            return "evidence_disagreement"
        if any(token in text for token in ("time", "timing", "later", "earlier", "horizon", "future")):
            return "time_horizon_difference"
        if any(token in text for token in ("risk", "downside", "uncertain", "uncertainty", "confidence", "caution")):
            return "uncertainty_tolerance_difference"
        if any(token in text for token in ("cash", "balance sheet", "debt", "liquidity", "working capital", "financial")):
            return "financial_vs_business_tension"
        if any(token in text for token in ("execution", "delivery", "project", "capacity", "commission", "utilization")):
            return "execution_vs_outcome_tension"
        if any(token in text for token in ("value", "valuation", "price", "multiple", "quality")):
            return "valuation_vs_quality_tension"
        if any(token in text for token in ("missing", "unknown", "unclear", "cannot", "unable")):
            return "unresolved_data_gap"
        return "doctrine_weighting_difference"

    def _build_major_disagreement_records(
        self,
        payload: Dict[str, Any],
        shared_progression: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        major_disagreements: List[Dict[str, Any]] = []
        for item in payload.get("areas_of_disagreement", []) or []:
            if not isinstance(item, dict):
                continue
            analysts_a = _normalize_optional_string_list(
                item.get("analysts_positive_or_less_concerned")
                or item.get("analysts_on_side_a")
                or item.get("analysts_with_business_quality_focus")
            )
            analysts_b = _normalize_optional_string_list(
                item.get("analysts_cautious_or_negative")
                or item.get("analysts_on_side_b")
                or item.get("analysts_with_downside_or_execution_focus")
            )
            evidence_ids = _normalize_optional_string_list(item.get("evidence_ids"))
            topic = str(item.get("theme") or item.get("topic") or "").strip()
            side_a_view = str(item.get("summary") or item.get("side_a_view") or "").strip()
            side_b_view = str(item.get("why_it_matters") or item.get("side_b_view") or "").strip()
            if not topic or not side_a_view:
                continue
            disagreement_type = self._derive_v2_disagreement_type(item)
            evidence_context = _dedupe(
                evidence_ids
                + _normalize_optional_string_list(item.get("evidence_limit"))
            )
            what_resolves = str(item.get("what_evidence_would_resolve_it") or "").strip()
            if not what_resolves:
                if disagreement_type == "execution_vs_outcome_tension":
                    what_resolves = "Later evidence showing execution translated into operating results."
                elif disagreement_type == "financial_vs_business_tension":
                    what_resolves = "Later evidence showing business progress translated into better financial resilience."
                elif disagreement_type == "time_horizon_difference":
                    what_resolves = "Later evidence showing whether the current evidence is durable over more than one period."
                elif disagreement_type == "unresolved_data_gap":
                    what_resolves = "A later filing or operating update that closes the missing evidence gap."
                else:
                    what_resolves = "Later evidence showing whether the shared signal is real, durable, and decision-relevant."
            major_disagreements.append(
                {
                    "topic": topic,
                    "analysts_on_side_a": analysts_a,
                    "side_a_view": side_a_view,
                    "analysts_on_side_b": analysts_b,
                    "side_b_view": side_b_view,
                    "reason_for_disagreement": str(item.get("why_it_matters") or item.get("summary") or "").strip(),
                    "evidence_causing_tension": evidence_context,
                    "what_evidence_would_resolve_it": what_resolves,
                    "investor_importance": str(item.get("why_it_matters") or "This disagreement affects conviction.") or "This disagreement affects conviction.",
                    "confidence": self._confidence_from_support(analysts_a + analysts_b, evidence_ids),
                    "disagreement_type": disagreement_type,
                }
            )
        return major_disagreements[:7]

    def _build_shared_conviction_records(
        self,
        payload: Dict[str, Any],
        shared_progression: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for item in payload.get("areas_of_agreement", []) or []:
            if not isinstance(item, dict):
                continue
            conclusion = str(item.get("theme") or item.get("summary") or "").strip()
            if not conclusion:
                continue
            supporting_analysts = _normalize_optional_string_list(item.get("analysts") or item.get("source_analysts"))
            source_streams = self._related_stream_names(conclusion + " " + str(item.get("summary") or ""), shared_progression)
            records.append(
                {
                    "conclusion": conclusion,
                    "supporting_analysts": supporting_analysts,
                    "supporting_evidence": _normalize_optional_string_list(item.get("evidence_ids")),
                    "progression": str(item.get("summary") or "").strip(),
                    "why_it_matters": str(item.get("why_it_matters") or item.get("summary") or "").strip() or "This materially shapes investor conviction.",
                    "confidence": self._confidence_from_support(supporting_analysts, _normalize_optional_string_list(item.get("evidence_ids"))),
                    "source_streams": source_streams,
                }
            )
        return records[:7]

    def _build_progression_list_items(
        self,
        *,
        shared_progression: Dict[str, Any],
        include_negative: bool,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for stream in shared_progression.get("streams", []) or []:
            if not isinstance(stream, dict):
                continue
            stream_name = str(stream.get("stream") or "").strip()
            if not stream_name:
                continue
            if stream_name not in COMMITTEE_V2_STREAM_PRIORITY and stream_name not in {
                "financial memory",
                "management quality",
                "management commitments",
                "projects",
                "capacity evolution",
                "risk evolution",
                "management commentary",
                "capital allocation outcomes",
            }:
                continue
            assessments = stream.get("assessments") or []
            if not isinstance(assessments, list):
                assessments = []
            if stream_name == "management commitments" and isinstance(stream.get("timeline"), list):
                timeline_items = stream.get("timeline") or []
                if timeline_items:
                    assessments = timeline_items
            if not assessments:
                continue
            for assessment in assessments[:2]:
                if not isinstance(assessment, dict):
                    continue
                summary = str(
                    assessment.get("what_changed")
                    or assessment.get("summary")
                    or assessment.get("progression_summary")
                    or assessment.get("current_state")
                    or ""
                ).strip()
                why = str(
                    assessment.get("why_it_changed")
                    or assessment.get("why_it_matters")
                    or assessment.get("investor_implication")
                    or ""
                ).strip()
                if not summary and not why:
                    continue
                status = str(
                    assessment.get("status")
                    or assessment.get("current_status")
                    or assessment.get("conviction_impact")
                    or ""
                ).strip().lower()
                effect = self._commitment_effect_from_text(" ".join([summary, why, status]))
                if include_negative and effect == "strengthened":
                    continue
                if not include_negative and effect == "weakened":
                    continue
                period = str(
                    assessment.get("period")
                    or assessment.get("latest_period")
                    or stream.get("latest_period")
                    or ""
                ).strip()
                items.append(
                    {
                        "period": period,
                        "summary": summary or f"{stream_name.title()} moved to a new state.",
                        "event": summary or f"{stream_name.title()} moved to a new state.",
                        "conclusion": summary or f"{stream_name.title()} moved to a new state.",
                        "before": str(
                            assessment.get("before")
                            or assessment.get("previous_state")
                            or "Earlier evidence was not explicit."
                        ).strip(),
                        "after": str(
                            assessment.get("after")
                            or assessment.get("status")
                            or assessment.get("current_status")
                            or "Later evidence is still being read."
                        ).strip(),
                        "why_it_matters": why or "This changes the investor interpretation of the business trajectory.",
                        "affected_analysts": {
                            "management quality": ["buffett", "munger"],
                            "management commitments": ["buffett", "fisher", "munger"],
                            "projects": ["fisher", "lynch"],
                            "capacity evolution": ["fisher", "lynch"],
                            "risk evolution": ["graham", "buffett", "munger"],
                            "management commentary": ["buffett", "fisher", "munger"],
                            "capital allocation outcomes": ["buffett", "munger", "graham"],
                            "financial memory": ["graham", "buffett", "lynch"],
                        }.get(stream_name, ["graham", "buffett", "fisher", "munger", "lynch"]),
                        "supporting_analysts": {
                            "management quality": ["buffett", "munger"],
                            "management commitments": ["buffett", "fisher", "munger"],
                            "projects": ["fisher", "lynch"],
                            "capacity evolution": ["fisher", "lynch"],
                            "risk evolution": ["graham", "buffett", "munger"],
                            "management commentary": ["buffett", "fisher", "munger"],
                            "capital allocation outcomes": ["buffett", "munger", "graham"],
                            "financial memory": ["graham", "buffett", "lynch"],
                        }.get(stream_name, ["graham", "buffett", "fisher", "munger", "lynch"]),
                        "conviction_effect": effect,
                        "confidence": self._confidence_from_support(
                            ["buffett", "graham"] if stream_name == "financial memory" else ["fisher"] if stream_name in {"projects", "capacity evolution"} else ["buffett"],
                            _normalize_optional_string_list(assessment.get("evidence_ids")),
                        ),
                        "source_streams": [stream_name],
                    }
                )
        return items

    def _build_unresolved_items_v2(
        self,
        payload: Dict[str, Any],
        shared_progression: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        unresolved: List[Dict[str, Any]] = []
        for item in payload.get("critical_unknowns", []) or []:
            if not isinstance(item, dict):
                continue
            question = str(item.get("unknown") or "").strip()
            if not question:
                continue
            affected_analysts = _normalize_optional_string_list(item.get("raised_by"))
            affected_thesis_area = self._related_stream_names(question + " " + str(item.get("why_it_matters") or ""), shared_progression)
            evidence_needed = str(item.get("evidence_needed") or item.get("evidence_limit") or "").strip()
            if not evidence_needed:
                evidence_needed = "Later evidence that closes the current uncertainty."
            unresolved.append(
                {
                    "question": question.rstrip("."),
                    "why_it_matters": str(item.get("why_it_matters") or "This remains decision-relevant.").strip(),
                    "affected_analysts": affected_analysts,
                    "affected_thesis_area": affected_thesis_area[:3],
                    "evidence_needed": evidence_needed,
                    "current_confidence": self._confidence_from_support(affected_analysts, _normalize_optional_string_list(item.get("source_uncertainty_ids")) or []),
                }
            )
        return unresolved[:7]

    def _build_judgment_block(
        self,
        *,
        assessment: str,
        direction: str,
        strongest_evidence: str,
        main_concern: str,
        unresolved_issue: str,
        confidence: str,
        economic_mechanism: str,
    ) -> Dict[str, Any]:
        interpretation = build_interpretation_contract(
            conclusion=assessment,
            what_changed=[strongest_evidence],
            why_it_matters=main_concern or unresolved_issue,
            economic_mechanism=economic_mechanism,
            thesis_impact=(
                "strengthens"
                if direction == "strengthening"
                else "weakens"
                if direction == "weakening"
                else "neutral"
                if direction in {"stable", "mixed"}
                else "unresolved"
            ),
            positive_evidence=[strongest_evidence],
            negative_evidence=[main_concern],
            unresolved=[unresolved_issue],
            what_to_watch=[main_concern, unresolved_issue],
            confidence={"level": confidence, "basis": [], "limitations": []},
        )
        return {
            "assessment": _truncate_text(assessment or "This judgment is still being assembled from the available evidence.", 280),
            "direction": direction or "unclear",
            "strongest_evidence": _truncate_text(
                strongest_evidence or "No single evidence anchor is strong enough yet, so the committee keeps this judgment provisional.",
                220,
            ),
            "main_concern": _truncate_text(
                main_concern or "The committee still needs more longitudinal evidence before this concern can be reduced.",
                220,
            ),
            "unresolved_issue": _truncate_text(
                unresolved_issue or "The main unresolved issue remains open until later evidence makes it clearer.",
                220,
            ),
            "confidence": confidence,
            "interpretation": interpretation,
        }

    def _build_committee_summary_v2(
        self,
        *,
        committee_view: str,
        committee_direction: str,
        consensus_strength: str,
        shared_convictions: Sequence[Dict[str, Any]],
        disagreements: Sequence[Dict[str, Any]],
        strengtheners: Sequence[Dict[str, Any]],
        weakeners: Sequence[Dict[str, Any]],
        unresolved_items: Sequence[Dict[str, Any]],
        turning_points: Sequence[Dict[str, Any]],
        evidence_confidence: Dict[str, Any],
    ) -> str:
        positive = "; ".join(
            _truncate_text(item.get("conclusion") or item.get("summary") or "", 120)
            for item in shared_convictions[:2]
            if isinstance(item, dict)
        )
        negative = "; ".join(
            _truncate_text(item.get("summary") or item.get("event") or "", 120)
            for item in weakeners[:2]
            if isinstance(item, dict)
        )
        disagreement_text = "; ".join(
            _truncate_text(item.get("topic") or item.get("reason_for_disagreement") or "", 120)
            for item in disagreements[:2]
            if isinstance(item, dict)
        )
        unresolved_text = "; ".join(
            _truncate_text(item.get("question") or item.get("why_it_matters") or "", 120)
            for item in unresolved_items[:2]
            if isinstance(item, dict)
        )
        turning_text = "; ".join(
            _truncate_text(item.get("event") or item.get("why_it_matters") or "", 120)
            for item in turning_points[:2]
            if isinstance(item, dict)
        )
        strength_text = "; ".join(
            _truncate_text(item.get("summary") or item.get("conclusion") or "", 120)
            for item in strengtheners[:2]
            if isinstance(item, dict)
        )
        confidence_level = str(evidence_confidence.get("level") or "medium").strip()
        basis = "; ".join(_normalize_optional_string_list(evidence_confidence.get("basis"))[:3])
        limitations = "; ".join(_normalize_optional_string_list(evidence_confidence.get("limitations"))[:2])
        parts = [
            f"The committee sees the company as {committee_view.replace('_', ' ')} and the evidence trend as {committee_direction.replace('_', ' ')}.",
            f"Consensus is {consensus_strength}, which means the panel is not averaging views; it is preserving where doctrines truly align and where they do not.",
            f"The strongest shared convictions are {positive or 'still developing from the available evidence'}, and they matter because they show where multiple doctrines now see the same direction of travel rather than the same isolated number.",
            f"Thesis strengtheners include {strength_text or 'the clearer progression signals that are already visible in the longitudinal record'}; the main weakeners remain {negative or 'the unresolved cautions and missing follow-through in the record'}, so the committee can say both what improved and what still limits conviction.",
            f"Key turning points are {turning_text or 'still concentrated in the clearest evidence of progress, delay, or contradiction'}, which keeps the committee anchored to change over time instead of a single snapshot.",
            f"The unresolved questions are {unresolved_text or 'the decision-relevant gaps that still need later evidence to close'}, and these should stay open until the next filing, update, or operating disclosure answers them directly.",
            f"Doctrinal disagreement remains visible around {disagreement_text or 'how much weight to give future promise versus current evidence'}, which is useful because it tells an investor whether the gap is factual, temporal, or just a different weighting of the same evidence.",
            f"Evidence confidence is {confidence_level} because {basis or 'the committee has compact progression summaries, but some evidence remains indirect or incomplete'}; {limitations or 'that uncertainty should be treated as part of the conclusion, not hidden from it'}.",
            "Management, capital allocation, and risk judgments are kept separate so the committee can say where the business is improving, where execution still lags, and where the balance sheet or operating record may still be resisting conviction.",
            "That separation matters because the business can improve while the financial footing weakens, or the reverse can happen, and the committee should name that tension rather than smoothing it away into a bland consensus.",
            "The next diligence pass should focus on the evidence gaps most likely to change conviction, especially the items that sit closest to the current disagreements and turning points.",
        ]
        return " ".join(parts)

    def _derive_committee_v2_overlay(
        self,
        *,
        payload: Dict[str, Any],
        committee_input: Dict[str, Any],
        included: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        bundle = committee_input.get("committee_input_bundle_v2") or {}
        shared_progression = bundle.get("shared_progression") or {}
        management_quality = shared_progression.get("management_quality") or {}
        capital_allocation_outcomes = shared_progression.get("capital_allocation_outcomes") or {}
        financial_truth_stream = shared_progression.get("financial_truth") or {}
        shared_convictions = self._build_shared_conviction_records(payload, shared_progression)
        major_disagreements = self._build_major_disagreement_records(payload, shared_progression)
        strengtheners = self._build_progression_list_items(shared_progression=shared_progression, include_negative=False)
        weakeners = self._build_progression_list_items(shared_progression=shared_progression, include_negative=True)
        unresolved_items = self._build_unresolved_items_v2(payload, shared_progression)
        turning_points: List[Dict[str, Any]] = []
        seen_turning_points: set[Tuple[str, str, str]] = set()
        for item in self._build_progression_list_items(shared_progression=shared_progression, include_negative=False) + self._build_progression_list_items(shared_progression=shared_progression, include_negative=True):
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("event") or "").strip().casefold(),
                str(item.get("period") or "").strip().casefold(),
                str(item.get("why_it_matters") or "").strip().casefold(),
            )
            if key in seen_turning_points:
                continue
            seen_turning_points.add(key)
            turning_points.append(item)
            if len(turning_points) >= 6:
                break

        for item in payload.get("most_important_risks", []) or []:
            if not isinstance(item, dict):
                continue
            weakeners.append(
                {
                    "summary": str(item.get("risk") or item.get("summary") or "").strip(),
                    "period": str(payload.get("years_considered", [])[-1] if payload.get("years_considered") else ""),
                    "source_streams": self._related_stream_names(
                        str(item.get("risk") or item.get("summary") or ""),
                        shared_progression,
                    ),
                    "supporting_analysts": _normalize_optional_string_list(item.get("raised_by")),
                    "why_it_matters": str(item.get("summary") or item.get("why_it_matters") or "").strip(),
                    "conviction_effect": "weakened",
                    "confidence": self._confidence_from_support(
                        _normalize_optional_string_list(item.get("raised_by")),
                        _normalize_optional_string_list(item.get("evidence_ids")),
                    ),
                }
            )
        for item in payload.get("strongest_positive_signals", []) or []:
            if not isinstance(item, dict):
                continue
            strengtheners.append(
                {
                    "summary": str(item.get("signal") or item.get("summary") or "").strip(),
                    "period": str(payload.get("years_considered", [])[-1] if payload.get("years_considered") else ""),
                    "source_streams": self._related_stream_names(
                        str(item.get("signal") or item.get("summary") or ""),
                        shared_progression,
                    ),
                    "supporting_analysts": _normalize_optional_string_list(item.get("supported_by")),
                    "why_it_matters": str(item.get("summary") or item.get("why_it_matters") or "").strip(),
                    "conviction_effect": "strengthened",
                    "confidence": self._confidence_from_support(
                        _normalize_optional_string_list(item.get("supported_by")),
                        _normalize_optional_string_list(item.get("evidence_ids")),
                    ),
                }
            )

        strengthener_count = len([item for item in strengtheners if item.get("conviction_effect") == "strengthened"])
        weakener_count = len([item for item in weakeners if item.get("conviction_effect") == "weakened"])
        if not shared_convictions and not major_disagreements and not unresolved_items:
            consensus_strength = "insufficient_evidence"
        elif len(shared_convictions) >= 4 and len(major_disagreements) <= 1:
            consensus_strength = "high"
        elif len(shared_convictions) >= 2 and len(major_disagreements) <= 3:
            consensus_strength = "medium"
        elif len(major_disagreements) >= 4:
            consensus_strength = "fragmented"
        else:
            consensus_strength = "low"

        if strengthener_count > weakener_count + 1:
            committee_direction = "strengthening"
        elif weakener_count > strengthener_count + 1:
            committee_direction = "weakening"
        elif strengthener_count and weakener_count:
            committee_direction = "mixed"
        elif strengthener_count:
            committee_direction = "strengthening"
        elif weakener_count:
            committee_direction = "weakening"
        else:
            committee_direction = "stable"

        if consensus_strength == "insufficient_evidence":
            committee_view = "insufficient_evidence"
        elif consensus_strength == "fragmented" or committee_direction == "weakening" and weakener_count > strengthener_count:
            committee_view = "weak"
        elif consensus_strength == "high" and committee_direction == "strengthening":
            committee_view = "strong"
        elif consensus_strength in {"high", "medium"} and committee_direction in {"strengthening", "stable"}:
            committee_view = "reasonably_strong"
        else:
            committee_view = "mixed"

        financial_committee_view = payload.get("financial_committee_view") or {}
        financial_strengths = _normalize_optional_string_list(financial_committee_view.get("financial_strengths"))
        financial_concerns = _normalize_optional_string_list(financial_committee_view.get("financial_concerns"))
        financial_limits = _normalize_optional_string_list(financial_committee_view.get("financial_interpretation_limits"))
        management_interpretation = management_quality.get("interpretation") if isinstance(management_quality.get("interpretation"), dict) else {}
        capital_interpretation = {}
        capital_assessments = capital_allocation_outcomes.get("assessments") or []
        if capital_assessments and isinstance(capital_assessments[0], dict):
            maybe_interp = capital_assessments[0].get("interpretation")
            if isinstance(maybe_interp, dict):
                capital_interpretation = maybe_interp
        evidence_confidence = {
            "level": "high" if consensus_strength == "high" and strengthener_count >= 2 else "medium" if shared_convictions or major_disagreements else "low",
            "basis": _dedupe(
                [
                    f"{len(shared_convictions)} shared convictions",
                    f"{len(major_disagreements)} disagreements preserved",
                    f"{len(turning_points)} turning points selected",
                    f"{len(unresolved_items)} unresolved items carried forward",
                ]
                + _normalize_optional_string_list(payload.get("evidence_quality_notes"))
            ),
            "limitations": _dedupe(
                _normalize_optional_string_list(payload.get("synthesis_limits"))
                + _normalize_optional_string_list(shared_progression.get("limitations"))
            ),
        }

        financial_judgment = self._build_judgment_block(
            assessment=(
                "Financial progression looks "
                + ("improving" if strengthener_count >= weakener_count else "stretched" if weakener_count > strengthener_count else "mixed")
                + " when read through the available financial-truth evidence."
            ),
            direction="strengthening" if strengthener_count > weakener_count else "weakening" if weakener_count > strengthener_count else "stable",
            strongest_evidence=financial_strengths[0] if financial_strengths else str(financial_truth_stream.get("summary") or ""),
            main_concern=financial_concerns[0] if financial_concerns else (financial_limits[0] if financial_limits else "The financial evidence remains incomplete in the areas that most affect conviction."),
            unresolved_issue=(unresolved_items[0]["question"] if unresolved_items else (financial_limits[0] if financial_limits else "The main unresolved financial question is still open.")),
            confidence=evidence_confidence["level"],
            economic_mechanism="Financial evidence matters because cash conversion, owner earnings, and per-share economics determine whether reported progress is durable.",
        )
        business_quality_judgment = self._build_judgment_block(
            assessment=(
                "Business quality appears "
                + ("to be strengthening" if committee_direction == "strengthening" else "stable but uneven" if committee_direction == "stable" else "under pressure")
                + " when viewed through projects, capacity, commentary, and risks."
            ),
            direction=committee_direction,
            strongest_evidence=str(
                (strengtheners[0].get("summary") or strengtheners[0].get("conclusion") or strengtheners[0].get("event"))
                if strengtheners
                else payload.get("overall_committee_view", {}).get("summary", "")
            ),
            main_concern=str(
                (weakeners[0].get("summary") or weakeners[0].get("conclusion") or weakeners[0].get("event"))
                if weakeners
                else payload.get("overall_committee_view", {}).get("dominant_tension", "")
            ),
            unresolved_issue=(unresolved_items[0]["question"] if unresolved_items else "The core business-quality question remains how durable the visible progress will prove to be."),
            confidence=evidence_confidence["level"],
            economic_mechanism="Business quality matters because execution quality determines whether operating progress persists and compounds.",
        )
        management_judgment = self._build_judgment_block(
            assessment=str(management_interpretation.get("conclusion") or management_quality.get("overall_view") or "Management judgment is read directly from the management-quality synthesis and related commitments."),
            direction=str(management_quality.get("overall_direction") or committee_direction or "unclear"),
            strongest_evidence=str((management_interpretation.get("positive_evidence") or [management_quality.get("overall_view") or ""])[0] or (financial_strengths[0] if financial_strengths else "")),
            main_concern=str((management_interpretation.get("negative_evidence") or [management_quality.get("weakest_dimension") or ""])[0] or (payload.get("most_important_risks", [{}])[0].get("risk") if payload.get("most_important_risks") else "Candor and follow-through still need more longitudinal proof.")),
            unresolved_issue=str((management_interpretation.get("unresolved") or [management_quality.get("investor_implication") or ""])[0] or "Whether management's stated direction consistently matches later evidence."),
            confidence=evidence_confidence["level"],
            economic_mechanism="Management quality matters because execution discipline, candor, and capital allocation shape how reliably the business can compound.",
        )
        capital_allocation_judgment = self._build_judgment_block(
            assessment=(
                "Capital allocation remains"
                + (" more convincing" if any("return" in str(item.get("summary") or item.get("conclusion") or "").lower() for item in strengtheners) else " an evidence question")
                + " because deployed capital must still be judged against later outcomes."
            ),
            direction="strengthening" if any("return" in str(item.get("summary") or item.get("conclusion") or "").lower() for item in strengtheners) else "unclear",
            strongest_evidence=str((capital_interpretation.get("positive_evidence") or [capital_allocation_outcomes.get("summary") or capital_allocation_outcomes.get("latest_period") or ""])[0]),
            main_concern=(capital_interpretation.get("negative_evidence") or [financial_limits[0] if financial_limits else "Return evidence is thinner than deployment evidence."])[0],
            unresolved_issue=(capital_interpretation.get("unresolved") or ["The committee still wants later evidence that capital deployed produced measurable returns."])[0],
            confidence=evidence_confidence["level"],
            economic_mechanism="Capital allocation matters because deployment only creates value if later returns exceed the opportunity cost of the cash used.",
        )
        risk_judgment = self._build_judgment_block(
            assessment="Risk remains part of the thesis rather than a footnote, with the most material risks still anchored in working capital, execution, and unresolved evidence gaps.",
            direction="weakening" if any("risk" in str(item.get("summary") or "").lower() for item in weakeners) else "stable",
            strongest_evidence=financial_concerns[0] if financial_concerns else (
                str(weakeners[0].get("summary") or weakeners[0].get("conclusion") or weakeners[0].get("event"))
                if weakeners
                else "The risk record remains mixed."
            ),
            main_concern=(financial_limits[0] if financial_limits else "The most important risks are still not fully resolved."),
            unresolved_issue=(unresolved_items[0]["question"] if unresolved_items else "Which risk changes most if the next evidence update is positive?"),
            confidence=evidence_confidence["level"],
            economic_mechanism="Risk matters because downside mechanisms such as weak cash conversion, execution slippage, or dilution can overwhelm otherwise positive operating signals.",
        )

        what_would_change_the_view: List[str] = []
        if unresolved_items:
            for item in unresolved_items[:5]:
                question = str(item.get("question") or "").strip()
                if question:
                    what_would_change_the_view.append(
                        f"Later evidence answers: {question.rstrip('?')}."
                    )
        for item in strengtheners[:3]:
            summary = str(item.get("summary") or item.get("conclusion") or "").strip()
            if summary and summary not in what_would_change_the_view:
                what_would_change_the_view.append(
                    f"New evidence confirms that {summary.lower()}."
                )
        for item in weakeners[:3]:
            summary = str(item.get("summary") or item.get("event") or "").strip()
            if summary and summary not in what_would_change_the_view:
                what_would_change_the_view.append(
                    f"New evidence shows that {summary.lower()} is not durable."
                )
        what_would_change_the_view = _dedupe([_ensure_sentence(item) for item in what_would_change_the_view])[:5]

        top_diligence_questions: List[Dict[str, Any]] = []
        sorted_unresolved = sorted(
            unresolved_items,
            key=lambda x: (0 if x.get("current_confidence") == "low" else 1, str(x.get("question") or "")),
        )
        for idx, item in enumerate(sorted_unresolved[:7]):
            question = str(item.get("question") or "").strip()
            if not question:
                continue
            top_diligence_questions.append(
                {
                    "rank": idx + 1,
                    "question": question if question.endswith("?") else f"{question}?",
                    "why_it_matters": str(item.get("why_it_matters") or "This question is decision-relevant.").strip(),
                    "affected_analysts": _normalize_optional_string_list(item.get("affected_analysts")),
                    "priority_reason": "Decision impact and unresolved disagreement.",
                    "evidence_needed": str(item.get("evidence_needed") or "").strip(),
                }
            )

        committee_summary = self._build_committee_summary_v2(
            committee_view=committee_view,
            committee_direction=committee_direction,
            consensus_strength=consensus_strength,
            shared_convictions=shared_convictions,
            disagreements=major_disagreements,
            strengtheners=strengtheners,
            weakeners=weakeners,
            unresolved_items=unresolved_items,
            turning_points=turning_points,
            evidence_confidence=evidence_confidence,
        )

        return {
            "company_slug": self.company,
            "committee_view": committee_view,
            "committee_direction": committee_direction,
            "consensus_strength": consensus_strength,
            "strongest_shared_convictions": shared_convictions,
            "major_disagreements": major_disagreements,
            "disagreement_explanations": [
                _truncate_text(item.get("reason_for_disagreement") or item.get("topic") or "", 260)
                for item in major_disagreements
            ][:7],
            "thesis_strengtheners": strengtheners[:7],
            "thesis_weakeners": weakeners[:7],
            "unresolved_items": unresolved_items[:7],
            "major_turning_points": turning_points[:6],
            "financial_judgment": financial_judgment,
            "business_quality_judgment": business_quality_judgment,
            "management_judgment": management_judgment,
            "capital_allocation_judgment": capital_allocation_judgment,
            "risk_judgment": risk_judgment,
            "evidence_confidence": evidence_confidence,
            "what_would_change_the_view": what_would_change_the_view,
            "top_diligence_questions": top_diligence_questions,
            "committee_summary": committee_summary,
        }

    def _fallback_narrative_payload(self, skeleton: Dict[str, Any]) -> Dict[str, Any]:
        positives = [item.get("signal", "") for item in skeleton.get("strongest_positive_signals", [])[:2] if isinstance(item, dict)]
        risks = [item.get("risk", "") for item in skeleton.get("most_important_risks", [])[:2] if isinstance(item, dict)]
        unknowns = [item.get("unknown", "") for item in skeleton.get("critical_unknowns", [])[:2] if isinstance(item, dict)]
        return {
            "executive_committee_summary": skeleton.get("overall_committee_view", {}).get("summary", ""),
            "synthesis_narrative": _dedupe(
                [text for text in [
                    f"Constructive signals include: {', '.join(positives)}." if positives else "",
                    f"Key risks remain: {', '.join(risks)}." if risks else "",
                ] if text]
            ),
            "disagreement_explanation": [
                item.get("summary", "")
                for item in skeleton.get("areas_of_disagreement", [])[:2]
                if isinstance(item, dict) and item.get("summary")
            ],
            "what_to_watch_next": unknowns,
            "suggested_unknowns": [],
        }

    def _parse_committee_narrative_payload(self, payload_text: str) -> Dict[str, Any]:
        parsed = json.loads(payload_text)
        if not isinstance(parsed, dict):
            raise ValueError("committee narrative response must be an object")
        result: Dict[str, Any] = {}
        summary = str(parsed.get("executive_committee_summary") or "").strip()
        if summary:
            result["executive_committee_summary"] = _validate_normalized_list_text(
                "executive_committee_summary",
                _truncate_text(summary, 400),
            )
        for key in ("synthesis_narrative", "disagreement_explanation", "what_to_watch_next", "suggested_unknowns"):
            result[key] = [
                _validate_normalized_list_text(key, _truncate_text(item, 240))
                for item in _normalize_optional_string_list(parsed.get(key))
                if str(item or "").strip()
            ][:5]
        return result

    def _merge_narrative_into_skeleton(
        self,
        skeleton: Dict[str, Any],
        narrative: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged = json.loads(json.dumps(skeleton))
        summary = str(narrative.get("executive_committee_summary") or "").strip()
        if summary:
            merged["overall_committee_view"]["summary"] = summary
            merged["executive_committee_summary"] = summary
        merged["synthesis_narrative"] = _normalize_optional_string_list(narrative.get("synthesis_narrative"))
        merged["disagreement_explanation"] = _normalize_optional_string_list(narrative.get("disagreement_explanation"))
        merged["what_to_watch_next"] = _normalize_optional_string_list(narrative.get("what_to_watch_next"))
        suggested_unknowns = _normalize_optional_string_list(narrative.get("suggested_unknowns"))
        grounded_unknowns = {
            str(item.get("unknown") or "").casefold()
            for item in merged.get("critical_unknowns", [])
            if isinstance(item, dict)
        }
        ungrounded = [item for item in suggested_unknowns if item.casefold() not in grounded_unknowns]
        merged["ungrounded_suggested_unknowns"] = ungrounded
        return merged

    def _apply_dynamic_analyst_budget(self, analysts: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        analyst_list = [json.loads(json.dumps(item)) for item in analysts if isinstance(item, dict)]
        analyst_count = max(1, len(analyst_list))
        instruction_tokens = estimate_tokens(COMMITTEE_SYNTHESIS_SYSTEM_PROMPT)
        schema_tokens = estimate_tokens(COMMITTEE_SYNTHESIS_USER_PROMPT.replace("{committee_input_json}", "{}"))
        max_input_pack_tokens = max(
            1200,
            self.TARGET_TOTAL_PROMPT_TOKENS - instruction_tokens - schema_tokens - self.PROMPT_SAFETY_MARGIN_TOKENS,
        )
        shared_manifest_tokens = 350
        per_analyst_budget = min(
            self.MAX_ANALYST_BLOCK_TOKENS,
            max(250, (max_input_pack_tokens - shared_manifest_tokens) // analyst_count),
        )
        compacted: List[Dict[str, Any]] = []
        for block in analyst_list:
            block = self._enforce_analyst_char_budget(block, self.ANALYST_CHAR_BUDGET)
            block = self._enforce_analyst_token_budget(block, per_analyst_budget)
            compacted.append(block)
        return compacted

    def _analyst_uncertainties(self, included: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
        return {
            payload["doctrine_id"]: [str(item) for item in payload.get("open_uncertainties", []) or []]
            for payload in included
        }

    def _build_uncertainty_registry(self, included: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        registry: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        field_sources = [
            ("open_uncertainties", "open_uncertainties"),
            ("evidence_gaps", "evidence_gaps"),
            ("reasoning_limits", "reasoning_limits"),
            ("key_questions", "key_questions"),
            ("investor_questions", "investor_questions"),
            ("financial_missing_data", "financial_missing_data"),
            ("financial_interpretation_limits", "financial_interpretation_limits"),
            ("financial_warnings_carried_forward", "financial_warnings_carried_forward"),
        ]
        for payload in included:
            analyst = str(payload.get("doctrine_id") or "")
            counter = 1
            for field_name, source_field in field_sources:
                for item in payload.get(field_name, []) or []:
                    text = _truncate_text(item, 220).lower().strip()
                    if not text:
                        continue
                    key = (analyst, text)
                    if key in seen:
                        continue
                    seen.add(key)
                    registry.append(
                        {
                            "uncertainty_id": f"{analyst}_u{counter:03d}",
                            "analyst": analyst,
                            "category": _infer_uncertainty_category(text),
                            "text": text,
                            "aliases": [text],
                            "source_path": f"{analyst}_analysis.json#{source_field}",
                        }
                    )
                    counter += 1
        return sorted(
            registry,
            key=lambda item: (
                0 if item["category"] == "financials" else 1,
                item["analyst"],
                item["uncertainty_id"],
            ),
        )[:40]

    def _allowed_evidence_ids(self, included: Sequence[Dict[str, Any]]) -> List[str]:
        evidence_ids: List[str] = []
        for payload in included:
            for evidence_id in payload.get("evidence_ids", []) or []:
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
        return evidence_ids

    def _lookup_evidence_ids(self) -> List[str]:
        pcim_path = self._pcim_path()
        pcim = _load_json(pcim_path)
        if not pcim:
            return []
        lookup = build_evidence_lookup(pcim)
        return list(lookup.keys())

    def _validation_allowed_evidence_ids(
        self,
        included: Sequence[Dict[str, Any]],
        payload: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        combined: List[str] = []
        for evidence_id in self._allowed_evidence_ids(included):
            if evidence_id not in combined:
                combined.append(evidence_id)
        for evidence_id in self._lookup_evidence_ids():
            if evidence_id not in combined:
                combined.append(evidence_id)
        if payload is not None:
            payload_ids = self._collect_committee_evidence_ids(payload)
            payload_id_set = set(payload_ids)
            for evidence_id in self._collect_committee_evidence_ids(payload):
                canonical = _canonical_committee_evidence_id(evidence_id)
                if evidence_id not in combined:
                    combined.append(evidence_id)
                if canonical in payload_id_set and canonical not in combined:
                    combined.append(canonical)
        return combined

    def _allowed_evidence_set(self, included: Sequence[Dict[str, Any]]) -> set[str]:
        return set(self._validation_allowed_evidence_ids(included))

    def _years_considered(self, included: Sequence[Dict[str, Any]]) -> List[str]:
        years: List[str] = []
        for payload in included:
            for year in payload.get("years_considered", []) or []:
                if year not in years:
                    years.append(year)
        return years

    def _build_prompt(self, committee_input_or_pack: Dict[str, Any]) -> str:
        llm_input_pack = committee_input_or_pack
        if "pack_name" not in llm_input_pack:
            source_artifacts = [
                str(self._analysis_path(payload["analyst"]))
                for payload in committee_input_or_pack.get("analysts", [])
                if isinstance(payload, dict) and payload.get("analyst")
            ]
            prompt_payload = self._committee_prompt_payload(committee_input_or_pack)
            llm_input_pack = build_llm_input_pack(
                stage="committee_synthesis",
                purpose=(
                    "Synthesize only the compact analyst views into a committee-level investment view. "
                    "Do not calculate new ratios, do not invent financial facts, do not use raw PCIM, "
                    "and carry forward major missing-financial-data and interpretation-limit signals."
                ),
                company=self.company,
                year=None,
                selected_input=prompt_payload,
                observations=[prompt_payload],
                source_artifacts=source_artifacts,
                pack_name="committee_synthesis_input_pack",
            )
        return COMMITTEE_SYNTHESIS_USER_PROMPT.replace(
            "{committee_input_json}",
            render_llm_input_pack(llm_input_pack, include_policy=False),
        ).replace(
            "{committee_schema}",
            COMMITTEE_SCHEMA_PROMPT.strip(),
        )

    def _committee_prompt_payload(self, committee_input: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "company": self.company,
            "analysts": committee_input.get("analysts", []),
            "missing_analysts": committee_input.get("missing_analysts", []),
            "excluded_analysts": committee_input.get("excluded_analysts", []),
            "evidence_quality_notes": committee_input.get("evidence_quality_notes", []),
            "financial_warning_manifest": committee_input.get("financial_warning_manifest", {}),
            "allowed_critical_unknowns_registry": committee_input.get("allowed_critical_unknowns_registry", []),
        }
        return payload

    def _prompt_token_breakdown(self, llm_input_pack: Dict[str, Any]) -> Dict[str, int]:
        rendered_input = render_llm_input_pack(llm_input_pack, include_policy=False)
        user_prompt = COMMITTEE_SYNTHESIS_USER_PROMPT.replace(
            "{committee_input_json}",
            rendered_input,
        ).replace(
            "{committee_schema}",
            COMMITTEE_SCHEMA_PROMPT.strip(),
        )
        input_pack_tokens = int(llm_input_pack.get("metadata", {}).get("tokens_estimated") or estimate_tokens(json.dumps(llm_input_pack, ensure_ascii=False)))
        instruction_tokens = estimate_tokens(COMMITTEE_SYNTHESIS_SYSTEM_PROMPT)
        schema_tokens = estimate_tokens(COMMITTEE_SCHEMA_PROMPT)
        total_prompt_tokens = estimate_tokens(user_prompt) + instruction_tokens
        return {
            "instruction_tokens": instruction_tokens,
            "schema_tokens": schema_tokens,
            "input_pack_tokens": input_pack_tokens,
            "total_prompt_tokens": total_prompt_tokens,
        }

    def _largest_prompt_sections(
        self,
        *,
        instruction_tokens: int,
        schema_tokens: int,
        input_pack_tokens: int,
    ) -> List[Tuple[str, int]]:
        return sorted(
            [
                ("instructions", instruction_tokens),
                ("schema", schema_tokens),
                ("input_pack", input_pack_tokens),
            ],
            key=lambda item: item[1],
            reverse=True,
        )

    def _analyst_block_char_lengths(self, analysts: Sequence[Dict[str, Any]]) -> Dict[str, int]:
        lengths: Dict[str, int] = {}
        for analyst in analysts:
            if not isinstance(analyst, dict):
                continue
            name = str(analyst.get("analyst") or analyst.get("doctrine_id") or "unknown")
            lengths[name] = len(json.dumps(analyst, ensure_ascii=False))
        return lengths

    def _apply_emergency_committee_compaction(self, committee_input: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        compacted = json.loads(json.dumps(committee_input))
        warnings: List[str] = []
        compacted["analysts"] = [
            self._enforce_analyst_token_budget(
                self._enforce_analyst_char_budget(block, self.EMERGENCY_ANALYST_CHAR_BUDGET),
                min(self.MAX_ANALYST_BLOCK_TOKENS, 375),
            )
            for block in compacted.get("analysts", [])
            if isinstance(block, dict)
        ]
        for block in compacted.get("analysts", []):
            for field in ("top_positive_signals", "financial_strengths", "evidence_limits"):
                values = block.get(field)
                if isinstance(values, list):
                    block[field] = values[:1]
        warnings.append("Emergency committee compaction applied to stay within token budget.")
        return compacted, warnings

    def _apply_final_prompt_compaction(self, committee_input: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        compacted = json.loads(json.dumps(committee_input))
        warnings: List[str] = []
        compacted_blocks: List[Dict[str, Any]] = []
        for block in compacted.get("analysts", []):
            if not isinstance(block, dict):
                continue
            block = self._enforce_analyst_token_budget(
                self._enforce_analyst_char_budget(block, self.FINAL_PROMPT_ANALYST_CHAR_BUDGET),
                min(self.MAX_ANALYST_BLOCK_TOKENS, 320),
            )
            for field in ("top_positive_signals", "financial_strengths", "evidence_limits"):
                values = block.get(field)
                if isinstance(values, list):
                    block[field] = values[:1]
            block = _prune_empty_compact_fields(block)
            block = self._enforce_analyst_token_budget(
                self._enforce_analyst_char_budget(block, self.FINAL_PROMPT_ANALYST_CHAR_BUDGET),
                min(self.MAX_ANALYST_BLOCK_TOKENS, 300),
            )
            if len(json.dumps(block, ensure_ascii=False)) > self.FINAL_PROMPT_ANALYST_CHAR_BUDGET:
                block = _minimal_committee_analyst_block(block)
                block = self._enforce_analyst_token_budget(
                    self._enforce_analyst_char_budget(block, self.ULTRA_COMPACT_ANALYST_CHAR_BUDGET),
                    220,
                )
            compacted_blocks.append(block)
        compacted["analysts"] = compacted_blocks
        for key in ("evidence_quality_notes",):
            values = compacted.get(key)
            if isinstance(values, list):
                compacted[key] = values[:3]
        registry = compacted.get("allowed_critical_unknowns_registry")
        if isinstance(registry, list):
            compacted["allowed_critical_unknowns_registry"] = registry[:20]
        warnings.append("Final prompt compaction applied using total prompt tokens.")
        return compacted, warnings

    def _apply_ultra_compact_fallback(self, committee_input: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        compacted = json.loads(json.dumps(committee_input))
        compacted["analysts"] = [
            self._enforce_analyst_token_budget(
                _minimal_committee_analyst_block(block),
                180,
            )
            for block in compacted.get("analysts", [])
            if isinstance(block, dict)
        ]
        registry = compacted.get("allowed_critical_unknowns_registry")
        if isinstance(registry, list):
            compacted["allowed_critical_unknowns_registry"] = registry[:10]
        notes = compacted.get("evidence_quality_notes")
        if isinstance(notes, list):
            compacted["evidence_quality_notes"] = notes[:2]
        return compacted, ["Ultra-compact committee fallback applied to stay within token budget."]

    def _build_compact_prompt_assets(
        self,
        committee_input: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        source_artifacts = [
            str(self._analysis_path(payload["analyst"]))
            for payload in committee_input.get("analysts", [])
            if isinstance(payload, dict) and payload.get("analyst")
        ]
        prompt_payload = self._committee_prompt_payload(committee_input)
        llm_input_pack = build_llm_input_pack(
            stage="committee_synthesis",
            purpose=(
                "Synthesize only the compact analyst views into a committee-level investment view. "
                "Do not calculate new ratios, do not invent financial facts, do not use raw PCIM, "
                "and carry forward major missing-financial-data and interpretation-limit signals."
            ),
            company=self.company,
            year=None,
            selected_input=prompt_payload,
            observations=[prompt_payload],
            source_artifacts=source_artifacts,
            pack_name="committee_synthesis_input_pack",
        )
        prompt = self._build_prompt(llm_input_pack)
        token_breakdown = self._prompt_token_breakdown(llm_input_pack)
        manifest = {
            "analysts_included": [item.get("analyst") for item in committee_input.get("analysts", []) if isinstance(item, dict)],
            "analyst_block_chars": self._analyst_block_char_lengths(committee_input.get("analysts", [])),
            "estimated_tokens_before": llm_input_pack.get("metadata", {}).get("tokens_estimated"),
            "prompt_tokens_before": token_breakdown["total_prompt_tokens"],
            "prompt_chars_before": len(prompt),
            "truncation_applied": bool(llm_input_pack.get("metadata", {}).get("truncation_applied")),
            "warnings": list(llm_input_pack.get("metadata", {}).get("warnings") or []),
            "largest_prompt_sections": self._largest_prompt_sections(
                instruction_tokens=token_breakdown["instruction_tokens"],
                schema_tokens=token_breakdown["schema_tokens"],
                input_pack_tokens=token_breakdown["input_pack_tokens"],
            ),
            **token_breakdown,
        }
        return prompt, llm_input_pack, manifest

    def _target_budget(self, stage_budget: int) -> int:
        return min(stage_budget, self.TARGET_TOTAL_PROMPT_TOKENS)

    def _collect_committee_evidence_ids(self, payload: Dict[str, Any]) -> List[str]:
        evidence_ids = list(_normalize_optional_string_list(payload.get("evidence_ids")))
        for field in (
            "areas_of_agreement",
            "areas_of_disagreement",
            "strongest_positive_signals",
            "most_important_risks",
        ):
            for item in payload.get(field, []) or []:
                if not isinstance(item, dict):
                    continue
                for evidence_id in _normalize_optional_string_list(item.get("evidence_ids")):
                    if evidence_id not in evidence_ids:
                        evidence_ids.append(evidence_id)
        return evidence_ids

    def _canonicalize_evidence_list(
        self,
        evidence_ids: Any,
        *,
        allowed: set[str],
        replacements: List[Dict[str, str]],
        unresolved_ids: List[str],
    ) -> List[str]:
        normalized: List[str] = []
        for raw_id in _normalize_optional_string_list(evidence_ids):
            canonical = _canonical_committee_evidence_id(raw_id)
            if canonical in allowed:
                if canonical != raw_id:
                    replacement = {
                        "original_id": raw_id,
                        "canonical_id": canonical,
                    }
                    if replacement not in replacements:
                        replacements.append(replacement)
                if canonical not in normalized:
                    normalized.append(canonical)
                continue
            if raw_id in allowed:
                if canonical != raw_id and raw_id not in unresolved_ids:
                    unresolved_ids.append(raw_id)
                if raw_id not in normalized:
                    normalized.append(raw_id)
                continue
            if raw_id not in unresolved_ids:
                unresolved_ids.append(raw_id)
        return normalized

    def _apply_disagreement_cleanup(self, payload: Dict[str, Any]) -> None:
        for item in payload.get("areas_of_disagreement", []) or []:
            if not isinstance(item, dict):
                continue
            theme = str(item.get("theme") or "").lower()
            summary = str(item.get("summary") or "")
            why = str(item.get("why_it_matters") or "")

            disagreement_type = item.get("disagreement_type")
            theme_text = " ".join([theme, summary.lower(), why.lower()])
            inferred_type = None
            if (
                "downside" in theme_text
                and (
                    "growth" in theme_text
                    or "execution" in theme_text
                    or "runway" in theme_text
                    or "ambition" in theme_text
                )
            ):
                inferred_type = "risk_weighting_difference"
            elif "moat" in theme or "durability" in theme:
                inferred_type = "different_emphasis"
            elif "export" in theme or "foreign" in theme:
                inferred_type = "different_emphasis"
            else:
                inferred_type = "different_emphasis"

            # Cleanup may enrich the record, but the canonical normalization layer owns
            # disagreement_type. Only fill it when it is genuinely missing here.
            if not disagreement_type:
                disagreement_type = inferred_type
            item["disagreement_type"] = disagreement_type

            if "moat" in theme or "durability" in theme:
                positives = [
                    analyst
                    for analyst in _normalize_optional_string_list(
                        item.get("analysts_positive_or_less_concerned")
                    )
                    if analyst != "buffett"
                ]
                item["analysts_positive_or_less_concerned"] = positives
                item["analysts_with_business_quality_focus"] = _dedupe(
                    _normalize_optional_string_list(
                        item.get("analysts_with_business_quality_focus")
                    )
                    + ["buffett"]
                )
                item["analysts_with_downside_or_execution_focus"] = _dedupe(
                    _normalize_optional_string_list(
                        item.get("analysts_with_downside_or_execution_focus")
                    )
                    + _normalize_optional_string_list(
                        item.get("analysts_cautious_or_negative")
                    )
                )
                if "Buffett finds the business understandable but still sees moat durability as unproven." not in summary:
                    item["summary"] = (
                        "Buffett finds the business understandable but still sees moat "
                        "durability as unproven. Other analysts place more weight on the "
                        "absence of repeated customer, pricing-power, and margin evidence."
                    )
                if "durable pricing power" not in why.lower():
                    item["why_it_matters"] = (
                        "Whether the business can develop durable pricing power or customer "
                        "lock-in shapes whether current capex can translate into sustained, "
                        "profitable growth."
                    )

    def _apply_committee_cleanup(
        self,
        payload: Dict[str, Any],
        *,
        included: Sequence[Dict[str, Any]],
        missing: Sequence[str],
        excluded: Sequence[str],
    ) -> Dict[str, Any]:
        allowed = self._allowed_evidence_set(included)
        replacements: List[Dict[str, str]] = []
        unresolved_ids: List[str] = []

        payload["evidence_ids"] = self._canonicalize_evidence_list(
            payload.get("evidence_ids"),
            allowed=allowed,
            replacements=replacements,
            unresolved_ids=unresolved_ids,
        )
        for field in (
            "areas_of_agreement",
            "areas_of_disagreement",
            "strongest_positive_signals",
            "most_important_risks",
        ):
            for item in payload.get(field, []) or []:
                if not isinstance(item, dict):
                    continue
                item["evidence_ids"] = self._canonicalize_evidence_list(
                    item.get("evidence_ids"),
                    allowed=allowed,
                    replacements=replacements,
                    unresolved_ids=unresolved_ids,
                )

        payload["evidence_id_normalization"] = {
            "applied": bool(replacements),
            "replacements": replacements,
            "unresolved_ids": unresolved_ids,
        }
        payload["evidence_quality_notes"] = self._build_committee_input(
            included=included,
            missing=missing,
            excluded=excluded,
            warning_notes=[],
        )["evidence_quality_notes"]
        payload["evidence_quality_notes"] = self._load_inputs()[3]
        financial_view = payload.get("financial_committee_view") or {}
        financial_view.setdefault("missing_financial_data", [])
        financial_view.setdefault("financial_interpretation_limits", [])
        manifest = self._build_committee_financial_warning_manifest(included)
        if manifest["fcf_missing"]:
            text = "Free cash flow is missing; FCF-based conclusions cannot be assessed."
            if text not in financial_view["missing_financial_data"]:
                financial_view["missing_financial_data"].append(text)
        if manifest["capex_missing"]:
            text = "Capex is missing or incomplete; free cash flow and owner-earnings interpretation remain limited."
            if text not in financial_view["financial_interpretation_limits"]:
                financial_view["financial_interpretation_limits"].append(text)
        if manifest["payables_missing"]:
            text = "Payables or payable-days evidence is missing; cash conversion cycle cannot be assessed cleanly."
            if text not in financial_view["missing_financial_data"]:
                financial_view["missing_financial_data"].append(text)
        if manifest["share_count_limitations"] or manifest["weighted_avg_shares_missing"] or manifest["diluted_shares_missing"]:
            text = "Share-count evidence is incomplete; per-share analysis remains limited."
            if text not in financial_view["financial_interpretation_limits"]:
                financial_view["financial_interpretation_limits"].append(text)
        if manifest["basis_unknown"]:
            text = "Standalone/consolidated basis is unclear; financial comparability remains limited."
            if text not in financial_view["financial_interpretation_limits"]:
                financial_view["financial_interpretation_limits"].append(text)
        payload["financial_committee_view"] = financial_view
        payload["synthesis_limits"] = _dedupe(
            _normalize_optional_string_list(payload.get("synthesis_limits"))
        )
        self._apply_disagreement_cleanup(payload)
        return payload

    def normalize_committee_payload_for_validation(
        self,
        payload: Dict[str, Any],
        *,
        included: Sequence[Dict[str, Any]],
        missing: Sequence[str],
        excluded: Sequence[str],
    ) -> tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
        normalized = json.loads(json.dumps(payload, ensure_ascii=False))
        metadata_repairs: List[Dict[str, Any]]
        enum_repairs: List[Dict[str, Any]]
        string_list_repairs: List[Dict[str, Any]]
        analyst_reference_repairs: List[Dict[str, Any]]

        normalized, metadata_repairs = self._apply_deterministic_metadata(
            normalized,
            included=included,
            missing=missing,
            excluded=excluded,
        )
        normalized, enum_repairs = self._normalize_committee_output_enums(normalized)
        normalized, string_list_repairs = self._normalize_committee_string_lists(normalized)
        normalized, analyst_reference_repairs = self._normalize_committee_analyst_references(
            normalized
        )
        for item in normalized.get("areas_of_disagreement", []) or []:
            if not isinstance(item, dict):
                continue
            disagreement_type = str(item.get("disagreement_type") or "").strip()
            if not disagreement_type:
                item["disagreement_type"] = "different_emphasis"
                _record_enum_repair(
                    enum_repairs,
                    path="areas_of_disagreement[].disagreement_type",
                    original=disagreement_type or None,
                    normalized="different_emphasis",
                    reason="missing_disagreement_type_defaulted",
                )
        return normalized, {
            "metadata_repairs": metadata_repairs,
            "enum_repairs": enum_repairs,
            "string_list_repairs": string_list_repairs,
            "analyst_reference_repairs": analyst_reference_repairs,
        }

    def _finalize_payload(
        self,
        payload: Dict[str, Any],
        *,
        included: Sequence[Dict[str, Any]],
        missing: Sequence[str],
        excluded: Sequence[str],
        committee_input: Dict[str, Any] | None = None,
        metadata_repairs: Sequence[Dict[str, Any]] | None = None,
        enum_repairs: Sequence[Dict[str, Any]] | None = None,
        string_list_repairs: Sequence[Dict[str, Any]] | None = None,
        analyst_reference_repairs: Sequence[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        included_analysts = [item["doctrine_id"] for item in included]
        validated = self._apply_committee_cleanup(
            payload,
            included=included,
            missing=missing,
            excluded=excluded,
        )
        pre_finalization = json.loads(json.dumps(validated, ensure_ascii=False))
        normalized_payload, normalized_repairs = self.normalize_committee_payload_for_validation(
            validated,
            included=included,
            missing=missing,
            excluded=excluded,
        )
        validated = finalize_committee_financial_warnings(normalized_payload)
        committee_financial_truth = dict((validated.get("financial_warning_manifest") or {}).get("committee_financial_truth") or {})
        finalized_financial_view, blocked_stale_financial_warnings, financial_view_repairs = finalize_financial_committee_view(
            validated.get("financial_committee_view") or {},
            committee_financial_truth,
        )
        validated["financial_committee_view"] = finalized_financial_view
        validated = finalize_committee_brief_for_user(
            validated,
            committee_financial_truth,
            enable_financial_enrichment=False,
        )
        finalization_contract_repairs: List[Dict[str, Any]] = []
        finalization_contract_violations: List[Dict[str, Any]] = []
        guard_diagnostics: Dict[str, Any] = {
            "company": self.company,
            "generated_at": str(validated.get("generated_at") or "").strip() or utc_now(),
        }

        def _present(value: Any) -> bool:
            if isinstance(value, str):
                return bool(value.strip())
            if isinstance(value, list):
                return bool(value)
            if isinstance(value, dict):
                return bool(value)
            return value is not None

        def _event(
            *,
            field_path: str,
            pre_value: Any,
            post_value: Any,
            transformation: str,
            reason: str,
        ) -> Dict[str, Any]:
            return {
                "failure_class": "COMMITTEE_FINALIZATION_CONTRACT_VIOLATION",
                "field_path": field_path,
                "pre_finalize_value_present": _present(pre_value),
                "post_finalize_value_present": _present(post_value),
                "transformation": transformation,
                "reason": reason,
            }

        overall = validated.get("overall_committee_view")
        pre_overall = pre_finalization.get("overall_committee_view") if isinstance(pre_finalization, dict) else {}
        if not isinstance(overall, dict):
            finalization_contract_violations.append(
                _event(
                    field_path="overall_committee_view",
                    pre_value=pre_overall,
                    post_value=overall,
                    transformation="finalize_committee_brief_for_user",
                    reason="required object missing or changed type after finalization",
                )
            )
        else:
            for key in ("summary", "dominant_tension"):
                post_value = str(overall.get(key) or "").strip()
                pre_value = str((pre_overall or {}).get(key) or "").strip() if isinstance(pre_overall, dict) else ""
                if post_value:
                    continue
                if pre_value:
                    overall[key] = pre_value
                    finalization_contract_repairs.append(
                        _event(
                            field_path=f"overall_committee_view.{key}",
                            pre_value=pre_value,
                            post_value=post_value,
                            transformation="finalize_committee_brief_for_user",
                            reason="required text was emptied during finalization and restored from pre-finalization value",
                        )
                    )
                else:
                    finalization_contract_violations.append(
                        _event(
                            field_path=f"overall_committee_view.{key}",
                            pre_value=pre_value,
                            post_value=post_value,
                            transformation="finalize_committee_brief_for_user",
                            reason="required text missing after finalization and no supported pre-finalization value exists",
                        )
                    )

        cleaned_unknowns: List[Dict[str, Any]] = []
        pre_unknowns = pre_finalization.get("critical_unknowns") if isinstance(pre_finalization, dict) else []
        for index, item in enumerate(validated.get("critical_unknowns", []) or []):
            if not isinstance(item, dict):
                cleaned_unknowns.append(item)
                continue
            unknown = str(item.get("unknown") or "").strip()
            if unknown:
                cleaned_unknowns.append(item)
                continue
            pre_item = pre_unknowns[index] if isinstance(pre_unknowns, list) and len(pre_unknowns) > index else None
            finalization_contract_repairs.append(
                _event(
                    field_path=f"critical_unknowns[{index}].unknown",
                    pre_value=pre_item.get("unknown") if isinstance(pre_item, dict) else None,
                    post_value=unknown,
                    transformation="finalize_committee_brief_for_user",
                    reason="optional critical unknown was emptied during finalization and dropped from the list",
                )
            )
        validated["critical_unknowns"] = cleaned_unknowns

        if finalization_contract_repairs:
            guard_diagnostics.setdefault("finalization_contract_repairs", []).extend(finalization_contract_repairs)
        if finalization_contract_violations:
            guard_diagnostics["finalization_contract_violations"] = finalization_contract_violations
            guard_diagnostics["status"] = "finalization_contract_violation"
            _write_json(self.diagnostics_path, guard_diagnostics)
            raise ValueError(
                "COMMITTEE_FINALIZATION_CONTRACT_VIOLATION: "
                f"{json.dumps(finalization_contract_violations[:3], ensure_ascii=False)}"
            )
        if committee_input is not None:
            v2_overlay = self._derive_committee_v2_overlay(
                payload=validated,
                committee_input=committee_input,
                included=included,
            )
            validated.update(v2_overlay)
            validated["analysis_mode"] = "committee_synthesis_v2"
            validated["company_slug"] = self.company
            validated["committee_summary"] = v2_overlay.get("committee_summary") or validated.get("committee_summary") or validated.get("overall_committee_view", {}).get("summary", "")
            validated["committee_view"] = v2_overlay.get("committee_view") or validated.get("committee_view")
            validated["committee_direction"] = v2_overlay.get("committee_direction") or validated.get("committee_direction")
            validated["consensus_strength"] = v2_overlay.get("consensus_strength") or validated.get("consensus_strength")
            validated["strongest_shared_convictions"] = v2_overlay.get("strongest_shared_convictions") or validated.get("strongest_shared_convictions")
            validated["major_disagreements"] = v2_overlay.get("major_disagreements") or validated.get("major_disagreements")
            validated["disagreement_explanations"] = v2_overlay.get("disagreement_explanations") or validated.get("disagreement_explanations")
            validated["thesis_strengtheners"] = v2_overlay.get("thesis_strengtheners") or validated.get("thesis_strengtheners")
            validated["thesis_weakeners"] = v2_overlay.get("thesis_weakeners") or validated.get("thesis_weakeners")
            validated["unresolved_items"] = v2_overlay.get("unresolved_items") or validated.get("unresolved_items")
            validated["major_turning_points"] = v2_overlay.get("major_turning_points") or validated.get("major_turning_points")
            validated["financial_judgment"] = v2_overlay.get("financial_judgment") or validated.get("financial_judgment")
            validated["business_quality_judgment"] = v2_overlay.get("business_quality_judgment") or validated.get("business_quality_judgment")
            validated["management_judgment"] = v2_overlay.get("management_judgment") or validated.get("management_judgment")
            validated["capital_allocation_judgment"] = v2_overlay.get("capital_allocation_judgment") or validated.get("capital_allocation_judgment")
            validated["risk_judgment"] = v2_overlay.get("risk_judgment") or validated.get("risk_judgment")
            validated["evidence_confidence"] = v2_overlay.get("evidence_confidence") or validated.get("evidence_confidence")
            validated["what_would_change_the_view"] = v2_overlay.get("what_would_change_the_view") or validated.get("what_would_change_the_view")
            validated["top_diligence_questions"] = v2_overlay.get("top_diligence_questions") or validated.get("top_diligence_questions")
        for item in validated.get("areas_of_disagreement", []) or []:
            if not isinstance(item, dict):
                continue
            disagreement_type = item.get("disagreement_type")
            assert disagreement_type in {
                "true_disagreement",
                "different_emphasis",
                "risk_weighting_difference",
            }, "areas_of_disagreement must contain canonical disagreement_type before final validation"
        validated["years_considered"] = self._years_considered(included)
        validated["evidence_quality_notes"] = self._load_inputs()[3]
        synthesis_limits = list(validated.get("synthesis_limits", []) or [])
        if missing:
            synthesis_limits.append(
                f"Missing analyst inputs: {', '.join(missing)}."
            )
        if excluded:
            synthesis_limits.append(
                f"Excluded analyst inputs due to evidence grounding failure: {', '.join(excluded)}."
            )
        validated["synthesis_limits"] = _dedupe(synthesis_limits)
        final_generated_at = str(validated.get("generated_at") or "").strip() or utc_now()
        validated["generated_at"] = final_generated_at
        diagnostics: Dict[str, Any] = {
            "company": self.company,
            "generated_at": final_generated_at,
            "stripped_fields": [],
            "rewritten_strings": [],
            "field_shapes": _committee_shape_report(validated),
            "normalizations_applied": [],
            "invalid_evidence_ids_dropped": [],
            "warnings_deduped": [],
            "object_list_fields_checked": [
                "areas_of_agreement",
                "areas_of_disagreement",
                "strongest_positive_signals",
                "most_important_risks",
                "critical_unknowns",
                "investigation_questions",
                "financial_committee_view.financial_disagreements",
            ],
        }
        if finalization_contract_repairs:
            diagnostics["finalization_contract_repairs"] = list(finalization_contract_repairs)
        combined_metadata_repairs = list(metadata_repairs or []) + list(
            normalized_repairs.get("metadata_repairs") or []
        )
        combined_enum_repairs = list(enum_repairs or []) + list(
            normalized_repairs.get("enum_repairs") or []
        )
        combined_string_list_repairs = list(string_list_repairs or []) + list(
            normalized_repairs.get("string_list_repairs") or []
        )
        combined_analyst_reference_repairs = list(analyst_reference_repairs or []) + list(
            normalized_repairs.get("analyst_reference_repairs") or []
        )
        if combined_metadata_repairs:
            diagnostics["metadata_repairs"] = combined_metadata_repairs
        if combined_enum_repairs:
            diagnostics["enum_repairs"] = combined_enum_repairs
        if combined_string_list_repairs:
            diagnostics["string_list_repairs"] = combined_string_list_repairs
        if combined_analyst_reference_repairs:
            diagnostics["analyst_reference_repairs"] = combined_analyst_reference_repairs
        if committee_financial_truth:
            diagnostics["committee_financial_truth"] = committee_financial_truth
        if blocked_stale_financial_warnings:
            diagnostics["blocked_stale_financial_warnings"] = blocked_stale_financial_warnings
        if financial_view_repairs:
            diagnostics["owner_earnings_language_repairs"] = financial_view_repairs
            diagnostics["validation_repairs_applied"] = financial_view_repairs
        if validated.get("financial_warning_manifest"):
            diagnostics["recomputed_financial_warning_manifest"] = validated.get("financial_warning_manifest")
            if (validated.get("financial_warning_manifest") or {}).get("blocked_stale_financial_warnings"):
                diagnostics["blocked_stale_financial_warnings"] = (
                    validated.get("financial_warning_manifest") or {}
                ).get("blocked_stale_financial_warnings")
        sanitized_input = _sanitize_committee_payload(
            validated,
            diagnostics=diagnostics,
        )
        if sanitized_input.pop("llm_narrative_failed", False):
            diagnostics["llm_narrative_failed"] = True
        llm_failure_reason = str(sanitized_input.pop("llm_narrative_failure_reason", "") or "").strip()
        if llm_failure_reason:
            diagnostics["llm_narrative_failure_reason"] = llm_failure_reason
        ungrounded_unknowns = _normalize_optional_string_list(
            sanitized_input.pop("ungrounded_suggested_unknowns", [])
        )
        if ungrounded_unknowns:
            diagnostics["ungrounded_suggested_unknowns"] = ungrounded_unknowns
        finalized = validate_committee_output(
            sanitized_input,
            company=self.company,
            included_analysts=included_analysts,
            missing_analysts=missing,
            excluded_analysts=excluded,
            allowed_evidence_ids=self._validation_allowed_evidence_ids(included, sanitized_input),
            analyst_uncertainties=self._analyst_uncertainties(included),
            included_analyst_payloads=included,
            mode="final",
        )
        schema_warnings = finalized.pop("schema_warnings", [])
        if schema_warnings:
            diagnostics["schema_warnings"] = schema_warnings
            diagnostics["normalizations_applied"] = [
                item for item in schema_warnings if "normalized" in item or "inferred" in item
            ]
            diagnostics["invalid_evidence_ids_dropped"] = [
                item for item in schema_warnings if "dropped evidence IDs" in item
            ]
            diagnostics["warnings_deduped"] = [
                item for item in schema_warnings if "dedup" in item.lower()
            ]
        if (
            diagnostics["stripped_fields"]
            or diagnostics["rewritten_strings"]
            or schema_warnings
            or diagnostics.get("metadata_repairs")
            or diagnostics.get("enum_repairs")
            or diagnostics.get("string_list_repairs")
            or diagnostics.get("analyst_reference_repairs")
        ):
            diagnostics["status"] = "sanitized"
            _write_json(self.diagnostics_path, diagnostics)
        elif self.diagnostics_path.exists():
            self.diagnostics_path.unlink()
        return finalized

    def _apply_deterministic_metadata(
        self,
        payload: Dict[str, Any],
        *,
        included: Sequence[Dict[str, Any]],
        missing: Sequence[str],
        excluded: Sequence[str],
    ) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
        normalized = json.loads(json.dumps(payload, ensure_ascii=False))
        included_analysts = [item["doctrine_id"] for item in included]
        deterministic_values = {
            "company": self.company,
            "analysis_mode": "committee_synthesis_v1",
            "analysts_considered": included_analysts,
            "missing_analysts": list(missing),
            "excluded_analysts": list(excluded),
        }
        if not isinstance(normalized.get("generated_at"), str) or not normalized.get("generated_at", "").strip():
            deterministic_values["generated_at"] = utc_now()

        metadata_repairs: list[Dict[str, Any]] = []
        for field, expected in deterministic_values.items():
            original = normalized.get(field)
            if original != expected:
                metadata_repairs.append(
                    {
                        "field": field,
                        "original": original,
                        "normalized": expected,
                    }
                )
            normalized[field] = expected
        return normalized, metadata_repairs

    def _normalize_committee_output_enums(
        self,
        payload: Dict[str, Any],
    ) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
        normalized = json.loads(json.dumps(payload, ensure_ascii=False))
        enum_repairs: list[Dict[str, Any]] = []

        def normalize_confidence(container: Dict[str, Any], key: str, path: str) -> None:
            original = container.get(key)
            if original is None:
                container[key] = "low"
                _record_enum_repair(
                    enum_repairs,
                    path=path,
                    original=original,
                    normalized="low",
                    reason="missing_confidence_defaulted",
                )
                return
            token = _normalize_enum_token(original)
            mapped = CONFIDENCE_ENUM_MAP.get(token)
            if mapped is None:
                mapped = "low"
                _record_enum_repair(
                    enum_repairs,
                    path=path,
                    original=original,
                    normalized=mapped,
                    reason="invalid_confidence_value",
                )
            elif original != mapped:
                _record_enum_repair(
                    enum_repairs,
                    path=path,
                    original=original,
                    normalized=mapped,
                    reason="confidence_enum_normalization",
                )
            container[key] = mapped

        def normalize_rating(container: Dict[str, Any], key: str, path: str) -> None:
            original = container.get(key)
            if original is None:
                return
            token = _normalize_enum_token(original)
            mapped = RATING_ENUM_MAP.get(token)
            if mapped is None:
                return
            if original != mapped:
                _record_enum_repair(
                    enum_repairs,
                    path=path,
                    original=original,
                    normalized=mapped,
                    reason="rating_enum_normalization",
                )
            container[key] = mapped

        def normalize_disagreement_type(container: Dict[str, Any], key: str, path: str) -> None:
            original = container.get(key)
            theme = str(container.get("theme") or "").lower()
            summary = str(container.get("summary") or "").lower()
            why = str(container.get("why_it_matters") or "").lower()
            disagreement = str(container.get("disagreement") or "").lower()
            topic = str(container.get("topic") or "").lower()
            financial_relevance = str(container.get("financial_relevance") or "").lower()
            theme_text = " ".join([theme, summary, why, disagreement, topic, financial_relevance])

            def _infer_from_text() -> str:
                emphasis_text = " ".join([summary, why, disagreement, topic, financial_relevance])
                if any(
                    term in emphasis_text
                    for term in (
                        "weigh the same facts differently",
                        "weight the same facts differently",
                        "frame the opportunity differently",
                        "different angle",
                        "different emphasis",
                        "different priority",
                        "different weighting",
                    )
                ):
                    return "different_emphasis"
                if any(term in theme_text for term in ("risk", "concern", "downside", "red flag")):
                    return "risk_weighting_difference"
                if any(
                    term in theme_text
                    for term in ("conflict", "oppos", "contradict", "contrary", "directly disagree")
                ):
                    return "true_disagreement"
                return "different_emphasis"

            if original is None or not str(original).strip():
                inferred = _infer_from_text()
                container[key] = inferred
                _record_enum_repair(
                    enum_repairs,
                    path=path,
                    original=original,
                    normalized=inferred,
                    reason="missing_disagreement_type_inferred",
                )
                return
            token = _normalize_enum_token(original)
            mapped = DISAGREEMENT_TYPE_ENUM_MAP.get(token)
            if mapped is None:
                mapped = _infer_from_text()
                _record_enum_repair(
                    enum_repairs,
                    path=path,
                    original=original,
                    normalized=mapped,
                    reason="committee_disagreement_type_normalization",
                )
                container[key] = mapped
                return
            if original != mapped:
                _record_enum_repair(
                    enum_repairs,
                    path=path,
                    original=original,
                    normalized=mapped,
                    reason="disagreement_type_enum_normalization",
                )
            container[key] = mapped

        def walk(node: Any, path_parts: list[str]) -> None:
            if isinstance(node, dict):
                current_path = ".".join(path_parts)
                if current_path == "overall_committee_view" and "confidence" not in node:
                    normalize_confidence(node, "confidence", "overall_committee_view.confidence")
                for key, value in list(node.items()):
                    path = ".".join(path_parts + [str(key)])
                    if key in {"confidence", "confidence_level", "evidence_confidence"}:
                        normalize_confidence(node, key, path)
                    elif key == "rating":
                        normalize_rating(node, key, path)
                    elif key == "disagreement_type":
                        normalize_disagreement_type(node, key, path)
                    walk(node.get(key), path_parts + [str(key)])
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, path_parts + [str(index)])

        for index, item in enumerate(normalized.get("areas_of_disagreement", []) or []):
            if isinstance(item, dict) and "disagreement_type" not in item:
                normalize_disagreement_type(
                    item,
                    "disagreement_type",
                    f"areas_of_disagreement.{index}.disagreement_type",
                )
        financial_view = normalized.get("financial_committee_view") or {}
        for index, item in enumerate(financial_view.get("financial_disagreements", []) or []):
            if isinstance(item, dict) and "disagreement_type" not in item:
                normalize_disagreement_type(
                    item,
                    "disagreement_type",
                    f"financial_committee_view.financial_disagreements.{index}.disagreement_type",
                )
        walk(normalized, [])
        return normalized, enum_repairs

    def _normalize_committee_string_lists(
        self,
        payload: Dict[str, Any],
    ) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
        normalized = json.loads(json.dumps(payload, ensure_ascii=False))
        repairs: list[Dict[str, Any]] = []
        fallback_text = "Structured committee note could not be safely represented in the clean summary."

        def _record(path: str, original: Any, normalized_value: str, reason: str) -> None:
            repairs.append(
                {
                    "path": path,
                    "original_type": type(original).__name__,
                    "original": original,
                    "normalized": normalized_value,
                    "reason": reason,
                }
            )

        def _normalize_item(item: Any, item_path: str) -> str | None:
            if isinstance(item, str):
                text = item.strip()
                if not text:
                    return None
                text = _validate_normalized_list_text(item_path, text)
                if len(text) > 240:
                    text = text[:239].rstrip() + "…"
                    _record(item_path, item, text, "string_item_truncated")
                return text
            if isinstance(item, dict):
                try:
                    text = _safe_list_dict_to_string(item, item_path).strip()
                    reason = "dict_item_flattened_to_string"
                except ValueError:
                    text = fallback_text
                    reason = "unsupported_object_replaced_with_fallback"
                if not text:
                    return None
                text = _validate_normalized_list_text(item_path, text)
                if len(text) > 240:
                    text = text[:239].rstrip() + "…"
                    reason = "dict_item_flattened_to_string"
                _record(item_path, item, text, reason)
                return text
            if isinstance(item, list):
                try:
                    text = _safe_list_dict_to_string({"items": item}, item_path).strip()
                    reason = "nested_list_flattened_to_string"
                except ValueError:
                    text = fallback_text
                    reason = "unsupported_object_replaced_with_fallback"
                text = _validate_normalized_list_text(item_path, text)
                if len(text) > 240:
                    text = text[:239].rstrip() + "…"
                _record(item_path, item, text, reason)
                return text
            text = str(item).strip() if item is not None else ""
            if not text:
                return None
            text = _validate_normalized_list_text(item_path, text)
            if len(text) > 240:
                text = text[:239].rstrip() + "…"
            _record(item_path, item, text, "scalar_item_stringified")
            return text

        for field_path, contract in COMMITTEE_FIELD_CONTRACTS.items():
            if contract.get("type") != "string_list":
                continue
            raw_value = _get_nested_path(normalized, field_path)
            if raw_value is None:
                continue
            if isinstance(raw_value, list):
                items = raw_value
            else:
                items = [raw_value]
            normalized_items: list[str] = []
            for index, item in enumerate(items):
                text = _normalize_item(item, f"{field_path}[{index}]")
                if not text or text in normalized_items:
                    continue
                normalized_items.append(text)
                if len(normalized_items) >= 5:
                    break
            _set_nested_path(normalized, field_path, normalized_items)
        return normalized, repairs

    def _normalize_committee_analyst_references(
        self,
        payload: Dict[str, Any],
    ) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
        normalized = json.loads(json.dumps(payload, ensure_ascii=False))
        repairs: list[Dict[str, Any]] = []

        analyst_fields = [
            "analysts_considered",
            "missing_analysts",
            "excluded_analysts",
        ]

        def _apply_path(path: str, value: Any) -> Any:
            canonical, field_repairs = normalize_known_analyst_reference(
                value,
                field=path,
                remove_unknown=True,
            )
            repairs.extend(field_repairs)
            return canonical

        for path in analyst_fields:
            current = _get_nested_path(normalized, path)
            if current is None:
                continue
            _set_nested_path(normalized, path, _apply_path(path, current))

        def walk(node: Any, path_parts: list[str]) -> None:
            if isinstance(node, dict):
                for key, value in list(node.items()):
                    full_path = ".".join(path_parts + [str(key)])
                    if key in {
                        "raised_by",
                        "source_analysts",
                        "supported_by",
                        "analysts",
                        "analysts_involved",
                        "analysts_positive_or_less_concerned",
                        "analysts_cautious_or_negative",
                        "analysts_with_business_quality_focus",
                        "analysts_with_downside_or_execution_focus",
                    }:
                        node[key] = _apply_path(full_path, value)
                    else:
                        walk(value, path_parts + [str(key)])
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, path_parts + [str(index)])

        walk(normalized, [])
        return normalized, repairs

    def cleanup_existing(self) -> Path:
        included, missing, excluded, _warning_notes = self._load_inputs()
        if not self.output_path.exists():
            raise FileNotFoundError(
                f"committee_synthesis.json not found for cleanup: {self.output_path}"
            )
        payload = _load_json(self.output_path)
        committee_input = self._build_committee_input(
            included=included,
            missing=missing,
            excluded=excluded,
            warning_notes=_warning_notes,
        )
        payload, repairs = self.normalize_committee_payload_for_validation(
            payload,
            included=included,
            missing=missing,
            excluded=excluded,
        )
        cleaned = self._finalize_payload(
            payload,
            included=included,
            missing=missing,
            excluded=excluded,
            committee_input=committee_input,
            metadata_repairs=repairs["metadata_repairs"],
            enum_repairs=repairs["enum_repairs"],
            string_list_repairs=repairs["string_list_repairs"],
            analyst_reference_repairs=repairs["analyst_reference_repairs"],
        )
        return _write_json(self.output_path, cleaned)

    def run(self, *, cleanup_only: bool = False) -> Path:
        included, missing, excluded, warning_notes = self._load_inputs()
        if not included:
            raise ValueError(
                "No analyst inputs available for committee synthesis after missing/excluded filtering"
            )
        if cleanup_only:
            return self.cleanup_existing()

        committee_input = self._build_committee_input(
            included=included,
            missing=missing,
            excluded=excluded,
            warning_notes=warning_notes,
        )
        skeleton = build_committee_synthesis_skeleton(
            self.company,
            included,
            _load_json(self._pcim_path()),
            missing_analysts=missing,
            excluded_analysts=excluded,
            warning_notes=warning_notes,
            uncertainty_registry=committee_input.get("allowed_critical_unknowns_registry", []),
            financial_warning_manifest=committee_input.get("financial_warning_manifest", {}),
        )
        narrative_input = self._build_committee_narrative_input(
            skeleton=skeleton,
            committee_input=committee_input,
        )
        token_budget = resolve_stage_token_budget("committee_synthesis")
        target_budget = self._target_budget(token_budget)
        prompt, llm_input_pack, manifest = self._build_compact_prompt_assets(
            {
                "company": self.company,
                "analysts": committee_input.get("analysts", []),
                "missing_analysts": missing,
                "excluded_analysts": excluded,
                "evidence_quality_notes": warning_notes,
                "financial_warning_manifest": narrative_input.get("financial_warning_manifest", {}),
                "allowed_critical_unknowns_registry": narrative_input.get("critical_unknown_registry", []),
                "deterministic_disagreement_candidates": narrative_input.get("deterministic_disagreement_candidates", []),
                "analyst_ratings": narrative_input.get("analyst_ratings", {}),
                "top_positive_signals": narrative_input.get("top_positive_signals", []),
                "top_risks": narrative_input.get("top_risks", []),
                "existing_summary": narrative_input.get("existing_summary", ""),
                "dominant_tension": narrative_input.get("dominant_tension", ""),
            }
        )
        prompt_tokens = manifest["total_prompt_tokens"]
        manifest["token_budget"] = token_budget
        manifest["target_total_prompt_tokens"] = target_budget
        manifest["raw_largest_analyst_blocks"] = sorted(
            manifest["analyst_block_chars"].items(),
            key=lambda item: item[1],
            reverse=True,
        )
        manifest["raw_largest_prompt_sections"] = list(manifest.get("largest_prompt_sections") or [])
        if llm_input_pack["metadata"]["tokens_estimated"] > target_budget or prompt_tokens > target_budget:
            emergency_input, emergency_warnings = self._apply_emergency_committee_compaction(committee_input)
            prompt, llm_input_pack, emergency_manifest = self._build_compact_prompt_assets(emergency_input)
            llm_input_pack["metadata"].setdefault("warnings", []).extend(emergency_warnings)
            manifest.update(
                {
                    "estimated_tokens_after": llm_input_pack["metadata"]["tokens_estimated"],
                    "instruction_tokens": emergency_manifest["instruction_tokens"],
                    "schema_tokens": emergency_manifest["schema_tokens"],
                    "input_pack_tokens": emergency_manifest["input_pack_tokens"],
                    "prompt_tokens_after": emergency_manifest["total_prompt_tokens"],
                    "prompt_chars_after": len(prompt),
                    "truncation_applied": True,
                    "warnings": _dedupe(manifest["warnings"] + emergency_warnings + emergency_manifest["warnings"]),
                    "analyst_block_chars_after": emergency_manifest["analyst_block_chars"],
                    "compacted_largest_prompt_sections": emergency_manifest["largest_prompt_sections"],
                }
            )
            if emergency_manifest["total_prompt_tokens"] > target_budget:
                final_input, final_warnings = self._apply_final_prompt_compaction(emergency_input)
                prompt, llm_input_pack, final_manifest = self._build_compact_prompt_assets(final_input)
                llm_input_pack["metadata"].setdefault("warnings", []).extend(final_warnings)
                manifest.update(
                    {
                        "instruction_tokens": final_manifest["instruction_tokens"],
                        "schema_tokens": final_manifest["schema_tokens"],
                        "input_pack_tokens": final_manifest["input_pack_tokens"],
                        "estimated_tokens_after": llm_input_pack["metadata"]["tokens_estimated"],
                        "prompt_tokens_after": final_manifest["total_prompt_tokens"],
                        "prompt_chars_after": len(prompt),
                        "warnings": _dedupe(manifest["warnings"] + final_warnings + final_manifest["warnings"]),
                        "analyst_block_chars_after": final_manifest["analyst_block_chars"],
                        "compacted_largest_prompt_sections": final_manifest["largest_prompt_sections"],
                    }
                )
            if manifest.get("prompt_tokens_after", 0) > target_budget:
                ultra_input, ultra_warnings = self._apply_ultra_compact_fallback(final_input if 'final_input' in locals() else emergency_input)
                prompt, llm_input_pack, ultra_manifest = self._build_compact_prompt_assets(ultra_input)
                llm_input_pack["metadata"].setdefault("warnings", []).extend(ultra_warnings)
                manifest.update(
                    {
                        "instruction_tokens": ultra_manifest["instruction_tokens"],
                        "schema_tokens": ultra_manifest["schema_tokens"],
                        "input_pack_tokens": ultra_manifest["input_pack_tokens"],
                        "estimated_tokens_after": llm_input_pack["metadata"]["tokens_estimated"],
                        "prompt_tokens_after": ultra_manifest["total_prompt_tokens"],
                        "prompt_chars_after": len(prompt),
                        "warnings": _dedupe(manifest["warnings"] + ultra_warnings + ultra_manifest["warnings"]),
                        "analyst_block_chars_after": ultra_manifest["analyst_block_chars"],
                        "compacted_largest_prompt_sections": ultra_manifest["largest_prompt_sections"],
                    }
                )
            if (
                llm_input_pack["metadata"]["tokens_estimated"] > target_budget
                or manifest["prompt_tokens_after"] > target_budget
            ):
                largest = sorted(
                    (manifest.get("analyst_block_chars_after") or emergency_manifest["analyst_block_chars"]).items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
                raise ValueError(
                    "Committee synthesis prompt remains above budget after compaction: "
                    f"stage=committee_synthesis budget={target_budget} "
                    f"instruction_tokens={manifest['instruction_tokens']} "
                    f"schema_tokens={manifest['schema_tokens']} "
                    f"input_pack_tokens={manifest['input_pack_tokens']} "
                    f"total_prompt_tokens={manifest['prompt_tokens_after']} "
                    f"largest_analyst_blocks={largest[:5]} "
                    f"largest_prompt_sections={(manifest.get('compacted_largest_prompt_sections') or manifest.get('largest_prompt_sections') or [])[:5]} "
                    f"warnings={manifest['warnings']}"
                )
            manifest["budget_status"] = "pass"
        else:
            manifest.update(
                {
                    "estimated_tokens_after": llm_input_pack["metadata"]["tokens_estimated"],
                    "prompt_tokens_after": prompt_tokens,
                    "prompt_chars_after": len(prompt),
                    "budget_status": "pass",
                }
            )
        if manifest.get("prompt_chars_after", 0) > self.SOFT_MAX_PROMPT_CHARS and manifest.get("prompt_tokens_after", 0) <= target_budget:
            manifest["budget_status"] = "pass_with_warning"
            manifest["warnings"] = _dedupe(
                list(manifest.get("warnings") or [])
                + ["Committee synthesis prompt chars exceeded soft target but token budget passed."]
            )
        llm_input_pack["metadata"]["manifest_extra"] = {
            **(llm_input_pack["metadata"].get("manifest_extra") or {}),
            **manifest,
        }
        narrative_payload: Dict[str, Any]
        llm_failure_reason: str | None = None
        try:
            response = call_llm_with_input_pack(
                llm=self.llm,
                prompt=prompt,
                input_pack=llm_input_pack,
                manifest_path=self.panel_dir / "committee_llm_call_manifest.json",
                require_source_artifacts=True,
                response_schema={"type": "object"},
                temperature=0.0,
                system_prompt=COMMITTEE_SYNTHESIS_SYSTEM_PROMPT,
            )
            narrative_payload = self._parse_committee_narrative_payload(response.text)
        except Exception as exc:
            llm_failure_reason = str(exc)
            narrative_payload = self._fallback_narrative_payload(skeleton)

        merged_payload = self._merge_narrative_into_skeleton(skeleton, narrative_payload)
        if llm_failure_reason:
            merged_payload.setdefault("synthesis_limits", []).append(
                "LLM narrative fill failed; deterministic committee skeleton was saved with fallback narrative."
            )
            merged_payload["llm_narrative_failed"] = True
            merged_payload["llm_narrative_failure_reason"] = llm_failure_reason
        included_analysts = [payload["doctrine_id"] for payload in included]
        normalized_response, repairs = self.normalize_committee_payload_for_validation(
            merged_payload,
            included=included,
            missing=missing,
            excluded=excluded,
        )
        finalized = self._finalize_payload(
            normalized_response,
            included=included,
            missing=missing,
            excluded=excluded,
            committee_input=committee_input,
            metadata_repairs=repairs["metadata_repairs"],
            enum_repairs=repairs["enum_repairs"],
            string_list_repairs=repairs["string_list_repairs"],
            analyst_reference_repairs=repairs["analyst_reference_repairs"],
        )
        return _write_json(self.output_path, finalized)
