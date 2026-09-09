from __future__ import annotations

import json
from pathlib import Path

from intelligence.ask_intrinsiciq.answer_cards import (
    _build_management_promises_answer,
    _build_past_claims_answer,
)
from intelligence.management_credibility.builder import build_management_credibility_synthesis
from intelligence.management_promises.builder import build_management_promise_tracker
from intelligence.management_promises.verification_bridge import build_verification_events
from knowledge.management_progression.producer import build_management_progression


def _commitment(mc_id: str, fingerprint: str, statement: str) -> dict:
    return {
        "id": mc_id,
        "commitment_fingerprint": fingerprint,
        "topic": "Product launch",
        "category": "Product",
        "announcement_period": "fy21",
        "original_statement": statement,
        "normalized_commitment": statement.lower(),
        "priority": "high",
        "status": "Unable To Verify",
        "statement_type": "planned_action",
        "accountability_ontology": "VERIFIABLE_COMMITMENT",
        "verification_applicability": "APPLICABLE",
        "semantic_quality": {"investor_relevance": "core", "materiality": "high", "relevance_outcome": "KEEP"},
        "source_references": [{"period": "fy21", "source_item_id": f"src-{mc_id}"}],
    }


def _write_inputs(root: Path) -> None:
    company = root / "sample_co"
    mc_dir = company / "company_memory" / "management_commitments"
    mc_dir.mkdir(parents=True)
    commitments = [
        _commitment("MC-0008", "fp-ilumya", "Ramp-up ILUMYA prescriptions in Japan and Australia"),
        _commitment("MC-0006", "fp-generic", "Target new markets for specialty products"),
    ]
    (mc_dir / "management_commitments.json").write_text(json.dumps({"company": "sample_co", "commitments": commitments}))
    annual = company / "fy22" / "intelligence"
    annual.mkdir(parents=True)
    (annual / "management_summary.json").write_text(json.dumps({"key_initiatives": ["ILUMYA launched in Japan and Australia"], "company_results": []}))


def _bundle(**payloads: dict) -> dict:
    return {"company_slug": "sample_co", "sources": {key: {"status": "loaded", "payload": value} for key, value in payloads.items()}}


def test_bridge_to_mp_to_gold_is_one_coherent_accountability_path(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    bridge = build_verification_events("sample_co", tmp_path)
    assert bridge["summary"] == {"VERIFIED": 1, "UNVERIFIED": 1}

    progression = build_management_progression("sample_co", companies_root=tmp_path, generated_at="2026-01-01T00:00:00Z")
    mp_dir = tmp_path / "sample_co" / "company_memory" / "management_progression"
    mp_dir.mkdir(parents=True)
    (mp_dir / "management_progression.json").write_text(json.dumps(progression))

    ilumya = next(item for item in progression["progression_items"] if any(event.get("event_id") == "fp-ilumya" for event in item["events"]))
    assert ilumya["current_status"] == "delivered"
    assert any(event["role"] == "completion" and event["verification_status"] == "verified" for event in ilumya["events"])

    gold = build_management_promise_tracker("sample_co", companies_root=tmp_path)
    by_id = {item["management_commitment_id"]: item for item in gold["accountability_promises"]}
    assert by_id["MC-0008"]["accountability_verification_state"] == "VERIFIED"
    assert by_id["MC-0008"]["current_status"] == "ACHIEVED"
    assert by_id["MC-0006"]["accountability_verification_state"] == "UNVERIFIED"
    assert gold["summary"]["accountability_metrics"]["verified_commitments"] == 1
    assert gold["summary"]["accountability_metrics"]["unresolved_verifiable_commitments"] == 1


def test_ask_and_credibility_use_gold_accountability_denominator(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    build_verification_events("sample_co", tmp_path)
    progression = build_management_progression("sample_co", companies_root=tmp_path)
    mp_dir = tmp_path / "sample_co" / "company_memory" / "management_progression"
    mp_dir.mkdir(parents=True)
    (mp_dir / "management_progression.json").write_text(json.dumps(progression))
    gold = build_management_promise_tracker("sample_co", companies_root=tmp_path)
    gold_dir = tmp_path / "sample_co" / "company_memory" / "gold"
    (gold_dir / "management_promise_tracker.json").write_text(json.dumps(gold))
    credibility = build_management_credibility_synthesis("sample_co", companies_root=tmp_path)
    assert credibility["dimensions"]["promise_follow_through"]["evidence_completeness_signal"] == "1 unverified out of 2 tracked promises."

    bundle = _bundle(gold_promise_tracker=gold, gold_credibility=credibility, management_commitments={"commitments": []}, management_progression=progression)
    question = {"question_id": "q", "title": "q", "category_id": "management"}
    promised = _build_management_promises_answer(bundle, business_journey_payload={}, products_services_payload={}, question=question)
    claims = _build_past_claims_answer(bundle, business_journey_payload={}, products_services_payload={}, question=question)
    rendered = json.dumps([promised, claims])
    assert "1 have delivery evidence and 1 remain unresolved" in promised["simple_answer"]
    assert "1 are verified" in claims["simple_answer"]
    assert "31 commitments" not in rendered
    assert "31 unverified" not in rendered


def test_bridge_does_not_require_preexisting_gold(tmp_path: Path) -> None:
    _write_inputs(tmp_path)
    assert not (tmp_path / "sample_co" / "company_memory" / "gold" / "management_promise_tracker.json").exists()
    result = build_verification_events("sample_co", tmp_path)
    assert sum(result["summary"].values()) == 2
