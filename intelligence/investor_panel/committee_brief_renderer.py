from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from pipelines.pipeline_context import get_context

from .forbidden_language import find_forbidden_recommendation_language

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

FORBIDDEN_INTERNAL_TERMS = {
    "pcim",
    "cim",
    "evidence_id",
    "evidence ids",
    "source_manifest",
    "input_pack",
    "artifact",
    "doctrine",
    "schema",
    "validator",
    "grounding_status",
    "raw chunk",
    "source_chunk",
    "multi_year_inputs",
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

    text_blob = "\n".join(_flatten_strings(payload))
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
        return validate_committee_brief_source(payload)

    def _render_section_separator(self, lines: List[str]) -> None:
        lines.extend(["", "---", ""])

    def _render(self, payload: Dict[str, Any], *, include_evidence_ids: bool) -> str:
        company_name = str(payload.get("company") or self.company).title()
        overall = payload["overall_committee_view"]
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
        for item in payload.get("areas_of_agreement", []) or []:
            lines.extend(
                [
                    "",
                    f"### {item.get('theme', '').strip()}",
                    str(item.get("summary", "")).strip(),
                    "",
                    f"**Analysts:** {_format_analysts(item.get('source_analysts') or item.get('analysts'))}",
                ]
            )
            self._render_section_separator(lines)

        financial = payload["financial_committee_view"]
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
        if missing:
            lines.extend([f"- {str(item).strip()}" for item in missing if str(item).strip()])
        else:
            lines.append("- No material missing financial data was recorded.")
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

        lines.append("## Where the Analysts Differ")
        for item in payload.get("areas_of_disagreement", []) or []:
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

        lines.append("## Strongest Positive Signals")
        for item in payload.get("strongest_positive_signals", []) or []:
            lines.extend(
                [
                    "",
                    f"### {item.get('signal', '').strip()}",
                    str(item.get("summary") or item.get("why_it_matters") or "").strip(),
                    "",
                    f"**Supported by:** {_format_analysts(item.get('source_analysts') or item.get('supported_by'))}",
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
                    f"**Raised by:** {_format_analysts(item.get('source_analysts') or item.get('raised_by'))}",
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

    def build(self, *, include_evidence_ids: bool = False) -> Dict[str, Path]:
        payload = self._load_committee_synthesis()
        markdown = self._render(payload, include_evidence_ids=include_evidence_ids)
        return {
            "committee_brief.md": _write_text(self.output_path, markdown),
        }
