from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipelines.pipeline_context import get_context
from .forbidden_language import find_forbidden_recommendation_language

ANALYST_ORDER = ["graham", "buffett", "fisher", "munger", "lynch"]
FORBIDDEN_BRIEF_TERMS = (
    "pcim",
    "cim",
    "evidence_id",
    "evidence_ids",
    "evidence ids",
    "ev_",
    "source_manifest",
    "input_pack",
    "artifact",
    "doctrine_id",
    "schema",
    "validator",
    "grounding_status",
    "raw chunk",
    "source_chunk",
    "multi_year_inputs",
    "analysis_mode",
    "sections_consumed",
    "evidence_map",
    "reasoning_limits",
    "source_item_id",
    "source_artifact",
    "compacted for token budget",
    "provided in the.",
    "but the provides no",
)
LENS_CONFIG = {
    "graham": {
        "title": "Graham School of Thought: Downside Protection",
        "lens_heading": "Downside Protection",
        "lens_text": "This lens looks for balance-sheet caution, financial resilience, and whether the downside appears protected when conditions get worse.",
    },
    "buffett": {
        "title": "Buffett School of Thought: Business Quality & Capital Allocation",
        "lens_heading": "Business Quality & Capital Allocation",
        "lens_text": "This lens focuses on business durability, moat strength, management rationality, and whether capital appears to be allocated with long-term discipline.",
    },
    "fisher": {
        "title": "Fisher School of Thought: Growth Quality & Management Ambition",
        "lens_heading": "Growth Quality & Management Ambition",
        "lens_text": "This lens looks for credible growth runway, strong execution, product strength, and ambition that is backed by real follow-through.",
    },
    "munger": {
        "title": "Munger School of Thought: Incentives, Governance & Avoidable Mistakes",
        "lens_heading": "Incentives, Governance & Avoidable Mistakes",
        "lens_text": "This lens focuses on incentive alignment, governance sanity, behavioural discipline, and whether avoidable mistakes are starting to pile up.",
    },
    "lynch": {
        "title": "Lynch School of Thought: Simple Story, Growth Runway & Hype Check",
        "lens_heading": "Simple Story, Growth Runway & Hype Check",
        "lens_text": "This lens asks whether the business story is understandable, whether growth looks practical, and whether the numbers support the narrative.",
    },
}
REQUIRED_BRIEF_KEYS = {
    "title",
    "lens",
    "what_looks_good",
    "what_needs_caution",
    "what_is_missing",
    "bottom_line",
}
OPTIONAL_BRIEF_KEYS = {
    "financial_lens",
}
MAX_BRIEF_ITEMS = 5
MAX_BRIEF_BULLET_CHARS = 350
MAX_BRIEF_LENS_CHARS = 700
MAX_BRIEF_BOTTOM_LINE_CHARS = 900
MIN_BRIEF_LENS_CHARS = 40
BRIEF_FIELD_ORDER = (
    "title",
    "lens",
    "what_looks_good",
    "what_needs_caution",
    "what_is_missing",
    "bottom_line",
)
BRIEF_LIST_FIELDS = (
    "what_looks_good",
    "what_needs_caution",
    "what_is_missing",
)
BRIEF_SCALAR_LIMITS = {
    "title": None,
    "lens": MAX_BRIEF_LENS_CHARS,
    "financial_lens": MAX_BRIEF_BULLET_CHARS,
    "bottom_line": MAX_BRIEF_BOTTOM_LINE_CHARS,
}
INTERNAL_BRIEF_REPLACEMENTS = (
    (re.compile(r"\bPCIM\b", re.IGNORECASE), "available evidence"),
    (re.compile(r"\bCIM\b", re.IGNORECASE), "available company intelligence"),
    (re.compile(r"\bmulti_year_inputs\b", re.IGNORECASE), "multi-year evidence"),
    (re.compile(r"\bevidence_ids?\b", re.IGNORECASE), "supporting evidence"),
    (re.compile(r"\bevidence ids?\b", re.IGNORECASE), "supporting evidence"),
    (re.compile(r"\bsource_manifest\b", re.IGNORECASE), "source coverage"),
    (re.compile(r"\binput_pack\b", re.IGNORECASE), "analysis materials"),
    (re.compile(r"\bartifact(s)?\b", re.IGNORECASE), "reported information"),
    (re.compile(r"\bdoctrine\b", re.IGNORECASE), "investment lens"),
    (re.compile(r"\bschema\b", re.IGNORECASE), "format"),
    (re.compile(r"\bvalidator\b", re.IGNORECASE), "review check"),
    (re.compile(r"\bgrounding_status\b", re.IGNORECASE), "evidence support"),
    (re.compile(r"\braw chunk\b", re.IGNORECASE), "raw excerpt"),
    (re.compile(r"\bsource_chunk\b", re.IGNORECASE), "source excerpt"),
)

EXTERNAL_READER_FIELD_LABELS = {
    "business_understanding": "business evidence",
    "business_economics_inputs": "business-economics evidence",
    "moat_inputs": "competitive-position evidence",
    "financial_fundamentals_inputs": "financial fundamentals evidence",
    "financial_growth_inputs": "financial growth evidence",
    "profitability_inputs": "profitability evidence",
    "cash_conversion_inputs": "cash-conversion evidence",
    "return_on_capital_inputs": "return-on-capital evidence",
    "balance_sheet_strength_inputs": "balance-sheet evidence",
    "financial_quality_inputs": "financial-quality evidence",
    "per_share_inputs": "per-share evidence",
    "financial_driver_inputs": "financial-driver evidence",
    "multi_year_financial_inputs": "multi-year financial evidence",
    "capital_allocation_inputs": "capital-allocation evidence",
    "management_quality_inputs": "management-quality evidence",
    "governance_and_incentive_inputs": "governance and incentive evidence",
    "working_capital_inputs": "working-capital evidence",
    "growth_execution_inputs": "growth-execution evidence",
    "growth_quality_inputs": "growth-quality evidence",
    "risk_inputs": "risk evidence",
    "ownership_inputs": "ownership evidence",
    "corporate_action_inputs": "corporate-action evidence",
    "multi_year_inputs": "multi-year evidence",
    "uncertainty_missing_data": "information gaps",
    "evidence_map": "supporting evidence",
}

EXTERNAL_READER_REPLACEMENTS = (
    (re.compile(r"\bPCIM\b", re.IGNORECASE), "available company evidence"),
    (re.compile(r"\bCIM\b", re.IGNORECASE), "available company intelligence"),
    (re.compile(r"\bLLM\b", re.IGNORECASE), "analysis"),
    (re.compile(r"\bJSON\b", re.IGNORECASE), "structured analysis output"),
    (re.compile(r"\.json\b", re.IGNORECASE), ""),
    (re.compile(r"\bsource_artifact\b", re.IGNORECASE), "source material"),
    (re.compile(r"\bsource_item_id\b", re.IGNORECASE), "source reference"),
    (re.compile(r"\bevidence_map\b", re.IGNORECASE), "supporting evidence"),
    (re.compile(r"\bevidence_ids?\b", re.IGNORECASE), "supporting evidence"),
    (re.compile(r"\bnormalized_ids\b", re.IGNORECASE), "normalized supporting evidence"),
    (re.compile(r"\boriginal_ids\b", re.IGNORECASE), "original supporting evidence references"),
    (re.compile(r"\bdoctrine_id\b", re.IGNORECASE), "investment lens"),
    (re.compile(r"\bschema_warnings\b", re.IGNORECASE), "review warnings"),
    (re.compile(r"\bvalidation_status\b", re.IGNORECASE), "review status"),
    (re.compile(r"\bevidence_grounding_status\b", re.IGNORECASE), "evidence-support status"),
    (re.compile(r"\binput pack\b", re.IGNORECASE), "analysis materials"),
    (re.compile(r"\bprompt\b", re.IGNORECASE), "analysis framing"),
    (re.compile(r"\bsource chunk\b", re.IGNORECASE), "source excerpt"),
    (re.compile(r"\braw artifact\b", re.IGNORECASE), "raw source material"),
    (re.compile(r"\bgenerated artifact\b", re.IGNORECASE), "generated output"),
    (re.compile(r"\bsource file\b", re.IGNORECASE), "source document"),
    (re.compile(r"\bartifact(s)?\b", re.IGNORECASE), "available evidence"),
    (re.compile(r"\bcompacted PCIM\b", re.IGNORECASE), "condensed company evidence"),
)

EXTERNAL_READER_FORBIDDEN_PATTERNS = (
    (re.compile(r"\bpcim\b", re.IGNORECASE), "PCIM"),
    (re.compile(r"\bcim\b", re.IGNORECASE), "CIM"),
    (re.compile(r"\bartifacts?\b", re.IGNORECASE), "artifact"),
    (re.compile(r"\.json\b", re.IGNORECASE), ".json"),
    (re.compile(r"\bjson\b", re.IGNORECASE), "JSON"),
    (re.compile(r"\bsource_artifact\b", re.IGNORECASE), "source_artifact"),
    (re.compile(r"\bsource_item_id\b", re.IGNORECASE), "source_item_id"),
    (re.compile(r"\bevidence_ids?\b", re.IGNORECASE), "evidence_id"),
    (re.compile(r"\bevidence_map\b", re.IGNORECASE), "evidence_map"),
    (re.compile(r"\buncertainty_missing_data\b", re.IGNORECASE), "uncertainty_missing_data"),
    (re.compile(r"\bbusiness_understanding\b", re.IGNORECASE), "business_understanding"),
    (re.compile(r"\bmanagement_quality_inputs\b", re.IGNORECASE), "management_quality_inputs"),
    (re.compile(r"\bfinancial_growth_inputs\b", re.IGNORECASE), "financial_growth_inputs"),
    (re.compile(r"\bprofitability_inputs\b", re.IGNORECASE), "profitability_inputs"),
    (re.compile(r"\bworking_capital_inputs\b", re.IGNORECASE), "working_capital_inputs"),
    (re.compile(r"\bfinancial_driver_inputs\b", re.IGNORECASE), "financial_driver_inputs"),
    (re.compile(r"\bgrowth_execution_inputs\b", re.IGNORECASE), "growth_execution_inputs"),
    (re.compile(r"\bfinancial_quality_inputs\b", re.IGNORECASE), "financial_quality_inputs"),
    (re.compile(r"\bmulti_year_financial_inputs\b", re.IGNORECASE), "multi_year_financial_inputs"),
    (re.compile(r"\bbalance_sheet_strength_inputs\b", re.IGNORECASE), "balance_sheet_strength_inputs"),
    (re.compile(r"\bper_share_inputs\b", re.IGNORECASE), "per_share_inputs"),
    (re.compile(r"\bcorporate_action_inputs\b", re.IGNORECASE), "corporate_action_inputs"),
    (re.compile(r"\bmulti_year_inputs\b", re.IGNORECASE), "multi_year_inputs"),
    (re.compile(r"\bdoctrine_id\b", re.IGNORECASE), "doctrine_id"),
    (re.compile(r"\bschema_warnings\b", re.IGNORECASE), "schema_warnings"),
    (re.compile(r"\bvalidation_status\b", re.IGNORECASE), "validation_status"),
    (re.compile(r"\bevidence_grounding_status\b", re.IGNORECASE), "evidence_grounding_status"),
    (re.compile(r"\bnormalized_ids\b", re.IGNORECASE), "normalized_ids"),
    (re.compile(r"\boriginal_ids\b", re.IGNORECASE), "original_ids"),
    (re.compile(r"\binput pack\b", re.IGNORECASE), "input pack"),
    (re.compile(r"\bprompt\b", re.IGNORECASE), "prompt"),
    (re.compile(r"\bllm\b", re.IGNORECASE), "LLM"),
    (re.compile(r"\braw artifact\b", re.IGNORECASE), "raw artifact"),
    (re.compile(r"\bgenerated artifact\b", re.IGNORECASE), "generated artifact"),
    (re.compile(r"\bsource file\b", re.IGNORECASE), "source file"),
    (re.compile(r"\bsource chunk\b", re.IGNORECASE), "source chunk"),
    (re.compile(r"\bev_[A-Za-z0-9_\-]+\b", re.IGNORECASE), "evidence_id"),
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


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _normalize_bullet(text: Any) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.rstrip(".") + "." if cleaned and not cleaned.endswith(".") else cleaned


def _normalize_sanitized_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned


def _normalize_brief_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip()
    return ""


def _rewrite_external_reader_labels(text: str) -> str:
    rewritten = str(text or "")
    for internal_label, human_label in EXTERNAL_READER_FIELD_LABELS.items():
        rewritten = re.sub(rf"\b{re.escape(internal_label)}\b", human_label, rewritten, flags=re.IGNORECASE)
    return rewritten


def _rewrite_external_reader_boilerplate(text: str) -> str:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return ""
    if (
        "grounded in" in lowered
        or "is grounded in" in lowered
        or "is interpreted through the doctrine focus" in lowered
        or "consumes sections" in lowered
    ) and any(label in lowered for label in EXTERNAL_READER_FIELD_LABELS):
        return (
            "Insufficient direct evidence is available to make a confident doctrine-specific "
            "assessment."
        )
    return str(text or "")


def rewrite_text_for_external_reader(
    text: Any,
    *,
    field_path: str = "",
    diagnostics: Optional[Dict[str, Any]] = None,
) -> str:
    original = str(text or "").strip()
    if not original:
        return ""
    rewritten = _rewrite_external_reader_boilerplate(original)
    rewritten = _rewrite_external_reader_labels(rewritten)
    for pattern, replacement in INTERNAL_BRIEF_REPLACEMENTS:
        rewritten = pattern.sub(replacement, rewritten)
    for pattern, replacement in EXTERNAL_READER_REPLACEMENTS:
        rewritten = pattern.sub(replacement, rewritten)
    rewritten = re.sub(r"\bev_[A-Za-z0-9_\-]+\b", "supporting evidence", rewritten, flags=re.IGNORECASE)
    rewritten = re.sub(r"\s{2,}", " ", rewritten)
    rewritten = re.sub(r"\s+([,.;:])", r"\1", rewritten)
    rewritten = rewritten.replace("..", ".")
    rewritten = rewritten.strip(" ,")
    rewritten = _normalize_sanitized_text(rewritten)
    if diagnostics is not None and rewritten != original:
        diagnostics.setdefault("rewritten_fields", []).append(
            {
                "field": field_path,
                "original_text": original,
                "rewritten_text": rewritten,
            }
        )
    return rewritten


def _truncate_text_to_limit(text: str, max_chars: Optional[int]) -> str:
    cleaned = _normalize_sanitized_text(text)
    if max_chars is None or len(cleaned) <= max_chars:
        return cleaned

    if max_chars <= 3:
        return cleaned[:max_chars]

    sentence_candidates = [match.end() for match in re.finditer(r"[.!?](?:\s|$)", cleaned)]
    valid_sentence_endings = [end for end in sentence_candidates if end <= max_chars]
    if valid_sentence_endings:
        truncated = cleaned[: valid_sentence_endings[-1]].strip()
        if truncated:
            return truncated

    truncated = cleaned[: max_chars - 3].rstrip(" ,;:-")
    if not truncated:
        truncated = cleaned[: max_chars - 3].strip()
    return f"{truncated}..."


def _brief_validation_error(analyst: str, field: str, reason: str) -> ValueError:
    return ValueError(f'Invalid user_facing_brief for analyst {analyst}: field "{field}" {reason}')


def _validate_no_internal_language(text: str, *, analyst: str, field: str, max_chars: Optional[int] = None) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        raise _brief_validation_error(analyst, field, "is required")
    lowered = cleaned.lower()
    for term in FORBIDDEN_BRIEF_TERMS:
        if term in lowered:
            forbidden = "PCIM" if term == "pcim" else term
            raise _brief_validation_error(analyst, field, f'contains forbidden term "{forbidden}"')
    if max_chars is not None and len(cleaned) > max_chars:
        raise _brief_validation_error(analyst, field, f"exceeds max length {max_chars}")
    if find_forbidden_recommendation_language(cleaned):
        raise _brief_validation_error(analyst, field, "contains recommendation language")
    return cleaned


def _normalize_brief_list(value: Any, *, analyst: str, field: str) -> List[str]:
    if not isinstance(value, list):
        raise _brief_validation_error(analyst, field, "must be a list")
    if len(value) > MAX_BRIEF_ITEMS:
        value = value[:MAX_BRIEF_ITEMS]
    normalized: List[str] = []
    for item in value:
        text = _validate_no_internal_language(
            str(item or "").strip(),
            analyst=analyst,
            field=field,
            max_chars=MAX_BRIEF_BULLET_CHARS,
        )
        normalized.append(_normalize_bullet(text))
    return normalized


def normalize_user_facing_brief_shape(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return value

    normalized = dict(value)
    for field in ("title", "lens", "financial_lens", "bottom_line"):
        normalized[field] = _normalize_brief_scalar(normalized.get(field))

    for field in BRIEF_LIST_FIELDS:
        raw_items = normalized.get(field)
        if raw_items is None:
            normalized[field] = []
            continue
        if isinstance(raw_items, str):
            raw_items = [raw_items]
        elif not isinstance(raw_items, list):
            raw_items = [raw_items]

        cleaned_items: List[str] = []
        for item in raw_items:
            if isinstance(item, (str, int, float, bool)):
                text = str(item).strip()
                if text:
                    cleaned_items.append(text)
        normalized[field] = cleaned_items[:MAX_BRIEF_ITEMS]

    return normalized


def normalize_user_facing_brief_lengths(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return value

    normalized = dict(value)
    for field, max_chars in BRIEF_SCALAR_LIMITS.items():
        normalized[field] = _truncate_text_to_limit(_normalize_brief_scalar(normalized.get(field)), max_chars)

    for field in BRIEF_LIST_FIELDS:
        raw_items = normalized.get(field)
        if not isinstance(raw_items, list):
            continue

        shortened_items: List[str] = []
        for item in raw_items[:MAX_BRIEF_ITEMS]:
            text = _normalize_brief_scalar(item)
            if not text:
                continue
            text = _truncate_text_to_limit(text, MAX_BRIEF_BULLET_CHARS)
            if text:
                shortened_items.append(text)
        normalized[field] = shortened_items

    return normalized


def collect_user_facing_brief_validation_issues(analyst: str, brief: Any) -> List[Dict[str, Any]]:
    if not isinstance(brief, dict):
        return [
            {
                "analyst": analyst,
                "field": "user_facing_brief",
                "forbidden_term": "",
                "original_text": str(brief),
                "suggested_rewrite": "Convert user_facing_brief into an object before validation.",
                "reason": "user_facing_brief must be an object",
            }
        ]

    issues: List[Dict[str, Any]] = []
    for field in BRIEF_FIELD_ORDER + ("financial_lens",):
        value = brief.get(field)
        values = value if isinstance(value, list) else [value]
        for item in values:
            text = str(item or "").strip()
            if not text:
                continue
            matched_any = False
            for pattern, label in EXTERNAL_READER_FORBIDDEN_PATTERNS:
                if pattern.search(text):
                    matched_any = True
                    issues.append(
                        {
                            "analyst": analyst,
                            "field": field,
                            "forbidden_term": label,
                            "original_text": text,
                            "suggested_rewrite": rewrite_text_for_external_reader(
                                text,
                                field_path=f"user_facing_brief.{field}",
                            ),
                            "reason": f'contains forbidden term "{label}"',
                        }
                    )
            if matched_any:
                continue
            if find_forbidden_recommendation_language(text):
                issues.append(
                    {
                        "analyst": analyst,
                        "field": field,
                        "forbidden_term": "recommendation_language",
                        "original_text": text,
                        "suggested_rewrite": "",
                        "reason": "contains recommendation language",
                    }
                )
    return issues


def finalize_user_facing_brief_for_external_reader(
    analyst: str,
    brief: Any,
    doctrine: Optional[Dict[str, Any]] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    brief_diagnostics = diagnostics if diagnostics is not None else {}
    normalized = normalize_user_facing_brief_shape(brief)
    finalized = finalize_user_facing_brief(
        analyst,
        normalized,
        brief_diagnostics.setdefault("brief_repair_diagnostics", []),
    )

    for field in BRIEF_FIELD_ORDER + ("financial_lens",):
        current = finalized.get(field)
        if isinstance(current, list):
            finalized[field] = [
                rewrite_text_for_external_reader(
                    item,
                    field_path=f"user_facing_brief.{field}",
                    diagnostics=brief_diagnostics,
                )
                for item in current
                if str(item or "").strip()
            ]
        else:
            finalized[field] = rewrite_text_for_external_reader(
                current,
                field_path=f"user_facing_brief.{field}",
                diagnostics=brief_diagnostics,
            )

    issues = collect_user_facing_brief_validation_issues(analyst, finalized)
    if issues:
        brief_diagnostics.setdefault("remaining_validation_issues", []).extend(issues)
    return finalized


def finalize_user_facing_brief(
    analyst: str,
    value: Any,
    diagnostics: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    repairs = diagnostics if diagnostics is not None else []
    base: Dict[str, Any]
    if isinstance(value, dict):
        base = dict(value)
    elif isinstance(value, str):
        base = {"bottom_line": str(value).strip()}
    elif isinstance(value, list):
        base = {"what_needs_caution": value}
    else:
        base = {}

    normalized = normalize_user_facing_brief_shape(base)
    finalized = dict(normalized)
    canonical = LENS_CONFIG.get(analyst, {})

    canonical_title = str(canonical.get("title") or "").strip()
    if canonical_title:
        original_title = _normalize_brief_scalar(finalized.get("title"))
        if original_title != canonical_title:
            repairs.append(
                {
                    "field": "user_facing_brief.title",
                    "original_value": original_title,
                    "repaired_value": canonical_title,
                    "repair_reason": "canonical_title_enforced",
                    "repair_status": "repaired",
                }
            )
        finalized["title"] = canonical_title

    canonical_lens = str(canonical.get("lens_text") or "").strip()
    if canonical_lens:
        original_lens = _normalize_brief_scalar(finalized.get("lens"))
        if original_lens != canonical_lens:
            repairs.append(
                {
                    "field": "user_facing_brief.lens",
                    "original_value": original_lens,
                    "repaired_value": canonical_lens,
                    "repair_reason": "canonical_lens_enforced",
                    "repair_status": "repaired",
                }
            )
        finalized["lens"] = canonical_lens
    else:
        finalized["lens"] = _normalize_brief_scalar(finalized.get("lens"))

    for field in BRIEF_LIST_FIELDS:
        raw_items = finalized.get(field)
        if raw_items is None:
            finalized[field] = []
        elif isinstance(raw_items, str):
            finalized[field] = [raw_items] if raw_items.strip() else []
        elif not isinstance(raw_items, list):
            scalar = _normalize_brief_scalar(raw_items)
            finalized[field] = [scalar] if scalar else []

    finalized["bottom_line"] = _normalize_brief_scalar(finalized.get("bottom_line"))
    finalized["financial_lens"] = _normalize_brief_scalar(finalized.get("financial_lens"))

    for key in REQUIRED_BRIEF_KEYS:
        finalized.setdefault(key, [] if key in BRIEF_LIST_FIELDS else "")
    for key in OPTIONAL_BRIEF_KEYS:
        finalized.setdefault(key, "")

    return finalized


def validate_user_facing_brief(analyst: str, value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("user_facing_brief must be an object")
    missing = REQUIRED_BRIEF_KEYS - set(value.keys())
    if missing:
        raise ValueError(f"user_facing_brief missing required keys: {sorted(missing)}")

    issues = collect_user_facing_brief_validation_issues(analyst, value)
    if issues:
        details = "; ".join(
            f'field "{item["field"]}" {item["reason"]}'
            for item in issues
        )
        raise ValueError(f"Invalid user_facing_brief for analyst {analyst}: {details}")

    title = _validate_no_internal_language(value.get("title"), analyst=analyst, field="title")
    lens = _validate_no_internal_language(
        value.get("lens"),
        analyst=analyst,
        field="lens",
        max_chars=MAX_BRIEF_LENS_CHARS,
    )
    bottom_line = _validate_no_internal_language(
        value.get("bottom_line"),
        analyst=analyst,
        field="bottom_line",
        max_chars=MAX_BRIEF_BOTTOM_LINE_CHARS,
    )
    financial_lens = ""
    if value.get("financial_lens"):
        financial_lens = _validate_no_internal_language(
            value.get("financial_lens"),
            analyst=analyst,
            field="financial_lens",
            max_chars=MAX_BRIEF_BULLET_CHARS,
        )

    expected_title = LENS_CONFIG.get(analyst, {}).get("title")
    expected_lens = LENS_CONFIG.get(analyst, {}).get("lens_text")
    if expected_title and title != expected_title:
        raise _brief_validation_error(
            analyst,
            "title",
            f"must match the canonical analyst title: {expected_title}",
        )
    if len(lens) < MIN_BRIEF_LENS_CHARS or lens.strip().lower() == analyst.lower():
        raise _brief_validation_error(
            analyst,
            "lens",
            "must be a full user-facing lens sentence, not a placeholder",
        )
    if expected_lens and lens.strip().lower() == {
        "graham": "benjamin graham",
        "buffett": "warren buffett",
        "fisher": "phil fisher",
        "munger": "charlie munger",
        "lynch": "peter lynch",
    }.get(analyst, ""):
        raise _brief_validation_error(
            analyst,
            "lens",
            "must be a full user-facing lens sentence, not just the investor name",
        )

    if not any(value.get(key) for key in ("what_looks_good", "what_needs_caution", "what_is_missing")):
        raise _brief_validation_error(
            analyst,
            "user_facing_brief",
            "must include content in at least one of what_looks_good, what_needs_caution, or what_is_missing",
        )

    validated = {
        "title": title,
        "lens": lens,
        "what_looks_good": _normalize_brief_list(value.get("what_looks_good"), analyst=analyst, field="what_looks_good"),
        "what_needs_caution": _normalize_brief_list(value.get("what_needs_caution"), analyst=analyst, field="what_needs_caution"),
        "what_is_missing": _normalize_brief_list(value.get("what_is_missing"), analyst=analyst, field="what_is_missing"),
        "bottom_line": bottom_line,
    }
    if financial_lens:
        validated["financial_lens"] = financial_lens
    return validated


def sanitize_user_facing_brief(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return value

    sanitized: Dict[str, Any] = normalize_user_facing_brief_shape(value)

    for key in BRIEF_FIELD_ORDER:
        current = sanitized.get(key)
        if isinstance(current, list):
            sanitized[key] = [rewrite_text_for_external_reader(item, field_path=f"user_facing_brief.{key}") for item in current]
        elif isinstance(current, str):
            sanitized[key] = rewrite_text_for_external_reader(current, field_path=f"user_facing_brief.{key}")
    if isinstance(sanitized.get("financial_lens"), str):
        sanitized["financial_lens"] = rewrite_text_for_external_reader(
            sanitized.get("financial_lens"),
            field_path="user_facing_brief.financial_lens",
        )
    return sanitized


def _render_brief(analyst: str, payload: Dict[str, Any]) -> str:
    brief = payload.get("user_facing_brief")
    if not isinstance(brief, dict):
        raise ValueError(
            f"{analyst}_analysis.json is missing user_facing_brief; markdown generation requires embedded user_facing_brief"
        )
    brief = validate_user_facing_brief(
        analyst,
        normalize_user_facing_brief_lengths(
            finalize_user_facing_brief_for_external_reader(
                analyst,
                sanitize_user_facing_brief(normalize_user_facing_brief_shape(brief)),
            ),
        ),
    )

    lines = [
        f"# {brief['title']}",
        "",
        "## Lens",
        brief["lens"],
    ]
    if brief.get("financial_lens"):
        lines.extend(
            [
                "",
                "## Financial Lens",
                brief["financial_lens"],
            ]
        )
    lines.extend(
        [
            "",
            "## What Looks Good",
        ]
    )
    lines.extend([f"- {item}" for item in brief["what_looks_good"]])
    lines.extend(
        [
            "",
            "## What Needs Caution",
        ]
    )
    lines.extend([f"- {item}" for item in brief["what_needs_caution"]])
    lines.extend(
        [
            "",
            "## What Is Missing",
        ]
    )
    lines.extend([f"- {item}" for item in brief["what_is_missing"]])
    lines.extend(
        [
            "",
            "## Bottom Line",
            brief["bottom_line"],
            "",
        ]
    )
    return "\n".join(lines)


class InvestorBriefBuilder:
    def __init__(self, company: str, companies_root: Path | str = Path("companies")):
        self.company = company
        self.companies_root = Path(companies_root)
        self.panel_dir = self.companies_root / company / "company_memory" / "investor_panel"
        self.briefs_dir = self.panel_dir / "briefs"

    def _analysis_path(self, analyst: str) -> Path:
        return self.panel_dir / f"{analyst}_analysis.json"

    def _brief_path(self, analyst: str) -> Path:
        return self.briefs_dir / f"{analyst}_brief.md"

    def _brief_index_payload(
        self,
        source_analysis_files: List[str],
        briefs_generated: List[str],
        hidden_evidence_ids_by_analyst: Dict[str, List[str]],
        limitations: List[str],
    ) -> Dict[str, Any]:
        return {
            "company": self.company,
            "generated_at": utc_now(),
            "source_analysis_files": source_analysis_files,
            "briefs_generated": briefs_generated,
            "hidden_evidence_ids_by_analyst": hidden_evidence_ids_by_analyst,
            "limitations": limitations,
        }

    def build(self) -> Dict[str, Path]:
        written: Dict[str, Path] = {}
        source_analysis_files: List[str] = []
        briefs_generated: List[str] = []
        hidden_evidence_ids_by_analyst: Dict[str, List[str]] = {}
        limitations: List[str] = []

        for analyst in ANALYST_ORDER:
            analysis_path = self._analysis_path(analyst)
            if not analysis_path.exists():
                limitations.append(f"{analyst}_analysis.json was not found, so no brief was generated for that analyst.")
                continue

            payload = _load_json(analysis_path)
            if not payload:
                limitations.append(f"{analyst}_analysis.json was unreadable or empty, so no brief was generated for that analyst.")
                continue

            try:
                brief_text = _render_brief(analyst, payload)
            except ValueError as exc:
                limitations.append(f"{analyst}_analysis.json was skipped: {exc}")
                continue
            brief_path = self._brief_path(analyst)
            written[brief_path.name] = _write_text(brief_path, brief_text)
            source_analysis_files.append(str(analysis_path))
            briefs_generated.append(str(brief_path))
            hidden_evidence_ids_by_analyst[analyst] = list(payload.get("evidence_ids", []) or [])

        index_payload = self._brief_index_payload(
            source_analysis_files=source_analysis_files,
            briefs_generated=briefs_generated,
            hidden_evidence_ids_by_analyst=hidden_evidence_ids_by_analyst,
            limitations=limitations or [
                "Briefs are derived only from analyst analysis JSON files and intentionally omit internal trace data from the markdown output."
            ],
        )
        index_path = self.briefs_dir / "brief_index.json"
        written[index_path.name] = _write_json(index_path, index_payload)
        return written
