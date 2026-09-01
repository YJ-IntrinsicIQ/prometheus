from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .classifier import classify_promise_type, is_material_promise
from .resolver import (
    build_investor_interpretation,
    extract_evidence_ids,
    extract_later_evidence,
    materiality_rank,
    resolve_current_status,
    resolve_execution_status,
    resolve_financial_link_status,
    resolve_outcome_status,
)

SCHEMA_VERSION = "promise_tracker_gold.v1"

_GOLD_DIR = "gold"
_ARTIFACT_NAME = "management_promise_tracker.json"


# ── I/O helpers ────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _gold_output_path(company_slug: str, companies_root: Path) -> Path:
    return companies_root / company_slug / "company_memory" / _GOLD_DIR / _ARTIFACT_NAME


# ── Original statement extraction ──────────────────────────────────────────────

def _original_statement(item: Dict[str, Any]) -> str:
    events = item.get("events") or []
    for event in events:
        if event.get("role") == "commitment":
            stmt = (event.get("statement_text") or "").strip()
            if stmt:
                return stmt
    # Fall back to theme
    theme = (item.get("theme") or "").strip()
    if len(theme) > 120:
        theme = theme[:120].rsplit(" ", 1)[0] + "…"
    return theme


def _source_period(item: Dict[str, Any]) -> str:
    events = item.get("events") or []
    commitment_periods = sorted(e.get("source_period") or "" for e in events if e.get("role") == "commitment")
    if commitment_periods:
        return commitment_periods[0]
    periods = sorted(e.get("source_period") or "" for e in events if e.get("source_period"))
    return periods[0] if periods else ""


def _target_period(item: Dict[str, Any]) -> Optional[str]:
    events = item.get("events") or []
    for event in events:
        tp = (event.get("target_period") or "").strip()
        if tp:
            return tp
    return None


def _measurable_target(item: Dict[str, Any], measurable_commitments: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    item_id = item.get("item_id") or ""
    for mc in measurable_commitments:
        if mc.get("source_item_id") == item_id or mc.get("commitment_id", "").startswith("MC-LINK"):
            # Check for overlap in statement text
            mc_stmt = (mc.get("original_statement") or "").lower()
            theme = (item.get("theme") or "").lower()[:60]
            if theme and any(word in mc_stmt for word in theme.split()[:5] if len(word) > 4):
                target = mc.get("extracted_target") or ""
                return {
                    "target_description": target,
                    "target_period": mc.get("target_period"),
                    "later_actual": None,
                    "delivery_status": mc.get("delivery_status") or "UNVERIFIED",
                } if target else None
    return None


# ── Core promise builder ────────────────────────────────────────────────────────

def _build_promise_record(
    item: Dict[str, Any],
    measurable_commitments: List[Dict[str, Any]],
    promise_index: int,
) -> Dict[str, Any]:
    promise_id = f"PT-{promise_index:04d}-{item['item_id'].split('-', 2)[-1][:40]}"
    promise_type = classify_promise_type(item)
    execution_status = resolve_execution_status(item)
    financial_link_status = resolve_financial_link_status(item)
    outcome_status = resolve_outcome_status(
        item,
        execution_status=execution_status,
        financial_link_status=financial_link_status,
    )
    current_status = resolve_current_status(item, outcome_status, execution_status)
    later_evidence = extract_later_evidence(item)
    evidence_ids = extract_evidence_ids(item)
    investor_interpretation = build_investor_interpretation(item, execution_status, outcome_status)
    measurable = _measurable_target(item, measurable_commitments)

    record: Dict[str, Any] = {
        "promise_id": promise_id,
        "source_item_id": item.get("item_id"),
        "theme": (item.get("theme") or "").strip()[:200],
        "original_statement": _original_statement(item),
        "source_period": _source_period(item),
        "target_period": _target_period(item),
        "promise_type": promise_type,
        "execution_status": execution_status,
        "outcome_status": outcome_status,
        "financial_link_status": financial_link_status,
        "current_status": current_status,
        "later_evidence": later_evidence,
        "evidence_ids": evidence_ids,
        "linked_company_model_ids": item.get("linked_company_model_ids") or [],
        "investor_interpretation": investor_interpretation,
    }
    if measurable:
        record["measurable_commitment"] = measurable

    return record


# ── Credibility patterns ────────────────────────────────────────────────────────

def _build_credibility_patterns(promises: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(promises) < 2:
        return []

    status_counts = Counter(p["current_status"] for p in promises)
    exec_counts = Counter(p["execution_status"] for p in promises)
    total = len(promises)
    patterns = []

    action_completed = exec_counts.get("ACTION_COMPLETED", 0) + exec_counts.get("EARLY_OPERATING_SIGNAL", 0)
    financial_unproven = sum(
        1 for p in promises
        if p["execution_status"] in ("ACTION_COMPLETED", "EARLY_OPERATING_SIGNAL")
        and p["financial_link_status"] == "INSUFFICIENT_EVIDENCE"
    )
    if action_completed >= 2 and financial_unproven >= 2:
        patterns.append({
            "pattern_id": "execution_without_economic_proof",
            "description": (
                f"Management completed operational steps in {action_completed} tracked commitments, "
                f"but {financial_unproven} of these show no established financial consequence. "
                "Execution follow-through is visible; economic proof is not."
            ),
            "evidence_count": action_completed,
            "investor_relevance": "Completion of a project does not automatically mean the economic premise is proven.",
        })

    unverified_count = status_counts.get("UNVERIFIED", 0)
    if unverified_count >= 3:
        patterns.append({
            "pattern_id": "frequent_unverified_commitments",
            "description": (
                f"{unverified_count} of {total} tracked commitments remain unverified — "
                "either no later evidence exists or follow-through has not been confirmed."
            ),
            "evidence_count": unverified_count,
            "investor_relevance": "High unverified count reflects evidence gaps, not necessarily management failure.",
        })

    achieved = status_counts.get("ACHIEVED", 0) + status_counts.get("PARTIALLY_ACHIEVED", 0)
    if achieved >= 3:
        patterns.append({
            "pattern_id": "demonstrated_follow_through",
            "description": (
                f"{achieved} of {total} tracked commitments show evidence of delivery or partial delivery. "
                "Management follow-through on execution appears present."
            ),
            "evidence_count": achieved,
            "investor_relevance": "Execution credibility is constructive but must be weighed against economic outcome proof.",
        })

    missed_count = status_counts.get("MISSED", 0)
    if missed_count >= 2:
        patterns.append({
            "pattern_id": "repeated_missed_commitments",
            "description": (
                f"{missed_count} commitments show evidence of being missed or contradicted. "
                "This is a red flag that warrants further scrutiny."
            ),
            "evidence_count": missed_count,
            "investor_relevance": "Repeated misses or contradictions erode management credibility.",
        })

    delayed = status_counts.get("DELAYED", 0)
    if delayed >= 2:
        patterns.append({
            "pattern_id": "repeated_timeline_slippage",
            "description": (
                f"{delayed} commitments had target periods that were not met. "
                "Timeline discipline appears weak."
            ),
            "evidence_count": delayed,
            "investor_relevance": "Repeated delays matter most for capital-intensive or time-bound strategic commitments.",
        })

    return patterns


# ── Summary ────────────────────────────────────────────────────────────────────

def _build_summary(
    promises: List[Dict[str, Any]],
    company_slug: str,
    credibility_patterns: List[Dict[str, Any]],
    trivial_excluded: int,
) -> Dict[str, Any]:
    status_counts = Counter(p["current_status"] for p in promises)
    type_counts = Counter(p["promise_type"] for p in promises)
    return {
        "company_slug": company_slug,
        "tracked_promises": len(promises),
        "trivial_excluded": trivial_excluded,
        "status_breakdown": {
            "achieved": status_counts.get("ACHIEVED", 0),
            "partially_achieved": status_counts.get("PARTIALLY_ACHIEVED", 0),
            "delayed": status_counts.get("DELAYED", 0),
            "missed": status_counts.get("MISSED", 0),
            "abandoned": status_counts.get("ABANDONED", 0),
            "unverified": status_counts.get("UNVERIFIED", 0),
        },
        "promise_type_breakdown": dict(type_counts),
        "credibility_patterns_count": len(credibility_patterns),
        "silence_is_not_failure_note": (
            "UNVERIFIED status means no later evidence is available — it does not imply the promise was missed."
        ),
    }


# ── Critical follow-up ─────────────────────────────────────────────────────────

def _build_critical_followup(promises: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    followup = []
    for p in promises:
        if p["current_status"] == "DELAYED":
            followup.append({
                "promise_id": p["promise_id"],
                "question": f"Has this commitment been delivered or formally revised since {p['source_period']}?",
                "type": "timeline_verification",
                "promise_theme": p["theme"][:100],
            })
        elif p["financial_link_status"] == "INSUFFICIENT_EVIDENCE" and p["execution_status"] in ("ACTION_COMPLETED", "EARLY_OPERATING_SIGNAL"):
            followup.append({
                "promise_id": p["promise_id"],
                "question": f"What is the measurable financial or business consequence of the completed action?",
                "type": "economic_outcome_needed",
                "promise_theme": p["theme"][:100],
            })
        elif p["current_status"] == "MISSED":
            followup.append({
                "promise_id": p["promise_id"],
                "question": f"What explains the gap between this commitment and the later evidence?",
                "type": "miss_explanation",
                "promise_theme": p["theme"][:100],
            })
    return followup[:10]


# ── Main builder ───────────────────────────────────────────────────────────────

def build_management_promise_tracker(
    company_slug: str,
    *,
    companies_root: Path | str = Path("companies"),
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    companies_root = Path(companies_root)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    # Load sources
    memory_root = companies_root / company_slug / "company_memory"
    progression = _load_json(memory_root / "management_progression" / "management_progression.json")
    measurable_commitments = progression.get("measurable_commitments") or []

    # All progression items
    all_items = progression.get("progression_items") or []
    trivial_count = 0
    material_items = []
    for item in all_items:
        if is_material_promise(item):
            material_items.append(item)
        else:
            trivial_count += 1

    # Build promise records
    promises: List[Dict[str, Any]] = []
    for idx, item in enumerate(material_items, start=1):
        record = _build_promise_record(item, measurable_commitments, idx)
        promises.append(record)

    # Sort by materiality rank descending
    promises.sort(key=materiality_rank, reverse=True)

    # Partition into resolved / unresolved
    resolved = [p for p in promises if p["current_status"] in ("ACHIEVED", "PARTIALLY_ACHIEVED", "MISSED", "ABANDONED")]
    unresolved = [p for p in promises if p["current_status"] not in ("ACHIEVED", "PARTIALLY_ACHIEVED", "MISSED", "ABANDONED")]

    # Credibility patterns
    credibility_patterns = _build_credibility_patterns(promises)

    # Summary
    summary = _build_summary(promises, company_slug, credibility_patterns, trivial_count)

    # Critical follow-up
    critical_followup = _build_critical_followup(promises)

    return {
        "schema_version": SCHEMA_VERSION,
        "company_slug": company_slug,
        "generated_at": generated_at,
        "summary": summary,
        "material_promises": promises,
        "resolved_promises": resolved,
        "unresolved_promises": unresolved,
        "credibility_patterns": credibility_patterns,
        "critical_follow_up": critical_followup,
    }


def write_management_promise_tracker(
    company_slug: str,
    *,
    companies_root: Path | str = Path("companies"),
    generated_at: Optional[str] = None,
) -> Path:
    companies_root = Path(companies_root)
    payload = build_management_promise_tracker(
        company_slug, companies_root=companies_root, generated_at=generated_at
    )
    output_path = _gold_output_path(company_slug, companies_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path
