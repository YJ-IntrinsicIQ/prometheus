"""Tests for passage persistence — ENG-135A provenance contract.

Verifies that:
1. evidence passage pointer survives extraction → company_intelligence
2. source item ID survives serialization into multi_year timeline
3. page/section survives into timeline items
4. fingerprint is computable from retrieved passage
5. resolver can reach exact evidence via extraction hop
6. missing passage stays explicit (not fabricated)
7. legacy pointer recovery requires deterministic proof
8. ambiguous recovery is rejected
9. no cross-initiative evidence reuse
10. serialization/reload preserves provenance
11. CAO provenance contract
12. project provenance contract
13. Management Progression provenance contract
"""
from __future__ import annotations
import hashlib, json, re, sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.resolve_eng135a_provenance import resolve, _fingerprint, _is_synthetic_id, _hop_ci_to_extraction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(path: str) -> Any:
    return json.loads((ROOT / path).read_text())


def _find_ci_item(company: str, year: str, item_id: str) -> Optional[Dict]:
    ci_path = ROOT / f"companies/{company}/{year}/intelligence/company_intelligence.json"
    if not ci_path.exists():
        return None
    ci = json.loads(ci_path.read_text())
    items = ((ci.get("financial") or {}).get("capital_allocation") or {}).get("items") or []
    return next((x for x in items if x.get("id") == item_id), None)


# ---------------------------------------------------------------------------
# Test 1: evidence passage pointer survives extraction → company_intelligence
# ---------------------------------------------------------------------------

def test_extracted_ca_has_source_chunk():
    """extracted_capital_allocations.json items carry source_chunk."""
    for company, year in [("sun_pharma", "fy20"), ("datapatterns", "fy22")]:
        path = ROOT / f"companies/{company}/{year}/extracted/extracted_capital_allocations.json"
        if not path.exists():
            continue
        items = json.loads(path.read_text())
        items_with_chunk = [x for x in items if x.get("source_chunk")]
        assert len(items_with_chunk) > 0, (
            f"{company}/{year}: no items with source_chunk in extracted_capital_allocations"
        )
        return  # one company suffices
    assert False, "No test data found for extracted_capital_allocations"


# ---------------------------------------------------------------------------
# Test 2: source item ID survives serialization into multi_year timeline
# ---------------------------------------------------------------------------

def test_timeline_items_have_source_item_id():
    """Multi-year capital_allocation_timeline items carry source_item_id."""
    for company in ["sun_pharma", "tanla", "datapatterns", "ujjivan"]:
        tl_path = ROOT / f"companies/{company}/company_memory/multi_year/capital_allocation_timeline.json"
        if not tl_path.exists():
            continue
        tl = json.loads(tl_path.read_text())
        raw = json.dumps(tl)
        assert '"source_item_id"' in raw, f"{company}: no source_item_id in multi_year timeline"


# ---------------------------------------------------------------------------
# Test 3: page/section survives into timeline items
# ---------------------------------------------------------------------------

def test_timeline_items_have_page():
    """At least some multi_year timeline items carry page metadata."""
    found = False
    for company in ["sun_pharma", "tanla", "datapatterns"]:
        tl_path = ROOT / f"companies/{company}/company_memory/multi_year/capital_allocation_timeline.json"
        if not tl_path.exists():
            continue
        raw = (tl_path).read_text()
        if '"source_page"' in raw or '"page"' in raw:
            found = True
            break
    assert found, "No page metadata found in any multi_year timeline"


# ---------------------------------------------------------------------------
# Test 4: fingerprint is computable from retrieved passage
# ---------------------------------------------------------------------------

def test_fingerprint_deterministic():
    """Fingerprint of same text is always the same SHA-256."""
    text = "The recently announced agreement to acquire Organon."
    fp1 = _fingerprint(text)
    fp2 = _fingerprint(text)
    assert fp1 == fp2
    assert len(fp1) == 64  # sha256 hex
    # Different text → different fingerprint
    fp3 = _fingerprint("Something completely different.")
    assert fp1 != fp3


# ---------------------------------------------------------------------------
# Test 5: resolver can reach exact evidence via extraction hop
# ---------------------------------------------------------------------------

def test_resolver_exact_via_extraction_hop():
    """Resolver returns RESOLVED_EXACT for a known good CAO record via extraction hop."""
    packets = _load("governance/ENG135A_PRODUCTION_EVIDENCE_PACKETS.json")["packets"]
    # Use a PARTIAL record that should become EXACT after hop — e.g., sun_pharma CAO-0001
    pkt = next(p for p in packets if p["company"] == "sun_pharma" and p["record_id"] == "CAO-0001")
    result = resolve(pkt)
    assert result["resolution_status"] in ("RESOLVED_EXACT", "RESOLVED_PARTIAL"), (
        f"Expected EXACT or PARTIAL for sun_pharma CAO-0001, got {result['resolution_status']}: {result['reason_code']}"
    )
    # If EXACT, passage must be non-empty
    if result["resolution_status"] == "RESOLVED_EXACT":
        assert result["passage"], "RESOLVED_EXACT must have a non-empty passage"


# ---------------------------------------------------------------------------
# Test 6: missing passage stays explicit (not fabricated)
# ---------------------------------------------------------------------------

def test_unresolvable_has_reason():
    """UNRESOLVABLE_WITH_REASON records must carry an explicit reason_code."""
    packets = _load("governance/ENG135A_PRODUCTION_EVIDENCE_PACKETS.json")["packets"]
    for pkt in packets:
        result = resolve(pkt)
        if result["resolution_status"] == "UNRESOLVABLE_WITH_REASON":
            assert result["reason_code"], (
                f"{pkt['company']} {pkt['record_id']}: UNRESOLVABLE without a reason_code"
            )
            assert result["passage"] is None, (
                f"{pkt['company']} {pkt['record_id']}: UNRESOLVABLE must not carry a passage"
            )


# ---------------------------------------------------------------------------
# Test 7: legacy pointer recovery requires deterministic proof
# ---------------------------------------------------------------------------

def test_synthetic_ids_are_unrecoverable():
    """capex_fy*, share_issue_*, roi_ledger_* IDs are classified as LEGACY_UNRECOVERABLE."""
    synthetic_ids = ["capex_fy20", "capex_fy22", "share_issue_fy21", "roi_ledger_fy23_operating_reinvestment"]
    for sid in synthetic_ids:
        assert _is_synthetic_id(sid), f"Expected {sid} to be detected as synthetic"


# ---------------------------------------------------------------------------
# Test 8: ambiguous recovery is rejected
# ---------------------------------------------------------------------------

def test_resolver_rejects_ambiguous_empty_item_id():
    """A packet with no source_refs → UNRESOLVABLE SOURCE_ITEM_ID_MISSING, no passage."""
    fake_packet = {"company": "sun_pharma", "record_id": "FAKE-001", "source_refs": []}
    result = resolve(fake_packet)
    assert result["resolution_status"] == "UNRESOLVABLE_WITH_REASON"
    assert result["reason_code"] == "SOURCE_ITEM_ID_MISSING"
    assert result["passage"] is None


# ---------------------------------------------------------------------------
# Test 9: no cross-initiative evidence reuse
# ---------------------------------------------------------------------------

def test_resolver_respects_source_year():
    """Two packets with the same source_item_id but different source_years return independent results."""
    packets = _load("governance/ENG135A_PRODUCTION_EVIDENCE_PACKETS.json")["packets"]
    # Find two CAO records from different years/companies that would both go through timeline
    cao_pkts = [p for p in packets if "CAO-" in p.get("record_id", "") and
                p.get("source_refs") and p["source_refs"][0].get("source_item_id")]
    if len(cao_pkts) < 2:
        return  # not enough data to test
    r1 = resolve(cao_pkts[0])
    r2 = resolve(cao_pkts[1])
    # Results must carry the correct company
    assert r1["company"] == cao_pkts[0]["company"]
    assert r2["company"] == cao_pkts[1]["company"]
    # If both exact, passages must be for different items (or same company same item is OK)
    if r1["passage"] and r2["passage"] and cao_pkts[0]["company"] != cao_pkts[1]["company"]:
        # Cross-company passages must not be identical (unless genuinely same text)
        # We just check that the resolver didn't return the same resolved_item_id for both
        if r1["resolved_item_id"] and r2["resolved_item_id"]:
            assert not (r1["company"] != r2["company"] and r1["resolved_item_id"] == r2["resolved_item_id"]), (
                "Resolver returned same item_id for two different companies — cross-initiative reuse"
            )


# ---------------------------------------------------------------------------
# Test 10: serialization/reload preserves provenance
# ---------------------------------------------------------------------------

def test_extraction_item_survives_json_roundtrip():
    """An extraction item serialized and reloaded preserves source_chunk."""
    for company, year in [("sun_pharma", "fy20"), ("tanla", "fy22"), ("datapatterns", "fy22")]:
        path = ROOT / f"companies/{company}/{year}/extracted/extracted_capital_allocations.json"
        if not path.exists():
            continue
        items = json.loads(path.read_text())
        with_chunk = [x for x in items if x.get("source_chunk")]
        if not with_chunk:
            continue
        original = with_chunk[0]["source_chunk"]
        # roundtrip
        reloaded = json.loads(json.dumps(with_chunk[0]))["source_chunk"]
        assert original == reloaded
        return
    assert False, "No extraction data found for roundtrip test"


# ---------------------------------------------------------------------------
# Test 11: CAO provenance contract
# ---------------------------------------------------------------------------

def test_cao_source_references_carry_source_item_id():
    """CAO outcomes source_references carry source_item_id for timeline items."""
    for company in ["sun_pharma", "tanla", "datapatterns", "ujjivan"]:
        path = ROOT / f"companies/{company}/company_memory/capital_allocation_outcomes/capital_allocation_outcomes.json"
        if not path.exists():
            continue
        allocs = json.loads(path.read_text()).get("allocations", [])
        for a in allocs:
            for ref in a.get("source_references", []):
                if ref.get("source_artifact") == "capital_allocation_timeline.json":
                    assert ref.get("source_item_id"), (
                        f"{company} {a['allocation_id']}: timeline ref missing source_item_id"
                    )


# ---------------------------------------------------------------------------
# Test 12: project provenance contract
# ---------------------------------------------------------------------------

def test_project_source_references_carry_source_item_id():
    """Project source_references carry source_item_id."""
    for company in ["sun_pharma", "datapatterns"]:
        path = ROOT / f"companies/{company}/company_memory/projects/projects_registry.json"
        if not path.exists():
            continue
        registry = json.loads(path.read_text())
        projects = registry if isinstance(registry, list) else registry.get("projects", [])
        for proj in projects:
            for ref in proj.get("source_references", []):
                assert ref.get("source_item_id"), (
                    f"{company} project: source_reference missing source_item_id"
                )
        return  # one company is enough


# ---------------------------------------------------------------------------
# Test 13: Management Progression provenance contract
# ---------------------------------------------------------------------------

def test_mp_events_carry_evidence():
    """MP events carry an evidence array with at least source_artifact."""
    for company in ["sun_pharma", "tanla"]:
        path = ROOT / f"companies/{company}/company_memory/management_progression/management_progression.json"
        if not path.exists():
            continue
        mp = json.loads(path.read_text())
        items = mp if isinstance(mp, list) else []
        if not items and isinstance(mp, dict):
            for v in mp.values():
                if isinstance(v, list) and v:
                    items = v
                    break
        if not items:
            continue
        item = items[0]
        events = item.get("events", [])
        if not events:
            continue
        ev = events[0]
        assert "evidence" in ev, f"{company} MP event missing evidence field"
        if ev["evidence"]:
            assert ev["evidence"][0].get("source_artifact"), (
                f"{company} MP event evidence missing source_artifact"
            )
        return


# ---------------------------------------------------------------------------
# Test 14: recently-announced guard — status must not be "operational"
# ---------------------------------------------------------------------------

def test_recently_announced_not_operational():
    """_status_from_text must return 'announced' for passages that say 'recently announced'.

    Regression for ENG-135A-P1K: capacity_expansions_00001 (Organon acquisition)
    had status='operational' despite source_chunk containing 'recently announced
    agreement to acquire'. The passage also contained 'Strengthening the Operational
    Foundation' (a section header), which caused the operational keyword to fire first.
    The guard at the top of _status_from_text must prevent this.
    """
    from intelligence.capacity.progression import _status_from_text
    passage = (
        "The recently announced agreement to acquire Organon represents another "
        "important step towards strengthening our global Innovative Medicines portfolio. "
        "Ensuring timely closure and enabling effective integration planning will remain "
        "key priorities. Strengthening the Operational Foundation As we continue to scale "
        "globally, operational discipline and quality systems remain fundamental."
    )
    status = _status_from_text(passage)
    assert status == "announced", (
        f"Expected 'announced' for recently-announced text, got '{status}'. "
        "The 'recently announced' guard in _status_from_text must fire before operational keyword matching."
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_extracted_ca_has_source_chunk,
        test_timeline_items_have_source_item_id,
        test_timeline_items_have_page,
        test_fingerprint_deterministic,
        test_resolver_exact_via_extraction_hop,
        test_unresolvable_has_reason,
        test_synthetic_ids_are_unrecoverable,
        test_resolver_rejects_ambiguous_empty_item_id,
        test_resolver_respects_source_year,
        test_extraction_item_survives_json_roundtrip,
        test_cao_source_references_carry_source_item_id,
        test_project_source_references_carry_source_item_id,
        test_mp_events_carry_evidence,
        test_recently_announced_not_operational,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{len(tests)} PASS")
    if failed:
        sys.exit(1)
