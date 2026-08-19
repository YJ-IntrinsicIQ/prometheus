import json
from pathlib import Path

from knowledge.evidence_layer import build_evidence_quality
from knowledge.company_memory.guardrails import (
    assess_progression_materiality,
    classify_business_relevance,
    classify_temporal_references,
    resolve_period_status,
    semantic_validation,
)


ROOT = Path(__file__).resolve().parents[2]


def load_capacity_item(company: str, fy: str, item_id: str):
    path = ROOT / "companies" / company / fy / "extracted" / "extracted_capacity.json"
    for item in json.loads(path.read_text()):
        if item.get("item_id") == item_id:
            return item
    raise AssertionError(f"missing capacity item {company} {fy} {item_id}")


def load_extracted_item(company: str, fy: str, artifact: str, item_id: str):
    path = ROOT / "companies" / company / fy / "extracted" / artifact
    for item in json.loads(path.read_text()):
        if item.get("item_id") == item_id:
            return item
    raise AssertionError(f"missing item {company} {fy} {artifact} {item_id}")


def test_business_relevance_quarantines_non_core_civic_projects():
    relevance = classify_business_relevance(
        "School renovation and classroom addition to support students.",
        module_name="projects",
        actor_type="management",
        source_kind="management_summary",
    )

    assert relevance["quarantine"] is True
    assert relevance["status"] in {"ambiguous", "out_of_scope"}


def test_business_relevance_accepts_company_specific_risk_disclosures():
    relevance = classify_business_relevance(
        "Dynamic and stringent regulatory/compliance environment requiring ongoing changes to platforms and processes.",
        module_name="risks",
        actor_type="management",
    )

    assert relevance["quarantine"] is False
    assert relevance["status"] in {"core", "supporting"}


def test_period_resolution_detects_historical_context():
    period = resolve_period_status(
        source_year="fy22",
        text="Production ongoing since 2013.",
        explicit_year="2013",
    )

    assert period["status"] == "HISTORICAL_CONTEXT"


def test_period_resolution_allows_forward_looking_project_years():
    period = resolve_period_status(
        source_year="fy22",
        text="Capacity expansion planned for FY25.",
        explicit_year="FY25",
        module_name="projects",
    )

    assert period["status"] == "RESOLVED"


def test_period_resolution_accepts_comparative_history_when_source_period_is_anchor():
    period = resolve_period_status(
        source_year="fy21",
        text="Scaled monthly disbursals from ₹16 Crores in June, 2020 to ₹125+ Crores in March, 2021.",
        explicit_year="2021",
        module_name="capacity_expansions",
    )

    assert period["status"] == "RESOLVED"
    assert period["resolved_period"] == "fy21"
    assert any("source period fy21" in basis.lower() for basis in period["basis"])


def test_period_resolution_still_rejects_conflicting_year_mentions():
    period = resolve_period_status(
        source_year="fy20",
        text="FY20 and FY21 both appear in the same promise context.",
        explicit_year="FY20",
        module_name="promises",
    )

    assert period["status"] == "AMBIGUOUS"


def test_period_resolution_separates_source_period_from_target_period_for_promises():
    period = resolve_period_status(
        source_year="fy24",
        text="Expand globally with ValueFirst. FY24 context and FY25 target are both present in the narrative.",
        explicit_year="FY25",
        module_name="promises",
        target_period="FY25",
    )

    assert period["status"] == "RESOLVED"


def test_period_resolution_keeps_source_target_plus_extra_year_ambiguous():
    period = resolve_period_status(
        source_year="fy24",
        text="Expand globally with ValueFirst. FY24 context, FY25 target, and FY26 follow-on all appear in the same narrative.",
        explicit_year="FY25",
        module_name="promises",
        target_period="FY25",
    )

    assert period["status"] == "AMBIGUOUS"
    assert period["failure_class"] == "SOURCE_PERIOD_VS_TARGET_PERIOD_CONFLICT"


def test_period_resolution_separates_source_historical_and_target_roles_for_promises():
    item = {
        "promise": "Customer log-ins for the first set of MSME products to commence.",
        "source_year": "fy23",
        "year": "2021",
        "timeline": "Q1 FY24",
        "category": "product launch commitment",
    }

    quality = build_evidence_quality(item, module_name="promises")

    period = quality["period_resolution"]
    assert period["status"] == "RESOLVED"
    assert period["resolved_period"] == "fy23"
    assert period["temporal_roles"]["source_period"] == "fy23"
    assert period["temporal_roles"]["event_period"] == "fy23"
    assert period["temporal_roles"]["target_period"] == "fy24"
    assert period["temporal_roles"]["historical_periods"] == ["fy21"]


def test_period_resolution_keeps_unrelated_future_years_ambiguous():
    period = resolve_period_status(
        source_year="fy23",
        text="FY21 legacy setup is referenced alongside FY24 rollout and FY25 expansion.",
        explicit_year="FY21",
        module_name="promises",
        target_period="FY24",
    )

    assert period["status"] == "AMBIGUOUS"


def test_period_resolution_keeps_two_historical_events_ambiguous_without_comparative_context():
    period = resolve_period_status(
        source_year="fy23",
        text="The project records separate actions in FY20 and FY21 without a declared anchor.",
        module_name="projects",
    )

    assert period["status"] == "AMBIGUOUS"


def test_period_resolution_ignores_parenthetical_example_years_for_risks():
    period = resolve_period_status(
        source_year="fy20",
        text="Dynamic and stringent regulatory/compliance environment (e.g., TCCPR 2018) requiring ongoing changes to platforms and processes.",
        explicit_year="fy20",
        module_name="risks",
    )

    assert period["status"] == "RESOLVED"


def test_period_resolution_allows_paired_fiscal_years_for_capital_allocations():
    period = resolve_period_status(
        source_year="fy22",
        text="Final dividend for FY 2021-22 proposed by the Board, subject to shareholder approval.",
        explicit_year="fy22",
        module_name="capital_allocations",
    )

    assert period["status"] == "RESOLVED"


def test_period_resolution_ignores_statute_year_references():
    period = resolve_period_status(
        source_year="fy24",
        text="Transfer to Special Reserve U/S 36(1)(viii) Income Tax Act, 1961 for FY 2023-24.",
        explicit_year="2023",
        module_name="capital_allocations",
    )

    assert period["status"] == "RESOLVED"
    assert period["resolved_period"] == "fy24"
    assert "1961" not in " ".join(period["basis"])
    assert any(
        item["year"] == 1961 and item["role"] == "NON_TEMPORAL_REFERENCE"
        for item in period["temporal_roles"]["references"]
    )


def test_period_resolution_ignores_accounting_and_regulatory_reference_years():
    period = resolve_period_status(
        source_year="fy24",
        text="Current period accounting classification follows Ind AS 116 and RBI circular dated September 23, 2000.",
        explicit_year="fy24",
        module_name="risks",
    )

    assert period["status"] == "RESOLVED"


def test_period_resolution_allows_risk_observation_with_explicit_future_target_role():
    period = resolve_period_status(
        source_year="fy24",
        text="Supply chains remain unstable, so the company is working towards self-sufficiency by 2030.",
        explicit_year="2030",
        module_name="risks",
    )

    assert period["status"] == "RESOLVED"
    assert period["resolved_period"] == "fy24"
    assert period["temporal_roles"]["target_period"] == "fy30"


def test_period_resolution_still_rejects_unsupported_future_risk_year():
    period = resolve_period_status(
        source_year="fy24",
        text="Supply chain risk includes a standalone 2030 reference without any stated company action.",
        explicit_year="2030",
        module_name="risks",
    )

    assert period["status"] == "OUTSIDE_ANALYSIS_WINDOW"


def test_polymatech_fy24_risk_future_target_from_source_context_resolves():
    item = load_extracted_item("polymatech", "fy24", "extracted_risks.json", "risks_00001")
    item["source_year"] = "fy24"
    quality = build_evidence_quality(item, module_name="risks")

    assert quality["period_resolution"]["status"] == "RESOLVED"
    assert quality["period_resolution"]["resolved_period"] == "fy24"
    assert quality["period_resolution"]["temporal_roles"]["target_period"] == "fy30"


def test_ujjivan_fy21_risk_comparative_table_context_resolves():
    item = load_extracted_item("ujjivan", "fy21", "extracted_risks.json", "risks_00013")
    quality = build_evidence_quality(item, module_name="risks")

    assert quality["period_resolution"]["status"] == "RESOLVED"
    assert quality["period_resolution"]["resolved_period"] == "fy21"
    assert "fy20" in quality["period_resolution"]["temporal_roles"]["historical_periods"]


def test_ujjivan_fy24_risk_forecast_range_resolves_to_source_observation():
    item = load_extracted_item("ujjivan", "fy24", "extracted_risks.json", "risks_00001")
    quality = build_evidence_quality(item, module_name="risks")

    assert quality["period_resolution"]["status"] == "RESOLVED"
    assert quality["period_resolution"]["resolved_period"] == "fy24"
    assert quality["period_resolution"]["temporal_roles"]["target_period"] == "fy25"
    assert "fy22" in quality["period_resolution"]["temporal_roles"]["historical_periods"]


def test_period_resolution_preserves_actual_historical_comparison_years():
    period = resolve_period_status(
        source_year="fy24",
        text="FY24 disclosure compares the current reserve transfer with the actual FY23 transfer.",
        explicit_year="2023",
        module_name="capital_allocations",
    )

    assert period["status"] == "RESOLVED"
    assert period["temporal_roles"]["historical_periods"] == ["fy23"]


def test_temporal_reference_contract_classifies_source_target_and_comparison_roles():
    references = classify_temporal_references(
        "FY23 annual report compares FY22 performance and targets FY24 customer rollout.",
        source_year="fy23",
        target_period="fy24",
        module_name="promises",
    )
    roles_by_year = {
        item["year"]: item["role"]
        for item in references
    }

    assert roles_by_year[2023] == "SOURCE_PERIOD"
    assert roles_by_year[2022] == "COMPARATIVE_PERIOD"
    assert roles_by_year[2024] == "TARGET_PERIOD"


def test_temporal_reference_contract_marks_non_temporal_statute_years():
    references = classify_temporal_references(
        "Transfer follows Income Tax Act, 1961 and Banking Regulation Act, 1949 for FY 2023-24.",
        source_year="fy24",
        module_name="capital_allocations",
    )
    statute_years = {
        item["year"]
        for item in references
        if item["role"] == "NON_TEMPORAL_REFERENCE"
    }

    assert statute_years == {1949, 1961}


def test_capacity_current_target_row_resolves_from_corpus():
    item = load_capacity_item("tanla", "fy23", "capacity_expansions_00002")
    quality = build_evidence_quality(item, module_name="capacity_expansions")

    assert quality["period_resolution"]["status"] == "RESOLVED"
    assert any("current-state" in basis for basis in quality["period_resolution"]["basis"])


def test_capacity_future_milestone_from_corpus_resolves():
    item = load_capacity_item("tanla", "fy24", "capacity_expansions_00001")
    quality = build_evidence_quality(item, module_name="capacity_expansions")

    assert quality["period_resolution"]["status"] == "RESOLVED"


def test_capacity_historical_reference_stays_historical_context():
    period = resolve_period_status(
        source_year="fy26",
        text="FY25 (added during FY25)",
        explicit_year="FY25",
        module_name="capacity_expansions",
    )

    assert period["status"] in {"RESOLVED", "HISTORICAL_CONTEXT"}


def test_capacity_ambiguous_multi_year_evidence_still_fails():
    period = resolve_period_status(
        source_year="fy23",
        text="Capacity expansion noted in FY24 and FY25 without a declared target.",
        module_name="capacity_expansions",
    )

    assert period["status"] == "AMBIGUOUS"


def test_materiality_requires_resolved_core_evidence():
    relevance = classify_business_relevance("Commissioned new manufacturing line.", module_name="projects", actor_type="management")
    period = resolve_period_status(source_year="fy24", text="Commissioned new manufacturing line.", explicit_year="fy24")
    materiality = assess_progression_materiality(
        "Commissioned new manufacturing line.",
        module_name="projects",
        relevance_status=relevance["status"],
        period_status=period["status"],
        evidence_quality={"company_specificity": "high", "actionability": "high", "investor_relevance": "high", "numeric_support": True},
        status_text="commissioned",
    )

    assert materiality["should_promote"] is True


def test_semantic_validation_blocks_quarantined_items():
    relevance = classify_business_relevance("Pond and stormwater management capacity.", module_name="capacity", actor_type="management")
    period = resolve_period_status(source_year="fy22", text="Pond and stormwater management capacity.", explicit_year="2013")
    validation = semantic_validation(module_name="capacity", relevance=relevance, period=period, materiality={"level": "low", "should_promote": False})

    assert validation["errors"]
