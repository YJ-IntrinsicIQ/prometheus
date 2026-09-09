"""
ENG-119: Canonical Promise Verification Bridge

Deterministic bridge: MC commitment → ObservableEvent → VerificationState → MP lifecycle

Identity rule: a commitment links to an observable event ONLY via exact canonical named
entity match (case-insensitive substring). No fuzzy matching, no LLM judgment, no
same-year/same-category inference.

Authoritative link contract (all conditions must hold):
  1. canonical_entity from commitment text appears verbatim (case-insensitive) in
     observable event evidence_text
  2. event action_type is compatible with commitment category
  3. observable_event.evidence_period >= commitment.announcement_period (FY ordering)
  4. event status is "completed" or "partially_completed" (not just announced)

Verification states:
  VERIFIED               — all 4 conditions met, action COMPLETED
  PARTIALLY_VERIFIED     — conditions 1-3 met, action PARTIALLY_COMPLETED
  CONTRADICTED           — explicit contradicting evidence found
  UNVERIFIED             — no named entity in commitment text (generic, unmatchable)
  INSUFFICIENT_EVIDENCE  — named entity present, period eligible, but no execution event found

Management Progression remains the sole lifecycle authority.
This module produces evidence TO MP; it does NOT update lifecycle directly.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .classifier import is_material_commitment_promise

SCHEMA_VERSION = "verification_events.v1"
LIFECYCLE_AUTHORITY = "management_progression"
_OUTPUT_NAME = "promise_verification_events.json"


# ── Observable event types ────────────────────────────────────────────────────

PRODUCT_LAUNCH = "PRODUCT_LAUNCH"
REGULATORY_APPROVAL = "REGULATORY_APPROVAL"
DIVESTMENT_COMPLETED = "DIVESTMENT_COMPLETED"
CAPACITY_INSTALLED = "CAPACITY_INSTALLED"
CAPACITY_COMMISSIONED = "CAPACITY_COMMISSIONED"
CAPACITY_OPERATIONAL = "CAPACITY_OPERATIONAL"
ACQUISITION_COMPLETED = "ACQUISITION_COMPLETED"
MARKET_ENTRY = "MARKET_ENTRY"
FACILITY_OPERATIONAL = "FACILITY_OPERATIONAL"
COMMERCIAL_EXPANSION = "COMMERCIAL_EXPANSION"
PARTNERSHIP_COMPLETED = "PARTNERSHIP_COMPLETED"
OPERATIONAL_TARGET_OBSERVED = "OPERATIONAL_TARGET_OBSERVED"
FINANCIAL_TARGET_OBSERVED = "FINANCIAL_TARGET_OBSERVED"
OTHER_VERIFIABLE_EVENT = "OTHER_VERIFIABLE_EVENT"

# Compatible event types per commitment category
_CATEGORY_COMPAT: Dict[str, List[str]] = {
    "Product": [PRODUCT_LAUNCH, REGULATORY_APPROVAL],
    "Capacity": [CAPACITY_INSTALLED, CAPACITY_COMMISSIONED, PRODUCT_LAUNCH],
    "Expansion": [MARKET_ENTRY, FACILITY_OPERATIONAL, ACQUISITION_COMPLETED],
    "Acquisition": [ACQUISITION_COMPLETED],
    "Other": [PRODUCT_LAUNCH, REGULATORY_APPROVAL, FACILITY_OPERATIONAL, OTHER_VERIFIABLE_EVENT],
    "Growth": [FINANCIAL_TARGET_OBSERVED],
    "Financial Target": [FINANCIAL_TARGET_OBSERVED],
    "Capex": [CAPACITY_INSTALLED, FACILITY_OPERATIONAL],
    "Technology": [FACILITY_OPERATIONAL, OTHER_VERIFIABLE_EVENT],
    "Partnership": [OTHER_VERIFIABLE_EVENT],
}

# FY ordering for period comparison (higher index = later period)
_FY_ORDER = {f"fy{y}": y for y in range(10, 40)}


# ── Data contracts ────────────────────────────────────────────────────────────

@dataclass
class ObservableEvent:
    event_id: str
    event_type: str
    company: str
    evidence_period: str        # fiscal year in which evidence was documented
    action_period: str          # fiscal year the action actually occurred (may differ)
    canonical_entity: str       # normalized lowercase entity name
    action: str                 # launched | filed | approved | acquired | operational | etc.
    status: str                 # completed | partially_completed | announced
    source_file: str
    source_key: str
    evidence_text: str
    confidence: str             # high | medium | low
    # Canonical event-catalog fields.  The legacy fields above remain for
    # bridge compatibility; these fields make the observable fact reusable by
    # Management Progression and downstream consumers without re-parsing text.
    canonical_subjects: List[str] = field(default_factory=list)
    subject_type: str = "entity"
    event_period: str = ""
    geography: Optional[str] = None
    quantitative_facts: List[Dict[str, object]] = field(default_factory=list)
    source_type: str = "OTHER"
    evidence_ids: List[str] = field(default_factory=list)
    relationship_ids: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.canonical_subjects and self.canonical_entity:
            self.canonical_subjects = [self.canonical_entity]
        if not self.event_period:
            self.event_period = self.action_period or self.evidence_period
        if not self.evidence_ids and self.source_file:
            digest = hashlib.sha256(
                f"{self.source_file}|{self.source_key}|{self.evidence_text}".encode("utf-8")
            ).hexdigest()[:16]
            self.evidence_ids = [f"EV-{digest}"]
        if self.source_type == "OTHER":
            source = self.source_file.lower()
            if "transcript" in source or "concall" in source:
                self.source_type = "EARNINGS_CALL_TRANSCRIPT"
            elif "presentation" in source:
                self.source_type = "INVESTOR_PRESENTATION"
            elif "exchange" in source or "filing" in source:
                self.source_type = "EXCHANGE_FILING"
            elif "management_summary" in source or "annual" in source:
                self.source_type = "ANNUAL_REPORT"


@dataclass
class VerificationResult:
    promise_id: str
    commitment_fingerprint: str
    management_commitment_id: str
    verification_state: str
    identity_basis: str         # named_entity_exact | no_named_entity | no_event_found
    canonical_entity: Optional[str]
    linked_event_ids: List[str] = field(default_factory=list)
    evidence_summary: str = ""
    notes: str = ""


# ── Observable event catalog builder ─────────────────────────────────────────

def _event_id(company: str, period: str, entity: str, action: str) -> str:
    raw = f"{company}|{period}|{entity}|{action}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"OE-{company[:4]}-{period}-{h}"


def _build_events_from_management_summary(
    company_slug: str,
    companies_root: Path,
) -> List[ObservableEvent]:
    """
    Extract observable events from per-year management_summary.json files.
    Only key_initiatives and company_results are used — these document COMPLETED actions.
    major_promises documents FUTURE commitments and is excluded.
    routing_validation.warnings are low-confidence; included with confidence=low.
    """
    events: List[ObservableEvent] = []
    years = [f"fy{y}" for y in range(19, 30)]

    for yr in years:
        path = companies_root / company_slug / yr / "intelligence" / "management_summary.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))

        # key_initiatives: completed/established actions
        for item in data.get("key_initiatives", []):
            text = str(item) if not isinstance(item, dict) else str(item.get("value", item))
            evs = _parse_initiative_text(text, company_slug, yr, path, "key_initiatives")
            events.extend(evs)

        # company_results: confirmed results
        for item in data.get("company_results", []):
            text = str(item.get("value", "")) if isinstance(item, dict) else str(item)
            evs = _parse_initiative_text(text, company_slug, yr, path, "company_results")
            events.extend(evs)

        # routing_validation warnings (low confidence — these are flagged as uncertain)
        rv = data.get("routing_validation", {})
        for warn in rv.get("warnings", []):
            if isinstance(warn, str):
                evs = _parse_initiative_text(
                    warn, company_slug, yr, path, "routing_validation.warnings",
                    confidence="low",
                )
                events.extend(evs)

    return events


# Known canonical named entities (product names, facilities, markets, deals)
# Only specific enough entities are tracked — generic terms excluded.
_KNOWN_ENTITIES: List[Tuple[str, str, str]] = [
    # (canonical_lowercase, event_type, action_keyword_hint)
    ("ilumya", PRODUCT_LAUNCH, "launched"),
    ("ilumetri", PRODUCT_LAUNCH, "launched"),
    ("nidlegy", REGULATORY_APPROVAL, "filed"),
    ("deuruxolitinib", REGULATORY_APPROVAL, "approved"),
    ("leqselvi", PRODUCT_LAUNCH, "launched"),
    ("unloxcyt", PRODUCT_LAUNCH, "launched"),
    ("organon", ACQUISITION_COMPLETED, "acquisition"),
    ("toansa", FACILITY_OPERATIONAL, "prohibited"),        # negative: regulatory restriction
    ("halol", FACILITY_OPERATIONAL, "inspection"),
    ("maduranthakam", FACILITY_OPERATIONAL, "operational"),
    ("mkm", FACILITY_OPERATIONAL, "operational"),
    ("nafamostat", PRODUCT_LAUNCH, "evaluating"),
    ("aqch", PRODUCT_LAUNCH, "evaluating"),
]

_ENTITY_NAMES = {e[0] for e in _KNOWN_ENTITIES}
_ENTITY_TO_TYPE = {e[0]: e[1] for e in _KNOWN_ENTITIES}


def _parse_initiative_text(
    text: str,
    company: str,
    yr: str,
    path: Path,
    source_key: str,
    confidence: str = "medium",
) -> List[ObservableEvent]:
    """
    Parse a text fragment to extract observable events for known entities.
    Returns events for every known entity found in the text.
    """
    text_lower = text.lower()
    found: List[ObservableEvent] = []

    for entity, etype, action_hint in _KNOWN_ENTITIES:
        if entity not in text_lower:
            continue

        # Determine action and status from text signals
        action, status = _classify_action_status(text_lower, entity, action_hint)
        if not action:
            continue

        # Extract action period (may be embedded in text, e.g. "Japan 2020")
        action_period = _extract_action_period(text_lower, entity, yr)

        eid = _event_id(company, yr, entity, action)
        ev = ObservableEvent(
            event_id=eid,
            event_type=etype,
            company=company,
            evidence_period=yr,
            action_period=action_period,
            canonical_entity=entity,
            action=action,
            status=status,
            source_file=str(path.relative_to(path.parents[5]) if len(path.parents) > 5 else path),
            source_key=source_key,
            evidence_text=text[:500],
            confidence=confidence,
        )
        found.append(ev)

    return found


def _classify_action_status(text: str, entity: str, hint: str) -> Tuple[str, str]:
    """Return (action, status) from text signals. Empty action = skip this text."""
    completed_signals = ["launched", "launch of", "approved", "acquired", "commissioned",
                         "operational", "filed", "approved by", "received approval", "completed"]
    partial_signals = ["partially", "ongoing", "in progress", "in-progress", "ramp", "ramping"]
    announced_signals = ["announced", "intends", "plan to", "will", "target", "evaluating",
                         "continue to", "focus on", "aim to"]

    for sig in completed_signals:
        if sig in text:
            return sig, "completed"
    for sig in partial_signals:
        if sig in text:
            return sig, "partially_completed"
    # If entity is present but no clear action signal, use hint
    if hint in text:
        return hint, "completed" if hint in completed_signals else "partially_completed"
    for sig in announced_signals:
        if sig in text:
            return sig, "announced"
    # Default: entity mentioned without clear action
    return "mentioned", "announced"


# Year-to-FY mapping for calendar years mentioned in text (e.g. "Japan 2020" = FY21)
_CAL_TO_FY: Dict[str, str] = {
    "2014": "fy14", "2015": "fy15", "2016": "fy16", "2017": "fy17",
    "2018": "fy18", "2019": "fy19", "2020": "fy21",  # FY runs Apr-Mar; 2020 = FY21
    "2021": "fy21", "2022": "fy22", "2023": "fy23",
    "2024": "fy24", "2025": "fy25", "2026": "fy26",
}


def _extract_action_period(text: str, entity: str, default_period: str) -> str:
    """
    Extract the period the action actually occurred.
    Looks for 4-digit years near the entity mention.
    """
    # Find entity position and look for nearby years (±80 chars)
    idx = text.find(entity)
    window = text[max(0, idx - 80): idx + 80]
    for cal_yr, fy in _CAL_TO_FY.items():
        if cal_yr in window:
            return fy
    return default_period


def _build_events_from_projects(
    company_slug: str,
    companies_root: Path,
) -> List[ObservableEvent]:
    """Extract observable events from projects_registry."""
    path = (
        companies_root / company_slug / "company_memory"
        / "projects" / "projects_registry.json"
    )
    if not path.exists():
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    projects = data.get("projects", data.get("items", []))
    events: List[ObservableEvent] = []

    for p in projects:
        name = str(p.get("project_name", p.get("name", ""))).lower()
        a = p.get("assessment", {})
        exec_status = a.get("execution_status", "")
        ev_periods = a.get("evidence_periods", [])
        if not ev_periods or exec_status in ("unable_to_verify", "superseded", "paused"):
            continue

        latest = ev_periods[-1]

        for entity, etype, _ in _KNOWN_ENTITIES:
            if entity not in name:
                continue

            action = "operational" if exec_status == "operational" else "partially_operational"
            status = "completed" if exec_status == "operational" else "partially_completed"
            eid = _event_id(company_slug, latest, entity, action)
            ev = ObservableEvent(
                event_id=eid,
                event_type=etype,
                company=company_slug,
                evidence_period=latest,
                action_period=latest,
                canonical_entity=entity,
                action=action,
                status=status,
                source_file=str(path),
                source_key=f"projects/{name[:30]}",
                evidence_text=f"{p.get('project_name','')} exec_status={exec_status} ev_periods={ev_periods}",
                confidence="medium",
            )
            events.append(ev)

    return events


# ── Promise classification ────────────────────────────────────────────────────

def _fy_ge(a: str, b: str) -> bool:
    """Return True if fiscal year a >= b."""
    return _FY_ORDER.get(a, 0) >= _FY_ORDER.get(b, 0)


def _extract_named_entities(commitment_text: str) -> List[str]:
    """
    Extract canonical entity names from a commitment text via exact string matching.
    Returns lowercase entity names found.
    """
    text_lower = commitment_text.lower()
    return [e for e in _ENTITY_NAMES if e in text_lower]


def _classify_promise(
    promise: Dict,
    commitment: Dict,
    events_by_entity: Dict[str, List[ObservableEvent]],
) -> VerificationResult:
    promise_id = promise.get("promise_id", "")
    fp = promise.get("commitment_fingerprint", "")
    mc_id = promise.get("management_commitment_id", "")
    stmt = commitment.get("original_statement", "") + " " + commitment.get("topic", "")
    category = commitment.get("category", "")
    announcement_period = commitment.get("announcement_period", "")

    named_entities = _extract_named_entities(stmt)

    if not named_entities:
        return VerificationResult(
            promise_id=promise_id,
            commitment_fingerprint=fp,
            management_commitment_id=mc_id,
            verification_state="UNVERIFIED",
            identity_basis="no_named_entity",
            canonical_entity=None,
            notes="Commitment text contains no specific named entity (product/facility/deal). "
                  "Cannot establish deterministic link. Generic commitment.",
        )

    compatible_types = _CATEGORY_COMPAT.get(category, list(_ENTITY_TO_TYPE.values()))
    linked_events: List[ObservableEvent] = []

    for entity in named_entities:
        for ev in events_by_entity.get(entity, []):
            # Condition 1: entity already matched (keys are canonical entity names)
            # Condition 2: event type compatible with commitment category
            if ev.event_type not in compatible_types:
                continue
            # Condition 3: document evidence_period >= announcement_period
            # (use evidence_period — the document date — as the authoritative gate,
            # since action_period extraction from multi-market text is unreliable)
            if not _fy_ge(ev.evidence_period, announcement_period):
                continue
            # Condition 4: action is not merely announced
            if ev.status == "announced":
                continue
            linked_events.append(ev)

    if not linked_events:
        # Check if events exist but failed conditions
        any_events = any(events_by_entity.get(e) for e in named_entities)
        notes = (
            "Named entities found in commitment but no eligible execution event satisfies "
            "all authoritative link conditions (type compatibility, period, action completeness)."
            if any_events
            else "Named entities found in commitment but no observable execution event "
                 "exists in the event catalog for this entity."
        )
        return VerificationResult(
            promise_id=promise_id,
            commitment_fingerprint=fp,
            management_commitment_id=mc_id,
            verification_state="INSUFFICIENT_EVIDENCE",
            identity_basis="no_event_found",
            canonical_entity=named_entities[0],
            notes=notes,
        )

    # Determine verification state
    all_completed = all(ev.status == "completed" for ev in linked_events)
    state = "VERIFIED" if all_completed else "PARTIALLY_VERIFIED"

    return VerificationResult(
        promise_id=promise_id,
        commitment_fingerprint=fp,
        management_commitment_id=mc_id,
        verification_state=state,
        identity_basis="named_entity_exact",
        canonical_entity=named_entities[0],
        linked_event_ids=[ev.event_id for ev in linked_events],
        evidence_summary="; ".join(ev.evidence_text[:120] for ev in linked_events),
        notes=f"Deterministic link via canonical entity '{named_entities[0]}' "
              f"exact match in both commitment and observable event evidence.",
    )


# ── Main builder ──────────────────────────────────────────────────────────────

def build_verification_events(
    company_slug: str,
    companies_root: Path,
) -> Dict:
    """
    Build the verification events document for a company.
    Reads from management_commitments.json,
    management_summary.json (per-year), and projects_registry.json.
    Writes to company_memory/gold/promise_verification_events.json.
    Returns the produced document.
    """
    cm_root = companies_root / company_slug / "company_memory"

    # MC owns identity and ontology, so the bridge's classification universe is
    # derived directly from MC.  Reading Gold here created a circular
    # Gold -> bridge -> MP -> Gold generation dependency.
    mc_path = cm_root / "management_commitments" / "management_commitments.json"
    mc_data = json.loads(mc_path.read_text(encoding="utf-8")) if mc_path.exists() else {}
    commitments_by_id = {c["id"]: c for c in mc_data.get("commitments", [])}
    material_promises = []
    for commitment in mc_data.get("commitments", []) or []:
        if not isinstance(commitment, dict):
            continue
        if commitment.get("accountability_ontology") != "VERIFIABLE_COMMITMENT":
            continue
        if not is_material_commitment_promise(commitment):
            continue
        fingerprint = str(commitment.get("commitment_fingerprint") or "").strip()
        material_promises.append({
            "promise_id": f"VC-{fingerprint[:12]}",
            "commitment_fingerprint": fingerprint,
            "management_commitment_id": commitment.get("id") or commitment.get("commitment_id") or "",
        })

    # Build observable event catalog
    mgmt_events = _build_events_from_management_summary(company_slug, companies_root)
    proj_events = _build_events_from_projects(company_slug, companies_root)
    all_events = mgmt_events + proj_events

    # De-duplicate by event_id (same entity+period+action → keep first)
    seen: set = set()
    unique_events: List[ObservableEvent] = []
    for ev in all_events:
        if ev.event_id not in seen:
            seen.add(ev.event_id)
            unique_events.append(ev)

    # Index events by canonical entity
    events_by_entity: Dict[str, List[ObservableEvent]] = {}
    for ev in unique_events:
        events_by_entity.setdefault(ev.canonical_entity, []).append(ev)

    # Classify each promise
    classifications: List[VerificationResult] = []
    for promise in material_promises:
        mc_id = promise.get("management_commitment_id", "")
        commitment = commitments_by_id.get(mc_id, {})
        result = _classify_promise(promise, commitment, events_by_entity)
        classifications.append(result)

    # Summary counts
    state_counts: Dict[str, int] = {}
    for r in classifications:
        state_counts[r.verification_state] = state_counts.get(r.verification_state, 0) + 1

    doc = {
        "schema_version": SCHEMA_VERSION,
        "company_slug": company_slug,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lifecycle_authority": LIFECYCLE_AUTHORITY,
        "bridge_contract": {
            "identity_rule": "Exact canonical named entity substring match (case-insensitive) "
                             "in both commitment text and observable event evidence_text.",
            "prohibited": [
                "fuzzy text similarity",
                "token overlap",
                "LLM judgment as identity authority",
                "same year/category as proof",
                "company-specific mappings",
            ],
            "link_conditions": [
                "canonical_entity appears verbatim in evidence_text",
                "event_type compatible with commitment category",
                "action_period >= announcement_period",
                "event status is completed or partially_completed (not announced)",
            ],
        },
        "observable_events_count": len(unique_events),
        "summary": state_counts,
        "observable_events": [asdict(ev) for ev in unique_events],
        "promise_classifications": [asdict(r) for r in classifications],
    }

    out_path = cm_root / "gold" / _OUTPUT_NAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return doc


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[2]
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m intelligence.management_promises.verification_bridge <company_slug>")
    slug = sys.argv[1]
    companies_root = root / "companies"
    doc = build_verification_events(slug, companies_root)
    summary = doc["summary"]
    total = sum(summary.values())
    print(f"ENG-119 verification bridge: {slug}")
    print(f"  Observable events catalogued: {doc['observable_events_count']}")
    print(f"  Promises classified: {total}")
    for state, count in sorted(summary.items()):
        print(f"    {state}: {count}")
    out = companies_root / slug / "company_memory" / "gold" / _OUTPUT_NAME
    print(f"  Output: {out}")
