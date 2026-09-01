"""
Investor Acceptance Harness Tests
==================================

Validates that the harness itself works correctly — source tracking, semantic
checks, defect detection, and the complete per-question trace. These tests run
against sun_pharma and assert structural properties of harness output, not
the correctness of Prometheus answers (that is the harness's job).

Run with: pytest tests/intelligence/test_investor_acceptance_harness.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines.run_investor_acceptance import (
    EXPECTED_OWNER_MAP,
    GOLD_SOURCE_KEYS,
    QUESTION_SETS,
    TrackedBundle,
    _SourcesProxy,
    _check_decision_useful,
    _check_economically_relevant,
    _check_evidence_backed,
    _check_internally_consistent,
    _check_longitudinal,
    _check_non_generic,
    _check_specific,
    _check_uncertainty_aware,
    _classify_evidence_links,
    _detect_defects,
    _source_meta,
    _summarize_link_integrity,
    _text_of,
    run_acceptance,
    trace_question,
)
from intelligence.ask_intrinsiciq.loader import load_company_memory_sources


# ─── Fixtures ─────────────────────────────────────────────────────────────────

COMPANY = "sun_pharma"
COMPANY_ROOT = ROOT / "companies" / COMPANY


@pytest.fixture(scope="session")
def source_bundle() -> dict[str, Any]:
    return load_company_memory_sources(COMPANY)


@pytest.fixture(scope="session")
def tracked_bundle(source_bundle: dict[str, Any]) -> TrackedBundle:
    return TrackedBundle(source_bundle)


@pytest.fixture(scope="session")
def acceptance_summary(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    out_dir = tmp_path_factory.mktemp("harness_out")
    return run_acceptance(COMPANY, QUESTION_SETS["recovery_baseline"], out_dir)


# ─── H1: TrackedBundle intercepts source access ────────────────────────────────

class TestTrackedBundle:
    def test_accessing_sources_is_logged(self, source_bundle: dict[str, Any]) -> None:
        """H1: Accessing a source via .get('sources').get(key) records the key."""
        tracked = TrackedBundle(source_bundle)
        proxy = tracked.get("sources")
        proxy.get("gold_promise_tracker")
        assert "gold_promise_tracker" in tracked.access_log

    def test_accessing_missing_source_not_logged(self, source_bundle: dict[str, Any]) -> None:
        """H1b: Accessing a source that is missing from inner dict is NOT logged."""
        tracked = TrackedBundle(source_bundle)
        proxy = tracked.get("sources")
        proxy.get("__nonexistent_source__")
        assert "__nonexistent_source__" not in tracked.access_log

    def test_access_order_preserved(self, source_bundle: dict[str, Any]) -> None:
        """H1c: Sources are logged in access order, duplicates deduplicated."""
        tracked = TrackedBundle(source_bundle)
        proxy = tracked.get("sources")
        proxy.get("gold_promise_tracker")
        proxy.get("management_commitments")
        proxy.get("gold_promise_tracker")  # second access
        log = tracked.access_log
        # First occurrence should be gold, second management_commitments, no duplicate gold
        assert log[0] == "gold_promise_tracker"
        assert "management_commitments" in log
        assert log.count("gold_promise_tracker") == 1  # deduplicated

    def test_non_sources_key_passes_through(self, source_bundle: dict[str, Any]) -> None:
        """H1d: Keys other than 'sources' are not intercepted."""
        tracked = TrackedBundle(source_bundle)
        assert tracked.get("company_slug") == COMPANY

    def test_sources_proxy_contains(self, source_bundle: dict[str, Any]) -> None:
        """H1e: 'in' operator works on proxy for existing source keys."""
        tracked = TrackedBundle(source_bundle)
        proxy = tracked.get("sources")
        assert "gold_promise_tracker" in proxy


# ─── H2: Source registry completeness ─────────────────────────────────────────

class TestSourceRegistry:
    def test_gold_keys_recognized(self) -> None:
        """H2: All Gold keys are in the GOLD_SOURCE_KEYS set."""
        expected = {
            "gold_promise_tracker", "gold_credibility", "gold_capital_allocation",
            "gold_strategy_evolution", "gold_risk_evolution",
        }
        assert expected.issubset(GOLD_SOURCE_KEYS)

    def test_source_bundle_loads_minimum_sources(self, source_bundle: dict[str, Any]) -> None:
        """H2b: sun_pharma source bundle loads at least 30 of 44 sources."""
        found = source_bundle.get("source_files_found") or []
        assert len(found) >= 30, f"Only {len(found)} sources loaded for {COMPANY}"

    def test_gold_credibility_loaded(self, source_bundle: dict[str, Any]) -> None:
        """H2c: gold_credibility is present and loaded for sun_pharma."""
        sources = source_bundle.get("sources") or {}
        gold = sources.get("gold_credibility") or {}
        assert gold.get("status") == "loaded", f"gold_credibility status={gold.get('status')!r}"

    def test_per_share_compounding_analysis_loaded(self, source_bundle: dict[str, Any]) -> None:
        """H2d: per_share_compounding_analysis is loaded with analysis records."""
        sources = source_bundle.get("sources") or {}
        psa = (sources.get("per_share_compounding_analysis") or {}).get("payload") or {}
        records = psa.get("analysis") or []
        assert len(records) >= 5, f"Expected >=5 per-share records, got {len(records)}"


# ─── H3: Semantic checks are correct ──────────────────────────────────────────

class TestSemanticChecks:
    def _make_answer(self, **kw: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "simple_answer": "",
            "key_points": [],
            "detailed_explanation": "",
            "answer_status": "supported",
            "evidence_summary": {"status": "direct"},
            "uncertainty_note": {},
        }
        base.update(kw)
        return base

    def test_specific_passes_with_numeric(self) -> None:
        """H3a: _check_specific passes when answer contains a numeric metric."""
        ans = self._make_answer(simple_answer="Revenue grew to ₹47,000 crore in FY25")
        result, _ = _check_specific(ans)
        assert result == "PASS"

    def test_specific_fails_with_generic_text(self) -> None:
        """H3b: _check_specific fails when answer has no numeric/entity content."""
        ans = self._make_answer(simple_answer="The company operates in the pharmaceutical industry.")
        result, _ = _check_specific(ans)
        assert result == "FAIL"

    def test_longitudinal_passes_with_two_fiscal_years(self) -> None:
        """H3c: _check_longitudinal passes when two FY references present in a multi-year context."""
        ans = self._make_answer(simple_answer="EPS improved from FY22 to FY25 significantly.")
        result, _ = _check_longitudinal(ans, {"per_share_series_length": 7})
        assert result == "PASS"

    def test_longitudinal_fails_with_series_but_single_year(self) -> None:
        """H3d: _check_longitudinal fails when series is >= 5 but only one FY mentioned."""
        ans = self._make_answer(simple_answer="In FY25, EPS was ₹38.")
        result, _ = _check_longitudinal(ans, {"per_share_series_length": 7})
        assert result == "FAIL"

    def test_evidence_backed_passes_with_direct_evidence_and_source(self) -> None:
        """H3e: _check_evidence_backed passes when evidence=direct and sources accessed."""
        ans = self._make_answer(evidence_summary={"status": "direct"})
        result, _ = _check_evidence_backed(ans, ["gold_promise_tracker", "management_commitments"])
        assert result == "PASS"

    def test_evidence_backed_fails_with_missing_evidence(self) -> None:
        """H3f: _check_evidence_backed fails when evidence_status=missing."""
        ans = self._make_answer(evidence_summary={"status": "missing"})
        result, _ = _check_evidence_backed(ans, [])
        assert result == "FAIL"

    def test_non_generic_fails_with_template_leak(self) -> None:
        """H3g: _check_non_generic fails when key_points contain template artifacts."""
        ans = self._make_answer(
            key_points=["Investment lens implication: improve upstream progression for better results"]
        )
        result, _ = _check_non_generic(ans)
        assert result == "FAIL"

    def test_uncertainty_aware_fails_when_partial_without_note(self) -> None:
        """H3h: _check_uncertainty_aware fails if evidence is partial but no uncertainty_note."""
        ans = self._make_answer(
            answer_status="partially_supported",
            evidence_summary={"status": "partial"},
            uncertainty_note={},
        )
        result, _ = _check_uncertainty_aware(ans)
        assert result == "FAIL"

    def test_internally_consistent_fails_on_contradiction(self) -> None:
        """H3i: _check_internally_consistent fails when not_supported + direct evidence."""
        ans = self._make_answer(
            answer_status="not_supported",
            evidence_summary={"status": "direct"},
        )
        result, _ = _check_internally_consistent(ans)
        assert result == "FAIL"


# ─── H4: Defect detection ─────────────────────────────────────────────────────

class TestDefectDetection:
    def _empty_source_bundle_meta(self) -> dict[str, Any]:
        return {"gold_credibility_mtime": ""}

    def _base_answer(self) -> dict[str, Any]:
        return {
            "answer_status": "supported",
            "evidence_summary": {"status": "direct"},
            "key_points": [],
            "simple_answer": "Revenue grew.",
            "detailed_explanation": "",
        }

    def test_path_divergence_when_gold_expected_but_not_accessed(self) -> None:
        """H4a: PATH_DIVERGENCE is flagged when Gold is expected but no Gold accessed."""
        expected = EXPECTED_OWNER_MAP["what-has-management-promised"]
        ans = self._base_answer()
        defects = _detect_defects(
            "what-has-management-promised", ans,
            sources_accessed=["management_commitments"],  # no Gold
            source_bundle_meta=self._empty_source_bundle_meta(),
            saved_card=None,
            expected_owner=expected,
            source_context={},
        )
        assert "PATH_DIVERGENCE" in defects

    def test_stale_artifact_when_card_predates_gold(self) -> None:
        """H4b: STALE_ARTIFACT is flagged when answer card is older than Gold artifact."""
        ans = self._base_answer()
        defects = _detect_defects(
            "did-past-claims-come-true", ans,
            sources_accessed=["gold_credibility"],
            source_bundle_meta={"gold_credibility_mtime": "2026-08-31T09:16:22Z"},
            saved_card={"generated_at": "2026-08-31T06:07:03+00:00", "answer_status": "not_supported"},
            expected_owner=EXPECTED_OWNER_MAP["did-past-claims-come-true"],
            source_context={},
        )
        assert "STALE_ARTIFACT" in defects

    def test_bad_synthesis_on_snapshot_with_long_series(self) -> None:
        """H4c: BAD_SYNTHESIS is flagged when multi-year series ignored."""
        ans = self._base_answer()
        ans["key_points"] = ["This is a current-year snapshot only; multi-year data unavailable."]
        ans["simple_answer"] = "Snapshot of FY25."
        expected = EXPECTED_OWNER_MAP["are-per-share-economics-improving"]
        defects = _detect_defects(
            "are-per-share-economics-improving", ans,
            sources_accessed=["per_share_compounding_analysis"],
            source_bundle_meta=self._empty_source_bundle_meta(),
            saved_card=None,
            expected_owner=expected,
            source_context={"per_share_series_length": 7},
        )
        assert "BAD_SYNTHESIS" in defects

    def test_bad_rendering_on_template_leakage(self) -> None:
        """H4d: BAD_RENDERING is flagged when key_points contain template text."""
        ans = self._base_answer()
        ans["key_points"] = ["Investment lens implication: regenerate the progression"]
        defects = _detect_defects(
            "what-projects-are-underway", ans,
            sources_accessed=["projects_registry"],
            source_bundle_meta=self._empty_source_bundle_meta(),
            saved_card=None,
            expected_owner=EXPECTED_OWNER_MAP.get("what-projects-are-underway"),
            source_context={"per_share_series_length": 0},
        )
        assert "BAD_RENDERING" in defects

    def test_no_spurious_defects_on_clean_answer(self) -> None:
        """H4e: No defects flagged for a well-routed, current answer with Gold."""
        ans = self._base_answer()
        ans["key_points"] = ["13 promises tracked. 1 partially achieved. MODERATE_WEIGHT guidance."]
        expected = EXPECTED_OWNER_MAP["did-past-claims-come-true"]
        defects = _detect_defects(
            "did-past-claims-come-true", ans,
            sources_accessed=["gold_credibility", "gold_promise_tracker"],
            source_bundle_meta={"gold_credibility_mtime": "2026-08-30T00:00:00Z"},
            saved_card={"generated_at": "2026-08-31T06:07:03+00:00", "answer_status": "partially_supported"},
            expected_owner=expected,
            source_context={},
        )
        # Card newer than Gold, correct routing — no defects
        assert "PATH_DIVERGENCE" not in defects
        assert "STALE_ARTIFACT" not in defects


# ─── H5: Evidence link classification ─────────────────────────────────────────

class TestEvidenceLinks:
    def test_toansa_2014_classified_as_unrelated(self) -> None:
        """H5a: 2014-era project key_point in projects question is UNRELATED."""
        answer = {"key_points": ["2014 Toansa USFDA prohibition remains active"]}
        links = _classify_evidence_links("what-projects-are-underway", answer, [], {})
        assert any(l["classification"] == "UNRELATED" for l in links)

    def test_template_text_classified_as_unrelated(self) -> None:
        """H5b: Template/builder artifacts are UNRELATED."""
        answer = {"key_points": ["Improve upstream progression for better investor clarity"]}
        links = _classify_evidence_links("what-has-management-promised", answer, [], {})
        assert any(l["classification"] == "UNRELATED" for l in links)

    def test_numeric_claim_with_financial_source_is_supported(self) -> None:
        """H5c: Numeric claim with financial source accessed is SUPPORTED."""
        answer = {"key_points": ["EPS was ₹38.50 in FY25"]}
        links = _classify_evidence_links(
            "are-per-share-economics-improving", answer,
            ["per_share_compounding_analysis"], {}
        )
        assert any(l["classification"] == "SUPPORTED" for l in links)

    def test_link_integrity_summary_is_non_empty(self) -> None:
        """H5d: Summary of link classifications is a non-empty string."""
        links = [
            {"classification": "SUPPORTED"}, {"classification": "UNRELATED"}
        ]
        summary = _summarize_link_integrity(links)
        assert isinstance(summary, str) and len(summary) > 0


# ─── H6: Full trace structure ──────────────────────────────────────────────────

class TestFullTrace:
    @pytest.mark.skipif(not COMPANY_ROOT.exists(), reason="sun_pharma company directory not found")
    def test_trace_has_required_top_level_keys(self, source_bundle: dict[str, Any]) -> None:
        """H6a: trace_question returns a dict with all required top-level keys."""
        trace = trace_question(
            "did-past-claims-come-true",
            company_internal_key=COMPANY,
            company_public_slug="sun-pharma",
            source_bundle=source_bundle,
            company_root=COMPANY_ROOT,
            run_timestamp="2026-09-01T00:00:00Z",
        )
        required_keys = {
            "question_id", "routing_trace", "artifact_trace",
            "evidence_trace", "answer_trace", "ui_trace",
            "semantic_checks", "verdict", "defect_classes", "explanation",
        }
        assert required_keys.issubset(set(trace.keys())), (
            f"Missing keys: {required_keys - set(trace.keys())}"
        )

    @pytest.mark.skipif(not COMPANY_ROOT.exists(), reason="sun_pharma company directory not found")
    def test_trace_routing_includes_expected_and_actual_source(self, source_bundle: dict[str, Any]) -> None:
        """H6b: routing_trace distinguishes expected_primary from actual_primary."""
        trace = trace_question(
            "what-has-management-promised",
            company_internal_key=COMPANY,
            company_public_slug="sun-pharma",
            source_bundle=source_bundle,
            company_root=COMPANY_ROOT,
            run_timestamp="2026-09-01T00:00:00Z",
        )
        rt = trace["routing_trace"]
        assert "expected_primary_source" in rt
        assert "actual_primary_source_used" in rt
        # The expected and actual may differ — that is the finding
        assert isinstance(rt["expected_primary_source"], str)

    @pytest.mark.skipif(not COMPANY_ROOT.exists(), reason="sun_pharma company directory not found")
    def test_trace_semantic_checks_has_eight_entries(self, source_bundle: dict[str, Any]) -> None:
        """H6c: semantic_checks has exactly 8 checks."""
        trace = trace_question(
            "are-per-share-economics-improving",
            company_internal_key=COMPANY,
            company_public_slug="sun-pharma",
            source_bundle=source_bundle,
            company_root=COMPANY_ROOT,
            run_timestamp="2026-09-01T00:00:00Z",
        )
        checks = trace["semantic_checks"]
        assert len(checks) == 8, f"Expected 8 semantic checks, got {len(checks)}"

    @pytest.mark.skipif(not COMPANY_ROOT.exists(), reason="sun_pharma company directory not found")
    def test_verdict_is_accepted_or_rejected(self, source_bundle: dict[str, Any]) -> None:
        """H6d: verdict is always 'ACCEPTED' or 'REJECTED'."""
        for qid in QUESTION_SETS["recovery_baseline"]:
            trace = trace_question(
                qid,
                company_internal_key=COMPANY,
                company_public_slug="sun-pharma",
                source_bundle=source_bundle,
                company_root=COMPANY_ROOT,
                run_timestamp="2026-09-01T00:00:00Z",
            )
            assert trace["verdict"] in ("ACCEPTED", "REJECTED"), (
                f"{qid}: unexpected verdict {trace['verdict']!r}"
            )


# ─── H7: Acceptance summary ────────────────────────────────────────────────────

class TestAcceptanceSummary:
    @pytest.mark.skipif(not COMPANY_ROOT.exists(), reason="sun_pharma company directory not found")
    def test_summary_contains_all_questions(self, acceptance_summary: dict[str, Any]) -> None:
        """H7a: summary.per_question has one entry per question in the suite."""
        per_q = acceptance_summary.get("per_question") or []
        assert len(per_q) == len(QUESTION_SETS["recovery_baseline"])

    @pytest.mark.skipif(not COMPANY_ROOT.exists(), reason="sun_pharma company directory not found")
    def test_summary_acceptance_rate_is_str(self, acceptance_summary: dict[str, Any]) -> None:
        """H7b: acceptance_rate is formatted as 'N/M'."""
        rate = acceptance_summary.get("acceptance_rate", "")
        assert "/" in rate, f"acceptance_rate has unexpected format: {rate!r}"

    @pytest.mark.skipif(not COMPANY_ROOT.exists(), reason="sun_pharma company directory not found")
    def test_summary_p0_recommendation_present(self, acceptance_summary: dict[str, Any]) -> None:
        """H7c: p0_recommendation includes should_proceed and reason."""
        p0 = acceptance_summary.get("p0_recommendation") or {}
        assert "should_proceed" in p0
        assert "reason" in p0 and isinstance(p0["reason"], str)

    @pytest.mark.skipif(not COMPANY_ROOT.exists(), reason="sun_pharma company directory not found")
    def test_summary_systemic_findings_present(self, acceptance_summary: dict[str, Any]) -> None:
        """H7d: systemic_findings block is present with defect counts."""
        sf = acceptance_summary.get("systemic_findings") or {}
        assert "path_divergence_count" in sf
        assert "stale_artifact_count" in sf
        assert "highest_severity_defect" in sf

    @pytest.mark.skipif(not COMPANY_ROOT.exists(), reason="sun_pharma company directory not found")
    def test_at_least_one_question_rejected(self, acceptance_summary: dict[str, Any]) -> None:
        """H7e: Prometheus baseline has at least one REJECTED question (no false pass)."""
        rejected = acceptance_summary.get("rejected", 0)
        assert rejected >= 1, (
            "Expected at least 1 rejection in the recovery_baseline set. "
            f"Got {rejected} rejections. "
            "If all 5 pass, Prometheus has no known defects — which contradicts the 42/100 audit."
        )

    @pytest.mark.skipif(not COMPANY_ROOT.exists(), reason="sun_pharma company directory not found")
    def test_trace_files_written(self, acceptance_summary: dict[str, Any]) -> None:
        """H7f: All trace files listed in summary actually exist on disk."""
        for fpath in acceptance_summary.get("trace_files") or []:
            assert Path(fpath).exists(), f"Trace file missing: {fpath}"

    @pytest.mark.skipif(not COMPANY_ROOT.exists(), reason="sun_pharma company directory not found")
    def test_trace_files_are_valid_json(self, acceptance_summary: dict[str, Any]) -> None:
        """H7g: All trace files are valid JSON."""
        for fpath in acceptance_summary.get("trace_files") or []:
            path = Path(fpath)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                assert isinstance(data, dict), f"{fpath} is not a JSON object"
            except json.JSONDecodeError as exc:
                pytest.fail(f"{fpath} is not valid JSON: {exc}")


# ─── H8: Question set contracts ───────────────────────────────────────────────

class TestQuestionSetContracts:
    def test_recovery_baseline_has_five_questions(self) -> None:
        """H8a: recovery_baseline question set has exactly 5 questions."""
        assert len(QUESTION_SETS["recovery_baseline"]) == 5

    def test_all_recovery_baseline_questions_have_expected_owner(self) -> None:
        """H8b: Every question in recovery_baseline has an entry in EXPECTED_OWNER_MAP."""
        for qid in QUESTION_SETS["recovery_baseline"]:
            assert qid in EXPECTED_OWNER_MAP, f"{qid!r} missing from EXPECTED_OWNER_MAP"

    def test_expected_owner_map_has_required_fields(self) -> None:
        """H8c: Every EXPECTED_OWNER_MAP entry has expected_primary and gold_expected."""
        for qid, config in EXPECTED_OWNER_MAP.items():
            assert "expected_primary" in config, f"{qid}: missing expected_primary"
            assert "gold_expected" in config, f"{qid}: missing gold_expected"
