from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .forbidden_language import find_forbidden_recommendation_language

ALLOWED_ANALYSTS = {"Graham", "Buffett", "Fisher", "Munger", "Lynch"}
REQUIRED_SECTIONS = [
    "# Investment Committee Brief — ",
    "## Committee View",
    "## Where the Analysts Agree",
    "## Where the Analysts Differ",
    "## Strongest Positive Signals",
    "## Most Important Risks",
    "## Critical Unknowns",
    "## Investigation Questions",
    "## Evidence Quality Notes",
    "## Synthesis Limits",
]


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
        brief = _load_text(self.brief_path)
        if not brief:
            raise FileNotFoundError(
                f"committee_brief.md not found or unreadable: {self.brief_path}"
            )
        return synthesis, brief

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

    def _source_fidelity_check(self, synthesis: Dict[str, Any], brief: str) -> Dict[str, Any]:
        missing_items: List[str] = []
        mismatched_items: List[str] = []

        overall = synthesis.get("overall_committee_view", {})
        if not _contains_substantial_text(brief, overall.get("summary", "")):
            missing_items.append("overall_committee_view.summary")
        if not _contains_substantial_text(brief, f"**Confidence:** {overall.get('confidence', '')}"):
            mismatched_items.append("overall_committee_view.confidence")
        if not _contains_substantial_text(brief, f"**Dominant Tension:** {overall.get('dominant_tension', '')}"):
            mismatched_items.append("overall_committee_view.dominant_tension")

        for item in synthesis.get("areas_of_agreement", []) or []:
            if not _contains_substantial_text(brief, f"### {item.get('theme', '')}"):
                missing_items.append(f"areas_of_agreement.theme:{item.get('theme', '')}")
            if not _contains_substantial_text(brief, item.get("summary", "")):
                missing_items.append(f"areas_of_agreement.summary:{item.get('theme', '')}")
            analyst_line = f"**Analysts:** {', '.join(_normalize_analyst_names(item.get('analysts')))}"
            if not _contains_substantial_text(brief, analyst_line):
                mismatched_items.append(f"areas_of_agreement.analysts:{item.get('theme', '')}")

        for item in synthesis.get("areas_of_disagreement", []) or []:
            if not _contains_substantial_text(brief, f"### {item.get('theme', '')}"):
                missing_items.append(f"areas_of_disagreement.theme:{item.get('theme', '')}")
            if not _contains_substantial_text(brief, f"**Type:** {item.get('disagreement_type', '')}"):
                mismatched_items.append(f"areas_of_disagreement.disagreement_type:{item.get('theme', '')}")
            if not _contains_substantial_text(brief, item.get("why_it_matters", "")):
                missing_items.append(f"areas_of_disagreement.why_it_matters:{item.get('theme', '')}")

        for item in synthesis.get("strongest_positive_signals", []) or []:
            if not _contains_substantial_text(brief, f"### {item.get('signal', '')}"):
                missing_items.append(f"strongest_positive_signals.signal:{item.get('signal', '')}")
            supported_line = f"**Supported by:** {', '.join(_normalize_analyst_names(item.get('supported_by')))}"
            if not _contains_substantial_text(brief, supported_line):
                mismatched_items.append(f"strongest_positive_signals.supported_by:{item.get('signal', '')}")

        for item in synthesis.get("most_important_risks", []) or []:
            if not _contains_substantial_text(brief, f"### {item.get('risk', '')}"):
                missing_items.append(f"most_important_risks.risk:{item.get('risk', '')}")
            if not _contains_substantial_text(brief, f"**Severity:** {item.get('severity', '')}"):
                mismatched_items.append(f"most_important_risks.severity:{item.get('risk', '')}")
            raised_line = f"**Raised by:** {', '.join(_normalize_analyst_names(item.get('raised_by')))}"
            if not _contains_substantial_text(brief, raised_line):
                mismatched_items.append(f"most_important_risks.raised_by:{item.get('risk', '')}")

        for item in synthesis.get("critical_unknowns", []) or []:
            if not _contains_substantial_text(brief, f"### {item.get('unknown', '')}"):
                missing_items.append(f"critical_unknowns.unknown:{item.get('unknown', '')}")
            if not _contains_substantial_text(brief, item.get("why_it_matters", "")):
                missing_items.append(f"critical_unknowns.why_it_matters:{item.get('unknown', '')}")

        for index, item in enumerate(synthesis.get("investigation_questions", []) or [], start=1):
            if not _contains_substantial_text(brief, f"### Question {index}"):
                missing_items.append(f"investigation_questions.question_number:{index}")
            if not _contains_substantial_text(brief, item.get("question", "")):
                missing_items.append(f"investigation_questions.question:{index}")
            if not _contains_substantial_text(brief, item.get("reason", "")):
                missing_items.append(f"investigation_questions.reason:{index}")
            if not _contains_substantial_text(brief, item.get("linked_unknown_or_risk", "")):
                mismatched_items.append(f"investigation_questions.linked_unknown_or_risk:{index}")

        notes = synthesis.get("evidence_quality_notes", []) or []
        if notes:
            for note in notes:
                if not _contains_substantial_text(brief, note):
                    missing_items.append(f"evidence_quality_notes:{note}")
        else:
            expected = "No material evidence-quality warnings were recorded."
            if not _contains_substantial_text(brief, expected):
                mismatched_items.append("evidence_quality_notes.default_message")

        for item in synthesis.get("synthesis_limits", []) or []:
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

    def build(self, *, include_evidence_ids: bool = False) -> Dict[str, Path]:
        synthesis, brief = self._load_inputs()
        checks = {
            "required_sections": self._required_sections_check(brief, self.company),
            "forbidden_language": self._forbidden_language_check(brief),
            "evidence_id_visibility": self._evidence_id_visibility_check(
                brief,
                include_evidence_ids=include_evidence_ids,
            ),
            "analyst_names": self._analyst_names_check(brief),
            "source_fidelity": self._source_fidelity_check(synthesis, brief),
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
            "generated_at": utc_now(),
        }
        return {
            "committee_brief_qa.json": _write_json(self.output_path, payload),
        }
