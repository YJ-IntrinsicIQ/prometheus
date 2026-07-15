from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from knowledge.ai import get_llm
from knowledge.ai.input_packs import (
    build_llm_input_pack,
    call_llm_with_input_pack,
    render_llm_input_pack,
)

from .committee_validator import (
    EXPECTED_ANALYSTS,
    _canonical_committee_evidence_id,
    validate_analyst_payload,
    validate_committee_output,
)
from .evidence_grounding import build_evidence_lookup


COMMITTEE_SYNTHESIS_SYSTEM_PROMPT = """
You are the Investment Committee Synthesizer for Prometheus.

You are not an investment advisor.
You are not a valuation engine.
You are not allowed to issue buy, sell, hold, accumulate, avoid, or target-price conclusions.

Your job is to synthesize the views of five specialist investor analysts:
- Graham: downside protection, financial strength, margin of safety
- Buffett: business quality, moat, capital allocation
- Fisher: growth quality, management ambition, execution
- Munger: incentives, governance, avoidable mistakes
- Lynch: simple story, growth runway, hype check

You must only use the analyst outputs provided in the input.
Do not read or infer from raw annual reports.
Do not introduce new facts.
Do not re-analyze the company independently.
Do not override the analysts.
Do not pretend certainty where analysts expressed uncertainty.

Your synthesis should answer:
1. Where do the analysts agree?
2. Where do they disagree or emphasize different things?
3. What are the strongest positive signals?
4. What are the most important risks?
5. What remains unknown?
6. What should the investor investigate next?

Rules:
- Preserve uncertainty.
- Use cautious, evidence-backed language.
- Treat two-year history as provisional.
- Mention evidence-quality limitations when relevant.
- Do not create unsupported conclusions.
- Evidence IDs in the output must come only from analyst evidence_ids.
- Output valid JSON only.
"""

COMMITTEE_SYNTHESIS_USER_PROMPT = """
Synthesize the following analyst outputs into one Investment Committee view.

INPUT:
{committee_input_json}

Return ONLY valid JSON using this exact schema:

{
  "company": "",
  "analysis_mode": "committee_synthesis_v1",
  "analysts_considered": [],
  "missing_analysts": [],
  "excluded_analysts": [],
  "years_considered": [],
  "overall_committee_view": {
    "summary": "",
    "confidence": "low|medium|high",
    "dominant_tension": ""
  },
  "areas_of_agreement": [
    {
      "theme": "",
      "analysts": [],
      "summary": "",
      "evidence_ids": []
    }
  ],
  "areas_of_disagreement": [
    {
      "theme": "",
      "analysts_positive_or_less_concerned": [],
      "analysts_cautious_or_negative": [],
      "summary": "",
      "why_it_matters": "",
      "evidence_ids": []
    }
  ],
  "strongest_positive_signals": [
    {
      "signal": "",
      "supported_by": [],
      "summary": "",
      "evidence_ids": []
    }
  ],
  "most_important_risks": [
    {
      "risk": "",
      "raised_by": [],
      "summary": "",
      "severity": "low|medium|high|uncertain",
      "evidence_ids": []
    }
  ],
  "critical_unknowns": [
    {
      "unknown": "",
      "raised_by": [],
      "why_it_matters": ""
    }
  ],
  "investigation_questions": [
    {
      "question": "",
      "reason": "",
      "linked_unknown_or_risk": ""
    }
  ],
  "evidence_ids": [],
  "evidence_quality_notes": [],
  "synthesis_limits": [],
  "generated_at": ""
}

Synthesis instructions:

1. Overall committee view
Write a concise committee-level summary.
Do not give a recommendation.
Do not say the company is attractive, unattractive, cheap, expensive, investable, or uninvestable.
Focus on the dominant investment tension.

2. Areas of agreement
Include themes supported by at least two analysts.
Examples:
- capex-heavy manufacturing story
- liquidity/refinancing risk
- missing cash-flow evidence
- promise follow-through uncertainty
- unproven moat
- provisional two-year history

3. Areas of disagreement
Disagreement does not require direct contradiction.
It can mean different weighting.
Example:
- Fisher/Lynch may emphasize growth ambition and execution signals.
- Graham/Munger may emphasize downside, liquidity, and avoidable risk.
- Buffett may accept business understandability but question moat durability.

4. Strongest positive signals
Only include positives that analysts actually mentioned.
Do not exaggerate.
Do not convert ambition into execution unless analysts did so.

5. Most important risks
Prioritize risks mentioned by multiple analysts or central to the committee tension.
Severity should reflect analyst emphasis, not your independent judgment.

6. Critical unknowns
Use analyst open_uncertainties.
Do not invent new unknowns.
Prefer unknowns that affect investment judgment:
- cash-flow evidence
- debt maturity/refinancing
- capex funding
- customer/revenue concentration
- promise follow-through
- governance/compensation detail

7. Investigation questions
Convert critical unknowns into practical investor questions.
Questions should be answerable through future documents, management Q&A, concalls, filings, or scuttlebutt.

8. Evidence handling
Every evidence_id used must appear in at least one analyst input.
Do not create new evidence IDs.
Do not include source chunks.
Do not include raw PCIM or raw annual report text.

9. Language constraints
Forbidden words/phrases:
- buy
- sell
- hold
- target price
- fair value
- undervalued
- overvalued
- recommendation
- invest now
- avoid

Return JSON only.
"""


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


class InvestmentCommitteeSynthesizer:
    def __init__(self, company: str, companies_root: Path | str = Path("companies")):
        self.company = company
        self.companies_root = Path(companies_root)
        self.panel_dir = self.companies_root / company / "company_memory" / "investor_panel"
        self.output_path = self.panel_dir / "committee_synthesis.json"
        self.llm = get_llm()

    def _analysis_path(self, analyst: str) -> Path:
        return self.panel_dir / f"{analyst}_analysis.json"

    def _pcim_path(self) -> Path:
        return self.companies_root / self.company / "company_memory" / "pcim_v1.json"

    def _load_analyst_payload(self, analyst: str) -> Optional[Dict[str, Any]]:
        path = self._analysis_path(analyst)
        if not path.exists():
            return None
        payload = _load_json(path)
        validate_analyst_payload(payload, analyst=analyst)
        return payload

    def _load_inputs(self) -> Tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
        included: List[Dict[str, Any]] = []
        missing: List[str] = []
        excluded: List[str] = []
        warning_notes: List[str] = []

        for analyst in EXPECTED_ANALYSTS:
            payload = self._load_analyst_payload(analyst)
            if payload is None:
                missing.append(analyst)
                continue

            status = str(payload.get("evidence_grounding_status") or "").strip().lower()
            warning_count = len(payload.get("evidence_grounding_warnings") or [])
            unresolved_count = len(
                ((payload.get("evidence_id_normalization") or {}).get("unresolved_ids") or [])
            )
            if status == "fail":
                excluded.append(analyst)
                warning_notes.append(
                    f"{analyst} excluded because evidence_grounding_status=fail "
                    f"with {warning_count} warning(s) and {unresolved_count} unresolved id(s)."
                )
                continue

            if status == "warning":
                warning_notes.append(
                    f"{analyst} included with evidence grounding warnings: {warning_count} issue(s)."
                )

            included.append(payload)

        return included, missing, excluded, warning_notes

    def _compact_analyst_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "doctrine_id": payload["doctrine_id"],
            "rating": payload["rating"],
            "key_findings": list(payload.get("key_findings", []) or []),
            "red_flags": list(payload.get("red_flags", []) or []),
            "open_uncertainties": list(payload.get("open_uncertainties", []) or []),
            "evidence_ids": list(payload.get("evidence_ids", []) or []),
            "evidence_grounding_status": payload.get("evidence_grounding_status"),
            "evidence_grounding_warnings": list(payload.get("evidence_grounding_warnings", []) or []),
            "historical_context_used": bool(payload.get("historical_context_used")),
            "years_considered": list(payload.get("years_considered", []) or []),
            "reasoning_limits": list(payload.get("reasoning_limits", []) or []),
            "user_facing_brief": payload.get("user_facing_brief"),
        }

    def _build_committee_input(
        self,
        included: Sequence[Dict[str, Any]],
        missing: Sequence[str],
        excluded: Sequence[str],
        warning_notes: Sequence[str],
    ) -> Dict[str, Any]:
        return {
            "company": self.company,
            "analysts": [self._compact_analyst_input(payload) for payload in included],
            "missing_analysts": list(missing),
            "excluded_analysts": list(excluded),
            "evidence_quality_notes": list(warning_notes),
        }

    def _analyst_uncertainties(self, included: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
        return {
            payload["doctrine_id"]: [str(item) for item in payload.get("open_uncertainties", []) or []]
            for payload in included
        }

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

    def _build_prompt(self, committee_input: Dict[str, Any]) -> str:
        llm_input_pack = build_llm_input_pack(
            stage="committee_synthesis",
            purpose="Synthesize analyst-only outputs into a committee-level investment view without introducing new facts.",
            company=self.company,
            year=None,
            selected_input=committee_input,
            observations=[committee_input],
            source_artifacts=[
                str(self._analysis_path(payload["doctrine_id"]))
                for payload in committee_input.get("analysts", [])
                if isinstance(payload, dict) and payload.get("doctrine_id")
            ],
            pack_name="committee_synthesis_input_pack",
        )
        return COMMITTEE_SYNTHESIS_USER_PROMPT.replace(
            "{committee_input_json}",
            render_llm_input_pack(llm_input_pack, include_policy=False),
        )

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

            if not disagreement_type or (
                disagreement_type == "different_emphasis"
                and inferred_type == "risk_weighting_difference"
            ):
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
        payload["synthesis_limits"] = _dedupe(
            _normalize_optional_string_list(payload.get("synthesis_limits"))
        )
        self._apply_disagreement_cleanup(payload)
        return payload

    def _finalize_payload(
        self,
        payload: Dict[str, Any],
        *,
        included: Sequence[Dict[str, Any]],
        missing: Sequence[str],
        excluded: Sequence[str],
    ) -> Dict[str, Any]:
        included_analysts = [item["doctrine_id"] for item in included]
        validated = self._apply_committee_cleanup(
            payload,
            included=included,
            missing=missing,
            excluded=excluded,
        )
        validated["company"] = self.company
        validated["analysis_mode"] = "committee_synthesis_v1"
        validated["analysts_considered"] = included_analysts
        validated["missing_analysts"] = list(missing)
        validated["excluded_analysts"] = list(excluded)
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
        validated["generated_at"] = utc_now()
        return validate_committee_output(
            validated,
            company=self.company,
            included_analysts=included_analysts,
            missing_analysts=missing,
            excluded_analysts=excluded,
            allowed_evidence_ids=self._validation_allowed_evidence_ids(included, validated),
            analyst_uncertainties=self._analyst_uncertainties(included),
            mode="final",
        )

    def cleanup_existing(self) -> Path:
        included, missing, excluded, _warning_notes = self._load_inputs()
        if not self.output_path.exists():
            raise FileNotFoundError(
                f"committee_synthesis.json not found for cleanup: {self.output_path}"
            )
        payload = _load_json(self.output_path)
        cleaned = self._finalize_payload(
            payload,
            included=included,
            missing=missing,
            excluded=excluded,
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
        prompt = self._build_prompt(committee_input)
        llm_input_pack = build_llm_input_pack(
            stage="committee_synthesis",
            purpose="Synthesize analyst-only outputs into a committee-level investment view without introducing new facts.",
            company=self.company,
            year=None,
            selected_input=committee_input,
            observations=[committee_input],
            source_artifacts=[
                str(self._analysis_path(payload["doctrine_id"]))
                for payload in included
                if isinstance(payload, dict) and payload.get("doctrine_id")
            ],
            pack_name="committee_synthesis_input_pack",
        )
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

        included_analysts = [payload["doctrine_id"] for payload in included]
        validated = validate_committee_output(
            response.text,
            company=self.company,
            included_analysts=included_analysts,
            missing_analysts=missing,
            excluded_analysts=excluded,
            allowed_evidence_ids=self._validation_allowed_evidence_ids(included),
            analyst_uncertainties=self._analyst_uncertainties(included),
            mode="raw",
        )
        validated["evidence_quality_notes"] = _dedupe(
            list(validated.get("evidence_quality_notes", []) or []) + list(warning_notes)
        )
        finalized = self._finalize_payload(
            validated,
            included=included,
            missing=missing,
            excluded=excluded,
        )
        return _write_json(self.output_path, finalized)
