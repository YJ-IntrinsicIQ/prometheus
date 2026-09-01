from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple


GENERIC_LINK_WORDS = {
    "growth",
    "expansion",
    "capacity",
    "platform",
    "efficiency",
    "business",
    "bounded",
    "control",
    "deliver",
    "delivery",
    "direction",
    "execution",
    "focus",
    "improve",
    "operating",
    "operational",
    "objective",
    "readiness",
    "project",
    "product",
    "development",
    "support",
}

# Extended generic set for cross-year linking — adds common verbs and prepositions
# that appear in many unrelated initiatives.
_CROSS_YEAR_GENERIC = GENERIC_LINK_WORDS | {
    "action",
    "company",
    "management",
    "market",
    "strategy",
    "initiative",
    "programme",
    "program",
    "system",
    "services",
    "service",
    "approach",
    "following",
    "through",
    "ensure",
    "provide",
    "across",
    "enable",
    "their",
    "would",
    "could",
    "while",
    "given",
    "under",
    "since",
    "after",
    "being",
    "using",
    "other",
    "these",
    "about",
    "within",
    "order",
    "based",
    "level",
    "levels",
}

_CHAIN_STATUS_HIERARCHY: Dict[str, int] = {
    "FINANCIAL_IMPACT_CONFIRMED": 9,
    "FINANCIAL_LINK_UNPROVEN": 8,
    "OUTCOME_POSITIVE": 7,
    "OUTCOME_NEGATIVE": 6,
    "OUTCOME_MIXED": 5,
    "EARLY_OPERATING_SIGNAL": 4,
    "ACTION_COMPLETED": 3,
    "PARTIAL_EXECUTION": 3,
    "ACTION_STARTED": 2,
    "CLAIM_ONLY": 1,
    "OUTCOME_UNKNOWN": 1,
}

_DELIVERY_STATUSES = frozenset(
    {"ACHIEVED", "PARTIALLY_ACHIEVED", "DELAYED", "MISSED", "ABANDONED", "UNVERIFIED"}
)

_TARGET_RE = re.compile(
    r"(?:"
    r"\d[\d,.]*\s*%\s*(?:reduction|improvement|growth|increase|decrease|target|savings|cutback)"
    r"|(?:achieve|target|reach|grow\s+to)\s+[₹\$]?\s*\d[\d,.]+"
    r"|\d[\d,.]+\s*%\s+of\s+(?:sales|revenue|net)"
    r"|\d[\d,]+(?:\s+\w+){0,2}\s+(?:branches|stores|outlets|facilities|plants|beds|centres?|centers?)"
    r")",
    re.IGNORECASE,
)

_PERIOD_RE = re.compile(r"\b(?:by\s+)?(fy\s*\d{2,4}|\d{4})\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public API — existing functions (unchanged)
# ---------------------------------------------------------------------------


def link_company_model_ids(text: str, company_model: Dict[str, Any]) -> List[str]:
    linked: List[str] = []
    normalized_text = _normalize(text)
    if not normalized_text:
        return []
    for item in company_model.get("offerings", []) or []:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("offering_id") or "").strip()
        candidates = [item.get("name"), item.get("description"), item.get("customer_problem_solved")]
        if identifier and _has_specific_overlap(normalized_text, candidates):
            linked.append(identifier)
    for item in company_model.get("revenue_engines", []) or []:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("engine_id") or "").strip()
        candidates = [item.get("description"), item.get("billing_basis")]
        if identifier and _has_specific_overlap(normalized_text, candidates):
            linked.append(identifier)
    return list(dict.fromkeys(linked))


def theme_key(text: str) -> str:
    words = [
        word
        for word in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(word) >= 4 and word not in GENERIC_LINK_WORDS
    ]
    return "_".join(words[:6]) or "unclassified_progression"


def duplicate_key(event: Dict[str, Any]) -> str:
    basis = "|".join(
        [
            str(event.get("role") or ""),
            str(event.get("event_type") or ""),
            str(event.get("source_period") or ""),
            str(event.get("event_period") or ""),
            _normalize(
                event.get("statement_text")
                or event.get("action_taken")
                or event.get("operational_outcome")
                or event.get("financial_or_business_outcome")
            )[:180],
            ",".join(sorted(_evidence_ids(event))),
        ]
    )
    return basis


# ---------------------------------------------------------------------------
# Public API — new: cross-year linking
# ---------------------------------------------------------------------------


def build_cross_year_links(
    items: List[Dict[str, Any]],
    *,
    consistency_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build cross-year management thesis chains, measurable commitments, and
    contradiction signals from a list of progression items.

    Args:
        items: progression_items list from the producer.
        consistency_data: optional dict loaded from management_consistency.json.
            When provided, unresolved promises and measurable targets from
            promise_follow_through_summary are incorporated into the output.

    Returns a dict with:
      - management_thesis_chains
      - measurable_commitments
      - contradiction_signals
    """
    thesis_chains = _build_thesis_chains(items)
    measurable_commitments = _build_measurable_commitments(items, thesis_chains)
    contradiction_signals = _detect_contradiction_signals(items)

    if consistency_data:
        extra_mc, extra_signals = _build_consistency_signals(
            consistency_data, len(measurable_commitments), len(contradiction_signals)
        )
        measurable_commitments = measurable_commitments + extra_mc
        contradiction_signals = contradiction_signals + extra_signals

    return {
        "management_thesis_chains": thesis_chains,
        "measurable_commitments": measurable_commitments,
        "contradiction_signals": contradiction_signals,
    }


# ---------------------------------------------------------------------------
# Internal: item similarity
# ---------------------------------------------------------------------------


def _cross_year_anchor_words(text: str) -> List[str]:
    """Specific words (≥5 chars, not generic) used as linking anchors."""
    return [
        word
        for word in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(word) >= 5 and word not in _CROSS_YEAR_GENERIC
    ]


def _all_evidence_ids(item: Dict[str, Any]) -> frozenset:
    ids: List[str] = []
    for ev in item.get("events") or []:
        ids.extend(_evidence_ids(ev))
    return frozenset(ids)


def _items_are_linked(
    item_a: Dict[str, Any], item_b: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Conservative cross-year linking.

    Returns (linked: bool, basis: str).

    Rules (in priority order):
      1. Shared evidence ID → definitively the same source document.
      2. Both items have model IDs, at least 1 shared model, AND ≥4 shared
         anchor words in the theme text → high-confidence same initiative.

    Uncertain → keep separate (returns False).
    """
    # Rule 1: shared evidence
    shared_ev = _all_evidence_ids(item_a) & _all_evidence_ids(item_b)
    if shared_ev:
        return True, "shared_evidence"

    # Rule 2: model anchor + word overlap
    models_a = frozenset(item_a.get("linked_company_model_ids") or [])
    models_b = frozenset(item_b.get("linked_company_model_ids") or [])
    if not models_a or not models_b:
        return False, "no_model_anchor"
    if not (models_a & models_b):
        return False, "disjoint_models"

    words_a = set(_cross_year_anchor_words(item_a.get("theme", "")))
    words_b = set(_cross_year_anchor_words(item_b.get("theme", "")))
    if len(words_a & words_b) >= 4:
        return True, "model_and_word_overlap"

    return False, "insufficient_overlap"


# ---------------------------------------------------------------------------
# Internal: thesis chain building
# ---------------------------------------------------------------------------


def _period_year_int(period: Any) -> int:
    m = re.search(r"(\d{2,4})", str(period or "").lower())
    if not m:
        return 9999
    v = int(m.group(1))
    return 2000 + v if v < 100 else v


def _item_earliest_year(item: Dict[str, Any]) -> int:
    periods = [
        ev.get("source_period") or ev.get("event_period", "")
        for ev in (item.get("events") or [])
    ]
    years = [_period_year_int(p) for p in periods if p]
    return min(years) if years else 9999


def _build_thesis_chains(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cluster related items into evolving management thesis chains (union-find)."""
    n = len(items)
    parent = list(range(n))
    link_bases: Dict[Tuple[int, int], str] = {}

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(x: int, y: int, basis: str) -> None:
        px, py = _find(x), _find(y)
        if px != py:
            key = (min(px, py), max(px, py))
            parent[px] = py
            link_bases[key] = basis

    for i in range(n):
        for j in range(i + 1, n):
            linked, basis = _items_are_linked(items[i], items[j])
            if linked:
                _union(i, j, basis)

    groups: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        groups[_find(i)].append(i)

    chains: List[Dict[str, Any]] = []
    thesis_num = 0
    for _root, indices in sorted(groups.items()):
        if len(indices) < 2:
            continue  # Solo items do not form thesis chains
        thesis_num += 1
        group_items = sorted([items[i] for i in indices], key=_item_earliest_year)

        all_periods: set = set()
        for item in group_items:
            for ev in item.get("events") or []:
                p = ev.get("source_period") or ev.get("event_period", "")
                if p:
                    all_periods.add(p)

        evolution: List[Dict[str, Any]] = []
        for item in group_items:
            events = item.get("events") or []
            item_periods = [
                ev.get("source_period") or ev.get("event_period", "")
                for ev in events
                if ev.get("source_period") or ev.get("event_period")
            ]
            earliest = min(item_periods, key=_period_year_int, default="")
            cs = (item.get("synthesis_chain") or {}).get("chain_status", "")
            evolution.append(
                {"item_id": item.get("item_id", ""), "period": earliest, "chain_status": cs}
            )

        all_statuses = [
            (item.get("synthesis_chain") or {}).get("chain_status", "") for item in group_items
        ]
        strongest = max(all_statuses, key=lambda s: _CHAIN_STATUS_HIERARCHY.get(s, 0), default="")

        basis_values = list(link_bases.values())
        basis = "shared_evidence" if "shared_evidence" in basis_values else "model_and_word_overlap"

        # Use the theme from the item with highest chain_status (most progressed)
        theme_source = max(
            group_items,
            key=lambda it: _CHAIN_STATUS_HIERARCHY.get(
                (it.get("synthesis_chain") or {}).get("chain_status", ""), 0
            ),
        )
        thesis_theme = (theme_source.get("theme") or "")[:120]

        chains.append(
            {
                "thesis_id": f"TH-{thesis_num:04d}",
                "thesis_theme": thesis_theme,
                "linked_item_ids": [item.get("item_id", "") for item in group_items],
                "earliest_period": evolution[0]["period"] if evolution else "",
                "latest_period": evolution[-1]["period"] if evolution else "",
                "years_with_evidence": sorted(all_periods, key=_period_year_int),
                "strongest_chain_status": strongest,
                "chain_evolution": evolution,
                "link_basis": basis,
            }
        )

    return chains


# ---------------------------------------------------------------------------
# Internal: measurable commitment extraction
# ---------------------------------------------------------------------------


def _extract_measurable_target(text: str) -> Optional[Dict[str, Any]]:
    """Extract the first measurable numeric target from text. Returns None if none found."""
    if not text:
        return None
    matches = _TARGET_RE.findall(text)
    if not matches:
        return None
    period_matches = _PERIOD_RE.findall(text)
    target_period = period_matches[-1].lower().replace(" ", "") if period_matches else None
    return {
        "target_text": matches[0],
        "target_period": target_period,
        "full_statement": text[:250],
    }


def _classify_delivery_status(
    source_period: str,
    target_period: Optional[str],
    linked_items: List[Dict[str, Any]],
) -> str:
    """Classify delivery status by scanning later events in the item's thesis chain."""
    source_year = _period_year_int(source_period)
    target_year = _period_year_int(target_period) if target_period else 9999

    has_full_completion = False
    has_partial_completion = False
    has_abandonment = False
    has_contradiction = False
    latest_evidence_year = source_year

    for item in linked_items:
        for ev in item.get("events") or []:
            ev_year = _period_year_int(ev.get("source_period") or ev.get("event_period", ""))
            if ev_year <= source_year:
                continue
            latest_evidence_year = max(latest_evidence_year, ev_year)
            role = ev.get("role", "")
            vs = ev.get("verification_status", "")
            if role in ("completion", "outcome"):
                if vs == "verified":
                    has_full_completion = True
                elif vs == "partially_verified":
                    has_partial_completion = True
            if role in ("reversal", "abandonment"):
                has_abandonment = True
            if vs == "contradicted":
                has_contradiction = True

    if has_abandonment:
        return "ABANDONED"
    if has_contradiction:
        return "MISSED"
    if has_full_completion:
        return "ACHIEVED"
    if has_partial_completion:
        return "PARTIALLY_ACHIEVED"
    # DELAYED: target period is known, has passed, and there is still later activity
    if (
        target_year < 9999
        and latest_evidence_year > target_year
    ):
        return "DELAYED"
    return "UNVERIFIED"


def _build_measurable_commitments(
    items: List[Dict[str, Any]],
    thesis_chains: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Extract measurable commitments from commitment/statement events."""
    item_by_id = {item.get("item_id", ""): item for item in items}
    item_to_chain_items: Dict[str, List[Dict[str, Any]]] = {}
    for chain in thesis_chains:
        chain_items = [item_by_id[iid] for iid in chain["linked_item_ids"] if iid in item_by_id]
        for iid in chain["linked_item_ids"]:
            item_to_chain_items[iid] = chain_items

    commitments: List[Dict[str, Any]] = []
    seen_target_keys: set = set()

    for item in items:
        item_id = item.get("item_id", "")
        for ev in item.get("events") or []:
            if ev.get("role") not in ("commitment", "statement"):
                continue
            text = ev.get("statement_text") or ev.get("action_taken") or ""
            target = _extract_measurable_target(text)
            if not target:
                continue
            dedup_key = " ".join(target["target_text"].lower().split())
            if dedup_key in seen_target_keys:
                continue
            seen_target_keys.add(dedup_key)

            source_period = ev.get("source_period") or ev.get("event_period", "")
            # Check within the item itself + any linked thesis chain items
            scope = item_to_chain_items.get(item_id, [item])
            if item not in scope:
                scope = [item] + scope
            delivery = _classify_delivery_status(
                source_period, target.get("target_period"), scope
            )
            commitments.append(
                {
                    "commitment_id": f"MC-LINK-{len(commitments) + 1:04d}",
                    "source_item_id": item_id,
                    "original_statement": target["full_statement"],
                    "extracted_target": target["target_text"],
                    "target_period": target.get("target_period"),
                    "source_period": source_period,
                    "delivery_status": delivery,
                }
            )

    return commitments


# ---------------------------------------------------------------------------
# Internal: contradiction detection
# ---------------------------------------------------------------------------


def _detect_contradiction_signals(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flag items where:
      - A later event has verification_status == "contradicted" (explicit contradiction), OR
      - A commitment/statement is repeated unresolved across ≥3 fiscal years (repeated_unresolved).
    Silence alone (no later evidence) is NOT flagged as a contradiction.
    """
    signals: List[Dict[str, Any]] = []

    for item in items:
        events = sorted(
            item.get("events") or [],
            key=lambda ev: _period_year_int(ev.get("source_period") or ev.get("event_period", "")),
        )
        if len(events) < 2:
            continue

        first_ev = events[0]
        first_role = first_ev.get("role", "")
        first_period = first_ev.get("source_period") or first_ev.get("event_period", "")
        first_year = _period_year_int(first_period)
        first_text = (
            first_ev.get("statement_text") or first_ev.get("action_taken") or ""
        )[:200]

        flagged = False
        for later_ev in events[1:]:
            if flagged:
                break
            later_period = later_ev.get("source_period") or later_ev.get("event_period", "")
            later_year = _period_year_int(later_period)
            later_vs = later_ev.get("verification_status", "")
            later_role = later_ev.get("role", "")
            later_text = (
                later_ev.get("statement_text")
                or later_ev.get("action_taken")
                or later_ev.get("operational_outcome")
                or ""
            )[:200]

            if later_vs == "contradicted" and first_role in ("commitment", "statement"):
                signals.append(
                    {
                        "signal_id": f"CONTRA-{len(signals) + 1:04d}",
                        "signal_type": "explicit_contradiction",
                        "source_item_id": item.get("item_id", ""),
                        "earlier_period": first_period,
                        "earlier_claim": first_text,
                        "later_period": later_period,
                        "later_evidence": later_text,
                        "contradiction_type": "claim_contradicted",
                    }
                )
                flagged = True

            elif (
                later_role in ("commitment", "statement")
                and first_role in ("commitment", "statement")
                and later_year - first_year >= 3
                and later_vs in ("unresolved",)
            ):
                signals.append(
                    {
                        "signal_id": f"CONTRA-{len(signals) + 1:04d}",
                        "signal_type": "repeated_unresolved",
                        "source_item_id": item.get("item_id", ""),
                        "earlier_period": first_period,
                        "earlier_claim": first_text,
                        "later_period": later_period,
                        "later_evidence": later_text,
                        "contradiction_type": "commitment_repeated_unresolved",
                    }
                )
                flagged = True

    return signals


# ---------------------------------------------------------------------------
# Internal: management_consistency.json integration
# ---------------------------------------------------------------------------

_PROMISE_PREFIX_RE = re.compile(r"^promise_(fy\s*\d{2,4}|\d{4})_(.+)$", re.IGNORECASE)


def _parse_promise_entry(entry: str) -> Optional[Tuple[str, str]]:
    """
    Parse "promise_fy20_we continue disciplined identifying future r d projects"
    into ("fy20", "we continue disciplined identifying future r d projects").
    Returns None if the format doesn't match.
    """
    m = _PROMISE_PREFIX_RE.match(str(entry or "").strip())
    if not m:
        return None
    period = m.group(1).lower().replace(" ", "")
    text = m.group(2).strip()
    return period, text


def _build_consistency_signals(
    consistency_data: Dict[str, Any],
    mc_offset: int,
    signal_offset: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extract measurable commitments and contradiction signals from
    management_consistency.json promise_follow_through_summary.
    """
    pfts = (consistency_data or {}).get("promise_follow_through_summary") or {}
    unresolved = pfts.get("repeated_unresolved_promises") or []

    new_commitments: List[Dict[str, Any]] = []
    new_signals: List[Dict[str, Any]] = []
    seen_target_keys: set = set()

    for entry in unresolved:
        parsed = _parse_promise_entry(entry)
        if not parsed:
            continue
        period, text = parsed

        # Contradiction signal: genuine promise left unresolved across years
        new_signals.append(
            {
                "signal_id": f"CONTRA-{signal_offset + len(new_signals) + 1:04d}",
                "signal_type": "repeated_unresolved",
                "source_item_id": None,
                "earlier_period": period,
                "earlier_claim": text[:200],
                "later_period": None,
                "later_evidence": "Recorded as unresolved in multi-year consistency audit.",
                "contradiction_type": "commitment_repeated_unresolved",
                "source": "management_consistency",
            }
        )

        # Also try to extract a measurable target from the promise text
        target = _extract_measurable_target(text)
        if target:
            dedup_key = " ".join(target["target_text"].lower().split())
            if dedup_key not in seen_target_keys:
                seen_target_keys.add(dedup_key)
                new_commitments.append(
                    {
                        "commitment_id": f"MC-LINK-{mc_offset + len(new_commitments) + 1:04d}",
                        "source_item_id": None,
                        "original_statement": target["full_statement"],
                        "extracted_target": target["target_text"],
                        "target_period": target.get("target_period"),
                        "source_period": period,
                        "delivery_status": "UNVERIFIED",
                        "source": "management_consistency",
                    }
                )

    return new_commitments, new_signals


# ---------------------------------------------------------------------------
# Internal helpers (shared)
# ---------------------------------------------------------------------------


def _evidence_ids(event: Dict[str, Any]) -> List[str]:
    ids = []
    for ref in event.get("evidence", []) or []:
        if isinstance(ref, dict) and ref.get("evidence_id"):
            ids.append(str(ref.get("evidence_id")))
    return ids


def _has_specific_overlap(text: str, candidates: Iterable[Any]) -> bool:
    text_words = set(_specific_words(text))
    if not text_words:
        return False
    for candidate in candidates:
        candidate_words = set(_specific_words(str(candidate or "")))
        if len(text_words & candidate_words) >= 2:
            return True
    return False


def _specific_words(text: str) -> List[str]:
    return [
        word
        for word in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(word) >= 5 and word not in GENERIC_LINK_WORDS
    ]


def _normalize(text: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))
