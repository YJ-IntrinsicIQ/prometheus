from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .forbidden_language import find_forbidden_recommendation_language

ANALYST_ORDER = ["graham", "buffett", "fisher", "munger", "lynch"]
FORBIDDEN_BRIEF_TERMS = (
    "pcim",
    "evidence_id",
    "evidence_ids",
    "ev_",
    "analysis_mode",
    "sections_consumed",
    "evidence_map",
    "reasoning_limits",
    "source_item_id",
    "source_artifact",
    "compacted for token budget",
    "provided in the.",
    "but the provides no",
)
LENS_CONFIG = {
    "graham": {
        "title": "Graham School of Thought: Downside Protection",
        "lens_heading": "Downside Protection",
        "lens_text": "This lens looks for balance-sheet caution, financial resilience, and whether the downside appears protected when conditions get worse.",
    },
    "buffett": {
        "title": "Buffett School of Thought: Business Quality & Capital Allocation",
        "lens_heading": "Business Quality & Capital Allocation",
        "lens_text": "This lens focuses on business durability, moat strength, management rationality, and whether capital appears to be allocated with long-term discipline.",
    },
    "fisher": {
        "title": "Fisher School of Thought: Growth Quality & Management Ambition",
        "lens_heading": "Growth Quality & Management Ambition",
        "lens_text": "This lens looks for credible growth runway, strong execution, product strength, and ambition that is backed by real follow-through.",
    },
    "munger": {
        "title": "Munger School of Thought: Incentives, Governance & Avoidable Mistakes",
        "lens_heading": "Incentives, Governance & Avoidable Mistakes",
        "lens_text": "This lens focuses on incentive alignment, governance sanity, behavioural discipline, and whether avoidable mistakes are starting to pile up.",
    },
    "lynch": {
        "title": "Lynch School of Thought: Simple Story, Growth Runway & Hype Check",
        "lens_heading": "Simple Story, Growth Runway & Hype Check",
        "lens_text": "This lens asks whether the business story is understandable, whether growth looks practical, and whether the numbers support the narrative.",
    },
}
REQUIRED_BRIEF_KEYS = {
    "title",
    "lens",
    "what_looks_good",
    "what_needs_caution",
    "what_is_missing",
    "bottom_line",
}
MAX_BRIEF_ITEMS = 5
MAX_BRIEF_BULLET_CHARS = 350
MAX_BRIEF_LENS_CHARS = 700
MAX_BRIEF_BOTTOM_LINE_CHARS = 900
MIN_BRIEF_LENS_CHARS = 40


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


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _normalize_bullet(text: Any) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.rstrip(".") + "." if cleaned and not cleaned.endswith(".") else cleaned


def _brief_validation_error(analyst: str, field: str, reason: str) -> ValueError:
    return ValueError(f'Invalid user_facing_brief for analyst {analyst}: field "{field}" {reason}')


def _validate_no_internal_language(text: str, *, analyst: str, field: str, max_chars: Optional[int] = None) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        raise _brief_validation_error(analyst, field, "is required")
    lowered = cleaned.lower()
    for term in FORBIDDEN_BRIEF_TERMS:
        if term in lowered:
            forbidden = "PCIM" if term == "pcim" else term
            raise _brief_validation_error(analyst, field, f'contains forbidden term "{forbidden}"')
    if max_chars is not None and len(cleaned) > max_chars:
        raise _brief_validation_error(analyst, field, f"exceeds max length {max_chars}")
    if find_forbidden_recommendation_language(cleaned):
        raise _brief_validation_error(analyst, field, "contains recommendation language")
    return cleaned


def _normalize_brief_list(value: Any, *, analyst: str, field: str) -> List[str]:
    if not isinstance(value, list):
        raise _brief_validation_error(analyst, field, "must be a list")
    if len(value) > MAX_BRIEF_ITEMS:
        raise _brief_validation_error(analyst, field, f"contains more than {MAX_BRIEF_ITEMS} items")
    normalized: List[str] = []
    for item in value:
        text = _validate_no_internal_language(
            str(item or "").strip(),
            analyst=analyst,
            field=field,
            max_chars=MAX_BRIEF_BULLET_CHARS,
        )
        normalized.append(_normalize_bullet(text))
    if not normalized:
        raise _brief_validation_error(analyst, field, "must not be empty")
    return normalized


def validate_user_facing_brief(analyst: str, value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("user_facing_brief must be an object")
    missing = REQUIRED_BRIEF_KEYS - set(value.keys())
    if missing:
        raise ValueError(f"user_facing_brief missing required keys: {sorted(missing)}")

    title = _validate_no_internal_language(value.get("title"), analyst=analyst, field="title")
    lens = _validate_no_internal_language(
        value.get("lens"),
        analyst=analyst,
        field="lens",
        max_chars=MAX_BRIEF_LENS_CHARS,
    )
    bottom_line = _validate_no_internal_language(
        value.get("bottom_line"),
        analyst=analyst,
        field="bottom_line",
        max_chars=MAX_BRIEF_BOTTOM_LINE_CHARS,
    )

    expected_title = LENS_CONFIG.get(analyst, {}).get("title")
    expected_lens = LENS_CONFIG.get(analyst, {}).get("lens_text")
    if expected_title and title != expected_title:
        raise _brief_validation_error(
            analyst,
            "title",
            f"must match the canonical analyst title: {expected_title}",
        )
    if len(lens) < MIN_BRIEF_LENS_CHARS or lens.strip().lower() == analyst.lower():
        raise _brief_validation_error(
            analyst,
            "lens",
            "must be a full user-facing lens sentence, not a placeholder",
        )
    if expected_lens and lens.strip().lower() == {
        "graham": "benjamin graham",
        "buffett": "warren buffett",
        "fisher": "phil fisher",
        "munger": "charlie munger",
        "lynch": "peter lynch",
    }.get(analyst, ""):
        raise _brief_validation_error(
            analyst,
            "lens",
            "must be a full user-facing lens sentence, not just the investor name",
        )

    if not any(value.get(key) for key in ("what_looks_good", "what_needs_caution", "what_is_missing")):
        raise _brief_validation_error(
            analyst,
            "user_facing_brief",
            "must include content in at least one of what_looks_good, what_needs_caution, or what_is_missing",
        )

    return {
        "title": title,
        "lens": lens,
        "what_looks_good": _normalize_brief_list(value.get("what_looks_good"), analyst=analyst, field="what_looks_good"),
        "what_needs_caution": _normalize_brief_list(value.get("what_needs_caution"), analyst=analyst, field="what_needs_caution"),
        "what_is_missing": _normalize_brief_list(value.get("what_is_missing"), analyst=analyst, field="what_is_missing"),
        "bottom_line": bottom_line,
    }


def _render_brief(analyst: str, payload: Dict[str, Any]) -> str:
    brief = payload.get("user_facing_brief")
    if not isinstance(brief, dict):
        raise ValueError(
            f"{analyst}_analysis.json is missing user_facing_brief; markdown generation requires embedded user_facing_brief"
        )
    brief = validate_user_facing_brief(analyst, brief)

    lines = [
        f"# {brief['title']}",
        "",
        "## Lens",
        brief["lens"],
        "",
        "## What Looks Good",
    ]
    lines.extend([f"- {item}" for item in brief["what_looks_good"]])
    lines.extend(
        [
            "",
            "## What Needs Caution",
        ]
    )
    lines.extend([f"- {item}" for item in brief["what_needs_caution"]])
    lines.extend(
        [
            "",
            "## What Is Missing",
        ]
    )
    lines.extend([f"- {item}" for item in brief["what_is_missing"]])
    lines.extend(
        [
            "",
            "## Bottom Line",
            brief["bottom_line"],
            "",
        ]
    )
    return "\n".join(lines)


class InvestorBriefBuilder:
    def __init__(self, company: str, companies_root: Path | str = Path("companies")):
        self.company = company
        self.companies_root = Path(companies_root)
        self.panel_dir = self.companies_root / company / "company_memory" / "investor_panel"
        self.briefs_dir = self.panel_dir / "briefs"

    def _analysis_path(self, analyst: str) -> Path:
        return self.panel_dir / f"{analyst}_analysis.json"

    def _brief_path(self, analyst: str) -> Path:
        return self.briefs_dir / f"{analyst}_brief.md"

    def _brief_index_payload(
        self,
        source_analysis_files: List[str],
        briefs_generated: List[str],
        hidden_evidence_ids_by_analyst: Dict[str, List[str]],
        limitations: List[str],
    ) -> Dict[str, Any]:
        return {
            "company": self.company,
            "generated_at": utc_now(),
            "source_analysis_files": source_analysis_files,
            "briefs_generated": briefs_generated,
            "hidden_evidence_ids_by_analyst": hidden_evidence_ids_by_analyst,
            "limitations": limitations,
        }

    def build(self) -> Dict[str, Path]:
        written: Dict[str, Path] = {}
        source_analysis_files: List[str] = []
        briefs_generated: List[str] = []
        hidden_evidence_ids_by_analyst: Dict[str, List[str]] = {}
        limitations: List[str] = []

        for analyst in ANALYST_ORDER:
            analysis_path = self._analysis_path(analyst)
            if not analysis_path.exists():
                limitations.append(f"{analyst}_analysis.json was not found, so no brief was generated for that analyst.")
                continue

            payload = _load_json(analysis_path)
            if not payload:
                limitations.append(f"{analyst}_analysis.json was unreadable or empty, so no brief was generated for that analyst.")
                continue

            try:
                brief_text = _render_brief(analyst, payload)
            except ValueError as exc:
                limitations.append(f"{analyst}_analysis.json was skipped: {exc}")
                continue
            brief_path = self._brief_path(analyst)
            written[brief_path.name] = _write_text(brief_path, brief_text)
            source_analysis_files.append(str(analysis_path))
            briefs_generated.append(str(brief_path))
            hidden_evidence_ids_by_analyst[analyst] = list(payload.get("evidence_ids", []) or [])

        index_payload = self._brief_index_payload(
            source_analysis_files=source_analysis_files,
            briefs_generated=briefs_generated,
            hidden_evidence_ids_by_analyst=hidden_evidence_ids_by_analyst,
            limitations=limitations or [
                "Briefs are derived only from analyst analysis JSON files and intentionally omit internal trace data from the markdown output."
            ],
        )
        index_path = self.briefs_dir / "brief_index.json"
        written[index_path.name] = _write_json(index_path, index_payload)
        return written
