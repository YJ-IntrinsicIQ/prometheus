#!/usr/bin/env python3
"""
Prometheus Investor Acceptance Harness
======================================

Traces the full pipeline from canonical artifact → answer builder → saved card
for each question in an investor acceptance suite.

This is a measuring instrument. It does NOT change routing, quarantine policy,
synthesis logic, or UI behaviour. It records what actually happened.

Usage
-----
  python pipelines/run_investor_acceptance.py sun_pharma
  python pipelines/run_investor_acceptance.py sun_pharma --questions recovery_baseline
  python pipelines/run_investor_acceptance.py sun_pharma --questions all
  python pipelines/run_investor_acceptance.py sun_pharma --out-dir custom/path

Output
------
  acceptance_reports/<company>/acceptance_summary.json
  acceptance_reports/<company>/question_traces/<question_id>.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from intelligence.ask_intrinsiciq.answer_cards import (
    ANSWER_BUILDERS,
    build_answer_for_question,
)
from intelligence.ask_intrinsiciq.loader import SOURCE_REGISTRY, load_company_memory_sources


# ─── Question sets ────────────────────────────────────────────────────────────

RECOVERY_BASELINE_QUESTIONS = [
    "what-has-management-promised",
    "did-past-claims-come-true",
    "what-projects-are-underway",
    "what-would-buffett-focus-on",
    "are-per-share-economics-improving",
]

ALL_QUESTIONS = [
    "what-does-company-do",
    "who-are-the-customers",
    "how-does-it-make-money",
    "are-profits-converting-into-cash",
    "what-is-owner-earnings",
    "is-working-capital-a-concern",
    "are-per-share-economics-improving",
    "what-has-management-promised",
    "did-past-claims-come-true",
    "what-projects-are-underway",
    "how-is-capacity-changing",
    "what-is-management-commentary-saying",
    "how-is-capital-allocated",
    "what-incentives-matter",
    "what-can-break-the-thesis",
    "which-disclosure-is-missing",
    "what-evidence-would-change-the-view",
    "what-needs-management-clarification",
    "what-should-i-ask-ir",
    "what-remains-unresolved",
    "what-would-graham-worry-about",
    "what-would-buffett-focus-on",
    "where-would-fisher-be-curious",
    "what-would-munger-avoid",
    "how-would-lynch-explain-it",
]

QUESTION_SETS = {
    "recovery_baseline": RECOVERY_BASELINE_QUESTIONS,
    "all": ALL_QUESTIONS,
}


# ─── Expected canonical owner map ─────────────────────────────────────────────
# Defines what SHOULD be the primary source for each question.
# Harness compares against actual to detect PATH_DIVERGENCE.

EXPECTED_OWNER_MAP: dict[str, dict[str, Any]] = {
    "what-has-management-promised": {
        "expected_primary": "gold_promise_tracker",
        "expected_secondary": "management_commitments",
        "forbidden_primary": None,
        "gold_expected": True,
        "freshness_cycles": 2,
    },
    "did-past-claims-come-true": {
        "expected_primary": "gold_promise_tracker",
        "expected_secondary": "gold_credibility",
        "forbidden_primary": "management_progression",
        "gold_expected": True,
        "freshness_cycles": 3,
    },
    "what-projects-are-underway": {
        "expected_primary": "projects_registry",
        "expected_secondary": "gold_strategy_evolution",
        "forbidden_primary": None,
        "gold_expected": False,
        "freshness_cycles": None,
        "temporal_filter_expected": True,
    },
    "what-would-buffett-focus-on": {
        "expected_primary": "buffett_analysis",
        "expected_secondary": "committee_synthesis",
        "forbidden_primary": None,
        "gold_expected": True,
        "freshness_cycles": 2,
    },
    "are-per-share-economics-improving": {
        "expected_primary": "per_share_compounding_analysis",
        "expected_secondary": "financial_truth_pack",
        "forbidden_primary": None,
        "gold_expected": False,
        "freshness_cycles": None,
        "longitudinal_synthesis_expected": True,
        "min_series_length_for_synthesis": 5,
    },
}

# Gold source keys in SOURCE_REGISTRY
GOLD_SOURCE_KEYS = {k for k in SOURCE_REGISTRY if k.startswith("gold_")}

CERTIFICATION_CONTRACT_VERSION = "INVESTOR_CERTIFICATION_V2.0"

DOMAIN_MAP: dict[str, list[str]] = {
    "business_understanding": [
        "what-does-company-do", "who-are-the-customers", "how-does-it-make-money",
    ],
    "financial_intelligence": [
        "are-profits-converting-into-cash", "what-is-owner-earnings",
        "is-working-capital-a-concern", "are-per-share-economics-improving",
        "how-is-capital-allocated",
    ],
    "management_accountability": [
        "what-has-management-promised", "did-past-claims-come-true",
        "what-is-management-commentary-saying", "what-incentives-matter",
    ],
    "operational_intelligence": [
        "what-projects-are-underway", "how-is-capacity-changing",
    ],
    "risk_and_diligence": [
        "what-can-break-the-thesis", "which-disclosure-is-missing",
        "what-evidence-would-change-the-view", "what-needs-management-clarification",
        "what-should-i-ask-ir", "what-remains-unresolved",
    ],
    "investor_judgment": [
        "what-would-graham-worry-about", "what-would-buffett-focus-on",
        "where-would-fisher-be-curious", "what-would-munger-avoid",
        "how-would-lynch-explain-it",
    ],
}


# ─── V2 verdict logic ─────────────────────────────────────────────────────────

HARD_FLOOR_CHECKS = {"evidence_backed", "internally_consistent"}


def _detect_critical_failures_v2(
    question_id: str,
    answer: dict[str, Any],
    defects: list[str],
    semantic_checks: dict[str, Any],
) -> list[str]:
    """
    Detect auto-detectable critical failures (CF-A001 through CF-A004).
    Returns list of critical failure IDs detected.
    """
    failures: list[str] = []

    # CF-A001: Internal contradiction (answer_status vs evidence_status)
    if semantic_checks.get("internally_consistent", {}).get("result") == "FAIL":
        failures.append("CF-A001")

    # CF-A002: Stale artifact serving materially wrong data
    if "STALE_ARTIFACT" in defects and "BAD_EVIDENCE_LINK" in defects:
        failures.append("CF-A002")

    # CF-A003: Pre-2020 event as current project
    if question_id == "what-projects-are-underway":
        kps = [str(kp) for kp in (answer.get("key_points") or [])]
        for kp in kps:
            if re.search(r"\b201[0-9]\b", kp):
                failures.append("CF-A003")
                break

    # CF-A004: Builder template language in user output
    if "BAD_RENDERING" in defects:
        kps_text = " ".join(str(kp) for kp in (answer.get("key_points") or []))
        if _TEMPLATE_PATTERNS.search(kps_text):
            failures.append("CF-A004")

    return list(dict.fromkeys(failures))  # deduplicate, preserve order


def _determine_verdict_v2(
    semantic_checks: dict[str, Any],
    critical_failures: list[str],
) -> tuple[str, str]:
    """
    Determine three-tier V2 verdict.
    Returns (verdict, rationale).
    Hard-floor checks: evidence_backed, internally_consistent → REJECTED on FAIL.
    Soft-floor checks: all others → PARTIAL on FAIL.
    Critical failures → REJECTED regardless of check results.
    """
    if critical_failures:
        return "REJECTED", f"Critical failure(s) detected: {critical_failures}"

    for check_name in HARD_FLOOR_CHECKS:
        check = semantic_checks.get(check_name, {})
        if check.get("result") == "FAIL":
            return "REJECTED", f"Hard-floor check failed: {check_name} — {check.get('detail', '')}"

    applicable = {k: v for k, v in semantic_checks.items() if v.get("result") != "N/A"}
    all_pass = all(v.get("result") == "PASS" for v in applicable.values())
    if all_pass:
        return "ACCEPTED", "All applicable semantic checks PASS"

    failing = [k for k, v in applicable.items() if v.get("result") == "FAIL"]
    return "PARTIAL", f"Soft-floor check(s) failed: {failing}"


def _compute_grade_v2(
    accepted: int,
    rejected: int,
    partial: int,
    total: int,
    critical_failures: int,
    domain_accepted: dict[str, int],
) -> dict[str, Any]:
    """
    Compute investor-grade gate and grade taxonomy from verdict distribution.
    """
    if total == 0:
        return {"grade": "UNSAFE", "investor_grade_pass": False, "reason": "No questions evaluated"}

    accepted_pct = accepted / total

    # UNSAFE: any critical failure, or fewer than 8 ACCEPTED
    if critical_failures > 0 or accepted < 8:
        return {
            "grade": "UNSAFE",
            "investor_grade_pass": False,
            "reason": (
                f"Critical failures: {critical_failures}" if critical_failures > 0
                else f"Only {accepted} ACCEPTED (minimum 8 required)"
            ),
        }

    # Evaluate investor-grade gate conditions
    cond_accepted_count = accepted >= 15
    cond_accepted_pct = accepted_pct >= 0.60
    cond_rejected_count = rejected <= 2
    cond_crit_zero = critical_failures == 0
    cond_fi_floor = domain_accepted.get("financial_intelligence", 0) >= 1
    cond_ma_floor = domain_accepted.get("management_accountability", 0) >= 1
    cond_domain_floors = cond_fi_floor and cond_ma_floor

    gate_pass = all([
        cond_accepted_count, cond_accepted_pct, cond_rejected_count,
        cond_crit_zero, cond_domain_floors,
    ])

    if gate_pass:
        return {
            "grade": "CERTIFIED",
            "investor_grade_pass": True,
            "reason": (
                f"{accepted}/{total} ACCEPTED ({accepted_pct:.0%}), "
                f"{rejected} REJECTED, 0 critical failures, domain floors met"
            ),
            "gate_detail": {
                "accepted_count": cond_accepted_count,
                "accepted_pct": cond_accepted_pct,
                "rejected_count": cond_rejected_count,
                "critical_failures_zero": cond_crit_zero,
                "financial_intelligence_floor": cond_fi_floor,
                "management_accountability_floor": cond_ma_floor,
            },
        }

    # Count gate conditions met (for NEAR_CERTIFICATION check)
    gate_conditions = [
        cond_accepted_count, cond_accepted_pct, cond_rejected_count,
        cond_fi_floor, cond_ma_floor,
    ]
    conditions_met = sum(gate_conditions)

    if conditions_met >= 4:  # NEAR_CERTIFICATION: 4 of 5 conditions met, 0 critical failures
        return {
            "grade": "NEAR_CERTIFICATION",
            "investor_grade_pass": False,
            "reason": f"{conditions_met}/5 gate conditions met, critical failures = 0",
            "gate_detail": {
                "accepted_count": cond_accepted_count,
                "accepted_pct": cond_accepted_pct,
                "rejected_count": cond_rejected_count,
                "financial_intelligence_floor": cond_fi_floor,
                "management_accountability_floor": cond_ma_floor,
            },
        }

    return {
        "grade": "DEVELOPING",
        "investor_grade_pass": False,
        "reason": f"{conditions_met}/5 gate conditions met, critical failures = 0",
        "gate_detail": {
            "accepted_count": cond_accepted_count,
            "accepted_pct": cond_accepted_pct,
            "rejected_count": cond_rejected_count,
            "financial_intelligence_floor": cond_fi_floor,
            "management_accountability_floor": cond_ma_floor,
        },
    }


# ─── Source access tracking ────────────────────────────────────────────────────

class _SourcesProxy:
    """
    Wraps the inner sources dict and records every source name accessed
    via .get(). Allows the harness to observe actual source access without
    modifying answer_cards.py.
    """

    def __init__(self, inner: dict[str, Any], log: list[str]) -> None:
        self._inner = inner
        self._log = log

    def get(self, key: str, default: Any = None) -> Any:
        result = self._inner.get(key, default)
        # Only log legitimate source names (not empty fallback lookups)
        if key in self._inner:
            if key not in self._log:
                self._log.append(key)
        return result

    def __contains__(self, key: object) -> bool:
        return key in self._inner

    def __getitem__(self, key: str) -> Any:
        if key not in self._log:
            self._log.append(str(key))
        return self._inner[key]

    def items(self) -> Any:
        return self._inner.items()

    def keys(self) -> Any:
        return self._inner.keys()

    def values(self) -> Any:
        return self._inner.values()


class TrackedBundle(dict):
    """
    Dict subclass that intercepts .get("sources") to return a proxy
    that records every source access. All other keys pass through normally.
    """

    def __init__(self, base: dict[str, Any]) -> None:
        super().__init__(base)
        self.access_log: list[str] = []
        self._proxy = _SourcesProxy(base.get("sources", {}), self.access_log)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "sources":
            return self._proxy
        return super().get(key, default)

    def __getitem__(self, key: str) -> Any:
        if key == "sources":
            return self._proxy
        return super().__getitem__(key)


# ─── Semantic checks ───────────────────────────────────────────────────────────

_NUMERIC_RE = re.compile(r"₹\s*[\d,]+|[\d,.]+\s*%|[\d,.]+\s*(?:cr|crore|lakh|bn|mn|day|year)|fy\d{2,4}", re.IGNORECASE)
_FISCAL_YEAR_RE = re.compile(r"\bfy\s*20?\d{2}\b|\bfy\s*\d{2}\b", re.IGNORECASE)
_TEMPLATE_PATTERNS = re.compile(
    r"investment lens implication|implication first:|is claim evidence|regenerate the progression|improve upstream progression",
    re.IGNORECASE,
)
_GENERIC_PHARMA_RE = re.compile(
    r"^(?:the company operates|the company is engaged|the company focuses|"
    r"management has committed to growth|the pharmaceutical industry|"
    r"the company continues to focus on|the company aims to)[^.]*\.$",
    re.IGNORECASE,
)

def _text_of(answer: dict[str, Any]) -> str:
    parts = [
        str(answer.get("simple_answer") or ""),
        " ".join(str(kp) for kp in (answer.get("key_points") or [])),
        str(answer.get("detailed_explanation") or ""),
    ]
    return " ".join(parts)


def _check_specific(answer: dict[str, Any]) -> tuple[str, str]:
    text = _text_of(answer)
    if _NUMERIC_RE.search(text):
        return "PASS", "contains numeric metric or fiscal year reference"
    named_entities = _extract_named_entities(answer)
    if named_entities:
        return "PASS", f"contains named entities: {named_entities[:3]}"
    return "FAIL", "no named metric, number, ratio, date, or company-specific entity found"


def _check_longitudinal(answer: dict[str, Any], source_context: dict[str, Any]) -> tuple[str, str]:
    text = _text_of(answer)
    years = set(_FISCAL_YEAR_RE.findall(text.lower()))
    series_len = source_context.get("per_share_series_length", 0)
    if series_len >= 3 and len(years) >= 2:
        return "PASS", f"references {len(years)} fiscal years with {series_len}-year series available"
    if series_len >= 5 and len(years) < 2:
        return "FAIL", f"only {len(years)} fiscal year(s) referenced despite {series_len}-year series being available"
    if len(years) >= 2:
        return "PASS", f"references {len(years)} fiscal years"
    if series_len == 0:
        return "N/A", "no multi-year series in scope for this question"
    return "FAIL", f"only {len(years)} fiscal year(s) referenced"


def _check_evidence_backed(answer: dict[str, Any], sources_accessed: list[str]) -> tuple[str, str]:
    ev = answer.get("evidence_summary") or {}
    status = str(ev.get("status") or "")
    if status in ("direct", "derived", "partial"):
        # Check there's an actual source
        meaningful = [s for s in sources_accessed if s not in ("cim", "pcim")]
        if meaningful:
            return "PASS", f"evidence_status={status!r}; sources accessed: {meaningful[:4]}"
        return "FAIL", f"evidence_status={status!r} but no meaningful source accessed"
    if status == "missing":
        return "FAIL", "evidence_summary.status=missing"
    return "FAIL", f"evidence_summary.status={status!r} (not a positive evidence state)"


def _check_internally_consistent(answer: dict[str, Any]) -> tuple[str, str]:
    # Check for obvious contradiction: "not_supported" status with "direct" evidence
    ans_status = str(answer.get("answer_status") or "")
    ev_status = str((answer.get("evidence_summary") or {}).get("status") or "")
    if ans_status == "not_supported" and ev_status == "direct":
        return "FAIL", "answer_status=not_supported contradicts evidence_status=direct"
    if ans_status == "supported" and ev_status == "missing":
        return "FAIL", "answer_status=supported contradicts evidence_status=missing"
    # Check key_points don't contradict simple_answer on Gold usage
    simple = str(answer.get("simple_answer") or "").lower()
    kps_text = " ".join(str(kp) for kp in (answer.get("key_points") or []))
    if "not available" in simple and "₹" in kps_text:
        return "FAIL", "simple_answer says not available but key_points contain financial data"
    return "PASS", "no obvious internal contradiction detected"


def _check_economically_relevant(answer: dict[str, Any]) -> tuple[str, str]:
    text = _text_of(answer)
    econ_signals = re.compile(
        r"₹|revenue|earnings|cash|fcf|capex|margin|eps|book value|working capital|"
        r"per share|owner earnings|returns|profitability|dividend",
        re.IGNORECASE,
    )
    if econ_signals.search(text):
        return "PASS", "answer contains economic/financial context"
    return "FAIL", "no financial or economic reference in answer text"


def _check_uncertainty_aware(answer: dict[str, Any]) -> tuple[str, str]:
    ans_status = str(answer.get("answer_status") or "")
    ev_status = str((answer.get("evidence_summary") or {}).get("status") or "")
    uncertainty = answer.get("uncertainty_note") or {}
    if ans_status in ("partially_supported", "not_supported") or ev_status in ("partial", "missing"):
        if uncertainty and str(uncertainty.get("message") or "").strip():
            return "PASS", "uncertainty_note is set when evidence is partial/missing"
        return "FAIL", "evidence is partial/missing but uncertainty_note is absent or empty"
    return "PASS", "full support — no uncertainty note required"


def _check_non_generic(answer: dict[str, Any]) -> tuple[str, str]:
    kps = [str(kp) for kp in (answer.get("key_points") or []) if str(kp).strip()]
    if not kps:
        return "FAIL", "no key_points present"
    generic_count = sum(1 for kp in kps if _GENERIC_PHARMA_RE.match(kp.strip()))
    if generic_count == len(kps):
        return "FAIL", f"all {len(kps)} key_points match generic pharmaceutical/business boilerplate"
    if generic_count > 0:
        return "FAIL", f"{generic_count}/{len(kps)} key_points are generic boilerplate"
    # Check for template leakage
    for kp in kps:
        if _TEMPLATE_PATTERNS.search(kp):
            return "FAIL", f"template artifact detected in key_point: {kp[:80]!r}"
    return "PASS", f"key_points appear company-specific ({len(kps)} points, 0 generic)"


def _check_decision_useful(answer: dict[str, Any]) -> tuple[str, str]:
    text = _text_of(answer)
    # Checks for watchpoints, action items, specific investor-relevant content
    actionable = re.compile(
        r"watchpoint|watch for|investor should|investors should|track|monitor|verify|"
        r"due diligence|investigate|confirms|flag|signal|red flag|caution|"
        r"₹[\d,]+|[\d]+\s*(?:crore|cr|%)|fy\d{2}",
        re.IGNORECASE,
    )
    if actionable.search(text):
        return "PASS", "answer contains actionable investor context"
    ans_status = str(answer.get("answer_status") or "")
    if ans_status == "not_supported":
        return "FAIL", "answer_status=not_supported gives investor no actionable information"
    return "FAIL", "no watchpoint, metric, or actionable investor context found"


def _extract_named_entities(answer: dict[str, Any]) -> list[str]:
    text = _text_of(answer)
    # Look for capitalized named entities and fiscal years
    caps = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
    years = re.findall(r"\bFY\d{2,4}\b", text)
    pharma_entities = {"Sun", "Pharma", "USFDA", "FDA", "Toansa", "Halol", "Mohali", "Alchemee", "Ranbaxy"}
    found = [e for e in (caps + years) if e in pharma_entities or re.match(r"FY\d+", e)]
    return list(dict.fromkeys(found))[:6]


# ─── Defect detection ─────────────────────────────────────────────────────────

def _detect_defects(
    question_id: str,
    answer: dict[str, Any],
    sources_accessed: list[str],
    source_bundle_meta: dict[str, Any],
    saved_card: dict[str, Any] | None,
    expected_owner: dict[str, Any] | None,
    source_context: dict[str, Any],
) -> list[str]:
    defects: list[str] = []

    # PATH_DIVERGENCE: Gold expected but not accessed
    if expected_owner and expected_owner.get("gold_expected"):
        gold_accessed = [s for s in sources_accessed if s in GOLD_SOURCE_KEYS]
        if not gold_accessed:
            defects.append("PATH_DIVERGENCE")

    # PATH_DIVERGENCE: forbidden source used as primary
    forbidden = (expected_owner or {}).get("forbidden_primary")
    if forbidden and sources_accessed and sources_accessed[0] == forbidden:
        if "PATH_DIVERGENCE" not in defects:
            defects.append("PATH_DIVERGENCE")

    # STALE_ARTIFACT: saved card older than its registered dependencies
    if saved_card:
        saved_ts = str(saved_card.get("generated_at") or "")
        dep_provenance = saved_card.get("dependency_provenance") or []
        if dep_provenance and saved_ts:
            # Provenance-based freshness (canonical P0+ check)
            for dep in dep_provenance:
                dep_ts = str(dep.get("artifact_timestamp") or "")
                if dep_ts and dep_ts > saved_ts:
                    defects.append("STALE_ARTIFACT")
                    break
        elif saved_ts:
            # Legacy fallback: compare against gold_credibility mtime (pre-provenance cards)
            gold_ts = source_bundle_meta.get("gold_credibility_mtime", "")
            if gold_ts and saved_ts < gold_ts:
                defects.append("STALE_ARTIFACT")

    # BAD_UPSTREAM_INTELLIGENCE: zero evidence in answer
    ev_status = str((answer.get("evidence_summary") or {}).get("status") or "")
    if ev_status == "missing":
        defects.append("BAD_UPSTREAM_INTELLIGENCE")

    # BAD_SYNTHESIS: multi-year series present but answer claims snapshot
    series_len = source_context.get("per_share_series_length", 0)
    if series_len >= 5 and expected_owner and expected_owner.get("longitudinal_synthesis_expected"):
        text = _text_of(answer)
        if re.search(r"snapshot|does not.*multi.year|current.year only|limited.*compar", text, re.IGNORECASE):
            defects.append("BAD_SYNTHESIS")

    # BAD_UPSTREAM_INTELLIGENCE: project data is historically outdated (not a card freshness issue)
    # The 2014 Toansa event is outdated data IN the projects_registry, not a stale saved card.
    # This is a P2 concern (project temporal filtering). Do not classify as STALE_ARTIFACT.
    if question_id == "what-projects-are-underway":
        kps = [str(kp) for kp in (answer.get("key_points") or [])]
        for kp in kps:
            if "2014" in kp or "toansa" in kp.lower():
                if "BAD_UPSTREAM_INTELLIGENCE" not in defects:
                    defects.append("BAD_UPSTREAM_INTELLIGENCE")
                break

    # BAD_RENDERING: template language in key_points
    kps_text = " ".join(str(kp) for kp in (answer.get("key_points") or []))
    if _TEMPLATE_PATTERNS.search(kps_text):
        defects.append("BAD_RENDERING")

    # BAD_RENDERING: truncation artifacts
    if kps_text.endswith("..") or " m.." in kps_text or " r.." in kps_text:
        if "BAD_RENDERING" not in defects:
            defects.append("BAD_RENDERING")

    # BAD_EVIDENCE_LINK: not_supported when Gold data exists (live vs saved divergence)
    if saved_card:
        saved_status = str(saved_card.get("answer_status") or "")
        live_status = str(answer.get("answer_status") or "")
        if saved_status == "not_supported" and live_status in ("supported", "partially_supported"):
            if "STALE_ARTIFACT" not in defects:
                defects.append("STALE_ARTIFACT")

    return defects


# ─── Evidence link integrity ───────────────────────────────────────────────────

def _classify_evidence_links(
    question_id: str,
    answer: dict[str, Any],
    sources_accessed: list[str],
    source_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Classify each key_point's evidence relationship.
    Returns list of {claim, classification, reason}.
    """
    results = []
    kps = [str(kp) for kp in (answer.get("key_points") or []) if str(kp).strip()]

    for kp in kps:
        # Temporal mismatch check
        if re.search(r"\b201[0-9]\b", kp) and question_id == "what-projects-are-underway":
            results.append({
                "claim": kp[:120],
                "classification": "UNRELATED",
                "reason": "event year is pre-2020; serving as active project in FY26 context is a temporal mismatch",
            })
            continue

        # Template artifact — not investor content
        if _TEMPLATE_PATTERNS.search(kp):
            results.append({
                "claim": kp[:120],
                "classification": "UNRELATED",
                "reason": "builder template language — not investor-facing evidence",
            })
            continue

        # Generic boilerplate — evidence relationship cannot be assessed
        if _GENERIC_PHARMA_RE.match(kp.strip()):
            results.append({
                "claim": kp[:120],
                "classification": "WEAK",
                "reason": "generic pharmaceutical language; cannot verify company-specific evidence link",
            })
            continue

        # Numeric claim with financial source accessed — supported
        if _NUMERIC_RE.search(kp):
            financial_sources = [s for s in sources_accessed if "financial" in s or "per_share" in s]
            if financial_sources:
                results.append({
                    "claim": kp[:120],
                    "classification": "SUPPORTED",
                    "reason": f"numeric claim with financial source accessed: {financial_sources[0]}",
                })
            else:
                results.append({
                    "claim": kp[:120],
                    "classification": "WEAK",
                    "reason": "numeric claim but no financial source accessed during build",
                })
            continue

        # Gold-derived claim
        gold_accessed = [s for s in sources_accessed if s in GOLD_SOURCE_KEYS]
        if gold_accessed and any(w in kp.lower() for w in ["tracked", "verified", "credibility", "commitment", "promise"]):
            results.append({
                "claim": kp[:120],
                "classification": "SUPPORTED",
                "reason": f"Gold-derived claim with Gold source: {gold_accessed[0]}",
            })
            continue

        results.append({
            "claim": kp[:120],
            "classification": "UNKNOWN",
            "reason": "cannot determine evidence link from runtime trace alone",
        })

    return results


# ─── Artifact metadata helpers ────────────────────────────────────────────────

def _source_meta(source_bundle: dict[str, Any], key: str) -> dict[str, str]:
    s = (source_bundle.get("sources") or {}).get(key) or {}
    payload = s.get("payload") or {}
    return {
        "path": str(s.get("path") or ""),
        "status": str(s.get("status") or "missing"),
        "file_mtime": str(s.get("file_mtime") or ""),
        "generated_at": str(payload.get("generated_at") or s.get("generated_at") or ""),
    }


def _answer_card_meta(company_root: Path) -> dict[str, Any]:
    card_path = company_root / "company_memory/ask_intrinsiciq/answer_cards.json"
    if not card_path.exists():
        return {"path": str(card_path), "exists": False}
    try:
        data = json.loads(card_path.read_text(encoding="utf-8"))
        stat = card_path.stat()
        return {
            "path": str(card_path),
            "exists": True,
            "generated_at": str(data.get("generated_at") or ""),
            "file_mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "answer_count": len(data.get("answers", [])),
        }
    except Exception as exc:
        return {"path": str(card_path), "exists": True, "error": str(exc)}


def _saved_answer_for(company_root: Path, question_id: str) -> dict[str, Any] | None:
    card_path = company_root / "company_memory/ask_intrinsiciq/answer_cards.json"
    if not card_path.exists():
        return None
    try:
        data = json.loads(card_path.read_text(encoding="utf-8"))
        for ans in data.get("answers") or []:
            if ans.get("question_id") == question_id:
                return ans
    except Exception:
        pass
    return None


# ─── Per-question trace ────────────────────────────────────────────────────────

def trace_question(
    question_id: str,
    company_internal_key: str,
    company_public_slug: str,
    source_bundle: dict[str, Any],
    company_root: Path,
    run_timestamp: str,
) -> dict[str, Any]:
    """
    Run the live builder for question_id, collect traces, run semantic checks,
    and return a complete trace record.
    """
    # ── Load side-channel payloads (not tracked as sources) ──────────────────
    bj_path = company_root / "company_memory/ask_intrinsiciq/business_journey.json"
    ps_path = company_root / "company_memory/ask_intrinsiciq/products_services.json"
    bj = json.loads(bj_path.read_text(encoding="utf-8")) if bj_path.exists() else {}
    ps = json.loads(ps_path.read_text(encoding="utf-8")) if ps_path.exists() else {}

    # ── Collect per-share series metadata for synthesis check ────────────────
    psa_payload = ((source_bundle.get("sources") or {}).get("per_share_compounding_analysis") or {}).get("payload") or {}
    series_len = len(psa_payload.get("analysis") or [])

    # ── Collect project year metadata ─────────────────────────────────────────
    proj_payload = ((source_bundle.get("sources") or {}).get("projects_registry") or {}).get("payload") or {}
    projects = proj_payload.get("projects") or []
    projects_without_year = sum(
        1 for p in projects
        if not str(p.get("years") or "").strip() and not str(p.get("event_year") or "").strip()
    )

    source_context = {
        "per_share_series_length": series_len,
        "projects_total": len(projects),
        "projects_without_year": projects_without_year,
    }

    # ── Wrap bundle to track source access ───────────────────────────────────
    tracked = TrackedBundle(source_bundle)
    tracked["company_slug"] = company_internal_key  # required by some builders

    # ── Run live builder ──────────────────────────────────────────────────────
    answer = build_answer_for_question(
        question_id,
        tracked,
        business_journey_payload=bj,
        products_services_payload=ps,
        generated_at=run_timestamp,
    )
    sources_accessed: list[str] = list(tracked.access_log)

    # ── Identify which builder function was dispatched ────────────────────────
    builder_fn = ANSWER_BUILDERS.get(question_id, None)
    builder_name = builder_fn.__name__ if builder_fn else "_build_generic_not_supported_answer"

    # ── Expected owner map ────────────────────────────────────────────────────
    expected_owner = EXPECTED_OWNER_MAP.get(question_id)

    # ── Gold source resolution ────────────────────────────────────────────────
    gold_sources_accessed = [s for s in sources_accessed if s in GOLD_SOURCE_KEYS]
    gold_expected = (expected_owner or {}).get("gold_expected", False)
    gold_used = len(gold_sources_accessed) > 0

    # ── Determine primary source actually used ────────────────────────────────
    # First non-metadata source accessed is the primary
    metadata_sources = {"company_memory_index", "multi_year_company_year_index"}
    substantive_accessed = [s for s in sources_accessed if s not in metadata_sources]
    actual_primary = substantive_accessed[0] if substantive_accessed else None

    # ── Artifact metadata ─────────────────────────────────────────────────────
    key_sources = [
        "gold_promise_tracker", "gold_credibility", "gold_capital_allocation",
        "per_share_compounding_analysis", "projects_registry",
        "management_commitments", "management_progression", "buffett_analysis",
        "committee_synthesis",
    ]
    artifact_trace: dict[str, Any] = {}
    for src in key_sources:
        artifact_trace[src] = _source_meta(source_bundle, src)

    card_meta = _answer_card_meta(company_root)
    saved_card = _saved_answer_for(company_root, question_id)
    gold_credibility_mtime = artifact_trace.get("gold_credibility", {}).get("file_mtime", "")

    # ── Stale-card detection ──────────────────────────────────────────────────
    saved_status = str((saved_card or {}).get("answer_status") or "")
    live_status = str(answer.get("answer_status") or "")
    saved_vs_live_diverges = (saved_status != live_status)
    card_generated_at = card_meta.get("generated_at", "")
    # Prefer provenance-based freshness if the saved card carries it; fall back to gold_credibility comparison
    saved_provenance = (saved_card or {}).get("dependency_provenance") or []
    if saved_provenance and card_generated_at:
        card_stale_vs_gold = any(
            str(dep.get("artifact_timestamp") or "") > card_generated_at
            for dep in saved_provenance
            if str(dep.get("artifact_timestamp") or "")
        )
    else:
        card_stale_vs_gold = bool(
            card_generated_at and gold_credibility_mtime and card_generated_at < gold_credibility_mtime
        )

    # ── Source bundle metadata for defect detection ───────────────────────────
    sbm = {"gold_credibility_mtime": gold_credibility_mtime}

    # ── Defect detection ──────────────────────────────────────────────────────
    defects = _detect_defects(
        question_id, answer, sources_accessed,
        sbm, saved_card, expected_owner, source_context,
    )

    # ── Evidence link classification ──────────────────────────────────────────
    evidence_links = _classify_evidence_links(question_id, answer, sources_accessed, source_context)

    # ── Semantic checks ────────────────────────────────────────────────────────
    s_specific = _check_specific(answer)
    s_longitudinal = _check_longitudinal(answer, source_context)
    s_evidence = _check_evidence_backed(answer, sources_accessed)
    s_consistent = _check_internally_consistent(answer)
    s_economic = _check_economically_relevant(answer)
    s_uncertainty = _check_uncertainty_aware(answer)
    s_non_generic = _check_non_generic(answer)
    s_decision = _check_decision_useful(answer)

    semantic_checks = {
        "specific":             {"result": s_specific[0],    "detail": s_specific[1]},
        "longitudinal":         {"result": s_longitudinal[0], "detail": s_longitudinal[1]},
        "evidence_backed":      {"result": s_evidence[0],    "detail": s_evidence[1]},
        "internally_consistent":{"result": s_consistent[0],  "detail": s_consistent[1]},
        "economically_relevant":{"result": s_economic[0],    "detail": s_economic[1]},
        "uncertainty_aware":    {"result": s_uncertainty[0], "detail": s_uncertainty[1]},
        "non_generic":          {"result": s_non_generic[0], "detail": s_non_generic[1]},
        "decision_useful":      {"result": s_decision[0],    "detail": s_decision[1]},
    }

    # V2 three-tier verdict: ACCEPTED / PARTIAL / REJECTED
    critical_failures = _detect_critical_failures_v2(question_id, answer, defects, semantic_checks)
    verdict, verdict_rationale = _determine_verdict_v2(semantic_checks, critical_failures)

    # ── Explanation of why this answer exists ─────────────────────────────────
    explanation_parts: list[str] = [
        f"Builder dispatched: {builder_name}.",
        f"Sources accessed during build ({len(sources_accessed)}): {sources_accessed[:8]}.",
    ]
    if gold_used:
        explanation_parts.append(f"Gold sources used: {gold_sources_accessed}.")
    else:
        if gold_expected:
            explanation_parts.append(
                f"Gold was expected but NOT accessed. "
                f"Expected primary: {expected_owner.get('expected_primary')!r}. "
                f"Actual primary: {actual_primary!r}."
            )
    if defects:
        explanation_parts.append(f"Defects detected: {defects}.")
    if saved_vs_live_diverges:
        explanation_parts.append(
            f"Saved card says {saved_status!r}; live builder now produces {live_status!r}. "
            f"The saved answer card is out of date."
        )
    if card_stale_vs_gold:
        explanation_parts.append(
            f"Answer card generated_at ({card_generated_at[:16]}) predates Gold credibility "
            f"mtime ({gold_credibility_mtime[:16]}). Pipeline re-run required."
        )

    return {
        "question_id": question_id,
        "company_internal_key": company_internal_key,
        "company_public_slug": company_public_slug,
        "run_timestamp": run_timestamp,

        "routing_trace": {
            "builder_function": builder_name,
            "expected_primary_source": (expected_owner or {}).get("expected_primary"),
            "actual_primary_source_used": actual_primary,
            "all_sources_accessed": sources_accessed,
            "secondary_source": (expected_owner or {}).get("expected_secondary"),
            "forbidden_primary": (expected_owner or {}).get("forbidden_primary"),
            "forbidden_primary_used": bool(
                (expected_owner or {}).get("forbidden_primary") and
                actual_primary == (expected_owner or {}).get("forbidden_primary")
            ),
            "gold_expected": gold_expected,
            "gold_used": gold_used,
            "gold_sources_accessed": gold_sources_accessed,
            "source_selection_reason": (
                "Gold accessed as expected" if gold_used and gold_expected else
                "Gold bypassed — PATH_DIVERGENCE" if gold_expected and not gold_used else
                "Gold not expected for this question" if not gold_expected else
                "Unknown"
            ),
        },

        "artifact_trace": {
            **artifact_trace,
            "answer_card_file": card_meta,
            "saved_answer_status": saved_status or None,
            "live_builder_status": live_status,
            "saved_vs_live_diverges": saved_vs_live_diverges,
            "card_stale_vs_gold": card_stale_vs_gold,
        },

        "evidence_trace": {
            "sources_accessed_count": len(sources_accessed),
            "gold_sources_accessed": gold_sources_accessed,
            "per_share_series_length": series_len,
            "projects_total": len(projects),
            "projects_without_year": projects_without_year,
            "evidence_link_classifications": evidence_links,
            "evidence_link_integrity_summary": _summarize_link_integrity(evidence_links),
        },

        "answer_trace": {
            "answer_status": live_status,
            "key_points": list(answer.get("key_points") or []),
            "simple_answer": str(answer.get("simple_answer") or "")[:300],
            "evidence_status": str((answer.get("evidence_summary") or {}).get("status") or ""),
            "fiscal_years_referenced": sorted(set(_FISCAL_YEAR_RE.findall(_text_of(answer).lower()))),
            "named_entities": _extract_named_entities(answer),
            "named_metrics": _NUMERIC_RE.findall(_text_of(answer))[:6],
            "longitudinal": len(set(_FISCAL_YEAR_RE.findall(_text_of(answer).lower()))) >= 2,
            "template_leakage_detected": bool(_TEMPLATE_PATTERNS.search(
                " ".join(str(kp) for kp in (answer.get("key_points") or []))
            )),
        },

        "ui_trace": {
            "public_route": f"/company/{company_public_slug}/question/{question_id}",
            "loader_function": "getResearchAnswerCard (apps/ask-intrinsiciq/src/lib/ask-intrinsiciq/load-answer-card.ts)",
            "rendered_answer_source": (
                "Gold artifact" if gold_used else
                f"Progression/commitment data via {actual_primary or 'unknown'}"
            ),
            "stale_artifact_detected": card_stale_vs_gold or ("STALE_ARTIFACT" in defects),
            "raw_backend_language_detected": bool(_TEMPLATE_PATTERNS.search(
                " ".join(str(kp) for kp in (answer.get("key_points") or []))
            )),
            "browser_spot_check_required": True,
            "browser_spot_check_note": (
                "Automated browser access not available in harness. "
                "Verify rendered output at /company/sun-pharma/question/" + question_id
            ),
        },

        "semantic_checks": semantic_checks,

        "verdict": verdict,
        "verdict_rationale": verdict_rationale,
        "critical_failures_detected": critical_failures,
        "certification_contract_version": CERTIFICATION_CONTRACT_VERSION,

        "defect_classes": defects,

        "explanation": " ".join(explanation_parts),
    }


def _summarize_link_integrity(links: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for link in links:
        c = str(link.get("classification") or "UNKNOWN")
        counts[c] = counts.get(c, 0) + 1
    parts = [f"{v} {k}" for k, v in counts.items()]
    return ", ".join(parts) if parts else "no key_points to classify"


# ─── Main runner ───────────────────────────────────────────────────────────────

def run_acceptance(
    company: str,
    questions: list[str],
    out_dir: Path,
) -> dict[str, Any]:
    company_internal_key = company.replace("-", "_").lower()
    company_public_slug = company.replace("_", "-").lower()
    run_timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    company_root = ROOT / "companies" / company_internal_key

    if not company_root.exists():
        print(f"ERROR: company directory not found: {company_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading source bundle for {company_internal_key}...")
    source_bundle = load_company_memory_sources(company_internal_key)
    found = len(source_bundle.get("source_files_found") or [])
    missing = len(source_bundle.get("source_files_missing") or [])
    print(f"  {found} sources loaded, {missing} missing")

    traces_dir = out_dir / "question_traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    traces: list[dict[str, Any]] = []
    accepted = 0
    partial = 0
    rejected = 0

    for qid in questions:
        print(f"  Tracing: {qid}...")
        trace = trace_question(
            qid,
            company_internal_key=company_internal_key,
            company_public_slug=company_public_slug,
            source_bundle=source_bundle,
            company_root=company_root,
            run_timestamp=run_timestamp,
        )
        traces.append(trace)
        verdict = trace["verdict"]
        if verdict == "ACCEPTED":
            accepted += 1
        elif verdict == "PARTIAL":
            partial += 1
        else:
            rejected += 1
        cfs = trace.get("critical_failures_detected") or []
        cf_note = f" CF:{cfs}" if cfs else ""
        print(f"    → {verdict}{cf_note} | defects: {trace['defect_classes'] or 'none'}")

        trace_path = traces_dir / f"{qid}.json"
        trace_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")

    # Determine highest-severity systemic defect
    all_defects: list[str] = []
    for t in traces:
        all_defects.extend(t["defect_classes"])
    defect_severity = [
        "PATH_DIVERGENCE", "BAD_UPSTREAM_INTELLIGENCE", "STALE_ARTIFACT",
        "BAD_SYNTHESIS", "BAD_EVIDENCE_LINK", "BAD_RENDERING", "WRONG_LOADER_PATH",
    ]
    highest_defect = next((d for d in defect_severity if d in all_defects), "none")

    # P0 recommendation
    path_divergence_count = sum(1 for t in traces if "PATH_DIVERGENCE" in t["defect_classes"])
    stale_count = sum(1 for t in traces if "STALE_ARTIFACT" in t["defect_classes"])
    harness_status = "HARNESS_READY"

    p0_should_proceed = rejected > 0  # There are questions to fix

    # V2: domain-level acceptance counts
    domain_accepted: dict[str, int] = {d: 0 for d in DOMAIN_MAP}
    domain_partial: dict[str, int] = {d: 0 for d in DOMAIN_MAP}
    domain_rejected: dict[str, int] = {d: 0 for d in DOMAIN_MAP}
    domain_tested: dict[str, int] = {d: 0 for d in DOMAIN_MAP}
    question_domain_map = {q: d for d, qs in DOMAIN_MAP.items() for q in qs}
    for t in traces:
        qid = t["question_id"]
        dom = question_domain_map.get(qid)
        if dom:
            domain_tested[dom] = domain_tested.get(dom, 0) + 1
            v = t["verdict"]
            if v == "ACCEPTED":
                domain_accepted[dom] = domain_accepted.get(dom, 0) + 1
            elif v == "PARTIAL":
                domain_partial[dom] = domain_partial.get(dom, 0) + 1
            else:
                domain_rejected[dom] = domain_rejected.get(dom, 0) + 1

    # V2: critical failures across all questions
    all_critical_failures: list[str] = []
    for t in traces:
        all_critical_failures.extend(t.get("critical_failures_detected") or [])
    critical_failures_count = len(all_critical_failures)
    unique_critical_failures = list(dict.fromkeys(all_critical_failures))

    # V2: grade computation
    grade_result = _compute_grade_v2(
        accepted, rejected, partial, len(questions),
        critical_failures_count, domain_accepted,
    )

    per_domain_summary = {
        dom: {
            "tested": domain_tested[dom],
            "accepted": domain_accepted[dom],
            "partial": domain_partial[dom],
            "rejected": domain_rejected[dom],
        }
        for dom in DOMAIN_MAP
    }

    summary = {
        "certification_contract_version": CERTIFICATION_CONTRACT_VERSION,
        "run_timestamp": run_timestamp,
        "company_internal_key": company_internal_key,
        "company_public_slug": company_public_slug,
        "questions_tested": len(questions),
        "accepted": accepted,
        "partial": partial,
        "rejected": rejected,
        "acceptance_rate": f"{accepted}/{len(questions)}",
        "grade": grade_result["grade"],
        "investor_grade_pass": grade_result["investor_grade_pass"],
        "grade_reason": grade_result["reason"],
        "critical_failures_count": critical_failures_count,
        "critical_failures_detected": unique_critical_failures,

        "per_question": [
            {
                "question_id": t["question_id"],
                "domain": question_domain_map.get(t["question_id"], "unknown"),
                "verdict": t["verdict"],
                "verdict_rationale": t.get("verdict_rationale", ""),
                "critical_failures": t.get("critical_failures_detected") or [],
                "answer_status_live": t["answer_trace"]["answer_status"],
                "answer_status_saved": t["artifact_trace"].get("saved_answer_status"),
                "gold_expected": t["routing_trace"]["gold_expected"],
                "gold_used": t["routing_trace"]["gold_used"],
                "actual_primary_source": t["routing_trace"]["actual_primary_source_used"],
                "expected_primary_source": t["routing_trace"]["expected_primary_source"],
                "stale_artifact": t["ui_trace"]["stale_artifact_detected"],
                "template_leakage": t["answer_trace"]["template_leakage_detected"],
                "defect_classes": t["defect_classes"],
                "semantic_fails": [
                    k for k, v in t["semantic_checks"].items()
                    if v["result"] == "FAIL"
                ],
            }
            for t in traces
        ],

        "per_domain": per_domain_summary,

        "investor_grade_gate": {
            "gate_passed": grade_result["investor_grade_pass"],
            "gate_detail": grade_result.get("gate_detail", {}),
            "grade": grade_result["grade"],
        },

        "systemic_findings": {
            "path_divergence_count": path_divergence_count,
            "stale_artifact_count": stale_count,
            "highest_severity_defect": highest_defect,
            "all_defect_classes": sorted(set(all_defects)),
            "critical_failure_count": critical_failures_count,
        },

        "p0_recommendation": {
            "should_proceed": p0_should_proceed,
            "reason": (
                f"{rejected} REJECTED, {partial} PARTIAL of {len(questions)} questions. "
                f"Highest severity defect: {highest_defect}. "
                f"PATH_DIVERGENCE in {path_divergence_count} question(s). "
                "Fix routing first (P0), then evidence repair (P1), then synthesis (P2)."
                if p0_should_proceed else
                f"All questions ACCEPTED. Grade: {grade_result['grade']}. No P0 action required."
            ),
        },

        "harness_status": harness_status,
        "trace_files": [str(traces_dir / f"{qid}.json") for qid in questions],
    }

    summary_path = out_dir / "acceptance_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("━" * 60)
    print(f"ACCEPTED: {accepted}/{len(questions)}")
    print(f"PARTIAL:  {partial}/{len(questions)}")
    print(f"REJECTED: {rejected}/{len(questions)}")
    print(f"Grade: {grade_result['grade']} | Investor grade: {grade_result['investor_grade_pass']}")
    print(f"Critical failures: {critical_failures_count}")
    print(f"Highest defect: {highest_defect}")
    print(f"Summary: {summary_path}")
    print(f"Harness status: {harness_status}")
    print("━" * 60)

    return summary


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Prometheus Investor Acceptance Harness")
    parser.add_argument("company", help="Company internal key or public slug (e.g. sun_pharma or sun-pharma)")
    parser.add_argument(
        "--questions",
        default="recovery_baseline",
        choices=list(QUESTION_SETS.keys()),
        help="Question set to run (default: recovery_baseline)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (default: acceptance_reports/<company>/)",
    )
    args = parser.parse_args()

    company = args.company.replace("-", "_").lower()
    questions = QUESTION_SETS[args.questions]
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "acceptance_reports" / company

    run_acceptance(company, questions, out_dir)


if __name__ == "__main__":
    main()
