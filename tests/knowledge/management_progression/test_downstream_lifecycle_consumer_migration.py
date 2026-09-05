from __future__ import annotations

from intelligence.ask_intrinsiciq.answer_cards import (
    _commitment_lifecycle_status_label,
    _management_progression_commitment_index,
    _mc_claim_outcome_points,
    _mc_specific_promise_points,
)
from intelligence.management_quality.evidence_linker import extract_commitment_evidence
from intelligence.management_promises.builder import (
    resolve_current_status,
    resolve_execution_status,
    resolve_financial_link_status,
    resolve_outcome_status,
)


def _commitment(
    fingerprint: str,
    *,
    status: str = "Delivered",
    topic: str = "Platform rollout",
    text: str = "Roll out a new digital platform",
    assessment: str = "Later evidence supports delivery.",
) -> dict:
    return {
        "id": "MC-9999",
        "commitment_fingerprint": fingerprint,
        "announcement_period": "fy24",
        "topic": topic,
        "normalized_commitment": text,
        "original_statement": text,
        "status": status,
        "delivery_assessment": assessment,
        "investor_implication": "Investors should watch whether execution evidence appears.",
        "category": "Technology",
        "priority": "high",
        "confidence": {"level": "medium"},
        "source_references": [{"period": "fy24", "source_year": "fy24"}],
    }


def _mp_item(fingerprint: str, current_status: str) -> dict:
    return {
        "item_id": "MP-1",
        "current_status": current_status,
        "events": [
            {
                "event_id": fingerprint,
                "event_role": "commitment",
                "period": "fy24",
                "summary": "Management made the commitment.",
            },
        ],
    }


def _mp_payload(*items: dict) -> dict:
    return {"progression_items": list(items)}


def test_ask_q_a_follows_management_progression_not_stale_mc_delivered() -> None:
    fp = "fp-utv"
    commitment = _commitment(fp, status="Delivered")
    index = _management_progression_commitment_index(_mp_payload(_mp_item(fp, "announced")))

    points = _mc_specific_promise_points([commitment], lifecycle_index=index)

    assert points
    assert "Unable To Verify" in points[0]
    assert "Delivered" not in points[0]


def test_ask_q_b_follows_management_progression_and_ignores_delivery_assessment() -> None:
    fp = "fp-qb"
    commitment = _commitment(fp, status="Delivered", assessment="Later evidence supports delivery.")
    index = _management_progression_commitment_index(_mp_payload(_mp_item(fp, "announced")))

    points = _mc_claim_outcome_points([commitment], lifecycle_index=index)

    assert points
    assert "Unable To Verify" in points[0]
    assert "supports delivery" not in points[0]
    assert "Delivered" not in points[0]


def test_mp_in_progress_overrides_mc_unable_to_verify_downstream() -> None:
    fp = "fp-progress"
    commitment = _commitment(fp, status="Unable To Verify")
    index = _management_progression_commitment_index(_mp_payload(_mp_item(fp, "in_progress")))

    assert _commitment_lifecycle_status_label(commitment, index) == "In Progress"
    assert "In Progress" in _mc_specific_promise_points([commitment], lifecycle_index=index)[0]


def test_missing_mp_match_is_unknown_not_mc_fallback() -> None:
    commitment = _commitment("fp-missing", status="Delivered")

    assert _commitment_lifecycle_status_label(commitment, {}) == "Unable To Verify"
    assert "Delivered" not in _mc_specific_promise_points([commitment], lifecycle_index={})[0]


def test_fingerprint_join_survives_ordinal_id_change() -> None:
    fp = "stable-fingerprint"
    commitment = _commitment(fp, status="Unable To Verify")
    commitment["id"] = "MC-CHANGED"
    index = _management_progression_commitment_index(_mp_payload(_mp_item(fp, "in_progress")))

    assert _commitment_lifecycle_status_label(commitment, index) == "In Progress"


def test_topic_equality_is_irrelevant_to_lifecycle_join() -> None:
    matched = _commitment("fp-match", status="Unable To Verify", topic="Product launch")
    same_topic_unmatched = _commitment("fp-other", status="Delivered", topic="Product launch")
    index = _management_progression_commitment_index(_mp_payload(_mp_item("fp-match", "in_progress")))

    assert _commitment_lifecycle_status_label(matched, index) == "In Progress"
    assert _commitment_lifecycle_status_label(same_topic_unmatched, index) == "Unable To Verify"


def test_management_quality_uses_mp_lifecycle_not_mc_delivery_status() -> None:
    fp = "fp-mq"
    commitment = _commitment(fp, status="Delivered")
    evidence = extract_commitment_evidence([commitment], _mp_payload(_mp_item(fp, "announced")))

    assert evidence
    assert evidence[0]["polarity"] == "neutral"
    assert evidence[0]["direction"] == "unclear"
    assert evidence[0]["evidence_type"] == "commitment_unable_to_verify"


def test_management_quality_mp_in_progress_is_mixed_not_mc_negative() -> None:
    fp = "fp-mq-progress"
    commitment = _commitment(fp, status="Unable To Verify")
    evidence = extract_commitment_evidence([commitment], _mp_payload(_mp_item(fp, "in_progress")))

    assert evidence[0]["polarity"] == "mixed"
    assert evidence[0]["evidence_type"] == "commitment_in_progress"


def test_gold_status_cannot_contradict_mp_item() -> None:
    mp_item = {
        "events": [{"event_role": "commitment"}],
        "current_status": "announced",
        "management_credibility_signal": "claim_only",
    }
    execution = resolve_execution_status(mp_item)
    financial_link = resolve_financial_link_status(mp_item)
    outcome = resolve_outcome_status(mp_item, execution_status=execution, financial_link_status=financial_link)
    current = resolve_current_status(mp_item, outcome, execution)

    assert execution == "CLAIM_ONLY"
    assert outcome == "UNVERIFIED"
    assert current == "UNVERIFIED"


def test_delivery_assessment_cannot_influence_final_status() -> None:
    fp = "fp-assessment"
    commitment = _commitment(fp, status="Delivered", assessment="Later evidence supports delivery.")
    index = _management_progression_commitment_index(_mp_payload(_mp_item(fp, "announced")))

    assert _commitment_lifecycle_status_label(commitment, index) == "Unable To Verify"
