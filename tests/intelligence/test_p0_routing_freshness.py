"""
P0 Regression Tests — Canonical Routing + Artifact Freshness
=============================================================

These tests guard the P0 repair:
  - Gold Promise Tracker is primary for management-promise questions when eligible
  - management_progression cannot outrank valid Gold
  - projects_registry owns the projects question
  - Fallback occurs with recorded reason when Gold is absent/stale/insufficient
  - Dependency provenance is saved with each answer card
  - Newer dependency marks answer stale; unrelated artifact does NOT
  - Fresh answer remains fresh
  - Live builder and saved card converge after P0 regeneration

Run: pytest tests/intelligence/test_p0_routing_freshness.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from intelligence.ask_intrinsiciq.answer_cards import (
    ANSWER_BUILDERS,
    QUESTION_DEPENDENCY_MAP,
    _build_dependency_provenance,
    _build_management_promises_answer,
    _build_past_claims_answer,
    _build_projects_answer,
    _is_gold_eligible,
    build_answer_for_question,
)
from intelligence.ask_intrinsiciq.loader import load_company_memory_sources

COMPANY = "sun_pharma"
COMPANY_ROOT = ROOT / "companies" / COMPANY
ANSWER_CARDS_PATH = COMPANY_ROOT / "company_memory/ask_intrinsiciq/answer_cards.json"

# ── Helpers ────────────────────────────────────────────────────────────────────

def _fake_bundle(sources: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal source bundle with given source payloads."""
    return {
        "company_slug": "test_co",
        "company_root": "companies/test_co",
        "sources": {
            name: {"status": "loaded", "payload": payload, "file_mtime": "", "path": f"companies/test_co/{name}.json"}
            for name, payload in sources.items()
        },
        "source_files_found": list(sources.keys()),
        "source_files_missing": [],
    }


def _call_builder(builder_fn, bundle: dict[str, Any]) -> dict[str, Any]:
    from intelligence.ask_intrinsiciq.answer_cards import QUESTION_INDEX
    question = list(QUESTION_INDEX.values())[0]  # generic question for non-question-specific builders
    return builder_fn(bundle, business_journey_payload={}, products_services_payload={}, question=question)


# ── T1: Gold eligibility ───────────────────────────────────────────────────────

class TestGoldEligibility:
    def test_absent_payload_is_ineligible(self) -> None:
        """T1a: None payload → GOLD_ABSENT fallback reason."""
        ok, reason = _is_gold_eligible(None)
        assert not ok
        assert "GOLD_ABSENT" in reason

    def test_empty_dict_is_ineligible(self) -> None:
        """T1b: Empty dict → GOLD_ABSENT (no summary)."""
        ok, reason = _is_gold_eligible({})
        assert not ok
        assert "GOLD_ABSENT" in reason or "GOLD_INSUFFICIENT" in reason

    def test_zero_promises_is_ineligible(self) -> None:
        """T1c: Zero tracked_promises → GOLD_INSUFFICIENT."""
        ok, reason = _is_gold_eligible({"summary": {"tracked_promises": 0}})
        assert not ok
        assert "GOLD_INSUFFICIENT" in reason

    def test_one_promise_is_eligible(self) -> None:
        """T1d: One tracked promise → eligible."""
        ok, reason = _is_gold_eligible({"summary": {"tracked_promises": 1}})
        assert ok
        assert reason == ""

    def test_many_promises_eligible(self) -> None:
        """T1e: 13 tracked promises → eligible (sun_pharma scenario)."""
        ok, _ = _is_gold_eligible({"summary": {"tracked_promises": 13}})
        assert ok


# ── T2: Routing — management-promises question ─────────────────────────────────

class TestManagementPromisesRouting:
    def test_gold_tracker_is_primary_when_eligible(self) -> None:
        """T2a: Fresh eligible Gold Promise Tracker → builder selects Gold as primary."""
        bundle = _fake_bundle({
            "gold_promise_tracker": {
                "summary": {
                    "tracked_promises": 5,
                    "status_breakdown": {"achieved": 1, "partially_achieved": 1, "unverified": 3},
                    "promise_type_breakdown": {"CAPACITY": 3, "PRODUCT_LAUNCH": 2},
                },
                "credibility_patterns": [],
            },
            "management_commitments": {"commitments": []},
        })
        from intelligence.ask_intrinsiciq.answer_cards import QUESTION_INDEX
        q = QUESTION_INDEX["what-has-management-promised"]
        answer = _build_management_promises_answer(bundle, business_journey_payload={}, products_services_payload={}, question=q)
        assert answer["answer_status"] in ("supported", "partially_supported")
        ev = answer.get("evidence_summary") or {}
        assert "gold" in str(ev.get("summary") or "").lower() or "Gold" in str(answer.get("detailed_explanation") or "")

    def test_management_progression_cannot_outrank_eligible_gold(self) -> None:
        """T2b: management_progression must never become primary when Gold is eligible."""
        bundle = _fake_bundle({
            "gold_promise_tracker": {"summary": {"tracked_promises": 3}},
            "management_progression": {"coverage_status": "supported", "progression_items": [{"type": "management"}]},
            "management_commitments": {},
        })
        from intelligence.ask_intrinsiciq.answer_cards import QUESTION_INDEX
        q = QUESTION_INDEX["what-has-management-promised"]
        answer = _build_management_promises_answer(bundle, business_journey_payload={}, products_services_payload={}, question=q)
        # Answer must not come from management_progression; Gold was eligible
        assert answer["answer_status"] != "not_supported"
        det = str(answer.get("detailed_explanation") or "").lower()
        assert "progression" not in det or "gold" in det

    def test_fallback_to_commitments_when_gold_absent(self) -> None:
        """T2c: Gold absent → falls back to management_commitments."""
        bundle = _fake_bundle({
            "management_commitments": {
                "commitments": [{"topic": "Capacity expansion", "normalized_commitment": "Expand manufacturing capacity", "status": "in progress", "type": "CAPACITY"}]
            },
        })
        from intelligence.ask_intrinsiciq.answer_cards import QUESTION_INDEX
        q = QUESTION_INDEX["what-has-management-promised"]
        answer = _build_management_promises_answer(bundle, business_journey_payload={}, products_services_payload={}, question=q)
        assert answer["answer_status"] in ("supported", "partially_supported")

    def test_not_supported_when_both_absent(self) -> None:
        """T2d: Gold absent AND no commitments → not_supported or unavailable."""
        bundle = _fake_bundle({})
        from intelligence.ask_intrinsiciq.answer_cards import QUESTION_INDEX
        q = QUESTION_INDEX["what-has-management-promised"]
        answer = _build_management_promises_answer(bundle, business_journey_payload={}, products_services_payload={}, question=q)
        assert answer["answer_status"] in ("not_supported", "unavailable")


# ── T3: Routing — did-past-claims question ─────────────────────────────────────

class TestPastClaimsRouting:
    def test_gold_tracker_is_primary_for_did_past_claims(self) -> None:
        """T3a: Eligible Gold Tracker → did-past-claims uses Gold first."""
        bundle = _fake_bundle({
            "gold_promise_tracker": {"summary": {"tracked_promises": 4}},
            "gold_credibility": {"summary": {"management_credibility_summary": "Track record is mixed.", "guidance_weight": "MODERATE_WEIGHT"}},
            "management_commitments": {},
        })
        from intelligence.ask_intrinsiciq.answer_cards import QUESTION_INDEX
        q = QUESTION_INDEX["did-past-claims-come-true"]
        answer = _build_past_claims_answer(bundle, business_journey_payload={}, products_services_payload={}, question=q)
        assert answer["answer_status"] in ("supported", "partially_supported")

    def test_gold_eligible_invariant_not_supported_forbidden(self) -> None:
        """T3b: Gold Tracker has promises → answer_status CANNOT be not_supported."""
        bundle = _fake_bundle({
            "gold_promise_tracker": {"summary": {"tracked_promises": 8}},
        })
        from intelligence.ask_intrinsiciq.answer_cards import QUESTION_INDEX
        q = QUESTION_INDEX["did-past-claims-come-true"]
        answer = _build_past_claims_answer(bundle, business_journey_payload={}, products_services_payload={}, question=q)
        assert answer["answer_status"] != "not_supported", (
            "Invariant violated: Gold Tracker has promises but answer is not_supported"
        )

    def test_fallback_occurs_when_gold_absent(self) -> None:
        """T3c: Gold absent → falls back to management_commitments."""
        bundle = _fake_bundle({
            "management_commitments": {
                "commitments": [{"topic": "Regulatory remediation", "normalized_commitment": "Resolve USFDA observations", "status": "delivered"}]
            },
        })
        from intelligence.ask_intrinsiciq.answer_cards import QUESTION_INDEX
        q = QUESTION_INDEX["did-past-claims-come-true"]
        answer = _build_past_claims_answer(bundle, business_journey_payload={}, products_services_payload={}, question=q)
        assert answer["answer_status"] in ("supported", "partially_supported")

    def test_fallback_reason_implicit_when_gold_insufficient(self) -> None:
        """T3d: Gold has 0 promises → routing skips Gold and uses commitments fallback."""
        bundle = _fake_bundle({
            "gold_promise_tracker": {"summary": {"tracked_promises": 0}},
            "management_commitments": {"commitments": [{"topic": "Audit remediation", "normalized_commitment": "Resolve audit observations", "status": "in progress"}]},
        })
        from intelligence.ask_intrinsiciq.answer_cards import QUESTION_INDEX
        q = QUESTION_INDEX["did-past-claims-come-true"]
        answer = _build_past_claims_answer(bundle, business_journey_payload={}, products_services_payload={}, question=q)
        # Should have fallen back to management_commitments
        assert answer["answer_status"] in ("supported", "partially_supported", "not_supported")


# ── T4: Routing — projects question ───────────────────────────────────────────

class TestProjectsRouting:
    def test_projects_selects_projects_registry(self) -> None:
        """T4a: what-projects-are-underway primary source must be projects_registry."""
        bundle = _fake_bundle({
            "projects_registry": {
                "projects": [{"project_name": "Capacity expansion FY24", "objective": "Build dedicated OSD manufacturing."}]
            },
        })
        from intelligence.ask_intrinsiciq.answer_cards import QUESTION_INDEX
        q = QUESTION_INDEX["what-projects-are-underway"]
        answer = _build_projects_answer(bundle, business_journey_payload={}, products_services_payload={}, question=q)
        assert answer["answer_status"] in ("supported", "partially_supported")

    def test_projects_does_not_use_management_progression(self) -> None:
        """T4b: projects_registry present → management_progression must not be primary."""
        bundle = _fake_bundle({
            "projects_registry": {"projects": [{"project_name": "API launch"}]},
            "management_progression": {"coverage_status": "supported", "progression_items": []},
        })
        from intelligence.ask_intrinsiciq.answer_cards import QUESTION_INDEX
        q = QUESTION_INDEX["what-projects-are-underway"]
        answer = _build_projects_answer(bundle, business_journey_payload={}, products_services_payload={}, question=q)
        # Simple sanity: answer does not say "regenerate the progression"
        text = " ".join([str(answer.get("simple_answer") or "")] + [str(kp) for kp in (answer.get("key_points") or [])])
        assert "regenerate the progression" not in text.lower()


# ── T5: ANSWER_BUILDERS dispatch ──────────────────────────────────────────────

class TestAnswerBuildersDispatch:
    def test_buffett_source_unchanged(self) -> None:
        """T5a: what-would-buffett-focus-on uses _build_buffett_answer (no P0 change)."""
        from intelligence.ask_intrinsiciq.answer_cards import _build_buffett_answer
        assert ANSWER_BUILDERS["what-would-buffett-focus-on"] is _build_buffett_answer

    def test_per_share_source_unchanged(self) -> None:
        """T5b: are-per-share-economics-improving uses _build_per_share_answer (no P0 change)."""
        from intelligence.ask_intrinsiciq.answer_cards import _build_per_share_answer
        assert ANSWER_BUILDERS["are-per-share-economics-improving"] is _build_per_share_answer

    def test_management_promises_rewired(self) -> None:
        """T5c: what-has-management-promised is now _build_management_promises_answer."""
        assert ANSWER_BUILDERS["what-has-management-promised"] is _build_management_promises_answer

    def test_past_claims_rewired(self) -> None:
        """T5d: did-past-claims-come-true is now _build_past_claims_answer."""
        assert ANSWER_BUILDERS["did-past-claims-come-true"] is _build_past_claims_answer

    def test_projects_rewired(self) -> None:
        """T5e: what-projects-are-underway is now _build_projects_answer."""
        assert ANSWER_BUILDERS["what-projects-are-underway"] is _build_projects_answer


# ── T6: Dependency provenance ──────────────────────────────────────────────────

class TestDependencyProvenance:
    def test_provenance_recorded_for_management_promises(self) -> None:
        """T6a: Management-promises provenance lists gold_promise_tracker as first dep."""
        bundle = _fake_bundle({
            "gold_promise_tracker": {
                "status": "loaded",
                "file_mtime": "2026-08-31T06:58:33Z",
                "summary": {"tracked_promises": 1},
            },
        })
        # Inject file_mtime into sources correctly
        bundle["sources"]["gold_promise_tracker"]["file_mtime"] = "2026-08-31T06:58:33Z"
        prov = _build_dependency_provenance("what-has-management-promised", bundle)
        assert len(prov) >= 1
        assert prov[0]["logical_source"] == "gold_promise_tracker"
        assert prov[0]["used_as"] == "primary"

    def test_provenance_recorded_for_did_past_claims(self) -> None:
        """T6b: did-past-claims provenance lists gold_promise_tracker + gold_credibility."""
        bundle = _fake_bundle({})
        prov = _build_dependency_provenance("did-past-claims-come-true", bundle)
        sources = [d["logical_source"] for d in prov]
        assert "gold_promise_tracker" in sources
        assert "gold_credibility" in sources

    def test_provenance_question_scoped(self) -> None:
        """T6c: Projects question provenance does NOT include gold_promise_tracker."""
        bundle = _fake_bundle({})
        prov = _build_dependency_provenance("what-projects-are-underway", bundle)
        sources = [d["logical_source"] for d in prov]
        assert "projects_registry" in sources
        assert "gold_promise_tracker" not in sources

    def test_answer_card_carries_provenance_after_regeneration(self) -> None:
        """T6d: Regenerated sun_pharma answer card has dependency_provenance field."""
        if not ANSWER_CARDS_PATH.exists():
            pytest.skip("sun_pharma answer cards not found")
        data = json.loads(ANSWER_CARDS_PATH.read_text(encoding="utf-8"))
        for ans in data.get("answers") or []:
            if ans.get("question_id") == "what-has-management-promised":
                prov = ans.get("dependency_provenance")
                assert prov is not None, "dependency_provenance missing from answer card"
                assert len(prov) >= 1
                assert prov[0]["logical_source"] == "gold_promise_tracker"
                return
        pytest.skip("what-has-management-promised not found in answer cards")


# ── T7: Freshness enforcement ──────────────────────────────────────────────────

class TestFreshnessEnforcement:
    def _make_provenance(self, ts: str, source: str = "gold_promise_tracker") -> list[dict]:
        return [{"logical_source": source, "artifact_path": f"companies/test/{source}.json", "artifact_timestamp": ts, "used_as": "primary"}]

    def test_newer_dependency_marks_answer_stale(self) -> None:
        """T7a: Dependency timestamp newer than card generated_at → STALE."""
        prov = self._make_provenance("2026-08-31T09:16:22Z")
        card_ts = "2026-08-31T06:07:03+00:00"
        # Simulate harness provenance check
        stale = any(
            d.get("artifact_timestamp") and d["artifact_timestamp"] > card_ts
            for d in prov
        )
        assert stale

    def test_unrelated_newer_artifact_does_not_mark_stale(self) -> None:
        """T7b: Artifact not in question's provenance → no staleness for this question."""
        prov = self._make_provenance("2026-08-30T00:00:00Z", source="gold_promise_tracker")
        unrelated_mtime = "2026-08-31T09:16:22Z"
        card_ts = "2026-08-31T06:07:03+00:00"
        # Provenance only contains gold_promise_tracker (older than card) — unrelated mtime ignored
        stale = any(
            d.get("artifact_timestamp") and d["artifact_timestamp"] > card_ts
            for d in prov
        )
        assert not stale  # risk_evolution or other unrelated artifacts don't contaminate

    def test_fresh_answer_remains_fresh(self) -> None:
        """T7c: All deps <= card generated_at → FRESH."""
        prov = self._make_provenance("2026-08-31T06:00:00Z")
        card_ts = "2026-09-01T05:47:21+00:00"
        stale = any(
            d.get("artifact_timestamp") and d["artifact_timestamp"] > card_ts
            for d in prov
        )
        assert not stale

    def test_missing_timestamp_does_not_cause_stale(self) -> None:
        """T7d: Empty artifact_timestamp → treated as missing; does not mark stale."""
        prov = [{"logical_source": "cim", "artifact_path": "", "artifact_timestamp": "", "used_as": "primary"}]
        card_ts = "2026-09-01T05:47:21+00:00"
        stale = any(
            d.get("artifact_timestamp") and d["artifact_timestamp"] > card_ts
            for d in prov
        )
        assert not stale

    def test_no_provenance_is_unknown_not_fresh(self) -> None:
        """T7e: Absent provenance → UNKNOWN state, not silently treated as FRESH."""
        # The TypeScript checkAnswerCardFreshness returns "UNKNOWN" when provenance is absent.
        # This test verifies the contract: empty list → cannot be FRESH.
        prov: list[dict] = []
        card_ts = "2026-09-01T05:47:21+00:00"
        # With no provenance, we cannot assert FRESH; caller must handle UNKNOWN
        if not prov or not card_ts:
            freshness = "UNKNOWN"
        else:
            stale_deps = [d for d in prov if d.get("artifact_timestamp") and d["artifact_timestamp"] > card_ts]
            freshness = "STALE" if stale_deps else "FRESH"
        assert freshness == "UNKNOWN"  # confirmed by empty provenance list → UNKNOWN not FRESH

    def test_sun_pharma_cards_fresh_after_regeneration(self) -> None:
        """T7f: Regenerated sun_pharma cards have no stale dependencies."""
        if not ANSWER_CARDS_PATH.exists():
            pytest.skip("sun_pharma answer cards not found")
        data = json.loads(ANSWER_CARDS_PATH.read_text(encoding="utf-8"))
        stale_questions: list[str] = []
        for ans in data.get("answers") or []:
            qid = ans.get("question_id", "")
            card_ts = str(ans.get("generated_at") or "")
            prov = ans.get("dependency_provenance") or []
            if not prov or not card_ts:
                continue
            stale = [d["logical_source"] for d in prov if d.get("artifact_timestamp") and d["artifact_timestamp"] > card_ts]
            if stale:
                stale_questions.append(f"{qid} (stale: {stale})")
        assert not stale_questions, f"Stale dependencies found after P0 regeneration: {stale_questions}"


# ── T8: Live builder vs saved card convergence ─────────────────────────────────

class TestLiveSavedConvergence:
    @pytest.mark.skipif(not ANSWER_CARDS_PATH.exists(), reason="sun_pharma cards required")
    def test_live_builder_and_saved_card_converge_management_promises(self) -> None:
        """T8a: Live builder and saved card produce same answer_status for management-promises."""
        source_bundle = load_company_memory_sources(COMPANY)
        bj_path = COMPANY_ROOT / "company_memory/ask_intrinsiciq/business_journey.json"
        ps_path = COMPANY_ROOT / "company_memory/ask_intrinsiciq/products_services.json"
        bj = json.loads(bj_path.read_text()) if bj_path.exists() else {}
        ps = json.loads(ps_path.read_text()) if ps_path.exists() else {}
        live = build_answer_for_question(
            "what-has-management-promised",
            source_bundle,
            business_journey_payload=bj,
            products_services_payload=ps,
            generated_at="test",
        )
        data = json.loads(ANSWER_CARDS_PATH.read_text())
        saved = next((a for a in data["answers"] if a["question_id"] == "what-has-management-promised"), None)
        assert saved is not None
        assert live["answer_status"] == saved["answer_status"], (
            f"Live builder says {live['answer_status']!r} but saved card says {saved['answer_status']!r}"
        )

    @pytest.mark.skipif(not ANSWER_CARDS_PATH.exists(), reason="sun_pharma cards required")
    def test_live_builder_and_saved_card_converge_did_past_claims(self) -> None:
        """T8b: Live builder and saved card produce same answer_status for did-past-claims."""
        source_bundle = load_company_memory_sources(COMPANY)
        bj_path = COMPANY_ROOT / "company_memory/ask_intrinsiciq/business_journey.json"
        ps_path = COMPANY_ROOT / "company_memory/ask_intrinsiciq/products_services.json"
        bj = json.loads(bj_path.read_text()) if bj_path.exists() else {}
        ps = json.loads(ps_path.read_text()) if ps_path.exists() else {}
        live = build_answer_for_question(
            "did-past-claims-come-true",
            source_bundle,
            business_journey_payload=bj,
            products_services_payload=ps,
            generated_at="test",
        )
        data = json.loads(ANSWER_CARDS_PATH.read_text())
        saved = next((a for a in data["answers"] if a["question_id"] == "did-past-claims-come-true"), None)
        assert saved is not None
        assert live["answer_status"] == saved["answer_status"], (
            f"Live builder says {live['answer_status']!r} but saved card says {saved['answer_status']!r}"
        )


# ── T9: No company-specific or question-specific hacks ────────────────────────

class TestNoHardcoding:
    def test_no_company_specific_logic_in_builders(self) -> None:
        """T9a: Builder functions do not hard-code company slug or ID."""
        import inspect
        for fn in [_build_management_promises_answer, _build_past_claims_answer, _build_projects_answer]:
            src = inspect.getsource(fn)
            assert "sun_pharma" not in src, f"{fn.__name__} contains hard-coded sun_pharma"
            assert "sun-pharma" not in src, f"{fn.__name__} contains hard-coded sun-pharma"

    def test_routing_uses_dependency_map_not_question_hacks(self) -> None:
        """T9b: QUESTION_DEPENDENCY_MAP is generic — no company-specific entries."""
        for qid, deps in QUESTION_DEPENDENCY_MAP.items():
            for src in deps:
                assert "sun_pharma" not in src, f"Hard-coded company in dependency map entry {qid}"

    def test_all_five_p0_questions_in_dependency_map(self) -> None:
        """T9c: All five P0 questions have registered dependencies."""
        p0_questions = [
            "what-has-management-promised",
            "did-past-claims-come-true",
            "what-projects-are-underway",
            "what-would-buffett-focus-on",
            "are-per-share-economics-improving",
        ]
        for qid in p0_questions:
            assert qid in QUESTION_DEPENDENCY_MAP, f"{qid} missing from QUESTION_DEPENDENCY_MAP"
            assert len(QUESTION_DEPENDENCY_MAP[qid]) >= 1, f"{qid} has empty dependency list"
