from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List
from pipelines.pipeline_context import get_context

from .forbidden_language import find_forbidden_recommendation_language
from .committee_validator import FORBIDDEN_INTERNAL_BRIEF_TERMS as FORBIDDEN_INTERNAL_TERMS

REQUIRED_TOP_LEVEL_FIELDS = {
    "company",
    "overall_committee_view",
    "financial_committee_view",
    "areas_of_agreement",
    "areas_of_disagreement",
    "strongest_positive_signals",
    "most_important_risks",
    "critical_unknowns",
    "investigation_questions",
    "synthesis_limits",
}

FORBIDDEN_INTERNAL_KEYS = {
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

INTERNAL_PHRASE_REWRITES = {
    "fcf: derived value used": "FCF is derived rather than explicitly reported, so treat it as an estimate.",
    "fcf: fcf is derived from normalized inputs": "FCF is derived rather than explicitly reported, so treat it as an estimate.",
    "critical financial fields include unknown basis entries": "The reporting basis remains unclear, limiting comparability.",
    "diluted shares missing": "Diluted share-count data is missing, limiting per-share analysis.",
    "financial basis remains unknown or unclear": "The reporting basis remains unclear, limiting comparability.",
}

FINANCIAL_CONTRADICTION_REWRITES = {
    "fcf_or_owner_earnings_missing": (
        "Derived FCF / owner-earnings estimate is available for the current usable year, "
        "but precision is limited because maintenance-versus-growth capex split and multi-year bridge history are incomplete."
    ),
    "capex_available_precision_limited": (
        "Identified capex is available, but the maintenance-versus-growth split is unavailable."
    ),
    "payables_available_precision_limited": (
        "Payables/payable-days are available for the current usable year; multi-year payable-support history may still be limited."
    ),
}

FINANCIAL_STRENGTH_KEYWORDS = {
    "revenue", "pat", "profit", "margin", "cash", "cfo", "fcf", "owner earnings", "owner-earnings",
    "debt", "net cash", "net debt", "balance sheet", "liquidity", "working capital", "payables",
    "receivables", "inventory", "capex", "roe", "roce", "roa", "eps", "book value",
}

BUSINESS_ONLY_STRENGTH_KEYWORDS = {
    "business model", "competitive position", "certification", "operational story", "execution story",
    "moat", "customer relationship", "market position", "story", "business quality",
}

LIMITATION_ONLY_KEYWORDS = {
    "basis",
    "standalone",
    "consolidated",
    "share-count",
    "share count",
    "weighted-average",
    "weighted average",
    "diluted share",
    "per-share analysis is limited",
    "comparability",
    "maintenance versus growth capex split",
    "maintenance-versus-growth capex split",
    "multi-year cfo/capex bridge",
    "bridge history",
    "precision is limited",
}

PRECISION_LIMITED_GAP_DEFAULTS = [
    ("maintenance_growth_split_missing", "Maintenance versus growth capex split remains unavailable."),
    ("weighted_avg_shares_missing", "Weighted-average share count remains unavailable."),
    ("diluted_shares_missing", "Diluted share-count data remains unavailable."),
    ("basis_unknown", "Basis consistency remains unclear across reported financials."),
    ("multi_year_bridge_history_incomplete", "Multi-year CFO/capex bridge history remains incomplete."),
]

CANONICAL_SIGNAL_PATTERNS = (
    ("aerospace", "B2G/B2B aerospace and defence manufacturing model"),
    ("defence", "B2G/B2B aerospace and defence manufacturing model"),
    ("vertical integration", "Vertical integration and qualification capabilities"),
    ("qualification", "Vertical integration and qualification capabilities"),
    ("net cash", "Net-cash balance sheet signal"),
    ("owner earnings", "Current-year derived FCF / owner-earnings estimate"),
    ("owner-earnings", "Current-year derived FCF / owner-earnings estimate"),
    ("fcf", "Current-year derived FCF / owner-earnings estimate"),
    ("margin", "Reported margin strength"),
    ("cfo", "Positive operating cash flow signal"),
    ("manufacturing", "Simple manufacturing-oriented business story"),
)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _format_analysts(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(str(item).title() for item in value if str(item).strip())


def _unique_evidence_ids(payload: Dict[str, Any]) -> List[str]:
    evidence_ids: List[str] = []
    for evidence_id in payload.get("evidence_ids", []) or []:
        if evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
    for field in (
        "areas_of_agreement",
        "areas_of_disagreement",
        "strongest_positive_signals",
        "most_important_risks",
    ):
        for item in payload.get(field, []) or []:
            if not isinstance(item, dict):
                continue
            for evidence_id in item.get("evidence_ids", []) or []:
                if evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_id)
    return evidence_ids


def _flatten_strings(value: Any) -> List[str]:
    collected: List[str] = []
    if isinstance(value, str):
        collected.append(value)
    elif isinstance(value, list):
        for item in value:
            collected.extend(_flatten_strings(item))
    elif isinstance(value, dict):
        for item in value.values():
            collected.extend(_flatten_strings(item))
    return collected


def _clean_phrase(text: Any) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    excluded_for_invalid_references = re.match(
        r"^([a-z][a-z .'-]*)\s+was excluded because final analyst evidence[ _-]*ids? are invalid\b",
        value,
        flags=re.IGNORECASE,
    )
    if excluded_for_invalid_references:
        analyst = excluded_for_invalid_references.group(1).strip().title()
        return f"{analyst} was excluded because cited source references could not be verified."
    lowered = value.lower()
    for source, replacement in INTERNAL_PHRASE_REWRITES.items():
        if source in lowered:
            return replacement
    value = value.replace("integr…", "integrity")
    value = value.replace("owner-earnings readiness", "owner-earnings assessment readiness")
    value = value.replace("…", "")
    value = " ".join(value.split())
    value = value.rstrip()
    if value.endswith("..."):
        value = value[:-3].rstrip()
    return value


def _title_case_analysts(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    cleaned: List[str] = []
    for item in value:
        name = str(item or "").strip()
        if not name:
            continue
        titled = name.title()
        if titled not in cleaned:
            cleaned.append(titled)
    return cleaned


def _is_broken_fragment(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if "integr…" in value:
        return True
    if value.endswith("..."):
        return True
    if "≈₹" in value and value.endswith("."):
        return True
    if re.search(r"(?:\.\.\.|…)$", value):
        return True
    if re.search(r"[A-Za-z]-\.\.\.$", value):
        return True
    if "₹" in value and value.endswith("."):
        suffix = value.rsplit("₹", 1)[-1]
        if suffix and suffix.replace(",", "").replace(".", "").strip().isdigit():
            return True
    if re.search(r"\b(?:and|or|with|in|to|for|vs|versus|about|around)\s*$", value.lower()):
        return True
    if re.search(r"\band s\s*$", value.lower()):
        return True
    if value.endswith("-"):
        return True
    if value.count("(") != value.count(")"):
        return True
    if re.search(r"\b[a-z]{1,2}\s*$", value) and len(value.split()) >= 3:
        return True
    return False


def _lookup_truth_amount_crore(truth: Dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = truth.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _format_crore_amount(value: float) -> str:
    rounded_one = round(value, 1)
    if rounded_one.is_integer():
        return f"about ₹{int(rounded_one)} crore"
    return f"about ₹{rounded_one:.1f} crore"


def _ensure_sentence(text: Any) -> str:
    value = _clean_phrase(text)
    if not value:
        return ""
    if _is_broken_fragment(value):
        return ""
    if value.endswith(("?", "!", ".")):
        return value
    return f"{value}."


def _normalize_semantic_key(text: str) -> str:
    lowered = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    lowered = " ".join(lowered.split())
    if "basis is identified as" in lowered or lowered.startswith("basis used "):
        return "basis_used_positive"
    if any(token in lowered for token in ("fcf", "free cash flow", "owner earnings", "owner earnings estimate")):
        return "fcf_owner_earnings"
    if "capex" in lowered and ("split" in lowered or "maintenance" in lowered or "growth" in lowered):
        return "capex_split"
    if "basis" in lowered and any(token in lowered for token in ("standalone", "consolidated", "comparability", "unclear")):
        return "basis"
    if "diluted" in lowered or "weighted average share" in lowered or "per share" in lowered:
        return "share_count"
    if "payables" in lowered or "payable days" in lowered or "cash conversion cycle" in lowered:
        return "payables"
    if any(token in lowered for token in ("working-capital", "working capital", "receivable days", "cash conversion", "payable days")):
        return "working_capital_risk"
    return lowered


def _canonical_financial_phrase(text: str) -> str:
    value = _clean_phrase(text)
    lowered = value.lower()
    normalized = _normalize_semantic_key(value)
    if normalized == "fcf_owner_earnings":
        return (
            "Derived FCF / owner-earnings estimate is available for the current usable year, "
            "but precision is limited by maintenance-versus-growth capex split and incomplete multi-year bridge history."
        )
    if normalized == "basis":
        return "Standalone versus consolidated basis remains unclear, limiting comparability."
    if normalized == "share_count":
        return "Weighted-average and diluted share-count evidence is incomplete, limiting per-share analysis."
    if normalized == "capex_split":
        return "Maintenance versus growth capex split is unavailable."
    if normalized == "working_capital_risk":
        return "Severe working-capital intensity and stretched cash-conversion metrics remain a real concern."
    if "cfo" in lowered and "working-capital" in lowered:
        return "Positive CFO and working-capital metrics are available for the current usable year."
    if "payables" in lowered and "available" in lowered:
        return "Payables and payable-days evidence are available for the current usable year."
    if "basis is identified as" in lowered:
        return value
    return value


def _is_limitation_like_strength(text: str) -> bool:
    lowered = text.lower()
    if "working-capital metrics are available" in lowered or "payables and payable-days evidence are available" in lowered:
        return False
    if "basis is identified as unknown" in lowered:
        return True
    if any(token in lowered for token in ("severe working-capital intensity", "stretched cash-conversion metrics", "real concern")):
        return True
    if _normalize_semantic_key(text) in {"basis", "share_count", "capex_split"}:
        return True
    return any(keyword in lowered for keyword in LIMITATION_ONLY_KEYWORDS)


def _contains_positive_financial_signal(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in (
            "margin strength",
            "positive cfo",
            "operating cash flow",
            "net cash",
            "low debt",
            "derived fcf",
            "owner-earnings estimate is available",
            "revenue",
            "pat",
            "eps",
            "book value",
            "payables and payable-days evidence are available",
            "working-capital metrics are available",
        )
    )


def _synthesize_committee_summary(
    overall: Dict[str, Any],
    financial: Dict[str, Any],
    truth: Dict[str, Any],
) -> str:
    existing = _rewrite_financial_truth_phrase(_clean_phrase(overall.get("summary")), truth)
    positives = financial.get("financial_strengths") or []
    concerns = financial.get("financial_concerns") or []
    working_capital_risk = bool(truth.get("working_capital_risk"))
    lead_positive = next((item for item in positives if _contains_positive_financial_signal(item)), "")
    lead_concern = next(
        (
            item for item in concerns
            if _normalize_semantic_key(item) in {"working_capital_risk", "capex_split", "share_count", "basis"}
            or "pressure" in item.lower()
        ),
        "",
    )
    if working_capital_risk or any(
        "working-capital" in str(item).lower() or "cash-conversion" in str(item).lower()
        for item in concerns
    ):
        positive_clause = "Reported profitability and current-year cash-flow signals look constructive"
        if "owner-earnings estimate is available" in " ".join(positives).lower():
            positive_clause = "Reported profitability and a derived current-year FCF / owner-earnings estimate look constructive"
        concern_clause = "severe working-capital intensity and stretched cash-conversion metrics keep caution high"
        if truth.get("owner_earnings_status") == "available_derived_precision_limited":
            concern_clause += ", especially because cash-generation precision is still limited"
        return f"{positive_clause}, but {concern_clause}."
    if lead_positive and lead_concern:
        return f"{lead_positive.rstrip('.')} But {lead_concern[:1].lower() + lead_concern[1:].rstrip('.')}."
    return existing


def _synthesize_dominant_tension(
    overall: Dict[str, Any],
    truth: Dict[str, Any],
    financial: Dict[str, Any] | None = None,
) -> str:
    existing = _rewrite_financial_truth_phrase(_clean_phrase(overall.get("dominant_tension")), truth)
    concern_blob = " ".join(str(item) for item in ((financial or {}).get("financial_concerns") or []))
    if truth.get("working_capital_risk") or any(token in concern_blob.lower() for token in ("working-capital", "cash-conversion", "receivable days")):
        if truth.get("owner_earnings_status") == "available_derived_precision_limited":
            return "Strong reported profitability versus severe working-capital intensity and precision-limited cash-generation evidence."
        return "Reported profitability versus severe working-capital intensity and stretched cash conversion."
    return existing


def _rewrite_financial_truth_phrase(text: str, truth: Dict[str, Any]) -> str:
    lowered = text.lower()
    amount_crore = _lookup_truth_amount_crore(
        truth,
        "owner_earnings_estimate_value_crore",
        "owner_earnings_estimate_crore",
        "conservative_fcf_estimate_crore",
        "derived_fcf_estimate_crore",
    )
    if (
        truth.get("fcf_missing") is False
        or truth.get("owner_earnings_estimate_available") is True
        or truth.get("owner_earnings_status") == "available_derived_precision_limited"
    ):
        if any(
            phrase in lowered
            for phrase in (
                "free cash flow is missing",
                "fcf-based conclusions cannot be assessed",
                "free cash flow and capex data are not provided",
                "owner-earnings cannot be assessed",
                "owner earnings cannot be assessed",
            )
        ):
            return FINANCIAL_CONTRADICTION_REWRITES["fcf_or_owner_earnings_missing"]
    if truth.get("capex_missing") is False and any(
        phrase in lowered for phrase in ("capex data are not provided", "capex missing", "capex unavailable")
    ):
        return FINANCIAL_CONTRADICTION_REWRITES["capex_available_precision_limited"]
    if truth.get("payables_missing") is False or truth.get("payables_available") is True:
        if any(
            phrase in lowered
            for phrase in ("payables missing", "cash conversion cycle cannot be assessed cleanly", "payables or payable-days evidence is missing")
        ):
            return FINANCIAL_CONTRADICTION_REWRITES["payables_available_precision_limited"]
    if _is_broken_fragment(text):
        if "owner earnings" in lowered or "owner-earnings" in lowered or "fcf" in lowered:
            if amount_crore is not None:
                return _ensure_sentence(
                    f"A derived owner-earnings / conservative FCF estimate of {_format_crore_amount(amount_crore)} is available, "
                    "but precision is limited by capex classification and bridge assumptions"
                )
            return FINANCIAL_CONTRADICTION_REWRITES["fcf_or_owner_earnings_missing"]
        return _ensure_sentence(re.sub(r"[≈~]?\s*₹[\d,]+(?:\.\d+)?\.?", "", text).strip())
    return _ensure_sentence(text)


def _looks_business_only_strength(text: str) -> bool:
    lowered = text.lower()
    has_financial = any(keyword in lowered for keyword in FINANCIAL_STRENGTH_KEYWORDS)
    has_business = any(keyword in lowered for keyword in BUSINESS_ONLY_STRENGTH_KEYWORDS)
    return has_business and not has_financial


def _question_from_statement(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("fcf", "free cash flow")) and any(token in lowered for token in ("derived", "estimate", "explicitly reported")):
        return "How was the derived FCF estimate calculated, and what assumptions drive the estimate?"
    if "basis" in lowered and any(token in lowered for token in ("unclear", "standalone", "consolidated", "comparability")):
        return "Is the financial basis standalone or consolidated, and does it remain consistent across years?"
    if any(token in lowered for token in ("diluted", "weighted-average", "weighted average", "per-share")):
        return "What diluted and weighted-average share counts are needed to assess per-share performance cleanly?"
    if "maintenance" in lowered and "capex" in lowered:
        return "How much of identified capex is maintenance capex versus growth capex?"
    if "owner earnings" in lowered or "owner-earnings" in lowered:
        return "What assumptions are used in the derived owner-earnings estimate, and how sensitive is it to capex classification?"
    if not lowered.endswith("?") and any(lowered.startswith(prefix) for prefix in ("what ", "why ", "how ", "which ", "whether ", "can ", "does ", "did ", "is ", "are ")):
        return f"{text.rstrip('.')}?"
    return ""


def _normalize_question(text: Any, *, fallback_sources: List[str] | None = None) -> str:
    value = _clean_phrase(text)
    if value and not _is_broken_fragment(value):
        if value.endswith("?"):
            return value
        derived = _question_from_statement(value)
        if derived:
            return derived
    for source in fallback_sources or []:
        candidate = _clean_phrase(source)
        if not candidate:
            continue
        derived = _question_from_statement(candidate)
        if derived:
            return derived
    return ""


def _append_positive_signal(cleaned: Dict[str, Any], summary: str) -> None:
    signals = cleaned.setdefault("strongest_positive_signals", [])
    if not isinstance(signals, list):
        return
    normalized = _normalize_semantic_key(summary)
    for item in signals:
        if isinstance(item, dict) and _normalize_semantic_key(str(item.get("summary") or item.get("signal") or "")) == normalized:
            return
    signal_text = summary.rstrip(".")
    signals.append(
        {
            "signal": signal_text[:90],
            "supported_by": [],
            "summary": _ensure_sentence(summary),
            "evidence_ids": [],
        }
    )


def _canonical_signal_heading(signal: str, summary: str) -> str:
    combined = f"{signal} {summary}".lower()
    for token, heading in CANONICAL_SIGNAL_PATTERNS:
        if token in combined:
            return heading
    cleaned = _clean_phrase(signal or summary)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .:-")
    if not cleaned:
        return ""
    if len(cleaned) > 72:
        words = cleaned.split()
        clipped: List[str] = []
        for word in words:
            candidate = " ".join(clipped + [word]).strip()
            if len(candidate) > 72:
                break
            clipped.append(word)
        cleaned = " ".join(clipped).strip()
    if _is_broken_fragment(cleaned):
        return ""
    return cleaned[:1].upper() + cleaned[1:]


def _collect_precision_limited_gaps(truth: Dict[str, Any], financial: Dict[str, Any]) -> List[str]:
    gaps: List[str] = []
    for flag, message in PRECISION_LIMITED_GAP_DEFAULTS:
        if truth.get(flag):
            gaps.append(_canonical_financial_phrase(message))
    for item in (financial.get("financial_interpretation_limits") or []):
        text = _clean_phrase(item)
        if not text:
            continue
        normalized = _normalize_semantic_key(text)
        if normalized in {"capex_split", "basis", "share_count"} and text not in gaps:
            gaps.append(_canonical_financial_phrase(text))
    return _dedupe_clean_list(gaps)


def _clean_title(text: Any, *, truth: Dict[str, Any]) -> str:
    value = _rewrite_financial_truth_phrase(_clean_phrase(text), truth)
    if not value:
        return ""
    value = value.rstrip(".")
    if value.endswith("-"):
        return ""
    if _is_broken_fragment(value) or "..." in value or "…" in value:
        return ""
    if re.search(r"[₹~≈]\s*[\d,]+\.$", value):
        return ""
    return value


def _build_supported_by_list(*values: Any) -> List[str]:
    supported: List[str] = []
    for value in values:
        for analyst in _title_case_analysts(value):
            if analyst not in supported:
                supported.append(analyst)
    return supported


def _dedupe_signal_dicts(items: List[Dict[str, Any]], *, title_key: str, summary_key: str) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        title = str(item.get(title_key, "")).strip()
        summary = str(item.get(summary_key, "")).strip()
        if not title or not summary:
            continue
        key = _normalize_semantic_key(f"{title} {summary}")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _semantic_key_from_item(item: Dict[str, Any], *, fields: Sequence[str]) -> str:
    parts = []
    for field in fields:
        value = str(item.get(field) or "").strip()
        if value:
            parts.append(value)
    return _normalize_semantic_key(" ".join(parts))


def _dedupe_brief_progression_sections(
    what_changed: List[Dict[str, Any]],
    what_strengthened: List[Dict[str, Any]],
    what_weakened: List[Dict[str, Any]],
    what_remains_unproven: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    seen: set[str] = set()

    def _keep(items: List[Dict[str, Any]], *, fields: Sequence[str]) -> List[Dict[str, Any]]:
        kept: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            key = _semantic_key_from_item(item, fields=fields)
            if not key or key in seen:
                continue
            seen.add(key)
            kept.append(item)
        return kept

    deduped_changed = _keep(what_changed, fields=("current_state",))
    deduped_strengthened = _keep(what_strengthened, fields=("conclusion",))
    deduped_weakened = _keep(what_weakened, fields=("conclusion",))
    deduped_unproven = _keep(what_remains_unproven, fields=("item",))
    return deduped_changed, deduped_strengthened, deduped_weakened, deduped_unproven


def _dedupe_clean_list(values: Any, *, require_question: bool = False) -> List[str]:
    cleaned: List[str] = []
    seen = set()
    for item in values or []:
        text = _clean_phrase(item)
        if not text or _is_broken_fragment(text):
            continue
        if require_question and not text.endswith("?"):
            if any(text.lower().startswith(prefix) for prefix in ("what ", "why ", "how ", "which ", "whether ", "can ", "does ", "did ", "is ", "are ")):
                text = f"{text.rstrip('.')}?"
            else:
                continue
        key = _normalize_semantic_key(text)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _is_v2_committee_synthesis(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    if str(payload.get("analysis_mode") or "").strip() == "committee_synthesis_v2":
        return True
    return any(
        key in payload
        for key in (
            "committee_view",
            "committee_direction",
            "consensus_strength",
            "strongest_shared_convictions",
            "major_disagreements",
            "thesis_strengtheners",
            "thesis_weakeners",
            "unresolved_items",
            "major_turning_points",
            "financial_judgment",
            "business_quality_judgment",
            "management_judgment",
            "capital_allocation_judgment",
            "risk_judgment",
            "evidence_confidence",
            "what_would_change_the_view",
            "top_diligence_questions",
            "committee_summary",
        )
    )


def _first_text(*values: Any) -> str:
    for value in values:
        text = _clean_phrase(value)
        if text:
            return text
    return ""


def _truncate_words(text: Any, limit: int) -> str:
    value = _ensure_sentence(text)
    if not value:
        return ""
    words = value.split()
    if len(words) <= limit:
        return value
    return " ".join(words[:limit]).rstrip(",;") + "..."


def _dedupe_across_financial_sections(financial: Dict[str, Any], fields: List[str]) -> None:
    seen = set()
    for field in fields:
        unique_items: List[str] = []
        for item in financial.get(field, []) or []:
            text = _clean_phrase(item)
            if not text:
                continue
            key = _normalize_semantic_key(text)
            if key in seen:
                continue
            seen.add(key)
            unique_items.append(text)
        financial[field] = unique_items


def finalize_committee_brief_for_user(
    committee_synthesis: Dict[str, Any],
    committee_financial_truth: Dict[str, Any] | None = None,
    *,
    enable_financial_enrichment: bool = True,
) -> Dict[str, Any]:
    truth = committee_financial_truth if isinstance(committee_financial_truth, dict) else (
        committee_synthesis.get("committee_financial_truth") if isinstance(committee_synthesis, dict) else {}
    )
    truth = truth if isinstance(truth, dict) else {}
    cleaned = json.loads(json.dumps(committee_synthesis, ensure_ascii=False))

    financial = cleaned.get("financial_committee_view")
    if isinstance(financial, dict):
        precision_limited_gaps = _collect_precision_limited_gaps(truth, financial)
        strengths: List[str] = []
        moved_business_strengths: List[str] = []
        moved_limit_strengths: List[str] = []
        for item in financial.get("financial_strengths", []) or []:
            rewritten = _canonical_financial_phrase(
                _rewrite_financial_truth_phrase(_clean_phrase(item), truth)
            )
            if not rewritten:
                continue
            if _looks_business_only_strength(rewritten):
                moved_business_strengths.append(rewritten)
                continue
            if _is_limitation_like_strength(rewritten):
                moved_limit_strengths.append(rewritten)
                continue
            strengths.append(rewritten)
        if enable_financial_enrichment and truth.get("working_capital_metrics_available"):
            strengths.append("Current-year CFO and working-capital metrics are available, improving visibility.")
        if enable_financial_enrichment and truth.get("payables_available"):
            strengths.append("Payables and payable-days evidence are available for the current usable year.")
        if truth.get("owner_earnings_estimate_available") or truth.get("owner_earnings_status") == "available_derived_precision_limited":
            strengths.append(FINANCIAL_CONTRADICTION_REWRITES["fcf_or_owner_earnings_missing"])
        if enable_financial_enrichment and not truth.get("basis_unknown") and str(financial.get("basis_used") or "").strip().lower() != "unknown":
            strengths.append(f"Financial basis is identified as {str(financial.get('basis_used') or 'reported').strip()}.")
        financial["financial_strengths"] = _dedupe_clean_list(strengths)
        for item in moved_business_strengths:
            _append_positive_signal(cleaned, item)
        for field in ("financial_concerns", "missing_financial_data", "financial_red_flags", "financial_interpretation_limits"):
            rewritten_items = [
                _canonical_financial_phrase(_rewrite_financial_truth_phrase(_clean_phrase(item), truth))
                for item in (financial.get(field) or [])
            ]
            financial[field] = _dedupe_clean_list(rewritten_items)
        financial["financial_interpretation_limits"] = _dedupe_clean_list(
            list(financial.get("financial_interpretation_limits") or []) + moved_limit_strengths
        )
        if enable_financial_enrichment and truth.get("working_capital_metrics_available"):
            financial.setdefault("financial_concerns", [])
            financial["financial_concerns"] = _dedupe_clean_list(
                list(financial["financial_concerns"]) + [
                    "Severe working-capital intensity and stretched cash-conversion metrics remain a real concern."
                ]
            )
        if precision_limited_gaps:
            financial["missing_financial_data"] = _dedupe_clean_list(
                list(financial.get("missing_financial_data") or []) + precision_limited_gaps
            )
        else:
            financial["missing_financial_data"] = _dedupe_clean_list(financial.get("missing_financial_data"))
        financial["financial_consensus"] = _dedupe_clean_list(
            [_canonical_financial_phrase(_rewrite_financial_truth_phrase(_clean_phrase(item), truth)) for item in (financial.get("financial_consensus") or [])]
        )
        financial["investor_questions_from_financials"] = _dedupe_clean_list(
            [
                _normalize_question(
                    item,
                    fallback_sources=[
                        FINANCIAL_CONTRADICTION_REWRITES["fcf_or_owner_earnings_missing"] if truth.get("fcf_missing") is False else "",
                        FINANCIAL_CONTRADICTION_REWRITES["capex_available_precision_limited"] if truth.get("capex_missing") is False else "",
                    ],
                )
                for item in (financial.get("investor_questions_from_financials") or [])
            ],
            require_question=True,
        )
        precision_items: List[str] = []
        if truth.get("owner_earnings_estimate_available") or truth.get("owner_earnings_status") == "available_derived_precision_limited":
            precision_items.append(FINANCIAL_CONTRADICTION_REWRITES["fcf_or_owner_earnings_missing"])
        financial["precision_limited_financial_data"] = _dedupe_clean_list(precision_items)
        financial["financial_concerns"] = _dedupe_clean_list(
            [
                item
                for item in (financial.get("financial_concerns") or [])
                if _normalize_semantic_key(item) != "fcf_owner_earnings"
            ]
        )
        _dedupe_across_financial_sections(
            financial,
            [
                "financial_strengths",
                "financial_concerns",
                "missing_financial_data",
                "precision_limited_financial_data",
                "financial_interpretation_limits",
            ],
        )

    overall = cleaned.get("overall_committee_view")
    if isinstance(overall, dict):
        overall["summary"] = _synthesize_committee_summary(overall, financial or {}, truth)
        overall["dominant_tension"] = _synthesize_dominant_tension(overall, truth, financial or {})

    for field in ("synthesis_narrative", "what_to_watch_next"):
        cleaned[field] = _dedupe_clean_list([
            _rewrite_financial_truth_phrase(_clean_phrase(item), truth)
            for item in (cleaned.get(field) or [])
        ])

    for field in ("evidence_quality_notes", "synthesis_limits"):
        cleaned[field] = _dedupe_clean_list([_ensure_sentence(item) for item in (cleaned.get(field) or [])])

    deduped_unknowns: List[Dict[str, Any]] = []
    seen_unknowns = set()
    for item in cleaned.get("critical_unknowns", []) or []:
        if not isinstance(item, dict):
            continue
        unknown = _clean_phrase(item.get("unknown"))
        why = _rewrite_financial_truth_phrase(_clean_phrase(item.get("why_it_matters")), truth)
        key = _normalize_semantic_key(f"{unknown} {why}")
        if key in seen_unknowns:
            continue
        seen_unknowns.add(key)
        if enable_financial_enrichment:
            if key == "fcf_owner_earnings":
                unknown = "How reliable is the derived FCF / owner-earnings estimate?"
                why = "Derived FCF / owner-earnings estimates are available, but reliability still depends on capex classification and bridge assumptions."
            elif key == "basis":
                unknown = "Is the financial basis standalone or consolidated, and is it consistent across years?"
            elif key == "share_count":
                unknown = "What diluted and weighted-average share counts are needed for clean per-share analysis?"
            elif key == "capex_split":
                unknown = "How much of identified capex is maintenance capex versus growth capex?"
        normalized_unknown = _ensure_sentence(unknown)
        if not normalized_unknown:
            continue
        deduped_unknowns.append(
            {
                **item,
                "unknown": normalized_unknown.rstrip(".") if not normalized_unknown.endswith("?") else normalized_unknown,
                "why_it_matters": _ensure_sentence(why),
            }
        )
    cleaned["critical_unknowns"] = deduped_unknowns

    rewritten_risks: List[Dict[str, Any]] = []
    for item in cleaned.get("most_important_risks", []) or []:
        if not isinstance(item, dict):
            continue
        updated = dict(item)
        updated["risk"] = _clean_title(item.get("risk"), truth=truth)
        updated["summary"] = _rewrite_financial_truth_phrase(_clean_phrase(item.get("summary") or item.get("why_it_matters")), truth)
        if updated["risk"] and updated["summary"] and not _is_broken_fragment(updated["risk"]):
            rewritten_risks.append(updated)
    cleaned["most_important_risks"] = rewritten_risks

    rewritten_signals: List[Dict[str, Any]] = []
    for item in cleaned.get("strongest_positive_signals", []) or []:
        if not isinstance(item, dict):
            continue
        summary = _rewrite_financial_truth_phrase(_clean_phrase(item.get("summary") or item.get("why_it_matters") or item.get("signal")), truth)
        heading = _canonical_signal_heading(str(item.get("signal") or ""), summary)
        supported_by = _build_supported_by_list(
            item.get("supported_by"),
            item.get("source_analysts"),
            item.get("analysts"),
        )
        if not heading or not summary or not supported_by:
            continue
        rewritten_signals.append(
            {
                **item,
                "signal": heading,
                "summary": _ensure_sentence(summary),
                "supported_by": supported_by,
            }
        )
    cleaned["strongest_positive_signals"] = _dedupe_signal_dicts(
        rewritten_signals,
        title_key="signal",
        summary_key="summary",
    )

    deduped_questions: List[Dict[str, Any]] = []
    seen_questions = set()
    unknown_texts = [item.get("unknown", "") for item in deduped_unknowns if isinstance(item, dict)]
    for item in cleaned.get("investigation_questions", []) or []:
        if not isinstance(item, dict):
            continue
        question = _normalize_question(
            item.get("question"),
            fallback_sources=[
                item.get("linked_unknown_or_risk", ""),
                item.get("reason", ""),
                *unknown_texts,
            ],
        )
        reason = _rewrite_financial_truth_phrase(_clean_phrase(item.get("reason")), truth)
        linked = _clean_phrase(item.get("linked_unknown_or_risk"))
        if not question:
            continue
        key = _normalize_semantic_key(question)
        if key in seen_questions:
            continue
        seen_questions.add(key)
        deduped_questions.append(
            {
                "question": question,
                "reason": _ensure_sentence(reason),
                "linked_unknown_or_risk": _ensure_sentence(linked).rstrip("."),
            }
        )
    cleaned["investigation_questions"] = deduped_questions

    return cleaned


def finalize_committee_brief_quality(payload: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = json.loads(json.dumps(payload, ensure_ascii=False))
    cleaned = finalize_committee_brief_for_user(
        cleaned,
        cleaned.get("committee_financial_truth") if isinstance(cleaned, dict) else {},
        enable_financial_enrichment=True,
    )
    return cleaned


def build_canonical_committee_brief_view(
    committee_synthesis: Dict[str, Any],
    committee_financial_truth: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if _is_v2_committee_synthesis(committee_synthesis):
        return build_canonical_committee_brief_view_v2(
            committee_synthesis,
            committee_financial_truth,
        )
    # NOTE: committee_synthesis is already finalized by the synthesizer's _finalize_payload.
    # We consume the investor-ready fields directly — no re-finalization.
    payload = committee_synthesis
    truth = committee_financial_truth if isinstance(committee_financial_truth, dict) else payload.get("committee_financial_truth")
    truth = truth if isinstance(truth, dict) else {}

    overall = payload.get("overall_committee_view", {}) if isinstance(payload.get("overall_committee_view"), dict) else {}
    financial = payload.get("financial_committee_view", {}) if isinstance(payload.get("financial_committee_view"), dict) else {}

    positive_signals: List[Dict[str, Any]] = []
    for item in payload.get("strongest_positive_signals", []) or []:
        if not isinstance(item, dict):
            continue
        signal = _clean_title(item.get("signal"), truth=truth)
        summary = _rewrite_financial_truth_phrase(_clean_phrase(item.get("summary") or item.get("why_it_matters")), truth)
        supported_by = _build_supported_by_list(
            item.get("supported_by"),
            item.get("source_analysts"),
            item.get("analysts"),
        )
        if not signal or not summary:
            continue
        if not supported_by:
            continue
        positive_signals.append(
            {
                "signal": signal,
                "summary": summary,
                "supported_by": supported_by,
                "evidence_ids": [eid for eid in (item.get("evidence_ids") or []) if str(eid).strip()],
            }
        )
    positive_signals = _dedupe_signal_dicts(positive_signals, title_key="signal", summary_key="summary")

    risks: List[Dict[str, Any]] = []
    for item in payload.get("most_important_risks", []) or []:
        if not isinstance(item, dict):
            continue
        risk = _clean_title(item.get("risk"), truth=truth)
        summary = _rewrite_financial_truth_phrase(_clean_phrase(item.get("summary") or item.get("why_it_matters")), truth)
        raised_by = _build_supported_by_list(item.get("raised_by"), item.get("source_analysts"))
        if not risk or not summary:
            continue
        risks.append(
            {
                "risk": risk,
                "summary": summary,
                "severity": str(item.get("severity") or "").strip(),
                "raised_by": raised_by,
                "evidence_ids": [eid for eid in (item.get("evidence_ids") or []) if str(eid).strip()],
            }
        )

    critical_unknowns: List[Dict[str, Any]] = []
    for item in payload.get("critical_unknowns", []) or []:
        if not isinstance(item, dict):
            continue
        unknown = _clean_title(item.get("unknown"), truth=truth)
        why = _rewrite_financial_truth_phrase(_clean_phrase(item.get("why_it_matters")), truth)
        raised_by = _build_supported_by_list(item.get("raised_by"))
        if not unknown or not why:
            continue
        critical_unknowns.append(
            {
                "unknown": unknown,
                "why_it_matters": why,
                "raised_by": raised_by,
            }
        )
    critical_unknowns = _dedupe_signal_dicts(critical_unknowns, title_key="unknown", summary_key="why_it_matters")

    unknown_question_sources = [item.get("unknown", "") for item in critical_unknowns]

    investigation_questions: List[Dict[str, Any]] = []
    for item in payload.get("investigation_questions", []) or []:
        if not isinstance(item, dict):
            continue
        question = _normalize_question(
            item.get("question"),
            fallback_sources=[item.get("reason"), item.get("linked_unknown_or_risk"), *unknown_question_sources],
        )
        reason = _rewrite_financial_truth_phrase(_clean_phrase(item.get("reason")), truth)
        linked = _clean_phrase(item.get("linked_unknown_or_risk"))
        if not question or not reason:
            continue
        investigation_questions.append(
            {
                "question": question,
                "reason": _ensure_sentence(reason),
                "linked_unknown_or_risk": linked,
            }
        )
    deduped_questions: List[Dict[str, Any]] = []
    seen_questions = set()
    for item in investigation_questions:
        key = _normalize_semantic_key(item["question"])
        if key in seen_questions:
            continue
        seen_questions.add(key)
        deduped_questions.append(item)

    financial_view = {
        "financials_used": bool(financial.get("financials_used")),
        "basis_used": str(financial.get("basis_used") or "").strip(),
        "financial_consensus": _dedupe_clean_list([
            _rewrite_financial_truth_phrase(_clean_phrase(item), truth)
            for item in (financial.get("financial_consensus") or [])
        ]),
        "financial_strengths": _dedupe_clean_list([
            _rewrite_financial_truth_phrase(_clean_phrase(item), truth)
            for item in (financial.get("financial_strengths") or [])
        ]),
        "financial_concerns": _dedupe_clean_list([
            _rewrite_financial_truth_phrase(_clean_phrase(item), truth)
            for item in (financial.get("financial_concerns") or [])
        ]),
        "financial_disagreements": [],
        "missing_financial_data": _dedupe_clean_list([
            _canonical_financial_phrase(_rewrite_financial_truth_phrase(_clean_phrase(item), truth))
            for item in (financial.get("missing_financial_data") or [])
        ]),
        "precision_limited_financial_data": _dedupe_clean_list([
            _canonical_financial_phrase(_rewrite_financial_truth_phrase(_clean_phrase(item), truth))
            for item in (financial.get("precision_limited_financial_data") or [])
        ]),
        "financial_red_flags": _dedupe_clean_list([
            _rewrite_financial_truth_phrase(_clean_phrase(item), truth)
            for item in (financial.get("financial_red_flags") or [])
        ]),
        "financial_interpretation_limits": _dedupe_clean_list([
            _rewrite_financial_truth_phrase(_clean_phrase(item), truth)
            for item in (financial.get("financial_interpretation_limits") or [])
        ]),
        "investor_questions_from_financials": _dedupe_clean_list([
            _normalize_question(item, fallback_sources=critical_unknowns)
            for item in (financial.get("investor_questions_from_financials") or [])
        ], require_question=True),
    }

    for item in financial.get("financial_disagreements", []) or []:
        if not isinstance(item, dict):
            continue
        topic = _clean_title(item.get("topic") or item.get("what_they_disagree_on"), truth=truth)
        disagreement = _rewrite_financial_truth_phrase(_clean_phrase(item.get("disagreement") or item.get("what_they_disagree_on")), truth)
        why = _rewrite_financial_truth_phrase(_clean_phrase(item.get("financial_relevance") or item.get("why_it_matters")), truth)
        evidence_limit = _rewrite_financial_truth_phrase(_clean_phrase(item.get("evidence_limit") or item.get("uncertainty")), truth)
        analysts = _build_supported_by_list(item.get("analysts"), item.get("analysts_involved"))
        if not topic or not disagreement:
            continue
        financial_view["financial_disagreements"].append(
            {
                "topic": topic,
                "disagreement": disagreement,
                "disagreement_type": str(item.get("disagreement_type") or "").strip(),
                "analysts": analysts,
                "financial_relevance": why,
                "evidence_limit": evidence_limit,
            }
        )

    analyst_agreements: List[Dict[str, Any]] = []
    for item in payload.get("areas_of_agreement", []) or []:
        if not isinstance(item, dict):
            continue
        theme = _clean_title(item.get("theme"), truth=truth)
        summary = _rewrite_financial_truth_phrase(_clean_phrase(item.get("summary")), truth)
        analysts = _build_supported_by_list(item.get("source_analysts"), item.get("analysts"))
        if not theme or not summary:
            continue
        analyst_agreements.append(
            {
                "theme": theme,
                "summary": summary,
                "analysts": analysts,
                "evidence_ids": [eid for eid in (item.get("evidence_ids") or []) if str(eid).strip()],
            }
        )

    analyst_disagreements: List[Dict[str, Any]] = []
    for item in payload.get("areas_of_disagreement", []) or []:
        if not isinstance(item, dict):
            continue
        theme = _clean_title(item.get("theme"), truth=truth)
        summary = _rewrite_financial_truth_phrase(_clean_phrase(item.get("summary")), truth)
        why = _rewrite_financial_truth_phrase(_clean_phrase(item.get("why_it_matters")), truth)
        if not theme or not summary:
            continue
        analyst_disagreements.append(
            {
                "theme": theme,
                "disagreement_type": str(item.get("disagreement_type") or "").strip(),
                "summary": summary,
                "why_it_matters": why,
                "analysts_positive_or_less_concerned": _build_supported_by_list(item.get("analysts_positive_or_less_concerned")),
                "analysts_cautious_or_negative": _build_supported_by_list(item.get("analysts_cautious_or_negative")),
                "evidence_ids": [eid for eid in (item.get("evidence_ids") or []) if str(eid).strip()],
            }
        )

    return {
        "company": str(payload.get("company") or ""),
        "committee_view": {
            "summary": _rewrite_financial_truth_phrase(_clean_phrase(overall.get("summary")), truth),
            "confidence": str(overall.get("confidence") or "").strip(),
            "dominant_tension": _rewrite_financial_truth_phrase(_clean_phrase(overall.get("dominant_tension")), truth),
        },
        "analyst_agreements": analyst_agreements,
        "analyst_disagreements": analyst_disagreements,
        "financial_view": financial_view,
        "strongest_positive_signals": positive_signals,
        "most_important_risks": risks,
        "critical_unknowns": critical_unknowns,
        "investigation_questions": deduped_questions,
        "evidence_quality_notes": _dedupe_clean_list([
            _rewrite_financial_truth_phrase(_clean_phrase(item), truth)
            for item in (payload.get("evidence_quality_notes") or [])
        ]),
        "synthesis_limits": _dedupe_clean_list([
            _rewrite_financial_truth_phrase(_clean_phrase(item), truth)
            for item in (payload.get("synthesis_limits") or [])
        ]),
        "evidence_ids": _unique_evidence_ids(payload),
        "committee_financial_truth": truth,
    }


def build_canonical_committee_brief_view_v2(
    committee_synthesis: Dict[str, Any],
    committee_financial_truth: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = finalize_committee_brief_quality(committee_synthesis)
    truth = committee_financial_truth if isinstance(committee_financial_truth, dict) else payload.get("committee_financial_truth")
    truth = truth if isinstance(truth, dict) else {}

    latest_period = str(
        payload.get("latest_period")
        or (payload.get("years_considered") or [])[-1] if payload.get("years_considered") else ""
    ).strip()
    if not latest_period:
        latest_period = "latest period not specified"

    committee_view = str(payload.get("committee_view") or payload.get("overall_committee_view", {}).get("summary") or "").strip()
    committee_direction = str(payload.get("committee_direction") or payload.get("overall_committee_view", {}).get("dominant_tension") or "unclear").strip()
    consensus_strength = str(payload.get("consensus_strength") or payload.get("overall_committee_view", {}).get("confidence") or "insufficient").strip()
    committee_summary = _truncate_words(payload.get("committee_summary") or payload.get("executive_committee_summary") or committee_view, 140)
    public_summary = _truncate_words(
        payload.get("public_evidence_summary")
        or payload.get("committee_summary")
        or payload.get("executive_committee_summary")
        or committee_view,
        140,
    )

    def _list_from_items(items: Any, *, keys: List[str], confidence_key: str = "confidence") -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            result: Dict[str, Any] = {}
            for key in keys:
                result[key] = _ensure_sentence(item.get(key) or item.get(key.replace("_", "")))
            if confidence_key in item:
                result[confidence_key] = str(item.get(confidence_key) or "").strip() or "medium"
            results.append(result)
        return results

    def _humanize_state(text: Any) -> str:
        value = _clean_phrase(text)
        if not value:
            return ""
        value = value.replace("_", " ").replace("-", " ")
        value = " ".join(value.split())
        return value[:1].upper() + value[1:] if value else ""

    # ---------------------------------------------------------------------------
    # Surface-safety helpers — filter internal/garbled text before user display
    # ---------------------------------------------------------------------------
    _INTERNAL_STRENGTHENER_PREFIXES = (
        "the project is visible in the source record",
        "investment lens implication",
        "investment lens question",
    )
    _INTERNAL_OR_NEGATIVE_STATE_PHRASES = frozenset({
        "unable to verify", "unable to confirm", "not verified", "evidence not available",
        "later evidence is still being read", "evidence quality change",
        "the project is visible in the source record",
    })
    _RAW_MANAGEMENT_VERB_STARTERS = (
        "continue to ", "continue focus", "develop ", "build a ", "focus on ",
        "grow ", "expand ", "invest ", "pursue ", "implement ",
    )
    _ANALYST_FRAMING_MARKERS = (
        "shows ", "began", "remains", "completed", "operational", "delivered",
        "unproven", "evidence", "partially", "action started", "verified",
        "action began", "outcome", "commissioned",
    )

    def _safe_why(val: str) -> str:
        v = (val or "").strip()
        if any(tok in v.lower() for tok in ("evidence_quality_change", "turning_point is", "turning point is")):
            return ""
        return v

    def _safe_positive_state(val: str) -> str:
        cleaned = (val or "").strip()
        if cleaned.casefold() in _INTERNAL_OR_NEGATIVE_STATE_PHRASES:
            return ""
        if any(cleaned.casefold().startswith(p) for p in ("the project is visible", "unable to")):
            return ""
        # A bare single word (title-cased from a raw state enum) carries no investor context
        if len(cleaned.split()) == 1 and cleaned[0].isupper() and cleaned[1:].islower():
            return ""
        return cleaned

    def _is_internal_strengthener(text: str) -> bool:
        t = (text or "").strip().casefold()
        if any(t.startswith(p) for p in _INTERNAL_STRENGTHENER_PREFIXES):
            return True
        # Raw management directive: imperative verb, no analyst framing words
        if any(t.startswith(v) for v in _RAW_MANAGEMENT_VERB_STARTERS):
            if not any(m in t for m in _ANALYST_FRAMING_MARKERS):
                return True
        return False

    what_changed: List[Dict[str, Any]] = []
    for item in payload.get("major_turning_points", []) or []:
        if not isinstance(item, dict):
            continue
        period = str(item.get("period") or latest_period).strip()
        previous_state = _humanize_state(_first_text(item.get("before"), item.get("prior_state"), item.get("previous_state")))
        # Prefer longer, human-readable fields over bare state tokens from "after"
        current_state_raw = _humanize_state(_first_text(item.get("event"), item.get("summary"), item.get("after"), item.get("current_state")))
        # Skip bare single-word state tokens (e.g. "Operational", "Funded") — use summary instead
        if len((current_state_raw or "").split()) == 1:
            current_state_raw = _humanize_state(_first_text(item.get("summary"), item.get("event"), item.get("after"), item.get("current_state")))
        current_state = current_state_raw
        why_it_matters = _safe_why(_ensure_sentence(item.get("why_it_matters")))
        if not current_state:
            continue
        what_changed.append(
            {
                "period": period or latest_period,
                "previous_state": previous_state or "Earlier evidence was not explicit.",
                "current_state": current_state,
                "why_it_matters": why_it_matters or "This is decision-relevant.",
            }
        )
    if not what_changed:
        _RAW_MGMT_VERB_CHECK = (
            "continue to ", "develop ", "build a ", "focus on ",
            "grow ", "expand ", "invest ", "pursue ", "implement ",
        )
        _ANALYST_MARKER_CHECK = (
            "shows ", "began", "completed", "operational", "delivered",
            "unproven", "evidence", "partially", "verified", "outcome", "commissioned",
        )
        for item in (payload.get("thesis_strengtheners") or [])[:2]:
            if not isinstance(item, dict):
                continue
            summary = _ensure_sentence(item.get("summary") or item.get("conclusion") or item.get("event"))
            if not summary:
                continue
            t = summary.strip().casefold()
            # Skip raw management directives in what_changed fallback
            if any(t.startswith(v) for v in _RAW_MGMT_VERB_CHECK) and not any(m in t for m in _ANALYST_MARKER_CHECK):
                continue
            what_changed.append(
                {
                    "period": str(item.get("period") or latest_period).strip() or latest_period,
                    "previous_state": "Earlier evidence was not explicit.",
                    "current_state": summary,
                    "why_it_matters": _ensure_sentence(item.get("why_it_matters")) or "This changes investor conviction.",
                }
            )

    what_strengthened: List[Dict[str, Any]] = []
    for item in (payload.get("thesis_strengtheners") or [])[:4]:
        if not isinstance(item, dict):
            continue
        conclusion = _ensure_sentence(item.get("summary") or item.get("conclusion") or item.get("event"))
        if not conclusion or _is_internal_strengthener(conclusion):
            continue
        why_raw = _ensure_sentence(item.get("why_it_matters")) or "This matters for conviction."
        why_clean = _safe_why(why_raw) or "This matters for conviction."
        what_strengthened.append(
            {
                "conclusion": conclusion,
                "why_it_matters": why_clean,
                "evidence_confidence": str(item.get("confidence") or "medium").strip() or "medium",
            }
        )

    what_weakened: List[Dict[str, Any]] = []
    for item in (payload.get("thesis_weakeners") or [])[:4]:
        if not isinstance(item, dict):
            continue
        conclusion = _ensure_sentence(item.get("summary") or item.get("conclusion") or item.get("event"))
        if not conclusion:
            continue
        what_weakened.append(
            {
                "conclusion": conclusion,
                "why_it_matters": _ensure_sentence(item.get("why_it_matters")) or "This limits conviction.",
                "evidence_confidence": str(item.get("confidence") or "medium").strip() or "medium",
            }
        )

    major_disagreement: List[Dict[str, Any]] = []
    disagreement_sources = list(payload.get("major_disagreements") or [])
    if not disagreement_sources and payload.get("analyst_disagreements"):
        disagreement_sources = list(payload.get("analyst_disagreements") or [])
    if not disagreement_sources:
        for item in payload.get("areas_of_disagreement", []) or []:
            if not isinstance(item, dict):
                continue
            disagreement_sources.append(
                {
                    "topic": item.get("theme") or item.get("topic"),
                    "side_a_view": item.get("analysts_positive_or_less_concerned"),
                    "side_b_view": item.get("analysts_cautious_or_negative"),
                    "reason_for_disagreement": item.get("why_it_matters") or item.get("summary"),
                    "what_evidence_would_resolve_it": item.get("evidence_ids") and "Later evidence would need to make the direction clearer." or item.get("why_it_matters"),
                    "disagreement_type": item.get("disagreement_type"),
                    "summary": item.get("summary"),
                }
            )
    for item in disagreement_sources[:2]:
        if not isinstance(item, dict):
            continue
        topic = _first_text(item.get("topic"), item.get("theme"), item.get("summary"))
        side_a = _first_text(item.get("side_a_view"), item.get("analysts_positive_or_less_concerned"), item.get("analysts_on_side_a"))
        side_b = _first_text(item.get("side_b_view"), item.get("analysts_cautious_or_negative"), item.get("analysts_on_side_b"))
        why_exists = _ensure_sentence(item.get("reason_for_disagreement") or item.get("why_it_matters") or item.get("summary"))
        evidence_to_resolve = _ensure_sentence(item.get("what_evidence_would_resolve_it") or item.get("evidence_to_resolve") or item.get("evidence_limit"))
        disagreement_type = str(item.get("disagreement_type") or "").strip() or "unclear"
        if not topic:
            continue
        major_disagreement.append(
            {
                "topic": topic,
                "side_a": side_a or "One side sees the evidence as supportive.",
                "side_b": side_b or "The other side remains more cautious.",
                "why_the_disagreement_exists": why_exists or "The panel is weighting the same evidence differently.",
                "evidence_that_could_resolve_it": evidence_to_resolve or "Later evidence would need to make the direction clearer.",
                "disagreement_type": disagreement_type,
            }
        )

    def _build_view_block(assessment: str, direction: str, strongest: str, concern: str, unresolved: str, *, fallback_label: str) -> Dict[str, Any]:
        assessment_text = _clean_phrase(assessment)
        if not assessment_text or len(assessment_text.split()) < 4:
            assessment_text = fallback_label
        strongest_text = _clean_phrase(strongest)
        if not strongest_text or len(strongest_text.split()) < 4:
            strongest_text = f"{fallback_label} strongest evidence remains visible but incomplete."
        concern_text = _clean_phrase(concern)
        if not concern_text or len(concern_text.split()) < 4:
            concern_text = f"The main concern remains that {fallback_label.lower()} is still not fully proven."
        unresolved_text = _clean_phrase(unresolved)
        if not unresolved_text or len(unresolved_text.split()) < 4:
            unresolved_text = f"The key unresolved issue is still whether {fallback_label.lower()} becomes durable."
        return {
            "assessment": _ensure_sentence(assessment_text) or "The committee view remains incomplete.",
            "direction": direction or "unclear",
            "strongest_evidence": _ensure_sentence(strongest_text) or "The evidence is still developing.",
            "main_concern": _ensure_sentence(concern_text) or "The main concern remains unresolved.",
            "unresolved_issue": _ensure_sentence(unresolved_text) or "The central question remains open.",
        }

    management_view = _build_view_block(
        assessment=_first_text(payload.get("management_judgment", {}).get("assessment"), payload.get("management_judgment", {}).get("summary"), "Management evidence is being read through follow-through and progression."),
        direction=str(payload.get("management_judgment", {}).get("direction") or committee_direction or "unclear").strip() or "unclear",
        strongest=_first_text(payload.get("management_judgment", {}).get("strongest_evidence"), payload.get("management_judgment", {}).get("assessment")),
        concern=_first_text(payload.get("management_judgment", {}).get("main_concern"), payload.get("management_judgment", {}).get("unresolved_issue")),
        unresolved=_first_text(payload.get("management_judgment", {}).get("unresolved_issue"), "Whether later evidence keeps matching management's stated direction."),
        fallback_label="Management quality is being read through follow-through and progression",
    )
    capital_allocation_view = _build_view_block(
        assessment=_first_text(payload.get("capital_allocation_judgment", {}).get("assessment"), "Capital allocation is being judged by later outcomes, not by deployment alone."),
        direction=str(payload.get("capital_allocation_judgment", {}).get("direction") or "unclear").strip() or "unclear",
        strongest=_first_text(payload.get("capital_allocation_judgment", {}).get("strongest_evidence"), payload.get("capital_allocation_judgment", {}).get("assessment")),
        concern=_first_text(payload.get("capital_allocation_judgment", {}).get("main_concern"), "Returns are still not fully proven."),
        unresolved=_first_text(payload.get("capital_allocation_judgment", {}).get("unresolved_issue"), "The return on deployed capital still needs later proof."),
        fallback_label="Capital allocation is being judged by later outcomes, not deployment alone",
    )
    financial_view = _build_view_block(
        assessment=_first_text(payload.get("financial_judgment", {}).get("assessment"), "Financial quality is being read through earnings, cash conversion, and balance-sheet resilience."),
        direction=str(payload.get("financial_judgment", {}).get("direction") or "unclear").strip() or "unclear",
        strongest=_first_text(payload.get("financial_judgment", {}).get("strongest_evidence"), payload.get("financial_judgment", {}).get("assessment")),
        concern=_first_text(payload.get("financial_judgment", {}).get("main_concern"), "The financial evidence still has limits."),
        unresolved=_first_text(payload.get("financial_judgment", {}).get("unresolved_issue"), "The key financial question is still open."),
        fallback_label="Financial quality is being read through earnings, cash conversion, and balance-sheet resilience",
    )
    risk_view = _build_view_block(
        assessment=_first_text(payload.get("risk_judgment", {}).get("assessment"), "Risk remains a live part of the thesis."),
        direction=str(payload.get("risk_judgment", {}).get("direction") or "unclear").strip() or "unclear",
        strongest=_first_text(payload.get("risk_judgment", {}).get("strongest_evidence"), payload.get("risk_judgment", {}).get("assessment")),
        concern=_first_text(payload.get("risk_judgment", {}).get("main_concern"), "The most material risk remains unresolved."),
        unresolved=_first_text(payload.get("risk_judgment", {}).get("unresolved_issue"), "A disconfirming signal is still possible."),
        fallback_label="Risk remains a live part of the thesis",
    )

    what_remains_unproven: List[Dict[str, Any]] = []
    for item in payload.get("unresolved_items") or []:
        if not isinstance(item, dict):
            continue
        question = _ensure_sentence(item.get("question"))
        if not question:
            continue
        what_remains_unproven.append(
            {
                "item": question.rstrip("."),
                "why_it_matters": _ensure_sentence(item.get("why_it_matters")) or "This remains decision-relevant.",
                "evidence_needed": _ensure_sentence(item.get("evidence_needed")) or "Later evidence is needed.",
                "current_confidence": str(item.get("current_confidence") or "low").strip() or "low",
            }
        )
    if not what_remains_unproven:
        for item in payload.get("critical_unknowns", []) or []:
            if not isinstance(item, dict):
                continue
            unknown = _ensure_sentence(item.get("unknown"))
            if not unknown:
                continue
            what_remains_unproven.append(
                {
                    "item": unknown.rstrip("."),
                    "why_it_matters": _ensure_sentence(item.get("why_it_matters")) or "This remains decision-relevant.",
                    "evidence_needed": "Later evidence is needed.",
                    "current_confidence": "low",
                }
            )
    what_remains_unproven = what_remains_unproven[:5]

    what_changed, what_strengthened, what_weakened, what_remains_unproven = _dedupe_brief_progression_sections(
        what_changed,
        what_strengthened,
        what_weakened,
        what_remains_unproven,
    )

    what_would_change_the_view: List[str] = []
    for item in payload.get("what_would_change_the_view") or []:
        sentence = _ensure_sentence(item)
        if sentence and sentence not in what_would_change_the_view:
            what_would_change_the_view.append(sentence)
    if not what_would_change_the_view:
        for item in what_remains_unproven:
            what_would_change_the_view.append(f"Committee view could strengthen if {item['item'].lower()} is later resolved.")
    what_would_change_the_view = what_would_change_the_view[:5]

    top_questions_to_investigate: List[Dict[str, Any]] = []
    questions_source = list(payload.get("top_diligence_questions") or [])
    if not questions_source:
        questions_source = [
            {
                "rank": idx + 1,
                "question": item.get("item", ""),
                "why_it_matters": item.get("why_it_matters", ""),
                "evidence_needed": item.get("evidence_needed", ""),
            }
            for idx, item in enumerate(what_remains_unproven)
        ]
    for idx, item in enumerate(questions_source[:5]):
        if not isinstance(item, dict):
            continue
        question = _ensure_sentence(item.get("question"))
        if not question:
            continue
        top_questions_to_investigate.append(
            {
                "rank": int(item.get("rank") or idx + 1),
                "question": question.rstrip("?") + "?",
                "why_it_matters": _ensure_sentence(item.get("why_it_matters")) or "This could change the view.",
                "evidence_needed": _ensure_sentence(item.get("evidence_needed")) or "Later evidence is needed.",
            }
        )

    evidence_confidence = payload.get("evidence_confidence") if isinstance(payload.get("evidence_confidence"), dict) else {}
    evidence_confidence = {
        "level": str(evidence_confidence.get("level") or "medium").strip() or "medium",
        "basis": _dedupe_clean_list(evidence_confidence.get("basis") or [committee_summary, "v2 synthesis overlay"]),
        "main_limitation": _ensure_sentence(
            _first_text(
                (evidence_confidence.get("limitations") or [])[0] if isinstance(evidence_confidence.get("limitations"), list) and evidence_confidence.get("limitations") else "",
                "Some parts of the evidence remain incomplete.",
            )
        ),
    }

    committee_phrase = committee_view if len(committee_view.split()) > 1 else "a mixed business with still-developing evidence"
    positive_reason = _first_text(
        _safe_why(what_changed[0].get("why_it_matters", "") if what_changed else ""),
        _safe_why(what_strengthened[0].get("why_it_matters", "") if what_strengthened else ""),
        "the latest evidence still shows visible delivery and capacity progress",
    )
    positive_core = _first_text(
        _safe_positive_state(what_changed[0].get("current_state", "") if what_changed else ""),
        (what_strengthened[0].get("conclusion") if what_strengthened else ""),
        (payload.get("strongest_shared_convictions") or [{}])[0].get("conclusion") if payload.get("strongest_shared_convictions") else "",
        "visible delivery and capacity progress",
    )
    positive_phrase = f"{positive_core} because {positive_reason}" if positive_reason else positive_core

    concern_reason = _first_text(
        financial_view.get("main_concern"),
        capital_allocation_view.get("main_concern"),
        risk_view.get("main_concern"),
        "capital allocation returns and basis clarity are still unresolved",
    )
    concern_core = _first_text(
        financial_view.get("main_concern"),
        capital_allocation_view.get("main_concern"),
        risk_view.get("main_concern"),
        "capital allocation returns and basis clarity are still unresolved",
    )
    concern_phrase = f"{concern_core} because {concern_reason}" if concern_reason else concern_core

    unresolved_reason = _first_text(
        (what_remains_unproven[0].get("why_it_matters") if what_remains_unproven else ""),
        (what_remains_unproven[0].get("evidence_needed") if what_remains_unproven else ""),
        financial_view.get("unresolved_issue"),
        capital_allocation_view.get("unresolved_issue"),
        "whether the newer operating evidence turns into durable cash generation and per-share improvement",
    )
    unresolved_core = _first_text(
        (what_remains_unproven[0].get("item") if what_remains_unproven else ""),
        financial_view.get("unresolved_issue"),
        capital_allocation_view.get("unresolved_issue"),
        "whether the newer operating evidence turns into durable cash generation and per-share improvement",
    )
    unresolved_phrase = f"{unresolved_core} because {unresolved_reason}" if unresolved_reason else unresolved_core
    bottom_line = (
        f"The committee currently sees {committee_phrase}. "
        f"The strongest positive is {positive_phrase}. "
        f"The biggest concern is {concern_phrase}. "
        f"The main unresolved issue is {unresolved_phrase}. "
        "That keeps the view constructive, but not yet fully convinced."
    )
    bottom_line = _truncate_words(bottom_line, 140)

    if not what_changed:
        what_changed = [{
            "period": latest_period,
            "previous_state": "No clear turning point was preserved in the source synthesis.",
            "current_state": "The committee view remains anchored to the same evidence base.",
            "why_it_matters": "This is still a progression question, even if the source evidence is thin.",
        }]

    concise_progression = _truncate_words(
        " ".join(
            f"{item['period']}: {item['previous_state']} -> {item['current_state']}"
            for item in what_changed[:3]
        ),
        120,
    )

    return {
        "brief_mode": "v2",
        "company_slug": str(payload.get("company_slug") or payload.get("company") or "").strip(),
        "latest_period": latest_period,
        "committee_view": committee_view or "The committee sees the business through a progression lens.",
        "committee_direction": committee_direction or "unclear",
        "consensus_strength": consensus_strength or "insufficient",
        "bottom_line": bottom_line,
        "what_changed": what_changed[:4],
        "what_strengthened": what_strengthened[:4],
        "what_weakened": what_weakened[:4],
        "major_disagreement": major_disagreement[:2],
        "management_view": management_view,
        "capital_allocation_view": capital_allocation_view,
        "financial_view": financial_view,
        "risk_view": risk_view,
        "what_remains_unproven": what_remains_unproven,
        "what_would_change_the_view": what_would_change_the_view,
        "top_questions_to_investigate": top_questions_to_investigate,
        "evidence_confidence": evidence_confidence,
        "generated_at": str(payload.get("generated_at") or "").strip(),
        "major_turning_points": what_changed[:4],
        "concise_progression": concise_progression,
        "public_evidence_summary": public_summary,
        "committee_summary": committee_summary,
        "analysis_mode": str(payload.get("analysis_mode") or "committee_synthesis_v2"),
        "committee_financial_truth": truth,
    }


def validate_brief_view(
    brief_view: Dict[str, Any],
    committee_financial_truth: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not isinstance(brief_view, dict):
        raise ValueError("brief_view must be an object")
    if brief_view.get("brief_mode") == "v2":
        return validate_brief_view_v2(brief_view, committee_financial_truth)
    truth = committee_financial_truth if isinstance(committee_financial_truth, dict) else brief_view.get("committee_financial_truth")
    truth = truth if isinstance(truth, dict) else {}

    required = {
        "company",
        "committee_view",
        "analyst_agreements",
        "analyst_disagreements",
        "financial_view",
        "strongest_positive_signals",
        "most_important_risks",
        "critical_unknowns",
        "investigation_questions",
        "evidence_quality_notes",
        "synthesis_limits",
    }
    missing = required - set(brief_view.keys())
    if missing:
        raise ValueError(f"brief_view missing required fields: {sorted(missing)}")

    text_blob = "\n".join(_flatten_strings(brief_view))
    lowered = text_blob.lower()
    blocked_phrases = []
    if truth.get("fcf_missing") is False and "fcf-based conclusions cannot be assessed" in lowered:
        blocked_phrases.append("fcf_missing=false contradiction")
    if truth.get("capex_missing") is False and "capex data are not provided" in lowered:
        blocked_phrases.append("capex_missing=false contradiction")
    if "free cash flow and capex data are not provided" in lowered:
        blocked_phrases.append("stale_fcf_capex_missing_phrase")
    if blocked_phrases:
        raise ValueError(f"brief_view contains stale financial contradiction(s): {blocked_phrases}")
    if "..." in text_blob or "…" in text_blob:
        raise ValueError("brief_view contains ellipsis truncation")
    if re.search(r"[≈~]?\s*₹[\d,]+\.(?:\s|$)", text_blob):
        raise ValueError("brief_view contains incomplete currency fragment")
    for fragment in _flatten_strings(brief_view):
        stripped = str(fragment or "").strip()
        if re.search(r"[A-Za-z]-$", stripped):
            raise ValueError("brief_view contains dangling hyphen fragment")
        if _is_broken_fragment(stripped):
            raise ValueError("brief_view contains semantically truncated fragment")

    financial_view = brief_view.get("financial_view") or {}
    missing_financial_data = financial_view.get("missing_financial_data") or []
    precision_limited = financial_view.get("precision_limited_financial_data") or []
    if precision_limited and any(
        "no material missing financial data was recorded" in str(item).lower()
        for item in missing_financial_data
    ):
        raise ValueError("brief_view contains contradictory missing-data default despite precision-limited gaps")

    for item in brief_view.get("strongest_positive_signals", []) or []:
        if not item.get("supported_by"):
            raise ValueError("brief_view strongest_positive_signals item has empty supported_by")
    for item in brief_view.get("investigation_questions", []) or []:
        question = str(item.get("question") or "").strip()
        if not question or not question.endswith("?"):
            raise ValueError("brief_view investigation question is blank or not a question")

    seen_unknowns = set()
    for item in brief_view.get("critical_unknowns", []) or []:
        key = _normalize_semantic_key(f"{item.get('unknown', '')} {item.get('why_it_matters', '')}")
        if key in seen_unknowns:
            raise ValueError("brief_view contains duplicate critical unknowns")
        seen_unknowns.add(key)
    return brief_view


def validate_brief_view_v2(
    brief_view: Dict[str, Any],
    committee_financial_truth: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not isinstance(brief_view, dict):
        raise ValueError("brief_view must be an object")
    required = {
        "brief_mode",
        "company_slug",
        "latest_period",
        "committee_view",
        "committee_direction",
        "consensus_strength",
        "bottom_line",
        "what_changed",
        "what_strengthened",
        "what_weakened",
        "major_disagreement",
        "management_view",
        "capital_allocation_view",
        "financial_view",
        "risk_view",
        "what_remains_unproven",
        "what_would_change_the_view",
        "top_questions_to_investigate",
        "evidence_confidence",
        "generated_at",
    }
    missing = required - set(brief_view.keys())
    if missing:
        raise ValueError(f"brief_view missing required fields: {sorted(missing)}")

    if brief_view.get("brief_mode") != "v2":
        raise ValueError("brief_view.brief_mode must be v2")
    if not isinstance(brief_view.get("company_slug"), str) or not brief_view["company_slug"].strip():
        raise ValueError("brief_view.company_slug is required")
    if not isinstance(brief_view.get("latest_period"), str) or not brief_view["latest_period"].strip():
        raise ValueError("brief_view.latest_period is required")
    if not isinstance(brief_view.get("committee_view"), str) or not brief_view["committee_view"].strip():
        raise ValueError("brief_view.committee_view is required")
    if brief_view.get("committee_direction") not in {"strengthening", "weakening", "stable", "mixed", "unclear"}:
        raise ValueError("brief_view.committee_direction must be strengthening, weakening, stable, mixed, or unclear")
    if brief_view.get("consensus_strength") not in {"high", "medium", "low", "fragmented", "insufficient"}:
        raise ValueError("brief_view.consensus_strength must be high, medium, low, fragmented, or insufficient")
    if not isinstance(brief_view.get("bottom_line"), str) or not brief_view["bottom_line"].strip():
        raise ValueError("brief_view.bottom_line is required")
    if not isinstance(brief_view.get("what_changed"), list):
        raise ValueError("brief_view.what_changed must be a list")
    if not isinstance(brief_view.get("what_strengthened"), list):
        raise ValueError("brief_view.what_strengthened must be a list")
    if not isinstance(brief_view.get("what_weakened"), list):
        raise ValueError("brief_view.what_weakened must be a list")
    if not isinstance(brief_view.get("major_disagreement"), list):
        raise ValueError("brief_view.major_disagreement must be a list")
    if not isinstance(brief_view.get("what_remains_unproven"), list):
        raise ValueError("brief_view.what_remains_unproven must be a list")
    if not isinstance(brief_view.get("what_would_change_the_view"), list):
        raise ValueError("brief_view.what_would_change_the_view must be a list")
    if not isinstance(brief_view.get("top_questions_to_investigate"), list):
        raise ValueError("brief_view.top_questions_to_investigate must be a list")
    if not isinstance(brief_view.get("evidence_confidence"), dict):
        raise ValueError("brief_view.evidence_confidence must be an object")
    if not isinstance(brief_view.get("management_view"), dict):
        raise ValueError("brief_view.management_view must be an object")
    if not isinstance(brief_view.get("capital_allocation_view"), dict):
        raise ValueError("brief_view.capital_allocation_view must be an object")
    if not isinstance(brief_view.get("financial_view"), dict):
        raise ValueError("brief_view.financial_view must be an object")
    if not isinstance(brief_view.get("risk_view"), dict):
        raise ValueError("brief_view.risk_view must be an object")
    if not isinstance(brief_view.get("generated_at"), str) or not brief_view["generated_at"].strip():
        raise ValueError("brief_view.generated_at is required")

    for field in ("what_changed", "what_strengthened", "what_weakened", "major_disagreement", "what_remains_unproven", "top_questions_to_investigate"):
        for item in brief_view.get(field, []) or []:
            if not isinstance(item, dict):
                raise ValueError(f"brief_view.{field} must contain objects")

    for block_name in ("management_view", "capital_allocation_view", "financial_view", "risk_view"):
        block = brief_view.get(block_name) or {}
        for key in ("assessment", "direction", "strongest_evidence", "main_concern", "unresolved_issue"):
            if not isinstance(block.get(key), str) or not block.get(key, "").strip():
                raise ValueError(f"brief_view.{block_name}.{key} is required")

    evidence_confidence = brief_view.get("evidence_confidence") or {}
    if evidence_confidence.get("level") not in {"high", "medium", "low", "insufficient"}:
        raise ValueError("brief_view.evidence_confidence.level must be high, medium, low, or insufficient")
    if not isinstance(evidence_confidence.get("basis"), list) or any(not isinstance(item, str) for item in evidence_confidence.get("basis", [])):
        raise ValueError("brief_view.evidence_confidence.basis must be a list of strings")
    if not isinstance(evidence_confidence.get("main_limitation"), str) or not evidence_confidence.get("main_limitation", "").strip():
        raise ValueError("brief_view.evidence_confidence.main_limitation is required")
    if not isinstance(brief_view.get("committee_financial_truth") if brief_view.get("committee_financial_truth") is not None else {}, dict):
        raise ValueError("brief_view.committee_financial_truth must be an object when present")

    bottom_line_words = len(str(brief_view.get("bottom_line") or "").split())
    if bottom_line_words < 70 or bottom_line_words > 170:
        raise ValueError("brief_view.bottom_line must be concise and substantive")
    if len(str(brief_view.get("committee_view") or "").split()) > 45:
        raise ValueError("brief_view.committee_view is too long")
    if len(brief_view.get("what_changed", [])) > 4:
        raise ValueError("brief_view.what_changed must contain at most 4 items")
    if len(brief_view.get("what_strengthened", [])) > 4:
        raise ValueError("brief_view.what_strengthened must contain at most 4 items")
    if len(brief_view.get("what_weakened", [])) > 4:
        raise ValueError("brief_view.what_weakened must contain at most 4 items")
    if len(brief_view.get("major_disagreement", [])) > 2:
        raise ValueError("brief_view.major_disagreement must contain at most 2 items")
    if len(brief_view.get("what_remains_unproven", [])) > 5:
        raise ValueError("brief_view.what_remains_unproven must contain at most 5 items")
    if len(brief_view.get("what_would_change_the_view", [])) > 5:
        raise ValueError("brief_view.what_would_change_the_view must contain at most 5 items")
    if len(brief_view.get("top_questions_to_investigate", [])) > 5:
        raise ValueError("brief_view.top_questions_to_investigate must contain at most 5 items")
    return brief_view


def _find_forbidden_keys(value: Any, *, path: str = "$") -> List[str]:
    found: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_INTERNAL_KEYS:
                found.append(child_path)
            found.extend(_find_forbidden_keys(item, path=child_path))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            found.extend(_find_forbidden_keys(item, path=f"{path}[{idx}]"))
    return found


def validate_committee_brief_source(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("committee_synthesis.json must contain an object")
    missing = REQUIRED_TOP_LEVEL_FIELDS - set(payload.keys())
    if missing:
        raise ValueError(
            f"committee_synthesis.json missing required fields: {sorted(missing)}"
        )

    overall = payload.get("overall_committee_view")
    if not isinstance(overall, dict):
        raise ValueError("overall_committee_view must be an object")
    for field in ("summary", "confidence", "dominant_tension"):
        if not isinstance(overall.get(field), str) or not overall[field].strip():
            raise ValueError(f"overall_committee_view.{field} is required")

    if "source_chunk" in json.dumps(payload, ensure_ascii=False):
        raise ValueError("committee_synthesis.json must not contain source_chunk")
    forbidden_key_paths = _find_forbidden_keys(payload)
    if forbidden_key_paths:
        raise ValueError(
            "committee_synthesis.json contains forbidden internal fields: "
            f"{forbidden_key_paths}"
        )

    financial = payload.get("financial_committee_view")
    if not isinstance(financial, dict):
        raise ValueError("financial_committee_view must be an object")
    if not isinstance(financial.get("financials_used"), bool):
        raise ValueError("financial_committee_view.financials_used must be a boolean")
    if not isinstance(financial.get("basis_used"), str) or not financial["basis_used"].strip():
        raise ValueError("financial_committee_view.basis_used is required")
    for field in (
        "financial_consensus",
        "financial_strengths",
        "financial_concerns",
        "missing_financial_data",
        "financial_red_flags",
        "financial_interpretation_limits",
        "investor_questions_from_financials",
    ):
        if not isinstance(financial.get(field), list):
            raise ValueError(f"financial_committee_view.{field} must be a list")
    if not isinstance(financial.get("financial_disagreements"), list):
        raise ValueError("financial_committee_view.financial_disagreements must be a list")

    public_fields: List[Any] = [
        payload.get("company"),
        payload.get("overall_committee_view"),
        payload.get("financial_committee_view"),
        payload.get("areas_of_agreement"),
        payload.get("areas_of_disagreement"),
        payload.get("strongest_positive_signals"),
        payload.get("most_important_risks"),
        payload.get("critical_unknowns"),
        payload.get("investigation_questions"),
        payload.get("evidence_quality_notes"),
        payload.get("synthesis_limits"),
    ]
    if str(payload.get("analysis_mode") or "").strip() == "committee_synthesis_v2" or _is_v2_committee_synthesis(payload):
        public_fields.extend(
            [
                payload.get("committee_view"),
                payload.get("committee_direction"),
                payload.get("consensus_strength"),
                payload.get("strongest_shared_convictions"),
                payload.get("major_disagreements"),
                payload.get("thesis_strengtheners"),
                payload.get("thesis_weakeners"),
                payload.get("unresolved_items"),
                payload.get("major_turning_points"),
                payload.get("financial_judgment"),
                payload.get("business_quality_judgment"),
                payload.get("management_judgment"),
                payload.get("capital_allocation_judgment"),
                payload.get("risk_judgment"),
                payload.get("evidence_confidence"),
                payload.get("what_would_change_the_view"),
                payload.get("top_diligence_questions"),
            ]
        )
    # Apply _clean_phrase() before forbidden-term scanning so that analyst exclusion
    # messages containing raw diagnostic data (e.g. "buffett was excluded because final
    # analyst evidence IDs are invalid: [{'reason': 'unknown_evidence_id'}]") are rewritten
    # to user-safe equivalents ("Buffett was excluded because cited source references could
    # not be verified.") before the check runs. Genuine prose leakage of internal terms
    # (e.g. "Supported by evidence_id ev-123.") is not matched by _clean_phrase() and
    # still triggers the forbidden-term check.
    cleaned_strings = [_clean_phrase(s) for s in _flatten_strings(public_fields)]
    text_blob = "\n".join(s for s in cleaned_strings if s)
    matches = find_forbidden_recommendation_language(text_blob)
    if matches:
        raise ValueError(
            'committee_synthesis.json contains forbidden recommendation language: '
            f'"{matches[0]["matched_text"]}"'
        )
    lowered = text_blob.lower()
    for term in FORBIDDEN_INTERNAL_TERMS:
        if term in lowered:
            raise ValueError(
                f'committee_synthesis.json contains forbidden internal term: "{term}"'
            )
    return payload


class CommitteeBriefRenderer:
    def __init__(self, company: str, companies_root: Path | str = Path("companies")):
        self.company = company
        self.companies_root = Path(companies_root)
        self.panel_dir = self.companies_root / company / "company_memory" / "investor_panel"
        self.source_path = self.panel_dir / "committee_synthesis.json"
        self.output_path = self.panel_dir / "committee_brief.md"

    def _load_committee_synthesis(self) -> Dict[str, Any]:
        payload = _load_json(self.source_path)
        if not payload:
            raise FileNotFoundError(
                f"committee_synthesis.json not found or unreadable: {self.source_path}"
            )
        # committee_synthesis.json is already finalized by the synthesizer (_finalize_payload).
        # We validate the already-finalized payload directly — no re-finalization.
        sanitized = validate_committee_brief_source(payload)
        brief_view = build_canonical_committee_brief_view(
            sanitized,
            sanitized.get("committee_financial_truth"),
        )
        return validate_brief_view(brief_view, sanitized.get("committee_financial_truth"))

    def _render_section_separator(self, lines: List[str]) -> None:
        lines.extend(["", "---", ""])

    def _render(self, payload: Dict[str, Any], *, include_evidence_ids: bool) -> str:
        if payload.get("brief_mode") == "v2":
            return self._render_v2(payload, include_evidence_ids=include_evidence_ids)
        company_name = str(payload.get("company") or self.company).title()
        overall = payload["committee_view"]
        lines = [
            f"# Investment Committee Brief — {company_name}",
            "",
            "## Committee View",
            overall["summary"].strip(),
            "",
            f"**Confidence:** {overall['confidence'].strip()}",
            "",
            f"**Dominant Tension:** {overall['dominant_tension'].strip()}",
        ]
        self._render_section_separator(lines)

        lines.append("## Where the Analysts Agree")
        for item in payload.get("analyst_agreements", []) or []:
            lines.extend(
                [
                    "",
                    f"### {item.get('theme', '').strip()}",
                    str(item.get("summary", "")).strip(),
                    "",
                    f"**Analysts:** {_format_analysts(item.get('analysts'))}",
                ]
            )
            self._render_section_separator(lines)

        financial = payload["financial_view"]
        lines.extend(["## Financial View"])
        lines.extend(
            [
                "",
                f"**Financials Used:** {'Yes' if financial['financials_used'] else 'No'}",
                "",
                f"**Basis Used:** {financial['basis_used'].strip()}",
            ]
        )
        consensus = financial.get("financial_consensus", []) or []
        if consensus:
            lines.extend(["", "**Financial Consensus:**"])
            lines.extend([f"- {str(item).strip()}" for item in consensus if str(item).strip()])
        strengths = financial.get("financial_strengths", []) or []
        if strengths:
            lines.extend(["", "**Financial Strengths:**"])
            lines.extend([f"- {str(item).strip()}" for item in strengths if str(item).strip()])
        concerns = financial.get("financial_concerns", []) or []
        if concerns:
            lines.extend(["", "**Financial Concerns:**"])
            lines.extend([f"- {str(item).strip()}" for item in concerns if str(item).strip()])
        disagreements = financial.get("financial_disagreements", []) or []
        if disagreements:
            lines.extend(["", "**Financial Disagreements:**"])
            for item in disagreements:
                topic = str(item.get("topic") or item.get("what_they_disagree_on") or "").strip()
                disagreement = str(item.get("disagreement") or item.get("what_they_disagree_on") or "").strip()
                analysts = item.get("analysts") or item.get("analysts_involved")
                financial_relevance = str(item.get("financial_relevance") or item.get("why_it_matters") or "").strip()
                evidence_limit = str(item.get("evidence_limit") or item.get("uncertainty") or "").strip()
                lines.extend(
                    [
                        f"- {topic or disagreement}",
                        f"  - Disagreement: {disagreement}",
                        f"  - Type: {str(item.get('disagreement_type', '')).strip()}",
                        f"  - Analysts: {_format_analysts(analysts)}",
                        f"  - Why it matters: {financial_relevance}",
                        f"  - Evidence limit: {evidence_limit}",
                    ]
                )
        missing = financial.get("missing_financial_data", []) or []
        lines.extend(["", "**Missing Financial Data:**"])
        lines[-1] = "**Missing / Incomplete Inputs:**"
        if missing:
            lines.extend([f"- {str(item).strip()}" for item in missing if str(item).strip()])
        else:
            lines.append("- No material missing or incomplete inputs were recorded.")
        precision_limited = financial.get("precision_limited_financial_data", []) or []
        if precision_limited:
            lines.extend(["", "**Available but Precision-Limited:**"])
            lines.extend([f"- {str(item).strip()}" for item in precision_limited if str(item).strip()])
        red_flags = financial.get("financial_red_flags", []) or []
        if red_flags:
            lines.extend(["", "**Financial Red Flags:**"])
            lines.extend([f"- {str(item).strip()}" for item in red_flags if str(item).strip()])
        limits = financial.get("financial_interpretation_limits", []) or []
        if limits:
            lines.extend(["", "**Financial Interpretation Limits:**"])
            lines.extend([f"- {str(item).strip()}" for item in limits if str(item).strip()])
        questions = financial.get("investor_questions_from_financials", []) or []
        if questions:
            lines.extend(["", "**Financial Investigation Questions:**"])
            lines.extend([f"- {str(item).strip()}" for item in questions if str(item).strip()])
        self._render_section_separator(lines)

        disagreements = payload.get("analyst_disagreements", []) or []
        lines.append("## Where the Analysts Differ")
        if disagreements:
            for item in disagreements:
                lines.extend(
                    [
                        "",
                        f"### {item.get('theme', '').strip()}",
                        f"**Type:** {str(item.get('disagreement_type', '')).strip()}",
                        "",
                        str(item.get("summary", "")).strip(),
                        "",
                        f"**Why it matters:** {str(item.get('why_it_matters', '')).strip()}",
                    ]
                )
                self._render_section_separator(lines)
        else:
            lines.extend(["", "No material disagreement was recorded."])
            self._render_section_separator(lines)

        lines.append("## Strongest Positive Signals")
        for item in payload.get("strongest_positive_signals", []) or []:
            lines.extend(
                [
                    "",
                    f"### {item.get('signal', '').strip()}",
                    str(item.get("summary") or item.get("why_it_matters") or "").strip(),
                    "",
                    f"**Supported by:** {_format_analysts(item.get('supported_by'))}",
                ]
            )
            self._render_section_separator(lines)

        lines.append("## Most Important Risks")
        for item in payload.get("most_important_risks", []) or []:
            lines.extend(
                [
                    "",
                    f"### {item.get('risk', '').strip()}",
                    f"**Severity:** {str(item.get('severity', '')).strip()}",
                    "",
                    str(item.get("summary") or item.get("why_it_matters") or "").strip(),
                    "",
                    f"**Raised by:** {_format_analysts(item.get('raised_by'))}",
                ]
            )
            self._render_section_separator(lines)

        lines.append("## Critical Unknowns")
        for item in payload.get("critical_unknowns", []) or []:
            lines.extend(
                [
                    "",
                    f"### {item.get('unknown', '').strip()}",
                    str(item.get("why_it_matters", "")).strip(),
                    "",
                    f"**Raised by:** {_format_analysts(item.get('raised_by'))}",
                ]
            )
            self._render_section_separator(lines)

        lines.append("## Investigation Questions")
        for index, item in enumerate(payload.get("investigation_questions", []) or [], start=1):
            lines.extend(
                [
                    "",
                    f"### Question {index}",
                    str(item.get("question", "")).strip(),
                    "",
                    f"**Why this matters:** {str(item.get('reason', '')).strip()}",
                    "",
                    f"**Linked unknown/risk:** {str(item.get('linked_unknown_or_risk', '')).strip()}",
                ]
            )
            self._render_section_separator(lines)

        lines.append("## Evidence Quality Notes")
        notes = payload.get("evidence_quality_notes", []) or []
        if notes:
            lines.extend([""] + [f"- {str(note).strip()}" for note in notes])
        else:
            lines.extend(["", "No material evidence-quality warnings were recorded."])
        self._render_section_separator(lines)

        lines.append("## Synthesis Limits")
        limits = payload.get("synthesis_limits", []) or []
        if limits:
            lines.extend([""] + [f"- {str(item).strip()}" for item in limits])
        else:
            lines.extend(["", "- No additional synthesis limits were recorded."])

        if include_evidence_ids:
            self._render_section_separator(lines)
            lines.append("## Evidence References")
            unique_ids = _unique_evidence_ids(payload)
            if unique_ids:
                lines.extend([""] + [f"- {evidence_id}" for evidence_id in unique_ids])
            else:
                lines.extend(["", "- No evidence IDs were recorded."])

        lines.append("")
        return "\n".join(lines)

    def _render_v2(self, payload: Dict[str, Any], *, include_evidence_ids: bool) -> str:
        company_name = str(payload.get("company_slug") or payload.get("company") or self.company).title()
        lines: List[str] = [
            f"# Investment Committee Brief — {company_name}",
            "",
            "## Committee View",
            _ensure_sentence(payload.get("committee_view")) or "The committee view is still being formed.",
            "",
            f"**Latest Period:** {str(payload.get('latest_period') or '').strip()}",
            "",
            f"**Direction:** {str(payload.get('committee_direction') or 'unclear').strip()}",
            "",
            f"**Consensus Strength:** {str(payload.get('consensus_strength') or 'insufficient').strip()}",
            "",
            "## Bottom Line",
            _truncate_words(payload.get("bottom_line"), 140),
        ]

        lines.extend(["", "## What Changed"])
        what_changed = payload.get("what_changed") or []
        if what_changed:
            for item in what_changed[:4]:
                if not isinstance(item, dict):
                    continue
                period = str(item.get("period") or "").strip()
                previous_state = _ensure_sentence(item.get("previous_state"))
                current_state = _ensure_sentence(item.get("current_state"))
                why_it_matters = _ensure_sentence(item.get("why_it_matters"))
                bullet = f"- {period}: {previous_state or 'Earlier evidence was not explicit.'} → {current_state or 'Later evidence is still being read.'}"
                if why_it_matters:
                    bullet += f" Why it matters: {why_it_matters}"
                lines.append(bullet)
        else:
            lines.append("- No clear turning point was preserved in the current synthesis.")

        lines.extend(["", "## What Strengthened"])
        what_strengthened = payload.get("what_strengthened") or []
        if what_strengthened:
            for item in what_strengthened[:4]:
                if not isinstance(item, dict):
                    continue
                conclusion = _ensure_sentence(item.get("conclusion"))
                why_it_matters = _ensure_sentence(item.get("why_it_matters"))
                confidence = str(item.get("evidence_confidence") or "medium").strip() or "medium"
                lines.append(
                    f"- {conclusion or 'A positive signal was preserved.'} Why it matters: {why_it_matters or 'This matters for conviction.'} Confidence: {confidence}."
                )
        else:
            lines.append("- No strengthening signal was preserved in the current synthesis.")

        lines.extend(["", "## What Weakened"])
        what_weakened = payload.get("what_weakened") or []
        if what_weakened:
            for item in what_weakened[:4]:
                if not isinstance(item, dict):
                    continue
                conclusion = _ensure_sentence(item.get("conclusion"))
                why_it_matters = _ensure_sentence(item.get("why_it_matters"))
                confidence = str(item.get("evidence_confidence") or "medium").strip() or "medium"
                lines.append(
                    f"- {conclusion or 'A cautionary signal was preserved.'} Why it matters: {why_it_matters or 'This limits conviction.'} Confidence: {confidence}."
                )
        else:
            lines.append("- No weakening signal was preserved in the current synthesis.")

        lines.extend(["", "## Major Disagreement"])
        major_disagreement = payload.get("major_disagreement") or []
        if major_disagreement:
            for item in major_disagreement[:2]:
                if not isinstance(item, dict):
                    continue
                lines.extend(
                    [
                        "",
                        f"### {str(item.get('topic') or '').strip() or 'Disagreement'}",
                        f"**Side A:** {str(item.get('side_a') or '').strip() or 'One side is more constructive.'}",
                        f"**Side B:** {str(item.get('side_b') or '').strip() or 'The other side is more cautious.'}",
                        f"**Why it exists:** {str(item.get('why_the_disagreement_exists') or '').strip() or 'The same evidence is being weighted differently.'}",
                        f"**Evidence that could resolve it:** {str(item.get('evidence_that_could_resolve_it') or '').strip() or 'Later evidence would need to be clearer.'}",
                        f"**Type:** {str(item.get('disagreement_type') or 'unclear').strip()}",
                    ]
                )
        else:
            lines.append("- No material disagreement was preserved in the current synthesis.")

        def _render_view(title: str, view: Dict[str, Any]) -> None:
            lines.extend(["", f"## {title}"])
            lines.extend(
                [
                    "",
                    f"**Assessment:** {str(view.get('assessment') or '').strip()}",
                    "",
                    f"**Direction:** {str(view.get('direction') or 'unclear').strip()}",
                    "",
                    f"**Strongest Evidence:** {str(view.get('strongest_evidence') or '').strip()}",
                    "",
                    f"**Main Concern:** {str(view.get('main_concern') or '').strip()}",
                    "",
                    f"**Unresolved Issue:** {str(view.get('unresolved_issue') or '').strip()}",
                ]
            )

        _render_view("Financial View", payload.get("financial_view") or {})
        _render_view("Management View", payload.get("management_view") or {})
        _render_view("Capital Allocation View", payload.get("capital_allocation_view") or {})
        _render_view("Risk View", payload.get("risk_view") or {})

        lines.extend(["", "## What Remains Unproven"])
        unproven = payload.get("what_remains_unproven") or []
        if unproven:
            for item in unproven[:5]:
                if not isinstance(item, dict):
                    continue
                item_text = str(item.get("item") or "").strip()
                why_it_matters = _ensure_sentence(item.get("why_it_matters"))
                evidence_needed = _ensure_sentence(item.get("evidence_needed"))
                lines.append(
                    f"- {item_text or 'An unresolved item remains.'}: {why_it_matters or 'This is decision-relevant.'} Evidence needed: {evidence_needed or 'Later evidence is needed.'}"
                )
        else:
            lines.append("- No decision-relevant unknowns were preserved.")

        lines.extend(["", "## What Would Change the View"])
        for item in (payload.get("what_would_change_the_view") or [])[:5]:
            sentence = _ensure_sentence(item)
            if sentence:
                lines.append(f"- {sentence}")
        if not (payload.get("what_would_change_the_view") or []):
            lines.append("- Later evidence would need to materially resolve the open questions.")

        lines.extend(["", "## Top Questions to Investigate"])
        questions = payload.get("top_questions_to_investigate") or []
        if questions:
            for index, item in enumerate(questions[:5], start=1):
                if not isinstance(item, dict):
                    continue
                rank = str(item.get("rank") or "").strip() or str(index)
                question = _ensure_sentence(item.get("question"))
                why_it_matters = _ensure_sentence(item.get("why_it_matters"))
                lines.append(f"{rank}. {question or 'What is the next important question?'}")
                if why_it_matters:
                    lines.append(f"   - Why it matters: {why_it_matters}")
        else:
            lines.append("1. What evidence would most change the current view?")

        lines.extend(["", "## Evidence Confidence"])
        evidence_confidence = payload.get("evidence_confidence") or {}
        lines.extend(
            [
                "",
                f"**Level:** {str(evidence_confidence.get('level') or 'medium').strip()}",
                "",
                f"**Basis:** {', '.join(_dedupe_clean_list(evidence_confidence.get('basis') or [])) or 'The committee synthesis preserves progression, disagreements, and the latest evidence.'}",
                "",
                f"**Main Limitation:** {str(evidence_confidence.get('main_limitation') or 'Some evidence remains incomplete.').strip()}",
            ]
        )

        if include_evidence_ids:
            self._render_section_separator(lines)
            lines.append("## Evidence References")
            unique_ids = _unique_evidence_ids(payload)
            if unique_ids:
                lines.extend([""] + [f"- {evidence_id}" for evidence_id in unique_ids])
            else:
                lines.extend(["", "- No evidence IDs were recorded."])

        lines.append("")
        return "\n".join(lines)

    def build(self, *, include_evidence_ids: bool = False) -> Dict[str, Path]:
        payload = self._load_committee_synthesis()
        markdown = self._render(payload, include_evidence_ids=include_evidence_ids)
        return {
            "committee_brief.md": _write_text(self.output_path, markdown),
        }
