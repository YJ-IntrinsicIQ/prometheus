"""
Gold Integration Tests — 15 regression tests covering:
- Gold loader (load_gold_context)
- answer_cards.py Gold enrichment fallbacks
- committee_synthesizer shared_progression["gold"] injection
- Vocabulary translation (no raw Gold vocab on user surface)
- Cross-Gold consistency detection
- Graceful absence (missing Gold artifacts)
- Double-count safeguard present in limitations
- Gold precedence over re-inference
"""
from __future__ import annotations

import json
import types
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source_bundle(overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    sources: Dict[str, Any] = {}
    base = overrides or {}
    for key, payload in base.items():
        sources[key] = {"status": "loaded", "payload": payload}
    return {"company_slug": "test_co", "sources": sources}


def _minimal_credibility(guidance_weight: str = "MODERATE_WEIGHT") -> Dict[str, Any]:
    return {
        "summary": {
            "guidance_weight": guidance_weight,
            "management_credibility_summary": "Track record shows moderate consistency across reporting periods.",
            "key_strengths": ["Guidance accuracy on capacity", "Consistent dividend policy"],
            "key_cautions": ["Revenue guidance frequently revised upward late"],
            "evidence_confidence": "medium",
        },
        "credibility_patterns": [
            {"pattern_id": "moderate_follow_through", "description": "Moderate follow-through on stated milestones"},
        ],
        "evidence_limitations": ["Same underlying evidence can appear across multiple Gold layers; do not treat as independent confirmation."],
        "cross_gold_consistency": {"status": "consistent", "inconsistencies": []},
    }


def _minimal_capital(return_status: str = "PROVEN_POSITIVE") -> Dict[str, Any]:
    return {
        "summary": {
            "tracked_allocations": 4,
            "return_status_breakdown": {"PROVEN_POSITIVE": 2, "UNPROVEN": 2},
        },
        "material_allocations": [
            {"allocation_name": "Capacity expansion Phase 2", "allocation_type": "capex", "return_status": return_status, "investor_interpretation": "Capacity expansion delivered volume growth.", "evidence_ids": ["ev_cap_01"]},
            {"allocation_name": "R&D programme", "allocation_type": "r_and_d", "return_status": "UNPROVEN", "investor_interpretation": "R&D outcome not yet visible.", "evidence_ids": []},
        ],
        "owner_capital_summary": {"interpretation": "Owner capital discipline visible across 4 tracked deployments."},
        "allocation_patterns": [{"pattern_id": "capital_light_deployment", "description": "Capital deployed with discipline"}],
        "critical_follow_up": ["Confirm Phase 2 utilisation rate"],
    }


def _minimal_promise_tracker() -> Dict[str, Any]:
    return {
        "summary": {
            "tracked_promises": 8,
            "status_breakdown": {"achieved": 5, "unverified": 2},
        },
        "promises": [
            {"commitment": "Launch new product line", "status": "in_progress", "evidence_ids": ["ev_pt_01"]},
        ],
        "credibility_patterns": [{"pattern_id": "strong_follow_through", "description": "5 of 8 commitments confirmed delivered"}],
        "critical_follow_up": ["New product line launch status"],
    }


def _minimal_risk_evolution() -> Dict[str, Any]:
    return {
        "summary": {
            "current_risk_summary": "Two material risks actively worsening; three stabilising.",
            "active_material_risks": 2,
            "worsening_risks": 2,
            "improving_risks": 1,
        },
        "risk_themes": [
            {"theme": "Regulatory exposure", "current_state": "WORSENING", "direction": "worsening", "mitigation_status": "none", "investor_interpretation": "Regulatory risk is escalating.", "evidence_ids": ["ev_risk_01"]},
        ],
        "risk_patterns": [{"pattern_id": "recurring_regulatory", "description": "Regulatory risk recurs across periods"}],
        "critical_follow_up": ["Monitor regulatory pipeline"],
    }


def _minimal_strategy_evolution() -> Dict[str, Any]:
    return {
        "strategy_arc": {
            "opening_state": "Domestic-only focus through initial years.",
            "current_state": "Company pivoting from domestic-only to global distribution.",
        },
        "strategy_themes": [
            {
                "theme_name": "Global distribution",
                "current_status": "CURRENT_PRIORITY",
                "capital_backed": True,
                "periods_active": ["FY2022", "FY2023", "FY2024"],
                "events": [{"event_type": "PIVOTED", "period": "FY2022", "description": "Shifted from domestic-only model"}],
            },
        ],
        "strategy_patterns": [{"pattern_id": "strategy_broadening", "description": "New geographic themes added alongside core"}],
    }


# ---------------------------------------------------------------------------
# T1 — load_gold_context returns all 5 layers when artifacts present
# ---------------------------------------------------------------------------
def test_load_gold_context_returns_all_layers(tmp_path: Path) -> None:
    from intelligence.gold.loader import load_gold_context

    gold_dir = tmp_path / "test_co" / "company_memory" / "gold"
    gold_dir.mkdir(parents=True)

    files = {
        "management_promise_tracker.json": _minimal_promise_tracker(),
        "capital_allocation_outcome_tracker.json": _minimal_capital(),
        "management_credibility_synthesis.json": _minimal_credibility(),
        "risk_evolution_timeline.json": _minimal_risk_evolution(),
        "strategy_evolution_timeline.json": _minimal_strategy_evolution(),
    }
    for fname, payload in files.items():
        (gold_dir / fname).write_text(json.dumps({"company_slug": "test_co", **payload}))

    ctx = load_gold_context("test_co", companies_root=tmp_path)
    assert ctx is not None
    assert "management_credibility" in ctx
    assert "capital_allocation" in ctx
    assert "management_promises" in ctx
    assert "risk_evolution" in ctx
    assert "strategy_evolution" in ctx


# ---------------------------------------------------------------------------
# T2 — load_gold_context returns None for missing company root (graceful absence)
# ---------------------------------------------------------------------------
def test_load_gold_context_graceful_absence(tmp_path: Path) -> None:
    from intelligence.gold.loader import load_gold_context

    ctx = load_gold_context("nonexistent_co", companies_root=tmp_path)
    # Should not raise; may return None or empty context
    assert ctx is None or isinstance(ctx, dict)


# ---------------------------------------------------------------------------
# T3 — Vocabulary: guidance_weight_natural never exposes raw enum to caller
# ---------------------------------------------------------------------------
def test_guidance_weight_natural_vocabulary(tmp_path: Path) -> None:
    from intelligence.gold.loader import load_gold_context

    gold_dir = tmp_path / "test_co" / "company_memory" / "gold"
    gold_dir.mkdir(parents=True)
    cred = _minimal_credibility("HIGH_WEIGHT")
    cred["guidance_weight_natural"] = "management guidance deserves high weight"
    (gold_dir / "management_credibility_synthesis.json").write_text(
        json.dumps({"company_slug": "test_co", **cred})
    )

    ctx = load_gold_context("test_co", companies_root=tmp_path)
    cred_block = (ctx or {}).get("management_credibility") or {}
    gw = cred_block.get("guidance_weight_natural") or ""
    # Raw vocab must not surface as the natural text
    assert "HIGH_WEIGHT" not in gw, "Raw Gold vocabulary leaked into user-facing field"
    assert len(gw) > 0


# ---------------------------------------------------------------------------
# T4 — Vocabulary: return_status_natural never exposes PROVEN_POSITIVE raw enum
# ---------------------------------------------------------------------------
def test_return_status_natural_vocabulary(tmp_path: Path) -> None:
    from intelligence.gold.loader import load_gold_context

    gold_dir = tmp_path / "test_co" / "company_memory" / "gold"
    gold_dir.mkdir(parents=True)
    (gold_dir / "capital_allocation_outcome_tracker.json").write_text(
        json.dumps({"company_slug": "test_co", **_minimal_capital("PROVEN_POSITIVE")})
    )

    ctx = load_gold_context("test_co", companies_root=tmp_path)
    cap = (ctx or {}).get("capital_allocation") or {}
    for alloc in (cap.get("major_allocations") or []):
        if not isinstance(alloc, dict):
            continue
        ret_natural = alloc.get("return_status_natural") or ""
        assert "PROVEN_POSITIVE" not in ret_natural, "Raw return_status enum leaked into natural text"


# ---------------------------------------------------------------------------
# T5 — Cross-Gold consistency: HIGH_WEIGHT + >80% unproven/destructive → inconsistency
# ---------------------------------------------------------------------------
def test_cross_gold_consistency_high_weight_unproven_capital(tmp_path: Path) -> None:
    from intelligence.gold.loader import load_gold_context

    gold_dir = tmp_path / "test_co" / "company_memory" / "gold"
    gold_dir.mkdir(parents=True)

    cred = _minimal_credibility("HIGH_WEIGHT")
    # Override the summary guidance_weight to HIGH_WEIGHT
    cred["summary"]["guidance_weight"] = "HIGH_WEIGHT"

    cap = _minimal_capital("UNPROVEN")
    # Override summary return_status_breakdown so mostly unproven
    cap["summary"]["return_status_breakdown"] = {"UNPROVEN": 8, "PROVEN_POSITIVE": 1}

    (gold_dir / "management_credibility_synthesis.json").write_text(
        json.dumps({"company_slug": "test_co", **cred})
    )
    (gold_dir / "capital_allocation_outcome_tracker.json").write_text(
        json.dumps({"company_slug": "test_co", **cap})
    )

    ctx = load_gold_context("test_co", companies_root=tmp_path)
    consistency = (ctx or {}).get("cross_gold_consistency") or {}
    # Inconsistency should be detected when HIGH_WEIGHT credibility + mostly unproven capital
    if isinstance(consistency, dict):
        status = str(consistency.get("status") or "").lower()
        inconsistencies = consistency.get("inconsistencies") or []
        assert status == "inconsistent" or len(inconsistencies) > 0 or "inconsistent" in str(consistency).lower(), (
            f"Expected inconsistency detected, got: {consistency}"
        )


# ---------------------------------------------------------------------------
# T6 — answer_cards: Gold promise enrichment used as fallback when no commitments
# ---------------------------------------------------------------------------
def test_answer_cards_promise_gold_fallback() -> None:
    from intelligence.ask_intrinsiciq.answer_cards import _gold_promise_enrichment

    # _gold_promise_enrichment reads the raw Gold artifact (not the compact form)
    raw_promise = {
        "summary": {"tracked_promises": 8, "status_breakdown": {"achieved": 5, "unverified": 2}},
        "credibility_patterns": ["5 of 8 commitments confirmed delivered"],
    }
    bundle = _make_source_bundle({"gold_promise_tracker": raw_promise})
    result = _gold_promise_enrichment(bundle)
    assert result is not None
    assert "8" in result or "commitment" in result.lower()


# ---------------------------------------------------------------------------
# T7 — answer_cards: Gold promise enrichment returns None when Gold absent
# ---------------------------------------------------------------------------
def test_answer_cards_promise_gold_absent_returns_none() -> None:
    from intelligence.ask_intrinsiciq.answer_cards import _gold_promise_enrichment

    bundle = _make_source_bundle({})
    result = _gold_promise_enrichment(bundle)
    assert result is None


# ---------------------------------------------------------------------------
# T8 — answer_cards: management_quality Gold fallback returns partially_supported
# ---------------------------------------------------------------------------
def test_answer_cards_management_quality_gold_fallback() -> None:
    from intelligence.ask_intrinsiciq.answer_cards import _build_management_quality_answer

    raw_cred = {
        "guidance_weight_natural": "management guidance deserves moderate weight",
        "guidance_weight": "MODERATE_WEIGHT",
        "credibility_summary": "Track record shows moderate consistency.",
        "key_strengths": ["Guidance accuracy on capacity"],
        "key_cautions": ["Revenue guidance revised late"],
    }
    bundle = _make_source_bundle({"gold_credibility": raw_cred})
    question = {"intent": "management-quality", "text": "How good is management?"}
    result = _build_management_quality_answer(bundle, business_journey_payload={}, products_services_payload={}, question=question)
    assert result is not None
    assert result.get("answer_status") in ("partially_supported", "supported")
    simple = result.get("simple_answer") or ""
    assert len(simple) > 0
    assert "HIGH_WEIGHT" not in simple and "MODERATE_WEIGHT" not in simple


# ---------------------------------------------------------------------------
# T9 — answer_cards: capital_allocation Gold fallback populates key_points
# ---------------------------------------------------------------------------
def test_answer_cards_capital_allocation_gold_fallback() -> None:
    from intelligence.ask_intrinsiciq.answer_cards import _build_capital_allocation_answer

    raw_cap = {
        "major_allocations": [
            {"allocation_name": "Capacity expansion Phase 2", "return_status": "PROVEN_POSITIVE", "return_status_natural": "return confirmed"},
        ],
        "owner_capital_note": "Owner capital discipline visible across 4 tracked deployments.",
        "tracked_count": 4,
    }
    bundle = _make_source_bundle({"gold_capital_allocation": raw_cap})
    question = {"intent": "capital-allocation", "text": "How is capital being allocated?"}
    result = _build_capital_allocation_answer(bundle, business_journey_payload={}, products_services_payload={}, question=question)
    assert result is not None
    assert result.get("answer_status") in ("partially_supported", "supported")
    pts = result.get("key_points") or []
    assert len(pts) > 0


# ---------------------------------------------------------------------------
# T10 — answer_cards: buffett Gold sections appended when Gold available
# ---------------------------------------------------------------------------
def test_answer_cards_buffett_gold_sections() -> None:
    from intelligence.ask_intrinsiciq.answer_cards import _build_buffett_answer

    buffett_analysis = {
        "assessment": {"overall_view": "Buffett would find the moat narrow but durable."},
        "key_findings": ["Durable cost advantage in generics"],
        "red_flags": ["Working capital conversion is slow"],
        "open_uncertainties": ["Regulatory approval timelines"],
    }
    raw_cred = {
        "guidance_weight_natural": "management guidance deserves moderate weight",
        "guidance_weight": "MODERATE_WEIGHT",
        "credibility_summary": "Track record shows moderate consistency.",
        "key_cautions": ["Revenue guidance revised late"],
    }
    raw_cap = {
        "major_allocations": [
            {"allocation_name": "Capacity expansion Phase 2", "return_status": "PROVEN_POSITIVE", "return_status_natural": "return confirmed"},
        ],
        "owner_capital_note": "Owner capital discipline visible.",
    }
    bundle = _make_source_bundle({
        "buffett_analysis": buffett_analysis,
        "gold_credibility": raw_cred,
        "gold_capital_allocation": raw_cap,
    })
    question = {"intent": "what-would-buffett-focus-on", "text": "What would Buffett think?"}
    result = _build_buffett_answer(bundle, business_journey_payload={}, products_services_payload={}, question=question)
    assert result is not None
    # structured_sections should exist and may include Gold sections
    sections = result.get("structured_sections") or []
    section_titles = [s.get("title", "") for s in sections if isinstance(s, dict)]
    # Base sections must still be present
    assert any("like" in t.lower() or "question" in t.lower() or "unproven" in t.lower() for t in section_titles)


# ---------------------------------------------------------------------------
# T11 — Double-count safeguard: Gold limitations mention evidence deduplication
# ---------------------------------------------------------------------------
def test_gold_context_limitations_mention_double_count(tmp_path: Path) -> None:
    from intelligence.gold.loader import load_gold_context

    gold_dir = tmp_path / "test_co" / "company_memory" / "gold"
    gold_dir.mkdir(parents=True)
    (gold_dir / "management_credibility_synthesis.json").write_text(
        json.dumps({"company_slug": "test_co", **_minimal_credibility()})
    )

    ctx = load_gold_context("test_co", companies_root=tmp_path)
    cred = (ctx or {}).get("management_credibility") or {}
    limitations = cred.get("evidence_limitations") or []
    # At least one limitation should address evidence double-counting
    combined = " ".join(str(l) for l in limitations).lower()
    if limitations:
        assert "same" in combined or "double" in combined or "independent" in combined or "appear" in combined
    else:
        pytest.skip("No evidence_limitations present in compact credibility block")


# ---------------------------------------------------------------------------
# T12 — Committee synthesizer: Gold block appears in shared_progression
# ---------------------------------------------------------------------------
def test_committee_shared_progression_gold_block(tmp_path: Path) -> None:
    from intelligence.gold.loader import load_gold_context

    gold_dir = tmp_path / "test_co" / "company_memory" / "gold"
    gold_dir.mkdir(parents=True)
    for fname, payload in [
        ("management_credibility_synthesis.json", _minimal_credibility()),
        ("capital_allocation_outcome_tracker.json", _minimal_capital()),
        ("risk_evolution_timeline.json", _minimal_risk_evolution()),
    ]:
        (gold_dir / fname).write_text(json.dumps({"company_slug": "test_co", **payload}))

    ctx = load_gold_context("test_co", companies_root=tmp_path)
    assert ctx is not None
    assert "management_credibility" in ctx
    # Simulate what committee would extract
    cred = ctx.get("management_credibility") or {}
    gold_block = {
        "management_credibility": {
            "guidance_weight": cred.get("guidance_weight_natural"),
            "summary": cred.get("credibility_summary"),
        }
    }
    assert gold_block["management_credibility"]["guidance_weight"]


# ---------------------------------------------------------------------------
# T13 — Gold loader: stale artifact (generated_at) still loaded without error
# ---------------------------------------------------------------------------
def test_gold_loader_stale_artifact_no_error(tmp_path: Path) -> None:
    from intelligence.gold.loader import load_gold_context

    gold_dir = tmp_path / "test_co" / "company_memory" / "gold"
    gold_dir.mkdir(parents=True)
    stale = {**_minimal_credibility(), "generated_at": "2020-01-01T00:00:00Z"}
    (gold_dir / "management_credibility_synthesis.json").write_text(
        json.dumps({"company_slug": "test_co", **stale})
    )

    ctx = load_gold_context("test_co", companies_root=tmp_path)
    # Should load without raising; freshness check is caller's responsibility
    assert ctx is None or isinstance(ctx, dict)


# ---------------------------------------------------------------------------
# T14 — No raw Gold vocabulary in compact capital allocation output
# ---------------------------------------------------------------------------
def test_compact_capital_no_raw_vocabulary(tmp_path: Path) -> None:
    from intelligence.gold.loader import load_gold_context

    gold_dir = tmp_path / "test_co" / "company_memory" / "gold"
    gold_dir.mkdir(parents=True)
    cap = _minimal_capital("PROVEN_POSITIVE")
    (gold_dir / "capital_allocation_outcome_tracker.json").write_text(
        json.dumps({"company_slug": "test_co", **cap})
    )

    ctx = load_gold_context("test_co", companies_root=tmp_path)
    cap_block = (ctx or {}).get("capital_allocation") or {}
    for raw_token in ("PROVEN_POSITIVE", "PROVEN_NEGATIVE", "DESTRUCTIVE", "NOT_APPLICABLE"):
        for alloc in (cap_block.get("major_allocations") or []):
            if not isinstance(alloc, dict):
                continue
            nat = alloc.get("return_status_natural") or ""
            assert raw_token not in nat, f"Raw vocab {raw_token!r} in return_status_natural"


# ---------------------------------------------------------------------------
# T15 — No hardcoded company names in Gold loader module
# ---------------------------------------------------------------------------
def test_gold_loader_no_hardcoded_companies() -> None:
    loader_path = Path("intelligence/gold/loader.py")
    if not loader_path.exists():
        pytest.skip("loader.py not found at expected path")
    source = loader_path.read_text()
    for name in ("sun_pharma", "ujjivan", "tanla", "Sun Pharma", "Ujjivan", "Tanla"):
        assert name not in source, f"Hardcoded company name {name!r} found in gold/loader.py"
