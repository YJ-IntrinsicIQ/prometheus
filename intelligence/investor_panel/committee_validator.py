from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

from .evidence_grounding import normalize_evidence_id
from .forbidden_language import find_forbidden_recommendation_language


EXPECTED_ANALYSTS = ["graham", "buffett", "fisher", "munger", "lynch"]
REQUIRED_ANALYST_FIELDS = {
    "doctrine_id",
    "rating",
    "key_findings",
    "red_flags",
    "open_uncertainties",
    "evidence_ids",
    "historical_context_used",
    "years_considered",
    "evidence_grounding_status",
    "reasoning_limits",
    "user_facing_brief",
    "financial_assessment",
    "financial_sections_consumed",
    "financial_warnings_carried_forward",
    "supporting_pcim_sections",
}
RAW_REQUIRED_TOP_LEVEL_KEYS = {
    "company",
    "analysis_mode",
    "analysts_considered",
    "missing_analysts",
    "excluded_analysts",
    "years_considered",
    "overall_committee_view",
    "financial_committee_view",
    "areas_of_agreement",
    "areas_of_disagreement",
    "strongest_positive_signals",
    "most_important_risks",
    "critical_unknowns",
    "investigation_questions",
    "evidence_ids",
    "evidence_quality_notes",
    "synthesis_limits",
    "generated_at",
}
FINAL_REQUIRED_TOP_LEVEL_KEYS = RAW_REQUIRED_TOP_LEVEL_KEYS | {"evidence_id_normalization"}

FORBIDDEN_INTERNAL_BRIEF_TERMS = {
    "pcim",
    "cim",
    "evidence_id",
    "evidence ids",
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
}

FORBIDDEN_FINAL_COMMITTEE_KEYS = {
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

KNOWN_FINANCIAL_TERM_ALIASES = {
    "revenue": {"revenue", "sales", "topline", "top line"},
    "ebitda": {"ebitda"},
    "ebit": {"ebit"},
    "pat": {"pat", "profit after tax", "net profit"},
    "eps": {"eps", "earnings per share"},
    "book_value_per_share": {"book value per share", "book value"},
    "roe": {"roe", "return on equity"},
    "roce": {"roce", "return on capital employed"},
    "roa": {"roa", "return on assets"},
    "cfo": {"cfo", "operating cash flow", "cash from operations"},
    "fcf": {"fcf", "free cash flow"},
    "cash_conversion": {"cash conversion", "cfo to pat", "fcf to pat"},
    "debt": {"debt", "borrowings", "leverage"},
    "debt_to_equity": {"debt to equity", "net debt to equity"},
    "net_worth": {"net worth", "equity", "book equity"},
    "cash": {"cash", "cash and equivalents", "cash balance"},
    "capex": {"capex", "capital expenditure", "cwip"},
    "receivables": {"receivables", "debtor days", "receivable days"},
    "inventory": {"inventory", "inventory days"},
    "payables": {"payables", "payable days"},
    "working_capital": {"working capital", "cash conversion cycle", "ccc"},
    "share_count": {"share count", "shares outstanding", "weighted average shares", "diluted shares"},
    "dividend": {"dividend", "dividend per share", "payout ratio"},
    "promoter_holding": {"promoter holding", "pledged promoter holding"},
    "institutional_holding": {"fii holding", "dii holding", "mutual fund holding", "institutional holding"},
    "dilution": {"dilution", "qip", "preferential issue", "buyback", "bonus", "split"},
    "ownership": {"ownership", "public float", "shareholding"},
    "margin": {"margin", "ebitda margin", "ebit margin", "opm", "npm"},
    "growth": {"growth", "yoy", "cagr", "book value growth", "eps growth"},
    "interest_coverage": {"interest coverage"},
    "owner_earnings": {"owner earnings", "owner-earnings"},
}

STRICT_FINANCIAL_TERMS = {
    "revenue",
    "ebitda",
    "ebit",
    "pat",
    "eps",
    "book_value_per_share",
    "roe",
    "roce",
    "roa",
    "cfo",
    "fcf",
    "debt",
    "receivables",
    "inventory",
    "payables",
    "interest_coverage",
    "owner_earnings",
}

ALLOWED_COMMITTEE_BASIS = {"consolidated", "standalone", "mixed", "unknown"}
FORBIDDEN_LIST_CONTENT_TERMS = {
    "source_chunk",
    "raw_text",
    "full_text",
    "selected_pcim",
    "prompt",
    "input_pack",
    "token_budget",
    "compacted_sections",
    "grounding_status",
    "schema_warnings",
    "source_artifact",
    "source_artifacts",
}
PCIM_SECTION_NAME_EVIDENCE_IDS = {
    "profitability_inputs",
    "working_capital_inputs",
    "multi_year_inputs",
    "financial_quality_inputs",
    "financial_growth_inputs",
    "management_quality_inputs",
    "financial_driver_inputs",
    "business_understanding",
    "moat_inputs",
    "risk_inputs",
    "evidence_map",
    "uncertainty_missing_data",
    "cash_conversion_inputs",
    "return_on_capital_inputs",
    "balance_sheet_strength_inputs",
    "per_share_inputs",
    "corporate_action_inputs",
    "ownership_inputs",
}

COMMITTEE_FIELD_CONTRACTS = {
    "areas_of_agreement": {"type": "object_list"},
    "areas_of_disagreement": {"type": "object_list"},
    "strongest_positive_signals": {"type": "object_list"},
    "most_important_risks": {"type": "object_list"},
    "investigation_questions": {"type": "object_list"},
    "critical_unknowns": {"type": "object_list"},
    "evidence_quality_notes": {"type": "string_list"},
    "synthesis_limits": {"type": "string_list"},
    "financial_committee_view.financial_consensus": {"type": "string_list"},
    "financial_committee_view.financial_strengths": {"type": "string_list"},
    "financial_committee_view.financial_concerns": {"type": "string_list"},
    "financial_committee_view.financial_disagreements": {"type": "object_list"},
    "financial_committee_view.missing_financial_data": {"type": "string_list"},
    "financial_committee_view.financial_red_flags": {"type": "string_list"},
    "financial_committee_view.financial_interpretation_limits": {"type": "string_list"},
    "financial_committee_view.investor_questions_from_financials": {"type": "string_list"},
}

COMMITTEE_SYNTHESIS_MODES = {"committee_synthesis_v1", "committee_synthesis_v2"}
V2_COMMITTEE_VIEW_VALUES = {"strong", "reasonably_strong", "mixed", "weak", "insufficient_evidence"}
V2_COMMITTEE_DIRECTION_VALUES = {"strengthening", "weakening", "stable", "mixed", "unclear"}
V2_CONSENSUS_STRENGTH_VALUES = {"high", "medium", "low", "fragmented", "insufficient_evidence"}
V2_COMMITTEE_VIEW_ENUM_MAP = {
    "strong": "strong",
    "reasonably strong": "reasonably_strong",
    "reasonably_strong": "reasonably_strong",
    "mixed": "mixed",
    "weak": "weak",
    "insufficient evidence": "insufficient_evidence",
    "insufficient_evidence": "insufficient_evidence",
}
V2_COMMITTEE_DIRECTION_ENUM_MAP = {
    "strengthening": "strengthening",
    "weakening": "weakening",
    "stable": "stable",
    "mixed": "mixed",
    "unclear": "unclear",
}
V2_CONSENSUS_STRENGTH_ENUM_MAP = {
    "high": "high",
    "medium": "medium",
    "low": "low",
    "fragmented": "fragmented",
    "insufficient evidence": "insufficient_evidence",
    "insufficient_evidence": "insufficient_evidence",
}


def _safe_list_dict_to_string(item: Dict[str, Any], field: str) -> str:
    priority_keys = (
        "point",
        "summary",
        "view",
        "finding",
        "concern",
        "risk",
        "consensus",
        "conclusion",
        "question",
        "uncertainty",
        "limitation",
        "text",
        "description",
    )

    def _flatten_scalar(value: Any, depth: int = 0) -> List[str]:
        if depth > 2:
            return []
        if value in (None, ""):
            return []
        if isinstance(value, (str, int, float, bool)):
            text = str(value).strip()
            return [text] if text else []
        if isinstance(value, list):
            parts: List[str] = []
            for item_value in value[:3]:
                parts.extend(_flatten_scalar(item_value, depth + 1))
            return [part for part in parts if part]
        if isinstance(value, dict):
            parts: List[str] = []
            for nested_key in priority_keys:
                if nested_key in value:
                    parts.extend(_flatten_scalar(value[nested_key], depth + 1))
                    if parts:
                        return parts
            for nested_value in list(value.values())[:3]:
                parts.extend(_flatten_scalar(nested_value, depth + 1))
            return [part for part in parts if part]
        return []

    parts: List[str] = []

    for key in priority_keys:
        if key in item:
            flattened = _flatten_scalar(item.get(key))
            if flattened:
                parts.append(flattened[0])
                break

    for key, value in item.items():
        if key in priority_keys and parts:
            continue
        flattened = _flatten_scalar(value)
        if not flattened:
            continue
        label = key.replace("_", " ").strip()
        if isinstance(value, list):
            rendered = ", ".join(flattened[:3])
        else:
            rendered = flattened[0]
        if label in {"supporting analysts", "source analysts", "analysts", "supported by", "raised by"}:
            parts.append(f"{label.title()}: {rendered}.")
        elif label not in {"text", "description"}:
            parts.append(f"{label.title()}: {rendered}.")
        else:
            parts.append(rendered)
        if len(parts) >= 3:
            break

    cleaned = " ".join(part.strip() for part in parts if part and str(part).strip()).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    if not cleaned:
        raise ValueError(f"{field} contains an object that cannot be safely normalized")
    return cleaned


def _validate_normalized_list_text(field: str, text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in FORBIDDEN_LIST_CONTENT_TERMS):
        raise ValueError(f"{field} contains forbidden internal or prompt content")
    matches = find_forbidden_recommendation_language(text)
    if matches:
        raise ValueError(f"{field} contains forbidden recommendation or valuation language")
    if re.search(r"\b(?:buy|sell|hold)\b", lowered):
        raise ValueError(f"{field} contains forbidden recommendation or valuation language")
    return text.strip()


def _contains_forbidden_payload_content(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_FINAL_COMMITTEE_KEYS:
                return True
            if _contains_forbidden_payload_content(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden_payload_content(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(term in lowered for term in FORBIDDEN_LIST_CONTENT_TERMS)
    return False


def _normalize_string_list(
    value: Any,
    field: str,
    *,
    schema_warnings: List[str] | None = None,
    default_empty: bool = False,
) -> List[str]:
    warnings = schema_warnings if schema_warnings is not None else []
    if value is None:
        if default_empty:
            warnings.append(f"{field} was normalized to []")
            return []
        raise ValueError(f"{field} must be a list")
    items: List[Any]
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        warnings.append(f"{field} was normalized from string to list")
        items = [value]
    elif isinstance(value, dict):
        warnings.append(f"{field} was normalized from object to list")
        items = [value]
    else:
        raise ValueError(f"{field} must be a list")
    normalized: List[str] = []
    for item in items:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = _safe_list_dict_to_string(item, field).strip()
        else:
            raise ValueError(f"{field} contains items that cannot be safely normalized")
        if not text:
            continue
        text = _validate_normalized_list_text(field, text)
        if len(text) > 350:
            text = text[:349].rstrip() + "…"
            warnings.append(f"{field} contained a long value and it was truncated during normalization.")
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _default_object_list_adapter(item: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"{field_name} must contain objects")
    if _contains_forbidden_payload_content(item):
        raise ValueError(f"{field_name} contains forbidden internal or raw payload content")
    return json.loads(json.dumps(item, ensure_ascii=False))


def _normalize_object_list(
    value: Any,
    field_name: str,
    *,
    item_adapter,
    schema_warnings: List[str] | None = None,
) -> List[Dict[str, Any]]:
    warnings = schema_warnings if schema_warnings is not None else []
    if value is None:
        warnings.append(f"{field_name} was normalized to []")
        return []
    if _contains_forbidden_payload_content(value):
        raise ValueError(f"{field_name} contains forbidden internal or raw payload content")
    if isinstance(value, list):
        items = value
    elif isinstance(value, (str, dict)):
        warnings.append(f"{field_name} was normalized to object list")
        items = [value]
    else:
        raise ValueError(f"{field_name} must be a list")
    normalized: List[Dict[str, Any]] = []
    for item in items:
        normalized_item = item_adapter(item, field_name)
        if _contains_forbidden_payload_content(normalized_item):
            raise ValueError(f"{field_name} contains forbidden internal or raw payload content")
        normalized.append(normalized_item)
    return normalized


def _normalize_optional_string_list(value: Any, field: str) -> List[str]:
    if value is None:
        return []
    return _normalize_string_list(value, field)


def _normalize_bool(
    value: Any,
    field_name: str,
    *,
    schema_warnings: List[str] | None = None,
) -> bool:
    if isinstance(value, bool):
        return value
    normalized: bool | None = None
    warning_suffix = None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "used"}:
            normalized = True
        elif lowered in {"false", "no", "n", "not used", "unused"}:
            normalized = False
        else:
            raise ValueError(f"{field_name} must be a boolean")
        warning_suffix = "string"
    elif isinstance(value, int) and value in {0, 1}:
        normalized = bool(value)
        warning_suffix = "integer"
    elif value is None:
        raise ValueError(f"{field_name} must be a boolean")
    else:
        raise ValueError(f"{field_name} must be a boolean")
    if schema_warnings is not None:
        schema_warnings.append(
            f"{field_name} was normalized from {warning_suffix} to boolean."
        )
    return normalized


def _normalize_basis_used(
    value: Any,
    *,
    expected_basis: str | None = None,
    schema_warnings: List[str] | None = None,
) -> str:
    def _emit(normalized_basis: str) -> str:
        if schema_warnings is not None:
            schema_warnings.append(
                f"financial_committee_view.basis_used normalized to {normalized_basis}."
            )
        return normalized_basis

    if isinstance(value, str):
        lowered = value.strip().lower()
        if not lowered:
            raise ValueError(
                "financial_committee_view.basis_used must be consolidated|standalone|mixed|unknown"
            )
        if any(token in lowered for token in ("source_chunk", "raw_text", "input_pack", "full_text")):
            raise ValueError(
                "financial_committee_view.basis_used must be consolidated|standalone|mixed|unknown"
            )
        direct_map = {
            "consolidated": "consolidated",
            "consolidated basis": "consolidated",
            "consolidated financials": "consolidated",
            "standalone": "standalone",
            "standalone basis": "standalone",
            "standalone financials": "standalone",
            "mixed": "mixed",
            "mixed basis": "mixed",
            "both": "mixed",
            "standalone and consolidated": "mixed",
            "consolidated and standalone": "mixed",
            "unknown": "unknown",
            "not clear": "unknown",
        }
        normalized = direct_map.get(lowered)
        if normalized is None:
            raise ValueError(
                "financial_committee_view.basis_used must be consolidated|standalone|mixed|unknown"
            )
        if normalized != lowered:
            return _emit(normalized)
        return normalized
    if value is None:
        normalized = expected_basis if expected_basis in ALLOWED_COMMITTEE_BASIS else "unknown"
        return _emit(normalized)
    if isinstance(value, dict):
        candidate = value.get("basis_used") or value.get("basis") or value.get("value")
        if candidate is None:
            raise ValueError(
                "financial_committee_view.basis_used must be consolidated|standalone|mixed|unknown"
            )
        return _normalize_basis_used(
            candidate,
            expected_basis=expected_basis,
            schema_warnings=schema_warnings,
        )
    if isinstance(value, list) and len(value) == 1:
        return _normalize_basis_used(
            value[0],
            expected_basis=expected_basis,
            schema_warnings=schema_warnings,
        )
    raise ValueError(
        "financial_committee_view.basis_used must be consolidated|standalone|mixed|unknown"
    )


def _normalize_analyst_name(value: Any) -> str:
    return str(value or "").strip().lower()


ANALYST_REFERENCE_ALIASES = {
    "graham": "graham",
    "benjamin graham": "graham",
    "buffett": "buffett",
    "warren buffett": "buffett",
    "fisher": "fisher",
    "philip fisher": "fisher",
    "munger": "munger",
    "charlie munger": "munger",
    "lynch": "lynch",
    "peter lynch": "lynch",
}

ANALYST_REFERENCE_SUFFIX_RE = re.compile(
    r"\b(?:analyst|panel|registry|doctrine|profile)\b",
    re.IGNORECASE,
)


def normalize_known_analyst_reference(
    value: Any,
    *,
    field: str,
    remove_unknown: bool = False,
) -> tuple[List[str], List[Dict[str, Any]]]:
    repairs: List[Dict[str, Any]] = []

    def _record(original: Any, normalized: List[str], reason: str) -> None:
        repairs.append(
            {
                "path": field,
                "original": original,
                "normalized": normalized,
                "reason": reason,
            }
        )

    def _canonicalize_token(token: str) -> tuple[str | None, str | None]:
        original_token = token
        cleaned = token.strip().lower()
        if not cleaned:
            return None, None
        no_parens = re.sub(r"\([^)]*\)", " ", cleaned).strip()
        if no_parens != cleaned:
            cleaned = no_parens
            reason = "parenthetical_suffix_removed"
        else:
            reason = None
        suffix_stripped = ANALYST_REFERENCE_SUFFIX_RE.sub(" ", cleaned)
        suffix_stripped = re.sub(r"\s+", " ", suffix_stripped).strip(" ,/;:-")
        if suffix_stripped != cleaned:
            cleaned = suffix_stripped
            reason = reason or "role_suffix_removed"
        canonical = ANALYST_REFERENCE_ALIASES.get(cleaned)
        if canonical:
            return canonical, reason
        for alias, mapped in ANALYST_REFERENCE_ALIASES.items():
            if cleaned == alias:
                return mapped, reason
        return None, reason

    def _extract_tokens(item: Any) -> List[str]:
        if item is None:
            return []
        if isinstance(item, str):
            text = item.strip()
            if not text:
                return []
            parts = re.split(r"[,/]| and ", text, flags=re.IGNORECASE)
            return [part.strip() for part in parts if part and part.strip()]
        if isinstance(item, dict):
            candidate = item.get("analyst") or item.get("name") or item.get("value")
            return _extract_tokens(candidate)
        if isinstance(item, list):
            parts: List[str] = []
            for child in item:
                parts.extend(_extract_tokens(child))
            return parts
        return [str(item).strip()]

    if value is None:
        return [], repairs

    raw_items = value if isinstance(value, list) else [value]
    normalized: List[str] = []
    unknown_seen = False
    for raw_item in raw_items:
        tokens = _extract_tokens(raw_item)
        if isinstance(raw_item, str) and len(tokens) > 1:
            _record(raw_item, tokens, "compound_reference_split")
        token_normalized: List[str] = []
        for token in tokens:
            canonical, reason = _canonicalize_token(token)
            if canonical is None:
                unknown_seen = True
                if remove_unknown:
                    _record(token, [], "unknown_analyst_reference_removed")
                    continue
                raise ValueError(f"{field} contains invalid analysts: {[token.strip().lower()]}")
            if canonical not in token_normalized:
                token_normalized.append(canonical)
            if reason or canonical != token.strip().lower():
                _record(token, [canonical], reason or "analyst_reference_normalized")
        for candidate in token_normalized:
            if candidate not in normalized:
                normalized.append(candidate)

    if not normalized and unknown_seen:
        return [], repairs
    return normalized, repairs


def _normalize_analyst_list_field(
    value: Any,
    field: str,
    *,
    schema_warnings: List[str],
) -> List[str]:
    if value in (None, ""):
        if value is None:
            schema_warnings.append(f"{field} was normalized to []")
        return []
    if isinstance(value, str):
        normalized_text = value.strip().lower()
        if normalized_text in {"", "none", "no missing analysts", "no excluded analysts"}:
            schema_warnings.append(f"{field} was normalized to []")
            return []
        raise ValueError(f"{field} must be a list of analyst names")
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")

    normalized: List[str] = []
    coercion_applied = False
    for item in value:
        if isinstance(item, str):
            candidate = _normalize_analyst_name(item)
        elif isinstance(item, dict):
            raw_name = item.get("analyst") or item.get("name")
            candidate = _normalize_analyst_name(raw_name)
            coercion_applied = True
        else:
            raise ValueError(f"{field} must contain analyst names")
        if not candidate:
            coercion_applied = True
            continue
        if candidate not in normalized:
            normalized.append(candidate)
    if coercion_applied:
        schema_warnings.append(f"{field} was normalized to {normalized or []}")
    return normalized


def _normalize_known_analyst_list(
    value: Any,
    field: str,
    *,
    schema_warnings: List[str],
) -> List[str]:
    if value is not None and not isinstance(value, (str, list, dict)):
        raise ValueError(f"{field} must be a list of analyst names")
    normalized, repairs = normalize_known_analyst_reference(value, field=field, remove_unknown=False)
    if repairs:
        schema_warnings.append(f"{field} was normalized to {normalized or []}")
    return normalized


def _flatten_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, list):
        for item in value:
            yield from _flatten_strings(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _flatten_strings(item)


def _find_forbidden_keys(value: Any, *, path: str = "$") -> List[str]:
    found: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_FINAL_COMMITTEE_KEYS:
                found.append(child_path)
            found.extend(_find_forbidden_keys(item, path=child_path))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            found.extend(_find_forbidden_keys(item, path=f"{path}[{idx}]"))
    return found


def _normalize_registry_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _token_overlap(left: str, right: str) -> bool:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return False
    return not left_tokens.isdisjoint(right_tokens)


def _build_uncertainty_registry(
    analyst_payloads: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    registry: List[Dict[str, Any]] = []
    registry_by_id: Dict[str, Dict[str, Any]] = {}
    seen: Set[tuple[str, str]] = set()
    field_sources = [
        ("open_uncertainties", "evidence_gap"),
        ("evidence_gaps", "evidence_gap"),
        ("reasoning_limits", "evidence_gap"),
        ("key_questions", "business_quality"),
        ("investor_questions", "business_quality"),
        ("financial_missing_data", "financials"),
        ("financial_interpretation_limits", "financials"),
        ("financial_warnings_carried_forward", "financials"),
    ]
    for payload in analyst_payloads:
        analyst = str(payload.get("doctrine_id") or "").strip().lower()
        counter = 1
        for field_name, default_category in field_sources:
            for item in payload.get(field_name, []) or []:
                text = _normalize_registry_text(item)
                if not text:
                    continue
                key = (analyst, text)
                if key in seen:
                    continue
                seen.add(key)
                category = "financials" if default_category == "financials" else (
                    "governance" if any(token in text for token in ("governance", "board", "control", "compensation")) else default_category
                )
                entry = {
                    "uncertainty_id": f"{analyst}_u{counter:03d}",
                    "analyst": analyst,
                    "category": category,
                    "text": text[:220],
                    "aliases": [text[:220]],
                }
                registry.append(entry)
                registry_by_id[entry["uncertainty_id"]] = entry
                counter += 1
    return registry, registry_by_id


def _match_unknown_to_registry(
    unknown_text: str,
    *,
    raised_by: Sequence[str],
    registry: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    normalized_unknown = _normalize_registry_text(unknown_text)
    raised_by_set = {str(item).strip().lower() for item in raised_by}
    matches: List[Dict[str, Any]] = []
    for entry in registry:
        if raised_by_set and entry["analyst"] not in raised_by_set:
            continue
        if normalized_unknown == entry["text"]:
            matches.append(entry)
            continue
        if _token_overlap(normalized_unknown, entry["text"]):
            matches.append(entry)
    return matches


def _validate_forbidden_language(payload: Dict[str, Any]) -> None:
    text_blob = "\n".join(_flatten_strings(payload))
    if "source_chunk" in text_blob:
        raise ValueError("committee synthesis must not include raw source_chunk data")
    matches = find_forbidden_recommendation_language(text_blob)
    if matches:
        raise ValueError(
            f'committee synthesis contains forbidden language: "{matches[0]["matched_text"]}"'
        )


def _validate_internal_terms_free(value: Any, field: str) -> None:
    text_blob = "\n".join(_flatten_strings(value)).lower()
    for term in FORBIDDEN_INTERNAL_BRIEF_TERMS:
        if term in text_blob:
            raise ValueError(f'{field} contains forbidden internal term "{term}"')


def _tokenize(value: str) -> Set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value).lower())
        if len(token) >= 4
    }


def _normalize_evidence_ids(value: Any, field: str, *, allowed: Set[str]) -> List[str]:
    evidence_ids = _normalize_string_list(value, field)
    invalid = [item for item in evidence_ids if item not in allowed]
    if invalid:
        raise ValueError(
            f"{field} contains evidence_ids not present in analyst inputs: {sorted(set(invalid))}"
        )
    deduped: List[str] = []
    for item in evidence_ids:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _canonical_committee_evidence_id(evidence_id: str) -> str:
    normalized = normalize_evidence_id(evidence_id)
    match = re.match(
        r"^(ev_fy\d+)_business_classification_(?!json_)([a-z0-9_]+)$",
        normalized,
    )
    if match:
        year = match.group(1).replace("ev_", "")
        dna = match.group(2)
        return (
            f"{match.group(1)}_business_classification_json_"
            f"business_dna_by_year_{year}_{dna}"
        )
    return normalized


def _validate_normalized_evidence_ids(
    value: Any,
    field: str,
    *,
    allowed: Set[str],
) -> List[str]:
    evidence_ids = _normalize_string_list(value, field)
    normalized: List[str] = []
    unresolved: List[str] = []
    for evidence_id in evidence_ids:
        canonical = _canonical_committee_evidence_id(evidence_id)
        if canonical in allowed:
            if canonical not in normalized:
                normalized.append(canonical)
            continue
        if evidence_id in allowed:
            if evidence_id not in normalized:
                normalized.append(evidence_id)
            continue
        unresolved.append(evidence_id)
    if unresolved:
        raise ValueError(
            f"{field} contains unresolved evidence_ids not present in analyst inputs after normalization: "
            f"{sorted(set(unresolved))}"
        )
    return normalized


def _filter_known_evidence_ids(
    value: Any,
    field: str,
    *,
    allowed: Set[str],
    schema_warnings: List[str],
) -> List[str]:
    evidence_ids = _normalize_string_list(
        value,
        field,
        schema_warnings=schema_warnings,
        default_empty=True,
    )
    normalized: List[str] = []
    dropped: List[str] = []
    for evidence_id in evidence_ids:
        lowered = str(evidence_id).strip().lower()
        if lowered in PCIM_SECTION_NAME_EVIDENCE_IDS:
            dropped.append(evidence_id)
            continue
        canonical = _canonical_committee_evidence_id(evidence_id)
        if canonical in allowed:
            if canonical not in normalized:
                normalized.append(canonical)
            continue
        if evidence_id in allowed:
            if evidence_id not in normalized:
                normalized.append(evidence_id)
            continue
        dropped.append(evidence_id)
    if dropped:
        schema_warnings.append(
            f"{field} dropped evidence IDs not present in analyst evidence pool: {sorted(set(dropped))}"
        )
    return normalized


def _clean_optional_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _validate_normalized_list_text(field, text)


def _normalize_area_of_agreement_item(
    item: Any,
    allowed_evidence_ids: Set[str],
    schema_warnings: List[str] | None = None,
) -> Dict[str, Any]:
    warnings = schema_warnings if schema_warnings is not None else []
    field_name = "areas_of_agreement"
    if isinstance(item, str):
        summary = _validate_normalized_list_text(f"{field_name}.summary", item)
        return {
            "theme": "unspecified",
            "summary": summary,
            "evidence_ids": [],
            "source_analysts": [],
            "evidence_limit": (
                "No direct evidence ID supplied by committee output; agreement is grounded in analyst summaries."
            ),
        }
    if not isinstance(item, dict):
        raise ValueError(f"{field_name} must contain objects")
    if _contains_forbidden_payload_content(item):
        raise ValueError(f"{field_name} contains forbidden internal or raw payload content")

    theme = _clean_optional_text(
        item.get("theme") or item.get("topic") or item.get("area") or item.get("title"),
        f"{field_name}.theme",
    ) or "unspecified"
    summary = _clean_optional_text(
        item.get("summary") or item.get("agreement") or item.get("description") or item.get("text"),
        f"{field_name}.summary",
    )
    if not summary:
        if theme != "unspecified":
            summary = theme
            warnings.append(f"{field_name}.summary was inferred from theme")
        else:
            raise ValueError("areas_of_agreement.summary is required")

    evidence_source = item.get("evidence_ids")
    if evidence_source is None and "evidence" in item:
        evidence_source = item.get("evidence")
    evidence_ids = _filter_known_evidence_ids(
        evidence_source,
        f"{field_name}.evidence_ids",
        allowed=allowed_evidence_ids,
        schema_warnings=warnings,
    )
    source_analysts = _normalize_known_analyst_list(
        item.get("source_analysts") if "source_analysts" in item else item.get("analysts"),
        f"{field_name}.source_analysts",
        schema_warnings=warnings,
    )
    evidence_limit = _clean_optional_text(
        item.get("evidence_limit"),
        f"{field_name}.evidence_limit",
    )
    if not evidence_limit and not evidence_ids:
        evidence_limit = (
            "No direct evidence ID supplied by committee output; agreement is grounded in analyst summaries."
        )
    return {
        "theme": theme,
        "summary": summary,
        "evidence_ids": evidence_ids,
        "source_analysts": source_analysts,
        "evidence_limit": evidence_limit,
    }


def _normalize_area_of_disagreement_item(
    item: Any,
    allowed_evidence_ids: Set[str],
    schema_warnings: List[str],
) -> Dict[str, Any]:
    field_name = "areas_of_disagreement"
    if isinstance(item, str):
        summary = _validate_normalized_list_text(f"{field_name}.summary", item)
        return {
            "theme": "unspecified",
            "analysts_positive_or_less_concerned": [],
            "analysts_cautious_or_negative": [],
            "summary": summary,
            "why_it_matters": "",
            "evidence_ids": [],
        }
    if not isinstance(item, dict):
        raise ValueError(f"{field_name} must contain objects")
    if _contains_forbidden_payload_content(item):
        raise ValueError(f"{field_name} contains forbidden internal or raw payload content")

    theme = _clean_optional_text(
        item.get("theme") or item.get("topic") or item.get("area") or item.get("title"),
        f"{field_name}.theme",
    ) or "unspecified"
    summary = _clean_optional_text(
        item.get("summary") or item.get("disagreement") or item.get("description") or item.get("text"),
        f"{field_name}.summary",
    )
    if not summary:
        if theme != "unspecified":
            summary = theme
            schema_warnings.append(f"{field_name}.summary was inferred from theme")
        else:
            raise ValueError("areas_of_disagreement.summary is required")
    normalized = {
        "theme": theme,
        "analysts_positive_or_less_concerned": _normalize_known_analyst_list(
            item.get("analysts_positive_or_less_concerned")
            or item.get("analysts_positive")
            or item.get("analysts_less_concerned")
            or item.get("analysts_positive_or_less_concerned"),
            f"{field_name}.analysts_positive_or_less_concerned",
            schema_warnings=schema_warnings,
        ),
        "analysts_cautious_or_negative": _normalize_known_analyst_list(
            item.get("analysts_cautious_or_negative")
            or item.get("analysts_cautious")
            or item.get("analysts_negative"),
            f"{field_name}.analysts_cautious_or_negative",
            schema_warnings=schema_warnings,
        ),
        "summary": summary,
        "why_it_matters": _clean_optional_text(
            item.get("why_it_matters") or item.get("financial_relevance") or item.get("importance"),
            f"{field_name}.why_it_matters",
        ),
        "evidence_ids": _filter_known_evidence_ids(
            item.get("evidence_ids") if "evidence_ids" in item else item.get("evidence"),
            f"{field_name}.evidence_ids",
            allowed=allowed_evidence_ids,
            schema_warnings=schema_warnings,
        ),
    }
    for optional_field in (
        "analysts_with_business_quality_focus",
        "analysts_with_downside_or_execution_focus",
    ):
        if optional_field in item:
            normalized[optional_field] = _normalize_known_analyst_list(
                item.get(optional_field),
                f"{field_name}.{optional_field}",
                schema_warnings=schema_warnings,
            )
    disagreement_type = str(item.get("disagreement_type") or "").strip()
    if disagreement_type:
        normalized["disagreement_type"] = disagreement_type
    return normalized


def _normalize_positive_signal_item(
    item: Any,
    allowed_evidence_ids: Set[str],
    schema_warnings: List[str],
) -> Dict[str, Any]:
    field_name = "strongest_positive_signals"
    if isinstance(item, str):
        signal = _validate_normalized_list_text(f"{field_name}.signal", item)
        return {
            "signal": signal,
            "summary": "",
            "why_it_matters": "",
            "supported_by": [],
            "source_analysts": [],
            "evidence_ids": [],
            "evidence_limit": (
                "No direct evidence ID supplied by committee output; signal is grounded in analyst summaries."
            ),
        }
    if not isinstance(item, dict):
        raise ValueError(f"{field_name} must contain objects")
    if _contains_forbidden_payload_content(item):
        raise ValueError(f"{field_name} contains forbidden internal or raw payload content")
    signal = _clean_optional_text(
        item.get("signal")
        or item.get("title")
        or item.get("theme")
        or item.get("point")
        or item.get("summary"),
        f"{field_name}.signal",
    )
    if not signal:
        raise ValueError("strongest_positive_signals.signal is required")
    why = _clean_optional_text(
        item.get("why_it_matters") or item.get("importance") or item.get("rationale"),
        f"{field_name}.why_it_matters",
    )
    summary = _clean_optional_text(
        item.get("summary") or item.get("description") or why,
        f"{field_name}.summary",
    )
    source_analysts = _normalize_known_analyst_list(
        item.get("source_analysts") if "source_analysts" in item else item.get("analysts") or item.get("supported_by"),
        f"{field_name}.source_analysts",
        schema_warnings=schema_warnings,
    )
    evidence_ids = _filter_known_evidence_ids(
        item.get("evidence_ids") if "evidence_ids" in item else item.get("evidence"),
        f"{field_name}.evidence_ids",
        allowed=allowed_evidence_ids,
        schema_warnings=schema_warnings,
    )
    evidence_limit = _clean_optional_text(
        item.get("evidence_limit") or item.get("limitation"),
        f"{field_name}.evidence_limit",
    )
    if not evidence_limit and not evidence_ids:
        evidence_limit = (
            "No direct evidence ID supplied by committee output; signal is grounded in analyst summaries."
        )
    return {
        "signal": signal,
        "summary": summary or why or signal,
        "why_it_matters": why,
        "supported_by": source_analysts,
        "source_analysts": source_analysts,
        "evidence_ids": evidence_ids,
        "evidence_limit": evidence_limit,
    }


def _normalize_risk_signal_item(
    item: Any,
    allowed_evidence_ids: Set[str],
    schema_warnings: List[str],
) -> Dict[str, Any]:
    field_name = "most_important_risks"
    if isinstance(item, str):
        risk = _validate_normalized_list_text(f"{field_name}.risk", item)
        return {
            "risk": risk,
            "summary": "",
            "why_it_matters": "",
            "raised_by": [],
            "source_analysts": [],
            "severity": "uncertain",
            "evidence_ids": [],
            "evidence_limit": (
                "No direct evidence ID supplied by committee output; risk is grounded in analyst summaries."
            ),
        }
    if not isinstance(item, dict):
        raise ValueError(f"{field_name} must contain objects")
    if _contains_forbidden_payload_content(item):
        raise ValueError(f"{field_name} contains forbidden internal or raw payload content")
    risk = _clean_optional_text(
        item.get("risk")
        or item.get("concern")
        or item.get("red_flag")
        or item.get("title")
        or item.get("theme")
        or item.get("summary"),
        f"{field_name}.risk",
    )
    if not risk:
        raise ValueError("most_important_risks.risk is required")
    why = _clean_optional_text(
        item.get("why_it_matters") or item.get("importance") or item.get("rationale"),
        f"{field_name}.why_it_matters",
    )
    summary = _clean_optional_text(
        item.get("summary") or item.get("description") or why,
        f"{field_name}.summary",
    )
    source_analysts = _normalize_known_analyst_list(
        item.get("source_analysts") if "source_analysts" in item else item.get("analysts") or item.get("raised_by"),
        f"{field_name}.source_analysts",
        schema_warnings=schema_warnings,
    )
    severity = str(item.get("severity") or "uncertain").strip().lower()
    if severity not in {"low", "medium", "high", "uncertain"}:
        severity = "uncertain"
        schema_warnings.append("most_important_risks.severity normalized to uncertain")
    evidence_ids = _filter_known_evidence_ids(
        item.get("evidence_ids") if "evidence_ids" in item else item.get("evidence"),
        f"{field_name}.evidence_ids",
        allowed=allowed_evidence_ids,
        schema_warnings=schema_warnings,
    )
    evidence_limit = _clean_optional_text(
        item.get("evidence_limit") or item.get("limitation"),
        f"{field_name}.evidence_limit",
    )
    if not evidence_limit and not evidence_ids:
        evidence_limit = (
            "No direct evidence ID supplied by committee output; risk is grounded in analyst summaries."
        )
    return {
        "risk": risk,
        "summary": summary or why or risk,
        "why_it_matters": why,
        "raised_by": source_analysts,
        "source_analysts": source_analysts,
        "severity": severity,
        "evidence_ids": evidence_ids,
        "evidence_limit": evidence_limit,
    }


def _normalize_investigation_question_item(
    item: Any,
    schema_warnings: List[str],
) -> Dict[str, Any]:
    field_name = "investigation_questions"
    if isinstance(item, str):
        question = _validate_normalized_list_text(f"{field_name}.question", item)
        return {
            "question": question,
            "reason": "",
            "linked_unknown_or_risk": "",
        }
    if not isinstance(item, dict):
        raise ValueError(f"{field_name} must contain objects")
    if _contains_forbidden_payload_content(item):
        raise ValueError(f"{field_name} contains forbidden internal or raw payload content")
    question = _clean_optional_text(
        item.get("question") or item.get("text"),
        f"{field_name}.question",
    )
    if not question:
        raise ValueError("investigation_questions.question is required")
    return {
        "question": question,
        "reason": _clean_optional_text(
            item.get("reason") or item.get("why_it_matters") or item.get("rationale"),
            f"{field_name}.reason",
        ),
        "linked_unknown_or_risk": _clean_optional_text(
            item.get("linked_unknown_or_risk") or item.get("linked_unknown") or item.get("linked_risk"),
            f"{field_name}.linked_unknown_or_risk",
        ),
    }


def normalize_committee_field(
    field_name: str,
    value: Any,
    *,
    allowed_evidence_ids: Set[str],
    schema_warnings: List[str],
) -> Any:
    contract = COMMITTEE_FIELD_CONTRACTS.get(field_name)
    if contract is None:
        raise ValueError(f"unknown committee field contract: {field_name}")
    if contract["type"] == "string_list":
        return _normalize_string_list(
            value,
            field_name,
            schema_warnings=schema_warnings,
            default_empty=True,
        )
    if contract["type"] != "object_list":
        raise ValueError(f"unsupported committee field contract type: {contract['type']}")
    if field_name == "areas_of_agreement":
        return _normalize_object_list(
            value,
            field_name,
            item_adapter=lambda item, _field_name: _normalize_area_of_agreement_item(
                item,
                allowed_evidence_ids,
                schema_warnings=schema_warnings,
            ),
            schema_warnings=schema_warnings,
        )
    if field_name == "areas_of_disagreement":
        return _normalize_object_list(
            value,
            field_name,
            item_adapter=lambda item, _field_name: _normalize_area_of_disagreement_item(
                item,
                allowed_evidence_ids,
                schema_warnings,
            ),
            schema_warnings=schema_warnings,
        )
    if field_name == "strongest_positive_signals":
        return _normalize_object_list(
            value,
            field_name,
            item_adapter=lambda item, _field_name: _normalize_positive_signal_item(
                item,
                allowed_evidence_ids,
                schema_warnings,
            ),
            schema_warnings=schema_warnings,
        )
    if field_name == "most_important_risks":
        return _normalize_object_list(
            value,
            field_name,
            item_adapter=lambda item, _field_name: _normalize_risk_signal_item(
                item,
                allowed_evidence_ids,
                schema_warnings,
            ),
            schema_warnings=schema_warnings,
        )
    if field_name == "investigation_questions":
        return _normalize_object_list(
            value,
            field_name,
            item_adapter=lambda item, _field_name: _normalize_investigation_question_item(
                item,
                schema_warnings,
            ),
            schema_warnings=schema_warnings,
        )
    raise ValueError(f"committee field contract lacks adapter: {field_name}")


def _adapt_financial_disagreement_item(
    item: Any,
    field_name: str,
    *,
    schema_warnings: List[str],
) -> Dict[str, Any]:
    if isinstance(item, str):
        text = _validate_normalized_list_text(field_name, item)
        return {
            "topic": "unspecified",
            "analysts": [],
            "disagreement": text,
            "financial_relevance": "",
            "evidence_limit": "",
        }
    if not isinstance(item, dict):
        raise ValueError(f"{field_name} must contain objects")
    if _contains_forbidden_payload_content(item):
        raise ValueError(f"{field_name} contains forbidden internal or raw payload content")
    normalized_item = {
        "topic": str(item.get("topic") or item.get("what_they_disagree_on") or "unspecified").strip() or "unspecified",
        "analysts": _normalize_known_analyst_list(
            item.get("analysts") or item.get("analysts_involved"),
            f"{field_name}.analysts",
            schema_warnings=schema_warnings,
        ),
        "disagreement": _validate_normalized_list_text(
            f"{field_name}.disagreement",
            str(
                item.get("disagreement")
                or item.get("what_they_disagree_on")
                or item.get("summary")
                or ""
            ).strip(),
        ),
        "financial_relevance": _validate_normalized_list_text(
            f"{field_name}.financial_relevance",
            str(item.get("financial_relevance") or item.get("why_it_matters") or "").strip(),
        ) if str(item.get("financial_relevance") or item.get("why_it_matters") or "").strip() else "",
        "evidence_limit": _validate_normalized_list_text(
            f"{field_name}.evidence_limit",
            str(item.get("evidence_limit") or item.get("uncertainty") or "").strip(),
        ) if str(item.get("evidence_limit") or item.get("uncertainty") or "").strip() else "",
    }
    disagreement_type = str(item.get("disagreement_type") or "").strip()
    if disagreement_type:
        normalized_item["disagreement_type"] = disagreement_type
    return normalized_item


def _validate_object_list(
    value: Any,
    field: str,
    required_keys: Sequence[str],
) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    normalized: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{field} must contain objects")
        missing = [key for key in required_keys if key not in item]
        if missing:
            raise ValueError(f"{field} item missing required keys: {missing}")
        normalized.append(item)
    return normalized


def _normalize_critical_unknown_item(
    item: Any,
    *,
    registry: Sequence[Dict[str, Any]],
    registry_by_id: Dict[str, Dict[str, Any]],
    schema_warnings: List[str],
) -> Dict[str, Any]:
    if isinstance(item, str):
        unknown = _validate_normalized_list_text("critical_unknowns.unknown", item)
        matches = _match_unknown_to_registry(unknown, raised_by=[], registry=registry)
        if not matches:
            raise ValueError("critical_unknowns must be grounded in analyst uncertainty registry")
        schema_warnings.append(
            "critical_unknowns string entry was normalized using analyst uncertainty registry."
        )
        return {
            "unknown": unknown,
            "raised_by": sorted({match["analyst"] for match in matches}),
            "why_it_matters": "",
            "source_uncertainty_ids": [match["uncertainty_id"] for match in matches],
            "evidence_limit": "Grounded in analyst uncertainty registry.",
        }

    if not isinstance(item, dict):
        raise ValueError("critical_unknowns must contain objects or strings")
    if _contains_forbidden_payload_content(item):
        raise ValueError("critical_unknowns contains forbidden internal or raw payload content")

    unknown = _clean_optional_text(
        item.get("unknown")
        or item.get("uncertainty")
        or item.get("question")
        or item.get("issue")
        or item.get("unknown_text")
        or item.get("open_question")
        or item.get("description")
        or item.get("text")
        or item.get("summary"),
        "critical_unknowns.unknown",
    )
    if not unknown:
        raise ValueError("critical_unknowns.unknown is required")

    raised_by = _normalize_known_analyst_list(
        item.get("raised_by") or item.get("analysts") or item.get("source_analysts"),
        "critical_unknowns.raised_by",
        schema_warnings=schema_warnings,
    )
    source_ids = _normalize_string_list(
        item.get("source_uncertainty_ids")
        or item.get("uncertainty_ids")
        or item.get("source_ids"),
        "critical_unknowns.source_uncertainty_ids",
        schema_warnings=schema_warnings,
        default_empty=True,
    )
    invalid_ids = [item_id for item_id in source_ids if item_id not in registry_by_id]
    if invalid_ids:
        raise ValueError(
            "critical_unknowns contains source_uncertainty_ids not present in analyst uncertainty registry: "
            f"{sorted(set(invalid_ids))}"
        )

    if source_ids:
        source_entries = [registry_by_id[item_id] for item_id in source_ids]
        if not raised_by:
            raised_by = sorted({entry["analyst"] for entry in source_entries})
            schema_warnings.append("critical_unknowns.raised_by was inferred from source_uncertainty_ids.")
        invalid_raised_by = [analyst for analyst in raised_by if analyst not in {entry["analyst"] for entry in source_entries}]
        if invalid_raised_by:
            raise ValueError(f"critical_unknowns.raised_by contains analysts not linked to source_uncertainty_ids: {invalid_raised_by}")
        if not _match_unknown_to_registry(unknown, raised_by=raised_by, registry=source_entries):
            raise ValueError("critical_unknowns must be grounded in analyst uncertainty registry")
    else:
        matches = _match_unknown_to_registry(
            unknown,
            raised_by=raised_by,
            registry=registry,
        )
        if not matches:
            raise ValueError("critical_unknowns must be grounded in analyst uncertainty registry")
        source_ids = [match["uncertainty_id"] for match in matches]
        if not raised_by:
            raised_by = sorted({match["analyst"] for match in matches})
        schema_warnings.append(
            "critical_unknowns source_uncertainty_ids were inferred from analyst uncertainty registry."
        )

    source_text = " ".join(registry_by_id[item_id]["text"] for item_id in source_ids)
    if _tokenize(unknown).isdisjoint(_tokenize(source_text)):
        raise ValueError("critical_unknowns must be grounded in analyst uncertainty registry")

    return {
        "unknown": unknown,
        "raised_by": raised_by,
        "why_it_matters": _clean_optional_text(
            item.get("why_it_matters")
            or item.get("importance")
            or item.get("implication")
            or item.get("rationale"),
            "critical_unknowns.why_it_matters",
        ),
        "source_uncertainty_ids": source_ids,
        "evidence_limit": _clean_optional_text(
            item.get("evidence_limit") or item.get("limitation"),
            "critical_unknowns.evidence_limit",
        ) or "Grounded in analyst uncertainty registry.",
    }


def _normalize_critical_unknowns(
    value: Any,
    *,
    registry: Sequence[Dict[str, Any]],
    registry_by_id: Dict[str, Dict[str, Any]],
    schema_warnings: List[str],
) -> List[Dict[str, Any]]:
    if value in (None, []):
        return []
    if isinstance(value, (str, dict)):
        schema_warnings.append("critical_unknowns was normalized to object list")
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise ValueError("critical_unknowns must be a list")
    return [
        _normalize_critical_unknown_item(
            item,
            registry=registry,
            registry_by_id=registry_by_id,
            schema_warnings=schema_warnings,
        )
        for item in items
    ]


def _collect_allowed_financial_terms(
    analyst_payloads: Sequence[Dict[str, Any]],
) -> Set[str]:
    allowed: Set[str] = set()
    for payload in analyst_payloads:
        for field in (
            "financial_metrics_used",
            "financial_red_flags",
            "financial_positive_signals",
            "financial_missing_data",
            "financial_interpretation_limits",
            "reasoning_limits",
            "open_uncertainties",
        ):
            for text in payload.get(field, []) or []:
                tokens = _tokenize(text)
                allowed.update(tokens)
                lowered = str(text).lower()
                for canonical, aliases in KNOWN_FINANCIAL_TERM_ALIASES.items():
                    if any(alias in lowered for alias in aliases):
                        allowed.add(canonical)
        assessment = payload.get("financial_assessment") or {}
        if isinstance(assessment, dict):
            for field in (
                "key_financial_strengths",
                "key_financial_concerns",
                "financial_red_flags",
                "missing_financial_data",
                "financial_interpretation_limits",
            ):
                for text in assessment.get(field, []) or []:
                    tokens = _tokenize(text)
                    allowed.update(tokens)
                    lowered = str(text).lower()
                    for canonical, aliases in KNOWN_FINANCIAL_TERM_ALIASES.items():
                        if any(alias in lowered for alias in aliases):
                            allowed.add(canonical)
        for field in ("financial_sections_consumed", "financial_warnings_carried_forward"):
            for text in payload.get(field, []) or []:
                lowered = str(text).lower()
                allowed.update(_tokenize(lowered))
                for canonical, aliases in KNOWN_FINANCIAL_TERM_ALIASES.items():
                    if any(alias in lowered for alias in aliases):
                        allowed.add(canonical)
    return allowed


OWNER_EARNINGS_LIMITATION_PATTERNS = (
    "owner earnings cannot be assessed",
    "owner earnings can't be assessed",
    "owner earnings could not be assessed",
    "owner earnings cannot assess",
    "owner earnings cannot be determined",
    "owner earnings not determinable",
    "owner-earnings cannot be assessed",
    "owner earnings not assessable",
    "owner-earnings not assessable",
    "owner earnings are not assessable",
    "owner earnings is not assessable",
    "fcf/capex missing prevents owner earnings",
    "fcf missing prevents owner earnings",
    "capex missing prevents owner earnings",
    "owner earnings interpretation limited",
    "owner earnings interpretation remain limited",
    "owner earnings interpretation remains limited",
    "owner earnings cannot be calculated",
    "owner earnings cannot be calculable",
    "owner earnings could not be calculated",
    "owner-earnings analysis is limited",
    "owner earnings analysis is limited",
    "owner earnings assessment is limited",
    "owner earnings or fcf-driven",
    "owner earnings, fcf margin",
)
OWNER_EARNINGS_POSITIVE_PATTERNS = (
    "strong owner earnings",
    "positive owner earnings",
    "owner earnings are strong",
    "owner earnings are positive",
    "owner earnings support dividends",
    "owner earnings support dividend",
    "owner earnings support",
    "owner earnings are calculable",
    "owner earnings can be assessed",
    "owner earnings yield",
    "owner earnings margin",
    "owner-earnings yield",
    "owner-earnings margin",
    "attractive owner earnings",
    "owner earnings are healthy",
)


def _normalize_owner_earnings_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower().replace("owner-earnings", "owner earnings")).strip()


def classify_owner_earnings_reference(
    text: str,
    path: str = "",
    financial_context: Dict[str, Any] | None = None,
) -> str:
    lowered = _normalize_owner_earnings_text(text)
    if not lowered or "owner earnings" not in lowered:
        return "none"

    normalized_path = str(path or "").lower()
    context = financial_context or {}

    is_question_path = any(
        token in normalized_path
        for token in (
            "investor_questions_from_financials",
            "key_questions",
            "open_questions",
            "critical_unknowns",
            "financial_unknowns",
        )
    )
    starts_like_question = bool(
        re.match(r"^\s*(what|why|how|whether|can|should|does|did|is|are)\b", str(text or "").strip(), re.IGNORECASE)
    )
    ends_like_question = str(text or "").strip().endswith("?")
    assessability_signal = any(
        phrase in lowered
        for phrase in (
            "required to assess",
            "needed to assess",
            "cannot assess",
            "can't assess",
            "could not assess",
            "insufficient to assess",
            "missing data",
            "not available",
            "cannot be assessed",
            "ability to assess",
            "assessment readiness",
            "readiness to assess",
            "owner earnings readiness",
        )
    )

    limitation_signal = any(pattern in lowered for pattern in OWNER_EARNINGS_LIMITATION_PATTERNS)
    fcf_capex_limitation = (
        ("fcf" in lowered or "free cash flow" in lowered or "capex" in lowered)
        and any(
            term in lowered
            for term in (
                "missing",
                "unavailable",
                "incomplete",
                "cannot",
                "can't",
                "could not",
                "not available",
                "not provided",
                "limited",
                "prevents",
                "prevent",
            )
        )
        and any(term in lowered for term in ("assess", "calculate", "interpret", "owner earnings"))
    )
    positive_signal = any(pattern in lowered for pattern in OWNER_EARNINGS_POSITIVE_PATTERNS)

    if positive_signal and not (limitation_signal or fcf_capex_limitation):
        return "positive_claim"
    if is_question_path or ends_like_question or starts_like_question:
        return "question"
    if limitation_signal or fcf_capex_limitation:
        return "limitation"
    if assessability_signal:
        if context.get("fcf_missing") or context.get("capex_missing") or context.get("payables_missing") or context.get("basis_unknown"):
            return "limitation" if not (is_question_path or ends_like_question or starts_like_question) else "question"
        return "neutral_reference"
    if any(token in lowered for token in ("assess", "assessment", "readiness", "evaluate", "review")):
        return "neutral_reference"
    return "ambiguous"


def _classify_owner_earnings_reference(text: str) -> str:
    return classify_owner_earnings_reference(text)


def _owner_earnings_support_registry(
    analyst_payloads: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    limitation_supported = False
    positive_supported = False
    fcf_missing = False
    capex_missing = False
    payables_missing = False
    basis_unknown = False
    supporting_analysts: List[str] = []
    supporting_texts: List[str] = []
    source_fields = (
        "financial_interpretation_limits",
        "financial_missing_data",
        "open_uncertainties",
        "reasoning_limits",
        "financial_warnings_carried_forward",
    )
    assessment_fields = (
        "financial_interpretation_limits",
        "missing_financial_data",
        "financial_warnings_carried_forward",
        "key_financial_concerns",
    )
    for payload in analyst_payloads:
        analyst = str(payload.get("doctrine_id") or "").strip().lower()
        truth_pack = payload.get("analyst_financial_truth_pack") or {}
        if isinstance(truth_pack, dict):
            text_blob = "\n".join(_flatten_strings(truth_pack)).lower()
            if any(token in text_blob for token in ("owner_earnings_estimate", "owner earnings estimate", "conservative_fcf_after_total_capex", "derived owner earnings")):
                limitation_supported = True
                if analyst and analyst not in supporting_analysts:
                    supporting_analysts.append(analyst)
                supporting_texts.append("Derived owner-earnings / conservative FCF estimate is available from financial truth.")
                if "maintenance_growth" in text_blob or "maintenance versus growth capex" in text_blob:
                    capex_missing = False
            if any(token in text_blob for token in ("total_identified_capex", "identified capex", "capex_deployed", "ppe_cwip_capex")):
                capex_missing = False
            if any(token in text_blob for token in ("conservative_fcf_after_total_capex", "fcf_after_ppe_cwip_capex", "\"fcf\"", "metric_id\": \"fcf")):
                fcf_missing = False
            if any(token in text_blob for token in ("payable_days", "\"payables\"", "metric_id\": \"payables")):
                payables_missing = False
            if any(token in text_blob for token in ("shares_outstanding", "closing_shares", "weighted_avg_shares")):
                basis_unknown = basis_unknown and False
        texts: List[str] = []
        for field in source_fields:
            texts.extend(str(item or "") for item in (payload.get(field) or []))
        assessment = payload.get("financial_assessment") or {}
        if isinstance(assessment, dict):
            for field in assessment_fields:
                texts.extend(str(item or "") for item in (assessment.get(field) or []))
        for text in texts:
            lowered = _normalize_owner_earnings_text(text)
            if not lowered:
                continue
            if ("fcf" in lowered or "free cash flow" in lowered) and any(
                term in lowered for term in ("missing", "unavailable", "incomplete", "cannot", "can't", "not available", "not provided")
            ):
                fcf_missing = True
            if "capex" in lowered and any(
                term in lowered for term in ("missing", "unavailable", "incomplete", "cannot", "can't", "not available", "not provided")
            ):
                capex_missing = True
            if "payables" in lowered and any(
                term in lowered for term in ("missing", "unavailable", "incomplete", "cannot", "can't", "not available", "not provided")
            ):
                payables_missing = True
            if "basis" in lowered and any(
                term in lowered for term in ("unknown", "unclear", "not clear", "indeterminate")
            ):
                basis_unknown = True
            has_fcf_or_capex_warning = (
                ("fcf" in lowered or "free cash flow" in lowered or "capex" in lowered)
                and any(term in lowered for term in ("missing", "unavailable", "incomplete", "cannot", "limited"))
            )
            reference_type = classify_owner_earnings_reference(
                lowered,
                financial_context={
                    "fcf_missing": fcf_missing,
                    "capex_missing": capex_missing,
                    "payables_missing": payables_missing,
                    "basis_unknown": basis_unknown,
                },
            )
            if reference_type == "limitation" or has_fcf_or_capex_warning:
                limitation_supported = True
                if analyst and analyst not in supporting_analysts:
                    supporting_analysts.append(analyst)
                if text not in supporting_texts:
                    supporting_texts.append(text)
            if reference_type == "positive_claim":
                positive_supported = True
    return {
        "owner_earnings_limitation_supported": limitation_supported,
        "owner_earnings_positive_claim_supported": positive_supported,
        "supporting_analysts": supporting_analysts,
        "supporting_texts": supporting_texts[:10],
        "fcf_missing": fcf_missing,
        "capex_missing": capex_missing,
        "payables_missing": payables_missing,
        "basis_unknown": basis_unknown,
        "owner_earnings_status": (
            "available_derived_precision_limited"
            if (not fcf_missing and not capex_missing and limitation_supported and not positive_supported)
            else ("missing" if (fcf_missing or capex_missing) else "available_explicit")
        ),
    }


def _owner_earnings_positive_claim_present(text_blob: str) -> bool:
    return _classify_owner_earnings_reference(text_blob) == "positive_claim"


def _owner_earnings_limitation_claim_present(text_blob: str) -> bool:
    return _classify_owner_earnings_reference(text_blob) == "limitation"


def _owner_earnings_assessment_context_present(text_blob: str) -> bool:
    lowered = _normalize_owner_earnings_text(text_blob)
    if "owner earnings" not in lowered:
        return False
    return any(
        phrase in lowered
        for phrase in (
            "required to assess",
            "needed to assess",
            "cannot assess",
            "can't assess",
            "could not assess",
            "cannot be assessed",
            "assessment readiness",
            "ability to assess",
            "without capex",
            "without free cash flow",
        )
    )


def _iter_string_paths(value: Any, *, path: str = "$") -> Iterable[Tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_string_paths(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from _iter_string_paths(item, path=f"{path}[{idx}]")


def _owner_earnings_error(
    *,
    path: str,
    reference_type: str,
    owner_earnings_support: Dict[str, Any],
    text: str,
    message: str,
) -> ValueError:
    preview = re.sub(r"\s+", " ", text).strip()[:180]
    return ValueError(
        f"{message}: path={path}; classified_type={reference_type}; "
        f"limitation_supported={bool(owner_earnings_support.get('owner_earnings_limitation_supported'))}; "
        f"positive_claim_supported={bool(owner_earnings_support.get('owner_earnings_positive_claim_supported'))}; "
        f"fcf_missing={bool(owner_earnings_support.get('fcf_missing'))}; "
        f"capex_missing={bool(owner_earnings_support.get('capex_missing'))}; "
        f"text_preview={preview!r}"
    )


def _expected_financials_used(
    analyst_payloads: Sequence[Dict[str, Any]],
) -> bool:
    for payload in analyst_payloads:
        assessment = payload.get("financial_assessment") or {}
        if isinstance(assessment, dict) and assessment.get("financials_used") is True:
            return True
        if payload.get("financial_metrics_used"):
            return True
        if payload.get("financial_warnings_carried_forward"):
            return True
        if payload.get("financial_interpretation_limits"):
            return True
        if payload.get("financial_missing_data"):
            return True
        if payload.get("financial_positive_signals"):
            return True
        if payload.get("financial_red_flags"):
            return True
        if isinstance(assessment, dict):
            for field in (
                "key_financial_strengths",
                "key_financial_concerns",
                "financial_red_flags",
                "missing_financial_data",
                "financial_interpretation_limits",
            ):
                if assessment.get(field):
                    return True
    return False


def _contains_basis_unknown_signal(payload: Dict[str, Any]) -> bool:
    texts: List[str] = []
    for field in (
        "financial_warnings_carried_forward",
        "financial_interpretation_limits",
        "financial_missing_data",
    ):
        texts.extend(str(item or "").lower() for item in (payload.get(field) or []))
    assessment = payload.get("financial_assessment") or {}
    if isinstance(assessment, dict):
        for field in ("financial_interpretation_limits", "missing_financial_data"):
            texts.extend(str(item or "").lower() for item in (assessment.get(field) or []))
        basis_used = str(assessment.get("basis_used") or "").strip().lower()
        if basis_used == "unknown":
            return True
    combined = " ".join(texts)
    return "basis unknown" in combined or "basis is unknown" in combined or "basis unclear" in combined


def _expected_basis_used(
    analyst_payloads: Sequence[Dict[str, Any]],
) -> str:
    explicit_bases: Set[str] = set()
    saw_basis_unknown_signal = False
    for payload in analyst_payloads:
        assessment = payload.get("financial_assessment") or {}
        if isinstance(assessment, dict):
            basis_used = str(assessment.get("basis_used") or "").strip().lower()
            if basis_used in {"consolidated", "standalone", "mixed"}:
                explicit_bases.add(basis_used)
            elif basis_used == "unknown":
                saw_basis_unknown_signal = True
        if _contains_basis_unknown_signal(payload):
            saw_basis_unknown_signal = True
    if "mixed" in explicit_bases:
        return "mixed"
    if explicit_bases == {"consolidated", "standalone"}:
        return "mixed"
    if explicit_bases == {"consolidated"}:
        return "consolidated"
    if explicit_bases == {"standalone"}:
        return "standalone"
    if saw_basis_unknown_signal:
        return "unknown"
    return "unknown"


def _referenced_financial_terms(value: Any) -> Set[str]:
    referenced: Set[str] = set()
    text_blob = "\n".join(_flatten_strings(value)).lower()
    for canonical, aliases in KNOWN_FINANCIAL_TERM_ALIASES.items():
        if any(alias in text_blob for alias in aliases):
            referenced.add(canonical)
    return referenced


def _validate_financial_committee_view(
    value: Any,
    *,
    allowed_terms: Set[str],
    owner_earnings_support: Dict[str, Any],
    expected_financials_used: bool,
    expected_basis_used: str,
    schema_warnings: List[str],
) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("financial_committee_view must be an object")

    value["financials_used"] = _normalize_bool(
        value.get("financials_used"),
        "financial_committee_view.financials_used",
        schema_warnings=schema_warnings,
    )
    if value["financials_used"] != expected_financials_used:
        raise ValueError(
            "financial_committee_view.financials_used must match analyst financial input usage"
        )
    value["basis_used"] = _normalize_basis_used(
        value.get("basis_used"),
        expected_basis=expected_basis_used,
        schema_warnings=schema_warnings,
    )
    if value["basis_used"] not in ALLOWED_COMMITTEE_BASIS:
        raise ValueError(
            "financial_committee_view.basis_used must be consolidated|standalone|mixed|unknown"
        )
    if expected_basis_used != "unknown" and value["basis_used"] != expected_basis_used:
        raise ValueError(
            "financial_committee_view.basis_used must match analyst financial basis usage"
        )
    if expected_basis_used == "unknown" and value["basis_used"] != "unknown":
        raise ValueError(
            "financial_committee_view.basis_used must match analyst financial basis usage"
        )

    for field in (
        "financial_consensus",
        "financial_strengths",
        "financial_concerns",
        "missing_financial_data",
        "financial_red_flags",
        "financial_interpretation_limits",
        "investor_questions_from_financials",
    ):
        value[field] = _normalize_string_list(
            value.get(field),
            f"financial_committee_view.{field}",
            schema_warnings=schema_warnings,
            default_empty=True,
        )

    disagreements = _normalize_object_list(
        value.get("financial_disagreements"),
        "financial_committee_view.financial_disagreements",
        item_adapter=lambda item, field_name: _adapt_financial_disagreement_item(
            item,
            field_name,
            schema_warnings=schema_warnings,
        ),
        schema_warnings=schema_warnings,
    )
    for item in disagreements:
        if item.get("disagreement_type") and item.get("disagreement_type") not in {
            "true_disagreement",
            "different_emphasis",
            "risk_weighting_difference",
            "evidence_gap",
        }:
            raise ValueError(
                "financial_committee_view.financial_disagreements.disagreement_type must be "
                "true_disagreement, different_emphasis, risk_weighting_difference, or evidence_gap"
            )
        if not isinstance(item.get("topic"), str) or not item.get("topic", "").strip():
            raise ValueError("financial_committee_view.financial_disagreements.topic is required")
        if not isinstance(item.get("disagreement"), str) or not item.get("disagreement", "").strip():
            raise ValueError("financial_committee_view.financial_disagreements.disagreement is required")
        if not isinstance(item.get("financial_relevance"), str):
            raise ValueError("financial_committee_view.financial_disagreements.financial_relevance must be a string")
        if not isinstance(item.get("evidence_limit"), str):
            raise ValueError("financial_committee_view.financial_disagreements.evidence_limit must be a string")
    value["financial_disagreements"] = disagreements

    _validate_internal_terms_free(value, "financial_committee_view")

    referenced = _referenced_financial_terms(value)
    unsupported = sorted(
        term for term in referenced
        if term in STRICT_FINANCIAL_TERMS and term not in allowed_terms and term != "owner_earnings"
    )
    if unsupported:
        raise ValueError(
            "financial_committee_view references financial concepts not present in analyst outputs: "
            f"{unsupported}"
        )
    text_blob = "\n".join(_flatten_strings(value)).lower()
    for path, text in _iter_string_paths(value, path="financial_committee_view"):
        reference_type = classify_owner_earnings_reference(
            text,
            path=path,
            financial_context=owner_earnings_support,
        )
        if reference_type == "none":
            continue
        if (
            reference_type in {"positive_claim", "ambiguous"}
            and owner_earnings_support.get("owner_earnings_status") == "available_derived_precision_limited"
        ):
            lowered = _normalize_owner_earnings_text(text)
            if any(
                phrase in lowered
                for phrase in (
                    "derived owner earnings",
                    "owner earnings estimate",
                    "conservative fcf estimate",
                    "derived fcf estimate",
                    "approximate",
                    "precision is limited",
                    "maintenance versus growth capex split",
                    "maintenance/growth capex split",
                )
            ):
                schema_warnings.append(
                    f"{path} owner earnings reference allowed as derived precision-limited financial support."
                )
                continue
        if reference_type in {"question", "limitation", "neutral_reference"}:
            lowered = _normalize_owner_earnings_text(text)
            if (
                owner_earnings_support.get("owner_earnings_status") == "available_derived_precision_limited"
                and any(
                    phrase in lowered
                    for phrase in (
                        "maintenance versus growth capex split",
                        "maintenance/growth capex split",
                        "approximate",
                        "precision is limited",
                        "owner earnings estimate",
                    )
                )
            ):
                schema_warnings.append(
                    f"{path} owner earnings reference allowed as precision-limited derived estimate context."
                )
                continue
            if (
                owner_earnings_support.get("owner_earnings_limitation_supported")
                and not owner_earnings_support.get("owner_earnings_positive_claim_supported")
                and any(
                    owner_earnings_support.get(flag)
                    for flag in ("fcf_missing", "capex_missing", "payables_missing", "basis_unknown")
                )
            ):
                schema_warnings.append(
                    f"{path} owner earnings reference allowed as {reference_type} due to supported financial limitations."
                )
                continue
        if reference_type == "limitation":
            if not owner_earnings_support.get("owner_earnings_limitation_supported"):
                raise _owner_earnings_error(
                    path=path,
                    reference_type=reference_type,
                    owner_earnings_support=owner_earnings_support,
                    text=text,
                    message="financial_committee_view references owner earnings limitation without analyst support",
                )
            continue
        if reference_type == "positive_claim":
            if (
                owner_earnings_support.get("fcf_missing")
                or owner_earnings_support.get("capex_missing")
                or not owner_earnings_support.get("owner_earnings_positive_claim_supported")
            ):
                raise _owner_earnings_error(
                    path=path,
                    reference_type=reference_type,
                    owner_earnings_support=owner_earnings_support,
                    text=text,
                    message="financial_committee_view references positive owner earnings without analyst support",
                )
            continue
        raise _owner_earnings_error(
            path=path,
            reference_type=reference_type,
            owner_earnings_support=owner_earnings_support,
            text=text,
            message="financial_committee_view references ambiguous owner earnings language",
        )
    normalized_owner_text = _normalize_owner_earnings_text(text_blob)
    if "owner earnings" in normalized_owner_text and "owner_earnings" not in allowed_terms:
        # Path-level validation above has already accepted supported limitations. If the
        # term remains in the combined view without selected financial support, fail
        # only when no analyst limitation support exists.
        if not owner_earnings_support.get("owner_earnings_limitation_supported"):
            raise ValueError(
                "financial_committee_view references owner earnings without analyst support"
            )
    return value


def _validate_committee_v2_sections(
    parsed: Dict[str, Any],
    *,
    schema_warnings: List[str],
) -> None:
    company_slug = parsed.get("company_slug")
    if not isinstance(company_slug, str) or not company_slug.strip():
        raise ValueError("company_slug is required for committee_synthesis_v2")

    committee_view = parsed.get("committee_view")
    if committee_view is not None and committee_view not in V2_COMMITTEE_VIEW_VALUES:
        raise ValueError(
            "committee_view must be strong, reasonably_strong, mixed, weak, or insufficient_evidence"
        )
    committee_direction = parsed.get("committee_direction")
    if committee_direction is not None and committee_direction not in V2_COMMITTEE_DIRECTION_VALUES:
        raise ValueError(
            "committee_direction must be strengthening, weakening, stable, mixed, or unclear"
        )
    consensus_strength = parsed.get("consensus_strength")
    if consensus_strength is not None and consensus_strength not in V2_CONSENSUS_STRENGTH_VALUES:
        raise ValueError(
            "consensus_strength must be high, medium, low, fragmented, or insufficient_evidence"
        )

    def _validate_object_list(field_name: str, required_keys: Sequence[str]) -> None:
        value = parsed.get(field_name)
        if not isinstance(value, list):
            raise ValueError(f"{field_name} must be a list")
        for item in value:
            if not isinstance(item, dict):
                raise ValueError(f"{field_name} must contain objects")
            for key in required_keys:
                if key not in item or (isinstance(item.get(key), str) and not str(item.get(key)).strip()):
                    raise ValueError(f"{field_name}.{key} is required")

    def _validate_string_list(field_name: str) -> None:
        value = parsed.get(field_name)
        if not isinstance(value, list):
            raise ValueError(f"{field_name} must be a list")
        if any(not isinstance(item, str) for item in value):
            raise ValueError(f"{field_name} must contain strings")

    _validate_object_list(
        "strongest_shared_convictions",
        ["conclusion", "supporting_analysts", "supporting_evidence", "progression", "why_it_matters", "confidence"],
    )
    _validate_object_list(
        "major_disagreements",
        [
            "topic",
            "analysts_on_side_a",
            "side_a_view",
            "analysts_on_side_b",
            "side_b_view",
            "reason_for_disagreement",
            "evidence_causing_tension",
            "what_evidence_would_resolve_it",
            "investor_importance",
            "confidence",
        ],
    )
    _validate_object_list(
        "thesis_strengtheners",
        ["summary", "period", "source_streams", "supporting_analysts", "why_it_matters", "conviction_effect", "confidence"],
    )
    _validate_object_list(
        "thesis_weakeners",
        ["summary", "period", "source_streams", "supporting_analysts", "why_it_matters", "conviction_effect", "confidence"],
    )
    _validate_object_list(
        "unresolved_items",
        ["question", "why_it_matters", "affected_analysts", "affected_thesis_area", "evidence_needed", "current_confidence"],
    )
    _validate_object_list(
        "major_turning_points",
        ["period", "event", "before", "after", "why_it_matters", "affected_analysts", "conviction_effect", "confidence"],
    )
    _validate_object_list(
        "top_diligence_questions",
        ["rank", "question", "why_it_matters", "affected_analysts", "priority_reason", "evidence_needed"],
    )
    _validate_string_list("disagreement_explanations")
    _validate_string_list("what_would_change_the_view")

    for item in parsed.get("major_disagreements", []) or []:
        if item.get("disagreement_type") and item.get("disagreement_type") not in {
            "evidence_disagreement",
            "doctrine_weighting_difference",
            "time_horizon_difference",
            "uncertainty_tolerance_difference",
            "financial_vs_business_tension",
            "execution_vs_outcome_tension",
            "valuation_vs_quality_tension",
            "unresolved_data_gap",
        }:
            raise ValueError("major_disagreements.disagreement_type must be a recognized v2 disagreement type")
    for field_name in ("thesis_strengtheners", "thesis_weakeners", "major_turning_points"):
        for item in parsed.get(field_name, []) or []:
            if item.get("conviction_effect") and item.get("conviction_effect") not in {"strengthened", "weakened", "unchanged", "unclear"}:
                raise ValueError(f"{field_name}.conviction_effect must be strengthened, weakened, unchanged, or unclear")

    for field in ("financial_judgment", "business_quality_judgment", "management_judgment", "capital_allocation_judgment", "risk_judgment"):
        value = parsed.get(field)
        if not isinstance(value, dict):
            raise ValueError(f"{field} must be an object")
        for key in ("assessment", "direction", "strongest_evidence", "main_concern", "unresolved_issue", "confidence"):
            if key not in value or (isinstance(value.get(key), str) and not str(value.get(key)).strip()):
                raise ValueError(f"{field}.{key} is required")

    evidence_confidence = parsed.get("evidence_confidence")
    if not isinstance(evidence_confidence, dict):
        raise ValueError("evidence_confidence must be an object")
    if evidence_confidence.get("level") not in {"high", "medium", "low"}:
        raise ValueError("evidence_confidence.level must be high, medium, or low")
    if not isinstance(evidence_confidence.get("basis"), list) or any(
        not isinstance(item, str) for item in evidence_confidence.get("basis", [])
    ):
        raise ValueError("evidence_confidence.basis must be a list of strings")
    if not isinstance(evidence_confidence.get("limitations"), list) or any(
        not isinstance(item, str) for item in evidence_confidence.get("limitations", [])
    ):
        raise ValueError("evidence_confidence.limitations must be a list of strings")

    committee_summary = parsed.get("committee_summary")
    if not isinstance(committee_summary, str) or not committee_summary.strip():
        raise ValueError("committee_summary is required")
    if len(committee_summary.split()) < 40:
        schema_warnings.append(
            "committee_summary is compact; consider expanding committee narrative context if evidence remains rich."
        )


def validate_analyst_payload(payload: Dict[str, Any], *, analyst: str) -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"{analyst}_analysis.json must contain an object")
    missing = REQUIRED_ANALYST_FIELDS - set(payload.keys())
    if missing:
        raise ValueError(
            f"{analyst}_analysis.json missing required fields: {sorted(missing)}"
        )


def validate_committee_output(
    payload_text: Any,
    *,
    company: str,
    included_analysts: Sequence[str],
    missing_analysts: Sequence[str],
    excluded_analysts: Sequence[str],
    allowed_evidence_ids: Sequence[str],
    analyst_uncertainties: Dict[str, List[str]],
    included_analyst_payloads: Sequence[Dict[str, Any]] | None = None,
    mode: str = "final",
    allow_unresolved_ids: bool = False,
) -> Dict[str, Any]:
    if mode not in {"raw", "final"}:
        raise ValueError("mode must be 'raw' or 'final'")

    if isinstance(payload_text, dict):
        parsed = json.loads(json.dumps(payload_text, ensure_ascii=False))
    else:
        try:
            parsed = json.loads(payload_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Malformed JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    schema_warnings = _normalize_optional_string_list(parsed.get("schema_warnings"), "schema_warnings") if "schema_warnings" in parsed else []

    forbidden_key_paths = _find_forbidden_keys(parsed)
    if mode == "final" and forbidden_key_paths:
        raise ValueError(
            "committee synthesis contains forbidden internal fields: "
            f"{forbidden_key_paths}"
        )

    base_required_keys = FINAL_REQUIRED_TOP_LEVEL_KEYS if mode == "final" else RAW_REQUIRED_TOP_LEVEL_KEYS
    missing_keys = base_required_keys - set(parsed.keys())
    if missing_keys:
        raise ValueError(
            f"committee synthesis missing required keys: {sorted(missing_keys)}"
        )

    if not isinstance(parsed.get("company"), str) or not parsed["company"].strip():
        raise ValueError("company is required")
    analysis_mode = parsed.get("analysis_mode")
    if analysis_mode not in COMMITTEE_SYNTHESIS_MODES:
        raise ValueError("analysis_mode must be committee_synthesis_v1 or committee_synthesis_v2")

    required_keys = FINAL_REQUIRED_TOP_LEVEL_KEYS if analysis_mode == "committee_synthesis_v1" else FINAL_REQUIRED_TOP_LEVEL_KEYS | {
        "company_slug",
        "committee_view",
        "committee_direction",
        "consensus_strength",
        "strongest_shared_convictions",
        "major_disagreements",
        "disagreement_explanations",
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
    }
    if analysis_mode == "committee_synthesis_v2":
        missing_keys = required_keys - set(parsed.keys())
        if missing_keys:
            raise ValueError(
                f"committee synthesis missing required keys: {sorted(missing_keys)}"
            )

    allowed_analysts = set(EXPECTED_ANALYSTS)
    included = _normalize_string_list(
        parsed.get("analysts_considered"),
        "analysts_considered",
        schema_warnings=schema_warnings,
    )
    missing = _normalize_analyst_list_field(
        parsed.get("missing_analysts"),
        "missing_analysts",
        schema_warnings=schema_warnings,
    )
    excluded = _normalize_analyst_list_field(
        parsed.get("excluded_analysts"),
        "excluded_analysts",
        schema_warnings=schema_warnings,
    )
    years_considered = _normalize_string_list(
        parsed.get("years_considered"),
        "years_considered",
        schema_warnings=schema_warnings,
    )
    evidence_quality_notes = _normalize_string_list(
        parsed.get("evidence_quality_notes"),
        "evidence_quality_notes",
        schema_warnings=schema_warnings,
    )
    synthesis_limits = _normalize_string_list(
        parsed.get("synthesis_limits"),
        "synthesis_limits",
        schema_warnings=schema_warnings,
    )
    normalization = None
    if mode == "final":
        normalization = parsed.get("evidence_id_normalization")
        if not isinstance(normalization, dict):
            raise ValueError("evidence_id_normalization must be an object")
        if not isinstance(normalization.get("applied"), bool):
            raise ValueError("evidence_id_normalization.applied must be a boolean")
        if not isinstance(normalization.get("replacements"), list):
            raise ValueError("evidence_id_normalization.replacements must be a list")
        normalization["unresolved_ids"] = _normalize_optional_string_list(
            normalization.get("unresolved_ids"),
            "evidence_id_normalization.unresolved_ids",
        )

    for field_name, values in (
        ("analysts_considered", included),
        ("missing_analysts", missing),
        ("excluded_analysts", excluded),
    ):
        invalid = [value for value in values if value not in allowed_analysts]
        if invalid:
            raise ValueError(f"{field_name} contains invalid analysts: {sorted(set(invalid))}")

    if set(included) != set(included_analysts):
        raise ValueError(
            f"analysts_considered must match included analysts: {list(included_analysts)}"
        )
    if set(missing) != set(missing_analysts):
        raise ValueError(
            f"missing_analysts must match missing analysts: {list(missing_analysts)}"
        )
    if set(excluded) != set(excluded_analysts):
        raise ValueError(
            f"excluded_analysts must match excluded analysts: {list(excluded_analysts)}"
        )
    parsed["schema_warnings"] = schema_warnings

    if not isinstance(parsed.get("generated_at"), str) or not parsed["generated_at"].strip():
        raise ValueError("generated_at is required")

    overall = parsed.get("overall_committee_view")
    if not isinstance(overall, dict):
        raise ValueError("overall_committee_view must be an object")
    for field in ("summary", "dominant_tension"):
        if not isinstance(overall.get(field), str) or not overall[field].strip():
            raise ValueError(f"overall_committee_view.{field} is required")
    if overall.get("confidence") not in {"low", "medium", "high"}:
        raise ValueError("overall_committee_view.confidence must be low, medium, or high")

    allowed_financial_terms = _collect_allowed_financial_terms(
        included_analyst_payloads or []
    )
    # CRITICAL FIX: Use committee_financial_truth from synthesis (already finalized by synthesizer).
    # QA validates consistency against this truth — does NOT re-derive owner_earnings_support from analysts
    # when truth_detected=True.  When truth_detected=False (no financial truth pack), fall back to the
    # analyst-text registry so that honest limitation language in the committee view is not hard-blocked.
    # Positive claims are never granted by the registry path (registry.positive_claim_supported stays False
    # unless analysts explicitly made a positive owner-earnings assertion, which would be a real failure).
    financial_manifest = parsed.get("financial_warning_manifest") or {}
    committee_truth = financial_manifest.get("committee_financial_truth") or parsed.get("committee_financial_truth") or {}
    owner_earnings_support = {}
    if isinstance(committee_truth, dict) and committee_truth.get("truth_detected"):
        owner_earnings_support = {
            "fcf_missing": committee_truth.get("fcf_missing"),
            "capex_missing": committee_truth.get("capex_missing"),
            "payables_available": committee_truth.get("payables_available"),
            "basis_status": committee_truth.get("basis_status"),
            "owner_earnings_status": committee_truth.get("owner_earnings_status"),
            "owner_earnings_limitation_supported": committee_truth.get("owner_earnings_status") in {"available_explicit", "available_derived_precision_limited"},
        }
    elif included_analyst_payloads:
        # No financial truth pack — scan analyst text to determine whether owner earnings
        # limitations are grounded in what analysts actually reported.
        _registry = _owner_earnings_support_registry(included_analyst_payloads)
        owner_earnings_support = {
            "fcf_missing": _registry.get("fcf_missing", False),
            "capex_missing": _registry.get("capex_missing", False),
            "payables_missing": _registry.get("payables_missing", False),
            "basis_unknown": _registry.get("basis_unknown", False),
            "owner_earnings_status": "missing",
            "owner_earnings_limitation_supported": _registry.get("owner_earnings_limitation_supported", False),
            "owner_earnings_positive_claim_supported": _registry.get("owner_earnings_positive_claim_supported", False),
        }
    expected_financial_usage = _expected_financials_used(
        included_analyst_payloads or []
    )
    expected_basis_usage = _expected_basis_used(
        included_analyst_payloads or []
    )
    parsed["financial_committee_view"] = _validate_financial_committee_view(
        parsed.get("financial_committee_view"),
        allowed_terms=allowed_financial_terms,
        owner_earnings_support=owner_earnings_support,
        expected_financials_used=expected_financial_usage,
        expected_basis_used=expected_basis_usage,
        schema_warnings=schema_warnings,
    )

    if analysis_mode == "committee_synthesis_v2":
        _validate_committee_v2_sections(parsed, schema_warnings=schema_warnings)

    allowed_evidence_set = set(allowed_evidence_ids)

    areas_of_agreement = normalize_committee_field(
        "areas_of_agreement",
        parsed.get("areas_of_agreement"),
        allowed_evidence_ids=allowed_evidence_set,
        schema_warnings=schema_warnings,
    )
    parsed["areas_of_agreement"] = areas_of_agreement

    areas_of_disagreement = normalize_committee_field(
        "areas_of_disagreement",
        parsed.get("areas_of_disagreement"),
        allowed_evidence_ids=allowed_evidence_set,
        schema_warnings=schema_warnings,
    )
    for item in areas_of_disagreement:
        if mode == "final":
            if "disagreement_type" not in item:
                raise ValueError("areas_of_disagreement item missing required keys: ['disagreement_type']")
            if item.get("disagreement_type") not in {
                "true_disagreement",
                "different_emphasis",
                "risk_weighting_difference",
            }:
                raise ValueError(
                    "areas_of_disagreement.disagreement_type must be "
                    "true_disagreement, different_emphasis, or risk_weighting_difference"
                )
    parsed["areas_of_disagreement"] = areas_of_disagreement

    parsed["strongest_positive_signals"] = normalize_committee_field(
        "strongest_positive_signals",
        parsed.get("strongest_positive_signals"),
        allowed_evidence_ids=allowed_evidence_set,
        schema_warnings=schema_warnings,
    )

    parsed["most_important_risks"] = normalize_committee_field(
        "most_important_risks",
        parsed.get("most_important_risks"),
        allowed_evidence_ids=allowed_evidence_set,
        schema_warnings=schema_warnings,
    )

    # CRITICAL FIX: Committee Brief owns synthesis; QA validates without re-deriving.
    # The synthesizer already produced grounded critical_unknowns. We only VALIDATE
    # that they are properly grounded in the analyst uncertainty registry — we do NOT
    # re-derive or generate new ones.
    uncertainty_registry, uncertainty_registry_by_id = _build_uncertainty_registry(
        included_analyst_payloads or []
    )
    critical_unknowns = parsed.get("critical_unknowns", [])
    if not critical_unknowns:
        # No critical_unknowns present in synthesis — this is a synthesis gap.
        # Validator flags it via schema_warnings but does NOT generate fallback entries.
        schema_warnings.append(
            "critical_unknowns absent from synthesis; expected grounded entries from synthesizer."
        )
        critical_unknowns = []
    else:
        critical_unknowns = _normalize_critical_unknowns(
            critical_unknowns,
            registry=uncertainty_registry,
            registry_by_id=uncertainty_registry_by_id,
            schema_warnings=schema_warnings,
        )
        # Validate grounding — raise if ungrounded, but do not generate.
        critical_unknowns = _validate_object_list(
            critical_unknowns,
            "critical_unknowns",
            ("unknown", "raised_by", "why_it_matters", "source_uncertainty_ids", "evidence_limit"),
        )
        for item in critical_unknowns:
            raised_by = _normalize_string_list(
                item.get("raised_by"),
                "critical_unknowns.raised_by",
                schema_warnings=schema_warnings,
            )
            invalid_analysts = [analyst for analyst in raised_by if analyst not in EXPECTED_ANALYSTS]
            if invalid_analysts:
                raise ValueError(f"critical_unknowns.raised_by contains invalid analysts: {invalid_analysts}")
            item["raised_by"] = raised_by
            source_ids = _normalize_string_list(
                item.get("source_uncertainty_ids"),
                "critical_unknowns.source_uncertainty_ids",
                schema_warnings=schema_warnings,
            )
            invalid_ids = [item_id for item_id in source_ids if item_id not in uncertainty_registry_by_id]
            if invalid_ids:
                raise ValueError(
                    "critical_unknowns contains source_uncertainty_ids not present in analyst uncertainty registry: "
                    f"{sorted(set(invalid_ids))}"
                )
            if not source_ids:
                matches = _match_unknown_to_registry(
                    item.get("unknown", ""),
                    raised_by=raised_by,
                    registry=uncertainty_registry,
                )
                if not matches:
                    raise ValueError(
                        "critical_unknowns must be grounded in analyst uncertainty registry"
                    )
                source_ids = [match["uncertainty_id"] for match in matches]
                item["source_uncertainty_ids"] = source_ids
                if not raised_by:
                    raised_by = sorted({match["analyst"] for match in matches})
                    item["raised_by"] = raised_by
                schema_warnings.append(
                    "critical_unknowns source_uncertainty_ids were inferred from analyst uncertainty registry."
                )
            if not _match_unknown_to_registry(
                item.get("unknown", ""),
                raised_by=raised_by,
                registry=[uncertainty_registry_by_id[item_id] for item_id in source_ids],
            ):
                raise ValueError(
                    "critical_unknowns must be grounded in analyst uncertainty registry"
                )
            source_text = " ".join(uncertainty_registry_by_id[item_id]["text"] for item_id in source_ids)
            if _tokenize(item.get("unknown", "")).isdisjoint(_tokenize(source_text)):
                raise ValueError(
                    "critical_unknowns must be grounded in analyst uncertainty registry"
                )
            item["source_uncertainty_ids"] = source_ids
            if not isinstance(item.get("evidence_limit"), str):
                raise ValueError("critical_unknowns.evidence_limit must be a string")

    parsed["investigation_questions"] = normalize_committee_field(
        "investigation_questions",
        parsed.get("investigation_questions"),
        allowed_evidence_ids=allowed_evidence_set,
        schema_warnings=schema_warnings,
    )

    parsed["evidence_ids"] = _validate_normalized_evidence_ids(
        parsed.get("evidence_ids"),
        "evidence_ids",
        allowed=allowed_evidence_set,
    )
    manifest_sources: List[str] = []
    for analyst_payload in included_analyst_payloads or []:
        manifest_sources.extend(
            str(item or "")
            for item in (analyst_payload.get("financial_warnings_carried_forward") or [])
        )
        assessment = analyst_payload.get("financial_assessment") or {}
        if isinstance(assessment, dict):
            manifest_sources.extend(
                str(item or "")
                for item in (assessment.get("financial_warnings_carried_forward") or [])
            )
    manifest_blob = " ".join(manifest_sources).lower()
    committee_financial_blob = "\n".join(
        _flatten_strings(parsed.get("financial_committee_view", {}))
    ).lower()
    if (
        ("free cash flow" in manifest_blob or "fcf" in manifest_blob)
        and "free cash flow" not in committee_financial_blob
        and "fcf" not in committee_financial_blob
        and not (
            owner_earnings_support.get("owner_earnings_limitation_supported")
            and _owner_earnings_assessment_context_present(committee_financial_blob)
        )
    ):
        raise ValueError(
            "major financial warning from analyst inputs was not carried forward: free cash flow missing"
        )
    if "capex" in manifest_blob and "capex" not in committee_financial_blob:
        raise ValueError(
            "major financial warning from analyst inputs was not carried forward: capex missing"
        )
    if ("basis unknown" in manifest_blob or "basis unclear" in manifest_blob) and "basis" not in committee_financial_blob:
        raise ValueError(
            "major financial warning from analyst inputs was not carried forward: basis unknown"
        )
    parsed["analysts_considered"] = included
    parsed["missing_analysts"] = missing
    parsed["excluded_analysts"] = excluded
    parsed["years_considered"] = years_considered
    parsed["evidence_quality_notes"] = evidence_quality_notes
    parsed["synthesis_limits"] = synthesis_limits
    parsed["company"] = company
    parsed["critical_unknowns"] = critical_unknowns
    if mode == "final":
        if normalization["unresolved_ids"] and not allow_unresolved_ids:
            raise ValueError(
                "evidence_id_normalization.unresolved_ids must be empty after committee cleanup"
            )
        parsed["evidence_id_normalization"] = normalization

    _validate_forbidden_language(parsed)
    return parsed
