from __future__ import annotations

import json
from pathlib import Path

from intelligence.progression import build_interpretation_contract, rank_material_evidence


def test_material_evidence_ranking_prefers_material_and_relevant_items():
    items = [
        {"summary": "Routine update", "relevance": "low", "confidence": {"level": "low"}, "period": "fy23"},
        {"summary": "Capital allocation and per-share return trail", "relevance": "high", "confidence": {"level": "high"}, "period": "fy25"},
        {"summary": "Minor wording change", "relevance": "low", "confidence": {"level": "high"}, "period": "fy26"},
    ]

    ranked = rank_material_evidence(items, limit=2, latest_period="fy25", thesis_focus=("capital", "share"))
    assert [item["summary"] for item in ranked] == [
        "Capital allocation and per-share return trail",
        "Minor wording change",
    ]


def test_interpretation_contract_keeps_unresolved_items_explicit():
    interpretation = build_interpretation_contract(
        conclusion="Capacity improved, but value creation is unresolved.",
        what_changed=["Installed capacity increased"],
        why_it_matters="Installed capacity only matters if it becomes utilized.",
        economic_mechanism="Capacity creates value only when utilization and returns follow deployment.",
        thesis_impact="unresolved",
        positive_evidence=["Installed capacity increased"],
        negative_evidence=["Utilization is still thin"],
        unresolved=["Economic payback is still not visible"],
        what_to_watch=["Utilization", "Incremental returns"],
        confidence={"level": "medium", "basis": ["directional evidence"], "limitations": ["economic payoff not yet visible"]},
    )

    assert interpretation["thesis_impact"] == "unresolved"
    assert interpretation["unresolved"] == ["Economic payback is still not visible"]
    assert interpretation["what_to_watch"] == ["Utilization", "Incremental returns"]
    assert interpretation["economic_mechanism"].startswith("Capacity creates value")


def test_datapatterns_outputs_expose_interpretation_blocks():
    root = Path("companies/datapatterns/company_memory")

    mgmt = json.loads((root / "management_quality" / "management_quality_summary.json").read_text(encoding="utf-8"))
    assert mgmt["interpretation"]["economic_mechanism"]
    assert mgmt["interpretation"]["thesis_impact"] in {"strengthens", "weakens", "neutral", "unresolved"}

    committee = json.loads((root / "investor_panel" / "committee_synthesis.json").read_text(encoding="utf-8"))
    assert committee["management_judgment"]["interpretation"]["economic_mechanism"]
    assert committee["risk_judgment"]["interpretation"]["thesis_impact"] in {"strengthens", "weakens", "neutral", "unresolved"}

    ask = json.loads((root / "ask_intrinsiciq" / "answer_cards.json").read_text(encoding="utf-8"))
    break_thesis = next(answer for answer in ask["answers"] if answer["question_id"] == "what-can-break-the-thesis")
    assert break_thesis["interpretation"]["economic_mechanism"]
    assert break_thesis["interpretation"]["thesis_impact"] in {"strengthens", "weakens", "neutral", "unresolved"}
