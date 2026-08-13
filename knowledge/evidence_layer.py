from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from knowledge.company_memory.guardrails import (
    assess_progression_materiality,
    classify_business_relevance,
    normalize_period_label,
    resolve_period_status,
    semantic_validation,
)


_YEAR_RE = re.compile(r"\b(?:fy)?20\d{2}\b", re.IGNORECASE)
_FY_YEAR_RE = re.compile(r"\bfy(?P<year>\d{2,4})\b", re.IGNORECASE)
_DATE_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,-]+\d{4}\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")
_PERCENT_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\s?%")
_CURRENCY_RE = re.compile(r"(?:₹|rs\.?|inr|\$|usd|eur)\s?\d", re.IGNORECASE)
_ACTOR_TERMS = {
    "company": ("the company", "company", "we ", "our ", "board", "management"),
    "government": ("government", "ministry", "policy", "scheme", "regulation", "authority"),
    "customer": ("customer", "client", "buyer", "subscriber", "merchant"),
    "industry": ("industry", "market", "sector", "economy", "macro", "demand environment"),
    "auditor": ("auditor", "audit", "reasonable assurance", "financial statements", "annexure"),
}
_DIRECT_ACTION_TERMS = (
    "commissioned",
    "launched",
    "signed",
    "approved",
    "paid",
    "declared",
    "acquired",
    "invested",
    "expanded",
    "raised",
    "implemented",
    "deployed",
    "established",
)
_FORWARD_ACTION_TERMS = (
    "will",
    "plans to",
    "expects to",
    "intends to",
    "aims to",
    "targets",
    "roadmap",
)
_MACRO_TERMS = (
    "macroeconomic",
    "global economy",
    "industry outlook",
    "policy support",
    "sector outlook",
    "macro environment",
)
_BOILERPLATE_TERMS = (
    "table of contents",
    "forward looking statement",
    "corporate governance report",
    "director profile",
    "notice of annual general meeting",
)


def _financial_year_value(value: Any) -> int | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text.startswith("fy") and text[2:].isdigit():
        return 2000 + int(text[2:])
    if text.isdigit() and len(text) == 4:
        return int(text)
    return None


def _period_year_values(text: str) -> List[int]:
    years: List[int] = []
    for match in _FY_YEAR_RE.finditer(text):
        raw = match.group("year")
        if len(raw) == 4:
            years.append(int(raw))
        elif len(raw) == 2 and raw.isdigit():
            years.append(2000 + int(raw))
    for match in _YEAR_RE.finditer(text):
        raw = match.group(0).lower()
        if raw.startswith("fy"):
            digits = raw[2:]
            if digits.isdigit():
                years.append(2000 + int(digits))
        elif raw.isdigit():
            years.append(int(raw))
    return sorted(set(years))


@dataclass(frozen=True)
class ModuleProfile:
    name: str
    value_keys: Tuple[str, ...]
    required_fields: Tuple[str, ...]
    positive_patterns: Tuple[str, ...] = ()
    negative_patterns: Tuple[str, ...] = ()
    max_chunks: int = 8
    max_chars_per_chunk: int = 2400
    max_total_chars: int = 12000
    relevance_threshold: int = 3


MODULE_PROFILES: Dict[str, ModuleProfile] = {
    "projects": ModuleProfile(
        name="projects",
        value_keys=("project_name", "value"),
        required_fields=("project_name", "description", "status"),
        max_chunks=6,
    ),
    "promises": ModuleProfile(
        name="promises",
        value_keys=("promise", "value"),
        required_fields=("promise", "category"),
        max_chunks=6,
    ),
    "risks": ModuleProfile(
        name="risks",
        value_keys=("risk", "value"),
        required_fields=("risk", "category", "severity"),
        max_chunks=8,
    ),
    "capacity_expansions": ModuleProfile(
        name="capacity_expansions",
        value_keys=("capacity_type", "value"),
        required_fields=("capacity_type", "status"),
        max_chunks=6,
    ),
    "capital_allocations": ModuleProfile(
        name="capital_allocations",
        value_keys=("action", "value"),
        required_fields=("action", "category"),
        max_chunks=8,
    ),
    "initiatives": ModuleProfile(
        name="initiatives",
        value_keys=("initiative", "value"),
        required_fields=("initiative", "category", "status"),
        max_chunks=6,
    ),
    "commentary": ModuleProfile(
        name="commentary",
        value_keys=("commentary", "theme", "value"),
        required_fields=("context_type", "agency"),
        max_chunks=6,
    ),
}

MODULE_FILE_MAP = {
    "projects": {
        "discovery": "project_discovery_results.json",
        "extracted": "extracted_projects.json",
        "cleaned": "clean_projects.json",
    },
    "promises": {
        "discovery": "promise_discovery_results.json",
        "extracted": "extracted_promises.json",
        "cleaned": "clean_promises.json",
    },
    "risks": {
        "discovery": "risk_discovery_results.json",
        "extracted": "extracted_risks.json",
        "cleaned": "clean_risks.json",
    },
    "capacity_expansions": {
        "discovery": "capacity_discovery_results.json",
        "extracted": "extracted_capacity.json",
        "cleaned": "clean_capacity.json",
    },
    "capital_allocations": {
        "discovery": "capital_allocation_discovery_results.json",
        "extracted": "extracted_capital_allocation.json",
        "cleaned": "clean_capital_allocation.json",
    },
    "initiatives": {
        "discovery": "initiative_discovery_results.json",
        "extracted": "extracted_initiatives.json",
        "cleaned": "clean_initiatives.json",
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_text(text: Any) -> str:
    if text is None:
        return ""
    if isinstance(text, (dict, list)):
        text = json.dumps(text, ensure_ascii=False)
    return str(text).strip()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "item"


def _parse_bool(value: Any) -> bool:
    return bool(value)


def _dedupe_preserve(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def get_module_profile(module_name: str) -> ModuleProfile:
    profile = MODULE_PROFILES.get(module_name)
    if profile is None:
        return ModuleProfile(
            name=module_name,
            value_keys=("value",),
            required_fields=("value",),
            relevance_threshold=0,
        )
    return profile


def score_discovery_chunk(
    chunk: Dict[str, Any],
    *,
    module_name: str,
    positive_patterns: Optional[Sequence[str]] = None,
    negative_patterns: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    text = _normalize_text(chunk.get("chunk"))
    normalized = text.lower()
    reasons: List[str] = []
    warnings: List[str] = []
    score = 0

    actor_type = classify_actor_type(text)
    if actor_type == "company":
        score += 4
        reasons.append("company_actor")
    elif actor_type in {"management", "customer"}:
        score += 3
        reasons.append("business_actor")
    elif actor_type in {"government", "industry"}:
        score -= 1
        warnings.append("external_context")
    elif actor_type == "auditor":
        score -= 4
        warnings.append("auditor_boilerplate")

    if any(term in normalized for term in _DIRECT_ACTION_TERMS):
        score += 3
        reasons.append("direct_action")
    if any(term in normalized for term in _FORWARD_ACTION_TERMS):
        score += 2
        reasons.append("forward_commitment")
    if _NUMBER_RE.search(normalized):
        score += 1
        reasons.append("numeric_signal")
    if _PERCENT_RE.search(normalized) or _CURRENCY_RE.search(normalized):
        score += 1
        reasons.append("financial_signal")
    if _YEAR_RE.search(normalized) or _DATE_RE.search(normalized):
        score += 1
        reasons.append("time_specific")

    for pattern in positive_patterns or ():
        if pattern and pattern.lower() in normalized:
            score += 2
            reasons.append(f"positive:{pattern}")
    for pattern in negative_patterns or ():
        if pattern and pattern.lower() in normalized:
            score -= 2
            warnings.append(f"negative:{pattern}")

    if any(term in normalized for term in _MACRO_TERMS):
        score -= 2
        warnings.append("macro_context")
    if any(term in normalized for term in _BOILERPLATE_TERMS):
        score -= 3
        warnings.append("boilerplate")

    score += _module_specific_bonus(module_name, normalized, reasons)
    if "macro_context" in warnings and "company_actor" not in reasons and "direct_action" not in reasons:
        score -= 2

    return {
        "score": score,
        "actor_type": actor_type,
        "reasons": _dedupe_preserve(reasons),
        "warnings": _dedupe_preserve(warnings),
        "page": chunk.get("page"),
    }


def _module_specific_bonus(module_name: str, text: str, reasons: List[str]) -> int:
    bonuses = {
        "projects": ("facility", "plant", "project", "expansion", "construction", "commissioned"),
        "promises": ("target", "plan", "will", "timeline", "commission", "aims"),
        "risks": ("risk", "challenge", "dependence", "concentration", "competition", "litigation"),
        "capacity_expansions": ("capacity", "throughput", "production", "commercial production", "line"),
        "capital_allocations": ("capex", "dividend", "loan", "equity", "investment", "borrowings"),
        "initiatives": ("automation", "digital", "initiative", "implemented", "deployed", "research"),
        "commentary": ("strategy", "outlook", "competitive", "growth", "innovation"),
    }
    score = 0
    for token in bonuses.get(module_name, ()):
        if token in text:
            score += 1
            reasons.append(f"module_signal:{token}")
    return score


def select_discovery_chunks(
    chunks: Sequence[Dict[str, Any]],
    *,
    module_name: str,
    positive_patterns: Optional[Sequence[str]] = None,
    negative_patterns: Optional[Sequence[str]] = None,
    max_chunks: Optional[int] = None,
    max_chars_per_chunk: Optional[int] = None,
    max_total_chars: Optional[int] = None,
    relevance_threshold: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    profile = get_module_profile(module_name)
    selected: List[Dict[str, Any]] = []
    seen_chunk_text = set()
    scored_entries = []

    max_chunks = max_chunks or profile.max_chunks
    max_chars_per_chunk = max_chars_per_chunk or profile.max_chars_per_chunk
    max_total_chars = max_total_chars or profile.max_total_chars
    relevance_threshold = relevance_threshold if relevance_threshold is not None else profile.relevance_threshold

    for index, chunk in enumerate(chunks, start=1):
        score_info = score_discovery_chunk(
            chunk,
            module_name=module_name,
            positive_patterns=positive_patterns,
            negative_patterns=negative_patterns,
        )
        scored_entries.append((index, chunk, score_info))

    scored_entries.sort(
        key=lambda entry: (
            entry[2]["score"],
            0 if entry[2]["actor_type"] == "company" else 1,
            -(entry[1].get("page") or 0),
        ),
        reverse=True,
    )

    total_chars = 0
    rejected = 0
    selection_reasons: List[Dict[str, Any]] = []
    for rank, (original_index, chunk, score_info) in enumerate(scored_entries, start=1):
        chunk_text = _normalize_text(chunk.get("chunk"))
        dedupe_key = re.sub(r"\s+", " ", chunk_text.lower())
        if not chunk_text:
            rejected += 1
            selection_reasons.append({"chunk_index": original_index, "decision": "rejected", "reason": "empty_chunk"})
            continue
        if dedupe_key in seen_chunk_text:
            rejected += 1
            selection_reasons.append({"chunk_index": original_index, "decision": "rejected", "reason": "duplicate_chunk"})
            continue
        if score_info["score"] < relevance_threshold:
            rejected += 1
            selection_reasons.append(
                {
                    "chunk_index": original_index,
                    "decision": "rejected",
                    "reason": "below_relevance_threshold",
                    "score": score_info["score"],
                }
            )
            continue

        trimmed_text = chunk_text[:max_chars_per_chunk].strip()
        projected_chars = total_chars + len(trimmed_text)
        if len(selected) >= max_chunks or projected_chars > max_total_chars:
            rejected += 1
            selection_reasons.append(
                {
                    "chunk_index": original_index,
                    "decision": "rejected",
                    "reason": "budget_limit",
                    "score": score_info["score"],
                }
            )
            continue

        selected_item = deepcopy(chunk)
        selected_item["chunk"] = trimmed_text
        selected_item["selection_metadata"] = {
            "score": score_info["score"],
            "reasons": score_info["reasons"],
            "warnings": score_info["warnings"],
            "actor_type": score_info["actor_type"],
            "rank": rank,
            "original_index": original_index,
        }
        selected.append(selected_item)
        seen_chunk_text.add(dedupe_key)
        total_chars = projected_chars
        selection_reasons.append(
            {
                "chunk_index": original_index,
                "decision": "selected",
                "score": score_info["score"],
                "reasons": score_info["reasons"],
            }
        )

    metadata = {
        "module": module_name,
        "chunks_seen": len(chunks),
        "chunks_selected": len(selected),
        "chunks_rejected": rejected,
        "selection_reasons": selection_reasons[:50],
        "budget_applied": True,
        "estimated_tokens": max(1, total_chars // 4),
        "max_chunks": max_chunks,
        "max_chars_per_chunk": max_chars_per_chunk,
        "max_total_chars": max_total_chars,
        "relevance_threshold": relevance_threshold,
        "generated_at": _now_iso(),
    }
    return selected, metadata


def classify_actor_type(text: str) -> str:
    normalized = _normalize_text(text).lower()
    if not normalized:
        return "unknown"
    for actor_type, patterns in _ACTOR_TERMS.items():
        if any(pattern in normalized for pattern in patterns):
            if actor_type == "company" and "management" in normalized:
                return "management"
            return actor_type
    return "unknown"


def derive_time_specificity(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return "unclear"
    if _DATE_RE.search(normalized) or re.search(r"\bq[1-4]\b", normalized, re.IGNORECASE):
        return "dated"
    if _YEAR_RE.search(normalized) or "year ended" in normalized.lower() or "during the year" in normalized.lower():
        return "period_specific"
    if any(token in normalized.lower() for token in ("ongoing", "future", "long term", "near term")):
        return "undated"
    return "unclear"


def derive_source_proximity(text: str, *, actor_type: str) -> str:
    normalized = _normalize_text(text).lower()
    if actor_type == "auditor":
        return "note"
    if any(token in normalized for token in ("table", "₹", "lakhs", "crore", "%")):
        return "table"
    if actor_type in {"government", "industry"}:
        return "macro_context"
    if actor_type in {"company", "management", "customer"}:
        return "direct_statement"
    if normalized:
        return "derived"
    return "uncertain"


def derive_company_specificity(text: str, *, actor_type: str) -> str:
    normalized = _normalize_text(text).lower()
    if actor_type in {"company", "management"} and any(token in normalized for token in _DIRECT_ACTION_TERMS + _FORWARD_ACTION_TERMS):
        return "high"
    if actor_type in {"company", "management", "customer"}:
        return "medium"
    if actor_type in {"government", "industry", "auditor"}:
        return "low"
    return "low"


def derive_actionability(text: str) -> str:
    normalized = _normalize_text(text).lower()
    if any(token in normalized for token in _DIRECT_ACTION_TERMS):
        return "high"
    if any(token in normalized for token in _FORWARD_ACTION_TERMS):
        return "medium"
    if any(token in normalized for token in ("risk", "challenge", "dependence", "uncertain")):
        return "medium"
    return "low"


def derive_investor_relevance(text: str, module_name: str) -> str:
    normalized = _normalize_text(text).lower()
    if module_name == "capital_allocations" and any(token in normalized for token in ("dividend", "loan", "equity", "capex", "investment")):
        return "high"
    if module_name in {"projects", "promises", "risks", "capacity_expansions"} and (
        _NUMBER_RE.search(normalized)
        or any(token in normalized for token in ("customer", "capacity", "facility", "competition", "cash"))
    ):
        return "high"
    if module_name == "initiatives" and any(token in normalized for token in ("automation", "digital", "efficiency", "product")):
        return "medium"
    if module_name == "commentary":
        return "medium" if any(token in normalized for token in ("strategy", "growth", "competitive")) else "low"
    return "medium" if normalized else "low"


def derive_quality_warnings(text: str, *, actor_type: str, module_name: str) -> List[str]:
    normalized = _normalize_text(text).lower()
    warnings: List[str] = []
    if actor_type in {"government", "industry"}:
        warnings.append("external_context_requires_routing")
    if actor_type == "auditor":
        warnings.append("auditor_context")
    if any(token in normalized for token in _MACRO_TERMS):
        warnings.append("macro_context")
    if not _NUMBER_RE.search(normalized) and module_name in {"capital_allocations", "capacity_expansions", "projects"}:
        warnings.append("missing_numeric_support")
    if derive_time_specificity(text) in {"undated", "unclear"}:
        warnings.append("weak_time_specificity")
    return _dedupe_preserve(warnings)


def derive_confidence_from_quality(
    *,
    company_specificity: str,
    actionability: str,
    investor_relevance: str,
    actor_type: str,
    numeric_support: bool,
) -> str:
    score = 0
    score += {"high": 3, "medium": 2, "low": 1}.get(company_specificity, 1)
    score += {"high": 3, "medium": 2, "low": 1}.get(actionability, 1)
    score += {"high": 3, "medium": 2, "low": 1}.get(investor_relevance, 1)
    if actor_type in {"company", "management", "customer"}:
        score += 2
    if numeric_support:
        score += 1
    if score >= 9:
        return "high"
    if score >= 6:
        return "medium"
    return "low"


def build_evidence_quality(item: Dict[str, Any], *, module_name: str) -> Dict[str, Any]:
    text_parts = []
    period_text_parts = []
    for key, value in item.items():
        if isinstance(value, str) and key not in {"source_chunk", "source_artifact", "source_year"}:
            text_parts.append(value)
    for key, value in item.items():
        if isinstance(value, str) and key not in {"source_chunk", "source_artifact", "source_year"}:
            if module_name in {"capital_allocations", "risks", "initiatives", "capacity_expansions"} and key == "year" and item.get("source_year"):
                continue
            period_text_parts.append(value)
    text = " ".join(text_parts)
    period_text = " ".join(period_text_parts)
    actor_type = classify_actor_type(text)
    company_specificity = derive_company_specificity(text, actor_type=actor_type)
    actionability = derive_actionability(text)
    investor_relevance = derive_investor_relevance(text, module_name)
    numeric_support = bool(_NUMBER_RE.search(text) or _PERCENT_RE.search(text) or _CURRENCY_RE.search(text))
    source_proximity = derive_source_proximity(text, actor_type=actor_type)
    time_specificity = derive_time_specificity(text)
    business_relevance = classify_business_relevance(text, module_name=module_name, actor_type=actor_type)
    source_period = item.get("source_year") or item.get("year") or ""
    explicit_year = item.get("year") or item.get("time_reference") or item.get("source_year") or ""
    target_period = ""
    temporal_role = ""
    if module_name == "capacity_expansions":
        if item.get("current_capacity") and item.get("target_capacity"):
            temporal_role = "current_target"
        if item.get("year"):
            target_period = item.get("year") or ""
    source_value = _financial_year_value(source_period)
    period_years = _period_year_values(period_text)
    project_cues = ("as at", "capitalised during the year", "capitalized during the year", "moved out of cwip", "completed", "commissioned", "in progress", "closing as at")
    if module_name == "projects" and source_value is not None and len(period_years) == 2 and source_value in period_years and max(period_years) == source_value + 1 and any(cue in period_text.lower() for cue in project_cues):
        target_period = str(max(period_years))
    if module_name == "risks" and item.get("source_year"):
        risk_cues = ("go-live", "deadline", "renewal", "expiry", "expires", "meeting the fy", "compliance date")
        future_years = [year for year in period_years if source_value is not None and year > source_value]
        if future_years and any(cue in period_text.lower() for cue in risk_cues):
            explicit_year = source_period
            target_period = str(max(future_years))
    if module_name in {"promises", "initiatives"} and item.get("year"):
        target_period = item.get("year") or ""
    period_resolution = resolve_period_status(
        source_year=source_period,
        text=period_text,
        explicit_year=explicit_year,
        module_name=module_name,
        target_period=target_period,
        temporal_role=temporal_role,
    )
    progression_materiality = assess_progression_materiality(
        text,
        module_name=module_name,
        relevance_status=str(business_relevance.get("status") or "ambiguous"),
        period_status=str(period_resolution.get("status") or "AMBIGUOUS"),
        evidence_quality={
            "company_specificity": company_specificity,
            "actionability": actionability,
            "investor_relevance": investor_relevance,
            "numeric_support": numeric_support,
        },
        status_text=str(item.get("status") or item.get("time_reference") or ""),
    )
    semantic_flags = semantic_validation(
        module_name=module_name,
        relevance=business_relevance,
        period=period_resolution,
        materiality=progression_materiality,
    )
    confidence = derive_confidence_from_quality(
        company_specificity=company_specificity,
        actionability=actionability,
        investor_relevance=investor_relevance,
        actor_type=actor_type,
        numeric_support=numeric_support,
    )
    warnings = derive_quality_warnings(text, actor_type=actor_type, module_name=module_name)
    warnings.extend(business_relevance.get("limitations") or [])
    warnings.extend(period_resolution.get("limitations") or [])
    warnings.extend(progression_materiality.get("limitations") or [])
    warnings.extend(semantic_flags.get("warnings") or [])
    return {
        "company_specificity": company_specificity,
        "actionability": actionability,
        "investor_relevance": investor_relevance,
        "source_proximity": source_proximity,
        "actor_type": actor_type,
        "time_specificity": time_specificity,
        "numeric_support": numeric_support,
        "confidence": confidence,
        "warnings": warnings,
        "business_relevance": business_relevance,
        "period_resolution": period_resolution,
        "progression_materiality": progression_materiality,
        "semantic_validation": semantic_flags,
    }


def infer_generic_fields(item: Dict[str, Any], *, module_name: str) -> Dict[str, Any]:
    profile = get_module_profile(module_name)
    inferred = deepcopy(item)
    if not inferred.get("value"):
        for key in profile.value_keys:
            candidate = _normalize_text(inferred.get(key))
            if candidate:
                inferred["value"] = candidate
                break
    if "category" not in inferred or inferred.get("category") is None:
        inferred["category"] = ""
    if "status" not in inferred or inferred.get("status") is None:
        inferred["status"] = ""
    if "actor" not in inferred or inferred.get("actor") is None:
        inferred["actor"] = classify_actor_type(" ".join(_normalize_text(value) for value in inferred.values() if isinstance(value, str)))
    if "time_reference" not in inferred or inferred.get("time_reference") is None:
        inferred["time_reference"] = derive_time_specificity(" ".join(_normalize_text(value) for value in inferred.values() if isinstance(value, str)))
    if "year" not in inferred or inferred.get("year") is None:
        inferred["year"] = _extract_year(" ".join(_normalize_text(value) for value in inferred.values() if isinstance(value, str)))
    if "amount" not in inferred:
        inferred["amount"] = ""
    if "currency" not in inferred:
        inferred["currency"] = _extract_currency(inferred.get("amount", ""))
    if "uncertainty_reason" not in inferred:
        inferred["uncertainty_reason"] = ""
    return inferred


def _extract_year(text: str) -> str:
    match = _YEAR_RE.search(_normalize_text(text))
    return match.group(0).upper() if match else ""


def _extract_currency(amount: Any) -> str:
    normalized = _normalize_text(amount)
    if "₹" in normalized or "inr" in normalized.lower() or "rs" in normalized.lower():
        return "INR"
    if "$" in normalized or "usd" in normalized.lower():
        return "USD"
    if "eur" in normalized.lower():
        return "EUR"
    return ""


def ensure_evidence_ids(item: Dict[str, Any], *, module_name: str, item_index: int) -> List[str]:
    existing = _dedupe_preserve(item.get("evidence_ids") or [])
    if existing:
        return existing
    page = item.get("page")
    suffix = f"p{page}" if page not in (None, "") else "pna"
    return [f"ev_{module_name}_{suffix}_{item_index:05d}"]


def enrich_extracted_item(
    item: Dict[str, Any],
    *,
    module_name: str,
    item_index: int,
    selection_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    enriched = infer_generic_fields(item, module_name=module_name)
    enriched["item_id"] = enriched.get("item_id") or f"{_slugify(module_name)}_{item_index:05d}"
    enriched["evidence_ids"] = ensure_evidence_ids(enriched, module_name=module_name, item_index=item_index)
    if selection_metadata is not None:
        enriched["selection_metadata"] = deepcopy(selection_metadata)
    enriched["evidence_quality"] = build_evidence_quality(enriched, module_name=module_name)
    if not enriched.get("confidence"):
        enriched["confidence"] = enriched["evidence_quality"]["confidence"]
    if not enriched.get("uncertainty_reason") and enriched["evidence_quality"]["warnings"]:
        enriched["uncertainty_reason"] = "; ".join(enriched["evidence_quality"]["warnings"])
    return enriched


def finalize_cleaned_item(
    item: Dict[str, Any],
    *,
    module_name: str,
    item_index: int,
) -> Dict[str, Any]:
    finalized = infer_generic_fields(item, module_name=module_name)
    finalized["item_id"] = finalized.get("item_id") or f"{_slugify(module_name)}_{item_index:05d}"
    finalized["evidence_ids"] = ensure_evidence_ids(finalized, module_name=module_name, item_index=item_index)
    finalized["evidence_quality"] = build_evidence_quality(finalized, module_name=module_name)
    finalized["confidence"] = finalized.get("confidence") or finalized["evidence_quality"]["confidence"]
    if not finalized.get("uncertainty_reason") and finalized["evidence_quality"]["warnings"]:
        finalized["uncertainty_reason"] = "; ".join(finalized["evidence_quality"]["warnings"])
    finalized.pop("source_chunk", None)
    return finalized


def validate_cleaned_item(item: Dict[str, Any], *, module_name: str) -> Dict[str, List[str]]:
    profile = get_module_profile(module_name)
    errors: List[str] = []
    warnings: List[str] = []

    if item.get("source_chunk"):
        errors.append("source_chunk leakage detected in cleaned output")
    if not isinstance(item.get("evidence_ids"), list) or not item.get("evidence_ids"):
        errors.append("missing evidence_ids")
    if not _normalize_text(item.get("confidence")):
        errors.append("missing confidence")
    if not _normalize_text(item.get("value")):
        errors.append("missing value")
    for field in profile.required_fields:
        if field in {"status"} and module_name in {"promises", "capital_allocations"}:
            continue
        if not _normalize_text(item.get(field)):
            errors.append(f"missing {field}")

    quality = item.get("evidence_quality") or {}
    if not isinstance(quality, dict):
        errors.append("missing evidence_quality")
        quality = {}
    if quality.get("actor_type") in {"government", "industry", "auditor"} and item.get("actor") == "company":
        errors.append("external actor routed as company action without reason")
    if quality.get("company_specificity") == "low":
        warnings.append("low company_specificity")
    if quality.get("actor_type") in {"unknown", ""}:
        warnings.append("uncertain actor")
    if module_name in {"capital_allocations", "projects", "promises", "capacity_expansions"} and not _normalize_text(item.get("year")):
        warnings.append("no date or year")
    if module_name == "capital_allocations" and not _normalize_text(item.get("amount")):
        warnings.append("no amount for capital item")
    if quality.get("investor_relevance") == "low":
        warnings.append("weak investor relevance")
    if quality.get("business_relevance", {}).get("quarantine"):
        errors.append("business relevance quarantined")
    if str((quality.get("period_resolution") or {}).get("status") or "").upper() in {"INVALID", "AMBIGUOUS", "OUTSIDE_ANALYSIS_WINDOW"}:
        errors.append("invalid or unsupported period resolution")
    if not (quality.get("progression_materiality") or {}).get("should_promote", True) and module_name in {"capital_allocations", "capacity_expansions", "projects", "commentary"}:
        warnings.append("low progression materiality")
    return {"errors": _dedupe_preserve(errors), "warnings": _dedupe_preserve(warnings)}


def quality_bucket_counts(items: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for item in items:
        quality = item.get("evidence_quality") or {}
        bucket = quality.get("confidence") or item.get("confidence") or "low"
        if bucket not in counts:
            bucket = "low"
        counts[bucket] += 1
    return counts


def write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def build_evidence_layer_summary(context: Any) -> Dict[str, Any]:
    modules = []
    llm_calls = 0
    prompt_tokens = 0
    overall_status = "pass"
    top_noise_sources: List[str] = []

    for module_name, files in MODULE_FILE_MAP.items():
        discovered = _load_list(context.raw_dir / files["discovery"])
        extracted = _load_list(context.extracted_dir / files["extracted"])
        cleaned = _load_module_items(context.extracted_dir / files["cleaned"])
        selection_manifest = _load_json(context.extracted_dir / f"{Path(files['extracted']).stem}_selection_metadata.json")
        llm_manifest = _load_json(context.extracted_dir / f"{Path(files['extracted']).stem}_llm_call_manifest.json")
        selected_for_llm = 0
        warnings: List[str] = []
        failures: List[str] = []
        if isinstance(selection_manifest, dict):
            selected_for_llm = int(selection_manifest.get("chunks_selected") or 0)
            for reason in selection_manifest.get("selection_reasons", []):
                if isinstance(reason, dict) and reason.get("decision") == "rejected":
                    raw_reason = _normalize_text(reason.get("reason"))
                    if raw_reason and raw_reason not in top_noise_sources:
                        top_noise_sources.append(raw_reason)
        if isinstance(llm_manifest, dict):
            entries = llm_manifest.get("entries") or []
            llm_calls += len(entries)
            for entry in entries:
                prompt_tokens += int(entry.get("estimated_prompt_tokens") or 0)

        counts = quality_bucket_counts(cleaned)
        if not cleaned:
            overall_status = "warning"
            warnings.append("no cleaned output")
        if selected_for_llm == 0 and discovered:
            overall_status = "warning"
            warnings.append("no discovery chunks selected")
        for item in cleaned:
            validation = validate_cleaned_item(item, module_name=module_name)
            if validation["errors"]:
                overall_status = "fail"
                failures.extend(validation["errors"])
            warnings.extend(validation["warnings"])

        modules.append(
            {
                "module": module_name,
                "discovered": len(discovered),
                "selected_for_llm": selected_for_llm,
                "extracted": len(extracted),
                "cleaned": len(cleaned),
                "high_quality": counts["high"],
                "medium_quality": counts["medium"],
                "low_quality": counts["low"],
                "warnings": _dedupe_preserve(warnings),
                "failures": _dedupe_preserve(failures),
            }
        )

    summary = {
        "company": context.company,
        "year": context.year,
        "status": overall_status,
        "modules": modules,
        "cost_estimate": {
            "llm_calls": llm_calls,
            "estimated_prompt_tokens": prompt_tokens,
        },
        "top_noise_sources": top_noise_sources[:10],
        "generated_at": _now_iso(),
    }
    return summary


def write_evidence_layer_summary(context: Any) -> Path:
    summary = build_evidence_layer_summary(context)
    return write_json(context.year_root / "evidence_layer_summary.json", summary)


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_list(path: Path) -> List[Dict[str, Any]]:
    payload = _load_json(path)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _load_module_items(path: Path) -> List[Dict[str, Any]]:
    payload = _load_json(path)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        items: List[Dict[str, Any]] = []
        for value in payload.values():
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
        return items
    return []
