from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pipelines.pipeline_context import get_context
from .forbidden_language import find_forbidden_recommendation_language
from .committee_brief_renderer import (
    FORBIDDEN_INTERNAL_TERMS,
    build_canonical_committee_brief_view,
    finalize_committee_brief_for_user,
    _dedupe_clean_list,
    validate_brief_view,
)

ALLOWED_ANALYSTS = {"Graham", "Buffett", "Fisher", "Munger", "Lynch"}
REQUIRED_SECTIONS = [
    "# Investment Committee Brief — ",
    "## Committee View",
    "## Financial View",
    "## Where the Analysts Agree",
    "## Where the Analysts Differ",
    "## Strongest Positive Signals",
    "## Most Important Risks",
    "## Critical Unknowns",
    "## Investigation Questions",
    "## Evidence Quality Notes",
    "## Synthesis Limits",
]

V2_REQUIRED_SECTIONS = [
    "# Investment Committee Brief — ",
    "## Committee View",
    "## Bottom Line",
    "## What Changed",
    "## What Strengthened",
    "## What Weakened",
    "## Major Disagreement",
    "## Financial View",
    "## Management View",
    "## Capital Allocation View",
    "## Risk View",
    "## What Remains Unproven",
    "## What Would Change the View",
    "## Top Questions to Investigate",
    "## Evidence Confidence",
]

BROKEN_FRAGMENT_PATTERNS = (
    "integr…",
    "source_uncertainty_ids",
    "registry",
    "artifact",
    "critical financial fields",
    "derived value used",
    "normalized inputs",
    "fcf:",
)


def _looks_semantically_truncated(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if value == "---":
        return False
    lowered = value.lower()
    if value.endswith(("...", "…", "-")):
        return True
    if any(lowered.endswith(f" {token}") for token in ("and", "or", "with", "in", "to", "for", "vs", "versus", "about")):
        return True
    if lowered.endswith("and s"):
        return True
    if value.count("(") != value.count(")"):
        return True
    if "₹" in value and value.endswith("."):
        suffix = value.rsplit("₹", 1)[-1]
        if suffix and suffix.replace(",", "").replace(".", "").strip().isdigit():
            return True
    return False


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _normalize_analyst_names(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).title() for item in value if str(item).strip()]


def _contains_substantial_text(haystack: str, needle: str) -> bool:
    return str(needle or "").strip() in haystack


def _append_issue(bucket: List[str], text: str) -> None:
    if text not in bucket:
        bucket.append(text)


class CommitteeBriefQAGate:
    def __init__(self, company: str, companies_root: Path | str = Path("companies")):
        self.company = company
        self.companies_root = Path(companies_root)
        self.panel_dir = self.companies_root / company / "company_memory" / "investor_panel"
        self.synthesis_path = self.panel_dir / "committee_synthesis.json"
        self.brief_path = self.panel_dir / "committee_brief.md"
        self.output_path = self.panel_dir / "committee_brief_qa.json"

    def _load_inputs(self) -> Tuple[Dict[str, Any], str]:
        synthesis = _load_json(self.synthesis_path)
        if not synthesis:
            raise FileNotFoundError(
                f"committee_synthesis.json not found or unreadable: {self.synthesis_path}"
            )
        synthesis = finalize_committee_brief_for_user(
            synthesis,
            synthesis.get("committee_financial_truth") if isinstance(synthesis, dict) else {},
        )
        brief = _load_text(self.brief_path)
        if not brief:
            raise FileNotFoundError(
                f"committee_brief.md not found or unreadable: {self.brief_path}"
            )
        brief_view = build_canonical_committee_brief_view(
            synthesis,
            synthesis.get("committee_financial_truth") if isinstance(synthesis, dict) else {},
        )
        brief_view = validate_brief_view(
            brief_view,
            synthesis.get("committee_financial_truth") if isinstance(synthesis, dict) else {},
        )
        return brief_view, brief

    def _required_sections_check(self, brief: str, company: str) -> Dict[str, Any]:
        expected_title = f"# Investment Committee Brief — {company.title()}"
        missing: List[str] = []
        if expected_title not in brief:
            missing.append(expected_title)
        for section in REQUIRED_SECTIONS[1:]:
            if section not in brief:
                missing.append(section)
        return {
            "status": "fail" if missing else "pass",
            "missing_sections": missing,
        }

    def _forbidden_language_check(self, brief: str) -> Dict[str, Any]:
        raw_matches = find_forbidden_recommendation_language(brief)
        matches: List[str] = []
        for match in raw_matches:
            token = str(match["matched_text"])
            if token not in matches:
                matches.append(token)
        return {
            "status": "fail" if matches else "pass",
            "matches": matches,
        }

    def _evidence_id_visibility_check(self, brief: str, *, include_evidence_ids: bool) -> Dict[str, Any]:
        patterns = [r"ev_fy", r"evidence_id", r"evidence ids"]
        matches: List[str] = []
        lowered = brief.lower()
        for token in patterns:
            if token in lowered:
                matches.append(token)
        if include_evidence_ids:
            return {
                "status": "pass",
                "matches": matches,
            }
        return {
            "status": "fail" if matches else "pass",
            "matches": matches,
        }

    def _analyst_names_check(self, brief: str) -> Dict[str, Any]:
        unknown_names: List[str] = []
        for line in brief.splitlines():
            if line.startswith("**Analysts:**") or line.startswith("**Supported by:**") or line.startswith("**Raised by:**"):
                names = [
                    item.strip().strip("*").strip()
                    for item in line.split(":", 1)[1].split(",")
                    if item.strip().strip("*").strip()
                ]
                for name in names:
                    if name not in ALLOWED_ANALYSTS:
                        _append_issue(unknown_names, name)
        return {
            "status": "fail" if unknown_names else "pass",
            "unknown_names": unknown_names,
        }

    def _source_fidelity_check(self, brief_view: Dict[str, Any], brief: str) -> Dict[str, Any]:
        missing_items: List[str] = []
        mismatched_items: List[str] = []

        overall = brief_view.get("committee_view", {})
        if not _contains_substantial_text(brief, overall.get("summary", "")):
            missing_items.append("committee_view.summary")
        if not _contains_substantial_text(brief, f"**Confidence:** {overall.get('confidence', '')}"):
            mismatched_items.append("committee_view.confidence")
        if not _contains_substantial_text(brief, f"**Dominant Tension:** {overall.get('dominant_tension', '')}"):
            mismatched_items.append("committee_view.dominant_tension")

        for item in brief_view.get("analyst_agreements", []) or []:
            if not _contains_substantial_text(brief, f"### {item.get('theme', '')}"):
                missing_items.append(f"areas_of_agreement.theme:{item.get('theme', '')}")
            if not _contains_substantial_text(brief, item.get("summary", "")):
                missing_items.append(f"areas_of_agreement.summary:{item.get('theme', '')}")
            analyst_line = f"**Analysts:** {', '.join(_normalize_analyst_names(item.get('analysts')))}"
            if not _contains_substantial_text(brief, analyst_line):
                mismatched_items.append(f"areas_of_agreement.analysts:{item.get('theme', '')}")

        financial = brief_view.get("financial_view", {}) or {}
        if not _contains_substantial_text(brief, "## Financial View"):
            missing_items.append("financial_view.section")
        if not _contains_substantial_text(
            brief, f"**Financials Used:** {'Yes' if financial.get('financials_used') else 'No'}"
        ):
            mismatched_items.append("financial_view.financials_used")
        if not _contains_substantial_text(
            brief, f"**Basis Used:** {financial.get('basis_used', '')}"
        ):
            mismatched_items.append("financial_view.basis_used")
        for item in financial.get("financial_consensus", []) or []:
            if not _contains_substantial_text(brief, item):
                missing_items.append(f"financial_view.financial_consensus:{item}")
        for item in financial.get("financial_strengths", []) or []:
            if not _contains_substantial_text(brief, item):
                missing_items.append(f"financial_view.financial_strengths:{item}")
        for item in financial.get("financial_concerns", []) or []:
            if not _contains_substantial_text(brief, item):
                missing_items.append(f"financial_view.financial_concerns:{item}")
        for item in financial.get("financial_red_flags", []) or []:
            if not _contains_substantial_text(brief, item):
                missing_items.append(f"financial_view.financial_red_flags:{item}")
        missing_financial_data = financial.get("missing_financial_data", []) or []
        if missing_financial_data:
            for item in missing_financial_data:
                if not _contains_substantial_text(brief, item):
                    missing_items.append(f"financial_view.missing_financial_data:{item}")
        else:
            default_missing = "No material missing or incomplete inputs were recorded."
            if not _contains_substantial_text(brief, default_missing):
                mismatched_items.append("financial_view.missing_financial_data.default_message")
        for item in financial.get("financial_interpretation_limits", []) or []:
            if not _contains_substantial_text(brief, item):
                missing_items.append(
                    f"financial_view.financial_interpretation_limits:{item}"
                )
        for item in financial.get("precision_limited_financial_data", []) or []:
            if not _contains_substantial_text(brief, item):
                missing_items.append(
                    f"financial_view.precision_limited_financial_data:{item}"
                )
        for item in financial.get("investor_questions_from_financials", []) or []:
            if not _contains_substantial_text(brief, item):
                missing_items.append(
                    f"financial_view.investor_questions_from_financials:{item}"
                )
        for item in financial.get("financial_disagreements", []) or []:
            disagreement = str(item.get("disagreement", "")).strip()
            if disagreement and not _contains_substantial_text(brief, disagreement):
                missing_items.append(
                    f"financial_view.financial_disagreements.disagreement:{disagreement}"
                )
            for field in ("disagreement_type", "financial_relevance", "evidence_limit"):
                value = str(item.get(field, "")).strip()
                if value and not _contains_substantial_text(brief, value):
                    missing_items.append(
                        f"financial_view.financial_disagreements.{field}:{disagreement or value}"
                    )

        for item in brief_view.get("analyst_disagreements", []) or []:
            if not _contains_substantial_text(brief, f"### {item.get('theme', '')}"):
                missing_items.append(f"areas_of_disagreement.theme:{item.get('theme', '')}")
            if not _contains_substantial_text(brief, f"**Type:** {item.get('disagreement_type', '')}"):
                mismatched_items.append(f"areas_of_disagreement.disagreement_type:{item.get('theme', '')}")
            if not _contains_substantial_text(brief, item.get("why_it_matters", "")):
                missing_items.append(f"areas_of_disagreement.why_it_matters:{item.get('theme', '')}")

        for item in brief_view.get("strongest_positive_signals", []) or []:
            if not _contains_substantial_text(brief, f"### {item.get('signal', '')}"):
                missing_items.append(f"strongest_positive_signals.signal:{item.get('signal', '')}")
            supported_line = f"**Supported by:** {', '.join(_normalize_analyst_names(item.get('supported_by')))}"
            if not _contains_substantial_text(brief, supported_line):
                mismatched_items.append(f"strongest_positive_signals.supported_by:{item.get('signal', '')}")

        for item in brief_view.get("most_important_risks", []) or []:
            if not _contains_substantial_text(brief, f"### {item.get('risk', '')}"):
                missing_items.append(f"most_important_risks.risk:{item.get('risk', '')}")
            if not _contains_substantial_text(brief, f"**Severity:** {item.get('severity', '')}"):
                mismatched_items.append(f"most_important_risks.severity:{item.get('risk', '')}")
            raised_line = f"**Raised by:** {', '.join(_normalize_analyst_names(item.get('raised_by')))}"
            if not _contains_substantial_text(brief, raised_line):
                mismatched_items.append(f"most_important_risks.raised_by:{item.get('risk', '')}")

        for item in brief_view.get("critical_unknowns", []) or []:
            if not _contains_substantial_text(brief, f"### {item.get('unknown', '')}"):
                missing_items.append(f"critical_unknowns.unknown:{item.get('unknown', '')}")
            if not _contains_substantial_text(brief, item.get("why_it_matters", "")):
                missing_items.append(f"critical_unknowns.why_it_matters:{item.get('unknown', '')}")

        for index, item in enumerate(brief_view.get("investigation_questions", []) or [], start=1):
            if not _contains_substantial_text(brief, f"### Question {index}"):
                missing_items.append(f"investigation_questions.question_number:{index}")
            if not _contains_substantial_text(brief, item.get("question", "")):
                missing_items.append(f"investigation_questions.question:{index}")
            if not _contains_substantial_text(brief, item.get("reason", "")):
                missing_items.append(f"investigation_questions.reason:{index}")
            if not _contains_substantial_text(brief, item.get("linked_unknown_or_risk", "")):
                mismatched_items.append(f"investigation_questions.linked_unknown_or_risk:{index}")

        notes = brief_view.get("evidence_quality_notes", []) or []
        if notes:
            for note in notes:
                if not _contains_substantial_text(brief, note):
                    missing_items.append(f"evidence_quality_notes:{note}")
        else:
            expected = "No material evidence-quality warnings were recorded."
            if not _contains_substantial_text(brief, expected):
                mismatched_items.append("evidence_quality_notes.default_message")

        for item in brief_view.get("synthesis_limits", []) or []:
            if not _contains_substantial_text(brief, item):
                missing_items.append(f"synthesis_limits:{item}")

        status = "pass"
        if missing_items or mismatched_items:
            status = "fail"
        return {
            "status": status,
            "missing_items": missing_items,
            "mismatched_items": mismatched_items,
        }

    def _quality_contradiction_check(self, brief_view: Dict[str, Any], brief: str) -> Dict[str, Any]:
        contradictions: List[str] = []
        formatting_issues: List[str] = []
        internal_language: List[str] = []
        low_quality_questions: List[str] = []
        readability_warnings: List[str] = []
        lowered = brief.lower()
        truth = brief_view.get("committee_financial_truth") or {}

        contradiction_rules = [
            (truth.get("fcf_missing") is False, "free cash flow is missing", "fcf_missing=false"),
            (truth.get("fcf_missing") is False, "fcf-based conclusions cannot be assessed", "fcf_missing=false"),
            (truth.get("capex_missing") is False, "capex missing", "capex_missing=false"),
            (truth.get("capex_missing") is False, "capex unavailable", "capex_missing=false"),
            (truth.get("capex_missing") is False, "capex data are not provided", "capex_missing=false"),
            (truth.get("payables_available") is True, "payables missing", "payables_available=true"),
            (truth.get("payables_available") is True, "payables or payable-days evidence is missing", "payables_available=true"),
            (truth.get("payables_missing") is False, "payables missing", "payables_missing=false"),
            (truth.get("working_capital_metrics_available") is True, "cash conversion cycle cannot be assessed", "working_capital_metrics_available=true"),
            (truth.get("payables_available") is True, "cash conversion cycle cannot be assessed cleanly", "payables_available=true"),
        ]
        for enabled, phrase, reason in contradiction_rules:
            if enabled and phrase in lowered:
                contradictions.append(f'{reason}: "{phrase}"')

        seen_bullets = set()
        in_financial_strengths = False
        lines = brief.splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            lowered_line = stripped.lower()
            if stripped == "**Financial Strengths:**":
                in_financial_strengths = True
                continue
            if in_financial_strengths and (
                stripped.startswith("**")
                or stripped.startswith("## ")
                or stripped.startswith("### ")
                or stripped == "---"
            ):
                in_financial_strengths = False
            if stripped.startswith("- "):
                if lowered_line in seen_bullets and any(
                    token in lowered_line
                    for token in (
                        "share-count evidence incomplete",
                        "standalone/consolidated basis unclear",
                        "fcf is derived",
                        "maintenance versus growth capex split",
                    )
                ):
                    formatting_issues.append(f"duplicate_bullet:{stripped}")
                seen_bullets.add(lowered_line)
                if in_financial_strengths:
                    business_only = any(
                        token in lowered_line
                        for token in ("business model", "competitive position", "certification", "operating story", "moat")
                    )
                    financial_terms = any(
                        token in lowered_line
                        for token in ("revenue", "pat", "profit", "margin", "cash", "cfo", "fcf", "owner earnings", "debt", "capex", "roe", "roce", "eps", "book value")
                    )
                    if business_only and not financial_terms:
                        readability_warnings.append(f"financial_strength_business_only:{stripped[2:]}")
                    if any(
                        token in lowered_line
                        for token in (
                            "basis remains unclear",
                            "basis consistency remains unclear",
                            "share-count evidence is incomplete",
                            "weighted-average and diluted share-count evidence is incomplete",
                            "maintenance versus growth capex split",
                        )
                    ):
                        readability_warnings.append(f"limitation_inside_financial_strengths:{stripped[2:]}")
            if any(token in lowered_line for token in BROKEN_FRAGMENT_PATTERNS):
                internal_language.append(stripped)
            if "₹" in stripped and stripped.endswith("."):
                suffix = stripped.rsplit("₹", 1)[-1]
                if suffix and suffix.replace(",", "").replace(".", "").strip().isdigit():
                    formatting_issues.append(f"incomplete_currency_fragment:{stripped}")
            if "≈₹" in stripped and stripped.endswith("."):
                formatting_issues.append(f"incomplete_currency_fragment:{stripped}")
            if stripped.endswith("...") or stripped.endswith("…"):
                formatting_issues.append(f"truncated_ellipsis:{stripped}")
            if _looks_semantically_truncated(stripped):
                formatting_issues.append(f"semantic_truncation:{stripped}")
            if line.startswith("### Question "):
                next_substantial = ""
                for next_line in lines[index + 1 :]:
                    candidate = next_line.strip()
                    if not candidate:
                        continue
                    next_substantial = candidate
                    break
                if not next_substantial or next_substantial.startswith("**Why this matters:**") or next_substantial.startswith("---") or next_substantial.startswith("### "):
                    low_quality_questions.append(f"blank_question_body:{stripped}")
                continue
            if stripped.startswith("**Why this matters:**") or stripped.startswith("**Linked unknown/risk:**"):
                continue
            if stripped and stripped.endswith("?") is False and stripped.startswith("What "):
                low_quality_questions.append(stripped)
            if stripped.startswith("### ") and "Question " not in stripped and stripped.endswith(":"):
                low_quality_questions.append(stripped)

        financial = brief_view.get("financial_view") or {}
        precision_limited = financial.get("precision_limited_financial_data") or []
        if (
            precision_limited
            or truth.get("basis_unknown")
            or truth.get("weighted_avg_shares_missing")
            or truth.get("diluted_shares_missing")
            or truth.get("maintenance_growth_split_missing")
            or truth.get("multi_year_bridge_history_incomplete")
        ) and "no material missing financial data was recorded." in lowered:
            contradictions.append(
                'precision_limited_financial_data present but brief says "No material missing financial data was recorded."'
            )
        strengths = financial.get("financial_strengths") or []
        if len(strengths) <= 1 and (
            truth.get("owner_earnings_estimate_available")
            or truth.get("working_capital_metrics_available")
            or truth.get("payables_available")
        ):
            readability_warnings.append("financial_strengths_too_thin_for_available_financial_truth")
        summary_text = str((brief_view.get("committee_view") or {}).get("summary") or "").lower()
        tension_text = str((brief_view.get("committee_view") or {}).get("dominant_tension") or "").lower()
        if truth.get("working_capital_risk"):
            if not any(token in summary_text for token in ("working-capital", "cash-conversion", "receivable", "payable days")):
                readability_warnings.append("committee_view_omits_working_capital_risk")
            if not any(token in tension_text for token in ("working-capital", "cash-generation", "cash conversion", "receivable", "payable")):
                readability_warnings.append("dominant_tension_omits_working_capital_risk")
        for item in brief_view.get("strongest_positive_signals", []) or []:
            signal = str(item.get("signal") or "").strip()
            if _looks_semantically_truncated(signal):
                formatting_issues.append(f"signal_heading_truncated:{signal}")
            if len(signal.split()) > 14:
                readability_warnings.append(f"signal_heading_not_canonical:{signal}")

        for item in brief_view.get("investigation_questions", []) or []:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            if question and not question.endswith("?"):
                low_quality_questions.append(question)
            if question and len(question.split()) <= 2:
                low_quality_questions.append(question)
            if not question:
                low_quality_questions.append("empty_investigation_question")
        status = "pass"
        if contradictions or formatting_issues or internal_language or low_quality_questions:
            status = "fail"
        elif readability_warnings:
            status = "warning"
        return {
            "status": status,
            "contradictions": contradictions,
            "formatting_issues": formatting_issues,
            "internal_language": internal_language,
            "low_quality_questions": low_quality_questions,
            "readability_warnings": readability_warnings,
        }

    def _required_sections_check_v2(self, brief: str, company: str) -> Dict[str, Any]:
        expected_title = f"# Investment Committee Brief — {company.title()}"
        missing: List[str] = []
        if expected_title not in brief:
            missing.append(expected_title)
        for section in V2_REQUIRED_SECTIONS[1:]:
            if section not in brief:
                missing.append(section)
        return {
            "status": "fail" if missing else "pass",
            "missing_sections": missing,
        }

    def _v2_truth_consistency_check(self, brief_view: Dict[str, Any], brief: str) -> Dict[str, Any]:
        missing: List[str] = []
        mismatched: List[str] = []
        bottom_line = str(brief_view.get("bottom_line") or "").strip()
        if bottom_line and not _contains_substantial_text(brief, bottom_line):
            missing.append("bottom_line")
        for field in ("committee_view", "committee_direction", "consensus_strength"):
            value = str(brief_view.get(field) or "").strip()
            if value and not _contains_substantial_text(brief, value):
                mismatched.append(field)
        for block_name in ("management_view", "capital_allocation_view", "financial_view", "risk_view"):
            block = brief_view.get(block_name) or {}
            for key in ("assessment", "direction", "strongest_evidence", "main_concern", "unresolved_issue"):
                value = str(block.get(key) or "").strip()
                if value and not _contains_substantial_text(brief, value):
                    missing.append(f"{block_name}.{key}")
        evidence_confidence = brief_view.get("evidence_confidence") or {}
        for item in (
            f"**Level:** {evidence_confidence.get('level', '')}",
            f"**Basis:** {', '.join(evidence_confidence.get('basis') or [])}",
            f"**Main Limitation:** {evidence_confidence.get('main_limitation', '')}",
        ):
            if str(item).strip() and not _contains_substantial_text(brief, str(item).strip()):
                mismatched.append("evidence_confidence")
        status = "pass"
        if missing or mismatched:
            status = "fail"
        return {"status": status, "missing_items": missing, "mismatched_items": mismatched}

    def _v2_progression_consistency_check(self, brief_view: Dict[str, Any], brief: str) -> Dict[str, Any]:
        missing: List[str] = []
        issues: List[str] = []
        for item in brief_view.get("what_changed", []) or []:
            if not isinstance(item, dict):
                continue
            for key in ("period", "previous_state", "current_state", "why_it_matters"):
                value = str(item.get(key) or "").strip()
                if value and not _contains_substantial_text(brief, value):
                    missing.append(f"what_changed.{key}:{value}")
        if not brief_view.get("what_changed"):
            issues.append("what_changed is empty")
        for item in brief_view.get("what_remains_unproven", []) or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("item") or "").strip()
            if value and not _contains_substantial_text(brief, value):
                missing.append(f"what_remains_unproven.item:{value}")
        status = "pass"
        if missing:
            status = "fail"
        elif issues:
            status = "warning"
        return {"status": status, "missing_items": missing, "warnings": issues}

    def _v2_disagreement_preservation_check(self, brief_view: Dict[str, Any], brief: str) -> Dict[str, Any]:
        issues: List[str] = []
        for item in brief_view.get("major_disagreement", []) or []:
            if not isinstance(item, dict):
                continue
            for key in ("topic", "side_a", "side_b", "why_the_disagreement_exists", "evidence_that_could_resolve_it", "disagreement_type"):
                value = str(item.get(key) or "").strip()
                if value and not _contains_substantial_text(brief, value):
                    issues.append(f"{key}:{value}")
        status = "pass" if not issues else "fail"
        return {"status": status, "issues": issues}

    def _v2_uncertainty_discipline_check(self, brief_view: Dict[str, Any], brief: str) -> Dict[str, Any]:
        issues: List[str] = []
        lowered = brief.lower()
        if any(term in lowered for term in ("buy ", "sell ", "hold ", "target price", "fair value recommendation")):
            issues.append("recommendation language detected")
        if brief_view.get("what_remains_unproven"):
            resolved_patterns = (
                "fully resolved",
                "completely resolved",
                "already resolved",
                "has been resolved",
                "have been resolved",
                "is resolved",
                "are resolved",
            )
            if "not fully resolved" not in lowered and any(term in lowered for term in resolved_patterns):
                issues.append("resolved language conflicts with remaining unknowns")
        if not str((brief_view.get("evidence_confidence") or {}).get("main_limitation") or "").strip():
            issues.append("evidence confidence limitation missing")
        status = "pass" if not issues else "fail"
        return {"status": status, "issues": issues}

    def _v2_public_language_check(self, brief: str) -> Dict[str, Any]:
        matches: List[str] = []
        lowered = brief.lower()
        for term in FORBIDDEN_INTERNAL_TERMS:
            if term in lowered:
                matches.append(term)
        if find_forbidden_recommendation_language(brief):
            matches.append("recommendation language")
        status = "pass" if not matches else "fail"
        return {"status": status, "matches": _dedupe_clean_list(matches)}

    def _v2_evidence_traceability_check(self, brief_view: Dict[str, Any], brief: str) -> Dict[str, Any]:
        missing: List[str] = []
        for item in (brief_view.get("what_strengthened") or [])[:4]:
            if not isinstance(item, dict):
                continue
            value = str(item.get("conclusion") or "").strip()
            if value and not _contains_substantial_text(brief, value):
                missing.append(f"what_strengthened:{value}")
        for item in (brief_view.get("what_weakened") or [])[:4]:
            if not isinstance(item, dict):
                continue
            value = str(item.get("conclusion") or "").strip()
            if value and not _contains_substantial_text(brief, value):
                missing.append(f"what_weakened:{value}")
        for item in (brief_view.get("top_questions_to_investigate") or [])[:5]:
            if not isinstance(item, dict):
                continue
            value = str(item.get("question") or "").strip()
            if value and not _contains_substantial_text(brief, value):
                missing.append(f"top_questions_to_investigate:{value}")
        status = "pass" if not missing else "fail"
        return {"status": status, "missing_items": missing}

    def _v2_duplication_control_check(self, brief_view: Dict[str, Any], brief: str) -> Dict[str, Any]:
        seen: Dict[str, int] = {}
        duplicate_items: List[str] = []
        sections = []
        sections.extend([str(brief_view.get("bottom_line") or "")])
        sections.extend([str(item.get("current_state") or "") for item in brief_view.get("what_changed", []) or [] if isinstance(item, dict)])
        sections.extend([str(item.get("conclusion") or "") for item in brief_view.get("what_strengthened", []) or [] if isinstance(item, dict)])
        sections.extend([str(item.get("conclusion") or "") for item in brief_view.get("what_weakened", []) or [] if isinstance(item, dict)])
        sections.extend([str(item.get("item") or "") for item in brief_view.get("what_remains_unproven", []) or [] if isinstance(item, dict)])
        for text in sections:
            key = " ".join(text.lower().split())
            if not key:
                continue
            seen[key] = seen.get(key, 0) + 1
        for key, count in seen.items():
            if count > 1 and len(key.split()) >= 6 and len(key) >= 40:
                duplicate_items.append(key)
        if brief.count(str(brief_view.get("bottom_line") or "")) > 1:
            duplicate_items.append("bottom_line repeated")
        status = "pass" if not duplicate_items else "warning"
        return {"status": status, "duplicates": _dedupe_clean_list(duplicate_items)}

    def _build_v2_checks(self, brief_view: Dict[str, Any], brief: str) -> Dict[str, Dict[str, Any]]:
        return {
            "presentation_contract": self._required_sections_check_v2(brief, self.company),
            "truth_consistency": self._v2_truth_consistency_check(brief_view, brief),
            "progression_consistency": self._v2_progression_consistency_check(brief_view, brief),
            "disagreement_preservation": self._v2_disagreement_preservation_check(brief_view, brief),
            "uncertainty_discipline": self._v2_uncertainty_discipline_check(brief_view, brief),
            "public_language_quality": self._v2_public_language_check(brief),
            "evidence_traceability": self._v2_evidence_traceability_check(brief_view, brief),
            "recommendation_safety": self._v2_public_language_check(brief),
            "duplication_control": self._v2_duplication_control_check(brief_view, brief),
        }

    def build(self, *, include_evidence_ids: bool = False) -> Dict[str, Path]:
        brief_view, brief = self._load_inputs()
        if brief_view.get("brief_mode") == "v2":
            checks = self._build_v2_checks(brief_view, brief)
            errors: List[str] = []
            warnings: List[str] = []
            progression_issues: List[str] = []
            disagreement_issues: List[str] = []
            uncertainty_issues: List[str] = []
            public_language_issues: List[str] = []
            duplication_issues: List[str] = []
            recommendation_safety_issues: List[str] = []
            suggested_fixes: List[str] = []
            for check_name, result in checks.items():
                status = str(result.get("status") or "").strip()
                if status == "fail":
                    errors.append(check_name)
                elif status == "warning":
                    warnings.append(check_name)
                if check_name == "progression_consistency":
                    progression_issues.extend(result.get("missing_items", []) or result.get("warnings", []) or [])
                elif check_name == "disagreement_preservation":
                    disagreement_issues.extend(result.get("issues", []) or [])
                elif check_name == "uncertainty_discipline":
                    uncertainty_issues.extend(result.get("issues", []) or [])
                elif check_name == "public_language_quality":
                    public_language_issues.extend(result.get("matches", []) or [])
                elif check_name == "duplication_control":
                    duplication_issues.extend(result.get("duplicates", []) or [])
                elif check_name == "recommendation_safety":
                    recommendation_safety_issues.extend(result.get("matches", []) or [])
            if errors:
                suggested_fixes.extend([f"Fix {item} in the brief or synthesis." for item in errors])
            if not warnings and not errors:
                overall_status = "pass"
            elif errors:
                overall_status = "fail"
            else:
                overall_status = "warning"
            payload = {
                "company": self.company,
                "qa_mode": "committee_brief_qa_v2",
                "status": overall_status,
                "errors": errors,
                "warnings": warnings,
                "checks": checks,
                "progression_issues": _dedupe_clean_list(progression_issues),
                "disagreement_issues": _dedupe_clean_list(disagreement_issues),
                "uncertainty_issues": _dedupe_clean_list(uncertainty_issues),
                "public_language_issues": _dedupe_clean_list(public_language_issues),
                "duplication_issues": _dedupe_clean_list(duplication_issues),
                "recommendation_safety_issues": _dedupe_clean_list(recommendation_safety_issues),
                "suggested_fixes": _dedupe_clean_list(suggested_fixes),
                "failures": errors,
                "generated_at": utc_now(),
            }
        else:
            checks = {
                "required_sections": self._required_sections_check(brief, self.company),
                "forbidden_language": self._forbidden_language_check(brief),
                "evidence_id_visibility": self._evidence_id_visibility_check(
                    brief,
                    include_evidence_ids=include_evidence_ids,
                ),
                "analyst_names": self._analyst_names_check(brief),
                "source_fidelity": self._source_fidelity_check(brief_view, brief),
                "quality_contradictions": self._quality_contradiction_check(brief_view, brief),
            }

            failures: List[str] = []
            warnings: List[str] = []
            for check_name, result in checks.items():
                status = result.get("status")
                if status == "fail":
                    failures.append(check_name)
                elif status == "warning":
                    warnings.append(check_name)

            overall_status = "pass"
            if failures:
                overall_status = "fail"
            elif warnings:
                overall_status = "warning"

            payload = {
                "company": self.company,
                "qa_mode": "committee_brief_qa_v1",
                "status": overall_status,
                "checks": checks,
                "warnings": warnings,
                "failures": failures,
                "errors": failures,
                "progression_issues": [],
                "disagreement_issues": [],
                "uncertainty_issues": [],
                "public_language_issues": [],
                "duplication_issues": [],
                "recommendation_safety_issues": [],
                "suggested_fixes": [],
                "generated_at": utc_now(),
            }
        return {
            "committee_brief_qa.json": _write_json(self.output_path, payload),
        }
