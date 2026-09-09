from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .classifier import classify_promise_type, is_material_commitment_promise
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


def _management_commitments_path(company_slug: str, companies_root: Path) -> Path:
    return companies_root / company_slug / "company_memory" / "management_commitments" / "management_commitments.json"


def _management_progression_path(company_slug: str, companies_root: Path) -> Path:
    return companies_root / company_slug / "company_memory" / "management_progression" / "management_progression.json"


def _commitment_fingerprint(commitment: Dict[str, Any]) -> str:
    return str(commitment.get("commitment_fingerprint") or "").strip()


def _commitment_id(commitment: Dict[str, Any]) -> str:
    return str(commitment.get("id") or commitment.get("commitment_id") or "").strip()


def _commitment_period(commitment: Dict[str, Any]) -> str:
    return str(
        commitment.get("announcement_period")
        or commitment.get("source_period")
        or commitment.get("period")
        or ""
    ).strip()


def _commitment_target_period(commitment: Dict[str, Any]) -> Optional[str]:
    value = str(commitment.get("target_period") or commitment.get("expected_timeframe") or "").strip()
    if not value or value.lower() in {"unspecified", "unknown", "not specified", "n/a", "na"}:
        return None
    return value


def _commitment_source_evidence_ids(commitment: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for ref in commitment.get("source_references") or []:
        if isinstance(ref, dict):
            eid = ref.get("evidence_id") or ref.get("source_item_id")
            if eid and eid not in ids:
                ids.append(str(eid))
    for ev in commitment.get("supporting_evidence") or []:
        if isinstance(ev, dict):
            ref = ev.get("source_reference") or {}
            eid = ref.get("evidence_id") or ref.get("source_item_id") if isinstance(ref, dict) else None
            if eid and eid not in ids:
                ids.append(str(eid))
    return ids


def _commitment_as_progression_seed(commitment: Dict[str, Any]) -> Dict[str, Any]:
    statement = str(commitment.get("original_statement") or commitment.get("normalized_commitment") or commitment.get("topic") or "").strip()
    fingerprint = _commitment_fingerprint(commitment)
    period = _commitment_period(commitment)
    evidence = []
    for ref in commitment.get("source_references") or []:
        if isinstance(ref, dict):
            evidence.append({
                "source_artifact": ref.get("source_artifact") or "management_commitments.json",
                "source_period": ref.get("period") or period,
                "evidence_id": ref.get("evidence_id") or ref.get("source_item_id"),
                "source_item_id": ref.get("source_item_id") or _commitment_id(commitment),
                "field_path": "commitments[]",
                "excerpt": statement[:300],
            })
    return {
        "item_id": f"MC-{fingerprint}" if fingerprint else _commitment_id(commitment) or "MC-UNKNOWN",
        "theme": commitment.get("topic") or statement[:120],
        "linked_company_model_ids": [],
        "stream_types": ["commitment"],
        "current_status": "announced",
        "management_credibility_signal": "UNABLE_TO_VERIFY",
        "events": [
            {
                "event_id": fingerprint,
                "role": "commitment",
                "event_type": commitment.get("category") or "management_commitment",
                "source_period": period,
                "event_period": period,
                "target_period": _commitment_target_period(commitment) or "",
                "statement_text": statement,
                "action_taken": "",
                "operational_outcome": "",
                "financial_or_business_outcome": "",
                "verification_status": "unresolved",
                "evidence": evidence,
            }
        ],
        "investor_implication": None,
    }


def _commitment_lifecycle_index(progression: Dict[str, Any], valid_fingerprints: Set[str]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for item in progression.get("progression_items") or []:
        if not isinstance(item, dict):
            continue
        matched: Set[str] = set()
        for event in item.get("events") or []:
            if not isinstance(event, dict):
                continue
            role = str(event.get("role") or event.get("event_role") or "").strip().lower()
            event_id = str(event.get("event_id") or event.get("source_item_id") or "").strip()
            # Primary join: commitment event whose event_id IS the fingerprint.
            if role == "commitment" and event_id in valid_fingerprints:
                matched.add(event_id)
            # Secondary join (future contract): execution event carrying canonical_commitment_reference
            # set by upstream LLM extraction. No-op today; activates without code change when field exists.
            fp_field = str(event.get("commitment_fingerprint") or "").strip()
            if fp_field and fp_field in valid_fingerprints:
                matched.add(fp_field)
        for fingerprint in matched:
            index[fingerprint] = item
    return index


def _merge_evidence_ids(commitment: Dict[str, Any], lifecycle_item: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for eid in _commitment_source_evidence_ids(commitment) + extract_evidence_ids(lifecycle_item):
        if eid and eid not in ids:
            ids.append(eid)
    return ids

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
    commitment: Dict[str, Any],
    lifecycle_item: Dict[str, Any],
    measurable_commitments: List[Dict[str, Any]],
    promise_index: int,
) -> Dict[str, Any]:
    fingerprint = _commitment_fingerprint(commitment)
    source_item_id = lifecycle_item.get("item_id") or _commitment_id(commitment)
    promise_id = f"PT-{promise_index:04d}-{fingerprint[:12] or str(source_item_id).split('-', 2)[-1][:40]}"
    promise_type = classify_promise_type(lifecycle_item)
    execution_status = resolve_execution_status(lifecycle_item)
    financial_link_status = resolve_financial_link_status(lifecycle_item)
    outcome_status = resolve_outcome_status(
        lifecycle_item,
        execution_status=execution_status,
        financial_link_status=financial_link_status,
    )
    current_status = resolve_current_status(lifecycle_item, outcome_status, execution_status)
    later_evidence = extract_later_evidence(lifecycle_item)
    evidence_ids = _merge_evidence_ids(commitment, lifecycle_item)
    investor_interpretation = build_investor_interpretation(lifecycle_item, execution_status, outcome_status)
    measurable = _measurable_target(lifecycle_item, measurable_commitments)
    no_match = not bool(lifecycle_item.get("source_item_id") or lifecycle_item.get("item_id", "").startswith("MP-"))

    if no_match:
        execution_status = "CLAIM_ONLY"
        outcome_status = "UNVERIFIED"
        financial_link_status = "INSUFFICIENT_EVIDENCE"
        current_status = "UNVERIFIED"
        later_evidence = []
        investor_interpretation = "This commitment remains unverified because no matching Management Progression lifecycle record was found."

    verification_states = {
        str(event.get("verification_status") or "").strip().lower()
        for event in lifecycle_item.get("events") or []
        if isinstance(event, dict)
    }
    if "contradicted" in verification_states:
        accountability_verification_state = "CONTRADICTED"
    elif "verified" in verification_states and execution_status == "ACTION_COMPLETED":
        accountability_verification_state = "VERIFIED"
    elif "partially_verified" in verification_states and execution_status in {"ACTION_STARTED", "ACTION_COMPLETED"}:
        accountability_verification_state = "PARTIALLY_VERIFIED"
    else:
        accountability_verification_state = "UNVERIFIED"

    if commitment.get("accountability_ontology") == "VERIFIABLE_COMMITMENT":
        if accountability_verification_state == "VERIFIED":
            current_status = "ACHIEVED"
            investor_interpretation = (
                "Delivery is verified by an authoritative linked execution event. "
                "The financial consequence remains separate and must not be inferred from completion alone."
            )
        elif accountability_verification_state == "PARTIALLY_VERIFIED":
            current_status = "PARTIALLY_ACHIEVED"
        elif accountability_verification_state == "CONTRADICTED":
            current_status = "MISSED"

    record: Dict[str, Any] = {
        "promise_id": promise_id,
        "commitment_fingerprint": fingerprint,
        "management_commitment_id": _commitment_id(commitment),
        "source_item_id": lifecycle_item.get("item_id") if not no_match else None,
        "theme": str(commitment.get("topic") or lifecycle_item.get("theme") or "").strip()[:200],
        "original_statement": str(commitment.get("original_statement") or _original_statement(lifecycle_item)).strip(),
        "normalized_commitment": str(commitment.get("normalized_commitment") or "").strip(),
        "announcement_period": _commitment_period(commitment),
        "source_period": _commitment_period(commitment),
        "target_period": _commitment_target_period(commitment) or _target_period(lifecycle_item),
        "category": commitment.get("category") or "",
        "specificity": commitment.get("statement_type") or "",
        "accountability_ontology": commitment.get("accountability_ontology") or "STRATEGIC_INTENT",
        "verification_applicability": commitment.get("verification_applicability") or "NOT_APPLICABLE",
        "materiality": ((commitment.get("semantic_quality") or {}).get("materiality") if isinstance(commitment.get("semantic_quality"), dict) else None) or commitment.get("priority") or "",
        "promise_type": promise_type,
        "progression_status": lifecycle_item.get("current_status") or "announced",
        "progression_confidence": (lifecycle_item.get("confidence") or {}).get("level") if isinstance(lifecycle_item.get("confidence"), dict) else commitment.get("confidence"),
        "progression_source_item_ids": [lifecycle_item.get("item_id")] if lifecycle_item.get("item_id") and not no_match else [],
        "unresolved_reason": "NO_MATCHING_PROGRESSION_RECORD" if no_match else "",
        "execution_status": execution_status,
        "outcome_status": outcome_status,
        "financial_link_status": financial_link_status,
        "current_status": current_status,
        "accountability_verification_state": accountability_verification_state,
        "later_evidence": later_evidence,
        "evidence_ids": evidence_ids,
        "linked_company_model_ids": lifecycle_item.get("linked_company_model_ids") or [],
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

    # Load sources. Management Commitments owns promise identity; Management
    # Progression may only enrich lifecycle by exact commitment_fingerprint.
    memory_root = companies_root / company_slug / "company_memory"
    commitments_payload = _load_json(_management_commitments_path(company_slug, companies_root))
    progression = _load_json(_management_progression_path(company_slug, companies_root))
    measurable_commitments = progression.get("measurable_commitments") or []

    all_commitments = [c for c in commitments_payload.get("commitments") or [] if isinstance(c, dict)]
    valid_fingerprints = {_commitment_fingerprint(c) for c in all_commitments if _commitment_fingerprint(c)}
    lifecycle_index = _commitment_lifecycle_index(progression, valid_fingerprints)

    trivial_count = 0
    material_commitments: List[Dict[str, Any]] = []
    for commitment in all_commitments:
        if is_material_commitment_promise(commitment):
            material_commitments.append(commitment)
        else:
            trivial_count += 1

    promises: List[Dict[str, Any]] = []
    for idx, commitment in enumerate(material_commitments, start=1):
        fingerprint = _commitment_fingerprint(commitment)
        lifecycle_item = lifecycle_index.get(fingerprint) or _commitment_as_progression_seed(commitment)
        record = _build_promise_record(commitment, lifecycle_item, measurable_commitments, idx)
        promises.append(record)

    # Sort by materiality rank descending
    promises.sort(key=materiality_rank, reverse=True)

    # Partition into resolved / unresolved
    resolved = [p for p in promises if p["current_status"] in ("ACHIEVED", "PARTIALLY_ACHIEVED", "MISSED", "ABANDONED")]
    unresolved = [p for p in promises if p["current_status"] not in ("ACHIEVED", "PARTIALLY_ACHIEVED", "MISSED", "ABANDONED")]

    accountability_promises = [
        p for p in promises if p.get("accountability_ontology") == "VERIFIABLE_COMMITMENT"
    ]
    strategic_statements = [
        p for p in promises if p.get("accountability_ontology") != "VERIFIABLE_COMMITMENT"
    ]
    ontology_counts = Counter(p.get("accountability_ontology") or "STRATEGIC_INTENT" for p in promises)
    # Credibility patterns describe the accountability denominator, not all
    # strategic/aspirational management statements.
    credibility_patterns = _build_credibility_patterns(accountability_promises)

    # Summary retains the material-statement universe for compatibility while
    # accountability_metrics is the sole promise-delivery denominator.
    summary = _build_summary(promises, company_slug, credibility_patterns, trivial_count)
    verification_counts = Counter(
        p.get("accountability_verification_state") or "UNVERIFIED"
        for p in accountability_promises
    )
    summary["accountability_metrics"] = {
        "material_verifiable_commitments": len(accountability_promises),
        "verified_commitments": verification_counts.get("VERIFIED", 0),
        "partially_verified_commitments": verification_counts.get("PARTIALLY_VERIFIED", 0),
        "contradicted_commitments": verification_counts.get("CONTRADICTED", 0),
        "unresolved_verifiable_commitments": verification_counts.get("UNVERIFIED", 0),
        "strategic_intents": ontology_counts.get("STRATEGIC_INTENT", 0),
        "aspirations": ontology_counts.get("ASPIRATION", 0),
        "policies_or_principles": ontology_counts.get("POLICY_OR_PRINCIPLE", 0),
    }

    # Critical follow-up
    critical_followup = _build_critical_followup(promises)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "company_slug": company_slug,
        "generated_at": generated_at,
        "summary": summary,
        "material_promises": promises,
        "accountability_promises": accountability_promises,
        "strategic_intent_statements": strategic_statements,
        "resolved_promises": resolved,
        "unresolved_promises": unresolved,
        "credibility_patterns": credibility_patterns,
        "critical_follow_up": critical_followup,
    }
    validate_management_promise_tracker(payload, all_commitments=all_commitments, lifecycle_index=lifecycle_index)
    return payload


def validate_management_promise_tracker(
    payload: Dict[str, Any],
    *,
    all_commitments: List[Dict[str, Any]],
    lifecycle_index: Dict[str, Dict[str, Any]],
) -> None:
    mc_fingerprints = {_commitment_fingerprint(c) for c in all_commitments if _commitment_fingerprint(c)}
    seen: Set[str] = set()
    promises = payload.get("material_promises") or []
    for idx, promise in enumerate(promises):
        if not isinstance(promise, dict):
            raise ValueError(f"Gold promise tracker invalid row at index {idx}: not an object")
        fingerprint = str(promise.get("commitment_fingerprint") or "").strip()
        if not fingerprint:
            raise ValueError(f"Gold promise tracker invalid row at index {idx}: missing commitment_fingerprint")
        if fingerprint not in mc_fingerprints:
            raise ValueError(f"Gold promise tracker invalid row at index {idx}: fingerprint not found in Management Commitments")
        if fingerprint in seen:
            raise ValueError(f"Gold promise tracker invalid row at index {idx}: duplicate commitment_fingerprint")
        seen.add(fingerprint)
        has_lifecycle = fingerprint in lifecycle_index
        if promise.get("current_status") != "UNVERIFIED" and not has_lifecycle:
            raise ValueError(f"Gold promise tracker invalid row at index {idx}: non-UTV status without matching MP lifecycle evidence")
        if promise.get("source_item_id") and not has_lifecycle:
            raise ValueError(f"Gold promise tracker invalid row at index {idx}: non-MC progression item represented as promise")
    summary = payload.get("summary") or {}
    sb = summary.get("status_breakdown") or {}
    bucket_total = sum(int(sb.get(k) or 0) for k in ("achieved", "partially_achieved", "delayed", "missed", "abandoned", "unverified"))
    if int(summary.get("tracked_promises") or 0) != len(promises):
        raise ValueError("Gold promise tracker summary tracked_promises does not match material_promises length")
    if bucket_total != len(promises):
        raise ValueError("Gold promise tracker status buckets do not reconcile to tracked_promises")
    resolved = payload.get("resolved_promises") or []
    unresolved = payload.get("unresolved_promises") or []
    if len(resolved) + len(unresolved) != len(promises):
        raise ValueError("Gold promise tracker resolved/unresolved partitions do not reconcile")


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
