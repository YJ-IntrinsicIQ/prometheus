"""P1B.2 cross-year lifecycle linking tests — generic, no company-specific terms.

Covers:
- Cross-year reconfirmation: same text in later year → Reconfirmed (not In Progress)
- Silence ≠ failure: no later evidence → Unable To Verify (not Missed)
- Lifecycle model: source_year, check_years, last_checked_year, lifecycle_events
- Deduplication: same-text cross-year merges to one commitment
- Reconfirmation evidence appears in evidence_updates
- Decisive evidence overrides reconfirmation
- Multiple reconfirmations across years
- Within-year duplicate still flagged as validation error
- Reconfirmed status in ALLOWED_STATUSES
- Reconfirmation event_type in progression events
- Single-year commitment → Unable To Verify
- Lifecycle target_year populated from expected_timeframe
- Reconfirmed commitment has correct delivery_assessment
- Progress after reconfirmation → In Progress (not Reconfirmed)
- Delivery after reconfirmation → Delivered
- Abandonment after reconfirmation → Abandoned
- RECONFIRMED ≠ ACTION_STARTED (no status upgrade for repeat text)
- check_years excludes announcement year
- last_checked_year is latest period in lifecycle
- Reconfirmation from summary source as well as intelligence source
- No extra commitments from reconfirmation-only years
- Lifecycle events list starts with announcement
- Reconfirmation event carries correct period
- Evidence_updates empty for single-evidence commitment with no later data
- Status counts include Reconfirmed
- Commitment_count unchanged by reconfirmation
- Delay after reconfirmation → Delayed
"""

import json
from pathlib import Path

import pytest

from knowledge.company_memory import ManagementCommitmentsBuilder
from knowledge.company_memory.management_commitments import ALLOWED_STATUSES


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_year(base: Path, company: str, year: str, *, items=None, summary=None) -> None:
    d = base / "companies" / company / year / "intelligence"
    d.mkdir(parents=True, exist_ok=True)
    (d / "company_intelligence.json").write_text(
        json.dumps({"management": {"promises": {"items": items or []}}}),
        encoding="utf-8",
    )
    (d / "management_summary.json").write_text(
        json.dumps({"major_promises": summary or []}),
        encoding="utf-8",
    )


def _load(base: Path, company: str):
    out = base / "companies" / company / "company_memory" / "management_commitments"
    return {
        "commitments": json.loads((out / "management_commitments.json").read_text()),
        "validation": json.loads((out / "commitment_validation.json").read_text()),
        "timeline": json.loads((out / "commitment_timeline.json").read_text()),
    }


def _item(promise: str, category: str = "Capacity", page: int = 1) -> dict:
    return {"id": "X", "promise": promise, "category": category, "page": page}


# ── 1. Reconfirmed in ALLOWED_STATUSES ──────────────────────────────────────

def test_reconfirmed_in_allowed_statuses():
    assert "Reconfirmed" in ALLOWED_STATUSES


# ── 2. Unable To Verify in ALLOWED_STATUSES ─────────────────────────────────

def test_unable_to_verify_in_allowed_statuses():
    assert "Unable To Verify" in ALLOWED_STATUSES


# ── 3. Single-year commitment → Unable To Verify ────────────────────────────

def test_single_year_no_later_evidence_is_unable_to_verify(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year(tmp_path, "co", "fy23", items=[_item("We will open five new branches by FY25.")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert result["commitments"]["commitment_count"] == 1
    commitment = result["commitments"]["commitments"][0]
    assert commitment["status"] == "Unable To Verify"


# ── 4. Silence ≠ Missed: no later evidence keeps Unable To Verify ────────────

def test_silence_is_unable_to_verify_not_missed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year(tmp_path, "co", "fy22", items=[_item("Deploy the cloud migration for all core systems by Q3.")])
    # fy23 and fy24 exist but contain no mention of the commitment
    _write_year(tmp_path, "co", "fy23", items=[_item("Launch a new product line by FY24.", "Product")])
    _write_year(tmp_path, "co", "fy24", items=[_item("Enter the eastern European market.", "Expansion")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    cloud = next(c for c in result["commitments"]["commitments"] if "cloud" in c["original_statement"].lower())
    assert cloud["status"] == "Unable To Verify"


# ── 5. Same text in later year → one commitment, status Reconfirmed ──────────

def test_same_text_later_year_is_reconfirmed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will expand capacity at the manufacturing plant by FY25."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise)])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise)])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert result["commitments"]["commitment_count"] == 1
    commitment = result["commitments"]["commitments"][0]
    assert commitment["status"] == "Reconfirmed"


# ── 6. Validation passes for cross-year reconfirmation ───────────────────────

def test_validation_passes_for_cross_year_reconfirmation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will deploy a new distribution platform across all regions."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise)])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise)])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert result["validation"]["status"] == "pass", result["validation"].get("issues")
    assert not any(i["code"] == "identical_commitments_across_years" for i in result["validation"]["issues"])


# ── 7. Reconfirmation appears in evidence_updates ────────────────────────────

def test_reconfirmation_appears_in_evidence_updates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will open five new outlets in the northern region by FY25."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise)])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise)])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    evidence_updates = commitment.get("progression", {}).get("evidence_updates", [])
    reconfirm_events = [ev for ev in evidence_updates if ev.get("event_type") == "reconfirmation"]
    assert reconfirm_events, "Expected at least one reconfirmation event in evidence_updates"


# ── 8. Reconfirmation event carries the later year's period ──────────────────

def test_reconfirmation_event_has_correct_period(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will build three additional manufacturing facilities by FY26."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise, "Capacity")])
    _write_year(tmp_path, "co", "fy25", items=[_item(promise, "Capacity")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    evidence_updates = commitment.get("progression", {}).get("evidence_updates", [])
    reconfirm_events = [ev for ev in evidence_updates if ev.get("event_type") == "reconfirmation"]
    assert any(ev.get("period") == "fy25" for ev in reconfirm_events)


# ── 9. Lifecycle source_year matches announcement year ───────────────────────

def test_lifecycle_source_year_is_announcement_period(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year(tmp_path, "co", "fy22", items=[_item("We will expand into five new markets by FY24.")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    lifecycle = commitment.get("lifecycle", {})
    assert lifecycle.get("source_year") == "fy22"


# ── 10. Lifecycle check_years excludes announcement year ─────────────────────

def test_lifecycle_check_years_excludes_announcement_year(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We intend to launch the next-generation product line by FY25."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise, "Product")])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise, "Product")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    lifecycle = commitment.get("lifecycle", {})
    assert "fy23" not in lifecycle.get("check_years", [])
    assert "fy24" in lifecycle.get("check_years", [])


# ── 11. last_checked_year is the latest period ───────────────────────────────

def test_lifecycle_last_checked_year_is_latest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will commission a second data centre by FY26."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise)])
    _write_year(tmp_path, "co", "fy25", items=[_item(promise)])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    lifecycle = commitment.get("lifecycle", {})
    assert lifecycle.get("last_checked_year") == "fy25"


# ── 12. Lifecycle events list starts with announcement ───────────────────────

def test_lifecycle_events_start_with_announcement(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year(tmp_path, "co", "fy23", items=[_item("We plan to acquire a controlling stake in the target company.")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    lifecycle_events = commitment.get("lifecycle", {}).get("lifecycle_events", [])
    assert lifecycle_events, "lifecycle_events must not be empty"
    assert lifecycle_events[0].get("event_type") == "announcement"


# ── 13. Multiple reconfirmations across years ─────────────────────────────────

def test_multiple_reconfirmations_across_years(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will increase our market share in the core segment by FY26."
    for yr in ("fy22", "fy23", "fy24"):
        _write_year(tmp_path, "co", yr, items=[_item(promise, "Growth")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert result["commitments"]["commitment_count"] == 1
    commitment = result["commitments"]["commitments"][0]
    assert commitment["status"] == "Reconfirmed"
    lifecycle = commitment.get("lifecycle", {})
    assert "fy23" in lifecycle.get("check_years", [])
    assert "fy24" in lifecycle.get("check_years", [])


# ── 14. RECONFIRMED ≠ ACTION_STARTED ─────────────────────────────────────────

def test_reconfirmed_status_not_in_progress(tmp_path, monkeypatch):
    """Repeating the same text in a later year must not produce 'In Progress'."""
    monkeypatch.chdir(tmp_path)
    promise = "We will reduce fixed costs by 10% by FY25."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise, "Financial Target")])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise, "Financial Target")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    assert commitment["status"] != "In Progress"
    assert commitment["status"] == "Reconfirmed"


# ── 15. Decisive evidence overrides reconfirmation → In Progress ─────────────

def test_progress_evidence_overrides_reconfirmation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will expand the distribution network to 20 new regions by FY25."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise)])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise)])
    # fy25 has progress evidence — different text, same theme
    _write_year(tmp_path, "co", "fy25", items=[
        _item("Expanding the distribution network; rollout is in progress.", "Capacity")
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitments = result["commitments"]["commitments"]
    # Find the commitment about distribution network
    dist = next((c for c in commitments if "distribution" in c["original_statement"].lower()), None)
    assert dist is not None
    assert dist["status"] == "In Progress"


# ── 16. Delivery evidence after reconfirmation → Delivered ───────────────────

def test_delivery_after_reconfirmation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will launch the new logistics platform by FY25."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise, "Technology")])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise, "Technology")])
    _write_year(tmp_path, "co", "fy25", items=[
        _item("The new logistics platform was successfully launched and is now operational.", "Technology")
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitments = result["commitments"]["commitments"]
    logistics = next((c for c in commitments if "logistics" in c["original_statement"].lower()), None)
    assert logistics is not None
    assert logistics["status"] == "Delivered"


# ── 17. Abandonment after reconfirmation → Abandoned ────────────────────────

def test_abandonment_after_reconfirmation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We plan to enter the southern market by FY25."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise, "Expansion")])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise, "Expansion")])
    _write_year(tmp_path, "co", "fy25", items=[
        _item("We have abandoned our plans to enter the southern market.", "Expansion")
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitments = result["commitments"]["commitments"]
    southern = next((c for c in commitments if "southern" in c["original_statement"].lower()), None)
    assert southern is not None
    assert southern["status"] == "Abandoned"


# ── 18. Delay after reconfirmation → Delayed ────────────────────────────────

def test_delay_after_reconfirmation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will complete the plant upgrade by FY25."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise, "Capacity")])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise, "Capacity")])
    _write_year(tmp_path, "co", "fy25", items=[
        _item("The plant upgrade has been delayed due to supply chain disruptions.", "Capacity")
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitments = result["commitments"]["commitments"]
    plant = next((c for c in commitments if "plant upgrade" in c["original_statement"].lower()), None)
    assert plant is not None
    assert plant["status"] == "Delayed"


# ── 19. No extra commitments from reconfirmation-only years ──────────────────

def test_reconfirmation_does_not_inflate_commitment_count(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will grow our revenue by 15% annually over the next three years."
    for yr in ("fy22", "fy23", "fy24", "fy25"):
        _write_year(tmp_path, "co", yr, items=[_item(promise, "Growth")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert result["commitments"]["commitment_count"] == 1


# ── 20. Reconfirmed delivery_assessment mentions reconfirmation ───────────────

def test_reconfirmed_delivery_assessment_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will open 10 new stores by FY25."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise, "Expansion")])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise, "Expansion")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    assessment = commitment.get("delivery_assessment", "")
    assert "reconfirm" in assessment.lower() or "no execution" in assessment.lower()


# ── 21. Evidence_updates empty when single evidence with no later data ────────

def test_evidence_updates_empty_for_single_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year(tmp_path, "co", "fy24", items=[_item("We plan to launch two new product SKUs next quarter.", "Product")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    evidence_updates = commitment.get("progression", {}).get("evidence_updates", [])
    assert evidence_updates == []


# ── 22. Commitment_count unchanged when only reconfirmations added ────────────

def test_commitment_count_stable_with_reconfirmations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year(tmp_path, "co", "fy23", items=[
        _item("We will deploy new automation equipment at all plants by FY25.", "Technology"),
        _item("We plan to acquire a strategic partner in the logistics sector.", "Acquisition"),
    ])
    # fy24: only one of the commitments is reconfirmed
    _write_year(tmp_path, "co", "fy24", items=[
        _item("We will deploy new automation equipment at all plants by FY25.", "Technology"),
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert result["commitments"]["commitment_count"] == 2


# ── 23. Status counts include Reconfirmed ────────────────────────────────────

def test_status_counts_include_reconfirmed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will increase production capacity by 500 units by FY25."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise, "Capacity")])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise, "Capacity")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    status_counts = result["commitments"].get("status_counts", {})
    assert "Reconfirmed" in status_counts
    assert status_counts["Reconfirmed"] == 1


# ── 24. Reconfirmation across three years ────────────────────────────────────

def test_reconfirmation_three_years_still_one_commitment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will enter the western European market by FY26."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise, "Expansion")])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise, "Expansion")])
    _write_year(tmp_path, "co", "fy25", items=[_item(promise, "Expansion")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    assert result["commitments"]["commitment_count"] == 1
    commitment = result["commitments"]["commitments"][0]
    assert commitment["status"] == "Reconfirmed"
    lifecycle = commitment.get("lifecycle", {})
    assert set(lifecycle.get("check_years", [])) == {"fy24", "fy25"}


# ── 25. Lifecycle events list is non-empty ───────────────────────────────────

def test_lifecycle_events_non_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_year(tmp_path, "co", "fy23", items=[_item("We plan to invest in 50 new retail outlets by FY25.", "Expansion")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    lifecycle = commitment.get("lifecycle", {})
    assert lifecycle.get("lifecycle_events"), "lifecycle_events must be non-empty"


# ── 26. Reconfirmation lifecycle_event has correct period ────────────────────

def test_lifecycle_event_has_reconfirmation_period(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will reduce fixed costs by 8% by FY25."
    _write_year(tmp_path, "co", "fy23", items=[_item(promise, "Financial Target")])
    _write_year(tmp_path, "co", "fy24", items=[_item(promise, "Financial Target")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    lifecycle_events = commitment.get("lifecycle", {}).get("lifecycle_events", [])
    reconfirm_events = [ev for ev in lifecycle_events if ev.get("event_type") == "reconfirmation"]
    assert reconfirm_events
    assert any(ev.get("period") == "fy24" for ev in reconfirm_events)


# ── 27. Announcement period is earlier year when two years present ───────────

def test_announcement_period_is_earliest_year(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise = "We will build a new headquarters facility by FY27."
    _write_year(tmp_path, "co", "fy24", items=[_item(promise, "Capex")])
    _write_year(tmp_path, "co", "fy25", items=[_item(promise, "Capex")])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitment = result["commitments"]["commitments"][0]
    assert commitment["announcement_period"] == "fy24"
    assert commitment.get("lifecycle", {}).get("source_year") == "fy24"


# ── 28. Mixed: some commitments reconfirmed, others able to verify ───────────

def test_mixed_portfolio_reconfirmed_and_delivered(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    promise_a = "We will deploy automation at all manufacturing plants by FY25."
    promise_b = "We will launch the new customer portal by FY25."
    _write_year(tmp_path, "co", "fy23", items=[
        _item(promise_a, "Technology"),
        _item(promise_b, "Technology"),
    ])
    _write_year(tmp_path, "co", "fy24", items=[
        _item(promise_a, "Technology"),  # reconfirmation of A
        _item("The new customer portal was launched and is now live.", "Technology"),  # delivery of B
    ])
    ManagementCommitmentsBuilder(company="co").build()
    result = _load(tmp_path, "co")
    commitments = result["commitments"]["commitments"]
    assert result["commitments"]["commitment_count"] == 2
    statuses = {c["status"] for c in commitments}
    assert "Reconfirmed" in statuses
    assert "Delivered" in statuses
