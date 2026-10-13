"""M63/G2 regression tests: one authoritative owner per shared concept.

Commitments: knowledge.company_memory.management_commitments.classify_commitment is the single classifier (the register builder owns commitment
identity); the register, the promise tracker and the progression tracker must agree with it on WHICH commitments qualify (identity), not just on
totals. intelligence.management_quality.fact_pack_v2 (the M50.1 predicate) is FROZEN - its digest is part of the V3/V4/V5 contract identities -
so its known, pinned divergence is tested separately instead of being "fixed" by editing it.
Net debt: knowledge.financials.ratio_calculator.net_debt_measure is the single calculation.
Nothing here writes under companies/ (candidate artifacts are built in tmp_path)."""
import importlib.util
import json
import pathlib

import pytest

from intelligence.management_quality.fact_pack_v2 import _count_hard_commitments
from knowledge.company_memory.management_commitments import canonical_commitment_fields, classify_accountability_ontology, classify_commitment, is_hard_commitment
from knowledge.financials.ratio_calculator import net_debt_measure
from knowledge.management_progression.linker import _build_measurable_commitments

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPANIES = ("sun_pharma", "tanla", "ujjivan", "datapatterns")
# which commitments are HARD under the owner policy, by register identity (pinned so a regression names the commitment that moved)
EXPECTED_HARD = {"sun_pharma": {"MC-0029", "MC-0031", "MC-0039"}, "tanla": set(), "ujjivan": {"MC-0043"}, "datapatterns": set()}   # G2.1: MC-0001 is the Defence Ministry's 70% aim (FY22 p27), not a Data Patterns commitment; MC-0006 is a pipeline outlook (FY24 p8)


def cls(statement, timeframe="unspecified", announced="fy25"):
    return classify_commitment({"original_statement": statement, "expected_timeframe": timeframe, "announcement_period": announced})


# ── 1. policy: verifiable outcome AND explicit deadline ──
@pytest.mark.parametrize("statement, expected", [
    ("Open 100 branches by FY27", "HARD_COMMITMENT"),
    ("Reach ₹5,000 crore revenue within three years", "HARD_COMMITMENT"),
    ("We aim to become a market leader", "NOT_TRACKABLE"),                        # aspiration
    ("We plan to expand manufacturing capacity", "NOT_TRACKABLE"),                # undated intention
    ("Open 100 branches", "VERIFIABLE_UNDATED"),                                  # verifiable, no deadline
    ("Improve employee satisfaction by 2025", "DATED_UNVERIFIABLE"),              # deadline, no checkable outcome
])
def test_policy_examples(statement, expected):
    assert cls(statement)["commitment_class"] == expected


def test_deadline_stated_inside_the_statement_counts_even_when_the_structured_field_is_empty():
    c = cls("Expand physical servicing footprint (16 RACs already, with plans to establish 9 more by FY 2025-26)", timeframe="unspecified")
    assert c["hard"] and c["deadline_source"] == "statement" and c["deadline_year"] == 2026 and c["verifiable_outcome"] == "quantified_target"


def test_structured_timeframe_still_counts_and_is_labelled_as_the_source():
    c = cls("Co-process 30% of hazardous waste.", timeframe="By 2025")
    assert c["hard"] and c["deadline_source"] == "expected_timeframe" and c["deadline_year"] == 2025


@pytest.mark.parametrize("statement", [
    "the business went live across all 568 branches",                                                    # completed event
    "A 7.0% increase in attrition at the associates level is attributed to post-pandemic factors",       # observed outcome
    "Use of AI has driven measurable operational improvements, including over 90% reduction in registration time",
    "Robotic Process Automation milestones: automated UPI reconciliation; 15 new processes automated; 51,597 man-hours saved",
])
def test_a_completed_event_or_observed_outcome_is_never_a_commitment(statement):
    assert cls(statement)["commitment_class"] == "OBSERVATION" and not is_hard_commitment({"original_statement": statement})


def test_supporting_figures_and_labels_are_not_targets():
    assert cls("Strong focus on profitability supported by a robust balance sheet (₹1,354 crore equity and reserves, no debt)")["verifiable_outcome"] is None
    assert cls("Capitalise on better yields and retention in Tier 2 and 3 markets")["verifiable_outcome"] is None  # "Tier 2 and 3" is a label
    assert cls("Continue to report ESG disclosures", timeframe="FY26 and ongoing")["deadline_text"] is None       # "ongoing" is not a deadline
    assert cls("Grow the business", timeframe="over the next few years")["deadline_text"] is None                  # "a few years" is not a boundary


# ── 2. the register delegates; it no longer keeps its own regexes ──
@pytest.mark.parametrize("statement, eligible, tier", [
    ("Achieve 70% self-reliance in weaponry", True, "VERIFIABLE_COMMITMENT"),     # the old "\b" after "%" never matched, so this was STRATEGIC_INTENT
    ("Launch the next level of strategic growth after assessing readiness", True, "STRATEGIC_INTENT"),  # the old test counted the capitalised first word as a "named subject"
    ("Achieve 70% self-reliance in weaponry", False, "STRATEGIC_INTENT"),         # not eligible to be a commitment at all
    ("We will launch Product X in Japan", True, "VERIFIABLE_COMMITMENT"),
])
def test_register_tier_is_the_canonical_verdict(statement, eligible, tier):
    assert classify_accountability_ontology(statement, commitment_eligible=eligible) == tier


def test_register_fields_are_stamped_from_the_same_owner():
    fields = canonical_commitment_fields(original_statement="Achieve 70% self-reliance in weaponry", normalized_commitment="Achieve 70 self reliance in weaponry.",
                                         expected_timeframe="by 2027", announcement_period="fy22", ontology="VERIFIABLE_COMMITMENT")
    assert fields["hard_commitment"] and fields["commitment_class"] == "HARD_COMMITMENT" and fields["commitment_basis"]["deadline_year"] == 2027
    # a statement that is not an eligible commitment is never stamped hard, whatever it says
    assert not canonical_commitment_fields(original_statement="Achieve 70% self-reliance in weaponry", normalized_commitment="", expected_timeframe="by 2027",
                                           announcement_period="fy22", ontology="STRATEGIC_INTENT")["hard_commitment"]


# ── 3. the progression tracker: commitments only, with register identity ──
def _event(event_id, role, text, period="fy25", target="", **extra):
    return {"event_id": event_id, "role": role, "statement_text": text, "source_period": period, "event_period": period, "target_period": target, **extra}


FP_A, FP_B = "a" * 20, "b" * 20


def test_a_management_statement_with_numbers_is_not_a_measurable_commitment():
    items = [{"item_id": "MP-1", "events": [_event("s1", "statement", "Beginning with expansion, the business went live across all 568 branches")]}]
    assert _build_measurable_commitments(items, []) == []


def test_similar_outcomes_from_different_commitments_stay_two_commitments():
    items = [
        {"item_id": "MP-1", "events": [_event(FP_A, "commitment", "Open 100 branches by FY27")]},
        {"item_id": "MP-2", "events": [_event(FP_B, "commitment", "Open 100 branches by FY30")]},
    ]
    got = _build_measurable_commitments(items, [])
    assert {m["commitment_fingerprint"] for m in got} == {FP_A, FP_B}
    assert {m["commitment_fingerprint"]: m["hard_commitment"] for m in got} == {FP_A: True, FP_B: True}


def test_progression_uses_the_register_verdict_when_the_event_carries_it():
    # the deadline lives only in the register's structured field, so the event text alone is "verifiable but undated"
    stamped = _event(FP_A, "commitment", "Co-process 30% of hazardous waste.", commitment_class="HARD_COMMITMENT", hard_commitment=True, target_period="By 2025")
    got = _build_measurable_commitments([{"item_id": "MP-1", "events": [stamped]}], [])
    assert [(m["commitment_fingerprint"], m["hard_commitment"], m["target_period"]) for m in got] == [(FP_A, True, "fy25")]


# ── 4. identity agreement across modules, on real data for all four companies ──
def _tool():
    spec = importlib.util.spec_from_file_location("candidate_tool", ROOT / "tools" / "g1_candidate_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def candidates(tmp_path_factory):
    """The commitments chain (register reclassified by the canonical classifier -> progression -> promise tracker) built in a temp dir."""
    tool, out = _tool(), tmp_path_factory.mktemp("g2_candidates")
    built = {}
    for company in COMPANIES:
        src, dst = ROOT / "companies" / company, out / "companies" / company
        (dst / "company_memory").mkdir(parents=True)
        tool.commitments_stage(company, src, dst, out)
        memory = dst / "company_memory"
        load = lambda rel: json.loads((memory / rel).read_text())
        built[company] = (load("management_commitments/management_commitments.json")["commitments"], load("management_progression/management_progression.json"), load("gold/management_promise_tracker.json"))
    return built


@pytest.mark.parametrize("company", COMPANIES)
def test_every_layer_agrees_on_which_commitments_qualify(company, candidates):
    register, progression, tracker = candidates[company]
    ident = {c["commitment_fingerprint"]: c["id"] for c in register}
    names = lambda fps: {ident[f] for f in fps}
    reg_hard = {c["commitment_fingerprint"] for c in register if c["hard_commitment"]}
    reg_tier = {c["commitment_fingerprint"] for c in register if c["accountability_ontology"] == "VERIFIABLE_COMMITMENT"}
    tracker_hard = {p["commitment_fingerprint"] for p in tracker["accountability_promises"] if p["hard_commitment"]}
    tracker_tier = {p["commitment_fingerprint"] for p in tracker["accountability_promises"]}
    measurable = progression["measurable_commitments"]
    progression_hard = {m["commitment_fingerprint"] for m in measurable if m["hard_commitment"]}
    progression_tier = {m["commitment_fingerprint"] for m in measurable}
    # the same commitments, by identity - not merely the same totals
    assert names(reg_hard) == EXPECTED_HARD[company]
    assert tracker_hard == progression_hard == reg_hard
    assert tracker_tier == progression_tier == reg_tier
    assert all(m["commitment_fingerprint"] for m in measurable)  # every measurable commitment has a register identity
    assert tracker["summary"]["accountability_metrics"]["hard_commitments"] == len(reg_hard)


# The frozen M50.1 fact-pack predicate (structured timeframe only, regexes fitted to Sun) still feeds the V3/V4/V5 management-quality contracts.
# It is NOT edited (that would change pinned contract fingerprints and the V5 candidate under review); its divergence from the canonical
# classifier is therefore pinned here, by identity, until a new management-quality contract version adopts the canonical one (gate G7).
LEGACY_MISSES = {"sun_pharma": set(), "tanla": set(), "ujjivan": {"MC-0043"}, "datapatterns": set()}   # G2.1: DP MC-0006 is an outlook, no longer hard under either reading


@pytest.mark.parametrize("company", COMPANIES)
def test_frozen_m501_predicate_divergence_is_pinned_by_identity(company, candidates):
    register = candidates[company][0]
    ident = {c["commitment_fingerprint"]: c["id"] for c in register}
    legacy = {c["commitment_fingerprint"] for c in _count_hard_commitments(register)[1]}
    canonical = {c["commitment_fingerprint"] for c in register if c["hard_commitment"]}
    assert {ident[f] for f in canonical - legacy} == LEGACY_MISSES[company]   # what the frozen predicate fails to count
    assert legacy <= canonical                                                # and it never counts something the policy rejects


def test_the_frozen_predicate_file_is_untouched():
    # pinned digest of fact_pack_v2.py as committed: the V3/V4 contract identities hash this file, so any edit changes pinned fingerprints
    import hashlib

    assert hashlib.sha256((ROOT / "intelligence/management_quality/fact_pack_v2.py").read_bytes()).hexdigest() == "889581c7ae37dce2bbc7c673748cb5ea4af0c843118d0a135d9c638ffa7aa658"


def test_the_original_conflicts_are_gone(candidates):
    # Ujjivan: "8 verifiable" (register) vs "1 measurable (568 branches)" (progression) were different populations; now one set
    _, progression, _ = candidates["ujjivan"]
    assert "568" not in json.dumps(progression["measurable_commitments"])
    # Tanla: the progression "measurable commitments" were three observed outcomes (30.9% training, 7.0% attrition, 90% reduction)
    _, progression, _ = candidates["tanla"]
    assert not any(t in json.dumps(progression["measurable_commitments"]) for t in ("30.9%", "7.0%", "90%"))
    # Sun: the lifecycle owner used to drop all three hard commitments (generic text filter + 25-item cap)
    register, progression, _ = candidates["sun_pharma"]
    ident = {c["commitment_fingerprint"]: c["id"] for c in register}
    assert {ident[m["commitment_fingerprint"]] for m in progression["measurable_commitments"] if m["hard_commitment"]} == EXPECTED_HARD["sun_pharma"]


# ── 5. net debt: one calculation, one date, one basis, labelled components ──
def entry(value, period="March 31, 2026", basis="consolidated", line="line", **extra):
    return {"value_crore": value, "period": period, "basis": basis, "source_line_item": line, **extra}


def test_net_debt_is_total_debt_minus_cash_on_one_date_and_basis():
    m = net_debt_measure(entry(4081.61, line="derived:total_debt", derived=True), entry(9770.51, line="(iii) Cash and cash equivalents"))
    assert m["status"] == "OK" and m["value"] == pytest.approx(4081.61 - 9770.51)
    assert m["components"]["debt"]["period"] == m["components"]["cash"]["period"] == "March 31, 2026" and m["components"]["cash"]["basis"] == "consolidated"


def test_cash_and_debt_of_different_years_are_never_netted():
    m = net_debt_measure(entry(4081.61, period="March 31, 2026"), entry(10268.77, period="March 31, 2025"))
    assert m["value"] is None and m["status"] == "PERIOD_MISMATCH"
    assert net_debt_measure(entry(100, period="FY26"), entry(50, period="March 31, 2026"))["status"] == "OK"  # different spellings of one date


def test_standalone_cash_is_not_netted_against_consolidated_debt():
    assert net_debt_measure(entry(100, basis="consolidated"), entry(50, basis="standalone"))["status"] == "BASIS_MISMATCH"
    assert net_debt_measure(entry(100, basis="consolidated"), entry(50, basis="unknown"))["status"] == "OK"  # unknown does not prove a mismatch


def test_a_debt_total_built_from_one_section_line_is_not_a_total():
    partial = entry(6197.88, derived=True, derivation_state="PARTIAL_COMPONENT_ONLY")
    m = net_debt_measure(partial, entry(4623.73))
    assert m["value"] is None and m["status"] == "INCOMPLETE_DEBT"


def test_cash_and_bank_balances_is_netted_but_labelled():
    m = net_debt_measure(entry(0.0), entry(1064.0, warnings=["definition:cash_and_bank_balances - includes bank balances other than cash equivalents"]))
    assert m["value"] == pytest.approx(-1064.0) and m["components"]["cash"]["definition"] == "cash_and_bank_balances"
    assert any(w.startswith("definition:cash_and_bank_balances") for w in m["warnings"])
    assert "definition" not in net_debt_measure(entry(0.0), entry(1064.0))["components"]["cash"]


def test_a_bank_has_no_net_debt():
    bank = {"source_section_type": "schedule_6_cash_rbi"}
    m = net_debt_measure(entry(2845.36, **bank), entry(3133.37, **bank))
    assert m["value"] is None and m["status"] == "NOT_APPLICABLE_BANK"


def test_missing_inputs_are_missing_not_zero():
    assert net_debt_measure(entry(None), entry(50))["status"] == "MISSING_INPUT" and net_debt_measure(entry(100), entry(None))["value"] is None


def test_fact_registry_no_longer_derives_a_second_net_debt():
    from knowledge.financials import fact_registry

    assert not hasattr(fact_registry, "_derive_net_debt")


@pytest.mark.parametrize("company, fy, status, value", [
    ("sun_pharma", "fy26", "OK", -5688.9),        # closing cash 9,770.51 (not the FY25 balance) against current + non-current borrowings 4,081.61
    ("sun_pharma", "fy25", "OK", -8399.14),
    ("ujjivan", "fy25", "NOT_APPLICABLE_BANK", None),
    ("datapatterns", "fy25", "MISSING_INPUT", None),   # no borrowings line was extracted: nothing is guessed
])
def test_net_debt_on_real_balance_sheets(company, fy, status, value):
    from knowledge.financials.normalizer import normalize_financial_tables

    bs = normalize_financial_tables(company=company, year=fy, raw_tables_path=ROOT / "companies" / company / fy / "financials" / "raw_financial_tables.json")["balance_sheet"]
    m = net_debt_measure(bs["total_debt"], bs["cash_and_equivalents"])
    assert m["status"] == status and (m["value"] is None if value is None else m["value"] == pytest.approx(value, abs=0.01))
