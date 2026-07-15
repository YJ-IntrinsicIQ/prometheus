from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from knowledge.ai import get_llm
from knowledge.ai.input_packs import (
    build_llm_input_pack,
    call_llm_with_input_pack,
    render_llm_input_pack,
    resolve_stage_token_budget,
)

from .briefs import LENS_CONFIG, validate_user_facing_brief
from .doctrine_registry import InvestorDoctrineRegistry
from .evidence_grounding import (
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
    "historical_context_used",
    "years_considered",
    "supporting_pcim_sections",
    "evidence_id_normalization",
    "evidence_grounding_status",
    "evidence_grounding_warnings",
    "reasoning_limits",
    "user_facing_brief",
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
    stage_budget = resolve_stage_token_budget("investor_panel_analyst")
    compact_pcim, section_stats, limits_used, input_compacted = _prepare_compact_prompt_pack(
        pcim,
        sections,
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
    while (
        len(prompt) > limits_used["max_total_prompt_chars"]
        or _estimate_prompt_tokens(prompt) > stage_budget
    ):
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
    return prompt, compact_pcim, section_stats, limits_used, input_compacted


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
    return build_llm_input_pack(
        stage="investor_panel_analyst",
        purpose=f"Produce doctrine-bound investor analysis for {doctrine['doctrine_id']} from declared PCIM sections only.",
        company=company,
        year=None,
        selected_input={"selected_pcim": compact_pcim},
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
            "include_short_excerpts": True,
            "include_source_chunks": False,
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
        "evidence_ids": ["string"],
        "historical_context_used": True,
        "years_considered": ["fy24", "fy25"],
        "supporting_pcim_sections": allowed_sections,
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


def _build_llm_prompt(
    doctrine: Dict[str, Any],
    company: str,
    pcim_path: Path,
    llm_input_pack: Dict[str, Any],
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
            "- Return one valid JSON object containing both the internal analysis fields and user_facing_brief.",
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
            "- Use multi_year_inputs only as historical context when that section is provided.",
            "- Treat two-year trends as provisional unless the supplied evidence clearly supports a stronger claim.",
            "- Do not infer promise fulfillment unless it is explicitly shown in the supplied evidence.",
            "- Treat not_detected_this_year as absence of detection, not confirmed discontinuation.",
            "- Use recurring risks and worsening risks when relevant to the doctrine, but mention limitations when history is thin.",
            "- Do not overstate strategy shifts from deterministic theme matching alone.",
            "- user_facing_brief must not mention PCIM, evidence_ids, analysis_mode, sections_consumed, evidence_map, or reasoning_limits.",
            "- user_facing_brief must not contain evidence ID patterns like ev_ and must not contain buy/sell/hold recommendation language.",
            "- user_facing_brief should use simple, serious investor language and preserve the analyst's school of thought.",
            "- user_facing_brief must be a faithful summary of the internal analysis, not a second analysis.",
            "- user_facing_brief must not introduce new facts, risks, positives, or conclusions absent from the internal analysis.",
            "- user_facing_brief bullets should be concise: max 5 bullets per list, one sentence each.",
            "- user_facing_brief bottom_line should clearly reflect the rating/confidence level without using buy/sell/hold language.",
            "- Before returning JSON, self-check user_facing_brief and remove all internal system terms.",
            "- In user_facing_brief, never say PCIM. Say 'available evidence', 'available disclosures', or 'provided evidence' instead.",
            "- In user_facing_brief, never say evidence_ids. Say 'supporting evidence' instead.",
            "- In user_facing_brief, never say sections, evidence_map, analysis_mode, or reasoning_limits.",
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
            "Historical-context guidance for this analyst:",
            json.dumps(
                {
                    "graham": "Use multi_year_inputs to assess recurring financial or risk concerns, worsening liquidity, capital-allocation pattern, and missing cash-flow evidence.",
                    "buffett": "Use multi_year_inputs to assess consistency of business direction, capital-allocation pattern, repeated themes, and durability of business quality.",
                    "fisher": "Use multi_year_inputs to assess management ambition, execution continuity, product or R&D promises, and whether growth claims are followed through.",
                    "munger": "Use multi_year_inputs to assess incentives, governance ambiguity, recurring risks, related-party or internal-control or regulatory issues, and avoidable mistakes.",
                    "lynch": "Use multi_year_inputs to assess whether the story remains simple and consistent, whether growth matches observable evidence, and whether hype is increasing.",
                }.get(doctrine["doctrine_id"], ""),
                indent=2,
                ensure_ascii=False,
            ),
            "",
            "Output contract:",
            json.dumps(doctrine.get("output_contract", {}), indent=2, ensure_ascii=False),
            "",
            "Required JSON shape:",
            json.dumps(_llm_output_template(doctrine, allowed_sections), indent=2, ensure_ascii=False),
            "",
            "Selected compact PCIM sections:",
            render_llm_input_pack(llm_input_pack, include_policy=False),
            "User-facing wording replacements:",
            json.dumps({
                "PCIM": "available evidence",
                "evidence_ids": "supporting evidence",
                "sections_consumed": "materials reviewed",
                "reasoning_limits": "limitations",
                "evidence_map": "supporting evidence"
            }, indent=2, ensure_ascii=False),
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

    key_findings, finding_evidence, key_finding_map = _normalize_findings_with_map(parsed.get("key_findings"), "key_findings")
    red_flags, red_flag_evidence, red_flag_map = _normalize_findings_with_map(parsed.get("red_flags"), "red_flags")
    open_uncertainties, uncertainty_evidence, uncertainty_map = _normalize_findings_with_map(
        parsed.get("open_uncertainties"), "open_uncertainties"
    )
    reasoning_limits = _normalize_string_list(parsed.get("reasoning_limits"), "reasoning_limits")
    if parsed.get("user_facing_brief") is None:
        raise ValueError("user_facing_brief is required")
    user_facing_brief = validate_user_facing_brief(doctrine["doctrine_id"], parsed.get("user_facing_brief"))

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
    multi_year = pcim.get("multi_year_inputs") or {}
    historical_context_used = _normalize_optional_bool(
        parsed.get("historical_context_used"),
        "historical_context_used",
        default=("multi_year_inputs" in consumed_sections and not _section_empty(multi_year)),
    )
    years_considered = _normalize_string_list(parsed.get("years_considered"), "years_considered") if parsed.get("years_considered") is not None else []
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
        normalized_uncertainty_map.append(normalized_ids)
        uncertainty_summaries.append(summary)

    supplied_evidence_ids, top_level_summary = normalize_evidence_ids_with_summary(
        supplied_evidence_ids,
        evidence_lookup,
        allowed_evidence_ids=allowed_set,
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
            f"assessment.{key}": merged_evidence_ids
            for key in normalized_assessment.keys()
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
        "historical_context_used": historical_context_used,
        "years_considered": years_considered,
        "supporting_pcim_sections": supporting_pcim_sections,
        "evidence_id_normalization": normalization_summary,
        "evidence_grounding_status": grounding["evidence_grounding_status"],
        "evidence_grounding_warnings": grounding["evidence_grounding_warnings"],
        "reasoning_limits": reasoning_limits,
        "user_facing_brief": user_facing_brief,
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
        prompt, compact_pcim, section_stats, limits_used, input_compacted = _build_compact_prompt(
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
        print(
            "[INVESTOR PANEL] "
            f"analyst={doctrine['doctrine_id']} "
            f"sections={consumed_sections} "
            f"prompt_chars={prompt_chars} "
            f"approx_tokens={prompt_tokens} "
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
        prompt, compact_pcim, section_stats, limits_used, input_compacted = _build_compact_prompt(
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
