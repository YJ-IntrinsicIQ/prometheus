from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple


ALLOWED_BASIS = {"standalone", "consolidated", "unknown", "mixed"}
ALLOWED_BASIS_CONFIDENCE = {"high", "medium", "low"}

STANDALONE_PATTERNS: Tuple[str, ...] = (
    "standalone financial statements",
    "standalone balance sheet",
    "standalone statement of profit and loss",
    "standalone cash flow statement",
    "standalone financial results",
    "separate financial statements",
    "report on the audit of the standalone financial statements",
)

CONSOLIDATED_PATTERNS: Tuple[str, ...] = (
    "consolidated financial statements",
    "consolidated balance sheet",
    "consolidated statement of profit and loss",
    "consolidated cash flow statement",
    "consolidated financial results",
    "group financial statements",
    "report on the audit of the consolidated financial statements",
)


def _normalize(text: Any) -> str:
    value = str(text or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _contains_any(text: str, patterns: Iterable[str]) -> List[str]:
    return [pattern for pattern in patterns if pattern in text]


def detect_basis(
    *,
    text: str = "",
    signals: Sequence[str] | None = None,
) -> Tuple[str, str, List[str]]:
    normalized = _normalize(text)
    reasons: List[str] = []
    standalone_hits = _contains_any(normalized, STANDALONE_PATTERNS)
    consolidated_hits = _contains_any(normalized, CONSOLIDATED_PATTERNS)

    standalone_score = len(standalone_hits)
    consolidated_score = len(consolidated_hits)

    signal_values = [str(item) for item in signals or []]
    if "standalone_hint" in signal_values:
        standalone_score += 1
        reasons.append("signal:standalone_hint")
    if "consolidated_hint" in signal_values:
        consolidated_score += 1
        reasons.append("signal:consolidated_hint")

    reasons.extend(f"text:{item}" for item in standalone_hits)
    reasons.extend(f"text:{item}" for item in consolidated_hits)

    if standalone_score == 0 and consolidated_score == 0:
        return "unknown", "low", reasons
    if standalone_score and consolidated_score:
        if standalone_score == consolidated_score:
            reasons.append("conflict:both_basis_signals")
            return "unknown", "low", reasons
        if standalone_score > consolidated_score:
            reasons.append("resolved:standalone_stronger")
            return "standalone", "medium", reasons
        reasons.append("resolved:consolidated_stronger")
        return "consolidated", "medium", reasons
    if consolidated_score:
        return "consolidated", "high" if consolidated_score >= 2 else "medium", reasons
    return "standalone", "high" if standalone_score >= 2 else "medium", reasons


def available_basis_options(basis_views: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]]) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    for basis in ("consolidated", "standalone", "unknown"):
        section_map = basis_views.get(basis, {}) if isinstance(basis_views, dict) else {}
        populated_fields: List[str] = []
        critical_fields: List[str] = []
        for section_name, fields in section_map.items():
            if not isinstance(fields, dict):
                continue
            for field_name, entry in fields.items():
                if not isinstance(entry, dict):
                    continue
                has_value = entry.get("value_original") not in (None, "", []) or isinstance(entry.get("value_crore"), (int, float))
                if not has_value:
                    continue
                field_path = f"{section_name}.{field_name}"
                populated_fields.append(field_path)
                if field_path in {
                    "profit_and_loss.revenue",
                    "profit_and_loss.pat",
                    "balance_sheet.total_assets",
                    "balance_sheet.net_worth",
                    "cash_flow.cfo",
                }:
                    critical_fields.append(field_path)
        summary[basis] = {
            "field_count": len(populated_fields),
            "critical_count": len(critical_fields),
            "populated_fields": populated_fields,
            "critical_fields": critical_fields,
        }
    return summary


def choose_preferred_basis(basis_views: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]]) -> Tuple[str, List[str], str, str]:
    summary = available_basis_options(basis_views)
    available = [basis for basis in ("consolidated", "standalone", "unknown") if summary[basis]["field_count"] > 0]
    consolidated_ready = summary["consolidated"]["critical_count"] >= 2 or summary["consolidated"]["field_count"] >= 5
    standalone_ready = summary["standalone"]["critical_count"] >= 2 or summary["standalone"]["field_count"] >= 5

    if summary["consolidated"]["field_count"] > 0 and consolidated_ready:
        confidence = "high" if summary["consolidated"]["critical_count"] >= 4 else "medium"
        return "consolidated", available, "selected consolidated because it is available and reasonably complete", confidence
    if summary["standalone"]["field_count"] > 0 and standalone_ready:
        confidence = "high" if summary["standalone"]["critical_count"] >= 4 else "medium"
        return "standalone", available, "selected standalone because consolidated was unavailable or less complete", confidence
    if summary["consolidated"]["field_count"] > 0:
        return "consolidated", available, "selected consolidated because it was the only explicit basis available", "medium"
    if summary["standalone"]["field_count"] > 0:
        return "standalone", available, "selected standalone because it was the only explicit basis available", "medium"
    return "unknown", available, "basis could not be determined from available financial table evidence", "low"
