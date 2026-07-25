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
    financial_limits: List[str] = []
    financial_red_flags: List[str] = []
    investor_questions_from_financials: List[str] = []
    if financial_manifest.get("fcf_missing"):
        missing_financial_data.append("Free cash flow is missing; FCF-based conclusions cannot be assessed.")
        financial_limits.append("Owner-earnings analysis is limited because free cash flow/capex evidence is incomplete.")
        investor_questions_from_financials.append("What capex and free-cash-flow evidence is needed to assess owner earnings and cash-generation quality?")
        financial_red_flags.append("Cash-generation evidence remains incomplete.")
    if financial_manifest.get("capex_missing"):
        missing_financial_data.append("Capex evidence is missing or incomplete.")
    if financial_manifest.get("payables_missing"):
        missing_financial_data.append("Payables evidence is missing, limiting cash-conversion analysis.")
    if financial_manifest.get("basis_unknown"):
        financial_limits.append("Standalone versus consolidated basis remains unclear.")
    if financial_manifest.get("weighted_avg_shares_missing") or financial_manifest.get("diluted_shares_missing"):
        financial_limits.append("Share-count evidence is incomplete, so per-share analysis is limited.")

    areas_of_agreement: List[Dict[str, Any]] = []
    if len(financial_manifest.get("missing_fcf", [])) >= 2:
        areas_of_agreement.append(
            {
                "theme": "free cash flow evidence gap",
                "summary": "Multiple analysts treat missing free-cash-flow evidence as a real limitation on financial judgment.",
                "source_analysts": list(financial_manifest.get("missing_fcf", [])),
                "analysts": list(financial_manifest.get("missing_fcf", [])),
                "evidence_ids": [],
                "evidence_limit": "Built deterministically from analyst financial warning carry-forward.",
            }
        )
    if len(financial_manifest.get("missing_capex", [])) >= 2:
        areas_of_agreement.append(
            {
                "theme": "capex visibility is incomplete",
                "summary": "Multiple analysts highlight missing capex detail as a blocker for cleaner financial interpretation.",
                "source_analysts": list(financial_manifest.get("missing_capex", [])),
                "analysts": list(financial_manifest.get("missing_capex", [])),
                "evidence_ids": [],
                "evidence_limit": "Built deterministically from analyst financial warning carry-forward.",
            }
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

    financial_strengths = [
        item["signal"] for item in strongest_positive_signals[:3]
    ]
    financial_concerns = [item["risk"] for item in most_important_risks[:3]]

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
        "executive_committee_summary": "",
        "synthesis_narrative": [],
        "disagreement_explanation": [],
        "what_to_watch_next": [],
        "ungrounded_suggested_unknowns": [],
    }
    return skeleton


class InvestmentCommitteeSynthesizer:
    TARGET_TOTAL_PROMPT_TOKENS = 5600
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
        manifest = {
            "fcf_missing": False,
            "capex_missing": False,
            "payables_missing": False,
            "weighted_avg_shares_missing": False,
            "diluted_shares_missing": False,
            "basis_unknown": False,
            "working_capital_risk": False,
            "audit_or_reconciliation_warnings": [],
            "missing_fcf": [],
            "missing_capex": [],
            "missing_payables": [],
            "basis_unknown_analysts": [],
            "share_count_limitations": [],
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
                manifest["fcf_missing"] = True
                if analyst and analyst not in manifest["missing_fcf"]:
                    manifest["missing_fcf"].append(analyst)
            if "capex" in lowered_blob:
                manifest["capex_missing"] = True
                if analyst and analyst not in manifest["missing_capex"]:
                    manifest["missing_capex"].append(analyst)
            if "payables" in lowered_blob:
                manifest["payables_missing"] = True
                if analyst and analyst not in manifest["missing_payables"]:
                    manifest["missing_payables"].append(analyst)
                manifest["working_capital_risk"] = True
            if "weighted average shares" in lowered_blob:
                manifest["weighted_avg_shares_missing"] = True
            if "diluted shares" in lowered_blob:
                manifest["diluted_shares_missing"] = True
            if "share-count" in lowered_blob or "share count" in lowered_blob:
                if analyst and analyst not in manifest["share_count_limitations"]:
                    manifest["share_count_limitations"].append(analyst)
            if "basis" in lowered_blob and "unknown" in lowered_blob:
                manifest["basis_unknown"] = True
                if analyst and analyst not in manifest["basis_unknown_analysts"]:
                    manifest.setdefault("basis_unknown_analysts", []).append(analyst)
            if any(token in lowered_blob for token in ("reconciliation", "audit", "validation warning")):
                manifest["audit_or_reconciliation_warnings"].extend(combined)
        manifest["audit_or_reconciliation_warnings"] = _normalize_casefold_deduped_list(
            manifest["audit_or_reconciliation_warnings"]
        )
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
        return {
            "company": self.company,
            "analysts": analysts,
            "missing_analysts": list(missing),
            "excluded_analysts": list(excluded),
            "evidence_quality_notes": list(warning_notes),
            "financial_warning_manifest": self._build_committee_financial_warning_manifest(included),
            "allowed_critical_unknowns_registry": self._build_uncertainty_registry(included),
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
        normalized_payload, normalized_repairs = self.normalize_committee_payload_for_validation(
            validated,
            included=included,
            missing=missing,
            excluded=excluded,
        )
        validated = normalized_payload
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
            metadata_repairs=repairs["metadata_repairs"],
            enum_repairs=repairs["enum_repairs"],
            string_list_repairs=repairs["string_list_repairs"],
            analyst_reference_repairs=repairs["analyst_reference_repairs"],
        )
        return _write_json(self.output_path, finalized)
