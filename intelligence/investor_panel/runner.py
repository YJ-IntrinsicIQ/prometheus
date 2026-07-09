from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from knowledge.ai import get_llm

from .doctrine_registry import InvestorDoctrineRegistry


PCIM_FILE = "pcim_v1.json"
ALLOWED_RATINGS = {"strong", "mixed", "weak", "insufficient_evidence"}
DEFAULT_MAX_ITEMS_PER_SECTION = 25
DEFAULT_MAX_RISKS = 20
DEFAULT_MAX_CAPITAL_ALLOCATION_ITEMS = 20
DEFAULT_MAX_EVIDENCE_EXCERPT_CHARS = 300
DEFAULT_MAX_TOTAL_PROMPT_CHARS = 120_000
MIN_MAX_ITEMS_PER_SECTION = 3
MIN_MAX_RISKS = 3
MIN_MAX_CAPITAL_ALLOCATION_ITEMS = 3
MIN_MAX_EVIDENCE_EXCERPT_CHARS = 120
COMPACTION_REASONING_LIMIT = "Input PCIM was compacted for token budget; evidence_ids preserved."
DROP_KEYS = {
    "source_chunk",
    "raw_text",
    "full_text",
    "document_text",
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
    "evidence_ids",
    "supporting_pcim_sections",
    "reasoning_limits",
    "generated_at",
}


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


def _prompt_compaction_limits() -> Dict[str, int]:
    return {
        "max_items_per_section": _resolve_positive_int_env(
            "INVESTOR_PANEL_MAX_ITEMS_PER_SECTION",
            DEFAULT_MAX_ITEMS_PER_SECTION,
        ),
        "max_risks": _resolve_positive_int_env(
            "INVESTOR_PANEL_MAX_RISKS",
            DEFAULT_MAX_RISKS,
        ),
        "max_capital_allocation_items": DEFAULT_MAX_CAPITAL_ALLOCATION_ITEMS,
        "max_evidence_excerpt_chars": _resolve_positive_int_env(
            "INVESTOR_PANEL_MAX_EVIDENCE_EXCERPT_CHARS",
            DEFAULT_MAX_EVIDENCE_EXCERPT_CHARS,
        ),
        "max_total_prompt_chars": DEFAULT_MAX_TOTAL_PROMPT_CHARS,
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
    rating = _rating_for_sections(doctrine, pcim, consumed_sections, evidence_ids)

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
        "evidence_ids": evidence_ids,
        "supporting_pcim_sections": consumed_sections,
        "reasoning_limits": [
            "Dry-run/deterministic scaffold mode does not perform analyst-style LLM reasoning.",
            "Assessment text is structural and derived from doctrine plus PCIM availability only.",
        ],
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
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, int]], bool]:
    selected_pcim = _selected_pcim_view(pcim, sections)
    compacted: Dict[str, Any] = {}
    stats: Dict[str, Dict[str, int]] = {}
    truncated = False

    for section, value in selected_pcim.items():
        before = _count_compactable_items(value)
        compacted_value, section_truncated = _compact_value_for_prompt(
            value,
            section=section,
            limits=limits,
            current_key=section,
        )
        after = _count_compactable_items(compacted_value)
        compacted[section] = compacted_value
        stats[section] = {"before": before, "after": after}
        truncated = truncated or section_truncated or after < before

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
    if next_limits == limits:
        return None
    return next_limits


def _prepare_compact_prompt_pack(
    pcim: Dict[str, Any],
    sections: List[str],
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, int]], Dict[str, int], bool]:
    limits = _prompt_compaction_limits()
    while True:
        compacted_pcim, stats, truncated = _build_compact_pcim_view(pcim, sections, limits)
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
) -> Tuple[str, Dict[str, Any], Dict[str, Dict[str, int]], Dict[str, int], bool]:
    compact_pcim, section_stats, limits_used, input_compacted = _prepare_compact_prompt_pack(
        pcim,
        sections,
    )
    prompt = _build_llm_prompt(
        doctrine=doctrine,
        company=company,
        pcim_path=pcim_path,
        selected_pcim=compact_pcim,
        allowed_sections=sections,
    )
    while len(prompt) > limits_used["max_total_prompt_chars"]:
        next_limits = _shrink_limits(limits_used)
        if next_limits is None:
            break
        limits_used = next_limits
        compact_pcim, section_stats, next_truncated = _build_compact_pcim_view(
            pcim,
            sections,
            limits_used,
        )
        input_compacted = input_compacted or next_truncated
        prompt = _build_llm_prompt(
            doctrine=doctrine,
            company=company,
            pcim_path=pcim_path,
            selected_pcim=compact_pcim,
            allowed_sections=sections,
        )
    return prompt, compact_pcim, section_stats, limits_used, input_compacted


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
        "evidence_ids": ["string"],
        "supporting_pcim_sections": allowed_sections,
        "reasoning_limits": ["string"],
    }


def _build_system_prompt() -> str:
    return (
        "You are an investor-panel analyst inside Prometheus. "
        "Reason only from the supplied PCIM sections and doctrine configuration. "
        "Do not use outside knowledge, do not invent evidence, and do not make buy/sell/hold recommendations. "
        "Return exactly one valid JSON object matching the requested schema."
    )


def _build_llm_prompt(
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    selected_pcim: Dict[str, Any],
    allowed_sections: List[str],
) -> str:
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
            "- Distinguish evidence found from judgment inferred.",
            "- Cite evidence_ids for every major finding, red flag, and uncertainty when available.",
            "- If evidence_ids are unavailable, mention that in reasoning_limits.",
            "- If evidence is missing or conflicting, say so explicitly.",
            "- Do not introduce facts, metrics, risks, or conclusions not present in selected PCIM.",
            "- Do not claim the historical investor personally said anything here.",
            "- Do not make valuation conclusions unless the supplied PCIM directly supports them.",
            "- Rating must reflect evidence strength, consistency, red flags, and uncertainty.",
            "- Do not rate strong merely because required PCIM sections are present.",
            "- Prefer the most material 3-7 findings rather than listing everything.",
            "- Use plain investor language in assessment text where possible; avoid repeating internal PCIM labels unless needed for precision.",
            "- Distinguish clearly between positive evidence, red flags, and missing evidence that limits confidence.",
            "- Do not treat dividends, related-party advances, or governance ambiguity as automatic condemnation without context from the supplied PCIM.",
            "- supporting_pcim_sections must contain only values from the allowed list shown below.",
            "- Do not include any PCIM section not shown in the allowed list, even if it seems relevant.",
            "- If you wish you had another section, mention it under open_uncertainties or reasoning_limits, not under supporting_pcim_sections.",
            "",
            "Allowed supporting_pcim_sections:",
            json.dumps(allowed_sections, indent=2, ensure_ascii=False),
            "",
            "Doctrine primary focus:",
            json.dumps(doctrine.get("primary_focus", []), indent=2, ensure_ascii=False),
            "",
            "Canonical principles:",
            json.dumps(doctrine.get("canonical_principles", []), indent=2, ensure_ascii=False),
            "",
            "Canonical questions:",
            json.dumps(doctrine.get("canonical_questions", []), indent=2, ensure_ascii=False),
            "",
            "Red flags to watch:",
            json.dumps(doctrine.get("red_flags", []), indent=2, ensure_ascii=False),
            "",
            "Uncertainty rules:",
            json.dumps(doctrine.get("uncertainty_rules", []), indent=2, ensure_ascii=False),
            "",
            "Output contract:",
            json.dumps(doctrine.get("output_contract", {}), indent=2, ensure_ascii=False),
            "",
            "Required JSON shape:",
            json.dumps(_llm_output_template(doctrine, allowed_sections), indent=2, ensure_ascii=False),
            "",
            "Selected compact PCIM sections:",
            json.dumps(selected_pcim, indent=2, ensure_ascii=False),
        ]
    )


def _normalize_string_list(value: Any, field: str) -> List[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    normalized = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain non-empty strings")
        normalized.append(item.strip())
    return normalized


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


def _normalize_optional_evidence_ids(value: Any, field: str) -> List[str]:
    if value is None:
        return []
    return _normalize_string_list(value, f"{field}.evidence_ids")


def _validate_llm_panel_output(
    payload_text: str,
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    pcim_version: Any,
    consumed_sections: List[str],
    allowed_evidence_ids: List[str],
) -> Dict[str, Any]:
    try:
        parsed = json.loads(payload_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")

    assessment = parsed.get("assessment")
    if not isinstance(assessment, dict):
        raise ValueError("assessment must be an object")

    normalized_assessment = {}
    for key in _required_assessment_keys(doctrine):
        value = assessment.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"assessment.{key} is required")
        normalized_assessment[key] = value.strip()

    rating = parsed.get("rating")
    if not isinstance(rating, str) or rating not in ALLOWED_RATINGS:
        raise ValueError("rating must be one of strong, mixed, weak, insufficient_evidence")

    key_findings, finding_evidence = _normalize_findings(parsed.get("key_findings"), "key_findings")
    red_flags, red_flag_evidence = _normalize_findings(parsed.get("red_flags"), "red_flags")
    open_uncertainties, uncertainty_evidence = _normalize_findings(
        parsed.get("open_uncertainties"), "open_uncertainties"
    )
    reasoning_limits = _normalize_string_list(parsed.get("reasoning_limits"), "reasoning_limits")

    supporting_pcim_sections = _normalize_string_list(
        parsed.get("supporting_pcim_sections"), "supporting_pcim_sections"
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

    supplied_evidence_ids = _normalize_string_list(parsed.get("evidence_ids"), "evidence_ids")
    merged_evidence_ids: List[str] = []
    for evidence_id in supplied_evidence_ids + finding_evidence + red_flag_evidence + uncertainty_evidence:
        if evidence_id in allowed_evidence_ids and evidence_id not in merged_evidence_ids:
            merged_evidence_ids.append(evidence_id)

    return {
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
        "evidence_ids": merged_evidence_ids,
        "supporting_pcim_sections": supporting_pcim_sections,
        "reasoning_limits": reasoning_limits,
        "generated_at": utc_now(),
    }


def _analysis_filename(doctrine_id: str, analysis_mode: str) -> str:
    base = f"{_safe_slug(doctrine_id)}_analysis"
    if analysis_mode == "deterministic_scaffold":
        return f"{base}_dry_run.json"
    return f"{base}.json"


class InvestorPanelRunner:
    def __init__(
        self,
        company: str,
        companies_root: Path | str = Path("companies"),
        doctrines_dir: Path | str = Path(__file__).resolve().parent / "doctrines",
    ):
        self.company = company
        self.companies_root = Path(companies_root)
        self.company_root = self.companies_root / company
        self.company_memory_dir = self.company_root / "company_memory"
        self.output_dir = self.company_memory_dir / "investor_panel"
        self.registry = InvestorDoctrineRegistry(doctrines_dir)
        self.llm = get_llm()

    def _load_pcim(self) -> Tuple[Path, Dict[str, Any]]:
        pcim_path = self.company_memory_dir / PCIM_FILE
        pcim = _load_json(pcim_path)
        if not pcim:
            raise FileNotFoundError(f"PCIM not found or unreadable: {pcim_path}")
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
        prompt, _compact_pcim, section_stats, limits_used, input_compacted = _build_compact_prompt(
            doctrine=doctrine,
            company=self.company,
            pcim_path=pcim_path,
            pcim=pcim,
            sections=consumed_sections,
        )
        allowed_evidence_ids = _collect_section_evidence_ids(pcim, consumed_sections)
        prompt_chars = len(prompt)
        prompt_tokens = _estimate_prompt_tokens(prompt)
        print(
            "[INVESTOR PANEL] "
            f"analyst={doctrine['doctrine_id']} "
            f"sections={consumed_sections} "
            f"prompt_chars={prompt_chars} "
            f"approx_tokens={prompt_tokens} "
            f"item_counts={section_stats} "
            f"limits={limits_used}"
        )

        response = self.llm.generate(
            prompt=prompt,
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
            consumed_sections=consumed_sections,
            allowed_evidence_ids=allowed_evidence_ids,
        )
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
        prompt, _compact_pcim, section_stats, limits_used, input_compacted = _build_compact_prompt(
            doctrine=doctrine,
            company=self.company,
            pcim_path=pcim_path,
            pcim=pcim,
            sections=consumed_sections,
        )
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

            filename = _analysis_filename(
                doctrine_id=doctrine["doctrine_id"],
                analysis_mode=payload["analysis_mode"],
            )
            written_paths[filename] = _write_json(self.output_dir / filename, payload)
            analyses.append(
                {
                    "doctrine_id": doctrine["doctrine_id"],
                    "output_file": filename,
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
