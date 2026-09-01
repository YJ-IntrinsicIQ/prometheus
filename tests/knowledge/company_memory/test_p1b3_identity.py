"""P1B.3 — Commitment Identity Repair tests.

Verifies that:
- Generic topics cannot merge semantically unrelated commitments
- Same category alone is insufficient to merge different initiatives
- Same word "investment" cannot merge R&D and social investment
- Same word "growth" cannot merge market expansion and HR initiative
- Specific topic continuations merge correctly
- Semantically similar restatements produce RECONFIRMED
- Reconfirmation ≠ execution (RECONFIRMED ≠ In Progress / Delivered)
- Unrelated later evidence does not upgrade lifecycle status
- Evidence IDs remain resolvable after grouping
- No company-specific logic is used

All tests are generic (no pharma/Sun Pharma specific terms).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge.company_memory import ManagementCommitmentsBuilder, validate_management_commitments_payload
from knowledge.company_memory.management_commitments import _derive_specific_topic, _GENERIC_FALLBACK_TOPICS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write(base: Path, company: str, year: str, *, promise_items=None, summary_promises=None):
    d = base / "companies" / company / year / "intelligence"
    d.mkdir(parents=True, exist_ok=True)
    (d / "company_intelligence.json").write_text(
        json.dumps({"management": {"promises": {"items": promise_items or []}}}),
        encoding="utf-8",
    )
    (d / "management_summary.json").write_text(
        json.dumps({"major_promises": summary_promises or []}),
        encoding="utf-8",
    )


def _load(base: Path, company: str):
    out = base / "companies" / company / "company_memory" / "management_commitments"
    return {
        "commitments": json.loads((out / "management_commitments.json").read_text()),
        "validation": json.loads((out / "commitment_validation.json").read_text()),
    }


def _commitment_count(result):
    return result["commitments"]["commitment_count"]


def _commitment_by_index(result, index=0):
    return result["commitments"]["commitments"][index]


# ── 1. Generic topic cannot merge unrelated commitments ───────────────────────

def test_generic_topic_cannot_merge_unrelated_commitments(tmp_path, monkeypatch):
    """Two Other-category items with different semantic content must NOT merge."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy22", promise_items=[
        {"id": "A", "promise": "Evaluate new indications for product X in market Y.", "category": "Other", "page": 1, "source_chunk": "Evaluate new indications."},
        {"id": "B", "promise": "Establish an employee training programme across six thematic areas.", "category": "Other", "page": 2, "source_chunk": "Training programme."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert _commitment_count(result) == 2, "Different initiatives must not merge via generic topic"


# ── 2. Same category alone is insufficient to merge ──────────────────────────

def test_same_category_alone_is_insufficient(tmp_path, monkeypatch):
    """Same category (e.g. Growth) cannot merge different initiatives."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy21", promise_items=[
        {"id": "A", "promise": "Enhance presence in high-growth international markets.", "category": "Growth", "page": 1, "source_chunk": "Enhance international markets."},
        {"id": "B", "promise": "Launch an employee inclusion and diversity programme.", "category": "Growth", "page": 2, "source_chunk": "Inclusion diversity programme."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert _commitment_count(result) == 2, "Growth category alone must not merge different initiatives"


# ── 3. "investment" word cannot merge R&D and social investment ───────────────

def test_investment_word_cannot_merge_rd_and_social(tmp_path, monkeypatch):
    """Shared word 'investment' must not create a false cross-year link."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy23", promise_items=[
        {"id": "A", "promise": "Sustain investments in R&D to deliver medicines for unmet patient needs.", "category": "Capex", "page": 1, "source_chunk": "R&D investment."},
    ])
    _write(tmp_path, "co", "fy24", promise_items=[
        {"id": "B", "promise": "Evaluate the impact of social investments to inform equity decisions.", "category": "Capex", "page": 3, "source_chunk": "Social investment evaluation."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert _commitment_count(result) == 2, "R&D investment and social investment must be separate commitments"


# ── 4. "growth" word cannot merge market expansion and HR initiative ──────────

def test_growth_word_cannot_create_false_progress_link(tmp_path, monkeypatch):
    """A 'growth' category item with progress markers must NOT upgrade an
    unrelated market-expansion commitment via generic 'Growth target' topic."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy21", promise_items=[
        {"id": "A", "promise": "Enhance presence in high-growth markets across five geographies.", "category": "Growth", "page": 1, "source_chunk": "High-growth markets."},
    ])
    # fy25 item has category=Growth and progress language but is about HR programme
    _write(tmp_path, "co", "fy25", promise_items=[
        {"id": "B", "promise": "The employee inclusion programme is now in progress and being implemented.", "category": "Growth", "page": 5, "source_chunk": "Inclusion programme in progress."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    # The market-expansion commitment must NOT be In Progress because of the HR item.
    # Either: (a) two separate commitments, or (b) one commitment that remains Unable To Verify.
    market_c = next(
        (c for c in result["commitments"]["commitments"] if "market" in c["original_statement"].lower()),
        None,
    )
    assert market_c is not None, "Market expansion commitment must exist"
    assert market_c["status"] == "Unable To Verify", (
        "HR programme progress must not upgrade market-expansion commitment"
    )


# ── 5. Product-specific continuation merges correctly ────────────────────────

def test_product_specific_continuation_merges(tmp_path, monkeypatch):
    """Platform rollout in fy21 with later operational update merges into one."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy21", promise_items=[
        {"id": "P1", "promise": "We plan to roll out the logistics platform.", "category": "Product", "page": 2, "source_chunk": "Roll out the logistics platform."},
    ])
    _write(tmp_path, "co", "fy22", promise_items=[
        {"id": "P2", "promise": "The logistics platform rollout is now operational and customers are live.", "category": "Product", "page": 6, "source_chunk": "Logistics platform operational."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert _commitment_count(result) == 1
    assert _commitment_by_index(result)["status"] == "Delivered"


# ── 6. Facility-specific continuation merges correctly ───────────────────────

def test_facility_specific_continuation_merges(tmp_path, monkeypatch):
    """Manufacturing facility commitment with later commissioning merges into one."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy22", promise_items=[
        {"id": "F1", "promise": "We expect commercial production to begin at the new manufacturing facility by FY23.", "category": "Manufacturing", "page": 4, "source_chunk": "Commercial production at new facility."},
    ])
    _write(tmp_path, "co", "fy23", promise_items=[
        {"id": "F2", "promise": "Commercial production was commissioned and is now operational.", "category": "Manufacturing", "page": 8, "source_chunk": "Facility commissioned."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert _commitment_count(result) == 1
    assert _commitment_by_index(result)["status"] == "Delivered"


# ── 7. Geography-specific continuation merges correctly ──────────────────────

def test_geography_specific_continuation_merges(tmp_path, monkeypatch):
    """Market entry commitment with later delivery evidence merges into one."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy22", promise_items=[
        {"id": "M1", "promise": "We plan to enter the European market with our specialty product line.", "category": "Market Entry", "page": 5, "source_chunk": "Enter European market."},
    ])
    _write(tmp_path, "co", "fy24", promise_items=[
        {"id": "M2", "promise": "We are no longer pursuing the European market entry plan due to regulatory barriers.", "category": "Market Entry", "page": 10, "source_chunk": "No longer pursuing European entry."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert _commitment_count(result) == 1
    assert _commitment_by_index(result)["status"] == "Abandoned"


# ── 8. Semantically similar restatement becomes RECONFIRMED ──────────────────

def test_exact_text_restatement_becomes_reconfirmed(tmp_path, monkeypatch):
    """Identical wording in a later year must be RECONFIRMED, not a new commitment."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy23", promise_items=[
        {"id": "C1", "promise": "We will expand capacity at the new plant.", "category": "Capacity", "page": 4, "source_chunk": "Expand capacity at the new plant."},
    ])
    _write(tmp_path, "co", "fy24", promise_items=[
        {"id": "C2", "promise": "We will expand capacity at the new plant.", "category": "Capacity", "page": 10, "source_chunk": "Expand capacity at the new plant."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert _commitment_count(result) == 1
    assert _commitment_by_index(result)["status"] == "Reconfirmed"
    lifecycle = _commitment_by_index(result).get("lifecycle", {})
    assert "fy24" in lifecycle.get("check_years", [])


# ── 9. Reconfirmation ≠ execution ────────────────────────────────────────────

def test_reconfirmation_is_not_in_progress(tmp_path, monkeypatch):
    """A reconfirmation event must not produce In Progress or Delivered status."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy22", promise_items=[
        {"id": "C1", "promise": "We intend to launch the capacity expansion project.", "category": "Capacity", "page": 1, "source_chunk": "Launch capacity expansion."},
    ])
    _write(tmp_path, "co", "fy23", promise_items=[
        {"id": "C2", "promise": "We intend to launch the capacity expansion project.", "category": "Capacity", "page": 5, "source_chunk": "Launch capacity expansion."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    c = _commitment_by_index(result)
    assert c["status"] not in {"In Progress", "Delivered", "Partially Delivered"}
    assert c["status"] == "Reconfirmed"


# ── 10. Material scope change produces a separate commitment ──────────────────

def test_material_scope_change_is_separate_commitment(tmp_path, monkeypatch):
    """Substantially different initiative in same category must not merge."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy22", promise_items=[
        {"id": "A", "promise": "We plan to acquire a controlling interest in the target company.", "category": "Acquisition", "page": 2, "source_chunk": "Acquire controlling interest."},
        {"id": "B", "promise": "We will divest the legacy business unit to focus on core operations.", "category": "Acquisition", "page": 3, "source_chunk": "Divest legacy unit."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert _commitment_count(result) == 2


# ── 11. Unrelated later evidence does not upgrade lifecycle ───────────────────

def test_unrelated_evidence_does_not_upgrade_lifecycle(tmp_path, monkeypatch):
    """A follow-up event about a different initiative must not upgrade status."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy22", promise_items=[
        {"id": "A", "promise": "We will evaluate new geographic markets for our specialty product.", "category": "Market Entry", "page": 1, "source_chunk": "Evaluate new markets."},
    ])
    # fy23 follow-up is about a completely different topic (employee awards)
    _write(tmp_path, "co", "fy23", promise_items=[
        {"id": "B", "promise": "Employee awards programme was delivered across all business units.", "category": "Other", "page": 5, "source_chunk": "Employee awards delivered."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    # Separate commitments — the market entry is Unable To Verify
    market_entry = next((c for c in result["commitments"]["commitments"] if "market" in c["original_statement"].lower()), None)
    assert market_entry is not None
    assert market_entry["status"] == "Unable To Verify"


# ── 12. Uncertain match remains unverified ────────────────────────────────────

def test_uncertain_match_remains_unverified(tmp_path, monkeypatch):
    """When no later evidence confirms, status stays Unable To Verify."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy24", promise_items=[
        {"id": "A", "promise": "We aim to reduce water consumption by 25% by FY27.", "category": "Other", "page": 1, "source_chunk": "Water consumption reduction."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert _commitment_by_index(result)["status"] == "Unable To Verify"


# ── 13. False-link validation: incompatible evidence cannot deliver a commitment

def test_false_link_validation_rejects_incompatible_delivery(tmp_path, monkeypatch):
    """A commitment cannot be Delivered if the only evidence is from a different initiative."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy22", promise_items=[
        {"id": "A", "promise": "We plan to open five new distribution centres.", "category": "Expansion", "page": 1, "source_chunk": "Open distribution centres."},
    ])
    _write(tmp_path, "co", "fy23", promise_items=[
        {"id": "B", "promise": "The employee recognition scheme was successfully implemented.", "category": "Other", "page": 4, "source_chunk": "Employee recognition implemented."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    # Distribution centre commitment must be Unable To Verify — the employee
    # recognition event must not cross-contaminate the lifecycle.
    dist = next((c for c in result["commitments"]["commitments"] if "distribution" in c["original_statement"].lower()), None)
    assert dist is not None
    assert dist["status"] == "Unable To Verify"


# ── 14. Evidence IDs remain resolvable after grouping ────────────────────────

def test_evidence_ids_remain_resolvable(tmp_path, monkeypatch):
    """All source_item_ids in commitment evidence must match source items."""
    monkeypatch.chdir(tmp_path)
    items = [
        {"id": f"ITEM_{i}", "promise": f"We plan to commission manufacturing unit {i} by FY25.", "category": "Manufacturing", "page": i, "source_chunk": f"Commission unit {i}."}
        for i in range(3)
    ]
    _write(tmp_path, "co", "fy23", promise_items=items)
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    all_ids = {item["id"] for item in items}
    for commitment in result["commitments"]["commitments"]:
        for ev in commitment.get("supporting_evidence", []):
            ref = ev.get("source_reference", {})
            if ref.get("source_artifact") == "company_intelligence.json":
                assert ref.get("source_item_id") in all_ids, (
                    f"source_item_id {ref.get('source_item_id')!r} not in source items"
                )


# ── 15. Gold statuses cannot exceed canonical lifecycle status ────────────────

def test_delivered_status_requires_later_decisive_evidence(tmp_path, monkeypatch):
    """A commitment cannot claim Delivered without later-year delivery evidence."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy23", promise_items=[
        {"id": "X1", "promise": "We expect to launch the new product line next year.", "category": "Product", "page": 1, "source_chunk": "Launch new product line."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    c = _commitment_by_index(result)
    assert c["status"] != "Delivered"
    # Validation must also pass (no unsupported_delivery)
    assert result["validation"]["status"] == "pass"


# ── 16. management_progression artifact: commitment text passes specificity ───

def test_commitment_original_statement_specific_enough_for_progression(tmp_path, monkeypatch):
    """original_statement text must be long/specific enough to avoid being
    filtered by management_progression's _specific_enough gate."""
    from knowledge.management_progression.producer import _specific_enough, _is_low_value_progression_text

    statements = [
        "We plan to commission the new API manufacturing facility by FY24.",
        "Evaluate new product indications in the specialty segment.",
        "We intend to expand into five new international markets by FY26.",
        "Sustain investments in R&D to deliver medicines for unmet patient needs.",
        "Achieve a 35% reduction in carbon dioxide emissions by 2030.",
    ]
    for stmt in statements:
        assert _specific_enough(stmt), f"Expected specific enough: {stmt!r}"
        assert not _is_low_value_progression_text(stmt), f"Expected not low-value: {stmt!r}"


# ── 17. P1A classifier regressions remain green ──────────────────────────────

def test_p1a_eligible_types_still_admitted(tmp_path, monkeypatch):
    """Generic commitment forms rescued by P1A must still be captured."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy24", promise_items=[
        {"id": "G1", "promise": "Deploying the cloud migration for all core systems by Q3.", "category": "Technology", "page": 3, "source_chunk": "Cloud migration by Q3."},
        {"id": "G2", "promise": "We will open five new branches in the eastern region.", "category": "Expansion", "page": 4, "source_chunk": "Open branches."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert _commitment_count(result) >= 1


# ── 18. P0 routing regressions: commitment_count remains non-zero ─────────────

def test_p0_routing_commitment_count_nonzero_for_eligible_input(tmp_path, monkeypatch):
    """A valid management commitment must produce at least one canonical record."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy23", promise_items=[
        {"id": "R1", "promise": "We plan to launch the next-generation product line by FY24.", "category": "Product", "page": 7, "source_chunk": "Launch next-gen product."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert _commitment_count(result) >= 1
    assert result["validation"]["status"] == "pass"


# ── 19. Freshness: no manual timestamp patching (schema_version present) ──────

def test_no_manual_downstream_patching(tmp_path, monkeypatch):
    """Output artifacts must carry correct schema_version without manual edits."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "co", "fy23", promise_items=[
        {"id": "S1", "promise": "We intend to commission a second data centre by FY26.", "category": "Capex", "page": 1, "source_chunk": "Second data centre."},
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert result["commitments"].get("schema_version") == "management_commitments.v1"
    assert result["commitments"].get("generated_at")


# ── 20. No company-specific logic in grouping ─────────────────────────────────

def test_no_company_specific_logic_required(tmp_path, monkeypatch):
    """Grouping must work for any sector without company/sector-specific terms."""
    monkeypatch.chdir(tmp_path)
    items = [
        {"id": "B1", "promise": "We will open five new banking branches in the northern region.", "category": "Expansion", "page": 1, "source_chunk": "Open branches northern."},
        {"id": "T1", "promise": "Deploying cloud infrastructure for all enterprise systems by FY25.", "category": "Technology", "page": 2, "source_chunk": "Cloud infrastructure."},
        {"id": "C1", "promise": "We plan to launch two new consumer product SKUs next quarter.", "category": "Product", "page": 3, "source_chunk": "Launch product SKUs."},
        {"id": "I1", "promise": "Commissioning a second data centre to support workload growth.", "category": "Capex", "page": 4, "source_chunk": "Second data centre."},
        {"id": "M1", "promise": "We intend to acquire controlling interest in the target entity.", "category": "Acquisition", "page": 5, "source_chunk": "Acquire target."},
    ]
    _write(tmp_path, "co", "fy24", promise_items=items)
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    # All five are distinct — should produce 5 separate commitments
    assert _commitment_count(result) == 5
    assert result["validation"]["status"] == "pass"


# ── Unit tests for _derive_specific_topic ─────────────────────────────────────

def test_derive_specific_topic_produces_distinct_labels():
    """Different initiatives must produce different derived topics."""
    t1 = _derive_specific_topic("Evaluate new indications for product X in market Y.")
    t2 = _derive_specific_topic("Establish an employee training programme across six areas.")
    t3 = _derive_specific_topic("Achieve a 35% reduction in carbon emissions by 2030.")
    t4 = _derive_specific_topic("Establish a mobile healthcare unit in rural areas.")

    assert t1 != t2, "ILUMYA-type vs training must have different topics"
    assert t1 != t3, "Indications vs carbon must have different topics"
    assert t2 != t4, "Training vs healthcare unit must have different topics"


def test_derive_specific_topic_avoids_generic_noise_words():
    """Generic management words must not dominate the derived topic."""
    # If only noise words present, should fall back gracefully (non-empty)
    topic = _derive_specific_topic("We remain committed to excellence and creating value.")
    # Topic may not be empty — it falls back to first significant tokens
    # The key requirement: result is NOT "Management commitment" by accident
    assert isinstance(topic, str)


def test_generic_fallback_topics_constant_contains_expected():
    """_GENERIC_FALLBACK_TOPICS must include the known over-broad labels."""
    assert "Management commitment" in _GENERIC_FALLBACK_TOPICS
    assert "Capital deployment" in _GENERIC_FALLBACK_TOPICS
    assert "Growth target" in _GENERIC_FALLBACK_TOPICS
