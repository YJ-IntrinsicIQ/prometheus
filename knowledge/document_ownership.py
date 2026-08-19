from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict


FY_LABEL_RE = re.compile(r"\bfy\s*(?P<year>\d{2}|\d{4})\b", re.IGNORECASE)
YEAR_RANGE_RE = re.compile(r"\b(?P<start>20\d{2})\s*[-–]\s*(?P<end>\d{2}|20\d{2})\b")
REPORT_HEADING_RE = re.compile(
    r"(?:integrated\s+)?annual\s+report(?:\s+fy\s*\d{2,4}|\s+20\d{2}\s*[-–]\s*\d{2,4})?",
    re.IGNORECASE,
)
COMPACT_REPORT_RE = re.compile(r"\b[a-z0-9_-]*(?:integrated)?report(?P<year>\d{2})(?!\d)", re.IGNORECASE)


def normalize_fiscal_year(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "")
    if not text:
        return ""
    if text.startswith("fy") and text[2:].isdigit():
        return f"fy{text[2:][-2:]}"
    if text.isdigit():
        return f"fy{text[-2:]}"
    match = FY_LABEL_RE.search(text)
    if match:
        return f"fy{match.group('year')[-2:]}"
    return ""


def _fy_from_year_range(start: str, end: str) -> str:
    if len(end) == 2:
        return f"fy{end}"
    return f"fy{end[-2:]}"


def infer_document_reporting_period(text: Any, *, filename: Any = "") -> Dict[str, Any]:
    haystack = " ".join(str(text or "").split())
    filename_text = Path(str(filename or "")).name
    candidates = []

    for source_name, source_text in (("filename", filename_text), ("text", haystack[:360])):
        if not source_text:
            continue
        compact_source = re.sub(r"[^a-z0-9]+", "", source_text.lower()) if source_name == "filename" else source_text
        compact_match = COMPACT_REPORT_RE.search(compact_source)
        if compact_match:
            candidates.append(
                {
                    "period": f"fy{compact_match.group('year')}",
                    "basis": f"{source_name} compact report marker",
                    "evidence": compact_match.group(0),
                }
            )
        for heading in REPORT_HEADING_RE.finditer(source_text):
            window = source_text[heading.start() : min(len(source_text), heading.end() + 80)]
            range_match = YEAR_RANGE_RE.search(window)
            if range_match:
                candidates.append(
                    {
                        "period": _fy_from_year_range(range_match.group("start"), range_match.group("end")),
                        "basis": f"{source_name} annual report year range",
                        "evidence": window,
                    }
                )
                continue
            fy_match = FY_LABEL_RE.search(window)
            if fy_match:
                candidates.append(
                    {
                        "period": f"fy{fy_match.group('year')[-2:]}",
                        "basis": f"{source_name} annual report FY label",
                        "evidence": window,
                    }
                )
                continue

    if not candidates:
        return {"status": "unknown", "reporting_period": "", "basis": [], "evidence": []}

    period_counts: Dict[str, int] = {}
    for candidate in candidates:
        period = str(candidate["period"])
        period_counts[period] = period_counts.get(period, 0) + 1
    reporting_period = max(period_counts.items(), key=lambda item: item[1])[0]
    supporting = [item for item in candidates if item["period"] == reporting_period]
    return {
        "status": "resolved" if len(period_counts) == 1 else "warning",
        "reporting_period": reporting_period,
        "basis": [item["basis"] for item in supporting],
        "evidence": [item["evidence"] for item in supporting[:3]],
        "candidates": candidates,
    }


def assess_source_period_ownership(*, source_year: Any, source_text: Any = "", filename: Any = "") -> Dict[str, Any]:
    expected = normalize_fiscal_year(source_year)
    inferred = infer_document_reporting_period(source_text, filename=filename)
    actual = str(inferred.get("reporting_period") or "")
    if not expected or not actual:
        return {
            "status": "unknown",
            "expected_source_period": expected,
            "inferred_reporting_period": actual,
            "basis": inferred.get("basis") or [],
            "limitations": ["document reporting period could not be verified"],
        }
    if expected == actual:
        return {
            "status": "pass",
            "expected_source_period": expected,
            "inferred_reporting_period": actual,
            "basis": inferred.get("basis") or [],
            "limitations": [],
        }
    return {
        "status": "fail",
        "expected_source_period": expected,
        "inferred_reporting_period": actual,
        "basis": inferred.get("basis") or [],
        "limitations": [f"source text appears to belong to {actual}, not {expected}"],
        "failure_class": "SOURCE_PERIOD_VS_TARGET_PERIOD_CONFLICT",
    }
