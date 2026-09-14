import json

from intelligence.risks.builder import (
    _load_gold_risk_attribution,
    _map_gold_to_accountability,
)
from intelligence.risk_evolution_timeline.builder import (
    _explicit_same_disclosure_response,
    normalize_risk_theme,
)
from intelligence.investor_panel.company_memory_context import _compact_risk_evolution
from intelligence.investor_panel.runner import _shared_evidence_routing_rules


def test_gold_attribution_indexes_exact_multi_year_risk_identity(tmp_path):
    gold_dir = tmp_path / "company_memory" / "gold"
    gold_dir.mkdir(parents=True)
    payload = {
        "risk_themes": [
            {
                "risk_theme_id": "RG-0001",
                "theme": "supply-chain disruption",
                "economic_impact_status": "UNPROVEN",
                "timeline": [
                    {
                        "source_item_id": "risk_supply_chain_risk",
                        "event_type": "risk_reconfirmed",
                    }
                ],
            }
        ]
    }
    (gold_dir / "risk_evolution_timeline.json").write_text(json.dumps(payload))

    index = _load_gold_risk_attribution(tmp_path)

    assert index["risk_supply_chain_risk"] == payload["risk_themes"][0]


def test_gold_proven_consequence_maps_to_direct_consequence():
    result = _map_gold_to_accountability(
        {
            "economic_impact_status": "PROVEN",
            "mitigation_status": "not_evidenced",
            "timeline": [
                {
                    "financial_or_operating_effect": "Production interruption reduced supply.",
                    "management_response": "",
                }
            ],
        }
    )

    assert result["consequence_status"] == "DIRECT_CONSEQUENCE"
    assert result["management_response_status"] == "NO_RESPONSE_DISCLOSED"
    assert result["effectiveness_status"] == "EFFECTIVENESS_UNKNOWN"


def test_gold_partial_consequence_does_not_claim_causality():
    result = _map_gold_to_accountability(
        {
            "economic_impact_status": "PARTIAL",
            "mitigation_status": "not_evidenced",
            "timeline": [{"financial_or_operating_effect": "Margins weakened."}],
        }
    )

    assert result["consequence_status"] == "STRONGLY_ASSOCIATED_CONSEQUENCE"
    assert result["effectiveness_status"] == "EFFECTIVENESS_UNKNOWN"


def test_response_execution_never_implies_effectiveness():
    result = _map_gold_to_accountability(
        {
            "economic_impact_status": "UNPROVEN",
            "mitigation_status": "completed_outcome_unproven",
            "current_state": "RECURRING",
            "timeline": [],
        }
    )

    assert result["management_response_status"] == "RESPONSE_EXECUTED"
    assert result["response_execution_status"] == "EXECUTION_COMPLETED"
    assert result["effectiveness_status"] == "EFFECTIVENESS_UNKNOWN"


def test_improvement_after_response_remains_non_attributable():
    result = _map_gold_to_accountability(
        {
            "economic_impact_status": "UNPROVEN",
            "mitigation_status": "resolved",
            "current_state": "IMPROVING",
            "timeline": [],
        }
    )

    assert result["effectiveness_status"] == "ASSOCIATED_WITH_IMPROVEMENT_NOT_ATTRIBUTABLE"


def test_same_risk_disclosure_preserves_explicit_response():
    text = (
        "Foreign exchange exposure is noted as a risk the company seeks to limit "
        "through local sourcing."
    )
    assert "local sourcing" in _explicit_same_disclosure_response(text).lower()


def test_generic_nearby_mitigation_language_is_not_linked():
    assert _explicit_same_disclosure_response(
        "The company has a general risk-management framework and develops mitigation steps."
    ) == ""


def test_response_wording_without_company_actor_is_not_promoted():
    assert _explicit_same_disclosure_response(
        "The risk may be reduced through local sourcing."
    ) == ""


def test_foreign_exchange_wording_has_one_canonical_risk_family():
    variants = (
        "Foreign exchange exposure from international operations",
        "Currency risk affecting assets and liabilities",
        "FX exposure impacting international performance",
    )
    assert {normalize_risk_theme(value) for value in variants} == {
        ("foreign-exchange risk", "currency")
    }


def test_panel_compaction_preserves_canonical_risk_accountability():
    payload = {
        "assessments": [{
            "risk_id": "risk_fx",
            "risk_name": "Foreign exchange risk",
            "trajectory": "worsening",
            "consequence_status": "NO_CONSEQUENCE_EVIDENCE",
            "management_response_status": "RESPONSE_ACKNOWLEDGED",
            "response_execution_status": "EXECUTION_UNKNOWN",
            "effectiveness_status": "EFFECTIVENESS_UNKNOWN",
        }]
    }

    result = _compact_risk_evolution([(None, payload)])
    item = result["worsening"][0]

    assert item["management_response_status"] == "RESPONSE_ACKNOWLEDGED"
    assert item["response_execution_status"] == "EXECUTION_UNKNOWN"
    assert item["effectiveness_status"] == "EFFECTIVENESS_UNKNOWN"


def test_panel_compaction_merges_registry_accountability_into_assessment():
    assessment = {
        "assessments": [{
            "risk_id": "risk_fx",
            "risk_name": "Foreign exchange risk",
            "trajectory": "worsening",
            "what_changed": "Exposure intensified.",
        }]
    }
    registry = {
        "risks": [{
            "risk_id": "risk_fx",
            "management_response_status": "RESPONSE_ACKNOWLEDGED",
            "response_execution_status": "EXECUTION_UNKNOWN",
            "effectiveness_status": "EFFECTIVENESS_UNKNOWN",
        }]
    }

    item = _compact_risk_evolution([(None, assessment), (None, registry)])["worsening"][0]

    assert item["what_changed"] == "Exposure intensified."
    assert item["management_response_status"] == "RESPONSE_ACKNOWLEDGED"


def test_panel_compaction_defaults_sparse_risk_to_unknown_not_success():
    result = _compact_risk_evolution([(None, {
        "assessments": [{"risk_id": "risk_sparse", "trajectory": "recurring"}]
    })])
    item = result["recurring"][0]

    assert item["management_response_status"] == "NO_RESPONSE_DISCLOSED"
    assert item["response_execution_status"] == "EXECUTION_UNKNOWN"
    assert item["effectiveness_status"] == "EFFECTIVENESS_UNKNOWN"


def test_panel_rules_forbid_inflating_response_or_effectiveness():
    rules = "\n".join(_shared_evidence_routing_rules())
    assert "NO_RESPONSE_DISCLOSED" in rules
    assert "does not prove execution" in rules
    assert "EFFECTIVENESS_UNKNOWN never supports" in rules
