from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Sequence, Set

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
    "evidence_grounding_warnings",
    "reasoning_limits",
    "user_facing_brief",
}
RAW_REQUIRED_TOP_LEVEL_KEYS = {
    "company",
    "analysis_mode",
    "analysts_considered",
    "missing_analysts",
    "excluded_analysts",
    "years_considered",
    "overall_committee_view",
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


def _normalize_string_list(value: Any, field: str) -> List[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    normalized: List[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain non-empty strings")
        normalized.append(item.strip())
    return normalized


def _normalize_optional_string_list(value: Any, field: str) -> List[str]:
    if value is None:
        return []
    return _normalize_string_list(value, field)


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


def _validate_forbidden_language(payload: Dict[str, Any]) -> None:
    text_blob = "\n".join(_flatten_strings(payload))
    if "source_chunk" in text_blob:
        raise ValueError("committee synthesis must not include raw source_chunk data")
    matches = find_forbidden_recommendation_language(text_blob)
    if matches:
        raise ValueError(
            f'committee synthesis contains forbidden language: "{matches[0]["matched_text"]}"'
        )


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

    required_keys = FINAL_REQUIRED_TOP_LEVEL_KEYS if mode == "final" else RAW_REQUIRED_TOP_LEVEL_KEYS
    missing_keys = required_keys - set(parsed.keys())
    if missing_keys:
        raise ValueError(
            f"committee synthesis missing required keys: {sorted(missing_keys)}"
        )

    if not isinstance(parsed.get("company"), str) or not parsed["company"].strip():
        raise ValueError("company is required")
    if parsed["analysis_mode"] != "committee_synthesis_v1":
        raise ValueError("analysis_mode must be committee_synthesis_v1")

    allowed_analysts = set(EXPECTED_ANALYSTS)
    included = _normalize_string_list(parsed.get("analysts_considered"), "analysts_considered")
    missing = _normalize_string_list(parsed.get("missing_analysts"), "missing_analysts")
    excluded = _normalize_string_list(parsed.get("excluded_analysts"), "excluded_analysts")
    years_considered = _normalize_string_list(parsed.get("years_considered"), "years_considered")
    evidence_quality_notes = _normalize_string_list(
        parsed.get("evidence_quality_notes"), "evidence_quality_notes"
    )
    synthesis_limits = _normalize_string_list(parsed.get("synthesis_limits"), "synthesis_limits")
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

    allowed_evidence_set = set(allowed_evidence_ids)

    for item in _validate_object_list(
        parsed.get("areas_of_agreement"),
        "areas_of_agreement",
        ("theme", "analysts", "summary", "evidence_ids"),
    ):
        _normalize_string_list(item.get("analysts"), "areas_of_agreement.analysts")
        item["evidence_ids"] = _validate_normalized_evidence_ids(
            item.get("evidence_ids"),
            "areas_of_agreement.evidence_ids",
            allowed=allowed_evidence_set,
        )

    for item in _validate_object_list(
        parsed.get("areas_of_disagreement"),
        "areas_of_disagreement",
        (
            "theme",
            "analysts_positive_or_less_concerned",
            "analysts_cautious_or_negative",
            "summary",
            "why_it_matters",
            "evidence_ids",
        ),
    ):
        _normalize_string_list(
            item.get("analysts_positive_or_less_concerned"),
            "areas_of_disagreement.analysts_positive_or_less_concerned",
        )
        _normalize_string_list(
            item.get("analysts_cautious_or_negative"),
            "areas_of_disagreement.analysts_cautious_or_negative",
        )
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
        item["evidence_ids"] = _validate_normalized_evidence_ids(
            item.get("evidence_ids"),
            "areas_of_disagreement.evidence_ids",
            allowed=allowed_evidence_set,
        )

    for item in _validate_object_list(
        parsed.get("strongest_positive_signals"),
        "strongest_positive_signals",
        ("signal", "supported_by", "summary", "evidence_ids"),
    ):
        _normalize_string_list(item.get("supported_by"), "strongest_positive_signals.supported_by")
        item["evidence_ids"] = _validate_normalized_evidence_ids(
            item.get("evidence_ids"),
            "strongest_positive_signals.evidence_ids",
            allowed=allowed_evidence_set,
        )

    for item in _validate_object_list(
        parsed.get("most_important_risks"),
        "most_important_risks",
        ("risk", "raised_by", "summary", "severity", "evidence_ids"),
    ):
        _normalize_string_list(item.get("raised_by"), "most_important_risks.raised_by")
        if item.get("severity") not in {"low", "medium", "high", "uncertain"}:
            raise ValueError(
                "most_important_risks.severity must be low, medium, high, or uncertain"
            )
        item["evidence_ids"] = _validate_normalized_evidence_ids(
            item.get("evidence_ids"),
            "most_important_risks.evidence_ids",
            allowed=allowed_evidence_set,
        )

    critical_unknowns = _validate_object_list(
        parsed.get("critical_unknowns"),
        "critical_unknowns",
        ("unknown", "raised_by", "why_it_matters"),
    )
    for item in critical_unknowns:
        raised_by = _normalize_string_list(item.get("raised_by"), "critical_unknowns.raised_by")
        unknown_tokens = _tokenize(item.get("unknown", ""))
        if raised_by and unknown_tokens:
            source_text = " ".join(
                " ".join(analyst_uncertainties.get(analyst, []))
                for analyst in raised_by
            )
            source_tokens = _tokenize(source_text)
            if unknown_tokens.isdisjoint(source_tokens):
                raise ValueError(
                    "critical_unknowns must be grounded in analyst open_uncertainties"
                )

    for item in _validate_object_list(
        parsed.get("investigation_questions"),
        "investigation_questions",
        ("question", "reason", "linked_unknown_or_risk"),
    ):
        for field in ("question", "reason", "linked_unknown_or_risk"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"investigation_questions.{field} is required")

    parsed["evidence_ids"] = _validate_normalized_evidence_ids(
        parsed.get("evidence_ids"),
        "evidence_ids",
        allowed=allowed_evidence_set,
    )
    parsed["analysts_considered"] = included
    parsed["missing_analysts"] = missing
    parsed["excluded_analysts"] = excluded
    parsed["years_considered"] = years_considered
    parsed["evidence_quality_notes"] = evidence_quality_notes
    parsed["synthesis_limits"] = synthesis_limits
    parsed["company"] = company
    if mode == "final":
        if normalization["unresolved_ids"] and not allow_unresolved_ids:
            raise ValueError(
                "evidence_id_normalization.unresolved_ids must be empty after committee cleanup"
            )
        parsed["evidence_id_normalization"] = normalization

    _validate_forbidden_language(parsed)
    return parsed
