"""M63/G2.1 regression tests for the two independently reproduced G2 blockers.

B1  attribution: a target stated by someone else (government, regulator, industry, analysts) is not a company promise merely because it
    appears in the company's annual report. Decided from the SOURCE SENTENCE (speaker of the forward verb), not from the paraphrased promise.
B2  history vs promise: a completed result or a present state is never a commitment, even with a number and a fiscal year in it; in a mixed
    statement only the forward clause can carry the outcome and the deadline.
All tests are pure functions of text; nothing here touches companies/."""
import pytest

from knowledge.company_memory.management_commitments import attribute_statement, classify_commitment


def cls(statement, timeframe="", announced="fy25", **extra):
    return classify_commitment({"original_statement": statement, "expected_timeframe": timeframe, "announcement_period": announced, **extra})


# ── B2: history / state / mixed ──
@pytest.mark.parametrize("statement", [
    "Deposits grew 24% in FY25.",
    "Revenue grew 18% during FY24.",
    "Reached 568 branches by FY25.",
    "Operates 568 branches.",
    "The company has 568 branches across 20 states",
    "We operate 568 branches in FY25",
    "Net profit rose 31% to Rs 1,200 crore in FY24",
    "Opened 120 branches in FY25",
    "Headcount stood at 4,000 in FY25",
    "Added 2 million customers during FY24",
])
def test_reported_results_and_present_states_are_not_commitments(statement):
    assert cls(statement)["commitment_class"] == "OBSERVATION"


@pytest.mark.parametrize("statement, year", [
    ("We will open 100 branches by FY27", 2027),
    ("Open 100 branches by FY27", 2027),
    ("Reduce churn to below 5% by FY28", 2028),
    ("Achieve targeted ROE of 15% by FY27", 2027),                          # "targeted" is a modifier, not a past-tense verb
    ("Exceed 20% market share by FY27", 2027),                              # "Exceed" is not a past tense
    ("Capacity to be expanded to 10 plants by FY27", 2027),
    ("Operate 600 branches by FY27", 2027),                                 # base form = imperative promise; "Operates" = state
])
def test_forward_promises_stay_hard(statement, year):
    c = cls(statement)
    assert c["commitment_class"] == "HARD_COMMITMENT" and c["deadline_year"] == year


def test_a_mixed_statement_takes_outcome_and_deadline_from_the_forward_clause_only():
    c = cls("Revenue grew 18% in FY24 and we will open 100 branches by FY27")
    assert c["commitment_class"] == "HARD_COMMITMENT" and c["deadline_year"] == 2027
    c = cls("Opened 120 branches in FY25; plans to open 80 more")           # forward clause has an outcome but no deadline
    assert c["commitment_class"] == "VERIFIABLE_UNDATED" and c["deadline_year"] is None
    c = cls("Reached 568 branches by FY25 and plans to expand the network")  # forward clause has neither
    assert c["commitment_class"] in ("NOT_TRACKABLE", "DATED_UNVERIFIABLE") and not c["hard"] and c["deadline_year"] is None


def test_the_past_year_of_a_completed_event_is_not_the_deadline_of_the_promise():
    assert cls("Expand physical servicing footprint (16 RACs already, with plans to establish 9 more by FY 2025-26)")["deadline_year"] == 2026


# ── B1: attribution from the source sentence ──
MINISTRY = ("The Defence Ministry aims to achieve 70% self-reliance in weaponry by 2027, offering ample opportunities for industry players. "
            "The Government has introduced Green Channel Status Policy to promote private investment.")


def test_the_data_patterns_ministry_target_is_third_party():
    a = attribute_statement("Achieve 70% self-reliance in weaponry", MINISTRY)
    assert a["attribution"] == "THIRD_PARTY" and a["actor_type"] == "government"


@pytest.mark.parametrize("statement, chunk, expected", [
    ("Achieve defence production of USD 25.00 Billion by 2025", "The Indian government has set the defence production target at USD 25.00 Billion by 2025.", "THIRD_PARTY"),
    ("Grow the sector 12% by FY27", "Analysts expect the sector to grow 12% by FY27, and the regulator aims to double inspections.", "THIRD_PARTY"),
    ("Reach USD 5 billion by 2030", "The industry is projected to reach USD 5 billion by 2030.", "THIRD_PARTY"),
    ("Achieve 70% self-reliance in our product portfolio by 2027", "We aim to achieve 70% self-reliance in our product portfolio by 2027.", "MANAGEMENT"),
    ("Achieve 70% self-reliance in weaponry by 2027", "Management plans to achieve 70% self-reliance in weaponry by 2027, in line with the Ministry's goals.", "MANAGEMENT"),
    ("Achieve 70% self-reliance in weaponry by 2027", "In line with the Ministry's target, we will achieve 70% self-reliance in weaponry by 2027.", "MANAGEMENT"),
    ("Achieve 70% self-reliance in weaponry by 2027", "Aligned with national policy, the company targets 70% self-reliance in weaponry by 2027.", "MANAGEMENT"),
    ("Open 9 more RACs by FY 2025-26", "Expanded to 16 Retail Asset Centres, with plans to establish 9 more RACs by FY 2025-26 across the country.", "MANAGEMENT"),
])
def test_attribution_follows_the_speaker_of_the_forward_verb(statement, chunk, expected):
    assert attribute_statement(statement, chunk)["attribution"] == expected


def test_unclear_attribution_is_not_assigned_to_management():
    a = attribute_statement("Achieve 70% self-reliance in weaponry", "India aims for a lot. Ministry plans noted; 70% self-reliance in weaponry by 2027 is expected for the nation.")
    assert a["attribution"] in ("UNCLEAR", "THIRD_PARTY") and a["attribution"] != "MANAGEMENT"


def test_no_source_context_is_reported_as_such_not_invented():
    a = attribute_statement("Achieve 70% self-reliance in weaponry", "")
    assert a["attribution"] == "UNCLEAR" and a["basis"] == "no_source_sentence"
    a = attribute_statement("Achieve 70% self-reliance in weaponry", "Unrelated text about dividends and the AGM.")
    assert a["attribution"] == "UNCLEAR"


def test_a_sentence_with_no_external_party_keeps_the_report_voice():
    a = attribute_statement("File Nidlegy with the European Medicines Agency", "Our partner product Nidlegy is expected to be filed with the European Medicines Agency for locally advanced melanoma during H1CY24.")
    assert a["attribution"] != "THIRD_PARTY"          # a regulator is the destination here, not the speaker


# ── real data (read-only): the attribution gate removes only the Ministry target; nothing else leaves any register ──
def test_real_registers_lose_only_the_ministry_target(tmp_path):
    import importlib.util, json, pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("candidate_tool", root / "tools" / "g1_candidate_build.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    sizes = {"sun_pharma": 46, "tanla": 28, "ujjivan": 51, "datapatterns": 16}
    for company, stored in sizes.items():
        src, dst = root / "companies" / company, tmp_path / "companies" / company
        (dst / "company_memory").mkdir(parents=True)
        tool.commitments_stage(company, src, dst, tmp_path)
        reg = json.loads((dst / "company_memory/management_commitments/management_commitments.json").read_text())
        stored_n = len(json.loads((src / "company_memory/management_commitments/management_commitments.json").read_text())["commitments"])
        assert stored_n == stored
        if company == "datapatterns":
            assert len(reg["commitments"]) == stored - 1 and not any("70% self-reliance" in c["original_statement"] for c in reg["commitments"])
            q = [x for x in reg["quarantined_candidates"] if "70% self-reliance" in x["original_statement"]]
            assert q and q[0]["quarantine_reason"] == "EXTERNAL_ACTOR" and q[0]["attribution"]["actor_type"] == "government"
        else:
            assert len(reg["commitments"]) == stored


# ── source fidelity: an outlook is never strengthened into a promise ──
PIPELINE = "We have an order book of Rs. 1,083 Cr with a pipeline going forward of Rs 2 - 3 bn over next couple of years."


def test_a_pipeline_outlook_is_not_a_promise_just_because_the_paraphrase_starts_with_achieve():
    a = attribute_statement("Achieve a business pipeline of Rs. 2 - 3 bn", PIPELINE)
    assert a["basis"] == "no_forward_verb_in_sentence" and not a["intent_in_source"]
    c = cls("Achieve a business pipeline of Rs. 2 - 3 bn", timeframe="over next couple of years", announced="fy24", source_intent=False)
    assert c["commitment_class"] == "OUTLOOK_NOT_COMMITMENT" and not c["hard"] and c["verifiable_outcome"] and c["deadline_year"] == 2026
    assert cls("Achieve a business pipeline of Rs. 2 - 3 bn", timeframe="over next couple of years", announced="fy24")["hard"]   # without the source check the paraphrase alone would have been hard


def test_bare_bullets_under_a_roadmap_heading_keep_their_intent():
    a = attribute_statement("Ramp-up ILUMYA prescriptions in Japan and Australia", "Roadmap • Ramp-up ILUMYA prescriptions in Japan and Australia • Evaluate newer markets in RoW")
    assert a["basis"] == "no_forward_verb_in_sentence" and a["intent_in_source"]


# ── G2.2: possessive external actors and historical participial continuations ──
@pytest.mark.parametrize("statement, chunk, expected", [
    ("Achieve 70% self-reliance in weaponry by 2027", "Our government aims to achieve 70% self-reliance in weaponry by 2027.", "THIRD_PARTY"),
    ("Reach 500 GW renewable capacity by 2030", "Our Ministry has set a target to reach 500 GW renewable capacity by 2030.", "THIRD_PARTY"),
    ("Grow the market to USD 100 billion by 2030", "Our industry body expects the market to grow to USD 100 billion by 2030.", "THIRD_PARTY"),
    ("Cut NPAs below 3% by FY27", "Our regulator plans to cut NPAs below 3% by FY27.", "THIRD_PARTY"),
    ("Achieve 70% self-reliance in weaponry by 2027", "The company and the Ministry aim to achieve 70% self-reliance in weaponry by 2027.", "UNCLEAR"),   # co-actor: not assigned to management
    ("Achieve 70% self-reliance in weaponry by 2027", "We will achieve 70% self-reliance in weaponry by 2027, supporting our government's aim.", "MANAGEMENT"),
    ("Achieve 70% self-reliance in weaponry by 2027", "Supporting our government's aim, the company will achieve 70% self-reliance in weaponry by 2027.", "MANAGEMENT"),
])
def test_a_possessive_does_not_turn_an_external_actor_into_management(statement, chunk, expected):
    assert attribute_statement(statement, chunk)["attribution"] == expected


def test_the_real_register_gate_quarantines_our_government_and_keeps_genuine_policy_aligned_commitments(tmp_path):
    import json

    from knowledge.company_memory.management_commitments import build_management_commitments

    items = [("Achieve 70% self-reliance in weaponry by 2027", "Our government aims to achieve 70% self-reliance in weaponry by 2027."),
             ("Launch Product Y in Japan by FY28", "In line with the national policy, we will launch Product Y in Japan by FY28."),
             ("Cut costs 30% by FY28", "The company and the Ministry aim to cut costs 30% by FY28.")]
    fy = tmp_path / "acme" / "fy25"
    (fy / "intelligence").mkdir(parents=True)
    (fy / "extracted").mkdir()
    (tmp_path / "acme" / "company_memory").mkdir()
    promises = [{"promise": p, "timeline": "", "category": "strategic objective", "page": i + 5, "actor": "company", "confidence": "high", "id": f"PROM_{i}"} for i, (p, _) in enumerate(items)]
    (fy / "intelligence" / "company_intelligence.json").write_text(json.dumps({"management": {"promises": {"items": promises}}}))
    (fy / "extracted" / "extracted_promises.json").write_text(json.dumps([{"promise": p, "source_chunk": c, "page": i + 5} for i, (p, c) in enumerate(items)]))
    build_management_commitments("acme", companies_root=tmp_path)
    out = json.loads((tmp_path / "acme/company_memory/management_commitments/management_commitments.json").read_text())
    registered = {c["original_statement"]: c for c in out["commitments"]}
    quarantined = {q["original_statement"]: q["quarantine_reason"] for q in out["quarantined_candidates"]}
    assert quarantined["Achieve 70% self-reliance in weaponry by 2027"] == "EXTERNAL_ACTOR"
    assert quarantined["Cut costs 30% by FY28"] == "UNCLASSIFIED_STATEMENT"                       # co-actor is uncertain, not management
    assert registered["Launch Product Y in Japan by FY28"]["hard_commitment"]       # a genuine commitment that cites a policy stays eligible


@pytest.mark.parametrize("statement", [
    "Deposits grew 24% in FY25, taking the deposit base to ₹9,000 crore.",
    "Revenue rose 18% in FY24, bringing the order book to Rs 1,083 crore",
    "Added 120 branches in FY25, lifting the network to 568 branches",
    "Profit grew 31% during FY24, pushing ROE to 18%",
])
def test_a_historical_clause_and_its_participial_result_are_one_observation(statement):
    assert cls(statement)["commitment_class"] == "OBSERVATION"


@pytest.mark.parametrize("statement, expected, year", [
    ("Revenue grew 18% in FY24, expanding to 50 cities by FY27", "HARD_COMMITMENT", 2027),         # own deadline after the announcement
    ("Deposits grew 24% in FY25, targeting a Rs 12,000 crore deposit base by FY27", "HARD_COMMITMENT", 2027),
    ("We will open 100 branches by FY27, taking the network to 668 branches", "HARD_COMMITMENT", 2027),   # forward parent: the result stays with it
    ("Deposits grew 24% in FY25, aiming to add 100 branches", "VERIFIABLE_UNDATED", None),         # own intent, no deadline
])
def test_genuine_forward_clauses_survive_a_historical_parent(statement, expected, year):
    c = cls(statement)
    assert c["commitment_class"] == expected and c["deadline_year"] == year
